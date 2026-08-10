"""
app.py — hosted ingestion service for the DATA INAMOVIBLE (GWT v1.1, ADR-0017/0021).

The front door for teammates to COMPLEMENT the source of truth WITHOUT the repo or write credentials.
A teammate POSTs a public URL or uploads a file; the service stores the raw (source-pointer for public /
MinIO mirror for uploads), classifies it, extracts verified entities (resolve_id gate — never minted),
and parks a PROPOSED record in a pending queue. Only the ADMIN token can /approve, which merges the
record into the manifest and ingests it into Neo4j. The human gate (CLAUDE.md §7) is preserved: teammates
SUBMIT; a human APPROVES.

Auth (bearer tokens, env): INGEST_SUBMIT_TOKEN (teammates), INGEST_ADMIN_TOKEN (the approver).
Reuses the repo libs (raw_store, corpus_classifier, resolve_id) + ingest.py. Runs where Neo4j + MinIO +
the repo are reachable (same Dokploy network). Deploy: see README.md. NOT a public-internet service
without TLS + tokens.
"""
import datetime
import os
import sys
import json
import threading
import uuid
import tempfile
import subprocess
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))   # for git_sync (sibling module)
from lib import resolve_id, raw_store, corpus_classifier, add_dataset  # noqa: E402
import git_sync  # noqa: E402

QUEUE = Path(os.environ.get("INGEST_QUEUE_DIR", str(Path(__file__).parent / "queue")))
QUEUE.mkdir(parents=True, exist_ok=True)
# ADR-0045: a reject ARCHIVES (append-only), never deletes — /reject used to unlink the proposal and
# return 200 even for nonexistent ids, leaving no author, no reason, no record (incompatible with the
# DI-change history the webapp decisions require).
REJECTED = Path(os.environ.get("INGEST_REJECTED_DIR", str(Path(__file__).parent / "rejected")))
REJECTED.mkdir(parents=True, exist_ok=True)
ACTIONS_LOG = Path(os.environ.get("INGEST_ACTIONS_LOG", str(Path(__file__).parent / "actions_log.jsonl")))
MANIFEST = ROOT / "rag_index" / "corpus_manifest.json"
INGEST = ROOT / "rag_index" / "graphrag" / "ingest.py"
SUBMIT_TOKEN = os.environ.get("INGEST_SUBMIT_TOKEN")
ADMIN_TOKEN = os.environ.get("INGEST_ADMIN_TOKEN")

# ADR-0045: /approve and /reject are serialized. Two concurrent /approve computed the SAME _next_id, ran
# two full re-ingests, and the loser's git PUT failed with the data already in Neo4j ("applied in Neo4j
# but NOT in git" — half an ingest, which breaks inamovibility).
_WRITE_LOCK = threading.Lock()

# ADR-0052 (block 5): the write section is ALSO serialized across PROCESSES on the host — the promised
# "cola FIFO con concurrencia 1" is now structural, not an artifact of running one uvicorn worker. A
# file lock (O_CREAT|O_EXCL) next to the queue volume; a crashed holder must never wedge the human gate,
# so locks older than INGEST_LOCK_STALE_S are taken over. If the lock cannot be acquired within
# INGEST_LOCK_TIMEOUT_S the request gets an honest 503 ("write queue busy"), never a silent race.
LOCK_FILE = Path(os.environ.get("INGEST_LOCK_FILE", str(Path(__file__).parent / "write.lock")))
LOCK_TIMEOUT_S = float(os.environ.get("INGEST_LOCK_TIMEOUT_S", "30"))
LOCK_STALE_S = float(os.environ.get("INGEST_LOCK_STALE_S", "900"))


class _CrossProcessLock:
    def __enter__(self):
        import time as _t
        deadline = _t.time() + LOCK_TIMEOUT_S
        while True:
            try:
                fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"pid={os.getpid()} at={_now_iso()}".encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:  # stale takeover: the previous holder died mid-write
                    if _t.time() - LOCK_FILE.stat().st_mtime > LOCK_STALE_S:
                        LOCK_FILE.unlink(missing_ok=True)
                        continue
                except OSError:
                    continue
                if _t.time() > deadline:
                    raise HTTPException(status_code=503,
                                        detail="write queue busy (another approve/reject in flight) — retry")
                _t.sleep(0.2)

    def __exit__(self, *exc):
        try:
            LOCK_FILE.unlink(missing_ok=True)
        except OSError:
            pass

app = FastAPI(title="DATA INAMOVIBLE ingestion service", version="1.2")


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _log_action(entry):
    """Append-only action log (seed of the block-5 DI-change registry): who did what, when, outcome.
    Never raises (same pattern as server._log): the PRIMARY record of an approve is the manifest+git,
    of a reject the archived proposal — this log is the queryable index, not the record itself."""
    try:
        entry = {"ts": _now_iso(), **entry}
        with ACTIONS_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _auth(authorization, expected, role):
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not expected or token != expected:
        raise HTTPException(status_code=401, detail=f"{role} token required")


def _next_id():
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return add_dataset._next_id(man)


@app.get("/health")
def health():
    return {"ok": True, "pending": len(list(QUEUE.glob("*.json")))}


@app.post("/submit")
async def submit(authorization: str = Header(None), name: str = Form(...), source_db: str = Form("local"),
                 accession: str = Form(None), niche: str = Form(None), domain: str = Form(None),
                 url: str = Form(None), private: bool = Form(False), file: UploadFile = File(None)):
    """Teammate submission -> a PROPOSED record parked in the queue (NOT yet in the truth)."""
    _auth(authorization, SUBMIT_TOKEN, "submit")
    if not url and not file:
        raise HTTPException(status_code=400, detail="provide a public --url or upload a file")

    raw_files, ents = [], []
    if url:
        ref = raw_store.source_pointer(url); ref["filename"] = url.split("/")[-1]
        raw_files.append(ref)
    if file is not None:
        tmp = Path(tempfile.gettempdir()) / file.filename
        tmp.write_bytes(await file.read())
        if private:
            ref = raw_store.put(tmp, source_url=None)
        else:
            ref = raw_store.source_pointer(f"upload://{file.filename}", path=tmp)
        ref["filename"] = file.filename
        raw_files.append(ref)
        try:
            ents = add_dataset.verified_entities(tmp)
        except Exception:
            ents = []

    cls = corpus_classifier.propose_categorization(file.filename if file else (url or name), f"{name} {url or ''}")
    sid = uuid.uuid4().hex[:12]
    proposal = {
        "submission_id": sid, "corpus_record_id": _next_id(),
        "source_document": {"name": name, "accession": accession, "source_db": source_db},
        "axis_data_niche": {"primary": niche or cls["data_niche_candidates"][0]},
        "axis_scientific_domain": {"primary": domain or "N1"},
        "entities_extracted": ents,
        "proposed_placement": {"data_niche": niche or cls["data_niche_candidates"][0],
                               "confidence": cls["confidence"], "reasoning": "corpus_classifier v1; human gate required"},
        "raw_provenance": {"policy": "hybrid", "files": raw_files},
        "approval_chain": [{"gate": "categorization", "status": "pending_review"}],
        "substrate_evidence": ["test_1", "test_3"],
        "created_at": _now_iso(),   # ADR-0045: queue order + history need a timestamp (uuid4 has none)
    }
    (QUEUE / f"{sid}.json").write_text(json.dumps(proposal, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"submitted": True, "submission_id": sid, "verified_entities": len(ents),
            "proposed_niche": proposal["proposed_placement"]["data_niche"],
            "note": "PENDING human approval. An admin must /approve before it enters the source of truth."}


@app.get("/pending")
def pending(authorization: str = Header(None)):
    _auth(authorization, ADMIN_TOKEN, "admin")
    items = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(QUEUE.glob("*.json"))]
    # ADR-0045: FIFO by submission time — lexicographic order over a uuid4 filename is no order at all.
    # Legacy proposals without created_at sort first (oldest-unknown surfaces before anything newer).
    items.sort(key=lambda p: p.get("created_at", ""))
    return {"pending": [{"submission_id": p["submission_id"], "name": p["source_document"]["name"],
                         "niche": p["proposed_placement"]["data_niche"],
                         "entities": len(p["entities_extracted"]),
                         "created_at": p.get("created_at")} for p in items]}


@app.get("/pending/{sid}")
def pending_detail(sid: str, authorization: str = Header(None)):
    """The FULL proposal for the human gate (ADR-0052, block 5). The list endpoint shows 4 summary
    fields; approving on those alone is signing blind — the opposite of a human gate (handoff §5.4).
    Here the approver sees confidence, reasoning, gap_flags, extracted entities and raw provenance
    BEFORE putting their name on the approval chain."""
    _auth(authorization, ADMIN_TOKEN, "admin")
    qf = QUEUE / f"{sid}.json"
    if not qf.exists():
        raise HTTPException(status_code=404, detail="no such submission")
    return json.loads(qf.read_text(encoding="utf-8"))


@app.get("/actions")
def actions(limit: int = 100, authorization: str = Header(None)):
    """The DI-change history read path (decision 9-bis; seeded by ADR-0045's append-only action log):
    who approved/rejected what, when, with which outcome. Newest first."""
    _auth(authorization, ADMIN_TOKEN, "admin")
    if not ACTIONS_LOG.exists():
        return {"actions": []}
    lines = ACTIONS_LOG.read_text(encoding="utf-8").splitlines()
    out = []
    for line in reversed(lines[-max(1, min(limit, 1000)):]):
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return {"actions": out}


@app.post("/approve/{sid}")
def approve(sid: str, by: str, authorization: str = Header(None)):
    """The HUMAN GATE: merge a queued proposal into the manifest + ingest into Neo4j.
    Serialized under _WRITE_LOCK (ADR-0045): the whole read-manifest -> _next_id -> ingest -> git
    sequence is one critical section, so two concurrent approvals can no longer mint the same
    corpus_record_id or interleave half-ingests. A concurrent duplicate of the SAME sid gets a 404
    (the first one consumed the queue file) — idempotent by construction."""
    _auth(authorization, ADMIN_TOKEN, "admin")
    with _WRITE_LOCK, _CrossProcessLock():
        qf = QUEUE / f"{sid}.json"
        if not qf.exists():
            raise HTTPException(status_code=404, detail="no such submission")
        proposal = json.loads(qf.read_text(encoding="utf-8"))
        proposal.pop("submission_id", None)
        proposal["approval_chain"] = [{"gate": "categorization", "status": "approved", "approved_by": by,
                                       "approved_at": _now_iso()}]

        # canonical manifest: GitHub if push-back is configured (avoids clobbering concurrent edits), else local.
        git_on, sha = git_sync.enabled(), None
        if git_on:
            man, sha = git_sync.get_manifest()
        else:
            man = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cid = add_dataset._next_id(man)                   # recompute against canonical state (no ID collision)
        proposal["corpus_record_id"] = cid
        man["records"].append(proposal)
        man["status"] = f"{cid} approved by {by} via ingest_service."
        MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")  # local, for ingest

        r = subprocess.run([sys.executable, str(INGEST)], capture_output=True, text=True)

        git_status = "disabled (a maintainer syncs the manifest)"
        if git_on and r.returncode == 0:
            try:
                commit = git_sync.put_manifest(man, sha, f"corpus: approve {cid} via ingest service (by {by})")
                git_status = f"committed to git ({commit[:9]})"
            except Exception as e:
                git_status = f"git push FAILED: {type(e).__name__}: {str(e)[:120]}"
        elif git_on:
            git_status = "skipped (ingest failed; not committed to git)"
        qf.unlink()
    _log_action({"action": "approve", "submission_id": sid, "corpus_record_id": cid, "by": by,
                 "ingest_exit": r.returncode, "git_sync": git_status})
    return {"approved": True, "corpus_record_id": cid, "by": by,
            "ingest_exit": r.returncode, "ingest_tail": (r.stdout or r.stderr)[-200:],
            "git_sync": git_status}


@app.post("/reject/{sid}")
def reject(sid: str, by: str, reason: str, authorization: str = Header(None)):
    """The OTHER half of the human gate (ADR-0045): a rejection is a RECORDED decision, not a silent
    deletion. Requires author + non-empty reason; 404s on an unknown sid (the old handler returned 200
    and deleted nothing/anything silently); archives the full proposal, append-only, with the verdict."""
    _auth(authorization, ADMIN_TOKEN, "admin")
    if not (reason or "").strip():
        raise HTTPException(status_code=400, detail="a non-empty rejection reason is required")
    with _WRITE_LOCK, _CrossProcessLock():
        qf = QUEUE / f"{sid}.json"
        if not qf.exists():
            raise HTTPException(status_code=404, detail="no such submission")
        proposal = json.loads(qf.read_text(encoding="utf-8"))
        proposal["approval_chain"] = [{"gate": "categorization", "status": "rejected",
                                       "rejected_by": by, "reason": reason, "rejected_at": _now_iso()}]
        archived = REJECTED / f"{sid}.json"
        archived.write_text(json.dumps(proposal, indent=2, ensure_ascii=False), encoding="utf-8")
        qf.unlink()
    _log_action({"action": "reject", "submission_id": sid, "by": by, "reason": reason})
    return {"rejected": True, "submission_id": sid, "by": by, "reason": reason,
            "archived_to": str(archived)}

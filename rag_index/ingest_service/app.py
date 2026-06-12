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
import os
import sys
import json
import uuid
import tempfile
import subprocess
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
from lib import resolve_id, raw_store, corpus_classifier, add_dataset  # noqa: E402

QUEUE = Path(os.environ.get("INGEST_QUEUE_DIR", str(Path(__file__).parent / "queue")))
QUEUE.mkdir(parents=True, exist_ok=True)
MANIFEST = ROOT / "rag_index" / "corpus_manifest.json"
INGEST = ROOT / "rag_index" / "graphrag" / "ingest.py"
SUBMIT_TOKEN = os.environ.get("INGEST_SUBMIT_TOKEN")
ADMIN_TOKEN = os.environ.get("INGEST_ADMIN_TOKEN")

app = FastAPI(title="DATA INAMOVIBLE ingestion service", version="1.0")


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
    }
    (QUEUE / f"{sid}.json").write_text(json.dumps(proposal, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"submitted": True, "submission_id": sid, "verified_entities": len(ents),
            "proposed_niche": proposal["proposed_placement"]["data_niche"],
            "note": "PENDING human approval. An admin must /approve before it enters the source of truth."}


@app.get("/pending")
def pending(authorization: str = Header(None)):
    _auth(authorization, ADMIN_TOKEN, "admin")
    items = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(QUEUE.glob("*.json"))]
    return {"pending": [{"submission_id": p["submission_id"], "name": p["source_document"]["name"],
                         "niche": p["proposed_placement"]["data_niche"],
                         "entities": len(p["entities_extracted"])} for p in items]}


@app.post("/approve/{sid}")
def approve(sid: str, by: str, authorization: str = Header(None)):
    """The HUMAN GATE: merge a queued proposal into the manifest + ingest into Neo4j."""
    _auth(authorization, ADMIN_TOKEN, "admin")
    qf = QUEUE / f"{sid}.json"
    if not qf.exists():
        raise HTTPException(status_code=404, detail="no such submission")
    proposal = json.loads(qf.read_text(encoding="utf-8"))
    proposal.pop("submission_id", None)
    proposal["approval_chain"] = [{"gate": "categorization", "status": "approved", "approved_by": by}]
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    man["records"].append(proposal)
    man["status"] = f"{proposal['corpus_record_id']} approved by {by} via ingest_service."
    MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(INGEST)], capture_output=True, text=True)
    qf.unlink()
    return {"approved": True, "corpus_record_id": proposal["corpus_record_id"], "by": by,
            "ingest_exit": r.returncode, "ingest_tail": (r.stdout or r.stderr)[-300:],
            "note": "manifest updated on the service's repo copy — a maintainer commits it back to git (see README)."}


@app.post("/reject/{sid}")
def reject(sid: str, authorization: str = Header(None)):
    _auth(authorization, ADMIN_TOKEN, "admin")
    qf = QUEUE / f"{sid}.json"
    if qf.exists():
        qf.unlink()
    return {"rejected": True, "submission_id": sid}

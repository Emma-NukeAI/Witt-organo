"""
app.py — read-only HTTP query service for the webapp (block 2, ADR-0048; tapón 4 of the webapp handoff).

WHAT THIS IS. The HTTP front door the webapp reads through. It is a TRANSPORT CHANGE, not a new
semantic layer: /query returns EXACTLY the envelope `server._query` produces ({degraded, n_hits, hits,
last_error, index_version, store_version}, ADR-0043) — same backend, same markers, same §6 no-hang rule
as the CLI `witt-di` and the MCP. Choosing this door does NOT change the data (the trap faltantes §1.4
documented: rag_backend direct said 'sparse-by-config', the CLI said 'sparse', the envelope existed only
in the CLI).

WHAT THIS IS NOT. It exposes ZERO mutation: no ingest, no DI writes (those stay behind the human gate of
the ingest_service / repo scripts). It is deployed on the Dokploy INTERNAL network — the webapp is the
only exposed surface (ADR-0047 decision 5; direction of the parked ADR-0033).

The four inherited traps (all four caused real incidents — faltantes §1.4):
  1. sklearn/numpy MUST first-import on the MAIN thread before serving (the 1800s deadlock): done in
     lifespan() via _preload_main_thread().
  2. EMBED_MODEL is hard-pinned to 'openai' when NEO4J_URI is set: inherited by importing `server`
     (its _load_local_secrets pins it at import).
  3. .secrets/deploy.env loads at import: inherited the same way; the container must carry the secrets.
  4. Worker pool sizing: server._QUERY_POOL honors DI_QUERY_POOL_SIZE (README: set 8 for 5 users).

Run (single process — in-process caches and the block-5 write queue assume ONE worker):
    uvicorn app:app --host 0.0.0.0 --port 8078 --workers 1
"""
import datetime
import hashlib
import json
import os
import re
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
sys.path.insert(0, str(ROOT / "rag_index" / "mcp_server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import server  # noqa: E402  (side effects: deploy.env + EMBED_MODEL pin + backend import — traps 2/3)
import db  # noqa: E402
import precedent as precedent_mod  # noqa: E402
import runs as runs_mod  # noqa: E402
from lib import rag_backend  # noqa: E402

SERVICE_VERSION = "1.0"
STATUS_TTL_S = int(os.environ.get("WITT_STATUS_TTL_SECONDS", "60"))
ARTIFACTS_TTL_S = int(os.environ.get("WITT_ARTIFACTS_TTL_SECONDS", "60"))
REPORTS_DIR = ROOT / "reports"
RUNS_DIR = ROOT / "evaluation" / "runs"

_STATE = {"started_at": None, "preloaded": False}


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _preload_main_thread():
    """Trap 1: a first-time sklearn/numpy import from a NON-main thread deadlocks on the import lock
    (the true cause of the 2026-07-18/19 1800s stall). Pay the import + build the sparse index HERE,
    before accepting traffic; worker threads then reuse sys.modules. Also warm the dense half (one
    embed at boot, authorized spend) so the first user query is ~0.5s, not ~4-6s."""
    try:
        n = len(rag_backend.query_sparse("startup preload pronephros", 1))
        server._log(f"query_service preload sparse OK hits={n}")
    except Exception as e:
        server._log(f"query_service preload sparse ERROR {type(e).__name__}: {str(e)[:160]}")
    if os.environ.get("NEO4J_URI"):
        try:
            rag_backend.query("startup preload pronephros zebrafish", 1)
            server._log("query_service preload dense OK")
        except Exception as e:
            server._log(f"query_service preload dense ERROR {type(e).__name__}: {str(e)[:160]}")
    _STATE["preloaded"] = True


@asynccontextmanager
async def lifespan(_app):
    _STATE["started_at"] = _now_iso()
    db.init_db()
    _preload_main_thread()   # lifespan runs on the main thread, before serving — trap 1
    # run workers start AFTER the main-thread preload (the 1800s deadlock cannot recur) — ADR-0050
    runs_mod.start_workers(int(os.environ.get("WITT_RUN_WORKERS", "2")))
    yield
    runs_mod.stop_workers()


app = FastAPI(title="Witt DATA INAMOVIBLE query service (read-only)", version=SERVICE_VERSION,
              lifespan=lifespan)

_cors = [o.strip() for o in os.environ.get("WITT_CORS_ORIGINS", "").split(",") if o.strip()]
if _cors:
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(CORSMiddleware, allow_origins=_cors, allow_credentials=True,
                       allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])


# --- auth ------------------------------------------------------------------------------------------

def _user_of(authorization):
    """Bearer session token -> user dict; 401 otherwise. Flat permissions (ADR-0047): every valid
    session may read everything here; account admin lives ONLY in seed_users.py (local CLI)."""
    token = (authorization or "").removeprefix("Bearer ").strip()
    user = db.validate_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="valid session token required (POST /login)")
    return user


class LoginBody(BaseModel):
    username: str
    password: str


@app.post("/login")
def login(body: LoginBody):
    user = db.check_password(body.username.strip().lower(), body.password)
    if user is None:
        time.sleep(0.5)   # cheap tarpit; the service lives on the internal network (ADR-0047 d.5)
        raise HTTPException(status_code=401, detail="invalid credentials")
    sess = db.create_session(user["user_id"])
    return {**user, **sess}


@app.post("/logout")
def logout(authorization: str = Header(None)):
    _user_of(authorization)
    db.revoke_token((authorization or "").removeprefix("Bearer ").strip())
    return {"ok": True}


@app.get("/me")
def me(authorization: str = Header(None)):
    return _user_of(authorization)


# --- liveness (Dokploy healthcheck): process-only, no auth, no network, no spend --------------------

@app.get("/health")
def health():
    return {"ok": True, "service": "witt-query-service", "version": SERVICE_VERSION,
            "started_at": _STATE["started_at"], "preloaded": _STATE["preloaded"]}


# --- the read front door: EXACTLY the CLI/MCP envelope (transport change, ADR-0043/0048) ------------

@app.get("/query")
def query(q: str, k: int = 5, niche: str = None, authorization: str = Header(None)):
    """Semantic GraphRAG query. Returns server._query's envelope VERBATIM — {degraded, n_hits, hits,
    last_error, index_version, store_version}. Degraded results are 200 (a valid, banded answer the UI
    must paint); only query_unavailable is 503.

    LOTE-02·4 — `niche` (optional): a DECLARED post-retrieval filter. It filters a k*4 candidate window
    by the per-hit `record.data_niche` binding (block 1.4) and adds a `filter` block saying exactly what
    was done (candidates_considered + the recall caveat). A retrieve-level filter — the one agent doors
    would also use — is a future retrieval feature; this is honest filtering, never a disguised one.
    Without `niche` the envelope stays a verbatim mirror (no `filter` key)."""
    _user_of(authorization)
    if not niche:
        res = server._query(q, k)
        if "error" in res:
            raise HTTPException(status_code=503, detail=res)
        return res
    res = server._query(q, min(k * 4, 40))
    if "error" in res:
        raise HTTPException(status_code=503, detail=res)
    matched = [h for h in res["hits"] if (h.get("record") or {}).get("data_niche") == niche][:k]
    return {**res, "hits": matched, "n_hits": len(matched),
            "filter": {"niche": niche, "applied": "post-retrieval",
                       "candidates_considered": len(res["hits"]),
                       "note": "filtra por record.data_niche sobre una ventana k*4 de candidatos; el "
                               "recall fuera de esa ventana NO se explora — el filtro a nivel retrieve "
                               "(el que usarían también CLI/MCP) es feature futura de recuperación"}}


# LOTE-01·A7: declared ONCE, structurally — the verified store is an identity+provenance store; it has
# no per-entity niche/domain/context/metabolic-role axes and NEVER will through this door. Per-entity
# taxonomy derives from the GRAPH (Entity-MENTIONS-Document-IN_NICHE), i.e. the future browse operation
# (Rack fase 2, LOTE B). The UI can render "nunca por esta puerta" instead of "todavía no".
_TAXONOMY_AXES_DECL = {"served": False,
                       "why": "the verified store carries identity+provenance only; per-entity "
                              "niche/domain derives from graph MENTIONS — the browse operation "
                              "(Rack fase 2), never this door"}


@app.get("/resolve")
def resolve(key: str, authorization: str = Header(None)):
    """Deterministic verified-identifier resolve — full VerifiedRecord (block 1.4). NOT_FOUND is a
    positive result (200, resolved: false), not an HTTP error. `taxonomy_axes` declares that per-entity
    axes are NEVER served by this door (LOTE-01·A7)."""
    _user_of(authorization)
    return {**server._resolve(key), "taxonomy_axes": _TAXONOMY_AXES_DECL}


@app.get("/raw")
def raw(key: str, filename: str = None, authorization: str = Header(None)):
    """Drill to the RAW layer (fetch_raw): presigned MinIO URL or canonical source_url + sha256."""
    _user_of(authorization)
    res = server._fetch_raw(key, filename)
    if not res.get("found"):
        raise HTTPException(status_code=404, detail=res)
    return res


# --- StoreStatus: the UI contract's 9 fields + ADR-0048/0055 extensions (index_version, integrity,
# --- embed_model_changed_at), aggregated from the disconnected sources, NO-SPEND ---------------------

_STATUS_CACHE = {"at": 0.0, "data": None}


def _neo4j_counts():
    """liveness.py pattern: free Cypher counts + vector-index state. NEVER embeds (no OpenAI). Bounded
    connect timeout so a Neo4j outage degrades the status to OFFLINE instead of hanging it."""
    from neo4j import GraphDatabase
    uri = os.environ["NEO4J_URI"]
    drv = GraphDatabase.driver(uri, auth=(os.environ.get("NEO4J_USER", "neo4j"),
                                          os.environ["NEO4J_PASSWORD"]), connection_timeout=5)
    try:
        with drv.session() as s:
            doc = s.run("MATCH (d:Document) RETURN count(d) AS c").single()["c"]
            ent = s.run("MATCH (e:Entity) RETURN count(e) AS c").single()["c"]
            state, dim = "POPULATING", None
            for r in s.run("SHOW INDEXES YIELD name, type, state, options"):
                if str(r["type"]).upper().startswith("VECTOR"):
                    state = "ONLINE" if str(r["state"]).upper() == "ONLINE" else "POPULATING"
                    try:
                        dim = int(r["options"]["indexConfig"]["vector.dimensions"])
                    except Exception:
                        pass
        return {"doc_count": doc, "entity_count": ent, "index_state": state, "embed_dim": dim}
    finally:
        drv.close()


_INTEGRITY_ARTIFACT = ROOT / "analysis" / "outputs" / "store_integrity_scan_latest.json"
_CONFIG_HISTORY = ROOT / "rag_index" / "config_history.json"


def _integrity_row():
    """LOTE-01·A8a: the M2 integrity row, served ONLY from a real scan artifact (the convention:
    `store_integrity_scan.py --json analysis/outputs/store_integrity_scan_latest.json`). No artifact
    -> an honest 'scanned: false' — a missing scan is never rendered as a clean one."""
    if not _INTEGRITY_ARTIFACT.exists():
        return {"scanned": False,
                "note": "no scan artifact — run: python substrate_calibration/tools/"
                        "store_integrity_scan.py --json analysis/outputs/store_integrity_scan_latest.json"}
    try:
        rep = json.loads(_INTEGRITY_ARTIFACT.read_text(encoding="utf-8"))
        findings = rep.get("findings", [])
        return {"scanned": True,
                "scanned_at": datetime.datetime.fromtimestamp(
                    _INTEGRITY_ARTIFACT.stat().st_mtime,
                    datetime.timezone.utc).isoformat(timespec="seconds"),
                "n_records": rep.get("n_records"), "store_version": rep.get("store_version"),
                "n_findings": len(findings),
                "n_critical_high": sum(1 for f in findings
                                       if f.get("severity") in ("critical", "high"))}
    except Exception as e:
        return {"scanned": False, "note": f"scan artifact unreadable: {type(e).__name__}"}


def _embed_model_changed_at():
    """LOTE-01·A8b: without this date the UI cannot warn when old scores stopped being comparable
    ('el único caso en que un score viejo miente'). Source: rag_index/config_history.json (append-only,
    dates sourced from ADRs) — never a hardcoded constant in code."""
    try:
        hist = json.loads(_CONFIG_HISTORY.read_text(encoding="utf-8"))
        entries = [e for e in hist.get("entries", []) if e.get("field") == "embed_model"]
        return entries[-1]["changed_at"] if entries else None
    except Exception:
        return None


def _store_status():
    """StoreStatus: the UI contract's 9 fields (store_version, record_count, sha, doc_count,
    entity_count, embed_model, embed_dim, index_state, refreshed_at) + the ADR-0048/0055 extensions:
    index_version (score comparability), integrity (real scan or honest 'scanned: false') and
    embed_model_changed_at (config_history.json — the catalog has history). TTL-cached: a UI header
    polling every N seconds costs at most one free Cypher round per TTL and ZERO OpenAI, always — a
    status indicator that costs money ends up turned off, and that is the one that must never turn off."""
    now = time.time()
    if _STATUS_CACHE["data"] and now - _STATUS_CACHE["at"] < STATUS_TTL_S:
        return _STATUS_CACHE["data"]
    raw_bytes = (ROOT / "analysis" / "outputs" / "verified_identifiers.json").read_bytes()
    store = json.loads(raw_bytes)
    embed_model = os.environ.get("EMBED_MODEL") if os.environ.get("NEO4J_URI") else "sparse(dev)"
    st = {"store_version": store.get("store_version"),
          "record_count": store.get("n_records"),
          "sha": hashlib.sha256(raw_bytes).hexdigest(),
          "doc_count": None, "entity_count": None,
          "embed_model": embed_model,
          "embed_dim": 1536 if embed_model == "openai" else None,   # the ADR-0039 hard pin
          "index_state": "OFFLINE",
          "index_version": server._index_version(),
          "integrity": _integrity_row(),
          "embed_model_changed_at": _embed_model_changed_at(),
          "refreshed_at": _now_iso()}
    if os.environ.get("NEO4J_URI"):
        try:
            st.update(_neo4j_counts())
        except Exception as e:   # unreachable graph -> honest OFFLINE + nulls; NEVER invented counts
            st["status_error"] = f"{type(e).__name__}: {str(e)[:120]}"
    _STATUS_CACHE.update(at=now, data=st)
    return st


@app.get("/status")
def status(authorization: str = Header(None)):
    _user_of(authorization)
    return _store_status()


# --- historic artifacts index (ADR-0046: reports stay in master; the webapp makes them consultable) --

_ARTIFACTS_CACHE = {"at": 0.0, "data": None}
_TITLE_RE = re.compile(rb"<title[^>]*>(.*?)</title>", re.I | re.S)


def _artifacts_index():
    now = time.time()
    if _ARTIFACTS_CACHE["data"] and now - _ARTIFACTS_CACHE["at"] < ARTIFACTS_TTL_S:
        return _ARTIFACTS_CACHE["data"]
    reports = []
    for p in sorted(REPORTS_DIR.glob("*.html")):
        title = None
        m = _TITLE_RE.search(p.read_bytes()[:4096])
        if m:
            title = m.group(1).decode("utf-8", errors="replace").strip()[:200]
        stat = p.stat()
        reports.append({"name": p.name, "title": title, "bytes": stat.st_size,
                        "modified_at": datetime.datetime.fromtimestamp(
                            stat.st_mtime, datetime.timezone.utc).isoformat(timespec="seconds")})
    run_sets = {}
    for d in sorted(RUNS_DIR.iterdir()) if RUNS_DIR.exists() else []:
        if not d.is_dir():
            continue
        items = []
        for f in sorted(d.glob("*.json")):
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            items.append({"name": f.name,
                          # a run set also holds auxiliary artifacts (eps probes, summaries) — tag them
                          # so the UI lists them apart from claim records instead of hiding them
                          "kind": "claim_record" if (isinstance(rec, dict) and rec.get("claim_id")) else "aux",
                          "claim_id": rec.get("claim_id") if isinstance(rec, dict) else None,
                          "question": ((rec.get("question") if isinstance(rec, dict) else "") or "")[:200],
                          # ADR-0046/handoff §5.6: the historic corpus has NO decision_state — the UI
                          # shows these as not-instrumented, never as clean.
                          "instrumented": isinstance(rec, dict) and "decision_state" in rec})
        run_sets[d.name] = items
    data = {"reports": reports, "runs": run_sets, "refreshed_at": _now_iso()}
    _ARTIFACTS_CACHE.update(at=now, data=data)
    return data


@app.get("/artifacts")
def artifacts(authorization: str = Header(None)):
    _user_of(authorization)
    return _artifacts_index()


@app.get("/artifacts/report/{name}")
def artifact_report(name: str, authorization: str = Header(None)):
    """Serve one historic HTML report. Path-safe by membership: `name` must be in the index — no path
    arithmetic on user input ever touches the filesystem."""
    _user_of(authorization)
    if not any(r["name"] == name for r in _artifacts_index()["reports"]):
        raise HTTPException(status_code=404, detail="no such report")
    return FileResponse(REPORTS_DIR / name, media_type="text/html")


@app.get("/artifacts/run/{run_set}/{name}")
def artifact_run(run_set: str, name: str, authorization: str = Header(None)):
    _user_of(authorization)
    idx = _artifacts_index()["runs"]
    if run_set not in idx or not any(i["name"] == name for i in idx[run_set]):
        raise HTTPException(status_code=404, detail="no such run record")
    return json.loads((RUNS_DIR / run_set / name).read_text(encoding="utf-8"))


# --- runs: the run model + event stream (block 3, ADR-0050) -----------------------------------------

HEARTBEAT_STALE_S = int(os.environ.get("WITT_HEARTBEAT_STALE_SECONDS", "300"))


class RunBody(BaseModel):
    question: str
    entities: list[str] = []
    # ADR-0061 (tapon 3): referencia al plan declarado por POST /runs/plan. Opcional por diseno --
    # preguntar JAMAS se bloquea por el planner (no-hang §6); una corrida sin plan lo declara.
    plan_id: str | None = None


class PlanBody(BaseModel):
    question: str
    entities: list[str] = []


@app.post("/runs/plan")
def create_plan(body: PlanBody, authorization: str = Header(None)):
    """El plan declarado (tapon 3, ADR-0061): el checkpoint humano del boceto M3, ANTES de encolar.
    Partes estructurales del codigo + juicio del planner (modelo; puede fallar sin bloquear) +
    estimaciones DETERMINISTAS de la historia real. Server-side y referido por plan_id -- el cliente
    nunca re-manda el objeto (procedencia)."""
    user = _user_of(authorization)
    q = body.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="question must be non-empty")
    plan = runs_mod.build_plan(q, [e.strip() for e in body.entities if e.strip()])
    plan_id = uuid.uuid4().hex
    db.create_plan(plan_id, user["user_id"], q, plan["entities"],
                   json.dumps(plan, ensure_ascii=False, default=str))
    return {"plan_id": plan_id, "plan": plan}


def _run_view(run):
    """Run row -> API shape, with the heartbeat DERIVED (the UI's 'no event for N min' detector —
    a run stuck 1800s in a deadlock must be distinguishable from one that is working). LOTE-01·A2:
    the threshold TRAVELS with the derivation (an alert without its threshold cannot be judged).
    LOTE-01·A4: usage_json (spend on EVERY exit path, failed/cancelled included) is served parsed
    as `token_usage`."""
    now = datetime.datetime.now(datetime.timezone.utc)
    hb = (now - run["last_event_at"]).total_seconds() if run.get("last_event_at") else None
    view = {k: (v.isoformat(timespec="seconds") if isinstance(v, datetime.datetime) else v)
            for k, v in run.items()
            if k not in ("bundle_json", "frozen_record_json", "usage_json", "epistemic_summary_json",
                         "plan_json")}
    view["heartbeat_age_s"] = round(hb, 1) if hb is not None else None
    view["heartbeat_stale"] = bool(hb is not None and hb > HEARTBEAT_STALE_S
                                   and run["state"] in ("queued", "running"))
    view["heartbeat_stale_after_s"] = HEARTBEAT_STALE_S
    view["token_usage"] = json.loads(run["usage_json"]) if run.get("usage_json") else None
    view["plan_declared"] = bool(run.get("plan_json"))   # ADR-0061; el plan completo va en el registro
    # LOTE-02·3: frozen-at-freeze summary for rich list rows; null = run without a frozen record yet
    view["epistemic_summary"] = (json.loads(run["epistemic_summary_json"])
                                 if run.get("epistemic_summary_json") else None)
    return view


@app.post("/runs")
def create_run(body: RunBody, authorization: str = Header(None)):
    """Queue a run (async — poll /runs/{id} or subscribe to /runs/{id}/stream). Per ADR-0049 the run's
    terminal state is ALWAYS post-audit; per ADR-0047 d.3 the panel runs on 100% of runs (measured,
    never capped)."""
    user = _user_of(authorization)
    q = body.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="question must be non-empty")
    # LOTE-01·A5: "bloquea, no degrada" es del servidor, no disciplina de la UI. Con el índice OFFLINE
    # no se encola (la corrida nacería degradada); mismo camino NO-SPEND del /status. El loop local
    # sparse-dev (siempre OFFLINE sin NEO4J_URI) se destraba con WITT_ALLOW_RUNS_OFFLINE=1.
    st = _store_status()
    if st["index_state"] == "OFFLINE" and os.environ.get("WITT_ALLOW_RUNS_OFFLINE") != "1":
        raise HTTPException(status_code=409, detail={
            "state": "index_offline",
            "note": "el índice semántico está OFFLINE — el diseño manda bloquear, no degradar. "
                    "Dev sparse: exporta WITT_ALLOW_RUNS_OFFLINE=1 (documentado en README).",
            "status_error": st.get("status_error")})
    plan_json = None
    if body.plan_id:
        prow = db.get_plan(body.plan_id)
        if prow is None:
            raise HTTPException(status_code=404, detail="plan_id no existe")
        if prow["run_id"]:
            # un plan se consume por UNA corrida: re-usarlo callado haria pasar un juicio viejo como
            # fresco (ADR-0061). El cliente declara plan nuevo o corre sin plan.
            raise HTTPException(status_code=409, detail={
                "state": "plan_already_used", "run_id": prow["run_id"],
                "note": "este plan ya respalda otra corrida; declara un plan nuevo"})
        plan_json = prow["plan_json"]
    run_id = runs_mod.new_run(user["user_id"], q, [e.strip() for e in body.entities if e.strip()],
                              plan_json=plan_json)
    if body.plan_id:
        db.mark_plan_used(body.plan_id, run_id)
    return _run_view(db.get_run(run_id))


@app.get("/runs")
def list_runs(mine: bool = False, authorization: str = Header(None)):
    """LOTE-01·A1: the LIST goes through the same _run_view as the detail — heartbeat fields included
    and identical datetime serialization (a stuck run must be distinguishable FROM THE LIST)."""
    user = _user_of(authorization)
    return {"runs": [_run_view(r) for r in db.list_runs(user_id=user["user_id"] if mine else None)]}


@app.get("/runs/{run_id}")
def get_run(run_id: str, authorization: str = Header(None)):
    _user_of(authorization)
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="no such run")
    return _run_view(run)


@app.get("/runs/{run_id}/record")
def get_frozen_record(run_id: str, authorization: str = Header(None)):
    """The frozen record the UI renders (URL / PDF / bitácora — one source, three readers, ADR-0046)."""
    _user_of(authorization)
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="no such run")
    if not run.get("frozen_record_json"):
        raise HTTPException(status_code=409, detail={"state": run["state"],
                                                     "note": "no frozen record yet (run not finished)"})
    return json.loads(run["frozen_record_json"])


@app.get("/runs/{run_id}/events")
def get_events(run_id: str, after: int = 0, authorization: str = Header(None)):
    """Replay (and polling) endpoint — reads THE same log the live stream reads (db.run_events)."""
    _user_of(authorization)
    if db.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="no such run")
    return {"events": db.events_after(run_id, after)}


@app.get("/runs/{run_id}/stream")
async def stream_events(run_id: str, after: int = 0, authorization: str = Header(None)):
    """Live SSE trace — the SAME rows as /events (one log, two readers, they cannot contradict).
    Emits `data: <event JSON>` lines; closes after the run reaches a terminal state and the log drains."""
    _user_of(authorization)
    if db.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="no such run")

    async def _gen():
        import asyncio
        last = after
        idle = 0.0
        while True:
            events = db.events_after(run_id, last)
            for ev in events:
                last = ev["seq"]
                idle = 0.0
                yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"
            run = db.get_run(run_id)
            if run["state"] in ("awaiting_closure", "closed", "failed", "cancelled") and not events:
                yield f"event: end\ndata: {json.dumps({'state': run['state']})}\n\n"
                return
            await asyncio.sleep(1.0)
            idle += 1.0
            if idle >= 15.0:   # SSE keep-alive comment so proxies do not cut the stream
                idle = 0.0
                yield ": heartbeat\n\n"

    from fastapi.responses import StreamingResponse
    return StreamingResponse(_gen(), media_type="text/event-stream")


class CancelBody(BaseModel):
    reason: str = ""


@app.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, body: CancelBody = None, authorization: str = Header(None)):
    """Cancellation is a first-class terminal state — a cancelled run must NEVER render as failed/dead
    (it would lie about the system). Queued runs cancel immediately; running ones at the next stage.
    LOTE-01·A3: the author (session user) and reason are REGISTERED — a cancellation without an author
    is a hole in the registry (ERP rule)."""
    user = _user_of(authorization)
    if db.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="no such run")
    reason = (body.reason if body else "") or ""
    accepted = db.request_cancel(run_id, by=user["user_id"], reason=reason)
    if not accepted:
        raise HTTPException(status_code=409, detail={"state": db.get_run(run_id)["state"],
                                                     "note": "only queued/running runs can be cancelled"})
    db.add_event(run_id, "run.cancel_requested", level="warning",
                 payload={"by": user["user_id"], "reason": reason})
    return _run_view(db.get_run(run_id))


@app.post("/runs/{run_id}/close")
def close_run(run_id: str, authorization: str = Header(None)):
    """Explicit closure (seed of the closure-as-precedent-requirement ADR): freezes the record."""
    user = _user_of(authorization)
    res = runs_mod.close_run(run_id, by=user["user_id"])
    if res is None:
        raise HTTPException(status_code=404, detail="no such run")
    if not res.get("closed"):
        raise HTTPException(status_code=409, detail=res)
    return res


# --- taxonomy (LOTE-01·A6): the Rack's filters come from ONE door — the UI refuses to copy the files
# (drift); this serves the three living sources verbatim with declared provenance (path + mtime). ------

_TAXONOMY_CACHE = {"at": 0.0, "data": None}
_TAXONOMY_FILES = {"niches": ROOT / "rag_index" / "niches.json",
                   "databases": ROOT / "rag_index" / "databases.json",
                   "crosswalk": ROOT / "rag_index" / "niche_database_crosswalk.json"}


@app.get("/taxonomia")
def taxonomia(authorization: str = Header(None)):
    """Read-only taxonomy: niches (13, frozen since ADR-0018 — human-gated mutable), databases, and the
    niche-database crosswalk, each with its provenance (repo path + mtime). TTL-cached."""
    _user_of(authorization)
    now = time.time()
    if _TAXONOMY_CACHE["data"] and now - _TAXONOMY_CACHE["at"] < ARTIFACTS_TTL_S:
        return _TAXONOMY_CACHE["data"]
    data, provenance = {}, {}
    for key, path in _TAXONOMY_FILES.items():
        data[key] = json.loads(path.read_text(encoding="utf-8"))
        provenance[key] = {"path": str(path.relative_to(ROOT)).replace("\\", "/"),
                           "mtime": datetime.datetime.fromtimestamp(
                               path.stat().st_mtime, datetime.timezone.utc).isoformat(timespec="seconds")}
    out = {**data, "provenance": provenance, "refreshed_at": _now_iso()}
    _TAXONOMY_CACHE.update(at=now, data=out)
    return out


# --- usage aggregation (LOTE-02·2, M8): the sum lives on the SERVER ----------------------------------

@app.get("/usage")
def usage(from_: str = Query(None, alias="from"), to: str = None,
          authorization: str = Header(None)):
    """Aggregated consumption per person / period / model over usage_json of ALL runs (no cap — the
    list serves 50; a client-side total would have no full denominator). Token counts are MEASURED [M]
    from API responses; dollars stay a labeled PROJECTION [E] (cost_class). `from_`/`to` = ISO dates
    (inclusive; date-only accepted). Rack /query embeds are NOT per-run — served apart with their
    attribution caveat, never silently summed into totals."""
    _user_of(authorization)

    def _parse(dstr, end=False):
        if not dstr or not isinstance(dstr, str):   # direct (non-HTTP) calls pass the Query default
            return None
        d = datetime.datetime.fromisoformat(dstr)
        if d.tzinfo is None:
            d = d.replace(tzinfo=datetime.timezone.utc)
        if end and len(dstr) <= 10:   # date-only 'to' -> end of that day
            d = d + datetime.timedelta(days=1) - datetime.timedelta(seconds=1)
        return d

    try:
        frm, to_dt = _parse(from_), _parse(to, end=True)
    except ValueError:
        raise HTTPException(status_code=400, detail="from/to must be ISO dates (YYYY-MM-DD)")
    rows = db.runs_usage(frm, to_dt)
    totals = {"input_tokens": 0, "output_tokens": 0, "embedding_tokens": 0, "estimated_cost_usd": 0.0}
    by_user, by_model, most = {}, {}, None
    n_with = 0
    for r in rows:
        u = json.loads(r["usage_json"]) if r.get("usage_json") else None
        if not u:
            continue
        n_with += 1
        cost = float(u.get("estimated_cost_usd") or 0.0)
        totals["input_tokens"] += u.get("input_tokens", 0)
        totals["output_tokens"] += u.get("output_tokens", 0)
        totals["embedding_tokens"] += (u.get("embedding") or {}).get("total_tokens", 0)
        totals["estimated_cost_usd"] += cost
        bu = by_user.setdefault(r["user_id"], {"n_runs": 0, "input_tokens": 0, "output_tokens": 0,
                                               "estimated_cost_usd": 0.0})
        bu["n_runs"] += 1
        bu["input_tokens"] += u.get("input_tokens", 0)
        bu["output_tokens"] += u.get("output_tokens", 0)
        bu["estimated_cost_usd"] = round(bu["estimated_cost_usd"] + cost, 4)
        for model, m in (u.get("by_model") or {}).items():
            bm = by_model.setdefault(model, {"in": 0, "out": 0, "estimated_cost_usd": 0.0})
            bm["in"] += m.get("in", 0)
            bm["out"] += m.get("out", 0)
            pi, po = runs_mod.PRICES_PER_MTOK_USD.get(model, (0.0, 0.0))
            bm["estimated_cost_usd"] = round(bm["estimated_cost_usd"]
                                             + (m.get("in", 0) * pi + m.get("out", 0) * po) / 1e6, 4)
        if most is None or cost > most["estimated_cost_usd"]:
            most = {"run_id": r["run_id"], "user_id": r["user_id"], "state": r["state"],
                    "question": (r["question"] or "")[:120],
                    "created_at": r["created_at"].isoformat(timespec="seconds") if r["created_at"] else None,
                    "estimated_cost_usd": round(cost, 4)}
    totals["estimated_cost_usd"] = round(totals["estimated_cost_usd"], 4)
    try:
        sys.path.insert(0, str(ROOT / "rag_index" / "graphrag"))
        import embeddings as _emb
        snap = _emb.usage_snapshot()
        rack = {"total_tokens_since_boot": snap["total_tokens"], "calls": snap["calls"],
                "attribution": "proceso completo desde el arranque del servicio — INCLUYE los embeds de "
                               "corridas ya contados por corrida; no sumar con totals (doble conteo)"}
    except Exception:
        rack = {"total_tokens_since_boot": None, "calls": None, "attribution": "no disponible"}
    return {"from": from_, "to": to, "n_runs": len(rows), "n_runs_with_usage": n_with,
            "totals": totals, "by_user": by_user, "by_model": by_model, "most_expensive": most,
            "rack_embeddings": rack,
            "cost_class": f"PROJECTION (calculated from measured tokens x per-Mtok prices as of "
                          f"{runs_mod.PRICES_AS_OF}; the token counts are measurements, the dollars are not)"}


# --- config history (LOTE-02·5, M6/SISTEMA): the catalog has history ---------------------------------

@app.get("/config-history")
def config_history(authorization: str = Header(None)):
    """The comparability-affecting config changes, verbatim from rag_index/config_history.json
    (append-only, ADR-sourced dates — ADR-0055) with declared provenance. Also DECLARES where the other
    two histories live today (user account history, store_version history) instead of leaving silence."""
    _user_of(authorization)
    hist = json.loads(_CONFIG_HISTORY.read_text(encoding="utf-8"))
    return {"entries": hist.get("entries", []),
            "provenance": {"path": "rag_index/config_history.json",
                           "mtime": datetime.datetime.fromtimestamp(
                               _CONFIG_HISTORY.stat().st_mtime,
                               datetime.timezone.utc).isoformat(timespec="seconds")},
            "user_history": {"source": "tabla users: created_at + disabled (ESTADO, no bitácora de "
                                       "eventos); altas/resets vía seed_users.py local (ADR-0048)",
                             "note": "un event-log de altas/bajas/resets es bloque futuro"},
            "store_version_history": {"source": "git — commits a analysis/outputs/"
                                                "verified_identifiers.json + su serie de ADRs "
                                                "(0029/0035/0041/0042…), cada crecimiento human-gated",
                                      "note": "puerta programática del historial del store: futura"},
            "refreshed_at": _now_iso()}


# --- precedent layer (block 6, ADR-0053): the OTHER index — separate admissibility, equal value ------

@app.get("/precedent/search")
def precedent_search(q: str, k: int = 5, authorization: str = Header(None)):
    """Relevance search over CLOSED runs (explicit closure = the precedent requirement). Every item is
    structurally marked admissible_as_evidence: false — precedent informs humans and planning; it never
    enters the gated evidence object (the anti-fabrication gate is provenance-blind by design, so this
    rule lives at the product layer). Citation series stay disjoint: numbers=evidence, letters=precedent."""
    _user_of(authorization)
    if not q.strip():
        raise HTTPException(status_code=400, detail="q must be non-empty")
    return precedent_mod.search(q.strip(), k)


# --- aliases matching the UI's proposed surface (UI-DATA-CONTRACTS.md §2) — same handlers ------------
app.get("/rack/search")(query)
app.get("/rack/resolve")(resolve)
app.get("/rack/status")(status)

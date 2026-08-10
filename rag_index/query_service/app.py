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
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
sys.path.insert(0, str(ROOT / "rag_index" / "mcp_server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import server  # noqa: E402  (side effects: deploy.env + EMBED_MODEL pin + backend import — traps 2/3)
import db  # noqa: E402
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
    yield


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
def query(q: str, k: int = 5, authorization: str = Header(None)):
    """Semantic GraphRAG query. Returns server._query's envelope VERBATIM — {degraded, n_hits, hits,
    last_error, index_version, store_version}. Degraded results are 200 (a valid, banded answer the UI
    must paint); only query_unavailable is 503."""
    _user_of(authorization)
    res = server._query(q, k)
    if "error" in res:
        raise HTTPException(status_code=503, detail=res)
    return res


@app.get("/resolve")
def resolve(key: str, authorization: str = Header(None)):
    """Deterministic verified-identifier resolve — full VerifiedRecord (block 1.4). NOT_FOUND is a
    positive result (200, resolved: false), not an HTTP error."""
    _user_of(authorization)
    return server._resolve(key)


@app.get("/raw")
def raw(key: str, filename: str = None, authorization: str = Header(None)):
    """Drill to the RAW layer (fetch_raw): presigned MinIO URL or canonical source_url + sha256."""
    _user_of(authorization)
    res = server._fetch_raw(key, filename)
    if not res.get("found"):
        raise HTTPException(status_code=404, detail=res)
    return res


# --- StoreStatus: the 9 UI fields, aggregated from the 3 disconnected sources, NO-SPEND -------------

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


def _store_status():
    """StoreStatus (UI-DATA-CONTRACTS.md M2/M8): store_version, record_count, sha, doc_count,
    entity_count, embed_model, embed_dim, index_state, refreshed_at. TTL-cached: a UI header polling
    every N seconds costs at most one free Cypher round per TTL and ZERO OpenAI, always — a status
    indicator that costs money ends up turned off, and that is the one that must never turn off."""
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


# --- aliases matching the UI's proposed surface (UI-DATA-CONTRACTS.md §2) — same handlers ------------
app.get("/rack/search")(query)
app.get("/rack/resolve")(resolve)
app.get("/rack/status")(status)

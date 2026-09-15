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
import calibration as calibration_mod  # noqa: E402
import config_ledger  # noqa: E402  (ADR-0081 (I)/(E): bitácora de configuración; boot() en el lifespan)
import consulta_sistema as consulta_mod  # noqa: E402
import db  # noqa: E402
import question_agent  # noqa: E402
import rack_browse as rack_browse_mod  # noqa: E402
import record_pdf as record_pdf_mod  # noqa: E402
import precedent as precedent_mod  # noqa: E402
import runs as runs_mod  # noqa: E402
from lib import models  # noqa: E402  (ADR-0081 (A): la tabla de modelos — resolución EN LA LLAMADA)
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
    # ADR-0081 (I): el diff de configuración al ARRANQUE — tras create_all (la tabla config_history existe) y
    # ANTES de start_workers (ninguna corrida observa sin baseline). config_ledger.boot() JAMÁS lanza: un fallo
    # del ledger queda en ledger_state, nunca impide servir (§6 no-hang).
    config_ledger_boot()
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
                              "(GET /rack/node/{id}, ADR-0071), never this door",
                       "door": "/rack/node/{id}"}


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


# --- entities: the verified store ENUMERATED (2026-08-29) --------------------------------------------
# Until now the store was reachable one key at a time (/resolve); the webapp's advanced-search picker
# needs the measured roster (Emmanuel: pick entities from a select, not from memory). NO-SPEND by
# construction: same in-process snapshot the resolve door serves — no graph, no embeddings, no network.

_ENTITIES_CACHE = {"at": 0.0, "data": None}


@app.get("/entities")
def entities(authorization: str = Header(None)):
    """The verified-identifier store, enumerated: the resolvable roster (symbol + ensdarg + tier +
    tier_weight + verified_on) for pickers, and the absence markers declared APART (ensdarg=null is a
    positive 'looked, does not resolve' — offering one to anchor evidence would be a lie; hiding it,
    another). Same snapshot as /resolve (module singleton; a store change requires redeploy), with
    provenance and refreshed_at declared. TTL-cached like the other read doors."""
    _user_of(authorization)
    now = time.time()
    if _ENTITIES_CACHE["data"] and now - _ENTITIES_CACHE["at"] < ARTIFACTS_TTL_S:
        return _ENTITIES_CACHE["data"]
    out = {**server._list_entities(),
           "provenance": "analysis/outputs/verified_identifiers.json — snapshot del proceso; la misma "
                         "fuente que sirve /resolve",
           "refreshed_at": _now_iso()}
    _ENTITIES_CACHE.update(at=now, data=out)
    return out


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
        # 2026-09-05: la hora sale del REPORTE, no del mtime. El mtime de un artefacto
        # commiteado es la hora del CHECKOUT del contenedor — presentarlo como hora de
        # escaneo sería una fecha de deploy disfrazada de medición. Los artefactos viejos
        # (sin scanned_at) caen al mtime y ese fallback se DECLARA, no se disimula.
        sellada = rep.get("scanned_at")
        fila = {"scanned": True,
                "scanned_at": sellada or datetime.datetime.fromtimestamp(
                    _INTEGRITY_ARTIFACT.stat().st_mtime,
                    datetime.timezone.utc).isoformat(timespec="seconds"),
                "scanned_at_source": "report" if sellada else "file-mtime",
                "n_records": rep.get("n_records"), "store_version": rep.get("store_version"),
                "n_findings": len(findings),
                "n_critical_high": sum(1 for f in findings
                                       if f.get("severity") in ("critical", "high"))}
        if not sellada:
            fila["note"] = ("artefacto sin scanned_at: la fecha sale del mtime del archivo — en un "
                            "contenedor eso es la hora del checkout, no la del escaneo. Re-córrelo "
                            "para sellarlo.")
        return fila
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
    # 2026-09-04: el borrador del agente que originó esta pregunta. Opcional — preguntar nunca
    # se bloquea por el agente. Sella el lazo de calibración: borrador -> corrida -> eje pregunta.
    from_question_id: str | None = None
    # ADR-0079: la corrida PADRE de este turno (una investigación T-<run_no raíz>). Opcional: sin
    # padre la corrida nace raíz (thread_id = run_id, turn_no 1). El cliente sólo REFIERE al padre;
    # thread_id / turn_no / turn_kind / thread_context los deriva el servidor (ADR-0056).
    parent_run_id: str | None = None


class PlanBody(BaseModel):
    question: str
    entities: list[str] = []
    # ADR-0079: planear el turno siguiente de una investigación — el planner recibe el thread_context
    # del padre (snapshot armado en el servidor), jamás un objeto mandado por el cliente.
    parent_run_id: str | None = None


def _traduce_thread_error(fn, *args, **kwargs):
    """ADR-0079: la validación del padre vive UNA vez, en runs.py (new_run / plan_thread_context, ANTES
    de insertar): inexistente -> ParentNotFound (404 parent_not_found); no terminal (queued/running) ->
    ParentNotTerminal (409 parent_not_terminal, con parent_state) — un turno sólo se apila sobre una
    corrida que ya terminó (db.RATABLE_STATES). failed/cancelled SÍ son padres válidos: el hijo declara
    que el padre no tiene registro ('parent-without-frozen-record'), no se le niega la investigación.
    runs.py no importa fastapi: aquí se traduce su ThreadError {status, detail} a HTTPException —
    mismo patrón de detalle tipado que plan_already_used / question_already_used."""
    try:
        return fn(*args, **kwargs)
    except runs_mod.ThreadError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)


@app.post("/runs/plan")
def create_plan(body: PlanBody, authorization: str = Header(None)):
    """El plan declarado (tapon 3, ADR-0061): el checkpoint humano del boceto M3, ANTES de encolar.
    Partes estructurales del codigo + juicio del planner (modelo; puede fallar sin bloquear) +
    estimaciones DETERMINISTAS de la historia real. Server-side y referido por plan_id -- el cliente
    nunca re-manda el objeto (procedencia).

    ADR-0079: con parent_run_id (validado 404/409 igual que al encolar) el planner recibe el
    thread_context del padre — el MISMO snapshot que verá el sintetizador, armado por el SERVIDOR
    (runs.plan_thread_context -> sobre {snapshot, skipped_reason}) desde el registro congelado +
    comentarios del padre. El sobre entero va a build_plan (que declara en el plan si el planner lo
    vio: plan.thread_context_declared / thread_context_skipped_reason); la respuesta repite el padre
    y la razón de omisión (identidad del padre inválida, kill-switch) para que el cliente no infiera."""
    user = _user_of(authorization)
    q = body.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="question must be non-empty")
    sobre = None
    if body.parent_run_id:
        sobre = _traduce_thread_error(runs_mod.plan_thread_context, body.parent_run_id)
    plan = runs_mod.build_plan(q, [e.strip() for e in body.entities if e.strip()], thread_context=sobre)
    plan_id = uuid.uuid4().hex
    db.create_plan(plan_id, user["user_id"], q, plan["entities"],
                   json.dumps(plan, ensure_ascii=False, default=str))
    return {"plan_id": plan_id, "plan": plan,
            # ADR-0079: qué padre se declaró y si su contexto llegó al planner (o por qué no)
            "parent_run_id": body.parent_run_id,
            "thread_context_passed": (sobre or {}).get("snapshot") is not None,
            "thread_context_skipped_reason": ((sobre or {}).get("skipped_reason")
                                             if body.parent_run_id else "root-turn")}


def config_ledger_boot():
    """ADR-0081 (I): `app.config_ledger_boot()` — llamable DIRECTA (los smokes HTTP construyen
    TestClient(app) SIN lifespan y la llaman ellos); el lifespan sólo la cablea. Pasa los EXTRA_FIELDS que
    models.py no deriva (contract.render_contract_version, competence.gate, search.harness, revision.cycle)
    con la MISMA función que usa /config-history.current (config_ledger.default_extra): una sola verdad."""
    return config_ledger.boot(extra=config_ledger.default_extra())


def config_ledger_observe(snapshot=None):
    """ADR-0081 (E): el diff EN CORRIDA (runs.execute_run lo llama al inicio con el snapshot de
    stage.models). Nunca lanza. Alias de config_ledger.observe para quien llegue por app."""
    return config_ledger.observe(snapshot)


def _run_view(run):
    """Run row -> API shape, with the heartbeat DERIVED (the UI's 'no event for N min' detector —
    a run stuck 1800s in a deadlock must be distinguishable from one that is working). LOTE-01·A2:
    the threshold TRAVELS with the derivation (an alert without its threshold cannot be judged).
    LOTE-01·A4: usage_json (spend on EVERY exit path, failed/cancelled included) is served parsed
    as `token_usage`.
    ADR-0078: claimed_by/claimed_at (qué worker reclamó la corrida y cuándo) viajan TAL CUAL en la
    vista — la lista de exclusión de abajo no los tapa; null = nadie declaró (llamador sin worker_id),
    distinto de un nombre de hilo. Una corrida segada por el reaper llega state='failed' con
    error 'worker-lost: …' y su evento run.state {reason:'worker-lost'} en la bitácora.
    ADR-0079: las columnas de investigación (parent_run_id, thread_id, turn_no, turn_kind, origin,
    root_question_id) viajan TAL CUAL desde la fila — NULL = corrida anterior al contrato ('sin
    investigación' / origin desconocido), ausencia declarada que jamás se rellena aquí (un setdefault
    taparía justo la asimetría lista/detalle que rompió en ADR-0055/0076: si list_runs olvida una
    columna, la lista debe VERSE distinta del detalle, no igualarse a null). thread_context_json es
    un blob (el INSUMO que vio el modelo) y va a la lista de exclusión: vive en el registro congelado
    como frozen.thread_context, no en el renglón.
    ADR-0081 (F): `root_run_no` NACE en la BD (db._list_select / db.get_run: outerjoin a la raíz del hilo,
    columna root.run_no AS root_run_no) y fluye por este passthrough SIN código aquí — la vista no lo deriva
    ni lo rellena: raíz → su run_no; hijo de raíz virtual → el run_no del padre pre-ADR; corrida pre-ADR →
    null declarado. Lista, detalle y POST /runs lo sirven por construcción (misma consulta, misma llave)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    hb = (now - run["last_event_at"]).total_seconds() if run.get("last_event_at") else None
    view = {k: (v.isoformat(timespec="seconds") if isinstance(v, datetime.datetime) else v)
            for k, v in run.items()
            if k not in ("bundle_json", "frozen_record_json", "usage_json", "epistemic_summary_json",
                         "plan_json", "thread_context_json")}
    view["heartbeat_age_s"] = round(hb, 1) if hb is not None else None
    view["heartbeat_stale"] = bool(hb is not None and hb > HEARTBEAT_STALE_S
                                   and run["state"] in ("queued", "running"))
    view["heartbeat_stale_after_s"] = HEARTBEAT_STALE_S
    # ADR-0078 corrector: el POR QUÉ de un failed, tipado — 'worker-lost' (segada por el reaper) |
    # 'pipeline' (excepción del worker) | null (no falló). La webapp ya no tiene que hacer startsWith
    # sobre el string `error`.
    err = run.get("error") or ""
    if run.get("state") == "failed":
        view["failure_reason"] = "worker-lost" if err.startswith("worker-lost") else "pipeline"
    else:
        view["failure_reason"] = None
    view["token_usage"] = json.loads(run["usage_json"]) if run.get("usage_json") else None
    view["plan_declared"] = bool(run.get("plan_json"))   # ADR-0061; el plan completo va en el registro
    # ADR-0076: run_no (el NÚMERO de corrida) viaja tal cual — es columna asignada al nacer, no derivación
    # 2026-08-29 (columna nicho/veredicto de la lista): los CÓDIGOS de nicho del juicio del plan
    # viajan con el renglón, derivados del plan_json YA guardado (procedencia: el planner, ADR-0061);
    # None = corrida sin plan o juicio sin nichos — ausencia declarada, jamás se rellena. El veredicto
    # ya viaja en epistemic_summary (LOTE-02·3), congelado al freeze.
    view["plan_niches"] = None
    if run.get("plan_json"):
        try:
            juicio = (json.loads(run["plan_json"]).get("judgment") or {})
            codigos = [n.get("code") for n in (juicio.get("niches") or []) if n.get("code")]
            view["plan_niches"] = codigos or None
        except Exception:
            view["plan_niches"] = None
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
    # el borrador que respalda la pregunta: se valida ANTES de encolar, y un borrador ya
    # consumido es 409 igual que un plan reusado — dos corridas colgando del mismo borrador
    # romperían la calibración (contaría dos veces una sola redacción)
    if body.from_question_id:
        qrow = db.get_note_question(body.from_question_id)
        if qrow is None:
            raise HTTPException(status_code=404, detail="from_question_id no existe")
        if qrow["run_id"]:
            raise HTTPException(status_code=409, detail={
                "state": "question_already_used", "run_id": qrow["run_id"],
                "note": "este borrador ya respalda otra corrida; pide uno nuevo o corre sin él"})
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
    # ADR-0079: el padre lo valida runs.new_run ANTES de insertar (ThreadError -> 404 parent_not_found /
    # 409 parent_not_terminal, traducidos aquí). Sólo viaja la REFERENCIA: thread_id, turn_no, turn_kind,
    # origin, root_question_id y el snapshot thread_context los deriva el servidor (ADR-0056 — jamás del
    # cliente). from_question_id viaja también para que la raíz selle root_question_id = su borrador.
    run_id = _traduce_thread_error(runs_mod.new_run, user["user_id"], q,
                                   [e.strip() for e in body.entities if e.strip()],
                                   plan_json=plan_json, parent_run_id=body.parent_run_id,
                                   from_question_id=body.from_question_id)
    if body.from_question_id:
        db.mark_question_used(body.from_question_id, run_id)
    if body.plan_id:
        db.mark_plan_used(body.plan_id, run_id)
    return _con_comentarios([_run_view(db.get_run(run_id))])[0]


def _con_comentarios(views):
    """ADR-0077: `n_comments` viaja en TODA vista de corrida (lista, detalle y la recién creada) —
    misma-vista (LOTE-01·A1) — con UNA consulta agrupada, no una por renglón. Es un conteo: medición."""
    conteos = db.count_run_comments([v["run_id"] for v in views])
    for v in views:
        v["n_comments"] = conteos.get(v["run_id"], 0)
    return views


RUNS_LIST_CAP = 50   # el tope histórico de la lista general (M8 suma aparte en /usage); no aplica con thread=


@app.get("/runs")
def list_runs(mine: bool = False, thread: str = None, limit: int = None, after: int = None,
              authorization: str = Header(None)):
    """LOTE-01·A1: the LIST goes through the same _run_view as the detail — heartbeat fields included
    and identical datetime serialization (a stuck run must be distinguishable FROM THE LIST).

    ADR-0079: `thread=<thread_id>` lista los TURNOS de una investigación en orden de turn_no ASC,
    paginados con `limit` (sin tope: una investigación se lee entera) y `after` (cursor = turn_no
    exclusivo: devuelve turnos con turn_no > after). Sin `thread` la lista general conserva su tope
    (RUNS_LIST_CAP, declarado en la respuesta) y `after` no aplica (400). `next_after` es el turn_no
    del último renglón servido cuando hay más; `has_more` se mide pidiendo limit+1, nunca se estima."""
    user = _user_of(authorization)
    user_id = user["user_id"] if mine else None
    # corrector ADR-0079: la validación del signo va ANTES de los dos ramales — `limit=-1` llegaba a
    # `LIMIT -1` en la lista general (SQLite: sin tope, saltándose el 50; Postgres: error → 500)
    if limit is not None and limit < 1:
        raise HTTPException(status_code=400, detail="limit debe ser >= 1")
    if not thread:
        if after is not None:
            raise HTTPException(status_code=400, detail="after: cursor de turn_no — sólo aplica con thread=")
        tope = RUNS_LIST_CAP if limit is None else min(limit, RUNS_LIST_CAP)
        vistas = [_run_view(r) for r in db.list_runs(user_id=user_id, limit=tope)]
        return {"runs": _con_comentarios(vistas), "limit": tope, "limit_cap": RUNS_LIST_CAP}
    filas = db.list_runs(user_id=user_id, limit=(limit + 1) if limit else None,
                         thread_id=thread, after=after)
    has_more = bool(limit and len(filas) > limit)
    filas = filas[:limit] if limit else filas
    vistas = _con_comentarios([_run_view(r) for r in filas])
    return {"runs": vistas, "thread_id": thread, "limit": limit, "after": after,
            "n": len(vistas), "has_more": has_more,
            "next_after": (vistas[-1].get("turn_no") if has_more and vistas else None),
            "order": "turn_no ASC (cursor `after` = turn_no exclusivo)"}


@app.get("/runs/{run_id}")
def get_run(run_id: str, authorization: str = Header(None)):
    _user_of(authorization)
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="no such run")
    return _con_comentarios([_run_view(run)])[0]


# --- investigaciones (ADR-0079): la cadena de turnos sobre una pregunta, leída como UNA unidad --------
# Un turno = una corrida con parent_run_id. La investigación se nombra T-<run_no raíz> ante el humano;
# en código es thread_id (= run_id de la raíz). Todo lo de abajo son CONTEOS y sumas etiquetadas sobre
# valores YA congelados — ninguna prosa nueva, ninguna re-medición, nada del modelo.

# ADR-0079: turnos planos consecutivos. Corrector: lectura TOLERANTE (runs._env_int_tolerante, ADR-0078) —
# `int(os.environ.get(...))` al importar tumbaba el servicio con WITT_PIVOT_TURNS='' o 'abc' (el caso exacto
# de WITT_REAP_STALE_S en Dokploy); env vacía / no numérica / <= 0 -> default 3 con la FUENTE declarada.
PIVOT_TURNS_DEFAULT = 3
PIVOT_TURNS, PIVOT_TURNS_SOURCE = runs_mod._env_int_tolerante("WITT_PIVOT_TURNS", PIVOT_TURNS_DEFAULT)
PIVOT_RULE = "WITT_PIVOT_TURNS turnos consecutivos cuyo conjunto de gap_flags no se redujo"
ORIGIN_UNKNOWN = "unknown-pre-adr-0079"   # ADR-0079 (A): origin NULL = corrida anterior al contrato


def _gap_flags_de(frozen):
    """Los gap_flags del registro congelado con lectura TOLERANTE (ADR-0074): lista -> tal cual; string
    JSON de lista -> levantado por runs._lista_serializada; cualquier otra cosa -> [] y `unreadable`
    True (se declara, no se corrige). Sólo strings no vacíos cuentan."""
    crudo = ((frozen or {}).get("answer") or {}).get("gap_flags")
    if isinstance(crudo, list):
        return [g for g in crudo if isinstance(g, str) and g.strip()], False
    levantado = runs_mod._lista_serializada(crudo) if isinstance(crudo, str) else None
    if levantado is not None:
        return [g for g in levantado if isinstance(g, str) and g.strip()], False
    return [], crudo is not None


def _turno_de(run):
    """Una fila completa de corrida -> el renglón del turno + sus insumos (conjunto normalizado de
    gap_flags, costo) para los agregados. Cada llave ausente queda None (tres estados)."""
    frozen = None
    if run.get("frozen_record_json"):
        try:
            frozen = json.loads(run["frozen_record_json"])
        except Exception:
            frozen = None
    resumen = json.loads(run["epistemic_summary_json"]) if run.get("epistemic_summary_json") else None
    uso = json.loads(run["usage_json"]) if run.get("usage_json") else None
    flags, ilegible = _gap_flags_de(frozen)
    turno = {
        "run_id": run["run_id"], "run_no": run.get("run_no"),
        "turn_no": run.get("turn_no"), "turn_kind": run.get("turn_kind"),
        "parent_run_id": run.get("parent_run_id"),
        "state": run["state"],
        "verdict": (resumen or {}).get("verdict"),
        "decision_state": ((frozen or {}).get("decision_state") or {}).get("state"),
        "origin": run.get("origin"),
        "created_at": run["created_at"].isoformat(timespec="seconds") if run.get("created_at") else None,
        "user_id": run["user_id"], "closed_by": run.get("closed_by"),
        "has_frozen_record": frozen is not None,
        "n_gap_flags": len(flags) if frozen is not None else None,
        "gap_flags_unreadable": ilegible,
        # [PROYECCIÓN] congelada al freeze (ADR-0051); None = sin usage (turno sin terminar o pre-llave)
        "estimated_cost_usd": (uso or {}).get("estimated_cost_usd") if uso else None,
        "cost_projection_complete": (uso or {}).get("cost_projection_complete") if uso else None,
    }
    return turno, flags, uso


def _union_gap_flags(turnos_flags):
    """gap_flags_union: igualdad normalizada (lower/strip), conteo POR TURNO (un turno que repite el
    mismo gap cuenta una vez), `text` = la redacción de la PRIMERA aparición (jamás prosa nueva),
    `last_turn` = el último turn_no donde apareció. Orden: primera aparición, luego texto."""
    union = {}
    for turn_no, flags in turnos_flags:
        vistos = set()
        for g in flags:
            k = g.strip().lower()
            if k in vistos:
                continue
            vistos.add(k)
            fila = union.setdefault(k, {"text": g.strip(), "count": 0, "first_turn": turn_no,
                                        "last_turn": turn_no})
            fila["count"] += 1
            fila["last_turn"] = turn_no
    return sorted(union.values(), key=lambda f: ((f["first_turn"] or 0), f["text"]))


def _pivot(turnos_flags):
    """pivot_suggested (ADR-0079): True cuando los ÚLTIMOS PIVOT_TURNS turnos con registro congelado
    forman una racha plana — entre cada par consecutivo el conjunto normalizado de gap_flags NO se
    redujo ('se redujo' = subconjunto PROPIO del anterior: todo gap ya estaba y al menos uno cerró),
    y el último conjunto no está vacío (sin gaps no hay nada de qué pivotear). Con menos turnos que
    el umbral: False y la razón declarada. Es una sugerencia calculada, no un juicio."""
    con_registro = [(t, {g.strip().lower() for g in flags}) for t, flags in turnos_flags]
    ventana = con_registro[-PIVOT_TURNS:] if PIVOT_TURNS > 0 else []
    base = {"value": False, "rule": PIVOT_RULE, "threshold": PIVOT_TURNS,
            "threshold_source": PIVOT_TURNS_SOURCE,   # corrector ADR-0079: env|default, como REAP_STALE_S_SOURCE
            "turns_considered": [t for t, _ in ventana]}
    if len(ventana) < PIVOT_TURNS or PIVOT_TURNS < 1:
        return {**base, "reason": f"insufficient-turns: {len(ventana)} con registro < {PIVOT_TURNS}"}
    if not ventana[-1][1]:
        return {**base, "reason": "last-turn-without-gap-flags"}
    plano = all(not (ventana[i][1] < ventana[i - 1][1]) for i in range(1, len(ventana)))
    return {**base, "value": plano,
            "reason": None if plano else "gap_flags-reduced-within-window"}


@app.get("/threads")
def list_threads(mine: bool = False, limit: int = None, after: int = None,
                 authorization: str = Header(None)):
    """ADR-0081 (G): el ÍNDICE de investigaciones — una fila por hilo (thread_id) con conteos MEDIDOS en
    la BD (db.threads_index: UNA consulta GROUP BY + una segunda ligera para autores/orígenes/estados/último
    turno; jamás abre blobs). Declarada ANTES de /threads/{thread_id}. La webapp deja de agrupar 50 corridas
    en el cliente: aquí viaja el denominador (n_threads_total), la paginación (cursor `after` = root_run_no
    EXCLUSIVO, `has_more` medido con limit+1) y `n_runs_without_thread` (corridas pre-ADR-0079 sin hilo,
    contadas aparte — no son investigaciones y no se les inventa una).
    `label`/`root_run_no`/`n_turns` son LOS MISMOS que GET /threads/{id} (dos puertas, una verdad: la raíz
    virtual pre-ADR se cuenta +1 como allá, `root_counted false` dice CÓMO entró al GROUP BY).
    El SOBRE lo arma db.threads_index (THREADS_INDEX_ENVELOPE_FIELDS: threads, n, limit, limit_cap, after,
    has_more, next_after, order, cursor_rule, mine, mine_rule, n_turns_rule, n_threads_total,
    n_runs_without_thread, n_runs_without_thread_rule, costs) y esta puerta lo sirve TAL CUAL — una sola
    definición de las reglas y los literales (lección ADR-0055/0076: dos redacciones divergen).
    Sin costos por hilo (abrirían usage_json por turno): `costs` lo declara y remite al detalle.
    `limit < 1` → 400; `after` no entero → 422 (tipado de FastAPI); sin token → 401."""
    user = _user_of(authorization)
    if limit is not None and limit < 1:
        raise HTTPException(status_code=400, detail="limit debe ser >= 1")
    tope = RUNS_LIST_CAP if limit is None else min(limit, RUNS_LIST_CAP)
    try:
        return db.threads_index(user_id=user["user_id"] if mine else None, limit=tope, after=after)
    except ValueError as e:   # el cursor/tope que la BD rechaza es un 400 tipado, no un 500
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/threads/{thread_id}")
def get_thread(thread_id: str, authorization: str = Header(None)):
    """ADR-0079 (H): la investigación T-<run_no raíz> como UNA unidad — sus turnos en orden con
    veredicto/decision_state/origin/costo por turno, más agregados DETERMINISTAS: gap_flags_union
    (conteos con igualdad normalizada), total_cost_usd [PROYECCIÓN] con `complete` (False si algún
    turno no tiene usage o se congeló incompleto — la suma de proyecciones parciales se declara, no
    se disimula), pivot_suggested (regla WITT_PIVOT_TURNS), orígenes y autores. 404 si no existe.

    Raíz virtual (ADR-0079 B): un padre anterior al contrato conserva thread_id NULL (nada se
    backfillea); sus hijos llevan thread_id = su run_id. Aquí ese padre se LEE como raíz virtual
    (`root_pre_adr_0079: true`, turn_no/turn_kind null = ausencia declarada) — derivación al servir,
    no escritura."""
    _user_of(authorization)
    filas = db.thread_turns(thread_id)
    completas = [db.get_run(f["run_id"]) for f in filas]
    completas = [c for c in completas if c is not None]
    raiz_virtual = None
    if not any(c["run_id"] == thread_id for c in completas):
        raiz_virtual = db.get_run(thread_id)
        if raiz_virtual is not None and raiz_virtual.get("thread_id") not in (None, thread_id):
            raiz_virtual = None   # una corrida de OTRA investigación no es raíz de ésta
        if raiz_virtual is not None:
            completas.insert(0, raiz_virtual)
    if not completas:
        raise HTTPException(status_code=404, detail={"state": "thread_not_found", "thread_id": thread_id})

    turnos, turnos_flags = [], []
    total, n_sin_uso, n_incompleto, n_desconocido = 0.0, 0, 0, 0
    origenes, autores = {}, set()
    for run in completas:
        turno, flags, uso = _turno_de(run)
        if raiz_virtual is not None and run["run_id"] == raiz_virtual["run_id"]:
            turno["root_pre_adr_0079"] = True
        turnos.append(turno)
        autores.add(run["user_id"])
        clave = run.get("origin") or ORIGIN_UNKNOWN
        origenes[clave] = origenes.get(clave, 0) + 1
        if turno["has_frozen_record"]:
            turnos_flags.append((turno["turn_no"], flags))
        if not uso:
            n_sin_uso += 1
            continue
        total += float(uso.get("estimated_cost_usd") or 0.0)
        if uso.get("cost_projection_complete") is False:
            n_incompleto += 1
        elif "cost_projection_complete" not in uso:
            n_desconocido += 1
    raiz = turnos[0]
    fechas = [t["created_at"] for t in turnos if t["created_at"]]
    return {
        "thread_id": thread_id,
        "root_run_id": raiz["run_id"], "root_run_no": raiz["run_no"],
        "label": f"T-{raiz['run_no']}" if raiz["run_no"] is not None else None,
        "root_pre_adr_0079": raiz_virtual is not None,
        "root_question_id": next((c.get("root_question_id") for c in completas
                                  if c.get("root_question_id")), None),
        "turns": turnos, "n_turns": len(turnos),
        "n_closed": sum(1 for t in turnos if t["state"] == "closed"),
        "n_turns_without_record": sum(1 for t in turnos if not t["has_frozen_record"]),
        "authors": sorted(autores),
        "date_range": {"first": min(fechas) if fechas else None, "last": max(fechas) if fechas else None},
        "gap_flags_union": _union_gap_flags(turnos_flags),
        "total_cost_usd": {
            "value": round(total, 4),
            "complete": n_sin_uso == 0 and n_incompleto == 0 and n_desconocido == 0,
            "n_turns_without_usage": n_sin_uso, "n_turns_cost_incomplete": n_incompleto,
            "n_turns_cost_unknown": n_desconocido,
            "cost_class": f"PROJECTION (suma de estimated_cost_usd CONGELADOS por turno; tokens medidos x "
                          f"precios por Mtok al {runs_mod.PRICES_AS_OF}; un turno sin usage o incompleto "
                          f"deja la suma INCOMPLETA y así se declara)"},
        "pivot_suggested": _pivot(turnos_flags),
        "origins": origenes,
        "origin_unknown_label": ORIGIN_UNKNOWN,
    }


# --- comentarios de corrida (ADR-0077) -------------------------------------------------------------

COMMENT_BODY_MAX = 4000        # el mismo tope que las notas de calificación: un comentario no es un apunte


class RunCommentBody(BaseModel):
    body: str


def _corrida_o_404(run_id: str):
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="no such run")
    return run


@app.get("/runs/{run_id}/comments")
def list_run_comments(run_id: str, authorization: str = Header(None)):
    """ADR-0077: la conversación del equipo SOBRE la pregunta de esta corrida. Anexo append-only y
    PÚBLICO para toda sesión válida (permisos planos); fuera del registro congelado, de las
    calificaciones (M5) y de los apuntes. NO-SPEND. El tope del cuerpo se declara (body_max)."""
    _user_of(authorization)
    _corrida_o_404(run_id)
    comentarios = db.list_run_comments(run_id)
    return {"run_id": run_id, "comments": comentarios, "n": len(comentarios),
            "body_max": COMMENT_BODY_MAX}


@app.post("/runs/{run_id}/comments", status_code=201)
def create_run_comment(run_id: str, body: RunCommentBody, authorization: str = Header(None)):
    """Autor y hora los pone el SERVIDOR (procedencia de la sesión, ADR-0056). Sin PATCH ni DELETE:
    lo dicho queda dicho. La corrida no se toca."""
    user = _user_of(authorization)
    _corrida_o_404(run_id)
    texto = body.body.strip()
    if not texto:
        raise HTTPException(status_code=400, detail="un comentario vacío no se guarda")
    if len(texto) > COMMENT_BODY_MAX:
        raise HTTPException(status_code=400, detail=f"body: máximo {COMMENT_BODY_MAX} caracteres")
    return db.create_run_comment(uuid.uuid4().hex, run_id, user["user_id"], texto)


@app.get("/runs/{run_id}/record")
def get_frozen_record(run_id: str, authorization: str = Header(None)):
    """The frozen record the UI renders (URL / PDF / bitácora — one source, three readers, ADR-0046).
    Two zones (registro-congelado.md / ADR-0064): the frozen MEASUREMENTS come verbatim from the blob
    and never change; `ratings`/`consensus` are merged at read time from the append-only run_ratings
    table — the blob itself is never rewritten. Others' scores stay MASKED until the requester has
    rated (M5 independence — server-enforced, not UI discipline)."""
    user = _user_of(authorization)
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="no such run")
    if not run.get("frozen_record_json"):
        raise HTTPException(status_code=409, detail={"state": run["state"],
                                                     "note": "no frozen record yet (run not finished)"})
    rec = json.loads(run["frozen_record_json"])
    rec.update(_ratings_view(run, user["user_id"]))
    return rec


@app.get("/runs/{run_id}/record.pdf")
def get_record_pdf(run_id: str, authorization: str = Header(None)):
    """M4 export (ADR-0073): el PDF de SERVIDOR, generado DEL JSON CONGELADO con plantilla propia —
    jamás 'imprimir la página' (el derivado limpio es la fuga que este canal existe para tapar).
    Identidad rota (question_matches_run=false) => 409, la misma regla que la hoja (ADR-0044).
    El consenso viaja como conteos; los scores individuales no se exportan en v1."""
    user = _user_of(authorization)
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="no such run")
    if not run.get("frozen_record_json"):
        raise HTTPException(status_code=409, detail={"state": run["state"],
                                                     "note": "no frozen record yet (run not finished)"})
    rec = json.loads(run["frozen_record_json"])
    rec.update(_ratings_view(run, user["user_id"]))
    try:
        pdf_bytes = record_pdf_mod.build_pdf(rec)
    except ValueError as e:
        raise HTTPException(status_code=409, detail={"state": "identity-mismatch", "note": str(e)})
    from fastapi.responses import Response
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="registro_{run_id}.pdf"'})


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


# --- ratings + calibración (M5 → Test 4; tapón 4 de PENDIENTES DE BACK, ADR-0064) --------------------

class RatingBody(BaseModel):
    # Escala 1-5 del contrato del registro congelado (M5). El banco CSV usa OTRA escala (0-2
    # categórica): son instrumentos distintos y cada rating viaja con su campo `instrument`.
    rating_input: int | None = None
    rating_output: int | None = None
    rating_input_state: str | None = None    # "value" | "cannot-rate"
    rating_output_state: str | None = None   # "value" | "cannot-rate" | "not-applicable"
    # DOS notas (M5 v2, ADR-0075). `note` habla de la RESPUESTA; `note_question` de la PREGUNTA. Las dos
    # opcionales y las dos SIEMPRE ofrecidas por la UI: el banco midió que el texto libre fue lo único
    # que produjo diagnóstico, y que separarlo en dos columnas es lo que hizo posible atribuirlo.
    note: str = ""
    note_question: str = ""


def _rating_axis(value, state, allowed, axis):
    """Normalize one axis to (value, state) or 400. The [?] of M5 is EXPLICIT: absence of judgment is a
    declared state ('cannot-rate' / 'not-applicable'), never a silent null and NEVER a 1."""
    if state is None:
        if value is None:
            raise HTTPException(status_code=400, detail=f"{axis}: da un valor 1-5 o declara el estado "
                                f"explícito ({'|'.join(allowed[1:])}) — la ausencia silenciosa no existe (M5)")
        state = "value"
    if state not in allowed:
        raise HTTPException(status_code=400, detail=f"{axis}_state debe ser uno de {allowed}")
    if state == "value":
        if not isinstance(value, int) or not 1 <= value <= 5:
            raise HTTPException(status_code=400, detail=f"{axis} debe ser un entero 1-5 cuando el estado es 'value'")
    elif value is not None:
        raise HTTPException(status_code=400, detail=f"{axis}: un estado '{state}' no lleva número")
    return value, state


def _ratings_view(run, requester_id):
    """Ratings + consensus for one run, with the M5 independence rule SERVER-ENFORCED: others' scores
    and notes are masked until the requester has emitted their own rating ('si ves lo que ya opinaron,
    dejas de ser independiente'). The consensus block only counts — it never aggregates values."""
    rows = db.ratings_for(run["run_id"])
    has_rated = any(r["rated_by"] == requester_id for r in rows)
    if has_rated or not rows:
        visible, masked = rows, False
    else:
        visible = [{"seq": r["seq"], "rated_by": r["rated_by"], "rated_at": r["rated_at"],
                    "instrument": r["instrument"], "is_author": r["is_author"], "masked": True}
                   for r in rows]
        masked = True
    out = {"ratings": visible, "ratings_masked": masked,
           "consensus": db.consensus_view(run["run_id"], run["user_id"])}
    if masked:
        out["ratings_masking_note"] = ("las calificaciones ajenas se ocultan hasta que emitas la tuya "
                                       "(independencia M5, aplicada en el servidor)")
    return out


@app.post("/runs/{run_id}/ratings")
def add_rating(run_id: str, body: RatingBody, authorization: str = Header(None)):
    """Append ONE rating (M5 cierre/consenso). Append-only: a correction is a NEW row (the latest per
    rater counts for consensus/calibration); nothing is ever overwritten. Provenance derived server-side
    (rated_by/rater_profile/is_author/instrument) — same principle as ADR-0056's derived signer. The
    run_events entry carries NO scores (a reader of /events must not pierce the masking)."""
    user = _user_of(authorization)
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="no such run")
    if run["state"] not in db.RATABLE_STATES:
        raise HTTPException(status_code=409, detail={
            "state": run["state"],
            "note": "solo se califica una corrida que terminó (awaiting_closure/closed/failed/cancelled)"})
    rin, rin_state = _rating_axis(body.rating_input, body.rating_input_state,
                                  db.RATING_INPUT_STATES, "rating_input")
    rout, rout_state = _rating_axis(body.rating_output, body.rating_output_state,
                                    db.RATING_OUTPUT_STATES, "rating_output")
    note = (body.note or "").strip()
    if len(note) > 4000:
        raise HTTPException(status_code=400, detail="note: máximo 4000 caracteres")
    note_q = (body.note_question or "").strip()
    if len(note_q) > 4000:
        raise HTTPException(status_code=400, detail="note_question: máximo 4000 caracteres")
    stored = db.add_rating(run, user, rin, rin_state, rout, rout_state, note, note_q)
    db.add_event(run_id, "rating.added",
                 payload={"rated_by": stored["rated_by"], "instrument": stored["instrument"],
                          "seq": stored["seq"], "rating_input_state": rin_state,
                          "rating_output_state": rout_state})
    return {"rating": stored, **_ratings_view(run, user["user_id"])}


@app.get("/runs/{run_id}/ratings")
def get_ratings(run_id: str, authorization: str = Header(None)):
    """Ratings + consensus of one run, masked per the requester (see _ratings_view)."""
    user = _user_of(authorization)
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="no such run")
    return _ratings_view(run, user["user_id"])


@app.get("/ratings/pending")
def ratings_pending(authorization: str = Header(None)):
    """The M5 'PENDIENTES DE CALIFICAR' queue for the session user: ratable runs they have not rated,
    each with its consensus counts and frozen epistemic summary (a rater must see the epistemic state —
    'no se puede calificar una respuesta degradada creyendo que estaba limpia')."""
    user = _user_of(authorization)
    out = []
    for row in db.runs_pending_rating(user["user_id"]):
        row["epistemic_summary"] = (json.loads(row.pop("epistemic_summary_json"))
                                    if row.get("epistemic_summary_json") else None)
        row.pop("epistemic_summary_json", None)
        row["consensus"] = db.consensus_view(row["run_id"], row["user_id"])
        out.append(row)
    return {"pending": out, "expected_of": user["user_id"],
            "note": "calificar es esperado, no opcional (M5) — pero JAMÁS bloquea una corrida"}


def _origins_param(csv):
    """ADR-0079 (F): `include_origins` como CSV de query -> lista o None (None = el default del consumidor:
    sólo 'production', con las corridas pre-ADR de origin NULL incluidas y declaradas). Un origen fuera
    del enum db.RUN_ORIGINS es 400 con la lista permitida — filtrar por un origen que no existe
    devolvería un corpus vacío indistinguible de 'no hay corridas'. Los smokes corren con
    WITT_RUN_ORIGIN=smoke y piden include_origins=smoke explícitamente (documentado en el gate)."""
    if csv is None or not isinstance(csv, str):   # llamadas directas (no-HTTP) pasan el default
        return None
    valores = [v.strip() for v in csv.split(",") if v.strip()]
    if not valores:
        return None
    fuera = [v for v in valores if v not in db.RUN_ORIGINS]
    if fuera:
        raise HTTPException(status_code=400, detail={
            "state": "invalid-origin", "invalid": fuera, "allowed": list(db.RUN_ORIGINS),
            "note": "include_origins: CSV de orígenes del enum ADR-0079"})
    return valores


@app.get("/calibration")
def calibration_report(include_origins: str = None, authorization: str = Header(None)):
    """ECE sobre corridas CERRADAS anclado en calificaciones humanas (tapón 4, ADR-0064). Reutiliza
    compute_ece.py (nunca re-implementa el binning); el mapeo de outcomes viaja DECLARADO en la
    respuesta; con n < umbral el reporte lo dice (`power.sufficient: false`) en vez de calcular a
    ciegas. NO-SPEND por construcción.
    ADR-0079: `include_origins` (CSV) — default sólo 'production' (+ pre-ADR NULL, declaradas); la
    respuesta declara origins_included / excluded_by_origin (calibration.py los calcula)."""
    _user_of(authorization)
    return calibration_mod.report(include_origins=_origins_param(include_origins))


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

USAGE_BY_STAGE_CLASS = "MEDICION (tokens) · PROYECCION (USD con precios de hoy)"
USAGE_STAGE_ABSENT = "absent-in-record"        # la etapa no viene en by_stage de ese registro (declarado)
# corrector ADR-0081 (H): 'not-measured' = etapa sin NINGUNA corrida medida en el periodo (n_runs_measured 0) → USD null,
# jamás 0.0 'priced' (0 medido ≠ null no medido — §7).
USAGE_PRICE_STATES = ("priced", "missing", "mixed", "stage-without-model", "not-measured")


def _es_entero(v):
    return isinstance(v, int) and not isinstance(v, bool)


class _StageAccumulator:
    """ADR-0081 (H): agrega usage_json.by_stage de N corridas SIN tocar la suma de hoy (totals/by_user/
    most_expensive siguen byte a byte en el bucle de /usage). Por etapa: in/out (suma SÓLO de enteros),
    n_runs_measured / n_runs_null (null ≠ 0), states {literal: n}, model_split {model: {in,out}} | null,
    estimated_cost_usd | null + price_state (∈ USAGE_PRICE_STATES; 'not-measured' cuando n_runs_measured == 0 — corrector:
    una suma vacía no es un costo de 0.0). model_split sale de by_stage[etapa].model (plan/synth/elicit/
    revision, 1.9+) y de by_stage.panel.by_model {reviewer: {in,out}} (1.10); un panel 1.9 sin by_model suma en
    _unattributed.panel {in,out,n_runs} (declarado, jamás repartido)."""

    def __init__(self):
        self.stages = {s: {"in": 0, "out": 0, "n_runs_measured": 0, "n_runs_null": 0, "states": {},
                           "model_split": {}, "unattributed_in": 0, "unattributed_out": 0}
                       for s in runs_mod.TOKEN_STAGES if s != "embed"}
        self.embed = {"tokens": 0, "n_runs": 0}
        self.by_model_stage = {}
        self.unattributed_panel = {"in": 0, "out": 0, "n_runs": 0}
        self.n_with = self.n_without = self.n_mismatch = 0
        self.n_panel_by_model = self.n_panel_without = 0
        self.models_seen = set()

    def _split(self, stage, model, i, o):
        acc = self.stages[stage]["model_split"].setdefault(model, {"in": 0, "out": 0})
        acc["in"] += i
        acc["out"] += o
        ms = self.by_model_stage.setdefault(model, {}).setdefault(stage, {"in": 0, "out": 0})
        ms["in"] += i
        ms["out"] += o
        self.models_seen.add(model)

    def add(self, u):
        bs = u.get("by_stage")
        if not isinstance(bs, dict):
            self.n_without += 1          # pre-1.9: sin reparto por etapa ≠ gasto cero
            return
        self.n_with += 1
        if u.get("by_stage_sum_matches_by_model") is False:
            self.n_mismatch += 1
        for stage in runs_mod.TOKEN_STAGES:
            cell = bs.get(stage)
            if stage == "embed":
                tok = cell.get("tokens") if isinstance(cell, dict) else None
                if _es_entero(tok):
                    self.embed["tokens"] += tok
                    self.embed["n_runs"] += 1
                continue
            acc = self.stages[stage]
            if not isinstance(cell, dict):
                acc["n_runs_null"] += 1
                acc["states"][USAGE_STAGE_ABSENT] = acc["states"].get(USAGE_STAGE_ABSENT, 0) + 1
                continue
            i, o = cell.get("in"), cell.get("out")
            measured = _es_entero(i) and _es_entero(o)
            if measured:
                acc["in"] += i
                acc["out"] += o
                acc["n_runs_measured"] += 1
            else:
                acc["n_runs_null"] += 1
            st = cell.get("state")
            if isinstance(st, str) and st:
                acc["states"][st] = acc["states"].get(st, 0) + 1
            if stage == "panel":
                bm = cell.get("by_model")
                if isinstance(bm, dict):
                    self.n_panel_by_model += 1
                    for reviewer, mm in bm.items():
                        if isinstance(mm, dict) and _es_entero(mm.get("in")) and _es_entero(mm.get("out")):
                            self._split("panel", str(reviewer), mm["in"], mm["out"])
                elif measured:
                    self.n_panel_without += 1
                    self.unattributed_panel["in"] += i
                    self.unattributed_panel["out"] += o
                    self.unattributed_panel["n_runs"] += 1
                    acc["unattributed_in"] += i
                    acc["unattributed_out"] += o
                continue
            model = cell.get("model")
            if measured and isinstance(model, str) and model:
                self._split(stage, model, i, o)
            elif measured and (i or o):
                acc["unattributed_in"] += i    # tokens medidos SIN modelo en la etapa → 'stage-without-model'
                acc["unattributed_out"] += o

    def result(self):
        precios = runs_mod.PRICES_PER_MTOK_USD
        out = {}
        for stage, acc in self.stages.items():
            split = acc["model_split"] or None
            faltan = sorted(m for m in (split or {}) if m not in precios)
            if acc["n_runs_measured"] == 0:
                # corrector ADR-0081 (H): 0 medido != null no medido -- sin ninguna corrida medida la etapa NO "costó 0.0":
                # no se midió. USD null + price_state 'not-measured' (literal de USAGE_PRICE_STATES, declarado en (H)).
                price_state, cost = "not-measured", None
            elif acc["unattributed_in"] or acc["unattributed_out"]:
                price_state, cost = "stage-without-model", None
            elif split and faltan and len(faltan) == len(split):
                price_state, cost = "missing", None
            elif faltan:
                price_state, cost = "mixed", None
            else:
                price_state = "priced"
                cost = round(float(sum((m["in"] * precios[k][0] + m["out"] * precios[k][1]) / 1e6
                                       for k, m in (split or {}).items())), 4)   # 0.0 medido, jamás 0 entero
            out[stage] = {"in": acc["in"], "out": acc["out"], "n_runs_measured": acc["n_runs_measured"],
                          "n_runs_null": acc["n_runs_null"], "states": acc["states"],
                          "model_split": split, "estimated_cost_usd": cost, "price_state": price_state}
        out["embed"] = dict(self.embed)
        out["_sum"] = {"in": sum(v["in"] for k, v in out.items() if k != "embed"),
                       "out": sum(v["out"] for k, v in out.items() if k != "embed")}
        bms = {m: dict(sorted(st.items())) for m, st in sorted(self.by_model_stage.items())}
        bms["_unattributed"] = {"panel": dict(self.unattributed_panel)}
        return {"by_stage": out, "by_model_stage": bms,
                "coverage": {"n_runs_with_panel_by_model": self.n_panel_by_model,
                             "n_runs_without": self.n_panel_without},
                "n_with": self.n_with, "n_without": self.n_without, "n_mismatch": self.n_mismatch}


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
    # ADR-0078: modelos con gasto medido pero SIN precio en la tabla — antes se cotizaban a 0 en silencio
    missing_price = set()
    n_incomplete = 0    # corridas que al congelarse declararon cost_projection_complete=False
    n_unknown = 0       # corridas anteriores a la llave: no declararon; no se les inventa un estado
    stage_acc = _StageAccumulator()   # ADR-0081 (H): por ETAPA y MODELO×ETAPA, acumulación APARTE del bucle de hoy
    for r in rows:
        u = json.loads(r["usage_json"]) if r.get("usage_json") else None
        if not u:
            continue
        n_with += 1
        stage_acc.add(u)
        cost = float(u.get("estimated_cost_usd") or 0.0)
        if u.get("cost_projection_complete") is False:
            n_incomplete += 1
        elif "cost_projection_complete" not in u:
            n_unknown += 1
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
            if model not in runs_mod.PRICES_PER_MTOK_USD:
                missing_price.add(model)
                bm["estimated_cost_usd"] = None   # sin precio: ausente-declarado, jamás 0.0
                bm["price_state"] = "missing"
                continue
            pi, po = runs_mod.PRICES_PER_MTOK_USD[model]
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
    # ADR-0081 (H): la familia de PROVEEDOR llega SIEMPRE del servidor (regla D18: la webapp jamás la infiere);
    # `known` = el id está en la tabla (un id que la tabla no conoce se sirve igual, declarado).
    for model, bm in by_model.items():
        bm["family"] = models.family_of(model)[0]
        bm["known"] = model in models.MODELS
    stage_out = stage_acc.result()
    catalogo = {m: models.catalog_row(m)
                for m in sorted(set(models.MODELS) | set(by_model) | set(stage_acc.models_seen))}
    return {"from": from_, "to": to, "n_runs": len(rows), "n_runs_with_usage": n_with,
            "totals": totals, "by_user": by_user, "by_model": by_model, "most_expensive": most,
            "rack_embeddings": rack,
            # ADR-0081 (H): el MISMO gasto por ETAPA (TOKEN_STAGES) y por MODELO×ETAPA, desde usage_json.by_stage
            # (1.9+) y by_stage.panel.by_model (1.10). Tokens = MEDICIÓN; USD por etapa = PROYECCIÓN con precios
            # de HOY y sólo cuando TODOS sus tokens tienen modelo con precio (si no: null + price_state, nunca 0).
            # Registros sin by_stage (pre-1.9) se CUENTAN aparte (≠ gasto cero); un panel 1.9 sin reviewer va a
            # by_model_stage._unattributed.panel — declarado, jamás repartido.
            "by_stage": stage_out["by_stage"],
            "by_model_stage": stage_out["by_model_stage"],
            "by_model_stage_coverage": stage_out["coverage"],
            "n_runs_with_by_stage": stage_out["n_with"],
            "n_runs_without_by_stage": stage_out["n_without"],
            "n_runs_by_stage_mismatch": stage_out["n_mismatch"],
            "by_stage_class": USAGE_BY_STAGE_CLASS,
            "models_catalog": catalogo,
            "model_generation_current": models.resolve_generation()[0],
            # ADR-0078 (corrector): la suma es COMPLETA sólo si (a) todo modelo con gasto tiene precio en la
            # tabla de HOY y (b) NINGUNA corrida sumada se congeló declarándose incompleta — totals suma el
            # estimated_cost_usd CONGELADO de cada corrida, así que un modelo que hoy sí tiene precio no
            # repara el gasto que aquella corrida excluyó. n_runs_cost_unknown: corridas anteriores a la
            # llave (no declararon; se cuentan aparte, no como completas por omisión).
            "missing_price_models": sorted(missing_price),
            "cost_projection_complete": (not missing_price) and n_incomplete == 0,
            "n_runs_cost_incomplete": n_incomplete,
            "n_runs_cost_unknown": n_unknown,
            "cost_class": f"PROJECTION (calculated from measured tokens x per-Mtok prices as of "
                          f"{runs_mod.PRICES_AS_OF}; the token counts are measurements, the dollars are not"
                          + ("" if not missing_price else
                             f"; INCOMPLETE — sin precio para {sorted(missing_price)}")
                          + ("" if not n_incomplete else
                             f"; INCOMPLETE — {n_incomplete} corrida(s) congeladas sin precio en su momento")
                          + ("" if not n_unknown else
                             f"; {n_unknown} corrida(s) anteriores a la llave, estado no declarado") + ")"}


# --- config history (LOTE-02·5, M6/SISTEMA): the catalog has history ---------------------------------

CONFIG_ENTRIES_CLASS = "atestiguada (archivo human-maintained; fechas de ADRs)"


@app.get("/config-history")
def config_history(authorization: str = Header(None)):
    """The comparability-affecting config changes, verbatim from rag_index/config_history.json
    (append-only, ADR-sourced dates — ADR-0055) with declared provenance. Also DECLARES where the other
    two histories live today (user account history, store_version history) instead of leaving silence.

    ADR-0081 (I): TRES clases sin mezclar formas — `entries` (ARCHIVO, clase atestiguada, byte-compatible) +
    `ledger[]` (tabla config_history en BD, clase MEDICIÓN: filas que config_ledger.boot()/observe()
    appendearon al arrancar / en corrida, recorded_at DESC, tope ledger_limit) + `current` (el estado
    EFECTIVO ahora, con fuente por campo y warnings — config_ledger.current(), la MISMA función que
    consulta_sistema.config.models_effective). `ledger_state` dice si el escritor pudo escribir ('ok' |
    kill-switch | table-missing | 'error: …' | not-booted); una lectura fallida de la tabla manda el suyo.
    `provenance.db {table, n_rows, last_recorded_at}` mide la tabla; `_embed_model_changed_at` (/status)
    sigue leyendo el ARCHIVO. Nada se reescribe ni se borra por esta puerta (GET sin efectos)."""
    _user_of(authorization)
    hist = json.loads(_CONFIG_HISTORY.read_text(encoding="utf-8"))
    lectura = config_ledger.listing(limit=config_ledger.LEDGER_LIST_LIMIT)
    escritor = config_ledger.state_view()
    actual = config_ledger.current(extra=config_ledger.default_extra())
    return {"entries": hist.get("entries", []),
            "entries_class": CONFIG_ENTRIES_CLASS,
            "ledger": lectura["rows"],
            "ledger_limit": config_ledger.LEDGER_LIST_LIMIT,
            "ledger_state": lectura["state"] or escritor["state"],
            "ledger_writer": escritor,
            "ledger_encoding": config_ledger.VALUE_ENCODING,
            "ledger_scope_rule": config_ledger.SCOPE_RULE,
            "current": actual,
            "model_generation": actual["generation"],
            "provenance": {"path": "rag_index/config_history.json",
                           "mtime": datetime.datetime.fromtimestamp(
                               _CONFIG_HISTORY.stat().st_mtime,
                               datetime.timezone.utc).isoformat(timespec="seconds"),
                           "db": {"table": config_ledger.LEDGER_TABLE, "n_rows": lectura["n_rows"],
                                  "last_recorded_at": lectura["last_recorded_at"]}},
            "user_history": {"source": "tabla users: created_at + disabled (ESTADO, no bitácora de "
                                       "eventos); altas/resets vía seed_users.py local (ADR-0048)",
                             "note": "un event-log de altas/bajas/resets es bloque futuro"},
            "store_version_history": {"source": "git — commits a analysis/outputs/"
                                                "verified_identifiers.json + su serie de ADRs "
                                                "(0029/0035/0041/0042…), cada crecimiento human-gated",
                                      "note": "puerta programática del historial del store: futura"},
            "refreshed_at": _now_iso()}


# --- browse del grafo (Rack fase 2, ADR-0071): la operación que no existía en ninguna puerta ---------

@app.get("/rack/node/{node_id}")
def rack_node(node_id: str, authorization: str = Header(None)):
    """Recorre la DATA INAMOVIBLE como grafo: documento/entidad/nicho/base con sus aristas
    (IN_NICHE, FROM_DB, FEEDS, MENTIONS con tier_weight) — y para ENTIDADES los ejes de taxonomía
    derivados (la puerta que /resolve declara nunca servir, LOTE-01·A7). `browse_mode` viaja
    SIEMPRE (graph | files-fallback declarado, §6 no-hang); NOT_FOUND = 200 found:false; el
    embedding jamás se serializa; NO-SPEND (cero embeds — lookups parametrizados)."""
    _user_of(authorization)
    return rack_browse_mod.browse_node(node_id)


# --- consulta abierta del sistema (ADR-0063 la nombró; ADR-0070 la construye) ------------------------

@app.get("/consulta-sistema")
def consulta_sistema_endpoint(q: str = None, authorization: str = Header(None)):
    """La pregunta META respondida, no solo ruteada: inventario del sistema (store, índice, corpus,
    taxonomía, corridas, config, cuarentena) con procedencia por sección + resumen en lenguaje
    natural compuesto por CÓDIGO. v1 determinista — `model_consulted: false` estructural (una
    respuesta de modelo sin panel no puede verse homologada; ADR-0070 documenta el cambio de
    mecanismo vs el handoff). NO-SPEND: reusa el /status TTL + conteos gratis."""
    _user_of(authorization)
    return consulta_mod.answer(q, _store_status(), db.run_state_tally())


# --- precedent layer (block 6, ADR-0053): the OTHER index — separate admissibility, equal value ------

@app.get("/precedent/search")
def precedent_search(q: str, k: int = 5, include_origins: str = None,
                     authorization: str = Header(None)):
    """Relevance search over CLOSED runs (explicit closure = the precedent requirement). Every item is
    structurally marked admissible_as_evidence: false — precedent informs humans and planning; it never
    enters the gated evidence object (the anti-fabrication gate is provenance-blind by design, so this
    rule lives at the product layer). Citation series stay disjoint: numbers=evidence, letters=precedent.
    ADR-0079: `include_origins` (CSV, ver _origins_param) — por default el corpus es SÓLO origin
    'production' (+ las corridas pre-ADR con origin NULL, incluidas y declaradas); la respuesta trae
    origins_included / excluded_by_origin (lo calcula precedent.py, no esta puerta)."""
    _user_of(authorization)
    if not q.strip():
        raise HTTPException(status_code=400, detail="q must be non-empty")
    return precedent_mod.search(q.strip(), k, include_origins=_origins_param(include_origins))


# --- APUNTES (2026-09-04, pedido del fundador) -------------------------------------------------------
# El cuaderno de teorías: texto LIBRE que puede citar corridas, genes y nichos —o nada— y que existe
# ANTES de que haya corrida. No son las notas de calificación (ésas van clavadas a una corrida
# terminada, son append-only y se enmascaran); por eso tabla y palabra aparte.
#
# Reglas que la puerta hace cumplir, no el cliente:
#   · escribir es SÓLO del autor (403); un apunte 'shared' se lee, no se edita
#   · visibilidad POR APUNTE, default 'private' — quien escribe decide qué comparte
#   · los enlaces se guardan VERBATIM: resolverlos contra el store es trabajo de /resolve al leer.
#     Un apunte puede citar un gen que la DI todavía no conoce, y eso es información, no error.

NOTE_TITLE_MAX = 300
NOTE_BODY_MAX = 20000          # un apunte es prosa larga (las notas de calificación son 4000)
NOTE_LINKS_MAX = 50            # tope por lista de enlaces: un apunte no es un índice


class NoteBody(BaseModel):
    title: str = ""
    body: str = ""
    visibility: str = "private"
    run_ids: list[str] = []
    entities: list[str] = []
    niches: list[str] = []


class NotePatch(BaseModel):
    """PATCH real: lo OMITIDO no se toca, lo mandado vacío SÍ vacía — son cosas distintas."""
    title: str | None = None
    body: str | None = None
    visibility: str | None = None
    run_ids: list[str] | None = None
    entities: list[str] | None = None
    niches: list[str] | None = None


def _validar_apunte(title, body, visibility, run_ids, entities, niches):
    """Los topes se declaran en el 400 (un límite sin su cifra no se puede obedecer)."""
    if title is not None and len(title) > NOTE_TITLE_MAX:
        raise HTTPException(status_code=400, detail=f"title: máximo {NOTE_TITLE_MAX} caracteres")
    if body is not None and len(body) > NOTE_BODY_MAX:
        raise HTTPException(status_code=400, detail=f"body: máximo {NOTE_BODY_MAX} caracteres")
    if visibility is not None and visibility not in db.NOTE_VISIBILITIES:
        raise HTTPException(status_code=400,
                            detail=f"visibility: uno de {list(db.NOTE_VISIBILITIES)}")
    for nombre, lista in (("run_ids", run_ids), ("entities", entities), ("niches", niches)):
        if lista is not None and len(lista) > NOTE_LINKS_MAX:
            raise HTTPException(status_code=400,
                                detail=f"{nombre}: máximo {NOTE_LINKS_MAX} enlaces")


def _apunte_o_404(note_id: str, user: dict, para_escribir: bool) -> dict:
    nota = db.get_note(note_id)
    if nota is None:
        raise HTTPException(status_code=404, detail="apunte no encontrado")
    propio = nota["author_id"] == user["user_id"]
    if para_escribir and not propio:
        raise HTTPException(status_code=403, detail={
            "state": "not-author",
            "note": "un apunte lo edita o borra SÓLO quien lo escribió"})
    if not propio and nota["visibility"] != "shared":
        # el privado ajeno no existe para este lector: 404, no 403 (un 403 confirmaría que existe)
        raise HTTPException(status_code=404, detail="apunte no encontrado")
    return nota


@app.get("/notes")
def list_notes(limit: int = 200, authorization: str = Header(None)):
    """Los apuntes VISIBLES para quien pregunta: los propios (de cualquier visibilidad) más los
    ajenos marcados 'shared'. Los privados de otra cuenta no salen ni en el conteo."""
    user = _user_of(authorization)
    items = db.list_notes(user["user_id"], limit=limit)
    return {"notes": items, "n": len(items), "limit": limit,
            "reader": user["user_id"], "body_max": NOTE_BODY_MAX}


@app.post("/notes")
def create_note(body: NoteBody, authorization: str = Header(None)):
    user = _user_of(authorization)
    _validar_apunte(body.title, body.body, body.visibility, body.run_ids, body.entities, body.niches)
    if not body.title.strip() and not body.body.strip():
        raise HTTPException(status_code=400, detail="un apunte vacío no se guarda: título o cuerpo")
    return db.create_note(uuid.uuid4().hex, user["user_id"], body.title.strip(), body.body,
                          body.visibility, body.run_ids, body.entities, body.niches)


@app.get("/notes/{note_id}")
def get_note(note_id: str, authorization: str = Header(None)):
    user = _user_of(authorization)
    return _apunte_o_404(note_id, user, para_escribir=False)


@app.patch("/notes/{note_id}")
def update_note(note_id: str, body: NotePatch, authorization: str = Header(None)):
    user = _user_of(authorization)
    _apunte_o_404(note_id, user, para_escribir=True)
    _validar_apunte(body.title, body.body, body.visibility, body.run_ids, body.entities, body.niches)
    campos = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if "title" in campos:
        campos["title"] = campos["title"].strip()
    return db.update_note(note_id, campos)


@app.delete("/notes/{note_id}")
def delete_note(note_id: str, authorization: str = Header(None)):
    user = _user_of(authorization)
    _apunte_o_404(note_id, user, para_escribir=True)
    return {"deleted": db.delete_note(note_id), "note_id": note_id}


@app.post("/notes/{note_id}/question")
def draft_question(note_id: str, authorization: str = Header(None)):
    """EL AGENTE: apunte -> pregunta que opera en Witt (2026-09-04). GASTA — una llamada al
    modelo best-tier — y por eso es una acción EXPLÍCITA de la persona, jamás automática al
    guardar. El gasto se guarda con el borrador.

    Redactar es del AUTOR del apunte: un apunte compartido se lee, y poner a gastar sobre la
    teoría ajena no es leerla.

    §6 no-hang: si el modelo falla, la puerta responde 200 con un borrador `errored` que trae la
    causa verbatim. Un 500 perdería el registro del intento, y el intento fallido también es dato
    de calibración."""
    user = _user_of(authorization)
    nota = _apunte_o_404(note_id, user, para_escribir=True)
    if not (nota["title"].strip() or nota["body"].strip()):
        raise HTTPException(status_code=400, detail="un apunte vacío no da pregunta")

    borrador, usage = question_agent.draft_question(nota)
    return db.create_note_question(
        uuid.uuid4().hex, note_id, user["user_id"],
        borrador["spec_version"], borrador["model"], borrador["state"],
        borrador["question"], borrador["entities"],
        json.dumps(borrador, ensure_ascii=False, default=str),
        usage_json=json.dumps(usage, ensure_ascii=False, default=str) if usage else None,
        error=borrador.get("error"))


@app.get("/notes/{note_id}/questions")
def questions_of_note(note_id: str, authorization: str = Header(None)):
    """Los borradores de un apunte, el más nuevo primero. La historia de intentos NO se borra al
    pedir otro: es el material de la depuración."""
    user = _user_of(authorization)
    _apunte_o_404(note_id, user, para_escribir=False)
    items = db.questions_of_note(note_id)
    return {"questions": items, "n": len(items),
            "spec_version_actual": question_agent.QUESTION_SPEC_VERSION}


@app.get("/notes/questions/spec")
def question_spec(authorization: str = Header(None)):
    """La especificación VIGENTE, verbatim. La UI muestra la MISMA regla que el agente obedeció:
    una regla que el operador no puede leer no se puede depurar."""
    _user_of(authorization)
    # ADR-0081 (J): el modelo del agente se RESUELVE en la llamada (tabla/env), con su fuente y generación —
    # la UI muestra la misma elección que el redactor obedecerá, no una constante copiada en import.
    rol = models.resolve_role("question_agent")
    return {"spec": question_agent.QUESTION_SPEC, "model": rol["model"],
            "model_source": rol["source"], "generation": rol["generation"]}


@app.get("/notes/questions/calibration")
def question_calibration(include_origins: str = None, authorization: str = Header(None)):
    """El tablero de depuración del agente, POR VERSIÓN DE SPEC: enfrenta lo que el agente
    AFIRMÓ (fits_one_run) con lo que el humano MIDIÓ (rating_input = eje pregunta, TAMAÑO).
    Todo son conteos — promediar una ordinal de 5 anclas inventaría una medición.
    ADR-0079: `include_origins` (CSV) — las corridas que respaldan un borrador se filtran por origin
    igual que precedente y calibración (default 'production' + pre-ADR NULL declaradas). Corrector: el
    default se aplica AQUÍ, en la puerta, vía precedent.normalize_origins (None -> ('production',)) — antes
    None llegaba a db.question_calibration como SIN FILTRO y un borrador respaldado por una corrida smoke
    contaba en el tablero con origins_included null. db.question_calibration(None) sigue siendo 'sin filtro'
    para llamadas de biblioteca, declarado en su docstring."""
    _user_of(authorization)
    return db.question_calibration(
        include_origins=list(precedent_mod.normalize_origins(_origins_param(include_origins))))


@app.get("/runs/{run_id}/notes")
def notes_for_run(run_id: str, authorization: str = Header(None)):
    """El hipervínculo AL REVÉS: qué apuntes visibles citan esta corrida — para que la hoja pueda
    decir 'esto ya lo pensaste aquí'. Misma regla de visibilidad que /notes."""
    user = _user_of(authorization)
    items = db.notes_citing_run(run_id, user["user_id"])
    return {"notes": items, "n": len(items), "run_id": run_id}


# --- aliases matching the UI's proposed surface (UI-DATA-CONTRACTS.md §2) — same handlers ------------
app.get("/rack/search")(query)
app.get("/rack/resolve")(resolve)
app.get("/rack/status")(status)

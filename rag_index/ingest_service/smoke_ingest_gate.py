"""smoke_ingest_gate.py — regresion determinista del gate del ingest service (ADR-0045).

Cubre los defectos verificados el 2026-08-09:
  - /reject borraba el archivo y devolvia 200 aunque el sid no existiera, sin razon, sin autor, sin rastro
    (destruccion silenciosa — incompatible con el historico de cambios a la DI).
  - /approve sin lock: dos aprobaciones concurrentes calculaban el MISMO _next_id y podian dejar media
    ingesta ("aplicado en Neo4j pero NO en git").
  - la cola no tenia created_at ni orden (lexicografico sobre uuid4 = ningun orden).

100% offline: QUEUE/REJECTED/ACTIONS_LOG/MANIFEST van a un tmp dir; ingest.py y git_sync se stubben
(NUNCA se toca Neo4j ni GitHub — cero mutacion de la DATA INAMOVIBLE). Exit 0 = todo PASS.

Corre:  python rag_index/ingest_service/smoke_ingest_gate.py
(necesita `fastapi` + `python-multipart` — el container del servicio los trae; en dev usa cualquier venv
con `pip install fastapi python-multipart`. NO instalar en el .venv del MCP: esta pineado por uv.lock y
contaminarlo fue la causa raiz del incidente 2026-07-19, ADR-0039.)
"""
import json
import os
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TMP = Path(tempfile.mkdtemp(prefix="smoke_ingest_gate_"))
os.environ["INGEST_QUEUE_DIR"] = str(TMP / "queue")
os.environ["INGEST_REJECTED_DIR"] = str(TMP / "rejected")
os.environ["INGEST_ACTIONS_LOG"] = str(TMP / "actions_log.jsonl")
os.environ["INGEST_LOCK_FILE"] = str(TMP / "write.lock")
os.environ.setdefault("INGEST_SUBMIT_TOKEN", "smoke-submit-token")
os.environ.setdefault("INGEST_ADMIN_TOKEN", "smoke-admin-token")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402  (reads the env above at import)
from fastapi import HTTPException  # noqa: E402

ADMIN = "Bearer " + os.environ["INGEST_ADMIN_TOKEN"]

# ---- stubs: NEVER touch Neo4j / GitHub from this smoke (zero DI mutation) --------------------------
MANIFEST_TMP = TMP / "corpus_manifest.json"
MANIFEST_TMP.write_text(json.dumps({"records": [], "status": "smoke"}), encoding="utf-8")
app.MANIFEST = MANIFEST_TMP
app.git_sync = types.SimpleNamespace(enabled=lambda: False)


def _fake_ingest(cmd, capture_output=True, text=True):
    time.sleep(0.05)   # widen the race window for the concurrency check
    return types.SimpleNamespace(returncode=0, stdout="smoke ingest ok", stderr="")


app.subprocess = types.SimpleNamespace(run=_fake_ingest)

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


def _seed(sid, created_at, name="dataset X"):
    (app.QUEUE / f"{sid}.json").write_text(json.dumps({
        "submission_id": sid, "corpus_record_id": "CORPUS-0000-0000",
        "source_document": {"name": name, "accession": None, "source_db": "local"},
        "axis_data_niche": {"primary": "RN11"}, "axis_scientific_domain": {"primary": "N1"},
        "entities_extracted": [], "proposed_placement": {"data_niche": "RN11", "confidence": 0.5,
                                                         "reasoning": "smoke"},
        "raw_provenance": {"policy": "hybrid", "files": []},
        "approval_chain": [{"gate": "categorization", "status": "pending_review"}],
        "substrate_evidence": ["test_1"], "created_at": created_at,
    }, indent=2), encoding="utf-8")


def _http_error(fn, *a, **kw):
    try:
        fn(*a, **kw)
        return None
    except HTTPException as e:
        return e.status_code


# ---- 1. auth: token equivocado -> 401 --------------------------------------------------------------
check("auth: token equivocado -> 401",
      _http_error(app.reject, "whatever", by="mallory", reason="x", authorization="Bearer wrong") == 401)

# ---- 2. reject de sid inexistente -> 404 (antes: 200 silencioso) -----------------------------------
check("reject sid inexistente -> 404 (antes devolvia 200)",
      _http_error(app.reject, "nope", by="emmanuel", reason="duplicado", authorization=ADMIN) == 404)

# ---- 3. reject sin razon -> 400 ---------------------------------------------------------------------
_seed("zzz-old", "2026-08-01T10:00:00+00:00")
check("reject sin razon -> 400 (la razon es obligatoria)",
      _http_error(app.reject, "zzz-old", by="emmanuel", reason="  ", authorization=ADMIN) == 400)

# ---- 4. orden de /pending por created_at, no por uuid -----------------------------------------------
_seed("aaa-new", "2026-08-05T10:00:00+00:00")   # uuid lexicograficamente MENOR pero MAS NUEVO
p = app.pending(authorization=ADMIN)["pending"]
check("/pending ordena por created_at (FIFO real, no lexicografico)",
      [x["submission_id"] for x in p] == ["zzz-old", "aaa-new"]
      and all(x.get("created_at") for x in p))

# ---- 5. reject real: archiva (append-only), no borra; queda autor+razon+timestamp -------------------
r = app.reject("zzz-old", by="emmanuel", reason="fuente no confiable", authorization=ADMIN)
arch = app.REJECTED / "zzz-old.json"
rec = json.loads(arch.read_text(encoding="utf-8")) if arch.exists() else {}
chain = (rec.get("approval_chain") or [{}])[0]
check("reject archiva la propuesta completa con veredicto 'rejected' + autor + razon",
      r["rejected"] and arch.exists()
      and chain.get("status") == "rejected" and chain.get("rejected_by") == "emmanuel"
      and chain.get("reason") == "fuente no confiable" and chain.get("rejected_at")
      and not (app.QUEUE / "zzz-old.json").exists())
log_lines = [json.loads(l) for l in app.ACTIONS_LOG.read_text(encoding="utf-8").splitlines()]
check("reject queda en el action log (quien/que/cuando)",
      any(e["action"] == "reject" and e["submission_id"] == "zzz-old" and e["by"] == "emmanuel"
          for e in log_lines))

# ---- 6. approve feliz (manifest tmp, ingest stub): cid asignado + registro + log --------------------
r = app.approve("aaa-new", by="emmanuel", authorization=ADMIN)
man = json.loads(MANIFEST_TMP.read_text(encoding="utf-8"))
check("approve: corpus_record_id asignado + manifest actualizado + approved_at",
      r["approved"] and r["corpus_record_id"].startswith("CORPUS-")
      and len(man["records"]) == 1
      and man["records"][0]["approval_chain"][0].get("approved_at")
      and not (app.QUEUE / "aaa-new.json").exists())
log_lines = [json.loads(l) for l in app.ACTIONS_LOG.read_text(encoding="utf-8").splitlines()]
check("approve queda en el action log",
      any(e["action"] == "approve" and e["submission_id"] == "aaa-new" for e in log_lines))

# ---- 7. concurrencia: dos approve del MISMO sid -> exactamente 1 exito + 1 404 ----------------------
_seed("race-1", "2026-08-06T10:00:00+00:00")
results = []


def _try_approve():
    try:
        results.append(("ok", app.approve("race-1", by="emmanuel", authorization=ADMIN)))
    except HTTPException as e:
        results.append(("http", e.status_code))


threads = [threading.Thread(target=_try_approve) for _ in range(2)]
for t in threads:
    t.start()
for t in threads:
    t.join()
oks = [x for x in results if x[0] == "ok"]
notfound = [x for x in results if x == ("http", 404)]
man = json.loads(MANIFEST_TMP.read_text(encoding="utf-8"))
cids = [rec["corpus_record_id"] for rec in man["records"]]
check("concurrencia same-sid: exactamente 1 exito + 1 404 (no doble ingesta)",
      len(oks) == 1 and len(notfound) == 1, f"results={[(k, getattr(v, 'get', lambda *_: v)('corpus_record_id')) if k == 'ok' else (k, v) for k, v in results]}")
check("concurrencia: los corpus_record_id del manifest no colisionan",
      len(cids) == len(set(cids)), f"cids={cids}")

# ---- 8. detalle de propuesta: el gate humano YA NO firma a ciegas (ADR-0052) ------------------------
_seed("detail-1", "2026-08-10T10:00:00+00:00")
d = app.pending_detail("detail-1", authorization=ADMIN)
check("GET /pending/{sid}: propuesta COMPLETA (chain, provenance, created_at) antes de firmar",
      d["submission_id"] == "detail-1" and "approval_chain" in d and "raw_provenance" in d
      and bool(d.get("created_at")))
check("detalle de sid inexistente -> 404",
      _http_error(app.pending_detail, "nope", authorization=ADMIN) == 404)

# ---- 9. historico de acciones (decision 9-bis, read path) -------------------------------------------
acts = app.actions(authorization=ADMIN)["actions"]
kinds = {a["action"] for a in acts}
check("GET /actions: historico con approve y reject, newest-first",
      {"approve", "reject"}.issubset(kinds) and acts[0]["ts"] >= acts[-1]["ts"], f"n={len(acts)}")

# ---- 10. lock CROSS-PROCESO (ADR-0052): ocupado -> 503 honesto; stale -> takeover --------------------
app.LOCK_TIMEOUT_S = 0.5
app.LOCK_FILE.write_text("pid=99999 at=held", encoding="utf-8")
check("lock ocupado por otro proceso -> 503 'write queue busy' (jamas carrera silenciosa)",
      _http_error(app.reject, "detail-1", by="emmanuel", reason="x", authorization=ADMIN) == 503)
os.utime(app.LOCK_FILE, (0, time.time() - 2000))   # holder muerto hace >900s
r = app.reject("detail-1", by="emmanuel", reason="stale takeover test", authorization=ADMIN)
check("lock stale (holder muerto) -> takeover, la operacion procede y el lock se libera",
      r["rejected"] and not app.LOCK_FILE.exists())

npass = sum(CHECKS)
print("\n== %d/%d PASS ==" % (npass, len(CHECKS)))
sys.exit(0 if npass == len(CHECKS) else 1)

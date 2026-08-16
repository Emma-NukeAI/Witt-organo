"""smoke_query_service.py — gate determinista del query service (bloque 2, ADR-0048).

Cubre: identidad (login/logout/401, hash scrypt, sesiones expirables), el ESPEJO exacto del sobre
ADR-0043 en /query (incluida la degradacion con 0 hits — la regresion madre), el NO-SPEND estructural
de /status (falla si algo intenta un embed), el indice de artefactos historicos (ADR-0046) con
path-safety, y los alias /rack/*.

100% offline: BD = SQLite tmp; rag_backend monkeypatcheado (cero red, cero OpenAI, cero mutacion);
NEO4J_URI se limpia para que /status reporte OFFLINE honesto. Exit 0 = todo PASS.

Corre:  python rag_index/query_service/smoke_query_service.py
(necesita fastapi + sqlalchemy — el contenedor los trae; en dev un venv desechable, NO el .venv del
MCP que esta pineado por uv.lock, ADR-0039.)
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TMP = Path(tempfile.mkdtemp(prefix="smoke_query_service_"))
os.environ["WITT_BACKEND_DB_URL"] = f"sqlite:///{TMP / 'backend.db'}"
os.environ["WITT_STATUS_TTL_SECONDS"] = "2"
os.environ.pop("NEO4J_URI", None)          # /status debe reportar OFFLINE honesto, sin red
os.environ.pop("RAG_BACKEND", None)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402  (importa server -> deploy.env; NEO4J_URI ya fue limpiado arriba)
import db  # noqa: E402
import server  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from lib import rag_backend  # noqa: E402
from lib.rag_backend import Hit, HitList  # noqa: E402

# el import de app puede re-poblar NEO4J_URI desde .secrets/deploy.env -> limpiar OTRA vez para
# que _store_status y _preload no toquen la red en este smoke
os.environ.pop("NEO4J_URI", None)

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


def _http_error(fn, *a, **kw):
    try:
        fn(*a, **kw)
        return None
    except HTTPException as e:
        return e.status_code


db.init_db()
db.upsert_user("natalia", "Natalia", "medico", "pw-natalia-123")
db.upsert_user("emmanuel", "Emmanuel", "dev", "pw-emmanuel-456")

# ---- 1. identidad ----------------------------------------------------------------------------------
check("login invalido -> 401", _http_error(app.login, app.LoginBody(username="natalia", password="mal")) == 401)
sess = app.login(app.LoginBody(username="natalia", password="pw-natalia-123"))
AUTH = "Bearer " + sess["token"]
check("login ok: token + role (rater_profile) + expiracion",
      bool(sess.get("token")) and sess["role"] == "medico" and sess.get("expires_at"))
check("endpoint sin token -> 401", _http_error(app.me, authorization=None) == 401)
check("/me con sesion valida", app.me(authorization=AUTH)["user_id"] == "natalia")
check("la BD guarda solo sha256 del token (no el token)",
      sess["token"] not in json.dumps(db.list_users(), default=str) and len(sess["token"]) > 30)

# ---- 2. /query = el sobre ADR-0043 VERBATIM (incluye degradado + 0 hits) ----------------------------
_orig_q, _orig_s = rag_backend.query, rag_backend.query_sparse


def _dense_down(text, k=5):
    raise RuntimeError("forced dense failure (smoke)")


rag_backend.query = _dense_down
rag_backend.query_sparse = lambda text, k=5: HitList([], degraded="sparse-by-config")
r = app.query("zero hits degraded", 3, authorization=AUTH)
check("/query degradado+vacio: el sobre reporta degradado (la regresion madre)",
      r.get("degraded") == "sparse" and r.get("n_hits") == 0 and r.get("hits") == []
      and str(r.get("last_error", "")).startswith("dense:RuntimeError"),
      f"degraded={r.get('degraded')} last_error={str(r.get('last_error'))[:40]!r}")
env_direct = server._query("zero hits degraded", 3)
check("/query es ESPEJO de server._query (mismas llaves, cambio de transporte)",
      set(r.keys()) == set(env_direct.keys()), f"keys={sorted(r.keys())}")
rag_backend.query = lambda text, k=5: HitList(
    [Hit(doc_id="CORPUS-2026-0001", type="dataset", score=0.9, text="x", metadata={})], degraded=None)
r = app.query("healthy", 3, authorization=AUTH)
check("/query sano: degraded=None + record binding por hit (bloque 1.4)",
      r["degraded"] is None and r["n_hits"] == 1
      and r["hits"][0].get("record", {}).get("approval_status") == "approved")
check("/query sin auth -> 401", _http_error(app.query, "q", 3, authorization=None) == 401)

# ---- 3. /status NO-SPEND estructural ----------------------------------------------------------------
def _spend_trap(*a, **kw):
    raise AssertionError("NO-SPEND violado: /status intento un embed/query")


rag_backend.query, rag_backend.query_sparse = _spend_trap, _spend_trap
app._STATUS_CACHE.update(at=0.0, data=None)
st = app.status(authorization=AUTH)
FIELDS = {"store_version", "record_count", "sha", "doc_count", "entity_count",
          "embed_model", "embed_dim", "index_state", "refreshed_at"}
check("/status trae los 9 campos StoreStatus del contrato UI",
      FIELDS.issubset(st.keys()), f"faltan={sorted(FIELDS - set(st.keys()))}")
check("/status NO-SPEND (ni un embed) + datos reales del store",
      st["record_count"] == 113 and st["store_version"] == "2026-07-21.3"
      and len(st["sha"]) == 64 and st["index_state"] == "OFFLINE"
      and st["doc_count"] is None,  # Neo4j fuera -> null honesto, jamas conteo inventado
      f"n={st['record_count']} v={st['store_version']} state={st['index_state']}")
st2 = app.status(authorization=AUTH)
check("/status cachea por TTL (mismo refreshed_at dentro de la ventana)",
      st2["refreshed_at"] == st["refreshed_at"])
# --- LOTE-01·A8: integridad honesta + la fecha del cambio de embed model ------------------------------
check("/status.integrity: sin artefacto de escaneo -> scanned:false declarado (jamas 'limpio')",
      st["integrity"]["scanned"] is False and "note" in st["integrity"])
check("/status.embed_model_changed_at desde config_history.json (ADR-0021, no hardcodeado)",
      st["embed_model_changed_at"] == "2026-06-12")
rag_backend.query, rag_backend.query_sparse = _orig_q, _orig_s

# --- LOTE-01·A6: la taxonomia por UNA puerta (la UI se niega a copiar los archivos) -------------------
tax = app.taxonomia(authorization=AUTH)
check("/taxonomia: niches + databases + crosswalk con procedencia (ruta+mtime)",
      all(k in tax for k in ("niches", "databases", "crosswalk", "provenance"))
      and tax["provenance"]["niches"]["path"] == "rag_index/niches.json"
      and tax["provenance"]["niches"]["mtime"])
check("/taxonomia sin token -> 401", _http_error(app.taxonomia, authorization=None) == 401)

# --- LOTE-01·A7: los ejes por entidad NUNCA van por /resolve — declarado, no silencio -----------------
rr = app.resolve("pax2a", authorization=AUTH)
check("/resolve declara taxonomy_axes.served=false con el porque (nunca por esta puerta)",
      rr["resolved"] is True and rr["taxonomy_axes"]["served"] is False
      and "browse" in rr["taxonomy_axes"]["why"])

# ---- 4. indice de artefactos historicos (ADR-0046) --------------------------------------------------
art = app.artifacts(authorization=AUTH)
check("indice: reports/*.html listados con titulo y mtime",
      len(art["reports"]) >= 40 and all(("name" in x and "modified_at" in x) for x in art["reports"]),
      f"n_reports={len(art['reports'])}")
m0 = art["runs"].get("month_0", [])
check("indice: runs historicos con instrumented=false (sin decision_state, honesto)",
      len(m0) >= 30 and all(x["instrumented"] is False for x in m0),
      f"month_0={len(m0)}")
name = art["reports"][0]["name"]
resp = app.artifact_report(name, authorization=AUTH)
check("servir un report por nombre (FileResponse valido)",
      str(getattr(resp, "path", "")).endswith(name))
check("path traversal rechazado por membresia (404)",
      _http_error(app.artifact_report, "../CLAUDE.md", authorization=AUTH) == 404
      and _http_error(app.artifact_report, "..%2fCLAUDE.md", authorization=AUTH) == 404)
claims = [x for x in m0 if x["kind"] == "claim_record"]
aux = [x for x in m0 if x["kind"] == "aux"]
check("indice separa claim_records de artefactos aux (eps probes) sin ocultarlos",
      len(claims) >= 30 and len(aux) >= 1, f"claims={len(claims)} aux={len(aux)}")
rec = app.artifact_run("month_0", claims[0]["name"], authorization=AUTH)
check("servir un run historico (JSON con claim_id)", bool(rec.get("claim_id")))

# ---- 5. logout + alias ------------------------------------------------------------------------------
app.logout(authorization=AUTH)
check("logout revoca la sesion (siguiente llamada 401)",
      _http_error(app.me, authorization=AUTH) == 401)
routes = {r.path for r in app.app.routes}
check("alias de la superficie UI presentes (/rack/search|resolve|status)",
      {"/rack/search", "/rack/resolve", "/rack/status"}.issubset(routes))

npass = sum(CHECKS)
print("\n== %d/%d PASS ==" % (npass, len(CHECKS)))
sys.exit(0 if npass == len(CHECKS) else 1)

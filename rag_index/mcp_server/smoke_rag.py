"""smoke_rag.py — validacion end-to-end del RAG data-inamovible (determinista, venv).
Exit 0 = todo PASS. Artefacto reutilizable por el equipo de Latido."""
import os, sys, time, concurrent.futures as cf
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
_env = ROOT / ".secrets" / "deploy.env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())
os.environ["RAG_BACKEND"] = "neo4j"
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
sys.path.insert(0, str(ROOT / "rag_index" / "mcp_server"))
CHECKS = []
def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))
missing = []
for m in ("neo4j", "openai", "sklearn", "mcp", "fastembed"):
    try: __import__(m)
    except Exception: missing.append(m)
check("deps completas", not missing, ("faltan: " + ",".join(missing)) if missing else sys.executable)
# WARN (no cuenta al 6/6): tooluniverse jamas debe vivir en el .venv del MCP — corre por uvx (env aislado).
# Si es importable aqui, alguien hizo `uv pip install tooluniverse` en este venv -> drift vs uv.lock ->
# `uv run --locked` intenta desinstalarlo en cada arranque y puede romper el env (incidente 2026-07-19).
try:
    import importlib.util as _u
    if _u.find_spec("tooluniverse") is not None:
        print("WARN venv contaminado: 'tooluniverse' esta instalado en este .venv "
              "(debe correr por uvx). Corre: uv sync --locked  (o rebuild del .venv). Ver skills/external/README.md")
except Exception:
    pass
import server
from lib import rag_backend, resolve_id
Q = "transcription factors pronephric mesoderm zebrafish"
rag_backend.query(Q, 1)  # warmup: conecta Neo4j + embedder
t = time.perf_counter(); h = rag_backend.query(Q, 3); dt = time.perf_counter() - t
top = h[0].score if h else 0.0
check("semantic score alto (>=0.7)", bool(h) and top >= 0.7,
      "%.2fs top=%s:%.3f" % (dt, h[0].doc_id if h else "-", top))
r = resolve_id.resolve("pax2a")
check("resolve pax2a -> ENSDARG00000028148",
      r is not resolve_id.NOT_FOUND and r.ensdarg == "ENSDARG00000028148",
      getattr(r, "ensdarg", "NOT_FOUND"))
_old = server._DENSE_TIMEOUT_S; server._DENSE_TIMEOUT_S = 0
t = time.perf_counter(); rf = server._query(Q, 3); dt = time.perf_counter() - t
server._DENSE_TIMEOUT_S = _old
check("sparse fallback (Neo4j caido -> hits, no vacio)",
      isinstance(rf, list) and bool(rf) and dt < 3 and rf[0]["metadata"].get("degraded") == "sparse",
      "%.2fs hits=%d" % (dt, len(rf) if isinstance(rf, list) else 0))
def _one(i):
    t = time.perf_counter(); x = server._query(Q, 3)
    return time.perf_counter() - t, isinstance(x, list) and len(x) > 0
with cf.ThreadPoolExecutor(max_workers=8) as ex:
    res = list(ex.map(_one, range(8)))
allok = all(ok for _, ok in res); maxdt = max(dt for dt, _ in res)
check("concurrencia 8 usuarios (todas responden)", allok, "max=%.2fs" % maxdt)
check("no-hang (todas < 20s)", maxdt < 20, "max=%.2fs" % maxdt)
npass = sum(CHECKS)
print("\n== %d/%d PASS ==" % (npass, len(CHECKS)))
sys.exit(0 if npass == len(CHECKS) else 1)

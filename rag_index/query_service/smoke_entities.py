"""
smoke_entities.py — gate de la puerta GET /entities (el store verificado ENUMERADO, 2026-08-29).

Cubre las dos vías (lección permanente del ADR-0075: un campo puede persistir por la vía directa y
no llegar nunca por HTTP): la llamada directa a la función Y el stack ASGI completo con TestClient —
el mismo camino que recorre la webapp. Fija: 401 sin sesión · el roster resoluble con sus campos
(symbol/ensdarg/tier/tier_weight/verified_on) · los marcadores de ausencia declarados APARTE y
coherentes con /resolve (resolved: false) · la coherencia roster↔/resolve (mismo ensdarg, mismo
store_version) · orden determinista · TTL-cache · y el NO-SPEND estructural (corre con la máscara
offline: NEO4J_URI vacío, sin OpenAI — si la puerta tocara red, aquí fallaría).

Uso:  python smoke_entities.py
"""
import os
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# --- máscara offline ANTES de importar la app (misma disciplina que los otros gates) ----------------
_tmp = Path(tempfile.gettempdir()) / f"witt_entities_{uuid.uuid4().hex[:8]}.db"
os.environ["WITT_BACKEND_DB_URL"] = f"sqlite:///{_tmp.as_posix()}"
os.environ["NEO4J_URI"] = ""
os.environ["RAG_BACKEND"] = "sparse"
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""

import db  # noqa: E402
import app as app_mod  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from lib import verify_output  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  -> {detail}" if detail else ""))


db.init_db()
db.upsert_user("natalia", "Natalia", "medico", "pw-natalia")

client = TestClient(app_mod.app)

# ---- 1. sesión: las dos vías niegan sin token -------------------------------------------------------
try:
    app_mod.entities(authorization=None)
    check("vía directa sin token -> 401", False)
except HTTPException as e:
    check("vía directa sin token -> 401", e.status_code == 401)

r = client.get("/entities")
check("HTTP sin token -> 401", r.status_code == 401, f"status={r.status_code}")

r = client.post("/login", json={"username": "natalia", "password": "pw-natalia"})
assert r.status_code == 200, r.text
AUTH = {"Authorization": "Bearer " + r.json()["token"]}

# ---- 2. el sobre por HTTP: el gate VE los campos, no solo que no explotó ----------------------------
r = client.get("/entities", headers=AUTH)
check("HTTP con sesión -> 200", r.status_code == 200, f"status={r.status_code}")
env = r.json()

check("roster no vacío y conteo coherente",
      env.get("n_entities", 0) > 0 and len(env.get("entities", [])) == env["n_entities"],
      f"n_entities={env.get('n_entities')}")

campos = {"symbol", "ensdarg", "tier", "tier_weight", "verified_on"}
check("cada entidad trae symbol/ensdarg/tier/tier_weight/verified_on",
      all(campos <= set(e) for e in env["entities"]))
check("ningún ensdarg nulo en el roster (los nulos son marcadores, viajan aparte)",
      all(e["ensdarg"] for e in env["entities"]))
check("tier ∈ {RAW, DERIVED} y tier_weight coincide con verify_output",
      all(e["tier"] in ("RAW", "DERIVED") and
          e["tier_weight"] == verify_output.tier_weight(e["tier"]) for e in env["entities"]))
check("tier_weight_kind declarado (no es ranking)",
      "NOT ranking" in env.get("tier_weight_kind", ""))
check("roster ordenado determinista (por symbol)",
      [e["symbol"] for e in env["entities"]] == sorted(e["symbol"] for e in env["entities"]))
check("procedencia + refreshed_at + store_version declarados",
      bool(env.get("provenance")) and bool(env.get("refreshed_at")) and "store_version" in env)

# ---- 3. marcadores de ausencia: declarados APARTE y coherentes con /resolve -------------------------
check("marcadores de ausencia: conteo coherente y fuera del roster",
      len(env.get("absence_markers", [])) == env.get("n_absence_markers", -1)
      and not ({m["symbol"] for m in env["absence_markers"]}
               & {e["symbol"] for e in env["entities"]}),
      f"n_absence_markers={env.get('n_absence_markers')}")
if env["absence_markers"]:
    m = env["absence_markers"][0]["symbol"]
    rv = client.get(f"/resolve?key={m}", headers=AUTH).json()
    check("un marcador de ausencia NO resuelve en /resolve (resolved: false, positivo)",
          rv.get("resolved") is False, f"symbol={m}")
else:
    check("(sin marcadores en el store — nada que cruzar; se declara, no se inventa)", True)

# ---- 4. coherencia roster <-> /resolve (las dos puertas sirven el MISMO snapshot) -------------------
e0 = env["entities"][0]
rv = client.get(f"/resolve?key={e0['symbol']}", headers=AUTH).json()
check("la primera entidad del roster resuelve con el MISMO ensdarg y tier",
      rv.get("resolved") is True and rv.get("ensdarg") == e0["ensdarg"]
      and rv.get("tier") == e0["tier"], f"symbol={e0['symbol']}")
check("store_version idéntico entre /entities y /resolve",
      env.get("store_version") == rv.get("store_version"),
      f"{env.get('store_version')} vs {rv.get('store_version')}")

# ---- 5. TTL-cache: la segunda lectura dentro del TTL es el mismo snapshot ---------------------------
r2 = client.get("/entities", headers=AUTH)
check("TTL-cache: refreshed_at estable dentro del TTL",
      r2.json().get("refreshed_at") == env.get("refreshed_at"))

# ---- 6. NO-SPEND estructural: respondió con la máscara offline puesta ------------------------------
check("NO-SPEND: la puerta respondió con NEO4J_URI vacío y sin OpenAI (cero red por construcción)",
      env["n_entities"] > 0 and os.environ.get("NEO4J_URI") == "")

n_pass = sum(CHECKS)
print(f"\n{n_pass}/{len(CHECKS)} PASS")
sys.exit(0 if n_pass == len(CHECKS) else 1)

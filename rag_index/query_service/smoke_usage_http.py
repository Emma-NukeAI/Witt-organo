"""
smoke_usage_http.py — gate HTTP de GET /usage por ETAPA y por MODELO×ETAPA (ADR-0081 (H), rebanada S5).

Sobre TRES generaciones de usage_json que conviven en la BD real (nada se backfillea, ADR-0081 (J)):
  · 1.10 — by_stage completo + panel.by_model {reviewer: {in,out}} (la partición que separa a opus-5
    sintetizador de opus-5 juez correctness)
  · 1.9  — by_stage SIN panel.by_model (el panel se suma sin reviewer → _unattributed.panel, declarado,
    jamás repartido) — incluida una corrida con by_stage_sum_matches_by_model false, una etapa con tokens SIN
    modelo ('stage-without-model') y un id que la tabla no conoce (known false, sin precio)
  · pre-1.9 — sin by_stage (se CUENTA en n_runs_without_by_stage: ausencia ≠ gasto cero)

Lo que FIJA (vía ASGI TestClient, el mismo camino que la webapp — lección ADR-0075):
  · totals / by_user / most_expensive BYTE-IGUALES a f57a3d3: el golden se RE-DERIVA aquí con la regla de hoy
    (suma de usage_json congelado), independiente del código de la puerta
  · by_stage: in/out suma SÓLO enteros; n_runs_measured / n_runs_null (null ≠ 0); states {literal: n};
    model_split por etapa; estimated_cost_usd sólo cuando TODOS los tokens tienen modelo con precio (si no null
    + price_state ∈ priced|missing|mixed|stage-without-model|not-measured — nunca 0; corrector: 'not-measured' cuando
    NINGUNA corrida midió la etapa, 0 medido ≠ null no medido); embed {tokens, n_runs}; _sum
  · by_model_stage {model: {stage: {in,out}}} + _unattributed.panel {in,out,n_runs}; by_model_stage_coverage
  · n_runs_with_by_stage / n_runs_without_by_stage / n_runs_by_stage_mismatch
  · by_model[m] += family (del SERVIDOR, regla D18) y known; models_catalog desde la tabla + ids observados;
    model_generation_current; by_stage_class

NO-SPEND: sin red, sin modelo; usage_json sembrado directo en la BD sqlite temporal (fuera del repo).
Uso (máscara offline):
  WITT_BACKEND_DB_URL="sqlite:///C:/Users/Emmanuel/AppData/Local/Temp/claude/witt-smokes/adr81-usage-http.db"
  NEO4J_URI="" RAG_BACKEND=sparse OPENAI_API_KEY="" ANTHROPIC_API_KEY="" WITT_RUN_ORIGIN=smoke
  python rag_index/query_service/smoke_usage_http.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# --- máscara offline ANTES de importar la app (misma disciplina que los otros gates) ----------------
SMOKES_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Temp" / "claude" / "witt-smokes"
SMOKES_DIR.mkdir(parents=True, exist_ok=True)
_url = os.environ.get("WITT_BACKEND_DB_URL") or f"sqlite:///{(SMOKES_DIR / 'adr81-usage-http.db').as_posix()}"
os.environ["WITT_BACKEND_DB_URL"] = _url
if _url.startswith("sqlite:///"):
    _f = Path(_url[len("sqlite:///"):])
    if _f.exists():
        _f.unlink()
os.environ["NEO4J_URI"] = ""
os.environ["RAG_BACKEND"] = "sparse"
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["WITT_RUN_ORIGIN"] = "smoke"
for _var in ("WITT_MODEL_GENERATION", "OPENAI_EMBED_MODEL"):
    os.environ.pop(_var, None)

# ---- cero red: urlopen bloqueado y CONTADO durante TODO el smoke ---------------------------------------
import urllib.request as _urlreq  # noqa: E402

_URLOPEN_CALLS = []


def _urlopen_blocked(*a, **kw):
    _URLOPEN_CALLS.append(a[0] if a else kw.get("url"))
    raise RuntimeError("smoke_usage_http: red bloqueada")


_urlreq.urlopen = _urlopen_blocked

import db  # noqa: E402
import app as app_mod  # noqa: E402
import runs as runs_mod  # noqa: E402
from lib import models  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  -> {detail}" if detail else ""))


def _fin():
    n_pass = sum(CHECKS)
    print(f"\n{n_pass}/{len(CHECKS)} PASS")
    sys.exit(0 if n_pass == len(CHECKS) else 1)


# ---- fixtures: tres generaciones de usage_json -------------------------------------------------------
# ADR-0081 (M.4, S7): ningún literal de modelo fuera de models.py — los ids se LEEN de la tabla (defaults g2/g1).
_G2, _G1 = models.GENERATIONS["g2-2026-09"]["defaults"], models.GENERATIONS["g1-2026-08"]["defaults"]
OPUS5, OPUS48 = _G2["synthesizer"], _G1["synthesizer"]
SON, HAI, G4O = _G2["judge.overclaim"], _G2["judge.evidence-grounding"], _G2["judge.reproducibility"]
DESCONOCIDO = "gpt-nuevo-x"      # un id que la tabla NO conoce (prefijo gpt- → openai): se sirve igual, known false, sin precio
EMBED = models.SNAPSHOT_ALSO_READS[models.EMBED_MODEL_ENV]["default"]


def _cero(**extra):
    return {"in": 0, "out": 0, **extra}


# A · 1.10 — by_stage + panel.by_model. Σ by_stage == Σ by_model (2000 / 350).
U_A = {
    "input_tokens": 2000, "output_tokens": 350,
    "by_model": {OPUS5: {"in": 1000, "out": 200}, SON: {"in": 300, "out": 50}, HAI: {"in": 300, "out": 40},
                 G4O: {"in": 400, "out": 60}},
    "by_stage": {
        "plan": {"in": 100, "out": 20, "model": OPUS5},
        "synthesize_pass1": {"in": 600, "out": 120, "model": OPUS5},
        "elicit_pass1": {"in": 50, "out": 10, "state": "measured", "model": OPUS5},
        "search": _cero(note="Layer 0 tools — no model call (ADR-0080)"),
        "synthesize_pass2": _cero(),
        "elicit_pass2": {"in": None, "out": None, "state": "not-run"},
        "panel": {"in": 1250, "out": 200,
                  "by_model": {OPUS5: {"in": 250, "out": 50}, SON: {"in": 300, "out": 50},
                               HAI: {"in": 300, "out": 40}, G4O: {"in": 400, "out": 60}}},
        "revision": _cero(),
        "embed": {"tokens": 120, "unit": "embedding tokens (not chat tokens; excluded from _sum)"},
        "_sum": {"in": 2000, "out": 350, "rule": "sum over model stages (embed excluded); must equal by_model totals"},
    },
    "by_stage_sum_matches_by_model": True,
    "embedding": {"model": EMBED, "total_tokens": 120},
    "estimated_cost_usd": 0.0132, "missing_price_models": [], "cost_projection_complete": True,
}
# B · 1.9 — by_stage SIN panel.by_model (panel 900/130 sin reviewer → _unattributed).
U_B = {
    "input_tokens": 1500, "output_tokens": 250,
    "by_model": {OPUS48: {"in": 800, "out": 150}, SON: {"in": 200, "out": 30}, HAI: {"in": 200, "out": 30},
                 G4O: {"in": 300, "out": 40}},
    "by_stage": {
        "plan": _cero(state="no-plan"),
        "synthesize_pass1": {"in": 500, "out": 100, "model": OPUS48},
        "elicit_pass1": {"in": None, "out": None,
                         "state": "not-separable (synthesizer did not report usage_elicitation)"},
        "search": _cero(note="Layer 0 tools — no model call (ADR-0080)"),
        "synthesize_pass2": {"in": 100, "out": 20, "model": OPUS48},
        "elicit_pass2": {"in": None, "out": None, "state": "not-run"},
        "panel": {"in": 900, "out": 130},
        "revision": _cero(),
        "embed": {"tokens": 80, "unit": "embedding tokens (not chat tokens; excluded from _sum)"},
        "_sum": {"in": 1500, "out": 250},
    },
    "by_stage_sum_matches_by_model": True,
    "embedding": {"model": EMBED, "total_tokens": 80},
    "estimated_cost_usd": 0.01, "missing_price_models": [], "cost_projection_complete": True,
}
# C · pre-1.9 — sin by_stage ni cost_projection_complete (estado no declarado: n_runs_cost_unknown).
U_C = {
    "input_tokens": 800, "output_tokens": 110,
    "by_model": {OPUS48: {"in": 700, "out": 100}, G4O: {"in": 100, "out": 10}},
    "estimated_cost_usd": 0.0075,
}
# D · 1.9 con mismatch (Σ by_stage 140 ≠ by_model 150), synthesize_pass1 SIN modelo, panel sin by_model y un
# id desconocido para la tabla (sin precio → cost_projection_complete false).
U_D = {
    "input_tokens": 150, "output_tokens": 15,
    "by_model": {OPUS48: {"in": 100, "out": 10}, DESCONOCIDO: {"in": 50, "out": 5}},
    "by_stage": {
        "plan": _cero(state="no-plan"),
        "synthesize_pass1": {"in": 100, "out": 10},
        "elicit_pass1": {"in": None, "out": None, "state": "not-run"},
        "search": _cero(),
        "synthesize_pass2": _cero(),
        "elicit_pass2": {"in": None, "out": None, "state": "not-run"},
        "panel": {"in": 40, "out": 4},
        "revision": _cero(),
        "_sum": {"in": 140, "out": 14},
    },
    "by_stage_sum_matches_by_model": False,
    "estimated_cost_usd": 0.0008, "missing_price_models": [DESCONOCIDO], "cost_projection_complete": False,
}

db.init_db()
db.upsert_user("natalia", "Natalia", "medico", "pw-natalia")
db.upsert_user("emmanuel", "Emmanuel", "dev", "pw-emmanuel")
FIXTURES = [("u-a", "natalia", U_A), ("u-b", "natalia", U_B), ("u-c", "emmanuel", U_C), ("u-d", "emmanuel", U_D)]
for rid, uid, u in FIXTURES:
    db.create_run(rid, uid, f"¿pregunta {rid}?")
    db.update_run(rid, state="closed", usage_json=json.dumps(u, ensure_ascii=False))
db.create_run("u-sin", "natalia", "¿corrida sin usage (queued)?")   # n_runs cuenta, n_runs_with_usage no

client = TestClient(app_mod.app)
r = client.post("/login", json={"username": "natalia", "password": "pw-natalia"})
assert r.status_code == 200, r.text
AUTH = {"Authorization": "Bearer " + r.json()["token"]}

# ---- golden RE-DERIVADO con la regla de f57a3d3 (independiente del código de la puerta) --------------
def golden_hoy(rows):
    totals = {"input_tokens": 0, "output_tokens": 0, "embedding_tokens": 0, "estimated_cost_usd": 0.0}
    by_user, most = {}, None
    for r in rows:
        u = json.loads(r["usage_json"]) if r.get("usage_json") else None
        if not u:
            continue
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
        if most is None or cost > most["estimated_cost_usd"]:
            most = {"run_id": r["run_id"], "user_id": r["user_id"], "state": r["state"],
                    "question": (r["question"] or "")[:120],
                    "created_at": r["created_at"].isoformat(timespec="seconds") if r["created_at"] else None,
                    "estimated_cost_usd": round(cost, 4)}
    totals["estimated_cost_usd"] = round(totals["estimated_cost_usd"], 4)
    return totals, by_user, most


G_TOTALS, G_BY_USER, G_MOST = golden_hoy(db.runs_usage(None, None))

# ---- 1. puerta ----------------------------------------------------------------------------------------
check("GET /usage sin token -> 401", client.get("/usage").status_code == 401)
check("GET /usage?from=basura -> 400 (sin cambio)", client.get("/usage?from=ayer", headers=AUTH).status_code == 400)
resp = client.get("/usage", headers=AUTH)
check("GET /usage -> 200", resp.status_code == 200, resp.text[:200])
U = resp.json()

# ---- 2. lo de HOY, byte a byte -----------------------------------------------------------------------
check("totals BYTE-IGUAL al golden de f57a3d3 (4450 in · 725 out · 200 embed · Σ costo congelado)",
      U.get("totals") == G_TOTALS and G_TOTALS["input_tokens"] == 4450 and G_TOTALS["output_tokens"] == 725
      and G_TOTALS["embedding_tokens"] == 200, f"{U.get('totals')} vs {G_TOTALS}")
check("by_user BYTE-IGUAL al golden (natalia 2 corridas · emmanuel 2)",
      U.get("by_user") == G_BY_USER and G_BY_USER["natalia"]["n_runs"] == 2 and G_BY_USER["emmanuel"]["n_runs"] == 2,
      f"{U.get('by_user')}")
check("most_expensive BYTE-IGUAL al golden (u-a, 0.0132)",
      U.get("most_expensive") == G_MOST and G_MOST["run_id"] == "u-a", f"{U.get('most_expensive')}")
check(f"n_runs 5 · n_runs_with_usage 4 · missing_price_models [{DESCONOCIDO}] · cost_projection_complete false · "
      "n_runs_cost_incomplete 1 · n_runs_cost_unknown 1 (sin cambio ADR-0078)",
      U.get("n_runs") == 5 and U.get("n_runs_with_usage") == 4 and U.get("missing_price_models") == [DESCONOCIDO]
      and U.get("cost_projection_complete") is False and U.get("n_runs_cost_incomplete") == 1
      and U.get("n_runs_cost_unknown") == 1,
      f"n_runs={U.get('n_runs')} with={U.get('n_runs_with_usage')} missing={U.get('missing_price_models')}")
bm = U.get("by_model") or {}
check("by_model conserva in/out/estimated_cost_usd/price_state de hoy (opus-5 1000/200 → 0.01; desconocido: null + 'missing')",
      bm.get(OPUS5, {}).get("in") == 1000 and bm.get(OPUS5, {}).get("estimated_cost_usd") == 0.01
      and bm.get(DESCONOCIDO, {}).get("estimated_cost_usd") is None and bm.get(DESCONOCIDO, {}).get("price_state") == "missing",
      f"{bm.get(OPUS5)} {bm.get(DESCONOCIDO)}")

# ---- 3. (H) by_model += family/known; models_catalog; generación ------------------------------------
check(f"by_model[m] += family (del SERVIDOR, regla D18) y known: opus-5 anthropic/true · {G4O} openai/true · "
      f"{DESCONOCIDO} openai (prefijo)/false",
      bm.get(OPUS5, {}).get("family") == "anthropic" and bm.get(OPUS5, {}).get("known") is True
      and bm.get(G4O, {}).get("family") == "openai" and bm.get(G4O, {}).get("known") is True
      and bm.get(DESCONOCIDO, {}).get("family") == "openai" and bm.get(DESCONOCIDO, {}).get("known") is False,
      f"{[(m, bm[m].get('family'), bm[m].get('known')) for m in bm]}")
cat = U.get("models_catalog") or {}
check("models_catalog: los 9 ids de la tabla + el observado desconocido; forma {family, api, status, known, generation, price_state}",
      set(models.MODELS) <= set(cat) and DESCONOCIDO in cat
      and all(set(v) == {"family", "api", "status", "known", "generation", "price_state"} for v in cat.values())
      and cat[OPUS5]["status"] == "active" and cat[OPUS5]["generation"] == ["g2-2026-09"] and cat[OPUS5]["price_state"] == "priced"
      and cat[DESCONOCIDO] == {"family": "openai", "api": "openai-responses", "status": None, "known": False,
                                "generation": [], "price_state": "missing"},
      f"n={len(cat)} opus5={cat.get(OPUS5)} desconocido={cat.get(DESCONOCIDO)}")
check("model_generation_current == models.resolve_generation() ('g2-2026-09' sin env) · by_stage_class literal",
      U.get("model_generation_current") == models.resolve_generation()[0] == "g2-2026-09"
      and U.get("by_stage_class") == "MEDICION (tokens) · PROYECCION (USD con precios de hoy)",
      f"{U.get('model_generation_current')} {U.get('by_stage_class')}")

# ---- 4. (H) cobertura: con / sin by_stage; mismatch; panel con / sin by_model ------------------------
check("n_runs_with_by_stage 3 · n_runs_without_by_stage 1 (pre-1.9 ≠ gasto cero) · n_runs_by_stage_mismatch 1",
      U.get("n_runs_with_by_stage") == 3 and U.get("n_runs_without_by_stage") == 1 and U.get("n_runs_by_stage_mismatch") == 1,
      f"{U.get('n_runs_with_by_stage')} {U.get('n_runs_without_by_stage')} {U.get('n_runs_by_stage_mismatch')}")
check("by_model_stage_coverage {n_runs_with_panel_by_model 1, n_runs_without 2}",
      U.get("by_model_stage_coverage") == {"n_runs_with_panel_by_model": 1, "n_runs_without": 2},
      f"{U.get('by_model_stage_coverage')}")

# ---- 5. (H) by_stage ---------------------------------------------------------------------------------
bs = U.get("by_stage") or {}
ETAPAS = [s for s in runs_mod.TOKEN_STAGES if s != "embed"]
check("by_stage: las 8 etapas de modelo de TOKEN_STAGES + embed + _sum, cada etapa con la forma cerrada",
      set(bs) == set(ETAPAS) | {"embed", "_sum"}
      and all(set(bs[s]) == {"in", "out", "n_runs_measured", "n_runs_null", "states", "model_split",
                             "estimated_cost_usd", "price_state"} for s in ETAPAS),
      f"keys={sorted(bs)}")
check("panel: in 2190 · out 334 (Σ de los tres registros con by_stage) · n_runs_measured 3 · model_split = el by_model de la "
      "1.10 (4 reviewers) · price_state 'stage-without-model' (940/134 sin reviewer) · estimated_cost_usd null (nunca 0)",
      bs.get("panel", {}).get("in") == 2190 and bs["panel"]["out"] == 334 and bs["panel"]["n_runs_measured"] == 3
      and bs["panel"]["model_split"] == U_A["by_stage"]["panel"]["by_model"]
      and bs["panel"]["price_state"] == "stage-without-model" and bs["panel"]["estimated_cost_usd"] is None,
      f"{bs.get('panel')}")
check("synthesize_pass1: in 1200 · out 230 · model_split {opus-5 600/120, opus-4-8 500/100} · la 1.9 con tokens SIN modelo → "
      "price_state 'stage-without-model', costo null",
      bs.get("synthesize_pass1", {}).get("in") == 1200 and bs["synthesize_pass1"]["out"] == 230
      and bs["synthesize_pass1"]["model_split"] == {OPUS5: {"in": 600, "out": 120}, OPUS48: {"in": 500, "out": 100}}
      and bs["synthesize_pass1"]["price_state"] == "stage-without-model" and bs["synthesize_pass1"]["estimated_cost_usd"] is None,
      f"{bs.get('synthesize_pass1')}")
check("elicit_pass1: n_runs_measured 1 · n_runs_null 2 (null ≠ 0) · states {measured 1, not-separable… 1, not-run 1} · "
      "model_split {opus-5 50/10} · priced 0.0005",
      bs.get("elicit_pass1", {}).get("n_runs_measured") == 1 and bs["elicit_pass1"]["n_runs_null"] == 2
      and bs["elicit_pass1"]["states"] == {"measured": 1, "not-separable (synthesizer did not report usage_elicitation)": 1,
                                           "not-run": 1}
      and bs["elicit_pass1"]["model_split"] == {OPUS5: {"in": 50, "out": 10}}
      and bs["elicit_pass1"]["price_state"] == "priced" and bs["elicit_pass1"]["estimated_cost_usd"] == 0.0005,
      f"{bs.get('elicit_pass1')}")
check("plan: in 100 · out 20 · states {no-plan: 2} · model_split {opus-5} · priced 0.001 (100×5 + 20×25 por Mtok)",
      bs.get("plan", {}).get("in") == 100 and bs["plan"]["out"] == 20 and bs["plan"]["states"] == {"no-plan": 2}
      and bs["plan"]["model_split"] == {OPUS5: {"in": 100, "out": 20}} and bs["plan"]["estimated_cost_usd"] == 0.001
      and bs["plan"]["price_state"] == "priced", f"{bs.get('plan')}")
check("synthesize_pass2: sólo la 1.9 gastó (opus-4-8 100/20) → priced 0.001; elicit_pass2: 3 null, states {not-run: 3}, "
      "model_split null, in/out 0 con n_runs_measured 0 (suma vacía declarada)",
      bs.get("synthesize_pass2", {}).get("model_split") == {OPUS48: {"in": 100, "out": 20}}
      and bs["synthesize_pass2"]["estimated_cost_usd"] == 0.001
      and bs.get("elicit_pass2", {}).get("n_runs_null") == 3 and bs["elicit_pass2"]["states"] == {"not-run": 3}
      and bs["elicit_pass2"]["model_split"] is None and bs["elicit_pass2"]["n_runs_measured"] == 0
      and bs["elicit_pass2"]["in"] == 0, f"{bs.get('synthesize_pass2')} {bs.get('elicit_pass2')}")
check("(H, corrector) 0 medido ≠ null no medido: elicit_pass2 con n_runs_measured 0 → estimated_cost_usd null + price_state "
      "'not-measured' (antes: 0.0 'priced' por suma vacía); search/revision con 3 corridas medidas en 0 → 0.0 'priced' (0 MEDIDO); "
      "USAGE_PRICE_STATES declara el literal y todo price_state servido está en el vocabulario",
      bs["elicit_pass2"]["estimated_cost_usd"] is None and bs["elicit_pass2"]["price_state"] == "not-measured"
      and bs["search"]["n_runs_measured"] == 3 and bs["search"]["estimated_cost_usd"] == 0.0 and bs["search"]["price_state"] == "priced"
      and bs["revision"]["n_runs_measured"] == 3 and bs["revision"]["estimated_cost_usd"] == 0.0
      and "not-measured" in app_mod.USAGE_PRICE_STATES
      and all(bs[s]["price_state"] in app_mod.USAGE_PRICE_STATES for s in ETAPAS),
      f"{bs.get('elicit_pass2')} search={bs.get('search')}")
check("embed {tokens 200, n_runs 2} (la 1.9 sin llave embed no cuenta) · _sum {in 3640, out 614} == Σ etapas de modelo",
      bs.get("embed") == {"tokens": 200, "n_runs": 2}
      and bs.get("_sum") == {"in": sum(bs[s]["in"] for s in ETAPAS), "out": sum(bs[s]["out"] for s in ETAPAS)}
      and bs["_sum"] == {"in": 3640, "out": 614}, f"embed={bs.get('embed')} _sum={bs.get('_sum')}")

# ---- 6. (H) by_model_stage ---------------------------------------------------------------------------
bms = U.get("by_model_stage") or {}
check("by_model_stage: opus-5 {plan, synthesize_pass1, elicit_pass1, panel} — el sintetizador Y el juez correctness SEPARADOS "
      "por etapa; opus-4-8 {synthesize_pass1, synthesize_pass2}; el juez reproducibility {panel 400/60}",
      bms.get(OPUS5) == {"elicit_pass1": {"in": 50, "out": 10}, "panel": {"in": 250, "out": 50},
                         "plan": {"in": 100, "out": 20}, "synthesize_pass1": {"in": 600, "out": 120}}
      and bms.get(OPUS48) == {"synthesize_pass1": {"in": 500, "out": 100}, "synthesize_pass2": {"in": 100, "out": 20}}
      and bms.get(G4O) == {"panel": {"in": 400, "out": 60}}, f"{bms.get(OPUS5)} {bms.get(OPUS48)}")
check("by_model_stage._unattributed.panel {in 940, out 134, n_runs 2}: los paneles 1.9 sin reviewer, declarados y JAMÁS repartidos",
      (bms.get("_unattributed") or {}).get("panel") == {"in": 940, "out": 134, "n_runs": 2}, f"{bms.get('_unattributed')}")
check("el id desconocido NO aparece en by_model_stage (su gasto 1.9 no trae etapa con modelo) pero SÍ en by_model y models_catalog",
      DESCONOCIDO not in bms and DESCONOCIDO in bm and DESCONOCIDO in cat)

# ---- 7. cero red ------------------------------------------------------------------------------------
check("cero red: urllib.request.urlopen bloqueado y contado == 0", len(_URLOPEN_CALLS) == 0, f"{_URLOPEN_CALLS}")

_fin()

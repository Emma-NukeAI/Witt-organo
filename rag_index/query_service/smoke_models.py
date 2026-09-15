"""smoke_models.py — gate NO-SPEND de la rebanada S1 (ADR-0081 A/B/E/I/K): la tabla de modelos g2-2026-09.

MIDE (no promete): (1) identidad y forma cerrada de las 9 filas de `models.MODELS`; (2) `prices()` == GOLDEN de
`runs.PRICES_PER_MTOK_USD` @ f57a3d3 (literal copiado aquí) y == el `runs` vivo; (3) generaciones g2/g1 —
defaults 100% cotizados, g1 == f57a3d3 byte a byte (defaults y 5 topes), topes g2; (4) `resolve_role`/`panel`
con env INYECTADA: fuentes `env:`/`default:`/`default-invalid-env:(motivo)`, rechazos excluded-model /
wrong-family-for-lens / wrong-family-for-role, id desconocido usado tal cual con familia por prefijo, familia
desconocida declarada; (5) `api_of` + `WITT_OPENAI_API`; (6) `panel_signature`, `panel_source` (K), duplicados
declarados, `same-model-same-lens` inalcanzable hoy (declarado); (7) retiro de haiku con `today` inyectado:
`retirement_due`/`past_retirement`/auto-retire (E); (8) `relation`; (9) `snapshot` — SNAPSHOT_FIELDS cerrada,
{value, source} por campo, lectores tolerantes, `extra` del llamador, cinturón anti-secreto; (10)
`provenance_block` con stubs (planner copiado de plan_json en sus 3 estados; not-reported/prefix/different);
(11) `models.py` sólo stdlib y FAILURE-agnóstico; (12) grep estático de literales de modelo fuera de
`models.py` — PASS sólo con lista VACÍA: hasta que S2/S3/S7 migren runs.py, composite_auditor.py,
question_agent.py y sus smokes, este check FALLA y ES lo esperado (la lista de ofensores se imprime);
(13) openai >= 1.66 con `client.responses` en el venv; requirements.txt; (14) run_held_out.py toma panel y
sintetizador de la tabla, delega el juez OpenAI en `composite_auditor._default_caller` (fake con `tool=`) y erra
en voz alta ante una familia desconocida; ab_trapped_scalar.py sigue leyendo el alias `runs_mod.SYNTH_MODEL`;
(15) cero red: `urllib.request.urlopen` bloqueado y CONTADO (== 0); `sys.modules` sin `openai` al terminar.

100% offline: ninguna llamada de modelo, ninguna mutación de la DATA INAMOVIBLE ni de mcp_cache. Las envs de la
tabla se QUITAN del proceso al arrancar (el gate mide con env inyectada, nunca con la del operador). Exit 0 = todo PASS.

Corre (máscara offline, UNA base por smoke):
  WITT_BACKEND_DB_URL="sqlite:///C:/Users/Emmanuel/AppData/Local/Temp/claude/witt-smokes/adr81-models.db"
  NEO4J_URI="" RAG_BACKEND=sparse OPENAI_API_KEY="" ANTHROPIC_API_KEY="" WITT_RUN_ORIGIN=smoke
  python rag_index/query_service/smoke_models.py
"""
import ast
import json
import os
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SMOKES_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Temp" / "claude" / "witt-smokes"
SMOKES_DIR.mkdir(parents=True, exist_ok=True)
_default_db = SMOKES_DIR / "adr81-models.db"
_url = os.environ.get("WITT_BACKEND_DB_URL") or f"sqlite:///{_default_db.as_posix()}"
os.environ["WITT_BACKEND_DB_URL"] = _url
if _url.startswith("sqlite:///"):
    _f = Path(_url[len("sqlite:///"):])
    if _f.exists():
        _f.unlink()
os.environ.pop("NEO4J_URI", None)
os.environ["WITT_ALLOW_RUNS_OFFLINE"] = "1"
os.environ.setdefault("RAG_BACKEND", "sparse")
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ.setdefault("WITT_RUN_ORIGIN", "smoke")

sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "evaluation"))

# ---- cero red: urlopen bloqueado y CONTADO durante TODO el smoke ---------------------------------------------
import urllib.request as _urlreq  # noqa: E402

_NET_CALLS = []
_urlopen_real = _urlreq.urlopen


def _urlopen_blocked(*a, **kw):
    _NET_CALLS.append(str(a[0] if a else kw.get("url")))
    raise RuntimeError("network blocked by smoke_models (ADR-0081 offline gate)")


_urlreq.urlopen = _urlopen_blocked

from lib import models as m  # noqa: E402

# Las envs de la tabla NO se heredan del proceso: el gate mide con env inyectada.
for _var in list(m.ENV_TABLE) + list(m.SNAPSHOT_ALSO_READS):
    os.environ.pop(_var, None)

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


T = "2026-09-15"   # today inyectado (= MODEL_TABLE_AS_OF); la producción usa la fecha UTC del proceso

# =====================================================================================================
# 1. Identidad y forma de la tabla
# =====================================================================================================
check("identidad: MODELS_TABLE_VERSION 'g2-2026-09' · MODEL_TABLE_AS_OF '2026-09-15' · PRICES_AS_OF '2026-09'",
      m.MODELS_TABLE_VERSION == "g2-2026-09" and m.MODEL_TABLE_AS_OF == "2026-09-15" and m.PRICES_AS_OF == "2026-09")
EXPECTED_STATUS = {
    "claude-opus-5": "active", "claude-sonnet-5": "active", "claude-haiku-4-5-20251001": "retiring",
    "claude-opus-4-8": "previous-generation", "claude-fable-5-1": "excluded", "gpt-4o": "bridge",
    "gpt-6-astra": "candidate", "gpt-5.6-sol": "not-adopted", "text-embedding-3-small": "embed",
}
check("tabla: 9 filas con los ids de (A) y el status de cada una",
      set(m.MODELS) == set(EXPECTED_STATUS) and all(m.MODELS[k]["status"] == v for k, v in EXPECTED_STATUS.items()),
      f"ids={sorted(m.MODELS)}")
check("tabla: forma CERRADA por fila (MODEL_ROW_FIELDS, 13 llaves, retire_not_before/successor siempre presentes) y "
      "vocabularios (family/api/status/thinking_default) válidos",
      all(tuple(r) == m.MODEL_ROW_FIELDS for r in m.MODELS.values())
      and all(r["family"] in m.FAMILIES and r["api"] in m.APIS and r["status"] in m.STATUSES
              and r["thinking_default"] in m.THINKING_DEFAULTS and isinstance(r["api_verified"], bool)
              and isinstance(r["reasoning"], bool) for r in m.MODELS.values()))
_h = m.MODELS["claude-haiku-4-5-20251001"]
check("tabla: hechos decididos — gpt-4o chat-completions api_verified True (camino probado en vivo) · gpt-6-astra "
      "openai-responses reasoning True · gpt-5.6-sol api_verified False · haiku retire_not_before 2026-10-15 con "
      "sucesor {claude-sonnet-5, evidence-grounding} · opus-5 thinking adaptive · opus-4-8 off · fable excluded",
      m.MODELS["gpt-4o"]["api"] == "openai-chat-completions" and m.MODELS["gpt-4o"]["api_verified"] is True
      and m.MODELS["gpt-6-astra"]["api"] == "openai-responses" and m.MODELS["gpt-6-astra"]["reasoning"] is True
      and m.MODELS["gpt-5.6-sol"]["api_verified"] is False
      and _h["retire_not_before"] == "2026-10-15"
      and _h["successor"] == {"reviewer": "claude-sonnet-5", "lens": "evidence-grounding"}
      and m.MODELS["claude-opus-5"]["thinking_default"] == "adaptive"
      and m.MODELS["claude-opus-4-8"]["thinking_default"] == "off"
      and m.MODELS["claude-fable-5-1"]["status"] == "excluded")

# =====================================================================================================
# 2. Precios: GOLDEN literal de runs.PRICES_PER_MTOK_USD @ f57a3d3 (rag_index/query_service/runs.py L1469-1476)
# =====================================================================================================
GOLDEN_PRICES = {
    "claude-opus-4-8": (5.0, 25.0), "claude-sonnet-5": (2.0, 10.0),
    "claude-opus-5": (5.0, 25.0), "claude-fable-5-1": (10.0, 50.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "gpt-4o": (2.5, 10.0), "gpt-6-astra": (10.0, 50.0), "gpt-5.6-sol": (4.0, 20.0),
    "text-embedding-3-small": (0.02, 0.0),
}
check("prices(): EXACTAMENTE el golden de runs.PRICES_PER_MTOK_USD @ f57a3d3 (9 ids, tuplas (in, out))",
      m.prices() == GOLDEN_PRICES, f"diff={set(m.prices().items()) ^ set(GOLDEN_PRICES.items())}")
_p = m.prices()
_p["claude-opus-5"] = (0.0, 0.0)
check("prices(): devuelve una COPIA (mutar el resultado no toca la tabla)", m.prices() == GOLDEN_PRICES)
try:
    import runs as runs_mod  # noqa: E402
    check("runs vivo: runs.PRICES_PER_MTOK_USD == models.prices() y runs.PRICES_AS_OF == models.PRICES_AS_OF "
          "(hoy dos literales iguales; desde S3 identidad por alias)",
          runs_mod.PRICES_PER_MTOK_USD == m.prices() and runs_mod.PRICES_AS_OF == m.PRICES_AS_OF)
except Exception as e:   # pragma: no cover — el import de runs es parte de la medición
    check("runs vivo: import runs bajo la máscara", False, f"{type(e).__name__}: {e}")
    runs_mod = None

# =====================================================================================================
# 3. Generaciones
# =====================================================================================================
G2_DEFAULTS = {"synthesizer": "claude-opus-5", "planner": "claude-opus-5", "elicitation": "claude-opus-5",
               "question_agent": "claude-opus-5", "judge.correctness": "claude-opus-5",
               "judge.overclaim": "claude-sonnet-5", "judge.evidence-grounding": "claude-haiku-4-5-20251001",
               "judge.reproducibility": "gpt-4o"}
G2_TOPES = {"synthesizer": 8000, "planner": 4000, "elicitation": 2000, "question_agent": 4000, "judge-anthropic": 4000}
# f57a3d3 byte a byte: runs.SYNTH_MODEL (L91) en synth/planner/elicit; question_agent.QUESTION_MODEL (L37);
# composite_auditor.DEFAULT_PANEL (L60-65); topes CONF_TOOL 300 · PLAN_TOOL 1200 · SYNTH_TOOL 2500 · QUESTION 1200 · jueces 1200.
G1_DEFAULTS = {**{r: "claude-opus-4-8" for r in ("synthesizer", "planner", "elicitation", "question_agent", "judge.correctness")},
               "judge.overclaim": "claude-sonnet-5", "judge.evidence-grounding": "claude-haiku-4-5-20251001",
               "judge.reproducibility": "gpt-4o"}
G1_TOPES = {"synthesizer": 2500, "planner": 1200, "elicitation": 300, "question_agent": 1200, "judge-anthropic": 1200}
F57_DEFAULT_PANEL = [("claude-opus-4-8", "anthropic", "correctness"), ("claude-sonnet-5", "anthropic", "overclaim"),
                     ("claude-haiku-4-5-20251001", "anthropic", "evidence-grounding"), ("gpt-4o", "openai", "reproducibility")]
check("GENERATIONS: exactamente {g2-2026-09, g1-2026-08}; g2 defaults y TOPES de (A)",
      set(m.GENERATIONS) == {"g2-2026-09", "g1-2026-08"} and m.GENERATIONS["g2-2026-09"]["defaults"] == G2_DEFAULTS
      and m.GENERATIONS["g2-2026-09"]["max_tokens"] == G2_TOPES)
check("GENERATIONS: g1-2026-08 == f57a3d3 byte a byte (8 defaults + 5 topes 2500·1200·300·1200·1200)",
      m.GENERATIONS["g1-2026-08"]["defaults"] == G1_DEFAULTS and m.GENERATIONS["g1-2026-08"]["max_tokens"] == G1_TOPES)
_all_defaults = {v for g in m.GENERATIONS.values() for v in g["defaults"].values()}
check("defaults g1/g2: 100% conocidos por la tabla y 100% cotizados (ningún default sin precio)",
      all(v in m.MODELS and v in m.prices() for v in _all_defaults)
      and all(set(g["defaults"]) == set(m.ROLES) and set(g["max_tokens"]) == set(m.MAX_TOKENS_KEYS) for g in m.GENERATIONS.values()),
      f"defaults={sorted(_all_defaults)}")
check("ROLE_ENVS exacto (8 roles; OPENAI_JUDGE_MODEL conserva su nombre) y ENV_TABLE cerrada (21 envs del ADR)",
      m.ROLE_ENVS == {"synthesizer": "WITT_MODEL_SYNTH", "planner": "WITT_MODEL_PLANNER", "elicitation": "WITT_MODEL_ELICIT",
                      "question_agent": "WITT_MODEL_QUESTION", "judge.correctness": "WITT_JUDGE_CORRECTNESS",
                      "judge.overclaim": "WITT_JUDGE_OVERCLAIM", "judge.evidence-grounding": "WITT_JUDGE_GROUNDING",
                      "judge.reproducibility": "OPENAI_JUDGE_MODEL"}
      and set(m.ENV_TABLE) == {"WITT_MODEL_GENERATION", "WITT_MODEL_SYNTH", "WITT_MODEL_PLANNER", "WITT_MODEL_ELICIT",
                               "WITT_MODEL_QUESTION", "WITT_JUDGE_CORRECTNESS", "WITT_JUDGE_OVERCLAIM", "WITT_JUDGE_GROUNDING",
                               "OPENAI_JUDGE_MODEL", "WITT_PANEL_AUTO_RETIRE", "WITT_PANEL_MIN_FAMILIES", "WITT_PANEL_MIN_LENSES",
                               "WITT_OPENAI_API", "WITT_OPENAI_STORE", "WITT_OPENAI_MAX_OUTPUT_TOKENS",
                               "WITT_OPENAI_REASONING_EFFORT", "WITT_OPENAI_TIMEOUT_S", "WITT_ANTHROPIC_EFFORT",
                               "WITT_ANTHROPIC_EFFORT_ELICIT", "WITT_CONFIG_LEDGER", "WITT_JUDGE_RETRIES"}
      and all("default" in v and "kind" in v and "reader" in v and "effect" in v for v in m.ENV_TABLE.values()),
      f"envs={sorted(m.ENV_TABLE)}")

# =====================================================================================================
# 4. resolve_role con env INYECTADA
# =====================================================================================================
r = m.resolve_role("synthesizer", env={}, today=T)
check("resolve_role: env vacía → RoleResolved con forma cerrada (ROLE_RESOLVED_FIELDS) y default g2 "
      "{claude-opus-5, 'default:g2-2026-09', anthropic/table, anthropic-messages/table, known, priced, 8000}",
      tuple(r) == m.ROLE_RESOLVED_FIELDS and r == {
          "model": "claude-opus-5", "source": "default:g2-2026-09", "family": "anthropic", "family_source": "table",
          "api": "anthropic-messages", "api_source": "table", "known": True, "priced": True, "max_tokens": 8000,
          "generation": "g2-2026-09", "generation_source": "default-unset:WITT_MODEL_GENERATION"}, f"{r}")
g1 = {"WITT_MODEL_GENERATION": "g1-2026-08"}
g1_roles = {role: m.resolve_role(role, env=g1, today=T) for role in m.ROLES}
check("KILL-SWITCH WITT_MODEL_GENERATION=g1-2026-08: los 8 roles dan los modelos de f57a3d3 y los topes 2500/1200/300/1200/1200 "
      "(juez OpenAI: tope None declarado — es del transporte); generation_source 'env:WITT_MODEL_GENERATION'",
      {k: v["model"] for k, v in g1_roles.items()} == G1_DEFAULTS
      and g1_roles["synthesizer"]["max_tokens"] == 2500 and g1_roles["planner"]["max_tokens"] == 1200
      and g1_roles["elicitation"]["max_tokens"] == 300 and g1_roles["question_agent"]["max_tokens"] == 1200
      and g1_roles["judge.correctness"]["max_tokens"] == 1200 and g1_roles["judge.reproducibility"]["max_tokens"] is None
      and all(v["generation_source"] == "env:WITT_MODEL_GENERATION" and v["generation"] == "g1-2026-08" for v in g1_roles.values()))
check("KILL-SWITCH g1: panel() == composite_auditor.DEFAULT_PANEL @ f57a3d3 (reviewer, family, lens) en el mismo orden",
      [(x["reviewer"], x["family"], x["lens"]) for x in m.panel(env=g1, today=T)] == F57_DEFAULT_PANEL)
r = m.resolve_role("synthesizer", env={"WITT_MODEL_GENERATION": "g9-basura"}, today=T)
check("WITT_MODEL_GENERATION inválida → default g2 con generation_source 'default-invalid-env:WITT_MODEL_GENERATION (unknown-generation)'",
      r["generation"] == "g2-2026-09" and r["generation_source"] == "default-invalid-env:WITT_MODEL_GENERATION (unknown-generation)")
r = m.resolve_role("synthesizer", env={"WITT_MODEL_SYNTH": "claude-sonnet-5"}, today=T)
check("env pinea un modelo conocido → source 'env:WITT_MODEL_SYNTH', modelo sonnet-5, tope SIGUE siendo el del rol/generación (8000)",
      r["model"] == "claude-sonnet-5" and r["source"] == "env:WITT_MODEL_SYNTH" and r["max_tokens"] == 8000 and r["known"] is True)
r = m.resolve_role("planner", env={"WITT_MODEL_PLANNER": "claude-opus-5"}, today=T)
check("env igual al default sigue siendo un ACTO: source 'env:WITT_MODEL_PLANNER' (no 'default:')",
      r["source"] == "env:WITT_MODEL_PLANNER")
r = m.resolve_role("synthesizer", env={"WITT_MODEL_SYNTH": "claude-fable-5-1"}, today=T)
check("RECHAZO excluded-model: fable en cualquier rol → default con source 'default-invalid-env:WITT_MODEL_SYNTH (excluded-model)'",
      r["model"] == "claude-opus-5" and r["source"] == "default-invalid-env:WITT_MODEL_SYNTH (excluded-model)")
r1 = m.resolve_role("judge.reproducibility", env={"OPENAI_JUDGE_MODEL": "claude-opus-5"}, today=T)
r2 = m.resolve_role("judge.overclaim", env={"WITT_JUDGE_OVERCLAIM": "gpt-4o"}, today=T)
r3 = m.resolve_role("synthesizer", env={"WITT_MODEL_SYNTH": "gpt-4o"}, today=T)
check("RECHAZO wrong-family-for-lens en ambas direcciones (claude-* en OPENAI_JUDGE_MODEL → gpt-4o; gpt-* en lente Anthropic → "
      "sonnet-5) y wrong-family-for-role (gpt-* en el sintetizador, que sólo habla anthropic-messages)",
      r1["model"] == "gpt-4o" and r1["source"] == "default-invalid-env:OPENAI_JUDGE_MODEL (wrong-family-for-lens)"
      and r2["model"] == "claude-sonnet-5" and r2["source"] == "default-invalid-env:WITT_JUDGE_OVERCLAIM (wrong-family-for-lens)"
      and r3["model"] == "claude-opus-5" and r3["source"] == "default-invalid-env:WITT_MODEL_SYNTH (wrong-family-for-role)")
r = m.resolve_role("judge.reproducibility", env={"OPENAI_JUDGE_MODEL": "gpt-6-astra"}, today=T)
check("OPENAI_JUDGE_MODEL=gpt-6-astra (la palanca E1) → known, priced, api 'openai-responses' (table), source 'env:OPENAI_JUDGE_MODEL'",
      r["model"] == "gpt-6-astra" and r["known"] and r["priced"] and r["api"] == "openai-responses"
      and r["api_source"] == "table" and r["source"] == "env:OPENAI_JUDGE_MODEL")
r = m.resolve_role("judge.reproducibility", env={"OPENAI_JUDGE_MODEL": "gpt-7-nova"}, today=T)
check("id DESCONOCIDO se USA tal cual: known False, priced False, source 'env:OPENAI_JUDGE_MODEL (unknown-to-table)', "
      "familia openai por prefijo ('prefix'), api openai-responses ('prefix')",
      r == {"model": "gpt-7-nova", "source": "env:OPENAI_JUDGE_MODEL (unknown-to-table)", "family": "openai",
            "family_source": "prefix", "api": "openai-responses", "api_source": "prefix", "known": False, "priced": False,
            "max_tokens": None, "generation": "g2-2026-09", "generation_source": "default-unset:WITT_MODEL_GENERATION"}, f"{r}")
r = m.resolve_role("synthesizer", env={"WITT_MODEL_SYNTH": "llama-9"}, today=T)
check("id sin prefijo que case → family 'unknown' declarada, api None + api_source 'unknown-family', tope None (fail-loud en la llamada: S2)",
      r["family"] == "unknown" and r["family_source"] == "prefix" and r["api"] is None
      and r["api_source"] == "unknown-family" and r["max_tokens"] is None and r["known"] is False)
try:
    m.resolve_role("judge.vibes", env={}, today=T)
    check("resolve_role: rol desconocido → ValueError", False)
except ValueError:
    check("resolve_role: rol desconocido → ValueError (error de programación, no default silencioso)", True)
check("family_by_prefix: claude-*→anthropic · gpt-*/o3-*/text-embedding-*→openai · resto→unknown",
      m.family_by_prefix("claude-x-9") == "anthropic" and m.family_by_prefix("gpt-9") == "openai"
      and m.family_by_prefix("o3-mini") == "openai" and m.family_by_prefix("text-embedding-4") == "openai"
      and m.family_by_prefix("llama-9") == "unknown" and m.family_by_prefix(None) == "unknown")

# =====================================================================================================
# 5. api_of + WITT_OPENAI_API
# =====================================================================================================
check("api_of: tabla → (api, 'table'); desconocido → por prefijo; sin familia → (None, 'unknown-family')",
      m.api_of("gpt-4o", env={}) == ("openai-chat-completions", "table")
      and m.api_of("gpt-6-astra", env={}) == ("openai-responses", "table")
      and m.api_of("claude-opus-5", env={}) == ("anthropic-messages", "table")
      and m.api_of("gpt-7-nova", env={}) == ("openai-responses", "prefix")
      and m.api_of("claude-x-9", env={}) == ("anthropic-messages", "prefix")
      and m.api_of("llama-9", env={}) == (None, "unknown-family"))
check("WITT_OPENAI_API=responses fuerza Responses para TODO juez OpenAI ('env:WITT_OPENAI_API'); =chat-completions es el kill-switch "
      "(astra por chat); table/vacío/basura no tocan la tabla; jamás toca un modelo Anthropic",
      m.api_of("gpt-4o", env={"WITT_OPENAI_API": "responses"}) == ("openai-responses", "env:WITT_OPENAI_API")
      and m.api_of("gpt-6-astra", env={"WITT_OPENAI_API": "chat-completions"}) == ("openai-chat-completions", "env:WITT_OPENAI_API")
      and m.api_of("gpt-4o", env={"WITT_OPENAI_API": "table"}) == ("openai-chat-completions", "table")
      and m.api_of("gpt-4o", env={"WITT_OPENAI_API": "grpc"}) == ("openai-chat-completions", "table")
      and m.api_of("claude-opus-5", env={"WITT_OPENAI_API": "responses"}) == ("anthropic-messages", "table")
      and m.api_of("text-embedding-3-small", env={"WITT_OPENAI_API": "responses"}) == ("openai-embeddings", "table")
      and m.resolve_openai_api(env={"WITT_OPENAI_API": "grpc"}) == ("table", "default-invalid-env:WITT_OPENAI_API"))
r = m.resolve_role("judge.reproducibility", env={"WITT_OPENAI_API": "responses"}, today=T)
check("panel: el asiento reproducibility hereda el transporte forzado (gpt-4o vía openai-responses, api_source 'env:WITT_OPENAI_API')",
      r["model"] == "gpt-4o" and r["api"] == "openai-responses" and r["api_source"] == "env:WITT_OPENAI_API")

# =====================================================================================================
# 6. panel(), panel_signature, panel_source (K), duplicados, same-model-same-lens
# =====================================================================================================
P = m.panel(env={}, today=T)
check("panel(): 4 miembros en orden FIJO correctness/overclaim/evidence-grounding/reproducibility con forma cerrada "
      "(PANEL_MEMBER_FIELDS) y reviewers g2 opus-5/sonnet-5/haiku/gpt-4o; tope 4000 en Anthropic, None en OpenAI",
      [x["lens"] for x in P] == list(m.LENSES) and all(tuple(x) == m.PANEL_MEMBER_FIELDS for x in P)
      and [x["reviewer"] for x in P] == ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5-20251001", "gpt-4o"]
      and [x["max_tokens"] for x in P] == [4000, 4000, 4000, None]
      and all(x["reviewer_source"] == "default:g2-2026-09" for x in P)
      and [x["api"] for x in P] == ["anthropic-messages"] * 3 + ["openai-chat-completions"], f"{P}")
roles_ = {role: m.resolve_role(role, env={}, today=T) for role in m.PIPELINE_ROLES}
sig0 = m.panel_signature(P, roles_)
sig_pin_seat = m.panel_signature(m.panel(env={"OPENAI_JUDGE_MODEL": "gpt-6-astra"}, today=T), roles_)
sig_pin_synth = m.panel_signature(P, {**roles_, "synthesizer": m.resolve_role("synthesizer", env={"WITT_MODEL_SYNTH": "claude-sonnet-5"}, today=T)})
sig_extra_keys = m.panel_signature(P, {**roles_, "judge.correctness": {"model": "otro"}, "ruido": "x"})
sig_str_roles = m.panel_signature(P, {k: v["model"] for k, v in roles_.items()})
check("panel_signature: sha256[:16] hex determinista; cambia al pinear un asiento y al pinear el sintetizador; ignora llaves "
      "fuera de PIPELINE_ROLES; acepta {rol: RoleResolved} o {rol: 'id'}",
      re.fullmatch(r"[0-9a-f]{16}", sig0) and sig0 == m.panel_signature(P, roles_) and sig0 != sig_pin_seat
      and sig0 != sig_pin_synth and sig0 == sig_extra_keys and sig0 == sig_str_roles, f"sig0={sig0}")
RP = m.resolve_panel(env={}, today=T, directives=[{"niche": "N1"}])
check("panel_source (K): forma exacta {generation, table_version, panel_signature, directives_state 'empty-until-ADR-0082', "
      "council_hook {state, accepts, lens_scope 'global'}, lens_charges_source} — `directives` se acepta y se ignora",
      RP["panel_source"] == {
          "generation": "g2-2026-09", "table_version": "g2-2026-09", "panel_signature": sig0,
          "directives_state": "empty-until-ADR-0082",
          "council_hook": {"state": "not-available (ADR-0082)", "accepts": "directives[] → asientos/lentes por nicho",
                           "lens_scope": "global"},
          "lens_charges_source": "composite_auditor._LENS_CHARGES"}
      and m.panel_source(env={}, today=T) == RP["panel_source"], f"{RP['panel_source']}")
check("resolve_panel: llaves {panel, panel_signature, panel_source, seat_substitutions, panel_duplicate_models, rejected_env, "
      "unknown_models, warnings, generation, generation_source, roles}; env vacía → sin sustituciones ni rechazos ni desconocidos",
      set(RP) == {"panel", "panel_signature", "panel_source", "seat_substitutions", "panel_duplicate_models", "rejected_env",
                  "unknown_models", "warnings", "generation", "generation_source", "roles"}
      and RP["seat_substitutions"] == [] and RP["rejected_env"] == [] and RP["unknown_models"] == []
      and RP["panel_duplicate_models"] == [] and RP["panel"] == P)
RP = m.resolve_panel(env={"WITT_JUDGE_GROUNDING": "claude-sonnet-5"}, today=T)
check("(D) mismo modelo en DOS lentes distintas NO se rechaza: se DECLARA en panel_duplicate_models ['claude-sonnet-5'] "
      "(reviewer_source 'env:WITT_JUDGE_GROUNDING'; sin retirement-due porque haiku ya no es efectivo)",
      RP["panel_duplicate_models"] == ["claude-sonnet-5"] and RP["rejected_env"] == []
      and RP["panel"][2]["reviewer_source"] == "env:WITT_JUDGE_GROUNDING"
      and not any(w.startswith("retirement-due:") for w in RP["warnings"]))
RP = m.resolve_panel(env={"WITT_JUDGE_CORRECTNESS": "claude-sonnet-5", "WITT_JUDGE_OVERCLAIM": "claude-opus-5",
                          "WITT_JUDGE_GROUNDING": "claude-sonnet-5", "OPENAI_JUDGE_MODEL": "gpt-6-astra"}, today=T)
check("same-model-same-lens: está en INVALID_ENV_REASONS pero es INALCANZABLE hoy (una lente por asiento fija): 4 asientos por "
      "env, 2 duplicados de modelo, 0 rechazos — declarado, no disimulado",
      "same-model-same-lens" in m.INVALID_ENV_REASONS and RP["rejected_env"] == []
      and RP["panel_duplicate_models"] == ["claude-sonnet-5"]
      and all(x["reviewer_source"].startswith("env:") for x in RP["panel"]))
RP = m.resolve_panel(env={"OPENAI_JUDGE_MODEL": "gpt-7-nova", "WITT_MODEL_SYNTH": "llama-9"}, today=T)
check("resolve_panel/unknown_models: [{role, model, family, family_source}] para cada id desconocido en efecto (incluye roles del pipeline)",
      RP["unknown_models"] == [{"role": "synthesizer", "model": "llama-9", "family": "unknown", "family_source": "prefix"},
                               {"role": "judge.reproducibility", "model": "gpt-7-nova", "family": "openai", "family_source": "prefix"}],
      f"{RP['unknown_models']}")
RP = m.resolve_panel(env={"WITT_MODEL_SYNTH": "claude-fable-5-1", "WITT_MODEL_GENERATION": "g7"}, today=T)
check("warnings 'invalid-env:' — generación inválida y rechazo de fable, con el default que se usó; rejected_env lo estructura",
      RP["warnings"][0] == "invalid-env: WITT_MODEL_GENERATION=g7 (unknown-generation) — se usa default g2-2026-09"
      and RP["warnings"][1] == "invalid-env: WITT_MODEL_SYNTH=claude-fable-5-1 (excluded-model) — se usa default:g2-2026-09 claude-opus-5 en synthesizer"
      and RP["rejected_env"] == [{"role": "synthesizer", "env": "WITT_MODEL_SYNTH", "value": "claude-fable-5-1",
                                  "reason": "excluded-model", "fallback": "claude-opus-5"}], f"{RP['warnings']}")
mf = m.member_for("gpt-4o", "reproducibility", env={}, today=T)
check("member_for(model, lens): PanelMember con reviewer_source 'caller' (para smoke_live_models --model y run_held_out)",
      tuple(mf) == m.PANEL_MEMBER_FIELDS and mf["reviewer"] == "gpt-4o" and mf["reviewer_source"] == "caller"
      and mf["api"] == "openai-chat-completions" and mf["max_tokens"] is None
      and m.member_for("claude-opus-5", "correctness", env={}, today=T)["max_tokens"] == 4000)

# =====================================================================================================
# 7. Retiro de haiku (E) con `today` inyectado
# =====================================================================================================
due = m.retirement_due(env={}, today=T)
EXPECTED_DUE = ("retirement-due: claude-haiku-4-5-20251001 en judge.evidence-grounding (retire_not_before 2026-10-15, "
                "faltan 30 días; sucesor declarado claude-sonnet-5 — fijar WITT_JUDGE_GROUNDING=claude-sonnet-5 o WITT_PANEL_AUTO_RETIRE=1)")
check("retirement_due(today=2026-09-15): UN aviso MEDIDO, days_left 30, texto EXACTO del ADR (E)",
      len(due) == 1 and due[0]["days_left"] == 30 and due[0]["warning"] == EXPECTED_DUE
      and due[0]["role"] == "judge.evidence-grounding" and due[0]["successor"] == "claude-sonnet-5",
      f"{[d['warning'] for d in due]}")
check("retirement_due: fuera de la ventana (2026-08-15) → []; el día del retiro (2026-10-15) → [] y past_retirement → 1 fila days_past 0",
      m.retirement_due(env={}, today="2026-08-15") == [] and m.retirement_due(env={}, today="2026-10-15") == []
      and len(m.past_retirement(env={}, today="2026-10-15")) == 1
      and m.past_retirement(env={}, today="2026-10-15")[0]["days_past"] == 0
      and m.past_retirement(env={}, today=T) == [])
past = m.past_retirement(env={}, today="2026-10-20")
check("past_retirement(2026-10-20, AUTO_RETIRE=0 default): haiku SIGUE en el asiento (nada cambia solo) y avisa 'past-retirement: … hace 5 días …'",
      len(past) == 1 and past[0]["days_past"] == 5 and past[0]["warning"].startswith("past-retirement: claude-haiku-4-5-20251001 en judge.evidence-grounding (retire_not_before 2026-10-15, hace 5 días;")
      and m.panel(env={}, today="2026-10-20")[2]["reviewer"] == "claude-haiku-4-5-20251001")
RP = m.resolve_panel(env={"WITT_PANEL_AUTO_RETIRE": "1"}, today="2026-10-15")
check("AUTO_RETIRE=1 y today >= retire_not_before → el asiento se sustituye: reviewer sonnet-5, reviewer_source "
      "'auto-retire:claude-haiku-4-5-20251001->claude-sonnet-5', seat_substitutions exacto, panel_duplicate_models ['claude-sonnet-5'], "
      "sin aviso de retiro (la sustitución es la huella)",
      RP["panel"][2]["reviewer"] == "claude-sonnet-5"
      and RP["panel"][2]["reviewer_source"] == "auto-retire:claude-haiku-4-5-20251001->claude-sonnet-5"
      and RP["seat_substitutions"] == [{"seat": "evidence-grounding", "retired": "claude-haiku-4-5-20251001",
                                        "retire_not_before": "2026-10-15", "successor": "claude-sonnet-5", "applied": True}]
      and RP["panel_duplicate_models"] == ["claude-sonnet-5"]
      and not any(w.startswith(("retirement-due:", "past-retirement:")) for w in RP["warnings"])
      and m.past_retirement(env={"WITT_PANEL_AUTO_RETIRE": "1"}, today="2026-10-15") == [], f"{RP['seat_substitutions']} {RP['warnings']}")
RP = m.resolve_panel(env={"WITT_PANEL_AUTO_RETIRE": "1"}, today="2026-10-14")
check("AUTO_RETIRE=1 un día ANTES → nada se sustituye; retirement-due con faltan 1 día",
      RP["seat_substitutions"] == [] and RP["panel"][2]["reviewer"] == "claude-haiku-4-5-20251001"
      and any("faltan 1 días" in w for w in RP["warnings"]))
RP = m.resolve_panel(env={"WITT_PANEL_AUTO_RETIRE": "1", "WITT_JUDGE_GROUNDING": "claude-haiku-4-5-20251001"}, today="2026-10-20")
check("AUTO_RETIRE=1 pero la env PINEA haiku explícitamente → el ACTO del operador no se sustituye; past-retirement avisa",
      RP["seat_substitutions"] == [] and RP["panel"][2]["reviewer_source"] == "env:WITT_JUDGE_GROUNDING"
      and any(w.startswith("past-retirement:") for w in RP["warnings"]))
check("panel signature cambia con el auto-retire (ADR-0087 segmenta por firma)",
      m.resolve_panel(env={"WITT_PANEL_AUTO_RETIRE": "1"}, today="2026-10-15")["panel_signature"]
      != m.resolve_panel(env={}, today="2026-10-15")["panel_signature"])

# =====================================================================================================
# 8. relation · thinking_state
# =====================================================================================================
check("relation: exact | prefix (alias→snapshot fechado) | different (también el prefijo inverso) | not-reported (None y '')",
      m.relation("claude-opus-5", "claude-opus-5") == "exact"
      and m.relation("claude-opus-5", "claude-opus-5-20260901") == "prefix"
      and m.relation("gpt-4o", "gpt-4o-2024-08-06") == "prefix"
      and m.relation("claude-opus-5", "claude-sonnet-5") == "different"
      and m.relation("claude-opus-5-20260901", "claude-opus-5") == "different"
      and m.relation("claude-opus-5", None) == "not-reported" and m.relation("claude-opus-5", "") == "not-reported"
      and set(m.RELATIONS) == {"exact", "prefix", "different", "not-reported"})
check("thinking_state por tabla (C.4): opus-5 'adaptive-by-api-default (tokens dentro de output_tokens)' · opus-4-8 "
      "'off-by-model-default' · gpt-4o not-applicable · desconocido 'unknown-to-table'",
      m.thinking_state("claude-opus-5") == "adaptive-by-api-default (tokens dentro de output_tokens)"
      and m.thinking_state("claude-opus-4-8") == "off-by-model-default"
      and m.thinking_state("gpt-4o").startswith("not-applicable") and m.thinking_state("llama-9") == "unknown-to-table")

# =====================================================================================================
# 9. snapshot (I)
# =====================================================================================================
S = m.snapshot(env={}, today=T)
check("snapshot: fields == SNAPSHOT_FIELDS (28, cerrada, en orden) y cada campo es exactamente {value, source}",
      tuple(S["fields"]) == m.SNAPSHOT_FIELDS and len(m.SNAPSHOT_FIELDS) == 28
      and all(set(c) == {"value", "source"} for c in S["fields"].values()))
F = S["fields"]
check("snapshot env vacía: defaults TIPADOS con fuente 'default-unset:' — min_families 2 · min_lenses 3 · auto_retire False · openai.api "
      "'table' · store False · max_output_tokens 4000 · timeout_s 120 · reasoning_effort None · anthropic.effort None · judge.retries 1 · "
      "prices.as_of '2026-09' · embed.model text-embedding-3-small 'default:table(embed)'",
      F["panel.min_families"] == {"value": 2, "source": "default-unset:WITT_PANEL_MIN_FAMILIES"}
      and F["panel.min_lenses"] == {"value": 3, "source": "default-unset:WITT_PANEL_MIN_LENSES"}
      and F["panel.auto_retire"] == {"value": False, "source": "default-unset:WITT_PANEL_AUTO_RETIRE"}
      and F["openai.api"] == {"value": "table", "source": "default-unset:WITT_OPENAI_API"}
      and F["openai.store"]["value"] is False and F["openai.max_output_tokens"]["value"] == 4000
      and F["openai.timeout_s"]["value"] == 120 and F["openai.reasoning_effort"]["value"] is None
      and F["anthropic.effort"]["value"] is None and F["anthropic.effort_elicit"]["value"] is None
      and F["judge.retries"] == {"value": 1, "source": "default-unset:WITT_JUDGE_RETRIES"}
      and F["prices.as_of"] == {"value": "2026-09", "source": "models.PRICES_AS_OF"}
      and F["embed.model"] == {"value": "text-embedding-3-small", "source": "default:table(embed)"}
      and F["model_generation"] == {"value": "g2-2026-09", "source": "default-unset:WITT_MODEL_GENERATION"}
      and F["table_version"]["value"] == "g2-2026-09" and F["panel_signature"]["value"] == sig0
      and F["role.synthesizer"] == {"value": "claude-opus-5", "source": "default:g2-2026-09"}
      and F["panel.reproducibility"] == {"value": "gpt-4o", "source": "default:g2-2026-09"}, f"{json.dumps(F, ensure_ascii=False)[:600]}")
check("snapshot: los 4 EXTRA_FIELDS (contract.render_contract_version, competence.gate, search.harness, revision.cycle) sin `extra` → "
      "{None, 'not-provided-by-caller'} (null declarado, no un default duplicado de otro módulo)",
      all(F[k] == {"value": None, "source": "not-provided-by-caller"} for k in m.EXTRA_FIELDS)
      and set(m.EXTRA_FIELDS) == {"contract.render_contract_version", "competence.gate", "search.harness", "revision.cycle"})
S2 = m.snapshot(env={}, today=T, extra={"contract.render_contract_version": {"value": "1.10", "source": "runs.RENDER_CONTRACT_VERSION"},
                                          "competence.gate": {"value": True, "source": "competence.env_config"},
                                          "role.synthesizer": {"value": "hack", "source": "x"}, "ruido": {"value": 1}})
check("snapshot(extra=…): los EXTRA_FIELDS entran con su fuente; intentar sobreescribir un campo propio o una llave desconocida se "
      "IGNORA y se declara en extra_ignored",
      S2["fields"]["contract.render_contract_version"] == {"value": "1.10", "source": "runs.RENDER_CONTRACT_VERSION"}
      and S2["fields"]["competence.gate"] == {"value": True, "source": "competence.env_config"}
      and S2["fields"]["role.synthesizer"]["value"] == "claude-opus-5" and S2["extra_ignored"] == ["role.synthesizer", "ruido"])
S3 = m.snapshot(env={"WITT_PANEL_MIN_FAMILIES": "abc", "WITT_PANEL_MIN_LENSES": "0", "WITT_OPENAI_REASONING_EFFORT": "ultra",
                     "WITT_OPENAI_STORE": "1", "WITT_ANTHROPIC_EFFORT": "LOW", "WITT_OPENAI_TIMEOUT_S": "-5",
                     "WITT_PANEL_AUTO_RETIRE": "yes", "WITT_OPENAI_MAX_OUTPUT_TOKENS": "8000", "WITT_JUDGE_RETRIES": "0"}, today=T)
F3 = S3["fields"]
check("lectores tolerantes: basura → default con 'default-invalid-env:'; 0 en MIN_LENSES es kill-switch VÁLIDO ('env:'); "
      "effort se normaliza a minúsculas; negativos inválidos; retries 0 válido",
      F3["panel.min_families"] == {"value": 2, "source": "default-invalid-env:WITT_PANEL_MIN_FAMILIES"}
      and F3["panel.min_lenses"] == {"value": 0, "source": "env:WITT_PANEL_MIN_LENSES"}
      and F3["openai.reasoning_effort"] == {"value": None, "source": "default-invalid-env:WITT_OPENAI_REASONING_EFFORT"}
      and F3["openai.store"] == {"value": True, "source": "env:WITT_OPENAI_STORE"}
      and F3["anthropic.effort"] == {"value": "low", "source": "env:WITT_ANTHROPIC_EFFORT"}
      and F3["openai.timeout_s"] == {"value": 120, "source": "default-invalid-env:WITT_OPENAI_TIMEOUT_S"}
      and F3["panel.auto_retire"] == {"value": False, "source": "default-invalid-env:WITT_PANEL_AUTO_RETIRE"}
      and F3["openai.max_output_tokens"] == {"value": 8000, "source": "env:WITT_OPENAI_MAX_OUTPUT_TOKENS"}
      and F3["judge.retries"] == {"value": 0, "source": "env:WITT_JUDGE_RETRIES"}, f"{json.dumps(F3, ensure_ascii=False)[:500]}")
SECRET_ENV = {"OPENAI_API_KEY": "sk-proj-SECRETO1234567890abcdefghijklmnop", "ANTHROPIC_API_KEY": "sk-ant-SECRETO",
              "WITT_MODEL_SYNTH": "sk-live-SECRETOenUnModelo", "OPENAI_EMBED_MODEL": "my_api_key_SECRETO"}
S4 = m.snapshot(env=SECRET_ENV, today=T)
_dump = json.dumps(S4, ensure_ascii=False)
check("snapshot JAMÁS lleva una llave: env con OPENAI_API_KEY/ANTHROPIC_API_KEY (no se leen) y valores con forma de llave en envs "
      "de modelo → RECHAZO 'secret-like-value' (jamás se usa como `model` ni se echa el valor): role.synthesizer = default con "
      "'default-invalid-env:WITT_MODEL_SYNTH (secret-like-value)', embed.model = default de tabla, rejected_env.value redactado; "
      "el dump completo no contiene 'SECRETO' ni 'sk-'",
      "SECRETO" not in _dump and "sk-" not in _dump
      and S4["fields"]["role.synthesizer"] == {"value": "claude-opus-5", "source": "default-invalid-env:WITT_MODEL_SYNTH (secret-like-value)"}
      and S4["fields"]["embed.model"] == {"value": "text-embedding-3-small", "source": "default-invalid-env:OPENAI_EMBED_MODEL (secret-like-value)"}
      and S4["rejected_env"] == [{"role": "synthesizer", "env": "WITT_MODEL_SYNTH", "value": "<redactado: parece llave>",
                                  "reason": "secret-like-value", "fallback": "claude-opus-5"}]
      and S4["unknown_models"] == [] and "secret-like-value" in m.INVALID_ENV_REASONS, _dump[:300])
check("snapshot: warnings y unknown_models viajan (retirement-due hoy; api-unverified de opus-5 hasta LG1); llaves top-level cerradas",
      any(w == EXPECTED_DUE for w in S["warnings"]) and any(w.startswith("api-unverified: claude-opus-5") for w in S["warnings"])
      and all(w.startswith(m.WARNING_PREFIXES) for w in S["warnings"])
      and set(S) == {"generation", "generation_source", "table_version", "table_as_of", "panel_signature", "today", "fields",
                     "roles", "panel", "panel_source", "seat_substitutions", "panel_duplicate_models", "rejected_env",
                     "warnings", "unknown_models", "extra_ignored"} and S["today"] == T and set(S["roles"]) == set(m.ROLES),
      f"{S['warnings']}")
try:
    from lib import composite_auditor as _ca  # noqa: E402
    check("defaults compartidos MEDIDOS: composite_auditor.JUDGE_RETRIES_DEFAULT == int(ENV_TABLE['WITT_JUDGE_RETRIES'].default) y "
          "JUDGE_RETRIES_ENV == 'WITT_JUDGE_RETRIES' (models.py no duplica en silencio el default del dueño)",
          _ca.JUDGE_RETRIES_DEFAULT == int(m.ENV_TABLE["WITT_JUDGE_RETRIES"]["default"]) and _ca.JUDGE_RETRIES_ENV == "WITT_JUDGE_RETRIES")
except Exception as e:   # pragma: no cover
    check("import composite_auditor offline", False, f"{type(e).__name__}: {e}")
    _ca = None
try:
    m.env_value("WITT_NADA", env={})
    check("env_value: env no declarada → KeyError", False, "no lanzó")
except KeyError:
    check("env_value: env no declarada en ENV_TABLE → KeyError (nadie lee una env que la tabla no conoce)", True)

# =====================================================================================================
# 10. provenance_block (B) con stubs
# =====================================================================================================
roles_env = {"WITT_MODEL_ELICIT": "claude-sonnet-5"}
ROLES_RUN = {"synthesizer": m.resolve_role("synthesizer", env=roles_env, today=T),
             "elicitation": m.resolve_role("elicitation", env=roles_env, today=T)}
PASSES = [("pass1", {"model": "claude-opus-5", "model_reported": None, "usage": {"input_tokens": 1, "output_tokens": 1},
                     "usage_elicitation": None}),                               # stub: nada reportado; elicitación intentada y fallida
          ("pass2", {"model": "claude-opus-5", "model_reported": "claude-opus-5-20260901", "usage": {},
                     "usage_elicitation": {"input_tokens": 1, "output_tokens": 1},
                     "elicitation_model": "claude-sonnet-5", "elicitation_model_reported": "claude-sonnet-5"}),
          ("revision", {"model": "claude-opus-5", "model_reported": "claude-sonnet-5", "usage": {}})]   # sin elicitación
PANEL_ROWS = [
    {"reviewer": "claude-opus-5", "family": "anthropic", "lens": "correctness", "api": "anthropic-messages", "verdict": "APPROVE",
     "attempts": [{"attempt": 1, "status": "ok", "model_reported": "claude-opus-5-20260901", "api": "anthropic-messages"}]},
    {"reviewer": "claude-sonnet-5", "family": "anthropic", "lens": "overclaim", "verdict": "APPROVE"},          # fila legada sin api ni attempts
    {"reviewer": "claude-haiku-4-5-20251001", "family": "anthropic", "lens": "evidence-grounding", "api": "anthropic-messages",
     "status": "errored", "error": "network error: x",
     "attempts": [{"attempt": 1, "status": "errored", "error": "x"}, {"attempt": 2, "status": "errored", "error": "x"}]},
    {"reviewer": "gpt-4o", "family": "openai", "lens": "reproducibility", "api": "openai-chat-completions", "verdict": "REVISE",
     "model_reported": "gpt-4o-2024-08-06", "attempts": [{"attempt": 1, "status": "ok"}]},
]
B = m.provenance_block(ROLES_RUN, PASSES, {"model": "claude-opus-4-8", "usage": {"input_tokens": 3, "output_tokens": 2}}, PANEL_ROWS)
check("provenance_block: llaves top-level == PROVENANCE_FIELDS; roles {synthesizer, elicitation, question_agent null, planner}; "
      "ran {synthesize_pass1/2, revision, elicit_pass1/2, plan, question, panel}; generation copiada del rol resuelto",
      tuple(B) == m.PROVENANCE_FIELDS and set(B["roles"]) == {"synthesizer", "elicitation", "question_agent", "planner"}
      and B["roles"]["question_agent"] is None and B["roles"]["synthesizer"] == ROLES_RUN["synthesizer"]
      and B["roles"]["elicitation"]["source"] == "env:WITT_MODEL_ELICIT"
      and set(B["ran"]) == {"synthesize_pass1", "synthesize_pass2", "revision", "elicit_pass1", "elicit_pass2", "plan", "question", "panel"}
      and B["generation"] == "g2-2026-09" and B["table_version"] == "g2-2026-09" and B["table_as_of"] == "2026-09-15"
      and B["ran"]["question"] is None and B["rule"] == m.PROVENANCE_RULE)
R_ = B["ran"]
check("ran.*: Ran = {requested, reported, relation, thinking_state} — pass1 stub → not-reported · pass2 alias fechado → prefix (NEUTRO) · "
      "revision otro modelo → different (objeción) · elicit_pass1 intentada y fallida → Ran not-reported · elicit_pass2 exact · "
      "thinking_state por tabla",
      all(tuple(R_[k]) == m.RAN_FIELDS for k in ("synthesize_pass1", "synthesize_pass2", "revision", "elicit_pass1", "elicit_pass2", "plan"))
      and R_["synthesize_pass1"] == {"requested": "claude-opus-5", "reported": None, "relation": "not-reported",
                                     "thinking_state": "adaptive-by-api-default (tokens dentro de output_tokens)"}
      and R_["synthesize_pass2"]["relation"] == "prefix" and R_["revision"]["relation"] == "different"
      and R_["elicit_pass1"]["relation"] == "not-reported" and R_["elicit_pass1"]["requested"] == "claude-sonnet-5"
      and R_["elicit_pass2"] == {"requested": "claude-sonnet-5", "reported": "claude-sonnet-5", "relation": "exact",
                                 "thinking_state": "adaptive-by-api-default (tokens dentro de output_tokens)"}, f"{R_}")
check("roles.planner COPIADO de plan_json.judgment.planner sin 'model_source' → provenance 'plan_json (pre-1.10: source not recorded)', "
      "model opus-4-8 (un plan viejo con síntesis opus-5 es la verdad, no un bug); ran.plan thinking 'off-by-model-default'",
      B["roles"]["planner"] == {"model": "claude-opus-4-8", "model_source": None, "provenance": "plan_json (pre-1.10: source not recorded)"}
      and R_["plan"] == {"requested": "claude-opus-4-8", "reported": None, "relation": "not-reported", "thinking_state": "off-by-model-default"})
B2 = m.provenance_block(ROLES_RUN, PASSES, None, PANEL_ROWS)
B3 = m.provenance_block(ROLES_RUN, PASSES, {"model": "claude-opus-5", "model_source": "default:g2-2026-09",
                                            "model_reported": "claude-opus-5-20260901"}, PANEL_ROWS,
                        question_meta={"model": "claude-opus-5", "model_reported": None})
check("planner en sus 3 estados: sin plan → {None, None, 'no-plan'} y ran.plan null · plan 1.10 con model_source → 'plan_json' y ran.plan "
      "prefix · question_meta → ran.question Ran (not-reported)",
      B2["roles"]["planner"] == {"model": None, "model_source": None, "provenance": "no-plan"} and B2["ran"]["plan"] is None
      and B3["roles"]["planner"] == {"model": "claude-opus-5", "model_source": "default:g2-2026-09", "provenance": "plan_json"}
      and B3["ran"]["plan"]["relation"] == "prefix"
      and B3["ran"]["question"] == {"requested": "claude-opus-5", "reported": None, "relation": "not-reported",
                                    "thinking_state": "adaptive-by-api-default (tokens dentro de output_tokens)"}
      and set(m.PLANNER_PROVENANCES) == {"plan_json", "plan_json (pre-1.10: source not recorded)", "no-plan"})
PR = R_["panel"]
check("ran.panel: [{lens, reviewer, reported, relation, api_used, attempts}] — reported desde attempts[] cuando la fila no lo trae; fila "
      "legada sin api/attempts → api_used None, attempts None, not-reported; juez errado → not-reported con 2 intentos; gpt-4o prefix",
      all(tuple(x) == m.PANEL_RAN_FIELDS for x in PR) and len(PR) == 4
      and PR[0] == {"lens": "correctness", "reviewer": "claude-opus-5", "reported": "claude-opus-5-20260901", "relation": "prefix",
                    "api_used": "anthropic-messages", "attempts": 1}
      and PR[1] == {"lens": "overclaim", "reviewer": "claude-sonnet-5", "reported": None, "relation": "not-reported",
                    "api_used": None, "attempts": None}
      and PR[2]["relation"] == "not-reported" and PR[2]["attempts"] == 2
      and PR[3] == {"lens": "reproducibility", "reviewer": "gpt-4o", "reported": "gpt-4o-2024-08-06", "relation": "prefix",
                    "api_used": "openai-chat-completions", "attempts": 1}, f"{PR}")
check("provenance_block.panel_signature == models.panel_signature(panel g2, roles) cuando las filas son el panel g2 (costura (N))",
      B["panel_signature"] == m.panel_signature(P, ROLES_RUN))
B4 = m.provenance_block(ROLES_RUN, {"pass1": PASSES[0][1]}, None, [])
check("provenance_block acepta passes como dict; pasadas ausentes → null declarado; panel vacío → []",
      B4["ran"]["synthesize_pass2"] is None and B4["ran"]["revision"] is None and B4["ran"]["elicit_pass2"] is None
      and B4["ran"]["panel"] == [] and B4["ran"]["synthesize_pass1"]["relation"] == "not-reported")

# =====================================================================================================
# 11. models.py: sólo stdlib, sin `from lib import`, FAILURE-agnóstico
# =====================================================================================================
MODELS_PY = ROOT / "analysis" / "scripts" / "lib" / "models.py"
_src = MODELS_PY.read_text(encoding="utf-8")
_tree = ast.parse(_src)
_imports = set()
for node in ast.walk(_tree):
    if isinstance(node, ast.Import):
        _imports.update(a.name.split(".")[0] for a in node.names)
    elif isinstance(node, ast.ImportFrom):
        _imports.add((node.module or "").split(".")[0])
_stdlib = getattr(sys, "stdlib_module_names", set())
check("models.py: SÓLO stdlib (ast: todos los imports ∈ sys.stdlib_module_names) y ningún 'lib' importado",
      _imports and all(i in _stdlib for i in _imports) and "lib" not in _imports
      and not re.search(r"^\s*(from|import)\s+lib\b", _src, re.M), f"imports={sorted(_imports)}")
_FAILURE_KINDS = ("no-api-key", "sdk-unavailable", "arguments-unparseable", "verdict-off-vocabulary",
                  "incomplete:max_output_tokens", "incomplete:content_filter", "no-function-call", "error_kind", "CallerError")


def _code_strings(tree):
    """Constantes str del CÓDIGO (excluye docstrings de módulo/función/clase): lo que el módulo EMITE, no lo que explica."""
    doc_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                doc_ids.add(id(first.value))
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in doc_ids]


_code_strs = _code_strings(_tree)
_present = sorted({k for k in _FAILURE_KINDS for s in _code_strs if k in s})
check("models.py FAILURE-agnóstico: ningún kind del vocabulario de fallos de S2 (ni 'error_kind'/'CallerError') en las constantes "
      "str del CÓDIGO (ast, docstrings excluidos) ni en nombres — los kinds nacen en composite_auditor",
      not _present and "CallerError" not in re.sub(r'""".*?"""', "", _src, flags=re.S), f"present={_present}")

# =====================================================================================================
# 12. Grep estático: literales de modelo FUERA de models.py (PASS sólo con lista vacía; hoy FALLA — esperado hasta S7)
# =====================================================================================================
_ids = sorted(m.MODELS, key=len, reverse=True)
_LIT = re.compile("|".join([re.escape(i) for i in _ids] + [r"claude-[a-z]+-[0-9]", r"gpt-[0-9]", r"text-embedding-3-[a-z]+"]))
_SCOPE = [ROOT / "analysis" / "scripts", ROOT / "rag_index" / "query_service", ROOT / "evaluation"]
_EXEMPT_FILES = {MODELS_PY.resolve(), Path(__file__).resolve()}   # la tabla y este golden
_EXEMPT_MARK = "# models-literal-doc"


def _literal_offenders():
    out = []
    for base in _SCOPE:
        for f in sorted(base.rglob("*.py")):
            if f.resolve() in _EXEMPT_FILES or "__pycache__" in f.parts:
                continue
            for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if _EXEMPT_MARK in line:
                    continue
                if _LIT.search(line):
                    out.append(f"{f.relative_to(ROOT).as_posix()}:{n}")
    return out


_off = _literal_offenders()
_off_files = sorted({o.rsplit(":", 1)[0] for o in _off})
check("GATE ESTÁTICO (M.4): cero literales de modelo fuera de models.py en analysis/scripts, rag_index/query_service y evaluation "
      "(exentos: models.py, este smoke, líneas '# models-literal-doc'; rag_index/graphrag FUERA de alcance: infra de embeddings de la "
      "DATA INAMOVIBLE). PASS sólo con lista VACÍA — hasta que S2/S3/S7 migren runs.py/composite_auditor.py/question_agent.py y sus "
      "smokes este check FALLA y ES lo esperado",
      not _off, f"{len(_off)} líneas en {len(_off_files)} archivos: " + "; ".join(_off_files))
if _off:
    for o in _off:
        print("       literal:", o)

# =====================================================================================================
# 13. openai en el venv · requirements.txt
# =====================================================================================================
try:
    import openai as _oai  # noqa: E402
    _v = tuple(int(x) for x in re.match(r"(\d+)\.(\d+)\.(\d+)", _oai.__version__).groups())
    check("venv de los gates: openai.__version__ >= 1.66 y la clase OpenAI expone `responses` (Responses API disponible sin instanciar cliente)",
          _v >= (1, 66, 0) and hasattr(_oai.OpenAI, "responses"), f"openai {_oai.__version__}")
except Exception as e:   # pragma: no cover
    check("venv de los gates: import openai", False, f"{type(e).__name__}: {e}")
for _k in [k for k in sys.modules if k == "openai" or k.startswith("openai.")]:
    sys.modules.pop(_k, None)
_req = (HERE / "requirements.txt").read_text(encoding="utf-8")
check("requirements.txt: 'openai>=1.66,<3' (un build con client.responses; sin 'openai>=1.40')",
      "openai>=1.66,<3" in _req and "openai>=1.40" not in _req)

# =====================================================================================================
# 14. evaluation/run_held_out.py toma panel y sintetizador de la tabla; juez OpenAI delega; familia desconocida erra
# =====================================================================================================
try:
    import run_held_out as rho  # noqa: E402
    check("run_held_out: JUDGE_PANEL == [(family, reviewer)] de models.panel() y SYNTH_MODEL == resolve_role('synthesizer').model "
          "(forma [(family, model)] conservada para run_held_out_v2.judge_answer)",
          rho.JUDGE_PANEL == [(x["family"], x["reviewer"]) for x in m.panel()]
          and rho.SYNTH_MODEL == m.resolve_role("synthesizer")["model"] == "claude-opus-5"
          and rho._SYNTH_ROLE["max_tokens"] == 8000)
    _seen = {}

    def _fake_default_caller(member, system, user_text, tool=None):
        _seen.update({"member": member, "tool": tool, "system": system})
        return ({"overall_score": 0.7, "verdict": "correct", "justification": "fake"},
                {"input_tokens": 1, "output_tokens": 1}, {"model_reported": "gpt-4o-2024-08-06", "api": "openai-chat-completions"})

    _orig = _ca._default_caller if _ca else None
    if _ca:
        _ca._default_caller = _fake_default_caller
        try:
            v, u = rho.openai_verdict("gpt-4o", "SYS", "USER", rho.VERDICT_TOOL)
        finally:
            _ca._default_caller = _orig
        check("run_held_out.openai_verdict DELEGA en composite_auditor._default_caller(member, system, user_text, tool=) con la firma de S2: "
              "member = PanelMember de la tabla (gpt-4o · reproducibility · openai-chat-completions), tool = el VERDICT_TOOL de "
              "run_held_out (emit_verdict, NO el del panel), meta → _model_reported/_api",
              _seen["tool"] is rho.VERDICT_TOOL and _seen["member"]["reviewer"] == "gpt-4o"
              and _seen["member"]["lens"] == "reproducibility" and _seen["member"]["api"] == "openai-chat-completions"
              and _seen["member"]["reviewer_source"] == "caller" and v["verdict"] == "correct"
              and v["_model_reported"] == "gpt-4o-2024-08-06" and v["_api"] == "openai-chat-completions"
              and u == {"input_tokens": 1, "output_tokens": 1}, f"{_seen.get('member')}")
        _caller_now, _accepts_now = rho._default_caller_accepts_tool()
        print(f"       info: composite_auditor._default_caller acepta tool= HOY: {_accepts_now} "
              f"({'delegación ACTIVA' if _accepts_now else 'camino legado chat.completions declarado hasta S2'})")
        check("run_held_out._default_caller_accepts_tool(): (callable, bool) — import perezoso de composite_auditor",
              callable(_caller_now) and isinstance(_accepts_now, bool))
    try:
        rho._judge_call("unknown", "llama-9", "SYS", "USER")
        check("run_held_out._judge_call: familia desconocida erra en voz alta", False)
    except RuntimeError as e:
        check("run_held_out._judge_call: familia desconocida → RuntimeError 'unknown-family …' SIN llamar a ninguna API "
              "(no el `else: anthropic` de f57a3d3)", "unknown-family" in str(e) and not _NET_CALLS)
    _cap = {}
    _orig_atc = rho.anthropic_tool_call

    def _fake_atc(model, system, user_text, tool, max_tokens=2000, timeout=120, retries=1):
        _cap.update({"model": model, "max_tokens": max_tokens, "tool": tool})
        return {"overall_score": 0.5, "verdict": "partial", "justification": "fake"}, {}

    rho.anthropic_tool_call = _fake_atc
    try:
        rho._judge_call("anthropic", "claude-opus-5", "SYS", "USER")
    finally:
        rho.anthropic_tool_call = _orig_atc
    check("run_held_out._judge_call anthropic: pasa el TOPE del asiento de la tabla (g2 judge-anthropic 4000, antes 1200 fijo) y el VERDICT_TOOL propio",
          _cap == {"model": "claude-opus-5", "max_tokens": 4000, "tool": rho.VERDICT_TOOL})
except Exception as e:   # pragma: no cover
    check("import evaluation/run_held_out.py offline (sin llaves)", False, f"{type(e).__name__}: {e}")
_ab = (ROOT / "evaluation" / "scripts" / "ab_trapped_scalar.py").read_text(encoding="utf-8")
check("evaluation/scripts/ab_trapped_scalar.py SIN cambio: sigue leyendo el alias runs_mod.SYNTH_MODEL (>= 4 lecturas) y no tiene literal de modelo",
      _ab.count("runs_mod.SYNTH_MODEL") >= 4 and not _LIT.search(_ab))

# =====================================================================================================
# 15. Cero red · sys.modules sin openai
# =====================================================================================================
check("la sección corrió 100% OFFLINE — MEDIDO: urllib.request.urlopen bloqueado y contado == 0",
      _NET_CALLS == [], f"calls={_NET_CALLS}")
check("sys.modules sin 'openai' al terminar (el smoke no deja el SDK cargado)",
      not any(k == "openai" or k.startswith("openai.") for k in sys.modules))
_urlreq.urlopen = _urlopen_real

n_ok = sum(CHECKS)
print(f"\n== {n_ok}/{len(CHECKS)} PASS ==")
sys.exit(0 if n_ok == len(CHECKS) else 1)

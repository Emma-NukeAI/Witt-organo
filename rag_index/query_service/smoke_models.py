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
(15) cero red: `urllib.request.urlopen` bloqueado y CONTADO (== 0); `sys.modules` sin `openai` al terminar;
(16) ADR-0082 (D.2, rebanada C3): rol `council` FUERA de PIPELINE_ROLES — `resolve_role('council')` g2 opus-5 / g1
opus-4-8 (declarado) con fuente, `WITT_MODEL_COUNCIL` respetado, fable → excluded-model, gpt-* → wrong-family-for-role,
tope `max_tokens.council` 4000/1200; `panel_signature` byte-IGUAL al GOLDEN @ 9d90c01 con y sin el rol (y con
WITT_MODEL_COUNCIL pineado / WITT_COUNCIL=0); `snapshot().fields` 35 con `role.council` y `council.*` sin secretos;
`council_effort()` (default medium, `inherit` declarado); kinds `bool`/`float` tolerantes y PARIDAD de literales con
agent_matrix.council_full y catalog_cards.cache_config (C1); `CACHE_MULTIPLIERS` con fuente/fecha y `cache_prices()` =
1.25×/2×/0.1× de `prices()`; ENV_TABLE 68 = 21 (ADR-0081) + 27 (ENV_ADR_0082) + 20 (ENV_ADR_0083); compose ∩ README ⊇
ENV_TABLE en TRES checks: las 21 de ADR-0081 y las 27 de ADR-0082 (PASS hoy) y las 20 de ADR-0083 (FALLA hasta que F7 entregue
compose/README — esperado y declarado, patrón del gate M.4);
(17) ADR-0083 (G.4 / H / M.4 / O.5, rebanada F3): columnas `vision_tier` ∈ VISION_TIERS / `vision_multiplier` / `vision_verified`
(False en TODAS) por fila y coherentes con la familia; `vision_tokens` == los ejemplos PÚBLICOS del ADR (1000² → 1296 en ambos
tiers; 1920×1080 → 1560 estándar / 2691 alto; 2000×1500 → 1564/3888; 3840×2160 → 4784 = tope; puente 750×417 → 425 y 738×840 →
765; candidato 750×417 → ⌈336×1.2⌉ = 404; low → 85; embed/desconocido → None); `panel_signature` INTACTA (golden 9d90c01) con
WITT_FIGURES=0/1; `snapshot().fields` += figures.enabled/figures.vision con fuente; ENV_ADR_0083 (20) con los MISMOS defaults
que figures.ENV_SPECS (paridad medida); clamps `maximum`/`minimum` de env_value.

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
check("tabla: forma CERRADA por fila (MODEL_ROW_FIELDS, 16 llaves = 13 de ADR-0081 + vision_tier/vision_multiplier/vision_verified "
      "de ADR-0083, retire_not_before/successor siempre presentes) y "
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
# ADR-0082 (D.2): el rol `council` — opus-5 / 4000 en g2 (decisión de Emmanuel); opus-4-8 / 1200 en g1 DECLARADO (g1 no
# tenía consejo; la llave existe para que resolve_role('council') no lance bajo el kill-switch de generación).
G2_COUNCIL = ("claude-opus-5", 4000)
G1_COUNCIL = ("claude-opus-4-8", 1200)
# f57a3d3 byte a byte: runs.SYNTH_MODEL (L91) en synth/planner/elicit; question_agent.QUESTION_MODEL (L37);
# composite_auditor.DEFAULT_PANEL (L60-65); topes CONF_TOOL 300 · PLAN_TOOL 1200 · SYNTH_TOOL 2500 · QUESTION 1200 · jueces 1200.
G1_DEFAULTS = {**{r: "claude-opus-4-8" for r in ("synthesizer", "planner", "elicitation", "question_agent", "judge.correctness")},
               "judge.overclaim": "claude-sonnet-5", "judge.evidence-grounding": "claude-haiku-4-5-20251001",
               "judge.reproducibility": "gpt-4o"}
G1_TOPES = {"synthesizer": 2500, "planner": 1200, "elicitation": 300, "question_agent": 1200, "judge-anthropic": 1200}
F57_DEFAULT_PANEL = [("claude-opus-4-8", "anthropic", "correctness"), ("claude-sonnet-5", "anthropic", "overclaim"),
                     ("claude-haiku-4-5-20251001", "anthropic", "evidence-grounding"), ("gpt-4o", "openai", "reproducibility")]


def _sin_council(d):
    return {k: v for k, v in d.items() if k != "council"}


check("GENERATIONS: exactamente {g2-2026-09, g1-2026-08}; g2 defaults y TOPES de (A) + council opus-5 / 4000 (ADR-0082 D.2)",
      set(m.GENERATIONS) == {"g2-2026-09", "g1-2026-08"} and _sin_council(m.GENERATIONS["g2-2026-09"]["defaults"]) == G2_DEFAULTS
      and _sin_council(m.GENERATIONS["g2-2026-09"]["max_tokens"]) == G2_TOPES
      and (m.GENERATIONS["g2-2026-09"]["defaults"]["council"], m.GENERATIONS["g2-2026-09"]["max_tokens"]["council"]) == G2_COUNCIL)
check("GENERATIONS: g1-2026-08 == f57a3d3 byte a byte en los 8 defaults + 5 topes 2500·1200·300·1200·1200; la llave `council` "
      "(opus-4-8 / 1200) es DECLARADA por ADR-0082 — g1 no tenía consejo — y la nota lo dice",
      _sin_council(m.GENERATIONS["g1-2026-08"]["defaults"]) == G1_DEFAULTS and _sin_council(m.GENERATIONS["g1-2026-08"]["max_tokens"]) == G1_TOPES
      and (m.GENERATIONS["g1-2026-08"]["defaults"]["council"], m.GENERATIONS["g1-2026-08"]["max_tokens"]["council"]) == G1_COUNCIL
      and "council" in m.GENERATIONS["g1-2026-08"]["note"])
_all_defaults = {v for g in m.GENERATIONS.values() for v in g["defaults"].values()}
check("defaults g1/g2: 100% conocidos por la tabla y 100% cotizados (ningún default sin precio)",
      all(v in m.MODELS and v in m.prices() for v in _all_defaults)
      and all(set(g["defaults"]) == set(m.ROLES) and set(g["max_tokens"]) == set(m.MAX_TOKENS_KEYS) for g in m.GENERATIONS.values()),
      f"defaults={sorted(_all_defaults)}")
ENV_ADR_0081 = {"WITT_MODEL_GENERATION", "WITT_MODEL_SYNTH", "WITT_MODEL_PLANNER", "WITT_MODEL_ELICIT",
                "WITT_MODEL_QUESTION", "WITT_JUDGE_CORRECTNESS", "WITT_JUDGE_OVERCLAIM", "WITT_JUDGE_GROUNDING",
                "OPENAI_JUDGE_MODEL", "WITT_PANEL_AUTO_RETIRE", "WITT_PANEL_MIN_FAMILIES", "WITT_PANEL_MIN_LENSES",
                "WITT_OPENAI_API", "WITT_OPENAI_STORE", "WITT_OPENAI_MAX_OUTPUT_TOKENS",
                "WITT_OPENAI_REASONING_EFFORT", "WITT_OPENAI_TIMEOUT_S", "WITT_ANTHROPIC_EFFORT",
                "WITT_ANTHROPIC_EFFORT_ELICIT", "WITT_CONFIG_LEDGER", "WITT_JUDGE_RETRIES"}
# ADR-0082 tabla de env: las 27 nuevas (WITT_REAP_STALE_S ya existía y NO es de models.ENV_TABLE)
ENV_ADR_0082 = ("WITT_COUNCIL", "WITT_COUNCIL_FULL", "WITT_MODEL_COUNCIL", "WITT_COUNCIL_EFFORT", "WITT_CG_COUNCIL_COMPONENT",
                "WITT_COUNCIL_RECOVERAGE", "WITT_COUNCIL_ORIGINS", "WITT_COUNCIL_WORKERS", "WITT_COUNCIL_DEDUP_S",
                "WITT_COUNCIL_MAX_QUEUED_PER_USER", "WITT_COUNCIL_CONCURRENCY", "WITT_COUNCIL_MEMBER_TIMEOUT_S",
                "WITT_COUNCIL_ROUND_BUDGET_S", "WITT_COUNCIL_MEMBER_RETRIES", "WITT_COUNCIL_QUORUM",
                "WITT_COUNCIL_MAX_REQUIREMENTS", "WITT_COUNCIL_MAX_PER_MEMBER", "WITT_COUNCIL_R2_EVIDENCE_CHARS",
                "WITT_COUNCIL_ATTESTATION_CHARS", "WITT_COUNCIL_CACHE", "WITT_COUNCIL_CACHE_TTL", "WITT_COUNCIL_INDEX",
                "WITT_COUNCIL_PRIOR_K", "WITT_COUNCIL_PRIOR_KINDS", "WITT_COUNCIL_INDEX_ORIGINS",
                "WITT_ANTHROPIC_MAX_INFLIGHT", "WITT_ANTHROPIC_RETRY_AFTER_CAP_S")
# ADR-0083 tabla de env: las 20 nuevas de figuras (WITT_MCP_CACHE_DIR ya existía y NO es de models.ENV_TABLE), en el orden del ADR
ENV_ADR_0083 = ("WITT_FIGURES", "WITT_FIGURES_VISION", "WITT_FIGURES_VISION_LENSES", "WITT_FIGURES_MAX_PAPERS",
                "WITT_FIGURES_MAX_PER_PAPER", "WITT_FIGURES_MAX_PER_RUN", "WITT_FIGURES_MAX_PER_LENS", "WITT_FIGURES_MAX_IMAGE_MB",
                "WITT_FIGURES_ZIP_MAX_MB", "WITT_FIGURES_BUDGET_S", "WITT_FIGURES_TTL_DAYS", "WITT_FIGURES_CACHE_MAX_MB",
                "WITT_FIGURES_CAPTION_CHARS", "WITT_FIGURES_EMBED_LICENSES", "WITT_FIGURES_PANEL_LICENSES",
                "WITT_FIGURES_PROSE_LICENSE", "WITT_FIGURES_OPENAI_DETAIL", "WITT_FIGURES_REFETCH_ON_GET", "WITT_FIGURES_PDF_THUMBS",
                "WITT_FIGURES_COUNT_TOKENS")
# ADR-0084 tabla de env: las 17 nuevas del localizador web, en el orden del ADR (BRAVE_API_KEY es SECRETO: NO entra a models.ENV_TABLE)
ENV_ADR_0084 = ("WITT_WEB_LOCATOR", "WITT_WEB_MAX_RESULTS", "WITT_WEB_MAX_QUERIES", "WITT_WEB_MAX_MATERIALIZE", "WITT_WEB_MAX_QUERY_CHARS",
                "WITT_WEB_BUDGET_S", "WITT_WEB_MIN_INTERVAL_S", "WITT_WEB_COUNTRY", "WITT_WEB_LANG", "WITT_WEB_FRESHNESS",
                "WITT_WEB_ALLOWED_HOSTS", "WITT_WEB_GENERIC_DOI_RULE", "WITT_WEB_MONTHLY_CAP", "WITT_WEB_TEST_QUERY",
                "WITT_ANTHROPIC_WEB_SEARCH_MAX_USES", "WITT_WEB_ANTHROPIC_TOOL_TYPE", "WITT_WEB_LOCATOR_MODEL")
# ADR-0086 (F3): las 15 WITT_ATTESTED_* que SÍ entran a la tabla; la ruta local y las dos llaves de MinIO quedan fuera
ENV_ADR_0086 = ("WITT_ATTESTED_IMAGES", "WITT_ATTESTED_VISION", "WITT_ATTESTED_BACKEND", "WITT_ATTESTED_MINIO_BUCKET",
                "WITT_ATTESTED_MAX_IMAGE_MB", "WITT_ATTESTED_MAX_PER_PLAN", "WITT_ATTESTED_MAX_TOTAL_MB",
                "WITT_ATTESTED_MAX_PER_LENS", "WITT_ATTESTED_MAX_PER_USER_PER_DAY", "WITT_ATTESTED_CAPTION_CHARS",
                "WITT_ATTESTED_ALLOWED_MEDIA", "WITT_ATTESTED_EXIF", "WITT_ATTESTED_TEAM_VIEW", "WITT_ATTESTED_WITHDRAW",
                "WITT_ATTESTED_PATIENT_MATERIAL")

check("ROLE_ENVS exacto (9 roles: 8 de ADR-0081 + council→WITT_MODEL_COUNCIL; OPENAI_JUDGE_MODEL conserva su nombre) y ENV_TABLE "
      "cerrada: 21 envs de ADR-0081 + 27 de ADR-0082 + 20 de ADR-0083 + 17 de ADR-0084 + 15 de ADR-0086 (models.ENV_ADR_0082/0083/0084/0086 == las listas exactas "
      "de las tablas de los ADR, en su orden), cada fila con default/kind/reader/effect y kind ∈ ENV_KINDS; BRAVE_API_KEY NO está en la tabla",
      m.ROLE_ENVS == {"synthesizer": "WITT_MODEL_SYNTH", "planner": "WITT_MODEL_PLANNER", "elicitation": "WITT_MODEL_ELICIT",
                      "question_agent": "WITT_MODEL_QUESTION", "judge.correctness": "WITT_JUDGE_CORRECTNESS",
                      "judge.overclaim": "WITT_JUDGE_OVERCLAIM", "judge.evidence-grounding": "WITT_JUDGE_GROUNDING",
                      "judge.reproducibility": "OPENAI_JUDGE_MODEL", "council": "WITT_MODEL_COUNCIL"}
      and set(m.ENV_TABLE) == ENV_ADR_0081 | set(ENV_ADR_0082) | set(ENV_ADR_0083) | set(ENV_ADR_0084) | set(ENV_ADR_0086)
      and len(m.ENV_TABLE) == 100
      and m.ENV_ADR_0082 == ENV_ADR_0082 and len(m.ENV_ADR_0082) == 27
      and m.ENV_ADR_0083 == ENV_ADR_0083 and len(m.ENV_ADR_0083) == 20
      and m.ENV_ADR_0084 == ENV_ADR_0084 and len(m.ENV_ADR_0084) == 17 and "BRAVE_API_KEY" not in m.ENV_TABLE
      and m.ENV_ADR_0086 == ENV_ADR_0086 and len(m.ENV_ADR_0086) == 15
      and all(m.ENV_TABLE[k].get("adr") == "0082" for k in ENV_ADR_0082) and not any(m.ENV_TABLE[k].get("adr") for k in ENV_ADR_0081)
      and all(m.ENV_TABLE[k].get("adr") == "0083" for k in ENV_ADR_0083)
      and all(m.ENV_TABLE[k].get("adr") == "0084" for k in ENV_ADR_0084)
      and all(m.ENV_TABLE[k].get("adr") == "0086" for k in ENV_ADR_0086)
      # ADR-0086: ni la ruta del almacén ni las llaves de MinIO entran a la tabla (ni rutas de máquina ni secretos)
      and not ({"WITT_ATTESTED_DIR", "WITT_ATTESTED_MINIO_ACCESS_KEY", "WITT_ATTESTED_MINIO_SECRET_KEY"} & set(m.ENV_TABLE))
      and all("default" in v and "kind" in v and "reader" in v and "effect" in v and v["kind"] in m.ENV_KINDS for v in m.ENV_TABLE.values()),
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
      "(juez OpenAI: tope None declarado — es del transporte); el 9º (council) opus-4-8 / 1200 declarado; generation_source "
      "'env:WITT_MODEL_GENERATION'",
      _sin_council({k: v["model"] for k, v in g1_roles.items()}) == G1_DEFAULTS
      and g1_roles["synthesizer"]["max_tokens"] == 2500 and g1_roles["planner"]["max_tokens"] == 1200
      and g1_roles["elicitation"]["max_tokens"] == 300 and g1_roles["question_agent"]["max_tokens"] == 1200
      and g1_roles["judge.correctness"]["max_tokens"] == 1200 and g1_roles["judge.reproducibility"]["max_tokens"] is None
      and (g1_roles["council"]["model"], g1_roles["council"]["max_tokens"]) == G1_COUNCIL
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
check("snapshot: fields == SNAPSHOT_FIELDS (41 = 28 de ADR-0081 + 5 de ADR-0082 + 2 de ADR-0083 + 2 de ADR-0084 + 4 de ADR-0086 al final, "
      "cerrada, en orden) y cada campo es exactamente {value, source}",
      tuple(S["fields"]) == m.SNAPSHOT_FIELDS and len(m.SNAPSHOT_FIELDS) == 41
      and m.SNAPSHOT_FIELDS[28:33] == m.COUNCIL_SNAPSHOT_FIELDS == ("role.council", "council.enabled", "council.full", "council.effort", "council.cache_ttl")
      and m.SNAPSHOT_FIELDS[33:35] == m.FIGURES_SNAPSHOT_FIELDS == ("figures.enabled", "figures.vision")
      and m.SNAPSHOT_FIELDS[35:37] == m.WEB_SNAPSHOT_FIELDS == ("web.locator", "web.provider")
      and m.SNAPSHOT_FIELDS[37:] == m.ATTESTED_SNAPSHOT_FIELDS == ("attested.enabled", "attested.vision",
                                                                   "attested.backend", "attested.team_view")
      # ADR-0086 (F3): los interruptores de lo atestiguado quedan FUERA de panel_signature — la firma del panel no cambia
      # porque haya o no imágenes aportadas (si cambiara, toda corrida anterior parecería de otra configuración)
      and not any(f in str(S["fields"]["panel_signature"]["value"]) for f in m.ATTESTED_SNAPSHOT_FIELDS)
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
check("provenance_block: llaves top-level == PROVENANCE_FIELDS; roles {synthesizer, elicitation, question_agent null, planner, "
      "council null (ADR-0082 M: el llamador no lo trajo — declarado, no inventado)}; "
      "ran {synthesize_pass1/2, revision, elicit_pass1/2, plan, question, panel}; generation copiada del rol resuelto",
      tuple(B) == m.PROVENANCE_FIELDS and set(B["roles"]) == {"synthesizer", "elicitation", "question_agent", "planner", "council"}
      and B["roles"]["question_agent"] is None and B["roles"]["council"] is None and B["roles"]["synthesizer"] == ROLES_RUN["synthesizer"]
      and B["roles"]["elicitation"]["source"] == "env:WITT_MODEL_ELICIT"
      and set(B["ran"]) == {"synthesize_pass1", "synthesize_pass2", "revision", "elicit_pass1", "elicit_pass2", "plan", "question", "panel"}
      and B["generation"] == "g2-2026-09" and B["table_version"] == "g2-2026-09" and B["table_as_of"] == "2026-09-15"
      and B["ran"]["question"] is None and B["rule"] == m.PROVENANCE_RULE)
_B_c = m.provenance_block({**ROLES_RUN, "council": m.resolve_role("council")}, PASSES, None, [])
check("ADR-0082 (M): provenance_block copia roles.council TAL CUAL del snapshot que runs le pasa (frozen.models.roles.council == "
      "stage.models.roles.council — el rol council FUERA de panel_signature: la firma no cambia con o sin él)",
      _B_c["roles"]["council"] == m.resolve_role("council") and _B_c["roles"]["council"]["model"] == m.GENERATIONS["g2-2026-09"]["defaults"]["council"]
      and _B_c["panel_signature"] == m.provenance_block(ROLES_RUN, PASSES, None, [])["panel_signature"],
      f"council={_B_c['roles']['council']['model']} sig={_B_c['panel_signature']}")
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
# 16. ADR-0082 (D.2, rebanada C3): rol `council` fuera de PIPELINE_ROLES · effort · caché · env · snapshot
# =====================================================================================================
PANEL_SIGNATURE_GOLDEN_9D90C01 = "5f60c94ab22e65f5"   # models.panel_signature(panel(env={}), roles PIPELINE, today T) @ 9d90c01
check("ADR-0082 (D.2): COUNCIL_ROLES ('council',) FUERA de PIPELINE_ROLES; ROLES = PIPELINE + JUDGE + COUNCIL (9); ROLE_FAMILY "
      "council 'anthropic'; 'council' ∈ MAX_TOKENS_KEYS (6 topes); las dos generaciones lo cotizan",
      m.COUNCIL_ROLES == ("council",) and "council" not in m.PIPELINE_ROLES and "council" not in m.JUDGE_ROLES
      and m.ROLES == m.PIPELINE_ROLES + m.JUDGE_ROLES + m.COUNCIL_ROLES and len(m.ROLES) == 9
      and m.ROLE_FAMILY["council"] == "anthropic" and "council" in m.MAX_TOKENS_KEYS and len(m.MAX_TOKENS_KEYS) == 6
      and all("council" in g["defaults"] and "council" in g["max_tokens"] for g in m.GENERATIONS.values()))
rc = m.resolve_role("council", env={}, today=T)
rc1 = m.resolve_role("council", env=g1, today=T)
check("resolve_role('council'): g2 → claude-opus-5 'default:g2-2026-09', anthropic-messages, known, priced, tope 4000; g1 → "
      "claude-opus-4-8 'default:g1-2026-08', tope 1200 (declarado); forma cerrada ROLE_RESOLVED_FIELDS",
      tuple(rc) == m.ROLE_RESOLVED_FIELDS and rc["model"] == "claude-opus-5" and rc["source"] == "default:g2-2026-09"
      and rc["api"] == "anthropic-messages" and rc["known"] and rc["priced"] and rc["max_tokens"] == 4000
      and rc1["model"] == "claude-opus-4-8" and rc1["source"] == "default:g1-2026-08" and rc1["max_tokens"] == 1200, f"{rc}")
rc_env = m.resolve_role("council", env={"WITT_MODEL_COUNCIL": "claude-sonnet-5"}, today=T)
rc_fab = m.resolve_role("council", env={"WITT_MODEL_COUNCIL": "claude-fable-5-1"}, today=T)
rc_gpt = m.resolve_role("council", env={"WITT_MODEL_COUNCIL": "gpt-4o"}, today=T)
rc_sec = m.resolve_role("council", env={"WITT_MODEL_COUNCIL": "sk-live-SECRETOenUnModelo"}, today=T)
check("WITT_MODEL_COUNCIL respetado (sonnet-5 → 'env:WITT_MODEL_COUNCIL', tope SIGUE 4000: palanca declarada, no default — K.f); "
      "fable → 'default-invalid-env:WITT_MODEL_COUNCIL (excluded-model)'; gpt-4o → '(wrong-family-for-role)' (el consejo habla "
      "anthropic-messages con tools forzados); valor con forma de llave → '(secret-like-value)' y jamás viaja",
      rc_env["model"] == "claude-sonnet-5" and rc_env["source"] == "env:WITT_MODEL_COUNCIL" and rc_env["max_tokens"] == 4000
      and rc_fab["model"] == "claude-opus-5" and rc_fab["source"] == "default-invalid-env:WITT_MODEL_COUNCIL (excluded-model)"
      and rc_gpt["model"] == "claude-opus-5" and rc_gpt["source"] == "default-invalid-env:WITT_MODEL_COUNCIL (wrong-family-for-role)"
      and rc_sec["model"] == "claude-opus-5" and rc_sec["source"] == "default-invalid-env:WITT_MODEL_COUNCIL (secret-like-value)"
      and "SECRETO" not in json.dumps(m.resolve_panel(env={"WITT_MODEL_COUNCIL": "sk-live-SECRETOenUnModelo"}, today=T)))
roles_all = {role: m.resolve_role(role, env={}, today=T) for role in m.ROLES}
sig_all = m.panel_signature(P, roles_all)
sig_pin_council = m.panel_signature(P, {**roles_all, "council": m.resolve_role("council", env={"WITT_MODEL_COUNCIL": "claude-sonnet-5"}, today=T)})
sig_off = m.snapshot(env={"WITT_COUNCIL": "0"}, today=T)["panel_signature"]
sig_full = m.snapshot(env={"WITT_COUNCIL_FULL": "1", "WITT_COUNCIL_EFFORT": "max", "WITT_MODEL_COUNCIL": "claude-sonnet-5"}, today=T)["panel_signature"]
check("panel_signature INTACTA (veredicto de los dos jueces, D.2): == GOLDEN @ 9d90c01 '5f60c94ab22e65f5' con los 4 roles del pipeline, "
      "con los 9 roles, con WITT_MODEL_COUNCIL pineado a sonnet, con WITT_COUNCIL=0 y con FULL=1/effort max — el consejo NO es "
      "identidad de la configuración (la serie de ADR-0087 no se corta)",
      sig0 == PANEL_SIGNATURE_GOLDEN_9D90C01 and sig_all == sig0 and sig_pin_council == sig0 and sig_off == sig0 and sig_full == sig0
      and m.snapshot(env={}, today=T)["panel_signature"] == sig0, f"sig0={sig0} all={sig_all} pin={sig_pin_council} off={sig_off}")
FC = m.snapshot(env={}, today=T)["fields"]
check("snapshot env vacía: role.council {claude-opus-5, 'default:g2-2026-09'} · council.enabled True 'default-unset:WITT_COUNCIL' · "
      "council.full False · council.effort 'medium' 'default-unset:WITT_COUNCIL_EFFORT' · council.cache_ttl '5m'; roles del snapshot "
      "== ROLES (9); stage.models.roles.council viaja aunque el consejo esté apagado (excepción declarada L.2 ii)",
      FC["role.council"] == {"value": "claude-opus-5", "source": "default:g2-2026-09"}
      and FC["council.enabled"] == {"value": True, "source": "default-unset:WITT_COUNCIL"}
      and FC["council.full"] == {"value": False, "source": "default-unset:WITT_COUNCIL_FULL"}
      and FC["council.effort"] == {"value": "medium", "source": "default-unset:WITT_COUNCIL_EFFORT"}
      and FC["council.cache_ttl"] == {"value": "5m", "source": "default-unset:WITT_COUNCIL_CACHE_TTL"}
      and set(m.snapshot(env={}, today=T)["roles"]) == set(m.ROLES)
      and "council" in m.snapshot(env={"WITT_COUNCIL": "0"}, today=T)["roles"]
      and m.snapshot(env={"WITT_COUNCIL": "0"}, today=T)["fields"]["council.enabled"] == {"value": False, "source": "env:WITT_COUNCIL"},
      json.dumps({k: FC[k] for k in m.COUNCIL_SNAPSHOT_FIELDS}, ensure_ascii=False))
S5 = m.snapshot(env={"WITT_MODEL_COUNCIL": "sk-live-SECRETOenUnModelo", "WITT_COUNCIL_EFFORT": "sk-ant-SECRETO"}, today=T)
check("snapshot JAMÁS lleva una llave por el consejo: WITT_MODEL_COUNCIL con forma de llave → default con '(secret-like-value)'; "
      "WITT_COUNCIL_EFFORT basura → 'medium' default-invalid; el dump no contiene 'SECRETO' ni 'sk-'",
      "SECRETO" not in json.dumps(S5, ensure_ascii=False) and "sk-" not in json.dumps(S5, ensure_ascii=False)
      and S5["fields"]["role.council"] == {"value": "claude-opus-5", "source": "default-invalid-env:WITT_MODEL_COUNCIL (secret-like-value)"}
      and S5["fields"]["council.effort"] == {"value": "medium", "source": "default-invalid-env:WITT_COUNCIL_EFFORT"})
check("council_effort() (E2, default medium, FIJO por ruta): vacía → ('medium', 'default-unset:WITT_COUNCIL_EFFORT'); 'HIGH' → "
      "('high', 'env:…') normalizado; 'inherit' (alternativa E2 declarada) → hereda WITT_ANTHROPIC_EFFORT: (None, 'env:WITT_COUNCIL_EFFORT "
      "(inherit -> default-unset:WITT_ANTHROPIC_EFFORT)') = no se envía, o ('low', '… (inherit -> env:WITT_ANTHROPIC_EFFORT)'); "
      "'ultra' → ('medium', 'default-invalid-env:…'); COUNCIL_EFFORT_CHOICES = ANTHROPIC_EFFORTS + ('inherit',)",
      m.council_effort(env={}) == ("medium", "default-unset:WITT_COUNCIL_EFFORT")
      and m.council_effort(env={"WITT_COUNCIL_EFFORT": "HIGH"}) == ("high", "env:WITT_COUNCIL_EFFORT")
      and m.council_effort(env={"WITT_COUNCIL_EFFORT": "inherit"}) == (None, "env:WITT_COUNCIL_EFFORT (inherit -> default-unset:WITT_ANTHROPIC_EFFORT)")
      and m.council_effort(env={"WITT_COUNCIL_EFFORT": "inherit", "WITT_ANTHROPIC_EFFORT": "low"}) == ("low", "env:WITT_COUNCIL_EFFORT (inherit -> env:WITT_ANTHROPIC_EFFORT)")
      and m.council_effort(env={"WITT_COUNCIL_EFFORT": "ultra"}) == ("medium", "default-invalid-env:WITT_COUNCIL_EFFORT")
      and m.COUNCIL_EFFORT_CHOICES == m.ANTHROPIC_EFFORTS + ("inherit",) and m.COUNCIL_EFFORT_DEFAULT == "medium"
      and m.env_value("WITT_COUNCIL_EFFORT", env={"WITT_COUNCIL_EFFORT": "inherit"}) == ("inherit", "env:WITT_COUNCIL_EFFORT"))
check("kind `bool` tolerante (WITT_COUNCIL): 'false' → (False, 'env:'), 'YES' → (True, 'env:'), 'maybe' → (True, 'default-invalid-env:'), "
      "vacía → (True, 'default-unset:'); kind `float` con rango (WITT_COUNCIL_QUORUM ∈ (0,1]): vacía 0.6, '0.75' env, '0'/'1.5'/'nan' → "
      "0.6 default-invalid; kind `choice` (WITT_COUNCIL_CACHE_TTL): '1h' env, '2h' → '5m' default-invalid; ints con mínimo "
      "(CONCURRENCY '0' → 6 default-invalid; WORKERS '0' → 0 válido)",
      m.env_value("WITT_COUNCIL", env={"WITT_COUNCIL": "false"}) == (False, "env:WITT_COUNCIL")
      and m.env_value("WITT_COUNCIL", env={"WITT_COUNCIL": "YES"}) == (True, "env:WITT_COUNCIL")
      and m.env_value("WITT_COUNCIL", env={"WITT_COUNCIL": "maybe"}) == (True, "default-invalid-env:WITT_COUNCIL")
      and m.env_value("WITT_COUNCIL", env={}) == (True, "default-unset:WITT_COUNCIL")
      and m.env_value("WITT_COUNCIL_QUORUM", env={}) == (0.6, "default-unset:WITT_COUNCIL_QUORUM")
      and m.env_value("WITT_COUNCIL_QUORUM", env={"WITT_COUNCIL_QUORUM": "0.75"}) == (0.75, "env:WITT_COUNCIL_QUORUM")
      and all(m.env_value("WITT_COUNCIL_QUORUM", env={"WITT_COUNCIL_QUORUM": bad}) == (0.6, "default-invalid-env:WITT_COUNCIL_QUORUM")
              for bad in ("0", "1.5", "nan", "-0.2", "abc"))
      and m.env_value("WITT_COUNCIL_QUORUM", env={"WITT_COUNCIL_QUORUM": "1"}) == (1.0, "env:WITT_COUNCIL_QUORUM")
      and m.env_value("WITT_COUNCIL_CACHE_TTL", env={"WITT_COUNCIL_CACHE_TTL": "1h"}) == ("1h", "env:WITT_COUNCIL_CACHE_TTL")
      and m.env_value("WITT_COUNCIL_CACHE_TTL", env={"WITT_COUNCIL_CACHE_TTL": "2h"}) == ("5m", "default-invalid-env:WITT_COUNCIL_CACHE_TTL")
      and m.env_value("WITT_COUNCIL_CONCURRENCY", env={"WITT_COUNCIL_CONCURRENCY": "0"}) == (6, "default-invalid-env:WITT_COUNCIL_CONCURRENCY")
      and m.env_value("WITT_COUNCIL_WORKERS", env={"WITT_COUNCIL_WORKERS": "0"}) == (0, "env:WITT_COUNCIL_WORKERS"))
try:
    from lib import agent_matrix as _am  # noqa: E402
    from lib import catalog_cards as _cc  # noqa: E402
    _lits = ("1", "true", "yes", "on", "TRUE", "On", "0", "false", "no", "off", "OFF", "maybe", "2", "", "  ")
    _parity_full = all(m.env_value("WITT_COUNCIL_FULL", env={"WITT_COUNCIL_FULL": s})[0] == _am.council_full(env={"WITT_COUNCIL_FULL": s})[0] for s in _lits)
    _parity_cache = all(m.env_value("WITT_COUNCIL_CACHE", env={"WITT_COUNCIL_CACHE": s})[0] == _cc.cache_config(env={"WITT_COUNCIL_CACHE": s})["enabled"] for s in _lits)
    _parity_ttl = all(m.env_value("WITT_COUNCIL_CACHE_TTL", env={"WITT_COUNCIL_CACHE_TTL": s})[0] == _cc.cache_config(env={"WITT_COUNCIL_CACHE_TTL": s})["ttl_card"] for s in ("5m", "1h", "1H", "2h", "", "x"))
    check("PARIDAD de lectores (C1 ↔ C3, medida sobre 15 literales): models.env_value(kind bool) == agent_matrix.council_full "
          "(WITT_COUNCIL_FULL) == catalog_cards.cache_config.enabled (WITT_COUNCIL_CACHE); TTL == cache_config.ttl_card — el snapshot "
          "y el lector del dueño jamás divergen; COUNCIL_CACHE_TTLS == catalog_cards.CACHE_TTLS",
          _parity_full and _parity_cache and _parity_ttl and m.COUNCIL_CACHE_TTLS == _cc.CACHE_TTLS,
          f"full={_parity_full} cache={_parity_cache} ttl={_parity_ttl}")
except Exception as e:   # pragma: no cover — C1 entrega agent_matrix v1.3 / catalog_cards en la misma rama
    check("PARIDAD de lectores C1 ↔ C3: import lib.agent_matrix / lib.catalog_cards", False, f"{type(e).__name__}: {e}")
check("CACHE_MULTIPLIERS {write_5m 1.25, write_1h 2.0, read 0.1} con fuente (platform.claude.com + skill claude-api cache 2026-06-24) y "
      "CACHE_AS_OF '2026-06-24'; cache_prices('claude-opus-5') = {6.25, 10.0, 0.5, price_in 5.0, class 'derived-from-published-multipliers', "
      "multipliers, source, as_of} (forma CACHE_PRICE_FIELDS); para TODO modelo cotizado write_5m/write_1h/read == price_in × mult; "
      "modelo sin precio → None (jamás un 0)",
      m.CACHE_MULTIPLIERS == {"write_5m": 1.25, "write_1h": 2.0, "read": 0.1} and "2026-06-24" in m.CACHE_MULTIPLIERS_SOURCE
      and "platform.claude.com" in m.CACHE_MULTIPLIERS_SOURCE and m.CACHE_AS_OF == "2026-06-24"
      and tuple(m.cache_prices("claude-opus-5")) == m.CACHE_PRICE_FIELDS
      and {k: m.cache_prices("claude-opus-5")[k] for k in ("write_5m", "write_1h", "read", "price_in", "class")}
      == {"write_5m": 6.25, "write_1h": 10.0, "read": 0.5, "price_in": 5.0, "class": "derived-from-published-multipliers"}
      and all(m.cache_prices(mid) == {"write_5m": p[0] * 1.25, "write_1h": p[0] * 2.0, "read": p[0] * 0.1, "price_in": p[0],
                                       "class": m.CACHE_PRICE_CLASS, "multipliers": m.CACHE_MULTIPLIERS,
                                       "source": m.CACHE_MULTIPLIERS_SOURCE, "as_of": m.CACHE_AS_OF}
              for mid, p in m.prices().items())
      and m.cache_prices("llama-9") is None and m.prices() == GOLDEN_PRICES, f"{m.cache_prices('claude-opus-5')}")
# =====================================================================================================
# 17. ADR-0083 (G.4 / H / M.4 / O.5, rebanada F3): visión por tabla · vision_tokens · env de figuras · snapshot
# =====================================================================================================
_G2 = m.GENERATIONS["g2-2026-09"]["defaults"]
_HAIKU, _OPUS, _BRIDGE = _G2["judge.evidence-grounding"], _G2["synthesizer"], _G2["judge.reproducibility"]
_ASTRA = next(k for k, r_ in m.MODELS.items() if r_["status"] == "candidate")
_EMBED = next(k for k, r_ in m.MODELS.items() if r_["status"] == "embed")
_EXCL = next(k for k, r_ in m.MODELS.items() if r_["status"] == "excluded")
check("ADR-0083 (G.4): VISION_TIERS cerrado (6); vision_tier por fila ∈ VISION_TIERS y COHERENTE con la familia — anthropic ∈ {high-res-2576, "
      "standard-1568, unknown}, openai de herramientas ∈ {tile-512, patch-32}, embed 'none'; grounding g2 standard · sintetizador/overclaim/"
      "g1 high-res · fable 'unknown' · puente tile · candidato y sol patch-32 ×1.2; vision_multiplier float sólo en patch-32; "
      "vision_verified False en las 9 (nada medido en vivo: LG3/LG4)",
      m.VISION_TIERS == ("high-res-2576", "standard-1568", "tile-512", "patch-32", "none", "unknown")
      and all(r_["vision_tier"] in m.VISION_TIERS for r_ in m.MODELS.values())
      and all(r_["vision_tier"] in ("high-res-2576", "standard-1568", "unknown") for r_ in m.MODELS.values() if r_["family"] == "anthropic")
      and all(r_["vision_tier"] in ("tile-512", "patch-32") for r_ in m.MODELS.values() if r_["family"] == "openai" and r_["api"] != "openai-embeddings")
      and m.MODELS[_EMBED]["vision_tier"] == "none" and m.MODELS[_HAIKU]["vision_tier"] == "standard-1568"
      and m.MODELS[_OPUS]["vision_tier"] == m.MODELS[_G2["judge.overclaim"]]["vision_tier"] == m.MODELS["claude-opus-4-8"]["vision_tier"] == "high-res-2576"
      and m.MODELS[_EXCL]["vision_tier"] == "unknown" and m.MODELS[_BRIDGE]["vision_tier"] == "tile-512"
      and m.MODELS[_ASTRA]["vision_tier"] == m.MODELS["gpt-5.6-sol"]["vision_tier"] == "patch-32"
      and m.MODELS[_ASTRA]["vision_multiplier"] == m.MODELS["gpt-5.6-sol"]["vision_multiplier"] == 1.2
      and all((r_["vision_multiplier"] is None) == (r_["vision_tier"] != "patch-32") for r_ in m.MODELS.values())
      and not any(r_["vision_verified"] for r_ in m.MODELS.values()),
      json.dumps({k: (r_["vision_tier"], r_["vision_multiplier"]) for k, r_ in m.MODELS.items()}))
_VT = [(_OPUS, 1000, 1000, 1296), (_HAIKU, 1000, 1000, 1296), (_HAIKU, 1920, 1080, 1560), (_OPUS, 1920, 1080, 2691),
       (_HAIKU, 2000, 1500, 1564), (_OPUS, 2000, 1500, 3888), (_OPUS, 3840, 2160, 4784), (_BRIDGE, 750, 417, 425),
       (_BRIDGE, 738, 840, 765), (_ASTRA, 750, 417, 404)]
_got = [(mdl, w, h, m.vision_tokens(mdl, w, h)["tokens"]) for mdl, w, h, _e in _VT]
check("ADR-0083 (H): vision_tokens == la tabla PÚBLICA del ADR — 1000² → 1296 (alto y estándar); 1920×1080 → 1560 estándar (1456×819) / 2691 "
      "alto (sin reescalar); 2000×1500 → 1564 / 3888; 3840×2160 alto → 4784 (= tope publicado, 2576×1449); puente 750×417 → 85+2×170 = 425, "
      "738×840 → 85+4×170 = 765; candidato 750×417 → ⌈336×1.2⌉ = 404",
      _got == list(_VT), json.dumps(_got))
_vh = m.vision_tokens(_HAIKU, 1920, 1080)
_vg = m.vision_tokens(_BRIDGE, 738, 840)
_va = m.vision_tokens(_ASTRA, 750, 417)
check("ADR-0083 (H): forma de vision_tokens — {tokens, formula, tier, family, detail, detail_effective, scaled, scaled_applied, multiplier, "
      "cap_applied, source, class 'proyección', rule} (+tiles | +patches); formulas literales; anthropic scaled 1456×819 (aplicado); "
      "tile 4 tiles sin reescalar; patch 336 parches ×1.2; detail None → 'auto' proyecta como high (declarado)",
      _vh["formula"] == m.VISION_FORMULAS["anthropic"] == "anthropic: Σ⌈w/28⌉×⌈h/28⌉ (tier cap)" and _vh["scaled"] == {"w": 1456, "h": 819}
      and _vh["scaled_applied"] is True and _vh["cap_applied"] is False and _vh["class"] == "proyección" == m.VISION_CLASS
      and _vh["source"] == m.VISION_FORMULA_SOURCE["anthropic"] and _vh["rule"] == m.VISION_TOKENS_RULE
      and _vg["formula"] == "openai-tile: 85+170×tiles (fit 2048 → shortest 768 → 512-px tiles)" and _vg["tiles"] == 4
      and _vg["scaled_applied"] is False and _vg["detail"] is None and _vg["detail_effective"] == "high"
      and _va["formula"] == "openai-patch: Σ⌈w/32⌉×⌈h/32⌉ × 1.2 (cap 2500)" and _va["patches"] == 336 and _va["multiplier"] == 1.2
      and set(_vh) == {"tokens", "formula", "tier", "family", "detail", "detail_effective", "scaled", "scaled_applied", "multiplier",
                       "cap_applied", "source", "class", "rule"})
check("ADR-0083 (H): límites — puente detail 'low' → 85 fijos (0 tiles); 4000×3000 en el puente → encaja en 2048, lado corto a 768 → 1024×768 "
      "= 2×2 tiles → 765; candidato 6000×4000 (23 437 parches) → reescalado a ≤ 2500 parches (cap_applied), 'original' → sin tope; "
      "3000×3000 alto → 1932² → 69² = 4761 ≤ 4784; embed / id desconocido / dims inválidas → None (no se proyecta lo que no se sabe)",
      m.vision_tokens(_BRIDGE, 750, 417, "low")["tokens"] == 85 and m.vision_tokens(_BRIDGE, 750, 417, "low")["tiles"] == 0
      and m.vision_tokens(_BRIDGE, 4000, 3000)["tokens"] == 765 and m.vision_tokens(_BRIDGE, 4000, 3000)["scaled"] == {"w": 1024, "h": 768}
      and m.vision_tokens(_ASTRA, 6000, 4000)["patches"] <= 2500 and m.vision_tokens(_ASTRA, 6000, 4000)["cap_applied"] is True
      and m.vision_tokens(_ASTRA, 6000, 4000, "original")["patches"] == 188 * 125 and m.vision_tokens(_ASTRA, 6000, 4000, "original")["cap_applied"] is False
      and m.vision_tokens(_OPUS, 3000, 3000)["tokens"] == 4761 and m.vision_tokens(_OPUS, 3000, 3000)["scaled"] == {"w": 1932, "h": 1932}
      and m.vision_tokens(_EMBED, 100, 100) is None and m.vision_tokens("llama-9", 100, 100) is None
      and m.vision_tokens(_OPUS, 0, 100) is None and m.vision_tokens(_OPUS, None, 100) is None and m.vision_tokens(_OPUS, 10.5, 100) is None)
check("ADR-0083 (G.4): vision_tier_of — (tier, multiplier, verified, 'table') por fila; id desconocido → ('unknown', None, False, 'unknown-to-table')",
      m.vision_tier_of(_HAIKU) == ("standard-1568", None, False, "table") and m.vision_tier_of(_ASTRA) == ("patch-32", 1.2, False, "table")
      and m.vision_tier_of("llama-9") == ("unknown", None, False, "unknown-to-table"))
_SF = m.snapshot(env={}, today=T)["fields"]
_SF0 = m.snapshot(env={"WITT_FIGURES": "0", "WITT_FIGURES_VISION": "off"}, today=T)["fields"]
_SFb = m.snapshot(env={"WITT_FIGURES": "maybe"}, today=T)["fields"]
check("ADR-0083 (O.5): snapshot.fields figures.enabled {True, 'default-unset:WITT_FIGURES'} y figures.vision {True, 'default-unset:…'}; "
      "WITT_FIGURES=0 → {False, env}; WITT_FIGURES_VISION=off → False (mismos literales bool que figures.env_config); 'maybe' → default con "
      "'default-invalid-env'; panel_signature INTACTA (== golden 9d90c01) con figuras encendidas o apagadas — FUERA de la firma",
      _SF["figures.enabled"] == {"value": True, "source": "default-unset:WITT_FIGURES"}
      and _SF["figures.vision"] == {"value": True, "source": "default-unset:WITT_FIGURES_VISION"}
      and _SF0["figures.enabled"] == {"value": False, "source": "env:WITT_FIGURES"} and _SF0["figures.vision"] == {"value": False, "source": "env:WITT_FIGURES_VISION"}
      and _SFb["figures.enabled"] == {"value": True, "source": "default-invalid-env:WITT_FIGURES"}
      and m.snapshot(env={"WITT_FIGURES": "0"}, today=T)["panel_signature"] == PANEL_SIGNATURE_GOLDEN_9D90C01 == _SF["panel_signature"]["value"])
try:
    from lib import figures as _fig  # noqa: E402
    _specs = {s[1]: s for s in _fig.ENV_SPECS if s[1] != "WITT_MCP_CACHE_DIR"}
    _KIND_MAP = {"bool": "bool", "int": "int", "float": "float", "csv": "str", "licenses": "str", "choice": "choice"}
    _cfg0 = _fig.env_config({})
    _by_var = {s[1]: s[0] for s in _fig.ENV_SPECS}

    def _typed_default_equal(var):
        v_m, _s = m.env_value(var, {})
        v_f = _cfg0[_by_var[var]]
        kind = _specs[var][3]
        if kind in ("csv", "licenses"):
            return [t for t in v_m.split(",")] == list(v_f) or tuple(v_m.split(",")) == tuple(v_f)
        return v_m == v_f
    _bad_default = [v for v in ENV_ADR_0083 if m.ENV_TABLE[v]["default"] != _specs[v][2]]
    _bad_kind = [v for v in ENV_ADR_0083 if m.ENV_TABLE[v]["kind"] != _KIND_MAP[_specs[v][3]]]
    _bad_typed = [v for v in ENV_ADR_0083 if v in ("WITT_FIGURES_EMBED_LICENSES", "WITT_FIGURES_PANEL_LICENSES") and False or not _typed_default_equal(v)]
    _bad_clamp = [v for v in ENV_ADR_0083 if _specs[v][3] in ("int", "float") and _specs[v][4]
                  and (m.ENV_TABLE[v].get("minimum") != _specs[v][4][0] or m.ENV_TABLE[v].get("maximum") != _specs[v][4][1])]
    check("ADR-0083 (M.4) PARIDAD de literales: set(ENV_ADR_0083) == figures.ENV_VARS − {WITT_MCP_CACHE_DIR}; default de cada fila de "
          "models.ENV_TABLE == el de figures.ENV_SPECS (string); kind mapeado (bool/int/float/choice; csv y licencias → str); default TIPADO "
          "de env_value == figures.env_config({}) (bools, ints, floats, choice, CSV); clamps int/float de figures == minimum/maximum",
          set(ENV_ADR_0083) == set(_fig.ENV_VARS) - {"WITT_MCP_CACHE_DIR"} and not _bad_default and not _bad_kind and not _bad_typed
          and not _bad_clamp and m.ENV_TABLE["WITT_FIGURES_OPENAI_DETAIL"]["choices"] == tuple(_fig.OPENAI_DETAILS),
          f"default={_bad_default} kind={_bad_kind} typed={_bad_typed} clamp={_bad_clamp}")
    check("ADR-0083 (M.4) env_value con clamps: MAX_PER_LENS 25 → default 12 'default-invalid-env' (máximo 20); MAX_IMAGE_MB '0' → 0.0 env "
          "(mínimo INCLUSIVO); '7.5' → default 5.0 invalid; OPENAI_DETAIL 'HIGH' → 'high' (casefold); 'ultra' → default 'high' invalid; "
          "WITT_COUNCIL_QUORUM '0' sigue rechazado (min_exclusive intacto); figures.env_config lee lo mismo",
          m.env_value("WITT_FIGURES_MAX_PER_LENS", {"WITT_FIGURES_MAX_PER_LENS": "25"}) == (12, "default-invalid-env:WITT_FIGURES_MAX_PER_LENS")
          and m.env_value("WITT_FIGURES_MAX_IMAGE_MB", {"WITT_FIGURES_MAX_IMAGE_MB": "0"}) == (0.0, "env:WITT_FIGURES_MAX_IMAGE_MB")
          and m.env_value("WITT_FIGURES_MAX_IMAGE_MB", {"WITT_FIGURES_MAX_IMAGE_MB": "7.5"}) == (5.0, "default-invalid-env:WITT_FIGURES_MAX_IMAGE_MB")
          and m.env_value("WITT_FIGURES_OPENAI_DETAIL", {"WITT_FIGURES_OPENAI_DETAIL": "HIGH"}) == ("high", "env:WITT_FIGURES_OPENAI_DETAIL")
          and m.env_value("WITT_FIGURES_OPENAI_DETAIL", {"WITT_FIGURES_OPENAI_DETAIL": "ultra"}) == ("high", "default-invalid-env:WITT_FIGURES_OPENAI_DETAIL")
          and m.env_value("WITT_COUNCIL_QUORUM", {"WITT_COUNCIL_QUORUM": "0"})[1].startswith("default-invalid-env")
          and _fig.env_config({"WITT_FIGURES_MAX_PER_LENS": "25"})["max_per_lens"] == 12
          and _fig.env_config({"WITT_FIGURES_MAX_PER_LENS": "25"})["sources"]["max_per_lens"] == "default-invalid-env:WITT_FIGURES_MAX_PER_LENS")
except Exception as e:  # pragma: no cover — F1 es dueño de figures.py; si no importa, se declara
    check(f"ADR-0083: lib.figures importable para la paridad de env ({type(e).__name__}: {str(e)[:100]})", False)
    check("ADR-0083: paridad env (no medida)", False)

# =====================================================================================================
# 14b. ADR-0084 — las 17 env del localizador web: paridad con web_locator.ENV_SPECS, snapshot web.*, firma intacta
# =====================================================================================================
try:
    from lib import web_locator as _wl  # noqa: E402
    _wspecs = {s[1]: s for s in _wl.ENV_SPECS}
    _WKIND = {"provider": "choice", "choice": "choice", "int": "int", "float": "float", "bool": "bool", "csv": "str", "str": "str",
              "country": "str", "lang": "str", "freshness": "str", "model": "str"}   # corrector: anthropic_tool_type es 'choice' cerrado
    _wbad_default = [v for v in ENV_ADR_0084 if m.ENV_TABLE[v]["default"] != _wl.ENV_DEFAULTS[v]]
    _wbad_kind = [v for v in ENV_ADR_0084 if m.ENV_TABLE[v]["kind"] != _WKIND[_wspecs[v][3]]]
    _wbad_clamp = [v for v in ENV_ADR_0084 if _wspecs[v][3] in ("int", "float") and _wspecs[v][4]
                   and (m.ENV_TABLE[v].get("minimum") != _wspecs[v][4][0] or m.ENV_TABLE[v].get("maximum") != _wspecs[v][4][1])]
    _wcfg0 = _wl.env_config({})
    _wtyped_bad = [v for v in ("WITT_WEB_MAX_RESULTS", "WITT_WEB_MAX_QUERIES", "WITT_WEB_MAX_MATERIALIZE", "WITT_WEB_MAX_QUERY_CHARS",
                               "WITT_WEB_BUDGET_S", "WITT_WEB_MIN_INTERVAL_S", "WITT_WEB_MONTHLY_CAP", "WITT_ANTHROPIC_WEB_SEARCH_MAX_USES")
                   if m.env_value(v, {})[0] != _wcfg0[_wspecs[v][0]]]
    check("ADR-0084 (tabla de env) PARIDAD de literales: set(ENV_ADR_0084) == web_locator.ENV_VARS (17); default de cada fila de models.ENV_TABLE == "
          "el de web_locator.ENV_SPECS (string); kind mapeado (provider→choice, int/float/bool, csv/country/lang/freshness/model→str); clamps "
          "int/float == minimum/maximum; defaults TIPADOS de env_value == web_locator.env_config({}) (8 numéricas); WITT_WEB_LOCATOR choices "
          "('', brave, anthropic, off) casefold",
          set(ENV_ADR_0084) == set(_wl.ENV_VARS) and not _wbad_default and not _wbad_kind and not _wbad_clamp and not _wtyped_bad
          and m.ENV_TABLE["WITT_WEB_LOCATOR"]["choices"] == ("", "brave", "anthropic", "off") and m.ENV_TABLE["WITT_WEB_LOCATOR"].get("casefold") is True
          # corrector ADR-0084: el tipo del server-tool es un vocabulario CERRADO en AMBAS tablas (models.ENV_TABLE y web_locator.ENV_SPECS)
          and m.ENV_TABLE["WITT_WEB_ANTHROPIC_TOOL_TYPE"]["kind"] == "choice"
          and tuple(m.ENV_TABLE["WITT_WEB_ANTHROPIC_TOOL_TYPE"]["choices"]) == _wl.ANTHROPIC_TOOL_TYPES == ("web_search_20250305",)
          and m.env_value("WITT_WEB_ANTHROPIC_TOOL_TYPE", {"WITT_WEB_ANTHROPIC_TOOL_TYPE": "web_search_20260318"})
          == ("web_search_20250305", "default-invalid-env:WITT_WEB_ANTHROPIC_TOOL_TYPE"),
          f"default={_wbad_default} kind={_wbad_kind} clamp={_wbad_clamp} typed={_wtyped_bad}")
    check("ADR-0084 env_value: WITT_WEB_LOCATOR 'BRAVE' → 'brave' env; 'zzz' → '' default-invalid-env; WITT_WEB_MAX_RESULTS '50' → default 10 invalid "
          "(models cae al default) mientras web_locator.env_config RECORTA a 20 y lo declara en clamped (dos lectores, una tabla de defaults); "
          "WITT_WEB_MONTHLY_CAP '0' → 0 env (mínimo 0 inclusivo); WITT_WEB_LOCATOR_MODEL con id fuera de tabla → web_locator lo rechaza "
          "'default-invalid-env' (validado contra models.MODELS)",
          m.env_value("WITT_WEB_LOCATOR", {"WITT_WEB_LOCATOR": "BRAVE"}) == ("brave", "env:WITT_WEB_LOCATOR")
          and m.env_value("WITT_WEB_LOCATOR", {"WITT_WEB_LOCATOR": "zzz"}) == ("", "default-invalid-env:WITT_WEB_LOCATOR")
          and m.env_value("WITT_WEB_MAX_RESULTS", {"WITT_WEB_MAX_RESULTS": "50"}) == (10, "default-invalid-env:WITT_WEB_MAX_RESULTS")
          and _wl.env_config({"WITT_WEB_MAX_RESULTS": "50"})["max_results"] == 20
          and _wl.env_config({"WITT_WEB_MAX_RESULTS": "50"})["clamped"]["max_results"]["raw"] == 50
          and m.env_value("WITT_WEB_MONTHLY_CAP", {"WITT_WEB_MONTHLY_CAP": "0"}) == (0, "env:WITT_WEB_MONTHLY_CAP")
          and _wl.env_config({"WITT_WEB_LOCATOR_MODEL": "llama-9"})["sources"]["locator_model"] == "default-invalid-env:WITT_WEB_LOCATOR_MODEL"
          and _wl.env_config({"WITT_WEB_LOCATOR_MODEL": "llama-9"})["locator_model"] is None)
    _combos = [{}, {"BRAVE_API_KEY": "k"}, {"WITT_WEB_LOCATOR": "brave"}, {"WITT_WEB_LOCATOR": "brave", "BRAVE_API_KEY": "k"},
               {"WITT_WEB_LOCATOR": "anthropic"}, {"WITT_WEB_LOCATOR": "off", "BRAVE_API_KEY": "k"}, {"WITT_WEB_LOCATOR": "zzz"},
               {"WITT_WEB_LOCATOR": " OFF "}]
    _parity = [(c, m._web_provider_field(c), {"value": _wl.provider_state(c)["provider"], "source": _wl.provider_state(c)["provider_source"]})
               for c in _combos]
    check("ADR-0084 models.py sigue SÓLO stdlib: web.provider se deriva de la env con la MISMA regla que web_locator.provider_state (B.3) — "
          "paridad byte a byte de {value, source} en 8 combinaciones (sin env/con llave, brave con y sin llave, anthropic, off, basura, ' OFF ') "
          "y models.WEB_PROVIDERS == web_locator.PROVIDERS",
          all(a == b for _c, a, b in _parity) and m.WEB_PROVIDERS == _wl.PROVIDERS,
          json.dumps([(c, a, b) for c, a, b in _parity if a != b])[:400])
    _SW = m.snapshot(env={}, today=T)["fields"]
    _SWb = m.snapshot(env={"WITT_WEB_LOCATOR": "brave", "BRAVE_API_KEY": "fake-key-smoke-models-never-in-output"}, today=T)
    _SWo = m.snapshot(env={"WITT_WEB_LOCATOR": "off", "BRAVE_API_KEY": "fake-key-smoke-models-never-in-output"}, today=T)
    _SWd = m.snapshot(env={"BRAVE_API_KEY": "fake-key-smoke-models-never-in-output"}, today=T)["fields"]
    _SWz = m.snapshot(env={"WITT_WEB_LOCATOR": "zzz"}, today=T)["fields"]
    check("ADR-0084 snapshot.fields: web.locator {'' , default-unset:WITT_WEB_LOCATOR} y web.provider {'off', 'default-derived:BRAVE_API_KEY absent'} "
          "sin llave; con llave y sin env → provider 'brave' 'default-derived:BRAVE_API_KEY present'; WITT_WEB_LOCATOR=brave → {'brave', env}; "
          "off → provider 'off' env; 'zzz' → locator '' default-invalid-env y provider 'off' 'default-invalid-env:WITT_WEB_LOCATOR'; la llave JAMÁS "
          "aparece en el snapshot; panel_signature INTACTA (== golden 9d90c01) con el localizador en brave/off — FUERA de la firma",
          _SW["web.locator"] == {"value": "", "source": "default-unset:WITT_WEB_LOCATOR"}
          and _SW["web.provider"] == {"value": "off", "source": "default-derived:BRAVE_API_KEY absent"}
          and _SWd["web.provider"] == {"value": "brave", "source": "default-derived:BRAVE_API_KEY present"}
          and _SWb["fields"]["web.locator"] == {"value": "brave", "source": "env:WITT_WEB_LOCATOR"}
          and _SWb["fields"]["web.provider"] == {"value": "brave", "source": "env:WITT_WEB_LOCATOR"}
          and _SWo["fields"]["web.provider"] == {"value": "off", "source": "env:WITT_WEB_LOCATOR"}
          and _SWz["web.locator"] == {"value": "", "source": "default-invalid-env:WITT_WEB_LOCATOR"}
          and _SWz["web.provider"] == {"value": "off", "source": "default-invalid-env:WITT_WEB_LOCATOR"}
          and "fake-key-smoke-models" not in json.dumps(_SWb) and "fake-key-smoke-models" not in json.dumps(_SWo)
          and _SWb["panel_signature"] == _SWo["panel_signature"] == PANEL_SIGNATURE_GOLDEN_9D90C01 == sig0,
          f"loc={_SW['web.locator']} prov={_SW['web.provider']} sig={_SWb['panel_signature']}")
except Exception as e:  # pragma: no cover — W2 es dueño de web_locator.py; si no importa, se declara
    check(f"ADR-0084: lib.web_locator importable para la paridad de env ({type(e).__name__}: {str(e)[:100]})", False)
    check("ADR-0084: env_value web (no medida)", False)
    check("ADR-0084: snapshot web.* (no medido)", False)

# --- compose ∩ README ⊇ ENV_TABLE (C8 entregó las 27 de 0082; F7 es dueño de las 20 de 0083: ese check FALLA hasta que entregue) ---
_compose = (HERE / "docker-compose.query.yml").read_text(encoding="utf-8")
_readme = (HERE / "README.md").read_text(encoding="utf-8")
_compose_vars = set(re.findall(r"^\s*-\s*([A-Z][A-Z0-9_]+)=", _compose, re.M))
_missing_81 = sorted(v for v in ENV_ADR_0081 if v not in _compose_vars or f"`{v}`" not in _readme)
_missing_82 = sorted(v for v in ENV_ADR_0082 if v not in _compose_vars or f"`{v}`" not in _readme)
_missing_83 = sorted(v for v in ENV_ADR_0083 if v not in _compose_vars or f"`{v}`" not in _readme)
_missing_84 = sorted(v for v in ENV_ADR_0084 if v not in _compose_vars or f"`{v}`" not in _readme)
check("ENV_TABLE ⊆ compose ∩ README — las 21 env de ADR-0081 declaradas en docker-compose.query.yml (- VAR=${VAR:-…}) y en README.md (`VAR`)",
      not _missing_81, f"faltan={_missing_81}")
check("ENV_TABLE ⊆ compose ∩ README — las 27 env de ADR-0082 (ENV_ADR_0082) declaradas en compose (bloque ADR-0082 tras WITT_CONFIG_LEDGER, "
      "27 placeholders ${VAR:-default}) y en README (tabla de env). Dueño: C8. Hasta que aterrice este check FALLA y ES lo esperado "
      "(patrón del gate M.4 de ADR-0081); la lista de faltantes se imprime",
      not _missing_82, f"{len(_missing_82)} faltan: {_missing_82}")
check("ENV_TABLE ⊆ compose ∩ README — las 20 env de ADR-0083 (ENV_ADR_0083) declaradas en compose (bloque ADR-0083 tras el bloque 0082, "
      "20 placeholders ${VAR:-default}) y en README (tabla de env). Dueño: F7. Hasta que aterrice este check FALLA y ES lo esperado "
      "(patrón del gate M.4 de ADR-0081 / C8 de ADR-0082); la lista de faltantes se imprime",
      not _missing_83, f"{len(_missing_83)} faltan: {_missing_83}")
check("ENV_TABLE ⊆ compose ∩ README — las 17 env de ADR-0084 (ENV_ADR_0084) declaradas en compose (bloque ADR-0084 tras el bloque 0083, "
      "17 placeholders ${VAR:-default}) y en README (tabla de env). Dueño: W7",
      not _missing_84, f"{len(_missing_84)} faltan: {_missing_84}")
_brave_compose = re.search(r"^\s*-\s*BRAVE_API_KEY=\$\{BRAVE_API_KEY:-\}.*$", _compose, re.M)
check("ADR-0084 (secreto) BRAVE_API_KEY NO está en models.ENV_TABLE (la tabla no registra secretos; sólo su PRESENCIA viaja) pero SÍ en compose "
      "como placeholder `${BRAVE_API_KEY:-}` con «never git» en su comentario y en README (`BRAVE_API_KEY` con «never git»)",
      "BRAVE_API_KEY" not in m.ENV_TABLE and _brave_compose is not None and "never git" in _brave_compose.group(0)
      and "`BRAVE_API_KEY`" in _readme and "never git" in _readme,
      f"compose={_brave_compose.group(0)[:120] if _brave_compose else None}")

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

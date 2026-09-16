"""
models.py — ADR-0081 (A): la ÚNICA tabla de modelos del repo y sus dos generaciones (g2-2026-09 / g1-2026-08).

Hasta f57a3d3 había CUATRO verdades de modelo desincronizables (runs.SYNTH_MODEL, question_agent.QUESTION_MODEL,
composite_auditor.DEFAULT_PANEL con una env evaluada EN IMPORT, evaluation/run_held_out.JUDGE_PANEL) más la
tabla de precios runs.PRICES_PER_MTOK_USD. Este módulo es la verdad única: los literales de modelo viven SOLO
aquí (gate estático en smoke_models.py); runs/composite_auditor/question_agent/app leen la tabla EN TIEMPO DE
LLAMADA, jamás en import.

Doctrina (CLAUDE.md §7 + ADR-0043): tres estados (llave ausente ≠ null declarado ≠ valor); toda elección lleva
su FUENTE (`env:<VAR>` · `default:<gen>` · `default-invalid-env:<VAR> (<motivo>)` · `auto-retire:<a>-><b>`);
un id que la tabla no conoce se USA tal cual (known False, familia por prefijo) — sustituir la elección explícita
del operador sería corregir en silencio; sólo se RECHAZA lo que la tabla sabe que ROMPE (excluded, familia
incompatible). Kill-switch declarado: WITT_MODEL_GENERATION=g1-2026-08 devuelve los defaults y TOPES de f57a3d3.

stdlib puro; sin `from lib import` (composite_auditor lo importa en duro y runs/app lo importan vía sys.path).
Nada aquí toca red, BD ni llaves API: `snapshot()` lee SÓLO las envs declaradas en ENV_TABLE/SNAPSHOT_ALSO_READS
y pasa cada valor por un cinturón anti-secreto.

ADR-0082 (D.2) — el consejo de criterio: rol `council` FUERA de PIPELINE_ROLES (COUNCIL_ROLES), así
`panel_signature` y `role.<rol>` del snapshot no cambian con el consejo encendido ni apagado (la serie de
ADR-0087 no se corta); env `WITT_MODEL_COUNCIL`, default claude-opus-5 en g2 / claude-opus-4-8 en g1 (declarado:
g1 no tenía consejo, la llave existe para que resolve_role('council') no lance), tope `max_tokens.council`
4000 (g2) / 1200 (g1); `WITT_COUNCIL_EFFORT` (default 'medium', E2) fijo por ruta — `council_effort()`;
CACHE_MULTIPLIERS / cache_prices() para cotizar la caché de prompt (clase derivada, no medida); ENV_TABLE gana
las 27 env del consejo (ENV_ADR_0082) con lectores tolerantes (kinds nuevos `bool` y `float`); SNAPSHOT_FIELDS
+= role.council, council.enabled, council.full, council.effort, council.cache_ttl (una fila `new-field` en
config_history al arrancar: excepción DECLARADA del kill-switch, ADR-0082 (L.2)(ii)).
"""
import datetime as _dt
import hashlib
import json
import os
import re

# ---------------------------------------------------------------------------------------------------------------
# 1. Identidad de la tabla
# ---------------------------------------------------------------------------------------------------------------
MODELS_TABLE_VERSION = "g2-2026-09"
MODEL_TABLE_AS_OF = "2026-09-15"
# Precios: el mismo literal que runs.PRICES_AS_OF tenía en f57a3d3 (runs lo aliasa a este nombre desde 1.10).
PRICES_AS_OF = "2026-09"   # verified: 2026-09-08 source: platform.claude.com/docs/en/about-claude/pricing · developers.openai.com/api/docs/pricing

# Vocabularios CERRADOS (viajan congelados junto al dato — los smokes y el gate de paridad los leen).
FAMILIES = ("anthropic", "openai")
FAMILY_UNKNOWN = "unknown"
TOOL_CALL_APIS = ("anthropic-messages", "openai-responses", "openai-chat-completions")   # los del despacho (C.3)
APIS = TOOL_CALL_APIS + ("openai-embeddings",)   # + el transporte de la fila `embed` (no es modelo de herramientas)
STATUSES = ("active", "retiring", "bridge", "candidate", "excluded", "not-adopted", "previous-generation", "embed")
THINKING_DEFAULTS = ("adaptive", "off", "n/a")
MODEL_ROW_FIELDS = ("family", "api", "api_verified", "status", "thinking_default", "reasoning", "retire_not_before",
                    "successor", "price_in", "price_out", "verified_on", "source", "note")

_PRICE_SRC = ("ADR-0081 (A); precio verificado 2026-09-08 (runs.PRICES_AS_OF @ f57a3d3): "
              "platform.claude.com/docs/en/about-claude/pricing")
_PRICE_SRC_OAI = ("ADR-0081 (A); precio verificado 2026-09-08 (runs.PRICES_AS_OF @ f57a3d3): "
                  "developers.openai.com/api/docs/pricing")


def _row(family, api, api_verified, status, thinking_default, reasoning, price_in, price_out, source, note,
         retire_not_before=None, successor=None, verified_on=MODEL_TABLE_AS_OF):
    """Una fila con TODAS las llaves (forma cerrada: retire_not_before/successor son null declarado cuando no
    aplican, jamás llaves ausentes)."""
    assert family in FAMILIES and api in APIS and status in STATUSES and thinking_default in THINKING_DEFAULTS
    return {"family": family, "api": api, "api_verified": bool(api_verified), "status": status,
            "thinking_default": thinking_default, "reasoning": bool(reasoning),
            "retire_not_before": retire_not_before, "successor": successor,
            "price_in": price_in, "price_out": price_out, "verified_on": verified_on, "source": source, "note": note}


# ---------------------------------------------------------------------------------------------------------------
# 2. LA tabla (9 filas). `api_verified` = el transporte con tool forzado fue MEDIDO en vivo con ESTE modelo por
#    este código (no "el proveedor dice que funciona"); False = pendiente de un gate en vivo (LG1/LG2/LG3).
# ---------------------------------------------------------------------------------------------------------------
MODELS = {
    "claude-opus-5": _row(
        "anthropic", "anthropic-messages", False, "active", "adaptive", False, 5.0, 25.0, _PRICE_SRC,
        "Sintetizador/planner/elicitación/agente de preguntas y juez correctness en g2 (decisión de Emmanuel). "
        "PIENSA por default (thinking adaptativo; max_tokens acota pensamiento + respuesta — topes g2). "
        "api_verified False: forced tool_use bajo los schemas REALES y topes g2 lo mide LG1 (Emmanuel)."),
    "claude-sonnet-5": _row(
        "anthropic", "anthropic-messages", True, "active", "adaptive", False, 2.0, 10.0, _PRICE_SRC,
        "Juez overclaim (producción desde ADR-0047); sucesor declarado de haiku-4-5 en evidence-grounding (E)."),
    "claude-haiku-4-5-20251001": _row(
        "anthropic", "anthropic-messages", True, "retiring", "off", False, 1.0, 5.0, _PRICE_SRC,
        "Juez evidence-grounding. Se retira >= 2026-10-15 (decisión de Emmanuel): la tabla declara el sucesor "
        "(DATO), la env lo ejecuta (ACTO) — ver retirement_due()/WITT_PANEL_AUTO_RETIRE.",
        retire_not_before="2026-10-15", successor={"reviewer": "claude-sonnet-5", "lens": "evidence-grounding"}),
    "claude-opus-4-8": _row(
        "anthropic", "anthropic-messages", True, "previous-generation", "off", False, 5.0, 25.0, _PRICE_SRC,
        "El modelo de g1 (f57a3d3) en síntesis/planner/elicitación/preguntas/correctness; sigue cotizado para "
        "que /usage recotice registros históricos sin missing_price."),
    "claude-fable-5-1": _row(
        "anthropic", "anthropic-messages", False, "excluded", "adaptive", False, 10.0, 50.0, _PRICE_SRC,
        "EXCLUIDO (decisión de Emmanuel): 400 en tool_choice forzado observado (la guía de migración de Fable 5.1 "
        "lo documenta: tool_choice type 'tool'/'any' no soportados); retención 30 días obligatoria. Supersede la "
        "cláusula '>= 1 Fable en el panel' de ADR-0031. Cotizado por si aparece en un registro."),
    "gpt-4o": _row(
        "openai", "openai-chat-completions", True, "bridge", "n/a", False, 2.5, 10.0, _PRICE_SRC_OAI,
        "Juez reproducibility HOY (el camino probado en vivo por chat.completions). Puente hasta que LG3 pase con "
        "Astra y Emmanuel confirme acceso (E1). Nota ATESTIGUADA del brief v3: su snapshot se apaga 2026-10-23."),
    "gpt-6-astra": _row(
        "openai", "openai-responses", False, "candidate", "n/a", True, 10.0, 50.0, _PRICE_SRC_OAI,
        "ÚNICO juez OpenAI decidido por Emmanuel. Exige la Responses API (verificado en vivo por Emmanuel: "
        "chat.completions no sirve). api_verified False: el caller Responses de ESTE código lo mide LG2/LG3. "
        "reasoning True: WITT_OPENAI_REASONING_EFFORT se envía sólo a modelos con este flag."),
    "gpt-5.6-sol": _row(
        "openai", "openai-responses", False, "not-adopted", "n/a", True, 4.0, 20.0, _PRICE_SRC_OAI,
        "Sin puente, decisión de Emmanuel (plan v3). Cotizado por si aparece en un registro."),
    "text-embedding-3-small": _row(
        "openai", "openai-embeddings", True, "embed", "n/a", False, 0.02, 0.0, _PRICE_SRC_OAI,
        "Embeddings del índice de la DATA INAMOVIBLE (1536-dim). No es modelo de herramientas: en un asiento de "
        "rol se rechaza como excluded-model."),
}

# Precios: EXACTAMENTE el dict runs.PRICES_PER_MTOK_USD de f57a3d3 (golden en smoke_models.py).
_PRICES = {mid: (row["price_in"], row["price_out"]) for mid, row in MODELS.items()}


def prices():
    """{model_id: (usd_in_per_Mtok, usd_out_per_Mtok)} — insumo de la PROYECCIÓN de costo (ADR-0051), no medición.
    Copia fresca: nadie muta la tabla desde fuera. runs.PRICES_PER_MTOK_USD = models.prices() (nombre conservado)."""
    return dict(_PRICES)


# ADR-0082 (D.2): multiplicadores PUBLICADOS de la caché de prompt sobre el precio de entrada — escritura 1.25×
# (TTL 5 min) · 2× (TTL 1 h) · lectura 0.1×. Verificados contra la referencia (skill claude-api,
# shared/prompt-caching.md, cache 2026-06-24, § Economics). Son insumo de la PROYECCIÓN de USD de runs._token_usage
# (H): los TOKENS de caché se MIDEN (usage.cache_creation_input_tokens / cache_read_input_tokens); el USD es
# proyección con clase declarada. Cambian de valor sólo con un ADR (registros viejos conservan su `as_of`).
CACHE_MULTIPLIERS = {"write_5m": 1.25, "write_1h": 2.0, "read": 0.1}
CACHE_MULTIPLIERS_SOURCE = ("platform.claude.com pricing (prompt caching); skill claude-api shared/prompt-caching.md "
                            "cached 2026-06-24")
CACHE_AS_OF = "2026-06-24"
CACHE_PRICE_CLASS = "derived-from-published-multipliers"   # hasta que LG1 mida cache_creation/cache_read reales
CACHE_PRICE_FIELDS = ("write_5m", "write_1h", "read", "price_in", "class", "multipliers", "source", "as_of")


def cache_prices(model):
    """{write_5m, write_1h, read, price_in, class, multipliers, source, as_of} en USD por Mtok DERIVADOS de
    `price_in` × CACHE_MULTIPLIERS (clase 'derived-from-published-multipliers'); None para un modelo que la tabla
    no cotiza (priced False → runs lo declara missing_price, jamás un 0)."""
    p = _PRICES.get(model)
    if p is None:
        return None
    price_in = p[0]
    return {"write_5m": price_in * CACHE_MULTIPLIERS["write_5m"], "write_1h": price_in * CACHE_MULTIPLIERS["write_1h"],
            "read": price_in * CACHE_MULTIPLIERS["read"], "price_in": price_in, "class": CACHE_PRICE_CLASS,
            "multipliers": dict(CACHE_MULTIPLIERS), "source": CACHE_MULTIPLIERS_SOURCE, "as_of": CACHE_AS_OF}


# ---------------------------------------------------------------------------------------------------------------
# 3. Roles, lentes, envs, generaciones
# ---------------------------------------------------------------------------------------------------------------
LENSES = ("correctness", "overclaim", "evidence-grounding", "reproducibility")   # orden FIJO del panel
LENS_FAMILY = {"correctness": "anthropic", "overclaim": "anthropic", "evidence-grounding": "anthropic",
               "reproducibility": "openai"}
PIPELINE_ROLES = ("synthesizer", "planner", "elicitation", "question_agent")
JUDGE_ROLES = tuple("judge." + lens for lens in LENSES)
# ADR-0082 (D.2): el rol del consejo va FUERA de PIPELINE_ROLES a propósito — panel_signature() itera
# PIPELINE_ROLES y snapshot() escribe `role.<rol>` por PIPELINE_ROLES + el suyo propio; la firma de toda corrida
# queda INTACTA con o sin consejo (medido en smoke_models con el golden @ 9d90c01).
COUNCIL_ROLES = ("council",)
ROLES = PIPELINE_ROLES + JUDGE_ROLES + COUNCIL_ROLES
# Familia que el rol EXIGE: los roles del pipeline hablan anthropic-messages con schemas Anthropic
# (runs._anthropic_tool_call); cada lente tiene su familia (ADR-0047 d.4 / ADR-0038: reproducibility es el juez
# cross-provider); el consejo habla anthropic-messages con tools forzados (council.py, ADR-0082 C.2).
ROLE_FAMILY = {**{r: "anthropic" for r in PIPELINE_ROLES}, **{"judge." + l: f for l, f in LENS_FAMILY.items()},
               **{r: "anthropic" for r in COUNCIL_ROLES}}
ROLE_ENVS = {
    "synthesizer": "WITT_MODEL_SYNTH", "planner": "WITT_MODEL_PLANNER", "elicitation": "WITT_MODEL_ELICIT",
    "question_agent": "WITT_MODEL_QUESTION",
    "judge.correctness": "WITT_JUDGE_CORRECTNESS", "judge.overclaim": "WITT_JUDGE_OVERCLAIM",
    "judge.evidence-grounding": "WITT_JUDGE_GROUNDING",
    "judge.reproducibility": "OPENAI_JUDGE_MODEL",   # conserva su nombre: es la palanca que Emmanuel flipará (E1)
    "council": "WITT_MODEL_COUNCIL",                # ADR-0082 (D.2): el modelo de los 17 miembros (3 rondas)
}
# Qué tope de la generación aplica a cada rol (los jueces Anthropic comparten uno; el juez OpenAI NO usa
# max_tokens de aquí: su tope es del transporte — WITT_OPENAI_MAX_OUTPUT_TOKENS en Responses, 1200 en chat).
# `council`: techo, no gasto — opus-5 piensa por default y el tope acota pensamiento + respuesta del tool.
MAX_TOKENS_KEYS = ("synthesizer", "planner", "elicitation", "question_agent", "judge-anthropic", "council")
_ROLE_TOPE = {**{r: r for r in PIPELINE_ROLES}, **{"judge." + l: "judge-anthropic" for l in LENSES},
              **{r: r for r in COUNCIL_ROLES}}

GENERATIONS = {
    "g2-2026-09": {
        "as_of": "2026-09-15", "source": "ADR-0081 (A) — decisiones de Emmanuel del plan v3 (2026-09-14)",
        "defaults": {
            "synthesizer": "claude-opus-5", "planner": "claude-opus-5", "elicitation": "claude-opus-5",
            "question_agent": "claude-opus-5",
            "judge.correctness": "claude-opus-5", "judge.overclaim": "claude-sonnet-5",
            "judge.evidence-grounding": "claude-haiku-4-5-20251001", "judge.reproducibility": "gpt-4o",
            # ADR-0082 (D.2): el consejo de criterio = opus-5 vía la tabla (decisión de Emmanuel, brief §14);
            # Sonnet es palanca declarada (WITT_MODEL_COUNCIL), no default (ADR-0082 K.f)
            "council": "claude-opus-5",
        },
        # TOPES, no gasto (C.4): opus-5 piensa por default y max_tokens acota pensamiento + respuesta; con los
        # topes g1 la mini-llamada de confianza (300) se truncaría en cada corrida. `council` 4000 (ADR-0082 D.2):
        # 17 llamadas de CRITERIO con tool forzado; el tope acota pensamiento adaptativo + el tool_use.
        "max_tokens": {"synthesizer": 8000, "planner": 4000, "elicitation": 2000, "question_agent": 4000,
                       "judge-anthropic": 4000, "council": 4000},
        "note": "panel CONSERVA gpt-4o hasta que LG3 pase con gpt-6-astra (OPENAI_JUDGE_MODEL es la palanca)",
    },
    "g1-2026-08": {
        "as_of": "2026-08", "source": "f57a3d3 byte a byte (runs.SYNTH_MODEL, composite_auditor.DEFAULT_PANEL, "
                                      "topes de CONF_TOOL/PLAN_TOOL/SYNTH_TOOL/QUESTION_TOOL/jueces)",
        "defaults": {
            "synthesizer": "claude-opus-4-8", "planner": "claude-opus-4-8", "elicitation": "claude-opus-4-8",
            "question_agent": "claude-opus-4-8",
            "judge.correctness": "claude-opus-4-8", "judge.overclaim": "claude-sonnet-5",
            "judge.evidence-grounding": "claude-haiku-4-5-20251001", "judge.reproducibility": "gpt-4o",
            # ADR-0082 (D.2), DECLARADO: g1 (f57a3d3) no tenía consejo; la llave existe para que
            # resolve_role('council') no lance bajo el kill-switch de generación — no es un default de f57a3d3
            "council": "claude-opus-4-8",
        },
        "max_tokens": {"synthesizer": 2500, "planner": 1200, "elicitation": 300, "question_agent": 1200,
                       "judge-anthropic": 1200, "council": 1200},   # council 1200: declarado (ADR-0082 D.2), no f57a3d3
        "note": "kill-switch (M.2): WITT_MODEL_GENERATION=g1-2026-08 restaura los 8 defaults y los 5 topes de hoy "
                "(council opus-4-8 / 1200 es una llave DECLARADA por ADR-0082, g1 no tenía consejo)",
    },
}
GENERATION_DEFAULT = "g2-2026-09"
GENERATION_ENV = "WITT_MODEL_GENERATION"
AUTO_RETIRE_ENV = "WITT_PANEL_AUTO_RETIRE"
OPENAI_API_ENV = "WITT_OPENAI_API"
OPENAI_API_CHOICES = ("table", "responses", "chat-completions")
EMBED_MODEL_ENV = "OPENAI_EMBED_MODEL"
REASONING_EFFORTS = ("low", "medium", "high")                      # Responses API `reasoning.effort`
ANTHROPIC_EFFORTS = ("low", "medium", "high", "xhigh", "max")      # Messages API `output_config.effort`
# ADR-0082 (D.2 / E2): el effort del consejo se FIJA por ruta para las 17 llamadas de las tres rondas (cambiarlo
# por petición invalida la caché de messages y, según el modelo, también tools+system — "pin per route"). Default
# 'medium' (17 llamadas de CRITERIO, no de síntesis). El literal `inherit` es la alternativa de E2 como palanca
# DECLARADA (hereda WITT_ANTHROPIC_EFFORT; vacío = default de la API) — ver council_effort().
COUNCIL_EFFORT_ENV = "WITT_COUNCIL_EFFORT"
COUNCIL_EFFORT_DEFAULT = "medium"
COUNCIL_EFFORT_INHERIT = "inherit"
COUNCIL_EFFORT_CHOICES = ANTHROPIC_EFFORTS + (COUNCIL_EFFORT_INHERIT,)
COUNCIL_CACHE_TTLS = ("5m", "1h")                                  # WITT_COUNCIL_CACHE_TTL (catalog_cards.CACHE_TTLS)

# Motivos CERRADOS de rechazo de una env (van dentro de `default-invalid-env:<VAR> (<motivo>)`).
INVALID_ENV_REASONS = ("excluded-model", "wrong-family-for-lens", "wrong-family-for-role", "same-model-same-lens",
                       "unknown-generation", "secret-like-value")
# Prefijos de fuente (la webapp tipa ModelSource por prefijo).
SOURCE_PREFIXES = ("env:", "default:", "default-invalid-env:", "default-unset:", "auto-retire:")
WARNING_PREFIXES = ("retirement-due:", "past-retirement:", "invalid-env:", "api-unverified:", "not-adopted:")
RELATIONS = ("exact", "prefix", "different", "not-reported")
THINKING_STATES = {
    "adaptive": "adaptive-by-api-default (tokens dentro de output_tokens)",
    "off": "off-by-model-default",
    "n/a": "not-applicable (sin pensamiento declarado en tabla)",
    None: "unknown-to-table",
}

# La tabla de env del ADR-0081 (todas con default declarado; lectores tolerantes; toda env = reinicio).
# `kind` gobierna env_value(): str | int (>= minimum) | bool01 | choice | effort (vacío = no se envía).
ENV_TABLE = {
    "WITT_MODEL_GENERATION":        {"default": GENERATION_DEFAULT, "kind": "choice", "choices": tuple(GENERATIONS),
                                     "reader": "models.resolve_role", "effect": "generación de defaults y topes; g1-2026-08 = hoy byte a byte"},
    "WITT_MODEL_SYNTH":             {"default": "", "kind": "str", "reader": "models.resolve_role", "effect": "modelo del sintetizador"},
    "WITT_MODEL_PLANNER":           {"default": "", "kind": "str", "reader": "models.resolve_role", "effect": "modelo del planner"},
    "WITT_MODEL_ELICIT":            {"default": "", "kind": "str", "reader": "models.resolve_role", "effect": "modelo de la elicitación"},
    "WITT_MODEL_QUESTION":          {"default": "", "kind": "str", "reader": "models.resolve_role", "effect": "modelo del agente de preguntas"},
    "WITT_JUDGE_CORRECTNESS":       {"default": "", "kind": "str", "reader": "models.panel", "effect": "asiento correctness (anthropic)"},
    "WITT_JUDGE_OVERCLAIM":         {"default": "", "kind": "str", "reader": "models.panel", "effect": "asiento overclaim (anthropic)"},
    "WITT_JUDGE_GROUNDING":         {"default": "", "kind": "str", "reader": "models.panel", "effect": "asiento evidence-grounding; el sucesor de haiku se fija AQUÍ (E)"},
    "OPENAI_JUDGE_MODEL":           {"default": "", "kind": "str", "reader": "models.panel", "effect": "asiento reproducibility (openai); gpt-6-astra SÓLO tras LG3", "preexisting": True},
    "WITT_PANEL_AUTO_RETIRE":       {"default": "0", "kind": "bool01", "reader": "models.panel", "effect": "1 = sucesor automático al llegar retire_not_before (declarado + fila runtime-diff)"},
    "WITT_PANEL_MIN_FAMILIES":      {"default": "2", "kind": "int", "minimum": 0, "reader": "composite_auditor.audit", "effect": "cuórum de familias; 0|1 = kill-switch (gating false)"},
    "WITT_PANEL_MIN_LENSES":        {"default": "3", "kind": "int", "minimum": 0, "reader": "composite_auditor.audit", "effect": "cuórum de lentes; 0|1 = kill-switch"},
    "WITT_OPENAI_API":              {"default": "table", "kind": "choice", "choices": OPENAI_API_CHOICES, "reader": "models.api_of", "effect": "responses fuerza Responses para todo juez OpenAI; chat-completions = caller de hoy"},
    "WITT_OPENAI_STORE":            {"default": "0", "kind": "bool01", "reader": "composite_auditor._responses_kwargs", "effect": "store de responses.create (default de la API: true)"},
    "WITT_OPENAI_MAX_OUTPUT_TOKENS": {"default": "4000", "kind": "int", "minimum": 1, "reader": "composite_auditor._responses_kwargs", "effect": "tope (no gasto) del camino Responses; chat conserva 1200"},
    "WITT_OPENAI_REASONING_EFFORT": {"default": "", "kind": "effort", "choices": REASONING_EFFORTS, "reader": "composite_auditor._responses_kwargs", "effect": "reasoning.effort sólo con reasoning True en tabla"},
    "WITT_OPENAI_TIMEOUT_S":        {"default": "120", "kind": "int", "minimum": 1, "reader": "composite_auditor._openai_client", "effect": "timeout por llamada del juez OpenAI; regla (1+retries)×timeout×2 <= 900"},
    "WITT_ANTHROPIC_EFFORT":        {"default": "", "kind": "effort", "choices": ANTHROPIC_EFFORTS, "reader": "composite_auditor._anthropic_tool_call", "effect": "output_config.effort sólo a modelos thinking_default 'adaptive'"},
    "WITT_ANTHROPIC_EFFORT_ELICIT": {"default": "", "kind": "effort", "choices": ANTHROPIC_EFFORTS, "reader": "runs._elicit_confidence", "effect": "override para CONF_TOOL (vacío = hereda WITT_ANTHROPIC_EFFORT)"},
    "WITT_CONFIG_LEDGER":           {"default": "1", "kind": "bool01", "reader": "app.config_ledger_boot/observe", "effect": "0 = cero escrituras; ledger_state lo dice"},
    "WITT_JUDGE_RETRIES":           {"default": "1", "kind": "int", "minimum": 0, "reader": "composite_auditor.audit", "effect": "sin cambio (ADR-0080); entra al snapshot", "preexisting": True},
    # ---- ADR-0082 (D.2): las 27 env del consejo de criterio (tabla de env del ADR; toda env = reinicio). Kinds nuevos:
    # `bool` = tolerante 1/true/yes/on · 0/false/no/off (los mismos literales que agent_matrix.council_full y
    # catalog_cards.cache_config, así el snapshot y el lector del dueño jamás divergen); `float` con rango.
    "WITT_COUNCIL":                 {"default": "1", "kind": "bool", "reader": "council.enabled · app.create_plan · runs.execute_run", "effect": "kill-switch global: 0 = sin job en el plan, sin r2/r3, componente 'kill-switch WITT_COUNCIL=0' (gating false), camino 9d90c01 con las excepciones de (L.2)", "adr": "0082"},
    "WITT_COUNCIL_FULL":            {"default": "0", "kind": "bool", "reader": "agent_matrix.council_members (al ENCOLAR r1)", "effect": "1 = los 8 operativos también se sientan (N=25, cuórum 15); requisitos from_operative contados aparte", "adr": "0082"},
    "WITT_MODEL_COUNCIL":           {"default": "", "kind": "str", "reader": "models.resolve_role('council')", "effect": "modelo de los miembros (vacía → claude-opus-5 en g2 · claude-opus-4-8 en g1); fable rechazado excluded-model; tope max_tokens.council 4000/1200", "adr": "0082"},
    "WITT_COUNCIL_EFFORT":          {"default": COUNCIL_EFFORT_DEFAULT, "kind": "effort", "choices": COUNCIL_EFFORT_CHOICES, "reader": "models.council_effort → council.build_request", "effect": "output_config.effort FIJO por ruta para las 3 rondas (cambiarlo por petición invalida la caché); sólo a modelos adaptive; 'inherit' = hereda WITT_ANTHROPIC_EFFORT (alternativa E2, declarada)", "adr": "0082"},
    "WITT_CG_COUNCIL_COMPONENT":    {"default": "1", "kind": "bool", "reader": "competence.env_config", "effect": "1 = council_uncovered_must GATEA cuando state ∈ {checked, vacuous, incomplete}; 0 = informativo declarado (fuera de conjunction)", "adr": "0082"},
    "WITT_COUNCIL_RECOVERAGE":      {"default": "1", "kind": "bool", "reader": "runs.execute_run", "effect": "1 = ronda r3 (sólo si n_admitted_total > 0, sólo dueños de must sin cubrir); 0 = post_search.state 'not-run (kill-switch …)'", "adr": "0082"},
    "WITT_COUNCIL_ORIGINS":         {"default": "production", "kind": "str", "reader": "app.create_plan (CSV tolerante; 'all' = sin filtro declarado)", "effect": "orígenes del PROCESO que encolan r1; smoke/fixture/dev-offline → 'not-requested (origin …)'", "adr": "0082"},
    "WITT_COUNCIL_WORKERS":         {"default": "1", "kind": "int", "minimum": 0, "reader": "runs.start_workers → council_jobs.worker_loop", "effect": "hilos daemon council-worker-N que reclaman plans.council_state='queued'", "adr": "0082"},
    "WITT_COUNCIL_DEDUP_S":         {"default": "600", "kind": "int", "minimum": 0, "reader": "app.create_plan", "effect": "ventana del dedup del doble clic (misma pregunta+entidades+padre, mismo usuario, r1 queued|running → se reutiliza el plan vivo)", "adr": "0082"},
    "WITT_COUNCIL_MAX_QUEUED_PER_USER": {"default": "3", "kind": "int", "minimum": 0, "reader": "app.create_plan", "effect": "tope de jobs r1 queued por usuario; el excedente nace 'not-requested (queue-cap per user)'", "adr": "0082"},
    "WITT_COUNCIL_CONCURRENCY":     {"default": "6", "kind": "int", "minimum": 1, "reader": "council.run_round (clamp 1..25)", "effect": "max_workers del pool por ronda; el miembro #1 va SOLO y el resto tras su respuesta", "adr": "0082"},
    "WITT_COUNCIL_MEMBER_TIMEOUT_S": {"default": "120", "kind": "int", "minimum": 1, "reader": "council.run_round", "effect": "future.result(timeout) y timeout del socket por miembro; vencido → fila 'timeout', la ronda sigue", "adr": "0082"},
    "WITT_COUNCIL_ROUND_BUDGET_S":  {"default": "300", "kind": "int", "minimum": 1, "reader": "council.run_round", "effect": "presupuesto de reloj por ronda; agotado → skipped-budget (cero llamadas), en vuelo abandonados y contados; regla ≤ WITT_REAP_STALE_S − 300", "adr": "0082"},
    "WITT_COUNCIL_MEMBER_RETRIES":  {"default": "1", "kind": "int", "minimum": 0, "reader": "council.run_round → _anthropic_tool_call(retries=)", "effect": "intentos ADICIONALES por miembro (transporte con Retry-After; contenido); refusal/4xx nunca; attempts ≤ 2", "adr": "0082"},
    "WITT_COUNCIL_QUORUM":          {"default": "0.6", "kind": "float", "min_exclusive": 0.0, "maximum": 1.0, "reader": "council.round_valid", "effect": "fracción de miembros válidos (ceil(q·N): 17 → 11, 25 → 15); fuera de (0,1] → default declarado", "adr": "0082"},
    "WITT_COUNCIL_MAX_REQUIREMENTS": {"default": "24", "kind": "int", "minimum": 1, "reader": "council.aggregate_requirements", "effect": "tope del ledger; truncated, n_truncated, truncated_ids[]", "adr": "0082"},
    "WITT_COUNCIL_MAX_PER_MEMBER":  {"default": "5", "kind": "int", "minimum": 1, "reader": "council.validate_tool_input (y maxItems del schema)", "effect": "requisitos por miembro; excedente descartado en orden y contado", "adr": "0082"},
    "WITT_COUNCIL_R2_EVIDENCE_CHARS": {"default": "24000", "kind": "int", "minimum": 1, "reader": "council.payload_r2", "effect": "tope de la vista de evidencia por miembro en r2/r3; payload_truncated declarado; acota tokens/min", "adr": "0082"},
    "WITT_COUNCIL_ATTESTATION_CHARS": {"default": "4000", "kind": "int", "minimum": 1, "reader": "app (ledger)", "effect": "tope de knowledge_now y de cada attested_text (600 en el frozen, truncated)", "adr": "0082"},
    "WITT_COUNCIL_CACHE":           {"default": "1", "kind": "bool", "reader": "catalog_cards.cache_config → council.build_system", "effect": "1 = cache_control en los dos bloques system; 0 = string concatenado (A/B medible en usage.cache_*)", "adr": "0082"},
    "WITT_COUNCIL_CACHE_TTL":       {"default": "5m", "kind": "choice", "choices": COUNCIL_CACHE_TTLS, "casefold": True, "reader": "catalog_cards.cache_config → council.build_system", "effect": "5m (escritura 1.25×) · 1h (2×) para el bloque de la ficha; E3 tras medir el hueco r1→r2", "adr": "0082"},
    "WITT_COUNCIL_INDEX":           {"default": "1", "kind": "bool", "reader": "council_index · app", "effect": "0 = GET /council/search 503 declarado, prior_observations {state 'disabled'}", "adr": "0082"},
    "WITT_COUNCIL_PRIOR_K":         {"default": "5", "kind": "int", "minimum": 0, "reader": "council_index.prior_observations (clamp 0..12)", "effect": "observaciones previas inyectadas en r1 (letras P-A…); 0 = ninguna", "adr": "0082"},
    "WITT_COUNCIL_PRIOR_KINDS":     {"default": "requirement,coverage,decision,gap_flag,panel_finding", "kind": "str", "reader": "council_index.prior_observations (CSV tolerante)", "effect": "kinds que ENTRAN al prompt de r1; 'comment' EXCLUIDO por default (inyección); la búsqueda siempre puede pedirlo", "adr": "0082"},
    "WITT_COUNCIL_INDEX_ORIGINS":   {"default": "production", "kind": "str", "reader": "council_index · /council/demand", "effect": "orígenes del corpus (NULL incluido y declarado, regla de precedent)", "adr": "0082"},
    "WITT_ANTHROPIC_MAX_INFLIGHT":  {"default": "8", "kind": "int", "minimum": 1, "reader": "composite_auditor._anthropic_tool_call", "effect": "BoundedSemaphore de PROCESO alrededor de urlopen para TODA llamada Anthropic; meta.queue_wait_s", "adr": "0082"},
    "WITT_ANTHROPIC_RETRY_AFTER_CAP_S": {"default": "30", "kind": "int", "minimum": 0, "reader": "composite_auditor._anthropic_tool_call", "effect": "tope al Retry-After honrado en http-429/529; sin cabecera, backoff de hoy", "adr": "0082"},
}
# Las env que ADR-0082 añade (27): gen_fixtures las quita del proceso (patrón ENV_ADR_0081) y smoke_models mide
# que compose ∩ README las declaran (C8). Vocabulario cerrado de kinds de ENV_TABLE (env_value los gobierna).
ENV_ADR_0082 = tuple(k for k, v in ENV_TABLE.items() if v.get("adr") == "0082")
ENV_KINDS = ("str", "int", "float", "bool01", "bool", "choice", "effort")
_BOOL_TRUTHY = ("1", "true", "yes", "on")
_BOOL_FALSEY = ("0", "false", "no", "off")
# Envs PREEXISTENTES que snapshot() también lee (default del dueño, declarado aquí sólo para el snapshot).
SNAPSHOT_ALSO_READS = {
    EMBED_MODEL_ENV: {"default": "text-embedding-3-small", "kind": "str", "owner": "rag_index/graphrag/embeddings.py · runs._token_usage"},
}

# Lista CERRADA de campos del snapshot (I): insumo del ledger config_history, de stage.models y de
# /config-history.current. Cada campo = {value, source}. JAMÁS una llave API.
SNAPSHOT_FIELDS = (
    "model_generation", "table_version", "panel_signature",
    "role.synthesizer", "role.planner", "role.elicitation", "role.question_agent",
    "panel.correctness", "panel.overclaim", "panel.evidence-grounding", "panel.reproducibility",
    "panel.min_families", "panel.min_lenses", "panel.auto_retire",
    "openai.api", "openai.store", "openai.max_output_tokens", "openai.timeout_s", "openai.reasoning_effort",
    "anthropic.effort", "anthropic.effort_elicit",
    "judge.retries", "prices.as_of", "contract.render_contract_version", "embed.model",
    "competence.gate", "search.harness", "revision.cycle",
    # ADR-0082 (D.2): el consejo entra al snapshot (una fila `new-field` en config_history al arrancar tras el
    # redeploy — excepción DECLARADA del kill-switch, (L.2)(ii)); role.council va aquí y NO en panel_signature
    "role.council", "council.enabled", "council.full", "council.effort", "council.cache_ttl",
)
COUNCIL_SNAPSHOT_FIELDS = ("role.council", "council.enabled", "council.full", "council.effort", "council.cache_ttl")
# Campos que models.py NO puede derivar (viven en runs/competence): el llamador (app.config_ledger_boot) los
# pasa en `extra={campo: {value, source}}`; ausentes → {value: None, source: 'not-provided-by-caller'} (null
# declarado, jamás un default duplicado de otro módulo).
EXTRA_FIELDS = ("contract.render_contract_version", "competence.gate", "search.harness", "revision.cycle")
NOT_PROVIDED = "not-provided-by-caller"

# Formas cerradas (R3 / smokes las comparan).
ROLE_RESOLVED_FIELDS = ("model", "source", "family", "family_source", "api", "api_source", "known", "priced",
                        "max_tokens", "generation", "generation_source")
PANEL_MEMBER_FIELDS = ("reviewer", "family", "family_source", "lens", "api", "api_source", "reviewer_source",
                       "known", "priced", "max_tokens")
RAN_FIELDS = ("requested", "reported", "relation", "thinking_state")
PANEL_RAN_FIELDS = ("lens", "reviewer", "reported", "relation", "api_used", "attempts")
PROVENANCE_FIELDS = ("generation", "generation_source", "table_version", "table_as_of", "panel_signature",
                     "roles", "ran", "rule")
PLANNER_PROVENANCES = ("plan_json", "plan_json (pre-1.10: source not recorded)", "no-plan")


# ---------------------------------------------------------------------------------------------------------------
# 4. Lectores de env tolerantes (patrón competence.env_config / runs._env_int_tolerante, ADR-0078)
# ---------------------------------------------------------------------------------------------------------------
def _env(env):
    return os.environ if env is None else env


def _raw(env, name):
    v = _env(env).get(name)
    return "" if v is None else str(v).strip()


_SECRET_RE = re.compile(r"(?i)(^sk-|api[_-]?key|token|secret|bearer)")


def _looks_secret(value):
    """Cinturón: un valor que parece llave jamás viaja en snapshot/warnings (S4 repite el cinturón al escribir)."""
    s = str(value)
    if _SECRET_RE.search(s):
        return True
    return len(s) >= 40 and re.fullmatch(r"[A-Za-z0-9_\-]+", s) is not None


def _redact(value, limit=60):
    return "<redactado: parece llave>" if _looks_secret(value) else str(value)[:limit]


def env_value(name, env=None):
    """(valor tipado, fuente) para una env de ENV_TABLE/SNAPSHOT_ALSO_READS. Fuente ∈ 'env:<VAR>' |
    'default-unset:<VAR>' | 'default-invalid-env:<VAR>'. Vacío/basura/fuera de rango → default DECLARADO, jamás
    tumba el proceso. S2/S3/S5 leen aquí sus envs para no duplicar defaults."""
    spec = ENV_TABLE.get(name) or SNAPSHOT_ALSO_READS.get(name)
    if spec is None:
        raise KeyError(f"env no declarada en models.ENV_TABLE: {name}")
    raw, default, kind = _raw(env, name), spec["default"], spec["kind"]

    def _typed(s):
        if kind == "int":
            v = int(s)
            if v < spec.get("minimum", 0):
                raise ValueError(s)
            return v
        if kind == "float":
            # ADR-0082: fracciones con rango declarado (WITT_COUNCIL_QUORUM ∈ (0, 1]); nan/inf caen fuera del rango
            v = float(s)
            if not (v > spec.get("min_exclusive", float("-inf"))) or v > spec.get("maximum", float("inf")):
                raise ValueError(s)
            return v
        if kind == "bool01":
            if s not in ("0", "1"):
                raise ValueError(s)
            return s == "1"
        if kind == "bool":
            # ADR-0082: los MISMOS literales que agent_matrix.council_full / catalog_cards.cache_config
            low = s.lower()
            if low in _BOOL_TRUTHY:
                return True
            if low in _BOOL_FALSEY:
                return False
            raise ValueError(s)
        if kind == "choice":
            if spec.get("casefold"):
                s = s.lower()   # ADR-0082: WITT_COUNCIL_CACHE_TTL '1H' == '1h' (paridad con catalog_cards.cache_config)
            if s not in spec["choices"]:
                raise ValueError(s)
            return s
        if kind == "effort":
            if s == "":
                return None
            if s.lower() not in spec["choices"]:
                raise ValueError(s)
            return s.lower()
        return s   # str

    if raw == "":
        return _typed(default), f"default-unset:{name}"
    try:
        return _typed(raw), f"env:{name}"
    except (ValueError, TypeError):
        return _typed(default), f"default-invalid-env:{name}"


def resolve_generation(env=None):
    """(generación, fuente). Fuente ∈ 'env:WITT_MODEL_GENERATION' | 'default-unset:…' |
    'default-invalid-env:WITT_MODEL_GENERATION (unknown-generation)'."""
    raw = _raw(env, GENERATION_ENV)
    if raw == "":
        return GENERATION_DEFAULT, f"default-unset:{GENERATION_ENV}"
    if raw in GENERATIONS:
        return raw, f"env:{GENERATION_ENV}"
    return GENERATION_DEFAULT, f"default-invalid-env:{GENERATION_ENV} (unknown-generation)"


def resolve_openai_api(env=None):
    """(table|responses|chat-completions, fuente) — WITT_OPENAI_API. Default 'table' (C.3: la decisión tomada
    conserva gpt-4o por chat.completions hasta el smoke vivo)."""
    return env_value(OPENAI_API_ENV, env)


def council_effort(env=None):
    """ADR-0082 (D.2 / E2): (effort | None, fuente) del rol `council`, FIJO por ruta para las 3 rondas.
    Vacía → 'medium' ('default-unset:WITT_COUNCIL_EFFORT'); ∈ ANTHROPIC_EFFORTS → ese ('env:WITT_COUNCIL_EFFORT');
    'inherit' (la alternativa de E2, declarada) → el valor de WITT_ANTHROPIC_EFFORT con fuente
    'env:WITT_COUNCIL_EFFORT (inherit -> <fuente de WITT_ANTHROPIC_EFFORT>)' — None = no se envía (default de la
    API); basura → 'medium' ('default-invalid-env:WITT_COUNCIL_EFFORT'). C2 (council.build_request) lee AQUÍ, no
    env_value(): env_value devuelve el literal 'inherit' sin resolver. El envío como output_config.effort sigue la
    regla ADR-0081 C.4 (sólo a modelos thinking_default 'adaptive') — la aplica el llamador con MODELS[model]."""
    raw, src = env_value(COUNCIL_EFFORT_ENV, env)
    if raw == COUNCIL_EFFORT_INHERIT:
        val, inner = env_value("WITT_ANTHROPIC_EFFORT", env)
        return val, f"env:{COUNCIL_EFFORT_ENV} (inherit -> {inner})"
    return raw, src


def _as_date(today):
    """today: None → fecha UTC del proceso · date/datetime · 'YYYY-MM-DD'. Los smokes lo fijan."""
    if today is None:
        return _dt.datetime.now(_dt.timezone.utc).date()
    if isinstance(today, _dt.datetime):
        return today.date()
    if isinstance(today, _dt.date):
        return today
    return _dt.date.fromisoformat(str(today)[:10])


# ---------------------------------------------------------------------------------------------------------------
# 5. Familia, API, relación, pensamiento
# ---------------------------------------------------------------------------------------------------------------
def family_by_prefix(model):
    """Familia inferida por prefijo para un id que la tabla NO conoce: claude-* → anthropic · gpt-*/o[0-9]*/
    text-embedding-* → openai · resto → 'unknown' (el asiento erra en la llamada con error_kind 'unknown-family'
    — fail-loud, no el `else: anthropic` de f57a3d3)."""
    m = str(model or "")
    if m.startswith("claude-"):
        return "anthropic"
    if m.startswith("gpt-") or m.startswith("text-embedding-") or re.match(r"^o[0-9]", m):
        return "openai"
    return FAMILY_UNKNOWN


def family_of(model):
    """(familia, fuente) — fuente ∈ 'table' | 'prefix'."""
    row = MODELS.get(model)
    if row:
        return row["family"], "table"
    return family_by_prefix(model), "prefix"


def api_of(model, env=None):
    """(api, api_source). La api de la tabla ('table'); un id desconocido la infiere por familia ('prefix':
    anthropic → anthropic-messages · openai → openai-responses, la API vigente para cualquier id más nuevo que la
    tabla); familia desconocida → (None, 'unknown-family'). WITT_OPENAI_API ∈ responses|chat-completions FUERZA
    el transporte de TODO modelo OpenAI de herramientas ('env:WITT_OPENAI_API'); 'table' (default) no toca nada."""
    row = MODELS.get(model)
    if row:
        api, src = row["api"], "table"
    else:
        fam = family_by_prefix(model)
        api = {"anthropic": "anthropic-messages", "openai": "openai-responses"}.get(fam)
        src = "prefix" if api else "unknown-family"
    force, _ = resolve_openai_api(env)
    if api in ("openai-responses", "openai-chat-completions") and force != "table":
        api = "openai-responses" if force == "responses" else "openai-chat-completions"
        src = f"env:{OPENAI_API_ENV}"
    return api, src


def relation(requested, reported):
    """exact | prefix (alias → snapshot fechado, NEUTRO) | different (objeción) | not-reported (gris: stub o API
    sin `model`). Nunca se copia una constante al lugar de `reported`."""
    if reported is None or str(reported) == "":
        return "not-reported"
    req, rep = str(requested), str(reported)
    if req == rep:
        return "exact"
    if rep.startswith(req):
        return "prefix"
    return "different"


def thinking_state(model):
    """Estado del pensamiento POR TABLA para `frozen.models.ran.*` (C.4): 'adaptive-by-api-default (tokens dentro
    de output_tokens)' | 'off-by-model-default' | 'not-applicable (…)' | 'unknown-to-table'."""
    row = MODELS.get(model)
    return THINKING_STATES[row["thinking_default"] if row else None]


def embed_model(env=None):
    """(modelo de embeddings efectivo, fuente) — OPENAI_EMBED_MODEL o la fila `embed` de la tabla."""
    raw = _raw(env, EMBED_MODEL_ENV)
    if raw and _looks_secret(raw):
        return SNAPSHOT_ALSO_READS[EMBED_MODEL_ENV]["default"], f"default-invalid-env:{EMBED_MODEL_ENV} (secret-like-value)"
    if raw:
        return raw, f"env:{EMBED_MODEL_ENV}"
    return SNAPSHOT_ALSO_READS[EMBED_MODEL_ENV]["default"], "default:table(embed)"


def catalog_row(model, env=None):
    """{family, api, status, known, generation, price_state} para /usage.models_catalog (H). `generation` = las
    generaciones donde el id es default (lista; [] = en ninguna)."""
    row = MODELS.get(model)
    fam, _ = family_of(model)
    api, _ = api_of(model, env)
    gens = [g for g, spec in GENERATIONS.items() if model in spec["defaults"].values()]
    return {"family": fam, "api": api, "status": row["status"] if row else None, "known": row is not None,
            "generation": gens, "price_state": "priced" if model in _PRICES else "missing"}


# ---------------------------------------------------------------------------------------------------------------
# 6. Resolución EN TIEMPO DE LLAMADA (jamás en import)
# ---------------------------------------------------------------------------------------------------------------
def _resolve_seat(role, env, gen, gen_src, spec, today, auto_retire, out):
    """RoleResolved de UN rol + efectos declarados en `out` (rejected_env, seat_substitutions, unknown_models)."""
    var, default = ROLE_ENVS[role], spec["defaults"][role]
    raw = _raw(env, var)
    if raw:
        fam = family_of(raw)[0]
        known = raw in MODELS
        reason = None
        if _looks_secret(raw):
            # Cinturón: un valor con forma de llave en una env de modelo es una env mal puesta; USARLO lo mandaría
            # como `model` en el cuerpo de una petición al proveedor. Se rechaza y JAMÁS se echa el valor.
            reason = "secret-like-value"
        elif known and MODELS[raw]["status"] in ("excluded", "embed"):
            reason = "excluded-model"
        elif fam != FAMILY_UNKNOWN and fam != ROLE_FAMILY[role]:
            reason = "wrong-family-for-lens" if role.startswith("judge.") else "wrong-family-for-role"
        if reason:
            out["rejected_env"].append({"role": role, "env": var, "value": _redact(raw), "reason": reason,
                                        "fallback": default})
            model, source = default, f"default-invalid-env:{var} ({reason})"
        else:
            model, source = raw, f"env:{var}" + ("" if known else " (unknown-to-table)")
    else:
        model, source = default, f"default:{gen}"
        # (E) auto-retire: SÓLO sobre el asiento por default (una env explícita es un ACTO del operador que no
        # se sustituye); con WITT_PANEL_AUTO_RETIRE=1 y today >= retire_not_before el sucesor DECLARADO entra.
        row = MODELS.get(model)
        if (auto_retire and row and row["status"] == "retiring" and row["successor"]
                and today >= _dt.date.fromisoformat(row["retire_not_before"])):
            succ = row["successor"]["reviewer"]
            out["seat_substitutions"].append({
                "seat": role.split(".", 1)[1] if role.startswith("judge.") else role,
                "retired": model, "retire_not_before": row["retire_not_before"], "successor": succ,
                "applied": True})
            source, model = f"auto-retire:{model}->{succ}", succ
    fam, fam_src = family_of(model)
    api, api_src = api_of(model, env)
    known = model in MODELS
    if not known:
        out["unknown_models"].append({"role": role, "model": model, "family": fam, "family_source": fam_src})
    return {"model": model, "source": source, "family": fam, "family_source": fam_src, "api": api,
            "api_source": api_src, "known": known, "priced": model in _PRICES,
            "max_tokens": spec["max_tokens"][_ROLE_TOPE[role]] if fam == "anthropic" else None,
            "generation": gen, "generation_source": gen_src}


def _member(lens, r):
    return {"reviewer": r["model"], "family": r["family"], "family_source": r["family_source"], "lens": lens,
            "api": r["api"], "api_source": r["api_source"], "reviewer_source": r["source"], "known": r["known"],
            "priced": r["priced"], "max_tokens": r["max_tokens"]}


def _resolve(env=None, today=None):
    """La resolución COMPLETA (9 roles: 4 pipeline + 4 jueces + council, panel + avisos) de un `env` en un
    `today`. Todo lo público la rebana."""
    env = _env(env)
    today = _as_date(today)
    gen, gen_src = resolve_generation(env)
    spec = GENERATIONS[gen]
    auto_retire, auto_src = env_value(AUTO_RETIRE_ENV, env)
    out = {"rejected_env": [], "seat_substitutions": [], "unknown_models": [], "warnings": []}
    roles = {role: _resolve_seat(role, env, gen, gen_src, spec, today, auto_retire, out) for role in ROLES}

    # Regla cruzada (A): `same-model-same-lens` — dos asientos idénticos (mismo modelo Y misma lente) por env.
    # Con las 4 lentes fijas por asiento es INALCANZABLE hoy (queda para cuando ADR-0082 mueva lentes por
    # directiva); el mismo modelo en lentes DISTINTAS NO se rechaza: se DECLARA en panel_duplicate_models (D).
    seen = {}
    for lens in LENSES:
        role = "judge." + lens
        r = roles[role]
        key = (r["model"], lens)
        if key in seen and r["source"].startswith("env:"):
            var = ROLE_ENVS[role]
            out["rejected_env"].append({"role": role, "env": var, "value": _redact(r["model"]),
                                        "reason": "same-model-same-lens", "fallback": spec["defaults"][role]})
            roles[role] = _resolve_seat(role, {}, gen, gen_src, spec, today, auto_retire,
                                        {"rejected_env": [], "seat_substitutions": [], "unknown_models": []})
            roles[role]["source"] = f"default-invalid-env:{var} (same-model-same-lens)"
        seen.setdefault(key, role)
    members = [_member(lens, roles["judge." + lens]) for lens in LENSES]
    counts = {}
    for m in members:
        counts[m["reviewer"]] = counts.get(m["reviewer"], 0) + 1
    duplicates = sorted(mid for mid, n in counts.items() if n > 1)

    # Avisos (orden fijo): invalid-env · retirement-due · past-retirement · api-unverified · not-adopted.
    warnings = []
    if gen_src.startswith("default-invalid-env:"):
        warnings.append(f"invalid-env: {GENERATION_ENV}={_redact(_raw(env, GENERATION_ENV))} (unknown-generation) "
                        f"— se usa default {GENERATION_DEFAULT}")
    for rej in out["rejected_env"]:
        warnings.append(f"invalid-env: {rej['env']}={rej['value']} ({rej['reason']}) — se usa default:{gen} "
                        f"{rej['fallback']} en {rej['role']}")
    due = _retirement(roles, today, days=30, past=False)
    past = _retirement(roles, today, days=None, past=True)
    warnings.extend(x["warning"] for x in due)
    warnings.extend(x["warning"] for x in past)
    unverified, seen_uv = [], {}
    for role in ROLES:
        r = roles[role]
        row = MODELS.get(r["model"])
        if row and not row["api_verified"]:
            seen_uv.setdefault(r["model"], []).append(role)
    for mid, in_roles in seen_uv.items():
        unverified.append(f"api-unverified: {mid} ({', '.join(in_roles)}) — transporte/forced tool_use no medido "
                          f"en vivo con este modelo por este código; gate {'LG1' if MODELS[mid]['family'] == 'anthropic' else 'LG2/LG3'}")
    warnings.extend(unverified)
    for role in ROLES:
        r = roles[role]
        row = MODELS.get(r["model"])
        if row and row["status"] == "not-adopted":
            warnings.append(f"not-adopted: {r['model']} en {role} — {row['note']}")

    sig = panel_signature(members, roles)
    return {"generation": gen, "generation_source": gen_src, "generation_spec": spec, "today": today.isoformat(),
            "auto_retire": auto_retire, "auto_retire_source": auto_src, "roles": roles, "panel": members,
            "panel_signature": sig, "panel_duplicate_models": duplicates,
            "seat_substitutions": out["seat_substitutions"], "rejected_env": out["rejected_env"],
            "unknown_models": out["unknown_models"], "warnings": warnings,
            "retirement_due": due, "past_retirement": past}


def _retirement(roles, today, days, past):
    """Filas de retiro sobre los modelos EFECTIVOS (un asiento sustituido por auto-retire ya no avisa: la
    sustitución vive en seat_substitutions). past=False → 0 < faltan <= days; past=True → today >= fecha."""
    rows = []
    for role in ROLES:
        r = roles[role]
        row = MODELS.get(r["model"])
        if not row or row["status"] != "retiring" or not row["retire_not_before"]:
            continue
        rnb = _dt.date.fromisoformat(row["retire_not_before"])
        delta = (rnb - today).days
        succ = (row["successor"] or {}).get("reviewer")
        var = ROLE_ENVS[role]
        fix = f"fijar {var}={succ} o {AUTO_RETIRE_ENV}=1" if succ else "sin sucesor declarado en tabla"
        if past and delta <= 0:
            rows.append({"role": role, "model": r["model"], "retire_not_before": row["retire_not_before"],
                         "days_past": -delta, "successor": succ, "env": var,
                         "warning": f"past-retirement: {r['model']} en {role} (retire_not_before "
                                    f"{row['retire_not_before']}, hace {-delta} días; sucesor declarado {succ} — {fix})"})
        elif not past and 0 < delta <= days:
            rows.append({"role": role, "model": r["model"], "retire_not_before": row["retire_not_before"],
                         "days_left": delta, "successor": succ, "env": var,
                         "warning": f"retirement-due: {r['model']} en {role} (retire_not_before "
                                    f"{row['retire_not_before']}, faltan {delta} días; sucesor declarado {succ} — {fix})"})
    return rows


def resolve_role(role, env=None, today=None):
    """RoleResolved = {model, source, family, family_source, api, api_source, known, priced, max_tokens,
    generation, generation_source}. `source` ∈ 'env:<VAR>' | 'env:<VAR> (unknown-to-table)' | 'default:<gen>' |
    'default-invalid-env:<VAR> (<motivo>)' | 'auto-retire:<a>-><b>'. Resolución en la LLAMADA: `env` es un
    mapping (default os.environ) y `today` una fecha (default UTC del proceso) para que los smokes la prueben sin
    tocar el proceso. `max_tokens` es el TOPE de la generación para el rol (None para un asiento OpenAI o de
    familia desconocida: su tope es del transporte)."""
    if role not in ROLES:
        raise ValueError(f"rol desconocido para la tabla: {role!r} (ROLES={ROLES})")
    return _resolve(env, today)["roles"][role]


def resolve_panel(env=None, today=None, directives=None):
    """La resolución del panel con TODO lo declarable: {panel: PanelMember[4], panel_signature, panel_source (K),
    seat_substitutions[] (E), panel_duplicate_models[] (D), rejected_env[], unknown_models[], warnings[],
    generation, generation_source, roles}. `panel()` es su rebanada `panel`."""
    R = _resolve(env, today)
    return {"panel": R["panel"], "panel_signature": R["panel_signature"],
            "panel_source": _panel_source(R, directives), "seat_substitutions": R["seat_substitutions"],
            "panel_duplicate_models": R["panel_duplicate_models"], "rejected_env": R["rejected_env"],
            "unknown_models": R["unknown_models"], "warnings": R["warnings"],
            "generation": R["generation"], "generation_source": R["generation_source"], "roles": R["roles"]}


def panel(env=None, today=None, directives=None):
    """PanelMember[4] en orden FIJO correctness/overclaim/evidence-grounding/reproducibility; cada miembro =
    {reviewer, family, family_source, lens, api, api_source, reviewer_source, known, priced, max_tokens}.
    `directives` (ADR-0082) se acepta y HOY se ignora — declarado en panel_source (K)."""
    return resolve_panel(env, today, directives)["panel"]


def _panel_source(R, directives):
    return {"generation": R["generation"], "table_version": MODELS_TABLE_VERSION,
            "panel_signature": R["panel_signature"],
            "directives_state": "empty-until-ADR-0082",
            "council_hook": {"state": "not-available (ADR-0082)",
                             "accepts": "directives[] → asientos/lentes por nicho", "lens_scope": "global"},
            "lens_charges_source": "composite_auditor._LENS_CHARGES"}


def panel_source(env=None, today=None, directives=None):
    """(K) — {generation, table_version, panel_signature, directives_state 'empty-until-ADR-0082', council_hook
    {state, accepts, lens_scope}, lens_charges_source}. audit() lo congela en audit.panel_source."""
    return resolve_panel(env, today, directives)["panel_source"]


def member_for(model, lens, env=None, today=None):
    """PanelMember para un modelo ARBITRARIO en una lente (smoke_live_models --model, run_held_out): misma forma
    que panel(), reviewer_source 'caller'. No aplica rechazos: el llamador eligió."""
    if lens not in LENSES:
        raise ValueError(f"lente desconocida: {lens!r}")
    R = _resolve(env, today)
    fam, fam_src = family_of(model)
    api, api_src = api_of(model, env)
    return {"reviewer": model, "family": fam, "family_source": fam_src, "lens": lens, "api": api,
            "api_source": api_src, "reviewer_source": "caller", "known": model in MODELS,
            "priced": model in _PRICES,
            "max_tokens": R["generation_spec"]["max_tokens"]["judge-anthropic"] if fam == "anthropic" else None}


def panel_signature(panel_members, roles):
    """sha256[:16] de la IDENTIDAD del panel + roles del pipeline: [(lens, reviewer, api)] × 4 y
    {rol: modelo} para synthesizer/planner/elicitation/question_agent (los topes NO son identidad). Cuando
    Emmanuel pinea una env la generación sigue g2 pero la firma cambia — ADR-0087 segmenta por firma.
    `roles` acepta {rol: RoleResolved} o {rol: 'model-id'}; sólo PIPELINE_ROLES presentes cuentan."""
    seats = [[m.get("lens"), m.get("reviewer"), m.get("api")] for m in (panel_members or [])]
    role_models = {}
    for k in PIPELINE_ROLES:
        if k in (roles or {}):
            v = roles[k]
            role_models[k] = v.get("model") if isinstance(v, dict) else v
    blob = json.dumps({"panel": seats, "roles": role_models}, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def retirement_due(env=None, today=None, days=30):
    """Avisos MEDIDOS (E): [{role, model, retire_not_before, days_left, successor, env, warning}] para todo modelo
    EFECTIVO con status 'retiring' y 0 < faltan <= days. warning = 'retirement-due: <model> en <role>
    (retire_not_before <fecha>, faltan N días; sucesor declarado <succ> — fijar <VAR>=<succ> o
    WITT_PANEL_AUTO_RETIRE=1)'."""
    R = _resolve(env, today)
    return _retirement(R["roles"], _as_date(today), days, past=False)


def past_retirement(env=None, today=None):
    """[{role, model, retire_not_before, days_past, successor, env, warning 'past-retirement: …'}] para todo
    modelo EFECTIVO retirado (today >= retire_not_before) que sigue en un asiento (env explícita o AUTO_RETIRE=0)."""
    return _resolve(env, today)["past_retirement"]


# ---------------------------------------------------------------------------------------------------------------
# 7. Snapshot (I): el estado EFECTIVO con fuente por campo — insumo del ledger, de stage.models y de
#    /config-history.current
# ---------------------------------------------------------------------------------------------------------------
def snapshot(env=None, today=None, extra=None):
    """{generation, generation_source, table_version, table_as_of, panel_signature, today, fields, roles, panel,
    panel_source, seat_substitutions, panel_duplicate_models, rejected_env, warnings, unknown_models,
    extra_ignored}. `fields` = SNAPSHOT_FIELDS en orden, cada uno {value (escalar JSON), source}. `extra` =
    {campo ∈ EXTRA_FIELDS: {value, source}} del llamador; lo que falte queda {None, 'not-provided-by-caller'}.
    Cinturón: ningún value que parezca llave sale de aquí."""
    R = _resolve(env, today)
    extra = extra or {}
    f = {}
    f["model_generation"] = {"value": R["generation"], "source": R["generation_source"]}
    f["table_version"] = {"value": MODELS_TABLE_VERSION, "source": "models.MODELS_TABLE_VERSION"}
    f["panel_signature"] = {"value": R["panel_signature"], "source": "models.panel_signature(panel, roles)"}
    for role in PIPELINE_ROLES:
        f[f"role.{role}"] = {"value": R["roles"][role]["model"], "source": R["roles"][role]["source"]}
    for m in R["panel"]:
        f[f"panel.{m['lens']}"] = {"value": m["reviewer"], "source": m["reviewer_source"]}
    for field, var in (("panel.min_families", "WITT_PANEL_MIN_FAMILIES"), ("panel.min_lenses", "WITT_PANEL_MIN_LENSES"),
                       ("panel.auto_retire", AUTO_RETIRE_ENV), ("openai.api", OPENAI_API_ENV),
                       ("openai.store", "WITT_OPENAI_STORE"), ("openai.max_output_tokens", "WITT_OPENAI_MAX_OUTPUT_TOKENS"),
                       ("openai.timeout_s", "WITT_OPENAI_TIMEOUT_S"), ("openai.reasoning_effort", "WITT_OPENAI_REASONING_EFFORT"),
                       ("anthropic.effort", "WITT_ANTHROPIC_EFFORT"), ("anthropic.effort_elicit", "WITT_ANTHROPIC_EFFORT_ELICIT"),
                       ("judge.retries", "WITT_JUDGE_RETRIES")):
        v, s = env_value(var, env)
        f[field] = {"value": v, "source": s}
    f["prices.as_of"] = {"value": PRICES_AS_OF, "source": "models.PRICES_AS_OF"}
    em, em_src = embed_model(env)
    f["embed.model"] = {"value": em, "source": em_src}
    # ADR-0082 (D.2): el consejo en el snapshot — role.council FUERA de panel_signature; bools tolerantes
    for role in COUNCIL_ROLES:
        f[f"role.{role}"] = {"value": R["roles"][role]["model"], "source": R["roles"][role]["source"]}
    for field, var in (("council.enabled", "WITT_COUNCIL"), ("council.full", "WITT_COUNCIL_FULL"),
                       ("council.cache_ttl", "WITT_COUNCIL_CACHE_TTL")):
        v, s = env_value(var, env)
        f[field] = {"value": v, "source": s}
    ce, ce_src = council_effort(env)
    f["council.effort"] = {"value": ce, "source": ce_src}
    ignored = []
    for field in EXTRA_FIELDS:
        given = extra.get(field)
        if isinstance(given, dict) and "value" in given:
            f[field] = {"value": given["value"], "source": str(given.get("source") or "caller")}
        else:
            f[field] = {"value": None, "source": NOT_PROVIDED}
    for k in extra:
        if k not in EXTRA_FIELDS:
            ignored.append(k)   # models.py es la verdad de sus propios campos: no se sobreescriben desde fuera
    fields = {k: f[k] for k in SNAPSHOT_FIELDS}
    for k, cell in fields.items():
        if cell["value"] is not None and _looks_secret(cell["value"]):
            fields[k] = {"value": "<redactado: parece llave>", "source": cell["source"] + " (rejected-secret-like)"}
    return {"generation": R["generation"], "generation_source": R["generation_source"],
            "table_version": MODELS_TABLE_VERSION, "table_as_of": MODEL_TABLE_AS_OF,
            "panel_signature": R["panel_signature"], "today": R["today"], "fields": fields,
            "roles": R["roles"], "panel": R["panel"], "panel_source": _panel_source(R, None),
            "seat_substitutions": R["seat_substitutions"], "panel_duplicate_models": R["panel_duplicate_models"],
            "rejected_env": R["rejected_env"], "warnings": R["warnings"], "unknown_models": R["unknown_models"],
            "extra_ignored": ignored}


# ---------------------------------------------------------------------------------------------------------------
# 8. Procedencia MEDIDA (B): frozen.models
# ---------------------------------------------------------------------------------------------------------------
PROVENANCE_RULE = ("requested = el modelo RESUELTO (tabla/env) en la llamada; reported = payload.model que la API "
                   "devolvió (null con un stub o una API que no lo manda); relation exact | prefix (alias → snapshot "
                   "fechado, NEUTRO) | different (objeción) | not-reported (gris). thinking_state por tabla (C.4). "
                   "roles.planner se COPIA de plan_json.judgment.planner (el plan pudo correr antes del redeploy: "
                   "un plan opus-4-8 con síntesis opus-5 es la verdad, no un bug). Nada se copia de una constante.")


def _ran(requested, reported):
    return {"requested": requested, "reported": reported, "relation": relation(requested, reported),
            "thinking_state": thinking_state(requested)}


def _passes_dict(passes):
    if isinstance(passes, dict):
        return dict(passes)
    out = {}
    for label, p in (passes or []):
        out[label] = p
    return out


def provenance_block(roles, passes, planner_meta, panel_rows, question_meta=None, signature_roles=None):
    """frozen.models (B) = {generation, generation_source, table_version, table_as_of, panel_signature,
    roles: {synthesizer: RoleResolved, elicitation: RoleResolved, question_agent: RoleResolved|null,
            planner: {model, model_source, provenance ∈ PLANNER_PROVENANCES}},
    ran: {synthesize_pass1: Ran, synthesize_pass2: Ran|null, revision: Ran|null, elicit_pass1: Ran|null,
          elicit_pass2: Ran|null, plan: Ran|null, question: Ran|null,
          panel: [{lens, reviewer, reported, relation, api_used, attempts}]},
    rule} con Ran = {requested, reported: str|null, relation, thinking_state}.

    Insumos (los MISMOS de runs._usage_by_stage): `roles` = {synthesizer, elicitation[, question_agent]:
    RoleResolved} resueltos EN la corrida; `passes` = [(label, dict)] con label ∈ pass1|pass2|revision (o dict);
    cada dict trae `model` (pedido), `model_reported` (lo que la API dijo; ausente/None → not-reported) y, si la
    elicitación se intentó, la llave `usage_elicitation` (marcador de ADR-0080) + `elicitation_model`/
    `elicitation_model_reported`; `planner_meta` = plan_json.judgment.planner ({model, model_source?,
    model_reported?}) o None; `panel_rows` = audit.panel (cada fila con lens, reviewer, api?, model_reported? y
    attempts[] con model_reported?/api?); `question_meta` = salida de question_agent.draft_question ({model,
    model_reported?}) o None. FAILURE-agnóstico: los error_kind son de composite_auditor (S2).
    `signature_roles` (S7, costura N): los roles con los que se calcula `panel_signature` — runs pasa los 8 roles del
    snapshot de stage.models, así frozen.models.panel_signature == stage.models.panel_signature ==
    audit.panel_source.panel_signature (UNA identidad de configuración por corrida; ADR-0087 segmenta por ella);
    None → se firma con `roles` (synthesizer/elicitation), la forma de un llamador sin snapshot."""
    synth, elic = roles["synthesizer"], roles["elicitation"]
    qa = roles.get("question_agent")
    P = _passes_dict(passes)

    def _synth_ran(label):
        p = P.get(label)
        if not isinstance(p, dict):
            return None
        return _ran(p.get("model") or synth["model"], p.get("model_reported"))

    def _elicit_ran(label):
        p = P.get(label)
        if not isinstance(p, dict) or "usage_elicitation" not in p:
            return None
        return _ran(p.get("elicitation_model") or elic["model"], p.get("elicitation_model_reported"))

    if isinstance(planner_meta, dict) and planner_meta.get("model"):
        prov = "plan_json" if "model_source" in planner_meta else "plan_json (pre-1.10: source not recorded)"
        planner = {"model": planner_meta["model"], "model_source": planner_meta.get("model_source"),
                   "provenance": prov}
        plan_ran = _ran(planner_meta["model"], planner_meta.get("model_reported"))
    else:
        planner = {"model": None, "model_source": None, "provenance": "no-plan"}
        plan_ran = None
    question_ran = (_ran(question_meta["model"], question_meta.get("model_reported"))
                    if isinstance(question_meta, dict) and question_meta.get("model") else None)

    panel_ran, members = [], []
    for row in panel_rows or []:
        attempts = row.get("attempts") if isinstance(row.get("attempts"), list) else None
        reported = row.get("model_reported")
        api_used = row.get("api")
        if attempts:
            for a in reversed(attempts):
                if reported is None and isinstance(a, dict) and a.get("model_reported"):
                    reported = a["model_reported"]
                if api_used is None and isinstance(a, dict) and a.get("api"):
                    api_used = a["api"]
        panel_ran.append({"lens": row.get("lens"), "reviewer": row.get("reviewer"), "reported": reported,
                          "relation": relation(row.get("reviewer"), reported), "api_used": api_used,
                          "attempts": len(attempts) if attempts is not None else None})
        members.append({"lens": row.get("lens"), "reviewer": row.get("reviewer"),
                        "api": row.get("api") or api_of(row.get("reviewer"))[0]})
    return {
        "generation": synth.get("generation"), "generation_source": synth.get("generation_source"),
        "table_version": MODELS_TABLE_VERSION, "table_as_of": MODEL_TABLE_AS_OF,
        "panel_signature": panel_signature(members, signature_roles if signature_roles is not None else roles),
        # ADR-0082 (M, C9): roles.council = el RoleResolved del rol `council` del MISMO snapshot de stage.models que
        # runs pasa en `roles` (frozen.models.roles.council == stage.models.roles.council); None declarado cuando el
        # llamador no lo trae (llamadores anteriores a 0082). Viaja también bajo WITT_COUNCIL=0: el rol está en la
        # tabla aunque el consejo esté apagado (excepción DECLARADA L.2 ii, junto a stage.models.roles.council).
        "roles": {"synthesizer": synth, "elicitation": elic, "question_agent": qa, "planner": planner,
                  "council": roles.get("council")},
        "ran": {"synthesize_pass1": _synth_ran("pass1"), "synthesize_pass2": _synth_ran("pass2"),
                "revision": _synth_ran("revision"), "elicit_pass1": _elicit_ran("pass1"),
                "elicit_pass2": _elicit_ran("pass2"), "plan": plan_ran, "question": question_ran,
                "panel": panel_ran},
        "rule": PROVENANCE_RULE,
    }

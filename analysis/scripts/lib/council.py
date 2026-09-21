"""
council.py — el CONSEJO DE CRITERIO ejecutable (ADR-0082 (C): C.1 prompts · C.2 tools · C.3 ronda · C.4 agregación ·
C.5 cobertura · C.6 directivas · C.7 re-cobertura estructural · C.8 vocabularios · C.9 kill-switch). stdlib puro
(json, hashlib, math, re, threading, time, concurrent.futures) + las tablas del repo (`catalog_cards`, `agent_matrix`,
`search_harness.SEARCH_DISPATCH`, `models`) y el caller Anthropic de `composite_auditor` (D.1).

Doctrina (CLAUDE.md §7, ADR-0082 (L.5)) — lo que este módulo NUNCA hace:
  · el consejo NO escribe la respuesta, NO emite veredicto, NO rankea, NO despacha: sus tres tools sólo producen
    REQUISITOS de información (r1), BANDERAS con gate humano (r1, regulatory-ethics-advisor) y JUICIOS de cobertura
    sobre SUS propios requisitos (r2/r3). Ningún `input_schema` lleva un campo prohibido (`PROHIBITED_OUTPUT_FIELDS`;
    `tools_static_check()` lo mide);
  · nada se afirma sin medirse: un `evidence_id` que no está en el bundle ANULA el voto; un `requirement_id` ajeno se
    descarta y se cuenta; un enum fuera de vocabulario descarta el ítem y se guarda crudo; un miembro caído es una fila
    `errored` con su kind, jamás un default;
  · `causal-pruner` es hard-rule: todo requisito suyo nace `hard_rule_gate True` y el ledger exige decisión humana
    EXPLÍCITA (apply_ledger_decisions lo rechaza con `hard_rule_requirements_undecided`); `cross-field-bridge-agent`
    es exploratorio: su `must` se degrada a `should` con `priority_downgraded_from` (§7 Test 5);
  · lo atestiguado por humanos y las observaciones previas viajan como PRIOR ART en el user message, jamás como
    evidencia; el sistema (bloque A + ficha VERBATIM) es una función pura sin fechas ni ids (caché: Context 7);
  · la agregación es CÓDIGO byte a byte (`aggregate_r1`): mismos insumos barajados → mismo JSON, mismos
    `requirement_id` (golden en smoke_council.py);
  · tres estados (ADR-0043): ausente ≠ null declarado ≠ valor; un 0 medido nunca se confunde con "no medido".

Costuras (ADR-0082 plan C1–C9): C4 (`council_jobs.py`) llama `run_round(members, 'r1', ctx, caller, …)` +
`aggregate_r1`; C5 (`runs.py`) llama `run_round(…, 'r2'|'r3', …)`, `judge_coverage`, `directives_from`,
`coverage_after_search`, `summary_for_thread`, `abandoned_cost_upper`; C6 (`app.py`) expone
`council_vocabulary()` en `GET /council/membership` y puede usar `apply_ledger_decisions` (F.1). Los eventos
(`on_event`) se emiten SÓLO desde el hilo que llamó a `run_round` (Context 6: `db.add_event` no es reentrante).

Kill-switch: `enabled(env)` (WITT_COUNCIL, default 1). Con `0` NADIE llama a `run_round`; este módulo no impone
nada al importar (sin I/O, sin red, sin BD).

ADR-0084 (F.1/F.2/F.4 — la web LOCALIZA, jamás es fuente): `harness_state_for` delega en `search_harness.family_available`
(disponibilidad leída EN LA LLAMADA: web → web_locator.provider_state; bajo off el literal de 7d9ce15 byte a byte);
`directives_from` RECOMPUTA el harness_state de las familias con disponibilidad dinámica al compilar (la llave que llegó
compila la directiva web sin re-planear); `coverage_after_search(…, web_locator=)` mide por requisito web
{n_queries, n_results, n_located, n_materialized, n_unresolved} — conteos, jamás URLs ni títulos de la web.
"""
import concurrent.futures
import hashlib
import json
import math
import os
import re
import threading
import time

from lib import agent_matrix
from lib import catalog_cards
from lib import composite_auditor
from lib import models
from lib import search_harness

MODULE_VERSION = "council-1"                                   # frozen.council.module_version (ADR-0082 J)
COUNCIL_VERSION = agent_matrix.MEMBERSHIP_VERSION              # 'cm-1' — la versión del consejo ES la de su membresía
MEMBERSHIP_VERSION = agent_matrix.MEMBERSHIP_VERSION

# ── (C.1) re-exports del prompt: el bloque A (fijo + §7) y la ficha viven en catalog_cards (dueño C1) ─────────────
COUNCIL_FIXED_BLOCK = catalog_cards.COUNCIL_FIXED_BLOCK
COUNCIL_RULES = catalog_cards.COUNCIL_RULES
COUNCIL_RULES_ITEMS = catalog_cards.COUNCIL_RULES_ITEMS
RULES_SHA = catalog_cards.RULES_SHA
SHARED_BLOCK_TEXT = catalog_cards.SHARED_BLOCK_TEXT
SHARED_BLOCK_SHA = catalog_cards.SHARED_BLOCK_SHA
PROHIBITED_OUTPUT_FIELDS = catalog_cards.PROHIBITED_OUTPUT_FIELDS
MIN_CACHEABLE_TOKENS = catalog_cards.MIN_CACHEABLE_TOKENS
build_system = catalog_cards.build_system
system_sha = catalog_cards.system_sha
cache_config = catalog_cards.cache_config


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canon(obj):
    """JSON canónico (la forma que se hashea y se compara byte a byte)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


# ── (C.8) vocabularios CERRADOS — viajan congelados en frozen.council.vocabulary (gate (F) de paridad) ────────────
ROUNDS = ("r1", "r2", "r3")
ROUND_KINDS = ("requirements", "coverage", "recoverage")
ROUND_KIND_OF = {"r1": "requirements", "r2": "coverage", "r3": "recoverage"}
ROUND_PHASES = ("plan", "run")
PRIORITIES = ("must", "should")
COVERAGE_VOTES = ("covered", "partial", "uncovered")
COVERAGE_STATES = ("covered", "partial", "uncovered", "not-judged", "covered-by-attestation", "discarded")
MEMBER_STATES = ("ok", "not-applicable", "errored", "timeout", "skipped-budget", "skipped-cancelled", "not-invoked")
AGGREGATE_STATES_EXACT = ("applicable", "incomplete")
AGGREGATE_STATE_PREFIXES = ("errored (",)
# (H) estados de token_usage.by_stage.council_r1/r2/r3 — ÚNICA fuente (runs.py los re-exporta como
# COUNCIL_USAGE_STAGE_STATES_*; corrector ADR-0082: viajan en council.vocabulary para que el gate (F) y la webapp los tipen)
USAGE_STAGE_STATES_EXACT = ("measured", "measured (partial: round cancelled)", "copied-from-plan_json",
                            "plan-without-council", "kill-switch WITT_COUNCIL=0")
USAGE_STAGE_STATE_PREFIXES = ("not-run (",)
COUNCIL_STATES_EXACT = ("queued", "running", "applicable", "incomplete", "skipped-by-human",
                        "not-applicable (no-ledger)", "disabled (kill-switch WITT_COUNCIL=0)", "pre-adr-0082")
COUNCIL_STATE_PREFIXES = ("errored (", "not-requested (")
DECISION_STATES = ("keep", "discard", "aporto", "pending")
DECIDED_BY_PREFIXES = ("human:", "default-keep", "gate-human-pending")
LEDGER_STATES = ("draft", "approved", "skipped-by-human")
DIRECTIVE_STATES = ("compiled", "excluded-unknown-family", "excluded-unsatisfiable")
DIRECTIVES_STATES = ("provided", "none (all must covered)", "not-run")
AFTER_SEARCH_STATES = ("retrieved-for", "still-uncovered", "not-searched", "covered-pre")
POST_SEARCH_STATES_EXACT = ("judged", "not-run (nothing admitted)", "not-run (all must covered)",
                            "not-run (kill-switch WITT_COUNCIL_RECOVERAGE=0)", "not-run (search not triggered)")
HARNESS_STATES_EXACT = ("satisfiable",)
HARNESS_STATE_PREFIXES = ("unsatisfiable-by-harness (",)
FLAG_KINDS = ("wet-lab", "animal-work", "patient-material", "budget", "compliance", "partner-relationship",
              "human-embryo-hard-line")
# kinds de error de una fila de miembro: los del caller (composite_auditor C.2) + los del consejo (declarados aquí)
MEMBER_ERROR_KINDS_EXTRA = ("timeout", "wrong-tool", "no-card-in-catalog", "not-in-membership", "invalid-output",
                            "no-model", "caller-exception")
# el evidence_kind y la familia salen de la TABLA (síntesis del ADR: 'text-literature' es `paper`; un enum paralelo
# se desincroniza) + 'figure' (unsatisfiable hasta ADR-0083, contado)
COUNCIL_EVIDENCE_KINDS = tuple(sorted({spec["evidence_kind"] for spec in search_harness.SEARCH_DISPATCH.values()}
                                      | {"figure"}))
COUNCIL_SOURCE_FAMILIES = tuple(sorted(search_harness.SEARCH_DISPATCH))


def council_state_in_vocabulary(s):
    """Predicado del gate de paridad (patrón runs.plan_state_in_vocabulary): exacto o prefijo con algo detrás."""
    if not isinstance(s, str) or not s:
        return False
    return s in COUNCIL_STATES_EXACT or any(s.startswith(p) and len(s) > len(p) for p in COUNCIL_STATE_PREFIXES)


def aggregate_state_in_vocabulary(s):
    if not isinstance(s, str) or not s:
        return False
    return s in AGGREGATE_STATES_EXACT or any(s.startswith(p) and len(s) > len(p) for p in AGGREGATE_STATE_PREFIXES)


def harness_state_in_vocabulary(s):
    if not isinstance(s, str) or not s:
        return False
    return s in HARNESS_STATES_EXACT or any(s.startswith(p) and len(s) > len(p) for p in HARNESS_STATE_PREFIXES)


def council_vocabulary():
    """Todos los vocabularios juntos — `frozen.council.vocabulary` y `GET /council/membership.vocabulary` (C6)."""
    return {
        "module_version": MODULE_VERSION, "council_version": COUNCIL_VERSION,
        "council_states": {"exact": list(COUNCIL_STATES_EXACT), "prefixes": list(COUNCIL_STATE_PREFIXES)},
        "aggregate_states": {"exact": list(AGGREGATE_STATES_EXACT), "prefixes": list(AGGREGATE_STATE_PREFIXES)},
        "member_states": list(MEMBER_STATES),
        "member_error_kinds": {"caller_exact": list(composite_auditor.FAILURE_KINDS_EXACT),
                               "caller_prefixes": list(composite_auditor.FAILURE_KIND_PREFIXES),
                               "council_extra": list(MEMBER_ERROR_KINDS_EXTRA)},
        "coverage_votes": list(COVERAGE_VOTES), "coverage_states": list(COVERAGE_STATES),
        "decision_states": list(DECISION_STATES), "decided_by_prefixes": list(DECIDED_BY_PREFIXES),
        "ledger_states": list(LEDGER_STATES),
        "directive_states": list(DIRECTIVE_STATES), "directives_states": list(DIRECTIVES_STATES),
        "after_search_states": list(AFTER_SEARCH_STATES),
        "post_search_states": {"exact": list(POST_SEARCH_STATES_EXACT), "prefixes": ["not-run ("]},
        "usage_stage_states": {"exact": list(USAGE_STAGE_STATES_EXACT), "prefixes": list(USAGE_STAGE_STATE_PREFIXES)},
        "quorum_rule": QUORUM_SOURCE,
        "harness_states": {"exact": list(HARNESS_STATES_EXACT), "prefixes": list(HARNESS_STATE_PREFIXES)},
        "round_kinds": list(ROUND_KINDS), "rounds": list(ROUNDS), "round_phases": list(ROUND_PHASES),
        "priorities": list(PRIORITIES), "flag_kinds": list(FLAG_KINDS),
        "evidence_kinds": list(COUNCIL_EVIDENCE_KINDS), "source_families": list(COUNCIL_SOURCE_FAMILIES),
        "membership_groups": list(agent_matrix.COUNCIL_MEMBERSHIP["groups"]),
        "membership_modes": list(agent_matrix.COUNCIL_MEMBERSHIP["modes"]),
        "prohibited_output_fields": list(PROHIBITED_OUTPUT_FIELDS),
    }


# ── (C.2) los TRES tools cerrados, bytes idénticos en TODA llamada; la ronda se fuerza con tool_choice ────────────
MAX_PER_MEMBER_DEFAULT = 5          # `maxItems` del schema (constante: el schema es identidad de la caché; la env sólo
                                    # mueve el tope de CÓDIGO en validate_tool_input — declarado en el ADR/deviations)
STR_CAPS = {"gap": 300, "query_en": 200, "acceptance_test": 300, "notes_for_human": 400, "not_applicable_reason": 300,
            "statement": 300, "rationale": 300}
ENTITIES_CAP = 6
EVIDENCE_IDS_CAP = 8
FLAGS_CAP = 5

REQ_TOOL_NAME = "emit_information_requirements"
FLAGS_TOOL_NAME = "emit_flags"
COV_TOOL_NAME = "emit_coverage_judgment"

REQ_TOOL = {
    "name": REQ_TOOL_NAME,
    "description": ("Emit the INFORMATION REQUIREMENTS your catalog role needs verified before this zebrafish pronephros "
                    "research question can be addressed from evidence: for each requirement, the gap (what is missing), "
                    "the evidence kind and the source family that could satisfy it, an English query, the entities "
                    "involved, an acceptance test and a priority. Criteria only: no findings, no conclusions, no "
                    "identifiers asserted as facts. If your role has nothing to require for this question, set "
                    "applicable to false and say why."),
    "input_schema": {
        "type": "object",
        "properties": {
            "applicable": {"type": "boolean",
                           "description": "false when your role has no information requirement for this question"},
            "not_applicable_reason": {"type": "string", "maxLength": STR_CAPS["not_applicable_reason"]},
            "requirements": {
                "type": "array", "maxItems": MAX_PER_MEMBER_DEFAULT,
                "items": {
                    "type": "object",
                    "properties": {
                        "gap": {"type": "string", "maxLength": STR_CAPS["gap"],
                                "description": "what is missing, in one or two sentences"},
                        "evidence_kind": {"type": "string", "enum": list(COUNCIL_EVIDENCE_KINDS)},
                        "source_family": {"type": "string", "enum": list(COUNCIL_SOURCE_FAMILIES)},
                        "query_en": {"type": "string", "maxLength": STR_CAPS["query_en"],
                                     "description": "English query that a search over the source family would run"},
                        "entities": {"type": "array", "maxItems": ENTITIES_CAP, "items": {"type": "string"},
                                     "description": "gene symbols / terms involved; checked by code, never asserted"},
                        "acceptance_test": {"type": "string", "maxLength": STR_CAPS["acceptance_test"],
                                            "description": "how a human would know the requirement is satisfied"},
                        "priority": {"type": "string", "enum": list(PRIORITIES)},
                    },
                    "required": ["gap", "evidence_kind", "source_family", "query_en", "acceptance_test", "priority"],
                },
            },
            "notes_for_human": {"type": "string", "maxLength": STR_CAPS["notes_for_human"]},
        },
        "required": ["applicable", "requirements"],
    },
}

FLAGS_TOOL = {
    "name": FLAGS_TOOL_NAME,
    "description": ("Emit COMPLIANCE / BUDGET / PARTNER flags that this research question raises for a human to decide "
                    "(CLAUDE.md §7: compliance and budget decisions never go through automatic filtering). Flags only: "
                    "no information requirements, no findings, no decision. The human gate is set by code."),
    "input_schema": {
        "type": "object",
        "properties": {
            "applicable": {"type": "boolean", "description": "false when nothing in the question needs a flag"},
            "not_applicable_reason": {"type": "string", "maxLength": STR_CAPS["not_applicable_reason"]},
            "flags": {
                "type": "array", "maxItems": FLAGS_CAP,
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": list(FLAG_KINDS)},
                        "statement": {"type": "string", "maxLength": STR_CAPS["statement"]},
                    },
                    "required": ["kind", "statement"],
                },
            },
        },
        "required": ["applicable", "flags"],
    },
}

COV_TOOL = {
    "name": COV_TOOL_NAME,
    "description": ("Judge, for EACH of YOUR OWN requirements listed in the message, whether the evidence shown covers it. "
                    "Cite only evidence_ids that appear in the evidence (an id that is not there annuls your vote — code "
                    "checks it). Optionally refine the search directive for a requirement that is not covered. Judgments "
                    "only: no findings, no conclusions about the question."),
    "input_schema": {
        "type": "object",
        "properties": {
            "judgments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "requirement_id": {"type": "string", "description": "one of YOUR requirement ids from the message"},
                        "coverage": {"type": "string", "enum": list(COVERAGE_VOTES)},
                        # SIN `enum` por corrida (síntesis contra D3): un schema por corrida = definición de tool distinta =
                        # posición 0 del prefijo = reconstrucción total de la caché. La validación es CÓDIGO (judge_coverage).
                        "evidence_ids": {"type": "array", "maxItems": EVIDENCE_IDS_CAP, "items": {"type": "string"},
                                         "description": "evidence ids from the evidence shown that support the judgment"},
                        "rationale": {"type": "string", "maxLength": STR_CAPS["rationale"]},
                        "search_directive": {
                            "type": "object",
                            "properties": {
                                "query_en": {"type": "string", "maxLength": STR_CAPS["query_en"]},
                                "entities": {"type": "array", "maxItems": ENTITIES_CAP, "items": {"type": "string"}},
                            },
                        },
                    },
                    "required": ["requirement_id", "coverage", "evidence_ids", "rationale"],
                },
            },
        },
        "required": ["judgments"],
    },
}

TOOLS = (REQ_TOOL, FLAGS_TOOL, COV_TOOL)
TOOL_BY_NAME = {t["name"]: t for t in TOOLS}
TOOLS_SHA = _sha256(_canon(list(TOOLS)))
_DISCRIMINATOR_OF_TOOL = {REQ_TOOL_NAME: "requirements", FLAGS_TOOL_NAME: "flags", COV_TOOL_NAME: "judgments"}
_TOOL_OF_DISCRIMINATOR = {v: k for k, v in _DISCRIMINATOR_OF_TOOL.items()}


def _schema_property_names(schema, acc):
    if isinstance(schema, dict):
        props = schema.get("properties")
        if isinstance(props, dict):
            for k, v in props.items():
                acc.append(k)
                _schema_property_names(v, acc)
        for key in ("items",):
            if key in schema:
                _schema_property_names(schema[key], acc)
    return acc


def tools_static_check():
    """(C.2) test ESTÁTICO: ningún nombre de propiedad de ningún input_schema es prohibido; `evidence_ids` sin `enum`;
    ningún tool lleva `strict` (ADR-0081 C.1 f); los tres nombres esperados y en orden fijo."""
    names_all = {}
    prohibited = []
    for t in TOOLS:
        names = _schema_property_names(t["input_schema"], [])
        names_all[t["name"]] = names
        prohibited += [f"{t['name']}.{n}" for n in names if n in PROHIBITED_OUTPUT_FIELDS]
    ev = COV_TOOL["input_schema"]["properties"]["judgments"]["items"]["properties"]["evidence_ids"]
    return {"prohibited_found": prohibited,
            "evidence_ids_has_enum": "enum" in ev or "enum" in (ev.get("items") or {}),
            "strict_present": any("strict" in t for t in TOOLS),
            "names": tuple(t["name"] for t in TOOLS),
            "tools_sha": TOOLS_SHA,
            "ok": not prohibited and "enum" not in ev and "enum" not in (ev.get("items") or {})
                  and not any("strict" in t for t in TOOLS)
                  and tuple(t["name"] for t in TOOLS) == (REQ_TOOL_NAME, FLAGS_TOOL_NAME, COV_TOOL_NAME)}


def round_kind(round_):
    if round_ not in ROUND_KIND_OF:
        raise ValueError(f"round fuera de vocabulario: {round_!r} (ROUNDS={ROUNDS})")
    return ROUND_KIND_OF[round_]


def tool_for(entry, round_):
    """El tool que una ronda fuerza a un miembro: r1 → el de su membresía (emit_information_requirements | emit_flags);
    r2/r3 → emit_coverage_judgment para todos."""
    round_kind(round_)
    if round_ == "r1":
        return entry["tool"]
    return COV_TOOL_NAME


# ── tabla de env (las 27 del ADR-0082) con lector TOLERANTE en tiempo de llamada ─────────────────────────────────
_TRUTHY = {"1", "true", "yes", "on"}
_FALSEY = {"0", "false", "no", "off"}
ENV_SPECS = {
    "WITT_COUNCIL":                    {"default": True, "kind": "bool", "reader": "council.enabled", "effect": "kill-switch global"},
    "WITT_COUNCIL_FULL":               {"default": False, "kind": "bool", "reader": "agent_matrix.council_members", "effect": "los 8 operativos se sientan (N=25)"},
    "WITT_MODEL_COUNCIL":              {"default": "", "kind": "str", "reader": "models.resolve_role('council')", "effect": "modelo de los miembros"},
    "WITT_COUNCIL_EFFORT":             {"default": "medium", "kind": "effort", "reader": "council.build_request", "effect": "output_config.effort fijo por ruta"},
    "WITT_CG_COUNCIL_COMPONENT":       {"default": True, "kind": "bool", "reader": "competence.env_config", "effect": "council_uncovered_must gatea"},
    "WITT_COUNCIL_RECOVERAGE":         {"default": True, "kind": "bool", "reader": "runs.execute_run", "effect": "ronda r3"},
    "WITT_COUNCIL_ORIGINS":            {"default": "production", "kind": "csv", "reader": "app.create_plan", "effect": "orígenes que encolan r1"},
    "WITT_COUNCIL_WORKERS":            {"default": 1, "kind": "int", "minimum": 0, "reader": "runs.start_workers", "effect": "hilos council-worker-N"},
    "WITT_COUNCIL_DEDUP_S":            {"default": 600, "kind": "int", "minimum": 0, "reader": "app.create_plan", "effect": "ventana dedup del doble clic"},
    "WITT_COUNCIL_MAX_QUEUED_PER_USER": {"default": 3, "kind": "int", "minimum": 0, "reader": "app.create_plan", "effect": "tope de jobs r1 queued por usuario"},
    "WITT_COUNCIL_CONCURRENCY":        {"default": 6, "kind": "int", "minimum": 1, "maximum": 25, "reader": "council.run_round", "effect": "max_workers del pool"},
    "WITT_COUNCIL_MEMBER_TIMEOUT_S":   {"default": 120, "kind": "int", "minimum": 1, "reader": "council.run_round", "effect": "timeout por miembro"},
    "WITT_COUNCIL_ROUND_BUDGET_S":     {"default": 300, "kind": "int", "minimum": 1, "reader": "council.run_round", "effect": "presupuesto de reloj por ronda"},
    "WITT_COUNCIL_MEMBER_RETRIES":     {"default": 1, "kind": "int", "minimum": 0, "reader": "council.run_round → _anthropic_tool_call(retries=)", "effect": "intentos adicionales por miembro"},
    "WITT_COUNCIL_QUORUM":             {"default": 0.6, "kind": "fraction", "reader": "council.quorum_required", "effect": "fracción de miembros válidos"},
    "WITT_COUNCIL_MAX_REQUIREMENTS":   {"default": 24, "kind": "int", "minimum": 1, "reader": "council.aggregate_r1", "effect": "tope del ledger"},
    "WITT_COUNCIL_MAX_PER_MEMBER":     {"default": MAX_PER_MEMBER_DEFAULT, "kind": "int", "minimum": 1, "reader": "council.validate_tool_input", "effect": "requisitos por miembro (tope de código; el schema fija 5)"},
    "WITT_COUNCIL_R2_EVIDENCE_CHARS":  {"default": 24000, "kind": "int", "minimum": 1, "reader": "council.payload_r2", "effect": "tope de la vista de evidencia por miembro"},
    "WITT_COUNCIL_ATTESTATION_CHARS":  {"default": 4000, "kind": "int", "minimum": 1, "reader": "app (ledger) · council.apply_ledger_decisions", "effect": "tope de knowledge_now / attested_text"},
    "WITT_COUNCIL_CACHE":              {"default": True, "kind": "bool", "reader": "catalog_cards.cache_config", "effect": "cache_control en el system"},
    "WITT_COUNCIL_CACHE_TTL":          {"default": "5m", "kind": "choice", "choices": catalog_cards.CACHE_TTLS, "reader": "catalog_cards.cache_config", "effect": "TTL de la ficha"},
    "WITT_COUNCIL_INDEX":              {"default": True, "kind": "bool", "reader": "council_index · app", "effect": "índice y prior observations"},
    "WITT_COUNCIL_PRIOR_K":            {"default": 5, "kind": "int", "minimum": 0, "maximum": 12, "reader": "council_index.prior_observations", "effect": "observaciones previas en r1"},
    "WITT_COUNCIL_PRIOR_KINDS":        {"default": "requirement,coverage,decision,gap_flag,panel_finding", "kind": "csv", "reader": "council_index.prior_observations", "effect": "kinds que entran al prompt (comment excluido)"},
    "WITT_COUNCIL_INDEX_ORIGINS":      {"default": "production", "kind": "csv", "reader": "council_index · /council/demand", "effect": "orígenes del corpus"},
    "WITT_ANTHROPIC_MAX_INFLIGHT":     {"default": 8, "kind": "int", "minimum": 1, "reader": "composite_auditor._anthropic_tool_call", "effect": "BoundedSemaphore de proceso"},
    "WITT_ANTHROPIC_RETRY_AFTER_CAP_S": {"default": 30, "kind": "int", "minimum": 0, "reader": "composite_auditor._anthropic_tool_call", "effect": "tope al Retry-After honrado"},
}
assert len(ENV_SPECS) == 27


def _env_read(env, name):
    spec = ENV_SPECS[name]
    default = spec["default"]
    # UNA verdad: si models.ENV_TABLE (dueño C3, D.2) ya declara la env, su lector tipado gana; la tabla local sólo
    # cubre el árbol donde C3 aún no aterrizó (misma semántica: vacía/basura → default declarado).
    if name in getattr(models, "ENV_TABLE", {}):
        try:
            v, src = models.env_value(name, env)
            if spec["kind"] == "bool":
                v = bool(v)
            elif spec["kind"] == "fraction":
                v = float(v)
            elif spec["kind"] == "int" and isinstance(v, str):
                v = int(v)
            return {"value": v, "source": src, "default": default}
        except (KeyError, ValueError, TypeError):
            pass
    raw = env.get(name)
    if raw is None or str(raw).strip() == "":
        return {"value": default, "source": f"default ({name} unset)", "default": default}
    s = str(raw).strip()
    kind = spec["kind"]
    try:
        if kind == "bool":
            low = s.lower()
            if low in _TRUTHY:
                return {"value": True, "source": f"env {name}", "default": default}
            if low in _FALSEY:
                return {"value": False, "source": f"env {name}", "default": default}
            raise ValueError(s)
        if kind == "int":
            v = int(s)
            if v < spec.get("minimum", 0) or ("maximum" in spec and v > spec["maximum"]):
                raise ValueError(s)
            return {"value": v, "source": f"env {name}", "default": default}
        if kind == "fraction":
            v = float(s)
            if not (0.0 < v <= 1.0):
                raise ValueError(s)
            return {"value": v, "source": f"env {name}", "default": default}
        if kind == "choice":
            low = s.lower()
            if low not in spec["choices"]:
                raise ValueError(s)
            return {"value": low, "source": f"env {name}", "default": default}
        if kind == "effort":
            low = s.lower()
            if low == "inherit":
                return {"value": "inherit", "source": f"env {name} (inherit WITT_ANTHROPIC_EFFORT)", "default": default}
            if low not in models.ANTHROPIC_EFFORTS:
                raise ValueError(s)
            return {"value": low, "source": f"env {name}", "default": default}
        if kind == "csv":
            items = [x.strip() for x in s.split(",") if x.strip()]
            return {"value": ",".join(items), "source": f"env {name}", "default": default}
        return {"value": s, "source": f"env {name}", "default": default}
    except (ValueError, TypeError):
        return {"value": default, "source": f"default ({name} unparseable: {s[:40]!r})", "default": default}


def env_config(env=None):
    """Las 27 env de la tabla del ADR-0082 → {NAME: {value, source, default}}; vacía/basura → default DECLARADO."""
    env = os.environ if env is None else env
    return {name: _env_read(env, name) for name in ENV_SPECS}


def enabled(env=None):
    """(C.9) kill-switch WITT_COUNCIL (default 1) → (bool, source). Con False NADIE llama a run_round."""
    r = _env_read(os.environ if env is None else env, "WITT_COUNCIL")
    return bool(r["value"]), r["source"]


HEARTBEAT_S = 30
HEARTBEAT_RULE = ("progress every <= 30 s from the orchestrator thread; 30 s < HEARTBEAT_STALE_S 300 s; "
                  "WITT_COUNCIL_ROUND_BUDGET_S 300 s <= WITT_REAP_STALE_S 900 s - 300 s (declared, ADR-0082 C.3)")
COUNCIL_MAX_TOKENS_DEFAULT = 4000        # tope g2 del rol `council` (models.py, dueño C3); aquí sólo el fallback declarado
QUORUM_SOURCE = ("WITT_COUNCIL_QUORUM: required = ceil(q·n_eligible) — n_eligible = the members with something to judge in "
                 "THIS round (r1: all N, 17 → 11, 25 → 15; r2/r3: the owners of a kept requirement — a member 'not-invoked' "
                 "for lack of a kept requirement cannot vote and is NOT in the denominator); a member-emitted not-applicable "
                 "COUNTS as valid (corrector ADR-0082 C.3/C.5)")
# (F7) el socket del caller cabe DENTRO de la ventana del orquestador: antes socket == member_timeout y el reintento de
# transporte arrancaba justo cuando el orquestador abandonaba el future (llamada fantasma: facturada, jamás recogida).
TRANSPORT_BACKOFF_S = 2                    # composite_auditor._backoff(2*(attempt+1)) del primer reintento
SOCKET_TIMEOUT_RULE = ("socket timeout per attempt = max(10, floor((WITT_COUNCIL_MEMBER_TIMEOUT_S - 2·retries) / (retries + 1))) "
                       "so that every attempt of the caller fits inside the orchestrator's per-member window "
                       "(corrector ADR-0082 C.3)")


def config(env=None, **overrides):
    """Configuración PLANA de una ronda (lo que run_round/aggregate/payload leen). `overrides` (p. ej. model=,
    concurrency=, heartbeat_s=, budget_s=) ganan a la env — la corrida pasa la N/membresía CONGELADA del plan."""
    env = os.environ if env is None else env
    e = env_config(env)
    cfg = {
        "enabled": e["WITT_COUNCIL"]["value"], "enabled_source": e["WITT_COUNCIL"]["source"],
        "full": e["WITT_COUNCIL_FULL"]["value"], "full_source": e["WITT_COUNCIL_FULL"]["source"],
        "model": None, "model_source": None,
        "effort_env": e["WITT_COUNCIL_EFFORT"]["value"], "effort_env_source": e["WITT_COUNCIL_EFFORT"]["source"],
        "concurrency": e["WITT_COUNCIL_CONCURRENCY"]["value"], "concurrency_source": e["WITT_COUNCIL_CONCURRENCY"]["source"],
        "member_timeout_s": e["WITT_COUNCIL_MEMBER_TIMEOUT_S"]["value"],
        "member_timeout_source": e["WITT_COUNCIL_MEMBER_TIMEOUT_S"]["source"],
        "budget_s": e["WITT_COUNCIL_ROUND_BUDGET_S"]["value"], "budget_source": e["WITT_COUNCIL_ROUND_BUDGET_S"]["source"],
        "member_retries": e["WITT_COUNCIL_MEMBER_RETRIES"]["value"],
        "member_retries_source": e["WITT_COUNCIL_MEMBER_RETRIES"]["source"],
        "quorum": e["WITT_COUNCIL_QUORUM"]["value"], "quorum_source": e["WITT_COUNCIL_QUORUM"]["source"],
        "max_requirements": e["WITT_COUNCIL_MAX_REQUIREMENTS"]["value"],
        "max_requirements_source": e["WITT_COUNCIL_MAX_REQUIREMENTS"]["source"],
        "max_per_member": e["WITT_COUNCIL_MAX_PER_MEMBER"]["value"],
        "max_per_member_source": e["WITT_COUNCIL_MAX_PER_MEMBER"]["source"],
        "r2_evidence_chars": e["WITT_COUNCIL_R2_EVIDENCE_CHARS"]["value"],
        "r2_evidence_chars_source": e["WITT_COUNCIL_R2_EVIDENCE_CHARS"]["source"],
        "attestation_chars": e["WITT_COUNCIL_ATTESTATION_CHARS"]["value"],
        "recoverage": e["WITT_COUNCIL_RECOVERAGE"]["value"], "recoverage_source": e["WITT_COUNCIL_RECOVERAGE"]["source"],
        "cg_component": e["WITT_CG_COUNCIL_COMPONENT"]["value"],
        "cache": cache_config(env),
        "heartbeat_s": HEARTBEAT_S, "heartbeat_rule": HEARTBEAT_RULE,
        "max_tokens": COUNCIL_MAX_TOKENS_DEFAULT, "max_tokens_source": "default (council.COUNCIL_MAX_TOKENS_DEFAULT)",
        "env_sources": {k: v["source"] for k, v in e.items()},
    }
    for k, v in overrides.items():
        cfg[k] = v
        if k == "model" and "model_source" not in overrides:
            cfg["model_source"] = "caller"
    return cfg


def quorum_required(n_members, quorum=None):
    """ceil(q·n). `n_members` None → None: sin membresía declarada no hay cuórum que calcular (corrector ADR-0082 — una
    corrida sin copia del consejo congela n_members null, no la tabla vigente)."""
    if n_members is None:
        return None
    q = 0.6 if quorum is None else float(quorum)
    return int(math.ceil(q * int(n_members)))


def socket_timeout_s(cfg):
    """(F7, corrector ADR-0082) timeout del SOCKET por intento, dimensionado para que retries+1 intentos + backoff quepan en
    WITT_COUNCIL_MEMBER_TIMEOUT_S; piso 10 s."""
    m = int(cfg["member_timeout_s"])
    r = max(0, int(cfg["member_retries"]))
    return max(10, (m - TRANSPORT_BACKOFF_S * r) // (r + 1))


def resolve_council_model(env=None, cfg=None):
    """{model, source, generation?, max_tokens, max_tokens_source, known, effort, effort_source, effort_sent}: el modelo del
    rol `council` por la tabla (models.resolve_role — dueño C3; si el rol aún no existe en ROLES se DECLARA
    'not-available', jamás un literal aquí — gate estático M.4) y el effort FIJO por ruta (D.2): WITT_COUNCIL_EFFORT
    default 'medium'; vacía/'inherit' → WITT_ANTHROPIC_EFFORT; se ENVÍA sólo a modelos `thinking_default 'adaptive'`."""
    env = os.environ if env is None else env
    cfg = cfg or config(env)
    model, source, generation, max_tokens, mt_src = None, None, None, cfg["max_tokens"], cfg["max_tokens_source"]
    if cfg.get("model"):
        model, source = cfg["model"], cfg.get("model_source") or "caller"
    else:
        try:
            r = models.resolve_role("council", env)
            model, source, generation = r["model"], r["source"], r.get("generation")
            if isinstance(r.get("max_tokens"), int) and r["max_tokens"] > 0:
                max_tokens, mt_src = r["max_tokens"], "models.resolve_role('council').max_tokens"
        except (ValueError, KeyError) as e:
            source = f"not-available (models.resolve_role('council'): {type(e).__name__} — role pending ADR-0082 D.2)"
    if hasattr(models, "council_effort"):
        # (D.2) UNA verdad: models.council_effort (dueño C3) resuelve default 'medium' / env / 'inherit' / basura
        eff, eff_src = models.council_effort(env)
    else:
        eff = cfg.get("effort_env", "medium")
        eff_src = cfg.get("effort_env_source", "default")
        if eff == "inherit":
            try:
                eff, inh_src = models.env_value("WITT_ANTHROPIC_EFFORT", env)
            except KeyError:
                eff, inh_src = None, "WITT_ANTHROPIC_EFFORT not in models.ENV_TABLE"
            eff_src = f"inherited WITT_ANTHROPIC_EFFORT ({inh_src})"
    row = models.MODELS.get(model) if model else None
    if eff and row and row.get("thinking_default") == "adaptive":
        effort_sent, sent_src = eff, eff_src
    else:
        effort_sent = None
        sent_src = (eff_src + " → not-sent (" + ("no effort" if not eff else
                    f"model {model!r} thinking_default {row.get('thinking_default') if row else 'unknown-to-table'}") + ")")
    return {"model": model, "source": source, "generation": generation, "known": bool(row),
            "max_tokens": max_tokens, "max_tokens_source": mt_src,
            "effort": eff, "effort_source": eff_src, "effort_sent": effort_sent, "effort_sent_source": sent_src}


# ── payloads (lo VOLÁTIL va SIEMPRE en el user message; el system es puro) ────────────────────────────────────────
R1_PREAMBLE = ("ROUND 1 — INFORMATION REQUIREMENTS. Read your card (system), then the research question and the plan "
               "judgment below. Emit ONLY the requested tool. `prior_observations`, `inherited_criteria` and "
               "`human_attestations` are PRIOR ART from earlier turns, never evidence.")
R1_FLAGS_PREAMBLE = ("ROUND 1 — FLAGS. Read your card (system), then the research question and the plan judgment below. "
                     "Emit ONLY compliance / budget / partner flags for a human to decide; no requirements, no findings.")
R2_PREAMBLE = ("ROUND {round} — COVERAGE JUDGMENT. Below are YOUR OWN requirements (kept by the human ledger), the "
               "compact evidence view of this run, the ids you may cite, the first-pass synthesis and human attestations "
               "(PRIOR ART, never evidence). For EACH of your requirements judge covered | partial | uncovered citing only "
               "evidence_ids that appear in the evidence; optionally refine the search directive of an uncovered one. "
               "Emit ONLY the tool.")
EVIDENCE_VIEW_STATE = "DI + path_b (structural, if fired)"      # coverage.pre_search.evidence_view (síntesis D2/D3)


def _judgment_view(judgment):
    if not isinstance(judgment, dict):
        return None
    return {k: judgment.get(k) for k in ("work_type", "route", "niches", "clarifying_questions", "state")
            if k in judgment}


def payload_r1(agent, ctx, cfg=None):
    """(user_text, meta) de la ronda 1: pregunta, entidades, juicio del plan, prior observations (letras P-A…),
    criterios heredados y atestiguaciones como PRIOR ART. Sin recorte (insumo acotado por WITT_COUNCIL_PRIOR_K)."""
    cfg = cfg or config()
    ctx = ctx or {}
    entry = agent_matrix.council_member(agent) or {}
    body = {
        "round": "r1", "kind": ROUND_KIND_OF["r1"],
        "question": ctx.get("question"),
        "entities": list(ctx.get("entities") or []),
        "plan_judgment": _judgment_view(ctx.get("judgment")),
        "prior_observations": ctx.get("prior_observations") if ctx.get("prior_observations") is not None else [],
        "prior_observations_state": ctx.get("prior_observations_state"),
        "inherited_criteria": ctx.get("inherited_criteria"),
        "human_attestations": ctx.get("human_attestations"),
        "constraints": {"max_requirements": min(int(cfg["max_per_member"]), MAX_PER_MEMBER_DEFAULT),
                        "priorities": list(PRIORITIES), "evidence_kinds": list(COUNCIL_EVIDENCE_KINDS),
                        "source_families": list(COUNCIL_SOURCE_FAMILIES)},
    }
    pre = R1_FLAGS_PREAMBLE if entry.get("tool") == FLAGS_TOOL_NAME else R1_PREAMBLE
    # ADR-0086 (F6): si viajan imágenes aportadas (un ledger HEREDADO del turno anterior puede traerlas), la cláusula
    # viaja con ellas y el meta lo declara
    _att_head, _n_img = _attested_images_head(ctx.get("human_attestations"))
    text = pre + _att_head + "\n\n" + json.dumps(body, ensure_ascii=False, indent=1, sort_keys=True)
    meta = {"payload_chars": len(text), "payload_truncated": False, "evidence_chars": None}
    if _n_img:
        meta.update(n_attested_images=_n_img, attested_images_rule=ATTESTED_IMAGES_COUNCIL_RULE)
    return text, meta


def is_kept(req):
    """Un requisito entra a r2/r3/directivas SÓLO con decision 'keep' (ledger aprobado o skip con ledger vacío)."""
    return isinstance(req, dict) and req.get("decision") == "keep"


def ledger_requirements(ledger):
    if isinstance(ledger, dict):
        return list(ledger.get("requirements") or [])
    return list(ledger or [])


def requirements_for_member(ledger, agent):
    """Los requisitos KEPT que ESTE miembro pidió (`requested_by ∋ agent`) — el único insumo suyo en r2/r3."""
    return [r for r in ledger_requirements(ledger) if is_kept(r) and agent in (r.get("requested_by") or [])]



# ── ADR-0086 (F6) · LAS IMÁGENES APORTADAS EN EL CONSEJO ─────────────────────────────────────────────────────────
# Ningún miembro del consejo tiene visión en este canal: lo que ve de una imagen aportada es el PIE DE FOTO que escribió
# la persona, más sus metadatos. La cláusula viaja SÓLO cuando de veras viajan imágenes (M.1: una ronda sin ellas es byte
# a byte la de 1.13), y dice las dos cosas que un juez podría suponer mal: que no ha visto la imagen, y que un requisito
# marcado `aporto` está cubierto por la DECISIÓN HUMANA, no por la existencia de una foto.
ATTESTED_IMAGES_COUNCIL_CLAUSE = (
    "ATTESTED IMAGES — `human_attestations.images[]` are pictures a PERSON contributed as PRIOR ART, with provenance on "
    "record. You are shown their CAPTIONS and metadata; you have NOT seen the pixels and you are not given them. Never "
    "claim to have seen one, never describe what it shows, never cite one, and never count one as evidence: what a person "
    "says about their own image is an ATTESTATION and is judged as such. A requirement the human ledger marked `aporto` is "
    "covered BY THAT HUMAN DECISION, never by the existence of a picture.")
ATTESTED_IMAGES_COUNCIL_RULE = ("captions + metadata to the council, never bytes (no council member has vision in this "
                               "channel); an image never covers a requirement by itself — the human `aporto` does "
                               "(ADR-0086 F6)")
ATTESTED_IMAGES_LEDGER_RULE = ("images attach to `knowledge_now` (top-level) or to a requirement the human decided "
                              "`aporto`; an image on a kept or discarded requirement is an error, not a default "
                              "(images_without_aporto) — ADR-0086 J.2")


def attested_images_of(human_attestations):
    """Las imágenes que viajan en este payload (vista de prompt: caption + metadatos, `bytes_delivered` False) o []."""
    if not isinstance(human_attestations, dict):
        return []
    return [i for i in (human_attestations.get("images") or []) if isinstance(i, dict)]


def _attested_images_head(human_attestations):
    """('' | '\n' + cláusula, n) — la cláusula NACE sólo cuando hay imágenes en el payload, y va DENTRO del bloque del
    preámbulo (UN salto de línea, no dos): es una instrucción más, y el cuerpo JSON sigue siendo el bloque que empieza
    tras el primer renglón en blanco — la forma que el payload tiene desde 1.12 y de la que dependen sus lectores."""
    imgs = attested_images_of(human_attestations)
    if not imgs:
        return "", 0
    return "\n" + ATTESTED_IMAGES_COUNCIL_CLAUSE, len(imgs)


def _req_prompt_view(r):
    return {k: r.get(k) for k in ("requirement_id", "gap", "evidence_kind", "source_family", "query_en", "entities",
                                  "acceptance_test", "priority", "harness_state", "n_requested_by")}


def payload_r2(agent, ctx, cfg=None, round_="r2", requirements=None):
    """(user_text, meta) de r2/r3: SUS requisitos kept, la vista compacta de evidencia (recortada a
    WITT_COUNCIL_R2_EVIDENCE_CHARS con `payload_truncated` declarado), los evidence_ids citables, pass1
    {direct_answer, gap_flags, absence_kind, citations} y las atestiguaciones como PRIOR ART."""
    cfg = cfg or config()
    ctx = ctx or {}
    reqs = requirements if requirements is not None else requirements_for_member(ctx.get("ledger"), agent)
    ev = ctx.get("evidence_view")
    ev_text = ev if isinstance(ev, str) else json.dumps(ev, ensure_ascii=False, indent=1, sort_keys=True)
    cap = int(cfg["r2_evidence_chars"])
    truncated = len(ev_text) > cap
    ev_text = ev_text[:cap]
    p1 = ctx.get("pass1") if isinstance(ctx.get("pass1"), dict) else {}
    body = {
        "round": round_, "kind": ROUND_KIND_OF[round_],
        "question": ctx.get("question"),
        "entities": list(ctx.get("entities") or []),
        "your_requirements": [_req_prompt_view(r) for r in reqs],
        "evidence_ids_available": list(ctx.get("evidence_ids") or []),
        "evidence_view": EVIDENCE_VIEW_STATE if round_ == "r2" else "DI + path_b (after directed search)",
        "evidence_chars": len(ev_text), "evidence_truncated": truncated,
        "pass1": {k: p1.get(k) for k in ("direct_answer", "gap_flags", "absence_kind", "citations") if k in p1},
        "human_attestations": ctx.get("human_attestations"),
    }
    # ADR-0086 (F6): los pies de foto viajan al juicio de cobertura; los píxeles, jamás
    _att_head, _n_img = _attested_images_head(ctx.get("human_attestations"))
    head = (R2_PREAMBLE.format(round=round_.upper()) + _att_head + "\n\n"
            + json.dumps(body, ensure_ascii=False, indent=1, sort_keys=True))
    text = head + "\n\nEVIDENCE (compact view" + (f", TRUNCATED at {cap} chars" if truncated else "") + "):\n" + ev_text
    meta = {"payload_chars": len(text), "payload_truncated": truncated, "evidence_chars": len(ev_text),
            "n_requirements": len(reqs)}
    if _n_img:
        meta.update(n_attested_images=_n_img, attested_images_rule=ATTESTED_IMAGES_COUNCIL_RULE)
    return text, meta


def payload_for_round(agent, round_, ctx, cfg=None):
    if round_ == "r1":
        return payload_r1(agent, ctx, cfg)
    return payload_r2(agent, ctx, cfg, round_)


def build_request(agent, round_, ctx=None, cfg=None, env=None, user_text=None):
    """La PETICIÓN de un miembro para una ronda — pura, sin red: {agent, round, kind, tool (nombre), tool_def, tools
    (los TRES, bytes idénticos), tool_choice {type:'tool', name}, system (lista de bloques | str), system_sha, card_sha,
    shared_block_sha, user_text, payload_chars, payload_truncated, model, model_source, max_tokens, effort, effort_source,
    timeout_s, retries}. Lanza ValueError('not-in-membership: …') o ValueError('no-card-in-catalog: …')."""
    env = os.environ if env is None else env
    cfg = cfg or config(env)
    entry = agent_matrix.council_member(agent)
    if entry is None:
        raise ValueError(f"not-in-membership: {agent}")
    tool_name = tool_for(entry, round_)
    system = build_system(agent, env)                        # ValueError('no-card-in-catalog: …') sin ficha
    card = catalog_cards.card(agent)
    if user_text is None:
        user_text, pmeta = payload_for_round(agent, round_, ctx, cfg)
    else:
        pmeta = {"payload_chars": len(user_text), "payload_truncated": False, "evidence_chars": None}
    mres = resolve_council_model(env, cfg)
    return {
        "agent": agent, "round": round_, "kind": ROUND_KIND_OF[round_],
        "seat": entry["seat"], "group": entry["group"], "mode": entry["mode"],
        "tool": tool_name, "tool_def": TOOL_BY_NAME[tool_name], "tools": list(TOOLS), "tools_sha": TOOLS_SHA,
        "tool_choice": {"type": "tool", "name": tool_name},
        "system": system, "system_sha": system_sha(system), "card_sha": card["sha"] if card else None,
        "shared_block_sha": SHARED_BLOCK_SHA, "rules_sha": RULES_SHA,
        "cache": {"enabled": cfg["cache"]["enabled"], "ttl_card": cfg["cache"]["ttl_card"],
                  "ttl_shared": cfg["cache"]["ttl_shared"]},
        "user_text": user_text, "payload_chars": pmeta["payload_chars"], "payload_truncated": pmeta["payload_truncated"],
        "evidence_chars": pmeta.get("evidence_chars"),
        "model": mres["model"], "model_source": mres["source"], "max_tokens": mres["max_tokens"],
        "effort": mres["effort_sent"], "effort_source": mres["effort_sent_source"], "effort_pinned": mres["effort"],
        "timeout_s": socket_timeout_s(cfg), "retries": int(cfg["member_retries"]),
        "member_timeout_s": int(cfg["member_timeout_s"]), "timeout_rule": SOCKET_TIMEOUT_RULE,
    }


def default_caller(request):
    """El caller REAL: composite_auditor._anthropic_tool_call con los TRES tools, tool_choice forzado, system como
    lista de bloques con cache_control, effort pinneado y return_meta=True → (tool_input, usage numérico, meta).
    Sin modelo resuelto → CallerError('no-model') SIN llamar (cero gasto)."""
    if not request.get("model"):
        raise composite_auditor.CallerError("no-model", f"council: no model resolved ({request.get('model_source')})")
    return composite_auditor._anthropic_tool_call(
        request["model"], request["system"], request["user_text"], tool=request["tool_def"],
        timeout=request["timeout_s"], retries=request["retries"], max_tokens=request["max_tokens"],
        effort=request["effort"], return_meta=True, tools=request["tools"])


# ── (C.2) validación por CÓDIGO de lo que un miembro emitió ──────────────────────────────────────────────────────
def _cut(s, cap, field, idx, report):
    if len(s) > cap:
        report["truncated_fields"].append({"index": idx, "field": field, "chars": len(s), "cap": cap})
        return s[:cap]
    return s


def _str_field(item, key, idx, report, required=True):
    v = item.get(key)
    if isinstance(v, str) and v.strip():
        return _cut(v.strip(), STR_CAPS.get(key, 10_000), key, idx, report)
    if required:
        return None
    return None


def _str_list(item, key, cap, idx, report):
    v = item.get(key)
    if v is None:
        return []
    if not isinstance(v, list):
        report["dropped_fields"].append(f"{idx}.{key} (not a list)")
        return []
    out = []
    for x in v:
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
        else:
            report["dropped_fields"].append(f"{idx}.{key}[] (non-string element)")
    if len(out) > cap:
        report["truncated_fields"].append({"index": idx, "field": key, "chars": len(out), "cap": cap})
        out = out[:cap]
    return out


def _drop_unknown(obj, allowed, idx, report):
    for k in list(obj.keys()):
        if k not in allowed:
            tag = f"{idx}.{k}" if idx is not None else k
            report["dropped_fields"].append(tag)
            if k in PROHIBITED_OUTPUT_FIELDS:
                report["prohibited_fields_seen"].append(tag)


def _enum_ok(item, key, vocab, idx, report):
    v = item.get(key)
    if v in vocab:
        return True
    report["off_vocabulary"].append({"index": idx, "field": key, "value": (str(v)[:100] if v is not None else None)})
    return False


def _clean_requirements(raw, report, cap_items):
    props = REQ_TOOL["input_schema"]["properties"]
    _drop_unknown(raw, props, None, report)
    applicable = raw.get("applicable")
    items_raw = raw.get("requirements")
    if not isinstance(items_raw, list):
        items_raw = [] if items_raw is None else None
    if items_raw is None:
        report["kind"] = "invalid-output"
        report["detail"] = "requirements is not a list"
        return None
    report["n_items_raw"] = len(items_raw)
    if applicable is None:
        if items_raw:
            applicable = True
            report["defaulted_fields"].append("applicable (true: requirements present)")
        else:
            report["kind"] = "required-missing:applicable,requirements"
            return None
    if not isinstance(applicable, bool):
        applicable = bool(applicable)
        report["defaulted_fields"].append("applicable (coerced to bool)")
    reason = _str_field(raw, "not_applicable_reason", None, report, required=False)
    notes = _str_field(raw, "notes_for_human", None, report, required=False)
    if applicable is False:
        if items_raw:
            report["dropped_items"].append({"index": "*", "reason": f"applicable false → {len(items_raw)} requirement(s) ignored"})
        return {"applicable": False, "not_applicable_reason": reason, "requirements": [], "notes_for_human": notes}
    item_props = props["requirements"]["items"]["properties"]
    clean = []
    for j, it in enumerate(items_raw):
        if len(clean) >= cap_items:
            report["n_dropped_over_cap"] += 1
            continue
        if not isinstance(it, dict):
            report["dropped_items"].append({"index": j, "reason": "not an object"})
            continue
        _drop_unknown(it, item_props, j, report)
        if not (_enum_ok(it, "evidence_kind", COUNCIL_EVIDENCE_KINDS, j, report)
                and _enum_ok(it, "source_family", COUNCIL_SOURCE_FAMILIES, j, report)
                and _enum_ok(it, "priority", PRIORITIES, j, report)):
            report["dropped_items"].append({"index": j, "reason": "off-vocabulary enum"})
            continue
        gap = _str_field(it, "gap", j, report)
        query = _str_field(it, "query_en", j, report)
        acc = _str_field(it, "acceptance_test", j, report)
        missing = [k for k, v in (("gap", gap), ("query_en", query), ("acceptance_test", acc)) if v is None]
        if missing:
            report["dropped_items"].append({"index": j, "reason": f"required-missing:{','.join(missing)}"})
            continue
        clean.append({"gap": gap, "evidence_kind": it["evidence_kind"], "source_family": it["source_family"],
                      "query_en": query, "entities": _str_list(it, "entities", ENTITIES_CAP, j, report),
                      "acceptance_test": acc, "priority": it["priority"]})
    report["n_items_kept"] = len(clean)
    return {"applicable": True, "not_applicable_reason": reason, "requirements": clean, "notes_for_human": notes}


def _clean_flags(raw, report):
    props = FLAGS_TOOL["input_schema"]["properties"]
    _drop_unknown(raw, props, None, report)
    applicable = raw.get("applicable")
    items_raw = raw.get("flags")
    if not isinstance(items_raw, list):
        items_raw = [] if items_raw is None else None
    if items_raw is None:
        report["kind"] = "invalid-output"
        report["detail"] = "flags is not a list"
        return None
    report["n_items_raw"] = len(items_raw)
    if applicable is None:
        if items_raw:
            applicable = True
            report["defaulted_fields"].append("applicable (true: flags present)")
        else:
            report["kind"] = "required-missing:applicable,flags"
            return None
    reason = _str_field(raw, "not_applicable_reason", None, report, required=False)
    if applicable is False:
        if items_raw:
            report["dropped_items"].append({"index": "*", "reason": f"applicable false → {len(items_raw)} flag(s) ignored"})
        return {"applicable": False, "not_applicable_reason": reason, "flags": []}
    item_props = props["flags"]["items"]["properties"]
    clean = []
    for j, it in enumerate(items_raw):
        if len(clean) >= FLAGS_CAP:
            report["n_dropped_over_cap"] += 1
            continue
        if not isinstance(it, dict):
            report["dropped_items"].append({"index": j, "reason": "not an object"})
            continue
        _drop_unknown(it, item_props, j, report)
        if not _enum_ok(it, "kind", FLAG_KINDS, j, report):
            report["dropped_items"].append({"index": j, "reason": "off-vocabulary kind"})
            continue
        st = _str_field(it, "statement", j, report)
        if st is None:
            report["dropped_items"].append({"index": j, "reason": "required-missing:statement"})
            continue
        clean.append({"kind": it["kind"], "statement": st})
    report["n_items_kept"] = len(clean)
    return {"applicable": True, "not_applicable_reason": reason, "flags": clean}


def _clean_judgments(raw, report):
    props = COV_TOOL["input_schema"]["properties"]
    _drop_unknown(raw, props, None, report)
    items_raw = raw.get("judgments")
    if not isinstance(items_raw, list):
        report["kind"] = "required-missing:judgments" if items_raw is None else "invalid-output"
        if items_raw is not None:
            report["detail"] = "judgments is not a list"
        return None
    report["n_items_raw"] = len(items_raw)
    item_props = props["judgments"]["items"]["properties"]
    sd_props = item_props["search_directive"]["properties"]
    clean = []
    for j, it in enumerate(items_raw):
        if not isinstance(it, dict):
            report["dropped_items"].append({"index": j, "reason": "not an object"})
            continue
        _drop_unknown(it, item_props, j, report)
        if not _enum_ok(it, "coverage", COVERAGE_VOTES, j, report):
            report["dropped_items"].append({"index": j, "reason": "off-vocabulary coverage"})
            continue
        rid = it.get("requirement_id")
        if not (isinstance(rid, str) and rid.strip()):
            report["dropped_items"].append({"index": j, "reason": "required-missing:requirement_id"})
            continue
        rationale = _str_field(it, "rationale", j, report, required=False) or ""
        item = {"requirement_id": rid.strip(), "coverage": it["coverage"],
                "evidence_ids": _str_list(it, "evidence_ids", EVIDENCE_IDS_CAP, j, report), "rationale": rationale}
        sd = it.get("search_directive")
        if isinstance(sd, dict):
            _drop_unknown(sd, sd_props, f"{j}.search_directive", report)
            q = _str_field(sd, "query_en", j, report, required=False)
            ents = _str_list(sd, "entities", ENTITIES_CAP, j, report)
            if q or ents:
                item["search_directive"] = {"query_en": q, "entities": ents}
        elif sd is not None:
            report["dropped_fields"].append(f"{j}.search_directive (not an object)")
        clean.append(item)
    report["n_items_kept"] = len(clean)
    return {"judgments": clean}


def validate_tool_input(agent, round_, raw, cfg=None):
    """(clean, report) — ADR-0082 (C.2): campos desconocidos DESCARTADOS y contados (`dropped_fields[]`, los prohibidos
    además en `prohibited_fields_seen[]`), enums fuera de vocabulario descartan el ÍTEM y se guardan crudos
    (`off_vocabulary[]`, jamás corregidos), excedente sobre el tope descartado en orden (`n_dropped_over_cap`), strings
    largos recortados y declarados (`truncated_fields[]`), tool equivocado → `report.kind 'wrong-tool'` (fila errored).
    `clean` es None cuando `report.kind` está puesto."""
    cfg = cfg or config()
    entry = agent_matrix.council_member(agent)
    report = {"tool": None, "kind": None, "dropped_fields": [], "prohibited_fields_seen": [], "off_vocabulary": [],
              "n_dropped_over_cap": 0, "n_items_raw": 0, "n_items_kept": 0, "dropped_items": [],
              "truncated_fields": [], "defaulted_fields": []}
    if entry is None:
        report["kind"] = "not-in-membership"
        return None, report
    expected = tool_for(entry, round_)
    report["tool"] = expected
    if not isinstance(raw, dict):
        report["kind"] = "invalid-output"
        report["detail"] = f"tool_input is {type(raw).__name__}, not an object"
        return None, report
    own = _DISCRIMINATOR_OF_TOOL[expected]
    seen = [k for k in _TOOL_OF_DISCRIMINATOR if k in raw]
    if own not in raw and seen:
        report["kind"] = "wrong-tool"
        report["tool_seen"] = _TOOL_OF_DISCRIMINATOR[seen[0]]
        report["detail"] = f"expected {expected} (field {own!r}), got fields {seen}"
        return None, report
    if expected == REQ_TOOL_NAME:
        clean = _clean_requirements(raw, report, int(cfg["max_per_member"]))
    elif expected == FLAGS_TOOL_NAME:
        clean = _clean_flags(raw, report)
    else:
        clean = _clean_judgments(raw, report)
    return clean, report


# ── (C.3) una RONDA: pool, escalonado, latido, timeouts, presupuesto, cancelación, eventos desde el orquestador ──
class RoundCancelled(Exception):
    """`cancel_check()` devolvió verdadero a media ronda: `.result` es el RoundResult PARCIAL (pendientes
    `skipped-cancelled`, en vuelo abandonados, usage de los que SÍ terminaron). Si `cancel_check` LANZÓ (p. ej.
    runs.RunCancelled), se relanza ESA excepción con `.council_round_result` adjunto."""

    def __init__(self, result):
        super().__init__("council round cancelled")
        self.result = result


def _usage_add(acc, usage):
    if not isinstance(usage, dict):
        return acc
    for k, v in usage.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            acc[k] = acc.get(k, 0) + v
    return acc


def _member_usage(usage, meta, err=None):
    """usage de la fila = TODOS los intentos: el de la respuesta final (o el de CallerError.usage) + los intentos previos
    que el caller declaró en meta.usage_prior_attempts (composite_auditor D.1). None cuando nada se midió."""
    acc = {}
    if isinstance(usage, dict):
        _usage_add(acc, usage)
    if err is not None and isinstance(getattr(err, "usage", None), dict):
        _usage_add(acc, err.usage)
    m = meta if isinstance(meta, dict) else (getattr(err, "meta", None) if err is not None else None)
    if isinstance(m, dict):
        for u in m.get("usage_prior_attempts") or []:
            _usage_add(acc, u)
    if not acc:
        return None
    return {k: acc[k] for k in ("input_tokens", "output_tokens", "thinking_tokens", "cache_creation_input_tokens",
                                 "cache_read_input_tokens") if k in acc}


def _unpack(res):
    if isinstance(res, tuple) and len(res) == 3:
        out, usage, meta = res
        return out, usage, (meta if isinstance(meta, dict) else {})
    if isinstance(res, tuple) and len(res) == 2:
        return res[0], res[1], {}
    raise TypeError(f"caller must return (tool_input, usage[, meta]); got {type(res).__name__}")


def _base_row(agent, round_):
    entry = agent_matrix.council_member(agent)
    card = catalog_cards.card(agent)
    return {
        "agent": agent, "round": round_, "tool": None, "status": None, "error_kind": None, "error": None,
        "attempts": 0, "elapsed_s": None, "queue_wait_s": None, "usage": None,
        "payload_chars": None, "payload_truncated": None,
        "card_sha": card["sha"] if card else None, "system_sha": None,
        "model_reported": None, "relation": "not-reported",
        "seat": entry["seat"] if entry else None, "group": entry["group"] if entry else None,
        "mode": entry["mode"] if entry else None,
        "hard_rule_gate": bool(entry and entry["hard_rule_gate"]), "exploratory": bool(entry and entry["exploratory"]),
        "from_operative": bool(entry and entry["from_operative"]),
        "dispatched": False,
    }


def _abandon(row, status, reason, cfg, model):
    row["status"] = status
    if status == "timeout":
        row["error_kind"] = "timeout"
    row["abandoned"] = True
    row["abandon_reason"] = reason
    row["usage"] = None
    row["late_usage_state"] = "unrecoverable (thread abandoned; provider bills up to max_tokens)"


def abandoned_cost_upper(n, payload_chars_total, max_tokens, model, attempts_possible=1):
    """[E] cota SUPERIOR del gasto de llamadas abandonadas (PROYECCIÓN, ADR-0082 H): n × attempts_possible ×
    (payload_tokens_est × p_in + max_tokens × p_out) con tokens_est = chars/4 y precios de la tabla (models.prices).
    `attempts_possible` = retries + 1 del caller: un hilo abandonado pudo lanzar TODOS sus intentos (corrector ADR-0082 —
    antes contaba 1 por hilo). Sin modelo cotizable → usd None con estado declarado; la fila jamás dice 0."""
    k = max(1, int(attempts_possible or 1))
    rule = ("n_threads × attempts_possible × (ceil(payload_chars/4) × price_in + max_tokens × price_out) / 1e6 — upper bound, "
            "class PROJECTION")
    if not n:
        return {"n": 0, "attempts_possible": k, "n_calls_upper": 0, "usd": 0.0, "class": "PROJECTION",
                "state": "no abandoned threads (0 measured)", "rule": rule}
    p = models.prices().get(model) if model else None
    if not p:
        return {"n": n, "attempts_possible": k, "n_calls_upper": n * k, "usd": None, "class": "PROJECTION", "rule": rule,
                "state": f"not-priced (model {model!r} unknown to models.prices)"}
    tokens_in = math.ceil((payload_chars_total or 0) / 4.0)
    usd = k * (tokens_in * p[0] + n * int(max_tokens or 0) * p[1]) / 1e6
    return {"n": n, "attempts_possible": k, "n_calls_upper": n * k, "usd": round(usd, 6), "class": "PROJECTION",
            "rule": rule, "state": "projected",
            "assumptions": {"payload_tokens_est": tokens_in, "max_tokens": max_tokens, "price_in_per_mtok": p[0],
                            "price_out_per_mtok": p[1], "model": model, "attempts_possible": k}}


def run_round(members, round_, ctx, caller=None, budget_s=None, on_event=None, cancel_check=None, cfg=None,
              env=None, clock=None, payload_for=None, phase=None, cancel_exc=None):
    """ADR-0082 (C.3) — ejecuta UNA ronda del consejo sobre `members` (nombres en el orden CONGELADO de
    `agent_matrix.council_members(full=…)`; N = len(members)) y devuelve el RoundResult (forma en el docstring del
    módulo / contrato C2). NUNCA escribe respuesta ni veredicto: sólo recoge lo que cada miembro emitió por su tool y lo
    valida por código.

    · `caller(request) -> (tool_input, usage, meta)` (default `default_caller` → composite_auditor); un fake lo sustituye
      entero (cero red). CallerError/excepciones → fila `errored` con kind.
    · el miembro #1 se lanza SOLO y los demás sólo cuando termina (`stagger_wait_s`; el prefijo compartido se escribe una
      vez y se lee N−1 — Context 7); después ≤ `concurrency` en vuelo, despachados UNO a UNO (antes de cada despacho se
      consulta `cancel_check` y el presupuesto: `skipped-cancelled` / `skipped-budget` = CERO llamadas).
    · timeout por miembro (`member_timeout_s`) → fila `timeout` (abandonado y contado); presupuesto de ronda vencido →
      pendientes `skipped-budget`, en vuelo `timeout` (abandon_reason 'round-budget'); `abandoned_threads` +
      `abandoned_cost_upper` [E].
    · `cancel_check()` (= runs._check_cancel, que LANZA) o que devuelve verdadero → pendientes `skipped-cancelled`, en vuelo
      abandonados, usage de los recogidos conservado, y se relanza la excepción del cancel_check (con
      `.council_round_result`) o RoundCancelled(result).
    · TODOS los eventos (`on_event(type, payload)`) salen del HILO LLAMADOR: `stage.council.member` (phase start | done),
      `stage.council.progress` cada ≤ heartbeat_s sin recogidas, `stage.council.round` al cerrar. Nunca desde el pool.
    · `clock` inyectable (default time.monotonic) para elapsed/deadlines; `payload_for(agent, round, ctx, cfg)`
      inyectable (default payload_for_round)."""
    round_kind(round_)
    env = os.environ if env is None else env
    cfg = cfg or config(env)
    clock = clock or time.monotonic
    caller = caller or default_caller
    payload_fn = payload_for or payload_for_round
    on_event = on_event or (lambda t, p: None)
    budget = float(budget_s if budget_s is not None else cfg["budget_s"])
    concurrency = max(1, min(25, int(cfg["concurrency"])))
    member_timeout = float(cfg["member_timeout_s"])
    heartbeat_s = float(cfg.get("heartbeat_s", HEARTBEAT_S))
    members = list(members)
    N = len(members)
    phase = phase or (ctx or {}).get("phase") or ("plan" if round_ == "r1" else "run")
    mres = resolve_council_model(env, cfg)
    orchestrator_thread = threading.get_ident()
    events = {"n": 0, "threads": set()}
    t0 = clock()
    last_event_at = [t0]

    def emit(etype, payload):
        events["n"] += 1
        events["threads"].add(threading.get_ident())
        last_event_at[0] = clock()
        on_event(etype, payload)

    # ── filas y peticiones (puras; una ficha ausente o un miembro fuera de tabla es fila errored, no excepción) ──
    rows = {a: _base_row(a, round_) for a in members}
    requests = {}
    dispatch_order = []
    for a in members:
        row = rows[a]
        entry = agent_matrix.council_member(a)
        if entry is None:
            row.update({"status": "errored", "error_kind": "not-in-membership",
                        "error": f"not-in-membership: {a} (cm-1)"})
            continue
        row["tool"] = tool_for(entry, round_)
        if round_ != "r1":
            mine = requirements_for_member((ctx or {}).get("ledger"), a)
            if not mine:
                row.update({"status": "not-invoked",
                            "not_invoked_reason": "no kept requirement requested by this member (r2/r3 judge only their own)"})
                continue
        try:
            req = build_request(a, round_, ctx, cfg, env)
        except ValueError as e:
            kind = "no-card-in-catalog" if str(e).startswith("no-card-in-catalog") else "not-in-membership"
            row.update({"status": "errored", "error_kind": kind, "error": f"ValueError: {e}"[:300]})
            continue
        except Exception as e:                                     # payload_for/caller-side surprises → fila, no caída
            row.update({"status": "errored", "error_kind": "caller-exception",
                        "error": f"{type(e).__name__}: {e}"[:300]})
            continue
        if payload_fn is not payload_for_round:
            try:
                text, pmeta = payload_fn(a, round_, ctx, cfg)
                req["user_text"], req["payload_chars"] = text, pmeta.get("payload_chars", len(text))
                req["payload_truncated"] = pmeta.get("payload_truncated", False)
            except Exception as e:
                row.update({"status": "errored", "error_kind": "caller-exception",
                            "error": f"payload_for {type(e).__name__}: {e}"[:300]})
                continue
        row.update({"system_sha": req["system_sha"], "payload_chars": req["payload_chars"],
                    "payload_truncated": req["payload_truncated"]})
        requests[a] = req
        dispatch_order.append(a)

    shared_shas = set()
    for req in requests.values():
        s = req["system"]
        shared_shas.add(_sha256(s[0]["text"]) if isinstance(s, list) else _sha256(s[:len(SHARED_BLOCK_TEXT)]))

    # ── ejecución ──
    def _work(agent, request):
        t_start = clock()
        try:
            out, usage, meta = _unpack(caller(request))
            return {"agent": agent, "ok": True, "out": out, "usage": usage, "meta": meta, "elapsed_s": clock() - t_start}
        except BaseException as e:                                 # nada sale del hilo sin envolverse
            return {"agent": agent, "ok": False, "exc": e, "elapsed_s": clock() - t_start}

    def _collect(agent, res):
        row, req = rows[agent], requests[agent]
        row["elapsed_s"] = round(res["elapsed_s"], 3)
        if res["ok"]:
            out, usage, meta = res["out"], res["usage"], res["meta"]
            row["attempts"] = int(meta.get("attempts") or 1)
            row["usage"] = _member_usage(usage, meta)
            row["model_reported"] = meta.get("model_reported")
            for k in ("queue_wait_s", "retry_after_honored_s", "stop_reason", "response_id"):
                if meta.get(k) is not None:
                    row["meta_" + k if k in ("queue_wait_s",) else k] = meta[k]
            clean, report = validate_tool_input(agent, round_, out, cfg)
            row["validation"] = report
            if report["kind"]:
                row.update({"status": "errored", "error_kind": report["kind"],
                            "error": report.get("detail") or report["kind"]})
            elif clean.get("applicable") is False:
                row.update({"status": "not-applicable", "output": clean,
                            "not_applicable_reason": clean.get("not_applicable_reason")})
            else:
                row.update({"status": "ok", "output": clean})
        else:
            e = res["exc"]
            kind = composite_auditor.failure_kind_of(e)
            if kind == "unclassified" and not isinstance(e, composite_auditor.CallerError):
                kind = "caller-exception"
            meta = getattr(e, "meta", None)
            row["attempts"] = int((meta or {}).get("attempts") or 1)
            row["usage"] = _member_usage(None, None, err=e)
            if isinstance(meta, dict) and meta.get("model_reported"):
                row["model_reported"] = meta["model_reported"]
            if getattr(e, "retry_after", None) is not None:
                row["retry_after_s"] = e.retry_after
            row.update({"status": "errored", "error_kind": kind, "error": f"{type(e).__name__}: {e}"[:300]})
        row["relation"] = models.relation(req["model"], row["model_reported"])
        emit("stage.council.member", {
            "round": round_, "agent": agent, "tool": row["tool"], "phase": "done", "status": row["status"],
            "error_kind": row["error_kind"], "elapsed_s": row["elapsed_s"], "attempts": row["attempts"],
            "attempt": row["attempts"] or 1,           # corrector ADR-0082 (J): la MISMA llave que en phase 'start'
            "max_attempts": int(cfg["member_retries"]) + 1,
            "cache_read": (row["usage"] or {}).get("cache_read_input_tokens"), "heartbeat": True})

    cancelled = {"flag": False, "exc": None}
    cancel_check_errors = []
    cancel_types = tuple(cancel_exc) if cancel_exc else ()

    def _is_cancel_exc(e):
        # corrector ADR-0082 (C.3): SÓLO la excepción de cancelación DECLARADA cuenta como cancelación — RoundCancelled, las
        # clases pasadas en `cancel_exc` o la del contrato de runs (`RunCancelled`, por nombre: lib no importa runs). Un
        # fallo transitorio del propio cancel_check (OSError, OperationalError…) NO es una cancelación: antes marcaba a
        # los pendientes 'skipped-cancelled' y afirmaba en el registro una cancelación que nunca ocurrió.
        return (isinstance(e, RoundCancelled) or bool(cancel_types and isinstance(e, cancel_types))
                or type(e).__name__ == "RunCancelled")

    def _cancel_requested():
        if cancel_check is None:
            return False
        try:
            c = cancel_check()
        except BaseException as e:                                 # runs._check_cancel LANZA RunCancelled
            if not _is_cancel_exc(e):
                if isinstance(e, (KeyboardInterrupt, SystemExit)):
                    raise
                cancel_check_errors.append({"kind": type(e).__name__, "error": f"{type(e).__name__}: {e}"[:200],
                                            "at_s": round(clock() - t0, 3)})
                return False                                       # la ronda SIGUE; el error queda medido
            cancelled["exc"] = e
            c = True
        if c:
            cancelled["flag"] = True
        return bool(c)

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix=f"council-{round_}")
    in_flight = {}            # future → (agent, dispatched_at)
    pending = list(dispatch_order)
    eligible_at = t0
    stagger = {"wait_s": None, "first": None, "first_status": None}
    n_dispatched = 0
    abandoned = []

    def _dispatch(agent):
        nonlocal n_dispatched
        now = clock()
        req = requests[agent]
        row = rows[agent]
        row["dispatched"] = True
        row["queue_wait_s"] = round(max(0.0, now - eligible_at), 3)
        fut = executor.submit(_work, agent, req)
        in_flight[fut] = (agent, now)
        n_dispatched += 1
        emit("stage.council.member", {"round": round_, "agent": agent, "tool": row["tool"], "phase": "start",
                                      "attempt": 1, "max_attempts": int(cfg["member_retries"]) + 1, "heartbeat": True})

    def _mark_pending(status, reason):
        for a in pending:
            rows[a]["status"] = status
            rows[a]["skip_reason"] = reason
        pending.clear()

    def _abandon_in_flight(status, reason):
        for fut, (a, _) in list(in_flight.items()):
            _abandon(rows[a], status, reason, cfg, mres["model"])
            abandoned.append(a)
            fut.cancel()
        in_flight.clear()

    def _over_budget(now):
        return (now - t0) >= budget

    def _service(wait_s):
        """Espera ≤ wait_s a que termine algún future, recoge lo terminado (emitiendo desde ESTE hilo), aplica timeouts
        por miembro y latido. Devuelve True si hubo recogidas."""
        got = False
        if in_flight:
            done, _ = concurrent.futures.wait(list(in_flight), timeout=max(0.0, wait_s),
                                              return_when=concurrent.futures.FIRST_COMPLETED)
            for fut in done:
                agent, _started = in_flight.pop(fut)
                _collect(agent, fut.result())
                got = True
        now = clock()
        for fut, (a, started) in list(in_flight.items()):
            if now - started >= member_timeout:
                _abandon(rows[a], "timeout", f"member-timeout ({member_timeout:g}s)", cfg, mres["model"])
                rows[a]["elapsed_s"] = round(now - started, 3)
                abandoned.append(a)
                fut.cancel()
                del in_flight[fut]
                emit("stage.council.member", {"round": round_, "agent": a, "tool": rows[a]["tool"], "phase": "done",
                                              "status": "timeout", "error_kind": "timeout",
                                              "elapsed_s": rows[a]["elapsed_s"], "attempts": rows[a]["attempts"] or 1,
                                              "attempt": rows[a]["attempts"] or 1,
                                              "max_attempts": int(cfg["member_retries"]) + 1, "heartbeat": True})
        if now - last_event_at[0] >= heartbeat_s:
            n_done = sum(1 for r in rows.values() if r["status"] in ("ok", "not-applicable", "errored", "timeout"))
            emit("stage.council.progress", {"round": round_, "n_done": n_done,
                                            "n_pending": len(pending) + len(in_flight),
                                            "elapsed_s": round(now - t0, 3), "heartbeat": True})
        return got

    def _next_wait():
        now = clock()
        cands = [heartbeat_s, budget - (now - t0)]
        for _f, (_a, started) in in_flight.items():
            cands.append(member_timeout - (now - started))
        return max(0.0, min(cands))

    try:
        # ── el miembro #1 va SOLO (caché: el prefijo compartido se escribe una vez) ──
        if pending:
            if _cancel_requested():
                _mark_pending("skipped-cancelled", "cancel requested before first dispatch")
            elif _over_budget(clock()):
                _mark_pending("skipped-budget", f"round budget {budget:g}s exhausted before first dispatch")
            else:
                first = pending.pop(0)
                stagger["first"] = first
                _dispatch(first)
                while in_flight:
                    _service(_next_wait())
                    if _over_budget(clock()) and in_flight:
                        _abandon_in_flight("timeout", "round-budget")
                        _mark_pending("skipped-budget", f"round budget {budget:g}s exhausted")
                stagger["wait_s"] = round(clock() - t0, 3)
                stagger["first_status"] = rows[first]["status"]
                eligible_at = clock()
        # ── la oleada: ≤ concurrency en vuelo, un despacho a la vez con sus compuertas ──
        while pending or in_flight:
            while pending and len(in_flight) < concurrency:
                if _cancel_requested():
                    _mark_pending("skipped-cancelled", "cancel requested mid-round")
                    break
                if _over_budget(clock()):
                    _mark_pending("skipped-budget", f"round budget {budget:g}s exhausted")
                    break
                _dispatch(pending.pop(0))
            if cancelled["flag"]:
                break
            if not in_flight:
                continue
            got = _service(_next_wait())
            if got and _cancel_requested():
                break
            if _over_budget(clock()) and in_flight:
                _abandon_in_flight("timeout", "round-budget")
                _mark_pending("skipped-budget", f"round budget {budget:g}s exhausted")
        if cancelled["flag"]:
            _abandon_in_flight("skipped-cancelled", "cancel requested mid-round (dispatched, abandoned)")
            _mark_pending("skipped-cancelled", "cancel requested mid-round")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    # ── cierre: conteos, cuórum, usage, cota de abandonados, evento de ronda ──
    elapsed = round(clock() - t0, 3)
    order_rows = [rows[a] for a in members]
    counts = {s: sum(1 for r in order_rows if r["status"] == s) for s in MEMBER_STATES}
    n_valid = counts["ok"] + counts["not-applicable"]
    n_invoked = sum(1 for r in order_rows if r["dispatched"])
    # corrector ADR-0082 (C.3/C.5): el DENOMINADOR del cuórum son los miembros ELEGIBLES de ESTA ronda. En r2/r3 un miembro
    # sin requisito kept queda 'not-invoked' y jamás puede votar; contarlo en N hacía 'incomplete' POR CONSTRUCCIÓN toda
    # ronda con ≤ 10 dueños aunque TODOS votaran válido (la compuerta declaraba no competente sin haber medido nada y
    # forzaba búsqueda + pass2). r1: todos elegibles (n_eligible == N). 0 elegibles → cuórum vacuo declarado.
    n_eligible = N - counts["not-invoked"]
    required_full = quorum_required(N, cfg["quorum"])
    required = quorum_required(n_eligible, cfg["quorum"]) if n_eligible > 0 else 0
    met = n_valid >= required
    usage_tot = {}
    for r in order_rows:
        _usage_add(usage_tot, r["usage"])
    usage = {"in": usage_tot.get("input_tokens", 0), "out": usage_tot.get("output_tokens", 0),
             "cache_creation": usage_tot.get("cache_creation_input_tokens", 0),
             "cache_read": usage_tot.get("cache_read_input_tokens", 0),
             "n_members_measured": sum(1 for r in order_rows if r["usage"] is not None)}
    if "thinking_tokens" in usage_tot:
        usage["thinking_tokens"] = usage_tot["thinking_tokens"]
    aband_chars = sum(int(rows[a]["payload_chars"] or 0) for a in abandoned)
    state = "applicable" if met else "incomplete"
    result = {
        "module_version": MODULE_VERSION, "council_version": COUNCIL_VERSION, "membership_version": MEMBERSHIP_VERSION,
        "round": round_, "kind": ROUND_KIND_OF[round_], "phase": phase, "state": state,
        "n_members": N, "members_order": list(members),
        "n_invoked": n_invoked, "n_valid": n_valid, "n_ok": counts["ok"], "n_not_applicable": counts["not-applicable"],
        "n_errored": counts["errored"], "n_timeout": counts["timeout"], "n_skipped_budget": counts["skipped-budget"],
        "n_skipped_cancelled": counts["skipped-cancelled"], "n_not_invoked": counts["not-invoked"],
        "n_eligible": n_eligible,
        "quorum": {"required": required, "met": met, "ratio": float(cfg["quorum"]), "n_valid": n_valid, "n_members": N,
                   "n_eligible": n_eligible, "n_not_invoked": counts["not-invoked"], "required_full_membership": required_full,
                   "state": ("vacuous (0 eligible members)" if n_eligible == 0 else ("met" if met else "not-met")),
                   "source": cfg.get("quorum_source"), "rule": QUORUM_SOURCE},
        "cancel_check_errors": cancel_check_errors, "n_cancel_check_errors": len(cancel_check_errors),
        "budget_s": budget, "elapsed_s": elapsed, "over_budget": elapsed > budget,
        "stagger_wait_s": stagger["wait_s"], "stagger_first": {"agent": stagger["first"], "status": stagger["first_status"]},
        "concurrency": concurrency, "member_timeout_s": member_timeout, "heartbeat_s": heartbeat_s,
        "abandoned_threads": len(abandoned), "abandoned_agents": list(abandoned),
        "abandoned_cost_upper_usd": abandoned_cost_upper(len(abandoned), aband_chars, mres["max_tokens"], mres["model"],
                                                         attempts_possible=int(cfg["member_retries"]) + 1),
        "late_usage_state": ("unrecoverable (thread abandoned; provider bills up to max_tokens)" if abandoned
                             else "not-applicable (0 abandoned)"),
        "cache_prefix_identical_across_members": (len(shared_shas) == 1) if shared_shas else None,
        "cache": {"enabled": cfg["cache"]["enabled"], "ttl_card": cfg["cache"]["ttl_card"],
                  "ttl_shared": cfg["cache"]["ttl_shared"], "min_cacheable_tokens": MIN_CACHEABLE_TOKENS,
                  "creation": usage["cache_creation"], "read": usage["cache_read"], "class": "medicion"},
        "model": {"requested": mres["model"], "source": mres["source"], "generation": mres["generation"],
                  "effort": mres["effort_sent"], "effort_source": mres["effort_sent_source"],
                  "effort_pinned": mres["effort"], "max_tokens": mres["max_tokens"]},
        "tools_sha": TOOLS_SHA, "rules_sha": RULES_SHA, "shared_block_sha": SHARED_BLOCK_SHA,
        "catalog_sha": catalog_cards.CATALOG_SHA,
        "members": order_rows, "usage": usage,
        "cancelled": cancelled["flag"],
        "events": {"n": events["n"], "emitted_from": ("orchestrator-thread" if events["threads"] <= {orchestrator_thread}
                                                      else "MIXED (bug)"), "heartbeat_rule": HEARTBEAT_RULE},
    }
    emit("stage.council.round", {
        "round": round_, "kind": ROUND_KIND_OF[round_], "phase": phase, "n_members": N, "n_invoked": n_invoked,
        "n_eligible": n_eligible, "n_valid": n_valid, "n_errored": counts["errored"], "n_timeout": counts["timeout"],
        "n_skipped_budget": counts["skipped-budget"], "n_skipped_cancelled": counts["skipped-cancelled"],
        "quorum": result["quorum"], "budget_s": budget, "elapsed_s": elapsed, "over_budget": result["over_budget"],
        "stagger_wait_s": stagger["wait_s"], "abandoned_threads": len(abandoned), "state": state,
        "cancelled": cancelled["flag"], "heartbeat": True})
    result["events"]["n"] = events["n"]
    result["events"]["emitted_from"] = ("orchestrator-thread" if events["threads"] <= {orchestrator_thread}
                                        else "MIXED (bug)")
    if cancelled["flag"]:
        if cancelled["exc"] is not None:
            try:
                cancelled["exc"].council_round_result = result
            except Exception:
                pass
            raise cancelled["exc"]
        raise RoundCancelled(result)
    return result


# ── (C.4) agregación de la ronda 1 — código puro, byte a byte ─────────────────────────────────────────────────────
_TOKEN_RE = re.compile(r"[a-z0-9]+")
REQUIREMENT_ID_RULE = ("'req-' + sha256(f'{source_family}|{evidence_kind}|{tokens}')[:12], tokens = sorted unique "
                       "lowercase [a-z0-9]+ of query_en ∪ entities")
DEDUP_RULE = "one requirement per requirement_id (family, evidence_kind, normalized query ∪ entities)"
PRIORITY_RULE = "max over requesters (must if any requester said must); exploratory-only → must degraded to should"
ORDER_RULE = "must > should, n_requested_by desc, requirement_id asc; cap WITT_COUNCIL_MAX_REQUIREMENTS"
EXPLORATORY_DOWNGRADE_REASON = ("CLAUDE.md §7 (:147-148): cross-field-bridge-agent is Method 2 only / Test 5 exploratory "
                                "in Phase I — a requirement emitted ONLY by exploratory members cannot be a must")


def requirement_tokens(query_en, entities):
    text = " ".join([query_en or ""] + [e for e in (entities or []) if isinstance(e, str)]).lower()
    return sorted(set(_TOKEN_RE.findall(text)))


def requirement_id(source_family, evidence_kind, query_en, entities):
    toks = requirement_tokens(query_en, entities)
    return "req-" + _sha256(f"{source_family}|{evidence_kind}|{' '.join(toks)}")[:12]


HARNESS_STATE_RULE = ("search_harness.family_available(family) read at CALL time (ADR-0084 F.1): rows with fn None and "
                      "adapter None → unsatisfiable (their unavailable_reason: tooluniverse, ADR-0085); rows with dynamic "
                      "availability (web → web_locator.provider_state: WITT_WEB_LOCATOR / BRAVE_API_KEY) → satisfiable when "
                      "the locator can dispatch NOW, else 'unsatisfiable-by-harness (tool-unavailable (ADR-0084…))'; "
                      "evidence_kind figure → unsatisfiable (ADR-0083)")


def harness_state_for(source_family, evidence_kind, env=None):
    """'satisfiable' | 'unsatisfiable-by-harness (<razón>)': `figure` (ADR-0083) y las familias que el harness NO puede
    despachar AHORA según `search_harness.family_available` (ADR-0084 F.1 — UNA verdad de disponibilidad, leída en la
    llamada): tooluniverse (sin mecanismo, ADR-0085) y `web` cuando el localizador está apagado o sin llave (bajo off o
    derivado el literal EXACTO de 7d9ce15 — UNA verdad: `search_harness.WEB_UNSATISFIABLE_LITERAL`, que los smokes importan;
    con causa cuando el operador fijó brave/anthropic sin llave). Con llave la directiva web se COMPILA ('satisfiable'). Nota: europepmc tiene
    tool_module None pero `fn` (answer_pipeline) → SÍ es satisfiable. `env` (dict) sustituye a os.environ en los smokes."""
    if evidence_kind == "figure":
        return "unsatisfiable-by-harness (evidence_kind figure — ADR-0083)"
    ok, why = search_harness.family_available(source_family, env)
    if ok:
        return "satisfiable"
    return f"{search_harness.UNSATISFIABLE_PREFIX}{why or 'no tool module'})"


def _default_resolver(entity):
    """True/ensdarg cuando la entidad resuelve en la fuente de verdad (resolve_id, DATA INAMOVIBLE, sólo lectura);
    None cuando NOT_FOUND. Import perezoso: el módulo no lee archivos al importar."""
    from lib import resolve_id
    r = resolve_id.resolve(entity)
    if r is resolve_id.NOT_FOUND:
        return None
    return getattr(r, "ensdarg", None) or True


def _resolve_entities(entities, resolver):
    resolved, unresolved, detail = [], [], []
    state = "checked (resolve_id.resolve)"
    for e in entities:
        try:
            r = resolver(e)
        except Exception as ex:                                    # jamás afirma: todo queda sin resolver, declarado
            r = None
            state = f"errored ({type(ex).__name__})"
        if r:
            resolved.append(e)
            detail.append({"entity": e, "ensdarg": r if isinstance(r, str) else None})
        else:
            unresolved.append(e)
    return resolved, unresolved, detail, state


def aggregate_r1(round_result, members=None, cfg=None, resolver=None):
    """ADR-0082 (C.4) `aggregate_requirements`: de las filas `ok` de r1 → el agregado DETERMINISTA (mismos insumos
    barajados → mismo JSON, mismos ids). Devuelve {state ∈ AGGREGATE_STATES, n_members, n_valid, n_raw, n_dedup,
    n_requirements, n_must, n_should, truncated, n_truncated, truncated_ids[], n_unsatisfiable, n_hard_rule,
    n_exploratory, n_from_operative, n_flags, requirements[], flags[], notes_for_human[], not_applicable_members[],
    entities_resolution_state, aggregation_sha, rules, shas}. Los requisitos NO llevan decisión (el ledger humano las
    añade: apply_ledger_decisions)."""
    cfg = cfg or config()
    resolver = resolver or _default_resolver
    rows = round_result.get("members") if isinstance(round_result, dict) else list(round_result)
    order = list(members or (round_result.get("members_order") if isinstance(round_result, dict) else None)
                 or [r["agent"] for r in rows])
    idx = {a: i for i, a in enumerate(order)}
    rows_sorted = sorted([r for r in rows if r.get("agent") in idx], key=lambda r: idx[r["agent"]])
    raw_items, flags_raw, notes, not_applicable = [], [], [], []
    for r in rows_sorted:
        a = r["agent"]
        entry = agent_matrix.council_member(a) or {"hard_rule_gate": False, "exploratory": False, "from_operative": False}
        if r.get("status") == "not-applicable":
            not_applicable.append({"agent": a, "reason": r.get("not_applicable_reason")})
            continue
        if r.get("status") != "ok":
            continue
        out = r.get("output") or {}
        if r.get("tool") == FLAGS_TOOL_NAME:
            for f in out.get("flags") or []:
                flags_raw.append((idx[a], a, f))
        else:
            for j, it in enumerate(out.get("requirements") or []):
                raw_items.append((idx[a], j, a, it, entry))
        if out.get("notes_for_human"):
            notes.append({"agent": a, "text": out["notes_for_human"]})
    groups = {}
    for tup in raw_items:
        it = tup[3]
        rid = requirement_id(it["source_family"], it["evidence_kind"], it["query_en"], it.get("entities"))
        groups.setdefault(rid, []).append(tup)
    reqs = []
    res_state = "not-applicable (0 entities)"
    for rid, emits in groups.items():
        emits.sort(key=lambda t: (t[0], t[1]))
        first = emits[0][3]
        requested_by = []
        for t in emits:
            if t[2] not in requested_by:
                requested_by.append(t[2])
        variants, gap_variants, acc_variants, entities = [], [], [], []
        for t in emits:
            it = t[3]
            if it["query_en"] != first["query_en"] and it["query_en"] not in variants:
                variants.append(it["query_en"])
            if it["gap"] != first["gap"] and it["gap"] not in gap_variants:
                gap_variants.append(it["gap"])
            if it["acceptance_test"] != first["acceptance_test"] and it["acceptance_test"] not in acc_variants:
                acc_variants.append(it["acceptance_test"])
            for e in it.get("entities") or []:
                if e not in entities:
                    entities.append(e)
        priority = "must" if any(t[3]["priority"] == "must" for t in emits) else "should"
        exploratory = all(bool(t[4].get("exploratory")) for t in emits)
        hard_rule = any(bool(t[4].get("hard_rule_gate")) for t in emits)
        from_operative = any(bool(t[4].get("from_operative")) for t in emits)
        req = {
            "requirement_id": rid, "gap": first["gap"], "evidence_kind": first["evidence_kind"],
            "source_family": first["source_family"], "query_en": first["query_en"], "variants": variants,
            "gap_variants": gap_variants, "acceptance_test": first["acceptance_test"],
            "acceptance_test_variants": acc_variants, "entities": entities,
            "priority": priority, "priority_rule": PRIORITY_RULE,
            "requested_by": requested_by, "n_requested_by": len(requested_by), "n_members": len(order),
            "hard_rule_gate": hard_rule, "exploratory": exploratory, "from_operative": from_operative,
            "harness_state": harness_state_for(first["source_family"], first["evidence_kind"]),
        }
        if exploratory and priority == "must":
            req["priority"] = "should"
            req["priority_downgraded_from"] = "must"
            req["priority_downgrade_reason"] = EXPLORATORY_DOWNGRADE_REASON
        if entities:
            resolved, unresolved, detail, st = _resolve_entities(entities, resolver)
            req["entities_resolved"], req["entities_unresolved"], req["entities_resolution"] = resolved, unresolved, detail
            res_state = st if not res_state.startswith("errored") else res_state
        else:
            req["entities_resolved"], req["entities_unresolved"], req["entities_resolution"] = [], [], []
        reqs.append(req)
    reqs.sort(key=lambda r: (0 if r["priority"] == "must" else 1, -r["n_requested_by"], r["requirement_id"]))
    cap = int(cfg["max_requirements"])
    truncated_ids = [r["requirement_id"] for r in reqs[cap:]]
    kept = reqs[:cap]
    flags = []
    seen_flags = {}
    for i, a, f in sorted(flags_raw, key=lambda t: (FLAG_KINDS.index(t[2]["kind"]), t[2]["statement"], t[0])):
        key = (f["kind"], f["statement"].strip().lower())
        if key in seen_flags:
            if a not in seen_flags[key]["emitted_by"]:
                seen_flags[key]["emitted_by"].append(a)
            continue
        flag = {"kind": f["kind"], "statement": f["statement"], "gate": "human", "emitted_by": [a]}
        seen_flags[key] = flag
        flags.append(flag)
    n_valid = sum(1 for r in rows_sorted if r.get("status") in ("ok", "not-applicable"))
    agg = {
        "aggregation_version": MODULE_VERSION, "membership_version": MEMBERSHIP_VERSION, "council_version": COUNCIL_VERSION,
        "n_members": len(order), "n_valid": n_valid, "n_raw": len(raw_items), "n_dedup": len(reqs),
        "n_requirements": len(kept), "n_must": sum(1 for r in kept if r["priority"] == "must"),
        "n_should": sum(1 for r in kept if r["priority"] == "should"),
        "truncated": bool(truncated_ids), "n_truncated": len(truncated_ids), "truncated_ids": truncated_ids,
        "max_requirements": cap,
        "n_unsatisfiable": sum(1 for r in kept if r["harness_state"] != "satisfiable"),
        "n_hard_rule": sum(1 for r in kept if r["hard_rule_gate"]),
        "n_exploratory": sum(1 for r in kept if r["exploratory"]),
        "n_from_operative": sum(1 for r in kept if r["from_operative"]),
        "n_flags": len(flags),
        "requirements": kept, "flags": flags, "notes_for_human": notes, "not_applicable_members": not_applicable,
        "entities_resolution_state": res_state,
        "rules": {"requirement_id": REQUIREMENT_ID_RULE, "dedup": DEDUP_RULE, "priority": PRIORITY_RULE,
                  "order": ORDER_RULE, "harness_state": HARNESS_STATE_RULE},
        "catalog_sha": catalog_cards.CATALOG_SHA, "rules_sha": RULES_SHA, "tools_sha": TOOLS_SHA,
        "decided_by": "code (council.aggregate_r1)",
    }
    if isinstance(round_result, dict) and round_result.get("state"):
        agg["state"] = round_result["state"] if aggregate_state_in_vocabulary(round_result["state"]) else "incomplete"
    else:
        agg["state"] = "applicable"
    agg["aggregation_sha"] = _sha256(_canon({k: v for k, v in agg.items() if k not in ("aggregation_sha",)}))
    return agg


aggregate_requirements = aggregate_r1


# ── el ledger humano como CÓDIGO puro (F.1 — la ruta HTTP es de C6; la validación vive aquí) ─────────────────────
def _shas_of(images):
    """ADR-0086 (J.1): `images` como sha256 crudos o como ítems {sha256, …} — se normaliza a una lista de sha, en orden
    y sin repetir. Lo que la ruta pura guarda son IDENTIDADES, nunca bytes."""
    out = []
    for it in (images or []):
        sha = it.get("sha256") if isinstance(it, dict) else it
        if isinstance(sha, str) and sha and sha not in out:
            out.append(sha)
    return out


def apply_ledger_decisions(aggregation, decisions=None, approve=False, decided_by=None, decided_at=None,
                           knowledge_now=None, attestation_chars=None, ledger=None, images=None):
    """Aplica decisiones humanas {requirement_id, decision ∈ keep|discard|aporto, reason?, attested_text?} sobre los
    requisitos del agregado (o de un `ledger` previo) y devuelve el ledger (J): {state ∈ draft|approved, requirements[]
    (+decision, decision_reason?, attested_text? (íntegro), decided_by, decided_at), flags[], knowledge_now {text, class
    'attested', by, at, chars, truncated} | None, n_requirements, n_kept, n_discarded, n_attested, n_pending, n_hard_rule,
    errors {unknown_requirement_id[], discard_without_reason[], aporto_without_text[], hard_rule_requirements_undecided[]}}.
    Con `approve`: los `pending` no hard-rule pasan a keep con decided_by 'default-keep' (brief §3: "ningún requisito se
    descarta"); un hard-rule pendiente BLOQUEA la aprobación (§7.1: decisión humana EXPLÍCITA, sin default) y queda
    'gate-human-pending'. `decided_by` → 'human:<user_id>'.
    ADR-0086 (J.1, ADITIVO): `images` (sha256 de imágenes aportadas, adjuntas a `knowledge_now`) y `decisions[].images`
    (adjuntas a ESE requisito, SÓLO con decision 'aporto' — en keep o discard es `images_without_aporto`, un error, no un
    default). Aquí viajan IDENTIDADES: ningún byte, ninguna llave de almacén. Sin imágenes no nace ninguna llave (M.1)."""
    cap = int(attestation_chars or ENV_SPECS["WITT_COUNCIL_ATTESTATION_CHARS"]["default"])
    base_reqs = ledger_requirements(ledger) if ledger is not None else list((aggregation or {}).get("requirements") or [])
    reqs = []
    for r in base_reqs:
        q = dict(r)
        q.setdefault("decision", "pending")
        q.setdefault("decided_by", None)
        q.setdefault("decided_at", None)
        reqs.append(q)
    by_id = {r["requirement_id"]: r for r in reqs}
    errors = {"unknown_requirement_id": [], "discard_without_reason": [], "aporto_without_text": [],
              "hard_rule_requirements_undecided": []}
    who = f"human:{decided_by}" if decided_by else "human:unknown"
    for d in decisions or []:
        rid = d.get("requirement_id")
        req = by_id.get(rid)
        if req is None:
            errors["unknown_requirement_id"].append(rid)
            continue
        dec = d.get("decision")
        if dec not in ("keep", "discard", "aporto"):
            errors.setdefault("decision_off_vocabulary", []).append({"requirement_id": rid, "decision": dec})
            continue
        if dec == "discard" and not (isinstance(d.get("reason"), str) and d["reason"].strip()):
            errors["discard_without_reason"].append(rid)
            continue
        if dec == "aporto" and not (isinstance(d.get("attested_text"), str) and d["attested_text"].strip()):
            errors["aporto_without_text"].append(rid)
            continue
        req["decision"] = dec
        req["decided_by"] = who
        req["decided_at"] = decided_at
        if dec == "discard":
            req["decision_reason"] = d["reason"].strip()
        if dec == "aporto":
            txt = d["attested_text"].strip()
            req["attested_text"] = txt[:cap]
            req["attested_text_truncated"] = len(txt) > cap
            req["attested_class"] = "attested"
        # ADR-0086 (J.1/J.2): una imagen se cuelga de un requisito que la persona APORTA, no de uno que mantiene o descarta
        _imgs = _shas_of(d.get("images"))
        if _imgs and dec != "aporto":
            errors.setdefault("images_without_aporto", []).append(rid)
        elif _imgs:
            req["images"] = _imgs
            req["n_images"] = len(_imgs)
    if approve:
        hard_pending = [r["requirement_id"] for r in reqs if r["decision"] == "pending" and r.get("hard_rule_gate")]
        errors["hard_rule_requirements_undecided"] = hard_pending
        for r in reqs:
            if r["decision"] == "pending":
                if r.get("hard_rule_gate"):
                    r["decided_by"] = "gate-human-pending"
                else:
                    r["decision"], r["decided_by"], r["decided_at"] = "keep", "default-keep", decided_at
    has_errors = any(v for v in errors.values())
    kn = None
    if isinstance(knowledge_now, str) and knowledge_now.strip():
        t = knowledge_now.strip()
        kn = {"text": t[:cap], "class": "attested", "by": decided_by, "at": decided_at, "chars": len(t),
              "truncated": len(t) > cap}
    state = "approved" if (approve and not has_errors) else "draft"
    # ADR-0086 (J.4): el total y el detalle de las imágenes de ESTE ledger. Las llaves nacen sólo si hubo imágenes.
    _kn_imgs = _shas_of(images)
    _por_req = {r["requirement_id"]: list(r.get("images") or []) for r in reqs if r.get("images")}
    _n_imgs = len(_kn_imgs) + sum(len(v) for v in _por_req.values())
    _img_block = ({"images": _kn_imgs, "images_by_requirement": _por_req, "n_images": _n_imgs,
                   "images_rule": ATTESTED_IMAGES_LEDGER_RULE, "images_class": "attested"} if _n_imgs else {})
    return {
        "state": state, "ledger_version": MODULE_VERSION,
        "requirements": reqs, "flags": list((aggregation or {}).get("flags") or []) if ledger is None else list(ledger.get("flags") or []),
        "knowledge_now": kn,
        "n_requirements": len(reqs), "n_kept": sum(1 for r in reqs if r["decision"] == "keep"),
        "n_discarded": sum(1 for r in reqs if r["decision"] == "discard"),
        "n_attested": sum(1 for r in reqs if r["decision"] == "aporto"),
        "n_pending": sum(1 for r in reqs if r["decision"] == "pending"),
        "n_hard_rule": sum(1 for r in reqs if r.get("hard_rule_gate")),
        "truncated": bool((aggregation or {}).get("truncated")) if ledger is None else bool(ledger.get("truncated")),
        "n_truncated": int((aggregation or {}).get("n_truncated") or 0) if ledger is None else int(ledger.get("n_truncated") or 0),
        "approved_by": decided_by if state == "approved" else None,
        "approved_at": decided_at if state == "approved" else None,
        "errors": errors, "has_errors": has_errors,
        **_img_block,
        "rule": ("approve: pending non-hard-rule → keep (default-keep); hard_rule_gate pending → 400 "
                 "hard_rule_requirements_undecided (§7.1, no default); discard needs reason; aporto needs attested_text"),
    }


# ── (C.5) cobertura: cada miembro juzga SUS requisitos; ids alucinados ANULAN el voto; worst-of-N ─────────────────
_WORST = {"uncovered": 2, "partial": 1, "covered": 0}
COVERAGE_RULE = ("worst-of-N over VALID votes (uncovered > partial > covered); a vote citing an evidence_id not in the "
                 "bundle is ANNULLED (hallucinated_evidence_ids); covered|partial with zero evidence_ids is ANNULLED "
                 "(nothing is asserted without a cited id, §7); a vote on a requirement the member did not request or "
                 "that does not exist is FOREIGN (discarded, counted); no valid votes → not-judged; decision aporto → "
                 "covered-by-attestation; discard → discarded")
MUST_UNCOVERED_RULE = ("must_uncovered = kept must with coverage_final ∈ {uncovered, partial, not-judged} AND harness_state "
                       "satisfiable (conservative, ADR-0080 E pattern); must attested / discarded / unsatisfiable are "
                       "declared apart and do NOT gate (E1 default)")
COVERAGE_CLASS = "model-judgment aggregated by code (worst-of-N over valid votes; hallucinated evidence_id annuls the vote)"


def evidence_ids_of(bundle):
    """Los ids del bundle sobre los que se valida un voto — la MISMA regla que runs._evidence_ids (copiada aquí para no
    importar runs desde lib; C5 puede pasar la lista directamente)."""
    if isinstance(bundle, (list, tuple, set)):
        return list(bundle)
    ids = [h["doc_id"] for h in ((bundle.get("path_a") or {}).get("hits") or [])]
    for p in (bundle.get("path_b") or {}).get("papers", []) or []:
        if p.get("evidence_id"):
            ids.append(p["evidence_id"])
            continue
        rec = p.get("search_rec", {}) or {}
        ids.append(f"PMID:{rec['pmid']}" if rec.get("pmid") else (rec.get("pmcid") or rec.get("doi") or "paper"))
    return ids


def judge_coverage(round_result, ledger, evidence_ids, phase="pre-search", round_=None):
    """ADR-0082 (C.5) `aggregate_coverage`: las filas `ok` de r2/r3 (`output.judgments`) contra el ledger (requisitos con
    decision) y los ids del bundle (`runs._evidence_ids(bundle)` o el bundle). Devuelve coverage {state 'judged', phase,
    round, evidence_view, by_requirement[] {requirement_id, priority, decision, harness_state, coverage_final, votes[]
    {agent, coverage, evidence_ids[], annulled, annul_reason?, hallucinated_evidence_ids[], rationale,
    search_directive?}, n_votes, n_valid_votes, n_annulled_votes}, foreign_requirement_ids[], hallucinated_evidence_ids[],
    n_hallucinated_votes, n_annulled_votes, n_valid_votes, must_total, must_gateable, must_covered, must_uncovered
    (gate), must_uncovered_strict, must_partial, must_not_judged, must_attested, must_discarded, must_unsatisfiable,
    uncovered_must_ids[], n_requirements_kept, pertinence {evidence_id: [requirement_id]}, pertinent_source, rule, class}."""
    ids = set(evidence_ids_of(evidence_ids))
    reqs = ledger_requirements(ledger)
    by_id = {r["requirement_id"]: r for r in reqs}
    votes = {r["requirement_id"]: [] for r in reqs}
    foreign, halluc_all = [], []
    rows = round_result.get("members") if isinstance(round_result, dict) else list(round_result)
    round_ = round_ or (round_result.get("round") if isinstance(round_result, dict) else None)
    for row in rows:
        if row.get("status") != "ok":
            continue
        a = row["agent"]
        for j in (row.get("output") or {}).get("judgments") or []:
            rid = j["requirement_id"]
            req = by_id.get(rid)
            if req is None:
                foreign.append({"agent": a, "requirement_id": rid, "reason": "unknown-requirement"})
                continue
            if a not in (req.get("requested_by") or []):
                foreign.append({"agent": a, "requirement_id": rid, "reason": "not-requested-by-member"})
                continue
            if not is_kept(req):
                foreign.append({"agent": a, "requirement_id": rid, "reason": f"decision {req.get('decision')} (not kept)"})
                continue
            bad = [e for e in j.get("evidence_ids") or [] if e not in ids]
            vote = {"agent": a, "coverage": j["coverage"], "evidence_ids": list(j.get("evidence_ids") or []),
                    "annulled": False, "hallucinated_evidence_ids": bad, "rationale": j.get("rationale") or ""}
            if bad:
                vote["annulled"], vote["annul_reason"] = True, "hallucinated evidence_id (not in bundle)"
                halluc_all.append({"agent": a, "requirement_id": rid, "evidence_ids": bad})
            elif j["coverage"] in ("covered", "partial") and not vote["evidence_ids"]:
                vote["annulled"], vote["annul_reason"] = True, f"{j['coverage']} without any evidence_id"
            if j.get("search_directive"):
                vote["search_directive"] = j["search_directive"]
            votes[rid].append(vote)
    by_req = []
    pertinence = {}
    counts = {"must_total": 0, "must_gateable": 0, "must_covered": 0, "must_uncovered_strict": 0, "must_partial": 0,
              "must_not_judged": 0, "must_attested": 0, "must_discarded": 0, "must_unsatisfiable": 0}
    uncovered_ids = []
    n_valid_votes = n_annulled = 0
    for r in reqs:
        rid = r["requirement_id"]
        vs = votes[rid]
        valid = [v for v in vs if not v["annulled"]]
        n_valid_votes += len(valid)
        n_annulled += len(vs) - len(valid)
        dec = r.get("decision")
        if dec == "aporto":
            final = "covered-by-attestation"
        elif dec == "discard":
            final = "discarded"
        elif not valid:
            final = "not-judged"
        else:
            final = max(valid, key=lambda v: _WORST[v["coverage"]])["coverage"]
        for v in valid:
            if v["coverage"] in ("covered", "partial"):
                for e in v["evidence_ids"]:
                    lst = pertinence.setdefault(e, [])
                    if rid not in lst:
                        lst.append(rid)
        is_must = r.get("priority") == "must"
        if is_must:
            counts["must_total"] += 1
            if dec == "aporto":
                counts["must_attested"] += 1
            elif dec == "discard":
                counts["must_discarded"] += 1
            elif r.get("harness_state", "satisfiable") != "satisfiable":
                counts["must_unsatisfiable"] += 1
            else:
                counts["must_gateable"] += 1
                if final == "covered":
                    counts["must_covered"] += 1
                else:
                    uncovered_ids.append(rid)
                    if final == "uncovered":
                        counts["must_uncovered_strict"] += 1
                    elif final == "partial":
                        counts["must_partial"] += 1
                    else:
                        counts["must_not_judged"] += 1
        by_req.append({"requirement_id": rid, "priority": r.get("priority"), "decision": dec,
                       "harness_state": r.get("harness_state"), "coverage_final": final, "votes": vs,
                       "n_votes": len(vs), "n_valid_votes": len(valid), "n_annulled_votes": len(vs) - len(valid),
                       "requested_by": list(r.get("requested_by") or [])})
    must_uncovered = counts["must_uncovered_strict"] + counts["must_partial"] + counts["must_not_judged"]
    # ADR-0086 (F6): cuántos requisitos traen una imagen aportada detrás. Es un CONTEO, no una cobertura: la imagen no
    # cubre nada por sí sola — cubre la decisión humana `aporto`, que ya se cuenta en must_attested. Sin imágenes en el
    # ledger no nace ninguna llave (M.1).
    _img_reqs = [r for r in reqs if r.get("images")]
    _img_counts = ({"n_with_image": len(_img_reqs),
                    "n_attested_with_image": sum(1 for r in _img_reqs if r.get("decision") == "aporto"),
                    "must_attested_with_image": sum(1 for r in _img_reqs if r.get("priority") == "must"
                                                    and r.get("decision") == "aporto"),
                    "n_images_total": sum(len(r.get("images") or []) for r in _img_reqs),
                    "attested_images_rule": ATTESTED_IMAGES_COUNCIL_RULE} if _img_reqs else {})
    return {
        "state": "judged", "phase": phase, "round": round_,
        **_img_counts,
        "evidence_view": EVIDENCE_VIEW_STATE if phase == "pre-search" else "DI + path_b (after directed search)",
        "by_requirement": by_req,
        "foreign_requirement_ids": foreign, "n_foreign_votes": len(foreign),
        "hallucinated_evidence_ids": halluc_all, "n_hallucinated_votes": len(halluc_all),
        "n_annulled_votes": n_annulled, "n_valid_votes": n_valid_votes,
        "n_requirements": len(reqs), "n_requirements_kept": sum(1 for r in reqs if is_kept(r)),
        **counts, "must_uncovered": must_uncovered, "uncovered_must_ids": uncovered_ids,
        "pertinence": {k: pertinence[k] for k in sorted(pertinence)},
        "pertinent_source": f"council.{round_ or 'r2'} (covered|partial votes)",
        "rule": COVERAGE_RULE, "must_uncovered_rule": MUST_UNCOVERED_RULE, "class": COVERAGE_CLASS,
        "decided_by": "code (council.judge_coverage)",
    }


aggregate_coverage = judge_coverage


# ── (C.6) directivas: las compila CÓDIGO desde el requisito; el voto sólo REFINA ─────────────────────────────────
# corrector ADR-0084 (L): el literal de 1.12 BYTE A BYTE — viaja a frozen.council.directives_rule en TODA corrida con consejo; la
# ampliación de F.2 vive en DIRECTIVES_AVAILABILITY_RULE y se emite como `availability_rule` SÓLO cuando hubo un recomputo (así el
# kill-switch no cambia un literal compartido del registro)
DIRECTIVES_RULE = ("one directive per KEPT requirement with coverage_final ∈ {uncovered, partial, not-judged} and "
                   "harness_state satisfiable; family/query/entities come from the REQUIREMENT (never from optional prose); "
                   "a valid vote's search_directive only refines query_en/entities (refined_by_members); "
                   "dedup by (family, requirement_id); order must > should, requirement_id asc")
DIRECTIVES_AVAILABILITY_RULE = ("for families with dynamic availability (SEARCH_DISPATCH row 'availability': web) harness_state is "
                                "RECOMPUTED at compile time (harness_state_at_plan / harness_state_at_compile / "
                                "harness_state_recomputed when they differ — ADR-0084 F.2)")
HARNESS_STATE_RECOMPUTE_RULE = ("the harness_state stored in the round-1 ledger is what the PLAN saw; for families whose "
                                "availability is dynamic (web: WITT_WEB_LOCATOR / BRAVE_API_KEY read at call time) the "
                                "compiler asks search_harness.family_available again — a key that arrived compiles the web "
                                "directive without re-planning, a key that left excludes it; static families keep the stored "
                                "value byte for byte (ADR-0084 F.2)")


def _availability_is_dynamic(family):
    """True para las filas de SEARCH_DISPATCH con `availability` (web → web_locator.provider_state; ADR-0084 C.2)."""
    spec = search_harness.SEARCH_DISPATCH.get(family) or {}
    return bool(spec.get("availability"))


def directives_from(coverage, ledger, members_order=None, env=None):
    """ADR-0082 (C.6) `compile_directives` → {directives[] {requirement_id, family, query_en, query_en_original?,
    entities[], symbols[] (entities_resolved), evidence_kind, priority, requested_by[], refined_by_members[], state
    'compiled', harness_state_at_plan? / harness_state_at_compile? / harness_state_recomputed? (ADR-0084 F.2, sólo cuando
    el estado guardado en r1 y el recomputado difieren)}, excluded[] {requirement_id, family, state ∈ excluded-unknown-family |
    excluded-unsatisfiable, reason, + las mismas tres llaves cuando difieren}, n, n_excluded, families[], state ∈
    DIRECTIVES_STATES, rule, harness_state_recompute_rule}. Sin dependencia de `search_directive`. ADR-0084 (F.2): para las
    familias con disponibilidad DINÁMICA (web) el `harness_state` se RECOMPUTA aquí con `harness_state_for(…, env)` — el
    guardado en el ledger de la ronda 1 es lo que vio el PLAN; si la llave llegó (o se fue) entre el plan y la corrida, la
    directiva web se compila (o se excluye) sin re-planear. Las familias estáticas conservan el guardado byte a byte."""
    reqs = {r["requirement_id"]: r for r in ledger_requirements(ledger)}
    order = {a: i for i, a in enumerate(members_order or agent_matrix.council_members(full=True))}
    out, excluded, seen = [], [], set()
    any_recomputed = False   # corrector ADR-0084 (L): availability_rule sólo cuando un recomputo ocurrió
    for br in (coverage or {}).get("by_requirement") or []:
        rid = br["requirement_id"]
        req = reqs.get(rid)
        if req is None or not is_kept(req):
            continue
        if br.get("coverage_final") not in ("uncovered", "partial", "not-judged"):
            continue
        fam = req.get("source_family")
        key = (fam, rid)
        if key in seen:
            continue
        seen.add(key)
        if fam not in search_harness.SEARCH_DISPATCH:
            excluded.append({"requirement_id": rid, "family": fam, "state": "excluded-unknown-family",
                             "reason": f"family {fam!r} not in SEARCH_DISPATCH"})
            continue
        hs_stored = req.get("harness_state")
        recomputed = {}
        if hs_stored and _availability_is_dynamic(fam):
            # ADR-0084 (F.2): disponibilidad leída AHORA (plan bajo off → llave presente al correr compila la directiva web)
            hs_now = harness_state_for(fam, req.get("evidence_kind"), env)
            if hs_now != hs_stored:
                recomputed = {"harness_state_at_plan": hs_stored, "harness_state_at_compile": hs_now,
                              "harness_state_recomputed": True}
                any_recomputed = True
            hs = hs_now
        else:
            hs = hs_stored or harness_state_for(fam, req.get("evidence_kind"), env)
        if hs != "satisfiable":
            excluded.append({"requirement_id": rid, "family": fam, "state": "excluded-unsatisfiable", "reason": hs,
                             **recomputed})
            continue
        d = {"requirement_id": rid, "family": fam, "query_en": req.get("query_en"),
             "entities": list(req.get("entities") or []), "symbols": list(req.get("entities_resolved") or []),
             "evidence_kind": req.get("evidence_kind"), "priority": req.get("priority"),
             "requested_by": list(req.get("requested_by") or []), "refined_by_members": [], "state": "compiled",
             **recomputed}
        refiners = sorted([v for v in br.get("votes") or [] if not v.get("annulled") and v.get("search_directive")],
                          key=lambda v: order.get(v["agent"], 10_000))
        if refiners:
            sd = refiners[0]["search_directive"]
            if sd.get("query_en"):
                d["query_en_original"] = d["query_en"]
                d["query_en"] = sd["query_en"]
            for v in refiners:
                d["refined_by_members"].append(v["agent"])
                for e in (v["search_directive"].get("entities") or []):
                    if e not in d["entities"]:
                        d["entities"].append(e)
        out.append(d)
    out.sort(key=lambda d: (0 if d["priority"] == "must" else 1, d["requirement_id"]))
    fams = []
    for d in out:
        if d["family"] not in fams:
            fams.append(d["family"])
    res = {"directives": out, "excluded": excluded, "n": len(out), "n_excluded": len(excluded), "families": fams,
           "state": "provided" if out else "none (all must covered)", "rule": DIRECTIVES_RULE,
           "harness_state_recompute_rule": HARNESS_STATE_RECOMPUTE_RULE,
           "decided_by": "code (council.directives_from)"}
    if any_recomputed:
        res["availability_rule"] = DIRECTIVES_AVAILABILITY_RULE   # corrector ADR-0084 (L): sólo cuando un recomputo ocurrió
    return res


compile_directives = directives_from


# ── (C.7) re-cobertura ESTRUCTURAL tras la búsqueda (código; corre SIEMPRE) ──────────────────────────────────────
# corrector ADR-0084 (L): el literal de 1.12 BYTE A BYTE — viaja a frozen.council.coverage.after_search.rule en toda corrida con
# cobertura; la ampliación web (F.4) vive en WEB_LOCATOR_COVERAGE_RULE y se emite como `web_locator_rule` SÓLO con ledger web
AFTER_SEARCH_RULE = ("retrieved-for = at least one item ADMITTED by the harness carries this requirement_id in "
                     "directive_requirement_ids (structural MEASUREMENT, not a judgment); still-uncovered = a directive "
                     "was compiled but nothing admitted for it; not-searched = no directive (unsatisfiable, discarded or "
                     "no search); covered-pre = coverage_final ∈ {covered, covered-by-attestation} before the search")
WEB_LOCATOR_COVERAGE_KEYS = ("n_queries", "n_results", "n_located", "n_materialized", "n_unresolved")
WEB_LOCATOR_COVERAGE_RULE = ("web requirements (family web) additionally carry web_locator {n_queries, n_results, n_located, "
                             "n_materialized, n_unresolved} measured from the web locator ledger — web-located candidates only exist "
                             "materialized by Europe PMC, so retrieved-for via the web = exists in Europe PMC (ADR-0084 F.4); "
                             "per web requirement_id over the web locator ledger (queries[].requirement_ids, "
                             "located[].requirement_ids, unresolved[].requirement_ids): n_queries = queries naming it; "
                             "n_results = sum of their integer n_results (None = not measured, not counted); n_located = "
                             "located naming it; n_materialized = those with feed_state 'materialized-same-round'; "
                             "n_unresolved = unresolved naming it; URLs never leave the ledger (ADR-0084 F.4)")
_WEB_MATERIALIZED_FEED_STATE = "materialized-same-round"   # == web_locator.FEED_STATES_EXACT[0] (atado en smoke_council)


def _web_locator_ledger(search_ledger, web_locator):
    """(ledger web {queries[], located[], unresolved[]} | None, fuente): el bloque agregado que pasa el llamador
    (`web_locator=` — runs pasa block['web_locator'] de answer_pipeline D.4), si no `search_ledger.web_locator`, si no la
    unión de las filas de familia web en `search_ledger.rounds[].sources[].web_locator` (ledger íntegro del harness).
    Sin ninguna → (None, None). Sólo lectura: jamás muta el ledger."""
    # corrector ADR-0084 (L): un bloque D.4 con las TRES listas VACÍAS (runs lo pasa SIEMPRE que hubo harness, también sin directiva web)
    # NO es un ledger web — sin datos web la forma de coverage_after_search es la de 1.12 byte a byte (ni web_locator_source ni _rule)
    if isinstance(web_locator, dict) and any(isinstance(web_locator.get(k), list) and web_locator.get(k)
                                             for k in ("queries", "located", "unresolved")):
        return web_locator, "caller (web_locator=)"
    if isinstance(search_ledger, dict):
        wl = search_ledger.get("web_locator")
        if isinstance(wl, dict) and any(isinstance(wl.get(k), list) and wl.get(k) for k in ("queries", "located", "unresolved")):
            return wl, "search_ledger.web_locator"
        merged = {"queries": [], "located": [], "unresolved": []}
        found = False
        for rnd in search_ledger.get("rounds") or []:
            if not isinstance(rnd, dict):
                continue
            for row in rnd.get("sources") or []:
                if not isinstance(row, dict) or row.get("family") != "web" or not isinstance(row.get("web_locator"), dict):
                    continue
                found = True
                for k in merged:
                    merged[k] += [x for x in (row["web_locator"].get(k) or []) if isinstance(x, dict)]
        if found:
            return merged, "search_ledger.rounds[].sources[web].web_locator"
    return None, None


def _web_locator_by_requirement(wl):
    """{requirement_id: {n_queries, n_results, n_located, n_materialized, n_unresolved}} — conteos ENTEROS por requisito
    (MEDICIÓN estructural sobre el ledger del localizador; ADR-0084 F.4). Ninguna URL ni título viaja."""
    per = {}

    def slot(rid):
        return per.setdefault(rid, {k: 0 for k in WEB_LOCATOR_COVERAGE_KEYS})

    for q in wl.get("queries") or []:
        for rid in q.get("requirement_ids") or []:
            s = slot(rid)
            s["n_queries"] += 1
            if isinstance(q.get("n_results"), int) and not isinstance(q.get("n_results"), bool):
                s["n_results"] += q["n_results"]
    for loc in wl.get("located") or []:
        for rid in loc.get("requirement_ids") or []:
            s = slot(rid)
            s["n_located"] += 1
            if loc.get("feed_state") == _WEB_MATERIALIZED_FEED_STATE:
                s["n_materialized"] += 1
    for u in wl.get("unresolved") or []:
        for rid in u.get("requirement_ids") or []:
            slot(rid)["n_unresolved"] += 1
    return per


def _ledger_items(search_ledger):
    """Los ítems admitidos que el harness dejó: search_ledger.items[] ∪ rounds[].items[] (forma de search_harness.run_round;
    C3 añade directive_requirement_ids[] a cada ítem/fila)."""
    items = []
    if not isinstance(search_ledger, dict):
        return items
    items += [i for i in (search_ledger.get("items") or []) if isinstance(i, dict)]
    for rnd in search_ledger.get("rounds") or []:
        if isinstance(rnd, dict):
            items += [i for i in (rnd.get("items") or []) if isinstance(i, dict)]
    return items


def coverage_after_search(coverage_pre, search_ledger, directives=None, web_locator=None):
    """ADR-0082 (C.7): {state ∈ 'measured' | 'not-run (no search ledger)', by_requirement[] {requirement_id, state ∈
    AFTER_SEARCH_STATES, n_items_retrieved, families[], web_locator? {n_queries, n_results, n_located, n_materialized,
    n_unresolved}}, n_retrieved_for, n_still_uncovered, n_not_searched, n_covered_pre, n_items_for_directives {rid: n},
    rule, web_locator_source? , web_locator_rule?}. ADR-0084 (F.4): `web_locator` viaja SÓLO en los requisitos de familia web
    (directiva web compilada o consulta del localizador que los nombra) — ausente en los demás; las llaves de nivel superior
    `web_locator_source`/`web_locator_rule` sólo cuando hubo ledger web (sin web la salida es byte-idéntica a 1.12).
    `web_locator=` es el bloque agregado de answer_pipeline (block['web_locator']: queries[], located[], unresolved[]) —
    runs lo pasa porque el ledger que entrega aquí es {plan, items} sin rondas; si falta se lee del propio ledger."""
    items = _ledger_items(search_ledger)
    plan_dirs = directives
    if plan_dirs is None and isinstance(search_ledger, dict):
        plan_dirs = ((search_ledger.get("plan") or {}).get("directives")) or []
    directed = {d.get("requirement_id") for d in (plan_dirs or []) if isinstance(d, dict)}
    web_rids = {d.get("requirement_id") for d in (plan_dirs or []) if isinstance(d, dict) and d.get("family") == "web"}
    wl, wl_source = _web_locator_ledger(search_ledger, web_locator)
    web_per = _web_locator_by_requirement(wl) if wl is not None else {}
    web_rids |= set(web_per)
    per_req = {}
    for it in items:
        for rid in it.get("directive_requirement_ids") or []:
            slot = per_req.setdefault(rid, {"n": 0, "families": []})
            slot["n"] += 1
            fam = it.get("source_family") or it.get("family")
            if fam and fam not in slot["families"]:
                slot["families"].append(fam)
    by_req = []
    for br in (coverage_pre or {}).get("by_requirement") or []:
        rid = br["requirement_id"]
        if br.get("coverage_final") in ("covered", "covered-by-attestation"):
            st = "covered-pre"
        elif rid in per_req:
            st = "retrieved-for"
        elif rid in directed:
            st = "still-uncovered"
        else:
            st = "not-searched"
        row = {"requirement_id": rid, "priority": br.get("priority"), "state": st,
               "n_items_retrieved": per_req.get(rid, {}).get("n", 0),
               "families": per_req.get(rid, {}).get("families", [])}
        if rid in web_rids and wl is not None:
            # ADR-0084 (F.4): qué requisitos web quedaron materializados — conteos, jamás URLs; sólo en requisitos web
            row["web_locator"] = dict(web_per.get(rid) or {k: 0 for k in WEB_LOCATOR_COVERAGE_KEYS})
        by_req.append(row)
    out = {"state": "measured" if isinstance(search_ledger, dict) else "not-run (no search ledger)",
           "by_requirement": by_req,
           "n_retrieved_for": sum(1 for b in by_req if b["state"] == "retrieved-for"),
           "n_still_uncovered": sum(1 for b in by_req if b["state"] == "still-uncovered"),
           "n_not_searched": sum(1 for b in by_req if b["state"] == "not-searched"),
           "n_covered_pre": sum(1 for b in by_req if b["state"] == "covered-pre"),
           "n_items_for_directives": {rid: per_req[rid]["n"] for rid in sorted(per_req)},
           "rule": AFTER_SEARCH_RULE, "decided_by": "code (council.coverage_after_search)"}
    if wl is not None:
        out["web_locator_source"] = wl_source
        out["web_locator_rule"] = WEB_LOCATOR_COVERAGE_RULE
    return out


def recoverage_members(coverage_pre, ledger):
    """Los DUEÑOS de los must kept sin cubrir (subconjunto para r3, C.7): requested_by de uncovered_must_ids, en orden de
    membresía (full: los operativos sólo aparecen si pidieron algo)."""
    reqs = {r["requirement_id"]: r for r in ledger_requirements(ledger)}
    owners = set()
    for rid in (coverage_pre or {}).get("uncovered_must_ids") or []:
        owners |= set((reqs.get(rid) or {}).get("requested_by") or [])
    return [a for a in agent_matrix.council_members(full=True) if a in owners]


# ── (G.9) resumen para el hilo (thread_context.council_summary) ──────────────────────────────────────────────────
def summary_for_thread(council, cap=24):
    """`thread_context.council_summary` del turno siguiente desde `frozen.council` del padre: {requirements[]
    {requirement_id, gap ≤200, priority, coverage_final, decision, n_requested_by}, flags[] {kind, statement}, knowledge_now_present,
    must_uncovered_post: int|null, truncated, n_total, source} | None (padre sin consejo o sin ledger). Lo reciben el
    PLANNER (runs.plan_thread_context) y la RONDA 1 del turno N+1 (council_jobs._inherited_criteria); el SINTETIZADOR del
    hijo NO (E5 — runs.execute_run se lo quita de SU copia del snapshot; corrector ADR-0082 G.9): `gap` (≤200) y
    `flags[].statement` son texto escrito por los miembros, y un sintetizador que los lee es el ADR con held-out (K.i)."""
    if not isinstance(council, dict) or not isinstance(council.get("ledger"), dict):
        return None
    ledger = council["ledger"]
    cov = council.get("coverage") if isinstance(council.get("coverage"), dict) else {}
    post = cov.get("post_search") if isinstance(cov.get("post_search"), dict) else {}
    pre = cov.get("pre_search") if isinstance(cov.get("pre_search"), dict) else {}
    src_cov = post if post.get("state") == "judged" else (pre if pre.get("state") == "judged" else {})
    final_by = {b["requirement_id"]: b.get("coverage_final") for b in src_cov.get("by_requirement") or []}
    reqs = ledger_requirements(ledger)
    out = []
    for r in reqs[:cap]:
        out.append({"requirement_id": r.get("requirement_id"), "gap": (r.get("gap") or "")[:200],
                    "priority": r.get("priority"), "coverage_final": final_by.get(r.get("requirement_id")),
                    "decision": r.get("decision"), "n_requested_by": r.get("n_requested_by")})
    kn = ledger.get("knowledge_now")
    # ADR-0086 (F6): el turno siguiente hereda CUÁNTAS imágenes aportó una persona, no lo que dicen. El caption es texto
    # de una persona y el planner no lo necesita para planear; `thread_context.parent_attested_images` (runs) sí lo lleva,
    # recortado, para quien de veras lo usa. Sin imágenes no nace la llave (M.1).
    _n_img = int(ledger.get("n_images") or 0) or sum(len(r.get("images") or []) for r in reqs)
    _img_block = ({"n_attested_images": _n_img,
                   "n_requirements_with_image": sum(1 for r in reqs if r.get("images")),
                   "attested_images_rule": ATTESTED_IMAGES_COUNCIL_RULE} if _n_img else {})
    return {"requirements": out, **_img_block,
            "flags": [{"kind": f.get("kind"), "statement": f.get("statement")} for f in (ledger.get("flags") or [])],
            "knowledge_now_present": bool(kn and (kn.get("present") if isinstance(kn, dict) and "present" in kn
                                                  else (kn.get("text") if isinstance(kn, dict) else kn))),
            "must_uncovered_post": post.get("must_uncovered") if post.get("state") == "judged" else None,
            "coverage_source": ("post_search" if post.get("state") == "judged" else
                                ("pre_search" if pre.get("state") == "judged" else "none")),
            "truncated": len(reqs) > cap, "n_total": len(reqs), "cap": cap,
            "source": "frozen.council of the parent run (council.summary_for_thread; prose does not travel)"}


__all__ = [
    "MODULE_VERSION", "COUNCIL_VERSION", "MEMBERSHIP_VERSION",
    "COUNCIL_FIXED_BLOCK", "COUNCIL_RULES", "COUNCIL_RULES_ITEMS", "RULES_SHA", "SHARED_BLOCK_TEXT", "SHARED_BLOCK_SHA",
    "PROHIBITED_OUTPUT_FIELDS", "MIN_CACHEABLE_TOKENS", "build_system", "system_sha", "cache_config",
    "ROUNDS", "ROUND_KINDS", "ROUND_KIND_OF", "ROUND_PHASES", "PRIORITIES", "COVERAGE_VOTES", "COVERAGE_STATES",
    "MEMBER_STATES", "AGGREGATE_STATES_EXACT", "AGGREGATE_STATE_PREFIXES", "COUNCIL_STATES_EXACT",
    "COUNCIL_STATE_PREFIXES", "DECISION_STATES", "DECIDED_BY_PREFIXES", "LEDGER_STATES", "DIRECTIVE_STATES",
    "DIRECTIVES_STATES", "AFTER_SEARCH_STATES", "POST_SEARCH_STATES_EXACT", "HARNESS_STATES_EXACT",
    "HARNESS_STATE_PREFIXES", "FLAG_KINDS", "MEMBER_ERROR_KINDS_EXTRA", "COUNCIL_EVIDENCE_KINDS",
    "COUNCIL_SOURCE_FAMILIES", "council_state_in_vocabulary", "aggregate_state_in_vocabulary",
    "harness_state_in_vocabulary", "council_vocabulary",
    "REQ_TOOL", "FLAGS_TOOL", "COV_TOOL", "TOOLS", "TOOL_BY_NAME", "TOOLS_SHA", "REQ_TOOL_NAME", "FLAGS_TOOL_NAME",
    "COV_TOOL_NAME", "tools_static_check", "round_kind", "tool_for",
    "USAGE_STAGE_STATES_EXACT", "USAGE_STAGE_STATE_PREFIXES", "socket_timeout_s", "SOCKET_TIMEOUT_RULE", "TRANSPORT_BACKOFF_S",
    "ENV_SPECS", "env_config", "enabled", "config", "quorum_required", "resolve_council_model", "HEARTBEAT_S",
    "HEARTBEAT_RULE", "COUNCIL_MAX_TOKENS_DEFAULT", "EVIDENCE_VIEW_STATE",
    "payload_r1", "payload_r2", "payload_for_round", "is_kept", "ledger_requirements", "requirements_for_member",
    "build_request", "default_caller", "validate_tool_input",
    "RoundCancelled", "run_round", "abandoned_cost_upper",
    "requirement_tokens", "requirement_id", "harness_state_for", "aggregate_r1", "aggregate_requirements",
    "apply_ledger_decisions", "evidence_ids_of", "judge_coverage", "aggregate_coverage", "directives_from",
    "compile_directives", "coverage_after_search", "recoverage_members", "summary_for_thread",
    "HARNESS_STATE_RULE", "HARNESS_STATE_RECOMPUTE_RULE", "WEB_LOCATOR_COVERAGE_KEYS", "WEB_LOCATOR_COVERAGE_RULE",
]

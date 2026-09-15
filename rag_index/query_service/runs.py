"""
runs.py — run model + execution worker for the webapp backend (block 3, ADR-0050).

A run is the unit the webapp submits: question -> retrieve (answer_pipeline, ONE state machine — never
re-assembled) -> synthesize (Claude, best-tier policy) -> deterministic anti-fabrication gate
(verify_output) -> composite-audit panel (ADR-0049, 100% of runs) -> terminal AUDIT_APPROVED|REJECTED
-> frozen record persisted in the backend DB (ADR-0047 decision 2: the webapp only reads).

Events: every stage appends to run_events (db.add_event) — the ONE log the live SSE trace and the
replay both read. The heartbeat is last_event_at: a run with no event for N minutes is distinguishable
from a working one (the 1800s sklearn-deadlock lesson). Cancellation is a flag checked at stage
boundaries — a cancelled run is CANCELLED, never disguised as failed.

ZERO DATA INAMOVIBLE mutation: runs read the DI and write only to the backend DB (runs/run_events) +
the gitignored mcp_cache. Approved external evidence still re-enters the DI ONLY via the human-gated
ingest path.

Spend per run (authorized, measured, never capped — ADR-0047 d.3): 1 query embed (path_a) + 1 synthesis
(opus) + the 4-reviewer panel (~1-2.50 USD). Usage is accumulated into the frozen record.
"""
import hashlib
import inspect
import json
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import competence  # noqa: E402  — ADR-0080: la compuerta de competencia (código puro; runs.py sólo la cablea)
import config_ledger  # noqa: E402  — ADR-0081 (E/I): bitácora de configuración en corrida (S5; import en DURO desde S7)
import db  # noqa: E402
import niche_catalog  # noqa: E402
import precedent  # noqa: E402  — ADR-0079: la serie de letras del precedente la produce precedent.py, no runs.py
from lib import (agent_matrix, answer_pipeline, composite_auditor, models, reasoning_catalog,  # noqa: E402
                 resolve_id, verify_output)
try:
    # ADR-0080 (C), rebanada C2: el harness de búsqueda. Import TOLERANTE — si la rebanada aún no aterrizó,
    # runs.py declara `search_ledger.state 'harness-unavailable'` y la Ruta B corre por el camino de hoy.
    from lib import search_harness  # noqa: E402
except ImportError:   # pragma: no cover — depende del árbol
    search_harness = None

RENDER_CONTRACT_VERSION = "1.10"  # ADR-0081 (política best-tier v2 / generación g2-2026-09): +models (procedencia
                                  # MEDIDA del modelo que corrió — roles resueltos con fuente, ran {requested,
                                  # reported, relation, thinking_state}, panel_signature; models.provenance_block) +
                                  # answer.{model_source, model_reported, relation} + audit/audit_initial.
                                  # {families_valid, n_families_valid, lenses_valid, n_lenses_valid, quorum,
                                  # panel_incomplete_reasons} (composite_auditor D) + revision.skipped_reason literal
                                  # 'panel_incomplete (<failed>) — …' + token_usage.by_stage.panel.by_model +
                                  # by_stage.<synth|elicit|plan|revision>.model_source + plan.judgment.planner.
                                  # {model_source, model_reported, relation} + plan.audit.panel_resolved[] +
                                  # epistemic_summary.{model_generation, panel_n_families_valid}. Eventos: stage.models
                                  # (NUEVO, primer evento de etapa tras run.state{running}), run.state{queued}.{run_no,
                                  # thread.root_run_no}, stage.synthesize.start{model, model_source, generation},
                                  # stage.audit.judge{family, api, api_source, reviewer_source}, stage.audit.verdict
                                  # {families_valid, n_families_valid, lenses_valid, n_lenses_valid, panel_incomplete,
                                  # panel_incomplete_reasons}. TODO aditivo; kill-switch WITT_MODEL_GENERATION=g1-2026-08
                                  # (+ WITT_OPENAI_API=chat-completions, WITT_PANEL_MIN_*=0) = valores de f57a3d3.
                                  # 1.9 = ADR-0080 (compuerta de competencia + lazo de búsqueda): +competence (bloque
                                  # de competence.evaluate: competent|null, components, decided_by 'code') +
                                  # search_ledger {plan, rounds[], families_default, n_rounds, cap, state} +
                                  # citations[].support_state (aditivo por cita) + citations_support_summary +
                                  # deterministic_checks.{pass1_admissible, positive_claim_requires_citations,
                                  # competence_gate} + fallback.trigger ∈ {structural, competence, null} (el
                                  # literal viejo 'confidence' vive en fb_meta.trigger_legacy) + fb_meta.competence
                                  # + token_usage.by_stage + epistemic_summary.{competent, n_search_rounds}.
                                  # 1.8 = ADR-0079 (investigación = turnos encadenados sobre una raíz): +thread
                                  # {thread_id, parent_run_id, turn_no, turn_kind, parent_state, parent_run_no,
                                  # root_question_id, root_run_no, context_delivery} + thread_context (el snapshot del turno
                                  # anterior que el modelo VIO; null con thread_context_skipped_reason) +
                                  # thread_parent_matches_run + precedent_citations (serie de LETRAS 'l',
                                  # admissible_as_evidence False — jamás en `citations`) + origin {value,
                                  # source} + episode_axes {world, inference, technical, provenance} +
                                  # deterministic_checks.{thread, parent_identifier_leak, disjoint_series};
                                  # epistemic_summary +thread_id/turn_no/origin. `citations` NO cambia de forma.
                                  # Corrector ADR-0079 (mismo 1.8, aún sin desplegar): +precedent_citations_state
                                  # (la letra sólo con padre 'closed') + origin.source COPIADA del sobre de
                                  # encolado (+source_at_execution) + plan_parent_matches_run /
                                  # plan_snapshot_matches_run (+_state) + parent_identifier_leak_state 'no-snapshot'
                                  # + disjoint_series_state 'parent-not-precedent'.
                                  # 1.7 = ADR-0078 (higiene de Ruta A y B): +citations_schema {source, n_raw,
                                  # n_valid, raw_len_chars?, raw_type?, note?} + evidence_cited_raw +
                                  # token_usage.{missing_price_models, cost_projection_complete} (+ la
                                  # vista de corrida gana claimed_by/claimed_at/failure_reason). El bump
                                  # va con el tipado opcional (`?`) en witt-webapp/src/api/types.ts —
                                  # ESO es la paridad front↔back, no dejar la versión congelada.
                                  # 1.6 = ADR-0067 (ciclo de revisión acotado, adopción VB): +revision
                                  # {enabled, performed, cap=1, findings_used, initial/final_verdict} +
                                  # audit_initial + answer_initial cuando hubo revisión (AMBAS versiones
                                  # persisten — nada se borra) + confidence.revision/revision_source.
                                  # 1.5 = ADR-0065 (escalar atrapado): confidence.source gana el literal
                                  # "stated-second-elicitation" (la elicitación dedicada es la medición
                                  # autoritativa del escalar) + confidence.pass1_inline/pass2_inline
                                  # (el instrumento in-line persiste — continuidad de la serie).
                                  # 1.4 = ADR-0061 (tapón 3): +plan (el plan declarado o null-declarado) y
                                  # agents_invoked poblado desde el juicio del planner cuando existe.
                                  # 1.3 = ADR-0060 (tapón 2): +reasoning {framework_applied (SELF-REPORT, con
                                  # sección y tier resueltos por tabla), structural_frameworks (derivados
                                  # del código)}, +agents_invoked (derivado, §11), +alternatives_considered.
                                  # 1.2 = ADR-0057 (confidence.source + path_b.query_sent). 1.1 = ADR-0051.
# ADR-0081 (A): los literales de modelo viven SOLO en analysis/scripts/lib/models.py. SYNTH_MODEL se CONSERVA como alias
# DERIVADO en import (evaluation/scripts/ab_trapped_scalar.py lo lee); el pipeline resuelve cada rol EN LA LLAMADA
# (models.resolve_role: tabla + env WITT_MODEL_SYNTH/_PLANNER/_ELICIT + WITT_MODEL_GENERATION, con fuente declarada).
# best-tier policy (2026-06-13 directive) — never downgraded to save cost.
SYNTH_MODEL = models.resolve_role("synthesizer")["model"]
ANTHROPIC_EFFORT_ENV = "WITT_ANTHROPIC_EFFORT"                 # (C.4) output_config.effort — sólo a modelos adaptativos
ANTHROPIC_EFFORT_ELICIT_ENV = "WITT_ANTHROPIC_EFFORT_ELICIT"   # override para CONF_TOOL (vacío = hereda)
# Llaves del payload de stage.models (snapshot REDUCIDO — ADR-0081 B): la Traza dice qué va a correr ANTES de gastar.
STAGE_MODELS_PAYLOAD_KEYS = ("generation", "generation_source", "table_version", "panel_signature", "roles", "panel",
                             "warnings", "unknown_models")
# Llaves que audit_initial COPIA del veredicto inicial: las de ADR-0067 + las del cuórum (ADR-0081 D) cuando audit() las trae.
AUDIT_INITIAL_KEYS = ("panel", "tally", "verdict", "n_valid", "source_vocabulary")
AUDIT_INITIAL_QUORUM_KEYS = ("families_valid", "n_families_valid", "lenses_valid", "n_lenses_valid", "quorum",
                             "panel_incomplete", "panel_incomplete_reasons")


def _max_tokens_for(role, role_name):
    """El TOPE (no gasto) del rol en la generación efectiva (ADR-0081 C.4): RoleResolved.max_tokens; para un id de
    familia desconocida (max_tokens null en la tabla) se toma el tope del rol en la generación — jamás un literal."""
    if role.get("max_tokens") is not None:
        return role["max_tokens"]
    key = role_name if role_name in models.PIPELINE_ROLES else "judge-anthropic"
    return models.GENERATIONS[role["generation"]]["max_tokens"][key]


def _effort_for(model, elicit=False):
    """(effort | None, fuente) — WITT_ANTHROPIC_EFFORT (y WITT_ANTHROPIC_EFFORT_ELICIT como override de CONF_TOOL) se
    envía como output_config.effort SÓLO a modelos con thinking_default 'adaptive' en la tabla (ADR-0081 C.4): en g1
    (opus-4-8, 'off') o con un id desconocido para la tabla NO se envía y la fuente lo declara. Vacío → None = no se
    envía (default de la API, `high`)."""
    val, src = models.env_value(ANTHROPIC_EFFORT_ENV)
    if elicit:
        v2, s2 = models.env_value(ANTHROPIC_EFFORT_ELICIT_ENV)
        if v2 is not None:
            val, src = v2, s2
        elif val is not None:
            src = f"{src} (heredado: {ANTHROPIC_EFFORT_ELICIT_ENV} vacío)"
    if val is None:
        return None, src
    row = models.MODELS.get(model)
    if row is None:
        return None, f"not-sent (unknown-to-table; {src}={val})"
    if row["thinking_default"] != "adaptive":
        return None, f"not-sent (thinking_default {row['thinking_default']}; {src}={val})"
    return val, src


def _anthropic_call(model, system, user_text, tool, max_tokens, effort=None):
    """(tool_input, usage, meta) — UNA sede para las llamadas Anthropic del pipeline (ADR-0081 B): pide a
    composite_auditor._anthropic_tool_call `return_meta=True` (meta = {model_reported, api, stop_reason, …}) y `effort=`
    SÓLO si la firma del caller los acepta (inspección determinista, patrón _call_with_optional — un caller/fake anterior
    a (C) sigue válido) y tolera la 2-tupla (meta {} → model_reported None → relation 'not-reported'). Nada se copia de
    una constante al lugar de lo que la API dijo.
    Corrector ADR-0081 (A): un id de familia DESCONOCIDA (sin prefijo que case, p. ej. WITT_MODEL_SYNTH=llama-9) NO se manda
    a la Messages API "por default": se lanza CallerError('unknown-family') ANTES de construir la petición — la misma regla
    que composite_auditor._default_caller aplica a los asientos del panel (cero llamadas; la corrida queda failed con error
    tipado, sin gasto)."""
    if models.family_of(model)[0] == models.FAMILY_UNKNOWN:
        raise composite_auditor.CallerError(
            "unknown-family",
            f"unknown-family: {model!r} en rol del pipeline — la tabla no lo conoce y el prefijo no casa; no se llama a "
            f"Anthropic (ADR-0081 A, corrector)")
    fn = composite_auditor._anthropic_tool_call
    try:
        params = inspect.signature(fn).parameters
        varkw = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
    except (TypeError, ValueError):
        params, varkw = {}, False
    kwargs = {"tool": tool, "max_tokens": max_tokens}
    if effort is not None and ("effort" in params or varkw):
        kwargs["effort"] = effort
    if "return_meta" in params or varkw:
        kwargs["return_meta"] = True
    res = fn(model, system, user_text, **kwargs)
    if isinstance(res, tuple) and len(res) >= 3:
        out, usage, meta = res[0], res[1], res[2]
    else:
        out, usage = res
        meta = {}
    meta = dict(meta) if isinstance(meta, dict) else {}
    # `effort_delivered`: False cuando se pidió effort pero el caller del árbol no lo acepta (declarado, no silencioso)
    meta["effort_delivered"] = ("effort" in kwargs) if effort is not None else None
    return out, usage, meta

# tau (ADR-0051): pass-1 confidence below this triggers the Path B fallback — the model's own "is my
# store enough?" signal, the decider the eval harness recommends (run_held_out --conf-threshold 0.5)
# over the structural check the repo documents as fooled-by-any-chunk-present (run #1 confirmed it live).
# corrector ADR-0080: lector TOLERANTE (una env presente y vacía en el compose tumbaba el import con ValueError);
# la misma función que competence.env_config usa, así ambos lectores de WITT_FALLBACK_CONF_TAU coinciden.
FALLBACK_CONF_TAU, FALLBACK_CONF_TAU_SOURCE = competence._env_float_tolerante(
    os.environ, competence.TAU_ENV, competence.TAU_DEFAULT)

SYNTH_TOOL = {
    "name": "emit_answer",
    "description": ("Answer the biology question using ONLY the provided evidence. If the evidence is "
                    "thin, say so in gap_flags and keep confidence honest. NEVER invent identifiers: "
                    "only assert gene IDs that appear in the evidence or the verified-store resolutions. "
                    # ADR-0079 — instrucción anti-fuga: el turno anterior es precedente, no evidencia
                    "The previous turn (thread_context), when present, is PRIOR ART, not evidence; never "
                    "cite or reuse an identifier from it unless it appears in evidence."),
    "input_schema": {
        "type": "object",
        "properties": {
            "direct_answer": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "confidence_by_subclaim": {
                "type": "object", "additionalProperties": {"type": "number"},
                "description": ("REQUIRED when the answer composes sub-claims of asymmetric evidence "
                                "strength (CLAUDE.md §5): map each sub-claim (short label) to its own "
                                "confidence instead of averaging them into one number.")},
            "absence_kind": {
                "type": "string",
                "enum": ["not-applicable", "no-evidence-retrieved", "evidence-of-no-effect"],
                "description": ("When the answer rests on an ABSENCE: 'no-evidence-retrieved' (the store "
                                "returned nothing on-topic — says nothing about the world) vs "
                                "'evidence-of-no-effect' (retrieved evidence actively supports a null "
                                "effect). These are OPPOSITE epistemic states; never conflate them. "
                                "'not-applicable' when the answer asserts positive evidence.")},
            "search_query_en": {
                "type": "string",
                "description": ("ENGLISH keyword query for external literature search (gene symbols + "
                                "concise English domain terms, e.g. 'osr1 pax2a zebrafish pronephros "
                                "induction'). ALWAYS provide it — a low-confidence pass triggers an "
                                "external search and the index is English-only (ADR-0057).")},
            "gap_flags": {"type": "array", "items": {"type": "string"}},
            "evidence_cited": {
                "type": "array",
                "items": {"type": "object", "properties": {
                    "kind": {"type": "string",
                             "enum": ["di-chunk", "di-record", "di-database", "paper", "store-resolution",
                                      "other"]},
                    "id": {"type": "string"},
                    "note": {"type": "string"}},
                    "required": ["kind", "id"]},
                "description": "typed citations — every claim traces to a doc_id / CORPUS id / PMID"},
            # --- contrato §5, campos que faltaban en 100% de las corridas de la webapp (ADR-0060) ---
            "alternatives_considered": {
                "type": "array", "items": {"type": "string"},
                "description": ("REQUIRED by CLAUDE.md §5: the hypotheses/readings you REJECTED and why, "
                                "one per item. An answer with no alternatives considered is either "
                                "trivial or under-examined — say which. Asymmetry between formats is a "
                                "contract violation, so this travels in the record, not only in prose.")},
            "framework_applied": {
                "type": "string", "enum": reasoning_catalog.ENUM,
                "description": ("The reasoning framework you applied, chosen from the catalog handed to "
                                "you in the system prompt. Pick the NAME only — the catalog section and "
                                "the tier are resolved deterministically from a table, NOT from you "
                                "(CLAUDE.md §4 records two real sessions that cited 'Tier 2' instead of "
                                "the framework section; that is an audit failure). If none matches, "
                                "answer NONE-MATCHED instead of forcing one.")},
            "framework_criterion": {
                "type": "string",
                "description": ("QUOTE the applicability criterion from that framework's catalog entry "
                                "that your task actually matched. Required by §4: naming the framework "
                                "without quoting the criterion is an audit failure. Empty when "
                                "NONE-MATCHED — and then say why in framework_reason.")},
            "framework_reason": {
                "type": "string",
                "description": "one line on why this framework fits (or why none did)"},
        },
        "required": ["direct_answer", "confidence", "absence_kind", "alternatives_considered",
                     "framework_applied"],
    },
}

# --- elicitación dedicada del escalar (ADR-0065) -------------------------------------------------------
# El hallazgo medido (evaluation/scripts/ab_trapped_scalar.py, 2026-08-22): Opus 4.8 emite la transición
# de parámetro en sintaxis XML legada DENTRO del string de direct_answer en ~50-60% de las llamadas de
# síntesis (A 5/8 · C 6/12; 6/6 corridas de producción), es INSENSIBLE al orden del schema (emitió
# direct_answer primero en 16/16 aunque el schema listara confidence primero), `temperature` está
# DEPRECADO para el modelo (400 medido), y los nudges de prompt solo lo reducen (B 2/8). El fix
# estructural: un tool SIN campos de texto largo no tiene string que contaminar — 24/24 elicitaciones
# limpias — y la confianza se emite VIENDO la respuesta completa (answer-then-confidence). La semántica
# va CLAVADA al gate (una declinación honesta = confianza BAJA): la primera versión sin esta cláusula
# midió |delta| 0.75 vs el in-line — habría roto el fallback en silencio. Con la semántica fijada:
# |delta| mediana 0.09, sesgo conservador (jamás cruza el umbral en 24/24).
CONF_TOOL = {
    "name": "emit_confidence",
    "description": ("Emit ONLY the calibration scalars for the answer you are shown. No prose, no "
                    "restating the answer — just the numbers."),
    "input_schema": {
        "type": "object",
        "properties": {
            "confidence": {"type": "number", "minimum": 0, "maximum": 1,
                           "description": ("the SAME quantity the synthesizer reports in its own "
                                           "confidence field: how confident you are that the QUESTION "
                                           "is substantively and correctly ANSWERED from the evidence "
                                           "shown. Thin, off-topic or insufficient evidence means LOW "
                                           "confidence — and an answer that DECLINES or mostly "
                                           "describes gaps means LOW confidence (the fallback gate "
                                           "consumes this signal as 'is this evidence enough?'). This "
                                           "is NOT a grade of whether declining was the right move.")},
            "confidence_by_subclaim": {
                "type": "object", "additionalProperties": {"type": "number"},
                "description": ("REQUIRED when the answer composes sub-claims of asymmetric evidence "
                                "strength (CLAUDE.md §5): short label -> confidence, never averaged")},
        },
        "required": ["confidence"],
    },
}
ELICIT_SYSTEM = ("You are the confidence-calibration step of the Witt zebrafish evidence pipeline. "
                 "You are shown a question, the evidence bundle the synthesizer saw, and the answer "
                 "it produced (with its gap flags). Emit ONLY the calibration scalars via the tool. "
                 "SEMANTICS (hard rule): confidence measures whether the QUESTION got a substantive, "
                 "correct answer from THIS evidence — the very signal the pipeline's fallback gate "
                 "consumes. An honest decline over thin evidence is the RIGHT behavior AND scores LOW "
                 "confidence (low = 'this evidence is not enough', which is what triggers the external "
                 "search). Never score the quality of the declining itself.")


def _elicit_confidence(question, evidence, direct_answer, gap_flags, pass_label):
    """La medición AUTORITATIVA del escalar (ADR-0065): una mini-llamada forzada cuyo tool no tiene
    campos de texto largo — estructuralmente no hay string que contaminar. Devuelve (conf, subs, usage, meta);
    valores fuera de [0,1] o no numéricos se rechazan a None (el caller cae al in-line, §6 no-hang).

    ADR-0081: rol `elicitation` propio (WITT_MODEL_ELICIT; default de la generación), tope de la generación (g2 2000 —
    opus-5 piensa por default y con 300 la mini-llamada se truncaría; g1 300 = f57a3d3) y WITT_ANTHROPIC_EFFORT_ELICIT
    como override de effort SÓLO para CONF_TOOL. `meta` trae model (pedido), model_source, model_reported (lo que la
    API dijo; None con un stub), effort, effort_source."""
    user_text = json.dumps({"question": question, "evidence": evidence,
                            "produced_answer": {"pass": pass_label, "direct_answer": direct_answer,
                                                "gap_flags": gap_flags}},
                           ensure_ascii=False, default=str)
    role = models.resolve_role("elicitation")
    effort, effort_source = _effort_for(role["model"], elicit=True)
    out, usage, meta = _anthropic_call(role["model"], ELICIT_SYSTEM, user_text, CONF_TOOL,
                                       _max_tokens_for(role, "elicitation"), effort)
    conf = out.get("confidence")
    conf = float(conf) if isinstance(conf, (int, float)) and 0 <= conf <= 1 else None
    subs = out.get("confidence_by_subclaim") or None
    meta = {**meta, "model": role["model"], "model_source": role["source"],
            "effort": effort, "effort_source": effort_source}
    return conf, subs, usage, meta


# --- el planner (tapón 3, ADR-0061) --------------------------------------------------------------------
# El plan declarado del boceto M3: el checkpoint humano ANTES de gastar. Tres clases de contenido, cada
# una con su clase declarada, jamás mezcladas:
#   structural       — hechos del pipeline (Ruta A primero, B condicional, auditoría al 100%): del código.
#   model-judgment   — clasificación de work-type/nichos/agentes: juicio del modelo contra la matriz,
#                      con el gate level y la componentización resueltos por TABLA (agent_matrix).
#   projection       — costo/duración: mediana de la historia REAL, calculada por código (constitución:
#                      una proyección la calcula un tool desde insumos declarados, nunca la estima un
#                      modelo). Sin historia suficiente: "[?] sin historia suficiente" (LOTE-01).
PLAN_VERSION = "3"   # v3 (ADR-0066, adopción VB): +judgment.clarifying_questions (alineación pre-gasto,
                     # jamás bloquea) + data_landscape estructural (preview DI sparse NO-SPEND + qué
                     # fuentes Ruta B aplican — el briefing chief-of-staff, versión Witt).
                     # v2 (ADR-0063): +judgment.route — el juicio del planner ahora TIENE a dónde ir
PLAN_MIN_HISTORY = int(os.environ.get("WITT_PLAN_MIN_HISTORY", "3"))

PLAN_TOOL = {
    "name": "emit_plan_judgment",
    "description": ("Classify this question BEFORE the run executes (CLAUDE.md §11 preflight + §3 scope "
                    "filter). Judge which catalog agents' work-types the question implicates and which "
                    "niches it belongs to. You are NOT answering the question. Return ONLY applicable "
                    "agents — the gate level and whether each exists as an executable component are "
                    "resolved from a table, NOT by you."),
    "input_schema": {
        "type": "object",
        "properties": {
            "work_type": {"type": "string",
                          "description": "dominant work-type of answering this question, one short line"},
            "route": {
                "type": "string", "enum": ["evidence-run", "store-consultation"],
                "description": ("WHERE this question belongs (ADR-0063). 'store-consultation': the "
                                "question asks about the SYSTEM ITSELF — what the DATA INAMOVIBLE "
                                "contains, versions, counts, state, inventory ('qué tenemos en la "
                                "DI') — its answer lives in the consultation doors (store status, "
                                "taxonomy, Rack search), NOT in the evidence pipeline; running the "
                                "pipeline would spend the 4-judge panel on a question it cannot "
                                "answer from evidence chunks. 'evidence-run': a biology question "
                                "answerable from evidence — the pipeline's actual job.")},
            "niches": {"type": "array", "items": {"type": "string", "enum": agent_matrix.NICHE_ENUM},
                       "description": ("CLAUDE.md §3: every task classifies into >=1 of the six niches. "
                                       "Empty array = OUT OF SCOPE (must be flagged, never silently "
                                       "proceeded).")},
            "out_of_scope_reason": {"type": "string",
                                    "description": "REQUIRED when niches=[] — why no niche fits"},
            "agents_applicable": {
                "type": "array",
                "items": {"type": "object", "properties": {
                    "agent": {"type": "string", "enum": agent_matrix.ENUM},
                    "reason": {"type": "string",
                               "description": "which part of the question matches this work-type signal"}},
                    "required": ["agent", "reason"]},
                "description": ("agents whose work-type signal THIS question implicates (composite-auditor "
                                "and identifier-verification-gate always run — include them only to add a "
                                "question-specific reason)")},
            "clarifying_questions": {
                "type": "array", "maxItems": 3,
                "items": {"type": "object", "properties": {
                    "question": {"type": "string"},
                    "why": {"type": "string",
                            "description": "which analysis decision changes depending on the answer"}},
                    "required": ["question", "why"]},
                "description": ("0-3 clarification questions for the HUMAN, ONLY when the question is "
                                "genuinely ambiguous about scope or intent (ADR-0066, pre-spend "
                                "alignment). An EMPTY array means the question is clear — NEVER invent "
                                "questions for a clear one. These never block the run (never-stopper): "
                                "answering them refines a FUTURE plan, it is not a gate.")},
        },
        "required": ["work_type", "route", "niches", "agents_applicable"],
    },
}


def _data_landscape(question, entities):
    """El briefing de paisaje pre-gasto (ADR-0066 — el patrón chief-of-staff de Virtual Biotech,
    versión Witt): QUÉ tiene la DI sobre el tema (preview con el índice sparse LOCAL — NO-SPEND por
    construcción: cero red, cero embed, mismo patrón /status) y qué fuentes de Ruta B aplican
    (hechos del código, no juicio). Best-effort: su fallo jamás tumba el plan (§6 no-hang)."""
    land = {
        "class": "structural",
        "path_b_sources": {
            "europepmc": "aplica siempre (query EN, entidades-primero — ADR-0057)",
            "pubmed": "aplica siempre (NCBI E-utilities, dedup por PMID vs EPMC — ADR-0062)",
            "zfin": (f"aplica: {len(entities)} símbolo(s) de gen declarados"
                     if entities else "NO aplica sin entities (las keys son símbolos de gen — ADR-0059)"),
            "tooluniverse": "hook [] — solo sesiones de agente (ADR-0062)",
        },
        "note": ("preview con el índice sparse local (NO-SPEND, orientativo); la corrida real "
                 "recupera con el índice semántico — este conteo NO es una medición de la corrida"),
    }
    try:
        from lib import rag_backend
        hits = rag_backend.query_sparse(question, 5)
        land["di_preview"] = {"n_hits": len(hits),
                              "top_doc_ids": [getattr(h, "doc_id", None) for h in hits[:3]],
                              "mode": "sparse-preview-no-spend"}
    except Exception as e:
        land["di_preview"] = {"state": "unavailable",
                              "error": f"{type(e).__name__}: {str(e)[:120]}"}
    return land


def _default_planner(question, entities, thread_context=None):
    """One SMALL model call (rol `planner`, best-tier policy) that judges work-type/nichos/agentes contra
    la matriz. Inyectable en los gates. Devuelve (judgment_dict, usage, meta) — ADR-0081 (B): `meta` =
    {model (pedido, resuelto por tabla/env), model_source, model_reported (lo que la API dijo), relation,
    generation, effort, effort_source}; un planner inyectado con la firma vieja puede seguir devolviendo
    (judgment_dict, usage): build_plan tolera ambas (_planner_result).

    ADR-0079: `thread_context` (snapshot del turno anterior, armado por el SERVIDOR) viaja como llave
    APARTE del user_text — el planner ve qué se preguntó antes y qué faltó (gap_flags, comentarios),
    nunca mezclado con la pregunta. Sin padre (None) la llave no aparece: el prompt de una raíz es el
    de siempre."""
    system = ("You are the §11 agent-invocation preflight of the Witt × Organogenesis webapp: classify "
              "the incoming question BEFORE the pipeline runs. Judge strictly against the matrix and "
              "niches below; do NOT answer the question itself.\n\n" + agent_matrix.digest())
    payload = {"question": question, "entities": entities or []}
    if thread_context is not None:
        payload["thread_context"] = thread_context
    user_text = json.dumps(payload, ensure_ascii=False, default=str)
    role = models.resolve_role("planner")
    effort, effort_source = _effort_for(role["model"])
    out, usage, meta = _anthropic_call(role["model"], system, user_text, PLAN_TOOL,
                                       _max_tokens_for(role, "planner"), effort)
    return out, usage, {"model": role["model"], "model_source": role["source"],
                        "model_reported": meta.get("model_reported"),
                        "relation": models.relation(role["model"], meta.get("model_reported")),
                        "generation": role["generation"], "effort": effort, "effort_source": effort_source}


def _planner_result(res):
    """(out, usage, meta) de lo que devolvió el planner. El wrapper real (_default_planner) entrega 3-tupla con la
    procedencia; un planner inyectado con la firma vieja entrega (out, usage) → `model` = el rol RESUELTO por la tabla
    en la llamada (lo que el código pediría, con su fuente) y model_reported None → relation 'not-reported'. Nada se
    copia de una constante al lugar de lo que la API dijo (ADR-0081 B)."""
    if isinstance(res, tuple) and len(res) >= 3 and isinstance(res[2], dict):
        out, usage, meta = res[0], res[1], dict(res[2])
    else:
        out, usage = res
        meta = {}
    if not meta.get("model"):
        role = models.resolve_role("planner")
        meta["model"], meta["model_source"] = role["model"], role["source"]
    meta.setdefault("model_source", None)
    meta.setdefault("model_reported", None)
    meta["relation"] = models.relation(meta["model"], meta.get("model_reported"))
    return out, usage, meta


def _plan_structural_audit():
    """plan.audit (clase structural — 'del código'): el panel que VA a correr, resuelto por models.panel() EN LA
    LLAMADA (tabla + env WITT_JUDGE_*/OPENAI_JUDGE_MODEL/WITT_MODEL_GENERATION — ADR-0081 A), no el literal de una
    generación. `panel` conserva su forma de prosa; `panel_resolved[]` añade reviewer/family/lens/reviewer_source
    (aditivo 1.10)."""
    seats = models.panel()
    return {"class": "structural", "required": True,
            "panel": [f"{m['reviewer']} ({m['lens']})" for m in seats],
            "panel_resolved": [{k: m.get(k) for k in ("reviewer", "family", "lens", "reviewer_source")}
                               for m in seats],
            "note": "obligatorio en el 100% de las corridas (ADR-0049) — la mayor parte del costo"}


def plan_estimates(history_rows):
    """Proyección DETERMINISTA de costo/duración por escenario (DI-only vs con-fallback), mediana sobre
    la historia real. n < PLAN_MIN_HISTORY => estado insufficient-history (LOTE-01: '[?] sin historia
    suficiente' — jamás un número inventado)."""
    def _median(vals):
        vals = sorted(v for v in vals if isinstance(v, (int, float)))
        if not vals:
            return None
        m = len(vals) // 2
        return round((vals[m] if len(vals) % 2 else (vals[m - 1] + vals[m]) / 2), 4)

    def _metric(rows, key):
        """Estado POR MÉTRICA. El defecto que esto corrige lo destapó la primera corrida real del
        planner: el escenario se reportaba `projected` con la mediana de costo en null, porque las
        corridas de ese escenario no tenían gasto medido. Una proyección sin número NO es una
        proyección — cada métrica declara su propio denominador."""
        vals = [r.get(key) for r in rows]
        n = sum(1 for v in vals if isinstance(v, (int, float)))
        if n < PLAN_MIN_HISTORY:
            return {"state": "insufficient-history", "n_measured": n,
                    "min_required": PLAN_MIN_HISTORY,
                    "note": "[?] sin historia suficiente — no se inventa un número"}
        return {"state": "projected", "n_measured": n, "median": _median(vals),
                "basis": f"mediana de {n} corridas con esta métrica medida"}

    def _scenario(rows, label):
        cost, dur = _metric(rows, "cost_usd"), _metric(rows, "duration_s")
        # el escenario está proyectado sólo si AMBAS métricas lo están; si una falta, se declara
        # parcial en vez de dejar que la que sí existe cubra a la que no
        states = {cost["state"], dur["state"]}
        state = ("projected" if states == {"projected"}
                 else "insufficient-history" if states == {"insufficient-history"}
                 else "partial")
        return {"scenario": label, "state": state, "n_runs": len(rows),
                "cost_usd": cost, "duration_s": dur}

    rows = history_rows or []
    di_only = [r for r in rows if r.get("trigger") is None]
    fallback = [r for r in rows if r.get("trigger") is not None]
    return {"class": "PROJECTION (calculada por código desde la historia real; los insumos son "
                     "mediciones, la proyección no lo es)",
            "di_only": _scenario(di_only, "di-only"),
            "with_fallback": _scenario(fallback, "with-fallback")}


def build_plan(question, entities=None, planner=None, history_rows=None, thread_context=None):
    """El plan completo. El juicio del modelo puede FALLAR sin tumbar nada (§6 no-hang): un plan con
    judgment.state=errored sigue siendo un plan — declara que el juicio no se pudo hacer, que es
    distinto de no haberlo intentado.

    ADR-0079: `thread_context` (el sobre {snapshot, skipped_reason} de plan_thread_context, o el
    snapshot directo) llega al planner como llave hermana. El plan DECLARA si el planner lo vio
    (plan.thread_context_declared) — un componente que cambia el prompt lo dice en el registro."""
    planner = planner or _default_planner
    entities = [e for e in (entities or []) if e and e.strip()]
    snapshot = _snapshot_of(thread_context)

    plan = {
        "plan_version": PLAN_VERSION,
        "matrix": f"{agent_matrix.MATRIX_PATH} {agent_matrix.MATRIX_VERSION}",
        "question": question, "entities": entities,
        # ADR-0079: tres estados — False (raíz: no había turno anterior) / True (el planner lo vio) /
        # el skipped_reason cuando había padre pero el snapshot no se armó (identidad inválida, kill-switch)
        "thread_context_declared": snapshot is not None,
        "thread_context_skipped_reason": ((thread_context or {}).get("skipped_reason")
                                         if isinstance(thread_context, dict) and snapshot is None
                                         else None),
        # corrector ADR-0079: QUÉ padre y QUÉ registro (sha) vio el planner — al congelar la corrida se
        # derivan plan_parent_matches_run / plan_snapshot_matches_run (un plan hecho con el padre X no puede
        # respaldar en silencio una corrida con padre Y; misma disciplina que plan_question_matches_run).
        "thread_parent_run_id": (((thread_context or {}).get("parent_run_id")
                                  if isinstance(thread_context, dict) else None)
                                 or ((snapshot or {}).get("parent") or {}).get("run_id")),
        "thread_parent_frozen_sha256": (snapshot or {}).get("parent_frozen_sha256"),
        "route": {
            "class": "structural",
            "path_a": "DATA INAMOVIBLE primero — siempre",
            "path_b": {"conditional": True,
                       "note": ("la suficiencia se evalúa DESPUÉS de correr la Ruta A: declarar la Ruta B "
                                "como hecho sería inventar información"),
                       "deciders": ["structural (assess_sufficiency)",
                                    f"confidence (pass1 < tau={FALLBACK_CONF_TAU})"],
                       "sources": list(answer_pipeline.PATH_B_SOURCES)},
        },
        "audit": _plan_structural_audit(),   # ADR-0081: el panel RESUELTO en la llamada + panel_resolved[]
        "deterministic_gate": {"class": "structural", "component": "lib/verify_output.py",
                               "note": "clase Logic-LM, no es un LLM; corre en cada corrida"},
    }
    # ADR-0066: el paisaje es ESTRUCTURAL — se calcula aunque el juicio del planner falle
    plan["data_landscape"] = _data_landscape(question, entities)

    try:
        # ADR-0079: el snapshot viaja al planner SOLO si existe; un planner inyectado con la firma vieja
        # (question, entities) sigue funcionando y el plan declara que no lo recibió.
        res, ctx_delivered = _call_with_optional(planner, (question, entities), "thread_context", snapshot)
        out, usage, pmeta = _planner_result(res)   # ADR-0081 (B): 3-tupla del wrapper real o 2-tupla de un stub
        niches = [{"code": c, **agent_matrix.NICHES[c]} for c in out.get("niches", [])
                  if c in agent_matrix.NICHES]
        agents = []
        for a in out.get("agents_applicable", []):
            row = agent_matrix.resolve(a.get("agent"))
            if row is None:
                agents.append({"agent": a.get("agent"), "off_matrix": True,
                               "reason": a.get("reason", ""), "will_run": "unknown-off-matrix"})
                continue
            comp = row.get("componentized")
            agents.append({
                "agent": a["agent"],
                "gate": row["gate"],
                "signal": row["signal"],
                "evidence": row["evidence"],
                "componentized": bool(comp),
                "component": comp[0] if comp else None,
                "matrix_note": row.get("note"),
                "reason": a.get("reason", ""),
                "will_run": "runs-always-componentized" if comp else "skipped-ad-hoc",
            })
        # la ruta (ADR-0063): el modelo la elige; la GUÍA la resuelve la tabla — dónde vive la
        # respuesta es un hecho del sistema, no un juicio
        route = out.get("route") or "evidence-run"
        route_guidance = None
        if route == "store-consultation":
            route_guidance = {
                "doors": ["Rack — estado del store, búsqueda y resolución determinista (/rack)",
                          "taxonomía y crosswalk — la única puerta (/rack)",
                          "estado del sistema y consumo (/consumo)"],
                "note": ("la respuesta a una pregunta de inventario/estado vive en las puertas de "
                         "consulta (deterministas, sin gasto de modelo). El pipeline la trataría "
                         "como pregunta de evidencia y gastaría el panel de 4 jueces en algo que "
                         "no puede responder desde chunks."),
            }
        # el filtro §3 gobierna TAREAS de sustrato; una pregunta meta sobre el sistema no es
        # fuera-de-alcance ni dentro: el filtro NO APLICA, y eso se declara (tres estados, no dos)
        if route == "store-consultation":
            scope = {"in_scope": None,
                     "note": ("consulta META sobre el sistema — el filtro §3 aplica a tareas de "
                              "sustrato, no a preguntas de inventario; no-aplica ≠ fuera-de-alcance")}
        elif niches:
            scope = {"in_scope": True}
        else:
            scope = {"in_scope": False,
                     "reason": out.get("out_of_scope_reason") or "no declarado",
                     "note": "§3: una tarea fuera de los seis nichos SE MARCA — el humano decide"}
        plan["judgment"] = {
            "class": "model-judgment",
            "state": "declared",
            "work_type": out.get("work_type"),
            "route": route,
            "route_guidance": route_guidance,
            "niches": niches,
            "scope": scope,
            "agents_applicable": agents,
            # ADR-0066 (never-stopper): 0-3 preguntas de clarificación pre-gasto; [] = pregunta clara.
            # JAMÁS bloquean — responderlas refina un plan FUTURO, no es un gate.
            "clarifying_questions": out.get("clarifying_questions") or [],
            # ADR-0081 (B): `model` = lo PEDIDO (resuelto por tabla/env en la llamada), `model_source` su fuente,
            # `model_reported` lo que la API dijo (None con un planner stub), `relation` la comparación.
            # frozen.models.roles.planner COPIA este bloque (el plan pudo correr antes de un redeploy: un plan
            # opus-4-8 con síntesis opus-5 es la verdad, no un bug — la Hoja lo pinta sin "corregir").
            "planner": {"model": pmeta["model"], "model_source": pmeta["model_source"],
                        "model_reported": pmeta.get("model_reported"), "relation": pmeta["relation"],
                        "usage": usage, "class": "self-report",
                        "note": "juicio de prompt-time (misma advertencia §5 que framework_applied)",
                        # ADR-0079: None = no había snapshot; True/False = lo recibió / firma sin la llave
                        "thread_context_delivered": (ctx_delivered if snapshot is not None else None)},
        }
    except Exception as e:
        plan["judgment"] = {"class": "model-judgment", "state": "errored",
                            "error": f"{type(e).__name__}: {str(e)[:300]}",
                            "note": ("el juicio no se pudo hacer — DISTINTO de no intentado y de "
                                     "'ningún agente aplica'. El plan sigue siendo válido en sus partes "
                                     "estructurales; preguntar no se bloquea (§6 no-hang).")}

    plan["estimates"] = plan_estimates(db.plan_history() if history_rows is None else history_rows)
    return plan


def plan_event_payload(plan):
    """Resumen de stage.plan — la traza viva y el replay leen el MISMO resumen."""
    j = plan.get("judgment", {})
    p = {"plan_version": plan.get("plan_version"),
         "judgment_state": j.get("state"),
         "work_type": j.get("work_type"),
         "route": j.get("route"),
         "niches": [n.get("code") for n in j.get("niches", [])],
         "n_agents_applicable": len(j.get("agents_applicable", [])),
         "agents": [a.get("agent") for a in j.get("agents_applicable", [])],
         "n_clarifying": len(j.get("clarifying_questions") or []),                       # ADR-0066
         "di_preview_hits": ((plan.get("data_landscape") or {}).get("di_preview") or {}).get("n_hits"),
         "audit_required": True}
    sc = j.get("scope") or {}
    if sc.get("in_scope") is False:
        p["out_of_scope"] = True
    return p


def _agents_invoked(audit_result, deterministic_checks, plan=None):
    """§11's `agents_invoked`, DERIVED FROM WHAT ACTUALLY RAN — never self-reported. A model listing the
    agents it invoked is precisely the §7 anti-pattern (self-audit as audit evidence); the code knows.

    Con plan (tapón 3, ADR-0061): el preflight §11 SÍ se hizo — lo hizo el planner antes de encolar.
    Cada agente que el planner juzgó aplicable y no existe como componente entra con el literal §5 de la
    matriz (`skipped-ad-hoc`: el rol corre ad-hoc dentro de la síntesis) y la razón del planner. El resto
    del catálogo queda en UNA fila agregada `not-applicable` (trazabilidad sin 25 filas de ruido).

    Sin plan: el hueco sigue declarado como `not-assessed` — nadie juzgó, y eso se dice.

    Schema per §11: {agent, status, invocation_id|reason, evidence_generated}."""
    out = [{
        "agent": "composite-auditor",
        "status": "invoked",
        "invocation_id": f"panel:{audit_result.get('n_valid')}/{len(audit_result.get('panel', []))}",
        "evidence_generated": [f"verdict:{audit_result.get('verdict')}",
                               f"tally:{json.dumps(audit_result.get('tally', {}), sort_keys=True)}",
                               # ADR-0081 (D): familias que votaron válidas (composite_auditor); None = audit() sin cuórum
                               f"families_valid:{audit_result.get('n_families_valid')}"],
    }, {
        "agent": "verify_output (gate determinista, clase Logic-LM)",
        "status": "invoked",
        "invocation_id": "deterministic_gate",
        "evidence_generated": [f"admissible:{deterministic_checks.get('admissible')}"],
    }]
    judgment = (plan or {}).get("judgment") or {}
    if judgment.get("state") == "declared":
        judged = 0
        for a in judgment.get("agents_applicable", []):
            if a.get("componentized"):
                continue   # composite-auditor / verify_output ya están arriba como invoked, medidos
            judged += 1
            out.append({
                "agent": a.get("agent"),
                "status": "skipped-ad-hoc",   # literal §5 de la matriz: el rol corre ad-hoc en la síntesis
                "reason": (f"planner (§11): {a.get('reason', '')} — no existe como componente; la "
                           f"síntesis cubre el rol ad-hoc. Gate de matriz: {a.get('gate')}"
                           + (f". {a.get('matrix_note')}" if a.get("matrix_note") else "")),
                "evidence_generated": [],
            })
        out.append({
            "agent": f"(resto del catálogo — {agent_matrix.MATRIX_VERSION})",
            "status": "not-applicable",
            "reason": (f"preflight §11 HECHO por el planner: {judged} aplicables arriba; los demás "
                       f"work-types de la matriz no aplican a esta pregunta (fila agregada por "
                       f"trazabilidad, matriz {agent_matrix.MATRIX_PATH})"),
            "evidence_generated": [],
        })
    else:
        reason_extra = ""
        if judgment.get("state") == "errored":
            reason_extra = (f" En esta corrida SÍ se intentó (plan adjunto) pero el juicio FALLÓ: "
                            f"{judgment.get('error', '')}.")
        out.append({
            # El hueco, DECLARADO en cada corrida en vez de invisible. `not-assessed` NO es
            # `skipped-ad-hoc`: saltarse con justificación afirma que alguien juzgó; esto afirma que
            # nadie juzgó (o que el juicio falló, y entonces se dice).
            "agent": "(preflight §11 sobre el catálogo de agentes)",
            "status": "not-assessed",
            "reason": ("la corrida no lleva juicio del planner: ningún componente decidió qué agente "
                       "del catálogo es dueño del work-type de esta respuesta. NO equivale a "
                       "skipped-ad-hoc (que afirmaría un juicio hecho)." + reason_extra),
            "evidence_generated": [],
        })
    return out


# --- ciclo de revisión acotado (ADR-0067, adopción del loop reviewer->re-delegate de VB) --------------
# Hoy un REVISE del panel era terminal: la corrida moría honesta sin intentar la corrección. VB
# demuestra el valor del loop de re-delegación; la versión Witt lo acota y lo AUDITA: UNA pasada de
# revisión con los hallazgos del panel como insumo tipado, re-gate determinista, re-auditoría, y tope
# DURO de 1 (dinámica-dentro-de-etapas-acotadas, jamás iteración abierta — stress-test/method-selection).
# A diferencia de VB, NADA se borra: ambas respuestas y ambos veredictos persisten en el registro.
REVISION_CAP = 1


def _revision_enabled():
    """Kill-switch operativo (leído en tiempo de corrida, no de import): WITT_REVISION_CYCLE=0
    restaura el comportamiento pre-ADR-0067 (REVISE terminal sin intento de corrección)."""
    return os.environ.get("WITT_REVISION_CYCLE", "1") == "1"


def _panel_findings(audit_result):
    """Los hallazgos ACCIONABLES del panel para la pasada de revisión: qué atrapó cada juez y qué
    corrección propuso — lo que VB re-delega como prosa, aquí viaja como insumo tipado. Incluye
    APPROVE_MINOR (catch real aunque no vete) además de REVISE."""
    out = []
    for r in audit_result.get("panel", []):
        if r.get("verdict") in ("REVISE", "APPROVE_MINOR") and (r.get("caught") or r.get("reasons")):
            out.append({"lens": r["lens"], "reviewer": r["reviewer"], "verdict": r["verdict"],
                        "caught": r.get("caught", ""),
                        "correction_applied": r.get("correction_applied", ""),
                        "reasons": r.get("reasons", [])})
    return out


# --- investigación: turnos encadenados sobre una raíz (ADR-0079) ---------------------------------------
# Una corrida puede NACER desde otra terminada. La derivación (thread_id, turn_no, turn_kind, origin,
# snapshot del turno anterior) la hace el SERVIDOR al encolar (ADR-0056: procedencia derivada, jamás del
# cliente); db sólo persiste (T1). Vocabulario en código: thread_id / turn_no / turn_kind / parent_run_id;
# en docs y mensajes al humano: "investigación" (T-<run_no raíz>) — "hilo" ya nombra los comentarios
# (ADR-0077). Doctrina: el turno anterior es PRECEDENTE (serie de letras, ADR-0053), nunca evidencia; lo
# ausente se declara (tres estados); el registro congelado del padre es INMUTABLE (ADR-0074) y por eso
# su sha al encolar debe coincidir con su sha al congelar al hijo (thread_parent_matches_run).
THREAD_CONTEXT_ENV = "WITT_THREAD_CONTEXT"            # default 1; 0 = kill-switch (columnas sí, contexto no)
THREAD_COMMENTS_MAX_DEFAULT = 8                        # WITT_THREAD_COMMENTS_MAX
THREAD_COMMENTS_CHARS_DEFAULT = 8000                   # WITT_THREAD_COMMENTS_CHARS (total, todos los cuerpos)
THREAD_ANSWER_CHARS_DEFAULT = 1200                     # WITT_THREAD_ANSWER_CHARS (direct_answer del padre)
THREAD_CONTEXT_EXCLUDED = ["ratings values and notes (masked per requester, never averaged)"]
THREAD_SHA_EXCLUDED_KEYS = ("frozen_at", "closed_by")  # las DOS únicas llaves que close_run añade al blob
THREAD_SHA_RULE = ("sha256 of json.dumps(frozen_record minus {frozen_at, closed_by}, sort_keys=True): the "
                   "frozen blob is immutable (ADR-0074); closure only appends those two keys (ADR-0079)")
# identificadores cuya presencia en el contexto del padre + en la respuesta del hijo + AUSENCIA de la
# evidencia del hijo = fuga (parent_identifier_leak). Patrones declarados junto al resultado.
IDENTIFIER_PATTERNS = {
    "ensdarg": re.compile(r"ENSDARG\d+", re.I),
    "pmid": re.compile(r"PMID:\s?\d+", re.I),
    "pmc": re.compile(r"PMC\d+", re.I),
    "doi": re.compile(r"10\.\d{4,9}/[^\s\"',;)\]}>]+"),   # 'DOI 10\.\S+' sin arrastrar puntuación JSON
    "zdb": re.compile(r"ZDB-[A-Z]+-\d+-\d+"),
}


class ThreadError(Exception):
    """ADR-0079 — error de derivación de investigación al encolar. `status` y `detail` son lo que la
    capa HTTP (app.py, T3) traduce a HTTPException; runs.py no importa fastapi."""
    def __init__(self, status, detail):
        super().__init__(detail.get("state") if isinstance(detail, dict) else str(detail))
        self.status = status
        self.detail = detail


class ParentNotFound(ThreadError):
    def __init__(self, parent_run_id):
        super().__init__(404, {"state": "parent_not_found", "parent_run_id": parent_run_id,
                               "note": "parent_run_id no existe (ADR-0079)"})


class ParentNotTerminal(ThreadError):
    def __init__(self, parent_run_id, parent_state):
        super().__init__(409, {"state": "parent_not_terminal", "parent_run_id": parent_run_id,
                               "parent_state": parent_state,
                               "note": (f"la corrida padre está '{parent_state}'; sólo una corrida terminal "
                                        f"{db.RATABLE_STATES} puede tener un turno siguiente (ADR-0079)")})


def _thread_context_enabled():
    """Kill-switch operativo (leído en tiempo de corrida, patrón WITT_REVISION_CYCLE): WITT_THREAD_CONTEXT=0
    → las columnas de investigación SÍ se llenan, el snapshot NO se arma ni viaja, skipped_reason declarado."""
    return os.environ.get(THREAD_CONTEXT_ENV, "1").strip() != "0"


def _kill_switch_view():
    return {THREAD_CONTEXT_ENV: os.environ.get(THREAD_CONTEXT_ENV, "1"),
            "default": "1", "enabled": _thread_context_enabled()}


def _thread_limits():
    """Topes del snapshot, leídos en tiempo de corrida con fuente declarada (_env_int_tolerante: env
    vacía / no numérica / <= 0 → default DECLARADO, nunca un int() que tumbe el proceso — ADR-0078)."""
    out = {}
    for key, env, default in (("comments_max", "WITT_THREAD_COMMENTS_MAX", THREAD_COMMENTS_MAX_DEFAULT),
                              ("comments_chars", "WITT_THREAD_COMMENTS_CHARS", THREAD_COMMENTS_CHARS_DEFAULT),
                              ("answer_chars", "WITT_THREAD_ANSWER_CHARS", THREAD_ANSWER_CHARS_DEFAULT)):
        v, src = _env_int_tolerante(env, default)
        out[key], out[key + "_source"] = v, src
    return out


def run_origin():
    """(F) La PROCEDENCIA de la corrida, derivada por el servidor al encolar: {value, source}.
    WITT_RUN_ORIGIN definida y en db.RUN_ORIGINS → ese valor (source 'env:WITT_RUN_ORIGIN'); fuera del enum
    → 'invalid-env:<valor>' DECLARADO (la corrida se crea igual — no se corrige en silencio ni se tumba);
    sin env: 'dev-offline' cuando WITT_ALLOW_RUNS_OFFLINE == '1' (source 'derived:offline-mask'), si no
    'production' (source 'default:production'). La columna runs.origin mide 24 chars: un valor inválido
    largo se recorta y se declara `truncated`."""
    raw = os.environ.get("WITT_RUN_ORIGIN")
    if raw is not None and raw.strip():
        v = raw.strip()
        if v in db.RUN_ORIGINS:
            return {"value": v, "source": "env:WITT_RUN_ORIGIN"}
        full = f"invalid-env:{v}"
        out = {"value": full[:24], "source": "env:WITT_RUN_ORIGIN", "raw": v,
               "note": f"WITT_RUN_ORIGIN fuera del enum {db.RUN_ORIGINS} — declarado, la corrida se crea igual"}
        if len(full) > 24:
            out["truncated"] = True
        return out
    if os.environ.get("WITT_ALLOW_RUNS_OFFLINE") == "1":
        return {"value": "dev-offline", "source": "derived:offline-mask"}
    return {"value": "production", "source": "default:production"}


def frozen_sha256(frozen_json):
    """Sha del registro congelado SIN frozen_at/closed_by (THREAD_SHA_RULE). None cuando no hay blob; un
    blob no-JSON se hashea tal cual y se declara con el prefijo 'raw:' (jamás se finge la regla)."""
    if not frozen_json:
        return None
    try:
        rec = json.loads(frozen_json)
    except ValueError:
        return "raw:" + hashlib.sha256(frozen_json.encode("utf-8")).hexdigest()
    if not isinstance(rec, dict):
        return "raw:" + hashlib.sha256(frozen_json.encode("utf-8")).hexdigest()
    body = {k: v for k, v in rec.items() if k not in THREAD_SHA_EXCLUDED_KEYS}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False,
                                     default=str).encode("utf-8")).hexdigest()


def _gap_flags_tolerante(raw):
    """Lectura TOLERANTE (ADR-0074) de gap_flags del registro del padre: lista → íntegra; string → JSON de
    lista parseado o el string como UN elemento; None → None (ausente declarado, no [])."""
    if raw is None:
        return None
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, str):
        parsed = _lista_serializada(raw)
        return parsed if parsed is not None else [raw]
    return [json.dumps(raw, ensure_ascii=False, default=str)]


def _human_comments(comments_rows, limits):
    """Los comentarios del padre (ADR-0077) como insumo ATESTIGUADO: orden determinista, tope en número y en
    caracteres totales, `truncated` declarado. Los cuerpos son de humanos: viajan verbatim (recortados si
    hace falta), jamás resumidos por el modelo aquí.
    Corrector ADR-0079 — orden: db.list_run_comments ya viene en (created_at con microsegundos, comment_id);
    la vista sólo trae created_at a SEGUNDOS, así que aquí se ordena ESTABLE por ese string y el empate
    conserva el orden de llegada. Desempatar por comment_id (uuid aleatorio) barajaba dos comentarios del
    mismo segundo — el gate lo midió (orden 50/50)."""
    rows = sorted(comments_rows or [], key=lambda c: str(c.get("created_at") or ""))
    out, used, truncated = [], 0, False
    for c in rows:
        if len(out) >= limits["comments_max"]:
            truncated = True
            break
        body = c.get("body") or ""
        room = limits["comments_chars"] - used
        if room <= 0:
            truncated = True
            break
        if len(body) > room:
            body, truncated = body[:room], True
        used += len(body)
        out.append({"author_name": c.get("author_name"), "created_at": c.get("created_at"), "body": body})
    return {"items": out, "n_total": len(rows), "n_included": len(out), "chars_included": used,
            "truncated": truncated, "class": "atestiguada",
            # corrector ADR-0079: el tope es en CARACTERES (code points); snapshot.bytes mide UTF-8 — dos
            # unidades distintas, ambas etiquetadas para que nadie las compare entre sí
            "limits": {"max": limits["comments_max"], "chars": limits["comments_chars"],
                       "unit": "chars (code points)"}}


def build_thread_context(parent_run_row, comments_rows, now):
    """(C) El snapshot del turno anterior, armado en el SERVIDOR al encolar desde frozen_record_json +
    run_comments del padre (jamás del cliente). PURO: no toca la BD — los renglones llegan como
    argumentos, así que se prueba sin motor. Devuelve el SOBRE {snapshot: dict|null, skipped_reason:
    str|null, kill_switch, built_at} — tres estados por construcción:
      · padre con question_matches_run === false → snapshot null, skipped_reason 'parent-identity-invalid'
        (la corrida hija SÍ se crea; el llamador decide).
      · padre sin registro congelado (failed/cancelled) → snapshot CON previous_answer null y previous_audit
        null declarados (frozen_absent_reason 'parent-without-frozen-record').
      · snapshot completo en el resto.
    evidence_hints son PISTAS para RE-RECUPERAR (el texto se vuelve a leer de la fuente); las
    calificaciones quedan fuera por diseño (excluded). `bytes` mide el snapshot serializado."""
    limits = _thread_limits()
    parent = parent_run_row or {}
    frozen_json = parent.get("frozen_record_json")
    frozen, frozen_state = None, "absent"
    if frozen_json:
        try:
            frozen = json.loads(frozen_json)
            frozen_state = "present" if isinstance(frozen, dict) else "unparseable"
            if not isinstance(frozen, dict):
                frozen = None
        except ValueError:
            frozen, frozen_state = None, "unparseable"
    envelope = {"snapshot": None, "skipped_reason": None, "kill_switch": _kill_switch_view(),
                "built_at": now.isoformat(timespec="seconds") if hasattr(now, "isoformat") else str(now)}
    if frozen is not None and frozen.get("question_matches_run") is False:
        envelope["skipped_reason"] = "parent-identity-invalid"
        envelope["note"] = ("el registro del padre declara question_matches_run=false (ADR-0044): su "
                            "respuesta no es de su pregunta y no puede ser contexto de nadie")
        return envelope

    ans = (frozen or {}).get("answer") or {}
    audit = (frozen or {}).get("audit") or {}
    conf = (frozen or {}).get("confidence") or {}
    snap = {
        "parent": {"run_id": parent.get("run_id"), "run_no": parent.get("run_no"),
                   "question": parent.get("question"), "entities_csv": parent.get("entities_csv"),
                   "state": parent.get("state"), "verdict": audit.get("verdict"),
                   "decision_state": ((frozen or {}).get("decision_state") or {}).get("state")},
        "previous_answer": None, "previous_audit": None,
        "human_comments": _human_comments(comments_rows, limits),
        "evidence_hints": {"entities": [e for e in (parent.get("entities_csv") or "").split(",") if e],
                           "approved_evidence_ids": list(audit.get("approved") or []),
                           "note": "hints to RE-RETRIEVE only — the text is re-read from the source"},
        "excluded": list(THREAD_CONTEXT_EXCLUDED),
        "snapshot_at": envelope["built_at"],
        "parent_frozen_sha256": frozen_sha256(frozen_json),
        "parent_frozen_sha256_rule": THREAD_SHA_RULE,
        "kill_switch": {THREAD_CONTEXT_ENV: os.environ.get(THREAD_CONTEXT_ENV, "1")},
    }
    if frozen is None:
        snap["frozen_absent_reason"] = ("parent-without-frozen-record" if frozen_state == "absent"
                                        else "parent-frozen-record-unparseable")
    else:
        da = ans.get("direct_answer") or ""
        snap["previous_answer"] = {
            "direct_answer": da[:limits["answer_chars"]],
            "direct_answer_truncated": len(da) > limits["answer_chars"],
            "direct_answer_chars_total": len(da),
            "stated_confidence": ans.get("stated_confidence", conf.get("final")),
            "absence_kind": ans.get("absence_kind"),
            "gap_flags": _gap_flags_tolerante(ans.get("gap_flags")),
            "confidence_by_subclaim": conf.get("by_subclaim"),
        }
        snap["previous_audit"] = {"verdict": audit.get("verdict"), "n_valid": audit.get("n_valid"),
                                  "findings": _panel_findings(audit)[:5]}
    if parent.get("thread_id") is None:
        snap["parent_pre_adr_0079"] = True   # el padre nació antes del contrato: raíz VIRTUAL (turn_no 2)
    snap["bytes_unit"] = "utf-8 bytes"   # corrector ADR-0079: la unidad viaja junto a la cifra
    snap["bytes"] = len(json.dumps(snap, ensure_ascii=False, default=str).encode("utf-8"))
    envelope["snapshot"] = snap
    return envelope


def _snapshot_of(thread_context):
    """El snapshot dentro de un sobre {snapshot, skipped_reason}, o el snapshot mismo si llegó crudo."""
    if not isinstance(thread_context, dict):
        return None
    if "snapshot" in thread_context and "skipped_reason" in thread_context:
        return thread_context.get("snapshot")
    return thread_context


def _thread_envelope(run):
    """El sobre persistido en runs.thread_context_json (tres estados): NULL/ausente = corrida pre-ADR o
    encolada sin derivación → sobre vacío con skipped_reason declarado; si no, el JSON tal cual."""
    raw = run.get("thread_context_json") if isinstance(run, dict) else None
    if not raw:
        return {"snapshot": None,
                "skipped_reason": ("root-turn" if run.get("turn_kind") == "root"
                                   else "thread_context_json-absent (pre-ADR-0079 row or undeclared)")}
    try:
        env = json.loads(raw)
    except ValueError:
        return {"snapshot": None, "skipped_reason": "thread_context_json-unparseable"}
    if not isinstance(env, dict):
        return {"snapshot": None, "skipped_reason": "thread_context_json-unparseable"}
    if "snapshot" not in env:
        env = {"snapshot": env, "skipped_reason": None}
    return env


def _call_with_optional(fn, args, name, value):
    """Llama fn(*args, name=value) si la firma acepta `name` (o **kwargs); si no, fn(*args). Devuelve
    (resultado, entregado: bool). Determinista por inspección de firma — NO un try/except TypeError que
    enmascararía errores reales del callable (ADR-0079: los stubs con la firma vieja siguen válidos y el
    registro declara que no recibieron el contexto)."""
    accepts = False
    try:
        params = inspect.signature(fn).parameters
        accepts = name in params or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
    except (TypeError, ValueError):
        accepts = False
    if accepts:
        return fn(*args, **{name: value}), True
    return fn(*args), False


def extract_identifiers(text):
    """Identificadores (IDENTIFIER_PATTERNS) presentes en un texto, normalizados (mayúsculas, sin espacio
    tras 'PMID:'), como conjunto ordenable."""
    found = set()
    for pat in IDENTIFIER_PATTERNS.values():
        for m in pat.findall(text or ""):
            # corrector ADR-0079: el patrón DOI arrastraba el punto/coma final de la prosa ("… 10.1242/dev.1.")
            # → el token no casaba con el mismo DOI en la evidencia → falso positivo del predicado DURO.
            found.add(re.sub(r"^PMID:\s+", "PMID:", m.rstrip(".,").upper()))
    return found


def parent_identifier_leak(thread_snapshot, direct_answer, evidence_ids, evidence_text=""):
    """(E) Identificadores presentes en el TEXTO del snapshot del padre Y en la respuesta del hijo Y
    AUSENTES de la evidencia del hijo (sus evidence_ids y el texto de la evidencia que el modelo vio).
    Lista ordenada; [] sin snapshot (el llamador declara 'no-parent'). Regla declarada en el registro:
    un identificador que sí está en la evidencia del hijo no es fuga aunque el padre también lo tuviera."""
    if not thread_snapshot:
        return []
    ctx_ids = extract_identifiers(json.dumps(thread_snapshot, ensure_ascii=False, default=str))
    ans_ids = extract_identifiers(direct_answer or "")
    ev_ids = extract_identifiers(" ".join(str(i) for i in (evidence_ids or []))) | extract_identifiers(evidence_text)
    ev_ids |= {str(i).upper() for i in (evidence_ids or [])}
    return sorted((ctx_ids & ans_ids) - ev_ids)


def _leak_check(thread_snapshot, direct_answer, bundle, run=None):
    """(checks_dict_fragment, extra_predicates) para verify_output.admissible. Predicado DURO: fuga no vacía
    → inadmisible (declarado en reasons como 'hard predicate failed: parent_identifier_leak').
    Corrector ADR-0079 — TRES estados en parent_identifier_leak_state (mismo vocabulario que
    thread_parent_matches_run_state): 'no-parent' sólo sin padre; 'no-snapshot' cuando HAY padre pero el
    snapshot no viajó (kill-switch, identidad inválida): no se midió, no se declara 'sin padre'."""
    if not thread_snapshot:
        state = "no-snapshot" if (run or {}).get("parent_run_id") else "no-parent"
        return ({"parent_identifier_leak": [], "parent_identifier_leak_state": state}, None)
    ev_text = json.dumps(_compact_evidence(bundle), ensure_ascii=False, default=str)
    leak = parent_identifier_leak(thread_snapshot, direct_answer, _evidence_ids(bundle), ev_text)
    frag = {"parent_identifier_leak": leak, "parent_identifier_leak_state": "checked",
            "parent_identifier_leak_rule": ("ids in thread_context AND in direct_answer AND absent from the "
                                            "child's evidence_ids + evidence text; patterns: "
                                            + ", ".join(f"{k}={v.pattern}" for k, v in IDENTIFIER_PATTERNS.items()))}
    return frag, [lambda _obj, _report: ("parent_identifier_leak", not leak)]


def _thread_checks_summary(run, thread_snapshot):
    """deterministic_checks.thread para el PANEL: resumen sin prosa — el panel sabe que hubo turno previo,
    no lee su texto (la evidencia que recibe va LIMPIA)."""
    parent = (thread_snapshot or {}).get("parent") or {}
    return {"thread_id": run.get("thread_id"), "turn_no": run.get("turn_no"),
            "turn_kind": run.get("turn_kind"), "parent_run_id": run.get("parent_run_id"),
            "parent_run_no": parent.get("run_no"), "parent_verdict": parent.get("verdict"),
            "context_available": thread_snapshot is not None}


# (G) Ejes del episodio — DERIVADOS AL CONGELAR (clase 'derived-at-freeze') por TABLA, jamás un enum único
# que mezcle mundo, inferencia y técnica. La tabla vive aquí y en el ADR; el registro cita la regla.
EPISODE_AXES_MAP = {
    "class": "derived-at-freeze",
    "world": {
        "rule": "decision_state.state × answer.absence_kind × audit.verdict",
        "AUDIT_APPROVED × not-applicable": "effect-claimed",
        "AUDIT_APPROVED × evidence-of-no-effect": "null-bounded",
        "AUDIT_APPROVED × no-evidence-retrieved": "indeterminate",
        "AUDIT_APPROVED × <absence_kind absent>": "indeterminate (declared: absence_kind absent)",
        "AUDIT_REJECTED": "not-established",
        # corrector ADR-0079: la PRECEDENCIA es la del código — sin veredicto manda sobre decision_state
        # (un AUDIT_REJECTED sin veredicto sale not-assessed), y un veredicto sobre un decision_state no
        # terminal de auditoría también cae a not-assessed (declarado en notes).
        "<no audit verdict> (precede a decision_state)": "not-assessed",
        "<verdict present> × decision_state ∉ {AUDIT_APPROVED, AUDIT_REJECTED}": "not-assessed (declared in notes)",
    },
    "inference": {"rule": "audit.verdict", "APPROVE": "supported", "APPROVE_MINOR": "minor-issues",
                  "APPROVE_DECLINE": "honest-decline", "REVISE": "insufficient", "<none>": "not-evaluated"},
    "technical": {"rule": "run.state × retrieval_summary.mode",
                  "awaiting_closure|closed × semantic": "completed",
                  "awaiting_closure|closed × <mode != semantic>": "degraded",
                  "failed": "failed", "cancelled": "cancelled"},
    "provenance": {"rule": "origin + human_gates {plan_declared, closed} + turn {thread_id, turn_no, turn_kind}"},
}


def episode_axes(decision_state, absence_kind, verdict, run_state, retrieval_mode, origin,
                 plan_declared, closed, thread):
    """(G) Los cuatro ejes del episodio según EPISODE_AXES_MAP. Puro y determinista."""
    notes = []
    if verdict is None:
        world, inference = "not-assessed", "not-evaluated"
    else:
        inference = {"APPROVE": "supported", "APPROVE_MINOR": "minor-issues",
                     "APPROVE_DECLINE": "honest-decline", "REVISE": "insufficient"}.get(verdict)
        if inference is None:
            inference = "not-evaluated"
            notes.append(f"verdict '{verdict}' fuera del vocabulario — inference not-evaluated (declarado)")
        if decision_state == "AUDIT_APPROVED":
            world = {"not-applicable": "effect-claimed", "evidence-of-no-effect": "null-bounded",
                     "no-evidence-retrieved": "indeterminate"}.get(absence_kind)
            if world is None:
                world = "indeterminate"
                notes.append(f"absence_kind {absence_kind!r} ausente/fuera del enum → world indeterminate (declarado)")
        elif decision_state == "AUDIT_REJECTED":
            world = "not-established"
        else:
            world = "not-assessed"
            notes.append(f"decision_state {decision_state!r} no es terminal de auditoría → world not-assessed")
    if run_state in ("failed", "cancelled"):
        technical = run_state
    elif run_state in ("awaiting_closure", "closed"):
        technical = "completed" if retrieval_mode == "semantic" else "degraded"
        if technical == "degraded":
            notes.append(f"retrieval_summary.mode={retrieval_mode!r} ≠ semantic → technical degraded")
    else:
        technical = "degraded"
        notes.append(f"run.state {run_state!r} no terminal al derivar → technical degraded (declarado)")
    return {"class": EPISODE_AXES_MAP["class"], "world": world, "inference": inference,
            "technical": technical,
            "provenance": {"origin": origin,
                           "human_gates": {"plan_declared": bool(plan_declared), "closed": bool(closed),
                                           "closed_note": ("at-freeze value: closure happens AFTER the freeze "
                                                           "and lives in frozen_at/closed_by")},
                           "turn": {"thread_id": (thread or {}).get("thread_id"),
                                    "turn_no": (thread or {}).get("turn_no"),
                                    "turn_kind": (thread or {}).get("turn_kind")}},
            "map": "runs.EPISODE_AXES_MAP (ADR-0079)", "notes": notes}


def _question_of_run(run_id):
    """question_id del borrador (note_questions) que respalda una corrida, o None. Lectura directa de la
    tabla de db (sin función nueva en db.py); su fallo no bloquea encolar (§6 no-hang)."""
    try:
        from sqlalchemy import select
        with db.engine().begin() as cx:
            row = cx.execute(select(db.note_questions.c.question_id)
                             .where(db.note_questions.c.run_id == run_id)
                             .order_by(db.note_questions.c.created_at.asc())).first()
        return row[0] if row else None
    except Exception:
        return None


def _root_run_no(run):
    """ADR-0079 (T5, integrador): run_no de la RAÍZ de la investigación de `run` — la propia corrida cuando
    thread_id == run_id; si no, la fila thread_id (la raíz, real o VIRTUAL pre-ADR, que conserva su run_no
    aunque sus columnas de investigación sean NULL). None declarado cuando no consta — jamás se infiere."""
    tid = run.get("thread_id")
    if not tid:
        return None
    if tid == run.get("run_id"):
        return run.get("run_no")
    root = db.get_run(tid)
    return root.get("run_no") if root else None


def derive_thread(run_id, question, entities, parent_run_id=None, from_question_id=None, now=None):
    """(B) La derivación de investigación al ENCOLAR (servidor). Devuelve las columnas THREAD_COLUMNS
    (menos origin) + el sobre del contexto. Raíz: thread_id = run_id, turn_no 1, 'root', sobre con
    skipped_reason 'root-turn'. Con padre: 404 ParentNotFound · 409 ParentNotTerminal (state ∉
    RATABLE_STATES) · thread_id = parent.thread_id or parent.run_id (padre pre-ADR = raíz VIRTUAL, se
    declara parent_pre_adr_0079 en el snapshot) · turn_no = max(turno del hilo, 1) + 1 · turn_kind:
    'rerun' (misma pregunta + entities_csv), 'branch' (el padre ya tenía otro hijo), 'refine' (resto) ·
    root_question_id = parent.root_question_id or borrador del padre or None (corrector ADR-0079: en un turno
    con padre JAMÁS se siembra desde el from_question_id del hijo — la llave dice 'raíz' y ese borrador es del
    turno 2..N; el borrador propio ya vive en note_questions.run_id). Kill-switch WITT_THREAD_CONTEXT=0:
    columnas sí, snapshot no (skipped_reason).
    Carreras (corrector ADR-0079): turn_no y turn_kind se derivan FUERA de la transacción del INSERT; dos hijos
    encolados a la vez podrían leer el mismo máximo. El índice ÚNICO (thread_id, turn_no) — db._migrate,
    patrón de run_no — rechaza al segundo y new_run RE-DERIVA (turn_no siguiente; turn_kind vuelve a mirar si
    el padre ya tiene hijos → 'branch'). Nada se corrige en silencio: se re-deriva desde la BD."""
    now = now or db._now()
    entities_csv = ",".join(entities or [])
    if not parent_run_id:
        return {"parent_run_id": None, "thread_id": run_id, "turn_no": 1, "turn_kind": "root",
                "root_question_id": from_question_id,
                "envelope": {"snapshot": None, "skipped_reason": "root-turn",
                             "kill_switch": _kill_switch_view(),
                             "built_at": now.isoformat(timespec="seconds")}}
    parent = db.get_run(parent_run_id)
    if parent is None:
        raise ParentNotFound(parent_run_id)
    if parent.get("state") not in db.RATABLE_STATES:
        raise ParentNotTerminal(parent_run_id, parent.get("state"))
    thread_id = parent.get("thread_id") or parent["run_id"]
    turn_no = max(db.max_turn_no(thread_id) or 0, 1) + 1
    if question == parent.get("question") and entities_csv == (parent.get("entities_csv") or ""):
        turn_kind = "rerun"
    elif db.has_children(parent_run_id):
        turn_kind = "branch"
    else:
        turn_kind = "refine"
    root_question_id = parent.get("root_question_id") or _question_of_run(parent_run_id)
    if _thread_context_enabled():
        envelope = build_thread_context(parent, db.list_run_comments(parent_run_id), now)
    else:
        envelope = {"snapshot": None, "skipped_reason": f"kill-switch {THREAD_CONTEXT_ENV}=0",
                    "kill_switch": _kill_switch_view(), "built_at": now.isoformat(timespec="seconds")}
    if parent.get("thread_id") is None:
        envelope["parent_pre_adr_0079"] = True
    return {"parent_run_id": parent_run_id, "thread_id": thread_id, "turn_no": turn_no,
            "turn_kind": turn_kind, "root_question_id": root_question_id, "envelope": envelope}


def plan_thread_context(parent_run_id):
    """Para POST /runs/plan con parent_run_id (T3): valida al padre igual que new_run (404/409) y devuelve
    el sobre {snapshot, skipped_reason} que build_plan pasa al planner. Kill-switch respetado."""
    parent = db.get_run(parent_run_id)
    if parent is None:
        raise ParentNotFound(parent_run_id)
    if parent.get("state") not in db.RATABLE_STATES:
        raise ParentNotTerminal(parent_run_id, parent.get("state"))
    if not _thread_context_enabled():
        return {"snapshot": None, "skipped_reason": f"kill-switch {THREAD_CONTEXT_ENV}=0",
                "kill_switch": _kill_switch_view(), "parent_run_id": parent_run_id}
    env = build_thread_context(parent, db.list_run_comments(parent_run_id), db._now())
    env["parent_run_id"] = parent_run_id   # corrector ADR-0079: el plan declara QUÉ padre vio (plan↔padre)
    return env


class RunCancelled(Exception):
    pass


# ADR-0078 corrector — la VISTA DE PROMPT del bloque path_b: el modelo lee EVIDENCIA, no bitácora. El
# bloque íntegro (query_builder, throttles, rate_limit_headers, search_ledger anidado por paper, dedup_keys,
# duplicates, cache_age…) se queda en el bundle (identidad sha, runs.bundle_json); al sintetizador y a los
# jueces viaja esta proyección con lista blanca. Un paper lleva UN texto (text_excerpt; el abstract solo
# cuando el excerpt viene del texto completo, porque entonces son textos distintos).
_PROMPT_PATH_B_TOP = ("triggered", "triggered_by", "reason", "ledger_version", "query_sent", "query_sent_scope",
                      "query_source", "epmc_query", "pubmed_query", "zfin_filter", "n_results_by_source",
                      "sources_requested", "n_papers_requested")
_PROMPT_LEDGER_KEYS = ("status", "n_found", "n_found_total", "n_returned", "n_new", "n_candidates",
                       "detail", "error", "ncbi_identity")
_PROMPT_ZFIN_ROW_KEYS = ("symbol", "status", "n_matched", "n_phenotypes_total", "n_phenotypes_total_scope",
                         "anatomy_filter", "detail")
_PROMPT_SELECTION_KEYS = ("rule", "n_requested", "n_candidates", "n_selected", "n_duplicates", "not_selected")
_PROMPT_PAPER_KEYS = ("source", "evidence_id", "search_rec", "selection_rank", "text_provenance",
                      "text_excerpt", "text_excerpt_omitted", "text_excerpt_rule")
_PROMPT_ZFIN_ITEM_KEYS = ("symbol", "curie", "status", "has_references", "anatomy_filter", "n_phenotypes_total",
                          "n_phenotypes_total_scope", "n_matched", "n_returned", "truncated", "phenotypes",
                          "identifier_provenance")


def _prompt_path_b(block):
    """Proyección del bloque path_b para el prompt (ver _PROMPT_* arriba). Conserva los tres estados de cada
    campo que copia (presente / null / ausente) — solo RECORTA llaves, jamás rellena."""
    out = {k: block[k] for k in _PROMPT_PATH_B_TOP if k in block}
    for led in ("europepmc_searched", "pubmed_searched"):
        if isinstance(block.get(led), dict):
            out[led] = {k: block[led][k] for k in _PROMPT_LEDGER_KEYS if k in block[led]}
    if isinstance(block.get("zfin_searched"), list):
        out["zfin_searched"] = [{k: r[k] for k in _PROMPT_ZFIN_ROW_KEYS if k in r} for r in block["zfin_searched"]]
    if isinstance(block.get("selection"), dict):
        out["selection"] = {k: block["selection"][k] for k in _PROMPT_SELECTION_KEYS if k in block["selection"]}
    papers = []
    for it in block.get("papers") or []:
        p = {k: it[k] for k in _PROMPT_PAPER_KEYS if k in it}
        if it.get("text_provenance") == "fulltext-excerpt" and "abstract" in it:
            p["abstract"] = it["abstract"]   # texto distinto del excerpt: los dos aportan
        f = it.get("fetched") or {}
        p["fetched"] = {k: f.get(k) for k in ("found", "full_text") if k in f}
        for k in ("fetch_error", "cache_hit", "cached_at"):
            if k in f:
                p["fetched"][k] = f[k]
        if isinstance(it.get("zfin"), dict):
            z = it["zfin"]
            p["zfin"] = {k: z[k] for k in _PROMPT_ZFIN_ITEM_KEYS if k in z}
        papers.append(p)
    if "papers" in block:
        out["papers"] = papers
    return out


def _compact_evidence(bundle, include_path_b=True):
    """The evidence view handed to the synthesizer and the panel — compact, never the raw 100K bundle.
    include_path_b=False is the PASS-1 view (DI-only): pass-1 confidence measures 'is my store enough?'
    even when structural insufficiency already fetched external papers (ADR-0051).
    ADR-0078 corrector: path_b viaja PROYECTADO (_prompt_path_b) — evidencia y estados por fuente, sin la
    plomería diagnóstica del ledger v2 (que sigue íntegra en el bundle)."""
    ev = {
        "path_a_hits": [{"doc_id": h["doc_id"], "type": h["type"], "score": h["score"], "text": h["text"]}
                        for h in bundle["path_a"]["hits"]],
        "retrieval": bundle["path_a"]["retrieval"],
        "entities_checked": bundle["entities_checked"],
        "sufficiency": bundle["sufficiency"],
    }
    if include_path_b:
        ev["path_b"] = _prompt_path_b(bundle["path_b"])
    else:
        ev["path_b"] = {"included": False, "note": "pass-1 view is DI-only by design (ADR-0051)"}
    return ev


def _evidence_ids(bundle):
    """The ids the audit's approved/rejected lists key on. `evidence_id` (set by path_b for every source)
    is preferred: a multi-source Path B where several items fall back to the literal "paper" collapses
    distinct evidence into one key, and the panel's verdict then lands on the wrong item."""
    ids = [h["doc_id"] for h in bundle["path_a"]["hits"]]
    for p in bundle["path_b"].get("papers", []):
        if p.get("evidence_id"):
            ids.append(p["evidence_id"])
            continue
        rec = p.get("search_rec", {})
        ids.append(f"PMID:{rec['pmid']}" if rec.get("pmid") else (rec.get("pmcid") or rec.get("doi") or "paper"))
    return ids


# ADR-0079 — la cláusula anti-fuga del sistema de síntesis. Va en synth_system (cuando hay turno anterior)
# Y en SYNTH_TOOL.description (siempre): el turno anterior es PRECEDENTE, no evidencia.
THREAD_ANTI_LEAK_CLAUSE = ("The previous turn (thread_context) is PRIOR ART, not evidence; never cite or "
                           "reuse an identifier from it unless it appears in evidence. Use it only to "
                           "understand what was asked before, what was missing (gap_flags) and what the "
                           "humans commented — then answer THIS question from THIS evidence.")


def synth_system(pass_label, thread_context=False):
    """The EXACT production system prompt of a synthesis pass — factored out so diagnostics
    (evaluation/scripts/ab_trapped_scalar.py) measure against the real string, never a replica.

    ADR-0079: `thread_context=True` añade la cláusula anti-fuga (THREAD_ANTI_LEAK_CLAUSE). Sin turno
    anterior el string es EXACTAMENTE el de antes — la medición de ab_trapped_scalar no cambia."""
    return ("You answer zebrafish pronephros research questions for a medical team, from a curated "
            "evidence bundle (DATA INAMOVIBLE"
            + ("" if pass_label == "pass1" else " + externally fetched literature") + "). "
            "Use ONLY the provided evidence. Be direct; keep confidence honest (thin evidence means "
            "LOW confidence + explicit gap_flags); when sub-claims have asymmetric evidence strength, "
            "report confidence_by_subclaim instead of averaging. If your answer rests on an absence, "
            "declare absence_kind precisely. Technical identifiers stay in English; never assert an "
            "identifier that is not in the evidence."
            + (" " + THREAD_ANTI_LEAK_CLAUSE if thread_context else "") + "\n\n"
            # §4 exige citar la sección ESPECÍFICA del catálogo con su criterio. Un criterio no se
            # puede citar de un archivo que el modelo nunca vio: sin este digest, pedir la cita
            # fabrica números de sección, que es peor que no pedir nada.
            + reasoning_catalog.digest()
            + "\n\nAlso report alternatives_considered (§5): the readings you rejected and why.")


def _lista_serializada(raw, keep_dicts=False):
    """ADR-0074: un campo-lista que llegó como STRING — atrapado como texto y levantado crudo
    (ADR-0057), o emitido como string por el modelo (la API no valida tipos del schema). String
    JSON de lista -> la lista (ítems no-string se re-serializan legibles); cualquier otra cosa ->
    None, y el llamador conserva el crudo DECLARADO — jamás lo corrige, jamás lo rellena.

    ADR-0078: `keep_dicts=True` conserva los ítems dict tal cual — evidence_cited es una lista de
    citas TIPADAS ({kind, id, note}) y re-serializarlas a string las degradaría a kind='other' con
    el JSON como id (una cita sin tipo ni id legible: pérdida silenciosa)."""
    if not isinstance(raw, str):
        return None
    try:
        v = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(v, list):
        return None
    return [x if isinstance(x, str) or (keep_dicts and isinstance(x, dict))
            else json.dumps(x, ensure_ascii=False) for x in v]


def _default_synthesizer(question, evidence, pass_label, thread_context=None):
    """One synthesis pass over an evidence view (pass1 = DI-only, pass2 = DI + Path B). Returns
    {direct_answer, stated_confidence, confidence_by_subclaim, absence_kind, gap_flags,
    evidence_cited, model, usage}.

    ADR-0079: `thread_context` (snapshot del turno anterior) viaja como LLAVE HERMANA de evidence en el
    user_text — {question, evidence, thread_context} — nunca dentro de evidence (patrón revision_input).
    Con snapshot, el system gana la cláusula anti-fuga. None = raíz: prompt idéntico al de siempre."""
    system = synth_system(pass_label, thread_context=thread_context is not None)
    payload = {"question": question, "evidence": evidence}
    if thread_context is not None:
        payload["thread_context"] = thread_context
    user_text = json.dumps(payload, ensure_ascii=False, default=str)
    # ADR-0081 (A/C.4): el rol se resuelve EN LA LLAMADA (tabla + env, con fuente), el tope es el de la generación
    # (g2 8000: opus-5 piensa por default y max_tokens acota pensamiento + respuesta; g1 2500 = f57a3d3) y el effort
    # (WITT_ANTHROPIC_EFFORT) viaja como output_config SÓLO a modelos adaptativos. return_meta: lo que la API DIJO.
    role = models.resolve_role("synthesizer")
    effort, effort_source = _effort_for(role["model"])
    out, usage, meta = _anthropic_call(role["model"], system, user_text, SYNTH_TOOL,
                                       _max_tokens_for(role, "synthesizer"), effort)
    # ADR-0074 (corrida real 9b3140ab): los campos-lista pueden llegar SERIALIZADOS como string.
    # Un string aquí JAMÁS se explota en caracteres (list(str) congeló gap_flags como chars) ni se
    # rellena con []: se parsea con procedencia declarada, o se conserva crudo como UN elemento.
    gap_crudo = out.get("gap_flags", [])
    if isinstance(gap_crudo, str):
        gap_parseado = _lista_serializada(gap_crudo)
        gap_flags = gap_parseado if gap_parseado is not None else [gap_crudo]
        gap_flags.append(
            f"gap_flags llegó SERIALIZADO como string en {pass_label} y se "
            + ("parseó" if gap_parseado is not None else "conserva crudo (no era JSON de lista)")
            + " — procedencia declarada (ADR-0074)")
    else:
        gap_flags = list(gap_crudo or [])
    recovered = out.get("_recovered_fields", [])
    inline_conf = out.get("confidence")
    if "confidence" in recovered:
        # ADR-0057: el escalar in-line llegó ATRAPADO como texto (medido ~50-60% de llamadas); la
        # recuperación lo levanta con procedencia. Desde ADR-0065 es el CROSS-CHECK, no la medición.
        gap_flags.append(f"in-line confidence RECOVERED from a malformed tool call in {pass_label} "
                         "(serialization artifact stripped from direct_answer) — kept as cross-check; "
                         "the elicited scalar governs (ADR-0065)")
    # ADR-0065: la elicitación dedicada es la medición autoritativa del escalar. Su fallo NUNCA
    # bloquea (§6 no-hang): se cae al camino in-line/recovered de ADR-0057, con la procedencia de ese
    # camino, y se declara.
    e_role = models.resolve_role("elicitation")   # lo PEDIDO se declara aunque la llamada falle (ADR-0081 B)
    try:
        elicited, e_subs, e_usage, e_meta = _elicit_confidence(question, evidence, out["direct_answer"],
                                                               gap_flags, pass_label)
    except Exception as e:
        elicited, e_subs, e_usage, e_meta = None, None, None, {}
        gap_flags.append(f"confidence elicitation FAILED in {pass_label} "
                         f"({type(e).__name__}: {str(e)[:80]}) — falling back to the in-line scalar "
                         "(§6 no-hang)")
    if e_usage:
        mi, mo = _usage_in_out(usage)
        ei, eo = _usage_in_out(e_usage)
        usage = {"input_tokens": mi + ei, "output_tokens": mo + eo}   # M8 cuadra: el gasto se fusiona
    if elicited is not None:
        conf = elicited
        conf_source = "stated-second-elicitation"
        if isinstance(inline_conf, (int, float)) and abs(elicited - inline_conf) > 0.15:
            gap_flags.append(f"confidence cross-check divergence in {pass_label}: elicited {elicited} "
                             f"vs in-line {inline_conf}"
                             + (" (in-line itself recovered)" if "confidence" in recovered else "")
                             + " — declared; the elicited value governs (ADR-0065)")
    elif inline_conf is not None:
        conf = inline_conf
        conf_source = ("recovered-from-malformed-tool-call" if "confidence" in recovered else "stated")
    elif out.get("confidence_by_subclaim"):
        conf, conf_source = None, None   # runs.py derives min-of-subclaims (declared) — §5 allows the OR
    else:
        conf, conf_source = None, None
        gap_flags.append(f"stated_confidence ABSENT in {pass_label} (in-line omitted after retry AND "
                         "elicitation unavailable) — not calibratable")
    if not out.get("framework_applied"):
        gap_flags.append(f"framework_applied AUSENTE en {pass_label} (§4 lo exige) — no se inventa: "
                         "el registro lo declara ausente")
    # ADR-0074: la lista del §5 serializada como string se normaliza ANTES de congelar
    alts = out.get("alternatives_considered")
    if isinstance(alts, str):
        alts_parseadas = _lista_serializada(alts)
        if alts_parseadas is not None:
            alts = alts_parseadas
            gap_flags.append(f"alternatives_considered llegó SERIALIZADA como string en {pass_label} "
                             "y se parseó — procedencia declarada, no una emisión limpia (ADR-0074)")
        else:
            alts = [alts]
            gap_flags.append(f"alternatives_considered llegó como string NO parseable en {pass_label} "
                             "— se conserva cruda como un elemento, declarada (ADR-0074)")
    if not alts:
        gap_flags.append(f"alternatives_considered AUSENTE en {pass_label} (§5 lo exige) — declarado, "
                         "no rellenado con una lista vacía que se leería como 'no había alternativas'")
    # ADR-0078 (misma lesión que gap_flags en ADR-0074, ahora en las citas): evidence_cited puede llegar
    # SERIALIZADO como string. Iterarlo tal cual lo explota en N citas de UN carácter (medido: 469
    # pseudocitas en una corrida real). Aquí se re-parsea con procedencia — el crudo se conserva en
    # evidence_cited_raw — y si no es JSON de lista se deja el string para que _normalize_citations lo
    # DECLARE 'string-unparseable' (jamás se rellena con [] callado ni se itera por caracteres).
    ev_crudo = out.get("evidence_cited")   # None = la llave NO vino (ausente ≠ [] — ADR-0078 corrector)
    ev_raw = None
    if ev_crudo is None:
        gap_flags.append(f"evidence_cited AUSENTE en {pass_label} — declarado, no rellenado con [] "
                         "(citations_schema.source 'absent'; ADR-0078)")
    if isinstance(ev_crudo, str):
        ev_raw = ev_crudo
        ev_parseado = _lista_serializada(ev_crudo, keep_dicts=True)
        if ev_parseado is not None:
            ev_crudo = ev_parseado
            gap_flags.append(f"evidence_cited llegó SERIALIZADO como string en {pass_label} y se parseó "
                             f"({len(ev_parseado)} citas) — procedencia declarada, crudo conservado en "
                             "evidence_cited_raw (ADR-0078)")
        else:
            gap_flags.append(f"evidence_cited llegó como string NO parseable en {pass_label} — se "
                             "conserva crudo en evidence_cited_raw; las citas quedan declaradas "
                             "'string-unparseable', no se inventan (ADR-0078)")
    return {"direct_answer": out["direct_answer"], "stated_confidence": conf,
            "confidence_source": conf_source,
            # ADR-0080 (F): el gasto de la elicitación viaja APARTE (usage sigue siendo la suma — M8 cuadra);
            # runs._token_usage lo reparte en by_stage.{synthesize_*, elicit_*}. Tres estados declarados.
            "usage_elicitation": e_usage,
            "elicitation_state": ("elicited" if elicited is not None
                                  else "failed" if e_usage is None else "elicited-out-of-range"),
            "stated_confidence_inline": inline_conf,   # el instrumento previo persiste (continuidad)
            "confidence_by_subclaim": e_subs or out.get("confidence_by_subclaim"),
            "absence_kind": out.get("absence_kind"),
            "search_query_en": out.get("search_query_en"),
            "gap_flags": gap_flags, "evidence_cited": ev_crudo,   # None cuando el modelo no la emitió
            "evidence_cited_raw": ev_raw,   # ADR-0078: el string tal cual llegó; None = NO llegó string
            # contrato §5 (ADR-0060): self-report del modelo; runs.py resuelve sección/tier por tabla
            "alternatives_considered": alts,
            "framework_applied": out.get("framework_applied"),
            "framework_criterion": out.get("framework_criterion"),
            "framework_reason": out.get("framework_reason"),
            # ADR-0081 (B): procedencia MEDIDA — `model` es lo PEDIDO (resuelto por tabla/env con su fuente),
            # `model_reported` lo que la API devolvió (None con un stub o un caller anterior a (C)), `relation` la
            # comparación (exact | prefix NEUTRO | different | not-reported). La elicitación lleva las suyas.
            "model": role["model"], "model_source": role["source"],
            "model_reported": meta.get("model_reported"),
            "relation": models.relation(role["model"], meta.get("model_reported")),
            "effort": effort, "effort_source": effort_source, "effort_delivered": meta.get("effort_delivered"),
            "elicitation_model": e_role["model"], "elicitation_model_source": e_role["source"],
            "elicitation_model_reported": e_meta.get("model_reported"),
            "elicitation_relation": models.relation(e_role["model"], e_meta.get("model_reported")),
            "elicitation_effort": e_meta.get("effort"), "elicitation_effort_source": e_meta.get("effort_source"),
            "usage": usage}


def _resolve_confidence(answer):
    """(value, source) for the fallback gate and the record. §5's own contract is `confidence OR
    confidence_by_subclaim`: when the model honestly refuses one scalar over asymmetric sub-claims
    (the run-99986dbb hypothesis) but emits by_subclaim, we DERIVE min-of-subclaims — worst-of, the
    house aggregation rule, conservative for the never-stopper gate — and DECLARE the derivation."""
    conf = answer.get("stated_confidence")
    if conf is not None:
        return conf, (answer.get("confidence_source") or "stated")
    subs = answer.get("confidence_by_subclaim") or {}
    vals = [v for v in subs.values() if isinstance(v, (int, float))]
    if vals:
        return round(min(vals), 4), "derived-min-of-subclaims"
    return None, None


CITATIONS_SCHEMA_SOURCES = ("list", "string-reparsed", "string-unparseable", "absent",
                            "unsupported-type")


def _normalize_citations(items, with_schema=False):
    """Typed, numerically indexed citation series (ADR-0051). Numbers are EVIDENCE; the letter series
    is reserved for precedent (block 6) so the two can never be conflated by construction.

    ADR-0078: un STRING jamás se itera — `for c in "abc"` producía N pseudocitas de un carácter
    (469 en una corrida real). Un string se re-parsea vía _lista_serializada (JSON de lista -> citas,
    'string-reparsed'); si no es JSON de lista -> [] y se DECLARA 'string-unparseable'. Con
    with_schema=True devuelve (citas, citations_schema) donde citations_schema =
    {source: 'list'|'string-reparsed'|'string-unparseable'|'absent'|'unsupported-type',
     n_raw: ítems recibidos, n_valid: citas con id no vacío} — tres estados: ausente (None) ≠ []
    ≠ lista con citas. Sin with_schema el retorno sigue siendo la lista (compatibilidad)."""
    schema = {"source": None, "n_raw": 0, "n_valid": 0}
    if items is None:
        schema["source"], seq = "absent", []
    elif isinstance(items, str):
        parsed = _lista_serializada(items, keep_dicts=True)
        if parsed is None:
            schema["source"], seq = "string-unparseable", []
            schema["n_raw"] = 1   # UN string opaco recibido, cero citas derivables
            schema["raw_len_chars"] = len(items)
            schema["note"] = ("evidence_cited llegó como string que no es JSON de lista; NO se itera "
                              "por caracteres ni se inventa una cita (ADR-0078)")
        else:
            schema["source"], seq = "string-reparsed", parsed
    elif isinstance(items, (list, tuple)):
        schema["source"], seq = "list", list(items)
    else:
        schema["source"], seq = "unsupported-type", []
        schema["n_raw"] = 1
        schema["raw_type"] = type(items).__name__
        schema["note"] = "evidence_cited llegó con un tipo que no es lista ni string — declarado, no forzado"
    if seq:
        schema["n_raw"] = len(seq)
    out = []
    for i, c in enumerate(seq, 1):
        if isinstance(c, dict):
            out.append({"n": i, "kind": c.get("kind", "other"), "id": str(c.get("id", "")),
                        "note": c.get("note", "")})
        else:
            out.append({"n": i, "kind": "other", "id": str(c), "note": ""})
    schema["n_valid"] = sum(1 for c in out if c["id"])
    return (out, schema) if with_schema else out


# Per-Mtok prices for the cost PROJECTION (input, output). These are projection INPUTS, not
# measurements — the token counts are measured from API responses; the dollar figure is calculated
# and labeled as such (measurement-class discipline, ADR 2026-07-13).
# ADR-0078: sonnet-5 cobraba (3.0, 15.0) y vale (2.0, 10.0); entran los modelos del consejo. Un modelo
# que NO está en la tabla NO se cotiza a 0 (eso disfrazaba un hueco de precio como gasto cero): se
# declara en missing_price_models y cost_projection_complete=False (ver _token_usage).
# ADR-0081 (A): la tabla de precios vive en lib/models.py (una fila por modelo, con verified_on/source); aquí se
# CONSERVAN los nombres (app.usage y los smokes los leen) como alias derivados — prices() == el dict de f57a3d3
# (golden en smoke_models.py), PRICES_AS_OF el mismo literal.
PRICES_PER_MTOK_USD = models.prices()
PRICES_AS_OF = models.PRICES_AS_OF


def _usage_in_out(usage):
    """Normalize Anthropic (input_tokens/output_tokens) and OpenAI (prompt_tokens/completion_tokens)."""
    u = usage or {}
    return (int(u.get("input_tokens") or u.get("prompt_tokens") or 0),
            int(u.get("output_tokens") or u.get("completion_tokens") or 0))


TOKEN_STAGES = ("plan", "synthesize_pass1", "elicit_pass1", "search", "synthesize_pass2", "elicit_pass2",
                "panel", "revision", "embed")
_PASS_STAGE = {"pass1": ("synthesize_pass1", "elicit_pass1"), "pass2": ("synthesize_pass2", "elicit_pass2"),
               "revision": ("revision", "revision")}   # la elicitación de la revisión se atribuye a 'revision'


def _usage_by_stage(passes, planner_meta, audit_result, embed_tokens, plan_declared=False):
    """ADR-0080 (F): reparto del gasto MEDIDO por etapa. Insumos: cada pasada trae `usage` (síntesis +
    elicitación fusionadas — M8) y, desde ADR-0080, `usage_elicitation` aparte: la etapa synthesize_* es la
    resta y elicit_* la parte. Un sintetizador que no separa (stub, firma vieja) deja elicit_* con in/out null
    + state 'not-separable' — no se inventa un 0 — y todo su gasto va a synthesize_*. `search` no gasta modelo
    (tools Layer 0): 0 medido con nota. `_sum` es la suma sobre las etapas de MODELO (embed aparte).
    Corrector ADR-0080: `plan` distingue TRES estados — medido (planner con usage), `plan-without-usage`
    (plan declarado pero el planner no reportó gasto: in/out null, no 0) y `no-plan`; y el panel cuenta el gasto
    de TODA fila con `usage` medido, incluida la de un juez agotado (`errored`) cuyos intentos cobraron —
    composite_auditor lo suma en audit.usage y M8 debe cuadrar contra el mismo número."""
    stages = {s: {"in": 0, "out": 0} for s in TOKEN_STAGES if s != "embed"}
    stages["search"]["note"] = "Layer 0 tools — no model call (ADR-0080)"
    stages["elicit_pass1"] = {"in": None, "out": None, "state": "not-run"}
    stages["elicit_pass2"] = {"in": None, "out": None, "state": "not-run"}
    for label, p in passes:
        synth_stage, elicit_stage = _PASS_STAGE.get(label, ("revision", "revision"))
        ti, to = _usage_in_out(p.get("usage"))
        e_usage = p.get("usage_elicitation")
        if "usage_elicitation" in p and isinstance(e_usage, dict):
            ei, eo = _usage_in_out(e_usage)
            ei, eo = min(ei, ti), min(eo, to)   # la parte jamás excede la suma fusionada
            if elicit_stage == synth_stage:
                stages[synth_stage]["in"] += ti
                stages[synth_stage]["out"] += to
            else:
                stages[synth_stage]["in"] += ti - ei
                stages[synth_stage]["out"] += to - eo
                stages[elicit_stage] = {"in": ei, "out": eo, "state": "measured",
                                        # ADR-0081 (corrector): el modelo RESUELTO de la elicitación — SÓLO el que el
                                        # wrapper escribió en `elicitation_model`; un stub sin él deja null declarado.
                                        # Antes caía a p['model'] (el sintetizador) y la etapa afirmaba que corrió el
                                        # modelo de síntesis: una constante copiada al lugar de lo medido (§7).
                                        "model": p.get("elicitation_model")}
                if "elicitation_model_source" in p:
                    stages[elicit_stage]["model_source"] = p.get("elicitation_model_source")
        else:
            stages[synth_stage]["in"] += ti
            stages[synth_stage]["out"] += to
            if elicit_stage != synth_stage:
                stages[elicit_stage] = {"in": None, "out": None,
                                        "state": ("not-separable (synthesizer did not report usage_elicitation)"
                                                  if "usage_elicitation" not in p else "elicitation-failed")}
        if synth_stage in ("synthesize_pass1", "synthesize_pass2", "revision"):
            # ADR-0081: el modelo de la PASADA (resuelto por el wrapper); null declarado si la pasada no lo trae
            stages[synth_stage]["model"] = p.get("model")
            if "model_source" in p:
                stages[synth_stage]["model_source"] = p.get("model_source")
    if planner_meta and planner_meta.get("usage"):
        pi, po = _usage_in_out(planner_meta.get("usage"))
        stages["plan"] = {"in": pi, "out": po, "model": planner_meta.get("model")}
        if "model_source" in planner_meta:
            stages["plan"]["model_source"] = planner_meta.get("model_source")
    elif plan_declared:
        stages["plan"] = {"in": None, "out": None, "state": "plan-without-usage (planner reported no usage)",
                          "model": (planner_meta or {}).get("model")}
    else:
        stages["plan"] = {"in": 0, "out": 0, "state": "no-plan"}
    # ADR-0081 (H): el panel también por REVIEWER — opus-5 es sintetizador Y juez correctness; sólo la partición
    # etapa×modelo los separa en /usage. Σ by_model == panel.in/out por construcción (mismas filas, misma suma).
    stages["panel"]["by_model"] = {}
    for row in audit_result.get("panel", []):
        if isinstance(row.get("usage"), dict) and row["usage"]:
            i, o = _usage_in_out(row["usage"])
            stages["panel"]["in"] += i
            stages["panel"]["out"] += o
            m = stages["panel"]["by_model"].setdefault(row.get("reviewer") or "unknown-reviewer", {"in": 0, "out": 0})
            m["in"] += i
            m["out"] += o
    stages["embed"] = {"tokens": embed_tokens, "unit": "embedding tokens (not chat tokens; excluded from _sum)"}
    stages["_sum"] = {"in": sum(v["in"] for k, v in stages.items() if k != "embed" and isinstance(v.get("in"), int)),
                      "out": sum(v["out"] for k, v in stages.items() if k != "embed" and isinstance(v.get("out"), int)),
                      "rule": "sum over model stages (embed excluded); must equal by_model totals"}
    return stages


def _token_usage(passes, audit_result, embed_tokens, plan=None):
    """TokenUsage (UI contract, ADR-0051): measured token counts by model + a LABELED cost projection.
    `passes` = [(label, answer_dict)] for the synthesis passes that ran.

    `plan` (ADR-0061): el planner es una llamada de modelo y GASTA. Dejarla fuera haría que M8 no
    cuadre — misma disciplina que LOTE-01·A4 (lo gastado antes de morir sobrevive). El gasto del plan
    se atribuye al modelo que lo hizo y se declara aparte en `plan_judgment`."""
    by_model = {}

    def _add(model, usage):
        i, o = _usage_in_out(usage)
        m = by_model.setdefault(model, {"in": 0, "out": 0})
        m["in"] += i
        m["out"] += o

    # ADR-0081: el gasto se atribuye al modelo RESUELTO de cada pasada (el wrapper lo escribe); una pasada sin `model`
    # (stub) cae a 'unknown-model' declarado (mismo patrón que 'unknown-reviewer') — jamás a una constante copiada.
    for _label, p in passes:
        _add(p.get("model") or "unknown-model", p.get("usage"))
    planner_meta = ((plan or {}).get("judgment") or {}).get("planner") or {}
    planner_usage = planner_meta.get("usage") or {}
    if planner_usage:
        _add(planner_meta.get("model") or "unknown-model", planner_usage)
    for row in audit_result.get("panel", []):
        # corrector ADR-0080: un juez agotado (`errored`) cuyos intentos cobraron trae `usage` medido; entra a
        # by_model bajo su reviewer (composite_auditor ya lo suma en audit.usage — M8 cuadra contra ese número)
        if isinstance(row.get("usage"), dict) and row["usage"]:
            _add(row.get("reviewer") or "unknown-reviewer", row["usage"])
    embed_model, _embed_src = models.embed_model()   # ADR-0081: OPENAI_EMBED_MODEL o la fila `embed` de la tabla
    # ADR-0078: un modelo sin precio en la tabla NO se cotiza a 0 — se EXCLUYE de la proyección y se
    # declara en missing_price_models; cost_projection_complete dice si el número cubre todo el gasto.
    cost = 0.0
    missing = []
    for model, m in by_model.items():
        if model not in PRICES_PER_MTOK_USD:
            missing.append(model)
            continue
        pi, po = PRICES_PER_MTOK_USD[model]
        cost += (m["in"] * pi + m["out"] * po) / 1e6
    if embed_tokens:
        if embed_model in PRICES_PER_MTOK_USD:
            cost += embed_tokens * PRICES_PER_MTOK_USD[embed_model][0] / 1e6
        else:
            missing.append(embed_model)
    pi, po = _usage_in_out(planner_usage)
    by_stage = _usage_by_stage(passes, planner_meta or None, audit_result, embed_tokens,
                               plan_declared=plan is not None)
    total_in, total_out = sum(m["in"] for m in by_model.values()), sum(m["out"] for m in by_model.values())
    return {
        "input_tokens": total_in,
        "output_tokens": total_out,
        "by_model": by_model,
        # ADR-0080 (F): el MISMO gasto repartido por ETAPA (plan, synthesize_pass1, elicit_pass1, search,
        # synthesize_pass2, elicit_pass2, panel, revision, embed). suma(by_stage) == by_model total — el check
        # viaja con el dato; embed se cuenta aparte (tokens de embedding, no tokens de modelo de chat).
        "by_stage": by_stage,
        "by_stage_sum_matches_by_model": (by_stage["_sum"]["in"] == total_in
                                          and by_stage["_sum"]["out"] == total_out),
        # el gasto del plan va DENTRO del total (M8 cuadra) y ADEMÁS aparte, para que se pueda
        # responder "¿cuánto cuesta declarar un plan?" sin re-derivarlo
        "plan_judgment": ({"model": planner_meta.get("model"), "in": pi, "out": po}
                          if planner_usage else None),
        "embedding": {"model": embed_model, "total_tokens": embed_tokens,
                      "attribution": "process-wide window during this run (concurrent runs may overlap)"},
        "estimated_cost_usd": round(cost, 4),
        # ADR-0078: modelos con gasto medido pero SIN precio en la tabla — excluidos del número de arriba
        "missing_price_models": missing,
        "cost_projection_complete": not missing,
        "cost_class": f"PROJECTION (calculated from measured tokens x per-Mtok prices as of "
                      f"{PRICES_AS_OF}; the token counts are measurements, the dollars are not"
                      + ("" if not missing else
                         f"; INCOMPLETE — sin precio para {missing}, excluidos") + ")",
    }


def _embed_usage_snapshot():
    try:
        sys.path.insert(0, str(ROOT / "rag_index" / "graphrag"))
        import embeddings as _emb
        return _emb.usage_snapshot()["total_tokens"]
    except Exception:
        return 0


# --- ADR-0080: compuerta de competencia + lazo de búsqueda ----------------------------------------------
# La decisión "¿basta la pasada 1 o se busca afuera?" deja de ser `pass1 < tau` (ADR-0051) y pasa a
# competence.evaluate: una CONJUNCIÓN de componentes deterministas decidida por CÓDIGO (la confianza del
# modelo es UN componente, jamás la decisión). No competente → stage.search.plan + rondas del harness
# (lib/search_harness, rebanada C2) → pass2. Competente → pass1 es la candidata, fallback.trigger null.
# El literal viejo 'confidence' NO desaparece: vive en fb_meta.trigger_legacy (la regla `pass1 < tau` se
# sigue evaluando y declarando) y fb_meta.competence explica quién decidió.
SEARCH_ROUNDS_CAP_DEFAULT = 2                       # WITT_SEARCH_ROUNDS_CAP
SEARCH_ROUND_BUDGET_S_DEFAULT = 120                 # WITT_SEARCH_ROUND_BUDGET_S
SEARCH_DEFAULT_FAMILIES_DEFAULT = "europepmc,pubmed,zfin,alliance_orthologs,zfin_expression"   # WITT_SEARCH_DEFAULT_FAMILIES
# corrector ADR-0080: 'confidence' es literal VÁLIDO de nuevo, pero SÓLO cuando `competence.competent is None`
# (kill-switch WITT_COMPETENCE_GATE=0 o ruta store-consultation): ahí decide la regla legada `pass1 < tau`
# (texto del modelo) y el trigger lo dice con su propio nombre — 'competence' se reserva a la decisión por
# código. fb_meta.trigger_decided_by nombra al decisor en los tres casos.
FALLBACK_TRIGGERS = ("structural", "competence", "confidence", None)
TRIGGER_LEGACY_CONFIDENCE = "confidence"            # el literal pre-ADR-0080 (ADR-0051), conservado como alias declarado
TRIGGER_VOCABULARY = "structural|competence|confidence(only when competence.competent is null)|null (ADR-0080)"
SEARCH_HARNESS_ENV = "WITT_SEARCH_HARNESS"          # 1 (default) | 0 = la Ruta B no competente corre por path_b_bundle SIN plan
CG_CALIBRATION_ORIGINS_ENV = "WITT_CG_CALIBRATION_ORIGINS"   # 'production' (default) | lista CSV | 'all' = sin filtro
CG_CALIBRATION_ORIGINS_DEFAULT = "production"
CG_CALIBRATION_ORIGINS_ALL = "all"                  # literal DECLARADO en la cobertura cuando no hay filtro (jamás null)
# corrector ADR-0080 (paridad webapp 2026-09-15): el vocabulario REAL de search_plan.state / search_ledger.plan_state /
# stage.search.plan.state. ADR-0080 (G) declaraba cuatro literales exactos; el código emite además formas con detalle:
# 'kill-switch <ENV>=0' (compuerta o harness apagados), 'not-applicable (<skipped_reason>)' (ruta store-consultation bajo
# la regla legada), 'error: <tipo>: <msg>' y 'harness-unavailable (<qué faltó>)' en el plan-sobre de _build_search_plan.
# Un lector valida: exacto ∈ SEARCH_PLAN_STATES_EXACT o startswith(alguno de SEARCH_PLAN_STATE_PREFIXES).
SEARCH_PLAN_STATES_EXACT = ("built", "not-requested", "harness-unavailable", "error")
SEARCH_PLAN_STATE_PREFIXES = ("error: ", "kill-switch ", "not-applicable (", "harness-unavailable (")
SEARCH_PLAN_STATE_VOCABULARY = {"exact": list(SEARCH_PLAN_STATES_EXACT), "prefixes": list(SEARCH_PLAN_STATE_PREFIXES),
                                "rule": "state in exact OR state.startswith(prefix) (ADR-0080 G, corrector 2026-09-15)"}


def plan_state_in_vocabulary(state):
    """¿`state` es un literal exacto o empieza con un prefijo declarado? (el predicado que el gate de paridad aplica)."""
    return isinstance(state, str) and (state in SEARCH_PLAN_STATES_EXACT
                                       or any(state.startswith(p) for p in SEARCH_PLAN_STATE_PREFIXES))


def _search_config():
    """Configuración EFECTIVA del lazo de búsqueda con la fuente de cada valor. Corrector ADR-0080: UN solo
    lector — cuando lib/search_harness está en el árbol se delega en sus parsers (budget FLOTANTE, familias en
    minúsculas y sin duplicados), para que search_ledger.config_source y plan.*_source digan lo mismo de la misma
    env; el parser propio (entero, ADR-0078) queda sólo como respaldo `harness-unavailable`."""
    if search_harness is not None and hasattr(search_harness, "resolve_default_families"):
        cap, cap_src = search_harness._env_int_src("WITT_SEARCH_ROUNDS_CAP", search_harness.ROUNDS_CAP_DEFAULT)
        budget, b_src = search_harness._env_float_src("WITT_SEARCH_ROUND_BUDGET_S", search_harness.ROUND_BUDGET_S_DEFAULT)
        fams, f_src = search_harness.resolve_default_families()
        return {"rounds_cap": cap, "rounds_cap_source": cap_src,
                "round_budget_s": budget, "round_budget_s_source": b_src,
                "families_default": list(fams), "families_source": f_src,
                "config_reader": "search_harness"}
    cap, cap_src = _env_int_tolerante("WITT_SEARCH_ROUNDS_CAP", SEARCH_ROUNDS_CAP_DEFAULT)
    budget, b_src = _env_int_tolerante("WITT_SEARCH_ROUND_BUDGET_S", SEARCH_ROUND_BUDGET_S_DEFAULT)
    raw = os.environ.get("WITT_SEARCH_DEFAULT_FAMILIES", "").strip()
    fams = []
    for f in (raw or SEARCH_DEFAULT_FAMILIES_DEFAULT).split(","):
        f = f.strip().lower()
        if f and f not in fams:
            fams.append(f)
    return {"rounds_cap": cap, "rounds_cap_source": cap_src,
            "round_budget_s": budget, "round_budget_s_source": b_src,
            "families_default": fams,
            "families_source": ("env:WITT_SEARCH_DEFAULT_FAMILIES" if raw
                                else "default-unset:WITT_SEARCH_DEFAULT_FAMILIES"),
            "config_reader": "runs (search_harness unavailable)"}


def _search_harness_enabled():
    """(bool, fuente) — WITT_SEARCH_HARNESS (corrector ADR-0080): 0 apaga SÓLO el harness (la compuerta sigue
    decidiendo); la Ruta B no competente corre por path_b_bundle SIN plan, camino ADR-0078 byte a byte."""
    raw = os.environ.get(SEARCH_HARNESS_ENV, "").strip()
    if not raw:
        return True, f"default-unset:{SEARCH_HARNESS_ENV}"
    return raw != "0", f"env:{SEARCH_HARNESS_ENV}"


def _calibration_origins():
    """(include_origins | None, fuente) — WITT_CG_CALIBRATION_ORIGINS (corrector ADR-0080): la cobertura de
    calibración que alimenta la compuerta cuenta por default SÓLO corridas `production` (ADR-0079: smoke /
    simulation / fixture jamás son historia de competencia). CSV tolerante; 'all' | '*' = sin filtro, declarado."""
    raw = os.environ.get(CG_CALIBRATION_ORIGINS_ENV, "").strip()
    if not raw:
        return [CG_CALIBRATION_ORIGINS_DEFAULT], f"default-unset:{CG_CALIBRATION_ORIGINS_ENV}"
    toks = []
    for t in raw.split(","):
        t = t.strip().lower()
        if t and t not in toks:
            toks.append(t)
    if not toks:
        return [CG_CALIBRATION_ORIGINS_DEFAULT], f"default-invalid-env:{CG_CALIBRATION_ORIGINS_ENV}"
    if toks in (["all"], ["*"]):
        return None, f"env:{CG_CALIBRATION_ORIGINS_ENV} (all origins, no filter)"
    return toks, f"env:{CG_CALIBRATION_ORIGINS_ENV}"


def _competence_min_history():
    return _env_int_tolerante(competence.MIN_HISTORY_ENV, competence.MIN_HISTORY_DEFAULT)


def _citations_of(answer):
    """(citations, citations_schema, ev_raw) — UNA sede de re-parseo (ADR-0078 corrector), usada por el gate
    de cada pasada (n_valid para positive_claim_requires_citations) y al congelar."""
    ev_raw = answer.get("evidence_cited_raw")
    if ev_raw is None and isinstance(answer.get("evidence_cited"), str):
        ev_raw = answer["evidence_cited"]
    citations, schema = _normalize_citations(
        ev_raw if isinstance(ev_raw, str) else answer.get("evidence_cited"), with_schema=True)
    return citations, schema, ev_raw


def _positive_claim_check(answer, n_citations_valid, identifier_report=None):
    """(E) positive_claim_requires_citations vive en verify_output (rebanada E). Aquí se cablea SI existe en
    el árbol; si no, se declara 'tool-unavailable' — jamás se re-implementa en runs.py ni se rellena.
    Corrector ADR-0080: el informe de identificadores del MISMO gate (verify_identifiers) viaja al predicado
    cuando su firma lo acepta — una declinación que afirma identificadores resueltos sin citar también dispara.
    Devuelve (fragmento para deterministic_checks, predicado para extra_predicates | None)."""
    fn = getattr(verify_output, "positive_claim_requires_citations", None)
    if fn is None:
        return ({"positive_claim_requires_citations": None,
                 "positive_claim_requires_citations_state":
                     "tool-unavailable (verify_output.positive_claim_requires_citations not in tree — ADR-0080 E)"},
                None)
    try:
        try:
            accepts_report = "identifier_report" in inspect.signature(fn).parameters
        except (TypeError, ValueError):
            accepts_report = False
        res = (fn(answer, n_citations_valid, identifier_report=identifier_report) if accepts_report
               else fn(answer, n_citations_valid))
    except Exception as e:   # el predicado no puede tumbar la corrida (§6 no-hang); se declara
        return ({"positive_claim_requires_citations": None,
                 "positive_claim_requires_citations_state": f"error: {type(e).__name__}: {str(e)[:120]}"}, None)
    if callable(res):
        # la interfaz de verify_output (rebanada E): devuelve el PREDICADO (text_or_obj, report) -> (name, ok)
        # con la evaluación completa colgada en `.evaluation` — se congela tal cual, sin recalcular.
        evaluation = getattr(res, "evaluation", None)
        if not isinstance(evaluation, dict):
            _name, ok = res(None, None)
            evaluation = {"ok": ok}
        return ({"positive_claim_requires_citations": bool(evaluation.get("ok")),
                 "positive_claim_requires_citations_state": "checked",
                 "positive_claim_requires_citations_evaluation": evaluation}, [res])
    ok = bool(res[1]) if isinstance(res, tuple) and len(res) >= 2 else bool(res)
    return ({"positive_claim_requires_citations": ok, "positive_claim_requires_citations_state": "checked",
             "positive_claim_requires_citations_inputs": {"absence_kind": answer.get("absence_kind"),
                                                          "n_citations_valid": n_citations_valid}},
            [lambda _obj, _report: ("positive_claim_requires_citations", ok)])


def _gate(answer, bundle, thread_snapshot, run, pass_no):
    """El gate determinista (verify_output.admissible, clase Logic-LM) sobre UNA pasada: predicados duros
    de identificadores + parent_identifier_leak (ADR-0079) + positive_claim_requires_citations (ADR-0080 E,
    si está en el árbol). ADR-0080 (B): corre ADELANTADO sobre pass1 (su admisibilidad es un componente de
    la compuerta) y de nuevo sobre pass2/revisión. `pass_no` viaja en el payload del evento como ETIQUETA
    ('pass1' | 'pass2' | 'revision' — el mismo vocabulario que usage_raw.passes; corrector ADR-0080: antes
    mezclaba int y str en la misma llave)."""
    leak_frag, leak_preds = _leak_check(thread_snapshot, answer["direct_answer"], bundle, run)
    _cits, schema, _raw = _citations_of(answer)
    # el informe de identificadores se mide UNA vez y alimenta también al predicado de citas (corrector ADR-0080)
    report = verify_output.verify_identifiers(answer["direct_answer"]).as_dict()
    pc_frag, pc_preds = _positive_claim_check(answer, schema.get("n_valid"), identifier_report=report)
    preds = list(leak_preds or []) + list(pc_preds or [])
    adm, reasons = verify_output.admissible({"direct_answer": answer["direct_answer"],
                                             "evidence_cited": answer.get("evidence_cited") or [],
                                             "absence_kind": answer.get("absence_kind")},
                                            extra_predicates=preds or None)
    return {"pass": pass_no, "admissible": adm, "reasons": reasons, "identifier_report": report,
            **leak_frag, **pc_frag,
            # el PANEL sabe que hubo turno previo por este resumen — jamás lee el texto del padre
            "thread": _thread_checks_summary(run, thread_snapshot)}


def _usage_payload(usage, model):
    """payload.usage {in, out, model} de un evento que GASTA (ADR-0080 F). None declarado si no se midió."""
    if not isinstance(usage, dict):
        return None
    i, o = _usage_in_out(usage)
    return {"in": i, "out": o, "model": model}


def _synth_usage_payload(answer):
    """El gasto de la SÍNTESIS sola (usage fusionado menos la elicitación separada, cuando la hay)."""
    ti, to = _usage_in_out(answer.get("usage"))
    e = answer.get("usage_elicitation")
    if isinstance(e, dict):
        ei, eo = _usage_in_out(e)
        ti, to = ti - min(ei, ti), to - min(eo, to)
    if not isinstance(answer.get("usage"), dict):
        return None
    return {"in": ti, "out": to, "model": answer.get("model")}   # ADR-0081: null declarado, jamás una constante


def _elicit_event_payload(answer, pass_no, conf, source):
    return {"pass": pass_no, "stated_confidence": conf, "confidence_source": source,
            "stated_confidence_inline": answer.get("stated_confidence_inline"),
            "elicitation_state": answer.get("elicitation_state") or "not-reported-by-synthesizer",
            # ADR-0081 (corrector): el modelo de la elicitación jamás se copia del sintetizador — null declarado si falta
            "usage": _usage_payload(answer.get("usage_elicitation"), answer.get("elicitation_model"))}


def _build_search_plan(question, entities, pass1_query_en, cfg):
    """(C) El plan de búsqueda lo arma search_harness.build_search_plan (rebanada C2). Sin el módulo en el
    árbol se devuelve un plan-sobre DECLARADO (state 'harness-unavailable') para que el registro diga qué
    faltó; nada se inventa. Devuelve (plan, state)."""
    if search_harness is None or not hasattr(search_harness, "build_search_plan"):
        return ({"plan_version": None, "rounds_cap": cfg["rounds_cap"], "families": list(cfg["families_default"]),
                 "queries": None, "directives": [], "source": "default-families",
                 "state": "harness-unavailable (lib.search_harness not in tree — ADR-0080 C2)"},
                "harness-unavailable")
    try:
        # families=None: el harness resuelve WITT_SEARCH_DEFAULT_FAMILIES (con su fuente declarada) y deja fuera
        # las familias gate 'directive-only' hasta que haya directivas del consejo (ADR-0082)
        plan = search_harness.build_search_plan(question, entities, pass1_query_en, directives=None,
                                                families=None)
        plan.setdefault("rounds_cap", cfg["rounds_cap"])
        return plan, "built"
    except Exception as e:   # §6 no-hang: un plan que falla deja fila 'error' y la Ruta B corre por el camino de hoy
        return ({"plan_version": None, "rounds_cap": cfg["rounds_cap"], "families": list(cfg["families_default"]),
                 "queries": None, "directives": [], "source": "default-families",
                 "state": f"error: {type(e).__name__}: {str(e)[:160]}"}, "error")


def _path_b_bundle_accepts():
    """Qué llaves ADR-0080 acepta answer_pipeline.path_b_bundle (search_plan, on_stage, existing_ids) —
    por inspección de firma, no por try/except (patrón _call_with_optional)."""
    try:
        params = inspect.signature(answer_pipeline.path_b_bundle).parameters
        has_varkw = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
        return {n for n in ("search_plan", "on_stage", "existing_ids") if n in params or has_varkw}
    except (TypeError, ValueError):
        return set()


def _path_b_via_harness(question, entities, q_sent, q_source, triggered_by, search_plan, on_stage,
                        existing_ids=None):
    """La Ruta B por el harness: answer_pipeline.path_b_bundle(..., search_plan=, on_stage=, existing_ids=)
    cuando la firma lo acepta (rebanada C2); si no, el path_b_bundle de hoy y `harness_used False` declarado.
    Devuelve (block, harness_used: bool, on_stage_delivered: bool)."""
    kwargs = {"entities": entities, "query": q_sent, "query_source": q_source, "triggered_by": triggered_by}
    accepts = _path_b_bundle_accepts()
    if search_plan is not None and "search_plan" in accepts:
        kwargs["search_plan"] = search_plan
        if "on_stage" in accepts:
            kwargs["on_stage"] = on_stage
        if "existing_ids" in accepts and existing_ids is not None:
            kwargs["existing_ids"] = list(existing_ids)
        block = answer_pipeline.path_b_bundle(question, **kwargs)
        return block, True, "on_stage" in accepts
    block = answer_pipeline.path_b_bundle(question, **kwargs)
    return block, False, False


def _search_ledger_of(block, search_plan, plan_state, harness_used, cfg):
    """frozen.search_ledger {plan, rounds[], families_default, n_rounds, cap, state, …} — el ledger que dejó
    el harness en block.search_ledger (answer_pipeline._path_b_harness: harness_version, plan sin
    query_builder, rounds sin items, n_rounds, cap, round_budget_s, stop_reason, n_new_total, n_items) más
    la procedencia de la configuración; o declarado ausente (rounds [], n_rounds null) cuando la Ruta B no
    corrió por el harness. El bundle.path_b íntegro sigue en bundle_json."""
    led = block.get("search_ledger") if isinstance(block, dict) else None
    if harness_used and isinstance(led, dict):
        out = dict(led)
        out.setdefault("plan", {k: v for k, v in (search_plan or {}).items() if k != "query_builder"})
        out["rounds"] = list(out.get("rounds") or [])
        out["n_rounds"] = len(out["rounds"]) if out.get("n_rounds") is None else out["n_rounds"]
        out["state"] = "harness"
    else:
        if harness_used:
            state = "harness-without-ledger (path_b_bundle accepted search_plan but returned no search_ledger)"
        elif plan_state == "not-requested":
            state = "not-requested (no search round: competent or structural route)"
        elif plan_state != "built":
            state = f"legacy-path-b ({plan_state})"
        else:
            state = "legacy-path-b (path_b_bundle without search_plan — ADR-0080 C2)"
        # corrector ADR-0080 (ADR-0043): 'not-requested' es CERO rondas MEDIDO (la compuerta o lo estructural
        # decidieron no buscar) → n_rounds 0; null se reserva a cuando el harness NO midió (ausente, error,
        # camino legado, kill-switch)
        out = {"plan": ({k: v for k, v in search_plan.items() if k != "query_builder"}
                        if isinstance(search_plan, dict) else None),
               "rounds": [], "n_rounds": 0 if plan_state == "not-requested" else None,
               "cap": cfg["rounds_cap"], "state": state}
    out["plan_state"] = plan_state
    # corrector ADR-0080 (paridad webapp 2026-09-15): el vocabulario REAL viaja congelado (como stop_reasons_vocabulary)
    out["plan_state_vocabulary"] = dict(SEARCH_PLAN_STATE_VOCABULARY)
    out.setdefault("families_default", list(cfg["families_default"]))
    out.setdefault("cap", cfg["rounds_cap"])
    out.setdefault("round_budget_s", cfg["round_budget_s"])
    out["config_source"] = {"families": cfg["families_source"], "cap": cfg["rounds_cap_source"],
                            "round_budget_s": cfg["round_budget_s_source"]}
    out["second_round_rule"] = ("only if n_admitted == 0 in round k AND k < cap AND the inputs of some family "
                                "changed since round k (dois/curies resolved in the round); with the default "
                                "families the inputs only change when items are admitted, so today a round "
                                "is never re-executed with identical inputs (stop_reason 'no-new-inputs'; "
                                "until ADR-0082 directives)")
    out["config_reader"] = cfg.get("config_reader")
    return out


def _support_states(citations, bundle, audit_result):
    """(E/G) support_state por cita — verify_output.support_state_for (rebanada E) si está en el árbol; el
    grounding viene de la lente evidence-grounding (citation_support opcional en su fila). Devuelve
    (citations con support_state aditivo, citations_support_summary). Sin el helper: support_state None por
    cita + summary.state 'tool-unavailable' — nunca se funden los peldaños."""
    fn = getattr(verify_output, "support_state_for", None)
    ladder = tuple(getattr(verify_output, "SUPPORT_LADDER", None)
                   or ("unresolved", "resolved", "passage_delivered", "supported", "unsupported"))
    # corrector ADR-0080 (G): la forma degradada conserva la FORMA — los 5 peldaños con null (no medido), no un
    # dict vacío; ladder/pertinent viajan igual para que el front tipe UNA forma
    summary = {"n": len(citations), "by_state": {rung: None for rung in ladder}, "ladder": list(ladder),
               "pertinent": getattr(verify_output, "PERTINENT_NOT_AVAILABLE", "not-available (ADR-0082)")}
    if fn is None:
        for c in citations:
            c.setdefault("support_state", None)
        summary["state"] = "tool-unavailable (verify_output.support_state_for not in tree — ADR-0080 E)"
        return citations, summary
    # el grounding lo extrae composite_auditor (la lente evidence-grounding, ADR-0080 E) cuando existe el
    # helper; si no, se recogen las filas que traigan citation_support
    picker = getattr(composite_auditor, "citation_support_from_panel", None)
    rows = (audit_result or {}).get("panel", [])
    if callable(picker):
        grounding = picker(rows)
    else:
        grounding = []
        for row in rows:
            if isinstance(row.get("citation_support"), list):
                grounding.extend(row["citation_support"])
    try:
        per = fn(citations, bundle, grounding=grounding or None)
    except Exception as e:
        for c in citations:
            c.setdefault("support_state", None)
        summary["state"] = f"error: {type(e).__name__}: {str(e)[:120]}"
        return citations, summary
    by_n = {p.get("n"): p for p in (per or []) if isinstance(p, dict)}
    for c in citations:
        p = by_n.get(c.get("n"))
        if p is None:
            c.setdefault("support_state", None)
            continue
        # los peldaños viajan SEPARADOS dentro de la cita (aditivo, ADR-0080 G); la regla de la escalera va UNA
        # vez en el resumen, no repetida por cita
        for k in ("resolved", "resolved_to", "passage_delivered", "pertinent", "supported", "support_state"):
            if k in p:
                c[k] = p[k]
        c.setdefault("support_state", None)
    summarizer = getattr(verify_output, "support_summary", None)
    if callable(summarizer):
        summary = dict(summarizer(per or []))
    else:
        for c in citations:
            key = str(c.get("support_state"))
            summary["by_state"][key] = summary["by_state"].get(key, 0) + 1
    summary["state"] = "checked"
    summary["grounding_rows"] = len(grounding or [])
    summary["ladder_rule"] = getattr(verify_output, "SUPPORT_LADDER_RULE", None)
    return citations, summary


def snapshot_extra():
    """ADR-0081 (I): los EXTRA_FIELDS del snapshot que models.py no puede derivar porque viven aquí y en competence —
    {campo: {value, source}}. UNA sede: execute_run (config_ledger.observe / stage.models) y app.config_ledger_boot
    (S5) pasan exactamente esto, así el boot y la corrida describen el mismo estado."""
    cg = competence.env_config()
    harness, harness_src = _search_harness_enabled()
    gate_raw = (os.environ.get(competence.GATE_ENV) or "").strip()
    # misma regla de fuente que config_ledger.default_extra (S5): la env PRESENTE (aunque vacía) es 'env:' — así el
    # boot y la corrida escriben la misma fuente y el runtime-diff no inventa cambios
    rev_present = "WITT_REVISION_CYCLE" in os.environ
    return {
        "contract.render_contract_version": {"value": RENDER_CONTRACT_VERSION, "source": "runs.RENDER_CONTRACT_VERSION"},
        "competence.gate": {"value": cg["gate_enabled"],
                            "source": (f"env:{competence.GATE_ENV}" if gate_raw else f"default-unset:{competence.GATE_ENV}")},
        "search.harness": {"value": harness, "source": harness_src},
        "revision.cycle": {"value": _revision_enabled(),
                           "source": "env:WITT_REVISION_CYCLE" if rev_present else "default-unset:WITT_REVISION_CYCLE"},
    }


def _config_ledger_observe(snap):
    """ADR-0081 (E/I): bitácora de configuración en tiempo de corrida — config_ledger.observe(snapshot) (S5,
    rag_index/query_service/config_ledger.py) compara el snapshot con el último visto y appendea filas
    'system:runtime-diff' (p. ej. el auto-retire de haiku). El módulo se importa en DURO (S7: la tolerancia
    'module-missing' de la obra se retiró — sin él el servicio no importa y el smoke lo dice a gritos); la LLAMADA sigue
    siendo tolerante: con cualquier fallo la corrida sigue — JAMÁS frena (§6 no-hang). Devuelve lo que observe() devolvió
    o un estado de error declarado."""
    try:
        return config_ledger.observe(snap)
    except Exception as e:
        return {"state": f"error: {type(e).__name__}: {str(e)[:120]}"}


def _judge_identity(member):
    """ADR-0081 (B): stage.audit.judge += family, api, api_source, reviewer_source — lo que el asiento DECLARA
    (models.panel vía composite_auditor.audit). `api`/`api_source` salen de la MISMA función con la que audit() escribe
    audit.panel[].api/api_source (composite_auditor._member_api — S7, costura N: dos puertas, una definición): un panel
    legado sin `api` la infiere por familia ('inferred-from-family'); familia desconocida → (None, 'unknown-family').
    reviewer_source None = el asiento no declaró fuente."""
    reviewer = member.get("reviewer")
    family = member.get("family") or models.family_of(reviewer)[0]
    api, api_source = composite_auditor._member_api(member)
    return {"family": family, "api": api, "api_source": api_source, "reviewer_source": member.get("reviewer_source")}


def _panel_incomplete_reasons(a):
    """Códigos CERRADOS ('min_valid' | 'families' | 'lenses') de un REVISE estructural (ADR-0081 D). composite_auditor
    los entrega en panel_incomplete_reasons (= quorum.failed); un audit() anterior a (D) sólo marca panel_incomplete
    por min_valid, así que ése es el único código que puede declararse sin inventar."""
    reasons = a.get("panel_incomplete_reasons")
    if not isinstance(reasons, list) or not reasons:
        q = a.get("quorum")
        reasons = q.get("failed") if isinstance(q, dict) else None
    return list(reasons) if reasons else ["min_valid"]


def _verdict_payload(a, revision_round):
    """stage.audit.verdict (ADR-0081 D): + families_valid, n_families_valid, lenses_valid, n_lenses_valid,
    panel_incomplete, panel_incomplete_reasons. Las llaves del cuórum las produce composite_auditor.audit; si el
    audit() del árbol aún no las trae viajan null (no medido), jamás inventadas. panel_incomplete: audit() sólo la
    escribe True → ausente == False (medido por construcción)."""
    reasons = a.get("panel_incomplete_reasons")
    if reasons is None and isinstance(a.get("quorum"), dict):
        reasons = a["quorum"].get("failed")
    return {"verdict": a["verdict"], "tally": a["tally"], "n_valid": a["n_valid"], "revision_round": revision_round,
            "source_vocabulary": a["source_vocabulary"],
            "families_valid": a.get("families_valid"), "n_families_valid": a.get("n_families_valid"),
            "lenses_valid": a.get("lenses_valid"), "n_lenses_valid": a.get("n_lenses_valid"),
            "panel_incomplete": bool(a.get("panel_incomplete")), "panel_incomplete_reasons": reasons}


def execute_run(run, synthesizer=None, panel_caller=None):
    """Execute one claimed run end-to-end. Deterministic under injected synthesizer/panel_caller (the
    offline gate); live otherwise. Never raises — every exit is a recorded terminal state + event.

    ADR-0081: los roles se resuelven EN LA LLAMADA (models.snapshot: tabla + env, con fuente), el snapshot va a la
    bitácora de configuración (config_ledger.observe — nunca frena) y al evento stage.models (PRIMER evento de etapa:
    qué va a correr ANTES de gastar); frozen.models (models.provenance_block) mide requested vs reported por pasada.

    ADR-0080: tras pass1 → stage.confidence.elicit{pass:1} → stage.deterministic_gate{pass:1} (adelantado) →
    stage.competence (competence.evaluate, decidido por código). Competente → pass1 es la candidata, sin ronda
    extra, fallback.trigger null. No competente (o kill-switch con `pass1 < tau`) → stage.search.plan + Ruta B
    por el harness (C2) → pass2 → elicit{pass:2} → gate{pass:2}. Estructural → trigger 'structural' como hoy."""
    run_id = run["run_id"]
    synthesizer = synthesizer or _default_synthesizer

    def _check_cancel():
        if db.cancel_requested(run_id):
            raise RunCancelled()

    def _on_stage(name, payload):
        degraded = None
        if name == "path_a":
            mode = payload.get("retrieval", {}).get("mode")
            degraded = None if mode == "semantic" else mode
        # corrector ADR-0080: los eventos search.* que el harness emite en vivo llevan el MISMO agent que la
        # forma que runs emite cuando no corre ('search_harness') — un tipo de evento, un agente
        db.add_event(run_id, f"stage.{name}", payload=payload,
                     agent="search_harness" if name.startswith("search.") else "answer_pipeline",
                     degraded=degraded)
        _check_cancel()

    # ADR-0078 corrector — latido POR JUEZ: el panel corre en serie (composite_auditor.audit) y cada juez
    # puede tardar hasta timeout×(1+retries) = 240 s sin emitir evento; con 4 jueces (y dos paneles si hay
    # revisión) el hueco legítimo rebasaba WITT_REAP_STALE_S=900 y el reaper sentenciaba una corrida viva.
    # Un evento stage.audit.judge ANTES de cada juez acota el hueco a un juez (≤ 240 s). Se envuelve el
    # caller inyectable — composite_auditor no se toca; el caller por default sigue siendo el suyo.
    inner_caller = panel_caller or composite_auditor._default_caller
    judge_attempts = {}   # ADR-0080 (E): composite_auditor puede REINTENTAR un juez caído (WITT_JUDGE_RETRIES);
                          # cada invocación del caller deja su evento con attempt / retries_judge MEDIDOS aquí
    # corrector ADR-0080 (paridad webapp 2026-09-15): la Traza quiere decir "intento N de M" — M = 1 + reintentos
    # configurados, leídos de la MISMA fuente que composite_auditor.audit usa (resolve_judge_retries, WITT_JUDGE_RETRIES
    # tolerante); audit() se llama aquí sin judge_retries=, así que el tope efectivo es exactamente este
    judge_retries_cfg, judge_retries_src = composite_auditor.resolve_judge_retries()
    judge_max_attempts = 1 + int(judge_retries_cfg)

    def panel_caller(member, system, user_text):   # noqa: F811 — envuelve al inyectado
        key = (member.get("reviewer"), member.get("lens"))
        judge_attempts[key] = judge_attempts.get(key, 0) + 1
        # composite_auditor (E) entrega `attempt` en el member; si un caller viejo no lo trae, se cuenta aquí
        attempt = member.get("attempt") if isinstance(member.get("attempt"), int) else judge_attempts[key]
        db.add_event(run_id, "stage.audit.judge", agent="composite-auditor",
                     payload={"reviewer": member.get("reviewer"), "lens": member.get("lens"),
                              "phase": "start", "heartbeat": True,
                              "attempt": attempt, "retries_judge": max(0, attempt - 1),
                              "max_attempts": judge_max_attempts, "max_attempts_source": judge_retries_src,
                              # ADR-0081 (B): la Traza dice "intento N de M · <api> · <family>"
                              **_judge_identity(member)})
        return inner_caller(member, system, user_text)

    # partial-spend tracking (LOTE-01·A4): what a run spent BEFORE dying must survive on failed and
    # cancelled paths too — M8 cannot reconcile otherwise ("118,000 tokens gastados antes de morir").
    # panel_rows_all acumula las filas de TODOS los paneles (con revisión hay dos — ADR-0067): el
    # gasto de ambos debe contar en cualquier camino de salida.
    passes, audit_result, panel_rows_all = [], {}, []
    embed_t0 = _embed_usage_snapshot()
    # holder explícito: el plan se carga DENTRO del try, y _usage_now (definida antes) tiene que
    # poder verlo en los caminos failed/cancelled — el gasto del planner ya ocurrió y debe sobrevivir
    # (LOTE-01·A4). Una clausura sobre `plan` con locals() no lo alcanza.
    plan_holder = {}

    def _usage_now():
        return _token_usage(passes, {"panel": panel_rows_all},
                            max(0, _embed_usage_snapshot() - embed_t0),
                            plan=plan_holder.get("plan"))

    try:
        db.add_event(run_id, "run.state", payload={"state": "running"})
        _check_cancel()

        # 0a) ADR-0081 (A/B/E): qué modelos VAN a correr, ANTES de gastar — el snapshot EFECTIVO (tabla + env, en la
        # llamada; roles con fuente, panel, avisos retirement-due/past-retirement, ids desconocidos), la bitácora de
        # configuración en tiempo de corrida (S5; jamás frena) y el evento stage.models — PRIMER evento de etapa, antes
        # de stage.plan (patrón de la casa: evento propio, no una llave dentro de run.state{running}).
        models_snapshot = models.snapshot(extra=snapshot_extra())
        synth_role, elicit_role = models_snapshot["roles"]["synthesizer"], models_snapshot["roles"]["elicitation"]
        _config_ledger_observe(models_snapshot)
        db.add_event(run_id, "stage.models", agent="runs",
                     payload={k: models_snapshot[k] for k in STAGE_MODELS_PAYLOAD_KEYS},
                     level="warning" if models_snapshot["warnings"] or models_snapshot["unknown_models"] else "info")
        _check_cancel()

        # 0) el plan declarado (tapón 3, ADR-0061) — si la corrida lo trae, es el primer evento de etapa tras
        # stage.models (el boceto M3 lo pinta como primera línea). No traerlo no bloquea nada: se declara.
        plan = json.loads(run["plan_json"]) if run.get("plan_json") else None
        plan_holder["plan"] = plan
        if plan:
            db.add_event(run_id, "stage.plan", agent="planner", payload=plan_event_payload(plan))
            _check_cancel()

        # 0b) investigación (ADR-0079): el sobre del turno anterior se armó al ENCOLAR (servidor) y vive en
        # runs.thread_context_json. Aquí se decide si VIAJA: el kill-switch se relee en tiempo de corrida
        # (patrón WITT_REVISION_CYCLE) — un snapshot persistido pero apagado al ejecutar NO llega al modelo
        # y frozen.thread_context queda null con la razón. Al PANEL jamás viaja el texto: sólo el resumen
        # deterministic_checks.thread.
        thread_env = _thread_envelope(run)
        thread_snapshot = thread_env.get("snapshot")
        thread_delivery = {"synthesizer": None, "panel": False,
                           "skipped_reason": thread_env.get("skipped_reason"),
                           "prompt_components": []}
        if thread_snapshot is not None and not _thread_context_enabled():
            thread_snapshot = None
            thread_delivery["skipped_reason"] = (f"kill-switch {THREAD_CONTEXT_ENV}=0 at execution (snapshot "
                                                 "persisted at enqueue, NOT delivered)")
        if thread_snapshot is not None:
            thread_delivery["prompt_components"] = ["user_text.thread_context (sibling of evidence)",
                                                    "synth_system: THREAD_ANTI_LEAK_CLAUSE",
                                                    "SYNTH_TOOL.description: anti-leak sentence"]
            hc = thread_snapshot.get("human_comments") or {}
            db.add_event(run_id, "stage.thread_context", agent="runs",
                         payload={"turn_no": run.get("turn_no"), "turn_kind": run.get("turn_kind"),
                                  "parent_run_no": (thread_snapshot.get("parent") or {}).get("run_no"),
                                  "bytes": thread_snapshot.get("bytes"),
                                  "n_comments_included": hc.get("n_included"),
                                  "comments_truncated": hc.get("truncated"),
                                  "previous_answer_present": thread_snapshot.get("previous_answer") is not None})
            _check_cancel()

        def _synth(evidence, label):
            """Cada pasada recibe el snapshot como LLAVE HERMANA si existe; un stub con la firma vieja
            (question, evidence, pass_label) sigue válido y el registro declara que no lo recibió."""
            if thread_snapshot is None:
                return synthesizer(run["question"], evidence, label)
            out, delivered = _call_with_optional(synthesizer, (run["question"], evidence, label),
                                                 "thread_context", thread_snapshot)
            thread_delivery["synthesizer"] = delivered
            if not delivered:
                thread_delivery["synthesizer_note"] = "synthesizer signature without thread_context — not delivered"
            return out

        # 1) retrieve — the ONE state machine, instrumented via on_stage (never re-assembled)
        bundle = answer_pipeline.retrieve(run["question"],
                                          entities=[e for e in run["entities_csv"].split(",") if e],
                                          on_stage=_on_stage)
        # one identity end-to-end: the run's id IS the bundle's id (ADR-0044)
        bundle["run_id"] = run_id
        bundle["bundle_identity"] = answer_pipeline._identity(bundle)

        # 2) PASS 1 — DI-only synthesis. Its confidence is the real "is my store enough?" signal
        # (ADR-0051), measured even when structural insufficiency already fetched Path B.
        # ADR-0081 (B): el evento declara el modelo RESUELTO con su fuente y la generación (antes sólo agent=constante)
        db.add_event(run_id, "stage.synthesize.start", agent=synth_role["model"],
                     payload={"model": synth_role["model"], "model_source": synth_role["source"],
                              "generation": synth_role["generation"]})
        pass1 = _synth(_compact_evidence(bundle, include_path_b=False), "pass1")
        passes.append(("pass1", pass1))
        conf1, conf1_source = _resolve_confidence(pass1)
        db.add_event(run_id, "stage.synthesize.pass1", agent=pass1.get("model"),
                     payload={"stated_confidence": conf1, "confidence_source": conf1_source,
                              "absence_kind": pass1.get("absence_kind"),
                              "gap_flags": pass1.get("gap_flags", []),
                              "usage": _synth_usage_payload(pass1)})   # ADR-0080 (F): el evento que gasta lo dice
        # ADR-0080 (B): la elicitación dedicada (ADR-0065) gana su propio evento — el escalar autoritativo
        # con su procedencia y su gasto, separado de la síntesis.
        db.add_event(run_id, "stage.confidence.elicit", agent=pass1.get("model"),
                     payload=_elicit_event_payload(pass1, "pass1", conf1, conf1_source))
        _check_cancel()

        # 2b) ADR-0080 (B): el gate determinista ADELANTADO sobre pass1 — su admisibilidad es un componente
        # de la compuerta (una pasada inadmisible no puede ser candidata por competente que se declare).
        checks1 = _gate(pass1, bundle, thread_snapshot, run, pass_no="pass1")
        db.add_event(run_id, "stage.deterministic_gate", tool="verify_output",
                     payload=checks1, level="info" if checks1["admissible"] else "warning")
        _check_cancel()

        # 3) ADR-0080 (A/B): la COMPUERTA DE COMPETENCIA decide — por código — si pass1 basta. Sustituye al
        # disparador `pass1 < tau` de ADR-0051, que sigue evaluándose como REGLA LEGADA declarada
        # (fb_meta.trigger_legacy) y gobierna sólo bajo kill-switch / ruta no aplicable. Lo estructural
        # (assess_sufficiency, ya disparó Ruta B dentro de retrieve) manda sobre todo, como hoy.
        structural_fired = bundle["path_b"]["triggered"]
        min_hist, min_hist_src = _competence_min_history()
        niche_codes = competence.plan_niches(plan)
        cal_origins, cal_origins_src = _calibration_origins()
        cal_cov = db.calibration_coverage(niche_codes, min_hist, include_origins=cal_origins)
        cal_cov["min_required_source"] = min_hist_src
        # corrector ADR-0080 (paridad webapp 2026-09-15): la cobertura DECLARA el filtro que se aplicó — lista de
        # orígenes o el literal 'all' (sin filtro; db recibe None, el registro nunca lleva un null ambiguo) — y su
        # fuente; competence._calibration_component los copia al componente que la webapp pinta
        cal_cov["include_origins"] = list(cal_origins) if cal_origins is not None else CG_CALIBRATION_ORIGINS_ALL
        cal_cov["include_origins_source"] = cal_origins_src
        comp = competence.evaluate(conf1, checks1["admissible"], plan, structural_fired, cal_cov,
                                   council_coverage=None, tau=FALLBACK_CONF_TAU)
        legacy_conf_fired = (not structural_fired) and (conf1 is None or conf1 < FALLBACK_CONF_TAU)
        if structural_fired:
            trigger, decision_source = "structural", "structural (assess_sufficiency, inside retrieve)"
            trigger_decided_by = "structural (assess_sufficiency, code)"
        elif comp["competent"] is True:
            trigger, decision_source = None, "competence-gate: competent (pass1 is the candidate)"
            trigger_decided_by = "code (competence-gate)"
        elif comp["competent"] is False:
            trigger, decision_source = "competence", "competence-gate: not competent"
            trigger_decided_by = "code (competence-gate)"
        else:   # None: kill-switch o ruta store-consultation → la regla por confianza de hoy decide, y el
                # trigger lo dice con SU nombre ('confidence', ADR-0051) — jamás 'competence' (corrector ADR-0080)
            trigger = TRIGGER_LEGACY_CONFIDENCE if legacy_conf_fired else None
            decision_source = (f"legacy-confidence ({comp.get('skipped_reason')})")
            trigger_decided_by = "model-confidence (legacy rule pass1 < tau; competence.competent is null)"
        comp["decision"] = {"trigger": trigger, "decision_source": decision_source,
                            "legacy_confidence_fired": legacy_conf_fired, "trigger_decided_by": trigger_decided_by}
        db.add_event(run_id, "stage.competence", agent="competence-gate", tool="competence",
                     payload=comp, level="info" if trigger not in ("competence", "confidence") else "warning")
        _check_cancel()

        search_cfg = _search_config()
        harness_enabled, harness_enabled_src = _search_harness_enabled()
        search_plan, search_plan_state, harness_used = None, "not-requested", False
        if trigger in ("competence", TRIGGER_LEGACY_CONFIDENCE):
            # ADR-0057: the query SENT to the English index is never the raw (Spanish) question when a
            # better source exists — the synthesizer's English keywords first, entities second.
            entities = [e for e in run["entities_csv"].split(",") if e]
            if (pass1.get("search_query_en") or "").strip():
                q_sent, q_source = pass1["search_query_en"].strip(), "synthesizer"
            else:
                q_sent, q_source = answer_pipeline.build_external_query(run["question"], entities)
            if trigger == TRIGGER_LEGACY_CONFIDENCE or not harness_enabled:
                # corrector ADR-0080: bajo kill-switch / ruta no aplicable (competent null) o con
                # WITT_SEARCH_HARNESS=0 la Ruta B es la de ADR-0078 BYTE A BYTE — path_b_bundle SIN plan, sin
                # harness, sin stage.search.round/source; el plan-sobre lo dice y el ledger queda 'legacy-path-b (…)'
                if trigger == TRIGGER_LEGACY_CONFIDENCE:
                    search_plan_state = ("kill-switch WITT_COMPETENCE_GATE=0" if comp.get("config", {}).get("gate_enabled") is False
                                         else f"not-applicable ({comp.get('skipped_reason')})")
                else:
                    search_plan_state = f"kill-switch {SEARCH_HARNESS_ENV}=0"
                search_plan = {"plan_version": None, "rounds_cap": search_cfg["rounds_cap"],
                               "families": list(answer_pipeline.PATH_B_SOURCES), "queries": None, "directives": [],
                               "source": "legacy-path-b (answer_pipeline.PATH_B_SOURCES)", "state": search_plan_state}
                accepts = _path_b_bundle_accepts()
                harness_live = False
            else:
                # ADR-0080 (C): el plan de búsqueda (familias por default o directivas — vacías hasta ADR-0082)
                search_plan, search_plan_state = _build_search_plan(run["question"], entities,
                                                                    pass1.get("search_query_en"), search_cfg)
                accepts = _path_b_bundle_accepts()
                harness_live = search_plan_state == "built" and {"search_plan", "on_stage"} <= accepts
            if not harness_live:
                # el harness emite stage.search.plan/round/source por on_stage cuando corre en vivo (C2); si
                # no va a correr, el plan-sobre (declarado: unavailable/error/legacy/kill-switch) se emite desde aquí
                db.add_event(run_id, "stage.search.plan", agent="search_harness",
                             payload={"state": search_plan_state, "plan_version": search_plan.get("plan_version"),
                                      "harness_version": search_plan.get("harness_version"),
                                      "families": search_plan.get("families"),
                                      "rounds_cap": search_plan.get("rounds_cap"),
                                      "source": search_plan.get("source") or search_plan.get("families_source"),
                                      "n_directives": len(search_plan.get("directives") or []),
                                      "round_budget_s": search_cfg["round_budget_s"],
                                      "families_source": search_cfg["families_source"],
                                      "harness_enabled": harness_enabled, "harness_enabled_source": harness_enabled_src,
                                      "path_b_bundle_accepts": sorted(accepts),
                                      "pass1_query_en_present": bool((pass1.get("search_query_en") or "").strip())})
            _check_cancel()
            # ONE builder for the block (answer_pipeline.path_b_bundle) — the structural trigger inside
            # retrieve() and this competence-gated one must not maintain two copies of the same dict.
            # `entities` travels: the zfin source keys on gene SYMBOLS, not on a free-text query.
            # existing_ids = los doc_ids de la Ruta A ya presentes (dedup declarado por el harness).
            if trigger == TRIGGER_LEGACY_CONFIDENCE:
                # el literal de ADR-0051, intacto: quien lea triggered_by sabe que decidió el escalar
                triggered_by = [f"confidence-gate: pass1_confidence={conf1} < tau={FALLBACK_CONF_TAU} "
                                f"(legacy rule; {comp.get('skipped_reason')})"]
            else:
                triggered_by = [f"competence-gate: {decision_source}; reasons={comp.get('reasons')}; "
                                f"pass1_confidence={conf1} tau={FALLBACK_CONF_TAU}"]
            block, harness_used, on_stage_delivered = _path_b_via_harness(
                run["question"], entities, q_sent, q_source, triggered_by,
                search_plan if search_plan_state == "built" else None, _on_stage,
                existing_ids=[h["doc_id"] for h in bundle["path_a"]["hits"]])
            bundle["path_b"] = block
            if harness_used and not on_stage_delivered:
                # el harness no pudo emitir en vivo: la traza gana los rounds desde el ledger (replay == traza)
                for rnd in ((block.get("search_ledger") or {}).get("rounds") or []):
                    db.add_event(run_id, "stage.search.round", agent="search_harness",
                                 payload={k: rnd.get(k) for k in ("round", "trigger", "budget_s", "elapsed_s")}
                                 | {"n_sources": len(rnd.get("sources") or []),
                                    "sources": [{k: s.get(k) for k in ("family", "status", "n_found", "n_new",
                                                                        "elapsed_s", "cache_hit")}
                                                for s in (rnd.get("sources") or [])]})
            # external evidence entered the run -> the honest state is FALLBACK_FETCHED (same
            # constructor, same literals — never a re-invented machine)
            bundle["decision_state"] = answer_pipeline._state(
                "FALLBACK_FETCHED", may_answer=False, may_propose=False,
                required_next="AUDIT — composite-auditor Mode 1 (>=3 adversarial) MUST verdict the "
                              "externally-augmented answer BEFORE it may be shown (competence-gated "
                              "fallback, ADR-0080; audit on 100% of runs, ADR-0049).")
            pb_payload = answer_pipeline.path_b_event_payload(bundle["path_b"], trigger=trigger)
            pb_payload["trigger_legacy"] = TRIGGER_LEGACY_CONFIDENCE if legacy_conf_fired else None
            pb_payload["trigger_decided_by"] = trigger_decided_by
            pb_payload["harness_used"] = harness_used
            db.add_event(run_id, "stage.path_b", agent="answer_pipeline", payload=pb_payload)
            _check_cancel()
        bundle["search_ledger"] = _search_ledger_of(bundle["path_b"], search_plan, search_plan_state,
                                                    harness_used, search_cfg)
        bundle["fallback"] = {"trigger": trigger,
                              "fb_meta": {"pass1_confidence": conf1,
                                          "pass1_confidence_source": conf1_source,
                                          "tau": FALLBACK_CONF_TAU, "tau_source": FALLBACK_CONF_TAU_SOURCE,
                                          "structural_sufficient": not structural_fired,
                                          "absence_kind": pass1.get("absence_kind"),
                                          # ADR-0080: el literal viejo como ALIAS declarado + quién decidió
                                          "trigger_legacy": (TRIGGER_LEGACY_CONFIDENCE if legacy_conf_fired
                                                             else ("structural" if structural_fired else None)),
                                          "trigger_vocabulary": TRIGGER_VOCABULARY,
                                          "trigger_decided_by": trigger_decided_by,
                                          "search_harness_enabled": harness_enabled,
                                          "search_harness_enabled_source": harness_enabled_src,
                                          "competence": {"competent": comp["competent"],
                                                         "not_applicable": comp["not_applicable"],
                                                         "reasons": comp["reasons"],
                                                         "decision_source": decision_source,
                                                         "skipped_reason": comp.get("skipped_reason"),
                                                         "decided_by": comp["decided_by"],
                                                         "module_version": comp["module_version"]}}}

        # 4) PASS 2 — only when a fallback fired: re-synthesize with the external evidence
        # incorporated. BOTH confidences persist; the delta is the run's most informative datum
        # (the 0.14 -> 0.71 Level-2 measurement).
        if trigger:
            pass2 = _synth(_compact_evidence(bundle, include_path_b=True), "pass2")
            passes.append(("pass2", pass2))
            conf2, conf2_source = _resolve_confidence(pass2)
            delta = (round(conf2 - conf1, 4) if isinstance(conf1, (int, float))
                     and isinstance(conf2, (int, float)) else None)
            db.add_event(run_id, "stage.synthesize.pass2", agent=pass2.get("model"),
                         payload={"stated_confidence": conf2, "confidence_source": conf2_source,
                                  "delta_vs_pass1": delta,
                                  "absence_kind": pass2.get("absence_kind"),
                                  "usage": _synth_usage_payload(pass2)})
            db.add_event(run_id, "stage.confidence.elicit", agent=pass2.get("model"),
                         payload=_elicit_event_payload(pass2, "pass2", conf2, conf2_source))
            answer = pass2
            final_conf, final_source = conf2, conf2_source
        else:
            conf2, conf2_source, delta = None, None, None
            answer = pass1
            final_conf, final_source = conf1, conf1_source
        bundle["bundle_identity"] = answer_pipeline._identity(bundle)
        _check_cancel()

        # 5) deterministic anti-fabrication gate over the FINAL answer (Logic-LM-class, NOT an LLM)
        # ADR-0079: predicado DURO parent_identifier_leak — un identificador que sólo existe en el turno
        # anterior (precedente) y reaparece en la respuesta sin estar en la evidencia del hijo = fuga →
        # inadmisible (extra_predicates de verify_output.admissible; la clase Logic-LM no cambia).
        # ADR-0080: sobre pass1 YA corrió (checks1, evento pass:1); competente → la candidata ES pass1 y sus
        # checks son los del gate adelantado (no se re-mide lo mismo dos veces); con pass2 → gate{pass:2}.
        if trigger:
            checks = _gate(answer, bundle, thread_snapshot, run, pass_no="pass2")
            db.add_event(run_id, "stage.deterministic_gate", tool="verify_output",
                         payload=checks, level="info" if checks["admissible"] else "warning")
        else:
            checks = dict(checks1)
        checks["pass1_admissible"] = checks1["admissible"]
        checks["competence_gate"] = competence.compact(comp)
        _check_cancel()

        # 6) composite audit — 100% of runs (ADR-0049), the terminal transition
        db.add_event(run_id, "stage.audit.start", agent="composite-auditor")
        audit_result = composite_auditor.audit(
            claim={"direct_answer": answer["direct_answer"],
                   "stated_confidence": answer.get("stated_confidence")},
            evidence=_compact_evidence(bundle), deterministic_checks=checks,
            required_because=bundle["decision_state"]["state"], caller=panel_caller)
        panel_rows_all.extend(audit_result.get("panel", []))
        db.add_event(run_id, "stage.audit.verdict", agent="composite-auditor",
                     payload=_verdict_payload(audit_result, 0),   # ADR-0081 (D): + familias/lentes/panel_incomplete
                     level="info" if audit_result["verdict"] != "REVISE" else "warning")

        # 6b) ciclo de revisión acotado (ADR-0067): UN intento de corrección con los hallazgos del
        # panel como insumo, re-gate determinista, re-auditoría — y el veredicto de la ronda 2 es
        # terminal SEA CUAL SEA (tope duro REVISION_CAP=1). AMBAS versiones persisten en el registro.
        revision = {"enabled": _revision_enabled(), "performed": False, "cap": REVISION_CAP}
        audit_initial, answer_initial = None, None
        conf_rev, conf_rev_source = None, None
        if audit_result["verdict"] == "REVISE" and not revision["enabled"]:
            revision["skipped_reason"] = "kill-switch WITT_REVISION_CYCLE=0 (comportamiento pre-ADR-0067)"
        elif audit_result["verdict"] == "REVISE" and audit_result.get("panel_incomplete"):
            # el REVISE viene del panel (delgado: <3 jueces válidos; ADR-0081 D: o sin diversidad de FAMILIAS /
            # LENTES), no de la respuesta: re-sintetizar no arregla jueces caídos ni una sola familia votando — se
            # declara con los códigos cerrados del cuórum y el terminal honesto se conserva. El literal viejo
            # ('panel_incomplete — el REVISE es estructural (jueces caídos), …') sigue válido en registros 1.9.
            revision["skipped_reason"] = (f"panel_incomplete ({', '.join(_panel_incomplete_reasons(audit_result))}) — "
                                          "el REVISE es estructural (jueces caídos o sin diversidad), no un hallazgo "
                                          "sobre la respuesta; la revisión no aplica")
        elif audit_result["verdict"] == "REVISE":
            _check_cancel()
            findings = _panel_findings(audit_result)
            db.add_event(run_id, "stage.revision.start", agent="composite-auditor",
                         payload={"n_findings": len(findings), "cap": REVISION_CAP}, level="warning")
            rev_evidence = {**_compact_evidence(bundle), "revision_input": {
                "previous_answer": {"direct_answer": answer["direct_answer"],
                                    "stated_confidence": answer.get("stated_confidence"),
                                    "gap_flags": answer.get("gap_flags", [])},
                "panel_findings": findings,
                "instruction": ("REVISE the previous answer to resolve the panel's findings USING ONLY "
                                "the evidence shown — fixing a finding never licenses new claims or new "
                                "identifiers; if a finding cannot be resolved from this evidence, say so "
                                "explicitly (honest-decline doctrine, ADR-0058)")}}
            answer_rev = _synth(rev_evidence, "revision")
            passes.append(("revision", answer_rev))
            conf_rev, conf_rev_source = _resolve_confidence(answer_rev)
            db.add_event(run_id, "stage.synthesize.revision", agent=answer_rev.get("model"),
                         payload={"stated_confidence": conf_rev, "confidence_source": conf_rev_source,
                                  "n_findings_input": len(findings)})
            _check_cancel()
            # ADR-0080: el MISMO gate (_gate) que corrió sobre pass1/pass2 — predicados de identificadores +
            # fuga del padre + positive_claim_requires_citations; conserva pass1_admissible y competence_gate.
            checks2 = _gate(answer_rev, bundle, thread_snapshot, run, pass_no="revision")
            checks2["pass1_admissible"] = checks1["admissible"]
            checks2["competence_gate"] = competence.compact(comp)
            adm2 = checks2["admissible"]
            db.add_event(run_id, "stage.deterministic_gate", tool="verify_output",
                         payload=checks2, level="info" if adm2 else "warning")
            _check_cancel()
            db.add_event(run_id, "stage.audit.start", agent="composite-auditor",
                         payload={"revision_round": 1})
            audit2 = composite_auditor.audit(
                claim={"direct_answer": answer_rev["direct_answer"],
                       "stated_confidence": answer_rev.get("stated_confidence")},
                evidence=_compact_evidence(bundle), deterministic_checks=checks2,
                required_because=bundle["decision_state"]["state"], caller=panel_caller)
            panel_rows_all.extend(audit2.get("panel", []))
            db.add_event(run_id, "stage.audit.verdict", agent="composite-auditor",
                         payload=_verdict_payload(audit2, 1),
                         level="info" if audit2["verdict"] != "REVISE" else "warning")
            # nada se borra: la versión inicial y su veredicto quedan en el registro. ADR-0081 (D): también el
            # cuórum inicial (familias/lentes/quorum/panel_incomplete*) cuando audit() lo trae.
            audit_initial = {k: audit_result[k] for k in AUDIT_INITIAL_KEYS}
            audit_initial.update({k: audit_result[k] for k in AUDIT_INITIAL_QUORUM_KEYS if k in audit_result})
            answer_initial = {"direct_answer": answer["direct_answer"],
                              "stated_confidence": answer.get("stated_confidence"),
                              "absence_kind": answer.get("absence_kind"),
                              "gap_flags": answer.get("gap_flags", [])}
            revision.update(performed=True, findings_used=findings,
                            initial_verdict=audit_result["verdict"],
                            final_verdict=audit2["verdict"],
                            initial_checks_admissible=checks["admissible"])
            answer, checks = answer_rev, checks2
            final_conf, final_source = conf_rev, conf_rev_source
            audit_result = audit2
        bundle = composite_auditor.apply_to_bundle(bundle, audit_result, _evidence_ids(bundle))

        # 7) frozen record (backend-persisted; the webapp only reads — ADR-0047 d.2).
        # El usage cuenta TODOS los paneles (con revisión hay dos — ADR-0067).
        embed_tokens = max(0, _embed_usage_snapshot() - embed_t0)
        token_usage = _token_usage(passes, {"panel": panel_rows_all}, embed_tokens, plan=plan)
        # ADR-0078 corrector: UNA sola sede de re-parseo. Si evidence_cited LLEGÓ como string (el wrapper
        # real lo guarda en evidence_cited_raw; un sintetizador stub puede dejarlo en evidence_cited),
        # _normalize_citations recibe ESE string y declara 'string-reparsed' | 'string-unparseable'; si
        # llegó lista, 'list'; si no vino, 'absent'. El registro ya no puede decir "llegó lista" junto a
        # un crudo string.
        citations, citations_schema, ev_raw = _citations_of(answer)
        # ADR-0080 (E/G): la ESCALERA de soporte por cita (unresolved → resolved → passage_delivered →
        # supported|unsupported), aditiva dentro de cada cita, jamás fundida en un solo bool; el resumen
        # cuenta por peldaño. El helper vive en verify_output (rebanada E); su ausencia se declara.
        citations, citations_support_summary = _support_states(citations, bundle, audit_result)
        frozen = {
            "render_contract_version": RENDER_CONTRACT_VERSION,
            "run_id": run_id, "user_id": run["user_id"], "question": run["question"],
            "measured_at": bundle["stamp"],
            "store_at_retrieval": {"store_version": _safe(resolve_id.store_version),
                                   "index_version": _index_version()},
            "retrieval_summary": bundle["retrieval_summary"],
            "decision_state": bundle["decision_state"],
            # block 4 (ADR-0051): which decider fired the fallback + the two-pass confidence story
            "fallback": bundle["fallback"],
            "confidence": {
                "pass1": conf1, "pass1_source": conf1_source,
                "pass2": conf2, "pass2_source": conf2_source,
                # ADR-0065: el instrumento in-line PERSISTE junto al elicitado — un cambio de
                # instrumento se declara y ambas series sobreviven (continuidad de la calibración)
                "pass1_inline": pass1.get("stated_confidence_inline"),
                "pass2_inline": (pass2.get("stated_confidence_inline") if trigger else None),
                # ADR-0067: la confianza de la pasada de revisión (null cuando no hubo revisión)
                "revision": conf_rev,
                "revision_source": conf_rev_source,
                "delta": delta,
                "final": final_conf,
                # ADR-0057/0065: the EXACT provenance field the UI renders — a recovered or derived
                # value is a value (state), but source says HOW it exists:
                # "stated-second-elicitation" (ADR-0065, the authoritative dedicated elicitation) |
                # "stated" | "recovered-from-malformed-tool-call" | "derived-min-of-subclaims" | null
                "source": final_source,
                "by_subclaim": answer.get("confidence_by_subclaim"),
                # three-state discipline: a null NEVER masquerades as a measurement
                "state": "value" if final_conf is not None else "absent-not-calibratable",
            },
            "audit": bundle["audit"],
            # --- ciclo de revisión (ADR-0067): AMBAS versiones persisten — nada se borra ------------
            # audit_initial/answer_initial son null-declarados cuando no hubo revisión (3 estados,
            # jamás ausencia silenciosa); revision.skipped_reason explica los REVISE sin intento.
            "audit_initial": audit_initial,
            "answer_initial": answer_initial,
            "revision": revision,
            "answer": {"direct_answer": answer["direct_answer"],
                       "stated_confidence": answer.get("stated_confidence"),
                       "absence_kind": answer.get("absence_kind"),
                       "gap_flags": answer.get("gap_flags", []),
                       "model": answer.get("model"),
                       # ADR-0081 (B): lo PEDIDO (model, con su fuente) vs lo que la API DIJO (model_reported);
                       # relation exact | prefix (NEUTRO) | different (objeción) | not-reported (stub/gris)
                       "model_source": answer.get("model_source"),
                       "model_reported": answer.get("model_reported"),
                       "relation": answer.get("relation") or models.relation(answer.get("model"),
                                                                             answer.get("model_reported"))},
            # --- ADR-0081 (B): procedencia MEDIDA del modelo que corrió — generación + fuente, tabla, firma del
            # panel, roles resueltos EN esta corrida, ran {requested, reported, relation, thinking_state} por pasada
            # y por juez; roles.planner COPIADO de plan_json.judgment.planner (no re-resuelto). Nada de constantes.
            # S7 (N): la firma se calcula con los MISMOS 8 roles del snapshot de stage.models → frozen.models.
            # panel_signature == stage.models.panel_signature == audit.panel_source.panel_signature (UNA identidad de
            # configuración por corrida; medido en smoke_run_pipeline).
            "models": models.provenance_block({"synthesizer": synth_role, "elicitation": elicit_role}, passes,
                                              ((plan or {}).get("judgment") or {}).get("planner"),
                                              bundle["audit"].get("panel"),
                                              signature_roles=models_snapshot["roles"]),
            # --- contrato §5, ADR-0060 -------------------------------------------------------------
            # alternatives_considered: null (ausente) NO es [] (se consideraron y no había). Tres
            # estados, como en todo este contrato.
            "alternatives_considered": answer.get("alternatives_considered"),
            "reasoning": {
                # SELF-REPORT del modelo, con la sección y el tier resueltos por TABLA (§4): el modelo
                # sólo elige el nombre y cita el criterio, así que no puede citar una sección que no
                # existe. `criterion_matches_catalog` dice si la cita vino de verdad del catálogo.
                "framework_applied": reasoning_catalog.resolve(
                    answer.get("framework_applied"), answer.get("framework_criterion"),
                    answer.get("framework_reason") or ""),
                # y el contrapeso honesto: lo que el PIPELINE aplica, pase lo que pase con la etiqueta
                "structural_frameworks": reasoning_catalog.structural_frameworks(),
            },
            "agents_invoked": _agents_invoked(audit_result, checks, plan),
            # --- tapón 3 (ADR-0061): el plan declarado viaja congelado; su ausencia se DECLARA -----
            "plan": plan,
            "plan_declared": plan is not None,
            # un plan hecho para OTRA pregunta no puede pasar por el juicio de ésta (misma disciplina
            # que question_matches_run, ADR-0044)
            "plan_question_matches_run": (plan.get("question") == run["question"]) if plan else None,
            "citations": citations,
            # ADR-0078: cómo llegó evidence_cited (lista / string re-parseado / string no parseable /
            # ausente) y cuántas citas válidas salieron — el lector distingue "citó 0" de "citó y se perdió"
            "citations_schema": citations_schema,
            "citations_support_summary": citations_support_summary,   # ADR-0080: {n, by_state, state}
            "evidence_cited_raw": ev_raw,   # el string crudo tal cual llegó; None = NO llegó string
            # --- ADR-0080 (G): la compuerta y el lazo, congelados ---------------------------------------
            # competence = el bloque ÍNTEGRO de competence.evaluate (+decision); search_ledger = el plan y
            # las rondas (el bundle.path_b íntegro sigue en bundle_json). Sin ronda: rounds [] y state.
            "competence": comp,
            "search_ledger": bundle["search_ledger"],
            "deterministic_checks": checks,
            "token_usage": token_usage,
            "usage_raw": {"passes": {label: p.get("usage", {}) for label, p in passes},
                          # suma de TODOS los paneles (con revisión hay dos — ADR-0067)
                          # corrector ADR-0080: TODA fila con usage medido (también un juez agotado que cobró)
                          "panel_total": {
                              "input_tokens": sum(_usage_in_out(r.get("usage"))[0]
                                                  for r in panel_rows_all if isinstance(r.get("usage"), dict)),
                              "output_tokens": sum(_usage_in_out(r.get("usage"))[1]
                                                   for r in panel_rows_all if isinstance(r.get("usage"), dict))}},
            "bundle_identity": bundle["bundle_identity"],
            "question_matches_run": bundle["question"] == run["question"],
        }
        # --- investigación (ADR-0079) — derivado AL CONGELAR desde las columnas + el sobre persistido ---
        parent_row = db.get_run(run["parent_run_id"]) if run.get("parent_run_id") else None
        frozen["thread"] = {
            "thread_id": run.get("thread_id"), "parent_run_id": run.get("parent_run_id"),
            "turn_no": run.get("turn_no"), "turn_kind": run.get("turn_kind"),
            "parent_state": parent_row.get("state") if parent_row else None,
            "parent_run_no": parent_row.get("run_no") if parent_row else None,
            "root_question_id": run.get("root_question_id"),
            # T5 (integrador, ADR-0079): el run_no de la RAÍZ — insumo de la etiqueta 'T-<run_no raíz>' que el
            # PDF (record_pdf._thread_label) imprime en CUALQUIER turno; sin él declara 'T-?'. Raíz real o
            # VIRTUAL (padre pre-ADR): la fila cuyo run_id es thread_id. None declarado si no consta.
            "root_run_no": _root_run_no(run),
            # qué componente recibió el snapshot (None = no había; False = firma sin la llave) — el panel
            # NUNCA (por diseño: evidencia limpia + deterministic_checks.thread)
            "context_delivery": thread_delivery,
        }
        # el INSUMO que el modelo vio (igual que `plan`): null con razón cuando no viajó — tres estados
        frozen["thread_context"] = thread_snapshot
        frozen["thread_context_skipped_reason"] = (None if thread_snapshot is not None
                                                   else thread_delivery["skipped_reason"])
        # el padre es INMUTABLE: el sha que el snapshot tomó al encolar debe ser el sha del padre AHORA
        # (sobre el blob sin frozen_at/closed_by — THREAD_SHA_RULE). None declarado sin snapshot/padre.
        if parent_row is None:
            matches, matches_state = None, "no-parent"
        elif thread_snapshot is None:
            matches, matches_state = None, "no-snapshot"
        elif thread_snapshot.get("parent_frozen_sha256") is None:
            # None == None sería un True vacío: sin blob del padre no hay nada que casar — se declara
            matches, matches_state = None, "parent-without-frozen-record"
        else:
            matches = thread_snapshot["parent_frozen_sha256"] == frozen_sha256(parent_row.get("frozen_record_json"))
            matches_state = "checked"
        frozen["thread_parent_matches_run"] = matches
        frozen["thread_parent_matches_run_state"] = matches_state
        frozen["thread_parent_matches_run_rule"] = THREAD_SHA_RULE
        # (E) PRECEDENTE ≠ EVIDENCIA: el turno anterior entra en la serie de LETRAS (precedent.serialize_disjoint
        # sobre precedent.turn_item, 'l'='A', admissible_as_evidence False); `citations` (números) NO cambia de
        # forma. validate_disjoint es el gate determinista de que ninguna serie produjo la etiqueta de la otra.
        # Corrector ADR-0079 — precedente SÓLO si el padre está 'closed' (ADR-0053 / db.closed_runs: una corrida
        # es precedente únicamente tras la clausura humana explícita). Un padre awaiting_closure / failed /
        # cancelled sigue siendo padre válido (su snapshot viaja como thread_context, declarado en §B) pero NO
        # lleva letra: precedent_citations [] + precedent_citations_state declarado (tres estados).
        if parent_row is None:
            pc_state = "no-parent"
        elif parent_row.get("state") == "closed":
            pc_state = "checked"
        elif parent_row.get("frozen_record_json"):
            pc_state = "parent-not-closed"
        else:
            pc_state = "parent-without-frozen-record"
        parent_items = [precedent.turn_item(parent_row)] if pc_state == "checked" else []
        serialized = precedent.serialize_disjoint(citations, parent_items)
        frozen["precedent_citations"] = serialized["precedent"]
        frozen["precedent_citations_state"] = pc_state
        checks["disjoint_series"] = precedent.validate_disjoint(
            {"evidence": citations, "precedent": frozen["precedent_citations"]})
        checks["disjoint_series_state"] = ("no-parent" if parent_row is None
                                           else "checked" if pc_state == "checked" else "parent-not-precedent")
        # (F) procedencia: el valor es el de la columna (derivado al encolar). Corrector ADR-0079: la FUENTE
        # también es la de encolar — new_run la persiste en el sobre (envelope.origin) y aquí se COPIA; la
        # re-derivación al ejecutar viaja aparte como source_at_execution (dato secundario), jamás en `source`.
        # Sobre sin origin (encolado antes de este corrector) → source 'unknown-at-enqueue' declarado.
        origin_now = run_origin()
        origin_enq = thread_env.get("origin") if isinstance(thread_env.get("origin"), dict) else None
        frozen["origin"] = {"value": run.get("origin"),
                            "source": (origin_enq["source"]
                                       if origin_enq and origin_enq.get("value") == run.get("origin")
                                       else "unknown-at-enqueue (envelope without origin)"
                                       if run.get("origin") is not None else None),
                            "source_at_execution": {"value": origin_now["value"], "source": origin_now["source"],
                                                    "same_value_as_column": origin_now["value"] == run.get("origin")},
                            "note": None if run.get("origin") is not None else "unknown-pre-adr-0079"}
        # corrector ADR-0079: procedencia plan↔padre — el plan declaró un padre y un sha (build_plan); la
        # corrida tiene los suyos. Tres estados: None con estado cuando no hay plan, el plan es anterior a la
        # declaración, o no hay padre/snapshot en ninguno de los dos lados.
        env_snapshot = thread_env.get("snapshot") if isinstance(thread_env.get("snapshot"), dict) else None
        if plan is None:
            ppm, ppm_state = None, "no-plan"
        elif "thread_parent_run_id" not in plan:
            ppm, ppm_state = None, "plan-predates-thread-declaration"
        elif plan.get("thread_parent_run_id") is None and run.get("parent_run_id") is None:
            ppm, ppm_state = None, "no-parent"
        else:
            ppm, ppm_state = plan.get("thread_parent_run_id") == run.get("parent_run_id"), "checked"
        frozen["plan_parent_matches_run"] = ppm
        frozen["plan_parent_matches_run_state"] = ppm_state
        run_sha = (env_snapshot or {}).get("parent_frozen_sha256")
        if plan is None:
            psm, psm_state = None, "no-plan"
        elif "thread_parent_frozen_sha256" not in plan:
            psm, psm_state = None, "plan-predates-thread-declaration"
        elif plan.get("thread_parent_frozen_sha256") is None and run_sha is None:
            psm, psm_state = None, "no-snapshot"
        else:
            psm, psm_state = plan.get("thread_parent_frozen_sha256") == run_sha, "checked"
        frozen["plan_snapshot_matches_run"] = psm
        frozen["plan_snapshot_matches_run_state"] = psm_state
        # (G) ejes del episodio — por tabla (EPISODE_AXES_MAP), clase derived-at-freeze
        frozen["episode_axes"] = episode_axes(
            decision_state=bundle["decision_state"]["state"], absence_kind=answer.get("absence_kind"),
            verdict=audit_result.get("verdict"), run_state="awaiting_closure",
            retrieval_mode=bundle["retrieval_summary"].get("mode"), origin=run.get("origin"),
            plan_declared=plan is not None, closed=False, thread=frozen["thread"])
        # LOTE-02·3: the list-row epistemic summary is derived HERE, at freeze — never at serve time
        # (the frozen-counter discipline: a list row must not re-derive what the record froze).
        # LOS DOS EJES DE NICHO (2026-09-05, decisión del fundador: "catálogo medido + panel para
        # el resto"). Son fuentes DISTINTAS y se guardan separadas — el juicio jamás tapa a la
        # medición:
        #   · catalogo: RN* (tipo de dato) y N* (dominio) LEÍDOS de las fichas del corpus que la
        #     respuesta citó, con su cobertura declarada. Es medición y cuesta cero.
        #   · panel: N* JUZGADO por los cuatro jueces sobre la respuesta completa — cubre el 100%
        #     de las corridas, incluidas las que citaron pura literatura sin ficha.
        # Enfrentarlos es el lazo de calibración del panel: donde el catálogo alcanza, se puede ver
        # si el panel coincide con lo que las fichas aprobadas ya declaraban.
        # OJO con la llave: el registro congelado las llama `citations`, no `evidence`. Leer la
        # llave equivocada NO truena — devuelve cobertura "0 de 0", que se lee como una corrida
        # sin evidencia catalogada. Un cableado roto disfrazado de caso limpio (2026-09-05).
        nichos = {
            "catalogo": niche_catalog.niches_of_evidence(frozen.get("citations")),
            "panel": audit_result.get("domain_niches"),
        }
        epistemic_summary = {"retrieval_mode": bundle["retrieval_summary"]["mode"],
                             "verdict": audit_result["verdict"],
                             "confidence_state": frozen["confidence"]["state"],
                             "panel_n_valid": audit_result["n_valid"],
                             "niches": nichos,
                             # ADR-0079 (regla frozen-counter: derivado AQUÍ, la lista no re-deriva)
                             "thread_id": run.get("thread_id"), "turn_no": run.get("turn_no"),
                             "origin": run.get("origin"),
                             # ADR-0080: competente (True|False|null con razón en frozen.competence) y
                             # cuántas rondas de búsqueda corrieron (null = el harness no midió)
                             "competent": comp["competent"],
                             "n_search_rounds": bundle["search_ledger"].get("n_rounds"),
                             # ADR-0081: generación de modelos de la corrida y familias que votaron válidas (null =
                             # el audit() del árbol no midió cuórum por familias) — ListaCorridas/Banco: "3/4 · 1 familia"
                             "model_generation": synth_role["generation"],
                             "panel_n_families_valid": audit_result.get("n_families_valid")}
        frozen["niches"] = nichos
        _finish(run_id, "awaiting_closure", {"verdict": audit_result["verdict"]},
                bundle_json=json.dumps(bundle, ensure_ascii=False, default=str),
                frozen_record_json=json.dumps(frozen, ensure_ascii=False, default=str),
                usage_json=json.dumps(token_usage, ensure_ascii=False, default=str),
                epistemic_summary_json=json.dumps(epistemic_summary, ensure_ascii=False))
    except RunCancelled:
        _finish(run_id, "cancelled", {}, level="warning",
                usage_json=json.dumps(_usage_now(), ensure_ascii=False, default=str))
    except Exception as e:
        db.add_event(run_id, "error", payload={"error": f"{type(e).__name__}: {str(e)[:400]}"},
                     level="error")
        _finish(run_id, "failed", {}, level="error",
                error=f"{type(e).__name__}: {str(e)[:400]}",
                usage_json=json.dumps(_usage_now(), ensure_ascii=False, default=str))


def _finish(run_id, state, payload, level="info", **values):
    """ADR-0078 corrector — cierre terminal del worker, CONDICIONAL a que la fila siga 'running'
    (db.finish_run). Si el reaper ya la sentenció failed/worker-lost (o alguien la canceló) mientras el
    hilo seguía vivo, NO se pisa: queda UN evento run.state.conflict {attempted, found, ignored: true} y el
    registro conserva un solo veredicto terminal. Devuelve True si el cierre se escribió."""
    ok = db.finish_run(run_id, expected_state="running", state=state, finished_at=db._now(), **values)
    if ok:
        db.add_event(run_id, "run.state", payload={"state": state, **payload}, level=level)
        return True
    row = db.get_run(run_id) or {}
    db.add_event(run_id, "run.state.conflict",
                 payload={"attempted": state, "found": row.get("state"), "found_error": row.get("error"),
                          "ignored": True,
                          "note": "finished-after-reap: the worker outlived the reaper's verdict; the row "
                                  "was NOT overwritten (ADR-0078)"},
                 level="error")
    return False


def _safe(fn):
    try:
        return fn()
    except Exception:
        return None


def _index_version():
    try:
        import server
        return server._index_version()
    except Exception:
        return None


def close_run(run_id, by):
    """Explicit closure (the requirement for a run to become precedent — pending closure ADR): freezes
    the record (frozen_at) and stops further measurement mutation. ratings[] append AFTER this point."""
    run = db.get_run(run_id)
    if run is None:
        return None
    if run["state"] != "awaiting_closure":
        return {"closed": False, "state": run["state"],
                "note": "only an awaiting_closure run can be closed"}
    now = db._now()
    frozen = json.loads(run["frozen_record_json"] or "{}")
    frozen["frozen_at"] = now.isoformat(timespec="seconds")
    frozen["closed_by"] = by
    db.update_run(run_id, state="closed", frozen_at=now, closed_by=by,
                  frozen_record_json=json.dumps(frozen, ensure_ascii=False, default=str))
    db.add_event(run_id, "run.state", payload={"state": "closed", "closed_by": by})
    return {"closed": True, "run_id": run_id, "frozen_at": frozen["frozen_at"]}


def new_run(user_id, question, entities=None, plan_json=None, parent_run_id=None, from_question_id=None):
    """Encola una corrida. ADR-0079: la investigación se DERIVA aquí (derive_thread — servidor, jamás del
    cliente) y la procedencia también (run_origin). Con parent_run_id: ParentNotFound (404) /
    ParentNotTerminal (409) suben ANTES de insertar — la capa HTTP las traduce. `from_question_id` sólo
    siembra root_question_id de una RAÍZ (el sello mark_question_used sigue siendo de app.py). El plan:
    un plan_id se consume por UNA corrida (409 plan_already_used en app.py) — el hijo declara plan nuevo
    o el llamador copia plan_json; aquí sólo se persiste lo que llegue."""
    from sqlalchemy.exc import IntegrityError
    run_id = uuid.uuid4().hex
    entities = list(entities or [])
    origin = run_origin()
    ultimo_error = None
    for _intento in range(5):
        thread = derive_thread(run_id, question, entities, parent_run_id=parent_run_id,
                               from_question_id=from_question_id)
        envelope = thread["envelope"]
        # corrector ADR-0079: la PROCEDENCIA completa ({value, source, raw?, truncated?}) se persiste al
        # encolar dentro del sobre — el registro congelado copia esta fuente en vez de re-derivarla.
        envelope["origin"] = origin
        try:
            db.create_run(run_id, user_id, question, entities, plan_json=plan_json,
                          parent_run_id=thread["parent_run_id"], thread_id=thread["thread_id"],
                          turn_no=thread["turn_no"], turn_kind=thread["turn_kind"],
                          thread_context_json=json.dumps(envelope, ensure_ascii=False, default=str),
                          origin=origin["value"], root_question_id=thread["root_question_id"])
            break
        except IntegrityError as e:
            # corrector ADR-0079: SÓLO la carrera de turn_no (índice único ux_runs_thread_turn) se reintenta
            # re-derivando desde la BD; cualquier otra violación sube tal cual (SQLite: 'runs.thread_id,
            # runs.turn_no'; Postgres: 'ux_runs_thread_turn').
            msg = str(e.orig).lower()
            if "turn_no" not in msg and "ux_runs_thread_turn" not in msg:
                raise
            ultimo_error = e
    else:
        raise ultimo_error
    snap = envelope.get("snapshot") or {}
    # ADR-0081 (F): run_no y root_run_no nacen en la BD — la fila tras el INSERT (db.get_run pasa por db._detail_select,
    # el JOIN a la raíz de S4: raíz real → su run_no; hijo de raíz VIRTUAL (padre pre-ADR-0079) → el del padre; NULL
    # declarado si no consta). S7 (N): sin fallback a _root_run_no — es la MISMA verdad (medido en smoke_run_pipeline
    # sobre todas las corridas del gate) y una fila sin la llave debe fallar en voz alta, no derivarse en silencio.
    row = db.get_run(run_id)
    if row is None:
        # corrector ADR-0081 (F): la fila recién insertada DEBE ser legible; un None aquí es un fallo de BD, no un estado a
        # tolerar — se falla en voz alta (coherente con S7: sin fallback silencioso) en vez de mezclar una guardia con un
        # `.get` que la contradecía (AttributeError latente).
        raise RuntimeError(f"new_run: fila {run_id} no legible tras el INSERT (db.get_run devolvió None)")
    root_run_no = row["root_run_no"]
    db.add_event(run_id, "run.state", payload={
        "state": "queued", "origin": origin, "run_no": row.get("run_no"),
        "thread": {"thread_id": thread["thread_id"], "turn_no": thread["turn_no"],
                   "root_run_no": root_run_no,
                   "turn_kind": thread["turn_kind"], "parent_run_id": thread["parent_run_id"],
                   "context": ("built" if envelope.get("snapshot") is not None else "skipped"),
                   "context_skipped_reason": envelope.get("skipped_reason"),
                   "context_bytes": snap.get("bytes"),
                   "n_comments_included": ((snap.get("human_comments") or {}).get("n_included"))}})
    return run_id


# --- worker threads ----------------------------------------------------------------------------------

_STOP = threading.Event()

# ADR-0078: umbral del segador de corridas huérfanas (segundos sin latido). Default 900 = 3× el umbral
# de VISTA HEARTBEAT_STALE_S=300 de app.py, a propósito: la vista sólo AVISA ("sin evento por N min")
# y puede avisar temprano sin costo; el reaper MATA (running -> failed, irreversible) y tiene que
# tolerar etapas legítimamente largas — una ronda de consejo futura (varios jueces en serie) o un
# panel con reintentos puede pasar 5 min sin emitir evento. Matar sólo lo que lleva 3× el umbral de
# aviso deja una banda donde la UI ya dice "sospechoso" y el sistema todavía no ha sentenciado.
REAP_STALE_S_DEFAULT = 900


def _env_int_tolerante(name, default):
    """(valor, fuente) — igual que answer_pipeline._env_int_src: env vacía / no numérica / <= 0 -> default
    DECLARADO (ADR-0078 corrector: `int(os.environ.get(...))` al importar tumbaba el servicio con
    WITT_REAP_STALE_S='' en Dokploy — la única env del ADR cuyo fallo mataba el proceso)."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default, f"default-unset:{name}"
    try:
        v = int(raw)
    except ValueError:
        return default, f"default-invalid-env:{name}"
    return (v, f"env:{name}") if v > 0 else (default, f"default-invalid-env:{name}")


REAP_STALE_S, REAP_STALE_S_SOURCE = _env_int_tolerante("WITT_REAP_STALE_S", REAP_STALE_S_DEFAULT)

# ADR-0078 corrector: identidad del PROCESO en claimed_by. El nombre de hilo ('run-worker-0') es idéntico
# en cada generación del proceso: ni el reaper ni la vista podían distinguir el hilo vivo del muerto.
# claimed_by = '<boot_id>:<pid>:<thread>' (<= 64 chars: 8 + 1 + <=7 + 1 + nombre de hilo).
WORKER_BOOT_ID = uuid.uuid4().hex[:8]


def worker_id_for(thread_name):
    return f"{WORKER_BOOT_ID}:{os.getpid()}:{thread_name}"[:64]


def worker_loop(poll_seconds=1.0):
    # ADR-0078: boot_id:pid:hilo es el worker_id que queda en runs.claimed_by (procedencia del reclamo)
    worker_id = worker_id_for(threading.current_thread().name)
    while not _STOP.is_set():
        run = db.claim_next_queued(worker_id)
        if run is None:
            time.sleep(poll_seconds)
            continue
        execute_run(run)


def _reap_once(stale_s, label, reason="worker-lost"):
    """Una pasada del segador. Su fallo (BD caída un instante) NO tumba el hilo ni el arranque —
    §6 no-hang: se deja huella en stderr y se reintenta en la siguiente ronda."""
    try:
        segadas = db.reap_stale_running(stale_s, reason=reason, stale_s_source=REAP_STALE_S_SOURCE)
        if segadas:
            print(f"[runs.reaper] {label}: {len(segadas)} corrida(s) running "
                  + ("sin worker en este proceso" if reason == "worker-lost-restart"
                     else f"sin latido por >{stale_s}s")
                  + f" -> failed {reason} (ADR-0078): {segadas}", file=sys.stderr)
        return segadas
    except Exception as e:
        print(f"[runs.reaper] {label}: reap_stale_running falló ({type(e).__name__}: {str(e)[:160]}) — "
              "se reintenta en la siguiente ronda", file=sys.stderr)
        return []


def reaper_loop(stale_s=None):
    """Hilo daemon 'run-reaper' (ADR-0078): repite reap_stale_running cada stale_s/3 segundos — tres
    oportunidades por umbral, así una corrida huérfana se sentencia entre stale_s y 4/3·stale_s
    después de su último latido, nunca mucho más tarde. Termina con _STOP."""
    stale_s = REAP_STALE_S if stale_s is None else stale_s
    period = max(1.0, float(stale_s) / 3.0)
    while not _STOP.wait(period):
        _reap_once(stale_s, "ronda")


def start_workers(n=2, reap_stale_s=None):
    """In-process daemon workers (single uvicorn process, ADR-0048). sklearn is already preloaded on the
    MAIN thread by the app lifespan before workers start — the 1800s deadlock cannot recur here.

    ADR-0078 (corrector 2026-09-14): ANTES de lanzar hilos corre reap_stale_running(0, reason=
    'worker-lost-restart') UNA vez — con `--workers 1` (ADR-0048) TODA fila 'running' al nacer el proceso
    es huérfana por construcción (ningún hilo de este proceso la reclamó; el anterior murió por redeploy
    u OOM), latiera hace 5 min o hace 5 h. Se sentencian failed/worker-lost, NUNCA se re-encolan. Luego
    un hilo daemon 'run-reaper' aplica el umbral WITT_REAP_STALE_S cada WITT_REAP_STALE_S/3 s para los
    hilos que mueran en caliente. Por qué 900 > HEARTBEAT_STALE_S=300: ver REAP_STALE_S arriba (la vista
    avisa, el reaper mata). `reap_stale_s` solo parametriza el hilo periódico (gates)."""
    stale_s = REAP_STALE_S if reap_stale_s is None else reap_stale_s
    print(f"[runs.reaper] arranque: REAP_STALE_S={stale_s} ({REAP_STALE_S_SOURCE}); boot_id={WORKER_BOOT_ID}",
          file=sys.stderr)
    _reap_once(0.0, "arranque", reason="worker-lost-restart")
    for i in range(n):
        threading.Thread(target=worker_loop, name=f"run-worker-{i}", daemon=True).start()
    threading.Thread(target=reaper_loop, args=(stale_s,), name="run-reaper", daemon=True).start()


def stop_workers():
    _STOP.set()

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
from lib import (agent_matrix, answer_pipeline, catalog_cards, composite_auditor, council, figures, models,  # noqa: E402
                 reasoning_catalog, resolve_id, verify_output)   # ADR-0082: council (C2) y catalog_cards (C1) en DURO;
                                                                 # ADR-0083 (F1): figures en DURO (stdlib puro)
try:
    # ADR-0080 (C), rebanada C2: el harness de búsqueda. Import TOLERANTE — si la rebanada aún no aterrizó,
    # runs.py declara `search_ledger.state 'harness-unavailable'` y la Ruta B corre por el camino de hoy.
    from lib import search_harness  # noqa: E402
except ImportError:   # pragma: no cover — depende del árbol
    search_harness = None
try:
    # ADR-0084 (G): el localizador web — disponibilidad EN LA LLAMADA (provider_state), vocabularios cerrados y encabezado del
    # frozen (lib/web_locator.py, rebanada W2). Import TOLERANTE: sin la rebanada en el árbol, frozen.web_locator y
    # deterministic_checks.web_locator lo DECLARAN ('tool-unavailable (ADR-0084: …)') y nada más cambia.
    from lib import web_locator  # noqa: E402
except ImportError:   # pragma: no cover — depende del árbol
    web_locator = None

RENDER_CONTRACT_VERSION = "1.14"  # ADR-0086 (una imagen que aporta una persona es ATESTIGUADA, jamás evidencia ni cita):
                                  # +attested_images {state ∈ attestations.ATTESTED_STATES_*, items[] SIN bytes (identidad,
                                  # procedencia, consentimiento, licencia declarada, quién la vio), delivery (el sintetizador
                                  # NO vio píxeles), vision, vocabulary}, +deterministic_checks.attested_images (2 duros + 1
                                  # informativo), +human_attestations.images[] (captions al sintetizador y al consejo),
                                  # +epistemic_summary.attested_*, +token_usage.attested_images, +agents_invoked[attestations],
                                  # +thread_context.parent_attested_images, eventos stage.attestations.*. 1.13 = ADR-0084 (la web LOCALIZA identificadores, jamás es fuente): +web_locator {state ∈ web_locator.WEB_STATES_*,
                                  # state_vocabulary, module_version 'wl-1', resolver_version 'wlr-1', tool_version 'bws-1'|null, provider, provider_source,
                                  # gate 'directive-only', entered_by, directive_requirement_ids, families_order_rule, n_* (int; AUSENTES bajo
                                  # kill-switch/tool-unavailable), queries[], located[] (URL hallada SÓLO aquí), unresolved[] (title_web SÓLO aquí),
                                  # gap_flags_typed[], allowed_hosts, generic_doi_rule, resolver_rules[], cost (PROYECCIÓN), quota, text_policy,
                                  # kill_switch? (sólo bajo off), rule} SIEMPRE presente en >= 1.13 + deterministic_checks.web_locator (4 predicados de
                                  # verify_output.web_predicates, 3 gating; {state} bajo kill-switch) + citations[].located_via ('web'|null) +
                                  # citations_support_summary.n_located_via_web + token_usage.web_locator / estimated_cost_usd_total_projected /
                                  # total_class / by_stage.search.web_locator_usd_projected (estimated_cost_usd INTACTO) + epistemic_summary.
                                  # {web_locator_state, web_n_located, web_n_unresolved} + agents_invoked fila 'web_locator (…)' + answer.gap_flags
                                  # con <= 2 strings de CONTEO por clase (jamás URLs: viajan al modelo del turno siguiente) + search_ledger.plan.
                                  # families_order_rule + selection.pool_admission_rule/tie_break_web_located. Evento NUEVO stage.web.locate (agent
                                  # 'web_locator', UNO por consulta ENVIADA, ids y hosts sin URLs); stage.search.source(web) += provider/n_*;
                                  # stage.path_b += n_web_located/n_web_unresolved; stage.deterministic_gate += web_locator_state. 0 ítems con
                                  # source 'web': los identificadores se MATERIALIZAN por Europe PMC en la misma ronda (source 'europepmc',
                                  # source_family 'web', identifier_provenance 'web-located:<regla>'). TODO aditivo; kill-switch WITT_WEB_LOCATOR=off
                                  # (explícito o derivado sin BRAVE_API_KEY) = frozen 1.12 byte a byte salvo EXACTAMENTE WEB_DECLARED_EXCEPTIONS (3).
                                  # Historial 1.12 — ADR-0083 (figuras como evidencia OBSERVADA): +figures {state, module_version 'fig-1', parser_version
                                  # 'jats-fig-1', license_table_version 'lt-1', license_table, license_table_rule, license_table_env_ignored,
                                  # mechanism 'supplementaryFiles-zip', cache {dir_source, dir_state, ttl_days, cache_max_mb, evicted_n},
                                  # budget {total_s, used_s, over_budget}, caps {…{value, source}}, n_papers_eligible/selected/with_xml,
                                  # n_figures, n_with_caption, n_fetched, n_verified, n_not_fetched, n_error (corrector), n_mismatch, n_embeddable, n_panel_view,
                                  # n_unknown_license, n_cited, zfin_figures_state, selection {rule, n_sent_to_panel_by_lens}, vision {state,
                                  # enabled, lenses, lenses_source, rule, openai_detail, sent, cost_projection, selection, delivery}, items
                                  # [FigureItem SIN bytes: id '<PMCID>#<fig_id>', sha256, license, embeddable, panel_view, bytes_state,
                                  # raw_ref (source-pointer), cited_by_answer, seen_by_lenses, delivered_to_synthesizer, class],
                                  # vocabulary, kill_switch?} + citations[].kind gana el literal 'figure' + citations[].figure_verification
                                  # {bytes, content, figure_id} (sólo kind figure) + citations_support_summary.figure_citations +
                                  # deterministic_checks.figures (5 predicados de verify_output.figure_predicates — F2) + audit.panel[].
                                  # saw_figures / figure_readings? / figure_readings_class? + audit.vision (composite_auditor — F3) +
                                  # token_usage.by_stage.panel.by_model[*].vision (PROYECCIÓN por fórmula pública) + agents_invoked fila
                                  # 'figures (lib/figures.py — …)' + epistemic_summary.{figures_state, figures_n_verified, figures_n_cited}.
                                  # Eventos NUEVOS (agent 'figures'): stage.figures.{plan, paper{start|done}, figure, summary};
                                  # stage.audit.judge += {figures_sent, figures_sha256}; stage.deterministic_gate += figures_state.
                                  # El sintetizador ve caption + metadatos (PROMPT_FIGURE_KEYS) y JAMÁS bytes; lo que la imagen dice es
                                  # JUICIO de dos lentes (figure_readings). TODO aditivo; kill-switch WITT_FIGURES=0 = frozen 1.11 salvo
                                  # EXACTAMENTE {render_contract_version, figures{state, kill_switch}, deterministic_checks.figures{state}}.
                                  # 1.11 = ADR-0082 (el consejo de criterio ejecutable): +council {state, module_version, membership_version,
                                  # membership_source, catalog_sha, plan_catalog_matches_run, rules_sha, tools_sha, model, full_council,
                                  # n_members, members[], quorum_rule, ledger (decisiones humanas + knowledge_now atestiguados,
                                  # texto ≤600), rounds[] (r1 COPIADA del plan + r2/r3 medidas: miembros/usage/estados),
                                  # coverage {pre_search, after_search, post_search}, must_uncovered, must_unsatisfiable,
                                  # directives[], directives_state, index, cache, vocabulary, decided_by, kill_switch} +
                                  # competence.components.council_uncovered_must (cg-4, forma G.2) + competence.config.
                                  # council_component_gating + deterministic_checks.{council, attestation_identifier_leak
                                  # (+_state, _rule)} + citations[].pertinent true | 'not-named-by-council (…)' | 'not-available
                                  # (council <state>)' (+pertinent_to, pertinent_source) + citations_support_summary.pertinent
                                  # objeto + search_ledger.plan.{directives, directives_state, families_source
                                  # 'directives+default'} + search_ledger.n_items_for_directives + fallback.fb_meta.council +
                                  # token_usage.{by_stage.council_r1/r2/r3, cache, input_tokens_total, council_judgment,
                                  # cache_sum_matches_by_model} + by_model[m].{cache_creation, cache_read} + agents_invoked
                                  # 'council:n/N' + filas por miembro + epistemic_summary.{council_state, council_n_valid,
                                  # council_n_members, council_must_uncovered} + thread_context.council_summary +
                                  # plan v4 (will_run 'council-member'). Eventos NUEVOS (agent 'council'): stage.council.
                                  # {ledger, round, member, progress, coverage, directives}; stage.plan += council_state;
                                  # run.state{queued}.council. TODO aditivo; kill-switch WITT_COUNCIL=0 = camino de 9d90c01
                                  # con las excepciones DECLARADAS de ADR-0082 (L.2).
                                  # 1.10 = ADR-0081 (política best-tier v2 / generación g2-2026-09): +models (procedencia
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
                             "panel_incomplete", "panel_incomplete_reasons",
                             "vision")     # corrector ADR-0083 (L/G.6): `audit += vision` TAMBIÉN en audit_initial (sólo si audit() la trae)


def _max_tokens_for(role, role_name):
    """El TOPE (no gasto) del rol en la generación efectiva (ADR-0081 C.4): RoleResolved.max_tokens; para un id de
    familia desconocida (max_tokens null en la tabla) se toma el tope del rol en la generación — jamás un literal."""
    if role.get("max_tokens") is not None:
        return role["max_tokens"]
    # ADR-0082 (D.2, C9): `council` está FUERA de PIPELINE_ROLES pero tiene tope propio en MAX_TOKENS_KEYS —
    # antes caía en 'judge-anthropic' (coincidía 4000/1200 por accidente, no por tabla).
    key = role_name if role_name in models.MAX_TOKENS_KEYS else "judge-anthropic"
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
                    "cite or reuse an identifier from it unless it appears in evidence. "
                    # ADR-0082 (F.5) — lo atestiguado por humanos es PRIOR ART, jamás evidencia
                    "Human attestations (human_attestations), when present, are PRIOR ART attested by humans, "
                    "not evidence; never cite an identifier from them unless it appears in evidence. "
                    # ADR-0083 (D.2) — la figura corrobora; el texto porta la evidencia. Excepción DECLARADA al byte a byte
                    # del PROMPT (no del registro): la description cambia aunque WITT_FIGURES=0 (LG9 re-corre el held-out).
                    "kind 'figure' = '<PMCID>#<fig_id>'. A figure citation supports ONLY what its caption text says and "
                    "may only accompany a text citation of the same paper; you never see the image — never state a "
                    "number or observation that exists only in an image. Cite inline as [n] in direct_answer."),
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
                             # ADR-0083 (D.2): 'figure' = '<PMCID>#<fig_id>' — sostiene SÓLO su caption
                             "enum": ["di-chunk", "di-record", "di-database", "paper", "store-resolution",
                                      "other", "figure"]},
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
PLAN_VERSION = "4"   # v4 (ADR-0082 B/J): agent_matrix v1.3 — digest() CAMBIA por construcción (34 nombres, 5 filas
                     # nuevas) y los 17 miembros del consejo son componentizados ('lib/council.py'):
                     # judgment.agents_applicable[].will_run gana el literal 'council-member'. Declarado, no fingido.
                     # v3 (ADR-0066, adopción VB): +judgment.clarifying_questions (alineación pre-gasto,
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
            # ADR-0082 (G.7, plan v4): un MIEMBRO del consejo (componentized == agent_matrix.COUNCIL_COMPONENT) deja de ser
            # 'skipped-ad-hoc' — corre como código en lib/council.py (r1 en el plan, r2/r3 en la corrida): 'council-member'
            if comp == agent_matrix.COUNCIL_COMPONENT:
                will_run = "council-member"
            else:
                will_run = "runs-always-componentized" if comp else "skipped-ad-hoc"
            agents.append({
                "agent": a["agent"],
                "gate": row["gate"],
                "signal": row["signal"],
                "evidence": row["evidence"],
                "componentized": bool(comp),
                "component": comp[0] if comp else None,
                "matrix_note": row.get("note"),
                "reason": a.get("reason", ""),
                "will_run": will_run,
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


def plan_event_payload(plan, council_state=None):
    """Resumen de stage.plan — la traza viva y el replay leen el MISMO resumen.
    ADR-0082 (J): `+= council_state` — el estado de la ronda 1 del consejo del plan que respalda la corrida
    (runs.council_json.r1_state); None = la corrida no trae copia del consejo (ausencia declarada)."""
    j = plan.get("judgment", {})
    p = {"plan_version": plan.get("plan_version"),
         "council_state": council_state,
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


COUNCIL_AGENT_ROW = "(consejo de criterio — cm-1)"
COUNCIL_OPERATIVES_ROW = "(operativos — not-applicable-by-category, cm-1)"
COUNCIL_SUBSTRATE_ROW = "(sustrato — cm-1)"
_COUNCIL_SUBSTRATE_INVOKED_ELSEWHERE = ("composite-auditor", "identifier-verification-gate")


def _council_agent_rows(council_block):
    """ADR-0082 (G.7) — las filas de `agents_invoked` DERIVADAS de frozen.council (código, jamás self-report): una fila
    agregada '(consejo de criterio — cm-1)' con `council:<n_valid>/<N>`; una fila por miembro con status 'invoked'
    (un miembro caído SÍ fue invocado: lo dice su evidence — 'errored:<kind>' / 'timeout' —, no gana un literal nuevo)
    o 'not-invoked' cuando la corrida no lo despachó; los 8 operativos en UNA fila `not-applicable` (bajo full-council
    son miembros); los 9 de sustrato en UNA fila con su estado real de la tabla (B). Bajo kill-switch la fila agregada
    es `not-applicable` con reason 'kill-switch WITT_COUNCIL=0' y nada más (camino 9d90c01, excepción L.2 iii)."""
    c = council_block if isinstance(council_block, dict) else {}
    state = c.get("state")
    rows = []
    if state == COUNCIL_STATE_DISABLED:
        rows.append({"agent": COUNCIL_AGENT_ROW, "status": "not-applicable", "reason": "kill-switch WITT_COUNCIL=0",
                     "evidence_generated": []})
        return rows, set()
    members = [m for m in (c.get("members") or []) if isinstance(m, str)]
    N = c.get("n_members") or len(members)
    rounds = {r.get("round"): r for r in (c.get("rounds") or []) if isinstance(r, dict) and r.get("round")}
    ledger = c.get("ledger") if isinstance(c.get("ledger"), dict) else {}
    reqs = ledger.get("requirements") or []
    cov = c.get("coverage") if isinstance(c.get("coverage"), dict) else {}
    post, pre = cov.get("post_search"), cov.get("pre_search")
    judged = post if isinstance(post, dict) and post.get("state") == "judged" else (
        pre if isinstance(pre, dict) and pre.get("state") == "judged" else {})
    votes_by_agent = {}
    for br in judged.get("by_requirement") or []:
        for v in br.get("votes") or []:
            if v.get("annulled"):
                continue
            slot = votes_by_agent.setdefault(v.get("agent"), {"covered": 0, "partial": 0, "uncovered": 0})
            if v.get("coverage") in slot:
                slot[v["coverage"]] += 1
    sha = c.get("catalog_sha") or ""
    if not rounds:
        rows.append({"agent": COUNCIL_AGENT_ROW, "status": "not-applicable",
                     "reason": f"council {state}" + (f" — {c.get('state_reason')}" if c.get("state_reason") else ""),
                     "evidence_generated": [f"catalog_sha:{sha[:16]}"] if sha else []})
        return rows, set()
    r1, r2, r3 = rounds.get("r1") or {}, rounds.get("r2") or {}, rounds.get("r3") or {}
    n_valid = r2.get("n_valid") if r2 else r1.get("n_valid")
    ev_agg = []
    for rn, rr in (("r1", r1), ("r2", r2), ("r3", r3)):
        if rr:
            ev_agg.append(f"{rn}:{rr.get('n_ok', rr.get('n_valid'))}/{rr.get('n_members', N)}")
    ev_agg += [f"requirements:{ledger.get('n_kept')}", f"must_uncovered:{c.get('must_uncovered')}"]
    if sha:
        ev_agg.append(f"catalog_sha:{sha[:16]}")
    rows.append({"agent": COUNCIL_AGENT_ROW, "status": "invoked", "invocation_id": f"council:{n_valid}/{N}",
                 "evidence_generated": ev_agg})
    seated = set()
    for a in members:
        seated.add(a)
        per_round = {}
        for rn, rr in (("r1", r1), ("r2", r2), ("r3", r3)):
            for m in rr.get("members") or []:
                if isinstance(m, dict) and m.get("agent") == a:
                    per_round[rn] = m
        n_req = sum(1 for r in reqs if a in (r.get("requested_by") or []))
        ev = [f"requirements:{n_req}"]
        vc = votes_by_agent.get(a)
        if vc:
            ev.append(f"coverage:{vc['covered']}/{vc['partial']}/{vc['uncovered']}")
        dispatched = []
        for rn, m in per_round.items():
            st = m.get("status")
            if m.get("dispatched") or st in ("ok", "not-applicable", "errored", "timeout"):
                dispatched.append(rn)
            if st == "errored":
                ev.append(f"errored:{m.get('error_kind')} ({rn})")
            elif st == "timeout":
                ev.append(f"timeout ({rn})")
            elif st in ("skipped-budget", "skipped-cancelled", "not-invoked"):
                ev.append(f"{st} ({rn})")
        # r1 corrió en el JOB del plan: si el plan la copió sin filas por miembro, los N fueron despachados por construcción
        if r1 and "r1" not in per_round and not (r1.get("members")):
            dispatched.insert(0, "r1")
        if dispatched:
            rows.append({"agent": a, "status": "invoked",
                         "invocation_id": "council:" + a + ":" + "+".join(sorted(set(dispatched))),
                         "evidence_generated": ev})
        else:
            rows.append({"agent": a, "status": "not-invoked", "invocation_id": f"council:{a}",
                         "reason": "council member (cm-1) seated, not dispatched in this run's rounds (no kept requirement "
                                   "of its own, or the round did not run)", "evidence_generated": ev})
    return rows, seated


def _council_static_rows(full_council):
    """Operativos (una fila) y sustrato (una fila con el estado REAL de la tabla B) — sin ruido de 17 renglones."""
    rows = []
    cm = agent_matrix.COUNCIL_MEMBERSHIP
    if not full_council:
        rows.append({"agent": COUNCIL_OPERATIVES_ROW, "status": "not-applicable",
                     "reason": ("category operations-reporting — not-applicable-by-category (cm-1; WITT_COUNCIL_FULL=1 "
                                "los sienta)"),
                     "evidence_generated": [f"{n}:{e.get('state')}" for n, e in cm["operatives"].items()]})
    rows.append({"agent": COUNCIL_SUBSTRATE_ROW, "status": "not-applicable",
                 "reason": ("substrate agents with their REAL state (agent_matrix.COUNCIL_MEMBERSHIP.substrate); "
                            "composite-auditor and identifier-verification-gate are the two `invoked` rows above"),
                 "evidence_generated": [f"{n}:{s}" for n, s in cm["substrate"].items()
                                        if n not in _COUNCIL_SUBSTRATE_INVOKED_ELSEWHERE]})
    return rows


def _figures_agent_row(figures_block, lenses):
    """ADR-0083 (L): la fila `agents_invoked` de las figuras, DERIVADA por código del bloque congelado (jamás self-report).
    None bajo kill-switch (M.1: `agents_invoked` no gana fila; frozen.figures.state lo dice)."""
    if not isinstance(figures_block, dict) or figures_block.get("state") == FIGURES_KILL_SWITCH_STATE:
        return None
    state = figures_block.get("state")
    n_fig, n_ver = figures_block.get("n_figures") or 0, figures_block.get("n_verified") or 0
    row = {"agent": FIGURES_AGENT_ROW, "status": "invoked" if state == "attached" else "not-applicable",
           "invocation_id": f"figures:{n_ver}/{n_fig}",
           "evidence_generated": [f"parsed:{n_fig}", f"verified:{n_ver}",
                                  f"embeddable:{figures_block.get('n_embeddable') or 0}",
                                  f"lenses:{','.join(lenses or [])}", "synthesizer:captions-only"]}
    if state != "attached":
        row["reason"] = ("no path_b" if state == "no-path-b"
                         else "no full-text XML among selected papers" if state == "no-papers-with-xml"
                         else str(state))
    return row


def _web_agent_row(web_frozen, ps):
    """ADR-0084 (G.9/L): la fila `agents_invoked` del localizador web, DERIVADA por código de frozen.web_locator (jamás self-report).
    None bajo `off` EXPLÍCITO o DERIVADO (M.1: la enumeración de excepciones del kill-switch es verdad — patrón 0083 «no emitir las
    otras dos») y cuando el bloque no existe. status: 'invoked' (la familia corrió: hubo ronda con web) · 'not-applicable (<estado>)'
    (competente sin ronda / ronda sin directiva web) · 'tool-unavailable' (proveedor fijado sin llave o deshabilitado)."""
    if not isinstance(web_frozen, dict) or not isinstance(ps, dict) or ps.get("provider") in (None, "off"):
        return None
    state = str(web_frozen.get("state") or "")
    if state.startswith("tool-unavailable ("):
        status = "tool-unavailable"
    elif state.startswith("not-requested"):
        status = f"not-applicable ({state})"
    elif web_frozen.get("measured") is False and state.startswith(("skipped-cap (", "skipped-budget (", "error: ")):
        # corrector ADR-0084 (G.9): la familia corrió pero NO envió nada (cuota, presupuesto o error) — no es 'invoked'
        status = f"not-applicable ({state})"
    else:
        status = "invoked"

    def _n(k):   # corrector: null = no midió → '-' (jamás el literal Python 'None' incrustado)
        v = web_frozen.get(k)
        return "-" if v is None else str(v)

    row = {"agent": WEB_LOCATOR_AGENT_ROW, "status": status, "provider": web_frozen.get("provider"),
           "invocation_id": f"web_locator:{_n('n_located')}/{_n('n_results')}",
           "evidence_generated": [f"state:{state}", f"queries:{_n('n_queries')}", f"located:{_n('n_located')}",
                                  f"materialized:{_n('n_materialized')}", f"unresolved:{_n('n_unresolved')}",
                                  "bundle:0 items with source 'web' (identifiers materialized by europepmc)"]}
    if status != "invoked":
        row["reason"] = web_frozen.get("state_detail") or state
    return row


def _agents_invoked(audit_result, deterministic_checks, plan=None, council=None, figures=None, figure_lenses=None,
                    attested=None,
                    web=None, web_ps=None):
    """§11's `agents_invoked`, DERIVED FROM WHAT ACTUALLY RAN — never self-reported. A model listing the
    agents it invoked is precisely the §7 anti-pattern (self-audit as audit evidence); the code knows.

    Con plan (tapón 3, ADR-0061): el preflight §11 SÍ se hizo — lo hizo el planner antes de encolar.
    Cada agente que el planner juzgó aplicable y no existe como componente entra con el literal §5 de la
    matriz (`skipped-ad-hoc`: el rol corre ad-hoc dentro de la síntesis) y la razón del planner. El resto
    del catálogo queda en UNA fila agregada `not-applicable` (trazabilidad sin 25 filas de ruido).

    Sin plan: el hueco sigue declarado como `not-assessed` — nadie juzgó, y eso se dice.

    ADR-0082 (G.7): `council` = frozen.council → fila agregada 'council:n/N' + una fila por miembro (invoked /
    not-invoked con su evidence), operativos y sustrato en filas agregadas; un miembro del consejo que el planner juzgó
    aplicable deja de ser 'skipped-ad-hoc' (es 'council-member' en el plan y su fila la deriva el consejo). Bajo
    kill-switch sólo la fila agregada `not-applicable 'kill-switch WITT_COUNCIL=0'` (L.2 iii).

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
    # ADR-0083 (L): la fila de las figuras — código (lib/figures.py): parseó / verificó por sha / gateó licencia. Ausente
    # bajo kill-switch WITT_FIGURES=0 (M.1). 'not-applicable' con razón cuando no hubo Ruta B o ningún XML de texto completo.
    fig_row = _figures_agent_row(figures, figure_lenses)
    if fig_row is not None:
        out.append(fig_row)
    # ADR-0084 (G.9): la fila del localizador web — código (lib/web_locator.py + search_harness._run_web_family): localizó por
    # tabla de patrones y materializó por Europe PMC. Ausente bajo off explícito/derivado (M.1).
    web_row = _web_agent_row(web, web_ps)
    if web_row is not None:
        out.append(web_row)
    # ADR-0086 (K): la fila de las imágenes atestiguadas — código (lib/attestations.py): validó por bytes, borró metadatos,
    # guardó en privado y entregó a lo sumo a dos lentes. Ausente sin imágenes aportadas y bajo kill-switch (M.1).
    if isinstance(attested, dict) and attested.get("items"):
        out.append({"agent": ATTESTED_AGENT_ROW, "status": "invoked", "invocation_id": "attestations",
                    "evidence_generated": [f"attached:{attested.get('n_attached')}",
                                           f"seen_by_panel:{attested.get('n_seen_by_panel')}",
                                           f"bytes_to_synthesizer:False"]})
    seated = set()
    council_rows = []
    if isinstance(council, dict):
        council_rows, seated = _council_agent_rows(council)
        out.extend(council_rows)
    judgment = (plan or {}).get("judgment") or {}
    if judgment.get("state") == "declared":
        judged = 0
        for a in judgment.get("agents_applicable", []):
            name = a.get("agent")
            is_member = (a.get("will_run") == "council-member" or a.get("component") == agent_matrix.COUNCIL_COMPONENT[0]
                         or agent_matrix.council_member(name) is not None)
            if is_member and isinstance(council, dict):
                # ADR-0082 (G.7): miembro del consejo — su fila la deriva el consejo (invoked/not-invoked arriba); si el
                # consejo no corrió en esta corrida, se declara 'not-invoked' con el estado del consejo, jamás skipped-ad-hoc.
                # Bajo kill-switch (L.2 iii) NO hay filas por miembro: el camino de 9d90c01 con la matriz v1.3 los omite
                # (componentizados → `continue`) y sólo queda la fila agregada 'kill-switch WITT_COUNCIL=0'.
                if council.get("state") == COUNCIL_STATE_DISABLED:
                    continue
                if name not in seated:
                    out.append({"agent": name, "status": "not-invoked", "invocation_id": f"council:{name}",
                                "reason": (f"planner (§11): {a.get('reason', '')} — council member (cm-1, component "
                                           f"lib/council.py) not dispatched: council {council.get('state')}"),
                                "evidence_generated": []})
                continue
            if a.get("componentized"):
                continue   # composite-auditor / verify_output ya están arriba como invoked, medidos
            judged += 1
            out.append({
                "agent": name,
                "status": "skipped-ad-hoc",   # literal §5 de la matriz: el rol corre ad-hoc en la síntesis
                "reason": (f"planner (§11): {a.get('reason', '')} — no existe como componente; la "
                           f"síntesis cubre el rol ad-hoc. Gate de matriz: {a.get('gate')}"
                           + (f". {a.get('matrix_note')}" if a.get("matrix_note") else "")),
                "evidence_generated": [],
            })
        if isinstance(council, dict) and council.get("state") != COUNCIL_STATE_DISABLED:
            out.extend(_council_static_rows(bool(council.get("full_council"))))
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


def _panel_findings(audit_result, figures_enabled=False):
    """Los hallazgos ACCIONABLES del panel para la pasada de revisión: qué atrapó cada juez y qué
    corrección propuso — lo que VB re-delega como prosa, aquí viaja como insumo tipado. Incluye
    APPROVE_MINOR (catch real aunque no vete) además de REVISE.
    ADR-0083 (D.4, el lazo): con figuras encendidas cada hallazgo gana `from_vision_lens` (= la fila trae saw_figures.n > 0:
    ESA lente vio imágenes; lo que diga en caught/reasons puede describir píxeles = juicio). `figure_readings` JAMÁS entra
    aquí (sólo caught/correction_applied/reasons, como siempre). Bajo kill-switch la forma es la de 1.11 byte a byte."""
    out = []
    for r in audit_result.get("panel", []):
        if r.get("verdict") in ("REVISE", "APPROVE_MINOR") and (r.get("caught") or r.get("reasons")):
            f = {"lens": r["lens"], "reviewer": r["reviewer"], "verdict": r["verdict"],
                 "caught": r.get("caught", ""),
                 "correction_applied": r.get("correction_applied", ""),
                 "reasons": r.get("reasons", [])}
            if figures_enabled:
                saw = r.get("saw_figures") if isinstance(r.get("saw_figures"), dict) else {}
                f["from_vision_lens"] = bool(isinstance(saw.get("n"), int) and saw.get("n") > 0)
            out.append(f)
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
        # ADR-0086 (B.6.i): lo que el PADRE tuvo aportado por una persona — metadatos y caption corto, jamás bytes. La llave
        # NO nace si el padre no tuvo imágenes (M.1: ese hilo es byte a byte el de 1.13).
        **_attested_thread_items(frozen),
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
        # corrector ADR-0083 (D.4 entre turnos): los hallazgos del PADRE se etiquetan `from_vision_lens` desde SU registro (alguna fila
        # trae saw_figures ⇒ el padre corrió con figuras), no desde la env de hoy; un padre 1.11/kill-switch NO gana la llave (M.1).
        # `n_from_vision_lens` viaja en previous_audit y synth_system añade la cláusula de visión cuando es > 0.
        parent_saw = any(isinstance(r.get("saw_figures"), dict) for r in (audit.get("panel") or []) if isinstance(r, dict))
        prev_findings = _panel_findings(audit, figures_enabled=parent_saw)[:5]
        snap["previous_audit"] = {"verdict": audit.get("verdict"), "n_valid": audit.get("n_valid"),
                                  "findings": prev_findings}
        if parent_saw:
            snap["previous_audit"]["n_from_vision_lens"] = sum(1 for f in prev_findings if f.get("from_vision_lens"))
    # ADR-0082 (G.9): el resumen del consejo del padre — requisitos (gap ≤200, estados, decisión), banderas, si hubo
    # "qué sabes ahora" y must sin cubrir tras la búsqueda — como llave hermana ESTRUCTURADA para el PLANNER
    # (plan_thread_context) y la RONDA 1 del turno N+1 (council_jobs._inherited_criteria: criterios heredados). El
    # SINTETIZADOR del hijo NO lo recibe: execute_run se lo quita de su copia del snapshot (E5, corrector ADR-0082 —
    # `gap` y `flags[].statement` son texto escrito por los miembros). None = padre sin consejo o sin ledger.
    snap["council_summary"] = council.summary_for_thread((frozen or {}).get("council")) if frozen else None
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
# ADR-0083 (D.1): lo ÚNICO que el sintetizador/consejo/panel ven por figura — caption + metadatos; `license` como {id, source};
# JAMÁS cache_path/raw_ref/b64/bytes. La lista vive en lib/figures (F1) y aquí se RE-EXPORTA para el gate estático del smoke
# (_PROMPT_FIGURE_KEYS ∩ _FORBIDDEN_PROMPT_FIGURE_KEYS == ∅). Sólo ítems con caption 'present' (una figura sin caption no
# puede sostener texto). Bajo kill-switch ningún paper trae `figures` → la proyección es la de 1.11 byte a byte.
_PROMPT_FIGURE_KEYS = tuple(figures.PROMPT_FIGURE_KEYS)
_FORBIDDEN_PROMPT_FIGURE_KEYS = tuple(figures.FORBIDDEN_PROMPT_KEYS)
assert not set(_PROMPT_FIGURE_KEYS) & set(_FORBIDDEN_PROMPT_FIGURE_KEYS)
_PROMPT_FIGURES_BLOCK_KEYS = ("state", "n")


def _prompt_figures(block):
    """Proyección del bloque paper['figures'] para el prompt (ADR-0083 D.1): {state, n, items[PROMPT_FIGURE_KEYS]} con
    figures.project_for_prompt (sólo caption 'present'; license {id, source}). Conserva los tres estados de state/n."""
    out = {k: block[k] for k in _PROMPT_FIGURES_BLOCK_KEYS if k in block}
    out["items"] = figures.project_for_prompt(block.get("items") or [])
    out["n_delivered"] = len(out["items"])
    return out


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
        # ADR-0083 (D.1): figuras = caption + metadatos por lista blanca; ausente cuando el paper no ganó la llave
        # (ZFIN, kill-switch, sin Ruta B) — jamás se rellena
        if isinstance(it.get("figures"), dict):
            p["figures"] = _prompt_figures(it["figures"])
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
        else:
            rec = p.get("search_rec", {})
            ids.append(f"PMID:{rec['pmid']}" if rec.get("pmid") else (rec.get("pmcid") or rec.get("doi") or "paper"))
        # ADR-0083 (D.3): los ids de figura '<PMCID>#<fig_id>' son ítems de evidencia propios — un voto del panel/consejo que
        # nombre una figura NO cae como hallucinated_evidence_id. Ausentes bajo kill-switch (el paper no gana `figures`).
        figs = p.get("figures") if isinstance(p.get("figures"), dict) else None
        for it in (figs or {}).get("items") or []:
            if isinstance(it, dict) and it.get("id"):
                ids.append(it["id"])
    return ids


# ADR-0079 — la cláusula anti-fuga del sistema de síntesis. Va en synth_system (cuando hay turno anterior)
# Y en SYNTH_TOOL.description (siempre): el turno anterior es PRECEDENTE, no evidencia.
THREAD_ANTI_LEAK_CLAUSE = ("The previous turn (thread_context) is PRIOR ART, not evidence; never cite or "
                           "reuse an identifier from it unless it appears in evidence. Use it only to "
                           "understand what was asked before, what was missing (gap_flags) and what the "
                           "humans commented — then answer THIS question from THIS evidence.")


# corrector ADR-0083 (D.4 entre turnos) — la cláusula de los hallazgos de VISIÓN del turno anterior (sólo cuando
# thread_context.previous_audit.n_from_vision_lens > 0): lo que una lente con visión ESCRIBIÓ sobre una imagen es juicio.
THREAD_VISION_FINDINGS_CLAUSE = ("In thread_context.previous_audit, findings marked from_vision_lens describe images a panel "
                                 "lens saw in the previous turn: they are judgment, never evidence; never adopt a number or "
                                 "observation from them unless it appears in a delivered TEXT passage of THIS evidence.")


# ADR-0082 (F.5) — la cláusula anti-fuga de lo ATESTIGUADO: `aporto` y "qué sabes ahora" viajan como llave hermana
# `human_attestations` FUERA de `evidence` (misma disciplina que thread_context); son PRIOR ART atestiguado, no evidencia.
ATTESTATION_ANTI_LEAK_CLAUSE = ("Human attestations (human_attestations: knowledge_now and attested requirements) are "
                                "PRIOR ART attested by humans, not evidence; never cite or reuse an identifier from them "
                                "unless it appears in evidence. Use them only to understand what the humans already know "
                                "or supplied — then answer THIS question from THIS evidence.")


def synth_system(pass_label, thread_context=False, human_attestations=False, vision_findings=False):
    """The EXACT production system prompt of a synthesis pass — factored out so diagnostics
    (evaluation/scripts/ab_trapped_scalar.py) measure against the real string, never a replica.

    ADR-0079: `thread_context=True` añade la cláusula anti-fuga (THREAD_ANTI_LEAK_CLAUSE). Sin turno
    anterior el string es EXACTAMENTE el de antes — la medición de ab_trapped_scalar no cambia.
    ADR-0082 (F.5): `human_attestations=True` añade ATTESTATION_ANTI_LEAK_CLAUSE (sólo cuando viajan atestiguaciones).
    corrector ADR-0083 (D.4 entre turnos): `vision_findings=True` (el snapshot del padre trae previous_audit.n_from_vision_lens > 0)
    añade THREAD_VISION_FINDINGS_CLAUSE — la cláusula anti-fuga sólo hablaba de IDENTIFICADORES; una observación o cifra de imagen
    escrita por una lente con visión en `caught` del turno N no debe dictarse al sintetizador del turno N+1."""
    return ("You answer zebrafish pronephros research questions for a medical team, from a curated "
            "evidence bundle (DATA INAMOVIBLE"
            + ("" if pass_label == "pass1" else " + externally fetched literature") + "). "
            "Use ONLY the provided evidence. Be direct; keep confidence honest (thin evidence means "
            "LOW confidence + explicit gap_flags); when sub-claims have asymmetric evidence strength, "
            "report confidence_by_subclaim instead of averaging. If your answer rests on an absence, "
            "declare absence_kind precisely. Technical identifiers stay in English; never assert an "
            "identifier that is not in the evidence."
            + (" " + THREAD_ANTI_LEAK_CLAUSE if thread_context else "")
            + (" " + THREAD_VISION_FINDINGS_CLAUSE if (thread_context and vision_findings) else "")
            + (" " + ATTESTATION_ANTI_LEAK_CLAUSE if human_attestations else "") + "\n\n"
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


def _default_synthesizer(question, evidence, pass_label, thread_context=None, human_attestations=None):
    """One synthesis pass over an evidence view (pass1 = DI-only, pass2 = DI + Path B). Returns
    {direct_answer, stated_confidence, confidence_by_subclaim, absence_kind, gap_flags,
    evidence_cited, model, usage}.

    ADR-0079: `thread_context` (snapshot del turno anterior) viaja como LLAVE HERMANA de evidence en el
    user_text — {question, evidence, thread_context} — nunca dentro de evidence (patrón revision_input).
    Con snapshot, el system gana la cláusula anti-fuga. None = raíz: prompt idéntico al de siempre.
    ADR-0082 (F.5): `human_attestations` ({knowledge_now, attestations[] {requirement_id, text, by, at}}) viaja
    igual — llave HERMANA `human_attestations`, jamás dentro de evidence — y el system gana
    ATTESTATION_ANTI_LEAK_CLAUSE. El sintetizador es CIEGO al consejo (E5): aquí sólo llega lo que el humano
    atestiguó, nunca los criterios ni la cobertura del consejo."""
    prev_audit = (thread_context or {}).get("previous_audit") if isinstance(thread_context, dict) else None
    n_vis = (prev_audit or {}).get("n_from_vision_lens") if isinstance(prev_audit, dict) else None
    system = synth_system(pass_label, thread_context=thread_context is not None,
                          human_attestations=human_attestations is not None,
                          vision_findings=isinstance(n_vis, int) and n_vis > 0)     # corrector ADR-0083 (D.4 entre turnos)
    payload = {"question": question, "evidence": evidence}
    if thread_context is not None:
        payload["thread_context"] = thread_context
    if human_attestations is not None:
        payload["human_attestations"] = human_attestations
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


# ADR-0082 (H): + council_r1 (COPIADA del plan: el gasto ocurrió ANTES de encolar — si no se copia M8 lo pierde, si se
# suma dos veces miente), council_r2 y council_r3 (MEDIDAS aquí), en el orden en que gastan.
TOKEN_STAGES = ("plan", "council_r1", "synthesize_pass1", "elicit_pass1", "council_r2", "search", "council_r3",
                "synthesize_pass2", "elicit_pass2", "panel", "revision", "embed")
COUNCIL_STAGES = ("council_r1", "council_r2", "council_r3")
COUNCIL_STAGE_OF_ROUND = {"r1": "council_r1", "r2": "council_r2", "r3": "council_r3"}
# corrector ADR-0082 (H / gate F): la ÚNICA fuente vive en lib.council (viaja en council.vocabulary.usage_stage_states)
COUNCIL_USAGE_STAGE_STATES_EXACT = council.USAGE_STAGE_STATES_EXACT
COUNCIL_USAGE_STAGE_STATE_PREFIXES = council.USAGE_STAGE_STATE_PREFIXES


def council_vocabulary_full():
    """corrector ADR-0082 (gate F): TODOS los vocabularios cerrados que la paridad compara con types.ts y los fixtures — los
    de lib.council (estados, miembros, cobertura, decisiones, directivas, by_stage.council_r*) más el del componente cg-4
    de competence (`competence_component_states`), que vive en el servicio. UNA función para frozen.council.vocabulary y
    para GET /council/membership.vocabulary (app)."""
    voc = council.council_vocabulary()
    voc["competence_component_states"] = {"exact": list(competence.COUNCIL_COMPONENT_STATES_EXACT),
                                          "prefixes": list(competence.COUNCIL_COMPONENT_STATE_PREFIXES)}
    return voc
_PASS_STAGE = {"pass1": ("synthesize_pass1", "elicit_pass1"), "pass2": ("synthesize_pass2", "elicit_pass2"),
               "revision": ("revision", "revision")}   # la elicitación de la revisión se atribuye a 'revision'


def _council_round_usage(usage):
    """{in, out, cache_creation, cache_read, thinking_tokens?} desde un usage de ronda del consejo — lectura TOLERANTE
    (in|input_tokens, out|output_tokens, cache_creation|cache_creation_input_tokens, cache_read|cache_read_input_tokens),
    la misma que app._plans_council_usage aplica a council_usage_json (C6). None si no hay usage medido."""
    if not isinstance(usage, dict):
        return None

    def g(*keys):
        for k in keys:
            v = usage.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return int(v)
        return 0
    out = {"in": g("in", "input_tokens"), "out": g("out", "output_tokens"),
           "cache_creation": g("cache_creation", "cache_creation_input_tokens"),
           "cache_read": g("cache_read", "cache_read_input_tokens")}
    if isinstance(usage.get("thinking_tokens"), (int, float)):
        out["thinking_tokens"] = int(usage["thinking_tokens"])
    return out


def _council_stages(council):
    """by_stage.council_r1/r2/r3 (ADR-0082 H) desde el holder del consejo de execute_run: {enabled, present, r1 {usage,
    model, model_source, n_members, n_valid, plan_id}, rounds[] (RoundResult de r2/r3 medidas), not_run {r2, r3}}.
    Cada etapa: {in, out, cache_creation, cache_read, thinking_tokens?, n_members, n_invoked, n_calls, model,
    model_source, state ∈ 'measured' | 'copied-from-plan_json' | 'not-run (<razón>)' | 'kill-switch WITT_COUNCIL=0' |
    'plan-without-council'}. Sin holder (llamador legado) → 'not-run (no council block)' con in/out null — jamás un 0."""
    c = council if isinstance(council, dict) else {}
    out = {}
    if not c:
        for s in COUNCIL_STAGES:
            out[s] = {"in": None, "out": None, "state": "not-run (no council block)"}
        return out
    r1 = c.get("r1") if isinstance(c.get("r1"), dict) else {}
    u1 = _council_round_usage(r1.get("usage"))
    if not c.get("enabled", True):
        # Kill-switch: cero llamadas NUEVAS — pero un gasto de ronda 1 que el plan YA hizo (antes de encolar) se COPIA igual:
        # apagar el consejo detiene el gasto, no la contabilidad (M8 debe cuadrar; app excluye de plans_council los planes
        # consumidos porque esta copia los cuenta). Sin r1 en la copia, las tres quedan 'kill-switch WITT_COUNCIL=0'.
        if u1 is not None:
            out["council_r1"] = {**u1, "n_members": r1.get("n_members"), "n_valid": r1.get("n_valid"),
                                 "n_calls": r1.get("n_calls"), "model": r1.get("model"), "model_source": r1.get("model_source"),
                                 "state": "copied-from-plan_json",
                                 "source": f"plan_json (spent BEFORE enqueue; plan_id {c.get('plan_id')}; council disabled at "
                                           "execution — WITT_COUNCIL=0 stops new calls, not accounting)"}
        else:
            out["council_r1"] = {"in": None, "out": None, "state": "kill-switch WITT_COUNCIL=0"}
        for s in ("council_r2", "council_r3"):
            out[s] = {"in": None, "out": None, "state": "kill-switch WITT_COUNCIL=0"}
        return out
    if not c.get("present"):
        out["council_r1"] = {"in": None, "out": None, "state": "plan-without-council"}
        for s in ("council_r2", "council_r3"):
            out[s] = {"in": None, "out": None, "state": "not-run (no-ledger)"}
        return out
    if u1 is not None:
        out["council_r1"] = {**u1, "n_members": r1.get("n_members"), "n_valid": r1.get("n_valid"),
                             "n_calls": r1.get("n_calls"), "model": r1.get("model"), "model_source": r1.get("model_source"),
                             "state": "copied-from-plan_json",
                             "source": f"plan_json (spent BEFORE enqueue; plan_id {c.get('plan_id')})"}
    else:
        out["council_r1"] = {"in": None, "out": None, "state": f"not-run ({c.get('r1_state') or 'round 1 without usage'})",
                             "model": r1.get("model")}
    by_round = {}
    for rr in c.get("rounds") or []:
        if isinstance(rr, dict) and rr.get("round") in ("r2", "r3"):
            by_round[rr["round"]] = rr
    for rn in ("r2", "r3"):
        stage = COUNCIL_STAGE_OF_ROUND[rn]
        rr = by_round.get(rn)
        if rr is None:
            reason = (c.get("not_run") or {}).get(rn) or "round not reached"
            out[stage] = {"in": None, "out": None, "state": f"not-run ({reason})"}
            continue
        u = _council_round_usage(rr.get("usage")) or {"in": 0, "out": 0, "cache_creation": 0, "cache_read": 0}
        model = (rr.get("model") or {}) if isinstance(rr.get("model"), dict) else {}
        out[stage] = {**u, "n_members": rr.get("n_members"), "n_invoked": rr.get("n_invoked"),
                      "n_calls": sum(int(m.get("attempts") or 0) for m in (rr.get("members") or []) if isinstance(m, dict)),
                      "model": model.get("requested"), "model_source": model.get("source"),
                      "state": "measured" if not rr.get("cancelled") else "measured (partial: round cancelled)"}
    return out


def _openai_detail_for(model, openai_detail):
    """corrector ADR-0083 (H): el `detail` SOLO aplica a la familia openai (Anthropic no lo tiene) — mismo criterio que
    composite_auditor._figures_for_member (`api != 'anthropic-messages'`)."""
    try:
        fam = models.family_of(model)[0]
    except Exception:
        fam = None
    return openai_detail if (openai_detail and fam == "openai") else None


def _vision_tokens(model, dims, detail=None):
    """ADR-0083 (H): tokens de visión PROYECTADOS por la fórmula pública del proveedor — la ÚNICA sede es
    models.vision_tokens(model, w, h, detail) -> {tokens, formula, tier} | None (rebanada F3). Devuelve {tokens, formula, tier, state}
    con state 'projected' | 'no-dims' | 'model-vision-unknown' | 'tool-unavailable (…)' — jamás se inventa un número.
    corrector: `detail` (WITT_FIGURES_OPENAI_DETAIL) viaja a la fórmula — con 'low' el tier tile-512 cuesta 85 fijos por imagen; runs y
    composite_auditor (saw_figures.visual_tokens_projected) proyectan la MISMA cifra para el mismo envío."""
    fn = getattr(models, "vision_tokens", None)
    if fn is None:
        return {"tokens": None, "formula": None, "tier": None, "state": FIGURES_TOOL_UNAVAILABLE_TOKENS}
    if not isinstance(dims, dict) or not dims.get("w") or not dims.get("h"):
        return {"tokens": None, "formula": None, "tier": None, "state": "no-dims"}
    try:
        res = fn(model, int(dims["w"]), int(dims["h"]), detail) if detail else fn(model, int(dims["w"]), int(dims["h"]))
    except Exception as e:   # la proyección jamás tumba la corrida
        return {"tokens": None, "formula": None, "tier": None, "state": f"error: {type(e).__name__}: {str(e)[:120]}"}
    if not isinstance(res, dict) or not isinstance(res.get("tokens"), (int, float)):
        return {"tokens": None, "formula": None, "tier": (res or {}).get("tier") if isinstance(res, dict) else None,
                "state": "model-vision-unknown"}
    return {"tokens": int(res["tokens"]), "formula": res.get("formula"), "tier": res.get("tier"), "state": "projected"}


def _vision_by_reviewer(rows, items, openai_detail=None, saw_key="saw_figures", dims_key="dims_measured"):
    """ADR-0083 (H): {reviewer: vision {…}} desde las filas del panel que traen <saw_key>.n > 0 (lo ENTREGADO al caller,
    medido por composite_auditor — F3) y las dims MEDIDAS de esas imágenes (por sha256). Cada intento del juez reenvía las
    imágenes (la API las factura): n_images/bytes/tokens se multiplican por len(attempts). Clase 'proyección'; los
    input_tokens medidos del juez YA incluyen las imágenes (nada se suma dos veces). Sin filas con imágenes → {}.
    ADR-0086 (K): las imágenes ATESTIGUADAS usan la MISMA cuenta con saw_key='saw_attested' y dims_key='dims' — una sola
    implementación: si la proyección de visión cambia, cambia para las dos fuentes a la vez."""
    by_sha = {it.get("sha256"): it for it in (items or []) if isinstance(it, dict) and it.get("sha256")}
    out = {}
    for row in rows or []:
        saw = row.get(saw_key) if isinstance(row.get(saw_key), dict) else None
        if not saw or not isinstance(saw.get("n"), int) or saw["n"] <= 0:
            continue
        reviewer = row.get("reviewer") or "unknown-reviewer"
        n_att = max(1, len(row.get("attempts") or []))
        v = out.setdefault(reviewer, {"n_images": 0, "bytes_b64": 0, "visual_tokens_projected": 0, "formula": None,
                                      "tier": None, "n_attempts_counted": 0, "n_rows": 0, "tokens_state": "projected"})
        v["n_images"] += int(saw["n"]) * n_att
        v["bytes_b64"] += int(saw.get("bytes_b64_total") or 0) * n_att
        v["n_attempts_counted"] += n_att
        v["n_rows"] += 1
        det = _openai_detail_for(reviewer, openai_detail)     # corrector: la proyección honra WITT_FIGURES_OPENAI_DETAIL (OpenAI)
        for sha in (saw.get("sha256s") or []):
            it = by_sha.get(sha)
            t = _vision_tokens(reviewer, (it or {}).get(dims_key), det)
            if t["state"] != "projected":
                v["visual_tokens_projected"] = None
                v["tokens_state"] = t["state"]
                if t.get("tier"):
                    v["tier"] = t["tier"]
                continue
            if v["visual_tokens_projected"] is not None:
                v["visual_tokens_projected"] += t["tokens"] * n_att
            v["formula"], v["tier"] = t["formula"], t["tier"]
    for reviewer, v in out.items():
        v["class"] = "proyección"
        v["formula_source"] = getattr(models, "VISION_FORMULA_SOURCE", None)
        v["input_tokens_measured_includes_images"] = True
        if models.family_of(reviewer)[0] == "openai" and openai_detail:
            v["detail"] = openai_detail
    return out


def _usage_by_stage(passes, planner_meta, audit_result, embed_tokens, plan_declared=False, council=None, figures=None,
                    web=None, attested=None):
    """ADR-0080 (F): reparto del gasto MEDIDO por etapa. Insumos: cada pasada trae `usage` (síntesis +
    elicitación fusionadas — M8) y, desde ADR-0080, `usage_elicitation` aparte: la etapa synthesize_* es la
    resta y elicit_* la parte. Un sintetizador que no separa (stub, firma vieja) deja elicit_* con in/out null
    + state 'not-separable' — no se inventa un 0 — y todo su gasto va a synthesize_*. `search` no gasta modelo
    (tools Layer 0): 0 medido con nota. `_sum` es la suma sobre las etapas de MODELO (embed aparte).
    Corrector ADR-0080: `plan` distingue TRES estados — medido (planner con usage), `plan-without-usage`
    (plan declarado pero el planner no reportó gasto: in/out null, no 0) y `no-plan`; y el panel cuenta el gasto
    de TODA fila con `usage` medido, incluida la de un juez agotado (`errored`) cuyos intentos cobraron —
    composite_auditor lo suma en audit.usage y M8 debe cuadrar contra el mismo número.
    ADR-0082 (H): `council` = el holder del consejo (ver _council_stages) → council_r1 (copiada del plan), council_r2/r3
    (medidas) con cache_creation/cache_read; sin holder las tres quedan 'not-run (no council block)' con in/out null."""
    stages = {s: {"in": 0, "out": 0} for s in TOKEN_STAGES if s != "embed" and s not in COUNCIL_STAGES}
    stages["search"]["note"] = "Layer 0 tools — no model call (ADR-0080)"
    if isinstance(web, dict):
        # ADR-0084 (G.7): el costo del localizador viaja APARTE (consultas × tarifa = PROYECCIÓN, jamás tokens); con el alterno
        # Anthropic los tokens del despachador SÍ son tokens MEDIDOS de un modelo → entran a la etapa `search` (y a by_model)
        stages["search"]["note"] = WEB_SEARCH_STAGE_NOTE
        stages["search"]["web_locator_usd_projected"] = web.get("usd_projected")
        toks = web.get("tokens") if isinstance(web.get("tokens"), dict) else None
        if toks and toks.get("model"):
            stages["search"]["in"] += int(toks.get("in") or 0)
            stages["search"]["out"] += int(toks.get("out") or 0)
            stages["search"]["model"] = toks.get("model")
            stages["search"]["state"] = WEB_ANTHROPIC_SEARCH_STATE
    stages["elicit_pass1"] = {"in": None, "out": None, "state": "not-run"}
    stages["elicit_pass2"] = {"in": None, "out": None, "state": "not-run"}
    stages.update(_council_stages(council))
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
    # ADR-0083 (H): visión PROYECTADA por reviewer (sólo con figuras encendidas y filas que vieron imágenes); los tokens
    # medidos de arriba ya incluyen las imágenes — `vision` es un desglose declarado, jamás se suma a in/out ni a _sum.
    if isinstance(figures, dict) and figures.get("enabled"):
        vis = _vision_by_reviewer(audit_result.get("panel", []), figures.get("items"), figures.get("openai_detail"))
        for reviewer, v in vis.items():
            m = stages["panel"]["by_model"].setdefault(reviewer, {"in": 0, "out": 0})
            m["vision"] = v
    # ADR-0086 (K): lo mismo para las imágenes que APORTÓ una persona, en llave PROPIA (`attested_vision`) para que el lector
    # nunca confunda una figura publicada con material del laboratorio. Misma clase (proyección) y misma advertencia: los
    # tokens medidos del juez YA las incluyen. Sin imágenes aportadas la llave NO nace (M.1).
    if isinstance(attested, dict) and attested.get("items"):
        for reviewer, v in _vision_by_reviewer(audit_result.get("panel", []), attested["items"],
                                               None, "saw_attested", "dims").items():
            m = stages["panel"]["by_model"].setdefault(reviewer, {"in": 0, "out": 0})
            m["attested_vision"] = v
    stages["embed"] = {"tokens": embed_tokens, "unit": "embedding tokens (not chat tokens; excluded from _sum)"}
    stages["_sum"] = {"in": sum(v["in"] for k, v in stages.items() if k != "embed" and isinstance(v.get("in"), int)),
                      "out": sum(v["out"] for k, v in stages.items() if k != "embed" and isinstance(v.get("out"), int)),
                      # ADR-0082 (H): la caché se cuadra APARTE (cache_sum_matches_by_model); in/out conservan la semántica
                      # de la API (el remanente no cacheado)
                      "rule": ("sum over model stages (embed excluded; council_r1 copied from plan_json counts once); "
                               "must equal by_model totals; cache_creation/cache_read reconciled apart")}
    return stages


def _token_usage(passes, audit_result, embed_tokens, plan=None, council=None, figures=None, web=None, attested=None):
    """TokenUsage (UI contract, ADR-0051): measured token counts by model + a LABELED cost projection.
    `passes` = [(label, answer_dict)] for the synthesis passes that ran.

    `plan` (ADR-0061): el planner es una llamada de modelo y GASTA. Dejarla fuera haría que M8 no
    cuadre — misma disciplina que LOTE-01·A4 (lo gastado antes de morir sobrevive). El gasto del plan
    se atribuye al modelo que lo hizo y se declara aparte en `plan_judgment`.

    `council` (ADR-0082 H): el holder del consejo — council_r1 se COPIA de runs.council_json.r1 (gastado ANTES de
    encolar), council_r2/r3 se MIDEN aquí; by_model[m] gana cache_creation/cache_read (tokens) para el modelo del
    consejo; USD = in×p_in + out×p_out + cache_creation×p_in×mult_write(ttl) + cache_read×p_in×0.1 con
    models.CACHE_MULTIPLIERS (clase derivada, declarada); `cache` {creation_input_tokens, read_input_tokens, priced,
    multipliers, source, as_of}; `input_tokens_total` = input_tokens + creation + read (input_tokens conserva la
    semántica de la API: el remanente no cacheado); `cache_sum_matches_by_model`; `council_judgment` aparte (como
    plan_judgment). Sin holder: cache 0/0 con estado declarado — la forma no cambia."""
    by_model = {}

    def _add(model, usage, cache=None):
        i, o = _usage_in_out(usage)
        m = by_model.setdefault(model, {"in": 0, "out": 0})
        m["in"] += i
        m["out"] += o
        if cache is not None:
            # ADR-0082 (H): sólo los modelos con caché MEDIDA ganan las llaves (aditivo; UsageByModel.cache_*?)
            m["cache_creation"] = m.get("cache_creation", 0) + int(cache[0] or 0)
            m["cache_read"] = m.get("cache_read", 0) + int(cache[1] or 0)

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
    # ADR-0084 (G.7): tokens del despachador del alterno Anthropic (MEDIDOS) → by_model bajo su modelo; Brave no gasta tokens
    web_toks = web.get("tokens") if isinstance(web, dict) and isinstance(web.get("tokens"), dict) else None
    if web_toks and web_toks.get("model"):
        _add(web_toks["model"], {"input_tokens": int(web_toks.get("in") or 0), "output_tokens": int(web_toks.get("out") or 0)})
    by_stage = _usage_by_stage(passes, planner_meta or None, audit_result, embed_tokens,
                               plan_declared=plan is not None, council=council, figures=figures, web=web,
                               attested=attested)
    # ADR-0082 (H): las etapas del consejo MEDIDAS (r2/r3) o COPIADAS (r1) entran a by_model bajo el modelo del consejo con
    # su caché; una etapa 'not-run'/'kill-switch' no aporta (in/out null, no 0)
    council_rows = []
    for s in COUNCIL_STAGES:
        st = by_stage.get(s) or {}
        if isinstance(st.get("in"), int):
            cm = st.get("model") or "unknown-model"
            _add(cm, {"input_tokens": st["in"], "output_tokens": st["out"]},
                 cache=(st.get("cache_creation", 0), st.get("cache_read", 0)))
            council_rows.append((s, cm, st))
    embed_model, _embed_src = models.embed_model()   # ADR-0081: OPENAI_EMBED_MODEL o la fila `embed` de la tabla
    # ADR-0078: un modelo sin precio en la tabla NO se cotiza a 0 — se EXCLUYE de la proyección y se
    # declara en missing_price_models; cost_projection_complete dice si el número cubre todo el gasto.
    cost = 0.0
    missing = []
    ttl = ((council or {}).get("cache_ttl") if isinstance(council, dict) else None) or "5m"
    write_key = "write_1h" if str(ttl) == "1h" else "write_5m"
    cache_usd = 0.0
    cache_priced = True
    for model, m in by_model.items():
        if model not in PRICES_PER_MTOK_USD:
            missing.append(model)
            continue
        pi, po = PRICES_PER_MTOK_USD[model]
        cost += (m["in"] * pi + m["out"] * po) / 1e6
        cc, cr = m.get("cache_creation", 0), m.get("cache_read", 0)
        if cc or cr:
            cp = models.cache_prices(model) if hasattr(models, "cache_prices") else None
            if cp:
                c_usd = (cc * cp[write_key] + cr * cp["read"]) / 1e6
                cost += c_usd
                cache_usd += c_usd
            else:
                cache_priced = False
    if embed_tokens:
        if embed_model in PRICES_PER_MTOK_USD:
            cost += embed_tokens * PRICES_PER_MTOK_USD[embed_model][0] / 1e6
        else:
            missing.append(embed_model)
    pi, po = _usage_in_out(planner_usage)
    total_in, total_out = sum(m["in"] for m in by_model.values()), sum(m["out"] for m in by_model.values())
    cache_creation_total = sum(m.get("cache_creation", 0) for m in by_model.values())
    cache_read_total = sum(m.get("cache_read", 0) for m in by_model.values())
    stage_cc = sum(int(st.get("cache_creation") or 0) for _s, _m, st in council_rows)
    stage_cr = sum(int(st.get("cache_read") or 0) for _s, _m, st in council_rows)
    c_state = (council or {}).get("state") if isinstance(council, dict) else None
    if council_rows and isinstance(council, dict) and not council.get("enabled", True):
        cache_state = "measured (council_r1 copied from plan_json; r2/r3 kill-switch WITT_COUNCIL=0)"
    elif council_rows:
        cache_state = "measured (council rounds)"
    elif isinstance(council, dict) and not council.get("enabled", True):
        cache_state = "no cached calls measured (council disabled (kill-switch WITT_COUNCIL=0))"
    else:
        cache_state = f"no cached calls measured (council {c_state or 'not present'})"
    council_judgment = None
    if council_rows:
        cj_in = sum(st["in"] for _s, _m, st in council_rows)
        cj_out = sum(st["out"] for _s, _m, st in council_rows)
        cj_models = sorted({m for _s, m, _st in council_rows})
        cj_usd = None
        if all(m in PRICES_PER_MTOK_USD for m in cj_models) and cache_priced:
            cj_usd = 0.0
            for _s, m, st in council_rows:
                p_in, p_out = PRICES_PER_MTOK_USD[m]
                cp = models.cache_prices(m)
                cj_usd += (st["in"] * p_in + st["out"] * p_out
                           + int(st.get("cache_creation") or 0) * cp[write_key]
                           + int(st.get("cache_read") or 0) * cp["read"]) / 1e6
            cj_usd = round(cj_usd, 6)
        council_judgment = {"model": cj_models[0] if len(cj_models) == 1 else cj_models, "in": cj_in, "out": cj_out,
                            "cache_creation": stage_cc, "cache_read": stage_cr, "usd_projected": cj_usd,
                            "rounds": [s for s, _m, _st in council_rows],
                            "class": "PROJECTION (usd) over MEASURED tokens; council_r1 copied from plan_json"}
    out = {
        "input_tokens": total_in,
        "output_tokens": total_out,
        # ADR-0082 (H): input_tokens conserva la semántica de la API (remanente no cacheado); el total con caché va aparte
        "input_tokens_total": total_in + cache_creation_total + cache_read_total,
        "by_model": by_model,
        # ADR-0080 (F): el MISMO gasto repartido por ETAPA (plan, council_r1, synthesize_pass1, elicit_pass1, council_r2,
        # search, council_r3, synthesize_pass2, elicit_pass2, panel, revision, embed). suma(by_stage) == by_model total —
        # el check viaja con el dato; embed se cuenta aparte (tokens de embedding, no tokens de modelo de chat).
        "by_stage": by_stage,
        "by_stage_sum_matches_by_model": (by_stage["_sum"]["in"] == total_in
                                          and by_stage["_sum"]["out"] == total_out),
        # ADR-0082 (H): la caché se cuadra aparte — Σ by_stage.council_*.cache_* == Σ by_model.cache_*
        "cache_sum_matches_by_model": (stage_cc == cache_creation_total and stage_cr == cache_read_total),
        "cache": {"creation_input_tokens": cache_creation_total, "read_input_tokens": cache_read_total,
                  "priced": bool(cache_priced), "usd_projected": round(cache_usd, 6),
                  "multipliers": dict(getattr(models, "CACHE_MULTIPLIERS", {})),
                  "source": getattr(models, "CACHE_MULTIPLIERS_SOURCE", None),
                  "as_of": getattr(models, "CACHE_AS_OF", None),
                  "price_class": getattr(models, "CACHE_PRICE_CLASS", None),
                  "ttl": str(ttl), "write_multiplier_key": write_key,
                  "state": cache_state,
                  "rule": ("usd = cache_creation × price_in × write_mult(ttl) + cache_read × price_in × 0.1 (per Mtok); "
                           "tokens are MEASURED (API usage.cache_*), dollars are PROJECTION")},
        # el gasto del plan va DENTRO del total (M8 cuadra) y ADEMÁS aparte, para que se pueda
        # responder "¿cuánto cuesta declarar un plan?" sin re-derivarlo
        "plan_judgment": ({"model": planner_meta.get("model"), "in": pi, "out": po}
                          if planner_usage else None),
        # ADR-0082 (H): idem para el consejo (r1 copiada + r2/r3 medidas), null cuando ninguna etapa midió
        "council_judgment": council_judgment,
        "embedding": {"model": embed_model, "total_tokens": embed_tokens,
                      "attribution": "process-wide window during this run (concurrent runs may overlap)"},
        "estimated_cost_usd": round(cost, 4),
        # ADR-0078: modelos con gasto medido pero SIN precio en la tabla — excluidos del número de arriba
        "missing_price_models": missing,
        "cost_projection_complete": not missing and cache_priced,
        "cost_class": f"PROJECTION (calculated from measured tokens x per-Mtok prices as of "
                      f"{PRICES_AS_OF}; the token counts are measurements, the dollars are not"
                      + ("; prompt-cache tokens priced via published multipliers (write x1.25|2.0, read x0.1; "
                         "ADR-0082 H)" if (cache_creation_total or cache_read_total) else "")
                      + ("" if not missing else
                         f"; INCOMPLETE — sin precio para {missing}, excluidos")
                      + ("" if cache_priced else "; INCOMPLETE — cache tokens of an unpriced model excluded") + ")",
    }
    # ADR-0083 (H) — F8 (integrador): usage_json ES este dict (runs.execute_run lo persiste tal cual), y GET /usage (F5) agrega
    # `usage_json.figures` APARTE de totals; el espejo se escribe aquí desde frozen.figures — SOLO con WITT_FIGURES=1 (M.1:
    # bajo kill-switch la llave no existe). Conteos y bytes son MEDICIÓN. corrector: `bytes_verified` = Σ bytes de las filas
    # 'verified' (con o sin caché); `bytes_downloaded` = SOLO las 'verified' que NO fueron cache_hit (B.3: ledger fresco + sha igual
    # = cero red — el nombre afirma una descarga que en esas corridas no ocurrió); `n_cache_hit` declara cuántas vinieron de caché.
    # ADR-0086 (K): el consumo de lo ATESTIGUADO viaja APARTE y es MEDICIÓN pura — los tokens de visión de esas imágenes
    # ya están dentro de los input_tokens medidos del panel: nada se suma dos veces.
    if isinstance(attested, dict) and attested.get("items"):
        out["attested_images"] = _attested_usage(attested)
    if isinstance(figures, dict) and figures.get("enabled") and isinstance(figures.get("summary"), dict):
        fs = figures["summary"]
        rows = [i for i in (fs.get("items") or []) if isinstance(i, dict) and i.get("bytes_state") == "verified"]
        out["figures"] = {"state": fs.get("state"), "n_figures": fs.get("n_figures"), "n_verified": fs.get("n_verified"),
                          "n_cited": fs.get("n_cited"),
                          "bytes_verified": sum(int(i.get("bytes") or 0) for i in rows),
                          "bytes_downloaded": sum(int(i.get("bytes") or 0) for i in rows if i.get("cache_hit") is not True),
                          "n_cache_hit": sum(1 for i in rows if i.get("cache_hit") is True),
                          "class": ("MEASUREMENT (counts, bytes) — mirror of frozen.figures for GET /usage (ADR-0083 H); "
                                    "bytes_downloaded = verified rows fetched from the source in THIS run (cache_hit false); "
                                    "bytes_verified = all verified rows (cache hits included)")}
    # ADR-0084 (G.7): el gasto del LOCALIZADOR web — sólo cuando la familia CORRIÓ (ausente bajo kill-switch / tool-unavailable /
    # sin directiva web). `estimated_cost_usd` NO cambia (su cost_class afirma «tokens × per-Mtok prices»); el total que cuadra
    # en M8 viaja aparte con su propia clase: dos proyecciones sumadas, los conteos (MEDICIÓN) al lado.
    if isinstance(web, dict):
        out["web_locator"] = dict(web)
        out["estimated_cost_usd_total_projected"] = round(cost + float(web.get("usd_projected") or 0.0), 4)
        out["total_class"] = WEB_TOTAL_CLASS
    return out


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


def _figure_checks(answer, bundle, cfg=None, cache_root=None):
    """ADR-0083 (F): los CINCO predicados deterministas de las figuras viven en verify_output.figure_predicates(citations, bundle,
    cache_dir, answer_text) -> (fragmento deterministic_checks.figures, extra_predicates[]) (rebanada F2). Aquí se CABLEA
    tolerante: kill-switch → {state 'kill-switch WITT_FIGURES=0'} (una de las 3 excepciones declaradas, M.1); sin el helper
    en el árbol → 'tool-unavailable (…)' declarado, jamás re-implementado en runs.py; un fallo del predicado no tumba la
    corrida (§6). Devuelve ({'figures': fragmento}, predicados | None)."""
    cfg = cfg or figures.env_config()
    if not cfg["figures"]:
        return {"figures": {"state": FIGURES_KILL_SWITCH_STATE}}, None
    fn = getattr(verify_output, "figure_predicates", None)
    if fn is None:
        return {"figures": {"state": FIGURES_TOOL_UNAVAILABLE_GATE}}, None
    if cache_root is None:
        cache_root = figures.cache_dir()[0]
    citations = _citations_of(answer)[0]
    try:
        # F8 (integrador, ADR-0083 F.3): se pasa el DICT del sintetizador — figure_predicates lee `direct_answer` Y
        # `absence_kind`; con sólo el str la declinación que cita figuras quedaría "positiva" (declarado not-provided)
        res = fn(citations, bundle, cache_root, answer if isinstance(answer, dict) else (answer or ""))
    except Exception as e:
        return {"figures": {"state": f"error: {type(e).__name__}: {str(e)[:120]}"}}, None
    if isinstance(res, tuple) and len(res) >= 2:
        frag, preds = res[0], res[1]
    else:
        frag, preds = res, None
    if not isinstance(frag, dict):
        frag = {"state": f"error: figure_predicates returned {type(frag).__name__}, not dict"}
        preds = None
    preds = [p for p in (preds or []) if callable(p)] or None
    return {"figures": frag}, preds


def _web_checks(answer, bundle, web_ledger=None, provider_state=None):
    """ADR-0084 (E/G.3): los CUATRO predicados deterministas del localizador web viven en verify_output.web_predicates(citations,
    bundle, answer, web_ledger, provider_state) -> (fragmento deterministic_checks.web_locator, extra_predicados[]) (rebanada W5):
    web_text_not_cited / web_located_cited_requires_fetch / web_items_native_only (DUROS) + web_urls_not_in_answer (informativo).
    Aquí se CABLEA tolerante (patrón _figure_checks): sin el helper en el árbol → 'tool-unavailable (…)' declarado, jamás
    re-implementado en runs.py; un fallo del predicado no tumba la corrida (§6). Bajo kill-switch el helper devuelve EXACTAMENTE
    {state} (una de las 3 excepciones declaradas, M.1). Devuelve ({'web_locator': fragmento}, predicados | None)."""
    fn = getattr(verify_output, "web_predicates", None)
    if fn is None:
        return {"web_locator": {"state": WEB_TOOL_UNAVAILABLE_GATE}}, None
    citations = _citations_of(answer)[0]
    try:
        res = fn(citations, bundle, answer if isinstance(answer, dict) else (answer or ""), web_ledger, provider_state)
    except Exception as e:
        return {"web_locator": {"state": f"error: {type(e).__name__}: {str(e)[:120]}"}}, None
    if isinstance(res, tuple) and len(res) >= 2:
        frag, preds = res[0], res[1]
    else:
        frag, preds = res, None
    if not isinstance(frag, dict):
        frag = {"state": f"error: web_predicates returned {type(frag).__name__}, not dict"}
        preds = None
    preds = [p for p in (preds or []) if callable(p)] or None
    return {"web_locator": frag}, preds


def _attested_checks(answer, items, bundle, state=None):
    """(fragmento deterministic_checks.attested_images, extra_predicates) — ADR-0086 (E). Sin la biblioteca del gate en el
    árbol, el fragmento lo DECLARA y ningún predicado entra a la conjunción (§6: nada se supone cumplido)."""
    fn = getattr(verify_output, "attested_predicates", None)
    if fn is None:
        return {"attested_images": {"state": ATTESTED_TOOL_UNAVAILABLE_GATE}}, None
    try:
        frag, preds = fn(_citations_of(answer)[0], items or [], answer,
                         evidence_ids=_evidence_ids(bundle), state=ATTESTED_CHECK_STATE_OF.get(state, state))
    except Exception as e:
        return {"attested_images": {"state": f"error: {type(e).__name__}: {str(e)[:120]}"}}, None
    return {"attested_images": frag}, (preds or None)


def _gate(answer, bundle, thread_snapshot, run, pass_no, attestations=None, figures_cfg=None, figures_cache_root=None,
          web_ledger=None, web_ps=None, attested_items=None, attested_state=None):
    """El gate determinista (verify_output.admissible, clase Logic-LM) sobre UNA pasada: predicados duros
    de identificadores + parent_identifier_leak (ADR-0079) + attestation_identifier_leak (ADR-0082 F.5) +
    positive_claim_requires_citations (ADR-0080 E, si está en el árbol). ADR-0080 (B): corre ADELANTADO sobre
    pass1 (su admisibilidad es un componente de la compuerta) y de nuevo sobre pass2/revisión. `pass_no` viaja
    en el payload del evento como ETIQUETA ('pass1' | 'pass2' | 'revision' — el mismo vocabulario que
    usage_raw.passes; corrector ADR-0080: antes mezclaba int y str en la misma llave).
    `attestations` = human_attestations_of(ledger) (ADR-0082 F.5) o None: un identificador que sólo existe en lo
    atestiguado y reaparece en la respuesta sin estar en la evidencia = fuga → inadmisible (predicado DURO)."""
    leak_frag, leak_preds = _leak_check(thread_snapshot, answer["direct_answer"], bundle, run)
    att_frag, att_preds = _attestation_leak_check(attestations, answer["direct_answer"], bundle)
    # ADR-0086 (E): una imagen aportada jamás es cita ni evidencia — dos predicados DUROS y uno informativo
    attimg_frag, attimg_preds = _attested_checks(answer, attested_items, bundle, state=attested_state)
    _cits, schema, _raw = _citations_of(answer)
    # el informe de identificadores se mide UNA vez y alimenta también al predicado de citas (corrector ADR-0080)
    report = verify_output.verify_identifiers(answer["direct_answer"]).as_dict()
    pc_frag, pc_preds = _positive_claim_check(answer, schema.get("n_valid"), identifier_report=report)
    # ADR-0083 (F): figure_id_resolves / figure_sha_matches / figure_only_not_asserted (DUROS) + numerals / license_known
    # (informativos, gating False) — cableados desde verify_output (F2) con estado declarado; sin figuras en el bundle el
    # fragmento dice 'no-figure-citations' y NINGÚN predicado entra a la conjunción (la admisibilidad de hoy).
    fig_frag, fig_preds = _figure_checks(answer, bundle, cfg=figures_cfg, cache_root=figures_cache_root)
    # ADR-0084 (E): web_text_not_cited / web_located_cited_requires_fetch / web_items_native_only (DUROS) + web_urls_not_in_answer
    # (informativo) — cableados desde verify_output (W5); sin datos web el fragmento dice 'no-web-items' y NINGÚN predicado entra
    # a la conjunción (la admisibilidad de hoy byte a byte); bajo kill-switch EXACTAMENTE {state}.
    web_frag, web_preds = _web_checks(answer, bundle, web_ledger=web_ledger, provider_state=web_ps)
    preds = (list(leak_preds or []) + list(att_preds or []) + list(attimg_preds or []) + list(pc_preds or [])
             + list(fig_preds or []) + list(web_preds or []))
    adm, reasons = verify_output.admissible({"direct_answer": answer["direct_answer"],
                                             "evidence_cited": answer.get("evidence_cited") or [],
                                             "absence_kind": answer.get("absence_kind")},
                                            extra_predicates=preds or None)
    return {"pass": pass_no, "admissible": adm, "reasons": reasons, "identifier_report": report,
            **leak_frag, **att_frag, **attimg_frag, **pc_frag, **fig_frag, **web_frag,
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


def _build_search_plan(question, entities, pass1_query_en, cfg, directives=None):
    """(C) El plan de búsqueda lo arma search_harness.build_search_plan (rebanada C2). Sin el módulo en el
    árbol se devuelve un plan-sobre DECLARADO (state 'harness-unavailable') para que el registro diga qué
    faltó; nada se inventa. Devuelve (plan, state).
    ADR-0082 (G.3): `directives` = las directivas COMPILADAS por council.compile_directives (forma C.6) o None —
    con ellas el harness hace la UNIÓN default ∪ directivas (families_source 'directives+default'; las familias
    'directive-only' entran por directiva); con WITT_COUNCIL=0 o sin directivas se pasa None: camino de hoy byte a byte."""
    directives = list(directives) if directives else None
    if search_harness is None or not hasattr(search_harness, "build_search_plan"):
        return ({"plan_version": None, "rounds_cap": cfg["rounds_cap"], "families": list(cfg["families_default"]),
                 "queries": None, "directives": directives or [], "source": "default-families",
                 "state": "harness-unavailable (lib.search_harness not in tree — ADR-0080 C2)"},
                "harness-unavailable")
    try:
        # families=None: el harness resuelve WITT_SEARCH_DEFAULT_FAMILIES (con su fuente declarada); las familias gate
        # 'directive-only' entran SÓLO nombradas por una directiva del consejo (ADR-0082 G.3)
        plan = search_harness.build_search_plan(question, entities, pass1_query_en, directives=directives,
                                                families=None)
        plan.setdefault("rounds_cap", cfg["rounds_cap"])
        return plan, "built"
    except Exception as e:   # §6 no-hang: un plan que falla deja fila 'error' y la Ruta B corre por el camino de hoy
        return ({"plan_version": None, "rounds_cap": cfg["rounds_cap"], "families": list(cfg["families_default"]),
                 "queries": None, "directives": directives or [], "source": "default-families",
                 "state": f"error: {type(e).__name__}: {str(e)[:160]}"}, "error")


def _path_b_bundle_accepts():
    """Qué llaves ADR-0080 acepta answer_pipeline.path_b_bundle (search_plan, on_stage, existing_ids) —
    por inspección de firma, no por try/except (patrón _call_with_optional)."""
    try:
        params = inspect.signature(answer_pipeline.path_b_bundle).parameters
        has_varkw = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
        # ADR-0084 (G.10): `web_quota` (db.web_locator_reserve) viaja al harness por inspección de firma — el harness NO importa db
        return {n for n in ("search_plan", "on_stage", "existing_ids", "web_quota") if n in params or has_varkw}
    except (TypeError, ValueError):
        return set()


def _path_b_via_harness(question, entities, q_sent, q_source, triggered_by, search_plan, on_stage,
                        existing_ids=None, web_quota=None):
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
        if "web_quota" in accepts and web_quota is not None:
            kwargs["web_quota"] = web_quota   # ADR-0084 (G.10): la cuota mensual, inyectada; None → 'not-enforced' declarado
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
        # ADR-0084 (G.2, lectura estricta): las URLs halladas viven SÓLO en frozen.web_locator — la fila web de cada ronda se congela
        # SIN su ledger anidado `web_locator` (queries/located/unresolved con URLs y title_web): se poda sobre una COPIA (el bundle_json
        # conserva la fila íntegra) y se declara dónde vive; los contadores C.7 de la fila (provider, n_*, cost, quota_state) siguen aquí
        out["rounds"] = json.loads(json.dumps(out.get("rounds") or [], default=str))
        for rnd in out["rounds"]:
            for src in (rnd.get("sources") or []) if isinstance(rnd, dict) else []:
                if isinstance(src, dict) and src.get("family") == "web" and "web_locator" in src:
                    src.pop("web_locator", None)
                    src["web_locator_frozen_at"] = "frozen.web_locator"
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


FIGURE_CITATION_KIND = "figure"
FIGURE_VERIFICATION_NOT_A_FIGURE = "not-a-figure"
FIGURE_CONTENT_STATES = ("panel-judgment", "not-evaluated")


def _figure_items_index(figures_block):
    """{id (tal cual y en minúsculas): FigureItem} del bloque congelado de figuras (F4 sólo casa por id exacto o
    case-insensitive: los ids '<PMCID>#<fig_id>' son deterministas)."""
    idx = {}
    for it in ((figures_block or {}).get("items") or []):
        if isinstance(it, dict) and it.get("id"):
            idx.setdefault(str(it["id"]), it)
            idx.setdefault(str(it["id"]).lower(), it)
    return idx


def _figure_item_for(cit, idx):
    ident = str((cit or {}).get("id") or "").strip()
    return idx.get(ident) or idx.get(ident.lower())


def _figure_readings_ids(audit_result):
    """Los ids COMPUESTOS '<PMCID>#<fig_id>' que alguna lente con visión LEYÓ (figure_readings, F3) — para `content
    'panel-judgment'` (E). corrector: SOLO `id` (parse_figure_readings ya resolvió el fig_id al id compuesto de la figura
    ENTREGADA); el fig_id desnudo era redundante y AMBIGUO — dos papers con el mismo fig_id ('F1', frecuente en JATS)
    colisionaban y una figura que ninguna lente leyó ganaba 'panel-judgment'. Nada se infiere del texto de la lectura."""
    out = set()
    for row in (audit_result or {}).get("panel", []):
        for r in (row.get("figure_readings") or []):
            if isinstance(r, dict) and r.get("id"):
                out.add(str(r["id"]))
    return out


_FIGURE_ID_SHAPE_RE = re.compile(r"^PMC\d+#\S+$", re.I)     # la forma '<PMCID>#<fig_id>' (L) — la misma que verify_output._FIGURE_ID_RE


def _is_figure_citation(c, idx):
    """corrector ADR-0083 (E/F): UN clasificador de «cita-figura» para runs = el SUPERSET conservador de verify_output.figure_predicates
    (kind 'figure' ∨ id con forma '<PMCID>#<fig_id>' ∨ id que resuelve a un ítem figura del bloque). Antes (E) filtraba SOLO por kind y
    (F) por el superset: una cita con id de figura etiquetada kind 'paper' quedaba gateada pero sin figure_verification, fuera de
    figure_citations.n, de cited_by_answer/n_cited y de la prioridad «citadas primero» del panel — dos conteos del MISMO registro
    discrepaban. La etiqueta que eligió el modelo se conserva en `kind_reported`."""
    if not isinstance(c, dict):
        return False
    ident = str(c.get("id") or "").strip()
    if not ident:
        return False
    if c.get("kind") == FIGURE_CITATION_KIND or _FIGURE_ID_SHAPE_RE.match(ident):
        return True
    return _figure_item_for(c, idx) is not None


def _figure_verification(citations, figures_block, audit_result):
    """ADR-0083 (E): `figure_verification {bytes, content, figure_id, kind_reported}` en toda cita-figura (superset: kind 'figure' ∨ id
    con forma '<PMCID>#<fig_id>' ∨ id que resuelve a un ítem — corrector) + el resumen `figure_citations {n, n_verified_bytes,
    n_not_fetched, n_error, n_mismatch, n_unresolved, n_other, n_figure_shaped_other_kind}`. bytes = el bytes_state del ítem
    (vocabulario B.2 COMPLETO: 'verified' | 'not-fetched (…)' | 'error: …' | 'mismatch' | 'never (…)' | 'not-requested (…)') o
    'not-a-figure' cuando el id no nombra una figura del bundle; content 'panel-judgment' ⇔ alguna lente con visión emitió
    figure_readings para ESE id compuesto, si no 'not-evaluated'. corrector: n_not_fetched cuenta SOLO 'not-fetched (…)', los
    'error: …' van a n_error y el resto ('never'/'not-requested') a n_other → n == Σ cubetas + n_unresolved. Ausente bajo
    kill-switch (el llamador no llama)."""
    idx = _figure_items_index(figures_block)
    read = _figure_readings_ids(audit_result)
    summ = {"n": 0, "n_verified_bytes": 0, "n_not_fetched": 0, "n_error": 0, "n_mismatch": 0, "n_unresolved": 0, "n_other": 0,
            "n_figure_shaped_other_kind": 0}
    for c in citations:
        if not _is_figure_citation(c, idx):
            continue
        summ["n"] += 1
        if c.get("kind") != FIGURE_CITATION_KIND:
            summ["n_figure_shaped_other_kind"] += 1
        it = _figure_item_for(c, idx)
        if it is None:
            c["figure_verification"] = {"bytes": FIGURE_VERIFICATION_NOT_A_FIGURE, "content": "not-evaluated", "figure_id": None,
                                        "kind_reported": c.get("kind")}
            summ["n_unresolved"] += 1
            continue
        bs = it.get("bytes_state")
        content = "panel-judgment" if it.get("id") in read else "not-evaluated"
        c["figure_verification"] = {"bytes": bs, "content": content, "figure_id": it.get("id"), "kind_reported": c.get("kind")}
        if bs == "verified":
            summ["n_verified_bytes"] += 1
        elif bs == "mismatch":
            summ["n_mismatch"] += 1
        elif isinstance(bs, str) and bs.startswith("not-fetched ("):
            summ["n_not_fetched"] += 1
        elif isinstance(bs, str) and bs.startswith("error: "):
            summ["n_error"] += 1
        else:
            summ["n_other"] += 1
    return summ


def _support_states(citations, bundle, audit_result, council_pertinence=None, council_state=None,
                    council_source=None, figures_block=None):
    """(E/G) support_state por cita — verify_output.support_state_for (rebanada E) si está en el árbol; el
    grounding viene de la lente evidence-grounding (citation_support opcional en su fila). Devuelve
    (citations con support_state aditivo, citations_support_summary). Sin el helper: support_state None por
    cita + summary.state 'tool-unavailable' — nunca se funden los peldaños.
    ADR-0082 (G.4): `council_pertinence` = {evidence_id: [requirement_id]} de los votos VÁLIDOS covered|partial de
    r2/r3 (council.judge_coverage.pertinence) → citations[].pertinent true | 'not-named-by-council (…)'; sin mapa
    → 'not-available (council <council_state>)' (la escalera no cambia de peldaños)."""
    fn = getattr(verify_output, "support_state_for", None)
    ladder = tuple(getattr(verify_output, "SUPPORT_LADDER", None)
                   or ("unresolved", "resolved", "passage_delivered", "supported", "unsupported"))
    na_literal = getattr(verify_output, "PERTINENT_NOT_AVAILABLE", "not-available (ADR-0082)")
    if council_state and council_pertinence is None:
        na_literal = f"not-available (council {council_state})"
    # corrector ADR-0080 (G): la forma degradada conserva la FORMA — los 5 peldaños con null (no medido), no un
    # dict vacío; ladder/pertinent viajan igual para que el front tipe UNA forma
    summary = {"n": len(citations), "by_state": {rung: None for rung in ladder}, "ladder": list(ladder),
               "pertinent": {"state": na_literal, "n_true": 0, "n_not_named": 0, "n_not_available": len(citations),
                             "literal": getattr(verify_output, "PERTINENT_NOT_AVAILABLE", "not-available (ADR-0082)"),
                             "rule": getattr(verify_output, "PERTINENT_RULE", None)}}
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
        kwargs = {"grounding": grounding or None}
        try:
            fn_params = inspect.signature(fn).parameters
        except (TypeError, ValueError):
            fn_params = {}
        if "council_pertinence" in fn_params:   # verify_output ≥ ADR-0082 (G.4); un árbol anterior sigue válido
            kwargs.update(council_pertinence=council_pertinence, council_state=council_state,
                          council_source=council_source)
        per = fn(citations, bundle, **kwargs)
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
        # vez en el resumen, no repetida por cita. ADR-0082 (G.4): + pertinent_to / pertinent_source cuando el consejo juzgó
        for k in ("resolved", "resolved_to", "passage_delivered", "pertinent", "pertinent_to", "pertinent_source",
                  "supported", "support_state"):
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
    # ADR-0083 (E): figure_verification por cita kind 'figure' + figure_citations en el resumen — SÓLO con figuras encendidas
    # (figures_block no-None y sin kill-switch); la escalera NO cambia de peldaños (el caption es el pasaje: F2 la indexa).
    if isinstance(figures_block, dict) and figures_block.get("state") != FIGURES_KILL_SWITCH_STATE:
        summary["figure_citations"] = _figure_verification(citations, figures_block, audit_result)
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
    # ADR-0083 (O.5): figures.enabled / figures.vision NO van aquí — models.snapshot los deriva de su propia ENV_TABLE (F3,
    # SNAPSHOT_FIELDS += figures.*; models.py es la verdad de sus campos y rechaza duplicados desde fuera en extra_ignored).
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


# --- ADR-0083: FIGURAS como evidencia OBSERVADA en la corrida (C etapa propia · D.1 proyección · E citas · G.2 panel · H gasto ·
# L frozen.figures · M kill-switches). La figura es MEDICIÓN sólo cuando código verifica identidad (fig_id del JATS), bytes
# (sha256 recalculado al gatear/servir/embeber) y licencia (tabla cerrada) — lib/figures.py (F1); lo que la imagen DICE es
# JUICIO de dos lentes (composite_auditor.audit figures=, F3); los predicados viven en verify_output.figure_predicates (F2).
# Aquí SÓLO se cablea, se congela con su clase y se MIDE lo que se entregó al panel. Nada binario en el blob (ADR-0074). ----------
# ADR-0086 (F4): la biblioteca de imágenes atestiguadas — import TOLERANTE: un árbol sin ella corre igual y lo declara
try:
    from lib import attestations as attestations_mod
except Exception:                                              # pragma: no cover
    attestations_mod = None
ATTESTED_AGENT = "attestations"                                # `agent` de todo evento stage.attestations.*
ATTESTED_AGENT_ROW = ("attestations (lib/attestations.py — imágenes que aporta una persona: magic bytes + sha256 + borrado "
                      "de metadatos + almacén privado; los bytes sólo a <=2 lentes con visión, jamás al sintetizador)")
ATTESTED_KILL_SWITCH_STATE = "kill-switch WITT_ATTESTED_IMAGES=0"
ATTESTED_DECLARED_EXCEPTIONS = ("render_contract_version", "attested_images",
                                "deterministic_checks.attested_images")    # M.1: EXACTAMENTE 3
ATTESTED_TOOL_UNAVAILABLE_GATE = "tool-unavailable (verify_output.attested_predicates not in tree — ADR-0086)"
ATTESTED_TOOL_UNAVAILABLE_MODULE = "tool-unavailable (ADR-0086: lib/attestations.py not in tree)"
ATTESTED_NO_LEDGER_STATE = "not-applicable (no-ledger)"
THREAD_ATTESTED_MAX = 8                                        # = WITT_ATTESTED_MAX_PER_PLAN por defecto: el tope de un plan
ATTESTED_THREAD_RULE = ("what the PARENT run had: metadata and caption (<= 200 chars), never bytes; withdrawn images are "
                        "excluded and counted (a person who retired an image does not keep feeding it to child runs) "
                        "— ADR-0086 B.6.i")
# corrector (E): el estado del BLOQUE y el de la COMPUERTA son vocabularios DISTINTOS. 'attached' quiere decir "hay imágenes:
# MIDE" → se le pasa None a verify_output para que calcule 'checked' y los dos predicados duros ENTREN a la conjunción; los
# demás estados viajan tal cual y la biblioteca los declara sin fingir que midió (§6). Pasar 'attached' dejaba el gate INERTE.
ATTESTED_CHECK_STATE_OF = {"attached": None, "no-attested-images": "no-attested-images",
                           ATTESTED_KILL_SWITCH_STATE: ATTESTED_KILL_SWITCH_STATE}
ATTESTED_DELIVERY_RULE = ("el sintetizador y el consejo reciben caption y metadatos rotulados ATESTIGUADOS; los BYTES sólo "
                          "llegan a las lentes con visión, que los juzgan y lo declaran — nunca son evidencia ni cita")

FIGURES_AGENT = "figures"                                      # `agent` de todo evento stage.figures.*
FIGURES_AGENT_ROW = "figures (lib/figures.py — JATS parser + fetch by sha + license gate)"
FIGURES_KILL_SWITCH_STATE = "kill-switch WITT_FIGURES=0"
VISION_KILL_SWITCH_STATE = "kill-switch WITT_FIGURES_VISION=0"
FIGURES_DECLARED_EXCEPTIONS = ("render_contract_version", "figures", "deterministic_checks.figures")   # M.1: EXACTAMENTE 3
FIGURES_TOOL_UNAVAILABLE_GATE = "tool-unavailable (verify_output.figure_predicates not in tree — ADR-0083)"
FIGURES_TOOL_UNAVAILABLE_PANEL = "tool-unavailable (composite_auditor.audit without figures= — ADR-0083 F3)"
FIGURES_TOOL_UNAVAILABLE_TOKENS = "tool-unavailable (models.vision_tokens not in tree — ADR-0083 F3)"
FIGURES_TOOL_UNAVAILABLE_RULE = "tool-unavailable (composite_auditor.FIGURE_READING_RULE not in tree — ADR-0083 F3)"
VISION_STATES_EXACT = ("sent", VISION_KILL_SWITCH_STATE, "no-eligible-figures")
VISION_STATES_PREFIXES = ("tool-unavailable (", "error: ")
VISION_LENS_FINDINGS_CLAUSE = ("findings marked from_vision_lens describe images: they are judgment; never adopt a number "
                               "or observation from them unless it appears in a delivered TEXT passage")
FIGURES_STAGE_RULE = ("stage.figures runs AFTER path_b (both trigger sites: structural inside retrieve, competence-gated in "
                      "runs) and BEFORE council r3 / pass2; per selected paper ONE zip GET inside WITT_FIGURES_BUDGET_S; a "
                      "figure that does not download leaves a declared row and the run continues (§6); the synthesizer "
                      "receives caption + metadata (PROMPT_FIGURE_KEYS), never bytes; no Ruta B → state 'no-path-b' and no "
                      "stage.figures.* event; WITT_FIGURES=0 → ONE stage.figures.summary and nothing else")
VISION_SENT_RULE = ("measured in runs.panel_caller from member['figures'] handed to the caller (F3): n_panels = audit() calls "
                    "that received >=1 selected figure; n_attempts_with_images = caller invocations with >=1 figure (each "
                    "attempt re-sends and is billed); bytes_b64_sent_total = sum(len(b64)); visual_tokens_projected_total = "
                    "sum(models.vision_tokens) — PROJECTION; input_tokens measured per judge already include the images")
N_SENT_BY_LENS_RULE = "distinct sha256 delivered to that lens across ALL panels (audit.panel[].saw_figures.sha256s, F3)"

# --- ADR-0084: la WEB como LOCALIZADOR, jamás fuente (A tool Brave · B resolutor de tabla · C familia web en el harness · D admisión
# native-first · E 4 predicados · F consejo/demanda · G runs · H cuota en db · I /usage · J PDF · L kill-switch M.1). Aquí SÓLO se
# cablea y se congela: el bloque lo arma answer_pipeline._web_locator_block (D.4) sobre las filas de search_harness._run_web_family
# (C.5); los vocabularios son los de lib/web_locator.py (W2, UNA verdad: se aliasan, no se copian). Ninguna URL hallada sale de
# frozen.web_locator (ni a eventos, ni a answer.gap_flags, ni al prompt: _PROMPT_PATH_B_TOP / _PROMPT_PAPER_KEYS son ciegas). ------
WEB_LOCATOR_AGENT = "web_locator"                             # `agent` del evento stage.web.locate
WEB_LOCATOR_AGENT_ROW = ("web_locator (lib/web_locator.py — Brave|Anthropic locator + deterministic URL→id resolver; web text never "
                         "enters the bundle)")
WEB_KILL_SWITCH_STATE = getattr(web_locator, "WEB_KILL_SWITCH_STATE", "kill-switch WITT_WEB_LOCATOR=off")   # alias (G.11): una verdad
WEB_DECLARED_EXCEPTIONS = ("render_contract_version", "web_locator", "deterministic_checks.web_locator")   # M.1: EXACTAMENTE 3
# corrector ADR-0084 (L): las 3 excepciones son la verdad para el MISMO fixture SIN datos web (smoke_run_pipeline M.1 ON vs OFF);
# estas llaves ADITIVAS existen SÓLO cuando hubo datos web o la disponibilidad cambió entre plan y corrida — nunca bajo off en un
# fixture sin web (los literales compartidos del consejo DIRECTIVES_RULE / AFTER_SEARCH_RULE volvieron a los de 1.12; la
# ampliación web viaja en llaves propias: council.availability_rule / web_locator_rule). epistemic_summary es OTRA columna
# (epistemic_summary_json), no parte del registro congelado — ahí web_locator_state viaja siempre (patrón figures_state, ADR-0083).
WEB_ADDITIVE_KEYS_WITH_WEB_DATA = ("citations[].located_via", "citations_support_summary.n_located_via_web",
                                   "agents_invoked[web_locator]", "token_usage.web_locator",
                                   "token_usage.estimated_cost_usd_total_projected", "token_usage.total_class",
                                   "token_usage.by_stage.search.web_locator_usd_projected", "search_ledger.plan.families_order_rule",
                                   "path_b.selection.pool_admission_rule", "path_b.selection.tie_break_web_located",
                                   "council.directives[].harness_state_at_plan/at_compile/recomputed (only when they differ)",
                                   "council.directives_excluded[].harness_state_at_plan/at_compile/recomputed (only when they differ)",
                                   "council.coverage.after_search.web_locator_source/web_locator_rule (only with a web ledger)",
                                   "council.coverage.after_search.by_requirement[web].web_locator (only with a web ledger)",
                                   "council.availability_rule (only when a recompute happened)")
WEB_STATE_NOT_REQUESTED_NO_ROUND = "not-requested (no search round)"          # web_locator.WEB_STATES_EXACT[3]
WEB_STATE_NOT_REQUESTED_NO_DIRECTIVE = "not-requested (no web directive)"     # web_locator.WEB_STATES_EXACT[2]
WEB_TOOL_UNAVAILABLE_MODULE = "tool-unavailable (ADR-0084: lib/web_locator.py not in tree)"          # bajo el prefijo glosado
WEB_TOOL_UNAVAILABLE_GATE = "tool-unavailable (verify_output.web_predicates not in tree — ADR-0084)"
WEB_SEARCH_STAGE_NOTE = "Layer 0 tools — no model call (ADR-0080); web locator cost travels apart (ADR-0084)"
WEB_TOTAL_CLASS = ("PROJECTION (tokens × price) + PROJECTION (web locator requests × unit price) — two projections, same class; "
                   "measurement counts travel apart")
WEB_ANTHROPIC_SEARCH_STATE = "measured (anthropic web_search dispatcher)"
# G.4: answer.gap_flags recibe A LO SUMO estos dos strings de CONTEO (viaja a previous_answer.gap_flags → planner y sintetizador del
# turno siguiente, Context 3): la URL vive SÓLO en frozen.web_locator.unresolved[] / gap_flags_typed[] (humano, Hoja, PDF)
WEB_GAP_FLAG_UNRESOLVED = ("web-located-unresolved: {n} URL(s) located on the web could not be resolved to an identifier by code — "
                           "declared in frozen.web_locator.unresolved, never cited")
WEB_GAP_FLAG_UNMATERIALIZED = ("web-located-unmaterialized: {k} identifier(s) located on the web were not found in Europe PMC — "
                               "declared in frozen.web_locator.located, never cited")
WEB_GAP_FLAG_PREFIXES = ("web-located-unresolved:", "web-located-unmaterialized:")
# G.2: bajo off EXPLÍCITO frozen.web_locator se reduce a EXACTAMENTE estas 6 llaves (M.1)
WEB_FROZEN_KILL_SWITCH_KEYS = ("state", "provider", "provider_source", "kill_switch", "state_vocabulary", "rule")
# G.2: contadores del bloque que se OMITEN cuando la familia no MIDIÓ (null en el bloque de D.4 = no midió ≠ 0; en el frozen: ausentes)
WEB_FROZEN_COUNTER_KEYS = ("n_queries_planned", "n_queries_dropped_by_cap", "n_results", "n_located", "n_materialized", "n_epmc_gets",
                           "n_not_found_in_europepmc", "n_fed_ctx", "n_located_not_fed", "n_duplicates_in_response", "n_unresolved",
                           "n_already_present_resolver", "n_already_present_pool", "n_already_present", "n_admitted",
                           "n_located_selected", "n_located_not_selected", "n_papers_web_located",
                           "n_same_paper_dups", "n_epmc_record_mismatch")   # corrector: dedup por paper + trampa del top hit
WEB_FROZEN_SOURCE = ("answer_pipeline.path_b_bundle.web_locator (D.4: union of the web rows of search_harness._run_web_family over "
                     "all rounds + pool admission/selection/fetch closure) frozen by runs (G.2); URLs live only here")


def _web_provider_state():
    """ADR-0084 (M.4): la disponibilidad del localizador leída EN LA CORRIDA (web_locator.provider_state: env WITT_WEB_LOCATOR +
    presencia de BRAVE_API_KEY/ANTHROPIC_API_KEY, jamás sus valores). Sin la rebanada en el árbol → declarado, cero red."""
    env_raw = os.environ.get("WITT_WEB_LOCATOR")
    keys = {"brave": bool((os.environ.get("BRAVE_API_KEY") or "").strip()),
            "anthropic": bool((os.environ.get("ANTHROPIC_API_KEY") or "").strip())}
    if web_locator is None:
        return {"provider": None, "provider_source": None, "available": False, "unavailable_reason": WEB_TOOL_UNAVAILABLE_MODULE,
                "key_present": keys, "env_raw": env_raw, "explicit_off": False}
    try:
        return web_locator.provider_state()
    except Exception as e:   # el lector es tolerante; esto sólo ocurre en un árbol roto — se declara, la corrida sigue
        return {"provider": None, "provider_source": None, "available": False,
                "unavailable_reason": f"error: {type(e).__name__}: {str(e)[:120]}", "key_present": keys, "env_raw": env_raw,
                "explicit_off": False}


def _web_quota_fn():
    """ADR-0084 (G.10/H): el callable de cuota que viaja al harness — db.web_locator_reserve(provider, month, cap, record=None) →
    {granted, n_before, n_after, cap} (UPDATE condicional atómico). None cuando db no lo expone (el harness declara 'not-enforced')."""
    fn = getattr(db, "web_locator_reserve", None)
    return fn if callable(fn) else None


def _web_locator_frozen(block, plan_state, harness_used, ps):
    """ADR-0084 (G.2): frozen.web_locator — SIEMPRE presente en >= 1.13. Tres formas:
      · off EXPLÍCITO (WITT_WEB_LOCATOR=off) → EXACTAMENTE {state 'kill-switch WITT_WEB_LOCATOR=off', provider 'off', provider_source,
        kill_switch {WITT_WEB_LOCATOR, enabled false, source, declared_exceptions [3]}, state_vocabulary, rule} (M.1);
      · Ruta B por el harness → el bloque de answer_pipeline._web_locator_block (D.4) copiado: estado, encabezado (versiones, tabla
        de reglas, lista blanca, política), consultas verbatim, located[] (URL hallada SÓLO aquí) cerrados tras selección/fetch,
        unresolved[] (title_web rotulado), gap_flags_typed[], cost (PROYECCIÓN), quota; los contadores viajan como ENTEROS sólo si la
        familia MIDIÓ — bajo tool-unavailable / not-requested se OMITEN (ADR-0043: no midió ≠ 0);
      · sin Ruta B por el harness → encabezado de web_locator.frozen_header + state por disponibilidad y ruta:
        'tool-unavailable (ADR-0084: BRAVE_API_KEY unset)' (off DERIVADO: la CAUSA viaja aquí, no en el plan) | env inválida |
        proveedor sin llave | 'not-requested (no search round)' (competente o Ruta B legada). Nada se recalcula: lo que la corrida
        no midió queda ausente o null con estado."""
    if web_locator is None:
        return {"state": WEB_TOOL_UNAVAILABLE_MODULE, "provider": ps.get("provider"), "provider_source": ps.get("provider_source"),
                "provider_available": False, "gate": "directive-only", "module_version": None, "resolver_version": None,
                "tool_version": None, "rule": None, "source": "runs (lib/web_locator.py not importable — declared)"}
    header = web_locator.frozen_header()
    if ps.get("explicit_off"):
        return {"state": WEB_KILL_SWITCH_STATE, "provider": "off", "provider_source": ps.get("provider_source"),
                "kill_switch": {"WITT_WEB_LOCATOR": str(ps.get("env_raw") or ""), "enabled": False,
                                "source": ps.get("provider_source"), "declared_exceptions": list(WEB_DECLARED_EXCEPTIONS)},
                "state_vocabulary": header["state_vocabulary"], "rule": header["rule"]}
    wl_block = block.get("web_locator") if isinstance(block, dict) else None
    if harness_used and isinstance(wl_block, dict):
        out = json.loads(json.dumps(wl_block, default=str))   # copia: el bundle conserva el bloque íntegro (bundle_json)
        if not out.get("measured"):
            for k in WEB_FROZEN_COUNTER_KEYS:
                if out.get(k) is None:
                    out.pop(k, None)
            # G.2: la DISPONIBILIDAD manda sobre la ruta — con el proveedor no disponible (brave/anthropic fijado sin llave, env inválida,
            # off derivado) la directiva web se excluyó al COMPILAR (council, F.2) y el bloque de D.4 sólo ve «web no entró al plan»:
            # el frozen declara la CAUSA ('tool-unavailable (ADR-0084: BRAVE_API_KEY unset)' …) y conserva la ruta en state_detail
            if not ps.get("available") and str(out.get("state") or "").startswith("not-requested"):
                cause = web_locator.state_when_not_run(ps)
                if cause:
                    out["state_detail"] = f"{ps.get('unavailable_reason')}; {out.get('state')}"
                    out["state"] = cause
        out["source"] = WEB_FROZEN_SOURCE
        return out
    if not ps.get("available"):
        state, detail = web_locator.state_when_not_run(ps), ps.get("unavailable_reason")
    elif plan_state == "not-requested":
        state, detail = WEB_STATE_NOT_REQUESTED_NO_ROUND, "competent or structural route: no harness round (ADR-0080)"
    else:
        state, detail = WEB_STATE_NOT_REQUESTED_NO_ROUND, f"no harness round in this run (plan_state {plan_state!r})"
    cfg = None
    try:
        cfg = web_locator.env_config()
    except Exception:
        cfg = None
    out = dict(header)
    out.update({
        "block_version": getattr(answer_pipeline, "WEB_LOCATOR_BLOCK_VERSION", None),
        "state": state, "state_detail": detail, "measured": False, "in_plan": False, "plan_exclusion_reason": None,
        "provider": ps.get("provider"), "provider_source": ps.get("provider_source"), "provider_available": bool(ps.get("available")),
        "provider_state": {**ps, "read_at": "runs.execute_run (freeze time; M.4)"},
        "entered_by": None, "directive_requirement_ids": [], "query_source": None, "families_order_rule": None,
        "n_rounds_with_web": 0, "by_round": [], "n_queries": 0,
        "queries": [], "located": [], "unresolved": [], "gap_flags_typed": [],
        "n_gap_flags": {k: 0 for k in getattr(answer_pipeline, "WEB_GAP_KINDS", ("web-located-unresolved", "web-located-unmaterialized"))},
        "quota": {"state": None, "n_before": None, "n_after": None,
                  "cap": int((cfg or {}).get("monthly_cap") or 0) if cfg else None,
                  "cap_source": ((cfg or {}).get("sources") or {}).get("monthly_cap") if cfg else None,
                  "month": None, "hook": None, "n_record_errors": 0, "rule": web_locator.QUOTA_RULE},
        "quota_state": None, "had_web_candidates": False,
        "pool_admission_rule": getattr(answer_pipeline, "WEB_POOL_ADMISSION_RULE", None),
        "tie_break_rule": getattr(answer_pipeline, "WEB_TIE_BREAK_RULE", None),
        # corrector ADR-0084 (G.2): UNA sola forma «no medido» — la de D.4 sin contadores: cost con 0 facturables (nada se envió: 0 es
        # medición de facturables, los conteos de la familia siguen AUSENTES), cost_usd_projected 0.0, reglas y cierre declarados
        "cost": web_locator.cost_of(ps.get("provider") if ps.get("provider") in web_locator.PROVIDERS else "off", 0),
        "cost_usd_projected": 0.0,
        "dedup_layer_rule": getattr(search_harness, "WEB_DEDUP_LAYER_RULE", None),
        "materialize_rule": getattr(search_harness, "WEB_MATERIALIZE_RULE", None),
        "located_close_keys": list(getattr(answer_pipeline, "WEB_LOCATED_CLOSE_KEYS", ())),
        "source": "runs.execute_run (no harness round: state by availability and route; G.2)",
    })
    return out


def _web_gap_flags(block):
    """ADR-0084 (G.4): los <= 2 strings de CONTEO por clase que runs apila en answer.gap_flags tras cada síntesis — desde
    block.web_locator.n_gap_flags (D.4); sólo con n/k > 0; JAMÁS una URL (Context 3: answer.gap_flags viaja al modelo del hijo)."""
    wl_block = block.get("web_locator") if isinstance(block, dict) else None
    if not isinstance(wl_block, dict):
        return []
    ng = wl_block.get("n_gap_flags") or {}
    out = []
    n = int(ng.get("web-located-unresolved") or 0)
    k = int(ng.get("web-located-unmaterialized") or 0)
    if n > 0:
        out.append(WEB_GAP_FLAG_UNRESOLVED.format(n=n))
    if k > 0:
        out.append(WEB_GAP_FLAG_UNMATERIALIZED.format(k=k))
    return out


def _stack_web_gap_flags(answer, bundle):
    """Apila por CÓDIGO (patrón de _default_synthesizer :gap_flags) los conteos del localizador en la pasada que vio la Ruta B —
    sin duplicar si la pasada ya los trae (una revisión recibe previous_answer.gap_flags como insumo y puede repetirlos)."""
    if not isinstance(answer, dict):
        return answer
    new = _web_gap_flags((bundle or {}).get("path_b"))
    if not new:
        return answer
    cur = answer.get("gap_flags")
    cur = list(cur) if isinstance(cur, list) else (_gap_flags_tolerante(cur) or [])
    for s in new:
        if s not in cur:
            cur.append(s)
    answer["gap_flags"] = cur
    return answer


def _web_citations_fill(citations, summary, bundle):
    """ADR-0084 (G.5): citations[] += located_via ('web' | null: la cita resuelve a un paper web-localizado — source_family 'web',
    materializado por Europe PMC — o no) y citations_support_summary += n_located_via_web (int, 0 medido). Sólo con el localizador
    DISPONIBLE en la corrida (ausentes bajo off explícito/derivado — M.1). La cita se casa por `resolved_to` (escalera de
    verify_output) o por su id contra evidence_id de los papers; nada se re-resuelve."""
    papers = ((bundle or {}).get("path_b") or {}).get("papers") or []
    by_id = {}
    for p in papers:
        if isinstance(p, dict) and p.get("evidence_id"):
            by_id[str(p["evidence_id"])] = p
            by_id[str(p["evidence_id"]).lower()] = p
    n = 0
    for c in citations:
        if not isinstance(c, dict):
            continue
        target = c.get("resolved_to") or c.get("id")
        p = by_id.get(str(target)) or by_id.get(str(target).lower()) if target is not None else None
        if p is None and isinstance(target, str) and target.isdigit():
            p = by_id.get(f"PMID:{target}")
        via = "web" if isinstance(p, dict) and p.get("source_family") == "web" else None
        c["located_via"] = via
        n += 1 if via == "web" else 0
    if isinstance(summary, dict):
        summary["n_located_via_web"] = n
    return citations, summary


def _web_usage_ctx(web_frozen):
    """El insumo de _token_usage(web=): cost (B.6) + conteos + quota_state — SÓLO cuando la familia web CORRIÓ en la corrida
    (>= 1 ronda con fila web: n_rounds_with_web > 0); None bajo kill-switch / tool-unavailable / sin directiva (G.7: ausente)."""
    if not isinstance(web_frozen, dict) or int(web_frozen.get("n_rounds_with_web") or 0) <= 0:
        return None
    cost = web_frozen.get("cost") if isinstance(web_frozen.get("cost"), dict) else {}
    out = dict(cost)
    out.update({"state": web_frozen.get("state"), "n_queries": web_frozen.get("n_queries"),
                "n_results": web_frozen.get("n_results"), "n_located": web_frozen.get("n_located"),
                "n_materialized": web_frozen.get("n_materialized"), "n_unresolved": web_frozen.get("n_unresolved"),
                "quota_state": web_frozen.get("quota_state")})
    out.setdefault("usd_projected", web_frozen.get("cost_usd_projected") or 0.0)
    out.setdefault("class", "proyección")
    return out
VISION_CLASS = "model-judgment (figure_readings) — bytes never in the record; tokens PROJECTED; counts/bytes MEASURED"


def _figures_vision_lenses(cfg):
    """(lenses, source) — composite_auditor.vision_lenses(env) (rebanada F3: CSV validado contra models.LENSES) cuando existe;
    si no, la MISMA validación aquí: WITT_FIGURES_VISION_LENSES tokenizada por figures.env_config, un token fuera de
    models.LENSES → default declarado con source 'default-invalid-env:WITT_FIGURES_VISION_LENSES'. Orden = el del CSV."""
    fn = getattr(composite_auditor, "vision_lenses", None)
    if callable(fn):
        try:
            res = fn(os.environ)
            if isinstance(res, tuple) and len(res) >= 2:
                return list(res[0]), str(res[1])
            if isinstance(res, dict):
                return (list(res.get("lenses") or []),
                        str(res.get("lenses_source") or res.get("source") or "composite_auditor.vision_lenses"))
            if isinstance(res, (list, tuple)):
                return list(res), "composite_auditor.vision_lenses"
        except Exception:
            pass   # cae a la validación local, declarada abajo por `source`
    toks = []
    for t in (cfg.get("vision_lenses") or []):
        if t not in toks:
            toks.append(t)
    src = (cfg.get("sources") or {}).get("vision_lenses", "default-unset:WITT_FIGURES_VISION_LENSES")
    if not toks or any(t not in models.LENSES for t in toks):
        default = next(s[2] for s in figures.ENV_SPECS if s[0] == "vision_lenses").split(",")
        return default, "default-invalid-env:WITT_FIGURES_VISION_LENSES"
    return toks, src


def _figures_preview(bundle, cfg, root=None):
    """(n_papers_eligible, n_papers_selected) SIN mutar — espejo de la selección determinista de figures.attach (C) para que
    stage.figures.plan diga qué va a bajar ANTES de bajarlo: papers source ∈ FIGURE_SOURCES con PMCID, fetched.full_text True
    y XML de texto completo en raw_cached (figures.locate_xml); primeros max_papers por selection_rank."""
    papers = ((bundle or {}).get("path_b") or {}).get("papers") or []
    n = 0
    for p in papers:
        if not isinstance(p, dict) or p.get("source") not in figures.FIGURE_SOURCES:
            continue
        sr = p.get("search_rec") or {}
        pmcid = sr.get("pmcid") or (p.get("record") or {}).get("pmcid")
        fetched = p.get("fetched") or {}
        if pmcid and fetched.get("full_text") and figures.locate_xml(fetched.get("raw_cached"), root) is not None:
            n += 1
    return n, min(n, int(cfg["max_papers"]))


def _figures_summary_payload(summary):
    """stage.figures.summary (C): estado + conteos + presupuesto + caché — sin ítems (los ítems van al frozen)."""
    cache = summary.get("cache") or {}
    budget = summary.get("budget") or {}
    return {"state": summary.get("state"),
            **{k: summary.get(k) for k in ("n_papers_eligible", "n_papers_selected", "n_papers_with_xml", "n_figures",
                                           "n_with_caption", "n_fetched", "n_verified", "n_not_fetched", "n_error", "n_mismatch",
                                           "n_embeddable", "n_panel_view", "n_unknown_license")},
            "budget": budget, "over_budget": bool(budget.get("over_budget")),
            "evicted_n": cache.get("evicted_n"), "cache": cache,
            "kill_switch": summary.get("kill_switch")}


FIGURES_EVENT_TYPES = ("stage.figures.plan", "stage.figures.paper", "stage.figures.figure", "stage.figures.summary")  # (C) — vocabulario


def _figures_stage(bundle, run_id, cfg=None, cache_root=None, root=None, cancel_check=None):
    """ADR-0083 (C): la etapa PROPIA `stage.figures` — corre tras la Ruta B (cualquiera de los dos disparadores) y antes de la
    ronda 3 del consejo y de pass2. Selección determinista por código (figures.attach): papers europepmc|pubmed con PMCID,
    texto completo y XML cacheado, en orden selection_rank, primeros max_papers; figuras en orden de documento con los topes
    por paper / por corrida; UN zip por paper dentro de WITT_FIGURES_BUDGET_S; filas declaradas cuando algo no baja (§6).
    Eventos (agent 'figures'): stage.figures.plan (una vez, ANTES de bajar) · stage.figures.paper {phase start} ANTES de cada
    descarga (latido: acota el hueco a UNA descarga <= 45 s) y {phase done} después · stage.figures.figure por figura verified ·
    stage.figures.summary. Con WITT_FIGURES=0: UN summary {state 'kill-switch …'} y nada más; sin Ruta B: sin eventos y
    state 'no-path-b'. Devuelve el resumen (→ frozen.figures; F4 completa n_cited/cited_by_answer/seen_by_lenses/vision al
    congelar) y deja bundle['figures_ledger'] (salvo kill-switch: el bundle es el de 1.11). `cancel_check` corre tras cada
    evento de paper/figura → una cancelación a media etapa deja las filas ya declaradas y la corrida queda `cancelled`.
    F8 (integrador): los CUATRO tipos (FIGURES_EVENT_TYPES) se escriben con db.add_event y el tipo como LITERAL — el gate de
    paridad de la webapp (tools/parity_check.py, superficie (C) ETAPAS) lee esa forma; un emisor indirecto los volvía invisibles."""
    cfg = cfg or figures.env_config()
    if not cfg["figures"]:
        summary = figures.attach(bundle, cfg=cfg)            # kill-switch: no parsea, no baja, no toca ningún paper
        summary.pop("papers", None)
        db.add_event(run_id, "stage.figures.summary", payload=_figures_summary_payload(summary), agent=FIGURES_AGENT)
        return summary
    papers = ((bundle or {}).get("path_b") or {}).get("papers") or []
    if cache_root is None:
        cache_root, _src = figures.cache_dir()
    if not papers:
        summary = figures.attach(bundle, cfg=cfg, cache_root=cache_root, root=root)    # → 'no-path-b', cero eventos
        summary.pop("papers", None)
        bundle["figures_ledger"] = summary
        return summary
    n_elig, n_sel = _figures_preview(bundle, cfg, root)
    lenses, lenses_src = _figures_vision_lenses(cfg)
    db.add_event(run_id, "stage.figures.plan", agent=FIGURES_AGENT, payload={
        "n_papers_eligible": n_elig, "n_papers_selected": n_sel, "caps": cfg["caps"], "budget_s": cfg["budget_s"],
        # F8: el dir se CREA sólo si hay algo que bajar (n_sel > 0); si no, se mide sin tocar el disco (mcp_cache intacto)
        "cache_dir_state": figures.cache_dir_state(cache_root, create=n_sel > 0), "cache_dir_source": figures.cache_dir()[1],
        "ttl_days": cfg["ttl_days"], "cache_max_mb": cfg["cache_max_mb"],
        "vision": {"enabled": bool(cfg["vision"]), "lenses": lenses, "lenses_source": lenses_src,
                   "max_per_lens": cfg["max_per_lens"], "detail": cfg["openai_detail"]},
        "module_version": figures.MODULE_VERSION, "parser_version": figures.PARSER_VERSION,
        "license_table_version": figures.LICENSE_TABLE_VERSION, "mechanism": figures.MECHANISM, "rule": FIGURES_STAGE_RULE})
    if cancel_check:
        cancel_check()

    def _on_event(kind, payload):
        if kind == "paper":
            db.add_event(run_id, "stage.figures.paper", payload=payload, agent=FIGURES_AGENT,
                         level="warning" if (payload.get("phase") == "done" and payload.get("error")) else "info")
        elif kind == "figure":
            db.add_event(run_id, "stage.figures.figure", payload=payload, agent=FIGURES_AGENT)
        if cancel_check:
            cancel_check()

    try:
        summary = figures.attach(bundle, cfg=cfg, cache_root=cache_root, root=root, on_event=_on_event)
    except RunCancelled:
        raise
    except Exception as e:   # §6 no-hang: la etapa jamás tumba la corrida — el estado se declara con su tipo
        summary = figures.attach({"path_b": {"papers": []}}, cfg=cfg, cache_root=cache_root, root=root)
        summary["state"] = f"error: {type(e).__name__}: {str(e)[:120]}"
        summary["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    summary.pop("papers", None)
    bundle["figures_ledger"] = summary
    level = "warning" if (summary.get("budget") or {}).get("over_budget") or str(summary.get("state")).startswith("error") else "info"
    db.add_event(run_id, "stage.figures.summary", payload=_figures_summary_payload(summary), agent=FIGURES_AGENT, level=level)
    return summary


def _figure_citation_ns(citations, figures_block):
    """{item_id: [n…]} — qué figuras cita la respuesta y con qué marcadores (E/G.2: citadas primero). corrector: el MISMO
    clasificador superset que _figure_verification y verify_output (kind 'figure' ∨ forma '<PMCID>#<fig_id>' ∨ id que resuelve)."""
    idx = _figure_items_index(figures_block)
    out = {}
    for c in citations or []:
        if not _is_figure_citation(c, idx):
            continue
        it = _figure_item_for(c, idx)
        if it is not None and isinstance(c.get("n"), int):
            out.setdefault(it["id"], []).append(c["n"])
    return out


def _figures_for_panel(bundle, answer, cfg, cache_root):
    """ADR-0083 (G.2): lo que UNA lente con visión puede ver en ESTE panel — figures.select_for_panel sobre los ítems del
    bundle (panel_view ∧ verified ∧ caption present; citadas por la respuesta primero, luego rank, luego orden de documento;
    topes por lente / por imagen / por petición; el sha se RECALCULA al leer). Devuelve {figures [PANEL_FIGURE_KEYS con b64],
    state, selection, cited_ns}. Con WITT_FIGURES_VISION=0 no se lee ni un byte."""
    summary = (bundle or {}).get("figures_ledger") or {}
    items = summary.get("items") or []
    out = {"figures": [], "state": None, "selection": None,
           "cited_ns": _figure_citation_ns(_citations_of(answer)[0], summary)}
    if not cfg["vision"]:
        out["state"] = VISION_KILL_SWITCH_STATE
        return out
    if not items:
        out["state"] = "no-eligible-figures"
        return out
    try:
        sel = figures.select_for_panel(items, cache_root, cfg=cfg, cited_ns=out["cited_ns"])
    except Exception as e:   # §6: la selección jamás tumba la corrida — el panel corre sin imágenes, declarado
        out["state"] = f"error: {type(e).__name__}: {str(e)[:120]}"
        return out
    out["selection"] = {k: sel.get(k) for k in ("n_eligible", "n_selected", "n_dropped_by_request_cap", "n_excluded",
                                                 "bytes_b64_total", "rule")}
    out["figures"] = sel.get("figures") or []
    out["state"] = "sent" if out["figures"] else "no-eligible-figures"
    return out


def _audit_accepts_figures():
    """(accepts_figures, accepts_vision_lenses) — la firma de composite_auditor.audit del árbol (F3: figures=, vision_lenses=);
    un árbol anterior sigue válido y el registro DECLARA que no se entregó (jamás se finge)."""
    try:
        params = inspect.signature(composite_auditor.audit).parameters
    except (TypeError, ValueError):
        return False, False
    varkw = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
    return ("figures" in params or varkw), ("vision_lenses" in params or varkw)


# =====================================================================================================================
# ADR-0086 (K) · LAS IMÁGENES ATESTIGUADAS EN LA CORRIDA
# ---------------------------------------------------------------------------------------------------------------------
# Lo que una persona aportó por el ledger del consejo: el servidor lee las filas del plan (adjuntas y vivas), declara la
# etapa con sus eventos, entrega los BYTES sólo a las lentes con visión y congela identidad y procedencia SIN un solo byte.
# =====================================================================================================================
def _attested_cfg():
    """(cfg, storage, probe) leídos EN LA LLAMADA — (None, None, None) si la biblioteca no está en el árbol."""
    if attestations_mod is None:
        return None, None, None
    try:
        cfg = attestations_mod.env_config()
        storage, probe = attestations_mod.storage_backend(cfg=cfg)
        return cfg, storage, probe
    except Exception:
        return None, None, None


def _attested_rows_for_run(plan_id, cfg):
    """(filas ADJUNTAS y vivas del plan, estado) — la compuerta humana manda: una imagen subida que el ledger no selló no
    entra a ninguna corrida. `plan_id` sale de la copia del consejo (la corrida no tiene columna propia); sin plan no hay
    ledger y el estado lo dice: 'not-applicable (no-ledger)' NO es 'no había imágenes'."""
    if attestations_mod is None:
        return [], ATTESTED_TOOL_UNAVAILABLE_MODULE
    if cfg is not None and not cfg.get("enabled", True):
        return [], ATTESTED_KILL_SWITCH_STATE
    if not plan_id:
        return [], ATTESTED_NO_LEDGER_STATE
    try:
        if db.attested_schema_state() != "ready":
            return [], f"error: attested table {db.attested_schema_state()}"
        rows = db.attested_images_of_plan(plan_id, include_withdrawn=False, attached_only=True)
    except Exception as e:
        return [], f"error: {type(e).__name__}: {str(e)[:120]}"
    return rows, ("attached" if rows else "no-attested-images")



def _attested_ledger_images(images):
    """{} | {images[], n_images} para frozen.council.ledger (J.4) — la forma la declara attestations.ledger_item."""
    if not images or attestations_mod is None:
        return {}
    out = []
    for row in images:
        try:
            out.append(attestations_mod.ledger_item(row))
        except Exception:
            continue
    return {"images": out, "n_images": len(out)} if out else {}


def _attested_thread_items(frozen_padre):
    """(B.6.i) thread_context.parent_attested_images[] — lo que el padre TUVO, leído de SU registro congelado (jamás de la
    tabla viva: el contexto del hilo es lo que pasó, no lo que quedó hoy). Se excluyen las RETIRADAS: una imagen que su
    autora retiró no sigue viajando a las corridas hijas, y el meta DICE cuántas se excluyeron (no desaparecen en silencio).
    Caption ≤ 200 (attestations.thread_item). Un padre sin imágenes no hace nacer ninguna llave (M.1)."""
    if attestations_mod is None or not isinstance(frozen_padre, dict):
        return {}
    bloque = frozen_padre.get("attested_images")
    items = bloque.get("items") if isinstance(bloque, dict) else None
    if not isinstance(items, list) or not items:
        return {}
    out, n_wd = [], 0
    for it in items[:THREAD_ATTESTED_MAX]:
        if not isinstance(it, dict) or not it.get("sha256"):
            continue
        if it.get("withdrawn"):
            n_wd += 1
            continue
        fila = {"sha256": it["sha256"], "caption": it.get("caption"), "uploaded_by": it.get("uploaded_by"),
                "uploaded_at": it.get("uploaded_at"),
                "consent_kind": (it.get("consent") or {}).get("kind") if isinstance(it.get("consent"), dict) else None,
                "patient_material": bool(it.get("patient_material"))}
        try:
            out.append(attestations_mod.thread_item(fila, seen_by_lenses=it.get("seen_by_lenses") or []))
        except Exception:
            continue
    if not out and not n_wd:
        return {}
    return {"parent_attested_images": out,
            "parent_attested_images_meta": {"n": len(out), "n_withdrawn_excluded": n_wd,
                                            "n_truncated": max(0, len(items) - THREAD_ATTESTED_MAX),
                                            "caption_chars": attestations_mod.THREAD_CAPTION_CHARS,
                                            "rule": ATTESTED_THREAD_RULE}}


def _attested_stage(rows, state, run_id, cfg, probe):
    """Los eventos de la etapa (uno por imagen + el resumen) y el ESQUELETO del bloque congelado. Ningún byte, ningún
    caption completo en el evento: identidad, procedencia y estado. Bajo kill-switch no se emite ni un evento (M.1)."""
    base = {"state": state, "n_attached": len(rows), "rule": ATTESTED_DELIVERY_RULE,
            "delivery": {"synthesizer": "captions-only", "bytes_to_synthesizer": False,
                         "council": "captions-only", "panel": "bytes to <=2 vision lenses"},
            "storage": {"backend": (probe or {}).get("backend"), "state": (probe or {}).get("state"),
                        "durability": (attestations_mod.durability_of(probe) if (attestations_mod and probe) else None)},
            "items": [],            # `vision` NACE sólo cuando el panel midió: una llave en null sería ruido (M.1)
            "vocabulary": (dict(attestations_mod.VOCABULARY) if attestations_mod is not None else None)}
    if state == ATTESTED_KILL_SWITCH_STATE or not rows:
        return base
    db.add_event(run_id, "stage.attestations.plan", agent=ATTESTED_AGENT,
                 payload={"state": state, "n_attached": len(rows),
                          "storage_backend": (probe or {}).get("backend"),
                          "max_per_lens": (cfg or {}).get("max_per_lens"),
                          "rule": ATTESTED_DELIVERY_RULE})
    items = []
    for row in rows:
        try:
            item = attestations_mod.frozen_item(row)
        except Exception as e:
            item = {"sha256": row.get("sha256"), "state": f"error: {type(e).__name__}"}
        items.append(item)
        db.add_event(run_id, "stage.attestations.image", agent=ATTESTED_AGENT,
                     payload={"id": item.get("id"), "sha256_short": item.get("sha256_short"),
                              "media_type": item.get("media_type"), "dims": item.get("dims"),
                              "attached_to": item.get("attached_to"), "requirement_id": item.get("requirement_id"),
                              "uploaded_by": item.get("uploaded_by"), "patient_material": item.get("patient_material"),
                              "exif_state": item.get("exif_state"), "class": item.get("class")})
    base["items"] = items
    return base


def _attested_for_panel(rows, cfg, storage, figs_b64_total=0):
    """Lo que las lentes con visión PUEDEN ver: bytes leídos del almacén con el sha RECALCULADO al leer, con su tope y el
    presupuesto compartido con las figuras. Un error del almacén jamás tumba la corrida: se declara y el panel corre sin
    imágenes aportadas (§6)."""
    if attestations_mod is None or storage is None or not rows:
        return {"attested": [], "state": "no-eligible-attested"}
    if cfg is not None and not cfg.get("vision", True):
        return {"attested": [], "state": "kill-switch WITT_ATTESTED_VISION=0"}
    try:
        sel = attestations_mod.select_for_panel(rows, storage, cfg=cfg, figures_b64_total=int(figs_b64_total or 0))
    except Exception as e:
        return {"attested": [], "state": f"error: {type(e).__name__}: {str(e)[:120]}"}
    sel["state"] = "sent" if sel.get("attested") else "no-eligible-attested"
    return sel


def _attested_panel_kwargs(rows, cfg, storage, panel_selections, figs_b64_total=0):
    """kwargs ADITIVOS para composite_auditor.audit — {} cuando no hay imágenes aportadas o la firma del árbol no las
    acepta (la llamada queda EXACTAMENTE como en 1.13)."""
    if not rows:
        return {}
    try:
        acepta = "attested" in inspect.signature(composite_auditor.audit).parameters
    except (TypeError, ValueError):
        acepta = False
    sel = _attested_for_panel(rows, cfg, storage, figs_b64_total)
    entregadas = list(sel.get("attested") or [])
    panel_selections.append({"state": sel.get("state"), "n_attested": len(entregadas), "delivered": bool(entregadas) and acepta,
                             "sha256s": [a.get("sha256") for a in entregadas],
                             "n_dropped": sel.get("n_dropped"), "storage_errors": sel.get("storage_errors") or [],
                             "rule": sel.get("rule")})
    return {"attested": entregadas} if (acepta and entregadas) else {}


def _attested_fill(block, panel_rows_all, panel_selections, run_id):
    """Cierra el bloque con lo que el panel MIDIÓ: quién vio cada imagen, cuántas lecturas hubo (JUICIO) y el resumen de
    la entrega. Emite el evento de resumen. Nada de esto se re-deriva al servir (frozen-counter)."""
    if not isinstance(block, dict) or not block.get("items"):
        return block
    vistos, leidas = {}, {}
    n_readings = 0
    for r in (panel_rows_all or []):
        saw = r.get("saw_attested") if isinstance(r, dict) else None
        if not isinstance(saw, dict):
            continue
        for sha in (saw.get("sha256s") or []):
            vistos.setdefault(sha, []).append(r.get("lens"))
        if isinstance(r.get("attested_readings"), list):
            n_readings += len(r["attested_readings"])
            for lec in r["attested_readings"]:
                if isinstance(lec, dict) and lec.get("sha256"):
                    leidas[lec["sha256"]] = leidas.get(lec["sha256"], 0) + 1
    # la FORMA del ítem la declara attestations.frozen_item (ATTESTED_FROZEN_KEYS): aquí sólo se rellenan DOS llaves que ya
    # existen en ella — quién lo vio y cuántas lecturas emitió el panel sobre él. Ninguna llave nueva nace en el llamador.
    for it in block["items"]:
        it["seen_by_lenses"] = sorted(set(vistos.get(it.get("sha256"), [])))
        it["n_readings"] = int(leidas.get(it.get("sha256"), 0))
    block["vision"] = {"n_selections": len(panel_selections or []),
                       "n_delivered_total": sum(int(p.get("n_attested") or 0) for p in (panel_selections or [])),
                       "n_readings": n_readings, "readings_class": "model-judgment",
                       "selections": list(panel_selections or [])}
    block["n_seen_by_panel"] = sum(1 for it in block["items"] if it.get("seen_by_lenses"))
    db.add_event(run_id, "stage.attestations.summary", agent=ATTESTED_AGENT,
                 payload={"state": block.get("state"), "n_attached": block.get("n_attached"),
                          "n_seen_by_panel": block.get("n_seen_by_panel"),
                          "n_readings": n_readings, "readings_class": "model-judgment",
                          "bytes_to_synthesizer": False})
    return block


def _attested_usage(block):
    """token_usage.attested_images — conteos MEDIDOS (ninguna proyección: el costo de visión ya viaja en los tokens de
    entrada medidos del juez, ADR-0083 H)."""
    if not isinstance(block, dict):
        return None
    return {"state": block.get("state"), "n_attached": int(block.get("n_attached") or 0),
            "n_seen_by_panel": int(block.get("n_seen_by_panel") or 0),
            "n_readings": int(((block.get("vision") or {}).get("n_readings")) or 0),
            "bytes_total": sum(int(it.get("bytes") or 0) for it in (block.get("items") or [])),
            "class": "medición (conteos y bytes; los tokens de visión ya están en los input_tokens medidos del panel)"}


def _figures_panel_kwargs(bundle, answer, cfg, cache_root, lenses, enabled, vision_sent, panel_selections):
    """kwargs ADITIVOS para composite_auditor.audit (G.2) — {} bajo kill-switch (la llamada es EXACTAMENTE la de 1.11) o
    cuando la firma del árbol no los acepta. Registra la selección de ESTE panel en `panel_selections` y suma n_panels."""
    if not enabled:
        return {}
    pf = _figures_for_panel(bundle, answer, cfg, cache_root)
    acc_f, acc_l = _audit_accepts_figures()
    pf["delivered"] = bool(pf["figures"]) and acc_f
    panel_selections.append({k: pf[k] for k in ("state", "selection", "delivered")}
                            | {"n_figures": len(pf["figures"]), "sha256s": [f.get("sha256") for f in pf["figures"]]})
    kw = {}
    if acc_f:
        kw["figures"] = pf["figures"]
    if acc_l:
        kw["vision_lenses"] = list(lenses)
    if pf["delivered"]:
        vision_sent["n_panels"] += 1
    return kw


def _figures_fill(summary, answer, panel_rows_all, cfg, lenses, lenses_src, vision_sent, panel_selections):
    """ADR-0083 (L): completa el bloque congelado con lo que SÓLO la corrida sabe — cited_by_answer (citas kind 'figure' de la
    respuesta FINAL), seen_by_lenses / selection.n_sent_to_panel_by_lens (audit.panel[].saw_figures, F3), n_cited y el bloque
    `vision` {state, lenses, rule, sent MEDIDO, cost_projection PROYECTADA}. Muta EN SITIO antes del re-sellado de identidad."""
    items = summary.get("items") or []
    cited = _figure_citation_ns(_citations_of(answer)[0], summary)
    for it in items:
        it["cited_by_answer"] = sorted(set(cited.get(it["id"], [])))
        it["seen_by_lenses"] = []
    summary["n_cited"] = sum(1 for it in items if it["cited_by_answer"])
    by_sha = {it.get("sha256"): it for it in items if it.get("sha256")}
    shas_by_lens = {}
    for row in panel_rows_all or []:
        saw = row.get("saw_figures") if isinstance(row.get("saw_figures"), dict) else None
        if not saw:
            continue
        lens = row.get("lens")
        for sha in (saw.get("sha256s") or []):
            if not isinstance(sha, str):
                continue
            shas_by_lens.setdefault(lens, set()).add(sha)
            it = by_sha.get(sha)
            if it is not None and lens not in it["seen_by_lenses"]:
                it["seen_by_lenses"].append(lens)
    summary.setdefault("selection", {"rule": figures.SELECTION_RULE})
    summary["selection"]["n_sent_to_panel_by_lens"] = {lens: len(s) for lens, s in shas_by_lens.items()}
    summary["selection"]["n_sent_by_lens_rule"] = N_SENT_BY_LENS_RULE
    summary["vision"] = _figures_vision_block(cfg, lenses, lenses_src, vision_sent, panel_selections, panel_rows_all, items)
    return summary


def _figures_vision_block(cfg, lenses, lenses_src, vision_sent, panel_selections, panel_rows_all, items):
    """frozen.figures.vision (L/H): estado, lentes, regla (FIGURE_READING_RULE verbatim de composite_auditor, F3),
    `sent` MEDIDO en panel_caller, `cost_projection` por lente (models.vision_tokens × models.prices, clase proyección),
    la selección por panel y qué aceptó la firma del árbol."""
    acc_f, acc_l = _audit_accepts_figures()
    if not cfg["vision"]:
        state = VISION_KILL_SWITCH_STATE
    elif not acc_f:
        state = FIGURES_TOOL_UNAVAILABLE_PANEL
    elif any(s.get("delivered") for s in panel_selections):
        state = "sent"
    else:
        state = "no-eligible-figures"
    rule = getattr(composite_auditor, "FIGURE_READING_RULE", None)
    by_rev = _vision_by_reviewer(panel_rows_all, items, cfg["openai_detail"])
    per_lens, total = [], 0.0
    priced = True
    lens_of = {}
    for row in panel_rows_all or []:
        if isinstance(row.get("saw_figures"), dict) and row.get("reviewer"):
            lens_of.setdefault(row["reviewer"], row.get("lens"))
    for reviewer, v in by_rev.items():
        toks = v.get("visual_tokens_projected")
        usd = None
        if isinstance(toks, int) and reviewer in PRICES_PER_MTOK_USD:
            usd = round(toks * PRICES_PER_MTOK_USD[reviewer][0] / 1e6, 6)
            total += usd
        else:
            priced = False
        per_lens.append({"lens": lens_of.get(reviewer), "reviewer": reviewer, "model": reviewer, "tier": v.get("tier"),
                         "n_images": v["n_images"], "visual_tokens_projected": toks, "usd_projected": usd,
                         "tokens_state": v.get("tokens_state")})
    sent = dict(vision_sent)
    return {"state": state, "enabled": bool(cfg["vision"]), "lenses": list(lenses), "lenses_source": lenses_src,
            "rule": rule, "rule_state": "declared (composite_auditor.FIGURE_READING_RULE)" if rule else FIGURES_TOOL_UNAVAILABLE_RULE,
            "openai_detail": cfg["openai_detail"], "openai_chat_form_state": figures.OPENAI_CHAT_FORM_STATE,
            "max_per_lens": cfg["max_per_lens"], "max_image_mb": cfg["max_image_mb"], "request_b64_mb": figures.REQUEST_B64_MB,
            "sent": sent,
            "cost_projection": {"per_lens": per_lens,
                                "total_usd_projected": round(total, 6) if (per_lens and priced) else None,
                                "prices_source": "models.prices() (ADR-0081)", "class": "proyección",
                                "complete": bool(per_lens) and priced},
            "panels": panel_selections,
            "delivery": {"audit_accepts_figures": acc_f, "audit_accepts_vision_lenses": acc_l},
            "vocabulary": {"states_exact": list(VISION_STATES_EXACT), "states_prefixes": list(VISION_STATES_PREFIXES),
                           "vision_lenses": list(getattr(composite_auditor, "VISION_LENSES", ()) or ()),
                           "saw_figures_details": list(getattr(composite_auditor, "SAW_FIGURES_DETAILS", ()) or ())},
            "class": VISION_CLASS}


def _figures_usage_ctx(enabled, summary, cfg):
    """El insumo de _token_usage(figures=): {enabled, items, openai_detail} — None bajo kill-switch (by_model[*] no gana vision)."""
    if not enabled:
        return None
    return {"enabled": True, "items": (summary or {}).get("items") or [], "openai_detail": cfg["openai_detail"],
            "summary": summary if isinstance(summary, dict) else None}


def _gate_event_payload(checks):
    """stage.deterministic_gate += figures_state (ADR-0083 L) + web_locator_state (ADR-0084 G.6) — el evento, no el frozen (los
    fragmentos íntegros van en checks['figures'] / checks['web_locator'])."""
    return dict(checks, figures_state=(checks.get("figures") or {}).get("state"),
                web_locator_state=(checks.get("web_locator") or {}).get("state"))


# --- ADR-0082: el CONSEJO DE CRITERIO en la corrida (F.4 copia congelada · F.5 atestiguado ≠ evidencia · G orden de
# etapas y componente · H gasto · J frozen.council). El consejo NUNCA escribe respuesta, veredicto ni ranking (§7): aquí
# sólo se cablea lo que lib/council.py (C2) mide y agrega por código, y se congela con su clase y su estado. ------------
COUNCIL_AGENT = "council"                                   # `agent` de todo evento stage.council.*
COUNCIL_STATE_NO_LEDGER = "not-applicable (no-ledger)"
COUNCIL_STATE_DISABLED = "disabled (kill-switch WITT_COUNCIL=0)"
COUNCIL_STATE_PENDING_R2 = "pending-r2"                     # centinela INTERNO: la ronda 2 decide el estado (jamás se congela)
COUNCIL_LEDGER_FROZEN_TEXT_CAP = 600                        # attested_text / knowledge_now en el frozen (íntegros en plans)
COUNCIL_MEMBERSHIP_SOURCE_PLAN = "plan.council (frozen at r1)"
COUNCIL_MEMBERSHIP_SOURCE_ENV = "agent_matrix.council_members (env at execution — plan without frozen members)"
COUNCIL_DECIDED_BY = "code (council.aggregate_*)"
POST_SEARCH_MERGE_RULE = ("post_search = council.judge_coverage over the UNION of the r2 rows of members NOT re-invoked in r3 "
                          "and the r3 rows (status ok) of the re-invoked members: a member's r3 judgment REPLACES its r2 "
                          "judgment; nothing is re-judged twice; r3 never re-gates (informative — ADR-0082 C.7)")
AFTER_SEARCH_ITEMS_RULE = ("items = bundle.path_b.papers (what ENTERED the run after the directed search); "
                           "directive_requirement_ids taken from the item when the harness wrote it (Layer-0 items keep "
                           "the key), else family-level attribution from search_plan.queries[fam].directive_requirement_ids "
                           "when the family entered ONLY by directive (entered_by 'directive'); a literature paper loses the "
                           "key in answer_pipeline._paper_item → 'not-attributable' (declared, never inferred)")
COUNCIL_CACHE_HIT_RATIO_RULE = ("hit_ratio = cache_read / (cache_read + cache_creation) over the round's member usage "
                                "(API usage.cache_*); null when neither was measured")
ATTESTATION_LEAK_RULE = ("ids in human_attestations (knowledge_now + attested_text of `aporto` requirements) AND in "
                         "direct_answer AND absent from the run's evidence_ids + evidence text; patterns: "
                         + ", ".join(f"{k}={v.pattern}" for k, v in IDENTIFIER_PATTERNS.items()) + " (ADR-0082 F.5)")
COUNCIL_CHECKS_RULE = ("counts only — the panel is HANDED deterministic_checks.council {must_uncovered_pre/post, "
                       "n_hallucinated_votes, n_directives, n_requirements_kept} with its class; no council prose travels "
                       "to the judges (ADR-0082 G.6)")
COUNCIL_SUMMARY_SYNTH_RULE = ("thread_context.council_summary (parent's council: gap ≤200 written by the members, "
                              "flags[].statement, coverage_final, decision) is handed to the PLANNER and to the council's "
                              "round 1 of turn N+1 ONLY; the synthesizer receives thread_context WITHOUT that key (E5 default: "
                              "a synthesizer that reads the uncovered criteria is an ADR with held-out — corrector ADR-0082 G.9)")
COUNCIL_MEMBERSHIP_SOURCE_NONE = ("not-available (no council copy: membership and N are facts of the plan's round 1, not of "
                                  "this run — corrector ADR-0082 J/G.8)")


def _council_json_of(run):
    """runs.council_json (F.4) parseado: dict | None (ausente) | {r1_state 'errored (council_json unparseable)'}."""
    raw = run.get("council_json") if isinstance(run, dict) else None
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        cj = json.loads(raw)
    except (TypeError, ValueError):
        return {"r1_state": "errored (council_json unparseable)", "r1": None, "ledger": None}
    return cj if isinstance(cj, dict) else None


def council_ledger_from(council_json):
    """El ledger en la FORMA de lib/council (requirements[] con `decision`) desde runs.council_json {r1, ledger} (F.4).
    Tolerante a las DOS formas del ledger: la de council.apply_ledger_decisions (requirements[]) y el sobre HTTP de app
    (C6: decisions[] por requirement_id + knowledge_now + approved_by…) — ésta se FUSIONA con r1.requirements[] (el
    agregado de la ronda 1) por requirement_id: un requisito sin decisión queda 'pending' (no kept), una decisión sin
    requisito se declara en decisions_without_requirement[]. None = sin ledger (r1 no corrió o nadie aprobó/saltó)."""
    cj = council_json if isinstance(council_json, dict) else {}
    led = cj.get("ledger")
    if not isinstance(led, dict):
        return None
    r1 = cj.get("r1") if isinstance(cj.get("r1"), dict) else {}
    agg_reqs = r1.get("requirements")
    if agg_reqs is None:
        agg_reqs = (r1.get("aggregation") or {}).get("requirements") or []
    out = {"state": led.get("state"), "plan_id": led.get("plan_id") or cj.get("plan_id"),
           "ledger_version": led.get("ledger_version"),
           "approved_by": led.get("approved_by"), "approved_at": led.get("approved_at"),
           "approved_by_is_author": led.get("approved_by_is_author"),
           "skipped_by": led.get("skipped_by"), "skipped_at": led.get("skipped_at"),
           "skip_reason": led.get("reason") if led.get("state") == "skipped-by-human" else None,
           "knowledge_now": led.get("knowledge_now") if isinstance(led.get("knowledge_now"), dict) else None,
           "flags": list(led.get("flags") or r1.get("flags") or []),
           "truncated": bool(r1.get("truncated")), "n_truncated": int(r1.get("n_truncated") or 0)}
    if isinstance(led.get("requirements"), list):
        reqs = [dict(r) for r in led["requirements"] if isinstance(r, dict) and r.get("requirement_id")]
        out["requirements_source"] = "ledger.requirements (council.apply_ledger_decisions form)"
        out["decisions_without_requirement"] = []
    else:
        decs = {d.get("requirement_id"): d for d in (led.get("decisions") or []) if isinstance(d, dict)}
        reqs = []
        for r in agg_reqs:
            if not isinstance(r, dict) or not r.get("requirement_id"):
                continue
            q = dict(r)
            d = decs.get(q["requirement_id"]) or {}
            q["decision"] = d.get("decision") or "pending"
            q["decided_by"] = d.get("decided_by")
            q["decided_at"] = d.get("decided_at")
            if d.get("reason") is not None:
                q["decision_reason"] = d["reason"]
            if d.get("attested_text") is not None:
                q["attested_text"] = d["attested_text"]
                q["attested_class"] = d.get("attested_class") or "attested"
                q["attested_chars"] = (d["attested_chars"] if isinstance(d.get("attested_chars"), int)
                                       else len(str(d["attested_text"])))
            reqs.append(q)
        out["requirements_source"] = "r1.requirements ⨝ ledger.decisions by requirement_id (app HTTP ledger form, C6)"
        known = {q["requirement_id"] for q in reqs}
        out["decisions_without_requirement"] = sorted(str(rid) for rid in decs if rid not in known)
    for q in reqs:
        q.setdefault("decision", "pending")
    out["requirements"] = reqs
    out["n_requirements"] = len(reqs)
    out["n_kept"] = sum(1 for q in reqs if q["decision"] == "keep")
    out["n_discarded"] = sum(1 for q in reqs if q["decision"] == "discard")
    out["n_attested"] = sum(1 for q in reqs if q["decision"] == "aporto")
    out["n_pending"] = sum(1 for q in reqs if q["decision"] == "pending")
    out["n_hard_rule"] = sum(1 for q in reqs if q.get("hard_rule_gate"))
    out["source"] = "runs.council_json.ledger (plans.council_ledger_json copied at enqueue, F.4)"
    return out


def _council_members_frozen(council_json, env=None):
    """(members[], N, source, full_council) — la membresía y N quedan CONGELADOS en la copia del plan (F.4): r2/r3 usan
    `members[]` del plan, no la env vigente (cambiar WITT_COUNCIL_FULL entre plan y corrida no mueve el cuórum en
    silencio). Sin copia con miembros → agent_matrix.council_members(env, full=<full_council del plan | env>), declarado."""
    if council_json is None:
        # corrector ADR-0082 (J/G.8): sin copia NO hay consejo en esta corrida — N y members son hechos de la ronda 1 del
        # plan, no de la tabla vigente al ejecutar; congelar 17 aquí era una segunda verdad frente a epistemic (null)
        return [], None, COUNCIL_MEMBERSHIP_SOURCE_NONE, None
    cj = council_json if isinstance(council_json, dict) else {}
    members = cj.get("members")
    if isinstance(members, list) and members and all(isinstance(m, str) for m in members):
        return list(members), len(members), COUNCIL_MEMBERSHIP_SOURCE_PLAN, bool(cj.get("full_council"))
    full = cj.get("full_council") if isinstance(cj.get("full_council"), bool) else None
    mem = agent_matrix.council_members(env, full=full)
    is_full, _src = agent_matrix.council_full(env, full=full)
    return mem, len(mem), COUNCIL_MEMBERSHIP_SOURCE_ENV, is_full


def human_attestations_of(ledger, images=None):
    """(F.5) Lo que el humano ATESTIGUÓ en el ledger APROBADO — {knowledge_now {text, by, at, chars, truncated, class},
    attestations[] {requirement_id, text, by, at, class}, n_attestations, class 'attested', rule} | None. Viaja al
    sintetizador como llave HERMANA de evidence (jamás dentro) y a r2/r3 como PRIOR ART etiquetado; al panel NO viaja."""
    if not isinstance(ledger, dict) or ledger.get("state") != "approved":
        return None
    items = []
    for r in ledger.get("requirements") or []:
        if r.get("decision") == "aporto" and r.get("attested_text"):
            items.append({"requirement_id": r.get("requirement_id"), "text": str(r["attested_text"]),
                          "by": r.get("decided_by"), "at": r.get("decided_at"), "class": "attested"})
    kn = ledger.get("knowledge_now")
    kn_view = None
    if isinstance(kn, dict) and str(kn.get("text") or "").strip():
        kn_view = {"text": str(kn["text"]), "by": kn.get("by"), "at": kn.get("at"),
                   "chars": kn.get("chars") if isinstance(kn.get("chars"), int) else len(str(kn["text"])),
                   "truncated": bool(kn.get("truncated")), "class": "attested"}
    # ADR-0086 (K): las IMÁGENES aportadas viajan aquí como caption + metadatos rotulados — jamás un byte (prompt_item)
    imgs = []
    if images and attestations_mod is not None:
        for row in images:
            try:
                imgs.append(attestations_mod.prompt_item(row))
            except Exception:
                continue
    if not items and kn_view is None and not imgs:
        return None
    if imgs:
        return {"knowledge_now": kn_view, "attestations": items, "n_attestations": len(items),
                "images": imgs, "n_images": len(imgs), "images_delivery": ATTESTED_DELIVERY_RULE,
                "class": "attested",
            "rule": ("PRIOR ART attested by humans (ledger `aporto` + knowledge_now) — never evidence; sibling key of "
                     "`evidence` in the synthesizer prompt; identifiers from it must appear in evidence to be cited "
                         "(attestation_identifier_leak, hard predicate) — ADR-0082 F.5")}
    return {"knowledge_now": kn_view, "attestations": items, "n_attestations": len(items), "class": "attested",
            "rule": ("PRIOR ART attested by humans (ledger `aporto` + knowledge_now) — never evidence; sibling key of "
                     "`evidence` in the synthesizer prompt; identifiers from it must appear in evidence to be cited "
                     "(attestation_identifier_leak, hard predicate) — ADR-0082 F.5")}


def attestation_identifier_leak(attestations, direct_answer, evidence_ids, evidence_text=""):
    """(F.5) Identificadores presentes en lo ATESTIGUADO Y en la respuesta Y AUSENTES de la evidencia de la corrida — el
    MISMO mecanismo que parent_identifier_leak (ADR-0079). Lista ordenada; [] sin atestiguaciones."""
    if not attestations:
        return []
    att_ids = extract_identifiers(json.dumps(attestations, ensure_ascii=False, default=str))
    ans_ids = extract_identifiers(direct_answer or "")
    ev_ids = extract_identifiers(" ".join(str(i) for i in (evidence_ids or []))) | extract_identifiers(evidence_text)
    ev_ids |= {str(i).upper() for i in (evidence_ids or [])}
    return sorted((att_ids & ans_ids) - ev_ids)


def _attestation_leak_check(attestations, direct_answer, bundle):
    """(fragmento para deterministic_checks, extra_predicates) — predicado DURO attestation_identifier_leak (F.5):
    fuga no vacía → inadmisible. Tres estados: 'no-attestations' (nada atestiguado viajó) | 'checked'."""
    if not attestations:
        return ({"attestation_identifier_leak": [], "attestation_identifier_leak_state": "no-attestations",
                 "attestation_identifier_leak_rule": ATTESTATION_LEAK_RULE}, None)
    ev_text = json.dumps(_compact_evidence(bundle), ensure_ascii=False, default=str)
    leak = attestation_identifier_leak(attestations, direct_answer, _evidence_ids(bundle), ev_text)
    frag = {"attestation_identifier_leak": leak, "attestation_identifier_leak_state": "checked",
            "attestation_identifier_leak_rule": ATTESTATION_LEAK_RULE}
    return frag, [lambda _obj, _report: ("attestation_identifier_leak", not leak)]


def _council_initial_state(enabled, council_json, ledger):
    """(state, state_reason) ANTES de la ronda 2 (G.1): kill-switch → disabled; sin copia → no-ledger; r1 applicable|
    incomplete + ledger approved → centinela pending-r2 (la ronda 2 decide); + skipped-by-human → 'skipped-by-human';
    r1 terminal sin aprobar ni saltar → no-ledger con razón; r1 queued|running → no-ledger con razón; not-requested (…) /
    disabled (…) / errored (…) / pre-adr-0082 → el literal tal cual (vocabulario C.8)."""
    if not enabled:
        return COUNCIL_STATE_DISABLED, "WITT_COUNCIL=0 at execution"
    if council_json is None:
        return COUNCIL_STATE_NO_LEDGER, "run without council copy (no plan_id, or plan/db without council round 1)"
    r1 = council_json.get("r1_state")
    if r1 in ("applicable", "incomplete"):
        st = (ledger or {}).get("state") if isinstance(ledger, dict) else None
        if st == "approved":
            return COUNCIL_STATE_PENDING_R2, None
        if st == "skipped-by-human":
            return "skipped-by-human", (ledger or {}).get("skip_reason")
        return COUNCIL_STATE_NO_LEDGER, f"round 1 {r1} but ledger {st or 'absent'} (neither approved nor skipped)"
    if r1 in ("queued", "running"):
        return COUNCIL_STATE_NO_LEDGER, f"round 1 {r1} at execution (no ledger yet)"
    if isinstance(r1, str) and council.council_state_in_vocabulary(r1):
        return r1, None
    return f"errored (r1_state {r1!r} off-vocabulary)", None


def council_run_gate(council_state, ledger=None, enabled=None):
    """(F.3) El predicado de la PUERTA antes de encolar — la capa HTTP (app.py, C6) emite los 409: {allowed, reason ∈
    null | 'council_round1_pending' | 'council_ledger_unapproved', council_state, kill_switch}. queued|running →
    round1_pending; applicable|incomplete sin ledger approved ni skipped-by-human → ledger_unapproved; errored (…) /
    not-requested (…) / disabled (…) / pre-adr-0082 / skipped-by-human NO bloquean; WITT_COUNCIL=0 → nunca bloquea (L.2)."""
    if enabled is None:
        enabled = council.enabled()[0]
    out = {"allowed": True, "reason": None, "council_state": council_state, "kill_switch": not enabled}
    if not enabled:
        return out
    if council_state in ("queued", "running"):
        return {**out, "allowed": False, "reason": "council_round1_pending"}
    if council_state in ("applicable", "incomplete"):
        st = ledger.get("state") if isinstance(ledger, dict) else None
        if st not in ("approved", "skipped-by-human"):
            return {**out, "allowed": False, "reason": "council_ledger_unapproved"}
    return out


def _council_r1_view(council_json):
    """La ronda 1 COPIADA de runs.council_json.r1 para frozen.council.rounds[0] (+copied_from_plan_id): rounds[0] del
    plan cuando el worker (C4) la escribió; si no, un resumen desde el agregado {n_valid, n_members, usage, state,
    aggregation_sha, prior_observations}. None sin ronda 1. Lectura tolerante — nada se rellena."""
    cj = council_json if isinstance(council_json, dict) else {}
    r1 = cj.get("r1") if isinstance(cj.get("r1"), dict) else None
    if r1 is None:
        return None
    rounds = r1.get("rounds") if isinstance(r1.get("rounds"), list) else []
    base = dict(rounds[0]) if rounds and isinstance(rounds[0], dict) else {}
    view = {"round": "r1", "kind": "requirements", "phase": "plan", **base}
    view["copied_from_plan_id"] = cj.get("plan_id")
    view.setdefault("state", r1.get("state") or cj.get("r1_state"))
    view.setdefault("n_members", r1.get("n_members") or cj.get("n_members"))
    view.setdefault("n_valid", r1.get("n_valid"))
    if "usage" not in view and isinstance(r1.get("usage"), dict):
        view["usage"] = r1["usage"]
    view.setdefault("aggregation_sha", r1.get("aggregation_sha"))
    if "prior_observations" not in view and isinstance(r1.get("prior_observations"), dict):
        view["prior_observations"] = r1["prior_observations"]
    view["source"] = "plans.council_json (round 1 ran as the plan's job, BEFORE enqueue — copied, not re-measured)"
    return view


def _council_r1_usage_holder(council_json):
    """El insumo de by_stage.council_r1 (H): {usage, model, model_source, n_members, n_valid, n_calls} desde la ronda 1
    copiada. usage None = la ronda no midió (o el plan no la trae) — declarado, jamás 0."""
    v = _council_r1_view(council_json)
    if v is None:
        return None
    model = v.get("model") if isinstance(v.get("model"), dict) else {}
    return {"usage": v.get("usage") if isinstance(v.get("usage"), dict) else None,
            "model": model.get("requested") if model else (v.get("model") if isinstance(v.get("model"), str) else None),
            "model_source": model.get("source") if model else None,
            "n_members": v.get("n_members"), "n_valid": v.get("n_valid"),
            "n_calls": sum(int(m.get("attempts") or 0) for m in (v.get("members") or []) if isinstance(m, dict)) or None}


def _items_for_after_search(bundle, search_plan):
    """Los ítems que ENTRARON a la corrida (bundle.path_b.papers) con su atribución a directivas para
    council.coverage_after_search (C.7) — ver AFTER_SEARCH_ITEMS_RULE. Cada ítem declara `directive_attribution`."""
    papers = ((bundle.get("path_b") or {}).get("papers") or []) if isinstance(bundle, dict) else []
    queries = (search_plan or {}).get("queries") or {}
    items = []
    for p in papers:
        if not isinstance(p, dict):
            continue
        fam = p.get("source_family") or p.get("source")
        q = queries.get(fam) if isinstance(queries, dict) else None
        q = q or {}
        if "directive_requirement_ids" in p:
            rids, attr = list(p.get("directive_requirement_ids") or []), "item (harness normalize_item)"
        elif q.get("entered_by") == "directive":
            rids, attr = list(q.get("directive_requirement_ids") or []), "family-entry (entered_by directive)"
        else:
            rids, attr = [], "not-attributable (paper item without directive_requirement_ids)"
        items.append({"evidence_id": p.get("evidence_id"), "source_family": fam, "round": p.get("round"),
                      "directive_requirement_ids": rids, "directive_attribution": attr})
    return items


def _post_search_rows(r2, r3):
    """(filas para judge_coverage post-búsqueda, miembros re-juzgados) — POST_SEARCH_MERGE_RULE."""
    r3_ok = {m.get("agent") for m in ((r3 or {}).get("members") or []) if m.get("status") == "ok"}
    rows = [m for m in ((r2 or {}).get("members") or []) if m.get("agent") not in r3_ok]
    rows += [m for m in ((r3 or {}).get("members") or []) if m.get("status") == "ok"]
    return rows, sorted(a for a in r3_ok if a)


def _frozen_ledger_view(ledger, cap=COUNCIL_LEDGER_FROZEN_TEXT_CAP, images=None):
    """frozen.council.ledger (J): decisiones humanas + knowledge_now ATESTIGUADOS con el texto RECORTADO a `cap` y
    `truncated` declarado (íntegros en plans.council_ledger_json). None sin ledger.
    ADR-0086 (J.4): `images` = las filas SELLADAS por este ledger → `images[]` (attestations.ledger_item: metadatos y
    procedencia, jamás bytes) + `n_images`. Sin imágenes la llave NO nace: un ledger de 1.13 sigue byte a byte (M.1)."""
    if not isinstance(ledger, dict):
        return None
    reqs = []
    keep = ("requirement_id", "gap", "evidence_kind", "source_family", "query_en", "variants", "entities",
            "entities_resolved", "entities_unresolved", "acceptance_test", "priority", "requested_by", "n_requested_by",
            "n_members", "hard_rule_gate", "exploratory", "from_operative", "harness_state", "decision", "decided_by",
            "decided_at")
    for r in ledger.get("requirements") or []:
        q = {k: r.get(k) for k in keep}
        if "priority_downgraded_from" in r:
            q["priority_downgraded_from"] = r["priority_downgraded_from"]
        if r.get("decision_reason") is not None:
            q["decision_reason"] = r["decision_reason"]
        if r.get("attested_text") is not None:
            t = str(r["attested_text"])
            q.update(attested_text=t[:cap], attested_text_truncated=len(t) > cap, attested_chars=len(t),
                     attested_class="attested")
        reqs.append(q)
    kn = ledger.get("knowledge_now")
    if isinstance(kn, dict) and str(kn.get("text") or "").strip():
        t = str(kn["text"])
        kn_view = {"present": True, "text": t[:cap], "chars": kn.get("chars") if isinstance(kn.get("chars"), int) else len(t),
                   "truncated": bool(len(t) > cap or kn.get("truncated")), "by": kn.get("by"), "at": kn.get("at"),
                   "class": "attested"}
    else:
        kn_view = {"present": False, "text": None, "chars": 0, "truncated": False}
    return {"plan_id": ledger.get("plan_id"), "state": ledger.get("state"),
            "approved_by": ledger.get("approved_by"), "approved_by_is_author": ledger.get("approved_by_is_author"),
            "approved_at": ledger.get("approved_at"), "skipped_by": ledger.get("skipped_by"),
            "skip_reason": ledger.get("skip_reason"), "knowledge_now": kn_view,
            "n_requirements": ledger.get("n_requirements"), "n_kept": ledger.get("n_kept"),
            "n_discarded": ledger.get("n_discarded"), "n_attested": ledger.get("n_attested"),
            "n_pending": ledger.get("n_pending"), "n_hard_rule": ledger.get("n_hard_rule"),
            "truncated": ledger.get("truncated"), "n_truncated": ledger.get("n_truncated"),
            "requirements": reqs, "flags": list(ledger.get("flags") or []),
            **_attested_ledger_images(images),
            "requirements_source": ledger.get("requirements_source"),
            "decisions_without_requirement": list(ledger.get("decisions_without_requirement") or []),
            "text_cap_chars": cap,
            "source": ("plans.council_ledger_json copied at enqueue (runs.council_json.ledger); attested text ≤ "
                       f"{cap} chars here, full text lives in plans")}


def _council_cache_view(cfg, rounds):
    """frozen.council.cache (J): {enabled, ttl, ttl_shared, min_cacheable_tokens, r1|r2|r3 {creation, read} | null,
    hit_ratio_r2, hit_ratio_rule, class 'medicion'} — tokens MEDIDOS (API usage.cache_*), nunca supuestos."""
    cache_cfg = (cfg or {}).get("cache") or {}
    out = {"enabled": cache_cfg.get("enabled"), "ttl": cache_cfg.get("ttl_card"), "ttl_shared": cache_cfg.get("ttl_shared"),
           "min_cacheable_tokens": cache_cfg.get("min_cacheable_tokens", council.MIN_CACHEABLE_TOKENS),
           "r1": None, "r2": None, "r3": None, "hit_ratio_r2": None, "hit_ratio_rule": COUNCIL_CACHE_HIT_RATIO_RULE,
           "class": "medicion"}
    for rr in rounds or []:
        if not isinstance(rr, dict) or rr.get("round") not in ("r1", "r2", "r3"):
            continue
        u = _council_round_usage(rr.get("usage"))
        if u is None:
            continue
        out[rr["round"]] = {"creation": u["cache_creation"], "read": u["cache_read"]}
    r2 = out.get("r2")
    if r2 and (r2["creation"] or r2["read"]):
        out["hit_ratio_r2"] = round(r2["read"] / float(r2["read"] + r2["creation"]), 4)
    return out


def _council_index_block(council_json):
    """frozen.council.index (J): council_index.frozen_index_block(prior) sobre las prior observations que la ronda 1
    copió (rounds[0].prior_observations {n, kinds, state}); sin módulo o sin ronda 1 → estado declarado."""
    v = _council_r1_view(council_json) or {}
    prior = v.get("prior_observations") if isinstance(v.get("prior_observations"), dict) else None
    try:
        import council_index   # C7 — import perezoso (importa db); su ausencia se declara
    except ImportError:
        return {"index_version": None, "state": "not-available (council_index not in tree — C7 pending)",
                "prior_observations_n": (prior or {}).get("n"), "scorer": None, "origins_included": None,
                "kinds_included": list((prior or {}).get("kinds") or [])}
    if prior is None:
        blk = council_index.frozen_index_block({})
        blk["state"] = "not-available (round 1 without prior_observations)" if v else "not-available (no council round 1)"
        return blk
    return council_index.frozen_index_block(prior)


def _council_checks_summary(state, cov_pre, cov_post, directives, ledger):
    """deterministic_checks.council (G.6): conteos con clase para el panel — jamás prosa del consejo."""
    n_hall = 0
    for cov in (cov_pre, cov_post):
        if isinstance(cov, dict):
            n_hall += int(cov.get("n_hallucinated_votes") or 0)
    return {"state": state,
            "must_uncovered_pre": cov_pre.get("must_uncovered") if isinstance(cov_pre, dict) else None,
            "must_uncovered_post": cov_post.get("must_uncovered") if isinstance(cov_post, dict) else None,
            "n_hallucinated_votes": n_hall if (cov_pre is not None or cov_post is not None) else None,
            "n_directives": directives.get("n") if isinstance(directives, dict) else None,
            "n_requirements_kept": ledger.get("n_kept") if isinstance(ledger, dict) else None,
            "class": council.COVERAGE_CLASS, "rule": COUNCIL_CHECKS_RULE}


def execute_run(run, synthesizer=None, panel_caller=None, council_caller=None):
    """Execute one claimed run end-to-end. Deterministic under injected synthesizer/panel_caller (the
    offline gate); live otherwise. Never raises — every exit is a recorded terminal state + event.

    ADR-0081: los roles se resuelven EN LA LLAMADA (models.snapshot: tabla + env, con fuente), el snapshot va a la
    bitácora de configuración (config_ledger.observe — nunca frena) y al evento stage.models (PRIMER evento de etapa:
    qué va a correr ANTES de gastar); frozen.models (models.provenance_block) mide requested vs reported por pasada.

    ADR-0080: tras pass1 → stage.confidence.elicit{pass:1} → stage.deterministic_gate{pass:1} (adelantado) →
    stage.competence (competence.evaluate, decidido por código). Competente → pass1 es la candidata, sin ronda
    extra, fallback.trigger null. No competente (o kill-switch con `pass1 < tau`) → stage.search.plan + Ruta B
    por el harness (C2) → pass2 → elicit{pass:2} → gate{pass:2}. Estructural → trigger 'structural' como hoy.

    ADR-0082 (G.1): stage.models → stage.plan{council_state} → stage.council.ledger → thread_context → retrieve → pass1 →
    elicit → gate{pass1} → council r2 (stage.council.round/member/progress + coverage{pre-search}, cobertura sobre
    _compact_evidence(include_path_b=True)) → competence.evaluate(council_coverage=…) → [no competente] stage.council.
    directives → _build_search_plan(directives) → Ruta B → council r3 (sólo dueños de must sin cubrir, si el harness
    admitió algo) → coverage{post-search} → pass2 → gate → panel → revisión. `council_caller(request) -> (tool_input,
    usage, meta)` inyectable (default council.default_caller = la API real); el sintetizador es CIEGO al consejo (E5):
    sólo recibe `human_attestations` (aporto + knowledge_now) como llave hermana. WITT_COUNCIL=0 → cero llamadas y
    cero eventos stage.council.* (L.2); una cancelación a media ronda persiste lo gastado (LOTE-01·A4)."""
    run_id = run["run_id"]
    synthesizer = synthesizer or _default_synthesizer

    def _check_cancel():
        if db.cancel_requested(run_id):
            raise RunCancelled()

    def _on_stage(name, payload):
        if name == "web.locate":
            # ADR-0084 (C.6/G.6): UN latido por consulta ENVIADA del localizador (search_harness._run_web_family → ctx['on_web_locate']
            # → answer_pipeline._stage('web.locate')): ids y hosts, jamás URLs ni títulos; 0 eventos bajo off. El tipo va como
            # LITERAL y con su agent propio — el gate de paridad de la webapp (superficie (C) ETAPAS) lee esta forma.
            db.add_event(run_id, "stage.web.locate", payload=payload, agent=WEB_LOCATOR_AGENT)
            _check_cancel()
            return
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
    # ADR-0083 (M.4): la configuración de figuras se lee EN LA LLAMADA; el holder del bloque viaja a _usage_now (failed/cancelled)
    # ADR-0086 (K): configuración, almacén y FILAS de las imágenes atestiguadas — leídas EN LA LLAMADA
    att_cfg, att_storage, att_probe = _attested_cfg()
    att_rows, att_state = [], ATTESTED_NO_LEDGER_STATE   # se resuelven con la copia del consejo (abajo): ahí vive el plan_id
    att_holder = {"block": None, "selections": []}
    fig_cfg = figures.env_config()
    fig_enabled = bool(fig_cfg["figures"])
    fig_cache_root = figures.cache_dir()[0]
    fig_lenses, fig_lenses_src = _figures_vision_lenses(fig_cfg)
    figures_holder = {"summary": None}
    # ADR-0084 (M.4): la disponibilidad del localizador web se lee EN LA CORRIDA (una vez aquí; el plan/compilación/despacho la
    # releen en su llamada); el holder del bloque congelado viaja a _usage_now (failed/cancelled: lo gastado sobrevive)
    web_ps = _web_provider_state()
    web_holder = {"frozen": None}
    # (H) reenvío MEDIDO: cada intento de cada lente con visión reenvía las imágenes — se cuenta desde lo ENTREGADO al caller
    vision_sent = {"n_panels": 0, "n_attempts_with_images": 0, "bytes_b64_sent_total": 0,
                   "visual_tokens_projected_total": 0, "tokens_state": "projected", "rule": VISION_SENT_RULE}
    panel_selections = []

    def panel_caller(member, system, user_text):   # noqa: F811 — envuelve al inyectado
        key = (member.get("reviewer"), member.get("lens"))
        judge_attempts[key] = judge_attempts.get(key, 0) + 1
        # composite_auditor (E) entrega `attempt` en el member; si un caller viejo no lo trae, se cuenta aquí
        attempt = member.get("attempt") if isinstance(member.get("attempt"), int) else judge_attempts[key]
        # ADR-0083 (G.2/H/L): lo que ESTA llamada lleva en imágenes — medido del member (composite_auditor las pone SÓLO en
        # las lentes con visión, F3); la b64 jamás sale de aquí (sólo conteo, sha y bytes)
        figs_sent = [f for f in (member.get("figures") or []) if isinstance(f, dict)] if isinstance(member.get("figures"), list) else []
        if figs_sent:
            vision_sent["n_attempts_with_images"] += 1
            vision_sent["bytes_b64_sent_total"] += sum(len(f.get("b64") or "") for f in figs_sent)
            _det = _openai_detail_for(member.get("reviewer"), fig_cfg.get("openai_detail"))   # corrector: misma cifra que saw_figures
            for f in figs_sent:
                t = _vision_tokens(member.get("reviewer"), f.get("dims_measured"), _det)
                if t["state"] == "projected" and vision_sent["visual_tokens_projected_total"] is not None:
                    vision_sent["visual_tokens_projected_total"] += t["tokens"]
                elif t["state"] != "projected":
                    vision_sent["visual_tokens_projected_total"] = None
                    vision_sent["tokens_state"] = t["state"]
        db.add_event(run_id, "stage.audit.judge", agent="composite-auditor",
                     payload={"reviewer": member.get("reviewer"), "lens": member.get("lens"),
                              "phase": "start", "heartbeat": True,
                              "attempt": attempt, "retries_judge": max(0, attempt - 1),
                              "max_attempts": judge_max_attempts, "max_attempts_source": judge_retries_src,
                              # ADR-0081 (B): la Traza dice "intento N de M · <api> · <family>"
                              **_judge_identity(member),
                              # ADR-0083 (L): "+ N imágenes" en la Traza; 0 y [] medidos cuando no viajó ninguna
                              "figures_sent": len(figs_sent),
                              "figures_sha256": [f.get("sha256") for f in figs_sent]})
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
    # ADR-0082 (H / LOTE-01·A4): el holder del consejo — las rondas YA recogidas (r2/r3 medidas, r1 copiada del plan)
    # sobreviven en usage_json cuando la corrida muere o se cancela a media ronda (council.run_round adjunta el
    # RoundResult PARCIAL a la excepción y aquí se recoge ANTES de relanzar).
    council_holder = {"present": False, "enabled": True, "state": None, "r1": None, "r1_state": None, "plan_id": None,
                      "rounds": [], "not_run": {}, "model": None, "model_source": None, "cache_ttl": None}

    def _usage_now():
        return _token_usage(passes, {"panel": panel_rows_all},
                            max(0, _embed_usage_snapshot() - embed_t0),
                            plan=plan_holder.get("plan"), council=council_holder,
                            figures=_figures_usage_ctx(fig_enabled, figures_holder["summary"], fig_cfg),
                            web=_web_usage_ctx(web_holder["frozen"]))

    def _council_event(etype, payload):
        """TODOS los eventos stage.council.* salen del HILO ORQUESTADOR (council.run_round los emite al recoger
        futures; Context 6: db.add_event no es reentrante) con agent 'council'."""
        db.add_event(run_id, etype, payload=payload, agent=COUNCIL_AGENT)

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
        # 0a') ADR-0082 (F.4/G.1): la copia SERVER-SIDE del consejo (runs.council_json: r1 + ledger + membresía y N
        # CONGELADAS) y el estado inicial del consejo en esta corrida. Kill-switch WITT_COUNCIL=0 → cero llamadas, cero
        # eventos stage.council.*, componente 'kill-switch …' (L.2). Sin copia → 'not-applicable (no-ledger)'.
        council_enabled, council_enabled_src = council.enabled()
        cj = _council_json_of(run)
        c_members, c_n, c_membership_src, c_full = _council_members_frozen(cj)
        c_ledger = council_ledger_from(cj) if council_enabled else None
        c_r1_state = (cj or {}).get("r1_state") if cj else None
        c_state, c_state_reason = _council_initial_state(council_enabled, cj, c_ledger)
        c_cfg = council.config()
        c_model = council.resolve_council_model(cfg=c_cfg)
        c_quorum_required = council.quorum_required(c_n, c_cfg["quorum"])
        # ADR-0086 (K): las filas ADJUNTAS del plan (la copia del consejo trae el plan_id) y lo que de ellas ve el
        # sintetizador y el consejo: caption + metadatos rotulados, nunca bytes.
        att_rows, att_state = _attested_rows_for_run((cj or {}).get("plan_id") if cj else None, att_cfg)
        c_attest = human_attestations_of(c_ledger, images=att_rows) if council_enabled else None
        c_catalog_plan = (cj or {}).get("catalog_sha") if cj else None
        council_holder.update(present=cj is not None, enabled=council_enabled, state=c_state,
                              model=c_model["model"], model_source=c_model["source"],
                              cache_ttl=c_cfg["cache"]["ttl_card"], r1=_council_r1_usage_holder(cj),
                              plan_id=(cj or {}).get("plan_id") if cj else None, r1_state=c_r1_state)
        att_holder["block"] = _attested_stage(att_rows, att_state, run_id, att_cfg, att_probe)
        if plan:
            db.add_event(run_id, "stage.plan", agent="planner",
                         payload=plan_event_payload(plan, council_state=c_r1_state))
            _check_cancel()
        if council_enabled and cj is not None:
            # G.1: stage.council.ledger — qué ledger respalda la corrida (decisiones humanas, "qué sabes ahora")
            db.add_event(run_id, "stage.council.ledger", agent=COUNCIL_AGENT, payload={
                "plan_id": (cj or {}).get("plan_id"), "r1_state": c_r1_state,
                "ledger_state": (c_ledger or {}).get("state"),
                # corrector ADR-0082 (J / gate F): el centinela interno pending-r2 JAMÁS se escribe en la traza — mientras la
                # ronda 2 decide, `state` es el estado de la ronda 1 (∈ vocabulario) y `r2_pending` lo declara
                "state": c_r1_state if c_state == COUNCIL_STATE_PENDING_R2 else c_state,
                "r2_pending": c_state == COUNCIL_STATE_PENDING_R2,
                "state_reason": c_state_reason,
                "n_requirements": (c_ledger or {}).get("n_requirements"), "n_keep": (c_ledger or {}).get("n_kept"),
                "n_discard": (c_ledger or {}).get("n_discarded"), "n_aporto": (c_ledger or {}).get("n_attested"),
                "n_pending": (c_ledger or {}).get("n_pending"), "n_hard_rule": (c_ledger or {}).get("n_hard_rule"),
                "knowledge_now_present": bool(c_attest and c_attest.get("knowledge_now")),
                "n_attestations": (c_attest or {}).get("n_attestations", 0),
                "catalog_sha": c_catalog_plan,
                "plan_catalog_matches_run": (c_catalog_plan == catalog_cards.CATALOG_SHA) if c_catalog_plan else None,
                "n_members": c_n, "membership_source": c_membership_src, "full_council": c_full,
                "membership_version": (cj or {}).get("membership_version") or council.MEMBERSHIP_VERSION})
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
        # corrector ADR-0082 (E5 / G.9 / K.i): el sintetizador recibe el snapshot SIN `council_summary` — la prosa del consejo
        # del padre (gap ≤200 escrito por los miembros, flags[].statement, coverage_final, decision) sólo la ven el planner
        # y la ronda 1 del turno N+1. La copia íntegra sigue en runs.thread_context_json (planner/r1) y en frozen.thread_context.
        synth_thread_snapshot = None
        if thread_snapshot is not None:
            synth_thread_snapshot = {k: v for k, v in thread_snapshot.items() if k != "council_summary"}
            thread_delivery["council_summary"] = {
                "present_in_snapshot": thread_snapshot.get("council_summary") is not None,
                "delivered_to_synthesizer": False,
                "delivered_to": ["planner (runs.plan_thread_context at POST /runs/plan)",
                                 "council round 1 of turn N+1 (council_jobs._inherited_criteria)"],
                "rule": COUNCIL_SUMMARY_SYNTH_RULE}
            _pa = thread_snapshot.get("previous_audit") if isinstance(thread_snapshot.get("previous_audit"), dict) else {}
            thread_delivery["prompt_components"] = ["user_text.thread_context (sibling of evidence) WITHOUT council_summary "
                                                    "(E5: synthesizer blind to the council — corrector ADR-0082)",
                                                    "synth_system: THREAD_ANTI_LEAK_CLAUSE",
                                                    *(["synth_system: THREAD_VISION_FINDINGS_CLAUSE (previous_audit.n_from_vision_lens > 0 — corrector ADR-0083 D.4)"]
                                                      if isinstance(_pa.get("n_from_vision_lens"), int) and _pa["n_from_vision_lens"] > 0 else []),
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

        attest_delivery = {"synthesizer": None, "panel": False, "council_rounds": c_attest is not None,
                           "present": c_attest is not None}

        def _synth(evidence, label):
            """Cada pasada recibe el snapshot como LLAVE HERMANA si existe; un stub con la firma vieja
            (question, evidence, pass_label) sigue válido y el registro declara que no lo recibió.
            ADR-0082 (F.5): idem para `human_attestations` (aporto + knowledge_now del ledger aprobado) — llave
            hermana, jamás dentro de evidence; el sintetizador sigue CIEGO al consejo (E5): ni criterios ni cobertura."""
            args = (run["question"], evidence, label)
            wanted = {}
            if thread_snapshot is not None:
                wanted["thread_context"] = synth_thread_snapshot     # corrector ADR-0082 (E5): sin council_summary
            if c_attest is not None:
                wanted["human_attestations"] = c_attest
            if not wanted:
                return synthesizer(*args)
            try:
                params = inspect.signature(synthesizer).parameters
                varkw = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
            except (TypeError, ValueError):
                params, varkw = {}, False
            kwargs = {k: v for k, v in wanted.items() if k in params or varkw}
            out = synthesizer(*args, **kwargs)
            if thread_snapshot is not None:
                delivered = "thread_context" in kwargs
                thread_delivery["synthesizer"] = delivered
                if not delivered:
                    thread_delivery["synthesizer_note"] = "synthesizer signature without thread_context — not delivered"
            if c_attest is not None:
                attest_delivery["synthesizer"] = "human_attestations" in kwargs
                if not attest_delivery["synthesizer"]:
                    attest_delivery["synthesizer_note"] = ("synthesizer signature without human_attestations — not "
                                                           "delivered (ADR-0082 F.5)")
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
        checks1 = _gate(pass1, bundle, thread_snapshot, run, pass_no="pass1", attestations=c_attest,
                        attested_items=(att_holder["block"] or {}).get("items"), attested_state=att_state,
                        figures_cfg=fig_cfg, figures_cache_root=fig_cache_root,
                        web_ledger=(bundle.get("path_b") or {}).get("web_locator"), web_ps=web_ps)
        db.add_event(run_id, "stage.deterministic_gate", tool="verify_output",
                     payload=_gate_event_payload(checks1), level="info" if checks1["admissible"] else "warning")
        _check_cancel()

        # 2c) ADR-0082 (G.1 / C.5): la RONDA 2 del consejo — cada miembro juzga la COBERTURA de SUS requisitos kept
        # sobre el bundle (DI + path_b si lo estructural ya disparó; evidence_view declarado) ANTES de la compuerta. El
        # sintetizador no ve nada de esto (E5). Cero llamadas bajo kill-switch / sin ledger aprobado / 0 kept.
        r2, cov_pre, c_directives = None, None, None
        c_rounds_skipped = []
        c_evidence_ids = _evidence_ids(bundle)
        if c_state == COUNCIL_STATE_PENDING_R2:
            kept = [r for r in c_ledger["requirements"] if council.is_kept(r)]
            if not kept:
                c_rounds_skipped.append({"round": "r2", "reason": "0 kept requirements (all discarded or attested) — "
                                                                   "nothing for the council to judge (0 calls)"})
                council_holder["not_run"]["r2"] = "0 kept requirements"
                c_state = "applicable"
                cov_pre = council.judge_coverage({"members": [], "round": "r2"}, c_ledger, c_evidence_ids,
                                                 phase="pre-search", round_="r2")
                cov_pre["round"] = "r2"
            else:
                ctx2 = {"question": run["question"],
                        "entities": [e for e in run["entities_csv"].split(",") if e],
                        "ledger": c_ledger,
                        "evidence_view": _compact_evidence(bundle, include_path_b=True),
                        "evidence_ids": c_evidence_ids,
                        "pass1": {"direct_answer": pass1.get("direct_answer"), "gap_flags": pass1.get("gap_flags", []),
                                  "absence_kind": pass1.get("absence_kind"),
                                  "citations": _citations_of(pass1)[0]},
                        "human_attestations": c_attest, "phase": "run"}
                try:
                    r2 = council.run_round(c_members, "r2", ctx2, caller=council_caller, on_event=_council_event,
                                           cancel_check=_check_cancel, cfg=c_cfg, cancel_exc=(RunCancelled,))
                except RunCancelled as e:
                    partial = getattr(e, "council_round_result", None)
                    if isinstance(partial, dict):
                        council_holder["rounds"].append(partial)   # LOTE-01·A4: lo gastado por los que SÍ terminaron
                    raise
                except Exception as e:   # §6 no-hang: una ronda caída es una fila 'errored (…)', la corrida sigue
                    c_state = f"errored ({type(e).__name__})"
                    c_state_reason = f"{type(e).__name__}: {str(e)[:200]}"
                    council_holder["not_run"]["r2"] = c_state
                    db.add_event(run_id, "stage.council.round", agent=COUNCIL_AGENT, level="error",
                                 payload={"round": "r2", "kind": "coverage", "phase": "run", "state": c_state,
                                          "error": c_state_reason, "n_members": c_n, "heartbeat": True})
                if r2 is not None:
                    council_holder["rounds"].append(r2)
                    c_state = r2["state"]
                    cov_pre = council.judge_coverage(r2, c_ledger, c_evidence_ids, phase="pre-search", round_="r2")
            council_holder["state"] = c_state
        if cov_pre is not None:
            # corrector ADR-0082 (C.3/C.5): el cuórum de r2 se mide sobre los ELEGIBLES (dueños de un requisito kept) — la fila
            # copia quorum.required / n_eligible de la ronda; quorum_required_full_membership = ceil(q·N) sobre la membresía.
            # Sin ronda (0 kept → vacua) no hay cuórum medido: null, no 0.
            cov_pre["round_summary"] = {"state": r2["state"] if r2 else "applicable",
                                        "n_valid": r2["n_valid"] if r2 else 0, "n_members": c_n,
                                        "n_eligible": r2["n_eligible"] if r2 else 0,
                                        "quorum_required": r2["quorum"]["required"] if r2 else None,
                                        "quorum_required_full_membership": c_quorum_required,
                                        "quorum_met": r2["quorum"]["met"] if r2 else None,
                                        "quorum_rule": council.QUORUM_SOURCE,
                                        "n_invoked": r2["n_invoked"] if r2 else 0}
            # C.6: las directivas se COMPILAN por código desde los requisitos sin cubrir (puro, sin costo); se USAN sólo
            # si la compuerta declara no competente (G.1) — directives_state lo dice
            c_directives = council.directives_from(cov_pre, c_ledger, members_order=c_members)
            db.add_event(run_id, "stage.council.coverage", agent=COUNCIL_AGENT, payload={
                "phase": "pre-search", "round": "r2", "evidence_view": cov_pre.get("evidence_view"),
                "must_total": cov_pre["must_total"], "must_uncovered": cov_pre["must_uncovered"],
                "must_partial": cov_pre["must_partial"], "must_not_judged": cov_pre["must_not_judged"],
                "must_covered": cov_pre["must_covered"], "must_attested": cov_pre["must_attested"],
                "must_discarded": cov_pre["must_discarded"], "must_unsatisfiable": cov_pre["must_unsatisfiable"],
                "n_hallucinated_votes": cov_pre["n_hallucinated_votes"], "n_valid_votes": cov_pre["n_valid_votes"],
                "n_foreign_votes": cov_pre["n_foreign_votes"], "n_requirements_kept": cov_pre["n_requirements_kept"],
                "n_directives": c_directives["n"], "directives_state": c_directives["state"],
                "round_state": cov_pre["round_summary"]["state"], "class": cov_pre["class"]})
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
        # ADR-0082 (G.2): el insumo del componente council_uncovered_must — None bajo kill-switch (competence lo lee de la
        # env, L.2); la cobertura JUZGADA (+ round {state, n_valid, quorum}) cuando r2 corrió; un {state} declarado si no
        if not council_enabled:
            council_input = None
        elif cov_pre is not None:
            council_input = dict(cov_pre)
            council_input["round"] = cov_pre["round_summary"]
            council_input["council_state"] = c_state
        else:
            council_input = {"state": c_state if c_state != COUNCIL_STATE_PENDING_R2 else COUNCIL_STATE_NO_LEDGER,
                             "council_state": c_state, "reason": c_state_reason}
        comp = competence.evaluate(conf1, checks1["admissible"], plan, structural_fired, cal_cov,
                                   council_coverage=council_input, tau=FALLBACK_CONF_TAU)
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
        dirs_for_plan = None            # ADR-0082 (G.3): las directivas compiladas que VIAJAN al harness (o None)
        c_directives_state = "not-run"  # ∈ council.DIRECTIVES_STATES — 'provided' | 'none (all must covered)' | 'not-run'
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
                # ADR-0082 (G.1/G.3): las directivas del consejo — compiladas por CÓDIGO desde los must kept sin cubrir
                # (C.6) — mueven la búsqueda: UNIÓN default ∪ directivas ('directives+default'; las familias
                # directive-only entran por directiva). Sin consejo (kill-switch, no-ledger) → directives=None: hoy.
                if c_directives is not None and trigger == "competence":
                    db.add_event(run_id, "stage.council.directives", agent=COUNCIL_AGENT, payload={
                        "n": c_directives["n"], "families": c_directives["families"],
                        "n_excluded": c_directives["n_excluded"], "excluded": c_directives["excluded"],
                        "state": c_directives["state"],
                        "requirement_ids": [d["requirement_id"] for d in c_directives["directives"]],
                        "decided_by": c_directives["decided_by"]})
                    dirs_for_plan = c_directives["directives"] or None
                    c_directives_state = c_directives["state"]
                # ADR-0080 (C): el plan de búsqueda (familias por default ∪ directivas del consejo, ADR-0082)
                search_plan, search_plan_state = _build_search_plan(run["question"], entities,
                                                                    pass1.get("search_query_en"), search_cfg,
                                                                    directives=dirs_for_plan)
                accepts = _path_b_bundle_accepts()
                harness_live = search_plan_state == "built" and {"search_plan", "on_stage"} <= accepts
                if dirs_for_plan and not harness_live:
                    c_directives_state = "not-run"   # compiladas, pero el harness no corre en vivo: no se despacharon
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
                                      "families_source": (search_plan.get("families_source") if dirs_for_plan
                                                          else search_cfg["families_source"]),
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
                existing_ids=[h["doc_id"] for h in bundle["path_a"]["hits"]],
                web_quota=_web_quota_fn())   # ADR-0084 (G.10): la cuota mensual (db.web_locator_reserve) por firma
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
        # ADR-0084 (G.2): frozen.web_locator se arma AQUÍ (tras la Ruta B: el bloque D.4 ya cerró located[] con admisión/selección/
        # fetch) y viaja al holder para _usage_now; el gate de pass2/revisión lee el MISMO ledger (bundle.path_b.web_locator)
        web_holder["frozen"] = _web_locator_frozen(bundle["path_b"], search_plan_state, harness_used, web_ps)

        # 3a') ADR-0083 (C): la etapa PROPIA `stage.figures` — tras la Ruta B (estructural dentro de retrieve o por la
        # compuerta), ANTES de la ronda 3 del consejo (O.3: el consejo ve la MISMA proyección sin bytes) y de pass2. Los papers
        # seleccionados ganan paper['figures'] (caption + sha + licencia por código); el sintetizador verá caption + metadatos por
        # _prompt_path_b (D.1), JAMÁS bytes. Sin Ruta B: 'no-path-b' y cero eventos; WITT_FIGURES=0: UN summary y el bundle de 1.11.
        figures_holder["summary"] = _figures_stage(bundle, run_id, cfg=fig_cfg, cache_root=fig_cache_root,
                                                   cancel_check=_check_cancel)
        _check_cancel()

        # 3b) ADR-0082 (C.7): re-cobertura ESTRUCTURAL (código, corre siempre que hubo cobertura pre) y la RONDA 3 de
        # MODELO (re-juicio) SÓLO si WITT_COUNCIL_RECOVERAGE=1 ∧ el harness admitió algo ∧ quedan must kept sin cubrir,
        # y SÓLO sobre los dueños de esos must (subconjunto). r3 es INFORMATIVA: jamás re-gatea ni abre otra ronda.
        after_search, r3, cov_post = None, None, None
        post_state = None
        n_admitted_total = bundle["search_ledger"].get("n_admitted_total") if harness_used else None
        if cov_pre is not None:
            items_as = _items_for_after_search(bundle, search_plan if harness_used else None)
            # ADR-0084 (F.4): el ledger web (bloque D.4) viaja a coverage_after_search para by_requirement[].web_locator — SÓLO en
            # requisitos de familia web; sin él la llave queda AUSENTE (no se inventan ceros). Por inspección de firma (W6 lo añadió).
            _cas_kw = {}
            try:
                if "web_locator" in inspect.signature(council.coverage_after_search).parameters and harness_used:
                    _cas_kw["web_locator"] = (bundle["path_b"] or {}).get("web_locator")
            except (TypeError, ValueError):
                pass
            after_search = council.coverage_after_search(
                cov_pre, ({"plan": search_plan or {}, "items": items_as} if trigger else None),
                directives=(c_directives or {}).get("directives"), **_cas_kw)
            after_search["items_rule"] = AFTER_SEARCH_ITEMS_RULE
            after_search["n_admitted_total"] = n_admitted_total
            after_search["n_items_considered"] = len(items_as) if trigger else 0
            bundle["search_ledger"]["n_items_for_directives"] = after_search.get("n_items_for_directives")
            if dirs_for_plan and harness_used:
                c_directives_state = c_directives["state"]
            if trigger is None:
                post_state = "not-run (search not triggered)"
            elif trigger == "structural":
                post_state = "not-run (structural search preceded r2; nothing admitted after r2)"
            elif not cov_pre.get("uncovered_must_ids"):
                post_state = "not-run (all must covered)"
            elif not c_cfg["recoverage"]:
                post_state = "not-run (kill-switch WITT_COUNCIL_RECOVERAGE=0)"
            elif not n_admitted_total:
                post_state = "not-run (nothing admitted)"
            else:
                r3_members = council.recoverage_members(cov_pre, c_ledger)
                ctx3 = {"question": run["question"],
                        "entities": [e for e in run["entities_csv"].split(",") if e],
                        "ledger": c_ledger,
                        "evidence_view": _compact_evidence(bundle, include_path_b=True),
                        "evidence_ids": _evidence_ids(bundle),
                        "pass1": {"direct_answer": pass1.get("direct_answer"), "gap_flags": pass1.get("gap_flags", []),
                                  "absence_kind": pass1.get("absence_kind"), "citations": _citations_of(pass1)[0]},
                        "human_attestations": c_attest, "phase": "run"}
                try:
                    r3 = council.run_round(r3_members, "r3", ctx3, caller=council_caller, on_event=_council_event,
                                           cancel_check=_check_cancel, cfg=c_cfg, cancel_exc=(RunCancelled,))
                except RunCancelled as e:
                    partial = getattr(e, "council_round_result", None)
                    if isinstance(partial, dict):
                        council_holder["rounds"].append(partial)
                    raise
                except Exception as e:
                    post_state = f"not-run (errored ({type(e).__name__}))"
                    db.add_event(run_id, "stage.council.round", agent=COUNCIL_AGENT, level="error",
                                 payload={"round": "r3", "kind": "recoverage", "phase": "run",
                                          "state": f"errored ({type(e).__name__})",   # corrector: vocabulario de RONDA
                                          "post_search_state": post_state,
                                          "error": f"{type(e).__name__}: {str(e)[:200]}",
                                          "n_members": len(r3_members), "heartbeat": True})
                if r3 is not None:
                    council_holder["rounds"].append(r3)
                    post_rows, rejudged = _post_search_rows(r2, r3)
                    cov_post = council.judge_coverage({"members": post_rows, "round": "r3"}, c_ledger,
                                                      _evidence_ids(bundle), phase="post-search", round_="r3")
                    cov_post["merge_rule"] = POST_SEARCH_MERGE_RULE
                    cov_post["rejudged_members"] = rejudged
                    cov_post["r3"] = {"state": r3["state"], "n_members": r3["n_members"], "n_invoked": r3["n_invoked"],
                                      "n_valid": r3["n_valid"], "members": list(r3_members)}
                    post_state = "judged"
                    db.add_event(run_id, "stage.council.coverage", agent=COUNCIL_AGENT, payload={
                        "phase": "post-search", "round": "r3", "evidence_view": cov_post.get("evidence_view"),
                        "must_total": cov_post["must_total"], "must_uncovered": cov_post["must_uncovered"],
                        "must_partial": cov_post["must_partial"], "must_not_judged": cov_post["must_not_judged"],
                        "must_covered": cov_post["must_covered"], "must_attested": cov_post["must_attested"],
                        "must_discarded": cov_post["must_discarded"], "must_unsatisfiable": cov_post["must_unsatisfiable"],
                        "n_hallucinated_votes": cov_post["n_hallucinated_votes"], "n_valid_votes": cov_post["n_valid_votes"],
                        "n_foreign_votes": cov_post["n_foreign_votes"], "n_requirements_kept": cov_post["n_requirements_kept"],
                        "n_directives": c_directives["n"] if c_directives else None, "rejudged_members": rejudged,
                        "round_state": r3["state"], "class": cov_post["class"]})
            if post_state != "judged":
                council_holder["not_run"]["r3"] = post_state[len("not-run ("):-1] if post_state.startswith("not-run (") else post_state
            _check_cancel()
        elif council_enabled and c_state != COUNCIL_STATE_DISABLED:
            council_holder["not_run"].setdefault("r3", f"no round 2 coverage (council {c_state})")
            council_holder["not_run"].setdefault("r2", f"council {c_state}")
        if c_directives is not None and c_directives["n"] == 0:
            c_directives_state = "none (all must covered)"
        bundle["fallback"] = {"trigger": trigger,
                              "fb_meta": {"pass1_confidence": conf1,
                                          "pass1_confidence_source": conf1_source,
                                          "tau": FALLBACK_CONF_TAU, "tau_source": FALLBACK_CONF_TAU_SOURCE,
                                          "structural_sufficient": not structural_fired,
                                          "absence_kind": pass1.get("absence_kind"),
                                          # ADR-0082 (J): qué hizo el consejo con la decisión de buscar
                                          "council": {"state": c_state,
                                                      "must_uncovered_pre": cov_pre.get("must_uncovered") if cov_pre else None,
                                                      "n_directives": c_directives["n"] if c_directives else None,
                                                      "directives_state": c_directives_state,
                                                      "families_from_directives": list((search_plan or {}).get("families_from_directives") or [])},
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
            # ADR-0084 (G.4): runs APILA por código los <= 2 strings de CONTEO del localizador (jamás URLs) en la pasada que vio la
            # Ruta B — la clase 'web-located-*' queda declarada donde el humano la lee; la URL vive en frozen.web_locator
            _stack_web_gap_flags(pass2, bundle)
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
            checks = _gate(answer, bundle, thread_snapshot, run, pass_no="pass2", attestations=c_attest,
                           attested_items=(att_holder["block"] or {}).get("items"), attested_state=att_state,
                           figures_cfg=fig_cfg, figures_cache_root=fig_cache_root,
                           web_ledger=(bundle.get("path_b") or {}).get("web_locator"), web_ps=web_ps)
            db.add_event(run_id, "stage.deterministic_gate", tool="verify_output",
                         payload=_gate_event_payload(checks), level="info" if checks["admissible"] else "warning")
        else:
            checks = dict(checks1)
        checks["pass1_admissible"] = checks1["admissible"]
        checks["competence_gate"] = competence.compact(comp)
        # ADR-0082 (G.6): al panel viajan CONTEOS con clase (deterministic_checks.council), jamás la prosa del consejo
        checks["council"] = _council_checks_summary(c_state, cov_pre, cov_post, c_directives, c_ledger)
        _check_cancel()

        # 6) composite audit — 100% of runs (ADR-0049), the terminal transition
        db.add_event(run_id, "stage.audit.start", agent="composite-auditor")
        # ADR-0083 (G.2): las imágenes viajan DENTRO del member de las dos lentes con visión (composite_auditor, F3) — aquí
        # se seleccionan por código (citadas por la respuesta primero; sha recalculado al leer) y la llamada es EXACTAMENTE
        # la de 1.11 bajo kill-switch o cuando la firma del árbol aún no acepta figures=/vision_lenses= (declarado).
        fig_kw = _figures_panel_kwargs(bundle, answer, fig_cfg, fig_cache_root, fig_lenses, fig_enabled,
                                       vision_sent, panel_selections)
        # ADR-0086 (K): las imágenes APORTADAS viajan aparte de las figuras, con su propio tope y el presupuesto b64
        # compartido (las figuras van primero). Sin filas adjuntas la llamada queda EXACTAMENTE como en 1.13.
        fig_kw.update(_attested_panel_kwargs(att_rows, att_cfg, att_storage, att_holder["selections"],
                                             sum(len(f.get("b64") or "") for f in (fig_kw.get("figures") or []))))
        audit_result = composite_auditor.audit(
            claim={"direct_answer": answer["direct_answer"],
                   "stated_confidence": answer.get("stated_confidence")},
            evidence=_compact_evidence(bundle), deterministic_checks=checks,
            required_because=bundle["decision_state"]["state"], caller=panel_caller, **fig_kw)
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
            # ADR-0083 (D.4, el lazo): con figuras encendidas cada hallazgo dice si vino de una lente que VIO imágenes y la
            # instrucción de la revisión cierra el lazo (una lectura de imagen es juicio, jamás dicta un número al sintetizador);
            # figure_readings JAMÁS entra a los hallazgos. Bajo kill-switch la revisión es la de 1.11 byte a byte.
            findings = _panel_findings(audit_result, figures_enabled=fig_enabled)
            db.add_event(run_id, "stage.revision.start", agent="composite-auditor",
                         payload={"n_findings": len(findings), "cap": REVISION_CAP,
                                  "n_from_vision_lens": sum(1 for f in findings if f.get("from_vision_lens"))},
                         level="warning")
            rev_evidence = {**_compact_evidence(bundle), "revision_input": {
                "previous_answer": {"direct_answer": answer["direct_answer"],
                                    "stated_confidence": answer.get("stated_confidence"),
                                    "gap_flags": answer.get("gap_flags", [])},
                "panel_findings": findings,
                "instruction": ("REVISE the previous answer to resolve the panel's findings USING ONLY "
                                "the evidence shown — fixing a finding never licenses new claims or new "
                                "identifiers; if a finding cannot be resolved from this evidence, say so "
                                "explicitly (honest-decline doctrine, ADR-0058)"
                                + ("; " + VISION_LENS_FINDINGS_CLAUSE if fig_enabled else ""))}}
            answer_rev = _synth(rev_evidence, "revision")
            _stack_web_gap_flags(answer_rev, bundle)   # ADR-0084 (G.4): idem en la revisión (sin duplicar los ya apilados)
            passes.append(("revision", answer_rev))
            conf_rev, conf_rev_source = _resolve_confidence(answer_rev)
            db.add_event(run_id, "stage.synthesize.revision", agent=answer_rev.get("model"),
                         payload={"stated_confidence": conf_rev, "confidence_source": conf_rev_source,
                                  "n_findings_input": len(findings)})
            _check_cancel()
            # ADR-0080: el MISMO gate (_gate) que corrió sobre pass1/pass2 — predicados de identificadores +
            # fuga del padre + positive_claim_requires_citations; conserva pass1_admissible y competence_gate.
            checks2 = _gate(answer_rev, bundle, thread_snapshot, run, pass_no="revision", attestations=c_attest,
                            attested_items=(att_holder["block"] or {}).get("items"), attested_state=att_state,
                            figures_cfg=fig_cfg, figures_cache_root=fig_cache_root,
                            web_ledger=(bundle.get("path_b") or {}).get("web_locator"), web_ps=web_ps)
            checks2["pass1_admissible"] = checks1["admissible"]
            checks2["competence_gate"] = competence.compact(comp)
            checks2["council"] = checks["council"]   # ADR-0082 (G.6): los mismos conteos (r3 no se repite en revisión)
            adm2 = checks2["admissible"]
            db.add_event(run_id, "stage.deterministic_gate", tool="verify_output",
                         payload=_gate_event_payload(checks2), level="info" if adm2 else "warning")
            _check_cancel()
            db.add_event(run_id, "stage.audit.start", agent="composite-auditor",
                         payload={"revision_round": 1})
            # ADR-0083 (H): el segundo panel REENVÍA las imágenes (la revisión pudo cambiar qué figuras cita → se reselecciona)
            fig_kw2 = _figures_panel_kwargs(bundle, answer_rev, fig_cfg, fig_cache_root, fig_lenses, fig_enabled,
                                            vision_sent, panel_selections)
            fig_kw2.update(_attested_panel_kwargs(att_rows, att_cfg, att_storage, att_holder["selections"],
                                                  sum(len(f.get("b64") or "") for f in (fig_kw2.get("figures") or []))))
            audit2 = composite_auditor.audit(
                claim={"direct_answer": answer_rev["direct_answer"],
                       "stated_confidence": answer_rev.get("stated_confidence")},
                evidence=_compact_evidence(bundle), deterministic_checks=checks2,
                required_because=bundle["decision_state"]["state"], caller=panel_caller, **fig_kw2)
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
        # ADR-0083 (L): el bloque de figuras se COMPLETA con lo que sólo la corrida sabe (citas de la respuesta FINAL, lentes que
        # vieron cada sha, reenvío medido, proyección de visión) ANTES del re-sellado de identidad del bundle (ADR-0044) — el
        # frozen.figures y el bundle.figures_ledger son el MISMO objeto. Nada bajo kill-switch.
        # ADR-0086 (K): el bloque se cierra con lo que el panel MIDIÓ (quién vio qué, cuántas lecturas) y emite su resumen
        if isinstance(att_holder["block"], dict) and att_holder["block"].get("items"):
            _attested_fill(att_holder["block"], panel_rows_all, att_holder["selections"], run_id)
        if fig_enabled and isinstance(figures_holder["summary"], dict):
            _figures_fill(figures_holder["summary"], answer, panel_rows_all, fig_cfg, fig_lenses, fig_lenses_src,
                          vision_sent, panel_selections)
        bundle = composite_auditor.apply_to_bundle(bundle, audit_result, _evidence_ids(bundle))

        # 7) frozen record (backend-persisted; the webapp only reads — ADR-0047 d.2).
        # El usage cuenta TODOS los paneles (con revisión hay dos — ADR-0067).
        embed_tokens = max(0, _embed_usage_snapshot() - embed_t0)
        council_holder["state"] = c_state
        # ADR-0084 (G.2): si la corrida no pasó por la Ruta B del harness (competente, estructural, legado) el bloque se arma aquí —
        # SIEMPRE presente en >= 1.13 (estado por disponibilidad y ruta; sin contadores: nada se midió)
        if web_holder["frozen"] is None:
            web_holder["frozen"] = _web_locator_frozen(bundle.get("path_b"), search_plan_state, harness_used, web_ps)
        web_frozen = web_holder["frozen"]
        token_usage = _token_usage(passes, {"panel": panel_rows_all}, embed_tokens, plan=plan, council=council_holder,
                                   attested=att_holder["block"],
                                   figures=_figures_usage_ctx(fig_enabled, figures_holder["summary"], fig_cfg),
                                   web=_web_usage_ctx(web_frozen))
        # ADR-0078 corrector: UNA sola sede de re-parseo. Si evidence_cited LLEGÓ como string (el wrapper
        # real lo guarda en evidence_cited_raw; un sintetizador stub puede dejarlo en evidence_cited),
        # _normalize_citations recibe ESE string y declara 'string-reparsed' | 'string-unparseable'; si
        # llegó lista, 'list'; si no vino, 'absent'. El registro ya no puede decir "llegó lista" junto a
        # un crudo string.
        citations, citations_schema, ev_raw = _citations_of(answer)
        # ADR-0080 (E/G): la ESCALERA de soporte por cita (unresolved → resolved → passage_delivered →
        # supported|unsupported), aditiva dentro de cada cita, jamás fundida en un solo bool; el resumen
        # cuenta por peldaño. El helper vive en verify_output (rebanada E); su ausencia se declara.
        # ADR-0082 (G.4): `pertinent` deja de ser gris — el mapa {evidence_id: [requirement_id]} sale SÓLO de votos VÁLIDOS
        # covered|partial de r2/r3 (post-búsqueda si hubo r3); sin ronda válida el literal lleva el estado del consejo
        if isinstance(cov_post, dict) and cov_post.get("state") == "judged":
            c_pert, c_pert_src = cov_post.get("pertinence") or {}, cov_post.get("pertinent_source")
        elif isinstance(cov_pre, dict) and cov_pre.get("state") == "judged" and cov_pre["round_summary"]["state"] == "applicable":
            c_pert, c_pert_src = cov_pre.get("pertinence") or {}, cov_pre.get("pertinent_source")
        else:
            c_pert, c_pert_src = None, None
        citations, citations_support_summary = _support_states(citations, bundle, audit_result,
                                                               council_pertinence=c_pert, council_state=c_state,
                                                               council_source=c_pert_src,
                                                               # ADR-0083 (E): figure_verification + figure_citations (no bajo kill-switch)
                                                               figures_block=figures_holder["summary"] if fig_enabled else None)
        # ADR-0084 (G.5): located_via por cita + n_located_via_web — SÓLO con el localizador disponible en la corrida (M.1: ausentes
        # bajo off explícito/derivado); la cita a un paper web-localizado se casa por la escalera (resolved_to) o por su id
        if web_ps.get("available"):
            citations, citations_support_summary = _web_citations_fill(citations, citations_support_summary, bundle)
        # --- ADR-0082 (J): frozen.council — el consejo congelado: estado, membresía y N congeladas, ledger atestiguado
        # (texto ≤600), rondas (r1 COPIADA del plan + r2/r3 medidas con miembros/usage/estados), cobertura pre/after/post,
        # directivas, índice, caché medida, vocabularios. decided_by 'code (council.aggregate_*)'.
        c_rounds_frozen = [r for r in (_council_r1_view(cj),) if r] + [r for r in council_holder["rounds"] if isinstance(r, dict)]
        frozen_council = {
            "state": c_state, "state_reason": c_state_reason,
            "module_version": council.MODULE_VERSION, "council_version": council.COUNCIL_VERSION,
            "membership_version": (cj or {}).get("membership_version") or council.MEMBERSHIP_VERSION,
            "membership_source": c_membership_src,
            "catalog_sha": catalog_cards.CATALOG_SHA, "catalog_state": catalog_cards.CATALOG_STATE,
            "plan_catalog_sha": c_catalog_plan,
            "plan_catalog_matches_run": (c_catalog_plan == catalog_cards.CATALOG_SHA) if c_catalog_plan else None,
            "rules_sha": council.RULES_SHA, "tools_sha": council.TOOLS_SHA, "shared_block_sha": council.SHARED_BLOCK_SHA,
            "model": {"requested": c_model["model"], "source": c_model["source"], "generation": c_model["generation"],
                      "effort": c_model["effort_sent"], "effort_source": c_model["effort_sent_source"],
                      "effort_pinned": c_model["effort"], "max_tokens": c_model["max_tokens"]},
            "full_council": c_full, "n_members": c_n, "members": list(c_members),
            "quorum_rule": council.QUORUM_SOURCE, "quorum_required": c_quorum_required,
            "plan_id": (cj or {}).get("plan_id") if cj else None, "r1_state": c_r1_state,
            "ledger": _frozen_ledger_view(c_ledger, images=att_rows),
            "human_attestations": ({"present": True, "n_attestations": c_attest["n_attestations"],
                                    "knowledge_now_present": c_attest["knowledge_now"] is not None,
                                    "delivery": attest_delivery, "class": "attested"} if c_attest
                                   else {"present": False, "n_attestations": 0, "knowledge_now_present": False,
                                         "delivery": attest_delivery}),
            "rounds": c_rounds_frozen,
            "rounds_skipped": c_rounds_skipped,
            "coverage": {"pre_search": cov_pre if cov_pre is not None else {
                             "state": f"not-run ({c_state_reason or c_state})"},
                         "after_search": after_search if after_search is not None else {
                             "state": "not-run (no round 2 coverage)"},
                         "post_search": cov_post if cov_post is not None else {
                             "state": post_state or f"not-run (no round 2 coverage: council {c_state})"}},
            "must_uncovered": cov_pre.get("must_uncovered") if isinstance(cov_pre, dict) else None,
            "must_uncovered_post": cov_post.get("must_uncovered") if isinstance(cov_post, dict) else None,
            "must_unsatisfiable": cov_pre.get("must_unsatisfiable") if isinstance(cov_pre, dict) else None,
            "directives": list((c_directives or {}).get("directives") or []),
            "directives_excluded": list((c_directives or {}).get("excluded") or []),
            "directives_state": c_directives_state,
            "directives_rule": (c_directives or {}).get("rule"),
            # corrector ADR-0084 (L): la regla de disponibilidad dinámica (F.2) viaja SÓLO cuando hubo recomputo (council la emite
            # sólo entonces) — directives_rule conserva el literal de 1.12 byte a byte en toda corrida
            **({"directives_availability_rule": c_directives["availability_rule"]}
               if isinstance(c_directives, dict) and c_directives.get("availability_rule") else {}),
            "r3": ({"state": "judged", "members": cov_post["r3"]["members"], "n_invoked": cov_post["r3"]["n_invoked"],
                    "n_valid": cov_post["r3"]["n_valid"], "round_state": cov_post["r3"]["state"]} if cov_post
                   else {"state": post_state or "not-run (no round 2 coverage)", "members": []}),
            "index": _council_index_block(cj),
            "cache": _council_cache_view(c_cfg, c_rounds_frozen),
            "usage": {r.get("round"): _council_round_usage(r.get("usage")) for r in c_rounds_frozen},
            "config": {"recoverage": c_cfg["recoverage"], "recoverage_source": c_cfg["recoverage_source"],
                       "concurrency": c_cfg["concurrency"], "member_timeout_s": c_cfg["member_timeout_s"],
                       "budget_s": c_cfg["budget_s"], "quorum": c_cfg["quorum"], "cg_component": c_cfg["cg_component"],
                       "r2_evidence_chars": c_cfg["r2_evidence_chars"]},
            "vocabulary": council_vocabulary_full(),
            "decided_by": COUNCIL_DECIDED_BY,
            "kill_switch": {"WITT_COUNCIL": os.environ.get("WITT_COUNCIL", ""), "enabled": council_enabled,
                            "source": council_enabled_src},
            "source": ("runs.council_json (F.4 copy at enqueue) + council.run_round/judge_coverage/directives_from/"
                       "coverage_after_search measured in this run"),
        }
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
            # ADR-0082 (M, C9): roles.council = stage.models.roles.council (mismo snapshot; igualdad medida en smoke).
            "models": models.provenance_block({"synthesizer": synth_role, "elicitation": elicit_role,
                                               "council": models_snapshot["roles"].get("council")}, passes,
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
            "agents_invoked": _agents_invoked(audit_result, checks, plan, council=frozen_council,
                                              attested=att_holder["block"],
                                              figures=figures_holder["summary"], figure_lenses=fig_lenses,
                                              web=web_frozen, web_ps=web_ps),
            # --- ADR-0082 (J): el consejo de criterio congelado (ver arriba) ------------------------------------
            "council": frozen_council,
            # --- ADR-0083 (L): las figuras OBSERVADAS congeladas — SIEMPRE presente en >= 1.12: state ∈ FIGURES_STATES, ítems
            # sin bytes (sha256 + source-pointer + licencia por código), vision (juicio, medido lo enviado, proyectado el
            # costo), vocabularios; bajo kill-switch {state, kill_switch} y la forma base (excepción declarada M.1) -----------
            "figures": figures_holder["summary"],
            # --- ADR-0084 (G.2): el LOCALIZADOR WEB congelado — SIEMPRE presente en >= 1.13: state ∈ web_locator.WEB_STATES_*, versiones,
            # tabla del resolutor, consultas verbatim, located[] (la URL hallada vive SÓLO aquí), unresolved[] (title_web rotulado),
            # gap_flags_typed[], cost (PROYECCIÓN), quota; bajo kill-switch EXACTAMENTE {state, provider, provider_source, kill_switch,
            # state_vocabulary, rule} (excepción declarada M.1); sin Ruta B por el harness, estado por disponibilidad y ruta ---------
            "web_locator": web_frozen,
            # --- ADR-0086 (L): las IMÁGENES ATESTIGUADAS congeladas — SIEMPRE presentes en >= 1.14: state ∈
            # attestations.ATTESTED_STATES_*, items[] SIN bytes (identidad, procedencia, consentimiento, licencia
            # declarada y qué lentes la vieron), delivery (el sintetizador NO vio píxeles), storage con su durabilidad,
            # vision (lecturas = JUICIO) y el vocabulario. Bajo kill-switch, EXACTAMENTE {state, …} sin ítems (M.1) ------
            "attested_images": att_holder["block"],
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
                             "panel_n_families_valid": audit_result.get("n_families_valid"),
                             # ADR-0082 (G.8): estado del consejo, k/N válidos de la ronda de cobertura (o de r1 copiada)
                             # y must sin cubrir (int | null: 0 medido ≠ null) — frozen-counter, la lista no re-deriva
                             "council_state": c_state,
                             "council_n_valid": (r2["n_valid"] if r2 else
                                                 ((_council_r1_view(cj) or {}).get("n_valid") if cj else None)),
                             # corrector ADR-0082 (G.8): UNA verdad — el N que congela frozen.council (null sin copia)
                             "council_n_members": frozen_council["n_members"],
                             "council_must_uncovered": frozen_council["must_uncovered"],
                             # ADR-0083 (L, vista): estado de las figuras y conteos MEDIDOS (0 = medido; null = kill-switch:
                             # nada se contó) — la Lista/Banco pinta 'N figuras verificadas · K citadas' sin re-derivar
                             # ADR-0086 (K): el estado de lo atestiguado y sus conteos viven también aquí (columna propia,
                             # FUERA del registro congelado) para la Lista y el Banco — existe aun con el localizador apagado
                             "attested_state": (att_holder["block"] or {}).get("state"),
                             "attested_n_images": (att_holder["block"] or {}).get("n_attached"),
                             "attested_n_seen_by_panel": (att_holder["block"] or {}).get("n_seen_by_panel"),
                             "figures_state": (figures_holder["summary"] or {}).get("state"),
                             "figures_n_verified": ((figures_holder["summary"] or {}).get("n_verified") if fig_enabled else None),
                             "figures_n_cited": ((figures_holder["summary"] or {}).get("n_cited") if fig_enabled else None),
                             # ADR-0084 (G.8): estado del localizador web y conteos MEDIDOS (0 = medido; null = no midió: kill-switch,
                             # tool-unavailable, sin directiva) — la Lista/Banco pinta 'web: N localizados · K sin resolver' sin re-derivar
                             "web_locator_state": (web_frozen or {}).get("state"),
                             "web_n_located": (web_frozen or {}).get("n_located"),
                             "web_n_unresolved": (web_frozen or {}).get("n_unresolved")}
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


def compose_council_json(prow, now_iso=None):
    """ADR-0082 (F.4) — la copia SERVER-SIDE que la corrida CONGELA al encolar, compuesta desde la fila del plan (jamás
    del cliente): {plan_id, r1_state, r1: plans.council_json | null, ledger: plans.council_ledger_json | null,
    membership_version, n_members, members[], full_council, catalog_sha (los cuatro tal como r1 los congeló: r2/r3 usan
    ESTA N, no la env vigente), membership_source, composed_at, source}. La MISMA forma que app._compose_run_council_json
    (C6) — app la compone cuando tiene la fila; runs la compone si sólo recibe plan_id (una verdad, dos puertas).
    Tres estados de plans.council_state: columna AUSENTE (BD sin migrar la superficie E.1) → 'not-requested (council db
    unavailable)'; NULL → 'pre-adr-0082'; valor → tal cual."""
    if not isinstance(prow, dict):
        return None

    def _json(s):
        if s is None:
            return None
        if isinstance(s, (dict, list)):
            return s
        try:
            return json.loads(s)
        except (TypeError, ValueError):
            return None
    if "council_state" not in prow:
        r1_state = "not-requested (council db unavailable)"
    else:
        r1_state = prow.get("council_state") or "pre-adr-0082"
    r1 = _json(prow.get("council_json"))
    r1d = r1 if isinstance(r1, dict) else {}
    return {"plan_id": prow.get("plan_id"), "r1_state": r1_state, "r1": r1, "ledger": _json(prow.get("council_ledger_json")),
            "membership_version": r1d.get("membership_version"), "n_members": r1d.get("n_members"),
            "members": r1d.get("members"), "full_council": r1d.get("full_council"),
            "catalog_sha": r1d.get("catalog_sha"),
            "membership_source": (COUNCIL_MEMBERSHIP_SOURCE_PLAN if r1d else "not-available (plan without council round 1)"),
            "composed_at": now_iso or db._now().isoformat(timespec="seconds"),
            "source": "plans.council_json + plans.council_ledger_json (copied at enqueue)"}


def new_run(user_id, question, entities=None, plan_json=None, parent_run_id=None, from_question_id=None,
            council_json=None, plan_id=None):
    """Encola una corrida. ADR-0079: la investigación se DERIVA aquí (derive_thread — servidor, jamás del
    cliente) y la procedencia también (run_origin). Con parent_run_id: ParentNotFound (404) /
    ParentNotTerminal (409) suben ANTES de insertar — la capa HTTP las traduce. `from_question_id` sólo
    siembra root_question_id de una RAÍZ (el sello mark_question_used sigue siendo de app.py). El plan:
    un plan_id se consume por UNA corrida (409 plan_already_used en app.py) — el hijo declara plan nuevo
    o el llamador copia plan_json; aquí sólo se persiste lo que llegue.

    ADR-0082 (F.4): `council_json` (str JSON o dict) = la copia server-side del consejo que app compone desde la fila
    del plan (compose_council_json); si NO llega y sí `plan_id`, se compone AQUÍ desde db.get_plan (misma función).
    Se persiste en runs.council_json (db.create_run(council_json=), columna E.1); run.state{queued}.council.persisted
    lo declara (False sólo cuando no hubo copia que persistir → la corrida ejecuta 'not-applicable (no-ledger)'). Jamás se
    acepta del cliente. La membresía y N viajan CONGELADOS dentro de la copia (r2/r3 no releen WITT_COUNCIL_FULL)."""
    from sqlalchemy.exc import IntegrityError
    run_id = uuid.uuid4().hex
    entities = list(entities or [])
    origin = run_origin()
    if council_json is None and plan_id:
        try:
            council_json = compose_council_json(db.get_plan(plan_id))
        except Exception:   # §6 no-hang: sin fila legible no hay copia — se declara, no se inventa
            council_json = None
    if isinstance(council_json, str):
        try:
            council_dict = json.loads(council_json)
        except ValueError:
            council_dict = None
    else:
        council_dict = council_json if isinstance(council_json, dict) else None
    council_str = (json.dumps(council_dict, ensure_ascii=False, default=str) if isinstance(council_dict, dict) else None)
    ultimo_error = None
    for _intento in range(5):
        thread = derive_thread(run_id, question, entities, parent_run_id=parent_run_id,
                               from_question_id=from_question_id)
        envelope = thread["envelope"]
        # corrector ADR-0079: la PROCEDENCIA completa ({value, source, raw?, truncated?}) se persiste al
        # encolar dentro del sobre — el registro congelado copia esta fuente en vez de re-derivarla.
        envelope["origin"] = origin
        try:
            # ADR-0082 (F.4): runs.council_json = la copia server-side (db.create_run(council_json=), columna de C4)
            db.create_run(run_id, user_id, question, entities, plan_json=plan_json,
                          parent_run_id=thread["parent_run_id"], thread_id=thread["thread_id"],
                          turn_no=thread["turn_no"], turn_kind=thread["turn_kind"],
                          thread_context_json=json.dumps(envelope, ensure_ascii=False, default=str),
                          origin=origin["value"], root_question_id=thread["root_question_id"],
                          council_json=council_str)
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
    # ADR-0082 (J): run.state{queued}.council {ledger_present, n_kept, n_hard_rule, r1_state, persisted} desde la copia
    c_ledger = council_ledger_from(council_dict) if isinstance(council_dict, dict) else None
    council_ev = None
    if isinstance(council_dict, dict):
        council_ev = {"ledger_present": c_ledger is not None,
                      "ledger_state": (c_ledger or {}).get("state"),
                      "n_kept": (c_ledger or {}).get("n_kept"), "n_hard_rule": (c_ledger or {}).get("n_hard_rule"),
                      "r1_state": council_dict.get("r1_state"), "plan_id": council_dict.get("plan_id"),
                      "n_members": council_dict.get("n_members"),
                      "persisted": council_str is not None}
    db.add_event(run_id, "run.state", payload={
        "state": "queued", "origin": origin, "run_no": row.get("run_no"),
        "thread": {"thread_id": thread["thread_id"], "turn_no": thread["turn_no"],
                   "root_run_no": root_run_no,
                   "turn_kind": thread["turn_kind"], "parent_run_id": thread["parent_run_id"],
                   "context": ("built" if envelope.get("snapshot") is not None else "skipped"),
                   "context_skipped_reason": envelope.get("skipped_reason"),
                   "context_bytes": snap.get("bytes"),
                   "n_comments_included": ((snap.get("human_comments") or {}).get("n_included"))},
        "council": council_ev})
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
    # ADR-0082 (E.2): los hilos council-worker-N del JOB de ronda 1 (council_jobs, C4) junto a los run-worker-N
    return start_council_workers()


def start_council_workers(n=None):
    """ADR-0082 (E.2/L): lanza council_jobs.start_council_workers(WITT_COUNCIL_WORKERS) — el worker propio de la ronda
    1 del plan (rag_index/query_service/council_jobs.py) — y devuelve un estado DECLARADO: 'started' (+ `council_jobs` =
    la declaración del arranque: hilos, reaper, siega, orígenes) | 'disabled (kill-switch WITT_COUNCIL=0)' |
    'not-started (WITT_COUNCIL_WORKERS=0)' | 'error: …'. Ningún fallo tumba el arranque (§6 no-hang); el número de hilos
    sale de models.env_value('WITT_COUNCIL_WORKERS') (tolerante, default 1)."""
    enabled, en_src = council.enabled()
    if n is None:
        try:
            n, n_src = models.env_value("WITT_COUNCIL_WORKERS")
        except Exception:
            n, n_src = council.env_config()["WITT_COUNCIL_WORKERS"]["value"], "council.env_config"
    else:
        n_src = "caller"
    state = {"workers": int(n or 0), "workers_source": n_src, "enabled": enabled, "enabled_source": en_src}
    if not enabled:
        state["state"] = COUNCIL_STATE_DISABLED
        print(f"[runs.council] council-worker: {state['state']} (sin hilos)", file=sys.stderr)
        return state
    if int(n or 0) <= 0:
        state["state"] = "not-started (WITT_COUNCIL_WORKERS=0)"
        print(f"[runs.council] council-worker: {state['state']}", file=sys.stderr)
        return state
    # import PEREZOSO dentro de la función (council_jobs no importa runs; boot_id() reutiliza WORKER_BOOT_ID vía
    # sys.modules) — ADR-0082 E.2, costura C4↔C5 cosida por C9. El reaper de planes es el hilo propio `council-reaper`
    # de council_jobs (reaper=True): runs._reap_once sigue segando SÓLO corridas (deviación declarada en el ADR).
    import council_jobs
    try:
        state["council_jobs"] = council_jobs.start_council_workers(int(n))
        state["state"] = "started"
        print(f"[runs.council] council-worker: {n} hilo(s) ({n_src}) — council_jobs.start_council_workers", file=sys.stderr)
    except Exception as e:
        state["state"] = f"error: {type(e).__name__}: {str(e)[:120]}"
        print(f"[runs.council] council-worker: {state['state']}", file=sys.stderr)
    return state


def stop_workers():
    _STOP.set()
    # ADR-0082 (E.2, C9): los hilos council-worker-N / council-reaper comparten el apagado (council_jobs._STOP)
    try:
        import council_jobs
        council_jobs.stop_council_workers()
    except Exception as e:   # §6 no-hang: apagar jamás lanza
        print(f"[runs.council] stop_council_workers: {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)

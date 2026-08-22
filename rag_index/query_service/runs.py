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
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import db  # noqa: E402
from lib import (agent_matrix, answer_pipeline, composite_auditor, reasoning_catalog,  # noqa: E402
                 resolve_id, verify_output)

RENDER_CONTRACT_VERSION = "1.5"   # ADR-0065 (escalar atrapado): confidence.source gana el literal
                                  # "stated-second-elicitation" (la elicitación dedicada es la medición
                                  # autoritativa del escalar) + confidence.pass1_inline/pass2_inline
                                  # (el instrumento in-line persiste — continuidad de la serie).
                                  # 1.4 = ADR-0061 (tapón 3): +plan (el plan declarado o null-declarado) y
                                  # agents_invoked poblado desde el juicio del planner cuando existe.
                                  # 1.3 = ADR-0060 (tapón 2): +reasoning {framework_applied (SELF-REPORT, con
                                  # sección y tier resueltos por tabla), structural_frameworks (derivados
                                  # del código)}, +agents_invoked (derivado, §11), +alternatives_considered.
                                  # 1.2 = ADR-0057 (confidence.source + path_b.query_sent). 1.1 = ADR-0051.
SYNTH_MODEL = "claude-opus-4-8"   # best-tier policy (2026-06-13 directive) — never downgraded to save cost

# tau (ADR-0051): pass-1 confidence below this triggers the Path B fallback — the model's own "is my
# store enough?" signal, the decider the eval harness recommends (run_held_out --conf-threshold 0.5)
# over the structural check the repo documents as fooled-by-any-chunk-present (run #1 confirmed it live).
FALLBACK_CONF_TAU = float(os.environ.get("WITT_FALLBACK_CONF_TAU", "0.5"))

SYNTH_TOOL = {
    "name": "emit_answer",
    "description": ("Answer the biology question using ONLY the provided evidence. If the evidence is "
                    "thin, say so in gap_flags and keep confidence honest. NEVER invent identifiers: "
                    "only assert gene IDs that appear in the evidence or the verified-store resolutions."),
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
    campos de texto largo — estructuralmente no hay string que contaminar. Devuelve (conf, subs, usage);
    valores fuera de [0,1] o no numéricos se rechazan a None (el caller cae al in-line, §6 no-hang)."""
    user_text = json.dumps({"question": question, "evidence": evidence,
                            "produced_answer": {"pass": pass_label, "direct_answer": direct_answer,
                                                "gap_flags": gap_flags}},
                           ensure_ascii=False, default=str)
    out, usage = composite_auditor._anthropic_tool_call(
        SYNTH_MODEL, ELICIT_SYSTEM, user_text, tool=CONF_TOOL, max_tokens=300)
    conf = out.get("confidence")
    conf = float(conf) if isinstance(conf, (int, float)) and 0 <= conf <= 1 else None
    subs = out.get("confidence_by_subclaim") or None
    return conf, subs, usage


# --- el planner (tapón 3, ADR-0061) --------------------------------------------------------------------
# El plan declarado del boceto M3: el checkpoint humano ANTES de gastar. Tres clases de contenido, cada
# una con su clase declarada, jamás mezcladas:
#   structural       — hechos del pipeline (Ruta A primero, B condicional, auditoría al 100%): del código.
#   model-judgment   — clasificación de work-type/nichos/agentes: juicio del modelo contra la matriz,
#                      con el gate level y la componentización resueltos por TABLA (agent_matrix).
#   projection       — costo/duración: mediana de la historia REAL, calculada por código (constitución:
#                      una proyección la calcula un tool desde insumos declarados, nunca la estima un
#                      modelo). Sin historia suficiente: "[?] sin historia suficiente" (LOTE-01).
PLAN_VERSION = "2"   # v2 (ADR-0063): +judgment.route — el juicio del planner ahora TIENE a dónde ir
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
        },
        "required": ["work_type", "route", "niches", "agents_applicable"],
    },
}


def _default_planner(question, entities):
    """One SMALL model call (SYNTH_MODEL, best-tier policy) that judges work-type/nichos/agentes contra
    la matriz. Inyectable en los gates. Devuelve (judgment_dict, usage)."""
    system = ("You are the §11 agent-invocation preflight of the Witt × Organogenesis webapp: classify "
              "the incoming question BEFORE the pipeline runs. Judge strictly against the matrix and "
              "niches below; do NOT answer the question itself.\n\n" + agent_matrix.digest())
    user_text = json.dumps({"question": question, "entities": entities or []}, ensure_ascii=False)
    return composite_auditor._anthropic_tool_call(SYNTH_MODEL, system, user_text,
                                                  tool=PLAN_TOOL, max_tokens=1200)


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


def build_plan(question, entities=None, planner=None, history_rows=None):
    """El plan completo. El juicio del modelo puede FALLAR sin tumbar nada (§6 no-hang): un plan con
    judgment.state=errored sigue siendo un plan — declara que el juicio no se pudo hacer, que es
    distinto de no haberlo intentado."""
    planner = planner or _default_planner
    entities = [e for e in (entities or []) if e and e.strip()]

    plan = {
        "plan_version": PLAN_VERSION,
        "matrix": f"{agent_matrix.MATRIX_PATH} {agent_matrix.MATRIX_VERSION}",
        "question": question, "entities": entities,
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
        "audit": {"class": "structural", "required": True,
                  "panel": [f"{m['reviewer']} ({m['lens']})" for m in composite_auditor.DEFAULT_PANEL],
                  "note": "obligatorio en el 100% de las corridas (ADR-0049) — la mayor parte del costo"},
        "deterministic_gate": {"class": "structural", "component": "lib/verify_output.py",
                               "note": "clase Logic-LM, no es un LLM; corre en cada corrida"},
    }

    try:
        out, usage = planner(question, entities)
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
            "planner": {"model": SYNTH_MODEL, "usage": usage, "class": "self-report",
                        "note": "juicio de prompt-time (misma advertencia §5 que framework_applied)"},
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
                               f"tally:{json.dumps(audit_result.get('tally', {}), sort_keys=True)}"],
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


class RunCancelled(Exception):
    pass


def _compact_evidence(bundle, include_path_b=True):
    """The evidence view handed to the synthesizer and the panel — compact, never the raw 100K bundle.
    include_path_b=False is the PASS-1 view (DI-only): pass-1 confidence measures 'is my store enough?'
    even when structural insufficiency already fetched external papers (ADR-0051)."""
    ev = {
        "path_a_hits": [{"doc_id": h["doc_id"], "type": h["type"], "score": h["score"], "text": h["text"]}
                        for h in bundle["path_a"]["hits"]],
        "retrieval": bundle["path_a"]["retrieval"],
        "entities_checked": bundle["entities_checked"],
        "sufficiency": bundle["sufficiency"],
    }
    if include_path_b:
        ev["path_b"] = {k: v for k, v in bundle["path_b"].items() if k != "tool_universe_directive"}
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


def synth_system(pass_label):
    """The EXACT production system prompt of a synthesis pass — factored out so diagnostics
    (evaluation/scripts/ab_trapped_scalar.py) measure against the real string, never a replica."""
    return ("You answer zebrafish pronephros research questions for a medical team, from a curated "
            "evidence bundle (DATA INAMOVIBLE"
            + ("" if pass_label == "pass1" else " + externally fetched literature") + "). "
            "Use ONLY the provided evidence. Be direct; keep confidence honest (thin evidence means "
            "LOW confidence + explicit gap_flags); when sub-claims have asymmetric evidence strength, "
            "report confidence_by_subclaim instead of averaging. If your answer rests on an absence, "
            "declare absence_kind precisely. Technical identifiers stay in English; never assert an "
            "identifier that is not in the evidence.\n\n"
            # §4 exige citar la sección ESPECÍFICA del catálogo con su criterio. Un criterio no se
            # puede citar de un archivo que el modelo nunca vio: sin este digest, pedir la cita
            # fabrica números de sección, que es peor que no pedir nada.
            + reasoning_catalog.digest()
            + "\n\nAlso report alternatives_considered (§5): the readings you rejected and why.")


def _default_synthesizer(question, evidence, pass_label):
    """One synthesis pass over an evidence view (pass1 = DI-only, pass2 = DI + Path B). Returns
    {direct_answer, stated_confidence, confidence_by_subclaim, absence_kind, gap_flags,
    evidence_cited, model, usage}."""
    system = synth_system(pass_label)
    user_text = json.dumps({"question": question, "evidence": evidence}, ensure_ascii=False, default=str)
    out, usage = composite_auditor._anthropic_tool_call(
        SYNTH_MODEL, system, user_text, tool=SYNTH_TOOL, max_tokens=2500)
    gap_flags = list(out.get("gap_flags", []))
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
    try:
        elicited, e_subs, e_usage = _elicit_confidence(question, evidence, out["direct_answer"],
                                                       gap_flags, pass_label)
    except Exception as e:
        elicited, e_subs, e_usage = None, None, None
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
    if not out.get("alternatives_considered"):
        gap_flags.append(f"alternatives_considered AUSENTE en {pass_label} (§5 lo exige) — declarado, "
                         "no rellenado con una lista vacía que se leería como 'no había alternativas'")
    return {"direct_answer": out["direct_answer"], "stated_confidence": conf,
            "confidence_source": conf_source,
            "stated_confidence_inline": inline_conf,   # el instrumento previo persiste (continuidad)
            "confidence_by_subclaim": e_subs or out.get("confidence_by_subclaim"),
            "absence_kind": out.get("absence_kind"),
            "search_query_en": out.get("search_query_en"),
            "gap_flags": gap_flags, "evidence_cited": out.get("evidence_cited", []),
            # contrato §5 (ADR-0060): self-report del modelo; runs.py resuelve sección/tier por tabla
            "alternatives_considered": out.get("alternatives_considered"),
            "framework_applied": out.get("framework_applied"),
            "framework_criterion": out.get("framework_criterion"),
            "framework_reason": out.get("framework_reason"),
            "model": SYNTH_MODEL, "usage": usage}


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


def _normalize_citations(items):
    """Typed, numerically indexed citation series (ADR-0051). Numbers are EVIDENCE; the letter series
    is reserved for precedent (block 6) so the two can never be conflated by construction."""
    out = []
    for i, c in enumerate(items or [], 1):
        if isinstance(c, dict):
            out.append({"n": i, "kind": c.get("kind", "other"), "id": str(c.get("id", "")),
                        "note": c.get("note", "")})
        else:
            out.append({"n": i, "kind": "other", "id": str(c), "note": ""})
    return out


# Per-Mtok prices for the cost PROJECTION (input, output). These are projection INPUTS, not
# measurements — the token counts are measured from API responses; the dollar figure is calculated
# and labeled as such (measurement-class discipline, ADR 2026-07-13).
PRICES_PER_MTOK_USD = {
    "claude-opus-4-8": (5.0, 25.0), "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0), "gpt-4o": (2.5, 10.0),
    "text-embedding-3-small": (0.02, 0.0),
}
PRICES_AS_OF = "2026-08"


def _usage_in_out(usage):
    """Normalize Anthropic (input_tokens/output_tokens) and OpenAI (prompt_tokens/completion_tokens)."""
    u = usage or {}
    return (int(u.get("input_tokens") or u.get("prompt_tokens") or 0),
            int(u.get("output_tokens") or u.get("completion_tokens") or 0))


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

    for _label, p in passes:
        _add(p.get("model") or SYNTH_MODEL, p.get("usage"))
    planner_meta = ((plan or {}).get("judgment") or {}).get("planner") or {}
    planner_usage = planner_meta.get("usage") or {}
    if planner_usage:
        _add(planner_meta.get("model") or SYNTH_MODEL, planner_usage)
    for row in audit_result.get("panel", []):
        if "usage" in row and "verdict" in row:
            _add(row["reviewer"], row["usage"])
    embed_model = os.environ.get("OPENAI_EMBED_MODEL", "text-embedding-3-small")
    cost = 0.0
    for model, m in by_model.items():
        pi, po = PRICES_PER_MTOK_USD.get(model, (0.0, 0.0))
        cost += (m["in"] * pi + m["out"] * po) / 1e6
    cost += embed_tokens * PRICES_PER_MTOK_USD.get(embed_model, (0.02, 0.0))[0] / 1e6
    pi, po = _usage_in_out(planner_usage)
    return {
        "input_tokens": sum(m["in"] for m in by_model.values()),
        "output_tokens": sum(m["out"] for m in by_model.values()),
        "by_model": by_model,
        # el gasto del plan va DENTRO del total (M8 cuadra) y ADEMÁS aparte, para que se pueda
        # responder "¿cuánto cuesta declarar un plan?" sin re-derivarlo
        "plan_judgment": ({"model": planner_meta.get("model"), "in": pi, "out": po}
                          if planner_usage else None),
        "embedding": {"model": embed_model, "total_tokens": embed_tokens,
                      "attribution": "process-wide window during this run (concurrent runs may overlap)"},
        "estimated_cost_usd": round(cost, 4),
        "cost_class": f"PROJECTION (calculated from measured tokens x per-Mtok prices as of "
                      f"{PRICES_AS_OF}; the token counts are measurements, the dollars are not)",
    }


def _embed_usage_snapshot():
    try:
        sys.path.insert(0, str(ROOT / "rag_index" / "graphrag"))
        import embeddings as _emb
        return _emb.usage_snapshot()["total_tokens"]
    except Exception:
        return 0


def execute_run(run, synthesizer=None, panel_caller=None):
    """Execute one claimed run end-to-end. Deterministic under injected synthesizer/panel_caller (the
    offline gate); live otherwise. Never raises — every exit is a recorded terminal state + event."""
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
        db.add_event(run_id, f"stage.{name}", payload=payload, agent="answer_pipeline",
                     degraded=degraded)
        _check_cancel()

    # partial-spend tracking (LOTE-01·A4): what a run spent BEFORE dying must survive on failed and
    # cancelled paths too — M8 cannot reconcile otherwise ("118,000 tokens gastados antes de morir").
    passes, audit_result = [], {}
    embed_t0 = _embed_usage_snapshot()
    # holder explícito: el plan se carga DENTRO del try, y _usage_now (definida antes) tiene que
    # poder verlo en los caminos failed/cancelled — el gasto del planner ya ocurrió y debe sobrevivir
    # (LOTE-01·A4). Una clausura sobre `plan` con locals() no lo alcanza.
    plan_holder = {}

    def _usage_now():
        return _token_usage(passes, audit_result, max(0, _embed_usage_snapshot() - embed_t0),
                            plan=plan_holder.get("plan"))

    try:
        db.add_event(run_id, "run.state", payload={"state": "running"})
        _check_cancel()

        # 0) el plan declarado (tapón 3, ADR-0061) — si la corrida lo trae, es el PRIMER evento de la
        # traza (el boceto M3 lo pinta como primera línea). No traerlo no bloquea nada: se declara.
        plan = json.loads(run["plan_json"]) if run.get("plan_json") else None
        plan_holder["plan"] = plan
        if plan:
            db.add_event(run_id, "stage.plan", agent="planner", payload=plan_event_payload(plan))
            _check_cancel()

        # 1) retrieve — the ONE state machine, instrumented via on_stage (never re-assembled)
        bundle = answer_pipeline.retrieve(run["question"],
                                          entities=[e for e in run["entities_csv"].split(",") if e],
                                          on_stage=_on_stage)
        # one identity end-to-end: the run's id IS the bundle's id (ADR-0044)
        bundle["run_id"] = run_id
        bundle["bundle_identity"] = answer_pipeline._identity(bundle)

        # 2) PASS 1 — DI-only synthesis. Its confidence is the real "is my store enough?" signal
        # (ADR-0051), measured even when structural insufficiency already fetched Path B.
        db.add_event(run_id, "stage.synthesize.start", agent=SYNTH_MODEL)
        pass1 = synthesizer(run["question"], _compact_evidence(bundle, include_path_b=False), "pass1")
        passes.append(("pass1", pass1))
        conf1, conf1_source = _resolve_confidence(pass1)
        db.add_event(run_id, "stage.synthesize.pass1", agent=pass1.get("model"),
                     payload={"stated_confidence": conf1, "confidence_source": conf1_source,
                              "absence_kind": pass1.get("absence_kind"),
                              "gap_flags": pass1.get("gap_flags", [])})
        _check_cancel()

        # 3) fallback decision — TWO deciders, and the record says WHICH fired (handoff §5.7):
        # structural (assess_sufficiency, documented as fooled-by-any-chunk-present) already fetched
        # Path B inside retrieve(); the confidence gate (pass1 < tau, or absent) fires it now.
        structural_fired = bundle["path_b"]["triggered"]
        conf_fired = (not structural_fired) and (conf1 is None or conf1 < FALLBACK_CONF_TAU)
        trigger = "structural" if structural_fired else ("confidence" if conf_fired else None)
        if conf_fired:
            # ADR-0057: the query SENT to the English index is never the raw (Spanish) question when a
            # better source exists — the synthesizer's English keywords first, entities second.
            entities = [e for e in run["entities_csv"].split(",") if e]
            if (pass1.get("search_query_en") or "").strip():
                q_sent, q_source = pass1["search_query_en"].strip(), "synthesizer"
            else:
                q_sent, q_source = answer_pipeline.build_external_query(run["question"], entities)
            # ONE builder for the block (answer_pipeline.path_b_bundle) — the structural trigger inside
            # retrieve() and this confidence-gated one must not maintain two copies of the same dict.
            # `entities` travels: the zfin source keys on gene SYMBOLS, not on a free-text query.
            bundle["path_b"] = answer_pipeline.path_b_bundle(
                run["question"], entities=entities, query=q_sent, query_source=q_source,
                triggered_by=[f"confidence-gate: pass1_confidence={conf1} < tau={FALLBACK_CONF_TAU}"
                              if conf1 is not None else
                              f"confidence-gate: pass1_confidence ABSENT (tau={FALLBACK_CONF_TAU})"])
            # external evidence entered the run -> the honest state is FALLBACK_FETCHED (same
            # constructor, same literals — never a re-invented machine)
            bundle["decision_state"] = answer_pipeline._state(
                "FALLBACK_FETCHED", may_answer=False, may_propose=False,
                required_next="AUDIT — composite-auditor Mode 1 (>=3 adversarial) MUST verdict the "
                              "externally-augmented answer BEFORE it may be shown (confidence-gated "
                              "fallback, ADR-0051; audit on 100% of runs, ADR-0049).")
            db.add_event(run_id, "stage.path_b", agent="answer_pipeline",
                         payload=answer_pipeline.path_b_event_payload(bundle["path_b"],
                                                                     trigger="confidence"))
            _check_cancel()
        bundle["fallback"] = {"trigger": trigger,
                              "fb_meta": {"pass1_confidence": conf1,
                                          "pass1_confidence_source": conf1_source,
                                          "tau": FALLBACK_CONF_TAU,
                                          "structural_sufficient": not structural_fired,
                                          "absence_kind": pass1.get("absence_kind")}}

        # 4) PASS 2 — only when a fallback fired: re-synthesize with the external evidence
        # incorporated. BOTH confidences persist; the delta is the run's most informative datum
        # (the 0.14 -> 0.71 Level-2 measurement).
        if trigger:
            pass2 = synthesizer(run["question"], _compact_evidence(bundle, include_path_b=True), "pass2")
            passes.append(("pass2", pass2))
            conf2, conf2_source = _resolve_confidence(pass2)
            delta = (round(conf2 - conf1, 4) if isinstance(conf1, (int, float))
                     and isinstance(conf2, (int, float)) else None)
            db.add_event(run_id, "stage.synthesize.pass2", agent=pass2.get("model"),
                         payload={"stated_confidence": conf2, "confidence_source": conf2_source,
                                  "delta_vs_pass1": delta,
                                  "absence_kind": pass2.get("absence_kind")})
            answer = pass2
            final_conf, final_source = conf2, conf2_source
        else:
            conf2, conf2_source, delta = None, None, None
            answer = pass1
            final_conf, final_source = conf1, conf1_source
        bundle["bundle_identity"] = answer_pipeline._identity(bundle)
        _check_cancel()

        # 5) deterministic anti-fabrication gate over the FINAL answer (Logic-LM-class, NOT an LLM)
        adm, reasons = verify_output.admissible({"direct_answer": answer["direct_answer"],
                                                 "evidence_cited": answer.get("evidence_cited", [])})
        report = verify_output.verify_identifiers(answer["direct_answer"]).as_dict()
        checks = {"admissible": adm, "reasons": reasons, "identifier_report": report}
        db.add_event(run_id, "stage.deterministic_gate", tool="verify_output",
                     payload=checks, level="info" if adm else "warning")
        _check_cancel()

        # 6) composite audit — 100% of runs (ADR-0049), the terminal transition
        db.add_event(run_id, "stage.audit.start", agent="composite-auditor")
        audit_result = composite_auditor.audit(
            claim={"direct_answer": answer["direct_answer"],
                   "stated_confidence": answer.get("stated_confidence")},
            evidence=_compact_evidence(bundle), deterministic_checks=checks,
            required_because=bundle["decision_state"]["state"], caller=panel_caller)
        bundle = composite_auditor.apply_to_bundle(bundle, audit_result, _evidence_ids(bundle))
        db.add_event(run_id, "stage.audit.verdict", agent="composite-auditor",
                     payload={"verdict": audit_result["verdict"], "tally": audit_result["tally"],
                              "n_valid": audit_result["n_valid"],
                              "source_vocabulary": audit_result["source_vocabulary"]},
                     level="info" if audit_result["verdict"] != "REVISE" else "warning")

        # 7) frozen record (backend-persisted; the webapp only reads — ADR-0047 d.2)
        embed_tokens = max(0, _embed_usage_snapshot() - embed_t0)
        token_usage = _token_usage(passes, audit_result, embed_tokens, plan=plan)
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
            "answer": {"direct_answer": answer["direct_answer"],
                       "stated_confidence": answer.get("stated_confidence"),
                       "absence_kind": answer.get("absence_kind"),
                       "gap_flags": answer.get("gap_flags", []),
                       "model": answer.get("model")},
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
            "citations": _normalize_citations(answer.get("evidence_cited")),
            "deterministic_checks": checks,
            "token_usage": token_usage,
            "usage_raw": {"passes": {label: p.get("usage", {}) for label, p in passes},
                          "panel_total": audit_result.get("usage", {})},
            "bundle_identity": bundle["bundle_identity"],
            "question_matches_run": bundle["question"] == run["question"],
        }
        # LOTE-02·3: the list-row epistemic summary is derived HERE, at freeze — never at serve time
        # (the frozen-counter discipline: a list row must not re-derive what the record froze).
        epistemic_summary = {"retrieval_mode": bundle["retrieval_summary"]["mode"],
                             "verdict": audit_result["verdict"],
                             "confidence_state": frozen["confidence"]["state"],
                             "panel_n_valid": audit_result["n_valid"]}
        db.update_run(run_id, state="awaiting_closure", finished_at=db._now(),
                      bundle_json=json.dumps(bundle, ensure_ascii=False, default=str),
                      frozen_record_json=json.dumps(frozen, ensure_ascii=False, default=str),
                      usage_json=json.dumps(token_usage, ensure_ascii=False, default=str),
                      epistemic_summary_json=json.dumps(epistemic_summary, ensure_ascii=False))
        db.add_event(run_id, "run.state", payload={"state": "awaiting_closure",
                                                   "verdict": audit_result["verdict"]})
    except RunCancelled:
        db.update_run(run_id, state="cancelled", finished_at=db._now(),
                      usage_json=json.dumps(_usage_now(), ensure_ascii=False, default=str))
        db.add_event(run_id, "run.state", payload={"state": "cancelled"}, level="warning")
    except Exception as e:
        db.update_run(run_id, state="failed", finished_at=db._now(),
                      error=f"{type(e).__name__}: {str(e)[:400]}",
                      usage_json=json.dumps(_usage_now(), ensure_ascii=False, default=str))
        db.add_event(run_id, "error", payload={"error": f"{type(e).__name__}: {str(e)[:400]}"},
                     level="error")
        db.add_event(run_id, "run.state", payload={"state": "failed"}, level="error")


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


def new_run(user_id, question, entities=None, plan_json=None):
    run_id = uuid.uuid4().hex
    db.create_run(run_id, user_id, question, entities, plan_json=plan_json)
    db.add_event(run_id, "run.state", payload={"state": "queued"})
    return run_id


# --- worker threads ----------------------------------------------------------------------------------

_STOP = threading.Event()


def worker_loop(poll_seconds=1.0):
    while not _STOP.is_set():
        run = db.claim_next_queued()
        if run is None:
            time.sleep(poll_seconds)
            continue
        execute_run(run)


def start_workers(n=2):
    """In-process daemon workers (single uvicorn process, ADR-0048). sklearn is already preloaded on the
    MAIN thread by the app lifespan before workers start — the 1800s deadlock cannot recur here."""
    for i in range(n):
        threading.Thread(target=worker_loop, name=f"run-worker-{i}", daemon=True).start()


def stop_workers():
    _STOP.set()

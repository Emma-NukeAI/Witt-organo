"""smoke_competence.py — gate determinista de la REBANADA C1 de ADR-0080 (compuerta de competencia y lazo):
competence.evaluate PURO (conjunción, kill-switch, not_applicable, calibration gating on/off, sin plan),
db.calibration_coverage (medición: sólo corridas CLOSED con rating cuyos nichos intersecan), y el CABLEADO en
runs.execute_run: elicit{pass} → gate{pass:1} adelantado → stage.competence → (competente: sin ronda, trigger
null | no competente: stage.search.plan + Ruta B por el harness + pass2 + gate{pass:2}) → frozen 1.9
(competence, search_ledger, citations[].support_state, deterministic_checks.{pass1_admissible,
positive_claim_requires_citations, competence_gate}, fallback.trigger nuevo + trigger_legacy, token_usage.by_stage
con suma == by_model, epistemic_summary.{competent, n_search_rounds}); reintento por juez declarado en el evento.

100% offline: SQLite en %LOCALAPPDATA%/Temp/claude/witt-smokes, answer_pipeline.retrieve / path_b_bundle
monkeypatcheados, sintetizador y panel inyectados — cero red, cero modelo, cero mutación de la DATA INAMOVIBLE.
Exit 0 = todo PASS.

Corre (máscara offline):
  WITT_BACKEND_DB_URL="sqlite:///C:/Users/Emmanuel/AppData/Local/Temp/claude/witt-smokes/smoke-c1-competence.db"
  NEO4J_URI="" RAG_BACKEND=sparse OPENAI_API_KEY="" ANTHROPIC_API_KEY="" WITT_RUN_ORIGIN=smoke
  python rag_index/query_service/smoke_competence.py
"""
import datetime
import json
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# --- máscara offline (patrón smoke_thread_context, ADR-0079): la BD se FUERZA vacía ----------------------------
_SMOKES = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Temp" / "claude" / "witt-smokes"
_SMOKES.mkdir(parents=True, exist_ok=True)
_DB = _SMOKES / "smoke-c1-competence.db"
if _DB.exists():
    _DB.unlink()
os.environ["WITT_BACKEND_DB_URL"] = f"sqlite:///{_DB.as_posix()}"
os.environ.pop("NEO4J_URI", None)
os.environ.setdefault("RAG_BACKEND", "sparse")
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["WITT_RUN_ORIGIN"] = "smoke"
os.environ["WITT_ALLOW_RUNS_OFFLINE"] = "1"
for _k in ("WITT_COMPETENCE_GATE", "WITT_CG_REQUIRE_CALIBRATION", "WITT_COMPETENCE_MIN_HISTORY",
           "WITT_SEARCH_ROUNDS_CAP", "WITT_SEARCH_ROUND_BUDGET_S", "WITT_SEARCH_DEFAULT_FAMILIES",
           "WITT_JUDGE_RETRIES", "WITT_FALLBACK_CONF_TAU"):
    os.environ.pop(_k, None)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import competence  # noqa: E402
import db  # noqa: E402
import runs as runs_mod  # noqa: E402
from lib import answer_pipeline, composite_auditor, verify_output  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


# =====================================================================================================
# (A) competence.evaluate — PURO
# =====================================================================================================
PLAN_OK = {"plan_version": "3", "question": "q", "judgment": {"state": "declared", "route": "evidence-run",
                                                             "niches": [{"code": "N3", "name": "Embriología"}]}}
PLAN_STORE = {"plan_version": "3", "question": "q",
              "judgment": {"state": "declared", "route": "store-consultation", "niches": []}}
CAL_OK = {"n": 12, "min_required": 10, "sufficient": True, "niche_codes": ["N3"]}
CAL_LOW = {"n": 2, "min_required": 10, "sufficient": False, "niche_codes": ["N3"]}
ENV0 = {}
# cg-3 (orquestador 2026-09-15): conf1_ge_tau GATEA por default; WITT_CG_CONF_COMPONENT=0 declarado lo vuelve informativo.
ENV_OFF = {"WITT_CG_CONF_COMPONENT": "0"}
NOTE_GATING = ("participa como componente conf1_ge_tau medido por CONF_TOOL (ADR-0065; gating true, "
               "WITT_CG_CONF_COMPONENT default 1, cg-3); la conjunción la decide código")
NOTE_OFF = "no participa en la decisión (conf1_ge_tau informativo, WITT_CG_CONF_COMPONENT=0 declarado)"

b = competence.evaluate(0.8, True, PLAN_OK, False, CAL_LOW, env=ENV0)
check("(A) conjunción completa → competent True, reasons [], decided_by 'code', cg-3; conf1_ge_tau GATEA por default "
      "(class model-judgment; la nota dice que participa como componente medido por CONF_TOOL, ADR-0065, y que la conjunción "
      "la decide código) y calibration NO gatea por default (WITT_CG_REQUIRE_CALIBRATION=0); "
      "conjunction = conf1>=tau ∧ admissible ∧ route ∧ niches ∧ ¬structural",
      b["competent"] is True and b["reasons"] == [] and b["decided_by"] == "code"
      and b["module_version"] == "cg-4" == competence.MODULE_VERSION and b["not_applicable"] is False
      and b["self_report"] == {"stated_confidence": 0.8, "class": "model-judgment", "note": NOTE_GATING}
      and b["conjunction"] == ["conf1_ge_tau", "admissible", "route_evidence_run", "niches_nonempty", "structural_not_fired"]
      and b["components"]["conf1_ge_tau"]["gating"] is True and b["config"]["conf_component_gating"] is True
      and b["components"]["calibration_coverage"]["gating"] is False
      and b["components"]["calibration_coverage"]["sufficient"] is False
      and "calibration_coverage" not in b["conjunction"]
      # ADR-0082 (G.2, cg-4): sin council_coverage el componente es 'not-applicable (no-ledger)' — null declarado, fuera de conjunction
      and b["components"]["council_uncovered_must"]["state"] == "not-applicable (no-ledger)"
      and b["components"]["council_uncovered_must"]["value"] is None
      and b["components"]["council_uncovered_must"]["gating"] is False
      and "council_uncovered_must" not in b["conjunction"],
      json.dumps(b["reasons"]))

# =====================================================================================================
# (A, cg-4 — ADR-0082 G.2) council_uncovered_must INTERPRETADO: checked / vacuous / incomplete / no-ledger / kill-switch / errored
# =====================================================================================================
COV_OK = {"state": "judged", "must_total": 4, "must_gateable": 2, "must_covered": 2, "must_uncovered": 0,
          "must_uncovered_strict": 0, "must_partial": 0, "must_not_judged": 0, "must_attested": 1, "must_discarded": 0,
          "must_unsatisfiable": 1, "n_valid_votes": 5, "n_hallucinated_votes": 0, "n_requirements_kept": 4,
          "round": {"state": "applicable", "n_valid": 15, "n_members": 17, "quorum_required": 11}}
COV_UNC = {**COV_OK, "must_covered": 1, "must_uncovered": 1, "must_partial": 1}
COV_INC = {**COV_UNC, "round": {"state": "incomplete", "n_valid": 9, "n_members": 17, "quorum_required": 11}}
COV_VAC0 = {**COV_OK, "must_total": 0, "must_gateable": 0, "must_covered": 0, "must_attested": 0, "must_unsatisfiable": 0}
COV_VACU = {**COV_OK, "must_total": 2, "must_gateable": 0, "must_covered": 0, "must_attested": 0, "must_unsatisfiable": 2}
b_ok = competence.evaluate(0.8, True, PLAN_OK, False, CAL_LOW, council_coverage=COV_OK, env=ENV0)
b_unc = competence.evaluate(0.8, True, PLAN_OK, False, CAL_LOW, council_coverage=COV_UNC, env=ENV0)
b_inc = competence.evaluate(0.8, True, PLAN_OK, False, CAL_LOW, council_coverage=COV_INC, env=ENV0)
c_ok, c_unc, c_inc = (x["components"]["council_uncovered_must"] for x in (b_ok, b_unc, b_inc))
check("(cg-4) cobertura JUZGADA con 0 must sin cubrir → componente {state 'checked', value True, gating True} DENTRO de conjunction "
      "(6 componentes, council_uncovered_must último) → competent True; copia must_* y n_valid_votes; must atestiguado (1) y "
      "unsatisfiable-by-harness (1) contados y FUERA del gating (E1: must_gateable 2 de must_total 4); class y rule declarados",
      b_ok["competent"] is True and c_ok["state"] == "checked" and c_ok["value"] is True and c_ok["gating"] is True
      and b_ok["conjunction"] == ["conf1_ge_tau", "admissible", "route_evidence_run", "niches_nonempty", "structural_not_fired",
                                  "council_uncovered_must"]
      and c_ok["must_total"] == 4 and c_ok["must_gateable"] == 2 and c_ok["must_attested"] == 1 and c_ok["must_unsatisfiable"] == 1
      and c_ok["n_valid_votes"] == 5 and c_ok["class"] == competence.COUNCIL_COMPONENT_CLASS and c_ok["rule"] == competence.COUNCIL_COMPONENT_RULE
      and c_ok["round"] == {"state": "applicable", "n_valid": 15, "n_members": 17, "quorum_required": 11,
                            "n_eligible": None, "quorum_required_full_membership": None},
      json.dumps({k: c_ok[k] for k in ("state", "value", "gating", "must_gateable")}))
# corrector ADR-0082 (C.3/C.5): el cuórum de r2 se mide sobre los ELEGIBLES (dueños de un requisito kept) — el literal del
# componente dice k / n_eligible; un insumo viejo sin n_eligible cae a n_members (el check de arriba lo mide: None declarado)
COV_INC_ELIG = {**COV_UNC, "round": {"state": "incomplete", "n_valid": 7, "n_members": 17, "n_eligible": 12, "quorum_required": 8,
                                     "quorum_required_full_membership": 11}}
c_inc_e = competence.evaluate(0.8, True, PLAN_OK, False, CAL_LOW, council_coverage=COV_INC_ELIG, env=ENV0)["components"]["council_uncovered_must"]
check("(cg-4) corrector: ronda INCOMPLETA medida sobre ELEGIBLES (7/12 < cuórum 8; 17 miembros, 5 not-invoked) → state "
      "'incomplete (7/12 < quorum 8)', value False, gating True, round copia n_eligible y quorum_required_full_membership 11",
      c_inc_e["state"] == "incomplete (7/12 < quorum 8)" and c_inc_e["value"] is False and c_inc_e["gating"] is True
      and c_inc_e["round"] == {"state": "incomplete", "n_valid": 7, "n_members": 17, "n_eligible": 12, "quorum_required": 8,
                               "quorum_required_full_membership": 11}
      and competence.council_component_state_in_vocabulary(c_inc_e["state"]), c_inc_e["state"])
check("(cg-4) 1 must PARCIAL (cuenta como sin cubrir, lectura conservadora) → value False, reason con el desglose → competent False "
      "reasons ['council_uncovered_must'] (los demás True)",
      b_unc["competent"] is False and b_unc["reasons"] == ["council_uncovered_must"] and c_unc["value"] is False
      and c_unc["state"] == "checked" and c_unc["reason"].startswith("1 kept must without coverage"),
      json.dumps(c_unc["reason"]))
check("(cg-4) ronda INCOMPLETA (9/17 < cuórum 11) → state 'incomplete (9/17 < quorum 11)', value False, gating True, reason "
      "'council-incomplete (k/N < quorum)' → competent False (un insumo que se intentó y falló es ausente, no kill-switch)",
      b_inc["competent"] is False and b_inc["reasons"] == ["council_uncovered_must"]
      and c_inc["state"] == "incomplete (9/17 < quorum 11)" and c_inc["value"] is False and c_inc["gating"] is True
      and c_inc["reason"] == competence.COUNCIL_INCOMPLETE_REASON == "council-incomplete (k/N < quorum)",
      json.dumps({k: c_inc[k] for k in ("state", "value", "reason")}))
b_v0 = competence.evaluate(0.8, True, PLAN_OK, False, CAL_LOW, council_coverage=COV_VAC0, env=ENV0)
b_vu = competence.evaluate(0.8, True, PLAN_OK, False, CAL_LOW, council_coverage=COV_VACU, env=ENV0)
check("(cg-4) VACUO: 0 must kept → 'vacuous (0 must kept)' value True (medición declarada, no un True vacío silencioso); 2 must todos "
      "unsatisfiable-by-harness → 'vacuous (0 gateable must — 2 unsatisfiable-by-harness)' value True (E1: no gatean, se cuentan); "
      "ambos gating True y competent True",
      b_v0["components"]["council_uncovered_must"]["state"] == "vacuous (0 must kept)"
      and b_v0["components"]["council_uncovered_must"]["value"] is True and b_v0["competent"] is True
      and b_vu["components"]["council_uncovered_must"]["state"] == "vacuous (0 gateable must — 2 unsatisfiable-by-harness)"
      and b_vu["components"]["council_uncovered_must"]["value"] is True and b_vu["competent"] is True
      and b_vu["components"]["council_uncovered_must"]["must_unsatisfiable"] == 2,
      json.dumps([b_v0["components"]["council_uncovered_must"]["state"], b_vu["components"]["council_uncovered_must"]["state"]]))
b_ks = competence.evaluate(0.8, True, PLAN_OK, False, CAL_LOW, council_coverage=COV_UNC, env={"WITT_COUNCIL": "0"})
b_err = competence.evaluate(0.8, True, PLAN_OK, False, CAL_LOW, council_coverage={"state": "errored (RuntimeError)"}, env=ENV0)
b_skip = competence.evaluate(0.8, True, PLAN_OK, False, CAL_LOW, council_coverage={"state": "skipped-by-human"}, env=ENV0)
b_nr = competence.evaluate(0.8, True, PLAN_OK, False, CAL_LOW, council_coverage={"state": "not-requested (origin smoke)"}, env=ENV0)
check("(cg-4) kill-switch WITT_COUNCIL=0 MANDA aunque llegue cobertura juzgada: state 'kill-switch WITT_COUNCIL=0', value null, gating "
      "False, fuera de conjunction (== cg-3), config.council_enabled False (source env); errored (…) → mismo literal, null, sin gatear; "
      "'skipped-by-human' → 'not-applicable (skipped-by-human)'; 'not-requested (…)' → 'not-applicable (not-requested (…))' — "
      "todos competent True porque el resto de la conjunción es True",
      b_ks["components"]["council_uncovered_must"]["state"] == "kill-switch WITT_COUNCIL=0"
      and b_ks["components"]["council_uncovered_must"]["value"] is None and b_ks["components"]["council_uncovered_must"]["gating"] is False
      and "council_uncovered_must" not in b_ks["conjunction"] and b_ks["conjunction"] == b["conjunction"]
      and b_ks["config"]["council_enabled"] is False and b_ks["config"]["council_enabled_source"] == "env:WITT_COUNCIL"
      and b_err["components"]["council_uncovered_must"]["state"] == "errored (RuntimeError)"
      and b_err["components"]["council_uncovered_must"]["value"] is None and b_err["components"]["council_uncovered_must"]["gating"] is False
      and b_skip["components"]["council_uncovered_must"]["state"] == "not-applicable (skipped-by-human)"
      and b_nr["components"]["council_uncovered_must"]["state"] == "not-applicable (not-requested (origin smoke))"
      and all(x["competent"] is True for x in (b_ks, b_err, b_skip, b_nr)),
      json.dumps([x["components"]["council_uncovered_must"]["state"] for x in (b_ks, b_err, b_skip, b_nr)]))
b_off = competence.evaluate(0.8, True, PLAN_OK, False, CAL_LOW, council_coverage=COV_UNC, env={"WITT_CG_COUNCIL_COMPONENT": "0"})
b_bad = competence.evaluate(0.8, True, PLAN_OK, False, CAL_LOW, council_coverage=COV_UNC, env={"WITT_CG_COUNCIL_COMPONENT": "maybe"})
check("(cg-4) WITT_CG_COUNCIL_COMPONENT=0 → INFORMATIVO declarado: value False (medido) pero gating False, reason_gating, fuera de "
      "conjunction → la conjunción es EXACTAMENTE la de cg-3 y competent True; config.council_component_gating False (env); env basura "
      "'maybe' → default True 'default-invalid-env:WITT_CG_COUNCIL_COMPONENT' (gatea)",
      b_off["components"]["council_uncovered_must"]["value"] is False and b_off["components"]["council_uncovered_must"]["gating"] is False
      and "reason_gating" in b_off["components"]["council_uncovered_must"]
      and b_off["conjunction"] == b["conjunction"] and b_off["competent"] is True
      and b_off["config"]["council_component_gating"] is False
      and b_off["config"]["council_component_gating_source"] == "env:WITT_CG_COUNCIL_COMPONENT"
      and b_bad["components"]["council_uncovered_must"]["gating"] is True and b_bad["competent"] is False
      and b_bad["config"]["council_component_gating_source"] == "default-invalid-env:WITT_CG_COUNCIL_COMPONENT",
      json.dumps(b_off["config"]))
check("(cg-4) compact() copia el bool del componente (True/False/null) como los demás; el vocabulario del estado (exactos + prefijos "
      "'incomplete (' | 'errored (' | 'not-applicable (' | 'vacuous (') valida TODOS los literales medidos aquí y rechaza basura",
      competence.compact(b_ok)["components"]["council_uncovered_must"] is True
      and competence.compact(b_unc)["components"]["council_uncovered_must"] is False
      and competence.compact(b_ks)["components"]["council_uncovered_must"] is None
      and all(competence.council_component_state_in_vocabulary(x["components"]["council_uncovered_must"]["state"])
              for x in (b, b_ok, b_unc, b_inc, b_v0, b_vu, b_ks, b_err, b_skip, b_nr, b_off))
      and not competence.council_component_state_in_vocabulary("incomplete (") and not competence.council_component_state_in_vocabulary("bogus")
      and competence.COUNCIL_COMPONENT_STATES_EXACT == ("checked", "vacuous (0 must kept)", "kill-switch WITT_COUNCIL=0",
                                                        "not-applicable (no-ledger)"),
      json.dumps(sorted({x["components"]["council_uncovered_must"]["state"] for x in (b, b_ok, b_unc, b_inc, b_v0, b_vu, b_ks, b_err, b_skip, b_nr, b_off)})))

b_low = competence.evaluate(0.3, True, PLAN_OK, False, CAL_OK, env=ENV0)
b_abs = competence.evaluate(None, True, PLAN_OK, False, CAL_OK, env=ENV0)
b_low_off = competence.evaluate(0.3, True, PLAN_OK, False, CAL_OK, env=ENV_OFF)
b_abs_off = competence.evaluate(None, True, PLAN_OK, False, CAL_OK, env=ENV_OFF)
check("(A, cg-3) el escalar ELICITADO gatea por default (ADR-0051/0065; caso a361f566): conf1 0.3 < tau con todo lo demás True → "
      "competent FALSE, reasons ['conf1_ge_tau'] (value False, conf1, tau 0.5, gating True, class model-judgment) y la nota de "
      "self_report dice 'participa como componente conf1_ge_tau medido por CONF_TOOL…'; conf1 AUSENTE → False con reason "
      "'conf1-absent' (lo ausente NO es competencia). APAGADO explícito (WITT_CG_CONF_COMPONENT=0): competent True, "
      "conf1_ge_tau value False gating False fuera de conjunction, sin reasons; conf ausente → True con reason 'conf1-absent' "
      "declarado en el componente informativo; nota 'no participa en la decisión…'",
      b_low["competent"] is False and b_low["reasons"] == ["conf1_ge_tau"]
      and b_low["components"]["conf1_ge_tau"] == {"value": False, "conf1": 0.3, "tau": 0.5,
                                                   "tau_source": "default-unset:WITT_FALLBACK_CONF_TAU",
                                                   "gating": True, "class": "model-judgment (stated_confidence)"}
      and b_low["conjunction"][0] == "conf1_ge_tau" and b_low["config"]["conf_component_gating"] is True
      and b_low["self_report"]["note"] == NOTE_GATING
      and b_abs["competent"] is False and b_abs["reasons"] == ["conf1_ge_tau"]
      and b_abs["components"]["conf1_ge_tau"]["reason"] == "conf1-absent"
      and b_low_off["competent"] is True and b_low_off["reasons"] == []
      and b_low_off["components"]["conf1_ge_tau"]["value"] is False and b_low_off["components"]["conf1_ge_tau"]["gating"] is False
      and "conf1_ge_tau" not in b_low_off["conjunction"] and b_low_off["config"]["conf_component_gating"] is False
      and b_low_off["self_report"]["note"] == NOTE_OFF
      and b_abs_off["competent"] is True and b_abs_off["components"]["conf1_ge_tau"]["reason"] == "conf1-absent")

b_inadm = competence.evaluate(0.9, False, PLAN_OK, False, CAL_OK, env=ENV0)
b_struct = competence.evaluate(0.9, True, PLAN_OK, True, CAL_OK, env=ENV0)
b_none = competence.evaluate(0.9, None, PLAN_OK, False, CAL_OK, env=ENV0)
check("(A) pass1 inadmisible → False ['admissible']; estructural disparado → False ['structural_not_fired']; "
      "admissible None (no medido) → False con reason 'admissible-not-measured'",
      b_inadm["competent"] is False and b_inadm["reasons"] == ["admissible"]
      and b_struct["competent"] is False and b_struct["reasons"] == ["structural_not_fired"]
      and b_none["competent"] is False and b_none["components"]["admissible"]["reason"] == "admissible-not-measured")

b_store = competence.evaluate(0.9, True, PLAN_STORE, False, CAL_OK, env=ENV0)
check("(A) route 'store-consultation' → not_applicable True, competent None, skipped_reason declarado (no hay "
      "compuerta que aplicar; los componentes viajan igual)",
      b_store["not_applicable"] is True and b_store["competent"] is None
      and "store-consultation" in b_store["skipped_reason"]
      and b_store["components"]["route_evidence_run"] == {"value": False, "route": "store-consultation",
                                                         "reason": "route='store-consultation'"})

b_kill = competence.evaluate(0.9, True, PLAN_OK, False, CAL_OK, env={"WITT_COMPETENCE_GATE": "0"})
check("(A) kill-switch WITT_COMPETENCE_GATE=0 → competent None + skipped_reason con la env; components completos "
      "(reasons [] — la conjunción habría pasado) y config.gate_enabled False",
      b_kill["competent"] is None and "WITT_COMPETENCE_GATE=0" in b_kill["skipped_reason"]
      and b_kill["reasons"] == [] and b_kill["config"]["gate_enabled"] is False
      and set(b_kill["components"]) == set(competence.COMPONENT_ORDER))

b_cal_on = competence.evaluate(0.9, True, PLAN_OK, False, CAL_LOW, env={"WITT_CG_REQUIRE_CALIBRATION": "1"})
b_cal_on_ok = competence.evaluate(0.9, True, PLAN_OK, False, CAL_OK, env={"WITT_CG_REQUIRE_CALIBRATION": "1"})
check("(A) calibration gating ON (WITT_CG_REQUIRE_CALIBRATION=1): insuficiente → False ['calibration_coverage'] "
      "(gating True, n_closed_rated 2, min 10); suficiente → True; la llave entra a `conjunction`",
      b_cal_on["competent"] is False and b_cal_on["reasons"] == ["calibration_coverage"]
      and b_cal_on["components"]["calibration_coverage"]["gating"] is True
      and b_cal_on["components"]["calibration_coverage"]["n_closed_rated"] == 2
      and b_cal_on["components"]["calibration_coverage"]["min_required"] == 10
      and "calibration_coverage" in b_cal_on["conjunction"]
      and b_cal_on_ok["competent"] is True)

b_noplan = competence.evaluate(0.9, True, None, False, {"n": None, "sufficient": False, "reason": "no-niches",
                                                        "min_required": 10}, env=ENV0)
b_errplan = competence.evaluate(0.9, True, {"judgment": {"state": "errored"}}, False, CAL_OK, env=ENV0)
check("(A) SIN plan (POST /runs directo) → route/niches False con reason 'no-plan' → not-competent declarado; "
      "juicio errado → reason cita el state; calibration n None + reason 'no-niches' se propaga",
      b_noplan["competent"] is False and b_noplan["reasons"] == ["route_evidence_run", "niches_nonempty"]
      and b_noplan["components"]["route_evidence_run"]["reason"] == "no-plan"
      and b_noplan["components"]["niches_nonempty"]["reason"] == "no-plan"
      and b_noplan["components"]["calibration_coverage"]["n_closed_rated"] is None
      and b_noplan["components"]["calibration_coverage"]["reason"] == "no-niches"
      and b_errplan["competent"] is False and "errored" in b_errplan["components"]["route_evidence_run"]["reason"])

cfg_bad = competence.env_config({"WITT_COMPETENCE_MIN_HISTORY": "abc", "WITT_FALLBACK_CONF_TAU": "7"})
cfg_env = competence.env_config({"WITT_COMPETENCE_MIN_HISTORY": "4", "WITT_FALLBACK_CONF_TAU": "0.7"})
comp_view = competence.compact(b_low)
check("(A) env tolerante: MIN_HISTORY 'abc' → 10 'default-invalid-env'; TAU 7 → 0.5 'default-invalid-env'; "
      "válidos → env:*; tau del caller se declara 'caller'; compact() = copia legible para el panel",
      cfg_bad["min_history"] == 10 and cfg_bad["min_history_source"] == "default-invalid-env:WITT_COMPETENCE_MIN_HISTORY"
      and cfg_bad["tau"] == 0.5 and cfg_bad["tau_source"] == "default-invalid-env:WITT_FALLBACK_CONF_TAU"
      and cfg_env["min_history"] == 4 and cfg_env["tau"] == 0.7 and cfg_env["tau_source"] == "env:WITT_FALLBACK_CONF_TAU"
      and competence.evaluate(0.6, True, PLAN_OK, False, CAL_OK, env=ENV0, tau=0.7)["config"]["tau_source"] == "caller"
      and competence.evaluate(0.6, True, PLAN_OK, False, CAL_OK, env=ENV0, tau=0.7)["competent"] is False
      and comp_view["competent"] is False and comp_view["reasons"] == ["conf1_ge_tau"]
      and comp_view["components"]["conf1_ge_tau"] is False and comp_view["components"]["calibration_coverage"] is True)

# corrector ADR-0080 (paridad webapp 2026-09-15): τ y su fuente se resuelven UNA vez — el componente y config coinciden
b_tau_c = competence.evaluate(0.6, True, PLAN_OK, False, CAL_OK, env=ENV0, tau=0.5)
b_tau_e = competence.evaluate(0.6, True, PLAN_OK, False, CAL_OK, env={"WITT_FALLBACK_CONF_TAU": "0.7"})
check("(A, corrector paridad webapp) tau_source UNA vez: con tau del caller components.conf1_ge_tau.tau_source == config.tau_source "
      "== 'caller' (antes el componente decía 'default-unset:…' para el MISMO τ); sin tau ambos == la fuente del env "
      "('env:WITT_FALLBACK_CONF_TAU', 0.7) o del default ('default-unset:WITT_FALLBACK_CONF_TAU', 0.5); el τ efectivo coincide",
      b_tau_c["components"]["conf1_ge_tau"]["tau_source"] == b_tau_c["config"]["tau_source"] == "caller"
      and b_tau_c["components"]["conf1_ge_tau"]["tau"] == b_tau_c["config"]["tau"] == 0.5
      and b_tau_e["components"]["conf1_ge_tau"]["tau_source"] == b_tau_e["config"]["tau_source"] == "env:WITT_FALLBACK_CONF_TAU"
      and b_tau_e["components"]["conf1_ge_tau"]["tau"] == b_tau_e["config"]["tau"] == 0.7 and b_tau_e["competent"] is False
      and b["components"]["conf1_ge_tau"]["tau_source"] == b["config"]["tau_source"] == "default-unset:WITT_FALLBACK_CONF_TAU",
      json.dumps({"caller": (b_tau_c["components"]["conf1_ge_tau"]["tau_source"], b_tau_c["config"]["tau_source"]),
                  "env": (b_tau_e["components"]["conf1_ge_tau"]["tau_source"], b_tau_e["config"]["tau_source"])}))

# corrector ADR-0080 (paridad webapp 2026-09-15): include_origins / include_origins_source viajan al componente si la cobertura los trae
CAL_ORIG = {**CAL_LOW, "include_origins": ["production"], "include_origins_source": "default-unset:WITT_CG_CALIBRATION_ORIGINS"}
b_orig = competence.evaluate(0.8, True, PLAN_OK, False, CAL_ORIG, env=ENV0)
check("(A, corrector paridad webapp) components.calibration_coverage COPIA include_origins (['production']) e include_origins_source "
      "('default-unset:WITT_CG_CALIBRATION_ORIGINS') cuando la cobertura los trae (ADR-0080 A lo promete); sin ellos (CAL_LOW) las "
      "dos llaves quedan AUSENTES, no null (nada se rellena)",
      b_orig["components"]["calibration_coverage"]["include_origins"] == ["production"]
      and b_orig["components"]["calibration_coverage"]["include_origins_source"] == "default-unset:WITT_CG_CALIBRATION_ORIGINS"
      and b_orig["components"]["calibration_coverage"]["n_closed_rated"] == 2
      and "include_origins" not in b["components"]["calibration_coverage"]
      and "include_origins_source" not in b["components"]["calibration_coverage"],
      json.dumps(b_orig["components"]["calibration_coverage"]))

# =====================================================================================================
# db.calibration_coverage — MEDICIÓN
# =====================================================================================================
db.init_db()
db.upsert_user("natalia", "Natalia", "medico", "pw-natalia-123")
USER = {"user_id": "natalia", "role": "medico"}


def _closed_rated(run_id, niches_frozen, rate=True, state="closed"):
    db.create_run(run_id, "natalia", f"q {run_id}", [], thread_id=run_id, turn_no=1, turn_kind="root", origin="smoke")
    frozen = json.dumps({"niches": niches_frozen}) if niches_frozen is not None else None
    db.update_run(run_id, state=state, frozen_record_json=frozen,
                  frozen_at=datetime.datetime.now(datetime.timezone.utc) if state == "closed" else None)
    if rate:
        db.add_rating({"run_id": run_id, "user_id": "dev-other", "frozen_record_json": frozen}, USER,
                      4, "value", 4, "value")


CAT_N3 = {"catalogo": {"domain_niches": {"primary": {"N3": 1}, "secondary": {}}}, "panel": {"counts": {}}}
PANEL_N4 = {"catalogo": {"domain_niches": {"primary": {}, "secondary": {}}}, "panel": {"counts": {"N4": 2}}}
_closed_rated("cal-1", CAT_N3)                       # cuenta (catálogo N3, closed, rated)
_closed_rated("cal-2", PANEL_N4)                     # cuenta para N4 (panel), no para N3
_closed_rated("cal-3", CAT_N3, rate=False)           # closed SIN rating → no cuenta
_closed_rated("cal-4", CAT_N3, state="awaiting_closure")   # rated pero NO closed → no cuenta
_closed_rated("cal-5", None)                         # closed + rated sin registro → no cuenta
cc_none = db.calibration_coverage([], 10)
cc_n3 = db.calibration_coverage(["N3"], 1)
cc_n34 = db.calibration_coverage(["N3", "N4"], 3)
check("db.calibration_coverage: sin nichos → {n: None, sufficient False, reason 'no-niches'} (no un 0); N3 → n=1 "
      "(sólo closed+rated+niche interseca: ni el closed sin rating, ni el awaiting_closure, ni el sin registro); "
      "N3+N4 → n=2 < 3 insuficiente; class 'medicion', include_origins None declarado (la FUNCIÓN no filtra; el filtro "
      "'production' lo pone runs._calibration_origins — ver el check de gating en execute_run)",
      cc_none["n"] is None and cc_none["sufficient"] is False and cc_none["reason"] == "no-niches"
      and cc_n3["n"] == 1 and cc_n3["sufficient"] is True and cc_n3["n_closed_rated_total"] == 3
      and cc_n34["n"] == 2 and cc_n34["sufficient"] is False and cc_n34["min_required"] == 3
      and cc_n3["class"] == "medicion" and cc_n3["include_origins"] is None and cc_n3["niche_codes"] == ["N3"],
      json.dumps([cc_none, cc_n3, cc_n34]))

# =====================================================================================================
# (B)(F)(G) cableado en runs.execute_run — retrieve / path_b_bundle monkeypatcheados, stubs inyectados
# =====================================================================================================
ALL_A = {"correctness": "APPROVE", "overclaim": "APPROVE", "evidence-grounding": "APPROVE",
         "reproducibility": "APPROVE"}
HIT = {"doc_id": "CORPUS-2026-0003#c000", "type": "chunk", "score": 0.9, "text": "pronephros evidence wt1a"}


def _fake_retrieve(structural=False):
    def _retrieve(question, entities=None, n_papers=None, on_stage=None, search_plan=None):
        a = {"n_hits": 1, "top_score": 0.9, "has_literature_chunks": True,
             "retrieval": {"mode": "semantic", "raw_marker": None, "n_hits": 1, "k_requested": 6},
             "text_cap_chars": 2400, "text_cap_source": "default-unset:WITT_PATH_A_CHARS", "hits": [dict(HIT)]}
        suf = {"sufficient": not structural, "reasons": ([] if not structural else ["no chunks on topic"])}
        if on_stage:
            on_stage("path_a", {"n_hits": 1, "retrieval": a["retrieval"], "text_cap_chars": 2400})
            on_stage("check_entities", {})
            on_stage("assess_sufficiency", suf)
        bundle = {"question": question, "run_id": "stub", "stamp": "2026-09-15T00:00:00+00:00",
                  "question_slug": "q", "entities_checked": {}, "path_a": a, "sufficiency": suf}
        if structural:
            bundle["path_b"] = {"triggered": True, "triggered_by": suf["reasons"], "papers": [], "query_sent": None,
                                "query_source": None, "n_results_by_source": {}, "sources_requested": []}
            bundle["decision_state"] = answer_pipeline._state("FALLBACK_FETCHED", False, False, "AUDIT")
            if on_stage:
                on_stage("path_b", answer_pipeline.path_b_event_payload(bundle["path_b"], trigger="structural"))
        else:
            bundle["path_b"] = {"triggered": False, "reason": "DI sufficient (stub)"}
            bundle["decision_state"] = answer_pipeline._state("DI_SUFFICIENT", False, False, "AUDIT")
        bundle["retrieval_summary"] = {"mode": "semantic", "retrievals": 1, "aggregation": "worst-of-n"}
        bundle["bundle_identity"] = answer_pipeline._identity(bundle)
        if on_stage:
            on_stage("decision_state", bundle["decision_state"])
        return bundle
    return _retrieve


PB_CALLS = []


def _pb_harness_stub(question, entities=None, n=None, query=None, query_source=None, triggered_by=None,
                     sources=None, retmax=None, search_plan=None, on_stage=None, existing_ids=None):
    """path_b_bundle con la firma C2 (search_plan, on_stage, existing_ids): emite search.* por on_stage y deja
    search_ledger — el contrato que runs.py consume."""
    PB_CALLS.append({"query": query, "query_source": query_source, "search_plan": search_plan,
                     "existing_ids": existing_ids, "on_stage": on_stage is not None})
    fams = list((search_plan or {}).get("families") or [])
    src = {"round": 1, "family": "europepmc", "status": "success", "n_found": 3, "n_new": 1, "elapsed_s": 0.01,
           "cache_hit": True, "query_sent": "wt1a AND zebrafish"}
    rd = {"round": 1, "trigger": "competence", "budget_s": 120, "elapsed_s": 0.02, "n_families": len(fams),
          "n_new_total": 1, "n_found_total": 3, "duplicates": [], "sources": [src]}
    if on_stage and search_plan is not None:
        from lib import search_harness as sh
        on_stage("search.plan", sh.plan_event_payload(search_plan))
        on_stage("search.source", sh.source_event_payload(src))
        on_stage("search.round", sh.round_event_payload(rd))
    block = {"triggered": True, "triggered_by": list(triggered_by or []),
             "papers": [{"evidence_id": "PMID:1001", "source": "europepmc", "selection_rank": 1,
                         "search_rec": {"pmid": "1001", "title": "wt1a in pronephros"},
                         "abstract": "wt1a marks the pronephros.", "text_excerpt": "wt1a marks the pronephros.",
                         "text_provenance": "abstract", "fetched": {"found": True, "full_text": False}}],
             "query_sent": query, "query_source": query_source, "n_results_by_source": {"europepmc": 1},
             "sources_requested": fams}
    if search_plan is not None:
        block["search_ledger"] = {"harness_version": "sh-1",
                                  "plan": {k: v for k, v in search_plan.items() if k != "query_builder"},
                                  "rounds": [rd], "families_default": list(search_plan.get("families_default") or []),
                                  "n_rounds": 1, "cap": search_plan.get("rounds_cap"), "round_budget_s": 120,
                                  "stop_reason": "n_new_total>0 after round 1", "n_new_total": 1, "n_items": 1}
    return block


def _pb_legacy_stub(question, entities=None, n=None, query=None, query_source=None, triggered_by=None,
                    sources=None, retmax=None):
    """path_b_bundle con la firma PRE-C2 — runs.py debe caer al camino de hoy y declararlo."""
    PB_CALLS.append({"legacy": True, "query": query})
    return {"triggered": True, "triggered_by": list(triggered_by or []), "papers": [], "query_sent": query,
            "query_source": query_source, "n_results_by_source": {}, "sources_requested": []}


def _panel(verdicts, fail_once=None, citation_support=None):
    """caller inyectado; fail_once = lens que falla en su PRIMER intento (reintento de composite_auditor E);
    citation_support = lista opcional que emite la lente evidence-grounding."""
    seen = {}

    def _caller(member, system, user_text):
        lens = member["lens"]
        seen[lens] = seen.get(lens, 0) + 1
        if fail_once == lens and seen[lens] == 1:
            raise RuntimeError("judge transport failure (simulated)")
        out = {"verdict": verdicts[lens], "caught": f"({lens})", "correction_applied": "", "confidence": 0.9,
               "reasons": []}
        if citation_support is not None and lens == "evidence-grounding":
            out["citation_support"] = citation_support
        return out, {"input_tokens": 10, "output_tokens": 5}
    return _caller


def _synth(conf_by_pass, evidence_cited="default", absence_kind="not-applicable", elicit_usage=None):
    def _s(question, evidence, pass_label):
        cited = ([{"kind": "di-chunk", "id": HIT["doc_id"]}] if evidence_cited == "default" else evidence_cited)
        out = {"direct_answer": "wt1a marks the zebrafish pronephros.", "stated_confidence": conf_by_pass.get(pass_label, 0.8),
               "confidence_source": "stated", "absence_kind": absence_kind, "gap_flags": [],
               "evidence_cited": cited, "search_query_en": "wt1a zebrafish pronephros",
               "alternatives_considered": ["wt1b: descartado"], "framework_applied": "Logic-LM",
               "framework_criterion": "for any task whose criteria are formalizable", "framework_reason": "r",
               "model": "stub-synth", "usage": {"input_tokens": 100, "output_tokens": 50}}
        if elicit_usage is not None:
            out["usage_elicitation"] = elicit_usage
            out["elicitation_state"] = "elicited"
        return out
    return _s


def _run(question, plan, synth, panel=None, entities=("wt1a",), structural=False, pb=_pb_harness_stub):
    answer_pipeline.retrieve = _fake_retrieve(structural)
    answer_pipeline.path_b_bundle = pb
    run_id = runs_mod.new_run("natalia", question, list(entities),
                              plan_json=json.dumps(plan) if plan is not None else None)
    claimed = db.claim_next_queued(worker_id="smoke-c1")
    assert claimed and claimed["run_id"] == run_id
    runs_mod.execute_run(claimed, synthesizer=synth, panel_caller=panel or _panel(ALL_A))
    row = db.get_run(run_id)
    ev = db.events_after(run_id, 0, 500)
    return row, json.loads(row["frozen_record_json"] or "null"), ev


def _types(ev):
    return [e["type"] for e in ev]


def _payloads(ev, t):
    return [e["payload"] for e in ev if e["type"] == t]


_orig_retrieve, _orig_pb = answer_pipeline.retrieve, answer_pipeline.path_b_bundle
PLAN_RUN = {**PLAN_OK, "question": "competent question", "thread_parent_run_id": None,
            "thread_parent_frozen_sha256": None}

# ---- (B) competente → pass1 candidata, SIN ronda, trigger null ------------------------------------------------
row, rec, ev = _run("competent question", PLAN_RUN, _synth({"pass1": 0.8}))
types = _types(ev)
check("(B) competente: eventos en orden pass1 → confidence.elicit{pass:1} → deterministic_gate{pass:1} → "
      "stage.competence (competent True, decided_by code) y NI search.plan NI pass2 NI path_b",
      row["state"] == "awaiting_closure"
      and types.index("stage.synthesize.pass1") < types.index("stage.confidence.elicit")
      < types.index("stage.deterministic_gate") < types.index("stage.competence") < types.index("stage.audit.start")
      and _payloads(ev, "stage.confidence.elicit")[0]["pass"] == "pass1"
      and _payloads(ev, "stage.deterministic_gate")[0]["pass"] == "pass1"
      and _payloads(ev, "stage.competence")[0]["competent"] is True
      and _payloads(ev, "stage.competence")[0]["decided_by"] == "code"
      and "stage.search.plan" not in types and "stage.synthesize.pass2" not in types and "stage.path_b" not in types
      and types.count("stage.deterministic_gate") == 1,
      json.dumps(types))
check("(G) competente congelado: contrato == runs.RENDER_CONTRACT_VERSION (el literal vive UNA vez, en smoke_run_pipeline), "
      "fallback.trigger null + trigger_legacy null + fb_meta.competence {competent True, decision_source}, frozen.competence "
      "íntegro, search_ledger rounds [] n_rounds 0 (CERO medido: no se buscó por decisión de la compuerta — corrector) state "
      "'not-requested…', deterministic_checks.{pass 'pass1', pass1_admissible True, competence_gate.competent True}, "
      "epistemic_summary.{competent True, n_search_rounds 0}, confidence.pass2 null",
      rec["render_contract_version"] == runs_mod.RENDER_CONTRACT_VERSION
      and rec["fallback"]["trigger"] is None and rec["fallback"]["fb_meta"]["trigger_legacy"] is None
      and rec["fallback"]["fb_meta"]["competence"]["competent"] is True
      and "competent" in rec["fallback"]["fb_meta"]["competence"]["decision_source"]
      and rec["competence"]["competent"] is True and rec["competence"]["module_version"] == competence.MODULE_VERSION == "cg-4"
      and rec["competence"]["decision"]["trigger"] is None
      and rec["search_ledger"]["rounds"] == [] and rec["search_ledger"]["n_rounds"] == 0
      and rec["search_ledger"]["state"].startswith("not-requested")
      and rec["search_ledger"]["cap"] == 2 and rec["search_ledger"]["families_default"] == [
          "europepmc", "pubmed", "zfin", "alliance_orthologs", "zfin_expression"]
      and rec["deterministic_checks"]["pass1_admissible"] is True
      and rec["deterministic_checks"]["competence_gate"]["competent"] is True
      and rec["deterministic_checks"]["pass"] == "pass1"
      and rec["confidence"]["pass2"] is None and rec["confidence"]["final"] == 0.8
      and json.loads(row["epistemic_summary_json"])["competent"] is True
      and json.loads(row["epistemic_summary_json"])["n_search_rounds"] == 0,
      json.dumps({k: rec[k] for k in ("fallback", "search_ledger")}, default=str)[:600])
tu = rec["token_usage"]
check("(F) by_stage con stub SIN usage_elicitation: synthesize_pass1 = 100/50 (modelo stub-synth), elicit_pass1 "
      "in/out null + state 'not-separable…' (no un 0 inventado), search 0 con nota, panel 40/20, plan declarado SIN usage del "
      "planner → 'plan-without-usage…' con in/out null (corrector: no 'no-plan', no 0), embed aparte; _sum == by_model → "
      "by_stage_sum_matches_by_model True",
      tu["by_stage"]["synthesize_pass1"] == {"in": 100, "out": 50, "model": "stub-synth"}
      and tu["by_stage"]["elicit_pass1"]["in"] is None
      and tu["by_stage"]["elicit_pass1"]["state"].startswith("not-separable")
      and tu["by_stage"]["search"]["in"] == 0 and "Layer 0" in tu["by_stage"]["search"]["note"]
      # ADR-0081 (H): panel gana by_model {reviewer: {in, out}} — se compara in/out y que Σ by_model == panel
      and {k: tu["by_stage"]["panel"][k] for k in ("in", "out")} == {"in": 40, "out": 20}
      and sum(m["in"] for m in tu["by_stage"]["panel"]["by_model"].values()) == 40
      and tu["by_stage"]["plan"]["state"].startswith("plan-without-usage") and tu["by_stage"]["plan"]["in"] is None
      and tu["by_stage"]["elicit_pass2"]["state"] == "not-run"
      and "tokens" in tu["by_stage"]["embed"]
      and tu["by_stage"]["_sum"] == {"in": 140, "out": 70, "rule": tu["by_stage"]["_sum"]["rule"]}
      and tu["input_tokens"] == 140 and tu["output_tokens"] == 70
      and tu["by_stage_sum_matches_by_model"] is True,
      json.dumps(tu["by_stage"], default=str)[:500])
cits = rec["citations"]
check("(E/G) support_state por cita (verify_output.support_state_for): la cita al hit de Ruta A con texto → "
      "resolved True, passage_delivered True, pertinent 'not-available (council not-applicable (no-ledger))' (ADR-0082 G.4: la "
      "corrida no trae ledger del consejo — el literal lleva la razón; el viejo sigue en summary.pertinent.literal), supported "
      "'not-evaluated' (sin citation_support), support_state 'passage_delivered' — peldaños separados, jamás fundidos; "
      "citations_support_summary {n 1, by_state con la escalera completa, state checked, pertinent objeto}",
      len(cits) == 1 and cits[0]["resolved"] is True and cits[0]["passage_delivered"] is True
      and cits[0]["pertinent"] == "not-available (council not-applicable (no-ledger))" and cits[0]["supported"] == "not-evaluated"
      and rec["citations_support_summary"]["pertinent"]["literal"] == "not-available (ADR-0082)"
      and rec["citations_support_summary"]["pertinent"]["n_not_available"] == 1
      and rec["council"]["state"] == "not-applicable (no-ledger)"
      and cits[0]["support_state"] == "passage_delivered"
      and rec["citations_support_summary"]["n"] == 1
      and rec["citations_support_summary"]["by_state"]["passage_delivered"] == 1
      and rec["citations_support_summary"]["by_state"]["unresolved"] == 0
      and rec["citations_support_summary"]["state"] == "checked",
      json.dumps(cits) + json.dumps(rec["citations_support_summary"]))

# ---- (B) NO competente (conf 0.3 < tau gatea POR DEFAULT, cg-3) → search.plan + harness + pass2 + gate{pass:2}
PB_CALLS.clear()
row, rec, ev = _run("thin question", {**PLAN_RUN, "question": "thin question"}, _synth({"pass1": 0.3, "pass2": 0.75}))
types = _types(ev)
sp = _payloads(ev, "stage.search.plan")
check("(B) no competente (default cg-3, sin env): stage.competence competent False reasons ['conf1_ge_tau'] → stage.search.plan "
      "(UNO, emitido por el harness vía on_stage, con families/rounds_cap y state 'built' — corrector: la forma es UNA) → "
      "stage.search.source → stage.search.round → stage.path_b trigger 'competence' → pass2 → elicit{pass2} → gate{pass2}",
      _payloads(ev, "stage.competence")[0]["competent"] is False
      and _payloads(ev, "stage.competence")[0]["reasons"] == ["conf1_ge_tau"]
      and types.count("stage.search.plan") == 1 and types.count("stage.search.round") == 1
      and types.count("stage.search.source") == 1
      and sp[0]["families"] and sp[0]["rounds_cap"] == 2 and sp[0]["plan_version"] == "1" and sp[0]["state"] == "built"
      and types.index("stage.competence") < types.index("stage.search.plan") < types.index("stage.search.round")
      < types.index("stage.path_b") < types.index("stage.synthesize.pass2")
      and _payloads(ev, "stage.path_b")[0]["trigger"] == "competence"
      and _payloads(ev, "stage.path_b")[0]["trigger_legacy"] == "confidence"
      and _payloads(ev, "stage.path_b")[0]["harness_used"] is True
      and [p["pass"] for p in _payloads(ev, "stage.confidence.elicit")] == ["pass1", "pass2"]
      and [p["pass"] for p in _payloads(ev, "stage.deterministic_gate")] == ["pass1", "pass2"],
      json.dumps(types))
check("(C→B) el harness recibió el plan REAL de search_harness.build_search_plan (plan_version 1, familias default, "
      "queries por familia, directives []) + query EN del sintetizador + existing_ids = doc_ids de Ruta A (dedup)",
      len(PB_CALLS) == 1 and PB_CALLS[0]["search_plan"]["plan_version"] == "1"
      and PB_CALLS[0]["search_plan"]["families"] == ["europepmc", "pubmed", "zfin", "alliance_orthologs", "zfin_expression"]
      and PB_CALLS[0]["search_plan"]["directives"] == [] and "queries" in PB_CALLS[0]["search_plan"]
      and PB_CALLS[0]["query"] == "wt1a zebrafish pronephros" and PB_CALLS[0]["query_source"] == "synthesizer"
      and PB_CALLS[0]["existing_ids"] == [HIT["doc_id"]] and PB_CALLS[0]["on_stage"] is True,
      json.dumps({k: v for k, v in PB_CALLS[0].items() if k != "search_plan"}))
check("(G) no competente congelado: fallback.trigger 'competence' + fb_meta.trigger_legacy 'confidence' (alias del "
      "literal viejo) + fb_meta.competence.reasons; frozen.search_ledger state 'harness', n_rounds 1 ≤ cap 2, rounds[0] "
      "sin items, plan sin query_builder, stop_reason; epistemic_summary.n_search_rounds 1; confidence.pass2 0.75 delta 0.45",
      rec["fallback"]["trigger"] == "competence" and rec["fallback"]["fb_meta"]["trigger_legacy"] == "confidence"
      and rec["fallback"]["fb_meta"]["competence"]["reasons"] == ["conf1_ge_tau"]
      and rec["fallback"]["fb_meta"]["trigger_vocabulary"] == runs_mod.TRIGGER_VOCABULARY
      and rec["fallback"]["fb_meta"]["trigger_decided_by"] == "code (competence-gate)"
      and rec["search_ledger"]["state"] == "harness" and rec["search_ledger"]["n_rounds"] == 1
      and rec["search_ledger"]["n_rounds"] <= rec["search_ledger"]["cap"] == 2
      and "items" not in rec["search_ledger"]["rounds"][0]
      and "query_builder" not in rec["search_ledger"]["plan"]
      and rec["search_ledger"]["stop_reason"] and rec["search_ledger"]["plan_state"] == "built"
      and json.loads(row["epistemic_summary_json"])["n_search_rounds"] == 1
      and json.loads(row["epistemic_summary_json"])["competent"] is False
      and rec["confidence"]["pass2"] == 0.75 and rec["confidence"]["delta"] == 0.45
      and rec["deterministic_checks"]["pass"] == "pass2" and rec["deterministic_checks"]["pass1_admissible"] is True
      and rec["audit"]["required_because"] == "FALLBACK_FETCHED",
      json.dumps(rec["search_ledger"], default=str)[:500])

# ---- (B) NO competente por INADMISIBLE (conf alta): la confianza no decide; trigger_legacy null -----------------
row, rec, ev = _run("uncited positive claim", {**PLAN_RUN, "question": "uncited positive claim"},
                    _synth({"pass1": 0.95, "pass2": 0.95}, evidence_cited=[]))
check("(B/E) afirmación positiva SIN citas con conf 0.95: gate{pass:1} inadmisible por positive_claim_requires_citations "
      "(checked, False) → competent False reasons ['admissible'] → trigger 'competence' con trigger_legacy null "
      "(la regla vieja NO habría disparado: la decisión es de la compuerta, no del escalar)",
      rec["deterministic_checks"]["pass1_admissible"] is False
      and _payloads(ev, "stage.deterministic_gate")[0]["positive_claim_requires_citations"] is False
      and _payloads(ev, "stage.deterministic_gate")[0]["positive_claim_requires_citations_state"] == "checked"
      and any("positive_claim_requires_citations" in r for r in _payloads(ev, "stage.deterministic_gate")[0]["reasons"])
      and rec["competence"]["competent"] is False and rec["competence"]["reasons"] == ["admissible"]
      and rec["fallback"]["trigger"] == "competence" and rec["fallback"]["fb_meta"]["trigger_legacy"] is None
      and rec["fallback"]["fb_meta"]["competence"]["decision_source"] == "competence-gate: not competent"
      and "stage.synthesize.pass2" in _types(ev),
      json.dumps(rec["deterministic_checks"]["positive_claim_requires_citations_evaluation"], default=str)[:300])

# ---- kill-switch --------------------------------------------------------------------------------------------
PB_CALLS.clear()
os.environ["WITT_COMPETENCE_GATE"] = "0"
row_k1, rec_k1, ev_k1 = _run("kill high", {**PLAN_RUN, "question": "kill high"}, _synth({"pass1": 0.8}))
row_k2, rec_k2, ev_k2 = _run("kill low", {**PLAN_RUN, "question": "kill low"}, _synth({"pass1": 0.3, "pass2": 0.6}))
os.environ.pop("WITT_COMPETENCE_GATE", None)
check("kill-switch WITT_COMPETENCE_GATE=0 (corrector): competent null + skipped_reason en stage.competence y fb_meta; la ruta "
      "cae al fallback por confianza de hoy — conf 0.8 ≥ tau → trigger null (sin ronda); conf 0.3 < tau → trigger 'confidence' "
      "(el literal de ADR-0051, válido SÓLO con competent null) + trigger_legacy 'confidence' + trigger_decided_by "
      "'model-confidence (legacy…)' + decision_source 'legacy-confidence (kill-switch…)' + Ruta B LEGADA: path_b_bundle SIN "
      "plan (PB_CALLS con search_plan None), harness_used False, search_ledger.state 'legacy-path-b (kill-switch "
      "WITT_COMPETENCE_GATE=0)', stage.search.plan state 'kill-switch WITT_COMPETENCE_GATE=0'; pass2 corre",
      rec_k1["competence"]["competent"] is None and "WITT_COMPETENCE_GATE=0" in rec_k1["competence"]["skipped_reason"]
      and rec_k1["fallback"]["trigger"] is None and "stage.synthesize.pass2" not in _types(ev_k1)
      and rec_k1["fallback"]["fb_meta"]["competence"]["skipped_reason"] == rec_k1["competence"]["skipped_reason"]
      and rec_k2["competence"]["competent"] is None
      and rec_k2["fallback"]["trigger"] == "confidence" and rec_k2["fallback"]["fb_meta"]["trigger_legacy"] == "confidence"
      and rec_k2["fallback"]["fb_meta"]["trigger_decided_by"].startswith("model-confidence (legacy")
      and rec_k2["fallback"]["fb_meta"]["competence"]["decision_source"].startswith("legacy-confidence (kill-switch")
      and rec_k2["search_ledger"]["state"] == "legacy-path-b (kill-switch WITT_COMPETENCE_GATE=0)"
      and rec_k2["search_ledger"]["n_rounds"] is None
      and _payloads(ev_k2, "stage.path_b")[0]["harness_used"] is False
      and _payloads(ev_k2, "stage.path_b")[0]["trigger"] == "confidence"
      and _payloads(ev_k2, "stage.search.plan")[0]["state"] == "kill-switch WITT_COMPETENCE_GATE=0"
      and "stage.search.round" not in _types(ev_k2)
      and PB_CALLS and PB_CALLS[-1]["search_plan"] is None
      and "stage.synthesize.pass2" in _types(ev_k2)
      and json.loads(row_k1["epistemic_summary_json"])["competent"] is None,
      rec_k2["fallback"]["fb_meta"]["competence"]["decision_source"])

# ---- sin plan (POST /runs directo) -----------------------------------------------------------------------------
row, rec, ev = _run("no plan question", None, _synth({"pass1": 0.9, "pass2": 0.9}))
check("sin plan (POST /runs directo): route/niches False con reason 'no-plan' → not-competent DECLARADO → ronda + pass2 "
      "aunque conf 0.9 (trigger 'competence', trigger_legacy null); calibration n None 'no-niches'; by_stage.plan 'no-plan'",
      rec["competence"]["competent"] is False
      and rec["competence"]["reasons"] == ["route_evidence_run", "niches_nonempty"]
      and rec["competence"]["components"]["route_evidence_run"]["reason"] == "no-plan"
      and rec["competence"]["components"]["calibration_coverage"]["n_closed_rated"] is None
      and rec["competence"]["components"]["calibration_coverage"]["reason"] == "no-niches"
      and rec["fallback"]["trigger"] == "competence" and rec["fallback"]["fb_meta"]["trigger_legacy"] is None
      and "stage.synthesize.pass2" in _types(ev) and rec["plan_declared"] is False
      and rec["token_usage"]["by_stage"]["plan"]["state"] == "no-plan")

# ---- estructural: manda sobre la compuerta, trigger 'structural' como hoy -------------------------------------
row, rec, ev = _run("no coverage", {**PLAN_RUN, "question": "no coverage"}, _synth({"pass1": 0.9, "pass2": 0.9}),
                    structural=True)
check("estructural (assess_sufficiency dentro de retrieve): trigger 'structural' + trigger_legacy 'structural'; "
      "competence components.structural_not_fired False (competent False declarado); SIN stage.search.plan (la Ruta "
      "B ya corrió en retrieve); pass2 corre; search_ledger state 'not-requested…'",
      rec["fallback"]["trigger"] == "structural" and rec["fallback"]["fb_meta"]["trigger_legacy"] == "structural"
      and rec["competence"]["competent"] is False
      and rec["competence"]["components"]["structural_not_fired"]["value"] is False
      and "structural_not_fired" in rec["competence"]["reasons"]
      and "stage.search.plan" not in _types(ev) and "stage.synthesize.pass2" in _types(ev)
      and rec["search_ledger"]["state"].startswith("not-requested")
      and _payloads(ev, "stage.path_b")[0]["trigger"] == "structural")

# ---- ruta store-consultation → not_applicable; la regla por confianza de hoy decide ---------------------------
row, rec, ev = _run("que hay en la DI", {**PLAN_STORE, "question": "que hay en la DI", "thread_parent_run_id": None,
                                          "thread_parent_frozen_sha256": None}, _synth({"pass1": 0.8}))
check("route store-consultation: competence.not_applicable True, competent null, skipped_reason; conf 0.8 → sin ronda, "
      "trigger null (n_rounds 0: no se buscó); decision_source 'legacy-confidence (route store-consultation…)'",
      rec["competence"]["not_applicable"] is True and rec["competence"]["competent"] is None
      and rec["fallback"]["trigger"] is None and rec["search_ledger"]["n_rounds"] == 0
      and rec["fallback"]["fb_meta"]["competence"]["not_applicable"] is True
      and "store-consultation" in rec["fallback"]["fb_meta"]["competence"]["decision_source"]
      and "stage.synthesize.pass2" not in _types(ev))
# corrector ADR-0080 (paridad webapp 2026-09-15): la MISMA ruta con conf 0.3 < tau → la regla legada dispara y el plan-sobre
# declara plan_state 'not-applicable (<skipped_reason>)' — un literal con PREFIJO del vocabulario real (G)
PB_CALLS.clear()
row_sl, rec_sl, ev_sl = _run("que hay en la DI baja", {**PLAN_STORE, "question": "que hay en la DI baja",
                                                       "thread_parent_run_id": None, "thread_parent_frozen_sha256": None},
                             _synth({"pass1": 0.3, "pass2": 0.6}))
check("(G, corrector paridad webapp) route store-consultation + conf 0.3 < tau: trigger 'confidence' (competent null), Ruta B LEGADA "
      "(path_b_bundle SIN plan) y plan_state 'not-applicable (route store-consultation: …)' — el mismo literal en "
      "search_ledger.plan_state, search_ledger.plan.state y stage.search.plan.state; search_ledger.state 'legacy-path-b "
      "(not-applicable (…))'; n_rounds null (el harness no midió)",
      rec_sl["competence"]["competent"] is None and rec_sl["fallback"]["trigger"] == "confidence"
      and rec_sl["search_ledger"]["plan_state"].startswith("not-applicable (route store-consultation")
      and rec_sl["search_ledger"]["plan"]["state"] == rec_sl["search_ledger"]["plan_state"]
      and _payloads(ev_sl, "stage.search.plan")[0]["state"] == rec_sl["search_ledger"]["plan_state"]
      and rec_sl["search_ledger"]["state"] == f"legacy-path-b ({rec_sl['search_ledger']['plan_state']})"
      and rec_sl["search_ledger"]["n_rounds"] is None and PB_CALLS and PB_CALLS[-1]["search_plan"] is None
      and "stage.synthesize.pass2" in _types(ev_sl),
      rec_sl["search_ledger"]["plan_state"])

# ---- calibration gating ON en la corrida real: ORÍGENES (corrector) + n=1 (cal-1) < min 10 → no competente ----------
os.environ["WITT_CG_REQUIRE_CALIBRATION"] = "1"
row0, rec0, ev0 = _run("cal gated prod", {**PLAN_RUN, "question": "cal gated prod"}, _synth({"pass1": 0.9, "pass2": 0.9}))
os.environ["WITT_CG_CALIBRATION_ORIGINS"] = "smoke"
row, rec, ev = _run("cal gated", {**PLAN_RUN, "question": "cal gated"}, _synth({"pass1": 0.9, "pass2": 0.9}))
os.environ["WITT_COMPETENCE_MIN_HISTORY"] = "1"
row2, rec2, ev2 = _run("cal ok", {**PLAN_RUN, "question": "cal ok"}, _synth({"pass1": 0.9}))
os.environ.pop("WITT_CG_REQUIRE_CALIBRATION", None)
os.environ.pop("WITT_COMPETENCE_MIN_HISTORY", None)
os.environ.pop("WITT_CG_CALIBRATION_ORIGINS", None)
_cal0 = rec0["competence"]["components"]["calibration_coverage"]
_cal0_ev = _payloads(ev0, "stage.competence")[0]["components"]["calibration_coverage"]
_cal1 = rec["competence"]["components"]["calibration_coverage"]
check("calibration gating ON en execute_run (corrector): por DEFAULT la cobertura cuenta SÓLO origin 'production' "
      "(WITT_CG_CALIBRATION_ORIGINS default-unset) → las corridas cal-* de este gate (origin smoke) quedan CONTADAS FUERA: "
      "n 0 → no competente ['calibration_coverage']; con WITT_CG_CALIBRATION_ORIGINS=smoke → n 1 (cal-1) < 10 insuficiente → "
      "ronda; con WITT_COMPETENCE_MIN_HISTORY=1 → n 1 ≥ 1 → competente sin ronda; min_required_source declarado. "
      "Corrector paridad webapp: el componente (y el evento stage.competence) LLEVAN include_origins ['production'] + "
      "include_origins_source 'default-unset:WITT_CG_CALIBRATION_ORIGINS'; con la env → ['smoke'] + 'env:WITT_CG_CALIBRATION_ORIGINS' "
      "(aserción DURA: antes el check era condicional a la presencia de la llave)",
      _cal0["n_closed_rated"] == 0 and _cal0["gating"] is True and rec0["competence"]["reasons"] == ["calibration_coverage"]
      and _cal0["include_origins"] == ["production"] and _cal0["include_origins_source"] == "default-unset:WITT_CG_CALIBRATION_ORIGINS"
      and _cal0_ev["include_origins"] == ["production"] and _cal0_ev["include_origins_source"] == _cal0["include_origins_source"]
      and _cal1["n_closed_rated"] == 1 and _cal1["gating"] is True
      and _cal1["include_origins"] == ["smoke"] and _cal1["include_origins_source"] == "env:WITT_CG_CALIBRATION_ORIGINS"
      and rec["competence"]["reasons"] == ["calibration_coverage"] and rec["fallback"]["trigger"] == "competence"
      and rec2["competence"]["competent"] is True and rec2["fallback"]["trigger"] is None
      and rec2["competence"]["components"]["calibration_coverage"]["min_required"] == 1
      and rec2["competence"]["components"]["calibration_coverage"]["include_origins"] == ["smoke"],
      json.dumps([_cal0, _cal1]))

# ---- harness NO disponible / path_b_bundle con firma vieja → declarado, la Ruta B corre por el camino de hoy -----
PB_CALLS.clear()
_sh = runs_mod.search_harness
runs_mod.search_harness = None
# cg-3: conf 0.2 < tau gatea por default → estas corridas piden la ronda sin env alguna
row_u, rec_u, ev_u = _run("harness gone", {**PLAN_RUN, "question": "harness gone"}, _synth({"pass1": 0.2, "pass2": 0.5}),
                          pb=_pb_legacy_stub)
runs_mod.search_harness = _sh
PB_CALLS.clear()
row_l, rec_l, ev_l = _run("legacy pb", {**PLAN_RUN, "question": "legacy pb"}, _synth({"pass1": 0.2, "pass2": 0.5}),
                          pb=_pb_legacy_stub)
check("harness ausente (search_harness None): stage.search.plan emitido por runs con state 'harness-unavailable', "
      "path_b legacy llamado, search_ledger.state 'legacy-path-b (harness-unavailable)' rounds [] n_rounds null; "
      "path_b_bundle con firma vieja y plan REAL → state 'legacy-path-b (path_b_bundle without search_plan…)', "
      "plan_state 'built', stage.search.plan declara path_b_bundle_accepts []",
      _payloads(ev_u, "stage.search.plan")[0]["state"] == "harness-unavailable"
      and rec_u["search_ledger"]["state"] == "legacy-path-b (harness-unavailable)"
      and rec_u["search_ledger"]["rounds"] == [] and rec_u["search_ledger"]["n_rounds"] is None
      and rec_u["fallback"]["trigger"] == "competence" and "stage.synthesize.pass2" in _types(ev_u)
      and _payloads(ev_u, "stage.path_b")[0]["harness_used"] is False
      and rec_l["search_ledger"]["state"].startswith("legacy-path-b (path_b_bundle without search_plan")
      and rec_l["search_ledger"]["plan_state"] == "built" and rec_l["search_ledger"]["plan"]["plan_version"] == "1"
      and _payloads(ev_l, "stage.search.plan")[0]["path_b_bundle_accepts"] == []
      and len(PB_CALLS) == 1 and PB_CALLS[0].get("legacy") is True,
      json.dumps([rec_u["search_ledger"]["state"], rec_l["search_ledger"]["state"]]))

# ---- (G, corrector paridad webapp 2026-09-15) vocabulario REAL de plan_state: exactos + prefijos, declarado y medido ----
_sh_real = runs_mod.search_harness


class _HarnessBoom:
    @staticmethod
    def build_search_plan(*a, **kw):
        raise RuntimeError("plan exploded (simulated)")


runs_mod.search_harness = _HarnessBoom
plan_err, state_err = runs_mod._build_search_plan("q", ["wt1a"], None, runs_mod._search_config())
runs_mod.search_harness = None
plan_un, state_un = runs_mod._build_search_plan("q", ["wt1a"], None, runs_mod._search_config())
runs_mod.search_harness = _sh_real
_ps_seen = sorted({r["search_ledger"]["plan_state"] for r in (rec_k1, rec_k2, rec_sl, rec_u, rec_l, rec0, rec2)}
                  | {state_err, plan_err["state"], state_un, plan_un["state"]}
                  | {(r["search_ledger"].get("plan") or {}).get("state") for r in (rec_k2, rec_sl, rec_u)})
check("(G, corrector paridad webapp) plan_state: el código emite MÁS que los 4 literales que ADR-0080 declaraba — 'kill-switch "
      "WITT_COMPETENCE_GATE=0', 'not-applicable (<skipped_reason>)', y en el plan-sobre 'error: <tipo>: <msg>' / "
      "'harness-unavailable (<qué faltó>)' junto a los exactos 'error' / 'harness-unavailable' de la tupla; runs declara el "
      "vocabulario REAL (SEARCH_PLAN_STATES_EXACT + SEARCH_PLAN_STATE_PREFIXES), lo congela en search_ledger.plan_state_vocabulary "
      "y plan_state_in_vocabulary lo valida: TODOS los literales medidos en este gate pasan; 'legacy-path-b (built)' y None no",
      all(runs_mod.plan_state_in_vocabulary(s) for s in _ps_seen)
      and {"built", "not-requested", "kill-switch WITT_COMPETENCE_GATE=0", "harness-unavailable", "error"} <= set(_ps_seen)
      and any(s.startswith("not-applicable (") for s in _ps_seen)
      and state_err == "error" and plan_err["state"].startswith("error: RuntimeError: plan exploded")
      and state_un == "harness-unavailable" and plan_un["state"].startswith("harness-unavailable (")
      and all(r["search_ledger"]["plan_state_vocabulary"] == runs_mod.SEARCH_PLAN_STATE_VOCABULARY
              for r in (rec_k1, rec_k2, rec_sl, rec_u, rec_l, rec0, rec2))
      and runs_mod.SEARCH_PLAN_STATE_VOCABULARY["exact"] == list(runs_mod.SEARCH_PLAN_STATES_EXACT)
      and runs_mod.SEARCH_PLAN_STATE_VOCABULARY["prefixes"] == list(runs_mod.SEARCH_PLAN_STATE_PREFIXES)
      and not runs_mod.plan_state_in_vocabulary("legacy-path-b (built)") and not runs_mod.plan_state_in_vocabulary(None),
      json.dumps(_ps_seen))

# ---- (F) by_stage con elicitación SEPARADA + (E) reintento por juez + citation_support ---------------------------
# cg-3: conf 0.3 < tau gatea por default → la ronda (pass2) llega sin env alguna
row, rec, ev = _run("elicit split", {**PLAN_RUN, "question": "elicit split"},
                    _synth({"pass1": 0.3, "pass2": 0.7}, elicit_usage={"input_tokens": 30, "output_tokens": 5}),
                    panel=_panel(ALL_A, fail_once="overclaim", citation_support=[{"n": 1, "verdict": "supported"}]))
tu = rec["token_usage"]
judge_ev = _payloads(ev, "stage.audit.judge")
check("(F) by_stage con usage_elicitation: synthesize_pass1 70/45 + elicit_pass1 30/5 (measured) = usage 100/50; "
      "igual pass2; el evento stage.synthesize.pass1 lleva usage {in 70, out 45, model} y el elicit {in 30, out 5, model null "
      "DECLARADO: el stub no reporta elicitation_model y el del sintetizador JAMÁS se copia en su lugar — corrector ADR-0081}; "
      "_sum == by_model (200/100 síntesis + 50/25 panel con 5 llamadas) → True",
      tu["by_stage"]["synthesize_pass1"] == {"in": 70, "out": 45, "model": "stub-synth"}
      and tu["by_stage"]["elicit_pass1"] == {"in": 30, "out": 5, "state": "measured", "model": None}
      and tu["by_stage"]["synthesize_pass2"]["in"] == 70 and tu["by_stage"]["elicit_pass2"]["in"] == 30
      and _payloads(ev, "stage.synthesize.pass1")[0]["usage"] == {"in": 70, "out": 45, "model": "stub-synth"}
      and _payloads(ev, "stage.confidence.elicit")[0]["usage"] == {"in": 30, "out": 5, "model": None}
      and _payloads(ev, "stage.confidence.elicit")[0]["elicitation_state"] == "elicited"
      # ADR-0081 (H): panel gana by_model {reviewer: {in, out}} — se compara in/out y que Σ by_model == panel
      and {k: tu["by_stage"]["panel"][k] for k in ("in", "out")} == {"in": 40, "out": 20}
      and sum(m["in"] for m in tu["by_stage"]["panel"]["by_model"].values()) == 40
      and tu["by_stage"]["_sum"]["in"] == tu["input_tokens"] == 240
      and tu["by_stage"]["_sum"]["out"] == tu["output_tokens"] == 120
      and tu["by_stage_sum_matches_by_model"] is True,
      json.dumps(tu["by_stage"], default=str)[:400])
over = [r for r in rec["audit"]["panel"] if r["lens"] == "overclaim"][0]
check("(E) reintento por juez (composite_auditor, WITT_JUDGE_RETRIES default 1) DECLARADO en la traza: 5 eventos "
      "stage.audit.judge (4 jueces + 1 reintento), el segundo intento de 'overclaim' lleva attempt 2 / retries_judge 1; "
      "la fila del juez trae retries_judge 1 y attempts [errored, ok]; el veredicto NO se fabrica (APPROVE real)",
      len(judge_ev) == 5
      and [e["attempt"] for e in judge_ev if e["lens"] == "overclaim"] == [1, 2]
      and [e["retries_judge"] for e in judge_ev if e["lens"] == "overclaim"] == [0, 1]
      and all(e["retries_judge"] == 0 for e in judge_ev if e["lens"] != "overclaim")
      # corrector paridad webapp: "intento N de M" — max_attempts == 1 + WITT_JUDGE_RETRIES (misma fuente que audit.judge_retries)
      and all(e["max_attempts"] == 2 == 1 + rec["audit"]["judge_retries"]["value"]
              and e["max_attempts_source"] == rec["audit"]["judge_retries"]["source"] == "default-unset:WITT_JUDGE_RETRIES"
              for e in judge_ev)
      and over.get("retries_judge") == 1 and len(over.get("attempts") or []) == 2
      and over["verdict"] == "APPROVE" and rec["audit"]["verdict"] == "APPROVE",
      json.dumps({k: over.get(k) for k in ("retries_judge", "attempts")}, default=str))
check("(E/G) citation_support del juez evidence-grounding eleva la cita: supported 'supported' + support_state "
      "'supported' (pasaje entregado); summary.by_state.supported 1, grounding_rows 1",
      rec["citations"][0]["supported"] == "supported" and rec["citations"][0]["support_state"] == "supported"
      and rec["citations_support_summary"]["by_state"]["supported"] == 1
      and rec["citations_support_summary"]["grounding_rows"] == 1,
      json.dumps(rec["citations"]))

# ---- escalera: cita NO resuelta + evidence_cited ausente (tres estados) ----------------------------------------
row, rec, ev = _run("unresolved cite", {**PLAN_RUN, "question": "unresolved cite"},
                    _synth({"pass1": 0.9}, evidence_cited=[{"kind": "paper", "id": "PMID:99999999"}]))
check("(G) cita a un id que NO está en el bundle → resolved False, support_state 'unresolved' (n_valid 1: el "
      "predicado de citas pasa — positive_claim_requires_citations True — y la compuerta es competente: la "
      "resolución de la cita es otro peldaño, no se funde con la admisibilidad)",
      rec["citations"][0]["resolved"] is False and rec["citations"][0]["support_state"] == "unresolved"
      and rec["citations_support_summary"]["by_state"]["unresolved"] == 1
      and rec["deterministic_checks"]["positive_claim_requires_citations"] is True
      and rec["competence"]["competent"] is True,
      json.dumps(rec["citations"]))

# ---- limpieza ----------------------------------------------------------------------------------------------------
answer_pipeline.retrieve, answer_pipeline.path_b_bundle = _orig_retrieve, _orig_pb

n_ok, n = sum(CHECKS), len(CHECKS)
print(f"\n{n_ok}/{n} checks PASS")
sys.exit(0 if n_ok == n else 1)

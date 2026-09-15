"""
competence.py — la COMPUERTA DE COMPETENCIA de una corrida (ADR-0080, rebanada C1).

Decide, POR CÓDIGO, si la pasada 1 (DI-only) basta como candidata o si la corrida debe buscar afuera
(rondas del harness, ADR-0080 (C)). Sustituye al disparador ÚNICO por confianza de ADR-0051 (`pass1 < tau`) por
una CONJUNCIÓN de componentes deterministas:

    conf1 >= tau ∧ admissible ∧ route == 'evidence-run' ∧ niches != [] ∧ ¬structural_fired
    ∧ (calibration_coverage.sufficient SI WITT_CG_REQUIRE_CALIBRATION=1)

La confianza de la pasada 1 GATEA POR DEFAULT (`cg-3`, corrección del orquestador 2026-09-15). Doctrina: ADR-0051
eligió `pass1 < tau` como DECISOR de la Ruta B por encima del chequeo estructural (medido con run_held_out
--conf-threshold 0.5; el estructural se documentó engañable por cualquier chunk presente) y ADR-0065 hizo del escalar
ELICITADO por CONF_TOOL la medición autoritativa — no es prosa del modelo, es un escalar medido y calibrable
(ADR-0064/0075). Lo que el brief v3 §4/§7 prohíbe como self-report es que el modelo se declare competente en prosa o
audite su propio trabajo; un escalar medido participando en una conjunción que decide CÓDIGO no es eso. El `cg-2`
(corrector de ADR-0080) lo había vuelto informativo por default y con ello una corrida con conf1 0.15 y suficiencia
estructural quedaba 'competente' y saltaba la búsqueda externa — la regresión exacta del caso real a361f566
(0.15 → Ruta B → 0.86, ADR-0059). Por eso se REVIRTIÓ. El operador puede apagarlo con `WITT_CG_CONF_COMPONENT=0`
(declarado en `config.conf_component_gating` y en `components.conf1_ge_tau.gating`); la nota de `self_report` dice
literalmente si participa o no, según `gating` — el registro no miente.

Puro y stdlib: sin BD, sin red, sin import del servicio. `calibration_coverage` llega ya calculado
(db.calibration_coverage) — este módulo sólo lee su `sufficient`. Se prueba sin motor (smoke_competence.py).

Doctrina heredada: TRES estados (competent True | False | None-con-skipped_reason); lo ausente se DECLARA
(un componente sin insumo es False con `reason`, nunca un True vacío); cada cifra con clase (`self_report.class
'model-judgment'`; `calibration_coverage` es medición de la BD). El kill-switch (WITT_COMPETENCE_GATE=0)
deja `competent: None` + `skipped_reason` y la corrida cae al fallback por confianza de hoy (runs.py).
"""
import os

# Historia de MODULE_VERSION:
#   cg-1  — conf1_ge_tau gateaba SIEMPRE (sin env que lo apagara).
#   cg-2  — [corrector ADR-0080] informativo por default (CONF_COMPONENT_DEFAULT "0"), gateaba sólo con env=1 — REVERTIDO:
#           dejaba pasar conf1 0.15 con suficiencia estructural (regresión del caso a361f566, ADR-0059).
#   cg-3  — [orquestador 2026-09-15] gatea por default (CONF_COMPONENT_DEFAULT "1", doctrina ADR-0051/0065); apagable
#           SÓLO con WITT_CG_CONF_COMPONENT=0 declarado (config.conf_component_gating False, fuera de conjunction).
MODULE_VERSION = "cg-3"
DECIDED_BY = "code"

# --- env vars del ADR (default declarado en código; el efectivo viaja en el bloque) ----------------------
GATE_ENV = "WITT_COMPETENCE_GATE"                 # 1 (default) | 0 = kill-switch
REQUIRE_CALIBRATION_ENV = "WITT_CG_REQUIRE_CALIBRATION"   # 0 (default) | 1 = calibration_coverage entra a la conjunción
CONF_COMPONENT_ENV = "WITT_CG_CONF_COMPONENT"      # 1 (default, cg-3) = conf1_ge_tau (escalar elicitado, ADR-0065) gatea | 0 = informativo
MIN_HISTORY_ENV = "WITT_COMPETENCE_MIN_HISTORY"   # 10 (default): corridas CLOSED con rating que intersecan los nichos
TAU_ENV = "WITT_FALLBACK_CONF_TAU"                # 0.5 (default; el mismo tau de ADR-0051 — runs.FALLBACK_CONF_TAU)
GATE_DEFAULT = "1"
REQUIRE_CALIBRATION_DEFAULT = "0"
CONF_COMPONENT_DEFAULT = "1"
MIN_HISTORY_DEFAULT = 10
TAU_DEFAULT = 0.5

ROUTE_EVIDENCE_RUN = "evidence-run"
ROUTE_STORE_CONSULTATION = "store-consultation"

# Orden CANÓNICO de la conjunción — el bloque lista `components` en este orden y `reasons` cita estos nombres.
COMPONENT_ORDER = ("conf1_ge_tau", "admissible", "route_evidence_run", "niches_nonempty",
                   "structural_not_fired", "calibration_coverage", "council_uncovered_must")


def _env_int_tolerante(env, name, default):
    """(valor, fuente) — mismo patrón que runs._env_int_tolerante (ADR-0078): env vacía / no numérica /
    <= 0 → default DECLARADO, jamás un int() que tumbe el proceso."""
    raw = (env.get(name) or "").strip()
    if not raw:
        return default, f"default-unset:{name}"
    try:
        v = int(raw)
    except ValueError:
        return default, f"default-invalid-env:{name}"
    return (v, f"env:{name}") if v > 0 else (default, f"default-invalid-env:{name}")


def _env_float_tolerante(env, name, default):
    raw = (env.get(name) or "").strip()
    if not raw:
        return default, f"default-unset:{name}"
    try:
        v = float(raw)
    except ValueError:
        return default, f"default-invalid-env:{name}"
    return (v, f"env:{name}") if 0.0 <= v <= 1.0 else (default, f"default-invalid-env:{name}")


def env_config(env=None):
    """La configuración EFECTIVA de la compuerta, con la fuente de cada valor (ADR-0080). `env` es un
    mapping (default os.environ) para que el gate la pruebe sin tocar el proceso."""
    env = os.environ if env is None else env
    gate_raw = (env.get(GATE_ENV) or GATE_DEFAULT).strip() or GATE_DEFAULT
    cal_raw = (env.get(REQUIRE_CALIBRATION_ENV) or REQUIRE_CALIBRATION_DEFAULT).strip() or REQUIRE_CALIBRATION_DEFAULT
    conf_raw = (env.get(CONF_COMPONENT_ENV) or CONF_COMPONENT_DEFAULT).strip() or CONF_COMPONENT_DEFAULT
    min_hist, min_src = _env_int_tolerante(env, MIN_HISTORY_ENV, MIN_HISTORY_DEFAULT)
    tau, tau_src = _env_float_tolerante(env, TAU_ENV, TAU_DEFAULT)
    return {
        "gate_enabled": gate_raw != "0",
        "gate_env": {GATE_ENV: gate_raw, "default": GATE_DEFAULT},
        "require_calibration": cal_raw == "1",
        "require_calibration_env": {REQUIRE_CALIBRATION_ENV: cal_raw, "default": REQUIRE_CALIBRATION_DEFAULT},
        "conf_component_gating": conf_raw == "1",
        "conf_component_env": {CONF_COMPONENT_ENV: conf_raw, "default": CONF_COMPONENT_DEFAULT},
        "min_history": min_hist, "min_history_source": min_src,
        "tau": tau, "tau_source": tau_src,
    }


def plan_route(plan):
    """La ruta que el planner juzgó (plan.judgment.route) o None declarado (sin plan / juicio errado)."""
    if not isinstance(plan, dict):
        return None
    j = plan.get("judgment") or {}
    if j.get("state") != "declared":
        return None
    return j.get("route")


def plan_niches(plan):
    """Códigos de nicho del plan (plan.judgment.niches[].code) — lista ordenada, [] cuando no consta.
    Devuelve None (ausente declarado) cuando NO hay plan o el juicio no se declaró."""
    if not isinstance(plan, dict):
        return None
    j = plan.get("judgment") or {}
    if j.get("state") != "declared":
        return None
    out = []
    for n in j.get("niches") or []:
        code = n.get("code") if isinstance(n, dict) else n
        if code and str(code).strip():
            out.append(str(code).strip())
    return sorted(set(out))


def _calibration_component(calibration_coverage, min_required, gating):
    cc = calibration_coverage if isinstance(calibration_coverage, dict) else {}
    n = cc.get("n")
    comp = {"n_closed_rated": n if isinstance(n, int) else None,
            "min_required": cc.get("min_required", min_required),
            "sufficient": bool(cc.get("sufficient")),
            "gating": bool(gating),
            "class": "medicion (db.calibration_coverage: corridas CLOSED con >=1 rating cuyos nichos intersecan el plan)"}
    if not isinstance(calibration_coverage, dict):
        comp["reason"] = "calibration_coverage absent (not computed)"
    elif cc.get("reason"):
        comp["reason"] = cc["reason"]
    # corrector ADR-0080 (paridad webapp 2026-09-15): el filtro por procedencia que runs._calibration_origins puso
    # en la cobertura (include_origins lista | 'all', include_origins_source 'default-unset:…' | 'env:…') viaja al
    # componente tal cual — ADR-0080 (A) lo promete; ausente en la cobertura → ausente aquí (nada se rellena)
    for k in ("include_origins", "include_origins_source"):
        if k in cc:
            comp[k] = cc[k]
    return comp


def evaluate(conf1, admissible_pass1, plan, structural_fired, calibration_coverage,
             council_coverage=None, env=None, tau=None):
    """(A) La compuerta. Devuelve el BLOQUE completo que viaja al evento stage.competence y a
    frozen.competence:

        {competent: bool|None, not_applicable: bool, components: {...}, reasons: [nombre de componente que
         falló], decided_by: 'code', module_version: 'cg-3', config: {...},
         self_report: {stated_confidence, class: 'model-judgment', note}, skipped_reason?}

    Conjunción (cg-3) = conf1 >= tau ∧ admissible ∧ route == 'evidence-run' ∧ niches != [] ∧ ¬structural_fired
    ∧ (calibration_coverage.sufficient SI WITT_CG_REQUIRE_CALIBRATION=1).
    Componente ausente → False con reason (`conf1` None → 'conf1-absent': una confianza que no llegó NO es competencia).
    `conf1_ge_tau` gatea POR DEFAULT (ADR-0051 lo eligió decisor sobre el estructural; ADR-0065 lo hizo escalar
    elicitado y medido); con WITT_CG_CONF_COMPONENT=0 declarado pasa a informativo (`gating False`, fuera de
    `conjunction`) y la nota de `self_report` lo dice literalmente.
    · route == 'store-consultation' → not_applicable True, competent None (no hay compuerta que aplicar).
    · kill-switch (WITT_COMPETENCE_GATE=0) → competent None + skipped_reason; los componentes se calculan y
      viajan igual (informativos), la decisión la toma el fallback por confianza de hoy (runs.py).
    · council_uncovered_must: 'not-available (ADR-0082)', gating False — la llave existe desde hoy para que
      el contrato no cambie de forma cuando el consejo aterrice.
    `tau` None → WITT_FALLBACK_CONF_TAU (default 0.5), la misma constante de runs.FALLBACK_CONF_TAU."""
    cfg = env_config(env)
    # corrector ADR-0080 (paridad webapp 2026-09-15): τ y su fuente se resuelven UNA vez — components.conf1_ge_tau.tau_source
    # y config.tau_source decían cosas distintas ('default-unset:…' vs 'caller') para el MISMO τ del llamador
    tau_from_caller = isinstance(tau, (int, float))
    tau_eff = float(tau) if tau_from_caller else cfg["tau"]
    tau_source = "caller" if tau_from_caller else cfg["tau_source"]
    route = plan_route(plan)
    niches = plan_niches(plan)
    has_plan = isinstance(plan, dict)
    judged = has_plan and ((plan.get("judgment") or {}).get("state") == "declared")

    conf_ok = isinstance(conf1, (int, float)) and conf1 >= tau_eff
    comp_conf = {"value": bool(conf_ok), "conf1": conf1, "tau": tau_eff, "tau_source": tau_source,
                 "gating": bool(cfg["conf_component_gating"]), "class": "model-judgment (stated_confidence)"}
    if not isinstance(conf1, (int, float)):
        comp_conf["reason"] = "conf1-absent"

    comp_adm = {"value": admissible_pass1 is True}
    if admissible_pass1 is None:
        comp_adm["reason"] = "admissible-not-measured"
    elif admissible_pass1 is False:
        comp_adm["reason"] = "pass1 inadmissible (verify_output)"

    if not has_plan:
        plan_reason = "no-plan"
    elif not judged:
        plan_reason = f"plan.judgment.state={(plan.get('judgment') or {}).get('state')!r} (not declared)"
    else:
        plan_reason = None
    comp_route = {"value": route == ROUTE_EVIDENCE_RUN, "route": route}
    if plan_reason:
        comp_route["reason"] = plan_reason
    elif route != ROUTE_EVIDENCE_RUN:
        comp_route["reason"] = f"route={route!r}"
    comp_niches = {"value": bool(niches), "niches": niches}
    if plan_reason:
        comp_niches["reason"] = plan_reason
    elif not niches:
        comp_niches["reason"] = "niches=[] (out of scope declared by planner)"

    comp_struct = {"value": not bool(structural_fired), "structural_fired": bool(structural_fired)}
    if structural_fired:
        comp_struct["reason"] = "structural insufficiency already fetched Path B (assess_sufficiency)"

    comp_cal = _calibration_component(calibration_coverage, cfg["min_history"], cfg["require_calibration"])
    comp_council = {"value": None, "state": "not-available (ADR-0082)", "gating": False}
    if council_coverage is not None:
        comp_council["received"] = council_coverage   # se conserva crudo, no se interpreta hasta ADR-0082

    components = {"conf1_ge_tau": comp_conf, "admissible": comp_adm, "route_evidence_run": comp_route,
                  "niches_nonempty": comp_niches, "structural_not_fired": comp_struct,
                  "calibration_coverage": comp_cal, "council_uncovered_must": comp_council}
    gating_values = {"admissible": comp_adm["value"],
                     "route_evidence_run": comp_route["value"], "niches_nonempty": comp_niches["value"],
                     "structural_not_fired": comp_struct["value"]}
    if comp_conf["gating"]:
        gating_values["conf1_ge_tau"] = comp_conf["value"]
    if comp_cal["gating"]:
        gating_values["calibration_coverage"] = comp_cal["sufficient"]
    reasons = [k for k in COMPONENT_ORDER if k in gating_values and not gating_values[k]]

    block = {
        "competent": None, "not_applicable": False,
        "components": components,
        "conjunction": [k for k in COMPONENT_ORDER if k in gating_values],
        "reasons": reasons,
        "decided_by": DECIDED_BY, "module_version": MODULE_VERSION,
        "config": {"gate_enabled": cfg["gate_enabled"], "require_calibration": cfg["require_calibration"],
                   "conf_component_gating": cfg["conf_component_gating"],
                   "min_history": cfg["min_history"], "min_history_source": cfg["min_history_source"],
                   "tau": tau_eff, "tau_source": tau_source},   # la MISMA fuente que components.conf1_ge_tau.tau_source
        # la nota dice la VERDAD del registro: coincide con components.conf1_ge_tau.gating (cg-3: gatea por default;
        # sólo con WITT_CG_CONF_COMPONENT=0 declarado pasa a informativo)
        "self_report": {"stated_confidence": conf1, "class": "model-judgment",
                        "note": ("participa como componente conf1_ge_tau medido por CONF_TOOL (ADR-0065; gating true, "
                                 f"{CONF_COMPONENT_ENV} default 1, cg-3); la conjunción la decide código" if comp_conf["gating"]
                                 else f"no participa en la decisión (conf1_ge_tau informativo, {CONF_COMPONENT_ENV}=0 declarado)")},
    }
    if route == ROUTE_STORE_CONSULTATION:
        block["not_applicable"] = True
        block["skipped_reason"] = "route store-consultation: la compuerta no aplica (ADR-0063/0080)"
        return block
    if not cfg["gate_enabled"]:
        block["skipped_reason"] = f"kill-switch {GATE_ENV}=0 — la ruta cae al fallback por confianza de hoy (ADR-0051)"
        return block
    block["competent"] = not reasons
    return block


def compact(block):
    """Copia COMPACTA para deterministic_checks.competence_gate (el panel la lee; el bloque íntegro vive en
    frozen.competence)."""
    if not isinstance(block, dict):
        return None
    comps = block.get("components") or {}
    return {"competent": block.get("competent"), "not_applicable": block.get("not_applicable"),
            "reasons": list(block.get("reasons") or []),
            "components": {k: (v.get("value") if k != "calibration_coverage" else v.get("sufficient"))
                           for k, v in comps.items() if isinstance(v, dict)},
            "decided_by": block.get("decided_by"), "module_version": block.get("module_version"),
            "skipped_reason": block.get("skipped_reason")}

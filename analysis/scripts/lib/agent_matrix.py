"""
agent_matrix.py — the machine-readable face of `references/agent-invocation-matrix.md` v1.3
(tapón 3 / ADR-0061; membresía del consejo de criterio, ADR-0082 (B)). Same discipline as
reasoning_catalog.py (ADR-0060): the model picks NAMES from a closed enum and gives reasons; the GATE LEVEL,
the composite pattern, the phase locks, the CATEGORY, the council seat and the componentization status
resolve from THIS table — a planner that cannot emit a gate level cannot emit a wrong one, and a council
whose membership is a table cannot be talked into seating anyone.

Three truths this table separates:
  - what the MATRIX says about an agent (gate level, work-type signal, substrate evidence, category) —
    copied from the .md, which stays the human-readable authority;
  - what the CATALOG says (`catalog_cards.CARDS`: the verbatim card and its sha) — `card` here only declares
    whether a card EXISTS ('present' | 'no-card-in-catalog'); the text lives in catalog_cards;
  - what the WEBAPP RUN actually has as executable components (`componentized`): before ADR-0082 exactly
    TWO rows ran as code (composite-auditor, the resolve_id+verify_output gate). ADR-0082 seats 17 rows as
    council members (`lib/council.py`, rounds r1-r2) → 19/34 rows run as code. Everything else is prose.
    The planner may judge an agent APPLICABLE; whether it can RUN is not a judgment, it is a fact of this
    table.

ADR-0082 (B) — membresía por TABLA (`COUNCIL_MEMBERSHIP`, versión `cm-1`, brief §5.1 aprobado 2026-09-14):
  · 17 miembros en orden FIJO (el orden es identidad de la agregación, ADR-0082 (C.4)):
      compute (5) · lab (7) · knowledge (3) · cross-field (1) · flags (1)
    con `mode` ∈ requirements (14) | requirements-human-gated (causal-pruner: todo requisito suyo nace
    `hard_rule_gate True`, CLAUDE.md §7 :146) | flags-only (regulatory-ethics-advisor → tool `emit_flags`)
    | exploratory (cross-field-bridge-agent: `must` se degrada a `should`, §7 Test 5).
  · 8 operativos `not-applicable-by-category` (categoría `operations-reporting` en ESTA tabla): sólo se
    sientan con `WITT_COUNCIL_FULL=1` (N=25) para MEDIR que no aportan; sus requisitos llevan
    `from_operative True`.
  · 9 de sustrato / cubiertos con su estado REAL declarado (`substrate`): corren como código, están
    absorbidos, viven en tapones 4/5, están derogados (ADR-0046) o son sólo de sesión de agente.
  El consejo NUNCA escribe respuesta, veredicto, ranking ni despacha (CLAUDE.md §7; ADR-0082 (L.5)).

`category` en la matriz es la categoría del CONSEJO. Coincide con la sección `## Category N:` del catálogo en
30 de 31 fichas con fila; en las 4 filas operativas cuya ficha vive en otra sección (`bwh-coordinator`,
`reagent-procurement` — Wet-Lab; `ip-patent-watcher` — Knowledge; `case-capture-elicitor` — Substrate) la
divergencia se DECLARA en `category_note` (rol operativo, brief §5.1) — el smoke la mide, no la infiere.

`digest()` CAMBIA por construcción respecto a v1.2 (34 nombres en vez de 29) → `PLAN_VERSION '3' → '4'`
en runs.py (ADR-0082 (B); dueño C5). Declarado, no fingido.

The niches are CLAUDE.md §3 verbatim, with Phase-I activation — the plan is where the §3 scope filter
("a task that does not fit any niche must be flagged") finally gets a structural place to live in the
webapp path.
"""
import os

MATRIX_VERSION = "v1.3"
MATRIX_PATH = "skills/custom/organogenesis-agent-architect/references/agent-invocation-matrix.md"
MEMBERSHIP_VERSION = "cm-1"

# Vocabulario cerrado de `category` (las seis `## Category N:` del catálogo; catalog_cards.CATEGORY_VOCABULARY
# es la misma tupla — se repite aquí para que este módulo no cargue el parser al importar).
CATEGORIES = ("compute-simulation", "wet-lab-experiment", "data-omics", "knowledge-strategy",
              "operations-reporting", "substrate-instrumentation")
CARD_STATES = ("present", "no-card-in-catalog")
GATES = ("hard-rule", "required", "recommended")

# ADR-0082 (B): los 17 miembros pasan de `componentized None` a este componente — hecho de tabla.
COUNCIL_COMPONENT = ("lib/council.py", "council member r1-r2 (ADR-0082)")

# gate: "hard-rule" (§1, CLAUDE.md §7 enforces) | "required" (§2) | "recommended" (§3)
# componentized: (module path, note) when the row runs as CODE in the webapp pipeline; None otherwise.
# category: the council category (see module docstring); card: 'present' | 'no-card-in-catalog'.
# category_note: ONLY where the matrix category diverges from the card's `## Category N:` section.
AGENTS = {
    # --- §1 · hard-gated -------------------------------------------------------------------------
    "causal-pruner": {
        "gate": "hard-rule",
        "signal": "generating ranked candidates / minimal sets / sufficiency hypotheses / pruning "
                  "over signaling networks",
        "pattern": "causal-pruner -> Logic-LM verifier -> HUMAN GATE (§7.1: outputs always require a "
                   "human gate before downstream use)",
        "evidence": ["test_1", "test_3", "test_4"],
        "componentized": COUNCIL_COMPONENT,
        "note": "en la webapp el gate humano estructural existente es el cierre explícito "
                "(awaiting_closure -> closed): la respuesta no es precedente hasta que un humano cierra",
        "category": "compute-simulation", "card": "present",
    },
    "composite-auditor": {
        "gate": "hard-rule",
        "signal": "retrospective / audit of substrate-evidence outputs",
        "pattern": "Mode 1 split-and-vote minimum (>=3 valid); worst-of-N",
        "evidence": ["test_1", "test_4"],
        "componentized": ("lib/composite_auditor.py", "corre en el 100% de las corridas (ADR-0049)"),
        "note": None,
        "category": "substrate-instrumentation", "card": "present",
    },
    "cross-field-bridge-agent": {
        "gate": "hard-rule",
        "signal": "cross-field framing of an organogenesis question in Phase I",
        "pattern": "standalone, Method 2 ONLY in Phase I (§7.2)",
        "evidence": ["test_5"],
        "componentized": COUNCIL_COMPONENT,
        "note": "Method 1 locked until Phase II",
        "category": "substrate-instrumentation", "card": "present",
    },
    "experiment-designer": {
        "gate": "hard-rule",
        "signal": "wet-lab protocol translation from an in-silico recipe",
        "pattern": "designer -> regulatory-ethics-advisor review -> HUMAN GATE (§7 budget rule)",
        "evidence": ["test_2"],
        "componentized": COUNCIL_COMPONENT,
        "note": None,
        "category": "wet-lab-experiment", "card": "present",
    },
    "regulatory-ethics-advisor": {
        "gate": "hard-rule",
        "signal": "any claim or output that affects compliance / budget / partner relationships",
        "pattern": "direct human gate, no automatic filtering (§7)",
        "evidence": ["mission-critical"],
        "componentized": COUNCIL_COMPONENT,
        "note": None,
        "category": "knowledge-strategy", "card": "present",
    },
    "html-report-emitter": {
        "gate": "hard-rule",
        "signal": "conclusion / checkpoint of substrate-evidence-producing work",
        "pattern": "emit HTML report per html-report-contract.md",
        "evidence": ["test_1", "test_2"],
        "componentized": None,
        "note": "DEROGADO para corridas webapp (ADR-0046): el registro congelado + URL de la UI + PDF "
                "de servidor SON la traza — un plan de webapp lo marca not-applicable por derogación",
        "category": "substrate-instrumentation", "card": "no-card-in-catalog",
    },
    "type-c-viz-emitter": {
        "gate": "hard-rule",
        "signal": "conclusion backed by simulation output (morpheus-4d-viz, "
                  "causal-ablation-cascade-sim, squidiff-in-silico-gate, BioDynaMo, sim-orchestrator)",
        "pattern": "TYPE C interactive viz; static screenshot NOT sufficient",
        "evidence": ["test_1", "test_2"],
        "componentized": None,
        "note": "la corrida webapp no invoca simuladores hoy; aplicable sólo si la evidencia citada "
                "es salida de simulación",
        "category": "substrate-instrumentation", "card": "no-card-in-catalog",
    },
    "identifier-verification-gate": {
        "gate": "hard-rule",
        "signal": "any output containing an external identifier (ENSDARG/ENSDARP, UniProt, PMID, "
                  "GEO/SRA/PXD, DOI) — GWT v1.1",
        "pattern": "resolve_id + verify_output (Logic-LM-class, NOT an LLM); unresolved ENSDARG = "
                   "gate FAILURE",
        "evidence": ["test_1", "test_4"],
        "componentized": ("lib/verify_output.py + lib/resolve_id.py",
                          "el gate determinista corre en cada corrida (etapa 6)"),
        "note": "owner de catálogo: domain-knowledge-curator (PR-09, diferido)",
        "category": "substrate-instrumentation", "card": "no-card-in-catalog",
    },
    # --- §2 · required ---------------------------------------------------------------------------
    "reasoning-exposer": {
        "gate": "required",
        "signal": "any structured output with confidence + framework_applied per §5",
        "pattern": "wraps the producing agent's output",
        "evidence": ["test_1"],
        "componentized": None,
        "note": "desde ADR-0060 el SYNTH_TOOL emite los campos §5 él mismo — el rol corre ad-hoc "
                "dentro de la síntesis, no como agente aparte",
        "category": "substrate-instrumentation", "card": "present",
    },
    "calibration-tracker": {
        "gate": "required",
        "signal": "claim record with confidence < 0.95 and a checkable outcome",
        "pattern": "registers record + post-hoc isotonic / histogram binning (v2.2)",
        "evidence": ["test_4"],
        "componentized": None,
        "note": "tapón 4 (M5 + compute_ece.py) — hoy no existe como componente",
        "category": "substrate-instrumentation", "card": "present",
    },
    "evaluation-runner": {
        "gate": "required",
        "signal": "perturbation-resistant evaluation against the held-out set (Test 3)",
        "pattern": "batch with controlled perturbations, mean ± std",
        "evidence": ["test_3"],
        "componentized": None,
        "note": "tapón 5 — run_held_out.py es offline, no corre en la ruta HTTP",
        "category": "substrate-instrumentation", "card": "present",
    },
    "scrna-seq-analyst": {
        "gate": "required",
        "signal": "scRNA-seq pipeline analysis",
        "pattern": "may chain to cross-modality-integrator",
        "evidence": ["test_1", "test_4"],
        "componentized": COUNCIL_COMPONENT, "note": None,
        "category": "data-omics", "card": "present",
    },
    "spatial-omics-analyst": {
        "gate": "required",
        "signal": "spatial-omics analysis",
        "pattern": "may chain to cross-modality-integrator",
        "evidence": ["test_1", "test_4"],
        "componentized": COUNCIL_COMPONENT, "note": None,
        "category": "data-omics", "card": "present",
    },
    "histology-reviewer": {
        "gate": "required",
        "signal": "histology analysis",
        "pattern": "may chain to cross-modality-integrator",
        "evidence": ["test_1", "test_4"],
        "componentized": COUNCIL_COMPONENT, "note": None,
        "category": "data-omics", "card": "present",
    },
    "imaging-analyst": {
        "gate": "required",
        "signal": "imaging analysis",
        "pattern": "may chain to cross-modality-integrator",
        "evidence": ["test_1", "test_4"],
        "componentized": COUNCIL_COMPONENT, "note": None,
        "category": "wet-lab-experiment", "card": "present",
    },
    "cross-modality-integrator": {
        "gate": "required",
        "signal": "integration of multiple readout modalities into success-gate evidence",
        "pattern": "synthesizes scRNA + spatial + histology + sim",
        "evidence": ["test_1", "test_4"],
        "componentized": COUNCIL_COMPONENT,
        "note": "highest-leverage agent per catalog",
        "category": "data-omics", "card": "present",
    },
    "marker-validator": {
        "gate": "required",
        "signal": "marker scoring against canonical kidney markers",
        "pattern": "may chain to cross-modality-integrator",
        "evidence": ["test_1", "test_4"],
        "componentized": COUNCIL_COMPONENT, "note": None,
        "category": "wet-lab-experiment", "card": "present",
    },
    "hypothesis-generator": {
        "gate": "required",
        "signal": "generating a research hypothesis grounded in priors/literature (GWT v1.1)",
        "pattern": "source-of-truth -> MCP/ToolUniverse -> reasoning-exposer -> ethics deny-list; "
                   "obligatory non-empty contradictory_evidence",
        "evidence": ["test_3", "test_4"],
        "componentized": COUNCIL_COMPONENT,
        "note": "Method 2 default; Method 1 sólo en escalación wet-lab con gate humano 100%",
        "category": "knowledge-strategy", "card": "present",
    },
    # --- §3 · recommended ------------------------------------------------------------------------
    "literature-monitor": {
        "gate": "recommended", "signal": "literature monitoring / paper triage",
        "pattern": "Method 1 swarm-suitable", "evidence": [], "componentized": COUNCIL_COMPONENT, "note": None,
        "category": "knowledge-strategy", "card": "present",
    },
    "ip-patent-watcher": {
        "gate": "recommended", "signal": "IP / patent landscape monitoring",
        "pattern": None, "evidence": [], "componentized": None, "note": None,
        "category": "operations-reporting", "card": "present",
        "category_note": "catalog section: knowledge-strategy (Category 4); operative role per brief §5.1 → "
                         "operations-reporting in cm-1 (not-applicable-by-category)",
    },
    "case-capture-elicitor": {
        "gate": "recommended", "signal": "engineer-feedback case capture",
        "pattern": None, "evidence": ["test_3"], "componentized": None, "note": None,
        "category": "operations-reporting", "card": "present",
        "category_note": "catalog section: substrate-instrumentation (Category 6); operative role per brief "
                         "§5.1 → operations-reporting in cm-1 (not-applicable-by-category)",
    },
    "accumulator": {
        "gate": "recommended", "signal": "Method 2 aggregation of specialist outputs into thesis",
        "pattern": "Method 2 only", "evidence": [], "componentized": None,
        "note": "ADR-0082: lo reemplaza código — council.aggregate_requirements (agregación determinista)",
        "category": "substrate-instrumentation", "card": "present",
    },
    "program-manager": {
        "gate": "recommended", "signal": "Phase I timeline / budget tracking",
        "pattern": None, "evidence": [], "componentized": None, "note": None,
        "category": "operations-reporting", "card": "present",
    },
    "budget-tracker": {
        "gate": "recommended", "signal": "Phase I budget tracking",
        "pattern": None, "evidence": [], "componentized": None, "note": None,
        "category": "operations-reporting", "card": "present",
    },
    "risk-register-agent": {
        "gate": "recommended", "signal": "risk tracking / escalation",
        "pattern": None, "evidence": [], "componentized": None,
        "note": "slot reservado para retrospector en Cycle 3 (ADR-0009)",
        "category": "operations-reporting", "card": "present",
    },
    "investor-relations-drafter": {
        "gate": "recommended", "signal": "investor updates / milestone packaging",
        "pattern": None, "evidence": [], "componentized": None,
        "note": "SUSPENDIDO en Fase I (ADR-0008) — manual hasta el gate de financiamiento de Fase II",
        "category": "operations-reporting", "card": "present",
    },
    "sim-orchestrator": {
        "gate": "recommended", "signal": "simulation orchestration (Runpod batches)",
        "pattern": "Method 1 task", "evidence": [], "componentized": COUNCIL_COMPONENT, "note": None,
        "category": "compute-simulation", "card": "present",
    },
    "benchmark-designer": {
        "gate": "recommended", "signal": "benchmark task design",
        "pattern": None, "evidence": ["test_4"], "componentized": COUNCIL_COMPONENT, "note": None,
        "category": "compute-simulation", "card": "present",
    },
    "domain-knowledge-curator": {
        "gate": "recommended", "signal": "domain-knowledge curation",
        "pattern": None, "evidence": ["test_3"], "componentized": COUNCIL_COMPONENT, "note": None,
        "category": "knowledge-strategy", "card": "present",
    },
    # --- §3 · recommended — filas NUEVAS v1.3 (ADR-0082 (B): las 5 fichas del catálogo sin fila en v1.2;
    #     gate `recommended` provisional; agent-invocation-matrix.md v1.3 las lista (dueño C8)) --------
    "bwh-coordinator": {
        "gate": "recommended",
        "signal": "BWH Aquatics Facility relationship: scheduling, IACUC compliance, embryo production "
                  "requests, microinjection slots, imaging support",
        "pattern": None, "evidence": [], "componentized": None, "note": None,
        "category": "operations-reporting", "card": "present",
        "category_note": "catalog section: wet-lab-experiment (Category 2); operative role per brief §5.1 → "
                         "operations-reporting in cm-1 (not-applicable-by-category)",
    },
    "reagent-procurement": {
        "gate": "recommended",
        "signal": "reagent / construct ordering, vendor lead times, reagent inventory and the ~$34k "
                  "Phase I reagent budget",
        "pattern": None, "evidence": [], "componentized": None, "note": None,
        "category": "operations-reporting", "card": "present",
        "category_note": "catalog section: wet-lab-experiment (Category 2); operative role per brief §5.1 → "
                         "operations-reporting in cm-1 (not-applicable-by-category)",
    },
    "fitness-curator": {
        "gate": "recommended",
        "signal": "fitness-function library / ablation on fitness criteria / fitness-vs-phenotype "
                  "calibration for organ-like order (cohesion, compartmentalization, lumenization)",
        "pattern": "often a sub-skill of benchmark-designer in Phase I (catalog)",
        "evidence": [], "componentized": COUNCIL_COMPONENT, "note": None,
        "category": "compute-simulation", "card": "present",
    },
    "squidiff-in-silico-gate": {
        "gate": "recommended",
        "signal": "Squidiff transcriptomic-prediction gate for in-silico hypothesis testing "
                  "(four-state verdict PASS / PASS-DECOUPLE / MODERATE / FAIL, HUMAN GATE figures)",
        "pattern": "predictor -> HUMAN GATE 1/2 with figure; cross-verdict with Morpheus (Mode 3)",
        "evidence": ["test_1", "test_4"], "componentized": COUNCIL_COMPONENT,
        "note": "la corrida webapp no invoca simuladores hoy; como miembro del consejo sólo emite "
                "requisitos de evidencia (criterio), jamás predicciones",
        "category": "compute-simulation", "card": "present",
    },
    "retrospector": {
        "gate": "recommended",
        "signal": "offline Reasoning-Improvement Loop cadence (RIL): post-run rubric scoring, "
                  "self-critique record, governance proposals",
        "pattern": "checkpoint-triggered batch (tools/retrospect.py), NOT a 24/7 server",
        "evidence": ["test_3", "test_1", "test_4"], "componentized": None,
        "note": "agent-session only (ADR-0009)",
        "category": "substrate-instrumentation", "card": "present",
    },
}

ENUM = sorted(AGENTS)

# ── ADR-0082 (B): membresía del consejo de criterio, versionada, por TABLA ────────────────────────────
# El ORDEN de `members` es el orden FIJO de la tabla (brief §5.1): la agregación (C.4) toma la `query_en`
# del PRIMER emisor en este orden — cambiarlo cambia el agregado, por eso es identidad y va versionado.
_REQ_TOOL = "emit_information_requirements"
_FLAGS_TOOL = "emit_flags"


def _member(group, mode="requirements", tool=_REQ_TOOL, hard_rule_gate=False, exploratory=False, rule=None):
    m = {"group": group, "mode": mode, "tool": tool, "hard_rule_gate": hard_rule_gate,
         "exploratory": exploratory, "from_operative": False}
    if rule:
        m["rule"] = rule
    return m


COUNCIL_MEMBERSHIP = {
    "version": MEMBERSHIP_VERSION,
    "source": "brief 'Consejo de agentes' v3 §5.1 (aprobado por Emmanuel 2026-09-14) · ADR-0082 (B)",
    "members": {
        # Cómputo y simulación (5)
        "causal-pruner": _member(
            "compute", mode="requirements-human-gated", hard_rule_gate=True,
            rule="CLAUDE.md §7 (:146): outputs always require a human gate before downstream use — every "
                 "requirement it emits is born hard_rule_gate True and the ledger demands an EXPLICIT human "
                 "decision on it (ADR-0082 (F.1): 400 hard_rule_requirements_undecided; no default takes it)"),
        "sim-orchestrator": _member("compute"),
        "benchmark-designer": _member("compute"),
        "fitness-curator": _member("compute"),
        "squidiff-in-silico-gate": _member("compute"),
        # Laboratorio y lectura (7)
        "experiment-designer": _member("lab"),
        "imaging-analyst": _member("lab"),
        "marker-validator": _member("lab"),
        "scrna-seq-analyst": _member("lab"),
        "spatial-omics-analyst": _member("lab"),
        "histology-reviewer": _member("lab"),
        "cross-modality-integrator": _member("lab"),
        # Conocimiento (3)
        "literature-monitor": _member("knowledge"),
        "domain-knowledge-curator": _member("knowledge"),
        "hypothesis-generator": _member("knowledge"),
        # Campo vecino (1)
        "cross-field-bridge-agent": _member(
            "cross-field", mode="exploratory", exploratory=True,
            rule="CLAUDE.md §7 (:147-148): Method 2 only in Phase I / Test 5 exploratory — a `must` it emits "
                 "is degraded to `should` with priority_downgraded_from (ADR-0082 (C.4)); its requirements "
                 "carry exploratory True"),
        # Bandera (1)
        "regulatory-ethics-advisor": _member(
            "flags", mode="flags-only", tool=_FLAGS_TOOL,
            rule="CLAUDE.md §7 (:149): compliance and budget decisions never go through automatic filtering "
                 "— emits ONLY flags (tool emit_flags), no evidence requirements; gate 'human' is set by CODE"),
    },
    "groups": ("compute", "lab", "knowledge", "cross-field", "flags"),
    "modes": ("requirements", "requirements-human-gated", "flags-only", "exploratory"),
    # Los 8 operativos: `not-applicable-by-category` (su `category` en ESTA tabla es operations-reporting).
    # Sólo se sientan con WITT_COUNCIL_FULL=1 (N=25) para MEDIR que no aportan (§14 del brief).
    "not_applicable_by_category": ("operations-reporting",),
    "operatives": {
        name: {"group": "operations", "mode": "requirements", "tool": _REQ_TOOL, "hard_rule_gate": False,
               "exploratory": False, "from_operative": True,
               "state": "not-applicable-by-category (cm-1); seated only with WITT_COUNCIL_FULL=1"}
        for name in ("program-manager", "budget-tracker", "bwh-coordinator", "reagent-procurement",
                     "ip-patent-watcher", "case-capture-elicitor", "risk-register-agent",
                     "investor-relations-drafter")
    },
    # Los 9 de sustrato / cubiertos, con su estado REAL (ADR-0082 (B)): no son miembros ni operativos.
    "substrate": {
        "composite-auditor": "invoked (component)",
        "identifier-verification-gate": "invoked (component)",
        "accumulator": "replaced-by-code (council.aggregate_requirements)",
        "reasoning-exposer": "absorbed (SYNTH_TOOL framework_applied)",
        "calibration-tracker": "tapón 4/5 (not in webapp run)",
        "evaluation-runner": "tapón 4/5 (not in webapp run)",
        "html-report-emitter": "derogated (ADR-0046)",
        "type-c-viz-emitter": "derogated (ADR-0046)",
        "retrospector": "agent-session only (ADR-0009)",
    },
    "full_env": "WITT_COUNCIL_FULL",
}

MEMBERS = tuple(COUNCIL_MEMBERSHIP["members"])          # los 17, orden fijo
OPERATIVES = tuple(COUNCIL_MEMBERSHIP["operatives"])    # los 8
SUBSTRATE = tuple(COUNCIL_MEMBERSHIP["substrate"])      # los 9

_TRUTHY = {"1", "true", "yes", "on"}


def council_full(env=None, full=None):
    """(full: bool, source) — WITT_COUNCIL_FULL tolerante: '1/true/yes/on' → True; vacía, '0' o basura →
    False declarado. `full=` explícito gana (la corrida usa la N CONGELADA en el plan, ADR-0082 (F.4))."""
    if full is not None:
        return bool(full), "explicit (frozen in plan.council)"
    env = os.environ if env is None else env
    raw = (env.get(COUNCIL_MEMBERSHIP["full_env"]) or "").strip().lower()
    if raw == "":
        return False, "default (WITT_COUNCIL_FULL unset)"
    if raw in _TRUTHY:
        return True, "env WITT_COUNCIL_FULL"
    if raw in {"0", "false", "no", "off"}:
        return False, "env WITT_COUNCIL_FULL"
    return False, f"default (WITT_COUNCIL_FULL unparseable: {raw!r})"


def council_members(env=None, full=None):
    """ADR-0082 (B): los nombres sentados, en orden FIJO de tabla — 17, o 17 + 8 operativos con
    WITT_COUNCIL_FULL=1 (N=25). El orden es identidad de la agregación."""
    is_full, _ = council_full(env, full)
    return list(MEMBERS) + (list(OPERATIVES) if is_full else [])


def council_size(env=None, full=None):
    return len(council_members(env, full))


def council_member(name):
    """La entrada de membresía (miembro u operativo) con `agent`, `seat` y la fila de la matriz resumida;
    None para quien no está en la tabla del consejo (sustrato o fuera de matriz)."""
    entry = COUNCIL_MEMBERSHIP["members"].get(name)
    seat = "member"
    if entry is None:
        entry = COUNCIL_MEMBERSHIP["operatives"].get(name)
        seat = "operative (full-council only)"
    if entry is None:
        return None
    row = AGENTS.get(name) or {}
    return {"agent": name, "seat": seat, **entry, "category": row.get("category"), "gate": row.get("gate"),
            "card": row.get("card"), "componentized": row.get("componentized")}


def membership_view(env=None, full=None, cards=None):
    """La membresía como la sirve `GET /council/membership` (ADR-0082 (I); dueño de la ruta C6) —
    NO-SPEND, sin BD. `cards` inyectable (default: catalog_cards.CARDS, import perezoso para no cargar el
    parser al importar la matriz). Declara cards_without_row / rows_without_card MEDIDOS."""
    if cards is None:
        from lib import catalog_cards            # perezoso: la matriz no lee archivos al importar
        cards = catalog_cards.CARDS
        catalog_sha, catalog_state, catalog_path = (catalog_cards.CATALOG_SHA, catalog_cards.CATALOG_STATE,
                                                    catalog_cards.CATALOG_PATH)
    else:
        from lib import catalog_cards
        catalog_sha, catalog_state, catalog_path = catalog_cards.catalog_sha(cards), "injected", None
    is_full, full_source = council_full(env, full)
    seated = council_members(env, full)
    members = []
    for name in seated:
        e = council_member(name)
        c = cards.get(name)
        members.append({"agent": name, "category": e["category"], "group": e["group"], "mode": e["mode"],
                        "tool": e["tool"], "gate": e["gate"], "hard_rule_gate": e["hard_rule_gate"],
                        "exploratory": e["exploratory"], "from_operative": e["from_operative"],
                        "card": e["card"], "card_sha": c["sha"] if c else None,
                        "componentized": e["componentized"]})
    return {
        "membership_version": MEMBERSHIP_VERSION,
        "matrix_version": MATRIX_VERSION,
        "catalog_sha": catalog_sha,
        "catalog_state": catalog_state,
        "catalog_path": catalog_path,
        "n_members": len(seated),
        "full_council": is_full,
        "full_council_source": full_source,
        "full_council_env": COUNCIL_MEMBERSHIP["full_env"],
        "members": members,
        "not_applicable_by_category": list(COUNCIL_MEMBERSHIP["not_applicable_by_category"]),
        "not_applicable": [] if is_full else [
            {"agent": n, "category": AGENTS[n]["category"], "state": COUNCIL_MEMBERSHIP["operatives"][n]["state"]}
            for n in OPERATIVES],
        "substrate": [{"agent": n, "state": s} for n, s in COUNCIL_MEMBERSHIP["substrate"].items()],
        "cards_without_row": sorted(n for n in cards if n not in AGENTS),
        "rows_without_card": sorted(n for n, r in AGENTS.items() if r["card"] == "no-card-in-catalog"),
        "n_rows": len(AGENTS),
        "n_componentized": sum(1 for r in AGENTS.values() if r["componentized"]),
    }


# CLAUDE.md §3 — the six niches, with Phase-I activation. The plan is where the scope filter finally
# lives structurally in the webapp path: no niche matched => the plan carries the flag §3 demands.
NICHES = {
    "N1": {"name": "Modelado de Sistemas Biológicos", "phase_i": "active"},
    "N2": {"name": "Biofísica y Biomecánica de Tejidos", "phase_i": "phase-II"},
    "N3": {"name": "Embriología, Genómica Funcional y de Célula Única", "phase_i": "active"},
    "N4": {"name": "Señalización Celular", "phase_i": "active"},
    "N5": {"name": "Biología Ocular", "phase_i": "exploratory (Test 5 candidato, pendiente "
                                                 "PROJECT_SCOPE §11)"},
    "N6": {"name": "Ingeniería de Tejidos y Medicina Regenerativa", "phase_i": "phase-III"},
}
NICHE_ENUM = sorted(NICHES)


def resolve(name):
    """Matrix row for an agent name; None when off-matrix (recorded raw, never corrected)."""
    return AGENTS.get(name)


def digest():
    """The compact matrix handed to the planner model. Same rationale as reasoning_catalog.digest():
    a judgment against a matrix the model never saw manufactures matches. Gate levels and
    componentization do NOT travel here as things to output — the model returns names + reasons only.
    v1.3 (ADR-0082): 34 nombres — CAMBIA respecto a v1.2 por construcción (PLAN_VERSION lo declara)."""
    lines = ["Agent-invocation matrix (judge which WORK-TYPES this question implicates; return ONLY "
             "applicable agents with a reason each):"]
    for name in ENUM:
        a = AGENTS[name]
        note = f" [{a['note']}]" if a.get("note") else ""
        lines.append(f"  - {name} ({a['gate']}): {a['signal']}{note}")
    lines.append("Niches (CLAUDE.md §3 — classify the question into >=1, or declare out-of-scope):")
    for code in NICHE_ENUM:
        n = NICHES[code]
        lines.append(f"  - {code}: {n['name']} (Phase I: {n['phase_i']})")
    return "\n".join(lines)

"""
agent_matrix.py — the machine-readable face of `references/agent-invocation-matrix.md` v1.2
(tapón 3 / ADR-0061). Same discipline as reasoning_catalog.py (ADR-0060): the model picks NAMES from a
closed enum and gives reasons; the GATE LEVEL, the composite pattern, the phase locks and the
componentization status resolve from THIS table — a planner that cannot emit a gate level cannot emit a
wrong one.

Two truths this table separates:
  - what the MATRIX says about an agent (gate level, work-type signal, substrate evidence) — copied
    from the .md, which stays the human-readable authority;
  - what the WEBAPP RUN actually has as executable components (`componentized`): today exactly TWO
    matrix rows run as code in the pipeline (composite-auditor, the resolve_id+verify_output gate).
    Everything else is prose. The planner may judge an agent APPLICABLE; whether it can RUN is not a
    judgment, it is a fact of this table.

The niches are CLAUDE.md §3 verbatim, with Phase-I activation — the plan is where the §3 scope filter
("a task that does not fit any niche must be flagged") finally gets a structural place to live in the
webapp path.
"""

MATRIX_VERSION = "v1.2"
MATRIX_PATH = "skills/custom/organogenesis-agent-architect/references/agent-invocation-matrix.md"

# gate: "hard-rule" (§1, CLAUDE.md §7 enforces) | "required" (§2) | "recommended" (§3)
# componentized: (module path, note) when the row runs as CODE in the webapp pipeline; None otherwise.
AGENTS = {
    # --- §1 · hard-gated -------------------------------------------------------------------------
    "causal-pruner": {
        "gate": "hard-rule",
        "signal": "generating ranked candidates / minimal sets / sufficiency hypotheses / pruning "
                  "over signaling networks",
        "pattern": "causal-pruner -> Logic-LM verifier -> HUMAN GATE (§7.1: outputs always require a "
                   "human gate before downstream use)",
        "evidence": ["test_1", "test_3", "test_4"],
        "componentized": None,
        "note": "en la webapp el gate humano estructural existente es el cierre explícito "
                "(awaiting_closure -> closed): la respuesta no es precedente hasta que un humano cierra",
    },
    "composite-auditor": {
        "gate": "hard-rule",
        "signal": "retrospective / audit of substrate-evidence outputs",
        "pattern": "Mode 1 split-and-vote minimum (>=3 valid); worst-of-N",
        "evidence": ["test_1", "test_4"],
        "componentized": ("lib/composite_auditor.py", "corre en el 100% de las corridas (ADR-0049)"),
        "note": None,
    },
    "cross-field-bridge-agent": {
        "gate": "hard-rule",
        "signal": "cross-field framing of an organogenesis question in Phase I",
        "pattern": "standalone, Method 2 ONLY in Phase I (§7.2)",
        "evidence": ["test_5"],
        "componentized": None,
        "note": "Method 1 locked until Phase II",
    },
    "experiment-designer": {
        "gate": "hard-rule",
        "signal": "wet-lab protocol translation from an in-silico recipe",
        "pattern": "designer -> regulatory-ethics-advisor review -> HUMAN GATE (§7 budget rule)",
        "evidence": ["test_2"],
        "componentized": None,
        "note": None,
    },
    "regulatory-ethics-advisor": {
        "gate": "hard-rule",
        "signal": "any claim or output that affects compliance / budget / partner relationships",
        "pattern": "direct human gate, no automatic filtering (§7)",
        "evidence": ["mission-critical"],
        "componentized": None,
        "note": None,
    },
    "html-report-emitter": {
        "gate": "hard-rule",
        "signal": "conclusion / checkpoint of substrate-evidence-producing work",
        "pattern": "emit HTML report per html-report-contract.md",
        "evidence": ["test_1", "test_2"],
        "componentized": None,
        "note": "DEROGADO para corridas webapp (ADR-0046): el registro congelado + URL de la UI + PDF "
                "de servidor SON la traza — un plan de webapp lo marca not-applicable por derogación",
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
    },
    "calibration-tracker": {
        "gate": "required",
        "signal": "claim record with confidence < 0.95 and a checkable outcome",
        "pattern": "registers record + post-hoc isotonic / histogram binning (v2.2)",
        "evidence": ["test_4"],
        "componentized": None,
        "note": "tapón 4 (M5 + compute_ece.py) — hoy no existe como componente",
    },
    "evaluation-runner": {
        "gate": "required",
        "signal": "perturbation-resistant evaluation against the held-out set (Test 3)",
        "pattern": "batch with controlled perturbations, mean ± std",
        "evidence": ["test_3"],
        "componentized": None,
        "note": "tapón 5 — run_held_out.py es offline, no corre en la ruta HTTP",
    },
    "scrna-seq-analyst": {
        "gate": "required",
        "signal": "scRNA-seq pipeline analysis",
        "pattern": "may chain to cross-modality-integrator",
        "evidence": ["test_1", "test_4"],
        "componentized": None, "note": None,
    },
    "spatial-omics-analyst": {
        "gate": "required",
        "signal": "spatial-omics analysis",
        "pattern": "may chain to cross-modality-integrator",
        "evidence": ["test_1", "test_4"],
        "componentized": None, "note": None,
    },
    "histology-reviewer": {
        "gate": "required",
        "signal": "histology analysis",
        "pattern": "may chain to cross-modality-integrator",
        "evidence": ["test_1", "test_4"],
        "componentized": None, "note": None,
    },
    "imaging-analyst": {
        "gate": "required",
        "signal": "imaging analysis",
        "pattern": "may chain to cross-modality-integrator",
        "evidence": ["test_1", "test_4"],
        "componentized": None, "note": None,
    },
    "cross-modality-integrator": {
        "gate": "required",
        "signal": "integration of multiple readout modalities into success-gate evidence",
        "pattern": "synthesizes scRNA + spatial + histology + sim",
        "evidence": ["test_1", "test_4"],
        "componentized": None,
        "note": "highest-leverage agent per catalog",
    },
    "marker-validator": {
        "gate": "required",
        "signal": "marker scoring against canonical kidney markers",
        "pattern": "may chain to cross-modality-integrator",
        "evidence": ["test_1", "test_4"],
        "componentized": None, "note": None,
    },
    "hypothesis-generator": {
        "gate": "required",
        "signal": "generating a research hypothesis grounded in priors/literature (GWT v1.1)",
        "pattern": "source-of-truth -> MCP/ToolUniverse -> reasoning-exposer -> ethics deny-list; "
                   "obligatory non-empty contradictory_evidence",
        "evidence": ["test_3", "test_4"],
        "componentized": None,
        "note": "Method 2 default; Method 1 sólo en escalación wet-lab con gate humano 100%",
    },
    # --- §3 · recommended ------------------------------------------------------------------------
    "literature-monitor": {
        "gate": "recommended", "signal": "literature monitoring / paper triage",
        "pattern": "Method 1 swarm-suitable", "evidence": [], "componentized": None, "note": None,
    },
    "ip-patent-watcher": {
        "gate": "recommended", "signal": "IP / patent landscape monitoring",
        "pattern": None, "evidence": [], "componentized": None, "note": None,
    },
    "case-capture-elicitor": {
        "gate": "recommended", "signal": "engineer-feedback case capture",
        "pattern": None, "evidence": ["test_3"], "componentized": None, "note": None,
    },
    "accumulator": {
        "gate": "recommended", "signal": "Method 2 aggregation of specialist outputs into thesis",
        "pattern": "Method 2 only", "evidence": [], "componentized": None, "note": None,
    },
    "program-manager": {
        "gate": "recommended", "signal": "Phase I timeline / budget tracking",
        "pattern": None, "evidence": [], "componentized": None, "note": None,
    },
    "budget-tracker": {
        "gate": "recommended", "signal": "Phase I budget tracking",
        "pattern": None, "evidence": [], "componentized": None, "note": None,
    },
    "risk-register-agent": {
        "gate": "recommended", "signal": "risk tracking / escalation",
        "pattern": None, "evidence": [], "componentized": None,
        "note": "slot reservado para retrospector en Cycle 3 (ADR-0009)",
    },
    "investor-relations-drafter": {
        "gate": "recommended", "signal": "investor updates / milestone packaging",
        "pattern": None, "evidence": [], "componentized": None,
        "note": "SUSPENDIDO en Fase I (ADR-0008) — manual hasta el gate de financiamiento de Fase II",
    },
    "sim-orchestrator": {
        "gate": "recommended", "signal": "simulation orchestration (Runpod batches)",
        "pattern": "Method 1 task", "evidence": [], "componentized": None, "note": None,
    },
    "benchmark-designer": {
        "gate": "recommended", "signal": "benchmark task design",
        "pattern": None, "evidence": ["test_4"], "componentized": None, "note": None,
    },
    "domain-knowledge-curator": {
        "gate": "recommended", "signal": "domain-knowledge curation",
        "pattern": None, "evidence": ["test_3"], "componentized": None, "note": None,
    },
}

ENUM = sorted(AGENTS)

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
    componentization do NOT travel here as things to output — the model returns names + reasons only."""
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

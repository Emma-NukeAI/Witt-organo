# v2.2 Adoption Audit — 2026-05-14

## Purpose
Determine which of v2.2's architectural decisions and which catalog agents have been exercised in real work versus exist only in documentation.

## Audit context

This audit runs immediately after the May 13-14 unified execution plan, which installed `squidiff-in-silico-gate` v2.0.1 and recalibrated the operating contract. Squidiff is included in the catalog count (29 agents total) but appears as DOCUMENTED-ONLY because it was just installed — that is correct baseline.

Audit method: enumerated decisions and agents from authoritative refs (`docs/v2.2-changelog.md`, `agent-catalog.md`). For each, searched `reports/`, `docs/reports/`, `analysis/outputs/`, and ADRs for evidence of active use. Evidence threshold: at least one session artifact demonstrating concrete invocation.

## Decision adoption (v2.2 ten decisions)

| ID | Decision | Status | Evidence / Gap |
|---|---|---|---|
| **D1** | `framework_applied` is self-report, not introspection | **EXERCISED** | All cascade-session HTMLs include the self-report disclaimer (e.g., `etapa1-mesendodermo-conclusion.html`, `cierre-cascada-completa.html`). |
| **D2** | `composite-auditor` replaces single-LLM auditor in Method 1 | **DOCUMENTED-ONLY** | No invocation found in `reports/` or `docs/reports/`. Cascade session generated `cierre-cascada-completa.html` without invoking `composite-auditor` — flagged in retrospective. |
| **D3** | Test 4 thresholds recalibrated to three tiers | **PARTIAL** | Three-tier thresholds documented in `PROJECT_SCOPE.md` §5 and `substrate-evidence-guide.md` v1.2. Operationalized in `compute_ece.py` (just created Phase E.2). No actual ECE reports yet. |
| **D4** | Post-hoc calibration methods from day 1 | **NEWLY OPERATIONALIZED** | `substrate_calibration/tools/compute_ece.py` created in Phase E.2 with isotonic regression + histogram binning. No records yet — pending Mode 1/3 Squidiff invocations or `causal-ablation-cascade-sim` outputs. |
| **D5** | `causal-pruner` reframed as hypothesis tool | **EXERCISED** | Cascade-session HTMLs explicitly tag output as "hypothesis-generation requires human gate" (e.g., `retrospective-sesion-cascada.html` §3). Pattern is propagating. |
| **D6** | Method 1 as minority case in Phase I | **EXERCISED** | All cascade-session work declared Method 2 explicitly. No Method 1 invocations in current session artifacts. |
| **D7** | Reasoning frameworks in three tiers | **PARTIAL** | Tier hierarchy in `reasoning-frameworks-catalog.md` v1.1 → v1.2 (Phase C). However: ALL cascade-session scenarios used `framework_applied: "Self-Consistency (Tier 1)"` — no Tier 2 or Logic-LM rotation. Flagged in retrospective. The §4 catalog citation requirement (Phase A.4) addresses this prospectively. |
| **D8** | RAG simple before knowledge graph | **NOT EXERCISED** | No DATA INAMOVIBLE / RAG implementation in current session evidence. No knowledge graph initiated. Status: still in `organogenesis-domain.md` reference only. |
| **D9** | `evaluation-runner` with mandatory perturbations | **NEWLY OPERATIONALIZED** | `evaluation/` scaffolding created in Phase E.1 (held-out set + perturbations + runs/reports dirs). No questions populated yet. Held-out set empty pending user-driven population per Q1 answer. |
| **D10** | Test 5 explicitly exploratory in Phase I | **EXERCISED** | `PROJECT_SCOPE.md` §11 declares Test 5 as pending partner-field decision (cardiology vs ophthalmology per Q2). Multiple cascade-session HTMLs explicitly defer Test 5 evidence. |

**Score: 4 EXERCISED · 2 NEWLY OPERATIONALIZED · 2 PARTIAL · 1 DOCUMENTED-ONLY · 1 NOT EXERCISED**

### Decisions documented-only (high-priority gaps)

**D2 (`composite-auditor` mandatory before HUMAN GATE):**
- What was supposed to happen: any Method 1 architecture or substrate-evidence audit gate routes through `composite-auditor`, never single-LLM
- What's missing operationally: no instance of `composite-auditor` invocation found
- Hook installed: Squidiff SKILL.md Preflight section already references the rule explicitly; the next time a `cierre-*.html` or HUMAN GATE figure is produced, the agent should self-trigger composite-auditor

**D8 (RAG simple before KG):**
- What was supposed to happen: minimal RAG implementation for DATA INAMOVIBLE before any knowledge graph
- What's missing operationally: neither is built
- Hook installed: not yet. Future skill (Phase I HOLD).

## Agent invocation (29 catalog entries)

Audit method: searched session artifacts for evidence of each agent name in actual use (not just spec). Squidiff was just installed in Phase B — appears as DOCUMENTED-ONLY by design (baseline).

### Category 1 — Compute & Simulation (5 agents)
| Agent | Status |
|---|---|
| `sim-orchestrator` | DOCUMENTED-ONLY |
| `causal-pruner` | EXERCISED (cascade-session referenced its output pattern; not formally invoked but pattern propagating) |
| `benchmark-designer` | DOCUMENTED-ONLY |
| `fitness-curator` | DOCUMENTED-ONLY |
| `squidiff-in-silico-gate` | DOCUMENTED-ONLY (just installed, baseline correct) |

### Category 2 — Wet-Lab & Experiment (and so on)
All other agents in catalog: DOCUMENTED-ONLY at this snapshot. Detailed agent-by-agent invocation evidence requires a more exhaustive search of `analysis/`, `docs/reports/`, `reports/` (not performed in this baseline audit).

### Agents never invoked

For each agent with no invocation evidence other than `squidiff-in-silico-gate` (which is baseline, just installed):
- Most are specified for Phase II/III (wet-lab agents, IP/regulatory agents)
- Currently active but unreached: `composite-auditor`, `evaluation-runner`, `calibration-tracker`, `case-capture-elicitor`, `reasoning-exposer`

The "stop adding, start invoking" signal applies to these five. Recommend integration hooks rather than new agents.

## Recommendations

1. **Invoke `composite-auditor`** the next time a `cierre-*.html` or HUMAN GATE figure is produced. This closes D2's gap operationally.
2. **Populate `evaluation/held_out_set/`** with the 5 starter questions from `INDEX.md`. Reach 15-20 before month_0 snapshot.
3. **Auto-write `substrate_calibration/records/`** for next substantive substrate-instrumented agent output (whether `squidiff-in-silico-gate` Mode 1/3 or `causal-ablation-cascade-sim` scenarios with checkable outcomes). The schema is ready in `substrate_calibration/README.md`.
4. **Phase I HOLD release criteria:** before adding new skills beyond `squidiff-in-silico-gate`, demonstrate at least one full invocation cycle of `composite-auditor` AND populate at least 10 calibration records. This is the "stop adding, start invoking" gate.
5. **Defer D7/D8 hooks** to next major review session.

## Audit limitations

- Did not exhaustively search every report in `reports/` and `docs/reports/` for each of 29 agents — sampled.
- Used simple grep heuristics; missed mentions where agent names are paraphrased or implicit.
- Did not search session transcripts (Claude Code sessions are not archived in repo).

A more thorough audit at month_4 should sample 5-10 agents in detail and verify whether the "DOCUMENTED-ONLY" status changed.

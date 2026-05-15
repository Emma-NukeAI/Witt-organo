# ADR 0006 — Catalog agent invocation discipline + decision matrix

- **Date:** 2026-05-14
- **Status:** proposed
- **Decided by:** Emmanuel (Nuke AI) — pending review; surfaced by composite-audit SESS-2026-05-14
- **Affects:** `CLAUDE.md §7`, `CLAUDE.md §11` (new), `references/agent-invocation-matrix.md` (new), `references/agent-catalog.md` (cross-reference), output contract §5

## Context

The composite audit of session 2026-05-14 identified a structural failure that the v2.3 recalibration did not fix: **6 catalog agents whose roles matched work being performed were not invoked**. Specifically:

| Agent | Role-match in session | Invocation status |
|---|---|---|
| `causal-pruner` | Generated 14-candidate minimal-set hypothesis (literal pruner output) | NOT invoked; CLAUDE.md §7.1 violated structurally |
| `composite-auditor` | Self-audit / retrospective of substrate evidence | NOT invoked for retrospective; CLAUDE.md §7.7 violated |
| `reasoning-exposer` | Should wrap every structured output to enforce contract | NOT invoked; some outputs missing `alternatives_considered` in JSON |
| `calibration-tracker` | Owns Test 4; should apply post-hoc methods from day 1 (v2.2 mandate) | NOT invoked; `post_hoc_calibration_applied: null` in all records |
| `cross-modality-integrator` | "Highest-leverage agent" per catalog; integrates multi-modal evidence | NOT invoked; resulted in 4 parallel artifact views (E10 artifact proliferation) |
| `evaluation-runner` | Owns Test 3 measurement with perturbation protocol | NOT invoked |

The root cause is **not missing rules** — CLAUDE.md §7 already enforces several of these. The root cause is **missing forcing function at decision time**. Rules in CLAUDE.md exist as constraints but not as reflexes. CLAUDE.md §10 (preflight) successfully created a reflex for repo-state verification because it specified explicit commands; agent invocation has no parallel mechanism.

This ADR proposes a **structural forcing function** parallel to §10: a §11 agent-invocation preflight backed by a decision matrix and an `agents_invoked` field in the output contract.

## Decision

Establish three coordinated mechanisms:

### 1. Decision matrix (lookup table)

A canonical `references/agent-invocation-matrix.md` mapping **work-types** to **required catalog agents**. Each row specifies: what work triggers it, which agent owns it, whether it is hard-gated (Hard Rule violation if skipped) or recommendation (skip-with-justification allowed), and what evidence the agent generates.

Initial matrix entries (full version in the reference file):

| Work-type | Required agent | Gate level |
|---|---|---|
| Ranked candidates / minimal-set / sufficiency hypothesis / pruning over signaling networks | `causal-pruner` + Logic-LM verifier + human gate | **Hard Rule §7.1** |
| Retrospective / audit of substrate-evidence outputs | `composite-auditor` Mode 1 minimum | **Hard Rule §7.7** |
| Structured-output contract enforcement | `reasoning-exposer` wraps | Recommended (skip-justify) |
| Claim records with confidence < 0.95 and checkable outcome | `calibration-tracker` registers + applies post-hoc | Recommended; required for Test 4 measurement |
| Cross-modal evidence integration (transcriptomic + proteomic + LoF + simulation) | `cross-modality-integrator` synthesizes | Recommended |
| Perturbation-resistant evaluation against held-out set | `evaluation-runner` with mean ± std | Required for Test 3 measurement |
| Wet-lab protocol translation from in-silico recipe | `experiment-designer` + budget/compliance preflight | **Hard Rule** (compliance/budget never auto-filtered) |
| Cross-field framing of organogenesis question | `cross-field-bridge-agent` (Method 2 only Phase I) | **Hard Rule §7.2** |

### 2. CLAUDE.md §11 — agent-invocation preflight (new section parallel to §10)

Before generating any substrate-instrumented output (output contract per §5), the agent MUST:

1. Classify the dominant work-type of the output being produced.
2. Consult the `agent-invocation-matrix.md` for required agents.
3. Either invoke the agent (via `Agent` tool or skill or sub-process) OR explicitly skip with justification.
4. Populate the output contract's new `agents_invoked` field accordingly.

The output contract field structure:

```json
"agents_invoked": [
  {
    "agent": "causal-pruner",
    "status": "invoked",
    "invocation_id": "agent_xxx",
    "evidence_generated": ["test_1", "test_2"]
  },
  {
    "agent": "reasoning-exposer",
    "status": "skipped-ad-hoc",
    "reason": "Work was a single-file edit not generating substrate evidence; reasoning-exposer overhead disproportionate"
  }
]
```

Skipping without justification is a §11 audit failure. The field MAY be empty if the work-type matches no catalog agent (e.g., trivial file edits, conversational responses).

### 3. New Hard Rule §7.10

Add to CLAUDE.md §7:

> **Self-audit by the same agent that produced the work is prohibited as the substrate-evidence audit gate.** Use `composite-auditor` (Mode 1 split-and-vote minimum) for any retrospective claimed as audit evidence. Self-reflection is permitted but is NOT an audit gate. The May 14 2026 session generated a single-LLM retrospective that violated §7.7; this rule makes the prohibition explicit.

## Alternatives considered

1. **Rely on existing CLAUDE.md §7 rules without a forcing function** — Rejected: this is the status quo and v2.3 failed in 2026-05-14 session despite §7 being explicit about causal-pruner and composite-auditor. Rules without reflexes don't bind.

2. **Auto-route via SDK / skill orchestration layer** — Rejected for now: requires building infrastructure (a routing skill that intercepts substrate work). Higher effort, can revisit if §11 preflight proves insufficient.

3. **Add the matrix to agent-catalog.md** — Rejected: agent-catalog.md describes agents (what they are); the matrix describes work-routing (when to invoke). Different concerns — separate file is clearer.

4. **Hard-gate all catalog agents (no recommendation tier)** — Rejected: would force agent invocation for trivial work (a one-line edit doesn't need reasoning-exposer). The hard-gate tier should stay narrow; recommendations + skip-with-justification provides flexibility while still requiring explicit acknowledgment.

5. **Make the matrix part of CLAUDE.md** — Rejected: matrix will grow; CLAUDE.md should stay tight (contract, not manual). Pattern follows §8 "Where to look for depth" — depth lives in references.

## Consequences

**Positive:**

- Closes the 2026-05-14 structural gap: agent invocation becomes a reflex like §10 preflight.
- Skip-with-justification creates audit trail when agents are not invoked — even when skip is appropriate, the decision is visible.
- Matrix is extensible: as new agents enter the catalog, new rows added.
- Reduces artifact proliferation (E10): work routed through `cross-modality-integrator` produces one synthesis instead of 4 parallel views.
- Creates a measurable agent-discipline signal for Test 1 (orchestration evidence).

**Negative / costs:**

- Adds preflight overhead before every substrate-instrumented output. Acceptable — §10 already added similar overhead and adoption was smooth.
- Some agents in the catalog are not yet operational (e.g., `composite-auditor` doesn't exist as a literal subagent_type; this session emulated it via `general-purpose` × 3). The matrix should note this until the agents are built.
- Skip-with-justification can be gamed (always justify-skip). Mitigation: `composite-auditor` audits skip justifications periodically (Phase I held action item).

**Implementation order:**

1. Write `references/agent-invocation-matrix.md` with initial entries (this ADR ships it).
2. Add CLAUDE.md §11 (this ADR's §1 content as the section body).
3. Add Hard Rule §7.10 (text from this ADR's §3 content).
4. Update `substrate-evidence-guide.md` output-contract spec to include `agents_invoked` field.
5. Backfill `agents_invoked` for the 4 claim records of session 2026-05-14 retroactively (with `status: skipped-ad-hoc` and audit reference).
6. From next session onward: enforce.

## Evidence

- `docs/findings/2026-05-14-composite-audit-meta-conclusion.md` §2 (convergent findings F2, F3), §4 (anti-patterns AP-N6, AP-N7), §5 (Hard Rules violations table), §6.2 (recommendations)
- `docs/findings/2026-05-14-pronephros-proteomics-session-retrospective.md` §3.2 E4 (framework drift) + §7.3 R8 (composite-auditor recommendation)
- `skills/custom/organogenesis-agent-architect/references/agent-catalog.md` (the 26-29 agents whose invocation discipline this ADR governs)
- `CLAUDE.md §7` (existing hard rules that this ADR makes mechanically enforceable)
- `CLAUDE.md §10` (the existing preflight that proves the reflex pattern works)

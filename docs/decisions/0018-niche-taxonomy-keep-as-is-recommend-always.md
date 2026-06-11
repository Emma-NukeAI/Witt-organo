# 0018 — DATA INAMOVIBLE niche taxonomy: keep-as-is + always-recommend-changes + metabolic discriminator

- **Date:** 2026-06-11
- **Status:** accepted
- **Decided by:** Emmanuel (ratifying the composite-audit verdict via governance gate gp-2026-06-11-niche-taxonomy-q30)
- **Affects:** `rag_index/` taxonomy, `domain-knowledge-curator`/corpus-classifier, Test 5, the RIL meta-loop

## Context

A team-biomedic (held-out Q30 / Nat Witt P2) argued ocular biology should not be a niche separate
from biophysics/biomechanics, that signaling may take metabolism for granted, and that ocular could
be reframed as "morphology and physiology." A composite-audit (Mode 1, 3 independent lenses —
modeling-coherence, data-engineering, substrate-evidence) returned a UNANIMOUS keep-as-is and rejected
the merge, because the project already separates two orthogonal axes (13 RAG data-niches RN1–RN13 ×
6 scientific-domain niches N1–N6) and merging ocular would collapse Test 5 (cross-field operation
needs a structurally distinct field to bridge to). See
`docs/findings/2026-06-11-q30-niche-taxonomy-resolution.md`.

## Decision

1. **Keep-as-is** for the DATA INAMOVIBLE niche taxonomy: the two-axis design stands; ocular (N5)
   remains a distinct scientific-domain niche (protects Test 5). The ocular→biophysics merge is rejected.
2. **Always-recommend-changes (non-negotiable):** keeping the taxonomy fixed does NOT freeze it. The
   corpus-classifier continuously **audits** categorizations and MAY **recommend where to change**
   (`corpus_classifier.audit_categorization`), and any agent MAY raise a governance-proposal to revise
   the taxonomy. The taxonomy is `revisable: true` = **human-gated mutable**: recommend freely, apply
   only via a human gate (ADR-0013). This is the explicit affordance Emmanuel required.
3. **Metabolic discriminator (accepted, applied additively):** `metabolic_role`
   (`signaling-scaffold | metabolic-general-function | null`) added to the `corpus_manifest.json`
   record schema — a field, not a 14th niche — flagging when a signaling model omits metabolic
   preconditions. The "morphology independent of tissue" need is met by RN9 on the data axis.

## Alternatives considered

- Merge ocular into biophysics (the biomedic's proposal) — REJECTED: collapses Test 5; facet/collinearity
  loss; backwards-incompatible.
- Freeze the taxonomy entirely (no recommendation path) — REJECTED by Emmanuel: the system must always
  be able to recommend changes.
- A 14th metabolic niche — REJECTED: prueba pequeño; a schema discriminator captures the gap.

## Consequences

- The two-axis taxonomy is the ratified baseline; Test 5 instrumentation is preserved.
- The corpus-classifier's audit/recommendation path is a standing capability, human-gated.
- The N5 partner-field decision (cardiology vs ophthalmology, PROJECT_SCOPE §11) remains a separate
  open decision — not pre-empted by this ratification.

## Evidence

`docs/findings/2026-06-11-q30-niche-taxonomy-resolution.md`; `substrate_calibration/records/claim_20260611_000000_niche-taxonomy-audit.json`;
governance `gp-2026-06-11-niche-taxonomy-q30` (approved); `rag_index/niches.json` (revisable); ADR-0013/0015/0017.

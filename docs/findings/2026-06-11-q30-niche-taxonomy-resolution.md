# Finding — Q30 niche-taxonomy critique: composite-audit resolution

- **Date:** 2026-06-11
- **Status:** **RATIFIED 2026-06-11 by Emmanuel (ADR-0018).** Audit UNANIMOUS keep-as-is + 2 amendments; the human gate (gp-2026-06-11-niche-taxonomy-q30) was approved. Keep-as-is for the DATA INAMOVIBLE taxonomy + metabolic discriminator accepted + the **always-recommend-changes** affordance made explicit (the classifier may recommend where to change at any time, human-gated).
- **Origin:** team-biomedic critique (Nat Witt interaction P2; logged as held-out `Q30`).
- **Method:** `corpus-classifier` proposal + `composite-auditor` Mode 1 split-and-vote (3 independent adversarial lenses). CLAUDE.md §7 (audits use composite-auditor, not a single-LLM pass).

## The critique (biomedic)

(1) Ocular biology should not be a niche separate from biophysics/biomechanics, since systems modeling is governed by those (diffusion/biomechanics) laws. (2) The cell-signaling niche may take metabolic pathways for granted (relevant for general function, not as scaffold). (3) Reframe "ocular biology" as "morphology and physiology, independent of tissue".

## Verdict — UNANIMOUS (3/3): KEEP-AS-IS, REJECT the merge

| Lens | Verdict | Confidence | Key reason |
|---|---|---|---|
| modeling-coherence | keep-as-is | 0.82 | Shared laws ≠ same niche; the shared-law continuum already IS the 13 RAG data-niches (RN3/RN6/RN7). A model is its *instantiation* (params/geometry/BCs), not its operator set. |
| data-engineering / retrieval | keep-as-is (dual-axis) | 0.82 | Empirically: `.json` maps to 12/13 niches, `.csv` to 9 → extension is not a clean key; data-niche = **modality+role** is the right primary partition; scientific-domain is an orthogonal filter. Merging ocular = facet loss. |
| substrate-evidence / scope-fit | keep-as-is | 0.83 | **Merging ocular collapses Test 5** — cross-field operation needs a structurally distinct field to bridge to. Merging deletes the test's measurement substrate. |

**Core diagnosis:** the biomedic is *right that the laws are shared* but conflates the **physics-law/data axis** (the 13 RAG data-niches, RN1–RN13) with the **scientific-domain axis** (the 6 PROJECT_SCOPE niches, N1–N6). The project already separates these; ocular-ness is a domain/bio-context tag, not a data-niche. **Root cause is partly a communication failure on our side** — the biomedic was shown N1–N6 without the RN1–RN13 axis surfaced.

## Two amendments ACCEPTED (real catches)

- **(B) Metabolic discriminator (applied, additive).** RN3/RN4 did not distinguish metabolism-as-signaling-scaffold from metabolism-as-general-function (ATP/redox gating signaling competence). Added `metabolic_role: signaling-scaffold | metabolic-general-function | null` to the `corpus_manifest.json` record schema, with an auto `gap_flag` when a signaling model omits metabolic preconditions. A schema field, NOT a 14th niche (prueba pequeño).
- **(A) Morphology reframe — already available.** "Morphology/physiology independent of tissue" is exactly RN9 (morfología emergente y topología) on the data axis. The biomedic re-intuited the RN axis. "Reframe N5 as morphology/physiology" is **rejected** as a scientific-domain change (it would neuter the CLAUDE.md §3 scope filter), but the underlying need is met by RN9.

## What was applied additively (no taxonomy reorg, no human gate needed)

- **Label-collision fix:** `evaluation/held_out_set_v1.json` niche tags renamed `N1…N13` → `RN1…RN13` (they were the data-niches, colliding with PROJECT_SCOPE N1–N6). A bug introduced in Cycle 2.
- **`rag_index/niche_database_crosswalk.json`** (declared feeds + proposed enrichments flagged).
- **`rag_index/interaction_table.json`** (RN10 promoted to a first-class queryable object).
- **`corpus_manifest.json`** schema enriched to the 5-axis model + entity tiers + `metabolic_role`.

## What is HUMAN-GATED (not self-applied)

The taxonomy **decision** (ratify keep-as-is on both axes) is queued as governance-proposal
`gp-2026-06-11-niche-taxonomy-q30` (`self_applied: false`). The taxonomy is `revisable: true` but
that means **human-gated mutable**, not agent-mutable (ADR-0013/0015/0017). The N5 partner-field
decision (cardiology vs ophthalmology, PROJECT_SCOPE §11) is a separate live decision — not pre-empted.

## Substrate evidence

Test 1 (multi-agent reasoning with §5 contracts), Test 4 (composite-audit calibration), Test 5
(the verdict PROTECTS the cross-field test). Claim record:
`substrate_calibration/records/claim_20260611_000000_niche-taxonomy-audit.json`. HTML report:
`reports/rag-categorization-and-niche-audit-v1.html`.

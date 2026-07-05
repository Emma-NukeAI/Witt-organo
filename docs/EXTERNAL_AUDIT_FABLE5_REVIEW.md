# External review (Fable 5, 2026-07-05) — opinion on the project brief

> External auditor agent (model: Fable 5) reviewing `docs/EXTERNAL_AUDIT_BRIEF.md`. It received ONLY the brief (not the repo), gave a candid supervisory opinion, and did **not** trigger any refusal/flag. Verbatim below.

---

## 1. Overall impression
Unusually disciplined design for a research-support system (protected source of truth, human gates, anti-fabrication checks, honest confidence language — better than most teams manage). Central concern is **not soundness but proportionality**: the accountability machinery is large relative to a single zebrafish POC whose core biological claim is still entirely unproven. Governance is strong on *form* (structure, provenance, process) but thin on *evidence that the form actually produces more correct/useful answers*. "A well-architected accountability layer wrapped around a scientific result that does not yet exist."

## 2. Architecture soundness
Robust backbone. Best decisions: read-only-by-default store with explicit specified mutations; **deterministic checks separated from the AI** (single strongest decision — verification that cannot hallucinate); "not in the KB is a prompt to learn, gated on approval." Weaknesses: (a) deterministic checks cover **syntax/provenance, not semantic correctness** — a resolvable ID can still be the *wrong* ID; (b) **retrieval quality unmeasured** (no recall@k / known-item tests) — load-bearing gap; (c) single source of truth = single point of failure, **no error-in-store detection** (only the same human-gated mutation path); (d) human gate = throughput bottleneck at scale.

## 3. Governance adequacy (weakest points, ranked)
1. **Reviewer independence asserted, not demonstrated.** If the 3 adversarial reviewers are instances of the same base model, their errors are **correlated** → ≈ one vote with extra cost ("panel is theater" unless measured disagreement proves otherwise). Need: different model families? inter-reviewer disagreement rate?
2. **Calibration has sample-size + circularity problems.** A single POC likely lacks enough resolved outcomes for meaningful ECE (early numbers = noise). And the thing being calibrated is the self-report that the project itself calls "not ground truth" — fine if explicit, but state how many labeled outcomes exist before treating a calibration number as real.
3. **Human-gate rubber-stamping uncontrolled.** No described defense against approval fatigue; gate *quality* unmeasured (are approvals audited after the fact? rejections tracked?).
4. **"Invoke-or-justify" invites boilerplate** unless skip-justifications are themselves periodically audited.
Keep: the documentation-consistency gate (cheap, high-value).

## 4. Gaps and risks
- Biological result **entirely open** → risk of *narrative drift* (polished apparatus creates impression of a validated program with zero lab confirmation). Guard the language hard.
- Retrieval/KB coverage untested (unknown false-negative rate on "do we already know this?").
- Correlated-reviewer failure (biggest governance risk).
- Error-in-store persistence (no post-hoc detection of an approved-but-wrong fact).
- **"Exercised end-to-end" ≠ validated** — execution is not validation; wants the actual defect list + disposition.
- **Security hardening of hosted services is a live integrity risk, not a backlog item** — an externally reachable/mutable canonical store voids the "inamovible" guarantee. Higher priority than framed.
- Generation half unbuilt → its real risk (flooding the human gate with plausible proposals, moving the bottleneck) can't be assessed yet.
- Under-specified to assess: held-out set size/provenance (+ leakage); # resolved calibration outcomes; # and independence of reviewers; retrieval metrics.

## 5. Honesty of self-assessment
Broadly honest, better than typical. Push-backs: "implemented and exercised end-to-end" risks reading as "validated" (maturity-of-plumbing, not correctness); "calibration discipline" implies a working measurement the sample size may not support (call it "scaffolding populated"); the multi-reviewer audit is presented as a strong control but its strength depends on unproven independence. Apply the project's own measured/preliminary/not-established vocabulary to the **substrate's own maturity** as strictly as to the biology.

## 6. Proportionality (most disagreement)
The substrate layer appears to **violate "test small before building well."** For a single-organism POC with an unvalidated biological claim, the team stood up a knowledge graph + vector + sparse retrieval, hosted graph DB + object store + ingest service, multi-agent roster, calibration subsystem, ADR discipline, several deterministic gates, and a separate generation repo — a *platform built ahead of the evidence that the platform's methods improve outcomes*. Over-building the **safety spine** (read-only store, human gates) is defensible (integrity failures are expensive to unwind); the **retrieval/audit/calibration superstructure is feature-weight** — that's where proportionality bites. Wants evidence each control *caught something a simpler control would have missed* before it's kept.

## 7. Top recommendations (ranked)
1. **Measure the controls, don't just run them** — retrieval recall on a known-item set, inter-reviewer disagreement rate, count of resolved calibration outcomes. Until they exist, treat audit + calibration as *scaffolding*, not validation. (Highest value, lowest cost.)
2. **Prove reviewer independence or stop calling it a three-vote gate** — different model families, log disagreements; if near-zero, collapse to one and admit it.
3. **Prioritize security hardening of the hosted store now** — integrity control, not backlog.
4. **Freeze substrate feature growth until the biology moves** — apply "test small" to the substrate itself.
5. **Add error-in-store detection** — periodic re-verification / contradiction scan (the human gate protects entry, not persistence).

*Would sharpen the review:* held-out set size/provenance, # labeled calibration outcomes, reviewer config + measured agreement, retrieval metrics, the end-to-end defect list.

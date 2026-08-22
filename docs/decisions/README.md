# Architecture Decision Records (ADRs)

This directory holds Architecture Decision Records for the `witt-organogenesis` project — short, dated, immutable notes capturing **why** a non-obvious architectural choice was made.

ADRs are not project documentation in the usual sense. They are forensic records: when a future collaborator (or future-you) asks "why did we do X this way?", an ADR is where the answer lives. The current state of the repo lives in code and live docs; the *why* of past choices lives here.

## When to write an ADR

Write one when **all** of the following are true:

1. The decision is non-obvious — there were defensible alternatives.
2. The decision is hard to reverse — it shapes downstream work.
3. Future collaborators will need the reasoning to evaluate or revise it.

Examples that warrant an ADR:
- Choosing one orchestration pattern over another for a substrate-instrumented agent.
- Recalibrating a substrate validation threshold because of new evidence.
- Selecting a Tier 2 reasoning framework as the default for a niche.
- Choosing one Tool Universe layer (skill / MCP tool / SDK) over another for a specific workflow.

Examples that do NOT warrant an ADR:
- Renaming a file (use git history).
- Adding a new collaborator (use access logs / contact docs).
- Updating a dependency to a newer compatible version.

## How to add one

1. Copy the template below into a new file: `NNNN-short-slug.md` where `NNNN` is the next zero-padded sequence number (`0001`, `0002`, …).
2. Fill the sections.
3. Set `Status: proposed` initially. Update to `accepted`, `rejected`, `superseded by NNNN`, or `deprecated` as the decision evolves. Never delete an ADR — supersede it.
4. Commit. ADRs are part of the repo's history.

## Template

```markdown
# NNNN — <short title>

- **Date:** YYYY-MM-DD
- **Status:** proposed | accepted | rejected | superseded by NNNN | deprecated
- **Decided by:** <name(s)>
- **Affects:** <scope: which niches, which agents, which phase>

## Context

What is the situation that requires a decision? What constraints, evidence,
or prior decisions frame it?

## Decision

What did we decide? State it as a single declarative paragraph.

## Alternatives considered

What other options were on the table? Why were they not chosen?

## Consequences

What downstream effects does this decision have? What does it make easier?
Harder? What is now committed that wasn't before?

## Evidence

Links to the stress-test brief, PROJECT_SCOPE sections, substrate test results,
or external references that informed the decision.
```

## Existing ADRs

| ADR | Date | Title | Status |
|-----|------|-------|--------|
| [0001](0001-cascade-protocol-4-scenarios.md) | 2026-05-12 (retroactive) | Cascade protocol uses 4 scenarios per stage (Mode A×B × hipo×KO) | Accepted |
| [0002](0002-version-preservation-rule.md) | 2026-05-12 (retroactive) | Version preservation: never modify prior session outputs | Accepted |
| [0003](0003-decouple-paradigm-as-purity-test.md) | 2026-05-12 (retroactive) | Decouple paradigm: PASA / PARCIAL / FALLA tripartite | Accepted |
| [0004](0004-squidiff-as-transcriptomic-gate.md) | 2026-05-13 (patched 2026-05-14) | Adopt Squidiff as transcriptomic hypothesis gate | Accepted |
| [0005](0005-test-claim-language-discipline.md) | 2026-05-14 | Test claim language: "satisfied" vs "case capture" vs "infrastructure populated" | Proposed |
| [0006](0006-catalog-agent-invocation-discipline.md) | 2026-05-14 | Catalog agent invocation discipline + decision matrix + §11 preflight | Proposed |
| [0007](0007-html-report-mandatory-at-conclusion.md) | 2026-05-14 | HTML report mandatory at conclusion + 4 TYPES + simulation-backed-viz hard rule + visual-offer reflex | Accepted |
| [0008](0008-ceded-slot-hypothesis-generator.md) | 2026-06-10 | Ceded Phase-I slot: +hypothesis-generator, −investor-relations-drafter; keep ip-patent-watcher | Accepted |
| [0009](0009-retrospector-and-ril-subsystem.md) | 2026-06-10 | retrospector agent + Reasoning-Improvement Loop as a subsystem (cedes risk-register-agent) | Accepted |
| [0010](0010-rename-bundle-to-gwt-v1.1.md) | 2026-06-10 | Rename the umbrella bundle v2.5 → GWT v1.1 (label reset; v2.x history preserved) | Accepted |
| [0011](0011-eps-must-be-measured.md) | 2026-06-11 | EPS must be measured (noise-probe before any improvement claim) | Accepted |
| [0012](0012-reactive-calibration-rolling-k6.md) | 2026-06-11 | Reactive calibration (rolling K=6 + auto-cap) supersedes quarterly-only | Accepted |
| [0013](0013-governance-proposal-meta-loop.md) | 2026-06-11 | Governance-proposal meta-loop: the agent proposes, the human applies (Sakana safety lesson) | Accepted |
| [0014](0014-outcome-vocab-and-per-stream-auto-cap.md) | 2026-06-11 | Outcome vocabulary (positive/negative/unfalsifiable) + per-stream auto-cap regime | Accepted |
| [0015](0015-rag-index-structure-backend-open.md) | 2026-06-11 | RAG index structure-first (13 niches + 9 DBs); backend OPEN (FAISS/Neo4j/graphify/hybrid via spike) | Accepted (structure) |
| [0016](0016-ril-program-charter.md) | 2026-06-11 | RIL_PROGRAM.md as the canonical Reasoning-Improvement-Loop charter | Accepted |
| [0017](0017-corpus-classifier-agent.md) | 2026-06-11 | Corpus-classifier as an operational mode of domain-knowledge-curator (categorize + audit, human-gated) | Accepted |
| [0018](0018-niche-taxonomy-keep-as-is-recommend-always.md) | 2026-06-11 | DATA INAMOVIBLE niche taxonomy keep-as-is + always-recommend-changes + metabolic discriminator | Accepted |
| [0019](0019-rag-backend-v1-sparse-flat-versioned.md) | 2026-06-11 | RAG backend v1: flat versioned human-gated sparse retriever (dense/hybrid gated) | Accepted |
| [0020](0020-hosted-graphrag-architecture.md) | 2026-06-11 | Hosted GraphRAG (self-host Neo4j + graphify, SPECTER2+general embeddings, MCP access; RAG_Techniques-informed pipeline) | Accepted (deploy next) |
| [0021](0021-raw-store-provenance-to-raw-minio-hybrid.md) | 2026-06-12 | Raw store + provenance-to-raw (MinIO, hybrid: public source-pointer / private mirror; `fetch_raw`) | Accepted |
| [0022](0022-answer-pipeline-di-first-mcp-fallback-audit-reingest.md) | 2026-06-13 | Answer pipeline: DI-first retrieval, Tool-Universe fallback, composite-audit gate, human-gated re-ingest | Proposed |
| [0023](0023-replay-as-regression-and-no-regression-prefilter.md) | 2026-06-18 | Replay-as-regression + no-regression governance pre-filter + failure-derived regression-case corpus (R1) | Accepted |
| [0024](0024-admissibility-predicate-and-bayes-purity-tier-weight.md) | 2026-06-18 | Explicit admissibility predicate H(c) + Bayes-purity verified_tier_weight + EVPI placeholder (R2) | Accepted |
| [0025](0025-accountability-checks-framework-and-agents-invoked-gates.md) | 2026-06-18 | Accountability checks: §4 framework-citation gate + §11 agents_invoked gate (R3) | Accepted |
| [0026](0026-unified-world-state-transition-and-tooluniverse-directive.md) | 2026-06-18 | Unified World-State-Transition claim contract (do-typed) + explicit Tool Universe Path-B directive (R4) | Accepted |
| [0027](0027-accountability-detection-hardening-from-adversarial-validation.md) | 2026-06-22 | Detection-layer hardening of MITAD_A from the 2026-06-22 adversarial validation | Accepted |
| [0028](0028-lens-validity-weighting-and-perspective-diverse-panels.md) | 2026-06-23 | Lens-validity weighting + perspective-diverse Self-Consistency panels | Accepted |
| [0029](0029-data-inamovible-add-signaling-induction-markers.md) | 2026-06-23 | DATA INAMOVIBLE: add 5 pronephros upstream-signaling / induction markers (human-gated ADD) | Accepted |
| [0030](0030-compute-ece-aggregate-captured-not-satisfied.md) | 2026-07-04 | compute_ece Test-4 language: a cross-sectional snapshot is "aggregate-captured", never "satisfied" | Accepted |
| [0031](0031-multi-family-composite-auditor-panel.md) | 2026-07-05 | Multi-family composite-auditor panels (reviewer independence) | Accepted |
| [0032](0032-measure-the-controls-retrieval-and-store-integrity.md) | 2026-07-05 | Measure the controls: retrieval eval + store-integrity scan as standing gates | Accepted |
| [0033](0033-security-hardening-hosted-store-integrity-control.md) | 2026-07-05 | Security hardening of the hosted store is an integrity control, not a backlog item | Proposed — DEFERRED (parked) |
| [0034](0034-freeze-substrate-feature-growth-until-controls-earn-their-weight.md) | 2026-07-05 | Freeze substrate feature growth until each control earns its weight (and biology moves) | Accepted |
| [0035](0035-di-add-level2-induction-cascade-ids.md) | 2026-07-11 | DATA INAMOVIBLE ADD: +23 pronephros-induction cascade IDs from the Level-2 Tool Universe fallback | Accepted |
| [0036](0036-verify-output-reingest-candidate-not-fabrication.md) | 2026-07-11 | verify_output: a live-verified out-of-store ID is a re-ingest candidate, not a fabrication fail | Accepted |
| [0037](0037-closing-composite-audit-corrections.md) | 2026-07-11 | Closing composite-audit of the 2026-07-11 session: all claims REVISE, one real bug, corrections applied | Accepted |
| [0038](0038-honesty-bundle-openai-judge-fabrication-fix.md) | 2026-07-11 | Honesty bundle: cross-provider (OpenAI) judge, judge-fabrication fix, deterministic-first scoring | Accepted |
| [0039](0039-data-inamovible-mcp-reproducible-venv-portable-config.md) | 2026-07-19 | data-inamovible MCP: run on a reproducible interpreter (uv.lock) + portable versioned `.mcp.json` | Accepted |
| [0040](0040-data-inamovible-perfection-audit-cli-primary-team-access.md) | 2026-07-19 | data-inamovible perfection audit: in-band degradation marker, structural human gate, `witt-di` CLI (hybrid CLI-primary), team access via local `.secrets` | Accepted |
| [0041](0041-materialize-tier-weights-and-register-europepmc.md) | 2026-07-20 | Re-ingest to materialize tier weights + register EuropePMC as a source (human-gated) | Accepted |
| [0042](0042-corpus-0004-rn3-ingest-and-relational-data-rn11-placement.md) | 2026-07-21 | First RN3 corpus record (CORPUS-2026-0004, human-gated ingest) + relational genotype-phenotype data places under RN11 | Accepted |
| [0043](0043-degraded-envelope-end-to-end.md) | 2026-08-09 | El marcador `degraded` viaja en un SOBRE `{degraded, n_hits, hits}` de punta a punta (y el bundle carga un enum de 4 literales, nunca nullable) | Accepted |
| [0044](0044-bundle-identity-run-id.md) | 2026-08-09 | Identidad de bundle: nombre por `run_id`, `stamp` real, `bundle_identity.sha256` | Accepted |
| [0045](0045-ingest-gate-rejection-registry-and-serialized-approve.md) | 2026-08-09 | El gate del ingest service registra sus decisiones: rechazo archivado (nunca borrado), `/approve` serializado, `created_at` + orden FIFO real | Accepted |
| [0046](0046-html-report-derogation-webapp-era.md) | 2026-08-04 | Derogación CON ALCANCE del reporte HTML obligatorio (§5/§7): las corridas de la era webapp no emiten HTML; su rastro es el registro congelado, y los reportes históricos se indexan en la webapp | Accepted |
| [0047](0047-webapp-backend-architecture-decisions.md) | 2026-08-09 | Decisiones de arquitectura del backend webapp (fundador, 2026-08-09) + exposición del bloque 1.4 | Accepted |
| [0048](0048-query-service-http-read-front-door.md) | 2026-08-09 | `query_service`: el front door HTTP de solo lectura para la webapp (espejo del sobre, status NO-SPEND, identidad de 5 cuentas, índice de históricos) | Accepted |
| [0049](0049-audit-always-composite-auditor-invokable.md) | 2026-08-04 | Auditoría en el 100% de las corridas (la máquina de estados se reforma) + `composite-auditor` se vuelve un componente invocable con vocabulario homologado | Accepted |
| [0050](0050-run-model-event-log-frozen-record.md) | 2026-08-09 | Modelo de corrida + bitácora única de eventos + registro congelado persistido en el backend | Accepted |
| [0051](0051-two-pass-confidence-gate-tokenusage.md) | 2026-08-10 | Dos pasadas con decisor de fallback por confianza, `confidence_by_subclaim` + `absence_kind`, citas tipadas y `TokenUsage` medido (bloque 4) | Accepted |
| [0052](0052-ingest-write-queue-and-sighted-gate.md) | 2026-08-10 | Cola de escritura serializada CROSS-PROCESO + el gate humano deja de firmar a ciegas (bloque 5) | Accepted |
| [0053](0053-precedent-layer-disjoint-series.md) | 2026-08-10 | La capa de precedente: índice separado, admisibilidad distinta, series de citas disjuntas por construcción (bloque 6) | Accepted |
| [0054](0054-ingest-e2e-first-gated-prune-volume-fix.md) | 2026-08-10 | Estreno e2e del gate hosted (push-back funcionando), el PRIMER prune human-gated, y el estado del gate al volumen | Accepted |
| [0055](0055-lote-backend-01a-contract-additions.md) | 2026-08-15 | LOTE BACKEND 01·A: adiciones de contrato reportadas por la webapp (M1–M3 construidos) | Accepted |
| [0056](0056-lote-backend-02-unified-sessions-usage-epistemic-list.md) | 2026-08-15 | LOTE BACKEND 02: sesiones unificadas en el ingest (dos puertas, una identidad) + agregados de consumo + resumen epistémico congelado + filtro declarado + puerta del historial | Accepted |
| [0057](0057-production-defects-external-query-trapped-confidence.md) | 2026-08-16 | Defectos de producción de las dos corridas reales: la Ruta B buscaba en español (0 papers) y la confianza viajaba atrapada como texto (LOTE-03) | Accepted |
| [0058](0058-approve-decline-honest-negative-findings.md) | 2026-08-16 | `APPROVE_DECLINE`: la declinación honesta correcta APRUEBA (decisión del hallazgo 3 de LOTE-03) | Accepted |
| [0059](0059-zfin-native-path-b-source.md) | 2026-08-19 | ZFIN (fenotipos nativos de pez cebra) como fuente de Ruta B: Tool Universe deja de ser un recado | Accepted |
| [0060](0060-section5-contract-fields-in-frozen-record.md) | 2026-08-20 | Los tres campos §5 que faltaban: `framework_applied` con sección resuelta por tabla, `agents_invoked` derivado, `alternatives_considered` | Accepted |
| [0061](0061-declared-plan-planner-preflight.md) | 2026-08-20 | El plan declarado: el preflight §11 se vuelve componente, y `not-assessed` se convierte en juicio | Accepted |
| [0062](0062-tooluniverse-sdk-rejected-pubmed-layer0.md) | 2026-08-20 | Tapón 1·B: el SDK de Tool Universe en el contenedor se MIDE y se RECHAZA; PubMed entra por Layer 0 | Accepted |
| [0063](0063-plan-route-store-consultation.md) | 2026-08-22 | El plan rutea: corrida de evidencia vs consulta del sistema (plan v2) | Accepted |
| [0064](0064-m5-ratings-append-only-and-declared-power-calibration.md) | 2026-08-22 | M5 ratings append-only sobre el registro + calibración ECE con poder DECLARADO | Accepted |

---

*Format adapted from Michael Nygard's "Documenting Architecture Decisions" (2011), tailored to the substrate-validation discipline of the Witt × Organogenesis project.*

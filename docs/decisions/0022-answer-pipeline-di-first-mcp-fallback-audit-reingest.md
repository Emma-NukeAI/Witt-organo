# ADR-0022 — Answer pipeline: DI-first retrieval, Tool-Universe fallback, audit gate, human-gated re-ingest

- **Status:** Proposed (Emmanuel, 2026-06-13) — design from the 2026-06-13 session, motivated by the Phase-1 finding below.
- **Relates:** ADR-0020 (hosted GraphRAG), ADR-0021 (raw store + `fetch_raw`), ADR-0009 (retrospector / RIL), ADR-0006 (composite-auditor invocation discipline), ADR-0008 (hypothesis-generator). CLAUDE.md §6 (MCP/Tool-Universe layers), §7 (human gates, anti-fabrication, composite-auditor).

## Context

The Phase-1 POC (2026-06-13) re-grounded the pronephros minimal-set hypothesis through the live DATA INAMOVIBLE and surfaced a structural limit: **the corpus indexed is the *catalog*** (niches / databases / datasets / verified entities), **not papers**. A negated (contradiction) query ran and returned nothing — not because the claim is sound, but because there is **no literature layer to adjudicate it**. Today, "not in the DATA INAMOVIBLE" is effectively a dead end for question-answering.

The founder's requirement (2026-06-13): the catalog index should be a *guide* — once it identifies *which* asset is relevant, an agent should be able to **fetch the full paper** and reason over it; and when the DATA INAMOVIBLE has nothing, the agent must **fall back to external search (Tool Universe)** rather than stop. Crucially, every fetched fact must be **audited**, and audited external knowledge worth keeping should be **proposed (human-gated) back into the store** — so the substrate **reinforces itself each run** (the Witt thesis: grows with use).

## Decision

A four-component answer pipeline, built mostly by **wiring existing pieces** (`chunk_document.py`, `add_dataset.py` → human gate → `approve_dataset.py` → `ingest.py`; `resolve_id`, `rag_backend.query`, `fetch_raw`; agents `literature-monitor`, `domain-knowledge-curator`, `composite-auditor`, `hypothesis-generator`):

1. **Two-path retrieval — absence in DI is NEVER a stopper.**
   - **Path A (DATA INAMOVIBLE first):** `query_data_inamovible` + `resolve_identifier`; if a hit points to a paper, drill to full text (component 2).
   - **Path B (fallback, when A is insufficient):** Tool Universe MCP literature (`PubMed_search_articles`, EuropePMC, `tooluniverse-literature-deep-research`). Owner: `literature-monitor` (Cat 4). Triggered by an explicit insufficiency signal from A, never by default.

2. **`fetch_paper` (NEW primitive) — drill to the *full* paper, not just the chunk.** Given a DI chunk/doc pointer (→ `raw_ref` → full doc) **or** an external PMID/DOI/URL, retrieve the full text, **cache the raw response** at `mcp_cache/raw_paper_<id>_<YYYYMMDD>.{pdf,txt,json}` (§7.9 — raw, not an AI summary), then `chunk_document.py` it. Extends the ADR-0021 drill-down from dataset-bytes to literature.

3. **Retrieval-audit gate = `composite-auditor` (NOT a single LLM).** For any brought-back evidence (Path A or B), `composite-auditor` Mode 1 (split-and-vote, **≥3** adversarial auditors, per §7 / ADR-0006) double-checks:
   - **(a) absence re-check:** independently confirm the fact is genuinely *not already* in the DATA INAMOVIBLE (`resolve_id` + a second/negated query) — catches "we missed it in DI."
   - **(b) veracity check of external info:** verify against the actual source — PMID/DOI/accession resolves, the claim is present in the fetched text, no hallucinated identifiers (§7.9 raw cached). Verdict **APPROVE / REJECT**. Only APPROVED evidence flows into the answer. (This resolves the founder's "un agente auditor" into the project's mandated composite form — single-LLM audit is a §7 violation.)

4. **Human-gated re-ingest — the self-reinforcement loop.** If APPROVED external evidence is **DI-worthy** (in-scope niche, durable, reusable), `domain-knowledge-curator` auto-generates a **PROPOSED** corpus record via the existing path (`chunk_document` + `add_dataset` semantics: source-pointer `raw_ref` + `resolve_id`-gated entities + `approval_chain=pending_review`). It **stops at the human gate** (`approve_dataset.py` → embed → `ingest.py`). The loop **never auto-ingests** and **never mints IDs**. `retrospector` logs each loop iteration (RIL ledger).

## Consequences

- **DI stops being a hard dependency for answering.** "Not in DI" becomes a *trigger to learn*, not a stop — exactly the founder's requirement.
- **The store self-reinforces, safely.** Audited + human-gated growth means the corpus enlarges with use without being polluted (anti-fabrication + composite-audit + human gate all hold).
- **New paid paths** (Tool Universe lit search, full-text fetch, embeddings on re-ingest) — authorized (2026-06-13); bounded and raw-cached (§6/§7.9). The bigger meter remains agent reasoning, not embeddings.
- **New code (small):** `fetch_paper.py`; an answerer orchestrator (Path A→B→audit→answer→queue-proposal; `hypothesis-generator`-owned); a `propose_from_external` wrapper over `add_dataset`/`chunk_document`; a `composite-auditor` *retrieval-audit* recipe (mode prompt). No backwards-incompatible change to existing agents → ADR (this) satisfies §7.
- **Risk — external veracity / source rot:** mitigated by the ≥3 composite audit, §7.9 raw caching (sha256), and the human gate before anything enters the store. A REJECTED fact is recorded (gap_flag), not silently dropped.

## First slice (prueba pequeño — build + validate this before the rest)

The exact question that just failed in Phase 1: **essentiality/sufficiency of `osr1` / `prkci` (NOT_FOUND in DI v1) for pronephros**. End-to-end: Path A (DI miss, already shown) → Path B (Tool Universe PubMed) → `fetch_paper` (full text + raw cache) → `composite-auditor` (absence re-check + veracity) → `propose_from_external` (pending_review record) → **STOP at human gate**. Proves all 4 components on a real question and closes the Phase-1 literature gap. No auto-ingest; Emmanuel runs `approve_dataset` if the proposal is sound.

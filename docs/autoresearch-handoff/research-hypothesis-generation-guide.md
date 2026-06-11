# Research Paper Hypothesis Generation — Reference Guide

A reference for building a system that reads research papers and generates valid, evidence-grounded hypotheses.

> **Core principle:** An LLM can help generate *plausible* hypotheses, but it cannot guarantee they are *valid*. Scientific validity requires evidence, experimental design, testing, and peer review — not the model itself.

---

## 1. What a good system should produce

A strong hypothesis-generation output includes:

- Summary of existing evidence
- Gaps in the literature
- Candidate hypothesis
- Supporting evidence
- Contradicting evidence
- Testable predictions
- Proposed experiment
- Required controls
- Possible confounders
- Confidence level
- Citations

### Example output structure

```
Hypothesis:
Compound X may reduce inflammatory signaling in cell type Y by modulating pathway Z.

Rationale:
- Paper A shows X affects pathway Z.
- Paper B shows pathway Z is elevated in cell type Y during inflammation.
- Paper C reports that inhibition of Z reduces cytokine expression.

Contradictory Evidence:
- Paper D found no effect of X in a related cell type.
- Paper E suggests toxicity at high concentrations.

Testable Prediction:
If the hypothesis is true, treatment with X should reduce IL-6 and TNF-alpha
expression in cell type Y under inflammatory stimulation.

Experiment:
- Culture cell type Y.
- Stimulate with LPS or relevant inflammatory trigger.
- Treat with multiple concentrations of X.
- Measure cytokine expression by qPCR/ELISA.
- Include vehicle control, positive control, and toxicity assay.

Confidence:
Moderate, because evidence supports the pathway relationship but direct
validation in cell type Y is missing.
```

This kind of structured reasoning is far better than simply asking *"Create a hypothesis."*

---

## 2. Best technical setup

| Layer | Components |
|---|---|
| **Paper sources** | PubMed, arXiv, Semantic Scholar, CrossRef, internal PDFs |
| **Processing** | PDF parsing, OCR if needed, reference extraction, section splitting |
| **Databases** | Vector DB for semantic search; keyword index for exact biomedical/technical terms; SQL DB for metadata; optional knowledge graph for entities and relationships |
| **Models** | Embedding model for retrieval; reranker for better evidence selection; LLM for synthesis; optional fine-tuned model for structured hypothesis output |
| **Evaluation** | Expert review, citation checking, novelty checking, contradiction search, experimental feasibility scoring |

### Domain-specific tools (biomedical)

- PubMed API
- BioBERT / SciBERT embeddings
- SPECTER embeddings for papers
- Semantic Scholar API
- UMLS / MeSH terms
- ChEMBL
- UniProt
- STRING database
- ClinicalTrials.gov

### General science

- arXiv
- OpenAlex
- CrossRef
- Semantic Scholar
- Dimensions (if available)
- Web of Science / Scopus (if licensed)

---

## 3. Data preparation matters a lot

The model is only as good as the data pipeline.

Split documents by **section**, not by blind fixed-size chunks:

- Title
- Abstract
- Introduction
- Methods
- Results
- Discussion
- Figures / Tables
- References

> Do not just chunk blindly every 1,000 tokens. Better chunking improves retrieval.

### Recommended metadata

```json
{
  "title": "Paper title",
  "authors": ["A", "B"],
  "year": 2023,
  "journal": "Journal Name",
  "doi": "10.xxxx/example",
  "section": "Results",
  "topic": "inflammation",
  "species": "mouse",
  "method": "RNA-seq",
  "sample_size": 32
}
```

Metadata enables filtered searches such as:

- "Only retrieve human studies after 2020."
- "Prioritize randomized controlled trials."

---

## 4. Evaluation is non-negotiable

For serious domain work, create an evaluation set.

### Example evaluation questions

- What are the known mechanisms linking protein X to disease Y?
- Which papers contradict the claim that compound A inhibits pathway B?
- What are the strongest open questions in this subfield?
- Generate a hypothesis involving mechanism M, but cite at least three supporting studies and one contradictory study.

### Scoring rubric

| Metric | Description |
|---|---|
| Factuality | Are claims accurate? |
| Citation correctness | Do citations actually support the claims? |
| Completeness | Did it miss important work? |
| Novelty | Is the hypothesis non-trivial? |
| Testability | Can it be experimentally tested? |
| Uncertainty | Does it avoid overclaiming? |
| Safety / ethics | Any problematic recommendations? |

---

## 5. Recommended starting stack

### Local / open-source stack

| Component | Options |
|---|---|
| LLM | Llama, Qwen, Mistral, Gemma, DeepSeek |
| Serving | Ollama (easy local), vLLM (production) |
| Embeddings | bge-large, e5-large, nomic-embed, SPECTER/SciBERT-style for papers |
| Vector DB | Qdrant, Chroma, Weaviate, FAISS |
| Keyword search | Elasticsearch / OpenSearch, or PostgreSQL full-text search |
| Framework | LlamaIndex or LangChain |
| Evaluation | RAGAS, DeepEval, custom expert review |

### API-based stack

| Component | Options |
|---|---|
| LLM | GPT-4.1 / GPT-4o, Claude, Gemini, or other strong model |
| Embeddings | OpenAI, Cohere, Voyage, Jina, or bge/e5 |
| Vector DB | Pinecone, Weaviate, Qdrant Cloud, Supabase Vector |
| Document processing | Unstructured, LlamaParse, GROBID (for papers) |
| Evaluation | Human expert review + automated citation checks |

---

## 6. Recommended path

### Phase 1 — Build a RAG research assistant
1. Collect papers.
2. Parse them cleanly.
3. Store chunks in a vector database.
4. Add metadata.
5. Use hybrid search.
6. Generate cited answers.

### Phase 2 — Add hypothesis generation
Prompt the model to produce: hypothesis, mechanism, evidence, contradictory evidence, experiment, controls, confidence score, citations.

### Phase 3 — Add evaluation
Have domain experts score the outputs.

### Phase 4 — Fine-tune only if needed
Fine-tune on high-quality examples of:
- question → evidence-based answer
- paper set → structured literature review
- evidence set → hypothesis + experiment proposal

### Phase 5 — Iterate
Improve retrieval, prompts, metadata, and datasets based on failures.

---

## Short answer

- Use a strong base LLM + RAG over your domain databases/papers + hybrid search + citations + expert evaluation.
- Fine-tune later only for format, style, or repeated domain tasks.
- Do **not** train from scratch unless you have huge data and compute.
- Use multiple iterations with evaluation and human feedback.
- For hypothesis generation, force the model to show evidence, contradictions, testable predictions, and proposed experiments.
- An LLM can help generate hypotheses, but the validity comes from evidence, testing, and expert review — not from the model itself.

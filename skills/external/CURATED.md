# Curated Tool Universe skills for witt-organogenesis

**Date curated:** 2026-05-07
**Sources researched:**
- https://github.com/mims-harvard/ToolUniverse (README, captured 2026-05-07)
- https://zitniklab.hms.harvard.edu/ToolUniverse/guide/skills_showcase.html (catalog, captured 2026-05-07)
- Local install of `mims-harvard/ToolUniverse` skills (108 `tooluniverse-*` skills installed via `npx skills add` on this machine, cross-referenced for description verbatim)

**Curation rule:** A skill enters this list only if it serves at least one of the project's six niches (see `PROJECT_SCOPE.md` §scope). Skills that look generally useful but do not serve a niche are excluded. Total target: 13–25 skills. This file currently holds **24 skills** (12 Emmanuel selections + 12 Claude Code additions).

**Note on count:** the handoff prose mentioned "13 selections" but the table in Section 4 contained 12 distinct entries. Emmanuel confirmed (2026-05-07) that 12 is the correct count — the prose was a counting error. This file curates against those 12.

---

## Niche legend

For brevity, each skill row tags its niche match using these codes:

| Code | Niche |
|---|---|
| **N1** | Modelado de Sistemas Biológicos (Biological Systems Modeling) |
| **N2** | Biofísica y Biomecánica de Tejidos (Tissue Biophysics & Biomechanics) |
| **N3** | Embriología, Genómica Funcional y de Célula Única (Embryology, Functional Genomics, Single-Cell) |
| **N4** | Señalización Celular (Cellular Signaling) |
| **N5** | Biología Ocular (Ocular Biology) |
| **N6** | Ingeniería de Tejidos y Medicina Regenerativa (Tissue Engineering & Regenerative Medicine) |

---

## Section A — Emmanuel's 12 initial selections

| Skill | Niches | One-line niche-fit justification |
|---|---|---|
| `tooluniverse-computational-biophysics` | **N1, N2** | Reasoning strategies and Python templates for biophysics calculations (binding equilibria, diffusion, Hardy-Weinberg, R0). Direct fit for N1 (modeling) and partial fit for N2 (general biophysics, but not tissue-mechanics-specific — see §gaps). |
| `tooluniverse-crispr-screen-analysis` | **N3** | Pooled/arrayed CRISPR screen analysis (knockout, activation, interference) with MAGeCK/BAGEL scoring. Required for niche 3 perturbation-genetics workflows in zebrafish. |
| `tooluniverse-expression-data-retrieval` | **N3** | Gene-expression and omics datasets from ArrayExpress and BioStudies. Provides input data for any developmental-trajectory analysis. |
| `tooluniverse-gene-regulatory-networks` | **N1, N3, N4** | **Note:** present in source repo `mims-harvard/ToolUniverse/skills/` but NOT distributed via `npx skills add` on this machine — invoke from source or wait for upstream distribution. Description from source SKILL.md: *"GRN inference starts with: which TF regulates which gene? Direct evidence (ChIP-seq binding) is stronger than indirect (co-expression correlation). Uses JASPAR (motifs), Enrichr (TF targets via ENCODE/ChEA/TRRUST), ENCODE (histone marks), GTEx (eQTLs), RegulomeDB, STRING/IntAct/BioGRID for protein-protein interactions among regulatory factors."* Demonstrated in this very repo's parent session against zebrafish cornea TFs. |
| `tooluniverse-functional-genomics-screens` | **N3** | DepMap, constraint scores, pathway enrichment, druggability. **Emmanuel flagged oncology bias** in this skill's catalog description; the underlying methods (essentiality scoring, pathway enrichment from screen hits) transfer to developmental biology, but the included reference datasets skew oncology. Use with awareness. |
| `tooluniverse-model-organism-genetics` | **N3** | Cross-species ortholog mapping (mouse, fly, worm, **zebrafish**, yeast, frog) with phenotypes from MGI, FlyBase, WormBase, **ZFIN**, SGD, Xenbase. **Critical for the zebrafish POC** — provides the human↔zebrafish ortholog bridge. |
| `tooluniverse-single-cell` | **N3, N4** | Production scanpy/anndata workflows: QC, normalization, PCA/UMAP, Leiden clustering, DE, trajectory inference, ligand-receptor (CellPhoneDB/CellChatDB via OmniPath). Cell-cell communication is the N4 hook. |
| `tooluniverse-spatial-transcriptomics` | **N3** | 10x Visium, MERFISH, seqFISH, Slide-seq spatial workflows. Maps gene expression to tissue architecture — directly applicable to pronephros segment-by-segment expression. |
| `tooluniverse-spatial-omics-analysis` | **N3, N4** | Spatial multi-omics integration (SVGs, domains, cell-cell interactions, druggable targets) with quantitative Spatial Omics Integration Score (0-100). Domain-level analysis useful for staged developmental tissues. |
| `tooluniverse-stem-cell-organoid` | **N3, N6** | Pluripotency markers, differentiation pathways, organoid characterization, cell-type annotation via CellxGene/HCA/CellMarker. **The closest skill in Tool Universe to N6 (tissue engineering / regenerative medicine).** |
| `tooluniverse-variant-to-mechanism` | **N1, N3, N4** | Variant → regulatory context (GWAS, eQTL, RegulomeDB, ENCODE) → target gene (GTEx, OpenTargets L2G) → pathway/disease (STRING, Reactome, GO). End-to-end mechanistic narrative for any genotype-phenotype trace. |
| `tooluniverse-data-integration-analysis` | **N1, N3** | Integrates statistical results (associations, DE) with biological knowledge (pathways, literature, drug-target databases, variant annotation). Bridges the project's statistical-analysis layer with the substrate-evidence layer. |

---

## Section B — Additional skills proposed by Claude Code

These additions were chosen to fill niches Emmanuel's initial 12 under-cover. Each has a paragraph-level justification.

### B.1 — Strengthening N1 (Biological Systems Modeling)

**`tooluniverse-systems-biology`**
*"Comprehensive systems biology and pathway analysis using multiple pathway databases (Reactome, KEGG, WikiPathways, Pathway Commons, BioModels)."*
The project's modeling layer needs first-class access to BioModels (curated mathematical models of biological systems — ODE systems, signaling cascades, metabolic networks). This skill is the canonical entry point for that. It also serves N4 directly through Reactome/KEGG signaling. Effectively **a dual-niche workhorse (N1 + N4).**

**`tooluniverse-network-pharmacology`**
*"Construct and analyze compound-target-disease networks for drug repurposing, polypharmacology discovery, and systems pharmacology. Builds multi-layer networks from ChEMBL, OpenTargets, STRING, DrugBank, Reactome, FAERS, and 60+ other ToolUniverse tools."*
The project's substrate-instrumented agents reason over multi-layer networks of perturbations and outcomes. Network pharmacology provides the canonical *technique* for that reasoning, transferable beyond drug discovery to any compound-target-process network (e.g., morphogen-receptor-cell-fate networks during organogenesis).

### B.2 — Strengthening N2 (Tissue Biophysics and Biomechanics) — see §gaps for honesty

**`tooluniverse-protein-structure-prediction`**
*"Predict and analyze protein 3D structure from amino acid sequence using ESMFold and AlphaFold."*
Biophysics calculations frequently start from a structural prior (binding-pocket geometry, conformational ensembles). ESMFold/AlphaFold give that prior on demand. **Closest available approximation for niche 2** in the absence of a dedicated tissue-mechanics skill.

**`tooluniverse-protein-structure-retrieval`**
*"Retrieves protein structure data from RCSB PDB, PDBe, and AlphaFold with protein disambiguation, quality assessment, and comprehensive structural profiles."*
Companion to the above for already-deposited structures. Useful when the protein is well-characterized and a curated PDB entry exists.

### B.3 — Strengthening N3 (Embryology, Functional Genomics, Single-Cell)

**`tooluniverse-comparative-genomics`**
*"Cross-species gene and sequence comparison, ortholog analysis, and evolutionary conservation assessment using ToolUniverse tools."*
Complements `tooluniverse-model-organism-genetics`: the latter focuses on phenotype/expression cross-species; this focuses on sequence-level conservation, useful for prioritizing zebrafish gene targets by human conservation score.

**`tooluniverse-epigenomics-chromatin`**
*"Epigenomics and chromatin accessibility research — histone modification ChIP-seq data from ENCODE, CTCF binding and chromatin architecture, eQTL analysis connecting variants to gene regulation, gene expression correlation with chromatin marks, regulatory element analysis."*
The pronephros development POC benefits from chromatin-accessibility context for stage-specific TF binding inference. Pairs with `tooluniverse-gene-regulatory-networks`.

**`tooluniverse-rnaseq-deseq2`**
*"Production-ready RNA-seq differential expression analysis using PyDESeq2."*
Bulk RNA-seq complements single-cell where larger-scale population-level effects matter (e.g., morpholino vs control bulk comparisons in zebrafish embryos at staged time points).

### B.4 — Strengthening N4 (Cellular Signaling)

**`tooluniverse-protein-interactions`**
*"Protein-protein interaction networks (STRING, BioGRID, SASBDB databases). Maps protein identifiers, retrieves interaction networks with confidence scores, performs functional enrichment analysis (GO/KEGG/Reactome)."*
Direct fit for signaling-network reasoning. Demonstrated in this repo's parent session for zebrafish corneal development (pax6b, pitx2, foxc1a, tfap2a hubs).

**`tooluniverse-regulatory-genomics`**
*"Investigate transcription factor binding, cis-regulatory elements, chromatin accessibility, and regulatory variant annotation."*
Close cousin to the GRN skill in Section A; this is the more general-purpose entry to ENCODE-style regulatory data. Useful when GRN analysis isn't the question but regulatory-element annotation is.

**`tooluniverse-pathway-disease-genetics`**
*"Connect GWAS variants to biological pathways for drug target discovery. Maps disease-associated SNPs to causal genes via eQTL colocalization (GTEx), links genes to enriched pathways (Reactome, KEGG, MetaCyc)."*
Variant-to-pathway-to-disease bridges N4 with N1.

### B.5 — Strengthening N6 (Tissue Engineering & Regenerative Medicine)

**`tooluniverse-protein-therapeutic-design`**
*"Design novel protein therapeutics (binders, enzymes, scaffolds) using AI-guided de novo design. Uses RFdiffusion for backbone generation, ProteinMPNN for sequence design, ESMFold/AlphaFold2 for validation."*
RFdiffusion / ProteinMPNN open the door to designing **engineered growth factors, modified ligands, and protein scaffolds** for regenerative-medicine applications. The relevance is long-term (Phase III), not Phase I, but the skill belongs in the curated set so it's known when needed.

### B.6 — Cross-cutting infrastructure (serve all niches)

**`tooluniverse-literature-deep-research`**
*"Comprehensive literature deep research across any academic domain using 120+ ToolUniverse tools. Conducts subject disambiguation, systematic literature search with citation network expansion, evidence grading (T1-T4), and structured theme extraction."*
**Critical for the project's substrate-validation discipline.** Every claim needs citations and evidence grading. This skill operationalizes that requirement at scale. Belongs in the curated set even though it's not niche-specific.

**`tooluniverse-data-wrangling`**
*"Universal data access reference for scientific research. Teaches how to download bulk data, parse any scientific file format (VCF, h5ad, mzML, PDB, FASTA, XPT, NIfTI, and 30+ more), paginate REST APIs, and handle authentication."*
The project will encounter heterogeneous data formats from public databases, lab partners, and computational outputs. This is the canonical reference for handling that variety.

**`tooluniverse-dataset-discovery`**
*"Find and evaluate research datasets for any scientific question. Teaches how to reason about data needs, search across public repositories, evaluate dataset fitness, and identify access requirements."*
Companion to `data-wrangling`: this is the *finding* layer, the wrangling skill is the *parsing* layer.

---

## Section C — Borderline cases (Emmanuel to decide)

**`tooluniverse-rare-disease-diagnosis` `[Borderline — N5 by general-purpose route]`**
There is no ocular-specific skill in Tool Universe, but `tooluniverse-rare-disease-diagnosis` matches symptoms to HPO terms and identifies candidate diseases from Orphanet/OMIM, which would catch ocular rare diseases (aniridia, Peters anomaly, Axenfeld-Rieger) by their symptom profiles. This is a workaround, not a dedicated solution. Keep if you want a partial N5 path; drop if you prefer to acknowledge the gap explicitly.

**`tooluniverse-binder-discovery` `[Borderline — N6 partial]`**
Small-molecule binders for protein targets are not the typical N6 toolkit (which is more about scaffolds, biomaterials, growth factors). However, certain regenerative strategies recruit small-molecule modulators of stem-cell signaling. Keep if you anticipate small-molecule recruitment in the regenerative-medicine roadmap; drop otherwise.

**`tooluniverse-clinical-trial-matching` `[Borderline — Test 5 candidate, ophthalmology partner field]`**
If Test 5's partner field becomes ophthalmology (PROJECT_SCOPE v1.2 §11 pending), this skill becomes the canonical entry to ocular clinical-trial data. If cardiology, this skill is still useful but less central. Default: include with `[Test 5 candidate]` marker.

**`tooluniverse-immunology` `[Borderline — adjacent to development]`**
Antibody-antigen, immune-protein interactions, IEDB epitope/MHC data, IMGT immunoglobulin genes. The pronephros has minimal immune crosstalk in early development, but later stages and any inflammation-aware ablation strategies would touch this domain. Marginal fit.

---

## Section D — Honest gaps in Tool Universe coverage for this project

These gaps are **not failures of curation** — Tool Universe simply does not provide skills in these areas, which is honest to acknowledge. Filling these gaps requires external tools and is **not** a target for the curated set.

### N2 — Tissue biomechanics and FEM/CFD
Tool Universe is a database-query and analysis-skill system. Tissue mechanics (continuum mechanics, finite element method, computational fluid dynamics, mechanotransduction modeling) requires dedicated solvers (FEniCS, Ansys, Abaqus, FEBio, Chaste) and morphogenesis frameworks (Morpheus, BioDynaMo, CompuCell3D). **No skill in the Tool Universe catalog wraps these.** The closest available substitute is `tooluniverse-computational-biophysics` for general biophysics calculations and `tooluniverse-protein-structure-*` for structural priors. For real biomechanics, the project will need its own tooling outside Tool Universe.

### N5 — Ocular-specific biology
There is no `tooluniverse-ophthalmology` or `tooluniverse-ocular-development` skill. The borderline workarounds in Section C (`rare-disease-diagnosis`, `clinical-trial-matching`) provide partial coverage via general-purpose disease/trial workflows. If ophthalmology becomes the Test 5 partner field, the project should track whether the MIMS Lab adds an ocular-specific skill upstream and propose one if not.

### N6 — Tissue engineering: scaffolds and biomaterials
`tooluniverse-stem-cell-organoid` is the closest fit and was Emmanuel's pick. Beyond that, Tool Universe does not currently offer skills on scaffold design, biomaterial selection, or bioreactor protocols. These remain the domain of project-specific tooling.

---

## Section E — Total count and rollup

| Section | Skills |
|---|---|
| A — Emmanuel's selections | 12 |
| B — Claude Code additions | 12 |
| C — Borderline (Emmanuel to decide) | 4 |
| **Total entries** | **28** |
| **Within handoff cap (≤25)** | A+B = 24 ✓ |

The 4 borderline entries are listed for Emmanuel's call but do not count toward the 25-skill cap.

---

## How to use this list

When invoking a skill conversationally with Claude, you do not need to load this file — Claude has the skills auto-installed via `npx skills add` and will dispatch by natural-language trigger. This file exists for:

1. **Onboarding** new collaborators: "what subset of Tool Universe is in-scope for this project?"
2. **Niche-fit auditing**: confirming a tool is being used inside an in-scope niche before relying on its output.
3. **Future curation**: when MIMS Lab adds new skills upstream, this file is the diff target.

For invoking a Tool Universe skill from inside a substrate-instrumented agent (per `skills/custom/organogenesis-agent-architect/`), populate `framework_applied` as `tooluniverse-skill: <skill-name>` per `CLAUDE.md` §6.

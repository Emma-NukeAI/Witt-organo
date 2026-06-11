"""
corpus_classifier.py — RAG corpus categorization scaffold (GWT v1.1 Cycle 4, PR-09 / ADR-0017).

NO-SPEND, stdlib + the rag_index/ structure. The operational core of the corpus-classifier role
(an extension of domain-knowledge-curator). Given a document descriptor it PROPOSES a categorization
into the 13 RAG data-niches (rag_index/niches.json) + the source database (rag_index/databases.json),
and can AUDIT an existing categorization and propose a re-categorization. It NEVER writes to
rag_index/corpus_manifest.json — it returns proposals for a HUMAN GATE (CLAUDE.md §7; the store is
read-only / human-gated mutable).

v1 is deterministic (file-extension + keyword routing). A semantic/LLM layer + embeddings are added
with the RAG backend (still OPEN, plan §A). Agents using this are NOT exempt from MCP/Tool Universe
verification + completeness checks (GWT v1.1 §3.3).

Usage:  python analysis/scripts/lib/corpus_classifier.py   # self-test on sample descriptors
"""
from pathlib import Path
import json

_RAG = Path(__file__).resolve().parents[2].parent / "rag_index"
NICHES_PATH = _RAG / "niches.json"
DB_PATH = _RAG / "databases.json"

# Keyword hints per data-niche (deterministic v1; extend as the corpus grows).
NICHE_KEYWORDS = {
    "RN1": ["transcriptom", "lineage", "scrna", "expression", "cluster", "hpf", "atlas", "stereo-seq", "stereoseq", "spatial transcriptom"],
    "RN2": ["structure", "alphafold", "pdb", "complex", "docking", "receptor", "domain"],
    "RN3": ["signaling", "pathway", "kinetic", "bngl", "bionetgen", "reaction", "cascade", "rule-based"],
    "RN4": ["metabolom", "lipidom", "mass spec", "gradient", "ph", "o2", "ion flux", "kegg"],
    "RN5": ["bioelectric", "membrane potential", "voltage", "ion channel", "vmem"],
    "RN6": ["biomechanic", "ecm", "stiffness", "afm", "collagen", "fibronectin", "scaffold", "young"],
    "RN7": ["fluid", "flow", "velocity", "shear", "cfd", "traction", "pressure"],
    "RN8": ["migration", "trajectory", "apoptosis", "tracking", "collective", "delamination"],
    "RN9": ["morpholog", "topology", "confocal", "mesh", "segmentation", "morphometr", "voxel", "spatial", "stereo-seq", "stereoseq"],
    "RN10": ["chaperone", "boundary condition", "neighbor tissue", "interaction table", "source", "target"],
    "RN11": ["literature", "claim", "citation", "review", "reference", "doi", "pmid"],
    "RN12": ["perturbation", "knockout", "ko", "intervention", "causal", "morpholino", "crispr"],
    "RN13": ["simulation", "morpheus", "model", "code", "script"],
}
DB_KEYWORDS = {
    "ZFIN": ["zfin", "marker", "mutant", "transcription factor"],
    "DanioCODE": ["daniocode", "regulatory element", "functional genome"],
    "Reactome": ["reactome", "pathway", "metabolic"],
    "GEO_NCBI": ["geo", "gse", "gsm", "ncbi", "count matrix"],
    "UCSC_Cell_Browser": ["ucsc", "cell browser", "scrna", "lineage trajector"],
    "STRING_DB": ["string", "predicted interaction"],
    "IntAct": ["intact", "physical interaction"],
    "BioGRID": ["biogrid", "genetic interaction", "double"],
    "Ensembl_DanioRerio": ["ensembl", "ensdarg", "ortholog", "promoter", "annotation"],
    "CNGB_STOmics": ["cngb", "stomics", "stereo-seq", "stereoseq", "zesta", "spatial transcriptom", "mosta"],
}


def _load():
    niches = {n["id"]: n for n in json.loads(NICHES_PATH.read_text(encoding="utf-8"))["niches"]}
    dbs = {d["id"]: d for d in json.loads(DB_PATH.read_text(encoding="utf-8"))["databases"]}
    return niches, dbs


def propose_categorization(filename, text=""):
    """Return a PROPOSAL (never a commit). Human gate required before writing to the manifest."""
    niches, dbs = _load()
    ext = Path(filename).suffix.lower()
    blob = f"{filename} {text}".lower()

    by_ext = [nid for nid, n in niches.items() if ext in n["file_types"]]
    by_kw = []
    for nid, kws in NICHE_KEYWORDS.items():
        score = sum(1 for k in kws if k in blob)
        if score:
            by_kw.append((nid, score))
    by_kw.sort(key=lambda x: -x[1])

    db_hits = [db for db, kws in DB_KEYWORDS.items() if any(k in blob for k in kws)]

    # Combine: keyword evidence ranks; extension narrows. Confidence is intentionally modest.
    ranked = []
    seen = set()
    for nid, _ in by_kw:
        ranked.append(nid); seen.add(nid)
    for nid in by_ext:
        if nid not in seen:
            ranked.append(nid); seen.add(nid)

    confidence = 0.0
    if by_kw and by_ext and by_kw[0][0] in by_ext:
        confidence = 0.8   # keyword + extension agree
    elif by_kw:
        confidence = 0.55
    elif by_ext:
        confidence = 0.4
    return {
        "proposal": True,
        "needs_human_gate": True,
        "filename": filename,
        "extension": ext,
        "data_niche_candidates": ranked[:3] or ["RN11"],
        "source_db_candidates": db_hits,
        "confidence": confidence,
        "ambiguous": len(set(ranked[:3])) > 1 and confidence < 0.8,
        "note": ("PROPOSAL ONLY — route to human gate before writing to rag_index/corpus_manifest.json. "
                 "Deterministic v1 (extension+keyword); semantic layer added with the RAG backend. "
                 "Verify entities + check completeness via MCP/ToolUniverse (GWT v1.1 §3.3)."),
    }


def audit_categorization(record):
    """Audit an existing manifest record; propose a re-categorization if evidence disagrees."""
    current = (record.get("data_niche") or [None])[0]
    fresh = propose_categorization(record.get("source_document", {}).get("filename", ""),
                                   " ".join(str(e.get("entity", "")) for e in record.get("entities_extracted", [])))
    top = fresh["data_niche_candidates"][0]
    agrees = current == top
    return {
        "current_data_niche": current,
        "proposed_data_niche": top,
        "agrees": agrees,
        "recommend_recategorization": (not agrees) and fresh["confidence"] >= 0.55,
        "evidence": fresh,
        "needs_human_gate": True,
    }


if __name__ == "__main__":
    samples = [
        ("GSE162031_raw_counts_day1.csv.gz", "scRNA-seq count matrix zebrafish pronephros cluster expression hpf"),
        ("foxc1a_alphafold.json", "AlphaFold predicted structure transcription factor docking"),
        ("bmp_nodal_ra_network.bngl", "BioNetGen rule-based signaling cascade kinetic"),
        ("wagner2018.pdf", "literature review zebrafish neural crest lineage citation"),
    ]
    for fn, txt in samples:
        p = propose_categorization(fn, txt)
        print(f"{fn:38s} -> {p['data_niche_candidates']} db={p['source_db_candidates']} conf={p['confidence']}")

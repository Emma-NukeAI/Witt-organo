#!/usr/bin/env python3
"""
LBPP — Load-Bearing Provenance Probe
Verifies javierdiegof/zebrafish identifiers against Ensembl REST + UniProt,
caching RAW responses (CLAUDE.md §6/§7.9) BEFORE any processing. Data-driven:
every identifier is read from the collaborator's own files, never from memory.

Outputs: raw caches to mcp_cache/raw_*  +  processed summary to mcp_cache/lbpp_result_<date>.json
Run:  python scripts/lbpp_verify.py
"""
import json, os, sys, urllib.request, urllib.error, time

DATE = "20260531"
COLLAB = r"c:\Users\Emmanuel\dev\zebrafish"
OURS = r"c:\Users\Emmanuel\dev\witt-organogenesis"
CACHE = os.path.join(OURS, "mcp_cache")
os.makedirs(CACHE, exist_ok=True)

def raw_path(desc, ext="json"):
    return os.path.join(CACHE, f"raw_{desc}_{DATE}.{ext}")

def post_json(url, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": "witt-lbpp/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode()

def get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                 "User-Agent": "witt-lbpp/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode()

# ---------- 1. read collaborator files (deterministic, from disk) ----------
with open(os.path.join(COLLAB, "network.tsv"), encoding="utf-8") as f:
    lines = [l.rstrip("\n").split("\t") for l in f if l.strip()]
hdr = lines[0]; rows = lines[1:]
ci = {c: i for i, c in enumerate(hdr)}

def ensp(stringid):  # "7955.ENSDARP00000004972" -> "ENSDARP00000004972"
    return stringid.split(".", 1)[1] if "." in stringid else stringid

protein_to_symbol = {}   # ENSDARP -> asserted symbol (preferredName) from network.tsv
edges = []               # (symA, symB, score)
for r in rows:
    a, b = ensp(r[ci["stringId_A"]]), ensp(r[ci["stringId_B"]])
    sa, sb = r[ci["preferredName_A"]], r[ci["preferredName_B"]]
    protein_to_symbol[a] = sa
    protein_to_symbol[b] = sb
    edges.append((sa, sb, float(r[ci["score"]])))

with open(os.path.join(COLLAB, "spatial_data.json"), encoding="utf-8") as f:
    spatial = json.load(f)

with open(os.path.join(COLLAB, "mapped_ids.tsv"), encoding="utf-8") as f:
    mlines = [l.rstrip("\n").split("\t") for l in f if l.strip()]
mhdr = {c: i for i, c in enumerate(mlines[0])}
documented = set()  # the 9 ENSDARP that have a mapped_ids row
for r in mlines[1:]:
    documented.add(ensp(r[mhdr["stringId"]]))

proteins = sorted(protein_to_symbol.keys())
print(f"[read] {len(proteins)} ENSDARP from network.tsv; {len(documented)} documented in mapped_ids.tsv; {len(spatial)} spatial genes", file=sys.stderr)

# ---------- 2. Ensembl pass 1: proteins -> species + parent transcript ----------
raw1 = post_json("https://rest.ensembl.org/lookup/id", {"ids": proteins})
open(raw_path("ensembl_lookup_proteins"), "w", encoding="utf-8").write(raw1)
p1 = json.loads(raw1)
transcripts = []
prot_info = {}
for pid in proteins:
    o = p1.get(pid)
    if o:
        prot_info[pid] = {"species": o.get("species"), "object_type": o.get("object_type"),
                          "parent_transcript": o.get("Parent")}
        if o.get("Parent"): transcripts.append(o["Parent"])
    else:
        prot_info[pid] = {"species": None, "object_type": None, "parent_transcript": None}

# ---------- 3. Ensembl pass 2: transcripts -> parent gene ----------
raw2 = post_json("https://rest.ensembl.org/lookup/id", {"ids": sorted(set(transcripts))})
open(raw_path("ensembl_lookup_transcripts"), "w", encoding="utf-8").write(raw2)
p2 = json.loads(raw2)
tx_to_gene = {t: (p2.get(t) or {}).get("Parent") for t in set(transcripts)}

# ---------- 4. Ensembl pass 3: genes -> display_name (symbol) ----------
genes = sorted({g for g in tx_to_gene.values() if g})
raw3 = post_json("https://rest.ensembl.org/lookup/id", {"ids": genes})
open(raw_path("ensembl_lookup_genes"), "w", encoding="utf-8").write(raw3)
p3 = json.loads(raw3)
gene_symbol = {g: (p3.get(g) or {}).get("display_name") for g in genes}
gene_desc = {g: (p3.get(g) or {}).get("description") for g in genes}

# ---------- 5. UniProt: verify the 9 accessions from spatial_data.json ----------
accs = sorted({v.get("accession") for v in spatial.values() if v.get("accession")})
uni_url = ("https://rest.uniprot.org/uniprotkb/accessions?accessions=" + ",".join(accs) +
           "&fields=accession,organism_name,organism_id,gene_primary,protein_name&format=json")
raw_u = get(uni_url)
open(raw_path("uniprot_accessions"), "w", encoding="utf-8").write(raw_u)
uni = json.loads(raw_u)
uni_by_acc = {}
for e in uni.get("results", []):
    acc = e.get("primaryAccession")
    org = (e.get("organism") or {})
    genes_u = e.get("genes") or []
    gname = genes_u[0].get("geneName", {}).get("value") if genes_u else None
    uni_by_acc[acc] = {"organism_id": org.get("taxonId"), "organism": org.get("scientificName"),
                       "gene_primary": gname}

# ---------- 6. build per-protein verdict ----------
results = []
for pid in proteins:
    asserted = protein_to_symbol[pid]
    info = prot_info[pid]
    tx = info["parent_transcript"]
    g = tx_to_gene.get(tx) if tx else None
    sym = gene_symbol.get(g) if g else None
    exists = info["object_type"] is not None
    is_danio = (info["species"] == "danio_rerio")
    sym_ok = (sym is not None and asserted is not None and sym.lower() == asserted.lower())
    results.append({
        "ensdarp": pid, "asserted_symbol": asserted, "documented": pid in documented,
        "exists": exists, "species": info["species"], "is_danio": is_danio,
        "resolved_ensdarg": g, "resolved_symbol": sym, "symbol_match": sym_ok,
        "description": (gene_desc.get(g) or "")[:80] if g else None,
    })

# ---------- 7. anchor cross-check against OUR verified map ----------
with open(os.path.join(OURS, "analysis", "outputs", "ensembl_symbol_map.json"), encoding="utf-8") as f:
    ourmap = json.load(f)
anchors = []
for r in results:
    sym = r["asserted_symbol"]
    if sym in ourmap and ourmap[sym]:
        anchors.append({"symbol": sym, "ensdarp": r["ensdarp"],
                        "our_ensdarg": ourmap[sym], "their_resolved_ensdarg": r["resolved_ensdarg"],
                        "match": ourmap[sym] == r["resolved_ensdarg"]})

# ---------- 8. UniProt verdict ----------
uni_results = []
for sym, v in spatial.items():
    acc = v.get("accession")
    u = uni_by_acc.get(acc, {})
    uni_results.append({"symbol": sym, "accession": acc,
        "exists": acc in uni_by_acc, "organism_id": u.get("organism_id"),
        "is_danio": u.get("organism_id") == 7955,
        "uniprot_gene": u.get("gene_primary"),
        "gene_match": (u.get("gene_primary") or "").lower() == sym.lower()})

# ---------- 9. faithful nb03 threshold recompute ----------
keywords_kidney = ["tubule","epitheli","duct","nephron","pronephr","kidney","renal","urogenital","glomerul","podocyte"]
def kidney_score(gene):
    if gene in spatial:
        info = spatial[gene]
        txt = " ".join(t["term"].lower() for t in info.get("go_bp", []))
        txt += " " + info.get("tissueSpecificity", "").lower()
        return sum(1 for kw in keywords_kidney if kw in txt) / len(keywords_kidney)
    return 0.125
all_genes = {e[0] for e in edges} | {e[1] for e in edges}
scores = {g: kidney_score(g) for g in all_genes}
def filt(T):
    kept = [e for e in edges if scores[e[0]] >= T and scores[e[1]] >= T]
    nodes = {e[0] for e in kept} | {e[1] for e in kept}
    return {"threshold": T, "edges_kept": len(kept), "nodes": len(nodes),
            "pruned": len(edges) - len(kept)}
collapse = [filt(T) for T in (0.10, 0.12, 0.125, 0.13)]
real9_scores = {g: round(scores[g], 3) for g in sorted(spatial.keys())}

# ---------- 10. aggregate verdict ----------
n = len(results)
doc = [r for r in results if r["documented"]]
fil = [r for r in results if not r["documented"]]
summary = {
    "date": DATE,
    "total_proteins": n,
    "documented_count": len(doc),
    "filler_count": len(fil),
    "documented_all_pass": all(r["exists"] and r["is_danio"] and r["symbol_match"] for r in doc),
    "documented_pass_n": sum(1 for r in doc if r["exists"] and r["is_danio"] and r["symbol_match"]),
    "filler_pass_n": sum(1 for r in fil if r["exists"] and r["is_danio"] and r["symbol_match"]),
    "all_resolve_danio": all(r["is_danio"] for r in results),
    "all_symbol_match": all(r["symbol_match"] for r in results),
    "symbol_mismatches": [{"ensdarp": r["ensdarp"], "asserted": r["asserted_symbol"], "resolved": r["resolved_symbol"]}
                          for r in results if not r["symbol_match"]],
    "anchor_checks": anchors,
    "anchor_all_match": all(a["match"] for a in anchors) if anchors else None,
    "uniprot_results": uni_results,
    "uniprot_all_danio": all(u["is_danio"] for u in uni_results),
    "uniprot_all_gene_match": all(u["gene_match"] for u in uni_results),
    "real9_kidney_scores": real9_scores,
    "threshold_collapse": collapse,
    "per_protein": results,
}
out = os.path.join(CACHE, f"lbpp_result_{DATE}.json")
json.dump(summary, open(out, "w", encoding="utf-8"), indent=2)
print(json.dumps({k: summary[k] for k in
    ["total_proteins","documented_count","filler_count","documented_pass_n","filler_pass_n",
     "all_resolve_danio","all_symbol_match","symbol_mismatches","anchor_all_match",
     "uniprot_all_danio","uniprot_all_gene_match","real9_kidney_scores","threshold_collapse"]}, indent=2))
print(f"\n[written] {out}", file=sys.stderr)
print(f"[raw cached] {len(os.listdir(CACHE))} files in mcp_cache/", file=sys.stderr)

"""
05_sgRNA_design.py (originally 05_mafba_sgRNA_design.py — refactored gene-agnostic)
Pre-resolve item 1: diseñar sgRNAs candidatos contra cualquier gen zebrafish.

Pipeline:
  1. Pull gene info via Ensembl REST (resolve symbol → Ensembl ID si necesario).
  2. Pull CDS sequence for canonical transcript.
  3. Identify NGG PAM sites in early CDS (exon 1 + exon 2).
  4. Score candidate sgRNAs by:
     - GC content (target 40-60%)
     - Distance from start codon (prefer early in CDS)
     - No polyT (4+ T's = pol III terminator, kills sgRNA expression)
     - Self-complementarity heuristic
  5. Output ranked list of candidates for wet-lab validation.

Uso:
  python 05_sgRNA_design.py --gene mafba
  python 05_sgRNA_design.py --gene hoxb8a
  python 05_sgRNA_design.py --gene-id ENSDARG00000017121

Note: this is computational pre-screening. Final sgRNA selection should use
production CRISPRdesign tools (CRISPRscan, CHOPCHOP, CRISPOR) which have
trained off-target databases.
"""

from pathlib import Path
import argparse
import json
import sys
import urllib.request
import urllib.error
import re

# Defaults preserved for backward compat: mafba
DEFAULT_GENE = "mafba"
DEFAULT_ENS_ID = "ENSDARG00000017121"

# OUT_DIR is set in main() based on --gene
OUT_DIR = Path("analysis/outputs/mafba_design")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def log(msg):
    print(f"[sgRNA] {msg}", flush=True)

def ensembl_get(endpoint, params=None):
    """GET request to Ensembl REST."""
    url = f"https://rest.ensembl.org{endpoint}"
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())

def ensembl_get_seq(endpoint, params=None):
    """GET request returning sequence (text/plain or json)."""
    url = f"https://rest.ensembl.org{endpoint}"
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())

def gc_content(seq):
    seq_upper = seq.upper()
    gc = seq_upper.count("G") + seq_upper.count("C")
    return gc / len(seq) if len(seq) > 0 else 0

def has_polyT_terminator(seq):
    """Pol III terminator = 4+ consecutive T's. Kill sgRNA expression."""
    return "TTTT" in seq.upper()

def reverse_complement(seq):
    comp = {"A": "T", "T": "A", "G": "C", "C": "G", "N": "N"}
    return "".join(comp.get(b.upper(), "N") for b in seq[::-1])

def find_pam_sites(seq, strand="+"):
    """Find NGG PAM sites. Return list of (position, sgRNA_target_20nt, pam_3nt).
    sgRNA target is 20 nt UPSTREAM of PAM (5' of PAM)."""
    sites = []
    seq_upper = seq.upper()
    # Find NGG patterns (N is any base, but in practice we scan for GG and look at -1 position)
    for match in re.finditer(r"(?=([ACGTN]GG))", seq_upper):
        pam_start = match.start()
        if pam_start < 20:
            continue  # Need 20 nt upstream
        sgRNA_seq = seq_upper[pam_start - 20:pam_start]
        pam = seq_upper[pam_start:pam_start + 3]
        if "N" in sgRNA_seq:
            continue
        sites.append({
            "strand": strand,
            "position_in_seq": pam_start - 20,  # start of sgRNA target
            "sgRNA_20nt": sgRNA_seq,
            "PAM_NGG": pam,
            "full_target_23nt": sgRNA_seq + pam,
        })
    return sites

def score_sgRNA(sgRNA_seq):
    """Heuristic score 0-100 based on common rules."""
    score = 50  # baseline
    notes = []

    gc = gc_content(sgRNA_seq)
    # GC content rule
    if 0.40 <= gc <= 0.60:
        score += 15
        notes.append(f"GC ok ({gc:.0%})")
    elif gc < 0.30 or gc > 0.70:
        score -= 20
        notes.append(f"GC suboptimal ({gc:.0%})")

    # Pol III terminator
    if has_polyT_terminator(sgRNA_seq):
        score -= 50
        notes.append("polyT terminator (TTTT) — KILL")

    # G at position 20 (3' end of sgRNA, just before PAM) — favored
    if sgRNA_seq[-1] == "G":
        score += 5
        notes.append("G at position 20")

    # Avoid 4+ consecutive same base anywhere
    for base in "ACGT":
        if base * 4 in sgRNA_seq:
            score -= 10
            notes.append(f"homopolymer {base}4")
            break

    # Strong start (G at position 1) is preferred for U6 expression
    if sgRNA_seq[0] == "G":
        score += 5
        notes.append("G at position 1 (good for U6)")

    return score, notes

def resolve_gene_to_ens_id(gene_symbol):
    """Resolve a zebrafish gene symbol to its Ensembl ID via REST."""
    info = ensembl_get(f"/lookup/symbol/danio_rerio/{gene_symbol}")
    return info.get("id"), info.get("display_name")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--gene", default=DEFAULT_GENE, help="Gene symbol (zebrafish)")
    p.add_argument("--gene-id", default=None, help="Ensembl gene ID (overrides --gene)")
    p.add_argument("--out-subdir", default=None, help="Output subdir (default: <gene>_design)")
    args = p.parse_args()

    if args.gene_id:
        gene_id = args.gene_id
        gene_symbol = args.gene
    elif args.gene == DEFAULT_GENE:
        gene_id = DEFAULT_ENS_ID
        gene_symbol = DEFAULT_GENE
    else:
        log(f"Resolving {args.gene} to Ensembl ID...")
        gene_id, gene_symbol = resolve_gene_to_ens_id(args.gene)
        if not gene_id:
            log(f"ERROR: cannot resolve {args.gene}")
            sys.exit(1)
        log(f"  {args.gene} -> {gene_id}")

    out_subdir = args.out_subdir or f"{gene_symbol}_design"
    out_dir = Path(f"analysis/outputs/{out_subdir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    # Override module-level OUT_DIR for output
    global OUT_DIR
    OUT_DIR = out_dir

    log(f"=== sgRNA design para {gene_symbol} ({gene_id}) ===")

    # Step 1: gene info with transcripts
    log("Pulling gene structure from Ensembl...")
    gene_info = ensembl_get(f"/lookup/id/{gene_id}", {"expand": 1})
    log(f"  Symbol: {gene_info.get('display_name')}")
    log(f"  Description: {gene_info.get('description', '')[:100]}")
    log(f"  Biotype: {gene_info.get('biotype')}")
    log(f"  N transcripts: {len(gene_info.get('Transcript', []))}")

    # Step 2: pick canonical transcript
    transcripts = gene_info.get("Transcript", [])
    canonical = None
    for t in transcripts:
        if t.get("is_canonical"):
            canonical = t
            break
    if canonical is None and transcripts:
        canonical = transcripts[0]
        log(f"  No canonical flag; using first transcript")
    if canonical is None:
        log("ERROR: no transcripts found")
        sys.exit(1)
    log(f"  Canonical transcript: {canonical['id']} (biotype={canonical['biotype']})")
    log(f"  Length: {canonical.get('length')} bp; n exons: {len(canonical.get('Exon', []))}")

    # Step 3: get CDS sequence
    log("Pulling CDS sequence...")
    cds_data = ensembl_get_seq(f"/sequence/id/{canonical['id']}", {"type": "cds"})
    cds_seq = cds_data.get("seq", "")
    log(f"  CDS length: {len(cds_seq)} nt = {len(cds_seq)//3} codons")
    log(f"  CDS start: {cds_seq[:30]}...")
    log(f"  CDS end: ...{cds_seq[-30:]}")

    # Step 4: focus on first ~250 nt of CDS (early KO target)
    early_cds = cds_seq[:300]
    log(f"  Searching PAM sites in first {len(early_cds)} nt of CDS")

    # Sense strand
    sense_sites = find_pam_sites(early_cds, strand="+")
    # Antisense strand
    rc = reverse_complement(early_cds)
    antisense_sites = find_pam_sites(rc, strand="-")
    # Convert antisense positions back to original seq coordinates
    for s in antisense_sites:
        s["position_in_seq"] = len(early_cds) - s["position_in_seq"] - 23

    all_sites = sense_sites + antisense_sites
    log(f"  Found {len(sense_sites)} sense + {len(antisense_sites)} antisense = {len(all_sites)} candidate PAM sites")

    # Step 5: score each candidate
    scored = []
    for s in all_sites:
        score, notes = score_sgRNA(s["sgRNA_20nt"])
        s["score"] = score
        s["notes"] = "; ".join(notes)
        s["gc_content"] = round(gc_content(s["sgRNA_20nt"]), 3)
        scored.append(s)

    # Sort by score descending
    scored.sort(key=lambda x: -x["score"])

    log(f"\n=== TOP 10 candidate sgRNAs ===")
    for i, s in enumerate(scored[:10]):
        log(f"\n#{i+1} (score={s['score']}) [{s['strand']} strand, position {s['position_in_seq']}]")
        log(f"  sgRNA (20nt):  5'-{s['sgRNA_20nt']}-3'")
        log(f"  PAM (NGG):     {s['PAM_NGG']}")
        log(f"  Full target:   5'-{s['full_target_23nt']}-3'")
        log(f"  GC: {s['gc_content']:.0%}")
        log(f"  Notes: {s['notes']}")

    # Step 6: save outputs
    output = {
        "gene_symbol": gene_symbol,
        "ens_id": gene_id,
        "canonical_transcript": canonical["id"],
        "cds_length_nt": len(cds_seq),
        "cds_n_codons": len(cds_seq) // 3,
        "search_window_nt": len(early_cds),
        "n_sites_found": len(all_sites),
        "top10_candidates": scored[:10],
        "all_candidates": scored,
        "design_notes": [
            "These are heuristic candidates based on PAM site search + simple scoring rules.",
            "BEFORE ordering: validate with production tools (CRISPRscan, CHOPCHOP, CRISPOR).",
            "Off-target prediction NOT included here; production tools have full off-target databases.",
            "Recommend wet-lab partner: select 2-3 sgRNAs from top 10, prioritize different strands and positions for orthogonality.",
            "In vitro cleavage assay before microinjection is essential."
        ]
    }

    out_file = OUT_DIR / f"{gene_symbol}_sgRNA_candidates.json"
    out_file.write_text(json.dumps(output, indent=2))
    log(f"\nSaved {out_file}")

    # Also write a wet-lab friendly markdown summary
    md_lines = [
        f"# {gene_symbol} sgRNA candidatos — pre-screening",
        f"",
        f"**Ensembl ID:** {gene_id}",
        f"**Symbol:** {gene_info.get('display_name')}",
        f"**Canonical transcript:** {canonical['id']}",
        f"**CDS length:** {len(cds_seq)} nt ({len(cds_seq)//3} codons)",
        f"**Search window:** primeros {len(early_cds)} nt de CDS (early KO target)",
        f"",
        f"## Top 5 candidatos (ranked por heuristic score)",
        f"",
        f"| Rank | Score | Strand | Pos | sgRNA 20nt | PAM | GC% | Notes |",
        f"|------|-------|--------|-----|-----------|-----|-----|-------|",
    ]
    for i, s in enumerate(scored[:5]):
        md_lines.append(
            f"| {i+1} | {s['score']} | {s['strand']} | {s['position_in_seq']} | "
            f"`{s['sgRNA_20nt']}` | `{s['PAM_NGG']}` | {s['gc_content']:.0%} | {s['notes']} |"
        )
    md_lines.extend([
        f"",
        f"## Recomendación al wet-lab partner",
        f"",
        f"1. Select 2-3 candidatos de los top 5, prioritizing **strand diversity** (mix sense/antisense) and **position diversity** (no overlap).",
        f"2. Validate cada sgRNA candidato con production tool: ingresa la secuencia 23nt completa en CRISPRscan (https://www.crisprscan.org/), CHOPCHOP (https://chopchop.cbu.uib.no/), o CRISPOR (http://crispor.tefor.net/) — comparar scores.",
        f"3. Run in vitro cleavage assay con cada sgRNA + Cas9 + PCR amplicon de mafba antes de microinjection.",
        f"4. Order como Alt-R sgRNA from IDT (recomendado para zebrafish CRISPR-Cas9 RNP injection).",
        f"",
        f"## Caveats importantes",
        f"",
        f"- Este pre-screening NO incluye análisis de off-targets (requiere base de datos genoma-wide).",
        f"- Scoring es heurístico: GC content, polyT, position rules. No reemplaza scoring de tools production que usan CNN entrenados.",
        f"- En zebrafish, F0 crispants con 2 sgRNAs simultáneos típicamente generan deleciones grandes (entre los dos cuts), lo cual es deseable para LoF allele.",
        f"",
    ])
    md_file = OUT_DIR / f"{gene_symbol}_sgRNA_candidates.md"
    md_file.write_text("\n".join(md_lines), encoding="utf-8")
    log(f"Saved {md_file}")

    log("\n=== sgRNA design complete ===")

if __name__ == "__main__":
    sys.exit(main() or 0)

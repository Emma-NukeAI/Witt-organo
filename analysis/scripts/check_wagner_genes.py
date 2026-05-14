"""Quick inspection of Wagner gene namespace."""
import pandas as pd
import re

df = pd.read_csv(
    "analysis/data/wagner/extracted/GSM3067193_14hpf.csv.gz",
    index_col=0, compression="gzip"
)
idx = list(df.index)

print(f"Total genes: {len(idx)}")
print(f"LOC* count: {sum(1 for g in idx if g.startswith('LOC'))}")
print(f"Non-LOC genes: {sum(1 for g in idx if not g.startswith('LOC'))}")
print(f"Sample non-LOC genes (first 20): {[g for g in idx if not g.startswith('LOC')][:20]}")

markers = ['wt1a','wt1b','pax2a','pax8','hnf1ba','hnf1bb','cdh17',
           'slc4a4a','tbx2b','pou3f3a','foxc1a','gata3','podxl','nphs1','nphs2',
           'slc12a3','slc20a1a','trpm7','mafba','emx1','irx3b','sim1a','lhx1a',
           'mecom','kcnj1a.1','slc13a1','slc13a3','atp1a1a.2','atp1b1b']
print(f"\nMarkers FOUND in Wagner: {[m for m in markers if m in idx]}")
print(f"Markers MISSING in Wagner: {[m for m in markers if m not in idx]}")

# Search case-insensitive
for m in markers:
    matches = [g for g in idx if g.lower() == m.lower()]
    if matches and matches[0] != m:
        print(f"  {m} found case-different: {matches}")
    fuzzy = [g for g in idx if m.lower() in g.lower()][:5]
    if fuzzy and m not in matches:
        print(f"  {m} fuzzy: {fuzzy[:3]}")

# Show pax-prefix genes
pax_genes = sorted([g for g in idx if re.match(r"^pax\d", g.lower())])
print(f"\npax* genes: {pax_genes[:20]}")

# Show wt-prefix
wt_genes = sorted([g for g in idx if g.lower().startswith("wt")])
print(f"\nwt* genes: {wt_genes[:20]}")

# Show hnf-prefix
hnf_genes = sorted([g for g in idx if g.lower().startswith("hnf")])
print(f"\nhnf* genes: {hnf_genes[:20]}")

# Show cdh-prefix
cdh_genes = sorted([g for g in idx if g.lower().startswith("cdh")])
print(f"\ncdh* genes: {cdh_genes[:20]}")

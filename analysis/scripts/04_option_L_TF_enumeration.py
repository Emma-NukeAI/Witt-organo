"""
04_option_L_TF_enumeration.py
Opción L: enumeración data-driven de TFs cluster-specific en Schoels.

Pipeline:
  1. Cargar DE per cluster + DE per day (ENSDARG IDs).
  2. Extraer ~590 IDs únicos.
  3. Batch reverse-lookup ENS->symbol+description vía Ensembl REST POST.
  4. Filtrar a TFs por (a) keywords en description, (b) prefijos de familia TF en symbol.
  5. Para cada cluster, enumerar top TFs en DE.
  6. Identificar TFs cluster-restricted (aparecen en 1-2 clusters, no en muchos).
  7. Cross-reference con los 10 markers core validados en Wagner.
  8. Output: tabla de TFs candidatos por segmento + reporte estructurado.

Reads:  analysis/outputs/schoels_DE_per_cluster.json
        analysis/outputs/schoels_DE_per_day.json
        analysis/outputs/wagner_vs_schoels_comparison.csv
Writes: analysis/outputs/ens_to_symbol_descriptions.json
        analysis/outputs/schoels_DE_per_cluster_with_symbols.csv
        analysis/outputs/schoels_TFs_per_cluster.csv
        analysis/outputs/option_L_TF_summary.json
"""

from pathlib import Path
import json
import sys
import time
import urllib.request
import urllib.error
from collections import defaultdict, Counter

import pandas as pd

OUT_DIR = Path("analysis/outputs")
DE_CLUSTER_FILE = OUT_DIR / "schoels_DE_per_cluster.json"
DE_DAY_FILE = OUT_DIR / "schoels_DE_per_day.json"
WAGNER_COMP_FILE = OUT_DIR / "wagner_vs_schoels_comparison.csv"
ENS_DESC_CACHE = OUT_DIR / "ens_to_symbol_descriptions.json"

# Anchor clusters from Phase 2 segment annotation
SEGMENT_ANCHORS = {
    "17": "podocyte (81%)",
    "13": "distal_late (60%)",
    "7":  "proximal_tubule (52%)",
    "4":  "proximal_tubule (37%)",
    "15": "progenitors_canonical_id (27%)",
    "16": "progenitors_TF_rich (intermed_meso 28% + TF_panel 24%)",
    "6":  "podocyte_transition (23%)",
    "12": "podocyte_PT_transition",
    "1":  "intermed_meso (20%)",
}

# Heuristic TF detection: keywords in Ensembl description
TF_DESC_KEYWORDS = [
    "transcription factor", "transcriptional",
    "homeobox", "homeodomain", "homeo box",
    "zinc finger", "krueppel", "kruppel",
    "forkhead", "fork head",
    "basic helix-loop-helix", "bhlh",
    "leucine zipper",
    "nuclear receptor", "nuclear hormone receptor",
    "t-box", "tbx",
    "paired box",
    "pou domain", "pou-domain",
    "high mobility group",
    "ets ", "ets-",
    "myb",
    "smad",
    "gata-binding", "gata zinc",
    "hairy",
    "iroquois",
    "lim homeodomain",
    "snai",  # snail family
]

# Family prefixes/patterns for TF symbol-based detection
TF_SYMBOL_PATTERNS = [
    # Fox family
    r"^fox[a-z]\d?[a-z]?$",
    # Sox family
    r"^sox\d+[a-z]?$",
    # Pax family
    r"^pax\d+[a-z]?$",
    # Hox family
    r"^hox[a-d]\d+[a-z]?$",
    # Gata family
    r"^gata\d+[a-z]?$",
    # Tbx family
    r"^tbx\d+[a-z]?$",
    # Irx family
    r"^irx\d+[a-z]?$",
    # Lhx family
    r"^lhx\d+[a-z]?$",
    # Hnf family
    r"^hnf\d+[a-z]+$",
    # Klf family
    r"^klf\d+[a-z]?$",
    # Nkx family
    r"^nkx\d.\d+[a-z]?$",
    # Sall family
    r"^sall\d+[a-z]?$",
    # Six family
    r"^six\d+[a-z]?$",
    # Mecom, mef2, myb, myod, myf
    r"^mecom$", r"^mef2[a-d]$", r"^myb[a-z]?$", r"^myod\d?$", r"^myf\d$",
    # Tcf, Lef, Bcl, Etv, Eomes, Foxp, Snai
    r"^tcf\d+[a-z]?$", r"^lef\d?$", r"^etv\d+[a-z]?$",
    # Pou, dlx, emx, otx
    r"^pou\d[a-z]\d+[a-z]?$", r"^dlx\d+[a-z]?$", r"^emx\d+[a-z]?$", r"^otx\d+[a-z]?$",
    # Wt, sim, tal, neurog, atoh, mafb, foxc, foxp
    r"^wt\d+[a-z]?$", r"^sim\d+[a-z]?$", r"^tal\d$", r"^neurog\d?[a-z]?$",
    r"^atoh\d?[a-z]?$", r"^mafb[a-z]?$",
    # Tcf21, ahr, twist, gli, ascl, snail
    r"^tcf21$", r"^ahr\d?[a-z]?$", r"^twist\d?[a-z]?$", r"^gli\d?[a-z]?$",
    r"^ascl\d?[a-z]?$", r"^snai\d[a-z]?$", r"^sp\d+[a-z]?$",
]


def log(msg):
    print(f"[opt-L] {msg}", flush=True)


def collect_unique_ens():
    """Collect all unique ENSDARG IDs from DE per cluster + per day."""
    de_cluster = json.loads(DE_CLUSTER_FILE.read_text())
    de_day = json.loads(DE_DAY_FILE.read_text())
    unique_ens = set()
    for genes in de_cluster.values():
        unique_ens.update(g["ens"] for g in genes)
    for genes in de_day.values():
        unique_ens.update(g["ens"] for g in genes)
    return list(unique_ens), de_cluster, de_day


def batch_lookup_ensembl(ens_ids, batch_size=300):
    """Batch-resolve ENS IDs to {symbol, description, biotype} via Ensembl REST POST.
    Cached to ENS_DESC_CACHE."""
    if ENS_DESC_CACHE.exists():
        log(f"Using cached lookup at {ENS_DESC_CACHE}")
        cached = json.loads(ENS_DESC_CACHE.read_text())
        if all(eid in cached for eid in ens_ids):
            return cached
        # Else: do partial lookup
        missing = [e for e in ens_ids if e not in cached]
        log(f"Cache hits: {len(cached)}, missing: {len(missing)}")
        result = dict(cached)
    else:
        missing = list(ens_ids)
        result = {}
    if not missing:
        return result
    url = "https://rest.ensembl.org/lookup/id"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    for i in range(0, len(missing), batch_size):
        chunk = missing[i:i + batch_size]
        body = json.dumps({"ids": chunk}).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        log(f"POST {url} batch {i // batch_size + 1} ({len(chunk)} IDs)...")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
            for ens_id, info in data.items():
                if info is None:
                    result[ens_id] = {"symbol": None, "description": None, "biotype": None}
                else:
                    result[ens_id] = {
                        "symbol": info.get("display_name"),
                        "description": info.get("description"),
                        "biotype": info.get("biotype"),
                    }
        except urllib.error.HTTPError as e:
            log(f"  HTTPError {e.code}: {e.read().decode()[:300]}")
        except Exception as e:
            log(f"  Error: {e}")
        time.sleep(0.5)
    # Save cache
    ENS_DESC_CACHE.write_text(json.dumps(result, indent=2))
    return result


def is_tf(symbol, description):
    """Heuristic: is this gene a TF?"""
    import re
    # Check description keywords
    if description:
        desc_lower = description.lower()
        for kw in TF_DESC_KEYWORDS:
            if kw in desc_lower:
                return True, f"desc:{kw}"
    # Check symbol patterns
    if symbol:
        sym_lower = symbol.lower()
        for pattern in TF_SYMBOL_PATTERNS:
            if re.match(pattern, sym_lower):
                return True, f"family:{pattern}"
    return False, None


def main():
    log("=== Opción L — TF enumeration data-driven ===")

    # 1. Collect unique ENS IDs
    unique_ens, de_cluster, de_day = collect_unique_ens()
    log(f"Unique ENS IDs across all DE: {len(unique_ens)}")
    log(f"Clusters: {len(de_cluster)}, days: {len(de_day)}")

    # 2. Batch reverse-lookup
    ens_info = batch_lookup_ensembl(unique_ens)
    n_resolved = sum(1 for v in ens_info.values() if v.get("symbol"))
    log(f"Resolved {n_resolved}/{len(unique_ens)} ENS IDs to symbols")

    # 3. Build augmented DE table per cluster with symbols + TF flag
    rows = []
    for cluster, genes in de_cluster.items():
        for rank, g in enumerate(genes, 1):
            info = ens_info.get(g["ens"], {})
            symbol = info.get("symbol")
            description = info.get("description")
            tf_flag, tf_reason = is_tf(symbol, description)
            rows.append({
                "cluster": cluster,
                "rank": rank,
                "ens": g["ens"],
                "symbol": symbol,
                "description": (description or "")[:120],
                "is_tf": tf_flag,
                "tf_reason": tf_reason or "",
                "score": g["score"],
                "padj": g["padj"],
                "anchor_label": SEGMENT_ANCHORS.get(cluster, ""),
            })
    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / "schoels_DE_per_cluster_with_symbols.csv", index=False)
    log(f"Wrote {OUT_DIR / 'schoels_DE_per_cluster_with_symbols.csv'} ({len(df)} rows)")

    # 4. TFs per cluster: extract only TF rows
    tf_df = df[df["is_tf"]].copy()
    tf_df.to_csv(OUT_DIR / "schoels_TFs_per_cluster.csv", index=False)
    log(f"\n=== TF candidates per anchor cluster ===")
    for cluster, anchor in SEGMENT_ANCHORS.items():
        sub = tf_df[tf_df["cluster"] == cluster].sort_values("rank")
        if len(sub) > 0:
            log(f"\nCluster {cluster} [{anchor}] — top {min(8, len(sub))} TFs:")
            for _, row in sub.head(8).iterrows():
                log(f"  rank {row['rank']:>2}  {row['symbol']:<14}  score={row['score']:.2f}  "
                    f"({row['tf_reason'][:30]})  {row['description'][:60]}")
        else:
            log(f"\nCluster {cluster} [{anchor}] — no TFs in top 30 DE")

    # 5. Identify cluster-restricted TFs (appear in <=2 anchor clusters)
    log("\n=== Cluster-restricted TFs (appear in <=2 clusters' top-30 DE) ===")
    tf_cluster_counts = tf_df.groupby("symbol")["cluster"].agg(lambda x: list(x.unique())).reset_index()
    tf_cluster_counts["n_clusters"] = tf_cluster_counts["cluster"].apply(len)
    restricted = tf_cluster_counts[tf_cluster_counts["n_clusters"] <= 2].sort_values("n_clusters")
    log(f"Found {len(restricted)} TFs in <=2 clusters")
    for _, row in restricted.head(30).iterrows():
        clusters = row["cluster"]
        anchor_str = ", ".join(f"C{c}({SEGMENT_ANCHORS.get(c, c)[:20]})" for c in clusters)
        log(f"  {row['symbol']:<14}  in: {anchor_str}")
    restricted.to_csv(OUT_DIR / "schoels_TFs_cluster_restricted.csv", index=False)

    # 6. Cross-reference with Wagner-validated markers
    if WAGNER_COMP_FILE.exists():
        wagner_df = pd.read_csv(WAGNER_COMP_FILE)
        wagner_validated = set(wagner_df[wagner_df["wagner_in_dataset"]]["marker"])
        log(f"\n=== Cross-reference: Wagner-validated TF markers ({len(wagner_validated)} total) ===")
        # Find TFs in our DE that are also Wagner-validated
        tf_wagner = tf_df[tf_df["symbol"].isin(wagner_validated)]
        tf_wagner_unique = tf_wagner.drop_duplicates("symbol")
        log(f"TFs in Schoels DE AND Wagner-validated: {len(tf_wagner_unique)}")
        for _, row in tf_wagner_unique.iterrows():
            log(f"  {row['symbol']:<14}  cluster {row['cluster']:>2}  rank {row['rank']:>2}")

    # 7. Summary
    summary = {
        "phase": "Option L",
        "total_unique_ens_in_de": len(unique_ens),
        "resolved_to_symbols": n_resolved,
        "total_de_genes": len(df),
        "total_tfs_flagged": int(df["is_tf"].sum()),
        "tfs_per_anchor_cluster": {
            c: int((tf_df["cluster"] == c).sum())
            for c in SEGMENT_ANCHORS
        },
        "cluster_restricted_tfs_count": int(len(restricted)),
        "wagner_validated_tfs_count": int(len(tf_wagner_unique)) if WAGNER_COMP_FILE.exists() else None,
    }
    with open(OUT_DIR / "option_L_TF_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    log(f"\nSummary:\n{json.dumps(summary, indent=2)}")
    log("=== Opción L complete ===")


if __name__ == "__main__":
    sys.exit(main() or 0)

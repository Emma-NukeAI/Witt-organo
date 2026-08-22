"""smoke_zfin_sweep.py — gate determinista del barrido de curación (ADR-0068).

Cubre: ledger tri-estado por unidad (success | no-match | error — 'no hay' jamás se ve igual que
'falló'), crudo cacheado ANTES de procesar (§7.9), señal pronephr derivada localmente y declarada,
muestra de validación F4 reproducible (seed), estructura de la propuesta en cuarentena con su
procedencia y su nota de gate humano, símbolos JAMÁS inventados (fuera del store = salida con
error), y CERO mutación del store.

100% offline: query_zfin stubbeado — cero red. Corre: python rag_index/curation/smoke_zfin_sweep.py
"""
import csv
import hashlib
import json
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / ".tooluniverse" / "tools"))

import zfin_zebrafish  # noqa: E402
import zfin_sweep  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


STORE_SHA_ANTES = hashlib.sha256(zfin_sweep.STORE.read_bytes()).hexdigest()

RESPUESTAS = {
    "pax2a": {"status": "success", "data": {
        "symbol": "pax2a", "zfin_curie": "ZFIN:ZDB-GENE-990415-8", "taxon": "NCBITaxon:7955",
        "n_phenotypes_total": 40, "n_matched": 2, "anatomy_filter": None,
        "phenotypes": [
            {"statement": "pronephric duct absent, abnormal", "references": ["PMID:9490019"]},
            {"statement": "optic stalk increased amount, abnormal", "references": ["PMID:9053325"]},
        ]}},
    "wt1a": {"status": "error", "error": "no ZFIN zebrafish gene resolved for symbol 'wt1a'"},
    "cdh17": {"status": "error", "error": "URLError: <urlopen error timed out>"},
}


def _stub(symbol, anatomy=None, limit=50):
    return json.loads(json.dumps(RESPUESTAS[symbol]))


zfin_zebrafish.query_zfin = _stub

TMP = Path(tempfile.mkdtemp(prefix="smoke_zfin_sweep_"))

# ---- 1. main end-to-end con stub (subset del store real; pax2a/wt1a/cdh17 SÍ están en el store) ------
sys.argv = ["zfin_sweep.py", "--symbols", "pax2a,wt1a,cdh17", "--sample", "1",
            "--sleep", "0", "--out-dir", str(TMP / "out")]
zfin_sweep.main()
ds = json.loads((TMP / "out" / "dataset.json").read_text(encoding="utf-8"))

check("propuesta en cuarentena: header con procedencia (tool, fuente, store_version) + nota de gate",
      ds["tool"].startswith(".tooluniverse/tools/zfin_zebrafish")
      and "Alliance" in ds["source"] and ds["symbols_from"]["store_version"]
      and "gate humano" in ds["quarantine_note"])
check("ledger tri-estado: success + no-match + error — 'no hay' JAMÁS igual que 'falló'",
      ds["counts"]["status_tally"] == {"success": 1, "no-match": 1, "error": 1})
por_sym = {r["symbol"]: r for r in ds["records"]}
check("no-match viene del prefijo del tool; error de red queda como error",
      por_sym["wt1a"]["status"] == "no-match" and por_sym["cdh17"]["status"] == "error")
check("fuente por campo: curie + PMIDs por statement + retrieved_at + raw_ref (doctrina VB)",
      por_sym["pax2a"]["zfin_curie"] == "ZFIN:ZDB-GENE-990415-8"
      and por_sym["pax2a"]["statements"][0]["pmids"] == ["PMID:9490019"]
      and por_sym["pax2a"]["retrieved_at"] and por_sym["pax2a"]["raw_ref"] == "raw/pax2a.json")
check("señal pronephr DERIVADA localmente y declarada (1 de 2 statements)",
      por_sym["pax2a"]["n_pronephros_matched"] == 1
      and por_sym["pax2a"]["n_statements_kept"] == 2)
check("crudo cacheado por gen ANTES de procesar (§7.9) — también para no-match y error",
      all((TMP / "out" / "raw" / f"{s}.json").exists() for s in ("pax2a", "wt1a", "cdh17")))

# ---- 2. muestra de validación F4 ----------------------------------------------------------------------
with (TMP / "out" / "validation_sample.csv").open(encoding="utf-8-sig") as fh:
    filas = list(csv.DictReader(fh))
check("muestra F4: n=min(sample, pool)=1, con URL de ZFIN y columnas de concordancia vacías",
      len(filas) == 1 and filas[0]["zfin_url"].startswith("https://zfin.org/ZDB-GENE")
      and filas[0]["concordante_con_zfin_web(SI/NO/NO-ENCONTRADO)"] == "")
check("protocolo F4 presente: measured jamás validated + taxonomía de desacuerdos",
      "measured" in (TMP / "out" / "validation_README.md").read_text(encoding="utf-8")
      and "ambigüedad intrínseca" in (TMP / "out" / "validation_README.md").read_text(encoding="utf-8"))

# reproducibilidad del muestreo: mismo seed -> misma muestra
n1, _ = zfin_sweep.build_validation_sample(ds["records"], 1, 42, TMP / "s1.csv", TMP / "r1.md")
n2, _ = zfin_sweep.build_validation_sample(ds["records"], 1, 42, TMP / "s2.csv", TMP / "r2.md")
check("la muestra es REPRODUCIBLE (mismo seed, misma fila)",
      n1 == n2 == 1
      and (TMP / "s1.csv").read_text(encoding="utf-8-sig")
      == (TMP / "s2.csv").read_text(encoding="utf-8-sig"))

# ---- 3. los símbolos JAMÁS se inventan ----------------------------------------------------------------
sys.argv = ["zfin_sweep.py", "--symbols", "genX_inventado", "--out-dir", str(TMP / "out2")]
try:
    zfin_sweep.main()
    salio = False
except SystemExit as e:
    salio = "no se inventan" in str(e.code)
check("símbolo fuera del store -> salida con error explícito (jamás se inventa)", salio)

# ---- 4. CERO mutación ----------------------------------------------------------------------------------
check("el store verificado NO cambió (sha256 idéntico — el sweep es read-only sobre la verdad)",
      hashlib.sha256(zfin_sweep.STORE.read_bytes()).hexdigest() == STORE_SHA_ANTES)
check("todo lo escrito vive en el out-dir de cuarentena (dataset + raw + muestra + protocolo)",
      {p.name for p in (TMP / "out").iterdir()}
      == {"dataset.json", "raw", "validation_sample.csv", "validation_README.md"})

npass = sum(CHECKS)
print("\n== %d/%d PASS ==" % (npass, len(CHECKS)))
sys.exit(0 if npass == len(CHECKS) else 1)

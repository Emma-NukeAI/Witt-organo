"""
zfin_sweep.py — barrido de curación Método 1 estilo map-reduce (ADR-0068, adopción VB #3+#4).

El patrón del paper Virtual Biotech (37,075 agentes, un agente por unidad de trabajo, schema
validado, fuente por campo, auditoría por muestreo humano) aplicado a NUESTRA deuda de corpus —
con dos diferencias deliberadas:

  1. **Determinista, sin LLM.** La constitución manda: lo repetible va a un ejecutable. ZFIN ya
     entrega statements ESTRUCTURADOS (símbolo → curie → fenotipos con PMIDs vía Alliance API);
     no hay juicio que delegar a un modelo. El mapa es HTTP puro; el reduce es este script.
     (La etapa que SÍ necesitará agentes-lectores — extracción de penetrancia desde papers EPMC —
     es un barrido futuro sobre esta misma plantilla.)
  2. **El gate humano de ingesta queda INTACTO** (hard rule §7 / ADR-0022 — VB no lo necesita
     porque no muta nada; nosotros sí). Este script produce una PROPUESTA EN CUARENTENA:
     jamás toca la DATA INAMOVIBLE, el manifest, Neo4j ni el store.

Doctrina VB conservada:
  - una unidad de trabajo = un gen del store verificado (los símbolos JAMÁS se inventan:
    vienen de verified_identifiers.json, el source-of-truth human-gated);
  - ledger por unidad con estado EXPLÍCITO (success | no-match | error) — "busqué y no hay"
    nunca se ve igual que "la búsqueda falló";
  - fuente por campo (curie, URL del API, PMIDs por statement, retrieved_at);
  - crudo cacheado ANTES de procesar (§7.9): raw/<símbolo>.json por gen;
  - validación de instrumento por MUESTREO (F4): --sample N produce el CSV de concordancia
    que un humano llena contra la web de ZFIN; el resultado se reporta como "measured",
    jamás "validated" (ADR-0005).

Salida (gitignored — es cuarentena, no verdad):
  rag_index/curation/quarantine/zfin_sweep_<ts>/
    dataset.json              la propuesta completa (header con procedencia + records por gen)
    raw/<símbolo>.json        la respuesta cruda del tool por gen (§7.9)
    validation_sample.csv     la muestra para concordancia humana (F4)
    validation_README.md      el protocolo de llenado

Uso (cualquier venv con stdlib; cero spend de modelo, ~2 HTTP GET por gen):
  python rag_index/curation/zfin_sweep.py                       # los 113 símbolos del store
  python rag_index/curation/zfin_sweep.py --symbols pax2a,wt1a  # subconjunto
  python rag_index/curation/zfin_sweep.py --sample 25 --sleep 0.35
"""
import argparse
import csv
import datetime
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".tooluniverse" / "tools"))

STORE = ROOT / "analysis" / "outputs" / "verified_identifiers.json"
QUARANTINE = Path(__file__).resolve().parent / "quarantine"

NO_MATCH_PREFIX = "no ZFIN zebrafish gene resolved"


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def load_store_symbols():
    """Los símbolos del source-of-truth (read-only). El sweep NUNCA inventa un símbolo."""
    store = json.loads(STORE.read_text(encoding="utf-8"))
    recs = store["records"]
    syms = []
    for r in recs:
        if r.get("symbol"):
            syms.append({"symbol": r["symbol"], "ensdarg": r.get("ensdarg"),
                         "store_provenance": r.get("provenance")})
    return store.get("store_version"), syms


def sweep_one(query_fn, unit, limit, raw_dir):
    """UNA unidad de trabajo (doctrina VB: contexto completo para un solo gen). El crudo se cachea
    ANTES de procesar (§7.9); el estado del ledger es explícito y tri-estado."""
    sym = unit["symbol"]
    resp = query_fn(sym, None, limit)
    (raw_dir / f"{sym}.json").write_text(json.dumps(resp, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    rec = {"symbol": sym, "ensdarg": unit.get("ensdarg"), "retrieved_at": _now_iso(),
           "source": "Alliance of Genome Resources API (ZFIN provider)",
           "raw_ref": f"raw/{sym}.json"}
    if resp.get("status") == "success":
        d = resp["data"]
        stmts = d.get("phenotypes", [])
        rec.update(status="success", zfin_curie=d.get("zfin_curie"),
                   n_phenotypes_total=d.get("n_phenotypes_total"),
                   n_statements_kept=len(stmts),
                   # señal derivada LOCALMENTE (substring), declarada como derivación:
                   n_pronephros_matched=sum(1 for p in stmts
                                            if "pronephr" in p["statement"].lower()),
                   statements=[{"statement": p["statement"], "pmids": p["references"]}
                               for p in stmts])
    elif str(resp.get("error", "")).startswith(NO_MATCH_PREFIX):
        rec.update(status="no-match", error=resp.get("error"))
    else:
        rec.update(status="error", error=resp.get("error"))
    return rec


def build_validation_sample(records, n, seed, out_csv, readme):
    """F4 (validación de instrumento, patrón VB): muestra aleatoria REPRODUCIBLE (seed declarado)
    de statements para concordancia humana contra la web de ZFIN. El resultado será 'measured',
    jamás 'validated' (ADR-0005)."""
    pool = []
    for r in records:
        if r["status"] != "success":
            continue
        for s in r["statements"]:
            pool.append({"symbol": r["symbol"], "zfin_curie": r["zfin_curie"],
                         "statement": s["statement"], "pmids": ";".join(s["pmids"]),
                         "zfin_url": f"https://zfin.org/{r['zfin_curie'].split(':', 1)[-1]}"})
    rng = random.Random(seed)
    sample = rng.sample(pool, min(n, len(pool)))
    with out_csv.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["symbol", "zfin_curie", "zfin_url", "statement",
                                           "pmids", "concordante_con_zfin_web(SI/NO/NO-ENCONTRADO)",
                                           "nota_del_revisor"])
        w.writeheader()
        for row in sample:
            w.writerow({**row, "concordante_con_zfin_web(SI/NO/NO-ENCONTRADO)": "",
                        "nota_del_revisor": ""})
    readme.write_text(
        "# Protocolo de validación de instrumento (F4, ADR-0068 — patrón Virtual Biotech)\n\n"
        f"Muestra aleatoria reproducible (seed={seed}) de {len(sample)} statements de "
        f"{len(pool)} recolectados.\n\n"
        "1. Abre el `zfin_url` de la fila (la página del gen en ZFIN) y localiza el fenotipo.\n"
        "2. Marca `SI` si el statement coincide con lo publicado en ZFIN; `NO` si difiere; "
        "`NO-ENCONTRADO` si no aparece.\n"
        "3. Anota en `nota_del_revisor` la clase del desacuerdo (ambigüedad intrínseca vs error "
        "del instrumento — la taxonomía del paper VB).\n\n"
        "La concordancia resultante se REPORTA como *measured* con su n; jamás como *validated* "
        "(ADR-0005/0037). Un desacuerdo sistemático detiene la propuesta ANTES del gate humano.\n",
        encoding="utf-8")
    return len(sample), len(pool)


def main():
    ap = argparse.ArgumentParser(description="Barrido ZFIN de curación (cuarentena, ADR-0068)")
    ap.add_argument("--symbols", default=None,
                    help="lista separada por comas (default: TODOS los símbolos del store)")
    ap.add_argument("--limit", type=int, default=50, help="máx statements por gen")
    ap.add_argument("--sample", type=int, default=20, help="tamaño de la muestra de validación F4")
    ap.add_argument("--seed", type=int, default=20260822, help="seed de la muestra (reproducible)")
    ap.add_argument("--sleep", type=float, default=0.35, help="pausa entre genes (cortesía API)")
    ap.add_argument("--out-dir", default=None, help="override del dir de salida (tests)")
    args = ap.parse_args()

    from zfin_zebrafish import query_zfin   # Layer-0, stdlib-puro (ADR-0027/0059)

    store_version, units = load_store_symbols()
    if args.symbols:
        wanted = {s.strip() for s in args.symbols.split(",") if s.strip()}
        units = [u for u in units if u["symbol"] in wanted]
        missing = wanted - {u["symbol"] for u in units}
        if missing:
            sys.exit(f"[sweep] símbolos FUERA del store (no se inventan): {sorted(missing)}")

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir) if args.out_dir else QUARANTINE / f"zfin_sweep_{ts}"
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    records, t0 = [], time.time()
    for i, unit in enumerate(units):
        rec = sweep_one(query_zfin, unit, args.limit, raw_dir)
        records.append(rec)
        print(f"[{i + 1}/{len(units)}] {rec['symbol']}: {rec['status']}"
              + (f" ({rec['n_statements_kept']} stmts, {rec['n_pronephros_matched']} pronephr)"
                 if rec["status"] == "success" else ""))
        if args.sleep and i + 1 < len(units):
            time.sleep(args.sleep)

    tally = {}
    for r in records:
        tally[r["status"]] = tally.get(r["status"], 0) + 1
    n_stmts = sum(r.get("n_statements_kept", 0) for r in records)

    n_sample, n_pool = build_validation_sample(
        records, args.sample, args.seed,
        out_dir / "validation_sample.csv", out_dir / "validation_README.md")

    dataset = {
        "sweep_id": f"zfin_sweep_{ts}",
        "generated_at": _now_iso(),
        "generator": "rag_index/curation/zfin_sweep.py (ADR-0068)",
        "tool": ".tooluniverse/tools/zfin_zebrafish.query_zfin (Layer-0, ADR-0027/0059)",
        "source": "Alliance of Genome Resources API (ZFIN provider), taxon NCBITaxon:7955",
        "symbols_from": {"file": "analysis/outputs/verified_identifiers.json",
                         "store_version": store_version,
                         "note": "los símbolos vienen del source-of-truth; JAMÁS se inventan"},
        "params": {"limit": args.limit, "sample": args.sample, "seed": args.seed},
        "counts": {"n_symbols": len(units), "status_tally": tally,
                   "n_statements_total": n_stmts,
                   "n_pronephros_matched_total": sum(r.get("n_pronephros_matched", 0)
                                                     for r in records),
                   "validation_sample": {"n": n_sample, "pool": n_pool}},
        "duration_s": round(time.time() - t0, 1),
        "quarantine_note": ("PROPUESTA EN CUARENTENA — esto NO es la DATA INAMOVIBLE. Toda "
                            "ingesta pasa por el gate humano (§7/ADR-0022): revisar la muestra de "
                            "validación, decidir alcance, y proponer vía add_dataset/approve. "
                            "Este script no muta store, manifest ni Neo4j."),
        "records": records,
    }
    (out_dir / "dataset.json").write_text(json.dumps(dataset, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    print(f"\n== {len(units)} genes · {tally} · {n_stmts} statements "
          f"({dataset['counts']['n_pronephros_matched_total']} pronephr) · "
          f"muestra F4 {n_sample}/{n_pool} ==")
    print(f"cuarentena -> {out_dir}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()

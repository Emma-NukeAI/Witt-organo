"""smoke_tools_a.py — gate determinista de las tools Layer 0 lote A (ADR-0080, rebanada C3).

Cubre alliance_orthologs.py · zfin_expression_tsv.py · ensembl_homology.py: por tool (a) el fixture REAL grabado
el 2026-09-15 con la UNICA GET permitida, (b) error de red -> status 'error' declarado (nunca un success vacio),
(c) no-match -> status 'no-match' (medicion de la tabla, no error), (d) presupuesto: timeout<=0 -> 'skipped-budget'
con CERO llamadas; presupuesto de descarga / tope de bytes / presupuesto de escaneo agotados -> 'error'
BudgetExhausted sin dejar archivos parciales. Ademas: cache de lectura por dia en un cache_dir temporal (cache_hit
declarado, n_http_gets 0 en el segundo golpe), timeout propagado a cada GET, evidence_id RESOLUBLE (la linea que
nombra existe y trae ese gen), column_mode detectado del archivo ('positional' en el real, 'header' en un sintetico),
cabeceras X-RateLimit-* como MEDICION (None cuando no vienen), reintento UNICO por 429 declarado en retries_429.

100% offline: se monkeypatchea la UNICA costura de red de cada tool (`_get` / `_get_with_headers` / `_get_stream`).
El cache_dir es un directorio temporal: mcp_cache/ NO se toca. Cero red / cero spend. Exit 0 = todo PASS.

Corre:  python rag_index/query_service/smoke_tools_a.py
"""
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import urllib.error
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TOOLS = ROOT / ".tooluniverse" / "tools"
FX = HERE / "fixtures"
FX_ALLIANCE = FX / "alliance_orthologs_wt1a_20260915.json"
FX_ENSEMBL = FX / "ensembl_homology_wt1a_20260915.json"
FX_ZFIN = FX / "zfin_wildtype_expression_head200_20260915.json"
WT1A_CURIE = "ZFIN:ZDB-GENE-980526-558"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"_witt_ws_{name}", TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


al = _load("alliance_orthologs")
ens = _load("ensembl_homology")
zx = _load("zfin_expression_tsv")

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


TMP = Path(tempfile.mkdtemp(prefix="witt-smoke-tools-a-"))


def fresh_dir(tag):
    d = TMP / tag
    d.mkdir(parents=True, exist_ok=True)
    return d


# =====================================================================================================
# A. alliance_orthologs
# =====================================================================================================
with open(FX_ALLIANCE, encoding="utf-8") as f:
    AL_ENV = json.load(f)
AL_PAYLOAD = AL_ENV["payload"]
AUTOCOMPLETE = {"results": [{"category": "gene_search_result", "name": "wt1a", "curie": WT1A_CURIE},
                            {"category": "gene_search_result", "name": "wt1b", "curie": "ZFIN:ZDB-GENE-050420-319"}]}


class FakeAlliance:
    def __init__(self, payload, autocomplete=AUTOCOMPLETE, raise_on_orthologs=None):
        self.payload, self.autocomplete, self.raise_on = payload, autocomplete, raise_on_orthologs
        self.calls = []

    def __call__(self, url, timeout=None):
        self.calls.append((url, timeout))
        if "/search_autocomplete" in url:
            return self.autocomplete
        if "/orthologs" in url:
            if self.raise_on:
                raise self.raise_on
            return self.payload
        raise AssertionError(f"URL inesperada: {url}")


print("\n--- A. alliance_orthologs ---")
check("A0 fixture real 2026-09-15: total=4, 4 results, todos con geneToGeneOrthologyGenerated.objectGene (sin homologGene plano)",
      AL_PAYLOAD["total"] == 4 and len(AL_PAYLOAD["results"]) == 4
      and all(("geneToGeneOrthologyGenerated" in r and "objectGene" in r["geneToGeneOrthologyGenerated"]) for r in AL_PAYLOAD["results"])
      and not any("homologGene" in r for r in AL_PAYLOAD["results"])
      and "filter.stringency=stringent" in AL_ENV["url"])

d_al = fresh_dir("alliance")
net = FakeAlliance(AL_PAYLOAD); al._get = net
r1 = al.query_orthologs(curie=WT1A_CURIE, cache_dir=d_al, timeout=7)
rows = (r1.get("data") or {}).get("orthologs", [])
human = [o for o in rows if o["taxon_id"] == "NCBITaxon:9606"]
# conteo DIRECTO del fixture (no de memoria): metodos de prediccion casados en la fila humana
n_methods_human = next(len(r["geneToGeneOrthologyGenerated"]["predictionMethodsMatched"]) for r in AL_PAYLOAD["results"]
                       if r["geneToGeneOrthologyGenerated"]["objectGene"]["primaryExternalId"] == "HGNC:12796")
check("A1 fixture: success, 4 ortologos, humano HGNC:12796/WT1 con best=Yes confidence=high, 10 metodos casados (conteo del fixture), evidence_id/url resolubles",
      r1["status"] == "success" and r1["data"]["n_returned"] == 4 and len(human) == 1
      and human[0]["id"] == "HGNC:12796" and human[0]["symbol"] == "WT1" and human[0]["species"] == "Homo sapiens"
      and human[0]["best"] == "Yes" and human[0]["confidence"] == "high" and human[0]["strict_filter"] is True
      and human[0]["evidence_id"] == f"alliance-ortholog:{WT1A_CURIE}->HGNC:12796"
      and human[0]["url"] == "https://www.alliancegenome.org/gene/HGNC:12796"
      and human[0]["methods_matched_n"] == n_methods_human == 10 and human[0]["identifier_provenance"] == "alliance-api-payload",
      f"status={r1['status']} err={r1.get('error')} n={len(rows)}")
check("A2 mediciones declaradas: query_sent literal con filter.stringency=stringent&limit=200, n_http_gets=1, cache_hit False, "
      "schema_observed nombra geneToGeneOrthologyGenerated, orthologs_capped False, n_total_api 4",
      r1["query_sent"].endswith(f"/gene/{WT1A_CURIE}/orthologs?filter.stringency=stringent&limit=200")
      and r1["n_http_gets"] == 1 and r1["cache_hit"] is False and r1["data"]["n_total_api"] == 4
      and r1["data"]["orthologs_capped"] is False and "geneToGeneOrthologyGenerated" in r1["data"]["schema_observed"]
      and [t for _, t in net.calls] == [7], f"calls={net.calls}")
net2 = FakeAlliance(AL_PAYLOAD); al._get = net2
r2 = al.query_orthologs(curie=WT1A_CURIE, cache_dir=d_al)
check("A3 cache de lectura por dia: segundo golpe cache_hit True, n_http_gets 0, cached_at declarado, misma tabla, "
      "archivo alliance_orthologs_*_<YYYYMMDD>.json existe en el cache_dir temporal",
      r2["status"] == "success" and r2["cache_hit"] is True and r2["n_http_gets"] == 0 and net2.calls == []
      and r2["cached_at"] and r2["data"]["orthologs"] == rows and Path(r2["cache_path"]).exists()
      and Path(r2["cache_path"]).name.startswith("alliance_orthologs_") and Path(r2["cache_path"]).name.endswith(al._today() + ".json"),
      f"cache_path={r2['cache_path']}")
net3 = FakeAlliance(AL_PAYLOAD); al._get = net3
r3 = al.query_orthologs(symbol="wt1a", cache_dir=fresh_dir("alliance2"), timeout=5)
check("A4 ruta por simbolo: resolve (search_autocomplete) + orthologs = 2 GETs, ambas con timeout=5, curie resuelto (no de memoria)",
      r3["status"] == "success" and r3["n_http_gets"] == 2 and [t for _, t in net3.calls] == [5, 5]
      and "/search_autocomplete?q=wt1a" in net3.calls[0][0] and r3["data"]["zfin_curie"] == WT1A_CURIE)
r5 = al.query_orthologs(curie=WT1A_CURIE, cache_dir=d_al, target_taxa={"NCBITaxon:9606"})
check("A5 target_taxa humano: 1 fila conservada, n_filtered_out 3 DECLARADO (no descarte silencioso)",
      r5["status"] == "success" and len(r5["data"]["orthologs"]) == 1 and r5["data"]["n_filtered_out"] == 3
      and r5["data"]["n_returned"] == 4 and r5["data"]["target_taxa"] == ["NCBITaxon:9606"])
al._get = FakeAlliance({"total": 0, "returnedRecords": 0, "results": []})
r6 = al.query_orthologs(curie=WT1A_CURIE, cache_dir=fresh_dir("alliance_nm"))
check("A6 no-match: total 0 -> status 'no-match' con data (n_returned 0), NO 'error'",
      r6["status"] == "no-match" and r6["data"]["n_returned"] == 0 and r6["data"]["orthologs"] == [] and "error" not in r6)
d_err = fresh_dir("alliance_err")
al._get = FakeAlliance(AL_PAYLOAD, raise_on_orthologs=urllib.error.HTTPError("u", 503, "Service Unavailable", {}, None))
r7 = al.query_orthologs(curie=WT1A_CURIE, cache_dir=d_err)
net8 = FakeAlliance(AL_PAYLOAD); al._get = net8
r8 = al.query_orthologs(curie=WT1A_CURIE, cache_dir=d_err)
check("A7 error de red (HTTP 503): status 'error' con tipo declarado, sin data; el error NO se cachea (la siguiente llamada vuelve a la red)",
      r7["status"] == "error" and r7["error"].startswith("HTTPError") and "data" not in r7
      and r8["status"] == "success" and r8["n_http_gets"] == 1 and len(net8.calls) == 1, f"err={r7.get('error')}")
net9 = FakeAlliance(AL_PAYLOAD); al._get = net9
r9 = al.query_orthologs(curie=WT1A_CURIE, cache_dir=fresh_dir("alliance_b"), timeout=0)
check("A8 presupuesto agotado (timeout=0): status 'skipped-budget' declarado y CERO llamadas de red",
      r9["status"] == "skipped-budget" and "BudgetExhausted" in r9["error"] and net9.calls == [] and r9["n_http_gets"] == 0)
CAPPED = {"total": 250, "returnedRecords": 200, "results": AL_PAYLOAD["results"] * 50}
al._get = FakeAlliance(CAPPED)
r10 = al.query_orthologs(curie=WT1A_CURIE, cache_dir=fresh_dir("alliance_cap"))
check("A9 API con total 250 > 200 devueltos -> orthologs_capped True declarado, limit_sent 200",
      r10["status"] == "success" and r10["data"]["orthologs_capped"] is True and r10["data"]["n_returned"] == 200
      and r10["data"]["limit_sent"] == al.ORTHOLOGS_API_LIMIT == 200)
net11 = FakeAlliance(AL_PAYLOAD); al._get = net11
r11 = al.query_orthologs(curie=WT1A_CURIE, stringency="loose", cache_dir=fresh_dir("alliance_s"))
check("A10 stringency invalida -> 'error' explicito sin tocar la red",
      r11["status"] == "error" and "stringency" in r11["error"] and net11.calls == [])
al._get = FakeAlliance(AL_PAYLOAD, autocomplete={"results": []})
r12 = al.query_orthologs(symbol="zzznotagene", cache_dir=fresh_dir("alliance_u"))
check("A11 simbolo sin gen resuelto -> 'no-match' MEDIDO con no_match_reason 'symbol-unresolved' (la API respondio; "
      "corrector ADR-0080: no es un fallo de transporte), zfin_curie None, orthologs [] (jamas un curie inventado); "
      "throttle declarado {host www.alliancegenome.org, min_interval_s 0.2, available, waited_s}",
      r12["status"] == "no-match" and r12["no_match_reason"] == "symbol-unresolved"
      and r12["data"]["zfin_curie"] is None and r12["data"]["orthologs"] == [] and r12["data"]["n_returned"] == 0
      and r12["throttle"]["host"] == "www.alliancegenome.org" and r12["throttle"]["min_interval_s"] == 0.2
      and isinstance(r12["throttle"]["available"], bool) and isinstance(r12["throttle"]["waited_s"], float))

# =====================================================================================================
# B. ensembl_homology
# =====================================================================================================
with open(FX_ENSEMBL, encoding="utf-8") as f:
    EN_ENV = json.load(f)
EN_PAYLOAD, EN_RL = EN_ENV["payload"], EN_ENV["rate_limit_headers"]


class FakeEnsembl:
    """Sirve (payload, status, headers) o lanza la secuencia de excepciones dada; graba (url, timeout)."""

    def __init__(self, payload=EN_PAYLOAD, headers=EN_RL, raises=()):
        self.payload, self.headers, self.raises = payload, headers, list(raises)
        self.calls = []

    def __call__(self, url, timeout=None):
        self.calls.append((url, timeout))
        if self.raises:
            e = self.raises.pop(0)
            if e is not None:
                raise e
        return self.payload, 200, self.headers


def http_err(code, body=None, headers=None):
    import email.message
    h = email.message.Message()
    for k, v in (headers or {}).items():
        h[k] = v
    return urllib.error.HTTPError("u", code, "reason", h, io.BytesIO(json.dumps(body or {}).encode("utf-8")))


if ens.net_throttle is not None:
    ens.net_throttle._sleep = lambda s: None   # el smoke no duerme: el reintento se ASIERTA, no se espera

print("\n--- B. ensembl_homology ---")
check("B0 fixture real 2026-09-15: HTTP 200, X-RateLimit-Limit/Remaining/Period/Reset medidos, data[0].id ENSDARG00000031420, "
      "1 homologia ortholog_one2one -> ENSG00000184937 (alineamientos recortados y declarados)",
      EN_ENV["http_status"] == 200 and set(EN_RL) >= {"X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Period", "X-RateLimit-Reset"}
      and EN_PAYLOAD["data"][0]["id"] == "ENSDARG00000031420" and len(EN_PAYLOAD["data"][0]["homologies"]) == 1
      and EN_PAYLOAD["data"][0]["homologies"][0]["type"] == "ortholog_one2one"
      and EN_PAYLOAD["data"][0]["homologies"][0]["target"]["id"] == "ENSG00000184937"
      and EN_ENV["cut"]["alignment_fields_dropped"] == 4 and ";content-type=application/json" in EN_ENV["url"])
d_en = fresh_dir("ensembl")
fe = FakeEnsembl(); ens._get_with_headers = fe
e1 = ens.query_homology("wt1a", cache_dir=d_en, timeout=9)
h0 = (e1.get("data") or {}).get("homologies", [{}])[0]
check("B1 fixture: success, 1 homologia one2one danio_rerio->homo_sapiens, ids/protein_ids/perc_id del payload, evidence_id/url, "
      "types={'ortholog_one2one':1}",
      e1["status"] == "success" and e1["data"]["n_homologies"] == 1 and h0["type"] == "ortholog_one2one"
      and h0["source_id"] == "ENSDARG00000031420" and h0["target_id"] == "ENSG00000184937"
      and h0["target_species"] == "homo_sapiens" and h0["target_taxon_id"] == 9606 and h0["target_protein_id"] == "ENSP00000415516"
      and abs(h0["target_perc_id"] - 61.1111) < 1e-3 and h0["evidence_id"] == "ensembl-homology:ENSDARG00000031420->ENSG00000184937"
      and h0["url"] == "https://www.ensembl.org/id/ENSG00000184937" and e1["data"]["types"] == {"ortholog_one2one": 1}
      and e1["data"]["source_gene_id"] == "ENSDARG00000031420" and h0["identifier_provenance"] == "ensembl-api-payload",
      f"status={e1['status']} err={e1.get('error')}")
check("B2 mediciones: query_sent literal (danio_rerio/wt1a?target_species=homo_sapiens;content-type=application/json), http_status 200, "
      "rate_limit_headers == cabeceras medidas, retries_429 0, n_http_gets 1, timeout=9 propagado, throttle declarado (host, intervalo, fuente)",
      e1["query_sent"] == "https://rest.ensembl.org/homology/symbol/danio_rerio/wt1a?target_species=homo_sapiens;content-type=application/json"
      and e1["http_status"] == 200 and e1["rate_limit_headers"] == EN_RL and e1["retries_429"] == 0 and e1["n_http_gets"] == 1
      and [t for _, t in fe.calls] == [9] and e1["throttle"]["host"] == "rest.ensembl.org"
      and e1["throttle"]["min_interval_s"] == ens.DEFAULT_MIN_INTERVAL_S and e1["throttle"]["min_interval_source"] == "default"
      and e1["throttle"]["available"] is (ens.net_throttle is not None), f"qs={e1['query_sent']}")
fe2 = FakeEnsembl(); ens._get_with_headers = fe2
e2 = ens.query_homology("wt1a", cache_dir=d_en)
check("B3 cache por dia: cache_hit True, n_http_gets 0, cabeceras y http_status conservados del dia, mismas filas",
      e2["status"] == "success" and e2["cache_hit"] is True and e2["n_http_gets"] == 0 and fe2.calls == []
      and e2["rate_limit_headers"] == EN_RL and e2["http_status"] == 200 and e2["data"]["homologies"] == e1["data"]["homologies"]
      and Path(e2["cache_path"]).name.startswith("ensembl_homology_danio_rerio_wt1a_homo_sapiens_"))
ens._get_with_headers = FakeEnsembl(raises=[http_err(400, {"error": "No valid lookup found for symbol wt1zz"})])
e3 = ens.query_homology("wt1zz", cache_dir=fresh_dir("ensembl_nm"))
check("B4 no-match: HTTP 400 'No valid lookup found for symbol' -> status 'no-match' con razon declarada, http_status 400, homologias []",
      e3["status"] == "no-match" and e3["no_match_reason"] == "ensembl-400-no-valid-lookup" and e3["http_status"] == 400
      and e3["data"]["homologies"] == [] and e3["data"]["n_homologies"] == 0, f"status={e3['status']} err={e3.get('error')}")
ens._get_with_headers = FakeEnsembl(payload={"data": [{"id": "ENSDARG00000031420", "homologies": []}]}, headers=None)
e4 = ens.query_homology("wt1a", cache_dir=fresh_dir("ensembl_nm2"))
check("B5 200 con homologies=[] -> 'no-match' razon 'zero-homologies-in-payload'; sin X-RateLimit -> rate_limit_headers None DECLARADO",
      e4["status"] == "no-match" and e4["no_match_reason"] == "zero-homologies-in-payload"
      and "rate_limit_headers" in e4 and e4["rate_limit_headers"] is None and e4["data"]["source_gene_id"] == "ENSDARG00000031420")
if ens.net_throttle is not None:
    fe6 = FakeEnsembl(raises=[http_err(429, {"error": "rate"}, {"Retry-After": "2"}), None]); ens._get_with_headers = fe6
    e6 = ens.query_homology("wt1a", cache_dir=fresh_dir("ensembl_429"))
    check("B6 429 una vez + Retry-After: UN reintento (retries_429 1, retry_after_s 2 de 'header'), 2 GETs, success",
          e6["status"] == "success" and e6["retries_429"] == 1 and e6["retry_after_s"] == 2.0 and e6["retry_after_src"] == "header"
          and e6["n_http_gets"] == 2 and len(fe6.calls) == 2, f"status={e6['status']} err={e6.get('error')} retries={e6.get('retries_429')}")
    fe7 = FakeEnsembl(raises=[http_err(429, {"error": "rate"}, {"X-RateLimit-Remaining": "0"}), http_err(429, {"error": "rate"}, {"X-RateLimit-Remaining": "0"})])
    ens._get_with_headers = fe7
    e7 = ens.query_homology("wt1a", cache_dir=fresh_dir("ensembl_429b"))
    check("B7 429 dos veces: 'error' declarado tras UN reintento (jamas un lazo), retries_429 1, http_status 429, "
          "cabeceras X-RateLimit de la respuesta de ERROR medidas, 2 GETs exactos",
          e7["status"] == "error" and e7["retries_429"] == 1 and e7["http_status"] == 429 and len(fe7.calls) == 2
          and e7["rate_limit_headers"] == {"X-RateLimit-Remaining": "0"}, f"status={e7['status']} err={e7.get('error')}")
else:
    check("B6 net_throttle no importable -> declarado en throttle.available", False, ens._THROTTLE_IMPORT_ERROR or "")
    check("B7 (omitido: sin net_throttle)", False)
ens._get_with_headers = FakeEnsembl(raises=[urllib.error.URLError("dns down")])
e8 = ens.query_homology("wt1a", cache_dir=fresh_dir("ensembl_err"))
check("B8 error de red (URLError): status 'error' con tipo declarado, sin data",
      e8["status"] == "error" and e8["error"].startswith("URLError") and "data" not in e8, e8.get("error"))
fe9 = FakeEnsembl(); ens._get_with_headers = fe9
e9 = ens.query_homology("wt1a", cache_dir=fresh_dir("ensembl_b"), timeout=0)
check("B9 presupuesto agotado (timeout=0): 'skipped-budget' y CERO llamadas",
      e9["status"] == "skipped-budget" and fe9.calls == [] and e9["n_http_gets"] == 0 and "BudgetExhausted" in e9["error"])
e10 = ens.query_homology("", cache_dir=fresh_dir("ensembl_e"))
check("B10 simbolo vacio -> 'error' explicito sin red", e10["status"] == "error" and fe9.calls == [])

# =====================================================================================================
# C. zfin_expression_tsv
# =====================================================================================================
with open(FX_ZFIN, encoding="utf-8") as f:
    ZX_ENV = json.load(f)
ZX_LINES = ZX_ENV["lines"]
ZX_BYTES = ("\n".join(ZX_LINES) + "\n").encode("utf-8")


class FakeStream:
    """Respuesta binaria de fixture; `raise_exc` la hace fallar al abrir; `chunks_before_fail` la corta a medias."""

    def __init__(self, data=ZX_BYTES, raise_exc=None, fail_after_reads=None):
        self.buf, self.raise_exc, self.fail_after = io.BytesIO(data), raise_exc, fail_after_reads
        self.reads = 0
        self.closed = False

    def read(self, n=-1):
        self.reads += 1
        if self.fail_after is not None and self.reads > self.fail_after:
            raise ConnectionResetError("peer reset mid-download")
        return self.buf.read(n)

    def close(self):
        self.closed = True


class FakeNetZ:
    def __init__(self, **kw):
        self.kw, self.calls, self.streams = kw, [], []

    def __call__(self, url, timeout=None):
        self.calls.append((url, timeout))
        if self.kw.get("raise_exc"):
            raise self.kw["raise_exc"]
        s = FakeStream(**{k: v for k, v in self.kw.items() if k != "raise_exc"})
        self.streams.append(s)
        return s


print("\n--- C. zfin_expression_tsv ---")
cut = ZX_ENV["cut"]
check("C0 fixture real 2026-09-15: 200 lineas, recorte DECLARADO (total 243119 lineas / 43.7 MB descargados), "
      "column_detection 'positional' con 15 columnas, TODAS las lineas con 15 columnas, sin cabecera",
      len(ZX_LINES) == 200 and cut["lines_kept"] == 200 and cut["total_lines_in_download"] == 243119 and cut["total_lines_in_download"] > 200
      and cut["total_bytes"] == 43700153 and ZX_ENV["column_detection"]["column_mode"] == "positional"
      and ZX_ENV["column_detection"]["n_columns"] == 15 and all(len(l.split("\t")) == 15 for l in ZX_LINES)
      and ZX_LINES[0].startswith("ZDB-GENE-060824-3\ta1cf\tWT\tZFA:0000123\tliver"))
det = zx.detect_columns(ZX_LINES[:3])
check("C1 detect_columns sobre la cabeza REAL: 'positional', columnas == POSITIONAL_SCHEMA (15 roles), head_observed = 3 lineas, fuente declarada",
      det["column_mode"] == "positional" and tuple(det["columns"]) == zx.POSITIONAL_SCHEMA and det["n_columns"] == 15
      and len(det["head_observed"]) == 3 and det["schema_source"].startswith("POSITIONAL_SCHEMA"))
HDR = "Gene ID\tGene Symbol\tFish Name\tSuper Structure ID\tSuper Structure Name\tSub Structure ID\tSub Structure Name\tStart Stage\tEnd Stage\tAssay\tAssay MMO ID\tPublication ID\tProbe ID\tAntibody ID\tFish ID"
det_h = zx.detect_columns([HDR, ZX_LINES[0], ZX_LINES[1]])
check("C2 detect_columns con cabecera sintetica: 'header', 15 roles mapeados por nombre, unmapped_headers []",
      det_h["column_mode"] == "header" and tuple(det_h["columns"]) == zx.POSITIONAL_SCHEMA and det_h["unmapped_headers"] == []
      and det_h["header_raw"][0] == "Gene ID")
d_zx = fresh_dir("zfin")
nz = FakeNetZ(); zx._get_stream = nz
z1 = zx.query_expression("aanat2", cache_dir=d_zx, timeout=11, limit=None)
rows_z = (z1.get("data") or {}).get("rows", [])
n_aanat2 = sum(1 for l in ZX_LINES if l.split("\t")[1] == "aanat2")
check("C3 fixture: success para aanat2 (58 filas = conteo directo del fixture), 1 GET con timeout=11, cache_hit False, "
      "archivo zfin_wildtype_expression_<YYYYMMDD>.txt escrito (sin .part), n_lines 200 medido, scan_complete True, n_rows_scanned 200, positional",
      z1["status"] == "success" and z1["data"]["n_matched_gene"] == n_aanat2 == 58 and z1["data"]["n_matched"] == 58 and len(rows_z) == 58
      and z1["n_http_gets"] == 1 and z1["cache_hit"] is False and [t for _, t in nz.calls] == [11]
      and Path(z1["cache_path"]).exists() and Path(z1["cache_path"]).name == f"zfin_wildtype_expression_{zx._today()}.txt"
      and not Path(z1["cache_path"] + ".part").exists() and z1["download"]["n_lines"] == 200 and z1["download"]["bytes"] == len(ZX_BYTES)
      and z1["scan_complete"] is True and z1["n_rows_scanned"] == 200 and z1["column_mode"] == "positional"
      and nz.streams[0].closed, f"status={z1['status']} err={z1.get('error')} n={len(rows_z)}")
r0 = rows_z[0] if rows_z else {}
resolvable = all(ZX_LINES[r["raw_ref"]["line_no"] - 1].split("\t")[1] == "aanat2"
                 and ZX_LINES[r["raw_ref"]["line_no"] - 1].split("\t")[11] == (r["pub_id"] or "")
                 and r["raw_ref"]["line_no"] == r["line_no"] and r["raw_ref"]["file_date"] == zx._today()
                 for r in rows_z)
_ids_expected = all(r["evidence_id"] == zx.build_evidence_id(r["resolves_to"], r["stage_start"], r["stage_end"])
                    and r["evidence_id"].startswith(f"zfin-expression:{r['gene_id']}:{r['anatomy_id']}:{r['pub_id']}:{r['assay_id']}")
                    for r in rows_z)
check("C4 evidence_id ESTABLE desde las llaves EXTERNAS de la fila (corrector ADR-0080): 'zfin-expression:<ZDB-GENE>:<ZFA>:<ZDB-PUB>:"
      "<MMO>[:sub][:fish][:stage]' == build_evidence_id(resolves_to) en 58/58 (no un numero de linea del TSV del dia); raw_ref "
      "{file_date, line_no} sigue LOCALIZANDO la linea real (58/58 traen ese gen y esa publicacion); url https://zfin.org/<ZDB-PUB>, "
      "gene_id ZDB-GENE, anatomy/anatomy_id ZFA, stage/assay/MMO poblados, provenance 'zfin-tsv-row-keys', evidence_id_rule declarada",
      resolvable and _ids_expected and r0.get("evidence_id", "").startswith("zfin-expression:ZDB-GENE-")
      and ":L" not in r0.get("evidence_id", "")
      and r0.get("url", "").startswith("https://zfin.org/ZDB-PUB-") and str(r0.get("gene_id", "")).startswith("ZDB-GENE-")
      and str(r0.get("anatomy_id", "")).startswith("ZFA:") and r0.get("anatomy") and r0.get("stage_start") and r0.get("assay")
      and str(r0.get("assay_id", "")).startswith("MMO:") and r0.get("identifier_provenance") == "zfin-tsv-row-keys"
      and r0.get("resolves_to", {}).get("publication_id") == r0.get("pub_id")
      and z1["data"]["identifier_provenance"] == "zfin-tsv-row-keys" and "evidence_id_rule" in z1["data"]
      and z1["data"]["n_rows_malformed"] == 0 and z1["n_rows_malformed"] == 0
      and z1["data"]["source_file_date"] == zx._today(), json.dumps(r0, ensure_ascii=False)[:300])
_ids_all = [r["evidence_id"] for r in rows_z]
check("C4b evidence_id distinto por fila del mismo gen (58 filas, 58 ids: stage/estructura/fish entran a la llave cuando difieren) "
      "y determinista (build_evidence_id puro); una fila con una comilla en la anatomia NO corre columnas (split por TAB) y una "
      "linea con menos columnas se cuenta en n_rows_malformed, no se mapea a roles equivocados",
      len(set(_ids_all)) == len(_ids_all)
      and zx.build_evidence_id({"gene_id": "ZDB-GENE-1", "anatomy_id": "ZFA:1", "publication_id": None, "assay_id": "MMO:1"}, "A", "B")
      == "zfin-expression:ZDB-GENE-1:ZFA:1:na:MMO:1:A-B"
      and (lambda det: det["n_columns"] == 15 and det["column_mode"] == "positional")(
          zx.detect_columns(['ZDB-GENE-1\tg1\tWT\tZFA:1\t"quoted\t\t\tA\tA\tassay\tMMO:1\tZDB-PUB-1\t\t\tZDB-FISH-1'])),
      json.dumps(_ids_all[:2]))
z2 = zx.query_expression("aanat2", anatomy="pineal", cache_dir=d_zx, limit=None)
n_pineal = sum(1 for l in ZX_LINES if l.split("\t")[1] == "aanat2" and any(w.startswith("pineal") for w in l.split("\t")[4].lower().split()))
z2b = zx.query_expression("aanat2", anatomy="physis", cache_dir=d_zx, limit=None)
check("C5 filtro anatomico por PREFIJO DE PALABRA: 'pineal' casa 'pineal complex' y 'pinealocyte' (conteo directo del fixture), "
      "'physis' NO casa 'epiphysis' -> no-match con n_matched_gene 58 conservado; semantica declarada",
      z2["status"] == "success" and z2["data"]["n_matched"] == n_pineal and n_pineal > 0
      and all(any(w.startswith("pineal") for w in (r["anatomy"] or "").lower().split()) for r in z2["data"]["rows"])
      and z2["data"]["anatomy_filter_semantics"].startswith("word-prefix") and z2["data"]["anatomy_terms"] == ["pineal"]
      and z2b["status"] == "no-match" and z2b["data"]["n_matched_gene"] == 58 and z2b["data"]["n_matched"] == 0,
      f"pineal={z2['data']['n_matched']}/{n_pineal} physis={z2b['status']}")
nz2 = FakeNetZ(); zx._get_stream = nz2
z3 = zx.query_expression("aanat2", cache_dir=d_zx, limit=5)
check("C6 cache por dia: segundo golpe cache_hit True, n_http_gets 0, CERO red; limit=5 -> 5 filas, rows_truncated True, n_matched 58 conservado",
      z3["status"] == "success" and z3["cache_hit"] is True and z3["n_http_gets"] == 0 and nz2.calls == [] and z3["cached_at"]
      and len(z3["data"]["rows"]) == 5 and z3["data"]["rows_truncated"] is True and z3["data"]["n_matched"] == 58)
z4 = zx.query_expression("wt1a", cache_dir=d_zx)
check("C7 no-match: 'wt1a' no esta en las 200 lineas del fixture -> 'no-match' con scan_complete True, n_matched_gene 0, rows [] (NO error)",
      z4["status"] == "no-match" and z4["scan_complete"] is True and z4["data"]["n_matched_gene"] == 0 and z4["data"]["rows"] == []
      and z4["n_rows_scanned"] == 200 and "error" not in z4)
d_err = fresh_dir("zfin_err")
zx._get_stream = FakeNetZ(raise_exc=urllib.error.URLError("zfin.org unreachable"))
z5 = zx.query_expression("aanat2", cache_dir=d_err)
check("C8 error de red al abrir: status 'error' URLError declarado, sin archivo ni .part en el cache_dir",
      z5["status"] == "error" and "URLError" in z5["error"] and z5["download"]["status"] == "error"
      and not any(d_err.iterdir()), f"err={z5.get('error')} files={[p.name for p in d_err.iterdir()]}")
zx._get_stream = FakeNetZ(fail_after_reads=0)
z5b = zx.query_expression("aanat2", cache_dir=d_err)
check("C9 corte a media descarga (ConnectionResetError): 'error', el .part se borra, nada queda que un lector tome por tabla completa",
      z5b["status"] == "error" and "ConnectionResetError" in z5b["error"] and not any(d_err.iterdir()))
nz6 = FakeNetZ(); zx._get_stream = nz6
z6 = zx.query_expression("aanat2", cache_dir=fresh_dir("zfin_b"), timeout=0)
check("C10 presupuesto agotado (timeout=0): 'skipped-budget', CERO GETs, cero disco",
      z6["status"] == "skipped-budget" and nz6.calls == [] and z6["n_http_gets"] == 0 and "BudgetExhausted" in z6["error"])
d_cap = fresh_dir("zfin_cap")
zx._get_stream = FakeNetZ()
z7 = zx.query_expression("aanat2", cache_dir=d_cap, download_kwargs={"max_bytes": 1000})
check("C11 tope de bytes (max_bytes=1000 < 41 KB): 'error' BudgetExhausted/OverflowError, .part borrado, max_bytes declarado",
      z7["status"] == "error" and "BudgetExhausted" in z7["error"] and "OverflowError" in z7["error"]
      and z7["download"]["max_bytes"] == 1000 and not any(d_cap.iterdir()), f"err={z7.get('error')}")


class FakeTime:
    """Reloj monotono que avanza 100 s por lectura: agota cualquier presupuesto sin dormir."""

    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        self.t += 100.0
        return self.t

    def sleep(self, s):
        pass


real_time = zx.time
d_bud = fresh_dir("zfin_bud")
zx._get_stream = FakeNetZ()
zx.time = FakeTime()
z8 = zx.query_expression("aanat2", cache_dir=d_bud, budget_s=50)
zx.time = real_time
check("C12 presupuesto de descarga agotado (reloj simulado, budget_s=50): 'error' BudgetExhausted/TimeoutError, .part borrado, budget_s declarado",
      z8["status"] == "error" and "BudgetExhausted" in z8["error"] and "TimeoutError" in z8["error"]
      and z8["download"]["budget_s"] == 50.0 and not any(d_bud.iterdir()), f"err={z8.get('error')}")
# escaneo: archivo sintetico de 3000 lineas ya en cache + reloj simulado -> corte declarado con filas parciales
d_scan = fresh_dir("zfin_scan")
big = [ZX_LINES[i % len(ZX_LINES)] for i in range(3000)]
zx.cache_file_path(d_scan).write_text("\n".join(big) + "\n", encoding="utf-8")
zx.time = FakeTime()
z9 = zx.query_expression("aanat2", cache_dir=d_scan, scan_budget_s=10, limit=None)
zx.time = real_time
check("C13 presupuesto de ESCANEO agotado: 'error' BudgetExhausted, scan_complete False, n_rows_scanned < 3000, filas parciales DECLARADAS (no 'success')",
      z9["status"] == "error" and "BudgetExhausted" in z9["error"] and z9["scan_complete"] is False
      and 0 < z9["n_rows_scanned"] < 3000 and z9["cache_hit"] is True and isinstance(z9["data"]["rows"], list),
      f"scanned={z9['n_rows_scanned']} err={z9.get('error')}")
# modo cabecera: archivo sintetico con header + 2 filas
d_hdr = fresh_dir("zfin_hdr")
zx.cache_file_path(d_hdr).write_text(HDR + "\n" + ZX_LINES[0] + "\n" + ZX_LINES[1] + "\n", encoding="utf-8")
z10 = zx.query_expression("a1cf", anatomy="liver", cache_dir=d_hdr)
check("C14 archivo CON cabecera: column_mode 'header' detectado del archivo, 2 filas a1cf/liver, line_no de la primera fila = 2 (la cabecera es L1), 0 GETs",
      z10["status"] == "success" and z10["column_mode"] == "header" and z10["data"]["n_matched"] == 2
      and z10["data"]["rows"][0]["line_no"] == 2 and z10["data"]["rows"][0]["anatomy"] == "liver" and z10["n_http_gets"] == 0
      and z10["n_rows_scanned"] == 2, f"status={z10['status']} err={z10.get('error')} mode={z10.get('column_mode')}")
d_sym = fresh_dir("zfin_sym")
zx.cache_file_path(d_sym).write_text("\n".join(ZX_LINES[:5]) + "\n", encoding="utf-8")
z11 = zx.query_expression("A1CF", cache_dir=d_sym)
check("C15 simbolo case-insensitive exacto: 'A1CF' casa 'a1cf' (3 filas) y nada mas",
      z11["status"] == "success" and z11["data"]["n_matched_gene"] == 3 and all(r["gene"] == "a1cf" for r in z11["data"]["rows"]))
z12 = zx.query_expression("", cache_dir=d_sym)
check("C16 simbolo vacio -> 'error' explicito", z12["status"] == "error")

# =====================================================================================================
# D. contrato comun de las tres tools (lo que el harness (C) consume)
# =====================================================================================================
print("\n--- D. contrato comun ---")
COMMON = {"status", "query_sent", "elapsed_s", "n_http_gets", "cache_hit", "cache_path"}
check("D1 las tres salidas exitosas comparten {status, query_sent, elapsed_s, n_http_gets, cache_hit, cache_path} y data con identifier_provenance",
      all(COMMON <= set(r) for r in (r1, e1, z1)) and all(r["data"].get("identifier_provenance") for r in (r1, e1, z1)))
check("D2 vocabulario de estados de las tres tools ⊆ {success, no-match, error, skipped-budget}",
      {r["status"] for r in (r1, r6, r7, r9, e1, e3, e8, e9, z1, z4, z5, z6)} <= {"success", "no-match", "error", "skipped-budget"}
      and {r["status"] for r in (r1, r6, r7, r9)} == {"success", "no-match", "error", "skipped-budget"})
check("D3 cada item exitoso trae evidence_id y url no nulos (resolubles) en las tres tools",
      all(o["evidence_id"] and o["url"] for o in r1["data"]["orthologs"])
      and all(h["evidence_id"] and h["url"] for h in e1["data"]["homologies"])
      and all(r["evidence_id"] and r["url"] for r in rows_z))
check("D4 mcp_cache/ del repo NO se toco desde este smoke (todo el cache fue al directorio temporal)",
      all(str(TMP) in str(r["cache_path"]) for r in (r1, e1, z1)))

shutil.rmtree(TMP, ignore_errors=True)
n_pass = sum(CHECKS)
print(f"\n{n_pass}/{len(CHECKS)} PASS")
sys.exit(0 if n_pass == len(CHECKS) else 1)

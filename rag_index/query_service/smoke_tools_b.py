"""smoke_tools_b.py — gate determinista de los tools Layer 0 del lote B (ADR-0080, rebanada C4).

Cubre las CUATRO tools nuevas en .tooluniverse/tools/: uniprot_search, monarch_associations,
reactome_search, string_partners. Para cada una:
  (a) el fixture REAL grabado el 2026-09-15 (UNA GET por API, wt1a / ZFIN:ZDB-GENE-980526-558) produce
      status 'success' o 'no-match' con los campos, etiquetas ('predictive' STRING, 'inferred-by-orthology'
      Reactome, None UniProt/Monarch), evidence_id y provenance declarados;
  (b) respuesta vacia -> 'no-match' (jamas 'error', jamas 'success' vacio);
  (c) error de red (HTTP 503) -> 'error' con el tipo declarado y SIN data;
  (d) timeout<=0 -> 'error' BudgetExhausted con CERO llamadas de red; timeout propagado a la GET;
  (e) cache de lectura por dia (mcp_cache redirigido a un directorio temporal): la segunda llamada es
      cache_hit=True con n_http_gets=0 y el mismo resultado.
Hallazgos vivos fijados: Reactome NO honra types=Pathway (devolvio un Protein) -> no-match declarado con
entity_hits; UniProt X-Total-Results 6 > 5 -> truncated_by_size; Monarch 20/20 publicaciones ZFIN:ZDB-PUB
-> 'unresolved-zfin-curie'; STRING throttle 1 s declarado (el sleep se stubbea, nunca se espera de verdad).

100% offline: se monkeypatchea `<tool>._get` (la UNICA costura de red) y `<tool>.CACHE_DIR`.
Cero red / cero spend / cero mutacion de DATA INAMOVIBLE. Exit 0 = todo PASS.

Corre:  python rag_index/query_service/smoke_tools_b.py
"""
import importlib.util
import json
import os
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
FIX = HERE / "fixtures"
WT1A_CURIE = "ZFIN:ZDB-GENE-980526-558"

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


def load(name):
    spec = importlib.util.spec_from_file_location(f"_witt_ws_{name}", TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fixture(name):
    with open(FIX / name, encoding="utf-8") as f:
        blob = json.load(f)
    return blob["response"], blob["_fixture"].get("headers_subset") or {}, blob["_fixture"]


class FakeNet:
    """Sirve (payload, headers) y GRABA cada llamada (url, timeout); opcionalmente levanta un error."""

    def __init__(self, payload, headers=None, raise_exc=None):
        self.payload, self.headers, self.raise_exc, self.calls = payload, headers or {}, raise_exc, []

    def __call__(self, url, timeout=None):
        self.calls.append((url, timeout))
        if self.raise_exc:
            raise self.raise_exc
        return self.payload, dict(self.headers)


TMP = Path(tempfile.mkdtemp(prefix="witt-smoke-tools-b-"))
HTTP503 = urllib.error.HTTPError("u", 503, "Service Unavailable", {}, None)

uniprot = load("uniprot_search")
monarch = load("monarch_associations")
reactome = load("reactome_search")
string = load("string_partners")
for mod in (uniprot, monarch, reactome, string):
    mod.CACHE_DIR = TMP / mod.TOOL_FAMILY          # jamas escribe en el mcp_cache real desde el smoke
if string.net_throttle is not None:
    string.net_throttle._sleep = lambda s: None    # el throttle se DECLARA; el smoke no duerme


def common_checks(tag, mod, fn, args, payload, headers, expect_status):
    """Bloque comun (b)(c)(d)(e) para cada tool. Devuelve el resultado del fixture (a)."""
    # (a) fixture real, sin cache
    net = FakeNet(payload, headers)
    mod._get = net
    res = fn(*args, use_cache=False)
    check(f"[{tag}] fixture real -> status '{expect_status}', 1 GET, query_sent == URL enviada, sin cache",
          res["status"] == expect_status and net.calls and res["n_http_gets"] == 1
          and res["query_sent"] == net.calls[0][0] and res["cache_hit"] is False and res["cache_ref"] is None,
          f"status={res.get('status')} err={res.get('error')} url={res.get('query_sent')}")
    check(f"[{tag}] sobre: evidence_kind/label declarados a nivel resultado y elapsed_s medido",
          res["evidence_kind"] == mod.EVIDENCE_KIND and res["label"] == mod.LABEL
          and isinstance(res["elapsed_s"], float))
    # (b) vacio -> no-match
    net_e = FakeNet(payload.__class__() if not isinstance(payload, dict) else
                    {k: ([] if isinstance(v, list) else (0 if isinstance(v, int) else v)) for k, v in payload.items()},
                    headers={})
    mod._get = net_e
    res_e = fn(*args, use_cache=False)
    check(f"[{tag}] respuesta vacia -> 'no-match' con data e items=[] (no 'error', no 'success')",
          res_e["status"] == "no-match" and res_e["data"]["items"] == [],
          f"status={res_e.get('status')} err={res_e.get('error')}")
    # (c) error de red
    mod._get = FakeNet(None, raise_exc=HTTP503)
    res_x = fn(*args, use_cache=False)
    check(f"[{tag}] HTTP 503 -> status 'error' con tipo declarado y SIN data (la fila queda 'error', la corrida sigue)",
          res_x["status"] == "error" and res_x["error"].startswith("HTTPError") and "data" not in res_x,
          res_x.get("error"))
    # (d) presupuesto agotado / timeout propagado
    net_z = FakeNet(payload, headers)
    mod._get = net_z
    res_z = fn(*args, timeout=0, use_cache=False)
    check(f"[{tag}] timeout<=0 -> 'error' BudgetExhausted y CERO llamadas de red",
          res_z["status"] == "error" and "BudgetExhausted" in res_z["error"] and net_z.calls == [])
    net_t = FakeNet(payload, headers)
    mod._get = net_t
    fn(*args, timeout=7, use_cache=False)
    check(f"[{tag}] timeout=7 llega a la GET; sin timeout explicito el default DEFAULT_TIMEOUT_S={mod.DEFAULT_TIMEOUT_S}",
          [t for _, t in net_t.calls] == [7] and (mod._get.__class__ is FakeNet)
          and (lambda n: (setattr(mod, "_get", n), fn(*args, use_cache=False), [t for _, t in n.calls])[2])(FakeNet(payload, headers)) == [mod.DEFAULT_TIMEOUT_S],
          f"calls={net_t.calls}")
    # (e) cache por dia
    net_c = FakeNet(payload, headers)
    mod._get = net_c
    first = fn(*args, use_cache=True)
    second = fn(*args, use_cache=True)
    same_data = json.dumps(first.get("data"), sort_keys=True) == json.dumps(second.get("data"), sort_keys=True)
    check(f"[{tag}] cache por dia: 1a llamada GET+escribe (cache_ref declarado bajo mcp_cache), 2a llamada cache_hit=True, 0 GETs, mismo data",
          first["cache_hit"] is False and first["n_http_gets"] == 1 and first["cache_ref"]
          and second["cache_hit"] is True and second["n_http_gets"] == 0 and len(net_c.calls) == 1 and same_data
          and Path(TMP / mod.TOOL_FAMILY / Path(first["cache_ref"]).name).exists(),
          f"ref={first.get('cache_ref')} calls={len(net_c.calls)}")
    check(f"[{tag}] nombre de cache <tool>_<slug>_..._<YYYYMMDD>.json",
          Path(first["cache_ref"]).name.startswith(f"{mod.TOOL_FAMILY}_") and Path(first["cache_ref"]).name.endswith(".json")
          and len(Path(first["cache_ref"]).stem.rsplit("_", 1)[-1]) == 8)
    return res


# ================================ UniProt ================================================================
U_PAYLOAD, U_HEADERS, U_META = fixture("uniprot_wt1a_20260915.json")
check("[uniprot] fixture real 2026-09-15: 5 entradas, X-Total-Results 6, URL gene_exact+organism_id 7955",
      len(U_PAYLOAD["results"]) == 5 and U_HEADERS.get("x-total-results") == "6"
      and "gene_exact%3Awt1a" in U_META["url_sent"] and "organism_id%3A7955" in U_META["url_sent"])
ru = common_checks("uniprot", uniprot, uniprot.query_uniprot, ("wt1a",), U_PAYLOAD, U_HEADERS, "success")
du = ru["data"]
check("[uniprot] 5 items taxon 7955, todos con accession/evidence_id 'uniprot:<acc>', label None, kind protein-record",
      du["n_returned_by_api"] == 5 and len(du["items"]) == 5 and du["n_off_taxon"] == 0
      and all(i["evidence_id"] == f"uniprot:{i['accession']}" and i["label"] is None
              and i["kind"] == "protein-record" and i["identifier_provenance"] == uniprot.IDENTIFIER_PROVENANCE
              for i in du["items"]))
check("[uniprot] n_total=6 desde header x-total-results (fuente declarada) -> truncated_by_size True, size_sent 5",
      du["n_total"] == 6 and du["n_total_source"] == "header:x-total-results" and du["truncated_by_size"] is True
      and du["size_sent"] == 5)
check("[uniprot] ZFIN xref VERBATIM -> zfin_curie ZFIN:ZDB-GENE-980526-558 en la entrada Q9PUT7; reviewed False (TrEMBL) declarado",
      du["items"][0]["accession"] == "Q9PUT7" and du["items"][0]["zfin_curie"] == WT1A_CURIE
      and du["items"][0]["reviewed"] is False and du["n_unreviewed"] == 5 and du["n_reviewed"] == 0
      and du["items"][0]["protein_name"] == "Wilms tumor protein homolog" and du["items"][0]["sequence_length"] == 419)
check("[uniprot] reviewed en TRES estados: 'UniProtKB reviewed (Swiss-Prot)' -> True, 'UniProtKB unreviewed (TrEMBL)' -> False, sin entryType -> None (ausente != False)",
      uniprot.parse_entry({"entryType": "UniProtKB reviewed (Swiss-Prot)"})["reviewed"] is True
      and uniprot.parse_entry({"entryType": "UniProtKB unreviewed (TrEMBL)"})["reviewed"] is False
      and uniprot.parse_entry({})["reviewed"] is None)
uniprot._get = FakeNet(U_PAYLOAD, {})
r_nh = uniprot.query_uniprot("wt1a", use_cache=False)
check("[uniprot] sin header X-Total-Results: n_total None y fuente 'not-available' (no se inventa un total)",
      r_nh["data"]["n_total"] is None and r_nh["data"]["n_total_source"] == "not-available"
      and r_nh["data"]["truncated_by_size"] is False)
OFF = {"results": U_PAYLOAD["results"][:1] + [dict(U_PAYLOAD["results"][1], organism={"taxonId": 9606, "scientificName": "Homo sapiens"})]}
uniprot._get = FakeNet(OFF, {"x-total-results": "2"})
r_off = uniprot.query_uniprot("wt1a", use_cache=False)
check("[uniprot] entrada fuera de taxon 7955 -> excluida y CONTADA en n_off_taxon",
      len(r_off["data"]["items"]) == 1 and r_off["data"]["n_off_taxon"] == 1 and r_off["data"]["n_returned_by_api"] == 2)
check("[uniprot] simbolo vacio -> 'error' sin red",
      uniprot.query_uniprot("", use_cache=False)["status"] == "error")

# ================================ Monarch ================================================================
M_PAYLOAD, M_HEADERS, M_META = fixture("monarch_wt1a_20260915.json")
check("[monarch] fixture real 2026-09-15: total 66, 20 items, subject=curie, category GeneToPhenotypicFeatureAssociation",
      M_PAYLOAD["total"] == 66 and len(M_PAYLOAD["items"]) == 20
      and all(i["subject"] == WT1A_CURIE for i in M_PAYLOAD["items"])
      and "biolink:GeneToPhenotypicFeatureAssociation" in M_META["url_sent"])
rm = common_checks("monarch", monarch, monarch.query_monarch, (WT1A_CURIE,), M_PAYLOAD, M_HEADERS, "success")
dm = rm["data"]
check("[monarch] 20 items con evidence_id 'monarch:<id>', phenotype_id ZP:*, statement = object_label, label None, kind phenotype-association",
      len(dm["items"]) == 20 and all(i["evidence_id"] == f"monarch:{i['association_id']}" and i["phenotype_id"].startswith("ZP:")
                                     and i["statement"] == i["phenotype_label"] and i["label"] is None
                                     and i["kind"] == "phenotype-association" for i in dm["items"]))
check("[monarch] publicaciones ZFIN:ZDB-PUB copiadas VERBATIM y declaradas 'unresolved-zfin-curie' por item y a nivel resultado",
      dm["publications_resolution"] == "unresolved-zfin-curie"
      and all(i["publications_resolution"] == "unresolved-zfin-curie" and i["publications"]
              and all(p.startswith("ZFIN:ZDB-PUB-") for p in i["publications"]) for i in dm["items"])
      and dm["n_publications_total"] == 20 and len(dm["publications_unique"]) == 9)
check("[monarch] n_total 66 > 20 devueltos -> truncated_by_limit True; subject_resolved True; primary source infores:zfin",
      dm["n_total"] == 66 and dm["truncated_by_limit"] is True and dm["limit_sent"] == 20
      and dm["subject_resolved"] is True and dm["primary_knowledge_sources"] == ["infores:zfin"])
check("[monarch] primer item: ZP:0012447 'pronephric glomerulus morphogenesis arrested, abnormal', knowledge_assertion",
      dm["items"][0]["phenotype_id"] == "ZP:0012447" and dm["items"][0]["knowledge_level"] == "knowledge_assertion"
      and dm["items"][0]["phenotype_label"].startswith("pronephric glomerulus"))
check("[monarch] resolucion por item: PMID -> 'pmid'; PMID+ZFIN -> 'mixed'; sin pubs -> 'none'",
      monarch.publications_resolution(["PMID:1"]) == "pmid"
      and monarch.publications_resolution(["PMID:1", "ZFIN:ZDB-PUB-1"]) == "mixed"
      and monarch.publications_resolution([]) == "none")
r_nc = monarch.query_monarch("wt1a", use_cache=False)
check("[monarch] simbolo (no curie) -> 'error' not-a-curie SIN request (identificadores solo si resuelven)",
      r_nc["status"] == "error" and "not-a-curie" in r_nc["error"] and r_nc["n_http_gets"] == 0 and r_nc["query_sent"] is None)
monarch._get = FakeNet({"total": 0, "items": []}, {})
r_unres = monarch.query_monarch("ZFIN:ZDB-GENE-000000-0", use_cache=False)
check("[monarch] curie desconocida con 0 items -> 'no-match' y subject_resolved False (declarado, no inventado)",
      r_unres["status"] == "no-match" and r_unres["data"]["subject_resolved"] is False)

# ================================ Reactome ===============================================================
R_PAYLOAD, R_HEADERS, R_META = fixture("reactome_wt1a_20260915.json")
check("[reactome] fixture real 2026-09-15: types=Pathway pedido, la API devolvio 1 entry de tipo Protein (R-DRE-452420, Q9PUT7)",
      "types=Pathway" in R_META["url_sent"] and R_PAYLOAD["numberOfMatches"] == 1
      and R_PAYLOAD["results"][0]["entries"][0]["type"] == "Protein"
      and R_PAYLOAD["results"][0]["entries"][0]["stId"] == "R-DRE-452420")
rr = common_checks("reactome", reactome, reactome.query_reactome, ("wt1a",), R_PAYLOAD, R_HEADERS, "no-match")
dr = rr["data"]
check("[reactome] hallazgo vivo: filtro NO honrado -> types_filter_honored False, n_pathways 0, entry Protein en non_pathway_entries/entity_hits, items=[]",
      dr["types_filter_honored"] is False and dr["n_pathways"] == 0 and dr["n_non_pathway_entries"] == 1
      and dr["non_pathway_entries"][0]["type"] == "Protein" and dr["non_pathway_entries"][0]["reference_identifier"] == "Q9PUT7"
      and dr["non_pathway_entries"][0]["name"] == "wt1a" and dr["entity_hits"][0]["id"] == "R-DRE-452420"
      and dr["items"] == [] and dr["one_get_per_call"] is True)
PATHWAYS = {"results": [{"typeName": "Pathway", "entriesCount": 2, "entries": [
    {"stId": "R-DRE-1234", "dbId": "1", "name": "<span class=\"highlighting\">wt1a</span> signaling", "type": "Pathway",
     "exactType": "Pathway", "species": ["Danio rerio"], "isDisease": False, "summation": "Inferred <b>pathway</b>."},
    {"stId": "R-DRE-5678", "dbId": "2", "name": "Kidney development", "type": "Pathway", "exactType": "TopLevelPathway",
     "species": ["Danio rerio"], "isDisease": False}]},
    {"typeName": "Protein", "entriesCount": 1, "entries": [{"stId": "R-DRE-452420", "type": "Protein",
                                                            "exactType": "ReferenceGeneProduct", "referenceIdentifier": "Q9PUT7"}]}],
    "numberOfMatches": 3}
reactome._get = FakeNet(PATHWAYS, {})
r_pw = reactome.query_reactome("wt1a", use_cache=False)
dp = r_pw["data"]
check("[reactome] con pathways: 'success', 2 items label 'inferred-by-orthology' + label_note, evidence_id 'reactome:<stId>', kind pathway",
      r_pw["status"] == "success" and dp["n_pathways"] == 2
      and all(i["label"] == "inferred-by-orthology" and i["label_note"] and i["kind"] == "pathway"
              and i["evidence_id"] == f"reactome:{i['st_id']}" and i["identifier_provenance"] == reactome.IDENTIFIER_PROVENANCE
              for i in dp["items"]))
check("[reactome] markup <span> de Reactome removido (declarado name_markup_stripped) y texto verbatim; Protein mezclado sigue fuera de items",
      dp["items"][0]["name"] == "wt1a signaling" and dp["items"][0]["statement"] == "wt1a signaling"
      and dp["items"][0]["text"] == "Inferred pathway." and dp["items"][0]["name_markup_stripped"] is True
      and dp["n_non_pathway_entries"] == 1 and dp["types_filter_honored"] is False)
check("[reactome] URL: query=wt1a&species=Danio%20rerio&types=Pathway",
      reactome.build_url("wt1a").endswith("query=wt1a&species=Danio%20rerio&types=Pathway"))

# ================================ STRING =================================================================
S_PAYLOAD, S_HEADERS, S_META = fixture("string_wt1a_20260915.json")
check("[string] fixture real 2026-09-15: 10 filas, todas preferredName_A=wt1a, species 7955, limit=10",
      isinstance(S_PAYLOAD, list) and len(S_PAYLOAD) == 10 and all(r["preferredName_A"] == "wt1a" and r["ncbiTaxonId"] == 7955 for r in S_PAYLOAD)
      and "species=7955&limit=10" in S_META["url_sent"])
check("[string] net_throttle importable (stdlib, analysis/scripts/lib) — el throttle de 1 s se declara",
      string.net_throttle is not None and string.MIN_INTERVAL_S == 1.0, string._THROTTLE_IMPORT_ERROR or "")
rs = common_checks("string", string, string.query_string, ("wt1a",), S_PAYLOAD, S_HEADERS, "success")
ds = rs["data"]
check("[string] 10 items label 'predictive' + label_note, kind interaction-partner, evidence_id 'string:<A>--<B>', stringId verbatim 7955.ENSDARP*",
      len(ds["items"]) == 10 and all(i["label"] == "predictive" and i["label_note"] and i["kind"] == "interaction-partner"
                                     and i["evidence_id"] == f"string:{i['query_string_id']}--{i['partner_string_id']}"
                                     and i["partner_string_id"].startswith("7955.ENSDARP") for i in ds["items"]))
check("[string] primer socio tbx18 score 0.961 con canales verbatim y canal dominante tscore (text mining -> por eso 'predictive')",
      ds["items"][0]["partner_symbol"] == "tbx18" and ds["items"][0]["combined_score"] == 0.961
      and ds["items"][0]["score_channels"]["tscore"] == 0.959 and ds["items"][0]["dominant_channel"] == "tscore"
      and all(i["dominant_channel"] == "tscore" for i in ds["items"]))
check("[string] symbol_resolved True (A-side eco del simbolo); returned==limit -> truncated_by_limit True con semantica declarada; throttle en el sobre",
      ds["symbol_resolved"] is True and ds["query_string_ids"] == ["7955.ENSDARP00000029174"]
      and ds["truncated_by_limit"] is True and ds["truncated_semantics"].startswith("returned == limit")
      and rs["throttle"]["host"] == "version-12-0.string-db.org" and rs["throttle"]["min_interval_s"] == 1.0
      and isinstance(rs["throttle"]["waited_s"], float))
MIXED_A = [dict(S_PAYLOAD[0]), dict(S_PAYLOAD[1], preferredName_A="wt1b", stringId_A="7955.ENSDARP00000000001")]
string._get = FakeNet(MIXED_A, {})
r_mx = string.query_string("wt1a", limit=10, use_cache=False)
check("[string] fila cuyo lado A no es el simbolo pedido -> excluida y CONTADA (n_partners_other_query=1); 2 devueltas < limit -> truncated False",
      len(r_mx["data"]["items"]) == 1 and r_mx["data"]["n_partners_other_query"] == 1
      and r_mx["data"]["truncated_by_limit"] is False)
string._get = FakeNet([dict(S_PAYLOAD[0], preferredName_A="wt1b")], {})
r_o = string.query_string("wt1a", use_cache=False)
check("[string] solo filas de otro simbolo -> 'no-match' con symbol_resolved False (declarado)",
      r_o["status"] == "no-match" and r_o["data"]["symbol_resolved"] is False)
_saved = string.net_throttle
string.net_throttle = None
r_nt = string.query_string("wt1a", use_cache=False)
string.net_throttle = _saved
check("[string] sin net_throttle importable -> 'error' que lo nombra, sin red (misma politica que pubmed_literature)",
      r_nt["status"] == "error" and "net_throttle not importable" in r_nt["error"] and r_nt["n_http_gets"] == 0)

# ================================ contrato comun del lote =================================================
for tag, res in (("uniprot", ru), ("monarch", rm), ("reactome", rr), ("string", rs)):
    check(f"[{tag}] sobre comun del lote B: status/query_sent/elapsed_s/cache_hit/cache_ref/n_http_gets/evidence_kind/label/data",
          {"status", "query_sent", "elapsed_s", "cache_hit", "cache_ref", "n_http_gets", "evidence_kind", "label", "data"} <= set(res))
    check(f"[{tag}] cada item lleva evidence_id/kind/source_family/label/identifier_provenance/statement/text/url",
          all({"evidence_id", "kind", "source_family", "label", "identifier_provenance", "statement", "text", "url"} <= set(i)
              and i["source_family"] == tag for i in res["data"]["items"]))

# limpieza del cache temporal del smoke
import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)

n_pass = sum(CHECKS)
print(f"\n{n_pass}/{len(CHECKS)} PASS")
sys.exit(0 if n_pass == len(CHECKS) else 1)

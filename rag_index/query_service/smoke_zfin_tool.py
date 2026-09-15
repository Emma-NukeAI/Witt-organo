"""smoke_zfin_tool.py — gate determinista del workspace tool ZFIN (ADR-0078, rebanada I1).

Cubre: el parser de referencias lee el esquema NUEVO de la Alliance (`pubmedPublications[].referencedCurie`)
y cae al VIEJO (`pubmedPubModIDs`) declarando cual uso (`references_schema`); tres estados (success /
success-no-references / error) jamas conflados; cada corte DECLARADO (limit=300 de la API, tope de 5 PMIDs
por statement, `limit` del caller); filtro anatomico server-side OPCIONAL (`filter.termName=<raiz>`, UNA GET
por raiz — `a|b` se midio HTTP 400 en vivo el 2026-09-14, corrector ADR-0078) con el filtro cliente por
PREFIJO DE PALABRA como respaldo siempre activo; default server_filter=False; alcance del total declarado
(`n_phenotypes_total_scope`); `timeout` propagado a TODAS las llamadas de red.

100% offline: se monkeypatchea `zfin_zebrafish._get` (la UNICA costura de red del tool) para servir
  (a) el fixture REAL grabado el 2026-09-13 (fixtures/alliance_phenotypes_wt1a_20260913.json), y
  (b) el golden VIEJO de cuarentena (zfin_sweep_20260822T232036Z/raw/wt1a.json), que es la SALIDA del tool
      con el esquema viejo; se reconstruye la respuesta de la API antigua {phenotypeStatement, pubmedPubModIDs}
      a partir de el (transformacion declarada aqui, no un fixture crudo).
Cero red / cero spend / cero mutacion de DATA INAMOVIBLE. Exit 0 = todo PASS.

Corre:  python rag_index/query_service/smoke_zfin_tool.py
"""
import importlib.util
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TOOL_PATH = ROOT / ".tooluniverse" / "tools" / "zfin_zebrafish.py"
FIXTURE_NEW = HERE / "fixtures" / "alliance_phenotypes_wt1a_20260913.json"
GOLDEN_OLD = ROOT / "rag_index" / "curation" / "quarantine" / "zfin_sweep_20260822T232036Z" / "raw" / "wt1a.json"
WT1A_CURIE = "ZFIN:ZDB-GENE-980526-558"

spec = importlib.util.spec_from_file_location("_witt_ws_zfin_zebrafish", TOOL_PATH)
zfin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(zfin)

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


with open(FIXTURE_NEW, encoding="utf-8") as f:
    NEW = json.load(f)
with open(GOLDEN_OLD, encoding="utf-8") as f:
    OLD_ENVELOPE = json.load(f)

# Reconstruccion DECLARADA de la respuesta de la API con el esquema viejo, a partir del golden de salida.
OLD_API = {"total": OLD_ENVELOPE["data"]["n_phenotypes_total"],
           "results": [{"phenotypeStatement": p["statement"], "pubmedPubModIDs": list(p["references"])}
                       for p in OLD_ENVELOPE["data"]["phenotypes"]]}

AUTOCOMPLETE = {"results": [{"category": "gene_search_result", "name": "wt1a", "curie": WT1A_CURIE},
                            {"category": "gene_search_result", "name": "wt1b", "curie": "ZFIN:ZDB-GENE-050420-319"}]}


class FakeNet:
    """Sirve fixtures por URL y GRABA cada llamada (url, timeout) para asertar propagacion."""

    def __init__(self, phenotypes_payload, autocomplete=AUTOCOMPLETE, raise_on_phenotypes=None):
        self.payload = phenotypes_payload
        self.autocomplete = autocomplete
        self.raise_on_phenotypes = raise_on_phenotypes
        self.calls = []

    def __call__(self, url, timeout=None):
        self.calls.append((url, timeout))
        if "/search_autocomplete" in url:
            return self.autocomplete
        if "/phenotypes" in url:
            if self.raise_on_phenotypes:
                raise self.raise_on_phenotypes
            return self.payload
        raise AssertionError(f"URL inesperada en el smoke: {url}")

    @property
    def phenotypes_url(self):
        return next(u for u, _ in self.calls if "/phenotypes" in u)


def run(payload, **kw):
    net = FakeNet(payload, **{k: kw.pop(k) for k in list(kw) if k in ("autocomplete", "raise_on_phenotypes")})
    zfin._get = net
    return zfin.query_zfin("wt1a", **kw), net


# ---- 0. el hecho verificado 2026-09-13 queda fijado en el fixture ------------------------------------
check("fixture real: 53/53 statements traen pubmedPublications y NINGUNO trae pubmedPubModIDs",
      NEW["total"] == 53 and len(NEW["results"]) == 53
      and all(r.get("pubmedPublications") for r in NEW["results"])
      and not any("pubmedPubModIDs" in r for r in NEW["results"]))

# ---- 1. esquema nuevo: refs != [] y schema declarado --------------------------------------------------
res, net = run(NEW, anatomy=None, limit=100)
d = res.get("data", {})
check("esquema nuevo: status success, 53 matched, TODOS con PMIDs (el parser viejo daba references=[] bajo success)",
      res["status"] == "success" and d["n_matched"] == 53
      and all(p["references"] and all(x.startswith("PMID:") for x in p["references"]) for p in d["phenotypes"]),
      f"status={res.get('status')} n_matched={d.get('n_matched')} err={res.get('error')}")
check("esquema nuevo declarado por statement y a nivel resultado = 'pubmedPublications'",
      d["references_schema"] == "pubmedPublications"
      and all(p["references_schema"] == "pubmedPublications" for p in d["phenotypes"])
      and d["n_statements_with_references"] == 53 and d["n_statements_without_references"] == 0)
check("cortes declarados en FALSE cuando no hubo corte: capped_at_300 / references_truncated / statements_truncated",
      d["phenotypes_capped_at_300"] is False and d["references_truncated"] is False
      and d["statements_truncated"] is False and d["n_returned_by_api"] == 53 and d["n_phenotypes_total"] == 53
      and d["references_cap"] == 5)
check("sin anatomia: la URL pide limit=300 y NO manda filter.termName; anatomy_filter_mode='none'",
      f"?limit={zfin.PHENOTYPES_API_LIMIT}" in net.phenotypes_url and "filter.termName" not in net.phenotypes_url
      and d["anatomy_filter_mode"] == "none" and d["anatomy_terms"] == [],
      net.phenotypes_url)

# ---- 2. fallback al esquema viejo ---------------------------------------------------------------------
res_old, _ = run(OLD_API, anatomy=None, limit=100)
d_old = res_old.get("data", {})
check("esquema viejo (golden cuarentena 2026-08-22): fallback a pubmedPubModIDs, declarado como tal",
      res_old["status"] == "success" and d_old["references_schema"] == "pubmedPubModIDs"
      and d_old["n_matched"] == 50 and all(p["references"] for p in d_old["phenotypes"]),
      f"status={res_old.get('status')} schema={d_old.get('references_schema')}")
new_by_stmt = {p["statement"]: p["references"] for p in d["phenotypes"]}
old_by_stmt = {p["statement"]: p["references"] for p in d_old["phenotypes"]}
shared = set(new_by_stmt) & set(old_by_stmt)
check("paridad: en los 50 statements compartidos, los PMIDs del esquema nuevo == los del golden viejo",
      len(shared) == 50 and all(sorted(new_by_stmt[s]) == sorted(old_by_stmt[s]) for s in shared),
      f"shared={len(shared)}")

# ---- 3. success-no-references (fixture sintetico sin referencias) -------------------------------------
NO_REFS = {"total": 3, "results": [{"phenotypeStatement": "pronephric duct absent, abnormal"},
                                   {"phenotypeStatement": "glomerulus malformed, abnormal", "pubmedPublications": []},
                                   {"phenotypeStatement": "heart looping disrupted, abnormal", "pubmedPubModIDs": []}]}
res_nr, _ = run(NO_REFS)
d_nr = res_nr.get("data", {})
check("statements sin PMIDs -> status 'success-no-references' (NO 'success', NO 'error'), schema 'none'",
      res_nr["status"] == "success-no-references" and d_nr["n_matched"] == 3
      and d_nr["references_schema"] == "none" and all(p["references_schema"] == "none" for p in d_nr["phenotypes"])
      and d_nr["n_statements_with_references"] == 0 and d_nr["n_statements_without_references"] == 3,
      f"status={res_nr.get('status')}")
MIXED = {"total": 2, "results": [
    {"phenotypeStatement": "a", "pubmedPublications": [{"referencedCurie": "PMID:1"}]},
    {"phenotypeStatement": "b", "pubmedPubModIDs": ["PMID:2"]}]}
res_mx, _ = run(MIXED)
check("statements con esquemas distintos -> nivel resultado 'mixed', por statement el suyo",
      res_mx["status"] == "success" and res_mx["data"]["references_schema"] == "mixed"
      and [p["references_schema"] for p in res_mx["data"]["phenotypes"]] == ["pubmedPublications", "pubmedPubModIDs"])
check("statements=0 (busqueda sin hallazgo) -> success con n_matched 0, no 'success-no-references' ni error",
      run({"total": 0, "results": []})[0]["status"] == "success" and run({"total": 0, "results": []})[0]["data"]["n_matched"] == 0)

# ---- 4. truncados declarados ----------------------------------------------------------------------------
MANY = {"total": 1, "results": [{"phenotypeStatement": "pronephros hypoplastic, abnormal",
                                 "pubmedPublications": [{"referencedCurie": f"PMID:{i}"} for i in range(1, 8)]
                                 + [{"referencedCurie": "DOI:10.1/x"}]}]}
res_m, _ = run(MANY)
p0 = res_m["data"]["phenotypes"][0]
check("tope de 5 PMIDs se MANTIENE y se DECLARA: references=5, n_references_total=7, truncated True (statement y resultado)",
      len(p0["references"]) == 5 and p0["n_references_total"] == 7 and p0["references_truncated"] is True
      and res_m["data"]["references_truncated"] is True and "DOI:10.1/x" not in p0["references"])
CAPPED = {"total": 450, "returnedRecords": 300,
          "results": [{"phenotypeStatement": f"stmt {i}", "pubmedPubModIDs": ["PMID:9"]} for i in range(300)]}
res_c, _ = run(CAPPED, limit=None)
check("API con total 450 > 300 devueltos -> phenotypes_capped_at_300 True",
      res_c["data"]["phenotypes_capped_at_300"] is True and res_c["data"]["n_returned_by_api"] == 300
      and res_c["data"]["n_matched"] == 300)
res_l, _ = run(NEW, limit=4)
check("limit del caller: 4 statements devueltos de 53 matched -> statements_truncated True (n_matched se conserva)",
      len(res_l["data"]["phenotypes"]) == 4 and res_l["data"]["n_matched"] == 53
      and res_l["data"]["statements_truncated"] is True)

# ---- 5. filtro anatomico: cliente por default; server-side OPCIONAL, una GET por raiz --------------------------
n_pron = sum(1 for r in NEW["results"] if "pronephr" in r["phenotypeStatement"].lower())
res_d0, net_d0 = run(NEW, anatomy="pronephr")
check("corrector: DEFAULT server_filter=False -> sin filter.termName en la URL, modo 'client', total con alcance 'gene'",
      "filter.termName" not in net_d0.phenotypes_url and res_d0["data"]["anatomy_filter_mode"] == "client"
      and res_d0["data"]["n_matched"] == n_pron and n_pron > 0
      and res_d0["data"]["n_phenotypes_total"] == 53 and res_d0["data"]["n_phenotypes_total_scope"] == "gene"
      and res_d0["data"]["n_http_gets"] == 2 and res_d0["data"]["anatomy_filter_semantics"].startswith("word-prefix"),
      f"url={net_d0.phenotypes_url} n_pron={n_pron}")
res_a, net_a = run(NEW, anatomy="pronephr", server_filter=True)
check("server_filter=True con UNA raiz: URL lleva &filter.termName=pronephr, modo 'server+client', el cliente filtra igual; "
      "total del gen NO medido en esta ruta (None, scope 'server-filtered', server_filter_totals por raiz)",
      "&filter.termName=pronephr" in net_a.phenotypes_url and res_a["data"]["anatomy_filter_mode"] == "server+client"
      and res_a["data"]["n_matched"] == n_pron
      and all("pronephr" in p["statement"].lower() for p in res_a["data"]["phenotypes"])
      and res_a["data"]["n_phenotypes_total"] is None and res_a["data"]["n_phenotypes_total_scope"] == "server-filtered"
      and res_a["data"]["server_filter_totals"] == {"pronephr": 53} and res_a["data"]["n_http_gets"] == 2,
      f"url={net_a.phenotypes_url} n_pron={n_pron}")
res_o, net_o = run(NEW, anatomy="pronephr", anatomy_terms=["glomer", "Pronephr", ""], server_filter=True)
n_union = sum(1 for r in NEW["results"]
              if any(t in r["phenotypeStatement"].lower() for t in ("pronephr", "glomer")))
urls_o = [u for u, _ in net_o.calls if "/phenotypes" in u]
check("varias raices con server_filter: UNA GET por raiz (filter.termName=pronephr y =glomer), JAMAS 'a|b' "
      "(medido HTTP 400 en vivo 2026-09-14); el cliente une sin duplicar statements",
      len(urls_o) == 2 and any(u.endswith("filter.termName=pronephr") for u in urls_o)
      and any(u.endswith("filter.termName=glomer") for u in urls_o) and not any("|" in u or "%7C" in u for u in urls_o)
      and res_o["data"]["anatomy_terms"] == ["pronephr", "glomer"]
      and res_o["data"]["n_matched"] == n_union and n_union >= n_pron and res_o["data"]["n_http_gets"] == 3,
      f"urls={[u[-40:] for u in urls_o]} matched={res_o['data']['n_matched']} union={n_union}")
res_cl, net_cl = run(NEW, anatomy="pronephr", server_filter=False)
check("server_filter=False explicito: sin filter.termName en la URL, modo 'client', mismo n_matched",
      "filter.termName" not in net_cl.phenotypes_url and res_cl["data"]["anatomy_filter_mode"] == "client"
      and res_cl["data"]["n_matched"] == n_pron)
LOOSE = {"total": 2, "results": [{"phenotypeStatement": "pronephric duct absent, abnormal", "pubmedPubModIDs": ["PMID:1"]},
                                 {"phenotypeStatement": "heart looping disrupted, abnormal", "pubmedPubModIDs": ["PMID:2"]}]}
res_ls, _ = run(LOOSE, anatomy="pronephr", server_filter=True)
check("servidor permisivo (devuelve fuera de anatomia) -> el respaldo cliente lo descarta",
      res_ls["data"]["n_matched"] == 1 and res_ls["data"]["phenotypes"][0]["statement"].startswith("pronephric"))
WORDS = {"total": 3, "results": [{"phenotypeStatement": "pronephric duct absent, abnormal", "pubmedPubModIDs": ["PMID:1"]},
                                 {"phenotypeStatement": "heart size reduction, abnormal", "pubmedPubModIDs": ["PMID:2"]},
                                 {"phenotypeStatement": "cardiac conduction decreased, abnormal", "pubmedPubModIDs": ["PMID:3"]}]}
res_w, _ = run(WORDS, anatomy="duct")
check("corrector: respaldo cliente por PREFIJO DE PALABRA — 'duct' casa 'pronephric duct' y NO 'reduction' ni 'conduction'",
      res_w["data"]["n_matched"] == 1 and res_w["data"]["phenotypes"][0]["statement"].startswith("pronephric duct"),
      f"matched={[p['statement'] for p in res_w['data']['phenotypes']]}")

# ---- 6. timeout propagado a las DOS llamadas; presupuesto agotado no toca la red ----------------------------
res_t, net_t = run(NEW, timeout=7)
check("timeout=7 llega a resolve_curie Y a phenotypes (2 llamadas, ambas con 7)",
      res_t["status"] == "success" and [t for _, t in net_t.calls] == [7, 7], f"calls={net_t.calls}")
res_t2, net_t2 = run(NEW, timeout=7, anatomy="pronephr", anatomy_terms=["glomer"], server_filter=True)
check("timeout=7 llega a las TRES llamadas cuando hay dos raices con server_filter (resolve + 1 GET por raiz)",
      [t for _, t in net_t2.calls] == [7, 7, 7], f"calls={[t for _, t in net_t2.calls]}")
res_d, net_d = run(NEW)
check(f"sin timeout explicito: default declarado DEFAULT_TIMEOUT_S={zfin.DEFAULT_TIMEOUT_S} en ambas llamadas",
      [t for _, t in net_d.calls] == [zfin.DEFAULT_TIMEOUT_S] * 2)
res_z, net_z = run(NEW, timeout=0)
check("timeout<=0 (presupuesto agotado): status 'error' declarado y CERO llamadas de red",
      res_z["status"] == "error" and "BudgetExhausted" in res_z["error"] and net_z.calls == [],
      f"err={res_z.get('error')}")

# ---- 7. errores: la fuente que falla deja 'error', nunca un success vacio ----------------------------------
import urllib.error  # noqa: E402
res_e, _ = run(NEW, raise_on_phenotypes=urllib.error.HTTPError("u", 503, "Service Unavailable", {}, None))
check("HTTP 503 en phenotypes -> status 'error' con el tipo declarado (no un success con phenotypes=[])",
      res_e["status"] == "error" and res_e["error"].startswith("HTTPError") and "data" not in res_e, res_e.get("error"))
res_u, _ = run(NEW, autocomplete={"results": []})
check("simbolo sin gen resuelto -> status 'error' explicito",
      res_u["status"] == "error" and "no ZFIN zebrafish gene resolved" in res_u["error"])

# ---- 8. la firma vieja sigue funcionando (compat con answer_pipeline._search_zfin) -------------------------
zfin._get = FakeNet(NEW)
res_compat = zfin.query_zfin("wt1a", anatomy=None, limit=12)
check("firma vieja query_zfin(symbol, anatomy=, limit=) sigue valida; campos viejos presentes",
      res_compat["status"] == "success" and len(res_compat["data"]["phenotypes"]) == 12
      and all(k in res_compat["data"] for k in ("symbol", "zfin_curie", "taxon", "n_phenotypes_total", "n_matched",
                                                 "anatomy_filter", "phenotypes"))
      and all(set(p) >= {"statement", "references"} for p in res_compat["data"]["phenotypes"]))

n_pass = sum(CHECKS)
print(f"\n{n_pass}/{len(CHECKS)} PASS")
sys.exit(0 if n_pass == len(CHECKS) else 1)

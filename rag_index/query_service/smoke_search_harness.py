"""smoke_search_harness.py — gate offline del HARNESS de búsqueda de la Ruta B (ADR-0080, rebanada C2).

Cubre lib/search_harness.py y el cableado search_plan= de lib/answer_pipeline.py:
  * SEARCH_DISPATCH declarado (15 familias, llaves fijas, gate/label/inputs en sus dominios).
  * build_search_plan: familias default vs directivas vs env (WITT_SEARCH_DEFAULT_FAMILIES); 'directive-only'
    excluida sin directiva y DECLARADA; familia desconocida declarada; env inválida -> default declarado;
    queries por familia (search_queries para literatura/ZFIN; texto libre EN desde pass1 o símbolos+anatomía).
  * run_round con tools FALSAS inyectadas: success / no-match / error (contadores null) / módulo ausente ->
    tool-unavailable declarado; fuente LENTA que agota el presupuesto de ronda -> la siguiente 'skipped-budget'
    SIN llamar al tool; dedup contra evidence_ids ya presentes y dentro de la ronda; etiquetas
    'predictive' / 'inferred-by-orthology'; identificador derivado declarado; timeout= solo si la firma lo acepta;
    hook on_source por familia; payloads de evento sin ledgers anidados.
  * Familias legadas (europepmc / pubmed / zfin) por el harness con la red parcheada: ledger de hoy conservado.
  * path_b_bundle(search_plan=) y retrieve(search_plan=): eventos search.plan / search.source / search.round en
    orden, search_ledger congelable, ledgers legados + selection, dos rondas solo si la primera no trajo nada
    (cap), n_papers <= 0 -> literatura 'not-requested', y sin plan NINGÚN evento search.* (comportamiento actual).

100% offline: cero red (fetch_paper/pubmed/zfin parcheados; tools Layer 0 inyectadas), cero modelo, cero DB.
Exit 0 = todo PASS.

Corre:  python rag_index/query_service/smoke_search_harness.py
"""
import os
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# máscara offline (nada de esto toca red ni modelo; la máscara evita que el import lea .secrets)
os.environ.setdefault("NEO4J_URI", "")
os.environ.setdefault("RAG_BACKEND", "sparse")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("ANTHROPIC_API_KEY", "")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
from lib import search_harness as sh  # noqa: E402
from lib import answer_pipeline as ap  # noqa: E402
from lib import fetch_paper  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


def _env(**kw):
    """Fija/limpia env vars y devuelve lo anterior para restaurar."""
    old = {k: os.environ.get(k) for k in kw}
    for k, v in kw.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    return old


def _restore(old):
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# ---- tools falsas (misma interfaz que las Layer 0 reales: {status, query_sent, elapsed_s, cache_hit, data|error}) ----
def fake_ok(symbol, timeout=None):
    return {"status": "success", "query_sent": f"https://fake/{symbol}", "elapsed_s": 0.01, "cache_hit": True,
            "data": {"items": [{"evidence_id": f"FAKE:{symbol}:1", "statement": f"{symbol} item one", "url": "https://fake/1"},
                               {"id": f"FAKE:{symbol}:2", "title": f"{symbol} item two", "abstract": "an abstract"}],
                     "identifier_provenance": "fake-api-payload"}}


def fake_nomatch(symbol, timeout=None):
    return {"status": "no-match", "query_sent": f"https://fake/{symbol}", "elapsed_s": 0.01, "cache_hit": False,
            "data": {"items": []}}


def fake_error(symbol, timeout=None):
    return {"status": "error", "query_sent": None, "elapsed_s": 0.01, "error": "URLError: <urlopen error timed out>"}


def fake_raises(symbol, timeout=None):
    raise RuntimeError("boom")


def fake_no_ids(symbol):   # sin `timeout` en la firma: el harness NO debe pasárselo
    return {"status": "success", "query_sent": "q", "data": {"partners": [{"preferredName": "pax2a", "score": 0.9}]}}


def mk_slow(seconds):
    def slow(symbol, timeout=None):
        time.sleep(seconds)
        return fake_ok(symbol, timeout)
    return slow


def main():
    # ============ 1. SEARCH_DISPATCH declarado ============
    req = {"tool_module", "fn", "inputs", "budget_s", "host", "key_env", "evidence_kind", "gate", "label_provenance"}
    ok = all(req <= set(v.keys()) and v["gate"] in sh.GATES and v["label_provenance"] in sh.LABELS
             and v["inputs"] in sh.INPUT_MODES for v in sh.SEARCH_DISPATCH.values())
    expected = {"europepmc", "pubmed", "zfin", "alliance_orthologs", "zfin_expression", "ensembl_homology", "uniprot",
                "monarch", "reactome", "string", "geo", "unpaywall_crossref", "openalex", "web", "tooluniverse"}
    check("SEARCH_DISPATCH: 15 familias con llaves fijas; gate/label/inputs en sus dominios",
          ok and set(sh.SEARCH_DISPATCH) == expected, repr(sorted(set(sh.SEARCH_DISPATCH) ^ expected)))
    check("SEARCH_DISPATCH: reactome 'inferred-by-orthology', string 'predictive', web/tooluniverse sin tool con razón ADR",
          sh.SEARCH_DISPATCH["reactome"]["label_provenance"] == "inferred-by-orthology"
          and sh.SEARCH_DISPATCH["string"]["label_provenance"] == "predictive"
          and sh.SEARCH_DISPATCH["web"]["unavailable_reason"] == "tool-unavailable (ADR-0084)"
          and sh.SEARCH_DISPATCH["tooluniverse"]["unavailable_reason"] == "tool-unavailable (ADR-0085)")

    # ============ 2. build_search_plan ============
    old = _env(WITT_SEARCH_DEFAULT_FAMILIES=None, WITT_SEARCH_ROUNDS_CAP=None, WITT_SEARCH_ROUND_BUDGET_S=None)
    q = "Is wt1a required for zebrafish pronephros development?"
    plan = sh.build_search_plan(q, ["wt1a", "pax2a"], "wt1a pax2a pronephros zebrafish")
    check("plan default: familias == DEFAULT_FAMILIES, source 'default-families', cap 2 y budget 120 declarados como default-unset",
          plan["families"] == list(sh.DEFAULT_FAMILIES) and plan["families_source"] == "default-families"
          and plan["rounds_cap"] == 2 and plan["rounds_cap_source"] == "default-unset:WITT_SEARCH_ROUNDS_CAP"
          and plan["round_budget_s"] == 120.0 and plan["round_budget_s_source"].startswith("default-unset")
          and plan["plan_version"] == "1" and plan["directives"] == [] and plan["directives_state"] == "empty-until-ADR-0082",
          repr((plan["families"], plan["rounds_cap_source"])))
    check("plan default: ninguna familia directive-only entra; families_excluded vacío (nada que declarar)",
          all(sh.SEARCH_DISPATCH[f]["gate"] == "auto" for f in plan["families"]) and plan["families_excluded"] == [])
    check("plan: queries por familia — literatura y ZFIN de search_queries, free-query desde pass1_query_en, símbolos saneados",
          plan["queries"]["zfin"]["anatomy_filter"] == "pronephr" and plan["queries"]["zfin"]["symbols"] == ["wt1a", "pax2a"]
          and "TITLE:wt1a" in plan["queries"]["europepmc"]["query"] and "wt1a[tiab]" in plan["queries"]["pubmed"]["query"]
          and plan["queries"]["alliance_orthologs"] == {"inputs": "symbols", "symbols": ["wt1a", "pax2a"], "query_builder": "search_harness:v1:symbols"}
          and plan["question_en_source"] == "pass1_query_en", repr(plan["queries"]))
    plan_d = sh.build_search_plan(q, ["wt1a"], None, directives=[{"family": "reactome"}, {"family": "openalex"}, {"family": "nope"}])
    check("plan con directivas: familias de las directivas (directive-only incluidas), source 'directives', desconocida declarada",
          plan_d["families"] == ["reactome", "openalex"] and plan_d["families_source"] == "directives"
          and plan_d["families_excluded"] == [{"family": "nope", "reason": "unknown-family"}]
          and plan_d["directives_state"] == "provided" and len(plan_d["directives"]) == 3, repr(plan_d["families_excluded"]))
    check("plan sin pass1_query_en: free-query = símbolos + anatomía + 'zebrafish' (determinista, fuente declarada)",
          plan_d["queries"]["openalex"] == {"inputs": "free-query", "query": "wt1a pronephros pronephric zebrafish",
                                            "query_source": "search_harness:v1:symbols+anatomy"}
          and plan_d["question_en_source"] is None, repr(plan_d["queries"]["openalex"]))
    _restore(old)
    old = _env(WITT_SEARCH_DEFAULT_FAMILIES="zfin, uniprot,zzz", WITT_SEARCH_ROUNDS_CAP="abc", WITT_SEARCH_ROUND_BUDGET_S="-4")
    plan_e = sh.build_search_plan(q, ["wt1a"], None)
    check("plan por env: WITT_SEARCH_DEFAULT_FAMILIES nombra una directive-only (corre: es la directiva del operador), "
          "desconocida excluida; cap/budget inválidos -> default 'default-invalid-env'",
          plan_e["families"] == ["zfin", "uniprot"] and plan_e["families_default_source"] == "env:WITT_SEARCH_DEFAULT_FAMILIES"
          and plan_e["families_excluded"] == [{"family": "zzz", "reason": "unknown-family"}]
          and plan_e["rounds_cap"] == 2 and plan_e["rounds_cap_source"] == "default-invalid-env:WITT_SEARCH_ROUNDS_CAP"
          and plan_e["round_budget_s"] == 120.0 and plan_e["round_budget_s_source"] == "default-invalid-env:WITT_SEARCH_ROUND_BUDGET_S",
          repr((plan_e["families"], plan_e["families_excluded"], plan_e["rounds_cap_source"])))
    plan_c = sh.build_search_plan(q, [], None, families=["string", "web"])
    check("plan del llamador (families=): source 'caller'; sin símbolos ni EN los símbolos quedan [] y la literatura None",
          plan_c["families"] == ["string", "web"] and plan_c["families_source"] == "caller" and plan_c["symbols"] == []
          and plan_c["query_builder"]["europepmc"]["query"] is None)
    _restore(old)
    check("plan_event_payload: sin query_builder completo, con n_directives y state 'built' (corrector: la forma es UNA)",
          "query_builder" not in sh.plan_event_payload(plan) and sh.plan_event_payload(plan_d)["n_directives"] == 3
          and sh.plan_event_payload(plan)["state"] == "built")
    check("should_run_next_round: (1,0,2) True · (1,3,2) False · (2,0,2) False (cap) · (1,0,1) False · "
          "(1,0,2,inputs_changed=False) False (corrector: sin insumos nuevos no se re-ejecuta)",
          sh.should_run_next_round(1, 0, 2) and not sh.should_run_next_round(1, 3, 2)
          and not sh.should_run_next_round(2, 0, 2) and not sh.should_run_next_round(1, 0, 1)
          and not sh.should_run_next_round(1, 0, 2, False) and sh.should_run_next_round(1, 0, 2, True))
    check("resolve_default_families (público, corrector): mismo saneo que el plan — lista + fuente",
          sh.resolve_default_families() == sh._env_families_src())

    # ============ 3. run_round con tools falsas ============
    old = _env(WITT_SEARCH_DEFAULT_FAMILIES=None)
    fams = ["alliance_orthologs", "uniprot", "reactome", "string", "monarch", "web"]
    plan_r = sh.build_search_plan(q, ["wt1a"], None, families=fams)
    tools = {"alliance_orthologs": fake_ok, "uniprot": fake_nomatch, "reactome": fake_error, "string": fake_no_ids}
    sh._TOOL_CACHE["monarch"] = (None, None, "monarch_associations.py not found (simulated absent module)")
    seen_rows = []
    rd = sh.run_round(plan_r, 1, 30.0, on_source=seen_rows.append, tools=tools)
    by = {s["family"]: s for s in rd["sources"]}
    check("ronda: success n_found=2 n_new=2 cache_hit True · no-match 0/0 · error -> n_found/n_new null + error declarado",
          by["alliance_orthologs"]["status"] == "success" and by["alliance_orthologs"]["n_found"] == 2
          and by["alliance_orthologs"]["n_new"] == 2 and by["alliance_orthologs"]["cache_hit"] is True
          and by["uniprot"]["status"] == "no-match" and by["uniprot"]["n_found"] == 0 and by["uniprot"]["n_new"] == 0
          and by["reactome"]["status"] == "error" and by["reactome"]["n_found"] is None and by["reactome"]["n_new"] is None
          and "URLError" in by["reactome"]["error"], repr({k: (v["status"], v["n_found"], v["n_new"]) for k, v in by.items()}))
    check("ronda: módulo ausente -> 'tool-unavailable' con el detalle de qué faltó; web -> 'tool-unavailable (ADR-0084)'",
          by["monarch"]["status"] == "tool-unavailable" and "not found" in by["monarch"]["detail"]
          and by["web"]["status"] == "tool-unavailable" and by["web"]["detail"] == "tool-unavailable (ADR-0084)")
    check("ronda: totales n_new_total/n_found_total suman SOLO las fuentes que corrieron; sources en orden del plan; round=k",
          rd["n_new_total"] == 3 and rd["n_found_total"] == 3 and [s["family"] for s in rd["sources"]] == fams
          and all(s["round"] == 1 for s in rd["sources"]) and rd["round"] == 1)
    it_by = {i["evidence_id"]: i for i in rd["items"]}
    check("ítems normalizados: evidence_id del tool con su identifier_provenance; kind/source_family/label/url/statement",
          it_by["FAKE:wt1a:1"]["identifier_provenance"] == "fake-api-payload" and it_by["FAKE:wt1a:1"]["kind"] == "ortholog"
          and it_by["FAKE:wt1a:1"]["source_family"] == "alliance_orthologs" and it_by["FAKE:wt1a:1"]["label"] is None
          and it_by["FAKE:wt1a:1"]["url"] == "https://fake/1" and it_by["FAKE:wt1a:1"]["statement"] == "wt1a item one"
          and it_by["FAKE:wt1a:2"]["title"] == "wt1a item two" and it_by["FAKE:wt1a:2"]["abstract"] == "an abstract"
          and it_by["FAKE:wt1a:1"]["source"] == "alliance_orthologs" and it_by["FAKE:wt1a:1"]["fetched"]["found"] is True)
    derived = [i for i in rd["items"] if i["source_family"] == "string"]
    check("ítem sin identificador externo: id DERIVADO '<family>:sha256:<16>' + provenance 'derived:sha256-of-statement' + gap_flag; "
          "label 'predictive' de la familia; list_key 'partners' declarada",
          len(derived) == 1 and derived[0]["evidence_id"].startswith("string:sha256:") and len(derived[0]["evidence_id"]) == len("string:sha256:") + 16
          and derived[0]["identifier_provenance"] == "derived:sha256-of-statement" and derived[0]["gap_flags"] == ["no-external-identifier"]
          and derived[0]["label"] == "predictive" and by["string"]["calls"][0]["list_key"] == "partners", repr(derived[:1]))
    check("timeout= viaja al tool SOLO si su firma lo acepta (timeout_s_scope declarado en la llamada)",
          by["alliance_orthologs"]["calls"][0]["timeout_s_scope"] == "per-call" and by["alliance_orthologs"]["calls"][0]["timeout_s"] > 0
          and by["string"]["calls"][0]["timeout_s_scope"] == "not-accepted-by-tool")
    check("hook on_source: una fila por familia, en orden; source_event_payload sin 'ledger' ni 'calls'",
          [r["family"] for r in seen_rows] == fams
          and all("ledger" not in sh.source_event_payload(r) and "calls" not in sh.source_event_payload(r) for r in seen_rows)
          and sh.source_event_payload(by["reactome"])["error"].startswith("URLError"))
    check("round_event_payload: sin items; sources resumidas; n_duplicates",
          "items" not in sh.round_event_payload(rd) and len(sh.round_event_payload(rd)["sources"]) == len(fams)
          and sh.round_event_payload(rd)["n_duplicates"] == 0)
    # tool que LANZA -> error declarado, la ronda sigue
    rd_x = sh.run_round(plan_r, 1, 30.0, tools={"alliance_orthologs": fake_raises, "uniprot": fake_ok})
    bx = {s["family"]: s for s in rd_x["sources"]}
    check("tool que lanza: fila 'error' con RuntimeError declarado y la siguiente familia corre (§6 no-hang)",
          bx["alliance_orthologs"]["status"] == "error" and "RuntimeError: boom" in bx["alliance_orthologs"]["error"]
          and bx["uniprot"]["status"] == "success", repr(bx["alliance_orthologs"].get("error")))

    # ---- dedup contra lo ya presente y dentro de la ronda ----
    plan_dd = sh.build_search_plan(q, ["wt1a"], None, families=["alliance_orthologs", "uniprot"])
    rd_dd = sh.run_round(plan_dd, 1, 30.0, existing_ids={"FAKE:wt1a:1", "CORPUS-2026-0003#c000"},
                         tools={"alliance_orthologs": fake_ok, "uniprot": fake_ok})
    check("dedup: el id ya presente NO entra (duplicates 'existing'); el mismo id de dos familias entra una vez ('this-round'); n_new lo refleja",
          [i["evidence_id"] for i in rd_dd["items"]] == ["FAKE:wt1a:2"]
          and rd_dd["duplicates"] == [{"evidence_id": "FAKE:wt1a:1", "source_family": "alliance_orthologs", "of": "existing"},
                                      {"evidence_id": "FAKE:wt1a:1", "source_family": "uniprot", "of": "existing"},
                                      {"evidence_id": "FAKE:wt1a:2", "source_family": "uniprot", "of": "this-round"}]
          and [s["n_new"] for s in rd_dd["sources"]] == [1, 0] and [s["n_found"] for s in rd_dd["sources"]] == [2, 2]
          and rd_dd["n_new_total"] == 1, repr(rd_dd["duplicates"]))

    # ---- presupuesto de ronda: fuente lenta -> la siguiente skipped-budget SIN llamar al tool ----
    called = []

    def spy(symbol, timeout=None):
        called.append(symbol)
        return fake_ok(symbol, timeout)
    plan_b = sh.build_search_plan(q, ["wt1a"], None, families=["alliance_orthologs", "uniprot", "reactome"])
    called.clear()
    rd_b = sh.run_round(plan_b, 1, 0.8, tools={"alliance_orthologs": mk_slow(0.9), "uniprot": spy, "reactome": spy})
    bb = {s["family"]: s for s in rd_b["sources"]}
    check("presupuesto de RONDA: la fuente lenta agota el reloj (over_budget declarado); las siguientes quedan 'skipped-budget' "
          "con detalle y contadores null, y su tool NO se llama",
          bb["alliance_orthologs"]["status"] == "success" and bb["alliance_orthologs"]["over_budget"] is True
          and bb["uniprot"]["status"] == "skipped-budget" and bb["reactome"]["status"] == "skipped-budget"
          and "round budget" in bb["uniprot"]["detail"] and bb["uniprot"]["n_found"] is None and bb["uniprot"]["n_new"] is None
          and called == [] and rd_b["elapsed_s"] >= 0.8, repr((called, {k: v["status"] for k, v in bb.items()})))
    check("reparto del presupuesto: budget_s por familia = min(budget de la familia, restante / familias_restantes)",
          abs(bb["alliance_orthologs"]["budget_s"] - round(min(30.0, 0.8 / 3), 3)) < 0.01, repr(bb["alliance_orthologs"]["budget_s"]))
    # presupuesto por LLAMADA dentro de una familia (varios símbolos): el segundo símbolo queda skipped-budget
    plan_m = sh.build_search_plan(q, ["wt1a", "pax2a", "osr1"], None, families=["alliance_orthologs"])
    rd_m = sh.run_round(plan_m, 1, 0.7, tools={"alliance_orthologs": mk_slow(0.75)})
    row_m = rd_m["sources"][0]
    check("dentro de la familia: llamada por símbolo; agotado el presupuesto las restantes son 'skipped-budget' (n_calls_skipped_budget) "
          "y la fila sigue 'success' con lo medido",
          row_m["status"] == "success" and row_m["n_calls"] == 3 and row_m["n_calls_skipped_budget"] == 2
          and [c["status"] for c in row_m["calls"]] == ["success", "skipped-budget", "skipped-budget"], repr([c["status"] for c in row_m["calls"]]))
    # sin símbolos -> not-requested (nada que buscar), sin llamar
    plan_ns = sh.build_search_plan(q, [], None, families=["alliance_orthologs"])
    called.clear()
    rd_ns = sh.run_round(plan_ns, 1, 30.0, tools={"alliance_orthologs": spy})
    check("sin símbolos: familia 'symbols' -> 'not-requested' con razón, el tool no se llama",
          rd_ns["sources"][0]["status"] == "not-requested" and rd_ns["sources"][0]["detail"] == "no symbols" and called == [])
    # dois: se alimentan de los ítems de la misma ronda (search_rec.doi) — sin DOIs -> not-requested
    plan_doi = sh.build_search_plan(q, ["wt1a"], None, families=["unpaywall_crossref"])
    rd_doi = sh.run_round(plan_doi, 1, 30.0, tools={"unpaywall_crossref": spy})
    check("familia 'dois' sin DOIs en la ronda -> 'not-requested' declarado (inputs_mode 'dois')",
          rd_doi["sources"][0]["status"] == "not-requested" and rd_doi["sources"][0]["inputs_mode"] == "dois")
    # monarch toma CURIE: sin curies resueltas en la ronda -> not-requested; con una curie de ZFIN -> se llama con ella
    plan_mo = sh.build_search_plan(q, ["wt1a"], None, families=["monarch"])
    called.clear()
    rd_mo0 = sh.run_round(plan_mo, 1, 30.0, tools={"monarch": spy})
    rd_mo1 = sh.run_round(plan_mo, 1, 30.0, tools={"monarch": spy}, ctx={"curies": ["ZFIN:ZDB-GENE-980526-558"]})
    check("familia 'zfin-curies' (monarch): sin curie resuelta -> 'not-requested' con razón y sin llamar; con la curie de ZFIN en ctx "
          "se llama con la CURIE (jamás el símbolo)",
          rd_mo0["sources"][0]["status"] == "not-requested" and "curie" in rd_mo0["sources"][0]["detail"]
          and rd_mo1["sources"][0]["status"] == "success" and called == ["ZFIN:ZDB-GENE-980526-558"], repr(called))
    check("SEARCH_DISPATCH casa con los módulos entregados por C3–C5 (fn resuelta == declarada) para las 10 tools Layer 0 presentes",
          all(sh._load_tool(f)[1] == sh.SEARCH_DISPATCH[f]["fn"] for f in
              ("alliance_orthologs", "zfin_expression", "ensembl_homology", "uniprot", "monarch", "reactome", "string",
               "geo", "unpaywall_crossref", "openalex") if sh._load_tool(f)[0] is not None),
          repr({f: sh._load_tool(f)[1:] for f in ("monarch", "geo", "unpaywall_crossref")}))
    check("statement legible para ortólogos y expresión (formas fijadas por ADR-0080 D); el genérico declara el JSON compacto",
          sh.normalize_item("alliance_orthologs", {"species": "Homo sapiens", "symbol": "WT1", "id": "HGNC:12796", "stringency": "stringent"},
                            input_value="wt1a")["statement"] == "wt1a ortholog: Homo sapiens WT1 (HGNC:12796; stringency stringent)"
          and sh.normalize_item("zfin_expression", {"gene": "wt1a", "anatomy": "pronephric duct", "stage": "Prim-5", "assay": "mRNA in situ",
                                                    "pub_id": "ZFIN:ZDB-PUB-1"})["statement"]
          == "wt1a expressed in pronephric duct at Prim-5 (mRNA in situ) [ZFIN:ZDB-PUB-1]")
    sh._TOOL_CACHE.pop("monarch", None)
    _restore(old)

    # ============ 4. familias legadas por el harness (red parcheada) ============
    _epmc_real, _fetch_real, _cache_zfin_real = fetch_paper.search_europepmc_ledger, fetch_paper.fetch_external, ap._cache_zfin

    def fake_epmc(query, n=5, sort=None, synonym=True):
        return ([{"epmc_id": "1", "source": "MED", "pmid": "111", "pmcid": "PMC111", "doi": "10.1/aaa", "title": "EPMC paper",
                  "year": "2020", "journal": "J", "is_oa": True, "abstract": "wt1a pronephros abstract", "cited_by": 3}],
                {"source": "europepmc", "status": "success", "query_sent": query, "n_found": 1, "n_returned": 1,
                 "elapsed_s": 0.01, "contact": "unset"})

    def fake_pubmed(query, retmax=20):
        return {"status": "success", "ncbi_identity": "missing", "throttle": {}, "retries_429": 0,
                "data": {"query_sent": query, "retmax_sent": retmax, "n_found_total": 2,
                         "records": [{"pmid": "111", "title": "dup of epmc", "year": "2020", "journal": "J"},
                                     {"pmid": "222", "title": "PubMed only", "year": "2021", "journal": "K"}]}}

    def fake_zfin(symbol, anatomy=None, limit=50, anatomy_terms=None, server_filter=False, timeout=30):
        return {"status": "success", "data": {"zfin_curie": f"ZFIN:ZDB-GENE-{symbol}", "taxon": "NCBITaxon:7955",
                                              "n_phenotypes_total": 3, "n_matched": 1, "references_schema": "pubmedPublications",
                                              "phenotypes": [{"statement": "pronephric duct absent", "references": ["PMID:333"],
                                                              "references_schema": "pubmedPublications", "n_references_total": 1,
                                                              "references_truncated": False}]}}
    fetch_paper.search_europepmc_ledger = fake_epmc
    fetch_paper.fetch_external = lambda ident, want_full_text=True: {"found": False, "note": "offline stub (smoke)"}
    ap._cache_zfin = lambda s, r: []
    ap._WS_CACHE[("pubmed_literature.py", "query_pubmed")] = fake_pubmed
    ap._WS_CACHE[("zfin_zebrafish.py", "query_zfin")] = fake_zfin
    try:
        old = _env(WITT_SEARCH_DEFAULT_FAMILIES=None, WITT_SEARCH_ROUNDS_CAP=None, WITT_SEARCH_ROUND_BUDGET_S=None)
        plan_l = sh.build_search_plan(q, ["wt1a"], "wt1a pronephros", families=["europepmc", "pubmed", "zfin"])
        seen_pm = {}
        rd_l = sh.run_round(plan_l, 1, 30.0, ctx={"retmax": 20, "n_papers": 5, "literature_requested": True, "pubmed_seen": seen_pm})
        bl = {s["family"]: s for s in rd_l["sources"]}
        check("legadas: europepmc/pubmed/zfin corren por sus funciones actuales; la fila conserva el ledger de hoy ('ledger') "
              "y los ítems son 'literature-candidate' / 'phenotype'",
              bl["europepmc"]["status"] == "success" and bl["europepmc"]["ledger"]["status"] == "success" and bl["europepmc"]["n_found"] == 1
              and bl["pubmed"]["status"] == "success" and bl["pubmed"]["ledger"]["n_new"] == 1
              and bl["zfin"]["status"] == "success" and isinstance(bl["zfin"]["ledger"], list) and bl["zfin"]["ledger"][0]["symbol"] == "wt1a"
              and {i["kind"] for i in rd_l["items"]} == {"literature-candidate", "phenotype"}
              and any(i["evidence_id"] == "ZFIN:ZDB-GENE-wt1a" and i["identifier_provenance"] == "alliance-genome-api-live" for i in rd_l["items"]),
              repr({k: v["status"] for k, v in bl.items()}))
        check("legadas: PMID:111 lo declara el ledger de PubMed (duplicates_of_europepmc, semantica de hoy) porque la ronda le hace "
              "visibles los candidatos ya admitidos; el dedup del harness no lo duplica otra vez",
              bl["pubmed"]["ledger"]["duplicates_of_europepmc"] == ["PMID:111"] and bl["pubmed"]["n_new"] == 1
              and not any(d["evidence_id"] == "PMID:111" for d in rd_l["duplicates"])
              and [i["evidence_id"] for i in rd_l["items"] if i["kind"] == "literature-candidate"] == ["PMID:111", "PMID:222"])

        # ---- path_b_bundle(search_plan=) ----
        events = []
        plan_pb = sh.build_search_plan(q, ["wt1a"], "wt1a pronephros",
                                       families=["europepmc", "pubmed", "zfin", "alliance_orthologs", "web"])
        sh._TOOL_CACHE["alliance_orthologs"] = (fake_ok, "injected", None)
        blk = ap.path_b_bundle(q, entities=["wt1a"], triggered_by=["motivo"], search_plan=plan_pb,
                               on_stage=lambda n, p: events.append((n, p)), existing_ids=["CORPUS-2026-0003#c000"])
        names = [n for n, _ in events]
        check("path_b_bundle(search_plan=): eventos search.plan -> search.source x familias -> search.round, en orden",
              names == ["search.plan"] + ["search.source"] * 5 + ["search.round"], repr(names))
        sl = blk["search_ledger"]
        check("bloque: search_ledger congelable {plan sin query_builder, rounds[] sin items, families_default, n_rounds 1, cap 2, "
              "round_budget_s, stop_reason 'found-new'}; sources_requested = familias del plan; search_plan_version '1'",
              sl["n_rounds"] == 1 and sl["cap"] == 2 and sl["round_budget_s"] == 120.0 and sl["stop_reason"] == "found-new"
              and "query_builder" not in sl["plan"] and all("items" not in rd for rd in sl["rounds"])
              and sl["families_default"] == list(sh.DEFAULT_FAMILIES) and sl["harness_version"] == "sh-1"
              and blk["sources_requested"] == plan_pb["families"] and blk["search_plan_version"] == "1"
              and blk["ledger_version"] == "2", repr({k: sl[k] for k in ("n_rounds", "cap", "stop_reason")}))
        check("bloque: ledgers de hoy CONSERVADOS (europepmc_searched / pubmed_searched / zfin_searched / selection) con la misma forma",
              blk["europepmc_searched"]["status"] == "success" and blk["pubmed_searched"]["duplicates_of_europepmc"] == ["PMID:111"]
              and blk["zfin_searched"][0]["status"] == "success" and blk["selection"]["rule"] == ap.PATH_B_SELECTION_RULE
              and blk["selection"]["n_candidates"] == 2 and blk["selection"]["n_selected"] == 2
              and blk["selection"]["n_duplicates"] == 1 and blk["selection"]["duplicates"][0]["duplicate"] == "PMID:111"
              and blk["epmc_query"] == plan_pb["query_builder"]["europepmc"]["query"]
              and blk["query_source"].startswith("query-builder-v1:"), repr(blk["selection"]))
        srcs = [p["source"] for p in blk["papers"]]
        check("bloque: papers = literatura seleccionada (bajada por _paper_item, offline) + fenotipos ZFIN + ítems de las familias nuevas "
              "(kind/source_family/label); n_results_by_source por familia",
              srcs.count("europepmc") == 1 and srcs.count("pubmed") == 1 and srcs.count("zfin") == 1 and srcs.count("alliance_orthologs") == 2
              and all(p.get("text_provenance", "none") in ap.TEXT_PROVENANCES for p in blk["papers"])
              and blk["n_results_by_source"] == {"europepmc": 1, "pubmed": 1, "zfin": 1, "alliance_orthologs": 2}
              and next(p for p in blk["papers"] if p["source"] == "pubmed")["kind"] == "literature-candidate"
              and next(p for p in blk["papers"] if p["source"] == "alliance_orthologs")["kind"] == "ortholog",
              repr((srcs, blk["n_results_by_source"])))
        web_row = next(s for s in sl["rounds"][0]["sources"] if s["family"] == "web")
        check("bloque: web queda 'tool-unavailable (ADR-0084)' en la ronda congelada; la familia no aparece en n_results_by_source (no corrió)",
              web_row["status"] == "tool-unavailable" and "web" not in blk["n_results_by_source"])
        pl = ap.path_b_event_payload(blk, trigger="competence")
        check("stage.path_b: resumen del search_ledger (n_rounds, cap, stop_reason, families, rounds resumidas) sin ítems ni ledgers",
              pl["search_ledger"]["n_rounds"] == 1 and pl["search_ledger"]["stop_reason"] == "found-new"
              and pl["search_ledger"]["families"] == plan_pb["families"] and "items" not in pl["search_ledger"]["rounds"][0]
              and "ledger" not in pl["search_ledger"]["rounds"][0]["sources"][0] and pl["trigger"] == "competence")

        # ---- dos rondas solo si la primera no trajo nada; tope = cap ----
        plan_2 = sh.build_search_plan(q, ["wt1a"], None, families=["alliance_orthologs", "uniprot"])
        sh._TOOL_CACHE["alliance_orthologs"] = (fake_nomatch, "injected", None)
        sh._TOOL_CACHE["uniprot"] = (fake_error, "injected", None)
        ev2 = []
        blk2 = ap.path_b_bundle(q, entities=["wt1a"], search_plan=plan_2, on_stage=lambda n, p: ev2.append(n))
        sl2 = blk2["search_ledger"]
        check("nada nuevo en la ronda 1 y NINGÚN insumo cambió -> NO hay ronda 2 (corrector: 'nada se re-ejecuta'): stop_reason "
              "'no-new-inputs', n_rounds 1 < cap 2, un solo search.round, rounds[0].inputs_changed False; sin literatura en el "
              "plan no hay europepmc_searched/pubmed_searched (ausente != corrió)",
              sl2["n_rounds"] == 1 and sl2["stop_reason"] == "no-new-inputs" and sl2["rounds"][0]["inputs_changed"] is False
              and sl2["rounds"][0]["n_admitted"] == 0 and sl2["cap"] == 2
              and ev2.count("search.round") == 1 and sl2["n_new_total"] == 0 and blk2["papers"] == []
              and "europepmc_searched" not in blk2 and "pubmed_searched" not in blk2 and blk2["selection"]["n_candidates"] == 0,
              repr((sl2["n_rounds"], sl2["stop_reason"], ev2)))
        # ronda 2 SÍ ocurre cuando la ronda 1 resolvió un insumo nuevo para una familia que no lo tenía y no admitió nada:
        # alliance resuelve una curie ZFIN a nivel resultado (data.zfin_curie) pero sus ítems son duplicados de existing_ids
        _al_dup = {"species": "Homo sapiens", "symbol": "WT1", "id": "HGNC:12796", "stringency": "stringent",
                   "evidence_id": "alliance-ortholog:ZFIN:ZDB-GENE-980526-558->HGNC:12796", "identifier_provenance": "alliance-api-payload"}
        mon_calls = []

        def fake_al_curie(symbol, timeout=None, **kw):
            return {"status": "success", "query_sent": "al", "elapsed_s": 0.01, "cache_hit": True,
                    "data": {"zfin_curie": "ZFIN:ZDB-GENE-980526-558", "orthologs": [_al_dup]}}

        def fake_monarch(curie, timeout=None, **kw):
            mon_calls.append(curie)
            return {"status": "no-match", "query_sent": f"mon?{curie}", "elapsed_s": 0.01, "data": {"associations": []}}
        # orden del plan: monarch ANTES de alliance -> en la ronda 1 monarch no tiene curie (not-requested) y alliance la resuelve
        plan_3 = sh.build_search_plan(q, ["wt1a"], None, families=["monarch", "alliance_orthologs"])
        sh._TOOL_CACHE["alliance_orthologs"] = (fake_al_curie, "injected", None)
        sh._TOOL_CACHE["monarch"] = (fake_monarch, "injected", None)
        ev3 = []
        blk3 = ap.path_b_bundle(q, entities=["wt1a"], search_plan=plan_3, on_stage=lambda n, p: ev3.append(n),
                                existing_ids=[_al_dup["evidence_id"]])
        sl3 = blk3["search_ledger"]
        st3 = [{s["family"]: s["status"] for s in r["sources"]} for r in sl3["rounds"]]
        al_r2 = next(s for s in sl3["rounds"][1]["sources"] if s["family"] == "alliance_orthologs")
        check("ronda 2 SOLO para las familias con insumos NUEVOS: la ronda 1 no admite nada (el ortólogo ya estaba en existing_ids) "
              "pero alliance resolvió la curie ZFIN (data.zfin_curie -> ítem.zfin_curie -> ctx.curies, cosechada aunque el ítem sea "
              "duplicado y sobreviviendo a la copia del ctx) -> families_with_new_inputs ['monarch'] -> ronda 2 (trigger "
              "'no-new-in-previous-round'): monarch corre UNA vez con la curie -> no-match; alliance NO se re-ejecuta (fila "
              "'skipped-cap' con detail 'same inputs as round 1 (not re-executed)', budget 0, n_not_reexecuted 1) -> stop 'rounds-cap'",
              sl3["n_rounds"] == 2 and sl3["rounds"][0]["inputs_changed"] is True
              and sl3["rounds"][0]["families_with_new_inputs"] == ["monarch"]
              and sl3["rounds"][1]["trigger"] == "no-new-in-previous-round"
              and st3[0] == {"monarch": "not-requested", "alliance_orthologs": "success"}
              and st3[1] == {"monarch": "no-match", "alliance_orthologs": "skipped-cap"}
              and al_r2["detail"] == "same inputs as round 1 (not re-executed)" and al_r2["budget_s"] == 0.0
              and sl3["rounds"][1]["n_not_reexecuted"] == 1
              and mon_calls == ["ZFIN:ZDB-GENE-980526-558"] and sl3["stop_reason"] == "rounds-cap",
              repr((sl3["n_rounds"], sl3["stop_reason"], mon_calls, st3)))
        # con alliance ANTES de monarch la curie llega en la MISMA ronda: monarch corre en la ronda 1 y no hay ronda 2
        mon_calls.clear()
        plan_4 = sh.build_search_plan(q, ["wt1a"], None, families=["alliance_orthologs", "monarch"])
        blk4 = ap.path_b_bundle(q, entities=["wt1a"], search_plan=plan_4, existing_ids=[_al_dup["evidence_id"]])
        sl4 = blk4["search_ledger"]
        check("insumo resuelto en la MISMA ronda (alliance antes de monarch): monarch corre en la ronda 1 con la curie -> nada nuevo, "
              "ningún insumo pendiente -> UNA ronda, stop 'no-new-inputs', monarch llamado exactamente una vez",
              sl4["n_rounds"] == 1 and sl4["stop_reason"] == "no-new-inputs" and mon_calls == ["ZFIN:ZDB-GENE-980526-558"]
              and {s["family"]: s["status"] for s in sl4["rounds"][0]["sources"]}["monarch"] == "no-match"
              and sl4["rounds"][0]["families_with_new_inputs"] == [],
              repr((sl4["n_rounds"], sl4["stop_reason"], mon_calls)))
        old_cap = _env(WITT_SEARCH_ROUNDS_CAP="1")
        plan_1 = sh.build_search_plan(q, ["wt1a"], None, families=["alliance_orthologs"])
        blk1 = ap.path_b_bundle(q, entities=["wt1a"], search_plan=plan_1)
        check("WITT_SEARCH_ROUNDS_CAP=1: una sola ronda aunque no haya nada nuevo (cap declarado en el plan y el ledger)",
              blk1["search_ledger"]["n_rounds"] == 1 and blk1["search_ledger"]["cap"] == 1
              and plan_1["rounds_cap_source"] == "env:WITT_SEARCH_ROUNDS_CAP")
        _restore(old_cap)

        # ---- n_papers <= 0 -> literatura not-requested, ZFIN sí corre ----
        plan_0 = sh.build_search_plan(q, ["wt1a"], None, families=["europepmc", "pubmed", "zfin"])
        blk0 = ap.path_b_bundle(q, entities=["wt1a"], n=0, search_plan=plan_0)
        check("n_papers=0 con plan: europepmc/pubmed 'not-requested' (ledger de hoy, contadores null), ZFIN corre igual",
              blk0["europepmc_searched"]["status"] == "not-requested" and blk0["europepmc_searched"]["n_returned"] is None
              and blk0["pubmed_searched"]["status"] == "not-requested" and blk0["pubmed_searched"]["n_new"] is None
              and blk0["zfin_searched"][0]["status"] == "success" and blk0["n_results_by_source"]["europepmc"] == 0
              and blk0["selection"]["n_selected"] == 0, repr(blk0["europepmc_searched"]))

        # ---- retrieve(search_plan=) con Ruta A insuficiente (stubs) ----
        _path_a_real, _check_real = ap.path_a, ap.check_entities
        ap.path_a = lambda question, k=6, max_chars=None: {
            "n_hits": 1, "top_score": 0.5, "has_literature_chunks": False,
            "retrieval": {"mode": "semantic", "raw_marker": None, "n_hits": 1, "k_requested": k},
            "text_cap_chars": 2400, "text_cap_source": "caller",
            "hits": [{"doc_id": "CORPUS-2026-0003#c000", "type": "catalog", "score": 0.5, "text": "x"}]}
        ap.check_entities = lambda ents: {e: {"in_di": False, "ensdarg": None} for e in (ents or [])}
        try:
            sh._TOOL_CACHE["alliance_orthologs"] = (fake_ok, "injected", None)
            plan_rt = sh.build_search_plan(q, ["wt1a"], None, families=["alliance_orthologs"])
            st = []
            b = ap.retrieve(q, entities=["wt1a"], search_plan=plan_rt, on_stage=lambda n, p: st.append(n))
            check("retrieve(search_plan=): Ruta A insuficiente -> Ruta B por el harness; eventos path_a, check_entities, "
                  "assess_sufficiency, search.plan, search.source, search.round, path_b, decision_state",
                  st == ["path_a", "check_entities", "assess_sufficiency", "search.plan", "search.source", "search.round",
                         "path_b", "decision_state"]
                  and b["path_b"]["search_ledger"]["n_rounds"] == 1 and b["decision_state"]["state"] == "FALLBACK_FETCHED"
                  and [p["evidence_id"] for p in b["path_b"]["papers"]] == ["FAKE:wt1a:1", "FAKE:wt1a:2"], repr(st))
            st2 = []
            ap.path_b = lambda question, n=None, **kw: []   # el seam de siempre: sin plan, la Ruta B de hoy
            try:
                b2 = ap.retrieve(q, entities=["wt1a"], on_stage=lambda n, p: st2.append(n))
            finally:
                ap.path_b = _path_b_module_real
            check("retrieve sin plan: NINGÚN evento search.* y el bloque path_b no lleva search_ledger (comportamiento actual)",
                  not any(n.startswith("search.") for n in st2) and "search_ledger" not in b2["path_b"]
                  and "search_plan_version" not in b2["path_b"], repr(st2))
        finally:
            ap.path_a, ap.check_entities = _path_a_real, _check_real
        _restore(old)
    finally:
        fetch_paper.search_europepmc_ledger, fetch_paper.fetch_external, ap._cache_zfin = _epmc_real, _fetch_real, _cache_zfin_real
        ap._WS_CACHE.pop(("pubmed_literature.py", "query_pubmed"), None)
        ap._WS_CACHE.pop(("zfin_zebrafish.py", "query_zfin"), None)
        for fam in ("alliance_orthologs", "uniprot", "monarch"):
            sh._TOOL_CACHE.pop(fam, None)

    n_pass, n_total = sum(CHECKS), len(CHECKS)
    print(f"\n{n_pass}/{n_total} PASS")
    return 0 if n_pass == n_total else 1


_path_b_module_real = ap.path_b

if __name__ == "__main__":
    sys.exit(main())

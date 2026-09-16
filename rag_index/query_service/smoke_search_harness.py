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
  * ADR-0082 (G.3) directivas del consejo (rebanada C3): UNIÓN — directivas [openalex, monarch, string] -> familias
    = 5 auto ∪ 3, families_source 'directives+default' (las 5 auto SIGUEN); openalex.query == query_en de la
    directiva con query_source 'council-directive:req-…' (la sustituida declarada); símbolos AÑADIDOS a zfin/string
    declarados (symbols_from_directives, saneados); familia desconocida -> 'unknown-family' con requirement_ids;
    web -> excluida 'unsatisfiable-by-harness (tool-unavailable (ADR-0084))'; directive_queries de europepmc = UNA
    llamada EXTRA dentro del presupuesto (el fake cuenta), 'skipped-budget' con presupuesto 0 sin llamar; filas e
    ítems con directive_requirement_ids (atribución por insumo, no por contagio); stage.search.source lo lleva;
    path_b_bundle conserva los campos de directiva en search_ledger.plan; SIN directivas el plan es byte-idéntico
    al de 9d90c01 (GOLDEN sha256 del plan sin cache_dir, capturado antes de la rebanada).
  * ADR-0084 (C)/(D) familia web como LOCALIZADOR (rebanada W3): fila REAL de SEARCH_DISPATCH (brave_web_search.py /
    locate / adapter 'web' / availability dinámica); bajo kill-switch u off derivado (sin BRAVE_API_KEY) el plan con la
    directiva web es BYTE-IDÉNTICO al golden grabado en 7d9ce15 (fixtures/golden_plan_web_directive_7d9ce15.json) con el
    literal EXACTO 'unsatisfiable-by-harness (tool-unavailable (ADR-0084))' (UNA verdad: sh.WEB_UNSATISFIABLE_LITERAL);
    con llave fake web entra PRIMERA en families con families_order_rule, query de la directiva (o WITT_WEB_TEST_QUERY /
    pass1_query_en por env — jamás la pregunta cruda); ronda con proveedor FALSO + fetch_paper._resolve_one FALSO →
    0 ítems con source 'web' (los candidatos son source 'europepmc' / source_family 'web' / 'web-located:<rule>' / url
    canónica / título de EPMC, sin title_web ni description), DOI → ctx.dois y curie → ctx.curies en la MISMA ronda
    (unpaywall/monarch spies), dedup (already-present / duplicate-in-response), not-found-in-europepmc, topes
    WITT_WEB_MAX_QUERIES / WITT_WEB_MAX_MATERIALIZE, cortacircuito auth, cuota que niega, fake que lanza, presupuesto,
    ctx append-only (id() intacto), hook on_web_locate sin URLs, source_event_payload aditivo, cero red.

100% offline: cero red (fetch_paper/pubmed/zfin parcheados; tools Layer 0 inyectadas), cero modelo, cero DB.
Exit 0 = todo PASS.

Corre:  python rag_index/query_service/smoke_search_harness.py
"""
import hashlib
import json
import os
import re
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

# ---- cero red: urlopen bloqueado y CONTADO durante TODO el smoke (ADR-0082 L.3; patrón smoke_models) ----------------
import urllib.request as _urlreq  # noqa: E402

_NET_CALLS = []
_urlopen_real = _urlreq.urlopen


def _urlopen_blocked(*a, **kw):
    # se registra QUIÉN llamó (primer frame fuera de urllib): el detalle del check nombra al culpable, no sólo cuenta
    import traceback as _tb
    frames = [f for f in _tb.extract_stack()[:-1] if "urllib" not in f.filename.replace("\\", "/")]
    who = f"{Path(frames[-1].filename).name}:{frames[-1].lineno}:{frames[-1].name}" if frames else "?"
    req = a[0] if a else kw.get("url")
    url = getattr(req, "full_url", None) or str(req)
    _NET_CALLS.append(f"{who} -> {url[:120]}")
    raise RuntimeError("network blocked by smoke_search_harness (offline gate)")


_urlreq.urlopen = _urlopen_blocked

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


def fake_free(query, timeout=None):
    """Tool 'free-query' falsa (openalex/geo): un ítem cuyo id depende de la QUERY — así se mide qué llamada lo trajo."""
    key = hashlib.sha256(query.encode("utf-8")).hexdigest()[:8]
    return {"status": "success", "query_sent": f"https://fake/free?q={query}", "elapsed_s": 0.01, "cache_hit": False,
            "data": {"records": [{"id": f"W:{key}", "title": f"paper for {query}", "url": f"https://fake/W:{key}"}]}}


def _plan_sha(plan):
    """sha256 del plan SIN cache_dir (ruta de la máquina) — canon json sort_keys; el GOLDEN se capturó @ 9d90c01."""
    body = {k: v for k, v in plan.items() if k != "cache_dir"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


# GOLDEN @ 9d90c01 (ADR-0080 + 0081; capturado 2026-09-15 ANTES de la rebanada C3 de ADR-0082, con las env
# WITT_SEARCH_* sin fijar): el plan SIN directivas debe seguir siendo estos bytes (kill-switch WITT_COUNCIL=0).
PLAN_GOLDEN_SHA = {
    ("wt1a,pax2a", "wt1a pax2a pronephros zebrafish"): "360fdda0c7f0cd3e53d1eab5e0bfb126a54fb55b37ecdf31cbf25175dd6aa5e6",
    ("wt1a", None): "878b10fc8b2ad41b46b64e00180500acc0a92f836147206163d58c1e758d9b10",
}

# Directivas del consejo con la forma C.6 (council.compile_directives) — lo que runs._build_search_plan pasará
DIRECTIVES_C6 = [
    {"requirement_id": "req-aaa", "family": "openalex", "query_en": "wt1a pronephros glomerulus podocyte",
     "entities": ["wt1a"], "symbols": ["wt1a"], "evidence_kind": "paper", "priority": "must",
     "requested_by": ["literature-monitor"], "refined_by_members": []},
    {"requirement_id": "req-bbb", "family": "monarch", "query_en": "wt1a phenotype associations",
     "entities": ["wt1a"], "symbols": ["wt1a"], "evidence_kind": "gene-phenotype-association", "priority": "should",
     "requested_by": ["marker-validator"], "refined_by_members": []},
    {"requirement_id": "req-ccc", "family": "string", "query_en": "", "entities": [], "symbols": ["Pax2a", "osr1", "wt1a"],
     "evidence_kind": "interaction", "priority": "should", "requested_by": ["cross-modality-integrator"], "refined_by_members": []},
    {"requirement_id": "req-ddd", "family": "europepmc", "query_en": "wt1a knockdown pronephric duct", "entities": [],
     "symbols": [], "evidence_kind": "paper", "priority": "must", "requested_by": ["literature-monitor"], "refined_by_members": []},
    {"requirement_id": "req-eee", "family": "zfin", "query_en": None, "entities": [], "symbols": ["osr1", "x"],
     "evidence_kind": "phenotype", "priority": "must", "requested_by": ["marker-validator"], "refined_by_members": []},
    {"requirement_id": "req-fff", "family": "web", "query_en": "wt1a review", "entities": [], "symbols": [],
     "evidence_kind": "web", "priority": "should", "requested_by": ["domain-knowledge-curator"], "refined_by_members": []},
    {"requirement_id": "req-ggg", "family": "nope", "query_en": "x", "entities": [], "symbols": [],
     "evidence_kind": "paper", "priority": "should", "requested_by": ["hypothesis-generator"], "refined_by_members": []},
    {"requirement_id": "req-hhh", "family": "openalex", "query_en": "second openalex query", "entities": [], "symbols": [],
     "evidence_kind": "paper", "priority": "should", "requested_by": ["hypothesis-generator"], "refined_by_members": []},
]


def main():
    # ============ 1. SEARCH_DISPATCH declarado ============
    req = {"tool_module", "fn", "inputs", "budget_s", "host", "key_env", "evidence_kind", "gate", "label_provenance"}
    ok = all(req <= set(v.keys()) and v["gate"] in sh.GATES and v["label_provenance"] in sh.LABELS
             and v["inputs"] in sh.INPUT_MODES for v in sh.SEARCH_DISPATCH.values())
    expected = {"europepmc", "pubmed", "zfin", "alliance_orthologs", "zfin_expression", "ensembl_homology", "uniprot",
                "monarch", "reactome", "string", "geo", "unpaywall_crossref", "openalex", "web", "tooluniverse"}
    check("SEARCH_DISPATCH: 15 familias con llaves fijas; gate/label/inputs en sus dominios",
          ok and set(sh.SEARCH_DISPATCH) == expected, repr(sorted(set(sh.SEARCH_DISPATCH) ^ expected)))
    web_spec = sh.SEARCH_DISPATCH["web"]
    check("SEARCH_DISPATCH: reactome 'inferred-by-orthology', string 'predictive'; tooluniverse sin tool con razón ADR-0085; web "
          "(ADR-0084 C.1) YA NO es estática: tool REAL brave_web_search.py / fn 'locate' / adapter 'web' / availability "
          "'web_locator.provider_state' / host y key_env declarados / budget_env WITT_WEB_BUDGET_S, y unavailable_reason "
          "byte-idéntico a 7d9ce15",
          sh.SEARCH_DISPATCH["reactome"]["label_provenance"] == "inferred-by-orthology"
          and sh.SEARCH_DISPATCH["string"]["label_provenance"] == "predictive"
          and web_spec["unavailable_reason"] == "tool-unavailable (ADR-0084)"
          and web_spec["tool_module"] == "brave_web_search.py" and web_spec["fn"] == "locate" and web_spec["adapter"] == "web"
          and web_spec["availability"] == "web_locator.provider_state" and web_spec["host"] == "api.search.brave.com"
          and web_spec["key_env"] == "BRAVE_API_KEY" and web_spec["budget_env"] == "WITT_WEB_BUDGET_S" and web_spec["budget_s"] == 30.0
          and web_spec["evidence_kind"] == "web" and web_spec["gate"] == "directive-only"
          and sh.SEARCH_DISPATCH["tooluniverse"]["fn"] is None and sh.SEARCH_DISPATCH["tooluniverse"]["adapter"] is None
          and sh.SEARCH_DISPATCH["tooluniverse"]["unavailable_reason"] == "tool-unavailable (ADR-0085)",
          repr(web_spec))

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
    check("GOLDEN 9d90c01: el plan SIN directivas es byte-idéntico al de ADR-0080/0081 (sha256 del plan sin cache_dir, "
          "dos insumos distintos) — kill-switch WITT_COUNCIL=0 → build_search_plan(directives=None) EXACTAMENTE como hoy (ADR-0082 L.2)",
          _plan_sha(plan) == PLAN_GOLDEN_SHA[("wt1a,pax2a", "wt1a pax2a pronephros zebrafish")]
          and _plan_sha(sh.build_search_plan(q, ["wt1a"], None)) == PLAN_GOLDEN_SHA[("wt1a", None)],
          repr((_plan_sha(plan), _plan_sha(sh.build_search_plan(q, ["wt1a"], None)))))
    # ADR-0082 (G.3): con directivas la semántica es de UNIÓN (antes REEMPLAZO: una directiva apagaba las 5 auto)
    plan_d = sh.build_search_plan(q, ["wt1a"], None, directives=[{"family": "reactome"}, {"family": "openalex"}, {"family": "nope"}])
    check("ADR-0082 (G.3) plan con directivas (forma vieja {family} sin requirement_id): UNIÓN — las 5 auto SIGUEN + reactome/openalex "
          "(directive-only ENTRAN por directiva), families_source 'directives+default', desconocida declarada con su id posicional "
          "'directive:2' (declarado, no inventado), directives_state 'provided', directives verbatim",
          plan_d["families"] == list(sh.DEFAULT_FAMILIES) + ["reactome", "openalex"] and plan_d["families_source"] == "directives+default"
          and plan_d["families_excluded"] == [{"family": "nope", "reason": "unknown-family", "requirement_ids": ["directive:2"]}]
          and plan_d["directives_state"] == "provided" and len(plan_d["directives"]) == 3
          and plan_d["families_from_directives"] == ["reactome", "openalex"] and plan_d["n_directives_excluded"] == 1
          and [r["state"] for r in plan_d["directives_applied"]] == ["applied", "applied", "excluded-unknown-family"],
          repr((plan_d["families"], plan_d["families_excluded"])))
    check("plan sin pass1_query_en y directiva SIN query_en: free-query = símbolos + anatomía + 'zebrafish' (la directiva no "
          "sustituye nada: entered_by 'directive', sin query_source de consejo)",
          plan_d["queries"]["openalex"]["query"] == "wt1a pronephros pronephric zebrafish"
          and plan_d["queries"]["openalex"]["query_source"] == "search_harness:v1:symbols+anatomy"
          and plan_d["queries"]["openalex"]["entered_by"] == "directive"
          and plan_d["queries"]["openalex"]["directive_requirement_ids"] == ["directive:1"]
          and "directive_queries" not in plan_d["queries"]["openalex"]
          and plan_d["question_en_source"] is None, repr(plan_d["queries"]["openalex"]))
    _restore(old)

    # ============ 2b. ADR-0082 (G.3): directivas del consejo con la forma C.6 ============
    old = _env(WITT_SEARCH_DEFAULT_FAMILIES=None, WITT_SEARCH_ROUNDS_CAP=None, WITT_SEARCH_ROUND_BUDGET_S=None)
    pdc = sh.build_search_plan(q, ["wt1a"], "wt1a pronephros", directives=DIRECTIVES_C6)
    qd = pdc["queries"]
    check("directivas C.6 [openalex, monarch, string, europepmc, zfin, web, nope, openalex]: familias = 5 auto ∪ [openalex, monarch, "
          "string] en el orden pedido; families_source 'directives+default' ∈ FAMILIES_SOURCES; families_from_directives las 3 "
          "directive-only; europepmc/zfin (default) NO se duplican",
          pdc["families"] == list(sh.DEFAULT_FAMILIES) + ["openalex", "monarch", "string"]
          and pdc["families_source"] == "directives+default" and pdc["families_source"] in sh.FAMILIES_SOURCES
          and pdc["families_from_directives"] == ["openalex", "monarch", "string"] and pdc["directives_state"] == "provided"
          and pdc["directives"] == DIRECTIVES_C6, repr(pdc["families"]))
    check("exclusiones con razón y requirement_ids: 'nope' → 'unknown-family'; 'web' bajo la máscara (BRAVE_API_KEY vacía, "
          "WITT_WEB_LOCATOR sin fijar ⇒ provider derivado off, ADR-0084 C.2 family_available False) → el literal EXACTO de 7d9ce15 "
          "'unsatisfiable-by-harness (tool-unavailable (ADR-0084))' (importado: sh.WEB_UNSATISFIABLE_LITERAL) — NO se despacha "
          "una llamada que nacería tool-unavailable; n_directives_excluded 2; ni web ni nope en families",
          sh.family_available("web")[0] is False
          and pdc["families_excluded"] == [
              {"family": "web", "reason": sh.WEB_UNSATISFIABLE_LITERAL, "requirement_ids": ["req-fff"]},
              {"family": "nope", "reason": "unknown-family", "requirement_ids": ["req-ggg"]}]
          and sh.WEB_UNSATISFIABLE_LITERAL == "unsatisfiable-by-harness (tool-unavailable (ADR-0084))"
          and pdc["n_directives_excluded"] == 2 and "web" not in pdc["families"] and "nope" not in pdc["families"]
          and "families_order_rule" not in pdc,
          repr(pdc["families_excluded"]))
    check("free-query (openalex): la query_en de la PRIMERA directiva sustituye a pass1_query_en — query_source "
          "'council-directive:req-aaa', la sustituida declarada en query_replaced; la segunda directiva de la misma familia es "
          "insumo EXTRA (directive_queries ×2; _inputs_for → 2 llamadas); directive_inputs mapea cada query a su id",
          qd["openalex"]["query"] == "wt1a pronephros glomerulus podocyte"
          and qd["openalex"]["query_source"] == "council-directive:req-aaa"
          and qd["openalex"]["query_replaced"] == {"query": "wt1a pronephros", "query_source": "pass1_query_en"}
          and qd["openalex"]["directive_requirement_ids"] == ["req-aaa", "req-hhh"] and qd["openalex"]["entered_by"] == "directive"
          and [d["requirement_id"] for d in qd["openalex"]["directive_queries"]] == ["req-aaa", "req-hhh"]
          and sh._inputs_for("openalex", sh.SEARCH_DISPATCH["openalex"], pdc, {})[0] == ["wt1a pronephros glomerulus podocyte", "second openalex query"]
          and qd["openalex"]["directive_inputs"] == {"wt1a pronephros glomerulus podocyte": ["req-aaa"], "second openalex query": ["req-hhh"]},
          repr(qd["openalex"]))
    check("symbols (string, directive-only): símbolos de la directiva AÑADIDOS con el MISMO saneo (Pax2a → pax2a), el ya presente "
          "(wt1a) no se duplica ni se atribuye; symbols_from_directives declarado; zfin (default) gana osr1 y descarta 'x' "
          "(symbols_from_directives_dropped); entered_by 'directive' vs 'default+directive'",
          qd["string"]["symbols"] == ["wt1a", "pax2a", "osr1"] and qd["string"]["symbols_from_directives"] == ["pax2a", "osr1"]
          and qd["string"]["directive_inputs"] == {"pax2a": ["req-ccc"], "osr1": ["req-ccc"]} and qd["string"]["entered_by"] == "directive"
          and qd["zfin"]["symbols"] == ["wt1a", "osr1"] and qd["zfin"]["symbols_from_directives"] == ["osr1"]
          and qd["zfin"]["symbols_from_directives_dropped"] == ["x"] and qd["zfin"]["entered_by"] == "default+directive"
          and qd["zfin"]["directive_inputs"] == {"osr1": ["req-eee"]} and qd["zfin"]["anatomy_filter"] == "pronephr",
          repr((qd["string"], qd["zfin"])))
    check("literatura (europepmc, default): la query del constructor SIGUE; la directiva va a directive_queries[] (UNA llamada "
          "EXTRA en la ronda); _inputs_for la ve como insumo (inputs_used / inputs_signature completos); pubmed (sin directiva) "
          "queda EXACTAMENTE como sin directivas",
          "TITLE:wt1a" in qd["europepmc"]["query"] and qd["europepmc"]["entered_by"] == "default+directive"
          and qd["europepmc"]["directive_queries"] == [{"requirement_id": "req-ddd", "query_en": "wt1a knockdown pronephric duct"}]
          and sh._inputs_for("europepmc", sh.SEARCH_DISPATCH["europepmc"], pdc, {})[0] == [qd["europepmc"]["query"], "wt1a knockdown pronephric duct"]
          and qd["pubmed"] == {"inputs": "literature-query", "query": qd["pubmed"]["query"], "query_builder": "search_queries:v1"}
          and "directive_requirement_ids" not in qd["pubmed"], repr(qd["europepmc"]))
    check("monarch (zfin-curies, directive-only): entra por la directiva (family-entry) — sus insumos siguen siendo las curies "
          "resueltas en la ronda (jamás un símbolo de memoria); directives_applied: una fila por directiva con state ∈ "
          "DIRECTIVE_PLAN_STATES y applied_as por insumo",
          qd["monarch"]["entered_by"] == "directive" and qd["monarch"]["directive_requirement_ids"] == ["req-bbb"]
          and qd["monarch"]["curies"] == "from-zfin-items-at-round-time" and "directive_inputs" not in qd["monarch"]
          and all(r["state"] in sh.DIRECTIVE_PLAN_STATES for r in pdc["directives_applied"])
          and {r["requirement_id"]: (r["state"], r["applied_as"]) for r in pdc["directives_applied"]} == {
              "req-aaa": ("applied", ["family-entry", "free-query"]), "req-bbb": ("applied", ["family-entry"]),
              "req-ccc": ("applied", ["family-entry", "symbol:pax2a", "symbol:osr1"]), "req-ddd": ("applied", ["literature-extra-query"]),
              "req-eee": ("applied", ["symbol:osr1"]), "req-fff": ("excluded-unsatisfiable", []), "req-ggg": ("excluded-unknown-family", []),
              "req-hhh": ("applied", ["family-entry", "free-query-extra"])},
          repr(pdc["directives_applied"]))
    check("plan_event_payload con directivas: families_source 'directives+default', n_directives 8, state 'built', queries con los "
          "campos de directiva (la Traza glosa 'lo pidió el consejo + las 5 de siempre'); inputs_signature incluye los insumos de "
          "las directivas (openalex 2 queries, string 3 símbolos)",
          sh.plan_event_payload(pdc)["families_source"] == "directives+default" and sh.plan_event_payload(pdc)["n_directives"] == 8
          and sh.plan_event_payload(pdc)["state"] == "built"
          and sh.plan_event_payload(pdc)["queries"]["openalex"]["query_source"] == "council-directive:req-aaa"
          and sh.inputs_signature(pdc, {})["openalex"] == ["free-query", ["wt1a pronephros glomerulus podocyte", "second openalex query"]]
          and sh.inputs_signature(pdc, {})["string"] == ["symbols", ["wt1a", "pax2a", "osr1"]])
    pcd = sh.build_search_plan(q, ["wt1a"], None, directives=DIRECTIVES_C6[:2], families=["openalex"])
    check("families= del llamador MANDA sobre las directivas ('caller'): openalex entra por el llamador y la directiva refina su "
          "query (entered_by 'caller+directive'); la directiva de monarch (no pedida por el llamador) queda "
          "'not-requested (caller families)' — declarada, no callada",
          pcd["families"] == ["openalex"] and pcd["families_source"] == "caller"
          and pcd["queries"]["openalex"]["entered_by"] == "caller+directive"
          and pcd["queries"]["openalex"]["query_source"] == "council-directive:req-aaa"
          and [(r["requirement_id"], r["state"]) for r in pcd["directives_applied"]] == [("req-aaa", "applied"), ("req-bbb", "not-requested (caller families)")],
          repr(pcd["directives_applied"]))
    # run_round con el plan de directivas: filas e ítems con directive_requirement_ids (atribución por INSUMO)
    plan_rd = sh.build_search_plan(q, ["wt1a"], "wt1a pronephros", families=None,
                                   directives=[d for d in DIRECTIVES_C6 if d["family"] in ("openalex", "string", "monarch")])
    plan_rd["families"] = ["openalex", "string", "monarch", "alliance_orthologs"]   # sólo Layer 0 (las legadas van en §4)
    rows_rd = []
    def fake_al(symbol, timeout=None):   # ids distintos de fake_ok: así el [] de alliance se MIDE (no queda vacuo por dedup)
        return {"status": "success", "query_sent": f"https://fake/al/{symbol}", "elapsed_s": 0.01,
                "data": {"orthologs": [{"id": f"AL:{symbol}", "statement": f"{symbol} ortholog"}]}}
    rd_d = sh.run_round(plan_rd, 1, 30.0, on_source=rows_rd.append, tools={"openalex": fake_free, "string": fake_ok, "alliance_orthologs": fake_al, "monarch": fake_ok})
    by_d = {s["family"]: s for s in rd_d["sources"]}
    it_d = {i["evidence_id"]: i for i in rd_d["items"]}
    w1 = "W:" + hashlib.sha256(b"wt1a pronephros glomerulus podocyte").hexdigest()[:8]
    w2 = "W:" + hashlib.sha256(b"second openalex query").hexdigest()[:8]
    check("run_round: TODA fila lleva directive_requirement_ids (openalex [aaa, hhh] · string [ccc] · monarch [bbb] aunque quede "
          "'not-requested' sin curie · alliance_orthologs [] = nadie la pidió); openalex hizo 2 llamadas (una por query de "
          "directiva) y cada llamada declara su id",
          by_d["openalex"]["directive_requirement_ids"] == ["req-aaa", "req-hhh"] and by_d["string"]["directive_requirement_ids"] == ["req-ccc"]
          and by_d["monarch"]["directive_requirement_ids"] == ["req-bbb"] and by_d["monarch"]["status"] == "not-requested"
          and by_d["alliance_orthologs"]["directive_requirement_ids"] == []
          and by_d["openalex"]["n_calls"] == 2 and [c["directive_requirement_ids"] for c in by_d["openalex"]["calls"]] == [["req-aaa"], ["req-hhh"]],
          repr({f: (s["status"], s["directive_requirement_ids"]) for f, s in by_d.items()}))
    check("ítems: atribución POR INSUMO, no por contagio — el paper de la 1ª query openalex lleva [req-aaa], el de la 2ª [req-hhh]; "
          "string entró SÓLO por la directiva → sus ítems de pax2a/osr1 llevan [req-ccc] y los de wt1a (símbolo base de una "
          "familia que corrió POR la directiva) también; alliance_orthologs (default) → []",
          it_d[w1]["directive_requirement_ids"] == ["req-aaa"] and it_d[w2]["directive_requirement_ids"] == ["req-hhh"]
          and it_d["FAKE:pax2a:1"]["source_family"] == "string" and it_d["FAKE:pax2a:1"]["directive_requirement_ids"] == ["req-ccc"]
          and it_d["FAKE:osr1:1"]["directive_requirement_ids"] == ["req-ccc"]
          and it_d["FAKE:wt1a:1"]["source_family"] == "string" and it_d["FAKE:wt1a:1"]["directive_requirement_ids"] == ["req-ccc"]
          and it_d["AL:wt1a"]["source_family"] == "alliance_orthologs" and it_d["AL:wt1a"]["directive_requirement_ids"] == []
          and all("directive_requirement_ids" in i for i in rd_d["items"]),
          repr({k: v["directive_requirement_ids"] for k, v in it_d.items()}))
    check("source_event_payload lleva directive_requirement_ids (stage.search.source: 'lo pidió el consejo · req-…'); [] cuando nadie "
          "la pidió — la llave viaja SIEMPRE",
          sh.source_event_payload(by_d["openalex"])["directive_requirement_ids"] == ["req-aaa", "req-hhh"]
          and sh.source_event_payload(by_d["alliance_orthologs"])["directive_requirement_ids"] == []
          and all("directive_requirement_ids" in sh.source_event_payload(r) for r in rows_rd))
    check("_rids_for (la regla de atribución, pura): insumo mapeado → sus ids; familia entered_by 'directive' → todos; base de una "
          "familia default → []; sin queries → []; _family_status reproduce la agregación de ADR-0080 (refactor sin cambio)",
          sh._rids_for({"directive_inputs": {"osr1": ["r1"]}, "entered_by": "default+directive", "directive_requirement_ids": ["r1"]}, "osr1") == ["r1"]
          and sh._rids_for({"directive_inputs": {"osr1": ["r1"]}, "entered_by": "default+directive", "directive_requirement_ids": ["r1"]}, "wt1a") == []
          and sh._rids_for({"entered_by": "directive", "directive_requirement_ids": ["r1", "r2"]}, "wt1a") == ["r1", "r2"]
          and sh._rids_for({}, "wt1a") == [] and sh._rids_for(None, None) == []
          and sh._family_status([{"x": 1}], ["error"]) == "success" and sh._family_status([], []) == "skipped-budget"
          and sh._family_status([], ["no-match", "error"]) == "no-match" and sh._family_status([], ["tool-unavailable"] * 2) == "tool-unavailable"
          and sh._family_status([], ["skipped-budget"] * 3) == "skipped-budget" and sh._family_status([], ["not-requested"]) == "not-requested"
          and sh._family_status([], ["error", "skipped-budget"]) == "error")
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
    check("ronda: módulo ausente -> 'tool-unavailable' con el detalle de qué faltó; web (families= del llamador, provider derivado off "
          "sin llave) -> la fila MÍNIMA de 7d9ce15 (corrector ADR-0084 L): 'tool-unavailable' con detail 'tool-unavailable (ADR-0084)' "
          "byte-idéntico a hoy y el MISMO keyset que la fila de monarch (fn None) — SIN provider/n_queries/web_locator (la CAUSA "
          "'BRAVE_API_KEY unset' viaja en frozen.web_locator.state, no en la fila); contadores null, cero red",
          by["monarch"]["status"] == "tool-unavailable" and "not found" in by["monarch"]["detail"]
          and by["web"]["status"] == "tool-unavailable" and by["web"]["detail"] == "tool-unavailable (ADR-0084)"
          and set(by["web"]) == set(by["monarch"]) and "web_locator_state" not in by["web"] and "provider" not in by["web"]
          and by["web"]["n_found"] is None and by["web"]["n_new"] is None,
          repr({k: by["web"].get(k) for k in ("status", "detail")} | {"keys": sorted(by["web"])}))
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
    # tool que LANZA -> error declarado, la ronda sigue (TODAS las familias fakeadas: con sólo dos inyectadas, reactome/string
    # cargaban la tool REAL y, sin caché del día UTC, tocaban la red — medido por el contador de urlopen, ADR-0082 L.3)
    rd_x = sh.run_round(plan_r, 1, 30.0, tools={**tools, "alliance_orthologs": fake_raises, "uniprot": fake_ok})
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
        check("legadas SIN directivas (ADR-0082): las filas no ganan calls[] ni error; directive_requirement_ids [] en filas e ítems "
              "(la llave viaja siempre; el resto de la fila es el de ADR-0080)",
              all("calls" not in s and s["directive_requirement_ids"] == [] for s in rd_l["sources"])
              and all(i["directive_requirement_ids"] == [] for i in rd_l["items"]))

        # ---- ADR-0082 (G.3): directive_queries de europepmc = UNA llamada EXTRA dentro del presupuesto (el fake CUENTA) ----
        epmc_calls = []

        def fake_epmc_dir(query, n=5, sort=None, synonym=True):
            epmc_calls.append(query)
            if "knockdown" in query:
                return ([{"epmc_id": "4", "source": "MED", "pmid": "444", "pmcid": None, "doi": "10.1/ddd", "title": "directive paper",
                          "year": "2022", "journal": "J", "is_oa": False, "abstract": "wt1a knockdown pronephric duct", "cited_by": 0}],
                        {"source": "europepmc", "status": "success", "query_sent": query, "n_found": 1, "n_returned": 1,
                         "elapsed_s": 0.01, "contact": "unset"})
            return fake_epmc(query, n, sort, synonym)
        fetch_paper.search_europepmc_ledger = fake_epmc_dir
        plan_ld = sh.build_search_plan(q, ["wt1a"], "wt1a pronephros",
                                       directives=[d for d in DIRECTIVES_C6 if d["family"] in ("europepmc", "zfin")])
        plan_ld["families"] = ["europepmc", "pubmed", "zfin"]
        epmc_calls.clear()
        rd_ld = sh.run_round(plan_ld, 1, 30.0, ctx={"retmax": 20, "n_papers": 5, "literature_requested": True, "pubmed_seen": {}})
        bld = {s["family"]: s for s in rd_ld["sources"]}
        ep = bld["europepmc"]
        check("legadas + directiva (G.3): europepmc hizo DOS llamadas — la del constructor y UNA EXTRA con la query_en de la directiva "
              "(el fake cuenta 2); calls[] = [builder, council-directive req-ddd]; n_found 2 (1 + 1); `ledger` sigue siendo el de la "
              "BASE (europepmc_searched byte-compatible); el paper de la directiva (PMID:444) lleva [req-ddd] y el de la base (PMID:111) "
              "[]; zfin: el ítem de osr1 (símbolo añadido) lleva [req-eee] y el de wt1a []; pubmed sin directiva → [] y sin calls",
              len(epmc_calls) == 2 and "knockdown" in epmc_calls[1] and ep["status"] == "success" and ep["n_found"] == 2
              and [c["kind"] for c in ep["calls"]] == ["builder", "council-directive"] and ep["calls"][1]["requirement_id"] == "req-ddd"
              and ep["calls"][1]["status"] == "success" and ep["calls"][1]["n_found"] == 1 and ep["n_calls"] == 2
              and ep["ledger"]["query_sent"] == epmc_calls[0] and ep["directive_requirement_ids"] == ["req-ddd"]
              and ep["n_new"] == 2 and "error" not in ep
              and {i["evidence_id"]: i["directive_requirement_ids"] for i in rd_ld["items"] if i["source_family"] == "europepmc"}
              == {"PMID:111": [], "PMID:444": ["req-ddd"]}
              and {(i.get("zfin") or {}).get("symbol"): i["directive_requirement_ids"] for i in rd_ld["items"] if i["source_family"] == "zfin"}
              == {"wt1a": [], "osr1": ["req-eee"]}
              and bld["pubmed"]["directive_requirement_ids"] == [] and "calls" not in bld["pubmed"],
              repr((epmc_calls, {k: (v["status"], v.get("n_found"), v["directive_requirement_ids"]) for k, v in bld.items()})))
        epmc_calls.clear()
        row0, items0 = sh.run_source("europepmc", plan_ld, {"retmax": 20, "n_papers": 5, "literature_requested": True, "pubmed_seen": {}}, 0.0)
        check("presupuesto de familia 0: la llamada BASE corre (la admisión la decidió el reparto de la ronda) y la EXTRA de la "
              "directiva queda 'skipped-budget' declarada SIN tocar la red (el fake cuenta 1); n_calls_skipped_budget 1; la fila sigue "
              "'success' con lo medido (n_found 1)",
              len(epmc_calls) == 1 and row0["status"] == "success" and row0["calls"][1]["status"] == "skipped-budget"
              and "family budget" in row0["calls"][1]["detail"] and row0["n_calls_skipped_budget"] == 1 and row0["n_found"] == 1
              and row0["calls"][1]["directive_requirement_ids"] == ["req-ddd"]
              and [i["evidence_id"] for i in items0] == ["PMID:111"], repr(row0["calls"]))
        # ---- path_b_bundle con directivas: el camino que runs recorre (C5 pasará directives=…) ----
        # las 5 auto SIGUEN en el plan: alliance_orthologs / zfin_expression se FAKEAN (cero red, mcp_cache intacto)
        ev_d = []
        sh._TOOL_CACHE["openalex"] = (fake_free, "injected", None)
        sh._TOOL_CACHE["alliance_orthologs"] = (fake_ok, "injected", None)
        sh._TOOL_CACHE["zfin_expression"] = (fake_nomatch, "injected", None)
        dirs_pb = [d for d in DIRECTIVES_C6 if d["family"] in ("openalex", "europepmc", "web")]   # aaa, ddd, fff, hhh
        plan_pbd = sh.build_search_plan(q, ["wt1a"], "wt1a pronephros", directives=dirs_pb)
        epmc_calls.clear()
        blkd = ap.path_b_bundle(q, entities=["wt1a"], triggered_by=["competence"], search_plan=plan_pbd,
                                on_stage=lambda n, p: ev_d.append((n, p)))
        sld = blkd["search_ledger"]
        pl_ev = next(p for n, p in ev_d if n == "search.plan")
        ep_row = next(s for s in sld["rounds"][0]["sources"] if s["family"] == "europepmc")
        oa_row = next(s for s in sld["rounds"][0]["sources"] if s["family"] == "openalex")
        src_evs = {p["family"]: p for n, p in ev_d if n == "search.source"}
        check("path_b_bundle con directivas (4: openalex ×2, europepmc, web): stage.search.plan {families_source 'directives+default', "
              "n_directives 4, familias = 5 auto + openalex, web excluida 'unsatisfiable-by-harness'}; _plan_with_queries CONSERVA los "
              "campos de directiva (search_ledger.plan.queries.openalex.query_source 'council-directive:req-aaa', europepmc."
              "directive_queries, directives_applied ×4); la fila congelada de europepmc lleva calls[] con la directiva (el fake contó 2) "
              "y la de openalex directive_requirement_ids [aaa, hhh] con 2 llamadas; stage.search.source lo lleva (zfin []); los dos "
              "papers de openalex entran a papers con kind 'paper' / source_family",
              pl_ev["families_source"] == "directives+default" and pl_ev["n_directives"] == 4
              and pl_ev["families"] == list(sh.DEFAULT_FAMILIES) + ["openalex"]
              and pl_ev["families_excluded"] == [{"family": "web", "reason": "unsatisfiable-by-harness (tool-unavailable (ADR-0084))",
                                                   "requirement_ids": ["req-fff"]}]
              and sld["plan"]["queries"]["openalex"]["query_source"] == "council-directive:req-aaa"
              and sld["plan"]["queries"]["europepmc"]["directive_queries"][0]["requirement_id"] == "req-ddd"
              and [r["state"] for r in sld["plan"]["directives_applied"]] == ["applied", "applied", "excluded-unsatisfiable", "applied"]
              and sld["plan"]["families_source"] == "directives+default"
              and [c["kind"] for c in ep_row["calls"]] == ["builder", "council-directive"] and ep_row["directive_requirement_ids"] == ["req-ddd"]
              and oa_row["directive_requirement_ids"] == ["req-aaa", "req-hhh"] and oa_row["status"] == "success" and oa_row["n_calls"] == 2
              and src_evs["openalex"]["directive_requirement_ids"] == ["req-aaa", "req-hhh"] and src_evs["zfin"]["directive_requirement_ids"] == []
              and sum(1 for p in blkd["papers"] if p.get("source_family") == "openalex" and p.get("kind") == "paper") == 2
              and len(epmc_calls) == 2,
              repr((pl_ev["n_directives"], pl_ev["families"], pl_ev["families_excluded"], [c["kind"] for c in ep_row.get("calls", [])],
                    oa_row.get("directive_requirement_ids"), len(epmc_calls))))
        fetch_paper.search_europepmc_ledger = fake_epmc
        for fam in ("openalex", "alliance_orthologs", "zfin_expression"):
            sh._TOOL_CACHE.pop(fam, None)

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

        # ---- corrector ADR-0080 (paridad webapp 2026-09-15): SIN entidades y SIN EN -> nada que buscar, declarado ----
        # Hallazgo medido en los fixtures objetada-confianza-ausente / citas-no-parseables: el ledger legado decía
        # 'not-searched' (query None), el harness lo degradaba a 'error' ("query builder produced no … query") y dejaba
        # inputs_used [None] != [] (la firma de _inputs_for) -> ronda 2 idéntica (skipped-cap) -> stop 'rounds-cap', n_rounds 2.
        lit_calls = []
        _fe, _fp, _fz = (fetch_paper.search_europepmc_ledger, ap._WS_CACHE[("pubmed_literature.py", "query_pubmed")],
                         ap._WS_CACHE[("zfin_zebrafish.py", "query_zfin")])
        fetch_paper.search_europepmc_ledger = lambda *a, **kw: (lit_calls.append("europepmc"), _fe(*a, **kw))[1]
        ap._WS_CACHE[("pubmed_literature.py", "query_pubmed")] = lambda *a, **kw: (lit_calls.append("pubmed"), _fp(*a, **kw))[1]
        ap._WS_CACHE[("zfin_zebrafish.py", "query_zfin")] = lambda *a, **kw: (lit_calls.append("zfin"), _fz(*a, **kw))[1]
        called.clear()
        plan_nq = sh.build_search_plan(q, [], None, families=["europepmc", "pubmed", "zfin", "alliance_orthologs"])
        sh._TOOL_CACHE["alliance_orthologs"] = (spy, "injected", None)
        ctx_nq = {"retmax": 20, "n_papers": 5, "literature_requested": True, "pubmed_seen": {}, "dois": [], "curies": []}
        rd_nq = sh.run_round(plan_nq, 1, 30.0, ctx=ctx_nq)
        bnq = {s["family"]: s for s in rd_nq["sources"]}
        sig_nq = sh.inputs_signature(plan_nq, ctx_nq)
        check("corrector paridad webapp: plan SIN entidades ni EN -> europepmc/pubmed dejan fila 'not-requested' con el detail del "
              "ledger legado ('… (nothing to search)') y SIN error (no hubo fallo: no había nada que buscar; el ledger conserva SU "
              "literal 'not-searched'); zfin/alliance 'not-requested' 'no symbols'; inputs_used == firma de _inputs_for ([] en las "
              "cuatro, jamás [None]) con inputs_mode declarado; contadores null; cero llamadas a las fuentes; "
              "families_with_new_inputs sobre lo consumido == []",
              bnq["europepmc"]["status"] == "not-requested" and "nothing to search" in bnq["europepmc"]["detail"]
              and "error" not in bnq["europepmc"] and bnq["europepmc"]["ledger"]["status"] == "not-searched"
              and bnq["pubmed"]["status"] == "not-requested" and "nothing to search" in bnq["pubmed"]["detail"]
              and "error" not in bnq["pubmed"] and bnq["pubmed"]["ledger"]["status"] == "not-searched"
              and bnq["zfin"]["status"] == "not-requested" and bnq["zfin"]["detail"] == "no symbols"
              and bnq["alliance_orthologs"]["status"] == "not-requested"
              and all(bnq[f]["inputs_used"] == sig_nq[f][1] == [] and bnq[f]["inputs_mode"] == sig_nq[f][0] for f in bnq)
              and all(bnq[f]["n_found"] is None and bnq[f]["n_new"] is None for f in bnq)
              and lit_calls == [] and called == []
              and sh.families_with_new_inputs(plan_nq, ctx_nq, sh.inputs_used_by_round(rd_nq)) == [],
              repr({f: (s["status"], s.get("detail"), s.get("inputs_used")) for f, s in bnq.items()}))
        ev_nq = []
        blk_nq = ap.path_b_bundle(q, entities=[], search_plan=plan_nq, on_stage=lambda n, p: ev_nq.append(n))
        sl_nq = blk_nq["search_ledger"]
        check("corrector paridad webapp: la MISMA corrida por path_b_bundle con cap 2 -> should_run_next_round False -> UNA ronda, "
              "stop 'no-new-inputs' (antes: [None] != [] fingía insumos nuevos -> ronda 2 idéntica skipped-cap -> 'rounds-cap', "
              "n_rounds 2), rounds[0].inputs_changed False y families_with_new_inputs [], un solo search.round, las cuatro filas "
              "'not-requested', europepmc_searched/pubmed_searched 'not-searched' (ledger de hoy intacto), papers [], cero llamadas",
              sl_nq["n_rounds"] == 1 and sl_nq["cap"] == 2 and sl_nq["stop_reason"] == "no-new-inputs"
              and sl_nq["rounds"][0]["inputs_changed"] is False and sl_nq["rounds"][0]["families_with_new_inputs"] == []
              and ev_nq.count("search.round") == 1
              and {s["family"]: s["status"] for s in sl_nq["rounds"][0]["sources"]} == {f: "not-requested" for f in plan_nq["families"]}
              and not any("error" in s for s in sl_nq["rounds"][0]["sources"])
              and blk_nq["europepmc_searched"]["status"] == "not-searched" and blk_nq["pubmed_searched"]["status"] == "not-searched"
              and blk_nq["query_sent"] is None and blk_nq["papers"] == [] and lit_calls == [] and called == [],
              repr((sl_nq["n_rounds"], sl_nq["stop_reason"], ev_nq, lit_calls)))
        fetch_paper.search_europepmc_ledger = _fe
        ap._WS_CACHE[("pubmed_literature.py", "query_pubmed")] = _fp
        ap._WS_CACHE[("zfin_zebrafish.py", "query_zfin")] = _fz

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
        for fam in ("alliance_orthologs", "uniprot", "monarch", "openalex"):
            sh._TOOL_CACHE.pop(fam, None)

    # ============ 5. ADR-0084 (C)/(D): la familia web como LOCALIZADOR, jamás fuente (rebanada W3) ============
    from lib import web_locator as wl  # noqa: E402 — interfaz congelada por W2 (import barato)
    GOLDEN = json.loads((ROOT / "rag_index" / "query_service" / "fixtures" / "golden_plan_web_directive_7d9ce15.json")
                        .read_text(encoding="utf-8"))
    g_inputs = GOLDEN["_golden"]["recipe"]["plan_inputs"]
    gq, g_ents, g_pass1 = g_inputs["question"], list(g_inputs["entities"]), g_inputs["pass1_query_en"]
    FAKE_KEY = "fake-brave-key-smoke-0084-never-in-output"
    WEB_ENV_KEYS = dict(WITT_SEARCH_DEFAULT_FAMILIES=None, WITT_SEARCH_ROUNDS_CAP=None, WITT_SEARCH_ROUND_BUDGET_S=None,
                        WITT_WEB_LOCATOR=None, BRAVE_API_KEY="", WITT_WEB_TEST_QUERY=None, WITT_WEB_MAX_QUERIES=None,
                        WITT_WEB_MAX_MATERIALIZE=None, WITT_WEB_BUDGET_S=None, WITT_WEB_MONTHLY_CAP=None)

    def _canon_sha(obj):
        return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()

    old = _env(**WEB_ENV_KEYS)
    # ---- 5a. off DERIVADO (la máscara): disponibilidad dinámica y UNA verdad del literal ----
    src_text = (ROOT / "analysis" / "scripts" / "lib" / "search_harness.py").read_text(encoding="utf-8")
    n_literal_lines = sum(1 for ln in src_text.splitlines() if "unsatisfiable-by-harness (tool-unavailable (ADR-0084))" in ln)
    check("ADR-0084 (C.2) off DERIVADO (BRAVE_API_KEY vacía, WITT_WEB_LOCATOR sin fijar): family_available('web') == (False, "
          "'tool-unavailable (ADR-0084)') — el literal de 7d9ce15 —, unsatisfiable_families() == ('tooluniverse', 'web'); tooluniverse "
          "sigue estática (ADR-0085), europepmc (tool_module None pero adapter) disponible, desconocida declarada; el literal de exclusión "
          "aparece UNA sola vez en search_harness.py (grep -c == 1) y == golden._golden.exclusion_literal_at_7d9ce15 == "
          "f'unsatisfiable-by-harness ({SEARCH_DISPATCH.web.unavailable_reason})'",
          sh.family_available("web") == (False, "tool-unavailable (ADR-0084)")
          and sh.unsatisfiable_families() == ("tooluniverse", "web")
          and sh.family_available("tooluniverse") == (False, "tool-unavailable (ADR-0085)")
          and sh.family_available("europepmc") == (True, None) and sh.family_available("nope") == (False, "unknown-family")
          and n_literal_lines == 1
          and sh.WEB_UNSATISFIABLE_LITERAL == GOLDEN["_golden"]["exclusion_literal_at_7d9ce15"]
          == f"{sh.UNSATISFIABLE_PREFIX}{sh.SEARCH_DISPATCH['web']['unavailable_reason']})",
          repr((sh.family_available("web"), sh.unsatisfiable_families(), n_literal_lines)))
    check("ADR-0084 (C.1): _load_tool('web') carga la tool REAL por ruta (fn resuelta 'locate', sin nota, callable) — el cableado "
          "estático que smoke_run_pipeline mide como '13 módulos reales'; cero red al importar",
          sh._load_tool("web")[1] == "locate" and sh._load_tool("web")[2] is None and callable(sh._load_tool("web")[0]),
          repr(sh._load_tool("web")[1:]))
    # ---- 5b. GOLDEN W0: bajo off (derivado y EXPLÍCITO con llave) el plan con la directiva web es BYTE-IDÉNTICO a 7d9ce15 ----
    p_off = sh.build_search_plan(gq, g_ents, g_pass1, directives=DIRECTIVES_C6)
    body_off = {k: v for k, v in p_off.items() if k != "cache_dir"}
    _e2 = _env(WITT_WEB_LOCATOR="off", BRAVE_API_KEY=FAKE_KEY)
    p_off2 = sh.build_search_plan(gq, g_ents, g_pass1, directives=DIRECTIVES_C6)
    body_off2 = {k: v for k, v in p_off2.items() if k != "cache_dir"}
    fa_off2, uns_off2 = sh.family_available("web"), sh.unsatisfiable_families()
    _restore(_e2)
    diff_keys = sorted(k for k in set(body_off) | set(GOLDEN["plan"]) if body_off.get(k) != GOLDEN["plan"].get(k))
    check("GOLDEN W0 @ 7d9ce15 (ADR-0084 L): bajo off DERIVADO el plan con la directiva web (insumos EXACTOS de _golden.recipe) es "
          "byte-idéntico al golden — dict == dict sin cache_dir Y sha256 canon == _golden.sha256.plan (== _plan_sha); bajo kill-switch "
          "EXPLÍCITO WITT_WEB_LOCATOR=off CON llave presente, ídem (la llave no manda sobre el kill-switch) y family_available False "
          "con el MISMO literal; sin web NO hay families_order_rule (un plan sin web no gana llaves) ni en plan_event_payload",
          body_off == GOLDEN["plan"] and _canon_sha(body_off) == GOLDEN["_golden"]["sha256"]["plan"] == _plan_sha(p_off)
          and body_off2 == GOLDEN["plan"] and _canon_sha(body_off2) == GOLDEN["_golden"]["sha256"]["plan"]
          and fa_off2 == (False, "tool-unavailable (ADR-0084)") and uns_off2 == ("tooluniverse", "web")
          and "families_order_rule" not in p_off and "families_order_rule" not in sh.plan_event_payload(p_off),
          repr((diff_keys, _canon_sha(body_off), fa_off2)))
    check("GOLDEN W0 forma (2): el literal que council.harness_state_for('web','web') debe producir bajo off — "
          "f'unsatisfiable-by-harness ({razón de family_available})' — es byte-idéntico a golden.harness_state_web y su sha256 canon == "
          "_golden.sha256.harness_state_web (W6 delega en family_available; aquí se mide la vara que recibirá)",
          f"{sh.UNSATISFIABLE_PREFIX}{sh.family_available('web')[1]})" == GOLDEN["harness_state_web"] == sh.WEB_UNSATISFIABLE_LITERAL
          and _canon_sha(sh.WEB_UNSATISFIABLE_LITERAL) == GOLDEN["_golden"]["sha256"]["harness_state_web"],
          repr(GOLDEN["harness_state_web"]))
    # ---- 5c. brave EXPLÍCITO sin llave: la CAUSA viaja con el mismo prefijo ----
    _e3 = _env(WITT_WEB_LOCATOR="brave")
    p_nokey = sh.build_search_plan(gq, g_ents, g_pass1, directives=DIRECTIVES_C6)
    fa_nokey = sh.family_available("web")
    _restore(_e3)
    web_ex = next((e for e in p_nokey["families_excluded"] if e["family"] == "web"), {})
    check("ADR-0084 (B.3/C.2) WITT_WEB_LOCATOR=brave SIN llave: family_available == (False, 'tool-unavailable (ADR-0084: BRAVE_API_KEY "
          "unset)') y el plan excluye web con 'unsatisfiable-by-harness (tool-unavailable (ADR-0084: BRAVE_API_KEY unset))' — mismo "
          "prefijo que la webapp ya glosa, la causa declarada, requirement_ids [req-fff]; web fuera de families",
          fa_nokey == (False, wl.UNAVAILABLE_BRAVE_NO_KEY)
          and web_ex.get("reason") == f"{sh.UNSATISFIABLE_PREFIX}{wl.UNAVAILABLE_BRAVE_NO_KEY})"
          and web_ex.get("reason", "").startswith("unsatisfiable-by-harness (tool-unavailable (ADR-0084")
          and web_ex.get("requirement_ids") == ["req-fff"] and "web" not in p_nokey["families"],
          repr(web_ex))
    # ---- 5d. con llave (FAKE) y provider brave: web ENTRA por directiva y va PRIMERA ----
    _restore(old)
    old = _env(**dict(WEB_ENV_KEYS, WITT_WEB_LOCATOR="brave", BRAVE_API_KEY=FAKE_KEY))
    p_on = sh.build_search_plan(gq, g_ents, g_pass1, directives=DIRECTIVES_C6)
    qw = p_on["queries"]["web"]

    def _strip_web(p):
        d = {k: v for k, v in p.items() if k not in ("cache_dir", "families", "families_excluded", "families_from_directives",
                                                      "directives_applied", "n_directives_excluded", "families_order_rule")}
        d["queries"] = {k: v for k, v in (d.get("queries") or {}).items() if k != "web"}
        return d
    da_on = {r["requirement_id"]: (r["state"], r["applied_as"]) for r in p_on["directives_applied"]}
    da_g = {r["requirement_id"]: (r["state"], r["applied_as"]) for r in GOLDEN["plan"]["directives_applied"]}
    check("ADR-0084 (C.2/C.4) llave fake + WITT_WEB_LOCATOR=brave: family_available('web') == (True, None), unsatisfiable_families() == "
          "('tooluniverse',); el plan con DIRECTIVES_C6 pone web PRIMERA (families[0] == 'web', el resto == golden en su orden), declara "
          "families_order_rule 'web first — the locator feeds the round (ADR-0084)', excluye SÓLO 'nope' (n_directives_excluded 1), "
          "req-fff pasa de 'excluded-unsatisfiable' a ('applied', ['family-entry', 'free-query']) y las demás directivas quedan "
          "EXACTAMENTE como en el golden; plan_event_payload lo refleja",
          sh.family_available("web") == (True, None) and sh.unsatisfiable_families() == ("tooluniverse",)
          and p_on["families"][0] == "web" and p_on["families"][1:] == GOLDEN["plan"]["families"]
          and p_on["families_order_rule"] == sh.FAMILIES_ORDER_RULE_WEB_FIRST == "web first — the locator feeds the round (ADR-0084)"
          and p_on["families_excluded"] == [{"family": "nope", "reason": "unknown-family", "requirement_ids": ["req-ggg"]}]
          and p_on["n_directives_excluded"] == 1 and "web" in p_on["families_from_directives"]
          and da_on["req-fff"] == ("applied", ["family-entry", "free-query"])
          and {k: v for k, v in da_on.items() if k != "req-fff"} == {k: v for k, v in da_g.items() if k != "req-fff"}
          and sh.plan_event_payload(p_on)["families"][0] == "web",
          repr((p_on["families"], p_on.get("families_order_rule"), da_on.get("req-fff"))))
    check("ADR-0084 (C.3) gate directive-only ESTRICTO: queries.web.query == query_en de la directiva ('wt1a review'), query_source "
          "'council-directive:req-fff', entered_by 'directive', la sustituida (pass1_query_en) declarada en query_replaced, "
          "_inputs_for(web) == ['wt1a review'] (la pregunta cruda AUSENTE por substring); TODO lo demás del plan (queries de las otras "
          "familias, símbolos, cap, budget, directives verbatim) es byte-idéntico al golden — la entrada de web es SÓLO aditiva",
          qw["query"] == "wt1a review" and qw["query_source"] == "council-directive:req-fff" and qw["entered_by"] == "directive"
          and qw["directive_requirement_ids"] == ["req-fff"]
          and qw["query_replaced"] == {"query": g_pass1, "query_source": "pass1_query_en"}
          and sh._inputs_for("web", sh.SEARCH_DISPATCH["web"], p_on, {})[0] == ["wt1a review"]
          and gq not in json.dumps(qw) and "required" not in json.dumps(qw)
          and _strip_web(p_on) == _strip_web(GOLDEN["plan"]),
          repr(qw))
    # ---- 5e. web nombrada en WITT_SEARCH_DEFAULT_FAMILIES (la directiva del operador) ----
    _e5 = _env(WITT_SEARCH_DEFAULT_FAMILIES="europepmc,web")
    p_env = sh.build_search_plan(gq, g_ents, g_pass1)
    p_env_np = sh.build_search_plan(gq, g_ents, None)
    _e6 = _env(WITT_WEB_TEST_QUERY="wt1a zebrafish pronephros podocyte")
    p_tq = sh.build_search_plan(gq, g_ents, g_pass1)
    p_tq_d = sh.build_search_plan(gq, g_ents, g_pass1, directives=[d for d in DIRECTIVES_C6 if d["family"] == "web"])
    _restore(_e6)
    _restore(_e5)
    check("ADR-0084 (C.3) WITT_SEARCH_DEFAULT_FAMILIES='europepmc,web' SIN directiva: web PRIMERA (['web', 'europepmc']) con "
          "families_order_rule, query == pass1_query_en (query_source 'pass1_query_en'), entered_by 'env:WITT_SEARCH_DEFAULT_FAMILIES' "
          "∈ ENTERED_BY; sin pass1 la query es símbolos+anatomía+'zebrafish' (search_harness:v1:symbols+anatomy) — en ningún caso la "
          "pregunta cruda (substring ausente)",
          p_env["families"] == ["web", "europepmc"] and p_env["families_order_rule"] == sh.FAMILIES_ORDER_RULE_WEB_FIRST
          and p_env["queries"]["web"]["query"] == g_pass1 and p_env["queries"]["web"]["query_source"] == "pass1_query_en"
          and p_env["queries"]["web"]["entered_by"] == "env:WITT_SEARCH_DEFAULT_FAMILIES" and "env:WITT_SEARCH_DEFAULT_FAMILIES" in sh.ENTERED_BY
          and p_env_np["queries"]["web"]["query_source"] == "search_harness:v1:symbols+anatomy"
          and gq not in (p_env["queries"]["web"]["query"] + p_env_np["queries"]["web"]["query"])
          and "required" not in (p_env["queries"]["web"]["query"] + p_env_np["queries"]["web"]["query"]),
          repr((p_env["families"], p_env["queries"]["web"], p_env_np["queries"]["web"]["query"])))
    check("ADR-0084 (C.3) WITT_WEB_TEST_QUERY fijada: la consulta EXPLÍCITA del operador manda cuando web entra por la env (query_source "
          "'operator-env:WITT_WEB_TEST_QUERY'); con directiva web presente la query_en del consejo sigue mandando (la de prueba no pisa "
          "al consejo)",
          p_tq["queries"]["web"]["query"] == "wt1a zebrafish pronephros podocyte"
          and p_tq["queries"]["web"]["query_source"] == sh.WEB_TEST_QUERY_SOURCE == "operator-env:WITT_WEB_TEST_QUERY"
          and p_tq_d["queries"]["web"]["query"] == "wt1a review" and p_tq_d["queries"]["web"]["query_source"] == "council-directive:req-fff",
          repr((p_tq["queries"]["web"], p_tq_d["queries"]["web"]["query"])))
    p_call = sh.build_search_plan(gq, g_ents, g_pass1, families=["string", "web"])
    check("ADR-0084 (C.4) families= del llamador MANDA: el orden NO se altera (['string', 'web']) y se declara families_order_rule "
          "'caller order (families= mandates; web not moved) (ADR-0084)'; sin entered_by en queries.web (null en el frozen)",
          p_call["families"] == ["string", "web"] and p_call["families_order_rule"] == sh.FAMILIES_ORDER_RULE_CALLER
          and "entered_by" not in p_call["queries"]["web"] and p_call["queries"]["web"]["query"] == g_pass1,
          repr((p_call["families"], p_call.get("families_order_rule"))))

    # ---- proveedor web FALSO (forma (A) de brave_web_search.locate), Europe PMC FALSO (fetch_paper._resolve_one), cuota FALSA ----
    WEB_URLS = [
        {"url": "https://pubmed.ncbi.nlm.nih.gov/12345678/?dopt=Abstract", "title": "WEB TITLE pubmed (never evidence)",
         "host": "pubmed.ncbi.nlm.nih.gov", "age": None, "page_age": None},
        {"url": "https://doi.org/10.1000/xyz123", "title": "WEB TITLE doi", "host": "doi.org", "age": "2 years ago", "page_age": None},
        {"url": "https://pubmed.ncbi.nlm.nih.gov/23456789/", "title": "WEB TITLE already present", "host": "pubmed.ncbi.nlm.nih.gov",
         "age": None, "page_age": None},
        {"url": "https://zfin.org/ZDB-GENE-980526-558", "title": "WEB TITLE zfin", "host": "zfin.org", "age": None, "page_age": None},
        {"url": "https://ensembl.org/Danio_rerio/Gene/Summary?g=ENSDARG00000031420", "title": "WEB TITLE ensembl", "host": "ensembl.org",
         "age": None, "page_age": None},
        {"url": "https://www.researchgate.net/publication/7742441_x", "title": "R" * 205, "host": "www.researchgate.net",
         "age": None, "page_age": None},
        {"url": "https://en.wikipedia.org/wiki/Wt1", "title": "WEB TITLE wiki", "host": "en.wikipedia.org", "age": None, "page_age": None},
    ]

    class WebSpy:
        """provider_fn con la firma de brave_web_search.locate (query, count, country, search_lang, freshness, timeout, cache_dir)."""

        def __init__(self, results=None, plan=None):
            self.calls, self.results, self.plan = [], (WEB_URLS if results is None else results), list(plan or [])

        def __call__(self, query, count=None, country=None, search_lang=None, freshness=None, timeout=None, cache_dir=None):
            self.calls.append({"query": query, "count": count, "timeout": timeout, "search_lang": search_lang})
            step = self.plan.pop(0) if self.plan else None
            if isinstance(step, Exception):
                raise step
            if isinstance(step, dict):
                return step
            return {"status": "success", "query_sent": query, "query_truncated": False, "elapsed_s": 0.01, "n_http_gets": 1,
                    "cache_hit": False, "http_status": 200, "api_key_present": True,
                    "throttle": {"host": "api.search.brave.com", "min_interval_s": 1.0, "waited_s": 0.0}, "retries_429": 0,
                    "data": {"query_original": query, "query_altered": None, "query_altered_by_provider": False,
                             "n_results": len(self.results), "results": [dict(r) for r in self.results]}}

    AUTH_ROW = {"status": "error", "error": "auth (HTTP 401)", "error_kind": "auth", "http_status": 401, "auth_failed": True,
                "elapsed_s": 0.01, "n_http_gets": 1}
    BUDGET_ROW = {"status": "skipped-budget", "error": "BudgetExhausted: timeout=0.0 <= 0 before the call (no request sent)",
                  "elapsed_s": 0.0, "n_http_gets": 0}
    EPMC_RECS = {"PMID:12345678": {"epmc_id": "12345678", "source": "MED", "pmid": "12345678", "pmcid": "PMC7654321",
                                    "doi": "10.1000/abc999", "title": "EPMC record for the web-located PMID", "year": "2021",
                                    "journal": "Dev Biol", "is_oa": True, "abstract": "wt1a pronephros podocyte abstract (Europe PMC)",
                                    "cited_by": 4}}

    class EpmcSpy:
        """corrector ADR-0084: la ronda materializa por fetch_paper.search_europepmc_ledger(<consulta por ident>, n=1, timeout=<presupuesto
        restante>) — el spy sirve por ident (search_harness.epmc_ident_of_query) y registra `calls` (idents), `queries` (crudas) y `timeouts`."""

        def __init__(self, recs=None):
            self.calls, self.queries, self.timeouts, self.recs = [], [], [], (EPMC_RECS if recs is None else recs)

        def __call__(self, query, n=5, sort=None, synonym=True, timeout=None):
            ident = sh.epmc_ident_of_query(query)
            assert ident is not None, f"smoke: la familia web debe consultar a EPMC por ident, no {query!r}"
            self.calls.append(ident)
            self.queries.append(query)
            self.timeouts.append(timeout)
            rec = self.recs.get(ident)
            return ([dict(rec)] if rec else []), {"source": "europepmc", "status": "success" if rec else "no-match", "query_sent": query,
                                                  "n_found": 1 if rec else 0, "n_returned": 1 if rec else 0, "elapsed_s": 0.01,
                                                  "timeout_s": timeout}

    class QuotaSpy:
        def __init__(self, grant=True):
            self.calls, self.grant, self.n = [], grant, 0

        def __call__(self, provider, month, cap, record=None):
            self.calls.append({"provider": provider, "month": month, "cap": cap, "record": record})
            if record is not None:
                return {"granted": None, "n_before": self.n, "n_after": self.n, "cap": cap}
            if not self.grant:
                return {"granted": False, "n_before": self.n, "n_after": self.n, "cap": cap}
            self.n += 1
            return {"granted": True, "n_before": self.n - 1, "n_after": self.n, "cap": cap}

    up_calls, mon_calls = [], []

    def fake_unpaywall(doi, timeout=None):
        up_calls.append(doi)
        return {"status": "success", "query_sent": f"doi={doi}", "elapsed_s": 0.01,
                "data": {"doi": doi, "crossref": {"status": "success", "evidence_kind": "oa-location",
                                                  "identifier_provenance": "crossref-api-live",
                                                  "data": {"doi": doi, "title": f"crossref record {doi}", "year": "2020"}},
                         "unpaywall": {"status": "tool-unavailable"}}}

    def fake_monarch(curie, timeout=None):
        mon_calls.append(curie)
        return {"status": "no-match", "query_sent": f"curie={curie}", "elapsed_s": 0.01, "data": {"associations": []}}

    _resolve_real = fetch_paper.search_europepmc_ledger
    try:
        # ---- 5f. la RONDA: web PRIMERA alimenta unpaywall y monarch en la MISMA ronda; 0 ítems web; ledger completo ----
        wspy, espy, qspy, events = WebSpy(), EpmcSpy(), QuotaSpy(), []
        fetch_paper.search_europepmc_ledger = espy
        plan_w = dict(p_on)
        plan_w["families"] = ["web", "unpaywall_crossref", "monarch"]
        ctx_w = {"dois": [], "curies": [], "existing_ids": {"PMID:23456789", "CORPUS-2026-0003#c000"},
                 "web_store": lambda key: None, "web_quota": qspy, "on_web_locate": events.append}
        id_dois, id_curies = id(ctx_w["dois"]), id(ctx_w["curies"])
        rd_w = sh.run_round(plan_w, 1, 30.0, tools={"web": wspy, "unpaywall_crossref": fake_unpaywall, "monarch": fake_monarch},
                            ctx=ctx_w, existing_ids=ctx_w["existing_ids"])
        bw = {s["family"]: s for s in rd_w["sources"]}
        web = bw["web"]
        wl_led = web["web_locator"]
        loc = {l["id"]: l for l in wl_led["located"]}
        web_items = [i for i in rd_w["items"] if i.get("source_family") == "web"]
        check("ADR-0084 (C.5) fila web (7 URLs: PMID nuevo · DOI no hallado en EPMC · PMID ya presente · ZDB-GENE · ENSDARG · 2 sin patrón): "
              "status 'success', n_found 7 == n_results, n_located 5, n_materialized 1, n_epmc_gets 2, n_not_found_in_europepmc 1, "
              "n_already_present 1, n_unresolved 2, n_fed_ctx 2 (DOI + curie), n_located_not_fed 1 (ENSDARG), n_new 1, n_queries 1 sin "
              "recortes, provider 'brave' env:WITT_WEB_LOCATOR, quota_state 'under-cap', cost_usd_projected 0.005 (1 GET × US$5/1k), "
              "web_locator_state 'located', round 1, directive_requirement_ids [req-fff], budget_s = min(30, 30/3)",
              web["status"] == "success" and web["n_found"] == 7 == web["n_results"] and web["n_located"] == 5
              and web["n_materialized"] == 1 and web["n_epmc_gets"] == 2 and web["n_not_found_in_europepmc"] == 1
              and web["n_already_present"] == 1 and web["n_unresolved"] == 2 and web["n_fed_ctx"] == 2 and web["n_located_not_fed"] == 1
              and web["n_new"] == 1 and web["n_queries"] == 1 and web["n_queries_dropped_by_cap"] == 0
              and web["provider"] == "brave" and web["provider_source"] == "env:WITT_WEB_LOCATOR" and web["provider_available"] is True
              and web["quota_state"] == "under-cap" and abs(web["cost_usd_projected"] - 0.005) < 1e-9
              and web["web_locator_state"] == "located" and web["round"] == 1 and web["directive_requirement_ids"] == ["req-fff"]
              and web["budget_s"] == 10.0 and "provider_fn injected" in web["fn_resolved"]
              and wspy.calls == [{"query": "wt1a review", "count": 10, "timeout": wspy.calls[0]["timeout"], "search_lang": "en"}]
              and wspy.calls[0]["timeout"] > 0,
              repr({k: web.get(k) for k in ("status", "n_found", "n_located", "n_materialized", "n_epmc_gets", "n_not_found_in_europepmc",
                                              "n_already_present", "n_unresolved", "n_fed_ctx", "n_located_not_fed", "n_new", "quota_state",
                                              "cost_usd_projected", "web_locator_state", "budget_s")}))
        check("ADR-0084 (C.5 i) MATERIALIZACIÓN por Europe PMC en la MISMA ronda: fetch_paper._resolve_one recibió EXACTAMENTE "
              "['PMID:12345678', 'DOI:10.1000/xyz123'] (forma EPMC_IDENT_RE verificada ANTES; el PMID ya presente NO se busca) — el PMID "
              "→ 'materialized-same-round' fed_to pool con evidence_id; el DOI → rec None → 'not-found-in-europepmc' (contado, NO es "
              "candidato) y aun así fed_to 'ctx:dois' para unpaywall; PMID:23456789 → 'already-present (dup of PMID:23456789)' fed_to "
              "None; ZDB-GENE → 'ctx:curies' 'fed-same-round'; ENSDARG → 'no-sink-in-1.13 (ensdarg)' con store_state 'not-in-store' "
              "(store falso, 0 red); todo feed_state/fed_to en los vocabularios de web_locator",
              espy.calls == ["PMID:12345678", "DOI:10.1000/xyz123"] and all(wl.EPMC_IDENT_RE.match(c) for c in espy.calls)
              and espy.queries == ["EXT_ID:12345678 AND SRC:MED", "DOI:10.1000/xyz123"]
              and all(t is not None and sh.MIN_CALL_TIMEOUT_S <= t <= 10.0 for t in espy.timeouts)   # corrector: presupuesto de la familia (10 s)
              and loc["PMID:12345678"]["epmc_timeout_s"] == espy.timeouts[0] and loc["PMID:12345678"]["epmc_query_quoted"] is False
              and loc["PMID:12345678"]["fed_to"] == sh.WEB_FED_TO_POOL == "pool:literature-candidate (materialized by europepmc)"
              and loc["PMID:12345678"]["feed_state"] == "materialized-same-round" and loc["PMID:12345678"]["evidence_id"] == "PMID:12345678"
              and loc["PMID:12345678"]["epmc_ident_sent"] == "PMID:12345678"
              and loc["10.1000/xyz123"]["feed_state"] == "not-found-in-europepmc" and loc["10.1000/xyz123"]["fed_to"] == "ctx:dois"
              and loc["PMID:23456789"]["feed_state"] == "already-present (dup of PMID:23456789)" and loc["PMID:23456789"]["fed_to"] is None
              and loc["PMID:23456789"]["dedup"] == "already-present (existing_ids)"
              and loc["ZFIN:ZDB-GENE-980526-558"]["fed_to"] == "ctx:curies" and loc["ZFIN:ZDB-GENE-980526-558"]["feed_state"] == "fed-same-round"
              and loc["ENSDARG00000031420"]["feed_state"] == "no-sink-in-1.13 (ensdarg)" and loc["ENSDARG00000031420"]["fed_to"] is None
              and loc["ENSDARG00000031420"]["store_state"] == "not-in-store"
              and all(wl.feed_state_in_vocabulary(l["feed_state"]) and l["fed_to"] in wl.FED_TO and l["round"] == 1
                      and l["requirement_ids"] == ["req-fff"] for l in wl_led["located"])
              and wl.web_state_in_vocabulary(web["web_locator_state"]),
              repr((espy.calls, [(l["id"], l["fed_to"], l["feed_state"]) for l in wl_led["located"]])))
        wi = web_items[0] if web_items else {}
        items_json = json.dumps(rd_w["items"], ensure_ascii=False)
        check("ADR-0084 (C.5) 0 ÍTEMS WEB — el gate del brief: la familia emitió EXACTAMENTE 1 candidato y es de Europe PMC: evidence_id "
              "'PMID:12345678', source 'europepmc', source_family 'web', kind 'literature-candidate', identifier_provenance "
              "'web-located:pubmed-path', url CANÓNICA (≠ la hallada con ?dopt), title/search_rec/abstract de EPMC (no el título web), "
              "located_via 'web', located_from {host, rule_id, confidence, kind, round, requirement_ids} SIN url, search_rec_source "
              "declarado, dedup_layer 'pool', [req-fff]; ningún ítem de la ronda es source/kind 'web' ni trae title_web/description; "
              "ni 'WEB TITLE' ni la URL hallada aparecen en items[]",
              len(web_items) == 1 and wi.get("evidence_id") == "PMID:12345678" and wi.get("source") == "europepmc"
              and wi.get("source_family") == "web" and wi.get("kind") == "literature-candidate"
              and wi.get("identifier_provenance") == "web-located:pubmed-path" and wi.get("url") == "https://pubmed.ncbi.nlm.nih.gov/12345678/"
              and wi.get("title") == "EPMC record for the web-located PMID" and wi.get("search_rec", {}).get("pmcid") == "PMC7654321"
              and wi.get("search_rec", {}).get("doi") == "10.1000/abc999" and wi.get("abstract") == "wt1a pronephros podocyte abstract (Europe PMC)"
              and wi.get("located_via") == "web"
              and wi.get("located_from") == {"host": "pubmed.ncbi.nlm.nih.gov", "rule_id": "pubmed-path", "confidence": "host-table",
                                             "kind": "pmid", "round": 1, "requirement_ids": ["req-fff"]}
              and wi.get("search_rec_source") == sh.WEB_SEARCH_REC_SOURCE and wi.get("dedup_layer") == "pool"
              and wi.get("directive_requirement_ids") == ["req-fff"] and wi.get("round") == 1 and wi.get("label") is None
              and "title_web" not in wi and "description" not in wi
              and not any(i.get("source") == "web" or i.get("kind") == "web" or "title_web" in i or "description" in i for i in rd_w["items"])
              and "WEB TITLE" not in items_json and "?dopt" not in items_json,
              repr(wi))
        check("ADR-0084 (C.4/C.5 ii-iii) ENCADENADO EN LA MISMA RONDA: unpaywall_crossref RECIBIÓ el DOI localizado por la web "
              "('10.1000/xyz123', el primero) y el DOI del registro EPMC cosechado por run_round; monarch RECIBIÓ la curie "
              "'ZFIN:ZDB-GENE-980526-558'; ctx.dois / ctx.curies son las MISMAS listas del llamador (id() intacto: append-only, jamás "
              "reasignadas — M.3); ambas filas corrieron ('success' / 'no-match'); el candidato web va DESPUÉS de los nativos en items[] "
              "(D.1: no gana identidad en la ronda) y round.duplicates == []",
              up_calls == ["10.1000/xyz123", "10.1000/abc999"] and mon_calls == ["ZFIN:ZDB-GENE-980526-558"]
              and id(ctx_w["dois"]) == id_dois and id(ctx_w["curies"]) == id_curies
              and ctx_w["dois"] == ["10.1000/xyz123", "10.1000/abc999"] and ctx_w["curies"] == ["ZFIN:ZDB-GENE-980526-558"]
              and bw["unpaywall_crossref"]["status"] == "success" and bw["monarch"]["status"] == "no-match"
              and rd_w["items"][-1]["source_family"] == "web" and rd_w["items"][0]["source_family"] == "unpaywall_crossref"
              and rd_w["duplicates"] == [] and [s["family"] for s in rd_w["sources"]] == ["web", "unpaywall_crossref", "monarch"],
              repr((up_calls, mon_calls, [i["source_family"] for i in rd_w["items"]])))
        row_wo_led = json.dumps({k: v for k, v in web.items() if k != "web_locator"}, ensure_ascii=False)
        unres = wl_led["unresolved"]
        check("ADR-0084 texto web y URLs: unresolved[] ×2 con host / reason 'no-identifier-pattern' / title_web recortado a 120 (205 → 120) "
              "y SÓLO ahí viven títulos y URLs — fuera de row.web_locator la fila no contiene 'WEB TITLE' ni 'https://'; la llave fake "
              "JAMÁS aparece en la ronda (M.5); queries[] ×1 con la forma de web_locator.locate (provider_status 'success', state 'located', "
              "n_billable 1, cost.class 'proyección')",
              len(unres) == 2 and [u["reason"] for u in unres] == ["no-identifier-pattern"] * 2
              and [u["host"] for u in unres] == ["www.researchgate.net", "en.wikipedia.org"]
              and len(unres[0]["title_web"]) == 120 and unres[0]["round"] == 1 and unres[0]["requirement_ids"] == ["req-fff"]
              and "WEB TITLE" not in row_wo_led and "https://" not in row_wo_led
              and FAKE_KEY not in json.dumps(rd_w, ensure_ascii=False)
              and len(wl_led["queries"]) == 1 and wl_led["queries"][0]["provider_status"] == "success"
              and wl_led["queries"][0]["state"] == "located" and wl_led["queries"][0]["n_billable"] == 1
              and wl_led["queries"][0]["cost"]["class"] == "proyección" and wl_led["queries"][0]["round"] == 1
              and wl_led["queries"][0]["requirement_ids"] == ["req-fff"] and wl_led["queries"][0]["query_source"] == "council-directive:req-fff",
              repr([(u["host"], u["reason"], len(u["title_web"])) for u in unres]))
        ev_json = json.dumps(events, ensure_ascii=False)
        check("ADR-0084 (C.6/G.6) hook ctx.on_web_locate: UN payload por consulta ENVIADA con {round, provider, query_en, query_source, "
              "requirement_ids, provider_status, http_status, elapsed_s, throttle_wait_s, cache_hit, query_altered_by_provider, n_results, "
              "n_located, n_materialized, n_unresolved, located_ids[] (ids, NO URLs), hosts_unresolved[], cost_usd_projected, quota "
              "{state, n_after, cap}} — sin 'http' en todo el payload",
              len(events) == 1 and events[0]["round"] == 1 and events[0]["provider"] == "brave" and events[0]["query_en"] == "wt1a review"
              and events[0]["provider_status"] == "success" and events[0]["n_results"] == 7 and events[0]["n_located"] == 5
              and events[0]["n_materialized"] == 1 and events[0]["n_unresolved"] == 2
              and events[0]["located_ids"] == ["PMID:12345678", "10.1000/xyz123", "PMID:23456789", "ZFIN:ZDB-GENE-980526-558", "ENSDARG00000031420"]
              and events[0]["hosts_unresolved"] == ["www.researchgate.net", "en.wikipedia.org"]
              and events[0]["quota"] == {"state": "under-cap", "n_after": 1, "cap": 900} and events[0]["requirement_ids"] == ["req-fff"]
              and {"http_status", "elapsed_s", "throttle_wait_s", "cache_hit", "query_altered_by_provider", "cost_usd_projected",
                   "query_source"} <= set(events[0])
              and "http" not in ev_json.lower().replace("http_status", ""),
              repr(events[0]))
        check("ADR-0084 (B.5/G.10) cuota vía ctx.web_quota (firma db.web_locator_reserve): reservar ANTES de la red (provider 'brave', mes "
              "UTC, cap 900, sin record) y registrar DESPUÉS (record {n_results 7, cost 0.005}) — 2 llamadas exactas",
              len(qspy.calls) == 2 and qspy.calls[0]["provider"] == "brave" and qspy.calls[0]["cap"] == 900 and qspy.calls[0]["record"] is None
              and qspy.calls[0]["month"] == wl.month_utc()
              and qspy.calls[1]["record"] == {"n_results": 7, "cost": 0.005, "n_requests_extra": 0} and web["quota_hook"] == "ctx.web_quota",
              repr(qspy.calls))
        sp_web, sp_mon = sh.source_event_payload(web), sh.source_event_payload(bw["monarch"])
        rp_json = json.dumps(sh.round_event_payload(rd_w), ensure_ascii=False)
        check("ADR-0084 (C.7) source_event_payload ADITIVO: la fila web suma provider / n_queries / n_results / n_located / n_materialized / "
              "n_unresolved / n_already_present / cost_usd_projected / quota_state; la de monarch NO los gana; ni web_locator ni calls viajan; "
              "CERO URLs (regex https?://) en todo round_event_payload",
              {"provider": "brave", "n_queries": 1, "n_results": 7, "n_located": 5, "n_materialized": 1, "n_unresolved": 2,
               "n_already_present": 1, "quota_state": "under-cap"}.items() <= sp_web.items()
              and abs(sp_web["cost_usd_projected"] - 0.005) < 1e-9
              and not any(k in sp_mon for k in ("provider", "n_queries", "n_located", "n_materialized", "quota_state"))
              and "web_locator" not in sp_web and "calls" not in sp_web
              and len(re.findall(r"https?://", rp_json)) == 0,
              repr(sp_web))

        # ---- 5g. Europe PMC no halla NADA: located sí, candidatos no ----
        wspy2, espy2 = WebSpy(), EpmcSpy(recs={})
        fetch_paper.search_europepmc_ledger = espy2
        row_nf, items_nf = sh.run_source("web", plan_w, {"dois": [], "curies": [], "existing_ids": set(), "web_store": lambda k: None},
                                         30.0, tools={"web": wspy2})
        check("ADR-0084 (C.5) _resolve_one devuelve None para todo (y existing_ids VACÍO: PMID:23456789 ya no está presente → también va a "
              "EPMC): 0 ítems, fila 'no-match' con detail 'n_results=7 n_located=5 n_materialized=0', n_epmc_gets 3 == "
              "n_not_found_in_europepmc 3 (los TRES idents de literatura), feed_state 'not-found-in-europepmc', web_locator_state sigue "
              "'located' (URLs resueltas ≠ candidatos), quota 'not-enforced (no quota callable)' declarada (sin hook)",
              items_nf == [] and row_nf["status"] == "no-match" and row_nf["detail"] == "n_results=7 n_located=5 n_materialized=0"
              and row_nf["n_materialized"] == 0 and row_nf["n_not_found_in_europepmc"] == 3 and row_nf["n_epmc_gets"] == 3
              and espy2.calls == ["PMID:12345678", "DOI:10.1000/xyz123", "PMID:23456789"]
              and {l["id"]: l["feed_state"] for l in row_nf["web_locator"]["located"]}["PMID:12345678"] == "not-found-in-europepmc"
              and row_nf["web_locator_state"] == "located" and row_nf["n_found"] == 7
              and row_nf["quota_state"] == "not-enforced (no quota callable)" and row_nf["quota_hook"].startswith("absent"),
              repr((row_nf["status"], row_nf.get("detail"), row_nf["n_not_found_in_europepmc"])))

        # ---- 5h. WITT_WEB_MAX_QUERIES=1 con 3 directivas web ----
        dirs3 = [d for d in DIRECTIVES_C6 if d["family"] == "web"] + [
            {"requirement_id": "req-w2", "family": "web", "query_en": "wt1a podocyte review", "entities": [], "symbols": [],
             "evidence_kind": "web", "priority": "should", "requested_by": ["domain-knowledge-curator"], "refined_by_members": []},
            {"requirement_id": "req-w3", "family": "web", "query_en": "wt1a glomerulus review", "entities": [], "symbols": [],
             "evidence_kind": "web", "priority": "should", "requested_by": ["domain-knowledge-curator"], "refined_by_members": []}]
        plan3 = sh.build_search_plan(gq, g_ents, g_pass1, directives=dirs3)
        plan3["families"] = ["web"]
        _e8 = _env(WITT_WEB_MAX_QUERIES="1")
        wspy3, espy3 = WebSpy(), EpmcSpy()
        fetch_paper.search_europepmc_ledger = espy3
        row3, items3 = sh.run_source("web", plan3, {"dois": [], "curies": [], "web_store": lambda k: None}, 30.0, tools={"web": wspy3})
        _restore(_e8)
        check("ADR-0084 (C.3) WITT_WEB_MAX_QUERIES=1 con 3 directivas web (_inputs_for → 3 insumos): el proveedor se llamó UNA vez; calls[] "
              "= [success, skipped-cap, skipped-cap] con detail 'WITT_WEB_MAX_QUERIES=1 reached' y su requirement_id; "
              "n_queries_dropped_by_cap 2, n_queries 1 (queries[] sólo las enviadas), inputs_used conserva la firma COMPLETA (3), "
              "max_queries_source 'env:WITT_WEB_MAX_QUERIES'; la fila sigue 'success' con lo medido",
              len(wspy3.calls) == 1 and [c["status"] for c in row3["calls"]] == ["success", "skipped-cap", "skipped-cap"]
              and row3["calls"][1]["detail"] == "WITT_WEB_MAX_QUERIES=1 reached" and row3["calls"][1]["directive_requirement_ids"] == ["req-w2"]
              and row3["n_queries_dropped_by_cap"] == 2 and row3["n_queries"] == 1 and len(row3["web_locator"]["queries"]) == 1
              and row3["inputs_used"] == ["wt1a review", "wt1a podocyte review", "wt1a glomerulus review"]
              and row3["max_queries_source"] == "env:WITT_WEB_MAX_QUERIES" and row3["status"] == "success" and len(items3) == 1,
              repr(([c["status"] for c in row3["calls"]], row3["n_queries_dropped_by_cap"], row3["inputs_used"])))

        # ---- 5i. WITT_WEB_MAX_MATERIALIZE=1 y =0 con 3 PMIDs ----
        URLS3 = [{"url": f"https://pubmed.ncbi.nlm.nih.gov/{n}/", "title": f"WEB TITLE {n}", "host": "pubmed.ncbi.nlm.nih.gov",
                  "age": None, "page_age": None} for n in ("11111111", "22222222", "33333333")]
        RECS3 = {f"PMID:{n}": {"epmc_id": n, "source": "MED", "pmid": n, "pmcid": None, "doi": None, "title": f"EPMC {n}", "year": "2020",
                               "journal": "J", "is_oa": False, "abstract": None, "cited_by": 0} for n in ("11111111", "22222222", "33333333")}
        _e9 = _env(WITT_WEB_MAX_MATERIALIZE="1")
        wspy4, espy4 = WebSpy(results=URLS3), EpmcSpy(recs=RECS3)
        fetch_paper.search_europepmc_ledger = espy4
        row4, items4 = sh.run_source("web", plan_w, {"dois": [], "curies": [], "web_store": lambda k: None}, 30.0, tools={"web": wspy4})
        _restore(_e9)
        _e10 = _env(WITT_WEB_MAX_MATERIALIZE="0")
        wspy5, espy5 = WebSpy(results=URLS3), EpmcSpy(recs=RECS3)
        fetch_paper.search_europepmc_ledger = espy5
        row5, items5 = sh.run_source("web", plan_w, {"dois": [], "curies": [], "web_store": lambda k: None}, 30.0, tools={"web": wspy5})
        _restore(_e10)
        check("ADR-0084 (C.5) WITT_WEB_MAX_MATERIALIZE=1 con 3 PMIDs: UNA GET a EPMC (espy 1), 1 materializado + 2 'not-materialized (feed cap)', "
              "1 ítem, n_epmc_gets 1, max_materialize_source env; con =0 ('sólo localizar'): 0 GETs, los 3 'not-materialized (feed cap)', "
              "0 ítems, fila 'no-match' (midió y no materializó), n_located 3",
              espy4.calls == ["PMID:11111111"] and len(items4) == 1 and row4["n_materialized"] == 1 and row4["n_epmc_gets"] == 1
              and [l["feed_state"] for l in row4["web_locator"]["located"]] == ["materialized-same-round", "not-materialized (feed cap)",
                                                                                 "not-materialized (feed cap)"]
              and row4["max_materialize_source"] == "env:WITT_WEB_MAX_MATERIALIZE" and row4["status"] == "success"
              and espy5.calls == [] and items5 == [] and row5["status"] == "no-match" and row5["n_located"] == 3 and row5["n_epmc_gets"] == 0
              and [l["feed_state"] for l in row5["web_locator"]["located"]] == ["not-materialized (feed cap)"] * 3,
              repr((espy4.calls, [l["feed_state"] for l in row4["web_locator"]["located"]], row5["status"])))

        # ---- 5j. cortacircuito de autenticación por ronda ----
        wspy6, espy6 = WebSpy(plan=[AUTH_ROW]), EpmcSpy()
        fetch_paper.search_europepmc_ledger = espy6
        row6, items6 = sh.run_source("web", plan3, {"dois": [], "curies": [], "web_store": lambda k: None}, 30.0, tools={"web": wspy6})
        q6 = row6["web_locator"]["queries"]
        check("ADR-0084 (C.5) CORTACIRCUITO auth: la 1ª consulta devuelve 'auth (HTTP 401)' → el proveedor NO se vuelve a llamar (spy 1), "
              "las 2 restantes quedan provider_status 'skipped-cap' con state 'skipped-cap (auth failed in this round (no retry))', cero "
              "GETs a EPMC, fila 'error' con error 'auth (HTTP 401)', web_locator_state 'error: auth (HTTP 401)', 0 ítems; "
              "web_locator.is_auth_error True en la primera",
              len(wspy6.calls) == 1 and [q["provider_status"] for q in q6] == ["error", "skipped-cap", "skipped-cap"]
              and q6[1]["state"] == q6[2]["state"] == "skipped-cap (auth failed in this round (no retry))"
              and q6[1]["detail"] == sh.WEB_AUTH_CIRCUIT_DETAIL == "auth failed in this round (no retry)"
              and wl.is_auth_error(q6[0]) and espy6.calls == [] and row6["status"] == "error" and row6["error"] == "auth (HTTP 401)"
              and row6["web_locator_state"] == "error: auth (HTTP 401)" and items6 == [] and row6["n_found"] is None
              and [c["status"] for c in row6["calls"]] == ["error", "skipped-cap", "skipped-cap"],
              repr(([q["provider_status"] for q in q6], row6.get("error"))))

        # ---- 5k. la cuota mensual niega: skipped-cap con detail, CERO red ----
        wspy7, qspy7, ev7 = WebSpy(), QuotaSpy(grant=False), []
        fetch_paper.search_europepmc_ledger = EpmcSpy()
        row7, items7 = sh.run_source("web", plan_w, {"dois": [], "curies": [], "web_quota": qspy7, "on_web_locate": ev7.append,
                                                     "web_store": lambda k: None}, 30.0, tools={"web": wspy7})
        check("ADR-0084 (B.5/C.5) quota_fn niega: fila 'skipped-cap' con detail 'monthly cap WITT_WEB_MONTHLY_CAP=900 reached (…)', el "
              "proveedor NO se llama (spy 0), quota_state 'cap-reached', web_locator_state 'skipped-cap (monthly cap …)', contadores null, "
              "0 ítems; el latido SÍ se emite (una consulta declarada) con provider_status 'skipped-cap'; _family_status hereda 'skipped-cap' "
              "cuando todas las consultas lo son",
              row7["status"] == "skipped-cap" and row7["detail"].startswith("monthly cap WITT_WEB_MONTHLY_CAP=900 reached")
              and wspy7.calls == [] and row7["quota_state"] == "cap-reached"
              and row7["web_locator_state"].startswith("skipped-cap (monthly cap") and row7["n_found"] is None and row7["n_results"] is None
              and items7 == [] and len(ev7) == 1 and ev7[0]["provider_status"] == "skipped-cap"
              and sh._family_status([], ["skipped-cap"] * 2) == "skipped-cap" and sh._family_status([], ["error", "skipped-cap"]) == "error",
              repr((row7["status"], row7.get("detail"), row7["web_locator_state"])))

        # ---- 5l. proveedor que lanza / que declara skipped-budget / ronda sin presupuesto ----
        wspy8 = WebSpy(plan=[RuntimeError("boom")])
        plan8 = dict(p_on)
        plan8["families"] = ["web", "alliance_orthologs"]
        rd8 = sh.run_round(plan8, 1, 30.0, tools={"web": wspy8, "alliance_orthologs": fake_ok}, ctx={"dois": [], "curies": [], "web_store": lambda k: None})
        b8 = {s["family"]: s for s in rd8["sources"]}
        wspy9 = WebSpy(plan=[BUDGET_ROW])
        row9, _ = sh.run_source("web", plan_w, {"dois": [], "curies": [], "web_store": lambda k: None}, 30.0, tools={"web": wspy9})
        wspy10 = WebSpy()
        rd10 = sh.run_round(plan_w, 1, 0.1, tools={"web": wspy10, "unpaywall_crossref": fake_unpaywall, "monarch": fake_monarch},
                            ctx={"dois": [], "curies": [], "web_store": lambda k: None})
        check("ADR-0084 (M.1 §6 no-hang) proveedor que LANZA: fila web 'error' con 'RuntimeError: boom' (web_locator.locate lo envuelve) y la "
              "siguiente familia corre ('success'); proveedor que declara 'skipped-budget' → la familia lo hereda y web_locator_state "
              "'skipped-budget (…)'; ronda sin presupuesto (0.1 s < MIN_SOURCE_BUDGET_S) → web 'skipped-budget' 'round budget' SIN llamar "
              "al proveedor (spy 0)",
              b8["web"]["status"] == "error" and "RuntimeError: boom" in b8["web"]["error"] and b8["alliance_orthologs"]["status"] == "success"
              and b8["web"]["web_locator_state"].startswith("error: RuntimeError: boom")
              and row9["status"] == "skipped-budget" and row9["web_locator_state"].startswith("skipped-budget (")
              and {s["family"]: s["status"] for s in rd10["sources"]}["web"] == "skipped-budget"
              and "round budget" in {s["family"]: s for s in rd10["sources"]}["web"]["detail"] and wspy10.calls == [],
              repr((b8["web"].get("error"), row9["web_locator_state"], wspy10.calls)))

        # ---- 5m. kill-switch EXPLÍCITO con llave presente: cero red, cero cuota, cero latidos ----
        _e11 = _env(WITT_WEB_LOCATOR="off")
        wspy11, qspy11, ev11 = WebSpy(), QuotaSpy(), []
        row11, items11 = sh.run_source("web", p_call, {"dois": [], "curies": [], "web_quota": qspy11, "on_web_locate": ev11.append,
                                                        "web_store": lambda k: None}, 30.0, tools={"web": wspy11})
        fa11 = sh.family_available("web")
        _restore(_e11)
        row_tu, _ = sh.run_source("tooluniverse", p_call, {"dois": [], "curies": []}, 30.0)   # la fila MÍNIMA de una familia con fn None
        check("ADR-0084 (L, corrector) kill-switch WITT_WEB_LOCATOR=off CON llave (plan del llamador con web): la fila es la MÍNIMA de 7d9ce15 — "
              "'tool-unavailable' con detail 'tool-unavailable (ADR-0084)' y EXACTAMENTE el keyset de una familia con fn None (tooluniverse); "
              "SIN provider/n_queries/web_locator/quota_hook; proveedor 0 llamadas, cuota 0 llamadas, 0 latidos, 0 ítems, contadores null; "
              "family_available False con el literal de 7d9ce15",
              row11["status"] == "tool-unavailable" and row11["detail"] == "tool-unavailable (ADR-0084)"
              and set(row11) == set(row_tu) and not any(k in row11 for k in ("provider", "n_queries", "web_locator", "quota_hook", "web_locator_state"))
              and wspy11.calls == [] and qspy11.calls == [] and ev11 == [] and items11 == [] and row11["n_found"] is None
              and fa11 == (False, "tool-unavailable (ADR-0084)"),
              repr((row11["status"], row11.get("detail"), sorted(row11), len(ev11))))
        # ---- 5m-bis (corrector). OFF + web nombrada en WITT_SEARCH_DEFAULT_FAMILIES: el plan y la fila son los de 7d9ce15 ----
        _e11b = _env(WITT_WEB_LOCATOR="off", WITT_SEARCH_DEFAULT_FAMILIES="alliance_orthologs,string,web", WITT_WEB_TEST_QUERY="probe query")
        p_offenv = sh.build_search_plan(gq, g_ents, g_pass1)
        wspy11b, qspy11b, ev11b = WebSpy(), QuotaSpy(), []
        rd11b = sh.run_round(p_offenv, 1, 30.0, tools={"web": wspy11b, "alliance_orthologs": fake_ok, "string": fake_no_ids},
                             ctx={"dois": [], "curies": [], "web_quota": qspy11b, "on_web_locate": ev11b.append})
        _restore(_e11b)
        _e11c = _env(WITT_WEB_LOCATOR=None, BRAVE_API_KEY="", WITT_SEARCH_DEFAULT_FAMILIES="alliance_orthologs,string,web")
        p_offenv2 = sh.build_search_plan(gq, g_ents, g_pass1)
        row11c, _ = sh.run_source("web", p_offenv2, {"dois": [], "curies": []}, 30.0, tools={"web": WebSpy()})
        _restore(_e11c)
        row11b = {s["family"]: s for s in rd11b["sources"]}["web"]
        check("ADR-0084 (L, corrector) OFF + web nombrada en WITT_SEARCH_DEFAULT_FAMILIES (con y sin WITT_WEB_TEST_QUERY): el plan es el de 7d9ce15 — "
              "families en el ORDEN de la env (web NO se mueve al frente), SIN families_order_rule (ni en plan_event_payload), queries.web SIN "
              "entered_by y con la query de pass1 (la consulta de prueba NO manda sin localizador); la ronda deja la fila MÍNIMA 'tool-unavailable "
              "(ADR-0084)' en la posición de la env, cero llamadas, cero cuota, cero latidos; off DERIVADO (sin llave) → la MISMA fila mínima con "
              "el MISMO literal de 7d9ce15 (la CAUSA 'BRAVE_API_KEY unset' viaja en frozen.web_locator.state, no en la fila)",
              p_offenv["families"] == ["alliance_orthologs", "string", "web"] and "families_order_rule" not in p_offenv
              and "families_order_rule" not in sh.plan_event_payload(p_offenv)
              and p_offenv["queries"]["web"] == {"inputs": "free-query", "query": g_pass1, "query_source": "pass1_query_en"}
              and [s["family"] for s in rd11b["sources"]] == ["alliance_orthologs", "string", "web"]
              and row11b["status"] == "tool-unavailable" and row11b["detail"] == "tool-unavailable (ADR-0084)"
              and set(row11b) == set(row_tu) | {"round", "over_budget"} and wspy11b.calls == [] and qspy11b.calls == [] and ev11b == []
              and p_offenv2["families"] == ["alliance_orthologs", "string", "web"] and "families_order_rule" not in p_offenv2
              and row11c["status"] == "tool-unavailable" and row11c["detail"] == wl.UNAVAILABLE_OFF == "tool-unavailable (ADR-0084)"
              and set(row11c) == set(row_tu),
              repr((p_offenv["families"], p_offenv["queries"]["web"], row11b.get("detail"), row11c.get("detail"))))

        # ---- 5n. presupuesto de la familia por env y sin insumos ----
        _e12 = _env(WITT_WEB_BUDGET_S="5")
        fb_env = sh.family_budget_s(sh.SEARCH_DISPATCH["web"])
        plan12 = dict(p_on)
        plan12["families"] = ["web"]
        wspy12 = WebSpy()
        fetch_paper.search_europepmc_ledger = EpmcSpy()
        rd12 = sh.run_round(plan12, 1, 30.0, tools={"web": wspy12}, ctx={"dois": [], "curies": [], "web_store": lambda k: None})
        _restore(_e12)
        _e13 = _env(WITT_WEB_BUDGET_S="999")
        fb_clamp = sh.family_budget_s(sh.SEARCH_DISPATCH["web"])
        _restore(_e13)
        _e14 = _env(WITT_WEB_BUDGET_S="abc")
        fb_bad = sh.family_budget_s(sh.SEARCH_DISPATCH["web"])
        _restore(_e14)
        # sin entidades, sin EN y sin término anatómico en la pregunta: _free_query no produce nada (la pregunta cruda JAMÁS se usa)
        plan_ni = sh.build_search_plan("What is known about this?", [], None, families=["web"])
        wspy13 = WebSpy()
        row13, items13 = sh.run_source("web", plan_ni, {"dois": [], "curies": []}, 30.0, tools={"web": wspy13})
        check("ADR-0084 family_budget_s: default (30.0, 'default-unset:WITT_WEB_BUDGET_S'); WITT_WEB_BUDGET_S=5 → (5.0, 'env:…') y run_round "
              "acota la familia a 5.0 s (budget_s de la fila); 999 → clamp 120.0; 'abc' → 30.0 'default-invalid-env'; las filas sin "
              "budget_env → ('table'); sin insumo (sin entidades, sin EN, sin anatomía en la pregunta) → queries.web.query None → "
              "'not-requested' 'no English query (nothing to search)' sin llamar",
              sh.family_budget_s(sh.SEARCH_DISPATCH["web"]) == (30.0, "default-unset:WITT_WEB_BUDGET_S")
              and fb_env == (5.0, "env:WITT_WEB_BUDGET_S") and rd12["sources"][0]["budget_s"] == 5.0 and len(wspy12.calls) == 1
              and fb_clamp == (120.0, "env:WITT_WEB_BUDGET_S") and fb_bad == (30.0, "default-invalid-env:WITT_WEB_BUDGET_S")
              and sh.family_budget_s(sh.SEARCH_DISPATCH["monarch"]) == (30.0, "table")
              and row13["status"] == "not-requested" and row13["detail"] == sh.WEB_NO_QUERY_DETAIL and wspy13.calls == [] and items13 == [],
              repr((fb_env, rd12["sources"][0]["budget_s"], fb_clamp, fb_bad, row13["status"])))
        # ---- 5o (corrector). dedup por PAPER dentro de la familia · trampa del top hit · DOI con sintaxis EPMC · DOI del registro UNA vez ----
        URLS_SAME = [{"url": "https://pubmed.ncbi.nlm.nih.gov/15982647/", "title": "WEB TITLE pubmed", "host": "pubmed.ncbi.nlm.nih.gov",
                      "age": None, "page_age": None},
                     {"url": "https://www.ncbi.nlm.nih.gov/pmc/articles/pmc2688018/", "title": "WEB TITLE pmc (lowercase)", "host": "www.ncbi.nlm.nih.gov",
                      "age": None, "page_age": None},
                     {"url": "https://doi.org/10.1242/dev.02071/", "title": "WEB TITLE doi (trailing slash)", "host": "doi.org", "age": None,
                      "page_age": None},
                     {"url": "https://doi.org/10.1002/(SICI)1097-0177(199906)215:2%3C143::AID-DVDY5%3E3.0.CO;2-K", "title": "WEB TITLE sici",
                      "host": "doi.org", "age": None, "page_age": None},
                     {"url": "https://pubmed.ncbi.nlm.nih.gov/77777777/", "title": "WEB TITLE 777", "host": "pubmed.ncbi.nlm.nih.gov",
                      "age": None, "page_age": None}]
        REC_SAME = {"epmc_id": "15982647", "source": "MED", "pmid": "15982647", "pmcid": "PMC2688018", "doi": "10.1242/DEV.02071",
                    "title": "EPMC one paper", "year": "2005", "journal": "Development", "is_oa": True, "abstract": "abstract", "cited_by": 9}
        REC_OTHER = dict(REC_SAME, epmc_id="99999999", pmid="99999999", pmcid=None, doi=None, title="EPMC another paper")
        wspy15, espy15 = WebSpy(results=URLS_SAME), EpmcSpy(recs={"PMID:15982647": REC_SAME, "PMID:77777777": REC_OTHER})
        fetch_paper.search_europepmc_ledger = espy15
        ctx15 = {"dois": [], "curies": [], "web_store": lambda k: None}
        rd15 = sh.run_round(plan_w, 1, 30.0, tools={"web": wspy15, "unpaywall_crossref": fake_unpaywall, "monarch": fake_monarch}, ctx=ctx15)
        row15 = {s["family"]: s for s in rd15["sources"]}["web"]
        loc15 = {l["id"]: l for l in row15["web_locator"]["located"]}
        check("ADR-0084 (corrector) dedup por PAPER en la familia: pubmed 15982647 + PMC (minúsculas) + doi.org (con '/' final) del MISMO registro → "
              "UNA GET a EPMC (PMID:15982647), 1 candidato, PMC2688018 y 10.1242/dev.02071 'already-present (dup of PMID:15982647)' con "
              "same_paper {layer 'family', matched_key PMCID:PMC2688018 / DOI:10.1242/dev.02071}; n_same_paper_dups 2; el SICI viajó a EPMC ENTRE "
              "COMILLAS (epmc_query_quoted True, DOI:\"…\") y cayó not-found; PMID:77777777 devolvió OTRO registro → 'error: europepmc record "
              "mismatch (PMID:99999999 != PMID:77777777)', n_epmc_record_mismatch 1, NO candidato; n_epmc_gets 3; ctx.dois lleva el DOI UNA sola "
              "vez y en la forma del REGISTRO ('10.1242/DEV.02071', la misma que cosecha run_round) + el SICI normalizado; 1 ítem",
              espy15.calls == ["PMID:15982647", "DOI:10.1002/(sici)1097-0177(199906)215:2<143::aid-dvdy5>3.0.co;2-k", "PMID:77777777"]
              and espy15.queries[1] == 'DOI:"10.1002/(sici)1097-0177(199906)215:2<143::aid-dvdy5>3.0.co;2-k"'
              and row15["n_materialized"] == 1 and row15["n_same_paper_dups"] == 2 and row15["n_epmc_gets"] == 3
              and row15["n_epmc_record_mismatch"] == 1 and row15["n_not_found_in_europepmc"] == 1
              and loc15["PMID:15982647"]["feed_state"] == "materialized-same-round"
              and loc15["PMC2688018"]["feed_state"] == "already-present (dup of PMID:15982647)"
              and loc15["PMC2688018"]["same_paper"] == {"of": "PMID:15982647", "matched_key": "PMCID:PMC2688018", "layer": "family",
                                                        "rule": sh.WEB_SAME_PAPER_RULE}
              and loc15["10.1242/dev.02071"]["feed_state"] == "already-present (dup of PMID:15982647)"
              and loc15["10.1242/dev.02071"]["same_paper"]["matched_key"] == "DOI:10.1242/dev.02071"
              and loc15["10.1002/(sici)1097-0177(199906)215:2<143::aid-dvdy5>3.0.co;2-k"]["epmc_query_quoted"] is True
              and loc15["10.1002/(sici)1097-0177(199906)215:2<143::aid-dvdy5>3.0.co;2-k"]["feed_state"] == "not-found-in-europepmc"
              and loc15["PMID:77777777"]["feed_state"] == "error: europepmc record mismatch (PMID:99999999 != PMID:77777777)"
              and wl.feed_state_in_vocabulary(loc15["PMID:77777777"]["feed_state"])
              and ctx15["dois"] == ["10.1002/(sici)1097-0177(199906)215:2<143::aid-dvdy5>3.0.co;2-k", "10.1242/DEV.02071"]
              and len([i for i in rd15["items"] if i.get("source_family") == "web"]) == 1,
              repr((espy15.calls, espy15.queries, [(l["id"], l["feed_state"]) for l in row15["web_locator"]["located"]], ctx15["dois"])))
        # presupuesto de la familia → timeout de EPMC acotado (MIN_CALL_TIMEOUT_S <= t <= restante)
        wspy16, espy16 = WebSpy(results=URLS3), EpmcSpy(recs=RECS3)
        fetch_paper.search_europepmc_ledger = espy16
        row16, _ = sh.run_source("web", plan_w, {"dois": [], "curies": [], "web_store": lambda k: None}, 1.0, tools={"web": wspy16})
        check("ADR-0084 (M.1, corrector) la GET a Europe PMC usa el presupuesto RESTANTE de la familia: con budget_s 1.0 los 3 idents viajaron con "
              "timeout 0.5 <= t <= 1.0 (antes: HTTP_TIMEOUT_S 30 s por ident, 6 idents podían retener la ronda 180 s); epmc_timeout_s declarado en "
              "cada located",
              len(espy16.timeouts) == 3 and all(sh.MIN_CALL_TIMEOUT_S <= t <= 1.0 for t in espy16.timeouts)
              and all(l.get("epmc_timeout_s") == t for l, t in zip(row16["web_locator"]["located"], espy16.timeouts)),
              repr(espy16.timeouts))
    finally:
        fetch_paper.search_europepmc_ledger = _resolve_real
        _restore(old)

    check("el smoke corrió 100% OFFLINE — MEDIDO: urllib.request.urlopen bloqueado y contado == 0 (fakes/parches para toda familia)",
          _NET_CALLS == [], f"calls={_NET_CALLS[:5]}")
    _urlreq.urlopen = _urlopen_real
    n_pass, n_total = sum(CHECKS), len(CHECKS)
    print(f"\n{n_pass}/{n_total} PASS")
    return 0 if n_pass == n_total else 1


_path_b_module_real = ap.path_b

if __name__ == "__main__":
    sys.exit(main())

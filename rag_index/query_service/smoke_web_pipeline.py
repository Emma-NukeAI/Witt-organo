"""smoke_web_pipeline.py — gate offline de la Ruta B con la familia `web` como LOCALIZADOR (ADR-0084, rebanada W4).

Cubre lib/answer_pipeline.py (Decision D) de punta a punta por `path_b_bundle(search_plan=, web_quota=)`: el plan con la
directiva web (web PRIMERA), el harness (W3 `_run_web_family`), el tool Brave REAL cargado por ruta (W1) con su ÚNICA
costura de red `_get` parcheada, el resolutor de tabla REAL (W2), Europe PMC FALSO (`fetch_paper._resolve_one`) y el
`fetch_external` REAL sobre un tempdir (la caché del repo no se toca):
  * D.1 admisión NATIVE-FIRST: el PMID que EPMC trajo Y la web señaló queda en selection.duplicates[] con source_family
    'web' y en web_locator.located[].feed_state 'already-present (dup of <id>)'; selection.pool_admission_rule presente.
  * D.2 desempate native-before-web-located en _select_top_n (unit + pipeline: 5 nativos + 1 web con n=5 → web
    not_selected, n_located_not_selected 1); sin web la clave es la de ADR-0078 byte a byte (golden de referencia).
  * D.3 el paper web-localizado: source 'europepmc', source_family 'web', identifier_provenance 'web-located:<regla>',
    search_rec/título de EPMC (jamás el título del buscador), url CANÓNICA (≠ la hallada), located_via / located_from
    (sin URL) / search_rec_source; fetched.found True (o False con stub → paper sin pasaje).
  * D.4 block['web_locator'] completo (estado, proveedor, contadores, queries/located/unresolved, gap_flags_typed, cost
    PROYECCIÓN, quota, encabezado de web_locator.frozen_header) en las 5 situaciones: located · not-requested (no web
    directive) · kill-switch WITT_WEB_LOCATOR=off · tool-unavailable (sin BRAVE_API_KEY) · cache-hit del tool.
  * D.5 hooks: web_quota= (reserva ANTES / registro DESPUÉS; None → 'not-enforced'), on_stage recibe 'web.locate' UNA vez
    por consulta enviada (ids y hosts, jamás URLs), 0 eventos web sin web; path_b_event_payload aditivo (n_web_located,
    n_web_unresolved, located_from sólo en el paper web) SIN URLs halladas.
  * n_results_by_source.web == 0 SIEMPRE (0 papers source 'web'); los web-localizados cuentan en europepmc.
  * El read-cache abstract-only de fetch_external NO se envenena: fetch_external corre SÓLO tras la última ronda y sólo
    para los seleccionados (spy con reloj); el paper web OA baja texto completo sin 'full_text_skipped_reason' — y el
    control POSITIVO en otro tempdir muestra cómo se vería el envenenamiento ('cache-hit-abstract-only').
  * Doctrina: ni 'WEB TITLE', ni la description del buscador, ni la URL hallada, ni la llave fake aparecen fuera de
    web_locator / la fila del harness; las listas blancas del prompt (runs._PROMPT_PATH_B_TOP / _PROMPT_PAPER_KEYS) no
    incluyen web_locator / url / located_from y _compact_evidence no proyecta nada del localizador.
  * mcp_cache del repo byte-idéntico antes/después; urlopen bloqueado y contado == 0.

100% offline: cero red, cero modelo, cero BD (runs se importa sólo por sus constantes). Exit 0 = todo PASS.

Corre (máscara de siempre):  python rag_index/query_service/smoke_web_pipeline.py
"""
import json
import os
import re
import sys
import tempfile
import time
import urllib.parse
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
os.environ.setdefault("BRAVE_API_KEY", "")
os.environ.setdefault("WITT_RUN_ORIGIN", "smoke")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

_cache_env = (os.environ.get("WITT_MCP_CACHE_DIR") or "").strip()
TMP = Path(_cache_env) if _cache_env else Path(tempfile.mkdtemp(prefix="witt-smoke-web-pipeline-"))
TMP.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("WITT_BACKEND_DB_URL", f"sqlite:///{(TMP / 'smoke_web_pipeline.db').as_posix()}")

# ---- cero red: urlopen bloqueado y CONTADO durante TODO el smoke (patrón smoke_search_harness) -------------------------
import urllib.request as _urlreq  # noqa: E402

_NET_CALLS = []
_urlopen_real = _urlreq.urlopen


def _urlopen_blocked(*a, **kw):
    import traceback as _tb
    frames = [f for f in _tb.extract_stack()[:-1] if "urllib" not in f.filename.replace("\\", "/")]
    who = f"{Path(frames[-1].filename).name}:{frames[-1].lineno}:{frames[-1].name}" if frames else "?"
    req = a[0] if a else kw.get("url")
    url = getattr(req, "full_url", None) or str(req)
    _NET_CALLS.append(f"{who} -> {url[:120]}")
    raise RuntimeError("network blocked by smoke_web_pipeline (offline gate)")


_urlreq.urlopen = _urlopen_blocked

from lib import answer_pipeline as ap  # noqa: E402
from lib import search_harness as sh  # noqa: E402
from lib import web_locator as wl  # noqa: E402
from lib import fetch_paper  # noqa: E402
from lib import verify_output as vo  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


def _env(**kw):
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


def _snapshot(d):
    return {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in d.iterdir() if p.is_file()} if d.exists() else {}


def _j(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def _urls_in(text):
    return re.findall(r"https?://[^\s\"'\\]+", text)


FAKE_KEY = "fake-brave-key-smoke-web-pipeline-never-in-output"
WEB_TEXT = "DESCRIPTION-WEB-TEXT-NEVER-EVIDENCE"      # description del buscador: el tool la corta en la SALIDA (W1 A.3)
Q = "¿Es wt1a necesario para el podocito del pronefros del pez cebra?"
PASS1 = "wt1a pronephros glomerulus podocyte"
MCP_CACHE = ROOT / "mcp_cache"
SNAP_BEFORE = _snapshot(MCP_CACHE)


def web_directive(rid, query_en):
    return {"requirement_id": rid, "family": "web", "query_en": query_en, "entities": [], "symbols": [],
            "evidence_kind": "web", "priority": "should", "requested_by": ["domain-knowledge-curator"],
            "refined_by_members": []}


def _res(url, title, host=None, **extra):
    """Un resultado de Brave con la forma documentada (title + description + extra_snippets + meta_url)."""
    r = {"title": title, "url": url, "description": WEB_TEXT + " " + title, "extra_snippets": [WEB_TEXT],
         "age": None, "page_age": None, "language": "en", "family_friendly": True,
         "meta_url": {"hostname": host or urllib.parse.urlparse(url).hostname}}
    r.update(extra)
    return r


def _rec(pmid, pmcid=None, doi=None, is_oa=False, title=None):
    return {"epmc_id": pmid, "source": "MED", "pmid": pmid, "pmcid": pmcid, "doi": doi,
            "title": title or f"EPMC record {pmid}", "year": "2021", "journal": "Dev Biol", "is_oa": is_oa,
            "abstract": f"wt1a pronephros podocyte abstract (Europe PMC) {pmid}", "cited_by": 3}


# ---- fakes: la ÚNICA costura de red del tool Brave (W1 `_get`), Europe PMC (W3 `_resolve_one`), texto completo ------
class FakeNet:
    """Sirve por `q` de la URL una respuesta Brave con la forma documentada; cuenta las GETs y si viajó la llave."""

    def __init__(self):
        self.calls, self.by_query = [], {}

    def __call__(self, url, timeout=None, with_headers=True, api_key=None):
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        q = (qs.get("q") or [""])[0]
        self.calls.append({"q": q, "timeout": timeout, "key_in_header": api_key == FAKE_KEY, "key_in_url": FAKE_KEY in url})
        results = self.by_query.get(q)
        if results is None:
            raise AssertionError(f"smoke: unexpected Brave query {q!r}")
        js = {"type": "search", "query": {"original": q, "altered": None, "more_results_available": False},
              "web": {"type": "search", "results": [dict(r) for r in results]}}
        return (js, None) if with_headers else js


class EpmcSpy:
    def __init__(self, recs):
        self.calls, self.recs = [], dict(recs)

    def __call__(self, ident):
        self.calls.append(ident)
        rec = self.recs.get(ident)
        return rec, {"source": "europepmc", "status": "success" if rec else "no-match", "query_sent": ident,
                     "n_found": 1 if rec else 0, "n_returned": 1 if rec else 0, "elapsed_s": 0.01}


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


NATIVE = {"recs": [], "spy": None, "epmc_timeouts": [], "epmc_queries": []}


def fake_search_europepmc_ledger(query, n=5, sort=None, synonym=True, timeout=None):
    ident = sh.epmc_ident_of_query(query)
    if ident is not None and NATIVE["spy"] is not None:
        # corrector ADR-0084: la RONDA materializa por fetch_paper.search_europepmc_ledger(<consulta por ident>, n=1, timeout=<presupuesto
        # restante de la familia>) — el spy de Europe PMC sirve por ident y el timeout MEDIDO queda registrado
        NATIVE["epmc_timeouts"].append(timeout)
        NATIVE["epmc_queries"].append(query)
        rec, led = NATIVE["spy"](ident)
        return ([dict(rec)] if rec else []), led
    recs = [dict(r) for r in NATIVE["recs"]]
    return recs, {"source": "europepmc", "status": "success" if recs else "no-match", "query_sent": query,
                  "n_found": len(recs), "n_returned": len(recs), "elapsed_s": 0.01, "sort": "RELEVANCE",
                  "synonym": True, "throttle": "net_throttle", "throttle_slept_s": 0.0, "contact": "unset"}


_real_fetch_external = fetch_paper.fetch_external
FAKE_XML = ("<article><body><sec><title>Results</title><p>wt1a is required in the pronephric podocyte lineage; "
            "glomerulus formation fails in mutants.</p></sec></body></article>")


class FetchSpy:
    """fetch_external REAL sobre un tempdir (raw_paper_* jamás en la caché del repo) + reloj por llamada; found=False →
    stub que declara el paper sin pasaje."""

    def __init__(self, cache_dir, found=True):
        self.calls, self.cache_dir, self.found = [], Path(cache_dir), found
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def __call__(self, ident, want_full_text=True, cache_dir=None, ttl_days=None):
        self.calls.append({"ident": ident, "want_full_text": want_full_text, "t": time.monotonic()})
        if not self.found:
            return {"found": False, "note": "offline stub (smoke_web_pipeline): paper without passage"}
        return _real_fetch_external(ident, want_full_text=want_full_text, cache_dir=self.cache_dir)


def run_scenario(tag, directives, web_results, native_recs, epmc_recs, n=5, existing_ids=None, quota=None,
                 fetch_found=True, env=None, web_query=None):
    """Un path_b_bundle completo con los fakes → (block, events, spies)."""
    cache_web, cache_fetch = TMP / f"brave-{tag}", TMP / f"fetch-{tag}"
    cache_web.mkdir(parents=True, exist_ok=True)
    old = _env(WITT_MCP_CACHE_DIR=str(cache_web), WITT_SEARCH_DEFAULT_FAMILIES="europepmc", WITT_WEB_MIN_INTERVAL_S="0",
               WITT_SEARCH_ROUNDS_CAP=None, WITT_SEARCH_ROUND_BUDGET_S=None, WITT_WEB_MAX_QUERIES=None,
               WITT_WEB_MAX_MATERIALIZE=None, WITT_WEB_MONTHLY_CAP=None, **(env or {}))
    net = FakeNet()
    if web_query is not None:
        net.by_query[web_query] = web_results
    espy, fspy = EpmcSpy(epmc_recs), FetchSpy(cache_fetch, found=fetch_found)
    NATIVE["recs"], NATIVE["spy"], NATIVE["epmc_timeouts"], NATIVE["epmc_queries"] = list(native_recs), espy, [], []
    mod, _fn, _detail = wl._load_brave_tool()
    real_get = mod._get
    mod._get = net
    fetch_paper._resolve_one = espy
    fetch_paper.fetch_external = fspy
    events = []
    t_events = {}

    def on_stage(name, payload):
        events.append((name, payload))
        t_events.setdefault(name, []).append(time.monotonic())

    try:
        plan = sh.build_search_plan(Q, ["wt1a"], PASS1, directives=directives)
        blk = ap.path_b_bundle(Q, entities=["wt1a"], n=n, triggered_by=["competence"], search_plan=plan, on_stage=on_stage,
                               existing_ids=list(existing_ids or []), web_quota=quota)
    finally:
        mod._get = real_get
        _restore(old)
    return {"plan": plan, "block": blk, "events": events, "t_events": t_events, "net": net, "epmc": espy, "fetch": fspy,
            "cache_fetch": cache_fetch, "cache_web": cache_web, "epmc_timeouts": list(NATIVE["epmc_timeouts"]),
            "epmc_queries": list(NATIVE["epmc_queries"])}


def main():
    _resolve_real, _epmc_real = fetch_paper._resolve_one, fetch_paper.search_europepmc_ledger
    _xml_real = fetch_paper._full_text_xml
    fetch_paper.search_europepmc_ledger = fake_search_europepmc_ledger
    fetch_paper._full_text_xml = lambda pmcid: FAKE_XML if pmcid else None
    ON = {"WITT_WEB_LOCATOR": "brave", "BRAVE_API_KEY": FAKE_KEY}
    try:
        # =============================== S1 · 'located' de punta a punta ===============================================
        Q1 = "wt1a review S1"
        WEB1 = [
            _res("https://pubmed.ncbi.nlm.nih.gov/33333333/?dopt=Abstract", "WEB TITLE pubmed 333 (never evidence)"),
            _res("https://doi.org/10.1000/web444", "WEB TITLE doi 444"),
            _res("https://pubmed.ncbi.nlm.nih.gov/11111111/", "WEB TITLE pubmed 111 already native"),
            _res("https://www.researchgate.net/publication/777_wt1a", "WEB TITLE researchgate " + "R" * 182),   # 205 chars → title_web 120
            _res("https://doi.org/10.1000/notfound", "WEB TITLE doi not in EPMC"),
            _res("https://pubmed.ncbi.nlm.nih.gov/55555555/", "WEB TITLE pubmed 555 already in run"),
        ]
        NAT1 = [_rec("11111111", pmcid="PMC111", doi="10.1000/nat111", is_oa=True, title="Native EPMC 111"),
                _rec("22222222", title="Native EPMC 222")]
        REC444 = _rec("44444444", pmcid="PMC444", doi="10.1000/web444", is_oa=True, title="EPMC record for web-located DOI 444")
        # el spy de Europe PMC sirve a la RONDA (idents en forma EPMC del localizador: PMID:/DOI:) y a fetch_external (por
        # evidence_id, también los nativos): un mismo índice, dos llamadores — como en producción
        EP1 = {"PMID:33333333": _rec("33333333", title="EPMC record for web-located 333"),
               "DOI:10.1000/web444": REC444, "PMID:44444444": REC444,
               "PMID:11111111": NAT1[0], "PMID:22222222": NAT1[1], "PMID:55555555": _rec("55555555")}
        qspy1 = QuotaSpy()
        s1 = run_scenario("s1", [web_directive("req-w1", Q1)], WEB1, NAT1, EP1, n=5, existing_ids=["PMID:55555555", "CORPUS-2026-0003#c000"],
                          quota=qspy1, env=ON, web_query=Q1)
        blk, ev, plan = s1["block"], s1["events"], s1["plan"]
        wlb = blk["web_locator"]
        papers = blk["papers"]
        web_papers = [p for p in papers if p.get("source_family") == "web"]
        by_eid = {p["evidence_id"]: p for p in papers}
        loc = {l["id"]: l for l in wlb["located"]}
        papers_json = _j(papers)
        check("S1 plan: web PRIMERA por directiva (families ['web', 'europepmc'], families_order_rule WEB_FIRST), queries.web.query == query_en, "
              "entered_by 'directive'; el proveedor Brave REAL (cargado por ruta) recibió UNA GET con la llave SÓLO en la cabecera (no en la URL)",
              plan["families"] == ["web", "europepmc"] and plan.get("families_order_rule") == sh.FAMILIES_ORDER_RULE_WEB_FIRST
              and plan["queries"]["web"]["query"] == Q1 and plan["queries"]["web"]["entered_by"] == "directive"
              and len(s1["net"].calls) == 1 and s1["net"].calls[0]["key_in_header"] is True and s1["net"].calls[0]["key_in_url"] is False,
              repr((plan["families"], s1["net"].calls)))
        check("S1 D.3 papers: 0 con source/kind 'web'; EXACTAMENTE 2 web-localizados (PMID:44444444 por doi-org-path, PMID:33333333 por "
              "pubmed-path) con source 'europepmc', kind 'literature-candidate', identifier_provenance 'web-located:<regla>', url CANÓNICA "
              "(la hallada con '?dopt' AUSENTE), search_rec/título de EPMC ('WEB TITLE' AUSENTE en papers), located_via 'web', located_from "
              "{host, rule_id, confidence, kind, round, requirement_ids} SIN url, search_rec_source declarado, [req-w1]",
              not any(p.get("source") == "web" or p.get("kind") == "web" for p in papers)
              and sorted(p["evidence_id"] for p in web_papers) == ["PMID:33333333", "PMID:44444444"]
              and all(p["source"] == "europepmc" and p["kind"] == "literature-candidate" and p["located_via"] == "web"
                      and p["search_rec_source"] == sh.WEB_SEARCH_REC_SOURCE and p["directive_requirement_ids"] == ["req-w1"]
                      and set(p["located_from"]) == {"host", "rule_id", "confidence", "kind", "round", "requirement_ids"}
                      for p in web_papers)
              and by_eid["PMID:33333333"]["identifier_provenance"] == "web-located:pubmed-path"
              and by_eid["PMID:33333333"]["url"] == "https://pubmed.ncbi.nlm.nih.gov/33333333/"
              and by_eid["PMID:33333333"]["search_rec"]["title"] == "EPMC record for web-located 333"
              and by_eid["PMID:44444444"]["identifier_provenance"] == "web-located:doi-org-path"
              and by_eid["PMID:44444444"]["url"] == "https://doi.org/10.1000/web444"
              and by_eid["PMID:44444444"]["located_from"]["host"] == "doi.org" and by_eid["PMID:44444444"]["located_from"]["kind"] == "doi"
              and "WEB TITLE" not in papers_json and "?dopt" not in papers_json and WEB_TEXT not in papers_json
              and all(k not in by_eid["PMID:11111111"] for k in ("located_via", "located_from", "search_rec_source")),
              repr([(p["evidence_id"], p.get("identifier_provenance"), p.get("url")) for p in papers]))
        f444, f333 = by_eid["PMID:44444444"]["fetched"], by_eid["PMID:33333333"]["fetched"]
        check("S1 fetch del paper web-localizado (fetch_external REAL en tempdir): 444 OA+PMCID → found True, full_text True, "
              "text_provenance 'fulltext-excerpt', cache_hit False y SIN 'full_text_skipped_reason' (el read-cache abstract-only NO se "
              "envenenó); 333 sin OA → 'abstract' de EPMC; ambos fetched.found True",
              f444["found"] is True and f444["full_text"] is True and by_eid["PMID:44444444"]["text_provenance"] == "fulltext-excerpt"
              and f444.get("cache_hit") is False and "full_text_skipped_reason" not in f444
              and f333["found"] is True and by_eid["PMID:33333333"]["text_provenance"] == "abstract"
              and "Europe PMC" in (by_eid["PMID:33333333"]["text_excerpt"] or ""),
              repr({k: f444.get(k) for k in ("found", "full_text", "cache_hit", "full_text_skipped_reason")}))
        sel = blk["selection"]
        dup_web = [d for d in sel["duplicates"] if d.get("source_family") == "web"]
        check("S1 D.1 admisión NATIVE-FIRST: PMID:11111111 (EPMC nativo Y web) → selection.duplicates[] EXACTAMENTE {duplicate, source "
              "'europepmc', source_family 'web', of 'PMID:11111111', matched_key 'PMID:11111111'}; pool_admission_rule y tie_break_web_located "
              "presentes; n_candidates 4, n_selected 4; el paper PMID:11111111 es el NATIVO (identifier_provenance 'europepmc-api-live')",
              dup_web == [{"duplicate": "PMID:11111111", "source": "europepmc", "source_family": "web", "of": "PMID:11111111",
                           "matched_key": "PMID:11111111"}]
              and sel["pool_admission_rule"] == ap.WEB_POOL_ADMISSION_RULE == "native-first within a round (ADR-0084)"
              and sel["tie_break_web_located"] == ap.WEB_TIE_BREAK_RULE == "native-before-web-located (ADR-0084)"
              and sel["n_candidates"] == 4 and sel["n_selected"] == 4 and sel["n_duplicates"] == 1
              and by_eid["PMID:11111111"]["identifier_provenance"] == "europepmc-api-live" and "located_via" not in by_eid["PMID:11111111"],
              repr(sel["duplicates"]))
        check("S1 D.2 ranking (OA+PMCID primero, luego fuente, luego NATIVO antes que web-localizado, luego llegada): "
              "111 (nativo OA) 1 · 444 (web OA) 2 · 222 (nativo) 3 · 333 (web) 4",
              [p["evidence_id"] for p in sorted(papers, key=lambda p: p["selection_rank"])] == ["PMID:11111111", "PMID:44444444", "PMID:22222222", "PMID:33333333"],
              repr([(p["evidence_id"], p["selection_rank"]) for p in papers]))
        check("S1 D.4 web_locator.located[] CERRADOS: 333 admitted/selected True, rank 4, fetched_found True, duplicate_of None, "
              "'materialized-same-round'; 111 → feed_state 'already-present (dup of PMID:11111111)', admitted False, duplicate_of "
              "'PMID:11111111', pool_dedup {layer 'pool', rule}; 555 → 'already-present (dup of PMID:55555555)' por existing_ids (dedup "
              "'already-present (existing_ids)', SIN GET a EPMC); notfound → 'not-found-in-europepmc' fed_to 'ctx:dois', selected False, "
              "fetched_found None; todo feed_state/fed_to en los vocabularios de web_locator; _resolve_one recibió 4 idents en forma EPMC",
              loc["PMID:33333333"]["admitted"] is True and loc["PMID:33333333"]["selected"] is True and loc["PMID:33333333"]["selection_rank"] == 4
              and loc["PMID:33333333"]["fetched_found"] is True and loc["PMID:33333333"]["duplicate_of"] is None
              and loc["PMID:33333333"]["feed_state"] == "materialized-same-round"
              and loc["PMID:11111111"]["feed_state"] == "already-present (dup of PMID:11111111)" and loc["PMID:11111111"]["admitted"] is False
              and loc["PMID:11111111"]["duplicate_of"] == "PMID:11111111" and loc["PMID:11111111"]["pool_dedup"]["layer"] == "pool"
              and loc["PMID:11111111"]["selected"] is False
              and loc["PMID:55555555"]["feed_state"] == "already-present (dup of PMID:55555555)" and loc["PMID:55555555"]["dedup"] == "already-present (existing_ids)"
              and loc["PMID:55555555"]["admitted"] is False
              and loc["10.1000/notfound"]["feed_state"] == "not-found-in-europepmc" and loc["10.1000/notfound"]["fed_to"] == "ctx:dois"
              and loc["10.1000/notfound"]["selected"] is False and loc["10.1000/notfound"]["fetched_found"] is None
              and all(wl.feed_state_in_vocabulary(l["feed_state"]) and l["fed_to"] in wl.FED_TO for l in wlb["located"])
              and all(k in l for l in wlb["located"] for k in ap.WEB_LOCATED_CLOSE_KEYS)
              # las 4 primeras llamadas a _resolve_one son las de la RONDA (materialización); las 4 siguientes las hace
              # fetch_external al bajar los 4 seleccionados (por evidence_id) — 8 en total, ninguna en forma libre
              and s1["epmc"].calls[:4] == ["PMID:33333333", "DOI:10.1000/web444", "PMID:11111111", "DOI:10.1000/notfound"]
              and len(s1["epmc"].calls) == 8
              and sorted(s1["epmc"].calls[4:]) == ["PMID:11111111", "PMID:22222222", "PMID:33333333", "PMID:44444444"]
              and all(wl.EPMC_IDENT_RE.match(c) for c in s1["epmc"].calls),
              repr([(l["id"], l["feed_state"], l["admitted"], l["selected"]) for l in wlb["located"]]))
        check("S1 D.4 block['web_locator'] — estado y contadores (MEDICIÓN): state 'located' (en vocabulario), measured True, in_plan True, "
              "provider 'brave' env:WITT_WEB_LOCATOR, entered_by 'directive', directive_requirement_ids [req-w1], families_order_rule; "
              "n_queries 1, n_results 6, n_located 5, n_unresolved 1, n_materialized 3, n_epmc_gets 4, n_not_found_in_europepmc 1, "
              "n_already_present_resolver 1 (555) + n_already_present_pool 1 (111) = n_already_present 2, n_admitted 2, n_located_selected 2, "
              "n_located_not_selected 0, n_papers_web_located 2, n_fed_ctx 2 (DOI 444 + DOI notfound → ctx:dois)",
              wlb["state"] == "located" and wl.web_state_in_vocabulary(wlb["state"]) and wlb["measured"] is True and wlb["in_plan"] is True
              and wlb["provider"] == "brave" and wlb["provider_source"] == "env:WITT_WEB_LOCATOR" and wlb["provider_available"] is True
              and wlb["entered_by"] == "directive" and wlb["directive_requirement_ids"] == ["req-w1"]
              and wlb["families_order_rule"] == sh.FAMILIES_ORDER_RULE_WEB_FIRST and wlb["query_source"] == "council-directive:req-w1"
              and wlb["n_queries"] == 1 and wlb["n_results"] == 6 and wlb["n_located"] == 5 and wlb["n_unresolved"] == 1
              and wlb["n_materialized"] == 3 and wlb["n_epmc_gets"] == 4 and wlb["n_not_found_in_europepmc"] == 1
              and wlb["n_already_present_resolver"] == 1 and wlb["n_already_present_pool"] == 1 and wlb["n_already_present"] == 2
              and wlb["n_admitted"] == 2 and wlb["n_located_selected"] == 2 and wlb["n_located_not_selected"] == 0
              and wlb["n_papers_web_located"] == 2 and wlb["n_fed_ctx"] == 2 and wlb["n_rounds_with_web"] == 1
              and wlb["by_round"][0]["state"] == "located" and wlb["had_web_candidates"] is True,
              repr({k: wlb.get(k) for k in ("state", "n_results", "n_located", "n_materialized", "n_epmc_gets", "n_already_present",
                                              "n_admitted", "n_located_selected", "n_papers_web_located", "n_fed_ctx")}))
        check("S1 D.4 block['web_locator'] — costo/cuota/encabezado: cost {provider brave, n_queries_billable 1, price 5.0/1k, usd_projected "
              "0.005, class 'proyección', price_as_of} == cost_usd_projected 0.005; quota {state 'under-cap', n_before 0, n_after 1, cap 900, "
              "cap_source 'default', month UTC, hook 'ctx.web_quota', rule}; web_quota= llamado 2 veces (reserva sin record ANTES, record "
              "{n_results 6, cost 0.005} DESPUÉS); encabezado de frozen_header: module 'wl-1', resolver 'wlr-2', tool 'bws-1', "
              "state_vocabulary, 12 resolver_rules, allowed_hosts 'all …', generic_doi_rule enabled, text_policy, rule, gate 'directive-only'; "
              "block_version 'wlb-1'; queries[0] con provider_status 'success', state 'located', n_billable 1, cache_hit False",
              wlb["cost"]["provider"] == "brave" and wlb["cost"]["n_queries_billable"] == 1 and wlb["cost"]["price_usd_per_1k"] == 5.0
              and abs(wlb["cost"]["usd_projected"] - 0.005) < 1e-9 and wlb["cost"]["class"] == "proyección"
              and wlb["cost"]["price_as_of"] == wl.PRICE_AS_OF and abs(wlb["cost_usd_projected"] - 0.005) < 1e-9
              and wlb["quota"]["state"] == "under-cap" and wlb["quota"]["n_before"] == 0 and wlb["quota"]["n_after"] == 1
              and wlb["quota"]["cap"] == 900 and wlb["quota"]["cap_source"] == "default" and wlb["quota"]["month"] == wl.month_utc()
              and wlb["quota"]["hook"] == "ctx.web_quota" and wlb["quota"]["rule"] == wl.QUOTA_RULE and wlb["quota_state"] == "under-cap"
              and len(qspy1.calls) == 2 and qspy1.calls[0]["record"] is None and qspy1.calls[0]["provider"] == "brave"
              and qspy1.calls[1]["record"] == {"n_results": 6, "cost": 0.005, "n_requests_extra": 0}   # corrector: peticiones extra declaradas
              and wlb["module_version"] == "wl-1" and wlb["resolver_version"] == wl.RESOLVER_VERSION == "wlr-2" and wlb["tool_version"] == "bws-1"
              and wlb["state_vocabulary"]["exact"] == list(wl.WEB_STATES_EXACT) and len(wlb["resolver_rules"]) == 12
              and wlb["allowed_hosts"]["value"] == wl.ALLOWED_HOSTS_ALL and wlb["generic_doi_rule"]["enabled"] is True
              and wlb["text_policy"] == wl.TEXT_POLICY and wlb["rule"] == wl.WEB_LOCATOR_RULE and wlb["gate"] == "directive-only"
              and wlb["block_version"] == ap.WEB_LOCATOR_BLOCK_VERSION == "wlb-1"
              and wlb["queries"][0]["provider_status"] == "success" and wlb["queries"][0]["state"] == "located"
              and wlb["queries"][0]["n_billable"] == 1 and wlb["queries"][0]["cache_hit"] is False and wlb["queries"][0]["round"] == 1,
              repr((wlb["cost"], wlb["quota"], qspy1.calls)))
        gaps = wlb["gap_flags_typed"]
        check("S1 G.2 gap_flags_typed: EXACTAMENTE 2 — {kind 'web-located-unresolved', url researchgate, host, reason 'no-identifier-pattern'} "
              "y {kind 'web-located-unmaterialized', id '10.1000/notfound', url, host 'doi.org', reason 'not-found-in-europepmc'}; n_gap_flags "
              "{1, 1}; unresolved[0].title_web recortado a 120 (205 → 120) y SÓLO ahí vive el título del buscador",
              len(gaps) == 2 and gaps[0]["kind"] == "web-located-unresolved" and gaps[0]["host"] == "www.researchgate.net"
              and gaps[0]["reason"] == "no-identifier-pattern" and gaps[0]["url"].startswith("https://www.researchgate.net/")
              and gaps[1] == {"kind": "web-located-unmaterialized", "id": "10.1000/notfound", "url": "https://doi.org/10.1000/notfound",
                              "host": "doi.org", "reason": "not-found-in-europepmc", "round": 1, "requirement_ids": ["req-w1"]}
              and wlb["n_gap_flags"] == {"web-located-unresolved": 1, "web-located-unmaterialized": 1}
              and len(wlb["unresolved"]) == 1 and len(wlb["unresolved"][0]["title_web"]) == 120,
              repr(gaps))
        check("S1 n_results_by_source: web == 0 SIEMPRE (la familia MIDIÓ → 0 explícito) y europepmc == 4 (2 nativos + 2 web-localizados); "
              "europepmc_searched conservado; sources_requested == plan.families",
              blk["n_results_by_source"] == {"web": 0, "europepmc": 4} and blk["europepmc_searched"]["status"] == "success"
              and blk["sources_requested"] == ["web", "europepmc"], repr(blk["n_results_by_source"]))
        _pe1, _be1 = sh.plan_event_payload(plan), ap.path_b_event_payload(blk)
        check("S1 (corrector ADR-0084) los eventos llevan las reglas que la Hoja/Traza pintan: stage.search.plan += families_order_rule "
              "(WEB_FIRST) y stage.path_b.selection += pool_admission_rule / tie_break_web_located — SÓLO cuando existen en el plan/selection; "
              "la materialización por Europe PMC corrió por search_europepmc_ledger con timeout ACOTADO al presupuesto de la familia "
              "(0.5 s <= timeout <= WITT_WEB_BUDGET_S 30) y consultas en forma de ident (EXT_ID:… AND SRC:MED | DOI:…), 4 GETs",
              _pe1["families_order_rule"] == sh.FAMILIES_ORDER_RULE_WEB_FIRST
              and _be1["selection"]["pool_admission_rule"] == ap.WEB_POOL_ADMISSION_RULE
              and _be1["selection"]["tie_break_web_located"] == ap.WEB_TIE_BREAK_RULE
              and len(s1["epmc_timeouts"]) == 4 and all(0.5 <= t <= 30.0 for t in s1["epmc_timeouts"])
              and s1["epmc_queries"][0] == "EXT_ID:33333333 AND SRC:MED" and s1["epmc_queries"][1] == "DOI:10.1000/web444",
              repr((_pe1.get("families_order_rule"), _be1["selection"], s1["epmc_timeouts"], s1["epmc_queries"])))
        names = [n for n, _ in ev]
        ev_web = [p for n, p in ev if n == "web.locate"]
        ev_json_no_plan = _j([p for n, p in ev if n != "search.plan"])
        check("S1 D.5 eventos vía on_stage: ['search.plan', 'web.locate', 'search.source'(web), 'search.source'(europepmc), 'search.round'] "
              "— UN 'web.locate' por consulta ENVIADA con {round 1, provider 'brave', query_en, requirement_ids [req-w1], provider_status "
              "'success', n_results 6, n_located 5, n_materialized 3, n_unresolved 1, located_ids (ids, NO URLs), hosts_unresolved "
              "['www.researchgate.net'], quota {under-cap, 1, 900}}; CERO 'https://' y CERO 'WEB TITLE' en todos los payloads salvo el plan",
              names == ["search.plan", "web.locate", "search.source", "search.source", "search.round"]
              and [p["family"] for n, p in ev if n == "search.source"] == ["web", "europepmc"]
              and len(ev_web) == 1 and ev_web[0]["round"] == 1 and ev_web[0]["provider"] == "brave" and ev_web[0]["query_en"] == Q1
              and ev_web[0]["requirement_ids"] == ["req-w1"] and ev_web[0]["provider_status"] == "success"
              and ev_web[0]["n_results"] == 6 and ev_web[0]["n_located"] == 5 and ev_web[0]["n_materialized"] == 3 and ev_web[0]["n_unresolved"] == 1
              and ev_web[0]["located_ids"] == ["PMID:33333333", "10.1000/web444", "PMID:11111111", "10.1000/notfound", "PMID:55555555"]
              and ev_web[0]["hosts_unresolved"] == ["www.researchgate.net"]
              and ev_web[0]["quota"] == {"state": "under-cap", "n_after": 1, "cap": 900}
              and "https://" not in ev_json_no_plan and "WEB TITLE" not in ev_json_no_plan and WEB_TEXT not in ev_json_no_plan
              and next(p for n, p in ev if n == "search.plan")["families"][0] == "web",
              repr((names, ev_web[0] if ev_web else None)))
        src_web = next(p for n, p in ev if n == "search.source" and p["family"] == "web")
        check("S1 C.7 stage.search.source(web) trae provider / n_queries / n_results / n_located / n_materialized / n_unresolved / "
              "n_already_present / cost_usd_projected / quota_state y NO web_locator ni calls; la de europepmc NO los gana",
              {"provider": "brave", "n_queries": 1, "n_results": 6, "n_located": 5, "n_materialized": 3, "n_unresolved": 1,
               "quota_state": "under-cap"}.items() <= src_web.items() and "web_locator" not in src_web and "calls" not in src_web
              and not any(k in next(p for n, p in ev if n == "search.source" and p["family"] == "europepmc")
                          for k in ("provider", "n_located", "quota_state")),
              repr(src_web))
        pl = ap.path_b_event_payload(blk, trigger="competence")
        pl_json = _j(pl)
        pl_urls = set(_urls_in(pl_json))
        canon = {p["url"] for p in papers if p.get("url")}
        check("S1 D.5 path_b_event_payload ADITIVO: n_web_located 5, n_web_unresolved 1; papers[] trae located_via/located_from/search_rec_source "
              "SÓLO en los 2 web-localizados (located_from sin url); las ÚNICAS URLs del payload son las canónicas de los papers (0 halladas, "
              "0 '?dopt', 0 researchgate); sin 'WEB TITLE' ni description; n_results_by_source.web 0",
              pl["n_web_located"] == 5 and pl["n_web_unresolved"] == 1
              and sorted(r["evidence_id"] for r in pl["papers"] if "located_from" in r) == ["PMID:33333333", "PMID:44444444"]
              and all("url" not in r["located_from"] and r["located_via"] == "web" and r["search_rec_source"] == sh.WEB_SEARCH_REC_SOURCE
                      for r in pl["papers"] if "located_from" in r)
              and all("located_from" not in r for r in pl["papers"] if r["evidence_id"] in ("PMID:11111111", "PMID:22222222"))
              and pl_urls and pl_urls <= canon and "?dopt" not in pl_json and "researchgate" not in pl_json
              and "WEB TITLE" not in pl_json and WEB_TEXT not in pl_json and pl["n_results_by_source"]["web"] == 0,
              repr((pl["n_web_located"], pl["n_web_unresolved"], sorted(pl_urls))))
        t_round_last = max(s1["t_events"]["search.round"])
        fetch_idents = [c["ident"] for c in s1["fetch"].calls]
        raw_jsons = sorted(p.name for p in s1["cache_fetch"].glob("raw_paper_*.json"))
        check("S1 read-cache NO envenenado (MEDIDO): fetch_external corrió 4 veces, TODAS después del último 'search.round' (la "
              "materialización de la ronda fue _resolve_one, sin fetch), sólo para los 4 SELECCIONADOS (ni notfound ni 555); en el tempdir "
              "quedan EXACTAMENTE 4 raw_paper_*.json (0 en mcp_cache del repo)",
              # >= : mismo reloj monotónico; en Windows el tick es ~15 ms y el evento y el primer fetch pueden compartirlo
              len(s1["fetch"].calls) == 4 and all(c["t"] >= t_round_last for c in s1["fetch"].calls)
              and sorted(fetch_idents) == ["PMID:11111111", "PMID:22222222", "PMID:33333333", "PMID:44444444"]
              and len(raw_jsons) == 4 and all(c["want_full_text"] is True for c in s1["fetch"].calls),
              repr((fetch_idents, raw_jsons)))
        # control POSITIVO del envenenamiento (Context 4): en OTRO tempdir, fetch abstract-only y luego full-text → 'cache-hit-abstract-only'
        poison = TMP / "poison-control"
        poison.mkdir(parents=True, exist_ok=True)
        fetch_paper._resolve_one = EpmcSpy(EP1)
        g1 = _real_fetch_external("DOI:10.1000/web444", want_full_text=False, cache_dir=poison)
        g2 = _real_fetch_external("DOI:10.1000/web444", want_full_text=True, cache_dir=poison)
        check("control POSITIVO (Context 4): materializar con fetch_external(want_full_text=False) y pedir luego el texto completo devuelve "
              "cache_hit True + full_text_skipped_reason 'cache-hit-abstract-only' — exactamente lo que el pipeline EVITA (la ronda usa "
              "_resolve_one; el paper web 444 salió con full_text True y sin esa llave)",
              g1["found"] is True and g1["full_text"] is False and g2["cache_hit"] is True
              and g2.get("full_text_skipped_reason") == "cache-hit-abstract-only" and g2["full_text"] is False,
              repr({k: g2.get(k) for k in ("cache_hit", "full_text", "full_text_skipped_reason")}))
        blk_json = _j(blk)
        outside = _j({k: v for k, v in blk.items() if k not in ("web_locator", "search_ledger")})
        sl_rows_json = _j([{k: v for k, v in s.items() if k != "web_locator"} for rd in blk["search_ledger"]["rounds"] for s in rd["sources"]])
        check("S1 DOCTRINA (texto web y URLs): fuera de block.web_locator y de search_ledger.rounds[].sources[web].web_locator NO aparece "
              "'WEB TITLE', ni la description del buscador, ni '?dopt', ni researchgate; la description NO aparece NI en web_locator (el tool "
              "la corta en la salida; el raw en disco sí la conserva); la llave fake JAMÁS en el bloque ni en los eventos (M.5); el raw de "
              "Brave quedó en el tempdir del tool con la description íntegra",
              "WEB TITLE" not in outside and WEB_TEXT not in outside and "?dopt" not in outside and "researchgate" not in outside
              and "WEB TITLE" not in sl_rows_json and WEB_TEXT not in blk_json and FAKE_KEY not in blk_json and FAKE_KEY not in _j(ev)
              and "WEB TITLE" in _j(wlb["unresolved"])
              and any(WEB_TEXT in p.read_text(encoding="utf-8") for p in s1["cache_web"].glob("raw_brave_*.json")),
              repr(sorted(p.name for p in s1["cache_web"].glob("raw_brave_*.json"))))

        # =============================== S1b · segunda corrida del MISMO día → cache-hit del tool =========================
        qspy1b = QuotaSpy()
        s1b = run_scenario("s1", [web_directive("req-w1", Q1)], WEB1, NAT1, EP1, n=5, existing_ids=["PMID:55555555"], quota=qspy1b, env=ON, web_query=Q1)
        w1b = s1b["block"]["web_locator"]
        check("S1b B.5 caché del tool (mismo día, misma consulta, mismo cache_dir): 0 GETs a Brave, queries[0].cache_hit True, quota.state "
              "'not-consumed (cache-hit)', web_quota= NO llamado (0), n_billable 0, cost_usd_projected 0.0; el ledger y los papers son los mismos "
              "(state 'located', n_located 5, 2 web-localizados)",
              s1b["net"].calls == [] and w1b["queries"][0]["cache_hit"] is True and w1b["quota"]["state"] == "not-consumed (cache-hit)"
              and qspy1b.calls == [] and w1b["queries"][0]["n_billable"] == 0 and w1b["cost_usd_projected"] == 0.0
              and w1b["state"] == "located" and w1b["n_located"] == 5 and w1b["n_papers_web_located"] == 2,
              repr((len(s1b["net"].calls), w1b["quota"], w1b["cost_usd_projected"])))

        # =============================== S2 · 5 nativos + 1 web con n=5 → web NO seleccionado ============================
        Q2 = "wt1a review S2"
        NAT2 = [_rec(f"{i}" * 8, pmcid=f"PMC{i}", is_oa=True, title=f"Native {i}") for i in range(1, 6)]
        WEB2 = [_res("https://pubmed.ncbi.nlm.nih.gov/66666666/", "WEB TITLE 666")]
        EP2 = {"PMID:66666666": _rec("66666666", pmcid="PMC666", is_oa=True, title="EPMC web 666")}
        s2 = run_scenario("s2", [web_directive("req-w2", Q2)], WEB2, NAT2, EP2, n=5, quota=None, env=ON, web_query=Q2)
        b2, w2 = s2["block"], s2["block"]["web_locator"]
        l666 = next(l for l in w2["located"] if l["id"] == "PMID:66666666")
        check("S2 D.2 5 nativos OA + 1 web OA con n=5: el web-localizado (PMID:66666666) queda not_selected por el desempate "
              "native-before-web-located; located: admitted True, selected False, selection_rank None, fetched_found None; n_located_selected 0, "
              "n_located_not_selected 1, n_papers_web_located 0; tie_break_web_located presente; fetch_external NO se llamó para 666; "
              "n_results_by_source {web 0, europepmc 5}; quota sin web_quota= → 'not-enforced (no quota callable)', hook 'absent (…)'",
              b2["selection"]["not_selected"] == ["PMID:66666666"] and b2["selection"]["tie_break_web_located"] == ap.WEB_TIE_BREAK_RULE
              and l666["admitted"] is True and l666["selected"] is False and l666["selection_rank"] is None and l666["fetched_found"] is None
              and w2["n_located_selected"] == 0 and w2["n_located_not_selected"] == 1 and w2["n_papers_web_located"] == 0
              and "PMID:66666666" not in [c["ident"] for c in s2["fetch"].calls] and len(s2["fetch"].calls) == 5
              and b2["n_results_by_source"] == {"web": 0, "europepmc": 5}
              and w2["quota"]["state"] == "not-enforced (no quota callable)" and str(w2["quota"]["hook"]).startswith("absent")
              and w2["quota_state"] == "not-enforced (no quota callable)",
              repr((b2["selection"]["not_selected"], {k: l666[k] for k in ap.WEB_LOCATED_CLOSE_KEYS}, w2["quota"])))

        # =============================== S3 · 0 nativos + 1 web → seleccionado rank 1 ====================================
        Q3 = "wt1a review S3"
        s3 = run_scenario("s3", [web_directive("req-w3", Q3)], WEB2, [], EP2, n=5, quota=None, env=ON, web_query=Q3)
        b3, w3 = s3["block"], s3["block"]["web_locator"]
        check("S3 0 nativos (europepmc 'no-match') + 1 web: el web-localizado se selecciona con rank 1, fetched.found True; "
              "n_results_by_source {web 0, europepmc 1}; n_located_selected 1, n_papers_web_located 1; state 'located'",
              len(b3["papers"]) == 1 and b3["papers"][0]["evidence_id"] == "PMID:66666666" and b3["papers"][0]["selection_rank"] == 1
              and b3["papers"][0]["source_family"] == "web" and b3["papers"][0]["fetched"]["found"] is True
              and b3["europepmc_searched"]["status"] == "no-match" and b3["n_results_by_source"] == {"web": 0, "europepmc": 1}
              and w3["n_located_selected"] == 1 and w3["n_papers_web_located"] == 1 and w3["state"] == "located",
              repr((b3["n_results_by_source"], [(p["evidence_id"], p["selection_rank"]) for p in b3["papers"]])))

        # =============================== S4 · fetch_external stub found False → paper sin pasaje ==========================
        Q4 = "wt1a review S4"
        # corrector ADR-0084: el registro de EPMC SÍ trae abstract (resultType=core siempre lo trae) — antes el smoke lo vaciaba y por eso
        # no veía que el abstract del registro llegaba al paper y E.3 ('text-without-fetch') volvía inadmisible TODO el bundle
        s4 = run_scenario("s4", [web_directive("req-w4", Q4)], WEB2, [], EP2, n=5, quota=None, fetch_found=False, env=ON, web_query=Q4)
        p4, w4 = s4["block"]["papers"][0], s4["block"]["web_locator"]
        _frag4, _preds4 = vo.web_predicates([], {"path_b": s4["block"]}, "wt1a marks the pronephros.", s4["block"]["web_locator"],
                                              wl.provider_state({"WITT_WEB_LOCATOR": "brave", "BRAVE_API_KEY": FAKE_KEY}))
        check("S4 D.3 (corrector D.3 <-> E.3) fetch_external stub found False con registro EPMC CON abstract: el paper web-localizado queda SIN "
              "pasaje — abstract None, text_excerpt None, text_provenance 'none', text_excerpt_rule 'withheld: …', text_withheld_reason "
              "'web-located-not-fetched (ADR-0084 D.3)' (el abstract del registro se RETIENE) — conserva search_rec/fetched, located.fetched_found "
              "False, selected True; el gate E.3 web_items_native_only sobre ESTE bundle es ok True (0 'text-without-fetch') y los 3 DUROS pasan "
              "sin cita al paper: la respuesta sigue admisible; E.2 gatea sólo la CITA",
              p4["fetched"]["found"] is False and p4["text_provenance"] == "none" and p4["text_excerpt"] is None and p4["abstract"] is None
              and p4["text_excerpt_rule"] == ap.WEB_TEXT_WITHHELD_RULE and p4["text_withheld_reason"] == ap.WEB_TEXT_WITHHELD_REASON
              and p4["search_rec"]["title"] == "EPMC web 666" and EP2["PMID:66666666"]["abstract"] not in _j(p4)
              and next(l for l in w4["located"] if l["id"] == "PMID:66666666")["fetched_found"] is False
              and next(l for l in w4["located"] if l["id"] == "PMID:66666666")["selected"] is True
              and _frag4["state"] == "checked" and _frag4["web_items_native_only"]["ok"] is True
              and _frag4["web_items_native_only"]["n_web_located"] == 1
              and all(_frag4[n]["ok"] is True for n in _frag4["conjunction"]) and len(_preds4) == 3 == len(_frag4["conjunction"]),
              repr({k: p4.get(k) for k in ("text_provenance", "text_excerpt", "abstract", "text_withheld_reason")})
              + " " + repr(_frag4["web_items_native_only"]["offenders"]))

        # =============================== S8 · el MISMO paper en 3 URLs (pubmed + PMC + doi.org) → UNA GET, UN candidato ==========
        Q8 = "wt1a review S8"
        REC8 = _rec("15982647", pmcid="PMC2688018", doi="10.1242/DEV.02071", is_oa=True, title="EPMC record 15982647 (one paper)")
        WEB8 = [_res("https://pubmed.ncbi.nlm.nih.gov/15982647/", "WEB TITLE pubmed"),
                _res("https://pmc.ncbi.nlm.nih.gov/articles/PMC2688018/", "WEB TITLE pmc"),
                _res("https://doi.org/10.1242/dev.02071", "WEB TITLE doi"),
                _res("https://www.frontiersin.org/articles/10.3389/fcell.2020.00123/full", "WEB TITLE frontiers /full")]
        EP8 = {"PMID:15982647": REC8}
        s8 = run_scenario("s8", [web_directive("req-w8", Q8)], WEB8, [], EP8, n=5, quota=None, env=ON, web_query=Q8)
        b8, w8 = s8["block"], s8["block"]["web_locator"]
        l8 = {l["id"]: l for l in w8["located"]}
        check("S8 (corrector ADR-0084) el MISMO paper devuelto como pubmed + PMC + doi.org: Europe PMC recibió UNA GET (PMID:15982647) + la del "
              "DOI de Frontiers (sufijo /full RECORTADO por el resolutor -> '10.3389/fcell.2020.00123', not-found); 1 materializado, 2 "
              "'already-present (dup of PMID:15982647)' con same_paper {layer 'family', matched_key PMCID:/DOI:}, admitted/selected False y "
              "duplicate_of PMID:15982647; n_same_paper_dups 2, n_epmc_gets 2, n_materialized 1; selection.duplicates == [] (ningun paper "
              "duplicado de si mismo), 1 paper en el bundle; el candidato admitido y seleccionado conserva 'materialized-same-round' con "
              "admitted/selected True",
              s8["epmc"].calls[:2] == ["PMID:15982647", "DOI:10.3389/fcell.2020.00123"] and w8["n_epmc_gets"] == 2
              and w8["n_materialized"] == 1 and w8["n_same_paper_dups"] == 2 and w8["n_not_found_in_europepmc"] == 1
              and l8["PMID:15982647"]["feed_state"] == "materialized-same-round" and l8["PMID:15982647"]["admitted"] is True
              and l8["PMID:15982647"]["selected"] is True
              and l8["PMC2688018"]["feed_state"] == "already-present (dup of PMID:15982647)" and l8["PMC2688018"]["same_paper"]["layer"] == "family"
              and l8["PMC2688018"]["same_paper"]["matched_key"] == "PMCID:PMC2688018" and l8["PMC2688018"]["admitted"] is False
              and l8["PMC2688018"]["selected"] is False and l8["PMC2688018"]["duplicate_of"] == "PMID:15982647"
              and l8["10.1242/dev.02071"]["feed_state"] == "already-present (dup of PMID:15982647)"
              and l8["10.1242/dev.02071"]["same_paper"]["matched_key"] == "DOI:10.1242/dev.02071" and l8["10.1242/dev.02071"]["fed_to"] is None
              and l8["10.3389/fcell.2020.00123"]["feed_state"] == "not-found-in-europepmc"
              and b8["selection"]["duplicates"] == [] and len(b8["papers"]) == 1 and b8["papers"][0]["evidence_id"] == "PMID:15982647"
              and w8["n_already_present_pool"] == 0 and w8["n_papers_web_located"] == 1
              and all(wl.feed_state_in_vocabulary(l["feed_state"]) for l in w8["located"]),
              repr((s8["epmc"].calls[:3], [(l["id"], l["feed_state"], l["admitted"], l.get("duplicate_of")) for l in w8["located"]],
                    b8["selection"]["duplicates"])))

        # =============================== S9 · Europe PMC devuelve OTRO registro (top hit != ident) → mismatch, 0 candidatos =========
        Q9 = "wt1a review S9"
        WEB9 = [_res("https://pubmed.ncbi.nlm.nih.gov/77777777/", "WEB TITLE pubmed 777")]
        EP9 = {"PMID:77777777": _rec("99999999", title="EPMC returned ANOTHER paper")}
        s9 = run_scenario("s9", [web_directive("req-w9", Q9)], WEB9, [], EP9, n=5, quota=None, env=ON, web_query=Q9)
        w9 = s9["block"]["web_locator"]
        check("S9 (corrector ADR-0084, Context 4) Europe PMC devuelve un registro cuyo PMID/PMCID/DOI NO es el identificador localizado: "
              "feed_state 'error: europepmc record mismatch (PMID:99999999 != PMID:77777777)' (prefijo 'error: ' del vocabulario), 0 candidatos, "
              "0 papers, n_epmc_record_mismatch 1, n_materialized 0, fila 'no-match'",
              w9["located"][0]["feed_state"] == "error: europepmc record mismatch (PMID:99999999 != PMID:77777777)"
              and wl.feed_state_in_vocabulary(w9["located"][0]["feed_state"]) and s9["block"]["papers"] == []
              and w9["n_epmc_record_mismatch"] == 1 and w9["n_materialized"] == 0 and w9["by_round"][0]["status"] == "no-match",
              repr((w9["located"][0]["feed_state"], w9["n_epmc_record_mismatch"])))

        # =============================== S5 · SIN directiva web (proveedor disponible) ====================================
        # el 3º es un dup NATIVO en la capa del POOL (evidence_id distinto 'PMC111', misma llave PMCID): la capa de la ronda
        # deduplica por evidence_id, así que un registro idéntico jamás llegaría a _pool_add
        NAT5 = [_rec("11111111", pmcid="PMC111", is_oa=True), _rec("22222222"),
                dict(_rec("11111111", pmcid="PMC111", is_oa=True), pmid=None, epmc_id="PMC111", source="PMC")]
        s5 = run_scenario("s5", [], [], NAT5, {}, n=5, quota=None, env=ON)
        b5, w5 = s5["block"], s5["block"]["web_locator"]
        check("S5 sin directiva web (llave presente): el plan no trae web (families ['europepmc'], sin families_order_rule); "
              "block.web_locator SIEMPRE presente con state 'not-requested (no web directive)', in_plan False, plan_exclusion_reason None, "
              "measured False, contadores null (no midió ≠ 0), n_queries 0, queries/located/unresolved []; selection SIN pool_admission_rule "
              "ni tie_break_web_located (byte-idéntica a hoy) y el duplicado NATIVO sin 'source_family'; 0 eventos 'web.locate'; 0 GETs a Brave; "
              "path_b_event_payload n_web_located None",
              s5["plan"]["families"] == ["europepmc"] and "families_order_rule" not in s5["plan"]
              and w5["state"] == ap.WEB_STATE_NOT_REQUESTED == "not-requested (no web directive)" and wl.web_state_in_vocabulary(w5["state"])
              and w5["in_plan"] is False and w5["plan_exclusion_reason"] is None and w5["measured"] is False
              and w5["n_located"] is None and w5["n_results"] is None and w5["n_papers_web_located"] is None and w5["n_queries"] == 0
              and w5["queries"] == [] and w5["located"] == [] and w5["unresolved"] == [] and w5["gap_flags_typed"] == []
              and "pool_admission_rule" not in b5["selection"] and "tie_break_web_located" not in b5["selection"]
              and set(b5["selection"]) == {"rule", "n_requested", "retmax", "n_candidates", "n_selected", "n_duplicates", "duplicates",
                                           "not_selected", "dedup_keys"}
              and b5["selection"]["duplicates"] == [{"duplicate": "PMC111", "source": "europepmc", "of": "PMID:11111111",
                                                     "matched_key": "PMCID:PMC111"}]
              and not any(n == "web.locate" for n, _ in s5["events"]) and s5["net"].calls == []
              and ap.path_b_event_payload(b5)["n_web_located"] is None and "web" not in b5["n_results_by_source"],
              repr((s5["plan"]["families"], w5["state"], sorted(b5["selection"]))))

        # =============================== S6 · KILL-SWITCH explícito con la directiva web =================================
        s6 = run_scenario("s6", [web_directive("req-w6", "wt1a review S6")], [], NAT5, {}, n=5, quota=QuotaSpy(),
                          env={"WITT_WEB_LOCATOR": "off", "BRAVE_API_KEY": FAKE_KEY})
        b6, w6 = s6["block"], s6["block"]["web_locator"]
        check("S6 (L) kill-switch WITT_WEB_LOCATOR=off CON llave y directiva web: el plan la excluye con el literal EXACTO de 7d9ce15; "
              "block.web_locator {state 'kill-switch WITT_WEB_LOCATOR=off', provider 'off' env:WITT_WEB_LOCATOR, provider_available False, "
              "in_plan False, plan_exclusion_reason == literal, provider_state.explicit_off True, measured False}; 0 eventos web, 0 GETs; "
              "selection y papers BYTE-IDÉNTICOS a S5 (mismos nativos, sin web)",
              b6["search_ledger"]["plan"]["families_excluded"] == [{"family": "web", "reason": sh.WEB_UNSATISFIABLE_LITERAL,
                                                                     "requirement_ids": ["req-w6"]}]
              and sh.WEB_UNSATISFIABLE_LITERAL == "unsatisfiable-by-harness (tool-unavailable (ADR-0084))"
              and w6["state"] == wl.WEB_KILL_SWITCH_STATE == "kill-switch WITT_WEB_LOCATOR=off" and w6["provider"] == "off"
              and w6["provider_source"] == "env:WITT_WEB_LOCATOR" and w6["provider_available"] is False and w6["in_plan"] is False
              and w6["plan_exclusion_reason"] == sh.WEB_UNSATISFIABLE_LITERAL and w6["provider_state"]["explicit_off"] is True
              and w6["measured"] is False and w6["n_located"] is None
              and not any(n == "web.locate" for n, _ in s6["events"]) and s6["net"].calls == []
              and _j(b6["selection"]) == _j(b5["selection"])
              and [p["evidence_id"] for p in b6["papers"]] == [p["evidence_id"] for p in b5["papers"]],
              repr((w6["state"], w6["provider_source"], b6["search_ledger"]["plan"]["families_excluded"])))

        # =============================== S7 · off DERIVADO (sin llave, env sin fijar) =====================================
        s7 = run_scenario("s7", [web_directive("req-w7", "wt1a review S7")], [], NAT5, {}, n=5, quota=None,
                          env={"WITT_WEB_LOCATOR": None, "BRAVE_API_KEY": ""})
        w7 = s7["block"]["web_locator"]
        check("S7 off DERIVADO (WITT_WEB_LOCATOR sin fijar, BRAVE_API_KEY vacía): el plan excluye web con el MISMO literal de 7d9ce15 y "
              "block.web_locator declara la CAUSA: state 'tool-unavailable (ADR-0084: BRAVE_API_KEY unset)', provider 'off' "
              "'default-derived:BRAVE_API_KEY absent', key_present.brave False, explicit_off False; cero red",
              w7["state"] == wl.UNAVAILABLE_BRAVE_NO_KEY == "tool-unavailable (ADR-0084: BRAVE_API_KEY unset)"
              and w7["provider"] == "off" and w7["provider_source"] == "default-derived:BRAVE_API_KEY absent"
              and w7["provider_state"]["key_present"]["brave"] is False and w7["provider_state"]["explicit_off"] is False
              and w7["plan_exclusion_reason"] == sh.WEB_UNSATISFIABLE_LITERAL and s7["net"].calls == []
              and wl.web_state_in_vocabulary(w7["state"]),
              repr((w7["state"], w7["provider_source"])))

        # =============================== unit: _select_top_n byte-idéntico sin web + desempate con web ====================
        def _ref_select(pool, n, sources):   # la clave de ADR-0078 @ 7d9ce15, copiada literalmente
            rank = {s: i for i, s in enumerate(sources)}
            order = sorted(range(len(pool)), key=lambda i: (0 if (bool(pool[i]["search_rec"].get("is_oa")) and bool(pool[i]["search_rec"].get("pmcid"))) else 1,
                                                            rank.get(pool[i]["source"], len(rank)), i))
            chosen = order[:max(0, int(n))]
            return [pool[i]["evidence_id"] for i in chosen], [pool[i]["evidence_id"] for i in order[len(chosen):]]

        import random
        rng = random.Random(84)
        golden_pool = []
        for i in range(12):
            oa = rng.choice([True, False])
            golden_pool.append({"source": rng.choice(["europepmc", "pubmed", "openalex"]), "evidence_id": f"PMID:{i}",
                                "search_rec": {"is_oa": oa, "pmcid": f"PMC{i}" if rng.choice([True, False]) else None}})
        ok_golden = True
        for n_try in (0, 1, 3, 5, 12, 20):
            pool_copy = [dict(c, search_rec=dict(c["search_rec"])) for c in golden_pool]
            sel_new, ns_new = ap._select_top_n(pool_copy, n_try, ["europepmc", "pubmed", "web"])
            sel_ref, ns_ref = _ref_select(golden_pool, n_try, ["europepmc", "pubmed", "web"])
            ok_golden = ok_golden and [c["evidence_id"] for c in sel_new] == sel_ref and ns_new == ns_ref \
                and [c["selection_rank"] for c in sel_new] == list(range(1, len(sel_ref) + 1))
        check("unit D.2 _select_top_n SIN web es BYTE-IDÉNTICO a la clave de ADR-0078 @ 7d9ce15 (pool de 12 con OA/fuentes/orden mezclados, "
              "n ∈ {0, 1, 3, 5, 12, 20}: mismos seleccionados, mismos rangos, mismos not_selected)", ok_golden)
        tb_pool = [{"source": "europepmc", "evidence_id": "PMID:W", "source_family": "web", "search_rec": {"is_oa": True, "pmcid": "PMCW"}},
                   {"source": "europepmc", "evidence_id": "PMID:N", "source_family": "europepmc", "search_rec": {"is_oa": True, "pmcid": "PMCN"}},
                   {"source": "pubmed", "evidence_id": "PMID:P", "source_family": "pubmed", "search_rec": {"is_oa": False, "pmcid": None}}]
        sel_tb, ns_tb = ap._select_top_n(tb_pool, 2, ["web", "europepmc", "pubmed"])
        check("unit D.2 desempate: web-localizado llegado ANTES (índice 0) y nativo (índice 1) a igual OA y fuente → el nativo gana rank 1, el web "
              "rank 2 (el tercer componente manda antes que el índice); la fuente 'web' en `sources` no altera nada (los candidatos web son "
              "source 'europepmc')",
              [c["evidence_id"] for c in sel_tb] == ["PMID:N", "PMID:W"] and ns_tb == ["PMID:P"]
              and sel_tb[0]["selection_rank"] == 1 and sel_tb[1]["selection_rank"] == 2, repr([c["evidence_id"] for c in sel_tb]))
        pool_u, seen_u, dups_u = [], {}, []
        ap._pool_add(pool_u, seen_u, {"source": "europepmc", "evidence_id": "PMID:9", "search_rec": {"pmid": "9"}}, dups_u)
        ap._pool_add(pool_u, seen_u, {"source": "pubmed", "evidence_id": "PMID:9", "search_rec": {"pmid": "9"}}, dups_u)
        ap._pool_add(pool_u, seen_u, {"source": "europepmc", "source_family": "web", "evidence_id": "PMID:9", "search_rec": {"pmid": "9"}}, dups_u)
        check("unit D.1 _pool_add: el duplicado NATIVO conserva la forma de ADR-0078 {duplicate, source, of, matched_key}; el web-localizado "
              "gana SÓLO 'source_family': 'web'",
              dups_u == [{"duplicate": "PMID:9", "source": "pubmed", "of": "PMID:9", "matched_key": "PMID:9"},
                         {"duplicate": "PMID:9", "source": "europepmc", "of": "PMID:9", "matched_key": "PMID:9", "source_family": "web"}]
              and len(pool_u) == 1, repr(dups_u))

        # =============================== listas blancas del prompt (runs) — el modelo es CIEGO al localizador ==============
        try:
            import runs as runs_mod  # noqa: E402  (sólo constantes y _compact_evidence; sqlite temporal por la máscara)
            top, pk = set(runs_mod._PROMPT_PATH_B_TOP), set(runs_mod._PROMPT_PAPER_KEYS)
            proj = runs_mod._compact_evidence({"path_a": {"hits": [], "retrieval": {}}, "entities_checked": {}, "sufficiency": {},
                                               "path_b": blk})["path_b"]
            proj_json = _j(proj)
            check("Context 3 prompt: runs._PROMPT_PATH_B_TOP NO incluye web_locator/search_ledger/selection/papers-URL y _PROMPT_PAPER_KEYS NO "
                  "incluye url/located_from/located_via/search_rec_source/title; _compact_evidence(S1) NO proyecta 'web_locator', ninguna URL "
                  "hallada, 'WEB TITLE', la description ni 'located_from' — el sintetizador es CIEGO al localizador por construcción",
                  not ({"web_locator", "search_ledger", "url", "located_from"} & top)
                  and not ({"url", "located_from", "located_via", "search_rec_source", "title", "web_locator"} & pk)
                  and "web_locator" not in proj and "web_locator" not in proj_json and "located_from" not in proj_json
                  and "WEB TITLE" not in proj_json and WEB_TEXT not in proj_json and "?dopt" not in proj_json
                  and "researchgate" not in proj_json and "notfound" not in proj_json,
                  repr((sorted(top), sorted(pk))))
        except Exception as e:   # el import de runs es parte del gate: su fallo se declara como FAIL, no se salta
            check("Context 3 prompt: runs importable para leer _PROMPT_PATH_B_TOP / _PROMPT_PAPER_KEYS", False, f"{type(e).__name__}: {e}")
    finally:
        fetch_paper._resolve_one, fetch_paper.search_europepmc_ledger = _resolve_real, _epmc_real
        fetch_paper.fetch_external, fetch_paper._full_text_xml = _real_fetch_external, _xml_real

    check("mcp_cache del repo BYTE-IDÉNTICO antes/después (nombres, tamaños, mtimes): toda caché (raw_brave_* del tool, raw_paper_* del fetch) "
          "fue al tempdir", _snapshot(MCP_CACHE) == SNAP_BEFORE,
          repr(sorted(set(_snapshot(MCP_CACHE)) ^ set(SNAP_BEFORE))[:5]))
    check("el smoke corrió 100% OFFLINE — MEDIDO: urllib.request.urlopen bloqueado y contado == 0 (tool Brave real con _get parcheado; "
          "Europe PMC y texto completo falsos)", _NET_CALLS == [], f"calls={_NET_CALLS[:5]}")
    _urlreq.urlopen = _urlopen_real
    n_pass, n_total = sum(CHECKS), len(CHECKS)
    print(f"\n{n_pass}/{n_total} PASS")
    return 0 if n_pass == n_total else 1


if __name__ == "__main__":
    sys.exit(main())

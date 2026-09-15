"""smoke_tools_c.py — gate determinista de las tools Layer 0 del lote C (ADR-0080, rebanada C5):
geo_gds · unpaywall_crossref · openalex_search.

Cubre, por tool: (a) el fixture REAL grabado el 2026-09-15 (UNA GET por API pública, a través de la ruta
propia de la tool) servido offline -> status 'success' con los campos parseados y cada corte DECLARADO;
(b) un caso de error de red (HTTPError 503 / URLError) -> fila 'error' con el tipo declarado, jamás un
success vacío; (c) un caso no-match -> 'no-match' (buscado, ausente ≠ error); (d) presupuesto agotado
(timeout <= 0) -> 'skipped-budget' con CERO llamadas; (e) caché de lectura por día en un directorio
temporal (cache_hit True la segunda vez, ruta declarada, cero red); (f) identidad/contacto declarados
y JAMÁS escritos en la salida; (g) UN reintento ante 429 y el segundo 429 -> 'error' (§6 no-hang).
GEO además: la identidad (tool=witt-organogenesis, email sólo con WITT_NCBI_EMAIL) y el Throttle de
eutils son LOS MISMOS objetos de pubmed_literature (importado por ruta). Unpaywall: sin
WITT_UNPAYWALL_EMAIL -> 'tool-unavailable' declarado y NINGUNA llamada; su fixture es SINTÉTICO (marcado
en el nombre y en el cuerpo) porque no había correo para grabar uno real — el smoke lo dice.

100% offline: se monkeypatchea `<tool>._get` (la ÚNICA costura de red de cada tool) para servir fixtures;
net_throttle._sleep se stubea SÓLO para las esperas del reintento 429. Cero red / cero spend / cero
mutación de mcp_cache (toda caché va a un tempdir) ni de la DATA INAMOVIBLE. Exit 0 = todo PASS.

Corre:  python rag_index/query_service/smoke_tools_c.py
"""
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import urllib.error
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TOOLS = ROOT / ".tooluniverse" / "tools"
FIX = HERE / "fixtures"
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
from lib import net_throttle  # noqa: E402

# --- máscara offline (disciplina de la casa): ninguna tool depende de estas; se fijan por si acaso ------
os.environ["NEO4J_URI"] = ""
os.environ["RAG_BACKEND"] = "sparse"
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["WITT_RUN_ORIGIN"] = "smoke"
for _k in ("NCBI_API_KEY", "WITT_NCBI_EMAIL", "WITT_UNPAYWALL_EMAIL", "OPENALEX_API_KEY",
           "WITT_GEO_RETMAX", "WITT_GEO_ORGANISM", "WITT_OPENALEX_PER_PAGE"):
    os.environ.pop(_k, None)
os.environ["WITT_NCBI_MIN_INTERVAL_S"] = "0"   # el tiempo del throttle no es lo medido aquí


def _load(name):
    """Carga POR RUTA, igual que answer_pipeline._workspace_tool (el directorio va con punto: no es paquete)."""
    spec = importlib.util.spec_from_file_location(f"_witt_ws_{name}", TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


geo, uc, oa = _load("geo_gds"), _load("unpaywall_crossref"), _load("openalex_search")

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


def _fx(name):
    with open(FIX / name, encoding="utf-8") as f:
        return json.load(f)


GEO_FX = _fx("geo_gds_wt1a_20260915.json")
CR_FX = _fx("crossref_works_dev02071_20260915.json")
UP_FX = _fx("unpaywall_SYNTHETIC_dev02071_20260915.json")
OA_FX = _fx("openalex_works_wt1a_20260915.json")
TMP = Path(tempfile.mkdtemp(prefix="witt-smoke-tools-c-"))
EMAIL = "smoke@example.invalid"


def _http_error(code, headers=None, reason="err"):
    hdrs = None
    if headers:
        import email.message
        hdrs = email.message.Message()
        for k, v in headers.items():
            hdrs[k] = v
    return urllib.error.HTTPError("https://x.invalid/", code, reason, hdrs, io.BytesIO(b""))


class FakeNet:
    """Sirve por URL y GRABA cada llamada (url, timeout, kwargs). `plan`: lista de respuestas por llamada
    (dict json | Exception | 'fixture'); `headers` se devuelve cuando la tool pide with_headers=True."""

    def __init__(self, router, plan=None, headers=None):
        self.router, self.plan, self.headers, self.calls = router, list(plan or []), headers, []

    def __call__(self, url, timeout=None, with_headers=False, **kw):
        self.calls.append({"url": url, "timeout": timeout, "kw": kw})
        step = self.plan.pop(0) if self.plan else "fixture"
        if isinstance(step, Exception):
            raise step
        js = self.router(url) if step == "fixture" else step
        return (js, self.headers) if with_headers else js

    @property
    def urls(self):
        return [c["url"] for c in self.calls]


def _cache_dir(label):
    d = TMP / label
    d.mkdir(parents=True, exist_ok=True)
    return d


_real_sleep = net_throttle._sleep


def _with_retry_sleep_stub(fn, slept):
    """Stub SÓLO de las esperas del reintento 429 (>= 0.5 s); el throttle está a 0 s por env."""
    net_throttle._sleep = lambda secs: slept.append(secs) if secs >= 0.5 else _real_sleep(secs)
    try:
        return fn()
    finally:
        net_throttle._sleep = _real_sleep


# ======================================================================================================
# 1. GEO (geo_gds) — esearch + esummary db=gds
# ======================================================================================================
print("\n# geo_gds")
GEO_ES, GEO_SM = GEO_FX["esearch"]["response"], GEO_FX["esummary"]["response"]
check("fixture GEO real: esearch count 48 / 10 uids, esummary con los 10 uids y campos accession/entrytype/summary",
      GEO_FX["_fixture"]["live"] is True and GEO_ES["esearchresult"]["count"] == "48"
      and len(GEO_ES["esearchresult"]["idlist"]) == 10
      and GEO_SM["result"]["uids"] == GEO_ES["esearchresult"]["idlist"]
      and all(k in GEO_SM["result"][GEO_ES["esearchresult"]["idlist"][0]] for k in ("accession", "entrytype", "summary", "taxon")))


def _geo_router(url):
    if "esearch.fcgi" in url:
        return GEO_ES
    if "esummary.fcgi" in url:
        return GEO_SM
    raise AssertionError(f"URL inesperada: {url}")


check("pubmed_literature importado POR RUTA dentro de geo_gds (identidad + throttle prestados, no reimplementados)",
      geo._PL is not None and geo._PL_IMPORT_ERROR is None and hasattr(geo._PL, "_identity_params")
      and geo._PL.net_throttle is net_throttle, str(geo._PL_IMPORT_ERROR))

net = FakeNet(_geo_router, headers={"X-RateLimit-Limit": "3", "X-RateLimit-Remaining": "1"})
geo._get = net
out = geo.query_gds("wt1a", cache_dir=_cache_dir("geo1"))
d = out.get("data", {})
check("GEO fixture -> status success, n_found_total 48 (medición), n_uids 10, n_records 10, 2 GETs (esearch, esummary)",
      out["status"] == "success" and d["n_found_total"] == 48 and d["n_uids"] == 10 and d["n_records"] == 10
      and out["n_http_gets"] == 2 and "esearch.fcgi" in net.urls[0] and "esummary.fcgi" in net.urls[1],
      f"status={out['status']} err={out.get('error')}")
check("query_sent es el término LITERAL con bloque de organismo por default: '(wt1a) AND \"Danio rerio\"[Organism]'",
      out["query_sent"] == '(wt1a) AND "Danio rerio"[Organism]' and d["organism_sent"] == "Danio rerio"
      and "db=gds" in net.urls[0] and "retmax=10" in net.urls[0], out["query_sent"])
r0 = d["records"][0]
check("registro parseado: accession GSE178751, entry_type GSE, taxon Danio rerio, n_samples 25, pubmedids ['38237592'], url acc.cgi, procedencia declarada",
      r0["accession"] == "GSE178751" and r0["entry_type"] == "GSE" and r0["taxon"] == "Danio rerio"
      and r0["n_samples"] == 25 and r0["pubmedids"] == ["38237592"] and r0["url"].endswith("acc.cgi?acc=GSE178751")
      and r0["identifier_provenance"] == "ncbi-geo-esummary" and out["evidence_kind"] == "dataset", json.dumps(r0)[:200])
check("corte del summary DECLARADO: cap 1200, el de 1831 chars viene truncado y marcado; records_truncated False (10 de 10)",
      d["summary_chars_cap"] == geo.SUMMARY_CAP == 1200 and len(r0["summary"]) == 1200 and r0["summary_truncated"] is True
      and d["records_truncated"] is False and all("summary_truncated" in r for r in d["records"]))
check("identidad prestada: tool=witt-organogenesis en AMBAS URLs, sin email, ncbi_identity 'missing' declarado",
      all("tool=witt-organogenesis" in u for u in net.urls) and all("email=" not in u for u in net.urls)
      and out["ncbi_identity"] == "missing")
check("throttle prestado: MISMO objeto del registro de proceso para eutils (shared_with pubmed_literature)",
      out["throttle"]["host"] == "eutils.ncbi.nlm.nih.gov" and out["throttle"]["shared_with"] == "pubmed_literature"
      and net_throttle.get_throttle("eutils.ncbi.nlm.nih.gov") is geo._PL.net_throttle._REGISTRY["eutils.ncbi.nlm.nih.gov"])
check("rate_limit_headers = MEDICIÓN de la ÚLTIMA respuesta que los trajo, con su origen nombrado (esummary)",
      out["rate_limit_headers"] == {"X-RateLimit-Limit": "3", "X-RateLimit-Remaining": "1"}
      and out["rate_limit_headers_from"] == "esummary")
check("elapsed_s medido (float >= 0) y cache_hit False en la primera llamada, cache_path declarado bajo el tempdir",
      isinstance(out["elapsed_s"], float) and out["elapsed_s"] >= 0 and out["cache_hit"] is False
      and out["cache_path"] and "raw_geo_gds_" in out["cache_path"], out["cache_path"])

net2 = FakeNet(_geo_router)
geo._get = net2
out2 = geo.query_gds("wt1a", cache_dir=_cache_dir("geo1"))
check("caché de lectura por día: segunda llamada -> cache_hit True, cached_at declarado, CERO llamadas de red, mismo resultado",
      out2["status"] == "success" and out2["cache_hit"] is True and out2["cached_at"] and net2.calls == []
      and out2["data"]["records"] == d["records"] and out2["n_http_gets"] == 0)
cached_file = Path(ROOT / out["cache_path"]) if not Path(out["cache_path"]).is_absolute() else Path(out["cache_path"])
check("el archivo de caché es el cuerpo RAW de ambas respuestas (esearch + esummary) con fetched_at, bajo el tempdir (mcp_cache intacto)",
      cached_file.exists() and str(cached_file).startswith(str(TMP))
      and set(json.loads(cached_file.read_text(encoding="utf-8"))) >= {"fetched_at", "esearch", "esummary"})

os.environ["WITT_NCBI_EMAIL"] = EMAIL
net3 = FakeNet(_geo_router)
geo._get = net3
out3 = geo.query_gds("wt1a", cache_dir=_cache_dir("geo3"))
check("con WITT_NCBI_EMAIL: email=<env> viaja en las URLs, ncbi_identity 'declared', y la dirección NO aparece en la salida",
      all(f"email={EMAIL.replace('@', '%40')}" in u for u in net3.urls) and out3["ncbi_identity"] == "declared"
      and EMAIL not in json.dumps({k: v for k, v in out3.items() if k != "url_sent"}))
os.environ.pop("WITT_NCBI_EMAIL", None)

geo._get = FakeNet(_geo_router, plan=[{"esearchresult": {"count": "0", "idlist": []}}])
out_nm = geo.query_gds("gen_inexistente_xyz", cache_dir=_cache_dir("geo_nm"))
check("no-match: esearch count 0 -> status 'no-match' (≠ error, ≠ success), records [], n_found_total 0, NO se llama esummary",
      out_nm["status"] == "no-match" and out_nm["data"]["records"] == [] and out_nm["data"]["n_found_total"] == 0
      and out_nm["n_http_gets"] == 1, out_nm["status"])

geo._get = FakeNet(_geo_router, plan=[_http_error(503, reason="Service Unavailable")])
out_e = geo.query_gds("wt1a", cache_dir=_cache_dir("geo_e"))
check("error de red: HTTP 503 en esearch -> status 'error' con tipo y http_status declarados, sin records",
      out_e["status"] == "error" and out_e["http_status"] == 503 and out_e["error"].startswith("HTTPError")
      and "records" not in out_e.get("data", {}), out_e.get("error"))
geo._get = FakeNet(_geo_router, plan=[urllib.error.URLError("timed out")])
out_u = geo.query_gds("wt1a", cache_dir=_cache_dir("geo_u"))
check("error de red: URLError (timeout de socket) -> 'error' declarado, la corrida del caller sigue (§6 no-hang)",
      out_u["status"] == "error" and out_u["error"].startswith("URLError"))

netz = FakeNet(_geo_router)
geo._get = netz
out_z = geo.query_gds("wt1a", timeout=0, cache_dir=_cache_dir("geo_z"))
check("timeout<=0 (presupuesto agotado) -> 'skipped-budget' declarado y CERO llamadas de red",
      out_z["status"] == "skipped-budget" and "BudgetExhausted" in out_z["error"] and netz.calls == [])
nett = FakeNet(_geo_router)
geo._get = nett
geo.query_gds("wt1a", timeout=7, cache_dir=_cache_dir("geo_t"))
check("timeout=7 llega a las DOS GETs", [c["timeout"] for c in nett.calls] == [7, 7])

slept = []
net429 = FakeNet(_geo_router, plan=[_http_error(429, {"Retry-After": "2"}), "fixture", "fixture"])
geo._get = net429
out_r = _with_retry_sleep_stub(lambda: geo.query_gds("wt1a", cache_dir=_cache_dir("geo_r")), slept)
check("429 con Retry-After: 2 -> espera 2 s (stub), reintenta UNA vez, success, retries_429 = 1, 3 llamadas",
      out_r["status"] == "success" and out_r["retries_429"] == 1 and slept == [2.0] and len(net429.urls) == 3,
      f"slept={slept} n={len(net429.urls)}")
slept = []
geo._get = FakeNet(_geo_router, plan=[_http_error(429), _http_error(429)])
out_rr = _with_retry_sleep_stub(lambda: geo.query_gds("wt1a", cache_dir=_cache_dir("geo_rr")), slept)
check("429 + 429 -> exactamente 2 llamadas (1 reintento, NUNCA loop) y 'error' con http_status 429",
      out_rr["status"] == "error" and out_rr["http_status"] == 429 and out_rr["retries_429"] == 1 and slept == [1.0])

os.environ["WITT_GEO_RETMAX"] = "3"
os.environ["WITT_GEO_ORGANISM"] = ""
netv = FakeNet(_geo_router)
geo._get = netv
out_v = geo.query_gds("wt1a", cache_dir=_cache_dir("geo_v"))
check("env declaradas: WITT_GEO_RETMAX=3 -> retmax=3 en la URL; WITT_GEO_ORGANISM='' -> sin bloque de organismo (organism_sent None)",
      "retmax=3" in netv.urls[0] and out_v["data"]["retmax_sent"] == 3 and out_v["query_sent"] == "wt1a"
      and out_v["data"]["organism_sent"] is None, netv.urls[0][:140])
os.environ.pop("WITT_GEO_RETMAX", None)
os.environ.pop("WITT_GEO_ORGANISM", None)
check("query vacía -> 'error' declarado, cero llamadas",
      geo.query_gds("   ", cache_dir=_cache_dir("geo_q"))["status"] == "error")

# ======================================================================================================
# 2. Crossref + Unpaywall (unpaywall_crossref)
# ======================================================================================================
print("\n# unpaywall_crossref")
CR_JS, UP_JS = CR_FX["response"], UP_FX["response"]
check("fixture Crossref REAL (live) y fixture Unpaywall SINTÉTICO marcado en el nombre y en el cuerpo",
      CR_FX["_fixture"]["live"] is True and CR_JS["status"] == "ok"
      and UP_FX["_fixture"]["live"] is False and UP_FX["_fixture"]["synthetic"] is True
      and "SYNTHETIC" in (FIX / "unpaywall_SYNTHETIC_dev02071_20260915.json").name)


def _doi_router(url):
    if url.startswith(uc.CROSSREF_BASE):
        return CR_JS
    if url.startswith(uc.UNPAYWALL_BASE):
        return UP_JS
    raise AssertionError(f"URL inesperada: {url}")


check("normalize_doi: minúsculas y sin prefijos https://doi.org/ · doi: · dx.doi.org; basura -> None",
      uc.normalize_doi("https://doi.org/10.1242/DEV.02071") == "10.1242/dev.02071"
      and uc.normalize_doi("doi:10.1242/dev.02071") == "10.1242/dev.02071"
      and uc.normalize_doi("http://dx.doi.org/10.1242/dev.02071") == "10.1242/dev.02071"
      and uc.normalize_doi("PMID:123") is None and uc.normalize_doi("") is None)

netc = FakeNet(_doi_router)
uc._get = netc
out_c = uc.query_crossref("https://doi.org/10.1242/dev.02071", cache_dir=_cache_dir("cr1"))
dc = out_c.get("data", {})
check("Crossref fixture -> success: título, journal Development, año 2005 (published-print), type journal-article, 2 autores, 68 citas (medición)",
      out_c["status"] == "success" and dc["title"].startswith("Fgf signals from a novel signaling center")
      and dc["journal"] == "Development" and dc["year"] == 2005 and dc["type"] == "journal-article"
      and dc["n_authors"] == 2 and dc["authors_truncated"] is False and dc["is_referenced_by_count"] == 68
      and dc["doi"] == "10.1242/dev.02071" and dc["url"] == "https://doi.org/10.1242/dev.02071"
      and dc["identifier_provenance"] == "crossref-works" and out_c["evidence_kind"] == "paper-metadata",
      f"status={out_c['status']} err={out_c.get('error')}")
check("abstract de Crossref: etiquetas JATS quitadas, fuente declarada 'crossref-jats-stripped', corte declarado",
      dc["abstract"] and "<" not in dc["abstract"] and dc["abstract_source"] == "crossref-jats-stripped"
      and isinstance(dc["abstract_truncated"], bool), (dc["abstract"] or "")[:80])
check("sin contacto en env: URL sin mailto, contact 'unset', UNA GET, url_sent pública",
      "mailto" not in netc.urls[0] and out_c["contact"] == "unset" and out_c["contact_source"] is None
      and out_c["n_http_gets"] == 1 and out_c["url_sent"] == "https://api.crossref.org/works/10.1242/dev.02071")
check("throttle por host declarado (api.crossref.org, 0.2 s constante) y retry_available True",
      out_c["throttle"]["host"] == "api.crossref.org" and out_c["throttle"]["min_interval_s"] == 0.2
      and out_c["retry_available"] is True)

netc2 = FakeNet(_doi_router)
uc._get = netc2
out_c2 = uc.query_crossref("10.1242/dev.02071", cache_dir=_cache_dir("cr1"))
check("caché por día Crossref: segunda llamada cache_hit True, cero red, mismo registro",
      out_c2["cache_hit"] is True and netc2.calls == [] and out_c2["data"] == dc and out_c2["cached_at"])

os.environ["WITT_NCBI_EMAIL"] = EMAIL
netm = FakeNet(_doi_router)
uc._get = netm
out_m = uc.query_crossref("10.1242/dev.02071", cache_dir=_cache_dir("cr_m"))
check("con WITT_NCBI_EMAIL (fallback): mailto=<env> viaja en la URL y en el UA, contact 'declared' con fuente nombrada, "
      "y la dirección NO aparece en la salida ni en el archivo de caché",
      f"mailto={EMAIL.replace('@', '%40')}" in netm.urls[0] and netm.calls[0]["kw"].get("ua_suffix") == EMAIL
      and out_m["contact"] == "declared" and out_m["contact_source"] == "WITT_NCBI_EMAIL"
      and EMAIL not in json.dumps(out_m)
      and EMAIL not in (TMP / "cr_m" / Path(out_m["cache_path"]).name).read_text(encoding="utf-8"))
os.environ.pop("WITT_NCBI_EMAIL", None)

uc._get = FakeNet(_doi_router, plan=[_http_error(404, reason="Not Found")])
out_404 = uc.query_crossref("10.9999/no.existe.xyz", cache_dir=_cache_dir("cr_404"))
check("no-match: HTTP 404 en Crossref -> 'no-match' con http_status 404 (la agencia no conoce el DOI; NO es error)",
      out_404["status"] == "no-match" and out_404["http_status"] == 404 and "error" not in out_404)
net404b = FakeNet(_doi_router)
uc._get = net404b
out_404b = uc.query_crossref("10.9999/no.existe.xyz", cache_dir=_cache_dir("cr_404"))
check("el 404 se cachea el mismo día: segunda consulta -> 'no-match' desde caché, cero red",
      out_404b["status"] == "no-match" and out_404b["cache_hit"] is True and net404b.calls == [])

uc._get = FakeNet(_doi_router, plan=[_http_error(503, reason="Service Unavailable")])
out_ce = uc.query_crossref("10.1242/dev.02071", cache_dir=_cache_dir("cr_e"))
check("error de red Crossref: 503 -> 'error' con http_status declarado, sin data",
      out_ce["status"] == "error" and out_ce["http_status"] == 503 and "data" not in out_ce)
uc._get = FakeNet(_doi_router, plan=[{"status": "weird"}])
check("payload sin status 'ok'/message -> 'error' declarado (no un success con campos None)",
      uc.query_crossref("10.1242/dev.02071", cache_dir=_cache_dir("cr_w"))["status"] == "error")

slept = []
net429c = FakeNet(_doi_router, plan=[_http_error(429), "fixture"])
uc._get = net429c
out_rc = _with_retry_sleep_stub(lambda: uc.query_crossref("10.1242/dev.02071", cache_dir=_cache_dir("cr_r")), slept)
check("Crossref 429 -> UN reintento (espera default 1 s), success, retries_429 1, 2 llamadas",
      out_rc["status"] == "success" and out_rc["retries_429"] == 1 and slept == [1.0] and len(net429c.urls) == 2)

# --- Unpaywall ---------------------------------------------------------------------------------------
os.environ.pop("WITT_UNPAYWALL_EMAIL", None)
netu0 = FakeNet(_doi_router)
uc._get = netu0
out_u0 = uc.query_unpaywall("10.1242/dev.02071", cache_dir=_cache_dir("up0"))
check("Unpaywall sin WITT_UNPAYWALL_EMAIL -> 'tool-unavailable' con reason declarado y CERO llamadas (ningún correo inventado)",
      out_u0["status"] == "tool-unavailable" and "WITT_UNPAYWALL_EMAIL unset" in out_u0["reason"]
      and netu0.calls == [] and out_u0["contact"] == "unset")
os.environ["WITT_NCBI_EMAIL"] = EMAIL
out_u0b = uc.query_unpaywall("10.1242/dev.02071", cache_dir=_cache_dir("up0b"))
check("WITT_NCBI_EMAIL NO sirve como correo de Unpaywall (sólo WITT_UNPAYWALL_EMAIL): sigue 'tool-unavailable'",
      out_u0b["status"] == "tool-unavailable")
os.environ.pop("WITT_NCBI_EMAIL", None)

os.environ["WITT_UNPAYWALL_EMAIL"] = EMAIL
netu = FakeNet(_doi_router)
uc._get = netu
out_u = uc.query_unpaywall("10.1242/dev.02071", cache_dir=_cache_dir("up1"))
du = out_u.get("data", {})
check("Unpaywall con email, fixture SINTÉTICO -> success: is_oa True, oa_status bronze, best_oa_url, host_type publisher, n_oa_locations 1",
      out_u["status"] == "success" and du["is_oa"] is True and du["oa_status"] == "bronze"
      and du["best_oa_url"] == "https://example.invalid/synthetic-oa" and du["host_type"] == "publisher"
      and du["n_oa_locations"] == 1 and du["journal_is_oa"] is False and du["identifier_provenance"] == "unpaywall-v2"
      and out_u["evidence_kind"] == "oa-location", f"status={out_u['status']} err={out_u.get('error')}")
check("email=<env> viaja SÓLO en la URL; url_sent es la pública sin email; contact 'declared' desde WITT_UNPAYWALL_EMAIL; "
      "la dirección no está en la salida",
      f"email={EMAIL.replace('@', '%40')}" in netu.urls[0] and out_u["url_sent"] == "https://api.unpaywall.org/v2/10.1242/dev.02071"
      and out_u["contact"] == "declared" and out_u["contact_source"] == "WITT_UNPAYWALL_EMAIL"
      and EMAIL not in json.dumps(out_u))
uc._get = FakeNet(_doi_router, plan=[_http_error(404)])
check("Unpaywall 404 -> 'no-match'", uc.query_unpaywall("10.9999/x.y", cache_dir=_cache_dir("up404"))["status"] == "no-match")
uc._get = FakeNet(_doi_router, plan=[urllib.error.URLError("conn refused")])
check("Unpaywall error de red -> 'error' declarado",
      uc.query_unpaywall("10.1242/dev.02071", cache_dir=_cache_dir("up_e"))["status"] == "error")

# --- combinado ---------------------------------------------------------------------------------------
netd = FakeNet(_doi_router)
uc._get = netd
out_d = uc.query_doi("10.1242/dev.02071", cache_dir=_cache_dir("doi1"))
check("query_doi: dos filas independientes (crossref success, unpaywall success), status = el de Crossref, n_http_gets 2",
      out_d["status"] == "success" and out_d["data"]["crossref"]["status"] == "success"
      and out_d["data"]["unpaywall"]["status"] == "success" and out_d["n_http_gets"] == 2 and out_d["doi"] == "10.1242/dev.02071")
uc._get = FakeNet(_doi_router, plan=[_http_error(503)])
out_d2 = uc.query_doi("10.1242/dev.02071", cache_dir=_cache_dir("doi2"))
check("§6 no-hang: Crossref cae (503) y Unpaywall sigue: filas 'error' + 'success', status global 'error' con error nombrado",
      out_d2["status"] == "error" and out_d2["data"]["crossref"]["status"] == "error"
      and out_d2["data"]["unpaywall"]["status"] == "success" and out_d2["error"].startswith("HTTPError"))
out_d3 = uc.query_doi("10.1242/dev.02071", cache_dir=_cache_dir("doi3"), sources=("crossref",))
check("sources=('crossref',): la fila de Unpaywall queda 'not-requested' (no 'tool-unavailable', no 'error')",
      out_d3["data"]["unpaywall"]["status"] == "not-requested" and out_d3["status"] == "success")
netdz = FakeNet(_doi_router)
uc._get = netdz
out_dz = uc.query_doi("10.1242/dev.02071", timeout=0, cache_dir=_cache_dir("doi_z"))
check("timeout<=0 -> ambas filas 'skipped-budget', cero llamadas",
      out_dz["status"] == "skipped-budget" and out_dz["data"]["unpaywall"]["status"] == "skipped-budget" and netdz.calls == [])
check("DOI inválido -> 'error' declarado sin llamadas",
      uc.query_doi("no-es-un-doi", cache_dir=_cache_dir("doi_bad"))["status"] == "error")
os.environ.pop("WITT_UNPAYWALL_EMAIL", None)

# ======================================================================================================
# 3. OpenAlex (openalex_search)
# ======================================================================================================
print("\n# openalex_search")
OA_JS, OA_HDRS = OA_FX["response"], OA_FX["headers"]
check("fixture OpenAlex real: meta.count 225, 5 results, cabeceras X-RateLimit-* de crédito GRABADAS",
      OA_FX["_fixture"]["live"] is True and OA_JS["meta"]["count"] == 225 and len(OA_JS["results"]) == 5
      and OA_HDRS and any(k.lower().startswith("x-ratelimit") for k in OA_HDRS))


def _oa_router(url):
    if url.startswith(oa.BASE):
        return OA_JS
    raise AssertionError(f"URL inesperada: {url}")


neto = FakeNet(_oa_router, headers=OA_HDRS)
oa._get = neto
out_o = oa.query_openalex("wt1a zebrafish pronephros", cache_dir=_cache_dir("oa1"))
do = out_o.get("data", {})
check("OpenAlex fixture -> success, n_found_total 225 (medición), n_returned 5, per_page_sent 5, UNA GET con select=",
      out_o["status"] == "success" and do["n_found_total"] == 225 and do["n_returned"] == 5 and do["per_page_sent"] == 5
      and out_o["n_http_gets"] == 1 and "per-page=5" in neto.urls[0] and "&select=" in neto.urls[0],
      f"status={out_o['status']} err={out_o.get('error')}")
w0 = do["records"][0]
check("registro: openalex_id W1993074652, doi 10.1016/j.ydbio.2007.06.022 (sin prefijo), pmid 17651719, año 2007, journal Developmental Biology, is_oa True",
      w0["openalex_id"] == "W1993074652" and w0["doi"] == "10.1016/j.ydbio.2007.06.022" and w0["pmid"] == "17651719"
      and w0["year"] == 2007 and w0["journal"] == "Developmental Biology" and w0["is_oa"] is True
      and w0["n_authors"] == 3 and w0["identifier_provenance"] == "openalex-works" and out_o["evidence_kind"] == "paper",
      json.dumps(w0)[:200])
_inv1 = OA_JS["results"][1]["abstract_inverted_index"]
_first_word = min(((min(p), w) for w, p in _inv1.items() if p))[1]   # la palabra en la posición mínima del fixture
_n_words = sum(len(p) for p in _inv1.values())
check("abstract: ausente -> None + abstract_source None (ausencia declarada); presente -> reconstruido del índice invertido "
      "(empieza por la palabra en posición 0 del fixture, mismo número de palabras) y declarado",
      w0["abstract"] is None and w0["abstract_source"] is None
      and bool(do["records"][1]["abstract"]) and do["records"][1]["abstract_source"] == "inverted-index-reconstructed"
      and do["records"][1]["abstract"].startswith(_first_word)
      and len(do["records"][1]["abstract"].split(" ")) == _n_words and do["records"][1]["abstract_truncated"] is False,
      (do["records"][1]["abstract"] or "")[:60])
check("reconstruct_abstract: determinista por posición; vacío/None -> None",
      oa.reconstruct_abstract({"world": [1], "hello": [0]}) == "hello world" and oa.reconstruct_abstract(None) is None
      and oa.reconstruct_abstract({}) is None)
check("credits_headers = MEDICIÓN de las cabeceras X-RateLimit-* tal como vinieron; cost_usd_reported de meta con fuente",
      out_o["credits_headers"] == OA_HDRS and do["cost_usd_reported"] == 0.001
      and do["cost_usd_reported_source"] == "openalex meta.cost_usd")
check("sin OPENALEX_API_KEY: api_key_present False y ningún header api_key enviado; sin contacto: sin mailto, contact 'unset'",
      out_o["api_key_present"] is False and neto.calls[0]["kw"].get("api_key") is None
      and "mailto" not in neto.urls[0] and out_o["contact"] == "unset")

neto2 = FakeNet(_oa_router)
oa._get = neto2
out_o2 = oa.query_openalex("wt1a zebrafish pronephros", cache_dir=_cache_dir("oa1"))
check("caché por día OpenAlex: cache_hit True, cero red, credits_headers servidos desde la caché (medición de ESE día)",
      out_o2["cache_hit"] is True and neto2.calls == [] and out_o2["data"]["records"] == do["records"]
      and out_o2["credits_headers"] == OA_HDRS)

os.environ["OPENALEX_API_KEY"] = "smoke-fake-key-not-a-secret"
os.environ["WITT_UNPAYWALL_EMAIL"] = EMAIL
netk = FakeNet(_oa_router)
oa._get = netk
out_k = oa.query_openalex("wt1a zebrafish pronephros", cache_dir=_cache_dir("oa_k"))
check("con OPENALEX_API_KEY y contacto: la llave va en el HEADER api_key (no en la URL) y sólo se declara su presencia; "
      "mailto en la URL y contact 'declared'; ni llave ni correo aparecen en la salida",
      netk.calls[0]["kw"].get("api_key") == "smoke-fake-key-not-a-secret" and "api_key" not in netk.urls[0]
      and out_k["api_key_present"] is True and f"mailto={EMAIL.replace('@', '%40')}" in netk.urls[0]
      and out_k["contact"] == "declared" and out_k["contact_source"] == "WITT_UNPAYWALL_EMAIL"
      and "smoke-fake-key" not in json.dumps(out_k) and EMAIL not in json.dumps(out_k))
os.environ.pop("OPENALEX_API_KEY", None)
os.environ.pop("WITT_UNPAYWALL_EMAIL", None)

oa._get = FakeNet(_oa_router, plan=[{"meta": {"count": 0, "per_page": 5}, "results": []}])
out_onm = oa.query_openalex("xyzzy_nada_zebrafish", cache_dir=_cache_dir("oa_nm"))
check("no-match: meta.count 0 / results [] -> 'no-match' con n_found_total 0 y records []",
      out_onm["status"] == "no-match" and out_onm["data"]["n_found_total"] == 0 and out_onm["data"]["records"] == [])
oa._get = FakeNet(_oa_router, plan=[_http_error(503, reason="Service Unavailable")])
out_oe = oa.query_openalex("wt1a", cache_dir=_cache_dir("oa_e"))
check("error de red: 503 -> 'error' con http_status, sin records",
      out_oe["status"] == "error" and out_oe["http_status"] == 503 and "records" not in out_oe["data"])
oa._get = FakeNet(_oa_router, plan=[urllib.error.URLError("timed out")])
check("URLError -> 'error' declarado", oa.query_openalex("wt1a", cache_dir=_cache_dir("oa_u"))["status"] == "error")
oa._get = FakeNet(_oa_router, plan=[{"meta": {"count": 3}}])
check("payload sin results[] -> 'error' declarado (no un no-match fabricado)",
      oa.query_openalex("wt1a", cache_dir=_cache_dir("oa_w"))["status"] == "error")
netoz = FakeNet(_oa_router)
oa._get = netoz
out_oz = oa.query_openalex("wt1a", timeout=0, cache_dir=_cache_dir("oa_z"))
check("timeout<=0 -> 'skipped-budget', cero llamadas", out_oz["status"] == "skipped-budget" and netoz.calls == [])
slept = []
net429o = FakeNet(_oa_router, plan=[_http_error(429, {"Retry-After": "3"}), "fixture"], headers=OA_HDRS)
oa._get = net429o
out_ro = _with_retry_sleep_stub(lambda: oa.query_openalex("wt1a zebrafish pronephros", cache_dir=_cache_dir("oa_r")), slept)
check("OpenAlex 429 con Retry-After 3 -> UN reintento, success, retries_429 1, 2 llamadas",
      out_ro["status"] == "success" and out_ro["retries_429"] == 1 and slept == [3.0] and len(net429o.urls) == 2)
os.environ["WITT_OPENALEX_PER_PAGE"] = "2"
netp = FakeNet(_oa_router)
oa._get = netp
out_p = oa.query_openalex("wt1a", cache_dir=_cache_dir("oa_p"))
check("WITT_OPENALEX_PER_PAGE=2 -> per-page=2 en la URL y per_page_sent 2; argumento per_page=7 gana sobre la env",
      "per-page=2" in netp.urls[0] and out_p["data"]["per_page_sent"] == 2
      and oa.resolve_per_page(7) == 7 and oa.resolve_per_page(999) == 200)
os.environ.pop("WITT_OPENALEX_PER_PAGE", None)
check("query vacía -> 'error' declarado", oa.query_openalex("  ", cache_dir=_cache_dir("oa_q"))["status"] == "error")

# ======================================================================================================
# 4. transversal
import re as _re_mail  # noqa: E402
_EMAIL_RX = _re_mail.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}")
_FX_DIR = ROOT / "rag_index" / "query_service" / "fixtures"
_mails = {p.name: _EMAIL_RX.findall(p.read_text(encoding="utf-8")) for p in sorted(_FX_DIR.glob("*.json"))}
_mails = {k: v for k, v in _mails.items() if v}
_oa_fx_cut = OA_FX.get("_fixture", {}).get("cut") or {}
check("transversal (corrector ADR-0080): CERO correos en fixtures/*.json (grep de e-mail == 0 en todos); el fixture de OpenAlex "
      "declara el recorte {fields raw_affiliation_strings/raw_affiliation_string, n_fields_dropped, reason} y n_authors sigue "
      "saliendo de authorships (3 en el primer work)",
      _mails == {} and set(_oa_fx_cut.get("fields") or []) == {"raw_affiliation_strings", "raw_affiliation_string"}
      and _oa_fx_cut.get("n_fields_dropped", 0) > 0 and "emails" in _oa_fx_cut.get("reason", "")
      and len(OA_FX["response"]["results"][0]["authorships"]) == 3,
      json.dumps(_mails)[:200])
_cache_txt = json.dumps({"results": [{"authorships": [{"raw_affiliation_strings": ["Lab X. a.b@uni.edu"],
                                                       "affiliations": [{"raw_affiliation_string": "Lab X. a.b@uni.edu"}]}]}]})
_stripped, _n_drop = oa.strip_affiliation_strings(json.loads(_cache_txt))
_red, _n_red = oa.redact_emails("mail me at x.y@z.org or w@q.io")
check("openalex_search (corrector): strip_affiliation_strings quita los 2 campos de afiliacion cruda (contados) y redact_emails "
      "redacta y CUENTA correos — la cache del dia (mcp_cache) nunca guarda una direccion",
      _n_drop == 2 and "a.b@uni.edu" not in json.dumps(_stripped) and _n_red == 2 and "@" not in _red
      and oa.AFFILIATION_FIELDS_DROPPED == ("raw_affiliation_strings", "raw_affiliation_string"))
# ======================================================================================================
print("\n# transversal")
check("las tres tools siguen stdlib-puras: ningún import fuera de stdlib (requests/httpx/tooluniverse ausentes)",
      not any(m in sys.modules for m in ("requests", "httpx", "tooluniverse")))
check("las tres tools declaran su raíz de caché = <repo>/mcp_cache y NINGÚN archivo nuevo del smoke cayó ahí",
      geo.CACHE_DIR == uc.CACHE_DIR == oa.CACHE_DIR == ROOT / "mcp_cache"
      and not list((ROOT / "mcp_cache").glob("raw_geo_gds_*_20260915.json"))
      and not list((ROOT / "mcp_cache").glob("raw_crossref_*.json"))
      and not list((ROOT / "mcp_cache").glob("raw_unpaywall_*.json"))
      and not list((ROOT / "mcp_cache").glob("raw_openalex_*.json")))
check("registro ToolUniverse presente en las tres (clase con name/description/input_schema/run) sin requerir el paquete",
      all(hasattr(getattr(m, cls), a) for m, cls in ((geo, "GEO_gds_search_workspace"),
                                                     (uc, "DOI_resolve_crossref_unpaywall_workspace"),
                                                     (oa, "OpenAlex_search_works_workspace"))
          for a in ("name", "description", "input_schema", "run")))

shutil.rmtree(TMP, ignore_errors=True)
os.environ.pop("WITT_NCBI_MIN_INTERVAL_S", None)
n_pass = sum(CHECKS)
print(f"\n{n_pass}/{len(CHECKS)} PASS")
sys.exit(0 if n_pass == len(CHECKS) else 1)

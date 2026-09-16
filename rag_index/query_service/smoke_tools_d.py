"""smoke_tools_d.py — gate determinista del tool Layer 0 `brave_web_search` (ADR-0084 rebanada W1; molde
smoke_tools_c).

Qué MIDE (fila `smoke_tools_d.py` de los gates NO-SPEND del ADR-0084):
  D0  sin BRAVE_API_KEY -> 'tool-unavailable', CERO GETs, api_key_present False, url_sent None
  D1  fixture (SINTÉTICO hoy; si existe uno LIVE lo prefiere y lo declara) -> 'success'; results[] SÓLO
      {url, title, host, age, page_age}; `fields_dropped` ∋ description/extra_snippets (política) y
      `fields_dropped_measured` (medido); el sobre de caché SÍ conserva `description` (raw íntegro) y la
      SALIDA no (substring == 0)
  D2  web.results [] / web ausente -> 'no-match' (buscó y no halló ≠ error)
  D3  503 -> 'error' con http_status y error_kind, nada cacheado
  D4  401/403 -> 'error: auth (HTTP n)', error_kind 'auth', auth_failed True (cortacircuito para el harness)
  D5  429 + Retry-After 2 -> UN reintento (sleep stub == 2.0); 2º 429 -> error 'rate-limit'; Retry-After
      absurdo -> tope 60 s
  D6  cuerpo HTML con HTTP 200 -> 'error: NonJSONBody (content-type text/html) — HTML/captcha declared', el HTML
      NO está en la salida
  D7  timeout <= 0 -> 'skipped-budget', 0 GETs
  D8  2ª llamada del día -> cache_hit True, 0 GETs; cache_probe positivo/negativo sin red ni llave
  D9  q de 500 chars -> query_truncated True, <= 400 (tope NUESTRO, WITT_WEB_MAX_QUERY_CHARS)
  D10 la llave fake JAMÁS en salida / caché / fixture / url_sent; SÓLO en la cabecera X-Subscription-Token
  D11 dos llamadas con reloj falso -> throttle.waited_s >= 0.999 (WITT_WEB_MIN_INTERVAL_S default 1.0)
  D12 url_sent sin token y SIN result_filter/text_decorations/spellcheck/extra_snippets/offset/summary;
      params_sent == documentados
  D13 count 50 -> 20; freshness 'zz' -> no enviado + freshness_ignored; country/search_lang validados
  D14 422 con cuerpo que nombra `freshness` -> 'error: HTTP 422 unprocessable — freshness'
  D15 query.altered ≠ original -> query_altered_by_provider True
  D16 `_fixture.synthetic True` declarado (o LIVE preferido y declarado)
  + shape-mismatch, URLError, query vacía, vocabulario ⊆ SOURCE_STATES (UNA verdad: search_harness), stdlib puro,
    mcp_cache del repo intacto, WITT_MCP_CACHE_DIR honrado, registro ToolUniverse presente.

100% OFFLINE: `bws._get` (la ÚNICA costura de red) se monkeypatchea para servir el fixture; `bws._urlopen`
(indirección interna de `_get`) se sustituye por una respuesta falsa para probar la construcción de la petición
(cabeceras, no-JSON); urllib.request.urlopen queda BLOQUEADO Y CONTADO == 0 durante todo el smoke;
net_throttle._sleep/_monotonic se stubean SÓLO donde se mide. Toda caché va a un tempdir. Cero red, cero gasto,
cero mutación de mcp_cache ni de la DATA INAMOVIBLE. Exit 0 = todo PASS.

Corre:  python rag_index/query_service/smoke_tools_d.py
"""
import email.message
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
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

# --- máscara offline (disciplina de la casa) --------------------------------------------------------------
os.environ["NEO4J_URI"] = ""
os.environ["RAG_BACKEND"] = "sparse"
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["WITT_RUN_ORIGIN"] = "smoke"
os.environ["BRAVE_API_KEY"] = ""          # D0: la máscara la deja VACÍA (== unset para la tool)
for _k in ("WITT_WEB_MAX_RESULTS", "WITT_WEB_MAX_QUERY_CHARS", "WITT_WEB_COUNTRY", "WITT_WEB_LANG",
           "WITT_WEB_FRESHNESS", "WITT_WEB_MIN_INTERVAL_S", "WITT_WEB_LOCATOR"):
    os.environ.pop(_k, None)
TMP = Path(tempfile.mkdtemp(prefix="witt-smoke-tools-d-"))
if not os.environ.get("WITT_MCP_CACHE_DIR", "").strip():
    os.environ["WITT_MCP_CACHE_DIR"] = str(TMP / "envcache")   # jamás la mcp_cache del repo
ENV_CACHE = Path(os.environ["WITT_MCP_CACHE_DIR"])
os.environ["WITT_WEB_MIN_INTERVAL_S"] = "0"   # el tiempo del throttle se mide SÓLO en D11 (reloj falso)

# ---- cero red: urlopen bloqueado y CONTADO durante TODO el smoke (patrón smoke_search_harness / ADR-0082 L.3) --
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
    raise RuntimeError("network blocked by smoke_tools_d (offline gate)")


_urlreq.urlopen = _urlopen_blocked

from lib import net_throttle  # noqa: E402
from lib import search_harness as sh  # noqa: E402  (SOURCE_STATES: UNA verdad; import liviano, sin red)


def _load(name):
    """Carga POR RUTA, igual que search_harness._load_tool (el directorio va con punto: no es paquete)."""
    spec = importlib.util.spec_from_file_location(f"_witt_ws_{name}", TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bws = _load("brave_web_search")
_GET_REAL = bws._get
_URLOPEN_SEAM_AT_IMPORT = bws._urlopen

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


def _fx(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --- fixture: prefiere LIVE si existe, si no el SINTÉTICO — y lo DECLARA (D16) ---------------------------------
_cands = sorted(FIX.glob("brave_web_search_*.json"))
_live = [p for p in _cands if (_fx(p).get("_fixture") or {}).get("live") is True]
_synth = [p for p in _cands if "SYNTHETIC" in p.name]
FX_PATH = _live[-1] if _live else _synth[0]
FX = _fx(FX_PATH)
PROVENANCE = "live" if _live else "synthetic"
FX_JS = FX["response"]
FX_RESULTS = [r for r in FX_JS["web"]["results"] if isinstance(r, dict)]
FX_URLS = [r["url"] for r in FX_RESULTS if isinstance(r.get("url"), str) and r["url"].startswith("http")]
FX_TEXT = FX_PATH.read_text(encoding="utf-8")
Q = FX["_fixture"].get("query_sent") or FX_JS["query"]["original"]
FAKE = "smoke-fake-brave-token-not-a-secret-0084"
EXPECTED_HOSTS = {"doi.org", "pubmed.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov", "europepmc.org", "zfin.org",
                  "www.ensembl.org", "www.uniprot.org", "www.ncbi.nlm.nih.gov", "link.springer.com",
                  "www.researchgate.net", "en.wikipedia.org"}


def _http_error(code, headers=None, reason="err", body=b""):
    hdrs = None
    if headers:
        hdrs = email.message.Message()
        for k, v in headers.items():
            hdrs[k] = v
    return urllib.error.HTTPError("https://x.invalid/", code, reason, hdrs, io.BytesIO(body))


class FakeNet:
    """Sustituye bws._get: sirve por plan y GRABA cada llamada (url, timeout, kwargs incl. api_key).
    `plan`: lista de respuestas por llamada (dict json | Exception | 'fixture'); `headers` crudas devueltas
    cuando la tool pide with_headers=True."""

    def __init__(self, plan=None, headers=None, js=None):
        self.plan, self.headers, self.calls, self.js = list(plan or []), headers, [], js if js is not None else FX_JS

    def __call__(self, url, timeout=None, with_headers=True, **kw):
        self.calls.append({"url": url, "timeout": timeout, "kw": kw})
        step = self.plan.pop(0) if self.plan else "fixture"
        if isinstance(step, Exception):
            raise step
        js = self.js if step == "fixture" else step
        return (js, self.headers) if with_headers else js

    @property
    def urls(self):
        return [c["url"] for c in self.calls]


class FakeResp:
    """Respuesta falsa para bws._urlopen (prueba la construcción de la petición y el parseo del cuerpo)."""

    def __init__(self, body, headers=None):
        self._body = body
        self.headers = email.message.Message()
        for k, v in (headers or {}).items():
            self.headers[k] = v

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _cache_dir(label):
    d = TMP / label
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_file(out):
    p = Path(out["cache_path"])
    return p if p.is_absolute() else ROOT / p


_real_sleep = net_throttle._sleep


def _with_retry_sleep_stub(fn, slept):
    """Stub SÓLO de las esperas del reintento 429 (>= 0.5 s); el throttle está a 0 s por env."""
    net_throttle._sleep = lambda secs: slept.append(secs) if secs >= 0.5 else _real_sleep(secs)
    try:
        return fn()
    finally:
        net_throttle._sleep = _real_sleep


RATE_HDRS = {"X-RateLimit-Limit": "1, 15000", "X-RateLimit-Policy": "1;w=1, 15000;w=2592000",
             "X-RateLimit-Remaining": "0, 14999", "X-RateLimit-Reset": "1, 2591999"}

# ======================================================================================================
print(f"\n# fixture ({PROVENANCE}: {FX_PATH.name})")
_meta = FX.get("_fixture") or {}
if PROVENANCE == "synthetic":
    check("D16 fixture SINTÉTICO declarado en el NOMBRE y en el CUERPO: live False, synthetic True, shape_source con la URL "
          "de la doc de Brave y la fecha 2026-09-16, recorded_by nombra ADR-0084 W1, fetched_at null",
          "SYNTHETIC" in FX_PATH.name and _meta.get("live") is False and _meta.get("synthetic") is True
          and "api-dashboard.search.brave.com/app/documentation/web-search/responses" in (_meta.get("shape_source") or "")
          and "2026-09-16" in (_meta.get("shape_source") or "") and "ADR-0084 W1" in (_meta.get("recorded_by") or "")
          and FX.get("fetched_at") is None, json.dumps(_meta)[:160])
else:
    check("D16 fixture LIVE presente: se PREFIERE sobre el sintético y se declara (provenance 'live'); recorded_by = la tool",
          _meta.get("live") is True and _meta.get("synthetic") is False
          and "brave_web_search.py --record-fixture" in (_meta.get("recorded_by") or ""), json.dumps(_meta)[:160])
check("forma documentada: response.type 'search', query.original str, web.results[] >= 10 con url/title/description en todos; "
      ">= 1 con extra_snippets (para medir el corte); sobre con url SIN token, http_status 200, headers X-RateLimit-*",
      FX_JS.get("type") == "search" and isinstance(FX_JS["query"].get("original"), str) and len(FX_RESULTS) >= 10
      and all(isinstance(r.get("url"), str) and "title" in r and "description" in r for r in FX_RESULTS)
      and any(isinstance(r.get("extra_snippets"), list) and r["extra_snippets"] for r in FX_RESULTS)
      and FX["url"].startswith(bws.BASE) and "X-Subscription-Token" not in FX_TEXT and FX.get("http_status") == 200
      and any(k.lower().startswith("x-ratelimit") for k in (FX.get("headers") or {})),
      f"n_results={len(FX_RESULTS)}")
_hosts = {urllib.parse.urlparse(u).hostname for u in FX_URLS}
if PROVENANCE == "synthetic":
    check("hosts del fixture sintético cubren los 11 registros nombrados por el ADR (doi.org, pubmed, pmc, europepmc, zfin, "
          "ensembl, uniprot, GEO, publisher con DOI en ruta, researchgate, wikipedia); uno SIN meta_url (fallback de host) y "
          "uno con título > 120 (corte medido)",
          _hosts >= EXPECTED_HOSTS and any("meta_url" not in r for r in FX_RESULTS)
          and any(len(r.get("title") or "") > bws.TITLE_CAP for r in FX_RESULTS), f"hosts={sorted(_hosts)}")
else:
    check("hosts del fixture LIVE (medidos, declarados en el detalle)", len(_hosts) >= 1, f"hosts={sorted(_hosts)}")

# ======================================================================================================
print("\n# D0 — sin llave: cero red")
net0 = FakeNet()
bws._get = net0
out0 = bws.locate(Q, cache_dir=_cache_dir("d0"))
check("D0 BRAVE_API_KEY vacía/unset -> 'tool-unavailable', reason 'BRAVE_API_KEY unset (no request sent)', n_http_gets 0, "
      "api_key_present False, url_sent None, CERO llamadas a la costura, sin `data`",
      out0["status"] == "tool-unavailable" and out0["reason"] == bws.UNAVAILABLE_REASON and out0["n_http_gets"] == 0
      and out0["api_key_present"] is False and out0["url_sent"] is None and net0.calls == [] and "data" not in out0,
      json.dumps(out0)[:200])
os.environ.pop("BRAVE_API_KEY", None)
check("D0b BRAVE_API_KEY ausente del entorno (pop) -> mismo 'tool-unavailable' y cero llamadas",
      bws.locate(Q, cache_dir=_cache_dir("d0b"))["status"] == "tool-unavailable" and net0.calls == [])
prep0 = bws.prepare(Q)
probe0 = bws.cache_probe(Q, cache_dir=_cache_dir("d0"))
check("prepare()/cache_probe() son PUROS (sin llave, sin red): url_sent pública con q/count/search_lang, params_sent == "
      "['q','count','search_lang'], cache_hit False, cache_path declarado bajo el tempdir (insumo del --dry-run de W7)",
      prep0["url_sent"].startswith(bws.BASE + "?q=") and prep0["params_sent"] == ["q", "count", "search_lang"]
      and prep0["count_sent"] == 10 and prep0["search_lang_sent"] == "en" and probe0["cache_hit"] is False
      and str(TMP) in str(Path(probe0["cache_path"])) and net0.calls == [] and _NET_CALLS == [],
      prep0["url_sent"][:120])

# ======================================================================================================
print("\n# D1 — fixture con llave fake")
os.environ["BRAVE_API_KEY"] = FAKE
net1 = FakeNet(headers=RATE_HDRS)
bws._get = net1
out1 = bws.locate(Q, cache_dir=_cache_dir("d1"))
d1 = out1.get("data") or {}
res1 = d1.get("results") or []
check("D1 fixture -> 'success', n_results == URLs del fixture (en orden), UNA GET, api_key_present True, la llave viaja "
      "en kw api_key de la costura (cabecera) y NO en la URL",
      out1["status"] == "success" and d1["n_results"] == len(FX_URLS) and [r["url"] for r in res1] == FX_URLS
      and out1["n_http_gets"] == 1 and out1["api_key_present"] is True and net1.calls[0]["kw"].get("api_key") == FAKE
      and FAKE not in net1.urls[0], f"status={out1['status']} err={out1.get('error')} n={d1.get('n_results')}")
check("D1 results[] conservan EXACTAMENTE {url, title, host, age, page_age} (A.3) — ni description ni extra_snippets ni "
      "profile ni language en NINGÚN resultado",
      res1 and all(set(r) == set(bws.RESULT_KEYS_KEPT) for r in res1) and d1["fields_kept"] == list(bws.RESULT_KEYS_KEPT))
_descs = [str(r.get("description") or "")[:40] for r in FX_RESULTS if r.get("description")]
_snips = [s[:30] for r in FX_RESULTS for s in (r.get("extra_snippets") or []) if isinstance(s, str)]
_out1_txt = json.dumps(out1, ensure_ascii=False)
check("D1 corte MEDIDO en la SALIDA: fields_dropped (política) ∋ description/extra_snippets; fields_dropped_measured (medido) "
      "∋ description, extra_snippets, profile; NINGÚN fragmento de description/extra_snippets del fixture aparece en la salida",
      set(d1["fields_dropped"]) >= {"description", "extra_snippets"} and d1["fields_dropped"] == list(bws.FIELDS_DROPPED)
      and {"description", "extra_snippets", "profile"} <= set(d1["fields_dropped_measured"])
      and _descs and all(t not in _out1_txt for t in _descs) and all(s not in _out1_txt for s in _snips),
      f"measured={d1['fields_dropped_measured']}")
cf1 = _cache_file(out1)
env1 = json.loads(cf1.read_text(encoding="utf-8"))
check("D1 el sobre de caché es el RAW ÍNTEGRO (response == fixture, CON description y extra_snippets), con tool_version, "
      "fetched_at, url == url_sent (sin token), http_status 200, headers medidas y `cut.fields_dropped_from_output`; bajo el "
      "tempdir (mcp_cache intacto)",
      cf1.exists() and str(cf1).startswith(str(TMP)) and env1["response"] == FX_JS and env1["tool_version"] == "bws-1"
      and env1["fetched_at"] and env1["url"] == out1["url_sent"] and env1["http_status"] == 200 and env1["headers"] == RATE_HDRS
      and set(env1["cut"]["fields_dropped_from_output"]) >= {"description", "extra_snippets"}
      and any("description" in r for r in env1["response"]["web"]["results"]), out1["cache_path"])
_by_url = {r["url"]: r for r in res1}
_wiki = next((r for r in FX_RESULTS if "meta_url" not in r), None)
_meta_r = next((r for r in FX_RESULTS if isinstance(r.get("meta_url"), dict) and r["meta_url"].get("hostname")), None)
_long = next((r for r in FX_RESULTS if len(r.get("title") or "") > bws.TITLE_CAP), None)
if PROVENANCE == "synthetic":
    check("D1 host: con meta_url.hostname -> ese; sin meta_url -> urlparse(url).hostname (en.wikipedia.org); título > 120 -> "
          "recortado a 120 y CONTADO en n_titles_truncated; age/page_age copiados",
          _by_url[_meta_r["url"]]["host"] == _meta_r["meta_url"]["hostname"]
          and _by_url[_wiki["url"]]["host"] == urllib.parse.urlparse(_wiki["url"]).hostname
          and len(_by_url[_long["url"]]["title"]) == bws.TITLE_CAP and d1["n_titles_truncated"] == 1
          and _by_url[_meta_r["url"]]["age"] == _meta_r.get("age") and _by_url[_meta_r["url"]]["page_age"] == _meta_r.get("page_age"),
          f"wiki_host={_by_url.get((_wiki or {}).get('url'), {}).get('host')}")
else:
    check("D1 host derivado para TODOS los resultados (meta_url.hostname o urlparse) y títulos <= 120",
          all(r["host"] for r in res1) and all(len(r["title"] or "") <= bws.TITLE_CAP for r in res1))
check("D1 literales: identifier_provenance 'brave-web-search', evidence_kind 'web', tool_version 'bws-1', "
      "params_verified_as_of '2026-09-16'; data: count_sent 10 ('default'), search_lang_sent 'en', country/freshness None",
      out1["identifier_provenance"] == "brave-web-search" and out1["evidence_kind"] == "web" and out1["tool_version"] == "bws-1"
      and out1["params_verified_as_of"] == "2026-09-16" and d1["count_sent"] == 10 and d1["count_source"] == "default"
      and d1["search_lang_sent"] == "en" and d1["country_sent"] is None and d1["freshness_sent"] is None)
check("D1 rate_limit_headers NORMALIZADAS {limit, policy, remaining, reset} desde X-RateLimit-* (medición de ESA respuesta); "
      "throttle declarado {host api.search.brave.com, min_interval_s 0.0 (env), waited_s}",
      out1["rate_limit_headers"] == {"limit": "1, 15000", "policy": "1;w=1, 15000;w=2592000", "remaining": "0, 14999",
                                     "reset": "1, 2591999"}
      and out1["throttle"]["host"] == bws.HOST and out1["throttle"]["min_interval_s"] == 0.0
      and out1["throttle"]["min_interval_source"] == "env:WITT_WEB_MIN_INTERVAL_S" and out1["throttle"]["waited_s"] >= 0.0,
      json.dumps(out1["rate_limit_headers"]))
check("D15b fixture sin `query.altered` (o igual al original) -> query_altered_by_provider False, query_altered None|igual; "
      "more_results_available bool|None; query_original == la nuestra",
      d1["query_altered_by_provider"] is False and d1["query_original"] == Q
      and (d1["more_results_available"] is None or isinstance(d1["more_results_available"], bool)))

# --- D1g: la petición REAL de _get con _urlopen falso (cabeceras, JSON, token sólo en cabecera) ----------------
_captured = {}


def _fake_urlopen_json(req, timeout=None):
    _captured["req"], _captured["timeout"] = req, timeout
    return FakeResp(json.dumps(FX_JS).encode("utf-8"), dict(RATE_HDRS, **{"Content-Type": "application/json"}))


bws._urlopen = _fake_urlopen_json
js_g, hd_g = _GET_REAL(bws.prepare(Q)["url_sent"], timeout=7, with_headers=True, api_key=FAKE)
_req = _captured["req"]
check("D10/D1g _get REAL: cabeceras Accept application/json + X-Subscription-Token == llave (SÓLO ahí), User-Agent de la casa, "
      "SIN Accept-Encoding; la URL NO lleva la llave; timeout llega; JSON parseado y X-RateLimit-* devueltas crudas",
      _req.get_header("Accept") == "application/json" and _req.get_header("X-subscription-token") == FAKE
      and _req.get_header("Accept-encoding") is None and "witt-organo" in (_req.get_header("User-agent") or "")
      and FAKE not in _req.full_url and _captured["timeout"] == 7 and js_g == FX_JS
      and hd_g.get("X-RateLimit-Limit") == "1, 15000" and _NET_CALLS == [],
      f"headers={dict(_req.header_items())}")
check("la costura interna bws._urlopen quedó ligada al urlopen BLOQUEADO del smoke al importar (la ruta real de red es la "
      "contada) y _get sin api_key NO manda la cabecera",
      _URLOPEN_SEAM_AT_IMPORT is _urlopen_blocked
      and (lambda: (_GET_REAL(bws.BASE + "?q=x&count=1", with_headers=False, api_key=None),
                    _captured["req"].get_header("X-subscription-token") is None)[1])())
bws._urlopen = _URLOPEN_SEAM_AT_IMPORT

# ======================================================================================================
print("\n# D2..D7 — estados, jamás fundidos")
bws._get = FakeNet(plan=[dict(FX_JS, web={"type": "search", "results": []})])
out_nm = bws.locate("xyzzy nada zebrafish", cache_dir=_cache_dir("d2"))
check("D2 web.results [] -> 'no-match' (≠ error, ≠ success), n_results 0, results [], UNA GET; se cachea (fue un 200 que midió)",
      out_nm["status"] == "no-match" and out_nm["data"]["n_results"] == 0 and out_nm["data"]["results"] == []
      and out_nm["n_http_gets"] == 1 and _cache_file(out_nm).exists(), out_nm["status"])
bws._get = FakeNet(plan=[{"type": "search", "query": {"original": "x"}}])
check("D2b `web` AUSENTE -> 'no-match' declarado (no shape-mismatch: la doc lo permite)",
      bws.locate("sin web", cache_dir=_cache_dir("d2b"))["status"] == "no-match")

bws._get = FakeNet(plan=[_http_error(503, reason="Service Unavailable")])
out_e = bws.locate(Q, cache_dir=_cache_dir("d3"))
check("D3 HTTP 503 -> 'error' con http_status 503, error_kind 'http', error 'HTTPError: 503 …', sin results y NADA cacheado",
      out_e["status"] == "error" and out_e["http_status"] == 503 and out_e["error_kind"] == "http"
      and out_e["error"].startswith("HTTPError: 503") and "results" not in out_e["data"]
      and not list(_cache_dir("d3").glob("*.json")), out_e.get("error"))

bws._get = FakeNet(plan=[_http_error(401, reason="Unauthorized")])
out_401 = bws.locate(Q, cache_dir=_cache_dir("d4"))
bws._get = FakeNet(plan=[_http_error(403, reason="Forbidden")])
out_403 = bws.locate(Q, cache_dir=_cache_dir("d4b"))
check("D4 401 -> 'error' EXACTO 'auth (HTTP 401)', error_kind 'auth', auth_failed True, is_auth_error() True (cortacircuito "
      "para el harness: las demás consultas de la ronda quedan skipped-cap — C.5); 403 igual; nada cacheado; UNA llamada",
      out_401["status"] == "error" and out_401["error"] == "auth (HTTP 401)" and out_401["error_kind"] == bws.AUTH_ERROR_KIND
      and out_401["auth_failed"] is True and bws.is_auth_error(out_401) and out_401["http_status"] == 401
      and out_401["n_http_gets"] == 1 and out_403["error"] == "auth (HTTP 403)" and bws.is_auth_error(out_403)
      and not list(_cache_dir("d4").glob("*.json")) and not bws.is_auth_error(out_e), out_401.get("error"))

slept = []
net429 = FakeNet(plan=[_http_error(429, {"Retry-After": "2"}), "fixture"], headers=RATE_HDRS)
bws._get = net429
out_r = _with_retry_sleep_stub(lambda: bws.locate(Q, cache_dir=_cache_dir("d5")), slept)
check("D5 429 con Retry-After 2 -> espera 2 s (stub == [2.0]), reintenta UNA vez, 'success', retries_429 1, "
      "retry_after_s 2.0, 2 llamadas",
      out_r["status"] == "success" and out_r["retries_429"] == 1 and slept == [2.0] and out_r["retry_after_s"] == 2.0
      and len(net429.urls) == 2, f"slept={slept} n={len(net429.urls)}")
slept = []
bws._get = FakeNet(plan=[_http_error(429), _http_error(429)])
out_rr = _with_retry_sleep_stub(lambda: bws.locate(Q, cache_dir=_cache_dir("d5b")), slept)
slept2 = []
bws._get = FakeNet(plan=[_http_error(429, {"Retry-After": "9999"}), _http_error(429, {"Retry-After": "9999"})])
out_r3 = _with_retry_sleep_stub(lambda: bws.locate(Q, cache_dir=_cache_dir("d5c")), slept2)
check("D5b 429 + 429 -> EXACTAMENTE 2 llamadas (un reintento, NUNCA loop), 'error' http_status 429, error_kind 'rate-limit', "
      "espera default 1.0 sin Retry-After; Retry-After 9999 -> tope net_throttle.MAX_RETRY_AFTER_S (60 s)",
      out_rr["status"] == "error" and out_rr["http_status"] == 429 and out_rr["error_kind"] == "rate-limit"
      and out_rr["retries_429"] == 1 and out_rr["n_http_gets"] == 2 and slept == [1.0]
      and slept2 == [net_throttle.MAX_RETRY_AFTER_S] and out_r3["retry_after_s"] == 60.0
      and not list(_cache_dir("d5b").glob("*.json")), f"slept={slept} slept2={slept2}")

_HTML = b"<html><head><title>Just a moment...</title></head><body>captcha SYNTHETIC-HTML-MARKER</body></html>"
bws._get = _GET_REAL
bws._urlopen = lambda req, timeout=None: FakeResp(_HTML, {"Content-Type": "text/html; charset=utf-8"})
out_h = bws.locate(Q, cache_dir=_cache_dir("d6"))
bws._urlopen = _URLOPEN_SEAM_AT_IMPORT
check("D6 HTTP 200 con cuerpo HTML -> 'error' 'NonJSONBody (content-type text/html; charset=utf-8) — HTML/captcha declared', "
      "error_kind 'non-json-body', body_bytes medido, el HTML NO está en la salida, nada cacheado",
      out_h["status"] == "error" and out_h["error"] == "NonJSONBody (content-type text/html; charset=utf-8) — HTML/captcha declared"
      and out_h["error_kind"] == "non-json-body" and out_h["body_bytes"] == len(_HTML)
      and "SYNTHETIC-HTML-MARKER" not in json.dumps(out_h) and "<html" not in json.dumps(out_h)
      and not list(_cache_dir("d6").glob("*.json")), out_h.get("error"))

netz = FakeNet()
bws._get = netz
out_z = bws.locate(Q, timeout=0, cache_dir=_cache_dir("d7"))
out_z2 = bws.locate(Q, timeout=-1, cache_dir=_cache_dir("d7"))
check("D7 timeout <= 0 -> 'skipped-budget' con BudgetExhausted declarado y CERO llamadas (0 y -1)",
      out_z["status"] == "skipped-budget" and "BudgetExhausted" in out_z["error"] and out_z2["status"] == "skipped-budget"
      and netz.calls == [] and out_z["n_http_gets"] == 0)
nett = FakeNet()
bws._get = nett
bws.locate(Q, timeout=7, cache_dir=_cache_dir("d7t"))
check("timeout=7 llega a la costura", nett.calls[0]["timeout"] == 7)

# ======================================================================================================
print("\n# D8 — caché de lectura por día")
net8 = FakeNet()
bws._get = net8
out8 = bws.locate(Q, cache_dir=_cache_dir("d1"))     # mismo directorio que D1: mismo día, misma llave de caché
check("D8 2ª llamada del día -> cache_hit True, n_http_gets 0, cached_at declarado, CERO llamadas, mismos results, "
      "rate_limit_headers servidas desde la caché (medición de ESE día), throttle None (no hubo pacing)",
      out8["status"] == "success" and out8["cache_hit"] is True and out8["n_http_gets"] == 0 and out8["cached_at"]
      and net8.calls == [] and out8["data"]["results"] == res1 and out8["rate_limit_headers"] == out1["rate_limit_headers"]
      and out8["throttle"] is None and out8["cache_path"] == out1["cache_path"])
probe_hit = bws.cache_probe(Q, cache_dir=_cache_dir("d1"))
probe_miss = bws.cache_probe(Q + " otra cosa", cache_dir=_cache_dir("d1"))
probe_cnt = bws.cache_probe(Q, count=5, cache_dir=_cache_dir("d1"))
check("D8 cache_probe (B.5 paso 1, sin red): positivo para la misma (q, count, lang) con cache_path == el de D1 y cached_at; "
      "negativo para otra query y para otro count (la llave de caché incluye count/country/lang/freshness)",
      probe_hit["cache_hit"] is True and probe_hit["cache_path"] == out1["cache_path"] and probe_hit["cached_at"] == out8["cached_at"]
      and probe_miss["cache_hit"] is False and probe_cnt["cache_hit"] is False and net8.calls == [])
check("nombre de caché A.4: raw_brave_<slug(q,40)>_<sha8>_<YYYYMMDD>.json",
      __import__("re").match(r"^raw_brave_[a-z0-9-]{1,40}_[0-9a-f]{8}_\d{8}\.json$", Path(out1["cache_path"]).name) is not None,
      Path(out1["cache_path"]).name)

# ======================================================================================================
print("\n# D9/D12/D13 — parámetros: sólo documentados, topes NUESTROS declarados")
net9 = FakeNet()
bws._get = net9
long_q = ("wt1a pronephros podocyte " * 20)[:-1] + "."       # 25 chars x 20 = 500 chars exactos, sin espacio final
out9 = bws.locate(long_q, cache_dir=_cache_dir("d9"))
qs9 = urllib.parse.parse_qs(urllib.parse.urlparse(net9.urls[0]).query)
check("D9 q de 500 chars -> query_truncated True, len(query_sent) == 400 (WITT_WEB_MAX_QUERY_CHARS default, tope NUESTRO), "
      "el parámetro q de la URL ES query_sent; data declara max_query_chars 400 'default'",
      len(long_q) == 500 and out9["query_truncated"] is True and len(out9["query_sent"]) == 400
      and qs9["q"] == [out9["query_sent"]] and out9["data"]["max_query_chars"] == 400
      and out9["data"]["max_query_chars_source"] == "default")
os.environ["WITT_WEB_MAX_QUERY_CHARS"] = "100"
p_env = bws.prepare(long_q)
os.environ["WITT_WEB_MAX_QUERY_CHARS"] = "abc"
p_bad = bws.prepare(long_q)
os.environ.pop("WITT_WEB_MAX_QUERY_CHARS", None)
check("D9b WITT_WEB_MAX_QUERY_CHARS=100 -> 100 ('env:…'); basura 'abc' -> 400 con 'default-invalid-env:WITT_WEB_MAX_QUERY_CHARS' "
      "(ENV tolerante en la llamada, M.4)",
      len(p_env["query_sent"]) == 100 and p_env["max_query_chars_source"] == "env:WITT_WEB_MAX_QUERY_CHARS"
      and len(p_bad["query_sent"]) == 400 and p_bad["max_query_chars_source"] == "default-invalid-env:WITT_WEB_MAX_QUERY_CHARS")

qs1 = urllib.parse.parse_qs(urllib.parse.urlparse(out1["url_sent"]).query)
check("D12 url_sent = endpoint documentado + SÓLO {q, count, search_lang}; params_sent == esas; NINGUNO de result_filter/"
      "text_decorations/spellcheck/extra_snippets/offset/summary/ui_lang/safesearch; sin token",
      out1["url_sent"].startswith(bws.BASE + "?") and set(qs1) == {"q", "count", "search_lang"}
      and out1["params_sent"] == ["q", "count", "search_lang"] and set(out1["params_sent"]) <= set(bws.DOCUMENTED_PARAMS)
      and not (set(qs1) & set(bws.PARAMS_NEVER_SENT)) and FAKE not in out1["url_sent"] and qs1["count"] == ["10"],
      out1["url_sent"][:140])

net13 = FakeNet()
bws._get = net13
o50 = bws.locate(Q, count=50, cache_dir=_cache_dir("d13a"))
o0 = bws.locate(Q, count=0, cache_dir=_cache_dir("d13b"))
ozz = bws.locate(Q, freshness="zz", cache_dir=_cache_dir("d13c"))
opw = bws.locate(Q, freshness="pw", cache_dir=_cache_dir("d13d"))
orng = bws.locate(Q, freshness="2024-01-01to2024-12-31", cache_dir=_cache_dir("d13e"))
u50, u0, uzz, upw, urng = [urllib.parse.parse_qs(urllib.parse.urlparse(u).query) for u in net13.urls]
check("D13 count 50 -> 20 (tope DOCUMENTADO, clamp) y count 0 -> 1; count_source 'argument'",
      o50["data"]["count_sent"] == 20 and u50["count"] == ["20"] and o0["data"]["count_sent"] == 1 and u0["count"] == ["1"]
      and o50["data"]["count_source"] == "argument")
check("D13 freshness 'zz' -> NO enviado (sin `freshness` en la URL) + freshness_ignored 'zz' declarado; 'pw' y el rango "
      "YYYY-MM-DDtoYYYY-MM-DD SÍ se envían y entran a params_sent",
      ozz["data"]["freshness_sent"] is None and ozz["data"]["freshness_ignored"] == "zz" and "freshness" not in uzz
      and "freshness" not in ozz["params_sent"] and upw["freshness"] == ["pw"] and opw["data"]["freshness_sent"] == "pw"
      and urng["freshness"] == ["2024-01-01to2024-12-31"] and "freshness" in orng["params_sent"])
net13b = FakeNet()
bws._get = net13b
omx = bws.locate(Q, country="mx", cache_dir=_cache_dir("d13f"))
omex = bws.locate(Q, country="mex", cache_dir=_cache_dir("d13g"))
olang = bws.locate(Q, search_lang="english", cache_dir=_cache_dir("d13h"))
umx, umex, ulang = [urllib.parse.parse_qs(urllib.parse.urlparse(u).query) for u in net13b.urls]
check("D13 country 'mx' -> 'MX' enviado; 'mex' -> ignorado + country_ignored; search_lang 'english' (no ISO 639-1) -> "
      "ignorado + search_lang_ignored y sin `search_lang` en la URL",
      umx["country"] == ["MX"] and omx["data"]["country_sent"] == "MX" and "country" not in umex
      and omex["data"]["country_ignored"] == "mex" and "search_lang" not in ulang and olang["data"]["search_lang_ignored"] == "english")
os.environ["WITT_WEB_LANG"] = ""
os.environ["WITT_WEB_MAX_RESULTS"] = "5"
os.environ["WITT_WEB_COUNTRY"] = "us"
os.environ["WITT_WEB_FRESHNESS"] = "py"
net13c = FakeNet()
bws._get = net13c
oenv = bws.locate(Q, cache_dir=_cache_dir("d13i"))
uenv = urllib.parse.parse_qs(urllib.parse.urlparse(net13c.urls[0]).query)
os.environ["WITT_WEB_MAX_RESULTS"] = "abc"
oenv_bad = bws.prepare(Q)
for _k in ("WITT_WEB_LANG", "WITT_WEB_MAX_RESULTS", "WITT_WEB_COUNTRY", "WITT_WEB_FRESHNESS"):
    os.environ.pop(_k, None)
check("D13 env: WITT_WEB_LANG='' -> search_lang NO se envía (params_sent sin él); WITT_WEB_MAX_RESULTS=5 -> count 5 "
      "('env:…'); WITT_WEB_COUNTRY=us -> US; WITT_WEB_FRESHNESS=py -> py; WITT_WEB_MAX_RESULTS basura -> 10 "
      "'default-invalid-env:WITT_WEB_MAX_RESULTS'",
      "search_lang" not in uenv and oenv["params_sent"] == ["q", "count", "country", "freshness"] and uenv["count"] == ["5"]
      and oenv["data"]["count_source"] == "env:WITT_WEB_MAX_RESULTS" and uenv["country"] == ["US"] and uenv["freshness"] == ["py"]
      and oenv_bad["count_sent"] == 10 and oenv_bad["count_source"] == "default-invalid-env:WITT_WEB_MAX_RESULTS",
      json.dumps(oenv["params_sent"]))

# ======================================================================================================
print("\n# D14/D15 — deriva de API medida")
_body422 = json.dumps({"type": "ErrorResponse", "error": {"status": 422, "code": "VALIDATION",
                                                          "detail": "Unable to validate request parameter(s)",
                                                          "meta": {"errors": [{"loc": ["query", "freshness"], "msg": "invalid", "input": "zz"}]}}}).encode()
bws._get = FakeNet(plan=[_http_error(422, reason="Unprocessable Entity", body=_body422)])
out422 = bws.locate(Q, cache_dir=_cache_dir("d14"))
bws._get = FakeNet(plan=[_http_error(422, reason="Unprocessable Entity", body=b"")])
out422b = bws.locate(Q, cache_dir=_cache_dir("d14b"))
check("D14 422 con cuerpo que nombra `freshness` -> 'HTTP 422 unprocessable — freshness' (primer parámetro nombrado), "
      "error_kind 'unprocessable', unprocessable_param 'freshness'; cuerpo vacío -> '… body-not-parsed'; el cuerpo NO se copia",
      out422["status"] == "error" and out422["error"] == "HTTP 422 unprocessable — freshness" and out422["http_status"] == 422
      and out422["error_kind"] == "unprocessable" and out422["unprocessable_param"] == "freshness"
      and out422b["error"] == "HTTP 422 unprocessable — body-not-parsed" and out422b["unprocessable_param"] is None
      and "ErrorResponse" not in json.dumps(out422), out422.get("error"))
_alt = json.loads(json.dumps(FX_JS))
_alt["query"]["altered"] = Q + "s"
bws._get = FakeNet(plan=[_alt])
out15 = bws.locate(Q, cache_dir=_cache_dir("d15"))
check("D15 query.altered ≠ original -> query_altered_by_provider True y query_altered con el valor del proveedor "
      "(la búsqueda que Brave hizo, no la que pedimos — declarado, no fundido)",
      out15["data"]["query_altered_by_provider"] is True and out15["data"]["query_altered"] == Q + "s"
      and out15["data"]["query_original"] == Q)

# ======================================================================================================
print("\n# forma inesperada / red / vacía")
bws._get = FakeNet(plan=[dict(FX_JS, web={"type": "search", "results": {"a": 1}})])
out_sm = bws.locate(Q, cache_dir=_cache_dir("sm1"))
bws._get = FakeNet(plan=[["not", "a", "dict"]])
out_sm2 = bws.locate(Q, cache_dir=_cache_dir("sm2"))
check("shape-mismatch: web.results dict -> 'error' 'shape-mismatch (web.results is dict)', error_kind 'shape-mismatch', NO "
      "cacheado; cuerpo lista -> 'shape-mismatch (body is list)' (patrón shape-mismatch ADR-0080: jamás un no-match fabricado)",
      out_sm["status"] == "error" and out_sm["error"] == "shape-mismatch (web.results is dict)"
      and out_sm["error_kind"] == "shape-mismatch" and not list(_cache_dir("sm1").glob("*.json"))
      and out_sm2["error"] == "shape-mismatch (body is list)", out_sm.get("error"))
bws._get = FakeNet(plan=[urllib.error.URLError("timed out")])
out_u = bws.locate(Q, cache_dir=_cache_dir("net"))
netq = FakeNet()
bws._get = netq
out_q = bws.locate("   ", cache_dir=_cache_dir("q"))
check("URLError -> 'error' error_kind 'network' (la ronda sigue, §6 no-hang); query vacía -> 'error' 'empty query' "
      "error_kind 'empty-query' con cero llamadas",
      out_u["status"] == "error" and out_u["error_kind"] == "network" and out_u["error"].startswith("URLError")
      and out_q["status"] == "error" and out_q["error"] == "empty query" and out_q["error_kind"] == "empty-query" and netq.calls == [])
_skip = json.loads(json.dumps(FX_JS))
_skip["web"]["results"] = [{"title": "no url"}, "not-a-dict", {"url": "ftp://x/y", "title": "ftp"}] + _skip["web"]["results"][:2]
bws._get = FakeNet(plan=[_skip])
out_sk = bws.locate(Q, cache_dir=_cache_dir("skip"))
check("resultados sin URL http(s) o que no son dict se SALTAN y se CUENTAN (n_results_skipped_no_url 3), los válidos siguen",
      out_sk["status"] == "success" and out_sk["data"]["n_results"] == 2 and out_sk["data"]["n_results_skipped_no_url"] == 3)

# ======================================================================================================
print("\n# D10 — identidad: la llave jamás sale")
_all_out = json.dumps([out0, out1, out8, out_e, out_401, out_r, out_rr, out_h, out9, o50, out422, out15, out_sm], ensure_ascii=False)
check("D10 la llave fake JAMÁS aparece en ninguna salida, en el sobre de caché, en el fixture ni en url_sent; sólo su "
      "PRESENCIA (api_key_present) viaja",
      FAKE not in _all_out and FAKE not in cf1.read_text(encoding="utf-8") and FAKE not in FX_TEXT
      and FAKE not in out1["url_sent"] and out1["api_key_present"] is True and "X-Subscription-Token" not in _all_out)

# ======================================================================================================
print("\n# D11 — pacing propio con reloj falso")
_mono_real = net_throttle._monotonic
_clock = [5000.0]
net_throttle._monotonic = lambda: _clock[0]
net_throttle._sleep = lambda s: _clock.__setitem__(0, _clock[0] + s)
net_throttle._REGISTRY.pop(bws.HOST, None)
os.environ.pop("WITT_WEB_MIN_INTERVAL_S", None)          # default 1.0
net11 = FakeNet()
bws._get = net11
out11a = bws.locate(Q, cache_dir=_cache_dir("d11a"))
out11b = bws.locate(Q + " second", cache_dir=_cache_dir("d11b"))
os.environ["WITT_WEB_MIN_INTERVAL_S"] = "1.0"
out11c = bws.locate(Q + " third", cache_dir=_cache_dir("d11c"))
net_throttle._monotonic, net_throttle._sleep = _mono_real, _real_sleep
net_throttle._REGISTRY.pop(bws.HOST, None)
os.environ["WITT_WEB_MIN_INTERVAL_S"] = "0"
check("D11 WITT_WEB_MIN_INTERVAL_S ausente -> 1.0 ('default'); 1ª llamada waited 0, 2ª waited_s >= 0.999 (reloj falso), "
      "3ª con env '1.0' -> 'env:WITT_WEB_MIN_INTERVAL_S'; host api.search.brave.com; MISMO objeto del registro de proceso",
      out11a["throttle"]["min_interval_s"] == 1.0 and out11a["throttle"]["min_interval_source"] == "default"
      and out11a["throttle"]["waited_s"] == 0.0 and out11b["throttle"]["waited_s"] >= 0.999
      and out11c["throttle"]["waited_s"] >= 0.999 and out11c["throttle"]["min_interval_source"] == "env:WITT_WEB_MIN_INTERVAL_S"
      and out11b["throttle"]["host"] == bws.HOST and len(net11.calls) == 3,
      f"waited={[o['throttle']['waited_s'] for o in (out11a, out11b, out11c)]}")

# ======================================================================================================
print("\n# A.7 — CLI y grabador de fixture, offline")
_saved_key = os.environ.pop("BRAVE_API_KEY", None)
_stdout_real = sys.stdout
sys.stdout = io.StringIO()
try:
    _rc_nokey = bws._cli(["wt1a", "review"])
    _cli_txt = sys.stdout.getvalue()
finally:
    sys.stdout = _stdout_real
os.environ["BRAVE_API_KEY"] = _saved_key
check("A.7 CLI sin BRAVE_API_KEY -> imprime la fila 'tool-unavailable', dice que nada se envió y sale con 2; CERO red",
      _rc_nokey == 2 and '"tool-unavailable"' in _cli_txt and "nothing was sent" in _cli_txt and _NET_CALLS == [])
_fx_out = bws.record_fixture(out1["cache_path"], out1["query_sent"], out1["data"]["count_sent"], out_dir=_cache_dir("fx"))
_fx_env = json.loads(_fx_out.read_text(encoding="utf-8"))
check("A.7 record_fixture(): copia el sobre de caché a brave_web_search_<slug>_<YYYYMMDD>.json con _fixture {recorded_by "
      "'brave_web_search.py --record-fixture (ADR-0084 W1)', live True, synthetic False, query_sent, count_sent}; response "
      "íntegra; sin llave en el texto (el grabador ES la tool)",
      __import__("re").match(r"^brave_web_search_[a-z0-9-]{1,40}_\d{8}\.json$", _fx_out.name) is not None
      and _fx_env["_fixture"]["recorded_by"] == "brave_web_search.py --record-fixture (ADR-0084 W1)"
      and _fx_env["_fixture"]["live"] is True and _fx_env["_fixture"]["synthetic"] is False
      and _fx_env["_fixture"]["query_sent"] == Q and _fx_env["_fixture"]["count_sent"] == 10
      and _fx_env["response"] == FX_JS and FAKE not in _fx_out.read_text(encoding="utf-8"), _fx_out.name)

# ======================================================================================================
print("\n# transversal")
check("vocabulario: STATES del tool ⊆ search_harness.SOURCE_STATES (UNA verdad, ADR-0080) y los 5 estados medidos aquí "
      "son literales de esa tupla; ERROR_KINDS cerrado",
      set(bws.STATES) <= set(sh.SOURCE_STATES)
      and {out1["status"], out_nm["status"], out_e["status"], out_z["status"], out0["status"]} == set(bws.STATES)
      and all(o["error_kind"] in bws.ERROR_KINDS for o in (out_e, out_401, out_rr, out_h, out422, out_sm, out_u, out_q)))
check("la tool sigue stdlib-pura (requests/httpx/tooluniverse ausentes) y net_throttle importado por ruta (retry disponible)",
      not any(m in sys.modules for m in ("requests", "httpx", "tooluniverse")) and bws.net_throttle is net_throttle
      and bws._THROTTLE_IMPORT_ERROR is None)
check("raíz de caché declarada = <repo>/mcp_cache y NINGÚN raw_brave_* nuevo cayó ahí; con cache_dir=None honra "
      "WITT_MCP_CACHE_DIR (tempdir de la máscara), no la mcp_cache del repo",
      bws.CACHE_DIR == ROOT / "mcp_cache" and not list((ROOT / "mcp_cache").glob("raw_brave_*.json"))
      and bws.resolve_cache_dir() == ENV_CACHE
      and str(_cache_file(bws.locate(Q + " envdir"))).startswith(str(ENV_CACHE)),
      str(ENV_CACHE))
check("registro ToolUniverse presente (Brave_web_search_locate_workspace con name/description/input_schema/run) sin requerir "
      "el paquete; input_schema SÓLO con parámetros documentados + timeout; la firma de locate() es la del ADR (A)",
      all(hasattr(bws.Brave_web_search_locate_workspace, a) for a in ("name", "description", "input_schema", "run"))
      and set(bws.Brave_web_search_locate_workspace.input_schema["properties"]) == {"query", "count", "country", "search_lang", "freshness", "timeout"}
      and list(__import__("inspect").signature(bws.locate).parameters) == ["query", "count", "country", "search_lang", "freshness", "timeout", "cache_dir"])
check("constantes del contrato: TOOL_VERSION 'bws-1', DOCUMENTED_PARAMS == (q,count,country,search_lang,freshness), "
      "FIELDS_DROPPED == la lista del ADR (A.3), TITLE_CAP 120, COUNT_MAX 20, DEFAULT_MAX_QUERY_CHARS 400, DEFAULT_MIN_INTERVAL_S 1.0",
      bws.TOOL_VERSION == "bws-1" and bws.DOCUMENTED_PARAMS == ("q", "count", "country", "search_lang", "freshness")
      and bws.FIELDS_DROPPED == ("description", "extra_snippets", "language", "family_friendly", "thumbnail", "profile")
      and bws.TITLE_CAP == 120 and bws.COUNT_MAX == 20 and bws.DEFAULT_MAX_QUERY_CHARS == 400 and bws.DEFAULT_MIN_INTERVAL_S == 1.0)
check("el smoke corrió 100% OFFLINE — MEDIDO: urllib.request.urlopen bloqueado y contado == 0",
      _NET_CALLS == [], f"calls={_NET_CALLS[:5]}")

_urlreq.urlopen = _urlopen_real
os.environ.pop("BRAVE_API_KEY", None)
os.environ.pop("WITT_WEB_MIN_INTERVAL_S", None)
shutil.rmtree(TMP, ignore_errors=True)
n_pass = sum(CHECKS)
print(f"\n{n_pass}/{len(CHECKS)} PASS  (fixture provenance: {PROVENANCE})")
sys.exit(0 if n_pass == len(CHECKS) else 1)

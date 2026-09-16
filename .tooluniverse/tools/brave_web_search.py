"""
brave_web_search — tool Layer 0 del espacio de trabajo ToolUniverse (NUEVO 2026-09-16, ADR-0084 rebanada W1).

POR QUÉ EXISTE: el harness de búsqueda (ADR-0080) despacha una familia `web` cuyo valor NO es texto sino
LOCALIZACIÓN: la web devuelve URLs, un resolutor DETERMINISTA (analysis/scripts/lib/web_locator.py, ADR-0084 B)
extrae identificadores (DOI/PMID/PMCID/ZDB/ENSDARG/UniProt/GSE) y lo resuelto se MATERIALIZA por Europe PMC en
la misma ronda. Este módulo es el PRIMARIO de esa familia: Brave Search API REST, stdlib puro, SIN modelo.
Doctrina (CLAUDE.md §6 · ADR-0084): la web LOCALIZA, jamás es fuente — ningún `description`, `extra_snippets`
ni texto de la web sale de este tool hacia el bundle; la salida conserva SÓLO {url, title ≤ 120, host, age,
page_age} por resultado, y `title` existe únicamente para el ledger `unresolved[].title_web` del resolutor.

QUÉ HACE (ADR-0084 A.1): UNA GET a
  https://api.search.brave.com/res/v1/web/search?q=…&count=…[&country=…][&search_lang=…][&freshness=…]
con cabeceras `Accept: application/json` y `X-Subscription-Token: $BRAVE_API_KEY` (la llave viaja SÓLO en la
cabecera; `url_sent`, la caché y el fixture jamás la contienen — A.6). SÓLO parámetros DOCUMENTADOS por Brave
(verificados 2026-09-16 en api-dashboard.search.brave.com/app/documentation/web-search/query): NO se envían
`result_filter`, `text_decorations`, `spellcheck`, `extra_snippets`, `offset`, `summary`, `ui_lang` ni
`safesearch`. Sin `Accept-Encoding: gzip` (stdlib no descomprime — declarado). `count` clamp [1, 20] (tope
documentado); `q` recortado a WITT_WEB_MAX_QUERY_CHARS (400 — tope NUESTRO: Brave no documenta longitud) con
`query_truncated` declarado; `freshness` fuera de `pd|pw|pm|py|YYYY-MM-DDtoYYYY-MM-DD` → no se envía +
`freshness_ignored`; `country` que no sean 2 letras → no se envía + `country_ignored`; `search_lang` que no sea
ISO 639-1 (2 letras) → no se envía + `search_lang_ignored`.

ESTADOS (vocabulario cerrado de search_harness.SOURCE_STATES, ADR-0080; jamás fundidos — A.2):
  'success'          — web.results con ≥ 1 URL parseada
  'no-match'         — `web` ausente o `web.results` [] (buscó y no halló ≠ error)
  'error'            — HTTP ≠ 200 con `http_status` y `error_kind`:
                         401/403 → error 'auth (HTTP <code>)', error_kind 'auth', auth_failed True
                                   (CORTACIRCUITO: el harness marca las consultas restantes de la ronda
                                   'skipped-cap' con detail 'auth failed in this round (no retry)' — C.5)
                         429     → UN reintento con Retry-After (tope net_throttle.MAX_RETRY_AFTER_S = 60 s)
                                   vía net_throttle.retry_once_on_429; el segundo 429 → error_kind 'rate-limit'
                         422     → 'HTTP 422 unprocessable — <primer parámetro que el cuerpo nombre |
                                   body-not-parsed>' (MEDICIÓN de deriva de API; patrón shape-mismatch 0080)
                         otro    → 'HTTPError: <code> <reason>', error_kind 'http'
                       cuerpo no-JSON → 'NonJSONBody (content-type <ct>) — HTML/captcha declared'
                                   (error_kind 'non-json-body'; el cuerpo NO se copia a la salida)
                       forma inesperada → 'shape-mismatch (<detalle ≤ 120>)' (error_kind 'shape-mismatch')
                       red/socket → '<Tipo>: <msg>' (error_kind 'network')
  'skipped-budget'   — timeout ≤ 0 antes de la llamada (cero red)
  'tool-unavailable' — sin BRAVE_API_KEY: cero red, reason 'BRAVE_API_KEY unset (no request sent)'
                       (patrón unpaywall_crossref sin correo)

CORTE DEL TEXTO WEB — EN LA SALIDA (A.3): `data.results[]` conserva SÓLO {url, title (≤ TITLE_CAP=120), host
(meta_url.hostname o urlparse), age, page_age}. `description`, `extra_snippets` y todo lo demás se DESCARTAN
al parsear: `data.fields_dropped` es la POLÍTICA declarada (lista fija) y `data.fields_dropped_measured` lo
MEDIDO (llaves realmente vistas y descartadas en esta respuesta). El RAW ÍNTEGRO sí va al disco (§7.9: raw es
raw; `mcp_cache/` es caché gitignored y efímera en Dokploy; LG8 necesita `description`/`host` para medir tasas
por host) — el sobre de caché declara `cut {fields_dropped_from_output}` para no leerse como contrato de salida.

CACHÉ DE LECTURA POR DÍA (A.4): <cache_dir | WITT_MCP_CACHE_DIR | <repo>/mcp_cache>/raw_brave_<slug(q,40)>_
<sha8(q|count|country|lang|freshness)>_<YYYYMMDD>.json = {tool_version, fetched_at, url (sin token),
http_status, headers {X-RateLimit-*}, response (íntegra), cut}. Los ERRORES JAMÁS se cachean (un 'no-match'
sí: fue una respuesta 200 que midió). `cache_hit True` ⇒ `n_http_gets 0` (no consume cuota ni factura).
`cache_probe()` sondea sin red ni llave: web_locator.locate lo llama ANTES de reservar cuota (B.5).

PACING (A.5): net_throttle.get_throttle('api.search.brave.com', WITT_WEB_MIN_INTERVAL_S=1.0) — tope PROPIO
(Brave publica 50 qps) alrededor de la ÚNICA costura de red `_get(url, timeout, with_headers, api_key)`;
`throttle.waited_s` medido. `_urlopen` es la indirección interna de `_get` para que el smoke pruebe la
construcción de la petición sin red (patrón figures._urlopen); los smokes del harness parchean `_get`.

ENV (todas con default declarado; leídas EN LA LLAMADA — M.4; `<campo>_source` ∈ 'env:<VAR>' | 'default' |
'default-invalid-env:<VAR>'):
  BRAVE_API_KEY            default unset — sólo su PRESENCIA viaja (`api_key_present`); jamás git/vault/memoria
  WITT_WEB_MAX_RESULTS     default 10    — `count` (clamp 1..20)
  WITT_WEB_MAX_QUERY_CHARS default 400   — tope NUESTRO de `q`
  WITT_WEB_MIN_INTERVAL_S  default 1.0   — pacing propio por host
  WITT_WEB_COUNTRY         default unset — `country` (2 letras); vacío ⇒ ausente
  WITT_WEB_LANG            default 'en'  — `search_lang`; cadena vacía ⇒ NO se envía
  WITT_WEB_FRESHNESS       default unset — `freshness`; fuera de forma ⇒ no se envía + `freshness_ignored`
  WITT_MCP_CACHE_DIR       (pre-existente) raíz de la caché por día

CONTRATO DE SALIDA de locate() (ADR-0084 A):
  {status, query_sent, query_truncated, url_sent (SIN token), elapsed_s, n_http_gets, cache_hit, cache_path,
   cached_at, api_key_present, throttle {host, min_interval_s, min_interval_source, waited_s} | None,
   retries_429, retry_after_s, rate_limit_headers {limit, policy, remaining, reset} | None, http_status?,
   error?, error_kind?, auth_failed?, reason?, identifier_provenance 'brave-web-search', evidence_kind 'web',
   tool_version 'bws-1', params_sent [nombres], params_verified_as_of '2026-09-16',
   data {query_original, query_altered, query_altered_by_provider, more_results_available, count_sent,
         count_source, country_sent, search_lang_sent, freshness_sent, [country_ignored | search_lang_ignored |
         freshness_ignored], n_results, n_results_skipped_no_url, n_titles_truncated,
         results[] {url, title, host, age, page_age}, fields_kept, fields_consumed, fields_dropped,
         fields_dropped_measured}}
Las URLs devueltas son LOCALIZACIONES, no evidencia: el resolutor (web_locator) las convierte en identificadores
y Europe PMC confirma su existencia; nada de aquí entra al sintetizador, al panel ni a answer.gap_flags.

CLI (A.7): python .tooluniverse/tools/brave_web_search.py "<query>" [--count N] [--country XX] [--lang xx]
           [--freshness pw] [--record-fixture]   → UNA GET real (requiere BRAVE_API_KEY; sin ella imprime la fila
           tool-unavailable y sale con 2). `--record-fixture` copia el sobre de caché a
           rag_index/query_service/fixtures/brave_web_search_<slug>_<YYYYMMDD>.json con `_fixture {recorded_by
           'brave_web_search.py --record-fixture (ADR-0084 W1)', live true}` — el grabador ES la tool.
Fixture SINTÉTICO (sin llave el 2026-09-16): rag_index/query_service/fixtures/brave_web_search_SYNTHETIC_wt1a_20260916.json
Gate offline: rag_index/query_service/smoke_tools_d.py
"""
import datetime
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = _ROOT / "mcp_cache"                        # ADR-0080: raíz de caché declarada (gitignored)
FIXTURES_DIR = _ROOT / "rag_index" / "query_service" / "fixtures"
_LIB_PARENT = str(_ROOT / "analysis" / "scripts")
if _LIB_PARENT not in sys.path:
    sys.path.insert(0, _LIB_PARENT)
try:
    from lib import net_throttle  # noqa: E402
    _THROTTLE_IMPORT_ERROR = None
except Exception as _e:  # se declara en la salida (`throttle: None`), jamás se oculta
    net_throttle = None
    _THROTTLE_IMPORT_ERROR = f"{type(_e).__name__}: {_e}"

TOOL_VERSION = "bws-1"                                 # ADR-0084 (A): viaja en frozen.web_locator.tool_version
BASE = "https://api.search.brave.com/res/v1/web/search"
HOST = "api.search.brave.com"
_UA = "witt-organo/1.0 (brave-web-search-tool; ADR-0084)"
KEY_ENV = "BRAVE_API_KEY"

DEFAULT_TIMEOUT_S = 20            # timeout de socket por GET cuando el llamador no pasa ninguno
DEFAULT_COUNT = 10                # WITT_WEB_MAX_RESULTS
COUNT_MIN, COUNT_MAX = 1, 20      # tope DOCUMENTADO por Brave («max 20»)
DEFAULT_MAX_QUERY_CHARS = 400     # WITT_WEB_MAX_QUERY_CHARS — tope NUESTRO (la directiva ya viene ≤ 200)
DEFAULT_MIN_INTERVAL_S = 1.0      # WITT_WEB_MIN_INTERVAL_S — pacing PROPIO (Brave publica 50 qps)
DEFAULT_SEARCH_LANG = "en"        # WITT_WEB_LANG (las query_en del consejo son inglés)
TITLE_CAP = 120                   # A.3: `title` ≤ 120 — sólo para unresolved[].title_web del resolutor
ERROR_BODY_MAX_BYTES = 65536      # cuánto cuerpo de error se LEE para nombrar el parámetro (jamás se copia)

IDENTIFIER_PROVENANCE = "brave-web-search"
EVIDENCE_KIND = "web"
PARAMS_VERIFIED_AS_OF = "2026-09-16"
PARAMS_DOC_URL = "https://api-dashboard.search.brave.com/app/documentation/web-search/query"
RESPONSES_DOC_URL = "https://api-dashboard.search.brave.com/app/documentation/web-search/responses"
# Parámetros DOCUMENTADOS que este tool puede enviar (en este orden dentro de la URL):
DOCUMENTED_PARAMS = ("q", "count", "country", "search_lang", "freshness")
# NO documentados hoy en la página de query o descartados por doctrina: JAMÁS en la URL (smoke D12).
PARAMS_NEVER_SENT = ("result_filter", "text_decorations", "spellcheck", "extra_snippets", "offset",
                     "summary", "ui_lang", "safesearch", "units", "goggles", "goggles_id")
# Corte en la SALIDA (A.3): lo que se conserva, lo que se consume para derivar `host`, y la POLÍTICA de descarte.
RESULT_KEYS_KEPT = ("url", "title", "host", "age", "page_age")
FIELDS_CONSUMED = ("meta_url.hostname",)
FIELDS_DROPPED = ("description", "extra_snippets", "language", "family_friendly", "thumbnail", "profile")
_RESULT_KEYS_NOT_DROPPED = {"url", "title", "age", "page_age", "meta_url"}

STATES = ("success", "no-match", "error", "skipped-budget", "tool-unavailable")   # ⊆ SOURCE_STATES (0080)
ERROR_KINDS = ("auth", "rate-limit", "unprocessable", "non-json-body", "shape-mismatch", "http", "network",
               "empty-query")
AUTH_ERROR_KIND = "auth"
UNAVAILABLE_REASON = "BRAVE_API_KEY unset (no request sent)"

FRESHNESS_RE = re.compile(r"^(pd|pw|pm|py|\d{4}-\d{2}-\d{2}to\d{4}-\d{2}-\d{2})$")
COUNTRY_RE = re.compile(r"^[A-Za-z]{2}$")
LANG_RE = re.compile(r"^[A-Za-z]{2}$")                 # ISO 639-1
_RATE_HEADER_HINTS = ("x-ratelimit", "retry-after")
_RATE_LIMIT_MAP = (("limit", "x-ratelimit-limit"), ("policy", "x-ratelimit-policy"),
                   ("remaining", "x-ratelimit-remaining"), ("reset", "x-ratelimit-reset"))
_PARAM_NAME_RE = re.compile(r"\b(q|count|offset|country|search_lang|ui_lang|safesearch|freshness|extra_snippets|"
                            r"result_filter|text_decorations|spellcheck|summary|units|goggles_id|goggles)\b")

# Indirección interna de la costura `_get` (patrón figures._urlopen): el smoke la sustituye por una respuesta
# falsa para probar cabeceras/JSON/no-JSON sin red; el bloqueador de urlopen del smoke sigue contando la real.
_urlopen = urllib.request.urlopen


class NonJSONBody(Exception):
    """HTTP 200 cuyo cuerpo no es JSON (HTML de captcha, proxy…). Lleva content-type y tamaño; NUNCA el texto."""

    def __init__(self, content_type, n_bytes):
        super().__init__(f"NonJSONBody (content-type {content_type or 'unknown'})")
        self.content_type = content_type
        self.n_bytes = n_bytes


class ShapeMismatch(Exception):
    """La respuesta parseó como JSON pero no tiene la forma documentada (web.results lista, query dict)."""


# --- env tolerante (ADR-0084 B.4 / figures.ENV_SPECS): valor + fuente declarada, leídos EN LA LLAMADA ------
def _env_int(name, default, lo, hi, env=None):
    env = os.environ if env is None else env
    raw = (env.get(name) or "").strip()
    if not raw:
        return default, "default"
    try:
        v = int(raw)
    except ValueError:
        return default, f"default-invalid-env:{name}"
    return max(lo, min(v, hi)), f"env:{name}"


def _env_float(name, default, lo, hi, env=None):
    env = os.environ if env is None else env
    raw = (env.get(name) or "").strip()
    if not raw:
        return default, "default"
    try:
        v = float(raw)
    except ValueError:
        return default, f"default-invalid-env:{name}"
    if v != v:  # NaN
        return default, f"default-invalid-env:{name}"
    return max(lo, min(v, hi)), f"env:{name}"


def _api_key(env=None):
    env = os.environ if env is None else env
    return (env.get(KEY_ENV) or "").strip() or None


def resolve_cache_dir(cache_dir=None, env=None):
    """ADR-0080: `cache_dir` explícito (tests) > WITT_MCP_CACHE_DIR > <repo>/mcp_cache."""
    if cache_dir is not None:
        return Path(cache_dir)
    env = os.environ if env is None else env
    raw = (env.get("WITT_MCP_CACHE_DIR") or "").strip()
    return Path(raw) if raw else CACHE_DIR


def _slug(text, n=40):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:n].strip("-") or "query"


def _rel(path):
    try:
        return str(Path(path).resolve().relative_to(_ROOT)).replace("\\", "/")
    except Exception:
        return str(path)


def _now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


# --- preparación PURA de la petición (sin red, sin llave): la usa locate() y el --dry-run de smoke_live_web ---
def prepare(query, count=None, country=None, search_lang=None, freshness=None, env=None):
    """Recorta `q`, resuelve count/country/search_lang/freshness (arg explícito > env > default), valida contra
    las formas documentadas y construye la URL PÚBLICA (sin token). Determinista; jamás toca la red."""
    env = os.environ if env is None else env
    original = (query or "").strip()
    max_chars, max_chars_src = _env_int("WITT_WEB_MAX_QUERY_CHARS", DEFAULT_MAX_QUERY_CHARS, 1, 10000, env)
    sent = original[:max_chars]
    truncated = len(original) > max_chars

    if count is None:
        n, count_src = _env_int("WITT_WEB_MAX_RESULTS", DEFAULT_COUNT, COUNT_MIN, COUNT_MAX, env)
    else:
        try:
            n, count_src = max(COUNT_MIN, min(int(count), COUNT_MAX)), "argument"
        except (TypeError, ValueError):
            n, count_src = DEFAULT_COUNT, "default-invalid-argument"

    out = {"query_original": original, "query_sent": sent, "query_truncated": truncated,
           "max_query_chars": max_chars, "max_query_chars_source": max_chars_src,
           "count_sent": n, "count_source": count_src,
           "country_sent": None, "search_lang_sent": None, "freshness_sent": None}

    c_raw = country if country is not None else (env.get("WITT_WEB_COUNTRY") or "")
    c_raw = (c_raw or "").strip()
    if c_raw:
        if COUNTRY_RE.match(c_raw):
            out["country_sent"] = c_raw.upper()
        else:
            out["country_ignored"] = c_raw[:20]

    if search_lang is not None:
        l_raw = search_lang
    else:
        l_env = env.get("WITT_WEB_LANG")
        l_raw = DEFAULT_SEARCH_LANG if l_env is None else l_env   # env presente y vacía ⇒ NO se envía
    l_raw = (l_raw or "").strip()
    if l_raw:
        if LANG_RE.match(l_raw):
            out["search_lang_sent"] = l_raw.lower()
        else:
            out["search_lang_ignored"] = l_raw[:20]

    f_raw = freshness if freshness is not None else (env.get("WITT_WEB_FRESHNESS") or "")
    f_raw = (f_raw or "").strip()
    if f_raw:
        if FRESHNESS_RE.match(f_raw):
            out["freshness_sent"] = f_raw
        else:
            out["freshness_ignored"] = f_raw[:40]

    url, params = build_url(sent, n, out["country_sent"], out["search_lang_sent"], out["freshness_sent"])
    out["url_sent"], out["params_sent"] = url, params
    key_src = "|".join([sent, str(n), out["country_sent"] or "", out["search_lang_sent"] or "", out["freshness_sent"] or ""])
    out["cache_sha8"] = hashlib.sha256(key_src.encode("utf-8")).hexdigest()[:8]
    out["cache_slug"] = _slug(sent)
    return out


def build_url(query_sent, count, country=None, search_lang=None, freshness=None):
    """(url pública, [nombres de parámetros enviados]) — SÓLO DOCUMENTED_PARAMS, en ese orden. Sin token."""
    pairs = [("q", query_sent), ("count", str(int(count)))]
    if country:
        pairs.append(("country", country))
    if search_lang:
        pairs.append(("search_lang", search_lang))
    if freshness:
        pairs.append(("freshness", freshness))
    return BASE + "?" + urllib.parse.urlencode(pairs), [k for k, _ in pairs]


def cache_path_for(prep, cache_dir=None, day=None, env=None):
    day = day or _now_utc().strftime("%Y%m%d")
    return resolve_cache_dir(cache_dir, env) / f"raw_brave_{prep['cache_slug']}_{prep['cache_sha8']}_{day}.json"


def _read_cache(path):
    try:
        if not Path(path).exists():
            return None
        js = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(js, dict) and "fetched_at" in js and "response" in js:
            return js
    except Exception:
        pass
    return None


def cache_probe(query, count=None, country=None, search_lang=None, freshness=None, cache_dir=None, env=None):
    """Sonda de la caché por día SIN red y SIN llave (ADR-0084 B.5 paso 1: web_locator no reserva cuota si hay
    cache_hit). {cache_hit, cache_path, cached_at, url_sent}."""
    prep = prepare(query, count=count, country=country, search_lang=search_lang, freshness=freshness, env=env)
    cpath = cache_path_for(prep, cache_dir, env=env)
    cached = _read_cache(cpath)
    return {"cache_hit": cached is not None, "cache_path": _rel(cpath),
            "cached_at": cached.get("fetched_at") if cached else None, "url_sent": prep["url_sent"]}


# --- red: la ÚNICA costura --------------------------------------------------------------------------------
def _get(url, timeout=DEFAULT_TIMEOUT_S, with_headers=True, api_key=None):
    """ÚNICA costura de red (los smokes del harness la parchean para servir fixtures). La llave viaja SÓLO en
    la cabecera X-Subscription-Token. Devuelve (json, cabeceras X-RateLimit-* medidas | None); con
    `with_headers=False` sólo el json. Cuerpo no-JSON → NonJSONBody (content-type y tamaño, jamás el texto)."""
    hdrs = {"User-Agent": _UA, "Accept": "application/json"}
    if api_key:
        hdrs["X-Subscription-Token"] = api_key
    req = urllib.request.Request(url, headers=hdrs)
    with _urlopen(req, timeout=timeout) as r:
        raw = r.read()
        rh = getattr(r, "headers", None)
        ct = None
        try:
            ct = rh.get("Content-Type") if rh is not None else None
        except Exception:
            ct = None
        try:
            js = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            raise NonJSONBody(ct, len(raw))
        return (js, _rate_headers_raw(rh)) if with_headers else js


def _rate_headers_raw(hdrs):
    """Cabeceras X-RateLimit-* / Retry-After tal como vinieron (MEDICIÓN); None cuando no hubo ninguna."""
    if hdrs is None:
        return None
    try:
        items = hdrs.items()
    except Exception:
        return None
    found = {}
    for k, v in items:
        if any(h in str(k).lower() for h in _RATE_HEADER_HINTS):
            found[str(k)] = str(v)
    return found or None


def normalize_rate_limit_headers(raw):
    """{limit, policy, remaining, reset} desde las cabeceras crudas (case-insensitive); None si no hay ninguna."""
    if not isinstance(raw, dict) or not raw:
        return None
    low = {str(k).lower(): v for k, v in raw.items()}
    out = {name: low.get(hdr) for name, hdr in _RATE_LIMIT_MAP}
    return out if any(v is not None for v in out.values()) else None


def _error_body_param(err):
    """Para un 422: el PRIMER nombre de parámetro que el cuerpo del error mencione (medición de deriva de API).
    None cuando no hay cuerpo legible o ningún nombre aparece. El cuerpo jamás se copia a la salida."""
    try:
        body = err.read(ERROR_BODY_MAX_BYTES)
    except Exception:
        return None
    if not body:
        return None
    try:
        text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    except Exception:
        return None
    m = _PARAM_NAME_RE.search(text)
    return m.group(1) if m else None


# --- parseo: el corte del texto web ocurre AQUÍ (A.3) -------------------------------------------------------
def _host_of(url, meta_url):
    h = None
    if isinstance(meta_url, dict):
        h = meta_url.get("hostname")
    if not h:
        try:
            h = urllib.parse.urlparse(url).hostname
        except Exception:
            h = None
    return h.lower().rstrip(".") if isinstance(h, str) and h else None


def parse_response(js):
    """(status, data_tail). Aplica el corte: por resultado SÓLO {url, title ≤ 120, host, age, page_age}.
    Lanza ShapeMismatch cuando la forma no es la documentada."""
    if not isinstance(js, dict):
        raise ShapeMismatch(f"body is {type(js).__name__}")
    q = js.get("query")
    if q is None:
        q = {}
    if not isinstance(q, dict):
        raise ShapeMismatch(f"query is {type(q).__name__}")
    web = js.get("web")
    if web is None:
        raw_results = []
    elif not isinstance(web, dict):
        raise ShapeMismatch(f"web is {type(web).__name__}")
    else:
        raw_results = web.get("results")
        if raw_results is None:
            raw_results = []
        elif not isinstance(raw_results, list):
            raise ShapeMismatch(f"web.results is {type(raw_results).__name__}")

    results, seen_keys, n_skipped, n_title_cut = [], set(), 0, 0
    for r in raw_results:
        if not isinstance(r, dict):
            n_skipped += 1
            continue
        seen_keys.update(r.keys())
        url = r.get("url")
        if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
            n_skipped += 1
            continue
        title = r.get("title")
        title = str(title) if title is not None else None
        if title is not None and len(title) > TITLE_CAP:
            title, n_title_cut = title[:TITLE_CAP], n_title_cut + 1
        age, page_age = r.get("age"), r.get("page_age")
        results.append({"url": url, "title": title, "host": _host_of(url, r.get("meta_url")),
                        "age": age if isinstance(age, str) else None,
                        "page_age": page_age if isinstance(page_age, str) else None})

    original = q.get("original") if isinstance(q.get("original"), str) else None
    altered = q.get("altered") if isinstance(q.get("altered"), str) and q.get("altered") else None
    more = q.get("more_results_available") if isinstance(q.get("more_results_available"), bool) else None
    tail = {"query_original_provider": original, "query_altered": altered,
            "query_altered_by_provider": bool(altered) and altered != original,
            "more_results_available": more,
            "n_results": len(results), "n_results_skipped_no_url": n_skipped, "n_titles_truncated": n_title_cut,
            "title_cap": TITLE_CAP, "results": results,
            "fields_kept": list(RESULT_KEYS_KEPT), "fields_consumed": list(FIELDS_CONSUMED),
            "fields_dropped": list(FIELDS_DROPPED),
            "fields_dropped_measured": sorted(k for k in seen_keys if k not in _RESULT_KEYS_NOT_DROPPED)}
    return ("success" if results else "no-match"), tail


def is_auth_error(row):
    """True cuando la fila es un error de autenticación (401/403): el harness corta el circuito de la ronda."""
    return isinstance(row, dict) and row.get("status") == "error" and row.get("error_kind") == AUTH_ERROR_KIND


# --- el tool -------------------------------------------------------------------------------------------------
def locate(query, count=None, country=None, search_lang=None, freshness=None, timeout=DEFAULT_TIMEOUT_S,
           cache_dir=None):
    """Localiza URLs para `query` con UNA GET a Brave (ver docstring del módulo). Nunca lanza.
    Secuencia: query vacía → error · sin llave → tool-unavailable (cero red) · timeout ≤ 0 → skipped-budget ·
    caché del día → cache_hit (cero red) · throttle → GET (1 reintento en 429) · parseo con corte · caché."""
    t0 = time.monotonic()
    term = (query or "").strip()
    key = _api_key()
    base = {"query_sent": term or None, "query_truncated": False, "url_sent": None, "elapsed_s": 0.0,
            "n_http_gets": 0, "cache_hit": False, "cache_path": None, "cached_at": None,
            "api_key_present": key is not None, "throttle": None, "retries_429": 0, "retry_after_s": None,
            "rate_limit_headers": None, "identifier_provenance": IDENTIFIER_PROVENANCE,
            "evidence_kind": EVIDENCE_KIND, "tool_version": TOOL_VERSION, "params_sent": [],
            "params_verified_as_of": PARAMS_VERIFIED_AS_OF}

    def _done(status, **kw):
        base["elapsed_s"] = round(time.monotonic() - t0, 4)
        return dict(base, status=status, **kw)

    if not term:
        return _done("error", error="empty query", error_kind="empty-query")
    if key is None:
        # A.2 / unpaywall_crossref:277-279 — sin llave NADA se envía; la causa viaja en `reason`.
        return _done("tool-unavailable", reason=UNAVAILABLE_REASON)
    if timeout is not None and timeout <= 0:
        return _done("skipped-budget",
                     error=f"BudgetExhausted: timeout={timeout!r} <= 0 before the call (no request sent)")

    prep = prepare(term, count=count, country=country, search_lang=search_lang, freshness=freshness)
    base["query_sent"], base["query_truncated"] = prep["query_sent"], prep["query_truncated"]
    base["url_sent"], base["params_sent"] = prep["url_sent"], prep["params_sent"]
    data_head = {k: prep[k] for k in ("query_original", "count_sent", "count_source", "country_sent",
                                       "search_lang_sent", "freshness_sent")}
    for k in ("country_ignored", "search_lang_ignored", "freshness_ignored"):
        if k in prep:
            data_head[k] = prep[k]
    if prep["query_truncated"]:
        data_head["max_query_chars"], data_head["max_query_chars_source"] = prep["max_query_chars"], prep["max_query_chars_source"]

    cpath = cache_path_for(prep, cache_dir)
    base["cache_path"] = _rel(cpath)
    cached = _read_cache(cpath)
    raw_headers = None
    if cached is not None:
        base["cache_hit"], base["cached_at"] = True, cached.get("fetched_at")
        raw_headers = cached.get("headers")
        base["rate_limit_headers"] = normalize_rate_limit_headers(raw_headers)
        js = cached["response"]
    else:
        min_interval, min_src = _env_float("WITT_WEB_MIN_INTERVAL_S", DEFAULT_MIN_INTERVAL_S, 0.0, 60.0)
        thr = net_throttle.get_throttle(HOST, min_interval) if net_throttle is not None else None
        if thr is not None:
            base["throttle"] = {"host": HOST, "min_interval_s": min_interval, "min_interval_source": min_src,
                                "waited_s": 0.0}
        stats = {}
        holder = {"headers": None}

        def _once():
            if thr is not None:
                base["throttle"]["waited_s"] = round(base["throttle"]["waited_s"] + thr.wait(), 4)
            base["n_http_gets"] += 1
            try:
                js_, hd = _get(prep["url_sent"], timeout=timeout, with_headers=True, api_key=key)
            except urllib.error.HTTPError as e:
                hd = _rate_headers_raw(getattr(e, "headers", None))
                if hd:
                    holder["headers"] = hd
                raise
            if hd:
                holder["headers"] = hd
            return js_

        try:
            try:
                js = net_throttle.retry_once_on_429(_once, stats) if net_throttle is not None else _once()
            finally:
                base["retries_429"] += int(stats.get("retries_429") or 0)
                base["retry_after_s"] = stats.get("retry_after_s")
                raw_headers = holder["headers"]
                base["rate_limit_headers"] = normalize_rate_limit_headers(raw_headers)
        except urllib.error.HTTPError as e:
            code = getattr(e, "code", None)
            reason = str(getattr(e, "reason", "") or "").strip()
            if code in (401, 403):
                # cortacircuito por ronda (C.5): el harness lee auth_failed / error_kind, no el texto
                return _done("error", http_status=code, error=f"auth (HTTP {code})", error_kind=AUTH_ERROR_KIND,
                             auth_failed=True, data=data_head)
            if code == 429:
                return _done("error", http_status=429, error_kind="rate-limit",
                             error=f"HTTP 429 rate-limited after one retry (Retry-After {stats.get('retry_after_s')}s, "
                                   f"{stats.get('retry_after_src')})", data=data_head)
            if code == 422:
                pname = _error_body_param(e)
                return _done("error", http_status=422, error_kind="unprocessable", unprocessable_param=pname,
                             error=f"HTTP 422 unprocessable — {pname or 'body-not-parsed'}", data=data_head)
            return _done("error", http_status=code, error_kind="http",
                         error=f"HTTPError: {code or '?'} {reason}".strip(), data=data_head)
        except NonJSONBody as e:
            return _done("error", error_kind="non-json-body", http_status=200, body_bytes=e.n_bytes,
                         error=f"NonJSONBody (content-type {e.content_type or 'unknown'}) — HTML/captcha declared",
                         data=data_head)
        except Exception as e:
            return _done("error", error_kind="network", error=f"{type(e).__name__}: {str(e)[:200]}", data=data_head)

    try:
        status, tail = parse_response(js)
    except ShapeMismatch as e:
        return _done("error", error_kind="shape-mismatch", error=f"shape-mismatch ({str(e)[:120]})", data=data_head)
    except Exception as e:  # cualquier otra sorpresa del parseo: error declarado, jamás un success vacío
        return _done("error", error_kind="shape-mismatch",
                     error=f"shape-mismatch ({type(e).__name__}: {str(e)[:100]})", data=data_head)
    if cached is None:
        _cache_write(cpath, prep["url_sent"], js, raw_headers)   # sólo respuestas 200 parseables (A.4)
    return _done(status, data=dict(data_head, **tail))


def _cache_write(path, url_public, response, headers, http_status=200):
    """Sobre de caché: RAW ÍNTEGRO (§7.9) + cabeceras medidas + URL pública (sin token) + `cut` declarado.
    Mejor esfuerzo: un disco que falla no tumba la ronda."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        env = {"tool_version": TOOL_VERSION, "fetched_at": _now_utc().isoformat(timespec="seconds"),
               "url": url_public, "http_status": http_status, "headers": headers, "response": response,
               "cut": {"fields_dropped_from_output": list(FIELDS_DROPPED),
                       "note": "the envelope keeps the RAW response (CLAUDE.md §7.9); the tool OUTPUT keeps "
                               "url/title(<=120)/host/age/page_age per result only — this file is NOT an output "
                               "contract and nothing in it reaches the bundle (ADR-0084 A.3)"}}
        path.write_text(json.dumps(env, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def record_fixture(cache_path, query_sent, count_sent, out_dir=None, day=None):
    """A.7: copia el sobre de caché a fixtures/brave_web_search_<slug>_<YYYYMMDD>.json con `_fixture` live.
    Se niega a escribir si el texto contuviera la llave (A.6). Devuelve la ruta escrita."""
    src = Path(cache_path)
    if not src.is_absolute():
        src = _ROOT / src
    env = json.loads(src.read_text(encoding="utf-8"))
    env["_fixture"] = {"recorded_by": "brave_web_search.py --record-fixture (ADR-0084 W1)", "live": True,
                       "synthetic": False, "recorded_at": _now_utc().isoformat(timespec="seconds"),
                       "query_sent": query_sent, "count_sent": count_sent, "tool_version": TOOL_VERSION,
                       "source_file": src.name,
                       "note": "LIVE Brave response recorded through the tool's own path (one GET). Contains "
                               "description/extra_snippets ON PURPOSE (raw is raw) so smoke_tools_d can measure "
                               "that the tool OUTPUT drops them. No token anywhere in this file."}
    text = json.dumps(env, ensure_ascii=False, indent=1)
    key = _api_key()
    if key and key in text:
        raise RuntimeError("refusing to write a fixture that contains the API key")
    day = day or _now_utc().strftime("%Y%m%d")
    dst = Path(out_dir) if out_dir else FIXTURES_DIR
    dst.mkdir(parents=True, exist_ok=True)
    path = dst / f"brave_web_search_{_slug(query_sent)}_{day}.json"
    path.write_text(text, encoding="utf-8")
    return path


# --- registro ToolUniverse (no-op si el paquete no importa: el archivo sigue siendo testeable) ----------------
try:
    from tooluniverse.tool_registry import register_tool
except Exception:  # pragma: no cover
    def register_tool(x):
        return x


@register_tool
class Brave_web_search_locate_workspace:
    name = "Brave_web_search_locate_workspace"
    description = (
        "Brave Search API (REST, no model) as a LOCATOR: returns URLs {url, title<=120, host, age, page_age} "
        "for an English query; description/extra_snippets are dropped at the tool output (raw kept on disk). "
        "Web text NEVER enters the evidence bundle: a deterministic resolver turns URLs into DOI/PMID/PMCID/"
        "ZDB/ENSDARG/UniProt/GSE and Europe PMC materializes them (ADR-0084). Requires BRAVE_API_KEY (header "
        "only; presence declared). Status 'no-match' = searched, nothing found; 'tool-unavailable' = no key, "
        "no request sent."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "English query (council directive query_en), <= 400 chars."},
            "count": {"type": ["integer", "null"], "description": "Results per query (default WITT_WEB_MAX_RESULTS=10, max 20)."},
            "country": {"type": ["string", "null"], "description": "2-letter country code (default WITT_WEB_COUNTRY, unset)."},
            "search_lang": {"type": ["string", "null"], "description": "ISO 639-1 language (default WITT_WEB_LANG='en')."},
            "freshness": {"type": ["string", "null"], "description": "pd|pw|pm|py|YYYY-MM-DDtoYYYY-MM-DD (default unset)."},
            "timeout": {"type": ["number", "null"], "description": "Socket timeout in seconds for the GET (default 20)."},
        },
        "required": ["query"],
    }

    def run(self, query, count=None, country=None, search_lang=None, freshness=None, timeout=DEFAULT_TIMEOUT_S):
        return locate(query, count=count, country=country, search_lang=search_lang, freshness=freshness,
                      timeout=DEFAULT_TIMEOUT_S if timeout is None else timeout)


def _cli(argv):
    """python brave_web_search.py "<query>" [--count N] [--country XX] [--lang xx] [--freshness pw] [--record-fixture]"""
    words, opts = [], {"count": None, "country": None, "lang": None, "freshness": None, "record": False}
    it = iter(argv)
    for a in it:
        if a == "--record-fixture":
            opts["record"] = True
        elif a in ("--count", "--country", "--lang", "--freshness"):
            opts[a[2:]] = next(it, None)
        else:
            words.append(a)
    query = " ".join(words).strip()
    if not query:
        print(__doc__.split("CLI (A.7):", 1)[-1].split("Fixture", 1)[0])
        return 2
    if _api_key() is None:
        print(json.dumps(locate(query), ensure_ascii=False, indent=2))
        print("\nBRAVE_API_KEY unset: nothing was sent (tool-unavailable). Set it in the environment, never in git.")
        return 2
    out = locate(query, count=int(opts["count"]) if opts["count"] else None, country=opts["country"],
                 search_lang=opts["lang"], freshness=opts["freshness"])
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if opts["record"]:
        if out.get("status") not in ("success", "no-match"):
            print(f"\n--record-fixture: not recording a {out.get('status')!r} row (only 200 responses are fixtures)")
            return 1
        path = record_fixture(out["cache_path"], out["query_sent"], (out.get("data") or {}).get("count_sent"))
        print(f"\nfixture written: {_rel(path)} (live true; check X-RateLimit-* in headers and count effective)")
    return 0 if out.get("status") in ("success", "no-match") else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(_cli(sys.argv[1:]))

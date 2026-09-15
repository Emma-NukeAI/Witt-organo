"""smoke_pubmed_tool.py — gate determinista de la workspace tool pubmed_literature + net_throttle (ADR-0078).

Cubre la higiene de la Ruta B hacia NCBI E-utilities que el audit del 2026-09-13 encontró ausente:
identidad (tool=witt-organogenesis SIEMPRE; email=$WITT_NCBI_EMAIL SOLO si la env existe — si falta se
DECLARA ncbi_identity:'missing', jamás se inventa), throttle a nivel PROCESO por host (intervalo 0.34 s sin
NCBI_API_KEY / 0.10 s con llave / WITT_NCBI_MIN_INTERVAL_S sobreescribe; medido con monotonic entre
llamadas simuladas), UN reintento ante HTTP 429 (Retry-After o 1 s) y el segundo 429 -> status 'error'
declarado (nunca loop, §6 no-hang), retmax parametrizable (WITT_PATH_B_RETMAX default 20; viaja en la URL),
mediciones de salida (query_sent literal, rate_limit_headers con X-RateLimit-* o None declarado), y que el
contrato viejo (status/data/query/n_found_total/records) se CONSERVA — solo se agregan campos.

100% offline: urllib.request.urlopen monkeypatcheado, net_throttle._sleep stub SOLO para las esperas del
reintento 429 (el throttle duerme de verdad, es lo medido), cero red, cero OpenAI/Anthropic, cero mutación de la DATA INAMOVIBLE. Exit 0 = todo PASS.

Corre:  python rag_index/query_service/smoke_pubmed_tool.py
"""
import importlib.util
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
from lib import net_throttle  # noqa: E402

# --- máscara offline: la tool NO debe depender de ninguna de estas; se fijan por disciplina de la casa --
os.environ["NEO4J_URI"] = ""
os.environ["RAG_BACKEND"] = "sparse"
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
for _k in ("NCBI_API_KEY", "WITT_NCBI_EMAIL", "WITT_NCBI_MIN_INTERVAL_S", "WITT_PATH_B_RETMAX"):
    os.environ.pop(_k, None)


def _load_tool():
    """Carga POR RUTA, igual que answer_pipeline._workspace_tool (el directorio va con punto: no es paquete)."""
    path = ROOT / ".tooluniverse" / "tools" / "pubmed_literature.py"
    spec = importlib.util.spec_from_file_location("_witt_ws_pubmed_literature", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pl = _load_tool()

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


# ---- urlopen falso -----------------------------------------------------------------------------------
ESEARCH_JS = {"esearchresult": {"count": "9", "idlist": ["19666820", "12668625"]}}
ESUMMARY_JS = {"result": {
    "19666820": {"title": "RA responsive element controls wt1a", "pubdate": "2009 Aug 15",
                 "fulljournalname": "Development"},
    "12668625": {"title": "wt1 in the zebrafish pronephros", "pubdate": "2003", "source": "Dev Biol"},
}}


class _FakeResp:
    def __init__(self, js, headers=None):
        self._body = json.dumps(js).encode("utf-8")
        self.headers = dict(headers or {})

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeNet:
    """Simula urlopen. `plan` es una lista de respuestas por llamada: dict json | HTTPError | 'ok'."""

    def __init__(self, plan=None, headers=None):
        self.calls = []       # (monotonic, url)
        self.plan = list(plan or [])
        self.headers = headers

    def __call__(self, req, timeout=30):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        self.calls.append((time.monotonic(), url))
        step = self.plan.pop(0) if self.plan else "ok"
        if isinstance(step, Exception):
            raise step
        if step == "ok":
            js = ESEARCH_JS if "esearch.fcgi" in url else ESUMMARY_JS
        else:
            js = step
        return _FakeResp(js, self.headers)

    @property
    def urls(self):
        return [u for _, u in self.calls]


def _http_error(code, headers=None):
    hdrs = None
    if headers:
        import email.message
        hdrs = email.message.Message()
        for k, v in headers.items():
            hdrs[k] = v
    return urllib.error.HTTPError("https://eutils.ncbi.nlm.nih.gov/x", code, "Too Many Requests",
                                  hdrs, io.BytesIO(b""))


_real_urlopen = urllib.request.urlopen
_real_sleep = net_throttle._sleep


def _with_net(fake, fn, sleep_stub=None):
    urllib.request.urlopen = fake
    if sleep_stub is not None:
        net_throttle._sleep = sleep_stub
    try:
        return fn()
    finally:
        urllib.request.urlopen = _real_urlopen
        net_throttle._sleep = _real_sleep


def _fast():
    """Throttle a 0 s para las pruebas donde el tiempo NO es el objeto medido."""
    os.environ["WITT_NCBI_MIN_INTERVAL_S"] = "0"


def _retry_sleep_recorder(slept):
    """Stub de net_throttle._sleep que REGISTRA (sin dormir) las esperas del reintento 429 (>= 0.5 s) y
    deja pasar al sleep real las del throttle (< 0.5 s): el throttle mide contra monotonic y un stub que
    no dormía lo hacía girar; separar por magnitud mantiene ambas mediciones honestas."""
    return lambda secs: slept.append(secs) if secs >= 0.5 else _real_sleep(secs)


# ==== 1. contrato viejo conservado + campos nuevos ====================================================
_fast()
net = FakeNet(headers={"X-RateLimit-Limit": "3", "X-RateLimit-Remaining": "2", "Content-Type": "application/json"})
out = _with_net(net, lambda: pl.query_pubmed("wt1a zebrafish pronephros"))
check("contrato viejo CONSERVADO: status/data/query/n_found_total/records[pmid,title,year,journal]",
      out["status"] == "success" and out["data"]["query"] == "wt1a zebrafish pronephros"
      and out["data"]["n_found_total"] == 9 and len(out["data"]["records"]) == 2
      and out["data"]["records"][0] == {"pmid": "19666820", "title": "RA responsive element controls wt1a",
                                        "year": "2009", "journal": "Development"}
      and out["data"]["records"][1]["journal"] == "Dev Biol", json.dumps(out["data"]["records"][0]))
check("campos nuevos presentes: ncbi_identity/throttle/retries_429/rate_limit_headers/query_sent/retmax_sent",
      all(k in out for k in ("ncbi_identity", "throttle", "retries_429", "rate_limit_headers"))
      and all(k in out["data"] for k in ("query_sent", "retmax_sent")))
check("query_sent es el término LITERAL enviado (sin URL, sin llave)",
      out["data"]["query_sent"] == "wt1a zebrafish pronephros")
check("rate_limit_headers = MEDICIÓN: solo X-RateLimit-* tal como vinieron",
      out["rate_limit_headers"] == {"X-RateLimit-Limit": "3", "X-RateLimit-Remaining": "2"},
      json.dumps(out["rate_limit_headers"]))
check("esearch + esummary = 2 llamadas, en ese orden",
      len(net.urls) == 2 and "esearch.fcgi" in net.urls[0] and "esummary.fcgi" in net.urls[1])

net2 = FakeNet(headers={"Content-Type": "application/json"})
out2 = _with_net(net2, lambda: pl.query_pubmed("q"))
check("sin cabeceras X-RateLimit -> rate_limit_headers None DECLARADO (ausente ≠ {} ≠ valor)",
      out2["status"] == "success" and "rate_limit_headers" in out2 and out2["rate_limit_headers"] is None)

# ==== 2. identidad NCBI ================================================================================
os.environ.pop("WITT_NCBI_EMAIL", None)
net = FakeNet()
out = _with_net(net, lambda: pl.query_pubmed("q"))
check("sin WITT_NCBI_EMAIL: tool=witt-organogenesis viaja en esearch Y esummary",
      all("tool=witt-organogenesis" in u for u in net.urls) and len(net.urls) == 2)
check("sin WITT_NCBI_EMAIL: NO se manda email (ninguno inventado) y ncbi_identity='missing' declarado",
      all("email=" not in u for u in net.urls) and out["ncbi_identity"] == "missing")

os.environ["WITT_NCBI_EMAIL"] = "smoke@example.invalid"
net = FakeNet()
out = _with_net(net, lambda: pl.query_pubmed("q"))
check("con WITT_NCBI_EMAIL: email=<env> viaja en esearch Y esummary junto con tool=",
      all("email=smoke%40example.invalid" in u and "tool=witt-organogenesis" in u for u in net.urls)
      and len(net.urls) == 2)
check("con WITT_NCBI_EMAIL: ncbi_identity='declared'", out["ncbi_identity"] == "declared")
os.environ.pop("WITT_NCBI_EMAIL", None)

# ==== 3. retmax =========================================================================================
import re


def _retmax_in(url):
    m = re.search(r"[&?]retmax=(\d+)", url)
    return int(m.group(1)) if m else None


os.environ.pop("WITT_PATH_B_RETMAX", None)
net = FakeNet()
out = _with_net(net, lambda: pl.query_pubmed("q"))
check("retmax default 20 (sin env, sin argumento) viaja en la URL de esearch y se declara retmax_sent",
      _retmax_in(net.urls[0]) == 20 and out["data"]["retmax_sent"] == 20, net.urls[0][:120])
os.environ["WITT_PATH_B_RETMAX"] = "7"
net = FakeNet()
out = _with_net(net, lambda: pl.query_pubmed("q"))
check("WITT_PATH_B_RETMAX=7 -> retmax=7 en la URL",
      _retmax_in(net.urls[0]) == 7 and out["data"]["retmax_sent"] == 7)
net = FakeNet()
out = _with_net(net, lambda: pl.query_pubmed("q", retmax=3))
check("argumento retmax=3 gana sobre la env", _retmax_in(net.urls[0]) == 3 and out["data"]["retmax_sent"] == 3)
net = FakeNet()
out = _with_net(net, lambda: pl.query_pubmed("q", limit=4))
check("alias legado limit=4 sigue funcionando (callers viejos no se rompen)",
      _retmax_in(net.urls[0]) == 4 and out["data"]["retmax_sent"] == 4)
os.environ.pop("WITT_PATH_B_RETMAX", None)
check("sort=relevance se conserva en esearch", "sort=relevance" in net.urls[0])

# ==== 4. throttle: derivación del intervalo ============================================================
os.environ.pop("WITT_NCBI_MIN_INTERVAL_S", None)
os.environ.pop("NCBI_API_KEY", None)
check("intervalo derivado sin NCBI_API_KEY = 0.34 s", pl.resolve_min_interval_s() == (0.34, "derived"))
os.environ["NCBI_API_KEY"] = "smoke-fake-key-not-a-secret"
check("intervalo derivado con NCBI_API_KEY = 0.10 s", pl.resolve_min_interval_s() == (0.10, "derived"))
os.environ["WITT_NCBI_MIN_INTERVAL_S"] = "0.5"
check("WITT_NCBI_MIN_INTERVAL_S sobreescribe la derivación", pl.resolve_min_interval_s() == (0.5, "env"))
_fast()
net = FakeNet()
out = _with_net(net, lambda: pl.query_pubmed("q"))
check("la llave viaja en la URL pero JAMÁS en la salida (query_sent/throttle/data no la filtran)",
      all("api_key=smoke-fake-key-not-a-secret" in u for u in net.urls)
      and "smoke-fake-key" not in json.dumps(out) and out["throttle"]["api_key_present"] is True)
os.environ.pop("NCBI_API_KEY", None)

# ==== 5. throttle: respeta el intervalo (medido con monotonic entre llamadas simuladas) ===============
os.environ["WITT_NCBI_MIN_INTERVAL_S"] = "0.05"
net = FakeNet()
outs = _with_net(net, lambda: [pl.query_pubmed("q1"), pl.query_pubmed("q2"), pl.query_pubmed("q3")])
ts = [t for t, _ in net.calls]
deltas = [b - a for a, b in zip(ts, ts[1:])]
check("3 query_pubmed = 6 llamadas simuladas; cada delta consecutivo >= 0.05 s (tolerancia 5 ms)",
      len(ts) == 6 and all(d >= 0.045 for d in deltas),
      "deltas=" + ",".join(f"{d:.3f}" for d in deltas))
check("waited_s medido > 0 en al menos una corrida y el intervalo declarado = 0.05",
      any(o["throttle"]["waited_s"] > 0 for o in outs)
      and all(o["throttle"]["min_interval_s"] == 0.05 and o["throttle"]["host"] == "eutils.ncbi.nlm.nih.gov"
              for o in outs))
thr_a = net_throttle.get_throttle("eutils.ncbi.nlm.nih.gov")
thr_b = net_throttle.get_throttle("eutils.ncbi.nlm.nih.gov", 0.05)
check("registro a nivel PROCESO: get_throttle(host) devuelve el MISMO objeto (hilos del mismo uvicorn, ADR-0048)",
      thr_a is thr_b and thr_a is net_throttle._REGISTRY["eutils.ncbi.nlm.nih.gov"])
try:
    net_throttle.get_throttle("host.desconocido.invalid")
    _raised = False
except ValueError:
    _raised = True
check("host nuevo sin intervalo -> ValueError (un throttle con intervalo no declarado es default disfrazado)", _raised)

# ==== 6. 429 -> UN reintento ============================================================================
_fast()
slept = []
net = FakeNet(plan=[_http_error(429, {"Retry-After": "2"}), "ok", "ok"])
out = _with_net(net, lambda: pl.query_pubmed("q"), sleep_stub=_retry_sleep_recorder(slept))
check("429 en esearch con Retry-After: 2 -> espera 2 s (stub), reintenta UNA vez y la corrida sale success",
      out["status"] == "success" and out["retries_429"] == 1 and slept == [2.0] and len(net.urls) == 3,
      f"slept={slept} calls={len(net.urls)}")

slept = []
net = FakeNet(plan=[_http_error(429), "ok", "ok"])
out = _with_net(net, lambda: pl.query_pubmed("q"), sleep_stub=_retry_sleep_recorder(slept))
check("429 SIN Retry-After -> espera default 1 s declarada", out["status"] == "success" and slept == [1.0])

slept = []
net = FakeNet(plan=[_http_error(429), _http_error(429)])
out = _with_net(net, lambda: pl.query_pubmed("q"), sleep_stub=_retry_sleep_recorder(slept))
check("429 + 429 -> exactamente 2 llamadas (1 reintento, NUNCA loop) y status 'error' DECLARADO con http_status 429",
      out["status"] == "error" and out["http_status"] == 429 and out["retries_429"] == 1
      and len(net.urls) == 2 and slept == [1.0] and "429" in out["error"], out["error"])
check("el error conserva query_sent/retmax_sent/ncbi_identity para el ledger",
      out["data"]["query_sent"] == "q" and out["data"]["retmax_sent"] == 20 and out["ncbi_identity"] == "missing")

slept = []
net = FakeNet(plan=[_http_error(500)])
out = _with_net(net, lambda: pl.query_pubmed("q"), sleep_stub=_retry_sleep_recorder(slept))
check("500 -> error declarado SIN reintento (solo 429 reintenta)",
      out["status"] == "error" and out["http_status"] == 500 and out["retries_429"] == 0
      and len(net.urls) == 1 and slept == [])

# ==== 7. bordes ==========================================================================================
out = _with_net(FakeNet(), lambda: pl.query_pubmed("   "))
check("query vacía -> error declarado, cero llamadas", out["status"] == "error" and out["error"] == "empty query")
net = FakeNet(plan=[{"esearchresult": {"count": "0", "idlist": []}}])
out = _with_net(net, lambda: pl.query_pubmed("q"))
check("0 resultados -> success con records=[] y n_found_total=0 (≠ error), y NO se llama esummary",
      out["status"] == "success" and out["data"]["records"] == [] and out["data"]["n_found_total"] == 0
      and len(net.urls) == 1)
check("retry_once_on_429: parse_retry_after acota y rechaza basura",
      net_throttle.parse_retry_after("3") == 3.0 and net_throttle.parse_retry_after("Wed, 21 Oct 2015") is None
      and net_throttle.parse_retry_after("999") == 60.0 and net_throttle.parse_retry_after(None) is None)
check("la tool sigue stdlib-pura: ningún import fuera de stdlib",
      not any(m in sys.modules for m in ("requests", "httpx", "tooluniverse")))

# ---- resumen ---------------------------------------------------------------------------------------------
os.environ.pop("WITT_NCBI_MIN_INTERVAL_S", None)
n_ok, n = sum(CHECKS), len(CHECKS)
print(f"\n{n_ok}/{n} PASS")
sys.exit(0 if n_ok == n else 1)

"""smoke_fetch_paper.py — gate determinista de la higiene Europe PMC / fetch_paper (ADR-0078, rebanada I3).

Cubre: search_europepmc_ledger devuelve (items, ledger) y JAMAS relanza (§6 no-hang: red que truena =>
status 'error' + items=[]; hitCount 0 => 'no-match'; exito => 'success' con n_found medido del hitCount);
sort/synonym viajan en la URL y quedan declarados en el ledger; la fecha de descarga es la UTC real
(no el literal '20260613') y el JSON cacheado trae 'fetched_at'; cache de LECTURA por identificador
(hit fresco => cache_hit=True + cached_at, sin red; caducado o legado viejo => red); UA sin correo
hardcodeado (WITT_NCBI_EMAIL o 'contact: unset' declarado); throttle declarado en el ledger; y la
firma legada search_europepmc sigue viva (relanza, como antes, para sus llamadores actuales).
Corrector ADR-0078 (2026-09-14): el ledger declara contact 'declared'|'unset' y JAMAS el correo (viaja al
bundle, a la API y al prompt); n_found nunca se rellena con el tamano de pagina (hitCount ausente => None +
n_found_note); n_returned es None cuando la busqueda no corrio; throttle_slept_s es de ESTA llamada (meta
por llamada, sin global de modulo); net_throttle es import duro (sin 'noop-missing-net_throttle').

100% offline: red monkeypatcheada (fetch_paper._get), mcp_cache TEMPORAL — cero red, cero spend,
cero mutacion de la DATA INAMOVIBLE ni del mcp_cache del repo. Exit 0 = todo PASS.

Corre:  python rag_index/query_service/smoke_fetch_paper.py
"""
import json
import os
import re
import sys
import tempfile
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
os.environ.pop("WITT_NCBI_EMAIL", None)   # arrancamos SIN contacto para probar la declaracion 'unset'
os.environ.pop("WITT_CACHE_TTL_DAYS", None)
os.environ["WITT_EPMC_MIN_INTERVAL_S"] = "0.01"   # throttle REAL pero rapido: el smoke no debe tardar segundos durmiendo
from lib import fetch_paper  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="smoke_fetch_paper_"))
CACHE = TMP / "mcp_cache"

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


# ---- red falsa: registra URLs y UA, devuelve lo que le programemos -------------------------------
CALLS = []          # urls pedidas
UAS = []            # user-agents que se HABRIAN mandado (capturados via fetch_paper._ua)
_REAL_GET = fetch_paper._get
_REAL_UA = fetch_paper._ua


def _ua_spy():
    ua = _REAL_UA()
    UAS.append(ua["User-Agent"])
    return ua


fetch_paper._ua = _ua_spy


def _mk_get(payload=None, exc=None, raw=None):
    def _fake(url, parse_json=False, meta=None):
        CALLS.append(url)
        backend, slept = fetch_paper._throttle()   # el _get real pasa por el throttle y construye el UA por
        fetch_paper._ua()                          # request; lo emulamos para que el ledger declare lo mismo
        if meta is not None:                       # que en produccion (medicion POR LLAMADA, ADR-0078 corrector)
            meta["throttle"], meta["throttle_slept_s"] = backend, slept
        if exc is not None:
            raise exc
        if not parse_json:
            return raw if raw is not None else ""
        if callable(payload):
            return payload(url)
        return payload
    return _fake


def _epmc_payload(results, hit_count=None):
    return {"hitCount": len(results) if hit_count is None else hit_count,
            "resultList": {"result": results}}


REC_A = {"id": "24496627", "source": "MED", "pmid": "24496627", "pmcid": "PMC3989452",
         "doi": "10.1242/dev.101808", "title": "osr1 in zebrafish pronephros", "pubYear": "2014",
         "journalInfo": {"journal": {"title": "Development"}}, "isOpenAccess": "N",
         "abstractText": "The gene osr1 is required for pronephros formation in zebrafish embryos.", "citedByCount": 42}
REC_B = {"id": "28409341", "source": "MED", "pmid": "28409341", "pmcid": None, "doi": None,
         "title": "Zebrafish Pronephros Development.", "pubYear": "2017",
         "journalInfo": {"journal": {"title": "Results Probl Cell Differ"}}, "isOpenAccess": "N",
         "abstractText": "The pronephros is the first kidney type.", "citedByCount": 7}

# ---- 1. §6 no-hang: la red truena => status 'error', items=[], SIN excepcion ----------------------
for label, exc in (("URLError", urllib.error.URLError("name resolution failed")),
                   ("timeout", TimeoutError("read timed out")),
                   ("JSON roto", json.JSONDecodeError("Expecting value", "<html>", 0)),
                   ("HTTPError 503", urllib.error.HTTPError("u", 503, "Service Unavailable", {}, None))):
    fetch_paper._get = _mk_get(exc=exc)
    try:
        items, ledger = fetch_paper.search_europepmc_ledger("osr1 pronephros", n=5)
        check(f"red {label}: NO relanza, status='error', items=[]",
              items == [] and ledger["status"] == "error" and ledger["source"] == "europepmc",
              ledger.get("error", ""))
        check(f"red {label}: el error queda DECLARADO (str no vacio) + elapsed_s medido + n_returned None (no midio, no 0)",
              isinstance(ledger.get("error"), str) and ledger["error"] and isinstance(ledger["elapsed_s"], float)
              and ledger["n_returned"] is None)
    except Exception as e:
        check(f"red {label}: NO relanza", False, f"relanzo {type(e).__name__}: {e}")
        check(f"red {label}: el error queda DECLARADO", False, "no hubo ledger")

# ---- 2. no-match: hitCount 0 es 'searched and found nothing', NO error --------------------------
fetch_paper._get = _mk_get(payload=_epmc_payload([], hit_count=0))
items, ledger = fetch_paper.search_europepmc_ledger("xyzzy nonexistent gene", n=5)
check("hitCount 0 => status 'no-match', items=[], n_found=0, sin 'error'",
      items == [] and ledger["status"] == "no-match" and ledger["n_found"] == 0 and "error" not in ledger,
      json.dumps({k: ledger[k] for k in ("status", "n_found", "n_returned")}))

# ---- 3. exito: items normalizados + ledger con hitCount MEDIDO, sort/synonym declarados ----------
CALLS.clear()
fetch_paper._get = _mk_get(payload=_epmc_payload([REC_A, REC_B], hit_count=137))
items, ledger = fetch_paper.search_europepmc_ledger("osr1 pronephros", n=2, sort="CITED", synonym=False)
check("exito: status 'success', 2 items, n_found=137 (hitCount, medicion) y n_returned=2",
      ledger["status"] == "success" and len(items) == 2 and ledger["n_found"] == 137 and ledger["n_returned"] == 2)
check("items normalizados (pmid/pmcid/doi/title/year/journal/is_oa/abstract/cited_by)",
      items[0]["pmid"] == "24496627" and items[0]["journal"] == "Development" and items[0]["is_oa"] is False
      and items[0]["cited_by"] == 42 and items[1]["pmcid"] is None)
check("ledger declara query_sent, sort='CITED', synonym=False, throttle, contact ('unset' = estado, no correo)",
      ledger["query_sent"] == "osr1 pronephros" and ledger["sort"] == "CITED" and ledger["synonym"] is False
      and ledger["throttle"] and ledger["contact"] == "unset",
      json.dumps({k: ledger[k] for k in ("sort", "synonym", "throttle", "contact")}))
check("la URL lleva sort=CITED desc, synonym=FALSE, pageSize=2 (lo declarado ES lo enviado)",
      len(CALLS) == 1 and "sort=CITED+desc" in CALLS[0] and "synonym=FALSE" in CALLS[0] and "pageSize=2" in CALLS[0],
      CALLS[0] if CALLS else "-")
fetch_paper._get = _mk_get(payload={"resultList": {"result": [REC_A, REC_B]}})   # payload SIN hitCount
_, ledger_nh = fetch_paper.search_europepmc_ledger("osr1 pronephros", n=2)
check("corrector: hitCount AUSENTE -> n_found None + n_found_note (jamas se rellena con el tamano de pagina 2)",
      ledger_nh["status"] == "success" and ledger_nh["n_found"] is None and ledger_nh["n_returned"] == 2
      and "hitCount absent" in ledger_nh.get("n_found_note", ""), json.dumps({k: ledger_nh.get(k) for k in ("n_found", "n_returned", "n_found_note")}))
CALLS.clear()
items, ledger = fetch_paper.search_europepmc_ledger("osr1 pronephros", n=3)
check("default: sort=RELEVANCE (sin parametro sort en la URL), synonym=TRUE",
      ledger["sort"] == "RELEVANCE" and "sort=" not in CALLS[0] and "synonym=TRUE" in CALLS[0], CALLS[0])
check("throttle declarado: backend net_throttle (import DURO, sin no-op) + throttle_slept_s MEDIDO de esta llamada",
      ledger["throttle"] == "net_throttle" and isinstance(ledger["throttle_slept_s"], float)
      and not hasattr(fetch_paper, "_LAST_THROTTLE"),
      json.dumps({k: ledger[k] for k in ("throttle", "throttle_slept_s")}))
_, ledger_b = fetch_paper.search_europepmc_ledger("osr1", n=3)
check("throttle real: la segunda llamada consecutiva SI duerme (>0 s) con WITT_EPMC_MIN_INTERVAL_S=0.01",
      ledger_b["throttle"] != "net_throttle" or (ledger_b["throttle_slept_s"] or 0) > 0,
      json.dumps({k: ledger_b[k] for k in ("throttle", "throttle_slept_s")}))
CALLS.clear()
items, ledger = fetch_paper.search_europepmc_ledger("osr1", n=3, sort="BOGUS")
check("sort desconocido: status 'error' declarado sin ir a la red (no se manda basura a EPMC)",
      ledger["status"] == "error" and "unknown sort" in ledger["error"] and len(CALLS) == 0)

# ---- 4. firma legada search_europepmc: sigue devolviendo lista y sigue RELANZANDO ---------------
fetch_paper._get = _mk_get(payload=_epmc_payload([REC_A]))
legacy = fetch_paper.search_europepmc("osr1", n=1)
check("legado search_europepmc(query, n) devuelve la lista normalizada (compat integrador)",
      isinstance(legacy, list) and legacy[0]["pmid"] == "24496627")
fetch_paper._get = _mk_get(exc=urllib.error.URLError("down"))
try:
    fetch_paper.search_europepmc("osr1", n=1)
    check("legado search_europepmc RELANZA en fallo (semantica intacta para _fetch_or_declare)", False)
except urllib.error.URLError:
    check("legado search_europepmc RELANZA en fallo (semantica intacta para _fetch_or_declare)", True)

# ---- 5. UA: sin correo hardcodeado; WITT_NCBI_EMAIL manda, si falta => 'contact: unset' ----------
check("UA sin correo hardcodeado y con 'contact: unset' cuando WITT_NCBI_EMAIL falta",
      UAS and all("@" not in u and "contact: unset" in u for u in UAS), UAS[-1] if UAS else "-")
os.environ["WITT_NCBI_EMAIL"] = "smoke-contact@example.invalid"
UAS.clear()
fetch_paper._get = _mk_get(payload=_epmc_payload([REC_A]))
_, ledger = fetch_paper.search_europepmc_ledger("osr1", n=1)
check("UA usa WITT_NCBI_EMAIL como contact; el ledger declara contact='declared' y JAMAS lleva el correo "
      "(el ledger viaja al bundle, a GET /runs/{id} y al prompt de 5 modelos — corrector ADR-0078)",
      UAS and "contact: smoke-contact@example.invalid" in UAS[-1] and ledger["contact"] == "declared"
      and "@" not in json.dumps(ledger, ensure_ascii=False),
      f"ua={UAS[-1] if UAS else '-'} contact={ledger['contact']}")
got_e = fetch_paper.fetch_external("PMID:24496627", want_full_text=False, cache_dir=TMP / "mcp_cache_email")
check("fetch_external con WITT_NCBI_EMAIL: ningun '@' en TODA la respuesta (search_ledger incluido)",
      got_e["found"] is True and "@" not in json.dumps(got_e, ensure_ascii=False, default=str))
os.environ.pop("WITT_NCBI_EMAIL", None)

# ---- 6. fetch_external: fecha UTC real + fetched_at en el JSON cacheado (cache temporal) ---------
CALLS.clear()
fetch_paper._get = _mk_get(payload=_epmc_payload([REC_A], hit_count=1))
got = fetch_paper.fetch_external("PMID:24496627", want_full_text=False, cache_dir=CACHE)
today = datetime.now(timezone.utc).strftime("%Y%m%d")
files = sorted(p.name for p in CACHE.glob("raw_paper_*"))
check("fetch_external found=True, cache_hit=False (primera vez), search_ledger success",
      got["found"] is True and got["cache_hit"] is False and got["search_ledger"]["status"] == "success")
check(f"stamp del archivo = fecha UTC REAL ({today}), no el literal 20260613",
      any(n == f"raw_paper_PMC3989452_{today}.json" for n in files) and not any("20260613" in n for n in files),
      ",".join(files))
js = json.loads((CACHE / f"raw_paper_PMC3989452_{today}.json").read_text(encoding="utf-8"))
check("JSON cacheado trae fetched_at ISO-8601 UTC ('Z') + record crudo (§7.9)",
      re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", js.get("fetched_at", "")) is not None
      and js["record"]["pmid"] == "24496627" and js["source"] == "europepmc", js.get("fetched_at"))
check("respuesta declara fetched_at (== el del JSON), cached_at=None, cache_ttl_days=7 (default)",
      got["fetched_at"] == js["fetched_at"] and got["cached_at"] is None and got["cache_ttl_days"] == 7.0)
check("raw_cached lista .json + .txt del stamp real; n_chunks>0 desde el abstract",
      len(got["raw_cached"]) == 2 and got["n_chunks"] >= 1 and got["full_text"] is False)
n_calls_first = len(CALLS)

# ---- 7. cache de LECTURA: segunda llamada => cache_hit=True, cached_at, CERO red ----------------
fetch_paper._get = _mk_get(exc=RuntimeError("la red NO debe tocarse en un cache hit"))
got2 = fetch_paper.fetch_external("PMID:24496627", want_full_text=False, cache_dir=CACHE)
check("segunda llamada: cache_hit=True + cached_at + cached_at_source='fetched_at', sin red",
      got2["found"] is True and got2["cache_hit"] is True and got2["cached_at"] == js["fetched_at"]
      and got2["cached_at_source"] == "fetched_at" and len(CALLS) == n_calls_first,
      json.dumps({k: got2[k] for k in ("cache_hit", "cached_at", "cached_at_source", "cache_age_days")}))
check("cache hit NO se presenta como fresco: fetched_at == cached_at, search_ledger=None (no hubo busqueda)",
      got2["fetched_at"] == got2["cached_at"] and got2["search_ledger"] is None and got2["cache_age_days"] >= 0)
got2b = fetch_paper.fetch_external("PMC3989452", want_full_text=False, cache_dir=CACHE)
check("cache hit por PMCID del mismo paper (match contra el record, no solo el nombre de archivo)",
      got2b["cache_hit"] is True and len(CALLS) == n_calls_first)
got2c = fetch_paper.fetch_external("DOI:10.1242/dev.101808", want_full_text=False, cache_dir=CACHE)
check("cache hit por DOI del mismo paper", got2c["cache_hit"] is True and len(CALLS) == n_calls_first)

# ---- 8. cache CADUCADO (fetched_at hace 30 dias, TTL 7) => va a la red, cache_hit=False ----------
CACHE2 = TMP / "mcp_cache_stale"
CACHE2.mkdir()
old = (datetime.now(timezone.utc) - timedelta(days=30)).replace(microsecond=0)
(CACHE2 / f"raw_paper_28409341_{old.strftime('%Y%m%d')}.json").write_text(json.dumps(
    {"fetched_at": old.isoformat().replace("+00:00", "Z"), "source": "europepmc", "ident": "PMID:28409341",
     "record": fetch_paper._normalize_hit(REC_B)}), encoding="utf-8")
CALLS.clear()
fetch_paper._get = _mk_get(payload=_epmc_payload([REC_B], hit_count=1))
got3 = fetch_paper.fetch_external("PMID:28409341", want_full_text=False, cache_dir=CACHE2)
check("cache de 30 dias con TTL 7: MISS declarado (cache_hit=False) y SI va a la red",
      got3["cache_hit"] is False and len(CALLS) == 1 and got3["found"] is True)
check("el miss re-cachea con el stamp de HOY (el archivo viejo no se toca)",
      (CACHE2 / f"raw_paper_28409341_{today}.json").exists()
      and (CACHE2 / f"raw_paper_28409341_{old.strftime('%Y%m%d')}.json").exists())
os.environ["WITT_CACHE_TTL_DAYS"] = "60"
fetch_paper._get = _mk_get(exc=RuntimeError("no red"))
got3b = fetch_paper.fetch_external("PMID:28409341", want_full_text=False, cache_dir=CACHE2)
check("WITT_CACHE_TTL_DAYS=60 se lee en tiempo de llamada: ahora es hit y toma el MAS reciente",
      got3b["cache_hit"] is True and got3b["cache_ttl_days"] == 60.0 and got3b["cached_at"] != old.isoformat().replace("+00:00", "Z"))
got3c = fetch_paper.fetch_external("PMID:28409341", want_full_text=False, cache_dir=CACHE2, ttl_days=0)
check("ttl_days=0 explicito fuerza la red (y la red caida => found=False + fetch_error declarado, sin excepcion)",
      got3c["found"] is False and got3c["cache_hit"] is False and "RuntimeError" in got3c["fetch_error"]
      and got3c["search_ledger"]["status"] == "error")
os.environ.pop("WITT_CACHE_TTL_DAYS", None)

# ---- 9. archivo LEGADO (flat, sin fetched_at): reloj = mtime, declarado como tal ------------------
CACHE3 = TMP / "mcp_cache_legacy"
CACHE3.mkdir()
legacy_p = CACHE3 / "raw_paper_28409341_20260613.json"
legacy_p.write_text(json.dumps(fetch_paper._normalize_hit(REC_B)), encoding="utf-8")   # formato pre-ADR-0078
fetch_paper._get = _mk_get(exc=RuntimeError("no red"))
got4 = fetch_paper.fetch_external("PMID:28409341", want_full_text=False, cache_dir=CACHE3)
check("legado flat recien escrito (mtime fresco): hit con cached_at_source='mtime' DECLARADO",
      got4["cache_hit"] is True and got4["cached_at_source"] == "mtime")
old_ts = (datetime.now(timezone.utc) - timedelta(days=90)).timestamp()
os.utime(legacy_p, (old_ts, old_ts))
CALLS.clear()
fetch_paper._get = _mk_get(payload=_epmc_payload([REC_B], hit_count=1))
got4b = fetch_paper.fetch_external("PMID:28409341", want_full_text=False, cache_dir=CACHE3)
check("legado con mtime de 90 dias (como los 20260613 del repo): MISS, va a la red",
      got4b["cache_hit"] is False and len(CALLS) == 1)

# ---- 10. no-match en fetch_external: found=False, note, sin fetch_error --------------------------
fetch_paper._get = _mk_get(payload=_epmc_payload([], hit_count=0))
got5 = fetch_paper.fetch_external("PMID:99999999", want_full_text=False, cache_dir=CACHE)
check("no-match: found=False + note 'no Europe PMC match' + search_ledger no-match, sin fetch_error",
      got5["found"] is False and got5["note"] == "no Europe PMC match"
      and got5["search_ledger"]["status"] == "no-match" and "fetch_error" not in got5)

# ---- 11. free-text ident: sin identificador no hay cache posible => siempre busca -----------------
CALLS.clear()
fetch_paper._get = _mk_get(payload=_epmc_payload([REC_A], hit_count=5))
got6 = fetch_paper.fetch_external("zebrafish pronephros osr1", want_full_text=False, cache_dir=CACHE)
check("free-text: va a la red (no hay id que casar) y cachea bajo el id del record (PMC3989452)",
      len(CALLS) == 1 and got6["found"] is True and got6["cache_hit"] is False
      and any("PMC3989452" in p for p in got6["raw_cached"]))

# ---- 12. higiene: el mcp_cache del REPO no se toco -----------------------------------------------
repo_cache = ROOT / "mcp_cache"
check("mcp_cache del repo intacto (ningun raw_paper con stamp de hoy)",
      not any(repo_cache.glob(f"raw_paper_*_{today}*")) if repo_cache.exists() else True)

fetch_paper._get = _REAL_GET
fetch_paper._ua = _REAL_UA
n_ok, n_all = sum(CHECKS), len(CHECKS)
print(f"\n{n_ok}/{n_all} PASS  (tmp={TMP})")
sys.exit(0 if n_ok == n_all else 1)

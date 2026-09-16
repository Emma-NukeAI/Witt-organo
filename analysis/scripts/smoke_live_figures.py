"""
smoke_live_figures.py — ADR-0083 § Gates EN VIVO: el instrumento de LG1 (bytes REALES de Europe PMC), del respaldo
`--href-direct` (LG1 bis), de LG4 (formas de imagen por transporte con los callers REALES) y de `--count-tokens`
(Δ de tokens de imagen = MEDICIÓN). Lo corre Emmanuel; GASTA lo que dice; jamás toca la BD.

Ningún smoke del CI gasta modelo ni red (ADR-0083 (M.5)): todo lo que aquí llama a la red o a una API lo hace con la
llave del entorno del proceso de Emmanuel. Este script NO replica nada: usa `lib.figures` (parser JATS, licencia por
tabla, `fetch_figures`, `select_for_panel`, bloques por transporte) y los callers REALES de `lib.composite_auditor`
con `user_content=` (F3). Si un caller aún no acepta `user_content`, lo DICE (`caller-without-user_content`) y no llama.

  LG1  --pmcid PMC11379296 [--xml <ruta>] [--fetch-xml]
       UN GET a {EPMC}/{PMCID}/supplementaryFiles por `figures.fetch_figures` (la ÚNICA costura de red del módulo,
       con net_throttle y la UA de fetch_paper): HTTP, Content-Type, bytes del zip, entradas, elapsed_s y MB/s
       (calibra WITT_FIGURES_BUDGET_S); por figura sha256 / bytes / mime por magic / dims por cabecera vs `scaled`
       declaradas; si el PMCID está en fixtures/figures/MANIFEST.json se compara sha y dims con lo MEDIDO el
       2026-09-08 (g001 40877777ed82… 750×417 …). El XML se localiza en mcp_cache (raw_paper_<PMCID>_*_fulltext.xml),
       en los fixtures o por --xml; con --fetch-xml se baja (1 GET más). Sin XML: sólo se SONDEA el zip (probe-only).
       Un PMCID no-OA deja `not-fetched (http-4xx)` declarado — la fila existe, el script no falla (§6).
  LG1  --href-direct [--href <basename>]
       GET https://europepmc.org/articles/{PMCID}/bin/{href} — el href directo NO VERIFICADO del ADR (B.1): si 200 y el
       sha256 == el del miembro del zip, un 0083.1 aditivo lo declara como respaldo (30–100× menos bytes); si no, queda
       'no verificado' y el ADR no cambia.
  LG4  --judge <model> --api anthropic|responses|chat-completions [--lens evidence-grounding] [--image <sha>[,<sha>…]]
       UNA llamada real de juez con `VERDICT_TOOL` y las figuras VERIFICADAS en caché (`select_for_panel`: sha
       recalculado; jamás se envía un byte que no cuadre) como bloques del transporte REAL: `figures.anthropic_blocks`
       → `_anthropic_tool_call(..., user_content=)`; `figures.openai_responses_parts` → `_openai_responses_call(...,
       user_content=)`; `figures.openai_chat_parts` → `_openai_chat_call(..., user_content=)`. Mide: verdict ∈
       VOCABULARY, `usage`, `meta.model_reported`, latencia, `figure_readings` si el juez lo emitió, y — para
       chat.completions — que la forma pública 'not re-verified by doc' fue ACEPTADA por la API (LG4 la fija).
  LG4  --count-tokens (sólo Anthropic; 2 llamadas a /v1/messages/count_tokens, USD 0)
       tokens del MISMO cuerpo con y sin bloques de imagen → Δ = MEDICIÓN de los tokens de visión (sustituye la
       proyección ⌈w/28⌉×⌈h/28⌉ de `models.vision_tokens` cuando F3 la exponga; aquí NO se replica la fórmula).

  --dry-run   construye TODO sin red ni llave: XML de fixtures, `figures._get_bytes` FALSEADO con el zip fixture (misma
              firma), caché en TMP, `fetch_figures` real sobre el fake (9 verified), URL del zip por `figures._zip_url`,
              URL del href directo, bloques de los TRES transportes (imágenes ANTES del texto; la b64 decodifica al
              byte original) y, si los callers ya aceptan `user_content`, el cuerpo/kwargs REALES capturados con
              `urlopen` BLOQUEADO y contado (== 0) y un cliente OpenAI falso. Es el ÚNICO modo que corre F8 (exit 0).

Doctrina (CLAUDE.md §7 + ADR-0083): la figura es MEDICIÓN sólo por fig_id + sha256 + licencia verificadas por código;
lo que la imagen dice es JUICIO (`figure_readings`, class 'model-judgment'); toda cifra lleva clase; ausente ≠ null ≠
valor. Salida: una línea por fila y `analysis/outputs/live_figures_<fecha>.json` (append por invocación) pasado por un
cinturón anti-secreto (nunca headers, env ni llaves — sólo su PRESENCIA) y anti-binario (ninguna b64 ni data:URL se
serializa: sólo largo + sha). Sin llave para la familia pedida rehúsa con `no-api-key` (exit 2) ANTES de tocar red.
Jamás importa `db`/`runs`/`app`/`record_pdf` (medido en cada salida: `db_imported false`).

Uso (venv de los gates: dev/.venvs/witt-query-service):
  python analysis/scripts/smoke_live_figures.py --dry-run
  python analysis/scripts/smoke_live_figures.py --pmcid PMC11379296 --href-direct
  python analysis/scripts/smoke_live_figures.py --pmcid PMC11647118
  python analysis/scripts/smoke_live_figures.py --pmcid PMC11379296 --judge <reviewer de models.MODELS, p. ej. el bridge> --api chat-completions --image 40877777ed82
  python analysis/scripts/smoke_live_figures.py --pmcid PMC11379296 --judge <reviewer Anthropic de models.MODELS> --api anthropic --count-tokens
  (los ids de modelo viven SOLO en analysis/scripts/lib/models.py — ADR-0081 (A); aquí no se copian)
"""
import argparse
import base64
import contextlib
import datetime as _dt
import hashlib
import inspect
import json
import os
import re
import sys
import tempfile
import time
import types
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))

# Windows: la consola/pipe de Emmanuel puede ser cp1252 y este script imprime UTF-8. Reemplazar, no tumbar la corrida.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # pragma: no cover
            pass

from lib import figures as F  # noqa: E402  — F1: parser, licencia, fetch, selección, bloques (stdlib puro)
from lib import models  # noqa: E402  — ADR-0081: la única tabla de modelos
from lib import fetch_paper  # noqa: E402  — CACHE (mcp_cache) para localizar el XML; _full_text_xml con --fetch-xml

OUT_DIR = ROOT / "analysis" / "outputs"
FIXTURES = ROOT / "rag_index" / "query_service" / "fixtures" / "figures"
MANIFEST_PATH = FIXTURES / "MANIFEST.json"
HREF_DIRECT_TEMPLATE = "https://europepmc.org/articles/{pmcid}/bin/{href}"   # NO verificado (ADR-0083 (B.1); LG1 lo mide)
COUNT_TOKENS_URL = "https://api.anthropic.com/v1/messages/count_tokens"
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
API_FLAGS = {"anthropic": "anthropic-messages", "responses": "openai-responses", "chat-completions": "openai-chat-completions"}
FORBIDDEN_MODULES = ("db", "runs", "app", "record_pdf", "council_jobs", "council_index")   # jamás la BD
EXIT_OK, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2
CLASS_MEASUREMENT = "medicion"
CLASS_PROJECTION = "proyeccion"


# ---------------------------------------------------------------------------------------------------------------
# Utilidades (mismas convenciones que smoke_live_models / smoke_live_council)
# ---------------------------------------------------------------------------------------------------------------
def _accepts(fn, name):
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    return name in params or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())


def _numeric(usage):
    return {k: v for k, v in (usage or {}).items() if isinstance(v, (int, float)) and not isinstance(v, bool)}


def _err(e):
    return f"{getattr(e, 'legacy_type_name', type(e).__name__)}: {str(e)[:200]}"


def _kind(e):
    return getattr(e, "kind", None) or "unclassified"


def _today():
    return _dt.datetime.now(_dt.timezone.utc)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


_SECRET_VALUE_RE = re.compile(r"(?i)(sk-[A-Za-z0-9_\-]{8,}|bearer\s+[A-Za-z0-9._\-]{8,}|api[_-]?key\s*[:=]\s*\S+)")
_SECRET_KEY_RE = re.compile(r"(?i)(api[_-]?key|authorization|x-api-key|secret|password|token$)")
_B64_RE = re.compile(r"^[A-Za-z0-9+/=\r\n]{512,}$")


def _strip_binary(obj):
    """Cinturón anti-binario (ADR-0074/0083 M.6): ninguna b64 ni data:URL sale al archivo ni a la consola — sólo su
    largo y el sha256 de los BYTES decodificados (así el lector puede cotejar con el sha congelado)."""
    if isinstance(obj, dict):
        return {k: _strip_binary(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_strip_binary(x) for x in obj]
    if isinstance(obj, str):
        if obj.startswith("data:") and ";base64," in obj[:64]:
            b64 = obj.split(";base64,", 1)[1]
            return _b64_placeholder(b64, prefix=obj.split(";base64,", 1)[0] + ";base64,")
        if len(obj) >= 512 and _B64_RE.match(obj):
            return _b64_placeholder(obj)
    return obj


def _b64_placeholder(b64, prefix=""):
    try:
        raw = base64.b64decode(b64, validate=False)
        return f"<{prefix}b64 {len(b64)} chars -> {len(raw)} bytes sha256:{_sha(raw)[:F.SHA_SHORT]}>"
    except Exception:
        return f"<{prefix}b64 {len(b64)} chars (undecodable)>"


def _redact(obj):
    """Cinturón anti-secreto: ningún valor que parezca llave sale; llaves con nombre de credencial se eliminan y se
    declaran en `_redacted_keys`. Las llaves `*_tokens` de usage NO son secretos (la regex exige 'token' al final)."""
    if isinstance(obj, dict):
        out, dropped = {}, []
        for k, v in obj.items():
            if isinstance(k, str) and _SECRET_KEY_RE.search(k) and k != "key_present":
                dropped.append(k)
                continue
            out[k] = _redact(v)
        if dropped:
            out["_redacted_keys"] = dropped
        return out
    if isinstance(obj, (list, tuple)):
        return [_redact(x) for x in obj]
    if isinstance(obj, str) and _SECRET_VALUE_RE.search(obj):
        return "<redactado: parece llave>"
    return obj


def _load_manifest():
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_auditor():
    """composite_auditor se importa PEREZOSO (sólo LG4/count-tokens): trae `openai` opcional y la tabla; jamás db."""
    from lib import composite_auditor as ca
    return ca


@contextlib.contextmanager
def _blocked_network(sink):
    """--dry-run: `urllib.request.urlopen` Y la costura `figures._urlopen` BLOQUEADAS y CONTADAS (ADR-0083 M.5)."""
    real_global, real_seam = urllib.request.urlopen, F._urlopen

    def blocked(req, *a, **kw):
        data = getattr(req, "data", None)
        try:
            body = json.loads(data.decode("utf-8")) if data else None
        except Exception:
            body = {"_raw_len": len(data or b"")}
        sink.append({"url": getattr(req, "full_url", str(req)), "body": body})
        raise urllib.error.URLError("dry-run: red BLOQUEADA (ADR-0083 M.5)")

    urllib.request.urlopen = blocked
    F._urlopen = blocked
    try:
        yield
    finally:
        urllib.request.urlopen = real_global
        F._urlopen = real_seam


@contextlib.contextmanager
def _placeholder_key(var):
    """Sólo en --dry-run: el caller exige la env antes de armar el cuerpo; placeholder que NO es llave, sólo en este
    proceso, restaurado tal cual (la máscara vacía de los gates vuelve a quedar vacía)."""
    prev = os.environ.get(var)
    os.environ[var] = prev or "dry-run-placeholder-not-a-credential"
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = prev


@contextlib.contextmanager
def _patched_attr(obj, name, value):
    had, prev = hasattr(obj, name), getattr(obj, name, None)
    setattr(obj, name, value)
    try:
        yield
    finally:
        if had:
            setattr(obj, name, prev)
        else:
            delattr(obj, name)


def _fake_get_bytes_from_zip(zip_path):
    """--dry-run: `figures._get_bytes(url, timeout, max_bytes, dest=None)` con la MISMA firma; escribe el zip fixture en
    `dest` y devuelve la forma del contrato (status ok, http 200, application/zip). El módulo hace el resto (extraer
    por basename == graphic_href, sha, mime por magic, dims por cabecera, ledger raw en la caché TMP)."""
    data = Path(zip_path).read_bytes()

    def fake(url, timeout, max_bytes, dest=None):
        out = {"status": "ok", "http_status": 200, "content_length": len(data), "content_type": "application/zip",
               "bytes": len(data), "elapsed_s": 0.0, "url": url, "throttle_slept_s": 0.0}
        if dest is not None:
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Path(dest).write_bytes(data)
            out["path"] = str(dest)
        else:
            out["data"] = data
        return out
    return fake


# ---------------------------------------------------------------------------------------------------------------
# XML: localizar (mcp_cache → fixtures → --xml) o bajar (--fetch-xml, 1 GET)
# ---------------------------------------------------------------------------------------------------------------
def locate_xml(pmcid, explicit=None, allow_repo_cache=True):
    """(ruta|None, fuente ∈ 'arg' | 'mcp_cache' | 'fixture' | None). El más reciente por nombre cuando hay varios."""
    if explicit:
        p = Path(explicit)
        return (p, "arg") if p.is_file() else (None, None)
    if allow_repo_cache:
        try:
            hits = sorted(fetch_paper.CACHE.glob(f"raw_paper_{pmcid}_*_fulltext.xml"))
        except OSError:
            hits = []
        if hits:
            return hits[-1], "mcp_cache"
    hits = sorted(FIXTURES.glob(f"epmc_fulltext_{pmcid}_*.xml"))
    if hits:
        return hits[-1], "fixture"
    return None, None


def build_items(pmcid, xml_text, cfg, fetched=None, evidence_id=None):
    """FigureItem por figura (figures.make_item): parse_jats + parse_license + license_flags + filas de fetch_figures.
    Devuelve (items, parsed, license_)."""
    parsed = F.parse_jats(xml_text, pmcid, caption_chars=cfg["caption_chars"], prose_license=cfg["prose_license"])
    license_ = F.parse_license(xml_text, None, prose_ok=cfg["prose_license"])
    by_href = (fetched or {}).get("by_href") or {}
    items = []
    for fig in parsed["figs"]:
        lic = fig.get("fig_license") or license_
        flags = F.license_flags(lic.get("id"), cfg)
        href = fig.get("graphic_href")
        row = by_href.get(os.path.basename(str(href)).lower()) if href else by_href.get(f"__nohref__{fig.get('fig_id')}")
        items.append(F.make_item(pmcid, evidence_id or f"live:{pmcid}", fig, lic, flags, bytes_row=row))
    return items, parsed, license_


# ---------------------------------------------------------------------------------------------------------------
# LG1 — bytes reales del zip de supplementaryFiles
# ---------------------------------------------------------------------------------------------------------------
def run_pmcid(pmcid, args, cfg, cache_root, dry_run):
    row = {"item": "pmcid", "kind": None, "pmcid": pmcid, "zip_url": F._zip_url(pmcid), "mechanism": F.MECHANISM,
           "module_version": F.MODULE_VERSION, "parser_version": F.PARSER_VERSION, "cache_root": str(cache_root),
           "class": {"ledger": CLASS_MEASUREMENT + " (HTTP/bytes observados)", "sha256": F.FIGURE_CLASS,
                     "dims_measured": "medicion (cabecera JPEG/PNG/GIF/WebP; dims_source 'header')",
                     "dims_declared": "declaracion de la fuente (PIs <?scaled-*?>/<?original-*?> del JATS)"}}
    t0 = time.monotonic()
    xml_path, xml_source = locate_xml(pmcid, args.xml, allow_repo_cache=not dry_run)
    xml_text = None
    if xml_path is not None:
        xml_text = xml_path.read_text(encoding="utf-8", errors="replace")
        row["xml"] = {"source": xml_source, "path": str(xml_path), "bytes": len(xml_text.encode("utf-8"))}
    elif args.fetch_xml and not dry_run:
        xml_text = fetch_paper._full_text_xml(pmcid)
        row["xml"] = {"source": "live: fetch_paper._full_text_xml (1 GET)", "path": None,
                      "bytes": len(xml_text.encode("utf-8")) if xml_text else None,
                      "state": "fetched" if xml_text else "not-available (fullTextXML None: no OA full text or network error)"}
    else:
        row["xml"] = {"source": None, "path": None, "state": "not-located (mcp_cache/fixtures; pass --xml or --fetch-xml)"}

    if not xml_text:
        # probe-only: sin figs no hay nada que extraer; se mide el HTTP del zip y se descarta (el zip no se conserva)
        tmp_zip = Path(cache_root) / f"_probe_{pmcid}.zip"
        res = F._get_bytes(F._zip_url(pmcid), min(F.SOCKET_TIMEOUT_MAX_S, args.timeout or 30),
                           int(float(cfg["zip_max_mb"]) * 1024 * 1024), dest=tmp_zip)
        n_entries = None
        if res.get("status") == "ok":
            try:
                import zipfile
                with zipfile.ZipFile(tmp_zip) as z:
                    n_entries = len(z.infolist())
            except Exception as e:
                res["zip_state"] = f"not-a-zip: {type(e).__name__}"
        try:
            tmp_zip.unlink()
        except OSError:
            pass
        row.update({"kind": "probe-only", "probe": {k: res.get(k) for k in ("status", "http_status", "content_type",
                                                                                 "content_length", "bytes", "elapsed_s",
                                                                                 "throttle_slept_s", "error_kind", "error",
                                                                                 "zip_state")},
                    "zip_entries_n": n_entries,
                    "note": "sin XML no se parsean figuras: sólo se sondeó el zip; un http-4xx aquí = PMCID sin OA declarado"})
        row["elapsed_total_s"] = round(time.monotonic() - t0, 3)
        return row, None

    parsed = F.parse_jats(xml_text, pmcid, caption_chars=cfg["caption_chars"], prose_license=cfg["prose_license"])
    figs = parsed["figs"][: int(cfg["max_per_paper"])]
    deadline = time.monotonic() + float(cfg["budget_s"])
    fetched = F.fetch_figures(pmcid, figs, cfg=cfg, cache_root=cache_root, deadline=deadline)
    items, _parsed2, license_ = build_items(pmcid, xml_text, cfg, fetched=fetched)
    led = fetched["ledger"]
    mb_per_s = None
    if led.get("zip_bytes") and led.get("elapsed_s"):
        mb_per_s = round(led["zip_bytes"] / (1024 * 1024) / max(led["elapsed_s"], 1e-6), 3)
    manifest = _load_manifest() or {}
    man_entries = {e["href"].lower(): e for e in ((manifest.get("zips") or {}).get(pmcid) or {}).get("entries", [])}
    fig_rows, n_sha_eq, n_dims_eq, n_cmp = [], 0, 0, 0
    for it in items:
        href = (it.get("graphic_href") or "")
        me = man_entries.get(os.path.basename(href).lower()) if href else None
        cmp_ = None
        if me is not None and it.get("bytes_state") == "verified":
            n_cmp += 1
            sha_eq = it.get("sha256") == me.get("sha256")
            dims_eq = it.get("dims_measured") == me.get("dims")
            n_sha_eq += int(sha_eq)
            n_dims_eq += int(dims_eq)
            cmp_ = {"sha_equal": sha_eq, "dims_equal": dims_eq, "manifest_real": me.get("real")}
        fig_rows.append({"id": it["id"], "label": it.get("label"), "href": href or None, "caption_state": it["caption_state"],
                         "bytes_state": it["bytes_state"], "sha256": it.get("sha256"), "bytes": it.get("bytes"),
                         "media_type": it.get("media_type"), "mime_from_extension": it.get("mime_from_extension"),
                         "dims_measured": it.get("dims_measured"), "dims_declared_scaled": (it.get("dims_declared") or {}).get("scaled"),
                         "dims_match": it.get("dims_match"), "embeddable": it["embeddable"], "panel_view": it["panel_view"],
                         "cache_hit": it.get("cache_hit"), "manifest_compare": cmp_})
    row.update({
        "kind": "dry-run" if dry_run else ("ok" if led.get("status") in ("success", "cache-hit") else "declared"),
        "n_figs_in_xml": parsed["n_fig"], "n_without_caption": parsed["n_without_caption"], "n_selected": len(figs),
        "license": {k: license_.get(k) for k in ("id", "source", "rule_no", "url", "version", "scope")},
        "license_flags": dict(zip(("embeddable", "panel_view", "fetch_bytes"), F.license_flags(license_.get("id"), cfg))),
        "ledger": led, "mb_per_s": mb_per_s,
        "counts": {"n_verified": sum(1 for r in fig_rows if r["bytes_state"] == "verified"),
                   "n_not_fetched": sum(1 for r in fig_rows if str(r["bytes_state"]).startswith("not-fetched (")),
                   "n_mismatch": sum(1 for r in fig_rows if r["bytes_state"] == "mismatch"),
                   "n_embeddable_verified": sum(1 for r in fig_rows if r["embeddable"] and r["bytes_state"] == "verified"),
                   "n_dims_match": sum(1 for r in fig_rows if r["dims_match"] is True)},
        "manifest_compare": ({"n_compared": n_cmp, "n_sha_equal": n_sha_eq, "n_dims_equal": n_dims_eq,
                              "source": "fixtures/figures/MANIFEST.json (sha/dims MEDIDOS 2026-09-08 del zip real)"}
                             if man_entries else "not-in-manifest"),
        "figures": fig_rows,
    })
    if not dry_run and led.get("status") not in ("success", "cache-hit"):
        row["declared"] = f"zip {led.get('status')}: {led.get('error_kind')} — filas 'not-fetched (…)' declaradas, la corrida sigue (§6)"
    row["elapsed_total_s"] = round(time.monotonic() - t0, 3)
    return row, items


# ---------------------------------------------------------------------------------------------------------------
# LG1 bis — href directo (NO verificado en el ADR; aquí se mide)
# ---------------------------------------------------------------------------------------------------------------
def run_href_direct(pmcid, items, args, cfg, cache_root, dry_run):
    target = None
    if args.href:
        target = next((it for it in (items or []) if os.path.basename(it.get("graphic_href") or "").lower() == args.href.lower()), None)
        href = args.href
    else:
        target = next((it for it in (items or []) if it.get("bytes_state") == "verified"), None) or \
                 next((it for it in (items or []) if it.get("graphic_href")), None)
        href = os.path.basename(target["graphic_href"]) if target else None
    row = {"item": "href-direct", "kind": None, "pmcid": pmcid, "href": href,
           "url": HREF_DIRECT_TEMPLATE.format(pmcid=pmcid, href=href) if href else None,
           "template": HREF_DIRECT_TEMPLATE,
           "template_state": "NOT verified by doc (ADR-0083 B.1: WITT_FIGURES_HREF_TEMPLATE does not exist in 0083; LG1 measures)",
           "zip_member_sha256": target.get("sha256") if target else None,
           "class": CLASS_MEASUREMENT + " (HTTP/bytes observados) cuando se llama; en dry-run sólo la URL construida"}
    if not href:
        row.update({"kind": "declared", "state": "not-comparable (no graphic_href among the parsed figures)"})
        return row
    if dry_run:
        row.update({"kind": "dry-run", "state": "url-built (no request in dry-run)"})
        return row
    tmp = Path(cache_root) / f"_href_direct_{pmcid}_{href}"
    res = F._get_bytes(row["url"], min(F.SOCKET_TIMEOUT_MAX_S, args.timeout or 30),
                       int(float(cfg["max_image_mb"]) * 1024 * 1024) or None, dest=tmp)
    row["http"] = {k: res.get(k) for k in ("status", "http_status", "content_type", "content_length", "bytes", "elapsed_s",
                                             "throttle_slept_s", "error_kind", "error")}
    if res.get("status") == "ok":
        data = tmp.read_bytes()
        sha = _sha(data)
        row.update({"sha256": sha, "media_type": F.sniff_mime(data), "dims_measured": F.image_dims(data)})
        if row["zip_member_sha256"]:
            eq = sha == row["zip_member_sha256"]
            row["sha_matches_zip_member"] = eq
            row["state"] = ("verified-equal: 200 and sha256 == zip member → candidate fallback for a 0083.1 (additive)" if eq
                            else "differs: 200 but sha256 != zip member → NOT a fallback (declared)")
        else:
            row["state"] = "not-comparable (zip member not verified in this run: fetch --pmcid first or pass --href)"
        row["kind"] = "ok"
    else:
        row.update({"kind": "declared", "sha_matches_zip_member": None,
                    "state": f"not-verified ({res.get('error_kind')}) — the ADR keeps 'no verificado'"})
    try:
        tmp.unlink()
    except OSError:
        pass
    return row


# ---------------------------------------------------------------------------------------------------------------
# LG4 — un juez real con imágenes por el transporte REAL
# ---------------------------------------------------------------------------------------------------------------
def default_claim(pmcid, items):
    """Fixture SINTÉTICO y declarado: una afirmación que sólo repite el caption de la 1ª figura con caption (nada se
    afirma que no esté en texto entregado — la doctrina §7 se respeta también en el instrumento)."""
    first = next((it for it in items if it["caption_state"] == "present"), None)
    caption = (first or {}).get("caption") or ""
    return {"question": f"What does the first figure of {pmcid} report (per its caption)?",
            "direct_answer": (f"According to the caption of {first['id']} ({first.get('label') or 'no label'}): "
                              f"{caption[:400]} [1]") if first else f"No captioned figure was delivered for {pmcid}.",
            "citation_id": first["id"] if first else None}


def _judge_system(ca, lens):
    charge = ca._LENS_CHARGES.get(lens) or ""
    rule = getattr(ca, "FIGURE_READING_RULE", None)
    parts = [f"You are the {lens} lens of an adversarial audit panel (composite-auditor, Mode 1 split-and-vote). "
             f"Output ONLY through the tool.", charge]
    if isinstance(rule, str) and rule:
        parts.append(rule)
    system = "\n\n".join(p for p in parts if p)
    return system, ("composite_auditor.FIGURE_READING_RULE appended (F3)" if rule
                    else "not-available (composite_auditor.FIGURE_READING_RULE not in tree — F3 pending): charge only")


def _user_text(pmcid, items, claim, deterministic_checks):
    evidence = {"path_b": {"papers": [{"source": "europepmc", "evidence_id": f"live:{pmcid}", "search_rec": {"pmcid": pmcid},
                                       "figures": F.project_for_prompt(items)}]}}
    return json.dumps({"claim": {"direct_answer": claim["direct_answer"], "confidence": 0.5,
                                 "evidence_cited": ([{"n": 1, "kind": "figure", "id": claim["citation_id"],
                                                      "note": "caption text only"}] if claim["citation_id"] else [])},
                       "evidence": evidence, "deterministic_checks": deterministic_checks}, ensure_ascii=False)


def _blocks_for(api_flag, figs, user_text, detail):
    if api_flag == "anthropic-messages":
        return F.anthropic_blocks(figs, user_text)
    if api_flag == "openai-responses":
        return F.openai_responses_parts(figs, user_text, detail)
    return F.openai_chat_parts(figs, user_text, detail)


def _blocks_summary(api_flag, blocks, figs):
    """Mide la forma: tipos en orden, imágenes ANTES del texto, N imágenes, y que cada b64 decodifica al byte original."""
    types_ = [b.get("type") for b in blocks]
    imgs = []
    for b in blocks:
        if b.get("type") == "image":
            imgs.append(b["source"]["data"])
        elif b.get("type") == "input_image":
            imgs.append(str(b["image_url"]).split(";base64,", 1)[1])
        elif b.get("type") == "image_url":
            imgs.append(str(b["image_url"]["url"]).split(";base64,", 1)[1])
    decoded_ok = all(_sha(base64.b64decode(b64)) == f["sha256"] for b64, f in zip(imgs, figs)) if imgs else None
    image_types = ("image", "input_image", "image_url")
    last_is_text = bool(types_) and types_[-1] in ("text", "input_text")
    # forma (G.3): el ÚLTIMO bloque es el user_text y ninguna imagen viene después de él
    return {"api": api_flag, "n_blocks": len(blocks), "types": types_, "n_images": len(imgs),
            "images_before_final_text": last_is_text and not any(t in image_types for t in types_[-1:]),
            "b64_decodes_to_original_sha": decoded_ok, "b64_chars_total": sum(len(x) for x in imgs),
            "form_state": (F.OPENAI_CHAT_FORM_STATE if api_flag == "openai-chat-completions"
                           else "verified in ADR-0083 Context 8 (provider docs, 2026-09-15)")}


def _projection(models_mod, model, figs):
    """PROYECCIÓN de tokens de visión SÓLO por `models.vision_tokens` (la única sede de la fórmula — ADR-0081 (A)/0083 (G.4));
    si F3 aún no la expone, se declara ausente: aquí NO se replica ninguna fórmula."""
    fn = getattr(models_mod, "vision_tokens", None)
    if not callable(fn):
        return {"visual_tokens_projected": None, "class": CLASS_PROJECTION,
                "state": "not-available (models.vision_tokens not in tree — F3 pending); formula NOT replicated here"}
    total, per, tier = 0, [], None
    for f in figs:
        d = f.get("dims_measured") or {}
        try:
            r = fn(model, d.get("w"), d.get("h"))
        except Exception as e:  # pragma: no cover
            r = None
            per.append({"id": f["id"], "error": _err(e)})
            continue
        if isinstance(r, dict):
            total += int(r.get("tokens") or 0)
            tier = r.get("tier", tier)
            per.append({"id": f["id"], "tokens": r.get("tokens"), "formula": r.get("formula")})
        else:
            per.append({"id": f["id"], "tokens": None, "state": "None (model without vision tier)"})
    return {"visual_tokens_projected": total, "tier": tier, "per_figure": per, "class": CLASS_PROJECTION,
            "source": "models.vision_tokens (ADR-0083 G.4)"}


def run_judge(pmcid, items, args, cfg, cache_root, dry_run, ca, model, api_flag, lens, count_tokens=False):
    fam, fam_source = models.family_of(model)
    row = {"item": "judge", "kind": None, "pmcid": pmcid, "model": model, "family": fam, "family_source": fam_source,
           "api": api_flag, "lens": lens, "detail": cfg["openai_detail"] if api_flag != "anthropic-messages" else None,
           "class": {"verdict": "juicio del juez (model-judgment)", "figure_readings": "model-judgment (never a measurement)",
                     "usage": CLASS_MEASUREMENT + " (API usage)", "latency_s": CLASS_MEASUREMENT}}
    sel = F.select_for_panel(items, cache_root, cfg=cfg)
    figs = sel["figures"]
    if args.image:
        wanted = [s.strip().lower() for s in args.image.split(",") if s.strip()]
        figs = [f for f in figs if any(f["sha256"].startswith(w) for w in wanted)]
        row["image_filter"] = {"requested": wanted, "matched": [f["sha256"][:F.SHA_SHORT] for f in figs]}
    if args.max_images is not None:
        figs = figs[: max(0, int(args.max_images))]
    row["selection"] = {k: sel[k] for k in ("n_eligible", "n_selected", "n_dropped_by_request_cap", "n_excluded", "rule")}
    row["figures_sent"] = [{"id": f["id"], "sha256": f["sha256"], "media_type": f["media_type"], "dims_measured": f["dims_measured"],
                            "license": f["license"]} for f in figs]
    row["n_images"] = len(figs)
    row["bytes_b64_total"] = sum(len(f["b64"]) for f in figs)
    row["projection"] = _projection(models, model, figs)

    claim = default_claim(pmcid, items)
    dchecks = {"pass": True, "note": "live smoke LG4 (ADR-0083): synthetic claim that only repeats a delivered caption",
               "figures": {"state": "checked", "n_figure_citations": 1 if claim["citation_id"] else 0}}
    user_text = _user_text(pmcid, items, claim, dchecks)
    system, system_source = _judge_system(ca, lens)
    row["system_source"] = system_source
    blocks = _blocks_for(api_flag, figs, user_text, cfg["openai_detail"])
    row["blocks"] = _blocks_summary(api_flag, blocks, figs)
    row["user_text_sha256"] = _sha(user_text.encode("utf-8"))
    row["user_text_has_b64"] = any(f["b64"][:64] in user_text for f in figs) if figs else False   # debe ser False (D.1)

    caller = {"anthropic-messages": ca._anthropic_tool_call, "openai-responses": ca._openai_responses_call,
              "openai-chat-completions": ca._openai_chat_call}[api_flag]
    row["caller"] = f"composite_auditor.{caller.__name__}"
    accepts = _accepts(caller, "user_content")
    row["caller_user_content"] = "accepted" if accepts else "not-in-signature (F3 pending: caller called WITHOUT images would be a different measurement — refused)"

    if dry_run:
        row["kind"] = "dry-run"
        if accepts:
            sink = []
            try:
                if api_flag == "anthropic-messages":
                    with _placeholder_key(KEY_ENV["anthropic"]), _blocked_network(sink):
                        try:
                            caller(model, system, user_text, tool=ca.VERDICT_TOOL, retries=0, return_meta=True, user_content=blocks)
                        except Exception as e:
                            row["dry_run_caller_exception"] = f"{_kind(e)}: {_err(e)}"
                    body = (sink[0] or {}).get("body") if sink else None
                    msgs = (body or {}).get("messages") or []
                    content = msgs[0].get("content") if msgs else None
                    row["captured"] = {"url": (sink[0] or {}).get("url") if sink else None,
                                       "content_equals_blocks": content == blocks, "n_content_blocks": len(content) if isinstance(content, list) else None,
                                       "tools_n": len((body or {}).get("tools") or []), "tool_choice": (body or {}).get("tool_choice")}
                else:
                    class _Create:
                        def __init__(self, path):
                            self._path = path

                        def create(self, **kw):
                            sink.append({"path": self._path, "kwargs": kw})
                            raise RuntimeError(f"dry-run: {self._path} BLOQUEADO (sin red)")
                    fake = types.SimpleNamespace(responses=_Create("responses.create"),
                                                 chat=types.SimpleNamespace(completions=_Create("chat.completions.create")),
                                                 max_retries=0)
                    with _blocked_network([]):
                        try:
                            kw = {"tool": ca.VERDICT_TOOL, "client": fake, "user_content": blocks}
                            if _accepts(caller, "retries"):
                                kw["retries"] = 0
                            caller(model, system, user_text, **kw)
                        except Exception as e:
                            row["dry_run_caller_exception"] = f"{_kind(e)}: {_err(e)}"
                    kw = (sink[0] or {}).get("kwargs") if sink else {}
                    if api_flag == "openai-responses":
                        inp = kw.get("input")
                        content = inp[0].get("content") if isinstance(inp, list) and inp else None
                    else:
                        msgs = kw.get("messages") or []
                        content = msgs[1].get("content") if len(msgs) > 1 else None
                    row["captured"] = {"path": (sink[0] or {}).get("path") if sink else None,
                                       "content_equals_blocks": content == blocks,
                                       "n_content_parts": len(content) if isinstance(content, list) else None,
                                       "tool_choice": kw.get("tool_choice"), "model": kw.get("model")}
            except Exception as e:  # pragma: no cover — el dry-run declara, no tumba
                row["captured"] = {"error": _err(e)}
        if count_tokens and api_flag == "anthropic-messages":
            row["count_tokens"] = {"state": "not-measured (dry-run: 2 bodies built, no call)", "bodies_built": 2,
                                   "url": COUNT_TOKENS_URL, "class": "medicion (count_tokens) when run live"}
        return row

    if not accepts:
        row["kind"] = "caller-without-user_content"
        row["error"] = "the real caller does not accept user_content yet (F3): nothing was called — no image was sent"
        return row

    t0 = time.monotonic()
    try:
        if api_flag == "anthropic-messages":
            res = caller(model, system, user_text, tool=ca.VERDICT_TOOL, timeout=args.timeout or 120, retries=0,
                         return_meta=True, user_content=blocks)
        else:
            kw = {"tool": ca.VERDICT_TOOL, "user_content": blocks}
            if args.timeout and _accepts(caller, "timeout"):
                kw["timeout"] = args.timeout
            if _accepts(caller, "retries"):
                kw["retries"] = 0
            res = caller(model, system, user_text, **kw)
        out, usage, meta = (res if len(res) == 3 else (res[0], res[1], {}))
        row.update({"kind": "ok", "latency_s": round(time.monotonic() - t0, 3), "usage": _numeric(usage), "meta": meta,
                    "verdict": out.get("verdict"), "verdict_in_vocabulary": out.get("verdict") in ca.VOCABULARY,
                    "caught": (out.get("caught") or "")[:400], "reasons": out.get("reasons"),
                    "figure_readings": out.get("figure_readings", "<absent: judge did not emit>"),
                    "figure_readings_class": "model-judgment", "tool_input_keys": sorted(out.keys())})
        if api_flag == "openai-chat-completions":
            row["form_measured"] = f"MEASURED {_today().strftime('%Y-%m-%d')}: chat.completions ACCEPTED image_url parts (was '{F.OPENAI_CHAT_FORM_STATE}')"
    except Exception as e:
        row.update({"kind": _kind(e), "error": _err(e), "latency_s": round(time.monotonic() - t0, 3),
                    "usage": _numeric(getattr(e, "usage", None)), "meta": getattr(e, "meta", None)})
        if api_flag == "openai-chat-completions" and str(_kind(e)).startswith("http-4"):
            row["form_measured"] = f"MEASURED {_today().strftime('%Y-%m-%d')}: chat.completions REJECTED the public form ({_kind(e)}) — ADR keeps 'not re-verified'"

    if count_tokens and api_flag == "anthropic-messages":
        row["count_tokens"] = run_count_tokens(ca, model, system, user_text, blocks, args.timeout or 60)
    return row


def run_count_tokens(ca, model, system, user_text, blocks, timeout):
    """2 llamadas a count_tokens (USD 0): mismo system/tools/tool_choice, `content` con y sin imágenes → Δ MEDICIÓN."""
    key = os.environ.get(KEY_ENV["anthropic"])
    if not key:
        return {"state": "no-api-key", "class": "not-measured"}
    headers = {"x-api-key": key, "anthropic-version": ca.ANTHROPIC_VERSION, "content-type": "application/json"}

    def _call(content):
        body = {"model": model, "system": system, "messages": [{"role": "user", "content": content}],
                "tools": [ca.VERDICT_TOOL], "tool_choice": {"type": "tool", "name": ca.VERDICT_TOOL["name"]}}
        req = urllib.request.Request(COUNT_TOKENS_URL, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        n = payload.get("input_tokens")
        if not isinstance(n, int):
            raise RuntimeError(f"count_tokens sin input_tokens numérico: {str(payload)[:200]}")
        return n

    out = {"url": COUNT_TOKENS_URL, "class": "medicion (count_tokens; USD 0)"}
    try:
        with_images = _call(blocks)
        without = _call(user_text)
        out.update({"with_images": with_images, "text_only": without, "delta_image_tokens": with_images - without,
                    "n_images": sum(1 for b in blocks if b.get("type") == "image"),
                    "rule": "delta = input_tokens(with image blocks) - input_tokens(same request, text only); sustituye la proyección"})
    except Exception as e:
        out.update({"state": "error", "error": _err(e)})
    return out


# ---------------------------------------------------------------------------------------------------------------
# impresión
# ---------------------------------------------------------------------------------------------------------------
def _print_row(r):
    it = r.get("item")
    if it == "pmcid":
        led = r.get("ledger") or {}
        if r["kind"] == "probe-only":
            p = r.get("probe") or {}
            print(f"  [pmcid] {r['pmcid']} · PROBE-ONLY · http {p.get('http_status')} · {p.get('content_type')} · "
                  f"{p.get('bytes')} B · entries {r.get('zip_entries_n')} · {p.get('elapsed_s')} s · {p.get('error_kind') or 'ok'}")
            return
        c = r.get("counts") or {}
        mc = r.get("manifest_compare")
        mc_s = (f"manifest sha {mc['n_sha_equal']}/{mc['n_compared']} dims {mc['n_dims_equal']}/{mc['n_compared']}"
                if isinstance(mc, dict) else str(mc))
        print(f"  [pmcid] {r['pmcid']} · {r['kind']} · xml {r['xml'].get('source')} · license {r['license']['id']} ({r['license']['source']}) · "
              f"zip {led.get('status')} http {led.get('http_status')} {led.get('zip_bytes')} B entries {led.get('zip_entries_n')} "
              f"{led.get('elapsed_s')} s ({r.get('mb_per_s')} MB/s) · figs {r['n_figs_in_xml']} sel {r['n_selected']} verified {c.get('n_verified')} "
              f"not-fetched {c.get('n_not_fetched')} mismatch {c.get('n_mismatch')} dims_match {c.get('n_dims_match')} · {mc_s}"
              + (f" · {led.get('error_kind')}" if led.get('error_kind') else ""))
        for f in r.get("figures", []):
            d = f.get("dims_measured") or {}
            print(f"      {f['id']} · {f['bytes_state']} · sha {str(f.get('sha256'))[:F.SHA_SHORT]} · {f.get('bytes')} B · {f.get('media_type')} · "
                  f"{d.get('w')}x{d.get('h')} match={f.get('dims_match')} · embed={f['embeddable']} panel={f['panel_view']}")
    elif it == "href-direct":
        h = r.get("http") or {}
        print(f"  [href-direct] {r.get('url')} · {r['kind']} · http {h.get('http_status')} {h.get('bytes')} B · sha {str(r.get('sha256'))[:F.SHA_SHORT]} "
              f"vs zip {str(r.get('zip_member_sha256'))[:F.SHA_SHORT]} · {r.get('state')}")
    elif it == "judge":
        b = r.get("blocks") or {}
        print(f"  [judge] {r['model']} · {r['api']} · {r['lens']} · {r['kind']} · images {r.get('n_images')} ({r.get('bytes_b64_total')} b64 chars) · "
              f"blocks {b.get('types')} · b64→sha ok={b.get('b64_decodes_to_original_sha')} · user_content {r.get('caller_user_content')}"
              + (f" · verdict {r.get('verdict')} in_vocab={r.get('verdict_in_vocabulary')} · usage {r.get('usage')} · {r.get('latency_s')} s" if r["kind"] == "ok" else "")
              + (f" · {r.get('error')}" if r.get("error") else ""))
        if r.get("captured"):
            print(f"      captured: {r['captured']}")
        if r.get("count_tokens"):
            print(f"      count_tokens: {r['count_tokens']}")
        if r.get("figure_readings") not in (None, "<absent: judge did not emit>"):
            print(f"      figure_readings (JUICIO, jamás medición): {json.dumps(r['figure_readings'], ensure_ascii=False)[:600]}")


# ---------------------------------------------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pmcid", default=None, help="LG1: PMCID cuyo zip de supplementaryFiles se baja (1 GET a www.ebi.ac.uk)")
    ap.add_argument("--xml", default=None, help="ruta explícita al *_fulltext.xml (si no: mcp_cache → fixtures)")
    ap.add_argument("--fetch-xml", action="store_true", help="si no hay XML local, bajarlo por fetch_paper._full_text_xml (1 GET más)")
    ap.add_argument("--href-direct", action="store_true", help="LG1 bis: GET europepmc.org/articles/{PMCID}/bin/{href} y compara sha con el miembro del zip")
    ap.add_argument("--href", default=None, help="basename del href para --href-direct (default: la 1ª figura verificada)")
    ap.add_argument("--judge", default=None, help="LG4: id de modelo de la tabla (o prefijo conocido) para UNA llamada de juez con imágenes")
    ap.add_argument("--api", choices=sorted(API_FLAGS), default=None, help="transporte del juez; default: el de la tabla (models.api_of)")
    ap.add_argument("--lens", choices=models.LENSES, default="evidence-grounding", help="lente del juez (default evidence-grounding)")
    ap.add_argument("--image", default=None, help="CSV de sha256 (o prefijos ≥ 12) de las figuras a enviar; default: la selección determinista completa")
    ap.add_argument("--max-images", type=int, default=None, help="tope adicional de imágenes enviadas (≤ WITT_FIGURES_MAX_PER_LENS)")
    ap.add_argument("--count-tokens", action="store_true", help="Anthropic: 2 count_tokens (con/sin imágenes) → Δ MEDIDO (USD 0)")
    ap.add_argument("--timeout", type=int, default=None, help="timeout por llamada (s)")
    ap.add_argument("--cache-dir", default=None, help="raíz de la caché de figuras (default: TMP nuevo; pásala igual entre invocaciones para reutilizar bytes)")
    ap.add_argument("--dry-run", action="store_true", help="construye todo SIN red ni llave (fixtures + _get_bytes falseado); lo que corre F8")
    ap.add_argument("--out", default=None, help="ruta del JSON de salida (default: analysis/outputs/live_figures_<fecha>.json; --dry-run no escribe salvo --out)")
    ap.add_argument("--verbose", action="store_true", help="imprime las filas completas (sin b64: cinturón anti-binario)")
    args = ap.parse_args(argv)

    manifest = _load_manifest()
    dry = args.dry_run
    if dry and not args.pmcid:
        # el PMCID con zip REAL de los fixtures (CC BY): lo que el ADR fija para el gate estático
        zips = (manifest or {}).get("zips") or {}
        args.pmcid = next((p for p, z in zips.items() if z.get("real")), None) or "PMC11379296"
    if not args.pmcid and not args.judge and not args.href_direct:
        print(json.dumps({"kind": "bad-args", "error": "nada que correr: --pmcid (LG1) y/o --judge (LG4) y/o --dry-run"}, ensure_ascii=False))
        return EXIT_REFUSED
    if (args.judge or args.href_direct or args.count_tokens) and not args.pmcid:
        print(json.dumps({"kind": "bad-args", "error": "--judge/--href-direct/--count-tokens necesitan --pmcid (el XML da fig_id, caption y licencia)"}, ensure_ascii=False))
        return EXIT_REFUSED

    cfg = F.env_config()
    cache_root = Path(args.cache_dir) if args.cache_dir else Path(tempfile.mkdtemp(prefix="live_figures_"))
    cache_root.mkdir(parents=True, exist_ok=True)
    dir_state = F.cache_dir_state(cache_root)

    # plan de gasto (declarado ANTES de tocar red)
    judges = []
    if args.judge:
        fam, _ = models.family_of(args.judge)
        if fam not in KEY_ENV:
            print(json.dumps({"kind": "unknown-family", "error": f"--judge {args.judge!r}: la tabla no lo conoce y el prefijo no casa (ADR-0081 A)"}, ensure_ascii=False))
            return EXIT_REFUSED
        if args.api:
            api_flag = API_FLAGS[args.api]
            if (fam == "anthropic") != (api_flag == "anthropic-messages"):
                print(json.dumps({"kind": "bad-args", "error": f"--api {args.api} no corresponde a la familia {fam} de {args.judge}"}, ensure_ascii=False))
                return EXIT_REFUSED
        else:
            api_flag, _ = models.api_of(args.judge)
        judges.append((args.judge, api_flag, args.lens))
    elif dry:
        # los TRES transportes con los asientos del panel de la tabla (sin red): grounding (anthropic) + reproducibility (openai)
        panel = models.panel(env={}, today=models.MODEL_TABLE_AS_OF)
        by_lens = {m["lens"]: m for m in panel}
        g, r = by_lens.get("evidence-grounding"), by_lens.get("reproducibility")
        if g:
            judges.append((g["reviewer"], "anthropic-messages", "evidence-grounding"))
        if r:
            judges.append((r["reviewer"], "openai-responses", "reproducibility"))
            judges.append((r["reviewer"], "openai-chat-completions", "reproducibility"))
    need_fams = sorted({models.family_of(m)[0] for m, _a, _l in judges})
    key_present = {fam: bool(os.environ.get(KEY_ENV[fam])) for fam in need_fams}
    if not dry:
        absent = [KEY_ENV[f] for f, ok in key_present.items() if not ok]
        if absent:
            print(json.dumps({"kind": "no-api-key", "error": "sin llave en el entorno del proceso para la familia del juez; nada se llamó",
                              "missing_env": absent, "hint": "exporta la llave en ESTA shell (jamás en git ni en archivos del repo)"},
                             ensure_ascii=False, indent=2))
            return EXIT_REFUSED
        spend = []
        if args.pmcid:
            spend.append(f"1 GET a www.ebi.ac.uk (zip ≤ {cfg['zip_max_mb']} MB, 0 modelo)" + (" + 1 GET fullTextXML si falta el XML" if args.fetch_xml else ""))
        if args.href_direct:
            spend.append("1 GET a europepmc.org (href directo, 0 modelo)")
        for m, a, _l in judges:
            spend.append(f"1 llamada de juez {m} por {a}")
        if args.count_tokens:
            spend.append("2 count_tokens (USD 0)")
        print("ESTA CORRIDA GASTA: " + " · ".join(spend) + f". Caché de figuras: {cache_root} ({dir_state}). Sin BD, sin git.")

    header = {"invoked_at": _today().strftime("%Y-%m-%dT%H:%M:%SZ"), "argv": sys.argv[1:], "dry_run": dry, "adr": "ADR-0083",
              "module_version": F.MODULE_VERSION, "parser_version": F.PARSER_VERSION, "license_table_version": F.LICENSE_TABLE_VERSION,
              "table_version": models.MODELS_TABLE_VERSION, "cache_root": str(cache_root), "cache_dir_state": dir_state,
              "cfg_sources": cfg["sources"], "caps": cfg["caps"], "env_ignored": cfg["env_ignored"], "key_present": key_present,
              "manifest": {"path": str(MANIFEST_PATH.relative_to(ROOT)).replace("\\", "/"), "contract": (manifest or {}).get("contract"),
                           "present": manifest is not None}}
    print(f"ADR-0083 · figures {F.MODULE_VERSION}/{F.PARSER_VERSION}/{F.LICENSE_TABLE_VERSION} · tabla {models.MODELS_TABLE_VERSION} · "
          f"caché {cache_root} ({dir_state})" + (" · DRY-RUN (sin red, sin llave)" if dry else ""))

    rows, net_sink = [], []
    ca = _load_auditor() if (judges or args.count_tokens) else None

    def _body():
        items = None
        if args.pmcid:
            r, items = run_pmcid(args.pmcid, args, cfg, cache_root, dry)
            rows.append(r)
            _print_row(r)
        if args.href_direct:
            r = run_href_direct(args.pmcid, items, args, cfg, cache_root, dry)
            rows.append(r)
            _print_row(r)
        for m, a, lens in judges:
            r = run_judge(args.pmcid, items or [], args, cfg, cache_root, dry, ca, m, a, lens,
                          count_tokens=args.count_tokens and a == "anthropic-messages")
            rows.append(r)
            _print_row(r)

    if dry:
        zips = (manifest or {}).get("zips") or {}
        zfile = (zips.get(args.pmcid) or {}).get("file")
        zpath = FIXTURES / zfile if zfile else None
        fake = _fake_get_bytes_from_zip(zpath) if (zpath and zpath.is_file()) else None
        with _blocked_network(net_sink):
            if fake is not None:
                with _patched_attr(F, "_get_bytes", fake):
                    _body()
            else:
                _body()   # sin zip fixture: fetch_figures caerá en 'network' (bloqueada) → filas declaradas
        header["dry_run_zip_fixture"] = str(zpath.relative_to(ROOT)).replace("\\", "/") if (zpath and zpath.is_file()) else None
    else:
        _body()

    db_imported = any(m in sys.modules for m in FORBIDDEN_MODULES)
    static = {"urlopen_calls_real": len(net_sink) if dry else "not-counted (live)", "db_imported": db_imported,
              "forbidden_modules_checked": FORBIDDEN_MODULES,
              "zip_url_rule": "figures._zip_url(pmcid) == f'{EPMC}/{pmcid}/supplementaryFiles'",
              "zip_url_ok": all(r.get("zip_url") == f"{F.EPMC}/{r['pmcid']}/supplementaryFiles" for r in rows if r.get("item") == "pmcid"),
              "no_b64_in_user_text": all(r.get("user_text_has_b64") is False for r in rows if r.get("item") == "judge") or
                                     not any(r.get("item") == "judge" for r in rows)}
    bad_kinds = {"error", "unclassified", "network", "no-api-key", "unknown-family"}
    n_failed = sum(1 for r in rows if (r["kind"] in bad_kinds or str(r["kind"]).startswith("http-") or str(r["kind"]).startswith("error:")))
    dry_ok = (not dry) or (len(net_sink) == 0 and all(r["kind"] == "dry-run" for r in rows)
                           and all((r.get("blocks") or {}).get("b64_decodes_to_original_sha") in (True, None) for r in rows if r.get("item") == "judge"))
    exit_code = EXIT_OK if (n_failed == 0 and not db_imported and dry_ok and static["zip_url_ok"] and static["no_b64_in_user_text"]) else EXIT_FAILED
    summary = {"n": len(rows), "n_failed": n_failed, "kinds": [r["kind"] for r in rows], "static": static, "exit_code": exit_code}
    run = _redact(_strip_binary({**header, "rows": rows, "summary": summary}))

    if args.verbose:
        print(json.dumps(run, ensure_ascii=False, indent=2, default=str))
    out_path = Path(args.out) if args.out else (OUT_DIR / f"live_figures_{_today().strftime('%Y%m%d')}.json")
    if args.out or not dry:
        doc = {"script": "analysis/scripts/smoke_live_figures.py", "adr": "ADR-0083", "runs": []}
        if out_path.exists():
            try:
                doc = json.loads(out_path.read_text(encoding="utf-8"))
                doc.setdefault("runs", [])
            except Exception:
                doc = {"script": "analysis/scripts/smoke_live_figures.py", "adr": "ADR-0083", "runs": [], "_previous_unreadable": True}
        doc["runs"].append(run)
        text = json.dumps(doc, ensure_ascii=False, indent=2, default=str)
        assert not _SECRET_VALUE_RE.search(text), "cinturón: el JSON de salida contiene algo que parece llave — no se escribe"
        assert "data:image" not in text and ";base64," not in text, "cinturón anti-binario: una data:URL iba a salir — no se escribe"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        rel = out_path.relative_to(ROOT).as_posix() if out_path.is_relative_to(ROOT) else str(out_path)
        print(f"escrito: {rel} ({len(doc['runs'])} invocación(es); sin secretos ni b64: cinturones aplicados)")
    else:
        print("dry-run: nada escrito (usa --out para guardar las filas)")
    print(f"resumen: n={summary['n']} failed={n_failed} kinds={summary['kinds']} urlopen_real={static['urlopen_calls_real']} "
          f"db_imported={db_imported} zip_url_ok={static['zip_url_ok']} exit={exit_code}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

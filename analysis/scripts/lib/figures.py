"""
figures.py — figuras de papers como evidencia OBSERVADA (ADR-0083, contrato 1.12, rebanada F1).

Una figura es MEDICIÓN sólo cuando el código verifica tres cosas: su identidad (el `@id` del `<fig>` en el
XML JATS cacheado por fetch_paper, ADR-0078), sus bytes (sha256 calculado al gatear, al servir y al embeber;
ADR-0077) y su licencia (tabla CERRADA de reglas ordenadas sobre `<permissions>`; `unknown` NO se embebe).
Lo que la imagen DICE es JUICIO de dos lentes del panel (composite_auditor, F3) y jamás una medición; el
sintetizador recibe caption + metadatos y NUNCA bytes (runs, F4). Los bytes viven FUERA del registro congelado
(ADR-0074): en `mcp_cache/figures/<PMCID>/<href>` como raw cacheado con procedencia (ADR-0062) y se sirven por
`GET /runs/{id}/figures/{sha256}` (app, F5).

Qué hay aquí (ADR-0083 (A), (B), (G.2)-(G.3), (L)):
  parse_jats(xml_text, pmcid)             (A.1) figuras del JATS: id / label / caption / graphic / dims declaradas
  parse_license(xml_text, search_license) (A.2) licencia por REGLAS ORDENADAS, dos fuentes (XML > search), conflict
  LICENSE_TABLE / license_table(cfg)      (A.3) tabla cerrada embed / panel_view / fetch_bytes / words_es
  fetch_figures(pmcid, figs, ...)         (B)   UN zip por paper (supplementaryFiles), sha256 del ORIGINAL, caché
                                                acotada (TTL + LRU), presupuesto propio, filas declaradas (§6)
  attach(bundle, ...)                     (C)   figuras adheridas a los papers de la Ruta B + resumen → frozen.figures
  select_for_panel(items, cache_root)     (G.2) selección determinista de lo que ven las lentes (sha recalculado)
  anthropic_blocks / openai_responses_parts / openai_chat_parts   (G.3) bloques de imagen por transporte
  env_config()                            (M.4) las 20 env con default declarado, lector tolerante
  locate_xml / cache_dir / verify_cached / evict_lru / image_dims / servable_state / project_for_prompt

stdlib puro (re, json, hashlib, zipfile, io, struct, urllib, time, os, pathlib, html) — Pillow SOLO en record_pdf.
La ÚNICA costura de red es `_get_bytes` (host www.ebi.ac.uk, con net_throttle). Nada aquí toca la DATA
INAMOVIBLE ni el mcp_cache de papers: la caché de figuras es un subdirectorio propio (`figures/`).
"""
import base64
import hashlib
import html
import inspect
import io
import json
import os
import re
import struct
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2].parent
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
from lib import raw_store  # noqa: E402
from lib import net_throttle as _net_throttle  # noqa: E402
from lib import fetch_paper as _fetch_paper  # noqa: E402  (ROOT/EPMC/UA/throttle: la MISMA política que los papers)

# ---------------------------------------------------------------------------------------------------------
# Versiones y literales (ADR-0083 (A), (L))
# ---------------------------------------------------------------------------------------------------------
MODULE_VERSION = "fig-1"
PARSER_VERSION = "jats-fig-1"
LICENSE_TABLE_VERSION = "lt-1"
MECHANISM = "supplementaryFiles-zip"
EPMC = _fetch_paper.EPMC                    # https://www.ebi.ac.uk/europepmc/webservices/rest
EPMC_HOST = _fetch_paper.EPMC_HOST          # www.ebi.ac.uk (mismo pacing que fetch_paper._throttle)
FIGURE_CLASS = "measurement (source-pointer: bytes observed from source; sha256 recomputed on read)"
ZFIN_FIGURES_STATE = "not-available (zfin_zebrafish payload carries no ZDB-FIG ids at 9d90c01)"
SELECTION_RULE = "cited-by-answer first, then paper selection_rank, then document order"
FIGURE_SOURCES = ("europepmc", "pubmed")    # papers de la Ruta B que pueden ganar figuras (C); zfin jamás

# Constantes declaradas (viajan en `caps` con source 'constant (ADR-0083)')
PER_PAPER_BUDGET_S = 45.0       # por paper: min(45, restante)
SOCKET_TIMEOUT_MAX_S = 30.0     # socket timeout: min(30, restante)
MIN_REMAINING_S = 5.0           # restante < 5 s → papers pendientes 'not-fetched (budget-exhausted)' sin red
REQUEST_B64_MB = 8              # b64 acumulado por petición de juez
MAX_MEGAPIXELS = 40             # guardia w×h ≤ 40 MP (bomba → decode-error)
CHUNK_BYTES = 1 << 20           # streaming por chunks de 1 MB
SHA_SHORT = 12
LICENSE_EVIDENCE_CHARS = 200
CONSTANT_SOURCE = "constant (ADR-0083)"

# ---------------------------------------------------------------------------------------------------------
# Vocabularios CERRADOS (exportados para el gate de paridad; viajan en frozen.figures.vocabulary) — (L)
# ---------------------------------------------------------------------------------------------------------
LICENSES = ("cc-by", "cc0", "cc-by-sa", "cc-by-nc", "cc-by-nd", "cc-by-nc-sa", "cc-by-nc-nd",
            "cc-by-prose-unconfirmed", "zfin-display-only", "unknown")
LICENSE_SOURCES = ("ali-license-ref", "ext-link", "license-p-url", "license-p-token", "license-p-prose",
                   "epmc-search", "none")
LICENSE_SCOPES = ("article-level", "figure-level")
# Reglas ORDENADAS (A.2): (rule_no, source, descripción). El orden ES la regla: compuestos antes que 'CC BY'.
LICENSE_RULES = (
    (1, "ali-license-ref", "<ali:license_ref> URL → variante por path (/by/, /by-sa/, /by-nc/, /by-nd/, /by-nc-sa/, "
                           "/by-nc-nd/, /publicdomain/zero/ → cc0); sin URL, el atributo content-type='ccby…'"),
    (2, "ext-link", "URL creativecommons.org en xlink:href de <ext-link> (o del propio <license>) dentro de <license>"),
    (3, "license-p-url", "URL creativecommons.org en el TEXTO de <license-p>"),
    (4, "license-p-token", "token en prosa: CC BY-NC-ND | CC BY-NC-SA | CC BY-NC | CC BY-ND | CC BY-SA | CC BY | CC0 "
                           "(compuestos ANTES que CC BY)"),
    (5, "license-p-prose", "prosa 'Creative Commons Attribution' SIN Non[- ]?Commercial | No[- ]?Deriv | Share[- ]?Alike → "
                           "cc-by si WITT_FIGURES_PROSE_LICENSE=1, si no cc-by-prose-unconfirmed (E3)"),
    (6, "epmc-search", "`license` del search de EPMC normalizado ('cc by' → cc-by) SOLO cuando el XML no dio (1)-(5)"),
    (7, "none", "resto → unknown (license-type='OpenAccess' solo NO es licencia)"),
)
# Tabla CERRADA (A.3): embed = bytes al PDF / GET 200 / miniatura; panel_view = bytes a las lentes (E2, default
# delegado: NC/ND SÍ); fetch_bytes = se bajan y verifican por sha (unknown SÍ: lo que no viaja son sus bytes a
# terceros); words_es = la licencia EN PALABRAS para Hoja y PDF.
LICENSE_TABLE = {
    "cc-by":        {"embed": True,  "panel_view": True,  "fetch_bytes": True,  "words_es": "CC BY (Atribución) — embebible"},
    "cc0":          {"embed": True,  "panel_view": True,  "fetch_bytes": True,  "words_es": "CC0 (dominio público) — embebible"},
    "cc-by-sa":     {"embed": True,  "panel_view": True,  "fetch_bytes": True,  "words_es": "CC BY-SA (Atribución-CompartirIgual) — embebible"},
    "cc-by-nc":     {"embed": False, "panel_view": True,  "fetch_bytes": True,  "words_es": "CC BY-NC (No Comercial) — NO embebible: caption + enlace"},
    "cc-by-nd":     {"embed": False, "panel_view": True,  "fetch_bytes": True,  "words_es": "CC BY-ND (Sin Derivadas) — NO embebible: caption + enlace"},
    "cc-by-nc-sa":  {"embed": False, "panel_view": True,  "fetch_bytes": True,  "words_es": "CC BY-NC-SA — NO embebible: caption + enlace"},
    "cc-by-nc-nd":  {"embed": False, "panel_view": True,  "fetch_bytes": True,  "words_es": "CC BY-NC-ND — NO embebible: caption + enlace"},
    "cc-by-prose-unconfirmed": {"embed": False, "panel_view": True, "fetch_bytes": True,
                                "words_es": "CC BY en prosa sin URL, no confirmada — NO embebible (panel sí)"},
    "zfin-display-only": {"embed": False, "panel_view": False, "fetch_bytes": False,
                          "words_es": "ZFIN: sólo enlace ZDB-FIG, jamás bytes ('permission only to display')"},
    "unknown":      {"embed": False, "panel_view": False, "fetch_bytes": True,
                     "words_es": "licencia desconocida — NO embebible; sus bytes no viajan a terceros"},
}
LICENSE_TABLE_RULE = ("la licencia del ARTÍCULO puede no cubrir una figura reutilizada de terceros ('unless indicated "
                      "otherwise in a credit line', PMC8613261); el código sólo lee <permissions> (artículo o figura) — "
                      "lo demás es límite declarado, no detección")
assert tuple(LICENSE_TABLE) == LICENSES, "LICENSE_TABLE y LICENSES deben ser el MISMO vocabulario cerrado (A.3)"

# (B.2) estados de bytes: exactos + prefijos con razones cerradas. `cache-read-only` (B.3) y `no-graphic` (una <fig>
# sin <graphic>: no hay href que bajar) se DECLARAN aquí como razones adicionales a la lista de (B.2) del borrador.
BYTES_STATES_EXACT = ("verified", "mismatch", "not-requested (kill-switch)", "never (zfin-display-only)")
BYTES_STATES_PREFIXES = ("not-fetched (", "error: ")
NOT_FETCHED_REASONS = ("href-not-in-zip", "href-not-in-zip; thumb-available", "http-<code>", "not-a-zip", "bad-zip",
                       "zip-over-max", "timeout", "network", "budget-exhausted", "paper-cap", "run-cap", "size-cap",
                       "decode-error", "unsupported-mime", "no-caption", "cache-read-only", "no-graphic")
# (L) frozen.figures.state y bundle.path_b.papers[].figures.state
FIGURES_STATES_EXACT = ("attached", "no-path-b", "no-papers-with-xml", "kill-switch WITT_FIGURES=0")
FIGURES_STATES_PREFIXES = ("error: ",)
PAPER_FIGURES_STATES = ("attached", "no-fulltext-xml", "not-selected (paper-cap)")
# (I) medido al pedir GET /runs/{id}/figures
SERVABLE_STATES = ("yes", "forbidden-by-license", "bytes-not-in-cache", "bytes-mismatch", "kill-switch", "no-bytes")
CAPTION_STATES = ("present", "absent")
MEDIA_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp")
CACHE_DIR_STATES = ("writable", "read-only", "missing")
CACHE_DIR_SOURCES = ("env", "default", "injected")   # 'injected' = ruta pasada por el llamador (smokes), declarada
DIMS_SOURCES = ("header",)
FETCH_LEDGER_STATUSES = ("success", "cache-hit", "error", "skipped-budget", "not-requested")
OPENAI_DETAILS = ("low", "high", "auto", "original")
# Forma EXACTA del FigureItem (L) — el orden de llaves es el contrato para F2–F7 y la webapp.
# `caption_in_excerpt` viene de Consequences ("se MIDE por figura"), `mime_from_extension` va SIEMPRE (string|null).
FIGURE_ITEM_KEYS = ("id", "pmcid", "evidence_id", "fig_id", "label", "caption", "caption_truncated", "caption_state",
                    "caption_lang", "graphic_href", "source_url", "media_type", "mime_from_extension", "bytes", "sha256",
                    "sha256_short", "dims_declared", "dims_measured", "dims_source", "dims_match", "license", "embeddable",
                    "panel_view", "bytes_state", "raw_ref", "cache_path_rel", "fetched_at", "cache_hit", "cited_by_answer",
                    "seen_by_lenses", "delivered_to_synthesizer", "caption_in_excerpt", "class")
# (D.1) lo ÚNICO que ve el sintetizador por figura; `license` proyectada como {id, source}.
PROMPT_FIGURE_KEYS = ("id", "fig_id", "label", "caption", "caption_truncated", "caption_state", "license", "embeddable",
                      "sha256_short", "dims_measured", "bytes_state")
FORBIDDEN_PROMPT_KEYS = ("cache_path", "cache_path_rel", "raw_ref", "b64", "data", "bytes_b64")
assert not set(PROMPT_FIGURE_KEYS) & set(FORBIDDEN_PROMPT_KEYS)
# (G.2) lo que viaja al `member` de una lente con visión
PANEL_FIGURE_KEYS = ("id", "fig_id", "label", "caption", "license", "sha256", "media_type", "b64", "dims_measured")

VOCABULARY = {
    "LICENSES": LICENSES, "LICENSE_SOURCES": LICENSE_SOURCES, "LICENSE_SCOPES": LICENSE_SCOPES,
    "BYTES_STATES_EXACT": BYTES_STATES_EXACT, "BYTES_STATES_PREFIXES": BYTES_STATES_PREFIXES,
    "NOT_FETCHED_REASONS": NOT_FETCHED_REASONS, "FIGURES_STATES_EXACT": FIGURES_STATES_EXACT,
    "FIGURES_STATES_PREFIXES": FIGURES_STATES_PREFIXES, "PAPER_FIGURES_STATES": PAPER_FIGURES_STATES,
    "SERVABLE_STATES": SERVABLE_STATES, "CAPTION_STATES": CAPTION_STATES, "MEDIA_TYPES": MEDIA_TYPES,
    "CACHE_DIR_STATES": CACHE_DIR_STATES, "CACHE_DIR_SOURCES": CACHE_DIR_SOURCES, "DIMS_SOURCES": DIMS_SOURCES,
    "FETCH_LEDGER_STATUSES": FETCH_LEDGER_STATUSES, "OPENAI_DETAILS": OPENAI_DETAILS,
}


def bytes_state_in_vocabulary(s):
    """True si `s` es un estado de bytes válido (exacto o prefijo con razón cerrada) — patrón plan_state_in_vocabulary."""
    if s in BYTES_STATES_EXACT:
        return True
    if isinstance(s, str) and s.startswith("not-fetched (") and s.endswith(")"):
        reason = s[len("not-fetched ("):-1]
        return reason in NOT_FETCHED_REASONS or re.fullmatch(r"http-\d{3}", reason) is not None
    return isinstance(s, str) and s.startswith("error: ")


def figures_state_in_vocabulary(s):
    return s in FIGURES_STATES_EXACT or (isinstance(s, str) and s.startswith(FIGURES_STATES_PREFIXES))


# ---------------------------------------------------------------------------------------------------------
# Env (M.4): 20 variables con default declarado; lector TOLERANTE en tiempo de llamada (vacía/basura → default con
# source). Los clamps son invariantes de configuración del proveedor (M.8): fuera de rango → default declarado.
# ---------------------------------------------------------------------------------------------------------
_DEFAULT_EMBED = "cc-by,cc0,cc-by-sa"
_DEFAULT_PANEL = "cc-by,cc0,cc-by-sa,cc-by-nc,cc-by-nd,cc-by-nc-sa,cc-by-nc-nd,cc-by-prose-unconfirmed"
_DEFAULT_LENSES = "evidence-grounding,reproducibility"
# (name, VAR, default, kind, clamp|choices, reader, effect) — kind ∈ bool | int | float | csv | licenses | choice | path
ENV_SPECS = (
    ("figures",         "WITT_FIGURES",              "1",  "bool", None, "runs._figures_stage · audit() · app",
     "kill-switch maestro; 0 = frozen 1.11 byte a byte salvo 3 excepciones (M.1)"),
    ("vision",          "WITT_FIGURES_VISION",       "1",  "bool", None, "audit()",
     "0 = ninguna lente recibe imágenes; captions/sha/licencia siguen (M.2)"),
    ("vision_lenses",   "WITT_FIGURES_VISION_LENSES", _DEFAULT_LENSES, "csv", None, "composite_auditor.vision_lenses",
     "CSV de <= 2 lentes validado contra models.LENSES (F3: composite_auditor.VISION_LENSES_MAX; corrector); aquí sólo se tokeniza"),
    ("max_papers",      "WITT_FIGURES_MAX_PAPERS",   "3",  "int", (1, 50), "runs._figures_stage · figures.attach",
     "papers con PMCID + XML de los que se parsean/bajan figuras; resto not-fetched (paper-cap)"),
    ("max_per_paper",   "WITT_FIGURES_MAX_PER_PAPER", "9", "int", (1, 30), "figures.attach",
     "figuras por paper en orden de documento (clamp 1..30)"),
    ("max_per_run",     "WITT_FIGURES_MAX_PER_RUN",  "12", "int", (1, 200), "figures.attach",
     "tope de figuras bajadas por corrida; resto not-fetched (run-cap)"),
    ("max_per_lens",    "WITT_FIGURES_MAX_PER_LENS", "12", "int", (0, 20), "figures.select_for_panel",
     "imágenes por petición de juez (clamp 0..20: ≤ 20 evita «many-image requests»)"),
    ("max_image_mb",    "WITT_FIGURES_MAX_IMAGE_MB", "5",  "float", (0.0, 7.0), "figures.select_for_panel · PDF",
     "bytes crudos por imagen para panel/miniatura (clamp ≤ 7: 9.3 MB b64 < 10 MB API)"),
    ("zip_max_mb",      "WITT_FIGURES_ZIP_MAX_MB",   "40", "float", (0.0, 1024.0), "figures.fetch_figures",
     "precheck Content-Length y tope de streaming → not-fetched (zip-over-max) sin escribir"),
    ("budget_s",        "WITT_FIGURES_BUDGET_S",     "90", "float", (0.0, 3600.0), "figures.attach",
     "reloj TOTAL de la etapa, fuera de la ronda de búsqueda; por paper min(45, restante)"),
    ("ttl_days",        "WITT_FIGURES_TTL_DAYS",     "30", "float", None, "figures.fetch_figures",
     "frescura del ledger por PMCID; fresco + sha iguales → cache_hit, cero red; ≤0 = nunca confiar"),
    ("cache_max_mb",    "WITT_FIGURES_CACHE_MAX_MB", "512", "float", None, "figures.fetch_figures",
     "tope de figures/; evicción LRU por mtime al escribir, evicted_n; 0 = sin tope declarado"),
    ("caption_chars",   "WITT_FIGURES_CAPTION_CHARS", "2000", "int", (100, 20000), "figures.parse_jats",
     "tope del caption que viaja (caption_truncated)"),
    ("embed_licenses",  "WITT_FIGURES_EMBED_LICENSES", _DEFAULT_EMBED, "licenses", None, "figures.LICENSE_TABLE",
     "sólo RESTRINGE la tabla; gobierna GET 200/403, miniatura Hoja y PDF"),
    ("panel_licenses",  "WITT_FIGURES_PANEL_LICENSES", _DEFAULT_PANEL, "licenses", None, "figures.LICENSE_TABLE",
     "licencias cuyos bytes ven las lentes (E2); unknown/zfin nunca"),
    ("prose_license",   "WITT_FIGURES_PROSE_LICENSE", "1", "bool", None, "figures.parse_license",
     "prosa 'Creative Commons Attribution' sin URL → cc-by (license-p-prose); 0 → cc-by-prose-unconfirmed (E3)"),
    ("openai_detail",   "WITT_FIGURES_OPENAI_DETAIL", "high", "choice", OPENAI_DETAILS,
     "_responses_kwargs · _openai_chat_call", "detail del input_image/image_url"),
    ("refetch_on_get",  "WITT_FIGURES_REFETCH_ON_GET", "0", "bool", None, "app.get_figure_bytes",
     "1 = ante bytes-not-in-cache UNA GET y servir SOLO si sha == congelado (409 si no)"),
    ("pdf_thumbs",      "WITT_FIGURES_PDF_THUMBS",   "1",  "bool", None, "record_pdf.build_pdf",
     "0 = palabras + enlace aunque la licencia permita"),
    ("count_tokens",    "WITT_FIGURES_COUNT_TOKENS", "0",  "bool", None, "audit() (lentes Anthropic)",
     "1 = vision.tokens_measured por count_tokens sin imágenes"),
    ("mcp_cache_dir",   "WITT_MCP_CACHE_DIR",        "",   "path", None, "figures.cache_dir",
     "ya existe; vacía = <repo>/mcp_cache; las figuras la HONRAN (<dir>/figures/)"),
)
ENV_VARS = tuple(s[1] for s in ENV_SPECS)
assert len(ENV_SPECS) == 21 and len(set(ENV_VARS)) == 21   # 20 nuevas + WITT_MCP_CACHE_DIR (pre-existente)


def _parse_env_value(kind, raw, default, clamp):
    """(value, ok). ok False = inválida → el llamador toma el default y declara 'default-invalid-env'."""
    s = (raw or "").strip()
    if kind == "bool":
        if s in ("0", "1"):
            return s == "1", True
        low = s.lower()
        if low in ("true", "yes", "on"):
            return True, True
        if low in ("false", "no", "off"):
            return False, True
        return default == "1", False
    if kind == "int":
        try:
            v = int(float(s))
        except (TypeError, ValueError):
            return int(default), False
        if clamp and not (clamp[0] <= v <= clamp[1]):
            return int(default), False
        return v, True
    if kind == "float":
        try:
            v = float(s)
        except (TypeError, ValueError):
            return float(default), False
        if v != v or v in (float("inf"), float("-inf")):
            return float(default), False
        if clamp and not (clamp[0] <= v <= clamp[1]):
            return float(default), False
        return v, True
    if kind == "csv":
        toks = [t.strip() for t in s.split(",") if t.strip()]
        return (toks, True) if toks else ([t for t in default.split(",")], False)
    if kind == "licenses":
        toks = [t.strip().lower() for t in s.split(",") if t.strip()]
        return (toks, True) if toks else ([t for t in default.split(",")], False)
    if kind == "choice":
        low = s.lower()
        return (low, True) if low in clamp else (default, False)
    if kind == "path":
        return (s or None), True
    raise ValueError(kind)


def env_config(env=None):
    """Lee las 21 variables (20 nuevas + WITT_MCP_CACHE_DIR) del entorno EN LA LLAMADA (M.4), tolerante.

    Devuelve {<name>: <valor efectivo>, 'sources': {<name>: 'env:<VAR>' | 'default-unset:<VAR>' |
    'default-invalid-env:<VAR>'}, 'env_ignored': [ids fuera de tabla en *_LICENSES, declarados], 'caps': {...forma (L)...},
    'constants': {...}}. `embed_licenses`/`panel_licenses` quedan como tuplas RESTRINGIDAS a la tabla (un id fuera de
    LICENSE_TABLE se ignora y se declara; la env sólo puede restringir, nunca ampliar — A.3)."""
    env = os.environ if env is None else env
    out, sources, ignored = {}, {}, []
    for name, var, default, kind, clamp, _reader, _effect in ENV_SPECS:
        raw = env.get(var)
        if raw is None or not str(raw).strip():
            v, _ = _parse_env_value(kind, default, default, clamp)
            sources[name] = f"default-unset:{var}"
        else:
            v, ok = _parse_env_value(kind, str(raw), default, clamp)
            sources[name] = f"env:{var}" if ok else f"default-invalid-env:{var}"
        if kind == "licenses":
            kept = tuple(t for t in v if t in LICENSE_TABLE)
            ignored.extend(f"{var}:{t}" for t in v if t not in LICENSE_TABLE)
            v = kept
        out[name] = v
    out["vision_lenses"] = list(out["vision_lenses"])
    out["sources"] = sources
    out["env_ignored"] = ignored
    out["caps"] = {
        "max_papers": {"value": out["max_papers"], "source": sources["max_papers"]},
        "max_per_paper": {"value": out["max_per_paper"], "source": sources["max_per_paper"]},
        "max_per_run": {"value": out["max_per_run"], "source": sources["max_per_run"]},
        "max_per_lens": {"value": out["max_per_lens"], "source": sources["max_per_lens"]},
        "max_image_mb": {"value": out["max_image_mb"], "source": sources["max_image_mb"]},
        "request_b64_mb": {"value": REQUEST_B64_MB, "source": CONSTANT_SOURCE},
        "zip_max_mb": {"value": out["zip_max_mb"], "source": sources["zip_max_mb"]},
        "caption_chars": {"value": out["caption_chars"], "source": sources["caption_chars"]},
    }
    out["constants"] = {"per_paper_budget_s": PER_PAPER_BUDGET_S, "socket_timeout_max_s": SOCKET_TIMEOUT_MAX_S,
                        "min_remaining_s": MIN_REMAINING_S, "request_b64_mb": REQUEST_B64_MB,
                        "max_megapixels": MAX_MEGAPIXELS, "source": CONSTANT_SOURCE}
    return out


def license_table(cfg=None):
    """Tabla EFECTIVA (A.3): embed/panel_view de la tabla ∧ restricción de env; fetch_bytes y words_es de la tabla.
    Devuelve {table: {id: {embed, panel_view, fetch_bytes, words_es}}, version, rule, env_ignored}."""
    cfg = cfg or env_config()
    table = {}
    for lid, row in LICENSE_TABLE.items():
        table[lid] = {"embed": bool(row["embed"] and lid in cfg["embed_licenses"]),
                      "panel_view": bool(row["panel_view"] and lid in cfg["panel_licenses"]),
                      "fetch_bytes": bool(row["fetch_bytes"]), "words_es": row["words_es"]}
    return {"table": table, "version": LICENSE_TABLE_VERSION, "rule": LICENSE_TABLE_RULE,
            "env_ignored": list(cfg["env_ignored"])}


def license_flags(license_id, cfg=None):
    """(embeddable, panel_view, fetch_bytes) EFECTIVOS para un id; id fuera de vocabulario → los de 'unknown'."""
    t = license_table(cfg)["table"]
    row = t.get(license_id) or t["unknown"]
    return row["embed"], row["panel_view"], row["fetch_bytes"]


# ---------------------------------------------------------------------------------------------------------
# (A.1) Parser JATS
# ---------------------------------------------------------------------------------------------------------
_TAG_RE = re.compile(r"<[^>]+>")                                   # la MISMA limpieza de tags que _xml_to_text
_FIG_RE = re.compile(r"<fig\b(?!-)(?P<attrs>[^>]*)>(?P<body>.*?)</fig>", re.S | re.I)   # <fig-count>/<fig-group> NO casan
_LABEL_RE = re.compile(r"<label\b[^>]*>(.*?)</label>", re.S | re.I)
_CAPTION_RE = re.compile(r"<caption\b(?P<attrs>[^>]*)>(?P<body>.*?)</caption>", re.S | re.I)
_ALTERNATIVES_RE = re.compile(r"<alternatives\b[^>]*>(.*?)</alternatives>", re.S | re.I)
_GRAPHIC_RE = re.compile(r"<graphic\b(?P<attrs>[^>]*?)(?P<selfclose>/)?>(?(selfclose)|(?P<body>.*?)</graphic>)", re.S | re.I)
_PI_DIMS_RE = re.compile(r"<\?(?:image-)?(original|scaled)-(width|height)\s+(\d+)\s*\?>", re.I)
_ATTR_ID_RE = re.compile(r"""\bid\s*=\s*["']([^"']+)["']""", re.I)
_ATTR_HREF_RE = re.compile(r"""\bxlink:href\s*=\s*["']([^"']+)["']""", re.I)
_ATTR_CTYPE_RE = re.compile(r"""\bcontent-type\s*=\s*["']([^"']+)["']""", re.I)
_ATTR_LANG_RE = re.compile(r"""\bxml:lang\s*=\s*["']([^"']+)["']""", re.I)
_ARTICLE_RE = re.compile(r"<article\b([^>]*)>", re.I)


def _clean_text(fragment):
    """Texto plano de un fragmento JATS: tags → espacio (la misma limpieza de tags que fetch_paper._xml_to_text),
    html.unescape UNA vez, espacios colapsados. (Medido: el caption de PMC11379296 g001 pasa de 1 395 chars con las
    entidades crudas a 1 387 tras desescapar '&amp;' ×2 — el ADR contaba antes del unescape.)"""
    t = _TAG_RE.sub(" ", fragment or "")
    t = html.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def _choose_graphic(body):
    """(href|None, content_type|None, graphic_span|'', n_thumbs_ignored). Con <alternatives>: el <graphic
    content-type="image">; sin alternatives: el primer <graphic> que no sea thumb. El .gif thumb se IGNORA y se cuenta."""
    n_thumbs = 0
    alt = _ALTERNATIVES_RE.search(body)
    scope = alt.group(1) if alt else body
    chosen = None
    fallback = None
    for g in _GRAPHIC_RE.finditer(scope):
        ctype = (_ATTR_CTYPE_RE.search(g.group("attrs")) or [None, None])[1]
        if ctype and ctype.lower() == "thumb":
            n_thumbs += 1
            continue
        if ctype and ctype.lower() == "image" and chosen is None:
            chosen = g
        elif fallback is None:
            fallback = g
    g = chosen or fallback
    if g is None:
        return None, None, "", n_thumbs
    href = (_ATTR_HREF_RE.search(g.group("attrs")) or [None, None])[1]
    ctype = (_ATTR_CTYPE_RE.search(g.group("attrs")) or [None, None])[1]
    return href, ctype, g.group(0), n_thumbs


def _dims_declared(graphic_span, body):
    """PIs <?original-*?>/<?scaled-*?> (PMC) o <?image-original-*?>/<?image-scaled-*?> (Springer) — declaración de
    la fuente. Se buscan en el <graphic> elegido y, si no trae, en el cuerpo de la <fig>."""
    out = {"original": None, "scaled": None}
    for scope in (graphic_span, body):
        found = {"original": {}, "scaled": {}}
        for kind, axis, val in _PI_DIMS_RE.findall(scope or ""):
            found[kind.lower()]["w" if axis.lower() == "width" else "h"] = int(val)
        got = False
        for kind in ("original", "scaled"):
            d = found[kind]
            if "w" in d and "h" in d:
                out[kind] = {"w": d["w"], "h": d["h"]}
                got = True
        if got:
            break
    return out


def parse_jats(xml_text, pmcid, caption_chars=None, prose_license=None):
    """(A.1) Figuras de un XML JATS. Devuelve {pmcid, figs[], n_fig, n_without_id, n_without_label, n_without_caption,
    n_without_graphic, n_thumbs_ignored, n_fig_permissions, skipped[], parser_version, caption_chars, article_lang}.

    Por <fig>: fig_id (@id; sin id → fila skipped {state 'no-fig-id', position}, contada, NO ítem), label|None,
    caption (texto plano, tope caption_chars con caption_truncated; el íntegro NO se guarda: vive en el XML cacheado),
    caption_state 'present'|'absent' (sin <caption> o vacío → absent: no puede sostener texto), caption_lang (xml:lang de
    <caption> o de <article>; jamás detección), graphic_href (+ graphic_content_type), dims_declared {original, scaled},
    fig_permissions_present (+ fig_license con scope 'figure-level' si existe), attrib_present, position (orden de documento).
    `_xml_to_text` NO se toca: esto es un lector aparte sobre el mismo XML."""
    cfg_cap = int(caption_chars) if caption_chars is not None else env_config()["caption_chars"]
    xml_text = xml_text or ""
    art = _ARTICLE_RE.search(xml_text)
    article_lang = (_ATTR_LANG_RE.search(art.group(1)) or [None, None])[1] if art else None
    figs, skipped = [], []
    n_without_label = n_without_caption = n_without_graphic = n_thumbs = n_fig_perm = 0
    for pos, m in enumerate(_FIG_RE.finditer(xml_text)):
        attrs, body = m.group("attrs"), m.group("body")
        fid = (_ATTR_ID_RE.search(attrs) or [None, None])[1]
        if not fid:
            skipped.append({"state": "no-fig-id", "position": pos})
            continue
        lm = _LABEL_RE.search(body)
        label = _clean_text(lm.group(1)) if lm else None
        if not label:
            label = None
            n_without_label += 1
        cm = _CAPTION_RE.search(body)
        caption_full = _clean_text(cm.group("body")) if cm else ""
        cap_lang = (_ATTR_LANG_RE.search(cm.group("attrs")) or [None, None])[1] if cm else None
        caption_state = "present" if caption_full else "absent"
        if caption_state == "absent":
            n_without_caption += 1
        truncated = len(caption_full) > cfg_cap
        caption = caption_full[:cfg_cap] if truncated else caption_full
        href, ctype, gspan, nth = _choose_graphic(body)
        n_thumbs += nth
        if not href:
            n_without_graphic += 1
        fig_perm = "<permissions" in body.lower()
        fig_license = None
        if fig_perm:
            n_fig_perm += 1
            fig_license = parse_license(m.group(0), None, prose_ok=prose_license)
            fig_license["scope"] = "figure-level"
        figs.append({
            "fig_id": fid, "label": label, "caption": caption, "caption_truncated": truncated,
            "caption_chars_source": len(caption_full), "caption_state": caption_state,
            "caption_lang": cap_lang or article_lang, "graphic_href": href, "graphic_content_type": ctype,
            "dims_declared": _dims_declared(gspan, body), "fig_permissions_present": fig_perm,
            "fig_license": fig_license, "attrib_present": "<attrib" in body.lower(), "position": pos,
        })
    return {"pmcid": pmcid, "figs": figs, "n_fig": len(figs), "n_without_id": len(skipped),
            "n_without_label": n_without_label, "n_without_caption": n_without_caption,
            "n_without_graphic": n_without_graphic, "n_thumbs_ignored": n_thumbs, "n_fig_permissions": n_fig_perm,
            "skipped": skipped, "parser_version": PARSER_VERSION, "caption_chars": cfg_cap, "article_lang": article_lang}


# ---------------------------------------------------------------------------------------------------------
# (A.2) Licencia por reglas ordenadas — dos fuentes (XML > search), conflict declarado
# ---------------------------------------------------------------------------------------------------------
_PERMISSIONS_RE = re.compile(r"<permissions\b[^>]*>(.*?)</permissions>", re.S | re.I)
_ARTICLE_META_RE = re.compile(r"<article-meta\b[^>]*>(.*?)</article-meta>", re.S | re.I)
_LICENSE_RE = re.compile(r"<license\b(?P<attrs>[^>]*)>(?P<body>.*?)</license>", re.S | re.I)
_LICENSE_P_RE = re.compile(r"<license-p\b[^>]*>(.*?)</license-p>", re.S | re.I)
_ALI_RE = re.compile(r"<ali:license_ref\b(?P<attrs>[^>]*)>(?P<body>.*?)</ali:license_ref>", re.S | re.I)
_EXTLINK_RE = re.compile(r"<ext-link\b(?P<attrs>[^>]*)>", re.S | re.I)
_CC_URL_RE = re.compile(r"(?:https?://)?(?:www\.)?creativecommons\.org/(?:licenses/(?P<var>by(?:-nc-nd|-nc-sa|-nc|-nd|-sa)?)"
                        r"(?:/(?P<ver>\d\.\d))?|publicdomain/(?P<zero>zero)(?:/(?P<zver>\d\.\d))?)", re.I)
_CC_VARIANT = {"by": "cc-by", "by-sa": "cc-by-sa", "by-nc": "cc-by-nc", "by-nd": "cc-by-nd",
               "by-nc-sa": "cc-by-nc-sa", "by-nc-nd": "cc-by-nc-nd"}
# (4) tokens en prosa — ORDEN: compuestos antes que 'CC BY'; 'CC BY-NC-ND' jamás casa como cc-by
_TOKEN_RULES = (
    (re.compile(r"\bCC[\s-]?BY[\s-]?NC[\s-]?ND\b", re.I), "cc-by-nc-nd"),
    (re.compile(r"\bCC[\s-]?BY[\s-]?NC[\s-]?SA\b", re.I), "cc-by-nc-sa"),
    (re.compile(r"\bCC[\s-]?BY[\s-]?NC\b", re.I), "cc-by-nc"),
    (re.compile(r"\bCC[\s-]?BY[\s-]?ND\b", re.I), "cc-by-nd"),
    (re.compile(r"\bCC[\s-]?BY[\s-]?SA\b", re.I), "cc-by-sa"),
    (re.compile(r"\bCC[\s-]?BY\b", re.I), "cc-by"),
    (re.compile(r"\bCC0\b|\bCC[\s-]?Zero\b", re.I), "cc0"),
)
_PROSE_ATTRIB_RE = re.compile(r"Creative\s+Commons\s+Attribution", re.I)
_PROSE_RESTRICT_RE = re.compile(r"Non[\s-]?Commercial|No[\s-]?Deriv|Share[\s-]?Alike", re.I)
_ALI_CTYPE_RE = re.compile(r"""\bcontent-type\s*=\s*["']cc(by(?:nc)?(?:nd|sa)?|0|zero)[^"']*["']""", re.I)
_ALI_CTYPE_MAP = {"by": "cc-by", "bync": "cc-by-nc", "byncnd": "cc-by-nc-nd", "byncsa": "cc-by-nc-sa",
                  "bynd": "cc-by-nd", "bysa": "cc-by-sa", "0": "cc0", "zero": "cc0"}
_SEARCH_LICENSE_MAP = {"cc by": "cc-by", "cc-by": "cc-by", "cc by-sa": "cc-by-sa", "cc by-nc": "cc-by-nc",
                       "cc by-nd": "cc-by-nd", "cc by-nc-sa": "cc-by-nc-sa", "cc by-nc-nd": "cc-by-nc-nd",
                       "cc0": "cc0", "cc zero": "cc0", "cc-zero": "cc0"}


def _cc_from_url(url):
    m = _CC_URL_RE.search(url or "")
    if not m:
        return None, None
    if m.group("zero"):
        return "cc0", m.group("zver")
    return _CC_VARIANT.get(m.group("var").lower()), m.group("ver")


def normalize_search_license(s):
    """`license` del search de EPMC ('cc by', 'cc by-nc-nd', …) → id del vocabulario, o None si no se reconoce."""
    if not s or not isinstance(s, str):
        return None
    return _SEARCH_LICENSE_MAP.get(re.sub(r"\s+", " ", s.strip().lower()))


def _article_permissions(xml_text):
    """El <permissions> a NIVEL ARTÍCULO: el de <article-meta> si existe; si no, el primero del documento."""
    meta = _ARTICLE_META_RE.search(xml_text)
    scope = meta.group(1) if meta else xml_text
    pm = _PERMISSIONS_RE.search(scope)
    if pm is None and meta is not None:
        pm = _PERMISSIONS_RE.search(xml_text)
    return pm.group(1) if pm else None


def parse_license(xml_text, search_license=None, prose_ok=None):
    """(A.2) Licencia del ARTÍCULO por REGLAS ORDENADAS (LICENSE_RULES) sobre <permissions>, con el `license` del
    search de EPMC como segunda fuente. Devuelve {id, source, evidence_text (≤200 del <license-p>), url|None, rule_no,
    version|None, scope 'article-level', search_license (normalizado|None), conflict?: {xml, search}}.
    Precedencia XML > search: si ambos existen y difieren gana el XML y `conflict` viaja declarado."""
    if prose_ok is None:
        prose_ok = env_config()["prose_license"]
    xml_text = xml_text or ""
    perm = _article_permissions(xml_text)
    lic_body, lic_attrs = "", ""
    lm = _LICENSE_RE.search(perm) if perm else None
    if lm:
        lic_body, lic_attrs = lm.group("body"), lm.group("attrs")
    elif perm:
        lic_body = perm
    p_texts = [_clean_text(p) for p in _LICENSE_P_RE.findall(lic_body)]
    evidence = " ".join(t for t in p_texts if t) or _clean_text(lic_body)
    evidence = evidence[:LICENSE_EVIDENCE_CHARS]
    out = {"id": "unknown", "source": "none", "evidence_text": evidence, "url": None, "rule_no": 7, "version": None,
           "scope": "article-level", "search_license": normalize_search_license(search_license)}
    found = None
    # (1) <ali:license_ref>
    for am in _ALI_RE.finditer(perm or ""):
        url = _clean_text(am.group("body"))
        lid, ver = _cc_from_url(url)
        if lid is None:
            cm = _ALI_CTYPE_RE.search(am.group("attrs"))
            if cm:
                lid = _ALI_CTYPE_MAP.get(cm.group(1).lower())
        if lid:
            found = (lid, "ali-license-ref", url or None, 1, ver)
            break
    # (2) xlink:href a creativecommons.org en <ext-link> (o en el propio <license>) dentro de <license>
    if found is None and lm:
        cands = [(_ATTR_HREF_RE.search(lic_attrs) or [None, None])[1]]
        cands += [(_ATTR_HREF_RE.search(e.group("attrs")) or [None, None])[1] for e in _EXTLINK_RE.finditer(lic_body)]
        for url in cands:
            lid, ver = _cc_from_url(url)
            if lid:
                found = (lid, "ext-link", url, 2, ver)
                break
    # (3) URL creativecommons.org en el TEXTO de <license-p>
    if found is None and lic_body:
        text_all = " ".join(p_texts) if p_texts else _clean_text(lic_body)
        um = _CC_URL_RE.search(text_all)
        if um:
            lid, ver = _cc_from_url(um.group(0))
            if lid:
                found = (lid, "license-p-url", um.group(0), 3, ver)
    # (4) tokens en prosa (compuestos antes)
    if found is None and lic_body:
        text_all = " ".join(p_texts) if p_texts else _clean_text(lic_body)
        for rx, lid in _TOKEN_RULES:
            tm = rx.search(text_all)
            if tm:
                vm = re.search(r"\b(\d\.\d)\b", text_all[tm.end():tm.end() + 40])
                found = (lid, "license-p-token", None, 4, vm.group(1) if vm else None)
                break
    # (5) prosa 'Creative Commons Attribution' sin restricciones
    if found is None and lic_body:
        text_all = " ".join(p_texts) if p_texts else _clean_text(lic_body)
        if _PROSE_ATTRIB_RE.search(text_all) and not _PROSE_RESTRICT_RE.search(text_all):
            vm = re.search(r"Attribution(?:\s+License)?\s+(\d\.\d)", text_all, re.I)
            found = ("cc-by" if prose_ok else "cc-by-prose-unconfirmed", "license-p-prose", None, 5,
                     vm.group(1) if vm else None)
    if found is not None:
        out.update({"id": found[0], "source": found[1], "url": found[2], "rule_no": found[3], "version": found[4]})
        if out["search_license"] and out["search_license"] != out["id"]:
            out["conflict"] = {"xml": out["id"], "search": out["search_license"]}
        return out
    # (6) el search de EPMC, SOLO cuando el XML no dio (1)-(5)
    if out["search_license"]:
        out.update({"id": out["search_license"], "source": "epmc-search", "rule_no": 6})
        return out
    return out   # (7) unknown / none


# ---------------------------------------------------------------------------------------------------------
# Bytes: mime por magic, dims por cabecera (stdlib), sha256
# ---------------------------------------------------------------------------------------------------------
_EXT_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
_JPEG_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def mime_from_extension(href):
    return _EXT_MIME.get(os.path.splitext(str(href or "").lower())[1])


def sniff_mime(data):
    """media_type por magic bytes (jpeg/png/gif/webp) o None."""
    if not data or len(data) < 12:
        return None
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def image_dims(data):
    """{w, h} por cabecera (JPEG SOF / PNG IHDR / GIF LSD / WebP VP8|VP8L|VP8X) o None. dims_source 'header'."""
    mime = sniff_mime(data)
    try:
        if mime == "image/jpeg":
            i, n = 2, len(data)
            while i + 4 <= n:
                if data[i] != 0xFF:
                    return None
                marker = data[i + 1]
                if marker == 0xFF:
                    i += 1
                    continue
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                    i += 2
                    continue
                if marker == 0xD9:
                    return None
                seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
                if marker in _JPEG_SOF:
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    return {"w": w, "h": h}
                i += 2 + seg_len
            return None
        if mime == "image/png":
            if data[12:16] != b"IHDR":
                return None
            w, h = struct.unpack(">II", data[16:24])
            return {"w": w, "h": h}
        if mime == "image/gif":
            w, h = struct.unpack("<HH", data[6:10])
            return {"w": w, "h": h}
        if mime == "image/webp":
            chunk = data[12:16]
            if chunk == b"VP8 ":
                w, h = struct.unpack("<HH", data[26:30])
                return {"w": w & 0x3FFF, "h": h & 0x3FFF}
            if chunk == b"VP8L":
                b = data[21:25]
                bits = b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)
                return {"w": (bits & 0x3FFF) + 1, "h": ((bits >> 14) & 0x3FFF) + 1}
            if chunk == b"VP8X":
                w = 1 + (data[24] | (data[25] << 8) | (data[26] << 16))
                h = 1 + (data[27] | (data[28] << 8) | (data[29] << 16))
                return {"w": w, "h": h}
            return None
    except (struct.error, IndexError):
        return None
    return None


# ---------------------------------------------------------------------------------------------------------
# (B.3) caché de figuras: dir (honra WITT_MCP_CACHE_DIR), estado, verificación por sha, evicción LRU
# ---------------------------------------------------------------------------------------------------------
def cache_dir(env=None):
    """(Path, dir_source ∈ 'env' | 'default'): <WITT_MCP_CACHE_DIR or ROOT/mcp_cache>/figures — la misma env que las
    tools Layer 0 (search_harness, zfin_expression_tsv)."""
    env = os.environ if env is None else env
    v = (env.get("WITT_MCP_CACHE_DIR") or "").strip()
    if v:
        return Path(v) / "figures", "env"
    return _fetch_paper.CACHE / "figures", "default"


def _probe_writable(path):
    """Escribe y borra un archivo sonda dentro de `path` (nuestro propio directorio de caché). Costura para smokes."""
    probe = Path(path) / f".probe_{os.getpid()}_{int(time.time() * 1000)}"
    try:
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def cache_dir_state(path, create=True):
    """'writable' | 'read-only' | 'missing' — medido al inicio de la etapa. Un dir ausente se intenta crear
    (parents); si no se puede → 'missing'. `create=False` (F8, ADR-0083): sólo MIDE — un dir ausente es 'missing' y
    NO se crea (attach/runs lo usan cuando no hay nada que bajar, para que un gate jamás cree <repo>/mcp_cache/figures)."""
    p = Path(path)
    if not p.exists():
        if not create:
            return "missing"
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError:
            return "missing"
    if not p.is_dir():
        return "missing"
    return "writable" if _probe_writable(p) else "read-only"


def cache_path_of(cache_root, pmcid, href):
    """<cache_root>/<PMCID>/<basename(href)> — el href se reduce a basename (jamás rutas)."""
    return Path(cache_root) / str(pmcid) / os.path.basename(str(href))


def cache_path_rel_of(pmcid, href):
    return f"{pmcid}/{os.path.basename(str(href))}"


def verify_cached(cache_root, item_or_rel, expected_sha=None):
    """Recalcula el sha256 del archivo en caché (ADR-0077: sha verificado al LEER). Acepta un FigureItem (usa
    cache_path_rel + sha256) o una ruta relativa + expected_sha. Devuelve {state ∈ 'verified' | 'mismatch' | 'missing',
    sha256_expected, sha256_actual|None, path, bytes|None}."""
    if isinstance(item_or_rel, dict):
        rel, expected = item_or_rel.get("cache_path_rel"), item_or_rel.get("sha256")
    else:
        rel, expected = item_or_rel, expected_sha
    out = {"state": "missing", "sha256_expected": expected, "sha256_actual": None, "path": None, "bytes": None}
    if not rel or not expected:
        return out
    p = Path(cache_root) / rel
    out["path"] = str(p)
    if not p.is_file():
        return out
    try:
        actual = raw_store.sha256_file(p)
        out["bytes"] = p.stat().st_size
    except OSError:
        return out
    out["sha256_actual"] = actual
    out["state"] = "verified" if actual == expected else "mismatch"
    return out


def evict_lru(cache_root, max_mb, protect=()):
    """Evicción LRU por mtime al escribir (B.3): borra los archivos MÁS VIEJOS de <cache_root> hasta que el total quepa
    en max_mb; empate por ruta (determinista). `protect` = rutas que jamás se borran (las recién escritas). max_mb <= 0
    = sin tope declarado → 0. Devuelve evicted_n."""
    root = Path(cache_root)
    if max_mb is None or float(max_mb) <= 0 or not root.is_dir():
        return 0
    cap = float(max_mb) * 1024 * 1024
    protect = {str(Path(p).resolve()) for p in protect}
    files = []
    for p in root.rglob("*"):
        if p.is_file() and not p.name.endswith(".part"):
            try:
                st = p.stat()
            except OSError:
                continue
            files.append((st.st_mtime, str(p).replace("\\", "/"), p, st.st_size))
    total = sum(f[3] for f in files)
    evicted = 0
    for _mtime, _key, p, size in sorted(files, key=lambda f: (f[0], f[1])):
        if total <= cap:
            break
        if str(p.resolve()) in protect:
            continue
        try:
            p.unlink()
            total -= size
            evicted += 1
        except OSError:
            continue
    return evicted


def _cache_ledger_paths(pmcid_dir):
    return sorted(Path(pmcid_dir).glob("_figures_*.json"))


def _read_fresh_ledger(pmcid_dir, ttl_days, now):
    """El ledger raw más reciente del PMCID si su fetched_at está dentro de ttl_days; None si no hay o caducó.
    ttl_days <= 0 = nunca confiar (re-descarga)."""
    if ttl_days is None or float(ttl_days) <= 0:
        return None
    paths = _cache_ledger_paths(pmcid_dir)
    if not paths:
        return None
    try:
        led = json.loads(paths[-1].read_text(encoding="utf-8"))
        fetched = datetime.fromisoformat(str(led.get("fetched_at")).replace("Z", "+00:00"))
        # corrector: la resta DENTRO del try — un `now` naive contra un ledger aware ('…Z') lanzaba TypeError fuera de
        # fetch_figures (attach lo habría vuelto `state 'error: TypeError…'`, perdiendo TODA la etapa por un ledger legible)
        age_days = (now - fetched).total_seconds() / 86400.0
    except (OSError, ValueError, TypeError):
        return None
    if age_days > float(ttl_days) or age_days < -1:
        return None
    led["_path"] = str(paths[-1])
    led["_age_days"] = round(age_days, 3)
    return led


# ---------------------------------------------------------------------------------------------------------
# (B.1) la ÚNICA costura de red: _get_bytes — precheck Content-Length, streaming a .part, tope, timeout
# ---------------------------------------------------------------------------------------------------------
_urlopen = urllib.request.urlopen     # costura para smokes (la global urllib.request.urlopen sigue bloqueada/contada)


def _zip_url(pmcid):
    """GET {EPMC}/{PMCID}/supplementaryFiles — verificada 200 en el ADR; SIN ?includeInlineImage (no verificado)."""
    return f"{EPMC}/{pmcid}/supplementaryFiles"


def _error_kind(e):
    if isinstance(e, urllib.error.HTTPError):
        return f"http-{e.code}"
    if isinstance(e, TimeoutError) or type(e).__name__ in ("timeout", "SocketTimeout"):
        return "timeout"
    if isinstance(e, urllib.error.URLError):
        reason = getattr(e, "reason", None)
        if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
            return "timeout"
        return "network"
    if isinstance(e, (ConnectionError, OSError)):
        return "network"
    return f"error: {type(e).__name__}: {str(e)[:120]}"


class _DeadlineExceeded(Exception):
    """corrector (ADR-0083 B.4/C): la descarga superó el presupuesto POR PAPER (deadline) — se corta por reloj, no se espera al socket."""


def _get_bytes(url, timeout, max_bytes, dest=None, deadline=None, clock=None):
    """UNA GET con pacing de net_throttle (host www.ebi.ac.uk, WITT_EPMC_MIN_INTERVAL_S) y la UA de fetch_paper.

    Precheck de Content-Length contra max_bytes ANTES de leer el cuerpo (0 bytes leídos → 'zip-over-max'); sin
    Content-Length se lee por chunks de 1 MB con tope y se aborta declarando; con `dest` el cuerpo se escribe en
    <dest>.part y se publica por os.replace SOLO completo (patrón zfin_expression_tsv) — sin `dest` vuelve en `data`.
    corrector (B.4): `deadline` (en el reloj `clock`, default time.monotonic) = fin del presupuesto POR PAPER; el bucle de
    chunks lo consulta y ABORTA con error_kind 'timeout' cuando se rebasa — el socket timeout se renueva en cada read() y
    por sí solo no acota una respuesta que gotea (el hueco de latido queda ≤ min(45, restante) s, como promete (C)).
    Devuelve {status 'ok'|'error', http_status, content_length, content_type, bytes, elapsed_s, url, error_kind?, error?,
    data?|path?, deadline_exceeded?}. JAMÁS relanza: el llamador declara filas (§6)."""
    t0 = time.monotonic()
    clock = clock or time.monotonic
    out = {"status": "error", "http_status": None, "content_length": None, "content_type": None, "bytes": 0,
           "elapsed_s": None, "url": url, "throttle_slept_s": None}
    part = Path(str(dest) + ".part") if dest is not None else None
    try:
        out["throttle_slept_s"] = _net_throttle.get_throttle(EPMC_HOST, _fetch_paper._min_interval_s()).wait()
        req = urllib.request.Request(url, headers=_fetch_paper._ua())
        with _urlopen(req, timeout=timeout) as r:
            out["http_status"] = getattr(r, "status", None) or (r.getcode() if hasattr(r, "getcode") else None)
            hdrs = getattr(r, "headers", None)
            cl = hdrs.get("Content-Length") if hdrs is not None else None
            out["content_type"] = (hdrs.get("Content-Type") if hdrs is not None else None)
            if cl is not None:
                try:
                    out["content_length"] = int(cl)
                except (TypeError, ValueError):
                    out["content_length"] = None
            if out["content_length"] is not None and max_bytes and out["content_length"] > max_bytes:
                out.update({"error_kind": "zip-over-max",
                            "error": f"Content-Length {out['content_length']} > max_bytes {max_bytes} (body not read)"})
                out["elapsed_s"] = round(time.monotonic() - t0, 3)
                return out
            sink = open(part, "wb") if part is not None else io.BytesIO()
            try:
                total = 0
                while True:
                    if deadline is not None and clock() > deadline:
                        raise _DeadlineExceeded(f"paper budget deadline exceeded after {total} bytes (per-paper budget, ADR-0083 B.4)")
                    chunk = r.read(CHUNK_BYTES)
                    if not chunk:
                        break
                    total += len(chunk)
                    if max_bytes and total > max_bytes:
                        raise OverflowError(f"body exceeded max_bytes {max_bytes} after {total} bytes")
                    sink.write(chunk)
                out["bytes"] = total
                if part is None:
                    out["data"] = sink.getvalue()
            finally:
                sink.close()
        if part is not None:
            os.replace(part, dest)
            out["path"] = str(dest)
        out["status"] = "ok"
    except OverflowError as e:
        out.update({"error_kind": "zip-over-max", "error": str(e)[:200]})
    except _DeadlineExceeded as e:   # corrector: corte por presupuesto del paper → 'timeout' declarado (el reloj, no el socket)
        out.update({"error_kind": "timeout", "error": str(e)[:200], "deadline_exceeded": True})
    except Exception as e:  # HTTPError, URLError, timeout, OSError, RuntimeError (red bloqueada en smokes)
        out.update({"error_kind": _error_kind(e), "error": f"{type(e).__name__}: {str(e)[:200]}"})
        if isinstance(e, urllib.error.HTTPError):
            out["http_status"] = e.code
    finally:
        if part is not None and part.exists() and out["status"] != "ok":
            try:
                part.unlink()
            except OSError:
                pass
    out["elapsed_s"] = round(time.monotonic() - t0, 3)
    return out


def _not_fetched(reason):
    return f"not-fetched ({reason})"


def _iso(dt):
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------------------------------------
# (B) fetch_figures — UN zip por paper
# ---------------------------------------------------------------------------------------------------------
def fetch_figures(pmcid, figs, cfg=None, cache_root=None, deadline=None, clock=None, now=None, dir_state=None):
    """Baja (o lee de caché) los bytes de las figuras `figs` (dicts de parse_jats ya SELECCIONADAS) de UN paper.

    Devuelve {ledger, by_href} con ledger = {mechanism, status ∈ FETCH_LEDGER_STATUSES, http_status, zip_bytes,
    zip_entries_n, elapsed_s, n_wanted, n_extracted, n_missing, cache_hit, fetched_at, budget_s, timeout_s, evicted_n,
    error?, error_kind?} y by_href[href_lower] = {bytes_state, sha256, bytes, media_type, dims_measured, cache_path_rel,
    cache_hit, fetched_at, mime_from_extension}. Un fallo del zip deja TODAS las filas 'not-fetched (<razón>)' y la
    corrida sigue (§6); los errores JAMÁS se cachean; el sha es el de los bytes ORIGINALES tal como llegaron.
    `deadline` (reloj `clock`, default time.monotonic) = fin del presupuesto TOTAL de la etapa; por paper
    min(45, restante), socket min(30, restante); restante < 5 s → 'budget-exhausted' sin red."""
    cfg = cfg or env_config()
    clock = clock or time.monotonic
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:      # corrector: un `now` naive se normaliza a UTC (el ledger escribe aware '…Z')
        now = now.replace(tzinfo=timezone.utc)
    if cache_root is None:
        cache_root = cache_dir()[0]
    cache_root = Path(cache_root)
    pdir = cache_root / str(pmcid)
    ledger = {"mechanism": MECHANISM, "status": "error", "http_status": None, "zip_bytes": None, "zip_entries_n": None,
              "elapsed_s": 0.0, "n_wanted": 0, "n_extracted": 0, "n_missing": 0, "cache_hit": False, "fetched_at": None,
              "budget_s": None, "timeout_s": None, "evicted_n": 0}
    by_href = {}
    t0 = clock()

    def _row(state, **kw):
        base = {"bytes_state": state, "sha256": None, "bytes": None, "media_type": None, "dims_measured": None,
                "cache_path_rel": None, "cache_hit": None, "fetched_at": None}
        base.update(kw)
        return base

    wanted = {}
    for f in figs:
        href = f.get("graphic_href")
        key = os.path.basename(str(href)).lower() if href else None
        if not href:
            by_href[f"__nohref__{f.get('fig_id')}"] = _row(_not_fetched("no-graphic"))
            continue
        if f.get("caption_state") != "present":
            by_href[key] = _row(_not_fetched("no-caption"), mime_from_extension=mime_from_extension(href))
            continue
        wanted[key] = href
    ledger["n_wanted"] = len(wanted)

    def _all(state, **kw):
        for key, href in wanted.items():
            by_href[key] = _row(state, mime_from_extension=mime_from_extension(href), **kw)

    def _finish(status, **kw):
        ledger.update(kw)
        ledger["status"] = status
        ledger["elapsed_s"] = round(max(0.0, clock() - t0), 3)
        return {"ledger": ledger, "by_href": by_href}

    if not wanted:
        return _finish("not-requested")
    if dir_state is None:
        dir_state = cache_dir_state(cache_root)
    if dir_state != "writable":
        _all(_not_fetched("cache-read-only"))
        return _finish("error", error=f"cache dir {dir_state}", error_kind="cache-read-only")

    # --- caché: ledger fresco + archivos presentes + sha recalculado igual → cache_hit, cero red -----------------
    led = _read_fresh_ledger(pdir, cfg["ttl_days"], now)
    prev_sha = {}
    if led is not None:
        entries = {str(e.get("href", "")).lower(): e for e in (led.get("entries") or []) if isinstance(e, dict)}
        complete = True
        rows = {}
        mismatched = []
        for key, href in wanted.items():
            e = entries.get(key)
            p = pdir / os.path.basename(href)
            if e is None or not e.get("sha256") or not p.is_file():
                complete = False
                break
            actual = raw_store.sha256_file(p)
            prev_sha[key] = e["sha256"]
            if actual != e["sha256"]:
                # corrector (B.3): sha ≠ → la copia NO se reutiliza — un archivo corrupto/parcial con ledger fresco dejaba esa
                # figura sin bytes 30 días en TODAS las corridas; se va a la red (UNA GET, con presupuesto) y se DECLARA
                mismatched.append(os.path.basename(href))
                complete = False
                continue
            rows[key] = _row("verified", sha256=actual, bytes=p.stat().st_size, media_type=e.get("mime"), dims_measured=e.get("dims"),
                             cache_path_rel=cache_path_rel_of(pmcid, href), cache_hit=True, fetched_at=led.get("fetched_at"),
                             mime_from_extension=mime_from_extension(href), sha256_actual=actual)
        if complete:
            by_href.update(rows)
            return _finish("cache-hit", cache_hit=True, fetched_at=led.get("fetched_at"), http_status=led.get("http_status"),
                           zip_bytes=led.get("zip_bytes"), zip_entries_n=led.get("zip_entries_n"),
                           n_extracted=sum(1 for r in rows.values() if r["bytes_state"] == "verified"),
                           n_missing=0, cache_age_days=led.get("_age_days"))
        if mismatched:
            ledger["cache_mismatch_hrefs"] = mismatched      # declarado ANTES de la red: pase lo que pase, consta el porqué

    # --- presupuesto (B.4) ------------------------------------------------------------------------------------------
    remaining = (deadline - clock()) if deadline is not None else PER_PAPER_BUDGET_S
    if remaining < MIN_REMAINING_S:
        _all(_not_fetched("budget-exhausted"))
        return _finish("skipped-budget", error=f"BudgetExhausted: remaining {round(remaining, 3)} s < {MIN_REMAINING_S} s "
                                               "before the request (no request sent)", error_kind="budget-exhausted")
    paper_budget = min(PER_PAPER_BUDGET_S, remaining)
    timeout = min(SOCKET_TIMEOUT_MAX_S, remaining)
    ledger["budget_s"], ledger["timeout_s"] = round(paper_budget, 3), round(timeout, 3)
    paper_deadline = clock() + paper_budget      # corrector (B.4): el presupuesto por paper se APLICA en la descarga, no sólo se declara

    # --- red: UN zip ------------------------------------------------------------------------------------------------
    try:
        pdir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        _all(_not_fetched("cache-read-only"))
        return _finish("error", error=f"{type(e).__name__}: {e}", error_kind="cache-read-only")
    zip_dest = pdir / f"_supplementaryFiles_{os.getpid()}.zip"
    max_bytes = int(float(cfg["zip_max_mb"]) * 1024 * 1024)
    get_kw = {}
    try:   # la costura _get_bytes puede estar FALSEADA con la firma de 1.12-F1 (url, timeout, max_bytes, dest): sólo se pasa lo que acepta
        get_params = inspect.signature(_get_bytes).parameters
        if "deadline" in get_params:
            get_kw["deadline"] = paper_deadline
        if "clock" in get_params:
            get_kw["clock"] = clock
    except (TypeError, ValueError):
        get_kw = {}
    try:
        got = _get_bytes(_zip_url(pmcid), timeout, max_bytes, dest=zip_dest, **get_kw)
    except Exception as e:  # un _get_bytes que LANZA (smoke) → filas 'error: <tipo>: <msg>' y la corrida sigue
        _all(f"error: {type(e).__name__}: {str(e)[:120]}")
        return _finish("error", error=f"{type(e).__name__}: {str(e)[:200]}", error_kind=f"error: {type(e).__name__}")
    ledger["http_status"] = got.get("http_status")
    if got.get("status") != "ok":
        kind = got.get("error_kind") or "network"
        reason = kind if (kind in NOT_FETCHED_REASONS or re.fullmatch(r"http-\d{3}", kind)) else None
        state = _not_fetched(reason) if reason else (kind if kind.startswith("error: ") else _not_fetched("network"))
        _all(state)
        return _finish("error", error=got.get("error"), error_kind=kind, zip_bytes=got.get("bytes") or None,
                       content_length=got.get("content_length"))
    ledger["zip_bytes"] = got.get("bytes")
    fetched_at = _iso(now)
    written = []
    try:
        try:
            zf = zipfile.ZipFile(zip_dest)
        except zipfile.BadZipFile:
            head = zip_dest.read_bytes()[:4] if zip_dest.exists() else b""
            reason = "not-a-zip" if head[:2] != b"PK" else "bad-zip"
            _all(_not_fetched(reason))
            return _finish("error", error=f"{reason}: content-type {got.get('content_type')!r}", error_kind=reason)
        with zf:
            infos = {os.path.basename(i.filename).lower(): i for i in zf.infolist() if not i.is_dir()}
            ledger["zip_entries_n"] = len(infos)
            entries = []
            for key, href in wanted.items():
                info = infos.get(key)
                if info is None:
                    stem = os.path.splitext(key)[0]
                    thumb = any(k == f"{stem}.gif" for k in infos)
                    by_href[key] = _row(_not_fetched("href-not-in-zip; thumb-available" if thumb else "href-not-in-zip"),
                                        mime_from_extension=mime_from_extension(href))
                    continue
                if info.file_size > max_bytes:
                    by_href[key] = _row(_not_fetched("size-cap"), mime_from_extension=mime_from_extension(href))
                    continue
                data = zf.read(info)
                mime = sniff_mime(data)
                if mime not in MEDIA_TYPES:
                    by_href[key] = _row(_not_fetched("unsupported-mime"), mime_from_extension=mime_from_extension(href))
                    continue
                dims = image_dims(data)
                if dims is None or dims["w"] * dims["h"] > MAX_MEGAPIXELS * 1_000_000:
                    by_href[key] = _row(_not_fetched("decode-error"), mime_from_extension=mime_from_extension(href),
                                        media_type=mime)
                    continue
                target = pdir / os.path.basename(href)
                part = Path(str(target) + ".part")
                part.write_bytes(data)
                os.replace(part, target)
                written.append(target)
                sha = sha256_bytes(data)
                by_href[key] = _row("verified", sha256=sha, bytes=len(data), media_type=mime, dims_measured=dims,
                                    cache_path_rel=cache_path_rel_of(pmcid, href), cache_hit=False, fetched_at=fetched_at,
                                    mime_from_extension=mime_from_extension(href))
                entries.append({"href": os.path.basename(href), "sha256": sha, "bytes": len(data), "mime": mime, "dims": dims})
        ledger["n_extracted"] = len(entries)
        ledger["n_missing"] = len(wanted) - len(entries)
        if ledger.get("cache_mismatch_hrefs"):
            # corrector (B.3): la re-descarga tras un mismatch en caché queda DECLARADA; si la fuente entrega hoy otro sha que el del
            # ledger previo, eso también consta (cambio en la fuente o en la caché: medido, no disfrazado) — la fila es 'verified'
            # contra los bytes que la fuente entregó AHORA (el sha es el de los bytes originales tal como llegaron)
            ledger["cache_mismatch_refetched"] = list(ledger["cache_mismatch_hrefs"])
            changed = [{"href": e["href"], "previous_ledger_sha256": prev_sha.get(e["href"].lower()), "sha256": e["sha256"]}
                       for e in entries if prev_sha.get(e["href"].lower()) and prev_sha[e["href"].lower()] != e["sha256"]]
            if changed:
                ledger["sha_changed_from_previous_ledger"] = changed
        raw_ledger = {"fetched_at": fetched_at, "mechanism": MECHANISM, "pmcid": pmcid, "url": _zip_url(pmcid),
                      "http_status": got.get("http_status"), "zip_bytes": got.get("bytes"),
                      "zip_entries_n": ledger["zip_entries_n"], "module_version": MODULE_VERSION, "entries": entries}
        lpath = pdir / f"_figures_{now.strftime('%Y%m%d')}.json"
        lpath.write_text(json.dumps(raw_ledger, ensure_ascii=False, indent=1), encoding="utf-8")
        written.append(lpath)
    finally:
        try:
            if zip_dest.exists():
                zip_dest.unlink()      # el zip no se conserva: sólo las entradas pedidas + el ledger
        except OSError:
            pass
    ledger["evicted_n"] = evict_lru(cache_root, cfg["cache_max_mb"], protect=written)
    return _finish("success", fetched_at=fetched_at, cache_hit=False)


# ---------------------------------------------------------------------------------------------------------
# FigureItem (L) y proyecciones
# ---------------------------------------------------------------------------------------------------------
def make_item(pmcid, evidence_id, fig, license_, flags, bytes_row=None, caption_in_excerpt=None):
    """FigureItem con las llaves EXACTAS de FIGURE_ITEM_KEYS (orden incluido). `fig` = dict de parse_jats,
    `license_` = dict de parse_license (o el fig_license figure-level), `flags` = (embeddable, panel_view, fetch_bytes),
    `bytes_row` = fila de fetch_figures.by_href (None → bytes_state según flags/caption)."""
    embeddable, panel_view, fetch_bytes = flags
    row = bytes_row or {}
    href = fig.get("graphic_href")
    if bytes_row is None:
        if license_.get("id") == "zfin-display-only" or not fetch_bytes:
            state = "never (zfin-display-only)" if license_.get("id") == "zfin-display-only" else _not_fetched("no-graphic")
        elif not href:
            state = _not_fetched("no-graphic")
        elif fig.get("caption_state") != "present":
            state = _not_fetched("no-caption")
        else:
            state = _not_fetched("run-cap")
        row = {"bytes_state": state}
    sha = row.get("sha256")
    dims_m = row.get("dims_measured")
    scaled = (fig.get("dims_declared") or {}).get("scaled")
    dims_match = (dims_m == scaled) if (dims_m and scaled) else None
    source_url = f"{EPMC}/{pmcid}/supplementaryFiles#{os.path.basename(href)}" if href else None
    raw_ref = None
    if row.get("bytes_state") == "verified" and sha:
        raw_ref = raw_store.source_pointer(source_url, sha256=sha, bytes_=row.get("bytes"), content_type=row.get("media_type"))
    lic = {k: license_.get(k) for k in ("id", "source", "evidence_text", "url", "rule_no", "version", "scope")}
    if license_.get("conflict"):
        lic["conflict"] = license_["conflict"]
    caption_state = fig.get("caption_state")
    item = {
        "id": f"{pmcid}#{fig['fig_id']}", "pmcid": pmcid, "evidence_id": evidence_id, "fig_id": fig["fig_id"],
        "label": fig.get("label"), "caption": fig.get("caption") or "", "caption_truncated": bool(fig.get("caption_truncated")),
        "caption_state": caption_state, "caption_lang": fig.get("caption_lang"), "graphic_href": href,
        "source_url": source_url, "media_type": row.get("media_type"),
        "mime_from_extension": row.get("mime_from_extension", mime_from_extension(href)) if href else None,
        "bytes": row.get("bytes"), "sha256": sha, "sha256_short": sha[:SHA_SHORT] if sha else None,
        "dims_declared": fig.get("dims_declared") or {"original": None, "scaled": None},
        "dims_measured": dims_m, "dims_source": "header" if dims_m else None, "dims_match": dims_match,
        "license": lic, "embeddable": bool(embeddable), "panel_view": bool(panel_view),
        "bytes_state": row.get("bytes_state"), "raw_ref": raw_ref, "cache_path_rel": row.get("cache_path_rel"),
        "fetched_at": row.get("fetched_at"), "cache_hit": row.get("cache_hit"), "cited_by_answer": [],
        "seen_by_lenses": [], "delivered_to_synthesizer": caption_state == "present",
        "caption_in_excerpt": caption_in_excerpt, "class": FIGURE_CLASS,
    }
    assert tuple(item) == FIGURE_ITEM_KEYS
    return item


def project_for_prompt(items):
    """(D.1) Proyección para el sintetizador/consejo: SOLO PROMPT_FIGURE_KEYS de ítems con caption 'present';
    `license` como {id, source}. Jamás cache_path/raw_ref/b64/bytes."""
    out = []
    for it in items or []:
        if it.get("caption_state") != "present":
            continue
        proj = {k: it.get(k) for k in PROMPT_FIGURE_KEYS}
        lic = it.get("license") or {}
        proj["license"] = {"id": lic.get("id"), "source": lic.get("source")}
        out.append(proj)
    return out


def _norm_ws(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


_FULLTEXT_XML_RE = re.compile(r"fulltext.*\.xml$", re.I)   # raw_paper_*_fulltext.xml · raw_europepmc_S4-*_fulltext_*.xml · fixtures


def locate_xml(raw_cached, root=None):
    """El XML de texto completo de `fetched.raw_cached` resuelto contra `root` (default fetch_paper.ROOT, la base de _rel).
    Casa `*fulltext*.xml` (medido en mcp_cache: `raw_paper_<cid>_<stamp>_fulltext.xml` de fetch_paper Y
    `raw_europepmc_S4-*_fulltext_<stamp>.xml`; el fixture `epmc_fulltext_<PMCID>_<stamp>.xml`). Rutas absolutas se
    respetan. Devuelve Path existente o None (varios → el primero en orden; ninguno → None)."""
    root = Path(root) if root is not None else _fetch_paper.ROOT
    for p in sorted(str(x) for x in (raw_cached or []) if _FULLTEXT_XML_RE.search(os.path.basename(str(x)))):
        path = Path(p)
        if not path.is_absolute():
            path = root / path
        if path.is_file():
            return path
    return None


def _paper_pmcid(paper):
    sr = paper.get("search_rec") or {}
    v = sr.get("pmcid") or (paper.get("record") or {}).get("pmcid")
    return str(v).upper() if v else None


# ---------------------------------------------------------------------------------------------------------
# (C) attach — figuras adheridas a los papers de la Ruta B
# ---------------------------------------------------------------------------------------------------------
def attach(bundle, cfg=None, cache_root=None, root=None, clock=None, now=None, on_event=None, search_license_of=None):
    """Adhiere figuras a `bundle['path_b']['papers'][*]` (mutación EN SITIO de los papers) y devuelve el resumen que
    `runs` congela como `frozen.figures` (menos `vision`/`selection.n_sent_to_panel_by_lens`/`n_cited`, que F4 llena).

    Selección DETERMINISTA por código (C): papers `source ∈ FIGURE_SOURCES` con PMCID, `fetched.full_text True` y XML en
    `fetched.raw_cached` (locate_xml contra `root`), en orden `selection_rank`, primeros max_papers; figuras en orden de
    documento, primeras max_per_paper; tope max_per_run; el resto 'not-fetched (paper-cap | run-cap)' con caption parseado.
    Cada paper elegible gana paper['figures'] = {state ∈ PAPER_FIGURES_STATES, n, items[FigureItem], ledger}; los ZFIN no.
    `on_event(kind, payload)` con kind ∈ 'paper' | 'figure' (F4 los vuelve eventos stage.figures.*; 'paper' llega con
    phase 'start' ANTES de cada descarga = latido). `search_license_of(paper)` → license del search (default:
    search_rec.license, ausente en el bundle de hoy → None declarado). Con cfg['figures'] False no toca nada y devuelve
    el estado kill-switch. JAMÁS relanza por un paper: la corrida sigue (§6)."""
    cfg = cfg or env_config()
    clock = clock or time.monotonic
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:      # corrector: un `now` naive se normaliza a UTC (el ledger escribe aware '…Z')
        now = now.replace(tzinfo=timezone.utc)
    lt = license_table(cfg)
    base = {"state": None, "module_version": MODULE_VERSION, "parser_version": PARSER_VERSION,
            "license_table_version": LICENSE_TABLE_VERSION, "license_table": lt["table"], "license_table_rule": lt["rule"],
            "license_table_env_ignored": lt["env_ignored"], "mechanism": MECHANISM,
            "cache": {"dir_source": None, "dir_state": None, "ttl_days": cfg["ttl_days"], "cache_max_mb": cfg["cache_max_mb"],
                      "evicted_n": 0},
            "budget": {"total_s": cfg["budget_s"], "used_s": 0.0, "over_budget": False}, "caps": cfg["caps"],
            "n_papers_eligible": 0, "n_papers_selected": 0, "n_papers_with_xml": 0, "n_figures": 0, "n_with_caption": 0,
            "n_fetched": 0, "n_verified": 0, "n_not_fetched": 0, "n_error": 0, "n_mismatch": 0, "n_embeddable": 0, "n_panel_view": 0,
            "n_unknown_license": 0, "n_cited": 0, "zfin_figures_state": ZFIN_FIGURES_STATE,
            "selection": {"rule": SELECTION_RULE, "n_sent_to_panel_by_lens": {}}, "items": [], "papers": [],
            "vocabulary": VOCABULARY}
    if not cfg["figures"]:
        base["state"] = "kill-switch WITT_FIGURES=0"
        base["kill_switch"] = {"WITT_FIGURES": "0",
                               "declared_exceptions": ["render_contract_version", "figures", "deterministic_checks.figures"]}
        return base
    papers = ((bundle or {}).get("path_b") or {}).get("papers") or []
    if not papers:
        base["state"] = "no-path-b"
        return base
    if cache_root is None:
        cache_root, dir_source = cache_dir()
    else:  # un llamador (smoke/F4) inyectó la ruta: se declara 'injected' — jamás se disfraza de env|default
        env_dir, env_src = cache_dir()
        dir_source = env_src if Path(cache_root).resolve() == env_dir.resolve() else "injected"
    cache_root = Path(cache_root)
    # F8 (ADR-0083 B.3): aquí sólo se MIDE (create=False); el dir se crea más abajo, SOLO cuando hay papers seleccionados —
    # un bundle sin XML de texto completo no toca el disco (los gates sin WITT_MCP_CACHE_DIR dejaban <repo>/mcp_cache/figures vacío)
    dir_state = cache_dir_state(cache_root, create=False)
    base["cache"].update({"dir_source": dir_source, "dir_state": dir_state})

    # --- elegibles y selección --------------------------------------------------------------------------------------
    eligible = []
    for idx, p in enumerate(papers):
        if not isinstance(p, dict) or p.get("source") not in FIGURE_SOURCES:
            continue
        pmcid = _paper_pmcid(p)
        fetched = p.get("fetched") or {}
        xml_path = locate_xml(fetched.get("raw_cached"), root) if fetched.get("full_text") else None
        if not pmcid or xml_path is None:
            p["figures"] = {"state": "no-fulltext-xml", "n": 0, "items": [], "ledger": None}
            continue
        rank = p.get("selection_rank")
        eligible.append((rank if isinstance(rank, int) else 10 ** 9, idx, p, pmcid, xml_path))
    eligible.sort(key=lambda t: (t[0], t[1]))
    base["n_papers_eligible"] = base["n_papers_with_xml"] = len(eligible)
    if not eligible:
        base["state"] = "no-papers-with-xml"
        return base
    selected, capped = eligible[:cfg["max_papers"]], eligible[cfg["max_papers"]:]
    for _r, _i, p, _pm, _x in capped:
        p["figures"] = {"state": "not-selected (paper-cap)", "n": 0, "items": [], "ledger": None}
    base["n_papers_selected"] = len(selected)
    dir_state = cache_dir_state(cache_root)          # ahora sí: hay algo que bajar → se crea (parents) y se mide
    base["cache"]["dir_state"] = dir_state

    t0 = clock()
    deadline = t0 + float(cfg["budget_s"])
    n_run = 0
    all_items = []
    for _r, _i, p, pmcid, xml_path in selected:
        evidence_id = p.get("evidence_id")
        try:
            xml_text = xml_path.read_text(encoding="utf-8", errors="replace")
            parsed = parse_jats(xml_text, pmcid, caption_chars=cfg["caption_chars"], prose_license=cfg["prose_license"])
            search_lic = search_license_of(p) if search_license_of else (p.get("search_rec") or {}).get("license")
            lic = parse_license(xml_text, search_license=search_lic, prose_ok=cfg["prose_license"])
        except Exception as e:  # XML ilegible → paper declarado, la corrida sigue
            p["figures"] = {"state": "attached", "n": 0, "items": [],
                            "ledger": {"mechanism": MECHANISM, "status": "error", "error": f"{type(e).__name__}: {str(e)[:200]}",
                                       "error_kind": "xml-unreadable", "n_wanted": 0, "n_extracted": 0, "n_missing": 0}}
            base["papers"].append({"pmcid": pmcid, "evidence_id": evidence_id, "n_figs_in_xml": 0, "error": p["figures"]["ledger"]["error"]})
            continue
        figs = parsed["figs"]
        room_run = max(0, cfg["max_per_run"] - n_run)
        n_take = min(len(figs), cfg["max_per_paper"], room_run)
        to_fetch, rest = figs[:n_take], figs[n_take:]
        n_run += n_take
        if on_event:
            on_event("paper", {"pmcid": pmcid, "evidence_id": evidence_id, "phase": "start", "heartbeat": True,
                               "n_figs_in_xml": len(figs), "n_selected": n_take})
        fetched = fetch_figures(pmcid, to_fetch, cfg=cfg, cache_root=cache_root, deadline=deadline, clock=clock, now=now,
                                dir_state=dir_state)
        led, by_href = fetched["ledger"], fetched["by_href"]
        base["cache"]["evicted_n"] += int(led.get("evicted_n") or 0)
        excerpt = _norm_ws(p.get("text_excerpt"))
        items = []
        for k, f in enumerate(figs):
            fig_lic = f.get("fig_license") if f.get("fig_permissions_present") and f.get("fig_license") else None
            lic_f = fig_lic or lic
            flags = license_flags(lic_f["id"], cfg)
            href = f.get("graphic_href")
            key = os.path.basename(str(href)).lower() if href else f"__nohref__{f.get('fig_id')}"
            row = by_href.get(key) if k < n_take else None
            if k >= n_take:
                reason = "paper-cap" if k >= cfg["max_per_paper"] else "run-cap"
                row = {"bytes_state": _not_fetched(reason), "mime_from_extension": mime_from_extension(href)}
                if not href:
                    row["bytes_state"] = _not_fetched("no-graphic")
                elif f.get("caption_state") != "present":
                    row["bytes_state"] = _not_fetched("no-caption")
            if lic_f["id"] == "zfin-display-only":
                row = {"bytes_state": "never (zfin-display-only)"}
            cie = None
            if excerpt and f.get("caption_state") == "present":
                cie = _norm_ws(f.get("caption")) in excerpt
            item = make_item(pmcid, evidence_id, f, lic_f, flags, bytes_row=row, caption_in_excerpt=cie)
            items.append(item)
            if item["bytes_state"] == "verified" and on_event:
                on_event("figure", {"id": item["id"], "sha256": item["sha256"], "media_type": item["media_type"],
                                    "bytes": item["bytes"], "dims_measured": item["dims_measured"],
                                    "dims_match": item["dims_match"], "bytes_state": item["bytes_state"],
                                    "embeddable": item["embeddable"], "panel_view": item["panel_view"], "heartbeat": True})
        paper_ledger = {k: led.get(k) for k in ("mechanism", "status", "http_status", "zip_bytes", "zip_entries_n", "elapsed_s",
                                                 "n_wanted", "n_extracted", "n_missing", "cache_hit", "fetched_at",
                                                 "budget_s", "timeout_s", "evicted_n")}
        for k in ("error", "error_kind", "cache_mismatch_hrefs", "cache_mismatch_refetched", "sha_changed_from_previous_ledger"):
            if led.get(k):
                paper_ledger[k] = led[k]
        paper_ledger["n_entries"] = led.get("zip_entries_n")
        p["figures"] = {"state": "attached", "n": len(items), "items": items, "ledger": paper_ledger}
        all_items.extend(items)
        done = {"pmcid": pmcid, "evidence_id": evidence_id, "phase": "done", "n_figs_in_xml": len(figs), "n_selected": n_take,
                "license": {"id": lic["id"], "source": lic["source"]}, "mechanism": MECHANISM,
                "http_status": led.get("http_status"), "zip_bytes": led.get("zip_bytes"), "elapsed_s": led.get("elapsed_s"),
                "n_extracted": led.get("n_extracted"), "n_missing": led.get("n_missing"), "cache_hit": led.get("cache_hit"),
                "status": led.get("status")}
        if led.get("error"):
            done["error"] = led["error"]
        base["papers"].append(done)
        if on_event:
            on_event("paper", dict(done, heartbeat=True))

    used = max(0.0, clock() - t0)
    base["budget"] = {"total_s": float(cfg["budget_s"]), "used_s": round(used, 3), "over_budget": used > float(cfg["budget_s"])}
    base["items"] = all_items
    base["n_figures"] = len(all_items)
    base["n_with_caption"] = sum(1 for i in all_items if i["caption_state"] == "present")
    base["n_verified"] = sum(1 for i in all_items if i["bytes_state"] == "verified")
    base["n_mismatch"] = sum(1 for i in all_items if i["bytes_state"] == "mismatch")
    base["n_fetched"] = base["n_verified"] + base["n_mismatch"]
    # corrector (B.2/E): n_not_fetched = SOLO 'not-fetched (…)'; los 'error: <tipo>: <msg>' van APARTE en n_error (antes se sumaban
    # a n_not_fetched y n_figures ≠ Σ cubetas quedaba sin explicar). n_figures = n_verified + n_mismatch + n_not_fetched + n_error
    # (+ filas 'never (zfin-display-only)', 0 hoy: los ítems ZFIN no ganan figuras).
    base["n_not_fetched"] = sum(1 for i in all_items if str(i["bytes_state"]).startswith("not-fetched ("))
    base["n_error"] = sum(1 for i in all_items if str(i["bytes_state"]).startswith("error: "))
    base["n_embeddable"] = sum(1 for i in all_items if i["embeddable"] and i["bytes_state"] == "verified")
    base["n_panel_view"] = sum(1 for i in all_items if i["panel_view"] and i["bytes_state"] == "verified"
                               and i["caption_state"] == "present")
    base["n_unknown_license"] = sum(1 for i in all_items if (i["license"] or {}).get("id") == "unknown")
    base["state"] = "attached"
    if bundle is not None:
        bundle["figures_ledger"] = base
    return base


# ---------------------------------------------------------------------------------------------------------
# (G.2) selección para el panel + (G.3) bloques por transporte
# ---------------------------------------------------------------------------------------------------------
def select_for_panel(items, cache_root, cfg=None, cited_ns=None):
    """Lo que UNA lente con visión puede ver: ítems con panel_view True ∧ bytes_state 'verified' ∧ caption 'present',
    en orden DETERMINISTA — citadas por la respuesta primero (menor n), luego el orden de `items` (= selection_rank del
    paper, luego orden de documento) —, tope max_per_lens, cada una ≤ max_image_mb crudos, b64 acumulado ≤ 8 MB por
    petición. Los bytes se LEEN de la caché y el sha se RECALCULA (≠ → excluida 'mismatch', declarada; jamás se envía
    un byte que no cuadre). `cited_ns` = {id: [n…]} opcional (si falta se usa item.cited_by_answer).
    Devuelve {figures [{PANEL_FIGURE_KEYS}], n_eligible, n_selected, n_dropped_by_request_cap, n_excluded {license,
    bytes_state, caption, size, mismatch, missing, lens_cap}, bytes_b64_total, rule}."""
    cfg = cfg or env_config()
    cited_ns = cited_ns or {}
    excl = {"license": 0, "bytes_state": 0, "caption": 0, "size": 0, "mismatch": 0, "missing": 0, "lens_cap": 0}
    cands = []
    for pos, it in enumerate(items or []):
        if not it.get("panel_view"):
            excl["license"] += 1
            continue
        if it.get("bytes_state") != "verified":
            excl["bytes_state"] += 1
            continue
        if it.get("caption_state") != "present":
            excl["caption"] += 1
            continue
        ns = cited_ns.get(it.get("id")) or it.get("cited_by_answer") or []
        ns = [n for n in ns if isinstance(n, int)]
        cands.append((0 if ns else 1, min(ns) if ns else 0, pos, it))
    cands.sort(key=lambda t: (t[0], t[1], t[2]))
    max_raw = float(cfg["max_image_mb"]) * 1024 * 1024
    req_cap = REQUEST_B64_MB * 1024 * 1024
    out, b64_total, dropped = [], 0, 0
    for _c, _n, _pos, it in cands:
        if len(out) >= int(cfg["max_per_lens"]):
            excl["lens_cap"] += 1
            continue
        if (it.get("bytes") or 0) > max_raw:
            excl["size"] += 1
            continue
        chk = verify_cached(cache_root, it)
        if chk["state"] == "missing":
            excl["missing"] += 1
            continue
        if chk["state"] == "mismatch":
            excl["mismatch"] += 1
            continue
        data = Path(chk["path"]).read_bytes()
        if len(data) > max_raw:
            excl["size"] += 1
            continue
        b64 = base64.b64encode(data).decode("ascii")
        if b64_total + len(b64) > req_cap:
            dropped += 1
            continue
        b64_total += len(b64)
        out.append({"id": it["id"], "fig_id": it["fig_id"], "label": it.get("label"), "caption": it.get("caption") or "",
                    "license": {"id": (it.get("license") or {}).get("id")}, "sha256": it["sha256"],
                    "media_type": it.get("media_type"), "b64": b64, "dims_measured": it.get("dims_measured")})
    return {"figures": out, "n_eligible": len(cands), "n_selected": len(out), "n_dropped_by_request_cap": dropped,
            "n_excluded": excl, "bytes_b64_total": b64_total, "rule": SELECTION_RULE}


def figure_text_label(k, fig):
    """Rótulo corto ANTES de cada imagen (recomendación verbatim de la doc de Anthropic: 'Image 1:' …)."""
    label = fig.get("label") or "no label"
    return f"Figure {k} — {fig['id']} ({label}): {fig.get('caption') or ''}"


def anthropic_blocks(figures, user_text, attested_blocks=None):
    """Anthropic Messages `content` (forma verificada en el ADR, Context 8): imágenes ANTES del texto, cada una con su
    rótulo → [{type text}, {type image, source {type base64, media_type, data}}] × N + [{type text, text: user_text}].

    ADR-0086 (F3): `attested_blocks` (ya construidos por attestations.anthropic_attested_blocks — este módulo NO importa
    attestations) se INSERTA entre las figuras y el texto, detrás de su propio separador: las imágenes que aportó una
    persona nunca se mezclan con las figuras de los papers ni se confunden con evidencia. Sin ellos, la forma es byte a
    byte la de 1.12."""
    blocks = []
    for k, f in enumerate(figures or [], start=1):
        blocks.append({"type": "text", "text": figure_text_label(k, f)})
        blocks.append({"type": "image", "source": {"type": "base64", "media_type": f["media_type"], "data": f["b64"]}})
    blocks.extend(attested_blocks or [])
    blocks.append({"type": "text", "text": user_text})
    return blocks


def openai_responses_parts(figures, user_text, detail=None, attested_parts=None):
    """OpenAI Responses `input[0].content` (forma verificada): [{input_text}, {input_image, image_url data:…, detail}] × N
    + [{input_text: user_text}]."""
    detail = detail or env_config()["openai_detail"]
    parts = []
    for k, f in enumerate(figures or [], start=1):
        parts.append({"type": "input_text", "text": figure_text_label(k, f)})
        parts.append({"type": "input_image", "image_url": f"data:{f['media_type']};base64,{f['b64']}", "detail": detail})
    parts.extend(attested_parts or [])      # ADR-0086 (F3): lo atestiguado va tras las figuras y antes del texto
    parts.append({"type": "input_text", "text": user_text})
    return parts


def openai_chat_parts(figures, user_text, detail=None, attested_parts=None):
    """OpenAI Chat Completions `messages[1].content` — forma pública conocida, declarada 'public form; not re-verified by
    doc in this work' (Context 8; LG4 la mide): [{text}, {image_url {url data:…, detail}}] × N + [{text: user_text}]."""
    detail = detail or env_config()["openai_detail"]
    parts = []
    for k, f in enumerate(figures or [], start=1):
        parts.append({"type": "text", "text": figure_text_label(k, f)})
        parts.append({"type": "image_url", "image_url": {"url": f"data:{f['media_type']};base64,{f['b64']}", "detail": detail}})
    parts.extend(attested_parts or [])      # ADR-0086 (F3): lo atestiguado va tras las figuras y antes del texto
    parts.append({"type": "text", "text": user_text})
    return parts


OPENAI_CHAT_FORM_STATE = "public form; not re-verified by doc in this work"


def servable_state(item, cache_root, cfg=None):
    """(I) medido al pedir GET /runs/{id}/figures: 'kill-switch' | 'forbidden-by-license' | 'no-bytes' |
    'bytes-not-in-cache' | 'bytes-mismatch' | 'yes' (existencia + sha recalculado)."""
    cfg = cfg or env_config()
    if not cfg["figures"]:
        return "kill-switch"
    if not item.get("embeddable"):
        return "forbidden-by-license"
    if not item.get("sha256") or not item.get("cache_path_rel"):
        return "no-bytes"           # jamás se bajó (not-fetched / never): no hay sha congelado que verificar
    chk = verify_cached(cache_root, item)   # un ítem congelado 'mismatch' o alterado después → el sha RECALCULADO decide
    if chk["state"] == "missing":
        return "bytes-not-in-cache"
    if chk["state"] == "mismatch":
        return "bytes-mismatch"
    return "yes"


def public_item(item):
    """FigureItem para el índice HTTP (I): SIN b64 ni cache_path (nunca los trae) — copia con las llaves del contrato."""
    return {k: item.get(k) for k in FIGURE_ITEM_KEYS if k not in ("cache_path_rel",)}


# ---------------------------------------------------------------------------------------------------------
# CLI mínimo (offline): --parse <xml> --pmcid PMCID | --license <xml> [--search-license 'cc by']
# ---------------------------------------------------------------------------------------------------------
def main():
    import argparse
    ap = argparse.ArgumentParser(description="ADR-0083 figures — lectores offline del XML JATS cacheado")
    ap.add_argument("--parse", help="ruta a un *_fulltext.xml")
    ap.add_argument("--license", help="ruta a un *_fulltext.xml (sólo licencia)")
    ap.add_argument("--pmcid", default="PMC0")
    ap.add_argument("--search-license", default=None)
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if a.parse:
        xml = Path(a.parse).read_text(encoding="utf-8", errors="replace")
        out = parse_jats(xml, a.pmcid)
        out["license"] = parse_license(xml, a.search_license)
    elif a.license:
        out = parse_license(Path(a.license).read_text(encoding="utf-8", errors="replace"), a.search_license)
    else:
        ap.error("pass --parse or --license")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

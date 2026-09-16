"""
web_locator.py — el LOCALIZADOR web de la Ruta B (ADR-0084, rebanadas (B) e (I); contrato 1.13).

Doctrina (CLAUDE.md §6, brief v3 §6.4, ADR-0084): **la web LOCALIZA, jamás es fuente.** Un buscador devuelve URLs;
este módulo las convierte en IDENTIFICADORES por una TABLA CERRADA de patrones por host (RESOLVER_RULES, determinista,
sin red) y deja lo demás declarado como `unresolved[]` con su razón. Ningún título, snippet ni URL de la web entra al
bundle de evidencia, al prompt del sintetizador, al panel, al consejo ni a `answer.gap_flags`: las URLs viven SÓLO en el
ledger `frozen.web_locator` (lectura humana y PDF) y el `title_web` (≤ 120) SÓLO en `unresolved[]`, rotulado. Los
identificadores de literatura los MATERIALIZA la familia web del harness (W3) en la MISMA ronda vía Europe PMC
(`fetch_paper._resolve_one`, una GET sin escribir caché) — este módulo sólo entrega el ident en la forma que
`_ident_query` acepta (`epmc_ident`).

Qué vive aquí (B):
  * RESOLVER_RULES — tabla ordenada (la primera regla que casa gana): doi-org-path · pubmed-path · ncbi-pubmed-legacy ·
    pmc-path · ncbi-pmc-legacy · europepmc-path · biorxiv-doi (label 'preprint') · zfin-curie · ensembl-ensdarg ·
    uniprot-acc · geo-gse · doi-in-url-any-host (confidence 'pattern-only'; WITT_WEB_GENERIC_DOI_RULE, default 1).
  * resolve_url / resolve_urls — sin red, serializable, byte a byte determinista; lista blanca WITT_WEB_ALLOWED_HOSTS
    que RESTRINGE (nunca amplía); dedup dentro de la respuesta y contra `existing_ids` (el pool de ADR-0078);
    `store_state` para ENSDARG/UniProt vía resolve_id (DATA INAMOVIBLE, sólo lectura, 0 red).
  * provider_state — la disponibilidad, leída EN LA LLAMADA (M.4): WITT_WEB_LOCATOR ∈ brave|anthropic|off; sin env →
    brave si hay BRAVE_API_KEY, off si no. `off` (explícito o derivado) → `unavailable_reason` EXACTO
    'tool-unavailable (ADR-0084)' — byte-idéntico al literal de 7d9ce15 (kill-switch (L)).
  * env_config — las 17 env WITT_* de la tabla del ADR con default declarado, tolerantes (basura → default con
    `default-invalid-env:<VAR>`; fuera de rango → clamp declarado en `clamped`).
  * locate — la SECUENCIA ÚNICA por consulta: caché del tool (sin red) → reservar cuota (UPDATE condicional en db,
    inyectado como `quota_fn`) → llamar al proveedor → resolver → registrar. Devuelve la fila-query que W3 pone en el
    ledger de la familia y W7 congela en `frozen.web_locator.queries[]`.
  * cost_of — USD PROYECTADO por consultas facturables (clase 'proyección') + tokens MEDIDOS del alterno.
  * Alterno Anthropic `web_search` (I): caller PROPIO (`composite_auditor._anthropic_tool_call` FUERZA tool_choice, y un
    server-tool no se fuerza), server-tool `web_search_20250305` con `allowed_domains` y `max_uses`, rol
    `elicitation` de la tabla única (NINGÚN rol nuevo: `panel_signature` itera PIPELINE_ROLES). Se parsean SÓLO URLs
    (`web_search_tool_result` + `citations[].url`), `usage.server_tool_use.web_search_requests` y los tokens; TODO texto
    del modelo, `encrypted_content`, `encrypted_index` y `cited_text` se DESCARTAN sin persistir. Propiedad DECLARADA:
    en ese camino el modelo despachador LEE texto web (los resultados cuentan como tokens de entrada) — por eso es
    alterno EXPLÍCITO (WITT_WEB_LOCATOR=anthropic), sin auto-failover, y no es «operativo» hasta LG5.

Cero red en este módulo salvo `_post_json` (ÚNICA costura del alterno; el smoke la parchea) — el proveedor Brave vive
en `.tooluniverse/tools/brave_web_search.py` (W1) y se carga por ruta. stdlib puro al importar: los imports de `lib.*`
son perezosos (W3 importa este módulo al construir cada plan).
"""
import hashlib
import importlib.util
import inspect
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2].parent
_TU_WORKSPACE = ROOT / ".tooluniverse" / "tools"
_LIB_PARENT = str(ROOT / "analysis" / "scripts")
if _LIB_PARENT not in sys.path:
    sys.path.insert(0, _LIB_PARENT)

MODULE_VERSION = "wl-1"
RESOLVER_VERSION = "wlr-2"   # corrector ADR-0084: sufijos de publisher recortados, PMC case-insensitive, europepmc /articles/
ADR = "ADR-0084"
BRAVE_TOOL_MODULE = "brave_web_search.py"      # W1; se carga por ruta (patrón search_harness._load_tool)
BRAVE_TOOL_FN = "locate"
BRAVE_TOOL_VERSION_ATTR = "TOOL_VERSION"       # 'bws-1' cuando el módulo existe; None si no

# ---------------------------------------------------------------------------------------------------------
# Vocabularios CERRADOS (B.7) — viajan congelados; la webapp y el gate de paridad los leen de aquí.
# ---------------------------------------------------------------------------------------------------------
PROVIDERS = ("brave", "anthropic", "off")
PROVIDER_SOURCES_EXACT = ("env:WITT_WEB_LOCATOR", "default-derived:BRAVE_API_KEY present",
                          "default-derived:BRAVE_API_KEY absent", "default-invalid-env:WITT_WEB_LOCATOR")
PROVIDER_SOURCE_PREFIXES = ("env:", "default-derived:", "default-invalid-env:")

# Literales de `unavailable_reason` (B.3). El primero es el de 7d9ce15 (search_harness.SEARCH_DISPATCH['web']) y debe
# seguir byte-idéntico bajo `off`: families_excluded[].reason, harness_state y /council/demand lo reproducen.
UNAVAILABLE_OFF = "tool-unavailable (ADR-0084)"
UNAVAILABLE_BRAVE_NO_KEY = "tool-unavailable (ADR-0084: BRAVE_API_KEY unset)"
UNAVAILABLE_ANTHROPIC_NO_KEY = "tool-unavailable (ADR-0084: ANTHROPIC_API_KEY unset)"
UNAVAILABLE_ANTHROPIC_DISABLED = "tool-unavailable (ADR-0084: org web_search disabled in Console)"
UNAVAILABLE_INVALID_ENV = "tool-unavailable (ADR-0084: WITT_WEB_LOCATOR invalid)"
UNAVAILABLE_REASONS = (UNAVAILABLE_OFF, UNAVAILABLE_BRAVE_NO_KEY, UNAVAILABLE_ANTHROPIC_NO_KEY,
                       UNAVAILABLE_ANTHROPIC_DISABLED, UNAVAILABLE_INVALID_ENV)
UNAVAILABLE_PREFIX = "tool-unavailable (ADR-0084"

# Estados de fuente (search_harness.SOURCE_STATES, ADR-0080): se duplican como literal para que este módulo no importe
# el harness (el smoke compara ambos). `skipped-cap` + `detail` es la cuota mensual: SIN literal nuevo.
SOURCE_STATES = ("success", "no-match", "error", "skipped-budget", "skipped-cap", "tool-unavailable", "not-requested")

LOCATED_KINDS = ("pmid", "pmcid", "doi", "zfin-curie", "ensdarg", "uniprot", "gse")
LITERATURE_KINDS = ("pmid", "pmcid", "doi")               # los que W3 materializa por Europe PMC
CONFIDENCES = ("host-table", "pattern-only")
UNRESOLVED_REASONS = ("no-identifier-pattern", "host-not-allowed", "unsupported-scheme", "malformed-url")
DEDUP_STATES = (None, "duplicate-in-response", "already-present (existing_ids)")
STORE_STATES_EXACT = ("in-store (RAW)", "in-store (DERIVED)", "not-in-store")
STORE_STATE_PREFIXES = ("store-unavailable (",)          # el store no se pudo leer: se declara, no se finge ausencia

WEB_STATES_EXACT = ("located", "no-results", "not-requested (no web directive)", "not-requested (no search round)",
                    "kill-switch WITT_WEB_LOCATOR=off")
WEB_STATE_PREFIXES = ("tool-unavailable (ADR-0084", "skipped-cap (", "skipped-budget (", "error: ")
WEB_KILL_SWITCH_STATE = "kill-switch WITT_WEB_LOCATOR=off"

FED_TO = ("pool:literature-candidate (materialized by europepmc)", "ctx:dois", "ctx:curies", None)
FEED_STATES_EXACT = ("materialized-same-round", "fed-same-round", "already-present", "duplicate-in-response",
                     "not-found-in-europepmc", "not-materialized (feed cap)", "not-materialized (budget)",
                     "no-sink-in-1.13")
FEED_STATE_PREFIXES = ("already-present (dup of ", "no-sink-in-1.13 (", "error: ")

QUOTA_STATES_EXACT = ("under-cap", "cap-reached", "not-enforced (no quota callable)",
                      "disabled (WITT_WEB_MONTHLY_CAP=0)", "not-consumed (cache-hit)")
QUOTA_RULE = ("local counter of queries SENT by this deployment (UTC calendar month): ONE reservation per query BEFORE the "
              "network call; billable requests per query may exceed 1 (a 429 retry, anthropic max_uses) and are added AFTER the "
              "call as n_requests_extra, so the monthly row can exceed the cap by that declared delta; CLI probes do not count; "
              "the provider dashboard is the truth of the balance; provider cycle attested in LG0")

TEXT_POLICY = ("no web text enters the bundle, the prompt, the events or the answer: results carry url/title/age only; "
               "description and extra_snippets are dropped at the tool output; title_web lives only in unresolved[] "
               "of this ledger")
WEB_LOCATOR_RULE = ("the web LOCATES identifiers and is never a source (ADR-0084): URLs resolve by a closed host-pattern "
                    "table (RESOLVER_RULES) to PMID/PMCID/DOI/ZFIN/ENSDARG/UniProt/GSE; literature ids are materialized "
                    "in the same round by Europe PMC (fetch_paper._resolve_one) and enter the pool as source "
                    "'europepmc' / source_family 'web' / identifier_provenance 'web-located:<rule>'; unresolved URLs are "
                    "declared and counted here, never cited; 0 items with source 'web' by construction")
IDENTIFIER_PROVENANCE_PREFIX = "web-located:"
# Cortacircuito de autenticación (C.5, hueco del juez 1): W3 deja las consultas restantes de la ronda en skipped-cap.
AUTH_ERROR_PREFIX = "auth"

EPMC_IDENT_RE = re.compile(r"^(PMID:\d+|PMC\d+|DOI:10\.\S+)$")   # Context 4: SÓLO estas formas van a _resolve_one
_DOI_TRAILING_PUNCT = ".,;:)]/"
# corrector ADR-0084: segmentos de ruta y extensiones que los publishers cuelgan DESPUÉS del DOI (Frontiers /full, Springer .pdf,
# /figures/1, Wiley /abstract, biorxiv .article-info …) — jamás son parte del DOI; se recortan ANTES de validar la forma
_DOI_PATH_SUFFIX_RE = re.compile(r"(/(?:full|pdf|epdf|abstract|fulltext|full-text|html|meta|metrics|references|citedby|"
                                 r"supplementary-material|suppl|epub|figures(?:/\d+)?|tables(?:/\d+)?))+$", re.I)
_DOI_EXT_SUFFIX_RE = re.compile(r"\.(?:pdf|epdf|full|abstract|full-text|fulltext|html|xml|epub|article-info|article-metrics|"
                                r"supplementary-material|figures-only)$", re.I)

# (B.8) Precedente agéntico 2026-05-14 — regularizado: NO admisible, no se lee, no se muta ni se borra (K).
NOT_ADMISSIBLE_STATE = "not-admissible (agentic web cache; no source-pointer per claim; ADR-0062/0084)"
NOT_ADMISSIBLE_PRECEDENTS = (
    {"file": "mcp_cache/literature_pronephros_essentiality_20260514.json",
     "query_method": "WebSearch + WebFetch on PMC articles", "state": NOT_ADMISSIBLE_STATE},
    {"file": "mcp_cache/literature_pronephros_proteomics_20260514.json",
     "query_method": "WebSearch + WebFetch", "state": NOT_ADMISSIBLE_STATE},
)

# ---------------------------------------------------------------------------------------------------------
# Precios (B.6) — insumo de la PROYECCIÓN; verificados 2026-09-16 (ADR-0084 Context 9 y 10). Cambian sólo con ADR.
# ---------------------------------------------------------------------------------------------------------
PRICE_AS_OF = "2026-09-16"
PROVIDER_PRICES_USD_PER_1K = {"brave": 5.0, "anthropic": 10.0}
PROVIDER_PRICE_SOURCE_URL = {
    "brave": "https://brave.com/search/api/ (plan Search: $5 per 1,000 requests; $5 free credits per month)",
    "anthropic": "https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool "
                 "($10 per 1,000 searches, plus standard token costs)",
}
COST_CLASS = "proyección"
TOKENS_CLASS = "medición"

# ---------------------------------------------------------------------------------------------------------
# Anthropic (I): literales propios si composite_auditor no importa (misma URL/versión que ese módulo).
# ---------------------------------------------------------------------------------------------------------
ANTHROPIC_URL_FALLBACK = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION_FALLBACK = "2023-06-01"
ANTHROPIC_TOOL_NAME = "web_search"
ANTHROPIC_MAX_TOKENS = 256
ANTHROPIC_SYSTEM = ("You are a search dispatcher: call web_search exactly once with the query verbatim; do not answer, "
                    "do not summarize.")
ANTHROPIC_IDENTIFIER_PROVENANCE = "anthropic-web-search"
ANTHROPIC_ALLOWED_DOMAINS_MAX = 20
ANTHROPIC_READS_WEB_TEXT = ("the dispatcher model READS web text on this path: search results are counted as input "
                            "tokens by the provider even though this caller discards every text block (ADR-0084 (I))")
ANTHROPIC_TOOL_RESULT_ERRORS = ("too_many_requests", "invalid_tool_input", "max_uses_exceeded", "query_too_long",
                                "request_too_large", "unavailable")
# corrector ADR-0084: el ÚNICO tipo de server-tool admitido (básico, sin dynamic filtering). web_search_20260209/20260318 (código +
# modelo filtrando resultados) están en «Qué NO se hace»: entran por ADR, jamás por env.
ANTHROPIC_TOOL_TYPES = ("web_search_20250305",)
# llaves de la fila-proveedor del alterno que locate() copia a la fila-query (y viajan a frozen.web_locator.queries[]) — la propiedad
# «el modelo LEE texto web» queda declarada en el frozen, no sólo a nivel tool (corrector ADR-0084)
ANTHROPIC_ROW_KEYS = ("tool_type", "provider_property", "n_text_blocks_discarded", "n_fields_discarded", "request_shape",
                      "query_sent_matches_directive", "stop_reason", "max_uses", "allowed_domains")
# Memoria de PROCESO (B.3): un 400 «web search is not enabled» medido deja al alterno no disponible hasta reinicio.
_PROCESS_MEMORY = {"anthropic_disabled": False, "anthropic_disabled_detail": None}

# Indirección para que un smoke fije el reloj sin parchear `time` en todo el proceso.
_monotonic = time.monotonic
_gmtime = time.gmtime


def _reset_process_memory():
    """Sólo para smokes: olvida el 400 «not enabled» medido en este proceso."""
    _PROCESS_MEMORY["anthropic_disabled"] = False
    _PROCESS_MEMORY["anthropic_disabled_detail"] = None


# ---------------------------------------------------------------------------------------------------------
# DOI — la MISMA regla que answer_pipeline._normalize_doi, REPLICADA byte a byte (declarado) para que este módulo no
# importe answer_pipeline (rag_backend, Neo4j, OpenAI) al construir un plan. El smoke mide la paridad.
# ---------------------------------------------------------------------------------------------------------
NORMALIZE_DOI_SOURCE = ("replica of answer_pipeline._normalize_doi (lowercase; strip https://doi.org/ http://doi.org/ "
                        "https://dx.doi.org/ http://dx.doi.org/ doi:) — parity measured in smoke_web_locator")


def normalize_doi(doi):
    """DOI en minúsculas sin prefijo de resolver (https://doi.org/, dx.doi.org, doi:). None si vacío."""
    d = str(doi or "").strip().lower()
    for pre in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if d.startswith(pre):
            d = d[len(pre):]
    return d or None


def _trim_doi(raw):
    """Puntuación final `.,;:)]/` y sufijos de publisher (`/full`, `/pdf`, `.pdf`, `/figures/1`, `.article-info` …) recortados
    de forma ITERATIVA hasta estabilizar, y normalizado (corrector ADR-0084: un DOI con cola de ruta iba a Europe PMC como
    identificador falso, caía 'not-found-in-europepmc' y el paper real se perdía)."""
    s = str(raw or "").strip()
    prev = None
    while s and s != prev:
        prev = s
        while s and s[-1] in _DOI_TRAILING_PUNCT:
            s = s[:-1]
        s = _DOI_PATH_SUFFIX_RE.sub("", s)
        s = _DOI_EXT_SUFFIX_RE.sub("", s)
    return normalize_doi(s)


# ---------------------------------------------------------------------------------------------------------
# (B.1) RESOLVER_RULES — tabla CERRADA, ordenada: la primera que casa gana. `host_pattern` corre sobre el host en
# minúsculas (sin puerto); `id_pattern` sobre `subject` ∈ 'path' (URL-decodificado) | 'path+query' (path + '?' + query,
# URL-decodificados). El grupo nombrado `id` es el identificador crudo; `kind` fija la forma nativa (ver _native_id).
# NO se descarga ninguna página para hallar el DOI (§6.4 descarta el scraping; `doi-from-html-meta` es ADR futuro).
# ---------------------------------------------------------------------------------------------------------
_NCBI_HOST = r"^(www\.)?ncbi\.nlm\.nih\.gov$"
_UNIPROT_ACC = r"(?P<id>[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})(?=[/.?#-]|$)"

RESOLVER_RULES = (
    {"rule_id": "doi-org-path", "host_pattern": r"^(dx\.)?doi\.org$", "subject": "path",
     "id_pattern": r"^/(?P<id>10\.\d{4,9}/[^\s?#]+)", "kind": "doi", "confidence": "host-table",
     "canonical_url": "https://doi.org/{id}", "label": None},
    {"rule_id": "pubmed-path", "host_pattern": r"^pubmed\.ncbi\.nlm\.nih\.gov$", "subject": "path",
     "id_pattern": r"^/(?P<id>\d{4,9})(?:/|$)", "kind": "pmid", "confidence": "host-table",
     "canonical_url": "https://pubmed.ncbi.nlm.nih.gov/{n}/", "label": None},
    {"rule_id": "ncbi-pubmed-legacy", "host_pattern": _NCBI_HOST, "subject": "path",
     "id_pattern": r"^/pubmed/(?P<id>\d{4,9})(?:/|$)", "kind": "pmid", "confidence": "host-table",
     "canonical_url": "https://pubmed.ncbi.nlm.nih.gov/{n}/", "label": None},
    {"rule_id": "pmc-path", "host_pattern": r"^pmc\.ncbi\.nlm\.nih\.gov$", "subject": "path",
     "id_pattern": r"^/articles/(?P<id>[Pp][Mm][Cc]\d+)(?:/|$)", "kind": "pmcid", "confidence": "host-table",
     "canonical_url": "https://europepmc.org/article/PMC/{id}", "label": None},
    {"rule_id": "ncbi-pmc-legacy", "host_pattern": _NCBI_HOST, "subject": "path",
     "id_pattern": r"^/pmc/articles/(?P<id>[Pp][Mm][Cc]\d+)(?:/|$)", "kind": "pmcid", "confidence": "host-table",
     "canonical_url": "https://europepmc.org/article/PMC/{id}", "label": None},
    {"rule_id": "europepmc-path", "host_pattern": r"^(www\.)?europepmc\.org$", "subject": "path",
     # corrector ADR-0084: + la forma legacy REAL europepmc.org/articles/PMC<n> (grupo `id_legacy`, sólo PMC) y PMC en minúsculas
     "id_pattern": r"^/(?:(?:article|abstract)/(?P<src>MED|PMC)/(?P<id>(?:[Pp][Mm][Cc])?\d+)|articles/(?P<id_legacy>[Pp][Mm][Cc]\d+))(?:/|$)",
     "kind": "pmid|pmcid",
     "confidence": "host-table", "canonical_url": "(by kind)", "label": None},
    {"rule_id": "biorxiv-doi", "host_pattern": r"^(www\.)?(biorxiv|medrxiv)\.org$", "subject": "path",
     "id_pattern": r"^/content/(?P<id>10\.\d{4,9}/[^?#/]+?)(?:v\d+)?"
                   r"(?:\.(?:full|abstract|full-text|supplementary-material|article-info|article-metrics))?(?:\.pdf)?/?$",
     "kind": "doi", "confidence": "host-table", "canonical_url": "https://doi.org/{id}", "label": "preprint"},
    {"rule_id": "zfin-curie", "host_pattern": r"^(www\.)?zfin\.org$", "subject": "path+query",
     "id_pattern": r"(?P<id>ZDB-(?:GENE|PUB|FIG|ALT|FISH)-\d{6}-\d+)", "kind": "zfin-curie",
     "confidence": "host-table", "canonical_url": "https://zfin.org/{id}", "label": None},
    {"rule_id": "ensembl-ensdarg", "host_pattern": r"(^|\.)ensembl\.org$", "subject": "path+query",
     "id_pattern": r"(?P<id>ENSDARG\d{11})(?P<ver>\.\d+)?", "kind": "ensdarg", "confidence": "host-table",
     "canonical_url": "https://ensembl.org/Danio_rerio/Gene/Summary?g={id}", "label": None},
    {"rule_id": "uniprot-acc", "host_pattern": r"^(www\.)?uniprot\.org$", "subject": "path",
     "id_pattern": r"^/(?:uniprotkb|uniprot)/" + _UNIPROT_ACC, "kind": "uniprot", "confidence": "host-table",
     "canonical_url": "https://www.uniprot.org/uniprotkb/{id}", "label": None},
    {"rule_id": "geo-gse", "host_pattern": _NCBI_HOST, "subject": "path+query",
     "id_pattern": r"^/geo/query/acc\.cgi\?(?:.*&)?acc=(?P<id>GSE\d+)", "kind": "gse", "confidence": "host-table",
     "canonical_url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={id}", "label": None},
    {"rule_id": "doi-in-url-any-host", "host_pattern": r".*", "subject": "path",
     "id_pattern": r"(?P<id>10\.\d{4,9}/[^\s?#]+)", "kind": "doi", "confidence": "pattern-only",
     "canonical_url": "https://doi.org/{id}", "label": None,
     "env": "WITT_WEB_GENERIC_DOI_RULE"},
)
GENERIC_DOI_RULE_ID = "doi-in-url-any-host"
RULE_IDS = tuple(r["rule_id"] for r in RESOLVER_RULES)
assert len(RULE_IDS) == 12 and len(set(RULE_IDS)) == 12
_RULE_RE = {r["rule_id"]: (re.compile(r["host_pattern"]), re.compile(r["id_pattern"])) for r in RESOLVER_RULES}
# Hosts de la tabla (sin comodín): lista `allowed_domains` del alterno cuando WITT_WEB_ALLOWED_HOSTS está vacía (I).
RESOLVER_TABLE_HOSTS = ("doi.org", "dx.doi.org", "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov",
                        "europepmc.org", "biorxiv.org", "medrxiv.org", "zfin.org", "ensembl.org", "uniprot.org")
ALLOWED_HOSTS_ALL = "all (resolver table + doi-in-url on any host)"
ALLOWED_HOSTS_SEMANTICS = ("WITT_WEB_ALLOWED_HOSTS restricts by host suffix (host == h or host endswith '.h'); it never "
                           "widens the resolver table. For the Anthropic alternate the same list travels as "
                           "allowed_domains (subdomains included by the provider) and the table filters again by host")
RESOLVER_RULE_ORDER = "first matching rule wins (RESOLVER_RULES order); doi-in-url-any-host is last and optional"


def resolver_rules(generic_doi=True):
    """La tabla PÚBLICA para el frozen (G.2 `resolver_rules[]`): {rule_id, host_pattern, id_pattern, kind, confidence,
    label?, enabled}. La regla genérica va con `enabled` según WITT_WEB_GENERIC_DOI_RULE."""
    out = []
    for r in RESOLVER_RULES:
        row = {"rule_id": r["rule_id"], "host_pattern": r["host_pattern"], "id_pattern": r["id_pattern"],
               "kind": r["kind"], "confidence": r["confidence"], "subject": r["subject"],
               "enabled": True if r["rule_id"] != GENERIC_DOI_RULE_ID else bool(generic_doi)}
        if r.get("label"):
            row["label"] = r["label"]
        out.append(row)
    return out


def _native_id(kind, raw, src=None):
    """(kind_final, id nativo, extra) — la forma con la que el pool de ADR-0078 y `_ident_query` casan:
    PMID:<n> | PMC<n> | <doi minúsculas> | ZFIN:ZDB-… | ENSDARG… | <acc> | GSE<n>. None si la forma no cierra."""
    extra = {}
    if kind == "pmid|pmcid":
        kind = "pmcid" if str(raw).upper().startswith("PMC") or src == "PMC" else "pmid"
    if kind == "pmid":
        n = re.sub(r"\D", "", str(raw))
        return kind, (f"PMID:{n}" if n else None), extra
    if kind == "pmcid":
        s = str(raw).upper()
        if re.fullmatch(r"\d+", s):
            s = "PMC" + s          # europepmc.org/article/PMC/<n> sin prefijo: la forma nativa lo lleva
        return kind, (s if re.fullmatch(r"PMC\d+", s) else None), extra
    if kind == "doi":
        d = _trim_doi(raw)
        return kind, (d if d and re.match(r"^10\.\d{4,9}/\S+$", d) else None), extra
    if kind == "zfin-curie":
        return kind, f"ZFIN:{str(raw).upper()}", extra
    if kind == "ensdarg":
        return kind, str(raw).upper(), extra
    if kind == "uniprot":
        return kind, str(raw).upper(), extra
    if kind == "gse":
        return kind, str(raw).upper(), extra
    return kind, None, extra


def _canonical_url(kind, ident, template):
    if kind == "pmid":
        return f"https://pubmed.ncbi.nlm.nih.gov/{ident.split(':', 1)[1]}/"
    if kind == "pmcid":
        return f"https://europepmc.org/article/PMC/{ident}"
    if kind == "doi":
        return f"https://doi.org/{ident}"
    if kind == "zfin-curie":
        return f"https://zfin.org/{ident.split(':', 1)[1]}"
    if kind == "ensdarg":
        return f"https://ensembl.org/Danio_rerio/Gene/Summary?g={ident}"
    if kind == "uniprot":
        return f"https://www.uniprot.org/uniprotkb/{ident}"
    if kind == "gse":
        return f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={ident}"
    return template.replace("{id}", ident)


def _parse_url(url):
    """(ok, host, path_decoded, query_decoded, reason) — sin red. `reason` ∈ UNRESOLVED_REASONS cuando ok False."""
    if not isinstance(url, str) or not url.strip():
        return False, None, None, None, "malformed-url"
    u = url.strip()
    if re.search(r"\s", u):
        return False, None, None, None, "malformed-url"
    try:
        p = urllib.parse.urlsplit(u)
    except ValueError:
        return False, None, None, None, "malformed-url"
    scheme = (p.scheme or "").lower()
    if not scheme:
        return False, None, None, None, "malformed-url"
    if scheme not in ("http", "https"):
        host = (p.hostname or "").lower().rstrip(".") or None
        return False, host, None, None, "unsupported-scheme"
    try:
        host = (p.hostname or "").lower().rstrip(".")
    except ValueError:
        return False, None, None, None, "malformed-url"
    if not host or "." not in host and host != "localhost":
        return False, (host or None), None, None, "malformed-url"
    return True, host, urllib.parse.unquote(p.path or "/"), urllib.parse.unquote(p.query or ""), None


def host_allowed(host, allowed_hosts):
    """Lista blanca por SUFIJO de host (declarado en ALLOWED_HOSTS_SEMANTICS). `allowed_hosts` None/[] = todo permitido."""
    if not allowed_hosts:
        return True
    h = (host or "").lower()
    for a in allowed_hosts:
        a = str(a or "").strip().lower().rstrip(".")
        if not a:
            continue
        if h == a or h.endswith("." + a):
            return True
    return False


def _first_rule(host, path, query, generic_doi):
    for r in RESOLVER_RULES:
        if r["rule_id"] == GENERIC_DOI_RULE_ID and not generic_doi:
            continue
        host_re, id_re = _RULE_RE[r["rule_id"]]
        if not host_re.search(host):
            continue
        subject = path if r["subject"] == "path" else (path + ("?" + query if query else ""))
        m = id_re.search(subject)
        if not m:
            continue
        gd = m.groupdict()
        raw_id = gd.get("id") if gd.get("id") else gd.get("id_legacy")   # corrector: alternativa legacy (europepmc /articles/PMC…)
        if not raw_id:
            continue
        kind, ident, extra = _native_id(r["kind"], raw_id, gd.get("src"))
        if not ident:
            continue
        if r["rule_id"] == "ensembl-ensdarg" and m.groupdict().get("ver"):
            extra["version_stripped"] = m.group("ver")
        return r, kind, ident, extra
    return None, None, None, None


def _title_web(title):
    t = str(title or "").strip()
    return (t[:120] if t else None)


def resolve_url(url, allowed_hosts=None, generic_doi=True, title=None):
    """UNA URL → {'located': {...}} | {'unresolved': {...}} — determinista, sin red, serializable (B.1).
    located = {url, host, id, kind, resolver_rule, confidence, canonical_url, label, version_stripped?};
    unresolved = {url, host, title_web (≤ 120; el ÚNICO lugar donde viaja un título del buscador), reason}."""
    ok, host, path, query, reason = _parse_url(url)
    if not ok:
        return {"unresolved": {"url": url if isinstance(url, str) else repr(url), "host": host,
                               "title_web": _title_web(title), "reason": reason}}
    if not host_allowed(host, allowed_hosts):
        return {"unresolved": {"url": url, "host": host, "title_web": _title_web(title), "reason": "host-not-allowed"}}
    rule, kind, ident, extra = _first_rule(host, path, query, generic_doi)
    if rule is None:
        return {"unresolved": {"url": url, "host": host, "title_web": _title_web(title),
                               "reason": "no-identifier-pattern"}}
    row = {"url": url, "host": host, "id": ident, "kind": kind, "resolver_rule": rule["rule_id"],
           "confidence": rule["confidence"], "canonical_url": _canonical_url(kind, ident, rule["canonical_url"]),
           "label": rule.get("label")}
    row.update(extra)
    return {"located": row}


def existing_id_key(value):
    """Forma NATIVA de un id que ya vive en el pool/bundle (evidence_id de _epmc_candidate, llaves de _candidate_keys,
    ids de la DI): 'PMID:<n>' | 'PMC<n>' | '<doi>' | 'ZFIN:ZDB-…' | 'ENSDARG…' | '<acc>' | 'GSE<n>'. None si no casa."""
    s = str(value or "").strip()
    if not s:
        return None
    up = s.upper()
    if up.startswith("PMID:"):
        n = re.sub(r"\D", "", up[5:])
        return f"PMID:{n}" if n else None
    if re.fullmatch(r"\d{4,9}", s):
        return f"PMID:{s}"
    if up.startswith("PMCID:"):
        v = up[6:].strip()
        return v if re.fullmatch(r"PMC\d+", v) else None
    if re.fullmatch(r"PMC\d+", up):
        return up
    if up.startswith("DOI:") or up.startswith("HTTPS://DOI.ORG/") or up.startswith("HTTP://DOI.ORG/") \
            or up.startswith("HTTPS://DX.DOI.ORG/") or s.startswith("10."):
        return normalize_doi(s if not up.startswith("DOI:") else s[4:])
    if up.startswith("ZFIN:ZDB-") or up.startswith("ZDB-"):
        return "ZFIN:" + up.split(":", 1)[-1]
    if re.fullmatch(r"ENSDARG\d{11}(\.\d+)?", up):
        return up.split(".")[0]
    if re.fullmatch(r"GSE\d+", up):
        return up
    if re.fullmatch(_UNIPROT_ACC.replace("(?P<id>", "(").replace("(?=[/.?#-]|$)", ""), up):
        return up
    return None


def store_state(kind, ident, store=None):
    """'in-store (RAW)' | 'in-store (DERIVED)' | 'not-in-store' | 'store-unavailable (<Exc>)' — SÓLO ensdarg/uniprot,
    vía resolve_id.resolve (DATA INAMOVIBLE, sólo lectura, 0 red). `store` = callable key -> record|NOT_FOUND (default
    resolve_id.resolve, import perezoso). Otros kinds → None (la existencia la confirma la fuente nativa)."""
    if kind not in ("ensdarg", "uniprot"):
        return None
    try:
        if store is None:
            from lib import resolve_id as _rid
            store = _rid.resolve
        rec = store(ident)
    except Exception as e:
        return f"store-unavailable ({type(e).__name__})"
    if not rec:
        return "not-in-store"
    raw_ref = getattr(rec, "raw_cache_ref", None) if not isinstance(rec, dict) else rec.get("raw_cache_ref")
    return "in-store (RAW)" if str(raw_ref or "").startswith("RAW:") else "in-store (DERIVED)"


def resolve_urls(results, allowed_hosts=None, generic_doi=True, existing_ids=(), store=None):
    """(B.2) results[] ({url, title?, host?} o str) → {located[], unresolved[], n_results, n_located, n_unresolved,
    n_duplicates_in_response, n_already_present, n_located_new, resolver_version, allowed_hosts, generic_doi_rule,
    rule_order}. Determinista, sin red, serializable. `located[].dedup` ∈ DEDUP_STATES: la primera aparición de un id
    en la respuesta es la que se alimenta (dedup None); las siguientes quedan declaradas 'duplicate-in-response'; un id
    que ya vive en el pool (`existing_ids`, cualquier forma que existing_id_key entienda) queda 'already-present
    (existing_ids)' — W3 lo cuenta como n_already_present (MEDICIÓN de «la web halló lo que ya teníamos»)."""
    present = set()
    for v in (existing_ids or ()):
        k = existing_id_key(v)
        if k:
            present.add(k)
    located, unresolved, seen = [], [], set()
    n_dup = n_present = 0
    for item in (results or []):
        if isinstance(item, dict):
            url, title = item.get("url"), item.get("title")
        else:
            url, title = item, None
        r = resolve_url(url, allowed_hosts=allowed_hosts, generic_doi=generic_doi, title=title)
        if "unresolved" in r:
            unresolved.append(r["unresolved"])
            continue
        row = r["located"]
        if row["id"] in seen:
            row["dedup"] = "duplicate-in-response"
            n_dup += 1
        elif row["id"] in present:
            row["dedup"] = "already-present (existing_ids)"
            n_present += 1
            seen.add(row["id"])
        else:
            row["dedup"] = None
            seen.add(row["id"])
        st = store_state(row["kind"], row["id"], store=store)
        if st is not None:
            row["store_state"] = st
        located.append(row)
    return {"located": located, "unresolved": unresolved, "n_results": len(results or []),
            "n_located": len(located), "n_unresolved": len(unresolved), "n_duplicates_in_response": n_dup,
            "n_already_present": n_present, "n_located_new": len(located) - n_dup - n_present,
            "resolver_version": RESOLVER_VERSION,
            "allowed_hosts": list(allowed_hosts) if allowed_hosts else ALLOWED_HOSTS_ALL,
            "generic_doi_rule": bool(generic_doi), "rule_order": RESOLVER_RULE_ORDER}


def epmc_ident(located_row):
    """El ident que W3 entrega a fetch_paper._resolve_one — SÓLO 'PMID:<n>' | 'PMC<n>' | 'DOI:<doi>' (Context 4: un
    texto libre ataría el TOP HIT equivocado). None para kinds que no son literatura."""
    kind, ident = located_row.get("kind"), located_row.get("id")
    if kind == "pmid":
        s = ident
    elif kind == "pmcid":
        s = ident
    elif kind == "doi":
        s = f"DOI:{ident}"
    else:
        return None
    return s if EPMC_IDENT_RE.match(s or "") else None


def identifier_provenance(located_row):
    """'web-located:<rule_id>' — la procedencia del candidato materializado (C.5)."""
    return IDENTIFIER_PROVENANCE_PREFIX + str(located_row.get("resolver_rule"))


# ---------------------------------------------------------------------------------------------------------
# (B.4) ENV_SPECS — 17 variables WITT_* con default declarado (tabla del ADR); lector TOLERANTE en tiempo de llamada
# (M.4). `<name>_source` ∈ 'env:<VAR>' | 'default' | 'default-invalid-env:<VAR>'; fuera de rango → clamp DECLARADO en
# `clamped` (el ADR dice «clamp»: se recorta, no se descarta). BRAVE_API_KEY y ANTHROPIC_API_KEY quedan FUERA (secretos:
# sólo su PRESENCIA viaja, en provider_state.key_present). WITT_MCP_CACHE_DIR ya existe (se honra, no se cuenta).
# (name, VAR, default, kind, clamp|choices, reader, effect)
# ---------------------------------------------------------------------------------------------------------
FRESHNESS_RE = re.compile(r"^(pd|pw|pm|py|\d{4}-\d{2}-\d{2}to\d{4}-\d{2}-\d{2})$")
ENV_SPECS = (
    ("locator", "WITT_WEB_LOCATOR", "", "provider", PROVIDERS, "web_locator.provider_state",
     "brave | anthropic | off; vacía = derivado (brave si hay BRAVE_API_KEY, off si no); off = kill-switch (L)"),
    ("max_results", "WITT_WEB_MAX_RESULTS", "10", "int", (1, 20), "brave_web_search.locate",
     "count por consulta (tope documentado 20); anthropic no aplica"),
    ("max_queries", "WITT_WEB_MAX_QUERIES", "3", "int", (1, 10), "search_harness._run_web_family",
     "consultas por ronda; sobrantes skipped-cap en calls[]"),
    ("max_materialize", "WITT_WEB_MAX_MATERIALIZE", "6", "int", (0, 20), "search_harness._run_web_family",
     "ids de literatura verificados en Europe PMC por ronda; 0 = sólo localizar"),
    ("max_query_chars", "WITT_WEB_MAX_QUERY_CHARS", "400", "int", (1, 2000), "brave_web_search.locate",
     "tope NUESTRO de q (Brave no documenta longitud); query_truncated declarado"),
    ("budget_s", "WITT_WEB_BUDGET_S", "30", "float", (1.0, 120.0), "SEARCH_DISPATCH['web'].budget_s",
     "presupuesto de la familia dentro de la ronda (consultas + materialización)"),
    ("min_interval_s", "WITT_WEB_MIN_INTERVAL_S", "1.0", "float", (0.0, 60.0), "net_throttle (api.search.brave.com)",
     "pacing PROPIO (Brave publica 50 qps); throttle.waited_s medido"),
    ("country", "WITT_WEB_COUNTRY", "", "country", None, "brave_web_search.locate",
     "country 2 letras; vacía = no se envía"),
    ("lang", "WITT_WEB_LANG", "en", "lang", None, "brave_web_search.locate",
     "search_lang ISO 639-1; vacía = no se envía"),
    ("freshness", "WITT_WEB_FRESHNESS", "", "freshness", None, "brave_web_search.locate",
     "pd | pw | pm | py | YYYY-MM-DDtoYYYY-MM-DD; fuera de forma = no se envía (freshness_ignored)"),
    ("allowed_hosts", "WITT_WEB_ALLOWED_HOSTS", "", "csv", None, "web_locator.resolve_urls · _anthropic_web_search",
     "CSV que RESTRINGE los resolubles (host fuera = host-not-allowed); anthropic: allowed_domains (<= 20)"),
    ("generic_doi", "WITT_WEB_GENERIC_DOI_RULE", "1", "bool", None, "web_locator.resolve_urls",
     "regla doi-in-url-any-host (pattern-only); 0 = sólo reglas por host"),
    ("monthly_cap", "WITT_WEB_MONTHLY_CAP", "900", "int", (0, 1000000), "db.web_locator_reserve (web_quota)",
     "tope mensual UTC de consultas facturables por proveedor; 0 = sin tope declarado"),
    ("test_query", "WITT_WEB_TEST_QUERY", "", "str", None, "search_harness.build_search_plan",
     "consulta EXPLÍCITA del operador cuando web entra por WITT_SEARCH_DEFAULT_FAMILIES; nunca en producción"),
    ("anthropic_max_uses", "WITT_ANTHROPIC_WEB_SEARCH_MAX_USES", "1", "int", (1, 5), "web_locator._anthropic_web_search",
     "max_uses del server-tool (una directiva = una búsqueda)"),
    ("anthropic_tool_type", "WITT_WEB_ANTHROPIC_TOOL_TYPE", "web_search_20250305", "choice", ANTHROPIC_TOOL_TYPES,
     "web_locator._anthropic_web_search",
     "literal del type del server-tool (vocabulario CERRADO: sólo web_search_20250305, sin dynamic filtering; otro literal = "
     "default + default-invalid-env — 20260209/20260318 quedan fuera por ADR, no por env; corrector ADR-0084)"),
    ("locator_model", "WITT_WEB_LOCATOR_MODEL", "", "model", None, "web_locator._anthropic_web_search",
     "modelo del despachador; validado contra models.MODELS; vacía = models.resolve_role('elicitation')"),
)
ENV_VARS = tuple(s[1] for s in ENV_SPECS)
ENV_DEFAULTS = {s[1]: s[2] for s in ENV_SPECS}
assert len(ENV_SPECS) == 17 and len(set(ENV_VARS)) == 17
ENV_SOURCE_DEFAULT = "default"


def _parse_env(kind, raw, default, clamp):
    """(value, ok, clamped_from). ok False = inválida → default + 'default-invalid-env'; clamped_from = valor crudo
    recortado al rango (ok True, declarado en cfg['clamped'])."""
    s = (raw or "").strip()
    if kind == "provider":
        low = s.lower()
        return (low if low in clamp else None), (low in clamp), None
    if kind == "bool":
        if s in ("0", "1"):
            return s == "1", True, None
        low = s.lower()
        if low in ("true", "yes", "on"):
            return True, True, None
        if low in ("false", "no", "off"):
            return False, True, None
        return default == "1", False, None
    if kind == "int":
        try:
            v = int(float(s))
        except (TypeError, ValueError):
            return int(default), False, None
        if clamp and v < clamp[0]:
            return clamp[0], True, v
        if clamp and v > clamp[1]:
            return clamp[1], True, v
        return v, True, None
    if kind == "float":
        try:
            v = float(s)
        except (TypeError, ValueError):
            return float(default), False, None
        if v != v or v in (float("inf"), float("-inf")):
            return float(default), False, None
        if clamp and v < clamp[0]:
            return clamp[0], True, v
        if clamp and v > clamp[1]:
            return clamp[1], True, v
        return v, True, None
    if kind == "csv":
        toks = [t.strip().lower().rstrip(".") for t in s.split(",") if t.strip()]
        return (toks or None), True, None
    if kind == "str":
        return (s or None), True, None
    if kind == "choice":
        return (s if s in clamp else default), (s in clamp), None
    if kind == "country":
        return (s.upper() if re.fullmatch(r"[A-Za-z]{2}", s) else None), bool(re.fullmatch(r"[A-Za-z]{2}", s)), None
    if kind == "lang":
        return (s.lower() if re.fullmatch(r"[A-Za-z]{2}", s) else None), bool(re.fullmatch(r"[A-Za-z]{2}", s)), None
    if kind == "freshness":
        return (s if FRESHNESS_RE.match(s) else None), bool(FRESHNESS_RE.match(s)), None
    if kind == "model":
        try:
            from lib import models as _models
            known = s in _models.MODELS
        except Exception:
            known = False
        return (s if known else None), known, None
    raise ValueError(kind)


def env_config(env=None):
    """Lee las 17 env EN LA LLAMADA (M.4), tolerante. Devuelve {<name>: valor efectivo, …, 'sources': {<name>:
    'env:<VAR>' | 'default' | 'default-invalid-env:<VAR>'}, 'clamped': {<name>: {raw, value, clamp}}, 'env_vars': [17],
    'cache_dir': Path, 'cache_dir_source': 'env:WITT_MCP_CACHE_DIR' | 'default', 'module_version'}.
    `locator` es la env CRUDA validada (None = derivar); la disponibilidad la decide provider_state()."""
    env = os.environ if env is None else env
    out, sources, clamped = {}, {}, {}
    for name, var, default, kind, clamp, _reader, _effect in ENV_SPECS:
        raw = env.get(var)
        if raw is not None and not str(raw).strip() and kind == "lang":
            # corrector ADR-0084: presente y VACÍA ≠ ausente para `lang` (default no vacío 'en'): el operador APAGA search_lang
            # (la tabla del ADR y brave_web_search ya lo prometían; env_config lo anulaba devolviendo el default)
            v, sources[name] = None, f"env:{var} (empty: not sent)"
        elif raw is None or not str(raw).strip():
            v, _, _ = _parse_env(kind, default, default, clamp)
            sources[name] = ENV_SOURCE_DEFAULT
        else:
            v, ok, clamped_from = _parse_env(kind, str(raw), default, clamp)
            if ok:
                sources[name] = f"env:{var}"
                if clamped_from is not None:
                    clamped[name] = {"raw": clamped_from, "value": v, "clamp": list(clamp)}
            else:
                v, _, _ = _parse_env(kind, default, default, clamp)
                sources[name] = f"default-invalid-env:{var}"
        out[name] = v
    if out["allowed_hosts"]:
        out["allowed_hosts"] = list(out["allowed_hosts"])
    out["sources"] = sources
    out["clamped"] = clamped
    out["env_vars"] = list(ENV_VARS)
    mc = (env.get("WITT_MCP_CACHE_DIR") or "").strip()
    out["cache_dir"] = pathlib.Path(mc) if mc else ROOT / "mcp_cache"
    out["cache_dir_source"] = "env:WITT_MCP_CACHE_DIR" if mc else "default"
    out["module_version"] = MODULE_VERSION
    return out


def allowed_hosts_block(cfg):
    """(G.2) `allowed_hosts {value, source}` para el frozen."""
    return {"value": list(cfg["allowed_hosts"]) if cfg.get("allowed_hosts") else ALLOWED_HOSTS_ALL,
            "source": cfg["sources"]["allowed_hosts"], "semantics": ALLOWED_HOSTS_SEMANTICS}


def generic_doi_block(cfg):
    return {"enabled": bool(cfg["generic_doi"]), "source": cfg["sources"]["generic_doi"], "rule_id": GENERIC_DOI_RULE_ID}


# ---------------------------------------------------------------------------------------------------------
# (B.3) provider_state — UNA verdad de disponibilidad, leída en la llamada (plan, compilación, despacho).
# ---------------------------------------------------------------------------------------------------------
def _key_present(env, var):
    return bool(str(env.get(var) or "").strip())


def provider_state(env=None):
    """{provider ∈ PROVIDERS, provider_source, available: bool, unavailable_reason: str|None, key_present {brave,
    anthropic}, env_raw: str|None, explicit_off: bool}. `off` explícito o derivado → unavailable_reason EXACTO
    'tool-unavailable (ADR-0084)' (el literal de 7d9ce15); brave sin llave → '... BRAVE_API_KEY unset'; anthropic sin
    llave → '... ANTHROPIC_API_KEY unset'; anthropic con 400 «not enabled» medido en el proceso → '... Console'."""
    env = os.environ if env is None else env
    raw = env.get("WITT_WEB_LOCATOR")
    key_brave, key_anth = _key_present(env, "BRAVE_API_KEY"), _key_present(env, "ANTHROPIC_API_KEY")
    explicit_off = False
    if raw is None or not str(raw).strip():
        provider = "brave" if key_brave else "off"
        source = "default-derived:BRAVE_API_KEY present" if key_brave else "default-derived:BRAVE_API_KEY absent"
    else:
        low = str(raw).strip().lower()
        if low in PROVIDERS:
            provider, source = low, "env:WITT_WEB_LOCATOR"
            explicit_off = provider == "off"
        else:
            provider, source = "off", "default-invalid-env:WITT_WEB_LOCATOR"
    available, reason = False, None
    if provider == "off":
        reason = UNAVAILABLE_OFF
    elif provider == "brave":
        if key_brave:
            available = True
        else:
            reason = UNAVAILABLE_BRAVE_NO_KEY
    elif provider == "anthropic":
        if not key_anth:
            reason = UNAVAILABLE_ANTHROPIC_NO_KEY
        elif _PROCESS_MEMORY["anthropic_disabled"]:
            reason = UNAVAILABLE_ANTHROPIC_DISABLED
        else:
            available = True
    return {"provider": provider, "provider_source": source, "available": available, "unavailable_reason": reason,
            "key_present": {"brave": key_brave, "anthropic": key_anth},
            "env_raw": (str(raw) if raw is not None else None), "explicit_off": explicit_off}


def state_when_not_run(ps):
    """El `frozen.web_locator.state` cuando el localizador NO corrió por disponibilidad (G.2): off EXPLÍCITO →
    'kill-switch WITT_WEB_LOCATOR=off'; off DERIVADO por ausencia de llave → 'tool-unavailable (ADR-0084: BRAVE_API_KEY
    unset)' (la CAUSA viaja aquí, no en el plan); env inválida → '... WITT_WEB_LOCATOR invalid)'; brave/anthropic sin
    llave o deshabilitado → su literal. None cuando está disponible (entonces el estado lo decide la corrida)."""
    if ps.get("available"):
        return None
    if ps["provider"] == "off":
        if ps.get("explicit_off"):
            return WEB_KILL_SWITCH_STATE
        if ps["provider_source"] == "default-invalid-env:WITT_WEB_LOCATOR":
            return UNAVAILABLE_INVALID_ENV
        return UNAVAILABLE_BRAVE_NO_KEY
    return ps["unavailable_reason"]


def web_state_in_vocabulary(s):
    return s in WEB_STATES_EXACT or (isinstance(s, str) and s.startswith(WEB_STATE_PREFIXES))


def feed_state_in_vocabulary(s):
    return s in FEED_STATES_EXACT or (isinstance(s, str) and s.startswith(FEED_STATE_PREFIXES))


def quota_state_in_vocabulary(s):
    return s in QUOTA_STATES_EXACT


def store_state_in_vocabulary(s):
    return s in STORE_STATES_EXACT or (isinstance(s, str) and s.startswith(STORE_STATE_PREFIXES))


# ---------------------------------------------------------------------------------------------------------
# (B.6) costo — dos clases, jamás fundidas: consultas facturables × precio unitario = PROYECCIÓN; tokens = MEDICIÓN.
# ---------------------------------------------------------------------------------------------------------
def anthropic_provider_detail(cfg):
    """(corrector ADR-0084) `cost.provider_detail` del alterno: el tipo de server-tool enviado (vocabulario cerrado), su fuente y la
    propiedad declarada de que el modelo despachador LEE texto web en ese camino — la tabla de env del ADR lo prometía y no existía."""
    cfg = cfg or {}
    return {"tool_type": cfg.get("anthropic_tool_type") or ANTHROPIC_TOOL_TYPES[0],
            "tool_type_source": (cfg.get("sources") or {}).get("anthropic_tool_type", "default"),
            "tool_types_allowed": list(ANTHROPIC_TOOL_TYPES), "reads_web_text": True, "property": ANTHROPIC_READS_WEB_TEXT}


def cost_of(provider, n_billable, tokens=None, model=None, provider_detail=None):
    """{provider, n_queries_billable, price_usd_per_1k, price_as_of, price_source_url, usd_projected, class
    'proyección', tokens? {in, out, class 'medición', model?}, tokens_usd_projected?, tokens_price_state?, provider_detail?
    (anthropic: {tool_type, tool_type_source, tool_types_allowed, reads_web_text True, property} — corrector ADR-0084)}."""
    n = int(n_billable or 0)
    price = PROVIDER_PRICES_USD_PER_1K.get(provider)
    out = {"provider": provider, "n_queries_billable": n, "price_usd_per_1k": price, "price_as_of": PRICE_AS_OF,
           "price_source_url": PROVIDER_PRICE_SOURCE_URL.get(provider),
           "usd_projected": round(n * price / 1000.0, 6) if price is not None else 0.0, "class": COST_CLASS}
    if tokens is not None:
        t_in, t_out = int(tokens.get("in") or 0), int(tokens.get("out") or 0)
        out["tokens"] = {"in": t_in, "out": t_out, "class": TOKENS_CLASS}
        if model:
            out["tokens"]["model"] = model
        usd, state = None, "not-priced (no model)"
        if model:
            try:
                from lib import models as _models
                p = _models.prices().get(model)
                if p:
                    usd = round(t_in / 1e6 * p[0] + t_out / 1e6 * p[1], 6)
                    state = f"projected (models.prices, as of {_models.PRICES_AS_OF})"
                else:
                    state = "missing_price (model not in models.MODELS)"
            except Exception as e:
                state = f"not-priced (models import failed: {type(e).__name__})"
        out["tokens_usd_projected"] = usd
        out["tokens_price_state"] = state
    if provider_detail is not None:
        out["provider_detail"] = dict(provider_detail)
    return out


def month_utc(now=None):
    """'YYYY-MM' del mes calendario UTC (la fila de web_locator_usage, (H))."""
    t = _gmtime() if now is None else _gmtime(now)
    return time.strftime("%Y-%m", t)


# ---------------------------------------------------------------------------------------------------------
# Proveedor Brave — cargado por ruta (W1). Ausencia = fila 'error' declarada (código, no configuración).
# ---------------------------------------------------------------------------------------------------------
_BRAVE_CACHE = {}


def _load_brave_tool():
    """(module|None, fn|None, detail) — .tooluniverse/tools/brave_web_search.py por ruta (importlib), cacheado."""
    if "tool" in _BRAVE_CACHE:
        return _BRAVE_CACHE["tool"]
    path = _TU_WORKSPACE / BRAVE_TOOL_MODULE
    if not path.exists():
        result = (None, None, f"{BRAVE_TOOL_MODULE} not found under .tooluniverse/tools (W1)")
    else:
        try:
            mspec = importlib.util.spec_from_file_location(f"_witt_wl_{path.stem}", path)
            mod = importlib.util.module_from_spec(mspec)
            mspec.loader.exec_module(mod)
            fn = getattr(mod, BRAVE_TOOL_FN, None)
            result = (mod, fn, None) if callable(fn) else (mod, None, f"{BRAVE_TOOL_MODULE} has no {BRAVE_TOOL_FN!r}")
        except Exception as e:
            result = (None, None, f"{BRAVE_TOOL_MODULE} not importable: {type(e).__name__}: {str(e)[:160]}")
    _BRAVE_CACHE["tool"] = result
    return result


def brave_tool_version():
    mod, _fn, _d = _load_brave_tool()
    return getattr(mod, BRAVE_TOOL_VERSION_ATTR, None) if mod is not None else None


def _call_with_accepted_kwargs(fn, *args, **kwargs):
    """Llama fn con SÓLO los kwargs que su firma acepta (patrón search_harness: una rebanada paralela decide su firma)."""
    try:
        params = inspect.signature(fn).parameters
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
            return fn(*args, **kwargs)
        return fn(*args, **{k: v for k, v in kwargs.items() if k in params})
    except (TypeError, ValueError):
        return fn(*args, **kwargs)


def _truncate_query(query, cfg):
    q = str(query or "").strip()
    cap = int(cfg.get("max_query_chars") or 400)
    return (q[:cap], True) if len(q) > cap else (q, False)


_CACHE_STAMP_RE = re.compile(r"^raw_brave_.+_(?P<stamp>\d{8})\.json$")


def cache_probe(query, cfg, now=None):
    """(B.5 paso 1) Sonda SIN RED de la caché por día del tool Brave (A.4 `raw_brave_<slug>_<sha8>_<YYYYMMDD>.json`) para
    NO reservar cuota cuando el tool va a servir de caché. Con el tool presente DELEGA en `brave_web_search.cache_probe`
    (slug/sha8 EXACTOS: la sonda dice hit sólo donde el tool leerá; si la tool no va a servir de caché la cuota SÍ se
    reserva). Sin el tool (árbol sin W1 / fakes) cae al escaneo declarado: abre los sobres del día (UTC o local) y compara
    los parámetros de `url` (q, count, country, search_lang, freshness). Un fallo de la sonda se declara y cae a 'miss'
    (la cuota se reserva de más, jamás de menos). → {cache_hit, cache_path, cached_at, probe_method, n_envelopes_scanned}."""
    q_sent, _ = _truncate_query(query, cfg)
    cache_dir = pathlib.Path(cfg.get("cache_dir") or (ROOT / "mcp_cache"))
    mod, _fn, _detail = _load_brave_tool()
    tool_probe = getattr(mod, "cache_probe", None) if mod is not None else None
    fallback_note = ""
    if callable(tool_probe):
        try:
            r = _call_with_accepted_kwargs(tool_probe, q_sent, count=cfg.get("max_results"), country=cfg.get("country"),
                                           search_lang=cfg.get("lang"), freshness=cfg.get("freshness"), cache_dir=str(cache_dir))
            return {"cache_hit": bool((r or {}).get("cache_hit")), "cache_path": (r or {}).get("cache_path"),
                    "cached_at": (r or {}).get("cached_at"), "n_envelopes_scanned": None,
                    "probe_method": "brave_web_search.cache_probe (exact slug/sha8 of the tool; no network, no key)"}
        except Exception as e:
            fallback_note = f"; tool probe raised {type(e).__name__} — fell back to envelope scan"
    want = {"q": q_sent, "count": str(int(cfg.get("max_results") or 10))}
    if cfg.get("country"):
        want["country"] = cfg["country"]
    if cfg.get("lang"):
        want["search_lang"] = cfg["lang"]
    if cfg.get("freshness"):
        want["freshness"] = cfg["freshness"]
    out = {"cache_hit": False, "cache_path": None, "cached_at": None, "n_envelopes_scanned": 0,
           "probe_method": "scan raw_brave_*_<today>.json envelopes and match url params (q,count,country,search_lang,freshness)"
                           + fallback_note}
    if not cache_dir.exists():
        return out
    t = time.time() if now is None else now
    stamps = {time.strftime("%Y%m%d", time.gmtime(t)), time.strftime("%Y%m%d", time.localtime(t))}
    try:
        files = sorted(cache_dir.glob("raw_brave_*.json"))
    except OSError as e:
        out["probe_method"] += f"; glob failed ({type(e).__name__})"
        return out
    for p in files:
        m = _CACHE_STAMP_RE.match(p.name)
        if not m or m.group("stamp") not in stamps:
            continue
        out["n_envelopes_scanned"] += 1
        try:
            env = json.loads(p.read_text(encoding="utf-8"))
            qs = urllib.parse.parse_qs(urllib.parse.urlsplit(env.get("url") or "").query)
            got = {k: (qs.get(k) or [None])[0] for k in ("q", "count", "country", "search_lang", "freshness")}
        except Exception:
            continue
        if all(got.get(k) == v for k, v in want.items()) and all(got.get(k) is None for k in got if k not in want):
            out.update(cache_hit=True, cache_path=str(p), cached_at=env.get("fetched_at"))
            return out
    return out


# ---------------------------------------------------------------------------------------------------------
# (B.5) locate — la SECUENCIA ÚNICA por consulta: caché → reservar → llamar → resolver → registrar.
# ---------------------------------------------------------------------------------------------------------
def _quota_call(quota_fn, provider, month, cap, record=None):
    """quota_fn(provider, month, cap, record=None) -> {granted, n_before, n_after, cap} (db.web_locator_reserve, (H))."""
    if record is None:
        return quota_fn(provider, month, cap)
    return quota_fn(provider, month, cap, record=record)


def _row_base(query, cfg, ps, requirement_ids, round_no, query_source):
    q_sent, truncated = _truncate_query(query, cfg)
    return {"round": round_no, "query_en": str(query or ""), "query_sent": q_sent, "query_source": query_source,
            "requirement_ids": list(requirement_ids or []), "provider": ps["provider"],
            "provider_source": ps["provider_source"], "provider_status": None, "state": None, "http_status": None,
            "elapsed_s": 0.0, "throttle_wait_s": 0.0, "retries_429": 0, "cache_hit": False,
            "query_truncated": truncated, "query_altered_by_provider": False, "n_results": None, "n_located": None,
            "n_unresolved": None, "n_duplicates_in_response": None, "n_already_present": None, "located": [],
            "unresolved": [], "cost_usd_projected": 0.0, "billable": False, "n_billable": 0,
            "quota": {"state": None, "n_after": None, "cap": None, "month": None}, "resolver_version": RESOLVER_VERSION,
            "module_version": MODULE_VERSION}


def _finish(row, status, state=None, error=None, detail=None):
    row["provider_status"] = status
    if error is not None:
        row["error"] = error
    if detail is not None:
        row["detail"] = detail
    if state is None:
        if status == "success":
            state = "located" if (row.get("n_located") or 0) > 0 else "no-results"
        elif status == "no-match":
            state = "no-results"
        elif status == "error":
            state = f"error: {error or 'unknown'}"
        elif status == "skipped-cap":
            state = f"skipped-cap ({detail or ''})"
        elif status == "skipped-budget":
            state = f"skipped-budget ({detail or ''})"
        elif status == "tool-unavailable":
            state = detail if (detail or "").startswith(UNAVAILABLE_PREFIX) else UNAVAILABLE_OFF
    row["state"] = state
    return row


def is_auth_error(row):
    """True cuando la fila-query falló por autenticación (cortacircuito de ronda C.5: sin reintento, cero red)."""
    return row.get("provider_status") == "error" and str(row.get("error") or "").lower().startswith(AUTH_ERROR_PREFIX)


def locate(query, cfg=None, *, provider_fn=None, quota_fn=None, existing_ids=(), store=None, timeout=None,
           requirement_ids=(), round_no=None, query_source=None, env=None, urlopen=None):
    """UNA consulta → fila-query (B.5). Secuencia: (1) provider_state (M.4) — no disponible → 'tool-unavailable', CERO red;
    (2) cache_probe (brave) — hit → la cuota NO se reserva ('not-consumed (cache-hit)'); (3) quota_fn(provider, month,
    cap) ANTES de la red — granted False → 'skipped-cap' con detail, CERO red; sin quota_fn → 'not-enforced (no quota
    callable)'; (4) proveedor: `provider_fn` inyectado (smokes/W3 tools={'web': fake}) | brave_web_search.locate por ruta
    | _anthropic_web_search; una excepción → fila 'error' (§6 no-hang); (5) resolve_urls sobre data.results[]; (6)
    quota_fn(..., record={n_results, cost}) DESPUÉS. Devuelve {round, query_en, query_sent, query_source,
    requirement_ids[], provider, provider_source, provider_status ∈ SOURCE_STATES, state (WEB_STATES literal),
    http_status?, elapsed_s, throttle_wait_s, retries_429, cache_hit, query_truncated, query_altered_by_provider,
    n_results, n_located, n_unresolved, n_duplicates_in_response, n_already_present, located[], unresolved[],
    cost_usd_projected, billable, n_billable, quota {state, n_after, cap, month, n_before?}, cost (B.6), tokens?
    (anthropic), error?, detail?, resolver_version, module_version}. Sin red propia salvo el alterno (_post_json)."""
    env = os.environ if env is None else env
    cfg = cfg or env_config(env)
    ps = provider_state(env)
    row = _row_base(query, cfg, ps, requirement_ids, round_no, query_source)
    cap = int(cfg.get("monthly_cap") or 0)
    month = month_utc()
    row["quota"].update(cap=cap, month=month)
    if not ps["available"]:
        row["quota"]["state"] = None
        return _finish(row, "tool-unavailable", state=state_when_not_run(ps), detail=ps["unavailable_reason"])
    provider = ps["provider"]
    # (2) caché del tool — sin red
    probe = None
    if provider == "brave":
        probe = cache_probe(row["query_sent"], cfg)
        row["cache_probe"] = probe
    reserved = False
    if probe and probe["cache_hit"]:
        row["quota"]["state"] = "not-consumed (cache-hit)"
    elif quota_fn is None:
        row["quota"]["state"] = "not-enforced (no quota callable)"
    else:
        # (3) reservar ANTES de la red — UPDATE condicional atómico en db (H)
        try:
            q = _quota_call(quota_fn, provider, month, cap) or {}
        except Exception as e:
            return _finish(row, "error", error=f"quota callable raised {type(e).__name__}: {str(e)[:120]}")
        row["quota"].update(n_before=q.get("n_before"), n_after=q.get("n_after"), cap=q.get("cap", cap))
        if cap == 0:
            row["quota"]["state"] = "disabled (WITT_WEB_MONTHLY_CAP=0)"
            reserved = True
        elif q.get("granted"):
            row["quota"]["state"] = "under-cap"
            reserved = True
        else:
            row["quota"]["state"] = "cap-reached"
            detail = (f"monthly cap WITT_WEB_MONTHLY_CAP={cap} reached (n_queries={q.get('n_after', q.get('n_before'))}, "
                      f"month {month})")
            return _finish(row, "skipped-cap", detail=detail)
    # (4) proveedor
    t0 = _monotonic()
    try:
        if provider_fn is not None:
            prow = _call_with_accepted_kwargs(provider_fn, row["query_sent"], count=cfg.get("max_results"),
                                              country=cfg.get("country"), search_lang=cfg.get("lang"),
                                              freshness=cfg.get("freshness"), timeout=timeout,
                                              cache_dir=str(cfg.get("cache_dir")) if cfg.get("cache_dir") else None,
                                              cfg=cfg, requirement_ids=list(requirement_ids or []))
        elif provider == "brave":
            _mod, fn, detail = _load_brave_tool()
            if fn is None:
                return _finish(row, "error", error=f"tool-module: {detail}")
            kwargs = {"count": cfg.get("max_results"), "country": cfg.get("country"), "search_lang": cfg.get("lang"),
                      "freshness": cfg.get("freshness"),
                      "cache_dir": str(cfg.get("cache_dir")) if cfg.get("cache_dir") else None}
            if timeout is not None:
                kwargs["timeout"] = timeout
            prow = _call_with_accepted_kwargs(fn, row["query_sent"], **kwargs)
        else:
            prow = _anthropic_web_search(row["query_sent"], cfg, requirement_ids=requirement_ids, timeout=timeout,
                                         env=env, urlopen=urlopen)
    except Exception as e:
        row["elapsed_s"] = round(_monotonic() - t0, 3)
        return _finish(row, "error", error=f"{type(e).__name__}: {str(e)[:160]}")
    row["elapsed_s"] = round(float((prow or {}).get("elapsed_s") or (_monotonic() - t0)), 3)
    prow = prow if isinstance(prow, dict) else {}
    status = prow.get("status")
    if status not in SOURCE_STATES:
        return _finish(row, "error", error=f"shape-mismatch (provider status {status!r} not in SOURCE_STATES)")
    row["http_status"] = prow.get("http_status")
    row["cache_hit"] = bool(prow.get("cache_hit"))
    row["throttle_wait_s"] = float(((prow.get("throttle") or {}).get("waited_s")) or 0.0)
    row["retries_429"] = int(prow.get("retries_429") or 0)
    # el recorte pudo hacerlo esta fila (antes de llamar) o el tool (A.1): cualquiera de los dos lo declara
    row["query_truncated"] = bool(row["query_truncated"] or prow.get("query_truncated"))
    if prow.get("query_sent"):
        row["query_sent"] = prow["query_sent"]
    data = prow.get("data") or {}
    row["query_altered_by_provider"] = bool(data.get("query_altered_by_provider"))
    if prow.get("usage") is not None:
        row["tokens"] = {"in": int((prow["usage"] or {}).get("input_tokens") or 0),
                         "out": int((prow["usage"] or {}).get("output_tokens") or 0), "class": TOKENS_CLASS}
        row["web_search_requests"] = (prow["usage"] or {}).get("web_search_requests")
    if prow.get("model"):
        row["model"] = prow["model"]
        row["model_source"] = prow.get("model_source")
    provider_detail = None
    if provider == "anthropic":
        # corrector ADR-0084: lo que el alterno DECLARA viaja a la fila-query (y al frozen): tipo de tool, forma de la petición,
        # bloques de texto descartados y la propiedad «el modelo LEE texto web»
        for k in ANTHROPIC_ROW_KEYS:
            if k in prow:
                row[k] = prow[k]
        row.setdefault("provider_property", ANTHROPIC_READS_WEB_TEXT)
        provider_detail = anthropic_provider_detail(cfg)
    if status in ("success", "no-match"):
        # (5) resolver — sin red
        res = resolve_urls(data.get("results") or [], allowed_hosts=cfg.get("allowed_hosts"),
                           generic_doi=cfg.get("generic_doi", True), existing_ids=existing_ids, store=store)
        row.update(n_results=res["n_results"], n_located=res["n_located"], n_unresolved=res["n_unresolved"],
                   n_duplicates_in_response=res["n_duplicates_in_response"], n_already_present=res["n_already_present"],
                   located=res["located"], unresolved=res["unresolved"])
        if provider == "anthropic":
            n_bill = int(row.get("web_search_requests") or 0)
        else:
            n_bill = 0 if row["cache_hit"] else int(prow.get("n_http_gets", 1) or 0)
        row["n_billable"], row["billable"] = n_bill, n_bill > 0
        cost = cost_of(provider, n_bill, tokens=row.get("tokens"), model=row.get("model"), provider_detail=provider_detail)
        row["cost"], row["cost_usd_projected"] = cost, cost["usd_projected"]
        # corrector ADR-0084: la cuota reservó UNA por consulta; si el proveedor facturó más peticiones (reintento 429, max_uses > 1)
        # el delta se declara y se suma DESPUÉS a la fila mensual (QUOTA_RULE) — el contador cuenta peticiones facturadas, no consultas
        row["n_requests_extra"] = max(0, n_bill - 1) if reserved else 0
        if reserved and quota_fn is not None:
            # (6) registrar DESPUÉS (n_results / costo / peticiones extra a la fila mensual); un fallo aquí se declara, no tumba la fila
            try:
                _quota_call(quota_fn, provider, month, cap, record={"n_results": res["n_results"], "cost": cost["usd_projected"],
                                                                    "n_requests_extra": row["n_requests_extra"]})
            except Exception as e:
                row["quota"]["record_error"] = f"{type(e).__name__}: {str(e)[:120]}"
        return _finish(row, status, detail=prow.get("detail"))
    # error | skipped-budget | tool-unavailable | skipped-cap del proveedor: sin resolver, sin facturar
    row["cost"] = cost_of(provider, 0, provider_detail=provider_detail)
    err = prow.get("error")
    detail = prow.get("detail") or prow.get("reason")
    if status == "tool-unavailable":
        return _finish(row, status, state=(detail if str(detail or "").startswith(UNAVAILABLE_PREFIX) else None),
                       detail=detail)
    return _finish(row, status, error=(str(err) if err is not None else None), detail=detail)


# ---------------------------------------------------------------------------------------------------------
# (I) Alterno Anthropic web_search — caller PROPIO, una llamada, sólo URLs.
# ---------------------------------------------------------------------------------------------------------
def _anthropic_constants():
    """(url, version, inflight_semaphore|None, source) — de composite_auditor si importa, si no los literales propios."""
    try:
        from lib import composite_auditor as _ca
        return _ca.ANTHROPIC_URL, _ca.ANTHROPIC_VERSION, getattr(_ca, "_INFLIGHT", None), "composite_auditor"
    except Exception:
        return ANTHROPIC_URL_FALLBACK, ANTHROPIC_VERSION_FALLBACK, None, "web_locator literals (composite_auditor not importable)"


def anthropic_allowed_domains(cfg):
    """La lista `allowed_domains` (≤ 20, sin esquema): WITT_WEB_ALLOWED_HOSTS si está, si no los hosts de la tabla del
    resolutor. JAMÁS junto a `blocked_domains` (ambos → 400)."""
    hosts = list(cfg.get("allowed_hosts") or RESOLVER_TABLE_HOSTS)
    out, seen = [], set()
    for h in hosts:
        h = str(h).strip().lower().rstrip(".")
        h = re.sub(r"^https?://", "", h).split("/")[0]
        if h and h not in seen:
            seen.add(h)
            out.append(h)
    return out[:ANTHROPIC_ALLOWED_DOMAINS_MAX]


def anthropic_model(cfg, env=None):
    """(model, source): WITT_WEB_LOCATOR_MODEL validado (env_config) o models.resolve_role('elicitation') — tabla única
    ADR-0081, NINGÚN rol nuevo (panel_signature itera PIPELINE_ROLES)."""
    if cfg.get("locator_model"):
        return cfg["locator_model"], "env:WITT_WEB_LOCATOR_MODEL"
    from lib import models as _models
    r = _models.resolve_role("elicitation", env=env)
    return r["model"], f"models.resolve_role('elicitation') → {r.get('source')}"


def build_anthropic_body(query, cfg, model):
    """El cuerpo EXACTO que se envía (también lo construye smoke_live_web --dry-run): SIN tool_choice (un server-tool no se
    fuerza), SIN allowed_callers (default ['direct'] en 20250305), tools = [web_search con max_uses y allowed_domains]."""
    return {"model": model, "max_tokens": ANTHROPIC_MAX_TOKENS, "system": ANTHROPIC_SYSTEM,
            "messages": [{"role": "user", "content": str(query)}],
            "tools": [{"type": cfg.get("anthropic_tool_type") or "web_search_20250305", "name": ANTHROPIC_TOOL_NAME,
                       "max_uses": int(cfg.get("anthropic_max_uses") or 1),
                       "allowed_domains": anthropic_allowed_domains(cfg)}]}


def _post_json(url, body, headers, timeout, inflight=None, urlopen=None):
    """La ÚNICA costura de red del alterno. → (http_status, payload_json|None, raw_text). Un HTTPError devuelve su
    código y el cuerpo (no lanza); URLError/timeout sí propagan (el llamador los declara 'error')."""
    opener = urlopen or urllib.request.urlopen
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        if inflight is not None:
            with inflight:
                with opener(req, timeout=timeout) as resp:
                    raw = resp.read().decode("utf-8", "replace")
                    return getattr(resp, "status", 200), _json_or_none(raw), raw
        with opener(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return getattr(resp, "status", 200), _json_or_none(raw), raw
    except urllib.error.HTTPError as e:
        raw = ""
        try:
            raw = e.read().decode("utf-8", "replace")
        except Exception:
            pass
        return e.code, _json_or_none(raw), raw


def _json_or_none(raw):
    try:
        return json.loads(raw)
    except Exception:
        return None


def parse_anthropic_response(payload, query_sent):
    """Parsea SÓLO lo que la doctrina permite (I): server_tool_use.input.query, web_search_tool_result.content[].url/title/
    page_age, citations[].url y usage. TODO texto del modelo, encrypted_content, encrypted_index y cited_text se
    DESCARTAN (contados en n_text_blocks_discarded / n_fields_discarded). → {results[], query_model, query_sent_matches,
    n_search_uses, tool_error, n_text_blocks_discarded, n_fields_discarded, stop_reason, usage {input_tokens,
    output_tokens, web_search_requests}, fields_dropped[]}."""
    content = (payload or {}).get("content") or []
    results, seen = [], set()
    query_model, n_uses, tool_error, n_text, n_fields = None, 0, None, 0, 0

    def _add(url, title, page_age):
        nonlocal n_fields
        if not isinstance(url, str) or not url.strip():
            return
        if url in seen:
            return
        seen.add(url)
        host = None
        try:
            host = (urllib.parse.urlsplit(url).hostname or "").lower() or None
        except ValueError:
            pass
        results.append({"url": url, "title": (str(title)[:120] if title else None), "host": host, "age": None,
                        "page_age": page_age})

    for block in content:
        if not isinstance(block, dict):
            continue
        t = block.get("type")
        if t == "server_tool_use" and block.get("name") == ANTHROPIC_TOOL_NAME:
            n_uses += 1
            if query_model is None:
                query_model = ((block.get("input") or {}).get("query"))
        elif t == "web_search_tool_result":
            c = block.get("content")
            if isinstance(c, dict) and c.get("type") == "web_search_tool_result_error":
                tool_error = c.get("error_code") or "unknown"
            elif isinstance(c, list):
                for r in c:
                    if isinstance(r, dict) and r.get("type") == "web_search_result":
                        if "encrypted_content" in r:
                            n_fields += 1
                        _add(r.get("url"), r.get("title"), r.get("page_age"))
        elif t == "text":
            n_text += 1
            for cit in (block.get("citations") or []):
                if isinstance(cit, dict) and cit.get("type") == "web_search_result_location":
                    n_fields += sum(1 for k in ("encrypted_index", "cited_text") if k in cit)
                    _add(cit.get("url"), cit.get("title"), None)
    usage = (payload or {}).get("usage") or {}
    stu = usage.get("server_tool_use") or {}
    return {"results": results, "query_model": query_model,
            "query_sent_matches": (query_model == query_sent) if query_model is not None else None,
            "n_search_uses": n_uses, "tool_error": tool_error, "n_text_blocks_discarded": n_text,
            "n_fields_discarded": n_fields, "stop_reason": (payload or {}).get("stop_reason"),
            "usage": {"input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
                      "web_search_requests": stu.get("web_search_requests")},
            "fields_dropped": ["encrypted_content", "encrypted_index", "cited_text", "text", "thinking"]}


def _anthropic_web_search(query, cfg, requirement_ids=(), *, timeout=None, env=None, urlopen=None):
    """Fila-proveedor del alterno (misma forma que brave_web_search.locate (A)): {status ∈ SOURCE_STATES, query_sent,
    query_truncated, url_sent, elapsed_s, n_http_gets, cache_hit False, api_key_present, http_status?, error?, detail?,
    identifier_provenance 'anthropic-web-search', evidence_kind 'web', model, model_source, tool_type, max_uses,
    allowed_domains, request_shape {has_tool_choice False, has_allowed_callers False, has_blocked_domains False},
    usage {input_tokens, output_tokens, web_search_requests}, n_text_blocks_discarded, n_fields_discarded, stop_reason,
    query_sent_matches_directive, provider_property (ANTHROPIC_READS_WEB_TEXT), data {query_original, query_altered,
    query_altered_by_provider, more_results_available None, count_sent None, n_results, results[] {url, title ≤ 120, host,
    age None, page_age}, fields_dropped[]}}. Sin ANTHROPIC_API_KEY → tool-unavailable, CERO red."""
    env = os.environ if env is None else env
    t0 = _monotonic()
    q_sent, truncated = _truncate_query(query, cfg)
    base = {"status": None, "query_sent": q_sent, "query_truncated": truncated, "elapsed_s": 0.0, "n_http_gets": 0,
            "cache_hit": False, "api_key_present": _key_present(env, "ANTHROPIC_API_KEY"),
            "identifier_provenance": ANTHROPIC_IDENTIFIER_PROVENANCE, "evidence_kind": "web",
            "tool_type": cfg.get("anthropic_tool_type") or "web_search_20250305",
            "max_uses": int(cfg.get("anthropic_max_uses") or 1), "allowed_domains": anthropic_allowed_domains(cfg),
            "provider_property": ANTHROPIC_READS_WEB_TEXT, "requirement_ids": list(requirement_ids or [])}
    if not base["api_key_present"]:
        base.update(status="tool-unavailable", detail=UNAVAILABLE_ANTHROPIC_NO_KEY,
                    reason="ANTHROPIC_API_KEY unset (no request sent)")
        return base
    if _PROCESS_MEMORY["anthropic_disabled"]:
        base.update(status="tool-unavailable", detail=UNAVAILABLE_ANTHROPIC_DISABLED,
                    reason=f"remembered in this process: {_PROCESS_MEMORY['anthropic_disabled_detail']}")
        return base
    try:
        model, model_source = anthropic_model(cfg, env=env)
    except Exception as e:
        base.update(status="error", error=f"model-resolution: {type(e).__name__}: {str(e)[:120]}")
        return base
    base.update(model=model, model_source=model_source)
    body = build_anthropic_body(q_sent, cfg, model)
    base["request_shape"] = {"has_tool_choice": "tool_choice" in body,
                             "has_allowed_callers": any("allowed_callers" in t for t in body["tools"]),
                             "has_blocked_domains": any("blocked_domains" in t for t in body["tools"]),
                             "max_tokens": body["max_tokens"], "n_tools": len(body["tools"])}
    url, version, inflight, const_src = _anthropic_constants()
    base["url_sent"], base["constants_source"] = url, const_src
    headers = {"x-api-key": env.get("ANTHROPIC_API_KEY"), "anthropic-version": version, "content-type": "application/json"}
    try:
        base["n_http_gets"] = 1
        code, payload, raw = _post_json(url, body, headers, timeout if timeout is not None else 60, inflight=inflight,
                                        urlopen=urlopen)
    except Exception as e:
        base.update(status="error", error=f"{type(e).__name__}: {str(e)[:160]}", elapsed_s=round(_monotonic() - t0, 3))
        return base
    base["elapsed_s"], base["http_status"] = round(_monotonic() - t0, 3), code
    if code != 200:
        low = (raw or "").lower()
        if code == 400 and ("web search" in low or "web_search" in low) and "not enabled" in low:
            _PROCESS_MEMORY["anthropic_disabled"] = True
            _PROCESS_MEMORY["anthropic_disabled_detail"] = f"HTTP 400: {raw[:160]}"
            base.update(status="tool-unavailable", detail=UNAVAILABLE_ANTHROPIC_DISABLED, reason=f"HTTP 400: {raw[:160]}")
            return base
        if code == 400 and "allowed_domains" in low:
            base.update(status="error", error="allowed_domains rejected by org policy (HTTP 400)", detail=raw[:200])
            return base
        if code in (401, 403):
            base.update(status="error", error=f"auth (HTTP {code})", detail=raw[:200])
            return base
        base.update(status="error", error=f"HTTP {code}", detail=raw[:200])
        return base
    if payload is None:
        base.update(status="error", error="NonJSONBody (HTTP 200)")
        return base
    parsed = parse_anthropic_response(payload, q_sent)
    base.update(usage=parsed["usage"], n_text_blocks_discarded=parsed["n_text_blocks_discarded"],
                n_fields_discarded=parsed["n_fields_discarded"], stop_reason=parsed["stop_reason"],
                query_sent_matches_directive=parsed["query_sent_matches"], model_reported=payload.get("model"))
    n_req = parsed["usage"].get("web_search_requests")
    base["data"] = {"query_original": q_sent, "query_altered": parsed["query_model"],
                    "query_altered_by_provider": bool(parsed["query_model"] is not None and parsed["query_model"] != q_sent),
                    "more_results_available": None, "count_sent": None, "n_results": len(parsed["results"]),
                    "results": parsed["results"], "fields_dropped": parsed["fields_dropped"]}
    if parsed["tool_error"]:
        base.update(status="error", error=parsed["tool_error"], detail="web_search_tool_result_error (not billed)")
        return base
    if parsed["stop_reason"] == "pause_turn":
        base.update(status="error", error="provider-paused (no continuation by design)")
        return base
    if not n_req:
        base.update(status="no-match", detail="provider-declined-to-search")
        return base
    base["status"] = "success" if parsed["results"] else "no-match"
    return base


# ---------------------------------------------------------------------------------------------------------
# (K) precedente 2026-05-14 — medición, no mutación.
# ---------------------------------------------------------------------------------------------------------
def precedent_state(root=None):
    """[{file, query_method, state, exists}] — los dos cachés agénticos declarados NO admisibles; su existencia se MIDE."""
    root = pathlib.Path(root) if root else ROOT
    return [{**p, "exists": (root / p["file"]).exists()} for p in NOT_ADMISSIBLE_PRECEDENTS]


def frozen_header(cfg=None, env=None):
    """Las constantes de identidad que W7 pone en frozen.web_locator (G.2): versiones, vocabularios, política, regla,
    tabla de reglas, lista blanca y regla genérica — sin correr nada."""
    cfg = cfg or env_config(env)
    return {"module_version": MODULE_VERSION, "resolver_version": RESOLVER_VERSION, "tool_version": brave_tool_version(),
            "state_vocabulary": {"exact": list(WEB_STATES_EXACT), "prefixes": list(WEB_STATE_PREFIXES),
                                 "rule": "state ∈ exact or startswith one of prefixes (web_state_in_vocabulary)"},
            "resolver_rules": resolver_rules(cfg.get("generic_doi", True)),
            "allowed_hosts": allowed_hosts_block(cfg), "generic_doi_rule": generic_doi_block(cfg),
            "text_policy": TEXT_POLICY, "rule": WEB_LOCATOR_RULE, "gate": "directive-only"}

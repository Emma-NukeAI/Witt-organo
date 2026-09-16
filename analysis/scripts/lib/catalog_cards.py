"""
catalog_cards.py — las FICHAS del catálogo de agentes como código (ADR-0082 (A) y (C.1)).

Hasta ADR-0081 el catálogo (`references/agent-catalog.md`, 31 fichas) era prosa que nadie parseaba: el
planner veía nombre + gate + señal (`agent_matrix.digest`) y el consejo de criterio no existía. Este módulo
es un PARSER DETERMINISTA, stdlib puro, que convierte cada `### <agent>` en una ficha con:

  · `text_verbatim` — los BYTES exactos del bloque (desde `### ` hasta el siguiente `### `/`## `, saltos de
    línea del archivo, sin normalizar) y su `sha` = sha256(text_verbatim). La persona lee LA MISMA ficha
    que el agente obedeció (bloque B del system prompt, ver `build_system`).
  · `category` — el `## Category N:` vigente, en vocabulario cerrado (`CATEGORY_VOCABULARY`), con
    `category_raw` verbatim.
  · `name` — el header sin el sufijo `(NEW …)` / `(ADR …)` (`hypothesis-generator`, `composite-auditor`,
    `retrospector`); `header_raw` se conserva.
  · campos por etiqueta negrita: OBLIGATORIOS `purpose, owns, does_not_own, inputs, outputs` (un faltante
    es error de parseo, no un default) y OPCIONALES `substrate_evidence, framework, method, upstream,
    downstream, draft_description` (ausente = llave AUSENTE, jamás '' — tres estados, ADR-0043).

`CATALOG_SHA = sha256('\\n'.join(f'{name}:{sha}' for name in sorted(CARDS)))` viaja en `plans.council_json`,
`frozen.council.catalog_sha` y `GET /council/membership`; editar una ficha NO reescribe ningún registro
(ADR-0074): la siguiente corrida lleva otro sha y la Hoja lo dice (`plan_catalog_matches_run`).

El parser NO sabe de membresía: `agent_matrix.COUNCIL_MEMBERSHIP` (ADR-0082 (B)) decide quién se sienta;
aquí sólo se dice qué dice cada ficha y con qué sha.

El import NUNCA lanza: si el .md falta o no parsea, `CARDS = {}`, `CATALOG_SHA = None` y `CATALOG_STATE`
lo DECLARA (`'errored (...)'`) — el kill-switch `WITT_COUNCIL=0` debe seguir devolviendo el camino de
9d90c01 aunque el catálogo esté roto; `parse()` como función SÍ lanza `CatalogParseError` para quien quiera
estrictez (el smoke).

Prompt del consejo (ADR-0082 (C.1); C2 `council.py` lo re-exporta): `COUNCIL_FIXED_BLOCK` (inglés, sin
fechas ni ids, IDÉNTICO para los 17 — es el prefijo compartido que la caché lee 16×) + `COUNCIL_RULES`
(reglas §7 de CLAUDE.md, texto literal, `RULES_SHA`) y `build_system(card, env)` → dos bloques
`{type:'text', text, cache_control}` (bloque A fijo, bloque B la ficha VERBATIM) con `WITT_COUNCIL_CACHE=1`,
o el string concatenado con `=0` (A/B medible). Lo volátil (pregunta, entidades, ledger, evidencia) va
SIEMPRE en el user message, jamás aquí: `build_system` es una función PURA sin timestamps.

NO-SPEND: sin red, sin BD, sin modelo. Golden: `rag_index/query_service/smoke_catalog_cards.py`.
"""
import hashlib
import json
import os
import pathlib
import re

from lib import agent_matrix   # sólo por MATRIX_PATH: el catálogo es su hermano de carpeta

MODULE_VERSION = "catalog-cards-1"

ROOT = pathlib.Path(__file__).resolve().parents[2].parent
# ADR-0082 (A): CATALOG_PATH = hermano de agent_matrix.MATRIX_PATH
CATALOG_PATH = agent_matrix.MATRIX_PATH.rsplit("/", 1)[0] + "/agent-catalog.md"
CATALOG_PATH_ABS = ROOT / CATALOG_PATH

CARDS_COUNT_GOLDEN = 31          # medido 2026-09-15 @ 9d90c01 (ADR-0082 Context 1)

# Las seis `## Category N:` del catálogo → vocabulario cerrado (ADR-0082 (A)). `category_raw` viaja verbatim.
CATEGORY_VOCABULARY = (
    "compute-simulation",         # ## Category 1: Compute & Simulation
    "wet-lab-experiment",         # ## Category 2: Wet-Lab & Experiment
    "data-omics",                 # ## Category 3: Data & Omics
    "knowledge-strategy",         # ## Category 4: Knowledge & Strategy
    "operations-reporting",       # ## Category 5: Operations & Reporting
    "substrate-instrumentation",  # ## Category 6: Substrate Instrumentation (NEW v2.0)
)
CATEGORY_BY_NUMBER = {i + 1: c for i, c in enumerate(CATEGORY_VOCABULARY)}

REQUIRED_FIELDS = ("purpose", "owns", "does_not_own", "inputs", "outputs")
OPTIONAL_FIELDS = ("substrate_evidence", "framework", "method", "upstream", "downstream", "draft_description")
# etiqueta negrita al inicio de línea → campo. Case-sensitive: el catálogo escribe "Does NOT own".
LABEL_TO_FIELD = {
    "Purpose": "purpose",
    "Owns": "owns",
    "Does NOT own": "does_not_own",
    "Inputs": "inputs",
    "Outputs": "outputs",
    "Substrate evidence": "substrate_evidence",
    "Framework": "framework",
    "Method": "method",
    "Upstream": "upstream",
    "Downstream": "downstream",
}
_DRAFT_LABEL_PREFIX = "Draft description"      # "Draft description (~700 chars)" → draft_description

_HEADER_RE = re.compile(r"^(#{2,3}) (.*)$", re.M)          # `## ` o `### ` al inicio de línea
_CATEGORY_RE = re.compile(r"^Category (\d+):\s*(.*)$")
_SUFFIX_RE = re.compile(r"\s*\((NEW|ADR)[^)]*\)\s*$")     # `(NEW v1.1, PR-01)` · `(NEW v2.2)` · `(NEW v1.1, ADR-0009 — …)`
_LABEL_RE = re.compile(r"^\*\*([^*]+?):\*\*(.*)$")          # `**Label:** resto`


class CatalogParseError(ValueError):
    """El catálogo no cumple la forma que el ADR-0082 (A) exige. Nunca se rellena con defaults."""


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _line_no(text, offset):
    """Número de línea (1-based) del offset de caracteres."""
    return text.count("\n", 0, offset) + 1


def _parse_fields(block_text):
    """Campos por etiqueta negrita. Un campo empieza en `**Label:**` al inicio de línea y termina en la
    siguiente línea en blanco, en la siguiente etiqueta al inicio de línea o al acabar el bloque. Las
    líneas de continuación conservan su sangría (`rstrip` sólo) y se unen con '\\n'. Devuelve
    (fields, labels_raw): `fields` sólo trae las etiquetas CONOCIDAS presentes (ausente = ausente)."""
    fields = {}
    labels_raw = []
    current = None
    buf = []

    def _flush():
        nonlocal current, buf
        if current is not None:
            value = "\n".join(buf).strip()     # continuaciones con su sangría; extremos recortados
            if current not in fields:          # la PRIMERA aparición gana; una segunda se DECLARA
                fields[current] = value
            else:
                fields.setdefault("_duplicates", []).append(current)
        current, buf = None, []

    for raw in block_text.split("\n"):
        line = raw.rstrip("\r")
        m = _LABEL_RE.match(line)
        if m:
            _flush()
            label = m.group(1).strip()
            labels_raw.append(label)
            field = LABEL_TO_FIELD.get(label)
            if field is None and label.startswith(_DRAFT_LABEL_PREFIX):
                field = "draft_description"
            if field is None:
                current = None
                continue
            current = field
            buf = [m.group(2).strip()]
            continue
        if current is None:
            continue
        if line.strip() == "" or line.startswith("### ") or line.startswith("## "):
            _flush()
            continue
        buf.append(line.rstrip())
    _flush()
    return fields, labels_raw


def parse(path=None, text=None):
    """Parsea el catálogo → {name: card}. `text` (str) tiene prioridad sobre `path` (para el golden en
    memoria); sin ambos, lee `CATALOG_PATH_ABS`. Lanza CatalogParseError ante un obligatorio faltante,
    un `### ` fuera de categoría, una categoría fuera de vocabulario o un nombre duplicado."""
    if text is None:
        p = pathlib.Path(path) if path is not None else CATALOG_PATH_ABS
        raw = p.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            raise CatalogParseError(f"utf-8 decode failed at byte {e.start}") from e
        source = str(p)
    else:
        source = "<text>"

    headers = list(_HEADER_RE.finditer(text))
    cards = {}
    category = None
    category_raw = None
    for i, h in enumerate(headers):
        level, title = h.group(1), h.group(2).rstrip("\r")
        if level == "##":
            m = _CATEGORY_RE.match(title)
            if m:
                n = int(m.group(1))
                if n not in CATEGORY_BY_NUMBER:
                    raise CatalogParseError(f"category number {n} outside vocabulary at line "
                                            f"{_line_no(text, h.start())} ({source})")
                category, category_raw = CATEGORY_BY_NUMBER[n], title
            else:
                category, category_raw = None, None       # Quick-Pick / How to Use: fuera de categoría
            continue
        # level == "###": una ficha
        start = h.start()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        header_raw = title
        suffix_m = _SUFFIX_RE.search(header_raw)
        name = _SUFFIX_RE.sub("", header_raw).strip() if suffix_m else header_raw.strip()
        if category is None:
            raise CatalogParseError(f"card '{name}' at line {_line_no(text, start)} is outside any "
                                    f"'## Category N:' section ({source})")
        if name in cards:
            raise CatalogParseError(f"duplicate card name '{name}' at line {_line_no(text, start)} ({source})")
        block = text[start:end]
        fields, labels_raw = _parse_fields(block)
        missing = [f for f in REQUIRED_FIELDS if not fields.get(f)]
        if missing:
            raise CatalogParseError(f"card '{name}' (line {_line_no(text, start)}) lacks required "
                                    f"field(s) {missing} ({source})")
        card = {
            "name": name,
            "header_raw": header_raw,
            "header_suffix": suffix_m.group(0).strip() if suffix_m else None,
            "category": category,
            "category_raw": category_raw,
            "line_start": _line_no(text, start),
            "line_end": _line_no(text, end - 1) if end > start else _line_no(text, start),
            "offset_start": start,
            "offset_end": end,
            "chars": len(block),
            "text_verbatim": block,
            "sha": _sha256(block),
            "labels_raw": labels_raw,
            "fields_present": [f for f in REQUIRED_FIELDS + OPTIONAL_FIELDS if f in fields],
            "fields_absent": [f for f in OPTIONAL_FIELDS if f not in fields],
        }
        for f in REQUIRED_FIELDS + OPTIONAL_FIELDS:
            if f in fields:
                card[f] = fields[f]           # opcional ausente = llave AUSENTE (jamás '')
        if "_duplicates" in fields:
            card["labels_duplicated"] = fields["_duplicates"]
        cards[name] = card
    return cards


def catalog_sha(cards):
    """ADR-0082 (A): sha256 de 'name:sha' por línea, nombres ordenados. Cambia si cambia CUALQUIER ficha."""
    return _sha256("\n".join(f"{name}:{cards[name]['sha']}" for name in sorted(cards)))


# ── el catálogo del repo, parseado UNA vez al importar; el import jamás lanza ─────────────────────────
try:
    CARDS = parse(CATALOG_PATH_ABS)
    CATALOG_SHA = catalog_sha(CARDS)
    CATALOG_STATE = "parsed"
except (CatalogParseError, OSError) as _e:          # declarado, nunca un default silencioso
    CARDS = {}
    CATALOG_SHA = None
    CATALOG_STATE = f"errored ({type(_e).__name__}: {_e})"
CARDS_COUNT = len(CARDS)


def card(name):
    """La ficha o None (sin ficha en el catálogo — `agent_matrix` lo declara `card 'no-card-in-catalog'`)."""
    return CARDS.get(name)


def cards_summary():
    """Vista compacta para `GET /council/membership` y la Hoja: sin text_verbatim."""
    return {
        "module_version": MODULE_VERSION,
        "catalog_path": CATALOG_PATH,
        "catalog_state": CATALOG_STATE,
        "catalog_sha": CATALOG_SHA,
        "n_cards": CARDS_COUNT,
        "n_cards_golden": CARDS_COUNT_GOLDEN,
        "cards": {n: {"sha": c["sha"], "category": c["category"], "chars": c["chars"],
                      "line_start": c["line_start"], "header_suffix": c["header_suffix"],
                      "fields_present": c["fields_present"]} for n, c in CARDS.items()},
    }


# ── (C.1) el prompt del consejo: bloque fijo + reglas §7 literales + ficha verbatim ───────────────────
# Inglés, sin fechas ni ids, sin sustitución por miembro: es el PREFIJO COMPARTIDO que la caché escribe una
# vez y lee 16× por ronda (Context 7). La identidad del miembro la da el bloque B (`### <agent>` de su
# ficha), NO este texto — sustituir `<agent>` aquí rompería la identidad byte a byte del bloque A.
# Los verbos de la doctrina (answer / rank / dispatch) aparecen SÓLO negados; ningún nombre de campo
# prohibido (direct_answer, verdict, confidence, ranking, score) aparece: el smoke lo mide.
COUNCIL_FIXED_BLOCK = (
    "You sit on a COUNCIL OF CRITERIA for a zebrafish pronephros research question, as the catalog agent "
    "whose card follows this block (the `### <agent>` section below IS your role: obey it verbatim, "
    "including everything it does NOT own). "
    "You do NOT answer the question, do NOT rank, do NOT audit, do NOT dispatch anything. "
    "Emit ONLY the tool you are asked for, and nothing else. "
    "Name evidence kinds and source families from the enums the tool offers; never assert identifiers as "
    "facts (entities are checked by code against the source of truth); prior observations and human "
    "attestations are PRIOR ART, never evidence. "
    "Absence of evidence is a finding, not a zero: say what is missing and how it would be verified."
)

# Reglas §7 de CLAUDE.md, texto LITERAL de las líneas 146-149 y 153-158 @ 9d90c01 (ADR-0082 (C.1)), sin el
# guion de viñeta ni el `\r` del archivo (CLAUDE.md es CRLF). El smoke verifica cada ítem como substring
# exacto de la sección `## 7.` del CLAUDE.md del árbol: si alguien edita una regla, RULES_SHA cambia y el
# smoke lo dice — nunca se copia a ciegas.
COUNCIL_RULES_ITEMS = (
    '**`causal-pruner` outputs always require a human gate before downstream use.** It is hypothesis-generation, never decision.',
    '**`cross-field-bridge-agent` operates Method 2 only in Phase I.** Method 1 mode for this agent is locked until Phase II.',
    '**Test 5 is exploratory in Phase I — modest evidence is success.** Do not force conclusions; absence-of-evidence findings are also data.',
    '**Compliance and budget decisions never go through automatic filtering.** Direct human gate, no exceptions.',
    '**No backwards-incompatible changes to v2.1 agent designs without an ADR.** Document the recalibration in `docs/decisions/`.',
    '**External identifiers are never used from internal memory without verification.** Gene IDs (ENSDARG, ENSEMBL, NCBI symbols), PMIDs, GEO/SRA accessions, DOIs, and biological sequences MUST be verified against an authoritative external source (Ensembl REST, PubMed, GEO, NCBI) before being used in analysis, citations, `evidence_cited` fields, or output of any kind. Hardcoded identifiers in scripts must carry an inline `# verified: YYYY-MM-DD source: <db>` comment. The May 8-9 2026 session documented 5 of 11 ENSDARG IDs and 1 PMID generated from internal memory were wrong; this rule prevents recurrence. **Verification is satisfied only when the raw external response is cached per §6 cache discipline** — an AI-processed summary is NOT verification.',
    '**Anti-fabrication verification gate (GWT v1.1).** Every external identifier in an output (ENSDARG/ENSDARP, UniProt, PMID, GEO/SRA/PXD, DOI) MUST resolve through the **source-of-truth** — `analysis/scripts/lib/resolve_id.py` reading `analysis/outputs/verified_identifiers.json` (DATA INAMOVIBLE v1) — or be explicitly flagged in `gap_flags`. The deterministic gate `analysis/scripts/lib/verify_output.py` (Logic-LM-class, NOT an LLM) enforces this: an unresolved ENSDARG is a **gate FAILURE**; PMIDs/GEO are flagged (no literature store yet). In scripts, marker/gene IDs come from `resolve_id.require()` (which raises on NOT_FOUND), never hardcoded from memory. This is the structural fix for the 2026-06 corruption (15 of 16 marker IDs in `01_schoels_analysis.py` were wrong; the `wt1a` false-positive). The store is **read-only by default** and **human-gated mutable** (writes go through the single builder + a human gate); see ADR-0008/0010 and `docs/findings/2026-06-10-schoels-phase1-id-corruption.md`.',
    '**DATA INAMOVIBLE mutations are human-gated, ALWAYS, with explicit specification (2026-06-13 founder directive).** Every change to the shared store — **ADD, EDIT, or DELETE** — across the **embedding**, the **index** (Neo4j graph + vector + sparse), AND the **raw** layer, passes through a human gate and MUST state exactly what is being changed before proceeding. No agent mutates the DATA INAMOVIBLE unilaterally. Consequences: `ingest.py` is **add/update-only** (MERGE, **never deletes**); pruning dead/orphan nodes is a *proposal* (detect → `pending_review` specifying exactly what would be removed → human approve → execute), **never automatic**; changing the embedding model **halts** pending explicit human confirmation (re-embeds all + invalidates the vector space). **Reads/refreshes are free** (e.g. a reader auto-reloading the sparse index after a gated ingest); **mutations are not.** This is what makes it *inamovible* — *"siempre tiene que pasar por un gate humano y especificar qué se está haciendo"* (ADR-0022).',
    '**Self-audit by the same agent that produced the work is prohibited as a substrate-evidence audit gate.** Use `composite-auditor` (Mode 1 split-and-vote minimum) for any retrospective claimed as audit evidence. Self-reflection by the producing agent is permitted but is NOT an audit gate. The May 14 2026 session generated a single-LLM retrospective that was treated as audit evidence; the composite-audit that followed (ADR-0006) is the operationally correct pattern and this rule makes the distinction explicit. See `skills/custom/organogenesis-agent-architect/references/agent-invocation-matrix.md` for invocation routing.',
    "**Catalog-agent invocation discipline.** If the work being produced matches the role description of a catalog agent (per `references/agent-invocation-matrix.md`), that agent MUST be invoked OR the output's `agents_invoked` field MUST record `status: skipped-ad-hoc` with explicit justification. Implicitly performing the role without invocation OR explicit skip is a §7 violation. Particularly: generating ranked candidates / minimal sets / sufficiency hypotheses is `causal-pruner` work and MUST be flagged as such (also covered by the first rule above). Auditing substrate-evidence outputs is `composite-auditor` work and MUST NOT be done by a single-LLM self-audit pass.",
)

COUNCIL_RULES_HEADER = "CLAUDE.md §7 — Hard rules (non-negotiable), verbatim, applicable to a council member:"
COUNCIL_RULES = COUNCIL_RULES_HEADER + "\n" + "\n".join("- " + r for r in COUNCIL_RULES_ITEMS)
RULES_SHA = _sha256(COUNCIL_RULES)

SHARED_BLOCK_TEXT = COUNCIL_FIXED_BLOCK + "\n\n" + COUNCIL_RULES     # bloque A, idéntico para los 17
SHARED_BLOCK_SHA = _sha256(SHARED_BLOCK_TEXT)

# Nombres de campo que NINGÚN tool del consejo tiene y que el bloque A no debe nombrar como salida
# (ADR-0082 (C.2) test estático; C2 lo usa sobre los input_schema). Los verbos en inglés answer/rank/
# dispatch sí aparecen en el bloque A, SÓLO negados ("do NOT answer …").
PROHIBITED_OUTPUT_FIELDS = ("direct_answer", "answer", "verdict", "confidence", "ranking", "rank",
                            "score", "dispatch")

# Mínimo cacheable del modelo del consejo (rol `council` de la tabla g2 — models.resolve_role('council'); ningún
# literal de modelo aquí: gate M.4 de ADR-0081): skill claude-api shared/prompt-caching.md
# (cache 2026-06-24), tabla "Minimum cacheable prefix". Si el prefijo no llega, la API devuelve
# cache_creation_input_tokens 0 en silencio — LG1 lo mide con count_tokens.
MIN_CACHEABLE_TOKENS = 512
MIN_CACHEABLE_SOURCE = "skill claude-api shared/prompt-caching.md (cached 2026-06-24) — Claude Opus 5: 512"
CACHE_TTLS = ("5m", "1h")
# Regla de la API (misma referencia, §"Choosing the TTL"/tabla de mezcla): "a 1-hour entry must appear
# before any 5-minute entries". El bloque A va ANTES que el B, así que si la ficha (B) pide 1h el bloque A
# hereda 1h — el ADR escribe "el A siempre 5m", que con TTL=1h violaría la regla que él mismo cita.
CACHE_TTL_RULE = ("longer TTL first: block A (shared prefix) takes ttl 1h whenever block B (card) is 1h; "
                  "with 5m both blocks are 5m")

_FALSEY = {"0", "false", "no", "off"}
_TRUTHY = {"1", "true", "yes", "on"}


def cache_config(env=None):
    """Lector TOLERANTE de WITT_COUNCIL_CACHE (default 1) y WITT_COUNCIL_CACHE_TTL (default 5m): vacía o
    basura → default DECLARADO con su fuente (ADR-0082 (L.1))."""
    env = os.environ if env is None else env
    raw_on = (env.get("WITT_COUNCIL_CACHE") or "").strip().lower()
    if raw_on == "":
        enabled, on_src = True, "default (WITT_COUNCIL_CACHE unset)"
    elif raw_on in _TRUTHY:
        enabled, on_src = True, "env WITT_COUNCIL_CACHE"
    elif raw_on in _FALSEY:
        enabled, on_src = False, "env WITT_COUNCIL_CACHE"
    else:
        enabled, on_src = True, f"default (WITT_COUNCIL_CACHE unparseable: {raw_on!r})"
    raw_ttl = (env.get("WITT_COUNCIL_CACHE_TTL") or "").strip().lower()
    if raw_ttl == "":
        ttl_card, ttl_src = "5m", "default (WITT_COUNCIL_CACHE_TTL unset)"
    elif raw_ttl in CACHE_TTLS:
        ttl_card, ttl_src = raw_ttl, "env WITT_COUNCIL_CACHE_TTL"
    else:
        ttl_card, ttl_src = "5m", f"default (WITT_COUNCIL_CACHE_TTL unparseable: {raw_ttl!r})"
    ttl_shared = "1h" if ttl_card == "1h" else "5m"
    return {
        "enabled": enabled, "enabled_source": on_src,
        "ttl_card": ttl_card, "ttl_shared": ttl_shared, "ttl_source": ttl_src, "ttl_rule": CACHE_TTL_RULE,
        "min_cacheable_tokens": MIN_CACHEABLE_TOKENS, "min_cacheable_source": MIN_CACHEABLE_SOURCE,
    }


def _cache_control(ttl):
    """`{type:'ephemeral'}` es el TTL de 5 min por defecto de la API; sólo 1h lleva `ttl` explícito."""
    return {"type": "ephemeral", "ttl": "1h"} if ttl == "1h" else {"type": "ephemeral"}


def build_system(card_or_name, env=None):
    """ADR-0082 (C.1): el `system` de un miembro. Con caché → lista de DOS bloques
    `[{type:'text', text: bloque A (fijo + §7), cache_control}, {type:'text', text: ficha VERBATIM,
    cache_control}]`; sin caché (WITT_COUNCIL_CACHE=0) → el string `A + '\\n\\n' + B` (A/B medible).
    Función PURA: sin timestamps ni ids; dos llamadas con los mismos insumos → los mismos bytes.
    Sin ficha → ValueError('no-card-in-catalog: <name>') (C2 la vuelve fila `errored`)."""
    c = card(card_or_name) if isinstance(card_or_name, str) else card_or_name
    if not c or "text_verbatim" not in c:
        raise ValueError(f"no-card-in-catalog: {card_or_name if isinstance(card_or_name, str) else '?'}")
    cfg = cache_config(env)
    if not cfg["enabled"]:
        return SHARED_BLOCK_TEXT + "\n\n" + c["text_verbatim"]
    return [
        {"type": "text", "text": SHARED_BLOCK_TEXT, "cache_control": _cache_control(cfg["ttl_shared"])},
        {"type": "text", "text": c["text_verbatim"], "cache_control": _cache_control(cfg["ttl_card"])},
    ]


def system_sha(system):
    """sha256 del `system` tal como viaja (lista de bloques canonizada o string). Se congela por miembro."""
    if isinstance(system, str):
        return _sha256(system)
    return _sha256(json.dumps(system, sort_keys=True, ensure_ascii=False, separators=(",", ":")))


__all__ = [
    "MODULE_VERSION", "CATALOG_PATH", "CATALOG_PATH_ABS", "CARDS_COUNT_GOLDEN", "CATEGORY_VOCABULARY",
    "REQUIRED_FIELDS", "OPTIONAL_FIELDS", "CatalogParseError", "parse", "catalog_sha",
    "CARDS", "CATALOG_SHA", "CATALOG_STATE", "CARDS_COUNT", "card", "cards_summary",
    "COUNCIL_FIXED_BLOCK", "COUNCIL_RULES_ITEMS", "COUNCIL_RULES", "RULES_SHA",
    "SHARED_BLOCK_TEXT", "SHARED_BLOCK_SHA", "PROHIBITED_OUTPUT_FIELDS",
    "MIN_CACHEABLE_TOKENS", "MIN_CACHEABLE_SOURCE", "CACHE_TTLS", "CACHE_TTL_RULE",
    "cache_config", "build_system", "system_sha",
]

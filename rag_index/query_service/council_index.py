"""
council_index.py — el ÍNDICE DEL CONSEJO DE CRITERIO (ADR-0082 (I); rebanada C7). Patrón `precedent.py`.

Qué es: la memoria consultable de lo que el consejo PIDIÓ, lo que juzgó COBERTURA, lo que el humano DECIDIÓ
por `requirement_id` estable, y lo que la corrida dejó como huecos (`gap_flags`), alternativas, hallazgos del
panel y comentarios humanos (ADR-0077). Sirve a tres lectores: `GET /council/search` (humanos, M6 Bitácora),
`prior_observations[]` (la ronda 1 del plan y el `thread_context`, letras `P-A…`) y `GET /council/demand` (el
criterio MEDIDO de disparo de los sidecars ADR-0084/0085: cuántos requisitos pidieron `web`/`tooluniverse`/
`figure` — conteo por pertenencia ESTÁTICA (DEMAND_FAMILIES) que no se rompe al llegar la llave de Brave; lo que el
harness puede despachar HOY viaja al lado en `unsatisfiable_families` (derivada en la llamada) y en
`web_locator_provider_state` — ADR-0084 F.3).

Doctrina (CLAUDE.md §7 · ADR-0053 · ADR-0043 · ADR-0074):
  · Todo ítem sale `admissible_as_evidence: false` ESTRUCTURAL con `why_not_admissible`: una observación del
    consejo es PRIOR ART para humanos, planner y ronda 1 — jamás evidencia. El gate anti-fabricación es ciego a
    la procedencia por diseño, así que la regla se aplica aquí, en el producto, ítem por ítem.
  · Series de citas DISJUNTAS por construcción (`precedent.serialize_disjoint`): números = evidencia (runs.py),
    LETRAS = precedente/observaciones. Este módulo sólo produce letras (`l` en la búsqueda, `P-<letra>` en las
    observaciones previas); nunca `n`.
  · Corpus = corridas CLOSED (cierre explícito) del alcance de origen (default `production`; NULL incluido y
    DECLARADO — regla de `precedent.closed_runs_scoped`) + planes con `council_json` de esos orígenes que
    NINGUNA corrida indexada consumió (un requisito emitido en un plan nunca corrido también es observación;
    uno consumido ya viaja en el `frozen.council` de su corrida: contarlo dos veces mentiría).
  · La decisión humana viaja SIN su razón ni su texto atestiguado (kind `decision` = {requirement_id, decision,
    gap ≤200}): la razón es del ledger; aquí sólo la POLÍTICA consultable entre investigaciones.
  · Los comentarios (`comment`) llevan autor y ≤280 chars y entran a la BÚSQUEDA; al prompt de r1 sólo si
    `WITT_COUNCIL_PRIOR_KINDS` los nombra (default: EXCLUIDOS — mitigación de inyección, ADR-0082 R8).
  · El scorer se DECLARA siempre (`sparse-tfidf` con sklearn; `stdlib-tfidf-fallback` = TF-IDF coseno en stdlib
    puro cuando sklearn no está): un fallback nunca se disfraza del camino principal (ADR-0039/0043).
  · Tres estados: ausente ≠ null declarado ≠ valor. `corpus_state 'empty-corpus'`, `plans_state 'not-available
    (…DB not migrated…)'` cuando la BD conectada no tiene plans.council_json (db.council_schema_state), `'empty'` cuando
    la tiene y no hay planes con ronda 1, `prior_observations.state ∈ PRIOR_STATES`.
  · Cero escritura: este módulo SÓLO lee `runs`, `plans`, `run_comments`. Cero red, cero modelo.

Costuras (cosidas por C9): app cablea `GET /council/search` → `search()`, `GET /council/demand` → `demand()`;
council_jobs / runs llaman
`prior_observations()` en el job r1 y `frozen_index_block()` para `frozen.council.index`. Las rutas traducen
`CouncilIndexError.status/.detail` a HTTPException (patrón `runs.ThreadError`).
"""
import json
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "analysis" / "scripts"))
import db  # noqa: E402
import precedent  # noqa: E402
from lib import agent_matrix, catalog_cards  # noqa: E402

INDEX_VERSION = "council-index-1"

# ── vocabularios cerrados (viajan congelados junto al dato) ──────────────────────────────────────────────
KINDS = ("requirement", "coverage", "decision", "gap_flag", "alternative", "panel_finding", "comment")
PRIOR_KINDS_DEFAULT = ("requirement", "coverage", "decision", "gap_flag", "panel_finding")   # `comment` EXCLUIDO
CORPUS_STATES = ("indexed", "empty-corpus")
PLANS_STATE_NOT_AVAILABLE = "not-available (plans.council_json column absent — DB not migrated to ADR-0082 E.1)"
PLANS_STATES = ("indexed", "empty", PLANS_STATE_NOT_AVAILABLE)
# ADR-0082 (I) enumera delivered | empty-corpus | disabled; `no-match` se AÑADE (declarado en C7): corpus con
# ítems pero ninguno con score > 0 no es 'delivered 0' ni 'empty-corpus' — 0 entregadas ≠ corpus vacío.
PRIOR_STATES = ("delivered", "empty-corpus", "disabled", "no-match")
SCORERS = ("sparse-tfidf", "stdlib-tfidf-fallback", "none")
DECISION_KINDS = ("keep", "discard", "aporto")            # 'pending' NO es observación: nadie decidió
DECIDED_BY_KINDS = ("human", "default-keep", "gate-human-pending")
COVERAGE_PHASES = ("pre_search", "post_search")
COVERED_STATES = ("covered", "covered-by-attestation")   # lo demás deja la necesidad ABIERTA
PANEL_FINDING_VERDICTS = ("REVISE", "APPROVE_MINOR")     # = runs._panel_findings (:782)
FILTER_KEYS = ("run_id", "plan_id", "requirement_id", "source_family", "evidence_kind", "priority",
               "decision", "coverage_final", "phase", "requested_by", "lens", "author")
TEXT_CAPS = {"requirement": 300, "coverage": 240, "decision": 200, "gap_flag": 300, "alternative": 300,
             "panel_finding": 300, "comment": 280}
CORPUS_LIMIT = 1000                                       # = precedent.closed_runs_scoped(limit)
SEARCH_K_MAX = 50                                         # = precedent.search
PRIOR_K_DEFAULT, PRIOR_K_MIN, PRIOR_K_MAX = 5, 0, 12
PRIOR_LETTER_PREFIX = "P-"

# ADR-0084 (F.3): la DEMANDA se cuenta por PERTENENCIA ESTÁTICA y la DISPONIBILIDAD se lee en la llamada — dos verdades
# que viajan lado a lado, nunca fundidas. DEMAND_SOURCE_FAMILIES son las familias-sidecar cuya demanda MIDE este módulo
# (web → ADR-0084, tooluniverse → ADR-0085): `web` sigue contándose aunque el localizador tenga llave, para que la serie
# MEDIDA `n_requirements_unsatisfiable_by_family.web` no se rompa al llegar BRAVE_API_KEY (veredicto del juez 2). La lista
# de lo que el harness NO puede despachar AHORA la deriva `unsatisfiable_families(env)` EN LA LLAMADA vía
# `search_harness.unsatisfiable_families` (fn None ∪ web_locator.provider_state no disponible) — ya no en el import:
# con `fn` real en la fila web, el criterio `fn is None` la volvería «satisfiable» aunque no haya llave (Context 1).
# NO `tool_module is None`: europepmc tampoco tiene módulo bajo .tooluniverse pero SÍ corre (`fn answer_pipeline`).
DEMAND_SOURCE_FAMILIES = ("tooluniverse", "web")          # estática (ADR-0084 F.3 / ADR-0085)
UNSATISFIABLE_EVIDENCE_KINDS = ("figure",)               # ADR-0083
DEMAND_FAMILIES = ("figure", "tooluniverse", "web")       # estática: la serie medida no cambia con la llave
assert DEMAND_FAMILIES == tuple(sorted(set(DEMAND_SOURCE_FAMILIES) | set(UNSATISFIABLE_EVIDENCE_KINDS)))
DEMAND_FAMILIES_RULE = ("DEMAND_FAMILIES is STATIC (ADR-0084 F.3): a requirement whose source_family is web or tooluniverse, "
                        "or whose evidence_kind is figure, is COUNTED as demand for its sidecar whether or not the harness "
                        "can dispatch it today — the measured trigger series must not break when BRAVE_API_KEY arrives; "
                        "what the harness can dispatch NOW travels apart in unsatisfiable_families (derived at call time) "
                        "and web_locator_provider_state")
UNSATISFIABLE_FAMILIES_SOURCE = "derived: SEARCH_DISPATCH fn None ∪ web_locator.provider_state not available"
DEMAND_THRESHOLD = {"min_runs": 5, "min_requirements": 3, "source": "brief §6.3"}


def _unsatisfiable_now(env=None):
    """(tuple ordenada, fuente) — lo que el harness NO puede despachar AHORA (ADR-0084 C.2/F.3), leído en la llamada:
    bajo off/sin llave ('tooluniverse', 'web'); con llave de Brave ('tooluniverse',). Fallback DECLARADO si el árbol no
    trae search_harness (jamás fingido como derivado)."""
    try:
        from lib import search_harness as _sh
        return tuple(_sh.unsatisfiable_families(env)), UNSATISFIABLE_FAMILIES_SOURCE
    except Exception as e:   # pragma: no cover — depende del árbol
        return tuple(DEMAND_SOURCE_FAMILIES), f"declared fallback (search_harness unavailable: {type(e).__name__})"


def unsatisfiable_families(env=None):
    """Tupla ORDENADA de las familias que el harness NO puede satisfacer AHORA (search_harness.family_available False),
    derivada EN LA LLAMADA — ADR-0084 (F.3). `env` (dict) sustituye a os.environ en los smokes."""
    return _unsatisfiable_now(env)[0]


def web_locator_provider_state(env=None):
    """{provider, provider_source, available, unavailable_reason} — la disponibilidad del localizador web leída en la
    llamada (web_locator.provider_state; ADR-0084 B.3/F.3), proyectada a las 4 llaves que viajan en `demand()` y en
    GET /council/demand. Sin el módulo → declarado (provider None, available False), jamás fingido."""
    try:
        from lib import web_locator as _wl
        ps = _wl.provider_state(env)
        return {"provider": ps.get("provider"), "provider_source": ps.get("provider_source"),
                "available": bool(ps.get("available")), "unavailable_reason": ps.get("unavailable_reason")}
    except Exception as e:   # pragma: no cover — depende del árbol
        return {"provider": None, "provider_source": None, "available": False,
                "unavailable_reason": f"web_locator not importable ({type(e).__name__})"}

WHY_NOT_ADMISSIBLE = ("council observations (requirements, coverage judgments, human ledger decisions, gap flags, "
                      "alternatives, panel findings, comments) are PRIOR ART for humans, the planner and the "
                      "council's round 1 — never evidence: nothing indexed here enters the gated evidence object "
                      "(ADR-0082 (I), ADR-0053); the anti-fabrication gate is provenance-blind by design, so the "
                      "rule is enforced here, structurally, on every item")
PRIOR_ART_INSTRUCTION = ("PRIOR ART from earlier investigations and human ledgers — NOT evidence. Use it only to "
                         "avoid re-asking what was already asked, covered or decided; never assert an identifier "
                         "taken from it (entities are checked by code).")
DISJOINT_NOTE = "citation series are disjoint by construction: numbers = evidence, letters = council observations"

ENV_TABLE = {   # default declarado por variable (ADR-0082 tabla de env; lector tolerante en tiempo de llamada)
    "WITT_COUNCIL_INDEX": "1",
    "WITT_COUNCIL_PRIOR_K": str(PRIOR_K_DEFAULT),
    "WITT_COUNCIL_PRIOR_KINDS": ",".join(PRIOR_KINDS_DEFAULT),
    "WITT_COUNCIL_INDEX_ORIGINS": "production",
}
_TRUTHY = {"1", "true", "yes", "on"}
_FALSEY = {"0", "false", "no", "off"}

_IDX = {"key": None, "items": [], "meta": None, "vectorizer": None, "matrix": None, "stdlib": None,
        "scorer": "none", "n_builds": 0}


# ── errores tipados para la capa HTTP (patrón runs.ThreadError) ──────────────────────────────────────────
class CouncilIndexError(ValueError):
    """`status` y `detail` son lo que app.py traduce a HTTPException; este módulo no importa fastapi."""
    status = 400

    def __init__(self, detail, status=None):
        super().__init__(detail.get("error") if isinstance(detail, dict) else str(detail))
        self.detail = detail
        if status is not None:
            self.status = status


class CouncilIndexDisabled(CouncilIndexError):
    """Kill-switch WITT_COUNCIL_INDEX=0 → 503 DECLARADO (ADR-0082 (I))."""
    status = 503


# ── env tolerante ────────────────────────────────────────────────────────────────────────────────────────
def env_config(env=None):
    """Las 4 env del índice con default DECLARADO y fuente (vacía/basura → default, nunca una excepción)."""
    env = os.environ if env is None else env
    out = {}
    raw = (env.get("WITT_COUNCIL_INDEX") or "").strip().lower()
    if raw == "":
        out["enabled"], out["enabled_source"] = True, "default (WITT_COUNCIL_INDEX unset)"
    elif raw in _TRUTHY:
        out["enabled"], out["enabled_source"] = True, "env WITT_COUNCIL_INDEX"
    elif raw in _FALSEY:
        out["enabled"], out["enabled_source"] = False, "env WITT_COUNCIL_INDEX"
    else:
        out["enabled"], out["enabled_source"] = True, f"default (WITT_COUNCIL_INDEX unparseable: {raw!r})"

    raw = (env.get("WITT_COUNCIL_PRIOR_K") or "").strip()
    if raw == "":
        out["prior_k"], out["prior_k_source"] = PRIOR_K_DEFAULT, "default (WITT_COUNCIL_PRIOR_K unset)"
    else:
        try:
            k = int(raw)
            kk = max(PRIOR_K_MIN, min(k, PRIOR_K_MAX))
            out["prior_k"] = kk
            out["prior_k_source"] = ("env WITT_COUNCIL_PRIOR_K" if kk == k
                                     else f"env WITT_COUNCIL_PRIOR_K (clamped {k} -> {kk}; range {PRIOR_K_MIN}..{PRIOR_K_MAX})")
        except ValueError:
            out["prior_k"], out["prior_k_source"] = PRIOR_K_DEFAULT, f"default (WITT_COUNCIL_PRIOR_K unparseable: {raw!r})"

    raw = (env.get("WITT_COUNCIL_PRIOR_KINDS") or "").strip()
    if raw == "":
        out["prior_kinds"], out["prior_kinds_source"], out["prior_kinds_dropped"] = (
            tuple(PRIOR_KINDS_DEFAULT), "default (WITT_COUNCIL_PRIOR_KINDS unset)", [])
    else:
        wanted = [v.strip() for v in raw.split(",") if v.strip()]
        known = tuple(k for k in KINDS if k in wanted)          # orden canónico del vocabulario
        dropped = sorted(set(wanted) - set(KINDS))
        if known:
            out["prior_kinds"], out["prior_kinds_source"] = known, "env WITT_COUNCIL_PRIOR_KINDS"
        else:
            out["prior_kinds"], out["prior_kinds_source"] = (tuple(PRIOR_KINDS_DEFAULT),
                                                             f"default (WITT_COUNCIL_PRIOR_KINDS without a known kind: {raw!r})")
        out["prior_kinds_dropped"] = dropped

    raw = (env.get("WITT_COUNCIL_INDEX_ORIGINS") or "").strip()
    if raw == "":
        out["origins"], out["origins_source"] = tuple(precedent.DEFAULT_ORIGINS), "default (WITT_COUNCIL_INDEX_ORIGINS unset)"
    elif raw.lower() == "all":
        out["origins"], out["origins_source"] = None, "env WITT_COUNCIL_INDEX_ORIGINS=all (no origin filter, declared)"
    else:
        out["origins"], out["origins_source"] = precedent.normalize_origins(raw), "env WITT_COUNCIL_INDEX_ORIGINS"
    out["env_table"] = dict(ENV_TABLE)
    return out


def enabled(env=None):
    return env_config(env)["enabled"]


def _resolve_origins(include_origins, cfg):
    """El parámetro explícito gana sobre la env; 'all' (param o env) = sin filtro DECLARADO (None)."""
    if include_origins is None:
        return cfg["origins"], cfg["origins_source"]
    if isinstance(include_origins, str) and include_origins.strip().lower() == "all":
        return None, "param include_origins=all (no origin filter, declared)"
    if isinstance(include_origins, (list, tuple)) and [str(o).strip().lower() for o in include_origins] == ["all"]:
        return None, "param include_origins=all (no origin filter, declared)"
    return precedent.normalize_origins(include_origins), "param include_origins"


def normalize_kinds(kinds):
    """None → los 7; lista/tupla/CSV → tupla en orden canónico. Un kind fuera del enum → CouncilIndexError 400
    (filtrar por un kind que no existe daría un vacío indistinguible de 'no hay')."""
    if kinds is None:
        return tuple(KINDS)
    if isinstance(kinds, str):
        kinds = kinds.split(",")
    wanted = [str(k).strip() for k in kinds if str(k).strip()]
    if not wanted:
        return tuple(KINDS)
    unknown = sorted(set(wanted) - set(KINDS))
    if unknown:
        raise CouncilIndexError({"error": "unknown_kind", "unknown": unknown, "allowed": list(KINDS)})
    return tuple(k for k in KINDS if k in wanted)


def normalize_filters(filters):
    """Filtros de igualdad sobre campos ESTRUCTURADOS del ítem (FILTER_KEYS cerrado); `requested_by` es
    pertenencia. Llave desconocida → 400. Valores None se ignoran."""
    if not filters:
        return {}
    if not isinstance(filters, dict):
        raise CouncilIndexError({"error": "filters_not_object"})
    unknown = sorted(set(filters) - set(FILTER_KEYS))
    if unknown:
        raise CouncilIndexError({"error": "unknown_filter", "unknown": unknown, "allowed": list(FILTER_KEYS)})
    return {k: v for k, v in filters.items() if v is not None}


def _passes(item, flt):
    for k, v in flt.items():
        if k == "requested_by":
            if v not in (item.get("requested_by") or []):
                return False
        elif item.get(k) != v:
            return False
    return True


# ── lectura tolerante del registro (ADR-0074: nada se corrige, nada se rellena) ──────────────────────────
def _cap(text, n):
    """(texto colapsado en espacios y recortado a n, truncated). None/'' → ('', False)."""
    s = " ".join(str(text if text is not None else "").split())
    return s[:n], len(s) > n


def _iso(v):
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat(timespec="seconds")
    s = str(v).strip()
    return s[:19].replace(" ", "T") if len(s) >= 19 else s


def _frozen_of(row):
    """(frozen dict | None, state ∈ present | absent | unparseable)."""
    raw = row.get("frozen_record_json")
    if not raw:
        return None, "absent"
    try:
        rec = json.loads(raw)
    except ValueError:
        return None, "unparseable"
    return (rec, "present") if isinstance(rec, dict) else (None, "unparseable")


_REQ_PATHS = (("requirements",), ("ledger", "requirements"), ("aggregation", "requirements"),
              ("r1", "requirements"), ("r1", "aggregation", "requirements"), ("r1", "ledger", "requirements"))


def _requirements_of(container):
    """Los requisitos de un `frozen.council` o de un `plans.council_json`, leídos TOLERANTEMENTE por rutas
    conocidas (la forma exacta de `council_json` la fija C4/E.1; `frozen.council.ledger.requirements` la fija
    (J)). Devuelve (lista, ruta_encontrada | None). Nunca inventa: sin lista → ([], None)."""
    if not isinstance(container, dict):
        return [], None
    for path in _REQ_PATHS:
        cur = container
        ok = True
        for key in path:
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                ok = False
                break
        if ok and isinstance(cur, list):
            return [r for r in cur if isinstance(r, dict)], ".".join(path)
    return [], None


def _decided_by_kind(decided_by):
    """'human:<user_id>' → 'human' (el id NO viaja al índice); los otros prefijos tal cual; None → None."""
    if not isinstance(decided_by, str) or not decided_by:
        return None
    if decided_by.startswith("human:"):
        return "human"
    for k in DECIDED_BY_KINDS:
        if decided_by.startswith(k):
            return k
    return "other"


def _list_of_strings(raw):
    """gap_flags / alternatives_considered leídos tolerantes (espejo de runs._gap_flags_tolerante): lista →
    strings; string JSON de lista → parseado; string suelto → [string]; None → []."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, default=str) for x in raw]
    if isinstance(raw, str):
        try:
            v = json.loads(raw)
            if isinstance(v, list):
                return [x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, default=str) for x in v]
        except ValueError:
            pass
        return [raw]
    return [json.dumps(raw, ensure_ascii=False, default=str)]


def _panel_findings(audit):
    """ESPEJO de runs._panel_findings (:782) — el mismo criterio (REVISE | APPROVE_MINOR con caught o reasons)
    sin importar runs.py (evitaría un ciclo: runs → council_index → runs). El smoke mide la igualdad."""
    out = []
    for r in (audit or {}).get("panel", []) or []:
        if not isinstance(r, dict):
            continue
        if r.get("verdict") in PANEL_FINDING_VERDICTS and (r.get("caught") or r.get("reasons")):
            out.append({"lens": r.get("lens"), "reviewer": r.get("reviewer"), "verdict": r.get("verdict"),
                        "caught": r.get("caught", ""), "correction_applied": r.get("correction_applied", ""),
                        "reasons": r.get("reasons", [])})
    return out


# ── ítems (puros: reciben filas y JSON ya parseado; sin BD) ──────────────────────────────────────────────
def _item(kind, ctx, text_raw, source, search_text=None, **fields):
    text, truncated = _cap(text_raw, TEXT_CAPS[kind])
    item = {"kind": kind, "run_id": ctx.get("run_id"), "run_no": ctx.get("run_no"), "plan_id": ctx.get("plan_id"),
            "origin": ctx.get("origin"), "observed_at": ctx.get("observed_at"),
            "text": text, "text_truncated": truncated, "source": source,
            "admissible_as_evidence": False, "why_not_admissible": WHY_NOT_ADMISSIBLE}
    item.update(fields)
    item["_text"] = " ".join(str(x) for x in ([search_text] if search_text is not None else [text_raw]) if x)
    return item


def _requirement_items(reqs, ctx, source):
    out = []
    for r in reqs:
        gap = r.get("gap")
        ents = [str(e) for e in (r.get("entities") or []) if e]
        out.append(_item(
            "requirement", ctx, gap, source,
            search_text=" ".join([str(gap or ""), str(r.get("query_en") or ""), " ".join(ents),
                                  str(r.get("source_family") or ""), str(r.get("evidence_kind") or "")]),
            requirement_id=r.get("requirement_id"), query_en=r.get("query_en"),
            source_family=r.get("source_family"), evidence_kind=r.get("evidence_kind"),
            priority=r.get("priority"), priority_downgraded_from=r.get("priority_downgraded_from"),
            harness_state=r.get("harness_state"), hard_rule_gate=r.get("hard_rule_gate"),
            exploratory=r.get("exploratory"), from_operative=r.get("from_operative"),
            requested_by=list(r.get("requested_by") or []), n_requested_by=r.get("n_requested_by"),
            n_members=r.get("n_members"), entities=ents))
    return out


def _coverage_items(council, reqs_by_id, ctx):
    out = []
    coverage = council.get("coverage") if isinstance(council, dict) else None
    if not isinstance(coverage, dict):
        return out
    for phase in COVERAGE_PHASES:
        block = coverage.get(phase)
        if not isinstance(block, dict) or not isinstance(block.get("by_requirement"), list):
            continue   # {state 'not-run (…)'} declarado: no hay juicio que indexar
        for j in block["by_requirement"]:
            if not isinstance(j, dict):
                continue
            rid = j.get("requirement_id")
            req = reqs_by_id.get(rid, {})
            gap = req.get("gap")
            rationale = None
            for v in j.get("votes") or []:
                if isinstance(v, dict) and not v.get("annulled") and v.get("rationale"):
                    rationale = v["rationale"]
                    break
            cf = j.get("coverage_final")
            text_raw = rationale if rationale else f"{gap or ''} — {cf}"
            out.append(_item(
                "coverage", ctx, text_raw, f"frozen.council.coverage.{phase}.by_requirement",
                search_text=" ".join([str(gap or ""), str(rationale or ""), str(cf or "")]),
                requirement_id=rid, phase=phase, coverage_final=cf, n_valid_votes=j.get("n_valid_votes"),
                priority=j.get("priority", req.get("priority")), rationale_present=rationale is not None,
                source_family=req.get("source_family"), evidence_kind=req.get("evidence_kind")))
    return out


def _decision_items(reqs, ctx):
    """kind `decision` = {requirement_id, decision, gap ≤200} — SIN decision_reason, SIN attested_text,
    SIN el user_id (sólo la CLASE de quien decidió). 'pending' no es observación."""
    out = []
    for r in reqs:
        dec = r.get("decision")
        if dec not in DECISION_KINDS:
            continue
        out.append(_item(
            "decision", ctx, r.get("gap"), "frozen.council.ledger.requirements[].decision",
            search_text=" ".join([str(r.get("gap") or ""), str(dec)]),
            requirement_id=r.get("requirement_id"), decision=dec,
            decided_by_kind=_decided_by_kind(r.get("decided_by")), priority=r.get("priority"),
            source_family=r.get("source_family"), evidence_kind=r.get("evidence_kind"),
            hard_rule_gate=r.get("hard_rule_gate")))
    return out


def items_from_run(row, frozen):
    """Todos los ítems de UNA corrida cerrada (sin comentarios: esos van en una consulta agrupada). PURA.
    Devuelve (items, stats) con stats = {council: absent | without-ledger | with-ledger, n_requirements}."""
    ctx = {"run_id": row.get("run_id"), "run_no": row.get("run_no"), "plan_id": None,
           "origin": precedent.origin_of(row), "observed_at": _iso(row.get("frozen_at"))}
    items = []
    stats = {"council": "absent", "n_requirements": 0, "requirements_path": None}
    council = frozen.get("council") if isinstance(frozen, dict) else None
    reqs = []
    if isinstance(council, dict):
        ledger = council.get("ledger")
        ctx["plan_id"] = (ledger or {}).get("plan_id") if isinstance(ledger, dict) else None
        reqs, path = _requirements_of(council)
        stats["council"] = "with-ledger" if isinstance(ledger, dict) else "without-ledger"
        stats["requirements_path"] = path
        stats["n_requirements"] = len(reqs)
        stats["council_state"] = council.get("state")
        items.extend(_requirement_items(reqs, ctx, "frozen.council.ledger.requirements"))
        items.extend(_coverage_items(council, {r.get("requirement_id"): r for r in reqs}, ctx))
        items.extend(_decision_items(reqs, ctx))
    ans = (frozen or {}).get("answer") or {}
    for g in _list_of_strings(ans.get("gap_flags") if isinstance(ans, dict) else None):
        items.append(_item("gap_flag", ctx, g, "frozen.answer.gap_flags"))
    alts = (frozen or {}).get("alternatives_considered")
    for a in _list_of_strings(alts):
        items.append(_item("alternative", ctx, a, "frozen.alternatives_considered"))
    for f in _panel_findings((frozen or {}).get("audit") or {}):
        reasons = [str(x) for x in (f.get("reasons") or [])]
        text_raw = " ".join(x for x in [str(f.get("caught") or ""), "; ".join(reasons)] if x)
        items.append(_item("panel_finding", ctx, text_raw, "frozen.audit.panel[] (runs._panel_findings rule)",
                           lens=f.get("lens"), reviewer=f.get("reviewer"), verdict=f.get("verdict"),
                           n_reasons=len(reasons)))
    stats["_requirements"] = reqs
    stats["_council"] = council if isinstance(council, dict) else None
    return items, stats


def items_from_plan(prow, council_json):
    """Los requisitos de un plan con `council_json` (r1 sin decisiones ni cobertura). PURA."""
    ctx = {"run_id": None, "run_no": None, "plan_id": prow.get("plan_id"), "origin": precedent.origin_of(prow),
           "observed_at": _iso(prow.get("created_at"))}
    reqs, path = _requirements_of(council_json)
    items = _requirement_items(reqs, ctx, "plans.council_json" + (f".{path}" if path else ""))
    return items, {"n_requirements": len(reqs), "requirements_path": path, "_requirements": reqs,
                   "council_state": prow.get("council_state")}


def comment_items(row, comments_rows):
    """Los comentarios humanos de una corrida (ADR-0077): autor (display name de la cuenta), hora, ≤280."""
    ctx = {"run_id": row.get("run_id"), "run_no": row.get("run_no"), "plan_id": None,
           "origin": precedent.origin_of(row), "observed_at": _iso(row.get("frozen_at"))}
    out = []
    for c in comments_rows or []:
        out.append(_item("comment", ctx, c.get("body"), "run_comments (ADR-0077)",
                         comment_id=c.get("comment_id"), author=c.get("author_name"),
                         created_at=c.get("created_at")))
    return out


# ── lectura de la BD (sólo SELECT) ───────────────────────────────────────────────────────────────────────
def _closed_runs(origins):
    """(rows, declaración de origen). origins None = sin filtro (declarado: origins_included None)."""
    if origins is None:
        rows = db.closed_runs(limit=CORPUS_LIMIT, include_origins=None)
        counts = db.excluded_by_origin(None, states=("closed",))
        meta = {"origins_included": None, "excluded_by_origin": {},
                "origin_unknown_included": int(counts.get("origin_unknown_included") or 0),
                "origin_unknown_label": precedent.ORIGIN_UNKNOWN, "origin_policy": precedent.ORIGIN_POLICY}
        return rows, meta
    return precedent.closed_runs_scoped(list(origins), limit=CORPUS_LIMIT)


def _comments_for(run_ids):
    """{run_id: [comment rows]} en UNA consulta (la lista no dispara N+1). Reutiliza el SELECT de db (autor
    desde users: procedencia = la cuenta, jamás el cliente)."""
    ids = [r for r in run_ids if r]
    if not ids:
        return {}
    with db.engine().begin() as cx:
        rows = cx.execute(db._comments_select().where(db.run_comments.c.run_id.in_(ids))
                          .order_by(db.run_comments.c.created_at.asc(), db.run_comments.c.comment_id.asc())).all()
    out = {}
    for r in rows:
        v = db._comment_view(r)
        out.setdefault(v["run_id"], []).append(v)
    return out


def _plans_rows(origins, limit=CORPUS_LIMIT):
    """Planes con `council_json` (ADR-0082 E.1) vía la puerta de db (db.plans_with_council, C4) — cosido por C9 (antes
    reflexión del esquema). Si la BD conectada NO tiene la columna (db.council_schema_state: sin migrar) el estado se
    DECLARA `not-available (…)` y el índice sigue con las corridas — jamás un except silencioso. `origin`/
    `council_state` NULL = pre-ADR, declarado. Devuelve (rows, meta{state, n_rows, origins_included,
    excluded_by_origin, origin_unknown_included}) — la MISMA forma de siempre; el filtro por origen sigue siendo el de
    precedent (NULL incluido y contado), no el de db."""
    try:
        schema = db.council_schema_state()
    except Exception as e:   # tabla ausente: sólo posible sin init_db — se declara
        return [], {"state": f"errored ({type(e).__name__}: {e})", "n_rows": 0,
                    "origins_included": list(origins) if origins is not None else None,
                    "excluded_by_origin": {}, "origin_unknown_included": 0}
    if "council_json" in (schema.get("plans_missing") or []):
        return [], {"state": PLANS_STATE_NOT_AVAILABLE, "n_rows": 0,
                    "origins_included": list(origins) if origins is not None else None,
                    "excluded_by_origin": {}, "origin_unknown_included": 0}
    rows = db.plans_with_council(include_origins=None, limit=limit)   # sin filtro en SQL: el alcance lo mide precedent
    if origins is None:
        kept = rows
        meta = {"origins_included": None, "excluded_by_origin": {},
                "origin_unknown_included": sum(1 for r in rows if precedent.origin_of(r) is None)}
    else:
        kept, fm = precedent.filter_by_origin(rows, list(origins))
        meta = {"origins_included": fm["origins_included"], "excluded_by_origin": fm["excluded_by_origin"],
                "origin_unknown_included": fm["origin_unknown_included"]}
    meta.update(state="indexed" if kept else "empty", n_rows=len(rows))
    return kept, meta


def _scan(include_origins=None, env=None):
    """Recorre el corpus UNA vez: corridas cerradas del alcance + planes con council_json no consumidos.
    Devuelve {runs[] {row, frozen, items, stats}, plans[] {row, council_json, items, stats}, comments{run_id:[…]},
    meta}. `_corpus` lo aplana a ítems; `demand` lo cuenta."""
    cfg = env_config(env)
    origins, origins_source = _resolve_origins(include_origins, cfg)
    rows, meta = _closed_runs(origins)
    runs_out, run_ids = [], set()
    tally = Counter()
    max_frozen = None
    for r in rows:
        frozen, fstate = _frozen_of(r)
        if frozen is None:
            tally[f"runs_frozen_{fstate}"] += 1
            continue
        items, stats = items_from_run(r, frozen)
        tally[f"runs_council_{stats['council']}"] += 1
        runs_out.append({"row": r, "frozen": frozen, "items": items, "stats": stats})
        run_ids.add(r["run_id"])
        fa = _iso(r.get("frozen_at"))
        if fa and (max_frozen is None or fa > max_frozen):
            max_frozen = fa
    comments = _comments_for(sorted(run_ids))
    prows, pmeta = _plans_rows(origins)
    plans_out = []
    n_consumed, n_unparseable, max_plan = 0, 0, None
    for p in prows:
        if p.get("run_id") and p["run_id"] in run_ids:
            n_consumed += 1        # sus requisitos YA viajan en frozen.council de esa corrida
            continue
        try:
            cj = json.loads(p.get("council_json") or "null")
        except ValueError:
            n_unparseable += 1
            continue
        if not isinstance(cj, dict):
            n_unparseable += 1
            continue
        items, stats = items_from_plan(p, cj)
        plans_out.append({"row": p, "council_json": cj, "items": items, "stats": stats})
        ca = _iso(p.get("created_at"))
        if ca and (max_plan is None or ca > max_plan):
            max_plan = ca
    full_meta = {
        **meta,
        "origins_source": origins_source,
        "n_runs_closed_in_scope": len(rows),
        "n_runs_indexed": len(runs_out),
        "n_runs_council_with_ledger": tally["runs_council_with-ledger"],
        "n_runs_council_without_ledger": tally["runs_council_without-ledger"],
        "n_runs_council_absent": tally["runs_council_absent"],       # contrato < 1.11 o sin plan: declarado
        "n_runs_frozen_absent": tally["runs_frozen_absent"],
        "n_runs_frozen_unparseable": tally["runs_frozen_unparseable"],
        "max_frozen_at": max_frozen,
        "n_plans_indexed": len(plans_out),
        "n_plans_rows_with_council_json": pmeta["n_rows"],
        "n_plans_excluded_consumed_by_indexed_run": n_consumed,
        "n_plans_unparseable": n_unparseable,
        "plans_excluded_by_origin": pmeta["excluded_by_origin"],
        "plans_origin_unknown_included": pmeta["origin_unknown_included"],
        "plans_state": pmeta["state"],
        "max_plan_created_at": max_plan,
        "n_comments_indexed": sum(len(v) for v in comments.values()),
        "corpus_limit": CORPUS_LIMIT,
    }
    return {"runs": runs_out, "plans": plans_out, "comments": comments, "meta": full_meta}


def _corpus(include_origins=None, env=None):
    scan = _scan(include_origins, env)
    items = []
    for u in scan["runs"]:
        items.extend(u["items"])
    for u in scan["runs"]:
        items.extend(comment_items(u["row"], scan["comments"].get(u["row"]["run_id"])))
    for u in scan["plans"]:
        items.extend(u["items"])
    meta = dict(scan["meta"])
    meta["n_items_indexed"] = len(items)
    meta["n_items_by_kind"] = {k: sum(1 for i in items if i["kind"] == k) for k in KINDS}
    return items, meta


# ── scorer: sklearn TF-IDF o TF-IDF coseno en stdlib puro — ambos DECLARADOS ─────────────────────────────
def _tokens_list(s):
    return re.findall(r"[a-z0-9]+", (s or "").lower())


class _StdlibTfidf:
    """TF-IDF coseno sin dependencias: idf suavizado como sklearn (ln((1+N)/(1+df)) + 1), tf crudo, norma L2,
    sin stop-words (declarado). Es el FALLBACK cuando sklearn no importa — con nombre propio en `scorer`."""
    name = "stdlib-tfidf-fallback"

    def __init__(self, texts):
        docs = [_tokens_list(t) for t in texts]
        self.n = len(docs)
        df = Counter()
        for d in docs:
            df.update(set(d))
        self.idf = {t: math.log((1 + self.n) / (1 + c)) + 1.0 for t, c in df.items()}
        self.vectors = [self._vec(d) for d in docs]

    def _vec(self, toks):
        tf = Counter(t for t in toks if t in self.idf)
        v = {t: c * self.idf[t] for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def scores(self, q):
        qv = self._vec(_tokens_list(q))
        return [sum(qv.get(t, 0.0) * x for t, x in dv.items()) for dv in self.vectors]


def _ensure_index(include_origins=None, env=None):
    items, meta = _corpus(include_origins, env)
    # La llave de caché es la IDENTIDAD del corpus (ADR-0079: dos alcances, dos índices): tamaño, cierre más
    # reciente, planes, comentarios, alcance y lo excluido. Los `kinds` NO están en la llave: el índice se
    # construye sobre los 7 y la búsqueda filtra por kind al servir (una matriz, no 2^7).
    oi = meta["origins_included"]
    key = (len(items), meta["n_runs_indexed"], meta["max_frozen_at"], meta["n_plans_indexed"],
           meta["max_plan_created_at"], meta["n_comments_indexed"], meta["plans_state"],
           tuple(oi) if oi is not None else None, tuple(sorted(meta["excluded_by_origin"].items())),
           tuple(sorted(meta["plans_excluded_by_origin"].items())))
    if _IDX["key"] == key:
        return
    _IDX.update(key=key, items=items, meta=meta, vectorizer=None, matrix=None, stdlib=None, scorer="none")
    _IDX["n_builds"] += 1
    texts = [i["_text"] for i in items]
    if not texts:
        return
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        vec = TfidfVectorizer(stop_words="english")
        _IDX.update(vectorizer=vec, matrix=vec.fit_transform(texts), scorer="sparse-tfidf")
        return
    except Exception:
        pass
    _IDX.update(stdlib=_StdlibTfidf(texts), scorer=_StdlibTfidf.name)


def _scored(q):
    """[(item, score)] en orden DECRECIENTE de score, estable sobre el orden del corpus (determinista)."""
    items = _IDX["items"]
    if not items:
        return []
    if _IDX["scorer"] == "sparse-tfidf":
        from sklearn.metrics.pairwise import linear_kernel
        sims = linear_kernel(_IDX["vectorizer"].transform([q]), _IDX["matrix"])[0]
        scored = list(zip(items, (float(s) for s in sims)))
    elif _IDX["stdlib"] is not None:
        scored = list(zip(items, _IDX["stdlib"].scores(q)))
    else:
        scored = [(i, 0.0) for i in items]
    scored.sort(key=lambda x: -x[1])
    return scored


def _public(item):
    return {k: v for k, v in item.items() if not k.startswith("_")}


def _clamp_k(k, default=5, kmax=SEARCH_K_MAX):
    try:
        return max(1, min(int(k), kmax))
    except (TypeError, ValueError):
        return default


def _origin_declaration(meta):
    return {k: meta.get(k) for k in ("origins_included", "origins_source", "excluded_by_origin",
                                      "origin_unknown_included", "origin_unknown_label", "origin_policy",
                                      "plans_excluded_by_origin", "plans_origin_unknown_included")}


# ── las puertas ──────────────────────────────────────────────────────────────────────────────────────────
def search(q, k=5, include_origins=None, kinds=None, filters=None, env=None):
    """`GET /council/search?q=&k=&include_origins=&kinds=` (C6 cablea). Sobre de `precedent.search`:
    {index_version, scorer, corpus_state ∈ indexed | empty-corpus, n_runs_indexed, n_plans_indexed,
     n_comments_indexed, n_items_indexed, n_items_by_kind, plans_state, items[] {l, kind, run_id, run_no,
     plan_id, requirement_id?, text, text_truncated, score, admissible_as_evidence: false, why_not_admissible,
     …campos del kind}, n_items, k, kinds_included, kinds_available, filters, origins_included,
     excluded_by_origin, origin_unknown_included, …, note}.
    Lanza CouncilIndexDisabled (503) con WITT_COUNCIL_INDEX=0; CouncilIndexError (400) sin q, kind fuera del
    enum o filtro desconocido. Sólo ítems con score > 0 (el ranking no rellena con ruido)."""
    cfg = env_config(env)
    if not cfg["enabled"]:
        raise CouncilIndexDisabled({"error": "council_index_disabled",
                                    "state": "disabled (kill-switch WITT_COUNCIL_INDEX=0)",
                                    "source": cfg["enabled_source"], "index_version": INDEX_VERSION})
    if not isinstance(q, str) or not q.strip():
        raise CouncilIndexError({"error": "missing_q"})
    kinds_t = normalize_kinds(kinds)
    flt = normalize_filters(filters)
    kk = _clamp_k(k)
    _ensure_index(include_origins, env)
    out = []
    for item, s in _scored(q.strip()):
        if s <= 0:
            break
        if item["kind"] not in kinds_t or not _passes(item, flt):
            continue
        out.append((item, s))
        if len(out) >= kk:
            break
    rows = [{"l": precedent.letter_label(n), **_public(i), "score": round(float(s), 4)}
            for n, (i, s) in enumerate(out, 1)]
    meta = _IDX["meta"] or {}
    return {
        "index_version": INDEX_VERSION,
        "scorer": _IDX["scorer"],
        "corpus_state": "indexed" if _IDX["items"] else "empty-corpus",
        "n_runs_indexed": meta.get("n_runs_indexed", 0),
        "n_runs_council_with_ledger": meta.get("n_runs_council_with_ledger", 0),
        "n_runs_council_absent": meta.get("n_runs_council_absent", 0),
        "n_plans_indexed": meta.get("n_plans_indexed", 0),
        "n_plans_excluded_consumed_by_indexed_run": meta.get("n_plans_excluded_consumed_by_indexed_run", 0),
        "plans_state": meta.get("plans_state"),
        "n_comments_indexed": meta.get("n_comments_indexed", 0),
        "n_items_indexed": meta.get("n_items_indexed", 0),
        "n_items_by_kind": meta.get("n_items_by_kind", {k: 0 for k in KINDS}),
        "items": rows,
        "n_items": len(rows),
        "k": kk,
        "kinds_included": list(kinds_t),
        "kinds_available": list(KINDS),
        "filters": flt,
        **_origin_declaration(meta),
        "note": DISJOINT_NOTE,
    }


# Campos ESTRUCTURADOS que una observación previa lleva al user message de r1 (nada de prosa libre fuera del
# `text` acotado de su kind). `comment` sólo si WITT_COUNCIL_PRIOR_KINDS lo nombra (default: no).
PRIOR_FIELDS = {
    "requirement": ("requirement_id", "query_en", "source_family", "evidence_kind", "priority", "harness_state",
                    "hard_rule_gate", "n_requested_by", "n_members"),
    "coverage": ("requirement_id", "phase", "coverage_final", "n_valid_votes", "source_family", "evidence_kind"),
    "decision": ("requirement_id", "decision", "decided_by_kind", "priority", "source_family", "evidence_kind"),
    "gap_flag": (),
    "alternative": (),
    "panel_finding": ("lens", "verdict"),
    "comment": ("author", "created_at"),
}
PRIOR_COMMON_FIELDS = ("kind", "run_id", "run_no", "plan_id", "observed_at", "text", "text_truncated")


def prior_observations(question, k=None, entities=None, include_origins=None, kinds=None, env=None):
    """Las observaciones previas para la ronda 1 del plan y el `thread_context` (ADR-0082 (I)): top
    WITT_COUNCIL_PRIOR_K (clamp 0..12) con letras `P-A…`, SÓLO campos estructurados, kinds de
    WITT_COUNCIL_PRIOR_KINDS (default sin `comment`). NO lanza: `state ∈ PRIOR_STATES` (disabled con
    `disabled_reason`; empty-corpus; no-match; delivered). Devuelve
    {index_version, state, n, k, kinds, items[] {l, kind, run_id, run_no, plan_id, observed_at, text,
     text_truncated, score, admissible_as_evidence: false, …PRIOR_FIELDS[kind]}, scorer, class 'prior-art',
     instruction, origins_included, …}."""
    cfg = env_config(env)
    kinds_t = normalize_kinds(kinds) if kinds is not None else cfg["prior_kinds"]
    if k is None:
        kk, k_source = cfg["prior_k"], cfg["prior_k_source"]
    else:
        try:   # param explícito: mismo clamp 0..12 que la env (0 = ninguna, declarado)
            kk, k_source = max(PRIOR_K_MIN, min(int(k), PRIOR_K_MAX)), "param k"
        except (TypeError, ValueError):
            kk, k_source = cfg["prior_k"], f"{cfg['prior_k_source']} (param k unparseable: {k!r})"
    base = {"index_version": INDEX_VERSION, "k": kk, "k_source": k_source,
            "kinds": list(kinds_t), "kinds_source": cfg["prior_kinds_source"] if kinds is None else "param kinds",
            "items": [], "n": 0, "class": "prior-art", "admissible_as_evidence": False,
            "why_not_admissible": WHY_NOT_ADMISSIBLE, "instruction": PRIOR_ART_INSTRUCTION,
            "letter_prefix": PRIOR_LETTER_PREFIX, "scorer": "none"}
    if not cfg["enabled"]:
        return {**base, "state": "disabled", "disabled_reason": "kill-switch WITT_COUNCIL_INDEX=0"}
    if kk == 0:
        return {**base, "state": "disabled", "disabled_reason": "WITT_COUNCIL_PRIOR_K=0"}
    q = " ".join([str(question or "")] + [str(e) for e in (entities or []) if e]).strip()
    _ensure_index(include_origins, env)
    meta = _IDX["meta"] or {}
    decl = _origin_declaration(meta)
    base.update(scorer=_IDX["scorer"], n_items_indexed=meta.get("n_items_indexed", 0),
                n_runs_indexed=meta.get("n_runs_indexed", 0), n_plans_indexed=meta.get("n_plans_indexed", 0),
                plans_state=meta.get("plans_state"), **decl)
    if not _IDX["items"]:
        return {**base, "state": "empty-corpus"}
    if not q:
        return {**base, "state": "no-match", "note": "empty question: nothing to match against"}
    out = []
    for item, s in _scored(q):
        if s <= 0:
            break
        if item["kind"] not in kinds_t:
            continue
        out.append((item, s))
        if len(out) >= kk:
            break
    rows = []
    for n, (i, s) in enumerate(out, 1):
        row = {"l": PRIOR_LETTER_PREFIX + precedent.letter_label(n)}
        for f in PRIOR_COMMON_FIELDS:
            row[f] = i.get(f)
        for f in PRIOR_FIELDS[i["kind"]]:
            row[f] = i.get(f)
        row["score"] = round(float(s), 4)
        row["admissible_as_evidence"] = False
        rows.append(row)
    return {**base, "state": "delivered" if rows else "no-match", "items": rows, "n": len(rows)}


def frozen_index_block(prior):
    """`frozen.council.index {state, prior_observations_n, scorer, origins_included, kinds_included}` (J) a partir
    del resultado de prior_observations (C4/C5 lo copian al congelar)."""
    prior = prior or {}
    return {"index_version": INDEX_VERSION,
            "state": prior.get("state", "disabled"),
            "prior_observations_n": int(prior.get("n") or 0),
            "scorer": prior.get("scorer", "none"),
            "origins_included": prior.get("origins_included"),
            "kinds_included": list(prior.get("kinds") or [])}


def membership(env=None, full=None):
    """La membresía como la ve el índice (NO-SPEND, sin BD): `agent_matrix.membership_view` + los shas de las
    fichas de los sentados. C6 sirve `GET /council/membership` desde agent_matrix directamente; esto es la
    vista que el índice adjunta a sus respuestas y la que el smoke compara con catalog_cards."""
    view = agent_matrix.membership_view(env, full)
    return {**view,
            "index_version": INDEX_VERSION,
            "card_shas": {m["agent"]: m["card_sha"] for m in view["members"]},
            "catalog_module_version": catalog_cards.MODULE_VERSION,
            "source": "agent_matrix.membership_view + catalog_cards.CARDS[agent].sha"}


def _is_unsatisfiable(req):
    """(familia_o_kind_contado | None): `web`/`tooluniverse` por familia (DEMAND_SOURCE_FAMILIES, estática — la web se
    cuenta como demanda aunque haya llave, ADR-0084 F.3), `figure` por evidence_kind (ADR-0083). Estructural — no depende
    de que C2 haya escrito `harness_state` ni de la disponibilidad de hoy."""
    fam = req.get("source_family")
    if fam in DEMAND_SOURCE_FAMILIES:
        return fam
    if req.get("evidence_kind") in UNSATISFIABLE_EVIDENCE_KINDS:
        return req.get("evidence_kind")
    return None


def _latest_coverage(council, rid):
    """coverage_final del requisito en la fase más tardía juzgada (post_search si trae by_requirement, si no
    pre_search); None cuando ninguna fase lo juzgó."""
    cov = (council or {}).get("coverage") if isinstance(council, dict) else None
    if not isinstance(cov, dict):
        return None
    for phase in reversed(COVERAGE_PHASES):
        block = cov.get(phase)
        if isinstance(block, dict) and isinstance(block.get("by_requirement"), list):
            for j in block["by_requirement"]:
                if isinstance(j, dict) and j.get("requirement_id") == rid:
                    return j.get("coverage_final")
    return None


def demand(include_origins=None, env=None):
    """`GET /council/demand` (C6 cablea): el criterio MEDIDO de disparo de los sidecars ADR-0084 (web) y
    ADR-0085 (tooluniverse) y de ADR-0083 (figure), calculado por CÓDIGO sobre frozen.council de corridas
    cerradas + plans.council_json de planes nunca corridos, en el alcance de origen. Independiente del
    kill-switch del índice TF-IDF (es un conteo, no una búsqueda) — `index_enabled` viaja declarado.
    {index_version, n_runs_scanned, n_runs_council_absent, n_runs_council_without_ledger, n_plans_scanned,
     n_requirements_scanned, n_requirements_unsatisfiable_by_family {web, tooluniverse, figure},
     n_requirements_harness_state_unsatisfiable, n_runs_with_tooluniverse_uncovered, by_family_units,
     unsatisfiable_families[] (derivadas EN LA LLAMADA: lo que el harness no despacha HOY), unsatisfiable_families_source,
     demand_families[] (estáticas), demand_families_rule, web_locator_provider_state {provider, provider_source, available,
     unavailable_reason} (ADR-0084 F.3), threshold {min_runs, min_requirements, source}, fired_by_family, fired, class,
     rule, …origen}."""
    cfg = env_config(env)
    scan = _scan(include_origins, env)
    meta = scan["meta"]
    unsat_now, unsat_source = _unsatisfiable_now(env)          # ADR-0084 (F.3): disponibilidad de HOY, al lado del conteo
    by_family = Counter({f: 0 for f in DEMAND_FAMILIES})
    units_by_family = {f: {"n_runs": 0, "n_plans": 0} for f in DEMAND_FAMILIES}
    n_reqs, n_hs_unsat, n_runs_tu_uncovered = 0, 0, 0
    n_runs_scanned = 0
    for u in scan["runs"]:
        reqs = u["stats"].get("_requirements") or []
        if u["stats"]["council"] != "with-ledger":
            continue
        n_runs_scanned += 1
        fams_here, tu_open = set(), False
        for r in reqs:
            n_reqs += 1
            if str(r.get("harness_state") or "").startswith("unsatisfiable-by-harness"):
                n_hs_unsat += 1
            f = _is_unsatisfiable(r)
            if f:
                by_family[f] += 1
                fams_here.add(f)
            if r.get("source_family") == "tooluniverse" and r.get("decision") != "discard":
                cf = _latest_coverage(u["stats"].get("_council"), r.get("requirement_id"))
                if cf not in COVERED_STATES:
                    tu_open = True
        for f in fams_here:
            units_by_family[f]["n_runs"] += 1
        if tu_open:
            n_runs_tu_uncovered += 1
    for u in scan["plans"]:
        fams_here = set()
        for r in u["stats"].get("_requirements") or []:
            n_reqs += 1
            if str(r.get("harness_state") or "").startswith("unsatisfiable-by-harness"):
                n_hs_unsat += 1
            f = _is_unsatisfiable(r)
            if f:
                by_family[f] += 1
                fams_here.add(f)
        for f in fams_here:
            units_by_family[f]["n_plans"] += 1
    n_units = n_runs_scanned + len(scan["plans"])
    fired_by_family = {f: (n_units >= DEMAND_THRESHOLD["min_runs"]
                           and by_family[f] >= DEMAND_THRESHOLD["min_requirements"]) for f in DEMAND_FAMILIES}
    oi = meta["origins_included"]
    return {
        "index_version": INDEX_VERSION,
        "index_enabled": cfg["enabled"],
        "n_runs_scanned": n_runs_scanned,
        "n_runs_closed_in_scope": meta["n_runs_closed_in_scope"],
        "n_runs_council_absent": meta["n_runs_council_absent"],
        "n_runs_council_without_ledger": meta["n_runs_council_without_ledger"],
        "n_plans_scanned": len(scan["plans"]),
        "n_plans_excluded_consumed_by_indexed_run": meta["n_plans_excluded_consumed_by_indexed_run"],
        "plans_state": meta["plans_state"],
        "n_units_scanned": n_units,
        "n_requirements_scanned": n_reqs,
        "n_requirements_unsatisfiable_by_family": {f: int(by_family[f]) for f in DEMAND_FAMILIES},
        "n_requirements_unsatisfiable_total": int(sum(by_family[f] for f in DEMAND_FAMILIES)),
        "n_requirements_harness_state_unsatisfiable": n_hs_unsat,
        "n_runs_with_tooluniverse_uncovered": n_runs_tu_uncovered,
        "by_family_units": units_by_family,
        "unsatisfiable_families": list(unsat_now),
        "unsatisfiable_families_source": unsat_source,
        "unsatisfiable_evidence_kinds": list(UNSATISFIABLE_EVIDENCE_KINDS),
        "demand_families": list(DEMAND_FAMILIES),
        "demand_families_rule": DEMAND_FAMILIES_RULE,
        "web_locator_provider_state": web_locator_provider_state(env),
        "threshold": dict(DEMAND_THRESHOLD),
        "fired_by_family": fired_by_family,
        "fired": any(fired_by_family.values()),
        "class": ("medicion (frozen.council + plans.council_json, origin "
                  + (",".join(oi) if oi is not None else "all") + ")"),
        "rule": ("a requirement is counted as sidecar DEMAND when its source_family is one of DEMAND_SOURCE_FAMILIES "
                 "(" + ", ".join(DEMAND_SOURCE_FAMILIES) + " — static, ADR-0084 F.3: web counts even when the locator "
                 "has a key) or its evidence_kind is 'figure' (ADR-0083); counted over closed runs whose "
                 "frozen.council.ledger.requirements exist (n_runs_scanned) + plans with council_json not consumed by an "
                 "indexed run (n_plans_scanned), inside the origin scope; fired_by_family[f] = n_units_scanned >= min_runs "
                 "AND n_requirements_unsatisfiable_by_family[f] >= min_requirements; fired = any. "
                 "n_runs_with_tooluniverse_uncovered = runs with >= 1 tooluniverse requirement not discarded whose "
                 "latest coverage_final is not covered/covered-by-attestation (absence of a judgment counts as "
                 "open). n_requirements_harness_state_unsatisfiable is the council's own harness_state (C2), side "
                 "by side, never merged. unsatisfiable_families = what the harness cannot dispatch NOW "
                 "(search_harness.unsatisfiable_families, read at call time) and web_locator_provider_state = the web "
                 "locator's availability now — both travel apart from the static count"),
        **_origin_declaration(meta),
    }


def index_view(include_origins=None, env=None):
    """Estado del índice sin buscar (para la Bitácora y los smokes): {index_version, corpus_state, scorer,
    n_builds, …meta}."""
    cfg = env_config(env)
    if not cfg["enabled"]:
        return {"index_version": INDEX_VERSION, "state": "disabled (kill-switch WITT_COUNCIL_INDEX=0)",
                "scorer": "none", "n_builds": _IDX["n_builds"]}
    _ensure_index(include_origins, env)
    meta = _IDX["meta"] or {}
    return {"index_version": INDEX_VERSION, "state": "indexed" if _IDX["items"] else "empty-corpus",
            "corpus_state": "indexed" if _IDX["items"] else "empty-corpus",
            "scorer": _IDX["scorer"], "n_builds": _IDX["n_builds"], "kinds_available": list(KINDS),
            **{k: v for k, v in meta.items()}}


def vocabulary():
    """Los vocabularios cerrados del índice (viajan junto al dato; el gate de paridad los compara)."""
    return {"index_version": INDEX_VERSION, "kinds": list(KINDS), "prior_kinds_default": list(PRIOR_KINDS_DEFAULT),
            "corpus_states": list(CORPUS_STATES), "plans_states": list(PLANS_STATES),
            "prior_states": list(PRIOR_STATES), "scorers": list(SCORERS), "decision_kinds": list(DECISION_KINDS),
            "decided_by_kinds": list(DECIDED_BY_KINDS), "filter_keys": list(FILTER_KEYS),
            "text_caps": dict(TEXT_CAPS), "demand_families": list(DEMAND_FAMILIES),
            "demand_source_families": list(DEMAND_SOURCE_FAMILIES), "demand_families_rule": DEMAND_FAMILIES_RULE,
            "letter_prefix_prior": PRIOR_LETTER_PREFIX}

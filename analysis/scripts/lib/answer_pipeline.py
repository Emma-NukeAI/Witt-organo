"""
answer_pipeline.py — DI-first / external-fallback retrieval orchestrator (ADR-0022, slice 1b).

Given a question, gathers evidence on TWO paths:
  Path A — DATA INAMOVIBLE first: semantic query (rag_backend, live Neo4j) + resolve key entities.
  Path B — external fallback (only when A is insufficient), MULTI-SOURCE (see PATH_B_SOURCES):
             europepmc — literature search + fetch_paper full text (free, no key)
             zfin      — NATIVE zebrafish mutant/knockdown phenotypes with PMIDs, from the project's own
                         Tool Universe workspace tool (tapón 1·A, 2026-08-19). A stronger evidence tier
                         than generic literature for a pronephros claim; keys on gene SYMBOLS.
             pubmed    — literatura vía NCBI E-utilities (tapón 1·B, ADR-0062): misma query, ranking
                         distinto; dedup por PMID contra europepmc, declarado.
             tooluniverse — the PACKAGE tools; SDK-in-container medido y RECHAZADO (ADR-0062) — el
                         hook queda para un sidecar futuro.
  NEVER-STOPPER (founder rule, 2026-06-13): absence in DI never stops the answer — it TRIGGERS Path B.

Output = an auditor-ready EVIDENCE BUNDLE. This stage only gathers + routes; it does NOT audit
(slice 1c, composite-auditor) or synthesize the final answer. Sufficiency signal (v1):
  insufficient if DI has no paper/chunk evidence on the topic, OR a key entity is absent from DI.
As the human-gated re-ingest loop (slice 1d) adds papers, chunk hits appear and Path A becomes
sufficient on its own — the store reinforces itself.

Spend: Path A embeds the query (OpenAI, authorized 2026-06-13); Path B (Europe PMC) is free.
Bundle cached to mcp_cache/answer_bundle_<run_id>.json — named by run_id, NEVER by question-slug+date
(ADR-0044: a hardcoded date + 40-char slug silently overwrote bundles across users/days; the collision
rendered as a perfectly-instrumented sheet showing someone else's data).

Epistemic state travels with the bundle (ADR-0043): path_a carries `retrieval` {mode, raw_marker, n_hits,
k_requested} where `mode` is a 4-literal enum (RETRIEVAL_MODES) and NEVER None/nullable — `null` cannot
distinguish "measured clean" from "not measured". The run-level aggregate is `retrieval_summary`
(worst-of-n, declared).

ADR-0078 (higiene de Ruta A y B, 2026-09-14) — lo que cambió en este módulo:
  * Ruta A entregaba 140 chars por hit al sintetizador (el índice sí tenía el chunk entero). Ahora el
    fragmento va con WITT_PATH_A_CHARS (default 2400) y cada hit DECLARA su corte: text_offsets,
    text_sha256, text_omitted, text_hit_chars, text_source='index-hit'.
  * La query externa ya no es "símbolos ANDeados como texto libre" (medido: 'osr1 prkci pax2a' →
    PubMed 0, EPMC 1). Cada índice recibe SU sintaxis vía lib/search_queries (determinista, versionado):
    pubmed_query / epmc_query / zfin_filter viajan en el bloque path_b junto al dict completo del
    constructor (query_builder). `query_sent` se conserva (= la de Europe PMC, query_sent_scope
    'europepmc') para los lectores que ya existen.
  * Europe PMC corre por fetch_paper.search_europepmc_ledger: un fallo deja `europepmc_searched.status
    'error'` y la corrida sigue (§6 no-hang) — antes la línea 434 mataba path_b entero.
  * El CONTENIDO llega al bundle: cada paper lleva `abstract`, `text_excerpt` (regla declarada, ver
    _excerpt) y `text_provenance` ∈ {abstract, fulltext-excerpt, none}. Antes abstract y texto se
    bajaban y se tiraban (solo metadatos entraban al bundle).
  * n/retmax: se piden WITT_PATH_B_RETMAX (20) candidatos a cada fuente de literatura, se deduplican
    por PMID / PMCID / DOI normalizado y se eligen WITT_PATH_B_N_PAPERS (5) con la regla DECLARADA
    PATH_B_SELECTION_RULE; el ledger `selection` lleva n_candidates / n_selected / duplicados / los
    no elegidos (nada se tira callado).
  * ZFIN recibe timeout=min(10, presupuesto restante / 2) POR GET (dos GETs por símbolo: resolver +
    fenotipos) y las raíces anatómicas de build_zfin_filter como filtro CLIENTE por prefijo de palabra
    (server_filter=False por default: `filter.termName=a|b` se midió HTTP 400 el 2026-09-14 y la forma
    de una sola raíz sigue sin medirse; WITT_ZFIN_SERVER_FILTER=1 la activa cuando se mida); propaga al
    ledger los campos nuevos del tool (references_schema, success-no-references, phenotypes_capped_at_300,
    references_truncated, n_returned_by_api, n_phenotypes_total_scope, anatomy_filter_semantics).
  * El bloque path_b declara `ledger_version: '2'` y CONSERVA todas las llaves previas. Lo que la Traza
    de la webapp lee HOY del evento stage.path_b (medido en Traza.tsx): n_results_by_source,
    zfin_status_tally, pubmed_searched.{status, n_new, duplicates_of_europepmc}, n_papers, trigger. El
    evento gana un resumen por paper (evidence_id, source, text_provenance, cache_hit/cached_at,
    selection_rank) y selection.not_selected para que el lector humano pueda ver el ledger v2 sin el
    bundle completo (el bloque path_b íntegro vive en runs.bundle_json, no en el registro congelado).
  * Contadores: n_returned / n_new / n_candidates son ENTEROS solo cuando la fuente corrió (success |
    no-match); en not-searched / not-requested / tool-unavailable / error son null (no medido — ADR-0043).
  * Corrector 2026-09-14: n<=0 papers => las búsquedas de literatura NO se disparan y ambas fuentes
    declaran status 'not-requested'; una política de anatomía para los tres índices (unión de la pregunta
    original y la formulación EN, procedencia declarada en query_builder.*.notes.anatomy); la pregunta
    original jamás se tokeniza como texto libre (sin símbolos ni EN => 'empty' => not-searched).

Env vars (ADR-0078; defaults declarados aquí, leídos EN TIEMPO DE LLAMADA para que los gates los flipeen;
la procedencia del valor efectivo viaja en el bundle: 'env:<VAR>' | 'default-unset:<VAR>' |
'default-invalid-env:<VAR>' | 'caller'):
  WITT_PATH_A_CHARS          default 2400 — chars por hit de Ruta A que viajan al bundle/sintetizador
  WITT_PATH_B_N_PAPERS       default 5    — papers de literatura seleccionados por corrida (top-n)
  WITT_PATH_B_RETMAX         default 20   — candidatos pedidos a CADA fuente de literatura
  WITT_PATH_B_EXCERPT_CHARS  default 1500 — tope del text_excerpt por paper
  WITT_ZFIN_SERVER_FILTER    default 0    — 1 = mandar filter.termName (una GET por raíz) a Alliance
  (WITT_ZFIN_BUDGET_S 45 · WITT_ZFIN_MAX_ENTITIES 6 · WITT_ZFIN_MAX_STATEMENTS 12 ya existían, ADR-0059)

ADR-0080 (compuerta de competencia + harness, 2026-09-15) — lo que cambió en este módulo:
  * retrieve(..., search_plan=None) / path_b_bundle(..., search_plan=None, on_stage=None, existing_ids=None):
    con `search_plan` (dict de lib/search_harness.build_search_plan) la Ruta B corre por el HARNESS —
    rondas con presupuesto de reloj (WITT_SEARCH_ROUND_BUDGET_S), familias del plan (SEARCH_DISPATCH:
    europepmc, pubmed, zfin + las Layer 0 nuevas), dedup contra lo ya presente — y emite los eventos
    stage.search.plan / stage.search.round / stage.search.source vía on_stage. Los ledgers de hoy
    (europepmc_searched, pubmed_searched, zfin_searched, selection) se CONSERVAN (los llena la fila de la
    familia en la primera ronda en que corrió) y el bloque gana `search_ledger` {plan, rounds[],
    families_default, n_rounds, cap, round_budget_s, stop_reason}. Sin search_plan: comportamiento actual,
    byte a byte.
  * Segunda ronda SOLO si la primera no trajo nada nuevo (n_new_total == 0) y k < WITT_SEARCH_ROUNDS_CAP
    (search_harness.should_run_next_round, predicado declarado; con directivas en ADR-0082 cambiará).
  * Los ítems no-literatura del harness (ortólogos, expresión, ...) entran a `papers` con su `kind`,
    `source_family`, `label` ('predictive' | 'inferred-by-orthology' | null) e `identifier_provenance`; los
    candidatos de literatura entran al MISMO pool/dedup/selección de ADR-0078.

Decision pathway (explicit state machine — the route to an answer is STRUCTURAL, not contract-dependent).
REFORMED by ADR-0049 (founder decision 2026-08-09: the audit runs on 100% of runs, DI-sufficient included;
cost is measured, never capped). DI_SUFFICIENT and FALLBACK_FETCHED are now INTERMEDIATE states; the
terminal of every run is AUDIT_APPROVED | AUDIT_REJECTED:
  RETRIEVE -> Path A (DI)
     |- sufficient ----------------------> [DI_SUFFICIENT]    may_answer=N -> AUDIT (composite >=3, REQUIRED)
     |- insufficient -> Path B (external) -> [FALLBACK_FETCHED] may_answer=N -> AUDIT (composite >=3, REQUIRED)
                                                |- record_audit, approved -> [AUDIT_APPROVED] Y -> ANSWER + PROPOSE(gate)
                                                |- record_audit, none     -> [AUDIT_REJECTED]   -> ANSWER(gap) / REFINE
  The bundle's `decision_state` carries may_answer_now + required_next_action, so a consumer (agent,
  human, orchestrator) CANNOT answer without an audit verdict (record_audit()) on EITHER branch.
  The invokable panel lives in lib/composite_auditor.py (record_audit's first real caller).
  Audit + propose are wired transitions, not steps an agent is trusted to remember (CLAUDE.md §7).

CLI:
  python analysis/scripts/lib/answer_pipeline.py "Is osr1 required for zebrafish pronephros?" --entities osr1,prkci,pax2a
"""
import argparse
import datetime
import hashlib
import inspect
import json
import os
import re
import sys
import pathlib
import time
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2].parent
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
_env = ROOT / ".secrets" / "deploy.env"
if not os.environ.get("NEO4J_URI") and _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())
os.environ.setdefault("RAG_BACKEND", "neo4j")

from lib import rag_backend, resolve_id, fetch_paper, search_queries, search_harness  # noqa: E402

CACHE = ROOT / "mcp_cache"

# --- ADR-0078: tamaños y cuotas de Ruta A/B — defaults DECLARADOS aquí, leídos en tiempo de llamada -----
PATH_A_CHARS_DEFAULT = 2400          # WITT_PATH_A_CHARS  (era un literal [:140] — el sintetizador leía 140 chars)
PATH_B_N_PAPERS_DEFAULT = 5          # WITT_PATH_B_N_PAPERS (era n=2 fijo)
PATH_B_RETMAX_DEFAULT = 20           # WITT_PATH_B_RETMAX   (candidatos pedidos a cada fuente de literatura)
PATH_B_EXCERPT_CHARS_DEFAULT = 1500  # WITT_PATH_B_EXCERPT_CHARS (tope del text_excerpt por paper)
ZFIN_CALL_TIMEOUT_S = 10.0           # tope por GET a Alliance; el efectivo es min(10, presupuesto restante)
PATH_B_LEDGER_VERSION = "2"          # ADR-0078: el bloque path_b gana llaves; las previas se conservan
PATH_B_SELECTION_RULE = "oa-with-pmcid-first, then source order"
QUERY_SOURCE_PREFIX = "query-builder"  # query_source = 'query-builder-v<N>:<mode>' (lib/search_queries)
ZFIN_OK_STATES = ("success", "success-no-references")   # ADR-0078: el tool declara ambos como éxito


def _env_int_src(name, default):
    """(valor, fuente) — entero positivo desde la env `name`; vacío, no numérico o <= 0 -> `default`
    (declarado en código). fuente ∈ 'env:<name>' | 'default-unset:<name>' | 'default-invalid-env:<name>'
    (ADR-0078 corrector: un default aplicado por env inválida NO se declara como "vino de la env").
    El valor EFECTIVO y su fuente viajan en el bundle (text_cap_chars/_source, n_papers_requested/_source,
    retmax_requested/_source), así que un default aplicado nunca es invisible."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default, f"default-unset:{name}"
    try:
        v = int(raw)
    except ValueError:
        return default, f"default-invalid-env:{name}"
    if v <= 0:
        return default, f"default-invalid-env:{name}"
    return v, f"env:{name}"


def _env_int(name, default):
    """Solo el valor de _env_int_src (llamadores que no declaran la fuente)."""
    return _env_int_src(name, default)[0]


def _env_flag(name, default=False):
    """Bandera desde la env: '1'/'true'/'yes' -> True; '0'/'false'/'no' -> False; vacía -> default."""
    raw = os.environ.get(name, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


# --- retrieval-mode enum (ADR-0043) -----------------------------------------------------------
# Four EXPLICIT literals, never None/nullable: `null` cannot distinguish "measured clean" from
# "not measured", which forces any consumer (the webapp UI in particular) to paint the worst case.
RETRIEVAL_MODES = ("semantic", "degraded-dense-failed", "reduced-by-config", "not-measured")
_MODE_SEVERITY = {"semantic": 0, "reduced-by-config": 1, "not-measured": 2, "degraded-dense-failed": 3}
_MARKER_MISSING = object()   # sentinel: the result carried NO `degraded` attribute at all


def _mode_of(marker):
    """Map a raw HitList.degraded marker to the 4-literal enum. Unknown truthy markers (including the
    server-level 'sparse' timeout-fallback stamp) map to 'degraded-dense-failed' — degraded-somehow must
    never render as clean; `raw_marker` preserves the original literal untranslated."""
    if marker is _MARKER_MISSING:
        return "not-measured"
    if marker is None:
        return "semantic"
    if marker == "sparse-by-config":
        return "reduced-by-config"
    return "degraded-dense-failed"   # 'dense-failed:sparse-only', 'sparse', any unknown degradation


def _identity(bundle):
    """bundle_identity (ADR-0044): sha256 over the canonical payload (bundle minus bundle_identity), so a
    consumer can re-verify that the sheet it renders is the run it claims to be. Recomputed on every
    mutation of the bundle (record_audit re-stamps it)."""
    payload = {k: v for k, v in bundle.items() if k != "bundle_identity"}
    sha = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {"sha256": sha, "run_id": bundle.get("run_id"), "question": bundle.get("question")}


def path_a(question, k=6, max_chars=None):
    """DATA INAMOVIBLE first: live semantic retrieval + a literature-presence signal. The degradation
    marker travels ON the returned dict as `retrieval` (envelope-level, ADR-0043) — serializing only the
    hits dropped HitList.degraded silently, and with 0 hits there was nothing to stamp it on at all.

    ADR-0078: el fragmento de cada hit viaja con WITT_PATH_A_CHARS (default 2400; `max_chars` lo
    sobreescribe) y DECLARA su corte: text_offsets [0, n] sobre el texto del hit, text_sha256 del
    fragmento, text_omitted (el hit traía más), text_hit_chars (largo del hit tal cual lo sirvió el
    índice) y text_source 'index-hit' (el índice pudo haber recortado antes: esto es el hit, no el
    documento). El tope efectivo va en text_cap_chars."""
    if max_chars is None:
        cap, cap_src = _env_int_src("WITT_PATH_A_CHARS", PATH_A_CHARS_DEFAULT)
    else:
        cap, cap_src = int(max_chars), "caller"
    hits = rag_backend.query(question, k)
    marker = getattr(hits, "degraded", _MARKER_MISSING)
    serial = []
    for h in hits:
        full = h.text or ""
        frag = full[:cap]
        serial.append({"doc_id": h.doc_id, "type": h.type, "score": round(h.score, 4),
                       "text": frag,
                       "text_offsets": [0, len(frag)],
                       "text_sha256": hashlib.sha256(frag.encode("utf-8")).hexdigest(),
                       "text_omitted": len(full) > len(frag),
                       "text_hit_chars": len(full),
                       "text_source": "index-hit"})
    return {"n_hits": len(serial), "top_score": serial[0]["score"] if serial else 0.0,
            "has_literature_chunks": any(h.type == "chunk" for h in hits),
            "retrieval": {"mode": _mode_of(marker),
                          "raw_marker": None if marker is _MARKER_MISSING else marker,
                          "n_hits": len(serial), "k_requested": k},
            "text_cap_chars": cap,
            # ADR-0078 corrector: 'env:WITT_PATH_A_CHARS' | 'default-unset:…' | 'default-invalid-env:…' | 'caller'
            "text_cap_source": cap_src,
            "hits": serial}


def check_entities(entities):
    """Resolve each key entity against the verified store (feeds the auditor's absence re-check, 1c)."""
    out = {}
    for e in entities or []:
        r = resolve_id.resolve(e)
        out[e] = {"in_di": r is not resolve_id.NOT_FOUND,
                  "ensdarg": None if r is resolve_id.NOT_FOUND else r.ensdarg}
    return out


def assess_sufficiency(a, ent):
    reasons = []
    if not a["has_literature_chunks"]:
        reasons.append("DI has no paper/chunk evidence on this topic (catalog-only)")
    missing = [e for e, v in ent.items() if not v["in_di"]]
    if missing:
        reasons.append(f"key entities absent from DI: {missing}")
    return {"sufficient": not reasons, "reasons": reasons, "missing_entities": missing}


def _search_tooluniverse(question, n):
    """Tool Universe literature breadth (PubMed + many DBs) — the ADDITIONAL Path-B source beyond
    Europe PMC. Activates when the `tooluniverse` MCP is connected (agent context) or its SDK is installed.
    Not reachable from this standalone script today (SDK absent in .venv; MCP is per-session), so it returns
    [] and Europe PMC stays the dependency-free default. The explicit MCP query an agent should run is
    surfaced by tool_universe_directive() and threaded into the bundle (path_b.tool_universe_directive),
    so Tool Universe is NAMED + actionable by the agent rather than silently dropped (ADR-0022 / ADR-0026).

    NOTE (tapón 1·A/1·B): the WORKSPACE tools of `.tooluniverse/tools/` do NOT go through here — they
    are stdlib-pure and importable by path, so they run for real (_search_zfin, _search_pubmed).
    Installing the SDK in the query-service container was MEASURED and REJECTED (ADR-0062): the pinned
    1.2.6 does not even resolve on py3.12, and the latest pulls 173 packages (playwright, faiss-cpu,
    onnxruntime, …) into the container whose founding lesson is ADR-0039. If the planner someday routes
    to many package tools, the shape is a SEPARATE sidecar container over the internal network — never
    pip install into this interpreter. Until then this hook stays [] and the directive stays named."""
    return []


# --- Tool Universe workspace tools (tapón 1·A) --------------------------------------------------
# `.tooluniverse/tools/*.py` are the project's OWN tools: stdlib-pure and explicitly "importable +
# testable without the tooluniverse package installed" (their own docstrings). They are tracked in git,
# so the service container gets them with `COPY . /app`. Loading them BY PATH is required: the directory
# is dot-prefixed, hence not an importable package.
_TU_WORKSPACE = ROOT / ".tooluniverse" / "tools"
_WS_CACHE = {}


def _workspace_tool(filename, attr):
    """Load one workspace-tool callable by path. Returns None when absent/unloadable — a missing tool
    DEGRADES its source and is declared in the ledger; it never breaks a run (§6 no-hang rule)."""
    key = (filename, attr)
    if key not in _WS_CACHE:
        fn = None
        try:
            import importlib.util
            path = _TU_WORKSPACE / filename
            spec = importlib.util.spec_from_file_location(f"_witt_ws_{path.stem}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            fn = getattr(mod, attr, None)
        except Exception:
            fn = None
        _WS_CACHE[key] = fn
    return _WS_CACHE[key]


# Anatomy filter for ZFIN phenotype statements. ZFIN statements are ENGLISH; the team asks in Spanish,
# so the table maps BOTH (the LOTE-03 lesson: an index in another language returns zero and it looks
# identical to "nothing exists"). Deterministic and DECLARED — never a model deciding the filter.
# ADR-0078: el filtro que VIAJA a Alliance lo construye search_queries.build_zfin_filter (varias raíces
# OR-eadas, con borde de palabra). Esta tabla y zfin_anatomy_filter se CONSERVAN como el golden del mapeo
# ES/EN original (2026-08-19) y para lectores que las importan; _search_zfin ya no las usa.
ZFIN_ANATOMY_TERMS = (
    ("pronephr", ("pronephr", "pronefr", "prone fr")),
    ("glomer",   ("glomer", "glomér")),
    ("duct",     ("duct", "ducto", "conducto")),
    ("tubul",    ("tubul", "túbul", "tubul")),
    ("podocyte", ("podocyte", "podocito")),
    ("kidney",   ("kidney", "riñón", "rinon", "renal")),
)
ZFIN_BUDGET_S = float(os.environ.get("WITT_ZFIN_BUDGET_S", "45"))
ZFIN_MAX_ENTITIES = int(os.environ.get("WITT_ZFIN_MAX_ENTITIES", "6"))
ZFIN_MAX_STATEMENTS = int(os.environ.get("WITT_ZFIN_MAX_STATEMENTS", "12"))


def zfin_anatomy_filter(question):
    """(term, source) — the anatomy keyword sent to ZFIN, derived deterministically from the question.
    None means "no filter" (all phenotypes), which is a WIDER search, never a failed one.
    Legacy (pre ADR-0078): ONE root by first match. The wire filter is now build_zfin_filter()."""
    q = (question or "").lower()
    for term, needles in ZFIN_ANATOMY_TERMS:
        if any(nd in q for nd in needles):
            return term, "question-keyword-table"
    return None, "no-anatomy-term-in-question"


# Campos del tool ZFIN (ADR-0078) que se PROPAGAN al ledger y al item tal cual los declara el tool.
# Solo se copian si el tool los trae: un fake/tool viejo sin ellos deja la llave AUSENTE (≠ null).
_ZFIN_PROPAGATE = ("references_schema", "phenotypes_capped_at_300", "references_truncated",
                   "n_returned_by_api", "statements_truncated", "anatomy_filter_mode",
                   "n_statements_with_references", "n_statements_without_references", "references_cap",
                   # ADR-0078 corrector: alcance del total, semántica del filtro, GETs hechos, totales por raíz
                   "n_phenotypes_total_scope", "anatomy_filter_semantics", "n_http_gets", "server_filter_totals")
ZFIN_MIN_REMAINING_S = 0.5   # con menos presupuesto que esto no se dispara ninguna GET: skipped-budget


def _search_zfin(entities, question, budget_s=None, max_entities=None, max_statements=None,
                 zfin_filter=None):
    """Native zebrafish loss-of-function evidence (ZFIN via the Alliance of Genome Resources), the
    Path-B source the human-centric tools cannot provide. Symbol -> ZFIN curie -> observed mutant/
    knockdown phenotype STATEMENTS with backing PMIDs, taxon 7955, no API key.

    Returns (items, ledger):
      items  — evidence items (ONLY symbols that actually matched), same shape as the Europe PMC items
      ledger — one row PER SYMBOL ATTEMPTED with an explicit status. This is the diagnostic LOTE-03
               demanded: `no-match` ("searched, ZFIN has nothing on this anatomy") must never look like
               `error` ("the search itself failed") or like a symbol we never tried.

    Bounded by construction (§6 no-hang): a wall-clock budget stops the loop and the remaining symbols
    are recorded as `skipped-budget`. Statements per gene are capped and the truncation is DECLARED —
    a silent cut would render as "that is all ZFIN knows".

    ADR-0078:
      * `zfin_filter` (dict de search_queries.build_zfin_filter; se construye si no llega): las raíces
        anatómicas presentes en la pregunta (original + formulación EN, política única) viajan como
        `anatomy_terms`. Corrector 2026-09-14: el filtro va en el CLIENTE por prefijo de palabra
        (server_filter=False): `filter.termName=a|b` respondió HTTP 400 en vivo y la forma de una raíz
        no se ha medido; WITT_ZFIN_SERVER_FILTER=1 activa una GET por raíz cuando se mida. Sin anatomía
        -> sin filtro (búsqueda MÁS amplia). Se declara anatomy_filter_mode y, si el servidor filtró y
        devolvió 0, `detail` lo dice (un cero del servidor no se lee igual que uno del cliente).
      * Cada GET lleva timeout=min(ZFIN_CALL_TIMEOUT_S, presupuesto restante / 2) — el tool hace DOS GETs
        por símbolo (resolver + fenotipos), así que el reparto acota el símbolo completo al presupuesto.
        Se declara `timeout_s` con `timeout_s_scope: 'per-http-get'`. Con menos de ZFIN_MIN_REMAINING_S
        de presupuesto no se dispara nada: 'skipped-budget'.
      * Estados del tool: 'success' y 'success-no-references' son ÉXITO (statements con / sin PMIDs
        parseables); el segundo se conserva literal en el ledger y el item lleva has_references=false —
        "ZFIN tiene statements sin PMIDs" jamás se confunde con "la búsqueda falló".
      * Se propagan al ledger y al item los campos declarados por el tool (_ZFIN_PROPAGATE).
    """
    budget_s = ZFIN_BUDGET_S if budget_s is None else budget_s
    max_entities = ZFIN_MAX_ENTITIES if max_entities is None else max_entities
    max_statements = ZFIN_MAX_STATEMENTS if max_statements is None else max_statements

    symbols = [e.strip() for e in (entities or []) if e and e.strip()]
    query_zfin = _workspace_tool("zfin_zebrafish.py", "query_zfin")
    zf = zfin_filter if zfin_filter is not None else search_queries.build_zfin_filter(question)
    stems = list((zf.get("notes") or {}).get("stems") or [])
    anatomy = zf.get("query")                      # 'pronephr|glomer' | None (= sin filtro, declarado)
    anatomy_source = f"search_queries.build_zfin_filter:v{zf.get('builder_version')}"
    server_filter = _env_flag("WITT_ZFIN_SERVER_FILTER", False)   # ADR-0078 corrector: default cliente
    considered, over_cap = symbols[:max_entities], symbols[max_entities:]
    items, ledger = [], []

    if query_zfin is None:
        return [], [{"symbol": s, "status": "tool-unavailable",
                     "detail": f"{_TU_WORKSPACE / 'zfin_zebrafish.py'} not importable"}
                    for s in considered]
    if not symbols:
        return [], []

    t0 = time.monotonic()
    for sym in considered:
        elapsed = time.monotonic() - t0
        remaining = budget_s - elapsed
        if remaining < ZFIN_MIN_REMAINING_S:
            ledger.append({"symbol": sym, "status": "skipped-budget",
                           "detail": f"ZFIN wall-clock budget {budget_s}s exhausted "
                                     f"(remaining {max(0.0, round(remaining, 3))}s < {ZFIN_MIN_REMAINING_S}s)"})
            continue
        # dos GETs por símbolo (resolver + fenotipos): el tope por GET es la mitad del presupuesto restante
        timeout = round(min(ZFIN_CALL_TIMEOUT_S, remaining / 2.0), 3)
        try:
            res = query_zfin(sym, anatomy=None, limit=max_statements, anatomy_terms=stems,
                             server_filter=server_filter, timeout=timeout)
        except Exception as e:   # cinturón §6: un tool que lanza degrada SU símbolo, no la corrida
            res = {"status": "error", "error": f"{type(e).__name__}: {e}"}
        status = res.get("status")
        if status not in ZFIN_OK_STATES:
            ledger.append({"symbol": sym, "status": "error", "detail": str(res.get("error", ""))[:200],
                           "timeout_s": timeout, "timeout_s_scope": "per-http-get"})
            continue
        d = res["data"]
        n_matched = d.get("n_matched") or 0
        row = {"symbol": sym, "status": status if n_matched else "no-match",
               "curie": d.get("zfin_curie"), "n_matched": n_matched,
               "n_phenotypes_total": d.get("n_phenotypes_total"),
               "anatomy_filter": anatomy, "anatomy_terms": stems,
               "timeout_s": timeout, "timeout_s_scope": "per-http-get"}
        for k in _ZFIN_PROPAGATE:
            if k in d:
                row[k] = d[k]
        if (not n_matched and stems and str(d.get("anatomy_filter_mode", "")).startswith("server")
                and d.get("n_returned_by_api") == 0):
            # ADR-0078 corrector: el CERO lo produjo el filtro del servidor (ningún statement llegó al
            # cliente); el total del gen no se midió en esta ruta. Declarado, no confundible con un
            # cero del respaldo cliente sobre el payload completo.
            row["detail"] = ("server-side filter.termName returned 0 statements; gene total not measured "
                             "on this path (n_phenotypes_total_scope 'server-filtered')")
        ledger.append(row)
        if not n_matched:
            continue
        phenos = d.get("phenotypes", [])[:max_statements]
        cached = _cache_zfin(sym, res)
        zblock = {"symbol": sym, "curie": d.get("zfin_curie"), "taxon": d.get("taxon"),
                  "status": status, "has_references": status == "success",
                  "anatomy_filter": anatomy, "anatomy_filter_source": anatomy_source,
                  "anatomy_terms": stems,
                  "n_phenotypes_total": d.get("n_phenotypes_total"), "n_matched": n_matched,
                  "n_returned": len(phenos), "truncated": n_matched > len(phenos),
                  "phenotypes": phenos,
                  # the PMIDs come straight from the authoritative API, not from a model; they are
                  # RETRIEVED with provenance, NOT verified-for-citation (CLAUDE.md §7 — verify_output
                  # still gates whatever the synthesizer chooses to cite)
                  "identifier_provenance": "alliance-genome-api-live"}
        for k in _ZFIN_PROPAGATE:
            if k in d:
                zblock[k] = d[k]
        items.append({
            "source": "zfin",
            # a REAL external identifier, resolved live from the symbol (never minted) — this is what
            # the auditor's approved/rejected lists key on, so it must be unique and resolvable
            "evidence_id": d.get("zfin_curie") or f"ZFIN:unresolved:{sym}",
            "search_rec": {"pmid": None, "pmcid": None, "doi": None,
                           "title": (f"ZFIN phenotypes — {sym}"
                                     + (f" (anatomy: {anatomy})" if anatomy else " (all anatomies)")),
                           "year": None, "journal": "ZFIN via Alliance of Genome Resources",
                           "is_oa": True, "cited_by": None},
            "fetched": {"found": True, "full_text": False, "n_chunks": None,
                        "raw_cached": cached, "raw_ref": None},
            "zfin": zblock,
        })
    for sym in over_cap:
        ledger.append({"symbol": sym, "status": "skipped-cap",
                       "detail": f"more than max_entities={max_entities} symbols in the run"})
    return items, ledger


def _cache_zfin(symbol, res):
    """Persist the tool's DETERMINISTIC envelope under mcp_cache (§6 cache discipline). Named without
    the `raw_` prefix on purpose: it is one deterministic transform away from the Alliance response —
    the phenotype statements and PMIDs are verbatim, but it is not the untouched HTTP body, and this
    project does not let a near-raw artifact borrow the word `raw`."""
    try:
        CACHE.mkdir(exist_ok=True)
        date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
        slug = re.sub(r"[^a-z0-9]+", "-", symbol.lower()).strip("-") or "symbol"
        p = CACHE / f"zfin_{slug}_{date}.json"
        p.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        return [str(p.relative_to(ROOT))]
    except Exception:
        return []


def n_results_by_source(papers, sources=None, ran_sources=None):
    """Per-source result counts for the bundle + the event payload (ADR-0057 made the total auditable;
    per-source is what distinguishes 'this source found nothing' from 'this source never ran'). ONE
    implementation, called from both Path-B trigger sites — a re-derived counter drifts.

    ADR-0078 corrector: the explicit 0 is stamped ONLY for the literature sources that were REQUESTED
    (`sources`; default = both, the legacy behaviour): a source that was not asked for is ABSENT from
    the dict, not a 0 ('0 explícito' ≠ 'no se pidió').

    ADR-0080 corrector: with the harness, `ran_sources` = the families whose ledger row MEASURED
    (status success | no-match) — each of them gets its explicit 0 too (zfin_expression that scanned the
    table and found nothing is a 0, not an absence); families that were skipped / unavailable / errored
    stay ABSENT (they did not measure)."""
    counts = {}
    for p in papers or []:
        src = p.get("source") or "unknown"
        counts[src] = counts.get(src, 0) + 1
    requested = ("europepmc", "pubmed") if sources is None else tuple(sources)
    for src in ("europepmc", "pubmed"):
        if src in requested:
            counts.setdefault(src, 0)   # la fuente corrió (o se declaró) en este path_b: 0 explícito
    for src in ran_sources or ():
        counts.setdefault(src, 0)       # ADR-0080: la familia MIDIÓ (success | no-match) -> 0 explícito
    return counts


def tool_universe_directive(question, n=2):
    """The explicit Tool Universe query an agent should run via the connected `tooluniverse` MCP when Path B
    triggers (R4 / ADR-0026). The standalone pipeline cannot reach the MCP (per-session; SDK absent in
    .venv), so instead of silently dropping Tool Universe this NAMES the exact call — the orchestrating
    agent executes it and merges hits (source='tooluniverse') through the SAME composite-auditor gate
    (ADR-0022) before any answer/propose. Live execution requires the MCP connected (reopen Claude Code +
    approve .mcp.json); it is NOT verifiable from this standalone script."""
    return {
        "requires_mcp": "tooluniverse (uvx tooluniverse; project-scoped .mcp.json)",
        "tools": ["PubMed_search_articles", "EuropePMC_search", "tooluniverse-literature-deep-research"],
        "query": question,
        "n": n,
        "merge_back": ("add hits as path_b papers with source='tooluniverse', then route through the SAME "
                       "composite-auditor Mode 1 (>=3) audit gate (ADR-0022) before any answer/propose"),
        "live": False,
        "note": "Not executed by this standalone script (MCP is per-session). Surfaced for the agent to run.",
    }


# --- ADR-0078: constructor de queries POR FUENTE ---------------------------------------------------
def build_source_queries(question, entities=None, query=None, query_source=None):
    """Las TRES queries de la Ruta B, construidas por lib/search_queries (determinista, versionado) a
    partir de la pregunta, los símbolos y — si el llamador la trae — una formulación en inglés.

    `query` / `query_source` son la interfaz legada de path_b/path_b_bundle:
      * query_source 'synthesizer' (u otro literal que no empiece por 'query-builder'): `query` es la
        formulación EN del llamador y alimenta al constructor como question_en (detección anatómica y,
        sin símbolos, los términos de texto libre). Se declara en inputs.question_en_source.
      * query_source None con query: idem, declarado como 'caller'.
      * query_source 'query-builder-…': la query venía de este mismo constructor (runs.py la obtuvo de
        build_external_query y la devuelve) — se RECONSTRUYE de la pregunta+símbolos; misma cadena.
    Devuelve el dict de search_queries.build_all + `query_source` ('query-builder-v<N>:<mode>') +
    `inputs` {question, question_en, question_en_source, entities}. Una query None en alguna fuente es
    AUSENCIA DECLARADA (nada que buscar): esa fuente queda 'not-searched', jamás se manda vacía."""
    question_en, question_en_source = None, None
    q = str(query).strip() if query is not None else ""
    if q:
        if query_source is None:
            question_en, question_en_source = q, "caller"
        elif not str(query_source).startswith(QUERY_SOURCE_PREFIX):
            question_en, question_en_source = q, str(query_source)
    ents = [str(e).strip() for e in (entities or []) if e and str(e).strip()]
    qb = search_queries.build_all(ents, question_en=question_en, question=question)
    mode = ((qb.get("europepmc") or {}).get("notes") or {}).get("mode")
    qb["query_source"] = f"{QUERY_SOURCE_PREFIX}-v{qb.get('builder_version')}:{mode}"
    qb["inputs"] = {"question": question, "question_en": question_en,
                    "question_en_source": question_en_source, "entities": ents}
    return qb


def build_external_query(question, entities=None, question_en=None):
    """(query_sent, query_source) — the query actually SENT to Europe PMC (ADR-0057 → ADR-0078).
    Europe PMC is an ENGLISH biomedical index: sending the team's Spanish question verbatim returns ZERO
    results (verified live: ES→0, EN→3, entities→3 — production run 99986dbb), and symbols AND-ed as free
    text return ~0 too ('osr1 prkci pax2a' → PubMed 0, EPMC 1, medido 2026-09-13). The query now comes
    from lib/search_queries (native syntax per index). This 2-tuple is kept for the existing callers
    (runs.py, gates); it is the EUROPE PMC query (scope 'europepmc') — build_source_queries() returns all
    three. `query_source` is 'query-builder-v<N>:<mode>' (mode: symbols | question-only | empty)."""
    qb = build_source_queries(question, entities, query=question_en, query_source=None)
    return qb["europepmc"]["query"], qb["query_source"]


PATH_B_SOURCES = ("europepmc", "pubmed", "zfin", "tooluniverse")
_SEARCH_REC_KEYS = ("pmid", "pmcid", "doi", "title", "year", "journal", "is_oa", "cited_by")


def _search_europepmc(query, retmax, timeout=None):
    """(records, ledger) — Europe PMC vía fetch_paper.search_europepmc_ledger (ADR-0078): NUNCA lanza.
    status ∈ success | no-match | error | not-searched | tool-unavailable. `not-searched` = el
    constructor no produjo query (nada que buscar, declarado); `error` = la red/JSON falló y la corrida
    sigue con las demás fuentes (§6 no-hang). `timeout` (ADR-0080 corrector): tope de socket por GET que el
    harness deriva del presupuesto de la familia; None = el default del módulo (fetch_paper.HTTP_TIMEOUT_S);
    viaja sólo si la función lo acepta (los fakes de los smokes conservan la firma vieja)."""
    # ADR-0078 corrector: n_returned es un ENTERO solo cuando la búsqueda corrió; None = no medido
    base = {"source": "europepmc", "query_sent": query, "retmax_sent": retmax,
            "n_found": None, "n_returned": None}
    if not query:
        return [], dict(base, status="not-searched",
                        detail="query builder produced no Europe PMC query (nothing to search)")
    fn = getattr(fetch_paper, "search_europepmc_ledger", None)
    if fn is None:
        return [], dict(base, status="tool-unavailable",
                        detail="fetch_paper.search_europepmc_ledger not available")
    try:
        kw = {}
        if timeout is not None and _fn_accepts(fn, "timeout"):
            kw["timeout"] = timeout
        recs, led = fn(query, n=retmax, sort=None, synonym=True, **kw)
    except Exception as e:   # la función promete no lanzar; la corrida no depende de la promesa (§6)
        return [], dict(base, status="error", detail=f"{type(e).__name__}: {str(e)[:200]}")
    out = dict(led or {})
    out.setdefault("source", "europepmc")
    if timeout is not None:
        out["timeout_s_sent"] = timeout if _fn_accepts(fn, "timeout") else None
    out.setdefault("query_sent", query)
    out["retmax_sent"] = retmax
    if out.get("status") == "error":
        out["n_returned"] = None   # un fallo no devolvió 0: no midió (ADR-0043)
        if "detail" not in out:
            out["detail"] = out.get("error")
    return list(recs or []), out


def _fn_accepts(fn, name):
    """¿La firma de `fn` acepta la llave `name` (o **kwargs)? Inspección, no try/except (patrón _call_with_optional)."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    return name in params or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


def _search_pubmed(query, retmax, existing_ids, timeout=None):
    """PubMed directo (tapón 1·B, ADR-0062) vía la workspace tool — la primera llamada que nombra el
    directive (`PubMed_search_articles`), corriendo en Layer 0 en vez del SDK (medido y rechazado:
    173 paquetes, y la versión pineada ni resuelve en 3.12).

    Europe PMC INDEXA PubMed: la cobertura se solapa casi por completo — lo que esta fuente agrega es
    DIVERSIDAD DE RANKING (el best-match de PubMed sube papers distintos al top-k) e independencia de
    fuente. Por eso el dedup por PMID es obligatorio: sin él, el mismo paper entra dos veces a la
    evidencia y el sintetizador lo cuenta doble. El dedup se DECLARA en el ledger, nunca es silencioso.

    ADR-0078: se piden `retmax` registros (query_pubmed(query, retmax=…)); esta función devuelve
    CANDIDATOS (source, evidence_id, search_rec) sin bajar nada — la selección top-n y el fetch los hace
    path_b sobre el pool deduplicado. Al ledger pasan los campos que el tool declara: query_sent,
    retmax_sent, ncbi_identity, throttle, retries_429, rate_limit_headers, http_status (solo si vienen).

    Returns (candidates, ledger_row)."""
    # ADR-0078 corrector: contadores None hasta que la búsqueda corra (not-searched / tool-unavailable /
    # error los dejan None: no medido ≠ 0 medido, ADR-0043)
    row = {"query_sent": query, "retmax_sent": retmax, "n_found_total": None, "n_returned": None,
           "n_new": None, "duplicates_of_europepmc": None}
    if not query:
        return [], dict(row, status="not-searched",
                        detail="query builder produced no PubMed term (nothing to search)")
    query_pubmed = _workspace_tool("pubmed_literature.py", "query_pubmed")
    if query_pubmed is None:
        return [], dict(row, status="tool-unavailable",
                        detail=f"{_TU_WORKSPACE / 'pubmed_literature.py'} not importable")
    try:
        kw = {}
        if timeout is not None and _fn_accepts(query_pubmed, "timeout"):
            kw["timeout"] = timeout   # ADR-0080 corrector: el presupuesto de la familia acota cada GET del tool
        res = query_pubmed(query, retmax=retmax, **kw)
    except Exception as e:   # cinturón §6
        res = {"status": "error", "error": f"{type(e).__name__}: {e}"}
    data = res.get("data") or {}
    if timeout is not None:
        row["timeout_s_sent"] = timeout if _fn_accepts(query_pubmed, "timeout") else None
    row["query_sent"] = data.get("query_sent", query)
    row["retmax_sent"] = data.get("retmax_sent", retmax)
    for k in ("ncbi_identity", "throttle", "retries_429", "rate_limit_headers", "http_status"):
        if k in res:
            row[k] = res[k]
    if res.get("status") != "success":
        return [], dict(row, status="error", detail=str(res.get("error", ""))[:200])
    records = data.get("records", [])
    cands, dupes = [], []
    for rec in records:
        ident = f"PMID:{rec['pmid']}" if rec.get("pmid") else None
        if not ident:
            continue
        if ident in existing_ids:
            dupes.append(ident)   # ya entró por europepmc — declarado, no duplicado ni tirado callado
            continue
        cands.append({
            "source": "pubmed",
            "evidence_id": ident,
            "search_rec": {"pmid": rec.get("pmid"), "pmcid": None, "doi": None,
                           "title": rec.get("title"), "year": rec.get("year"),
                           "journal": rec.get("journal"), "is_oa": None, "cited_by": None},
            "abstract": None,   # esummary no trae abstract; fetch_external lo aporta si el paper se elige
        })
    row.update(status="success" if records else "no-match",
               n_found_total=data.get("n_found_total"), n_returned=len(records), n_new=len(cands),
               duplicates_of_europepmc=dupes,
               ranking="pubmed-relevance (diversidad frente al ranking de EPMC)")
    return cands, row


def _fetch_or_declare(ident, want_full_text):
    """fetch_external envuelto (§6 no-hang): un timeout de red bajando UN paper degrada ESE item
    (`found: false` + el error declarado), jamás tumba path_b completo. Lo destapó la verificación en
    vivo del 2026-08-20: un read-timeout de EPMC mató el bloque entero."""
    try:
        return fetch_paper.fetch_external(ident, want_full_text=want_full_text)
    except Exception as e:
        return {"found": False, "fetch_error": f"{type(e).__name__}: {str(e)[:160]}"}


# --- ADR-0078: pool de candidatos, dedup declarado, selección top-n --------------------------------
def _normalize_doi(doi):
    """DOI en minúsculas sin prefijo de resolver (https://doi.org/, dx.doi.org, doi:). None si vacío."""
    d = str(doi or "").strip().lower()
    for pre in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if d.startswith(pre):
            d = d[len(pre):]
    return d or None


def _candidate_keys(rec):
    """Las llaves por las que un candidato se considera EL MISMO paper: PMID, PMCID y DOI normalizado."""
    keys = []
    if rec.get("pmid"):
        keys.append(f"PMID:{rec['pmid']}")
    if rec.get("pmcid"):
        keys.append(f"PMCID:{str(rec['pmcid']).upper()}")
    d = _normalize_doi(rec.get("doi"))
    if d:
        keys.append(f"DOI:{d}")
    return keys


def _epmc_candidate(rec):
    ident = (f"PMID:{rec['pmid']}" if rec.get("pmid")
             else (rec.get("pmcid") or rec.get("doi")
                   or (f"EPMC:{rec['epmc_id']}" if rec.get("epmc_id") else None)))
    return {"source": "europepmc", "evidence_id": ident,
            "search_rec": {k: rec.get(k) for k in _SEARCH_REC_KEYS},
            "abstract": rec.get("abstract")}


def _pool_add(pool, seen, cand, duplicates):
    """Mete el candidato al pool si NINGUNA de sus llaves se vio antes; si alguna sí, lo registra en
    `duplicates` (de quién es duplicado y por qué llave). Devuelve 1 si entró, 0 si no."""
    keys = _candidate_keys(cand["search_rec"]) or [cand.get("evidence_id") or f"anon:{len(pool)}"]
    hit = next((k for k in keys if k in seen), None)
    if hit is not None:
        duplicates.append({"duplicate": cand.get("evidence_id"), "source": cand["source"],
                           "of": seen[hit], "matched_key": hit})
        return 0
    for k in keys:
        seen[k] = cand.get("evidence_id")
    cand["dedup_keys"] = keys
    pool.append(cand)
    return 1


def _select_top_n(pool, n, sources):
    """PATH_B_SELECTION_RULE: primero los Open Access con PMCID (texto completo alcanzable), luego el
    orden de fuentes de `sources`, luego el orden de llegada. Estable y declarado. Devuelve
    (seleccionados con selection_rank 1..n, evidence_ids NO seleccionados)."""
    rank = {s: i for i, s in enumerate(sources)}

    def _key(i):
        c = pool[i]
        sr = c["search_rec"]
        oa_pmc = bool(sr.get("is_oa")) and bool(sr.get("pmcid"))
        return (0 if oa_pmc else 1, rank.get(c["source"], len(rank)), i)

    order = sorted(range(len(pool)), key=_key)
    chosen = order[:max(0, int(n))]
    for r, i in enumerate(chosen, 1):
        pool[i]["selection_rank"] = r
    return [pool[i] for i in chosen], [pool[i].get("evidence_id") for i in order[len(chosen):]]


# --- ADR-0078: el CONTENIDO del paper viaja al bundle ------------------------------------------------
_FETCHED_ALWAYS = ("found", "full_text", "n_chunks", "raw_cached", "raw_ref")
_FETCHED_WHEN_PRESENT = ("fetch_error", "note", "cache_hit", "cached_at", "cached_at_source",
                         "cache_age_days", "cache_ttl_days", "fetched_at", "search_ledger")
EXCERPT_RULES = ("full", "head", "top-paragraphs-by-lexical-overlap", "none")
TEXT_PROVENANCES = ("abstract", "fulltext-excerpt", "none")


def _fetched_view(got):
    """La vista `fetched` del item: las 5 llaves de siempre SIEMPRE (None si el fetch no las trajo) y las
    de ADR-0078 (caché, fetched_at, search_ledger, fetch_error) SOLO si el fetch las declaró — así un
    stub o un fetch viejo deja la llave AUSENTE, que no es lo mismo que cache_hit=false."""
    out = {k: got.get(k) for k in _FETCHED_ALWAYS}
    for k in _FETCHED_WHEN_PRESENT:
        if k in got:
            out[k] = got[k]
    return out


def _cached_text(got):
    """Texto plano cacheado por fetch_external (raw_paper_<id>_<stamp>.txt; abstract o texto completo,
    lo que se bajó), leído del disco. None = no hay .txt o no se pudo leer (el item lo declara con
    text_provenance)."""
    for p in (got.get("raw_cached") or []):
        if str(p).lower().endswith(".txt"):
            path = pathlib.Path(str(p))
            if not path.is_absolute():
                path = ROOT / path
            try:
                return path.read_text(encoding="utf-8")
            except Exception:
                return None
    return None


def _excerpt(text, terms, cap):
    """(excerpt, rule, omitted) — el recorte del texto de un paper, con regla DETERMINISTA y declarada:
      'full'  — el texto cabe entero en `cap` chars: va íntegro (omitted=False).
      'top-paragraphs-by-lexical-overlap' — párrafos (separados por línea en blanco) puntuados por el
         número de términos de la query (símbolos + anatomía + términos de la pregunta, >=3 chars,
         substring case-insensitive) que contienen; se ordenan por puntaje desc y posición asc, se toman
         en ese orden hasta llenar `cap`, y se EMITEN EN ORDEN DEL DOCUMENTO, recortados a `cap`.
      'head'  — ningún párrafo comparte términos con la query (o no hay términos): primeros `cap` chars.
    omitted=True siempre que el excerpt sea más corto que el texto de origen. Sin modelo, sin azar."""
    text = (text or "").strip()
    if not text:
        return None, "none", False
    if len(text) <= cap:
        return text, "full", False
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    toks = [t for t in (terms or []) if len(t) >= 3]
    scores = [sum(1 for t in toks if t in p.lower()) for p in paras]
    if not toks or not scores or max(scores) == 0:
        return text[:cap], "head", True
    order = sorted(range(len(paras)), key=lambda i: (-scores[i], i))
    chosen, used = [], 0
    for i in order:
        if scores[i] == 0 or used >= cap:
            break
        chosen.append(i)
        used += len(paras[i]) + 2
    chosen.sort()
    out = "\n\n".join(paras[i] for i in chosen)[:cap]
    return out, "top-paragraphs-by-lexical-overlap", True


def _query_terms(qb):
    """Términos de la query (símbolos usados + anatomía + términos de pregunta) para el solapamiento
    léxico de _excerpt. Minúsculas, >=3 chars, sin duplicados, orden estable."""
    e = (qb or {}).get("europepmc") or {}
    raw = (list(e.get("symbols_used") or []) + list(e.get("anatomy_terms_used") or [])
           + list((e.get("notes") or {}).get("question_terms") or []))
    out = []
    for t in raw:
        t = str(t).lower().strip()
        if len(t) >= 3 and t not in out:
            out.append(t)
    return out


def _paper_content(abstract, got, terms, cap):
    """Los campos de CONTENIDO de un item (ADR-0078). text_provenance:
      'fulltext-excerpt' — hay .txt cacheado y fetched.full_text=True: excerpt del texto completo
      'abstract'         — excerpt del abstract (del .txt cacheado sin full text, o del search_rec/record)
      'none'             — no hubo texto alguno (declarado; el item sigue con sus metadatos)."""
    rec = got.get("record") or {}
    abstract = abstract or rec.get("abstract") or None
    txt = _cached_text(got)
    if txt and got.get("full_text"):
        excerpt, rule, omitted = _excerpt(txt, terms, cap)
        prov, src_chars = "fulltext-excerpt", len(txt)
    elif txt:
        excerpt, rule, omitted = _excerpt(txt, terms, cap)
        prov, src_chars = "abstract", len(txt)
    elif abstract:
        excerpt, rule, omitted = _excerpt(abstract, terms, cap)
        prov, src_chars = "abstract", len(abstract)
    else:
        excerpt, rule, omitted, prov, src_chars = None, "none", False, "none", 0
    return {"abstract": abstract, "text_excerpt": excerpt, "text_provenance": prov,
            "text_excerpt_rule": rule, "text_excerpt_chars": len(excerpt or ""),
            "text_excerpt_omitted": omitted, "text_source_chars": src_chars,
            "text_excerpt_cap_chars": cap}


def _paper_item(cand, full_text, terms, excerpt_chars):
    """Un candidato SELECCIONADO se convierte en item del bundle: se baja (fetch_external, §6 envuelto)
    y se le adjunta el contenido declarado."""
    ident = cand.get("evidence_id")
    got = _fetch_or_declare(ident, full_text) if ident else {"found": False}
    content = _paper_content(cand.get("abstract"), got, terms, excerpt_chars)
    item = {"source": cand["source"], "evidence_id": ident or "paper",
            "search_rec": cand["search_rec"], "fetched": _fetched_view(got),
            "selection_rank": cand.get("selection_rank"), "dedup_keys": cand.get("dedup_keys", [])}
    item.update(content)
    return item


def path_b(question, n=None, full_text=True, sources=PATH_B_SOURCES, query=None, entities=None,
           ledger_out=None, query_source=None, queries=None, retmax=None, search_plan=None, on_stage=None,
           existing_ids=None):
    """External fallback — MULTI-SOURCE, never a stopper. Each item records its `source`:
      europepmc   — literature (built-in, dependency-free)
      pubmed      — literatura vía NCBI E-utilities (tapón 1·B, ADR-0062): MISMA pregunta, sintaxis y
                    ranking propios; dedup por PMID contra europepmc, declarado en el ledger.
      zfin        — NATIVE zebrafish loss-of-function phenotypes (tapón 1·A): a STRONGER evidence tier
                    than generic literature for a pronephros claim, and invisible to the human-centric
                    tools. Needs `entities` (gene symbols), not a free-text query.
      tooluniverse— the PACKAGE tools. El SDK en el contenedor se MIDIÓ y se rechazó (ADR-0062);
                    este hook queda para un sidecar futuro, no para pip install aquí.

    ADR-0078: `n` (WITT_PATH_B_N_PAPERS, 5) papers de literatura seleccionados de un pool de hasta
    `retmax` (WITT_PATH_B_RETMAX, 20) candidatos POR FUENTE, deduplicados por PMID/PMCID/DOI y elegidos
    con PATH_B_SELECTION_RULE. Solo los seleccionados se bajan. `queries` = el dict de
    build_source_queries (si no llega, se construye de question/entities/query/query_source).
    `ledger_out` (dict, optional): side channel for per-source search ledgers — europepmc_searched,
    pubmed_searched, zfin_searched, selection — the diagnostic that keeps "searched and found nothing"
    distinguishable from "the search failed".

    ADR-0080: `search_plan` (dict de search_harness.build_search_plan) desvía la Ruta B al harness
    (_path_b_harness): rondas con presupuesto, familias del plan, eventos stage.search.* vía `on_stage`,
    dedup contra `existing_ids`. Sin plan, este cuerpo es el de ADR-0078 sin cambios.

    This function is the ONE seam the offline gates stub: everything that touches the network lives
    here, so a stubbed path_b is a genuinely offline run."""
    n = _env_int("WITT_PATH_B_N_PAPERS", PATH_B_N_PAPERS_DEFAULT) if n is None else int(n)
    retmax = _env_int("WITT_PATH_B_RETMAX", PATH_B_RETMAX_DEFAULT) if retmax is None else int(retmax)
    excerpt_chars = _env_int("WITT_PATH_B_EXCERPT_CHARS", PATH_B_EXCERPT_CHARS_DEFAULT)
    if search_plan is not None:
        return _path_b_harness(question, search_plan, n=n, full_text=full_text, retmax=retmax,
                               excerpt_chars=excerpt_chars, ledger_out=ledger_out, on_stage=on_stage,
                               existing_ids=existing_ids, qb=queries)
    qb = queries or build_source_queries(question, entities, query=query, query_source=query_source)
    ledger = ledger_out if ledger_out is not None else {}
    terms = _query_terms(qb)
    pool, seen, duplicates = [], {}, []
    ran = ("success", "no-match")   # solo estos estados MIDIERON: sus contadores son enteros
    if n <= 0:
        # ADR-0078 corrector: cero papers pedidos => cero red de literatura; declarado, no disparado en vano
        for src, key in (("europepmc", "europepmc_searched"), ("pubmed", "pubmed_searched")):
            if src in sources:
                ledger[key] = {"source": src, "status": "not-requested", "detail": f"n_papers={n} <= 0",
                               "query_sent": (qb.get(src) or {}).get("query"), "retmax_sent": retmax,
                               "n_found": None, "n_returned": None, "n_candidates": None}
                if src == "pubmed":
                    ledger[key].update(n_found_total=None, n_new=None, duplicates_of_europepmc=None)
    else:
        if "europepmc" in sources:
            recs, led = _search_europepmc((qb.get("europepmc") or {}).get("query"), retmax)
            added = sum(_pool_add(pool, seen, _epmc_candidate(rec), duplicates) for rec in recs)
            led["n_candidates"] = added if led.get("status") in ran else None
            ledger["europepmc_searched"] = led
        if "pubmed" in sources:
            cands, row = _search_pubmed((qb.get("pubmed") or {}).get("query"), retmax, seen)
            added = sum(_pool_add(pool, seen, c, duplicates) for c in cands)
            row["n_candidates"] = added if row.get("status") in ran else None
            for d in row.get("duplicates_of_europepmc") or []:
                duplicates.append({"duplicate": d, "source": "pubmed", "of": seen.get(d), "matched_key": d})
            ledger["pubmed_searched"] = row
    selected, not_selected = _select_top_n(pool, n, sources)
    ledger["selection"] = {"rule": PATH_B_SELECTION_RULE, "n_requested": n, "retmax": retmax,
                           "n_candidates": len(pool), "n_selected": len(selected),
                           "n_duplicates": len(duplicates), "duplicates": duplicates,
                           "not_selected": not_selected,
                           "dedup_keys": "PMID · PMCID · DOI (lower, sin prefijo https://doi.org/)"}
    papers = [_paper_item(c, full_text, terms, excerpt_chars) for c in selected]
    if "zfin" in sources:
        zfin_items, zfin_ledger = _search_zfin(entities, question, zfin_filter=qb.get("zfin"))
        papers += zfin_items
        ledger["zfin_searched"] = zfin_ledger
    if "tooluniverse" in sources:
        papers += _search_tooluniverse(question, n)  # documented breadth hook (live when MCP/SDK present)
    return papers


# --- ADR-0080: la Ruta B por el harness (rondas con presupuesto, familias del plan) -----------------
_LEGACY_LEDGER_KEYS = {"europepmc": "europepmc_searched", "pubmed": "pubmed_searched", "zfin": "zfin_searched"}
SEARCH_STOP_REASONS = ("found-new", "rounds-cap", "no-families", "no-new-inputs")
# 'no-new-inputs' (ADR-0080 corrector): la ronda k no admitió nada Y ningún insumo de familia cambió -> la ronda
# k+1 sería la MISMA búsqueda byte a byte; no se re-ejecuta (k < cap y todo).


def _plan_with_queries(plan, qb):
    """Copia superficial del plan con el dict del constructor `qb` como ÚNICA fuente de las queries de
    literatura/ZFIN (ADR-0078: una query que ya salió del constructor se reconstruye, no se reinterpreta).
    Las cadenas del plan y las de qb son byte-idénticas cuando ambos nacieron de los mismos insumos; si el
    llamador trajo una formulación EN distinta (query/query_source), la de qb manda y se declara."""
    out = dict(plan)
    out["query_builder"] = qb
    queries = dict(plan.get("queries") or {})
    for fam, key in (("europepmc", "europepmc"), ("pubmed", "pubmed")):
        if fam in queries:
            q = dict(queries[fam])
            new_q = (qb.get(key) or {}).get("query")
            if q.get("query") != new_q:
                q["query_plan"], q["query_replaced_by"] = q.get("query"), "path_b_bundle:query_builder"
            q["query"] = new_q
            queries[fam] = q
    if "zfin" in queries:
        q = dict(queries["zfin"])
        q["anatomy_filter"] = (qb.get("zfin") or {}).get("query")
        queries["zfin"] = q
    out["queries"] = queries
    return out


def _path_b_harness(question, plan, n, full_text, retmax, excerpt_chars, ledger_out=None, on_stage=None,
                    existing_ids=None, qb=None):
    """Ruta B vía lib/search_harness (ADR-0080 C). Devuelve `papers` y llena `ledger_out` con los ledgers de hoy
    (europepmc_searched / pubmed_searched / zfin_searched / selection) + `search_ledger`.

    Lazo de rondas (código, no modelo): k = 1..cap; tras cada ronda, otra SOLO si
    search_harness.should_run_next_round(k, n_admitted, cap, inputs_changed) — n_admitted = lo que ENTRÓ al pool
    o a los ítems (un candidato rechazado por _pool_add por PMID/PMCID/DOI no cuenta como nuevo aunque su
    evidence_id fuera distinto) e inputs_changed = la firma de insumos por familia (search_harness.inputs_signature)
    cambió durante la ronda (corrector ADR-0080; sin insumos nuevos no hay ronda 2: stop_reason
    'no-new-inputs'). Cada familia deja su fila; los candidatos de
    literatura ('literature-candidate') entran al pool/dedup/selección de ADR-0078 y solo los elegidos se
    bajan; los ítems de las demás familias entran a `papers` tal cual (normalizados, con kind/label/
    identifier_provenance). Los ledgers legados los llena la PRIMERA ronda en que la familia corrió; las
    rondas completas viven en search_ledger.rounds[]. Eventos (vía on_stage(name, payload)): 'search.plan',
    'search.source' (por familia), 'search.round' (por ronda)."""
    def _stage(name, payload):
        if on_stage:
            on_stage(name, payload)

    ledger = ledger_out if ledger_out is not None else {}
    if qb is None:
        qb = plan.get("query_builder") or build_source_queries(question, plan.get("symbols") or [],
                                                                query=plan.get("question_en"), query_source=None)
    plan = _plan_with_queries(plan, qb)
    terms = _query_terms(qb)
    cap = int(plan.get("rounds_cap") or search_harness.ROUNDS_CAP_DEFAULT)
    round_budget = float(plan.get("round_budget_s") or search_harness.ROUND_BUDGET_S_DEFAULT)
    families = list(plan.get("families") or [])
    _stage("search.plan", search_harness.plan_event_payload(plan))

    pool, seen, duplicates = [], {}, []
    other_items, rounds = [], []
    present = set(existing_ids or [])
    # pubmed_seen es un dict PROPIO de la ronda (evidence_id -> evidence_id): `seen` del pool va por llaves
    # PMID/PMCID/DOI y compartirlo haría que _pool_add leyera como duplicado lo que la propia ronda admitió
    # 'curies' se pre-crea (corrector ADR-0080): run_round copia el ctx superficialmente y una llave ausente se
    # creaba sólo en la copia — las curies ZFIN resueltas se perdían entre rondas (monarch jamás las veía)
    ctx = {"retmax": retmax, "n_papers": n, "literature_requested": n > 0, "pubmed_seen": {}, "dois": [], "curies": []}
    stop_reason = "no-families" if not families else None
    dup_seen = set()
    prev_inputs = {}   # {familia: insumos consumidos en rondas anteriores} — lo que NO se re-ejecuta
    k = 0
    while families:
        k += 1
        rd = search_harness.run_round(plan, k, round_budget,
                                      on_source=lambda row: _stage("search.source", search_harness.source_event_payload(row)),
                                      existing_ids=present, trigger="initial" if k == 1 else "no-new-in-previous-round",
                                      ctx=ctx, previous_inputs=prev_inputs or None)
        for row in rd["sources"]:
            key = _LEGACY_LEDGER_KEYS.get(row.get("family"))
            if key and key not in ledger and "ledger" in row:
                ledger[key] = row["ledger"]
            if row.get("family") == "pubmed" and isinstance(row.get("ledger"), dict):
                for d in row["ledger"].get("duplicates_of_europepmc") or []:
                    if d not in dup_seen:   # un mismo PMID declarado en dos rondas cuenta UNA vez
                        dup_seen.add(d)
                        duplicates.append({"duplicate": d, "source": "pubmed", "of": d, "matched_key": d})
        n_admitted = 0
        for it in rd["items"]:
            if it.get("kind") == "literature-candidate":
                if _pool_add(pool, seen, it, duplicates):
                    n_admitted += 1
                # entró o fue rechazado por llave PMID/PMCID/DOI: en ambos casos ya está PRESENTE en la corrida
                present.add(it.get("evidence_id"))
            else:
                other_items.append(it)
                present.add(it.get("evidence_id"))
                n_admitted += 1
        rd["n_admitted"] = n_admitted
        # ¿qué familias tendrían insumos NUEVOS en la ronda k+1? (las que aún no corrieron por presupuesto también)
        prev_inputs.update(search_harness.inputs_used_by_round(rd))
        pending = [s["family"] for s in rd["sources"] if s.get("status") == "skipped-budget"]
        new_inputs = search_harness.families_with_new_inputs(plan, ctx, prev_inputs)
        rd["families_with_new_inputs"] = sorted(set(new_inputs) | set(pending))
        inputs_changed = bool(rd["families_with_new_inputs"])
        rd["inputs_changed"] = inputs_changed
        rounds.append(rd)
        _stage("search.round", search_harness.round_event_payload(rd))
        if not search_harness.should_run_next_round(k, n_admitted, cap, inputs_changed):
            if n_admitted > 0:
                stop_reason = "found-new"
            elif k >= cap:
                stop_reason = "rounds-cap"
            else:
                stop_reason = "no-new-inputs"
            break

    # n <= 0: cero red de literatura (ADR-0078 corrector); las filas 'not-requested' las dejó el adaptador
    selected, not_selected = _select_top_n(pool, n, families)
    ledger["selection"] = {"rule": PATH_B_SELECTION_RULE, "n_requested": n, "retmax": retmax,
                           "n_candidates": len(pool), "n_selected": len(selected),
                           "n_duplicates": len(duplicates), "duplicates": duplicates,
                           "not_selected": not_selected,
                           "dedup_keys": "PMID · PMCID · DOI (lower, sin prefijo https://doi.org/)"}
    papers = []
    for c in selected:
        item = _paper_item(c, full_text, terms, excerpt_chars)
        for key in ("kind", "source_family", "label", "identifier_provenance", "url", "round"):
            if key in c:
                item[key] = c[key]
        papers.append(item)
    papers += other_items
    ledger["search_ledger"] = {
        "harness_version": search_harness.HARNESS_VERSION,
        "plan": {k2: v for k2, v in plan.items() if k2 != "query_builder"},
        "rounds": [{k2: v for k2, v in rd.items() if k2 != "items"} for rd in rounds],
        "families_default": list(plan.get("families_default") or []),
        "n_rounds": len(rounds), "cap": cap, "round_budget_s": round_budget,
        "stop_reason": stop_reason, "stop_reasons_vocabulary": list(SEARCH_STOP_REASONS),
        "n_new_total": sum(int(rd.get("n_new_total") or 0) for rd in rounds),
        "n_admitted_total": sum(int(rd.get("n_admitted") or 0) for rd in rounds),
        "n_items": len(papers)}
    return papers


def path_b_bundle(question, entities=None, n=None, query=None, query_source=None, triggered_by=None,
                  sources=PATH_B_SOURCES, retmax=None, search_plan=None, on_stage=None, existing_ids=None):
    """The `path_b` block of the bundle, built in ONE place. Both trigger sites (structural, inside
    retrieve(); confidence-gated, inside runs.execute_run) call this — a re-assembled block is how the
    per-source counters drift apart, and drifting counters are how a broken search looks like an empty
    world (LOTE-03·1).

    ADR-0078 (ledger_version '2'): conserva TODAS las llaves previas (triggered, triggered_by, papers,
    query_sent, query_source, n_results_by_source, sources_requested, tool_universe_directive,
    pubmed_searched, zfin_searched) y suma: query_sent_scope 'europepmc' (query_sent ES la de EPMC),
    epmc_query / pubmed_query / zfin_filter (lo que se mandó a cada índice), query_builder (el dict
    completo del constructor, con inputs), n_papers_requested / retmax_requested, europepmc_searched,
    selection.

    ADR-0080: con `search_plan` las fuentes son las FAMILIAS del plan (sources_requested = plan.families),
    la búsqueda corre por el harness (ver _path_b_harness) y el bloque gana `search_ledger` +
    `search_plan_version`; `on_stage` recibe los eventos search.*; `existing_ids` = evidence_ids ya
    presentes en la corrida (dedup declarado)."""
    if n is None:
        n, n_src = _env_int_src("WITT_PATH_B_N_PAPERS", PATH_B_N_PAPERS_DEFAULT)
    else:
        n, n_src = int(n), "caller"
    if retmax is None:
        retmax, retmax_src = _env_int_src("WITT_PATH_B_RETMAX", PATH_B_RETMAX_DEFAULT)
    else:
        retmax, retmax_src = int(retmax), "caller"
    # ADR-0080: también con plan hay UN constructor de queries (el de hoy, con la formulación EN y su
    # procedencia declarada por el llamador); el plan aporta familias, rondas y presupuesto. El harness
    # recibe este mismo qb (_plan_with_queries) para que adaptadores, bloque y evento coincidan byte a byte.
    qb = build_source_queries(question, entities, query=query, query_source=query_source)
    if search_plan is not None:
        sources = tuple(search_plan.get("families") or [])
    ledger = {}
    papers = path_b(question, n=n, query=query, entities=entities, sources=sources, ledger_out=ledger,
                    query_source=query_source, queries=qb, retmax=retmax, search_plan=search_plan,
                    on_stage=on_stage, existing_ids=existing_ids)
    # ADR-0080 corrector: con plan, las familias que MIDIERON (success | no-match en alguna ronda) reciben su 0
    # explícito en n_results_by_source; las que no corrieron quedan ausentes ('0 explícito' != 'no se pidió')
    ran_sources = None
    if search_plan is not None:
        ran_sources = []
        for rd in ((ledger.get("search_ledger") or {}).get("rounds") or []):
            for s in rd.get("sources") or []:
                if s.get("status") in ("success", "no-match") and s.get("family") not in ran_sources:
                    ran_sources.append(s.get("family"))
    block = {"triggered": True,
             "triggered_by": list(triggered_by or []),
             "ledger_version": PATH_B_LEDGER_VERSION,
             "papers": papers,
             # ADR-0057: what was ACTUALLY searched, auditable — a Path B that searched badly must
             # never look identical to a Path B that found nothing. ADR-0078: una query POR índice.
             "query_sent": qb["europepmc"]["query"], "query_sent_scope": "europepmc",
             "query_source": qb["query_source"],
             "epmc_query": qb["europepmc"]["query"],
             "pubmed_query": qb["pubmed"]["query"],
             "zfin_filter": qb["zfin"]["query"],
             "query_builder": qb,
             "n_papers_requested": n, "n_papers_source": n_src,
             "retmax_requested": retmax, "retmax_source": retmax_src,
             "n_results_by_source": n_results_by_source(papers, sources, ran_sources=ran_sources),
             "sources_requested": list(sources),
             "tool_universe_directive": tool_universe_directive(question, n)}
    if search_plan is not None:
        block["search_plan_version"] = search_plan.get("plan_version")
    block.update(ledger)   # europepmc_searched / pubmed_searched / zfin_searched / selection (+ search_ledger, ADR-0080)
    return block


def path_b_event_payload(block, trigger=None):
    """The event payload for `stage.path_b` — the live trace and the replay read the SAME summary."""
    p = {"triggered": True, "n_papers": len(block.get("papers", [])),
         "query_sent": block.get("query_sent"), "query_source": block.get("query_source"),
         "n_results_by_source": block.get("n_results_by_source", {})}
    if trigger:
        p["trigger"] = trigger
    # ADR-0078: la query por fuente y de dónde salió la formulación EN (synthesizer | caller | None)
    for k in ("ledger_version", "query_sent_scope", "epmc_query", "pubmed_query", "zfin_filter"):
        if k in block:
            p[k] = block.get(k)
    if "query_builder" in block:
        p["question_en_source"] = ((block["query_builder"] or {}).get("inputs") or {}).get("question_en_source")
    # ADR-0078 corrector: resumen POR PAPER para el lector humano (la Traza) — sin texto, solo procedencia.
    # El bloque path_b íntegro no viaja en el registro congelado; este resumen es lo que el front puede leer.
    if "papers" in block:
        resumen = []
        for it in block.get("papers") or []:
            f = it.get("fetched") or {}
            r = {"evidence_id": it.get("evidence_id"), "source": it.get("source"),
                 "selection_rank": it.get("selection_rank"),
                 "text_provenance": it.get("text_provenance"),
                 "fetched": {k: f.get(k) for k in ("found", "full_text")}}
            for k in ("cache_hit", "cached_at", "fetched_at", "fetch_error"):
                if k in f:
                    r["fetched"][k] = f[k]
            if it.get("zfin"):
                z = it["zfin"]
                r["zfin"] = {k: z.get(k) for k in ("status", "has_references", "n_matched", "n_returned")}
            resumen.append(r)
        p["papers"] = resumen
    if "zfin_searched" in block:
        led = block["zfin_searched"]
        p["zfin_searched"] = led
        p["zfin_status_tally"] = {s: sum(1 for r in led if r.get("status") == s)
                                  for s in sorted({r.get("status") for r in led})}
    if "pubmed_searched" in block:
        pm = block["pubmed_searched"]
        p["pubmed_searched"] = {k: pm.get(k) for k in ("status", "n_found_total", "n_new",
                                                       "duplicates_of_europepmc")}
        for k in ("n_returned", "ncbi_identity", "retries_429", "http_status"):
            if k in pm:
                p["pubmed_searched"][k] = pm[k]
    if "europepmc_searched" in block:
        ep = block["europepmc_searched"]
        p["europepmc_searched"] = {k: ep.get(k) for k in ("status", "n_found", "n_returned", "n_candidates")}
        for k in ("error", "detail"):
            if k in ep:
                p["europepmc_searched"][k] = ep[k]
    if "selection" in block:
        sel = block["selection"]
        p["selection"] = {k: sel.get(k) for k in ("rule", "n_requested", "n_candidates", "n_selected",
                                                  "n_duplicates", "not_selected")}
    if "search_ledger" in block:
        # ADR-0080: resumen del harness para la Traza — sin ítems ni ledgers anidados (viven en el bundle)
        sl = block["search_ledger"]
        p["search_ledger"] = {k: sl.get(k) for k in ("harness_version", "n_rounds", "cap", "round_budget_s",
                                                     "stop_reason", "n_new_total", "n_items", "families_default")}
        p["search_ledger"]["families"] = list((sl.get("plan") or {}).get("families") or [])
        p["search_ledger"]["rounds"] = [search_harness.round_event_payload(rd) for rd in sl.get("rounds") or []]
    return p


def _state(name, may_answer, may_propose, required_next):
    """A node in the explicit decision-state machine (see module docstring)."""
    return {"state": name, "may_answer_now": may_answer, "may_propose_now": may_propose,
            "required_next_action": required_next}


def retrieve(question, entities=None, n_papers=None, on_stage=None, search_plan=None):
    """The orchestrator: Path A, then Path B iff A is insufficient. Never a stopper. The returned bundle
    carries an explicit `decision_state` that GATES what may happen next — answering (on EITHER branch,
    ADR-0049) is blocked until an audit verdict is recorded (record_audit()).

    `n_papers` None (ADR-0078) -> WITT_PATH_B_N_PAPERS (default 5) leído en path_b_bundle.
    `on_stage(stage_name, payload)` (optional) is called after each stage — the event-emission hook the
    run model uses (ADR-0050) so the live trace and the replay read ONE state machine, not a re-built
    copy of it (the run_held_out.py re-assembly is exactly what left 31 historic runs without a
    decision_state). It may raise to abort (e.g. cancellation): the exception propagates.

    `search_plan` (ADR-0080, optional): dict de search_harness.build_search_plan. Si viene y la Ruta B se
    dispara (estructural), corre por el harness y emite stage.search.plan / .round / .source; los doc_ids de
    la Ruta A viajan como `existing_ids` (dedup declarado). Sin plan: comportamiento actual."""
    def _stage(name, payload):
        if on_stage:
            on_stage(name, payload)

    a = path_a(question)
    _stage("path_a", {"n_hits": a["n_hits"], "retrieval": a["retrieval"],
                      "text_cap_chars": a.get("text_cap_chars")})
    ent = check_entities(entities)
    _stage("check_entities", {e: v["in_di"] for e, v in ent.items()})
    suf = assess_sufficiency(a, ent)
    _stage("assess_sufficiency", suf)
    bundle = {"question": question,
              "run_id": uuid.uuid4().hex,
              "stamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
              "question_slug": re.sub(r"[^a-z0-9]+", "-", question.lower())[:40].strip("-"),
              "entities_checked": ent, "path_a": a, "sufficiency": suf}
    if suf["sufficient"]:
        bundle["path_b"] = {"triggered": False, "reason": "DI sufficient (literature present + entities resolved)"}
        # ADR-0049 (founder, 2026-08-09): DI-sufficiency no longer authorizes a direct answer — the
        # composite audit runs on 100% of runs. This state is now INTERMEDIATE.
        bundle["decision_state"] = _state(
            "DI_SUFFICIENT", may_answer=False, may_propose=False,
            required_next="AUDIT — composite-auditor Mode 1 (>=3 adversarial) MUST verdict the DI-grounded "
                          "answer BEFORE it may be shown (ADR-0049: audit on 100% of runs, DI-sufficient "
                          "included). Feed the verdict to record_audit(); lib/composite_auditor.py is the "
                          "invokable panel.")
    else:
        bundle["path_b"] = path_b_bundle(question, entities=entities, n=n_papers,
                                         triggered_by=suf["reasons"], search_plan=search_plan,
                                         on_stage=_stage if search_plan is not None else None,
                                         existing_ids=[h["doc_id"] for h in a["hits"]] if search_plan is not None else None)
        _stage("path_b", path_b_event_payload(bundle["path_b"], trigger="structural"))
        bundle["decision_state"] = _state(
            "FALLBACK_FETCHED", may_answer=False, may_propose=False,
            required_next="AUDIT — composite-auditor Mode 1 (>=3 adversarial) MUST verdict each Path-B paper "
                          "(DI absence re-check + external veracity) BEFORE any answer. Do NOT synthesize from "
                          "unaudited external evidence (CLAUDE.md §7). For full breadth ALSO run "
                          "path_b.tool_universe_directive via the connected tooluniverse MCP and audit those "
                          "hits the SAME way. Feed all verdicts to record_audit().")
    # Run-level epistemic aggregate (ADR-0043): one run may hold several retrievals; the band is ONE.
    # worst-of-n, declared — aggregating by "first" or "majority" paints a half-degraded run clean.
    modes = [a["retrieval"]["mode"]]
    bundle["retrieval_summary"] = {"mode": max(modes, key=_MODE_SEVERITY.__getitem__),
                                   "retrievals": len(modes), "aggregation": "worst-of-n"}
    bundle["bundle_identity"] = _identity(bundle)
    _stage("decision_state", bundle["decision_state"])
    return bundle


def record_audit(bundle, approved, rejected, note=""):
    """Transition the pathway AFTER the composite-auditor returns. `approved`/`rejected` = lists of paper
    ids. Structural enforcement: answering / proposing external evidence is only unlocked once a verdict is
    recorded here — the path is marked, not left to the agent's memory of the contract."""
    bundle["audit"] = {"approved": list(approved), "rejected": list(rejected), "note": note}
    if approved:
        bundle["decision_state"] = _state(
            "AUDIT_APPROVED", may_answer=True, may_propose=True,
            required_next=f"ANSWER from approved evidence {list(approved)} + PROPOSE to the DI via "
                          "propose_from_external.py (human gate). Rejected/absent items -> gap_flags.")
    else:
        bundle["decision_state"] = _state(
            "AUDIT_REJECTED", may_answer=True, may_propose=False,
            required_next="ANSWER with the gap EXPLICIT (no on-target evidence passed audit) + record a gap_flag; "
                          "optionally REFINE (e.g. follow an auditor-surfaced lead) and re-run retrieve().")
    bundle["bundle_identity"] = _identity(bundle)   # the audit mutated the bundle -> re-stamp (ADR-0044)
    return bundle


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--entities", default="", help="comma-separated gene symbols to check in DI")
    ap.add_argument("--papers", type=int, default=None,
                    help="literature papers to select (default WITT_PATH_B_N_PAPERS=5, ADR-0078)")
    a = ap.parse_args()
    ents = [e.strip() for e in a.entities.split(",") if e.strip()]
    bundle = retrieve(a.question, entities=ents, n_papers=a.papers)
    # ADR-0044: filename by run_id — a slug+date name silently overwrote bundles across users/days.
    (CACHE / f"answer_bundle_{bundle['run_id']}.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print(json.dumps(bundle, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

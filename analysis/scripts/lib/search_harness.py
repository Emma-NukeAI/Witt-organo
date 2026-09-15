"""
search_harness.py — el HARNESS de búsqueda de la Ruta B (ADR-0080, rebanada C2).

Por qué existe: hasta ADR-0078 la Ruta B era tres fuentes cableadas a mano dentro de answer_pipeline.path_b
(Europe PMC, PubMed, ZFIN), cada una con su ledger. ADR-0080 abre la búsqueda a una FAMILIA de fuentes Layer 0
(ortólogos, expresión, homología, proteína, asociaciones, rutas, interacciones, datasets, OA, OpenAlex) y a
rondas con presupuesto, sin que ninguna decisión del lazo la tome texto del modelo: el plan lo construye código
(build_search_plan), la ronda la ejecuta código (run_round) y la regla de "otra ronda" es un predicado declarado
(should_run_next_round). Lo que el consejo (ADR-0082) aportará son DIRECTIVAS — aquí ya existe el hueco
(`directives`, vacío hasta entonces) y la compuerta 'directive-only' por familia.

Doctrina heredada que este módulo aplica (constitución · CLAUDE.md §6/§7 · ADR-0043 · ADR-0078 · ADR-0079):
  * TRES estados, jamás un null ambiguo: cada fuente deja UNA fila con `status` ∈ SOURCE_STATES
    (success | no-match | error | skipped-budget | skipped-cap | tool-unavailable | not-requested). Los
    contadores n_found / n_new son ENTEROS solo cuando la fuente corrió (success | no-match); en cualquier otro
    estado son null (no medido).
  * §6 no-hang: una fuente que lanza, que no existe como módulo o que se queda sin presupuesto deja su fila y la
    RONDA sigue. Nada reintenta en lazo, nada re-ejecuta solo: otra ronda exige que los INSUMOS de alguna
    familia hayan cambiado (should_run_next_round(..., inputs_changed) — corrector ADR-0080); una ronda con los
    mismos insumos byte a byte no se repite (stop_reason 'no-new-inputs').
  * Presupuesto de RONDA (WITT_SEARCH_ROUND_BUDGET_S, 120 s): el tiempo restante se reparte entre las familias
    que faltan (min(budget_s de la familia, restante / familias_restantes)); la familia a la que no le alcanza
    queda 'skipped-budget' SIN tocar la red. El presupuesto por familia viaja al tool como `timeout` cuando su
    firma lo acepta (timeout_s_scope declarado).
  * Tools Layer 0 stdlib-puras cargadas POR PATH desde .tooluniverse/tools (igual que
    answer_pipeline._workspace_tool): un módulo ausente o sin la función declarada es 'tool-unavailable'
    DECLARADO (el detalle dice qué faltó) — así el harness corre aunque una rebanada paralela no haya entregado.
  * Ítems normalizados con evidence_id: el que trae el tool (identifier_provenance del tool) o uno DERIVADO
    ('<family>:sha256:<16 hex>' sobre el statement, identifier_provenance 'derived:sha256-of-statement' +
    gap_flag) — jamás un id inventado de memoria. Dedup contra lo ya presente (existing_ids) y dentro de la
    ronda, declarado en `duplicates`.
  * Etiquetas de clase de evidencia: 'inferred-by-orthology' (reactome) y 'predictive' (string) viajan en
    `label` — un ítem de esas familias nunca se lee como evidencia nativa de pez cebra.
  * Caché de lectura por día: la hace cada tool bajo mcp_cache (WITT_MCP_CACHE_DIR o <repo>/mcp_cache); el
    harness solo PROPAGA `cache_hit` y declara la ruta en el plan (`cache_dir`).

Las tres fuentes que ya existían (europepmc, pubmed, zfin) NO se reescriben: sus adaptadores llaman a las
funciones actuales de answer_pipeline (_search_europepmc / _search_pubmed / _search_zfin) y conservan el ledger
de hoy en la fila (`ledger`), para que path_b siga publicando europepmc_searched / pubmed_searched /
zfin_searched byte-compatibles. answer_pipeline importa este módulo; este módulo importa answer_pipeline
PEREZOSAMENTE (dentro de los adaptadores) para no invertir la dependencia en tiempo de carga.

Env vars (defaults declarados aquí, leídos EN TIEMPO DE LLAMADA; el valor efectivo y su fuente viajan en el plan):
  WITT_SEARCH_ROUNDS_CAP         default 2     — rondas máximas por corrida
  WITT_SEARCH_ROUND_BUDGET_S     default 120   — presupuesto de reloj por RONDA (segundos)
  WITT_SEARCH_DEFAULT_FAMILIES   default 'europepmc,pubmed,zfin,alliance_orthologs,zfin_expression' —
                                 familias que corren en una ronda SIN directivas del consejo; las demás
                                 (gate 'directive-only') solo por directiva explícita o por esta env
  WITT_MCP_CACHE_DIR             (lo leen los tools) — declarado en plan.cache_dir

Contrato de un ítem normalizado (run_round().items[]):
  {evidence_id, kind, source_family, title, statement, text, abstract, url, identifier_provenance, label,
   raw_ref, source (= source_family, compat path_b), search_rec (compat), fetched (compat), gap_flags?}
  'literature-candidate' (europepmc/pubmed) conserva además la forma de candidato de path_b (search_rec,
  abstract) para entrar al pool/dedup/selección de ADR-0078; 'phenotype' (zfin) es el ítem de hoy íntegro.

Interfaz que este harness espera de una tool Layer 0 (rebanadas C3–C5; declarada aquí para que casen):
  query_<algo>(<input>, ..., timeout=) -> {status ∈ success|no-match|error|skipped-budget, query_sent,
  elapsed_s, cache_hit?, label?, evidence_kind?, data|error}; la lista de resultados bajo data.items
  (preferido: [{evidence_id|id, statement|title, text|abstract|null, url, label?}]) o bajo una de
  _RESULT_LIST_KEYS. Cualquier otra forma cae al extractor genérico (identificador derivado, declarado).
"""
import hashlib
import importlib.util
import inspect
import json
import os
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parents[2].parent
_TU_WORKSPACE = ROOT / ".tooluniverse" / "tools"
CACHE = ROOT / "mcp_cache"

HARNESS_VERSION = "sh-1"
PLAN_VERSION = "1"

ROUNDS_CAP_DEFAULT = 2                      # WITT_SEARCH_ROUNDS_CAP
ROUND_BUDGET_S_DEFAULT = 120.0              # WITT_SEARCH_ROUND_BUDGET_S
DEFAULT_FAMILIES = ("europepmc", "pubmed", "zfin", "alliance_orthologs", "zfin_expression")  # WITT_SEARCH_DEFAULT_FAMILIES
MIN_SOURCE_BUDGET_S = 0.5                   # con menos que esto la familia queda skipped-budget sin red
MIN_CALL_TIMEOUT_S = 0.5                    # timeout mínimo por llamada dentro de una familia

SOURCE_STATES = ("success", "no-match", "error", "skipped-budget", "skipped-cap", "tool-unavailable",
                 "not-requested")
RAN_STATES = ("success", "no-match")        # solo estos MIDIERON: sus contadores son enteros
LABELS = ("predictive", "inferred-by-orthology", None)
GATES = ("auto", "directive-only")
INPUT_MODES = ("literature-query", "symbols", "zfin-curies", "free-query", "dois", "none")
STATEMENT_CAP_CHARS = 600                   # tope del statement genérico derivado de un elemento sin texto

# Indirección para que un smoke pueda fijar el reloj sin parchear `time` para todo el proceso.
_monotonic = time.monotonic

# ---------------------------------------------------------------------------------------------------------
# SEARCH_DISPATCH — UNA tabla, declarada. `tool_module` es el archivo bajo .tooluniverse/tools (None = no hay
# tool: la familia queda 'tool-unavailable' con `unavailable_reason`), `fn` la función query_* esperada,
# `inputs` cómo se alimenta (INPUT_MODES), `budget_s` el tope por familia dentro de la ronda, `host` el
# dominio al que pega, `key_env` la env de credencial (opcional), `evidence_kind` la clase del ítem, `gate`
# 'auto' (corre en una ronda por default) | 'directive-only' (solo por directiva o WITT_SEARCH_DEFAULT_FAMILIES),
# `label_provenance` la etiqueta de clase de evidencia que todo ítem de la familia lleva.
# ---------------------------------------------------------------------------------------------------------
SEARCH_DISPATCH = {
    "europepmc": {"tool_module": None, "fn": "answer_pipeline._search_europepmc", "adapter": "europepmc",
                  "inputs": "literature-query", "budget_s": 30.0, "host": "www.ebi.ac.uk", "key_env": None,
                  "evidence_kind": "paper", "gate": "auto", "label_provenance": None},
    "pubmed": {"tool_module": "pubmed_literature.py", "fn": "query_pubmed", "adapter": "pubmed",
               "inputs": "literature-query", "budget_s": 30.0, "host": "eutils.ncbi.nlm.nih.gov",
               "key_env": "NCBI_API_KEY", "evidence_kind": "paper", "gate": "auto", "label_provenance": None},
    "zfin": {"tool_module": "zfin_zebrafish.py", "fn": "query_zfin", "adapter": "zfin",
             "inputs": "symbols", "budget_s": 45.0, "host": "www.alliancegenome.org", "key_env": None,
             "evidence_kind": "phenotype", "gate": "auto", "label_provenance": None},
    "alliance_orthologs": {"tool_module": "alliance_orthologs.py", "fn": "query_orthologs", "adapter": None,
                           "inputs": "symbols", "budget_s": 30.0, "host": "www.alliancegenome.org",
                           "key_env": None, "evidence_kind": "ortholog", "gate": "auto", "label_provenance": None,
                           "list_keys": ("orthologs",)},
    "zfin_expression": {"tool_module": "zfin_expression_tsv.py", "fn": "query_expression", "adapter": None,
                        "inputs": "symbols", "budget_s": 60.0, "host": "zfin.org", "key_env": None,
                        "evidence_kind": "expression", "gate": "auto", "label_provenance": None,
                        "list_keys": ("rows",), "extra_kwargs": {"anatomy_terms": "stems"},
                        # corrector ADR-0080: su `budget_s` es el de la DESCARGA diaria (43.7 MB, 27 s medidos) y lo
                        # gobierna WITT_ZFIN_EXPR_DOWNLOAD_BUDGET_S; el presupuesto de familia viaja sólo como
                        # `timeout` (socket) — pisarlo con budget_s dejaba la fuente en 'error' todo el día
                        "pass_budget": False},
    "ensembl_homology": {"tool_module": "ensembl_homology.py", "fn": "query_homology", "adapter": None,
                         "inputs": "symbols", "budget_s": 30.0, "host": "rest.ensembl.org", "key_env": None,
                         "evidence_kind": "homology", "gate": "directive-only", "label_provenance": None,
                         "list_keys": ("homologies",)},
    "uniprot": {"tool_module": "uniprot_search.py", "fn": "query_uniprot", "adapter": None,
                "inputs": "symbols", "budget_s": 30.0, "host": "rest.uniprot.org", "key_env": None,
                "evidence_kind": "protein-record", "gate": "directive-only", "label_provenance": None},
    "monarch": {"tool_module": "monarch_associations.py", "fn": "query_monarch", "adapter": None,
                "inputs": "zfin-curies", "budget_s": 30.0, "host": "api.monarchinitiative.org", "key_env": None,
                "evidence_kind": "gene-phenotype-association", "gate": "directive-only", "label_provenance": None,
                "list_keys": ("associations",)},
    "reactome": {"tool_module": "reactome_search.py", "fn": "query_reactome", "adapter": None,
                 "inputs": "symbols", "budget_s": 30.0, "host": "reactome.org", "key_env": None,
                 "evidence_kind": "pathway", "gate": "directive-only", "label_provenance": "inferred-by-orthology",
                 "list_keys": ("pathways",)},
    "string": {"tool_module": "string_partners.py", "fn": "query_string", "adapter": None,
               "inputs": "symbols", "budget_s": 30.0, "host": "version-12-0.string-db.org", "key_env": None,
               "evidence_kind": "interaction", "gate": "directive-only", "label_provenance": "predictive",
               "list_keys": ("partners",)},
    "geo": {"tool_module": "geo_gds.py", "fn": "query_gds", "adapter": None,
            "inputs": "free-query", "budget_s": 30.0, "host": "eutils.ncbi.nlm.nih.gov", "key_env": "NCBI_API_KEY",
            "evidence_kind": "dataset", "gate": "directive-only", "label_provenance": None,
            "list_keys": ("records",)},   # ADR-0080 C7 (costura C2<->C5): geo_gds.query_gds -> data.records
    "unpaywall_crossref": {"tool_module": "unpaywall_crossref.py", "fn": "query_doi", "adapter": None,
                           "inputs": "dois", "budget_s": 30.0, "host": "api.crossref.org|api.unpaywall.org",
                           "key_env": "WITT_UNPAYWALL_EMAIL", "evidence_kind": "oa-location",
                           "gate": "directive-only", "label_provenance": None,
                           # ADR-0080 C7 (costura C2<->C5): query_doi devuelve data.{crossref, unpaywall} = UNA fila
                           # por fuente ({status, evidence_kind, identifier_provenance, data}), no una lista
                           "source_rows": ("crossref", "unpaywall")},
    "openalex": {"tool_module": "openalex_search.py", "fn": "query_openalex", "adapter": None,
                 "inputs": "free-query", "budget_s": 30.0, "host": "api.openalex.org", "key_env": "OPENALEX_API_KEY",
                 "evidence_kind": "paper", "gate": "directive-only", "label_provenance": None,
                 "list_keys": ("records",)},   # ADR-0080 C7 (costura C2<->C5): openalex_search.query_openalex -> data.records
    "web": {"tool_module": None, "fn": None, "adapter": None, "inputs": "free-query", "budget_s": 0.0,
            "host": None, "key_env": None, "evidence_kind": "web", "gate": "directive-only",
            "label_provenance": None, "unavailable_reason": "tool-unavailable (ADR-0084)"},
    "tooluniverse": {"tool_module": None, "fn": None, "adapter": None, "inputs": "free-query", "budget_s": 0.0,
                     "host": None, "key_env": None, "evidence_kind": "paper", "gate": "directive-only",
                     "label_provenance": None, "unavailable_reason": "tool-unavailable (ADR-0085)"},
}
LITERATURE_FAMILIES = ("europepmc", "pubmed")

# Llaves bajo las que un tool puede dejar su lista de resultados (orden de preferencia; `items` primero — es
# la forma preferida declarada en el docstring del módulo). Una familia puede fijar `list_keys` propias.
_RESULT_LIST_KEYS = ("items", "orthologs", "rows", "homologies", "records", "results", "associations",
                     "pathways", "partners", "datasets", "works", "entries", "phenotypes", "locations")
_ID_KEYS = ("evidence_id", "id", "curie", "accession", "primary_accession", "primaryAccession", "stable_id",
            "stId", "doi", "pmid", "stringId", "gds", "uid", "work_id")
_STATEMENT_KEYS = ("statement", "title", "display_name", "protein_name", "name", "description")
_URL_KEYS = ("url", "link")


# --- env con procedencia (mismos literales que answer_pipeline._env_int_src) ------------------------------
def _env_int_src(name, default):
    """(valor, fuente) — entero positivo desde la env; vacío / no numérico / <= 0 -> default declarado."""
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


def _env_float_src(name, default):
    """(valor, fuente) — flotante positivo desde la env; vacío / no numérico / <= 0 -> default declarado."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return float(default), f"default-unset:{name}"
    try:
        v = float(raw)
    except ValueError:
        return float(default), f"default-invalid-env:{name}"
    if v <= 0:
        return float(default), f"default-invalid-env:{name}"
    return v, f"env:{name}"


def _env_families_src():
    """(familias, fuente) — WITT_SEARCH_DEFAULT_FAMILIES como lista saneada (orden de la env, sin duplicados);
    vacía -> DEFAULT_FAMILIES declarado. Las familias desconocidas se CONSERVAN aquí y se declaran en el plan
    como 'unknown-family' (jamás se descartan calladas)."""
    raw = os.environ.get("WITT_SEARCH_DEFAULT_FAMILIES", "")
    fams = []
    for tok in raw.split(","):
        t = tok.strip().lower()
        if t and t not in fams:
            fams.append(t)
    if not fams:
        return list(DEFAULT_FAMILIES), "default-unset:WITT_SEARCH_DEFAULT_FAMILIES"
    return fams, "env:WITT_SEARCH_DEFAULT_FAMILIES"


def resolve_default_families():
    """Lector PÚBLICO de WITT_SEARCH_DEFAULT_FAMILIES (corrector ADR-0080): runs._search_config delega aquí para
    que `search_ledger.families_default` y `plan.families_default` salgan del MISMO saneo (minúsculas, sin
    duplicados) — una env, una verdad. Devuelve (familias, fuente)."""
    return _env_families_src()


# --- carga de tools por path (mismo patrón que answer_pipeline._workspace_tool) ---------------------------
_TOOL_CACHE = {}   # family -> (callable|None, fn_resolved|None, detail|None); un smoke puede inyectar fakes


def _load_tool(family, spec=None):
    """(callable|None, fn_resolved, detail) — la función query_* de la tool de `family`, cargada por path.
    None cuando el módulo no existe, no importa o no expone la función: el detalle dice cuál de las tres.
    Si la función declarada en SEARCH_DISPATCH no está pero el módulo expone EXACTAMENTE una `query_*`, se
    usa esa y se declara en fn_resolved (una rebanada paralela pudo nombrarla distinto; el ledger lo dice)."""
    if family in _TOOL_CACHE:
        return _TOOL_CACHE[family]
    spec = spec or SEARCH_DISPATCH.get(family) or {}
    module_file, fn_name = spec.get("tool_module"), spec.get("fn")
    result = (None, None, None)
    if not module_file:
        result = (None, None, spec.get("unavailable_reason") or f"no tool module declared for family {family!r}")
    else:
        path = _TU_WORKSPACE / module_file
        if not path.exists():
            result = (None, None, f"{path} not found")
        else:
            try:
                mspec = importlib.util.spec_from_file_location(f"_witt_sh_{path.stem}", path)
                mod = importlib.util.module_from_spec(mspec)
                mspec.loader.exec_module(mod)
            except Exception as e:
                result = (None, None, f"{path.name} not importable: {type(e).__name__}: {str(e)[:160]}")
            else:
                fn = getattr(mod, fn_name, None) if fn_name else None
                if callable(fn):
                    result = (fn, fn_name, None)
                else:
                    cands = [n for n in dir(mod) if n.startswith("query_") and callable(getattr(mod, n))]
                    if len(cands) == 1:
                        result = (getattr(mod, cands[0]), cands[0], f"declared fn {fn_name!r} absent; resolved {cands[0]!r}")
                    else:
                        result = (None, None, f"{path.name} has no {fn_name!r} (query_* found: {cands})")
    _TOOL_CACHE[family] = result
    return result


# --- plan ----------------------------------------------------------------------------------------------
def _free_query(symbols, qb, pass1_query_en):
    """(query, source) — texto libre EN para las familias 'free-query' (openalex, geo): la formulación EN de
    pass1 si llegó; si no, símbolos + términos anatómicos detectados + 'zebrafish' (determinista, declarado).
    None = nada que buscar (ni EN ni símbolos)."""
    q = (pass1_query_en or "").strip()
    if q:
        return q, "pass1_query_en"
    e = (qb or {}).get("europepmc") or {}
    terms = list(symbols) + [t for t in (e.get("anatomy_terms_used") or []) if t not in symbols]
    if not terms:
        return None, "empty"
    return " ".join(terms + ["zebrafish"]), "search_harness:v1:symbols+anatomy"


def build_search_plan(question, entities, pass1_query_en, directives=None, families=None):
    """El plan de búsqueda — construido por CÓDIGO, nunca por el modelo (ADR-0080 C).

    families (explícitas del llamador) > directives (consejo, ADR-0082: cada directiva {family, ...}) >
    WITT_SEARCH_DEFAULT_FAMILIES. Con 'default-families' las familias gate 'directive-only' NO corren aunque
    estén en la env... salvo que la env las nombre explícitamente (eso ES la directiva del operador); las que
    entran por DEFAULT_FAMILIES son todas gate 'auto'. Familias desconocidas se declaran ('unknown-family'), no
    corren. Las queries por familia salen de search_queries.build_all (literatura + zfin) y de _free_query.

    Devuelve {plan_version, harness_version, rounds_cap(+_source), round_budget_s(+_source), families,
    families_source, families_default, families_excluded[], directives[], directives_state, queries{family},
    query_builder, question, question_en, question_en_source, symbols, symbols_dropped, cache_dir}."""
    from lib import search_queries   # stdlib puro; import local para mantener este módulo liviano al cargar
    ents = [str(e).strip() for e in (entities or []) if e is not None and str(e).strip()]
    symbols, dropped, sanitized = search_queries.sanitize_symbols(ents)
    q_en = (pass1_query_en or "").strip() or None
    qb = search_queries.build_all(symbols, question_en=q_en, question=question)
    # misma forma que answer_pipeline.build_source_queries (query_source + inputs con procedencia), para que un
    # plan standalone declare de dónde salió la formulación EN; path_b_bundle sustituye este qb por el suyo
    mode = ((qb.get("europepmc") or {}).get("notes") or {}).get("mode")
    qb["query_source"] = f"query-builder-v{qb.get('builder_version')}:{mode}"
    qb["inputs"] = {"question": question, "question_en": q_en,
                    "question_en_source": "pass1_query_en" if q_en else None, "entities": ents}
    cap, cap_src = _env_int_src("WITT_SEARCH_ROUNDS_CAP", ROUNDS_CAP_DEFAULT)
    budget, budget_src = _env_float_src("WITT_SEARCH_ROUND_BUDGET_S", ROUND_BUDGET_S_DEFAULT)
    default_fams, default_src = _env_families_src()
    directives = list(directives or [])

    if families is not None:
        requested, source = [str(f).strip().lower() for f in families if str(f).strip()], "caller"
    elif directives:
        requested, source = [], "directives"
        for d in directives:
            fam = str((d or {}).get("family") or "").strip().lower() if isinstance(d, dict) else str(d).strip().lower()
            if fam and fam not in requested:
                requested.append(fam)
    else:
        requested, source = list(default_fams), "default-families"

    chosen, excluded = [], []
    for fam in requested:
        spec = SEARCH_DISPATCH.get(fam)
        if spec is None:
            excluded.append({"family": fam, "reason": "unknown-family"})
            continue
        if (source == "default-families" and spec["gate"] == "directive-only"
                and default_src.startswith("default-unset")):
            excluded.append({"family": fam, "reason": "directive-only (no directive, not in WITT_SEARCH_DEFAULT_FAMILIES)"})
            continue
        if fam not in chosen:
            chosen.append(fam)

    free_q, free_src = _free_query(symbols, qb, q_en)
    queries = {}
    for fam in chosen:
        mode = SEARCH_DISPATCH[fam]["inputs"]
        if fam == "europepmc":
            queries[fam] = {"inputs": mode, "query": qb["europepmc"]["query"], "query_builder": f"search_queries:v{qb['builder_version']}"}
        elif fam == "pubmed":
            queries[fam] = {"inputs": mode, "query": qb["pubmed"]["query"], "query_builder": f"search_queries:v{qb['builder_version']}"}
        elif fam == "zfin":
            queries[fam] = {"inputs": mode, "symbols": list(symbols), "anatomy_filter": qb["zfin"]["query"],
                            "query_builder": f"search_queries.build_zfin_filter:v{qb['builder_version']}"}
        elif mode == "symbols":
            queries[fam] = {"inputs": mode, "symbols": list(symbols), "query_builder": "search_harness:v1:symbols"}
        elif mode == "zfin-curies":
            queries[fam] = {"inputs": mode, "curies": "from-zfin-items-at-round-time", "symbols": list(symbols),
                            "query_builder": "search_harness:v1:zfin-curies"}
        elif mode == "free-query":
            queries[fam] = {"inputs": mode, "query": free_q, "query_source": free_src}
        elif mode == "dois":
            queries[fam] = {"inputs": mode, "dois": "from-items-at-round-time", "query_builder": "search_harness:v1:dois"}
        else:
            queries[fam] = {"inputs": mode}

    return {"plan_version": PLAN_VERSION, "harness_version": HARNESS_VERSION,
            "rounds_cap": cap, "rounds_cap_source": cap_src,
            "round_budget_s": budget, "round_budget_s_source": budget_src,
            "families": chosen, "families_source": source,
            "families_default": list(default_fams), "families_default_source": default_src,
            "families_excluded": excluded,
            "directives": directives, "directives_state": "empty-until-ADR-0082" if not directives else "provided",
            "queries": queries, "query_builder": qb,
            "question": question, "question_en": q_en,
            "question_en_source": "pass1_query_en" if q_en else None,
            "symbols": list(symbols), "symbols_dropped": list(dropped), "symbols_sanitized": sanitized,
            "cache_dir": str(os.environ.get("WITT_MCP_CACHE_DIR", "").strip() or CACHE)}


def plan_event_payload(plan):
    """Payload del evento stage.search.plan — el plan sin el dict completo del constructor de queries."""
    out = {k: plan.get(k) for k in ("plan_version", "harness_version", "rounds_cap", "rounds_cap_source",
                                    "round_budget_s", "round_budget_s_source", "families", "families_source",
                                    "families_default", "families_excluded", "directives_state",
                                    "queries", "question_en_source", "symbols", "symbols_dropped")}
    out["n_directives"] = len(plan.get("directives") or [])
    # corrector ADR-0080: la forma del evento es UNA — `state` viaja SIEMPRE ('built' cuando el harness corre en
    # vivo; runs emite 'harness-unavailable' | 'error: …' | 'kill-switch …' cuando no); la Traza no infiere
    # nada de la AUSENCIA de una llave
    out["state"] = "built"
    return out


def should_run_next_round(k, n_new_total, rounds_cap, inputs_changed=True):
    """La regla DECLARADA de 'otra ronda' (ADR-0080 C, corrector): solo si la ronda k no trajo NADA nuevo,
    k < cap Y los insumos de alguna familia CAMBIARON desde la ronda k (`inputs_changed`, medido con
    inputs_signature antes/después). Sin insumos nuevos la ronda k+1 sería la misma búsqueda byte a byte — red
    y reloj gastados para producir duplicados o no-match — y "nada se re-ejecuta solo". Con directivas
    (ADR-0082) cambiará; hoy es este predicado y no otro. `inputs_changed` default True conserva la firma vieja."""
    return int(n_new_total or 0) == 0 and int(k) < int(rounds_cap) and bool(inputs_changed)


def inputs_signature(plan, ctx):
    """{familia: [modo, insumos]} de la ronda que correría con este plan y este ctx — la FIRMA de la PRÓXIMA
    ronda (corrector ADR-0080). Determinista; no toca red."""
    sig = {}
    for fam in plan.get("families") or []:
        spec = SEARCH_DISPATCH.get(fam) or {}
        inputs, mode = _inputs_for(fam, spec, plan, ctx or {})
        sig[fam] = [mode, list(inputs)]
    return sig


NOT_REEXECUTED_DETAIL = "same inputs as round {k} (not re-executed)"


def inputs_used_by_round(rd):
    """{familia: insumos que la familia CONSUMIÓ en la ronda} desde sus filas (`inputs_used`); las familias que no
    corrieron por presupuesto/tope (skipped-*) no aparecen — su trabajo sigue pendiente."""
    used = {}
    for row in rd.get("sources") or []:
        if row.get("status") in ("skipped-budget", "skipped-cap"):
            continue
        if isinstance(row.get("inputs_used"), list):
            used[row["family"]] = list(row["inputs_used"])
    return used


def families_with_new_inputs(plan, ctx, previous_inputs):
    """Las familias cuya PRÓXIMA ronda tendría insumos distintos de los que ya consumieron (o que aún no han
    corrido: ausentes de `previous_inputs`). Es el predicado 'inputs_changed' desmenuzado por familia — lo que
    should_run_next_round recibe como bool y lo que run_round usa para NO re-ejecutar (corrector ADR-0080)."""
    sig = inputs_signature(plan, ctx)
    out = []
    for fam, (_mode, inputs) in sig.items():
        if fam not in (previous_inputs or {}) or list(inputs) != list(previous_inputs[fam]):
            out.append(fam)
    return out


# --- normalización de ítems ------------------------------------------------------------------------------
def _first(d, keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return v
    return None


def _templated_statement(family, element, input_value):
    """Statement legible para las formas que ADR-0080 (D) fija: ortólogos {species, symbol, id, stringency} y
    expresión {gene, anatomy, stage, assay, pub_id}. None si faltan los campos (cae al genérico)."""
    if family == "alliance_orthologs" and element.get("symbol") and element.get("species"):
        return (f"{input_value or element.get('subject_symbol') or 'gene'} ortholog: {element['species']} "
                f"{element['symbol']} ({element.get('id')}; stringency {element.get('stringency')})")
    if family == "zfin_expression" and element.get("gene") and element.get("anatomy"):
        return (f"{element['gene']} expressed in {element['anatomy']}"
                + (f" at {element['stage']}" if element.get("stage") else "")
                + (f" ({element['assay']})" if element.get("assay") else "")
                + (f" [{element['pub_id']}]" if element.get("pub_id") else ""))
    return None


def _derived_id(family, statement):
    return f"{family}:sha256:{hashlib.sha256((statement or '').encode('utf-8')).hexdigest()[:16]}"


def normalize_item(family, element, spec=None, tool_result=None, input_value=None):
    """Un elemento crudo del tool -> ítem normalizado (contrato del docstring del módulo). Nunca inventa un
    identificador: usa el del elemento (evidence_id | id | curie | accession | doi | ...) con la procedencia que
    el tool declare (o 'tool-payload'); si no hay ninguno, deriva '<family>:sha256:<16>' del statement y lo
    declara (identifier_provenance 'derived:sha256-of-statement' + gap_flag)."""
    spec = spec or SEARCH_DISPATCH.get(family) or {}
    tool_result = tool_result or {}
    if not isinstance(element, dict):
        element = {"statement": str(element)}
    statement = _first(element, _STATEMENT_KEYS)
    if statement is None:
        statement = _templated_statement(family, element, input_value)
    if statement is None:
        compact = {k: v for k, v in element.items() if isinstance(v, (str, int, float, bool)) and k not in _URL_KEYS}
        statement = json.dumps(compact, ensure_ascii=False, sort_keys=True)[:STATEMENT_CAP_CHARS]
        if input_value:
            statement = f"{family} {input_value}: {statement}"
    statement = str(statement)
    text = _first(element, ("text", "summary"))
    raw_id = _first(element, _ID_KEYS)
    gap_flags = []
    if raw_id is not None:
        evidence_id = str(raw_id)
        provenance = element.get("identifier_provenance") or tool_result.get("identifier_provenance") \
            or ((tool_result.get("data") or {}).get("identifier_provenance") if isinstance(tool_result.get("data"), dict) else None) \
            or "tool-payload"
    else:
        evidence_id = _derived_id(family, statement)
        provenance = "derived:sha256-of-statement"
        gap_flags.append("no-external-identifier")
    label = element.get("label", tool_result.get("label", spec.get("label_provenance")))
    if label not in LABELS:
        label = spec.get("label_provenance")
    kind = element.get("kind") or tool_result.get("evidence_kind") or spec.get("evidence_kind")
    url = _first(element, _URL_KEYS)
    title = element.get("title")
    # corrector ADR-0080: la curie ZFIN que el tool resolvió a nivel resultado (alliance_orthologs deja
    # data.zfin_curie) viaja al ítem para que run_round la ofrezca a las familias 'zfin-curies' (monarch)
    data_blk = tool_result.get("data") if isinstance(tool_result.get("data"), dict) else {}
    zfin_curie = element.get("zfin_curie") or data_blk.get("zfin_curie")
    item = {"evidence_id": evidence_id, "kind": kind, "source_family": family,
            "title": str(title) if title is not None else None, "statement": statement,
            "text": str(text) if text is not None else None,
            "abstract": element.get("abstract"),
            "url": str(url) if url is not None else None,
            "identifier_provenance": provenance, "label": label,
            # el raw_ref del ELEMENTO manda cuando existe (p. ej. {file_date, line_no} de la fila TSV de ZFIN);
            # si no, la referencia del resultado del tool (caché del día)
            "raw_ref": element.get("raw_ref") or tool_result.get("cache_ref") or tool_result.get("cache_path"),
            "input": input_value,
            "zfin_curie": str(zfin_curie) if zfin_curie else None,
            # compat con path_b / _compact_evidence / path_b_event_payload (leen source, search_rec, fetched)
            "source": family,
            "search_rec": {"pmid": element.get("pmid"), "pmcid": None, "doi": element.get("doi"),
                           "title": (title or statement)[:300], "year": element.get("year"),
                           "journal": spec.get("host"), "is_oa": None, "cited_by": None},
            "fetched": {"found": True, "full_text": False, "n_chunks": None, "raw_cached": [], "raw_ref": None},
            "text_provenance": "none" if (text is None and element.get("abstract") is None) else "abstract",
            "text_excerpt": (str(text) if text is not None else element.get("abstract")),
            "text_excerpt_rule": "full" if (text is not None or element.get("abstract") is not None) else "none",
            "text_excerpt_omitted": False}
    if gap_flags:
        item["gap_flags"] = gap_flags
    return item


def _result_list(tool_result, spec):
    """La lista de elementos de un resultado de tool: data.items (preferido), luego las list_keys de la familia,
    luego _RESULT_LIST_KEYS. Devuelve (lista, llave|None)."""
    data = tool_result.get("data")
    if not isinstance(data, dict):
        return [], None
    rows_keys = spec.get("source_rows")
    if rows_keys:
        # ADR-0080 C7 (costura C2<->C5): unpaywall_crossref.query_doi no deja una LISTA sino UNA fila por
        # fuente (data.crossref / data.unpaywall: {status, evidence_kind, identifier_provenance, data}). Cada
        # fila 'success' se vuelve UN elemento con evidence_id '<fuente>:<doi>' (dos fuentes, dos ids — no se
        # funden); una fila no-success no produce elemento (su estado ya vive en la fila del tool / calls[]).
        elements = []
        for name in rows_keys:
            row = data.get(name)
            if not isinstance(row, dict) or row.get("status") != "success" or not isinstance(row.get("data"), dict):
                continue
            d = dict(row["data"])
            doi = d.get("doi") or data.get("doi")
            el = {"kind": row.get("evidence_kind"), "identifier_provenance": row.get("identifier_provenance"),
                  "source_row": name, "statement": d.get("title"), "title": d.get("title"), "doi": doi,
                  "url": d.get("url") or d.get("best_oa_url") or (f"https://doi.org/{doi}" if doi else None),
                  "abstract": d.get("abstract"), "year": d.get("year")}
            if doi:
                el["evidence_id"] = f"{name}:{doi}"
            el.update({k: v for k, v in d.items() if k not in el})
            elements.append(el)
        return elements, "source-rows"
    for k in ("items",) + tuple(spec.get("list_keys") or ()) + _RESULT_LIST_KEYS:
        v = data.get(k)
        if isinstance(v, list):
            return v, k
    return [], None


# --- una fuente ------------------------------------------------------------------------------------------
def _row(family, spec, status, **extra):
    """Fila de ledger de UNA fuente. n_found / n_new son enteros solo si la fuente corrió (RAN_STATES)."""
    base = {"family": family, "status": status, "n_found": None, "n_new": None, "elapsed_s": None,
            "cache_hit": None, "query_sent": None, "evidence_kind": spec.get("evidence_kind"),
            "gate": spec.get("gate"), "label": spec.get("label_provenance"), "host": spec.get("host")}
    base.update(extra)
    if status not in RAN_STATES:
        base["n_found"] = None if "n_found" not in extra else extra["n_found"]
        base["n_new"] = None if "n_new" not in extra else extra["n_new"]
    return base


def _accepts(fn, name):
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    return name in params or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())


def _call_tool(fn, first_arg, timeout_s, extra_kwargs, pass_budget=True):
    """Llama al tool con el primer insumo posicional y `timeout=` solo si la firma lo acepta (declarado por el
    llamador en timeout_s_scope). `budget_s=` viaja también salvo que la familia declare `pass_budget False`
    (su budget_s tiene otro significado — p. ej. la descarga diaria de zfin_expression). Cualquier excepción
    vuelve como resultado 'error' (§6)."""
    kwargs = {}
    if _accepts(fn, "timeout"):
        kwargs["timeout"] = timeout_s
    if pass_budget and _accepts(fn, "budget_s"):
        kwargs["budget_s"] = timeout_s
    for k, v in (extra_kwargs or {}).items():
        if _accepts(fn, k):
            kwargs[k] = v
    try:
        res = fn(first_arg, **kwargs)
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {str(e)[:200]}"}
    if not isinstance(res, dict):
        return {"status": "error", "error": f"tool returned {type(res).__name__}, expected dict"}
    return res


def _inputs_for(family, spec, plan, ctx):
    """Los insumos de la familia en esta ronda: símbolos, una query o los DOIs presentes en ctx['dois']."""
    q = (plan.get("queries") or {}).get(family) or {}
    mode = spec.get("inputs")
    if mode == "symbols":
        return list(q.get("symbols") or plan.get("symbols") or []), mode
    if mode in ("free-query", "literature-query"):
        return ([q.get("query")] if q.get("query") else []), mode
    if mode == "dois":
        return list(dict.fromkeys(ctx.get("dois") or [])), mode
    if mode == "zfin-curies":
        return list(dict.fromkeys(ctx.get("curies") or [])), mode
    return [], mode


def _run_workspace_family(family, spec, plan, ctx, budget_s, fn, fn_resolved, fn_detail):
    """Una familia Layer 0 genérica: una llamada por insumo (símbolo | query | DOI) dentro del presupuesto de la
    familia; la fila agrega los estados de las llamadas (`calls[]`) y los ítems se normalizan.

    Reparto dentro de la familia: la PRIMERA llamada siempre corre (la admisión la decidió el reparto de la
    ronda) con timeout = max(MIN_CALL_TIMEOUT_S, restante / llamadas_restantes); las siguientes solo si queda
    al menos MIN_CALL_TIMEOUT_S — si no, 'skipped-budget' por llamada, declarado en calls[] y contado en
    n_calls_skipped_budget."""
    inputs, mode = _inputs_for(family, spec, plan, ctx)
    if not inputs:
        reason = {"symbols": "no symbols", "free-query": "no English query (nothing to search)",
                  "literature-query": "query builder produced no query", "dois": "no DOI inputs in the round",
                  "zfin-curies": "no ZFIN curie resolved earlier in the round (zfin/alliance_orthologs items; "
                                 "the tool takes a curie, never a symbol from memory)"}.get(mode, "no inputs")
        return _row(family, spec, "not-requested", detail=reason, inputs_mode=mode, inputs_used=[]), []
    extra = {}
    for k, src in (spec.get("extra_kwargs") or {}).items():
        if src == "stems":
            extra[k] = list(((plan.get("query_builder") or {}).get("zfin") or {}).get("notes", {}).get("stems") or [])
    t0 = _monotonic()
    calls, items, statuses = [], [], []
    cache_hits, any_cache_declared = 0, False
    n_calls_skipped = 0
    for idx, inp in enumerate(inputs):
        remaining = budget_s - (_monotonic() - t0)
        left = len(inputs) - idx
        if idx > 0 and remaining < MIN_CALL_TIMEOUT_S:
            n_calls_skipped += 1
            calls.append({"input": inp, "status": "skipped-budget", "detail": f"family budget {round(budget_s, 3)}s exhausted"})
            continue
        timeout_s = round(max(MIN_CALL_TIMEOUT_S, remaining / left), 3)
        c0 = _monotonic()
        res = _call_tool(fn, inp, timeout_s, extra, pass_budget=spec.get("pass_budget", True))
        elapsed = round(_monotonic() - c0, 3)
        st = res.get("status")
        call = {"input": inp, "status": st, "elapsed_s": elapsed, "timeout_s": timeout_s,
                "timeout_s_scope": "per-call" if _accepts(fn, "timeout") else "not-accepted-by-tool",
                "query_sent": res.get("query_sent")}
        if "cache_hit" in res:
            any_cache_declared = True
            call["cache_hit"] = bool(res.get("cache_hit"))
            cache_hits += int(bool(res.get("cache_hit")))
        if st == "success" and _result_list(res, spec)[1] is None:
            # corrector ADR-0080: la fuente dijo 'success' pero el harness NO supo leer su lista — eso es un
            # desajuste de forma, no un "buscó y no encontró": se declara 'error' (status_raw conserva la palabra
            # del tool), jamás n_found 0
            data_keys = sorted((res.get("data") or {}).keys()) if isinstance(res.get("data"), dict) else type(res.get("data")).__name__
            call["status_raw"], call["status"] = st, "error"
            call["error"] = f"shape-mismatch: success without result list (data keys: {data_keys})"
            st = "error"
        elif st in RAN_STATES:
            elements, list_key = _result_list(res, spec)
            call["n_found"], call["list_key"] = len(elements), list_key
            for el in elements:
                items.append(normalize_item(family, el, spec, res, input_value=inp))
        else:
            call["error"] = str(res.get("error", ""))[:200]
            if st not in SOURCE_STATES:
                call["status_raw"], call["status"] = st, "error"
        statuses.append(call["status"])
        calls.append(call)
    elapsed_total = round(_monotonic() - t0, 3)
    # Agregación DECLARADA de las llamadas a UN estado de familia: >=1 ítem -> success; ninguna llamada
    # corrió y todas quedaron sin presupuesto -> skipped-budget; alguna llamada MIDIÓ 0 -> no-match (los
    # errores de las demás se declaran en partial_errors, no se esconden); si no, error.
    if items:
        status = "success"
    elif not statuses:
        status = "skipped-budget"
    elif any(s in RAN_STATES for s in statuses):
        status = "no-match"
    elif all(s == "tool-unavailable" for s in statuses):
        # ADR-0080 C7 (costura C2<->C3/C5): las tools declaran 'tool-unavailable' (p. ej. unpaywall sin
        # WITT_UNPAYWALL_EMAIL) y 'skipped-budget' (timeout<=0) en su raíz; si TODAS las llamadas lo dijeron,
        # la familia hereda ese literal del vocabulario del ledger — no se degrada a 'error'
        status = "tool-unavailable"
    elif all(s == "skipped-budget" for s in statuses):
        status = "skipped-budget"
    elif all(s == "not-requested" for s in statuses):
        # corrector ADR-0080: un "no se pidió" declarado por el tool en TODAS sus llamadas se hereda, no se
        # degrada a fallo
        status = "not-requested"
    else:
        status = "error"
    n_err = sum(1 for s in statuses if s == "error")
    row = _row(family, spec, status, n_found=len(items) if status in RAN_STATES else None,
               elapsed_s=elapsed_total, budget_s=round(budget_s, 3), inputs_mode=mode, inputs_used=list(inputs),
               n_calls=len(calls), n_calls_error=n_err, n_calls_skipped_budget=n_calls_skipped,
               cache_hit=(cache_hits > 0) if any_cache_declared else None,
               query_sent=next((c.get("query_sent") for c in calls if c.get("query_sent")), None),
               fn_resolved=fn_resolved, calls=calls)
    if fn_detail:
        row["fn_note"] = fn_detail
    if n_err and status in RAN_STATES:
        row["partial_errors"] = n_err
    if status == "error":
        # 'error' jamás viaja con error null: si ninguna llamada dejó mensaje, la mezcla de estados ES el error
        row["error"] = (next((c.get("error") for c in calls if c.get("error")), None)
                        or "mixed call statuses: " + json.dumps(sorted(set(statuses))))
    elif status in ("tool-unavailable", "not-requested"):
        row["detail"] = next((c.get("error") or c.get("detail") for c in calls if c.get("error") or c.get("detail")), None)   # la razón que dio el tool
    return row, items


def _legacy_status(led):
    """(status de la fila, detail|None) desde el ledger legado de answer_pipeline (ADR-0078). Corrector ADR-0080
    (paridad webapp 2026-09-15): el ledger dice 'not-searched' cuando el constructor NO produjo query (nada que
    buscar, declarado) — ese literal es SUYO y no cambia; en el vocabulario del harness eso es 'not-requested' con el
    detail del ledger, jamás 'error' (no hubo fallo: no había nada que buscar). Un literal fuera de SOURCE_STATES
    sigue siendo 'error' (desajuste de vocabulario, declarado)."""
    status = led.get("status")
    if status == "not-searched":
        return "not-requested", led.get("detail")
    return (status if status in SOURCE_STATES else "error"), None


def _run_legacy_family(family, spec, plan, ctx, budget_s):
    """Adaptadores de las tres fuentes que ya existían — llaman a answer_pipeline (import perezoso) y conservan
    el ledger de hoy en `ledger` para que path_b publique europepmc_searched / pubmed_searched / zfin_searched.

    Corrector ADR-0080 (paridad webapp 2026-09-15): `inputs_used` de cada fila es EXACTAMENTE la firma que
    _inputs_for produce para la familia en este ctx (query None -> [], símbolos [] -> []). Antes la fila llevaba
    [None] cuando no había query y families_with_new_inputs leía [None] != [] como "insumo nuevo": ronda 2 idéntica
    (skipped-cap 'same inputs') y stop 'rounds-cap' en vez de 'no-new-inputs' — medido en los fixtures
    objetada-confianza-ausente / citas-no-parseables de la webapp."""
    from lib import answer_pipeline as ap
    qb = plan.get("query_builder") or {}
    retmax = int(ctx.get("retmax") or ap.PATH_B_RETMAX_DEFAULT)
    inputs, inputs_mode = _inputs_for(family, spec, plan, ctx)
    t0 = _monotonic()
    if family in LITERATURE_FAMILIES and not ctx.get("literature_requested", True):
        led = {"source": family, "status": "not-requested", "detail": f"n_papers={ctx.get('n_papers')} <= 0",
               "query_sent": (qb.get(family) or {}).get("query"), "retmax_sent": retmax,
               "n_found": None, "n_returned": None, "n_candidates": None}
        if family == "pubmed":
            led.update(n_found_total=None, n_new=None, duplicates_of_europepmc=None)
        return _row(family, spec, "not-requested", detail=led["detail"], query_sent=led["query_sent"], ledger=led,
                    inputs_mode=inputs_mode, inputs_used=list(inputs)), []
    if family == "europepmc":
        # corrector ADR-0080: el presupuesto de la familia ACOTA la llamada (timeout por GET = min(default del
        # módulo, presupuesto)); antes la fuente usaba HTTP_TIMEOUT_S fijo y podía rebasar la ronda entera
        fam_timeout = round(max(MIN_CALL_TIMEOUT_S, min(float(getattr(ap.fetch_paper, "HTTP_TIMEOUT_S", 30) or 30), budget_s)), 3)
        if _accepts(ap._search_europepmc, "timeout"):
            recs, led = ap._search_europepmc((qb.get("europepmc") or {}).get("query"), retmax, timeout=fam_timeout)
            scope = f"per-call (timeout {fam_timeout}s = min(fetch_paper.HTTP_TIMEOUT_S, family budget))"
        else:
            recs, led = ap._search_europepmc((qb.get("europepmc") or {}).get("query"), retmax)
            scope = "module-default (fetch_paper.HTTP_TIMEOUT_S)"
        items = []
        for rec in recs:
            cand = ap._epmc_candidate(rec)
            cand.update({"kind": "literature-candidate", "source_family": "europepmc", "label": None,
                         "statement": None, "title": (cand.get("search_rec") or {}).get("title"),
                         "url": f"https://europepmc.org/abstract/MED/{rec['pmid']}" if rec.get("pmid") else None,
                         "identifier_provenance": "europepmc-api-live", "raw_ref": None, "text": None})
            items.append(cand)
        status, detail = _legacy_status(led)
        row = _row("europepmc", spec, status, n_found=led.get("n_returned") if status in RAN_STATES else None,
                   elapsed_s=led.get("elapsed_s", round(_monotonic() - t0, 3)), query_sent=led.get("query_sent"),
                   cache_hit=None, timeout_s_scope=scope, inputs_mode=inputs_mode, inputs_used=list(inputs),
                   budget_s=round(budget_s, 3), ledger=led)
        if status == "error":
            row["error"] = led.get("error") or led.get("detail")
        elif detail:
            row["detail"] = detail
        return row, items
    if family == "pubmed":
        existing = ctx.get("pubmed_seen") or {}
        # corrector ADR-0080: mismo acotamiento que EPMC — timeout por GET = min(30 s del tool, presupuesto de la
        # familia); el reintento 429 (Retry-After ≤ 60 s) sigue siendo del tool y se declara en su ledger
        fam_timeout = round(max(MIN_CALL_TIMEOUT_S, min(30.0, budget_s)), 3)
        if _accepts(ap._search_pubmed, "timeout"):
            cands, led = ap._search_pubmed((qb.get("pubmed") or {}).get("query"), retmax, existing, timeout=fam_timeout)
            scope = f"per-call (timeout {fam_timeout}s = min(30, family budget); 429 retry-after is the tool's, declared)"
        else:
            cands, led = ap._search_pubmed((qb.get("pubmed") or {}).get("query"), retmax, existing)
            scope = "module-default (pubmed_literature)"
        items = []
        for cand in cands:
            cand.update({"kind": "literature-candidate", "source_family": "pubmed", "label": None,
                         "statement": None, "title": (cand.get("search_rec") or {}).get("title"),
                         "url": f"https://pubmed.ncbi.nlm.nih.gov/{cand['search_rec']['pmid']}/" if cand["search_rec"].get("pmid") else None,
                         "identifier_provenance": "ncbi-eutils-live", "raw_ref": None, "text": None})
            items.append(cand)
        status, detail = _legacy_status(led)
        row = _row("pubmed", spec, status, n_found=led.get("n_returned") if status in RAN_STATES else None,
                   elapsed_s=round(_monotonic() - t0, 3), query_sent=led.get("query_sent"), cache_hit=None,
                   timeout_s_scope=scope, inputs_mode=inputs_mode, inputs_used=list(inputs),
                   budget_s=round(budget_s, 3), ledger=led)
        if status == "error":
            row["error"] = led.get("detail") or led.get("error")
        elif detail:
            row["detail"] = detail
        return row, items
    if family == "zfin":
        symbols = list(inputs)   # la MISMA firma que _inputs_for (modo 'symbols'): queries.zfin.symbols | plan.symbols | []
        items, ledger = ap._search_zfin(symbols, plan.get("question"), budget_s=min(ap.ZFIN_BUDGET_S, budget_s),
                                        zfin_filter=qb.get("zfin"))
        for it in items:
            z = it.get("zfin") or {}
            it.update({"kind": "phenotype", "source_family": "zfin", "label": None,
                       "title": (it.get("search_rec") or {}).get("title"),
                       "statement": "; ".join(p.get("statement", "") for p in (z.get("phenotypes") or [])[:5]) or None,
                       "text": None, "abstract": None,
                       "url": f"https://zfin.org/{z['curie'].split(':', 1)[1]}" if z.get("curie") and ":" in z["curie"] else None,
                       "identifier_provenance": z.get("identifier_provenance", "alliance-genome-api-live"),
                       "raw_ref": ((it.get("fetched") or {}).get("raw_cached") or [None])[0]})
        tallies = {}
        for r in ledger:
            tallies[r.get("status")] = tallies.get(r.get("status"), 0) + 1
        if not symbols:
            status, detail = "not-requested", "no symbols"
        elif items:
            status, detail = "success", None
        elif ledger and all(r.get("status") == "tool-unavailable" for r in ledger):
            status, detail = "tool-unavailable", ledger[0].get("detail")
        elif ledger and all(r.get("status") == "skipped-budget" for r in ledger):
            status, detail = "skipped-budget", ledger[0].get("detail")
        elif ledger and any(r.get("status") == "no-match" for r in ledger):
            status, detail = "no-match", None
        else:
            status, detail = "error", next((r.get("detail") for r in ledger if r.get("status") == "error"), None)
        row = _row("zfin", spec, status, n_found=len(items) if status in RAN_STATES else None,
                   elapsed_s=round(_monotonic() - t0, 3), query_sent=(qb.get("zfin") or {}).get("query"),
                   cache_hit=None, budget_s=round(min(ap.ZFIN_BUDGET_S, budget_s), 3), inputs_mode=inputs_mode,
                   inputs_used=list(symbols),
                   timeout_s_scope="per-http-get (answer_pipeline._search_zfin)", ledger=ledger,
                   zfin_status_tally=tallies)
        if detail:
            row["detail"] = detail
        return row, items
    return _row(family, spec, "error", error=f"no adapter for legacy family {family!r}"), []


def run_source(family, plan, ctx, budget_s, tools=None):
    """(fila, ítems) de UNA familia dentro de su presupuesto. `tools` (dict family -> callable) inyecta fakes
    para las familias Layer 0 genéricas (los smokes); las tres legadas se parchean en answer_pipeline."""
    spec = SEARCH_DISPATCH.get(family)
    if spec is None:
        return _row(family, {}, "error", error=f"unknown family {family!r}"), []
    if spec.get("adapter"):
        try:
            return _run_legacy_family(family, spec, plan, ctx, budget_s)
        except Exception as e:   # cinturón §6: un adaptador que lanza degrada SU familia, no la ronda
            return _row(family, spec, "error", error=f"{type(e).__name__}: {str(e)[:200]}"), []
    if tools and family in tools:
        fn, fn_resolved, fn_detail = tools[family], "injected", None
    else:
        fn, fn_resolved, fn_detail = _load_tool(family, spec)
    if fn is None:
        return _row(family, spec, "tool-unavailable", detail=fn_detail or spec.get("unavailable_reason")), []
    return _run_workspace_family(family, spec, plan, ctx, budget_s, fn, fn_resolved, fn_detail)


# --- una ronda -------------------------------------------------------------------------------------------
def run_round(plan, k, budget_s, on_source=None, existing_ids=None, trigger=None, tools=None, ctx=None,
              previous_inputs=None):
    """Ejecuta la ronda k del plan dentro de `budget_s` segundos de reloj.

    Reparto: antes de cada familia, restante = budget_s - transcurrido; su presupuesto es
    min(SEARCH_DISPATCH[f].budget_s, restante / familias_restantes). Con restante < MIN_SOURCE_BUDGET_S la
    familia queda 'skipped-budget' sin tocar la red — el presupuesto acota la RONDA, no cada fuente aislada.
    Dedup: un ítem cuyo evidence_id ya está en `existing_ids` (lo ya presente en la corrida) o ya salió en esta
    ronda NO entra a `items`; queda en `duplicates` {evidence_id, source_family, of ∈ existing | this-round}.
    `on_source(row)` se llama al terminar cada familia (hook de eventos stage.search.source; puede lanzar para
    abortar, p. ej. cancelación: la excepción propaga). `ctx` (dict) lleva lo que las familias necesitan en
    tiempo de ronda: retmax, n_papers, literature_requested, pubmed_seen (dict evidence_id -> evidence_id de
    los candidatos de literatura ya admitidos, que PubMed declara como duplicates_of_europepmc), dois (los DOI
    de los ítems admitidos, insumo de la familia 'dois'), curies (las curies ZFIN que ZFIN/Alliance resolvieron
    en la ronda, insumo de 'zfin-curies' — monarch toma curie). El ORDEN de las familias en el plan importa:
    una familia que consume insumos de otra debe ir después (declarado; el consejo lo fijará en ADR-0082).

    Devuelve {round, trigger, budget_s, elapsed_s, n_families, n_new_total, n_found_total, sources[],
    items[], duplicates[], round_over_budget, elapsed_over_budget_s, n_not_reexecuted}. Corrector ADR-0080: los
    insumos que la ronda RESUELVE (dois, curies) se escriben también en el ctx del LLAMADOR (la copia superficial
    los perdía entre rondas cuando la llave no existía); `pubmed_seen` se alimenta SÓLO con candidatos de europepmc
    (lo que PubMed declara como duplicates_of_europepmc); y con `previous_inputs` ({familia: insumos consumidos en
    la ronda anterior}, de inputs_used_by_round) una familia cuyos insumos son IDÉNTICOS a los que ya consumió
    deja fila 'skipped-cap' con detail NOT_REEXECUTED_DETAIL sin tocar la red — nada se re-ejecuta."""
    caller_ctx = ctx if isinstance(ctx, dict) else None
    ctx = dict(ctx or {})
    previous_inputs = previous_inputs or {}
    n_not_reexecuted = 0

    def _ctx_list(key):
        lst = ctx.setdefault(key, [])
        if caller_ctx is not None and key not in caller_ctx:
            caller_ctx[key] = lst
        return lst

    seen = set(existing_ids or [])
    families = list(plan.get("families") or [])
    t0 = _monotonic()
    sources, items, duplicates = [], [], []
    for idx, fam in enumerate(families):
        remaining = budget_s - (_monotonic() - t0)
        left = len(families) - idx
        spec = SEARCH_DISPATCH.get(fam) or {}
        if remaining < MIN_SOURCE_BUDGET_S:
            row = _row(fam, spec, "skipped-budget",
                       detail=f"round budget {round(budget_s, 3)}s exhausted (remaining {max(0.0, round(remaining, 3))}s < {MIN_SOURCE_BUDGET_S}s)",
                       budget_s=0.0)
            row["round"] = k
            sources.append(row)
            if on_source:
                on_source(row)
            continue
        if fam in previous_inputs:
            nxt, mode = _inputs_for(fam, spec, plan, ctx)
            if list(nxt) == list(previous_inputs[fam]):
                row = _row(fam, spec, "skipped-cap", detail=NOT_REEXECUTED_DETAIL.format(k=k - 1),
                           inputs_mode=mode, inputs_used=None, budget_s=0.0)
                row["round"] = k
                n_not_reexecuted += 1
                sources.append(row)
                if on_source:
                    on_source(row)
                continue
        fam_budget = min(float(spec.get("budget_s") or remaining), remaining / left)
        row, found = run_source(fam, plan, ctx, fam_budget, tools=tools)
        row["round"] = k
        row["over_budget"] = bool(row.get("elapsed_s") is not None and row["elapsed_s"] > fam_budget + 0.05)
        new_here = 0
        for it in found:
            eid = it.get("evidence_id")
            # los INSUMOS que el ítem resolvió (DOI, curie ZFIN) se cosechan ANTES del dedup: una resolución es un
            # hecho de la fuente aunque el ítem ya estuviera presente en la corrida (corrector ADR-0080)
            doi = (it.get("search_rec") or {}).get("doi")
            if doi:
                dois = _ctx_list("dois")
                if doi not in dois:
                    dois.append(doi)
            curie = (it.get("zfin") or {}).get("curie") or it.get("zfin_curie")
            if curie and str(curie).startswith("ZFIN:"):
                curies = _ctx_list("curies")
                if curie not in curies:
                    curies.append(curie)
            if eid in seen:
                duplicates.append({"evidence_id": eid, "source_family": fam,
                                   "of": "existing" if eid in (existing_ids or ()) else "this-round"})
                continue
            seen.add(eid)
            it["round"] = k
            items.append(it)
            new_here += 1
            if (it.get("kind") == "literature-candidate" and it.get("source_family") == "europepmc"
                    and isinstance(ctx.get("pubmed_seen"), dict)):
                # el adaptador de PubMed declara duplicates_of_europepmc contra lo que EPMC ya trajo EN ESTA
                # ronda (ledger de hoy, ADR-0062/0078): se le hace visible aquí, no al cerrar la ronda
                ctx["pubmed_seen"].setdefault(eid, eid)
        if row.get("status") in RAN_STATES:
            row["n_new"] = new_here
        sources.append(row)
        if on_source:
            on_source(row)
    ran = [s for s in sources if s.get("status") in RAN_STATES]
    elapsed_total = round(_monotonic() - t0, 3)
    return {"round": k, "trigger": trigger, "budget_s": float(budget_s),
            "elapsed_s": elapsed_total, "n_families": len(families),
            "n_new_total": sum(int(s.get("n_new") or 0) for s in ran),
            "n_found_total": sum(int(s.get("n_found") or 0) for s in ran),
            # corrector ADR-0080: la ronda declara si REBASÓ su presupuesto (una familia legada con timeout de
            # módulo podía hacerlo) — la Traza lo lee, no lo suma
            "round_over_budget": bool(elapsed_total > float(budget_s) + 0.05),
            "elapsed_over_budget_s": round(max(0.0, elapsed_total - float(budget_s)), 3),
            "n_not_reexecuted": n_not_reexecuted,
            "sources": sources, "items": items, "duplicates": duplicates}


def round_event_payload(rd):
    """Payload del evento stage.search.round — la ronda sin ítems ni ledgers anidados."""
    return {"round": rd.get("round"), "trigger": rd.get("trigger"), "budget_s": rd.get("budget_s"),
            "elapsed_s": rd.get("elapsed_s"), "n_families": rd.get("n_families"),
            "n_new_total": rd.get("n_new_total"), "n_found_total": rd.get("n_found_total"),
            "n_admitted": rd.get("n_admitted"), "n_not_reexecuted": rd.get("n_not_reexecuted"),
            "families_with_new_inputs": rd.get("families_with_new_inputs"),
            "round_over_budget": rd.get("round_over_budget"), "elapsed_over_budget_s": rd.get("elapsed_over_budget_s"),
            "n_duplicates": len(rd.get("duplicates") or []),
            "sources": [source_event_payload(s) for s in rd.get("sources") or []]}


def source_event_payload(row):
    """Payload del evento stage.search.source — la fila sin `ledger` ni `calls` (viven en el bundle)."""
    out = {k: row.get(k) for k in ("round", "family", "status", "n_found", "n_new", "elapsed_s", "cache_hit",
                                   "query_sent", "budget_s", "gate", "label", "evidence_kind")}
    for k in ("error", "detail", "over_budget", "n_calls", "n_calls_error", "n_calls_skipped_budget", "fn_resolved"):
        if k in row and row[k] not in (None, False, 0):
            out[k] = row[k]
    return out

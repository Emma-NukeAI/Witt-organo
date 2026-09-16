"""
search_harness.py — el HARNESS de búsqueda de la Ruta B (ADR-0080, rebanada C2).

Por qué existe: hasta ADR-0078 la Ruta B era tres fuentes cableadas a mano dentro de answer_pipeline.path_b
(Europe PMC, PubMed, ZFIN), cada una con su ledger. ADR-0080 abre la búsqueda a una FAMILIA de fuentes Layer 0
(ortólogos, expresión, homología, proteína, asociaciones, rutas, interacciones, datasets, OA, OpenAlex) y a
rondas con presupuesto, sin que ninguna decisión del lazo la tome texto del modelo: el plan lo construye código
(build_search_plan), la ronda la ejecuta código (run_round) y la regla de "otra ronda" es un predicado declarado
(should_run_next_round). Las DIRECTIVAS del consejo (ADR-0082 (G.3), compiladas por CÓDIGO en council.compile_directives
— forma C.6 {requirement_id, family, query_en, entities[], symbols[], evidence_kind, priority, requested_by[],
refined_by_members[]}) entran a build_search_plan(directives=) con semántica de UNIÓN: las familias auto (o las de
WITT_SEARCH_DEFAULT_FAMILIES) SIGUEN y las familias de las directivas se AÑADEN (`families_source
'directives+default'`); las 'directive-only' entran SÓLO nombradas por directiva (o por la env); una familia que el
harness no puede satisfacer (web/tooluniverse) queda excluida 'unsatisfiable-by-harness (…)'. La directiva mueve los
INSUMOS de su familia: `query_en` sustituye la query libre (`query_source 'council-directive:<req ids>'`) o corre como
UNA llamada EXTRA en literatura (`directive_queries[]`); `symbols[]` se AÑADEN (`symbols_from_directives[]`). Filas e
ítems llevan `directive_requirement_ids[]` (atribución PRECISA: el insumo que la directiva añadió → sus ids; una
familia que entró sólo por directiva → todos; un insumo base → []). Sin directivas el plan es byte-idéntico al de
ADR-0080 (golden en smoke_search_harness) — el kill-switch WITT_COUNCIL=0 pasa directives=None.

ADR-0084 (C): la familia `web` deja de ser placeholder y es un LOCALIZADOR, jamás una fuente. Su fila de SEARCH_DISPATCH
apunta al tool real (.tooluniverse/tools/brave_web_search.py, `locate`) con `adapter 'web'` y `availability
'web_locator.provider_state'`: la disponibilidad es DINÁMICA (family_available / unsatisfiable_families, leídas EN LA
LLAMADA): sin BRAVE_API_KEY o con WITT_WEB_LOCATOR=off la familia queda excluida del plan con el literal EXACTO de
7d9ce15 (WEB_UNSATISFIABLE_LITERAL) y el plan es byte-idéntico al golden grabado en 7d9ce15; disponible, entra SÓLO por
directiva del consejo o nombrada en WITT_SEARCH_DEFAULT_FAMILIES y va PRIMERA en la ronda (`families_order_rule`) porque
es el único encadenado determinista hacia ctx:dois → unpaywall_crossref y ctx:curies → monarch en la MISMA ronda. Su
adaptador (_run_web_family) NO pasa por normalize_item: el localizador devuelve URLs, lib/web_locator las resuelve a
identificadores por una TABLA determinista y los de literatura se MATERIALIZAN en la ronda por Europe PMC
(fetch_paper._resolve_one, una GET sin escribir caché) → candidatos `source 'europepmc'` / `source_family 'web'` /
`identifier_provenance 'web-located:<rule>'`; CERO ítems con source 'web'; ningún título, snippet ni URL de la web llega
a los ítems ni a los eventos (viven SÓLO en la fila, `web_locator`, que runs congela en frozen.web_locator).

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
import re
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
    # ADR-0084 (C.1): fila REAL de la familia web — tool Brave por ruta + adaptador PROPIO (`adapter 'web'`: run_source
    # NO la normaliza, Context 2). `evidence_kind 'web'` es la CLASE DE DEMANDA del consejo (COUNCIL_EVIDENCE_KINDS se
    # deriva de aquí): ningún ítem emitido es kind 'web'. `availability` delega la disponibilidad a
    # web_locator.provider_state (llave / kill-switch, leído EN LA LLAMADA); `unavailable_reason` es el literal de
    # 7d9ce15 que viaja en families_excluded / harness_state / demand bajo `off`. `budget_env`: WITT_WEB_BUDGET_S manda
    # sobre budget_s (family_budget_s, clamp declarado).
    "web": {"tool_module": "brave_web_search.py", "fn": "locate", "adapter": "web", "inputs": "free-query",
            "budget_s": 30.0, "budget_env": "WITT_WEB_BUDGET_S", "budget_clamp": (1.0, 120.0),
            "host": "api.search.brave.com", "key_env": "BRAVE_API_KEY", "evidence_kind": "web",
            "gate": "directive-only", "label_provenance": None, "unavailable_reason": "tool-unavailable (ADR-0084)",
            "availability": "web_locator.provider_state"},
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


# --- ADR-0084 (C.2): disponibilidad DINÁMICA — UNA verdad, leída en la llamada (plan, compilación, despacho) --------
UNSATISFIABLE_PREFIX = "unsatisfiable-by-harness ("
# El literal de exclusión de la familia web bajo `off` — el MISMO de 7d9ce15 (ADR-0082 C.4). Aparece UNA vez en este
# módulo (los smokes lo importan; W0 lo grabó en golden_plan_web_directive_7d9ce15.json); el assert de abajo lo ata a la
# tabla para que jamás diverja de SEARCH_DISPATCH['web'].unavailable_reason.
WEB_UNSATISFIABLE_LITERAL = "unsatisfiable-by-harness (tool-unavailable (ADR-0084))"
assert WEB_UNSATISFIABLE_LITERAL == f"{UNSATISFIABLE_PREFIX}{SEARCH_DISPATCH['web']['unavailable_reason']})"


def family_available(family, env=None):
    """(bool, reason) — ¿puede el harness DESPACHAR esta familia ahora? Estática para las filas sin mecanismo (`fn`
    None y `adapter` None: tooluniverse → su unavailable_reason, ADR-0085); DINÁMICA para las filas con `availability`
    (web → web_locator.provider_state(env): sin llave o WITT_WEB_LOCATOR=off → (False, 'tool-unavailable (ADR-0084)'
    EXACTO — el literal de 7d9ce15; `brave`/`anthropic` fijados sin llave → (False, '<literal con causa>');
    disponible → (True, None)). build_search_plan excluye con esto; council.harness_state_for y
    council_index.unsatisfiable_families delegan aquí (ADR-0084 F). Desconocida → (False, 'unknown-family')."""
    spec = SEARCH_DISPATCH.get(family)
    if spec is None:
        return False, "unknown-family"
    if spec.get("availability") == "web_locator.provider_state":
        try:
            from lib import web_locator as wl   # import perezoso: este módulo sigue liviano al cargar
        except Exception as e:   # pragma: no cover — árbol sin la rebanada W2: declarado, no fingido
            return False, f"{spec.get('unavailable_reason') or 'tool-unavailable (ADR-0084)'}: web_locator not importable ({type(e).__name__})"
        ps = wl.provider_state(env)
        if ps.get("available"):
            return True, None
        return False, ps.get("unavailable_reason") or spec.get("unavailable_reason")
    if spec.get("fn") is None and spec.get("adapter") is None:
        return False, spec.get("unavailable_reason") or "no tool module declared"
    return True, None


def unsatisfiable_families(env=None):
    """Tupla ORDENADA de las familias que el harness NO puede satisfacer AHORA (family_available False) — bajo `off`
    ('tooluniverse', 'web'); con llave de Brave ('tooluniverse',). council_index.demand la deriva EN LA LLAMADA
    (ADR-0084 F.3: DEMAND_FAMILIES sigue estática para que la serie MEDIDA no se rompa al llegar la llave)."""
    return tuple(sorted(f for f in SEARCH_DISPATCH if not family_available(f, env)[0]))


def family_budget_s(spec):
    """(budget_s efectivo, fuente) de una familia dentro de la ronda: el de la tabla ('table') salvo que la fila declare
    `budget_env` (ADR-0084: WITT_WEB_BUDGET_S para web) — entonces la env manda con clamp declarado (`budget_clamp`);
    vacía / inválida → el de la tabla con fuente 'default-unset:…' | 'default-invalid-env:…'."""
    base = float(spec.get("budget_s") or 0.0)
    var = spec.get("budget_env")
    if not var:
        return base, "table"
    v, src = _env_float_src(var, base)
    lo, hi = spec.get("budget_clamp") or (MIN_SOURCE_BUDGET_S, 120.0)
    return float(min(max(v, lo), hi)), src


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


# ADR-0082 (G.3): vocabularios CERRADOS del plan con directivas (viajan congelados en search_ledger.plan).
FAMILIES_SOURCES = ("default-families", "directives+default", "caller")
DIRECTIVE_PLAN_STATES = ("applied", "excluded-unknown-family", "excluded-unsatisfiable",
                         "not-requested (caller families)", "ignored (no family)")
ENTERED_BY_ENV = "env:WITT_SEARCH_DEFAULT_FAMILIES"      # ADR-0084 (C.3): web nombrada por la env, sin directiva
ENTERED_BY = ("directive", "default+directive", "caller+directive", ENTERED_BY_ENV)
QUERY_SOURCE_DIRECTIVE_PREFIX = "council-directive:"
# ADR-0084 (C.3 / C.4): literales del plan cuando la familia web ENTRA (ausentes en un plan sin web: byte-identidad)
WEB_TEST_QUERY_SOURCE = "operator-env:WITT_WEB_TEST_QUERY"
FAMILIES_ORDER_RULE_WEB_FIRST = "web first — the locator feeds the round (ADR-0084)"
FAMILIES_ORDER_RULE_CALLER = "caller order (families= mandates; web not moved) (ADR-0084)"


def _directives_by_family(directives):
    """ADR-0082 (G.3): agrupa las directivas del consejo (forma C.6, compiladas por council.compile_directives) por
    familia en el orden en que llegaron. Devuelve (by_fam, rows): by_fam = {fam: {rids[], queries[{requirement_id,
    query_en}], symbols[(rid, symbol)]}}; rows = UNA fila por directiva {requirement_id, family, state, applied_as[]}
    para `directives_applied` (el state lo completa build_search_plan). Una directiva sin `requirement_id` (un
    llamador viejo que pasa {'family': …}) recibe el id posicional 'directive:<i>' — declarado, no inventado."""
    by_fam, rows = {}, []
    for i, d in enumerate(directives):
        if isinstance(d, dict):
            fam = str(d.get("family") or "").strip().lower()
            rid = d.get("requirement_id")
            query_en = str(d.get("query_en") or "").strip() or None
            symbols = [str(s).strip() for s in (d.get("symbols") or []) if s is not None and str(s).strip()]
        else:
            fam, rid, query_en, symbols = str(d or "").strip().lower(), None, None, []
        rid = str(rid) if rid not in (None, "") else f"directive:{i}"
        row = {"requirement_id": rid, "family": fam or None, "state": None, "applied_as": []}
        rows.append(row)
        if not fam:
            row["state"] = "ignored (no family)"
            continue
        slot = by_fam.setdefault(fam, {"rids": [], "queries": [], "symbols": []})
        if rid not in slot["rids"]:
            slot["rids"].append(rid)
        if query_en:
            slot["queries"].append({"requirement_id": rid, "query_en": query_en})
        for s in symbols:
            slot["symbols"].append((rid, s))
    return by_fam, rows


def _rids_for(q, input_value):
    """ADR-0082 (G.3): los requirement_id que un ÍTEM lleva — atribución PRECISA, nunca por contagio: el insumo
    (símbolo o query) que la directiva AÑADIÓ o sustituyó → sus ids (`queries[fam].directive_inputs`); una familia
    que entró SÓLO por directiva (`entered_by 'directive'`) → todos sus ids (corrió por ella); un insumo base de una
    familia default/caller → [] (no se afirma que el consejo lo pidió). Es lo que coverage_after_search (C5) lee
    como 'retrieved-for' — una MEDICIÓN estructural, distinta del juicio 'covered'."""
    q = q or {}
    d_inputs = q.get("directive_inputs") or {}
    if input_value is not None and str(input_value) in d_inputs:
        return list(d_inputs[str(input_value)])
    if q.get("entered_by") == "directive":
        return list(q.get("directive_requirement_ids") or [])
    return []


def build_search_plan(question, entities, pass1_query_en, directives=None, families=None):
    """El plan de búsqueda — construido por CÓDIGO, nunca por el modelo (ADR-0080 C; ADR-0082 G.3).

    families (explícitas del llamador, `families_source 'caller'`) > WITT_SEARCH_DEFAULT_FAMILIES ∪ familias de las
    directivas del consejo (`'directives+default'`: las auto SIGUEN — antes una directiva REEMPLAZABA a las auto y
    apagaba europepmc/pubmed/zfin, ADR-0082 Context 4) > WITT_SEARCH_DEFAULT_FAMILIES (`'default-families'`). Las
    familias gate 'directive-only' entran SÓLO nombradas por directiva o por la env (eso ES la directiva del
    operador); las que entran por DEFAULT_FAMILIES son todas gate 'auto'. Familias desconocidas se declaran
    ('unknown-family'), no corren; una familia que entró SÓLO por directiva y el harness no puede satisfacer (web /
    tooluniverse: sin tool ni adaptador) queda 'unsatisfiable-by-harness (<unavailable_reason>)'. Las queries por
    familia salen de search_queries.build_all (literatura + zfin) y de _free_query; con directivas: `query_en`
    sustituye la query libre (`query_source 'council-directive:<req ids>'`, la sustituida queda en `query_replaced`)
    y todas las de la familia viajan en `directive_queries[]` (una llamada por insumo en Layer 0; UNA llamada EXTRA
    por directiva en europepmc/pubmed); `symbols[]` se AÑADEN saneados (`symbols_from_directives[]`); cada
    `queries[fam]` tocada declara `directive_requirement_ids[]`, `entered_by` y `directive_inputs {insumo: [ids]}`.

    Devuelve {plan_version, harness_version, rounds_cap(+_source), round_budget_s(+_source), families,
    families_source, families_default, families_excluded[] {family, reason, requirement_ids?}, directives[]
    (verbatim), directives_state 'empty-until-ADR-0082' | 'provided', queries{family}, query_builder, question,
    question_en, question_en_source, symbols, symbols_dropped, symbols_sanitized, cache_dir} y, SÓLO con directivas
    (byte-identidad sin ellas, golden), + {directives_applied[] {requirement_id, family, state ∈ DIRECTIVE_PLAN_STATES,
    applied_as[], reason?}, families_from_directives[], n_directives_excluded}."""
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
    by_fam, d_rows = _directives_by_family(directives)

    if families is not None:
        requested, source = [str(f).strip().lower() for f in families if str(f).strip()], "caller"
    elif directives:
        # ADR-0082 (G.3): UNIÓN — las auto (o las de la env) primero y en su orden; después las familias de las
        # directivas en el orden en que el consejo las pidió (una familia que consume insumos de otra va después)
        requested, source = list(default_fams), "directives+default"
        for fam in by_fam:
            if fam not in requested:
                requested.append(fam)
    else:
        requested, source = list(default_fams), "default-families"

    chosen, excluded = [], []
    for fam in requested:
        spec = SEARCH_DISPATCH.get(fam)
        via_directive = fam in by_fam
        from_defaults = source != "caller" and fam in default_fams
        if spec is None:
            row = {"family": fam, "reason": "unknown-family"}
            if via_directive:
                row["requirement_ids"] = list(by_fam[fam]["rids"])
            excluded.append(row)
            continue
        if (source != "caller" and from_defaults and not via_directive and spec["gate"] == "directive-only"
                and default_src.startswith("default-unset")):
            excluded.append({"family": fam, "reason": "directive-only (no directive, not in WITT_SEARCH_DEFAULT_FAMILIES)"})
            continue
        if via_directive and not from_defaults and source != "caller":
            # ADR-0082 (G.3 / C.4): la familia entró SÓLO por la directiva y el harness no la puede satisfacer: se
            # declara y se cuenta (GET /council/demand la lee); NO se despacha una llamada que nacería
            # 'tool-unavailable'. Nombrada por la env sigue el camino de hoy. ADR-0084 (C.2): la disponibilidad es
            # DINÁMICA (family_available): tooluniverse sigue estática (ADR-0085); web depende de la llave y del
            # kill-switch WITT_WEB_LOCATOR — bajo `off` la razón es el literal EXACTO de 7d9ce15
            # (WEB_UNSATISFIABLE_LITERAL); con `brave` fijado sin llave viaja la causa (mismo prefijo).
            available, why = family_available(fam)
            if not available:
                excluded.append({"family": fam, "reason": f"{UNSATISFIABLE_PREFIX}{why})",
                                 "requirement_ids": list(by_fam[fam]["rids"])})
                continue
        if fam not in chosen:
            chosen.append(fam)

    families_order_rule = None
    web_available = family_available("web")[0] if "web" in chosen else False
    if "web" in chosen and web_available:
        # ADR-0084 (C.4): web PRIMERA en la RONDA cuando entra — el ÚNICO encadenado determinista hacia ctx:dois →
        # unpaywall_crossref y ctx:curies → monarch en la MISMA ronda (Context 5: should_run_next_round exige
        # n_new == 0, no hay "siguiente ronda" para alimentar). Sólo el ORDEN de ronda: la admisión al pool es
        # native-first y la selección desempata native-before-web-located (answer_pipeline, D). Con families= del
        # llamador el orden del llamador MANDA (declarado). Un plan sin web no gana la llave: byte-idéntico a 7d9ce15.
        # corrector ADR-0084 (L): SÓLO con el localizador DISPONIBLE — bajo kill-switch o sin llave, web nombrada por
        # WITT_SEARCH_DEFAULT_FAMILIES (o por families=) conserva su posición y el plan NO gana families_order_rule: es el
        # plan de 7d9ce15 byte a byte (la ronda deja la fila MÍNIMA 'tool-unavailable' de entonces — run_source).
        if source != "caller":
            chosen = ["web"] + [f for f in chosen if f != "web"]
            families_order_rule = FAMILIES_ORDER_RULE_WEB_FIRST
        else:
            families_order_rule = FAMILIES_ORDER_RULE_CALLER

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
            if fam == "web":
                # ADR-0084 (C.3): web entra por directiva (su query_en sustituye esta query en el bloque de abajo) o
                # nombrada en WITT_SEARCH_DEFAULT_FAMILIES — la directiva del operador (ADR-0080): entonces la consulta
                # es WITT_WEB_TEST_QUERY si está ('operator-env:WITT_WEB_TEST_QUERY') o la formulación EN de pass1
                # (_free_query) — JAMÁS la pregunta cruda. `entered_by 'env:WITT_SEARCH_DEFAULT_FAMILIES'` sólo cuando
                # entró por la env sin directiva (con directiva lo fija el bloque de abajo; por families= queda ausente).
                # corrector ADR-0084 (L): ambas llaves SÓLO con el localizador disponible — sin él, queries.web es la de 7d9ce15
                test_q = os.environ.get("WITT_WEB_TEST_QUERY", "").strip()
                if web_available and test_q and not (by_fam.get(fam) or {}).get("queries"):
                    queries[fam] = {"inputs": mode, "query": test_q, "query_source": WEB_TEST_QUERY_SOURCE}
                if web_available and fam not in by_fam and source != "caller" and fam in default_fams:
                    queries[fam]["entered_by"] = ENTERED_BY_ENV
        elif mode == "dois":
            queries[fam] = {"inputs": mode, "dois": "from-items-at-round-time", "query_builder": "search_harness:v1:dois"}
        else:
            queries[fam] = {"inputs": mode}

    # ADR-0082 (G.3): las directivas mueven los INSUMOS de su familia. Sólo se tocan las familias nombradas — sin
    # directivas este bloque no corre y el plan queda byte-idéntico al de ADR-0080.
    families_from_directives = []
    for fam in chosen:
        info = by_fam.get(fam)
        if info is None:
            continue
        q, mode = queries[fam], SEARCH_DISPATCH[fam]["inputs"]
        entered_by = ("directive" if (source != "caller" and fam not in default_fams)
                      else ("caller+directive" if source == "caller" else "default+directive"))
        if entered_by == "directive":
            families_from_directives.append(fam)
        q["directive_requirement_ids"] = list(info["rids"])
        q["entered_by"] = entered_by
        d_inputs = {}
        applied_by_rid = {rid: (["family-entry"] if entered_by == "directive" else []) for rid in info["rids"]}

        def _mark_input(insumo, rid):
            d_inputs.setdefault(insumo, [])
            if rid not in d_inputs[insumo]:
                d_inputs[insumo].append(rid)

        if mode == "free-query" and info["queries"]:
            # la query_en de la PRIMERA directiva sustituye a _free_query (las demás son insumos extra: una
            # llamada por insumo en _run_workspace_family); la sustituida se conserva declarada
            first = info["queries"][0]
            q["query_replaced"] = {"query": q.get("query"), "query_source": q.get("query_source")}
            q["query"] = first["query_en"]
            first_rids = list(dict.fromkeys(d["requirement_id"] for d in info["queries"] if d["query_en"] == first["query_en"]))
            q["query_source"] = QUERY_SOURCE_DIRECTIVE_PREFIX + ",".join(first_rids)
            q["directive_queries"] = [dict(d) for d in info["queries"]]
            for d in info["queries"]:
                _mark_input(d["query_en"], d["requirement_id"])
                applied_by_rid[d["requirement_id"]].append("free-query" if d["query_en"] == first["query_en"] else "free-query-extra")
        elif mode == "literature-query" and info["queries"]:
            # literatura: la query del constructor SIGUE; cada directiva corre como UNA llamada EXTRA dentro del
            # presupuesto de la familia (_literature_directive_calls; `calls[]` lo muestra)
            q["directive_queries"] = [dict(d) for d in info["queries"]]
            for d in info["queries"]:
                _mark_input(d["query_en"], d["requirement_id"])
                applied_by_rid[d["requirement_id"]].append("literature-extra-query")
        if mode == "symbols" and info["symbols"]:
            # los `symbols` de la directiva (entities_resolved por resolve_id, C.4) se AÑADEN con el MISMO saneo
            # que los símbolos de la corrida; uno ya presente no se duplica ni se atribuye
            base = list(q.get("symbols") or [])
            added, dropped_d = [], []
            for rid, raw in info["symbols"]:
                used, _dropped, _san = search_queries.sanitize_symbols([raw])
                if not used:
                    dropped_d.append(raw)
                    continue
                clean = used[0]
                if clean in base:
                    continue
                if clean not in added:
                    added.append(clean)
                _mark_input(clean, rid)
                applied_by_rid[rid].append(f"symbol:{clean}")
            q["symbols"] = base + added
            q["symbols_from_directives"] = added
            if dropped_d:
                q["symbols_from_directives_dropped"] = dropped_d
        if d_inputs:
            q["directive_inputs"] = d_inputs
        for row in d_rows:
            if row["family"] == fam:
                row["state"] = "applied"
                row["applied_as"] = list(applied_by_rid.get(row["requirement_id"]) or ["family-only"])
    excluded_by_fam = {e["family"]: e["reason"] for e in excluded}
    for row in d_rows:
        if row["state"] is not None:
            continue
        reason = excluded_by_fam.get(row["family"])
        if reason is None:
            row["state"] = "not-requested (caller families)"   # families= del llamador manda; la directiva se declara
        elif reason.startswith("unknown-family"):
            row["state"], row["reason"] = "excluded-unknown-family", reason
        elif reason.startswith("unsatisfiable-by-harness"):
            row["state"], row["reason"] = "excluded-unsatisfiable", reason
        else:
            row["state"], row["reason"] = f"excluded ({reason})", reason

    plan = {"plan_version": PLAN_VERSION, "harness_version": HARNESS_VERSION,
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
    if directives:
        # llaves ADITIVAS sólo con directivas (ADR-0082 G.3): sin ellas el plan es el de ADR-0080 byte a byte
        plan["directives_applied"] = d_rows
        plan["families_from_directives"] = families_from_directives
        plan["n_directives_excluded"] = sum(1 for r in d_rows if str(r["state"]).startswith("excluded"))
    if families_order_rule is not None:
        plan["families_order_rule"] = families_order_rule   # ADR-0084 (C.4): sólo cuando web está en el plan
    return plan


def plan_event_payload(plan):
    """Payload del evento stage.search.plan — el plan sin el dict completo del constructor de queries."""
    out = {k: plan.get(k) for k in ("plan_version", "harness_version", "rounds_cap", "rounds_cap_source",
                                    "round_budget_s", "round_budget_s_source", "families", "families_source",
                                    "families_default", "families_excluded", "directives_state",
                                    "queries", "question_en_source", "symbols", "symbols_dropped")}
    out["n_directives"] = len(plan.get("directives") or [])
    if plan.get("families_order_rule") is not None:
        # corrector ADR-0084 (C.4/G.6): la Traza pinta «web primera» desde el evento; ausente sin web → forma de hoy byte a byte
        out["families_order_rule"] = plan["families_order_rule"]
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


def normalize_item(family, element, spec=None, tool_result=None, input_value=None, directive_requirement_ids=None):
    """Un elemento crudo del tool -> ítem normalizado (contrato del docstring del módulo). Nunca inventa un
    identificador: usa el del elemento (evidence_id | id | curie | accession | doi | ...) con la procedencia que
    el tool declare (o 'tool-payload'); si no hay ninguno, deriva '<family>:sha256:<16>' del statement y lo
    declara (identifier_provenance 'derived:sha256-of-statement' + gap_flag). ADR-0082 (G.3):
    `directive_requirement_ids[]` = los requisitos del consejo para los que este ítem se trajo (_rids_for; [] =
    ninguno — la llave viaja SIEMPRE, ausente sólo en registros < 1.11)."""
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
            "directive_requirement_ids": list(directive_requirement_ids or []),   # ADR-0082 (G.3)
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
        inputs = [q.get("query")] if q.get("query") else []
        # ADR-0082 (G.3): las queries de las directivas del consejo son INSUMOS de la familia (una llamada por
        # insumo en Layer 0; una llamada EXTRA por directiva en las legadas) — así inputs_used / inputs_signature /
        # families_with_new_inputs las ven y "nada se re-ejecuta" sigue midiendo la firma completa
        for dq in q.get("directive_queries") or []:
            qe = (dq or {}).get("query_en")
            if qe and qe not in inputs:
                inputs.append(qe)
        return inputs, mode
    if mode == "dois":
        return list(dict.fromkeys(ctx.get("dois") or [])), mode
    if mode == "zfin-curies":
        return list(dict.fromkeys(ctx.get("curies") or [])), mode
    return [], mode


def _family_status(items, statuses):
    """Agregación DECLARADA de las llamadas de una familia a UN estado (la regla de _run_workspace_family, ADR-0080;
    ADR-0082 la reutiliza para las legadas con llamadas extra de directiva): >=1 ítem -> success; ninguna llamada
    corrió y todas quedaron sin presupuesto -> skipped-budget; alguna llamada MIDIÓ 0 -> no-match (los errores de
    las demás se declaran en partial_errors, no se esconden); todas 'tool-unavailable' | 'skipped-budget' |
    'not-requested' -> ese literal heredado; si no, error."""
    if items:
        return "success"
    if not statuses:
        return "skipped-budget"
    if any(s in RAN_STATES for s in statuses):
        return "no-match"
    if all(s == "tool-unavailable" for s in statuses):
        # ADR-0080 C7 (costura C2<->C3/C5): las tools declaran 'tool-unavailable' (p. ej. unpaywall sin
        # WITT_UNPAYWALL_EMAIL) y 'skipped-budget' (timeout<=0) en su raíz; si TODAS las llamadas lo dijeron,
        # la familia hereda ese literal del vocabulario del ledger — no se degrada a 'error'
        return "tool-unavailable"
    if all(s == "skipped-budget" for s in statuses):
        return "skipped-budget"
    if all(s == "skipped-cap" for s in statuses):
        # ADR-0084 (C.5): la familia web hereda 'skipped-cap' cuando TODAS sus consultas quedaron sin enviar por un tope
        # (cuota mensual, WITT_WEB_MAX_QUERIES, cortacircuito auth) — literal ya en SOURCE_STATES, no se degrada a error
        return "skipped-cap"
    if all(s == "not-requested" for s in statuses):
        # corrector ADR-0080: un "no se pidió" declarado por el tool en TODAS sus llamadas se hereda, no se
        # degrada a fallo
        return "not-requested"
    return "error"


def _run_workspace_family(family, spec, plan, ctx, budget_s, fn, fn_resolved, fn_detail):
    """Una familia Layer 0 genérica: una llamada por insumo (símbolo | query | DOI) dentro del presupuesto de la
    familia; la fila agrega los estados de las llamadas (`calls[]`) y los ítems se normalizan.

    Reparto dentro de la familia: la PRIMERA llamada siempre corre (la admisión la decidió el reparto de la
    ronda) con timeout = max(MIN_CALL_TIMEOUT_S, restante / llamadas_restantes); las siguientes solo si queda
    al menos MIN_CALL_TIMEOUT_S — si no, 'skipped-budget' por llamada, declarado en calls[] y contado en
    n_calls_skipped_budget. ADR-0082 (G.3): cada ítem lleva los requirement_id de su INSUMO (_rids_for)."""
    inputs, mode = _inputs_for(family, spec, plan, ctx)
    q_fam = (plan.get("queries") or {}).get(family) or {}
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
            rids = _rids_for(q_fam, inp)
            if rids:
                call["directive_requirement_ids"] = rids   # ADR-0082 (G.3): la llamada que el consejo pidió
            for el in elements:
                items.append(normalize_item(family, el, spec, res, input_value=inp, directive_requirement_ids=rids))
        else:
            call["error"] = str(res.get("error", ""))[:200]
            if st not in SOURCE_STATES:
                call["status_raw"], call["status"] = st, "error"
        statuses.append(call["status"])
        calls.append(call)
    elapsed_total = round(_monotonic() - t0, 3)
    status = _family_status(items, statuses)   # la regla declarada (ver _family_status)
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


def _literature_directive_calls(row, items, q, budget_s, t0, base_status, base_led, base_query, timeout_cap,
                                search, to_items):
    """ADR-0082 (G.3): en europepmc/pubmed cada directiva del consejo con `query_en` corre como UNA llamada EXTRA
    dentro del presupuesto de la familia (la del constructor SIGUE y va primero en `calls[]`; después una fila por
    directiva con su requirement_id). Sin presupuesto (restante < MIN_CALL_TIMEOUT_S) la llamada queda
    'skipped-budget' declarada y contada, SIN tocar la red. Los ítems de una llamada de directiva llevan
    `directive_requirement_ids` = _rids_for(q, query_en); la fila re-agrega su estado con la MISMA regla de las
    familias Layer 0 (_family_status) y recuenta n_found sobre las llamadas que MIDIERON. `row["ledger"]` sigue
    siendo el ledger de la llamada BASE (path_b publica europepmc_searched / pubmed_searched byte-compatibles).
    Muta `row` e `items`; sin `directive_queries` no hace nada (byte-identidad sin directivas)."""
    dqs = [d for d in (q.get("directive_queries") or []) if isinstance(d, dict) and d.get("query_en")]
    if not dqs:
        return
    calls = [{"input": base_query, "kind": "builder", "status": base_status,
              "n_found": base_led.get("n_returned") if base_status in RAN_STATES else None,
              "elapsed_s": base_led.get("elapsed_s"), "query_sent": base_led.get("query_sent"),
              "directive_requirement_ids": _rids_for(q, base_query)}]
    statuses, n_skipped = [base_status], 0
    for dq in dqs:
        rid, qe = dq.get("requirement_id"), dq["query_en"]
        remaining = budget_s - (_monotonic() - t0)
        if remaining < MIN_CALL_TIMEOUT_S:
            n_skipped += 1
            calls.append({"input": qe, "kind": "council-directive", "requirement_id": rid, "status": "skipped-budget",
                          "detail": f"family budget {round(budget_s, 3)}s exhausted", "directive_requirement_ids": [rid]})
            continue
        timeout_s = round(max(MIN_CALL_TIMEOUT_S, min(float(timeout_cap), remaining)), 3)
        c0 = _monotonic()
        try:
            found, led2 = search(qe, timeout_s)
        except Exception as e:   # cinturón §6: una llamada de directiva que lanza degrada SU llamada, no la familia
            found, led2 = [], {"status": "error", "error": f"{type(e).__name__}: {str(e)[:200]}", "query_sent": qe}
        led2 = led2 if isinstance(led2, dict) else {}
        st2, det2 = _legacy_status(led2)
        call = {"input": qe, "kind": "council-directive", "requirement_id": rid, "status": st2,
                "elapsed_s": round(_monotonic() - c0, 3), "timeout_s": timeout_s, "query_sent": led2.get("query_sent"),
                "n_found": led2.get("n_returned") if st2 in RAN_STATES else None, "directive_requirement_ids": [rid]}
        if st2 == "error":
            call["error"] = led2.get("error") or led2.get("detail")
        elif det2:
            call["detail"] = det2
        rids = _rids_for(q, qe) or [rid]
        if st2 in RAN_STATES:
            for it in to_items(found or [], rids):
                items.append(it)
        statuses.append(st2)
        calls.append(call)
    status = _family_status(items, statuses)
    n_err = sum(1 for s in statuses if s == "error")
    row["status"] = status
    row["n_found"] = (sum(int(c.get("n_found") or 0) for c in calls if c.get("status") in RAN_STATES)
                      if status in RAN_STATES else None)
    row["n_new"] = None   # run_round lo mide sobre los ítems admitidos
    row["elapsed_s"] = round(_monotonic() - t0, 3)
    row["calls"] = calls
    row["n_calls"], row["n_calls_error"], row["n_calls_skipped_budget"] = len(calls), n_err, n_skipped
    row["directive_calls_rule"] = "one extra call per council directive within the family budget (ADR-0082 G.3)"
    if status == "error":
        row["error"] = (row.get("error") or next((c.get("error") for c in calls if c.get("error")), None)
                        or "mixed call statuses: " + json.dumps(sorted(set(statuses))))
    else:
        # una familia que MIDIÓ no viaja con `error`: los fallos parciales se declaran, no se esconden
        row.pop("error", None)
        if n_err:
            row["partial_errors"] = n_err


def _run_legacy_family(family, spec, plan, ctx, budget_s):
    """Adaptadores de las tres fuentes que ya existían — llaman a answer_pipeline (import perezoso) y conservan
    el ledger de hoy en `ledger` para que path_b publique europepmc_searched / pubmed_searched / zfin_searched.
    ADR-0082 (G.3): con `directive_queries` en queries[fam] la literatura corre una llamada EXTRA por directiva
    (_literature_directive_calls); los ítems llevan `directive_requirement_ids` (_rids_for: ZFIN por símbolo).

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
    q_fam = (plan.get("queries") or {}).get(family) or {}   # ADR-0082 (G.3): directive_inputs / entered_by
    if family == "europepmc":
        base_query = (qb.get("europepmc") or {}).get("query")
        # corrector ADR-0080: el presupuesto de la familia ACOTA la llamada (timeout por GET = min(default del
        # módulo, presupuesto)); antes la fuente usaba HTTP_TIMEOUT_S fijo y podía rebasar la ronda entera
        fam_timeout = round(max(MIN_CALL_TIMEOUT_S, min(float(getattr(ap.fetch_paper, "HTTP_TIMEOUT_S", 30) or 30), budget_s)), 3)
        accepts_timeout = _accepts(ap._search_europepmc, "timeout")

        def _epmc_search(query, timeout_s):
            if accepts_timeout:
                return ap._search_europepmc(query, retmax, timeout=timeout_s)
            return ap._search_europepmc(query, retmax)

        def _epmc_items(recs, rids):
            out = []
            for rec in recs:
                cand = ap._epmc_candidate(rec)
                cand.update({"kind": "literature-candidate", "source_family": "europepmc", "label": None,
                             "statement": None, "title": (cand.get("search_rec") or {}).get("title"),
                             "url": f"https://europepmc.org/abstract/MED/{rec['pmid']}" if rec.get("pmid") else None,
                             "identifier_provenance": "europepmc-api-live", "raw_ref": None, "text": None,
                             "directive_requirement_ids": list(rids)})
                out.append(cand)
            return out

        recs, led = _epmc_search(base_query, fam_timeout)
        scope = (f"per-call (timeout {fam_timeout}s = min(fetch_paper.HTTP_TIMEOUT_S, family budget))" if accepts_timeout
                 else "module-default (fetch_paper.HTTP_TIMEOUT_S)")
        items = _epmc_items(recs, _rids_for(q_fam, base_query))
        status, detail = _legacy_status(led)
        row = _row("europepmc", spec, status, n_found=led.get("n_returned") if status in RAN_STATES else None,
                   elapsed_s=led.get("elapsed_s", round(_monotonic() - t0, 3)), query_sent=led.get("query_sent"),
                   cache_hit=None, timeout_s_scope=scope, inputs_mode=inputs_mode, inputs_used=list(inputs),
                   budget_s=round(budget_s, 3), ledger=led)
        if status == "error":
            row["error"] = led.get("error") or led.get("detail")
        elif detail:
            row["detail"] = detail
        _literature_directive_calls(row, items, q_fam, budget_s, t0, status, led, base_query, fam_timeout,
                                    _epmc_search, _epmc_items)
        return row, items
    if family == "pubmed":
        base_query = (qb.get("pubmed") or {}).get("query")
        existing = ctx.get("pubmed_seen") or {}
        # corrector ADR-0080: mismo acotamiento que EPMC — timeout por GET = min(30 s del tool, presupuesto de la
        # familia); el reintento 429 (Retry-After ≤ 60 s) sigue siendo del tool y se declara en su ledger
        fam_timeout = round(max(MIN_CALL_TIMEOUT_S, min(30.0, budget_s)), 3)
        accepts_timeout = _accepts(ap._search_pubmed, "timeout")

        def _pubmed_search(query, timeout_s):
            if accepts_timeout:
                return ap._search_pubmed(query, retmax, existing, timeout=timeout_s)
            return ap._search_pubmed(query, retmax, existing)

        def _pubmed_items(cands, rids):
            out = []
            for cand in cands:
                cand.update({"kind": "literature-candidate", "source_family": "pubmed", "label": None,
                             "statement": None, "title": (cand.get("search_rec") or {}).get("title"),
                             "url": f"https://pubmed.ncbi.nlm.nih.gov/{cand['search_rec']['pmid']}/" if cand["search_rec"].get("pmid") else None,
                             "identifier_provenance": "ncbi-eutils-live", "raw_ref": None, "text": None,
                             "directive_requirement_ids": list(rids)})
                out.append(cand)
            return out

        cands, led = _pubmed_search(base_query, fam_timeout)
        scope = (f"per-call (timeout {fam_timeout}s = min(30, family budget); 429 retry-after is the tool's, declared)"
                 if accepts_timeout else "module-default (pubmed_literature)")
        items = _pubmed_items(cands, _rids_for(q_fam, base_query))
        status, detail = _legacy_status(led)
        row = _row("pubmed", spec, status, n_found=led.get("n_returned") if status in RAN_STATES else None,
                   elapsed_s=round(_monotonic() - t0, 3), query_sent=led.get("query_sent"), cache_hit=None,
                   timeout_s_scope=scope, inputs_mode=inputs_mode, inputs_used=list(inputs),
                   budget_s=round(budget_s, 3), ledger=led)
        if status == "error":
            row["error"] = led.get("detail") or led.get("error")
        elif detail:
            row["detail"] = detail
        _literature_directive_calls(row, items, q_fam, budget_s, t0, status, led, base_query, fam_timeout,
                                    _pubmed_search, _pubmed_items)
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
                       "raw_ref": ((it.get("fetched") or {}).get("raw_cached") or [None])[0],
                       # ADR-0082 (G.3): ZFIN se atribuye por SÍMBOLO (el ítem sabe cuál lo trajo: zfin.symbol)
                       "directive_requirement_ids": _rids_for(q_fam, z.get("symbol"))})
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


# ---------------------------------------------------------------------------------------------------------
# ADR-0084 (C.5) — la familia `web`: adaptador PROPIO que NO pasa por normalize_item (Context 2) y emite CERO ítems
# con source 'web'. lib/web_locator.locate devuelve por consulta URLs resueltas a identificadores por una TABLA
# determinista (fila-query); los de literatura se MATERIALIZAN aquí, en la MISMA ronda, por Europe PMC
# (la MISMA consulta de fetch_paper._resolve_one vía search_europepmc_ledger(timeout=<presupuesto restante>) — corrector: UNA GET paceada
# y ACOTADA, SIN escribir caché, con el registro verificado contra el ident — Context 4: fetch_external envenenaría el read-cache
# abstract-only del paper seleccionado) y entran como candidatos `source 'europepmc'` / `source_family 'web'` /
# `identifier_provenance 'web-located:<rule>'`; los DOI van a ctx['dois'] (unpaywall_crossref) y las curies ZDB-GENE a
# ctx['curies'] (monarch) — append sobre las listas pre-creadas, jamás reasignar (M.3). Ningún título, snippet ni URL
# de la web llega a los ítems ni a los eventos: viven SÓLO en la fila (`web_locator {queries, located, unresolved}`),
# que runs congela en frozen.web_locator (el ledger humano, con URL completa).
# ---------------------------------------------------------------------------------------------------------
WEB_FED_TO_POOL = "pool:literature-candidate (materialized by europepmc)"
WEB_SEARCH_REC_SOURCE = "europepmc-record (web-located candidate; fetch_paper._resolve_one)"
WEB_AUTH_CIRCUIT_DETAIL = "auth failed in this round (no retry)"
WEB_NO_QUERY_DETAIL = "no English query (nothing to search)"
WEB_LOCATOR_FN_RESOLVED = "web_locator.locate"
WEB_DEDUP_LAYER = "pool"
WEB_DEDUP_LAYER_RULE = ("web-located candidates bypass the round's evidence_id dedup and are appended AFTER the native "
                        "families' items (run_round): a native family that brings the same id keeps the identity and the "
                        "pool (answer_pipeline._pool_add, native-first admission) declares the web one as duplicate "
                        "(ADR-0084 D.1); against ids already present in the run (existing_ids) they are dropped here")
WEB_MATERIALIZE_RULE = ("literature ids (pmid | pmcid | doi) located on the web are verified in Europe PMC in the same "
                        "round — fetch_paper.search_europepmc_ledger(<ident query>, n=1, timeout=<family budget left>) (the "
                        "query of fetch_paper._ident_query; DOIs with EPMC syntax chars travel quoted), ident in EPMC form only, "
                        "one GET each, no cache write (fetch_external runs later, only for the SELECTED paper); the record "
                        "returned must carry the located identifier (PMID/PMCID/DOI) or it is declared 'error: europepmc record "
                        "mismatch' and is NOT a candidate; a pattern that matched but does not exist in Europe PMC is NOT a "
                        "candidate ('not-found-in-europepmc'); WITT_WEB_MAX_MATERIALIZE caps the GETs per round (ADR-0084 C.5; "
                        "corrector: budget-bounded timeout + identity check)")
# corrector ADR-0084: el MISMO paper devuelto por la web en varias formas (pubmed + PMC + doi.org) se materializa UNA vez — las
# llaves PMID:/PMCID:/DOI: del registro (answer_pipeline._candidate_keys) se recuerdan en la familia y las formas siguientes quedan
# 'already-present (dup of <evidence_id>)' sin segunda GET ni segundo candidato (antes: 3 GETs, 3 candidatos, ledger contradictorio)
WEB_SAME_PAPER_RULE = ("same paper by PMID/PMCID/DOI (answer_pipeline._candidate_keys of the Europe PMC record) as one already "
                       "materialized in this family this round: no second Europe PMC GET, no second candidate; declared "
                       "'already-present (dup of <evidence_id>)' with same_paper {of, matched_key, layer 'family'} (corrector ADR-0084)")
_EPMC_DOI_QUOTE_RE = re.compile(r'[()<>;:"\s]')


def epmc_paper_key(kind, ident):
    """La llave de PAPER (forma de answer_pipeline._candidate_keys) de un hallazgo de literatura: 'PMID:<n>' | 'PMCID:PMC<n>' |
    'DOI:<doi minúsculas>'; None para otros kinds (corrector ADR-0084: dedup por paper dentro de la familia web)."""
    if kind == "pmid":
        return str(ident)
    if kind == "pmcid":
        return f"PMCID:{str(ident).upper()}"
    if kind == "doi":
        d = str(ident or "").strip().lower()
        for pre in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
            if d.startswith(pre):
                d = d[len(pre):]
        return f"DOI:{d}" if d else None
    return None


def epmc_query_for(epmc_id):
    """(query, quoted) — la consulta a Europe PMC para un ident en forma EPMC (la de fetch_paper._ident_query); un DOI con
    caracteres de la sintaxis de EPMC (paréntesis, dos puntos, <>, ;, comillas, espacios — p. ej. un SICI) viaja entre comillas
    para que el parser no lo reinterprete (corrector ADR-0084; fetch_paper no se toca)."""
    from lib import fetch_paper
    q, _ = fetch_paper._ident_query(epmc_id)
    if str(epmc_id).upper().startswith("DOI:"):
        v = str(epmc_id).split(":", 1)[1].strip()
        if _EPMC_DOI_QUOTE_RE.search(v):
            return f'DOI:"{v}"', True
    return q, False


def epmc_ident_of_query(query):
    """Inverso de epmc_query_for — para instrumentos y smokes que fakean fetch_paper.search_europepmc_ledger y sirven por ident:
    'EXT_ID:<n> AND SRC:MED' → 'PMID:<n>' · 'PMCID:PMC<n>' → 'PMC<n>' · 'DOI:<v>' | 'DOI:"<v>"' → 'DOI:<v>'; None si la
    consulta no es una de esas tres formas (búsqueda libre de la familia europepmc)."""
    q = str(query or "").strip()
    m = re.fullmatch(r"EXT_ID:(\d+) AND SRC:MED", q)
    if m:
        return f"PMID:{m.group(1)}"
    m = re.fullmatch(r"PMCID:(PMC\d+)", q, re.I)
    if m:
        return m.group(1).upper()
    m = re.fullmatch(r'DOI:"(.+)"', q) or re.fullmatch(r"DOI:(\S+)", q)
    if m:
        return f"DOI:{m.group(1)}"
    return None


def _web_query_row_skipped(wl, query, cfg, ps, rids, round_no, query_source, status, detail):
    """Fila-query con la MISMA forma que web_locator.locate para una consulta que este adaptador NO envió (cortacircuito
    auth C.5 · presupuesto de la familia · fallo del propio módulo): provider_status ∈ SOURCE_STATES y `state` del
    vocabulario de web_locator ('skipped-cap (<detail>)' | 'skipped-budget (<detail>)' | 'error: <detail>'); cero red,
    cero cuota, contadores null (no midió)."""
    q = str(query or "").strip()
    cap = int(cfg.get("max_query_chars") or 400)
    row = {"round": round_no, "query_en": str(query or ""), "query_sent": q[:cap], "query_source": query_source,
           "requirement_ids": list(rids or []), "provider": ps.get("provider"), "provider_source": ps.get("provider_source"),
           "provider_status": status, "state": None, "http_status": None, "elapsed_s": 0.0, "throttle_wait_s": 0.0,
           "retries_429": 0, "cache_hit": False, "query_truncated": len(q) > cap, "query_altered_by_provider": False,
           "n_results": None, "n_located": None, "n_unresolved": None, "n_duplicates_in_response": None,
           "n_already_present": None, "located": [], "unresolved": [], "cost_usd_projected": 0.0, "billable": False,
           "n_billable": 0, "quota": {"state": None, "n_after": None, "cap": int(cfg.get("monthly_cap") or 0), "month": None},
           "resolver_version": wl.RESOLVER_VERSION, "module_version": wl.MODULE_VERSION,
           "not_sent_by": "search_harness._run_web_family"}
    if status == "error":
        row["error"], row["state"] = detail, f"error: {detail}"
    else:
        row["detail"], row["state"] = detail, f"{status} ({detail})"
    return row


def _run_web_family(family, spec, plan, ctx, budget_s, tools=None):
    """La familia web dentro de la ronda (ADR-0084 C.5) — (fila, ítems).

    Por insumo de _inputs_for (las query_en de las directivas del consejo; o la consulta del operador cuando web entró
    por WITT_SEARCH_DEFAULT_FAMILIES), dentro del tope WITT_WEB_MAX_QUERIES y del presupuesto de la familia (timeout =
    max(MIN_CALL_TIMEOUT_S, restante / consultas_restantes), patrón _run_workspace_family):
      web_locator.locate(query, cfg, provider_fn=tools['web'] (fake de smoke | None → tool real por ruta),
                         quota_fn=ctx['web_quota'] (runs: db.web_locator_reserve; ausente → 'not-enforced', declarado),
                         existing_ids=ctx['existing_ids'] ∪ ids ya localizados en esta familia, store=ctx['web_store'],
                         timeout, requirement_ids, round_no=ctx['round'], query_source)
    → fila-query; con `located[]` (dedup None): kind ∈ pmid|pmcid|doi → MATERIALIZACIÓN por Europe PMC
    (fetch_paper._resolve_one(epmc_ident) — forma verificada ANTES de llamar; tope WITT_WEB_MAX_MATERIALIZE por ronda y
    presupuesto de la familia) → candidato answer_pipeline._epmc_candidate(rec) + {kind 'literature-candidate', source
    'europepmc', source_family 'web', identifier_provenance 'web-located:<rule>', url canónica (JAMÁS la hallada),
    located_from {host, rule_id, confidence, kind, round, requirement_ids}, search_rec_source, located_via 'web',
    dedup_layer 'pool'}; `rec None` → feed_state 'not-found-in-europepmc' (contado, no candidato); kind 'doi' además →
    ctx['dois'] (append); 'zfin-curie' ZDB-GENE → ctx['curies'] ('fed-same-round'); otros ZDB / ensdarg / uniprot / gse
    → fed_to None, 'no-sink-in-1.13 (<kind>)'; dedup 'already-present (existing_ids)' → 'already-present (dup of <id>)';
    'duplicate-in-response' → ídem. Cortacircuito auth: un `error: auth…` deja las consultas restantes 'skipped-cap'
    con detail WEB_AUTH_CIRCUIT_DETAIL, cero red. Hook ctx['on_web_locate'](payload) UNA vez por consulta DECLARADA —
    enviada o skipped-cap / skipped-budget / error (corrector ADR-0084: el latido de una consulta que la cuota frenó también
    se emite, con detail); jamás bajo tool-unavailable — (ids y hosts, sin URLs) → evento stage.web.locate (runs). La fila agrega con _family_status (success = ≥ 1
    candidato materializado; no-match = midió y 0 materializados, con detail; tool-unavailable / skipped-cap /
    skipped-budget / error heredados) y lleva el ledger COMPLETO en `web_locator` (las URLs viven SÓLO ahí)."""
    from lib import web_locator as wl
    from lib import fetch_paper
    from lib import answer_pipeline as ap

    inputs, mode = _inputs_for(family, spec, plan, ctx)
    q_fam = (plan.get("queries") or {}).get(family) or {}
    if not inputs:
        return _row(family, spec, "not-requested", detail=WEB_NO_QUERY_DETAIL, inputs_mode=mode, inputs_used=[]), []
    cfg = wl.env_config()          # M.4: las 17 env se leen EN LA LLAMADA
    ps = wl.provider_state()       # M.4: disponibilidad en el despacho (plan y compilación ya la leyeron)
    round_no = ctx.get("round")
    provider_fn = tools.get(family) if isinstance(tools, dict) and callable(tools.get(family)) else None
    quota_fn = ctx.get("web_quota") if callable(ctx.get("web_quota")) else None
    store = ctx.get("web_store") if callable(ctx.get("web_store")) else None
    on_locate = ctx.get("on_web_locate") if callable(ctx.get("on_web_locate")) else None
    max_q, max_mat = int(cfg["max_queries"]), int(cfg["max_materialize"])
    existing = set(str(x) for x in (ctx.get("existing_ids") or ()) if x is not None)
    seen_ids = set()                                     # ids nativos ya localizados/materializados en ESTA familia
    seen_keys = {}                                       # corrector: llave de PAPER (PMID:/PMCID:/DOI:) -> evidence_id materializado
    dois, curies = ctx.setdefault("dois", []), ctx.setdefault("curies", [])   # M.3: append-only, jamás reasignar
    t0 = _monotonic()
    calls, queries, located_all, unresolved_all, items, statuses = [], [], [], [], [], []
    tally = {"epmc_gets": 0, "materialized": 0, "not_found": 0, "same_paper": 0, "mismatch": 0}
    n_dropped = n_calls_skipped = 0
    auth_failed = False
    n_planned = min(len(inputs), max_q)

    def _qsrc(inp, rids):
        if rids:
            return QUERY_SOURCE_DIRECTIVE_PREFIX + ",".join(rids)
        if inp == q_fam.get("query"):
            return q_fam.get("query_source")
        return "plan:directive_queries"

    def _feed_doi(form):
        """(ii) → ctx['dois'] para unpaywall_crossref en la MISMA ronda: append-only (M.3) y sin duplicar por mayúsculas —
        corrector ADR-0084: la cosecha de run_round escribe la forma del registro EPMC; aquí se escribe la MISMA cadena cuando el
        registro existe, y la normalizada cuando no, comparando en minúsculas (un DOI no se manda dos veces a Crossref)."""
        if form and str(form).lower() not in {str(x).lower() for x in dois}:
            dois.append(form)

    def _feed(loc, rids):
        """Un hallazgo del resolutor → fed_to / feed_state (vocabularios de web_locator) y, para literatura, el candidato
        materializado (o None)."""
        kind, ident = loc.get("kind"), loc.get("id")
        loc["fed_to"], loc["feed_state"] = None, None
        dedup = loc.get("dedup")
        if dedup == "already-present (existing_ids)":
            loc["feed_state"] = f"already-present (dup of {ident})"
            return None
        if dedup == "duplicate-in-response":
            loc["feed_state"] = "duplicate-in-response"
            return None
        seen_ids.add(str(ident))
        if kind in wl.LITERATURE_KINDS:
            d = wl.normalize_doi(ident) if kind == "doi" else None
            key = epmc_paper_key(kind, ident)
            prev = seen_keys.get(key) if key else None
            if prev is not None:
                # corrector ADR-0084: el MISMO paper en otra forma (pubmed + PMC + doi.org): sin 2ª GET ni 2º candidato
                tally["same_paper"] += 1
                loc.update(evidence_id=prev, feed_state=f"already-present (dup of {prev})",
                           same_paper={"of": prev, "matched_key": key, "layer": "family", "rule": WEB_SAME_PAPER_RULE})
                return None
            if kind == "doi":
                loc["fed_to"], loc["fed_ctx"] = "ctx:dois", ["ctx:dois"]
            epmc_id = wl.epmc_ident(loc)
            if not epmc_id or not wl.EPMC_IDENT_RE.match(epmc_id):
                # Context 4: un texto libre ataría el TOP HIT equivocado — sólo PMID:<n> | PMC<n> | DOI:<doi> viajan
                _feed_doi(d)
                loc["feed_state"] = "error: identifier not in Europe PMC form (not sent to _resolve_one)"
                return None
            if tally["epmc_gets"] >= max_mat:
                _feed_doi(d)
                loc["feed_state"] = "not-materialized (feed cap)"
                return None
            left_s = budget_s - (_monotonic() - t0)
            if left_s < MIN_CALL_TIMEOUT_S:
                _feed_doi(d)
                loc["feed_state"] = "not-materialized (budget)"
                return None
            tally["epmc_gets"] += 1
            loc["epmc_ident_sent"] = epmc_id
            # corrector ADR-0084 (M.1): la GET a Europe PMC usa el presupuesto RESTANTE de la familia (antes: HTTP_TIMEOUT_S 30 s por
            # ident — 6 idents lentos podían retener la ronda 180 s); misma consulta que fetch_paper._resolve_one, sin escribir caché
            epmc_timeout = round(max(MIN_CALL_TIMEOUT_S, min(float(fetch_paper.HTTP_TIMEOUT_S), left_s)), 3)
            q_epmc, quoted = epmc_query_for(epmc_id)
            loc["epmc_timeout_s"], loc["epmc_query_quoted"] = epmc_timeout, quoted
            try:
                hits, led = fetch_paper.search_europepmc_ledger(q_epmc, n=1, timeout=epmc_timeout)   # UNA GET paceada, SIN caché
            except Exception as e:   # cinturón §6: EPMC caído deja el hallazgo declarado, la ronda sigue
                _feed_doi(d)
                loc["feed_state"] = f"error: {type(e).__name__}: {str(e)[:160]}"
                return None
            led = led if isinstance(led, dict) else {}
            rec = hits[0] if hits else None
            loc["epmc_search_status"] = led.get("status")
            if not rec:
                tally["not_found"] += 1
                _feed_doi(d)
                loc["feed_state"] = "not-found-in-europepmc"
                return None
            rec_keys = ap._candidate_keys(rec)
            if key not in rec_keys:
                # corrector ADR-0084 (Context 4): el registro devuelto NO es el identificador localizado (trampa del top hit) — se
                # declara bajo el prefijo 'error: ' y NO es candidato (atar un paper equivocado con web-located sería peor que nada)
                tally["mismatch"] += 1
                _feed_doi(d)
                loc["feed_state"] = f"error: europepmc record mismatch ({', '.join(rec_keys) or 'no ids'} != {key})"
                return None
            cand = ap._epmc_candidate(rec)   # forma NATIVA del evidence_id (Context 7): mismo dedup en dos capas
            if not cand.get("evidence_id"):
                _feed_doi(d)
                loc["feed_state"] = "error: europepmc record without identifier"
                return None
            # la forma del registro EPMC (la que cosecha run_round) manda sobre la normalizada: UNA cadena en ctx:dois
            if kind == "doi":
                _feed_doi((cand.get("search_rec") or {}).get("doi") or d)
            cand.update({"kind": "literature-candidate", "source": "europepmc", "source_family": "web", "label": None,
                         "statement": None, "title": (cand.get("search_rec") or {}).get("title"),
                         "url": loc.get("canonical_url"),
                         "identifier_provenance": wl.identifier_provenance(loc),
                         "located_via": "web",
                         "located_from": {"host": loc.get("host"), "rule_id": loc.get("resolver_rule"),
                                          "confidence": loc.get("confidence"), "kind": kind, "round": round_no,
                                          "requirement_ids": list(rids)},
                         "search_rec_source": WEB_SEARCH_REC_SOURCE, "raw_ref": None, "text": None,
                         "directive_requirement_ids": list(rids), "dedup_layer": WEB_DEDUP_LAYER,
                         # corrector: la referencia al hallazgo de ORIGEN (query_index + id) — answer_pipeline cierra SÓLO esa fila
                         # located[] cuando el pool lo declara duplicado (jamás todas las del mismo evidence_id)
                         "located_ref": {"query_index": loc.get("query_index"), "id": loc.get("id")}})
            tally["materialized"] += 1
            seen_ids.add(str(cand["evidence_id"]))
            for k in rec_keys:
                # corrector: las TRES formas del paper quedan vistas en la familia (misma ronda) y viajan como existing_ids a la
                # siguiente consulta (web_locator.existing_id_key entiende PMID:<n> | PMC<n> | <doi>)
                seen_keys.setdefault(k, cand["evidence_id"])
                seen_ids.add(k.split(":", 1)[1] if k.startswith(("PMCID:", "DOI:")) else k)
            loc.update(fed_to=WEB_FED_TO_POOL, feed_state="materialized-same-round", evidence_id=cand["evidence_id"])
            return cand
        if kind == "zfin-curie":
            if "ZDB-GENE-" in str(ident):
                if ident not in curies:
                    curies.append(ident)      # (iii) → monarch en la MISMA ronda
                loc["fed_to"], loc["feed_state"] = "ctx:curies", "fed-same-round"
            else:
                zdb = str(ident).split(":", 1)[-1]
                zdb_type = "-".join(zdb.split("-")[:2]) if zdb.startswith("ZDB-") else zdb
                loc["feed_state"] = f"no-sink-in-1.13 (zfin-curie {zdb_type})"
            return None
        loc["feed_state"] = f"no-sink-in-1.13 ({kind})"   # ensdarg / uniprot: store_state ya medido; gse: no auto-feed
        return None

    for idx, inp in enumerate(inputs):
        rids = _rids_for(q_fam, inp)
        qsrc = _qsrc(inp, rids)
        if idx >= max_q:
            n_dropped += 1
            calls.append({"input": inp, "status": "skipped-cap", "detail": f"WITT_WEB_MAX_QUERIES={max_q} reached",
                          "directive_requirement_ids": rids})
            continue
        remaining = budget_s - (_monotonic() - t0)
        if auth_failed or (idx > 0 and remaining < MIN_CALL_TIMEOUT_S):
            if auth_failed:
                st, detail = "skipped-cap", WEB_AUTH_CIRCUIT_DETAIL
            else:
                st, detail = "skipped-budget", f"family budget {round(budget_s, 3)}s exhausted"
                n_calls_skipped += 1
            qrow = _web_query_row_skipped(wl, inp, cfg, ps, rids, round_no, qsrc, st, detail)
            queries.append(qrow)
            statuses.append(st)
            calls.append({"input": inp, "status": st, "detail": detail, "directive_requirement_ids": rids})
            continue
        left = n_planned - idx
        timeout_s = round(max(MIN_CALL_TIMEOUT_S, remaining / left), 3)
        c0 = _monotonic()
        try:
            qrow = wl.locate(inp, cfg, provider_fn=provider_fn, quota_fn=quota_fn, existing_ids=existing | seen_ids,
                             store=store, timeout=timeout_s, requirement_ids=rids, round_no=round_no, query_source=qsrc)
        except Exception as e:   # locate ya envuelve al proveedor; esto cubre un fallo del propio módulo (§6)
            qrow = _web_query_row_skipped(wl, inp, cfg, ps, rids, round_no, qsrc, "error",
                                          f"{type(e).__name__}: {str(e)[:160]}")
        qrow = qrow if isinstance(qrow, dict) else {}
        st = qrow.get("provider_status")
        if st not in SOURCE_STATES:
            qrow["provider_status_raw"], st = st, "error"
            qrow["provider_status"] = st
            qrow.setdefault("error", f"shape-mismatch (provider_status {qrow.get('provider_status_raw')!r} not in SOURCE_STATES)")
        cands = []
        for loc in qrow.get("located") or []:
            loc["round"], loc["requirement_ids"], loc["query_index"] = round_no, list(rids), idx
            cand = _feed(loc, rids)
            if cand is not None:
                cands.append(cand)
        for u in qrow.get("unresolved") or []:
            u["round"], u["requirement_ids"], u["query_index"] = round_no, list(rids), idx
        items.extend(cands)
        located_all.extend(qrow.get("located") or [])
        unresolved_all.extend(qrow.get("unresolved") or [])
        call = {"input": inp, "status": st, "http_status": qrow.get("http_status"),
                "elapsed_s": round(_monotonic() - c0, 3), "provider_elapsed_s": qrow.get("elapsed_s"),
                "timeout_s": timeout_s, "timeout_s_scope": "per-call (web_locator.locate -> provider timeout=)",
                "cache_hit": qrow.get("cache_hit"), "query_sent": qrow.get("query_sent"),
                "n_results": qrow.get("n_results"), "n_located": qrow.get("n_located"), "n_materialized": len(cands),
                "n_unresolved": qrow.get("n_unresolved"), "throttle_wait_s": qrow.get("throttle_wait_s"),
                "retries_429": qrow.get("retries_429"), "directive_requirement_ids": rids}
        if qrow.get("error") is not None:
            call["error"] = str(qrow["error"])[:200]
        if qrow.get("detail") is not None:
            call["detail"] = qrow["detail"]
        queries.append(qrow)
        statuses.append(st)
        calls.append(call)
        if wl.is_auth_error(qrow):
            auth_failed = True   # C.5: las consultas restantes de la ronda quedan skipped-cap, cero red
        if on_locate is not None and st != "tool-unavailable":
            # C.6 / G.6: UN latido por consulta ENVIADA — ids y hosts, jamás URLs ni títulos (0 eventos bajo off)
            payload = {"round": round_no, "provider": qrow.get("provider"), "query_en": qrow.get("query_en"),
                       "query_source": qrow.get("query_source"), "requirement_ids": list(rids),
                       "provider_status": st, "http_status": qrow.get("http_status"), "elapsed_s": qrow.get("elapsed_s"),
                       "throttle_wait_s": qrow.get("throttle_wait_s"), "cache_hit": qrow.get("cache_hit"),
                       "query_altered_by_provider": qrow.get("query_altered_by_provider"),
                       "n_results": qrow.get("n_results"), "n_located": qrow.get("n_located"),
                       "n_materialized": len(cands), "n_unresolved": qrow.get("n_unresolved"),
                       "located_ids": [l.get("id") for l in (qrow.get("located") or [])],
                       "hosts_unresolved": [u.get("host") for u in (qrow.get("unresolved") or [])],
                       "cost_usd_projected": qrow.get("cost_usd_projected"),
                       "quota": {k: (qrow.get("quota") or {}).get(k) for k in ("state", "n_after", "cap")}}
            if qrow.get("error") is not None:
                payload["error"] = str(qrow["error"])[:200]
            if qrow.get("detail") is not None:
                payload["detail"] = qrow["detail"]
            try:
                on_locate(payload)
            except Exception as e:   # el latido jamás tumba la familia; el fallo del hook se declara en la fila
                qrow["hook_error"] = f"{type(e).__name__}: {str(e)[:120]}"

    elapsed_total = round(_monotonic() - t0, 3)
    status = _family_status(items, statuses)
    ran = [qr for qr in queries if qr.get("provider_status") in RAN_STATES]
    measured = status in RAN_STATES

    def _sum(key):
        return sum(int(qr.get(key) or 0) for qr in ran)

    n_results = _sum("n_results") if measured else None
    n_located = _sum("n_located") if measured else None
    fresh = [l for l in located_all if l.get("dedup") is None]
    n_err = sum(1 for s in statuses if s == "error")
    cost = round(sum(float(qr.get("cost_usd_projected") or 0.0) for qr in queries), 6)
    quota_state = next((qr["quota"]["state"] for qr in reversed(queries) if (qr.get("quota") or {}).get("state")), None)
    if any((qr.get("n_located") or 0) > 0 for qr in ran):
        web_state = "located"
    elif ran:
        web_state = "no-results"
    elif queries:
        q0 = queries[0]
        web_state = q0.get("state") or f"error: {q0.get('error') or 'unknown'}"
        if web_state.endswith(" ()") and q0.get("error"):
            # tolerancia declarada: una fila-query de web_locator sin `detail` (el tool dejó la causa en `error`, p. ej.
            # 'BudgetExhausted: …' bajo skipped-budget) no deja un estado con paréntesis vacíos en el frozen
            web_state = web_state[:-2] + f"({q0['error']})"
    else:
        web_state = "error: no query rows"
    row = _row(family, spec, status, n_found=n_results, elapsed_s=elapsed_total, budget_s=round(budget_s, 3),
               inputs_mode=mode, inputs_used=list(inputs), n_calls=len(calls), n_calls_error=n_err,
               n_calls_skipped_budget=n_calls_skipped,
               cache_hit=(any(bool(qr.get("cache_hit")) for qr in ran) if ran else None),
               query_sent=next((qr.get("query_sent") for qr in queries if qr.get("query_sent")), None),
               fn_resolved=WEB_LOCATOR_FN_RESOLVED + (" (provider_fn injected)" if provider_fn else f" -> {ps['provider']}"),
               calls=calls,
               # ADR-0084 (C.5): el ledger de la familia — contadores ENTEROS sólo si midió (RAN_STATES), null si no
               provider=ps["provider"], provider_source=ps["provider_source"], provider_available=bool(ps["available"]),
               n_queries=len(queries), n_queries_planned=n_planned, n_queries_dropped_by_cap=n_dropped,
               max_queries=max_q, max_queries_source=cfg["sources"]["max_queries"],
               max_materialize=max_mat, max_materialize_source=cfg["sources"]["max_materialize"],
               n_results=n_results, n_located=n_located,
               n_materialized=tally["materialized"] if measured else None,
               n_epmc_gets=tally["epmc_gets"] if measured else None,
               n_not_found_in_europepmc=tally["not_found"] if measured else None,
               n_same_paper_dups=tally["same_paper"] if measured else None,      # corrector: mismo paper en varias URLs
               n_epmc_record_mismatch=tally["mismatch"] if measured else None,   # corrector: top hit ≠ ident (Context 4)
               n_fed_ctx=(sum(1 for l in fresh if l.get("fed_to") in ("ctx:dois", "ctx:curies") or l.get("fed_ctx"))
                          if measured else None),
               n_located_not_fed=sum(1 for l in fresh if l.get("fed_to") is None) if measured else None,
               n_already_present=_sum("n_already_present") if measured else None,
               n_duplicates_in_response=_sum("n_duplicates_in_response") if measured else None,
               n_unresolved=_sum("n_unresolved") if measured else None,
               cost_usd_projected=cost, quota_state=quota_state,
               quota_hook=("ctx.web_quota" if quota_fn is not None
                           else "absent (quota not enforced by the harness; runs injects db.web_locator_reserve)"),
               web_locator_state=web_state, dedup_layer=WEB_DEDUP_LAYER, dedup_layer_rule=WEB_DEDUP_LAYER_RULE,
               materialize_rule=WEB_MATERIALIZE_RULE, text_policy=wl.TEXT_POLICY,
               web_locator={"queries": queries, "located": located_all, "unresolved": unresolved_all,
                            "module_version": wl.MODULE_VERSION, "resolver_version": wl.RESOLVER_VERSION})
    if n_err and measured:
        row["partial_errors"] = n_err
    if status == "error":
        row["error"] = (next((qr.get("error") for qr in queries if qr.get("error")), None)
                        or "mixed call statuses: " + json.dumps(sorted(set(statuses))))
    elif status == "no-match":
        row["detail"] = f"n_results={n_results} n_located={n_located} n_materialized=0"
    else:
        detail = next((qr.get("detail") for qr in queries if qr.get("detail")), None)
        if detail is not None:
            row["detail"] = detail   # tool-unavailable → la razón de provider_state; skipped-* → el tope que aplicó
    for it in items:
        # estructural (el gate del brief): la familia web JAMÁS emite un ítem web — sólo candidatos de Europe PMC
        if not (it.get("source") == "europepmc" and it.get("source_family") == "web"
                and it.get("kind") == "literature-candidate" and "title_web" not in it and "description" not in it):
            raise AssertionError("ADR-0084 (C.5): the web family emitted a non-europepmc item")
    return row, items


def run_source(family, plan, ctx, budget_s, tools=None):
    """(fila, ítems) de UNA familia dentro de su presupuesto. `tools` (dict family -> callable) inyecta fakes
    para las familias Layer 0 genéricas (los smokes); las tres legadas se parchean en answer_pipeline."""
    spec = SEARCH_DISPATCH.get(family)
    # ADR-0082 (G.3): la fila SIEMPRE declara los requisitos del consejo que nombraron a la familia ([] = ninguno)
    rids_fam = list(((plan.get("queries") or {}).get(family) or {}).get("directive_requirement_ids") or [])
    if spec is None:
        return _row(family, {}, "error", error=f"unknown family {family!r}", directive_requirement_ids=rids_fam), []
    if spec.get("adapter") == "web":
        # ADR-0084 (C.5): adaptador PROPIO de la familia web — jamás normalize_item (Context 2); `tools['web']` inyecta
        # el proveedor falso (provider_fn) en los smokes; la cuota y los hooks viajan en ctx (web_quota, on_web_locate,
        # existing_ids, web_store) y su ausencia se declara, no se finge
        available, why = family_available(family)
        if not available:
            # corrector ADR-0084 (L): sin localizador (kill-switch o sin llave) la fila es la MÍNIMA de 7d9ce15 — la misma forma que
            # una familia con fn None —, cero red, cero cuota, cero latidos; la CAUSA viaja en detail y frozen.web_locator la declara
            return _row(family, spec, "tool-unavailable", detail=why or spec.get("unavailable_reason"),
                        directive_requirement_ids=rids_fam), []
        try:
            row, items = _run_web_family(family, spec, plan, ctx, budget_s, tools=tools)
        except Exception as e:   # cinturón §6 (M.1): un localizador que lanza degrada SU familia, no la ronda
            row, items = _row(family, spec, "error", error=f"{type(e).__name__}: {str(e)[:200]}"), []
        row.setdefault("directive_requirement_ids", rids_fam)
        return row, items
    if spec.get("adapter"):
        try:
            row, items = _run_legacy_family(family, spec, plan, ctx, budget_s)
        except Exception as e:   # cinturón §6: un adaptador que lanza degrada SU familia, no la ronda
            row, items = _row(family, spec, "error", error=f"{type(e).__name__}: {str(e)[:200]}"), []
        row.setdefault("directive_requirement_ids", rids_fam)
        return row, items
    if tools and family in tools:
        fn, fn_resolved, fn_detail = tools[family], "injected", None
    else:
        fn, fn_resolved, fn_detail = _load_tool(family, spec)
    if fn is None:
        return _row(family, spec, "tool-unavailable", detail=fn_detail or spec.get("unavailable_reason"),
                    directive_requirement_ids=rids_fam), []
    row, items = _run_workspace_family(family, spec, plan, ctx, budget_s, fn, fn_resolved, fn_detail)
    row.setdefault("directive_requirement_ids", rids_fam)
    return row, items


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
    # ADR-0084 (C.5): los adaptadores que llevan ledger por consulta (web) conocen la ronda y lo ya presente en la
    # corrida — en la COPIA local: el ctx del llamador no gana llaves por esto (existing_ids sólo si el llamador no la
    # pre-creó; _path_b_harness la pre-crea con su `present`)
    ctx["round"] = k
    ctx.setdefault("existing_ids", existing_ids if existing_ids is not None else set())

    def _ctx_list(key):
        lst = ctx.setdefault(key, [])
        if caller_ctx is not None and key not in caller_ctx:
            caller_ctx[key] = lst
        return lst

    seen = set(existing_ids or [])
    families = list(plan.get("families") or [])
    t0 = _monotonic()
    sources, items, duplicates = [], [], []
    deferred = []   # ADR-0084 (D.1): candidatos web-localizados — entran a items[] DESPUÉS de las familias nativas
    for idx, fam in enumerate(families):
        remaining = budget_s - (_monotonic() - t0)
        left = len(families) - idx
        spec = SEARCH_DISPATCH.get(fam) or {}
        # ADR-0082 (G.3): toda fila de la ronda declara los requisitos del consejo que nombraron a su familia
        # ([] = ninguno — la llave viaja siempre, también en skipped-*; la Traza dice "lo pidió el consejo · req-…")
        q_fam = (plan.get("queries") or {}).get(fam) or {}
        rids_fam = list(q_fam.get("directive_requirement_ids") or [])
        if remaining < MIN_SOURCE_BUDGET_S:
            row = _row(fam, spec, "skipped-budget",
                       detail=f"round budget {round(budget_s, 3)}s exhausted (remaining {max(0.0, round(remaining, 3))}s < {MIN_SOURCE_BUDGET_S}s)",
                       budget_s=0.0)
            row["round"] = k
            row["directive_requirement_ids"] = rids_fam
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
                row["directive_requirement_ids"] = rids_fam
                n_not_reexecuted += 1
                sources.append(row)
                if on_source:
                    on_source(row)
                continue
        if spec.get("adapter") == "web":
            # ADR-0084 (M.3): las listas que el localizador alimenta (ctx:dois → unpaywall_crossref, ctx:curies →
            # monarch) existen ANTES de correr y son las MISMAS que ve el llamador (append-only; jamás se reasignan)
            _ctx_list("dois")
            _ctx_list("curies")
        # ADR-0084: budget_s de la tabla salvo `budget_env` (WITT_WEB_BUDGET_S para web); las demás filas, como hoy
        fam_budget = min(family_budget_s(spec)[0] or remaining, remaining / left)
        row, found = run_source(fam, plan, ctx, fam_budget, tools=tools)
        row["round"] = k
        row["directive_requirement_ids"] = rids_fam
        row["over_budget"] = bool(row.get("elapsed_s") is not None and row["elapsed_s"] > fam_budget + 0.05)
        new_here = 0
        for it in found:
            eid = it.get("evidence_id")
            if "directive_requirement_ids" not in it:
                # adaptador que no atribuyó (p. ej. un fake inyectado): atribución por familia (_rids_for)
                it["directive_requirement_ids"] = _rids_for(q_fam, it.get("input"))
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
            if it.get("dedup_layer") == WEB_DEDUP_LAYER:
                # ADR-0084 (D.1): un candidato web-localizado NO gana identidad en la ronda (WEB_DEDUP_LAYER_RULE): se
                # difiere al final de items[] sin entrar a `seen`, y el pool (native-first) lo declara duplicado si una
                # familia nativa trajo el mismo id; contra lo YA PRESENTE en la corrida sí se descarta aquí
                if eid in (existing_ids or ()):
                    duplicates.append({"evidence_id": eid, "source_family": fam, "of": "existing"})
                    continue
                it["round"] = k
                deferred.append(it)
                new_here += 1
                continue
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
    items.extend(deferred)   # ADR-0084 (D.1): los web-localizados van DESPUÉS de los nativos de la ronda
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
    """Payload del evento stage.search.source — la fila sin `ledger` ni `calls` (viven en el bundle).
    ADR-0082 (G.3): + `directive_requirement_ids[]` (la Traza pinta "lo pidió el consejo · req-…"; [] = ninguno)."""
    out = {k: row.get(k) for k in ("round", "family", "status", "n_found", "n_new", "elapsed_s", "cache_hit",
                                   "query_sent", "budget_s", "gate", "label", "evidence_kind")}
    out["directive_requirement_ids"] = list(row.get("directive_requirement_ids") or [])
    for k in ("error", "detail", "over_budget", "n_calls", "n_calls_error", "n_calls_skipped_budget", "fn_resolved"):
        if k in row and row[k] not in (None, False, 0):
            out[k] = row[k]
    # ADR-0084 (C.7): la fila de la familia web suma sus contadores al evento SÓLO cuando existen en la fila (aditivo;
    # las otras 14 familias no los ganan); 0 es una MEDICIÓN y viaja; jamás `web_locator` (URLs) ni `calls`
    for k in ("provider", "n_queries", "n_results", "n_located", "n_materialized", "n_unresolved", "n_already_present",
              "cost_usd_projected", "quota_state"):
        if k in row:
            out[k] = row[k]
    return out

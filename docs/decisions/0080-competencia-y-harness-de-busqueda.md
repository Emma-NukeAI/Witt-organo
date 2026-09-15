# ADR-0080 — La compuerta de competencia y el harness de búsqueda: la decisión "¿basta la pasada 1 o se busca afuera?" la toma código, la Ruta B corre por familias de fuentes Layer 0 con presupuesto, y cada cita declara hasta qué peldaño de soporte llegó

- **Status:** Accepted — 2026-09-15. Origen: plan v3 del brief *Consejo de agentes* aprobado por Emmanuel el
  2026-09-14 (§4 "ninguna decisión del lazo la toma texto del modelo — la toma código o un humano", §6.2 "harness
  Layer 0", §13) y hallazgos de la auditoría externa Codex/Martín ya aprobados: **la Ruta B entregaba tres fuentes
  cableadas a mano y el disparador era el escalar del modelo**; **una cita "resuelta" y una cita "sostenida" se leían
  igual**; **una afirmación positiva sin citas pasaba el gate**; **un juez caído se excluía sin reintento**; **M8 no podía
  decir en qué etapa se gastó**. Obra en siete rebanadas (C1 compuerta+cableado · C2 harness · C3/C4/C5 tools Layer 0 ·
  C6 gate+panel · C7 integrador) en la rama `feat/adr-0080-competencia-harness`, apilada sobre
  `feat/adr-0079-investigacion` @ `5a10987`; todas las cifras de este ADR son MEDICIONES: las de las APIs, UNA GET real por
  API grabada como fixture el 2026-09-15; las de los gates, offline con la máscara de siempre. **Corrector final
  (2026-09-15, tres lentes: doctrina · corrección · contrato):** las decisiones marcadas *(corrector)* abajo cambian lo que las
  rebanadas entregaron — el escalar del modelo dejaba de gatear (`cg-2`; **REVERTIDO**, ver la viñeta siguiente), el kill-switch devuelve la Ruta B a ADR-0078 con
  `trigger 'confidence'`, ninguna ronda se re-ejecuta con los mismos insumos, `absence_kind` ausente es afirmación positiva, la
  calibración cuenta sólo `production`, `n_rounds 0` es cero medido, `pass` es etiqueta, el `evidence_id` de expresión ZFIN
  nace de las llaves de la fila, y el fixture de OpenAlex perdió dos correos. Estilo de cita: este ADR cita **ruta:función**,
  no ruta:línea — los números de línea del diff sin commit se mueven al primer rebase; el nombre de la función no.
- **Corrección del orquestador 2026-09-15: `cg-2` revertido a gating por default (`cg-3`).** El corrector había hecho
  INFORMATIVO por default al componente `conf1_ge_tau` (`CONF_COMPONENT_DEFAULT "0"`) alegando que "el escalar del modelo es
  self-report". Es incorrecto respecto a la doctrina vigente: **ADR-0051** eligió la confianza de la pasada 1 (`< τ`) como
  DECISOR de la Ruta B por encima del chequeo estructural (medido con `run_held_out --conf-threshold 0.5`; el estructural
  quedó documentado como engañable por cualquier chunk presente), y **ADR-0065** hizo del escalar ELICITADO por `CONF_TOOL`
  la medición autoritativa. Lo que el brief v3 §4/§7 prohíbe como self-report es que el modelo se declare competente en
  PROSA o audite su propio trabajo — no que un escalar medido y calibrable (ADR-0064/0075) participe en una conjunción que
  decide CÓDIGO. Consecuencia concreta del `cg-2`: una corrida con `conf1 0.15` y suficiencia estructural quedaba
  "competente" y saltaba la búsqueda externa — la regresión exacta del caso real **a361f566** (0.15 → Ruta B → 0.86,
  ADR-0059). Por tanto `conf1_ge_tau` GATEA por default (`cg-3`); `WITT_CG_CONF_COMPONENT=0` declarado lo vuelve
  informativo. Las menciones a "informativo por default" del escalar en este ADR quedan corregidas abajo; las de
  `calibration_coverage` (Context 5) siguen vigentes — esa sí es informativa hasta que exista historia.
- **Relates:** ADR-0043 (tres estados, jamás `null` ambiguo) · ADR-0049 (auditoría en el 100% de las corridas) ·
  ADR-0051 (`pass1 < τ` como disparador de la Ruta B — deja de decidir SOLO: es el componente `conf1_ge_tau` de la conjunción,
  GATEANTE por default (`cg-3`), y sobrevive como alias `trigger_legacy`) · ADR-0053 (el gate es ciego a la procedencia por diseño) · ADR-0061/0066 (el plan declarado:
  `route`, `niches`) · ADR-0062 (PubMed directo en Layer 0; el SDK de ToolUniverse medido y rechazado) · ADR-0064/0075
  (calificaciones append-only: la cobertura de calibración SE CUENTA, no se promedia) · ADR-0065 (elicitación dedicada
  de confianza: aquí gana su propio evento y su propio renglón de gasto) · ADR-0067 (revisión acotada: el mismo gate) ·
  ADR-0078 (higiene de Ruta A y B: `ledger_version 2`, queries por índice, `_env_int_tolerante`, dedup PMID/PMCID/DOI —
  los tres ledgers `*_searched` siguen byte-compatibles) · ADR-0079 (`origin` por corrida; `include_origins`; el mismo
  `_gate` con `parent_identifier_leak`) · ADR-0082 (consejo: directivas — hueco declarado) · ADR-0084/0085 (web /
  ToolUniverse — familias `tool-unavailable` declaradas).
- **Affects:** `rag_index/query_service/competence.py` (NUEVO: `evaluate`, `compact`, `env_config`, `plan_route`,
  `plan_niches`) · `runs.py` (`execute_run`: `stage.confidence.elicit{pass}`, `stage.deterministic_gate{pass:1}`
  adelantado, `stage.competence`, `_build_search_plan`, `_path_b_via_harness`, `_search_ledger_of`, `_support_states`,
  `_positive_claim_check`, `_gate(pass_no)`, `_usage_by_stage`, `FALLBACK_TRIGGERS`, `TRIGGER_LEGACY_CONFIDENCE`; contrato
  **1.9**) · `db.py` (`calibration_coverage`, `_frozen_niche_codes`) · `analysis/scripts/lib/search_harness.py` (NUEVO:
  `SEARCH_DISPATCH` de 15 familias, `build_search_plan`, `run_round`, `run_source`, `should_run_next_round`,
  `normalize_item`, `plan_event_payload`/`round_event_payload`/`source_event_payload`) · `answer_pipeline.py`
  (`path_b(search_plan=, on_stage=, existing_ids=)`, `_path_b_harness`, `_plan_with_queries`, `path_b_bundle` y
  `retrieve` con `search_plan=`, `path_b_event_payload` con resumen `search_ledger`) · `verify_output.py`
  (`positive_claim_requires_citations`, `evaluate_positive_claim_citations`, `count_valid_citations`,
  `support_state_for`, `support_summary`, `SUPPORT_LADDER`, `SUPPORT_LADDER_RULE`) · `composite_auditor.py`
  (`VERDICT_TOOL.citation_support` opcional, `parse_citation_support`, `citation_support_from_panel`,
  `resolve_judge_retries`, `audit(judge_retries=)` con `attempts[]`/`retries_judge`, `apply_to_bundle` copia
  `judge_retries`) · `.tooluniverse/tools/` (10 tools NUEVAS stdlib-puras: `alliance_orthologs.py`,
  `zfin_expression_tsv.py`, `ensembl_homology.py`, `uniprot_search.py`, `monarch_associations.py`, `reactome_search.py`,
  `string_partners.py`, `geo_gds.py`, `unpaywall_crossref.py`, `openalex_search.py`) · `rag_index/query_service/fixtures/`
  (11 fixtures reales `<api>_<caso>_20260915.json`; el de Unpaywall es SINTÉTICO y lo dice en el nombre) · gates nuevos
  `smoke_competence.py` · `smoke_search_harness.py` · `smoke_tools_a.py` · `smoke_tools_b.py` · `smoke_tools_c.py` ·
  `smoke_gate_citations.py` + `smoke_run_pipeline.py` (217 → 238) · `smoke_thread_context.py` y `smoke_run_recovery.py`
  (toques mínimos, ver *Consequences*) · `README.md` · `docker-compose.query.yml` · witt-webapp (tipar y pintar; ver
  *Consequences*). **Cero mutación de la DATA INAMOVIBLE, del registro congelado existente (ningún registro viejo se
  migra) y de `mcp_cache` desde los gates; cero gasto de modelo en la obra.**

## Context

1. **El disparador de la Ruta B era texto del modelo.** Desde ADR-0051, `pass1.stated_confidence < τ` decidía si la
   corrida buscaba afuera. El escalar es una medición útil (ADR-0065 lo hizo limpio), pero es JUICIO del modelo sobre sí
   mismo: una pasada inadmisible con confianza 0.95 no buscaba; una pasada admisible con plan fuera de alcance
   (`niches = []`) sí. La constitución (brief v3 §4) es explícita: ninguna decisión del lazo la toma texto del modelo.
   *(orquestador 2026-09-15)* La respuesta correcta NO es sacar el escalar de la decisión, sino que deje de decidir SOLO:
   el escalar de ADR-0065 es una medición elicitada por herramienta, no prosa; lo que §4/§7 vetan es la auto-declaración
   de competencia en texto y la auto-auditoría. `cg-3` lo conserva como componente gateante de una conjunción que decide
   código, junto a la admisibilidad, el plan y lo estructural.
2. **La Ruta B eran tres fuentes cableadas a mano.** Europe PMC, PubMed y ZFIN vivían dentro de `answer_pipeline.path_b`;
   añadir una fuente era reescribir la función. Las preguntas del sustrato piden ortólogos, expresión anatómica, homología,
   proteína, asociaciones fenotípicas, rutas, interacciones, datasets y acceso abierto — y el SDK de ToolUniverse ya se
   había medido y rechazado (ADR-0062: 173 paquetes, versión pineada que ni resuelve en 3.12). La única vía honesta era la
   misma que PubMed: tools Layer 0, stdlib puras, UNA GET, presupuesto de reloj, caché de lectura por día.
3. **Lo que cada API RESPONDIÓ de verdad (una GET real por API, 2026-09-15, `wt1a` / `ZFIN:ZDB-GENE-980526-558` /
   DOI `10.1242/dev.02071`; esquema observado, no supuesto):**
   - **Alliance orthologs** `GET /api/gene/ZFIN:ZDB-GENE-980526-558/orthologs?filter.stringency=stringent&limit=200` →
     `{total 4, returnedRecords 4, results[]}`; cada result trae `geneToGeneOrthologyGenerated{subjectGene, objectGene
     {primaryExternalId, taxon, geneSymbol}, isBestScore, isBestScoreReverse, confidence, strictFilter, moderateFilter,
     predictionMethodsMatched[]…}` — NO el `homologGene/best/methodCount` plano que el primer corte supuso (el parser se
     reescribió sobre lo observado y declara `schema_observed`). wt1a: Xenbase wt1 (9 métodos), HGNC:12796 WT1 (10),
     RGD:3974 Wt1 (9), MGI:98968 Wt1 (10); todos `best Yes`, `confidence high`. Sin cabeceras de rate-limit.
   - **Ensembl homology** `GET rest.ensembl.org/homology/symbol/danio_rerio/wt1a?target_species=homo_sapiens` → HTTP 200,
     `X-RateLimit-Limit 55000 / Period 3600 / Remaining 54999 / Reset 1151` (ventana horaria de 55k, además del 15 req/s
     documentado — ambas declaradas); `data[0].id ENSDARG00000031420`, 1 `ortholog_one2one` → `ENSG00000184937`
     (`ENSP00000415516`, `perc_id 61.11`). El no-match de Ensembl es un **HTTP 400** con `"No valid lookup found"` → se
     clasifica `no-match` por patrón declarado (NO medido en vivo: una GET adicional que aprueba Emmanuel).
   - **ZFIN `wildtype-expression_fish.txt`** → 243,119 líneas / 43,700,153 bytes en 27.4 s; **SIN cabecera**
     (`column_mode 'positional'`, detectado leyendo las 3 primeras líneas), 15 columnas TSV con orden congelado
     (`gene_id | gene_symbol | fish_name | super_structure_id | super_structure_name | sub_structure_id |
     sub_structure_name | start_stage | end_stage | assay | assay_mmo_id | publication_id | probe_id | antibody_id |
     fish_id`). Se descarga UNA vez al día a `mcp_cache/zfin_wildtype_expression_<YYYYMMDD>.txt` (`.part` + `os.replace`);
     wt1a: 158 filas, 92 casan `pronephr` en 0.5 s de escaneo local. El fixture son las 200 primeras líneas (corte declarado).
   - **UniProt** `search?query=gene_exact:wt1a+AND+organism_id:7955&size=5` → HTTP 200, 5 entradas (TODAS TrEMBL,
     `reviewed False`), el total vive SOLO en la cabecera `X-Total-Results: 6` → `truncated_by_size True` declarado; xref
     ZFIN copiado verbatim → `zfin_curie ZFIN:ZDB-GENE-980526-558`. 1.23 s.
   - **Monarch** `association?subject=ZFIN:…&category=biolink:GeneToPhenotypicFeatureAssociation&limit=20` → HTTP 200,
     `total 66`, 20 items; las publicaciones son 20/20 curies `ZFIN:ZDB-PUB-…` → `publications_resolution
     'unresolved-zfin-curie'` por item y por resultado (jamás convertidas). El tool exige CURIE (un símbolo → error
     `not-a-curie` sin llamada). 0.91 s.
   - **Reactome** `search/query?query=wt1a&species=Danio%20rerio&types=Pathway` → HTTP 200, `numberOfMatches 1`… y es una
     **Protein** (`ReferenceGeneProduct R-DRE-452420 → Q9PUT7`), cero Pathway: **`types=Pathway` NO se honra**. El parser
     clasifica cada entrada por su tipo, sólo `Pathway` produce ítems (`label 'inferred-by-orthology'`), lo demás se cuenta
     en `non_pathway_entries` con `types_filter_honored False` → resultado `no-match`. Una proteína nunca se presenta como ruta.
   - **STRING** `interaction_partners?identifiers=wt1a&species=7955&limit=10` → HTTP 200, 10 partners (tbx18 0.961 … tp53
     0.773), TODOS dominados por `tscore` (minería de texto) → `label 'predictive'` es medición, no teoría. 1 s entre llamadas.
   - **GEO** `esearch+esummary db=gds` → `n_found_total 48`, 10 registros; `X-Ratelimit-Limit 3 / Remaining 1`; identidad NCBI
     `missing` (sin `WITT_NCBI_EMAIL` en el shell de la obra — correcto y declarado).
   - **Crossref** `works/10.1242/dev.02071` → `title "Fgf signals from a novel signaling center determine axial patterning
     of the prospective neural retina"`, 2005. **Unpaywall NO se llamó** (sin `WITT_UNPAYWALL_EMAIL` no se inventa correo):
     fila `tool-unavailable` declarada; su fixture es SINTÉTICO y lo dice en el nombre.
   - **OpenAlex** `works?search=…&per-page=5` → `n_found_total 225`, 5 devueltos; **sin llave cobra créditos**:
     `X-RateLimit-Credits-Used 10 · X-RateLimit-Cost-USD 0.001 · X-RateLimit-Limit 1000 · Remaining 990` (≈100 llamadas/día
     gratis). Declarado en `credits_headers` y `data.cost_usd_reported`.
4. **Familias por default vs. sólo-por-directiva.** De las 15 familias, cinco corren en toda ronda sin directivas
   (`gate 'auto'`): las tres de hoy + `alliance_orthologs` (ortología curada, 1 GET, sin rate-limit) + `zfin_expression`
   (expresión anatómica nativa de pez cebra, caché diario). Las otras diez son `'directive-only'`: o son inferencia
   (`reactome` por ortología, `string` predictivo), o piden insumos que sólo otra fuente produce (`monarch` toma CURIE,
   `unpaywall_crossref` toma DOI), o cobran (`openalex`), o duplican literatura (`geo`, `uniprot`, `ensembl_homology`),
   o no existen aún (`web`, `tooluniverse`). Hasta que el consejo (ADR-0082) emita directivas, entran sólo si el operador
   las nombra en `WITT_SEARCH_DEFAULT_FAMILIES` — nombrarlas ES la directiva.
5. **Por qué la cobertura de calibración NO gatea todavía.** El componente `calibration_coverage` (corridas CLOSED con ≥1
   calificación cuyos `frozen.niches` intersecan los del plan, `≥ WITT_COMPETENCE_MIN_HISTORY = 10`) es la medida honesta
   de "¿este sistema ya demostró competencia en este nicho?". Hoy producción tiene 0 corridas cerradas calificadas por
   nicho: gatear con él sería negarlo todo. Se MIDE y viaja siempre (informativo, `gating false`); entra a la conjunción
   sólo con `WITT_CG_REQUIRE_CALIBRATION=1`, cuando exista historia.
6. **Por qué el consejo es componente `'not-available'`.** La conjunción del brief incluye "ningún `must` del consejo
   quedó sin cubrir". El consejo aterriza en ADR-0082; si la llave no existiera desde hoy, el contrato cambiaría de forma
   al llegar. Existe como `council_uncovered_must {value null, state 'not-available (ADR-0082)', gating false}`.
7. **Una cita "resuelta" no es una cita "sostenida".** El registro decía `citations[{n, kind, id}]` y el lector no podía
   distinguir un identificador que resuelve, uno cuyo pasaje llegó al sintetizador y uno que el panel juzgó sostenido. Son
   PELDAÑOS distintos y deben viajar separados. Y una afirmación positiva con cero citas válidas pasaba el gate: el
   predicado es formalizable, así que va al gate determinista, no al panel.
8. **Un juez caído se excluía a la primera; M8 no sabía en qué etapa se gastó.** El transporte reintentaba (429/5xx) pero
   una salida ilegible o una excepción del juez lo sacaban del panel; con 4 jueces, dos caídos vuelven `REVISE` por panel
   delgado. Y `token_usage.by_model` sumaba pero no repartía: el costo de la síntesis, la elicitación, el panel y la
   revisión eran indistinguibles.

## Decision

**(A) La compuerta de competencia** (`competence.py`, `module_version 'cg-3'`, `decided_by 'code'`). Tras pass1,
`competence.evaluate(conf1, admissible_pass1, plan, structural_fired, calibration_coverage, tau=FALLBACK_CONF_TAU)`
devuelve el BLOQUE completo: `{competent: bool|null, not_applicable, components{conf1_ge_tau{value, conf1, tau,
tau_source, gating, class 'model-judgment'}, admissible{value}, route_evidence_run{value, route}, niches_nonempty{value,
niches}, structural_not_fired{value}, calibration_coverage{n_closed_rated, min_required, sufficient, gating, class
'medicion', include_origins, include_origins_source}, council_uncovered_must{value null, state 'not-available (ADR-0082)',
gating false}}, conjunction[], reasons[], config{…, conf_component_gating}, self_report{stated_confidence, class
'model-judgment', note}, skipped_reason?, decision{trigger, decision_source, legacy_confidence_fired, trigger_decided_by}}`.
**Conjunción *(cg-3, orquestador 2026-09-15)* = `conf1 ≥ τ ∧ admissible ∧ route == 'evidence-run' ∧ niches ≠ [] ∧
¬structural_fired ∧ (calibration_coverage.sufficient SI WITT_CG_REQUIRE_CALIBRATION=1)`.** El componente `conf1_ge_tau`
GATEA POR DEFAULT (`CONF_COMPONENT_DEFAULT "1"`, `gating true`, primero en `conjunction`). Historia: `cg-1` gateaba siempre;
el corrector (`cg-2`) lo volvió informativo por default alegando que con los demás componentes en True el escalar "decidía
solo la ronda" — pero eso es exactamente lo que ADR-0051 decidió y midió (`pass1 < τ` por encima del estructural, que
cualquier chunk presente engaña), y ADR-0065 hizo del escalar elicitado por `CONF_TOOL` la medición autoritativa; la
objeción "self-report" del brief §7 aplica a la prosa y a la auto-auditoría, no a un escalar medido en una conjunción que
decide código. Con `cg-2`, `conf1 0.15` + suficiencia estructural = "competente" sin búsqueda: la regresión del caso
a361f566 (0.15 → Ruta B → 0.86, ADR-0059). Por eso `cg-3` REVIERTE el default. La nota de `self_report` dice la verdad
según `gating` (`'participa como componente conf1_ge_tau medido por CONF_TOOL (ADR-0065; gating true, WITT_CG_CONF_COMPONENT
default 1, cg-3); la conjunción la decide código'` | `'no participa en la decisión (conf1_ge_tau informativo,
WITT_CG_CONF_COMPONENT=0 declarado)'`) y el operador puede apagar el gateo SÓLO con `WITT_CG_CONF_COMPONENT=0`, declarado en
`config.conf_component_gating`. Componente sin insumo → `False`
con `reason` (`'conf1-absent'`, `'admissible-not-measured'`, `'no-plan'`, …), jamás un `True` vacío. `route
'store-consultation'` → `not_applicable true`, `competent null` (no hay compuerta). Kill-switch `WITT_COMPETENCE_GATE=0` →
`competent null` + `skipped_reason`; los componentes se calculan y viajan igual; la regla legada `pass1 < τ` decide (ver
(B)). **Sin plan (`POST /runs` directo): `route`/`niches` ausentes → componentes `False` con reason `'no-plan'` → no
competente → ronda + pass2 SIEMPRE**, aunque la confianza sea alta. `calibration_coverage` la mide
`db.calibration_coverage(niche_codes, min_required, include_origins=…)`: `{n: int|null, sufficient, n_closed_rated_total,
reason 'no-niches'?, include_origins, class 'medicion'}`; sin nichos `n null` (no hay contra qué medir — jamás un 0).
*(corrector)* `runs.execute_run` pasa `include_origins` desde `WITT_CG_CALIBRATION_ORIGINS` (default `['production']`,
fuente en `include_origins_source`): corridas `smoke`/`simulation`/`fixture` cerradas y calificadas jamás cuentan como
historia de competencia (ADR-0079); `all` = sin filtro, declarado.

**(B) El cableado en `runs.execute_run`.** pass1 → `stage.synthesize.pass1` (gana `usage {in, out, model}`) →
`stage.confidence.elicit{pass 'pass1', stated_confidence, confidence_source, elicitation_state, usage}` (la elicitación de
ADR-0065 gana su evento) → `stage.deterministic_gate{pass 'pass1'}` **ADELANTADO** (la admisibilidad de pass1 es
componente) → `db.calibration_coverage` → `competence.evaluate` → `stage.competence` (el bloque íntegro + `decision`).
*(corrector)* `pass` es ETIQUETA en todos lados — `'pass1' | 'pass2' | 'revision'`, el vocabulario de `usage_raw.passes`
— nunca `1 | 2 | 'revision'` mezclados en una llave. Competente → pass1 es la candidata, `checks = checks1`,
`fallback.trigger null`, ninguna ronda (`search_ledger.state 'not-requested…'`, **`n_rounds 0`**: cero MEDIDO, ADR-0043;
`null` se reserva a "el harness no midió"). No competente → `_build_search_plan` (REAL, `families=None`: el harness
resuelve la env) → `path_b_bundle(search_plan=, on_stage=, existing_ids=doc_ids de Ruta A)` → `stage.path_b {trigger
'competence', trigger_legacy, trigger_decided_by, harness_used, search_ledger}` → pass2 → `elicit{pass2}` → `gate{pass2}`.
Lo estructural (`assess_sufficiency`) manda como hoy (`'structural'`). **Kill-switch / ruta no aplicable *(corrector)*:
con `competent null` decide la regla legada `pass1 < τ` y el registro lo dice con SU nombre — `fallback.trigger
'confidence'` (literal VÁLIDO sólo en este caso; `'competence'` se reserva a la decisión por código), `trigger_decided_by
'model-confidence (legacy rule pass1 < tau; competence.competent is null)'`, `triggered_by` con el literal de ADR-0051 — y la
Ruta B es la de ADR-0078 BYTE A BYTE: `path_b_bundle` SIN plan, sin harness, sin `stage.search.round/source`,
`stage.search.plan {state 'kill-switch WITT_COMPETENCE_GATE=0' | 'not-applicable (…)'}`, `search_ledger.state 'legacy-path-b
(kill-switch WITT_COMPETENCE_GATE=0)'`, `n_rounds null`.** Antes el kill-switch apagaba la decisión pero el camino de
búsqueda seguía siendo el harness y el trigger decía `'competence'`: no había env que devolviera la Ruta B a ADR-0078.
`WITT_SEARCH_HARNESS=0` *(corrector)* separa responsabilidades: la compuerta sigue decidiendo, la Ruta B corre por
`path_b_bundle` sin plan (`state 'legacy-path-b (kill-switch WITT_SEARCH_HARNESS=0)'`) — el freno del operador si una tool
Layer 0 se comporta mal en prod. `fallback.trigger ∈ {structural, competence, confidence, null}` (`runs.FALLBACK_TRIGGERS`);
`fb_meta.{trigger_legacy ('confidence' cuando `pass1 < τ` habría disparado | 'structural' | null), trigger_vocabulary,
trigger_decided_by ∈ 'code (competence-gate)' | 'structural (assess_sufficiency, code)' | 'model-confidence (legacy…)',
tau_source, search_harness_enabled(+_source), competence {competent, not_applicable, reasons, decision_source,
skipped_reason, decided_by, module_version}}` explican quién decidió. `WITT_FALLBACK_CONF_TAU` se lee con el lector
tolerante de `competence` (una env presente y vacía ya no tumba el import). Los eventos `stage.search.*` llevan `agent
'search_harness'` tanto cuando los emite el harness en vivo como cuando `runs` emite el plan-sobre (`plan_event_payload`
lleva `state 'built'`: la Traza tipa UNA forma, nunca infiere de la ausencia de una llave). La revisión (ADR-0067) usa el
MISMO `_gate` con `pass_no 'revision'` y conserva `pass1_admissible` y `competence_gate`.

**(C) El harness** (`lib/search_harness.py`, `harness_version 'sh-1'`, `plan_version '1'`). UNA tabla `SEARCH_DISPATCH`
de 15 familias `{tool_module, fn, adapter?, inputs ∈ literature-query|symbols|zfin-curies|free-query|dois, budget_s,
host, key_env, evidence_kind, gate ∈ auto|directive-only, label_provenance ∈ predictive|inferred-by-orthology|null,
list_keys?, source_rows?, extra_kwargs?, unavailable_reason?}`. `build_search_plan(question, entities, pass1_query_en,
directives=None, families=None)` — por CÓDIGO: familias (`caller` > `directives` > `WITT_SEARCH_DEFAULT_FAMILIES`; las
`directive-only` fuera salvo nombradas; desconocidas → `families_excluded 'unknown-family'`), queries por familia (las
de literatura/ZFIN vía `search_queries.build_all`; `free-query` = `pass1_query_en` o `símbolos + anatomía + zebrafish`
declarado; `dois`/`zfin-curies` se resuelven EN RONDA desde los ítems ya admitidos), `rounds_cap`, `round_budget_s` (cada
valor con su fuente), `directives []` + `directives_state 'empty-until-ADR-0082'`. `run_round(plan, k, budget_s,
on_source, existing_ids, ctx)` — presupuesto de RONDA: antes de cada familia `budget = min(budget_s de la familia,
restante / familias_restantes)`; `restante < 0.5 s` → `skipped-budget` sin tocar la red; dentro de la familia la PRIMERA
llamada siempre corre, las demás sólo con ≥ 0.5 s; `timeout=`/`budget_s=` viajan al tool cuando su firma los acepta
(`timeout_s_scope` declarado); nada corre en hilo (una fuente lenta consume la ronda y las siguientes quedan
`skipped-budget`, `over_budget` declarado en la lenta — diseño síncrono, §6 no-hang). Cada fuente deja UNA fila `{round,
family, status ∈ success|no-match|error|skipped-budget|skipped-cap|tool-unavailable|not-requested, n_found, n_new
(ENTEROS sólo en success|no-match), elapsed_s, cache_hit, query_sent, budget_s, gate, label, evidence_kind, host,
over_budget, error?, detail?, calls[], ledger (sólo europepmc/pubmed/zfin: el de hoy, íntegro)}`; una familia cuyas
llamadas dijeron TODAS `tool-unavailable` | `skipped-budget` hereda ese literal (C7). Ítems normalizados `{evidence_id,
kind, source_family, title|statement, text|abstract|null, url, identifier_provenance, label, raw_ref, gap_flags?}` —
jamás un identificador de memoria: el del tool con su procedencia, o uno DERIVADO `<family>:sha256:<16>` +
`gap_flag 'no-external-identifier'`. Dedup contra `existing_ids` y dentro de la ronda (`duplicates[]`); los candidatos de
literatura entran al pool/dedup/selección de ADR-0078 (PubMed sigue declarando `duplicates_of_europepmc`, alimentado
SÓLO con los candidatos que EPMC trajo — un PMID propio de PubMed no es duplicado de EPMC; un mismo PMID se declara UNA
vez). **Nada se re-ejecuta *(corrector)*: otra ronda SOLO si la anterior no ADMITIÓ nada (`n_admitted == 0`: lo que entró al
pool o a los ítems — un candidato rechazado por `_pool_add` por PMID/PMCID/DOI no cuenta como nuevo), `k <
WITT_SEARCH_ROUNDS_CAP` Y alguna familia tiene INSUMOS nuevos (`search_harness.families_with_new_inputs`: una curie ZFIN o
un DOI resueltos en la ronda — cosechados aunque el ítem sea duplicado —, o una familia que quedó `skipped-budget`); en esa
ronda las familias cuyos insumos son idénticos a los que ya consumieron (`rows[].inputs_used`) quedan `skipped-cap` con detail
`'same inputs as round k (not re-executed)'` sin tocar la red.** `should_run_next_round(k, n_new, cap, inputs_changed)`;
`stop_reason ∈ found-new|rounds-cap|no-families|no-new-inputs`; la ronda declara `n_admitted`, `families_with_new_inputs`,
`n_not_reexecuted`, `round_over_budget`, `elapsed_over_budget_s`. Con las cinco familias default los insumos sólo cambian
cuando se admite algo, así que hoy una corrida no competente que no encontró nada hace UNA ronda (antes hacía dos
idénticas: 5 GETs repetidos para producir duplicados o no-match). Las tres fuentes de hoy NO se reescriben: adaptadores
que llaman a `answer_pipeline._search_europepmc/_search_pubmed/_search_zfin` y conservan su ledger; *(corrector)* el
presupuesto de la familia ACOTA sus llamadas — `timeout=min(default del módulo, presupuesto)` viaja a
`fetch_paper.search_europepmc_ledger` y `pubmed_literature.query_pubmed` (ambas ganan `timeout=` opcional, declarado en
`timeout_s`/`timeout_s_source`), `timeout_s_scope 'per-call'` en la fila; antes eran 30 s fijos + `Retry-After` y una
familia legada podía consumir la ronda entera. `zfin_expression` declara `pass_budget False`: su `budget_s` es el de la
DESCARGA diaria y lo gobierna `WITT_ZFIN_EXPR_DOWNLOAD_BUDGET_S` — pisarlo con el presupuesto de familia dejaba la fuente en
`error` todo el día. Un `success` cuya lista el harness no supo leer es `error 'shape-mismatch…'` con `status_raw`, jamás
`n_found 0`; una familia cuyas llamadas dijeron TODAS `not-requested` lo hereda; `error` jamás viaja con `error null`.
`answer_pipeline.path_b(search_plan=)` desvía a `_path_b_harness`; sin plan el cuerpo es el de ADR-0078 sin cambios.
Eventos por `on_stage`: `stage.search.plan` (UNA vez: del harness cuando corre en vivo; de `runs` con `state` cuando no),
`stage.search.source` (por familia), `stage.search.round` (por ronda).

**(D) Diez tools Layer 0** (stdlib: `urllib/json/re/csv`; mismo esqueleto que `zfin_zebrafish.py`: costura de red única
`_get`, `query_*() -> {status, query_sent, elapsed_s, cache_hit, data|error, …}`, `@register_tool` no-op si el paquete no
está, `timeout <= 0` → `skipped-budget` sin red, todo corte declarado, errores JAMÁS cacheados): `alliance_orthologs.
query_orthologs(symbol|curie)` (símbolo→curie vía el mismo `search_autocomplete` de `zfin_zebrafish`; `evidence_id
'alliance-ortholog:<curie>-><id>'`) · `zfin_expression_tsv.query_expression(symbol, anatomy_terms=, budget_s=)`
(descarga diaria bajo un lock de proceso, `.part` único por hilo y validada — `n_lines > 0`, salto de línea final —
antes de publicarse: dos workers que arrancaban la ronda juntos corrompían el mismo `.part` *(corrector)*; `detect_columns`
con `column_mode 'header'|'positional'` declarado; el TSV se parte SÓLO por TAB — sin quoting csv que una comilla
descuadre — y una línea con otro número de columnas se cuenta en `n_rows_malformed`, no se mapea a roles equivocados;
`evidence_id` *(corrector)* nace de las LLAVES EXTERNAS de la fila —
`'zfin-expression:<ZDB-GENE>:<ZFA>:<ZDB-PUB>:<MMO>[:<sub ZFA>][:<ZDB-FISH>][:<stage>]'`, `identifier_provenance
'zfin-tsv-row-keys'`, regla en `data.evidence_id_rule`, `resolves_to` por fila — estable entre descargas, a diferencia del
número de línea de un archivo que ZFIN regenera; `raw_ref {file_date, line_no, cache_path}` sigue LOCALIZANDO la línea)
· `alliance_orthologs`: un símbolo sin gen resuelto es `no-match` con `no_match_reason 'symbol-unresolved'` (la API
respondió), no `error`; `alliance_orthologs` y `zfin_zebrafish` pegan a `www.alliancegenome.org` por `net_throttle`
(0.2 s, `throttle` declarado) *(corrector)* · `ensembl_homology.query_homology(symbol)`
(respeta `X-RateLimit-*`; UN reintento en 429 con `Retry-After`) · `uniprot_search.query_uniprot(symbol, size=5)`
(`n_total` de la cabecera o `'not-available'`) · `monarch_associations.query_monarch(curie, limit=20)`
(`publications_resolution 'unresolved-zfin-curie'`) · `reactome_search.query_reactome(symbol)` (`label
'inferred-by-orthology'`; sólo `Pathway` es ítem) · `string_partners.query_string(symbol, limit=10)` (`label
'predictive'`; 1 s entre llamadas vía `net_throttle`) · `geo_gds.query_gds(query)` (esearch+esummary `db=gds`; identidad y
throttle COMPARTIDOS con `pubmed_literature`) · `unpaywall_crossref.query_doi(doi)` (UNA fila por fuente
`data.{crossref, unpaywall}`; Unpaywall sin `WITT_UNPAYWALL_EMAIL` → `tool-unavailable`, cero llamadas, cero correo
inventado; el correo jamás toca caché ni salida) · `openalex_search.query_openalex(query, per_page=5)` (`api_key`
opcional; créditos declarados desde las cabeceras; *(corrector)* la caché del día descarta
`authorships[].raw_affiliation_strings` / `affiliations[].raw_affiliation_string` y redacta cualquier correo restante,
ambos CONTADOS en el sobre `cut` — el fixture real del 2026-09-15 traía dos direcciones de autores y perdió esos campos con
el recorte declarado en `_fixture.cut`; `smoke_tools_c` comprueba que `fixtures/*.json` tiene CERO correos). Cada tool tiene
su fixture REAL y su smoke offline con `_get` monkeypatcheada (+ un error de red + un no-match).

**(E) Gate y panel.** `verify_output.positive_claim_requires_citations(answer, citations_valid, identifier_report=None)` →
predicado para `extra_predicates`: INADMISIBLE si `absence_kind == 'not-applicable'` **o AUSENTE** *(corrector: lectura
conservadora por código — la omisión del campo era la vía de escape más barata para pasar el gate sin citar;
`absence_kind_state 'absent -> treated-as-positive (ADR-0080 conservative default)'`)* y `n_citations_valid == 0`; una
declinación puede no citar **salvo que su texto nombre identificadores RESUELTOS** (`verify_identifiers`, el MISMO informe
que `_gate` ya midió viaja al predicado; `resolved_identifiers` + `_state 'checked'|'not-provided'`) — afirmar cosas
concretas bajo la etiqueta de ausencia dispara igual (`reason 'declination with resolved identifiers […] and 0
citations'`); la evaluación completa (`{ok, positive_claim, absence_kind, absence_kind_state, n_citations_valid,
citations_state, resolved_identifiers(+_state), reason, rule, decided_by 'code'}`) cuelga del predicado y se congela tal cual. `verify_output.support_state_for(citations, bundle, grounding=None)` → por
cita `{n, id, resolved (el id nombra un ítem del bundle por llaves DETERMINISTAS: id, PMID±prefijo, DOI normalizado,
pmid/pmcid/doi del search_rec), passage_delivered (abstract | text_excerpt | statement | texto de Ruta A | fenotipos ZFIN),
pertinent 'not-available (ADR-0082)', supported ∈ supported|unsupported|not-assessable|not-evaluated (la palabra del
juez), support_state = el peldaño MÁS ALTO alcanzado ∈ unresolved|resolved|passage_delivered|supported|unsupported}` —
la escalera NO salta peldaños (un veredicto sólo eleva una cita con pasaje; `not-assessable` deja el determinista) y los
campos NUNCA se funden. `composite_auditor.VERDICT_TOOL` gana `citation_support [{n, verdict}]` OPCIONAL: sólo la charge de
`evidence-grounding` lo pide; las otras lentes lo ignoran; `parse_citation_support` descarta y cuenta lo fuera de
vocabulario. `audit(judge_retries=None)`: hasta `1 + WITT_JUDGE_RETRIES` intentos por juez caído/ilegible; la fila lleva
`retries_judge` + `attempts [{attempt, status, error?, usage?}]`; el gasto MEDIDO de cada intento se conserva y se suma
(un intento ilegible cobró); un juez agotado queda `errored` con el ÚLTIMO error, jamás fabricado, y su `usage` entra a
`audit.usage` **y** *(corrector)* a `token_usage.by_model` (bajo su reviewer), `by_stage.panel` y `usage_raw.panel_total` —
antes M8 sub-contaba exactamente ese gasto y `by_stage_sum_matches_by_model` lo escondía; `audit.judge_retries
{value, source}` declarado y copiado al registro (C7). `runs.panel_caller` emite `stage.audit.judge {attempt,
retries_judge}` por INTENTO (el latido sigue acotado a un juez).

**(F) Gasto por etapa.** `token_usage.by_stage {plan, synthesize_pass1, elicit_pass1, search, synthesize_pass2,
elicit_pass2, panel, revision, embed, _sum}` desde el `usage` que cada llamada devuelve: la síntesis es la resta y la
elicitación la parte cuando el sintetizador reporta `usage_elicitation` (el wrapper real lo hace: `elicit_pass1 {30, 3,
'measured'}` con la API falsa); un stub que no separa deja `elicit_* {in null, out null, state 'not-separable…'}` — nunca
un 0 inventado; `plan` distingue TRES estados *(corrector)*: medido, `{in null, out null, state 'plan-without-usage (planner
reported no usage)'}` con plan declarado, y `{0, 0, 'no-plan'}`; `search` es 0 con nota (Layer 0 no gasta modelo); `embed`
aparte en tokens de embedding.
`by_stage_sum_matches_by_model` (`_sum == by_model total`) se comprueba y viaja como bool.

**(G) Congelado — contrato 1.9 (aditivo).** `competence` (el bloque de (A) + `decision`) · `search_ledger {plan (sin
query_builder), plan_state ∈ built|not-requested|harness-unavailable|error, rounds[] (sin ítems), n_rounds int|null, cap,
round_budget_s, families_default, config_source{families, cap, round_budget_s}, second_round_rule, state ∈ 'harness' |
'not-requested (…)' | 'legacy-path-b (…)' | 'harness-without-ledger (…)', harness_version?, stop_reason?, n_new_total?,
n_items?}` (el `bundle.path_b` íntegro sigue en `bundle_json`) · `citations[]` += `resolved, resolved_to,
passage_delivered, pertinent, supported, support_state` (aditivo por cita) + `citations_support_summary {n, by_state (los
5 peldaños SIEMPRE: enteros cuando `checked`, null cuando el helper no está — la forma no cambia), ladder, pertinent, state ∈
checked|tool-unavailable|error, grounding_rows, ladder_rule}` · `deterministic_checks` += `pass ('pass1'|'pass2'|'revision'),
pass1_admissible, positive_claim_requires_citations (+_state, +_evaluation), competence_gate (competence.compact)` ·
`fallback.trigger ∈ {structural, competence, confidence, null}` (`'confidence'` SÓLO con `competence.competent null`) +
`fb_meta.{trigger_legacy, trigger_vocabulary, trigger_decided_by, tau_source, search_harness_enabled(+_source), competence}` ·
`token_usage.by_stage` + `by_stage_sum_matches_by_model` · `epistemic_summary += competent (bool|null), n_search_rounds
(int|null; 0 = no se buscó, null = el harness no midió)` · `search_ledger` += `config_reader, stop_reasons_vocabulary,
n_admitted_total`; `rounds[]` += `n_admitted, inputs_changed, families_with_new_inputs, n_not_reexecuted, round_over_budget,
elapsed_over_budget_s`; `rounds[].sources[]` += `inputs_used`. Eventos nuevos: `stage.confidence.elicit{pass}`,
`stage.competence`, `stage.search.plan`, `stage.search.round`, `stage.search.source`; ampliados: `stage.deterministic_gate
{pass}`, `stage.synthesize.pass1/pass2 {usage}`, `stage.path_b {trigger 'competence', trigger_legacy, harness_used,
search_ledger}`, `stage.audit.judge {attempt, retries_judge}`.

**(H) Integración (C7).** Costuras mínimas, cada una documentada en el archivo: `search_harness.SEARCH_DISPATCH`
apunta a las llaves REALES de C5 (`geo`/`openalex` → `data.records`; `unpaywall_crossref` → `source_rows
('crossref','unpaywall')`: una fila `success` por fuente = un elemento `evidence_id '<fuente>:<doi>'`, dos fuentes = dos
ids) y la agregación por familia hereda `tool-unavailable`/`skipped-budget` cuando TODAS las llamadas lo dijeron (el
vocabulario que las tools de C3/C5 emiten en su raíz); `composite_auditor.apply_to_bundle` copia `judge_retries` al
registro. `smoke_run_pipeline.py` actualizado al contrato 1.9 (las corridas sin plan ya no son "sin fallback": son
`'competence'` con `trigger_legacy null`; las citas se comparan por su forma BASE) y +22 checks ADR-0080 que además MIDEN
que la sección no toca la red (`urllib.request.urlopen` bloqueado y contado: 0) ni `mcp_cache` (snapshot antes/después).
`smoke_thread_context.py` declara el kill-switch en su cabecera (prueba la investigación, no la compuerta; sus corridas
nacen sin plan) y `smoke_run_recovery.py` compara la forma base de las citas.

## Consequences

- **Contrato: `render_contract_version` sube a "1.9"** — campos aditivos (lista en (G)); `citations` conserva su forma
  base (`n, kind, id, note`) y gana llaves; **`fallback.trigger` cambia de dominio**: `'confidence'` aparece SÓLO bajo
  kill-switch / ruta no aplicable (`competence.competent null`), `'competence'` es nuevo y `fb_meta.trigger_decided_by`
  nombra al decisor. **Ruptura REAL en la webapp (medida en `Hoja.tsx:2069`):** la Hoja pinta cualquier `trigger ≠
  'structural'` como "el decisor por confianza disparó la Ruta B" — con `'competence'` AFIRMA lo contrario de lo que este
  ADR instaura (decidió código); `types.ts:637/734` no admiten `'competence'`. La rama para `'competence'` debe decir "la
  compuerta de competencia (código) disparó la Ruta B" con `trigger_legacy` como glosa, `'confidence'` sigue siendo el
  decisor por confianza (ahora sólo bajo kill-switch) y todo otro literal cae a `LiteralDesconocido`.
- **La webapp debe tipar y pintar** (`witt-webapp/src/api/types.ts`, todo `?`): (1) `FallbackTrigger` pasa a
  `'structural' | 'competence' | 'confidence' | null` y `fb_meta.{trigger_legacy, trigger_vocabulary, trigger_decided_by,
  tau_source, search_harness_enabled, competence}`; el gate de paridad front↔back debe fallar si un frozen trae un literal
  fuera de ese union; (2) `competence` — la Traza pinta `stage.competence` como UNA fila con los componentes en verde/rojo
  y sus `reason`, `conf1_ge_tau` con su `gating` (gris cuando informativo), el `self_report` aparte con su nota literal,
  el kill-switch como `competent null` + `skipped_reason` (jamás un check verde por `null`); (3) `search_ledger` — plan
  (familias con su `gate`, `families_excluded` con razón),
  rondas y por fuente `status` con los 7 literales, `n_found`/`n_new` (null = no midió, distinto de 0), `cache_hit`,
  `over_budget`, `label` (`predictive` / `inferred-by-orthology` como cintillo: NO es evidencia nativa de pez cebra),
  `stop_reason` (incluido `'no-new-inputs'`), `skipped-cap` con detail "not re-executed" y `n_rounds 0` como "no se buscó";
  los eventos `stage.search.plan/round/source` en la Traza viva (`agent 'search_harness'`, `state` siempre presente); (4)
  `citations[].support_state` como
  escalera de 5 peldaños por cita, con `resolved`/`passage_delivered`/`supported` separados y `pertinent 'not-available
  (ADR-0082)'` como gris declarado; `citations_support_summary.by_state` como conteo; (5) `deterministic_checks.{pass,
  pass1_admissible, positive_claim_requires_citations (+_state, +_evaluation), competence_gate}`; (6)
  `token_usage.by_stage` como desglose de M8 (con `elicit_* null + state` visible como "no separable", no como 0) y
  `by_stage_sum_matches_by_model`, `plan.state 'plan-without-usage…'`; (7) `epistemic_summary.{competent, n_search_rounds}`
  en la fila del Banco (0 ≠ null); (8) `stage.audit.judge {attempt, retries_judge}` y `audit.panel[].{retries_judge,
  attempts, citation_support}`, `audit.judge_retries`; (9) `path_b.papers[].{kind, source_family, label,
  identifier_provenance, url, gap_flags, zfin_curie}`; (10) `deterministic_checks.pass` es string (`'pass1'|'pass2'|'revision'`).
- **`record_pdf.py` (obra C8, dueño: backend):** *(corrector)* hoy imprime `fallback.trigger` + `trigger_decided_by` + el
  veredicto de la compuerta (`competence.competent`, `decision_source`), `search_ledger {state, n_rounds, cap, stop_reason}`
  y el `support_state` por cita (ausente = `NO INSTRUMENTADO (contrato < 1.9)`); quedan pendientes de pintar
  `competence.components` con sus `reason`, las filas por fuente del `search_ledger`, `citations_support_summary` y
  `token_usage.by_stage`. Deuda declarada aquí, no en la lista de gates en vivo.
- **`witt-webapp/tools/gen_fixtures.py` (dueño: webapp):** corre contra este backend (importa, ejecuta el pipeline real,
  produce 10 registros 1.9 en un directorio temporal) y se detiene en su PROPIA aserción del caso 7 (el sintético
  "contrato pre-1.1"): exige que `deterministic_checks` tenga EXACTAMENTE `{admissible, reasons, identifier_report}` y desde
  1.9 el registro trae también `pass, pass1_admissible, positive_claim_requires_citations(+_state,+_evaluation),
  competence_gate`. Es una línea de la webapp (tomar la forma base como subconjunto) — pre-existente al corrector.
- **Producción (redeploy).** Ninguna migración de BD. `mcp_cache` (o `WITT_MCP_CACHE_DIR`) necesita ESCRITURA en el
  contenedor: la primera llamada del día a `zfin_expression` descarga 43.7 MB (27 s medidos) dentro del presupuesto de la
  ronda (`budget_s 60` de la familia, 120 s la ronda); sin escritura la tool devuelve `error` declarado y la ronda sigue.
  `WITT_NCBI_EMAIL`/`WITT_UNPAYWALL_EMAIL`/`OPENALEX_API_KEY` siguen sin fijarse hasta que Emmanuel lo decida: cada corrida lo
  declarará (`ncbi_identity 'missing'`, fila Unpaywall `tool-unavailable`, OpenAlex cobrando créditos SI se activa por env).
- **Históricos NO se recalculan.** Ningún registro anterior gana `competence`/`search_ledger`/`support_state`; el PDF y la
  webapp los leen como ausentes (`?`).
- **Costo de modelo.** Toda corrida `POST /runs` SIN plan ahora gasta ronda + pass2 aunque su confianza sea alta (antes,
  sólo con `pass1 < τ`). En producción la webapp encola con plan (M3); `evaluation/run_held_out_v2.py` y `gen_fixtures`
  encolan directo — ver decisiones abiertas. Un pass2 con más familias recibe más evidencia (ítems de ortología/expresión
  además de la literatura): el prompt crece — medir EN VIVO (`token_usage.by_stage.synthesize_pass2` contra la mediana).
  Reintentos: el de TRANSPORTE (`_anthropic_tool_call`, 429/5xx, `retries=1`, 120 s) se apila con el de JUEZ
  (`WITT_JUDGE_RETRIES=1`): peor caso por juez `2×2×120 s = 480 s`, con latido por intento; `WITT_REAP_STALE_S=900` sigue
  cubriendo.
- **Fronteras declaradas, no resueltas:** (a) el harness es SÍNCRONO: una fuente que se cuelga más allá del timeout de su
  socket sigue siendo responsabilidad de la tool (todas pasan `timeout` a urllib); (b) `monarch` sólo corre si `zfin` o
  `alliance_orthologs` resolvieron una curie ZFIN EN LA MISMA ronda (`not-requested` declarado si no; un resolver
  símbolo→curie propio es UNA GET más — decisión de ADR-0082); (c) `unpaywall_crossref` consume los DOI de los ítems ya
  admitidos en la ronda (es un RESOLVEDOR, no un buscador) — el orden de las familias en el plan importa y está declarado
  (con `monarch` ANTES de `alliance_orthologs` la curie llega en la ronda siguiente: es el único caso en que hoy ocurre
  una ronda 2, y sólo para `monarch`); (d) Reactome `types=Pathway` no se honra: la capa de rutas queda vacía por símbolo
  hasta decidir un tool de 2 GETs (`/data/pathways/low/entity/{dbId}`); (e) las curies `ZFIN:ZDB-PUB-*` de Monarch quedan
  `unresolved` (un resolver ZFIN-pub→PMID sería otra tool Layer 0); (f) *(resuelta por el corrector)* `stage.search.plan`
  tiene UNA forma y UN agente: `state` viaja siempre (`'built'` en vivo; `'harness-unavailable' | 'error: …' |
  'kill-switch …' | 'not-applicable …'` desde `runs`), `agent 'search_harness'` en ambos casos; (g) *(resuelta por el
  corrector)* `db.calibration_coverage` se llama con `include_origins=['production']` por default
  (`WITT_CG_CALIBRATION_ORIGINS`); (h) el tope de ronda es blando para una descarga en curso de `zfin_expression`: el
  socket respeta `timeout`, el presupuesto de descarga es el suyo (180 s) y un `.part` abortado no se reanuda (`Range:`
  queda para otra rebanada) — declarado.
- **Decisiones abiertas para Emmanuel:** (1) ¿toda corrida sin plan debe gastar ronda + pass2 (así está, por el literal del
  brief) o `run_held_out_v2`/`gen_fixtures` fijan un plan mínimo? (2) *(resuelta por el corrector con el default seguro)*
  la compuerta cuenta sólo `production`; `WITT_CG_CALIBRATION_ORIGINS` permite ampliarlo en dev. (3) *(resuelta por el
  corrector)* `absence_kind` AUSENTE ⇒ afirmación positiva, y una declinación con identificadores resueltos sin citas
  también dispara. (3b) *(resuelta por el orquestador 2026-09-15, `cg-3`)* el escalar elicitado GATEA por default en todos
  los nichos (ADR-0051/0065; caso a361f566); `WITT_CG_CONF_COMPONENT=0` queda como apagado explícito del operador, y la
  calibración (ADR-0064/0075) podrá ajustar τ, no si el escalar participa. (4) ¿Reactome con
  2 GETs o aceptar `no-match` como estado medido? (5) ¿tope de llamadas/día por familia para OpenAlex sin llave (cobra) o
  basta declararlo en el ledger? (6)
  `WITT_UNPAYWALL_EMAIL`: fijarlo UNA vez y grabar el fixture real (`python .tooluniverse/tools/unpaywall_crossref.py
  10.1242/dev.02071`, copiar `mcp_cache/raw_unpaywall_…json` a `fixtures/` y ajustar `smoke_tools_c.py`). (7) OpenAlex
  `api_key`: la spec dice header, la documentación dice query param — medir UNA vez cuando exista la llave.

### Variables de entorno (defaults declarados en código; el valor efectivo y su fuente viajan en el registro)

| Variable | Default | Lector | Efecto |
|---|---|---|---|
| `WITT_COMPETENCE_GATE` | `1` | `competence.env_config` (en cada `evaluate`) | `0` = kill-switch: `competent null` + `skipped_reason`; la regla legada `pass1 < τ` decide la ruta, `fallback.trigger 'confidence'`, Ruta B por `path_b_bundle` SIN plan (ADR-0078 byte a byte) |
| `WITT_CG_REQUIRE_CALIBRATION` | `0` | idem | `1` = `calibration_coverage.sufficient` entra a la conjunción (`components.calibration_coverage.gating`) |
| `WITT_CG_CONF_COMPONENT` *(cg-3, orquestador)* | `1` | idem | `1` (default) = `conf1_ge_tau` (confianza ELICITADA por `CONF_TOOL`, ADR-0065) gatea en la conjunción como decidió ADR-0051; `0` declarado = se mide y viaja informativo (`gating false`, fuera de `conjunction`; la nota de `self_report` lo dice). El default `0` del corrector (`cg-2`) se revirtió: dejaba pasar `conf1 0.15` con suficiencia estructural (caso a361f566) |
| `WITT_CG_CALIBRATION_ORIGINS` *(corrector)* | `production` | `runs._calibration_origins` → `db.calibration_coverage(include_origins=)` | orígenes que cuentan como historia de calibración (CSV tolerante, minúsculas, sin duplicados; `all` = sin filtro declarado); fuente en `components.calibration_coverage.include_origins_source` |
| `WITT_COMPETENCE_MIN_HISTORY` | 10 | `runs._competence_min_history` → `db.calibration_coverage` (tolerante: vacía/basura/≤0 → 10 declarado en `min_required_source`) | corridas CLOSED con ≥1 rating que intersecan los nichos del plan para `sufficient` |
| `WITT_FALLBACK_CONF_TAU` | 0.5 (ya existía) | `runs.FALLBACK_CONF_TAU` (lector TOLERANTE de `competence`, fuente en `fb_meta.tau_source`) → `evaluate(tau=)` (`tau_source 'caller'`) | τ del componente `conf1_ge_tau` y de la regla legada; declarada en el compose |
| `WITT_SEARCH_HARNESS` *(corrector)* | `1` | `runs._search_harness_enabled` (fuente en `fb_meta.search_harness_enabled_source`) | `0` = la compuerta decide pero la Ruta B corre por `path_b_bundle` SIN plan (`search_ledger.state 'legacy-path-b (kill-switch WITT_SEARCH_HARNESS=0)'`) |
| `WITT_SEARCH_ROUNDS_CAP` | 2 | `runs._search_config` (delega en `search_harness._env_int_src`) · `search_harness.build_search_plan` (fuente en `config_source.cap` / `plan.rounds_cap_source`; `config_reader` declarado) | rondas máximas por corrida; una 2ª ronda sólo para familias con INSUMOS nuevos |
| `WITT_SEARCH_ROUND_BUDGET_S` | 120 | idem | presupuesto de reloj por RONDA, repartido entre las familias que faltan; `skipped-budget` declarado |
| `WITT_SEARCH_DEFAULT_FAMILIES` | `europepmc,pubmed,zfin,alliance_orthologs,zfin_expression` | `search_harness.resolve_default_families` — UN lector para `runs` y el plan (minúsculas, sin duplicados) | familias que corren sin directivas; nombrar una `directive-only` ES la directiva del operador; desconocidas → `families_excluded 'unknown-family'` |
| `WITT_JUDGE_RETRIES` | 1 | `composite_auditor.resolve_judge_retries` (en cada `audit`; tolerante) | intentos ADICIONALES por juez caído/ilegible; `audit.judge_retries {value, source}` |
| `WITT_MCP_CACHE_DIR` | `<repo>/mcp_cache` | tools Layer 0; declarado en `plan.cache_dir` | caché de lectura por día (necesita escritura en el contenedor) |
| `OPENALEX_API_KEY` | — (opcional) | `openalex_search` (sólo `api_key_present` se declara) | sin llave OpenAlex cobra créditos (10 / 0.001 USD por llamada, 1000/día medidos) |
| `WITT_UNPAYWALL_EMAIL` | — (opcional) | `unpaywall_crossref` (Unpaywall lo EXIGE; también primer `mailto` de Crossref/OpenAlex) | sin él la fila Unpaywall es `tool-unavailable` declarada; jamás se inventa correo; una env presente y vacía cuenta como ausente |
| `WITT_ENSEMBL_MIN_INTERVAL_S` | 0.07 | `ensembl_homology` (`net_throttle`) | pacing de `rest.ensembl.org` (15 req/s documentados; 55k/h medidos) |
| `WITT_ZFIN_EXPR_DOWNLOAD_BUDGET_S` · `WITT_ZFIN_EXPR_MAX_MB` · `WITT_ZFIN_EXPR_SCAN_BUDGET_S` | 180 · 500 · 60 | `zfin_expression_tsv` | presupuesto/tope de la descarga diaria y del escaneo local; exceso → `error BudgetExhausted` declarado, `.part` borrado |
| `WITT_GEO_RETMAX` · `WITT_GEO_ORGANISM` · `WITT_OPENALEX_PER_PAGE` | 10 · `'Danio rerio'` · 5 | `geo_gds` · `openalex_search` | uids por esearch (clamp 1..500); bloque `[Organism]` (una env PRESENTE y vacía lo DESACTIVA — por eso el compose NO la declara); works por llamada (clamp 1..200) |
| `NCBI_API_KEY` · `WITT_NCBI_EMAIL` · `WITT_NCBI_MIN_INTERVAL_S` | ya existían (ADR-0078) | `pubmed_literature` → compartidos por `geo_gds` (mismo throttle de proceso) y como `mailto` de respaldo de Crossref/OpenAlex (NUNCA para Unpaywall) | identidad y pacing NCBI |

### Gates NO-SPEND (corridos el 2026-09-15, offline, máscara `WITT_BACKEND_DB_URL="sqlite:///…/witt-smokes/smoke-<nombre>.db"` · `NEO4J_URI=""` · `RAG_BACKEND=sparse` · `OPENAI_API_KEY=""` · `ANTHROPIC_API_KEY=""` · `WITT_RUN_ORIGIN=smoke`; Python del venv `witt-query-service`)

| Gate | Resultado |
|---|---|
| `smoke_competence.py` (C1 + corrector + cg-3: 8 checks de `competence.evaluate` puro — conjunción CON el escalar por default (`cg-3`: conf 0.3 → `['conf1_ge_tau']`, conf ausente → `'conf1-absent'`) y apagado explícito con `WITT_CG_CONF_COMPONENT=0` (informativo, nota veraz), conf ausente, inadmisible/estructural/no-medido, store-consultation `not_applicable`, kill-switch, calibration gating on/off, sin plan, env tolerante + `compact`; 1 de `db.calibration_coverage`; 18 del cableado real en `execute_run` con `retrieve`/`path_b_bundle` monkeypatcheados: competente sin ronda (`n_rounds 0`), no competente → plan REAL + harness stub + pass2, kill-switch alto/bajo con la Ruta B LEGADA (`search_plan None`, `trigger 'confidence'`), estructural, calibración sólo `production` vs `WITT_CG_CALIBRATION_ORIGINS=smoke`, harness ausente y `path_b_bundle` con firma vieja DECLARADOS, `by_stage` con/sin `usage_elicitation` y `plan-without-usage`, reintento por juez, `citation_support` eleva a `supported`) | **27/27 PASS** |
| `smoke_search_harness.py` (C2 + corrector: plan por familias/directivas/caller, `directive-only` fuera salvo nombrada, desconocidas declaradas, ronda con presupuesto y fuente lenta simulada → `skipped-budget`, dedup contra `existing_ids` y dentro de la ronda, ids derivados con `gap_flag`, insumos encadenados DOI/curie, tools ausentes `tool-unavailable`, adaptadores legados byte-compatibles, `retrieve` sin plan sin cambios; `plan_event_payload.state 'built'`, `should_run_next_round(…, inputs_changed)`, `resolve_default_families`, sin insumos nuevos → UNA ronda `'no-new-inputs'`, ronda 2 SÓLO para la familia con insumo nuevo (`monarch` tras la curie de `alliance`) con la otra `skipped-cap 'same inputs as round 1 (not re-executed)'`, insumo resuelto en la misma ronda → una ronda) | **45/45 PASS** |
| `smoke_tools_a.py` (C3 + corrector: `alliance_orthologs` A0–A11 (símbolo sin gen → `no-match 'symbol-unresolved'` + `throttle` declarado) · `ensembl_homology` B0–B10 · `zfin_expression_tsv` C0–C16 — `column_mode` positional/header, `evidence_id` desde las llaves de la fila == `build_evidence_id(resolves_to)` 58/58 y `raw_ref.line_no` localizando la línea real 58/58, 58 ids distintos, split por TAB con comilla, `n_rows_malformed`, presupuestos — · contrato común D1–D4) | **45/45 PASS** |
| `smoke_tools_b.py` (C4: `uniprot` · `monarch` · `reactome` · `string` — fixture, vacío→no-match, 503→error sin data, timeout 0/7/default, cache hit, labels, evidence_id, procedencia; el bug de `reviewed None` en TrEMBL se halló y se clavó aquí) | **69/69 PASS** |
| `smoke_tools_c.py` (C5 + corrector: `geo_gds` 22 · `unpaywall_crossref` 24 (Crossref 503 + Unpaywall success = filas independientes; sin correo → `tool-unavailable`, cero llamadas) · `openalex_search` 17 (créditos declarados) · transversal 5: CERO correos en `fixtures/*.json`, recorte del fixture declarado, `strip_affiliation_strings`/`redact_emails` cuentan) | **68/68 PASS** |
| `smoke_gate_citations.py` (C6 + corrector: predicado positivo/declinación/ids vacíos; `absence_kind` AUSENTE → afirmación positiva (sin citas inadmisible, con 1 cita admisible); declinación con identificadores RESUELTOS (informe inyectado o medido) sin citas → inadmisible, con cita → admisible, sin informe → `not-provided`; escalera con y sin grounding sobre bundle sintético con Ruta A + EPMC + PubMed + ZFIN + DOI; no-salto de peldaños; `VERDICT_TOOL` opcional; charge sólo grounding; caller inyectado que falla 1 vez → veredicto + `retries_judge 1`, 2 veces → `errored`, ilegible → reintento, usage sólo de intentos con usage, env leída en `audit()`; end-to-end panel→`support_state`) | **48/48 PASS** |
| `smoke_run_pipeline.py` (C7 integrador + corrector + cg-3: 217 → 238 → 247 → **248**; 32 checks ADR-0080 — cableado ESTÁTICO de `SEARCH_DISPATCH` sobre los 12 archivos reales (`fn_resolved == fn`), costuras C2↔C5, competente con plan sin ronda (`n_rounds 0`) y trigger null con la traza en orden, bloque `stage.competence == frozen.competence` (`cg-3`, `conjunction` CON `conf1_ge_tau` primero, nota veraz, `trigger_decided_by`, `tau_source`), `by_stage` competente (plan 400, `_sum 540`), NO competente con el harness REAL → 1 ronda `found-new`, 5 `stage.search.source`, ítem de ortología con id del tool, PubMed declarando duplicados de EPMC, `timeout` recibido por los fakes; `by_stage` NO competente y con revisión; camino REAL con `elicit_pass1 {30, 3, measured}`; eventos `gate{pass 'pass1','pass2'}` / `elicit` / `synthesize.pass1.usage`; nada nuevo → UNA ronda `'no-new-inputs'` (5 source events, no 10) + predicado `should_run_next_round(…, inputs_changed)`; `WITT_SEARCH_ROUNDS_CAP=1` → `rounds-cap`; presupuesto con reloj falso → `skipped-budget` + `over_budget`; kill-switch alto/bajo con la Ruta B de ADR-0078 byte a byte (`trigger 'confidence'`, `harness_used False`, sin `stage.search.round/source`, `legacy-path-b (kill-switch …)`, `triggered_by` con el literal de ADR-0051, `bundle.path_b` sin `search_ledger`); `WITT_SEARCH_HARNESS=0`; `WITT_CG_CONF_COMPONENT` default (gatea, `cg-3`: conf 0.3 → no competente + ronda) vs `0` explícito (informativo, competente, nota == gating) en dos checks; `WITT_CG_REQUIRE_CALIBRATION=1` gatea con n 0 (sólo `production`) + lector `WITT_CG_CALIBRATION_ORIGINS`; escalera `supported`/`unresolved`; afirmación positiva sin citas, `absence_kind` ausente sin citas y declinación con `ENSDARG` resuelto sin citas → inadmisibles; declinación limpia → competente; reintento por juez; juez AGOTADO que cobró → M8 cuadra (`panel 44`, `by_model` con el reviewer errado, `input_tokens == pasadas + plan + audit.usage`); `by_stage.plan` tres estados; env de familias en mayúsculas/duplicadas → UNA verdad; contrato 1.9 en las 20 corridas con `'confidence'` sólo bajo `competent null`; **0 llamadas a `urlopen` y `mcp_cache` byte-idéntico** — MEDIDO) | 203/217 → 217/217 → 238/238 → 247/247 → **248/248 PASS** |
| `smoke_thread_context.py` (kill-switch `WITT_COMPETENCE_GATE=0` para los conteos de pasadas + *(corrector)* UNA corrida encadenada con la compuerta ENCENDIDA: `no-plan` → dos pasadas con el snapshot del padre en AMBAS, `pass 'pass2'`, `parent_identifier_leak` evaluado sobre la candidata) | 34/36 → 36/36 → **37/37 PASS** |
| `smoke_run_recovery.py` (compara la forma BASE de las citas: la escalera es aditiva) | 39/40 → **40/40 PASS** |
| resto del directorio (`entities` 16 · `fetch_paper` 41 · `m5v2_http` 32 · `niches` 21 · `notes_http` 28 · `precedent` 30 · `pubmed_tool` 32 · `query_service` 47 · `question_agent_http` 35 · `ratings_calibration` 44 · `run_comments_http` 14 · `run_recovery` 40 · `runs_list_http` 17 · `runs_thread_http` 54 · `search_queries` 163 · `threads_db` 42 · `zfin_tool` 26 — `fetch_paper`/`pubmed_tool`/`zfin_tool` sin cambio tras `timeout=` opcional y el throttle) | todos PASS, exit 0 — **25/25 gates verdes tras el corrector** |

### Gates EN VIVO pendientes (NO ejecutados en esta obra — gastan modelo o red más allá de la GET por API; los corre Emmanuel tras el redeploy)

1. **Corrida real NO competente en prod → rondas.** Una pregunta con plan `evidence-run` y confianza baja (o una sin plan
   vía `POST /runs` directo, que hoy es `no-plan`): en la Traza `stage.competence` con sus componentes y `reasons`,
   `stage.search.plan` con las 5 familias default, 5 `stage.search.source` con estados REALES (EPMC/PubMed/ZFIN como hoy;
   `alliance_orthologs` success con `cache_hit false` la primera vez; `zfin_expression` success tras la descarga de 43.7 MB
   — o `skipped-budget`/`error` declarado si no alcanzó el presupuesto o el contenedor no escribe), `stage.search.round`,
   `stage.path_b {trigger 'competence', harness_used true}`; en el registro `search_ledger.state 'harness'`,
   `n_rounds ≤ 2`, `stop_reason`, y `fallback.fb_meta.trigger_legacy`.
2. **Recall de las fuentes nuevas.** En esa corrida, ¿pass2 CITA ítems de `alliance_orthologs`/`zfin_expression`
   (`citations[].support_state 'passage_delivered'` o `'supported'` con el `statement` del ítem)? Comparar `n_items` del
   harness vs. citas efectivas; si nunca cita, el ítem no está llegando en forma legible al sintetizador.
3. **Costo del prompt con más evidencia.** `token_usage.by_stage.synthesize_pass2.in` de esa corrida contra la mediana de
   `synthesize_pass2` de las corridas ADR-0078 (M8); y el `elicit_*` separado (`state 'measured'`) en el camino real.
4. **Corrida competente en prod → cero ronda.** Plan `evidence-run` + admisible (la confianza ya no decide): `competent
   true`, `fallback.trigger null`, `search_ledger.state 'not-requested…'`, `n_search_rounds 0`, sin `stage.search.*` en la Traza.
5. **Las GETs que la obra NO gastó:** Ensembl no-match (HTTP 400 `"No valid lookup"`, un símbolo inexistente) ·
   Unpaywall real con `WITT_UNPAYWALL_EMAIL` fijado (grabar el fixture y reemplazar el SINTÉTICO) · OpenAlex con
   `OPENALEX_API_KEY` (header vs. query param) · Alliance `search_autocomplete` para el resolve símbolo→curie de
   `alliance_orthologs` (en el smoke es un stub declarado).
6. **Reintento por juez en vivo:** un `stage.audit.judge` con `attempt 2` en la Traza real y la fila con `attempts
   [errored, ok]`; comprobar que el latido por intento mantiene el hueco < `WITT_REAP_STALE_S`.
7. **`_migrate`/arranque** sin cambios de esquema; `GET /runs/{id}/record.pdf` de una corrida 1.9 abre y muestra
   `trigger_decided_by`, el veredicto de la compuerta, el estado del `search_ledger` y el `support_state` por cita (lo demás:
   deuda declarada en *Consequences*).
8. **Kill-switch en prod (`WITT_COMPETENCE_GATE=0`) durante una corrida con `pass1 < τ`:** Traza sin `stage.search.round`,
   `stage.path_b {trigger 'confidence', harness_used false}`, registro `search_ledger.state 'legacy-path-b (kill-switch
   WITT_COMPETENCE_GATE=0)'` — el camino de ADR-0078 intacto.

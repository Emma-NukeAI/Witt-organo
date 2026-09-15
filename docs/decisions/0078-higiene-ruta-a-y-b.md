# ADR-0078 — Higiene de Ruta A y B: el sintetizador lee el contenido, cada índice recibe su query, cada fuente deja su estado, y nada se cotiza ni se cita a ciegas

- **Status:** Accepted — 2026-09-14. Origen: Emmanuel aprueba el plan v3 del brief *Consejo de agentes*;
  hallazgos propios + auditoría externa Codex/Martín 2026-09-13. Los nueve hallazgos vivos de esa
  auditoría cruzada son el Context de este ADR; las mediciones se hicieron el 2026-09-13/14 contra el
  código de `master` y las APIs públicas (una GET por API, grabada como fixture).
- **Corrector final (2026-09-14, misma rama):** tres revisiones cruzadas de la obra (doctrina · corrección
  y regresiones · contrato y paridad) produjeron 3 hallazgos de severidad alta y 9 medias, todos aplicados;
  las decisiones que cambiaron están marcadas **[corrector]** abajo. Una medición nueva:
  `GET …/gene/ZFIN:ZDB-GENE-980526-558/phenotypes?limit=300&filter.termName=pronephr|glomer` → **HTTP 400
  Bad Request** (Alliance, 2026-09-14; la única GET en vivo del corrector). `|` NO es un separador OR.
- **Relates:** ADR-0022 (la Ruta B existe para que la ausencia en DI dispare búsqueda, no un tope) ·
  ADR-0043 (tres estados, jamás `null` ambiguo) · ADR-0048 (`--workers 1`: hilos, no procesos) ·
  ADR-0050 (bitácora única; `last_event_at` es el latido) · ADR-0051 (`TokenUsage` medido, costo
  PROYECCIÓN etiquetada) · ADR-0057 (la query externa se REGISTRA: buscar mal ≠ no existe) · ADR-0059
  (ZFIN como fuente nativa) · ADR-0062 (PubMed en Layer 0, dedup declarado) · ADR-0074 (campos-lista
  serializados: se parsean con procedencia, jamás se explotan en caracteres) · ADR 2026-07-13 del vault
  (clases de cifra: medición / atestiguada / proyección).
- **Affects:** `analysis/scripts/lib/answer_pipeline.py` (integrador) · `analysis/scripts/lib/search_queries.py`
  (nuevo: constructor determinista) · `analysis/scripts/lib/net_throttle.py` (nuevo: pacing por host y
  proceso) · `analysis/scripts/lib/fetch_paper.py` · `.tooluniverse/tools/zfin_zebrafish.py` ·
  `.tooluniverse/tools/pubmed_literature.py` · `rag_index/query_service/{db,runs,app}.py` ·
  `rag_index/query_service/fixtures/alliance_phenotypes_wt1a_20260913.json` (nuevo, respuesta real íntegra)
  · gates nuevos `smoke_{zfin_tool,pubmed_tool,fetch_paper,search_queries,run_recovery}.py` +
  `smoke_run_pipeline.py` (126 → 160) · `README.md` · `docker-compose.query.yml` · witt-webapp
  (tipar los campos nuevos; ver *Consequences*). **Cero mutación de la DATA INAMOVIBLE, del registro
  congelado existente y de `mcp_cache`.**

## Context

Todas las cifras de esta sección son MEDICIONES (código leído línea a línea, o una llamada real grabada).

1. **Ruta A entregaba 140 caracteres por hit.** `answer_pipeline.path_a` recortaba `"text": (h.text or
   "")[:140]` (línea 113). El índice sí servía el chunk; el sintetizador y el panel leían una línea. Un
   modelo que responde con 140 chars de evidencia por hit está respondiendo de memoria.
2. **La query externa era símbolos ANDeados como texto libre.** `build_external_query` devolvía
   `" ".join(entities)` (líneas 343–352). Medido en vivo: `osr1 prkci pax2a` → PubMed **0** hits, Europe
   PMC **1**. Ninguno de los tres índices recibía su sintaxis (`[tiab]`, `TITLE:/ABSTRACT:`,
   `filter.termName`). Una query mal formada es indistinguible de "no hay literatura" (LOTE-03).
3. **El abstract y el texto se bajaban y se tiraban.** `search_rec` y `fetched` se filtraban a metadatos
   (líneas 389–394 y 440–442): `fetch_external` descargaba abstract y, si OA, el fullTextXML — y al bundle
   sólo llegaban pmid/título/año/journal. El costo de red se pagaba; el contenido no llegaba a nadie.
4. **n=2 fijo.** `path_b_bundle(n=2)` y `retrieve(n_papers=2)` (líneas 459 y 507): dos papers por fuente,
   sin pool, sin regla de selección declarada.
5. **Europe PMC sin ledger y sin cinturón.** `search_europepmc` (fetch_paper 55–69) no tenía `try/except`
   ni parámetro `sort`; la llamada en `path_b` (línea 434) no estaba envuelta: un timeout de EPMC mataba
   el bloque entero, y no existía la llave `europepmc_searched` (sólo `pubmed_searched` y `zfin_searched`).
   Además `fetch_paper.DATE = "20260613"` era un literal fijo (línea 39) y el UA llevaba un correo
   hardcodeado (línea 38).
6. **ZFIN leía una llave muerta.** La API de Alliance (`/api/gene/{curie}/phenotypes?limit=300`) ya no
   trae `pubmedPubModIDs`; trae `pubmedPublications: [{referencedCurie: 'PMID:…'}]`. Medido el
   2026-09-13 sobre wt1a `ZFIN:ZDB-GENE-980526-558`: 53/53 statements con `pubmedPublications`, 0/53 con la
   llave vieja; en los 50 statements compartidos con el golden del 2026-08-22 los PMIDs son idénticos.
   `zfin_zebrafish.py:60` leía la llave vieja → `references=[]` bajo `status 'success'`: **ZFIN en prod
   devolvía statements sin una sola referencia y lo reportaba como éxito.**
7. **PubMed sin identidad ni pacing.** `pubmed_literature.py` no mandaba `tool`/`email` (sólo
   `NCBI_API_KEY`); el servicio corre `WITT_RUN_WORKERS` hilos (default 2) en un proceso, y NCBI responde
   `X-RateLimit-Limit: 3` sin llave. Dos hilos disparando a la vez producen 429 que río abajo se leen como
   "cero resultados".
8. **Citas explotadas y precio equivocado.** `runs._normalize_citations` (742–753) iteraba lo que
   recibiera: un `evidence_cited` serializado como string producía N pseudocitas de UN carácter (469 en
   una corrida real); `_lista_serializada` (ADR-0074) se aplicaba a `gap_flags` y `alternatives` pero no a
   `evidence_cited`. `PRICES_PER_MTOK_USD` cobraba `claude-sonnet-5` a (3.0, 15.0) y vale (2.0, 10.0):
   las proyecciones desde 2026-08 iban 1.5× infladas; y `.get(model, (0.0, 0.0))` cotizaba a **cero** todo
   modelo ausente de la tabla — un hueco de precio disfrazado de gasto nulo.
9. **Nadie recogía a los huérfanos.** `claim_next_queued` (db 482–495) hacía el UPDATE optimista sin
   `claimed_by`/`claimed_at`; `HEARTBEAT_STALE_S=300` (app 436) sólo pintaba la vista. Una corrida
   `running` cuyo hilo murió quedaba `running` para siempre.

## Decision

**(1) Ruta A lee el contenido.** `path_a` entrega hasta `WITT_PATH_A_CHARS` (default 2400) por hit y
declara el corte: `text_offsets [0, n]`, `text_sha256` del fragmento, `text_omitted`, `text_hit_chars`,
`text_source: "index-hit"`; el tope efectivo viaja en `path_a.text_cap_chars`.

**(2) Cada índice recibe su query, construida por código.** `lib/search_queries` (stdlib puro,
`QUERY_BUILDER_VERSION "1"`, hash golden en su gate) arma `pubmed_query`, `epmc_query` y `zfin_filter` a
partir de símbolos saneados + bloque de organismo + anatomía (ES/EN, sin acentos, con borde de palabra);
jamás rellena anatomía por default. **[corrector] UNA política de anatomía para los TRES índices:** la
unión de lo detectado en la pregunta ORIGINAL y en la formulación EN (`question_en`), con la procedencia
declarada por índice (`notes.anatomy ∈ from-question | from-question-en | from-both | none-in-question`
+ `notes.anatomy_text_source`). La primera entrega usaba el EN para PubMed/EPMC y la ES para ZFIN — dos
políticas en una corrida. **[corrector] La pregunta original JAMÁS se tokeniza como texto libre:**
`question_terms` sale sólo de `question_en` (`notes.question_terms_source`); sin símbolos y sin EN el modo
es `empty` con `notes.reason` (mandar español a PubMed era ~0 hits garantizados vestidos de "no hay
literatura", la lección LOTE-03). `answer_pipeline.build_source_queries` lo cablea: la formulación EN del
sintetizador entra como `question_en` (declarada en `query_builder.inputs.question_en_source`); una query
que ya salió del constructor se reconstruye, no se reinterpreta. `query_sent` se conserva (= la de EPMC,
`query_sent_scope: "europepmc"`); `query_source` pasa a `query-builder-v1:<symbols|question-only|empty>`.
Query `null` = nada que buscar → la fuente queda `not-searched`; nunca se manda una cadena vacía.

**(3) Cada fuente deja su estado.** `europepmc_searched` nace (`success|no-match|error|not-searched|
not-requested|tool-unavailable` + `n_found` hitCount, `n_returned`, `n_candidates`, `throttle`, `contact`,
`error?`) vía `fetch_paper.search_europepmc_ledger`, que no lanza: un fallo de EPMC es una fila `error` y
la corrida sigue con PubMed y ZFIN (§6 no-hang). `pubmed_searched` gana `query_sent`, `retmax_sent`,
`ncbi_identity` (`declared|missing`), `throttle`, `retries_429`, `rate_limit_headers` (+
`rate_limit_headers_from`), `http_status`. `zfin_searched[]` gana el estado `success-no-references` y
propaga `references_schema`, `phenotypes_capped_at_300`, `references_truncated`, `n_returned_by_api`,
`statements_truncated`, `anatomy_terms`, `anatomy_filter_mode`, `timeout_s`. El bloque declara
`ledger_version: "2"` y conserva TODAS sus llaves.
**[corrector] Tres estados en los contadores:** `n_returned` / `n_new` / `n_candidates` son enteros SOLO
cuando la fuente corrió (`success | no-match`); en `not-searched | not-requested | tool-unavailable |
error` son `null` (no medido — ADR-0043), nunca un 0 que un agregador sumaría como medición. `n_found`
jamás se rellena con el tamaño de página: si EPMC no trae `hitCount` es `null` + `n_found_note`. `n_papers
<= 0` no dispara ninguna búsqueda de literatura: ambas fuentes quedan `not-requested`. **[corrector] El
ledger declara `contact: "declared" | "unset"` — el correo de `WITT_NCBI_EMAIL` vive SÓLO en el header
User-Agent:** el ledger viaja al bundle, a `GET /runs/{id}` y al prompt del sintetizador y de los cuatro
jueces; la primera entrega escribía la dirección misma. `throttle_slept_s` es la medición de ESA llamada
(meta por llamada; el global de módulo mezclaba hilos).

**(4) Pool, dedup y selección declarados.** Se piden `WITT_PATH_B_RETMAX` (20) candidatos a cada fuente
de literatura; se deduplican por PMID, PMCID y DOI normalizado (minúsculas, sin `https://doi.org/`); se
eligen `WITT_PATH_B_N_PAPERS` (5) con la regla `oa-with-pmcid-first, then source order` (estable); sólo
los elegidos se bajan. `selection` lleva `n_requested`, `n_candidates`, `n_selected`, `n_duplicates`,
`duplicates[{duplicate, of, matched_key, source}]`, `not_selected[]`.

**(5) El contenido llega al bundle.** Cada paper lleva `abstract`, `text_excerpt` (≤
`WITT_PATH_B_EXCERPT_CHARS` 1500), `text_provenance ∈ abstract|fulltext-excerpt|none` y la regla del
recorte `text_excerpt_rule ∈ full|head|top-paragraphs-by-lexical-overlap|none` (párrafos con más
términos de la query — símbolos, anatomía, términos de la pregunta — emitidos en orden del documento;
`head` sólo si ningún párrafo comparte términos). `fetched` gana `cache_hit`, `cached_at`,
`cached_at_source`, `cache_age_days`, `fetched_at`, `search_ledger` SOLO cuando el fetch los midió.

**(6) Red con identidad y pacing.** `tool=witt-organogenesis` siempre; `email` sólo con
`WITT_NCBI_EMAIL` — si falta, `ncbi_identity: "missing"` y `contact: "unset"` (no se inventa un correo).
`lib/net_throttle` pacea por host y por PROCESO (`--workers 1`, ADR-0048): 0.34 s sin llave / 0.10 s con
llave en eutils (`WITT_NCBI_MIN_INTERVAL_S` sobreescribe), 0.2 s en EPMC (`WITT_EPMC_MIN_INTERVAL_S`);
UN reintento en 429 con `Retry-After` (o 1 s); un segundo 429 es `error` declarado. La caché de
`raw_paper_*` se LEE con `WITT_CACHE_TTL_DAYS` (7) y el sello es la fecha real de descarga.

**(7) ZFIN honesto.** El parser lee `pubmedPublications[].referencedCurie` primero y cae a
`pubmedPubModIDs`; declara el esquema por statement y por resultado; `success-no-references` cuando hay
statements y cero PMIDs. **[corrector] El filtro anatómico va en el CLIENTE por default:**
`filter.termName=pronephr|glomer` (la sintaxis OR que la primera entrega ASUMIÓ y despachaba con
`server_filter=True`) respondió **HTTP 400** en vivo — toda pregunta con ≥2 raíces habría dejado cada
símbolo en `error`. El tool ya no une raíces con `|`: con `server_filter=True` hace UNA GET por raíz y une
en cliente (dedup por statement); la forma de una sola raíz sigue SIN medir, así que `server_filter` es
**False por default** (`WITT_ZFIN_SERVER_FILTER=1` la activa cuando se mida) y el ledger declara
`anatomy_filter_mode: client`. El respaldo cliente casa por PREFIJO DE PALABRA (`\bduct` no casa
`reduction`/`induction`/`conduction`), la misma semántica que el detector que produjo la raíz
(`anatomy_filter_semantics`). `n_phenotypes_total` es el total del GEN sólo sin filtro de servidor
(`n_phenotypes_total_scope: gene`); con filtro es `null` + `server_filter_totals` por raíz
(`scope: server-filtered`), y un cero producido por el servidor se declara en `detail`. `timeout` propagable
— el integrador pasa `min(10, presupuesto restante / 2)` POR GET (dos GETs por símbolo) y lo declara con
`timeout_s_scope: per-http-get`; con < 0.5 s de presupuesto no se dispara nada (`skipped-budget`). El
fixture real del 2026-09-13 es el golden del gate.

**(8) Corrida recuperable, citas y precios declarados.** `runs.claimed_by`/`claimed_at`; hilo
`run-reaper` (cada `WITT_REAP_STALE_S`/3 s) pasa a `failed` con `error "worker-lost: sin latido por >N s
(ADR-0078)"` toda `running` sin latido por `WITT_REAP_STALE_S` (900 = 3× el umbral de la vista) y emite
`run.state {reason: worker-lost}`; **nunca re-encola**. **[corrector] La carrera reaper ↔ worker vivo se
cierra en las dos direcciones:** (a) el worker cierra con `db.finish_run` (`UPDATE … WHERE state='running'`)
— si la fila ya fue segada o cancelada NO la pisa y deja `run.state.conflict {attempted, found, ignored:
true}` (antes `update_run` sin condición dejaba `awaiting_closure` + frozen record sobre un `error:
worker-lost`, dos veredictos terminales en un registro); (b) el reaper exige que el latido siga siendo el
que midió y marca la segada con `cancel_requested` (`cancelled_by: run-reaper`) para que un hilo vivo
aborte en la siguiente frontera y deje de gastar; (c) latido POR JUEZ (`stage.audit.judge`) — el panel
corre en serie y cada juez puede tardar hasta 240 s sin evento, así que 4 jueces (u 8 con revisión)
rebasaban legítimamente los 900 s; (d) `claimed_by = "<boot_id>:<pid>:<hilo>"` (el nombre de hilo era
idéntico en cada generación del proceso); (e) **al arrancar el proceso TODA fila `running` se siega**
(`reason: worker-lost-restart`, umbral 0): con `--workers 1` ninguna tiene worker por construcción, latiera
hace 5 min o hace 5 h — la primera entrega sólo segaba las de >900 s y una huérfana reciente seguía
sirviéndose como viva hasta 20 min; (f) `WITT_REAP_STALE_S` vacía o basura → 900 declarado
(`REAP_STALE_S_SOURCE`), ya no tumba el import; `failure_reason ∈ worker-lost | pipeline | null` tipado en
la vista. Un `evidence_cited` string se re-parsea con procedencia (`citations_schema.source:
string-reparsed`) o se declara `string-unparseable` con `citations=[]` — jamás se itera por caracteres;
`evidence_cited_raw` conserva el crudo. **[corrector] Un `evidence_cited` AUSENTE se declara
`citations_schema.source: absent`** (+ gap_flag), no se rellena con `[]` (que se leería "citó 0"); y el
re-parseo tiene UNA sede: `execute_run` normaliza desde el string crudo cuando lo hubo, así el camino real
de producción produce `string-reparsed` (la primera entrega lo dejaba inalcanzable: el wrapper ya había
convertido a lista y el registro decía `list` junto a un `evidence_cited_raw` string). `claude-sonnet-5` =
(2.0, 10.0); los modelos del consejo entran a la tabla con `PRICES_AS_OF "2026-09"`; un modelo sin precio
se EXCLUYE de la proyección y se declara en `token_usage.missing_price_models` con
`cost_projection_complete: false` (y en `/usage`: `missing_price_models`, `n_runs_cost_incomplete`,
`n_runs_cost_unknown`, `by_model[m].estimated_cost_usd: null` + `price_state: "missing"`; **[corrector]**
`/usage.cost_projection_complete` es `true` SÓLO sin modelos sin precio Y con `n_runs_cost_incomplete ==
0` — la suma agrega costos congelados, y un precio que hoy existe no repara el gasto que aquella corrida
excluyó). **[corrector] El prompt lee evidencia, no bitácora:** `_compact_evidence` proyecta `path_b`
(estados por fuente, selección, UN texto por paper) y deja fuera `query_builder`, throttles,
`rate_limit_headers`, `search_ledger` anidado, `dedup_keys`, `duplicates`; el bloque íntegro sigue en
`runs.bundle_json` (identidad sha).

## Consequences

- **Contrato: `render_contract_version` sube a "1.7"** [corrector]. La historia del propio `runs.py`
  muestra que cada campo aditivo al registro congelado subió la versión (1.2 … 1.6); dejarla en 1.6 con dos
  formas distintas habría vaciado a la versión de su único uso: identificar la forma. La webapp no gatea
  por versión (`Hoja.tsx` sólo la imprime) y todo campo del `RegistroCongelado` es opcional — tipar los
  nuevos como `?` (convención M5 v2 de `types.ts`) ES la paridad front↔back, no congelar el número. La
  "regla de paridad" que la primera entrega invocaba no está escrita en ningún repo; queda escrita aquí.
- **Cambios de tipo / dominio que SÍ hay** (un lector que hace `.lower()` sobre `query_sent` o compara
  `query_source == 'synthesizer'` debe saberlo por este ADR, no por un stack trace) [corrector]:
  `path_b.query_sent: str → str | null` (`null` = nada que buscar); `path_b.query_source` cambia de dominio
  (`entities | question-verbatim | synthesizer` → `query-builder-v1:<symbols|question-only|empty>`; los
  literales viejos quedan sólo en registros con `ledger_version` ausente); `papers[].zfin.anatomy_filter`
  pasa de una raíz a raíces unidas con `|` y `anatomy_filter_source` gana el literal
  `search_queries.build_zfin_filter:v1`; `europepmc_searched.n_returned`, `pubmed_searched.{n_returned,
  n_new, n_candidates}: int → int | null` y `duplicates_of_europepmc: list → list | null`;
  `zfin_searched[].n_phenotypes_total: int → int | null` (con `n_phenotypes_total_scope`); `contact` ya no
  puede ser un correo. El resto es aditivo; `path_b.ledger_version "2"` marca el bloque nuevo.
- **Dónde vive el ledger v2 para el lector humano** [corrector]: el bloque `path_b` NO viaja en el registro
  congelado (vive en `runs.bundle_json`); lo que la Traza puede leer es el evento `stage.path_b`, que gana
  `epmc_query`, `selection.not_selected` y un resumen por paper (`evidence_id, source, selection_rank,
  text_provenance, fetched.{found, full_text, cache_hit?, cached_at?, fetched_at?, fetch_error?}`, `zfin.{status,
  has_references, n_matched, n_returned}`) — sin texto. Hoy `Traza.tsx` lee de ese evento sólo
  `n_results_by_source`, `zfin_status_tally`, `pubmed_searched.{status, n_new, duplicates_of_europepmc}`,
  `n_papers`, `trigger`.
- **La webapp debe tipar y pintar** (`witt-webapp/src/api/types.ts`, todo opcional `?`): el bump a 1.7 y
  los campos nuevos del registro (`citations_schema` — "citó y se perdió" ≠ "citó 0" ≠ `absent`;
  `evidence_cited_raw`; `token_usage.missing_price_models`/`cost_projection_complete` — M8: el total NO es
  completo cuando false); la vista de corrida (`claimed_by`, `claimed_at`, `failure_reason`); el evento
  `stage.path_b` (resumen por paper con `fetched.cache_hit`/`cached_at` pintado como "caché de <fecha>",
  nunca como fresco; `europepmc_searched`, `selection`, `query_source` con los literales nuevos, los estados
  nuevos de ZFIN y PubMed, `ncbi_identity "missing"` visible); `/usage` (`n_runs_cost_unknown`,
  `by_model[m].price_state`).
- **Producción.** Al redeploy: `_migrate` añade `claimed_by`/`claimed_at` (tipo compilado por dialecto —
  `TIMESTAMP WITH TIME ZONE` en Postgres); **TODA `running` existente cae a `failed/worker-lost`
  (`worker-lost-restart`) en el arranque** (deseado; avisar al equipo). Sin `WITT_NCBI_EMAIL` en Dokploy
  cada corrida declarará `ncbi_identity: "missing"` — correcto y visible, pero hay que fijarla; al fijarla,
  ningún ledger la lleva (sólo el User-Agent). `WITT_ZFIN_SERVER_FILTER` queda en 0 hasta medir la GET de
  una raíz.
- **Históricos NO se recalculan** (nada se re-ejecuta solo; el registro congelado no muta): las corridas
  que cotizaron sonnet-5 a 1.5× o modelos sin precio a 0 quedan como están; `n_runs_cost_incomplete`
  sólo cuenta las que ya declaran la llave. Un backfill declarado sería ADR aparte.
- **Frontera del throttle.** El pacing es de proceso; con `--workers > 1` o varias réplicas dejaría de
  cubrir entre procesos (haría falta pacing compartido en la BD). Documentado, no supuesto.
- **Costo de modelo.** El sintetizador y el panel reciben ahora ~2400 chars × k hits + hasta 5 papers con
  excerpt de ≤1500 chars + abstracts: el prompt crece (proyección, sin medir aún — el gate EN VIVO 1 lo
  mide). Es el objetivo del ADR: que el modelo lea la evidencia, no su título.

### Variables de entorno (defaults declarados en código; el valor efectivo viaja en bundle/ledger)

| Variable | Default | Lector |
|---|---|---|
| `WITT_PATH_A_CHARS` | 2400 | `answer_pipeline.path_a` |
| `WITT_PATH_B_N_PAPERS` | 5 | `answer_pipeline.path_b` / `path_b_bundle` |
| `WITT_PATH_B_RETMAX` | 20 | `answer_pipeline` · `pubmed_literature.resolve_retmax` |
| `WITT_PATH_B_EXCERPT_CHARS` | 1500 | `answer_pipeline._paper_content` |
| `WITT_NCBI_EMAIL` | sin default (→ `missing`/`unset` declarado) | `pubmed_literature` · `fetch_paper` |
| `NCBI_API_KEY` | ya existía, opcional | `pubmed_literature` |
| `WITT_NCBI_MIN_INTERVAL_S` | derivado 0.34 / 0.10 (con llave) | `pubmed_literature.resolve_min_interval_s` |
| `WITT_EPMC_MIN_INTERVAL_S` | 0.2 | `fetch_paper` |
| `WITT_CACHE_TTL_DAYS` | 7 | `fetch_paper.fetch_external` |
| `WITT_REAP_STALE_S` | 900 (vacía/basura → 900 declarado) | `runs.REAP_STALE_S` + `REAP_STALE_S_SOURCE` |
| `WITT_ZFIN_SERVER_FILTER` [corrector] | 0 (filtro cliente) | `answer_pipeline._search_zfin` |

La procedencia del valor efectivo viaja en el bundle: `path_a.text_cap_source`, `path_b.n_papers_source`,
`path_b.retmax_source` ∈ `env:<VAR>` | `default-unset:<VAR>` | `default-invalid-env:<VAR>` | `caller`.

### Gates NO-SPEND (corridos el 2026-09-14, offline, máscara `WITT_BACKEND_DB_URL=sqlite:///<tmp>` · `NEO4J_URI=""` · `RAG_BACKEND=sparse` · `OPENAI_API_KEY=""` · `ANTHROPIC_API_KEY=""`)

| Gate | Resultado (primera entrega → corrector) |
|---|---|
| `smoke_run_pipeline.py` (integración; +34 checks ADR-0078, +21 del corrector: fuga de correo, camino real de citas, `absent`, conflicto reaper↔worker, latido por juez, forma por bloque, n=0, prompt proyectado, ZFIN cliente/servidor) | 160/160 → 181/181 PASS |
| `smoke_zfin_tool.py` (fixture real 2026-09-13 + golden viejo + sintéticos; una GET por raíz, prefijo de palabra, scope del total) | 23/23 → 26/26 PASS |
| `smoke_pubmed_tool.py` (identidad, retmax, throttle, 429) | 32/32 PASS |
| `smoke_fetch_paper.py` (ledger EPMC, caché de lectura, UA, throttle; contact sin correo, hitCount ausente) | 39/39 → 41/41 PASS |
| `smoke_search_queries.py` (6 casos × 3 índices, determinismo byte a byte; política única de anatomía, ES jamás como texto libre; hash regrabado — sólo cambiaron `notes`, las 18 queries son byte-idénticas) | 158/158 → 163/163 PASS |
| `smoke_run_recovery.py` (reaper, claimed_*, citas, precios) | 40/40 PASS |
| resto del directorio (`entities` 16 · `niches` 21 · `precedent` 15 · `query_service` 47 · `ratings_calibration` 39 · `m5v2_http` 32 · `notes_http` 28 · `question_agent_http` 33 · `run_comments_http` 14 · `runs_list_http` 17) | todos PASS, exit 0 |

### Gates EN VIVO pendientes (NO ejecutados en esta obra — gastan red o modelo; los corre Emmanuel tras el redeploy)

1. **Una corrida real** en witt-ai.com.mx con pregunta ES + símbolos: verificar en la Traza
   `path_b.ledger_version "2"`, `europepmc_searched.status`, `pubmed_searched.ncbi_identity "declared"` (con
   `WITT_NCBI_EMAIL` fijada), `selection.n_selected ≤ 5`, `papers[].text_provenance ≠ "none"` en al menos
   un paper OA, y `path_a.hits[].text` de hasta 2400 chars. Medir el `token_usage` resultante (proyección
   del prompt más largo) y compararlo con la mediana histórica.
2. **ZFIN en vivo**: `zfin_searched[].references_schema == "pubmedPublications"` y
   `phenotypes[].references ≠ []` para wt1a/pax2a. La GET con `filter.termName=pronephr|glomer` YA se hizo
   (corrector, 2026-09-14): **HTTP 400** — `|` no es OR; el tool ya no lo manda. Pendiente: UNA GET con una
   sola raíz (`…&filter.termName=pronephr`) para medir si el filtro de una raíz funciona (esperado: total
   16 < 53, todos los statements con 'pronephr'); si sí, grabarla como fixture y poner
   `WITT_ZFIN_SERVER_FILTER=1`; si no, el filtro se queda en el cliente (el default actual) y la opción se
   retira.
3. **PubMed/EPMC recall real** de las queries nativas sobre 3 preguntas del banco (hits > 0 donde la query
   libre daba 0); si el modo `question-only` mide 0 hits, la alternativa declarada es OR-ear los términos
   (`QUERY_BUILDER_VERSION "2"`, regrabar el hash golden).
4. **Reaper en prod**: tras el redeploy, `_migrate` sin error en el log, `GET /runs` muestra
   `claimed_by` en la primera corrida, y las `running` huérfanas previas aparecen `failed` con
   `worker-lost`.
5. **Throttle bajo dos workers**: dos corridas simultáneas con Ruta B sin ningún 429 en `pubmed_searched`
   (`retries_429 == 0`, `rate_limit_headers` presentes).
6. **/usage en prod**: `missing_price_models` vacío para los modelos reales del consejo;
   `cost_projection_complete: true` en la corrida nueva.

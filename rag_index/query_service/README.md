# Witt query service — el front door HTTP de solo lectura para la webapp

**Qué es (ADR-0048, bloque 2 del plan webapp):** el servicio que la webapp lee. Es un **cambio de
transporte, no una capa semántica nueva**: `/query` devuelve **exactamente** el sobre de
`server._query` (`{degraded, n_hits, hits, last_error, index_version, store_version}`, ADR-0043) —
mismo backend, mismos marcadores y misma regla no-hang §6 que el CLI `witt-di` y el MCP.

**Qué NO es:** no expone ninguna mutación. Ingesta y cambios a la DATA INAMOVIBLE siguen detrás del
gate humano (`ingest_service` / scripts del repo). El MCP sigue read-only. Nada nuevo se abre al
público: este servicio vive en la **red interna de Dokploy** y la webapp es la única superficie
expuesta (ADR-0047, decisión 5).

## Endpoints

| Método | Ruta | Auth | Nota |
|---|---|---|---|
| POST | `/login` | — | `{username, password}` → token de sesión (bearer) |
| POST | `/logout` | ✓ | revoca el token |
| GET | `/me` | ✓ | `{user_id, display_name, role}` (role = rater_profile) |
| GET | `/health` | — | liveness de proceso para Dokploy: sin red, sin spend |
| GET | `/query?q=&k=&niche=` | ✓ | **el sobre ADR-0043 verbatim**; degradado = 200 (la UI pinta la banda); `query_unavailable` = 503. `niche` (opcional): filtro **declarado** post-retrieval sobre ventana k×4 con bloque `filter` + caveat de recall (ADR-0056) |
| GET | `/resolve?key=` | ✓ | `VerifiedRecord` completo (bloque 1.4); NOT_FOUND = 200 con `resolved: false` |
| GET | `/raw?key=&filename=` | ✓ | drill al crudo (`fetch_raw`): URL presignada MinIO o source_url+sha256 |
| GET | `/status` | ✓ | **StoreStatus NO-SPEND** con caché TTL: los 9 campos del contrato + `index_version`, `integrity` (escaneo real o `scanned:false` honesto) y `embed_model_changed_at` (de `rag_index/config_history.json` — ADR-0055) |
| GET | `/taxonomia` | ✓ | nichos + bases + crosswalk con procedencia (ruta+mtime), TTL — la única puerta de la taxonomía (ADR-0055) |
| GET | `/artifacts` | ✓ | índice de históricos (ADR-0046): `reports/*.html` + `evaluation/runs/**` |
| GET | `/artifacts/report/{name}` | ✓ | sirve un HTML histórico (path-safe por membresía) |
| GET | `/artifacts/run/{set}/{name}` | ✓ | un run histórico (JSON; `instrumented: false` = sin `decision_state`) |
| GET | `/rack/search` · `/rack/resolve` · `/rack/status` | ✓ | alias de la superficie propuesta por la UI |
| POST | `/runs/plan` | ✓ | **el plan declarado** (ADR-0061; **plan v3** por ADR-0066): estructura del código + juicio del planner (nichos §3 + agentes §11 con gate resuelto por tabla + **0-3 `clarifying_questions` never-stopper**) + **`data_landscape`** estructural (preview DI sparse NO-SPEND + qué fuentes Ruta B aplican) + estimaciones DETERMINISTAS por métrica. Se refiere por `plan_id`; se consume UNA vez (409 `plan_already_used`) |
| POST | `/runs` | ✓ | encola una corrida (async); terminal SIEMPRE post-audit (ADR-0049). **409 `index_offline`** si el índice está OFFLINE — bloquea, no degrada (dev sparse: `WITT_ALLOW_RUNS_OFFLINE=1`) |
| GET | `/runs` · `/runs/{id}` | ✓ | lista y detalle por la MISMA vista: `heartbeat_age_s` + `heartbeat_stale` + `heartbeat_stale_after_s` (el umbral viaja) + `token_usage` (gasto en TODO camino de salida, failed/cancelled incluidos) + **`run_no`** (ADR-0076: el NÚMERO de corrida — identidad legible asignada al nacer; las anteriores a la columna se numeraron por orden de creación al arrancar) |
| GET | `/runs/{id}/record` | ✓ | el **registro congelado** que la UI renderiza (una fuente, tres lectores) |
| GET | `/runs/{id}/record.pdf` | ✓ | **el PDF de servidor** (M4, ADR-0073): generado DEL JSON congelado con plantilla propia — jamás "imprimir la página"; bandas con palabras completas, procedencia del escalar en palabras, ambas rondas de la revisión, identidad rota = 409; el ÚNICO canal autorizado de exportación |
| GET · POST | `/runs/{id}/comments` | ✓ | **los COMENTARIOS de la corrida** (ADR-0077): la conversación del equipo sobre la pregunta — anexo append-only y público (toda sesión lee y escribe; sin PATCH ni DELETE), fuera del registro congelado, de M5 y de los apuntes; autor y hora los pone el servidor; `body_max` declarado (4000); `n_comments` viaja en toda vista de corrida |
| GET | `/runs/{id}/events?after=` | ✓ | **replay** — las mismas filas que el stream (una bitácora) |
| GET | `/runs/{id}/stream` | ✓ | traza viva SSE (keep-alive; cierra al drenar un estado terminal) |
| POST | `/runs/{id}/cancel` | ✓ | body `{reason}`; registra `cancelled_by` (sesión) + `cancel_reason` — una cancelación sin autor es un hueco en el registro (ADR-0055). Queued: inmediato; running: frontera de etapa |
| POST | `/runs/{id}/close` | ✓ | cierre explícito: congela el registro (`frozen_at`) — requisito para precedente |
| GET | `/usage?from=&to=` | ✓ | agregados M8 en el SERVIDOR: totals/by_user/by_model/most_expensive; tokens [M], costo PROYECCIÓN con `cost_class`; `rack_embeddings` aparte con su caveat (ADR-0056) |
| GET | `/config-history` | ✓ | historial de config verbatim + procedencia; históricos de usuarios/store DECLARADOS (ADR-0056) |
| GET | `/consulta-sistema?q=` | ✓ | **la consulta abierta** (ADR-0070): la pregunta META respondida — inventario por secciones con fuente declarada (store/índice/corpus/taxonomía/corridas/config/cuarentena) + `resumen` en lenguaje natural compuesto por CÓDIGO; `model_consulted: false` estructural; ruteo por palabras clave con no-match declarado; NO-SPEND |
| GET | `/rack/node/{id}` | ✓ | **el browse del grafo** (ADR-0071, Rack fase 2): documento/entidad/nicho/base con sus aristas (MENTIONS lleva `verified_tier_weight` por arista) + **ejes POR ENTIDAD derivados** (la puerta que /resolve declara nunca servir); `browse_mode` in-band (graph \| files-fallback declarado, §6); NOT_FOUND = 200 found:false; el embedding jamás se serializa; NO-SPEND |
| GET | `/precedent/search?q=&k=` | ✓ | **la capa de precedente** (ADR-0053): corridas CERRADAS por relevancia, `admissible_as_evidence: false` estructural, scorer declarado; series de citas disjuntas (números=evidencia, letras=precedente) |
| POST | `/runs/{id}/ratings` | ✓ | **calificación M5** (ADR-0064): append-only (una corrección = fila nueva), procedencia DERIVADA de la sesión (`is_author`/`rater_profile`/`instrument`, jamás del cliente), ejes 1-5 con `[?]` explícito (`cannot-rate`/`not-applicable` — nunca un 1); solo corridas terminadas (409 en queued/running) |
| GET | `/runs/{id}/ratings` | ✓ | ratings + consenso con la **independencia M5 aplicada en el servidor**: scores ajenos enmascarados hasta que emitas el tuyo; el consenso cuenta sin promediar (`{invited, received, open, missing}`) |
| GET | `/ratings/pending` | ✓ | la cola "PENDIENTES DE CALIFICAR" del usuario de la sesión, con consenso y resumen epistémico por fila |
| GET | `/calibration` | ✓ | **ECE sobre corridas CERRADAS anclado en ratings humanos** (tapón 4, ADR-0064): reutiliza `compute_ece.py`, mapeo de outcomes DECLARADO en la respuesta, poder declarado (`n<10` = case capture, descriptivo, jamás un número ciego; `n>=10` agrega isotonic), desglose médico/dev; NO-SPEND |

**`/status` es NO-SPEND por construcción** (receta `liveness.py`): lee el JSON del store + el manifest
del índice y hace solo Cypher de conteo (jamás un embed). Con `WITT_STATUS_TTL_SECONDS` (default 60),
un indicador de cabecera refrescándose cuesta a lo sumo un round de Cypher gratis por TTL y **cero
OpenAI, siempre**. Si Neo4j no responde: `index_state: "OFFLINE"` + conteos `null` — nunca cifras
inventadas.

## Identidad (decisiones 3/4/9-bis + ADR-0047)

- **5 cuentas planas**: marcelo, natalia, martin (medico) · emmanuel, sharon (dev). El `role` es el
  `rater_profile` de las calificaciones, no un nivel de permiso.
- **La única asimetría es local**: altas, resets y bajas SOLO vía `python seed_users.py …` en una
  máquina con acceso a la BD (deliberadamente no existe endpoint HTTP de administración).
- **Corte de secrets**: el único secreto por persona es usuario+contraseña. Hash scrypt (stdlib) con
  salt por usuario; las sesiones son tokens opacos y la BD guarda solo su sha256.
- BD: `WITT_BACKEND_DB_URL` — Postgres en Dokploy (`postgresql+psycopg://…`, ADR-0047 decisión 1);
  sin la variable usa SQLite local (`backend.db`, gitignored) para dev.

## Despliegue (Dokploy)

1. App Postgres nativa en el mismo proyecto Dokploy (red interna, SIN external port) — hecha 2026-08-09
   (`rag-wittbackenddb-qxzrgu`).
2. **Create → Compose**, conectado a este repo (branch `master`), compose path
   `rag_index/query_service/docker-compose.query.yml`. En **Environment**: las mismas variables que ya
   usa el ingest service (`OPENAI_API_KEY`, `MINIO_*`, `NEO4J_USER/PASSWORD`) + `WITT_BACKEND_DB_URL`,
   **PERO** `NEO4J_URI=bolt://data-inamovible-neo4j:7687` (el nombre interno del contenedor — la IP
   pública del host da timeout desde dentro del contenedor; verificado en el deploy 2026-08-10).
   **Sin puertos públicos**: la webapp le hablará por la red interna.
3. Desde la **Terminal** del servicio en Dokploy: `python seed_users.py init` (una vez) — imprime las 5
   contraseñas UNA vez; distribúyelas por canal directo, no al Drive compartido, no a git.
4. Healthcheck del compose → `GET /health` (sin auth, sin red, sin spend). Verificación sin curl:
   `python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8078/health').read().decode())"`

## Las cuatro trampas heredadas (todas causaron incidentes reales)

1. **sklearn se precarga en el main thread** antes de aceptar tráfico (lifespan) — importarlo desde un
   worker deadlockea (el stall de 1800s del 2026-07-18/19).
2. **`EMBED_MODEL` pineado a `openai`** cuando hay `NEO4J_URI` (heredado al importar `server`); si
   deriva, se crea un índice de 768 dims contra un query path de 1536 y degrada en silencio.
3. **`.secrets/deploy.env` se carga en el import** — el contenedor debe traer los secretos o el
   servicio arranca en modo sparse(dev).
4. **Pool**: `DI_QUERY_POOL_SIZE=8` para 5 usuarios (el default 4 encolaba al quinto).

`--workers 1` es obligatorio: los cachés TTL in-process y la cola de escritura serializada (bloque 5)
asumen un solo proceso.

## Gate

`python rag_index/query_service/smoke_query_service.py` — offline (SQLite tmp, backend
monkeypatcheado, cero red / cero spend / cero mutación). Necesita `fastapi` + `sqlalchemy` (el
contenedor los trae; en dev cualquier venv desechable — **no** el `.venv` del MCP, ADR-0039).
Ratings + calibración: `python rag_index/query_service/smoke_ratings_calibration.py` (mismo régimen
offline; ADR-0064).

**Todos los gates del directorio** (`smoke_*.py`) corren offline con la máscara
`WITT_BACKEND_DB_URL="sqlite:///<tmp>/smoke-<nombre>.db" NEO4J_URI="" RAG_BACKEND=sparse OPENAI_API_KEY=""
ANTHROPIC_API_KEY=""` — cero red, cero modelo, cero mutación de `mcp_cache`. Los de ADR-0078 (
`smoke_zfin_tool.py` sirve el fixture REAL `fixtures/alliance_phenotypes_wt1a_20260913.json`;
`smoke_pubmed_tool.py`, `smoke_fetch_paper.py`, `smoke_search_queries.py`, `smoke_run_recovery.py`) se
corren junto a `smoke_run_pipeline.py` (que además integra los cinco en la corrida).

## Corridas (bloque 3, ADR-0049/0050)

Una corrida ejecuta: retrieve (la máquina de estados real de `answer_pipeline`, instrumentada por
`on_stage`) → síntesis (`claude-opus-4-8`) → gate determinista (`verify_output`) → **panel
composite-auditor** (Opus+Sonnet+Haiku+gpt-4o, 100% de las corridas) → `AUDIT_APPROVED|REJECTED` →
registro congelado en Postgres. Estados: `queued|running|awaiting_closure|closed|failed|cancelled`.
Gasto por corrida ~1–2.50 USD (medido en `usage`, sin caps — ADR-0047). Requiere `ANTHROPIC_API_KEY`
en el Environment del servicio. Gate: `smoke_run_pipeline.py` (181/181 offline; `smoke_query_service.py`
47/47). Contrato del registro: `render_contract_version 1.7` (ADR-0078: `+citations_schema`,
`+evidence_cited_raw`, `token_usage.{missing_price_models, cost_projection_complete}`; la vista de corrida
gana `claimed_by`/`claimed_at`/`failure_reason` — la webapp tipa los campos nuevos como opcionales, eso ES
la paridad front↔back). 1.6 (ADR-0067, adopción VB #2: **ciclo de
revisión acotado post-REVISE** — UNA pasada de corrección con los hallazgos del panel como insumo
tipado, re-gate determinista, re-auditoría terminal, tope DURO=1, kill-switch `WITT_REVISION_CYCLE=0`;
NADA se borra: `answer_initial`+`audit_initial`+`revision{...}`+`confidence.revision` persisten; la
traza puede llevar DOS `stage.audit.verdict` con `revision_round` 0|1 + `stage.revision.start` +
`stage.synthesize.revision`; el usage suma AMBOS paneles). 1.5 (ADR-0065: el escalar de confianza viene
de una **elicitación dedicada** post-síntesis — `confidence.source: "stated-second-elicitation"` — con
el instrumento in-line preservado en `pass1_inline`/`pass2_inline`, divergencia >0.15 declarada en
gap_flags y fallback §6 al camino ADR-0057 si la elicitación cae; medido en
`evaluation/scripts/ab_trapped_scalar.py`: in-line atrapado ~50–60% e insensible a prompts, elicitación
20/20 limpia con |delta| mediana ≤0.14). 1.4 (ADR-0061: `plan` congelado + `plan_declared` +
`plan_question_matches_run`, `agents_invoked` poblado desde el juicio del planner, y el gasto del plan
dentro de `token_usage` con su desglose `plan_judgment`). 1.3 (ADR-0060: los tres campos §5 que faltaban —
`reasoning.framework_applied` SELF-REPORT con sección/tier resueltos por tabla y la cita comprobada
contra el catálogo, `reasoning.structural_frameworks` derivados del código, `agents_invoked` derivado de
lo que corrió con el hueco del planner declarado `not-assessed`, y `alternatives_considered` con sus tres
estados). 1.2 (ADR-0057: `confidence.source` con procedencia
stated|recovered-from-malformed-tool-call|derived-min-of-subclaims; `path_b.query_sent/query_source` auditables). `/resolve` declara `taxonomy_axes.served: false` — los ejes por entidad derivan del grafo
(browse, Rack fase 2), nunca de esa puerta.

### Dos pasadas + decisor por confianza (bloque 4, ADR-0051)

**Ruta B multi-fuente (ADR-0059).** `PATH_B_SOURCES = ("europepmc", "pubmed", "zfin", "tooluniverse")`. `pubmed` (ADR-0062) es la misma
query por NCBI E-utilities con ranking propio y **dedup por PMID contra europepmc, declarado** — el SDK
en el contenedor se midió y se RECHAZÓ (la 1.2.6 pineada ni resuelve en py3.12; la última trae 173
paquetes con playwright/faiss/onnxruntime): la amplitud entra por Layer 0, y la escalación futura es un
sidecar, jamás pip install aquí. `zfin` es
la fuente NATIVA de pez cebra: símbolo → curie ZFIN → statements de fenotipo mutante/knockdown con sus
PMIDs (Alliance of Genome Resources, sin API key, cero gasto de modelo) — un tier de evidencia más
fuerte que literatura genérica para un claim de pronefros, y la tool ya vivía sin cablear en
`.tooluniverse/tools/`. Keys en **símbolos de gen**, no en query libre, así que `entities` viaja a
`path_b`. `path_b.zfin_searched` lleva una fila por símbolo intentado con estado explícito
(`success|no-match|error|skipped-budget|skipped-cap|tool-unavailable`): "busqué y no hay" jamás se ve
igual que "la búsqueda falló". Acotado por `WITT_ZFIN_BUDGET_S` (45) · `WITT_ZFIN_MAX_ENTITIES` (6) ·
`WITT_ZFIN_MAX_STATEMENTS` (12), y todo recorte se declara. `_search_tooluniverse` sigue devolviendo
`[]`: las tools del PAQUETE esperan el SDK. `path_b_bundle`/`path_b_event_payload` son el único
constructor del bloque y del evento (los dos disparadores no mantienen copias).

### Higiene de Ruta A y B (ADR-0078, 2026-09-14)

Lo que la auditoría 2026-09-13 midió: Ruta A entregaba **140 chars por hit** al sintetizador; la
Ruta B mandaba símbolos ANDeados como texto libre (`osr1 prkci pax2a` → PubMed 0, EPMC 1); el abstract
y el texto de cada paper se **bajaban y se tiraban**; ZFIN leía una llave muerta del payload de Alliance
(`references=[]` bajo `success`); PubMed sin `tool`/`email` ni pacing (NCBI: `X-RateLimit-Limit: 3`);
una excepción de EPMC mataba `path_b` entero; `evidence_cited` en string se iteraba por caracteres;
sonnet-5 cobraba 1.5×; una corrida `running` huérfana lo era para siempre. El bloque `path_b` declara
**`ledger_version: "2"`** y conserva sus llaves previas; los cambios de TIPO/DOMINIO que sí hay están
listados en el ADR (Consequences) y aquí: `query_sent: str → str|null`, `query_source` con literales
nuevos, `anatomy_filter` multi-raíz, `anatomy_filter_source` literal nuevo, contadores `int → int|null`.

**Corrector final (2026-09-14, tres revisiones cruzadas)** — lo que cambió respecto a la primera entrega
de la obra: (a) el correo de `WITT_NCBI_EMAIL` vive SOLO en el User-Agent — el ledger declara
`contact: "declared"|"unset"` (viajaba al bundle, a la API y al prompt de cinco modelos); (b) ZFIN:
`filter.termName=a|b` se midió **HTTP 400** en vivo — el tool ya no une raíces con `|` (una GET por raíz,
unión en cliente) y `server_filter` es **False por default** (`WITT_ZFIN_SERVER_FILTER=1` lo activa cuando
se mida la forma de una raíz); el respaldo cliente es por PREFIJO DE PALABRA (`\bduct` no casa
`reduction`); `n_phenotypes_total_scope: "gene"|"server-filtered"` declara qué total es; (c) UNA política
de anatomía para los tres índices (unión pregunta original + formulación EN, `notes.anatomy ∈
from-question|from-question-en|from-both|none-in-question` + `anatomy_text_source`); la pregunta original
JAMÁS se tokeniza como texto libre (sin símbolos ni EN → `empty` → `not-searched`); (d) contadores
`n_returned/n_new/n_candidates` son `null` cuando la fuente no corrió (not-searched / not-requested /
tool-unavailable / error) y `n_papers<=0` no dispara red (`not-requested`); `n_found` jamás se rellena con
el tamaño de página (`null` + `n_found_note`); (e) el reaper y el worker ya no se pisan: `db.finish_run`
(cierre `WHERE state='running'`, conflicto → evento `run.state.conflict`), el reaper exige que el latido
siga siendo el medido y deja `cancel_requested` para que un hilo vivo aborte; **al arrancar el proceso TODA
`running` cae a failed/worker-lost** (`reason: worker-lost-restart`); latido por juez (`stage.audit.judge`)
para que un panel legítimamente largo no rebase el umbral; `claimed_by = "<boot_id>:<pid>:<hilo>"`;
`WITT_REAP_STALE_S` vacía/basura → 900 declarado (ya no tumba el import); (f) citas: `evidence_cited`
ausente se declara `citations_schema.source: "absent"` (no se rellena con `[]`) y el re-parseo tiene UNA sede
(el registro ya no dice `list` junto a un `evidence_cited_raw` string); (g) `/usage`:
`cost_projection_complete` exige además `n_runs_cost_incomplete == 0` y declara `n_runs_cost_unknown`; (h) el
sintetizador y el panel reciben `path_b` PROYECTADO (evidencia y estados; sin `query_builder`, throttles,
`search_ledger` anidado, `dedup_keys`) — el bloque íntegro sigue en `bundle_json`; (i) el evento
`stage.path_b` gana un resumen por paper (`evidence_id, source, text_provenance, fetched.cache_hit/cached_at,
selection_rank`), `epmc_query` y `selection.not_selected` — lo que la Traza SÍ puede leer, porque el bloque
`path_b` no viaja en el registro congelado; (j) `text_cap_source`/`n_papers_source`/`retmax_source`
declaran la procedencia real del tope (`env:…` | `default-unset:…` | `default-invalid-env:…` | `caller`).

- **Ruta A**: cada hit viaja con hasta `WITT_PATH_A_CHARS` (2400) chars y declara su corte:
  `text_offsets [0,n]`, `text_sha256` del fragmento, `text_omitted`, `text_hit_chars`,
  `text_source: "index-hit"`; el tope efectivo va en `path_a.text_cap_chars`.
- **Queries por fuente** (`analysis/scripts/lib/search_queries.py`, determinista, `builder_version "1"`):
  `epmc_query` (`TITLE:/ABSTRACT:` + `MESH:"Zebrafish"` + anatomía), `pubmed_query` (`[tiab]`/`[mh]`),
  `zfin_filter` (raíces unidas con `|` SOLO como representación en el ledger; el tool las recibe como
  lista); `query_builder` completo con `inputs` (la formulación EN del sintetizador entra como
  `question_en`, `question_en_source: "synthesizer"`). Anatomía: UNA política para los tres índices —
  unión de la pregunta original y de `question_en`, procedencia en `notes.anatomy` y
  `notes.anatomy_text_source`; los términos de texto libre (`question_terms`) salen SOLO de `question_en`.
  `query_sent` sigue siendo la de EPMC (`query_sent_scope: "europepmc"`); `query_source` =
  `query-builder-v1:<symbols|question-only|empty>`. Query `null` = nada que buscar → fuente
  `not-searched`, jamás cadena vacía.
- **`europepmc_searched`** (nuevo): `status ∈ success|no-match|error|not-searched|not-requested|
  tool-unavailable`, `query_sent`, `n_found` (hitCount, medición; `null` + `n_found_note` si el payload no
  lo trae), `n_returned`/`n_candidates` (`int` solo en success|no-match; `null` si la fuente no corrió),
  `retmax_sent`, `elapsed_s`, `throttle`, `throttle_slept_s` (de ESTA llamada), `contact:
  "declared"|"unset"` (estado, jamás el correo), `error?`. Una caída deja `error` y la corrida sigue (§6).
- **Pool + dedup + selección**: `WITT_PATH_B_RETMAX` (20) candidatos POR fuente; dedup por PMID, PMCID y
  DOI normalizado (lower, sin `https://doi.org/`); `WITT_PATH_B_N_PAPERS` (5) elegidos con
  `selection.rule = "oa-with-pmcid-first, then source order"`; `selection` lleva `n_requested`,
  `n_candidates`, `n_selected`, `n_duplicates`, `duplicates[{duplicate, of, matched_key, source}]`,
  `not_selected[]`. Solo los elegidos se bajan. `n_papers_requested`/`retmax_requested` en el bloque.
- **Contenido al bundle** (cada paper): `abstract`, `text_excerpt` (≤ `WITT_PATH_B_EXCERPT_CHARS` 1500),
  `text_provenance ∈ abstract|fulltext-excerpt|none`, `text_excerpt_rule ∈ full|head|
  top-paragraphs-by-lexical-overlap|none` (párrafos con más términos de la query, en orden del
  documento), `text_excerpt_chars`, `text_excerpt_omitted`, `text_source_chars`, `selection_rank`,
  `dedup_keys`. `fetched` gana `cache_hit`, `cached_at`, `cached_at_source`, `cache_age_days`,
  `fetched_at`, `search_ledger` SOLO cuando el fetch los midió (ausente ≠ false).
- **`pubmed_searched`** gana `query_sent`, `retmax_sent`, `n_returned`, `n_candidates`, `n_new` (los tres
  `int|null`: `null` cuando la fuente no corrió), `duplicates_of_europepmc: list|null`, `ncbi_identity`
  (`declared|missing`), `throttle{host, min_interval_s, min_interval_source, api_key_present, waited_s}`,
  `retries_429`, `rate_limit_headers` (de UNA respuesta, la última que las trajo) +
  `rate_limit_headers_from: esearch|esummary|null`, `http_status` (en error); `status` gana
  `not-searched` y `not-requested`.
- **`zfin_searched[]`** gana el estado `success-no-references` (statements sin PMIDs parseables ≠ error),
  `references_schema ∈ pubmedPublications|pubmedPubModIDs|none|mixed`, `phenotypes_capped_at_300`,
  `references_truncated`, `n_returned_by_api`, `statements_truncated`, `anatomy_terms`,
  `anatomy_filter_mode ∈ none|client|server+client` (default `client`), `anatomy_filter_semantics`,
  `n_phenotypes_total_scope ∈ gene|server-filtered`, `n_http_gets`, `server_filter_totals?`,
  `timeout_s` (= min(10, presupuesto restante / 2)) + `timeout_s_scope: "per-http-get"`, `detail?`
  (cero producido por el filtro del servidor); el item `zfin` lleva `status`, `has_references` y los
  mismos campos.
- **Modelo de corrida**: `claimed_by` (`"<boot_id>:<pid>:<hilo>"`)/`claimed_at` en lista y detalle;
  `failure_reason ∈ worker-lost|pipeline|null` en la vista; al ARRANCAR el proceso toda `running` cae a
  `failed` (`reason: worker-lost-restart`), y el hilo `run-reaper` pasa a `failed` con `error:
  "worker-lost: sin latido por >N s (ADR-0078)"` toda `running` sin latido por `WITT_REAP_STALE_S`
  (900 = 3× el umbral de la vista; vacía/basura → 900 declarado; nunca re-encola; la segada queda con
  `cancel_requested` para que un hilo vivo aborte); el worker cierra con `db.finish_run` (`WHERE
  state='running'`) y si la fila ya no es suya deja `run.state.conflict` en vez de pisarla; el panel emite
  un latido por juez (`stage.audit.judge`). El registro congelado gana `citations_schema{source ∈
  list|string-reparsed|string-unparseable|absent|unsupported-type, n_raw, n_valid}` (un `evidence_cited`
  AUSENTE se declara `absent`, no se rellena con `[]`) y `evidence_cited_raw` (`null` = no llegó string);
  `token_usage` gana `missing_price_models[]` y `cost_projection_complete` (un modelo sin precio se
  EXCLUYE y se declara, jamás cotiza 0); `/usage` idem + `n_runs_cost_incomplete`, `n_runs_cost_unknown`
  y `by_model[m].estimated_cost_usd: null` con `price_state: "missing"` — `cost_projection_complete` es
  `true` SOLO sin modelos sin precio Y sin corridas congeladas incompletas. Precios: sonnet-5 (2.0, 10.0);
  consejo en tabla; `PRICES_AS_OF "2026-09"`.

**Variables de entorno nuevas (ADR-0078)** — default declarado en código; el valor efectivo viaja en el
bundle/ledger:

| Variable | Default | Dónde se lee | Efecto |
|---|---|---|---|
| `WITT_PATH_A_CHARS` | 2400 | `answer_pipeline.path_a` | chars por hit de Ruta A al bundle/sintetizador |
| `WITT_PATH_B_N_PAPERS` | 5 | `answer_pipeline.path_b(_bundle)` | papers de literatura seleccionados (top-n) |
| `WITT_PATH_B_RETMAX` | 20 | `answer_pipeline` · `pubmed_literature.resolve_retmax` | candidatos pedidos a cada fuente |
| `WITT_PATH_B_EXCERPT_CHARS` | 1500 | `answer_pipeline._paper_content` | tope del `text_excerpt` |
| `WITT_NCBI_EMAIL` | — (sin default) | `pubmed_literature` · `fetch_paper` (UA) | `email=` a E-utilities y contacto del UA; si falta NO se inventa: `ncbi_identity: "missing"` / `contact: "unset"` |
| `NCBI_API_KEY` | — (ya existía) | `pubmed_literature` | sube el límite de NCBI; deriva el intervalo 0.10 s |
| `WITT_NCBI_MIN_INTERVAL_S` | derivado: 0.34 sin llave / 0.10 con llave | `pubmed_literature.resolve_min_interval_s` | pacing por proceso en `eutils.ncbi.nlm.nih.gov` (`throttle.min_interval_source: env|derived`) |
| `WITT_EPMC_MIN_INTERVAL_S` | 0.2 | `fetch_paper` | pacing por proceso en `www.ebi.ac.uk` |
| `WITT_CACHE_TTL_DAYS` | 7 | `fetch_paper.fetch_external` | caché de LECTURA de `raw_paper_*.json` (`cache_hit` declarado; ≤0 = nunca confiar) |
| `WITT_REAP_STALE_S` | 900 | `runs.REAP_STALE_S` (import, tolerante: vacía/basura → 900 declarado; `REAP_STALE_S_SOURCE`) | segador de `running` huérfanas; el hilo repite cada N/3 s; al arrancar se siega TODA `running` (umbral 0) |
| `WITT_ZFIN_SERVER_FILTER` | 0 | `answer_pipeline._search_zfin` | 1 = una GET `filter.termName=<raíz>` por raíz en Alliance (sin medir en vivo; `a|b` = HTTP 400 medido); 0 = filtro cliente por prefijo de palabra |

El throttle es de PROCESO (`lib/net_throttle.py`, `--workers 1` obligatorio): si algún día el servicio
corre en varios procesos o réplicas, el pacing deja de cubrirlos — frontera documentada, no supuesto oculto.
Con `WITT_NCBI_EMAIL` sin fijar en Dokploy, cada corrida declarará `ncbi_identity: "missing"` (correcto y
visible). Gates (tras el corrector): `smoke_run_pipeline.py` 181/181 · `smoke_zfin_tool.py` 26/26 ·
`smoke_pubmed_tool.py` 32/32 · `smoke_fetch_paper.py` 41/41 · `smoke_search_queries.py` 163/163 ·
`smoke_run_recovery.py` 40/40.

Pass 1 es SIEMPRE DI-only (mide "¿mi store alcanza?"); si `pass1 < τ` (`WITT_FALLBACK_CONF_TAU`,
default 0.5) o la confianza viene ausente, dispara la Ruta B y corre pass 2 con la evidencia externa —
ambas confianzas + el **delta** quedan en el registro (`confidence {pass1, pass2, delta, by_subclaim,
state}`), junto con `fallback.trigger` (structural|confidence), `absence_kind`, citas tipadas
(`citations[{n, kind, id}]`) y `token_usage` (by_model medido, embeddings incluidos, costo etiquetado
como proyección). `render_contract_version: 1.1`.

## Pendiente

(Actualizado 2026-08-22 — la lista previa estaba una época atrás: el plan de M3 es ADR-0061, el
precedente + series disjuntas ADR-0053, y el bloque 5 del ingest ADR-0052/0054.)

- **Escalar atrapado: RESUELTO Y CONFIRMADO EN VIVO** (ADR-0065 + piloto v2 de ADR-0072, 2026-08-22:
  2/2 corridas reales por el código de producción salieron `stated-second-elicitation` limpio, cero
  recuperación regex). Verificación operativa restante: la primera corrida de witt-ai.com.mx tras
  el Redeploy.
- **Tapón 5 — evals periódicas**: el instrumento YA existe (`evaluation/run_held_out_v2.py` sobre el
  run model, ADR-0072, contra `evaluation/EVAL_DESIGN.md`); falta el cron + umbrales + volumen de
  etiquetas humanas (ratings M5, ADR-0064).
- Correo M9 (Resend — necesita cuenta) · 2ª etapa de curación (agentes-lectores EPMC, plantilla
  ADR-0068, tras validar F4 del barrido ZFIN).

(Resuelto 2026-08-22 también: PDF de servidor M4 = ADR-0073, `GET /runs/{id}/record.pdf`.)

(Resueltos 2026-08-22: la consulta abierta = ADR-0070 (`GET /consulta-sistema`, determinista v1) ·
la normalización de metadata §5.9 = ADR-0069 · el browse del grafo = ADR-0071
(`GET /rack/node/{id}`, verificado EN VIVO contra el Neo4j real).)
- PDF server-side (M4) · correo M9 (Resend) · poblar el precedente (corridas cerradas reales).

(Resuelto 2026-08-22 por decisión de Emmanuel — ADR-0064: `failed`/`cancelled` son estatus terminales
aparte, jamás precedente ni ECE; `close_run` se queda solo con `awaiting_closure`. No era pendiente de
código: el comportamiento actual es el decidido.)

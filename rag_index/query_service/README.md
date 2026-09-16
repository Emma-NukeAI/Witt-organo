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
| POST | `/runs/plan` | ✓ | **el plan declarado** (ADR-0061; **plan v3** por ADR-0066): estructura del código + juicio del planner (nichos §3 + agentes §11 con gate resuelto por tabla + **0-3 `clarifying_questions` never-stopper**) + **`data_landscape`** estructural (preview DI sparse NO-SPEND + qué fuentes Ruta B aplican) + estimaciones DETERMINISTAS por métrica. Se refiere por `plan_id`; se consume UNA vez (409 `plan_already_used`). **`parent_run_id`** (ADR-0079): el planner recibe el `thread_context` del padre (armado en el servidor); la respuesta declara `thread_context_passed` / `thread_context_skipped_reason`. **ADR-0082 (E.3)**: si `WITT_COUNCIL=1` ∧ `judgment.state 'declared'` ∧ `route 'evidence-run'` ∧ `niches ≠ []` ∧ `origin ∈ WITT_COUNCIL_ORIGINS`, ENCOLA la ronda 1 del consejo como JOB del plan (`council.state 'queued'`, `poll`/`events`/`stream`, `budget`, `estimate` [E]); si no, `council.state 'not-requested (…)'` \| `'disabled (kill-switch WITT_COUNCIL=0)'` con la razón; dedup del doble clic (`plan_response 'reused'`, `reused_from_plan_id`, ventana `WITT_COUNCIL_DEDUP_S`; el dedup se RE-CONSULTA tras el planner: dos POST idénticos concurrentes → UN job, el segundo `reused_after_planner true` — corrector) y tope `WITT_COUNCIL_MAX_QUEUED_PER_USER`; el plan es **v4** (`will_run 'council-member'`) |
| POST | `/runs` | ✓ | encola una corrida (async); terminal SIEMPRE post-audit (ADR-0049). **409 `index_offline`** si el índice está OFFLINE — bloquea, no degrada (dev sparse: `WITT_ALLOW_RUNS_OFFLINE=1`). **`parent_run_id`** (ADR-0079): el turno siguiente de una investigación — 404 `parent_not_found` · 409 `parent_not_terminal` (queued/running); `thread_id`/`turn_no`/`turn_kind`/`origin`/`thread_context` los deriva el SERVIDOR, jamás el cliente. **ADR-0082 (F.3)**: con `plan_id` exige la puerta del consejo — 409 `council_round1_pending` mientras la ronda 1 está `queued|running`, 409 `council_ledger_unapproved` con r1 `applicable|incomplete` sin ledger aprobado ni saltado (`errored`/`not-requested`/`disabled`/`pre-adr-0082` NO bloquean); 409 `plan_already_used {run_id, cancelled_run_id}` si OTRA corrida selló el plan entre la lectura y el sello (la perdedora queda `cancelled` por `server` con razón — corrector); el servidor compone `runs.council_json` (r1 + ledger + membresía CONGELADA) al encolar; la vista gana `plan_council_state` y `council_n_valid` |
| GET | `/plans/{plan_id}` | ✓ | **el plan declarado y su ronda 1** (ADR-0082 (E.3)): `plan`, `origin`, `council_state` (vocabulario `council.COUNCIL_STATES_*`; NULL = `pre-adr-0082`), `council` (= `plans.council_json`: r1 + agregación + requisitos SIN decisiones), `ledger`, `council_usage`, `approved_by/_at/_is_author`, `council_claimed_by/_at`, `heartbeat_age_s`/`heartbeat_stale` (300 s), `run_gate {allowed, reason}`, `poll`/`events`/`stream`; 404 `plan_not_found` |
| GET | `/plans/{plan_id}/events?after=` | ✓ | **replay de la traza del PLAN** (tabla `plan_events`, espejo de `run_events`, `agent 'council'`): `council.state` → `stage.council.member` ×N → `stage.council.progress` (latido ≤ 30 s) → `stage.council.round` → `stage.council.aggregate` → `council.ledger` / `council.skip` (+ `council.state.conflict` si el worker sobrevivió a la siega del reaper: el estado terminal no se pisa — corrector); 503 `council-db-unavailable` si la BD no tiene las columnas del ADR |
| GET | `/plans/{plan_id}/stream?after=` | ✓ | la misma traza por SSE (keep-alive 15 s); cierra con `event: end {council_state}` en estado terminal (`∉ {queued, running}`) |
| POST | `/plans/{plan_id}/council/ledger` | ✓ | **la ÚNICA puerta donde la prosa del consejo se vuelve gasto** (ADR-0082 (F.1)): body `{decisions[] {requirement_id, decision keep\|discard\|aporto, reason? (obligatoria con discard), attested_text? (obligatorio con aporto, ≤ `WITT_COUNCIL_ATTESTATION_CHARS`)}, knowledge_now?, approve}` → `ledger` (`draft`\|`approved`; `pending` no hard-rule → `keep` con `decided_by 'default-keep'`; `decided_by 'human:<user>'`, `approved_by_is_author`). 400 `hard_rule_requirements_undecided` (§7.1: `causal-pruner` exige decisión EXPLÍCITA) · `unknown_requirement_id` · `duplicated_requirement_id` · `invalid_decision` · `discard_without_reason` · `aporto_without_text` · `attested_text_too_long` · `knowledge_now_too_long`; 409 `council_not_terminal` (r1 viva) · `council_ledger_not_applicable` · `plan_already_used`; 404 `plan_not_found` |
| POST | `/plans/{plan_id}/council/skip` | ✓ | `{reason}` → `council_state 'skipped-by-human'` con autor y hora (la corrida sale con ledger VACÍO declarado; el sistema jamás salta solo); 400 `skip_without_reason` |
| GET | `/council/membership` | ✓ | **NO-SPEND, sin BD**: `agent_matrix.membership_view` (cm-1: 17 miembros con `group`/`mode`/`tool`/`gate`/`card_sha`, 8 `not-applicable-by-category`, 9 sustrato con estado, 3 filas sin ficha) + `vocabulary` (= `council.council_vocabulary()`, el que el gate (F) de paridad compara con `types.ts`) + `catalog_sha`/`rules_sha`/`shared_block_sha`/`cache` |
| GET | `/council/search?q=&k=&include_origins=&kinds=` | ✓ | **el índice del consejo** (ADR-0082 (I), patrón `precedent`): requisitos, coberturas, DECISIONES humanas (sin la razón), gap_flags, alternativas, hallazgos del panel y comentarios (sólo con `kinds=comment`) de corridas CERRADAS + planes con `council_json` del alcance de origen; letras `A..`, `admissible_as_evidence false` estructural, `scorer` declarado, `corpus_state`; 400 sin `q` / kind fuera del enum · 503 `council-index-disabled` (`WITT_COUNCIL_INDEX=0`) |
| GET | `/council/demand?include_origins=` | ✓ | el criterio MEDIDO de disparo de los sidecars ADR-0083/0084/0085: requisitos `unsatisfiable-by-harness` por familia (`web`, `tooluniverse`, `figure`), umbral `{min_runs 5, min_requirements 3}`, `fired_by_family`, `fired`; clase medición; independiente del kill-switch del índice |
| GET | `/runs` · `/runs/{id}` | ✓ | lista y detalle por la MISMA vista: `heartbeat_age_s` + `heartbeat_stale` + `heartbeat_stale_after_s` (el umbral viaja) + `token_usage` (gasto en TODO camino de salida, failed/cancelled incluidos) + **`run_no`** (ADR-0076: el NÚMERO de corrida — identidad legible asignada al nacer; las anteriores a la columna se numeraron por orden de creación al arrancar) + **columnas de investigación** (ADR-0079: `parent_run_id`, `thread_id`, `turn_no`, `turn_kind`, `origin`, `root_question_id` — NULL = anterior al contrato, sin backfill). **`GET /runs?thread=<thread_id>&limit=&after=`** lista los TURNOS de una investigación (orden `turn_no ASC`, sin el tope 50, cursor `after` = turn_no exclusivo, `has_more` medido, `next_after`); la lista general declara `limit`/`limit_cap`. **`root_run_no`** (ADR-0081 (F)): nace en la BD por JOIN a la raíz (`db._list_select`/`db.get_run`, UNA definición) — lista, detalle, `POST /runs` y `/runs?thread=` la traen; raíz = su `run_no`; `null` = corrida anterior a ADR-0079, declarado, jamás rellenado |
| GET | `/threads/{thread_id}` | ✓ | **la investigación T-<run_no raíz> como UNA unidad** (ADR-0079): `turns[]` en orden con veredicto/decision_state/origin/costo por turno, `gap_flags_union` (conteos con igualdad normalizada, jamás prosa nueva), `total_cost_usd` PROYECCIÓN con `complete`, `pivot_suggested` (regla `WITT_PIVOT_TURNS` declarada), `origins`, `authors`, `root_pre_adr_0079` (raíz virtual anterior al contrato); 404 `thread_not_found` |
| GET | `/threads?mine=&limit=&after=` | ✓ | **el índice de investigaciones** (ADR-0081 (G); declarada ANTES de `/threads/{thread_id}`): UNA consulta `GROUP BY thread_id` con la raíz por JOIN — `label 'T-<n>'`, `root_run_no`, `n_turns` (IGUAL al de `/threads/{id}`: la raíz virtual cuenta +1, `root_counted` lo declara), `n_closed`, `n_with_record`, `last_turn`, `authors`, `origins`, `states`, `root_pre_adr_0079`; orden `root_run_no DESC NULLS LAST`, cursor `after` = `root_run_no` EXCLUSIVO, `has_more` MEDIDO (`limit+1`), `limit_cap` 50, `mine` (≥ 1 turno del usuario; `mine_rule`), `n_threads_total`, `n_runs_without_thread` del SERVIDOR; sin costo agregado (`costs 'not-aggregated (GET /threads/{id})'`); `limit < 1` → 400 |
| GET | `/runs/{id}/record` | ✓ | el **registro congelado** que la UI renderiza (una fuente, tres lectores) |
| GET | `/runs/{id}/record.pdf` | ✓ | **el PDF de servidor** (M4, ADR-0073): generado DEL JSON congelado con plantilla propia — jamás "imprimir la página"; bandas con palabras completas, procedencia del escalar en palabras, ambas rondas de la revisión, identidad rota = 409; el ÚNICO canal autorizado de exportación. **ADR-0083 (J)**: RE-ESTRUCTURADO por TABLA (`record_pdf.SECCIONES` + `KEY_BORN`): CADA llave top-level del registro tiene sección espejo con TRES estados y el contrato de nacimiento CALCULADO (`NO INSTRUMENTADO (contrato < 1.10)` para `models` en un 1.9 — hoy imprimía `< 1.8`, falso — · `null declarado — razón: <state>` · valor), las 23 líneas `[pdf]` de la paridad (models, audit.quorum, by_stage.panel.by_model, search_ledger por fuente, los 5 literales de `citations_schema.source` en 5 frases DISTINTAS, deterministic_checks, agents_invoked, …) se saldan, la regla del sha del padre se LEE de `thread_parent_matches_run_rule` (no prosa fija), sección FIGURAS (1.12) con MINIATURA sólo si `embeddable` (congelado ∧ permitido por `WITT_FIGURES_EMBED_LICENSES` de HOY — la misma puerta que el 403 del GET, *corrector*) ∧ bytes en caché ∧ sha recalculado == sha ∧ `WITT_FIGURES_PDF_THUMBS=1` (≤ 60 mm, ≤ 12 por PDF, PDF ≤ 8 MB — degradación declarada), y un gate de COBERTURA (`smoke_record_pdf.py`, `pdf_sections_cover`) que FALLA si una llave del frozen real no tiene sección. El PDF jamás toca la red |
| GET | `/runs/{id}/figures` | ✓ | **el índice de FIGURAS del registro** (ADR-0083 (I); declarada ANTES de `/runs/{run_id}/events`, patrón `record.pdf`: membresía antes del filesystem — F5 la implementó; F8 la midió el 2026-09-16: `smoke_figures_http.py` 42/42): 401 · 404 corrida · 409 `{state, note 'no frozen record yet'}` · 409 identidad (`question_matches_run false`, misma regla que `record.pdf`) · 200 `{run_id, run_no, render_contract_version, state, frozen_state, n, n_verified, n_embeddable, n_servable, servable_counts, license_table_version, cache {dir_source, dir_state}, items[], class, servable_rule, vocabulary {SERVABLE_STATES}, kill_switch?}` *(corrector: la forma REAL de `app.get_run_figures`; `cache.dir_state` se MIDE sin crear el directorio — una GET jamás escribe, 'missing' es estado declarado)* — cada ítem = `FigureItem` SIN `b64` NI `cache_path` + `servable` como OBJETO `{state ∈ yes \| forbidden-by-license \| bytes-not-in-cache \| bytes-mismatch \| kill-switch \| no-bytes, reason?, sha256_actual?}` (MEDIDO al pedir: existencia + sha RECALCULADO; `reason 'restricted-by-env-now (WITT_FIGURES_EMBED_LICENSES)'` cuando la env de HOY restringe una licencia congelada embebible) + `url '/runs/{run_id}/figures/{sha256}'`; registro < 1.12 → `{state 'not-instrumented (contrato < 1.12)', items []}`; `WITT_FIGURES=0` → `state 'kill-switch WITT_FIGURES=0'`. Ninguna GET toca la red |
| GET | `/runs/{id}/figures/{sha256}` | ✓ | **los bytes ORIGINALES de UNA figura, fuera del registro** (ADR-0083 (I), ADR-0074): `{sha256}` validado `^[0-9a-f]{64}$` (400) → se busca en `frozen.figures.items` → 404 `{state 'no such figure in this record'}` · 403 `{state 'forbidden-by-license', license {id, words_es, source}, source_url}` si `embeddable False` (NC/ND, `unknown`, ZFIN) · 404 `{state 'bytes-not-in-cache', source_url, sha256, refetch 'disabled (WITT_FIGURES_REFETCH_ON_GET=0)' \| 'attempted: <estado>'}` (caché EFÍMERA sin volumen — E4; con `REFETCH_ON_GET=1` UNA GET y se sirve SOLO si sha == congelado, si no 409) · 409 `{state 'figure-bytes-mismatch', expected, actual}` si el sha recalculado del archivo ≠ (JAMÁS se sirve) · 200 bytes con `Content-Type` = `media_type` medido, `ETag "<sha256>"`, `Cache-Control: private, max-age=86400`, `X-Witt-Figure-License`, `X-Witt-Figure-Sha256`, `Content-Disposition: inline; filename="<PMCID>_<fig_id>.<ext>"`; kill-switch → 404 `{state 'kill-switch WITT_FIGURES=0'}`. **CORS**: `expose_headers` = las 5 de `app.FIGURE_EXPOSE_HEADERS` — `ETag`, `X-Witt-Figure-License`, `X-Witt-Figure-Sha256`, `X-Witt-Figure-Refetch` (aditiva: sólo viaja tras un refetch verificado) y `Content-Disposition` *(corrector: forma real)* (sin ello la webapp no lee los headers); la webapp baja por `fetch` con bearer → blob (`URL.revokeObjectURL` al desmontar), JAMÁS `<img src="/runs/…">` directo (no manda `Authorization`) |
| GET · POST | `/runs/{id}/comments` | ✓ | **los COMENTARIOS de la corrida** (ADR-0077): la conversación del equipo sobre la pregunta — anexo append-only y público (toda sesión lee y escribe; sin PATCH ni DELETE), fuera del registro congelado, de M5 y de los apuntes; autor y hora los pone el servidor; `body_max` declarado (4000); `n_comments` viaja en toda vista de corrida |
| GET | `/runs/{id}/events?after=` | ✓ | **replay** — las mismas filas que el stream (una bitácora) |
| GET | `/runs/{id}/stream` | ✓ | traza viva SSE (keep-alive; cierra al drenar un estado terminal) |
| POST | `/runs/{id}/cancel` | ✓ | body `{reason}`; registra `cancelled_by` (sesión) + `cancel_reason` — una cancelación sin autor es un hueco en el registro (ADR-0055). Queued: inmediato; running: frontera de etapa |
| POST | `/runs/{id}/close` | ✓ | cierre explícito: congela el registro (`frozen_at`) — requisito para precedente |
| GET | `/usage?from=&to=` | ✓ | agregados M8 en el SERVIDOR: totals/by_user/by_model/most_expensive; tokens [M], costo PROYECCIÓN con `cost_class`; `rack_embeddings` aparte con su caveat (ADR-0056). **ADR-0081 (H)**: `by_stage` (tokens por etapa — `n_runs_measured`/`n_runs_null`, `states`, `model_split`, USD SÓLO cuando todos los tokens tienen precio; si no `null` + `price_state ∈ priced | missing | mixed | stage-without-model | not-measured` — `not-measured` = etapa sin ninguna corrida medida en el periodo, USD null jamás 0.0 (corrector)), `by_model_stage` (+ `_unattributed.panel` de registros 1.9, jamás repartido), `by_model_stage_coverage`, `n_runs_without_by_stage` (pre-1.9 ≠ gasto cero), `models_catalog`, `by_model[].family/known`, `model_generation_current`; `totals/by_user/most_expensive` sin cambio. **ADR-0082 (H)**: `by_stage` gana `council_r1/r2/r3` iterando `TOKEN_STAGES` (sin código nuevo), `by_model[m] += cache_creation, cache_read` (tokens) y **`plans_council`** = el gasto de rondas 1 de planes que NUNCA se corrieron (`n_plans`, `n_unconsumed`, tokens, `cache {creation, read, multipliers}`, `estimated_cost_usd` [E] con `price_state`, `by_state {<council_state>: n}`, `by_model`) — sin él M8 no cuadra. **ADR-0083 (H)**: `figures {n_runs_with_figures, n_figures_verified, n_figures_cited, bytes_downloaded, vision_tokens_projected_by_model {model: n}, class 'PROJECTION (tokens) / MEASUREMENT (counts, bytes)'}` — bloque APARTE del medido (M8 lo pinta aparte; cierra el hueco HANDOFF §17.3) |
| GET | `/config-history` | ✓ | historial de config verbatim + procedencia; históricos de usuarios/store DECLARADOS (ADR-0056). **ADR-0081 (I)**: `entries` (archivo, clase ATESTIGUADA — incluida `budget_approval`) + `ledger[]` (tabla `config_history`: MEDICIÓN del diff de configuración al arrancar, `changed_by 'system:boot-diff'` / `'system:runtime-diff'`, `actor_state` declarado) + `ledger_state ∈ ok | kill-switch WITT_CONFIG_LEDGER=0 | table-missing | error: <tipo> | not-booted (lifespan no corrió: config_ledger.boot() no se ha llamado)` (el quinto = antes del lifespan; un TestClient sin lifespan lo ve — corrector) + `ledger_writer` / `ledger_encoding` / `ledger_scope_rule` + `current {fields {value, source}, warnings, unknown_models}` + `provenance.db` |
| GET | `/consulta-sistema?q=` | ✓ | **la consulta abierta** (ADR-0070): la pregunta META respondida — inventario por secciones con fuente declarada (store/índice/corpus/taxonomía/corridas/config/cuarentena) + `resumen` en lenguaje natural compuesto por CÓDIGO; `model_consulted: false` estructural; ruteo por palabras clave con no-match declarado; NO-SPEND |
| GET | `/rack/node/{id}` | ✓ | **el browse del grafo** (ADR-0071, Rack fase 2): documento/entidad/nicho/base con sus aristas (MENTIONS lleva `verified_tier_weight` por arista) + **ejes POR ENTIDAD derivados** (la puerta que /resolve declara nunca servir); `browse_mode` in-band (graph \| files-fallback declarado, §6); NOT_FOUND = 200 found:false; el embedding jamás se serializa; NO-SPEND |
| GET | `/precedent/search?q=&k=` | ✓ | **la capa de precedente** (ADR-0053): corridas CERRADAS por relevancia, `admissible_as_evidence: false` estructural, scorer declarado; series de citas disjuntas (números=evidencia, letras=precedente). **`include_origins`** (CSV, ADR-0079): por default SOLO origin `production` (+ pre-ADR NULL, incluidas y declaradas); la respuesta trae `origins_included` / `excluded_by_origin` / `origin_unknown_included`; fuera del enum = 400 |
| POST | `/runs/{id}/ratings` | ✓ | **calificación M5** (ADR-0064): append-only (una corrección = fila nueva), procedencia DERIVADA de la sesión (`is_author`/`rater_profile`/`instrument`, jamás del cliente), ejes 1-5 con `[?]` explícito (`cannot-rate`/`not-applicable` — nunca un 1); solo corridas terminadas (409 en queued/running) |
| GET | `/runs/{id}/ratings` | ✓ | ratings + consenso con la **independencia M5 aplicada en el servidor**: scores ajenos enmascarados hasta que emitas el tuyo; el consenso cuenta sin promediar (`{invited, received, open, missing}`) |
| GET | `/ratings/pending` | ✓ | la cola "PENDIENTES DE CALIFICAR" del usuario de la sesión, con consenso y resumen epistémico por fila |
| GET | `/calibration` | ✓ | **ECE sobre corridas CERRADAS anclado en ratings humanos** (tapón 4, ADR-0064): reutiliza `compute_ece.py`, mapeo de outcomes DECLARADO en la respuesta, poder declarado (`n<10` = case capture, descriptivo, jamás un número ciego; `n>=10` agrega isotonic), desglose médico/dev; NO-SPEND. **`include_origins`** (CSV, ADR-0079) con la misma declaración de alcance que el precedente (también en `GET /notes/questions/calibration`) |

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
corren junto a `smoke_run_pipeline.py` (que además integra los cinco en la corrida). Los de ADR-0079 —
`smoke_threads_db.py` (39/39, la capa de datos), `smoke_thread_context.py` (35/35, runs.py),
`smoke_runs_thread_http.py` (51/51, la puerta por ASGI TestClient) — más los ampliados `smoke_precedent.py`
(28/28) y `smoke_ratings_calibration.py` (44/44), y la sección ADR-0079 de `smoke_run_pipeline.py` (211/211)
que integra las cinco rebanadas. Todos fijan `WITT_RUN_ORIGIN=smoke` y piden `include_origins=smoke` explícito
cuando el check depende de sus propias corridas cerradas (el default `production` se prueba comprobando que
quedan CONTADAS fuera). Los de ADR-0080 — `smoke_competence.py` (27/27, la compuerta y su cableado),
`smoke_search_harness.py` (45/45, plan/rondas/presupuesto/dedup/no-re-ejecución), `smoke_tools_a.py` · `smoke_tools_b.py` ·
`smoke_tools_c.py` (45/45 · 69/69 · 68/68, las 10 tools Layer 0 sobre sus fixtures REALES del 2026-09-15 con `_get`
monkeypatcheada; transversal: CERO correos en `fixtures/`), `smoke_gate_citations.py` (48/48, predicado + escalera + reintento) — y la sección ADR-0080 de
`smoke_run_pipeline.py` (238/238), que además MIDE que la sección no toca la red (urlopen bloqueado y contado) ni
`mcp_cache`. Los de ADR-0083 — `smoke_figures.py` (NUEVO: parser JATS golden, licencia por reglas, fetch con el zip
fixture y `_get_bytes` falseada, caché TTL/LRU, selección para el panel, bloques por transporte), `smoke_panel_vision.py`
(NUEVO), `smoke_figures_http.py` (NUEVO), `smoke_record_pdf.py` (NUEVO — el gate de COBERTURA del PDF) — y los tocados
(`smoke_gate_citations.py`, `smoke_run_pipeline.py`, `smoke_models.py`, `smoke_openai_responses.py`, `smoke_panel_quorum.py`,
`smoke_usage_http.py`, `smoke_fetch_paper.py`) añaden a la máscara **`WITT_MCP_CACHE_DIR=<tmp>`**: los bytes de figura de
los gates van a una caché TEMPORAL, `mcp_cache/` real queda byte-idéntico y `urlopen` = 0 (sección ADR-0083 más abajo). **F8 (2026-09-16): los 41 `smoke_*.py` del directorio
corren exit 0 con la máscara — UNA `.db` y un `WITT_MCP_CACHE_DIR` temporal NUEVO por smoke —; `figures.attach` mide el dir de caché sin
crearlo cuando no hay nada que bajar (caché perezosa), así que un gate sin la variable tampoco deja `<repo>/mcp_cache/figures/`; `mcp_cache/`
byte-idéntico antes/después (372 archivos, `*.log` excluidos).**

## Corridas (bloque 3, ADR-0049/0050)

Una corrida ejecuta: retrieve (la máquina de estados real de `answer_pipeline`, instrumentada por
`on_stage`) → síntesis (`claude-opus-4-8`) → gate determinista (`verify_output`) → **panel
composite-auditor** (Opus+Sonnet+Haiku+gpt-4o, 100% de las corridas) → `AUDIT_APPROVED|REJECTED` →
registro congelado en Postgres. Estados: `queued|running|awaiting_closure|closed|failed|cancelled`.
Gasto por corrida ~1–2.50 USD (medido en `usage`, sin caps — ADR-0047). Requiere `ANTHROPIC_API_KEY`
en el Environment del servicio. Gate: `smoke_run_pipeline.py` (211/211 offline; `smoke_query_service.py`
47/47). Contrato del registro: `render_contract_version 1.8` (ADR-0079: `+thread {thread_id, parent_run_id,
turn_no, turn_kind, parent_state, parent_run_no, root_question_id, root_run_no, context_delivery}`, `+thread_context`
(el snapshot que el modelo VIO | null + `thread_context_skipped_reason`), `+thread_parent_matches_run` (+`_state`,
+`_rule`), `+precedent_citations` (letras `l`, `admissible_as_evidence false`), `+origin {value, source}`,
`+episode_axes {world, inference, technical, provenance}`, `deterministic_checks.{thread, parent_identifier_leak,
disjoint_series}`; `epistemic_summary +thread_id/turn_no/origin`; `citations` NO cambia de forma — la webapp tipa
los campos nuevos como opcionales). 1.7 (ADR-0078: `+citations_schema`,
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
selection_rank` y, desde la paridad webapp de ADR-0080 (2026-09-15), `kind, source_family, label, identifier_provenance,
url, gap_flags, zfin_curie, round` SÓLO cuando el ítem del harness las trae), `epmc_query` y `selection.not_selected` —
lo que la Traza SÍ puede leer, porque el bloque `path_b` no viaja en el registro congelado; (j) `text_cap_source`/`n_papers_source`/`retmax_source`
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
como proyección). `render_contract_version: 1.1`. **Desde ADR-0080** el disparador por confianza es UN componente de
la compuerta de competencia y `fallback.trigger ∈ {structural, competence, confidence, null}`: `'confidence'` aparece
SÓLO cuando `competence.competent` es `null` (kill-switch `WITT_COMPETENCE_GATE=0` o ruta `store-consultation`) — ahí
decide la regla legada y la Ruta B es la de ADR-0078 sin harness; en todo otro caso vive en `fb_meta.trigger_legacy` y
`fb_meta.trigger_decided_by` nombra al decisor (ver la sección ADR-0080 más abajo).

### La investigación: turnos encadenados y el origen de la corrida (ADR-0079, 2026-09-15)

Una corrida puede NACER desde otra terminada (`POST /runs {parent_run_id}`): el servidor deriva `thread_id`
(= run_id de la raíz), `turn_no` (max del hilo + 1), `turn_kind` (`refine` · `rerun` = misma pregunta+entities ·
`branch` = el padre ya tenía otro hijo) y `root_question_id`; arma el **snapshot del turno anterior**
(`thread_context`) desde el registro congelado + los comentarios del padre — respuesta recortada, `gap_flags`
íntegros, hallazgos del panel, comentarios (clase atestiguada, topes declarados), pistas para RE-RECUPERAR;
JAMÁS valores ni notas de calificación — y lo persiste como sobre `{snapshot, skipped_reason}`. Al ejecutar viaja al
SINTETIZADOR y al PLANNER como llave hermana `{question, evidence, thread_context}` con la cláusula anti-fuga
(`THREAD_ANTI_LEAK_CLAUSE`); el PANEL recibe evidencia limpia + `deterministic_checks.thread` (resumen sin prosa).
Al congelar: el padre entra a `precedent_citations` en LETRAS (`precedent.turn_item` → `serialize_disjoint`,
`admissible_as_evidence false`) **sólo si está `closed`** (ADR-0053: precedente = clausura humana explícita; un padre
awaiting_closure/failed/cancelled sigue siendo padre válido pero `precedent_citations []` +
`precedent_citations_state ∈ checked | no-parent | parent-not-closed | parent-without-frozen-record`), `validate_disjoint`
es gate, y **un identificador presente en el contexto del padre y en la respuesta del hijo pero AUSENTE de la evidencia
del hijo = `parent_identifier_leak` → inadmisible** (predicado duro, declarado; `_state ∈ checked | no-parent |
no-snapshot`). `thread_parent_matches_run` compara el sha del padre al encolar vs. al congelar (sin
`frozen_at`/`closed_by`). El plan con padre declara `thread_parent_run_id` + `thread_parent_frozen_sha256` y el registro
los casa: `plan_parent_matches_run` / `plan_snapshot_matches_run` (+`_state`). La carrera de `turn_no` la cierra el
índice ÚNICO `ux_runs_thread_turn (thread_id, turn_no)` + re-derivación en `runs.new_run`.
Padre inexistente 404 · padre queued/running 409 · padre con `question_matches_run false` → hija sin contexto
(`parent-identity-invalid`) · padre failed → `previous_answer null` declarado · padre anterior al contrato = raíz
VIRTUAL (turno 2, `parent_pre_adr_0079`). Vocabulario: en código `thread_id`/`turn_no`/`turn_kind`; ante el humano
**investigación T-<run_no raíz>** ("hilo" ya nombra los comentarios de ADR-0077).

**Origen** (`runs.origin`, derivado por `runs.run_origin()` al encolar): `WITT_RUN_ORIGIN` ∈ `production |
dev-offline | replay | smoke | simulation | fixture` (fuera del enum → `invalid-env:<v>` declarado); sin env →
`dev-offline` con `WITT_ALLOW_RUNS_OFFLINE=1`, si no `production`. **Precedente y calibración sólo ven
`production` por default**; smoke/simulation/… se EXCLUYEN y se CUENTAN (`excluded_by_origin`), origin NULL (pre-ADR)
se INCLUYE y se DECLARA (`origin_unknown_included`); `include_origins` amplía — el default se aplica en la PUERTA
(también en `GET /notes/questions/calibration`, vía `precedent.normalize_origins`). `/usage` y `plan_history` NO filtran
(decisión declarada en el ADR). `frozen.origin.source` es la fuente AL ENCOLAR (persistida en el sobre
`thread_context_json.origin`); la re-derivación al ejecutar viaja aparte en `origin.source_at_execution`. **Ejes del episodio** (`frozen.episode_axes`, derivados al congelar por
`runs.EPISODE_AXES_MAP`): `world ∈ effect-claimed | null-bounded | indeterminate | not-established | not-assessed`
· `inference ∈ supported | minor-issues | honest-decline | insufficient | not-evaluated` · `technical ∈ completed |
degraded | failed | cancelled` · `provenance {origin, human_gates, turn}`; el PDF los imprime en palabras junto al
estado y añade la sección INVESTIGACION (`T-<run_no raíz>`, `[A]` NO ADMISIBLE, identidad del padre, origen).

| Variable | Default | Dónde se lee | Efecto |
|---|---|---|---|
| `WITT_THREAD_CONTEXT` | 1 | `runs._thread_context_enabled` (al encolar Y al ejecutar) | 0 = kill-switch: columnas sí, snapshot no; `skipped_reason` declarado |
| `WITT_THREAD_COMMENTS_MAX` | 8 | `runs._thread_limits` (tolerante) | comentarios del padre en el snapshot; `truncated` declarado |
| `WITT_THREAD_COMMENTS_CHARS` | 8000 | idem | chars totales de esos comentarios |
| `WITT_THREAD_ANSWER_CHARS` | 1200 | idem | recorte del `direct_answer` del padre (`direct_answer_truncated`) |
| `WITT_RUN_ORIGIN` | — (derivación) | `runs.run_origin` | `runs.origin` + `frozen.origin {value, source}` |
| `WITT_ALLOW_RUNS_OFFLINE` | — (sólo dev) | `runs.run_origin` (insumo) · `app.create_run` | `'1'` → origin `dev-offline` (source `derived:offline-mask`) cuando `WITT_RUN_ORIGIN` no está y esas corridas quedan FUERA de precedente/calibración por default; **jamás en prod** (el compose no la declara a propósito) |
| `WITT_PIVOT_TURNS` | 3 | `app.PIVOT_TURNS` (`runs._env_int_tolerante`: vacía / no numérica / ≤ 0 → 3, fuente declarada en `pivot_suggested.threshold_source`) | ventana de `pivot_suggested` en `GET /threads` |

`GET /runs?limit=` valida el signo en ambos ramales (`limit < 1` → 400; `limit > 50` → 50 declarado).

Gates (tras el corrector final): `smoke_threads_db.py` 42/42 · `smoke_thread_context.py` 36/36 · `smoke_runs_thread_http.py`
54/54 · `smoke_precedent.py` 30/30 · `smoke_ratings_calibration.py` 44/44 · `smoke_question_agent_http.py` 35/35 ·
`smoke_run_pipeline.py` 217/217.

### La compuerta de competencia y el harness de búsqueda (ADR-0080, 2026-09-15)

**La decisión "¿basta la pasada 1 o se busca afuera?" la toma CÓDIGO.** `pass1 < τ` (ADR-0051) deja de ser el
disparador ÚNICO (`rag_index/query_service/competence.py`, `competence.evaluate`, `module_version cg-3`): la conjunción es
`conf1 ≥ τ ∧ pass1 admisible ∧ plan.route == 'evidence-run' ∧ plan.niches ≠ [] ∧ ¬estructural ∧
(calibration_coverage.sufficient SI WITT_CG_REQUIRE_CALIBRATION=1)`. El componente `conf1_ge_tau` (el escalar ELICITADO
por `CONF_TOOL`, ADR-0065 — medido y calibrable, no prosa) GATEA POR DEFAULT (`cg-3`, corrección del orquestador
2026-09-15: ADR-0051 lo eligió decisor de la Ruta B por encima del estructural; el `cg-2` del corrector lo había vuelto
informativo y con ello una corrida con conf1 0.15 y suficiencia estructural quedaba "competente" — la regresión del caso
a361f566, 0.15 → Ruta B → 0.86, ADR-0059). Se apaga SÓLO con `WITT_CG_CONF_COMPONENT=0` declarado
(`config.conf_component_gating False`, fuera de `conjunction`); `self_report.note` dice literalmente si participa, según
`gating`. Un componente sin insumo
es `False` con `reason` (jamás un `True` vacío). Orden de la traza tras pass1: `stage.confidence.elicit{pass 'pass1'}` →
`stage.deterministic_gate{pass 'pass1'}` (ADELANTADO: la admisibilidad de pass1 es componente) → `stage.competence` (el
bloque íntegro). **Competente** → pass1 es la candidata, `fallback.trigger null`, ninguna ronda (`search_ledger.n_rounds
0`: cero MEDIDO). **No competente** → `stage.search.plan` + rondas del harness → pass2 → `elicit{pass2}` → `gate{pass2}`,
`fallback.trigger 'competence'`, `fb_meta.trigger_decided_by 'code (competence-gate)'`. Lo estructural
(`assess_sufficiency`) manda como hoy (`'structural'`). **`POST /runs` SIN plan** (sin `plan_id`) es `no-plan` → no
competente → ronda + pass2 SIEMPRE, aunque la confianza sea alta: la webapp encola con plan (M3);
`evaluation/run_held_out_v2.py` y `gen_fixtures` encolan directo (decisión abierta en el ADR). `route
'store-consultation'` → `not_applicable` (no hay compuerta). **Kill-switch `WITT_COMPETENCE_GATE=0`** → `competent null`
+ `skipped_reason`, la regla legada por confianza gobierna y el registro lo dice con su nombre: `fallback.trigger
'confidence'` (literal válido SÓLO con `competent null`), `trigger_decided_by 'model-confidence (legacy…)'`, y la Ruta B
corre por `path_b_bundle` SIN plan — el camino de ADR-0078 byte a byte, sin harness ni `stage.search.round/source`
(`search_ledger.state 'legacy-path-b (kill-switch WITT_COMPETENCE_GATE=0)'`, `n_rounds null`). `WITT_SEARCH_HARNESS=0`
apaga SÓLO el harness (la compuerta sigue decidiendo). `calibration_coverage` (`db.calibration_coverage`: corridas
CLOSED con ≥1 rating cuyos `frozen.niches` intersecan los del plan, contando por default SÓLO `origin 'production'` —
`WITT_CG_CALIBRATION_ORIGINS`; smoke/simulation/fixture jamás son historia de competencia) se MIDE y viaja siempre, pero
sólo gatea con `WITT_CG_REQUIRE_CALIBRATION=1` (hoy 0 corridas cerradas calificadas en producción: gatear ya sería
negarlo todo). `council_uncovered_must` existe como llave `'not-available (ADR-0082)'`, `gating false`, para que el
contrato no cambie de forma cuando el consejo aterrice.

**La Ruta B corre por un HARNESS** (`analysis/scripts/lib/search_harness.py`, `harness_version sh-1`): UNA tabla
`SEARCH_DISPATCH` de 15 familias `{tool_module, fn, inputs, budget_s, host, key_env, evidence_kind, gate, label_provenance}`
— las tres de hoy (`europepmc`, `pubmed`, `zfin`, envueltas sin reescribir; sus ledgers `*_searched` siguen
byte-compatibles) + 10 tools Layer 0 NUEVAS y stdlib-puras en `.tooluniverse/tools/`: `alliance_orthologs.py`,
`zfin_expression_tsv.py`, `ensembl_homology.py`, `uniprot_search.py`, `monarch_associations.py`, `reactome_search.py`
(`label 'inferred-by-orthology'`), `string_partners.py` (`label 'predictive'`), `geo_gds.py`, `unpaywall_crossref.py`,
`openalex_search.py`; `web` y `tooluniverse` son `tool-unavailable` declarados (ADR-0084/0085). `gate 'auto'` =
corre por default (`WITT_SEARCH_DEFAULT_FAMILIES`: `europepmc,pubmed,zfin,alliance_orthologs,zfin_expression`);
`'directive-only'` = sólo por directiva del consejo (ADR-0082, hueco `directives: []`) o nombrada en esa env. El plan lo
arma código (`build_search_plan`: familias, queries por familia vía `search_queries.build_all`, `rounds_cap`,
`round_budget_s`, cada valor con su fuente); la ronda la ejecuta código (`run_round`: presupuesto de RONDA repartido entre
las familias que faltan, la que no alcanza queda `skipped-budget` sin tocar la red; `timeout` viaja al tool cuando su
firma lo acepta — también a Europe PMC y PubMed, `timeout_s_scope 'per-call'`; la ronda declara `round_over_budget`);
**nada se re-ejecuta**: otra ronda SOLO si la anterior no admitió nada (`n_admitted == 0`: lo que ENTRÓ al pool, no el
conteo de evidence_ids), `k < WITT_SEARCH_ROUNDS_CAP` y alguna familia tiene INSUMOS nuevos (una curie ZFIN o un DOI
resueltos en la ronda, o una familia que quedó `skipped-budget`); en esa ronda las familias con los mismos insumos quedan
`skipped-cap` con detail `'same inputs as round k (not re-executed)'` sin tocar la red; sin insumos nuevos → `stop_reason
'no-new-inputs'`. Cada fuente deja UNA fila `status ∈ success | no-match | error | skipped-budget |
skipped-cap | tool-unavailable | not-requested` con `n_found`/`n_new` ENTEROS sólo cuando midió (un `success` cuya
lista el harness no supo leer es `error 'shape-mismatch…'`, jamás un 0); cada ítem lleva
`evidence_id` del tool con `identifier_provenance` (o uno DERIVADO `<family>:sha256:…` + `gap_flag`), `kind`,
`source_family`, `label`, `url`, `statement|text|abstract`. Caché de lectura por día bajo `mcp_cache/`
(`WITT_MCP_CACHE_DIR`; el TSV de expresión de ZFIN pesa 43.7 MB — el contenedor necesita escritura). Eventos:
`stage.search.plan`, `stage.search.source` (por familia), `stage.search.round` (por ronda); `stage.path_b` gana
`trigger 'competence'`, `trigger_legacy`, `harness_used` y un resumen `search_ledger`.

**Gate y panel.** `verify_output.positive_claim_requires_citations`: una afirmación positiva (`absence_kind
'not-applicable'` — o AUSENTE: lectura conservadora por código, la omisión del campo no es vía de escape) con 0 citas
válidas es INADMISIBLE; una declinación puede no citar, salvo que nombre identificadores RESUELTOS por
`verify_identifiers` (el mismo informe del gate viaja al predicado): entonces también dispara. La ESCALERA de soporte por cita
(`verify_output.support_state_for`): `unresolved → resolved → passage_delivered → supported|unsupported`, peldaños que
NUNCA se funden (`resolved`, `passage_delivered`, `pertinent 'not-available (ADR-0082)'`, `supported`, `support_state`
viajan separados dentro de cada cita; el veredicto de la lente `evidence-grounding` — `citation_support [{n, verdict}]`,
OPCIONAL en `VERDICT_TOOL`, ignorado por las otras lentes — sólo eleva una cita que ya tiene pasaje). El panel REINTENTA
una vez a un juez caído/ilegible (`WITT_JUDGE_RETRIES`, default 1; `retries_judge` + `attempts[]` en la fila,
`audit.judge_retries {value, source}`, `stage.audit.judge` con `attempt` + `max_attempts` = `1 + WITT_JUDGE_RETRIES` de la
misma fuente (`max_attempts_source`) — "intento N de M"), jamás fabrica. **Gasto por etapa**:
`token_usage.by_stage {plan, synthesize_pass1, elicit_pass1, search, synthesize_pass2, elicit_pass2, panel, revision,
embed, _sum}` desde el `usage` que cada llamada devuelve (los eventos que gastan lo llevan); `_sum == by_model` se
comprueba y se declara (`by_stage_sum_matches_by_model`); un sintetizador que no separa la elicitación deja
`elicit_* {in null, state 'not-separable…'}`, nunca un 0 inventado; `plan` distingue `no-plan` de `plan-without-usage
(planner reported no usage)` (in/out null); el gasto de un juez AGOTADO que cobró entra a `by_model`/`panel` igual que
a `audit.usage` (M8 cuadra en el caso del reintento fallido).

**Registro congelado 1.9** (aditivo): `competence` (bloque íntegro + `decision`; `components.calibration_coverage` lleva
`include_origins` (lista | `'all'`) + `include_origins_source`, y `conf1_ge_tau.tau_source == config.tau_source`),
`search_ledger {plan, rounds[], families_default, n_rounds, cap, round_budget_s, state, plan_state,
plan_state_vocabulary {exact, prefixes, rule}, config_source, stop_reason}` — `plan_state` es un literal EXACTO de
`runs.SEARCH_PLAN_STATES_EXACT` (`built | not-requested | harness-unavailable | error`) o empieza con un prefijo de
`runs.SEARCH_PLAN_STATE_PREFIXES` (`'error: '`, `'kill-switch '`, `'not-applicable ('`, `'harness-unavailable ('`);
`runs.plan_state_in_vocabulary` lo valida —,
`citations[].{resolved, passage_delivered, pertinent, supported, support_state}`, `citations_support_summary {n,
by_state (los 5 peldaños siempre: enteros si `checked`, null si degradado), ladder, pertinent, state}`,
`deterministic_checks.{pass ('pass1'|'pass2'|'revision'), pass1_admissible, positive_claim_requires_citations(+_state,
+_evaluation), competence_gate}`, `fallback.trigger ∈ {structural, competence, confidence, null}` +
`fb_meta.{trigger_legacy, trigger_vocabulary, trigger_decided_by, tau_source, search_harness_enabled, competence}`,
`token_usage.by_stage`, `epistemic_summary.{competent, n_search_rounds (0 = no se buscó; null = el harness no midió)}`.
El PDF (`record_pdf.py`) imprime `trigger_decided_by` + el veredicto de la compuerta, el estado del `search_ledger` y el
`support_state` por cita (ausente = `NO INSTRUMENTADO (contrato < 1.9)`). **La webapp debe tipar (`?`) y pintar** — ver
*Consequences* del ADR.

| Variable | Default | Lector | Efecto |
|---|---|---|---|
| `WITT_COMPETENCE_GATE` | `1` | `competence.env_config` (en cada `evaluate`) | `0` = kill-switch: `competent null` + `skipped_reason`; la regla legada `pass1 < τ` decide, `fallback.trigger 'confidence'` y la Ruta B corre SIN harness (ADR-0078 byte a byte) |
| `WITT_CG_REQUIRE_CALIBRATION` | `0` | idem | `1` = `calibration_coverage.sufficient` entra a la conjunción (`components.calibration_coverage.gating`) |
| `WITT_CG_CONF_COMPONENT` | `1` | idem | `1` (default, `cg-3`) = `conf1_ge_tau` (la confianza ELICITADA por `CONF_TOOL`, ADR-0065) gatea en la conjunción como decidió ADR-0051; `0` declarado = se mide y viaja informativo (`gating false`, fuera de `conjunction`), la nota de `self_report` lo dice |
| `WITT_CG_CALIBRATION_ORIGINS` | `production` | `runs._calibration_origins` → `db.calibration_coverage(include_origins=)` | orígenes que cuentan como historia de calibración (CSV tolerante; `all` = sin filtro declarado) |
| `WITT_COMPETENCE_MIN_HISTORY` | 10 | `runs._competence_min_history` → `db.calibration_coverage` (tolerante) | corridas CLOSED calificadas que intersecan los nichos del plan para `sufficient` |
| `WITT_FALLBACK_CONF_TAU` | 0.5 (ya existía) | `runs.FALLBACK_CONF_TAU` (lector tolerante, `fb_meta.tau_source`) → `evaluate(tau=)` (`tau_source 'caller'`) | el τ del componente `conf1_ge_tau` y de la regla legada |
| `WITT_SEARCH_HARNESS` | `1` | `runs._search_harness_enabled` | `0` = la compuerta decide pero la Ruta B corre por `path_b_bundle` SIN plan (sin familias Layer 0 ni rondas): el freno del operador |
| `WITT_SEARCH_ROUNDS_CAP` | 2 | `runs._search_config` (delega en `search_harness`) · `search_harness.build_search_plan` | rondas máximas por corrida; una 2ª ronda sólo para familias con INSUMOS nuevos; `search_ledger.cap` + `config_source.cap` |
| `WITT_SEARCH_ROUND_BUDGET_S` | 120 | idem | presupuesto de reloj por RONDA (repartido; `skipped-budget` declarado) |
| `WITT_SEARCH_DEFAULT_FAMILIES` | `europepmc,pubmed,zfin,alliance_orthologs,zfin_expression` | idem | familias que corren sin directivas; nombrar una `directive-only` aquí ES la directiva del operador; desconocidas → `families_excluded 'unknown-family'` |
| `WITT_JUDGE_RETRIES` | 1 | `composite_auditor.resolve_judge_retries` (en cada `audit`) | intentos ADICIONALES por juez caído/ilegible; declarado en `audit.judge_retries` |
| `WITT_MCP_CACHE_DIR` | `<repo>/mcp_cache` | tools Layer 0 (declarado en `plan.cache_dir`) | caché de lectura por día; necesita escritura en el contenedor |
| `OPENALEX_API_KEY` | — (opcional) | `openalex_search` | sin llave OpenAlex cobra créditos (medido: 10 créditos / 0.001 USD por llamada, 1000/día) |
| `WITT_UNPAYWALL_EMAIL` | — (opcional) | `unpaywall_crossref` (también primer `mailto` de Crossref/OpenAlex) | sin él la fila Unpaywall es `tool-unavailable` declarada; JAMÁS se inventa correo |
| `WITT_ENSEMBL_MIN_INTERVAL_S` | 0.07 | `ensembl_homology` (`net_throttle`) | pacing de `rest.ensembl.org` |
| `WITT_ZFIN_EXPR_DOWNLOAD_BUDGET_S` · `WITT_ZFIN_EXPR_MAX_MB` · `WITT_ZFIN_EXPR_SCAN_BUDGET_S` | 180 · 500 · 60 | `zfin_expression_tsv` | presupuesto/tope de la descarga diaria del TSV y del escaneo local (exceso → `error BudgetExhausted` declarado) |
| `WITT_GEO_RETMAX` · `WITT_GEO_ORGANISM` · `WITT_OPENALEX_PER_PAGE` | 10 · `'Danio rerio'` · 5 | `geo_gds` · `openalex_search` | uids por esearch; bloque `[Organism]` (una env PRESENTE y vacía lo DESACTIVA — por eso el compose no la declara); works por llamada |

Gates (offline, máscara de siempre + `WITT_RUN_ORIGIN=smoke`, 2026-09-15, tras el corrector final): `smoke_competence.py`
27/27 · `smoke_search_harness.py` 45/45 · `smoke_tools_a.py` 45/45 · `smoke_tools_b.py` 69/69 · `smoke_tools_c.py` 68/68 ·
`smoke_gate_citations.py` 48/48 · `smoke_run_pipeline.py` 247/247 (sección ADR-0080: 31 checks; la sección bloquea y
CUENTA `urllib.request.urlopen` — 0 llamadas — y compara `mcp_cache` antes/después) · `smoke_thread_context.py` 37/37
(kill-switch declarado para los conteos de pasadas + UNA corrida encadenada con la compuerta ENCENDIDA) ·
`smoke_run_recovery.py` 40/40 · resto del directorio verde (25/25 gates).

### Política best-tier v2 y generación de modelos `g2-2026-09` (ADR-0081, 2026-09-15 — **Proposed**; conteos de gates MEDIDOS por S7 el 2026-09-15: 31 smokes en verde, 1623 checks)

**UNA tabla de modelos, dos generaciones, resolución en la LLAMADA.** Hasta `f57a3d3` había CUATRO verdades de modelo
desincronizables (`runs.SYNTH_MODEL`, `question_agent.QUESTION_MODEL`, `composite_auditor.DEFAULT_PANEL` con
`OPENAI_JUDGE_MODEL` evaluada EN IMPORT, `evaluation/run_held_out.JUDGE_PANEL`) más la tabla de precios. Desde ADR-0081 los
literales de modelo viven SÓLO en `analysis/scripts/lib/models.py` (`MODELS_TABLE_VERSION 'g2-2026-09'`; gate estático en
`smoke_models.py`), con dos generaciones: **g2** — `claude-opus-5` en síntesis/planner/elicitación/agente de preguntas y juez
correctness · `claude-sonnet-5` overclaim · `claude-haiku-4-5-20251001` evidence-grounding · `gpt-4o` reproducibility (puente) —
con TOPES `max_tokens` 8000/4000/2000/4000/4000 (techos, no gasto: Opus 5 PIENSA por default y `max_tokens` acota pensamiento +
respuesta); **g1** = hoy byte a byte (`claude-opus-4-8`, topes 2500/1200/300/1200/1200). Cada rol se resuelve **en tiempo de
llamada** (`models.resolve_role(rol, env, today)`), jamás en import, y viaja con su FUENTE: `env:<VAR>` · `default:<gen>` ·
`default-invalid-env:<VAR> (<motivo>)` · `auto-retire:<a>-><b>`. Un id que la tabla no conoce se USA tal cual (`known false`,
familia por prefijo, `unknown_models[]` declarado); sólo se rechaza lo que la tabla sabe que ROMPE (`claude-fable-5-1` excluido —
400 en `tool_choice` forzado, retención 30 días; familia incompatible con la lente).

**Lo que cambia para el operador**

1. **Nada cambia sin fuente.** La Traza abre con el evento `stage.models` (roles + fuente + panel + `warnings[]` +
   `unknown_models[]`) ANTES de gastar; el registro 1.10 congela `frozen.models` con `roles` (elección + fuente) y `ran`
   (`requested` vs `reported` = `payload.model` que la API devolvió; `relation ∈ exact | prefix | different | not-reported` —
   `prefix` es NEUTRO (alias → snapshot fechado), `different` es objeción, `not-reported` es gris). `answer.model` deja de ser
   una constante copiada.
2. **Envs por rol** (tabla abajo): `WITT_MODEL_SYNTH/_PLANNER/_ELICIT/_QUESTION`, `WITT_JUDGE_CORRECTNESS/_OVERCLAIM/_GROUNDING`,
   `OPENAI_JUDGE_MODEL` (conserva su nombre: es la palanca hacia Astra). `WITT_MODEL_GENERATION=g1-2026-08` es el kill-switch de
   toda la generación.
3. **Cuórum por FAMILIAS y LENTES** (`WITT_PANEL_MIN_FAMILIES=2`, `WITT_PANEL_MIN_LENSES=3`): tres APPROVE Anthropic con el juez
   OpenAI caído ya NO aprueban — `verdict 'REVISE'`, `panel_incomplete_reasons ['families']` (códigos cerrados; los números en
   `audit.quorum`), sin ciclo de revisión (`revision.skipped_reason` lo dice). **Consecuencia literal (R4): OpenAI caído = 100%
   REVISE estructural** hasta que vuelva o bajes `WITT_PANEL_MIN_FAMILIES` a `0|1` (kill-switch declarado, `gating false`).
4. **El juez OpenAI habla la Responses API** cuando la tabla lo dice (`gpt-6-astra`, `status 'candidate'`) o cuando
   `WITT_OPENAI_API=responses` lo fuerza; `gpt-4o` (`status 'bridge'`) sigue por `chat.completions` (`WITT_OPENAI_API=table`,
   default) hasta que LG3 pase. Todo fallo de juez lleva `attempts[].error_kind` de un vocabulario CERRADO (`no-api-key`,
   `http-<code>`, `network`, `refusal`, `no-function-call`, `arguments-unparseable`, `verdict-off-vocabulary`,
   `incomplete:max_output_tokens`, `incomplete:content_filter`, `unknown-family`, `required-missing:…`, `unclassified`); el
   string `error` de hoy queda byte a byte. `store: false` por default (`WITT_OPENAI_STORE`); `strict: false` FIJO (sin env);
   `max_retries=0` en el SDK para que `attempts[]` no mienta.
5. **Opus 5 piensa por default.** Las llamadas Anthropic siguen OMITIENDO `thinking`; en g2 eso es adaptativo por default de la
   API (los tokens de pensamiento se facturan como salida y quedan DENTRO de `usage.output_tokens`; el caller aplana
   `usage.thinking_tokens` cuando la API lo manda — informativo, jamás 0 inventado). El freno es `WITT_ANTHROPIC_EFFORT`
   (`output_config.effort`, sólo a modelos `thinking_default 'adaptive'`) o `WITT_ANTHROPIC_EFFORT_ELICIT` para la mini-llamada
   de confianza — NUNCA `thinking {type:'disabled'}` (dos modos de falla documentados).
6. **Retiro de haiku (≥ 2026-10-15).** La tabla declara el sucesor (`claude-sonnet-5`, lente distinta) — DATO; la env lo ejecuta
   — ACTO: `WITT_JUDGE_GROUNDING=claude-sonnet-5` (default, E2) o `WITT_PANEL_AUTO_RETIRE=1` (sustitución automática declarada
   con fila `runtime-diff`). El aviso MEDIDO `retirement-due: … (faltan N días; sucesor declarado …)` sale en
   `stage.models.warnings[]`, `/config-history.current.warnings[]` y `consulta_sistema.config` desde 30 días antes; después,
   `past-retirement: …`. Tras el retiro dos asientos `claude-sonnet-5` bajan la independencia intra-Anthropic:
   `panel_duplicate_models[]` lo declara, no lo disimula.
7. **Bitácora de configuración.** `GET /config-history` = `entries` del archivo `rag_index/config_history.json` (clase
   ATESTIGUADA, human-maintained; ganó `model_generation` y `budget_approval` — esta última con placeholder `<pendiente E3>`) +
   `ledger[]` de la tabla `config_history` en BD (clase MEDICIÓN: al arrancar el servicio compara `models.snapshot()` con la
   última fila por campo y appendea sólo lo que cambió; primer arranque = una fila por campo `first-boot-snapshot`;
   `actor_state 'not-observable (env set outside the service)'` — no se afirma QUIÉN cambió la env) + `current` (estado
   efectivo con fuente por campo). `WITT_CONFIG_LEDGER=0` = cero escrituras, `ledger_state` lo dice. Un fallo del ledger JAMÁS
   impide el arranque. La webapp (M6 SISTEMA) sustituye la placa "no tiene puerta HTTP".
8. **Investigaciones y consumo:** `GET /threads` (índice paginado en el servidor), `root_run_no` en toda vista de corrida y en
   `run.state{queued}` (la Traza dice "Investigación T-<n>" desde el primer evento), `/usage.by_stage` (tokens por etapa y
   modelo×etapa; `by_stage.panel.by_model` separa a opus-5 sintetizador de opus-5 juez).
9. **Históricos:** NADA se recalcula ni se backfillea. Registros < 1.10 no ganan `models` ni `audit.families_valid`; la webapp y
   el PDF los leen como "NO INSTRUMENTADO (contrato < 1.10)". `prices()` conserva TODOS los ids históricos para que `/usage`
   recotice sin `missing_price`. La única novedad de esquema es la tabla `config_history` + un JOIN (SELECT); `_migrate` no gana
   ALTER.
10. **Lo que NO se hace (ADR (L)) y no es deuda:** validación en arranque contra `/v1/models` (red en arranque viola §6),
    `WITT_OPENAI_STRICT` (rompe el tres-estados del schema), `WITT_PANEL_SPEC`, puente `gpt-5.6-sol`, `thinking disabled`,
    `fallbacks` server-side de Opus 5, migración del PDF (→ ADR-0083 con línea `[pdf]`).

**Kill-switches (ADR (M.2)) — cada uno con default declarado y devuelve el comportamiento de `f57a3d3`:**
`WITT_MODEL_GENERATION=g1-2026-08` (los 8 defaults y los 5 topes de hoy) · `WITT_OPENAI_API=chat-completions` (el caller de
hoy) · `WITT_PANEL_MIN_FAMILIES=0` · `WITT_PANEL_MIN_LENSES=0` (la regla de hoy) · `WITT_CONFIG_LEDGER=0` (cero escrituras) ·
`WITT_PANEL_AUTO_RETIRE=0` (default: nada cambia solo). Con los cinco primeros, el registro menos las llaves aditivas 1.10 tiene
EXACTAMENTE el keyset y los valores de un frozen 1.9 (lo mide `smoke_run_pipeline.py`).

**Invariante: TODA env implica reinicio.** El `os.environ` del contenedor se fija al arrancar el proceso: cambiar una variable en
la pestaña Environment de Dokploy NO surte efecto hasta redeploy/restart (el compose lo dice en su bloque ADR-0081). La lectura
en tiempo de llamada permite probar la env offline sin reimportar, pero NO elimina el reinicio; por eso el diff del ledger al
arrancar es COMPLETO para envs. Lo que el ledger NO puede registrar: un `min_families=` pasado por un llamador (viaja en
`audit.quorum.source 'caller'`) y el reloj (el auto-retire lo cubre `runtime-diff`).

| Variable | Default | Lector | Efecto / fuente declarada |
|---|---|---|---|
| `WITT_MODEL_GENERATION` | `g2-2026-09` | `models.resolve_role` | generación de defaults y topes; `g1-2026-08` = hoy byte a byte; inválida → `default-invalid-env` |
| `WITT_MODEL_SYNTH` · `WITT_MODEL_PLANNER` · `WITT_MODEL_ELICIT` · `WITT_MODEL_QUESTION` | `claude-opus-5` (g2) · `claude-opus-4-8` (g1) | `models.resolve_role` | modelo por rol; `frozen.models.roles.*.source` |
| `WITT_JUDGE_CORRECTNESS` | `claude-opus-5` (g2) · `claude-opus-4-8` (g1) | `models.panel` | asiento correctness (anthropic) |
| `WITT_JUDGE_OVERCLAIM` | `claude-sonnet-5` | `models.panel` | asiento overclaim |
| `WITT_JUDGE_GROUNDING` | `claude-haiku-4-5-20251001` | `models.panel` | asiento evidence-grounding; el sucesor declarado (sonnet-5) se fija AQUÍ (E) |
| `OPENAI_JUDGE_MODEL` | `gpt-4o` (ya existía) | `models.panel` | asiento reproducibility; `gpt-6-astra` SÓLO tras LG3 |
| `WITT_PANEL_AUTO_RETIRE` | `0` | `models.panel` | `1` = sucesor automático al llegar `retire_not_before` (declarado + fila `runtime-diff`) |
| `WITT_PANEL_MIN_FAMILIES` | `2` | `audit()` | cuórum de familias; `0|1` = kill-switch (`gating false`) |
| `WITT_PANEL_MIN_LENSES` | `3` | `audit()` | cuórum de lentes; `0|1` = kill-switch |
| `WITT_OPENAI_API` | `table` | `models.api_of` | `responses` fuerza Responses para todo juez OpenAI; `chat-completions` = caller de hoy |
| `WITT_OPENAI_STORE` | `0` | `_responses_kwargs` | `store` de `responses.create` (default de la API: true) |
| `WITT_OPENAI_MAX_OUTPUT_TOKENS` | `4000` | `_responses_kwargs` | tope (no gasto) del camino Responses; chat conserva 1200 |
| `WITT_OPENAI_REASONING_EFFORT` | vacío (no se envía) | `_responses_kwargs` | `reasoning.effort` sólo con `reasoning True` en tabla |
| `WITT_OPENAI_TIMEOUT_S` | `120` | `_openai_client` | timeout por llamada del juez OpenAI; regla `(1+retries)×timeout×2 ≤ 900` |
| `WITT_ANTHROPIC_EFFORT` | vacío (no se envía) | `_anthropic_tool_call` | `output_config.effort` sólo a modelos `thinking_default 'adaptive'` |
| `WITT_ANTHROPIC_EFFORT_ELICIT` | vacío (hereda) | `runs._elicit_confidence` | override para `CONF_TOOL` |
| `WITT_CONFIG_LEDGER` | `1` | `app.config_ledger_boot/observe` | `0` = cero escrituras; `ledger_state` lo dice |
| `WITT_JUDGE_RETRIES` | `1` (ADR-0080) | `audit()` | sin cambio; entra al snapshot |

**Gates EN VIVO — LG1–LG14, en este orden (los corre Emmanuel; cada uno gasta lo que dice; ningún smoke del CI gasta; el
resultado se anota en el ADR como MEDICIÓN con fecha).** El instrumento es `analysis/scripts/smoke_live_models.py`: usa los
callers REALES (`composite_auditor._responses_kwargs` / `_openai_responses_call` / `_anthropic_tool_call(return_meta=True)`),
imprime fila · `kind` · `usage` · `meta` · latencia por llamada, escribe `analysis/outputs/live_models_<fecha>.json` SIN
secretos, rehúsa correr sin llave (`no-api-key`), jamás toca la BD; `--dry-run` construye los kwargs y los imprime sin red (el
único modo que corre el CI). Python: `dev/.venvs/witt-query-service` con la llave en el entorno del proceso (nunca en git).

1. **LG1 · Opus 5 con los schemas REALES forzados, ANTES del redeploy** (≈ 4–5 llamadas, < 0.3 USD):
   `python analysis/scripts/smoke_live_models.py --roles synthesizer,elicitation,planner,question_agent,judge-anthropic` → cada
   llamada devuelve `tool_use` con todos los `required` bajo los topes g2, `stop_reason 'tool_use'` (no `max_tokens`),
   `usage.output_tokens` medido (compararlo contra la mediana 4.8 de `synthesize_pass1` de M8: `--baseline-median-out N`);
   repetir la elicitación con `--effort low`. Si truncara → `WITT_ANTHROPIC_EFFORT_ELICIT=low` o subir el tope en tabla; si
   Opus 5 rechazara `tool_choice` forzado (no esperado) → `WITT_MODEL_*=claude-opus-4-8` como freno y nota en el ADR.
2. **LG2 · Transporte Responses con el modelo barato** (1 llamada, ≈ 0.01 USD): `--model gpt-4o --api responses` → verdict ∈
   VOCABULARY, `meta.model_reported` empieza con `gpt-4o`, kwargs con `store False`, `strict False`. Si falla, el `error_kind`
   dice qué (`http-401/403` llave; `http-400` parámetros → reportar verbatim).
3. **LG3 · Astra** (1–2 llamadas, ≤ 0.05 USD): `--model gpt-6-astra --api responses` → verdict válido,
   `usage.reasoning_tokens > 0`, `output_tokens ≥ reasoning_tokens`, latencia (< 120 s o subir `WITT_OPENAI_TIMEOUT_S` ≤ 225).
   `http-404/400` con 'model' = la llave NO tiene acceso → E1. `incomplete:max_output_tokens` → repetir con
   `--max-output-tokens 8000` y fijar la env. SÓLO con LG3 en verde: `OPENAI_JUDGE_MODEL=gpt-6-astra` en Dokploy + redeploy.
4. **LG4 · Arranque tras el redeploy:** `GET /config-history` → `ledger_state 'ok'`, una fila por campo `first-boot-snapshot`,
   `current.fields.model_generation 'g2-2026-09'`, `panel.reproducibility 'gpt-4o'`, `openai.api 'table'` (la ELECCIÓN de env;
   el transporte efectivo del asiento viaja en `audit.panel[3].api` — corrector), `warnings` con `retirement-due: …` y
   `api-unverified: claude-opus-5 …` hasta E2/LG1 (NO `[]` — corrector); `/status` byte-igual; un segundo reinicio sin cambios NO
   añade filas.
5. **LG5 · Primera corrida real con opus-5:** Traza abre con `stage.models`; `frozen.models.roles.synthesizer ==
   {claude-opus-5, 'default:g2-2026-09'}`, `ran.synthesize_pass1.relation ∈ exact|prefix`, `ran.elicit_pass1` medido,
   `roles.planner.provenance` según cuándo se hizo el plan; `token_usage.by_model` sin `claude-opus-4-8` (salvo plan viejo); M8
   `models_catalog['claude-opus-5'].known true`; Hoja sección Modelos; comparar `synthesize_pass1.in/out` y latencia contra la
   mediana 4.8.
6. **LG6 · Primera corrida con Astra (tras LG3):** `audit.panel[3].api 'openai-responses'`, `attempts[-1].model_reported`
   presente, `ran.panel[3].relation ∈ exact|prefix`, `by_model['gpt-6-astra']` cotizado 10/50, `audit.usage.reasoning_tokens >
   0`; el ledger ganó `panel.reproducibility gpt-4o → gpt-6-astra` y `openai.api → openai-responses`.
7. **LG7 · Cuórum en vivo** (1 corrida, ≈ 0.2 USD): `OPENAI_JUDGE_MODEL=gpt-no-existe` + redeploy → `panel[3].status 'errored'`,
   `attempts[*].error_kind 'http-404'|'http-400'`, `verdict 'REVISE'`, `panel_incomplete_reasons ['families']`,
   `revision.performed false`, `epistemic_summary.panel_n_families_valid 1`, ListaCorridas "1 familia"; restaurar (el ledger deja
   DOS filas: el cambio y la vuelta).
8. **LG8 · `GET /threads` en Postgres:** sin 500 (dependencia funcional del GROUP BY); `n_threads_total == SELECT count(distinct
   thread_id) …`; cada `label`/`n_turns` == `/threads/{id}`; `n_runs_without_thread` == corridas pre-ADR-0079; `limit=1` →
   `has_more true`; M6 lista sin agrupar en el cliente.
9. **LG9 · `root_run_no` en prod:** lista y detalle de un hijo == `/threads/{thread_id}.root_run_no`; la Traza de una corrida
   encolada hoy muestra "Investigación T-<n>" desde `run.state{queued}`; una pre-ADR muestra `null` declarado.
10. **LG10 · `/usage` por etapa en prod:** `by_stage._sum` == suma de `totals` restringida a corridas con `by_stage`;
    `n_runs_without_by_stage` == corridas congeladas antes de 1.9; `by_model_stage_coverage.n_runs_with_panel_by_model` ==
    corridas 1.10; `by_model['claude-opus-4-8'].family 'anthropic'`.
11. **LG11 · Precios (atestiguado por Emmanuel):** confirmar en las páginas de precios que opus-5 5/25 · sonnet-5 2/10 ·
    haiku-4.5 1/5 · fable-5.1 10/50 · gpt-4o 2.5/10 · gpt-6-astra 10/50 · gpt-5.6-sol 4/20 siguen vigentes; si alguno cambió, fila
    en `models.py` con `verified_on` nuevo y `PRICES_AS_OF`.
12. **LG12 · Retiro de haiku (antes del 2026-10-15):** `stage.models.warnings` muestra `retirement-due` desde el 2026-09-15; al
    fijar `WITT_JUDGE_GROUNDING=claude-sonnet-5` (o `AUTO_RETIRE=1`) → fila del ledger, siguiente corrida con `lenses_valid 4`,
    `families_valid ['anthropic','openai']`, `panel_duplicate_models ['claude-sonnet-5']`, `warnings []`.
13. **LG13 · Kill-switch byte a byte en prod** (opcional, 1 corrida): g1 + chat-completions + MIN 0/0 + LEDGER=0 →
    opus-4-8/gpt-4o por chat.completions, `quorum.families_gating false`, `ledger_state 'kill-switch…'`, registro menos llaves
    1.10 = forma f57a3d3.
14. **LG14 · Promesas del brief (gastan; decisión E4, default NO se corre):** `evaluation/scripts/ab_trapped_scalar.py` con opus-5
    (|Δ| del escalar atrapado ≤ 0.15 vs la serie 4.8, ADR-0065) y `run_held_out_v2` sin regresión de veredictos (advisory).

Gates NO-SPEND (máscara de siempre + `WITT_RUN_ORIGIN=smoke`; conteos MEDIDOS por S7 el 2026-09-15 — la tabla completa vive en
el ADR): NUEVOS `smoke_models.py` 74 (tabla, precios golden, resolución por env, retiro con `today`, snapshot sin secretos, gate
estático de literales en PASS) · `smoke_openai_responses.py` 74 (kwargs exactos, fakes sin red, vocabulario de fallos) · `smoke_panel_quorum.py` 28
(cuórum + golden 1.9 con kill-switches) · `smoke_config_ledger_db.py` 37 · `smoke_usage_http.py` 24 · `smoke_config_history_http.py` 28;
TOCADOS `smoke_run_pipeline.py` 251 → 271 (contrato 1.10, `frozen.models`, `stage.models`, kill-switch g1 → keyset 1.9, costuras (N)), `smoke_run_recovery.py` 40,
`smoke_question_agent_http.py` 35 → 39, `smoke_threads_db.py` 42 → 77, `smoke_runs_thread_http.py` 54 → 71, `smoke_runs_list_http.py` 17 → 21; los otros 19 sin cambio (31/31 en verde, 1623 checks); estático
`smoke_live_models.py --dry-run` (6 filas, exit 0). Ningún gate del CI gasta modelo ni toca la red (`urlopen` bloqueado y contado = 0).

### El consejo de criterio ejecutable (ADR-0082, 2026-09-15 — **Proposed**; conteos de gates MEDIDOS por C9 el 2026-09-15/16: 37/37 smokes en verde)

**Qué es.** Hasta `9d90c01` dos filas de la matriz corrían como código y el planner declaraba, corrida tras corrida,
que ninguno de los 17 agentes aplicables corrió (`will_run 'skipped-ad-hoc'`). Desde ADR-0082 las **31 fichas del
catálogo se parsean como código** (`analysis/scripts/lib/catalog_cards.py`: `text_verbatim`, `sha` por ficha,
`CATALOG_SHA` global — 31 golden), la **membresía es una TABLA** (`agent_matrix.COUNCIL_MEMBERSHIP`, versión `cm-1`,
matriz v1.3: 17 miembros en orden FIJO — 5 cómputo · 7 lab/lectura · 3 conocimiento · `cross-field-bridge-agent`
exploratorio · `regulatory-ethics-advisor` sólo banderas —, 8 operativos `not-applicable-by-category` que sólo se sientan
con `WITT_COUNCIL_FULL=1`, 9 de sustrato con su estado real; **19/34 filas ejecutables**) y el consejo corre como
`analysis/scripts/lib/council.py` (stdlib puro) en tres rondas: **r1** requisitos de información (JOB del plan, ANTES de
gastar la corrida), **r2** cobertura de SUS requisitos sobre `DI + path_b` ANTES de la compuerta de competencia, **r3**
re-cobertura informativa sólo si la búsqueda dirigida admitió algo. **El consejo JAMÁS escribe la respuesta, ni
veredicto, ni ranking, ni despacha** (CLAUDE.md §7): sus tres tools (`emit_information_requirements`, `emit_flags`,
`emit_coverage_judgment`) no tienen campo `direct_answer`/`verdict`/`confidence`/`ranking`/`score`/`dispatch`
(`council.tools_static_check()` lo mide); la agregación es CÓDIGO byte a byte (`aggregate_r1`: mismos insumos barajados →
mismo JSON, mismos `requirement_id`); las directivas de búsqueda las COMPILA código desde los requisitos `kept` sin cubrir
(`directives_from`) y `SEARCH_DISPATCH` resuelve el mecanismo; el sintetizador es CIEGO al consejo (E5); la ÚNICA puerta
donde su prosa se vuelve gasto es la aprobación humana del ledger; `causal-pruner` (hard-rule §7.1) no pasa sin decisión
humana EXPLÍCITA sobre CADA requisito suyo (400 `hard_rule_requirements_undecided`, ningún default la toma).

**El flujo para el operador.** `POST /runs/plan` sigue síncrono (el planner) y, si aplica, encola la ronda 1
(`council.state 'queued'`); un hilo `council-worker-N` la reclama (FIFO, sólo orígenes de `WITT_COUNCIL_ORIGINS`), lanza al
miembro #1 SOLO (el prefijo compartido se escribe una vez en la caché y se lee 16×) y luego ≤ 6 en vuelo, emite latido
`stage.council.progress` cada ≤ 30 s a `plan_events`, persiste INCREMENTALMENTE tras cada miembro (un redeploy a media
ronda conserva lo gastado), agrega y deja `plans.council_state ∈ applicable | incomplete | errored (…)`. M3 lee
`GET /plans/{id}` + SSE y pinta el **ledger**: keep / discard (razón obligatoria) / "yo lo aporto" (texto ATESTIGUADO,
jamás evidencia) + "qué sabes ahora"; **Aprobar** (un clic "keep todo" salvo los `hard_rule` pendientes) o **Saltar
(razón)** libera `POST /runs {plan_id}` (409 hasta entonces — E4). En la corrida: `stage.council.ledger` → … →
`gate{pass1}` → **r2** (`stage.council.round/member/progress` + `stage.council.coverage {phase 'pre-search'}`) →
`stage.competence` con el componente NUEVO **`council_uncovered_must`** (`cg-4`: gatea por default — 0 must sin cubrir;
`vacuous` = True declarado; `incomplete` = False con razón; kill-switch/no-ledger = null fuera de la conjunción) → si no
competente, `stage.council.directives` → `stage.search.plan {families_source 'directives+default'}` (UNIÓN: las 5 auto
SIGUEN y las `directive-only` entran por directiva) → Ruta B → **r3** condicional → `coverage {phase 'post-search'}` →
pass2 → panel (recibe SÓLO `deterministic_checks.council` con conteos y clase, jamás la prosa). Cobertura = worst-of-N
sobre votos VÁLIDOS; un `evidence_id` que no está en el bundle ANULA el voto (`hallucinated_evidence_ids`); `must` con
`coverage_final ∈ {uncovered, partial, not-judged}` cuenta como SIN cubrir; `must` `unsatisfiable-by-harness`
(`web`/`tooluniverse`/`figure`) se CUENTA y no gatea (E1; `GET /council/demand` es el criterio de disparo de
ADR-0083/0084/0085). Lo atestiguado viaja al sintetizador como llave HERMANA `human_attestations` con cláusula anti-fuga y
predicado DURO `attestation_identifier_leak` (identificador presente en lo atestiguado y en la respuesta pero ausente de la
evidencia = inadmisible).

**Registro congelado 1.11** (aditivo; `plan_version '4'`): `frozen.council {state, membership_version 'cm-1',
membership_source, catalog_sha, plan_catalog_matches_run, rules_sha, tools_sha, shared_block_sha, model {requested, source,
generation, effort, effort_source, effort_pinned, max_tokens}, n_members, members[], ledger, human_attestations, rounds[]
(r1 COPIADA del plan + r2/r3 medidas), coverage {pre_search, after_search, post_search}, must_uncovered, must_uncovered_post,
must_unsatisfiable, directives[], directives_state, r3, index, cache {r1|r2|r3 {creation, read}, hit_ratio_r2}, usage,
config, vocabulary, kill_switch}`; `competence.components.council_uncovered_must` (G.2); `deterministic_checks.{council,
attestation_identifier_leak}`; `citations[].pertinent` (`true` | `'not-named-by-council (…)'` | `'not-available (council
<state>)'`) + `pertinent_to`/`pertinent_source`; `search_ledger.plan.directives[]`/`directives_state`/`families_source`,
`rows[].directive_requirement_ids`, `n_items_for_directives`; `fallback.fb_meta.council`; `token_usage.by_stage.council_r1`
(`'copied-from-plan_json'`: el gasto ocurrió ANTES de la corrida) `/r2/r3` con `cache_creation`/`cache_read` (`state` ∈
`council.vocabulary.usage_stage_states`: `'measured'` | `'measured (partial: round cancelled)'` | `'copied-from-plan_json'` |
`'plan-without-council'` | `'kill-switch WITT_COUNCIL=0'` | `'not-run (…)'` — corrector),
`token_usage.cache` (multiplicadores 1.25×/2×/0.1× declarados con fuente y fecha), `input_tokens_total`, `council_judgment`;
`agents_invoked` con la fila `(consejo de criterio — cm-1)` (`council:<n_valid>/<N>`) y una fila `invoked` por miembro (un
miembro caído SÍ fue invocado: lo dice su `evidence`); `epistemic_summary.council_*`; `thread_context.council_summary`
(el turno N+1 hereda criterios, nunca prosa); la vista de corrida gana `plan_council_state`/`council_n_valid`. **Históricos:
NADA se recalcula ni se backfillea** — registros < 1.11 no ganan `council`; la webapp y el PDF (sección "CONSEJO DE
CRITERIO (ADR-0082)", `record_pdf.py`) los leen 'NO INSTRUMENTADO (contrato < 1.11)'; planes anteriores a la columna se leen
`council_state 'pre-adr-0082'`. **La webapp debe tipar (`?`) y pintar** — la lista completa está en *Consequences* del ADR;
el gate (F) de paridad compara `council.vocabulary` (`GET /council/membership`) con los unions de `types.ts` y con TODOS los
fixtures.

**BD (aditivo, `db._migrate` por dialecto — lección ADR-0078):** `plans` gana `origin`, `council_state VARCHAR(96)`,
`council_json`, `council_ledger_json`, `council_usage_json`, `council_claimed_by/_at`, `council_started_at`,
`council_finished_at`, `council_last_event_at`, `council_approved_by/_at`, `council_error`; `runs` gana `council_json` (la
COPIA server-side al encolar); tabla NUEVA `plan_events` (espejo exacto de `run_events`, PK `(plan_id, seq)`, sin FK a
`runs`); índice `ix_plans_council_state`. Reaper: hilo propio `council-reaper` (`council_jobs.reaper_loop`) con el MISMO
`WITT_REAP_STALE_S` → `errored (worker-lost)`; al arrancar, todo job `running` cae `errored (worker-lost-restart)`; jamás
se re-encola. Kill-switch `WITT_COUNCIL=0`: cero hilos, cero siega, cero llamadas, cero `stage.council.*`; `POST /runs`
sin 409; el frozen tiene el keyset Y los valores de 1.10 + `council {state 'disabled (…)'}` con las excepciones DECLARADAS
en el ADR (L.2).

**Semáforo y `Retry-After` (D.1, TODA llamada Anthropic):** `composite_auditor._anthropic_tool_call` adquiere un
`BoundedSemaphore(WITT_ANTHROPIC_MAX_INFLIGHT)` de PROCESO alrededor de `urlopen` (consejo, síntesis, elicitación, planner,
jueces; `meta.queue_wait_s` medido), honra `Retry-After` en `http-429/529` con tope `WITT_ANTHROPIC_RETRY_AFTER_CAP_S`
(`meta.retry_after_honored_s`), acepta `tools=` (los TRES del consejo, bytes idénticos en r1/r2/r3; `tool_choice` cambia y
CONSERVA la caché de tools+system) y `system` como lista de bloques con `cache_control`. El caller de hoy (2-tupla, `[tool]`,
`system` str) sigue byte a byte. El semáforo acota PETICIONES en vuelo, no tokens/minuto — se declara (L.7).

**Variables de entorno nuevas (ADR-0082; 27 = `models.ENV_ADR_0082`)** — default declarado en `models.ENV_TABLE`; lector
tolerante en tiempo de llamada (vacía/basura → default con fuente); el valor efectivo viaja en el registro; **toda env
implica reinicio** (el compose lo dice en su bloque ADR-0082):

| Variable | Default | Lector | Efecto / fuente declarada |
|---|---|---|---|
| `WITT_COUNCIL` | `1` | `council.enabled` · `app.create_plan` · `runs.execute_run` · `council_jobs.start_council_workers` | kill-switch global: `0` = sin job en el plan, `POST /runs` sin 409, sin r2/r3, componente `state 'kill-switch WITT_COUNCIL=0'` (`gating false`), `build_search_plan(directives=None)`, camino `9d90c01` con las excepciones de (L.2) |
| `WITT_COUNCIL_FULL` | `0` | `agent_matrix.council_members` (al ENCOLAR r1; la corrida usa la N congelada en el plan) | `1` = los 8 operativos también se sientan (N=25, cuórum 15); requisitos `from_operative` contados aparte; E5: sólo A/B |
| `WITT_MODEL_COUNCIL` | vacía → `claude-opus-5` (g2) · `claude-opus-4-8` (g1) | `models.resolve_role('council')` | modelo de los 17 miembros; `frozen.council.model.source`; `fable` rechazado `excluded-model`; tope `max_tokens.council` 4000/1200 |
| `WITT_COUNCIL_EFFORT` | `medium` (`inherit` = hereda `WITT_ANTHROPIC_EFFORT`) | `models.council_effort` → `council.build_request` | `output_config.effort` FIJO por ruta para las 3 rondas (cambiarlo por petición invalida la caché); sólo a modelos `thinking_default 'adaptive'`; E2 se decide con `thinking_tokens` de LG1 |
| `WITT_CG_COUNCIL_COMPONENT` | `1` | `competence.env_config` | `1` = `council_uncovered_must` GATEA cuando `state ∈ {checked, vacuous, incomplete}`; `0` = informativo declarado (fuera de `conjunction`) |
| `WITT_COUNCIL_RECOVERAGE` | `1` | `runs.execute_run` | `1` = ronda r3 (sólo si `n_admitted_total > 0`, sólo dueños de must sin cubrir); `0` = `post_search.state 'not-run (kill-switch …)'` |
| `WITT_COUNCIL_ORIGINS` | `production` | `app.create_plan` · `council_jobs.council_origins` → `db.claim_next_council_plan(origins=)` (CSV tolerante; `all` = sin filtro declarado) | orígenes del PROCESO que encolan r1 y que el worker RECLAMA; `smoke/fixture/dev-offline` → `'not-requested (origin …)'` — cero llamadas de opus-5 por fixture |
| `WITT_COUNCIL_WORKERS` | `1` | `runs.start_council_workers` → `council_jobs.start_council_workers` | hilos daemon `council-worker-N` que reclaman `plans.council_state='queued'`; `0` = `not-started` declarado |
| `WITT_COUNCIL_DEDUP_S` | `600` | `app.create_plan` → `db.plans_council_pending` | ventana del dedup del doble clic (misma pregunta+entidades+padre, mismo usuario, r1 `queued|running` → se reutiliza el plan vivo, `plan_response 'reused'`) |
| `WITT_COUNCIL_MAX_QUEUED_PER_USER` | `3` | `app.create_plan` → `db.count_plans_council` | tope de jobs r1 `queued` por usuario; el excedente nace `'not-requested (queue-cap per user)'` (el plan sí se crea) |
| `WITT_COUNCIL_CONCURRENCY` | `6` | `council.run_round` (clamp 1..25) | `max_workers` del pool por ronda; el miembro #1 va SOLO y el resto tras su respuesta (`stagger_wait_s`) |
| `WITT_COUNCIL_MEMBER_TIMEOUT_S` | `120` | `council.run_round` · `_anthropic_tool_call(timeout=)` | timeout por miembro; vencido → fila `timeout` (abandonado y contado), la ronda sigue |
| `WITT_COUNCIL_ROUND_BUDGET_S` | `300` | `council.run_round` | presupuesto de reloj por ronda; agotado → `skipped-budget` (cero llamadas), en vuelo abandonados y contados (`abandoned_cost_upper_usd` [E]); regla `≤ WITT_REAP_STALE_S − 300` |
| `WITT_COUNCIL_MEMBER_RETRIES` | `1` | `council.run_round` → `_anthropic_tool_call(retries=)` | intentos ADICIONALES por miembro (transporte con `Retry-After`; contenido); `refusal`/4xx nunca; `attempts ≤ 2`; todo gasto de todo intento se suma |
| `WITT_COUNCIL_QUORUM` | `0.6` | `council.quorum_required` (vía `council.config`) | fracción de miembros válidos (`ceil(q·N)`: 17 → 11, 25 → 15; un `not-applicable` emitido por el miembro CUENTA); fuera de (0,1] → default declarado |
| `WITT_COUNCIL_MAX_REQUIREMENTS` | `24` | `council.aggregate_r1` (alias `aggregate_requirements`) | tope del ledger; `truncated`, `n_truncated`, `truncated_ids[]` |
| `WITT_COUNCIL_MAX_PER_MEMBER` | `5` | `council.validate_tool_input` (el schema fija `maxItems 5`: es identidad de la caché) | requisitos por miembro que el CÓDIGO conserva; excedente descartado en orden y contado (`n_dropped_over_cap`) |
| `WITT_COUNCIL_R2_EVIDENCE_CHARS` | `24000` | `council.payload_r2` | tope de la vista de evidencia por miembro en r2/r3; `payload_truncated` declarado; acota tokens/min |
| `WITT_COUNCIL_ATTESTATION_CHARS` | `4000` | `app` (ledger) · `council.apply_ledger_decisions` | tope de `knowledge_now` y de cada `attested_text` (íntegros en `plans.council_ledger_json`; 600 en el frozen, `truncated`) |
| `WITT_COUNCIL_CACHE` | `1` | `catalog_cards.cache_config` → `council.build_system` | `1` = `cache_control` en los DOS bloques `system` (prefijo compartido + ficha VERBATIM); `0` = string concatenado (A/B medible en `usage.cache_*`) |
| `WITT_COUNCIL_CACHE_TTL` | `5m` | `catalog_cards.cache_config` → `council.build_system` | `5m` (escritura 1.25×) · `1h` (2×) para la ficha; con `1h` el bloque A también va `1h` (regla de la API: una entrada 1h precede a las de 5m); E3 tras medir `hit_ratio_r2` |
| `WITT_COUNCIL_INDEX` | `1` | `council_index.enabled` · `app` | `0` = `GET /council/search` 503 declarado, `prior_observations {state 'disabled'}`; `/council/demand` sigue contando |
| `WITT_COUNCIL_PRIOR_K` | `5` | `council_index.prior_observations` (clamp 0..12) | observaciones previas inyectadas en r1 como PRIOR ART (letras `P-A…`); `0` = ninguna |
| `WITT_COUNCIL_PRIOR_KINDS` | `requirement,coverage,decision,gap_flag,panel_finding` | idem (CSV tolerante) | kinds que ENTRAN al prompt de r1; `comment` EXCLUIDO por default (inyección, R8); la búsqueda siempre puede pedirlo |
| `WITT_COUNCIL_INDEX_ORIGINS` | `production` | `council_index` · `/council/demand` | orígenes del corpus (NULL incluido y declarado, regla de `precedent`) |
| `WITT_ANTHROPIC_MAX_INFLIGHT` | `8` | `composite_auditor.inflight_limit` → `_INFLIGHT` | `BoundedSemaphore` de PROCESO alrededor de `urlopen` para TODA llamada Anthropic; `meta.queue_wait_s` |
| `WITT_ANTHROPIC_RETRY_AFTER_CAP_S` | `30` | `composite_auditor.retry_after_cap` | tope al `Retry-After` honrado en `http-429/529`; sin cabecera, el backoff de hoy |
| `WITT_REAP_STALE_S` | `900` (ya existe, ADR-0078) | `runs.reaper_loop` · `council_jobs.reap_stale_s_of` → `db.reap_stale_council_plans` | sin cambio; el mismo umbral siega jobs de plan huérfanos (`errored (worker-lost)`) |

**Gates NO-SPEND (máscara de siempre + `WITT_RUN_ORIGIN=smoke`; UNA `.db` por smoke; conteos MEDIDOS por C9 el
2026-09-15/16 — 37/37 en verde; la tabla completa vive en el ADR):** NUEVOS `smoke_catalog_cards.py` **57/57** (31 fichas,
shas por substring exacto, un byte mueve SÓLO su sha, `build_system` puro) · `smoke_agent_matrix.py` **46/46** (34 filas, cm-1
exacto, 19/34 componentizadas, 17/25) · `smoke_council.py` **64/64** (27 mediciones con 17 miembros FAKEADOS: válidos,
duplicados, caídos, timeout, ids alucinados, fuera de vocabulario, campos prohibidos, tool equivocado, cancelación, eventos
desde el hilo llamador) · `smoke_council_jobs_db.py` **57/57** (migraciones ×2 + SQL compilado para `postgresql`, claim
atómico con `run_id IS NULL`, persistencia incremental, reaper, kill-switch) · `smoke_council_http.py` **69/69** (las 8 rutas
+ 409/400 del ledger + `/usage.plans_council`, sobre la superficie E.1 REAL) · `smoke_council_index.py` **63/63** (corpus por
origen, kinds, `prior_observations` sin `comment`, `demand`, BD sin migrar simulada); TOCADOS `smoke_run_pipeline.py` **297/297**
(contrato 1.11, orden de la traza, componente gateante, kill-switch keyset+valores 1.10 salvo excepciones,
`frozen.models.roles.council == stage.models.roles.council`), `smoke_competence.py` **38/38** (`cg-4`),
`smoke_search_harness.py` **65/65** (UNIÓN de directivas; sin directivas byte-idéntico), `smoke_models.py` **87/87** (rol
`council`, `CACHE_MULTIPLIERS`, `ENV_TABLE 48 ⊆ compose ∩ README`, gate M.4 de literales en PASS), `smoke_panel_quorum.py`
**40/40** · `smoke_openai_responses.py` **79/79** (caller: `tools=`, `system` lista, semáforo, `Retry-After`),
`smoke_usage_http.py` **32/32**, `smoke_thread_context.py` **40/40**, `smoke_runs_list_http.py` **24/24**,
`smoke_gate_citations.py` **52/52**; los 21 restantes sin cambio (conteos en la tabla del ADR). Todos con
`urllib.request.urlopen` bloqueado y contado = 0 donde se mide y `mcp_cache` byte-idéntico. Estático:
`smoke_live_council.py --dry-run` (exit 0 medido 2026-09-15: 3 filas — 20 cuerpos de `count_tokens` construidos, miembro
`literature-monitor` r1 y r2 con cuerpo REAL capturado: `system` 2 bloques con `cache_control` (sha A == `SHARED_BLOCK_SHA`,
sha B == `CARDS[agent].sha`), `tools` ×3 byte-idénticos a `council.TOOLS`, `tool_choice` forzado, `max_tokens 4000`,
`output_config.effort 'medium'`; `urlopen` reales 0; `db` no importado).

**Gates EN VIVO (los corre Emmanuel; cada uno gasta lo que dice; ningún smoke del CI gasta; el resultado se anota en el ADR
como MEDICIÓN con fecha).** El instrumento es `analysis/scripts/smoke_live_council.py`: usa el código REAL
(`council.build_request` / `council.default_caller` / `council.run_round` / `council.aggregate_r1` /
`composite_auditor._anthropic_tool_call(return_meta=True, tools=)`), imprime fila · `kind` · `usage` con caché ·
`thinking_tokens` · latencia por llamada, escribe `analysis/outputs/live_council_<fecha>.json` SIN secretos, rehúsa correr sin
llave (`no-api-key`, exit 2), jamás toca la BD (no importa `db`/`runs`/`app`: medido en cada salida); `--dry-run` construye y
muestra sin red (el único modo que corre C9). Python: `dev/.venvs/witt-query-service` con la llave en el entorno del proceso.

1. **LG1 · MEDIR el prefijo y UNA ficha real ANTES de encender** (≈ 20 `count_tokens` = USD 0 + 2 llamadas reales ≤ 0.10 USD):
   `python analysis/scripts/smoke_live_council.py --count-tokens` → tokens de `[tools ×3 + bloque A + §7]` (**debe ser ≥ 512**
   o la caché no escribe — si no llega, el bloque A se completa con las reglas §7 íntegras, declarado) y de las 17 fichas
   (sustituye "≈ 0.3k tok de media"); `--member literature-monitor --round r1 --repeat 2` → `tool_use` válido con todos los
   `required` bajo `max_tokens 4000`, `stop_reason 'tool_use'`, 1ª llamada `cache_creation_input_tokens > 0`, 2ª
   `cache_read_input_tokens ≈ prefijo` y `creation ≈ 0`; `thinking_tokens` y `output_tokens` impresos (E2 se decide con esta
   cifra); latencia; `--round r2` mide el payload de cobertura. Opcional `--full-r1 --question "…"` (17 llamadas ≈ 0.8–1.5
   USD [E]): la ronda 1 completa por el mismo código del worker, sin plan ni BD — cuórum, `stagger_wait_s`, caché por miembro,
   `n_unsatisfiable`, `aggregation_sha`.
2. **LG2 · Un plan real en prod (17 llamadas r1):** `POST /runs/plan` responde al instante con `council.state 'queued'`; p95 del
   request MEDIDO contra el timeout del proxy Traefik/Dokploy; `GET /plans/{id}/stream` entrega 17 `stage.council.member` +
   `progress` sin cortarse y llega a `applicable` en < 300 s; `n_valid/17`, `n_unsatisfiable`, `cache_read` ≥ 16 lecturas del
   prefijo; ledger visible en M3; aprobar con 1 discard razonado y 1 aporto; `POST /runs` sin 409.
3. **LG3 · Esa corrida:** Traza con `stage.council.ledger`, `round{r2}`, `coverage{pre}`, `stage.competence` con
   `council_uncovered_must checked`, si hubo must sin cubrir `stage.council.directives` + `stage.search.plan {families_source
   'directives+default'}` con una familia directive-only entrando, `round{r3}` sólo si `n_admitted_total > 0`; `frozen.council`
   íntegro; `by_stage.council_r1 'copied-from-plan_json'` + `r2/r3` con caché; `hit_ratio_r2` medido (decide E3); M8 cuadra.
4. **LG4 · A/B con y sin consejo** (8 corridas ≈ 12–20 USD [E]; 2 con `WITT_COUNCIL_FULL=1` — E5): descriptivo, sin poder.
5. **LG5 · Presión sobre el proveedor** (2 corridas simultáneas + 1 plan): cero `http-429` no reintentados, `queue_wait_s > 0`
   en alguna llamada, ningún `skipped-budget`; con `WITT_COUNCIL_MEMBER_TIMEOUT_S=5` filas `timeout` y la ronda sigue.
6. **LG6 · Kill-switch en prod** (`WITT_COUNCIL=0`): sin `stage.council.*`, plan sin job, `POST /runs` directo,
   `panel_signature` igual — el camino de `9d90c01`.
7. **LG7 · `GET /council/search`** tras ≥ 3 corridas cerradas con consejo; `prior_observations {n ≥ 1}` en el siguiente plan;
   `GET /council/demand` con conteos y `fired`.
8. **LG8 · Redeploy:** `_migrate` añade columnas y `plan_events` en el Postgres real; planes pre-ADR se leen `'pre-adr-0082'`;
   un job r1 a medio correr queda `errored (worker-lost-restart)`; docker-compose con las 27 env; `/config-history` gana
   `role.council` / `council.*`.

**Decisiones abiertas (E1–E6, defaults aplicados; el ADR las lista):** E1 must `unsatisfiable-by-harness` NO gatea (se cuenta) ·
E2 `WITT_COUNCIL_EFFORT=medium` · E3 TTL `5m` · E4 409 hasta aprobar/saltar · E5 sintetizador ciego y `WITT_COUNCIL_FULL=0` en
prod · E6 texto de `budget_approval` `<pendiente E6>`.

### Figuras de papers como evidencia OBSERVADA, dos lentes con visión y el PDF completo (ADR-0083, 2026-09-15 — **Proposed**; conteos de gates MEDIDOS por F8 el 2026-09-16: 41/41 smokes exit 0 (tabla en el ADR))

**Qué es.** Hasta `ca9a03d` (contrato 1.11) el XML JATS de cada paper OA ya estaba en disco (`fetch_paper.fetch_external`
cachea `raw_paper_<cid>_<stamp>_fulltext.xml`, ADR-0078) y el parser lo tiraba: `_xml_to_text` borra `<graphic>` y reduce
`<fig>` a texto — el `xlink:href` y el `@id`, la única vía determinista de bajar y nombrar una figura, se perdían (MEDIDO:
12 XML JATS en `mcp_cache`, 60 `<fig>`, 2 sin `<caption>`). Desde ADR-0083 **`analysis/scripts/lib/figures.py`** (stdlib puro,
`MODULE_VERSION 'fig-1'`, `PARSER_VERSION 'jats-fig-1'`, `LICENSE_TABLE_VERSION 'lt-1'`) parsea los `<fig>` (matcher `<fig\b(?!-)`:
la trampa `<fig-count>` tiene golden), lee la **licencia por REGLAS ORDENADAS sobre `<permissions>`** con dos fuentes (XML >
`license` del search de EPMC, `conflict` declarado; 9 formas medidas en los 12 XML) y baja **UN zip por paper**
(`GET {EPMC}/{PMCID}/supplementaryFiles`, verificado 200) del que extrae SOLO las entradas cuyo basename == `graphic_href` (jamás
`s00N.pdf/.xlsx`, jamás el `.gif` thumb). **Una figura es MEDICIÓN sólo como source-pointer**: identidad (`fig_id` del JATS) +
bytes (`sha256` de los bytes ORIGINALES, recalculado al gatear, al servir y al embeber — ADR-0077) + licencia (tabla CERRADA:
`cc-by`/`cc0`/`cc-by-sa` embebibles; `cc-by-nc`/`nd`/`nc-sa`/`nc-nd` y `cc-by-prose-unconfirmed` NO embebibles pero visibles al
panel (E2); `unknown` se baja y verifica pero NUNCA se embebe ni viaja a un tercero; `zfin-display-only` jamás bytes). **Lo que la
imagen DICE es JUICIO** de exactamente dos lentes del panel (`WITT_FIGURES_VISION_LENSES=evidence-grounding,reproducibility`) que
lo reportan SOLO en `figure_readings` (`figure_readings_class 'model-judgment'`; regla literal `FIGURE_READING_RULE`: «NEVER derive,
read off or estimate numbers … from an image»); **el sintetizador recibe caption + metadatos (`_PROMPT_FIGURE_KEYS`) y JAMÁS bytes**
(assert: ninguna b64 ni `data:image` en `frozen_record_json`, `bundle_json` ni en el `user_text`); el lazo panel → revisión se cierra
(`_panel_findings[].from_vision_lens` + frase en la `instruction`). Los bytes viven FUERA del registro (ADR-0074) en
`<WITT_MCP_CACHE_DIR or mcp_cache>/figures/<PMCID>/<href>` con ledger raw por PMCID, TTL + evicción LRU con tope, y se sirven por
`GET /runs/{id}/figures/{sha256}` (403 por licencia, 409 si el sha no cuadra: JAMÁS se sirve un byte que no cuadre). §7 gana la regla
que no existía — **«figure-only NOT asserted»** (CLAUDE.md §7; `verify_output.figure_only_not_asserted`).

**La corrida.** Etapa PROPIA `stage.figures` en `runs.execute_run` tras `stage.path_b` y antes de pass2 (SOLO si hubo Ruta B;
`answer_pipeline.py` no se toca): selección DETERMINISTA — papers `europepmc|pubmed` con PMCID + XML en `raw_cached`, orden
`selection_rank`, primeros `WITT_FIGURES_MAX_PAPERS`; figuras en orden de documento, primeras `MAX_PER_PAPER`, tope `MAX_PER_RUN`; el
resto `not-fetched (paper-cap | run-cap)` con caption parseado — presupuesto propio (`WITT_FIGURES_BUDGET_S`, por paper `min(45,
restante)`, socket `min(30, restante)`), latido `stage.figures.paper {phase 'start'}` ANTES de cada descarga (hueco ≤ 45 s < 300 s
del watchdog) y `{phase 'done'}` después, `stage.figures.figure` por figura verificada, `stage.figures.summary`. Una figura que no
baja deja fila declarada (`not-fetched (<razón cerrada>)` / `error: <Tipo>: <msg>`) y la corrida sigue (§6). Citas `kind 'figure'`
(`'<PMCID>#<fig_id>'`; el caption es el pasaje) suben la MISMA escalera de ADR-0080 sin peldaños nuevos y ganan `figure_verification
{bytes, content, figure_id}`; **cinco predicados DETERMINISTAS** en `verify_output` (`deterministic_checks.figures`): `figure_id_resolves`
(DURO), `figure_sha_matches` (DURO sólo en MISMATCH: sha alterado = inadmisible; no bajada = `n_not_verifiable`, ausencia ≠ alteración),
`figure_only_not_asserted` (DURO: una afirmación POSITIVA cuyas citas válidas son TODAS figuras es inadmisible), `figure_numerals_grounded`
e `figure_license_known` (INFORMATIVOS, `gating false`, congelados). Sin figuras en el bundle → `state 'no-figure-citations'` y la
conjunción de hoy. `models.MODELS` gana `vision_tier` y `models.vision_tokens()` es la ÚNICA sede de la fórmula pública de tokens de
visión: `by_stage.panel.by_model[*].vision {…, class 'proyección'}` (los `input_tokens` medidos YA incluyen las imágenes: nada se suma
dos veces; el reenvío por intento/ronda se MIDE en `figures.vision.sent`).

**Registro congelado 1.12** (aditivo): `frozen.figures {state ∈ attached | no-path-b | no-papers-with-xml | kill-switch WITT_FIGURES=0 |
error: …, module_version, parser_version, license_table_version, license_table (efectiva), license_table_rule,
license_table_env_ignored, mechanism, cache {dir_source, dir_state, ttl_days, cache_max_mb, evicted_n}, budget {total_s, used_s,
over_budget}, caps {… cada uno {value, source}}, n_papers_eligible … n_unknown_license, n_cited, zfin_figures_state, selection, vision
{state, lenses, lenses_source, rule, openai_detail, sent, cost_projection}, items [FigureItem], vocabulary, kill_switch?}`;
`citations[].kind += 'figure'` + `figure_verification`; `citations_support_summary.figure_citations`; `deterministic_checks.figures`;
`audit.panel[] += saw_figures {n, sha256s[], bytes_b64_total, detail}`, `figure_readings?`, `figure_readings_class?`,
`figure_readings_dropped?`; `audit.vision`; `token_usage.by_stage.panel.by_model[*].vision`; `agents_invoked` fila `figures`;
`epistemic_summary.figures_state / figures_n_verified / figures_n_cited` (null = < 1.12 o kill-switch; 0 = medido). **Históricos: NADA se
recalcula ni se backfillea** — registros < 1.12 no ganan `figures`; la webapp y el PDF los leen 'NO INSTRUMENTADO (contrato < 1.12)'.
**La webapp debe tipar (`?`) y pintar** — la lista completa está en *Consequences* del ADR; el gate (F) de paridad compara
`frozen.figures.vocabulary` (`figures.LICENSES`, `LICENSE_TABLE`, `BYTES_STATES_*`, `FIGURES_STATES_*`, `SERVABLE_STATES`,
`VISION_LENSES`, `SAW_FIGURES_DETAILS`) con los unions de `types.ts` y con TODOS los fixtures; el gate (D) del PDF exige 0 huecos.

**Kill-switches (cada uno con default declarado):** `WITT_FIGURES=0` → no se parsea ni baja nada, los papers NO ganan `figures`, el
`user_text` del sintetizador es el de 1.11 BYTE A BYTE, el panel no recibe imágenes ni `saw_figures`/`audit.vision`, `GET
/figures/{sha}` 404; **el frozen es igual al 1.11 del MISMO fixture salvo EXACTAMENTE `{render_contract_version, figures {state,
kill_switch}, deterministic_checks.figures {state}}`** (lo mide `smoke_run_pipeline.py` listando cualquier otro path). `WITT_FIGURES_VISION=0`
→ figuras observadas siguen (captions, bytes, GET, escalera, predicados) pero NINGUNA lente recibe imágenes (`saw_figures.detail
'kill-switch WITT_FIGURES_VISION=0'`). `WITT_FIGURES_PDF_THUMBS=0` → palabras + enlace aunque la licencia permita.

**Caché y Dokploy (E4).** `figures.cache_dir()` honra `WITT_MCP_CACHE_DIR` como las tools Layer 0 (`frozen.figures.cache.dir_source ∈
env | default`, `dir_state ∈ writable | read-only | missing` medido al inicio de la etapa; read-only → filas `not-fetched (cache-read-only)`).
Sin volumen, tras cada redeploy `GET /figures/{sha}` → 404 `bytes-not-in-cache` declarado y el PDF/Hoja pasan a 'enlace + sha' (honesto,
no roto); el registro (sha, dims, licencia) sigue íntegro. Recomendación operativa: montar volumen para `WITT_MCP_CACHE_DIR` antes de
LG3 (también beneficia al TSV de ZFIN y al caché de papers); LG6 mide.

**Variables de entorno nuevas (ADR-0083; 20 + `WITT_MCP_CACHE_DIR` = `figures.ENV_VARS`, 21)** — default declarado en
`figures.ENV_SPECS`; lector tolerante EN LA LLAMADA (`figures.env_config()`: vacía/basura/fuera de clamp → default con fuente
`default-unset:<VAR>` | `default-invalid-env:<VAR>`); el valor efectivo y su fuente viajan en `frozen.figures.caps/cache/budget`;
`models.ENV_TABLE` gana las mismas filas (F3) y `smoke_models` mide `ENV_TABLE ⊆ compose ∩ README`; **toda env implica reinicio** (el
compose lo dice en su bloque ADR-0083):

| Variable | Default | Lector | Efecto / fuente declarada |
|---|---|---|---|
| `WITT_FIGURES` | `1` | `runs._figures_stage` · `audit()` · `app` | kill-switch maestro; `0` = frozen 1.11 byte a byte salvo las 3 excepciones (M.1) |
| `WITT_FIGURES_VISION` | `1` | `audit()` | `0` = ninguna lente recibe imágenes; captions/sha/licencia siguen (M.2) |
| `WITT_FIGURES_VISION_LENSES` | `evidence-grounding,reproducibility` | `composite_auditor.vision_lenses` | CSV de **≤ 2** lentes validado contra `models.LENSES`; inválido → default declarado (`lenses_source 'default-invalid-env'`); > 2 lentes → default declarado `'default-invalid-env:… (>2 lenses)'` (`VISION_LENSES_MAX = 2`, CLAUDE.md §7 «at most two panel lenses» — *corrector*) |
| `WITT_FIGURES_MAX_PAPERS` | `3` | `runs._figures_stage` · `figures.attach` | papers (con PMCID + XML) de los que se parsean/bajan figuras, orden `selection_rank` (clamp 1..50); resto `not-fetched (paper-cap)` |
| `WITT_FIGURES_MAX_PER_PAPER` | `9` | `figures.attach` | figuras por paper en orden de documento (clamp 1..30) |
| `WITT_FIGURES_MAX_PER_RUN` | `12` | `figures.attach` | tope de figuras bajadas por corrida (clamp 1..200); resto `not-fetched (run-cap)` |
| `WITT_FIGURES_MAX_PER_LENS` | `12` | `figures.select_for_panel` | imágenes por petición de juez (clamp 0..20: ≤ 20 evita «many-image requests») |
| `WITT_FIGURES_MAX_IMAGE_MB` | `5` | `figures.select_for_panel` · PDF | bytes CRUDOS por imagen para panel/miniatura (clamp ≤ 7: 9.3 MB b64 < 10 MB de la API) |
| `WITT_FIGURES_ZIP_MAX_MB` | `40` | `figures.fetch_figures` | precheck `Content-Length` y tope de streaming → `not-fetched (zip-over-max)` sin escribir |
| `WITT_FIGURES_BUDGET_S` | `90` | `figures.attach` | reloj TOTAL de la etapa, fuera de la ronda de búsqueda; por paper `min(45, restante)` (constante declarada) |
| `WITT_FIGURES_TTL_DAYS` | `30` | `figures.fetch_figures` | frescura del ledger por PMCID; fresco + sha iguales → `cache_hit`, cero red; `≤0` = nunca confiar |
| `WITT_FIGURES_CACHE_MAX_MB` | `512` | `figures.fetch_figures` | tope de `figures/`; evicción LRU por mtime al escribir, `evicted_n`; `0` = sin tope declarado |
| `WITT_FIGURES_CAPTION_CHARS` | `2000` | `figures.parse_jats` | tope del caption que viaja (`caption_truncated`; clamp 100..20000); medido: media 1 030, máx 3 087 |
| `WITT_FIGURES_EMBED_LICENSES` | `cc-by,cc0,cc-by-sa` | `figures.LICENSE_TABLE` (vía `license_table(cfg)`) | sólo RESTRINGE la tabla `lt-1` (un id fuera → `license_table_env_ignored`); gobierna GET 200/403, miniatura Hoja y PDF |
| `WITT_FIGURES_PANEL_LICENSES` | `cc-by,cc0,cc-by-sa,cc-by-nc,cc-by-nd,cc-by-nc-sa,cc-by-nc-nd,cc-by-prose-unconfirmed` | `figures.LICENSE_TABLE` (idem) | licencias cuyos bytes ven las lentes (E2); `unknown`/`zfin-display-only` nunca (tabla, no env) |
| `WITT_FIGURES_PROSE_LICENSE` | `1` | `figures.parse_license` | prosa «Creative Commons Attribution» sin URL → `cc-by` (`license-p-prose`, visible en Hoja/PDF); `0` → `cc-by-prose-unconfirmed` (E3) |
| `WITT_FIGURES_OPENAI_DETAIL` | `high` | `_responses_kwargs` · `_openai_chat_call` (vía `figures.openai_*_parts`) | `detail` del `input_image`/`image_url` (`low\|high\|auto\|original`); a ≤ 840 px `high` = 2–4 tiles en gpt-4o |
| `WITT_FIGURES_REFETCH_ON_GET` | `0` | `app.get_figure_bytes` | `1` = ante `bytes-not-in-cache` UNA GET (20 s) y servir SOLO si sha == congelado (409 si no) |
| `WITT_FIGURES_PDF_THUMBS` | `1` | `record_pdf.build_pdf` | `0` = palabras + enlace aunque la licencia permita (M.3) |
| `WITT_FIGURES_COUNT_TOKENS` | `0` | `audit()` (lentes Anthropic) | `1` = `vision.tokens_measured` por `count_tokens` SIN imágenes (una llamada gratuita por lente) |
| `WITT_MCP_CACHE_DIR` | (ya existe, ADR-0080; vacía = `<repo>/mcp_cache`) | `figures.cache_dir` | las figuras la HONRAN (`<dir>/figures/`); `frozen.figures.cache.dir_source/dir_state`; sin volumen = efímera (E4) |

Constantes declaradas (viajan en `caps`/`constants` con `source 'constant (ADR-0083)'`): presupuesto por paper `min(45, restante)`;
socket `min(30, restante)`; restante `< 5 s` → `budget-exhausted` sin red; b64 por petición 8 MB; guardia 40 MP; miniatura ≤ 60 mm; ≤ 12
miniaturas por PDF; PDF ≤ 8 MB; `expose_headers` fijos.

**Gates NO-SPEND (máscara de siempre + `WITT_RUN_ORIGIN=smoke` + `WITT_MCP_CACHE_DIR=<tmp>`; UNA `.db` por smoke; conteos MEDIDOS por F8 el 2026-09-16 —
la tabla completa vive en el ADR):** NUEVOS `smoke_figures.py` (141/141 — corrector 2026-09-16; 135 F8: GOLDEN del parser sobre los 2 XML fixture y los 12 del `mcp_cache`
cuando existen — 'NO MEDIDO (mcp_cache ausente)' declarado si faltan —, licencia en sus 9 formas + `conflict`, fetch con el zip fixture
y fallos declarados, presupuesto con reloj falso, caché TTL/LRU/read-only, `select_for_panel`, bloques por transporte, `_xml_to_text`
byte-idéntico, `_normalize_hit.license`) · `smoke_panel_vision.py` (60/60 — corrector; 55 F8: cuerpos sin `user_content` byte-idénticos a los de 9d90c01; con
imágenes la forma exacta por transporte; `member['figures']` SOLO en las dos lentes; `saw_figures` 9/9/0/0; `figure_readings` →
`model-judgment`, string → `dropped`; `panel_signature` idéntico) · `smoke_figures_http.py` (43/43 — corrector; 42 F8: TestClient + frozen 1.12 sembrado + caché
TMP: 401/404/409, índice `servable`, bytes 200 con headers y body sha == path, NC 403, sha malformado 400, archivo borrado 404,
alterado 409, kill-switch, frozen 1.10 `not-instrumented`, `expose_headers` en el preflight) · `smoke_record_pdf.py` (56/56 — corrector; 54 F8: el gate de
COBERTURA (K): regex de la webapp copiada → 0 huecos, anidadas en bytes, born correcto 1.8/1.9/1.10/1.11/1.12, 5 frases de
`citations_schema`, regla del sha leída, miniaturas sólo BY+verified, determinismo, `urlopen` 0); TOCADOS `smoke_gate_citations.py`
(80/80 — corrector +3: cita paper alucinada o sin pasaje NO rescata la afirmación figure-only; 77 F8, +25: escalera con `kind 'figure'`, los 5 predicados), `smoke_run_pipeline.py` (372/372 — corrector +5: `audit_initial.vision`, colisión de `fig_id`, clasificador superset, `detail` en la proyección, `bytes_verified`; 367 F8, +65: contrato '1.12', orden de la Traza, pass1 sin
`figures`, sin b64 en ningún string, `frozen.figures` completo, **kill-switch keyset+valores 1.11 salvo EXACTAMENTE 3 excepciones**,
budget agotado, `_get_bytes` que lanza, cancelación; F8 +8 costuras (O) y assert GLOBAL anti-binario sobre la BD), `smoke_models.py` (96/96: `vision_tier`/`vision_tokens`, `ENV_TABLE (+20) ⊆ compose ∩
README`, `panel_signature` golden), `smoke_openai_responses.py` · `smoke_panel_quorum.py` (81/81 · 42/42, +2 c/u), `smoke_usage_http.py` (34/34, +2),
`smoke_fetch_paper.py` (44/44, +3: `license`), `smoke_council.py` (70/70: D.1 amplía la firma de `_anthropic_tool_call` con `user_content=None`). Estático (MEDIDO por F7 el 2026-09-16 con la máscara): **`smoke_live_figures.py --dry-run` exit 0**
— 4 filas (`pmcid` PMC11379296 con XML de fixtures y `_get_bytes` falseada con el zip fixture → `fetch_figures` REAL: 9 `verified`, sha ==
MANIFEST 9/9, dims == `scaled` 9/9, `dims_match` 9, licencia `cc-by (ext-link)`; bloques de los TRES transportes con 9 imágenes ANTES del
texto y la b64 decodificando al sha original: Anthropic `[text, image]×9 + text`, Responses `[input_text, input_image]×9 + input_text`,
Chat `[text, image_url]×9 + text`; con F3 aterrizado los TRES callers reales CAPTURADOS con `user_content=` (`content_equals_blocks True` ×3, `urlopen` bloqueado y cliente OpenAI falso; re-medido por F8 el 2026-09-16) — nada se llamó);
`urlopen` reales 0; `figures._zip_url` == `{EPMC}/{PMCID}/supplementaryFiles`; ningún módulo de BD importado; nada escrito.

**Gates EN VIVO (los corre Emmanuel; cada uno gasta lo que dice; ningún smoke del CI gasta; el resultado se anota en el ADR como
MEDICIÓN con fecha).** El instrumento es `analysis/scripts/smoke_live_figures.py`: usa el código REAL (`figures.fetch_figures` — la única
costura de red —, `figures.select_for_panel` con sha recalculado, `figures.anthropic_blocks / openai_responses_parts / openai_chat_parts` y
los callers `composite_auditor._anthropic_tool_call / _openai_responses_call / _openai_chat_call` con `user_content=`), imprime fila · `kind`
· `usage` · latencia, escribe `analysis/outputs/live_figures_<fecha>.json` SIN secretos ni b64 (cinturones anti-secreto y anti-binario),
rehúsa correr sin llave (`no-api-key`, exit 2), jamás toca la BD (`db_imported false` medido en cada salida); `--dry-run` construye sin
red (el único modo que corre F8). Python: `dev/.venvs/witt-query-service` con la llave en el entorno del proceso.

1. **LG1 · Bytes reales (red a www.ebi.ac.uk, 0 modelo):** `python analysis/scripts/smoke_live_figures.py --pmcid PMC11379296 --href-direct`
   → HTTP 200 `application/zip` (~8.6 MB), 27 entradas, 9 jpg con sha256 == MANIFEST del fixture y dims == `scaled`; `elapsed_s` y MB/s
   desde el VPS (calibra `WITT_FIGURES_BUDGET_S`); repetir con `PMC11647118` (NC) → 6 `verified`, `embeddable False`; un PMCID no-OA
   → `not-fetched (http-4xx)` declarado. `--href-direct` mide `europepmc.org/articles/{PMCID}/bin/{href}` (NO verificado): si 200 y sha ==
   miembro del zip → un 0083.1 aditivo lo declara como respaldo; si no, queda 'no verificado'.
2. **LG2 · `license` del search (1 GET):** `…/search?query=PMCID:PMC11379296&resultType=core&format=json` → `license: "cc by"` esperado.
3. **LG3 · UNA corrida real con `WITT_FIGURES=1`** (≈ 0.25–0.45 USD [E]): Traza `stage.figures.plan → paper(start/done) → figure×n →
   summary`, hueco de latido < 300 s; `frozen.figures.n_verified ≥ 1`; `saw_figures.n > 0` EXACTAMENTE en evidence-grounding y
   reproducibility; `attempts[].error_kind` sin `http-400`; `figure_readings` etiquetado; `deterministic_checks.figures.state 'checked'` y
   `n_marker_absent`; Δ `input_tokens` vs la misma corrida con `WITT_FIGURES_VISION=0`; tasa de falsos positivos de `figure_numerals_grounded`
   (decide 0083.1 → gating); con `WITT_FIGURES_COUNT_TOKENS=1` → `vision.tokens_measured` (calibra la fórmula, `vision_verified True`).
4. **LG4 · Formas de imagen por transporte (≤ 3 llamadas, ≤ 0.05 USD):** `--pmcid PMC11379296 --judge gpt-4o --api chat-completions
   --image 40877777ed82` → verdict ∈ VOCABULARY (la forma Chat Completions queda MEDIDA); `--judge gpt-6-astra --api responses --image <sha>`
   → verdict + `usage.input_tokens`; `--judge claude-haiku-4-5-20251001 --api anthropic --count-tokens` → Δ con/sin bloque = MEDICIÓN.
5. **LG5 · Puertas en prod:** `GET /runs/{id}/figures` → índice; `/figures/{sha}` cc-by → 200 image/jpeg con headers (y la webapp los LEE:
   CORS); cc-by-nc → 403 con license; sha inventado → 404; la Hoja muestra miniatura BY y placa NC.
6. **LG6 · Dokploy (E4):** `cache.dir_state 'writable'` en el registro; tras redeploy `GET …/figures/{sha}` → 200 (con volumen) o 404
   `bytes-not-in-cache` (sin volumen) — MEDICIÓN que decide E4; `/config-history` ganó `figures.enabled/figures.vision`.
7. **LG7 · `GET /runs/{id}/record.pdf` de LG3:** 52 secciones, miniaturas SOLO en CC BY, NC en palabras, 'CUORUM', 'MODELOS', 'ESQUEMA DE
   CITAS' con el literal correcto, 'vista por 2 lentes: JUICIO'; un 1.9 histórico → 'NO INSTRUMENTADO (contrato < 1.10)' para models.
8. **LG8 · webapp:** `python tools/parity_check.py` contra `contract-1.12-frozen` → (D) 0 huecos, 23 líneas `[pdf]` SALDADAS y retiradas,
   (F) vocabularios OK, EXIT 0; `gen_fixtures.py` regenera 1.12; vitest verde.
9. **LG9 · Held-out ADR-0072** tras el cambio de `SYNTH_TOOL.description` (E5): la serie `ab_trapped_scalar` sigue comparable; anotar Δ.
10. **LG10 · Presupuesto (3 corridas con figuras):** `figures.budget.used_s` p95 y `stage.figures.paper.elapsed_s`; p95 > 45 s → ajustar
    `WITT_FIGURES_BUDGET_S`/`MAX_PAPERS` en compose (declarado).

**Decisiones abiertas (E1–E5, defaults aplicados; el ADR las lista):** E1 `WITT_FIGURES=1` y `WITT_FIGURES_VISION=1` · E2 las dos lentes SÍ
ven bytes NC/ND (embeber sigue prohibido) · E3 prosa CC BY = `cc-by` con `source 'license-p-prose'` visible · E4 sin volumen, declarado
(`REFETCH_ON_GET=0`) · E5 texto de la aprobación presupuestal `<pendiente E5>`.

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

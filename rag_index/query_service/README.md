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
| POST | `/runs/plan` | ✓ | **el plan declarado** (ADR-0061): estructura del código + juicio del planner (nichos §3 + agentes §11 con gate resuelto por tabla) + estimaciones DETERMINISTAS por métrica. Se refiere por `plan_id`; se consume UNA vez (409 `plan_already_used`) |
| POST | `/runs` | ✓ | encola una corrida (async); terminal SIEMPRE post-audit (ADR-0049). **409 `index_offline`** si el índice está OFFLINE — bloquea, no degrada (dev sparse: `WITT_ALLOW_RUNS_OFFLINE=1`) |
| GET | `/runs` · `/runs/{id}` | ✓ | lista y detalle por la MISMA vista: `heartbeat_age_s` + `heartbeat_stale` + `heartbeat_stale_after_s` (el umbral viaja) + `token_usage` (gasto en TODO camino de salida, failed/cancelled incluidos) |
| GET | `/runs/{id}/record` | ✓ | el **registro congelado** que la UI renderiza (una fuente, tres lectores) |
| GET | `/runs/{id}/events?after=` | ✓ | **replay** — las mismas filas que el stream (una bitácora) |
| GET | `/runs/{id}/stream` | ✓ | traza viva SSE (keep-alive; cierra al drenar un estado terminal) |
| POST | `/runs/{id}/cancel` | ✓ | body `{reason}`; registra `cancelled_by` (sesión) + `cancel_reason` — una cancelación sin autor es un hueco en el registro (ADR-0055). Queued: inmediato; running: frontera de etapa |
| POST | `/runs/{id}/close` | ✓ | cierre explícito: congela el registro (`frozen_at`) — requisito para precedente |
| GET | `/usage?from=&to=` | ✓ | agregados M8 en el SERVIDOR: totals/by_user/by_model/most_expensive; tokens [M], costo PROYECCIÓN con `cost_class`; `rack_embeddings` aparte con su caveat (ADR-0056) |
| GET | `/config-history` | ✓ | historial de config verbatim + procedencia; históricos de usuarios/store DECLARADOS (ADR-0056) |
| GET | `/precedent/search?q=&k=` | ✓ | **la capa de precedente** (ADR-0053): corridas CERRADAS por relevancia, `admissible_as_evidence: false` estructural, scorer declarado; series de citas disjuntas (números=evidencia, letras=precedente) |

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

## Corridas (bloque 3, ADR-0049/0050)

Una corrida ejecuta: retrieve (la máquina de estados real de `answer_pipeline`, instrumentada por
`on_stage`) → síntesis (`claude-opus-4-8`) → gate determinista (`verify_output`) → **panel
composite-auditor** (Opus+Sonnet+Haiku+gpt-4o, 100% de las corridas) → `AUDIT_APPROVED|REJECTED` →
registro congelado en Postgres. Estados: `queued|running|awaiting_closure|closed|failed|cancelled`.
Gasto por corrida ~1–2.50 USD (medido en `usage`, sin caps — ADR-0047). Requiere `ANTHROPIC_API_KEY`
en el Environment del servicio. Gate: `smoke_run_pipeline.py` (91/91 offline; `smoke_query_service.py`
29/29). Contrato del registro: `render_contract_version 1.4` (ADR-0061: `plan` congelado + `plan_declared` +
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

Pass 1 es SIEMPRE DI-only (mide "¿mi store alcanza?"); si `pass1 < τ` (`WITT_FALLBACK_CONF_TAU`,
default 0.5) o la confianza viene ausente, dispara la Ruta B y corre pass 2 con la evidencia externa —
ambas confianzas + el **delta** quedan en el registro (`confidence {pass1, pass2, delta, by_subclaim,
state}`), junto con `fallback.trigger` (structural|confidence), `absence_kind`, citas tipadas
(`citations[{n, kind, id}]`) y `token_usage` (by_model medido, embeddings incluidos, costo etiquetado
como proyección). `render_contract_version: 1.1`.

## Pendiente (bloques siguientes)

- `Plan` condicional de M3 (planner) · serializador de series disjuntas + `PrecedentItem` (bloque 6).
- Bloque 5: cola de escritura cross-proceso, endpoint de detalle de propuesta, PAT del push-back.
- `/rack/node/{id}` (browse del grafo) — la operación `browse` aún no existe en ninguna puerta.
- Normalización de metadata entre ruta densa y sparse (residual §5.9, notado en ADR-0047).

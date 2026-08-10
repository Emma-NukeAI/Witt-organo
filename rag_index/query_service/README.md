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
| GET | `/query?q=&k=` | ✓ | **el sobre ADR-0043 verbatim**; degradado = 200 (la UI pinta la banda); `query_unavailable` = 503 |
| GET | `/resolve?key=` | ✓ | `VerifiedRecord` completo (bloque 1.4); NOT_FOUND = 200 con `resolved: false` |
| GET | `/raw?key=&filename=` | ✓ | drill al crudo (`fetch_raw`): URL presignada MinIO o source_url+sha256 |
| GET | `/status` | ✓ | **StoreStatus (9 campos) NO-SPEND** con caché TTL — ver abajo |
| GET | `/artifacts` | ✓ | índice de históricos (ADR-0046): `reports/*.html` + `evaluation/runs/**` |
| GET | `/artifacts/report/{name}` | ✓ | sirve un HTML histórico (path-safe por membresía) |
| GET | `/artifacts/run/{set}/{name}` | ✓ | un run histórico (JSON; `instrumented: false` = sin `decision_state`) |
| GET | `/rack/search` · `/rack/resolve` · `/rack/status` | ✓ | alias de la superficie propuesta por la UI |

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
   usa el ingest service (`NEO4J_*`, `OPENAI_API_KEY`, `MINIO_*`) + `WITT_BACKEND_DB_URL`.
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

## Pendiente (bloques siguientes)

- `POST /runs` + stream SSE + modelo de corrida (bloque 3, con el composite-auditor invocable).
- `/rack/node/{id}` (browse del grafo) — la operación `browse` aún no existe en ninguna puerta.
- Normalización de metadata entre ruta densa y sparse (residual §5.9, notado en ADR-0047).

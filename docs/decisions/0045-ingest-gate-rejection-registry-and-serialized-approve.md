# ADR-0045 — El gate del ingest service registra sus decisiones: rechazo archivado (nunca borrado), `/approve` serializado, `created_at` + orden FIFO real

- **Status:** Accepted — autorizado por Emmanuel en sesión 2026-08-09: *"no importa qué toquen [la maquinaria de la] DATA INAMOVIBLE, donde se necesita el gate es para alguna ingesta o modificación [de datos]"* — es decir, el gate humano aplica a las mutaciones de datos, no a corregir el código del servicio. Parte del paquete de correcciones pre-UI (handoff webapp 2026-08-04).
- **Relates:** ADR-0017/0021 (ingest service + contributor workflow), ADR-0022 (mutaciones DI human-gated con especificación), decisión 9-bis del handoff webapp (histórico de cambios a la DI — este ADR siembra su semilla, el registro completo es bloque 5).
- **Affects:** `rag_index/ingest_service/app.py` (+`.gitignore`). **La política de mutación de la DI no cambia:** mismo gate humano, mismo `ingest.py` MERGE-only, mismo flujo submit→approve. Cambia la *contabilidad* del gate y su seguridad ante concurrencia. **NUEVO** gate determinista `rag_index/ingest_service/smoke_ingest_gate.py` (offline; Neo4j/GitHub stubbeados — cero mutación real).

## Context

Verificado el 2026-08-09 (fase 1 del trabajo de backend, hallazgos §5.3/§5.5 del handoff):

1. **`/reject` era destrucción silenciosa:** borraba el archivo de la propuesta y devolvía `200` aunque el `sid` no existiera; sin autor, sin razón, sin registro. El estado `rejected` existía en el esquema pero ningún código lo escribía. Incompatible con el histórico de cambios a la DI (decisión 9-bis) y con la naturaleza de un gate humano: un rechazo es una *decisión*, no una limpieza.
2. **`/approve` corría sin serialización:** dos aprobaciones simultáneas calculaban el mismo `_next_id`, corrían dos re-ingestas completas contra el mismo Neo4j, y el segundo PUT a GitHub fallaba por `sha` con los datos ya escritos — el estado *"aplicado en Neo4j pero NO en git"*, media ingesta, que rompe la inamovibilidad y no tenía nombre.
3. **La cola no tenía orden:** ningún proposer escribía `created_at` y `/pending` ordenaba lexicográficamente sobre un `uuid4` — es decir, ningún orden.

## Decision

1. **`/reject` archiva, nunca borra.** Requiere `by` + `reason` no vacía (400 si falta); `404` real si el `sid` no existe; escribe la propuesta completa con `approval_chain[0] = {status: "rejected", rejected_by, reason, rejected_at}` en `rejected/` (append-only) y solo entonces la retira de la cola.
2. **`/approve` y `/reject` se serializan bajo un lock in-process** (`threading.Lock`): la sección crítica completa (leer manifest → `_next_id` → escribir manifest → ingest → git PUT → consumir cola) es atómica dentro del proceso. Un duplicado concurrente del mismo `sid` recibe `404` (idempotente por construcción). `approved_at` se registra en la cadena.
3. **`created_at` en cada propuesta** al momento del submit; `/pending` ordena por él (FIFO real) y lo expone.
4. **Action log append-only** (`actions_log.jsonl`): cada approve/reject con quién/qué/cuándo/outcome (incl. `git_sync` status, que ya nombraba el estado media-ingesta). Es la **semilla** del registro de cambios a la DI de la decisión 9-bis, no su versión final. Nunca lanza (patrón `server._log`): el registro primario de un approve es el manifest+git, de un reject el archivo archivado.

## Consequences

- Un botón de "Rechazar" en la webapp deja de ser destrucción anónima; el aprobador y el histórico existen.
- La carrera del doble-approve desaparece **dentro del proceso** (uvicorn corre esta app single-process hoy). **Residual honesto:** con múltiples workers/procesos el lock no cruza procesos — la *cola de escritura serializada concurrencia-1* real es entregable del bloque 5 (y su ADR), igual que el endpoint de detalle de propuesta (§5.4, el aprobador sigue firmando con 4 campos) y el PAT del push-back a git.
- El estado "aplicado en Neo4j pero NO en git" sigue siendo *posible* si el PUT falla (no se cambió la semántica); ahora queda **registrado** en el action log en vez de solo convertido a string en la respuesta.
- `queue/`, `rejected/` y `actions_log.jsonl` son estado de runtime del host del servicio (gitignored); su durabilidad más allá del host llega con el registro del bloque 5.
- La versión del servicio sube a `1.1`.

## Verification (offline, deterministic)

- `python rag_index/ingest_service/smoke_ingest_gate.py` → **10/10 PASS** (2026-08-09): 401/404/400 · orden FIFO por `created_at` · archivo de rechazo con veredicto+autor+razón · approve feliz con manifest tmp + `approved_at` · action log con ambas acciones · carrera same-sid → exactamente 1 éxito + 1 404 · cero colisión de `corpus_record_id`. Neo4j/GitHub stubbeados; **cero mutación de la DATA INAMOVIBLE**.

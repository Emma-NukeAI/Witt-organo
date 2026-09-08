# ADR-0077 — Comentarios de corrida: la conversación sobre la pregunta como anexo append-only, público y fuera del registro

- **Status:** Accepted — 2026-09-06. Origen: Emmanuel, al revisar el Banco de preguntas rediseñado
  (filas-log, ADR-0076), pidió "notas internas o comentarios" sobre una pregunta: que él pueda escribir
  sobre esa corrida, que los demás los consulten y puedan responder — "una especie de conversación" —,
  y que **no tenga nada que ver con calificar**. Pidió también que no afectara al backend en el sentido
  de la corrida: es un anexo a la pregunta, no un cambio a lo que la corrida registró.
- **Relates:** ADR-0047 (permisos planos: toda sesión válida lee todo) · ADR-0055 (lista y detalle
  sirven la MISMA vista) · ADR-0056 (autoría y hora las pone el servidor) · ADR-0064/0075 (las notas
  de calificación de M5 son OTRA cosa: juicio con instrumento, append-only y enmascaradas) · ADR-0074
  (el registro congelado es inmutable: este anexo no entra al blob) · Apuntes 2026-09-04 (el cuaderno de
  teorías: existe ANTES de la pregunta y su visibilidad es por apunte).
- **Affects:** `rag_index/query_service/db.py` (tabla `run_comments` + `create/get/list/count_run_comments`)
  · `app.py` (`GET/POST /runs/{id}/comments`, `n_comments` en toda vista de corrida vía `_con_comentarios`)
  · `smoke_run_comments_http.py` (gate nuevo) · `README.md` · witt-webapp: `src/api/{types,client}.ts`,
  `M3Corridas/ListaCorridas.tsx` (hilo + redactor en el detalle de la fila, conteo en la fila plegada),
  `tests/m3.test.tsx`. **Cero mutación de la DATA INAMOVIBLE, del registro congelado y de la corrida.**

## Context

1. **Para que los demás lo vean, tiene que vivir en el servidor.** Un comentario "sólo de UI" viviría en
   un navegador. La petición es compartida y conversacional: eso es una tabla y dos puertas, chicas.
   "No afectar al backend" se lee como lo que es: no afectar a la CORRIDA (su estado, su registro, su
   calificación), no como "no tocar el servidor".
2. **No es ninguna de las dos cosas que ya existen.** Las notas de M5 van clavadas a una calificación
   (juicio con instrumento, enmascaradas hasta el consenso). Los apuntes son teorías que nacen antes de
   la pregunta y cuya visibilidad decide el autor. Un comentario es otra cosa: prosa libre SOBRE una
   pregunta ya corrida, visible para todos, en orden de llegada. Meterlo en cualquiera de las dos tablas
   confundiría tres semánticas que el fundador ha separado a propósito (decisión 6 del 09-04).
3. **Una conversación se lee entera.** Borrar o editar un comentario dejaría un hueco en el hilo que los
   demás ya leyeron; el registro de este sistema es append-only en todo lo demás (eventos, ratings).

## Decision

**(1) Tabla `run_comments`** (`comment_id`, `run_id` → runs, `author_id` → users, `body`, `created_at`).
`create_all` la crea al arrancar; no hay columnas nuevas en tablas vivas.

**(2) Dos puertas, ambas con sesión:** `GET /runs/{id}/comments` devuelve la conversación en orden de
llegada con `author_name` desde `users` (procedencia: la cuenta, jamás el cliente), `n` y `body_max`;
`POST /runs/{id}/comments` guarda el cuerpo VERBATIM (recortado en los extremos), con autor y hora del
servidor; `201`. Vacío → `400`; más de 4000 caracteres → `400` con la cifra; corrida inexistente →
`404`. **No hay PATCH ni DELETE:** lo dicho queda dicho.

**(3) Público por diseño.** Toda sesión válida lee y escribe (permisos planos). A diferencia de los
apuntes, aquí no hay visibilidad por pieza: la conversación es del equipo.

**(4) `n_comments` viaja en TODA vista de corrida** (lista, detalle y la recién creada) mediante UNA
consulta agrupada por lista — nada de N+1. Es un conteo: medición. La fila plegada del Banco lo imprime
en palabras ("3 comentarios") sólo cuando hay.

**(5) Fuera del registro.** El comentario no entra al `frozen_record_json`, no cambia el estado de la
corrida, no se califica ni se enmascara, y la ausencia de comentarios se declara ("sin comentarios
todavía"), no se rellena.

## Consequences

- Producción crea la tabla sola en el primer arranque tras el redeploy; ninguna corrida cambia.
- El hilo es una conversación abierta a todo el equipo: el que escribe firma con su cuenta y no puede
  borrar. Si algún día hace falta retirar algo, será una decisión nueva (un "retirado" tachado y legible,
  como el resto del lenguaje), no un DELETE.
- El gate fija: 401 sin sesión · 404 corrida inexistente · 400 vacío y 400 con la cifra del tope · 201
  con autor, nombre y hora del servidor · orden de llegada · otro usuario lo lee · `n_comments` idéntico
  en lista y detalle · la corrida no cambió · 405 al intentar borrar.

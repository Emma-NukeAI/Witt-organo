# ADR-0076 — Número de corrida: la identidad LEGIBLE nace en el backend, no en la vista

- **Status:** Accepted — 2026-09-05. Origen: al rediseñar el Banco de preguntas de la webapp como
  filas-log (misma fecha), Emmanuel preguntó qué significaban los cuatro caracteres del chip de cada
  corrida. Respuesta medida en el código: nada — `run_id = uuid4().hex` (`runs.py`) y el chip mostraba
  su prefijo. Y ni siquiera identificaba: con 65,536 prefijos de 4 hex posibles, dos corridas comparten
  chip con ~2 % de probabilidad a 50 corridas y ~30 % a 200. Decisión de Emmanuel el mismo día: **el
  chip es el número de corrida**, cuatro caracteres, y lo demás (usuario, gen, nicho, veredicto, fecha)
  se queda en sus columnas.
- **Relates:** ADR-0055 (la lista y el detalle sirven la MISMA vista; nada crítico sin señal) ·
  ADR-0056 (la procedencia se DERIVA en el servidor, jamás en el cliente) · ADR-0074 (el registro
  congelado es inmutable — este número NO entra al blob) · ADR-0075 (la misma migración aditiva sobre la
  tabla `runs` del Postgres de producción).
- **Affects:** `rag_index/query_service/db.py` (columna `run_no` + migración aditiva + backfill + índice
  único + asignación al nacer en `create_run` + entra al SELECT explícito de `list_runs`) · `app.py`
  (`_run_view` lo deja pasar tal cual) · `smoke_runs_list_http.py` (10 → 17) · `smoke_run_pipeline.py`
  (124 → 126) · `README.md` · witt-webapp: `src/api/types.ts`, `M3Corridas/ListaCorridas.tsx` (chip,
  detalle, búsqueda), `M3Corridas/Traza.tsx`, `M4Hoja/{Hoja,HojaRuta}.tsx`, `Inicio.tsx`,
  `tests/m3.test.tsx`. **Cero mutación de la DATA INAMOVIBLE y cero cambio al registro congelado.**

## Context

1. **El chip no era identidad.** El prefijo de un uuid es aleatorio: no ordena, no se recuerda, y con
   el registro creciendo deja de ser único (cumpleaños sobre 65,536 valores). Un identificador que puede
   repetirse no sirve para decir "la 9b31" en una junta clínica.
2. **Lo que Emmanuel puso sobre la mesa como alternativas no es identidad.** Usuario y gen se repiten
   entre muchas corridas y ya tienen columna y faceta. Nicho y veredicto no existen cuando la corrida
   nace (llegan al congelar) y pueden venir vacíos: el chip cambiaría de nombre a media vida o quedaría
   en blanco. La fecha se repite varias veces por día y la columna Hora ya la dice. Combinar dos de
   ellos rebasa los cuatro caracteres.
3. **Numerar en la UI estaba descartado por diseño.** La lista de `/runs` es una ventana (tope 50): un
   ordinal por posición correría cada vez que entra una corrida nueva, y sería una derivación del
   cliente — justo lo que ADR-0056 prohíbe. Un número que cambia es peor que uno aleatorio.
4. **La tabla `runs` no tenía secuencia.** Su llave es `run_id` (texto); ninguna columna entera crece
   con la creación. SQLite no autoincrementa una columna que no sea la llave primaria, y el Postgres de
   producción ya tiene filas: la columna tiene que llegar por la migración aditiva de `_migrate()`,
   el mismo mecanismo que agregó cinco columnas antes (ADR-0075 incluido).

## Decision

**(1) Columna `run_no INTEGER` en `runs`, con índice ÚNICO `ix_runs_run_no`.** `create_all` la crea en
instalaciones nuevas; `_migrate()` la agrega a la tabla viva con `ALTER TABLE … ADD COLUMN`, idempotente
como las demás.

**(2) El número se asigna AL NACER, en el backend.** `create_run` toma `MAX(run_no)+1` dentro de la
misma transacción del INSERT. Si dos corridas se encolan a la vez y leen el mismo máximo (Postgres en
READ COMMITTED lo permite), el índice único rechaza a la segunda y ésta reintenta con el siguiente número
(hasta cinco veces). No hay fallback a null: una corrida sin número sería la ambigüedad que el número
elimina. Un `run_id` repetido no se reintenta — es otro defecto y sube tal cual.

**(3) Backfill una sola vez, por orden de creación.** Al arrancar, las corridas con `run_no` NULL se
numeran en orden `created_at` ascendente (empate por `run_id`, para que sea determinista), continuando
después del máximo vigente: la más vieja del registro es la 1. Es asignación de identidad sobre un hecho
que ya estaba en el registro, no una re-medición; y sólo toca las filas que no tienen número, así que la
segunda pasada no renumera nada. El índice único se crea después del backfill.

**(4) Viaja tal cual en `/runs` y `/runs/{id}`.** `_run_view` lo deja pasar como columna (no es
derivación) y `list_runs` lo incluye en su SELECT explícito — la lección del 2026-08-30: lo que la lista
omite del SELECT no llega al renglón aunque el detalle lo sirva.

**(5) `run_id` sigue siendo la llave técnica.** Rutas, claves foráneas, eventos, ratings y el registro
congelado siguen colgando del uuid. El número es el NOMBRE: lo que se imprime, se busca y se dice.

**(6) La UI imprime el número y declara su ausencia.** El chip del Banco muestra `run_no` con el
anillo en la voz del estado; el detalle lo repite junto al `run_id` completo; el buscador lo encuentra;
la hoja, la traza y los recientes del Inicio lo nombran. Frente a un backend anterior a este ADR el chip
cae al prefijo del `run_id` y lo declara al hover ("sin número de corrida: backend anterior"), en vez de
inventar uno.

## Consequences

- **Producción se numera sola en el primer arranque después del redeploy** (la migración corre en
  `init_db`). A partir de ahí los números son fijos para siempre; nada los reasigna.
- **La secuencia no tiene huecos mientras nada borre corridas**, y el sistema no borra (registro
  append-only). Una carrera perdida no deja hueco: el número se reintenta, no se descarta.
- **Cuatro dígitos alcanzan para 9,999 corridas**; el chip conserva su tamaño. Si algún día se rebasa, el
  chip crece un carácter — no se reinicia la cuenta ni se recicla un número.
- **Las referencias en conversación cambian de forma:** "la 47" en vez de "la 9b31". El `run_id` sigue
  disponible en el detalle y en la hoja para cualquier traza técnica.
- **Lo que fija el gate:** la corrida nace con número; lista y detalle coinciden; la nueva recibe el
  siguiente; el backfill numera por creación después del máximo; el índice rechaza duplicados; la segunda
  pasada de la migración no renumera; y en el pipeline completo los números son únicos y descienden con
  la lista (`created_at desc`).

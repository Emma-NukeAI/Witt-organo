# ADR-0064 — M5 ratings append-only sobre el registro + calibración ECE con poder DECLARADO

- **Status:** Accepted — 2026-08-22. Tapón 4 de PENDIENTES DE BACK (`witt-ui-lab/HANDOFF-2026-08-22.md`);
  diseño ya decidido en el lab el 2026-08-04 (calificación **con procedencia**; `ratings[]` append-only
  sobre el registro congelado). Emmanuel autorizó atacar el item en sesión ("arranca con los 3 items").
- **Relates:** ADR-0050 (registro congelado persistido), ADR-0053 (cierre = precedente), ADR-0056 (el
  firmante se DERIVA de la sesión, jamás del cliente), ADR-0005/0030 (lenguaje de claims de Test 4:
  "aggregate-captured" nunca "satisfied"; n<10 = "case capture"), `witt-ui-lab/01-mapa/registro-congelado.md`
  (el contrato de `ratings[]` y las dos zonas) y `03-bocetos/M5-cierre-de-run.md` (las reglas del instrumento).
- **Affects:** `rag_index/query_service/db.py` (tabla `run_ratings` + helpers) · **NUEVO**
  `calibration.py` · `app.py` (`POST /runs/{id}/ratings`, `GET /runs/{id}/ratings`, `GET /ratings/pending`,
  `GET /calibration`, y `/runs/{id}/record` fusiona ratings+consenso en lectura) · **NUEVO** gate
  `smoke_ratings_calibration.py` (29/29 offline). **Cero mutación de la DATA INAMOVIBLE** (todo vive en la
  BD del backend). Migración: tabla nueva creada por `create_all` (aditiva, automática al arrancar).

## Context

El registro congelado tiene dos zonas (decisión del fundador 2026-08-04, `registro-congelado.md`): las
**mediciones** de la corrida se congelan en `frozen_at` y no cambian nunca; `ratings[]` y `consensus`
**crecen después** del congelamiento. El instrumento M5 exige además: procedencia por calificación
(`rater_profile`, `is_author`, `blind`, `instrument`), el `[?] no la puedo calificar` como estado
explícito que **jamás** cuenta como un 1, independencia entre calificadores ("no se muestran las
calificaciones ajenas hasta que emitiste la tuya"), y consenso que cuenta **sin promediar**.

Para la calibración, el cálculo ya existía (`substrate_calibration/tools/compute_ece.py`) pero no había
ni fuente de etiquetas humanas sobre corridas de la webapp ni puerta HTTP. Y el riesgo nombrado por el
handoff: hoy hay ~4 corridas reales — un ECE presentado sin declarar esa n sería un número ciego.

## Decision

**(1) `ratings[]` vive en su propia tabla append-only (`run_ratings`) y se fusiona al registro EN
LECTURA.** El blob congelado jamás se reescribe — la regla de dos zonas queda estructural, no
disciplinaria. Una corrección es una fila NUEVA; para consenso y calibración cuenta la última por
persona.

**(2) La procedencia se DERIVA en el servidor, nunca se acepta del cliente** (mismo principio que el
firmante de ADR-0056): `rated_by` y `rater_profile` de la sesión, `is_author` de la autoría de la
corrida, `instrument` de la autoría (`m5-cierre` = la calificación del autor; `m5-consenso` = el resto),
`saw_answer_before_rating` de si existe registro congelado (una corrida muerta no tiene respuesta que
ver). `blind` es `False` constante en v1: el instrumento de la webapp muestra la respuesta; el
instrumento ciego es el banco CSV.

**(3) Los ejes son explícitos de tres estados.** `rating_input ∈ 1..5 | cannot-rate`;
`rating_output ∈ 1..5 | cannot-rate | not-applicable` (corrida muerta: el eje de la respuesta queda
`not-applicable`, no un 1). Un eje sin valor y sin estado declarado es **400**: la ausencia silenciosa
no existe.

**(4) La independencia M5 se aplica en el SERVIDOR.** Quien no ha calificado ve stubs sin scores ni
notas (`ratings_masked: true` + nota) en `/runs/{id}/record` y `/runs/{id}/ratings`; el consenso
(conteos, jamás valores agregados) sí se ve. El evento `rating.added` en `run_events` **no lleva
scores** — la bitácora y el replay no perforan el enmascaramiento.

**(5) `GET /calibration`: ECE sobre corridas CERRADAS, anclado en ratings humanos, con el poder
DECLARADO.** Reutiliza `compute_ece.py` (jamás re-implementa el binning). El mapeo de outcomes viaja
declarado en la respuesta (v1: `rating_output >= 4` positivo, `<= 2` negativo, 3 se abstiene; última
calificación por persona; mayoría ESTRICTA por corrida — la misma regla `majority()` del banco; empate o
sin votos = excluida y contada). Con `n_scored < 10` el reporte dice `power.sufficient: false` +
"case capture"/"infrastructure populated" (ADR-0005/0030) y el ECE queda etiquetado `descriptive-only` —
**n<umbral se declara, no se calcula a ciegas**. Con n≥10 entra isotonic. Desglose por `rater_profile`
(médico vs dev, sin decidir en la captura) y tally de `confidence_sources`. NO-SPEND por construcción.

**(6) Los dos instrumentos NO se mezclan en silencio.** La escala de la webapp es 1–5 (contrato del
registro congelado); el banco CSV usa ejes categóricos 0–2. Son instrumentos DISTINTOS: cada rating
lleva `instrument`, `/calibration` declara que mezcla `m5-cierre`+`m5-consenso` y que el banco no entra
(su puerta sigue siendo `evaluation/scripts/score_calibration.py`).

## Alternatives considered

- **Guardar ratings dentro del blob `frozen_record_json`** — rechazado: cada calificación reescribiría
  el JSON congelado; la inmutabilidad de las mediciones se volvería promesa en vez de estructura.
- **`instrument`/procedencia declarados por el cliente** — rechazado: falsificable; exactamente el hueco
  que ADR-0056 cerró para el firmante del ingest.
- **Enmascaramiento del lado de la UI** — rechazado: "cinco opiniones y no una repetida" solo es real si
  el servidor no entrega los datos; una regla de UI se salta con un curl.
- **Etiqueta de outcome por promedio** (`mean >= 3.5`) — rechazado: M5 prohíbe el promedio limpio y el
  banco ya usa mayoría estricta; el mapeo umbral+mayoría es declarable y recalibrable con volumen.
- **No calcular ECE con n<10** — rechazado a medias: se calcula pero viaja etiquetado
  `descriptive-only` con `power.sufficient: false`, espejo exacto del comportamiento de `compute_ece.py`.
- **Job programado en vez de endpoint** — rechazado: el cálculo es determinista, barato y NO-SPEND;
  on-demand no necesita scheduler ni estado extra.

## Consequences

- La UI de M5 (cierre + consenso + pendientes) tiene todo su respaldo backend; el Tapón 5 (evals
  periódicas) gana su fuente de etiquetas humanas.
- `/calibration` va a responder "infrastructure populated" hasta que lleguen calificaciones reales —
  ese es el comportamiento correcto, no un defecto.
- Divergencia **flagged, no resuelta** (decisión de producto pendiente de Emmanuel): M5 dice que una
  corrida muerta/cancelada "se puede cerrar" (y así volverse precedente), pero `close_run` solo acepta
  `awaiting_closure`. Hoy: failed/cancelled SÍ se califican (RATABLE_STATES) pero no entran al corpus de
  precedente ni al ECE (que barre solo `closed`). Si se decide cerrarlas, es un cambio de máquina de
  estados → su propio ADR.
- Gates: `smoke_ratings_calibration.py` 29/29 · regresión completa verde (query service 29/29 ·
  run-pipeline 94/94 · precedent 15/15).

## Evidence

- `witt-ui-lab/01-mapa/registro-congelado.md` (contrato `ratings[]`, dos zonas, "nunca un promedio limpio")
- `witt-ui-lab/03-bocetos/M5-cierre-de-run.md` (instrumento, invitaciones, estados límite)
- `witt-ui-lab/HANDOFF-2026-08-22.md` §PENDIENTES DE BACK item 1
- `substrate_calibration/tools/compute_ece.py` (el cálculo reutilizado + lenguaje ADR-0005/0030)
- `evaluation/scripts/score_calibration.py` (la regla de mayoría del banco; la escala 0–2 que motiva la
  disciplina de instrumentos)

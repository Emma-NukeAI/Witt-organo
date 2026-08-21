# ADR-0061 — El plan declarado: el preflight §11 se vuelve componente, y `not-assessed` se convierte en juicio

- **Status:** Accepted — 2026-08-20. Tapón 3 del plan de `witt-ui-lab/01-mapa/harness-en-la-webapp.md`.
- **Relates:** CLAUDE.md §11 (preflight de invocación de agentes), §3 (filtro de alcance: los seis nichos), §7 (prohibición de auto-auditoría; gate humano de `causal-pruner`), §6 (regla no-hang), ADR-0060 (misma disciplina de tabla: el modelo elige nombres, el código resuelve gates), ADR-0050 (modelo de corrida + bitácora), ADR-0049 (auditoría al 100%), LOTE-BACKEND-01 (`POST /runs/plan` + "estimaciones con historia · `[?] sin historia suficiente`"), boceto `03-bocetos/M3-preguntar-y-ejecutar.md` paso 2.
- **Affects:** `analysis/scripts/lib/agent_matrix.py` (**nuevo**), `rag_index/query_service/{runs,app,db}.py`, el gate; en la webapp `src/api/{types,client}.ts` · `src/modulos/M3Corridas/{Preguntar,Traza}.tsx` · `src/modulos/M4Hoja/Hoja.tsx` · `src/modulos/M8Consumo/Consumo.tsx` · `tools/gen_fixtures.py`. **Sube `render_contract_version` a 1.4.**

## Contexto

ADR-0060 dejó el hueco declarado en cada registro: el preflight §11 salía como **`not-assessed`** —
ningún componente decidía qué agente del catálogo era dueño del work-type de la respuesta. Honesto,
pero una deuda visible en cada hoja. La ranura del paso 2 del boceto M3 llevaba meses pintada
**BLOQUEADA** con el texto *"el planner (POST /runs/plan) no existe en el backend todavía"*.

De los ~30 agentes del catálogo, exactamente dos existían como código. El planner es lo que convierte
esa lista de prosa en algo que participa de una corrida.

## Decisión

### 1 · `agent_matrix.py`: la matriz, machine-readable — y la misma disciplina de tabla que ADR-0060

El planner elige **nombres** de un enum cerrado y da una **razón** por agente. Todo lo demás lo
resuelve la tabla: el **gate level** (`hard-rule` / `required` / `recommended`), el patrón compuesto, la
evidencia de substrato, y —lo más importante— si el agente **existe como componente ejecutable**.

Esa última columna separa dos verdades que no se pueden mezclar:

- lo que la **matriz** dice del agente (su work-type, su gate) — copiado del `.md`, que sigue siendo la
  autoridad humana;
- lo que la **corrida** puede realmente ejecutar: hoy **dos** filas corren como código
  (`composite-auditor`, y el gate `resolve_id`+`verify_output`). El resto es prosa. Que un agente
  **aplique** es juicio; que **pueda correr** es un hecho de tabla.

La tabla también carga las derogaciones y suspensiones vigentes, para que el planner no proponga algo
que el proyecto ya derogó: `html-report-emitter` derogado para la era webapp (ADR-0046),
`investor-relations-drafter` suspendido en Fase I (ADR-0008), `cross-field-bridge-agent` con Method 1
bloqueado hasta Fase II.

### 2 · El §3 encuentra por fin dónde vivir

`CLAUDE.md` §3 manda que toda tarea se clasifique en ≥1 de los seis nichos, y que **una tarea fuera de
alcance se marque**. En la ruta HTTP eso no existía en ninguna parte. Ahora el plan clasifica, con la
fase de activación de cada nicho, y `niches: []` produce un `scope.in_scope: false` con su razón.

**Se marca, no se bloquea**: quien decide si una pregunta fuera de alcance corre es el humano, no el
planner. La UI pinta la marca maciza y el botón de correr sigue habilitado.

### 3 · Tres clases de contenido, cada una declarada, nunca mezcladas

| Clase | Qué es | De dónde sale |
|---|---|---|
| `structural` | Ruta A primero, B condicional con sus dos decisores y sus tres fuentes, panel obligatorio con sus cuatro lentes, gate determinista | **del código** — se lee de `answer_pipeline.PATH_B_SOURCES`, `composite_auditor.DEFAULT_PANEL`, `FALLBACK_CONF_TAU` |
| `model-judgment` | work-type, nichos, agentes aplicables | **juicio del modelo** contra la matriz, con gate/componentización resueltos por tabla; marcado self-report igual que `framework_applied` |
| `PROJECTION` | costo y duración | **calculada por código** — mediana de la historia real; la constitución del proyecto prohíbe que un modelo estime |

La ruta **no** se declara como hecho: `path_b.conditional: true` con la nota de que *la suficiencia se
evalúa DESPUÉS de correr la Ruta A — declararla antes sería inventar información*. Eso es lo que el
boceto M3 exigía y es lo que hace que el número de costo no sorprenda después.

### 4 · Estimaciones: estado POR MÉTRICA

`plan_estimates()` calcula la mediana por escenario (DI-only vs con-fallback) sobre corridas que
completaron el pipeline, y `n < 3` produce `insufficient-history` con el literal *"[?] sin historia
suficiente"* que pedía LOTE-01.

**Y cada métrica declara su propio denominador.** La primera corrida real del planner destapó el
defecto: el escenario salía `projected` con la mediana de costo en `null`, porque esas corridas no
tenían gasto medido. Una proyección sin número no es una proyección. Ahora `cost_usd` y `duration_s`
llevan estado propio, y un escenario con una sí y otra no es **`partial`** — la métrica que existe no
cubre a la que falta.

### 5 · El plan se consume UNA vez, y está atado a SU pregunta

- Server-side y referido por `plan_id`: el cliente nunca re-manda el objeto (procedencia, anti-tamper).
- `POST /runs` con un `plan_id` ya usado → **409 `plan_already_used`**: re-usarlo callado haría pasar un
  juicio viejo por fresco.
- El registro congelado lleva `plan_question_matches_run` — misma disciplina que `question_matches_run`
  (ADR-0044). Un plan hecho para otra pregunta no respalda ésta, y la hoja lo marca macizo.
- En la UI, editar la pregunta o las entidades **descarta** el plan y lo dice.

### 6 · `agents_invoked` deja de ser `not-assessed`

Con plan, cada agente que el planner juzgó aplicable y **no** existe como componente entra con el
literal §5 de la matriz — **`skipped-ad-hoc`** (el rol corre ad-hoc dentro de la síntesis) — y la razón
del planner. El resto del catálogo queda en **una** fila agregada `not-applicable` (trazabilidad sin 25
filas de ruido). Sin plan, el hueco sigue saliendo `not-assessed`, y si el juicio se intentó y **falló**,
lo dice con el error.

### 7 · Declarar el plan es opcional, y el planner puede caerse (§6 no-hang)

El planner es una llamada de modelo. `build_plan` atrapa su falla y emite
`judgment.state: "errored"` — **el plan sigue siendo un plan** en sus partes estructurales, y preguntar
nunca se bloquea. `errored` es distinto de "no intentado" y de "ningún agente aplica".

### 8 · El planner gasta, y ese gasto entra al total

Detectado en la corrida real: el plan consume ~3,100 in / ~900 out y no estaba en `token_usage`, así que
M8 no podía cuadrar. Ahora entra al total **y** se desglosa aparte en `plan_judgment` para poder
responder "¿cuánto cuesta declarar un plan?" sin re-derivarlo. Misma disciplina que LOTE-01·A4 (lo
gastado antes de morir sobrevive): el holder explícito hace que el gasto del plan aparezca también en
los caminos `failed` y `cancelled`.

## Consequences

- La ranura BLOQUEADA de M3 se desbloqueó sin rediseñar: el boceto ya tenía el lugar.
- `stage.plan` es el **primer evento de etapa** de la traza, como lo pinta el boceto. Traza viva y replay
  leen el mismo resumen.
- Costo por corrida sube ~0.025 USD (el juicio del planner): 0.2579 medido contra 0.2082 sin plan.
- **El tapón 3 no componentiza ningún agente nuevo** — y no lo pretende. Convierte el juicio en dato: qué
  agentes aplican, con qué gate, y cuáles no pueden correr. Componentizar `causal-pruner` (el primer
  candidato, con su gate humano obligatorio de §7) es trabajo siguiente, y ahora el registro dice en
  cada corrida que falta.

## Verification

**Offline, determinista:** `smoke_run_pipeline.py` → **86/86 PASS** (+19: estructura del plan desde el
código · gate y componentización por tabla · nichos con fase · estimaciones por escenario · **métrica sin
medir → escenario `partial`** · historia insuficiente sin número · fuera de alcance marcado · juicio
`errored` sin tumbar el plan · `POST /runs/plan` · plan consumido una vez → 409 · `plan_id` inexistente →
404 · `stage.plan` primero · plan congelado + `plan_question_matches_run` · `agents_invoked` con plan sin
`not-assessed` · sin plan con `not-assessed` · gasto del planner dentro del total y desglosado · sin plan
sin `plan_judgment` · derogaciones en la tabla). `smoke_query_service.py` → **29/29**.

**Webapp:** `npm run gate` → **129/129** (+10 sobre la ranura desbloqueada, la card del plan, el descarte
por edición, el planner caído, la línea del plan en la hoja y el desglose en M8; fixtures 1.4 regenerados
por el código real del backend).

**Corridas reales** (Neo4j real, Opus 4.8 real, panel real, ZFIN real):

| corrida | resultado |
|---|---|
| `fd6850eb…` | plan con 9 agentes, nichos N3·N4·N1 · Ruta B `zfin:2 europepmc:0` · **`APPROVE_DECLINE`** — el literal de ADR-0058 disparando por primera vez en producción: la respuesta declinó honestamente (conf 0.28) y el panel aprobó la declinación · `framework: NONE-MATCHED` declarado |
| `9b3140ab…` | plan con 10 agentes · `AUDIT_APPROVED`/`APPROVE_MINOR` · `plan_judgment` 3,115/896 · **`by_model` suma exactamente `input_tokens`** (28,413) — M8 cuadra · `framework: Chain-of-Verification §8` |

El planner real, sobre *"¿Qué señal upstream induce el set mínimo de TFs del pronefros, y es suficiente
por sí sola para inducirlo ectópicamente?"*, identificó `causal-pruner` con la razón correcta: *"pide un
'set mínimo de TFs' más una señal upstream y su 'suficiencia por sí sola' — esto es trabajo de
candidatos-rankeados / set-mínimo"*. Es exactamente la fila §1 de la matriz, encontrada sin ayuda.

## Pendiente que esta decisión NO cierra

Componentizar agentes del catálogo (empezando por `causal-pruner` + su gate humano) · tapón 1·B (SDK de
Tool Universe) · tapón 4 (M5 + calibración: `calibration-tracker` sale `skipped-ad-hoc` en cada plan, y
ése es su recordatorio) · tapón 5 (evals). Y el hallazgo abierto desde ADR-0057: el escalar de confianza
sigue llegando atrapado en el texto en **6 de 6** corridas reales.

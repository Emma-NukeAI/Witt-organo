# ADR-0066 — Plan v3: preguntas de clarificación + paisaje de datos pre-gasto (adopción VB #1)

- **Status:** Accepted — 2026-08-22. Adopción #1 del roadmap aprobado por Emmanuel tras la comparativa
  contra *The Virtual Biotech* (Stanford/Zou, bioRxiv 2026.02.23.707551):
  `reports/2026-08-22_virtual-biotech-vs-witt-organo_comparativa_v1.html`. Instrucción: *"hagamos un
  plan para implementarlas… que ya tengamos esta nueva versión… y yo pueda continuar con la UI"*.
- **Relates:** ADR-0061 (el plan declarado), ADR-0063 (plan v2, ruta), CLAUDE.md §6 (no-hang),
  el patrón chief-of-staff + clarification-interview de VB (CollabLLM/CLAM refs [30,31] del paper).
- **Affects:** `rag_index/query_service/runs.py` (`PLAN_TOOL` +clarifying_questions ·
  `_data_landscape()` · `build_plan` · `plan_event_payload`; `plan_version` → **3**) ·
  `smoke_run_pipeline.py` (+6 checks). Sin endpoints nuevos; aditivo al objeto plan.

## Context

VB alinea ANTES de gastar: el CSO entrevista al usuario para clarificar intención y el chief-of-staff
prepara un briefing del paisaje de datos (inventario de tools + contexto). Nuestro planner (ADR-0061)
rutea y estima, pero no alinea intención ni dice qué fuentes tiene disponibles para ESTA pregunta —
las corridas ambiguas se descubren caras (el panel de 4 jueces es la mayor parte del costo).

## Decision

El plan gana dos piezas, cada una con su clase declarada:

1. **`judgment.clarifying_questions[]`** (model-judgment): 0–3 preguntas de clarificación con su `why`
   (qué decisión del análisis cambia), SOLO cuando la pregunta es genuinamente ambigua — un array
   vacío significa "clara"; el schema prohíbe inventarlas. **Never-stopper:** jamás bloquean —
   responderlas refina un plan FUTURO; la corrida procede igual si el usuario decide correr.
2. **`data_landscape`** (structural, calculado por código incluso si el juicio del planner falla):
   `di_preview` con el índice **sparse local NO-SPEND** (n_hits + top doc_ids, etiquetado
   "orientativo, no medición de la corrida" — el mismo patrón /status) + `path_b_sources` como hechos
   del código (EPMC/PubMed siempre; ZFIN solo con entities — sus keys son símbolos; tooluniverse hook).
   Preview caído → `unavailable` declarado, el plan sigue entero (§6).

`stage.plan` lleva `n_clarifying` + `di_preview_hits`. `plan_version: "3"`.

## Alternatives considered

- **Entrevista conversacional multi-turno estilo VB (el CSO pregunta y espera)** — rechazada: bloquea
  el flujo Preguntar y contradice el never-stopper; las preguntas como PARTE del plan dan la misma
  alineación sin gate.
- **Preview con el índice semántico (embed)** — rechazado: el plan debe ser barato y el /status-style
  NO-SPEND es doctrina; el conteo sparse es orientativo y se declara como tal.
- **Hacer las clarificaciones requeridas antes de encolar** — rechazado: un plan jamás es requisito
  (ADR-0061); menos aún sus preguntas.

## Consequences

- La webapp (M3, card del plan) puede renderizar las preguntas + el paisaje; contrato del plan v3 es
  aditivo — fixtures a regenerar (`tools/gen_fixtures.py`).
- Costo: +0 llamadas de modelo (las preguntas van en el MISMO juicio del planner); el preview sparse
  es local.
- Gate: `smoke_run_pipeline.py` 112/112 (checks: v3 estructural, [] por claridad, declaradas+evento,
  zfin sin entities, preview caído declarado, paisaje sobrevive planner caído).

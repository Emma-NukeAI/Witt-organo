# ADR-0067 — Ciclo de revisión acotado post-REVISE: nada se borra, tope duro = 1 (adopción VB #2, contrato 1.6)

- **Status:** Accepted — 2026-08-22. Adopción #2 del roadmap aprobado por Emmanuel tras la comparativa
  contra *The Virtual Biotech* (`reports/2026-08-22_virtual-biotech-vs-witt-organo_comparativa_v1.html`).
- **Relates:** ADR-0049 (auditoría 100%, terminal post-audit), ADR-0058 (APPROVE_DECLINE / doctrina de
  declinación honesta), ADR-0038 (jueces con chequeo determinista entregado), method-selection v1.2 +
  orchestration-patterns (por qué la iteración ABIERTA está prohibida: los modos de falla se multiplican
  en cascada), el loop reviewer→re-delegate de VB (su caso B7-H3: el review accionable dispara análisis
  que cierran huecos).
- **Affects:** `rag_index/query_service/runs.py` (`_revision_enabled`/`REVISION_CAP`/`_panel_findings` +
  la sección 6b de `execute_run`; `render_contract_version` → **1.6**) · `smoke_run_pipeline.py`
  (+8 checks). Eventos nuevos: `stage.revision.start`, `stage.synthesize.revision`, y
  `stage.audit.verdict` ahora lleva `revision_round` (0|1) y puede aparecer DOS veces.

## Context

Hasta hoy, un REVISE del panel era terminal: la corrida moría honesta (`AUDIT_REJECTED`) sin intentar
la corrección — correcto cuando se construyó el bloque 3 (el terminal honesto era el punto), pero VB
demuestra que un review con hallazgos accionables + re-delegación convierte auditoría en calidad. Las
2 corridas reales de producción terminaron ambas REVISE→rechazadas; el valor de un intento de
corrección auditado es directo.

## Decision

Cuando el panel emite **REVISE** (y solo REVISE):

1. **UNA pasada de revisión** (`REVISION_CAP = 1`, tope DURO — dinámica-dentro-de-etapas-acotadas,
   jamás iteración abierta): la síntesis recibe `revision_input` tipado = respuesta previa + los
   hallazgos accionables del panel (`_panel_findings`: lens, caught, correction_applied, reasons de
   filas REVISE/APPROVE_MINOR) + la instrucción de que corregir un hallazgo JAMÁS licencia claims o
   identificadores nuevos (doctrina ADR-0058 incluida).
2. **Re-gate determinista** (`verify_output` sobre la respuesta revisada) y **re-auditoría completa**
   (mismo panel). El veredicto de la ronda 2 es terminal SEA CUAL SEA.
3. **NADA se borra** (la diferencia deliberada vs VB, donde la iteración es invisible en el artefacto
   final): el registro congelado carga `answer_initial` + `audit_initial` (panel completo de la ronda
   0) junto a la versión final; `revision {enabled, performed, cap, findings_used, initial_verdict,
   final_verdict, initial_checks_admissible}`; `confidence.revision/revision_source`. Tres estados:
   una corrida sin revisión lleva los campos null-DECLARADOS, jamás ausentes.
4. **Dos exclusiones declaradas:** kill-switch operativo `WITT_REVISION_CYCLE=0` (restaura el
   comportamiento pre-ADR) y `panel_incomplete` (un REVISE por panel delgado es un problema de
   JUECES, no de la respuesta — re-sintetizar no arregla jueces caídos; `skipped_reason` lo dice).
5. **El gasto de AMBOS paneles y de la pasada de revisión cuenta** (M8 cuadra): `token_usage` y
   `usage_raw.panel_total` suman todas las filas; los caminos cancelled/failed conservan el gasto
   parcial (LOTE-01·A4).

## Alternatives considered

- **Loop abierto hasta APPROVE (el diseño VB literal)** — rechazado: inauditable, costo no acotado, y
  el stress-test documenta la multiplicación de fallas en cascada; con tope 1 el peor caso es ~2× el
  costo de una corrida REVISE.
- **Revisión también en APPROVE_MINOR** — rechazada por ahora: APPROVE_MINOR ya aprueba; gastar un
  panel extra para pulir un minor invierte la economía (revisable con datos si los minors resultan
  sistemáticos).
- **Reusar el veredicto ronda-0 si la revisión "parece" buena** — rechazado: toda respuesta que se
  muestra pasa por SU propia auditoría (ADR-0049, 100%).
- **Guardar solo la versión final (estilo VB)** — rechazado: borrar la versión inicial destruye
  exactamente el rastro que este sistema existe para conservar.

## Consequences

- Corridas REVISE ahora pueden terminar `AUDIT_APPROVED` con su corrección auditada y AMBAS versiones
  visibles; el costo sube hasta ~2× solo en esas corridas (~USD 4 peor caso).
- Webapp/UI (FRONT): contrato **1.6** — `revision`, `audit_initial`, `answer_initial`,
  `confidence.revision`; la traza puede llevar DOS `stage.audit.verdict` (usar `revision_round`);
  fixtures a regenerar.
- La señal de calibración gana un dato nuevo: el delta inicial→revisado y la tasa de conversión
  REVISE→APPROVE (futuro insumo del RIL).
- Gates: `smoke_run_pipeline.py` **112/112** (a–h: conversión, nada-se-borra, dos rondas con cap,
  usage de ambos paneles, REVISE→REVISE terminal, kill-switch, panel_incomplete, 3-estados) ·
  regresión 29/29 · 29/29 · 15/15.
- **Confirmación en producción pendiente** (misma disciplina que ADR-0065): la próxima corrida real
  que caiga en REVISE es la medición.

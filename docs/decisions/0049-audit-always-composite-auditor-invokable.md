# ADR-0049 — Auditoría en el 100% de las corridas (la máquina de estados se reforma) + `composite-auditor` se vuelve un componente invocable con vocabulario homologado

- **Status:** Accepted — decisión del fundador (2026-08-04, ratificada con alcance el 2026-08-09: *"aunque sea data inamovible suficiente también debería de correr, es decir, en el 100% de las veces"*). Cambio **backwards-incompatible** a la máquina de estados de ADR-0022 → este ADR lo documenta (CLAUDE.md §7: sin ADR no hay cambios incompatibles).
- **Relates:** ADR-0022 (el decision pathway original), ADR-0047 (decisiones 3 y 4: alcance del panel + composición), ADR-0031/0038 (paneles multi-familia + juez cross-provider + fix judge-fabrication), ADR-0037 (jueces errados se excluyen, jamás se fabrican), ADR-0006 (composite-auditor reemplaza el single-LLM), tapón 3 del handoff webapp.
- **Affects:** `analysis/scripts/lib/answer_pipeline.py` (estado `DI_SUFFICIENT`) · **NUEVO** `analysis/scripts/lib/composite_auditor.py`. **Cero mutación de la DATA INAMOVIBLE.**

## Context

Tres hechos verificados (2026-08-09): `record_audit()` tenía **cero llamadores** y no persistía; `composite-auditor` no existía como código (era un rol que agentes ejecutaban en sesión); el gate estaba cerrado por un **string de prosa** (`required_next_action`) que un agente debía leer y obedecer. `AUDIT_APPROVED`/`AUDIT_REJECTED` eran estados muertos y la llave `audit` faltaba en el 100% de las corridas producibles. Prometer "siempre auditado" sin esto era un over-claim. Además había **cuatro vocabularios de veredicto vivos e incompatibles** (record_audit `approved/rejected` · judge_answer 5-way · paneles `APPROVE_MINOR` · S-bank `CONFIRMED/REVISE/REFUTED`).

## Decision

1. **`DI_SUFFICIENT` deja de autorizar responder.** `may_answer_now=False`, `required_next=AUDIT`. Los dos primeros estados son ahora **intermedios**; el terminal de TODA corrida es `AUDIT_APPROVED | AUDIT_REJECTED`. El costo del panel corre en el 100% de las corridas y **se mide, nunca se limita** (sin caps — ADR-0047 d.3).
2. **`composite_auditor.py` es el componente invocable** (Mode 1 split-and-vote): entrada tipada (claim + evidencia + **resultados del gate determinista** — los jueces tienen PROHIBIDO inventar verificación, el fix ADR-0038), salida = **tabla de panel** `{reviewer, family, lens, verdict, caught, correction_applied, confidence}` + `tally` + `verdict` + `source_vocabulary` + `usage`. Panel default (ADR-0047 d.4): `claude-opus-4-8` (correctness) + `claude-sonnet-5` (overclaim) + `claude-haiku-4-5-20251001` (evidence-grounding) + `gpt-4o` (reproducibility, cross-provider). **Fable-5 excluido.** Los callers LLM son inyectables (gates offline deterministas); el patrón de llamada es el de `run_held_out.py` (urllib forced-tool / openai function-calling), ya auditado.
3. **Reglas de agregación (deterministas):** verdict global = **worst-of-N** sobre revisores válidos (un catch real jamás se promedia); un juez errado/unparseable queda **registrado como `errored` y excluido** (nunca fabricado); **menos de 3 verdicts válidos NUNCA aprueba** → `REVISE` + `panel_incomplete: true` (el mínimo Mode 1 es estructural, no aspiracional).
4. **Vocabulario homologado:** corridas nuevas hablan `APPROVE | APPROVE_MINOR | REVISE`; todo objeto `audit` carga `source_vocabulary`; los artefactos históricos **conservan su vocabulario original** — jamás se colapsan a un semáforo (se perdería la lente, el catch y la corrección — el valor del panel).
5. **`record_audit` gana su primer llamador real:** `apply_to_bundle()` mapea el verdict (APPROVE/APPROVE_MINOR ⇒ evidencia admitida ⇒ `AUDIT_APPROVED`; REVISE ⇒ rechazada ⇒ `AUDIT_REJECTED`), enriquece `bundle.audit` con la tabla completa del panel (visible, no solo listas) y re-estampa `bundle_identity` (ADR-0044).

## Consequences

- La promesa "siempre auditado" es ahora estructural: el estado terminal solo existe post-panel, y el run model (ADR-0050) persiste el veredicto.
- Consumidores que dependían de `DI_SUFFICIENT.may_answer_now == True` deben pasar por el audit — se revisaron los del repo: `smoke_contract` (asserts por nombre de estado, intactos) y `run_held_out.py` (arma su propio bundle; migrarlo al run model es trabajo futuro ya señalado en §5.6 del handoff).
- Granularidad v1: el panel audita claim+evidencia **como conjunto**; verdicts por-ítem de evidencia son un refinamiento futuro.
- Residual honesto: el vocabulario homologado aplica a corridas nuevas; el mapeo de lectura de los 4 vocabularios históricos para la UI (M6/bitácora) queda al índice de históricos (`kind`/`source_vocabulary`), no a una conversión destructiva.

## Verification (offline, deterministic)

`smoke_run_pipeline.py` checks 1–8 → parte del **19/19 PASS** (2026-08-09): reforma DI_SUFFICIENT · worst-of (APPROVE/APPROVE_MINOR/REVISE) · panel delgado nunca aprueba · errored registrados · `record_audit` llamado con identidad re-estampada · REVISE ⇒ AUDIT_REJECTED. Gates previos re-corridos: `smoke_degraded_envelope` 17/17 · `smoke_query_service` 20/20.

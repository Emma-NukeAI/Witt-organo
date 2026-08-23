# ADR-0072 — El harness held-out migra al run model: lo que se evalúa ES el pipeline de producción

- **Status:** Accepted — 2026-08-22. Cierra el pendiente "migrar `run_held_out` al run model"
  (§12/handoff). Con esto el **Tapón 5** (evals periódicas como gate del código de producción)
  tiene su instrumento: ya no hay réplica paralela que evaluar.
- **Relates:** ADR-0050 (run model), ADR-0051/0065 (dos pasadas + elicitación — ahora MEDIDAS por
  la eval), ADR-0049/0058 (panel + APPROVE_DECLINE), ADR-0067 (revisión), ADR-0031/0037/0038 (el
  juez multi-proveedor ADVISORY que se conserva), `evaluation/EVAL_DESIGN.md` (F5, ADR-0068),
  faltantes §5.6 (el defecto original: el consumidor real saltaba la máquina de estados).
- **Affects:** **NUEVO** `evaluation/run_held_out_v2.py` + `smoke_run_held_out_v2.py` (12/12) ·
  `run_held_out.py` (nota de deprecación para corridas nuevas; se CONSERVA como procedencia de
  month_0/4/8 y como librería del juez) · `.gitignore` (+`evaluation/eval_runs.db`).

## Context

El v1 llamaba `path_a`/`check_entities`/`assess_sufficiency` por separado y armaba su propio bundle
sin `decision_state` — por eso los ~30 récords históricos salen `instrumented: false` en la webapp,
y por eso una eval del v1 NO medía el pipeline real (ni las dos pasadas, ni la elicitación, ni el
panel del run, ni la revisión). El propio v1 fue donde nació el trap del escalar (su
`_recover_leaked_confidence` es el ancestro de ADR-0057).

## Decision

**v2 = una pregunta, una corrida REAL** por `runs.execute_run` — el mismo código que producción:
retrieve multi-fuente → pass1 DI-only → decisor por confianza → pass2 → elicitación dedicada
(ADR-0065) → gate determinista → panel 4 jueces → ciclo de revisión (ADR-0067) → registro congelado
(contrato 1.6). Sobre ese registro, el v2 SOLO agrega la capa de evaluación:

1. **Outcome determinista del gate DEL PROPIO RUN** (`deterministic_checks` del registro) para
   preguntas de identificadores — el run es el instrumento; no se re-corre un gate paralelo
   (diferencia declarada vs v1, que recomputaba con `identifier_bindings`).
2. **Juez multi-proveedor ADVISORY reusado del v1 por import** (jamás re-implementado): mismos
   literales, mismas guardas (desacuerdo ≥0.5 / abstención ≥0.5 → unfalsifiable), mismo
   "NOT ground truth" (ADR-0037).
3. **Récord = claim-record compatible con compute_ece** (stated_confidence/observed_outcome/…)
   **+ el run model completo**: decision_state (¡instrumentado!), bloque de confianza con
   procedencia, veredicto del panel, revisión, retrieval_summary y el **gasto MEDIDO por pregunta**.
4. **EVAL_DESIGN en el récord** (F5): `sources_mode` declarado (`di-only` parchea
   `path_b_bundle(sources=())` — la Ruta B puede disparar pero no busca NADA externo, a prueba de
   fugas por construcción; `di+structured` = el pipeline real) + `model_cutoff` ATESTIGUADO por el
   operador (default "not-declared", honesto).
5. **Seguridad de BD estructural**: la BD del harness se FUERZA a `evaluation/eval_runs.db`
   (gitignored); un `WITT_BACKEND_DB_URL` de producción en el shell jamás captura corridas de eval,
   y las evals no entran al corpus de precedente de producción por construcción.
6. **EPS conservado**: `--runs 2` + subcomando `eps` construye los pares desde los raws del run
   model y reusa `noise_probe` (mismos ejes que v1).

## Piloto en vivo (2026-08-22, mismo día)

Q01 + Q26, backend neo4j, di+structured, juez completo: **2/2 `AUDIT_APPROVED` con
`APPROVE_DECLINE`** (DI delgada → declinación honesta → panel la aprueba, ADR-0058) · **2/2
`confidence.source: stated-second-elicitation`** limpio con el in-line persistido — **la
confirmación en vivo de ADR-0065** (anotada allá) · outcome `unfalsifiable_in_phase_I` en ambas
(el juez no puntúa declinaciones — exclusión honesta, jamás forzada) · gasto medido **USD 0.42**.
El fix del smoke lo atrapó el propio gate: el ENSDARG del stub estaba inventado y `verify_output`
lo marcó unresolved (anti-fabricación funcionando contra su propio autor).

## Alternatives considered

- **Reescribir v1 in-place** — rechazado: es el instrumento que produjo month_0/4/8 (procedencia) y
  la librería del juez que v2 importa; se deprecia para corridas nuevas, no se borra.
- **Evaluar vía HTTP (POST /runs)** — rechazado: acopla la eval al servicio vivo y a su auth; el
  harness llama `execute_run` directo con la MISMA semántica y BD propia.
- **Cerrar las corridas de eval (closed)** — rechazado: el cierre es un acto humano (M5) y `closed`
  alimenta el precedente; las evals quedan `awaiting_closure` en su BD local.
- **Forzar un outcome cuando el juez no puede** — prohibido de origen (v1): unfalsifiable se excluye
  y se cuenta.

## Consequences

- El Tapón 5 es ahora un cron + este harness + umbrales (falta solo volumen de etiquetas humanas).
- Los récords nuevos de `evaluation/runs/` salen INSTRUMENTADOS (la webapp los distinguirá de los
  históricos v1 automáticamente vía su regla `decision_state`).
- Toda mejora del pipeline (elicitación, revisión, fuentes B) queda automáticamente BAJO la eval —
  no hay réplica que se desactualice.
- Gates: `smoke_run_held_out_v2.py` **12/12** (BD forzada, instrumentado, determinista-del-run,
  advisory, di-only a prueba de fugas, failed honesto, compute_ece, EPS) · regresión completa verde.

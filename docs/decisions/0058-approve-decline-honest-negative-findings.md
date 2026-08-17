# ADR-0058 — `APPROVE_DECLINE`: la declinación honesta correcta APRUEBA (decisión del hallazgo 3 de LOTE-03)

- **Status:** Accepted — **decisión de Emmanuel (2026-08-16): opciones 1 y 2 del ADR-0057** (instruir a las lentes + vocabulario nuevo). Cierra el hallazgo 3 pendiente.
- **Relates:** ADR-0057 (el hallazgo: 2/2 corridas reales `AUDIT_REJECTED` por decir la verdad sobre una ausencia; gpt-4o/reproducibility fue el veto en ambas), ADR-0049 (vocabulario homologado + worst-of-N), la tesis del proyecto (el hallazgo negativo es dato de primera clase; Test 5: "absence-of-evidence findings are also data").
- **Affects:** `analysis/scripts/lib/composite_auditor.py`. Corridas nuevas; los registros congelados 1.0–1.2 previos conservan su `source_vocabulary` original (estructural, ADR-0049).

## Decision

1. **Vocabulario (opción 2):** `APPROVE | APPROVE_DECLINE | APPROVE_MINOR | REVISE`. **`APPROVE_DECLINE`** = el claim declina honestamente (con `absence_kind` declarado) y declinar ES el movimiento epistémico correcto dada la evidencia. Severidad worst-of-N: `APPROVE(0) < APPROVE_DECLINE(1) < APPROVE_MINOR(2) < REVISE(3)` — la caracterización específica domina al approve genérico; cualquier issue real domina a ambas. `SOURCE_VOCABULARY` actualizado para corridas nuevas.
2. **Doctrina de declinación honesta en las lentes (opción 1):** el system prompt compartido del panel instruye: una declinación con `absence_kind` declarado se juzga por si declinar es **correcto dada la evidencia mostrada** (literatura externa incluida) — jamás se castiga la declinación por la ausencia misma (la ausencia correctamente identificada dispara el loop de re-ingesta). Declinación correcta → `APPROVE_DECLINE`; **declinación floja** (la evidencia sí alcanzaba) → `REVISE`. La lente de reproducibility — la que vetó ambas corridas — recibe la corrección explícita: *una declinación honesta ES reproducible cuando un lector independiente de la misma evidencia también concluiría que no alcanza*.
3. **`record_audit`:** `APPROVE_DECLINE` **admite** — una declinación correcta termina **`AUDIT_APPROVED`**: el hallazgo negativo entra al registro como resultado de primera clase, distinguible del claim rechazado por el literal mismo del veredicto (que viaja en `audit.verdict`, `epistemic_summary.verdict` y la tabla del panel).

## Consequences

- El caso que motivó el hallazgo (declinar ante ausencia real, incluso tras Ruta B) ahora termina aprobado y etiquetado — la UI distingue *declinación correcta* de *claim rechazado* por el literal, sin heurísticas.
- El equipo puede confiar el veredicto: `REVISE` vuelve a significar "algo está mal en la respuesta", no "el mundo no tenía el dato".
- Señal de calibración pendiente de acumular: si `APPROVE_DECLINE` empieza a usarse para declinaciones flojas (falsos aprobados), el panel se re-instruye — misma disciplina de acumular corridas antes de tocar (ADR-0050).

## Verification (offline, deterministic)

`smoke_run_pipeline.py` → **44/44 PASS** (+3: `APPROVE_DECLINE` domina a `APPROVE` genérico · un `APPROVE_MINOR` real domina a la declinación · panel unánime en declinación → `AUDIT_APPROVED` con `audit.verdict = APPROVE_DECLINE`). `smoke_query_service` 29/29 · `smoke_ingest_gate` 22/22.

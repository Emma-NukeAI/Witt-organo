# ADR-0044 — Identidad de bundle: nombre por `run_id`, `stamp` real, `bundle_identity.sha256`

- **Status:** Accepted — autorizado por Emmanuel en sesión 2026-08-09, parte del paquete de correcciones pre-UI (handoff webapp 2026-08-04).
- **Relates:** ADR-0022 (answer_pipeline / decision pathway), ADR-0043 (sobre degraded — misma sesión). Hallazgo §5.1 y §5.11 de `witt-ui-lab/05-backend/faltantes-backend.md`, verificado el 2026-08-09.
- **Affects:** `analysis/scripts/lib/answer_pipeline.py` únicamente (nombre del artefacto en `mcp_cache/` — gitignored — y forma del bundle). **Cero mutación de la DATA INAMOVIBLE.** Aditivo salvo el nombre de archivo del bundle y el significado de `stamp`.

## Context

El nombre del bundle era `answer_bundle_<slug40>_<DATE>.json` con `DATE = "20260613"` **constante** (no una fecha). Verificado en fase 1:

- Dos preguntas con el mismo slug de 40 caracteres se sobrescribían **cualquier día, para siempre** — peor que el "mismo día" que estimó el handoff. Con 5 usuarios y una UI encima, el resultado es una hoja perfectamente instrumentada (procedencia y sha impecables) **mostrando los datos de otra corrida u otra persona**. Es la única falla de la lista que una UI no puede detectar sola: no se ve degradada, se ve *equivocada*.
- `stamp` (la misma constante) viajaba dentro del bundle como si fuera fecha; ningún consumidor podía usarla como fecha de corrida.
- `record_audit()` muta el bundle en memoria después de generado; sin identidad recomputada, cualquier hash previo quedaría obsoleto.

## Decision

1. **Nombre por `run_id`:** `answer_bundle_<run_id>.json`, con `run_id = uuid4().hex` generado en `retrieve()`. El slug se conserva **dentro** del bundle (`question_slug`) para grep-abilidad; jamás vuelve a ser identidad.
2. **`stamp` = timestamp real** de la corrida (ISO-8601 UTC, `timespec="seconds"`). Se elimina la constante `DATE`.
3. **`bundle_identity` = `{sha256, run_id, question}`**, donde `sha256` se computa sobre el payload canónico (el bundle **menos** `bundle_identity`, `json.dumps(sort_keys=True)`). Un consumidor re-verifica que la hoja que dibuja es la corrida que dice ser (`question_matches_run` de la UI se deriva de aquí). `record_audit()` **re-estampa** la identidad porque muta el bundle.

## Consequences

- La colisión silenciosa desaparece estructuralmente (uuid4, no slug+fecha).
- Los bundles históricos en `mcp_cache/` (gitignored, cache de trabajo) conservan el nombre viejo; no se migran — versión-preservación, y no son registro durable.
- El contrato de la UI (`registro-congelado.md`) recibe `run_id`/`bundle_identity` directamente del bundle; `measured_at`/`frozen_at` del registro congelado son capa aparte (bloque 3+).
- Residual honesto: `run_id` aún no enlaza con un modelo de corrida persistente (`Run`, §2.1 del handoff — bloque 3); hoy identifica el artefacto, no una fila en una cola de jobs.

## Verification (offline, deterministic)

- `smoke_degraded_envelope.py` checks 6–7: misma pregunta ⇒ `run_id` distinto (no colisión), `stamp` ISO real ≠ `'20260613'`, `bundle_identity.sha256` verifica por recomputación, y `record_audit` re-estampa una identidad válida distinta a la pre-audit. **12/12 PASS** (2026-08-09).

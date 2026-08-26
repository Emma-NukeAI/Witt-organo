# ADR-0074 — Campos-lista serializados como string: se normalizan ANTES de congelar, jamás después

- **Status:** Accepted — 2026-08-25. Origen: la corrida real `9b3140abd6b643639cf9f28c1ab4f091`
  congeló `alternatives_considered` como STRING JSON (`'["…","…"]'`) y `gap_flags` explotado en
  CARACTERES sueltos — la hoja de la webapp crasheaba en render (TypeError: alts.map). El front ya
  se defendió (witt-webapp 2026-08-25: la forma rota se DECLARA con bandera y se imprime cruda);
  este ADR tapa la causa en el backend.
- **Relates:** ADR-0057 (recuperación de parámetros atrapados como texto — la causa raíz),
  ADR-0060 (contrato §5: alternatives_considered viaja en el registro), ADR-0043 (lo ausente se
  declara, jamás se rellena).
- **Affects:** `analysis/scripts/lib/composite_auditor.py` (`recover_trapped_params`) ·
  `rag_index/query_service/runs.py` (`_lista_serializada` + `_default_synthesizer`) ·
  `smoke_run_pipeline.py` (+3 checks ADR-0074a/b/c).

## Context

Dos rutas producen un STRING donde el contrato pide `string[]`:

1. **Parámetro atrapado como texto (ADR-0057):** el modelo emite la transición de parámetro en
   sintaxis XML legada dentro de `direct_answer`; `recover_trapped_params` levantaba el valor
   crudo — para un campo-lista, eso es el string `'["…","…"]'` (solo los numéricos se convertían).
2. **Emisión directa mal tipada:** la API no valida los tipos del schema (lección de a361f566 con
   `required`), así que el modelo puede emitir un string donde va un array.

Con el string adentro, `_default_synthesizer` hacía `list(out.get("gap_flags", []))` — `list(str)`
= caracteres sueltos — y el freezer escribía ambas formas rotas al blob. El mojibake observado en
9b3140ab (`â€™`/`Ã©`) NO es de esta ruta HTTP (que decodifica UTF-8 correcto): viene de la emisión
descarrilada del propio modelo y se conserva verbatim — corregirlo sería reescribir lo que el
modelo dijo.

## Decision

1. **En la recuperación** (`recover_trapped_params`, regla 4 nueva): un valor atrapado que empieza
   con `[`/`{` se intenta `json.loads`; el parse fallido conserva el crudo. La procedencia sigue
   declarada vía `_recovered_fields`.
2. **En la síntesis** (`_default_synthesizer`, antes de congelar): un campo-lista que llega string
   se normaliza con `_lista_serializada` — string JSON de lista → la lista, CON bandera en
   `gap_flags` declarando que llegó serializada; cualquier otro string → se conserva crudo como
   UN elemento de lista (jamás `[]`, que se leería "no había alternativas"; jamás `list(str)`).
3. **Los registros ya congelados NO se migran.** El blob congelado es inmutable por diseño
   (ADR-0046/0064: la zona append-only se fusiona al leer; el blob jamás se reescribe). La webapp
   declara la forma rota verbatim al renderizarlos — que 9b3140ab exhiba su defecto ES el
   registro honesto de que ocurrió.

## Consequences

- Toda corrida futura congela `alternatives_considered`/`gap_flags` como listas, con la
  procedencia del parse declarada en el propio registro.
- `record_pdf.py` y la webapp reciben la forma del contrato sin defenderse; sus guards quedan
  para los registros históricos no migrados.
- El smoke fija las tres rutas (atrapado-parseado · serializado-directo-parseado · no-parseable
  conservado crudo).

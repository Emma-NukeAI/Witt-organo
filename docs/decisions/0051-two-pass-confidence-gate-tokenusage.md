# ADR-0051 — Dos pasadas con decisor de fallback por confianza, `confidence_by_subclaim` + `absence_kind`, citas tipadas y `TokenUsage` medido (bloque 4)

- **Status:** Accepted — bloque 4 del plan webapp, ejecutado 2026-08-10. Motivado directamente por los hallazgos de la **corrida real #1** (`a361f566`, ADR-0050): el chequeo estructural se dejó engañar por any-chunk-present y la Ruta B nunca disparó; `stated_confidence` llegó null; Sonnet pidió el gap estructurado absence-of-evidence vs evidence-of-absence.
- **Relates:** ADR-0049/0050 (auditoría 100% + run model), ADR-0047 d.3 (medido sin caps), CLAUDE.md §5 (`confidence_by_subclaim` obligatorio con sub-claims asimétricos), la lección Level-2 del 2026-07-11 (el delta 0.14→0.71 fue EL dato), handoff §5.7/§5.8/§2.5/§2.6, ADR 2026-07-13 del vault (clases de medición).
- **Affects:** `rag_index/query_service/runs.py` (pipeline de dos pasadas; `render_contract_version` 1.0→**1.1**) · `rag_index/graphrag/embeddings.py` (contador de usage real del API) · `analysis/scripts/lib/composite_auditor.py` (usage por revisor). **Cero mutación DI.**

## Decision

1. **Pass 1 es SIEMPRE DI-only** — su confianza es la señal real de *"¿mi store alcanza?"*, medida incluso cuando la insuficiencia estructural ya trajo Ruta B.
2. **Dos decisores de fallback, y el registro dice CUÁL disparó** (`fallback.trigger ∈ {structural, confidence, null}` + `fb_meta {pass1_confidence, tau, structural_sufficient, absence_kind}`): el estructural (dentro de `retrieve()`, documentado como engañable) y el **gate por confianza** — `pass1 < τ` **o ausente** dispara `path_b` (τ = `WITT_FALLBACK_CONF_TAU`, default **0.5** — el recomendado del harness `run_held_out --conf-threshold`). Al entrar evidencia externa, el estado pasa a `FALLBACK_FETCHED` **con el constructor del propio pipeline** (jamás una máquina re-inventada).
3. **Pass 2 solo cuando hay fallback**, con la evidencia externa incorporada. **Ambas confianzas persisten** + `delta` — el dato más informativo de la corrida (la medición que descubrió el lever de Tool Universe). Bloque `confidence {pass1, pass2, delta, final, by_subclaim, state}` con disciplina de tres estados: `state = value | absent-not-calibratable` — un null jamás se disfraza de medición.
4. **`confidence_by_subclaim`** en el tool de síntesis (obligatorio con sub-claims asimétricos, §5) y **`absence_kind`** (`not-applicable | no-evidence-retrieved | evidence-of-no-effect`) — el catch de Sonnet en la corrida #1, ahora campo estructurado requerido: las dos ausencias son estados epistémicos OPUESTOS.
5. **Citas tipadas** (`citations: [{n, kind ∈ di-chunk|di-record|di-database|paper|store-resolution|other, id, note}]`) con **serie numérica**; la serie de letras queda **reservada al precedente** (bloque 6) — inconfundibles por construcción. El serializador que rechaza letras en la respuesta directa llega con el precedente.
6. **`TokenUsage` formal en el registro congelado**: `by_model` con conteos **medidos** de las respuestas del API (síntesis por pasada + panel por revisor + **embeddings** — antes invisibles, ahora contados desde `resp.usage` real en `embeddings.py`, con atribución declarada "ventana process-wide"), totales, y `estimated_cost_usd` **etiquetado como PROYECCIÓN** (`cost_class`; precios por Mtok como insumo fechado `2026-08`) — tokens = medición, dólares = cálculo declarado (clases de medición del ADR 2026-07-13).

## Consequences

- La pregunta de la corrida #1 ahora dispararía la Ruta B por confianza (pass1 declinó), traería literatura wt1a, y el delta quedaría medido — el loop de aprendizaje completo.
- La UI recibe todo lo que M4/M8 esperaban de este bloque: dos pasadas visibles, subclaims, absence_kind, citas contables con "ir al crudo" (`kind`+`id`), y costo por corrida agregable por usuario/periodo.
- Residuales honestos: serializador de series disjuntas + `PrecedentItem` (bloque 6); `Plan` condicional de M3 (bloque del planner); atribución de embeddings es por ventana (corridas concurrentes pueden solaparse — declarado en el campo); precios por Mtok requieren refresco manual (fechados).

## Verification (offline, deterministic)

`smoke_run_pipeline.py` → **27/27 PASS** (2026-08-10; 8 checks nuevos): sin-fallback (0.8≥τ) una pasada · gate por confianza (0.3<0.5 → Ruta B + `required_because=FALLBACK_FETCHED` + `stage.path_b`) · delta persistido (0.3→0.75 = +0.45) · estructural con dos pasadas · confianza ausente → gate + `absent-not-calibratable` · by_subclaim al registro · citas `{n:1, kind, id}` · TokenUsage by_model medido + `PROJECTION` etiquetado + embeddings 0 offline. Gates previos re-corridos en verde.

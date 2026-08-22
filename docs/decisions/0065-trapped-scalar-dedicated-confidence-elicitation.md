# ADR-0065 — El escalar atrapado se resuelve por ESTRUCTURA: elicitación dedicada de confianza (contrato 1.5)

- **Status:** Accepted — 2026-08-22. Item 2 de PENDIENTES DE BACK (`witt-ui-lab/HANDOFF-2026-08-22.md`);
  Emmanuel priorizó atacarlo antes que sus propios ajustes ("hagamos primero esto… podría impactar más
  cosas"). **La declaración de "resuelto en producción" queda PENDIENTE de corridas reales nuevas** —
  este ADR registra el fix medido a nivel unidad, no un cierre por fe (disciplina del handoff: "medir
  contra corridas nuevas antes de declarar resuelto").
- **Relates:** ADR-0057 (descubrió el fenómeno 2/2 y creó `recover_trapped_params`), ADR-0051 (el gate
  de fallback por confianza τ=0.5 que consume este escalar), ADR-0058 (la doctrina de declinación
  honesta — reapareció aquí como el near-miss semántico), CLAUDE.md §6 (no-hang).
- **Affects:** `rag_index/query_service/runs.py` (`CONF_TOOL` + `ELICIT_SYSTEM` + `_elicit_confidence`
  + `_default_synthesizer` + `synth_system` factorizado + bloque `confidence` del registro;
  `render_contract_version` → **1.5**) · **NUEVO** `evaluation/scripts/ab_trapped_scalar.py` (el
  instrumento de medición, re-corrible) · `smoke_run_pipeline.py` (+5 checks, 99/99). **Cero mutación
  DI.** Raws de TODAS las llamadas del experimento en `mcp_cache/ab_trapped_scalar/` (§7.9).

## Context

Opus 4.8, bajo `tool_choice` forzado con `SYNTH_TOOL`, emite la transición al siguiente parámetro en
sintaxis XML legada DENTRO del string de `direct_answer` (`…</parameter>\n<parameter
name="confidence">0.15`) y `confidence` llega None. Ocurrió en 6/6 corridas de producción y en 7/8
pasadas locales con usage vivo. La recuperación regex de ADR-0057 rescataba el valor con procedencia
declarada — pero cargaba el 100% del peso: ninguna corrida tenía confianza `stated` limpia, y el
experimento reveló además que la recuperación puede **mal-asignar** bajo formas nuevas del artefacto
(C#00: un nombre de framework aterrizó en `confidence` — `conf="Chain-of-Verification"`).

## La investigación (todo medido, todo cacheado en crudo)

Instrumento: `evaluation/scripts/ab_trapped_scalar.py` — misma pregunta y evidencia REALES (la corrida
wt1a `ea96d70e`, vista pass1), llamadas intercaladas, clasificación PRE-recuperación sobre el raw.

| Brazo | Qué prueba | Resultado |
|---|---|---|
| Evidencia previa | corridas locales con usage vivo | **7/8 pasadas atrapadas**; truncación DESCARTADA (traps con 989–2356 out-tokens vs tope 2500; una limpia con 1393) |
| **A** producción verbatim | tasa base | **5/8 atrapadas** (wt1a) + 2/4 y 4/4 (aldh1a2/RA) → 11/16 |
| **B** reorden de schema + descripciones anti-artefacto | ¿el orden de emisión obedece al schema? | **2/8** — pero el modelo emitió `direct_answer` PRIMERO en 16/16 llamadas de ambos brazos: **el orden del schema NO controla la emisión**; la mejora fue solo instruccional y no es significativa (Fisher vs A p≈0.13) |
| `temperature` | ¿matar la estocasticidad del slip? | **la palanca NO EXISTE**: 400 medido — *"`temperature` is deprecated for this model"* |
| **C** = B + ancla de formato en system nombrando los tokens XML | ¿más autoridad = menos slip? | **6/12 — PEOR que B**: nombrar los tokens los prima. Conclusión del prompting: el fenómeno es a nivel modelo (~25–60% por pasada) e insensible a nudges |
| **D** elicitación dedicada (sin semántica fijada) | ¿estructura sin strings largos? | **16/16 limpias, 0 traps — PERO \|delta\| mediana 0.75**: el elicitor devolvió 0.90 donde la síntesis decía 0.10–0.15, porque calificaba *"¿la declinación es correcta?"* en vez de *"¿la evidencia alcanza?"*. **Adoptarlo así habría roto el gate de fallback en silencio** (0.9 > τ → Ruta B jamás dispararía). El near-miss es la lección ADR-0058 reapareciendo en el instrumento de medición |
| **D'** elicitación con SEMÁNTICA CLAVADA al gate (declinación = confianza BAJA) | el candidato final | **20/20 limpias** (16 wt1a + 4 aldh1a2), \|delta\| mediana 0.09–0.14, max 0.15, sesgo sistemático-CONSERVADOR (elicitada ≤ in-line), jamás cruza τ en la muestra |

Gasto total del experimento: ~USD 2.5 (proyección desde tokens medidos; ~70 llamadas Opus). Los raws
completos de cada round viven en `mcp_cache/ab_trapped_scalar/<ts>/` con su `summary.json`.

## Decision

**La medición autoritativa del escalar deja de ser el campo in-line de `SYNTH_TOOL` y pasa a una
elicitación dedicada post-síntesis** (`CONF_TOOL`: un tool SIN campos de texto largo — estructuralmente
no hay string que contaminar — que emite la confianza VIENDO la respuesta completa, con la semántica
del gate clavada en el system: una declinación honesta puntúa BAJO porque el escalar significa "¿esta
evidencia alcanza?").

Reglas del flujo (todas con check en el smoke):
1. `confidence.source` gana el literal **`stated-second-elicitation`** (procedencia exacta, jamás
   disfrazada de `stated` in-line) → `render_contract_version` **1.5**.
2. **El instrumento previo PERSISTE**: `confidence.pass1_inline`/`pass2_inline` guardan el escalar
   in-line (o recuperado) — un cambio de instrumento se declara y ambas series sobreviven (continuidad
   de la calibración; las ~6 corridas históricas son del instrumento in-line).
3. Divergencia `|elicitada − in-line| > 0.15` → gap_flag declarado; la elicitada gobierna.
4. **Fallo de la elicitación JAMÁS bloquea** (§6 no-hang): se cae al camino ADR-0057 (in-line/
   recuperado, con su procedencia de siempre) + flag.
5. `recover_trapped_params` se queda como cinturón (limpia los artefactos del texto y rescata el
   cross-check y los demás campos atrapables — framework, gap_flags, etc.).
6. El gasto de la elicitación se FUSIONA al usage de la pasada (M8 cuadra); costo ≈ +USD 0.02/pasada
   (~1–2% del costo de una corrida).

## Alternatives considered

- **Solo prompting** (brazos B/C) — medido insuficiente: reduce en el mejor caso a ~25% y puede empeorar.
- **Retry-on-trap** (reintentar la síntesis al detectar recuperación) — con ~50% de tasa deja ~75%
  limpio por par de intentos, duplica el costo de síntesis cuando dispara y mezcla dos protocolos de
  emisión en la misma serie; inferior en todo a D'.
- **Quitar `confidence` del schema de síntesis** — rompería el contrato §5 del output del sintetizador
  y perdería el cross-check gratuito que hoy detecta divergencias.
- **Gate sobre `min(in-line, elicitada)`** — complejidad sin justificación medida; el sesgo conservador
  de la elicitada ya protege la dirección never-stopper.
- **Status quo (recuperación como palabra final)** — el objetivo era procedencia limpia; y C#00 mostró
  que la regex puede mal-asignar bajo formas nuevas del artefacto.

## Consequences

- Las corridas nuevas deben salir con `confidence.source: "stated-second-elicitation"` y sin el flag de
  recuperación como procedencia del escalar. **Verificación en producción pendiente**: la próxima
  corrida real es la medición que permite declarar el item resuelto.
- El sesgo conservador (−0.05..−0.15) empuja, si acaso, a disparar Ruta B de más — dirección segura
  (never-stopper); las fuentes B son gratis y la pass2 cuesta ~USD 0.05–0.08.
- Cambio de instrumento de calibración DECLARADO: el ECE de ADR-0064 consumirá `confidence.final` como
  siempre; si algún día se quiere separar las series por instrumento, `pass*_inline` + `source` lo
  permiten sin re-correr nada.
- Tensión de diseño anotada (NO resuelta aquí): la calibración humana de M5 califica *"¿la respuesta
  sirve?"* (cercano a corrección), mientras el escalar del gate mide *suficiencia de evidencia*. Para
  una declinación honesta esas dos preguntas divergen por construcción — decisión de diseño de
  calibración para cuando haya volumen (se cruza con ADR-0058/0064).
- Webapp (FRONT): `render_contract_version` 1.5 — regenerar fixtures (`tools/gen_fixtures.py`), tipar
  el literal nuevo de `source` y los campos `pass1_inline`/`pass2_inline`.
- Gates: `smoke_run_pipeline.py` **99/99** (los 5 nuevos cubren: gobierna-elicitada + usage fusionado,
  divergencia declarada, recovered-como-cross-check + subclaims elicitados, caída→fallback §6,
  ausencia declarada) · resto de la suite sin regresión (29/29 · 29/29 · 15/15).

## Evidence

- `mcp_cache/ab_trapped_scalar/20260822T185925Z/` (A/B, 16 raws + summary) ·
  `…T190351Z/` (C, 12) · `…T190740Z_elicit/` (D near-miss, 16) · `…T190844Z_elicit/` (D', 16) ·
  `…T190948Z/` + `…T191032Z_elicit/` (aldh1a2 medio, 4+4) · `…T191044Z/` (RA, 4)
- `evaluation/scripts/ab_trapped_scalar.py` (instrumento re-corrible; referencia las definiciones de
  producción post-adopción)
- ADR-0057 §hallazgo 2 (el descubrimiento original) · `witt-ui-lab/HANDOFF-2026-08-22.md` §PENDIENTES
  DE BACK item 2 (las pistas: "reforzar el prompt o el orden de campos" — ambas medidas aquí, ambas
  insuficientes; la salida fue estructural)

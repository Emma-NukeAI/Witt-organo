# ADR-0060 — Los tres campos §5 que faltaban: `framework_applied` con sección resuelta por tabla, `agents_invoked` derivado, `alternatives_considered`

- **Status:** Accepted — 2026-08-20. Tapón 2 del plan de `witt-ui-lab/01-mapa/harness-en-la-webapp.md`.
- **Relates:** CLAUDE.md §5 (contrato de salida + su nota crítica sobre self-report), §4 (selección de framework y la cita obligatoria del catálogo), §11 (preflight de invocación de agentes), §7 (prohibición de auto-auditoría), ADR-0046 (derogación del reporte HTML en la era webapp — el registro congelado ES la traza), ADR-0059 (tapón 1·A).
- **Affects:** `analysis/scripts/lib/reasoning_catalog.py` (**nuevo**), `rag_index/query_service/runs.py`, el gate, y en la webapp `src/api/types.ts` · `src/modulos/M4Hoja/Hoja.tsx` · `tools/gen_fixtures.py`. **Sube `render_contract_version` a 1.3.**

## Contexto

`grep` de los tres campos del contrato §5 en el pipeline de la webapp daba **cero**:
`framework_applied`, `agents_invoked` y `alternatives_considered`. Es decir: el 100% de las corridas de
la webapp violaba §5 en tres puntos, y una de esas violaciones está explícitamente nombrada en el
contrato — *"la asimetría entre formatos de presentación es una violación de contrato"* (§5, sobre
`alternatives_considered`).

Con ADR-0046 el reporte HTML dejó de emitirse en la era webapp porque **el registro congelado ES la
traza de auditoría**. Eso convierte la ausencia de estos campos de "falta un adorno del reporte" a
"la traza de auditoría está incompleta".

## La decisión de diseño que gobierna todo lo demás

§5 ya trae su propia nota crítica: `framework_applied` es **self-report, no introspección fiel** — los
LLMs no introspectan su razonamiento de forma confiable (Anthropic, abril 2025); trátese como *etiqueta
de prompt-time*, nunca como afirmación verificada.

Entonces el campo no puede persistirse como si fuera una medición. La consecuencia se propaga a las tres
decisiones:

1. **El modelo elige el NOMBRE; la SECCIÓN y el TIER los resuelve una tabla.** `reasoning_catalog.py`
   mapea los 8 frameworks del catálogo v1.2 a `(sección, tier, criterio)`. El modelo escoge de un enum
   cerrado y **cita el criterio**; `runs.py` resuelve el resto. §4 documenta el anti-patrón que esto
   mata: dos sesiones reales (2026-05-09 y 2026-05-14) etiquetaron salidas como "Tier 2" sin consultar
   el catálogo, y citar el header del tier en vez de la sección del framework es en sí mismo falla de
   auditoría. Un modelo que no emite el número de sección **no puede** emitir uno equivocado: el
   anti-patrón pasa de prohibido a estructuralmente imposible.
2. **La cita se comprueba.** `criterion_matches_catalog` mide el traslape de tokens entre lo que el
   modelo citó y el criterio real del catálogo. No rechaza nada — **declara**. Una paráfrasis es una
   cita más débil, no una fabricada, y la diferencia queda en el registro.
3. **El catálogo viaja en el prompt.** Un criterio no se puede citar de un archivo que el modelo nunca
   vio: exigir la cita sin entregar el catálogo **fabrica números de sección**, que es peor que no
   exigir nada. `reasoning_catalog.digest()` es lo que se inyecta.

Y el contrapeso honesto: **`structural_frameworks`, derivado del código.** Lo que el pipeline aplica
pase lo que pase con la etiqueta del modelo — Logic-LM (§5) en `verify_output`, el panel adversarial y
las dos pasadas con gate de confianza. Ahí sí hay garantías, no self-report. El panel se nombra **como
lo que es**: `agregación worst-of-N`, con la nota explícita de que **NO es Self-Consistency (§4)**
porque no hay voto por mayoría — disfrazarlo de framework de Tier 1 sería exactamente el tipo de
overclaim que este sistema existe para impedir.

## `agents_invoked` se DERIVA, no se pregunta

§11 pide el campo; §7 prohíbe la auto-auditoría. Pedirle a un modelo la lista de agentes que invocó es
self-report sobre su propia conducta — precisamente el patrón prohibido. El código sabe qué corrió:

- `composite-auditor` → `invoked`, con `invocation_id: panel:<válidos>/<total>` y el veredicto como
  `evidence_generated`.
- `verify_output` (gate determinista, clase Logic-LM) → `invoked`.
- **El hueco, declarado en cada corrida:** `(preflight §11 sobre el catálogo de agentes)` →
  **`not-assessed`**. §11 exige decidir qué agente del catálogo es dueño del work-type y, o invocarlo, o
  saltarlo con justificación. La ruta HTTP no tiene planner (tapón 3), así que **ese juicio no se hizo**.
  `not-assessed` **no** es `skipped-ad-hoc`: saltarse con justificación afirma que alguien juzgó; esto
  afirma que nadie juzgó. La distinción es el punto — el hueco viaja visible en cada registro en vez de
  ser invisible.

## Tres estados, como en todo este contrato

`alternatives_considered`: **`null` (ausente) no es `[]`**. Ausente es hueco del sistema; lista vacía es
una afirmación fuerte de esta corrida ("se consideraron y no había"). La UI las pinta distinto: hueca vs
maciza. Y cuando el modelo omite el campo, el sintetizador **agrega un `gap_flag`** en vez de rellenar
con `[]`.

## Consequences

- El registro congelado 1.3 responde "¿con qué se razonó?" con dos capas separadas por clase epistémica:
  declarada (self-report, marcada) y estructural (derivada del código).
- La hoja gana la **sección 5 · MÉTODO DECLARADO**, en la ranura que el boceto M4 tenía reservada.
  Registros 1.0–1.2 muestran `···· NO INSTRUMENTADO` completo (regla 9) — no se inventa retroactivamente.
- Sube el costo por corrida marginalmente (el digest del catálogo son ~15 líneas de prompt): 0.2082 USD
  medido contra 0.1833 de la corrida 1.2 equivalente.
- `framework_applied` queda disponible para las analíticas de efectividad de frameworks que menciona §5
  — **con la advertencia pegada al dato**, no en una nota al pie que el consumidor puede no leer.

## Verification

**Offline, determinista:** `smoke_run_pipeline.py` → **67/67 PASS** (+13: sección y tier por tabla ·
marca self-report en todos los caminos · cita real hace match · cita inventada se declara no-coincidente
· `NONE-MATCHED` con sección/tier nulos y la declaración de §4 · nombre fuera del vocabulario registrado
crudo y marcado `off_catalog` · `structural_frameworks` derivado · el panel no se disfraza de
Self-Consistency · `agents_invoked` derivado con su `invocation_id` · el hueco del planner como
`not-assessed` ≠ `skipped-ad-hoc` · `alternatives_considered` en el registro · ausencia como `null` y no
`[]` · el digest va en el prompt). `smoke_query_service.py` → **29/29**.

**Webapp:** `npm run gate` → **121/121** (+9 sobre la sección nueva, contra fixtures **regenerados por el
código real del backend**).

**Corrida real** `49e440b65d494f008cbad552b7efa1c9` (Neo4j real, Opus 4.8 real, panel real, ZFIN real,
USD 0.2082, contrato 1.3, `AUDIT_APPROVED` / `APPROVE_MINOR`):

- Opus declaró **`Chain-of-Verification`** — la tabla resolvió **§8 · Tier 2**.
- Citó *"favored for high-stakes outputs, but excessive verification degrades performance on simple
  problems; context-dependent"* → `criterion_matches_catalog: true`, traslape **0.867**. La cita salió
  del catálogo de verdad.
- `alternatives_considered` trajo **4 lecturas descartadas**, y una es razonamiento que ningún campo
  anterior capturaba: *los conflictos normal/anormal en túbulo trazan a PMIDs distintos, consistente con
  diferencias de alelo/dosis (morfante vs mutante)* — o sea, no descartó el dato conflictivo como ruido,
  lo explicó.
- `agents_invoked`: `composite-auditor` invoked `panel:4/4`; el preflight §11 `not-assessed`.

## Hallazgo colateral, corregido

Regenerar los fixtures de la webapp destapó que **estaban una versión atrás**: traían
`source_vocabulary` de 3 literales cuando el backend usa 4 desde ADR-0058 (`APPROVE_DECLINE`). El gate
de la UI llevaba días validando contra un contrato viejo, y eso lo hace un gate que miente. Corregido, y
la derivación del fixture pre-1.1 ahora también quita las llaves de 1.3 para seguir siendo fiel.

## Pendiente que esta decisión NO cierra

`framework_applied` sigue siendo self-report y esta decisión **no** lo convierte en medición — sólo hace
la cita comprobable y el tier confiable. Tapón 1·B (SDK de Tool Universe) · tapón 3 (planner de M3, que
es lo que convertiría `not-assessed` en un juicio real) · tapón 4 (M5 + calibración) · tapón 5 (evals).
Y el hallazgo abierto de ADR-0059: el escalar de confianza sigue llegando atrapado en el texto en 4 de 4
corridas reales.

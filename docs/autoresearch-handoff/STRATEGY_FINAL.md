# STRATEGY_FINAL — autoresearch → witt-organogenesis (handoff completo)

> **Para qué sirve este documento.** Es el handoff de una sola pieza desde el run de autoresearch
> hacia tu proyecto Witt. Junta: qué se probó, qué se mejoró (la *estrategia*, no el modelo), las
> 3 evoluciones del `program.md`, y **6 prescripciones concretas** para `organogenesis-agent-architect`.
> Si ya leíste `AUTORESEARCH_SCOPE.md`, `FINDINGS_may26.md` y los `LEDGER.md`, esto es la síntesis.
> Si no, esto es lo único que necesitas leer para entender y aplicar.

---

## 0. Cómo leer este doc

| Si eres… | Salta directo a |
|---|---|
| diseñador de agentes Witt (organogenesis-agent-architect) | **§5** (prescripciones accionables) |
| revisor de evidencia de substrato (Tests 3/4) | **§6** (números) |
| curioso por la meta-estrategia | **§3** (evolución v1→v2→v3) |
| nuevo en el tema | empieza arriba, lee §1–§3, luego §5 |

Documentos fuente en este repo: `AUTORESEARCH_SCOPE.md` (brief inicial), `FINDINGS_may26.md`
(detalles del primer run), `LEDGER.md` (estado v3 + comparación medida), `program.md` (la
estrategia v3 ejecutable).

---

## 1. Qué se probó (1 párrafo)

`autoresearch` se usó como **banco de pruebas limpio** del substrato Witt: una métrica
objetiva (`val_bpb`), un loop rápido (5 min), reversibilidad total (git), cero riesgo de dominio.
El modelo GPT que `train.py` entrena es un **marcador desechable**. Lo que se puso a prueba —y
mejoró— fue **`program.md`: la estrategia de organización de investigación autónoma** (cómo un
agente explora, decide keep/discard, recuerda, calibra, escala a humano). Esa estrategia es una
*instancia concreta* de tu tesis Witt; los hallazgos transfieren al diseño de agentes en
`organogenesis-agent-architect`.

## 2. Qué significa "mejorar el substrate" (la confusión disuelta)

Tres capas, no se confunden:

| Capa | Qué es | En este run | Para Witt |
|---|---|---|---|
| **Objeto** | `train.py` (el código que el agente edita) | un GPT de juguete; desechable | el artefacto de investigación que tu sistema produce |
| **Estrategia** | `program.md` (las reglas que el agente sigue) | **mejorada v1→v2→v3 (el producto)** | tu SKILL.md / orquestación de agentes |
| **Evidencia** | Documento como éste + LEDGER + plot | el output transferible | lo que entra a tu base de evidencia substrato |

**Mecánica:** durante un run, el agente mejora el OBJETO. Entre runs, el HUMANO mejora la
ESTRATEGIA (apoyado en la evidencia). En este ejercicio se completaron **3 ciclos** de eso:
v1 → v2 → v3, cada uno con un fallo detectado en la corrida anterior y aprobado por gate humano.

---

## 3. La evolución de la estrategia (la demostración del meta-loop)

| Versión | Mejora vs anterior | Cómo se descubrió | Validación |
|---|---|---|---|
| **v1** | (baseline tipo Karpathy) | — | Run de 26 exps: encontró 3 wins reales (depth 4→6, batch 2¹⁶→2¹⁵, MATRIX_LR 0.04→0.05). Pero EPS=0.0002 era 45× muy fino → conservó 1 win espurio. Sin manejo de drift → 20 exps tardíos sesgados por throttling. Calibración cada 10 → sobre-optimista (12.5% hit-rate). |
| **v2** | • EPS medido del ruido empírico • drift-aware (re-mide frontier) • pivote tras plateau • calibración reactiva | Lecturas de v1 destiladas en `FINDINGS_may26.md` §4. | Run de 6 exps: mismo frontier real (1.2577) en **¼ del presupuesto**, **0 keeps espurios** (LR rechazada correctamente), throttling detectado en vivo. **Pero** el chequeo de drift comparaba `num_steps` crudos entre configs distintos → falsa alarma en cualquier config más pesado (depth 6 disparó la alarma). El propio v2 levantó esto como `governance-proposal`. |
| **v3** | • **Frontier efectivo** (re-medición same-config periódica) • **NUNCA** comparar `num_steps` entre configs distintos | `governance-proposal` de v2, aprobada por gate humano. | Run de 2 exps: Run 1 fijó effective_frontier; Run 2 (depth 8, heavier config) — el caso que rompía a v2 — fue *discard limpio sin falsa alarma*. **Fix validado.** |

**El número que más enseña, para Witt:** el mismo config frontier valió **1.2577 frío / 1.2608
templado / 1.2848 caliente** en este hardware — **0.027 de swing solo por throttling**, que
*empequeñece* casi todo lo que v1 llamó "resultado". Lección general: **sin medir tu piso de ruido,
estás reportando ruido como hallazgo.** Aplica idéntico a evals con LLMs (drift de proveedor,
versión, infra).

---

## 4. La estrategia final (`program.md` v3), en una página

Los 9 pilares y por qué cada uno importa:

1. **Una métrica única, sagrada.** En autoresearch es `val_bpb`; en Witt sería tu eval congelado.
   El agente no puede tocar la métrica. Sin esto, "mejora" es opinión.
2. **Un único archivo mutable.** `train.py` aquí; en Witt el equivalente es el artefacto que tu
   sistema produce. Mantiene el alcance del agente angosto y diffs revisables.
3. **§1b — Sonda de ruido al inicio (NUEVO en v3).** Antes de buscar nada, corre el baseline DOS
   veces. La diferencia = piso de ruido. **Fija `EPS = 2 × ruido_medido`.** Sin esto, no
   distingues señal de ruido (v1's pecado original).
4. **Contrato estructurado por experimento.** Cada experimento registra `hypothesis,
   predicted_direction, predicted_delta, confidence, framework_applied, evidence_cited,
   alternatives_considered, result, decision, outcome_vs_prediction, lesson, gap_flags`.
   Predicciones **pre-registradas en el commit message** (no se pueden racionalizar después). Es
   exactamente tu contrato `reasoning-exposer` con calibración medible adentro.
5. **Regla keep/discard determinista + parsimonia.** No es "a ojo": `KEEP iff result < effective_frontier - EPS`,
   parsimony tie-break al diff más pequeño. Es tu patrón `composite-auditor`, instanciado.
6. **Frontier efectivo (NUEVO v3).** Compara contra una medición FRESCA del mismo config, no
   contra un número viejo. Cada `REMEASURE_EVERY` experimentos, re-mide el frontier.
7. **Calibración reactiva.** Hit-rate rolling se actualiza cada experimento; si baja del umbral,
   las confianzas se capan automáticamente. Es tu `calibration-tracker`, vivo.
8. **Pivote tras plateau.** Tras 3 discards consecutivos, deja de barrer knobs (los defaults
   probablemente ya están afinados); ve a estructural/combinación o detente. Evita los 20 exps
   desperdiciados de v1.
9. **Cola asíncrona de human-gate + `governance-proposal`.** Cambios de alto impacto se aplican
   provisionalmente y se encolan; el agente puede proponer cambios al *propio* `program.md` pero
   nunca aplicarlos solo. Es tu disciplina HUMAN GATE no-negociable. Es por donde v3 nació.

---

## 5. Prescripciones para `organogenesis-agent-architect` (la parte accionable)

Cada hallazgo del run → un cambio concreto en tu skill, mapeado a un agente / referencia existente:

### 5.1 `evaluation-runner` v2.2 → **añadir sonda de ruido**
**Adición:** mandatorio correr el eval dos veces idénticas en cada snapshot (mes 0, 4, 8) para
medir el piso de ruido empírico (varianza del MISMO config). Después, fijar el umbral mínimo de
diferencia interpretable como `EPS = 2 × σ_medido`. **Razón:** sin esto, Vega et al. + Mirzadeh +
nuestras 0.0045 unidades de drift demuestran que reportas ruido como hallazgo. Esto **complementa**
las perturbaciones numéricas/orden/superficie de v2.2 — el drift es una *cuarta* perturbación, la
del entorno.

### 5.2 `substrate-evidence-guide` → **frontier efectivo bajo Test 3**
**Adición:** la sección de Test 3 (iteration loop) debe incluir que "best" no es un número fijo
sino una **medición fresca del mismo config bajo condiciones actuales**. Drift de modelo (versión
nueva del proveedor), drift de dataset, drift de infra existen. Sin re-medición same-config, los
hallazgos de iteración se contaminan con drift de fondo y la calibración miente.

### 5.3 `composite-auditor` → **EPS empírico, no arbitrario**
**Adición:** los modos Self-Consistency y Logic-LM ya filtran bien; añadir que sus umbrales de
acuerdo / certidumbre se calibren **contra ruido medido**, no como constantes (la práctica actual
de "70% acuerdo" es arbitraria). En modo Logic-LM (criterios formalizables), el `EPS` numérico
sale de la sonda de ruido (§5.1).

### 5.4 `calibration-tracker` → **reactivo, no periódico**
**Adición:** la calibración debe actualizarse **cada output**, no cada N (la guía v1.2 dice "cada
trimestre" y "cada CALIB_EVERY"; eso es demasiado lento). El run muestra que con tracking continuo
la sobre-optimismo se detecta y corrige al exp 11, no al exp 25. Implementación: rolling hit-rate
sobre los últimos K outputs (recomendado K=6); si cae <umbral, capar confianzas hasta recuperar.

### 5.5 Catálogo (cualquier orquestador) → **pivote tras plateau**
**Adición:** todo agente que ejecute trabajo iterativo (sim-orchestrator, evaluation-runner,
substrate-evidence-weekly) debe tener una regla `PIVOT_AFTER = N consecutive null results → cambiar
modo o detener y resumir`. v1 quemó 15+ experimentos confirmando defaults; v2/v3 lo evitaron. En
Witt: `causal-pruner` y `experiment-designer` son los principales candidatos.

### 5.6 Todos los agentes substrate-instrumented → **derecho a `governance-proposal`**
**Adición:** cualquier agente puede escribir entradas tipo `governance-proposal` en su propia cola
de human-gate cuando detecte ineficiencias o errores en su propio proceso. v2 lo hizo: detectó su
*propio* chequeo de drift como buggy y propuso el fix. Es **el meta-loop literal**, escala mejor
que esperar que el humano descubra todo. La regla §15 del `program.md` v3 es directamente
trasladable a SKILL.md.

---

## 6. Evidencia de substrato producida (Test 3 + Test 4, con ground truth)

### Test 3 — Iteration loop (el substrato compone con el uso)

- **3 versiones de la estrategia** (v1, v2, v3), cada una mejor que la anterior, validadas en
  hardware idéntico contra el mismo baseline (val_bpb 1.2577 cool):

  | | exp budget | frontier alcanzado | keeps espurios | wasted exps | governance fixes auto-detectados |
  |---|---|---|---|---|---|
  | v1 | 26 | 1.2572 (incluía 1 keep ruido) | **1** | ~20 | 0 |
  | v2 | 6 | 1.2577 (honesto) | **0** | 0 | **1** (drift-rule bug, propuesto y aprobado) |
  | v3 | 2 (validación) | 1.2577 mantenido | 0 | 0 | 0 |

- Cada keep espurio evitado, cada experimento ahorrado, y cada fix propuesto son **señales
  cuantitativas de compounding-through-use**. ECE-style: no aplican directamente, pero el
  hit-rate sobre predicciones pre-registradas (§6 abajo) sí.

### Test 4 — Calibration (la confianza coincide con la precisión)

| | improve-preds | hits | hit-rate | conf hits (mean) | conf misses (mean) |
|---|---|---|---|---|---|
| v1 | 24 | 3 | **12.5%** (sobre-optimista) | 0.48 | 0.43 |
| v2 | 2 | 2 | **100%** (disciplinada) | 0.5 | — |
| v3 | 1 worse-pred (+ 3 neutral-preds correctos) | 1 | **100%** (alineada) | 0.6 | — |

- v1: predijo "improve" demasiado seguido; **self-detectó** la sobre-optimismo al exp 11 y bajó
  confianzas (calibración reactiva *funciona*).
- v2/v3: predicciones reservadas (sólo cuando había base) → mucho mejor calibración. Acertaron
  llamar "neutral" al LR-tweak que v1 erró como win.

### Lo que esto significa concretamente para Witt

> Un sistema de agentes con la disciplina de v3 (predicción pre-registrada + EPS medido + frontier
> efectivo + auditor determinista + human-gate + calibración reactiva) produce **mejora medible y
> honesta**, **se auto-corrige a través del gate humano**, y **NO reporta ruido como hallazgo** —
> exactamente lo que tu defensibilidad ante stress-test exige.

---

## 7. Lo que este run NO probó (disciplina de auditoría, per PROJECT_SCOPE §5)

Honestidad obligatoria — la credibilidad del substrato depende de marcar lo no demostrado:

- **No es investigación de LLM-pretraining.** Los números de val_bpb son scoreboard de un toy GPT;
  no citarlos como hallazgos algorítmicos.
- **El mismo agente** (Claude en la misma sesión) ejecutó v1, v2 y v3 → parte de las ganancias
  pueden estar entrelazadas con el agente aprendiendo entre versiones. Un test limpio requeriría
  un agente fresco siguiendo cada estrategia. El **fix mecánico** de v3 (EPS empírico, frontier
  efectivo) NO depende del agente y es transferible directamente. El **orden de exploración** sí.
- **Cross-field (Test 5) intocado.** Este run es mono-dominio (LLM pretraining); no aporta
  evidencia de transferencia cross-field. Per PROJECT_SCOPE v1.2, Test 5 sigue exploratorio.
- **El throttling es específico de laptop.** En un H100 de datacenter no aplica; pero la lección
  meta (siempre medir tu ruido) es universal y aplica a cualquier eval LLM (drift de versión, de
  prompt, de dataset, de infra).
- **Budget chico.** Aún v1 con 26 experimentos es pequeño; con presupuesto mayor podrían existir
  combinaciones estructurales que no exploramos.

---

## 8. Próximos pasos concretos en `witt-organogenesis`

1. **Issue/ADR:** "EPS debe medirse, no asumirse" — análogo a la decisión v2.2 que hizo
   perturbaciones obligatorias en `evaluation-runner`. Referenciar este doc.
2. **PR a `evaluation-runner.md`:** añadir la sonda de ruido (§5.1) al protocolo obligatorio.
3. **PR a `substrate-evidence-guide.md`:** añadir el patrón frontier-efectivo bajo Test 3 (§5.2).
4. **PR a `calibration-tracker.md`:** switch a rolling/continuous (§5.4).
5. **PR a `agent-catalog.md`:** añadir la regla `PIVOT_AFTER` a `sim-orchestrator` y
   `causal-pruner` (§5.5).
6. **Mini-experimento Witt:** correr UN agente Witt (e.g., una corrida del flujo de hipótesis-a-evidencia)
   bajo dos versiones de su SKILL.md — una sin estos patrones, una con — y producir una tabla
   comparativa análoga a la de §3. Eso convierte la afirmación transferible en evidencia
   Witt-nativa.

---

## 9. Apéndice — Artefactos en el repo `autoresearch` (referencia)

| Archivo | Contenido | A quién sirve |
|---|---|---|
| **`program.md`** (v3) | La estrategia ejecutable | el agente que correrá el loop |
| **`STRATEGY_FINAL.md`** | (este doc) | el handoff a Witt |
| `FINDINGS_may26.md` | Detalles del run v1 + mapeo inicial | quien quiera más profundidad sobre v1 |
| `AUTORESEARCH_SCOPE.md` | Brief original del proyecto autoresearch | nuevos en el contexto |
| `LEDGER.md` | Estado v3 actual: frontier, comparaciones, lessons | revisar el último run en detalle |
| `LEDGER_v1.md`, `LEDGER_v2.md` | Snapshots históricos | trazabilidad |
| `results.tsv` / `results_v1.tsv` / `results_v2.tsv` | Tablas de experimentos | gráficas, auditoría numérica |
| `ledger.jsonl` / `ledger_v{1,2}.jsonl` | Registros estructurados por experimento (contrato §8) | data source para calibración / ECE |
| `progress_may26.png` | Curva de descenso del run v1 | visual rápida |
| `train.py` (frontier) | El config ganador (DEPTH=6, TOTAL_BATCH=2**15, MATRIX_LR=0.04) | curiosidad técnica; **no es el entregable** |

Rama git: `autoresearch/may27-v3`. Frontier commit: `c738c82` (program.md v3 + train.py frontier).

---

*Fin. Llévate este doc al repo `witt-organogenesis` (puedes ponerlo en `docs/` o como referencia
de ADR). La afirmación transferible vive en §6; los cambios accionables en §5.*

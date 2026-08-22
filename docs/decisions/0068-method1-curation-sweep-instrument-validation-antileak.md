# ADR-0068 — Curación Método 1 estilo map-reduce (gate humano intacto) + validación de instrumento + disciplina anti-fuga (adopciones VB #3–#5)

- **Status:** Accepted — 2026-08-22. Fases 3–5 del roadmap de adopciones aprobado por Emmanuel
  ("¿por qué no hacemos de la fase 2 a la 5?") tras la comparativa contra *The Virtual Biotech*
  (`reports/2026-08-22_virtual-biotech-vs-witt-organo_comparativa_v1.html`). La fase 2 (webapp a
  contrato 1.6 + plan v3) se entregó el mismo día en `witt-webapp@bd108b6`.
- **Relates:** ADR-0022 (gate humano de ingesta — INTACTO), ADR-0027/0059 (el tool ZFIN Layer-0),
  ADR-0005/0030/0037 (lenguaje de claims), method-selection v1.2 (Método 1 = acotado, reversible,
  repetible), la constitución de Emmanuel (lo repetible va a un ejecutable, jamás al modelo).
- **Affects:** **NUEVO** `rag_index/curation/zfin_sweep.py` + `smoke_zfin_sweep.py` (12/12) +
  `quarantine/` (gitignored) · **NUEVO** `evaluation/EVAL_DESIGN.md` (F5). **Cero mutación DI.**

## Context

El paper VB demostró curación masiva confiable con su doctrina: un agente por unidad de trabajo con
contexto completo, schema validado, cascada de fuentes declarada, fuente por campo, y validación del
instrumento por muestreo humano (n=100, concordancia por campo, taxonomía de desacuerdos). Nuestra
deuda de corpus equivalente: el paisaje genotipo→fenotipo del pronefros (S4 penetrancia cubre ~19
genes; la corrida real #1 falló por falta de evidencia funcional wt1a↔pronefros en la DI).

## Decision

**(1) F3 — El barrido de curación adopta la doctrina VB con dos diferencias deliberadas:**
- **Determinista, sin LLM** para fuentes YA estructuradas: ZFIN entrega statements con PMIDs vía
  Alliance API — no hay juicio que delegar; el "agente por unidad" de VB se vuelve "request por
  unidad" (constitución: lo repetible va a CLI). La etapa que SÍ necesitará agentes-lectores
  (extracción de penetrancia desde papers EPMC, como el barrido CORPUS-2026-0008) reutilizará esta
  misma plantilla de cuarentena+muestreo cuando se haga.
- **El gate humano de ingesta queda INTACTO** (hard rule §7/ADR-0022): el sweep produce una
  PROPUESTA EN CUARENTENA (`rag_index/curation/quarantine/`, gitignored) — jamás toca store,
  manifest ni Neo4j. VB no gatea porque no muta; nosotros mutamos la verdad, así que gateamos.

Doctrina VB conservada: símbolos SOLO del store verificado (jamás inventados — fuera del store =
salida con error) · ledger tri-estado por unidad (success | no-match | error: "no hay" ≠ "falló") ·
fuente por campo (curie, PMIDs, retrieved_at, raw_ref) · crudo cacheado antes de procesar (§7.9) ·
señal pronephr derivada localmente y declarada como derivación.

**(2) F4 — Validación de instrumento por muestreo, integrada y estándar:** todo lote produce una
muestra aleatoria REPRODUCIBLE (seed declarado) + CSV de concordancia + protocolo con la taxonomía
de desacuerdos de VB (ambigüedad intrínseca vs error del instrumento). El resultado se reporta
*measured*, jamás *validated* (ADR-0005). Estándar para todo Método 1 futuro (va en EVAL_DESIGN §2).

**(3) F5 — Disciplina anti-fuga codificada** en `evaluation/EVAL_DESIGN.md`: web tools apagadas en
held-out · verdad-terreno post-cutoff preferida y el cutoff registrado · verificación de
no-publicación para claims de novedad. El Tapón 5 se construirá contra ese diseño.

## Piloto ejecutado (2026-08-22, mismo día — prueba pequeño)

Los 113 genes del store contra el API real de Alliance: **112 success + 1 no-match (slc12a1a,
declarado — el autocomplete no lo resolvió) · 3,087 statements de fenotipo · 161 con match
'pronephr' · 88.8 s · cero gasto de modelo.** Top pronefros: irx3b (20), osr1 (20), sim1a (18),
nphs1 (16), **wt1a (16 — exactamente la clase de evidencia nativa que la corrida real #1 no tenía
en la DI)**. Muestra F4 de 25 statements lista para concordancia humana.

## Alternatives considered

- **Réplica literal de VB (37K agentes LLM)** — rechazada para ZFIN: gastar modelo en re-leer datos
  ya estructurados viola la constitución; los agentes-lectores quedan para fuentes NO estructuradas
  (papers EPMC), segunda etapa sobre esta plantilla.
- **Ingesta directa de lo barrido** — prohibida (hard rule): la DI es human-gated SIEMPRE; el
  volumen de propuesta se maneja con revisión por lotes + muestreo, jamás quitando el gate.
- **Commitear la cuarentena** — rechazado: es propuesta, no verdad; bulto sin procedencia aprobada.
  Lo versionado es el INSTRUMENTO (tool + smoke + protocolo), no su salida.

## Consequences

- Camino claro para crecer la DI con escala VB y estándar Witt: (a) Emmanuel llena la muestra F4
  (25 filas, ~20 min); (b) si la concordancia es alta y los desacuerdos son ambigüedad intrínseca,
  se decide el ALCANCE de ingesta (p. ej. solo statements pronefros, o por gen) y se propone vía el
  flujo add_dataset/approve human-gated; (c) la segunda etapa (agentes-lectores EPMC para
  penetrancia) hereda plantilla y protocolo.
- El candidato de paper (2) de la comparativa — dataset-release del paisaje fenotípico del
  pronefros con procedencia total — deja de ser idea: el instrumento existe y está gateado.
- Gates: `smoke_zfin_sweep.py` **12/12** offline (tri-estado, §7.9, F4 reproducible, no-invención,
  cero mutación del store por sha256).

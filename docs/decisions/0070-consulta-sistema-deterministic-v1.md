# ADR-0070 — La consulta abierta del sistema, v1 DETERMINISTA (`GET /consulta-sistema`)

- **Status:** Accepted — 2026-08-22. Construye el módulo que ADR-0063 nombró y dejó pendiente
  (*"agente que lea /status + /taxonomia + manifest y responda la pregunta meta en lenguaje
  natural… módulo propio, no parche a Preguntar"*), item 3 de PENDIENTES DE BACK. Origen real:
  Emmanuel preguntó en producción "dime qué tenemos en data inamovible" y el planner ruteó
  correctamente FUERA del pipeline — pero nadie respondía la pregunta; la card solo daba links.
- **Relates:** ADR-0063 (la ruta store-consultation), ADR-0055/0056 (las puertas /status,
  /taxonomia, /config-history que esto agrega), ADR-0068 (la cuarentena que esto inventaría),
  ADR-0062 (el precedente de cambiar el MECANISMO con razón manteniendo el objetivo).
- **Affects:** **NUEVO** `rag_index/query_service/consulta_sistema.py` · `app.py`
  (`GET /consulta-sistema?q=`) · `db.py` (`run_state_tally`) · `smoke_query_service.py` (+6).

## Context

El handoff nombraba "un agente" con respuesta "en lenguaje natural" — y advertía el problema en la
misma línea: *"una respuesta de modelo sin panel no puede verse homologada"*. La clase de pregunta
es INVENTARIO (conteos, versiones, estados, composición): todas sus respuestas ya existen como
datos estructurados con procedencia.

## Decision

**v1 determinista, sin modelo** (mecanismo cambiado con razón — patrón ADR-0062; el objetivo, la
pregunta meta RESPONDIDA en lenguaje natural, se entrega):

- **Snapshot por secciones con fuente declarada:** store (vía el /status NO-SPEND TTL-cacheado) ·
  índice (Neo4j Meta; OFFLINE = null jamás inventado) · corpus (manifest: n, tally por nicho,
  último id, path+mtime) · taxonomía · corridas (tally por estado de la BD; cerradas = precedente)
  · config (historial) · curación (propuestas en cuarentena, ADR-0068).
- **El lenguaje natural lo compone CÓDIGO** desde plantillas donde cada cifra sale del snapshot
  (lecturas en vivo autofechadas por `read_at`) — la constitución: lo repetible va a un ejecutable.
- **Ruteo por palabras clave declarado:** q con señal filtra secciones (`q_matched_sections`);
  sin match = snapshot completo con el no-match DECLARADO (null), jamás una adivinanza.
- **`model_consulted: false` estructural** — la homologación no se simula. Si el uso real
  demuestra preguntas que las plantillas no cubren, la capa de modelo será un ADR aparte
  (aditivo, con su propio ledger de gasto para que M8 cuadre).
- NO-SPEND por construcción (archivos + GROUP BY + el status cacheado).

## Alternatives considered

- **El agente LLM del handoff** — diferido con razón: gasto y problema de homologación para una
  clase de pregunta cuyas respuestas son datos; el resumen de plantilla responde la pregunta real
  que motivó el módulo. La capa de modelo queda como extensión medida-por-necesidad.
- **Parche a Preguntar** — rechazado por ADR-0063 mismo: módulo propio.
- **Solo devolver el snapshot crudo (sin resumen)** — rechazado: la pregunta del fundador pedía
  una RESPUESTA; el resumen compuesto por código la da sin sacrificar procedencia.

## Consequences

- La card de ruta de la webapp puede ahora ENLAZAR a una respuesta real (`/consulta-sistema`),
  no solo a puertas — trabajo FRONT: una vista simple que pinte `resumen` + secciones con fuente
  (nota en el addendum del handoff).
- Gates: `smoke_query_service.py` **38/38** (+9 con ADR-0069): NO-SPEND trap, model_consulted
  false, resumen con cifras reales, ruteo y no-match declarados, OFFLINE honesto, 401.

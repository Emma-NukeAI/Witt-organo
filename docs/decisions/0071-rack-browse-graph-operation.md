# ADR-0071 — El browse del grafo (`GET /rack/node/{id}`): la operación que no existía en ninguna puerta

- **Status:** Accepted — 2026-08-22. Cierra el pendiente "`/rack/node/{id}` (browse)" del handoff
  (Rack fase 2) — la operación que faltantes §3 documentó como "aparece en el documento de
  arquitectura, no es tool MCP ni subcomando del CLI" — y cumple la promesa de LOTE-01·A7: los
  ejes de taxonomía POR ENTIDAD derivan del grafo, nunca de /resolve.
- **Relates:** ADR-0020 (el grafo), ADR-0041 (tier weights materializados en Entity + MENTIONS —
  ahora VISIBLES por arista), ADR-0069 (metadata normalizada — el browse la reutiliza vía
  `meta_parsed`), ADR-0043 (marcador in-band — aquí `browse_mode`), ADR-0039 (gate estructural
  `is_approved` — el fallback lo replica), CLAUDE.md §6 (no-hang).
- **Affects:** **NUEVO** `rag_index/query_service/rack_browse.py` · `app.py`
  (`GET /rack/node/{node_id}` + `_TAXONOMY_AXES_DECL.door` apunta a la puerta viva) ·
  `smoke_query_service.py` (+7). Solo lectura; cero mutación DI.

## Context

El Rack podía buscar (/query), resolver (/resolve) y ver estado (/status), pero no RECORRER: dado
un nicho, ¿qué documentos viven en él?; dado un documento, ¿qué entidades menciona y con qué tier?;
dada una entidad, ¿en qué nichos aparece? Esa última es exactamente la pregunta que /resolve declara
estructuralmente no servir (`taxonomy_axes.served: false`) desde LOTE-01·A7.

## Decision

**Un contrato, dos backends, marcador in-band:**

- **graph** (NEO4J_URI): Cypher SIEMPRE parametrizado (jamás interpolación del id), lookups por
  label acotados (`EDGE_LIMIT=100` por dirección, truncamiento DECLARADO), NO-SPEND (cero embeds).
  El `embedding` del nodo jamás se serializa; `Document.meta` viaja como `meta_parsed` (ADR-0069).
- **files-fallback** (dev/offline o grafo caído): derivado de LOS MISMOS archivos fuente que
  alimentan ingest.py (niches/databases/corpus_manifest) con el MISMO gate estructural
  (`is_approved` — un registro no aprobado no existe para el browse, igual que para el grafo).
  Paridad por construcción; un grafo configurado-pero-caído cae aquí con `browse_error` declarado
  (§6 no-hang) — jamás un 500, jamás un fallback disfrazado.

**Resolución del id declarada** (documento → entidad por symbol, luego ENSDARG → nicho → base);
NOT_FOUND = 200 `found: false` (resultado positivo, como /resolve). **Aristas con sus propiedades**:
MENTIONS lleva `verified_tier_weight`/`verification_tier` (ADR-0024/0041 por fin visibles desde un
cliente). **Entidades llevan `derived.data_niches`** — los ejes por entidad, la puerta prometida.

## Verificación

- Offline (gate): 7 checks — nicho con documentos+FEEDS, documento con 44 MENTIONS y tier por
  arista, entidad con ejes derivados, resolución por ENSDARG, chunk→parent+raw_ref, NOT_FOUND
  declarado, 401. `smoke_query_service.py` **45/45**.
- **EN VIVO contra el Neo4j real (solo lectura, 2026-08-22):** `osr1` → entity con
  `data_niches=[{RN11, 1}]` · `CORPUS-2026-0009` → document con `meta_parsed` y SIN embedding ·
  `RN11` → niche con 8 in-edges · MENTIONS con `verified_tier_weight: 1.0` del grafo vivo ·
  not-found honesto en modo graph.

## Alternatives considered

- **Solo grafo (503 sin Neo4j)** — rechazado: dev/offline perdería el Rack entero y el smoke no
  podría ejercitar la lógica; el fallback por archivos-fuente da paridad honesta y declarada.
- **Exponer Cypher arbitrario** — rechazado de plano: superficie de inyección/DoS; el browse es
  una operación tipada por id.
- **Derivar ejes en la UI desde las aristas** — rechazado: tres clientes (webapp/CLI/MCP futuros)
  duplicarían la agregación; el servidor la entrega con su nota de procedencia.

## Consequences

- El Rack de la webapp puede construir la navegación completa: /taxonomia → nicho → documentos →
  entidades → nichos, con tier por arista y drill al crudo vía `raw_ref` (FRONT: nota en el
  addendum del handoff).
- `/resolve` ahora apunta a la puerta VIVA (`taxonomy_axes.door: "/rack/node/{id}"`).
- Gates: 45/45 (+7) · regresión 112/112 · 29/29 · 15/15 · 12/12.

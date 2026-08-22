# ADR-0069 — La metadata del path Neo4j se normaliza a LA MISMA forma del sparse (cierra §5.9)

- **Status:** Accepted — 2026-08-22. Cierra el residual §5.9 del handoff de la webapp (notado en
  ADR-0047 como pendiente): *"la inversión de metadata — los campos accession/data_niche/section/
  raw_ref aparecen SOLO en la ruta sparse (degradada); un panel de detalle enganchado a
  metadata.accession se ve RICO justo cuando el sistema falló y VACÍO cuando está sano. Es la peor
  inversión posible para este producto."*
- **Relates:** ADR-0020 (GraphRAG Neo4j), ADR-0043 (el sobre degraded — este es el complemento:
  el sobre dice el MODO; la metadata ahora dice lo MISMO en ambos modos), faltantes-backend §5.9.
- **Affects:** `analysis/scripts/lib/rag_backend.py` (**NUEVA** `_parse_node_meta` + su uso en
  `Neo4jGraphRetriever.query`) · `smoke_query_service.py` (+3 checks). Cero mutación DI; cero
  cambio de esquema en Neo4j (el fix es de LECTURA).

## Context

`ingest.py` guarda en `Document.meta` el `json.dumps` de la MISMA metadata que `gather_documents`
entrega al índice sparse. Pero `Neo4jGraphRetriever.query` construía `Hit.metadata` como
`{meta: <string sin parsear>, related}` — así que el path SANO entregaba un string opaco mientras
el path DEGRADADO entregaba los campos ricos. Único consumidor del literal `meta`:
`server.py:167`, tolerante (envuelve no-dicts); la webapp aún no engancha paneles a la metadata —
exactamente la ventana para arreglarlo antes de que alguien construya encima de la inversión.

## Decision

`_parse_node_meta(meta_raw, related_names)` (pura, testeable): parsea el string JSON y APLANA sus
campos al dict de metadata — ambas rutas cargan el mismo contrato (`accession`, `data_niche`,
`section`, `raw_ref`, `source_db`, …) — y suma `related` (la expansión 1-hop del grafo) como bonus
del path denso. Un string imparseable se conserva DECLARADO en `meta_unparsed` (jamás se tira en
silencio); un dict pasa directo; `None` deja solo `related`.

## Alternatives considered

- **Arreglarlo en la UI** (parsear `metadata.meta` del lado webapp) — rechazado: dos consumidores
  más (CLI, MCP) heredarían la inversión; la costura correcta es donde nace el Hit.
- **Cambiar el esquema de Neo4j** (propiedades planas en el nodo) — rechazado: mutar el grafo es
  human-gated y re-ingesta completa; el fix de lectura logra lo mismo sin tocar la DI.
- **Conservar la llave `meta` además de aplanar** — rechazado: dos representaciones del mismo dato
  divergen; `meta_unparsed` cubre el único caso donde el original importa (parse fallido).

## Consequences

- El panel de detalle de la webapp puede engancharse a `metadata.accession`/`data_niche`/`raw_ref`
  y verse rico EN EL CAMINO SANO (con `related` extra del grafo); el sparse no cambia.
- Verificación en vivo pendiente del próximo deploy + query real contra Neo4j (el smoke cubre la
  función pura y el cableado offline).
- Gates: `smoke_query_service.py` 38/38 (+3) · regresión 112/112 · 29/29 · 15/15 · 12/12.

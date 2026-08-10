# ADR-0047 — Decisiones de arquitectura del backend webapp (fundador, 2026-08-09) + exposición del bloque 1.4

- **Status:** Accepted — las cinco decisiones dictadas por Emmanuel en sesión el 2026-08-09, cerrando las consultas abiertas del plan de bloques (Método 2: decisiones consultadas, ingeniería normal ejecuta).
- **Relates:** ADR-0040 (front door híbrido CLI-primario), ADR-0043 (sobre degraded), ADR-0044 (identidad de bundle), ADR-0045 (gate del ingest), ADR-0046 (derogación HTML con alcance), ADR-0033 (security hardening, parkeado — la decisión 5 fija su dirección), ADR-0031/0038 (paneles multi-familia + juez cross-provider). Handoff webapp: `witt-ui-lab/05-backend/`.
- **Affects:** el plan de bloques del backend webapp (bloques 2–3 quedan desbloqueados) + `rag_index/mcp_server/server.py`/`cli.py` (bloque 1.4, este commit).

## Las cinco decisiones (cerradas)

1. **Persistencia: PostgreSQL en Dokploy.** El backend lleva registros propios ("registro de absolutamente todo", el reencuadre ERP del 2026-08-04): usuarios, corridas, registro congelado, `ratings[]`, veredictos de auditoría, histórico de cambios a la DI.
2. **Autoridad del gate de auditoría: el backend persiste; la webapp solo lee.** El registro congelado y los veredictos viven en el backend (el stack del repo conserva la autoridad); la webapp es un lector. Descarta la alternativa "webapp fuente de verdad".
3. **Auditoría siempre — 100% de las corridas, incluyendo `DI_SUFFICIENT`.** `DI_SUFFICIENT` y `FALLBACK_FETCHED` pasan a estados intermedios; el terminal de toda corrida es `AUDIT_APPROVED | AUDIT_REJECTED`. El costo del panel (~1–2.50 USD/corrida, ≥3 revisores) se **mide, no se limita** (sin caps). La reforma de la máquina de estados de `answer_pipeline` es cambio backwards-incompatible y se implementa en el bloque 3 **con su propio ADR**.
4. **Composición del panel auditor:** `claude-opus-4-8` + `claude-sonnet` + `claude-haiku` (familia Anthropic, lentes adversariales distintas) + **`gpt-4o`** (OpenAI — la independencia cross-provider real, ADR-0038). **Fable-5 queda EXCLUIDO por ahora**: rechaza tool-calls forzados y probablemente siempre habrá un flag — no se mete por texto libre ni se espera.
5. **Despliegue: `query_service` en la red interna de Dokploy; la webapp será la ÚNICA superficie expuesta.** Fija la dirección del ADR-0033 (cerrar puertos públicos detrás de la red interna) — su ejecución sigue siendo trabajo del bloque 2/5.

## Bloque 1.4 — exposición de lo ya calculado (implementado en este commit)

Lo más barato con más impacto (handoff §3): campos que ya existían del lado del servidor y no llegaban a ningún cliente.

- **`last_error` viaja en el sobre** cuando hay degradación — un diagnóstico ("Neo4j unreachable", "dense-timeout:12s"), no solo el marcador genérico. Fuentes: `HybridRetriever.last_error` (fallo in-band), la causa sintetizada (timeout/exception del path denso), y ambas causas concatenadas en la ruta de error. El CLI lo muestra como `cause:` bajo el banner DEGRADED.
- **`index_version` + `store_version` en el sobre** — comparabilidad de scores y resoluciones a través del tiempo (el registro congelado los consumirá como `store_at_retrieval`).
- **Cada hit `CORPUS-*` conoce su nivel probatorio**: `_hit_dicts` enlaza dataset (`CORPUS-YYYY-NNNN`) y chunk (`…#cNNN` / `metadata.parent` / accession) a su corpus record y adjunta `record: {corpus_record_id, verification_tier, approval_status, approved_by, data_niche}` — sin segunda llamada. Literal explícito `"not-declared"` cuando el campo no existe (nunca un null silencioso). Cache por mtime del manifest: un ingest gated se vuelve visible sin reiniciar (reads are free).
- **`_resolve` devuelve el `VerifiedRecord` COMPLETO** — antes devolvía 6 campos y descartaba 12 (`confidence`, `provenance`, `resolver`, `notes`, …). Incluye `tier_weight` SIEMPRE acompañado de su literal y etiquetado (`tier_weight_kind`): peso de **calibración** (Bayes-purity/ECE, ADR-0024), NO ranking ni fuerza probatoria; `DERIVED=0.7` es placeholder provisional.

## Consequences

- Bloques 2 (query_service HTTP + status NO-SPEND + identidad) y 3 (composite-auditor invocable + modelo de corrida + stream) quedan desbloqueados; el registro congelado se persiste en Postgres del lado backend (decisiones 1+2) — el esquema es entregable del bloque 2/3.
- Residual honesto: `verification_tier` de los records existentes del manifest está sin declarar (se expone como `"not-declared"`, no se inventa). Backfillearlo es una mutación del manifest → propuesta con gate humano, fuera de este alcance.
- Residual honesto: la inversión de metadata (§5.9 del handoff — la ruta sana Neo4j trae `{meta: string}` sin parsear mientras la sparse trae campos ricos) NO se resolvió aquí; el `record` binding la mitiga para datasets/chunks, pero la normalización de metadata entre rutas queda para el bloque 2 (query_service).

## Verification (offline, deterministic)

- `smoke_degraded_envelope.py` → **17/17 PASS** (2026-08-09): checks 13–17 cubren `last_error` como causa, `index_version`/`store_version` en el sobre, record binding dataset/chunk (y NO binding para `db:*`), `_resolve` con los 12 campos + `tier_weight` etiquetado, y NOT_FOUND intacto.
- `smoke_rag.py` live re-corrido al cierre (sobre con llaves adicionales — asserts por `.get`, compatibles).

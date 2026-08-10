# HANDOFF A→B — Adaptar `conciencia-universal` al sobre `{degraded, n_hits, hits}` (ADR-0043)

**Fecha:** 2026-08-09 · **De:** MITAD_A (`witt-organogenesis`, rama `fix/backend-pre-ui`) · **Para:** la sesión que trabaje en `c:/Users/Emmanuel/dev/conciencia-universal` (MITAD_B).
**Prompt pegable:** todo lo que sigue del separador se pega tal cual al iniciar la sesión en B.

---

## Contexto

Trabajas en `conciencia-universal` (MITAD_B). MITAD_A cambió el contrato de lectura de la DATA INAMOVIBLE
(**ADR-0043** en `../witt-organogenesis/docs/decisions/0043-degraded-envelope-end-to-end.md`, commits
`c515823`/`738acfa`, rama `fix/backend-pre-ui` — **aún sin merge a master**). No es cosmético: cierra el
modo de falla en que "degradado y vacío" era indistinguible de "sano y vacío" (el trap del 2026-07-18/19
en el borde del resultado vacío).

**Qué cambió** — la tool MCP `query_data_inamovible` ya NO devuelve una lista; devuelve un SOBRE:

```jsonc
// ANTES (lista cruda; el marcador solo en metadata de cada hit — se perdía con 0 hits)
[ {"doc_id": "...", "score": 0.8, "type": "chunk", "text": "...", "metadata": {"degraded": "sparse"}} ]

// AHORA (ADR-0043): el marcador vive EN el sobre y sobrevive n_hits == 0
{ "degraded": null | "dense-failed:sparse-only" | "sparse-by-config" | "sparse" | "unavailable",
  "n_hits": 3,
  "hits": [ ...los mismos hit-dicts de antes; conservan metadata.degraded por compatibilidad... ] }

// ruta de error (además del sobre trae la llave "error"):
{ "error": "query_unavailable", "degraded": "unavailable", "n_hits": 0, "hits": [], "note": "...", "query": "..." }
```

**Qué NO cambió:** `resolve_identifier` y `fetch_raw` (idénticas), el carácter **read-only** del MCP, y el
CLI `witt-di query --json` (ya devolvía `{degraded, hits}`; ahora suma `n_hits` — aditivo).

## FASE 1 — VERIFICAR (no arregles nada todavía)

1. `grep -rn "query_data_inamovible\|degraded" --include="*.py" --include="*.js" --include="*.md" .` —
   identifica qué consume el resultado y qué documentos describen su forma. Hallazgo previo de A (verifícalo):
   en B no hay código que parsee la lista de hits — los consumidores son **agentes en sesión** guiados por
   `docs/FASE_0_CONNECT_MCP.md`, `docs/A_B_CONTRACT.md`, `docs/GROUNDED_PASS_TODO.md`,
   `.claude/workflows/rank-next-questions.js` (el prompt GOV) y `tools/probe_di.py`.
2. Lee `mcp/data-inamovible.read-only.json`: la registración de referencia usa el **Python global del
   sistema** lanzando `server.py` directo — el patrón **pre-ADR-0039** cuya causa raíz ("intérprete sin
   neo4j" → siempre sparse, a veces en silencio) ya rompió una sesión completa el 2026-07-18/19. A hoy
   lanza el MCP con `uv run --locked` desde el `.mcp.json` versionado de `../witt-organogenesis`.
3. Confirma la forma vigente del sobre leyendo `../witt-organogenesis/rag_index/mcp_server/server.py`
   (`_envelope`, `_query`) — **solo lectura; no toques ese repo.**

## FASE 2 — ARREGLAR

1. **Adaptador tolerante a ambas formas.** A puede estar en `master` (lista) o en `fix/backend-pre-ui`
   (sobre) según el momento; B no controla eso. Toda lectura de `query_data_inamovible` en B pasa por un
   helper (p. ej. en `tools/probe_di.py` o un `tools/di_envelope.py`):
   - dict con `hits` → sobre nuevo: usa `degraded`/`n_hits`/`hits` tal cual (y trata `error` como unavailable);
   - lista → forma legacy: `hits = res`, `degraded` = primer `metadata.degraded` no nulo, `n_hits = len(res)`,
     **y con lista vacía `degraded` es NO-MEDIDO, no "sano"** (esa ambigüedad es exactamente el bug viejo).
2. **Regla epistémica para B (la parte que importa a tus invariantes):** un resultado con `degraded`
   no-nulo y `n_hits == 0` significa *"no se sabe — la recuperación degradó"*, **NUNCA** *"hueco real de la
   DI"*. No lo uses como evidencia de ausencia para EIG/priorización, y estampa `di_grounded=false` (o el
   equivalente de tu contrato) cuando la base fue degradada. Refleja esta regla donde tus docs/GOV prompts
   describan el uso de `query_data_inamovible`.
3. **Actualiza los documentos que describen la forma** (los de FASE 1.1): ejemplos de respuesta, el
   A_B_CONTRACT si cita la forma de retorno, y el GOV prompt del workflow si aplica.
4. **Actualiza la registración de referencia** en `mcp/data-inamovible.read-only.json` al patrón ADR-0039:
   lanzar vía `uv run --locked` con working dir `../witt-organogenesis` (mismo comando que su `.mcp.json`
   versionado), en vez del Python global. Documenta el porqué (incidente 07-18/19) en el `_README`.
5. **Gate determinista en B:** un smoke offline (sin red) que alimente al adaptador las TRES formas
   (sobre sano, sobre degradado con 0 hits, lista legacy) y afirme `degraded`/`n_hits` correctos — en
   particular que *sobre degradado + 0 hits* jamás se lea como "DI sin cobertura". Si el MCP está
   conectado, un probe read-only extra que muestre el sobre en vivo.

## Restricciones (sin cambio)

- **`../witt-organogenesis` es solo lectura para ti. No lo toques.** Cualquier gap del lado de A se
  reporta vía `outbox/` (patrón REQUEST_A_*), no se edita allá.
- B **jamás** escribe la DATA INAMOVIBLE (aislamiento estructural; el re-ingreso es por el gate humano de A).
- Autonomía A1: todo es propuesta al gate humano. No mintees identificadores; `resolve_identifier` sigue
  siendo la fuente determinista.

## Criterios de aceptación

- El smoke de las tres formas pasa offline (exit 0).
- Ningún doc/prompt de B describe la forma vieja como vigente; la regla "degradado+vacío ≠ hueco de DI"
  queda escrita donde se decide grounding/EIG.
- La registración de referencia ya no usa el Python global.
- Commits chicos en B; nada tocado en `../witt-organogenesis`.

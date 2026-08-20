# ADR-0059 — ZFIN (fenotipos nativos de pez cebra) como fuente de Ruta B: Tool Universe deja de ser un recado

- **Status:** Accepted — 2026-08-19. Tapón 1·A del plan de `witt-ui-lab/01-mapa/harness-en-la-webapp.md` (decisión de Emmanuel el mismo día: empezar por la fuente nativa, sin dependencias nuevas).
- **Relates:** ADR-0022 (Ruta B + gate de auditoría + re-ingesta con gate humano), ADR-0026 (el *directive* explícito de Tool Universe), ADR-0057 (la Ruta B que buscaba en español y devolvía cero; la query enviada tiene que quedar registrada), ADR-0058 (la declinación honesta aprueba), ADR-0039 (jamás contaminar el `.venv` del MCP), CLAUDE.md §6 (regla no-hang + disciplina de caché) y §7 (identificadores externos verificados).
- **Affects:** `analysis/scripts/lib/answer_pipeline.py`, `rag_index/query_service/runs.py`, `rag_index/query_service/smoke_run_pipeline.py`, `witt-webapp/src/modulos/M3Corridas/Traza.tsx`. **No** toca el contrato del registro congelado (`render_contract_version` sigue en 1.2: `path_b` vive en el bundle y en el evento, no en el registro).

## Contexto

Hasta hoy, en toda corrida de la webapp, `_search_tooluniverse()` devolvía `[]` y lo único que quedaba
de Tool Universe era `tool_universe_directive()`: un objeto que **nombra** la llamada que un agente
debería correr. Peor, `_compact_evidence()` lo retira antes de armar la vista que ven el sintetizador y
el panel — es un recado para un agente que en la ruta HTTP no existe. La Ruta B de producción era
Europe PMC y nada más.

Mientras tanto, en `.tooluniverse/tools/` viven **dos tools propias del proyecto**, versionadas en git y
escritas — por decisión explícita de su autor — en stdlib puro *"so the logic is importable + testable
without the tooluniverse package installed"*. Una de ellas, `zfin_zebrafish.py`, resuelve un símbolo de
gen a su curie ZFIN y devuelve **statements de fenotipo mutante/knockdown observados** con sus PMIDs,
taxon 7955, sin API key. Existe precisamente porque las tools de señalización de Tool Universe son
human-céntricas y no había fuente nativa de pez cebra.

Nunca se cableó. La evidencia de que eso costaba respuestas es la corrida real
`a361f566d67f470eb195c78b2b3cb7b6`: su `direct_answer` concluyó que ninguna evidencia del bundle liga
`wt1a` al desarrollo del pronefros. Medido hoy en vivo: **ZFIN tiene 16 statements de pronefros para
`wt1a`**, entre ellos *"pronephric glomerulus aplastic, abnormal"* (PMID:17651719). La respuesta fue
honesta respecto de su bundle; el bundle estaba incompleto por una fuente que ya existía y no corría.

## Decisión

1. **ZFIN es una fuente de Ruta B de primera clase.** `PATH_B_SOURCES = ("europepmc", "zfin",
   "tooluniverse")`. Las tools del workspace se cargan **por path** (`_workspace_tool`) — el directorio
   es dot-prefixed y no es un paquete importable —, y el `COPY . /app` del contenedor ya las trae porque
   están versionadas.
2. **El hook del SDK sigue siendo un hook.** `_search_tooluniverse()` continúa devolviendo `[]` y el
   directive se mantiene: cubre las tools del **paquete**, que sí necesitan el SDK (tapón 1·B). Esta
   decisión no lo declara resuelto.
3. **Filtro anatómico determinista y declarado.** `zfin_anatomy_filter()` mapea términos ES **y** EN al
   mismo keyword de ZFIN (`pronephr`, `glomer`, `duct`, `tubul`, `podocyte`, `kidney`) desde una tabla
   fija. Nunca decide el modelo. Sin término en la pregunta → sin filtro, que es una búsqueda **más
   ancha**, no una fallida; y el registro dice cuál de las dos ocurrió (`anatomy_filter_source`).
4. **Un ledger por símbolo, con cuatro destinos distinguibles.** `path_b.zfin_searched` lleva una fila
   por cada símbolo intentado: `success` · `no-match` · `error` · `skipped-budget` · `skipped-cap` ·
   `tool-unavailable`. Es la corrección directa del hallazgo LOTE-03·1: **"busqué y no hay" jamás puede
   verse igual que "la búsqueda falló" ni que "ese símbolo nunca se intentó".**
5. **Acotado por construcción (§6 no-hang).** Presupuesto de reloj (`WITT_ZFIN_BUDGET_S`, default 45s),
   tope de símbolos (`WITT_ZFIN_MAX_ENTITIES`, 6) y tope de statements por gen
   (`WITT_ZFIN_MAX_STATEMENTS`, 12). Todo recorte se **declara** (`truncated`, `n_matched` vs
   `n_returned`, `skipped-*`): un corte silencioso se leería como "eso es todo lo que ZFIN sabe".
6. **`evidence_id` en todo item de Ruta B.** Para ZFIN es el curie resuelto en vivo (jamás acuñado);
   para Europe PMC, el identificador de siempre. `_evidence_ids` lo prefiere: antes, dos items sin PMID
   colapsaban ambos en la cadena literal `"paper"` y el veredicto del panel podía aterrizar en el item
   equivocado.
7. **Un solo constructor del bloque.** `path_b_bundle()` y `path_b_event_payload()` sustituyen los dos
   diccionarios que `retrieve()` y `runs.execute_run()` mantenían por separado — contadores duplicados
   derivan, y un contador que deriva es cómo una búsqueda rota acaba pareciendo un mundo vacío.
8. **`n_results_by_source` es por fuente, y `europepmc` siempre aparece** (un `0` explícito no significa
   lo mismo que una fuente ausente del diccionario).
9. **Nada se relaja del gate.** Todo lo que entra por ZFIN pasa por el **mismo** panel composite-auditor
   antes de poder mostrarse, y la evidencia externa aprobada re-entra a la DATA INAMOVIBLE **sólo** por
   el gate humano de ingesta. Los PMIDs que devuelve ZFIN vienen de la API autoritativa con procedencia
   (`identifier_provenance: "alliance-genome-api-live"`), lo que **no** los declara verificados para
   cita: `verify_output` sigue siendo el que gatea lo que el sintetizador decida citar (§7).

## Consequences

- Una pregunta de pérdida de función en pronefros ahora se responde con **evidencia nativa de pez
  cebra**, un tier más fuerte que literatura genérica, y con sus PMIDs de respaldo.
- El sintetizador y el panel **ven el ledger** (`_compact_evidence` no lo retira): el modelo puede decir
  "ZFIN se consultó para `pax2a` y no tiene fenotipos de pronefros" en vez de callar la fuente.
- La traza viva y el replay muestran el desglose por fuente y el tally de ZFIN — mismo resumen, un solo
  log.
- Costo: **cero** modelo, cero API key. Dos GET públicos por símbolo, ~1.3 s por símbolo medido.
- Residual declarado: los statements de ZFIN traen HTML de origen (`<i>slc4a2a</i>`). Se conservan
  **verbatim** — fidelidad a la fuente — y quien los renderice debe escaparlos, no el pipeline
  reescribirlos.
- Residual declarado: el artefacto que se guarda en `mcp_cache/zfin_<simbolo>_<fecha>.json` es el sobre
  **determinista** de la tool, no el cuerpo HTTP intacto; por eso **no** lleva el prefijo `raw_` (§6 no
  deja que un artefacto casi-crudo tome prestada la palabra `raw`).

## Verification

**Offline, determinista:** `smoke_run_pipeline.py` → **54/54 PASS** (+10: los cuatro destinos del ledger
· item sólo con match y `evidence_id` = curie · truncado declarado · presupuesto agotado →
`skipped-budget` · tool ausente → `tool-unavailable` sin tronar la corrida · filtro ES/EN al mismo
término · `n_results_by_source` con `europepmc:0` explícito · `path_b_bundle` completo · el payload del
evento con el tally · `_evidence_ids` sin colapsar en `"paper"`). `smoke_query_service.py` → **29/29
PASS**. La red no se toca en ningún gate: `path_b` es la única costura y los gates la stubbean.

**Medido en vivo** (2026-08-19, HTTP público, cero gasto de modelo):

| símbolo | curie | matched / total | primer statement |
|---|---|---|---|
| `pax2a` | ZFIN:ZDB-GENE-990415-8 | 12 / 189 | pronephric duct absent, abnormal (PMID:9007239) |
| `wt1a` | ZFIN:ZDB-GENE-980526-558 | 16 / 53 | presumptive pronephric mesoderm malformed (PMID:25014653) |
| `osr1` | ZFIN:ZDB-GENE-070321-1 | 35 / 67 | pronephric glomerulus absence of anatomical entity (PMID:36359386) |

Bloque integrado sobre la pregunta real de `a361f566…` (`entities=['wt1a']`): 3.9 s,
`n_results_by_source = {europepmc: 2, zfin: 1}`, `evidence_ids` distintos
(`PMID:42153456`, `PMID:41194582`, `ZFIN:ZDB-GENE-980526-558`).

**Webapp:** `npm run gate` → **111/111 PASS** (+1: el desglose por fuente y el tally visibles en la
traza).

### Corrida real end-to-end (2026-08-20) — el A/B contra la corrida histórica

`ea96d70e120143df9fdfd339a3aeb208`, **misma pregunta** que `a361f566…`: Neo4j real, Opus 4.8 real,
panel real de 4 jueces, ZFIN real. USD **0.1833** (proyección desde 24,560 in / 4,837 out medidos).

| | `a361f566…` (2026-08-10, contrato 1.0, sin ZFIN) | `ea96d70e…` (2026-08-20, contrato 1.2, con ZFIN) |
|---|---|---|
| Respuesta | *"no wt1a requirement for pronephros development can be asserted"* | *"**Yes.** wt1a is required… concentrado en el compartimento glomérulo/podocito"* |
| `absence_kind` | (no existía en 1.0) | pass1 `no-evidence-retrieved` → pass2 `not-applicable` |
| Confianza | 0.15, atrapada en el texto | 0.15 → **0.86**, delta **+0.71** |
| Veredicto | **REVISE** (gpt-4o/reproducibility vetó) | **APPROVE_MINOR** — 2 APPROVE + 2 APPROVE_MINOR, **cero REVISE**; gpt-4o APPROVE 0.95 |
| Terminal | `AUDIT_REJECTED` | **`AUDIT_APPROVED`** |
| Citas | prosa, sin tipo | 5 tipadas: 1 `store-resolution` + 4 PMIDs de ZFIN |

Tres cosas que la corrida confirma más allá del tapón:

1. **El decisor de confianza es el que salva la corrida.** `fb_meta.structural_sufficient: true` — el
   decisor estructural volvió a decir "suficiente" (el defecto fooled-by-any-chunk-present que el repo
   documenta), y fue el gate de confianza (0.15 < 0.5) el que disparó la Ruta B. Confirmación viva de la
   tesis de ADR-0051.
2. **La respuesta quedó MÁS FINA que un "sí".** El modelo notó que los readouts de ducto y túbulo salen
   `NORMAL` en la perturbación de wt1a (PMID:21871448) y acotó el claim a podocito/glomérulo en vez de
   afirmar un requerimiento uniforme. Y sus `gap_flags` declaran que los hits de Path A eran off-topic y
   que la respuesta descansa en el set de ZFIN — exactamente la conducta que el contrato §5 pide.
3. **El bug del escalar atrapado sigue vivo: 3 de 3 corridas reales.** `confidence.source` =
   `recovered-from-malformed-tool-call` en **ambas** pasadas. La recuperación de ADR-0057 no es un parche
   histórico: es infraestructura que carga peso en cada corrida. Vale abrir la pregunta de por qué Opus
   sigue emitiendo el escalar dentro de `direct_answer`.

Cierre explícito ejercido: `frozen_at` 2026-08-20T19:20:26Z, `closed_by: emmanuel`,
`epistemic_summary = {semantic, APPROVE_MINOR, value, 4}`.

## Pendiente que esta decisión NO cierra

Tapón 1·B (SDK de Tool Universe en el contenedor del query service — **nunca** en el `.venv` del MCP) ·
tapón 2 (`framework_applied` / `agents_invoked` en el registro) · tapón 3 (planner de M3) · tapón 4
(M5 + calibración continua) · tapón 5 (evals como gate periódico).

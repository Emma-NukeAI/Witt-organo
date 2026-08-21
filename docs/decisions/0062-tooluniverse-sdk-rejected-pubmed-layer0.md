# ADR-0062 — Tapón 1·B: el SDK de Tool Universe en el contenedor se MIDE y se RECHAZA; PubMed entra por Layer 0

- **Status:** Accepted — 2026-08-20. Cierra el tapón 1·B de `witt-ui-lab/01-mapa/harness-en-la-webapp.md` — **cambiando el mecanismo con evidencia**: el objetivo (la amplitud de literatura de Tool Universe viva en la Ruta B) se entrega; el mecanismo propuesto (pip install del SDK en el contenedor del query service) se rechaza con mediciones.
- **Relates:** ADR-0039 (la lección fundacional: un intérprete contaminado degrada en silencio — el incidente del 2026-07-18/19), ADR-0059 (Layer 0: las workspace tools stdlib como fuentes de primera clase), ADR-0026 (el directive de Tool Universe), CLAUDE.md §6 (no-hang + la regla nueva de Layer 0: una workspace tool DEBE ser stdlib-pura).
- **Affects:** `.tooluniverse/tools/pubmed_literature.py` (**nuevo**), `analysis/scripts/lib/answer_pipeline.py`, el gate, `CLAUDE.md` §6; en la webapp `Traza.tsx` + fixtures. **No** toca el contrato del registro (`path_b` vive en bundle y evento).

## Las mediciones que deciden

Medido el 2026-08-20 con `pip install --dry-run --report` sobre el intérprete real del servicio
(Python 3.12):

1. **La versión pineada del proyecto no instala.** `.mcp.json` pinea `tooluniverse@1.2.6` para el MCP
   de los agentes. `pip install tooluniverse==1.2.6` **falla en resolución**: su dependencia
   `fitz>=0.0.1.dev2` no tiene ninguna distribución instalable en 3.12 (las viejas requieren <3.11).
   El contenedor ni construiría.
2. **La última versión (1.4.1) resuelve a 173 paquetes.** Entre ellos: `playwright` (que además exige
   binarios de navegador post-install), `faiss-cpu`, `onnxruntime`, `scipy`, `pandas`, `epam-indigo`,
   `google-genai`, `azure-ai-documentintelligence`, `speechrecognition`, `youtube-transcript-api`, y
   TRES frameworks web (flask + fastapi + fastmcp) — dentro del contenedor que corre `--workers 1`,
   comparte `numpy`/`openai` con el stack pineado de sklearn, y cuya lección fundacional (ADR-0039) es
   exactamente que una dependencia mal puesta degradó la búsqueda en silencio durante dos días.
3. **Divergencia silenciosa de versiones.** Los agentes usan 1.2.6 vía uvx; el contenedor correría
   1.4.1 — dos Tool Universes con catálogos distintos comportándose distinto sin que nada lo declare.

Con esos tres datos, instalar el SDK ahí no es una opción de ingeniería: es el patrón del incidente
2026-07-18/19 con más superficie.

## Decisión

1. **El SDK NO se instala en el contenedor del query service.** Ni pineado (no resuelve) ni el último
   (173 paquetes). El hook `_search_tooluniverse()` sigue devolviendo `[]` con la razón documentada.
2. **La amplitud de literatura entra por Layer 0** — el patrón que este proyecto inventó (las dos
   workspace tools existentes) y que ADR-0059 formalizó: `.tooluniverse/tools/pubmed_literature.py`,
   stdlib puro, NCBI E-utilities (esearch + esummary), sin API key obligatoria, honrando el
   `NCBI_API_KEY` opcional que `.mcp.json` ya contempla. Es la primera llamada que nombra el directive
   (`PubMed_search_articles`), corriendo de verdad.
3. **Dedup por PMID, declarado.** Europe PMC **indexa** PubMed: la cobertura se solapa casi por
   completo. Lo que PubMed agrega es **diversidad de ranking** (su best-match sube papers distintos al
   top-k) e independencia de fuente. Sin dedup, el mismo paper entra dos veces y el sintetizador lo
   cuenta doble; el dedup se declara en `path_b.pubmed_searched.duplicates_of_europepmc`, nunca es
   silencioso.
4. **El fetch de papers se envuelve (§6 no-hang)** — defecto pre-existente destapado por la
   verificación en vivo de esta decisión: un read-timeout bajando UN paper mataba `path_b` completo.
   Ahora degrada ese item (`found: false` + `fetch_error` declarado) y la corrida sigue. Aplica a las
   dos ramas de literatura.
5. **La ruta de escalación queda nombrada, no construida:** si el planner (ADR-0061) algún día rutea a
   muchas tools del paquete, la forma correcta es un **sidecar** — contenedor propio con su imagen y
   sus dependencias, hablando por la red interna de Dokploy — nunca `pip install` en el intérprete del
   query service. Y la tool agéntica (`tooluniverse-literature-deep-research`) queda explícitamente
   FUERA de `path_b`: un agente LLM generando evidencia dentro del retrieve sería evidencia sin
   auditar; entraría sólo vía ruteo del planner con su propia auditoría.

## Consequences

- La Ruta B queda con **cuatro fuentes vivas**: `europepmc`, `pubmed`, `zfin` y el hook del paquete
  (declarado). `n_results_by_source` lista SIEMPRE ambas fuentes de literatura (0 explícito ≠ ausente).
- Cero dependencias nuevas en producción. El contenedor no cambia.
- La imagen del servicio NO diverge del MCP de los agentes: cada uno usa su mecanismo (uvx per-session
  vs Layer 0 in-pipeline) sin compartir intérprete — exactamente la frontera que ADR-0039 exige.
- Costo por corrida: +0 de modelo (E-utilities es gratis); ~2–4 s de red por los fetches de PubMed.

## Verification

**Offline:** `smoke_run_pipeline.py` → **91/91 PASS** (+5: dedup por PMID declarado · búsqueda fallida
= `error`, nunca "no hay resultados" · tool ausente = `tool-unavailable` sin tumbar · el resumen de
pubmed en el evento · **timeout de fetch degrada el item, no mata path_b**). `smoke_query_service.py`
→ **29/29**. Webapp → **129/129** (el resumen de PubMed con su dedup visible en la traza; fixtures
regenerados).

**Vivo, cero gasto de modelo** (2026-08-20, pregunta real de `a361f566…`):

```
n_results_by_source: {europepmc: 2, pubmed: 2, zfin: 1}   · sin duplicados
pubmed_searched: {status: success, n_found_total: 55, n_new: 2, duplicates_of_europepmc: []}
```

Y el argumento de valor quedó demostrado en vivo, no teorizado: para esa pregunta el top-2 de Europe
PMC fue **off-topic** (identidad epicárdica; toxicología multi-órgano) mientras el ranking de PubMed
trajo *"Zebrafish Pronephros Development"* (PMID:28409341) y un paper de wt1a (PMID:35087838). En la
prueba standalone con query `wt1a zebrafish pronephros`, PubMed puso en el top-3 el paper del elemento
de respuesta a ácido retinoico que controla wt1a (PMID:19666820) — la conexión RA→wt1a que las
corridas previas no surfaceaban.

## Pendiente que esta decisión NO cierra

El sidecar de Tool Universe (si el ruteo del planner lo llega a justificar) · la tool agéntica de
deep-research (entra por planner + auditoría propia, nunca por path_b) · tapones 4 (M5+calibración) y
5 (evals) · el escalar atrapado (6 de 6 corridas reales).

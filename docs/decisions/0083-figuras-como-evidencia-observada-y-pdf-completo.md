# ADR-0083 — Figuras de papers como evidencia OBSERVADA (source-pointer + sha256 + licencia verificada por código), su lectura como JUICIO en dos lentes del panel, y el PDF de servidor COMPLETO con gate de cobertura (contrato 1.12)

- **Status:** Proposed — 2026-09-15 (llevado al repo por F7 el 2026-09-16 desde el borrador del sintetizador; pasa a Accepted
  cuando Emmanuel apruebe E1–E5; conteos MEDIDOS por F8 el 2026-09-16 — los 41 `smoke_*.py` exit 0 con la máscara; ver la tabla NO-SPEND y el bullet «Integración F8»). Origen: plan v3 del brief *Consejo de agentes* (§7 "Imágenes
  como evidencia" — R5: figuras como source-pointer con sha256 = medición observada de fuente; §18 paridad: "el PDF omite 12
  bloques del registro… ninguna llave del registro sin sección en el PDF"; fila ADR-0083 de la tabla de ADRs) aprobado por
  Emmanuel el 2026-09-14. **Apila sobre ADR-0082 (contrato 1.11)** — *(F7: alineado a ca9a03d)* ADR-0082 está COMMITEADO en `feat/adr-0082-consejo` @
  `ca9a03d` (tag `contract-1.11-frozen`); este ADR obra en el worktree `witt-organogenesis-0083` (rama `feat/adr-0083-figuras-pdf`,
  apilada sobre él) y asume las formas 1.11 tal como quedaron en el árbol (`docs/decisions/0082-consejo-de-criterio-ejecutable.md` (J)) —
  `frozen.council`, `deterministic_checks.council` + `attestation_identifier_leak(+_state,_rule)`, `citations[].pertinent`
  objeto, `token_usage.cache`, `search_ledger.plan.directives`, filas `council` en `agents_invoked`, `_run_view.plan_council_state` —
  y la firma D.1 `composite_auditor._anthropic_tool_call(model, system, user_text, tool=None, timeout=120, retries=1,
  max_tokens=1200, effort=None, return_meta=False, tools=None)` (ca9a03d :583-584 — verificada por F7) y la sección "CONSEJO DE
  CRITERIO" de `record_pdf.py` (ca9a03d :277-338: `_NOT_INSTRUMENTED_1_11` :277, `_section_consejo` :308; el archivo tiene 679 líneas y
  `build_pdf(record, compress=True)` :477 — verificado por F7). Obra sobre
  `feat/adr-0081-modelos-g2` @ `9d90c01` (tag `contract-1.10-frozen`) con paridad en `witt-webapp` @ `feat/adr-0081-paridad`
  `b791db5` (OTRO workflow; `tools/parity_debt.json` declara 23 líneas `[pdf]` hacia este ADR). Síntesis de tres diseños
  (doctrina-y-fidelidad · webapp-primero · operación-costo-riesgo) y dos juicios: parte del ganador (doctrina-y-fidelidad, 33/40 y
  31/40) e injerta lo que los dos jueces pidieron; donde los jueces o los diseños divergen, la decisión y su porqué van marcados
  *(síntesis)*. Estilo de cita: **ruta:función** con los números de línea del árbol @ `9d90c01`, verificados hoy (el nombre de la
  función es lo estable). *(F7: alineado a ca9a03d — los números de línea de `runs.py`/`app.py`/`verify_output.py`/`models.py`/
  `composite_auditor.py` citados en el cuerpo siguen siendo los de 9d90c01 salvo donde se marca «@ ca9a03d»; el bullet «Anclas @
  ca9a03d» de esta cabecera trae los verificados por F7 el 2026-09-16.)*
- **Decisiones YA tomadas por Emmanuel (no se relitigan aquí):** figura = source-pointer con sha256 (MEDICIÓN observada de
  fuente) · verificación DETERMINISTA de bytes/fig_id/licencia en `verify_output` · el contenido de la imagen lo leen SOLO dos
  lentes del panel (juicio etiquetado); el sintetizador recibe caption y metadatos, NUNCA bytes · gate de licencia: embebible
  sólo CC BY / CC0 / CC BY-SA (default delegado), NC y desconocida NO se embeben (se enlazan y declaran), ZFIN jamás bytes ·
  bytes FUERA del registro congelado (ADR-0074): viven en `mcp_cache` (raw cacheado, ADR-0062) y se sirven por
  `GET /runs/{id}/figures/{sha256}` con 403 si no embebible · imágenes atestiguadas subidas por humanos = ADR-0086 (MinIO
  privado), NO aquí · PDF completo: cada llave del registro con sección espejo y TRES estados (ausente = NO INSTRUMENTADO
  (contrato < X) ≠ null declarado ≠ valor), incluidas las 23 líneas de deuda `[pdf]`, `models`, `audit.quorum`,
  `by_stage.panel.by_model`, filas por fuente del `search_ledger`, `citations_schema` con sus 4+1 estados y `council` (1.11) ·
  costo no es impedimento pero toda cifra con clase · smokes 100 % offline (bytes desde fixtures/golden; cero red; jueces con
  visión fakeados) · un proceso FastAPI `--workers 1`; SQLite dev / Postgres prod · contrato ADITIVO 1.12 · kill-switches con
  default declarado que restauran el comportamiento previo · cero mutación de la DATA INAMOVIBLE · §6 no-hang (una figura que
  no baja deja fila declarada y la corrida sigue).
- **Relates:** ADR-0043 (tres estados) · ADR-0044 (identidad rota → ni hoja ni PDF) · ADR-0049 (auditoría en el 100 %) ·
  ADR-0051 (tokens medidos, USD proyectados) · ADR-0058 (`APPROVE_DECLINE`) · ADR-0062 (raw cacheado con procedencia) · ADR-0067
  (revisión acotada — aquí el lazo panel→revisión se cierra para las lecturas de imagen) · ADR-0072 (held-out: el prompt del
  sintetizador cambia → LG9) · ADR-0073 (PDF de servidor = canal único de salida) · ADR-0074 (nada binario en el blob; nada se
  migra) · ADR-0077 (sha256 verificado al leer) · ADR-0078 (`fetch_paper` cachea el XML; lectores tolerantes; `net_throttle`) ·
  ADR-0079 (`thread_parent_matches_run_rule` — hoy el PDF imprime prosa fija en su lugar) · ADR-0080 (escalera de soporte;
  `citations_schema` 5 literales; kill-switches byte a byte; §6 `_fetch_or_declare`) · ADR-0081 (tabla de modelos = única verdad
  de literales; `panel_signature`; `by_stage.panel.by_model`; `gpt-4o` bridge por chat.completions) · ADR-0082 (consejo:
  `evidence_kind 'figure'` → `unsatisfiable-by-harness (… ADR-0083)`, costura declarada en (O)) · ADR-0086 (imágenes
  atestiguadas) · ADR-0087 (calibración: `audit.vision` estratifica la serie).
- **Affects:** `analysis/scripts/lib/figures.py` (NUEVO) · `fetch_paper.py` (`_normalize_hit += license`, una línea) ·
  `verify_output.py` · `composite_auditor.py` · `models.py` (columna `vision_tier` + `ENV_TABLE`) · `rag_index/query_service/
  runs.py` (contrato **1.12**; etapa `stage.figures`) · `app.py` (2 rutas NUEVAS; `expose_headers`; `/usage += figures`) ·
  `record_pdf.py` (RE-ESTRUCTURA por tabla `SECCIONES`) · `db.py` (SIN cambio de esquema: sólo tipos de evento nuevos) ·
  `docker-compose.query.yml` · `README.md` · `CLAUDE.md` §7 (viñeta «figure-only») · `docs/decisions/README.md` · fixtures
  (2 XML golden copiados + zip CC BY reducido + zip sintético) · smokes (4 NUEVOS + 6 tocados) · witt-webapp (tipar y pintar;
  gate (D) PDF → 0 huecos; ver *Consequences*). **Cero mutación de la DATA INAMOVIBLE, del registro congelado existente, de
  `mcp_cache` desde los gates; cero gasto de modelo en la obra.** `answer_pipeline.py` NO se toca *(síntesis: la etapa vive en
  `runs`, ver (C))*; `precedent.py` NO se toca (verificado: `validate_disjoint` :249-256 sólo exige `n` entero sin `l`).
- **Estado de E1–E5 en esta obra (F7, 2026-09-16 — DEFAULTS aplicados, nada decidido por el código):** E1 `WITT_FIGURES=1` y
  `WITT_FIGURES_VISION=1` (encendido desde el merge; el kill-switch se mide byte a byte) · E2 `WITT_FIGURES_PANEL_LICENSES` incluye
  NC/ND (las dos lentes VEN esos bytes para juzgar; embeber sigue prohibido y el 403 lo acota; `unknown` nunca) · E3
  `WITT_FIGURES_PROSE_LICENSE=1` (prosa «Creative Commons Attribution» sin URL = `cc-by` con `source 'license-p-prose'` visible en
  Hoja/PDF) · E4 sin volumen, DECLARADO (`cache.dir_state`, 404 `bytes-not-in-cache`, `WITT_FIGURES_REFETCH_ON_GET=0`) · E5 el texto
  literal de la aprobación presupuestal lleva el placeholder `<pendiente E5>` hasta que Emmanuel lo confirme o acote (patrón E6 de
  ADR-0082: el placeholder es visible, jamás un texto inventado). Ninguna de las cinco se relitiga aquí.
- **Estado del árbol al escribir (F7, 2026-09-16):** F1 YA aterrizó en el worktree (untracked, F8 commitea): `analysis/scripts/lib/
  figures.py` (1 5xx líneas; `ENV_SPECS` de 21 filas = las 20 nuevas + `WITT_MCP_CACHE_DIR`, `VOCABULARY` de 17 llaves, `CACHE_DIR_SOURCES`
  gana `'injected'` para la ruta que pasa un llamador), `fetch_paper._normalize_hit += license` (fetch_paper.py:178),
  `rag_index/query_service/fixtures/figures/` (`MANIFEST.json` contrato 1.12: 2 XML reales 127 065 + 214 974 B, zip CC BY REDUCIDO
  1 270 115 B con los 9 sha medidos, zip NC SINTÉTICO 1 095 B con `gr9.gif` thumb sin jpg), `smoke_figures.py`, `smoke_fetch_paper.py`
  (+3). F2–F6 corren en paralelo y al cierre de F7 ya asoman en el worktree SIN commit (`git status`): `models.py` con las 20 filas
  `adr '0083'` de `ENV_TABLE` + `VISION_TIERS` (F3 parcial: `composite_auditor.py` aún SIN `user_content` — 0 ocurrencias),
  `verify_output.py` (F2), `runs.py` (F4), `app.py` + `smoke_figures_http.py` (F5), `smoke_gate_citations.py` / `smoke_usage_http.py` /
  `smoke_runs_list_http.py` tocados; F7 NO los lee como verdad de contrato (F8 cose y mide). La verdad de las 21 env es
  `figures.ENV_SPECS`/`env_config()` y F7 la midió BIDIRECCIONALMENTE el 2026-09-16: 21/21 con placeholder en el compose (los 20 nuevos
  tras el bloque 0082 + `WITT_MCP_CACHE_DIR` ya existente; defaults byte-iguales a `ENV_SPECS`), 21/21 con fila en la tabla del README
  (defaults iguales), las 20 filas `adr '0083'` de `models.ENV_TABLE` ⊆ `ENV_SPECS` ∩ compose ∩ README, y ningún `WITT_FIGURES*`
  fuera de `ENV_SPECS` en compose/README/ADR/CLAUDE.md. Como los tres callers de `composite_auditor` aún NO aceptan `user_content`, el
  instrumento en vivo lo detecta por firma y lo DECLARA (`caller-without-user_content`) en vez de llamar sin imágenes.
- **Anclas @ ca9a03d (verificadas por F7 el 2026-09-16; complementan las de 9d90c01 citadas en el cuerpo — el nombre de la función es lo
  estable):** `runs.py` (4 463 líneas): `RENDER_CONTRACT_VERSION = "1.11"` :50 · `SYNTH_TOOL` :222 (enum de `kind` :262) · `_agents_invoked`
  :845 · `_panel_findings` :956 · `_PROMPT_PAPER_KEYS` :1484 · `_prompt_path_b` :1491 · `_compact_evidence` :1521 · `_evidence_ids` :1541 ·
  `_normalize_citations` :1788 · `TOKEN_STAGES` :1854 · `_usage_by_stage` :1959 · `_positive_claim_check` :2320 · `_gate` :2359 ·
  `_support_states` :2515 · `snapshot_extra` :2593 · `execute_run` :3054 (`panel_caller` envoltorio :3108) · evento `stage.path_b` :3544 ·
  `_synth(…, 'pass2')` :3661 · literal `frozen = {` :3869 · `epistemic_summary` :4098. `app.py` (2 682): `CORSMiddleware` :121-123 (sin
  `expose_headers` — confirmado) · `_user_of` :128 · `artifact_report` :432 · `HEARTBEAT_STALE_S` :452 · `get_record_pdf` :1390-1391
  (`record_pdf_mod.build_pdf(rec)` :1406) · `/runs/{run_id}/events` :1414 · `_ratings_view` :1900 · `/usage` :2267. `verify_output.py`:
  `admissible` :219 · `SUPPORT_LADDER` :266 · `POSITIVE_CLAIM_RULE` :306 · `positive_claim_requires_citations` :363 · `_citation_keys` :391 ·
  `_bundle_evidence_index` :410 · `support_state_for(…, council_pertinence=…, council_state=…)` :493. `composite_auditor.py`: `VERDICT_TOOL`
  :363 · `_LENS_CHARGES` :422 · `_numeric_usage` :543 · `_anthropic_tool_call(…, tools=None)` :583-584 · `_responses_kwargs` :731 ·
  `_responses_usage` :767 · `_openai_responses_call` :797 · `_openai_chat_call` :918 · `_default_caller` :991 · `audit(…, directives=None)`
  :1051. `models.py`: `gpt-4o` bridge :98-99 · `gpt-6-astra` candidate :102-103 · `LENSES` :155 · `ENV_TABLE` :256 · `ENV_ADR_0082` :312 ·
  `SNAPSHOT_FIELDS` :323. `council.py`: `'unsatisfiable-by-harness (evidence_kind figure — ADR-0083)'` :1437-1438 (también :110, :1434,
  :1589). `record_pdf.py` (679): `_NOT_INSTRUMENTED` :81 · `_NOT_INSTRUMENTED_1_11` :277 · `_section_consejo` :308 · `build_pdf` :477.
  `fetch_paper.py`: `ROOT` :61 · `CACHE` :66 · `_ua` :122 · `_throttle` :127 · `_normalize_hit` :171-179 (`license` :178, F1) · `_xml_to_text`
  :248 · `fetch_external` :345 · `_rel` :407.
- **Integración F8 (2026-09-16, sin git — el orquestador commitea):** las siete rebanadas aterrizaron en el worktree y F8 cosió las
  costuras (O) y las preguntas cruzadas: (i) `runs._figure_checks` pasa el DICT del sintetizador a `verify_output.figure_predicates`
  (llega `absence_kind`: una declinación que cita figuras ya no queda «positiva»); (ii) `runs._token_usage` escribe `figures {state,
  n_figures, n_verified, n_cited, bytes_downloaded, class}` — espejo de `frozen.figures` — sólo con `WITT_FIGURES=1`, y como `usage_json`
  ES ese dict, `GET /usage.figures` (F5) cuenta corridas reales; (iii) caché PEREZOSA: `figures.cache_dir_state(path, create=True)` —
  `attach` mide sin crear (`create=False`) y crea el dir SOLO con papers seleccionados; el `stage.figures.plan` lo mide con
  `create=(n_sel > 0)` (un gate sin `WITT_MCP_CACHE_DIR` dejaba `<repo>/mcp_cache/figures/` vacío: retirado y causa cerrada); (iv) los
  cuatro `stage.figures.*` se escriben con `db.add_event(run_id, <literal>, …)` (`runs.FIGURES_EVENT_TYPES`): la superficie (C) del gate
  de paridad lee esa forma — con el emisor indirecto de F4 los cuatro eran INVISIBLES para la webapp; (v) `app.get_record_pdf` llama
  `build_pdf(rec, cache_dir=figures.cache_dir()[0], thumbs=None)` directo (costura `_pdf_figures_kwargs` de F5 retirada); (vi)
  `smoke_council` D.1 acepta `user_content=None` apilado tras `tools` y los 5 literales de modelo fuera de `models.py` (M.4) llevan
  `# models-literal-doc`; (vii) `smoke_run_pipeline` gana 8 checks de costura (O) — sha frozen == bundle == ledger == panels == saw_figures
  (⊆ items), `judge.figures_sent == saw_figures.n` por (reviewer, lens) en todos los intentos, `epistemic_summary.figures_*` == frozen en
  blob y vista, `pdf_sections_cover(frozen real)` == {missing [], extra [closed_by, frozen_at]}, `usage_json.figures` espejo, `absence_kind_state
  'declared'`, caché perezosa, y un assert GLOBAL anti-binario sobre TODA la BD del gate (90 corridas × 4 blobs: ni `data:image`, ni la b64 del
  fixture, ni cadenas base64 ≥ 300); (viii) O.2 DECIDIDO: `master` @ ac01b7a NO contiene ca9a03d ⇒ el literal del consejo no cambia
  (costura declarada). MEDIDO: 41/41 smokes exit 0 · `urlopen` 0 donde se mide · `mcp_cache/` byte-idéntico (372 archivos, sin
  `figures/`) · `grep -c figure-only CLAUDE.md` = 1 · `grep figure rag_index/query_service/precedent.py` = 0 · 21/21 env ⊆ compose ∩ README
  · `smoke_live_figures.py --dry-run --pmcid PMC11379296` exit 0 con `captured.content_equals_blocks True` en los TRES transportes.
- **Corrector (2026-09-16, sin git — el orquestador commitea):** aplicó los hallazgos de los tres revisores (doctrina · corrección ·
  contrato) marcados *(corrector)* en el cuerpo: (1) F.3 sólo se satisface con una cita de TEXTO que RESUELVE al bundle con pasaje
  ENTREGADO — un id alucinado al lado de la figura ya no rescata la afirmación; D.2 «same paper» se MIDE (informativo); (2)
  `VISION_LENSES_MAX = 2`: > 2 lentes por env o por llamador → default declarado (`'… (>2 lenses)'`), §7 hecho cumplir por código;
  (3) el PDF aplica `WITT_FIGURES_EMBED_LICENSES` de HOY en la miniatura (misma puerta que el 403 del GET; 'embebible al congelar; NO
  embebible HOY'); (4) el lazo D.4 se cierra TAMBIÉN entre turnos (`build_thread_context` etiqueta `from_vision_lens` desde el
  registro del padre + `previous_audit.n_from_vision_lens` + `THREAD_VISION_FINDINGS_CLAUSE` en `synth_system`); (5)
  `content 'panel-judgment'` casa SOLO por id compuesto (dos papers con el mismo `fig_id` ya no colisionan); (6) la fila con
  `citation_support` declara `citation_support_vision_informed` y `FIGURE_READING_RULE` pide juzgar SOLO el caption (la `description`
  de `citation_support` NO cambia: VERDICT_TOOL sin `figure_readings` sigue byte a byte el de 1.11); (7) `token_usage.figures` distingue
  `bytes_downloaded` (verified ∧ ¬cache_hit) de `bytes_verified` y declara `n_cache_hit` (también `/usage.figures`); (8) el presupuesto
  POR PAPER se APLICA dentro de la descarga (`_get_bytes(deadline, clock)` → `not-fetched (timeout)`); (9) sha ≠ en caché → la copia NO
  se reutiliza: UNA re-descarga DECLARADA (`cache_mismatch_hrefs/_refetched`, `sha_changed_from_previous_ledger`); (10)
  `tokens_measured` cuenta la MISMA petición menos los bloques `image` (los rótulos de caption son texto, no visión); (11) runs proyecta
  tokens de visión con el mismo `detail` que composite_auditor; (12) `now` naive normalizado a UTC y la resta del ledger dentro del try;
  (13) el índice `GET /figures` mide `cache.dir_state` con `create=False`; (14) `audit_initial.vision` cuando audit() la trae; (15)
  clasificador ÚNICO de cita-figura en runs (superset de verify_output) + `kind_reported`; (16) `n_error` aparte de `n_not_fetched` en
  `frozen.figures`, `stage.figures.summary` y `figure_citations` (+ `n_other`, `n_figure_shaped_other_kind`); (17) README (rutas
  `/figures` con la forma real, 5 `expose_headers`, ≤ 2 lentes), comentario de `SECCIONES` sin la trampa de la regex y la regex ANCLADA
  escrita en (K), lista «tipar y pintar» completada y plan W4 corregido (`WITT_MCP_CACHE_DIR` re-fijada, fixture `*_fulltext.xml`,
  fixtures sintéticos marcados). RECHAZADO con evidencia: ninguno — los 23 hallazgos se confirmaron contra el código (los duplicados
  R1/R2 sobre F.3 y sobre la miniatura se aplicaron una vez). MEDIDO tras corregir (máscara offline, una .db por smoke,
  `WITT_MCP_CACHE_DIR` temporal): smoke_figures **141/141** (+6) · smoke_panel_vision **60/60** (+5) · smoke_gate_citations **80/80** (+3) ·
  smoke_record_pdf **56/56** (+2) · smoke_figures_http **43/43** (+1) · smoke_thread_context **42/42** (+2) · smoke_run_pipeline
  **372/372** (+5) · smoke_usage_http 34/34 · smoke_models 96/96 · los 41 `smoke_*.py` exit 0 · `smoke_live_figures.py --dry-run
  --pmcid PMC11379296` exit 0 (`content_equals_blocks True` ×3, `urlopen_real=0`, `db_imported=False`).

## Context

1. **Hoy el XML JATS ya está en disco y el parser lo tira.** `fetch_paper.fetch_external` (analysis/scripts/lib/fetch_paper.py:344)
   cachea `raw_paper_<cid>_<stamp>_fulltext.xml` (:381) y lo lista en `raw_cached` (:414, rutas relativas a `ROOT` vía `_rel`
   :406); `_xml_to_text` (:247-255) borra `<graphic>` con `<[^>]+>` y reduce `<fig>` a texto: el `xlink:href` y el `@id` —
   la única vía determinista de bajar y nombrar una figura — se pierden. MEDIDO hoy sobre `mcp_cache`: **12 XML JATS**
   (9 `raw_paper_*` + 3 `raw_europepmc_S4-*_fulltext_20260721.xml`) con **60 `<fig>`** — PMC7809618 4 · PMC3198425 3 ·
   PMC9844136 8 · PMC11379296 9 · PMC11647118 6 · PMC12161502 0 · PMC12184772 0 (trae `<fig-count>` sin figuras: la trampa
   del regex ingenuo) · PMC13286355 11 · PMC6279434 4 · PMC6424945 3 · PMC8613261 7 · PMC8786916 5; 2 sin `<label>` y **2 sin
   `<caption>`** (`undfig1` abstract gráfico: PMC11647118 `fx1.jpg`, PMC7809618); captions media 1 030 chars, mediana 899, máx
   3 087 (21 de 58 > 1 200; 41 > 600). Cada `<fig>` de PMC trae `<alternatives>` con `<graphic content-type="image">` (.jpg) +
   `content-type="thumb"` (.gif) y PIs `<?original-width 2250?><?original-height 1252?><?scaled-width 750?><?scaled-height
   417?>` (PMC11379296 g001); Springer (PMC6424945) sin `<alternatives>`. `<fig>//<permissions>` a nivel figura: **0 en los 12**.
   *(Un diseño afirmó "9 XML / 45 figs, no 12 como dice el brief": FALSO — omitió los 3 `S4-*`. El juez 1 mencionó 31 XML
   `S4sweep`: `find` = 0 en el árbol @ 9d90c01; no se afirman.)*
2. **El zip de `/{PMCID}/supplementaryFiles` SÍ trae las gráficas del cuerpo — medido en bytes, no supuesto.**
   `tool-results/webfetch-1788917902535-6u9l6n.zip` (8 638 262 B, bajado 2026-09-08) tiene EXACTAMENTE 27 entradas: 9
   `pone.0307390.g00N.jpg` + 9 `.gif` (thumb) + 9 `s00N.pdf/.xlsx`. Los 9 JPG con sha256 y dims MEDIDOS hoy: g001 189 021 B
   `40877777ed82…` 750×417 · g002 154 092 B `78040d4deba4…` 738×840 · g003 185 231 B `8ddfb311f2bc…` 715×839 · g004 155 456 B
   `059e4bb82a7c…` 750×725 · g005 88 842 B `5b7d75e858d4…` 750×474 · g006 149 238 B `4a9e17b4b661…` 750×655 · g007 224 199 B
   `6e875992fe37…` 674×501 · g008 61 866 B `412965019bb5…` 750×251 · g009 61 086 B `58d57b703b16…` 750×556 — **las dims
   coinciden con la PI `scaled-*`, no con `original-*`**: EPMC entrega la versión escalada (≤ 840 px). Consecuencia: dos de los
   tres diseños proyectaron tokens de visión a 996–1 568 px (2–4× alto) y uno propuso un derivado LANCZOS con segundo sha —
   innecesario para EPMC *(síntesis: un solo sha, el del original; ver (B))*. El endpoint no está documentado por EPMC (la Help
   devolvió 403 a WebFetch; `?includeInlineImage=true` NO está verificado y NO hace falta para lo medido — no va por default).
3. **La licencia vive en `<permissions>` con NUEVE formas en 12 XML, y el `license` del search de EPMC SÍ está en caché.**
   `ali:license_ref` (PMC6424945 — además `license-type="OpenAccess"`, que NO es licencia —, PMC8613261, PMC12184772) ·
   `<ext-link>`/URL en `<license-p>` a `creativecommons.org/licenses/by/4.0` (PMC11379296, PMC9844136, PMC13286355,
   PMC6279434) · prosa + URL NC (PMC11647118 «CC BY-NC license (http://…/by-nc/4.0/)») y NC-ND (PMC7809618) · prosa SOLA
   «Creative Commons Attribution License» sin URL (PMC3198425, PLoS 2011) · «(CC BY)» sin URL (PMC8786916, Frontiers) · prosa en
   portugués sin variante (PMC12161502 → desconocida). Y `mcp_cache/raw_europepmc_*.json` trae el campo del search en 7
   archivos (37 ocurrencias: `"cc by"` ×28, `"cc by-nc"` ×2, `"cc by-nc-nd"` ×7) que `fetch_paper._normalize_hit` (:171-178)
   DESCARTA — los 15 `raw_paper_*.json` cacheados no tienen `license`. *(El ganador lo difería a un 0083.1 por no haber mirado
   los raw del search; los dos jueces piden la segunda fuente ya — injerto de D2.)*
4. **El sintetizador es ciego a las figuras por CONSTRUCCIÓN, no por prompt — y hay un lazo que ningún diseño vio.**
   `runs._prompt_path_b` (rag_index/query_service/runs.py:1311-1338) proyecta por paper SOLO `_PROMPT_PAPER_KEYS` (:1304) + `fetched`
   {found, full_text, …}: una lista blanca por llave. Pass1 es DI-only (`_compact_evidence(bundle, include_path_b=False)` :2402);
   pass2 (:2573), la revisión (:2652) y el panel (:2612, :2670) reciben `_compact_evidence(bundle)`. **Lazo:** `_panel_findings`
   (:782-793) recoge `caught`/`reasons`/`correction_applied` de jueces REVISE/APPROVE_MINOR → `rev_evidence['panel_findings']`
   (:2647) → `_synth(rev_evidence, 'revision')` (:2652): una lente con visión que escriba «la figura 3 muestra 42 %» en `caught`
   se lo dicta al sintetizador de la revisión. Un diseño afirmó "no hay lazo" (falso, juez 2); este ADR lo cierra en (D.4).
5. **`SYNTH_TOOL` no exige marcadores `[n]` en `direct_answer`** (runs.py:200-262; `evidence_cited.items.kind.enum` = `di-chunk |
   di-record | di-database | paper | store-resolution | other` :236-238) y `_normalize_citations` (:1591-1633) numera por
   enumeración sin validar `kind`. Un predicado que localice "la oración que cita la figura" por `[n]` es vacuo si el texto no
   trae marcadores (juez 2) — por eso el predicado numérico nace INFORMATIVO y el duro cuenta kinds (F).
6. **`verify_output.admissible` es una conjunción extensible** (analysis/scripts/lib/verify_output.py:219-247;
   `extra_predicates: (text_or_obj, report) -> (name, ok)`, «cada callable DEBE ser un invariante duro determinista»);
   `positive_claim_requires_citations` (:351-374) es el patrón predicado + `.evaluation`; `runs._positive_claim_check` (:1930) y
   `_gate` (:1969-1994) el cableado tolerante. `_bundle_evidence_index` (:398-435) indexa `path_a.hits` y `path_b.papers`
   (evidence_id, PMID±prefijo, PMCID, DOI; `delivered` = abstract | text_excerpt | statement | fenotipos ZFIN) — las figuras no
   existen para la escalera (`SUPPORT_LADDER` :266).
7. **El panel manda UN `user_text` string a todos los miembros.** `composite_auditor.audit` (analysis/scripts/lib/
   composite_auditor.py:910; `user_text = json.dumps({claim, evidence, deterministic_checks})` :961-965; system por lente :969-980
   con `_LENS_CHARGES` :316-338; `caller(dict(member, attempt=attempt), system, user_text)` :1002; la fila copia SOLO
   `reviewer/family/lens` + `seat` :1029-1036 — nada del `member` extra fuga al frozen). `_anthropic_tool_call` manda `"content":
   user_text` (:493); `_responses_kwargs` `"input": user_text` (:600); `_openai_chat_call` `content: user_text` (:795);
   `_default_caller` (:850-873) despacha por `member['api']`. **HOY el juez reproducibility es `gpt-4o` por
   `openai-chat-completions`** (models.py:88-89 `bridge`, `api_verified True`; g2 :148 — @ ca9a03d :98-99 y :192) y Astra es `candidate` por Responses
   (:92-93, `api_verified False` — @ ca9a03d :102-103): un diseño que sólo cablee Anthropic + Responses deja UNA lente con visión en producción (los
   dos jueces lo marcan OBLIGATORIO). `VERDICT_TOOL.citation_support` (:297; `parse_citation_support` :225;
   `citation_support_from_panel` :247) es el precedente de "campo opcional por lente".
8. **Formas y límites de los proveedores (VERIFICADOS por WebFetch 2026-09-15).** Anthropic
   (platform.claude.com/docs/en/build-with-claude/vision): bloque `{"type":"image","source":{"type":"base64","media_type":
   "image/jpeg","data":…}}` (también `url` y `file`); «Claude works best when images come before text»; con varias imágenes
   «introduce each one with a short text label (`Image 1:`…)»; jpeg/png/gif/webp (animaciones: primer frame); 10 MB base64 por
   imagen; 100 imágenes por request (modelos de 200k); 8000×8000 px; **> 20 imágenes por request ⇒ cada una ≤ 2000 px**
   («many-image requests»); 32 MB por request; **tokens = ⌈w/28⌉ × ⌈h/28⌉**; tiers **High-resolution (Claude 4.7 y
   posteriores): lado largo 2576 px / 4784 tokens · Standard (los demás): 1568 px / 1568 tokens**; ejemplos 1000² → 1296,
   1920×1080 → 1560 (std) / 2691 (high). OpenAI (developers.openai.com/api/docs/guides/images-vision): Responses `{"role":"user",
   "content":[{"type":"input_text","text":…},{"type":"input_image","image_url":"data:image/jpeg;base64,…","detail":"auto"}]}`,
   `detail ∈ low | high | original | auto` (omitido = auto); 512 MB por request, 1 500 imágenes; **modelos por parches
   (gpt-6-astra, gpt-5.6-sol/terra/luna, …): `⌈w/32⌉×⌈h/32⌉`, tope 2 500 parches a `high` para gpt-6-astra, multiplicador 1.2
   (astra y sol)**; modelos por tiles (gpt-4o, gpt-4.1, gpt-5.1): encajar en 2048², lado corto a 768, tiles de 512 px, **85 +
   170 × tiles**, `low` = 85 fijos. La forma de Chat Completions (`{"type":"image_url","image_url":{"url":"data:…","detail":…}}`)
   NO apareció en el documento leído: es la forma pública conocida, **declarada 'no re-verificada por doc en esta obra'**
   (patrón `api_verified`) — el smoke la fija, LG4 la mide. Ninguna de las dos APIs desglosa tokens de imagen en `usage`
   (`_numeric_usage` :437, `_responses_usage` :626 sólo ven totales) → el desglose de visión es PROYECCIÓN (H).
9. **El PDF de servidor lee 30 llaves y el frozen 1.10 tiene 50.** `record_pdf.py` (516 líneas @ 9d90c01) hace `record.get(…)`
   sobre 30 llaves (26 con comillas dobles + `run_id`, `question`, `render_contract_version`, `closed_by`), de las cuales
   `consensus` es de la zona de servicio (`app._ratings_view` :1096, fusionada al leer :976) → 29 llaves del frozen cubiertas,
   **21 top-level OMITIDAS + 2 anidadas** = las 23 líneas `[pdf]` de `witt-webapp/tools/parity_debt.json` (models,
   audit.quorum, token_usage.by_stage.panel.by_model, user_id, measured_at, store_at_retrieval, reasoning, agents_invoked, plan,
   plan_declared, plan_question_matches_run, deterministic_checks, niches, usage_raw, citations_schema, evidence_cited_raw,
   thread_parent_matches_run_rule, plan_parent_matches_run(+_state), plan_snapshot_matches_run(+_state), competence,
   citations_support_summary). Además: `_NOT_INSTRUMENTED` es UN literal fijo «contrato < 1.8» (:81) que se imprime también para
   llaves nacidas en 1.9/1.10 (falso para `models`); la regla del sha del padre es PROSA FIJA (:209-213) en vez de leer
   `thread_parent_matches_run_rule`; las citas (:461-471) funden los 5 estados de `citations_schema.source` (runs.py:1602-1633:
   `list | string-reparsed | string-unparseable | absent | unsupported-type`) en «[?] citas tipadas no constan (contrato pre-1.1)»;
   `search_ledger` sólo `state/n_rounds/cap/stop` (:454-457); `token_usage` sólo totales (:492-496). Las 50 llaves del frozen:
   31 en el literal `frozen = {` (:2710-2813, `user_id` y `question` en :2712) + 17 asignadas `frozen["…"] =` (:2816-2951:
   thread, thread_context, thread_context_skipped_reason, thread_parent_matches_run(+_state,+_rule), precedent_citations(+_state),
   origin, plan_parent_matches_run(+_state), plan_snapshot_matches_run(+_state), episode_axes, niches) + `frozen_at`/`closed_by`
   (:3013-3014). El gate de la webapp mide por regex `PDF_ACCESS_RE` (tools/parity_check.py:439-441; `frozen_keys` :269;
   `PDF_NESTED` :451; `check_pdf` :479). **(F7: alineado a ca9a03d) ADR-0082 YA aterrizó: `record_pdf.py` @ ca9a03d tiene 679 líneas con
   `_NOT_INSTRUMENTED_1_11` (:277) y `_section_consejo` (:308); F6 arranca sobre ese archivo y el doble dueño quedó resuelto por orden
   de aterrizaje (J.5)/(O), no por rama condicional.**
10. **La caché es efímera en Dokploy y sin tope.** `Dockerfile` `COPY . /app` (:10), `mcp_cache/` en `.gitignore` (:104), el
    compose (144 líneas) NO declara `volumes:`; `WITT_MCP_CACHE_DIR` (compose :88) la honran sólo `search_harness.py` y las 3
    tools Layer 0 (`alliance_orthologs`, `ensembl_homology`, `zfin_expression_tsv`) — `fetch_paper.CACHE = ROOT/'mcp_cache'`
    (:66) y `answer_pipeline.CACHE` (:138) NO. `mcp_cache` pesa **5.6 GB / 283 entradas** sin sweeper (único `unlink`:
    `zfin_expression_tsv.py:219`, el `.part`). Una caché de imágenes sin tope crece sin freno *(injerto de D3: tope LRU)*.
11. **CORS.** `app.add_middleware(CORSMiddleware, …, allow_headers=["Authorization","Content-Type"])` (app.py:111-113) SIN
    `expose_headers`: un `fetch()` cross-origin de la webapp NO puede leer `ETag`/`X-Witt-Figure-*` de la respuesta de bytes
    (hallazgo del juez 1; ninguno de los tres lo vio). Y `<img src>` no manda `Authorization` (`_user_of` :118): la webapp baja
    por fetch → blob, como `descargarRegistroPdf` (witt-webapp/src/api/client.ts:306-319).
12. **La regla «figure-only NOT asserted» no existe en el repo.** `grep -ri 'figure-only|figure only'` = 0 en `CLAUDE.md`
    (§7 :144-163), `docs/`, `skills/`, `analysis/scripts/lib/`. El brief la cita como §7; este ADR la escribe (D.5, M.7).
13. **ZFIN no entrega ids de figura.** `grep ZDB-FIG mcp_cache` = 0; `zfin_zebrafish.py` no los trae. «ZFIN → jamás bytes, sólo
    enlace ZDB-FIG» queda como fila de la tabla de licencias y estado declarado, sin fuente hoy (L).
14. **Dependencias medidas en el venv** (`dev/.venvs/witt-query-service`): fpdf2 2.8.8 + Pillow 12.3.0 (ya llegan con fpdf2,
    record_pdf.py:24-25): miniaturas en el PDF y dims medidas sin dependencia nueva. `figures.py` es stdlib puro (dims por
    cabecera JPEG/PNG/GIF/WebP con `struct`); Pillow SOLO en `record_pdf` (miniaturas) — declarado `dims_source 'header'`.

## Decision

**(A) `analysis/scripts/lib/figures.py` (NUEVO, stdlib puro: `re, json, hashlib, zipfile, io, struct, urllib, time, os, pathlib`) —
parser JATS y licencia por TABLA CERRADA.** `MODULE_VERSION = 'fig-1'`, `PARSER_VERSION = 'jats-fig-1'`, `LICENSE_TABLE_VERSION =
'lt-1'`. *(A.1 parser)* `parse_jats(xml_text, pmcid) -> {figs[], n_fig, n_without_label, n_without_caption, n_without_graphic,
n_thumbs_ignored, parser_version}`: matcher `<fig\b(?!-)` (la trampa `<fig-count>` de PMC12184772 tiene golden); por `<fig>`:
`fig_id` (@id, obligatorio; sin id → fila `state 'no-fig-id'` contada, no ítem), `label: string|null`, `caption` (texto plano
con la MISMA limpieza de tags que `_xml_to_text`, `html.unescape` una vez, tope `WITT_FIGURES_CAPTION_CHARS=2000` con
`caption_truncated` — el caption íntegro NO se guarda aparte: vive en el XML cacheado), **`caption_state ∈ 'present' | 'absent'`**
*(injerto de D2: `undfig1` sin `<caption>` ni `<label>` — una figura sin caption NO se entrega al sintetizador ni a las lentes:
no puede sostener texto)*, `caption_lang: string|null` (del `xml:lang` de `<article>`/`<caption>` si existe — medición de la
fuente; jamás detección), `graphic_href` (el `<graphic content-type="image">` dentro de `<alternatives>`, o el único `<graphic>`
si no hay alternativas; `content-type="thumb"` se IGNORA y se cuenta), `dims_declared {original {w,h}|null, scaled {w,h}|null}`
desde las PIs `<?original-*?>`/`<?scaled-*?>` (clase: declaración de la fuente; `image-scaled-*` de Springer se lee igual),
`fig_permissions_present: bool` (si `<fig>//<permissions>` existe se parsea con las mismas reglas y GOBIERNA la figura con
`license_scope 'figure-level'`; ilegible → `unknown`; `<attrib>` → `attrib_present true`, no se parsea como licencia). **`_xml_to_text`
NO se toca**: el `.txt` de la Ruta B queda byte-idéntico. *(A.2 licencia, DOS fuentes)* `parse_license(xml_text,
search_license=None) -> {id, source, evidence_text (≤200 del <license-p>), url|null, rule_no, version|null, scope
'article-level', conflict?: {xml, search}}` con REGLAS ORDENADAS y vocabulario CERRADO `LICENSES = ('cc-by','cc0','cc-by-sa',
'cc-by-nc','cc-by-nd','cc-by-nc-sa','cc-by-nc-nd','cc-by-prose-unconfirmed','zfin-display-only','unknown')`: (1) `<ali:license_ref>`
URL → variante por path (`/by/`, `/by-sa/`, `/by-nc/`, `/by-nd/`, `/by-nc-sa/`, `/by-nc-nd/`, `/publicdomain/zero/` → cc0;
también el atributo `content-type="ccby…"` cuando la URL falta) → `source 'ali-license-ref'`; (2) `<ext-link xlink:href>` a
creativecommons.org dentro de `<license>` → `'ext-link'`; (3) URL creativecommons.org en el texto de `<license-p>` → `'license-p-url'`;
(4) tokens en prosa `CC BY-NC-ND | CC BY-NC-SA | CC BY-NC | CC BY-ND | CC BY-SA | CC BY | CC0` — **compuestos ANTES que `CC
BY`** → `'license-p-token'`; (5) prosa `Creative Commons Attribution` SIN `Non[- ]?Commercial | No[- ]?Deriv | Share[- ]?Alike` →
`cc-by` con `'license-p-prose'` si `WITT_FIGURES_PROSE_LICENSE=1`, si no `cc-by-prose-unconfirmed` (E3); (6) el `license` del
search de EPMC normalizado (`'cc by'` → cc-by, `'cc by-nc-nd'` → cc-by-nc-nd) como fuente `'epmc-search'` SOLO cuando el XML no
dio (1)–(5); (7) resto → `unknown`, `source 'none'` (`license-type="OpenAccess"` solo NO es licencia). **Precedencia XML > search;
si ambos existen y difieren → gana el XML y `conflict {xml, search}` viaja declarado** *(injerto de D2)*. **`fetch_paper._normalize_hit
+= "license": r.get("license")`** (fetch_paper.py:171-178 — *F7: F1 ya lo aterrizó, @ ca9a03d+F1 :178*; None si EPMC no lo manda; los `raw_paper_*.json` viejos siguen sin
él: `search_license None` declarado). *(A.3 tabla cerrada)* `LICENSE_TABLE = {id: {embed, panel_view, fetch_bytes, words_es}}`:
cc-by / cc0 / cc-by-sa → `embed True, panel_view True` · cc-by-nc / cc-by-nd / cc-by-nc-sa / cc-by-nc-nd → `embed False,
panel_view True` (E2, default delegado) · cc-by-prose-unconfirmed → `embed False, panel_view True` · **unknown → `embed False,
panel_view False, fetch_bytes True`** (se bajan y verifican por sha; términos desconocidos = los bytes NO viajan a un tercero —
*síntesis: veredicto de los jueces sobre D2/D3*) · zfin-display-only → `embed False, panel_view False, fetch_bytes False`.
`WITT_FIGURES_EMBED_LICENSES` y `WITT_FIGURES_PANEL_LICENSES` sólo pueden RESTRINGIR sobre la tabla; un id fuera de tabla se
ignora y se declara en `figures.license_table.env_ignored[]`. `embeddable` y `panel_view` viajan por figura con
`license_table_version`. Regla declarada en la tabla (`rule`): «la licencia del ARTÍCULO puede no cubrir una figura reutilizada
de terceros ('unless indicated otherwise in a credit line', PMC8613261); el código sólo lee `<permissions>` (artículo o figura) —
lo demás es límite declarado, no detección».

**(B) `figures.fetch_figures` — UN zip por paper, sha256 del ORIGINAL, caché acotada, presupuesto propio, filas declaradas.**
*(B.1 fuente)* Mecanismo ÚNICO por default: `GET https://www.ebi.ac.uk/europepmc/webservices/rest/{PMCID}/supplementaryFiles`
(la URL verificada 200; SIN `?includeInlineImage` — no verificado, no necesario: Context 2) por paper seleccionado con
`fetched.full_text True` y `*_fulltext.xml` en `fetched.raw_cached`; costura de red ÚNICA `figures._get_bytes(url, timeout,
max_bytes)` con `net_throttle` del host `www.ebi.ac.uk` (mismo pacing que `fetch_paper._throttle` :127-133). **Precheck de
`Content-Length` contra `WITT_FIGURES_ZIP_MAX_MB=40` ANTES de leer el cuerpo; sin `Content-Length` se lee por chunks de 1 MB con
tope y se aborta declarando; streaming a `<zip>.part` + `os.replace`** (patrón `zfin_expression_tsv.py`; *injerto de D3*). Del zip
se extraen SOLO las entradas cuyo basename == `graphic_href` de un `<fig>` (case-insensitive; jamás `s00N.pdf/.xlsx`, jamás el
`.gif` thumb — si el `.jpg` falta y el thumb existe: `bytes_state 'not-fetched (href-not-in-zip; thumb-available)'`, declarado, no
se baja). Mime por magic bytes (jpeg/png/gif/webp; `mime_from_extension` aparte si difiere); `dims_measured {w,h}` por cabecera
(SOF/IHDR/GIF LSD/VP8) con guardia `w×h ≤ 40 MP` (bomba → `decode-error`); `dims_match: bool|null` = medida == `dims_declared.scaled`
(contra `scaled`, NO `original`: Context 2). **`sha256` = bytes ORIGINALES tal como los entregó la fuente; UN solo sha (no hay
derivado LANCZOS: las figuras EPMC caben en el tier estándar sin reescalar)** *(síntesis contra D3.D2)*; `raw_ref =
raw_store.source_pointer(source_url=f'{EPMC}/{pmcid}/supplementaryFiles#{href}', path=<cache>, content_type=<mime>)`
(analysis/scripts/lib/raw_store.py:54-62 — la MISMA forma que los papers, fetch_paper.py:398-403). Plantilla de href directo
`WITT_FIGURES_HREF_TEMPLATE` NO existe en 0083 (el href directo `europepmc.org/articles/{PMCID}/bin/{href}` no está verificado;
LG1 lo mide y, si pasa, un 0083.1 aditivo lo declara como respaldo). *(B.2 estados)* `BYTES_STATES_EXACT = ('verified',
'mismatch', 'not-requested (kill-switch)', 'never (zfin-display-only)')` (una licencia `unknown` SÍ se baja y verifica —
`fetch_bytes True`; lo que no viaja son sus bytes a terceros); `BYTES_STATES_PREFIXES = ('not-fetched (', 'error: ')` con razones cerradas
`href-not-in-zip | href-not-in-zip; thumb-available | http-<code> | not-a-zip | bad-zip | zip-over-max | timeout | network |
budget-exhausted | paper-cap | run-cap | size-cap | decode-error | unsupported-mime | no-caption | cache-read-only | no-graphic` y `'error: <tipo>: <msg≤120>'` *(F1: `cache-read-only` lo
nombraba B.3 sin listarlo; `no-graphic` = `<fig>` sin `<graphic>`, sin href que bajar)*.
Un fallo del zip deja TODAS las filas del paper `not-fetched (<razón>)` con caption intacto; **la corrida sigue** (§6). *(B.3
caché)* `figures.cache_dir() = Path(WITT_MCP_CACHE_DIR or ROOT/'mcp_cache') / 'figures'` (honra la env como las tools Layer 0;
`frozen.figures.cache.dir_source ∈ env | default | injected` — `injected` cuando un llamador pasa `cache_root` distinto del de la env, F1); layout `figures/<PMCID>/<href>` + ledger raw `figures/<PMCID>/_figures_<YYYYMMDD>.json`
{fetched_at, mechanism, http_status, zip_bytes, entries[] {href, sha256, bytes, mime, dims}}; TTL `WITT_FIGURES_TTL_DAYS=30`
(ledger fresco + archivos presentes + sha recalculado igual → `cache_hit True`, cero red; sha ≠ → la copia NO se reutiliza como
veredicto *(corrector: antes se devolvía `bytes_state 'mismatch'` como cache-hit COMPLETO y un archivo corrupto/parcial con ledger
fresco dejaba esa figura sin bytes 30 días en TODAS las corridas)*: UNA re-descarga con presupuesto, DECLARADA en el ledger del paper
(`cache_mismatch_hrefs[]` antes de la red; `cache_mismatch_refetched[]` al lograrla; `sha_changed_from_previous_ledger [{href,
previous_ledger_sha256, sha256}]` si la fuente entrega hoy otro sha — cambio en la fuente o en la caché: medido, no disfrazado) y la
fila queda `verified` contra los bytes que la fuente entregó AHORA (el sha es el de los bytes originales tal como llegaron); si la red
falla, las filas quedan `not-fetched (<razón>)` como en cualquier caché incompleta; errores JAMÁS se cachean); **tope `WITT_FIGURES_CACHE_MAX_MB=512` con evicción LRU por mtime al escribir, determinista,
`evicted_n` en el registro; `0` = sin tope declarado** *(injerto de D3)*; `cache_dir_state ∈ 'writable' | 'read-only' | 'missing'`
medido al inicio de la etapa (read-only → todas las filas `not-fetched (cache-read-only)` sin excepción). *(F8)* `cache_dir_state(path,
create=True)`: `attach` MIDE sin crear (`create=False`) y crea el dir SOLO cuando hay papers seleccionados (sin XML ⇒ `dir_state 'missing'`
medido y ningún mkdir); el `plan` lo mide con `create=(n_sel > 0)` — un gate sin `WITT_MCP_CACHE_DIR` ya no deja `<repo>/mcp_cache/figures/`. *(B.4 presupuesto)*
`WITT_FIGURES_BUDGET_S=90` total por corrida, FUERA de la ronda de búsqueda; por paper `min(45, restante)` (constante declarada);
socket timeout `min(30, restante)`; restante < 5 s → papers pendientes `not-fetched (budget-exhausted)` sin red;
`budget {total_s, used_s, over_budget}`. *(corrector)* el presupuesto por paper se APLICA dentro de la descarga, no sólo se declara:
`figures._get_bytes(url, timeout, max_bytes, dest, deadline=None, clock=None)` consulta el reloj en cada chunk de 1 MB y ABORTA con
`error_kind 'timeout'` (+ `deadline_exceeded True`) al rebasar `min(45, restante)` → filas `not-fetched (timeout)` declaradas — el socket
timeout se renueva en cada `read()` y por sí solo no acota una respuesta que gotea (un servidor a 1 MB cada 30 s habría dejado
`stage.figures.paper {start}` como último latido ~20 min con el tope de 40 MB); las fakes con la firma vieja `(url, timeout,
max_bytes, dest)` siguen válidas (`fetch_figures` pasa `deadline/clock` sólo si la costura los acepta). `now` naive (sin tz) se
normaliza a UTC en `fetch_figures`/`attach` y la resta contra `fetched_at` del ledger va dentro del `try` (un TypeError ya no escapa
ni tumba la etapa).

**(C) Etapa PROPIA `stage.figures` en `runs.execute_run`, después de `stage.path_b` y antes de pass2 — `answer_pipeline.py` no
se toca.** *(síntesis: D1 adjuntaba dentro de `path_b`; D3 la separa; los dos jueces prefieren la etapa propia porque pass1 es
DI-only y el presupuesto no compite con familias Layer 0.)* `runs._figures_stage(bundle, run_id, on_stage)` corre tras el
evento `stage.path_b` (runs.py:2543) y antes de `_synth(…, 'pass2')` (:2573) SOLO si hubo Ruta B; con `WITT_FIGURES=1`:
selección DETERMINISTA por código — papers `source 'europepmc'|'pubmed'` con `search_rec.pmcid`, `fetched.full_text True` y XML
en `raw_cached`, en orden `selection_rank`, primeros `WITT_FIGURES_MAX_PAPERS=3`; figuras en orden de documento, primeras
`WITT_FIGURES_MAX_PER_PAPER=9`; tope `WITT_FIGURES_MAX_PER_RUN=12`; el resto `not-fetched (paper-cap | run-cap)` con caption
parseado. Localización del XML: `figures.locate_xml(raw_cached, root)` = el único `*_fulltext.xml` de `fetched.raw_cached`
resuelto contra `root` (default `fetch_paper.ROOT`, la base de `_rel` :406; inyectable para el smoke). Resultado: cada paper
gana `paper['figures'] = {state ∈ 'attached' | 'no-fulltext-xml' | 'not-selected (paper-cap)', n, items[FigureItem], ledger}` y
`bundle['figures_ledger']` (resumen → `frozen.figures`). Los ítems ZFIN no ganan figuras (`zfin_figures_state 'not-available
(zfin_zebrafish payload carries no ZDB-FIG ids at 9d90c01)'`). Eventos (`agent 'figures'`, `db.add_event` :1190 sin cambio de
esquema): `stage.figures.plan {n_papers_eligible, n_papers_selected, caps{…}, budget_s, cache_dir_state, vision {lenses[],
max_per_lens, detail}}` (una vez) · **`stage.figures.paper {pmcid, evidence_id, phase 'start', heartbeat true}` ANTES de cada
descarga** *(injerto de D2: acota el hueco de latido a UNA descarga ≤ 45 s < HEARTBEAT_STALE_S 300, app.py:442 — corrector: hecho VERDAD por el
deadline por paper de B.4; antes sólo se declaraba en el ledger)* y `{phase
'done', n_figs_in_xml, n_selected, license {id, source}, mechanism 'supplementaryFiles-zip', http_status?, zip_bytes?, elapsed_s,
n_extracted, n_missing, error?}` · `stage.figures.figure {id, sha256, media_type, bytes, dims_measured, dims_match, bytes_state,
embeddable, panel_view, heartbeat true}` (una por figura extraída) · `stage.figures.summary {state, n_papers_with_xml, n_figures,
n_verified, n_not_fetched, n_error (corrector), n_embeddable, n_unknown_license, budget{…}, evicted_n}`. Con `WITT_FIGURES=0`: UN
`stage.figures.summary {state 'kill-switch WITT_FIGURES=0'}` y nada más (la Traza pinta el estado; los eventos no son el frozen).
Cancelación durante la etapa → `cancelled` con las filas ya declaradas. *(F4/F8, forma real)* la etapa corre tras
`bundle['search_ledger']` (ambos disparadores de Ruta B) y ANTES de la ronda 3 del consejo; sin Ruta B NO emite ningún evento (state
`'no-path-b'` sólo en el frozen); los cuatro tipos (`runs.FIGURES_EVENT_TYPES`) se escriben con `db.add_event(run_id, <literal>, …)` — la
forma que lee la superficie (C) del gate de paridad; `plan`/`summary` llevan llaves adicionales a las de arriba (versiones, mecanismo,
`cache`, `over_budget`, `kill_switch`) y `stage.revision.start += n_from_vision_lens`.

**(D) El sintetizador y el consejo ven SOLO texto observado — y el lazo de la revisión se cierra.** *(D.1)*
proyección PROPIA `runs._prompt_figures` = `{state, n, items[_PROMPT_FIGURE_KEYS], n_delivered}` dentro de `_prompt_path_b` *(F4: copiar la
llave entera habría filtrado `raw_ref`/`cache_path_rel`; el borrador decía `_PROMPT_PAPER_KEYS += 'figures'`)* y `_PROMPT_FIGURE_KEYS = ('id','fig_id','label','caption','caption_truncated',
'caption_state','license','embeddable','sha256_short','dims_measured','bytes_state')` aplicada en `_prompt_path_b` (:1311) SOLO
a ítems `caption_state 'present'`; `license` proyectada como `{id, source}`; jamás `cache_path`, `raw_ref`, `b64`, bytes.
**Gate ESTÁTICO independiente de fixtures** *(hueco que ningún diseño cubrió)*: `smoke_run_pipeline` asserta
`set(_PROMPT_FIGURE_KEYS) ∩ {'cache_path','cache_path_rel','raw_ref','b64','data','bytes_b64'} == ∅` y que el string
`frozen_record_json` y `bundle_json` NO contienen la base64 del fixture ni el prefijo `data:image` en NINGUNA ruta (no sólo en
`figures.items`). *(D.2)* `SYNTH_TOOL.evidence_cited.items.kind.enum += 'figure'` (:236-238) y la `description` gana, literal:
«kind 'figure' = '<PMCID>#<fig_id>'. A figure citation supports ONLY what its caption text says and may only accompany a text
citation of the same paper; you never see the image — never state a number or observation that exists only in an image. Cite
inline as [n] in direct_answer.» *(síntesis: el pedido de marcadores `[n]` del juez 2; `n_marker_absent` se MIDE en (F.4)).*
`synth_system` NO cambia (la serie `ab_trapped_scalar` sigue comparable) — el cambio de `description` es la excepción DECLARADA
al byte a byte del PROMPT (no del registro) y motiva LG9. *(D.3)* `_evidence_ids(bundle)` (:1361-1373) += los `id` de figuras
`<PMCID>#<fig_id>` (para que un voto del panel/consejo que nombre una figura NO caiga como `hallucinated_evidence_id`). *(D.4 el
lazo)* `_panel_findings` (:782) etiqueta cada hallazgo con `from_vision_lens: bool` (= la fila trae `saw_figures.n > 0`) y el
`instruction` de la revisión (:2648-2651) gana la frase «findings marked from_vision_lens describe images: they are judgment;
never adopt a number or observation from them unless it appears in a delivered TEXT passage»; `figure_readings` (G) JAMÁS entra a
`_panel_findings`; y la compuerta (F) corre también sobre la revisión (ya lo hace `_gate` para `'revision'`). *(corrector — el lazo
ENTRE TURNOS)* `build_thread_context` etiquetaba los hallazgos del padre SIN `from_vision_lens` y ese snapshot viaja al sintetizador
del hijo (`wanted['thread_context']`) y al planner; `THREAD_ANTI_LEAK_CLAUSE` sólo prohíbe reutilizar IDENTIFICADORES. Ahora los
hallazgos del PADRE se etiquetan desde SU registro (`figures_enabled = alguna fila trae saw_figures` — un padre 1.11/kill-switch NO
gana la llave, M.1), `previous_audit.n_from_vision_lens` viaja en el snapshot y `synth_system(pass, thread_context=True,
vision_findings=True)` añade `THREAD_VISION_FINDINGS_CLAUSE` («In thread_context.previous_audit, findings marked from_vision_lens describe
images a panel lens saw in the previous turn: they are judgment, never evidence; never adopt a number or observation from them unless it
appears in a delivered TEXT passage of THIS evidence») SOLO cuando `n_from_vision_lens > 0` — sin ella el system es byte a byte el de
ADR-0079/0082 (`ab_trapped_scalar` intacto); `thread_delivery.prompt_components` lo declara. *(D.5)* La regla
se ESCRIBE: viñeta nueva en `CLAUDE.md` §7 (:144-163) — «Figures are observed evidence only as source-pointers (fig_id + sha256 +
license verified by code); their pictorial content is model judgment by at most two panel lenses and never a measurement; no
number or claim that exists only in an image may be asserted (`verify_output.figure_only_not_asserted`, ADR-0083)»; en la
`description` del tool (D.2); en `FIGURE_READING_RULE` (G.3); en el nombre del predicado (F.3). El ADR declara que a 9d90c01 el
literal no existía (Context 12).

**(E) Citas `kind 'figure'`: la escalera de ADR-0080 sin peldaños nuevos, más `figure_verification`.** `_normalize_citations`
(:1591) no cambia (conserva `kind` tal cual). `verify_output._citation_keys` (:379-395) ya cubre la variante mayúsculas del id
compuesto; `_bundle_evidence_index` (:398-435) indexa cada `papers[].figures.items[]` como ítem propio `(id '<PMCID>#<fig_id>',
delivered = caption_state 'present')` *(F2: una figura con `caption_state 'absent'` NO se indexa — la cita a ella queda `unresolved` y
`figure_id_resolves` falla con detail `'caption-absent (never delivered)'`; jamás se entregó al sintetizador)* — `resolved` (id en índice) → `passage_delivered` (caption entregado) → `supported |
unsupported` (la palabra del juez evidence-grounding para ese n, `citation_support`), `support_state` = peldaño más alto:
misma semántica, mismos 5 peldaños (`SUPPORT_LADDER` :266). `runs._support_states` (:2118) añade, a toda cita-figura por el MISMO superset conservador de (F) — kind `'figure'` ∨ id
`^PMC\d+#\S+$` ∨ id que resuelve a un ítem (`runs._is_figure_citation`) *(corrector: (E) filtraba SÓLO por kind y (F) por el superset —
una cita con id de figura etiquetada kind 'paper' quedaba gateada pero sin `figure_verification`, fuera de `figure_citations.n`, de
`cited_by_answer`/`n_cited` y de la prioridad «citadas primero» del panel: dos conteos del MISMO registro discrepaban; la etiqueta que
eligió el modelo se conserva en `kind_reported`)* —,
`figure_verification {bytes ∈ BytesState | 'not-a-figure', content ∈ 'panel-judgment' | 'not-evaluated', figure_id: '<PMCID>#<fig_id>' |
null, kind_reported}` — `BytesState` = el vocabulario B.2 COMPLETO tal como viaja en el ítem: `'verified' | 'mismatch' | 'not-requested
(kill-switch)' | 'never (zfin-display-only)'` + prefijos `'not-fetched ('` y `'error: '` *(corrector: el borrador lo acotaba a cuatro
literales; el código copia `bytes_state` verbatim)* (`content 'panel-judgment'` ⇔ alguna lente con visión emitió `figure_readings[]`
para ese id COMPUESTO `'<PMCID>#<fig_id>'` *(corrector: el `fig_id` desnudo colisionaba entre papers — 'F1' es frecuente en JATS — y
atribuía juicio a una imagen que ninguna lente leyó)*), y `citations_support_summary.figure_citations {n, n_verified_bytes,
n_not_fetched, n_error, n_mismatch, n_unresolved, n_other, n_figure_shaped_other_kind}` *(corrector: `n_not_fetched` cuenta SOLO
`'not-fetched (…)'`, los `'error: …'` van a `n_error`, `'never'/'not-requested'` a `n_other` → `n == Σ cubetas + n_unresolved`)*
(ausente con kill-switch: `frozen.figures.state` desambigua). `precedent.serialize_disjoint`/
`validate_disjoint` (precedent.py:220-256) NO se tocan: exigen `n` entero sin `l` en evidencia; `kind` es libre (verificado).

**(F) Cinco predicados DETERMINISTAS en `verify_output` (clase Logic-LM, ciegos a píxeles), cableados en `runs._gate` (:1969)
vía `extra_predicates` con `gating` declarado por predicado.** Patrón `positive_claim_requires_citations` (:351-374: predicado
`(text_or_obj, report) -> (name, ok)` con `.evaluation`); `FIGURE_RULES` (5 literales) congeladas en `deterministic_checks.figures`.
*(F.1 `figure_id_resolves`, DURO)* *(injerto de D2)*: toda cita `kind 'figure'` cuyo id ∉ índice de figuras del bundle →
INADMISIBLE (`reason 'hard predicate failed: figure_id_resolves'`; misma disciplina que un ENSDARG no resuelto). *(F.2
`figure_sha_matches`, DURO sólo en MISMATCH)*: por cita figure resuelta a un ítem con `bytes_state 'verified'`, sha256 del
archivo en caché recalculado == `sha256` del bundle; desigualdad → INADMISIBLE (`mismatches [{id, expected, actual}]`); ítem
`not-fetched (…)` → `n_not_verifiable` y NO falla (la cita sostiene sólo su caption; «sha ALTERADO → inadmisible» es la decisión
tomada; ausencia ≠ alteración, §6) *(síntesis: veredicto de ambos jueces contra D3)*. *(F.3 `figure_only_not_asserted`, DURO)*:
una AFIRMACIÓN POSITIVA (`absence_kind 'not-applicable'` o AUSENTE — la misma lectura conservadora de `POSITIVE_CLAIM_RULE` :294)
con ≥ 1 cita figure y NINGUNA cita de texto que RESUELVA a un ítem del bundle con pasaje ENTREGADO (`_bundle_evidence_index`:
`passage_delivered True`) es INADMISIBLE (la figura corrobora; el texto porta la evidencia — y sólo el texto ENTREGADO puede portarla)
*(corrector: el borrador decía «citas VÁLIDAS TODAS kind figure» y el código contaba como no-figure cualquier id no vacío — una cita
paper ALUCINADA (`PMID:99999999`) al lado de la figura rescataba la afirmación y ningún otro predicado duro la atrapaba; ahora viajan
`n_non_figure_citations_resolved/_delivered/_unresolved` y D.2 «may only accompany a text citation of the same paper» se MIDE por cita
figure en `figure_citations_same_paper [{id, same_paper_text_citation}]` + `n_figure_citations_without_same_paper_text` — informativo,
no gatea)*; declinación (`absence_kind` declarado) sólo con figuras → ok. *(F.4 `figure_numerals_grounded`, INFORMATIVO, `gating False`)* — el proxy
numérico del ganador, degradado por los jueces hasta medir su tasa de falsos positivos (años, `n = 12`, cifras del texto citadas
en otra oración): por cada cita figure con marcador `[n]` en `direct_answer` se toma su oración; todo numeral
(`\d+(?:[.,]\d+)?\s*%?`) debe constar en el caption de esa figura o en un pasaje de texto ENTREGADO de otra cita de la misma
oración; sin marcadores → `state 'no-markers: whole-answer fallback'` (numerales de toda la respuesta vs unión de pasajes de
citas no-figure), `n_marker_absent` CONTADO como límite medido, jamás ok silencioso; `evaluations [{n, id, state, numerals,
numerals_unsupported[], supporting_sources[]}]` se congela; LG3 decide si sube a `gating True` (0083.1). *(F.5
`figure_license_known`, INFORMATIVO, `gating False`)*: `license.id != 'unknown'` para cada figura citada; `unknown [ids]`
congelado — la licencia gatea EMBEBER, no la verdad de la cita. `deterministic_checks.figures = {state ∈ 'checked' |
'no-figure-citations' | 'kill-switch WITT_FIGURES=0' | 'tool-unavailable (verify_output.figure_predicates not in tree — ADR-0083)',
figure_id_resolves {ok, gating true, unresolved_ids[], n_checked}, figure_sha_matches {ok: bool|null, gating true, n_checked,
n_not_verifiable, mismatches[]}, figure_only_not_asserted {ok, gating true, positive_claim, absence_kind_state, n_figure_citations,
n_non_figure_citations}, figure_numerals_grounded {ok: bool|null, gating false, n_marker_absent, evaluations[]},
figure_license_known {ok: bool|null, gating false, unknown[]}, rules {…5 literales}, decided_by 'code'}`; los duros añaden
`'hard predicate failed: <name>'` a `deterministic_checks.reasons`. Sin figuras en el bundle → `state 'no-figure-citations'` y
NINGÚN predicado entra a la conjunción (registro sin figuras = admisibilidad de hoy). *(F2/F8, forma real)* el fragmento conserva
TODAS las llaves y literales de arriba y añade aditivas — top-level `n_figure_citations`, `n_figures_in_bundle`, `n_figures_delivered`,
`gating {}`, `predicates_version 'figpred-1'`; por bloque `reason`, `rule`; `unresolved_detail[]`, `not_verifiable[]`, `checked_ids[]`,
`cache_dir_state`, `sha_source`, `n_figure_citations_kind_figure`, `n_citations_valid`, `state`, `n_numerals_unsupported`, `n_checked` —;
`state` gana el prefijo `'error: '` y el literal `'tool-unavailable (lib/figures.py not importable — ADR-0083 F1)'`; en
`'no-figure-citations'` viajan los 5 bloques con ceros MEDIDOS (una sola forma para webapp/PDF). La cita-figura se clasifica por SUPERSET
conservador (kind `'figure'` ∨ id `^PMC\d+#\S+$` ∨ id que resuelve a un ítem figura). F.4: la unión de respaldo incluye el caption de la
figura citada y los pasajes entregados de las citas no-figure de la misma oración; el match no se incrusta en un número mayor y los
separadores decimales NO se normalizan. Firma real `figure_predicates(citations, bundle, cache_dir, answer_text, absence_kind=_UNSET,
cfg=None)`: `answer_text` acepta el DICT del sintetizador (lee `direct_answer` Y `absence_kind`) — `runs._figure_checks` le pasa el dict
(F8; con sólo el str la lectura conservadora se DECLARA en `absence_kind_state 'not-provided by caller (…)'`).

**(G) Panel con visión: dos lentes, imágenes DENTRO del `member`, tres transportes, lectura etiquetada JUICIO.** *(G.1 quién)*
`composite_auditor.VISION_LENSES = ('evidence-grounding','reproducibility')` (env `WITT_FIGURES_VISION_LENSES`, CSV validado
contra `models.LENSES` :119; fuera de vocabulario → default declarado `lenses_source 'default-invalid-env'`; *(corrector)*
`VISION_LENSES_MAX = 2` (`VISION_LENSES_MAX_RULE`): un CSV o un `vision_lenses=` del llamador con > 2 lentes válidas cae al default
DECLARADO — `'default-invalid-env:WITT_FIGURES_VISION_LENSES (>2 lenses)'` / `'default-invalid-caller (>2 lenses)'` — así CLAUDE.md §7
«at most two panel lenses» y (N)(h) los hace cumplir el código, no sólo la doctrina (antes cuatro lentes recibían imágenes con
`lenses_source 'env:…'` sin declarar desviación)). *(G.2 cómo viajan)*
`audit(..., figures=None, vision_lenses=None)`: `figures` = lista que `runs` arma desde bundle + caché SOLO con `panel_view True`
∧ `bytes_state 'verified'` ∧ `caption_state 'present'`, selección determinista (citadas por la respuesta primero en orden de n,
luego `selection_rank`, luego orden de documento), tope `WITT_FIGURES_MAX_PER_LENS=12` (≤ 20 evita el régimen «many-image
requests», Context 8), cada una ≤ `WITT_FIGURES_MAX_IMAGE_MB=5` (crudos; la API admite 10 MB b64), b64 acumulado ≤ 8 MB por
petición (constante; `n_dropped_by_request_cap` declarado); `{id, fig_id, label, caption, license {id}, sha256, media_type, b64,
dims_measured}`. Para un `member` cuya lente ∈ `vision_lenses`, `audit` llama `caller(dict(member, attempt=k, figures=[…]),
system, user_text)`: **la firma `caller(member, system, user_text)` (:1002) se conserva para TODOS los fakes y para
`runs.panel_caller` (:2294); la fila copia sólo `reviewer/family/lens/seat` (:1029) → la b64 NO fuga al frozen** *(síntesis: D1/D3
contra el `images=` de D2; ambos jueces)*. *(G.3 bloques por transporte)* `_default_caller` (:850) lee `member.get('figures')`
y construye: **Anthropic** (`_anthropic_tool_call(..., user_content=None)`: `None` → `"content": user_text` BYTE A BYTE (:493);
lista → `"content": user_content`) = `[{type:'text', text:'Figure k — <id> (<label>): <caption>'}, {type:'image', source:{type:
'base64', media_type, data}}] × N + [{type:'text', text: user_text}]` (imágenes ANTES del texto, rotuladas — recomendación
verbatim de la doc); **OpenAI Responses** (`_responses_kwargs(..., user_content=None)`: `None` → `"input": user_text` (:600);
lista → `"input": [{role:'user', content: user_content}]`) = `[{type:'input_text', text:…}, {type:'input_image', image_url:
'data:<mime>;base64,<b64>', detail: WITT_FIGURES_OPENAI_DETAIL}] × N + [{type:'input_text', text: user_text}]`; **OpenAI Chat
Completions** (`_openai_chat_call(..., user_content=None)`: `None` → `content: user_text` (:795); lista → `messages[1].content =
[{type:'text', text:…}, {type:'image_url', image_url:{url:'data:…', detail}}] × N + [{type:'text', text: user_text}]`) —
**OBLIGATORIO por los dos jueces: `gpt-4o` = reproducibility HOY por chat.completions (models.py:88-89, :148); sin esto "dos
lentes" sería UNA en producción**; forma declarada `'public form; not re-verified by doc in this work'` (Context 8) → LG4 la mide;
un `http-400` cae en el vocabulario `error_kind` de ADR-0081 y la corrida sigue. El system de las lentes con visión gana
`FIGURE_READING_RULE` (literal congelado en `frozen.figures.vision.rule`): «You may be shown figure images from the cited papers.
Use them ONLY to judge whether the claim misrepresents what the figure shows. NEVER derive, read off or estimate numbers, counts,
sizes or statistics from an image — numbers must come from text. Never put figure-derived numbers or observations in `caught`,
`reasons` or `correction_applied`; report anything you conclude from an image ONLY in `figure_readings` — it is model judgment,
never a measurement. For `citation_support` on a kind 'figure' citation judge the CAPTION text delivered in `evidence` only — the image
never decides support.» *(corrector: la última oración es nueva — la lente evidence-grounding es a la vez lente con VISIÓN y la única
que emite `citation_support`, que sube una cita figure al peldaño supported/unsupported; la fila con `citation_support` gana
`citation_support_vision_informed` (= `saw_figures.n > 0`) para que el registro declare que ese veredicto pudo estar informado por
píxeles; la `description` de `citation_support` en VERDICT_TOOL NO cambia — VERDICT_TOOL sin `figure_readings` sigue byte a byte el de
1.11, golden de smoke_panel_vision)* *(G.4 capacidad por tabla)* `models.MODELS` gana columnas `vision_tier ∈ 'high-res-2576' | 'standard-1568' |
'tile-512' | 'patch-32' | 'none' | 'unknown'`, `vision_multiplier: float|null`, `vision_verified: bool` (False en TODAS hasta
LG3/LG4): opus-5 / sonnet-5 / opus-4-8 → high-res-2576 · haiku-4-5 → standard-1568 · fable → unknown (excluido igual) · gpt-4o →
tile-512 · gpt-6-astra → patch-32 ×1.2 · gpt-5.6-sol → patch-32 ×1.2 · text-embedding → none; `models.vision_tokens(model, w, h)
-> {tokens, formula, tier} | None` es la ÚNICA sede de la fórmula (ADR-0081 A) *(injerto de D3, aterriza DESPUÉS de
`contract-1.11-frozen`: 0082 también edita `models.py`, +152 líneas sin commit)*; `vision_tier ∈ {none, unknown}` → no se envían
bloques y `saw_figures.detail 'model-vision-unknown'`; `panel_signature` NO cambia (verificado en smoke). *(G.5 lo que emite el
juez)* `VERDICT_TOOL.input_schema.properties += figure_readings` OPCIONAL (`[{fig_id, reading (≤400), consistent_with_caption:
bool|null}]`, description «vision lenses ONLY; never numbers read off the image»); `parse_figure_readings` DESCARTA y cuenta ids
no entregados y formas fuera de vocabulario (`figure_readings_dropped`); no emitir ≠ emitir `[]`. *(G.6 la fila)* cada fila del
panel (también `errored`) gana `saw_figures {n, sha256s[], bytes_b64_total, detail ∈ 'sent' | 'lens-not-in-vision-lenses' |
'kill-switch WITT_FIGURES_VISION=0' | 'no-eligible-figures' | 'model-vision-unknown' | 'api-form-not-verified' }` MEDIDO desde lo
que se le entregó al caller; `figure_readings?` + `figure_readings_class 'model-judgment'`; `audit.vision {enabled, lenses[],
lenses_source, n_images_by_lens {}, bytes_b64_sent_total}` (ADR-0087 estratifica la serie por `enabled`). Con `WITT_FIGURES=0`
NINGUNA de estas llaves se emite (M.1). *(F3, forma real)* `saw_figures` y `audit.vision` son SUPERCONJUNTOS de la forma mínima — fila:
+ `attempts_with_images`, `n_dropped {lens_cap, request_cap, invalid}`, `tier`, `api_form_state`, `openai_detail`, `visual_tokens_projected`,
`n_images_unprojected`, `formula`, `projection_class 'proyección'`, `tokens_measured(+_state, +_text_only)`; `audit.vision`: + `state ∈
VISION_STATES`, `rule`, `openai_detail`, `n_candidates`, `n_attempts_with_images`, `visual_tokens_projected_*`, `formula_source`,
`count_tokens`, `readings`, `saw_figures_details` —; `figure_readings[]` normalizadas `{fig_id, id '<PMCID>#<fig_id>', sha256, reading,
reading_truncated, consistent_with_caption, numerals_present}` (un string emitido → `[]` + `figure_readings_dropped 1`);
`FIGURE_READING_RULE` entra al system SOLO cuando de veras viajan imágenes a ese asiento (sin figuras el system es byte a byte el de
1.11); `user_content=None` se apila DESPUÉS de `tools` en `_anthropic_tool_call` y al final en `_responses_kwargs` /
`_openai_responses_call` / `_openai_chat_call`; `audit()` re-aplica `max_per_lens` y `REQUEST_B64_MB` (defensa en profundidad,
declarada en `n_dropped`).

**(H) Gasto — tokens MEDIDOS, visión PROYECTADA por fórmula pública, medición opcional por `count_tokens`.** Los
`input_tokens` de cada juez SIGUEN siendo la medición (la API no separa; Context 8). `token_usage.by_stage.panel.by_model[reviewer]
+= vision {n_images, bytes_b64, visual_tokens_projected, formula ∈ 'anthropic: Σ⌈w/28⌉×⌈h/28⌉ (tier cap)' | 'openai-tile: 85+170×tiles
(fit 2048 → shortest 768 → 512-px tiles)' | 'openai-patch: Σ⌈w/32⌉×⌈h/32⌉ × <mult> (cap 2500)', tier, detail?, formula_source
'<URL doc> (2026-09-15)', class 'proyección', input_tokens_measured_includes_images true, tokens_measured?: int}` (runs.py:1720-1731);
`_sum` y `by_stage_sum_matches_by_model` SIN cambio (nada se suma dos veces); NO se añade etapa `figures` a `TOKEN_STAGES` (:1655)
— la etapa no gasta modelo y su reloj vive en `frozen.figures.budget`. **Reenvío medido** *(hueco de los tres, juez 2)*: cada
intento de cada lente reenvía las imágenes y la API las factura; `figures.vision.sent {n_panels, n_attempts_with_images,
bytes_b64_sent_total, visual_tokens_projected_total}` cuenta panel inicial + revisión (`composite_auditor.audit` en :2612 y :2670)
× intentos (`WITT_JUDGE_RETRIES`). `frozen.figures.vision.cost_projection {per_lens [{reviewer, model, tier, n_images,
visual_tokens_projected, usd_projected}], total_usd_projected, prices_source 'models.prices() (ADR-0081)', class 'proyección'}`.
`WITT_FIGURES_COUNT_TOKENS=1` (default 0) *(injerto de D2)*: para lentes Anthropic se llama `count_tokens` con la MISMA petición
SIN los bloques `image` — `figures.anthropic_blocks(figs, user_text)` menos las imágenes: los rótulos de texto 'Figure k — <id>
(<label>): <caption>' SÍ se cuentan (`saw_figures.tokens_measured_counted_blocks`) *(corrector: contar sólo `user_text` atribuía los
captions — hasta 2 000 chars × 12 — a visión: sesgo al alza por construcción)* — y `vision.tokens_measured = input_tokens −
count_tokens_text_only` (clase medición derivada; una llamada gratuita por lente). *(corrector)* runs proyecta con el MISMO `detail`
(`WITT_FIGURES_OPENAI_DETAIL`, sólo familia openai: `runs._openai_detail_for`) que composite_auditor — con `low` gpt-4o cuesta 85 fijos
por imagen en `saw_figures.visual_tokens_projected`, `vision.sent.visual_tokens_projected_total` y `by_model[*].vision` por igual (antes
runs proyectaba siempre la fórmula `high` y el frozen congelaba dos cifras distintas para el mismo envío). `GET /usage += figures {n_runs_with_figures, n_figures_verified, n_figures_cited, bytes_downloaded, bytes_verified (corrector),
n_figures_cache_hit (corrector), vision_tokens_projected_by_model {model: n}, class 'PROJECTION (tokens) / MEASUREMENT (counts, bytes)'}` (app.py:1365) *(injerto de
D3: cierra el hueco HANDOFF §17.3 — M8 lo lee del servidor)*. *(F5/F8, forma real)* `/usage.figures` = `{state ∈ 'measured' | 'not-measured', n_runs_with_figures,
n_runs_figures_declared, n_runs_without_figures_usage, by_state, n_figures, n_figures_verified, n_figures_cited, bytes_downloaded (null ⇔
0 corridas declaradas), vision_tokens_projected_by_model, vision_tokens_projected_total, vision_images_by_model, n_runs_with_vision, class,
source, rule}`; su FUENTE es `usage_json` (= `frozen.token_usage`, `db.runs_usage` sólo devuelve ese blob), que F8 hizo ganar
`figures {state, n_figures, n_verified, n_cited, bytes_downloaded, bytes_verified, n_cache_hit, class 'MEASUREMENT (…)'}` — espejo de
`frozen.figures` escrito en `runs._token_usage`, SOLO con `WITT_FIGURES=1` (llave aditiva 1.12 de `token_usage`; ausente bajo
kill-switch, M.1). *(corrector)* `bytes_downloaded` = Σ bytes de las filas `verified` con `cache_hit` False (red REAL de ESTA corrida);
`bytes_verified` = Σ verified (caché incluida); `n_cache_hit` cuenta las que vinieron de caché — el nombre `bytes_downloaded` afirmaba una
descarga que en las corridas con ledger fresco (B.3) no ocurría. `by_model[reviewer].vision`
se emite SOLO para reviewers con ≥ 1 fila `saw_figures.n > 0`, multiplicado por `len(attempts)` (reenvío facturado), con llaves extra
declaradas `n_attempts_counted`, `n_rows`, `tokens_state`.

**(I) Puertas HTTP (app.py, declaradas ANTES de `/runs/{run_id}/events` :986; patrón `get_record_pdf` :962-984 y
`artifact_report` :422-428: membresía antes del filesystem).** `GET /runs/{run_id}/figures` → 401 · 404 corrida · 409
`{state, note 'no frozen record yet'}` · 409 identidad (`question_matches_run false`, misma regla que record.pdf) · 200
`{run_id, run_no, render_contract_version, state, n, n_embeddable, license_table_version, items[] (FigureItem SIN b64 NI
cache_path, + servable ∈ 'yes' | 'forbidden-by-license' | 'bytes-not-in-cache' | 'bytes-mismatch' | 'kill-switch' | 'no-bytes'
(medido al pedir: existencia + sha recalculado), url '/runs/{run_id}/figures/{sha256}')}`; registro < 1.12 → `{state
'not-instrumented (contrato < 1.12)', items []}`. `GET /runs/{run_id}/figures/{sha256}` (`{sha256}` validado `^[0-9a-f]{64}$`
→ 400) → busca el sha en `frozen.figures.items` → 404 `{state 'no such figure in this record'}` · 403 `{state
'forbidden-by-license', license {id, words_es, source}, source_url}` si `embeddable False` (ZFIN incluido) · 404 `{state
'bytes-not-in-cache', source_url, sha256, refetch 'disabled (WITT_FIGURES_REFETCH_ON_GET=0)' | 'attempted: <estado>'}` si el
archivo falta (caché efímera, Context 10) — con `WITT_FIGURES_REFETCH_ON_GET=1` UNA GET (20 s) y se sirve SOLO si sha == el
congelado, si no 409 · 409 `{state 'figure-bytes-mismatch', expected, actual}` si el sha recalculado del archivo ≠ (JAMÁS se
sirve) · 200 bytes ORIGINALES con `Content-Type` = `media_type` medido, `ETag "<sha256>"`, `Cache-Control: private,
max-age=86400`, `X-Witt-Figure-License: <id>`, `X-Witt-Figure-Sha256`, `Content-Disposition: inline; filename="<PMCID>_<fig_id>.<ext>"`.
Kill-switch → índice `state 'kill-switch WITT_FIGURES=0'`, bytes 404 `{state 'kill-switch WITT_FIGURES=0'}`. **CORS:
`CORSMiddleware(..., expose_headers=["ETag","X-Witt-Figure-License","X-Witt-Figure-Sha256","Content-Disposition"])`** (app.py:112)
*(hueco del juez 1; sin esto la webapp no lee los headers)*. Ninguna GET toca la red salvo el refetch declarado. *(F5/F8, forma real)* `expose_headers` gana una 5.ª aditiva `X-Witt-Figure-Refetch`; el
409 de identidad aplica TAMBIÉN a `/figures/{sha256}` (ADR-0044); `servable` viaja como OBJETO `{state, reason?, sha256_actual?}` y el
sobre del índice añade `frozen_state, n_verified, n_servable, servable_counts, cache {dir_source, dir_state}, class, servable_rule,
vocabulary`; el 403 fusiona `{error 'not-embeddable', state, license {id, words_es, source}, reason, source_url, sha256, id,
license_table_version}`; `embeddable` EFECTIVO al servir = congelado ∧ tabla restringida por la env de HOY (`reason 'restricted-by-env-now
(…)'`, jamás amplía); `If-None-Match` == ETag ⇒ 304; bajo kill-switch el índice CONSERVA los ítems congelados (medición) con `servable
'kill-switch'`; el refetch reutiliza `figures.fetch_figures` con UNA fig (misma costura, mismo layout). F8 retiró la costura
`app._pdf_figures_kwargs` (inspect.signature): `get_record_pdf` llama `build_pdf(rec, cache_dir=figures.cache_dir()[0], thumbs=None)` y
`record_pdf` lee `WITT_FIGURES_PDF_THUMBS` en la llamada declarando la fuente. *(corrector)* el índice mide `cache.dir_state` con
`figures.cache_dir_state(root, create=False)` — una GET jamás escribe; 'missing' es estado declarado del vocabulario (un despliegue sin
`WITT_MCP_CACHE_DIR` ya no gana `<repo>/mcp_cache/figures` vacío al primer GET: la caché perezosa de F8 también en esta puerta).

**(J) `record_pdf.py` RE-ESTRUCTURADO por TABLA: cada llave del registro con sección espejo y TRES estados con el contrato de
nacimiento CALCULADO.** *(J.1)* `SECCIONES: tuple[(key, fn)]` con las 50 llaves top-level de 1.10 + `council` (1.11) + `figures`
(1.12) = 52 entradas, y `KEY_BORN = {render_contract_version:'1.0', run_id:'1.0', user_id:'1.0', question:'1.0', measured_at:'1.0',
store_at_retrieval:'1.0', retrieval_summary:'1.0', decision_state:'1.0', fallback:'1.1', confidence:'1.1', audit:'1.0',
audit_initial:'1.6', answer_initial:'1.6', revision:'1.6', answer:'1.0', models:'1.10', alternatives_considered:'1.3',
reasoning:'1.3', agents_invoked:'1.3', plan:'1.4', plan_declared:'1.4', plan_question_matches_run:'1.4', citations:'1.1',
citations_schema:'1.7', citations_support_summary:'1.9', evidence_cited_raw:'1.7', competence:'1.9', search_ledger:'1.9',
deterministic_checks:'1.0', token_usage:'1.0', usage_raw:'1.0', bundle_identity:'1.0', question_matches_run:'1.0', thread:'1.8',
thread_context:'1.8', thread_context_skipped_reason:'1.8', thread_parent_matches_run:'1.8', thread_parent_matches_run_state:'1.8',
thread_parent_matches_run_rule:'1.8', precedent_citations:'1.8', precedent_citations_state:'1.8', origin:'1.8',
plan_parent_matches_run:'1.8', plan_parent_matches_run_state:'1.8', plan_snapshot_matches_run:'1.8',
plan_snapshot_matches_run_state:'1.8', episode_axes:'1.8', niches:'1.7', frozen_at:'1.0', closed_by:'1.0', council:'1.11',
figures:'1.12'}` (los números ≤ 1.6 los FIJA la rebanada leyendo el historial de `RENDER_CONTRACT_VERSION` en runs.py:50-100; lo
que no conste → `'contrato desconocido, declarado'` — nunca se inventa). `_tres_estados(record, key) -> ('no-instrumentado', f"NO
INSTRUMENTADO (contrato < {KEY_BORN[key]}) - el registro nacio antes; no se rellena") | ('null', <razón de `<key>_state` /
`skipped_reason` si existe>) | ('valor', v)`. **Desaparecen los literales fijos `_NOT_INSTRUMENTED` (:81) y
`_NOT_INSTRUMENTED_1_11` (0082 :277) y la prosa fija del sha (:209-213): la regla se imprime desde
`record.get("thread_parent_matches_run_rule")`.** *(F6, forma real)* los números ≤ 1.6 los FIJÓ el historial de `RENDER_CONTRACT_VERSION`
(runs.py:97-99 «1.3 = ADR-0060: +reasoning +agents_invoked +alternatives_considered»; `fallback` 1.1 por ADR-0051) — donde difieren del
borrador, manda el historial; una llave nacida en 1.0 ausente imprime «NO INSTRUMENTADO (contrato base 1.0: la llave X no consta en este
registro) - no se rellena» (no existe «contrato < 1.0»); los GRUPOS con ANCLA (`GRUPOS`/`ANCLAS_EXTRA`) colapsan en UNA línea NO
INSTRUMENTADO cuando el ancla falta (smoke_precedent ADR-0079l sigue exacto: 4 líneas «< 1.8»); `contract_of` es polimórfica (dict →
`render_contract_version`; str → `born_of(key)`); `KEY_BORN['niches'] = '1.7'` viene del borrador (el historial no lo registra: nació sin
bump), declarado. Cada `fn` llama LITERALMENTE `record.get("<key>")` (regla escrita en el
módulo: el gate (D) de la webapp mide por `PDF_ACCESS_RE`; una refactorización a `record.get(key)` genérico lo cegaría — R10).
`SERVICE_KEYS = ('consensus','ratings','ratings_masked','ratings_masking_note')` *(F6: `app._ratings_view` también fusiona
`ratings_masking_note` al enmascarar)* (las que `app._ratings_view` fusiona al leer, :976) quedan
blanqueadas del gate de cobertura *(hueco del juez 1)*. *(J.2 secciones nuevas o re-hechas, forma exacta)* IDENTIDAD Y TIEMPO —
`run_id`, `run_no` si viaja, `user_id` ('quién corrió'), `question`, `render_contract_version`, `measured_at`,
`store_at_retrieval {store_version, …}`, `frozen_at`/`closed_by`, `origin`, `question_matches_run`, `bundle_identity.sha256`
COMPLETO · ESTADO — `retrieval_summary`, `decision_state`, `episode_axes` · COMPETENCIA — `competent/not_applicable`, cada
componente `{value, gating, reason}` (incl. `council_uncovered_must` 1.11), `conjunction`, `self_report` aparte, `decision`,
`config`, `module_version`, `skipped_reason` · BÚSQUEDA — `plan` (familias con gate, `directives_state`), `plan_state`,
`config_source`, y UNA FILA POR FUENTE por ronda desde `search_ledger.rounds[].sources[]`: `round | family | status | n_found
(null = 'no midió') | n_new | elapsed_s | cache_hit | label | query_sent | detail/error`, `stop_reason` · FALLBACK íntegro
(`fb_meta` completo, `council` 1.11) · MODELOS — `generation(+_source)`, `table_version/as_of`, `roles{}` (rol · pedido · fuente ·
familia · api), `ran` por pasada (requested/reported/relation/thinking_state), `panel_signature`, `rule` · REVISIÓN ADVERSARIAL
(íntegra: filas con family/api/api_source/reviewer_source/max_tokens, `attempts[].error_kind`, `citation_support`,
**`saw_figures` en palabras y `figure_readings` con la placa JUICIO**) · CUÓRUM — `audit.quorum` íntegro (n_valid/min,
familias y lentes presentes, `*_gating` → 'APAGADA' cuando 0|1, `failed[]`, `rule` verbatim), `families_valid`,
`lenses_valid`, `panel_duplicate_models`, `panel_origin`, `panel_source.council_hook`, `judge_retries` · RESPUESTA (incl.
model/model_source/relation) · CONFIANZA · EVIDENCIA CITADA — por cita `[n] kind: id · nota · soporte: <support_state | NO
INSTRUMENTADO (contrato < 1.9)> · pertinente: <objeto 1.11 en palabras>` y para `kind 'figure'` la sub-línea `figura: bytes
<verified | not-fetched (…) | mismatch> · contenido: juicio del panel | no evaluado` · ESQUEMA DE CITAS — los CINCO literales de
`citations_schema.source` en CINCO frases DISTINTAS (`list` → 'lista tipada (N crudas / M válidas)' · `string-reparsed` →
'llegaron SERIALIZADAS y se re-parsearon (procedencia declarada)' · `string-unparseable` → '0 citas DERIVABLES — el sintetizador
citó en texto no tipable; NO es "citó 0"' · `absent` → 'el bloque llegó AUSENTE — no es "citó 0"' · `unsupported-type` → 'tipo no
soportado (<raw_type>) — declarado, no forzado'), `n_raw/n_valid`, `evidence_cited_raw` plegado ≤ 600 chars verbatim + `raw_len`;
`citations []` con `citations_schema` AUSENTE → 'medido-vacío o NO INSTRUMENTADO (contrato < 1.7): no distinguible, declarado' ·
RESUMEN DE SOPORTE — los 5 peldaños SIEMPRE (entero | 'null: no midió'), `state`, `ladder_rule`, `pertinent`, `figure_citations`
(1.12) · **FIGURAS (1.12)** — cabecera `state · n_figures · n_verified · n_embeddable · n_unknown_license · mecanismo ·
license_table_version · presupuesto used/total (over_budget) · caché dir_source/evicted_n`, y por figura `id · label · licencia en
PALABRAS ('CC BY 4.0 — embebible (leída de ali:license_ref)' | 'CC BY-NC 4.0 — NO embebible: caption + enlace' | 'licencia
desconocida — NO embebible' | 'CC BY (prosa sin URL) — embebible por WITT_FIGURES_PROSE_LICENSE=1' | 'ZFIN: sólo enlace, jamás
bytes') · sha256 (16) · <w>×<h> (dims_match) · bytes_state · vista por N lentes: JUICIO · citada como [n…] · caption ≤ 400`;
**MINIATURA** sólo si `embeddable True` (congelado) ∧ la licencia sigue permitida por `WITT_FIGURES_EMBED_LICENSES` de HOY
*(corrector: la misma puerta que el 403 de `GET /figures` — `record_pdf._embeddable_now` = congelado ∧ `figures.license_flags(id,
cfg)[0]` con la `cfg` leída EN LA LLAMADA; si la env de hoy restringe: 'miniatura: embebible al congelar; NO embebible HOY (licencia
<id> restringida por WITT_FIGURES_EMBED_LICENSES …) - caption + enlace' y la licencia en palabras lo dice; `THUMB_RULE` lo declara —
antes el PDF, canal único de salida (ADR-0073), embebía lo que el GET negaba)* ∧ archivo en caché ∧ sha recalculado == sha ∧
`WITT_FIGURES_PDF_THUMBS=1`
(`pdf.image(BytesIO)`, ancho ≤ 60 mm constante; tope 12 miniaturas por PDF y **PDF ≤ 8 MB: al acercarse, las siguientes degradan a
'miniatura omitida por tope' + enlace** *(injerto de D3)*; `try/except` → palabras + `thumb_error`); si no: palabras + `source_url`
· HUECOS · ALTERNATIVAS · RAZONAMIENTO — `reasoning {framework_applied (class 'self-report'), structural_frameworks}` · AGENTES —
`agents_invoked[]` una fila por agente (`agent · status · invocation_id · reason · evidence_generated`), `skipped-ad-hoc` marcado ·
PLAN — `plan_declared`, `plan_question_matches_run`, `plan.judgment` (planner con model/model_source/provenance, agentes
aplicables, nichos predichos, `council_state` 1.11), `plan_parent_matches_run(+_state)`, `plan_snapshot_matches_run(+_state)` con
glosa por estado · GATE DETERMINISTA — `deterministic_checks` llave por llave (`pass`, `admissible`, `reasons[]`,
`identifier_report` conteos, `pass1_admissible`, `positive_claim_requires_citations(+_state)`, `competence_gate`, `thread`,
`parent_identifier_leak`, `disjoint_series(+_state)`, `attestation_identifier_leak(+_state,_rule)` 1.11, `council` 1.11,
**`figures` 1.12 con sus 5 predicados y `gating` en palabras ('GATEA' | 'informativo')**) · NICHOS — `catalogo`/`panel`/coverage,
dos fuentes sin fundir · INVESTIGACIÓN (ADR-0079, regla del sha LEÍDA de la llave; 'regla no declarada en este registro' si
falta) · PRECEDENTE en letras · CONSEJO DE CRITERIO (1.11, forma (J) de 0082: absorbe `_section_consejo`) · CONSUMO —
`token_usage` íntegro: totales, `by_model` con USD [E] y `price_state`, `by_stage` (TODAS las etapas con `model/model_source/state`
y los tres estados de `plan`), **`by_stage.panel.by_model` por reviewer (in/out + `vision` proyectado si existe, etiquetado
PROYECCIÓN)**, `by_stage_sum_matches_by_model`, `missing_price_models`, `cache` 1.11, `cost_class`; `usage_raw.passes` por
etiqueta + `panel_total` · CONSENSO (conteos) · pie (canal único + saneo latin-1). El PDF jamás toca la red. *(J.3)*
`record_pdf.pdf_sections_cover(frozen_keys, service_keys=SERVICE_KEYS) -> {missing[], extra[]}` y `record_pdf.contract_of(key)`
son la API del gate (K). *(J.4)* `build_pdf(record, compress=True, cache_dir=None, thumbs=None, now=None, pdf_max_mb=None)` *(F6: `now` fijo ⇒ bytes deterministas
(K.8); `pdf_max_mb` tope forzable (K.6); el tope es un presupuesto de BYTES de imagen = pdf_max_mb·MiB − 512 KB de reserva)* — kwargs opcionales para
smokes; `get_record_pdf` (app.py:963) pasa `cache_dir=figures.cache_dir()` y `thumbs` desde env. *(J.5 doble dueño)* F6 arranca
sobre `contract-1.11-frozen` (record_pdf.py con `_section_consejo`) y absorbe esa sección en `SECCIONES` eliminando AMBOS
literales fijos *(F7: alineado a ca9a03d — 0082 YA aterrizó (ca9a03d = `contract-1.11-frozen`): la rama condicional «si 0082 no ha
aterrizado al arrancar F6, F6 implementa la sección council desde (J) del borrador 0082 y F8 reconcilia» NO aplica; F6 absorbe
`_section_consejo` :308 y `_council_state_gloss` :298 tal como están en el árbol)* — orden de aterrizaje EXPLÍCITO en el plan, no un
riesgo *(injerto de D2)*.

**(K) Gate de COBERTURA del PDF — backend (`smoke_record_pdf.py`, NUEVO) y segunda fuente en la webapp.** (1) Parsea las llaves
top-level del literal `frozen = {` + `frozen["k"] =` de runs.py con la MISMA técnica que `parity_check.frozen_keys` (:232-276,
copiada literal) y exige `set(frozen_keys) - SERVICE_KEYS ⊆ {k for k,_ in SECCIONES}` y `{k in SECCIONES} - frozen_keys ⊆
{'council','figures'}` sólo cuando el frozen no los trae por contrato — con un frozen 1.12 REAL (`execute_run` con stubs, patrón
smoke_run_pipeline) igualdad EXACTA; (2) extrae los `record.get("k")` de record_pdf.py con `PDF_ACCESS_RE` copiada literal
(:439-441) y exige igualdad con las llaves del frozen (0 huecos) — el MISMO cálculo que `check_pdf` hará; (3) rutas anidadas
medidas en los BYTES del PDF sin comprimir (`compress=False`, patrón :1119-1145): `audit.quorum`, `token_usage.by_stage.panel.by_model`
(cada reviewer con in/out), `search_ledger.rounds[].sources[]` (una fila por fuente), `citations_schema.source` × 5 → 5 textos
DISTINTOS y NINGUNO contiene 'no constan (contrato pre-1.1)', `citations_support_summary.by_state`, `council.ledger/rounds/coverage`
(fixture 1.11 REAL cuando 0082 esté; sintético declarado hasta entonces), `figures.items[]`; (4) tres estados por llave con el
born CORRECTO: quitar `models` → b'NO INSTRUMENTADO (contrato < 1.10)'; `competence` → '< 1.9'; `thread` → '< 1.8'; `council` →
'< 1.11'; `figures` → '< 1.12'; `None` + `_state` → 'null declarado — razón: <state>'; valor → impreso; (5) la regla del sha
impresa == `record['thread_parent_matches_run_rule']` (dos strings distintos → dos PDFs distintos; ausente → 'regla no declarada
en este registro'); (6) figuras: fixture CC BY con caché TMP → N `/Subtype /Image` == min(n_embeddable, 12) y 'CC BY' +
'embebible' + sha[:16]; fixture NC → 0 imágenes + 'NO embebible' + 'caption + enlace'; unknown → 'licencia desconocida'; archivo
alterado → 0 imágenes + 'bytes: mismatch'; caché vacía → 'bytes no en caché'; `WITT_FIGURES_PDF_THUMBS=0` → 0 imágenes; tope 8 MB
forzado a 0.05 MB → miniaturas degradadas a enlace; 'vista por 2 lentes: JUICIO'; (7) checks ADR-0073 a–f siguen verdes;
(8) determinismo: dos `build_pdf` del mismo registro con fecha fija → bytes iguales; (9) `urlopen` bloqueado y contado = 0.
**Webapp:** `parity_check.check_pdf` gana `record_pdf.SECCIONES` como SEGUNDA fuente — *(corrector)* con la regex ANCLADA
`^SECCIONES\s*=\s*\($` (`re.M`) y luego `("<key>", "<sección>")` hasta el paréntesis de cierre a profundidad 0: una regex SIN anclar
casa antes `ORDEN_SECCIONES` (u otro texto) y devuelve 0 llaves (trampa MEDIDA en smoke_record_pdf: ≥ 2 sitios sin anclar, 52 llaves
anclada); `record_pdf.SECTION_KEYS` es la fuente programática equivalente y el comentario del módulo ya no contiene el texto del
literal —: OK sólo si ambas fuentes concuerdan; `PDF_NESTED += ('search_ledger.rounds[].sources[]', …),
('citations_schema.source', …), ('citations_support_summary.by_state', …), ('council.ledger', …), ('figures.items[]', …)`; las 23
líneas `[pdf]` se QUITAN de `parity_debt.json` cuando el gate reporta 0 huecos y 'DEUDA SALDADA' para cada una.

**(L) Contrato ADITIVO 1.12 (`RENDER_CONTRACT_VERSION = "1.12"`, runs.py:50) apilado sobre 1.11 — forma exacta.**
**`frozen.figures`** (llave top-level NUEVA, SIEMPRE presente en ≥ 1.12) = `{state ∈ 'attached' | 'no-path-b' |
'no-papers-with-xml' | 'kill-switch WITT_FIGURES=0' | 'error: <tipo>: <msg≤120>', module_version 'fig-1', parser_version
'jats-fig-1', license_table_version 'lt-1', license_table {<id>: {embed, panel_view, fetch_bytes, words_es}}, license_table_rule,
license_table_env_ignored [], mechanism 'supplementaryFiles-zip', cache {dir_source ∈ env | default | injected, dir_state ∈ writable |
read-only | missing, ttl_days, cache_max_mb, evicted_n}, budget {total_s, used_s, over_budget}, caps {max_papers, max_per_paper,
max_per_run, max_per_lens, max_image_mb, request_b64_mb, zip_max_mb, caption_chars — cada uno {value, source ∈ 'env:<VAR>' |
'default-unset:<VAR>' | 'default-invalid-env:<VAR>' | 'constant (ADR-0083)'}}, n_papers_eligible, n_papers_selected,
n_papers_with_xml, n_figures, n_with_caption, n_fetched, n_verified, n_not_fetched, n_error (corrector: Σ 'error: …'; n_not_fetched = SOLO
'not-fetched (…)'; n_figures = n_verified + n_mismatch + n_not_fetched + n_error + filas 'never' — 0 hoy), n_mismatch, n_embeddable, n_panel_view,
n_unknown_license, n_cited, zfin_figures_state 'not-available (…)', selection {rule 'cited-by-answer first, then paper
selection_rank, then document order', n_sent_to_panel_by_lens {<lens>: int}}, vision {state ∈ 'sent' | 'kill-switch
WITT_FIGURES_VISION=0' | 'no-eligible-figures', lenses [], lenses_source, rule (FIGURE_READING_RULE verbatim), openai_detail,
sent {n_panels, n_attempts_with_images, bytes_b64_sent_total, visual_tokens_projected_total, tokens_state, rule}, cost_projection
{…(H)…}, rule_state, openai_chat_form_state, max_per_lens, max_image_mb, request_b64_mb, panels [{state, selection, delivered, n_figures,
sha256s}], delivery {audit_accepts_figures, audit_accepts_vision_lenses}, vocabulary, class} *(F4: `vision.state` gana los prefijos
`'tool-unavailable ('` y `'error: '`; `selection += n_sent_by_lens_rule` — n_sent_to_panel_by_lens = sha256 DISTINTOS entregados a esa lente
en TODOS los paneles; el `papers[]` de `figures.attach` NO se congela — F4 lo quita antes de congelar)*,
items [FigureItem], kill_switch? {WITT_FIGURES: '0', declared_exceptions ['render_contract_version','figures',
'deterministic_checks.figures']}}`. **`FigureItem`** = `{id '<PMCID>#<fig_id>', pmcid, evidence_id (del paper), fig_id, label:
string|null, caption (≤ caption_chars), caption_truncated, caption_state ∈ present | absent, caption_lang: string|null,
graphic_href, source_url, media_type ∈ image/jpeg | image/png | image/gif | image/webp | null, mime_from_extension (SIEMPRE, string|null — F1), bytes: int|null,
sha256: string|null, sha256_short (12), dims_declared {original {w,h}|null, scaled {w,h}|null}, dims_measured {w,h}|null,
dims_source 'header' | null, dims_match: bool|null, license {id, source, evidence_text, url, rule_no, version, scope, conflict?},
embeddable, panel_view, bytes_state (B.2), raw_ref (source-pointer) | null, cache_path_rel: string|null, fetched_at: iso|null,
cache_hit: bool|null, cited_by_answer [n…], seen_by_lenses [<lens>…], delivered_to_synthesizer: bool (= caption_state 'present' por construcción: única proyección `figures.project_for_prompt`),
caption_in_excerpt: bool|null (F1: substring normalizado en `paper.text_excerpt`), class 'measurement
(source-pointer: bytes observed from source; sha256 recomputed on read)'}`. **`bundle.path_b.papers[].figures`** (bundle_json, no
frozen) = `{state, n, items [FigureItem], ledger {mechanism, http_status, zip_bytes, elapsed_s, n_entries, n_extracted, n_missing,
error?}}`; ausente con kill-switch. **`citations[].kind` enum += 'figure'**; `citations[] += figure_verification {bytes, content,
figure_id, kind_reported}` en toda cita-figura por el superset de (E) *(corrector)*. **`citations_support_summary += figure_citations {…}`** (E; ausente con kill-switch).
**`deterministic_checks.figures`** (F) y `deterministic_checks.reasons[]` con `'hard predicate failed: figure_id_resolves |
figure_sha_matches | figure_only_not_asserted'`. **`audit.panel[] += saw_figures {…}`, `figure_readings?`, `figure_readings_class?`,
`figure_readings_dropped?`; `audit += vision {…}`** (G.6; también en `audit_initial` — *corrector: `AUDIT_INITIAL_QUORUM_KEYS += 'vision'`,
copiada sólo si audit() la trae; antes el contrato lo prometía y `audit_initial` no la llevaba*; `audit.panel[] += citation_support_vision_informed?`
— *corrector*, sólo en la fila con `citation_support`; TODO ausente con kill-switch).
**`VERDICT_TOOL += figure_readings`** opcional. **`token_usage.by_stage.panel.by_model[*] += vision {…}` y `token_usage.figures {state, n_figures, n_verified, n_cited,
bytes_downloaded, bytes_verified, n_cache_hit, class}` (F8: espejo para `/usage`; *corrector*: bytes_downloaded = verified ∧ ¬cache_hit)** (H; ausentes con
kill-switch). **`thread_context.previous_audit.findings[] += from_vision_lens?`** (sólo cuando el padre corrió con figuras) y
**`previous_audit.n_from_vision_lens?`** *(corrector, D.4 entre turnos)*. **`revision.findings_used[].from_vision_lens`**, **`stage.revision.start
+= n_from_vision_lens`**, **`stage.deterministic_gate += figures_state`** (F4; el corrector los lleva a la lista «tipar y pintar»). **`agents_invoked += {agent 'figures (lib/figures.py — JATS parser + fetch by sha + license gate)', status 'invoked' |
'not-applicable', invocation_id 'figures:<n_verified>/<n_figures>', reason? ('no path_b' | 'no full-text XML among selected
papers'), evidence_generated ['parsed:<n>', 'verified:<n>', 'embeddable:<n>', 'lenses:<csv>', 'synthesizer:captions-only']}`**
(ausente con kill-switch: `frozen.figures.state` lo dice). **`SYNTH_TOOL.description`** (D.2) y **`_LENS_CHARGES`** de dos lentes
+ `FIGURE_READING_RULE` (prompt, no registro). **Vista `_run_view`/`epistemic_summary_json`** (derivado al congelar, db.py:92; NO
es el frozen) += `figures_state: string|null, figures_n_verified: int|null, figures_n_cited: int|null` (F4: `figures_state` es SIEMPRE string en ≥ 1.12 — incluido el literal kill-switch —; sólo los conteos son null =
< 1.12 o
kill-switch; 0 = medido). **Eventos** (C) + `stage.audit.judge += {figures_sent int, figures_sha256 []}` (runs.py:2299) y
`stage.deterministic_gate += {figures_state}`. **HTTP** (I) + `/usage.figures` (H). **`fetch_paper._normalize_hit += license`**
(A.2). **Vocabularios CERRADOS exportados para el gate de paridad** (patrón `plan_state_in_vocabulary`): `figures.LICENSES`,
`LICENSE_TABLE`, `BYTES_STATES_EXACT/PREFIXES`, `FIGURES_STATES_EXACT/PREFIXES`, `SERVABLE_STATES`, `composite_auditor.VISION_LENSES`,
`SAW_FIGURES_DETAILS`; viajan en `frozen.figures.vocabulary`. **Históricos: NADA se recalcula ni se backfillea** — registros < 1.12
no ganan `figures`; webapp y PDF los leen 'NO INSTRUMENTADO (contrato < 1.12)'; etiqueta `contract-1.12-frozen` tras el
integrador; `gen_fixtures.py CONTRATO = "1.12"` (witt-webapp/tools/gen_fixtures.py:161).

**(M) Invariantes operativos y kill-switches.** *(M.1 `WITT_FIGURES=0`, default 1)* no se parsea ni baja nada, los papers NO
ganan `figures`, el `user_text` del sintetizador es el de 1.11 BYTE A BYTE (la `description` del tool es la excepción declarada
del PROMPT), el panel no recibe imágenes ni `saw_figures`/`audit.vision`, ninguna cita gana `figure_verification`, `by_model[*]`
no gana `vision`, `agents_invoked` no gana fila, `GET /figures/{sha}` 404; **el frozen es igual al 1.11 del MISMO fixture (json
sort_keys, keyset Y valores) salvo EXACTAMENTE `{render_contract_version, figures {state, kill_switch}, deterministic_checks.figures
{state}}`** — cualquier otra diferencia falla listando el path *(F4: bajo kill-switch `figures` conserva la FORMA BASE de
`figures.attach` — conteos 0, cache None, sin `vision` — con `state` + `kill_switch`: la excepción se lee como «lo significativo» y la
webapp tipa UNA forma; `token_usage.figures` tampoco existe; el smoke lo mide como diff de paths == ∅ contra la corrida ENCENDIDA del
mismo fixture tras quitar las aditivas 1.12 y la identidad de corrida)* *(síntesis: el ganador prometía 3 y emitía 5; la enumeración
mínima se hace verdad no emitiendo las otras dos bajo kill-switch)* *(corrector: `audit.panel[].citation_support_vision_informed` es
aditiva 1.12 — ausente bajo kill-switch; el smoke la resta antes del diff junto a las demás aditivas)*. Un `stage.figures.summary {state
'kill-switch …'}` (evento, no frozen). *(M.2 `WITT_FIGURES_VISION=0`)* figuras observadas siguen (captions al sintetizador, bytes en caché, GET vivo, escalera
y predicados iguales) pero NINGUNA lente recibe imágenes: `saw_figures.detail 'kill-switch WITT_FIGURES_VISION=0'`,
`figures.vision.state` lo dice. *(M.3 `WITT_FIGURES_PDF_THUMBS=0`)* palabras aunque la licencia permita. *(M.4)* Toda env se lee
EN LA LLAMADA con `figures.env_config()` tolerante (vacía/basura → default con `source`); toda env = reinicio; los placeholders
van al compose (bloque ADR-0083 tras el bloque 0082) y `models.ENV_TABLE` gana las filas (el check env ⊆ compose ∩ README de
`smoke_models` las cubre). *(M.5 smokes offline y PORTABLES)* `urlopen` bloqueado y contado = 0 en todos; `mcp_cache` real
byte-idéntico antes/después (snapshot); caché de figuras de los gates en TMP; **los 2 XML golden (PMC11379296 CC BY,
PMC11647118 CC BY-NC) se COPIAN a `fixtures/figures/` (byte-idénticos; 127 KB + 215 KB) y el golden de los 12 se degrada a 'NO
MEDIDO (mcp_cache ausente)' cuando faltan — un clon limpio o el contenedor de Dokploy no tienen `mcp_cache/`** *(injerto de
D2/D3; el ganador fallaba en claro)*; el zip fixture `PMC11379296-figures.zip` REDUCIDO = SOLO los 9 `g00N.jpg` (1.27 MB; CC BY 4.0
leído del XML; `MANIFEST.json` con los 9 sha256 medidos hoy y la atribución tomada de `raw_paper_PMC11379296_20260613.json.title`,
no tecleada) y `PMC11647118-figures-SYNTHETIC.zip` con PNG 1×1 bajo los hrefs `fx1.jpg, gr1..gr5.jpg` (licencia NC: el repo NO
redistribuye sus bytes; el gate mide licencia y sha, no contenido). *(F1/F8)* el zip NC sintético trae además `gr9.gif` (thumb SIN su jpg) para
`'href-not-in-zip; thumb-available'`; los 9 JPG reales (1.27 MB, CC BY 4.0, atribución leída de `raw_paper_*.json` al MANIFEST) quedan bajo
git en `fixtures/` (Emmanuel confirma el binario — el ADR lo prevé como «zip CC BY real reducido»); durante la obra apareció
`<repo>/mcp_cache/figures/` VACÍO en el worktree (gates sin `WITT_MCP_CACHE_DIR` + `cache_dir_state` que creaba) — F8 lo retiró y cerró la
causa (caché perezosa, B.3); `smoke_figures_http`/`smoke_record_pdf` crean su raíz FRESCA con `mkdtemp` DENTRO de `WITT_MCP_CACHE_DIR` y
la borran (una raíz reutilizada haría cache-hit y rompería las precondiciones). *(M.6)* Nada binario en el blob: assert `b64 not in
frozen_record_json and not in bundle_json` (D.1). *(M.7)* La regla §7 vive en cuatro sedes (D.5). *(M.8)* Límites del proveedor
declarados como invariantes de configuración: `MAX_PER_LENS ≤ 20` (clamp) y `MAX_IMAGE_MB ≤ 7` (7 MB crudos ≈ 9.3 MB b64 < 10 MB)
— fuera de rango → default declarado.

**(N) Lo que NO se hace y por qué NO es deuda** *(injerto de D3)*. (a) Nada de OCR ni extracción de cifras de la imagen: es lo que
§7 prohíbe. (b) El sintetizador jamás ve bytes: decisión tomada, estructural (D.1). (c) ZFIN sin bytes: «permission only to
display»; sin fuente de ZDB-FIG hoy (Context 13) — estado declarado, ADR posterior si la demanda medida lo pide. (d) Sin Files API
de Anthropic: una corrida manda ≤ 12 imágenes ≤ ~250 KB en b64 (≈ 1.7 MB ≪ 32 MB) a dos lentes; el reenvío se MIDE (H) y la
Files API añade estado remoto sin ahorro medible aquí. (e) Sin espejo MinIO de figuras públicas: source-pointer + sha es la política
'hybrid: not mirrored' de `raw_store.fetch_url` (:104-122); ADR-0086 cubre lo atestiguado. (f) Sin `<supplementary-material>`
(81 en los 12 XML) ni tablas del zip: otra evidencia, otro ADR. (g) Sin `.tif/.ome` de la DATA INAMOVIBLE (brief §7). (h) Sin
visión en correctness/overclaim (hecho cumplir por `VISION_LENSES_MAX = 2` — corrector: una env o un llamador con más lentes cae al default declarado). (i) Sin backfill de registros < 1.12. (j) Sin endpoint de miniaturas server-side (una puerta, el
original; el cliente reduce). (k) Sin derivado LANCZOS ni segundo sha (Context 2). (l) Sin `?includeInlineImage` ni href directo
por default (no verificados; LG1). (m) Sin familia `'figure'` en `SEARCH_DISPATCH` (search_harness.py:103): las figuras no son
una fuente, vienen adheridas a papers (O). (n) Sin detección de idioma del caption: `caption_lang` sólo si la fuente lo declara.
(o) Sin etapa `figures` en `TOKEN_STAGES`: no gasta modelo.

**(O) Costura con ADR-0082 (apila sobre 1.11).** (1) *(F7: alineado a ca9a03d — no hay rebase pendiente: TODAS las rebanadas arrancan
ya sobre `ca9a03d` = `contract-1.11-frozen`; `runs.py` 4 463 líneas, `app.py` 2 682, `record_pdf.py` 679.)* Las formas 1.11 sobre las que
se apila: `composite_auditor` (`tools=None` :583-584 @ ca9a03d; `user_content=None` se apila sobre ella), `verify_output` (`support_state_for(...,
council_pertinence=…)` — el índice cambia, la firma no), `runs.py` (+1397 líneas 0082; `TOKEN_STAGES` con `council_r*` intacto),
`app.py` (8 rutas 0082; las 2 de 0083 se declaran junto a `/record.pdf`), `models.py` (+152; la columna `vision_tier` es aditiva;
`smoke_models` golden se actualiza), `record_pdf.py` (J.5). (2) `council.py` (@ ca9a03d :110 / :1434-1438 / :1589 — F7) declara `evidence_kind
'figure'` → `'unsatisfiable-by-harness (evidence_kind figure — ADR-0083)'`: este ADR NO abre familia; SOLO si 0082 está mergeado a la
rama principal al integrar (hoy vive commiteado en `feat/adr-0082-consejo` @ ca9a03d, sin merge — F8 lo decide y lo declara — DECIDIDO 2026-09-16: `master` @ ac01b7a NO contiene ca9a03d (`git merge-base --is-ancestor` = no; 0082 vive
sólo en `feat/adr-0082-consejo` y apilado aquí), así que el literal NO cambia y la costura queda declarada; `record_pdf` ya imprime
`figures_available_n` si algún día viaja en `coverage_after_search`), F8 cambia el literal a `'satisfiable-via-paper-figures (ADR-0083; no dedicated family)'` y `coverage_after_search`
gana la llave aditiva `figures_available_n` (= `frozen.figures.n_verified`); si no, la costura queda declarada en Consequences y
la sección CONSEJO del PDF imprime 'NO INSTRUMENTADO (contrato < 1.11)' — correcto. (3) El consejo recibe la MISMA proyección
sin bytes que el sintetizador (`_compact_evidence`). (4) `_evidence_ids` += figuras (D.3) para que los votos de cobertura no se
anulen. (5) `config_history` gana filas `first-boot-snapshot` para `figures.enabled`/`figures.vision` (`SNAPSHOT_FIELDS`
models.py:226 — @ ca9a03d :323; `snapshot_extra` runs.py:2178 — @ ca9a03d :2593) — declarado, patrón 0082 L.2(ii). *(F3/F4, forma real)* `figures.enabled` /
`figures.vision` se derivan DENTRO de `models.snapshot` (`SNAPSHOT_FIELDS` 35, leyendo `WITT_FIGURES`/`WITT_FIGURES_VISION` con fuente);
`runs.snapshot_extra` NO gana llaves (models rechaza duplicados en `extra_ignored`).

## Consequences

- **Contrato: `render_contract_version` sube a "1.12"** — todo aditivo (lista en (L)). `citations[].kind` gana el literal
  `'figure'` (el enum del tool y la union TS); ninguna otra llave cambia de dominio. `FALLBACK_TRIGGERS` intacto (gate (E) sin
  cambio). Históricos sin backfill.
- **La webapp debe tipar y pintar** (`witt-webapp/src/api/types.ts`, todo `?`; tres estados en lo nuevo): **(1)** `Citation.kind |=
  'figure'` (types.ts:997-1027) y `Citation.figure_verification?: {bytes: BytesState | 'not-a-figure' (corrector: la union `BytesState` de (2)
  — exactos `'verified' | 'mismatch' | 'not-requested (kill-switch)' | 'never (zfin-display-only)'` + prefijos `not-fetched (${string})` y
  `error: ${string}`), content: 'panel-judgment' | 'not-evaluated' | (string & {}), figure_id: string | null, kind_reported?: string}`;
  `CitationsSupportSummary.figure_citations?: {n, n_verified_bytes, n_not_fetched, n_error, n_mismatch, n_unresolved, n_other,
  n_figure_shaped_other_kind}` *(corrector: `n_not_fetched` ya NO incluye los `'error: '`)*. **(2)** `LicenseId` (union CERRADA = `figures.LICENSES`), `FigureLicense {id,
  source, evidence_text, url, rule_no, version, scope, conflict?}`, `FigureItem` (forma EXACTA de (L)), `FiguresBlock`
  (`FiguresState` por exacto + prefijo `'error: '`; `BytesState` por exacto + prefijo `'not-fetched ('`),
  `RegistroCongelado.figures?`, `DeterministicChecks.figures?` (5 predicados con `gating`), `PanelRow.saw_figures?`,
  `PanelRow.figure_readings?`, `figure_readings_class?`, `figure_readings_dropped?`, `AuditBlock.vision?`,
  `ByStagePanelByModel[reviewer].vision?`, `RunView.epistemic_summary.figures_state? / figures_n_verified? / figures_n_cited?`,
  `FiguresIndex` (GET /figures), `UsageReport.figures?` (+ `bytes_verified`, `n_figures_cache_hit` — corrector), payloads `StageFiguresPlan | Paper
  | Figure | Summary` (`Summary.n_error` — corrector), `StageAuditJudge += figures_sent?, figures_sha256?`. *(corrector — llaves que el
  código YA emitía y la lista no nombraba)* **`TokenUsage.figures?: {state, n_figures, n_verified, n_cited, bytes_downloaded, bytes_verified,
  n_cache_hit, class}`** (espejo F8 en el frozen/`usage_json`, distinto de `UsageReport.figures`; Hoja Consumo por corrida, bloque APARTE del
  medido) · **`RevisionFinding.from_vision_lens?: boolean`** (types.ts:1158-1165 es estricta; placa «hallazgo de lente que VIO imágenes =
  juicio» en la Hoja de revisión) — `thread_context.previous_audit.findings[]` la lleva TAMBIÉN cuando el padre corrió con figuras y
  `previous_audit.n_from_vision_lens?` viaja · **`RevisionStartPayload.n_from_vision_lens?`** y **`DeterministicGateEventPayload.figures_state?`**
  (types.ts:2377 tipa `DeterministicChecks`; Traza) · **`PanelRow.citation_support_vision_informed?: boolean`** · **`AuditBlock.vision?` también en
  `audit_initial`** · **`FiguresBlock.n_error`** · **`DeterministicChecks.figures.figure_only_not_asserted += n_non_figure_citations_resolved,
  n_non_figure_citations_delivered, n_non_figure_citations_unresolved, figure_citations_same_paper[] {id, same_paper_text_citation},
  n_figure_citations_without_same_paper_text`** · `vision.lenses_source` puede llevar el sufijo `' (>2 lenses)'` (string, no union cerrada) ·
  `FigureItem` sin cambio. **(3)** `client.ts`: `figurasDeCorrida(runId): Promise<FiguresIndex>` y
  `bytesDeFigura(runId, sha256): Promise<{ok: true, url: string, license: string, etag: string} | {ok: false, status: 400 | 401 |
  403 | 404 | 409, detail: unknown}>` — fetch con bearer → `URL.createObjectURL(await res.blob())` (patrón `descargarRegistroPdf`
  client.ts:306-319); **`URL.revokeObjectURL` al desmontar el componente** *(hueco del juez 1: 12 blobs vivos por render)*; NUNCA
  `<img src="/runs/…">` directo. **(4) Hoja (M4) fila de cita `kind 'figure'`** (`hoja-cita` Hoja.tsx:2440-2451): `[n] <palabra-
  máquina PMC…#fig> · figura · <label>` + miniatura vía blob SOLO si `embeddable` y el GET dio 200 (alt = caption ≤ 200) · 403 →
  placa 'NO embebible por licencia: <words_es> — caption + enlace a source_url' · 404 bytes-not-in-cache → 'bytes no en caché del
  servidor (caché efímera) — sha <12> declarado, enlace' · 409 → 'BYTES NO CUADRAN con el sha congelado — no se muestra' ·
  `figure_verification` en palabras ('bytes: verificados por sha' | 'no bajados (<razón>)' | 'NO CUADRAN'; 'contenido: JUICIO del
  panel' | 'no evaluado') · licencia SIEMPRE en palabras con la fuente de la regla ('CC BY 4.0 — leída de <ali:license_ref>') ·
  sha corto (12) con title = sha completo · 'vista por N lentes (<nombres>): JUICIO — el sintetizador sólo leyó el caption' desde
  `seen_by_lenses` (0 → 'ninguna lente la vio'); `SoporteDeCita` (:4604) NO cambia de peldaños (el caption es el pasaje);
  `Visuales.CitasPorTipo.ORDEN_KIND += 'figure'` tras 'paper' (:245). **(5) Hoja Entrada NUEVA `clave="figuras"`** (tras
  `busqueda`, :450): ausente → 'NO INSTRUMENTADO (contrato < 1.12)'; `state ≠ 'attached'` → literal por vocabulario en palabras
  ('kill-switch', 'sin Ruta B', 'sin XML de texto completo', 'error: …'); valor → cabecera (n_figures / n_with_caption / n_verified
  / n_embeddable / n_unknown_license, cada uno [M]; mecanismo; presupuesto used/total con `over_budget` en ámbar; caché
  `dir_source`/`dir_state`/`evicted_n`; `license_table_version`; `zfin_figures_state` literal; `kill_switch.declared_exceptions`)
  + tabla `hoja-figuras-tabla` UNA FILA por ítem (`data-evidence-id`): id · label · caption plegado · licencia (palabra + literal +
  source + `conflict` en ámbar) · embebible (sí/no + porqué) · sha 12 · bytes · dims medidas vs declaradas (`dims_match` ✓/✗/no
  consta) · `bytes_state` por vocabulario (`not-fetched (…)` gris, `mismatch` rojo) · `cache_hit` · 'entregada al sintetizador'
  · 'vista por' lentes · 'citada como [n…]' + bloque VISIÓN ('lentes con visión: …', `rule` verbatim, `sent` {n_panels,
  n_attempts_with_images, bytes} [M], `cost_projection` etiquetada PROYECCIÓN con fórmula y fuente). **(6) Hoja `GateDeterminista`**
  (:4805): bloque `figures` con los 5 predicados en filas, `gating` en palabras ('GATEA' | 'informativo'), `unresolved_ids[]`,
  `mismatches[]`, `numerals_unsupported[]` por cita, `n_marker_absent`, `state` por vocabulario. **(7) `PanelJueces`**
  (Visuales.tsx:478): por juez 'vio N figuras (sha…) por <api> · <visual_tokens_projected> tokens de visión [E]' o el `detail`
  glosado ('lente sin visión' | kill-switch | 'sin figuras elegibles' | 'modelo sin visión en tabla' | 'forma de API no
  verificada'); `figure_readings[]` como lista con la placa fija 'JUICIO DEL JUEZ SOBRE LA IMAGEN — no es medición; nunca entra al
  gate ni a la compuerta' y `consistent_with_caption` en palabras; `figure_readings_dropped` → 'N lecturas descartadas'. **(8) Hoja
  Consumo** (`hoja-consumo-panel-por-modelo` :6419): por reviewer 'visión: N imágenes · ~T tokens [E] (proyección por fórmula del
  proveedor; ya incluidos en los input_tokens medidos)' junto al in/out medido, jamás sumado; `tokens_measured` cuando viaja → [M]
  derivado. **(9) Traza (M3) `describir()`** (Traza.tsx:817): casos NUEVOS `stage.figures.plan` ('figuras: N papers elegibles ·
  caps 3/9/12 · presupuesto 90 s · lentes con visión: …'), `stage.figures.paper` (start: 'bajando figuras de PMC… (latido)'; done:
  'PMC…: 9 en el JATS · 9 extraídas · cc-by (ext-link) · zip 8.6 MB · 7.9 s'; voz alerta si `error` o `over_budget`),
  `stage.figures.figure` ('figura <fig_id> · sha <12> · <w>×<h> · <bytes_state> · embebible|no embebible'),
  `stage.figures.summary` ('figuras: N verificadas de M · K embebibles · presupuesto used/total' | 'kill-switch');
  `stage.audit.judge` (:1060) += '+ N imágenes' cuando `figures_sent > 0`; `LineaPaper` (:2106) sin cambio (los conteos viven en
  `stage.figures.paper`). **(10) Lista/Banco:** chip 'N figuras verificadas · K citadas' desde `epistemic_summary.figures_*`
  (null → nada; 0 → '0 figuras (medido)'). **(11) M8 Consumo:** bloque `usage.figures` (n corridas con figuras, verificadas,
  citadas, bytes, tokens de visión PROYECTADOS por modelo) como bloque APARTE del medido. **(12) PDF:** el botón 'PDF de
  servidor' no cambia; la Hoja dice 'el PDF incluye miniaturas sólo de figuras embebibles' cuando `n_embeddable > 0`.
- **Qué mide el gate de paridad (`tools/parity_check.py`):** (A) rutas `GET /runs/{run_id}/figures` y `/figures/{sha256}` con
  wrapper en client.ts Y consumidor fuera de client.ts; `/usage.figures` leído en M8. (B) `figures` en frozen ⇄
  `RegistroCongelado.figures` ⇄ lector en Hoja; `Citation.kind` incluye 'figure'; **(F) vocabularios**: `figures.LICENSES`,
  `LICENSE_TABLE` ids, `BYTES_STATES_EXACT/PREFIXES`, `FIGURES_STATES_EXACT/PREFIXES`, `SERVABLE_STATES`, `VISION_LENSES`,
  `SAW_FIGURES_DETAILS` del backend == unions TS (sin escape) == tablas de `src/lenguaje/figuras.ts` == TODOS los fixtures
  (`figures.state`, `items[].bytes_state`, `items[].license.id`, `citations[].figure_verification.bytes`,
  `audit.panel[].saw_figures.detail`) — patrón `check_trigger`/`check_plan_state` (:567/:733). (C) los 4 tipos `stage.figures.*`
  con caso en `describir()`. **(D) PDF: 0 huecos `[pdf]` (top-level por `PDF_ACCESS_RE` Y por `SECCIONES`, anidadas por
  `PDF_NESTED` ampliado); las 23 líneas de deuda reportadas 'DEUDA SALDADA' y retiradas; EXIT 0.** (E) sin cambio.
- **Gate NUEVO de cobertura del PDF en el backend** (K): toda llave top-level del frozen REAL tiene sección; una llave futura sin
  sección rompe `smoke_record_pdf` — la regla §18 «cada bloque nuevo nace con su sección» hecha mecánica.
- **Registros históricos y el PDF:** un registro 1.11 REAL (0082) imprime CONSEJO con valor y FIGURAS 'NO INSTRUMENTADO (contrato
  < 1.12)'; uno 1.9 imprime MODELOS '< 1.10' (hoy imprimiría '< 1.8': falso). El gate (K.4) lo mide con fixtures 1.9/1.10/1.11/1.12.
- **Dokploy:** sin volumen, tras cada redeploy `GET /figures/{sha}` → 404 `bytes-not-in-cache` declarado y el PDF/Hoja pasan a
  'enlace + sha' (honesto, no roto); el registro (sha, dims, licencia) sigue íntegro (E4). `WITT_MCP_CACHE_DIR` necesita ESCRITURA
  (ya lo exige el TSV de ZFIN, ADR-0080).
- **Held-out (ADR-0072):** la `description` de `SYNTH_TOOL` cambia aunque `WITT_FIGURES=0` → LG9 re-corre el held-out antes de
  Accepted (gasto declarado; E5).
- **Consejo (0082):** un requisito `evidence_kind 'figure'` sigue contándose `unsatisfiable-by-harness` hasta que la costura (O.2)
  aterrice; `coverage_after_search.figures_available_n` lo informa. Declarado, no resuelto.
- **Límites declarados (no se disfrazan):** *(F8)* la regla (6) `epmc-search` de (A.2) hoy NO dispara desde la corrida:
  `answer_pipeline._SEARCH_REC_KEYS` proyecta el `search_rec` a 8 llaves SIN `license` (y `answer_pipeline.py` no se toca en 0083) aunque
  `fetch_paper._normalize_hit` ya lo conserve — queda para 0083.1 (añadir `license` a la proyección y al check de forma del smoke 0078, o
  pasar `search_license_of` desde `runs`); mientras, `search_license None` declarado y `conflict` nunca se emite en producción · `figure_only_not_asserted` no atrapa una afirmación CUALITATIVA figure-only con una
  cita paper ENTREGADA al lado — la atrapan las lentes con visión como juicio y el proxy numérico (F.4) sólo lo mide *(corrector: una
  cita paper ALUCINADA o sin pasaje entregado ya NO la rescata; D.2 «same paper» se mide, no se gatea)* · *(corrector)* la lente
  evidence-grounding es a la vez lente con VISIÓN y la ÚNICA que emite `citation_support`: un `supported` de una cita figure pudo estar
  informado por los píxeles — `FIGURE_READING_RULE` pide juzgar SOLO el caption y la fila lo DECLARA (`citation_support_vision_informed`);
  el registro no puede distinguir un `supported` de caption de uno de imagen, y se dice · *(corrector)* `n_figures = n_verified +
  n_mismatch + n_not_fetched + n_error` (+ filas `'never (…)'`, 0 hoy); antes `n_not_fetched` englobaba los `'error: '` sin declararlo; la licencia del
  artículo puede no cubrir figuras de terceros (A.3 `rule`); el caption puede DUPLICAR texto que `_xml_to_text` ya puso en
  `text_excerpt` (se MIDE por figura `caption_in_excerpt: bool`, substring determinista; sin corregir); `figure_readings` de un juez
  que ignore la regla se congela como juicio etiquetado y jamás sube la escalera ni entra a la revisión (D.4).

## Tabla de env (todas con default declarado; lector `figures.env_config()` tolerante en tiempo de llamada; toda env = reinicio)

| Variable | Default | Lector | Efecto / fuente declarada |
|---|---|---|---|
| `WITT_FIGURES` | `1` | `runs._figures_stage` · `audit()` · `app` | kill-switch maestro; `0` = frozen 1.11 byte a byte salvo 3 excepciones (M.1) |
| `WITT_FIGURES_VISION` | `1` | `audit()` | `0` = ninguna lente recibe imágenes; captions/sha/licencia siguen (M.2) |
| `WITT_FIGURES_VISION_LENSES` | `evidence-grounding,reproducibility` | `composite_auditor.vision_lenses` | CSV de **≤ 2** lentes validado contra `models.LENSES`; inválido → default declarado; > 2 → default declarado `'default-invalid-env:… (>2 lenses)'` (`VISION_LENSES_MAX = 2`, §7 — *corrector*) |
| `WITT_FIGURES_MAX_PAPERS` | `3` | `runs._figures_stage` | papers (con PMCID + XML) de los que se parsean/bajan figuras, orden `selection_rank`; resto `not-fetched (paper-cap)` |
| `WITT_FIGURES_MAX_PER_PAPER` | `9` | `figures.attach` | figuras por paper en orden de documento (clamp 1..30) |
| `WITT_FIGURES_MAX_PER_RUN` | `12` | `figures.attach` | tope de figuras bajadas por corrida; resto `not-fetched (run-cap)` |
| `WITT_FIGURES_MAX_PER_LENS` | `12` | `figures.select_for_panel` | imágenes por petición de juez (clamp 0..20: ≤ 20 evita «many-image requests») |
| `WITT_FIGURES_MAX_IMAGE_MB` | `5` | `figures.select_for_panel` · PDF | bytes crudos por imagen para panel/miniatura (clamp ≤ 7: 9.3 MB b64 < 10 MB API) |
| `WITT_FIGURES_ZIP_MAX_MB` | `40` | `figures.fetch_figures` | precheck `Content-Length` y tope de streaming → `not-fetched (zip-over-max)` sin escribir |
| `WITT_FIGURES_BUDGET_S` | `90` | `figures.attach` | reloj TOTAL de la etapa, fuera de la ronda de búsqueda; por paper `min(45, restante)` (constante) APLICADO dentro de la descarga (`_get_bytes(deadline)` → `not-fetched (timeout)` — *corrector*) |
| `WITT_FIGURES_TTL_DAYS` | `30` | `figures.fetch_figures` | frescura del ledger por PMCID; fresco + sha iguales → `cache_hit`, cero red; `≤0` = nunca confiar |
| `WITT_FIGURES_CACHE_MAX_MB` | `512` | `figures.fetch_figures` | tope de `figures/`; evicción LRU por mtime al escribir, `evicted_n`; `0` = sin tope declarado |
| `WITT_FIGURES_CAPTION_CHARS` | `2000` | `figures.parse_jats` | tope del caption que viaja (`caption_truncated`); medido: media 1 030, máx 3 087 |
| `WITT_FIGURES_EMBED_LICENSES` | `cc-by,cc0,cc-by-sa` | `figures.LICENSE_TABLE` | sólo RESTRINGE la tabla; gobierna GET 200/403, miniatura Hoja y PDF (*corrector*: el PDF lo aplica de verdad — `record_pdf._embeddable_now`; antes embebía por el veredicto congelado) |
| `WITT_FIGURES_PANEL_LICENSES` | `cc-by,cc0,cc-by-sa,cc-by-nc,cc-by-nd,cc-by-nc-sa,cc-by-nc-nd,cc-by-prose-unconfirmed` | `figures.LICENSE_TABLE` | licencias cuyos bytes ven las lentes (E2); `unknown`/`zfin` nunca |
| `WITT_FIGURES_PROSE_LICENSE` | `1` | `figures.parse_license` | prosa «Creative Commons Attribution» sin URL → `cc-by` (`license-p-prose`); `0` → `cc-by-prose-unconfirmed` (E3) |
| `WITT_FIGURES_OPENAI_DETAIL` | `high` | `_responses_kwargs` · `_openai_chat_call` · `runs._vision_tokens` (*corrector*) | `detail` del `input_image`/`image_url` (`low|high|auto|original`); a ≤ 840 px `high` = 2–4 tiles en gpt-4o; gobierna TAMBIÉN la proyección de runs (`vision.sent`, `by_model[*].vision`) — una cifra por envío |
| `WITT_FIGURES_REFETCH_ON_GET` | `0` | `app.get_figure_bytes` | `1` = ante `bytes-not-in-cache` UNA GET y servir SOLO si sha == congelado (409 si no) |
| `WITT_FIGURES_PDF_THUMBS` | `1` | `record_pdf.build_pdf` | `0` = palabras + enlace aunque la licencia permita |
| `WITT_FIGURES_COUNT_TOKENS` | `0` | `audit()` (lentes Anthropic) | `1` = `vision.tokens_measured` por `count_tokens` con la MISMA petición menos los bloques `image` (rótulos de caption incluidos — *corrector*; una llamada gratuita por lente) |
| `WITT_MCP_CACHE_DIR` | (ya existe; vacía = `<repo>/mcp_cache`) | `figures.cache_dir` | las figuras la HONRAN (`<dir>/figures/`); `frozen.figures.cache.dir_source/dir_state`; sin volumen = efímera |

Constantes declaradas (viajan en `caps` con `source 'constant (ADR-0083)'`): presupuesto por paper `min(45, restante)`; b64 por
petición 8 MB; miniatura ≤ 60 mm; ≤ 12 miniaturas por PDF; PDF ≤ 8 MB; guardia 40 MP; `expose_headers` fijos (I).

## Gates NO-SPEND (máscara de siempre: `WITT_BACKEND_DB_URL` sqlite tmp · `NEO4J_URI=''` · `RAG_BACKEND=sparse` · `OPENAI_API_KEY=''` · `ANTHROPIC_API_KEY=''` · `WITT_RUN_ORIGIN=smoke` · `WITT_MCP_CACHE_DIR=<tmp>`; venv `dev/.venvs/witt-query-service`, fpdf2 2.8.8 + Pillow 12.3.0)

| Gate | Hoy @ ca9a03d *(F7: alineado — conteos MEDIDOS por C9/corrector que declara la tabla NO-SPEND de ADR-0082; 9d90c01 entre paréntesis donde difiere)* | Tras ADR-0083 | Qué MIDE de nuevo |
|---|---|---|---|
| `smoke_figures.py` (NUEVO) | — | **141/141** (corrector 2026-09-16; 135 F8: +6 — caché mismatch → re-descarga declarada y `sha_changed_from_previous_ledger`; deadline por paper con respuesta que gotea (costura real + attach); `now` naive; `n_error`) | GOLDEN parser: 2 XML fixture (PMC11379296 → 9 ids `pone.0307390.g001..g009`, labels 'Fig 1'..'Fig 9', hrefs `.jpg` jamás `.gif`, `dims_declared` g001 {original 2250×1252, scaled 750×417}, caption g001 **1 387** chars MEDIDOS tras `html.unescape` («&amp;» ×2 → «&»; el borrador decía 1 395) → 1 200 con `WITT_FIGURES_CAPTION_CHARS=1200` y `caption_truncated`; PMC11647118 → 6, `undfig1` `label None` + `caption_state 'absent'`, hrefs `fx1.jpg, gr1..gr5.jpg`) + los 12 del `mcp_cache` cuando existen (4·3·8·9·6·0·0·11·4·3·7·5 = 60; `<fig-count>` de PMC12184772 → 0) o 'NO MEDIDO (mcp_cache ausente)' declarado · LICENCIA golden: PMC11379296 cc-by/ext-link embed · PMC6424945 cc-by/ali-license-ref (pese a `OpenAccess`) · PMC8613261, PMC12184772 ali-license-ref · PMC9844136, PMC13286355, PMC6279434 ext-link · PMC11647118 cc-by-nc/license-p-url embed False panel_view True · PMC7809618 cc-by-nc-nd · PMC3198425 cc-by/license-p-prose con PROSE=1 y `cc-by-prose-unconfirmed` con 0 · PMC8786916 cc-by/license-p-token '(CC BY)' · PMC12161502 unknown/none embed False panel_view False · search `'cc by-nc-nd'` sin XML → epmc-search · XML cc-by-nc + search 'cc by' → gana XML + `conflict` · orden: 'CC BY-NC-ND' NO casa como cc-by · `<fig>//<permissions>` sintético → `scope 'figure-level'` · zfin → never · FETCH con zip fixture: 9 `verified`, sha == MANIFEST, mime jpeg por magic, dims == `scaled` → `dims_match True`, `s00N`/`.gif` jamás extraídos · entrada faltante → `not-fetched (href-not-in-zip)`; thumb presente → `(…; thumb-available)` · HTTP 500 / URLError / timeout / no-zip / BadZipFile / Content-Length > tope (0 bytes de cuerpo leídos) / cuerpo sin Content-Length > tope (`.part` borrado) → filas declaradas, sin excepción · presupuesto con reloj falso: 0 → `skipped`; total agotado → `budget-exhausted`, `over_budget` · caché: 2ª llamada TTL fresco → `cache_hit`, 0 `_get_bytes`; archivo alterado → `mismatch`; TTL 0 → re-descarga; `CACHE_MAX_MB=0.001` → `evicted_n ≥ 1`, el más nuevo sobrevive; dir read-only → `dir_state 'read-only'` y filas declaradas · `select_for_panel`: citadas primero, luego rank, luego orden; cap 12; request cap 8 MB → `n_dropped_by_request_cap`; > MAX_IMAGE_MB excluida · bloques Anthropic/Responses/Chat: forma exacta, imágenes antes del texto, b64 decodifica al byte original · `env_config` tolerante; `EMBED_LICENSES=cc-by,foo` → `env_ignored ['foo']` · `_xml_to_text` byte-idéntico antes/después · `_normalize_hit` con `license 'cc by'` / sin campo → None · `urlopen` = 0 · `mcp_cache` real idéntico |
| `smoke_models.py` | 87 (74 @ 9d90c01) | **96/96** (+9; el gate estático M.4 en verde tras marcar 5 literales de smokes ajenos con `# models-literal-doc`) | columna `vision_tier/vision_multiplier/vision_verified` por fila ∈ vocabulario y coherente con `family`; `vision_tokens`: 1000² opus-5 → 1296, haiku → 1296; 1920×1080 haiku → 1560, opus-5 → 2691; 2000×1500 → 1564/3888; 3840×2160 opus-5 → 4784 (tabla pública); gpt-4o 750×417 → 85+2×170 = 425, 738×840 → 85+4×170 = 765; astra 750×417 → 336×1.2 → 404; embed → None; `panel_signature` byte-idéntico al golden; `ENV_TABLE` (+20) ⊆ compose ∩ README; `snapshot()` trae `figures.enabled/figures.vision` con fuente |
| `smoke_panel_vision.py` (NUEVO) | — | **60/60** (corrector; 55 F8: +5 — clamp ≤ 2 lentes por env y por llamador; count_tokens con bloques sin `image`; cuerpo capturado; `citation_support_vision_informed`) | `body` de `_anthropic_tool_call` sin `user_content` byte-idéntico al de 9d90c01 (json sort_keys, `urlopen` fake); `_responses_kwargs` `input == user_text`; `_openai_chat_call` `content == user_text` · con 2 imágenes: Anthropic `[text, image, text, image, text(user_text)]` con `source.type 'base64'` y `media_type` medido; Responses `input[0].content` `[input_text, input_image(data URL), …, input_text]` + `detail`; Chat `messages[1].content` `[text, image_url{url,detail}, …, text]` · `audit()` con panel de 4 y 9 figuras: el fake recibe `member['figures']` SOLO en evidence-grounding y reproducibility (assert exacto por lente), su `system` contiene `FIGURE_READING_RULE` y los otros dos NO; `saw_figures.n` 9/9/0/0 con `detail` correcto · `vision_lenses=('correctness',)` → sólo correctness · `figures=None` → filas con el keyset de 9d90c01 + `saw_figures` (declarada) · `figure_readings` lista → crudo + class; string → `figure_readings_dropped`; id no entregado → dropped · juez `errored` conserva `saw_figures` y `attempts[].usage` · `MAX_PER_LENS=3` → 3 bloques · request cap → dropped · `vision_tier 'unknown'` → 0 bloques + `detail 'model-vision-unknown'` · `panel_signature` idéntico con y sin figuras · fakes de 3 argumentos siguen aceptados · `urlopen` = 0 |
| `smoke_openai_responses.py` · `smoke_panel_quorum.py` | 79 · 40 (28 @ 9d90c01) | **81/81 · 42/42** (+2 c/u) | golden byte a byte del cuerpo SIN `user_content` — nada cambia para los llamadores de hoy |
| `smoke_gate_citations.py` | 52 (48 @ 9d90c01) | **80/80** (+28; corrector +3: cita paper alucinada / resuelta sin pasaje NO rescatan la afirmación figure-only; `figure_citations_same_paper`) | cita `PMC11379296#pone.0307390.g001` resuelve al ítem figura → `resolved`, `passage_delivered` (caption); `caption_state 'absent'` → NO indexada · `figure_id_resolves`: id inventado → inadmisible con 'hard predicate failed: figure_id_resolves' · `figure_sha_matches`: igual → ok `n_checked 1`; 1 byte alterado → inadmisible, `mismatches[{id, expected, actual}]`; `not-fetched` → `n_not_verifiable 1`, ok · `figure_only_not_asserted`: positiva con SOLO citas figure → inadmisible; 1 paper + 2 figure → ok; declinación sólo figuras → ok; `absence_kind` AUSENTE + sólo figuras → inadmisible (conservador) · `figure_numerals_grounded`: '42 % [3]' sin respaldo → ok False, `numerals_unsupported ['42%']`, `admissible()` sigue True (gating false); caption con '42%' → ok; '[3][5]' con pasaje de [5] → `supporting_sources`; sin marcadores → `state 'no-markers: whole-answer fallback'`, `n_marker_absent 1`; '0,5' y 'n = 12' contados · `figure_license_known` unknown → ok False, `admissible()` True · las 5 evaluaciones se congelan, `decided_by 'code'` · sin figuras en el bundle → `state 'no-figure-citations'`, conjunción de hoy · `validate_disjoint` acepta kind figure con `n` entero y rechaza `l` · citas paper/di-chunk sin cambio de forma |
| `smoke_run_pipeline.py` | 302 (272 @ 9d90c01) | **372/372** (+70: F4 +57 → 359; F8 +8 costuras (O) + assert GLOBAL anti-binario sobre la BD; corrector +5: `audit_initial.vision`, colisión de `fig_id`, clasificador superset + `kind_reported`, proyección con `detail`, `bytes_verified`/`n_cache_hit`) | contrato '1.12' en TODAS · orden de la Traza: `stage.path_b → stage.figures.plan → paper{start,done}×n → figure×m → stage.figures.summary → stage.synthesize.pass2` · pass1 NUNCA recibe `figures`; pass2/revisión/panel reciben `papers[].figures[]` con caption y SIN `cache_path/raw_ref/b64` (assert por llaves y por substring de la b64 del fixture en `user_text`, `frozen_record_json` y `bundle_json`); gate ESTÁTICO `_PROMPT_FIGURE_KEYS ∩ FORBIDDEN == ∅` · `frozen.figures` completo (fixture BY: `n_figures 9`, `n_verified 9`, `n_embeddable 9`; fixture NC: `n_embeddable 0`, `n_panel_view 6`, `n_with_caption 5`); items sin b64; `seen_by_lenses` == lentes con `saw_figures.n>0` que incluyen ese sha · cita del stub `kind 'figure'` → `figure_verification {bytes 'verified', content 'panel-judgment'}` con fake que emite `figure_readings`, `'not-evaluated'` sin él · sha alterado entre attach y gate → pass2 inadmisible, `reasons` con `figure_sha_matches`, `decision_state` lo refleja · id inventado → inadmisible · positiva sólo-figuras → inadmisible · caller espía: SOLO grounding y reproducibility traen `member['figures']` (9), `saw_figures` 9/9/0/0; `stage.audit.judge.figures_sent` coincide · `WITT_FIGURES_VISION=0` → 0/0/0/0, captions siguen · `by_stage.panel.by_model['<haiku>'].vision {n_images 9, visual_tokens_projected 5037, class 'proyección'}`, `['gpt-4o'].vision {…5525…}`; `_sum` == by_model (sin doble conteo) · REVISE forzado → `vision.sent.n_panels 2` y `bytes_b64_sent_total` ×2 · `_panel_findings[].from_vision_lens` y la frase en `instruction`; `figure_readings` NO en findings · `agents_invoked` fila figures 'invoked'; sin XML → 'not-applicable' · `_evidence_ids` incluye los 9 ids · `epistemic_summary.figures_n_verified 9`; fixture 1.10 → null · `zfin_figures_state` literal · **KILL-SWITCH `WITT_FIGURES=0`: frozen == frozen 1.11 del mismo fixture (json sort_keys) salvo EXACTAMENTE `render_contract_version`, `figures`, `deterministic_checks.figures` — cualquier otra diferencia falla listando el path; 0 `_get_bytes`; UN `stage.figures.summary`; `user_text` byte-idéntico** · budget 0.5 s → `budget-exhausted`, la corrida cierra AUDIT_* · `_get_bytes` que lanza → 9 filas `not-fetched`, la corrida sigue · cancelar durante `stage.figures` → cancelled · `urlopen` = 0 · `mcp_cache` real idéntico |
| `smoke_figures_http.py` (NUEVO) | — | **43/43** (41 F5 + 1 F8: miniaturas del PDF == índice `servable 'yes'` y `WITT_FIGURES_PDF_THUMBS=0` leída en la llamada; corrector +1: índice con dir de caché INEXISTENTE → `dir_state 'missing'` sin crearlo) | TestClient, frozen 1.12 sembrado, caché TMP: 401 · 404 corrida · 409 sin frozen · 409 identidad · índice 200 con 9 items `servable 'yes'`, sin `b64`/`cache_path`, `url` relativa · bytes 200 `image/jpeg`, `ETag "<sha>"`, `X-Witt-Figure-License cc-by`, `X-Witt-Figure-Sha256`, body sha == path · NC → índice `forbidden-by-license`, bytes 403 con `{license, words_es, source_url}` · zfin sintético → 403 · sha ∉ registro → 404 · sha malformado → 400 · archivo borrado → 404 `bytes-not-in-cache` `refetch 'disabled …'`; `REFETCH_ON_GET=1` + `_get_bytes` fake igual → 200 `attempted: verified`; distinto → 409 · archivo alterado → 409 y NO se sirve · kill-switch → índice `state`, bytes 404 · frozen 1.10 → `not-instrumented (contrato < 1.12)` · `expose_headers` presentes en la respuesta CORS (preflight con `Origin`) · `/runs/{id}/figures` no captura `/runs/{id}/events` · `record.pdf` 200 con y sin caché · `/usage.figures` cuenta 1 corrida con figuras · `urlopen` = 0 |
| `smoke_usage_http.py` | 32 (25 @ 9d90c01) | **34/34** (+2) | `figures {n_runs_with_figures, n_figures_verified, vision_tokens_projected_by_model, class}` |
| `smoke_record_pdf.py` (NUEVO — gate de cobertura) | — | **56/56** (corrector +2: `WITT_FIGURES_EMBED_LICENSES=cc0` de HOY → 0 miniaturas + 'embebible al congelar; NO embebible HOY'; regex ANCLADA de `SECCIONES` → 52 llaves y la trampa sin anclar medida) | (K) completo: cobertura EXACTA con frozen 1.12 real; regex de la webapp copiada → 0 huecos; anidadas en bytes; born correcto por llave (1.8/1.9/1.10/1.11/1.12); 5 frases de `citations_schema`; regla del sha leída; miniaturas sólo BY+verified (conteo `/Subtype /Image`), NC 0, alterado 0, caché vacía 0, THUMBS=0, tope 8 MB degradado; ADR-0073 a–f; determinismo; `urlopen` 0 |
| `smoke_fetch_paper.py` | 41 (F1 ya suma sus +3 en el worktree) | **44/44** (+3) | `license` en `_normalize_hit` ('cc by-nc-nd' → igual; ausente → None); cache legado sin license declarado |
| resto (competence 39 · thread_context 40 · run_recovery 40 · query_service 47 · precedent 30 · … — @ ca9a03d; 31 · 37 @ 9d90c01) | medido igual | **41/41 smokes exit 0 (F8 2026-09-16; re-medidos por el corrector el 2026-09-16 tras aplicar los hallazgos — todos exit 0)**: competence 39 · thread_context **42** (corrector +2: D.4 entre turnos — `from_vision_lens`/`n_from_vision_lens` desde el registro del padre y `THREAD_VISION_FINDINGS_CLAUSE`) · run_recovery 40 · query_service 47 · precedent 30 · council **70/70** (D.1 amplía la firma con `user_content`) · council_http 74 · council_index 63 · council_jobs_db 59 · config_history_http 29 · config_ledger_db 37 · agent_matrix 46 · catalog_cards 57 · entities 16 · m5v2_http 32 · niches 21 · notes_http 28 · pubmed_tool 32 · question_agent_http 40 · ratings_calibration 44 · run_comments_http 14 · runs_list_http 25 (+1) · runs_thread_http 71 · search_harness 65 · search_queries 163 · threads_db 77 · tools_a 45 · tools_b 69 · tools_c 68 · zfin_tool 26 | `precedent.py` sin tocar (`grep figure` = 0); `smoke_competence`/`thread_context`/`run_recovery` sólo si un aserto se rompe por llaves nuevas |
| `smoke_live_figures.py --dry-run` (estático) | — | **exit 0 — MEDIDO por F7 el 2026-09-16 con la máscara; re-medido por el corrector tras los cambios (`n=4 failed=0 urlopen_real=0 db_imported=False`, `content_equals_blocks True` ×3)** (4 filas: `pmcid` PMC11379296 con XML de fixtures y `figures._get_bytes` FALSEADA con el zip fixture → `fetch_figures` REAL: 9 `verified`, sha == MANIFEST 9/9, dims == `scaled` 9/9, `dims_match` 9, licencia `cc-by (ext-link)`, `embeddable`/`panel_view` True; bloques de los TRES transportes con 9 imágenes ANTES del texto y la b64 decodificando al sha original — Anthropic `[text, image]×9 + text`, Responses `[input_text, input_image]×9 + input_text`, Chat `[text, image_url]×9 + text`; con F3 aterrizado los TRES callers reales quedan CAPTURADOS con `urlopen` bloqueado y cliente OpenAI falso — `captured.content_equals_blocks True` ×3 (Anthropic `messages[0].content` 19 bloques · Responses `input[0].content` 19 partes · Chat `messages[1].content` 19 partes; re-medido por F8 el 2026-09-16 con `--dry-run --pmcid PMC11379296`), nada llamado; `urlopen` reales 0; `figures._zip_url` == `{EPMC}/{PMCID}/supplementaryFiles`; ningún módulo de BD importado; nada escrito) | URLs construidas con `figures._zip_url`, `urlopen` 0, sin BD; con F3 aterrizado captura además el cuerpo/kwargs REALES del caller (`content_equals_blocks`) |
| paridad en LECTURA (`witt-webapp/tools/parity_check.py` copiado al scratchpad con `BACKEND` = este worktree; la webapp NO se toca) | — | **13 huecos SIN declarar (F8 2026-09-16)** | ESPERADOS por este ADR: `[registro] figures` (CONGELA SIN TIPO) · `[rutas] GET /runs/{run_id}/figures` y `/figures/{sha256}` (SIN RANURA) · `[etapas] stage.figures.plan | paper | figure | summary` (SIN CASO EN TRAZA — visibles SOLO tras F8: la superficie (C) lee `add_event(run_id, "literal"`) · `[pdf]` 0 huecos (las 23 líneas de deuda siguen en `parity_debt.json` con `adr ADR-0083`: W4 las retira). NO de este ADR: `[rutas] /me`, `/health`, `GET /runs/{run_id}/ratings`, `/notes/questions/spec`, `/notes/questions/calibration` — todas declaradas en `parity_debt.json` («no aplica» / ADR-0087) pero la copia EN OBRA de `parity_check.py` (la webapp tiene 70 archivos modificados por el workflow W1–W4) no las casa como deuda ni imprime «SALDADA»; W4 lo cierra |

## Gates EN VIVO (los corre Emmanuel; cada uno gasta lo que dice; resultados al ADR como MEDICIÓN con fecha)

- **LG1 · Bytes reales (red a www.ebi.ac.uk, 0 modelo):** `python analysis/scripts/smoke_live_figures.py --pmcid PMC11379296`
  → HTTP 200 `application/zip` (~8.6 MB), 27 entradas, 9 jpg con sha256 == MANIFEST del fixture (g001 `40877777ed82…` … g009
  `58d57b703b16…`) y dims == (750×417, 738×840, 715×839, 750×725, 750×474, 750×655, 674×501, 750×251, 750×556); `elapsed_s` y
  MB/s desde el VPS (calibra `WITT_FIGURES_BUDGET_S`); repetir con PMC11647118 (NC) → 6 `verified`, `embeddable False`; un PMCID
  no-OA → `not-fetched (http-4xx)` declarado. Además `--href-direct` prueba `europepmc.org/articles/PMC11379296/bin/pone.0307390.g001.jpg`:
  si 200 y sha == miembro del zip → 0083.1 aditivo declara el respaldo (30–100× menos bytes); si no, queda 'no verificado'.
- **LG2 · `license` del search (1 GET):** `curl '…/search?query=PMCID:PMC11379296&resultType=core&format=json'` → `license: "cc by"`
  esperado (la caché ya lo trae para otras consultas); anotar para el golden de `_normalize_hit`.
- **LG3 · UNA corrida real con `WITT_FIGURES=1` sobre a361f566 (o pregunta con paper OA con figuras; ≈ 0.25–0.45 USD [E]):**
  Traza con `stage.figures.plan → paper(start/done) → figure×n → summary`, hueco de latido < 300 s; `frozen.figures.n_verified ≥ 1`;
  `audit.panel[].saw_figures.n > 0` EXACTAMENTE en evidence-grounding y reproducibility; `attempts[].error_kind` sin `http-400`
  (la forma de bloques fue aceptada por Anthropic Y por gpt-4o chat.completions — LG4 lo aísla si falla); `figure_readings` presente
  y etiquetado; `deterministic_checks.figures.state 'checked'` y `n_marker_absent` (¿el sintetizador cita inline?); `input_tokens`
  de esas lentes vs la misma corrida con `WITT_FIGURES_VISION=0` (misma pregunta, mismo día) → Δ descriptivo vs
  `visual_tokens_projected`; tasa de falsos positivos de `figure_numerals_grounded` (decide 0083.1 → gating). Correr con
  `WITT_FIGURES_COUNT_TOKENS=1` → `vision.tokens_measured` para haiku (calibra la fórmula; marca `vision_verified True` en tabla).
- **LG4 · Formas de imagen por transporte (≤ 3 llamadas, ≤ 0.05 USD):** `smoke_live_figures.py --judge gpt-4o --api chat-completions
  --image <sha>` → `function_call`/tool con `verdict` ∈ VOCABULARY (la forma Chat Completions queda MEDIDA); `--judge gpt-6-astra --api
  responses --image <sha>` → verdict + `usage.input_tokens` anotado (si rechaza `detail` o la data URL: kind de fallo ADR-0081 C.2 y
  ajustar `WITT_FIGURES_OPENAI_DETAIL`); `--judge claude-haiku-4-5 --image <sha>` con `count_tokens` con/sin bloque → Δ = MEDICIÓN.
- **LG5 · Puertas en prod:** `GET /runs/{id}/figures` de LG3 → índice; `/figures/{sha}` de una cc-by → 200 image/jpeg con headers
  (y la webapp los LEE: CORS); de una cc-by-nc → 403 con license; sha inventado → 404; la Hoja muestra miniatura BY y placa NC.
- **LG6 · Dokploy (E4):** confirmar `cache.dir_state 'writable'` en el registro; tras redeploy `GET …/figures/{sha}` → 200 (con
  volumen) o 404 `bytes-not-in-cache` (sin volumen) — MEDICIÓN que decide E4; `/config-history` ganó `figures.enabled/figures.vision`.
- **LG7 · `GET /runs/{id}/record.pdf` de LG3:** 52 secciones (grep de rótulos), miniaturas SOLO en CC BY, NC en palabras, 'CUORUM',
  'MODELOS', 'ESQUEMA DE CITAS' con el literal correcto, 'vista por 2 lentes: JUICIO'; un registro 1.9 histórico → 'NO INSTRUMENTADO
  (contrato < 1.10)' para models y '< 1.12' para figures (no '< 1.8'); abrir en dos visores.
- **LG8 · webapp:** `python tools/parity_check.py` contra `contract-1.12-frozen` → (D) 0 huecos, 23 líneas SALDADAS retiradas,
  (F) vocabularios OK, EXIT 0; `gen_fixtures.py` regenera 1.12; vitest verde.
- **LG9 · Held-out ADR-0072 tras el cambio de `SYNTH_TOOL.description` (evaluation/run_held_out.py; gasto ≈ una tanda held-out,
  E5):** la serie `ab_trapped_scalar` sigue comparable (`synth_system` no cambió); anotar Δ.
- **LG10 · Presupuesto (3 corridas con figuras):** `figures.budget.used_s` p95 y `stage.figures.paper.elapsed_s`; p95 > 45 s →
  ajustar `WITT_FIGURES_BUDGET_S`/`MAX_PAPERS` en compose (declarado).

## Proyección de costo y latencia (CLASE: PROYECCIÓN — calculada por fórmula pública verificada 2026-09-15 desde insumos MEDIDOS y supuestos DECLARADOS; ninguna imagen se ha mandado a un modelo desde este código; LG3/LG4 sustituyen cada cifra)

**Insumos medidos:** dims de las 9 figuras de PMC11379296 (Context 2; ≤ 750×840, 1.27 MB de JPG → ≈ 1.7 MB b64); captions
media 1 030 chars ≈ 260 tokens. **Fórmulas verificadas:** Anthropic Σ⌈w/28⌉×⌈h/28⌉ = 405+810+780+702+459+648+450+243+540 =
**5 037 tokens por lente** (idéntico en tier estándar de haiku y alto de sonnet/opus: ninguna figura supera 1 568 px ni 1 568
tokens); gpt-4o (tiles: ninguna se reescala; 2 o 4 tiles) = 9×85 + 28×170 = **5 525**; gpt-6-astra (parches) = 3 997 × 1.2 =
**4 797**. **Tarifas** (`models.prices()` g2: haiku 1/5 · sonnet-5 2/10 · opus-5 5/25 · gpt-4o 2.5/10 · astra 10/50 USD/Mtok).
**Escenario A — panel de HOY (grounding = haiku, reproducibility = gpt-4o bridge), 9 figuras, 1 panel:** visión 5 037×1e-6×1 +
5 525×2.5e-6 = 0.005 + 0.014 = **0.019 USD**; captions al sintetizador (pass2: 9×260 = 2.3k tok × opus-5 5/M) 0.012; captions a
los 4 jueces (2.3k × (5+2+1+2.5)/M) 0.024; `figure_readings` de salida (≈ 300 tok × 2 lentes) 0.004 ⇒ **≈ 0.06 USD por corrida con
figuras**; con REVISE (2.º panel + revisión) ×≈1.8 ⇒ **≈ 0.10 USD**; con reintentos de juez hasta ×2 en la parte de panel. Base
medida hoy 0.208 USD (mediana ADR-0081) ⇒ **+30 % (A) a +50 % (A+REVISE)**. **Escenario B — sucesor sonnet-5 en grounding:**
+0.005. **Escenario C — Astra en reproducibility (si LG3/E1 de 0081 pasan):** visión astra 4 797×10e-6 = 0.048 (+ reasoning
tokens no proyectables) ⇒ ≈ 0.10 (1 panel) – 0.17 (REVISE) USD por corrida. **Escenario D — tope 12 figuras/lente con la figura
más cara medida (810 tok):** ×1.9 sobre A. **Consejo 1.11 encendido (fuera de este ADR, declarado):** captions a 17 miembros × r2 ≈
17 × 2.3k × 5e-6 ≈ 0.20 USD. **Latencia [E]:** zip 8.6–30 MB a 1–10 MB/s → 1–30 s por paper; 3 papers → 3–90 s dentro de
`WITT_FIGURES_BUDGET_S=90` (el 3.º queda `budget-exhausted` en el peor caso, declarado); latidos por paper y por figura mantienen
el watchdog < 300 s; el panel gana ≈ 1–4 s por lente con visión. **Petición:** 9 imágenes ≈ 1.7 MB b64 ≪ 32 MB; ≤ 12 por lente
evita «many-image requests». **Registro:** `frozen.figures.items` sin b64 ≈ 9 × ~1.6 KB ≈ 15 KB (medible en smoke). **Caché:** 9
originales ≈ 1.3 MB por paper; 512 MB cubren ≈ 400 papers antes de evicción. **PDF:** ≤ 12 miniaturas × 60 mm, JPEG originales
(≤ 225 KB) ⇒ +0.6–1.8 MB, tope 8 MB. **Mensual a 30 corridas con figuras:** 2–5 USD (A/A+REVISE). Lo medido es el `input_tokens`
por lente; todo lo demás lleva clase 'proyección' en el registro.

## Decisiones abiertas para Emmanuel (mínimas; cada una con default)

- **E1 · Encendido desde el merge.** Default: `WITT_FIGURES=1` y `WITT_FIGURES_VISION=1` (el costo no es impedimento; el kill-switch
  está medido byte a byte). Alternativa: `WITT_FIGURES_VISION=0` hasta LG3/LG4 (figuras observadas sin píxeles al panel).
- **E2 · ¿Las dos lentes ven bytes de figuras CC BY-NC/ND (no embebibles)?** Default: SÍ (`WITT_FIGURES_PANEL_LICENSES` incluye
  NC/ND: leer para juzgar no es redistribuir; embeber sigue prohibido y el 403 lo acota). Alternativa estricta: sólo embebibles.
  `unknown` NUNCA (no es pregunta: términos desconocidos).
- **E3 · Prosa «Creative Commons Attribution License» sin URL (PLoS 2011 PMC3198425; Frontiers PMC8786916 '(CC BY)') cuenta como
  cc-by embebible.** Default: `WITT_FIGURES_PROSE_LICENSE=1` con `source 'license-p-prose'` visible en Hoja/PDF. Alternativa 0:
  `cc-by-prose-unconfirmed`, no embebible (panel sí).
- **E4 · Persistencia de bytes en Dokploy.** Default de este ADR: SIN volumen, declarado (`dir_state`, 404 `bytes-not-in-cache`,
  `WITT_FIGURES_REFETCH_ON_GET=0`). Recomendación operativa: montar volumen para `WITT_MCP_CACHE_DIR` antes de LG3 (también
  beneficia al TSV de ZFIN y al caché de papers); LG6 mide el resultado. Alternativa: `REFETCH_ON_GET=1` (red en una GET,
  verificada por sha).
- **E5 · Texto literal de la aprobación presupuestal (brief R6) y autorización de LG3/LG4/LG9 (≈ 0.5–1.0 USD).** Propuesta:
  «Apruebo hasta 12 figuras por corrida (3 papers × 9) entregadas a dos lentes del panel (≈ +0.06–0.10 USD por corrida con el
  panel de hoy; ≈ +0.10–0.17 con Astra), captions al sintetizador y a los jueces, sin tope de USD por corrida; toda cifra con
  clase.» — confirmar tal cual o acotar (`WITT_FIGURES_MAX_PER_RUN`, `WITT_FIGURES_MAX_PER_LENS`, `WITT_FIGURES_OPENAI_DETAIL=low`).

(No son preguntas — defaults declarados + gate: href directo (LG1), `WITT_FIGURES_OPENAI_DETAIL=high` y `MAX_PER_LENS=12` (LG3/LG4),
`figure_numerals_grounded` informativo → gating (LG3), orden de aterrizaje 0082 → 0083 (J.5: ingeniería, en el plan).)

## Plan de implementación (rebanadas DISJUNTAS por archivo → integrador → 3 revisores → corrector)

Orden: **F1 → (F2 ∥ F3 ∥ F4 ∥ F5 ∥ F6 ∥ F7) → F8 integrador → R1/R2/R3 → corrector.** F1 congela la INTERFAZ de `figures.py`
(firmas y formas de (A)/(B)/(L)); F2–F6 desarrollan contra ella y, hasta que aterrice, contra un stub local con esas firmas que
F8 retira. Todas las rebanadas arrancan sobre `contract-1.11-frozen` (O.1); ningún archivo tiene dos dueños en 0083 (el doble dueño
con 0082 se resuelve por orden de aterrizaje, J.5).

- **F1 · `lib/figures.py` + `fetch_paper._normalize_hit` + fixtures + `smoke_figures.py`** — dueño de:
  `analysis/scripts/lib/figures.py` (NUEVO: `parse_jats`, `parse_license`, `LICENSE_RULES`, `LICENSE_TABLE`, `LICENSES`,
  `BYTES_STATES_*`, `FIGURES_STATES_*`, `SERVABLE_STATES`, `_get_bytes`, `fetch_figures`, `attach`, `locate_xml`, `cache_dir`,
  `verify_cached`, `evict_lru`, `image_dims`, `select_for_panel`, `anthropic_blocks`, `openai_responses_parts`, `openai_chat_parts`,
  `env_config`, `_zip_url`) · `analysis/scripts/lib/fetch_paper.py:171-178` (una línea) · `rag_index/query_service/fixtures/figures/`
  (`epmc_fulltext_PMC11379296_20260613.xml`, `epmc_fulltext_PMC11647118_20260613.xml` copias byte-idénticas;
  `PMC11379296-figures.zip` 9 jpg; `PMC11647118-figures-SYNTHETIC.zip`; `MANIFEST.json`) · `smoke_figures.py` (NUEVO) ·
  `smoke_fetch_paper.py` (+3). Interfaz congelada al cerrar F1.
- **F2 · `verify_output.py` + `smoke_gate_citations.py`** — dueño de: `analysis/scripts/lib/verify_output.py` (`_bundle_evidence_index`
  += figuras; `figure_predicates(citations, bundle, cache_dir, answer_text) -> (fragmento deterministic_checks.figures,
  extra_predicates[])` con los 5 predicados y `FIGURE_RULES`) · `rag_index/query_service/smoke_gate_citations.py` (+≥16).
- **F3 · `composite_auditor.py` + `models.py` + smokes del panel** — dueño de: `analysis/scripts/lib/composite_auditor.py`
  (`VISION_LENSES`, `vision_lenses(env)`, `FIGURE_READING_RULE`, `SAW_FIGURES_DETAILS`, `_anthropic_tool_call(..., user_content=None)`,
  `_responses_kwargs(..., user_content=None)`, `_openai_responses_call(..., user_content=None)`, `_openai_chat_call(...,
  user_content=None)`, `_default_caller` lee `member['figures']`, `VERDICT_TOOL.figure_readings` + `parse_figure_readings` +
  `figure_readings_from_panel`, `audit(figures=None, vision_lenses=None)`: fila `saw_figures`/`figure_readings`, `audit.vision`;
  `apply_to_bundle` copia) · `analysis/scripts/lib/models.py` (columnas `vision_tier/vision_multiplier/vision_verified`,
  `VISION_TIERS`, `vision_tokens()`, `ENV_TABLE` += 20 filas, `SNAPSHOT_FIELDS` += `figures.enabled`, `figures.vision`) ·
  `smoke_panel_vision.py` (NUEVO) · `smoke_models.py` · `smoke_openai_responses.py` (+2) · `smoke_panel_quorum.py` (+2).
- **F4 · `runs.py` + `smoke_run_pipeline.py`** — dueño de: `rag_index/query_service/runs.py` (contrato '1.12'; `SYNTH_TOOL` enum +
  description; `_PROMPT_FIGURE_KEYS` + proyección; `_evidence_ids`; `_figures_stage` (C) con eventos; `_figures_for_panel(bundle,
  answer)`; `_gate` cablea `figure_predicates` (tolerante: `tool-unavailable`); `_support_states` += `figure_verification` +
  `figure_citations`; `_panel_findings` += `from_vision_lens` + frase en `instruction`; `panel_caller` += `figures_sent/figures_sha256`;
  `_usage_by_stage` += `by_model[*].vision`; `audit(..., figures=…, vision_lenses=…)` en ambos paneles; `frozen.figures`,
  `deterministic_checks.figures`; `_agents_invoked` fila; `epistemic_summary` += figures_*; `snapshot_extra` += figures.*;
  kill-switch con excepciones exactas) · `smoke_run_pipeline.py` (+≥40) · `smoke_competence.py`/`smoke_thread_context.py`/
  `smoke_run_recovery.py` sólo si un aserto se rompe por llaves nuevas.
- **F5 · `app.py` + smokes HTTP** — dueño de: `rag_index/query_service/app.py` (`GET /runs/{run_id}/figures`, `GET /runs/{run_id}/
  figures/{sha256}` antes de `/events`; `expose_headers`; `get_record_pdf` pasa `cache_dir/thumbs`; `/usage += figures`) ·
  `smoke_figures_http.py` (NUEVO) · `smoke_usage_http.py` (+2) · `smoke_runs_list_http.py` (+1: `epistemic_summary.figures_*` lista ==
  detalle).
- **F6 · `record_pdf.py` completo + gate de cobertura** — dueño de: `rag_index/query_service/record_pdf.py` (RE-ESTRUCTURA: `SECCIONES`,
  `KEY_BORN`, `SERVICE_KEYS`, `_tres_estados`, `pdf_sections_cover`, `contract_of`, 52 secciones (J.2), miniaturas gateadas,
  `build_pdf(record, compress=True, cache_dir=None, thumbs=None)`; absorbe `_section_consejo` de 0082) · `smoke_record_pdf.py` (NUEVO).
- **F7 · doctrina + operación + vivo** *(entregado 2026-09-16)* — dueño de: `docs/decisions/0083-figuras-como-evidencia-observada-y-pdf-completo.md` (este
  documento con conteos "F8 mide", alineado a ca9a03d) · `docs/decisions/README.md` (fila 0083) · `CLAUDE.md` §7 (viñeta figure-only) ·
  `rag_index/query_service/docker-compose.query.yml` (bloque ADR-0083 tras el bloque 0082: 20 env `${VAR:-default}` + comentario
  de una línea) · `rag_index/query_service/README.md` (tabla de env + sección ADR-0083 + gates) · `analysis/scripts/smoke_live_figures.py`
  (NUEVO, EN VIVO: `--pmcid`, `--href-direct`, `--judge <model> --api <api> --image <sha>`, `--count-tokens`, `--dry-run`; usa
  `figures.fetch_figures` y los callers REALES con `user_content`; imprime JSON sin secretos a `analysis/outputs/live_figures_<fecha>.json`;
  rehúsa correr sin llave; jamás toca la BD).
- **F8 · integrador** — sin archivos propios: rebase sobre `contract-1.11-frozen`, retira stubs, cose: `frozen.figures.items[].sha256
  == bundle.path_b.papers[].figures.items[].sha256 == sha de `_figures_for_panel`; `audit.panel[].saw_figures.sha256s ⊆
  frozen.figures.items[].sha256`; `stage.audit.judge.figures_sent == saw_figures.n`; `epistemic_summary.figures_n_verified ==
  frozen.figures.n_verified`; `record_pdf.pdf_sections_cover(frozen_keys) == {missing [], extra []}`; costura (O.2) si 0082 está
  mergeado; corre TODOS los smokes con la máscara (una .db por smoke), verifica `urlopen` 0 y `mcp_cache` byte-idéntico, `grep -c
  'figure-only' CLAUDE.md ≥ 1`, compose/README ⊇ 20 env, `grep figure precedent.py` = 0, corre `witt-webapp/tools/parity_check.py`
  EN LECTURA (esperados: `[registro] figures`, `[etapas] stage.figures.plan|paper|figure|summary`, `[rutas] 2 GET`, `[pdf]` 0 huecos
  y 23 'SALDADA'), sustituye "F8 mide" por conteos, etiqueta `contract-1.12-frozen`. Commits por rebanada en
  `feat/adr-0083-figuras-pdf` apilada sobre `feat/adr-0082-consejo` @ `contract-1.11-frozen`; sin push (Emmanuel). *(F8 entregado 2026-09-16 — sin git: el orquestador commitea; lo cosido está en el bullet «Integración F8» de la
  cabecera; la etiqueta `contract-1.12-frozen` la pone el orquestador al commitear.)*
- **Revisores (3, en paralelo sobre el árbol de F8):** R1 doctrina (clases de cifra; tres estados; nada afirma sin medir; §7 «figure-only»
  en cuatro sedes; el lazo D.4 cerrado; «lo que NO se hace»); R2 corrección (kill-switch byte a byte con EXACTAMENTE 3 excepciones;
  sha recalculado en gate/GET/PDF; presupuesto y latidos; caché LRU; fakes sin red; portabilidad sin `mcp_cache`); R3 contrato
  (formas de (L) vs código vs lista de paridad; vocabularios congelados; fixtures 1.12 generables; 52 secciones vs 50+2 llaves).
  **Corrector:** aplica los hallazgos marcándolos *(corrector)*, re-corre los gates, actualiza conteos.
- **Webapp (OTRO workflow, contra `contract-1.12-frozen`): W1** tipos + cliente + `src/lenguaje/figuras.ts` + `tests/figuras-lenguaje.test.ts`
  · **W2** Hoja (cita figure, Entrada `figuras`, `GateDeterminista.figures`, `PanelJueces`, Consumo) + `tests/hoja.test.tsx` ·
  **W3** Traza + Lista + M8 + tests · **W4** `parity_check.py` (segunda fuente `SECCIONES`, `PDF_NESTED` ampliado, (F) vocabularios),
  `parity_debt.json` (−23 líneas), `gen_fixtures.py` (`CONTRATO '1.12'`; `figures._get_bytes` fake + zip fixture del backend;
  `ENV_ADR_0083` quitadas del proceso, patrón `ENV_ADR_0081` :143-157). *(corrector — verificado en LECTURA sobre gen_fixtures.py
  @ witt-webapp)*: (i) `ENV_ADR_0080` hace `os.environ.pop('WITT_MCP_CACHE_DIR')` (:143-149) y NO la re-fija → `figures.cache_dir()`
  caería a `<repo>/mcp_cache/figures` del backend REAL y `figures.attach` lo CREARÍA y escribiría JPG en cuanto haya papers con XML
  seleccionados (la caché perezosa sólo protege cuando no hay nada que bajar): W4 DEBE fijar `os.environ["WITT_MCP_CACHE_DIR"] =
  str(TMP / "mcp_cache")` DESPUÉS del pop y antes de cada `execute_run` (jamás quitarla); (ii) el fixture de texto completo es hoy
  `raw_paper_PMC111_20260915.txt` (:466) y `figures.locate_xml` sólo casa `fulltext.*\.xml$` → los 47 regenerados saldrían con
  `figures.state 'no-papers-with-xml'`: `raw_cached` debe nombrar un `*_fulltext.xml` (copiar los 2 XML de
  `rag_index/query_service/fixtures/figures/`); (iii) `figuras-prosa-cc-by.json` (PMC8786916) y `figuras-licencia-desconocida.json`
  (PMC12161502) NO son generables desde los fixtures del backend (sus XML viven sólo en `mcp_cache`, untracked): se marcan SINTÉTICOS
  en el MANIFIESTO (XML autorados por W4 con `<license-p>` '(CC BY)' / sin `<permissions>`, patrón
  `epmc_fulltext_PMC90000001_synthetic_fulltext.xml` de smoke_run_pipeline).

**Fixtures 1.12 que la webapp necesitará (los genera `gen_fixtures.py` contra `contract-1.12-frozen`):** los 47 existentes regenerados
(todos ganan `figures {state …}`, `deterministic_checks.figures`, `saw_figures` por fila; el SINTÉTICO pre-1.1 sigue sin ellos) ·
`figuras-cc-by-embebibles.json` (PMC11379296: 9 parseadas, 9 verificadas, cc-by/ext-link, 2 citadas, vistas por 2 lentes,
`figure_readings` en ambas) · `figuras-nc-no-embebibles.json` (PMC11647118: 6 parseadas, `undfig1` `caption_state 'absent'` no
entregada, cc-by-nc/license-p-url, `embeddable False`, `panel_view True`) · `figuras-licencia-desconocida.json` (PMC12161502 SINTÉTICO — XML autorado por W4, corrector —
con figuras: `unknown`, `panel_view False`) · `figuras-prosa-cc-by.json` (PMC8786916 SINTÉTICO — XML autorado por W4 con '(CC BY)', corrector: `license-p-token`) · `figuras-kill-switch.json`
(`WITT_FIGURES=0`: `figures {state, kill_switch.declared_exceptions}`, cita paper intacta) · `figuras-vision-apagada.json`
(`WITT_FIGURES_VISION=0`) · `figuras-sha-alterado-inadmisible.json` (`mismatches[]`, `reasons` visible) · `figuras-id-no-resuelto.json`
· `figuras-solo-figuras-inadmisible.json` · `figuras-numerales-sin-respaldo.json` (informativo: `ok False`, admisible) ·
`figuras-sin-xml.json` (`no-papers-with-xml`) · `figuras-presupuesto-agotado.json` (`over_budget`, filas `budget-exhausted`) ·
`figuras-bytes-evicted.json` (índice con `servable 'bytes-not-in-cache'`) · `eventos-figuras.json` (los 4 eventos + `stage.audit.judge`
con `figures_sent`) · `figures-index.json` (GET /figures) · `figures-bytes-403.json` / `-404.json` / `-409.json` (sobres tipados) ·
`usage-figures.json`; el MANIFIESTO registra '1.12', el SHA del backend, qué bytes son reales (CC BY) y cuáles sintéticos (NC).

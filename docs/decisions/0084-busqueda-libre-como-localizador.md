# ADR-0084 — Búsqueda libre en internet como LOCALIZADOR, jamás fuente: Brave Search REST sin modelo (primario), Anthropic `web_search` como alterno explícito, resolutor DETERMINISTA URL→identificador, materialización SÓLO por Europe PMC con raw cacheado, y `frozen.web_locator` con URLs declaradas-contadas-jamás-citadas (contrato 1.13)

- **Status:** Proposed — 2026-09-16 (llevado al repo por W9 el 2026-09-16 desde el borrador del sintetizador; pasa a Accepted cuando
  Emmanuel apruebe OE1–OE5 — la obra las implementa con su DEFAULT declarado, ver «Decisiones abiertas»; conteos MEDIDOS por W7 el
  2026-09-16 — los 45 `smoke_*.py` exit 0 con la máscara; ver la tabla NO-SPEND y el bullet «Integración W7»; donde el borrador y el
  código entregado difieren en FIRMA o FORMA, el texto se adapta al código y lo marca *(W9: alineado al código)*). Origen:
  plan v3 del brief *Consejo de agentes* aprobado el 2026-09-14 — §6.4 «Búsqueda libre en internet: localizador, no fuente»
  (medido: `html.duckduckgo.com` y `lite.duckduckgo.com` devuelven captcha desde esta IP y sus ToS no autorizan automatización;
  SearXNG frágil; PRIMARIO Brave Search API REST stdlib con `X-Subscription-Token`; ALTERNO Anthropic `web_search` server-tool;
  REGLA: el localizador devuelve URLs, un resolutor DETERMINISTA extrae identificadores, lo resuelto entra por `fetch_external`
  con raw cacheado, lo no resuelto = `gap_flag 'web-located-unresolved'` con la URL, NADA del texto de la web entra al bundle),
  §3 R3 («la web es LOCALIZADOR … todo se resuelve a DOI/PMID/PMCID y entra por `fetch_external`»), §6.2 (fila `web` de
  `SEARCH_DISPATCH` como PLACEHOLDER) y la fila ADR-0084 de la tabla de ADRs (gate NO-SPEND: «respuesta Brave grabada → k
  resueltos entran por `fetch_external`, el resto `gap_flag` con URL; **0 ítems `source='web'`**»; regularización del precedente
  agéntico de 2026-05-14). **Apila sobre ADR-0083 (contrato 1.12)** — COMMITEADO en `feat/adr-0083-figuras-pdf` @ `7d9ce15` (tag
  `contract-1.12-frozen`); este ADR obra en un worktree apilado y asume las formas 1.12 tal como quedaron en el árbol. La webapp
  `witt-webapp` (@ `d41e4a8`, `feat/adr-0082…`) está en obra por OTRO workflow: aquí sólo se lista la paridad. Síntesis de tres
  diseños (doctrina-y-fidelidad · webapp-primero · operación-costo-riesgo) y dos juicios: parte del ganador (doctrina-y-fidelidad,
  33/40 y 35/40) e injerta lo que los dos jueces pidieron; donde los diseños o los jueces divergen, la decisión y su porqué van
  marcados *(síntesis)*. Estilo de cita: **ruta:función** con los números de línea del árbol @ `7d9ce15`, VERIFICADOS hoy
  (el nombre de la función es lo estable).
- **Decisiones YA tomadas por Emmanuel (no se relitigan aquí):** la web es LOCALIZADOR, jamás fuente — ningún texto ni snippet
  de la web entra al bundle de evidencia ni al sintetizador · sólo identificadores resueltos por CÓDIGO (DOI/PMID/PMCID/ZDB/
  ENSDARG/UniProt/GSE) entran, por el camino de hoy (`fetch_external`/`fetch_paper` con raw cacheado y ledger), con procedencia
  `web-located` declarada · lo no resuelto = `gap_flag 'web-located-unresolved'` con la URL (declarado, contado, jamás citado) ·
  Brave REST primario SIN modelo (stdlib; `BRAVE_API_KEY` en Dokploy — PENDIENTE de Emmanuel: hoy no hay llave; la obra se
  entrega con fixture SINTÉTICO declarado y el gate en vivo espera la llave) · Anthropic `web_search` alterno detrás de env
  (`WITT_WEB_LOCATOR ∈ brave|anthropic|off`, default brave si hay llave, off si no) · la familia `web` entra SÓLO por directiva
  del consejo (gate `directive-only`) o por env explícita de prueba, con presupuesto propio y límite de resultados · estados de
  fuente del vocabulario cerrado de ADR-0080 (+ los que hagan falta, declarados) · costo no es impedimento pero toda cifra con
  clase; el gasto de Brave/`web_search` se MIDE por ronda y viaja en el ledger · kill-switch restaura 7d9ce15 byte a byte ·
  smokes offline con fixtures · contrato ADITIVO 1.13 · toda llave nueva del frozen con sección en el PDF (gate 0083 K) y
  ranura en la webapp · proceso único `--workers 1`; SQLite/Postgres; §6 no-hang; §7.9 raw cacheado; la DI jamás se muta.
- **Relates:** ADR-0043 (tres estados) · ADR-0051 (tokens MEDIDOS, USD PROYECTADOS) · ADR-0053 (el gate es ciego a la
  procedencia; la procedencia se declara, no gatea) · ADR-0061 (cada componente que gasta cuadra en M8) · ADR-0062 (raw cacheado
  con procedencia; SDK/deep-research agéntica rechazados) · ADR-0074 (nada se recalcula en históricos) · ADR-0078 (pool de
  candidatos, dedup PMID/PMCID/DOI, selección top-n, `fetch_external` con read-cache por día) · ADR-0079 (`thread_context`
  viaja al planner y al sintetizador del hijo — canal de fuga que este ADR cierra para URLs) · ADR-0080 (harness: `SEARCH_DISPATCH`,
  rondas, `SOURCE_STATES`, `should_run_next_round`, `_inputs_for`, «nombrarla en la env ES la directiva del operador») ·
  ADR-0081 (tabla de modelos única; `ENV_TABLE`; `panel_signature`) · ADR-0082 (directivas del consejo: `query_en` ≤ 200,
  `harness_state`, `unsatisfiable-by-harness (tool-unavailable (ADR-0084))`, `GET /council/demand` como criterio MEDIDO de
  disparo, `gap_flags_typed`) · ADR-0083 (kill-switch byte a byte con EXACTAMENTE 3 excepciones — M.1; gate de cobertura del
  PDF — K; `ENV_SPECS` tolerante; `figure_predicates` como molde de predicados; `_FiguresUsageAccumulator`) · ADR-0085
  (sidecar Tool Universe: su criterio de disparo sigue MEDIDO por `/council/demand`, que este ADR conserva).
- **Affects:** `.tooluniverse/tools/brave_web_search.py` (NUEVO) · `analysis/scripts/lib/web_locator.py` (NUEVO) ·
  `search_harness.py` (fila `web` REAL, adaptador propio, disponibilidad dinámica, web PRIMERA en la ronda) ·
  `answer_pipeline.py` (admisión native-first, tie-break de selección, `block['web_locator']`) · `verify_output.py` (4 predicados
  web) · `council.py` (`harness_state_for` dinámica; recomputo al compilar) · `rag_index/query_service/council_index.py`
  (`DEMAND_FAMILIES` estático + `web_locator_provider_state`) · `runs.py` (contrato **1.13**; `frozen.web_locator`;
  `deterministic_checks.web_locator`; evento `stage.web.locate`; `token_usage.web_locator`; cuota inyectada) · `db.py` (tabla
  NUEVA `web_locator_usage`, sin ALTER) · `app.py` (`/usage += web_locator`; `/council/demand += web_locator_provider_state`;
  CERO rutas nuevas) · `models.py` (`ENV_TABLE` += 17 filas `adr '0084'`; `SNAPSHOT_FIELDS` += 2, FUERA de `panel_signature`) ·
  `record_pdf.py` (`SECCIONES` 52 → 53: `web_locator`/`localizador`) · `docker-compose.query.yml` · `README.md` ·
  `docs/decisions/README.md` · fixtures (SINTÉTICO Brave + SINTÉTICO Anthropic + golden del resolutor + golden del plan @ 7d9ce15)
  · smokes (4 NUEVOS + 9 tocados) · `analysis/scripts/smoke_live_web.py` (NUEVO, instrumento de los gates en vivo) · witt-webapp
  (tipar y pintar; ver *Consequences*). **Cero mutación de la DATA INAMOVIBLE, del registro congelado existente y de `mcp_cache`
  desde los gates; cero gasto de modelo en la obra; CERO red en los smokes (urlopen bloqueado y contado).** `fetch_paper.py`,
  `precedent.py`, `composite_auditor.py` NO se tocan *(síntesis: el alterno lleva caller PROPIO — ver (I))*.
- **Integración W7 (MEDIDO 2026-09-16 — máscara offline, UNA `.db` y UN `WITT_MCP_CACHE_DIR` temporal por smoke; `urlopen` bloqueado y
  contado == 0; `mcp_cache` byte-idéntico — digest `a2909387007c882d` en el worktree y en el árbol principal; sin gasto de modelo; sin git):**
  `smoke_run_pipeline.py` **402/402** (línea base 7d9ce15 372/372; con `runs.py` 1.13 antes de tocar el smoke 363/372 — las 9 rojas eran
  expectativas 1.12/keyset): contrato `'1.13'` + 3 excepciones + alias `WEB_KILL_SWITCH_STATE` · cableado `_load_tool('web') == ('locate', None)`,
  14 módulos, `web_quota` por firma == `db.web_locator_reserve` · prompt ciego · snapshot `web.locator`/`web.provider` · CUOTA cap=1: q1
  `under-cap {n_before 0, n_after 1, hook ctx.web_quota}` 1 GET, q2 `skipped-cap (monthly cap WITT_WEB_MONTHLY_CAP=1 reached (n_queries=1,
  month 2026-09))` `cap-reached` 0 GETs, fila del mes `n_queries 1 n_results 6 USD 0.005`, `token_usage.web_locator` bajo skipped-cap · (a) Traza
  `search.plan (families[0] web) → stage.web.locate ×1 (agent web_locator) → search.source(web) primera → search.round → path_b → pass2`; la
  llave SÓLO en cabecera · `frozen.web_locator located {n_queries 1, n_results 6, n_located 5, n_unresolved 1, n_materialized 3,
  n_not_found_in_europepmc 1, n_already_present_pool 1, n_admitted 2, n_papers_web_located 2, gap_flags_typed 2, cost 1×0.005 'proyección',
  quota under-cap, 12 reglas}` · `located[]` cerrados (PMID 333 y DOI 666→PMID 888 materialized/admitted/selected/fetched True; 111
  `already-present (dup of PMID:11111111)` pool_dedup; `notfound84` `not-found-in-europepmc`; ZFIN `fed-same-round ctx:curies`) · papers 0 con
  `source 'web'`, 2 web-localizados `source 'europepmc'` / `source_family 'web'` / `identifier_provenance 'web-located:*'`, `url` canónica;
  `'WEB TITLE'`/`description` AUSENTES de todo el `bundle_json` · `deterministic_checks.web_locator checked`, 3 DUROS ok, conjunción, admisible ·
  `answer.gap_flags` == los 2 strings de CONTEO sin URLs · `citations[].located_via ['web', null]`, `n_located_via_web 1` · `token_usage.web_locator
  {brave, 1/1, 0.005}`, `estimated_cost_usd` intacto, total == +0.005, `by_stage.search {0, 0, note, web_locator_usd_projected 0.005}`,
  `by_stage_sum_matches_by_model True` · `epistemic {located, 5, 1}`; agents `invoked` `web_locator:5/6` · 0 texto web en el `user_text` de pass2,
  de las 4 lentes y de r3 · 0 URLs en eventos; payload de `stage.web.locate` íntegro · fila web del `search_ledger` SIN `web_locator` anidado
  (`web_locator_frozen_at`), 0 URLs en el frozen fuera de `web_locator` · `coverage_after_search.by_requirement[web].web_locator` + `retrieved-for` ·
  `thread_context` del hijo con los conteos y sin URLs/`title_web`/`canonical_url` · DOI→`ctx:dois` y curie→`ctx:curies` en la MISMA ronda, idents
  EPMC en forma · (b) cita URL fabricada → `web_text_not_cited id-is-url` → inadmisible · (c) kill-switch con directiva y llave: excluida con
  `'unsatisfiable-by-harness (tool-unavailable (ADR-0084))'`, `harness_state_recomputed True`, 0 `stage.web.*`, 0 GETs, `frozen.web_locator` == 6
  llaves EXACTAS, `dc {state}`, sin fila web, sin `token_usage.web_locator`, sin `located_via`, epistemic null · (d/e) M.1 ON vs OFF mismo fixture
  sin directiva web: diff == ∅ tras restar aditivas 1.13 + identidad; ON `not-requested (no web directive)` / `no-web-items` · (f) `brave` sin
  llave: `'unsatisfiable-by-harness (tool-unavailable (ADR-0084: BRAVE_API_KEY unset))'`, frozen `'tool-unavailable (ADR-0084: BRAVE_API_KEY
  unset)'` sin contadores, `dc {state}`, fila `tool-unavailable`, 0 GETs · (g) competente: `'not-requested (no search round)'` · (h) alterno
  Anthropic con `_post_json` falso: `n_results 5`, `cost {10.0/1k, 1 facturable, 0.01, tokens {1480, 92, medición, claude-opus-5}}`,
  `by_stage.search {1480, 92, model, state measured}`, `by_stage_sum True`, 0 GETs Brave, prosa del despachador ausente · assert GLOBAL sobre la BD:
  0 URLs de fixture / `'WEB TITLE'` / `description` / llave fuera de `web_locator` y en `run_events`; vocabularios cerrados en las 10 corridas.
  `smoke_web_quota_db.py` **15/15** (NUEVO: tabla EXACTA `(id, month, provider, n_queries, n_results, cost_usd_projected, updated_at)` + UNIQUE
  `(month, provider)`; `init_db` idempotente; `_migrate` no la menciona; DDL Postgres `SERIAL`/`TIMESTAMP WITH TIME ZONE`/`FLOAT`; reserve(cap 3)×4 →
  granted `[T,T,T,F]`, n_after `[1,2,3,3]`; 8 hilos cap 5 → EXACTAMENTE 5 granted, fila 5, 0 excepciones; otro mes/proveedor = otra fila; cap 0 concede
  y cuenta; `record=` suma `n_results 10` / `cost 0.01`, `granted None`; `month_to_date` con y sin fila (ceros MEDIDOS, `row_present False`);
  `usage_months` 6 filas ordenadas; SQL portable — sin `RETURNING`/`ON CONFLICT`/`INSERT OR IGNORE`, `rowcount`; costura W2↔H
  `locate(quota_fn=db.web_locator_reserve)` cap 1 → `under-cap` + `skipped-cap` con detail y 1 llamada al proveedor fake) · `smoke_usage_http.py`
  **39/39** (34 → +5: `/usage.web_locator` sin corridas 1.13 `'not-measured'` con `n_runs_locator_off 4`, conteos null, `month_to_date {under-cap,
  n_queries 0, row_present False, cap 900 'default', credit 5.0}`; con una corrida 1.13 sembrada + 2 reservas y 2 `record=`: forma cerrada de 21
  llaves, `state 'measured'`, `n_queries 2`, `n_queries_billable 2`, `n_results 12`, `n_located 7`, `n_materialized 4`, `n_unresolved 3`, `rate
  0.5833`, `cost 0.01`, `by_provider.brave {n_runs 1, n_queries 2, 0.01, 5.0}`; `month_to_date` leída de la tabla `{mes UTC, row_provider brave,
  provider 'off', n_queries 2, n_results 12, 0.01, cap 900, remaining 898, under-cap, row_present True, rows[]}`; `totals.estimated_cost_usd` ==
  golden + 0.0045 SIN el USD del localizador; `estimated_cost_usd_total_projected 0.0145` aparte) · `smoke_models.py` **102/102** (96 → +6:
  `ENV_TABLE` 85 = 21+27+20+17, `ENV_ADR_0084` en el orden del ADR, `BRAVE_API_KEY` fuera; `SNAPSHOT_FIELDS` 37 con `WEB_SNAPSHOT_FIELDS` al final;
  paridad de literales con `web_locator.ENV_SPECS` (defaults string, kinds mapeados, clamps min/max, 8 defaults tipados); `env_value 'BRAVE'`→`brave`,
  `'zzz'`→`''` `default-invalid-env`, `MAX_RESULTS 50` → default 10 vs `web_locator` recorta a 20 y lo declara, `MONTHLY_CAP '0'` → 0,
  `LOCATOR_MODEL` fuera de tabla rechazado; `models.py` stdlib-only con `web.provider == web_locator.provider_state` en 8 combinaciones; snapshot
  `web.locator`/`web.provider` con fuente, la llave jamás en el snapshot, `panel_signature` == golden 9d90c01 con `brave`/`off`; `ENV_TABLE ⊆ compose
  ∩ README` para las 17; `BRAVE_API_KEY` en compose `${BRAVE_API_KEY:-}` con «never git» y en README) · `analysis/scripts/smoke_live_web.py
  --dry-run` **exit 0** (NUEVO; único modo del CI: `{'mode': 'dry-run', 'db_imported': False, 'urlopen_calls': 0, 'ok': True}`; Brave `url_sent`
  `…/res/v1/web/search?q=wt1a+zebrafish+pronephros+podocyte&count=10&search_lang=en`, `params_sent ['q', 'count', 'search_lang']`,
  `params_documented_only True`, `token_in_url False`; Anthropic `has_tool_choice False`, `tool_type 'web_search_20250305'`, `max_uses 1`,
  `allowed_domains_equal_list True`, `n_tools 1`, `has_blocked_domains False`; `provider_state off default-derived:BRAVE_API_KEY absent`; resolutor
  sobre el fixture SINTÉTICO de W1: 11 resultados, 9 located, 2 unresolved — researchgate y wikipedia `no-identifier-pattern`) ·
  `smoke_record_pdf.py` **68/68** (los 6 checks etiquetados W7 de W8 verdes: `frozen_keys` 53, frozen real cerrado 53 llaves con `web_locator`
  contrato 1.13, cobertura EXACTA `{missing [], extra []}`, frozen ABIERTO extra == `[closed_by, frozen_at]`, PDF real sin «NO INSTRUMENTADO»,
  registro figuras exacto) · los **44 smokes restantes 44/44 exit 0** (`smoke_tools_c` 68/68 tras corregir un `mailto:` del fixture de W2;
  `smoke_tools_d` 50/50 con fixture `provenance: synthetic`; `smoke_web_locator` 170/170 (corrector 182/182); `smoke_web_pipeline` 29/29 (corrector
  32/32); `smoke_search_harness` 91/91 (corrector 94/94); `smoke_gate_citations` 100/100; `smoke_council` 77/77 (corrector 78/78) · `smoke_council_index`
  67/67 · `smoke_council_http` 76/76; la lista completa en la tabla
  NO-SPEND) — **45/45 exit 0 con `smoke_run_pipeline`**. Árbol del worktree: 21 archivos M (todo bajo `analysis/`, `rag_index/`) + 11 nuevos
  (`.tooluniverse/tools/brave_web_search.py`, `analysis/scripts/lib/web_locator.py`, `analysis/scripts/smoke_live_web.py`, 4 fixtures —
  `brave_web_search_SYNTHETIC_wt1a_20260916.json`, `anthropic_web_search_SYNTHETIC_wt1a_20260916.json`, `web_locator_urls_golden.json`,
  `golden_plan_web_directive_7d9ce15.json` —, `smoke_tools_d.py`, `smoke_web_locator.py`, `smoke_web_pipeline.py`, `smoke_web_quota_db.py`); el
  literal de exclusión `'unsatisfiable-by-harness (tool-unavailable (ADR-0084))'` vive UNA vez en `search_harness.py` (0 en runs/app/db/models);
  `"stage.web.locate"` 1 vez en `runs.py`; árbol principal `witt-organogenesis` intacto (status vacío); sin `git add/commit/checkout/tag`.
- **Anclas @ 7d9ce15 (verificadas hoy):** `search_harness.py` (1 321 líneas): `SOURCE_STATES` :93-94 · `INPUT_MODES` :98 ·
  `SEARCH_DISPATCH` :112 (fila `web` :168-170 con `unavailable_reason 'tool-unavailable (ADR-0084)'`) · `_STATEMENT_KEYS`/`_URL_KEYS`
  :183-184 · `_load_tool` :242 · `_free_query` :280 · `QUERY_SOURCE_DIRECTIVE_PREFIX` :299 · `build_search_plan` :348 (unión
  `directives+default` :388-395; exclusión `unsatisfiable-by-harness` por `tool_module is None and adapter is None` :414-421;
  `free-query` con directivas: `query_replaced` + `directive_queries[]` :471-483) · `should_run_next_round` :565-571 ·
  `inputs_signature` :574 · `families_with_new_inputs` :600 · `normalize_item` :639 (`search_rec.pmcid None` :696) · `_row` :744 ·
  `_inputs_for` :786 · `_run_workspace_family` :835 · `_run_legacy_family` :1001 (`_epmc_items`: `source_family 'europepmc'`,
  `identifier_provenance 'europepmc-api-live'`, `url` canónica :1038-1048) · `run_source` :1148 (rama `adapter` :1156) · `run_round`
  :1176 (`_ctx_list` :1205-1209; cosecha de DOI/curie ANTES del dedup :1252-1263) · `round_event_payload` :1300 ·
  `source_event_payload` :1312. `answer_pipeline.py` (1 387): `PATH_B_SELECTION_RULE` :147 · `_SEARCH_REC_KEYS` :595 ·
  `_fetch_or_declare` :712 · `_normalize_doi` :723 · `_candidate_keys` :732 · `_epmc_candidate` :745 · `_pool_add` :754 ·
  `_select_top_n` :770 · `_paper_item` :894 · `_path_b_harness` :1015 (ctx pre-crea `dois`/`curies` :1050; `_pool_add` por
  `kind 'literature-candidate'` :1074-1082; stop `found-new` :1099-1105; `_select_top_n(pool, n, families)` :1109; copia de
  `kind/source_family/label/identifier_provenance/url/round/directive_requirement_ids` al paper :1116-1120) · `path_b_bundle`
  :1135 (`ran_sources` :1174-1181; `n_results_by_source` :1194) · `path_b_event_payload` :1203 (:1239). `fetch_paper.py` (467):
  docstring «ident = free-text | PMID | PMCID | DOI | URL» :10 · `_normalize_hit` :171 · `search_europepmc_ledger` :190 (NO escribe
  caché) · `_ident_query` :259 · `_resolve_one` :274 (top hit) · `_cache_lookup` :295 (glob `raw_paper_*` :309-310) · `fetch_external`
  :345 (read-cache :357-362; `full_text_skipped_reason 'cache-hit-abstract-only'` :391-395; `raw_ref` :403). `verify_output.py`
  (1 132): `ENSDARG_RE/PMID_RE/GEO_RE` :39-42 · `admissible(extra_predicates)` :227 · `count_valid_citations` :295 (cuenta CUALQUIER
  id no vacío) · `_citation_keys` :399 (acepta `HTTPS://DOI.ORG/` :414-415) · `_bundle_evidence_index` :439 · `support_state_for`
  :528 · `FIGURE_CHECK_STATES_EXACT/_PREFIXES` :638-639 · `_block`/`_mk_pred` :800-813 · `figure_predicates` :821. `runs.py`
  (5 200): `RENDER_CONTRACT_VERSION = "1.12"` :51 · `SYNTH_TOOL` enum de `kind` :289-291 (incluye `'other'`) · `_default_planner`
  :499 (`payload["thread_context"]` :515) · `_agents_invoked` :892 · `_gap_flags_tolerante` :1141 · `build_thread_context` :1185
  (`previous_answer.gap_flags` :1247) · `_PROMPT_PATH_B_TOP` :1542 · `_PROMPT_PAPER_KEYS` :1550 · `_prompt_path_b` :1574 ·
  `_compact_evidence` :1608 · `_default_synthesizer` :1720 (`payload["thread_context"]` :1739) · gap_flags apilados por código
  :1750-1841 · `_normalize_citations` :1895 · `TOKEN_STAGES` :1961 · `_usage_by_stage` :2138 (`search` nota :2151) · `_token_usage`
  :2226 (`by_stage_sum_matches_by_model` :2351; `estimated_cost_usd` :2372; `cost_class` :2377-2384; espejo `figures` :2386-2400) ·
  `_search_config` :2451 · `_citations_of` :2512 · `_figure_checks` :2562 · `_gate` :2594 (conjunción :2612-2617) ·
  `_path_b_bundle_accepts` :2678 · `_path_b_via_harness` :2689 · `_search_ledger_of` :2708 · `FIGURES_KILL_SWITCH_STATE` :3010 ·
  `FIGURES_DECLARED_EXCEPTIONS` :3012 (EXACTAMENTE 3) · `synth_thread_snapshot` :3918-3920 · `_synth` :3947-3955 · llamada a
  `_path_b_via_harness` :4213 · `stage.path_b` :4238 · `"figures": figures_holder["summary"]` :4678 · `"deterministic_checks"`
  :4696 · `frozen["thread_context"]` :4726 · `epistemic_summary` :4830-4858. `council.py` (2 024): `COUNCIL_EVIDENCE_KINDS` :111
  (derivado de `SEARCH_DISPATCH` ∪ `{'figure'}`) · `DIRECTIVE_STATES` :97 · `HARNESS_STATES_EXACT/_PREFIXES` :102-103 ·
  `harness_state_in_vocabulary` :129 · `STR_CAPS['query_en'] = 200` :166 · `harness_state_for` :1433-1444 · `directives_from` :1839
  (`req.get("harness_state") or harness_state_for(…)` :1863) · `AFTER_SEARCH_RULE` :1898 · `coverage_after_search` :1917.
  `council_index.py` (1 005): `UNSATISFIABLE_FAMILIES` derivadas EN IMPORT por `fn is None` :82-88 · `DEMAND_FAMILIES` :90 ·
  `_is_unsatisfiable` :864-872 · `demand` :890 (:956, :961-962). `app.py` (2 981): `GET /resolve` :224 · `GET /council/demand`
  :2039 · `_FiguresUsageAccumulator` :2282 · `GET /usage` :2560 (`totals` :2606-2609). `record_pdf.py` (1 902): `KEY_BORN` :119-138
  · `SECCIONES` :150 (52 filas; `figures` :179) · `ORDEN_SECCIONES` :207-232 · asserts :234-236 · `_tres_estados` :309 ·
  `pdf_sections_cover` :322 · `_section_busqueda` :732 · `_section_figuras` :1224 · `_section_gate` :1434 (`conocidas` :1495-1498).
  `db.py` (2 308): `run_events` :161 · `config_history` :291 (nace por `create_all` :318; `_migrate` :322 sólo `ADD COLUMN`).
  `models.py` (1 161): `PRICES_AS_OF` :51 · `PIPELINE_ROLES` :185 · `COUNCIL_ROLES` :190 (fuera de `panel_signature` a propósito)
  · `ROLE_ENVS` :197 · `ENV_TABLE` :283 (sin filas de secretos) · `SNAPSHOT_FIELDS` :378 · `FIGURES_SNAPSHOT_FIELDS` :396 ·
  `resolve_role` :778 · `panel_signature` :838 (itera `PIPELINE_ROLES` :845). `resolve_id.py`: `resolve` :117-131 (símbolo, ENSDARG,
  UniProt, RefSeq — NO PMID/DOI/ZDB/GSE). `net_throttle.py`: `Throttle` :44 · `get_throttle` :81 · `retry_once_on_429` :122.
  `composite_auditor.py`: `ANTHROPIC_URL/VERSION` :136-137 · `_INFLIGHT` :353 · `_anthropic_tool_call` :746 (`tool_choice`
  FORZADO :778). `.tooluniverse/tools/openalex_search.py` (417): `DEFAULT_TIMEOUT_S` :83 · `_get` :96 · `query_openalex` :228
  (`api_key_present` :236; `cache_hit` :273) · `_cache_write` :357 · `__main__` :410. `unpaywall_crossref.py` `tool-unavailable`
  sin correo, cero red :277-279. Smokes que HOY fijan `web` como no satisfacible ESTÁTICA (se actualizan en sus rebanadas):
  `smoke_run_pipeline.py:2453` (`_load_tool("web") == (None, None, "tool-unavailable (ADR-0084)")`), `smoke_search_harness.py:189-191`
  y `:248-252`, `smoke_council.py:361-365`, `smoke_council_index.py:467-471`, `smoke_council_http.py:288-291` (fixture con literal
  propio `'unsatisfiable-by-harness (web: tool_module None)'`). Kill-switch molde: `smoke_run_pipeline.py:5034-5036` (3 excepciones)
  y `:5561-5564` (M.1: diff de paths == ∅ contra la corrida ENCENDIDA del MISMO fixture). Precedente: `mcp_cache/
  literature_pronephros_essentiality_20260514.json` (`query_method 'WebSearch + WebFetch on PMC articles'`) y
  `mcp_cache/literature_pronephros_proteomics_20260514.json` (`query_method 'WebSearch + WebFetch'`) — AMBOS existen; `.gitignore:104`
  `mcp_cache/`; sus únicos lectores son dos reports históricos (`reports/proteomic-evidence-pronephros-windows-v1*.md`).
  `record_fixtures_c.py` NO existe en el árbol (los `_fixture.recorded_by` lo nombran; medido: 0 archivos).
- **Corrector (2026-09-16 — tras R1 doctrina / R2 corrección / R3 contrato; cada hallazgo VERIFICADO contra el código antes de aplicarlo;
  marcado *(corrector)* donde cambia una decisión o una forma):** APLICADOS — (1) **D.3 ↔ E.3** (alta): un paper web-localizado SELECCIONADO
  cuyo `fetch_external` no lo entregó conservaba el abstract del registro de EPMC y `web_items_native_only` (DURO) volvía INADMISIBLE toda la
  respuesta por un timeout transitorio → `_paper_item` RETIENE el texto (`text_provenance 'none'`, `text_withheld_reason
  'web-located-not-fetched (ADR-0084 D.3)'`); E.2 sigue gateando la CITA · (2) **dedup por PAPER en la familia** (alta): el mismo paper como
  pubmed + PMC + doi.org producía 3 GETs, 3 candidatos y un ledger duplicado de sí mismo → `seen_keys` por `_candidate_keys` del registro,
  `already-present (dup of <eid>)` + `same_paper {layer 'family'}`, `n_same_paper_dups`; `_web_mark_pool_duplicate` cierra SÓLO la fila de
  origen (`located_ref`) y `n_already_present_pool` cuenta filas marcadas · (3) **kill-switch + web nombrada en la env** (media): el plan
  reordenaba y la ronda dejaba una fila rica → sólo con el localizador DISPONIBLE hay reorden/`families_order_rule`/`entered_by`/`WITT_WEB_TEST_QUERY`;
  sin él `run_source` devuelve la fila MÍNIMA de 7d9ce15 (mismo keyset que una familia con `fn None`; único valor distinto: `host`, el de la
  tabla C.1) · (4) **tipo de server-tool** (media): `WITT_WEB_ANTHROPIC_TOOL_TYPE` es VOCABULARIO cerrado (`ANTHROPIC_TOOL_TYPES`), la fila-query
  copia `tool_type / provider_property / n_text_blocks_discarded / request_shape / stop_reason …` y `cost.provider_detail` existe · (5) **literales del
  consejo** (media): `DIRECTIVES_RULE` y `AFTER_SEARCH_RULE` vuelven a los de 1.12 BYTE A BYTE; la ampliación web viaja en `availability_rule`
  (sólo con recomputo) y `web_locator_rule` (sólo con ledger web NO vacío) → la enumeración «3 excepciones» del frozen es VERDAD para el mismo
  fixture sin datos web (`runs.WEB_ADDITIVE_KEYS_WITH_WEB_DATA` enumera lo que sólo existe con datos web; `epistemic_summary` es otra columna,
  no el frozen) · (6) **resolutor `wlr-2`** (media): sufijos de publisher (`/full`, `/pdf`, `.pdf`, `/figures/1`, `/abstract`, `.article-info`,
  `/` final) recortados del DOI, PMC case-insensitive, `europepmc.org/articles/PMC<n>`; golden +10 casos, re-sellado · (7) **timeout EPMC**
  (media): la materialización corre por `search_europepmc_ledger(<consulta por ident>, n=1, timeout=<presupuesto restante>)` (`fetch_paper` NO
  se toca) · (8) **eventos** (media): `stage.search.plan += families_order_rule?`, `stage.path_b.selection += pool_admission_rule? /
  tie_break_web_located?` · (9) **contrato** (media): (7)/(8)/(13)/(6) de «tipar y pintar» corregidos al keyset MEDIDO · BAJAS: cuota cuenta
  peticiones facturadas (`n_requests_extra`); INSERT de la fila del mes en transacción PROPIA (Postgres); `record mismatch` de EPMC (trampa del
  top hit); DOI entre comillas si trae sintaxis EPMC; UNA cadena en `ctx:dois` (forma del registro, sin duplicar por mayúsculas);
  `WITT_WEB_LANG=""` apaga `search_lang`; `agents_invoked` `not-applicable (skipped-cap …)` sin `None` incrustado; forma «sin ronda» del frozen
  unificada con la «no medido» (`cost` 0 facturables); `stage.web.locate` UNO por consulta DECLARADA (+ `detail?/error?`); CLAUDE.md §6 preciso.
  RECHAZADOS — `gen_fixtures.py` (vive en `witt-webapp`, OTRO workflow: se documenta la receta de 4 hooks en «Fixtures», no se toca);
  «no emitir `epistemic_summary.web_*` bajo off» (patrón de 0083 `figures_state`: la columna `epistemic_summary_json` no es el frozen).
  Gates re-medidos por el corrector: `smoke_run_pipeline` **407/407** (W7 402) · `smoke_web_locator` **182/182** (170) · `smoke_web_pipeline` **32/32** (29) · `smoke_search_harness` **94/94** (91) · `smoke_web_quota_db` **17/17** (15) · `smoke_council` **78/78** (77) · `smoke_models` **102/102** · `smoke_gate_citations` 100/100 · `smoke_council_index` 67/67 · `smoke_council_http` 76/76 · `smoke_usage_http` 39/39 · `smoke_record_pdf` 68/68 · `smoke_tools_d` 50/50 · los 32 restantes sin cambio — **45/45 exit 0** + `smoke_live_web.py --dry-run` exit 0; `urlopen` bloqueado y contado == 0 en todos; UNA `.db` y UN `WITT_MCP_CACHE_DIR` temporal NUEVOS por smoke (0 archivos en la caché temporal salvo `smoke_figures` 16, `smoke_web_pipeline` 24 raw_brave_*/raw_paper_* del tempdir, `smoke_web_locator` 2, `smoke_tools_d` 1 — todos en el tempdir del smoke, `mcp_cache/` del repo intacto); sin red, sin gasto de modelo, sin git.

## Context

1. **Hoy la familia `web` es un PLACEHOLDER que el consejo cuenta y el harness excluye — y el literal es un contrato vivo.**
   `SEARCH_DISPATCH['web'] = {tool_module None, fn None, adapter None, inputs 'free-query', budget_s 0.0, host None, key_env None,
   evidence_kind 'web', gate 'directive-only', unavailable_reason 'tool-unavailable (ADR-0084)'}` (search_harness.py:168-170).
   `build_search_plan` la excluye cuando entra SÓLO por directiva con `reason f"unsatisfiable-by-harness ({unavailable_reason})"`
   (:414-421) → el literal EXACTO `'unsatisfiable-by-harness (tool-unavailable (ADR-0084))'`; `council.harness_state_for` lo
   reproduce cuando `fn is None and tool_module is None` (:1433-1444); `council_index.UNSATISFIABLE_FAMILIES` se deriva EN IMPORT
   por `fn is None` (:82-88) y `_is_unsatisfiable` cuenta por PERTENENCIA (:864-872) → `GET /council/demand.
   n_requirements_unsatisfiable_by_family.web` (:956) es la serie MEDIDA que el brief nombra como criterio de disparo. Cinco smokes
   afirman ese estado estático (Anclas). Consecuencia: al poner `tool_module`/`fn` reales en la fila, HOY el criterio `fn is None`
   la volvería «satisfiable» AUNQUE no haya llave (directivas compiladas a un tool muerto; `must_uncovered` gateando la
   competencia por un localizador no configurado; `demand` dejaría de contar la demanda web) — y si se deja estática
   «unsatisfiable», al llegar la llave el consejo contaría demanda pero jamás despacharía. *(síntesis: los tres diseños coinciden
   en una DISPONIBILIDAD en tiempo de llamada; el juez 2 añade que `demand()` debe seguir contando `web` aunque el localizador
   esté disponible — ver (F).)*
2. **`normalize_item` convierte CUALQUIER elemento del tool en un ítem con forma de evidencia: la única barrera estructural es
   NO pasar por él.** `_STATEMENT_KEYS = ("statement","title","display_name","protein_name","name","description")` y
   `_URL_KEYS = ("url","link")` (:183-184); el ítem gana `text`, `url`, `search_rec {…, pmcid None, title (title or statement)[:300]}`,
   `text_excerpt`, `text_provenance 'abstract'` (:683-706). Un resultado de Brave normalizado por `_run_workspace_family` (:835)
   sería `title`+`description` de la web dentro de `papers[]`, de `_compact_evidence` y del prompt del sintetizador. Por eso la
   familia `web` corre por un ADAPTADOR PROPIO (`run_source` ya despacha por `spec.get("adapter")` :1156) que NO emite ítems web.
3. **El sintetizador es CIEGO al ledger por LISTA BLANCA — y hay un canal de fuga hacia el turno siguiente que sólo un diseño
   vio.** `_prompt_path_b` proyecta el bloque por `_PROMPT_PATH_B_TOP` (:1542-1544: `triggered, triggered_by, reason,
   ledger_version, query_sent, query_sent_scope, query_source, epmc_query, pubmed_query, zfin_filter, n_results_by_source,
   sources_requested, n_papers_requested`) y cada paper por `_PROMPT_PAPER_KEYS` (:1550-1551: `source, evidence_id, search_rec,
   selection_rank, text_provenance, text_excerpt, text_excerpt_omitted, text_excerpt_rule`) — ni `url`, ni `search_ledger`, ni
   `web_locator`: un bloque `path_b.web_locator` es INVISIBLE para el modelo por construcción. PERO `answer.gap_flags` se copia
   a `previous_answer.gap_flags` (:1247) y el snapshot viaja como `thread_context` al planner (:515) y al sintetizador del hijo
   (:1739, :3955): una URL puesta en `answer.gap_flags` («gap_flag con la URL», brief §6.4 leído literalmente) llegaría al MODELO
   del turno siguiente. *(síntesis: veredicto unánime de los jueces contra el diseño B — la URL vive en `frozen.web_locator`
   tipado, humano y PDF; `answer.gap_flags` recibe UN string de CONTEO por clase; así «con la URL» se cumple donde la lee un
   humano y jamás donde la lee un modelo.)*
4. **El camino nativo YA sabe materializar identificadores — y tiene DOS trampas que este ADR esquiva por diseño.**
   `_ident_query` acepta `PMID:<n>`, `PMC<n>`/`PMCID:<n>` y `DOI:<v>`/`10.…` (fetch_paper.py:259-270) y todo lo demás es TEXTO
   LIBRE cuyo TOP HIT toma `_resolve_one` (:274-278): un título o una URL entregados como ident atarían un paper EQUIVOCADO con
   apariencia de resuelto → el camino web entrega a EPMC SÓLO idents que casan `^PMID:\d+$ | ^PMC\d+$ | ^10\.\S+$` (smoke +
   predicado estructural). Y `fetch_external(ident, want_full_text=False)` escribe `raw_paper_<cid>_<stamp>.json/.txt`; una
   llamada posterior con `want_full_text=True` sirve el read-cache abstract-only con `full_text_skipped_reason
   'cache-hit-abstract-only'` (:391-395) — materializar en la ronda con `fetch_external` ENVENENARÍA el fetch completo del paper
   seleccionado. La verificación de EXISTENCIA en tiempo de ronda se hace con `fetch_paper._resolve_one(ident)` (UNA GET a la
   búsqueda de EPMC, `n=1`, paceada por `_throttle` :127-133, **sin escribir caché**: `search_europepmc_ledger` :190-236 no
   persiste) y el raw §7.9 lo escribe `_paper_item` → `fetch_external` cuando el paper se SELECCIONA, como hoy (:894-905).
5. **La «siguiente ronda» es un camino MUERTO para alimentar familias; sólo el orden dentro de la ronda encadena.**
   `should_run_next_round(k, n_new_total, cap, inputs_changed)` exige `n_new_total == 0` (:565-571) y `_path_b_harness` para en
   `'found-new'` en cuanto algo se admite (:1099-1105): si `europepmc` (o la propia web) admite un candidato, NO hay ronda 2 y
   un DOI/curie cosechado por la web jamás llegaría a `unpaywall_crossref`/`monarch`. `run_round` cosecha `search_rec.doi` →
   `ctx['dois']` y `zfin_curie 'ZFIN:…'` → `ctx['curies']` ANTES del dedup (:1252-1263) y `_inputs_for` los lee en tiempo de ronda
   (:800-803) — el encadenado funciona EXACTAMENTE cuando la familia productora va ANTES en `plan.families` (ADR-0080 frontera (c)).
   *(síntesis: el ganador prometía «fed-next-round vía families_with_new_inputs» — FALSO por :565-571; se adopta «web PRIMERA en la
   ronda cuando entra» del diseño C, PERO neutralizando su efecto sobre la selección: ver (D) y Context 6.)*
6. **Orden de RONDA ≠ orden de SELECCIÓN — hoy son la MISMA lista, y la identidad de un paper la fija el PRIMERO visto.**
   `_path_b_harness` pasa `families` tanto a `run_round` como a `_select_top_n(pool, n, families)` (:1109); `_select_top_n` ordena
   por `(0 si OA+PMCID, rank de c['source'] en `sources`, índice de llegada)` (:770-787) y `_pool_add` da la identidad al primer
   candidato con esa llave y declara al segundo en `selection.duplicates[] {duplicate, source, of, matched_key}` (:754-767).
   Poner `web` primera SIN más haría que sus candidatos ganaran identidad y rango sobre los de EPMC/PubMed — «el localizador
   desplaza a las fuentes nativas» (hallazgo de ambos jueces sobre C). Este ADR separa los tres efectos: orden de ronda (web
   primera), admisión al pool (native-first dentro de la ronda) y selección (tie-break `native-before-web-located`) — (D).
7. **La forma del `evidence_id` decide en QUÉ capa cae el duplicado.** `run_round` deduplica por `evidence_id` (:1264-1268) y
   `_pool_add` por llaves `PMID:<n> | PMCID:<PMC…> | DOI:<doi normalizado>` (:732-743). `_epmc_candidate` fija el `evidence_id`
   nativo como `PMID:<n>` si hay PMID, si no el `pmcid` crudo, si no el `doi` crudo, si no `EPMC:<id>` (:745-751). Un candidato
   web con `evidence_id 'DOI:<doi>'` escaparía al dedup de la ronda y caería en `_pool_add` (contado en `selection.duplicates`,
   no en `round.duplicates`). Este ADR construye el candidato web-localizado CON `_epmc_candidate(rec)` sobre el registro que EPMC
   devolvió — misma forma, mismas dos capas.
8. **`count_valid_citations` cuenta CUALQUIER id no vacío y `_citation_keys` acepta `https://doi.org/<doi>`.** :295-311 y
   :399-416. Dos consecuencias: (a) una afirmación positiva sostenida SÓLO por una cita a un paper web-localizado que EPMC no
   materializó pasaría `positive_claim_requires_citations` — hace falta un predicado DURO sobre la CITA (`fetched.found` del
   ítem), no sólo sobre el ítem *(injerto de C, veredicto de ambos jueces)*; (b) un predicado ingenuo «ningún `id` que empiece
   por `https?://`» volvería inadmisible la forma `https://doi.org/<doi>` que el gate ya resuelve — el predicado normaliza
   `doi.org` → DOI antes de juzgar y sólo ofende URLs que NO resuelven a un ítem del bundle o que casan con el ledger web
   *(hueco del juez 2)*. El enum de `evidence_cited.kind` incluye `'other'` (runs.py:289-291): el predicado mira el `id`, no el `kind`.
9. **Brave Search API — VERIFICADO hoy por WebFetch (2026-09-16).** Endpoint `GET https://api.search.brave.com/res/v1/web/search`
   con cabecera `X-Subscription-Token` (api-dashboard.search.brave.com/app/documentation/web-search/get-started y …/query);
   parámetros DOCUMENTADOS: `q` (obligatoria; **longitud NO documentada**), `count` (default 20, «max 20»), `offset` («max 9»),
   `country` (2 letras), `search_lang` (ISO 639-1), `ui_lang`, `safesearch`, `freshness` (`pd|pw|pm|py` o rango), `extra_snippets`
   (bool); **NO documentados en esa página: `result_filter`, `text_decorations`, `spellcheck` (sólo en changelog), `summary`**.
   Respuesta (…/responses): `query {original, altered, more_results_available}`, `web.results[] {title, url, description, age,
   page_age, language, family_friendly, extra_snippets[], meta_url.hostname}`; cabeceras `X-RateLimit-Limit/-Policy/-Remaining/-Reset`;
   HTTP 401 (auth) · 422 (parámetros) · 429 (rate limit). Precios (brave.com/search/api): plan **«Search»** «$5 per 1,000 requests»,
   «$5 in free credits every month», «50 queries per second», tarjeta para identidad; plan **«Answers»** «$4 per 1,000 requests» +
   «$5 per million input/output tokens», 2 qps — **respuestas generadas por LLM: NO es este plan**; el «Free 1 req/s · 2 000/mes»
   del brief **YA NO aparece** en la página (declarado; LG0 lo atestigua al dar de alta). *(síntesis: el ganador enviaba
   `result_filter=web&text_decorations=0&spellcheck=1` y recortaba `q` a 400/50 citando la doc — no verificable hoy → NO se envían
   parámetros no documentados y el tope de `q` es NUESTRO (`WITT_WEB_MAX_QUERY_CHARS`), no de Brave; veredicto de ambos jueces.)*
10. **Anthropic `web_search` — VERIFICADO hoy (platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool).** Tipos
   `web_search_20250305` (básico), `web_search_20260209` (+dynamic filtering: código+modelo filtran resultados; `allowed_callers`
   default `["code_execution_20260120"]`), `web_search_20260318` (+`response_inclusion`); `max_uses`; `allowed_domains` XOR
   `blocked_domains` (ambos → 400; dominios sin esquema, con path opcional); `user_location`. Respuesta: `server_tool_use {input
   {query}}` (**la query que el MODELO decidió**, puede diferir de la pedida), `web_search_tool_result.content[] {type
   'web_search_result', url, title, encrypted_content, page_age}` o `content {type 'web_search_tool_result_error', error_code ∈
   too_many_requests | invalid_tool_input | max_uses_exceeded | query_too_long | request_too_large | unavailable}` (HTTP 200);
   citas `web_search_result_location {url, title, encrypted_index, cited_text ≤ 150}`; `usage.server_tool_use.web_search_requests`;
   «$10 per 1,000 searches, plus standard token costs»; «Web search results … are counted as input tokens» (**el modelo LEE texto
   web en ese camino — propiedad declarada del alterno, razón de que sea alterno**); «If an error occurs … will not be billed»;
   «enabled for your organization unless an administrator has disabled it in the Claude Console … fails with a 400
   `invalid_request_error`»; `stop_reason 'pause_turn'` (se declara, no se continúa); `encrypted_content` sólo hace falta para
   multi-turno (una sola llamada: se DESCARTA); ZDR vía `allowed_callers` (Server tools) — con `web_search_20250305` el default es
   `["direct"]`. `_anthropic_tool_call` FUERZA `tool_choice {type 'tool', name}` (composite_auditor.py:778) y exige que el tool
   forzado esté en `tools=` (:772-775): no sirve para un server-tool → caller PROPIO mínimo en `web_locator` (I).
11. **`resolve_id.resolve` NO resuelve PMID/PMCID/DOI/ZDB/GSE** — sólo símbolo, ENSDARG, UniProt y RefSeq contra el store
   (resolve_id.py:117-131; `GET /resolve` = misma puerta, app.py:224-231). «Resolver» en este ADR = PATRÓN por host → identificador
   (tabla cerrada, (B)); la EXISTENCIA la confirma la fuente nativa (EPMC para literatura en tiempo de ronda; `resolve_id` como
   `store_state` sólo-lectura para ENSDARG/UniProt; `monarch`/`unpaywall_crossref` para curie/DOI si consumen).
12. **Patrones de la casa que este ADR REUTILIZA sin inventar:** tool stdlib con UNA costura `_get`, estados
   `success|no-match|error|skipped-budget|tool-unavailable`, `api_key_present` sólo presencia, caché de lectura por día en
   `mcp_cache/raw_<tool>_<slug>_<sha8>_<YYYYMMDD>.json`, `net_throttle.get_throttle(host, min_interval)` + `retry_once_on_429`
   (openalex_search.py:96-110, :228-293; net_throttle.py:81-95, :122-145); fixture SINTÉTICO declarado en nombre y cuerpo
   (`unpaywall_SYNTHETIC_dev02071_20260915.json` `_fixture {live false, synthetic true, note}`); tabla nueva por `create_all` sin
   ALTER (`config_history`, db.py:291-318); `ENV_SPECS` tolerante en tiempo de llamada (figures.py:188, `env_config` :280);
   `figure_predicates` como molde de fragmento + `extra_predicates` (verify_output.py:821); `_figure_checks` como cableado
   tolerante (runs.py:2562-2591); `FIGURES_DECLARED_EXCEPTIONS` EXACTAMENTE 3 y el diff M.1 (runs.py:3012;
   smoke_run_pipeline.py:5561-5564); `_FiguresUsageAccumulator` (app.py:2282); `KEY_BORN`/`SECCIONES` con asserts (record_pdf.py:
   119-236); `ENV_TABLE` con `adr` + gate compose ∩ README (models.py:283; smoke_models.py:1007-1010). `SOURCE_STATES` ya
   contiene `'skipped-cap'` (:93) y la webapp lo glosa (`witt-webapp/src/lenguaje/harness.ts:59`); `SearchFamily` ya incluye `'web'`
   (`types.ts:1791-1808`) y `SourceStatus` (:1759-1766) no necesita literal nuevo.
13. **Precedente agéntico de 2026-05-14 (fila ADR-0084 de la tabla de ADRs).** Dos cachés con texto de la web guardado como
   evidencia por una sesión de agente sin identificadores por afirmación (Anclas): `literature_pronephros_essentiality_20260514.json`
   y `literature_pronephros_proteomics_20260514.json`. Ninguna ruta de `path_b`/`fetch_paper` los lee (`_cache_lookup` sólo globa
   `raw_paper_*`, :309-310); los citan dos reports históricos. Se REGULARIZAN declarándolos no admisibles y midiendo que nadie los
   lee (K); no se mutan ni borran (`mcp_cache/` es caché gitignored, no registro).

## Decision

**(A) `.tooluniverse/tools/brave_web_search.py` (NUEVO, stdlib: `urllib, json, re, hashlib, time, os, pathlib`) — el TOOL,
esqueleto de `openalex_search.py`.** `TOOL_VERSION = 'bws-1'`. `locate(query, count=None, country=None, search_lang=None,
freshness=None, timeout=DEFAULT_TIMEOUT_S, cache_dir=None) -> {status, query_sent, query_truncated: bool, url_sent (SIN token),
elapsed_s, n_http_gets, cache_hit, cache_path, cached_at, api_key_present: bool, throttle {host, min_interval_s, waited_s},
retries_429, rate_limit_headers {limit, policy, remaining, reset} | None, http_status?, error?, reason?, identifier_provenance
'brave-web-search', evidence_kind 'web', params_sent [nombres], params_verified_as_of '2026-09-16', data {query_original,
query_altered: str|null, query_altered_by_provider: bool, more_results_available: bool|null, count_sent, country_sent,
search_lang_sent, freshness_sent, n_results, results[] {url, title (≤ 120), host (meta_url.hostname o urlparse), age, page_age},
fields_dropped ['description', 'extra_snippets', 'language', 'family_friendly', 'thumbnail', 'profile']}}`. *(A.1 petición)* `GET
https://api.search.brave.com/res/v1/web/search?q=…&count=…[&country=…][&search_lang=…][&freshness=…]` con cabeceras `Accept:
application/json` y `X-Subscription-Token: $BRAVE_API_KEY` (sin `Accept-Encoding: gzip`: stdlib no descomprime — declarado);
**SÓLO parámetros documentados (Context 9)**: ni `result_filter`, ni `text_decorations`, ni `spellcheck`, ni `extra_snippets`, ni
`offset`; `count` clamp `[1, 20]`; `freshness` fuera de `pd|pw|pm|py|YYYY-MM-DDtoYYYY-MM-DD` → no se envía y `freshness_ignored`
declarado; `q` se recorta a `WITT_WEB_MAX_QUERY_CHARS` (400, tope NUESTRO: la directiva del consejo ya viene ≤ 200 por
`STR_CAPS`) con `query_truncated True`. *(A.2 estados, jamás fundidos)* `success` (`web.results` ≥ 1) · `no-match` (`web` ausente o
`results []`: buscó y no halló ≠ error) · `error` (HTTP ≠ 200 con `http_status`: 401/403 → `error: auth (HTTP <code>)`; 422 →
`error: HTTP 422 unprocessable — <primer nombre de parámetro que el cuerpo mencione | body-not-parsed>` (MEDICIÓN de deriva de
API, patrón shape-mismatch ADR-0080); 429 tras UN reintento con `Retry-After` vía `net_throttle.retry_once_on_429` (segundo 429 →
error); cuerpo no-JSON → `error: NonJSONBody (content-type <ct>) — HTML/captcha declared`; forma inesperada (`web.results` no lista) →
`error: shape-mismatch (<detalle ≤ 120>)`) · `skipped-budget` (`timeout ≤ 0`, cero red) · `tool-unavailable` (sin `BRAVE_API_KEY`:
cero red, `reason 'BRAVE_API_KEY unset (no request sent)'`, patrón unpaywall_crossref.py:277-279). *(A.3 corte del texto web — en la
SALIDA)* `results[]` conserva SÓLO `{url, title ≤ 120, host, age, page_age}`; `description`, `extra_snippets` y los demás campos
se DESCARTAN al parsear y se cuentan en `fields_dropped`. El raw ÍNTEGRO de la respuesta SÍ se cachea en disco (§7.9: raw es
raw; `mcp_cache/` es gitignored y efímero en Dokploy; LG7 necesita `description`/`host` para medir la tasa por host) — *(síntesis:
el ganador podaba también el disco; los jueces piden raw íntegro + corte en la salida medido por smoke — se adopta; el sobre de
caché declara `cut {fields_dropped_from_output}` para no leerse como contrato de salida)*. *(A.4 caché de LECTURA por día)*
`mcp_cache/raw_brave_<slug(q,40)>_<sha8(q|count|country|lang|freshness)>_<YYYYMMDD>.json {fetched_at, url (sin token), headers
{X-RateLimit-*}, response (íntegra), _fixture? , cut}`; errores JAMÁS se cachean; `cache_hit True` → `n_http_gets 0` (no consume
cuota ni factura). *(A.5 pacing)* `net_throttle.get_throttle('api.search.brave.com', WITT_WEB_MIN_INTERVAL_S=1.0)` (tope PROPIO,
no el del proveedor: Brave publica 50 qps) alrededor de la ÚNICA costura `_get(url, timeout, with_headers=True, api_key=…)`;
`throttle.waited_s` medido. *(A.6 identidad)* la llave viaja SÓLO en la cabecera; `url_sent`, `cache_path`, el sobre de caché y el
fixture jamás la contienen (smoke: grep del valor fake == 0). *(A.7 CLI)* `__main__`: `python .tooluniverse/tools/brave_web_search.py
"<query>" [--count N] [--record-fixture]` → UNA GET real e imprime status/headers/results; `--record-fixture` copia el sobre a
`rag_index/query_service/fixtures/brave_web_search_<slug>_<YYYYMMDD>.json` con `_fixture {recorded_by 'brave_web_search.py
--record-fixture (ADR-0084 W1)', live true}` — el grabador ES la tool (Context: `record_fixtures_c.py` no existe). `@register_tool`
no-op como las otras 12.

**(B) `analysis/scripts/lib/web_locator.py` (NUEVO, stdlib) — el RESOLUTOR de tabla, la disponibilidad, la config y el alterno.**
`MODULE_VERSION = 'wl-1'`, `RESOLVER_VERSION = 'wlr-2'` *(corrector: `wlr-1` → `wlr-2` — `_trim_doi` recorta ITERATIVAMENTE la puntuación final
`.,;:)]/` y los sufijos de publisher `/(full|pdf|epdf|abstract|fulltext|full-text|html|meta|metrics|references|citedby|supplementary-material|suppl|
epub|figures(/n)?|tables(/n)?)` y `.(pdf|epdf|full|abstract|full-text|fulltext|html|xml|epub|article-info|article-metrics|supplementary-material|
figures-only)` ANTES de validar la forma (Frontiers `/full` iba a EPMC como DOI falso y el paper real se perdía); `pmc-path`/`ncbi-pmc-legacy`
aceptan `pmc` en minúsculas; `europepmc-path` gana la forma legacy REAL `/articles/PMC<n>` (grupo `id_legacy`, sólo PMC — `/articles/<dígitos>`
sigue `no-identifier-pattern`); `biorxiv-doi` recorta `.article-info`/`.article-metrics`; golden 51 → 61 casos re-sellado)*. *(B.1 tabla cerrada, primera regla que casa gana)* `RESOLVER_RULES: tuple[
{rule_id, host_pattern (regex sobre el host en minúsculas, sin `www.` salvo que la regla lo exija), id_pattern (regex sobre path
+ query URL-decodificados), kind, confidence, canonical_url (plantilla)}]`: `doi-org-path` (`^(dx\.)?doi\.org$` → `10\.\d{4,9}/[^\s?#]+`,
`doi`, `host-table`) · `pubmed-path` (`^pubmed\.ncbi\.nlm\.nih\.gov$` → `^/(\d{4,9})/?`, `pmid`) · `ncbi-pubmed-legacy`
(`^(www\.)?ncbi\.nlm\.nih\.gov$` → `^/pubmed/(\d{4,9})`, `pmid`) · `pmc-path` (`^pmc\.ncbi\.nlm\.nih\.gov$` → `^/articles/(PMC\d+)`,
`pmcid`) · `ncbi-pmc-legacy` (`^(www\.)?ncbi\.nlm\.nih\.gov$` → `^/pmc/articles/(PMC\d+)`, `pmcid`) · `europepmc-path`
(`^europepmc\.org$` → `^/(article|abstract)/(MED|PMC)/(PMC?\d+)`, `pmid|pmcid`) · `biorxiv-doi` (`^(www\.)?(biorxiv|medrxiv)\.org$` →
`^/content/(10\.\d{4,9}/[^v?#]+)`, `doi`, `label 'preprint'`) · `zfin-curie` (`^(www\.)?zfin\.org$` → `ZDB-(GENE|PUB|FIG|ALT|FISH)-\d{6}-\d+`
en path o `?id=`, `zfin-curie` → `'ZFIN:ZDB-…'`) · `ensembl-ensdarg` (`(^|\.)ensembl\.org$` → `ENSDARG\d{11}` en path o `?g=`,
`ensdarg`, versión `.\d+` recortada y declarada) · `uniprot-acc` (`^(www\.)?uniprot\.org$` → `^/uniprotkb/([OPQ][0-9][A-Z0-9]{3}[0-9]|
[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2})`, `uniprot`) · `geo-gse` (`^(www\.)?ncbi\.nlm\.nih\.gov$` → `^/geo/query/acc\.cgi` con
`acc=(GSE\d+)`, `gse`) · `doi-in-url-any-host` (cualquier host → `10\.\d{4,9}/[^\s?#]+` en el path, puntuación final `.,;:)]` recortada,
`confidence 'pattern-only'`; activable por `WITT_WEB_GENERIC_DOI_RULE`, default 1). Lo demás → `unresolved {url, host, title_web (≤ 120,
SÓLO aquí), reason ∈ UNRESOLVED_REASONS = ('no-identifier-pattern', 'host-not-allowed', 'unsupported-scheme', 'malformed-url')}`.
DOI normalizado con la MISMA regla de `answer_pipeline._normalize_doi` (minúsculas, sin prefijo de resolver) para que el dedup del
pool case. **NO se descarga ninguna página para buscar el DOI en 1.13** (es el scraping que §6.4 descarta; alternativa futura
`doi-from-html-meta` acotada — criterio de disparo: `n_unresolved/n_results > 0.5` sostenido en 5 corridas, LG7 — ADR propio, no
deuda). *(B.2 `resolve_urls(results, allowed_hosts=None, generic_doi=True, existing_ids=(), store=None) -> {located[], unresolved[],
n_results, n_located, n_unresolved, n_duplicates_in_response, resolver_version}`)* determinista, sin red, serializable:
`located[] {url (la hallada; vive SÓLO en este ledger), host, id (forma nativa: `PMID:<n>` | `PMC<n>` | `<doi minúsculas>` |
`ZFIN:ZDB-…` | `ENSDARG…` | `<acc>` | `GSE<n>`), kind ∈ LOCATED_KINDS = ('pmid','pmcid','doi','zfin-curie','ensdarg','uniprot','gse'),
resolver_rule, confidence ∈ ('host-table','pattern-only'), canonical_url, label?, store_state? ('in-store (RAW)' | 'in-store
(DERIVED)' | 'not-in-store' — sólo `ensdarg`/`uniprot` vía `resolve_id.resolve`, 0 red), dedup ∈ null | 'duplicate-in-response' |
'already-present (existing_ids)'}`; `allowed_hosts` RESTRINGE (nunca amplía la tabla): host fuera → `host-not-allowed`. *(B.3
`provider_state(env=None) -> {provider ∈ PROVIDERS = ('brave','anthropic','off'), provider_source ∈ 'env:WITT_WEB_LOCATOR' |
'default-derived:BRAVE_API_KEY present' | 'default-derived:BRAVE_API_KEY absent' | 'default-invalid-env:WITT_WEB_LOCATOR', available:
bool, unavailable_reason: str|null, key_present {brave: bool, anthropic: bool}}`)* — leído EN LA LLAMADA (M.4). Literales de
`unavailable_reason`: `off` explícito o derivado → EXACTO `'tool-unavailable (ADR-0084)'` (byte-idéntico a 7d9ce15 en
`families_excluded[].reason`, `harness_state`, `/council/demand`); `brave` explícito sin llave → `'tool-unavailable (ADR-0084:
BRAVE_API_KEY unset)'`; `anthropic` sin llave → `'tool-unavailable (ADR-0084: ANTHROPIC_API_KEY unset)'`; `anthropic` con 400 «not
enabled» ya medido en el proceso → `'tool-unavailable (ADR-0084: org web_search disabled in Console)'`. *(W9: alineado al código —
`web_locator.UNAVAILABLE_INVALID_ENV = 'tool-unavailable (ADR-0084: WITT_WEB_LOCATOR invalid)'` es el `state_when_not_run(ps)` cuando la
env trae un literal fuera de vocabulario (el plan sigue excluyendo con el literal EXACTO de 7d9ce15: `provider 'off'`); el dict devuelve
además `env_raw` y `explicit_off` — `runs._web_locator_frozen` distingue por `explicit_off` el kill-switch del derivado; `UNAVAILABLE_REASONS`
(5) y `UNAVAILABLE_PREFIX = 'tool-unavailable (ADR-0084'` viajan como vocabulario.)* *(B.4 `env_config(env=None)`)*
tabla `ENV_SPECS` (17 filas, patrón figures.py:188; cada valor con `<campo>_source ∈ 'env:<VAR>' | 'default' | 'default-invalid-env:<VAR>'`;
clamps declarados). *(B.5 `locate(query, cfg, *, provider_fn=None, quota_fn=None, existing_ids=(), store=None, timeout=None,
requirement_ids=()) -> fila-query`)* *(W9: alineado al código — firma real `locate(query, cfg=None, *, provider_fn=None, quota_fn=None,
existing_ids=(), store=None, timeout=None, requirement_ids=(), round_no=None, query_source=None, env=None, urlopen=None)`; el paso (0) es
`provider_state(env)` — no disponible → `'tool-unavailable'` con CERO red antes de sondear la caché)* la SECUENCIA ÚNICA por consulta
*(hueco de ambos jueces)*: (1) sondear la caché por día del tool
(`cache_probe(query, cfg)`, sin red) → si hay `cache_hit`, NO se reserva cuota; (2) si no, `quota_fn(provider, month_utc, cap) →
{granted, n_before, n_after, cap}` ANTES de la red; `granted False` → `status 'skipped-cap'`, `detail 'monthly cap
WITT_WEB_MONTHLY_CAP=<cap> reached (n_queries=<n>, month <m>)'`, cero red; sin `quota_fn` → `quota.state 'not-enforced (no quota
callable)'`; (3) llamada al proveedor (`brave_web_search.locate` cargado por ruta | `_anthropic_web_search` | `provider_fn` inyectado);
(4) `resolve_urls` sobre `data.results[]`; (5) `quota_fn(..., record={n_results, cost})` DESPUÉS (n_results/costo a la fila mensual).
Devuelve `{round, query_en, query_source, requirement_ids[], provider, provider_status ∈ SOURCE_STATES, http_status?, elapsed_s,
throttle_wait_s, cache_hit, query_truncated, query_altered_by_provider, n_results, n_located, n_unresolved, located[], unresolved[],
cost_usd_projected, billable: bool, quota {state, n_after, cap}, error?, detail?}` *(W9: alineado al código — la fila real es un superconjunto:
+ `query_sent`, `provider_source`, `state` (literal de `WEB_STATES_*`), `retries_429`, `n_duplicates_in_response`, `n_already_present`,
`n_billable`, `cost` (B.6), `tokens?` (anthropic), `resolver_version`, `module_version`; `quota` gana `month` y `n_before?`)*. *(B.6 costo)* `cost_of(provider, n_billable,
tokens=None) -> {provider, n_queries_billable, price_usd_per_1k (5.0 brave | 10.0 anthropic), price_as_of '2026-09-16',
price_source_url, usd_projected, class 'proyección', tokens? {in, out, class 'medición', model?}, tokens_usd_projected? (models.prices()), tokens_price_state?}` *(W9: alineado
al código — firma real `cost_of(provider, n_billable, tokens=None, model=None)`; `tokens_price_state ∈ 'projected (models.prices, as of
<PRICES_AS_OF>)' | 'missing_price (model not in models.MODELS)' | 'not-priced (…)'`; `PRICE_AS_OF '2026-09-16'`, `PROVIDER_PRICES_USD_PER_1K
{brave 5.0, anthropic 10.0}`, `PROVIDER_PRICE_SOURCE_URL` por proveedor)*.
*(B.7 vocabularios cerrados, viajan congelados)* `WEB_STATES_EXACT = ('located', 'no-results', 'not-requested (no web directive)',
'not-requested (no search round)', 'kill-switch WITT_WEB_LOCATOR=off')`, `WEB_STATE_PREFIXES = ('tool-unavailable (ADR-0084',
'skipped-cap (', 'skipped-budget (', 'error: ')`, `LOCATED_KINDS`, `FED_TO = ('pool:literature-candidate (materialized by
europepmc)', 'ctx:dois', 'ctx:curies', None)`, `FEED_STATES_EXACT = ('materialized-same-round', 'fed-same-round', 'already-present',
'duplicate-in-response', 'not-found-in-europepmc', 'not-materialized (feed cap)', 'not-materialized (budget)', 'no-sink-in-1.13')`,
`FEED_STATE_PREFIXES = ('already-present (dup of ', 'no-sink-in-1.13 (', 'error: ')`, `UNRESOLVED_REASONS`, `PROVIDERS`,
`PROVIDER_SOURCE_PREFIXES`, `QUOTA_STATES_EXACT = ('under-cap', 'cap-reached', 'not-enforced (no quota callable)', 'disabled
(WITT_WEB_MONTHLY_CAP=0)', 'not-consumed (cache-hit)')` *(W9: alineado al código — además `PROVIDER_SOURCES_EXACT` (4), `CONFIDENCES`, `LITERATURE_KINDS` (los 3 que
materializa EPMC), `DEDUP_STATES`, `STORE_STATES_EXACT`/`STORE_STATE_PREFIXES ('store-unavailable (',)`, `WEB_KILL_SWITCH_STATE`, y las reglas en
letras `QUOTA_RULE`, `TEXT_POLICY`, `WEB_LOCATOR_RULE`, `RESOLVER_RULE_ORDER`, `ALLOWED_HOSTS_SEMANTICS` que viajan en el frozen)*. *(B.8 precedente)* `NOT_ADMISSIBLE_PRECEDENTS = ({file
'mcp_cache/literature_pronephros_essentiality_20260514.json', query_method 'WebSearch + WebFetch on PMC articles'}, {file
'mcp_cache/literature_pronephros_proteomics_20260514.json', query_method 'WebSearch + WebFetch'})` con `state 'not-admissible (agentic
web cache; no source-pointer per claim; ADR-0062/0084)'` — ver (K).

**(C) Familia `web` en el harness: adaptador PROPIO que emite CERO ítems web y candidatos de literatura YA materializados por
Europe PMC.** *(C.1 fila)* `SEARCH_DISPATCH['web'] = {tool_module 'brave_web_search.py', fn 'locate', adapter 'web', inputs
'free-query', budget_s 30.0 (WITT_WEB_BUDGET_S), host 'api.search.brave.com', key_env 'BRAVE_API_KEY', evidence_kind 'web' (la CLASE
DE DEMANDA del consejo — `COUNCIL_EVIDENCE_KINDS` se deriva de aquí :111 y NO cambia; ningún ítem emitido es `kind 'web'`), gate
'directive-only', label_provenance None, unavailable_reason 'tool-unavailable (ADR-0084)', availability 'web_locator.provider_state'}`.
*(C.2 disponibilidad DINÁMICA — UNA verdad)* NUEVAS `search_harness.family_available(family, env=None) -> (bool, reason)` *(W9: alineado al código — `env` dict sustituye a `os.environ` en
los smokes; familia desconocida → `(False, 'unknown-family')`; sin `web_locator` importable → razón con sufijo `': web_locator not importable
(<Exc>)'`; `unsatisfiable_families(env=None)` bajo off == `('tooluniverse', 'web')`, con llave `('tooluniverse',)`)* (False si `fn is None`
y `adapter is None`; para filas con `availability` delega en `web_locator.provider_state()`) y `unsatisfiable_families() ->
tuple` (en tiempo de llamada). `build_search_plan` excluye con `family_available` (misma rama :414-421; el literal bajo `off` sigue
siendo EXACTO `'unsatisfiable-by-harness (tool-unavailable (ADR-0084))'`); `_load_tool` no cambia. *(C.3 gate directive-only
ESTRICTO)* para `web`, `_inputs_for` toma SÓLO `queries.web.directive_queries[].query_en` (ya sustituyen a `_free_query` :471-478,
`query_source 'council-directive:<rids>'`, `entered_by 'directive'`). Nombrar `web` en `WITT_SEARCH_DEFAULT_FAMILIES` ES la
directiva del operador (regla ADR-0080 :145-149 — se conserva, veredicto de ambos jueces): entonces la query es
`WITT_WEB_TEST_QUERY` si está (`query_source 'operator-env:WITT_WEB_TEST_QUERY'`, *injerto de B*) o `_free_query` = `pass1_query_en`
(la formulación EN del modelo, `query_source 'pass1_query_en'`) — **jamás la pregunta cruda** (smoke: la pregunta ES ausente por
substring de `query_sent`); `entered_by 'env:WITT_SEARCH_DEFAULT_FAMILIES'`. Tope `WITT_WEB_MAX_QUERIES` (3) por ronda: insumos
sobrantes → `calls[] {input, status 'skipped-cap', detail 'WITT_WEB_MAX_QUERIES=<n> reached'}` y `n_queries_dropped_by_cap`;
`inputs_used` conserva la firma completa («nada se re-ejecuta» sigue midiendo bien). *(C.4 orden de RONDA — web PRIMERA cuando entra)*
`build_search_plan` coloca `web` al FRENTE de `chosen` cuando está presente y declara `plan.families_order_rule 'web first —
the locator feeds the round (ADR-0084)'` (llave sólo cuando web está en el plan: un plan sin web es byte-idéntico a 7d9ce15) *(W9: alineado
al código — DOS literales: `FAMILIES_ORDER_RULE_WEB_FIRST = 'web first — the locator feeds the round (ADR-0084)'` cuando el plan reordena y
`FAMILIES_ORDER_RULE_CALLER = 'caller order (families= mandates; web not moved) (ADR-0084)'` cuando el llamador impuso `families=` y web no se
mueve; la fila `web` de `SEARCH_DISPATCH` gana además `budget_env 'WITT_WEB_BUDGET_S'` y `budget_clamp (1.0, 120.0)` leídos por
`family_budget_s(spec)`; `WEB_TEST_QUERY_SOURCE = 'operator-env:WITT_WEB_TEST_QUERY'`)*. *(corrector — L: el reorden, `families_order_rule`,
`queries.web.entered_by` y `WITT_WEB_TEST_QUERY` se aplican SÓLO con el localizador DISPONIBLE (`family_available('web')`); bajo kill-switch o sin
llave, `web` nombrada en `WITT_SEARCH_DEFAULT_FAMILIES` (o en `families=`) conserva su posición y el plan es el de 7d9ce15 byte a byte — antes el
plan movía web al frente y ganaba la llave bajo off, tres diferencias fuera de las 3 excepciones declaradas. `plan_event_payload` copia
`families_order_rule` cuando existe: la Traza pinta «web primera» desde el evento)*.
Razón: Context 5 — es el ÚNICO encadenado determinista para `ctx:dois` → `unpaywall_crossref` y `ctx:curies` → `monarch` en la MISMA
ronda. *(C.5 `_run_web_family(family, spec, plan, ctx, budget_s, tools)` — rama `adapter == 'web'` en `run_source`)* por insumo dentro
del tope y del presupuesto (reparto `timeout = max(MIN_CALL_TIMEOUT_S, restante / llamadas_restantes)`, patrón :858-866):
`web_locator.locate(query, cfg, provider_fn=tools.get('web'), quota_fn=ctx.get('web_quota'), existing_ids=ctx['existing_ids'] ∪
ids ya vistos, store=…)`. Con `located[]`: (i) `kind ∈ pmid|pmcid|doi` → **materialización en la MISMA ronda por Europe PMC**:
`fetch_paper._resolve_one(ident)` con `ident ∈ 'PMID:<n>' | '<PMC…>' | 'DOI:<doi>'` (assert de forma ANTES de llamar; Context 4) —
UNA GET paceada por `fetch_paper._throttle`, SIN escritura de caché *(corrector — M.1: la GET corre por
`fetch_paper.search_europepmc_ledger(search_harness.epmc_query_for(ident), n=1, timeout=max(MIN_CALL_TIMEOUT_S, min(HTTP_TIMEOUT_S, presupuesto
restante de la familia)))` — la MISMA consulta de `_resolve_one` (`fetch_paper` NO se toca) con timeout ACOTADO (antes 30 s por ident: 6 idents
lentos retenían la ronda 180 s); un DOI con sintaxis de EPMC (`()<>;:"` o espacios — el SICI del golden) viaja ENTRE COMILLAS
(`epmc_query_quoted True`); `epmc_timeout_s` declarado en el hallazgo. DEDUP POR PAPER dentro de la familia (`WEB_SAME_PAPER_RULE`): las llaves
`PMID:/PMCID:/DOI:` del registro materializado (`answer_pipeline._candidate_keys`) se recuerdan en la ronda y otra FORMA del mismo paper (pubmed +
PMC + doi.org de un mismo registro) queda `feed_state 'already-present (dup of <evidence_id>)'` + `same_paper {of, matched_key, layer 'family',
rule}` SIN segunda GET ni segundo candidato (`n_same_paper_dups`); las tres formas viajan como `existing_ids` a la siguiente consulta. TRAMPA DEL
TOP HIT (Context 4): el registro devuelto debe traer el identificador localizado entre sus llaves, si no → `feed_state 'error: europepmc record
mismatch (<ids del registro> != <llave>)'` (prefijo `error: ` del vocabulario), NO candidato, `n_epmc_record_mismatch`. El candidato gana
`located_ref {query_index, id}` para que `answer_pipeline._web_mark_pool_duplicate` cierre SÓLO su fila de origen)*; `rec` → `cand =
answer_pipeline._epmc_candidate(rec)` (forma
nativa del `evidence_id`, Context 7) + `{kind 'literature-candidate', source 'europepmc', source_family 'web', label None,
statement None, title rec.title (de EPMC), url canonical_url (`https://doi.org/<doi>` | `https://pubmed.ncbi.nlm.nih.gov/<pmid>/` |
`https://europepmc.org/article/PMC/<pmcid>` — JAMÁS la URL hallada), identifier_provenance 'web-located:<rule_id>', located_from
{host, rule_id, confidence, round, requirement_ids[]}, search_rec_source 'europepmc-record (web-located candidate;
fetch_paper._resolve_one)', raw_ref None, text None, directive_requirement_ids [rids]}`; `rec None` → `feed_state
'not-found-in-europepmc'` (contado: un patrón que casó pero no existe NO es candidato); tope `WITT_WEB_MAX_MATERIALIZE` (6) por
ronda y presupuesto de la familia (`'not-materialized (feed cap | budget)'`); (ii) `kind 'doi'` además → `ctx['dois']` (append sobre
la lista pre-creada :1050 — INVARIANTE: jamás reasignar, smoke) para `unpaywall_crossref`; (iii) `kind 'zfin-curie'` con
`ZDB-GENE-*` → `ctx['curies']` (`'ZFIN:…'`) para `monarch`; `ZDB-PUB/FIG/ALT/FISH` → `fed_to None`, `feed_state 'no-sink-in-1.13
(<kind>)'`; (iv) `ensdarg`/`uniprot` → `store_state` medido, `fed_to None`; `gse` → `fed_to None` (una directiva `geo` es del
consejo, no un auto-feed). **La familia NO emite ningún ítem con `source 'web'`, `kind 'web'`, `url` hallada, `title_web` ni
`description`** — sus `items` son SÓLO los candidatos materializados (source 'europepmc'). Cortacircuito de autenticación *(hueco
del juez 1)*: un `error: auth` en la primera consulta deja las restantes de la ronda `skipped-cap` con `detail 'auth failed in
this round (no retry)'`, cero red *(W9: alineado al código — el detail vive en `search_harness.WEB_AUTH_CIRCUIT_DETAIL`; el candidato
materializado gana además `located_via 'web'` y `dedup_layer 'pool'`, y `located_from` incluye `kind`)*. Fila: `_row(family, spec, status, …)` con `status` por `_family_status` sobre las consultas
(`success` = ≥ 1 candidato materializado; `no-match` = consultas midieron y 0 materializados — `detail 'n_results=<k>
n_located=<j> n_materialized=0'`; `tool-unavailable`/`skipped-budget`/`skipped-cap`/`error` heredados) += `provider, n_queries,
n_queries_dropped_by_cap, n_results (== n_found), n_located, n_materialized, n_fed_ctx, n_located_not_fed, n_already_present,
n_unresolved, n_not_found_in_europepmc, n_same_paper_dups, n_epmc_record_mismatch *(corrector)*, cost_usd_projected, quota_state, inputs_mode
'free-query', inputs_used, calls[] {input,
status, http_status?, elapsed_s, timeout_s, cache_hit, n_results, n_located, n_materialized, n_unresolved, throttle_wait_s,
retries_429, error?, detail?}, web_locator {queries[], located[], unresolved[]}` (el ledger COMPLETO de la familia en la fila; las
URLs viven aquí y en `frozen.web_locator`, nunca en ítems ni eventos). *(C.6 hook de latido)* `ctx['on_web_locate']` (callable
inyectado por `_path_b_harness` desde `on_stage`) recibe UN payload por consulta DECLARADA — enviada o `skipped-cap` / `skipped-budget` /
`error`; jamás bajo `tool-unavailable` *(corrector: el borrador y el README decían «ENVIADA»; el latido de la consulta que la cuota frenó también
se emite, con `detail`)* → evento `stage.web.locate` (G).
*(C.7 `source_event_payload`)* copia `provider, n_queries, n_results, n_located, n_materialized, n_unresolved, n_already_present,
cost_usd_projected, quota_state` SÓLO cuando existen en la fila (aditivo; las otras 14 familias no los ganan). *(C.8 no se toca)*
`normalize_item`, `_run_workspace_family`, `_run_legacy_family`, `run_round` (la cosecha :1252-1263 ya recoge `search_rec.doi` de los
candidatos materializados — los DOI web llegan a `ctx['dois']` por DOS vías idempotentes: `_ctx_list` deduplica) *(corrector: idempotentes SÓLO si
la cadena es la misma — `_feed_doi` escribe la forma del REGISTRO de EPMC cuando existe (la que cosecha `run_round`) y la normalizada cuando no,
comparando en minúsculas: un DOI ya no va dos veces a Crossref/Unpaywall por mayúsculas)*.

**(D) `answer_pipeline._path_b_harness` — admisión native-first, tie-break de selección, `block['web_locator']`.** *(D.1 admisión
al pool)* dentro de cada ronda, los `literature-candidate` se admiten en orden `source_family != 'web'` primero y después los
web-localizados (`pool_admission_rule 'native-first within a round (ADR-0084)'`, llave en `selection` sólo cuando hubo candidatos
web) → un PMID que EPMC/PubMed trajeron Y la web señaló queda en `selection.duplicates[] {duplicate, source 'europepmc', source_family
'web', of <id nativo>, matched_key}` y en `located[].feed_state 'already-present (dup of <id>)'` (`n_already_present` = MEDICIÓN de «la
web halló lo que ya teníamos»). Sin candidatos web el orden de admisión es el de hoy: byte-idéntico. *(D.2 selección)* `_select_top_n`
gana un TERCER componente de orden entre `rank(source)` e índice: `1 if c.get('source_family') == 'web' else 0` — natives
antes que web-localizados a igual OA y fuente; para un pool sin web la clave es la de hoy → byte-idéntico. `PATH_B_SELECTION_RULE` NO
cambia de literal; `selection.tie_break_web_located 'native-before-web-located (ADR-0084)'` viaja sólo cuando hubo candidatos web.
*(síntesis: C ponía web primera y callaba el desplazamiento; A quería web última sin reordenar; se separan ronda/admisión/selección —
veredicto de ambos jueces.)* Se MIDEN `n_located_selected` / `n_located_not_selected`; una ranura reservada se decide con LG7, no aquí.
*(D.3 `_paper_item`)* el candidato ya trae `search_rec` de EPMC; `_fetch_or_declare(ident, full_text)` baja el paper con
raw cacheado como hoy (:894-905); `fetched.found False` en ese momento → paper sin pasaje, gateado por (E) *(corrector — D.3 ↔ E.3: «sin pasaje»
ahora es CÓDIGO, no promesa: para `source_family 'web'` con `fetched.found is not True` `_paper_item` pone `abstract None, text_excerpt None,
text_provenance 'none', text_excerpt_rule WEB_TEXT_WITHHELD_RULE, text_withheld_reason 'web-located-not-fetched (ADR-0084 D.3)'` — el abstract
del REGISTRO de búsqueda de EPMC (no texto web) se RETIENE porque E.3 sólo admite texto con `fetched.found True`; antes un read-timeout transitorio
de EPMC bajando UN paper (2026-08-20 en vivo) volvía inadmisible TODA la pass2 aunque nadie lo citara; E.2 sigue gateando la CITA)*. La copia
:1116-1120 gana
`located_from` y `search_rec_source` (aditivo, sólo cuando el candidato los trae). *(D.4 agregación)* `block['web_locator']` =
unión de las filas web de todas las rondas: `{queries[], located[] (+ evidence_id, admitted, duplicate_of, selected, selection_rank,
fetched_found — cerrados tras selección y `_paper_item`), unresolved[], contadores, cost, quota}` *(W9: alineado al código —
`answer_pipeline._web_locator_block(plan, rounds, papers, web_admitted, web_pool_dups, had_web_candidates)` emite `block_version 'wlb-1'`
(`WEB_LOCATOR_BLOCK_VERSION`), el encabezado de `web_locator.frozen_header` (`module_version`, `resolver_version`, `tool_version`,
`state_vocabulary`, `resolver_rules[12]`, `allowed_hosts`, `generic_doi_rule`, `text_policy`, `rule`, `gate`), `state`, `state_detail`, `measured`
(bool: la familia MIDIÓ), `in_plan`, `plan_exclusion_reason`, `provider`, `provider_source`, `provider_available`, `provider_state`, `entered_by`,
`directive_requirement_ids`, `query_source`, `families_order_rule`, `n_rounds_with_web`, `by_round[]`, `n_queries`, `queries[]` (fila-query de
`wl.locate`), `located[]` (url HALLADA sólo aquí + cierre `admitted`/`duplicate_of`/`selected`/`selection_rank`/`fetched_found`), `unresolved[]`
(`title_web` sólo aquí), `gap_flags_typed[]`, `n_gap_flags`, `cost` (B.6), `cost_usd_projected`, `quota {state, n_before, n_after, cap, cap_source,
month, hook, n_record_errors, rule}`, `quota_state`, `had_web_candidates`, `pool_admission_rule`, `tie_break_rule`, `dedup_layer_rule`,
`materialize_rule`, `located_close_keys`; los contadores de `runs.WEB_FROZEN_COUNTER_KEYS` — `n_queries_planned, n_queries_dropped_by_cap,
n_results, n_located, n_materialized, n_epmc_gets, n_not_found_in_europepmc, n_fed_ctx, n_located_not_fed, n_duplicates_in_response,
n_unresolved, n_already_present_resolver, n_already_present_pool, n_already_present, n_admitted, n_located_selected, n_located_not_selected,
n_papers_web_located, n_same_paper_dups, n_epmc_record_mismatch` *(corrector: + los 2 últimos; `n_already_present_pool` = filas `located[]` marcadas
`pool_dedup` — una por candidato rechazado, ya no `len(dict por eid)`; una fila `same_paper` cierra `admitted False, duplicate_of <of>, selected
False, selection_rank None, fetched_found None`)* — son `null` cuando no midió y ENTEROS cuando sí; `selection.pool_admission_rule` / `tie_break_web_located` leen
`WEB_POOL_ADMISSION_RULE` / `WEB_TIE_BREAK_RULE`)*; `block['n_results_by_source']`:
`web` entra a `ran_sources` cuando midió → `n_results_by_source.web == 0` SIEMPRE (papers con `source 'web'` = 0 por construcción:
el gate del brief, congelado en el frozen) y los web-localizados cuentan en `europepmc` (declarado: `web_locator.n_papers_web_located`).
*(D.5 hooks)* `_path_b_harness` pre-crea `ctx['on_web_locate'] = lambda p: _stage('web.locate', p)`, `ctx['web_quota'] =
web_quota` (parámetro NUEVO opcional de `path_b_bundle`/`path_b`/`_path_b_harness`, None → `not-enforced`), `ctx['existing_ids']`.
`path_b_event_payload` copia `located_from`/`search_rec_source` sólo cuando el ítem los trae (:1239) y añade `n_web_located`,
`n_web_unresolved` al payload.

**(E) `verify_output.web_predicates(citations, bundle, answer_text, web_ledger=None, provider_state=None, *, env=None) -> (fragmento
deterministic_checks.web_locator, extra_predicates[])` — CUATRO predicados, TRES gating, patrón `figure_predicates`.**
`WEB_PREDICATES_VERSION = 'wlpred-1'`. (1) **`web_text_not_cited`** (gating True): ofende toda cita cuyo `id` (a) casa `^https?://`
y NO resuelve a un ítem del bundle tras `_citation_keys` (carve-out `https://doi.org/<doi>` → DOI, Context 8), o (b) coincide con
una URL de `web_ledger.located[].url` / `unresolved[].url`, o (c) tiene `kind ∈ {'web','url'}`; `why ∈ 'id-is-url' |
'id-matches-located-url' | 'id-matches-unresolved-url' | 'kind-web'`. (2) **`web_located_cited_requires_fetch`** (gating True, *injerto
de C*): una cita que resuelve (por `_bundle_evidence_index`) a un paper con `source_family 'web'` cuyo `fetched.found is not True`
es inadmisible (`why 'web-located-not-fetched'`) — cerrar la cita a un id que sólo la web produjo y EPMC no materializó es citar la
web (Context 8a). (3) **`web_items_native_only`** (gating True, estructural): 0 papers con `source 'web'` o `kind 'web'`; todo paper
con `source_family 'web'` tiene `search_rec.pmid|pmcid|doi` no nulo, `identifier_provenance` que empieza con `'web-located:'`,
`source 'europepmc'`, `url` canónica (`doi.org|pubmed.ncbi.nlm.nih.gov|europepmc.org`) y `text_excerpt`/`abstract` no nulos SÓLO si
`fetched.found is True` (`why ∈ 'source-web' | 'kind-web' | 'no-resolvable-identifier' | 'provenance-not-web-located' |
'non-canonical-url' | 'text-without-fetch'`). (4) **`web_urls_not_in_answer`** (informativo, gating False): ninguna URL del ledger
web aparece verbatim en `direct_answer` (una URL en el texto sin ser cita no es fabricación gateable hoy; se MIDE y LG7 decide).
Fragmento `{state ∈ WEB_CHECK_STATES_EXACT = ('checked', 'no-web-items', 'kill-switch WITT_WEB_LOCATOR=off') | WEB_CHECK_STATES_PREFIXES
= ('tool-unavailable (', 'error: '), <pred> {ok, gating, n_checked, offenders[] {…, why}, rule}, decided_by 'code', module_version,
rules {…}}`; `'no-web-items'` (ni ítems web-localizados ni ledger web) → los 4 bloques se miden con ceros y NINGÚN predicado entra a
la conjunción (admisibilidad de hoy byte a byte); bajo kill-switch EXACTAMENTE `{state}` *(W9: alineado al código — firma real arriba; el
fragmento trae `conjunction[]` (predicados que entraron a la conjunción; `[]` bajo `no-web-items`); `WEB_CHECK_STATE_TOOL_UNAVAILABLE =
'tool-unavailable (lib/web_locator.py not importable — ADR-0084 W5)'`; un `id` de cita que coincide con una URL del ledger web viaja en
`offenders[]` REDACTADO — `WEB_URL_REDACTED = '<redacted: citation id equals a web-ledger URL — see frozen.web_locator>'`, porque
`deterministic_checks` llega al panel (`WEB_FRAGMENT_URL_POLICY`); `WEB_CANONICAL_HOSTS = ('doi.org', 'pubmed.ncbi.nlm.nih.gov',
'europepmc.org')`; `WEB_WHYS`/`WEB_RULES` por predicado)*. Cableado en `runs._web_checks` (patrón
`_figure_checks` :2562-2591) y en la conjunción de `_gate` (:2612-2617); `reasons[]` gana `'hard predicate failed: <nombre>'`.
El enum `kind` de `SYNTH_TOOL` NO cambia. La escalera `support_state_for` no cambia (ADR-0053: la procedencia se declara, no gatea).

**(F) Consejo y demanda: disponibilidad dinámica para DESPACHAR, conteo ESTÁTICO para MEDIR.** *(F.1)* `council.harness_state_for`
delega en `search_harness.family_available(fam)`: con localizador disponible `'satisfiable'` (la directiva web se COMPILA,
`state 'compiled'`); apagado o sin llave el literal de hoy `'unsatisfiable-by-harness (tool-unavailable (ADR-0084))'` (o los dos
literales con causa de (B.3) cuando el operador fijó `brave`/`anthropic` sin llave) *(W9: alineado al código — `council.harness_state_for(
source_family, evidence_kind, env=None)`; el literal de exclusión vive UNA vez en `search_harness.WEB_UNSATISFIABLE_LITERAL` — `grep -c` == 1 en
`search_harness.py` y 0 en runs/app/db/models)*. *(F.2 estado almacenado — hueco de ambos jueces)*
`directives_from` usa `req.get("harness_state")` guardado en r1 (:1863): para familias con `availability` dinámica RECOMPUTA en
tiempo de compilación y declara `harness_state_at_plan` + `harness_state_at_compile` + `harness_state_recomputed True` cuando
difieren (la llave llegó o se fue entre el plan y la corrida); planes aprobados bajo `off` compilan la directiva web si al correr hay
llave — sin re-planear. *(F.3 demanda)* `council_index.DEMAND_FAMILIES` conserva `'web'` SIEMPRE (tupla estática `('figure',
'tooluniverse', 'web')`): `n_requirements_unsatisfiable_by_family.web` sigue contando los requisitos de familia web de TODOS los
registros congelados (la serie MEDIDA de disparo no se rompe al llegar la llave — *injerto de C, veredicto del juez 2*);
`unsatisfiable_families[]` pasa a derivarse EN LA LLAMADA por `search_harness.unsatisfiable_families()` con
`unsatisfiable_families_source 'derived: SEARCH_DISPATCH fn None ∪ web_locator.provider_state not available'`; `demand()` +=
`web_locator_provider_state {provider, provider_source, available, unavailable_reason}` (aditivo) *(W9: alineado al código — además `demand_families[]` y `demand_families_rule`
(`council_index.DEMAND_FAMILIES_RULE`); el literal de la fuente es `council_index.UNSATISFIABLE_FAMILIES_SOURCE`)*. `GET /council/demand` sin cambio
de firma. `COUNCIL_EVIDENCE_KINDS`/`COUNCIL_SOURCE_FAMILIES` (13/15) sin cambio. *(F.4 cobertura)* `coverage_after_search.
by_requirement[]` += `web_locator? {n_queries, n_results, n_located, n_materialized, n_unresolved}` SÓLO en requisitos de familia
web (ausente en los demás; *injerto de B*); `retrieved-for` sigue siendo estructural: ≥ 1 candidato ADMITIDO con el `requirement_id`
— y como los candidatos web sólo existen materializados por EPMC, «retrieved-for» por la web = existe en EPMC.

**(G) `runs.py` — contrato 1.13, `frozen.web_locator`, gate, eventos, costo, cuota.** *(G.1)* `RENDER_CONTRACT_VERSION = "1.13"`
(+ línea de historial). *(G.2 `frozen.web_locator` — SIEMPRE presente en ≥ 1.13, forma EXACTA)* `{state ∈ WEB_STATES_EXACT |
WEB_STATE_PREFIXES, state_vocabulary {exact, prefixes, rule}, module_version 'wl-1', resolver_version 'wlr-2' *(corrector)*, tool_version 'bws-1' |
null, provider ∈ 'brave' | 'anthropic' | 'off', provider_source, gate 'directive-only', entered_by ∈ 'directive' |
'env:WITT_SEARCH_DEFAULT_FAMILIES' | null, directive_requirement_ids[], families_order_rule | null, n_queries, n_queries_dropped_by_cap,
n_results, n_located, n_materialized, n_not_found_in_europepmc, n_fed_ctx, n_located_not_fed, n_already_present, n_unresolved,
n_located_selected, n_located_not_selected, n_papers_web_located (todos int; 0 = medido; AUSENTES bajo kill-switch/tool-unavailable),
queries[] (forma de (B.5), `located_ids[]` en vez de URLs NO — aquí SÍ viajan las URLs: es el ledger humano), located[] {url, host,
id, kind, resolver_rule, confidence, canonical_url, fed_to ∈ FED_TO, feed_state ∈ FEED_STATES, evidence_id?, admitted?, duplicate_of?,
selected?, selection_rank?, fetched_found?, store_state?, round, requirement_ids[]}, unresolved[] {url, host, title_web, reason, round,
requirement_ids[]}, gap_flags_typed[] {kind ∈ 'web-located-unresolved' | 'web-located-unmaterialized', url?, id?, host, reason}
(patrón ADR-0082), allowed_hosts {value: [hosts] | 'all (resolver table + doi-in-url on any host)', source}, generic_doi_rule
{enabled, source}, resolver_rules[] {rule_id, host_pattern, id_pattern, kind, confidence}, cost (B.6), quota {month, n_before, n_after,
cap, cap_source, state ∈ QUOTA_STATES, rule 'local counter of queries SENT by this deployment (UTC calendar month); CLI probes do not
count; the provider dashboard is the truth of the balance; provider cycle attested in LG0'}, text_policy 'no web text enters the
bundle, the prompt, the events or the answer: results carry url/title/age only; description and extra_snippets are dropped at the
tool output; title_web lives only in unresolved[] of this ledger', kill_switch? {WITT_WEB_LOCATOR: '<raw>', enabled false, source,
declared_exceptions [3]} (sólo bajo off), rule (WEB_LOCATOR_RULE)}`. Estados: `'located'` (≥ 1 located) · `'no-results'` (consultas
midieron, 0 URLs o 0 located — con contadores) · `'not-requested (no web directive)'` (hubo ronda, web no entró) · `'not-requested (no
search round)'` (competente, sin Ruta B por harness) · `'kill-switch WITT_WEB_LOCATOR=off'` (off EXPLÍCITO) · `'tool-unavailable
(ADR-0084: BRAVE_API_KEY unset)'` (derivado off por ausencia de llave — la CAUSA viaja aquí, no en el plan) · `'skipped-cap (…)'` ·
`'skipped-budget (…)'` · `'error: …'`. *(W9: alineado al código — `runs._web_locator_frozen(block, plan_state, harness_used, ps)` produce TRES formas: **(1)** off EXPLÍCITO
(`WITT_WEB_LOCATOR=off`) → EXACTAMENTE `runs.WEB_FROZEN_KILL_SWITCH_KEYS = ('state', 'provider', 'provider_source', 'kill_switch',
'state_vocabulary', 'rule')` con `kill_switch {WITT_WEB_LOCATOR '<raw>', enabled false, source, declared_exceptions [3]}`; **(2)** Ruta B por el
harness → el bloque de D.4 copiado íntegro + `source runs.WEB_FROZEN_SOURCE`; si `measured false` los contadores `null` de
`WEB_FROZEN_COUNTER_KEYS` se OMITEN (no midió ≠ 0) y, con el proveedor no disponible y `state 'not-requested …'` (la directiva se excluyó al
COMPILAR, F.2), `state` pasa a `web_locator.state_when_not_run(ps)` — p. ej. `'tool-unavailable (ADR-0084: BRAVE_API_KEY unset)'` — y la ruta
queda en `state_detail`; **(3)** sin ronda del harness → `web_locator.frozen_header` + `{block_version, state ('not-requested (no search round)'
| state_when_not_run(ps) si no disponible), state_detail, measured false, in_plan false, plan_exclusion_reason null, provider, provider_source,
provider_available, provider_state {…, read_at}, entered_by null, directive_requirement_ids [], query_source null, families_order_rule null,
n_rounds_with_web 0, by_round [], n_queries 0, queries [], located [], unresolved [], gap_flags_typed [], n_gap_flags {2 kinds: 0}, quota {state
null, cap, cap_source, month null, rule}, quota_state null, had_web_candidates false, pool_admission_rule, tie_break_rule, source}` — SIN
contadores. Módulo ausente → `{state runs.WEB_TOOL_UNAVAILABLE_MODULE = 'tool-unavailable (ADR-0084: lib/web_locator.py not in tree)', …}`. En
`frozen.search_ledger.rounds[].sources[web]` el `web_locator` anidado se PODA al congelar (`web_locator_frozen_at 'frozen.web_locator'`) y la fila
conserva `provider, n_queries, n_results, n_located, n_materialized, n_unresolved, n_already_present, cost_usd_projected, quota_state` (C.7);
`bundle_json` conserva la fila íntegra.)* *(G.3 `deterministic_checks.web_locator`)* fragmento de (E); bajo kill-switch `{state}` *(W9:
alineado al código — también `{state}` bajo tool-unavailable sin datos; sin helper → `{state 'tool-unavailable (verify_output.web_predicates
not in tree — ADR-0084)'}` (`runs.WEB_TOOL_UNAVAILABLE_GATE`); `stage.deterministic_gate.payload.web_locator_state = frag.state`)*.
*(G.4 `answer.gap_flags`)* runs APILA por CÓDIGO tras cada síntesis (patrón :1750-1841) a lo sumo DOS strings de CONTEO:
`'web-located-unresolved: <n> URL(s) located on the web could not be resolved to an identifier by code — declared in
frozen.web_locator.unresolved, never cited'` y `'web-located-unmaterialized: <k> identifier(s) located on the web were not found in
Europe PMC — declared in frozen.web_locator.located, never cited'`; sólo con n/k > 0; JAMÁS URLs (Context 3) *(W9: alineado al código — `runs.WEB_GAP_FLAG_UNRESOLVED.format(n=…)`,
`runs.WEB_GAP_FLAG_UNMATERIALIZED.format(k=…)`, prefijos `runs.WEB_GAP_FLAG_PREFIXES`; los apila `runs._stack_web_gap_flags` tras pass2 y tras la
revisión)*. *(G.5 citas)*
`citations[] += located_via ('web' | null)` (del paper resuelto; aditivo); `citations_support_summary += n_located_via_web (int, 0
medido; ausente bajo kill-switch)` *(W9: alineado al código — `located_via` y `n_located_via_web` viajan SÓLO cuando
`web_locator.provider_state().available`: ausentes bajo off explícito o derivado y bajo `brave`/`anthropic` sin llave — `runs._web_citations_fill`)*.
*(G.6 eventos)* NUEVO `stage.web.locate` (`agent 'web_locator'`, UNO por consulta DECLARADA — enviada o `skipped-cap`/`skipped-budget`/`error`,
jamás bajo `tool-unavailable`; el payload gana `detail?` / `error?` *(corrector)* —, latido
dentro de la ronda): `{round, provider, query_en, query_source, requirement_ids[], provider_status, http_status?, elapsed_s,
throttle_wait_s, cache_hit, query_altered_by_provider, n_results, n_located, n_materialized, n_unresolved, located_ids[] (ids, no
URLs), hosts_unresolved[], cost_usd_projected, quota {state, n_after, cap}}` — emitido por `db.add_event(run_id, 'stage.web.locate',
agent='web_locator', payload)` desde `_on_stage` (la superficie (C) del gate de paridad lee esa forma). `stage.search.source` (fila
web) += las llaves de (C.7); `stage.search.plan += families_order_rule?` y `stage.path_b.selection += pool_admission_rule? /
tie_break_web_located?` *(corrector: SÓLO cuando existen — la Traza y la Hoja pintan desde el evento; ausentes sin web, forma de hoy byte a byte)*;
`stage.path_b` += `n_web_located, n_web_unresolved` y `papers[] += located_via?, located_from?, search_rec_source?`;
`stage.deterministic_gate += web_locator_state`. Ninguna URL en ningún evento (smoke: regex `https?://` == 0 sobre todos los payloads
salvo la canónica `url` de los papers, que es identificador). *(G.7 costo — dos clases, un total que cuadra)* `token_usage.web_locator
= cost (B.6) + {state, n_queries, n_results, n_located, n_materialized, n_unresolved, quota_state}` (sólo cuando la familia CORRIÓ —
`n_rounds_with_web > 0`, también `skipped-cap` con 0 facturables; ausente bajo kill-switch y bajo `not-requested` — *W9: alineado al código*,
`runs._web_usage_ctx`);
`by_stage.search.web_locator_usd_projected` y `by_stage.search.note` → `'Layer 0 tools — no model call (ADR-0080); web locator cost
travels apart (ADR-0084)'`; **`estimated_cost_usd` NO cambia** (su `cost_class` afirma «tokens × per-Mtok prices», :2377) y
**NUEVO `estimated_cost_usd_total_projected = round(estimated_cost_usd + web_locator.usd_projected, 4)`** *(W9: alineado al código —
`total_class = runs.WEB_TOTAL_CLASS`; `by_stage.search.note = runs.WEB_SEARCH_STAGE_NOTE`; con `anthropic`, `by_stage.search.state =
runs.WEB_ANTHROPIC_SEARCH_STATE`)* con `total_class 'PROJECTION (tokens ×
price) + PROJECTION (web locator requests × unit price) — two projections, same class; measurement counts travel apart'` (sólo cuando
`web_locator` existe) — *(síntesis: C sumaba dentro de `estimated_cost_usd` (juez 1 a favor, juez 2 en contra por el literal de
`cost_class`); A/B lo llevaban aparte: se conserva `estimated_cost_usd` byte a byte Y se entrega UN total que cuadra en M8 (lección
ADR-0061), sin falsear la clase)*. Con provider `anthropic`, los tokens del despachador SÍ entran a `by_model[<modelo>]` y a
`estimated_cost_usd` bajo etapa `search` (`by_stage.search {in, out, model, state 'measured (anthropic web_search dispatcher)'}`) —
son tokens medidos de un modelo. *(G.8 `epistemic_summary`)* += `web_locator_state (str|null), web_n_located (int|null),
web_n_unresolved (int|null)` (null = no midió ≠ 0) *(corrector:
`epistemic_summary` es la columna `epistemic_summary_json` de la Lista/Banco, NO parte del registro congelado — por eso `web_locator_state` viaja
también bajo off ('kill-switch WITT_WEB_LOCATOR=off'), como `figures_state` en ADR-0083; no cuenta contra las 3 excepciones del frozen)*. *(G.9 `agents_invoked`)* += fila `{agent 'web_locator (lib/web_locator.py —
Brave|Anthropic locator + deterministic URL→id resolver; web text never enters the bundle)', status ∈ 'invoked' | 'not-applicable
(<state>)' | 'tool-unavailable', provider, invocation_id 'web_locator:<n_located|->/<n_results|->', evidence_generated[], reason?}` — fila
AUSENTE bajo off explícito o derivado (L: «no emitir las otras dos») *(corrector: `invoked` SÓLO si la familia MIDIÓ; «corrió y no envió» —
`skipped-cap (…)` / `skipped-budget (…)` / `error: …` con `measured false` — es `not-applicable (<state>)` con `reason`; null se imprime `-`,
jamás el literal Python `None`)* *(W9: alineado al código — NO existe el status `'kill-switch'` que el
borrador listaba: bajo off la fila no se emite para que la enumeración de excepciones M.1 sea verdad; `runs.WEB_LOCATOR_AGENT_ROW` es el literal
del `agent` y `runs.WEB_LOCATOR_AGENT = 'web_locator'` el del evento)*. *(G.10 cuota inyectada)* runs construye `web_quota = db.web_locator_reserve`
(H) y lo pasa a `_path_b_via_harness` → `path_b_bundle(web_quota=)` por inspección de firma (patrón `_path_b_bundle_accepts` :2678). El
harness NO importa `db`. *(G.11 constantes)* `WEB_KILL_SWITCH_STATE = 'kill-switch WITT_WEB_LOCATOR=off'`, `WEB_DECLARED_EXCEPTIONS =
('render_contract_version', 'web_locator', 'deterministic_checks.web_locator')` — EXACTAMENTE 3 (junto a :3010-3012) *(W9: alineado al
código — constantes importables de `runs`: `WEB_LOCATOR_AGENT`, `WEB_LOCATOR_AGENT_ROW`, `WEB_KILL_SWITCH_STATE` (alias de
`web_locator.WEB_KILL_SWITCH_STATE`: UNA verdad), `WEB_DECLARED_EXCEPTIONS`, `WEB_STATE_NOT_REQUESTED_NO_ROUND`,
`WEB_STATE_NOT_REQUESTED_NO_DIRECTIVE`, `WEB_TOOL_UNAVAILABLE_MODULE`, `WEB_TOOL_UNAVAILABLE_GATE`, `WEB_SEARCH_STAGE_NOTE`, `WEB_TOTAL_CLASS`,
`WEB_ANTHROPIC_SEARCH_STATE`, `WEB_GAP_FLAG_UNRESOLVED`, `WEB_GAP_FLAG_UNMATERIALIZED`, `WEB_GAP_FLAG_PREFIXES`, `WEB_FROZEN_KILL_SWITCH_KEYS`,
`WEB_FROZEN_COUNTER_KEYS` (+ `n_same_paper_dups`, `n_epmc_record_mismatch` — corrector), `WEB_FROZEN_SOURCE`, `WEB_ADDITIVE_KEYS_WITH_WEB_DATA`
(corrector: la enumeración de lo que SÓLO existe con datos web o con recomputo de disponibilidad — ver L); funciones `_web_provider_state`, `_web_quota_fn`, `_web_locator_frozen`, `_web_gap_flags`,
`_stack_web_gap_flags`, `_web_citations_fill`, `_web_usage_ctx`, `_web_checks`, `_web_agent_row`)*.

**(H) `db.py` — tabla NUEVA `web_locator_usage`, contador ATÓMICO.** `web_locator_usage = Table(…, Column('id', Integer, PK),
Column('month', String(7)) ('YYYY-MM' UTC), Column('provider', String(16)), Column('n_queries', Integer), Column('n_results',
Integer), Column('cost_usd_projected', Float), Column('updated_at', DateTime(timezone=True)), UniqueConstraint('month', 'provider'))`
— nace por `metadata.create_all` (:318), `_migrate` no la toca (sin ALTER, sin backfill; patrón `config_history`).
`db.web_locator_reserve(provider, month, cap, record=None) -> {granted, n_before, n_after, cap}`: INSERT idempotente de la fila del
mes + `UPDATE web_locator_usage SET n_queries = n_queries + 1, updated_at = :now WHERE month = :m AND provider = :p AND n_queries < :cap`
(rowcount 1 = granted; 0 = cap alcanzado) — atómico en SQLite y Postgres, sin carrera entre hilos (`--workers 1` con hilos) ni entre
procesos; `cap == 0` → sin tope (`state 'disabled (WITT_WEB_MONTHLY_CAP=0)'`); `record={n_results, cost}` suma a la fila tras la
llamada. `db.web_locator_usage_months(limit=12) -> filas` para `/usage` *(W9: alineado al código — además `db.web_locator_month_to_date(provider, month)
-> {month, provider, n_queries, n_results, cost_usd_projected, updated_at, row_present}` (ceros MEDIDOS con `row_present False` cuando no hay
fila), `db.web_locator_usage_table_exists()`, `db.WEB_LOCATOR_USAGE_TABLE` / `WEB_LOCATOR_USAGE_FIELDS`; `granted` es `None` cuando la llamada
lleva `record=`; SQL portable — sin `RETURNING`, `ON CONFLICT` ni `INSERT OR IGNORE`, decide por `rowcount`; DDL Postgres `SERIAL` /
`TIMESTAMP WITH TIME ZONE` / `FLOAT`)*. Secuencia (B.5): la caché se sondea ANTES de reservar → un
`cache_hit` no consume (`quota.state 'not-consumed (cache-hit)'`). Regla declarada: cuenta lo que ENVIÓ este despliegue; las sondas
CLI de Emmanuel (LG1/LG3/LG5) no pasan por la BD — margen 900 de ~1 000. *(corrector: (a) la reserva es UNA por consulta pero las peticiones
FACTURADAS pueden ser > 1 (reintento 429 de Brave, `max_uses` > 1 del alterno) → `locate` declara `n_requests_extra = max(0, n_billable − 1)` y
`record={n_results, cost, n_requests_extra}` lo SUMA a `n_queries` DESPUÉS de la llamada (la fila cuenta peticiones facturadas y puede rebasar el
tope por ese delta declarado — `QUOTA_RULE` lo dice); (b) el INSERT idempotente de la PRIMERA fila del mes corre en su PROPIA transacción
(`_web_locator_ensure_row(month, provider)` antes del `engine().begin()` del UPDATE): en PostgreSQL una violación de UNIQUE aborta la transacción
compartida hasta ROLLBACK y convertía la carrera legítima de dos hilos en una fila `error` de la ronda — SQLite no lo mostraba)*.

**(I) Alterno Anthropic `web_search` — caller PROPIO, una llamada, sólo URLs.** `web_locator._anthropic_web_search(query, cfg,
requirement_ids) -> fila-proveedor` (misma forma que `brave_web_search.locate`): `POST https://api.anthropic.com/v1/messages` por
urllib (`ANTHROPIC_URL`/`ANTHROPIC_VERSION` importados de `composite_auditor` si importable, si no literales declarados; semáforo
`composite_auditor._INFLIGHT` reutilizado si importable), body `{model, max_tokens 256, system 'You are a search dispatcher: call
web_search exactly once with the query verbatim; do not answer, do not summarize.', messages [{role user, content <query>}], tools
[{type WITT_WEB_ANTHROPIC_TOOL_TYPE (VOCABULARIO cerrado `web_locator.ANTHROPIC_TOOL_TYPES = ('web_search_20250305',)`; otro literal ⇒ default +
`default-invalid-env` — *corrector*: `web_search_20260209/20260318` sólo por ADR), name 'web_search', max_uses WITT_ANTHROPIC_WEB_SEARCH_MAX_USES
(1), allowed_domains: hosts de la tabla del resolutor o `WITT_WEB_ALLOWED_HOSTS` (≤ 20 dominios sin esquema; JAMÁS junto a
`blocked_domains`)}]}` — SIN `tool_choice` (un server-tool no se fuerza; Context 10), SIN `allowed_callers` (default `["direct"]` en
20250305). Modelo: `WITT_WEB_LOCATOR_MODEL` si está (validado contra `models.MODELS`, registrado en `ENV_TABLE`), si no
`models.resolve_role('elicitation')` (tabla única ADR-0081; **NINGÚN rol nuevo en `PIPELINE_ROLES`**: `panel_signature` los itera
:845 — veredicto de ambos jueces contra B). Se parsean SÓLO `server_tool_use.input.query` (→ `query_sent`, `query_sent_matches_directive:
bool`, `query_altered_by_provider`), `web_search_tool_result.content[] {url, title, page_age}` y `citations[].url` (todas como URLs a
resolver, JAMÁS como evidencia); `encrypted_content`, `encrypted_index`, `cited_text` y TODO texto del modelo se DESCARTAN sin
persistir (`n_text_blocks_discarded` contado); `usage.input_tokens/output_tokens` y `usage.server_tool_use.web_search_requests` se
MIDEN (`web_search_requests == 0` → `no-match`, `detail 'provider-declined-to-search'`; `n_billable = web_search_requests`). Errores:
`content {type 'web_search_tool_result_error', error_code}` → `status 'error: <error_code>'` (no facturado); HTTP 400 con «web search
is not enabled» → `'tool-unavailable (ADR-0084: org web_search disabled in Console)'` (y `provider_state` lo recuerda en el proceso);
HTTP 400 por `allowed_domains` fuera de la lista de la org → `'error: allowed_domains rejected by org policy (HTTP 400)'`; `stop_reason
'pause_turn'` → `'error: provider-paused (no continuation by design)'`; sin `ANTHROPIC_API_KEY` → `tool-unavailable`, cero red.
Propiedad DECLARADA del alterno (Context 10): los resultados se cuentan como tokens de entrada — el modelo despachador LEE texto web
aunque el caller lo descarte: por eso es alterno EXPLÍCITO (`WITT_WEB_LOCATOR=anthropic`), sin auto-failover desde Brave, y NO se
nombra «alterno operativo» en el README hasta pasar LG5 (condición de la tabla de ADRs). Sus tokens van a `cost.tokens {in, out,
class 'medición'}` y a `by_model` (G.7). *(corrector: la propiedad se DECLARA en el registro, no sólo a nivel tool — `locate` copia a la
fila-query (`frozen.web_locator.queries[]`) `web_locator.ANTHROPIC_ROW_KEYS = (tool_type, provider_property, n_text_blocks_discarded,
n_fields_discarded, request_shape, query_sent_matches_directive, stop_reason, max_uses, allowed_domains)` y `cost.provider_detail = {tool_type,
tool_type_source, tool_types_allowed, reads_web_text True, property ANTHROPIC_READS_WEB_TEXT}` (`web_locator.anthropic_provider_detail(cfg)`) viaja
en la fila, en el bloque D.4, en `token_usage.web_locator` y lo imprime la sección 53 del PDF: «EL MODELO DESPACHADOR LEE TEXTO WEB»)*.

**(J) `record_pdf.py` — sección 53 y gate de cobertura.** `KEY_BORN['web_locator'] = '1.13'`; `SECCIONES += ('web_locator',
'localizador')` (53 filas; asserts :234-236 intactos); `ORDEN_SECCIONES += ('localizador', 'LOCALIZADOR WEB (ADR-0084) - la web
LOCALIZA identificadores, jamas es fuente: ningun texto ni URL de la web entra a la evidencia; lo localizado se materializo por
Europe PMC con raw cacheado, lo no resuelto se declara y se cuenta')` después de `busqueda`; `_section_localizador(pdf, record,
ctx)` con `_tres_estados` (registro < 1.13 → `NO INSTRUMENTADO (contrato < 1.13)`), imprime estado + glosa, proveedor y fuente,
`entered_by`, consultas (query_en verbatim, req-ids, proveedor, país/idioma, `n_results`, caché, `USD [PROYECCION]`), tabla
`located[]` (id · kind · regla · confianza · fed_to · feed_state · seleccionado · fetched — **SIN la URL hallada** *(W9: alineado al código —
W8 decidió NO imprimir la URL hallada de un localizado: vive sólo en `frozen.web_locator.located[]`, que la Hoja pinta; el PDF circula fuera de la
app y el identificador canónico basta para la lectura humana)*),
tabla `unresolved[]` (URL completa rotulada «NO ADMISIBLE COMO EVIDENCIA» · host · razón glosada · título del buscador rotulado «no es
evidencia» — la brecha declarada que el humano revisa), contadores con la palabra
`MEDICION`, cuota `n/cap` con `quota.rule`, `resolver_version`, `text_policy`, y bajo kill-switch el literal; `_section_gate` gana
bloque `web_locator` (4 predicados con ok/gating/offenders + `rules`) y `'web_locator'` entra a `conocidas` (:1495-1498). Cada `fn`
llama LITERALMENTE `record.get("web_locator")` (regla R10; `PDF_ACCESS_RE` de la webapp). `epistemic_summary.web_*` en `_facet`.

**(K) Regularización del precedente 2026-05-14.** `web_locator.NOT_ADMISSIBLE_PRECEDENTS` (B.8) + smoke que MIDE: los 2 archivos
existen (o su ausencia se declara), `fetch_paper._cache_lookup` con el glob real NO los devuelve para ningún ident, ningún módulo de
`analysis/scripts/lib`, `rag_index/query_service` ni `.tooluniverse/tools` los nombra (grep == 0), y `verify_output.
_bundle_evidence_index` no indexa nada sin `source`. No se mutan ni borran; los reports de mayo que los citan quedan como históricos.

**(L) Kill-switch y byte-identidad — M.1 de la casa.** `WITT_WEB_LOCATOR=off` (explícito) o derivado `off` (sin llave, env unset):
familia web excluida con el literal EXACTO de 7d9ce15, `harness_state`/`demand` idénticos, 0 eventos `stage.web.*`, 0 ítems web,
`token_usage` sin `web_locator`, `citations[]` sin `located_via`, `agents_invoked` con fila `kill-switch` — NO: *(síntesis: la fila
`web_locator` de `agents_invoked` y `n_located_via_web` NO se emiten bajo off para que la enumeración de excepciones sea verdad —
patrón «no emitir las otras dos», ADR-0083 M.1)*; **el frozen es igual al 1.12 del MISMO fixture (json sort_keys, keyset Y valores)
salvo EXACTAMENTE `WEB_DECLARED_EXCEPTIONS = ('render_contract_version', 'web_locator', 'deterministic_checks.web_locator')`**,
donde `frozen.web_locator = {state, provider 'off', provider_source, kill_switch {…}, state_vocabulary, rule}` y
`deterministic_checks.web_locator = {state}`; el smoke mide el diff de paths == ∅ contra la corrida ENCENDIDA del mismo fixture tras
restar las aditivas 1.13 (`web_locator`, `deterministic_checks.web_locator`, fila web de `agents_invoked`, `citations[].located_via`,
`citations_support_summary.n_located_via_web`, `token_usage.web_locator`/`estimated_cost_usd_total_projected`, `epistemic_summary.web_*`,
`search_ledger.plan.families_order_rule`, `selection.pool_admission_rule/tie_break_web_located`) y la identidad de corrida. ADEMÁS
(W0) un golden LIGERO grabado EN 7d9ce15 antes de la primera línea: `fixtures/golden_plan_web_directive_7d9ce15.json` = salida de
`build_search_plan` con la directiva web de `smoke_search_harness.py:170-171`, `harness_state_for('web','web')` y la forma de
`demand()` — determinista (sin reloj) — contra el que la obra compara byte a byte bajo off. *(síntesis: el ganador proponía un golden
del frozen 1.12 completo grabado en 7d9ce15; el patrón de la casa es el diff on/off en el mismo smoke (M.1) porque un frozen
cross-commit arrastra ruido de cada stub; se adopta el diff M.1 como gate y el golden ligero del PLAN como vara del literal.)*
*(corrector — la VERDAD medible de «EXACTAMENTE 3»: (i) los literales COMPARTIDOS del consejo que viajan al frozen (`council.directives_rule`,
`council.coverage.after_search.rule`) habían cambiado respecto a 1.12 en TODA corrida con consejo (el diff ON-vs-OFF del mismo árbol no lo veía); se
restauran BYTE A BYTE y la ampliación web viaja en llaves PROPIAS que sólo existen con datos web: `council.directives_availability_rule` (sólo
cuando hubo recomputo de disponibilidad, junto a `harness_state_at_plan/at_compile/recomputed`) y `coverage.after_search.web_locator_source /
web_locator_rule` (sólo con ledger web NO vacío — un bloque D.4 con `queries/located/unresolved` vacíos NO es ledger web); `smoke_run_pipeline`
compara ahora los literales con los strings de 7d9ce15 y `smoke_council` mide que `DIRECTIVES_RULE`/`AFTER_SEARCH_RULE` no nombran ADR-0084.
(ii) `runs.WEB_ADDITIVE_KEYS_WITH_WEB_DATA` ENUMERA las llaves aditivas que existen SÓLO con datos web o con recomputo (`citations[].located_via`,
`n_located_via_web`, fila web de `agents_invoked`, `token_usage.web_locator/estimated_cost_usd_total_projected/total_class/by_stage.search.
web_locator_usd_projected`, `search_ledger.plan.families_order_rule`, `path_b.selection.pool_admission_rule/tie_break_web_located`, recomputo del
consejo, `availability_rule`, `web_locator_source/_rule`, `by_requirement[web].web_locator`): bajo off en un fixture SIN datos web ninguna existe,
y las 3 excepciones son la verdad completa del frozen; con directiva web bajo off, las llaves de recomputo aparecen porque el ESTADO cambió entre
plan y corrida — información que en 1.12 no podía existir. (iii) `epistemic_summary` no es parte del frozen (columna aparte; G.8). (iv) Web nombrada
en la env bajo off/sin llave: plan y fila MÍNIMA de 7d9ce15 (C.4; único valor distinto en la fila: `host 'api.search.brave.com'`, el de la tabla
C.1 — declarado); la CAUSA (`BRAVE_API_KEY unset`) viaja en `frozen.web_locator.state`, la fila conserva el literal `tool-unavailable (ADR-0084)`.)*

**(M) Invariantes operativos.** *(M.1 §6 no-hang)* un proveedor caído deja fila declarada (`error`/`tool-unavailable`) y la ronda
sigue; `_run_web_family` envuelve TODO en try (patrón :1157-1160); la materialización por EPMC usa el presupuesto de la familia y
`_fetch_or_declare`-like sin relanzar. *(M.2 cero red en smokes)* `urlopen` bloqueado y contado == 0; fakes por `tools={'web': fake}`
y `provider_fn`; `fetch_paper._resolve_one` monkeypatcheado con records EPMC falsos; caché en tempdir; `mcp_cache` byte-idéntico.
*(M.3 ctx)* el runner web APPENDEA sobre `ctx['dois']`/`ctx['curies']` (listas pre-creadas :1050; `_ctx_list` :1205-1209) y jamás
reasigna — smoke con `id()` de la lista antes/después. *(M.4 env en la llamada)* `web_locator.env_config()` se lee en cada corrida;
`provider_state()` en cada plan/compilación/despacho. *(M.5 identidad)* la llave jamás en salida/ledger/caché/fixture/eventos.
*(M.6 históricos)* registros < 1.13 leen `web_locator` ausente → PDF «NO INSTRUMENTADO (contrato < 1.13)», webapp «?»; nada se recalcula.

## Consequences

- **Contrato: `render_contract_version` sube a "1.13"** — todo aditivo. NINGÚN literal nuevo en `SOURCE_STATES` (`skipped-cap`
  reutilizado con `detail`), en `SearchFamily` (ya trae `web`), en el enum `kind` de `SYNTH_TOOL` ni en `HARNESS_STATE_PREFIXES`
  (los dos literales con causa de (B.3) caen bajo el prefijo `unsatisfiable-by-harness (` que la webapp ya glosa). Históricos sin backfill.
- **La webapp debe tipar y pintar** (`witt-webapp/src/api/types.ts`, todo `?`; tres estados en lo nuevo; OTRO workflow): **(1)**
  `RegistroCongelado.web_locator?: WebLocatorBlock` (forma EXACTA de (G.2)) con unions CERRADOS sin escape en los exactos:
  `WebLocatorState` (exactos + prefijos `tool-unavailable (ADR-0084` · `skipped-cap (` · `skipped-budget (` · `error: `),
  `WebProvider = 'brave' | 'anthropic' | 'off'`, `WebProviderSource` (prefijos), `WebLocatedKind` (7), `WebFedTo`, `WebFeedState`
  (exactos + prefijos), `WebUnresolvedReason` (4), `WebQuotaState`, `WebEnteredBy`, `WebLocated`, `WebUnresolved`, `WebLocatorQuery`,
  `WebLocatorCost` (con `class 'proyección'` y `tokens?.class 'medición'`), `WebLocatorQuota`. **(2)** `DeterministicChecks.web_locator?:
  WebLocatorChecks` (`WebCheckState` exactos + prefijos; 4 predicados `{ok, gating, n_checked, offenders[], rule}`; bajo kill-switch
  sólo `{state}`). **(3)** `Citation.located_via?: 'web' | null`; `CitationsSupportSummary.n_located_via_web?: number`. **(4)**
  `EpistemicSummary.web_locator_state? / web_n_located? / web_n_unresolved?` (null ≠ 0: «no midió» vs «0 medido»). **(5)**
  `answer.gap_flags` sigue `string[]` (los dos strings de conteo con prefijos `web-located-unresolved:` / `web-located-unmaterialized:`
  se agrupan en Brechas bajo «localizadas por la web» con enlace interno a la sección del localizador). **(6)** `TokenUsage.web_locator?`
  y `TokenUsage.estimated_cost_usd_total_projected?` + `total_class?`; `by_stage.search.web_locator_usd_projected?`; con anthropic
  `by_stage.search {in, out, model, state}` *(corrector: `TokenUsage.web_locator.n_results | n_located | n_materialized | n_unresolved: number | null`
  — null = no midió (p. ej. `skipped-cap`); `WebLocatorBlock` tiene TRES keysets medidos: `located`/`no-results` (61 llaves), «no medido» con ronda
  y «sin ronda» (unificadas por el corrector: `cost` con 0 facturables, `cost_usd_projected 0.0`, `dedup_layer_rule`, `materialize_rule`,
  `located_close_keys` presentes; los contadores de `runs.WEB_FROZEN_COUNTER_KEYS` AUSENTES) y kill-switch (6 llaves); todo contador `?`)*.
  **(7)** `SearchSource` y `SearchSourceEventPayload` += `provider?, n_queries?, n_results?,
  n_located?, n_materialized?, n_unresolved?, n_already_present?, cost_usd_projected?, quota_state?`; `SearchLedger.plan.families_order_rule?`;
  `SearchSelection.pool_admission_rule? / tie_break_web_located?` (bundle Y evento `stage.path_b.selection` — corrector); `SearchPlanEventPayload.
  families_order_rule?` (corrector) *(corrector — keyset MEDIDO de la fila web de `frozen.search_ledger.rounds[].sources[]` además de las 9 de C.7:
  `web_locator_state, web_locator_frozen_at, text_policy, provider_available, provider_source, quota_hook, max_queries, max_queries_source,
  max_materialize, max_materialize_source, dedup_layer, dedup_layer_rule, materialize_rule, n_queries_planned, n_queries_dropped_by_cap,
  n_epmc_gets, n_fed_ctx, n_located_not_fed, n_duplicates_in_response, n_not_found_in_europepmc, n_same_paper_dups, n_epmc_record_mismatch`;
  `SearchCall += http_status?, n_results?, n_located?, n_materialized?, n_unresolved?, provider_elapsed_s?, retries_429?, throttle_wait_s?,
  timeout_s_scope?, query_sent?, directive_requirement_ids?` — la webapp tipa el keyset o declara `SearchSource` con un sub-bloque abierto)*.
  **(8)** `PathBPaperResumen += located_via?, located_from?, search_rec_source?` *(corrector: `located_via` viaja también — `WEB_PAPER_COPY_KEYS`)*;
  `StagePathBPayload += n_web_located?, n_web_unresolved?`. **(9)** NUEVO `StageWebLocatePayload` (forma de (G.6)) y caso
  `ev.type === 'stage.web.locate'` en `Traza.describir()` (etiqueta «localizador», una fila por consulta: proveedor · consulta ·
  resultados · localizados · materializados · sin resolver · caché · USD [PROYECCIÓN] · cuota n/cap; voz alerta en `error`/`skipped-cap`);
  la fila `stage.search.source` de familia `web` pinta las llaves de (7) y el cintillo fijo «la web localiza, no es fuente»;
  `families_excluded[web].reason` glosado por prefijo (ya existe). **(10)** `DeterministicGateEventPayload.web_locator_state?`.
  **(11)** `UsageResponse.web_locator?: {state 'measured' | 'not-measured', n_runs_with_queries, n_runs_web_locator_declared, n_runs_locator_off,
  by_state, by_quota_state, n_queries, n_queries_billable, n_results, n_located, n_materialized, n_unresolved, rate_located_over_results:
  number|null, cost_usd_projected, estimated_cost_usd_total_projected, by_provider {brave? | anthropic? {n_runs, n_queries, n_queries_billable,
  n_results, n_located, n_materialized, n_unresolved, cost_usd_projected, price_usd_per_1k, tokens_in, tokens_out}}, month_to_date {state ∈
  app.USAGE_WEB_MONTH_STATES ('under-cap' | 'cap-reached' | 'disabled (WITT_WEB_MONTHLY_CAP=0)' | 'table-missing' | 'error'), month, provider,
  provider_source, row_provider, n_queries, n_results, cost_usd_projected, cap, cap_source, remaining, row_present, updated_at,
  credit_usd_assumed 5.0, credit_source_url, rule, rows[]}, class app.USAGE_WEB_LOCATOR_CLASS, source, rule, price_as_of}` — 21 llaves
  *(W9: alineado al código — forma REAL de `app._WebLocatorUsageAccumulator.result`; `totals.estimated_cost_usd` NO incluye el localizador)*. **(12)**
  `CouncilDemand.web_locator_provider_state?` y `unsatisfiable_families_source` (string). **(13)** `CouncilAfterSearchRow.web_locator?`;
  `CouncilDirective.harness_state_at_plan? / harness_state_at_compile? / harness_state_recomputed?` y `CouncilDirectiveExcluded.harness_state_at_plan?
  / harness_state_at_compile? / harness_state_recomputed?` (sólo cuando difieren) — `CouncilRequirement` NO cambia *(corrector: el código pone las
  llaves en `council.directives[]` y `council.directives_excluded[]`, jamás en `council.ledger.requirements[]`)*; `Council.directives_availability_rule?`
  (sólo con recomputo). **(14)** `AgentsInvokedRow` acepta la fila `web_locator`
  (status incluye `'tool-unavailable'`; campo `provider`). **(15)** *(W9: alineado al código)* `EnteredBy += 'env:WITT_SEARCH_DEFAULT_FAMILIES'`
  — el literal que W3 emite cuando `web` entra por la env del operador y que el union de la webapp hoy NO admite (hueco `[trigger]` MEDIDO por el
  gate de paridad, abajo); `SearchSource.web_locator_frozen_at?` (la fila web del ledger congelado apunta a `frozen.web_locator`);
  `TokenUsage.total_class?` y `by_stage.search.model? / state?` con `anthropic`; `StageWebLocatePayload` con el payload de (G.6). **Hoja (M4):** Entrada NUEVA «2c · Localizador web» entre 2b Lazo de búsqueda y 3 Evidencia
  (patrón de B): (i) consultas enviadas verbatim con chips «lo pidió el consejo · req-…», proveedor y fuente, país/idioma/freshness,
  `n_results`, caché, USD con la palabra PROYECCIÓN; (ii) tabla «localizado → identificador»: URL como PALABRA-MÁQUINA (jamás enlace a
  texto), host, id + kind, regla y confianza, «entró como» (materializado por Europe PMC · DOI → unpaywall · curie → monarch · sólo
  comprobación en la DI · no consumido en 1.13 · ya presente · no encontrado en EPMC), admitido/duplicado, seleccionado, fetched;
  (iii) «sin resolver» como brechas declaradas: URL, título del buscador rotulado «título del buscador — no es evidencia», razón
  glosada; (iv) contadores con MEDICIÓN de esta corrida; (v) cuota `n/cap` con `quota.rule` y crédito supuesto declarado; (vi)
  `text_policy` y kill-switch como ESTADO declarado (jamás check verde por null). En Evidencia, la cita con `located_via 'web'` gana
  cintillo «localizado en la web · registro y texto de Europe PMC» sin fundirse con las nativas. En Gate, bloque `web_locator` con los
  4 predicados (rojo = inadmisible por `web_text_not_cited`/`web_located_cited_requires_fetch`/`web_items_native_only`; `no-web-items` gris
  declarado). **Consejo:** `harness_state` de un requisito web pinta «satisfiable» con llave y el literal completo sin ella;
  `harness_state_recomputed` como nota; `/council/demand.web_locator_provider_state` en la vista de demanda. **M8 Consumo:** bloque
  «Localizador web» desde `/usage.web_locator` (consultas MEDIDAS · USD PROYECTADO por proveedor · KPI del mes n/cap · «la verdad del
  saldo es el dashboard de Brave») APARTE de tokens; por corrida, `token_usage.web_locator` y el total `estimated_cost_usd_total_projected`
  como segunda línea con su clase. **Lista/Banco:** desde `epistemic_summary`: «web: N localizados · K sin resolver» (null → «no midió»).
  **M6 Configuración:** campos `web.locator`, `web.provider` por la vía genérica de `/config-history` (fila `new-field` al arrancar).
- **Qué mide el gate de paridad (`witt-webapp/tools/parity_check.py`):** (B) registro — `web_locator` (llave nueva del frozen) debe
  tener lector en la Hoja y en `record_pdf` (PDF_ACCESS_RE; `SECCIONES` como segunda fuente → 53 por la regex ANCLADA); (C) etapas —
  `stage.web.locate` con caso en `describir`; (D) PDF — `PDF_NESTED += web_locator.queries[] / located[] / unresolved[]`; (A) rutas —
  CERO rutas nuevas (`/usage` y `/council/demand` extendidos, ya envueltos); vocabularios — leer `web_locator.WEB_STATES_EXACT/_PREFIXES,
  LOCATED_KINDS, FED_TO, FEED_STATES_*, UNRESOLVED_REASONS, PROVIDERS, QUOTA_STATES_*`, `verify_output.WEB_CHECK_STATES_*`,
  `runs.WEB_DECLARED_EXCEPTIONS` (3) y validar TODO fixture por ruta (`frozen.web_locator.state/.provider/.located[].kind|fed_to|
  feed_state/.unresolved[].reason/.quota.state`, `deterministic_checks.web_locator.state`, `stage.web.locate.payload.provider_status ∈
  SourceStatus`). `parity_debt.json`: si la webapp entrega la ranura en la misma obra, 0 líneas; si no, UNA por hueco con `adr 'ADR-0084'`
  (`[registro] web_locator`, `[etapas] stage.web.locate`; `[pdf]` ninguna: el backend la pinta). **MEDIDO por W7 el 2026-09-16** (copia de lectura
  de `parity_check.py` con `BACKEND` → este worktree; la webapp @ `d41e4a8` NO se tocó): **EXIT 1** · 968 filas medidas · **8 huecos** — 5 ya
  declarados en `parity_debt.json` y 3 SIN declarar: `[registro] web_locator` CONGELA SIN TIPO · `[etapas] stage.web.locate` SIN CASO EN TRAZA ·
  `[trigger] consejo:entered_by 'env:WITT_SEARCH_DEFAULT_FAMILIES'` LITERAL SIN TIPO · `[pdf]` 0 huecos · rutas 0 nuevas (todas OK). Son la lista
  «tipar y pintar» de arriba: los salda el workflow de la webapp.
- **Gate de cobertura del PDF (ADR-0083 K):** `frozen_keys` 52 → 53 con `web_locator`; `pdf_sections_cover(frozen 1.13 real) ==
  {missing [], extra []}`; born `'1.13'`; regex ANCLADA devuelve 53; smoke_record_pdf 56 → ≥ 63 — **MEDIDO W7: 68/68**.
- **Redeploy:** Dokploy con las 17 env WITT_* (defaults en compose) + `BRAVE_API_KEY` (LG0); una fila `new-field` en
  `config_history` por `web.locator`/`web.provider` al arrancar (excepción DECLARADA del kill-switch, patrón 0082 L.2 ii / 0083 O.5);
  el redeploy pendiente de ADR-0076…0083 debe estar en prod ANTES (LG9). `mcp_cache` con escritura (raw_brave_* y raw_paper_*).
- **Con llave presente los `must` de familia web dejan de ser «unsatisfiable» (no gatean) y pasan a GATEAR la competencia** → más
  corridas no competentes → más pass2 (costo INDUCIDO de modelo, US$0.2–0.5 por pass2 según M8; ver Proyección). Es el comportamiento
  pedido («si el consejo dice que falta, se busca»); medible en LG2/LG7; kill-switch inmediato por env.

## Tabla de env (todas con default declarado; lector `web_locator.env_config()` tolerante en tiempo de llamada; toda env = reinicio; las 17 `WITT_*` entran a `models.ENV_TABLE` con `adr '0084'` y `SNAPSHOT_FIELDS += ('web.locator', 'web.provider')` FUERA de `panel_signature`; `BRAVE_API_KEY` queda FUERA de `ENV_TABLE` — la tabla no registra secretos — y sólo su PRESENCIA viaja)

| Variable | Default | Lector | Efecto / fuente declarada |
|---|---|---|---|
| `BRAVE_API_KEY` | — (unset; PENDIENTE de Emmanuel en Dokploy; jamás git/vault/memoria) | `brave_web_search._api_key` · `web_locator.provider_state` | cabecera `X-Subscription-Token`; en salida/ledger/caché/fixture sólo `api_key_present: bool`; ausente ⇒ provider derivado `off` (literal de exclusión byte-idéntico) y `frozen.web_locator.state 'tool-unavailable (ADR-0084: BRAVE_API_KEY unset)'`, cero red |
| `WITT_WEB_LOCATOR` | — (unset ⇒ derivado: `brave` si hay llave, `off` si no) | `web_locator.provider_state` (plan, compilación, despacho) | `brave \| anthropic \| off`; `off` = kill-switch (L); fuera de vocabulario ⇒ `off` con `provider_source 'default-invalid-env:WITT_WEB_LOCATOR'`; `anthropic` es EXPLÍCITO (sin auto-failover) |
| `WITT_WEB_MAX_RESULTS` | `10` (clamp 1..20) | `brave_web_search.locate` | `count` por consulta (tope documentado 20); anthropic no aplica (`count_sent null`) |
| `WITT_WEB_MAX_QUERIES` | `3` (clamp 1..10) | `search_harness._run_web_family` | consultas por ronda (una por directiva); sobrantes `skipped-cap` en `calls[]` + `n_queries_dropped_by_cap`; `inputs_used` íntegro |
| `WITT_WEB_MAX_MATERIALIZE` | `6` (clamp 0..20) | `_run_web_family` | ids de literatura verificados en Europe PMC por ronda (`_resolve_one`, una GET c/u); resto `not-materialized (feed cap)`; `0` = sólo localizar (todo queda `not-materialized`, nada entra al pool) |
| `WITT_WEB_MAX_QUERY_CHARS` | `400` (clamp 1..2000 — W9: alineado a `ENV_SPECS`) | `brave_web_search.locate` | tope NUESTRO de `q` (Brave no documenta longitud); `query_truncated` declarado; la directiva ya viene ≤ 200 |
| `WITT_WEB_BUDGET_S` | `30` (clamp 1..120) | `SEARCH_DISPATCH['web'].budget_s` | presupuesto de la familia dentro de la ronda (reparto `min(budget_s, restante/familias)` como hoy); cubre consultas + materialización |
| `WITT_WEB_MIN_INTERVAL_S` | `1.0` (clamp 0..60 — W9) | `net_throttle.get_throttle('api.search.brave.com')` | pacing PROPIO (Brave publica 50 qps); `throttle.waited_s` medido; LG3 mide cabeceras y ajusta por env |
| `WITT_WEB_COUNTRY` | — (no se envía) | `brave_web_search.locate` | `country` 2 letras; vacío ⇒ ausente (`country_sent null`) |
| `WITT_WEB_LANG` | `en` | idem | `search_lang` ISO 639-1 (las `query_en` son inglés); presente y VACÍA ⇒ no se envía (`env_config` devuelve `lang None` con `source 'env:WITT_WEB_LANG (empty: not sent)'` — *corrector: antes el lector devolvía el default `en` y anulaba la semántica del tool*); ausente ⇒ `en` |
| `WITT_WEB_FRESHNESS` | — (no se envía) | idem | `pd \| pw \| pm \| py \| YYYY-MM-DDtoYYYY-MM-DD`; fuera de forma ⇒ no se envía + `freshness_ignored` |
| `WITT_WEB_ALLOWED_HOSTS` | — (unset = `'all (resolver table + doi-in-url on any host)'`) | `web_locator.resolve_urls` · `_anthropic_web_search` | CSV que RESTRINGE los resolubles (host fuera ⇒ `host-not-allowed`); para anthropic viaja como `allowed_domains` (≤ 20, sin esquema); semánticas distintas declaradas (`allowed_domains` incluye subdominios; la tabla vuelve a filtrar por host) |
| `WITT_WEB_GENERIC_DOI_RULE` | `1` | `web_locator.resolve_urls` | regla `doi-in-url-any-host` (`confidence 'pattern-only'`); `0` = sólo reglas por host; la existencia la verifica EPMC (C.5) |
| `WITT_WEB_MONTHLY_CAP` | `900` (clamp 0..1 000 000 — W9) | `db.web_locator_reserve` (vía `web_quota`) | tope mensual UTC de consultas facturables por proveedor (≈ 90 % de las ~1 000 que cubre el crédito de US$5 — PROYECCIÓN); alcanzado ⇒ `skipped-cap` con detail, cero red; `0` = sin tope declarado |
| `WITT_WEB_TEST_QUERY` | — (unset) | `search_harness.build_search_plan` | consulta EXPLÍCITA del operador cuando `web` entra por `WITT_SEARCH_DEFAULT_FAMILIES` (`query_source 'operator-env:WITT_WEB_TEST_QUERY'`); sin ella, `pass1_query_en`; nunca en producción |
| `WITT_ANTHROPIC_WEB_SEARCH_MAX_USES` | `1` (clamp 1..5 — W9) | `web_locator._anthropic_web_search` | `max_uses` del server-tool (una directiva = una búsqueda); `max_uses_exceeded` declarado como error no facturado |
| `WITT_WEB_ANTHROPIC_TOOL_TYPE` | `web_search_20250305` | idem | literal del `type` — VOCABULARIO CERRADO `web_locator.ANTHROPIC_TOOL_TYPES = ('web_search_20250305',)` (básico, sin dynamic filtering; `web_search_20260209/20260318` están en «Qué NO se hace» y entran por ADR, jamás por env); otro literal ⇒ default + `default-invalid-env:WITT_WEB_ANTHROPIC_TOOL_TYPE`; el tipo ENVIADO y la propiedad «el modelo LEE texto web» viajan en `frozen.web_locator.queries[].tool_type / provider_property` y en `cost.provider_detail {tool_type, tool_type_source, tool_types_allowed, reads_web_text True, property}` *(corrector: el borrador prometía `cost.provider_detail` y no existía; el env aceptaba cualquier literal)* |
| `WITT_WEB_LOCATOR_MODEL` | — (unset ⇒ `models.resolve_role('elicitation')`) | idem | modelo del despachador; validado contra `models.MODELS`; FUERA de `PIPELINE_ROLES` (la firma no cambia) |
| `WITT_SEARCH_DEFAULT_FAMILIES` · `WITT_MCP_CACHE_DIR` · `ANTHROPIC_API_KEY` | ya existen | — | nombrar `web` ES la directiva del operador; caché por día `raw_brave_*`; la llave Anthropic sólo la lee el alterno |

## Gates NO-SPEND (máscara de siempre: `WITT_BACKEND_DB_URL` sqlite tmp · `NEO4J_URI=''` · `RAG_BACKEND=sparse` · `OPENAI_API_KEY=''` · `ANTHROPIC_API_KEY=''` · `BRAVE_API_KEY=''` · `WITT_RUN_ORIGIN=smoke` · `WITT_MCP_CACHE_DIR=<tmp>`; venv `dev/.venvs/witt-query-service`)

| Gate | Hoy @ 7d9ce15 | Tras ADR-0084 — meta → **MEDIDO por W7 el 2026-09-16** | Qué MIDE de nuevo |
|---|---|---|---|
| `smoke_tools_d.py` (NUEVO, patrón smoke_tools_c: `_get` monkeypatcheada, `net_throttle._sleep` stub, tempdir) | — | ≥ 26 → **50/50** (fixture `provenance: synthetic`) | D0 sin llave → `tool-unavailable`, 0 GETs, `api_key_present False` · D1 fixture SINTÉTICO → `success`, `results[]` SÓLO `{url,title,host,age,page_age}`, `fields_dropped` ∋ description/extra_snippets, el sobre de caché SÍ conserva `description` (raw íntegro) y la SALIDA no · D2 `web.results []` → `no-match` · D3 503 → `error` con `http_status`, nada cacheado · D4 401 → `error: auth` · D5 429+`Retry-After 2` → UN reintento (sleep stub == 2.0), 2º 429 → error · D6 cuerpo HTML → `error: NonJSONBody` · D7 `timeout ≤ 0` → `skipped-budget`, 0 GETs · D8 2ª llamada del día `cache_hit True`, 0 GETs · D9 `q` de 500 chars → `query_truncated`, ≤ 400 · D10 la llave fake JAMÁS en salida/caché/fixture · D11 dos llamadas → `throttle.waited_s ≥ 0.999` con reloj falso · D12 `url_sent` sin token y SIN `result_filter/text_decorations/spellcheck/extra_snippets` (`params_sent` == documentados) · D13 `count 50` → 20; `freshness 'zz'` → no enviado + `freshness_ignored` · D14 422 con cuerpo que nombra `freshness` → `error: HTTP 422 … freshness` · D15 `query.altered` ≠ original → `query_altered_by_provider True` · D16 `_fixture.synthetic True` declarado; si existe fixture LIVE lo prefiere y lo declara |
| `smoke_web_locator.py` (NUEVO) | — | ≥ 60 → **170/170** → corrector **182/182** (golden 61 casos wlr-2, tipo de tool cerrado, `WITT_WEB_LANG=""`, llaves del alterno en la fila) | GOLDEN del resolutor sobre ≥ 40 URLs fijas (≥ 2 por regla + trampas: doi con `.` final y `?utm`, pubmed con `/?dopt=`, PMC en ambos hosts, europepmc `/abstract/MED/`, zfin `ZDB-PUB` (located, `fed_to None`), ensembl con versión, uniprot válida/inválida, GEO `acc=GSE`, biorxiv `v2`, host cualquiera con DOI en path → `pattern-only`, sin patrón → `no-identifier-pattern`, `ftp://` → `unsupported-scheme`, `not a url` → `malformed-url`, host fuera de lista → `host-not-allowed`, misma DOI en 2 URLs → `duplicate-in-response`, PMID en `existing_ids` → `already-present`) · determinismo byte a byte, `urlopen` == 0 · `provider_state` × 8 combinaciones env/llave con `provider_source` exacto y `unavailable_reason` literal (off/derivado == `'tool-unavailable (ADR-0084)'`) · `locate()` con `quota_fn` que niega → `skipped-cap` sin llamar al proveedor (spy 0) · `cache_probe` positivo → cuota NO reservada (`not-consumed (cache-hit)`) · anthropic con fixture SINTÉTICO → URLs de `web_search_tool_result` + `citations`, `encrypted_content`/`cited_text`/texto AUSENTES (substring), `web_search_requests` medido, `input.query` ≠ directiva → `query_altered_by_provider`, error object → `error: max_uses_exceeded`, 400 «not enabled» → `tool-unavailable (… Console)`, `pause_turn` → `error: provider-paused`, body SIN `tool_choice` y con `allowed_domains` == lista · `cost_of`: 3 billables brave → 0.015 `class 'proyección'`; cache_hit no factura · `ENV_SPECS` tolerante (basura → default con `default-invalid-env`) · `NOT_ADMISSIBLE_PRECEDENTS`: 2 archivos, `_cache_lookup` no los devuelve, grep == 0 · `ENSDARG` del store → `in-store`, inventado → `not-in-store` (store real, 0 red) |
| `smoke_search_harness.py` | 47 | ≥ 63 → **91/91** → corrector **94/94** (fila mínima bajo off + env, dedup por paper, mismatch EPMC, DOI entre comillas, timeout acotado) | tabla de 15 con `web` `adapter 'web'`/`availability`; `provider off` → excluida con literal byte-idéntico y plan == `golden_plan_web_directive_7d9ce15.json`; `provider brave` (fake por `tools={'web': fake}` + monkeypatch de `provider_state`) + directiva → web PRIMERA en `families`, `families_order_rule`, query de la directiva, `entered_by 'directive'`; env `WITT_SEARCH_DEFAULT_FAMILIES=…,web` sin directiva → `pass1_query_en` (la pregunta ES ausente por substring), con `WITT_WEB_TEST_QUERY` → esa; ronda: fake 6 URLs (1 PMID nuevo, 1 DOI ya presente, 1 ZDB-GENE, 1 ENSDARG, 2 sin patrón) + `_resolve_one` falso → `items` == [1 candidato `source 'europepmc'`, `source_family 'web'`, `kind 'literature-candidate'`, `identifier_provenance 'web-located:pubmed-path'`, `url` canónica, `title` de EPMC, SIN llaves `title_web/description`], `ctx['dois']` ganó el DOI, `ctx['curies']` la curie, `located[]` con `feed_state` correctos, `unresolved` 2, fila `success n_found 6 n_materialized 1`; `_resolve_one` falso que devuelve None → `not-found-in-europepmc`, 0 ítems; orden: `unpaywall_crossref`/`monarch` (fakes) RECIBEN el DOI/curie en la MISMA ronda (spy); `WITT_WEB_MAX_QUERIES=1` con 3 directivas → 1 llamada + 2 `skipped-cap` + `inputs_used` con las 3; `WITT_WEB_MAX_MATERIALIZE=1` con 3 PMIDs → 1 materializado + 2 `not-materialized (feed cap)`; auth error en la 1ª → las demás `skipped-cap (auth failed …)`; `quota_fn` niega → fila `skipped-cap` cuota, 0 llamadas; fake que lanza → fila `error`, ronda sigue; timeout 0 → `skipped-budget`; `id(ctx['dois'])` inalterado; `source_event_payload` de web trae `provider/n_located` y la de alliance NO; `unsatisfiable_families()` == `('tooluniverse','web')` bajo off y `('tooluniverse',)` con llave fake; 0 URLs en `round_event_payload`/`source_event_payload` (regex); `urlopen` == 0 |
| `smoke_web_pipeline.py` (NUEVO: `_path_b_harness` con fake web + `_resolve_one` + `fetch_external` stubs en tempdir) | — | ≥ 20 → **29/29** → corrector **32/32** (S4 con abstract real → texto RETENIDO y E.3 ok; S8 mismo paper en 3 URLs; S9 record mismatch; eventos con reglas) | candidato web PMID → paper `source 'europepmc'`, `source_family 'web'`, `identifier_provenance 'web-located:…'`, `search_rec` de EPMC (NO el `title_web` del fixture: assert substring), `text_provenance 'abstract'`, `fetched.found True`, `url` canónica ≠ URL hallada, `located_from` sin URL; `fetch_external` stub `found False` → paper sin pasaje; nativo + web mismo PMID → `selection.duplicates[]` con `source_family 'web'`, `of` = id nativo, `pool_admission_rule` presente, `located[].feed_state 'already-present (dup of …)'`; 5 nativos + 1 web con n=5 → web `not_selected`, `n_located_not_selected 1`, `tie_break_web_located` presente; 0 nativos + 1 web → `selected rank 1`; `n_results_by_source.web == 0` y `.europepmc` cuenta el web; `block['web_locator']` completo (contadores, cost, quota); `path_b_event_payload.papers[]` trae `located_from` sólo en el web; `_PROMPT_PATH_B_TOP`/`_PROMPT_PAPER_KEYS` importadas de runs NO incluyen `web_locator`/`url`/`located_from`; sin web: `selection` byte-idéntica a hoy (sin `pool_admission_rule`); `mcp_cache` intacto; `urlopen` 0 |
| `smoke_gate_citations.py` | 80 | ≥ 92 → **100/100** | cita `kind 'other'` id `https://example.org/x` → `web_text_not_cited` `id-is-url` → inadmisible con reason; cita `https://doi.org/<doi del bundle>` → OK (carve-out); cita id == URL de `unresolved[]` → `id-matches-unresolved-url`; cita PMID a paper web-localizado `found True` → OK (la evidencia materializada ES citable); mismo con `found False` → `web_located_cited_requires_fetch` False → inadmisible; paper `source 'web'` inyectado → `web_items_native_only` `source-web`; paper web con `identifier_provenance 'europepmc-api-live'` → `provenance-not-web-located`; `text_excerpt` con `found False` → `text-without-fetch`; `url` hallada → `non-canonical-url`; `direct_answer` con URL de `located[]` → `web_urls_not_in_answer` False, gating False, admisibilidad no cambia; sin ítems web ni ledger → `no-web-items` y 0 predicados en la conjunción (byte a byte hoy); kill-switch → `{state}` |
| `smoke_council.py` · `smoke_council_index.py` · `smoke_council_http.py` | 70 · 63 · (actual) | +6 · +4 · +2 → **77/77 · 67/67 · 76/76** → corrector `smoke_council` **78/78** (literales 1.12 + `availability_rule`) | (11) bajo off → literal de hoy byte a byte; con `provider_state` parcheado → `satisfiable` y directiva `compiled` con `query_en`; `harness_state` guardado ≠ recomputado → `harness_state_recomputed True`; `coverage_after_search` con candidato web admitido → `retrieved-for` + `web_locator{…}` sólo en el requisito web; 6a `unsatisfiable_families()` dinámica; `DEMAND_FAMILIES` conserva `web`; `demand()` cuenta `web` histórico CON llave fake y trae `web_locator_provider_state`; `GET /council/demand` forma |
| `smoke_run_pipeline.py` | 372 | ≥ 410 → **402/402** → corrector **407/407** (literales del consejo == 1.12, eventos con reglas, paper no entregado ADMISIBLE, `tool_type`/`provider_detail`, agents `not-applicable (skipped-cap …)`) (la meta numérica NO se alcanzó — 402 < 410 — y se declara: era una estimación de CONTEO, no de cobertura; TODOS los checks de la columna «Qué MIDE» están presentes y verdes, ver «Integración W7») | contrato `'1.13'`; `WEB_DECLARED_EXCEPTIONS` EXACTAMENTE 3; cableado estático: 13 módulos reales (12 + brave), `_load_tool('web')[1] == 'locate'`, `len(SEARCH_DISPATCH) == 15`; corrida NO competente con directiva web + fakes → Traza `stage.search.plan (families[0]=='web')` → `stage.web.locate ×n` → `stage.search.source(web)` → … → `stage.search.round` → `stage.path_b`; `frozen.web_locator` `located` con `located[]`/`unresolved[]`/`cost`/`quota` y clases; paper web-localizado con `search_rec` de EPMC falso; `user_text` de pass2, del panel y del consejo r3 SIN ninguna URL del ledger ni `web_locator` (substring); `deterministic_checks.web_locator checked` ok; cita fabricada a URL → pass2 inadmisible `web_text_not_cited`; `answer.gap_flags` con los 2 strings de conteo y SIN URLs; `thread_context` de un hijo NO transporta URLs; `epistemic_summary.web_*`; `agents_invoked` fila `invoked`; `token_usage.web_locator.usd_projected == n×0.005`, `estimated_cost_usd` == tokens×precio, `estimated_cost_usd_total_projected` == suma, `by_stage_sum_matches_by_model True`; cuota: `WITT_WEB_MONTHLY_CAP=1` → 1ª granted, 2ª `skipped-cap`, tabla `n_queries 1`; **KILL-SWITCH M.1**: `off` → frozen == corrida encendida del MISMO fixture (sort_keys, keyset y valores) tras restar aditivas 1.13 e identidad, salvo EXACTAMENTE las 3 excepciones (diff listado), 0 `stage.web.*`, `families_excluded[web].reason` byte-idéntico, 0 `urlopen`, `mcp_cache` intacto; `brave` sin llave → literal `: BRAVE_API_KEY unset` y state `tool-unavailable`; competente → `not-requested (no search round)`; ronda sin directiva web → `not-requested (no web directive)`; anthropic con `urlopen` falso → `by_stage.search` medido y `cost.tokens`; assert GLOBAL sobre la BD del gate: ninguna URL de fixture web en `frozen_record_json` fuera de `web_locator` ni en `run_events` |
| `smoke_web_quota_db.py` (NUEVO, molde smoke_config_ledger_db) | — | ≥ 8 → **15/15** → corrector **17/17** (`n_requests_extra`; carrera UNIQUE en transacción propia) | `create_all` crea la tabla; `reserve` × cap → `granted` n veces y luego False con `n_after == cap`; 8 hilos concurrentes → exactamente `cap` granted (atómico); mes distinto no cuenta; `cap 0` → disabled; `record` suma `n_results`/`cost`; Postgres-compatible (SQL portable, sin `RETURNING`) |
| `smoke_usage_http.py` | 34 | ≥ 38 → **39/39** | `/usage.web_locator` suma corridas, `by_provider.brave`, `month_to_date` desde la tabla, `class`; sin corridas → 0 medido; `totals.estimated_cost_usd` NO incluye web (y `estimated_cost_usd_total_projected` agregado aparte) |
| `smoke_record_pdf.py` | 56 | ≥ 63 → **68/68** | (K.1) 53 llaves == frozen 1.13 real, cobertura `{missing [], extra []}`; born `'1.13'`; regex ANCLADA 53; PDF con located 2/unresolved 1 imprime `LOCALIZADOR WEB`, ids, regla, razón, URL completa, `PROYECCION` junto al USD y `MEDICION` junto a `n_queries`; 1.12 → `NO INSTRUMENTADO (contrato < 1.13)`; kill-switch → literal; `dc.web_locator` 4 predicados; determinismo; `urlopen` 0 |
| `smoke_models.py` | 96 | ≥ 101 → **102/102** | 17 filas `adr '0084'` en `ENV_TABLE` ⊆ compose ∩ README (defaults byte-iguales a `web_locator.ENV_SPECS`); `SNAPSHOT_FIELDS` += 2 FUERA de `panel_signature` (firma golden intacta); `WITT_WEB_LOCATOR_MODEL` validado; `BRAVE_API_KEY` NO en `ENV_TABLE` pero SÍ en compose/README con «never git» |
| `smoke_live_web.py --dry-run` (estático, NUEVO en `analysis/scripts/`) | — | exit 0 → **exit 0** (`{'mode': 'dry-run', 'db_imported': False, 'urlopen_calls': 0, 'ok': True}`; Brave `params_sent ['q','count','search_lang']`, `token_in_url False`; Anthropic `has_tool_choice False`, `tool_type 'web_search_20250305'`, `max_uses 1`, `allowed_domains_equal_list True`; resolutor sobre el fixture SINTÉTICO: 11 resultados, 9 located, 2 unresolved) | construye el cuerpo Brave (`url_sent` sin token, `params_sent` documentados) y el cuerpo Anthropic (sin `tool_choice`, `allowed_domains` == lista) con `urlopen` bloqueado == 0; único modo del CI |
| resto (41 smokes) | exit 0 | 45/45 → **45/45 exit 0** (`smoke_tools_c` 68/68 tras corregir un `mailto:` del fixture de W2; `mcp_cache` byte-idéntico — digest `a2909387007c882d` en worktree y árbol principal; `grep -c` del literal de exclusión == 1 en `search_harness.py` y 0 en runs/app/db/models) | sin regresión; `mcp_cache` byte-idéntico; `grep -c 'unsatisfiable-by-harness (tool-unavailable (ADR-0084))'` == 1 en `search_harness.py` (UNA verdad, los smokes la importan) |

## Gates EN VIVO (los corre Emmanuel; cada uno gasta lo que dice; resultados al ADR como MEDICIÓN con fecha)

- **LG0 · Alta de Brave (acción, sin código).** Crear la llave en api-dashboard.search.brave.com bajo el plan **«Search»** (US$5/1k,
  US$5 de crédito/mes, 50 qps; tarjeta sólo identidad) — **NO «Answers»** (US$4/1k + tokens: respuestas generadas por LLM, 2 qps —
  metería modelo en la recuperación); fijar `BRAVE_API_KEY` en Dokploy (jamás git/vault/memoria). ATESTIGUAR en el ADR: plan, fecha,
  si el crédito se renueva por mes calendario o por ciclo de facturación (`quota.rule`), y si el dashboard muestra tope mensual.
- **LG1 · Fixture REAL (1 GET, ≈ US$0.005 del crédito).** `python .tooluniverse/tools/brave_web_search.py "wt1a zebrafish pronephros
  podocyte" --record-fixture` → `fixtures/brave_web_search_wt1a-zebrafish-pronephros-podocyte_<YYYYMMDD>.json` con `live true`;
  verificar HTTP 200, `web.results[]` con `{url,title,description,age,page_age,meta_url}`, cabeceras `X-RateLimit-*` presentes
  (registrar valores en el ADR), `count` efectivo == 10; borrar el SINTÉTICO y correr `smoke_tools_d` (declara `provenance 'live'`).
  Si algún parámetro documentado devolviera 422, el cuerpo del error se registra (deriva de API).
- **LG2 · Localizador de punta a punta en dev (1 GET Brave + ≤ 6 GET EPMC).** `python analysis/scripts/smoke_live_web.py --provider
  brave --query "…" --materialize` → `located[]`/`unresolved[]` con reglas, `n_materialized`, idents 100 % en forma, `_resolve_one`
  real con `found True/False`; 0 campos `description` en la salida.
- **LG3 · Rate limit real.** 3 consultas seguidas con `WITT_WEB_MIN_INTERVAL_S=1.0` → cabeceras `X-RateLimit-*`, ningún 429; anotar;
  si el plan permite más, ajustar la env (no el código).
- **LG4 · Cuota.** En dev `WITT_WEB_MONTHLY_CAP=1` → 1ª consulta granted, 2ª fila `skipped-cap` con detail y CERO GETs (log del tool);
  la fila del mes UTC en `web_locator_usage`; restaurar 900.
- **LG5 · Alterno Anthropic (1 llamada, ≈ US$0.01 + tokens).** `WITT_WEB_LOCATOR=anthropic` en dev → si la org devuelve 400 «web search
  is not enabled» el estado `tool-unavailable (… Console)` se pinta y el alterno queda DECLARADO no operativo (el README no lo nombra
  alterno); si responde: grabar fixture REAL sin `encrypted_content` (`anthropic_web_search_<slug>_<fecha>.json`), medir
  `web_search_requests == 1`, `input.query` vs directiva, tokens, `n_text_blocks_discarded`, costo proyectado.
- **LG6 · Una corrida REAL en prod tras redeploy** con plan `evidence-run` cuya ronda 2 del consejo emita un `must source_family 'web'`
  (o en dev con `WITT_SEARCH_DEFAULT_FAMILIES=europepmc,pubmed,zfin,alliance_orthologs,zfin_expression,web` + `WITT_WEB_TEST_QUERY`):
  Traza con `stage.search.plan` (web primera), `stage.web.locate` por consulta, `stage.search.source(web)`; frozen `web_locator.located[]`
  con `fed_to`/`feed_state`/`fetched_found` reales, ≥ 1 paper `identifier_provenance 'web-located:…'` con texto de EPMC (`raw_paper_*`
  nuevo en `mcp_cache`), `deterministic_checks.web_locator checked`, `cost.usd_projected == n_billable × 0.005`, tabla mensual
  incrementada; PDF con «LOCALIZADOR WEB»; Hoja 2c / Traza / M8 pintan; `parity_check` 0 huecos nuevos.
- **LG7 · Kill-switch en prod.** `WITT_WEB_LOCATOR=off` con la misma pregunta → sin `stage.web.*`, `families_excluded[web].reason` ==
  literal de 7d9ce15, `frozen.web_locator.state 'kill-switch WITT_WEB_LOCATOR=off'`, `/council/demand` sigue contando `web`; reencender.
- **LG8 · Tasas tras 5 corridas con directiva web (descriptivo, n≈5).** `n_located/n_results`, `n_materialized/n_located`,
  `n_located_selected/n_located`, `unresolved[].reason` por host, `n_already_present/n_located` → decide ADR posterior (ranura en
  top-n · regla `doi-from-html-meta` · ampliar `WITT_WEB_ALLOWED_HOSTS` por env), y si `web_urls_not_in_answer` sube a gating.
- **LG9 · Ops.** Redeploy con las 17 env del compose + `BRAVE_API_KEY`; `mcp_cache` con escritura; el redeploy pendiente de
  ADR-0076…0083 ya en prod; fila `new-field` de `web.locator`/`web.provider` en `config_history` visible en M6.

## Proyección de costo y latencia (CLASE: PROYECCIÓN — precios públicos verificados 2026-09-16, supuestos DECLARADOS; ninguna consulta se ha enviado desde este código; LG1–LG8 sustituyen cada cifra)

- **Precios.** Brave plan Search: US$5.00 / 1 000 requests con US$5 de crédito mensual (brave.com/search/api) ⇒ US$0.005 por
  consulta cobrable y ≈ 1 000 consultas/mes sin gasto (el «Free 2 000/mes · 1 rps» del brief NO aparece hoy — declarado). Anthropic
  `web_search`: US$10 / 1 000 búsquedas + tokens; errores no facturados.
- **Supuestos.** (a) ≤ 3 consultas por ronda (`WITT_WEB_MAX_QUERIES`), ≤ 2 rondas ⇒ ≤ 6 por corrida; típico 1–3 (una directiva web
  por consejo); (b) sólo corridas NO competentes con un `must` web emiten directiva — supuesto 50 % de las corridas con ronda;
  (c) 40 corridas/mes con ronda (decenas, §6.4); (d) caché por día ≈ 0 en prod (efímera); (e) materialización ≤ 6 GET a Europe PMC
  por ronda (gratis).
- **Brave.** Por corrida US$0.005–0.03; mes típico 40 × 0.5 × 3 = 60 consultas ≈ US$0.30 (6 % del crédito); peor caso 240 ≈ US$1.20
  (24 %); `WITT_WEB_MONTHLY_CAP=900` impide rebasar el crédito aunque el volumen se multiplique ×3 (sobregiro imposible con el UPDATE
  condicional; las sondas CLI no cuentan: margen ~100).
- **Anthropic (sólo si se enciende).** US$0.010 por búsqueda + tokens del despachador (≈ 1.5k in por los resultados que la API mete
  como input + ≤ 100 out; con el modelo del rol `elicitation` — Opus 5 en g2 — ≈ US$0.01–0.03) ⇒ ≈ US$0.02–0.04 por consulta,
  ≈ US$0.06–0.12 por corrida, ≈ US$1.2–2.4/mes bajo (a)–(c): 4–8× Brave y CON modelo leyendo texto web — por eso es alterno.
- **Latencia añadida por ronda.** Brave 0.3–1.5 s por consulta (no medido) + 1 s de throttle entre consultas ⇒ ≤ 5 s con 3;
  materialización EPMC 1–3 s × ≤ 6 ⇒ ≤ 18 s peor caso dentro de `WITT_WEB_BUDGET_S=30` y de los 120 s de ronda; el `fetch_external`
  de un paper web-localizado SELECCIONADO ya cuenta en el camino de hoy. Turno completo: de 5–11 min a ≤ 5.5–11.5 min.
- **Costo INDUCIDO de modelo (indirecto, se mide en LG6/LG8).** Con llave, los `must` web gatean la competencia ⇒ más pass2
  (US$0.2–0.5 c/u según M8) y prompts con más evidencia. Es el costo de buscar lo que el consejo pide, no del localizador.
- **Sin llave (hoy):** US$0, 0 s, familia declarada `unsatisfiable-by-harness (tool-unavailable (ADR-0084))`.

## Decisiones abiertas para Emmanuel (mínimas; cada una con default — la obra IMPLEMENTA el default declarado *(W9: alineado al código)*: OE1 sin llave → `off` derivado y declarado · OE2 `WITT_WEB_MONTHLY_CAP=900` · OE3 alterno Anthropic CABLEADO pero NO operativo hasta LG5 (el README no lo nombra «alterno operativo») · OE4 `WITT_WEB_GENERIC_DOI_RULE=1` · OE5 conteo por clase en `answer.gap_flags`, URLs SÓLO en `frozen.web_locator`)

- **OE1 · Llave de Brave (acción, no diseño).** Dar de alta el plan **Search** (no Answers) y fijar `BRAVE_API_KEY` en Dokploy; grabar
  el fixture real (LG1). Default hasta entonces: provider derivado `off` — la obra se entrega con fixture SINTÉTICO declarado y el gate
  en vivo espera la llave. Nada bloquea el merge.
- **OE2 · Tope mensual `WITT_WEB_MONTHLY_CAP`.** Default **900** (≈ 90 % de las ~1 000 que cubre el crédito, margen para sondas CLI).
  Alternativas: 500 (más margen) · 0 (sin tope; el gasto se declara pero no se frena).
- **OE3 · Alterno Anthropic CABLEADO detrás de `WITT_WEB_LOCATOR=anthropic`** (default: sí, con fixture SINTÉTICO y LG5 de una llamada;
  el README lo nombra «alterno operativo» sólo tras LG5) vs dejarlo fuera de 1.13 y sólo declararlo. Recomendado: cableado — el modelo
  del despachador LEE texto web (propiedad declarada), por eso jamás es default ni failover.
- **OE4 · Regla genérica `doi-in-url-any-host` encendida por default** (recomendado: sí — la existencia la verifica Europe PMC en la
  MISMA ronda y un DOI falso jamás es candidato; tasa por host en LG8) vs `WITT_WEB_GENERIC_DOI_RULE=0` (sólo hosts de la tabla).
- **OE5 · «gap_flag con la URL».** El brief lo pide; el diseño pone la URL SÓLO en `frozen.web_locator.unresolved[]`/`gap_flags_typed[]`
  (Hoja, PDF) y en `answer.gap_flags` un string de CONTEO — porque `answer.gap_flags` viaja al sintetizador y al planner del turno
  siguiente (Context 3). Default recomendado: conteo. Si prefieres la URL literal en `answer.gap_flags`, el predicado
  `web_urls_not_in_answer` deberá exceptuar el snapshot y el riesgo de fuga queda declarado en el ADR.

## Plan de implementación (rebanadas DISJUNTAS por archivo → integrador → 3 revisores → corrector)

**Estado (W9, 2026-09-16):** W0–W8 aterrizados en el worktree `witt-organogenesis-0084` (rama `feat/adr-0084-web-localizador` apilada sobre
7d9ce15; 21 archivos M + 11 nuevos, ver «Integración W7»); W9 = este documento + `docs/decisions/README.md` + `rag_index/query_service/README.md`
+ la viñeta §6 de `CLAUDE.md`; R1–R3 y el corrector siguen. Orden: **W0 → W1 ∥ W2 → W3 → (W4 ∥ W5 ∥ W6 ∥ W8) → W7 integrador → W9 docs → R1
(doctrina) / R2 (corrección) / R3 (contrato y
paridad) → corrector.** W2 congela la INTERFAZ de `web_locator.py` (firmas de (B) y forma de la fila-query); W3 desarrolla contra ella;
W4–W6 contra fakes con esas formas. Todas arrancan sobre `contract-1.12-frozen`; ningún archivo tiene dos dueños. **W3 no se mergea
sin W6** (los cinco smokes que hoy fijan `web` estática cambian juntos).

- **W0 · golden del plan @ 7d9ce15** — dueño de `rag_index/query_service/fixtures/golden_plan_web_directive_7d9ce15.json`: ANTES de
  tocar código, en el árbol 7d9ce15, persistir `build_search_plan(q, ['wt1a'], 'wt1a pronephros glomerulus podocyte',
  directives=DIRECTIVES_C6)` (la de `smoke_search_harness.py:170-171` con `req-fff` web), `harness_state_for('web','web')` y
  `demand()` (forma con `n_requirements_unsatisfiable_by_family` sobre una BD vacía) — determinista, sin reloj. Smoke (W3): bajo off
  el plan es byte-idéntico al golden.
- **W1 · tool Brave** — dueño de `.tooluniverse/tools/brave_web_search.py` (NUEVO), `fixtures/brave_web_search_SYNTHETIC_wt1a_20260916.json`
  (NUEVO: forma documentada de `query{…}` + `web.results[]` ×10 con URLs PÚBLICAS reales de registros conocidos — doi.org, pubmed, pmc,
  europepmc, zfin ZDB-GENE, ensembl ENSDARG, uniprot, GEO GSE, un publisher con DOI en ruta, researchgate y wikipedia como no
  resolubles — con `description` presente en el fixture para medir el corte; `_fixture {live false, synthetic true, shape_source
  '<URL doc responses> 2026-09-16', note}`), `smoke_tools_d.py` (NUEVO). Interfaz (A).
- **W2 · resolutor + proveedor alterno** — dueño de `analysis/scripts/lib/web_locator.py` (NUEVO), `fixtures/anthropic_web_search_SYNTHETIC_wt1a_20260916.json`
  (NUEVO: `server_tool_use` + `web_search_tool_result` ×4 SIN `encrypted_content` + bloque de texto con `citations` + variante error
  + `usage.server_tool_use.web_search_requests 1`), `fixtures/web_locator_urls_golden.json` (NUEVO: ≥ 40 URLs → esperado),
  `smoke_web_locator.py` (NUEVO). Interfaz (B) congelada al cerrar.
- **W3 · harness** — dueño de `analysis/scripts/lib/search_harness.py` (fila `web`, `family_available`, `unsatisfiable_families`,
  `build_search_plan` exclusión dinámica + web primera + `WITT_WEB_TEST_QUERY`, `_inputs_for` sin cambio de forma, `_run_web_family`,
  rama `adapter 'web'` en `run_source`, `source_event_payload` aditivo) y `smoke_search_harness.py` (:185-191, :248-252 actualizados +
  ≥ 16 checks).
- **W4 · pipeline** — dueño de `analysis/scripts/lib/answer_pipeline.py` (admisión native-first, tie-break en `_select_top_n`,
  `block['web_locator']`, hooks `ctx`, `web_quota=` en `path_b_bundle`/`path_b`/`_path_b_harness`, `path_b_event_payload` aditivo,
  `n_results_by_source` con `web` en `ran_sources`) y `smoke_web_pipeline.py` (NUEVO).
- **W5 · gate** — dueño de `analysis/scripts/lib/verify_output.py` (`web_predicates`, `WEB_CHECK_STATES_*`, `WEB_PREDICATES`,
  `WEB_RULES`, `web_check_state_in_vocabulary`) y `smoke_gate_citations.py` (+≥ 12).
- **W6 · consejo y demanda** — dueño de `analysis/scripts/lib/council.py` (`harness_state_for` → `family_available`; recomputo en
  `directives_from`; `coverage_after_search += web_locator?`), `rag_index/query_service/council_index.py` (`DEMAND_FAMILIES` estático;
  `unsatisfiable_families()` en la llamada; `demand += web_locator_provider_state`), `smoke_council.py`, `smoke_council_index.py`,
  `smoke_council_http.py`.
- **W7 · runs · db · app · models (integrador)** — dueño de `rag_index/query_service/runs.py` (G), `db.py` (H), `app.py` (`/usage +=
  _WebLocatorUsageAccumulator` patrón :2282; `/council/demand` sin cambio de firma), `analysis/scripts/lib/models.py` (`ENV_TABLE` +=
  17 filas `adr '0084'`, `ENV_ADR_0084`, `SNAPSHOT_FIELDS += WEB_SNAPSHOT_FIELDS`), `docker-compose.query.yml` (17 env tras el bloque
  0083 + `BRAVE_API_KEY=${BRAVE_API_KEY:-}` «never git»), `smoke_run_pipeline.py` (:2444-2461 cableado; :5034 contrato; M.1 web),
  `smoke_usage_http.py`, `smoke_models.py`, `smoke_web_quota_db.py` (NUEVO), `analysis/scripts/smoke_live_web.py` (NUEVO: `--provider
  brave|anthropic --query … [--count N] [--materialize] [--dry-run]`). Cose las costuras: `ctx['on_web_locate']` → `db.add_event(
  'stage.web.locate')`, `web_quota` por firma, `_web_checks` en `_gate`, `frozen['web_locator']` junto a `'figures'` (:4678).
- **W8 · PDF** — dueño de `rag_index/query_service/record_pdf.py` (J) y `smoke_record_pdf.py` (52 → 53; born 1.13; +7).
- **W9 · docs** — dueño de `docs/decisions/0084-busqueda-libre-como-localizador.md`, `docs/decisions/README.md` (fila 0084),
  `rag_index/query_service/README.md` (tabla de env + contrato 1.13 + `/usage.web_locator` + `/council/demand`), `CLAUDE.md` §6 viñeta
  «la web es localizador, no fuente». Tag `contract-1.13-frozen` al merge.
- **R1 doctrina** (¿entra texto web por algún camino? `_PROMPT_*`, eventos, gap_flags, snapshot del hijo, PDF/Hoja rotulados) · **R2
  corrección** (ronda/admisión/selección, dedup en dos capas, cuota atómica, no-hang, ctx append-only, read-cache de `fetch_external`
  no envenenado) · **R3 contrato y paridad** (vocabularios cerrados, 3 excepciones, `SECCIONES` 53, `ENV_TABLE`, lista «tipar y
  pintar» completa, fixtures de la webapp) → **corrector** aplica y re-mide los 45 smokes.
- **Fixtures que la webapp necesitará (`tools/gen_fixtures.py` contra ESTE backend, fakes inyectados):** `web-localizador.json`
  (directiva web + 2 located materializados / 1 already-present / 1 unresolved / 1 not-found-in-europepmc, cita `located_via 'web'`,
  `deterministic_checks.web_locator checked`), `web-kill-switch.json` (`off` explícito: 3 excepciones), `web-sin-llave.json` (derivado
  off: `tool-unavailable (ADR-0084: BRAVE_API_KEY unset)`, consejo con el literal de exclusión), `web-cap-mensual.json` (`skipped-cap`
  con detail de cuota), `web-anthropic.json` (`by_stage.search` medido, `cost.tokens`), `eventos-web-locate.json` (`stage.web.locate` ×2
  + `stage.search.source(web)` + `stage.search.plan` con `families_order_rule`), `usage-web-locator.json` (`/usage.web_locator` con
  `month_to_date`), `demand-web-provider-state.json`; `MANIFIESTO.md` los declara sintéticos en la parte web. *(corrector — receta para
  `tools/gen_fixtures.py` de la webapp, OTRO workflow, medida contra este backend: hoy NO produce los fixtures web porque no inyecta `web` en
  `_TOOL_CACHE` (el tool Brave real cargado por ruta chocaría con `urlopen` bloqueado), no parchea la costura de EPMC ni `web_locator._post_json`, y
  no quita `BRAVE_API_KEY` (fuera de `ENV_TABLE`). Los 4 hooks que SÍ funcionan viven en `smoke_run_pipeline._run84`: `web_locator._load_brave_tool()[0]
  ._get = <fake>`, `fetch_paper.search_europepmc_ledger = <spy por ident con search_harness.epmc_ident_of_query, delegando las consultas libres al
  fake nativo>`, `fetch_paper.fetch_external = <fake>`, `web_locator._post_json = lambda …: (200, fixture, json)`, con env por corrida
  `{WITT_WEB_LOCATOR 'brave', BRAVE_API_KEY '<literal fake>', WITT_WEB_MIN_INTERVAL_S '0', WITT_MCP_CACHE_DIR tmp, WITT_PATH_B_N_PAPERS '10'}` y el
  stub del sintetizador citando el PMID web-localizado para `located_via 'web'`; `eventos-web-locate.json` SÍ lleva `families_order_rule` en
  `stage.search.plan` tras el corrector)*.

## Qué NO se hace y por qué NO es deuda

DuckDuckGo html/lite (captcha desde esta IP + ToS sin automatización — MEDIDO §6.4) · SearXNG autohospedado (frágil; una fuente más
que mantener sin dueño) · scraping de HTML o lectura de `<meta name="citation_doi">` para hallar el DOI (texto web al proceso, ToS,
presupuesto; alternativa `doi-from-html-meta` con criterio de disparo MEDIDO en LG8 — ADR propio) · `description`/`extra_snippets`/
`title` de Brave como texto, statement o evidencia (doctrina; `title_web` ≤ 120 vive SÓLO en `unresolved[]` del ledger, rotulado) ·
`result_filter`/`text_decorations`/`spellcheck`/`summary` de Brave (no documentados hoy; `summarizer` = texto generado) · plan
«Answers» de Brave (LLM en la recuperación) · `web_search_20260209/20260318` con dynamic filtering (código+modelo leyendo resultados) y
`web_fetch` de Anthropic (texto web al contexto del modelo) · auto-failover Brave → Anthropic (el gasto de modelo nunca se dispara solo)
· deep-research agéntica del paquete Tool Universe (ADR-0062; el sidecar es ADR-0085 con disparador MEDIDO por `/council/demand`, que
este ADR conserva) · reordenar el plan SIN web (byte-identidad) · ranura reservada para web en el top-n (se MIDE primero, LG8) ·
alimentar símbolos o GSE desde la web (la web no elige las ENTIDADES de la corrida; una directiva `geo` es del consejo) · materializar
en la ronda con `fetch_external` (envenenaría el read-cache abstract-only del paper seleccionado — Context 4) · rol nuevo en
`PIPELINE_ROLES` (movería `panel_signature`) · literal nuevo en `SOURCE_STATES` (`skipped-cap` + detail bastan; tres sedes de la webapp
intactas) · ruta HTTP nueva (`/usage` y `/council/demand` bastan) · URLs en `answer.gap_flags`, en eventos o en el prompt (canal de fuga
al modelo del turno siguiente) · borrar o mutar las cachés del precedente 2026-05-14 (se declaran no admisibles y se mide que nadie las lee) ·
*(corrector)* elegir por env un tipo de server-tool fuera de `web_locator.ANTHROPIC_TOOL_TYPES` (la única grieta que dejaba la prohibición de
`web_search_20260209/20260318` era el env libre) · mostrar al sintetizador el abstract de EPMC de un paper web-localizado que `fetch_external` no
entregó (D.3: texto RETENIDO, no por ser web sino porque E.3 exige `fetched.found True`) · materializar dos veces el mismo paper por dos formas de
URL (dedup por paper en la familia) · atar un registro de EPMC que no traiga el identificador localizado (record mismatch, Context 4).

## Contradicciones entre diseños/jueces y cómo se resolvieron (síntesis)

| Tema | A | B | C | Jueces | DECISIÓN |
|---|---|---|---|---|---|
| Encadenado a `unpaywall`/`monarch` | next-round vía `families_with_new_inputs` | igual, riesgo declarado | web PRIMERA | ambos: A es FALSO (`should_run_next_round` n==0) | **web primera EN LA RONDA** + admisión native-first + tie-break de selección (D) |
| Ítems del bundle desde la web | `source 'web'`, ids-only, refill de `search_rec` en `_paper_item` | `source 'web'`, `title None` | `source 'web'` | juez 2: verificar existencia antes de contar «located» | **0 ítems `source 'web'` (gate del brief)**: candidatos MATERIALIZADOS por EPMC en la ronda (`source 'europepmc'`, `source_family 'web'`, `web-located:<rule>`) |
| URLs en `answer.gap_flags` | conteo | una por URL (≤ 10) | conteo por clase | unánime: A/C (fuga al hijo) | **conteo por clase**; URLs en `frozen.web_locator` |
| Excepciones del kill-switch | 3, literal byte-idéntico | 3 | 4 + literal nuevo | unánime: A/B | **3 EXACTAS**, literal de 7d9ce15 |
| USD en `estimated_cost_usd` | aparte | aparte | suma | juez 1: sumar (ADR-0061); juez 2: aparte (`cost_class`) | **`estimated_cost_usd` intacto + `estimated_cost_usd_total_projected` con clase** |
| Query cuando `web` entra por env | `_free_query` | `None` salvo `WITT_WEB_TEST_QUERY` | `_free_query` | A/C + injerto B | **`WITT_WEB_TEST_QUERY` si está, si no `pass1_query_en`; jamás la pregunta cruda** |
| Estado de cuota | `skipped-cap` + detail | `skipped-monthly-cap` | `quota-exhausted` | ambos: A (cero cambio en la webapp) | **`skipped-cap` + detail** |
| Raw de Brave en disco | podado | íntegro | íntegro | juez 1: íntegro; juez 2: cualquiera declarado | **íntegro (§7.9); corte en la SALIDA medido por smoke** |
| Modelo del alterno | rol `elicitation` | rol nuevo en `PIPELINE_ROLES` | env con default `elicitation` | ambos: A/C (`panel_signature`) | **env `WITT_WEB_LOCATOR_MODEL` → default `elicitation`; sin rol nuevo** |
| Cita a paper web no materializado | escalera | informativo | gating | ambos: C | **gating `web_located_cited_requires_fetch`** |
| Evento nuevo | `stage.web.locate` | igual | ninguno | juez 1: A/B | **`stage.web.locate` por consulta** |
| `/council/demand` con llave | dinámico (web desaparece) | conserva llave en 0 | cuenta histórico | juez 2: C | **`DEMAND_FAMILIES` estático + `unsatisfiable_families` dinámica + `web_locator_provider_state`** |
| Parámetros Brave | `result_filter`, `text_decorations`, `spellcheck`, q≤400/50 | sólo documentados | q 400/50 del README del MCP | ambos: B | **sólo documentados; tope de `q` NUESTRO** |
| Golden del kill-switch | frozen 1.12 grabado en 7d9ce15 | diff on/off | diff on/off | juez 1: W0 | **diff M.1 on/off (gate) + golden LIGERO del plan @ 7d9ce15 (W0)** |
| Predicado URL | `^https?://` | ídem | ídem | juez 2: rompe `https://doi.org/<doi>` | **carve-out doi.org; ofende sólo lo que no resuelve o casa con el ledger web** |
| Texto de EPMC de un web-localizado no entregado por `fetch_external` *(corrector)* | — | — | — | R1/R2/R3: E.3 lo clasifica como texto web y tumba TODA la respuesta | **W4 retiene el texto** (`text_withheld_reason`), E.3 intacto, E.2 gatea la cita |
| Mismo paper en 3 URLs *(corrector)* | — | — | — | R2: 3 GETs, 3 candidatos, ledger duplicado de sí mismo | **dedup por PAPER en la familia** (`same_paper`, sin 2ª GET), `_web_mark_pool_duplicate` por fila de origen |
| Kill-switch con `web` nombrada en la env *(corrector)* | — | — | — | R1/R2: reorden + fila rica fuera de las 3 excepciones | **reorden/`families_order_rule`/`entered_by`/`WITT_WEB_TEST_QUERY` sólo con localizador disponible; fila MÍNIMA de 7d9ce15** |
| Literales del consejo bajo off *(corrector)* | — | — | — | R1: `directives_rule`/`after_search.rule` cambiados en TODA corrida | **1.12 byte a byte; ampliación web en `availability_rule` / `web_locator_rule` sólo con datos web; `WEB_ADDITIVE_KEYS_WITH_WEB_DATA`** |
| Tipo de server-tool por env *(corrector)* | — | — | — | R1: cualquier literal pasaba (20260209/20260318 prohibidos) | **vocabulario cerrado `ANTHROPIC_TOOL_TYPES`; `cost.provider_detail` y `queries[].tool_type/provider_property` declaran** |
| `epistemic_summary.web_*` bajo off *(corrector)* | — | — | — | R1: 3 llaves siempre | **se conservan** (columna aparte del frozen; patrón 0083 `figures_state`) — RECHAZADO quitarlas |
| `gen_fixtures.py` de la webapp *(corrector)* | — | — | — | R3: no produce los 8 fixtures web | **RECHAZADO tocarlo** (otro workflow); receta de 4 hooks documentada en «Fixtures» |

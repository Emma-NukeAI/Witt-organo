# ADR-0082 — El consejo de criterio ejecutable: 17 fichas verbatim como código, la ronda 1 es un JOB del plan que un humano aprueba antes de gastar, la ronda 2 mide cobertura ANTES de la compuerta y sus directivas mueven la búsqueda, la agregación es código byte a byte, y el consejo jamás escribe la respuesta

- **Status:** Proposed — 2026-09-15 (llevado al repo por C8 desde el borrador del sintetizador; pasa a Accepted cuando Emmanuel
  apruebe E1–E6; los conteos de la tabla NO-SPEND son los MEDIDOS por C9 al integrar, 2026-09-15/16). Origen: plan v3 del brief *Consejo de agentes* aprobado por
  Emmanuel el 2026-09-14 (§3 R1/R2/R7/R10, §4 etapas A–I, §5 membresía y fichas, §10 ACOTAR, §12 "dos riesgos operativos que
  van al ADR-0082 como requisito", tabla ADR-0082, §14 decisiones de Emmanuel) y el requisito que más le importa: *"no estamos
  usando a los 30 agentes… es indispensable que se usen"*, *"aunque genere más costo, una pregunta debería de invocar a todos los
  agentes… en el criterio"*. Obra sobre `feat/adr-0081-modelos-g2` @ `9d90c01` (tag `contract-1.10-frozen`; ADR-0078/0079/0080/0081
  commiteados) con paridad en `witt-webapp` (OTRO workflow; leída @ `3236aca`, no se toca). Síntesis de tres diseños
  (doctrina-y-fidelidad · Emmanuel-y-la-webapp · operación-costo-latencia) y dos juicios: parte del ganador (doctrina-y-fidelidad,
  34/40 y 35/40) e injerta lo que los jueces pidieron; donde los diseños o los jueces divergen, la decisión y su porqué van
  marcados *(síntesis)*. Estilo de cita: **ruta:función** con los números de línea del árbol @ `9d90c01`, verificados hoy (el
  nombre de la función es lo estable; la webapp se cita @ `3236aca`).
- **Decisiones YA tomadas por Emmanuel (no se relitigan aquí):** opción (b) consejo en el CRITERIO — no un supervisor que elige
  nicho · membresía de 17 por TABLA (5 cómputo/sim incl. `causal-pruner` que SOLO emite requisitos con gate humano · 7 lab/lectura
  · 3 conocimiento · `cross-field-bridge-agent` exploratorio · `regulatory-ethics-advisor` sólo banderas) + 8 operativos
  `not-applicable` por categoría + 9 sustrato/cubiertos con su estado real · modo **full-council** por bandera para MEDIR que los 8
  operativos no aportan · el consejo emite criterios y cobertura, JAMÁS veredictos, respuestas, rankings ni despacho · agregación
  DETERMINISTA por código (el `accumulator` lo reemplaza código) · ronda 1 = JOB asíncrono al declarar el plan; el humano aprueba
  el ledger (keep / discard con razón / "yo lo aporto" atestiguado) + "qué sabes ahora" ANTES de correr · ronda 2 de cobertura
  sobre bundle + pass1 ANTES de la compuerta de competencia; sus directivas alimentan la búsqueda dirigida (familias
  `directive-only` entran por directiva) · pass1 sigue solo-DI · `council_uncovered_must` pasa a componente GATEANTE (0 must sin
  cubrir) con kill-switch · modelo del consejo = `claude-opus-5` vía la tabla g2 (rol nuevo `council`, env `WITT_MODEL_COUNCIL`) ·
  topes duros (rondas de búsqueda ≤ 2, presupuesto por ronda, timeout por miembro) · `agents_invoked` deriva `council:n/N` con
  `status 'invoked'` · el costo no es impedimento pero toda cifra lleva clase (`token_usage.by_stage` gana `council_r1/r2/r3`) ·
  todo smoke offline con fakes · contrato aditivo **1.11**.
- **Estado de E1–E6 en esta obra (C8, 2026-09-15 — DEFAULTS aplicados, nada decidido por el código):** E1 un `must`
  `unsatisfiable-by-harness` NO gatea (se cuenta en `must_unsatisfiable` y en `GET /council/demand`) · E2
  `WITT_COUNCIL_EFFORT=medium` (`models.COUNCIL_EFFORT_DEFAULT`) · E3 `WITT_COUNCIL_CACHE_TTL=5m` · E4 `POST /runs {plan_id}`
  responde 409 hasta Aprobar o Saltar (`runs.council_run_gate`) · E5 el sintetizador es CIEGO al consejo y `WITT_COUNCIL_FULL=0` ·
  E6 el texto atestiguado de `budget_approval` lleva el placeholder literal `<pendiente E6>` (ver la decisión abajo). Ninguna de las
  seis se relitiga aquí; los conteos "C9 mide" ya son los medidos (ver el bullet C9 abajo y la tabla NO-SPEND).
- **C9 (2026-09-15/16) — integración sobre el worktree `feat/adr-0082-consejo` (37/37 smokes en verde con la máscara, UNA
  `.db` por smoke; `urlopen` = 0 donde se mide; `mcp_cache` byte-idéntico sin `.log`; gate estático M.4 de literales de
  modelo en PASS; `smoke_live_council.py --dry-run --member domain-knowledge-curator --round r1` exit 0 sin red).** Costuras
  (M) cosidas, cada una en el archivo del dueño: (i) `app.py` importa `lib.council` y `council_index` en DIRECTO (sin
  try/except "hasta que aterrice"); el kill-switch, el `effort` (E2: `models.council_effort` — vacía = `medium`, `inherit`
  hereda; C6 hacía "definida vacía → hereda": alineado a UNA verdad), el presupuesto de ronda, el modelo del consejo y
  `WITT_COUNCIL_INDEX` se leen de `council.*` / `models.env_value` sin lector local; la superficie E.1 se mide por ESQUEMA
  REAL (`db.council_schema_state`, cacheada al quedar lista) en vez de inspeccionar firmas de `db.py` — el 503
  `council-db-unavailable {missing[]}` y el estado `'not-requested (council db unavailable)'` quedan como estados REALES de
  una BD sin migrar (LG8), no como ventana de rebanada; `create_plan(origin=, council_state=)`, `set_plan_ledger(…,
  council_state=)`, `plan_add_event`, `plans_council_usage`, `runs.new_run(council_json=)` se llaman en directo (sin
  `_dbf`/`_accepts_kw`/`inspect`). (ii) `runs.py`: `new_run` persiste `runs.council_json` sin inspección de firma
  (`persisted` = hubo copia); `start_council_workers` importa `council_jobs` en directo (perezoso, sin ciclo) y
  `stop_workers` también apaga `council_jobs`; `_max_tokens_for` resuelve el tope por `models.MAX_TOKENS_KEYS` (el rol
  `council` caía en `judge-anthropic` por accidente); `COUNCIL_USAGE_STAGE_STATES_EXACT` gana `'measured (partial: round
  cancelled)'` (el literal ya se emitía); **`frozen.models.roles.council`** = `stage.models.roles.council` (mismo snapshot;
  `models.provenance_block` gana `roles.council`, `None` declarado para llamadores sin él; viaja bajo `WITT_COUNCIL=0`:
  excepción DECLARADA (L.2 ii) — medido en `smoke_models` y `smoke_run_pipeline`). (iii) `db._claim_council_query` exige
  además `run_id IS NULL` (hueco de C6: un plan `queued` que ya respalda una corrida — posible bajo el kill-switch — no se
  reclama al reencender: sus 17 llamadas serían gasto huérfano). (iv) `council_jobs` importa `council_index` a nivel de
  módulo (sin ciclo); `council_index._plans_rows` lee por `db.plans_with_council` + `db.council_schema_state` (ya no por
  reflexión) y el literal pasa a `'not-available (plans.council_json column absent — DB not migrated to ADR-0082 E.1)'`.
  (v) `answer_pipeline._path_b_harness` copia `directive_requirement_ids` del candidato al paper: `coverage_after_search`
  atribuye también la literatura (antes `'not-attributable'`). (vi) `council.ENV_SPECS[WITT_COUNCIL_R2_EVIDENCE_CHARS].minimum`
  1000 → 1 (== `models.ENV_TABLE`, la verdad efectiva). (vii) `catalog_cards.py` sin literal de modelo en el comentario del
  mínimo cacheable. Smokes: retirados los FAKES en memoria de la ventana "C4/C5 pendiente" (`smoke_council_http`
  `_instalar_fake_c4`, `smoke_usage_http` `db.plans_council_usage` → filas REALES de `plans`, `smoke_runs_list_http`
  → check directo, `smoke_council_index` → sin `ALTER` simulado y sección 0 con `plans_state 'empty'` + simulación de BD sin
  migrar) y los ids de modelo de los fakes se leen de la tabla (`models.resolve_role('council')` / `GENERATIONS`);
  `smoke_zfin_tool` exige el golden gitignored `rag_index/curation/quarantine/zfin_sweep_20260822T232036Z/raw/wt1a.json`
  (copiado del árbol principal al worktree, sólo lectura — dependencia ambiental preexistente, no del ADR). Paridad en
  LECTURA (`tools/parity_check.py` de la webapp apuntado al worktree, corrido desde `witt-webapp` sin tocarla): 14 huecos
  SIN declarar, todos esperados y del lado de la webapp — 8 rutas `/plans/*` · `/council/*` SIN RANURA, `[registro]
  council` CONGELA SIN TIPO, 5 tipos `council.state` · `stage.council.{ledger,round,coverage,directives}` SIN CASO EN TRAZA
  (`stage.council.member` / `progress` se emiten vía el `on_event` de `council.run_round` y el gate estático no los ve —
  la webapp debe tipar los 6 + `council.state`); `[pdf] council` NO aparece (`record_pdf.py` lo lee); `token_usage` y
  `deterministic_checks` OK en Hoja. Conteos de la columna "Hoy" re-medidos por las rebanadas @ `9d90c01` donde la tabla
  difería: `smoke_run_pipeline` 272 (no 275), `smoke_search_harness` 47 (no 51), `smoke_models` 74 (no 82).
- **Corrector (2026-09-16) — hallazgos de los tres revisores (doctrina · corrección · contrato) verificados uno a uno contra el
  código y APLICADOS; cada cambio de decisión o de forma va marcado *(corrector)* en su lugar. Alta:** (1) E5/§7 en el turno N+1
  — la prosa del consejo del padre (`thread_context.council_summary`: `gap` escrito por los miembros, `flags[].statement`,
  `coverage_final`, `decision`) llegaba al SINTETIZADOR dentro de `thread_context`; ahora `execute_run` le entrega el snapshot SIN
  esa llave y lo declara (`frozen.thread.context_delivery.council_summary`), el planner y la ronda 1 del turno N+1 SÍ la reciben
  (G.9); (2) el cuórum de r2/r3 se calculaba sobre los 17 aunque los miembros sin requisito kept quedan `not-invoked` y no pueden
  votar → con ≤ 10 dueños la ronda era `incomplete` POR CONSTRUCCIÓN y la compuerta declaraba no competente sin medir nada; el
  denominador pasa a los ELEGIBLES (`quorum {n_eligible, required, required_full_membership, …}`, C.3/C.5, componente `incomplete
  (k/n_eligible < quorum)`); (3) `stage.council.ledger.payload.state` congelaba el centinela interno `r2-pending` (fuera del
  vocabulario): ahora lleva el estado de r1 + `r2_pending` (J). **Media:** dedup del doble clic re-consultado DESPUÉS del planner
  (`reused_after_planner`); cierre CONDICIONAL del job r1 (`update_plan_council(expected_state='running')` + evento
  `council.state.conflict`, patrón ADR-0078); `'measured (partial: round cancelled)'` y los estados del componente cg-4 viajan en
  `council.vocabulary` (`usage_stage_states`, `competence_component_states` — `runs.council_vocabulary_full()` es la ÚNICA función
  para `frozen.council.vocabulary` y `GET /council/membership`); la lista "tipar y pintar" gana TODOS los literales HTTP reales por
  ruta; sin copia del consejo `frozen.council.n_members` es `null` (UNA verdad con `epistemic_summary.council_n_members`).
  **Baja:** `attestation_identifier_leak{,_state,_rule}` declarado en L.2(i) y medido contra el keyset 1.10; la anulación de un voto
  `covered|partial` sin `evidence_ids` escrita en C.5 (decisión (a)/(b) pendiente de Emmanuel, ver abajo); socket del caller
  dimensionado a los intentos (`socket_timeout_s`; antes el reintento por timeout era siempre una llamada fantasma) y
  `abandoned_cost_upper × attempts_possible`; `cancel_check` sólo cancela con la excepción DECLARADA (`cancel_exc`;
  `cancel_check_errors[]` medidos); `mark_plan_used` comprobado (409 `plan_already_used {cancelled_run_id}`); un borrador tras una
  aprobación limpia `approved_by/at`; INSERTs tolerantes a una BD sin migrar (`'not-requested (council db unavailable)'` alcanzable);
  `attempt` en ambas fases de `stage.council.member`; `decided_by: string | null`; `_worker_a_mano` del smoke HTTP con las formas
  REALES + el job REAL medido (`plan-eventos-consejo.json` nace de `execute_round1`); glosas de los literales `'empty-until-ADR-0082'`
  / `'not-available (ADR-0082)'`; receta completa de `gen_fixtures` en (11). **Rechazados (con evidencia):** ninguno — los 22
  hallazgos se sostuvieron contra el código; el único que NO se cierra en código es la anulación por voto sin id (F3): es una
  DECISIÓN de Emmanuel, aquí se aplica el default (a) y se deja escrita. Smokes re-medidos (máscara, una `.db` por smoke):
  `smoke_council` 70/70 (+6) · `smoke_competence` 39/39 (+1) · `smoke_council_jobs_db` 59/59 (+2) · `smoke_council_http` 74/74
  (+5) · `smoke_run_pipeline` 302/302 (+5) · resto sin cambio (tabla NO-SPEND); `smoke_live_council.py --dry-run` exit 0.
  **Decisión pendiente de Emmanuel (antes de `contract-1.11-frozen`):** conservar la anulación de votos `covered|partial` SIN
  `evidence_ids` (default aplicado, coherente con §7 "nada se afirma sin id", contada en `n_annulled_votes`) o retirarla de
  `council.judge_coverage` y de los dos checks de `smoke_council` que la miden.
- **C8 (2026-09-15) — alineación al código ENTREGADO por C1–C7 (cada ajuste va marcado *(C8: alineado al código)* en su lugar;
  la FORMA acordada no cambia, cambian firmas y literales que el borrador anticipó):** (a) la caché: con `WITT_COUNCIL_CACHE_TTL=1h`
  el bloque A también va `1h` — la regla de la API que este ADR cita ("una entrada de 1 h antes que las de 5 min") lo exige y el
  borrador la contradecía ("el A siempre 5m"); (b) `WITT_COUNCIL_EFFORT`: VACÍA es `medium`; la herencia de `WITT_ANTHROPIC_EFFORT`
  se pide con el literal `inherit`; (c) `plans.council_state` es `VARCHAR(96)` (el literal más largo de E.3 mide 74 chars);
  `plan_events` es espejo EXACTO de `run_events` (incluye `degraded`); (d) el reaper de planes es un hilo PROPIO `council-reaper`
  (`council_jobs.reaper_loop`) con el MISMO `WITT_REAP_STALE_S`, no una segunda tabla dentro de `run-reaper`; (e) firmas reales:
  `run_round(members, round_, ctx, caller, budget_s, on_event, cancel_check, cfg, env, clock, payload_for, phase)`,
  `aggregate_r1(round_result, members, cfg, resolver)` (alias `aggregate_requirements`), `judge_coverage(round_result, ledger,
  evidence_ids, phase, round_)` (alias `aggregate_coverage`), `directives_from(coverage, ledger, members_order)` (alias
  `compile_directives`), `coverage_after_search(coverage_pre, search_ledger, directives=None)`, `build_system(card_or_name, env)`,
  `validate_tool_input(agent, round, raw, cfg)`, `enabled(env) -> (bool, source)`; (f) vocabularios: `AGGREGATE_STATES_EXACT` +
  `AGGREGATE_STATE_PREFIXES`, `DIRECTIVES_STATES` (del conjunto) además de `DIRECTIVE_STATES` (de cada directiva),
  `MEMBER_ERROR_KINDS_EXTRA`, `PRIOR_STATES` gana `no-match`, `council_vocabulary()` devuelve 25 llaves; (g) el modo `requirements`
  lo tienen 14 miembros (17 − 3 modos especiales), no 13; (h) la llave de `agents_invoked` es `evidence` (contrato §11), no
  `evidence_generated`; el `scorer` de respaldo del índice es TF-IDF coseno en stdlib (`stdlib-tfidf-fallback`), no token-overlap;
  (i) `frozen.council`, `GET /runs/plan.council`, `GET /plans/{id}`, `GET /council/*` son SUPERCONJUNTOS declarados de las formas del
  borrador (la forma exacta la fijan los fixtures 1.11 y `smoke_run_pipeline.py`); (j) `smoke_live_council.py --dry-run` exit 0
  MEDIDO el 2026-09-15 (3 filas: 20 cuerpos de `count_tokens` construidos + `literature-monitor` r1/r2 con cuerpo REAL capturado:
  `system` 2 bloques con `cache_control`, `tools` ×3 byte-idénticos, `tool_choice` forzado, `max_tokens 4000`,
  `output_config.effort 'medium'`; `urlopen` reales 0; `db` no importado).
- **Relates:** ADR-0043 (tres estados) · ADR-0047 d.3 (gasto medido, nunca capado) · ADR-0049 (auditoría en el 100%) · ADR-0051/
  0065 (conf1 mide la suficiencia de la DI: pass1 sigue solo-DI) · ADR-0053 (precedente ≠ evidencia — aquí: atestiguado ≠
  evidencia) · ADR-0057 (`recover_trapped_params`) · ADR-0061/0066 (el plan declarado, never-stopper; aquí el plan gana el ledger) ·
  ADR-0067 (revisión acotada: una ronda incompleta NO dispara revisión) · ADR-0074 (registro inmutable; el `.md` del catálogo se
  versiona por sha, la historia no se reescribe) · ADR-0076 (`run_no`: la ronda 1 NO consume corridas) · ADR-0077 (comentarios
  → `council_index`) · ADR-0078 (reaper, `claimed_by`, lección de tipos-fecha por dialecto) · ADR-0079 (`origin`; `thread_context`
  gana `council_summary`; el mismo `_gate` con predicado nuevo) · **ADR-0080** (cierra los TRES huecos que dejó: `competence.
  council_uncovered_must 'not-available (ADR-0082)'`, `build_search_plan(directives=None)` + `directives_state
  'empty-until-ADR-0082'`, `citations[].pertinent 'not-available (ADR-0082)'`) · **ADR-0081** ((K) `panel_source.council_hook` se
  conserva `not-available` — las lentes por nicho NO entran aquí; (M.2) patrón de excepciones declaradas al kill-switch; tabla g2
  gana el rol `council`) · ADR-0083 (figuras: `evidence_kind 'figure'` queda `unsatisfiable-by-harness` contado) · ADR-0084/0085
  (`web`/`tooluniverse`: `GET /council/demand` es su criterio MEDIDO de disparo) · ADR-0087 (calibración: leerá `frozen.council`,
  `catalog_sha`, `membership_version`).
- **Affects:** `analysis/scripts/lib/catalog_cards.py` (NUEVO) · `agent_matrix.py` (v1.3) · `analysis/scripts/lib/council.py`
  (NUEVO, stdlib puro) · `composite_auditor.py` (`_anthropic_tool_call`: `tools=`, `system` lista, semáforo, `Retry-After`) ·
  `models.py` (rol `council`, `CACHE_MULTIPLIERS`, `ENV_TABLE`, `SNAPSHOT_FIELDS`) · `search_harness.py` (`build_search_plan
  (directives=)` con semántica de UNIÓN) · `verify_output.py` (`support_state_for(council_pertinence=)`) ·
  `rag_index/query_service/competence.py` (`cg-4`) · `runs.py` (contrato **1.11**, `PLAN_VERSION '4'`) · `db.py` (columnas
  aditivas en `plans` y `runs`; tabla NUEVA `plan_events`) · `council_jobs.py` (NUEVO) · `council_index.py` (NUEVO) · `app.py`
  (8 rutas nuevas bajo `/plans/*` y `/council/*`; `POST /runs/plan` encola; `POST /runs` exige ledger aprobado o saltado) ·
  `record_pdf.py` (sección "CONSEJO DE CRITERIO" — nace con el bloque) · `docker-compose.query.yml` · `README.md` ·
  `skills/custom/organogenesis-agent-architect/references/agent-invocation-matrix.md` (v1.3) · smokes (7 NUEVOS + 8 tocados) ·
  `analysis/scripts/smoke_live_council.py` (NUEVO, EN VIVO, lo corre Emmanuel) · witt-webapp (tipar y pintar; ver
  *Consequences*). **Cero mutación de la DATA INAMOVIBLE, del registro congelado existente, de `mcp_cache` desde los gates; cero
  gasto de modelo en la obra (lo único que gasta es un script de Emmanuel).**

## Context

1. **Hoy dos filas de 29 corren como código; el consejo es prosa.** `agent_matrix.AGENTS` tiene 29 filas (agent_matrix.py:26-226)
   y `componentized` es `None` en todas salvo `composite-auditor` (:44) e `identifier-verification-gate` (:97); el docstring lo
   dice literal: *"exactly TWO matrix rows run as code"* (:11-13). `runs.build_plan` marca a todo agente aplicable sin componente
   `will_run 'skipped-ad-hoc'` (runs.py:608-619) y `runs._agents_invoked` lo congela así (runs.py:699-771): el planner juzga
   17 aplicables y el registro declara, corrida tras corrida, que ninguno corrió. La matriz no tiene `category`; el catálogo tiene
   **31 fichas** (`### ` en agent-catalog.md:41…638, seis `## Category` en :39/:154/:234/:296/:405/:478) y la matriz 29 filas:
   faltan `bwh-coordinator`, `fitness-curator`, `reagent-procurement`, `retrospector`, `squidiff-in-silico-gate`; tres filas
   (`html-report-emitter`, `identifier-verification-gate`, `type-c-viz-emitter`) no tienen ficha. El planner sólo ve nombre + gate +
   señal (`agent_matrix.digest`, :249-263): nadie parsea las fichas.
2. **Las fichas MEDIDAS hoy (no supuestas).** Las 31 llevan `**Purpose:**`, `**Owns:**`, `**Does NOT own:**`, `**Inputs:**`,
   `**Outputs:**` (31/31); `**Substrate evidence:**` ×10, `**Framework:**` ×2, `**Method:**` ×1, `**Upstream/Downstream:**` ×4. Los
   17 miembros suman **20 765 caracteres** (media 1 221; máx `squidiff-in-silico-gate` 3 029; mín `histology-reviewer` 454) ≈
   **5.2k tokens en TOTAL** a 4 chars/token (PROYECCIÓN; `count_tokens` la sustituye en LG1). El brief §12 asumía "3–5k tokens por
   ficha": estaba inflado ~10×. Consecuencia para la caché (ver (D)): lo que vale cachear es el PREFIJO COMPARTIDO (tools + bloque
   fijo + reglas §7), no la ficha. Tres headers llevan sufijo: `hypothesis-generator (NEW v1.1, PR-01)` (:368), `composite-auditor
   (NEW v2.2)` (:599), `retrospector (NEW v1.1, ADR-0009 — …)` (:638).
3. **`causal-pruner` es hard-rule con gate humano ANTES de cualquier uso.** CLAUDE.md §7 (:146): *"outputs always require a human
   gate before downstream use"*; su ficha (agent-catalog.md:61-84): *"Does NOT own … the final decision … (always human-gated)"*,
   *"All outputs are advisory and require human gate before downstream consumption"*. `agent_matrix` lo tiene `gate 'hard-rule'`
   con `pattern '… -> HUMAN GATE'` (:28-38). Un requisito de información que él emita es una SALIDA suya: no puede entrar a la
   cobertura ni a la búsqueda sin decisión humana explícita sobre ESE requisito (un "keep todo" por default lo usaría sin humano).
   `cross-field-bridge-agent` es Method 2 only / Test 5 exploratorio (§7 :147-148; ficha :566-585 "Each output explicitly tagged
   as preliminary/exploratory"). `regulatory-ethics-advisor` sólo produce banderas de cumplimiento (:329-343) y §7 (:149) manda gate
   humano directo para compliance/presupuesto.
4. **Los tres huecos que ADR-0080/0081 dejaron con nombre.** `competence.evaluate(... council_coverage=None)` guarda el insumo
   CRUDO sin interpretarlo: `comp_council = {value None, state 'not-available (ADR-0082)', gating False}` (competence.py:220-222);
   `COMPONENT_ORDER` ya lista `council_uncovered_must` (:58-59) y la doctrina del módulo dice *"un componente sin insumo es False con
   reason, nunca un True vacío"* (:26-27). `search_harness.build_search_plan(directives=None)` (search_harness.py:285-371) devuelve
   `directives_state 'empty-until-ADR-0082'` (:366) y `runs._build_search_plan` pasa `directives=None` (runs.py:2033-2034). **Pero
   la semántica actual con directivas es de REEMPLAZO, no de unión:** con `directives` y `families=None`, `requested=[]` y sólo
   entran las familias nombradas (`source 'directives'`, :315-320); la exclusión `directive-only` sólo aplica a `'default-families'`
   (:330-332). Una sola directiva del consejo apagaría `europepmc/pubmed/zfin/alliance_orthologs/zfin_expression` — contra ADR-0080
   Context 4 "cinco corren en toda ronda". Y `verify_output.support_state_for` escribe `pertinent 'not-available (ADR-0082)'`
   en cada cita (verify_output.py:268, :502, :516): la escalera tiene el peldaño reservado.
5. **El plan es síncrono y ya es el objeto que el humano aprueba.** `app.create_plan` es `def` (hilo del threadpool de anyio):
   valida, llama `runs.build_plan` (una llamada de planner, 10–20 s hoy), `db.create_plan`, y responde (app.py:482-511). El brief
   §12 mide el riesgo: 17 llamadas de consejo dentro del request son 60–120 s contra el timeout del proxy Dokploy/Traefik que
   nadie ha consultado. La tabla `plans` (db.py:107-116) ya tiene `user_id`, `plan_json` y `run_id` sellado por `mark_plan_used`
   (:535-543, `WHERE run_id IS NULL` → un plan, una corrida); `POST /runs {plan_id}` copia `prow['plan_json']` a la corrida y sella
   (app.py:618-642). Reutilizar `runs` para la ronda 1 contaminaría TODOS sus lectores: consumiría `run_no` (ADR-0076), `turn_kind`
   es la POSICIÓN en la investigación con índice único `(thread_id, turn_no)` (db.py:63, :330-333), `run_events` tiene
   `ForeignKey('runs.run_id')` (:120) que Postgres exige, `claim_next_queued` es FIFO sobre `runs` (:626-648) — un plan esperaría
   detrás de corridas de 10 min — y `list_runs/threads_index/runs_usage/closed_runs/plan_history` leen `runs`.
6. **Operación en UN proceso.** `--workers 1` (ADR-0048); `start_workers(WITT_RUN_WORKERS=2)` lanza hilos `run-worker-N` + un
   `run-reaper` (runs.py:3158-3175, app.py:101). `REAP_STALE_S_DEFAULT = 900` se dimensionó previendo *"una ronda de consejo
   futura … puede pasar 5 min sin emitir evento"* (runs.py:3085-3091); la vista avisa a `HEARTBEAT_STALE_S 300` (app.py:442).
   `db.add_event` calcula `max(seq)+1` + INSERT + UPDATE `last_event_at` en UNA transacción (db.py:1190-1203): seis hilos de un
   pool escribiendo a la vez chocarían en la PK `(run_id, seq)` (Postgres) o darían `database is locked` (SQLite) — hoy ninguna
   corrida escribe eventos desde más de un hilo. `_anthropic_tool_call` reintenta UNA vez en 429/5xx con `_backoff(2*(attempt+1))`
   fijo y ciego al `Retry-After` (composite_auditor.py:505-512), reintenta UNA vez el contenido (`no-function-call`,
   `required-missing`, :539-557) y usa `urlopen` NO streaming (:503); no hay semáforo de proceso. 17 llamadas × 2 workers + 4
   jueces + 1 job de plan × 6 = hasta 22 peticiones concurrentes al proveedor sin control.
7. **Prompt caching, verificado contra la referencia (skill `claude-api`, `shared/prompt-caching.md`, cache 2026-06-24).** El
   prefijo se renderiza `tools → system → messages`; cambiar `tool_choice` CONSERVA las cachés de tools y system (tabla *Invalidation
   hierarchy*: sólo cambiar definiciones de tool o el modelo fuerza reconstrucción total); cambiar `thinking`/`effort` invalida
   messages y, según el modelo, también tools/system → *"pin thinking and effort settings per route"*. Mínimo cacheable en Opus 5 =
   **512 tokens** (`cache_creation_input_tokens: 0` en silencio si no llega). Escritura 1.25× (TTL 5 min) / 2× (1 h); lectura 0.1×;
   la vida se mide desde el START de la petición que escribe o lee. *Concurrent-request timing*: *"N parallel requests with identical
   prefixes all pay full price"* — mandar UNA, esperar su primer byte, y luego las N−1. Pre-warm con `max_tokens: 0` se RECHAZA con
   `tool_choice {type:'tool'}`. La API devuelve `usage.cache_creation_input_tokens` / `cache_read_input_tokens` (numéricos:
   sobreviven `_numeric_usage`, composite_auditor.py:437-452). Nada de esto está implementado: el caller arma `system` como string y
   `tools: [tool]` (:492-496). Entre la ronda 1 (job del plan) y la ronda 2 (corrida) está la LECTURA HUMANA del ledger: el hueco
   normal excede los 5 min → r2 vuelve a ESCRIBIR salvo TTL 1 h o campañas.
8. **Gasto por etapa y precedente ya tienen la forma que el consejo necesita.** `TOKEN_STAGES` (runs.py:1655) y `_usage_by_stage`
   (:1661-1733) reparten por etapa; `_token_usage` cotiza sólo `in/out` (:1736-1808; `_usage_in_out` :1648 ignora `cache_*`);
   `app.usage` agrega `by_stage` iterando `TOKEN_STAGES` (app.py:1238-1360). `precedent.py` ya da corpus por origen
   (`closed_runs_scoped` :87, `_corpus` :128-148), índice TF-IDF con fallback declarado (`_ensure_index` :155-172), `search` con
   `admissible_as_evidence False` (:175-200) y letras (`letter_label` :205-211; `serialize_disjoint`/`validate_disjoint`
   :220-256). `build_thread_context` arma el snapshot del padre en el servidor (runs.py:952-1024) y `_default_synthesizer` lo pasa
   como LLAVE HERMANA de `evidence` con cláusula anti-fuga (runs.py:1377-1402, :1426-1438); `parent_identifier_leak` es predicado
   DURO vía `extra_predicates` (runs.py:1083-1113; verify_output.admissible :219).
9. **Quién crea planes además de Emmanuel.** `smoke_run_pipeline` (:900-919) y `smoke_runs_thread_http` (:441-451) hacen
   `POST /runs/plan` con planner fake; `gen_fixtures.py` de la webapp corre con `WITT_RUN_ORIGIN=fixture` (gen_fixtures.py:32-34).
   `runs.run_origin()` deriva `production | dev-offline | <env>` del entorno del PROCESO (runs.py:869-889). Un job de ronda 1 que
   reclamara CUALQUIER plan `queued` con una llave real en el shell dispararía 17 llamadas de opus-5 por fixture.
10. **Lo que Emmanuel verá.** M3 `Preguntar.tsx` pinta la card del plan (`plan-card` :743, `plan-agentes` :797 — "sin componente —
    el rol corre ad-hoc", `plan-clarificaciones` :818, `plan-estimaciones` :866); `Traza.describir` (:818) tiene caso por tipo de
    evento (`stage.audit.judge` :1061 es el patrón de latido por miembro; `stage.search.plan` :1298); `Hoja.FilaComponente` ya aísla
    `esCouncil` y pinta "no disponible hasta ADR-0082" (:3758-3806); `types.CompetenceCouncilComponent` es `{value: null, state,
    gating: false, received?}` (:1534-1539); `PlanAgent.will_run` es un union de tres literales (:300); `AgentInvocation.status` es
    union abierto (:2760-2766); `gen_fixtures.py` asserta el contrato por igualdad (`CONTRATO = "1.10"` :161, assert :698) y quita
    del proceso las env de `models.ENV_TABLE` (:143-144).

## Decision

**(A) Fichas como código — `analysis/scripts/lib/catalog_cards.py` (NUEVO, stdlib puro).** `CATALOG_PATH` = hermano de
`agent_matrix.MATRIX_PATH` (`skills/custom/organogenesis-agent-architect/references/agent-catalog.md`). `parse(path) -> CARDS`
recorre el `.md` por líneas: un bloque empieza en `^### ` y termina en el siguiente `^### ` o `^## `; `category` = el `## Category N:`
vigente (seis: `compute-simulation`, `wet-lab-experiment`, `data-omics`, `knowledge-strategy`, `operations-reporting`,
`substrate-instrumentation`, con `category_raw` verbatim); `name` = el header sin el sufijo `\s*\((NEW|ADR)[^)]*\)\s*$`
(`hypothesis-generator`, `composite-auditor`, `retrospector`; `header_raw` se conserva); campos por etiqueta negrita —
`purpose, owns, does_not_own, inputs, outputs` (obligatorios en las 31: un faltante es error de parseo, no un default) y
`substrate_evidence, framework, method, upstream, downstream, draft_description` (opcionales: ausente = ausente, jamás `''`);
`text_verbatim` = los BYTES exactos del bloque (saltos de línea del archivo, sin normalizar); `sha = sha256(text_verbatim)`;
`CATALOG_SHA = sha256('\n'.join(f'{name}:{sha}' for name in sorted(CARDS)))`; `CARDS_COUNT` golden = **31**; `card(name)` → la
ficha o `None`. *(C8: alineado al código — `parse(path=None, text=None) -> dict` lanza `CatalogParseError(ValueError)` u `OSError`; el import jamás lanza:
`CARDS`, `CATALOG_SHA` (`None` si falló) y `CATALOG_STATE ∈ 'parsed' | 'errored (<Tipo>: <msg>)'` se declaran; `CATALOG_PATH_ABS`,
`cards_summary()`, `MODULE_VERSION 'catalog-cards-1'`; la ficha lleva además `header_suffix`, `category_raw`, `line_start/line_end`,
`offset_start/offset_end`, `chars`, `labels_raw[]`, `fields_present[]`, `fields_absent[]`)*. El parser no sabe de membresía: `agent_matrix` (B) decide quién se sienta; `catalog_cards` sólo dice qué dice cada
ficha y con qué sha. **Golden (smoke_catalog_cards):** 31 fichas; los 17 miembros ∈ `CARDS`; cada `sha` == `sha256` del substring
exacto del `.md`; `CATALOG_SHA` estable en dos parseos; copiar el `.md` a tmp y cambiar UN byte de `causal-pruner` → cambia SÓLO su
`sha` y `CATALOG_SHA` (ninguna otra); las tres filas sin ficha se declaran `card 'no-card-in-catalog'` en (B). **Deriva de
fichas:** `CATALOG_SHA` viaja en `plans.council_json`, en `frozen.council.catalog_sha` y en `GET /council/membership`;
`frozen.council.plan_catalog_matches_run` = `catalog_sha del plan == CATALOG_SHA al ejecutar` *(injerto de D3: misma disciplina que
`plan_question_matches_run`)*. Editar una ficha NO reescribe ningún registro (ADR-0074): la siguiente corrida lleva otro sha y la
Hoja lo dice.

**(B) Membresía por TABLA — `agent_matrix.py` v1.3.** `MATRIX_VERSION = 'v1.3'` (agent_matrix.py:21). Toda fila gana `category`
(las 29 + 5 NUEVAS en §3 `recommended`: `bwh-coordinator`, `reagent-procurement` (operations), `fitness-curator`,
`squidiff-in-silico-gate` (compute), `retrospector` (substrate; `note` 'agent-session only (ADR-0009)')) y `card ∈ 'present' |
'no-card-in-catalog'` (las tres sin ficha). **`COUNCIL_MEMBERSHIP = {'version': 'cm-1', 'members': {...}, 'not_applicable_by_category':
('operations-reporting',), 'substrate': {...}}`** con los 17 exactos del brief §5.1 y su `mode`: `requirements` (14 *(C8: alineado al código — 17 − 3 modos especiales; el borrador decía 13)*),
`requirements-human-gated` (`causal-pruner` → todo requisito suyo nace `hard_rule_gate True`), `flags-only`
(`regulatory-ethics-advisor` → tool `emit_flags`), `exploratory` (`cross-field-bridge-agent` → `priority 'must'` se DEGRADA a
`should` con `priority_downgraded_from`, §7 Test 5); `group ∈ compute | lab | knowledge | cross-field | flags`. Los 8 operativos
(`program-manager, budget-tracker, bwh-coordinator, reagent-procurement, ip-patent-watcher, case-capture-elicitor,
risk-register-agent, investor-relations-drafter`) son `not-applicable-by-category` y SÓLO entran con `WITT_COUNCIL_FULL=1` (N=25;
sus requisitos llevan `from_operative True` y se cuentan aparte — decisión §14 "para medir que no aportan"). Los 9 de sustrato con
su estado REAL declarado en `substrate`: `composite-auditor` e `identifier-verification-gate` `'invoked (component)'`;
`accumulator` `'replaced-by-code (council.aggregate_requirements)'`; `reasoning-exposer` `'absorbed (SYNTH_TOOL
framework_applied)'`; `calibration-tracker`/`evaluation-runner` `'tapón 4/5 (not in webapp run)'`;
`html-report-emitter`/`type-c-viz-emitter` `'derogated (ADR-0046)'`; `retrospector` `'agent-session only (ADR-0009)'`.
`componentized` de los 17 pasa de `None` a `('lib/council.py', 'council member r1-r2 (ADR-0082)')` → **19/34 filas ejecutables**
(antes 2/29). `council_members(env) -> [names]` (17 | 25 según `WITT_COUNCIL_FULL`, orden FIJO de la tabla: el orden es identidad
de la agregación) *(C8: alineado al código — `council_members(env=None, full=None)`: `full=` explícito gana (la corrida pasa la N congelada del
plan, F.4); además `council_full(env, full) -> (bool, source)`, `council_size`, `council_member(name)` (asiento, grupo, modo, tool,
gates) y `membership_view(env, full, cards)` — el cuerpo de `GET /council/membership`; `COUNCIL_MEMBERSHIP` lleva también `source`,
`groups`, `modes`, `operatives {8 → estado}`, `full_env`; constantes `COUNCIL_COMPONENT`, `CATEGORIES`, `CARD_STATES`, `GATES`,
`MEMBERS`, `OPERATIVES`, `SUBSTRATE`; `MEMBERSHIP_VERSION 'cm-1'`)*. **`digest()` CAMBIA** por construcción (itera `ENUM = sorted(AGENTS)`, :228/:253): el planner verá 34 nombres →
`PLAN_VERSION '3' → '4'` (runs.py:352) y el A/B (LG4) mide si sube `n_agents_applicable` *(síntesis: dos diseños prometían
`digest()` byte-igual — imposible con 5 filas nuevas; se declara en vez de fingirlo)*. `agent-invocation-matrix.md` → v1.3 (las 5
filas en §3 con gate `recommended` provisional y una nota "ADR-0082: consejo de criterio, membresía cm-1").

**(C) `analysis/scripts/lib/council.py` (NUEVO, stdlib puro: `json, hashlib, re, time, threading, concurrent.futures`).**
*(C.1 prompts)* `COUNCIL_FIXED_BLOCK` (inglés, sin fechas ni ids: *"You sit as `<agent>` on a COUNCIL OF CRITERIA for a zebrafish
pronephros research question. You do NOT answer the question, do NOT rank, do NOT audit, do NOT dispatch anything. Emit ONLY the
tool. Name evidence kinds and source families from the enums; never assert identifiers as facts (entities are checked by code);
prior observations and human attestations are PRIOR ART, never evidence."*) + `COUNCIL_RULES` = las reglas §7 aplicables, texto
literal de CLAUDE.md (:146-149, :153-158) → `RULES_SHA`; `build_system(card_or_name, env=None) -> list[block] | str` = `[{type:'text', text:
COUNCIL_FIXED_BLOCK + '\n\n' + COUNCIL_RULES, cache_control?}, {type:'text', text: card['text_verbatim'], cache_control?}]` — bloque A
IDÉNTICO para los 17 (el prefijo compartido que se lee 16×), bloque B la ficha VERBATIM (la persona lee lo mismo que el agente
obedeció); `cache_control {type:'ephemeral'[, ttl]}` en ambos con `WITT_COUNCIL_CACHE=1` (TTL del bloque B por
`WITT_COUNCIL_CACHE_TTL`; el A toma `1h` cuando el B es `1h` y `5m` en otro caso — la regla de la API que este ADR cita exige que una entrada de 1 h
vaya ANTES que las de 5 min, y el bloque A va antes que el B: un A en 5 min delante de un B en 1 h la violaría *(C8: alineado al código —
`catalog_cards.CACHE_TTL_RULE`; el borrador decía "el A siempre 5m")*); con `=0` el `system` es el
string concatenado (A/B medible). `system_sha` por miembro se congela. *(C8: alineado al código — `system_sha(system)`: string → sha256; lista → sha256 del JSON canónico; `cache_config(env) -> {enabled,
enabled_source, ttl_card, ttl_shared, ttl_source, ttl_rule, min_cacheable_tokens 512, min_cacheable_source}}`;
`SHARED_BLOCK_TEXT`/`SHARED_BLOCK_SHA` = bloque A; `COUNCIL_RULES_ITEMS` son 10 ítems literales de §7 (:146-149, :153-158); el texto
final de `COUNCIL_FIXED_BLOCK` vive en `catalog_cards` — la cita de arriba es el borrador; el final añade "Absence of evidence is
a finding, not a zero: say what is missing and how it would be verified")*. Lo volátil (pregunta, entidades, juicio del plan, prior
observations, ledger, evidencia, pass1, atestiguaciones) va SIEMPRE en el user message.
*(C.2 tools, sin campos prohibidos)* TRES tools cerrados, tupla fija `TOOLS = (REQ_TOOL, FLAGS_TOOL, COV_TOOL)` → `TOOLS_SHA`; se
envían los TRES en TODA llamada, bytes idénticos, y la ronda se fuerza con `tool_choice {type:'tool', name}` (Context 7: cambiar
`tool_choice` conserva tools+system). `emit_information_requirements {applicable: bool, not_applicable_reason?, requirements[≤
WITT_COUNCIL_MAX_PER_MEMBER=5] {gap ≤300, evidence_kind ∈ COUNCIL_EVIDENCE_KINDS, source_family ∈ sorted(SEARCH_DISPATCH), query_en
≤200, entities[≤6], acceptance_test ≤300, priority ∈ must|should}, notes_for_human? ≤400}` — `COUNCIL_EVIDENCE_KINDS =
sorted({spec['evidence_kind'] for spec in SEARCH_DISPATCH} ∪ {'figure'})` = `paper, phenotype, ortholog, expression, homology,
protein-record, gene-phenotype-association, pathway, interaction, dataset, oa-location, web, figure` *(síntesis: los NOMBRES de la
tabla, no el enum del brief — 'text-literature' es `paper`; un enum paralelo se desincroniza)*; `emit_flags {applicable, flags[≤5]
{kind ∈ wet-lab | animal-work | patient-material | budget | compliance | partner-relationship | human-embryo-hard-line, statement
≤300}}` (SÓLO `regulatory-ethics-advisor`; `gate 'human'` lo pone el CÓDIGO); `emit_coverage_judgment {judgments[] {requirement_id,
coverage ∈ covered | partial | uncovered, evidence_ids[≤8], rationale ≤300, search_directive? {query_en ≤200, entities[≤6]}}}`.
**Test estático:** ningún `input_schema` contiene `direct_answer | answer | verdict | confidence | ranking | rank | score |
dispatch`; `evidence_ids` NO lleva `enum` por corrida *(síntesis contra D3: un schema distinto por corrida cambia la definición de
la tool = posición 0 del prefijo = reconstrucción total de la caché; la validación es CÓDIGO, ver C.5)*; sin `strict` (ADR-0081
C.1 f). `validate_tool_input(agent, round, raw) -> (clean, report)`: campos desconocidos se DESCARTAN y cuentan (`dropped_fields[]`),
enums fuera de vocabulario descartan el ÍTEM y se cuentan crudos (`off_vocabulary[]`, jamás corregidos), excedente sobre el tope
se descarta en orden (`n_dropped_over_cap`), tool equivocado para el miembro → fila `errored 'wrong-tool'`. *(C8: alineado al código — `validate_tool_input(agent, round, raw, cfg=None) -> (clean|None, report)`; `report.kind ∈ None | 'wrong-tool' |
'invalid-output' | 'required-missing:<campos>' | 'not-in-membership'` + `dropped_fields[]`, `prohibited_fields_seen[]`,
`off_vocabulary[] {index, field, value}`, `n_dropped_over_cap`, `dropped_items[]`, `truncated_fields[]`, `defaulted_fields[]`;
`WITT_COUNCIL_MAX_PER_MEMBER` acota el CÓDIGO — el `maxItems 5` del schema es CONSTANTE porque el schema es identidad de la caché;
`TOOLS_SHA`, `TOOL_BY_NAME`, `tools_static_check() -> {prohibited_found[], evidence_ids_has_enum, strict_present, names, tools_sha,
ok}`, `tool_for(entry, round)`; topes `STR_CAPS`, `ENTITIES_CAP 6`, `EVIDENCE_IDS_CAP 8`, `FLAGS_CAP 5`)*.
*(C.3 ejecución de una ronda)* `run_round(members, round_, ctx, caller=None, budget_s=None, on_event=None, cancel_check=None, cfg=None, env=None, clock=None,
payload_for=None, phase=None) -> RoundResult` *(C8: alineado al código — `should_abort` se llama `cancel_check`; `members` =
`agent_matrix.council_members(full=<congelado>)`; con `caller=None` usa `default_caller`)*:
`ThreadPoolExecutor(max_workers=WITT_COUNCIL_CONCURRENCY=6)`; **el miembro #1 se lanza SOLO y los demás sólo cuando su future
termina** (Context 7: el prefijo compartido se escribe una vez y se lee 16; el caller es `urlopen` NO streaming, así que "su
primer byte" ES su respuesta completa: +10–20 s por ronda, declarado en `rounds[].stagger_wait_s`) *(injerto D2/D3 sobre D1)*;
espera con `as_completed(timeout=30)` en bucle → `stage.council.progress {n_done, n_pending, elapsed_s, heartbeat True}` cada
≤ 30 s (el hueco de latido NO depende de la latencia de ningún miembro; regla declarada `30 < HEARTBEAT_STALE_S 300 <
WITT_COUNCIL_ROUND_BUDGET_S 300 ≤ WITT_REAP_STALE_S 900 − 300`) *(injerto D3)*; timeout por miembro
`future.result(timeout=WITT_COUNCIL_MEMBER_TIMEOUT_S=120)` → fila `timeout`; presupuesto de ronda `WITT_COUNCIL_ROUND_BUDGET_S=300`:
al vencer no se lanza nada más (`skipped-budget`, cero llamadas), `executor.shutdown(wait=False, cancel_futures=True)`, los hilos
en vuelo se ABANDONAN y se cuentan (`abandoned_threads`, `late_usage_state 'unrecoverable (thread abandoned; provider bills up to
max_tokens)'`, `abandoned_cost_upper_usd [E]`); **`should_abort()` (= `_check_cancel` de la corrida) se consulta antes de cada
despacho y al recoger cada future:** un `POST /runs/{id}/cancel` a media ronda deja los pendientes `skipped-cancelled`, abandona
los en vuelo, persiste lo gastado por los que SÍ terminaron (LOTE-01·A4) y lanza `RunCancelled` en la frontera *(hueco que ningún
diseño cubría)*; reintentos: los del propio caller (`retries=WITT_COUNCIL_MEMBER_RETRIES=1`) — transporte en
`RETRY_TRANSPORT_KINDS` honrando `Retry-After`, contenido en `RETRY_CONTENT_KINDS` (composite_auditor.py:165-167), `refusal`/4xx
nunca → `attempts ≤ 2` por miembro y ronda, y TODO gasto de todo intento se suma (`CallerError.usage`); **TODOS los eventos los
emite el HILO ORQUESTADOR al recoger futures** (`on_event` se encola desde el pool y se drena en el orquestador; Context 6:
`db.add_event` no es reentrante) *(injerto D3 D15)*. Filas `members[] {agent, tool, status ∈ ok | not-applicable | errored | timeout
| skipped-budget | skipped-cancelled | not-invoked, error_kind? (`FAILURE_KINDS` + 'timeout' + 'wrong-tool'), attempts, elapsed_s,
queue_wait_s, usage {input_tokens, output_tokens, thinking_tokens?, cache_creation_input_tokens?, cache_read_input_tokens?} |
null, payload_chars, payload_truncated, card_sha, system_sha, model_reported, relation}` = `MEMBER_STATES` congelada. *(C8: alineado al código — la fila lleva además `seat`, `group`, `mode`, `hard_rule_gate`, `exploratory`, `from_operative`, `dispatched`,
`[output]`, `[validation]`, `[not_applicable_reason | not_invoked_reason | skip_reason]`, `[abandoned, abandon_reason,
late_usage_state]`, `[retry_after_s, stop_reason, response_id]`; `error_kind ∈ composite_auditor.FAILURE_KINDS_* ∪
MEMBER_ERROR_KINDS_EXTRA = ('timeout', 'wrong-tool', 'no-card-in-catalog', 'not-in-membership', 'invalid-output', 'no-model',
'caller-exception')`; la cancelación relanza la excepción de `cancel_check` con `.council_round_result` o `RoundCancelled(result)`;
`RoundResult` gana `quorum {required, met, ratio, n_valid, n_members, source, rule}`, `stagger_first`, `abandoned_agents[]`,
`abandoned_cost_upper_usd {n, usd|None, class 'PROJECTION', state, rule}`, `late_usage_state`,
`cache_prefix_identical_across_members` MEDIDO, `cache {creation, read, class 'medicion'}`, `model {…, effort_pinned, max_tokens}`,
`events {n, emitted_from 'orchestrator-thread', heartbeat_rule}`)*. Ronda VÁLIDA
si `n_valid ≥ ceil(WITT_COUNCIL_QUORUM=0.6 × n_eligible)` — **`n_eligible` = los miembros con algo que juzgar en ESTA ronda**: en r1
todos (N: 17 → 11; 25 → 15); en r2/r3 los DUEÑOS de un requisito `kept` (un miembro `not-invoked` por no tener requisito no puede
votar y NO está en el denominador); un `not-applicable` emitido por el miembro CUENTA como válido (respondió); si no, `state
'incomplete'` *(corrector — antes el denominador era N también en r2/r3: con ≤ 10 dueños la ronda era `incomplete` POR CONSTRUCCIÓN
aunque TODOS votaran válido y la compuerta declaraba no competente sin medir nada, forzando búsqueda + pass2; `quorum {required,
met, ratio, n_valid, n_members: N, n_eligible, n_not_invoked, required_full_membership: ceil(q·N), state ∈ 'met' | 'not-met' |
'vacuous (0 eligible members)', source, rule}` y `RoundResult.n_eligible`; r3 ya corría sobre el subconjunto de dueños — ahora las dos
rondas tienen la MISMA semántica; medido en `smoke_council` (3 dueños → applicable; r2 15 elegibles → required 9) y en
`smoke_run_pipeline` (l): 3 dueños todos covered → competente sin ronda, (c): 7/12 < 8 → incomplete)*. *(corrector — tres ajustes más
de C.3 medidos en `smoke_council`: (i) `cancel_check` sólo cancela con la excepción DECLARADA — `RoundCancelled`, las clases de
`cancel_exc=` (runs pasa `(RunCancelled,)`) o `RunCancelled` por nombre; cualquier otra (`OSError`, `OperationalError`…) es un fallo
del propio `cancel_check`: la ronda SIGUE y queda medido en `RoundResult.cancel_check_errors[] {kind, error, at_s}` /
`n_cancel_check_errors` (antes marcaba a los pendientes `skipped-cancelled` y el registro afirmaba una cancelación que no ocurrió);
(ii) `stage.council.member` lleva la MISMA llave `attempt` en `start` y `done` (`done` conserva `attempts` = total); (iii) el timeout
del SOCKET del caller ya no es `member_timeout_s`: `socket_timeout_s = max(10, (WITT_COUNCIL_MEMBER_TIMEOUT_S − 2·retries) //
(retries+1))` (120 → 59) para que TODOS los intentos quepan en la ventana del orquestador (antes el reintento por timeout arrancaba
justo cuando el orquestador abandonaba el future: llamada fantasma facturada y jamás recogida; `build_request.timeout_s`,
`member_timeout_s`, `timeout_rule`), y `abandoned_cost_upper` multiplica por `attempts_possible = retries + 1` (`n_calls_upper`))*.
*(C.4 agregación de la ronda 1 — código puro, byte a byte)* `aggregate_r1(round_result, members=None, cfg=None, resolver=None)` (alias `aggregate_requirements`) *(C8: alineado al código — `members` = orden
congelado, default `round_result['members_order']`; `resolver(entity) -> ensdarg | True | None`, default `resolve_id.resolve`
(DATA INAMOVIBLE, sólo lectura); devuelve además `aggregation_version`, `n_valid`, `n_raw`, `n_dedup`, `notes_for_human[]`,
`not_applicable_members[]`, `entities_resolution_state`, `rules {…}`, `decided_by 'code (council.aggregate_r1)'`)*:
`requirement_id = 'req-' + sha256(f"{source_family}|{evidence_kind}|{' '.join(sorted(tokens))}")[:12]` con `tokens` =
minúsculas, sin puntuación, únicos, de `query_en ∪ entities`; dedup por esa llave; `query_en` del PRIMER emisor en el orden de
`COUNCIL_MEMBERSHIP` y `variants[]` los demás; `requested_by[]` ordenado; `n_requested_by` ("pedido por k de N", `n_members`
viaja al lado — regla 1 de la webapp: k y N vienen del servidor); `priority = must si algún emisor dijo must`
(`priority_rule 'max over requesters'`); `exploratory True` sólo si TODOS los emisores son `exploratory` → `must` degradado a
`should` con `priority_downgraded_from 'must'` y razón §7.2; `hard_rule_gate True` si ALGÚN emisor es `requirements-human-gated`;
`from_operative True` si algún emisor es operativo (full-council); `entities` pasan por `resolve_id.resolve` (answer_pipeline.py:
253-260 patrón `check_entities`) → `entities_resolved[]` / `entities_unresolved[]` (nunca afirmadas); `harness_state ∈
'satisfiable' | 'unsatisfiable-by-harness (<unavailable_reason>)' | 'unsatisfiable-by-harness (evidence_kind figure — ADR-0083)'`
cuando `SEARCH_DISPATCH[family].tool_module is None` (`web`, `tooluniverse`) o `evidence_kind == 'figure'`; `n_unsatisfiable`
CONTADO (la demanda medida del sidecar, ver (I)); orden `must > should`, `n_requested_by desc`, `requirement_id asc`; tope
`WITT_COUNCIL_MAX_REQUIREMENTS=24` → `truncated True, n_truncated, truncated_ids[]`; `flags[]` de `emit_flags` con `gate 'human'`
y `emitted_by`; `json.dumps(sort_keys=True, ensure_ascii=False, separators=(',',':'))` → `aggregation_sha`. **Golden:** agregar
con los miembros BARAJADOS → JSON byte-idéntico y mismos `requirement_id`. Estados del agregado `AGGREGATE_STATES = ('applicable',
'incomplete', 'errored (<kind>)')`. *(C8: alineado al código — `AGGREGATE_STATES_EXACT = ('applicable', 'incomplete')` + `AGGREGATE_STATE_PREFIXES = ('errored (',)`; predicado
`aggregate_state_in_vocabulary`)*.
*(C.5 cobertura de la ronda 2 — cada miembro juzga SUS requisitos)* El payload r2 de un miembro lleva SÓLO los requisitos `kept` que
él pidió (`requested_by ∋ agent`), la vista de evidencia `_compact_evidence(bundle, include_path_b=True)` *(síntesis, D2/D3 sobre D1:
cuando lo estructural ya disparó la Ruta B dentro de `retrieve`, `structural_not_fired` ya es False y ocultarle los papers al
consejo sólo produce directivas redundantes; pass1 sigue DI-only y conf1 no se toca — decisión (2) del brief §4 intacta;
`coverage.pre_search.evidence_view 'DI + path_b (structural, if fired)'` declarado)*, recortada por miembro a
`WITT_COUNCIL_R2_EVIDENCE_CHARS=24000` con `payload_truncated` declarado *(hueco de los jueces: el único insumo que crece con
ADR-0078 y nadie acotaba)*, `pass1 {direct_answer, gap_flags, absence_kind, citations}` y `human_attestations` como PRIOR ART
(ver (F)). `judge_coverage(round_result, ledger, evidence_ids, phase='pre-search', round_=None)` (alias `aggregate_coverage`; `evidence_ids` =
`runs._evidence_ids(bundle)` o el bundle vía `evidence_ids_of`) *(C8: alineado al código)*: un `requirement_id` ajeno o inexistente → juicio descartado y
contado (`foreign_requirement_ids[]`); **un `evidence_id ∉ _evidence_ids(bundle)` (runs.py:1361-1374) → `hallucinated_evidence_ids[]`
y el voto se ANULA (`annulled True`)**; **un voto `covered | partial` SIN `evidence_ids` también se ANULA** (`annul_reason
'<coverage> without any evidence_id'`, contado en `n_annulled_votes`; `uncovered` no exige id) *(corrector — la regla estaba
congelada en `council.COVERAGE_RULE` y medida en `smoke_council` (13)(14) pero NO escrita aquí; es coherente con §7 "nada se afirma
sin id" y se APLICA como default (a); Emmanuel decide antes de `contract-1.11-frozen` si la conserva o la retira (b) — el ADR y el
`rule` congelado deben decir lo mismo)*; `coverage_final` = worst-of-N sobre votos válidos (`uncovered > partial > covered`; regla de
la casa, composite_auditor.py:30-32); sin votos válidos → `'not-judged'`; requisito `aporto` → `'covered-by-attestation'` (estado
propio, distinto de `covered`); `discard` → `'discarded'`. Para la compuerta (ver (G)): **must con `coverage_final ∈ {uncovered,
partial, not-judged}` cuenta como SIN cubrir** (lectura conservadora, patrón ADR-0080 E); `must` con `harness_state
'unsatisfiable-by-harness (…)'`, `covered-by-attestation` o `discarded` NO cuentan y se declaran aparte (`must_unsatisfiable`,
`must_attested`, `must_discarded`) — un must que el harness no puede satisfacer dejaría la rama competente constante-falsa (E1).
`COVERAGE_STATES = ('covered', 'partial', 'uncovered', 'not-judged', 'covered-by-attestation', 'discarded')`. *(C8: alineado al código — la cobertura lleva además `must_gateable` (kept ∧ satisfiable), `must_covered`, `must_uncovered_strict`,
`uncovered_must_ids[]`, `n_foreign_votes`, `n_hallucinated_votes`, `n_annulled_votes`, `n_valid_votes`, `pertinence
{evidence_id: [requirement_id]}` (votos válidos covered|partial → `verify_output.support_state_for(council_pertinence=)`),
`pertinent_source 'council.<round> (covered|partial votes)'`, `must_uncovered_rule`, `class`, `decided_by`; `COVERAGE_VOTES =
('covered', 'partial', 'uncovered')` es el vocabulario del VOTO, distinto del del estado final)*.
*(C.6 directivas — las compila CÓDIGO, la tabla resuelve el mecanismo)* `directives_from(coverage, ledger, members_order=None)` (alias `compile_directives`) *(C8: alineado al código — devuelve `{directives[] (+
query_en_original?, state 'compiled'), excluded[] {requirement_id, family, state, reason}, n, n_excluded, families[], state ∈
'provided' | 'none (all must covered)', rule, decided_by}`; `DIRECTIVES_STATES = ('provided', 'none (all must covered)', 'not-run')`
es el vocabulario del CONJUNTO — `frozen.council.directives_state` —, `DIRECTIVE_STATES` el de cada directiva)*: por cada requisito
`kept` con `coverage_final ∈ {uncovered, partial, not-judged}` y `harness_state 'satisfiable'` se emite UNA directiva
`{requirement_id, family: source_family, query_en, entities[], symbols[] (los `entities_resolved`), evidence_kind, priority,
requested_by[], refined_by_members[]}`; **la directiva NO depende de que el miembro haya escrito `search_directive`**: el requisito
ya trae familia, query y entidades; `search_directive` del voto sólo REFINA `query_en`/`entities` (declarado en `refined_by_members`)
*(síntesis: ningún despacho pende de prosa opcional del modelo)*. Familia desconocida → `directives_excluded 'unknown-family'`;
`tool_module None` → `'excluded-unsatisfiable'`. Dedup por `(family, requirement_id)`. `DIRECTIVE_STATES = ('compiled',
'excluded-unknown-family', 'excluded-unsatisfiable')`.
*(C.7 re-cobertura r3 y cobertura estructural)* `coverage_after_search(coverage_pre, search_ledger, directives=None)` es CÓDIGO y corre SIEMPRE *(C8: alineado al código — `state ∈ 'measured' |
'not-run (no search ledger)'`; lee ítems de `search_ledger['items']` ∪ `search_ledger['rounds'][*]['items']` con
`directive_requirement_ids[]`; `recoverage_members(coverage_pre, ledger)` da el subconjunto de r3)*:
cada ítem admitido por el harness lleva `directive_requirement_ids[]` (la familia que lo trajo sabe qué requisito la pidió) →
`coverage.after_search.by_requirement[] {requirement_id, state ∈ retrieved-for | still-uncovered | not-searched | covered-pre}`
(`retrieved-for` es MEDICIÓN estructural — hubo ítem admitido para su directiva —, distinta de `covered`, que es juicio) *(injerto
D2)*. La ronda r3 de MODELO (re-juicio) corre SÓLO si `WITT_COUNCIL_RECOVERAGE=1` (default) ∧ `search_ledger.n_admitted_total > 0`
∧ hay requisitos `kept` sin cubrir, y SÓLO sobre los miembros dueños de esos requisitos (subconjunto: `n_invoked < N`), con el
bundle YA con path_b *(injerto D3: "nada se re-ejecuta con los mismos insumos", corrector ADR-0080)*; r3 es INFORMATIVA (registro,
panel vía `deterministic_checks.council`, turno siguiente): JAMÁS re-gatea ni abre otra ronda de búsqueda (tope: rondas de
búsqueda ≤ 2, consejo ≤ 3 llamadas por miembro y turno). `coverage.post_search.state ∈ 'judged' | 'not-run (nothing admitted)' |
'not-run (all must covered)' | 'not-run (kill-switch WITT_COUNCIL_RECOVERAGE=0)' | 'not-run (search not triggered)'`. *(C8: alineado al código — `council.POST_SEARCH_STATES_EXACT` son esos 5; `runs.execute_run` emite además `'not-run (structural search preceded r2;
nothing admitted after r2)'`, `'not-run (errored (<Tipo>))'` y `'not-run (no round 2 coverage: council <state>)'`, validados por el
prefijo `'not-run ('`)*.
*(C.8 estados y vocabularios congelados)* `COUNCIL_STATES_EXACT = ('queued', 'running', 'applicable', 'incomplete',
'skipped-by-human', 'not-applicable (no-ledger)', 'disabled (kill-switch WITT_COUNCIL=0)', 'pre-adr-0082')`,
`COUNCIL_STATE_PREFIXES = ('errored (', 'not-requested (')`, `council_state_in_vocabulary(s)` (predicado del gate de paridad,
patrón `plan_state_in_vocabulary`, runs.py:1852); `MEMBER_STATES`, `COVERAGE_STATES`, `DECISION_STATES = ('keep', 'discard',
'aporto', 'pending')`, `DECIDED_BY_PREFIXES = ('human:', 'default-keep', 'gate-human-pending')`, `DIRECTIVE_STATES`, `ROUND_KINDS =
('requirements', 'coverage', 'recoverage')`; `ROUNDS`, `ROUND_PHASES`, `PRIORITIES`, `COVERAGE_VOTES`, `LEDGER_STATES = ('draft', 'approved', 'skipped-by-human')`,
`DIRECTIVES_STATES`, `AFTER_SEARCH_STATES`, `POST_SEARCH_STATES_EXACT`, `HARNESS_STATES_EXACT/_PREFIXES`, `FLAG_KINDS` (7),
`MEMBER_ERROR_KINDS_EXTRA`, `COUNCIL_EVIDENCE_KINDS` (13), `COUNCIL_SOURCE_FAMILIES` (15) *(C8: alineado al código — vocabularios añadidos por C2;
`council_vocabulary()` devuelve 25 llaves incl. `membership_groups`, `membership_modes`, `prohibited_output_fields`)*; `council_vocabulary()` los devuelve juntos y viaja congelado en
`frozen.council.vocabulary` (el gate (F) de paridad los compara con los unions de `types.ts` y con TODOS los fixtures).
`env_config(env)` tolerante para las 27 env de la tabla (vacía/basura → default declarado con fuente). *(C8: alineado al código — `env_config(env=None) -> {NAME: {value, source, default}}` delega en `models.env_value` cuando la env está en
`models.ENV_TABLE`; `config(env=None, **overrides) -> cfg` plano — `model=`, `concurrency=`, `heartbeat_s=`, `member_retries=` ganan a
la env; `quorum_required(n_members, quorum)`; `resolve_council_model(env, cfg) -> {model, source, generation, known, max_tokens,
max_tokens_source, effort, effort_source, effort_sent, effort_sent_source}`)*.
*(C.9 kill-switch)* `WITT_COUNCIL=0` → `council.enabled(env) -> (False, source)` *(C8: alineado al código — devuelve la tupla `(bool, source)`)*: `run_round` no se llama nunca (cero llamadas, cero eventos
`stage.council.*`); `POST /runs/plan` no encola; `competence` recibe `council_coverage=None`; `build_search_plan(directives=None)`
y `models.panel(directives=None)` EXACTAMENTE como hoy (ver (L)).

**(D) El caller y la tabla de modelos.** *(D.1 `composite_auditor._anthropic_tool_call`, aditivo)* gana `tools=None` (lista
completa a enviar; `tool` sigue nombrando el forzado — sin `tools=` el cuerpo es `[tool]`, byte a byte el de hoy) y acepta `system`
como `str` (hoy) o `list[block]` (bloques con `cache_control` tal cual). **Semáforo de PROCESO** `_INFLIGHT =
threading.BoundedSemaphore(WITT_ANTHROPIC_MAX_INFLIGHT=8)` adquirido alrededor de `urlopen` (composite_auditor.py:503) para TODA
llamada Anthropic — consejo, síntesis, elicitación, planner, jueces — con `meta.queue_wait_s` medido *(síntesis, D2/D3 sobre D1: el
riesgo del brief §12 es 17 × `WITT_RUN_WORKERS` × panel; un semáforo que no ve al panel no acota nada)*; `Retry-After` honrado en
`http-429/529` con tope `WITT_ANTHROPIC_RETRY_AFTER_CAP_S=30` (sin cabecera, el `_backoff(2*(attempt+1))` de hoy),
`CallerError.retry_after` y `meta.retry_after_honored_s`; `usage` NUMÉRICO conserva `cache_creation_input_tokens` /
`cache_read_input_tokens` (ya lo hace `_numeric_usage`). Los llamadores y fakes de hoy no cambian (2-tupla intacta). *(C8: alineado al código — firma `_anthropic_tool_call(model, system, user_text, tool=None, timeout=120, retries=1, max_tokens=1200, effort=None,
return_meta=False, tools=None)`; el `tool` forzado DEBE estar en `tools=` (si no, `ValueError` antes de llamar); `meta` gana
`attempts` (hechos), `usage_prior_attempts?`, `queue_wait_s`, `retry_after_honored_s?`; `CallerError(kind, message,
legacy_type_name=None, usage=None, meta=None, retry_after=None)`; `RETRY_AFTER_KINDS = ('http-429', 'http-529')`;
`inflight_limit(env)`, `retry_after_cap(env)`, `_INFLIGHT_RULE`)*. `audit()`
NO cambia: `directives` sigue aceptado e ignorado y `panel_source.council_hook` queda `not-available` (ADR-0081 K) — las lentes por
nicho cambiarían `panel_signature` y cortarían la serie de ADR-0087 (ver (K.a)). *(D.2 `models.py`: rol `council` FUERA de
`PIPELINE_ROLES`)* `COUNCIL_ROLES = ('council',)`, `ROLES = PIPELINE_ROLES + JUDGE_ROLES + COUNCIL_ROLES` (models.py:122-124),
`ROLE_FAMILY['council'] = 'anthropic'`, `ROLE_ENVS['council'] = 'WITT_MODEL_COUNCIL'`, `GENERATIONS[*].defaults['council']` =
`claude-opus-5` (g2) · `claude-opus-4-8` (g1, declarado: g1 no tenía consejo, la llave existe para que `resolve_role('council')` no
lance), `MAX_TOKENS_KEYS += 'council'` con tope **4000** (g2; techo, no gasto: opus-5 piensa por default y el tope acota
pensamiento + respuesta) / 1200 (g1). **`panel_signature` (:642-655) itera `PIPELINE_ROLES` y `snapshot()` escribe `role.<rol>` por
`PIPELINE_ROLES` (:689): con el rol FUERA la firma de toda corrida queda INTACTA — también bajo `WITT_COUNCIL=0`** *(veredicto de los
dos jueces contra D1/D3: meterlo en `PIPELINE_ROLES` cambiaba la firma en silencio y cortaba la serie de ADR-0087)*.
`SNAPSHOT_FIELDS += 'role.council', 'council.enabled', 'council.full', 'council.effort', 'council.cache_ttl'` (una fila más por campo
en `config_history` al arrancar: excepción DECLARADA, ver (L)); `ENV_TABLE` gana las 27 filas nuevas (`WITT_COUNCIL_*`, `WITT_MODEL_COUNCIL`, `WITT_CG_COUNCIL_COMPONENT`,
`WITT_ANTHROPIC_MAX_INFLIGHT`, `WITT_ANTHROPIC_RETRY_AFTER_CAP_S`; el check de `smoke_models` env ⊆ compose ∩ README las cubre).
`CACHE_MULTIPLIERS = {'write_5m': 1.25, 'write_1h': 2.0, 'read': 0.1}` con `CACHE_MULTIPLIERS_SOURCE 'platform.claude.com pricing
(prompt caching); skill claude-api shared/prompt-caching.md cached 2026-06-24'` y `CACHE_AS_OF`; `cache_prices(model) -> {write_5m,
write_1h, read, price_in, class, multipliers, source, as_of}` (`None` si el modelo no está cotizado) derivados de `price_in` (clase
`'derived-from-published-multipliers'` hasta que LG1 mida) *(C8: alineado al código)*. `WITT_COUNCIL_EFFORT`
(default **`medium`**, ∈ `ANTHROPIC_EFFORTS`; el literal **`inherit`** hereda `WITT_ANTHROPIC_EFFORT` — VACÍA es `medium`, no
herencia *(C8: alineado al código — `models.council_effort(env) -> (effort|None, source)`; `COUNCIL_EFFORT_CHOICES = ANTHROPIC_EFFORTS + ('inherit',)`;
el borrador decía "vacío = hereda")*) FIJO por ruta para las 17 llamadas de las tres
rondas *(injerto D3/jueces: cambiar `effort` por petición invalida la caché y, en modelos que lo renderizan antes, también
tools+system; "pin per route")* — se envía como `output_config.effort` SÓLO a modelos `thinking_default 'adaptive'` (regla ADR-0081
C.4); `frozen.council.model.effort` + `effort_source`. E2 decide el default tras LG1.

**(E) La ronda 1 es un JOB del PLAN — ni corrida ni tabla `jobs` genérica.** *(E.1 BD, `db.py`, aditivo)* `plans` gana columnas
(`_migrate`, patrón ADR-0078/0079 con `_dt_type` compilado por dialecto, db.py:290): `origin VARCHAR(24)` (derivado por
`runs.run_origin()` al crear el plan — el mismo derivador de la corrida), `council_state VARCHAR(96)` *(C8: alineado al código — `db.COUNCIL_STATE_MAXLEN 96`; el literal más largo de E.3 mide 74 chars y no cabía en 40)*, `council_json TEXT` (r1:
rounds[0] + agregación + requisitos SIN decisiones), `council_ledger_json TEXT` (decisiones humanas + `knowledge_now`),
`council_usage_json TEXT`, `council_claimed_by VARCHAR(64)`, `council_claimed_at/started_at/finished_at/last_event_at/
approved_at <dt>`, `council_approved_by VARCHAR(64)`, `council_error TEXT`; `runs` gana `council_json TEXT` (la COPIA server-side
al encolar, ver (F.4)); tabla NUEVA `plan_events (plan_id VARCHAR(64) FK plans.plan_id, seq INTEGER, ts, type, agent, tool, level, degraded *(C8: alineado al código — espejo EXACTO de `run_events`, misma forma de fila)*,
payload_json)` PK `(plan_id, seq)` — espejo de `run_events` SIN FK a `runs` (Context 5), nace por `create_all` (sin ALTER);
`CREATE INDEX IF NOT EXISTS ix_plans_council_state ON plans (council_state, created_at)`. Planes viejos: `council_state NULL` se lee
`'pre-adr-0082'` (declarado, jamás backfill). Funciones: `create_plan(..., origin=, council_state=)`, *(C8: alineado al código — firmas exactas: `create_plan(plan_id, user_id, question, entities, plan_json, origin=None, council_state=None)`,
`claim_next_council_plan(worker_id, origins=None, plan_id=None)`, `update_plan_council(plan_id, **values) -> bool` (sólo
`PLAN_COUNCIL_COLUMNS`), `plan_add_event(plan_id, type, payload=None, agent=None, tool=None, level='info', degraded=None) -> seq`,
`plan_events_after(plan_id, after_seq=0, limit=500)`, `plan_events_count`, `reap_stale_council_plans(stale_s, now=None,
reason='worker-lost', stale_s_source=None) -> [plan_id]` (`COUNCIL_REAP_STATE`), `set_plan_ledger(plan_id, ledger_json,
approved_by=None, council_state=None) -> bool`, `plans_council_pending(user_id, question, entities_csv, parent_run_id, since)`,
`count_plans_council(user_id=None, states=None)`, `plans_council_usage(frm=None, to=None, include_origins=None)`,
`plans_with_council(include_origins=None, limit=1000)`, `closed_runs_with_council(limit=1000, include_origins=None)`,
`council_migration_statements(dialect=None)` (14 ALTER) y `council_schema_state() -> {plans_missing[], runs_missing[],
plan_events_table, ready}` para el 503 `council-db-unavailable`; `create_run(..., origin=None, root_question_id=None,
council_json=None)`; `get_plan` devuelve todas las columnas y `council_state_of(row)` distingue columna ausente ≠ NULL
(`'pre-adr-0082'`) ≠ valor)* `claim_next_council_plan
(worker_id)` (UPDATE optimista `WHERE council_state='queued'`, FIFO por `created_at`, `claimed_by = boot:pid:hilo`),
`update_plan_council(plan_id, **values)`, `plan_add_event` / `plan_events_after` (seq monotónico + `council_last_event_at`),
`reap_stale_council_plans(stale_s, now, reason)` (misma carrera resuelta que `reap_stale_running`: `WHERE council_state='running'
AND council_last_event_at = <leído>` → `'errored (worker-lost)'` + evento `council.state`; jamás re-encola), `set_plan_ledger`
(rechaza si `plans.run_id` ya está sellado → 409 `plan_already_used`), `plans_council_usage(frm, to, include_origins)` (para
`/usage.plans_council`), `plans_council_pending(user_id, question, entities_csv, parent_run_id, since)` (dedup, E.3),
`closed_runs_with_council` y `plans_with_council` (para el índice (I)). *(E.2 worker propio — `rag_index/query_service/
council_jobs.py`, NUEVO)* hilos daemon `council-worker-<i>` (`WITT_COUNCIL_WORKERS=1`) con el patrón `runs.worker_loop`
(runs.py:3120-3128): reclaman → `execute_round1(plan_row, caller=None, env=None, on_event=None, clock=None, cfg=None, resolver=None, payload_for=None, prior=None,
inherited=None)` (inyectable; NUNCA lanza `Exception`: persiste `errored (<Tipo>)`; una `BaseException` sube y el plan queda
`running` para el reaper) *(C8: alineado al código)* → `council.run_round(r1, …)` con
`payload_for(member)` = `{question, entities, plan.judgment (work_type, route, niches, clarifying_questions), prior_observations[]
(I)}` → **persistencia INCREMENTAL**: tras CADA future recogido se escribe `council_json.members[]` y `council_usage_json`
(un redeploy a media ronda conserva lo gastado por los que respondieron — LOTE-01·A4 aplicado al plan; hueco de los jueces) →
`aggregate_requirements` → `council_state ∈ 'applicable' | 'incomplete' | 'errored (<kind>)'`, `council_finished_at`,
`stage.council.aggregate` en `plan_events`; una excepción del worker deja `errored (<tipo>)` y NO tumba el hilo. **El cierre del job
es CONDICIONAL** *(corrector — misma carrera resuelta que `runs._finish`/`db.finish_run`, ADR-0078)*: `write_final`/`write_errored`
cierran con `db.update_plan_council(plan_id, expected_state='running', …)` (`UPDATE … WHERE plan_id=? AND council_state='running'`);
`rowcount 0` = el reaper ya sentenció `errored (worker-lost[-restart])` (p. ej. solape de contenedores en un redeploy) o el humano
saltó mientras el hilo seguía vivo → el veredicto terminal NO se pisa, `council_json`/`council_usage_json` SÍ se escriben (lo gastado
es medición) y queda UN evento `council.state.conflict {attempted, found, found_error, ignored true, note 'finished-after-reap…',
plan_id, claimed_by}` (`level 'warning'`) en vez del `council.state` terminal; el resumen de `execute_round1` lleva `state_written`
y `conflict` (medido en `smoke_council_jobs_db` 7g/7h). Reaper de planes
en un hilo PROPIO `council-reaper` (`council_jobs.reaper_loop`; `runs._reap_once` sigue segando sólo `runs`) con el MISMO
`WITT_REAP_STALE_S` *(C8: alineado al código — el borrador lo metía en el `run-reaper`; C4 entregó el hilo propio con
`start_council_workers(n=None, reap_stale_s=None, env=None, caller=None, reaper=True, poll_seconds=1.0, job_kwargs=None)` y C5 lo
lanza desde `runs.start_workers` → `runs.start_council_workers(n=None)`, que devuelve un estado DECLARADO `'started' | 'disabled
(kill-switch WITT_COUNCIL=0)' | 'not-started (WITT_COUNCIL_WORKERS=0)' | 'not-available (…)' | 'error: …'`; con `WITT_COUNCIL=0`
cero hilos, cero siega y los jobs preexistentes se DECLARAN en `orphans`)* y siega al arranque con
umbral 0 (`'errored (worker-lost-restart)'`), patrón ADR-0078; `start_workers` lanza `council-worker-N` junto a `run-worker-N`.
*(E.3 `POST /runs/plan` encola — con compuertas de gasto)* El planner sigue SÍNCRONO (10–20 s hoy; LG2 mide el p95 contra el
timeout del proxy: si rebasa, volver asíncrono el planner es una línea más sobre el MISMO job, declarado, no deuda). Se encola r1
(`council_state 'queued'`) SÓLO si `WITT_COUNCIL=1` ∧ `judgment.state == 'declared'` ∧ `route == 'evidence-run'` ∧ `niches ≠ []` ∧
`origin ∈ WITT_COUNCIL_ORIGINS` (default `production`; el loop dev-offline, los smokes con `WITT_RUN_ORIGIN=smoke` y `gen_fixtures`
con `fixture` NO disparan 17 llamadas de opus-5 — Context 9); si no, `council_state 'not-requested (route store-consultation)' |
'not-requested (niches empty)' | 'not-requested (judgment <state>)' | 'not-requested (origin <o> not in WITT_COUNCIL_ORIGINS)' |
'disabled (kill-switch WITT_COUNCIL=0)'` *(injerto D3 + hueco de los jueces)*. **Dedup del doble clic:** si el MISMO usuario tiene
un plan con la MISMA `(question, entities_csv, parent_run_id)` en `council_state ∈ {queued, running}` creado hace <
`WITT_COUNCIL_DEDUP_S=600` s, `POST /runs/plan` NO llama al planner ni crea plan: responde 200 con ESE plan y `reused_from_plan_id`
+ `reused_reason 'council round 1 queued|running for an identical question (dedup window)'`; **el dedup se RE-CONSULTA después del
planner e inmediatamente antes del INSERT** *(corrector — dos POST idénticos que llegaban dentro de los 10–20 s del planner pasaban
los dos la primera consulta, llamaban al planner los dos y creaban DOS jobs `queued` (2 × 17 llamadas); ahora el segundo responde
200 `reused` con `reused_after_planner True` y `reused_reason '… — concurrent request: the planner call of this request was already
spent (declared); no second council job was created'` — el gasto del planner de ese request ya ocurrió y se dice; el cierre TOTAL
(insertar la fila del plan ANTES del planner con un estado `planning` y completar `plan_json` después) queda declarado y NO hecho:
una fila de `plans` sin `plan_json` rompe a todos sus lectores (GET /plans/{id}, dedup, /usage) y el planner asíncrono es la línea de
(K.d) si LG2 lo pide; medido en `smoke_council_http` 16b con dos hilos y una barrera dentro del planner)*; y un usuario no puede tener más de
`WITT_COUNCIL_MAX_QUEUED_PER_USER=3` jobs `queued` (el 4º nace `'not-requested (queue-cap per user)'`, el plan sí se crea) *(hueco de
los jueces: la fuga de costo más barata de cerrar)*. La respuesta gana `council {state, plan_id, membership_version, n_members,
full_council, catalog_sha, model {model, source, generation, effort}, poll '/plans/{plan_id}', events '/plans/{plan_id}/events',
stream '/plans/{plan_id}/stream', budget {member_timeout_s, round_budget_s, concurrency, quorum}, estimate {class 'PROJECTION',
usd_low, usd_high, assumptions[]}}`. *(C8: alineado al código — la respuesta lleva además `plan_response 'created' | 'reused'`, `origin {value, source}`, `reused_reason?`; `council`
gana `matrix_version`, `full_council_source`, `catalog_state`, `model {…, known, priced, max_tokens, effort_source, effort_sent,
effort_sent_source, resolver}`, `budget {…, quorum_required, source}`, `estimate {…, round 'r1', n_members, model, state
'projected' | 'not-priced (…)', source}`, `gates {kill_switch, origins_allowed, origins_source, dedup_window_s,
max_queued_per_user}`, `modules {council, council_index, db_missing[]}`; un estado más: `'not-requested (council db
unavailable)'` cuando la BD no tiene las columnas E.1 — se sirve, no se oculta)*. *(corrector — ese estado era INALCANZABLE: `create_plan` y
`create_run` INSERTaban `origin`/`council_state`/`council_json` incondicionalmente y una BD sin migrar fallaba con 500 antes de
declarar nada; ahora ambos OMITEN las columnas E.1 ausentes (`db._missing_council_columns(table)`, cacheado por tabla al quedar
lista) y el estado se sirve como está escrito — `council_state_of(fila sin columna) → None` → `'not-requested (council db
unavailable)'`; medido simulando la BD sin migrar en `smoke_council_http` 16d; LG8 lo mide en el Postgres real)*. **`GET /plans/{plan_id}`** → `{plan_id, plan, origin, council_state, council (r1 + agregación
+ requisitos), ledger, approved_by, approved_at, run_id, heartbeat_age_s, heartbeat_stale}` *(C8: alineado al código — además `user_id`,
`question`, `entities_csv`, `created_at`, `council_usage`, `council_error`, `approved_by_is_author`, `council_claimed_by/_at`,
`council_started_at`, `council_finished_at`, `council_last_event_at`, `heartbeat_stale_after_s 300`, `run_gate {allowed, reason null
| 'council_round1_pending' | 'council_ledger_unapproved', council_state, kill_switch}`, `poll`, `events`, `stream`; 404 `{state
'plan_not_found'}`; `/events` y `/stream` responden 503 `{state 'council-db-unavailable', missing[]}` sin las columnas E.1)*; **`GET /plans/{plan_id}/events?after=`**
y **`GET /plans/{plan_id}/stream`** (SSE, el MISMO generador que `/runs/{id}/stream` — app.py:995-1029, keep-alive 15 s — sobre
`plan_events`; cierra con `event: end {council_state}` en estado terminal) *(síntesis: SSE con polling de respaldo, no sólo polling —
la card quiere latido por miembro)*. Las rutas viven bajo `/plans/*`: no colisionan con `/runs/{run_id}` (app.py:691) ni con
`/runs/plan`.

**(F) El ledger humano — el ÚNICO punto donde la prosa del consejo se vuelve gasto.** *(F.1 `POST /plans/{plan_id}/council/ledger`)*
body `{decisions[] {requirement_id, decision ∈ keep | discard | aporto, reason? (OBLIGATORIA con discard), attested_text?
(OBLIGATORIO con aporto, ≤ WITT_COUNCIL_ATTESTATION_CHARS=4000)}, knowledge_now? ≤4000, approve: bool}` → 200 `ledger`; 404
`plan_not_found`; 409 `council_not_terminal {council_state}` mientras r1 esté `queued | running`; 409 `plan_already_used {run_id}`
tras el sello; 400 `unknown_requirement_id[ids]`; 400 `discard_without_reason[ids]` / `aporto_without_text[ids]`; **400
`hard_rule_requirements_undecided[ids]` si `approve` y algún requisito con `hard_rule_gate True` sigue `pending`** (§7.1: la
salida de `causal-pruner` exige decisión humana EXPLÍCITA sobre ESE requisito — ningún default la toma). *(C8: alineado al código — errores 400 adicionales: `duplicated_requirement_id`, `invalid_decision (+allowed[])`, `attested_text_too_long
(+max_chars, max_chars_source)`, `knowledge_now_too_long`; 409 `council_ledger_not_applicable {council_state}` cuando r1 no es
`applicable | incomplete`; 503 `council-db-unavailable`; la respuesta 200 es `{plan_id, council_state, ledger {state, decisions[]
(una fila por requisito en el orden del agregado), n_requirements, n_keep, n_discard, n_aporto, n_pending, n_hard_rule,
n_hard_rule_pending, n_default_keep, knowledge_now, approved_by, approved_at, approved_by_is_author, saved_by, saved_at, n_saves,
attestation_chars_max (+_source), permissions_rule, source}}`; la lógica pura vive en `council.apply_ledger_decisions(aggregation,
decisions, approve, decided_by, decided_at, knowledge_now, attestation_chars, ledger) -> ledger` con `errors
{unknown_requirement_id[], discard_without_reason[], aporto_without_text[], hard_rule_requirements_undecided[]}` y `has_errors`)*. Los demás `pending` al
aprobar toman `decision 'keep'` con `decided_by 'default-keep'` (declarado: "ningún requisito se descarta", brief §3); una decisión
humana lleva `decided_by 'human:<user_id>'`, `decided_at` del servidor y `approved_by_is_author` (= `plans.user_id == sesión`;
permisos planos — cualquier sesión autenticada puede aprobar, y queda dicho quién). `ledger.state ∈ 'draft' | 'approved' |
'skipped-by-human'`; un BORRADOR guardado DESPUÉS de una aprobación vuelve el ledger a `draft` y **limpia `plans.council_approved_by/at`
en el MISMO UPDATE** *(corrector — antes `GET /plans/{id}` servía `approved_by` del aprobador anterior junto a `ledger.state 'draft'`
y `run_gate` cerrado: dos verdades; medido en `smoke_council_http` 16a)*; `knowledge_now {text, class 'attested', by, at, chars, truncated}`. Un `attested_text`/`knowledge_now` viaja
íntegro en `plans.council_ledger_json` y RECORTADO a 600 chars en el frozen (`truncated` declarado). *(F.2 `POST
/plans/{plan_id}/council/skip {reason}`)* → `council_state 'skipped-by-human'` con autor y hora (libera la corrida con ledger VACÍO
declarado; el sistema jamás salta solo). *(F.3 `POST /runs {plan_id}` exige la puerta)* 409 `council_round1_pending {plan_id,
council_state}` si `council_state ∈ {queued, running}`; 409 `council_ledger_unapproved {plan_id}` si `applicable | incomplete` sin
ledger aprobado ni skip; `errored (…)` / `not-requested (…)` / `disabled (…)` / `pre-adr-0082` NO bloquean (`frozen.council.state`
lo dirá) *(veredicto de ambos jueces: es la decisión tomada — "el humano aprueba el ledger ANTES de correr" — y el brief §4 A; D2
gastaba r2 y búsqueda sobre prosa que nadie aprobó y con 0 requisitos daba un True vacío; D3 es el fallback honesto si Emmanuel
re-decide por no-hang: E4)*. **El sello se COMPRUEBA** *(corrector — preexistente @ 9d90c01: el bool de `db.mark_plan_used` se
descartaba y dos POST /runs concurrentes con el mismo `plan_id` producían DOS corridas del mismo plan, ahora con la misma copia del
consejo → r2 ×2; si el sello lo ganó otra corrida entre la lectura de la fila y el UPDATE, la corrida recién encolada se cancela
con `cancelled_by 'server'` y razón `'plan_already_used race: …'` (traza de la carrera, jamás se borra) y la respuesta es 409
`plan_already_used {plan_id, run_id: ganador, cancelled_run_id}`; medido en `smoke_council_http` 16c)*. *(F.4 sello al encolar)* `app.create_run` compone server-side `runs.council_json = {r1: plans.council_json,
ledger: plans.council_ledger_json, membership_version, n_members, members[], catalog_sha, plan_id, composed_at, source
'plans.council_json + plans.council_ledger_json (copied at enqueue)'}` *(C8: alineado al código — `runs.compose_council_json(prow)`; la copia lleva además `r1_state` (= `plans.council_state`), `full_council`,
`membership_source 'plan.council (frozen at r1)' | 'not-available (plan without council round 1)'`; viaja por `runs.new_run(...,
council_json=<str JSON>, plan_id=)` → `db.create_run(council_json=)` y emite `run.state{queued}.council {ledger_present,
ledger_state, n_kept, n_hard_rule, r1_state, plan_id, n_members, persisted}`; `runs.council_run_gate(council_state, ledger, enabled)`
es el predicado del 409 y del `frozen.council.state`)* — JAMÁS del cliente; `plan_json` sigue byte-idéntico a
`plans.plan_json` (`plan_question_matches_run` intacto). **La membresía y N quedan CONGELADOS en esa copia:** r2/r3 usan
`members[]` y `n_members` del plan, no la env vigente (`membership_source 'plan.council (frozen at r1)'`; cambiar
`WITT_COUNCIL_FULL` entre plan y corrida no mueve el cuórum en silencio — hueco de los jueces). Sin `plan_id` → sin ledger →
`frozen.council.state 'not-applicable (no-ledger)'` y cero llamadas de consejo en la corrida. *(F.5 lo atestiguado JAMÁS es
evidencia)* `aporto` y `knowledge_now` viajan al sintetizador (pass1, pass2, revisión) como llave HERMANA `human_attestations
{knowledge_now, attestations[] {requirement_id, text, by, at}}` FUERA de `evidence` (misma disciplina que `thread_context`,
runs.py:1426-1438); `synth_system` y `SYNTH_TOOL.description` ganan la cláusula `ATTESTATION_ANTI_LEAK_CLAUSE` ("attested by
humans is PRIOR ART, not evidence; never cite an identifier from it unless it appears in evidence"); predicado DURO
`attestation_identifier_leak` = identificadores presentes en las atestiguaciones ∩ respuesta − evidencia (mismo mecanismo que
`parent_identifier_leak`, runs.py:1083-1113) vía `extra_predicates` → inadmisible; `deterministic_checks.attestation_identifier_leak
{value[], state ∈ checked | no-attestations, rule}`. Al panel NO viaja la prosa atestiguada: sólo `deterministic_checks.council`
(conteos, ver (G.6)). A r2/r3 viaja como contexto etiquetado PRIOR ART para que un miembro no exija lo que el humano ya aportó
(su requisito ya es `covered-by-attestation` y no se le envía).

**(G) La corrida — `runs.execute_run`, orden de etapas y el componente gateante.** *(G.1 orden)* `stage.models → stage.plan →
stage.council.ledger` (NUEVO, `agent 'council'`: `{plan_id, ledger.state, n_keep, n_discard, n_aporto, n_hard_rule,
knowledge_now_present, catalog_sha, plan_catalog_matches_run}`) `→ stage.thread_context → retrieve → pass1 → elicit → gate{pass1}`
(runs.py:2395-2421, sin cambio) **`→ council r2`** (`stage.council.round {round 'r2', kind 'coverage', phase 'run'}` + `member` ×N +
`progress` + `stage.council.coverage {phase 'pre-search', must_total, must_uncovered, must_partial, must_not_judged,
n_hallucinated_votes, n_directives}`) **`→ competence.evaluate(..., council_coverage=cov_pre)`** (:2438-2439, la llave YA viaja) `→
stage.competence → [no competente] stage.council.directives {n, families[], n_excluded} → _build_search_plan(…, directives)
(:2487-2489) → stage.search.plan (families_source 'directives+default', n_directives) → Ruta B → stage.path_b → council r3
(condicional, C.7) → stage.council.coverage {phase 'post-search'} → pass2 → elicit → gate{pass2} → panel → revisión`. El
sintetizador es CIEGO al consejo en este ADR: sus criterios y coberturas NO entran a pass2 ni como pista de `gap_flags`; el
consejo mueve la BÚSQUEDA y lo ve el humano (E5). *(G.2 el componente, `competence.py` → `cg-4`)* `council_uncovered_must = {value:
bool|null, must_total, must_uncovered, must_partial, must_not_judged, must_attested, must_discarded, must_unsatisfiable,
n_valid_votes, state ∈ 'checked' | 'vacuous (0 must kept)' | 'incomplete (k/n_eligible < quorum <required>)' | 'not-applicable
(no-ledger)' | 'not-applicable (<otra razón: skipped-by-human | not-requested (…)>)' | 'kill-switch WITT_COUNCIL=0' | 'errored
(<kind>)' | 'vacuous (0 gateable must — n unsatisfiable-by-harness)' *(corrector — el vocabulario CERRADO es
`competence.COUNCIL_COMPONENT_STATES_EXACT` (4) + `COUNCIL_COMPONENT_STATE_PREFIXES = ('incomplete (', 'errored (', 'not-applicable
(', 'vacuous (')` (4, no 2), viaja en `council.vocabulary.competence_component_states`; el literal `incomplete` usa el denominador de
ELEGIBLES (C.3) y el componente copia `round {state, n_valid, n_members, n_eligible, quorum_required,
quorum_required_full_membership}`)*, gating: bool, rule, class 'model-judgment aggregated by code (worst-of-N over
valid votes; hallucinated evidence_id annuls the vote)'}`. **`gating = (WITT_CG_COUNCIL_COMPONENT=1, default) ∧ state ∈ {checked,
vacuous, incomplete}`**; `value = (must_uncovered == 0)` con `checked`; `True` con `vacuous` (0 must kept ES medición: el humano
descartó o atestiguó todo — se declara); **`False` con `incomplete` y `reason 'council-incomplete (k/N < quorum)'`** *(veredicto de
ambos jueces contra D2/D3: competence.py:26-27 — "un componente sin insumo es False con reason, nunca un True vacío"; una ronda que
se intentó y falló es un insumo ausente, no un kill-switch; el costo extra por miembros caídos se MIDE en LG4 y se declara)*;
`no-ledger` / `kill-switch` → `value null, gating false`, FUERA de `conjunction` (declarado) — la conjunción queda EXACTAMENTE la de
`cg-3`. `evaluate()` deja de guardar `received` crudo (:222) y lo interpreta; `COMPONENT_ORDER` no cambia; `compact()` copia el bool;
`config += council_component_gating (+_source)`; `MODULE_VERSION 'cg-4'`. *(C8: alineado al código — `competence.COUNCIL_COMPONENT_STATES_EXACT = ('checked', 'vacuous (0 must kept)', 'kill-switch WITT_COUNCIL=0',
'not-applicable (no-ledger)')` + `COUNCIL_COMPONENT_STATE_PREFIXES = ('incomplete (', 'errored (', 'not-applicable (', 'vacuous
(')`, predicado `council_component_state_in_vocabulary`; el componente lleva además `must_gateable`, `must_covered`,
`must_uncovered_strict`, `n_hallucinated_votes`, `n_requirements_kept`, `round? {state, n_valid, n_members, quorum_required}`,
`reason_gating?`; `config += council_enabled (+_source)`)*. *(G.3 directivas → búsqueda: semántica de UNIÓN)*
`search_harness.build_search_plan(question, entities, pass1_query_en, directives=[…])` CAMBIA cuando hay directivas y
`families=None`: `requested = default_fams ∪ familias de las directivas` con `families_source 'directives+default'` (literal NUEVO; el
smoke asserta que las 5 auto SIGUEN); las `directive-only` nombradas por directiva ENTRAN (`directive_requirement_ids[]` en
`queries[fam]`); para familias `free-query` la `query_en` de la directiva sustituye a `_free_query` (`query_source
'council-directive:<req ids>'`); para familias `symbols` los `symbols` de la directiva se AÑADEN (`symbols_from_directives[]`); para
literatura (`europepmc`/`pubmed`) la directiva queda en `queries[fam].directive_queries[]` y corre como UNA llamada EXTRA dentro
del presupuesto de la familia (`calls[]` la muestra); `directives_state 'provided'`; `plan_event_payload` lleva `families_source` y
`n_directives` (ya existe :380). `normalize_item` y las filas de `run_round` ganan `directive_requirement_ids[]`; el evento
`stage.search.source` también *(veredicto de ambos jueces: verificado en search_harness.py:311-320 — hoy `directives` REEMPLAZA a las
auto; sin la unión, una directiva apagaría europepmc/pubmed/zfin contra ADR-0080 C)*. Sin directivas → plan byte-idéntico al de hoy
(golden) *(C8: alineado al código — `search_harness.FAMILIES_SOURCES = ('default-families', 'directives+default', 'caller')`,
`DIRECTIVE_PLAN_STATES = ('applied', 'excluded-unknown-family', 'excluded-unsatisfiable', 'not-requested (caller families)',
'ignored (no family)')`, `ENTERED_BY = ('directive', 'default+directive', 'caller+directive')`, `QUERY_SOURCE_DIRECTIVE_PREFIX
'council-directive:'`; el plan gana `directives_applied[] {requirement_id, family, state, applied_as[], reason?}`,
`families_from_directives[]`, `n_directives_excluded`, `families_excluded[].requirement_ids?`; las filas de europepmc/pubmed con
`directive_queries` llevan `calls[] {kind 'builder' | 'council-directive', …}`; `runs._build_search_plan(question, entities,
pass1_query_en, cfg, directives=None)`)*. *(G.4 `citations[].pertinent` deja de ser gris)* `verify_output.support_state_for(citations, bundle, grounding=None,
council_pertinence=None)`: con `council_pertinence = {evidence_id: [requirement_id…]}` derivado SÓLO de votos VÁLIDOS de r2/r3 con
`coverage ∈ {covered, partial}`, cada cita resuelta gana `pertinent: true` + `pertinent_to[]` cuando su `resolved_to` está en el
mapa, y **`'not-named-by-council (valid round; no vote cites this id)'` cuando no** *(síntesis: jamás `false` — un miembro sólo
juzga SUS requisitos; que nadie nombrara una cita no niega su pertinencia (ausencia ≠ cero)); sin consejo válido conserva el
literal `'not-available (ADR-0082)'` (ahora con la razón: `'not-available (council <state>)'`) — la escalera NO cambia de peldaños;
`pertinent_source 'council.r2|r3 (covered|partial votes)'`; `citations_support_summary.pertinent` gana `{n_true, n_not_named,
state}` *(C8: alineado al código — `{state 'checked' | <literal not-available>, n_true, n_not_named, n_not_available, literal 'not-available
(ADR-0082)', rule}`; `verify_output.support_state_for(citations, bundle, grounding=None, council_pertinence=None,
council_state=None, …)`)*. *(G.5 `frozen.council`)* ver la forma exacta en (J); `plan_catalog_matches_run`; `rounds[]` con la fila de r1 COPIADA de
`runs.council_json` (`copied_from_plan_id`) y r2/r3 medidas aquí. *(G.6 al panel)* `deterministic_checks.council = {state,
must_uncovered_pre, must_uncovered_post: int|null, n_hallucinated_votes, n_directives, n_requirements_kept, class 'model-judgment
aggregated by code', rule}` (compacto; el juez lo recibe DENTRO de `deterministic_checks` como hoy la competencia — su charge dice
"you are HANDED the deterministic check results", composite_auditor.py:22-23 — con la CLASE al lado para que no lo lea como
medición; el A/B LG4 mide si mueve veredictos) y `attestation_identifier_leak` junto a `parent_identifier_leak`. *(G.7
`agents_invoked`, derivado por CÓDIGO — forma §11 intacta)* una fila por miembro `{agent, status 'invoked', invocation_id
'council:<agent>:r1[+r2[+r3]]', evidence_generated ['requirements:<n>', 'coverage:<c>/<p>/<u>', 'errored:<kind>'?,
'timeout'?]}` (un miembro caído SÍ fue invocado: lo dice su evidence, no se oculta ni gana un literal nuevo — decisión tomada
`status invoked`); fila agregada `{agent '(consejo de criterio — cm-1)', status 'invoked', invocation_id 'council:<n_valid>/<N>',
evidence_generated ['r1:<n_ok>/<N>', 'r2:<n_ok>/<N>', 'requirements:<n_kept>', 'must_uncovered:<n>', 'catalog_sha:<16>']}`;
los 8 operativos → UNA fila `not-applicable` con `reason 'category operations-reporting — not-applicable-by-category (cm-1;
WITT_COUNCIL_FULL=1 los sienta)'` (bajo full-council, filas `invoked`); los 9 de sustrato con su estado real de la tabla (B); un
agente aplicable según el planner que sea MIEMBRO deja de ser `skipped-ad-hoc`. `build_plan` marca `will_run 'council-member'`
(literal NUEVO) y `component 'lib/council.py'` para miembros (:608-619). *(C8: alineado al código — constantes `runs.COUNCIL_AGENT_ROW '(consejo de criterio — cm-1)'`, `COUNCIL_OPERATIVES_ROW '(operativos —
not-applicable-by-category, cm-1)'`, `COUNCIL_SUBSTRATE_ROW '(sustrato — cm-1)'`; por miembro `status 'invoked' | 'not-invoked'`
con `invocation_id 'council:<agent>:r1[+r2[+r3]]' | 'council:<agent>'` y `evidence ['requirements:<n>', 'coverage:<c>/<p>/<u>'?,
'errored:<kind> (<rn>)'?, 'timeout (<rn>)'?, '<skipped-*|not-invoked> (<rn>)'?]` — la llave del contrato §11 es `evidence`, el
borrador escribía `evidence_generated`)*. Bajo `WITT_COUNCIL=0` la fila agregada es `not-applicable`
con `reason 'kill-switch WITT_COUNCIL=0'`; sin plan → `'not-assessed (…)'` como hoy. *(G.8 `epistemic_summary`)* `+= council_state,
council_n_valid, council_n_members, council_must_uncovered (int|null)` (frozen-counter: derivado al congelar, la lista no
re-deriva). *(corrector — UNA verdad para N: `council_n_members` COPIA `frozen.council.n_members`; sin copia del consejo (no
`plan_id`, o plan sin ronda 1) `frozen.council {n_members: null, members: [], full_council: null, quorum_required: null,
membership_source 'not-available (no council copy: membership and N are facts of the plan's round 1, not of this run …)'}` — antes
el frozen congelaba los 17 de la tabla VIGENTE mientras epistemic decía null; con copia (también bajo kill-switch) ambos llevan el N
del plan; medido en `smoke_run_pipeline` (i)/(e)/(a))*. *(G.9 `thread_context.council_summary`, ADR-0079 §8 del brief)* `build_thread_context` añade `council_summary
{requirements[] {requirement_id, gap ≤200, priority, coverage_final, decision, n_requested_by}, flags[], knowledge_now_present,
must_uncovered_post, truncated} | null` (tope 24; *(C8: alineado al código — `council.summary_for_thread(council, cap=24)` añade `coverage_source ∈
post_search | pre_search | none`, `n_total`, `cap`, `source`; la llave `thread_context.council_summary` está SIEMPRE presente,
`null` si el padre no trae `council`*) desde `frozen.council` del padre — el planner (`runs.plan_thread_context`) y la ronda 1 del turno N+1
(`council_jobs._inherited_criteria`) lo reciben como llave hermana estructurada; **el SINTETIZADOR del hijo NO lo recibe**
*(corrector — E5/K.i: `gap` (≤200) y `flags[].statement` son texto escrito por los miembros y `coverage_final`/`decision` son sus
criterios; llegaban a pass1/pass2/revisión dentro de `thread_context` — `execute_run` entrega al sintetizador una copia del
snapshot SIN `council_summary` y lo declara en `frozen.thread.context_delivery.council_summary {present_in_snapshot,
delivered_to_synthesizer false, delivered_to ['planner (…)', 'council round 1 of turn N+1 (…)'], rule}` y en `prompt_components[0]`
("… WITHOUT council_summary (E5 …)"); `frozen.thread_context` conserva el snapshot íntegro (lo que el planner vio); medido en
`smoke_run_pipeline` (m) con un hijo del caso (a))*; la UI "Reforzar la pregunta" precarga los requisitos `∉ {covered, covered-by-attestation}`
como criterios heredados (`inherited_from_run_no`) del nuevo ledger, con keep/discard/aporto. La prosa del consejo NO viaja: sólo
`gap` recortado y estados.

**(H) Gasto — tokens MEDIDOS, USD PROYECTADOS, la caché cotizada, y la ronda 1 de planes nunca corridos visible.**
`TOKEN_STAGES += ('council_r1', 'council_r2', 'council_r3')` (runs.py:1655; el orden nuevo: `plan, council_r1, synthesize_pass1,
elicit_pass1, council_r2, search, council_r3, synthesize_pass2, elicit_pass2, panel, revision, embed`); cada etapa `{in, out,
cache_creation, cache_read, thinking_tokens?, n_members, n_calls (todos los intentos), model, model_source, state ∈ 'measured' |
'copied-from-plan_json' | 'not-run (<reason>)' | 'kill-switch WITT_COUNCIL=0' | 'plan-without-council'}`; *(corrector — el vocabulario CERRADO de `by_stage.council_r*.state` es `council.USAGE_STAGE_STATES_EXACT = ('measured', 'measured
(partial: round cancelled)', 'copied-from-plan_json', 'plan-without-council', 'kill-switch WITT_COUNCIL=0')` +
`USAGE_STAGE_STATE_PREFIXES = ('not-run (',)` — ÚNICA fuente en lib.council (runs.py los re-exporta como
`COUNCIL_USAGE_STAGE_STATES_*`) y viaja en `council.vocabulary.usage_stage_states` para que el gate (F) y la webapp lo tipen; el
literal de la ronda cancelada a medias estaba en el código y en `deviations` pero no en esta lista ni en "tipar y pintar")*; `council_r1` se COPIA de
`runs.council_json.r1.usage` con `source 'plan_json (spent BEFORE enqueue; plan_id …)'` (el gasto ocurrió antes de la corrida: si
no se copia M8 lo pierde; si se suma dos veces miente — regla LOTE-01·A4 aplicada al plan); `by_model[m] += cache_creation,
cache_read` (tokens); **USD** = `in×p_in + out×p_out + cache_creation×p_in×mult_write + cache_read×p_in×0.1` con
`CACHE_MULTIPLIERS` (D.2); `token_usage += cache {creation_input_tokens, read_input_tokens, priced: true, multipliers, source,
as_of}` e `input_tokens_total = input_tokens + creation + read` (`input_tokens` conserva la semántica de la API: el remanente no
cacheado); `_sum` y `by_stage_sum_matches_by_model` siguen comparando `in/out` (regla en `_sum.rule`; la caché se cuadra aparte:
`cache_sum_matches_by_model`); `cost_class` nombra la caché; `plan_judgment` sin cambio; `council_judgment {model, in, out,
cache_creation, cache_read, usd_projected}` aparte (como `plan_judgment`). `_usage_now()` (LOTE-01·A4) incluye las rondas de
consejo YA recogidas cuando la corrida muere/cancela. `GET /usage += plans_council {n_plans, n_unconsumed, input_tokens,
output_tokens, cache, estimated_cost_usd [E], by_state {<council_state>: n}}` = el gasto de rondas 1 de planes que NUNCA se
corrieron (sólo D1 lo veía; sin él M8 no cuadra) — `db.plans_council_usage`; `/usage.by_stage` gana `council_r*` iterando
`TOKEN_STAGES` sin código nuevo (ADR-0081 H). Llamadas ABANDONADAS (timeout/presupuesto/cancelación): `usage null` +
`late_usage_state` + `abandoned_cost_upper_usd [E] = n_threads × attempts_possible × (payload_tokens_est × p_in + max_tokens ×
p_out)` declarado como PROYECCIÓN (la fila jamás dice 0) *(corrector — `attempts_possible = retries + 1`: un hilo abandonado pudo
lanzar todos sus intentos; `{n, attempts_possible, n_calls_upper, usd, class, state, rule, assumptions}`)*.

**(I) `council_index.py` (NUEVO, patrón `precedent.py`) y las puertas `/council/*`.** Corpus = corridas CLOSED de origin
`WITT_COUNCIL_INDEX_ORIGINS` (default `production`; NULL incluido y declarado, `precedent.closed_runs_scoped`) con
`frozen.council` **+ planes con `council_json` de esos orígenes** (un requisito emitido en un plan nunca corrido también es
observación); ítems `kind ∈ requirement {gap, query_en, source_family, priority} | coverage {rationale ≤240, coverage_final} |
decision {requirement_id, decision, gap ≤200 — SIN la razón humana} | gap_flag | alternative | panel_finding
(`runs._panel_findings`, :782) | comment (ADR-0077: {author, created_at, text ≤280})`; TF-IDF sklearn con fallback TF-IDF coseno en stdlib puro (`SCORERS = ('sparse-tfidf', 'stdlib-tfidf-fallback', 'none')`;
*(C8: alineado al código — el borrador decía "token-overlap")*
DECLARADO (`_ensure_index`, :155-172) y llave de caché `(n, frozen_at máx, origins, kinds)`. **`GET /council/search?q=&k=&
include_origins=&kinds=`** → el sobre de `precedent.search` (`scorer, n_runs_indexed, n_plans_indexed, items[] {l (letra), run_id,
run_no, plan_id?, kind, requirement_id?, text, score, admissible_as_evidence: false, why_not_admissible}, origins_included,
excluded_by_origin, kinds_included, corpus_state ∈ indexed | empty-corpus`); *(C8: alineado al código — `council_index.search(q, k=5, include_origins=None, kinds=None, filters=None, env=None)`; el sobre lleva además
`n_runs_council_with_ledger`, `n_runs_council_absent`, `n_plans_excluded_consumed_by_indexed_run` (un plan consumido por una corrida
indexada NO se cuenta dos veces), `plans_state ∈ 'indexed' | 'empty' | 'not-available (plans.council_json column absent — ADR-0082
E.1 pending)'`, `n_comments_indexed`, `n_items_by_kind`, `kinds_available[]`, `filters`, `origin_policy`; errores tipados
`CouncilIndexError(.status 400, .detail)` / `CouncilIndexDisabled(.status 503)` que C6 traduce a `HTTPException`; `INDEX_VERSION
'council-index-1'`; `KINDS` (7), `TEXT_CAPS`, `SEARCH_K_MAX 50`)*; 400 sin `q` o kind fuera del enum; 503 declarado
con `WITT_COUNCIL_INDEX=0`. **`prior_observations[]`** a la ronda 1: top `WITT_COUNCIL_PRIOR_K=5` (clamp 0..12) con letras `P-A…`,
SÓLO campos estructurados y kinds ∈ `WITT_COUNCIL_PRIOR_KINDS` (default `requirement,coverage,decision,gap_flag,panel_finding`;
**`comment` EXCLUIDO del prompt por default** — mitigación de inyección: sólo en la búsqueda, con autor); van en el user message
(no rompen la caché) con la instrucción "prior art, not evidence"; `rounds[0].prior_observations {n, kinds, state ∈ delivered |
empty-corpus | disabled | no-match}` *(C8: alineado al código — `PRIOR_STATES` gana `'no-match'`; `prior_observations(question, k=None,
entities=None, include_origins=None, kinds=None, env=None)` NO lanza; `frozen_index_block(prior) -> frozen.council.index
{index_version, state, prior_observations_n, scorer, origins_included, kinds_included}`)*. Las DECISIONES humanas por `requirement_id` estable quedan consultables ENTRE investigaciones por esta
puerta (kind `decision`) *(hueco de los jueces: Q6 de la auditoría — la primera memoria de política con promoción humana)*.
**`GET /council/membership`** (NO-SPEND, sin BD) → `{membership_version, matrix_version, catalog_sha, catalog_path, n_members,
full_council_env, members[] {agent, category, group, mode, gate, card_sha, card, componentized}, not_applicable_by_category[],
substrate[] {agent, state}, cards_without_row[], rows_without_card[], vocabulary}`. *(C8: alineado al código — = `agent_matrix.membership_view(os.environ) | {'vocabulary': council.council_vocabulary()}`; `members[]` lleva además
`tool`, `hard_rule_gate`, `exploratory`, `from_operative`; la vista trae `catalog_state`, `full_council`, `full_council_source`,
`not_applicable[] {agent, category, state}`, `n_rows 34`, `n_componentized 19`, y app añade `council_version`,
`council_module_state`, `catalog_module_version`, `rules_sha`, `shared_block_sha`, `cache {enabled, ttl, ttl_shared,
min_cacheable_tokens}`, `refreshed_at`)*. **`GET /council/demand`** → `{n_runs_scanned,
n_plans_scanned, n_requirements_unsatisfiable_by_family {web, tooluniverse, figure}, n_runs_with_tooluniverse_uncovered, threshold
{min_runs 5, min_requirements 3, source 'brief §6.3'}, fired: bool, class 'medicion (frozen.council + plans.council_json, origin
production)', rule}` *(C8: alineado al código — `demand(include_origins=None, env=None)` añade `index_enabled`, `n_runs_closed_in_scope`, `n_runs_council_absent`,
`n_runs_council_without_ledger`, `n_plans_excluded_consumed_by_indexed_run`, `plans_state`, `n_units_scanned`,
`n_requirements_scanned`, `n_requirements_unsatisfiable_total`, `n_requirements_harness_state_unsatisfiable` (el `harness_state`
de C2 al lado, nunca fusionado), `by_family_units`, `unsatisfiable_families[]` (derivadas de `SEARCH_DISPATCH` con `fn None`),
`unsatisfiable_evidence_kinds[]`, `fired_by_family {f: bool}` (= `n_units_scanned ≥ min_runs ∧ n_family ≥ min_requirements`);
independiente del kill-switch del índice)* — el criterio de disparo de ADR-0085 calculado por código *(injerto D3; la retro lo lee)*.

**(J) Contrato 1.11 (aditivo), `PLAN_VERSION '4'`, eventos.** `RENDER_CONTRACT_VERSION = "1.11"` (runs.py:50); `PLAN_VERSION =
"4"` (:352). **`frozen.council`** = `{state (C.8), module_version 'council-1', membership_version 'cm-1', membership_source,
catalog_sha, plan_catalog_matches_run: bool|null, rules_sha, tools_sha, model {requested, source, generation, effort,
effort_source}, full_council, n_members, members[] (nombres), quorum_rule, ledger {plan_id, state, approved_by,
approved_by_is_author, approved_at, knowledge_now {present, chars, truncated}, n_requirements, n_kept, n_discarded, n_attested,
n_hard_rule, truncated, n_truncated, requirements[] {requirement_id, gap, evidence_kind, source_family, query_en, variants[],
entities[], entities_resolved[], entities_unresolved[], acceptance_test, priority, priority_downgraded_from?, requested_by[],
n_requested_by, n_members, hard_rule_gate, exploratory, from_operative, harness_state, decision, decision_reason?,
attested_text? (≤600, truncated?), decided_by: string (`DECIDED_BY_PREFIXES`) | null (*corrector* — `null` = `pending` sin gate
humano: borrador o ledger saltado; el fixture `consejo-skip.json` lo trae), decided_at | null}, flags[] {kind, statement, gate
'human', emitted_by}, source} | null,
rounds[] {round ∈ r1|r2|r3, kind ∈ ROUND_KINDS, phase ∈ plan|run, copied_from_plan_id?, n_invoked, n_valid, n_errored, n_timeout,
n_skipped_budget, n_skipped_cancelled, quorum {required, met, ratio, source}, budget_s, elapsed_s, over_budget, stagger_wait_s,
concurrency, abandoned_threads, cache_prefix_identical_across_members: true, members[] (C.3), aggregation_sha?, prior_observations?,
usage {in, out, cache_creation, cache_read, thinking_tokens?}}, coverage {pre_search {state, evidence_view, by_requirement[]
{requirement_id, priority, coverage_final, votes[] {agent, coverage, evidence_ids[], annulled, hallucinated_evidence_ids[],
foreign?}, n_valid_votes}, must_total, must_uncovered, must_partial, must_not_judged, must_attested, must_discarded,
must_unsatisfiable, n_hallucinated_votes, rule}, after_search {state, by_requirement[] {requirement_id, state ∈ retrieved-for |
still-uncovered | not-searched | covered-pre, n_items_retrieved, families[]}}, post_search {…como pre_search…} | {state 'not-run
(<reason>)'}}, directives[] {requirement_id, family, query_en, entities[], symbols[], evidence_kind, priority, requested_by[],
refined_by_members[], state}, directives_state ∈ 'provided' | 'none (all must covered)' | 'not-run', index {state,
prior_observations_n, scorer, origins_included, kinds_included}, cache {enabled, ttl, min_cacheable_tokens 512, r1 {creation,
read}, r2 {creation, read}, r3 {creation, read} | null, hit_ratio_r2: float|null, class 'medicion'}, vocabulary, decided_by 'code
(council.aggregate_*)', kill_switch?}`. *(C8: alineado al código — la FORMA congelada es la que C5 entregó en `runs.execute_run` (contrato 1.11), un SUPERCONJUNTO de la lista de arriba:
`state_reason`, `plan_catalog_sha`, `model {…, effort_pinned, max_tokens}`, `quorum_required`, `plan_id`, `r1_state`, `ledger {…,
approved_by_is_author, skipped_by, skip_reason, knowledge_now {present, text ≤600, chars, truncated, by, at, class 'attested'},
n_pending, requirements[] {…, decision_reason?, attested_text_truncated?, attested_chars?, attested_class?}, requirements_source,
decisions_without_requirement[], text_cap_chars 600}`, `human_attestations {present, n_attestations, knowledge_now_present, delivery
{synthesizer, panel False, council_rounds, present}}`, `rounds_skipped[] {round, reason}`, `coverage.pre_search + round_summary`,
`coverage.after_search + items_rule + n_admitted_total + n_items_considered`, `coverage.post_search + merge_rule +
rejudged_members[] + r3`, `must_uncovered`, `must_uncovered_post`, `must_unsatisfiable`, `directives_excluded[]`, `directives_rule`,
`r3 {state, members[], n_invoked?, n_valid?, round_state?}`, `cache {…, ttl_shared, hit_ratio_rule}`, `usage {r1|r2|r3}`, `config
{recoverage (+_source), concurrency, member_timeout_s, budget_s, quorum, cg_component, r2_evidence_chars}`, `kill_switch
{WITT_COUNCIL: raw, enabled, source}` (SIEMPRE presente), `source`; el keyset exacto lo mide `smoke_run_pipeline.py` y lo tipa la
webapp desde los fixtures 1.11)*. *(corrector — formas que CAMBIAN de dominio: `n_members: int | null`, `members[]` (`[]` sin copia),
`full_council: bool | null`, `quorum_required: int | null` (ceil(q·N) de la membresía; el cuórum MEDIDO de cada ronda va en
`rounds[].quorum` con `n_eligible`), `membership_source` gana el literal `'not-available (no council copy: …)'`;
`coverage.pre_search.round_summary {state, n_valid, n_members, n_eligible, quorum_required (elegibles) | null, quorum_required_full_membership,
quorum_met | null, quorum_rule, n_invoked}`; `rounds[] += n_eligible, cancel_check_errors[], n_cancel_check_errors`; `vocabulary` =
`runs.council_vocabulary_full()` (lib.council + `competence_component_states` + `usage_stage_states` + `quorum_rule`); y fuera del
bloque: `frozen.thread.context_delivery.council_summary {present_in_snapshot, delivered_to_synthesizer false, delivered_to[], rule}`)*. **`competence.components.council_uncovered_must`** (G.2); `competence.module_version
'cg-4'`; `competence.config += council_component_gating (+_source)`. **`deterministic_checks += council`, `attestation_identifier_leak`
(+`_state`, `_rule`)**. **`citations[].pertinent`** (G.4) + `pertinent_to?`, `pertinent_source?`; `citations_support_summary.pertinent`
pasa de literal a `{state, n_true, n_not_named, literal}` (aditivo: el literal viejo sigue dentro). **`search_ledger.plan`**:
`directives[]` (forma C.6), `directives_state 'provided'`, `families_source 'directives+default'` (literal nuevo);
`rows[] += directive_requirement_ids[]`, `query_source 'council-directive:…'`, `directive_queries?`; `search_ledger.n_items_for_directives
{requirement_id: n}`. **`fallback.fb_meta += council {state, must_uncovered_pre, n_directives, families_from_directives[]}`**.
**`token_usage`** (H). **`agents_invoked`** (G.7). **`epistemic_summary`** (G.8). **`thread_context.council_summary`** (G.9).
**`plan` (plan_json v4)**: `plan.judgment.agents_applicable[].will_run += 'council-member'`, `component 'lib/council.py'`. **`frozen.answer`**
no cambia de forma. **Vista `_run_view`** += `plan_council_state: string|null` (derivado de `runs.council_json`, como
`plan_niches`) y `council_n_valid?: int|null`. *(C8: alineado al código — `plan_council_state = runs.council_json.r1_state`, `council_n_valid = runs.council_json.r1.rounds[0].n_valid`; lista y
detalle por la MISMA vista, `smoke_runs_list_http.py` lo mide)*. **Eventos NUEVOS en `run_events` (`agent 'council'`):** `stage.council.ledger`,
`stage.council.round {round, kind, phase 'run', n_invoked, n_eligible, n_valid, n_errored, n_timeout, n_skipped_budget, quorum
{required, met, ratio, n_valid, n_members, n_eligible, n_not_invoked, required_full_membership, state, source, rule}, budget_s,
elapsed_s, over_budget, stagger_wait_s, state ∈ aggregate_states, cancelled}`, `stage.council.member {round, agent, tool, phase
start|done, status?, error_kind?, elapsed_s?, attempt (en AMBAS fases: en curso en start, último en done), attempts? (done: total),
max_attempts, cache_read?, heartbeat: true}` *(corrector — `attempt` faltaba en `done`)*, `stage.council.ledger {plan_id, r1_state,
ledger_state, state ∈ council_states (= r1_state mientras la ronda 2 decide; el centinela interno pending-r2 JAMÁS se escribe),
r2_pending: bool, state_reason, n_requirements, n_keep, n_discard, n_aporto, n_pending, n_hard_rule, knowledge_now_present,
n_attestations, catalog_sha, plan_catalog_matches_run, n_members, membership_source, full_council, membership_version}`
*(corrector — antes congelaba `state 'r2-pending'`, fuera del vocabulario: el gate (F) habría fallado en TODO registro con consejo
aplicable; `smoke_run_pipeline` censa ahora `state` en todos los `stage.council.*`: ledger ∈ council_states, round ∈
aggregate_states, directives ∈ DIRECTIVES_STATES; la ronda r3 caída emite `state 'errored (<Tipo>)'` + `post_search_state`)*, `stage.council.progress {round, n_done, n_pending, elapsed_s,
heartbeat: true}`, `stage.council.coverage {phase, must_total, must_uncovered, must_partial, must_not_judged, n_hallucinated_votes,
n_directives}`, `stage.council.directives {n, families[], n_excluded}`. **Eventos en `plan_events` (`agent 'council'`):**
`council.state {state, plan_id, claimed_by?, reason?}`, `stage.council.round {… phase 'plan'}`, `stage.council.member`,
`stage.council.progress`, `stage.council.aggregate {n_raw, n_dedup, n_requirements, n_must, n_should, n_truncated, n_unsatisfiable,
n_hard_rule, n_flags, catalog_sha, aggregation_sha}`, `council.ledger {approved_by, n_keep, n_discard, n_aporto, knowledge_now_present}`,
`council.skip {by, reason}`, `council.state.conflict {attempted, found, found_error, ignored true, note, plan_id, claimed_by}`
(`level 'warning'`; *corrector E.2* — el worker sobrevivió al veredicto del reaper: el estado terminal no se pisa). **Ampliados:** `stage.search.plan {families_source, n_directives}`; `stage.search.source
{directive_requirement_ids}`; `stage.competence` (el bloque íntegro con el componente nuevo); `stage.plan += council_state`;
`run.state{queued}.council {ledger_present, n_kept, n_hard_rule, r1_state}`. **HTTP nuevo (8 rutas):** `GET /plans/{plan_id}`,
`GET /plans/{plan_id}/events`, `GET /plans/{plan_id}/stream`, `POST /plans/{plan_id}/council/ledger`, `POST
/plans/{plan_id}/council/skip`, `GET /council/membership`, `GET /council/search`, `GET /council/demand`; `POST /runs/plan` responde
`+= council{}`, `reused_from_plan_id?`, `reused_reason?`; `POST /runs` 409 `council_round1_pending` | `council_ledger_unapproved` | `plan_already_used {run_id, cancelled_run_id?}`
*(corrector — el sello comprobado, F.3)*; `POST /runs/plan` `reused_after_planner?: bool` *(corrector — E.3)*;
`GET /usage += plans_council`. **Históricos: NADA se recalcula ni se backfillea** — registros < 1.11 no ganan `council`; la
webapp y el PDF los leen 'NO INSTRUMENTADO (contrato < 1.11)'; planes viejos `council_state 'pre-adr-0082'`.

**(K) Lo que NO se hace y por qué NO es deuda.** (a) Lentes del panel por nicho vía `models.panel(directives)` /
`audit(directives)`: el hook queda `not-available` — literal REAL del código `panel_source.council_hook.state 'not-available
(ADR-0082)'` y `search_ledger.plan.directives_state 'empty-until-ADR-0082'` cuando el consejo aplicó pero compiló 0 directivas
(byte-identidad del golden 1.10; *corrector* — la webapp los GLOSA "lentes por nicho: ADR propio" / "sin directivas del consejo",
jamás "pendiente de ADR-0082": `frozen.council.directives_state` es la verdad del consejo) — una lente más en `_LENS_CHARGES` cambia la
composición del panel y corta la serie de calibración que ADR-0087 segmenta por firma (ADR-0081 A/E); el panel SÍ recibe la
cobertura como insumo determinista (G.6). E6 confirma el diferimiento. (b) Verificador Logic-LM de `causal-pruner`: aquí sólo emite
requisitos con gate humano; el ranking real sigue siendo el agente siguiente (brief §13 fuera de alcance). (c) Pre-warm de la caché
con `max_tokens: 0`: rechazado por la API con `tool_choice {type:'tool'}` y sería gasto sin corrida. (d) Planner asíncrono: LG2 mide
el p95 de `POST /runs/plan`; si rebasa el proxy, es UNA línea más sobre el mismo job. (e) Reintento de CONTENIDO propio del consejo
más allá del del caller: un criterio ilegible es fila `errored` y la ronda sigue con cuórum (17× reintentos no compran nada). (f)
Sonnet en el consejo: palanca declarada (`WITT_MODEL_COUNCIL`), no default — decisión de Emmanuel (§14). (g) `evidence_kind
'figure'`: `unsatisfiable-by-harness` contado hasta ADR-0083. (h) Un enum `evidence_ids` por corrida en el tool (D3): invalida la
caché completa en cada r2; la validación por código anula el voto igual. (i) Sintetizador que lee los criterios no cubiertos
(pista tipada a pass2): cambia lo que el modelo escribe sin held-out — ADR aparte (E5). (j) Comentarios humanos en el prompt de r1:
excluidos por default (E3), sólo en la búsqueda. (k) `WITT_COUNCIL_QUORUM` por ronda distinto: una fracción, declarada. (l) Tabla
`jobs` genérica: `plans` YA es el objeto que el humano aprueba; una cola genérica sin segundo consumidor es abstracción sin dueño.
(m) PDF: la sección "CONSEJO DE CRITERIO" NACE con el bloque (record_pdf.py tras `search_ledger`, :461-464) — regla del brief §18
"cada bloque nuevo nace con su sección"; cero líneas nuevas `[pdf] council` en `parity_debt.json` *(síntesis, D2 sobre D1)*.

**(L) Invariantes operativos y kill-switches.** (1) Toda env implica reinicio (ADR-0081 Context 10); el compose y el README lo
dicen; toda env de la tabla tiene default declarado y lector tolerante en tiempo de llamada. (2) **Kill-switch `WITT_COUNCIL=0`
devuelve el camino de `9d90c01`:** `POST /runs/plan` no encola (`council {state 'disabled (kill-switch WITT_COUNCIL=0)'}`), `POST
/runs` no exige aprobación, `execute_run` no llama a `council` (cero eventos `stage.council.*`, cero llamadas), `competence` recibe
`council_coverage=None` → componente `state 'kill-switch WITT_COUNCIL=0'`, `gating false`, `value null` (fuera de `conjunction`:
la conjunción es la de `cg-3`), `build_search_plan(directives=None)` y `audit(directives=None)` EXACTAMENTE como hoy. El frozen
menos las llaves aditivas 1.11 tiene el keyset Y LOS VALORES de un frozen 1.10 — medido en smoke — con **excepciones DECLARADAS**
(patrón ADR-0081 M.2): (i) `frozen.council {state, kill_switch}`, `deterministic_checks.council {state}`, `deterministic_checks.attestation_identifier_leak
[] + _state 'no-attestations' + _rule` (*corrector* — el fragmento viaja SIEMPRE al panel dentro de `deterministic_checks`, también
bajo kill-switch, con su tres-estados declarado; medido en `smoke_run_pipeline` (e) contra el keyset 1.10 congelado @ 9d90c01 + estas
4 llaves EXACTAS), `token_usage.cache` e `input_tokens_total` existen con estado declarado; (ii) `config_history` gana filas `first-boot-snapshot` para `role.council`,
`council.*` y `stage.models.roles.council` viaja (el rol está en la tabla aunque el consejo esté apagado); (iii) `plans` gana
columnas NULL y `agents_invoked` gana la fila agregada `not-applicable 'kill-switch WITT_COUNCIL=0'`; (iv) `citations[].pertinent`
cambia de `'not-available (ADR-0082)'` a `'not-available (council disabled (kill-switch WITT_COUNCIL=0))'` — el literal viejo
sigue válido en registros ≤ 1.10. `panel_signature` NO cambia (D.2). Los demás kill-switches: `WITT_CG_COUNCIL_COMPONENT=0`
(consejo corre, componente informativo), `WITT_COUNCIL_RECOVERAGE=0` (sin r3), `WITT_COUNCIL_CACHE=0` (system string, A/B),
`WITT_COUNCIL_INDEX=0` (sin índice ni prior observations), `WITT_COUNCIL_FULL=1` (25). (3) Smokes 100% offline: los 17 miembros se
FAKEAN por `caller` inyectado (válidos, duplicados, caídos, con timeout por reloj falso, con ids alucinados, fuera de vocabulario,
con campos prohibidos, con tool equivocado, `not-applicable`); `urllib.request.urlopen` bloqueado y contado (= 0); `mcp_cache`
byte-idéntico; una `.db` SQLite por smoke; SQL de las migraciones compilado para `postgresql` sin funciones exclusivas de SQLite.
(4) Ningún literal de modelo fuera de `models.py` (gate estático M.4 de ADR-0081, intacto). (5) §7: el consejo NO escribe la
respuesta (el sintetizador es ciego a él), NO despacha (las directivas las compila código y `SEARCH_DISPATCH` resuelve el
mecanismo), NO audita (el panel lo recibe como conteos con clase), NO muta la DI (nada escribe en el store), y la ÚNICA puerta
donde su prosa se vuelve gasto es la aprobación humana del ledger; `causal-pruner` no pasa sin decisión explícita. (6) Todo gate
EN VIVO lo corre Emmanuel con `analysis/scripts/smoke_live_council.py`; ningún smoke del CI gasta. (7) Límites del proveedor: el
semáforo acota PETICIONES en vuelo, no tokens/minuto — una ronda r2 son 17 × ≤ 6k tokens de entrada en ráfaga (≤ ~110k ITPM);
se declara y LG5 lo mide; la palanca es `WITT_COUNCIL_CONCURRENCY` y `WITT_COUNCIL_R2_EVIDENCE_CHARS`.

**(M) Integración (C9).** Costuras mínimas, cada una en el archivo del dueño: `frozen.council.catalog_sha ==
runs.council_json.catalog_sha == GET /council/membership.catalog_sha` (misma `catalog_cards.CATALOG_SHA`); `frozen.council.rounds[0].
aggregation_sha == plans.council_json.aggregation_sha`; `stage.council.member` count == `n_invoked` por ronda; `plan_events.seq` y
`run_events.seq` no se mezclan; `frozen.models.roles.council == stage.models.roles.council`; `by_stage.council_r1 ==
runs.council_json.r1.usage`; retirar los stubs que C5/C4 usaron contra las firmas de C2/C3; regenerar la tabla NO-SPEND con
conteos MEDIDOS; correr `tools/parity_check.py` de la webapp EN LECTURA (huecos esperados: 8 rutas `/plans/*`,`/council/*`; llave
`council`; `deterministic_checks.council`; `token_usage.cache`; 6 tipos `stage.council.*`; `[pdf] council` NO debe aparecer);
etiquetar `contract-1.11-frozen`.

## Consequences

- **Contrato: `render_contract_version` sube a "1.11" y `plan_version` a "4"** — todo aditivo (lista en (J)). Ninguna llave cambia de
  dominio salvo `competence.components.council_uncovered_must` (de `{value null, state, gating false}` a la forma de G.2 — el
  literal `'not-available (ADR-0082)'` desaparece de las corridas nuevas), `citations[].pertinent` (gana `true` y dos literales
  con razón) y `PlanAgent.will_run` (gana `'council-member'`). `FALLBACK_TRIGGERS` intacto (gate (E) de paridad sin cambio).
- **La webapp debe tipar y pintar** (`witt-webapp/src/api/types.ts`, todo `?`; tres estados: ausente = contrato anterior, `null` =
  declarado, valor): **(1)** `client.ts`: `planDeCorrida` devuelve `PlanRespuesta.council?`, `reused_from_plan_id?`; NUEVAS
  `planDeclarado(planId)` → `GET /plans/{id}`, `eventosDePlan(planId, after)`, `streamDePlan(planId, onEvent)` (la MISMA máquina que
  `streamEventos` :411: SSE + fallback a polling), `aprobarLedger(planId, body)`, `saltarConsejo(planId, reason)`,
  `membresiaDelConsejo()`, `buscarConsejo(q, k, kinds, includeOrigins)`, `demandaDelConsejo()`; errores tipados POR RUTA, `detail.state` como union CERRADO *(corrector — la lista original omitía la mitad de los literales
  reales)*: `POST /runs` 409 `plan_already_used {run_id, cancelled_run_id?} | council_round1_pending | council_ledger_unapproved`, 404
  `plan_id no existe` (string); `POST /plans/{id}/council/ledger` 404 `plan_not_found`, 409 `council_not_terminal |
  plan_already_used | council_ledger_not_applicable`, 400 `hard_rule_requirements_undecided | unknown_requirement_id |
  duplicated_requirement_id | invalid_decision (+allowed[]) | discard_without_reason | aporto_without_text | attested_text_too_long
  (+max_chars, max_chars_source) | knowledge_now_too_long (+max_chars, max_chars_source)`, 503 `council-db-unavailable {missing[]}`;
  `POST /plans/{id}/council/skip` 404 `plan_not_found`, 409 `council_not_terminal | plan_already_used | council_ledger_not_applicable`,
  400 `skip_without_reason`, 503 `council-db-unavailable`; `GET /plans/{id}` 404 `plan_not_found`; `/events` y `/stream` 503
  `council-db-unavailable`; `GET /council/search` 400 `q must be non-empty` (string) | `invalid-kind {invalid[]}` | `invalid-filter`,
  503 `council-index-disabled`; `POST /runs/plan` 200 `plan_response 'created' | 'reused'` (+`reused_after_planner`). El gate (A) exige consumidor fuera de `client.ts` para las
  8 rutas. **(2)** `types.ts`: `PlanRespuesta.council?`, `PlanAgent.will_run += 'council-member'`, `PlanDeclarado.plan_version '4'`;
  `PlanDeclaradoView` (GET /plans/{id}); `CouncilBlock` = forma EXACTA de (J) con unions CERRADOS (`CouncilState` por exacto +
  prefijo, `CouncilMemberStatus`, `CoverageFinal` (6), `LedgerDecision` (4), `DirectiveState` (3), `RoundKind`) SIN escape `(string
  & {})` — el gate (F) los compara con `council.vocabulary`; `RegistroCongelado.council?`; `CompetenceCouncilComponent` pasa a
  `{value: boolean|null, must_total?, must_uncovered?, …, state, gating: boolean, rule?, class?}` (`state` por literal exacto —
  `competence.COUNCIL_COMPONENT_STATES_EXACT`: `'checked' | 'vacuous (0 must kept)' | 'kill-switch WITT_COUNCIL=0' | 'not-applicable
  (no-ledger)'` — o por los CUATRO prefijos `'incomplete (' | 'errored (' | 'not-applicable (' | 'vacuous ('`; *corrector* — el código
  emite `'not-applicable (skipped-by-human)'`, `'not-applicable (not-requested (judgment errored))'` y `'vacuous (0 gateable must —
  …)'`; la fuente para el gate (F) es `council.vocabulary.competence_component_states`); `DeterministicChecks.council?`, `attestation_identifier_leak?` (+`_state`);
  `Citation.pertinent: true | string`, `pertinent_to?`, `pertinent_source?`; `CitationsSupportSummary.pertinent` objeto;
  `SearchPlan.directives: CouncilDirective[]`, `SearchPlanEventPayload.families_source += 'directives+default'`,
  `SearchSourceRow.directive_requirement_ids?`; `FbMeta.council?`; `TokenUsage.by_stage.council_r1/r2/r3?` con `state` = union CERRADO desde `council.vocabulary.usage_stage_states` (5 exactos incl.
  `'measured (partial: round cancelled)'` + prefijo `'not-run ('`; *corrector*), `TokenUsage.cache?`,
  `input_tokens_total?`, `council_judgment?`; `UsageByModel.cache_creation?/cache_read?`; `EpistemicSummary.council_state?,
  council_n_valid?, council_n_members?, council_must_uncovered?`; `RunView.plan_council_state?, council_n_valid?`;
  `RunStateEventPayload.council?`; `UsageResponse.plans_council?`; `ThreadContextSnapshot.council_summary?`; payloads
  `CouncilLedgerEventPayload, CouncilRoundEventPayload, CouncilMemberEventPayload, CouncilProgressEventPayload,
  CouncilCoverageEventPayload, CouncilDirectivesEventPayload, PlanEvent` (`plan_events`: `council.state`, `stage.council.aggregate`,
  `council.ledger`, `council.skip`); `CouncilMembership`, `CouncilSearch`, `CouncilDemand`. **(3) M3 Preguntar** (`Preguntar.tsx`
  card `plan-card` :743, bajo `plan-agentes` :797): sección NUEVA **CONSEJO** (`data-testid="plan-consejo"`) con placa de estado del
  job (`queued | running · k de N respondieron · latido por miembro desde el SSE de plan` — filas `plan-consejo-miembro-<agent>`;
  `disabled | not-requested (…)` en gris declarado; `incomplete | errored` como placa, jamás check verde), la **tabla del LEDGER**
  (`plan-ledger`, filas `ledger-req-<id>`) ordenada must > should: gap (primer texto; `variants` plegadas) · evidence_kind ·
  source_family (cintillo "no alcanzable por el harness" con `harness_state`) · **pedido por k de N** (k y N del servidor; regla 1
  de la casa: ausencia ≠ 0) · `hard_rule_gate` como placa §7.1 "requiere TU decisión explícita" (ámbar, sin default) ·
  `exploratory` · `from_operative` · controles por fila (`ledger-decision-<id>`) **keep / discard (razón obligatoria) / yo lo
  aporto (texto atestiguado, clase atestiguada)** · banderas de `regulatory-ethics-advisor` como placas §7 con gate humano; campo
  **"qué sabes ahora"** (`ledger-know-now`); `truncated` visible ("24 de 30; 6 fuera por tope"); las **`clarifying_questions`
  del planner y los requisitos del consejo se muestran JUNTOS bajo "lo que acota esta corrida"** (brief §10; hueco de los jueces);
  **COSTO PROYECTADO del turno ANTES de correr** (`plan-costo-turno`): `council_r1` MEDIDO (usage del job, con caché) + `council_r2`
  PROYECTADO con supuestos visibles + `estimates` de hoy → "turno ≈ USD x–y [E]"; el botón **Correr queda DESHABILITADO** con el
  motivo del 409 hasta **Aprobar ledger** (un clic "keep todo" salvo los `hard_rule` pendientes, que bloquean Aprobar con la lista)
  o **Saltar consejo (razón)**; línea "Método: Hybrid — tú decides los turnos, el sistema ejecuta ≤ 2 rondas". `plan-agentes`
  pinta `will_run 'council-member'` distinto de `skipped-ad-hoc` ("miembro del consejo (tabla cm-1)"). Al llegar desde "Reforzar la
  pregunta", la card precarga `thread_context.council_summary` como criterios heredados (`inherited_from_run_no`). **(4) M3 Traza**
  (`Traza.describir` :818): casos NUEVOS `stage.council.ledger` ("ledger del consejo · 12 requisitos · 9 keep · 2 discard · 1
  aportado · qué sabes ahora: sí"), `stage.council.round` ("ronda r2 · 15/17 válidos · quórum 11 · 48 s"), `stage.council.member`
  (fila por miembro como `stage.audit.judge` :1061: agente · inicio / ok / `error_kind` glosado por vocabulario · segundos ·
  "cuenta como latido" · "intento N de M"), `stage.council.progress` ("latido · 9/17 listos"), `stage.council.coverage` ("cobertura
  pre-búsqueda: 2 must sin cubrir · 1 voto anulado"), `stage.council.directives` ("3 directivas → openalex, monarch, string");
  `stage.search.plan` glosa `families_source 'directives+default'` como "lo pidió el consejo + las 5 de siempre" y
  `stage.search.source` pinta "lo pidió el consejo · req-xxxx"; `stage.competence` pinta el componente del consejo con `gating`;
  `stage.plan` += "consejo: queued|…". La Traza del PLAN (nueva vista mínima embebida en la card) lee `plan_events` con los MISMOS
  casos y `phase 'plan'`. **El gate (C) FALLA si falta cualquier caso `stage.council.*`.** **(5) M4 Hoja**: Entrada NUEVA
  **"Consejo"** (tres estados: ausente = 'NO INSTRUMENTADO (contrato < 1.11)'; `state` declarado; valor): membresía (cm-1,
  `catalog_sha` con enlace a `/council/membership` — la ficha VERBATIM que obedeció el agente —, N, full_council,
  `plan_catalog_matches_run`), modelo `{requested, source, effort}`, ledger con decisiones y `decided_by` (humano vs `default-keep`
  vs `gate-human-pending`, autor y hora; `approved_by_is_author`), "qué sabes ahora" como bloque ATESTIGUADO fuera de la
  evidencia, **tabla de cobertura** pre/post por requisito (`coverage_final` con 6 literales; `votes[]` con `evidence_ids` como
  enlaces a la Entrada de evidencia; votos `annulled` en rojo con sus `hallucinated_evidence_ids`; `not-judged` en ámbar;
  `after_search` "retrieved-for ≠ covered", dos palabras), directivas compiladas y excluidas, rondas con `n_valid/N`, cuórum,
  miembros `errored/timeout`, caché medida (creation/read por ronda, `hit_ratio_r2`), `abandoned_threads` y
  `abandoned_cost_upper_usd [E]`; `[hoja-competencia] FilaComponente` (:3758-3806) pinta `council_uncovered_must` con
  `must_*` desglosados — check/X REAL sólo cuando `gating true` y la compuerta decidió; `state` kill-switch/no-ledger como null
  declarado; `deterministic_checks.council` y `attestation_identifier_leak` junto a `parent_identifier_leak`; `citations[].pertinent
  true` retira el gris fijo y `'not-named-by-council (…)'` se glosa "ningún miembro la nombró — no es negación"; Entrada Método
  (`AgentesInvocados` :2572): fila `council:n/N` primero, filas `invoked` por miembro con su evidence, los 8 `not-applicable`
  plegados; Entrada Costo: renglones `council_r1` ("copiado del plan"), `r2`, `r3` con in/out/cache y USD [E] por multiplicadores
  declarados, `input_tokens_total ≠ input_tokens` explicado; `panel_source.council_hook` sigue en gris "lentes por nicho: ADR
  propio". **(6) M3 ListaCorridas / Banco**: columna "consejo" desde `epistemic_summary.council_n_valid/council_n_members ·
  council_must_uncovered` y `plan_council_state` (0 ≠ null; 'sin consejo' declarado). **(7) M6 Bitácora** (`Bitacora.tsx`
  pestañas :70-104): pestaña NUEVA **CONSEJO** → `GET /council/search` (caja `q`, `kinds` con `comment` opcional, `include_origins`;
  ítems en letras con `kind`, `run_no`/`plan_id`, `scorer` declarado, `admissible_as_evidence false` como cintillo estructural;
  `corpus_state 'empty-corpus'` como placa) + sub-bloque **Membresía** (`GET /council/membership`: 17 por grupo con `mode`, `gate`,
  `card_sha`; 8 not-applicable; 9 sustrato con estado; 3 sin ficha; 5 fichas sin fila = 0 tras C1) + placa **Demanda del sidecar**
  (`GET /council/demand`: `fired`, conteos, umbral, clase). **(8) M8 Consumo** (`Consumo.tsx` :640-655): filas `council_r1/r2/r3` en
  la tabla por etapa con columnas caché (creation/read) y glosa "leídos de caché (0.1×) / escritos (1.25×)"; `plans_council` como
  bloque aparte ("rondas 1 de planes nunca corridos: N planes · USD [E]"); `models_catalog` gana el rol `council`. **(9)
  Investigación** ("Reforzar la pregunta", `Preguntar.tsx` :553-620): criterios heredados con `inherited_from_run_no` y placa
  "Turno N de T-xxxx · k must sin cubrir". **(10) PDF** (`record_pdf.py`, dueño backend — C5): sección **"CONSEJO DE CRITERIO"**
  (membresía/versión, ledger con decisiones, cobertura pre/post, rondas n/N, catalog_sha, costo r1/r2/r3) NACE con el bloque; sin él
  → 'NO INSTRUMENTADO (contrato < 1.11)'. **(11) `gen_fixtures.py`**: `CONTRATO = "1.11"`; quitar del proceso las 27 env nuevas
  (patrón `ENV_ADR_0081`, gen_fixtures.py:143-144); fixtures NUEVOS abajo. *(corrector — la receta COMPLETA que el generador
  necesita, evaluada en LECTURA sobre `witt-webapp/tools/gen_fixtures.py` @ `3236aca`: (a) `correr()` hoy arma el plan con
  `runs_mod.build_plan` + `new_run(plan_json=)` SIN fila en `plans` — así TODA corrida nacería `'not-applicable (no-ledger)'`; para
  los fixtures con consejo debe pasar por `TestClient POST /runs/plan` bajo `WITT_RUN_ORIGIN=fixture` + `WITT_COUNCIL_ORIGINS=fixture`
  (encola) → `db.claim_next_council_plan(worker_id, plan_id=)` → `council_jobs.execute_round1(row, caller=<fake de 17>)` (job r1
  llamable en sincrónico; el fixture `plan-eventos-consejo.json` nace de AQUÍ, no de una receta a mano) → `POST
  /plans/{id}/council/ledger` (o `/skip`) → `POST /runs {plan_id}` → `runs.execute_run(run, synthesizer=, panel_caller=,
  council_caller=<fake>)`; (b) tres asserts 1.10 que la forma 1.11 rompe: `set(m["roles"]) == {synthesizer, elicitation,
  question_agent, planner}` (ahora incluye `council`), `council_uncovered_must == {value None, state 'not-available (ADR-0082)',
  gating False}` (ahora la forma G.2) y `CONTRATO`; (c) los 17 fakes se inyectan SÓLO por `caller` (cero red) y las 27 env se quitan
  solas porque ya están en `models.ENV_TABLE`; (d) nuevos fixtures de este corrector: `consejo-tres-duenos.json` (3 dueños → applicable
  → competente), `plan-eventos-consejo-conflict.json` (`council.state.conflict`), `plan-respuesta-reused-after-planner.json`)*. **(12) `tools/parity_check.py`**: superficies (A) 8 rutas, (B) `council`,
  `deterministic_checks.council`, `token_usage.cache` congeladas → tipadas → leídas en Hoja Y PDF, (C) 6 tipos `stage.council.*` + nueva
  sub-superficie `plan_events` ↔ casos, (D) PDF sin deuda nueva, (E) `FALLBACK_TRIGGERS` sin cambio, **(F) NUEVA `council.vocabulary`** (= `runs.council_vocabulary_full()`, la MISMA que sirve `GET /council/membership`):
  `COUNCIL_STATES_*`, `MEMBER_STATES`, `COVERAGE_STATES`, `DECISION_STATES`, `DIRECTIVE_STATES`, `DECIDED_BY_PREFIXES`,
  `usage_stage_states` (`by_stage.council_r*.state`), `competence_component_states` (cg-4), `aggregate_states` (`stage.council.round.state`)
  *(corrector)* vs los unions de `types.ts` (sin escape) vs TODOS los fixtures (`council.state`, `members[].status`, `coverage_final`,
  `decision`, `stage.council.*.payload.state` POR TIPO: `ledger` → `council_states`, `round` → `aggregate_states`, `directives` →
  `directives_states`; `by_stage.council_r*.state`; `competence.components.council_uncovered_must.state`) — patrón
  `plan_state_in_vocabulary`; `decided_by` admite `null`.
- **Qué mide el gate de paridad tras 0082:** 0 rutas nuevas sin consumidor; 0 llaves de `frozen.council` / `deterministic_checks.
  council` / `by_stage.council_*` / `token_usage.cache` sin tipo ni lector; 0 eventos `stage.council.*` / `council.*` sin voz; 0
  literales de estado del consejo fuera de los vocabularios (fixtures incluidos); la sección PDF presente (ninguna línea `[pdf]
  council` en `parity_debt.json`); y la regla nueva: cada `CouncilRequirement` del fixture pinta "k de N" sin inferirlo (k y N vienen
  del servidor).
- **Protocolo de corte con la webapp (otro workflow en paralelo):** la FORMA de (C)–(J) se congela al cerrar C1/C2/C3 (commit del
  integrador con etiqueta `contract-1.11-frozen`); la webapp regenera `gen_fixtures.py` contra ESE SHA; hasta entonces su gate corre
  contra `9d90c01`. Ningún cambio de forma después de C9 sin corrector declarado.
- **Deuda declarada aquí, no en la lista de gates en vivo:** las lentes del panel por nicho (K.a) → ADR propio; `figure` (K.g) →
  ADR-0083; `web`/`tooluniverse` → ADR-0084/0085 con `GET /council/demand` como criterio; la pista tipada al sintetizador (K.i) →
  ADR con held-out; el planner asíncrono sólo si LG2 lo pide.
- **Riesgos** (con mitigación y dueño): **R1** Fricción del gate humano — cada pregunta con plan exige aprobar o saltar el ledger
  (409): un clic "keep todo" salvo `hard_rule`; skip con razón; `WITT_COUNCIL=0` restaura el flujo de hoy; si Emmanuel lo percibe como
  freno, la retro decide (E4), no el código. **R2** El consejo también es LLM (calibración, faithfulness): pide y verifica contra
  ids; un id inventado anula el voto; nunca escribe la respuesta ni decide el despacho; la verdad sigue saliendo del gate
  determinista, el panel y el cierre humano. **R3** 429 del proveedor con 17 concurrentes × 2 workers × panel: semáforo de proceso
  (8), escalonado, `Retry-After`, miembro caído = fila `errored`, ronda válida ≥ 60 %; `incomplete` → no competente (conservador) y
  se declara; LG5 lo mide bajo carga. **R4** Hilos huérfanos tras timeout/presupuesto/cancelación (urllib no se cancela): ocupan un
  permiso del semáforo hasta que el socket expira (≤ 120 s); `abandoned_threads` y `abandoned_cost_upper_usd [E]` declarados; el
  proveedor cobra hasta `max_tokens` y M8 NO lo ve — se dice, no se esconde. **R5** Caché neutra en un turno aislado (la puerta
  humana excede el TTL de 5 min): r1 y r2 escriben; el ahorro real es el prefijo compartido leído 16× por ronda (~0.17 USD/ronda
  [E]) y campañas (A/B, replays); jamás se afirma ahorro sin `cache_read_input_tokens` medido (LG1/LG3); palanca
  `WITT_COUNCIL_CACHE_TTL=1h` (E3). **R6** Caché silenciosamente inactiva (prefijo < 512 tokens; bloque A con fecha; tools en
  otro orden; `effort` variable): `build_system` es una función pura sin timestamps; `TOOLS` es tupla fija; `effort` pinneado por
  ruta; LG1 mide `count_tokens` del prefijo y `cache_read > 0`. **R7** Deriva de fichas: `CATALOG_SHA` viaja en cada corrida y
  `plan_catalog_matches_run` lo compara; el golden detecta una edición de un byte. **R8** Inyección vía índice: comentarios
  excluidos del prompt por default, tope de ítems, sólo texto ≤ 280 con autor, etiquetados "prior art, not evidence". **R9**
  Lavado de prosa atestiguada como evidencia: `human_attestations` FUERA del objeto gateado + cláusula anti-fuga + predicado duro
  `attestation_identifier_leak`. **R10** Un must `unsatisfiable-by-harness` dejaría la rama competente constante-falsa: se cuenta
  (`GET /council/demand`) y NO gatea (E1). **R11** Cobertura worst-of demasiado severa → más "no competente" → más búsquedas y
  pass2: rondas ≤ 2, `WITT_CG_COUNCIL_COMPONENT=0` informativo, A/B descriptivo (LG4); la regla es un literal congelado que un ADR
  posterior puede cambiar sin reescribir registros. **R12** Costo ×8–20 por turno frente a los 0.208 USD medidos hoy: nunca capado
  (ADR-0047 d.3), medido por etapa con caché aparte, kill-switches por componente, `WITT_COUNCIL_EFFORT` como palanca del pensamiento;
  E6 registra la aprobación presupuestal. **R13** Doble clic / fixtures / dev-offline disparando r1: dedup por ventana, tope por
  usuario, `WITT_COUNCIL_ORIGINS`. **R14** Postgres: ALTERs con tipos-fecha por dialecto (lección ADR-0078), `plan_events` por
  `create_all`; el smoke compila el SQL para `postgresql`; LG8 mide el redeploy. **R15** Matriz v1.3 con 5 filas nuevas cambia
  `digest()` y el planner puede juzgar más agentes aplicables: `PLAN_VERSION '4'` lo declara; LG4 mide `n_agents_applicable`.
  **R16** `plan_events` y `run_events` con dos escritores lógicos (worker del consejo + corrida) sobre SQLite: eventos sólo desde
  hilos orquestadores; tablas distintas; Postgres en prod no tiene el límite.

## Tabla de env (todas con default declarado; lectores tolerantes en tiempo de llamada; toda env = reinicio)

| Variable | Default | Lector | Efecto / fuente declarada |
|---|---|---|---|
| `WITT_COUNCIL` | `1` | `council.enabled` · `app.create_plan` · `runs.execute_run` | kill-switch global: `0` = sin job en el plan, sin r2/r3, componente `state 'kill-switch WITT_COUNCIL=0'` (`gating false`), `build_search_plan(directives=None)`, camino `9d90c01` con las excepciones de (L.2) |
| `WITT_COUNCIL_FULL` | `0` | `agent_matrix.council_members` (al ENCOLAR r1; la corrida usa la N congelada en el plan) | `1` = los 8 operativos también se sientan (N=25, cuórum 15); requisitos `from_operative` contados aparte |
| `WITT_MODEL_COUNCIL` | vacía → `claude-opus-5` (g2) · `claude-opus-4-8` (g1) | `models.resolve_role('council')` | modelo de los miembros; fuente en `frozen.council.model.source`; `fable` rechazado `excluded-model`; tope `max_tokens.council` 4000/1200 |
| `WITT_COUNCIL_EFFORT` | `medium` (`inherit` = hereda `WITT_ANTHROPIC_EFFORT`; vacía = `medium`) *(C8: alineado al código)* | `models.council_effort` → `council.build_request` | `output_config.effort` FIJO por ruta para las 3 rondas (cambiarlo por petición invalida la caché); sólo a modelos `adaptive`; E2 |
| `WITT_CG_COUNCIL_COMPONENT` | `1` | `competence.env_config` | `1` = `council_uncovered_must` GATEA cuando `state ∈ {checked, vacuous, incomplete}`; `0` = informativo declarado (fuera de `conjunction`) |
| `WITT_COUNCIL_RECOVERAGE` | `1` | `runs.execute_run` | `1` = ronda r3 (sólo si `n_admitted_total > 0`, sólo dueños de must sin cubrir); `0` = `post_search.state 'not-run (kill-switch …)'` |
| `WITT_COUNCIL_ORIGINS` | `production` | `app.create_plan` · `council_jobs.council_origins` → `db.claim_next_council_plan(origins=)` (CSV tolerante; `all` = sin filtro declarado) *(C8: alineado al código — el worker también filtra al RECLAMAR)* | orígenes del PROCESO que encolan r1; `smoke/fixture/dev-offline` → `'not-requested (origin …)'` |
| `WITT_COUNCIL_WORKERS` | `1` | `runs.start_council_workers` → `council_jobs.start_council_workers` → `worker_loop` *(C8: alineado al código)* | hilos daemon `council-worker-N` que reclaman `plans.council_state='queued'` |
| `WITT_COUNCIL_DEDUP_S` | `600` | `app.create_plan` | ventana del dedup del doble clic (misma pregunta+entidades+padre, mismo usuario, r1 `queued|running` → se reutiliza el plan vivo) |
| `WITT_COUNCIL_MAX_QUEUED_PER_USER` | `3` | `app.create_plan` | tope de jobs r1 `queued` por usuario; el excedente nace `'not-requested (queue-cap per user)'` |
| `WITT_COUNCIL_CONCURRENCY` | `6` | `council.run_round` (clamp 1..25) | `max_workers` del pool por ronda; el miembro #1 va SOLO y el resto tras su respuesta |
| `WITT_COUNCIL_MEMBER_TIMEOUT_S` | `120` | `council.run_round` · `council.socket_timeout_s` | ventana del ORQUESTADOR por miembro (vencida → fila `timeout`, la ronda sigue); el socket del caller por intento es `max(10, (M − 2·retries) // (retries+1))` = 59 s con los defaults *(corrector: antes socket == M y el reintento por timeout era una llamada fantasma)* |
| `WITT_COUNCIL_ROUND_BUDGET_S` | `300` | `council.run_round` | presupuesto de reloj por ronda; agotado → `skipped-budget` (cero llamadas), en vuelo abandonados y contados; regla `≤ WITT_REAP_STALE_S − 300` |
| `WITT_COUNCIL_MEMBER_RETRIES` | `1` | `council.run_round` → `_anthropic_tool_call(retries=)` | intentos ADICIONALES por miembro (transporte con `Retry-After`; contenido); `refusal`/4xx nunca; `attempts ≤ 2` |
| `WITT_COUNCIL_QUORUM` | `0.6` | `council.quorum_required` (vía `council.config`) *(C8: alineado al código)* | fracción de miembros válidos sobre los ELEGIBLES de la ronda (`ceil(q·n_eligible)`: r1 17 → 11, 25 → 15; r2/r3 sobre los dueños de requisitos kept — *corrector*); fuera de (0,1] → default declarado |
| `WITT_COUNCIL_MAX_REQUIREMENTS` | `24` | `council.aggregate_r1` (alias `aggregate_requirements`) | tope del ledger; `truncated`, `n_truncated`, `truncated_ids[]` |
| `WITT_COUNCIL_MAX_PER_MEMBER` | `5` | `council.validate_tool_input` (el `maxItems 5` del schema es CONSTANTE: identidad de la caché) *(C8: alineado al código)* | requisitos por miembro; excedente descartado en orden y contado |
| `WITT_COUNCIL_R2_EVIDENCE_CHARS` | `24000` | `council.payload_r2` | tope de la vista de evidencia por miembro en r2/r3; `payload_truncated` declarado; acota tokens/min |
| `WITT_COUNCIL_ATTESTATION_CHARS` | `4000` | `app` (ledger) · `council.apply_ledger_decisions` | tope de `knowledge_now` y de cada `attested_text` (600 en el frozen, `truncated`) |
| `WITT_COUNCIL_CACHE` | `1` | `catalog_cards.cache_config` → `council.build_system` | `1` = `cache_control` en los dos bloques `system`; `0` = string concatenado (A/B medible en `usage.cache_*`) |
| `WITT_COUNCIL_CACHE_TTL` | `5m` | `catalog_cards.cache_config` → `council.build_system` | `5m` (escritura 1.25×) · `1h` (2×) para el bloque de la ficha; con `1h` el bloque A también va `1h` (regla de la API) *(C8: alineado al código)*; E3 tras medir el hueco r1→r2 |
| `WITT_COUNCIL_INDEX` | `1` | `council_index` · `app` | `0` = `GET /council/search` 503 declarado, `prior_observations {state 'disabled'}` |
| `WITT_COUNCIL_PRIOR_K` | `5` | `council_index.prior_observations` (clamp 0..12) | observaciones previas inyectadas en r1 (letras `P-A…`); `0` = ninguna |
| `WITT_COUNCIL_PRIOR_KINDS` | `requirement,coverage,decision,gap_flag,panel_finding` | idem (CSV tolerante) | kinds que ENTRAN al prompt de r1; `comment` EXCLUIDO por default (inyección); la búsqueda siempre puede pedirlo |
| `WITT_COUNCIL_INDEX_ORIGINS` | `production` | `council_index` · `/council/demand` | orígenes del corpus (NULL incluido y declarado, regla de `precedent`) |
| `WITT_ANTHROPIC_MAX_INFLIGHT` | `8` | `composite_auditor._anthropic_tool_call` | `BoundedSemaphore` de PROCESO alrededor de `urlopen` para TODA llamada Anthropic; `meta.queue_wait_s` |
| `WITT_ANTHROPIC_RETRY_AFTER_CAP_S` | `30` | `composite_auditor._anthropic_tool_call` | tope al `Retry-After` honrado en `http-429/529`; sin cabecera, backoff de hoy |
| `WITT_REAP_STALE_S` | `900` (ya existe) | `runs.reaper_loop` · `council_jobs.reap_stale_s_of` → `council_jobs.reaper_loop` → `db.reap_stale_council_plans` *(C8: alineado al código — hilo propio `council-reaper`)* | sin cambio; el mismo umbral siega jobs de plan huérfanos |

## Gates NO-SPEND (máscara de siempre: `WITT_BACKEND_DB_URL` sqlite tmp · `NEO4J_URI=''` · `RAG_BACKEND=sparse` · `OPENAI_API_KEY=''` · `ANTHROPIC_API_KEY=''` · `WITT_RUN_ORIGIN=smoke`; venv `dev/.venvs/witt-query-service`)

| Gate | Hoy (medido 2026-09-15 @ 9d90c01) | Tras ADR-0082 | Qué MIDE de nuevo |
|---|---|---|---|
| `smoke_catalog_cards.py` (NUEVO) | — | **57/57** | 31 fichas; 17 miembros ∈ CARDS; sha == sha256 del substring exacto; `CATALOG_SHA` estable ×2; un byte en `causal-pruner` cambia SÓLO su sha + el global; sufijos normalizados (3); obligatorios 31/31, opcionales ausentes = ausentes; `category` ∈ 6; sin BD, sin red |
| `smoke_agent_matrix.py` (NUEVO) | — | **46/46** | 34 filas; `category` en todas; `card` en las 3; `COUNCIL_MEMBERSHIP` = 17 nombres exactos del brief con ficha; modos por tabla (human-gated, flags-only, exploratory); 8 operativos; 9 sustrato con estado; `componentized` 19/34; `council_members({})` 17 / `FULL=1` 25 en orden fijo; `digest()` incluye 34 (declarado: cambia); `ENUM ⊇ membership` |
| `smoke_council.py` (NUEVO; caller y reloj INYECTADOS, 0 red) | — | **70/70** (64 de C9 + 6 del corrector: cuórum sobre elegibles r2 (15 → 9) y ronda de 3 dueños → applicable; `cancel_check` con OSError NO cancela; `attempt` en start y done; `abandoned_cost_upper × attempts_possible`; `socket_timeout_s` 59; vocabulario `usage_stage_states`) | (1) 17 fakes ok → quórum, ledger ≤ 24; (2) misma familia con tokens permutados ×4 → 1 requisito `n_requested_by 4`, `variants 3`, query del 1º por tabla; (3) 7 requisitos → 5 + `n_dropped 2`; 17×5 → `truncated 24`; (4) `CallerError http-529` → `errored`, ronda sigue; (5) miembro lento > timeout (reloj falso) → `timeout`; (6) 8/17 caídos → `incomplete`; (7) `source_family 'pubmed-central'` → `off_vocabulary`, ítem descartado; (8) `direct_answer`/`confidence` en la salida → `dropped_fields`, no viajan; (9) `regulatory-ethics` con requisitos → `wrong-tool`; `causal-pruner` → `hard_rule_gate true`; (10) cross-field must → should + `priority_downgraded_from`; (11) `web`/`figure` → `unsatisfiable`, `n_unsatisfiable`; (12) agregar barajado → JSON byte-idéntico; (13) r2: `PMID:999` ∉ bundle → anulado + `hallucinated`; todos anulados → `not-judged` → cuenta como must sin cubrir; id ajeno → `foreign`; (14) covered+partial → partial; (15) `system == [A+§7, ficha]`, `sha256(bloque B) == CARDS[agent].sha` ×17; (16) el fake recibe `tools` byte-idéntico en r1/r2/r3 y `tool_choice` distinto; (17) `cache_control` ×2 con CACHE=1, ausente con 0, `ttl 1h` por env, orden 1h antes de 5m; (18) `usage` con `cache_*` sobrevive; (19) test estático: ningún tool con campos prohibidos, `evidence_ids` sin `enum`; (20) full-council 25 + `from_operative`; (21) escalonado: el #1 arranca y TERMINA antes que el #2; (22) presupuesto 0.5 s → `skipped-budget` sin llamadas, `abandoned_threads` contado; (23) `should_abort` a mitad → `skipped-cancelled` + usage de los recogidos; (24) eventos `on_event` drenados en el hilo llamador (id de hilo medido); (25) `compile_directives` sin `search_directive` → directiva desde el requisito; con él → `refined_by_members`; (26) `coverage_after_search` → `retrieved-for`/`still-uncovered`; (27) `council_vocabulary()` == unions; `urlopen` = 0 |
| `smoke_council_jobs_db.py` (NUEVO) | — | **59/59** (57 de C9 + 2 del corrector: 7g el worker sobrevive a la siega → cierre condicional, `council.state.conflict`, lo gastado se conserva; 7h `update_plan_council(expected_state=)`) | `_migrate` idempotente ×2; planes viejos → `'pre-adr-0082'`; `claim_next_council_plan` atómico (2 hilos → 1 gana); `plan_add_event` seq monotónico + `council_last_event_at`; worker con 17 fakes → `applicable`, `council_json` con `rounds[0]` y requisitos, `aggregation_sha`; persistencia INCREMENTAL (matar tras 9 futures → 9 filas y usage escritos); excepción del worker → `errored (…)`, hilo vivo; reaper: `running` con latido viejo → `errored (worker-lost)` + evento, latido fresco intacto, carrera → rowcount 0; arranque umbral 0 → `worker-lost-restart`; `set_plan_ledger` rechaza tras `mark_plan_used`; `plans_council_usage` suma sólo planes con usage; SQL compilado para `postgresql` |
| `smoke_council_http.py` (NUEVO; `TestClient` sin lifespan; worker a mano con caller fake) | — | **74/74** (69 de C9 + 5 del corrector: 16a borrador tras aprobación limpia `approved_by`; 16b dos POST /runs/plan concurrentes → UN job; 16c `mark_plan_used` False → 409 + corrida cancelled; 16d BD sin migrar → INSERT tolerante; 16e el job REAL vs el worker a mano: mismas formas) | `POST /runs/plan` → `council.state 'queued'` + `poll/stream`; `store-consultation` / `niches []` / `WITT_RUN_ORIGIN=smoke` sin `WITT_COUNCIL_ORIGINS=smoke` → `'not-requested (…)'` y CERO jobs; dedup: 2º POST idéntico en la ventana → 200 con `reused_from_plan_id`, planner fake llamado UNA vez; tope por usuario; `GET /plans/{id}` 401/404/200 y estados; `/events?after=` monotónico; SSE cierra con `event: end`; `POST /runs` antes de terminal → 409 `council_round1_pending`; `applicable` sin aprobar → 409 `council_ledger_unapproved`; ledger con `hard_rule` pending → 400 con ids; `discard` sin razón → 400; `aporto` sin texto → 400; approve → `runs.council_json` compuesto server-side, `plan_json` byte-igual a `plans.plan_json`, `run.state{queued}.council`; `approved_by_is_author` false con otra sesión; skip → `'skipped-by-human'` y corrida OK con ledger vacío declarado; `WITT_COUNCIL=0` → `'disabled …'`, `POST /runs` sin 409; `/council/membership` == tabla + shas; `/council/search` sin `q` → 400, corpus vacío → `'empty-corpus'`, `INDEX=0` → 503; `/council/demand` sobre 6 fixtures → conteos exactos, `fired` false/true con 5; `/usage.plans_council` con plan no consumido; `/plans/*` no captura `/runs/{run_id}` |
| `smoke_council_index.py` (NUEVO) | — | **63/63** (62 de C7 + 1: BD sin migrar simulada → `plans_state 'not-available'`) | 3 corridas closed (2 production, 1 smoke) + 1 plan con `council_json` + comentarios: excluye smoke y lo cuenta; ítems por kind incl. `decision` sin la razón humana; letras `A..`; `admissible_as_evidence false` 100 %; scorer declarado (tfidf | fallback forzado por monkeypatch); `prior_observations` default sin `comment`, k=5; `kinds=comment` los incluye con autor y ≤ 280; corrida sin `council` aporta sólo gap_flags/alternatives/hallazgos; reconstrucción al cambiar la llave |
| `smoke_run_pipeline.py` | 275 (tabla) · **272 medido @ 9d90c01 por C1** | **302/302** (297 de C9 + 5 del corrector: (l) 3 dueños → competente sin ronda; (m) turno N+1: el sintetizador SIN `council_summary`, planner y r1 CON; keyset 1.10 de `deterministic_checks` bajo kill-switch + 4 llaves declaradas; UNA verdad para N (null sin copia); censo de `state` en todos los `stage.council.*`; (c) pasa a `incomplete (7/12 < quorum 8)`) | contrato `'1.11'` en TODAS; orden de la traza: `stage.plan → stage.council.ledger → … → gate{pass1} → stage.council.round{r2} → member ×17 → progress → coverage{pre} → stage.competence → [no competente] stage.council.directives → stage.search.plan {families_source 'directives+default', n_directives ≥ 1, familia directive-only ENTRA, las 5 auto SIGUEN} → stage.path_b → stage.council.round{r3} SÓLO con `n_admitted_total > 0` y `n_invoked < 17` → coverage{post} → pass2`; 1 must uncovered → `competent false`, `reasons ['council_uncovered_must']`; 0 must sin cubrir + resto True → competente, sin ronda; `incomplete` → `False` + `reason 'council-incomplete…'`, revisión NO disparada por eso; `vacuous` → True declarado; `frozen.council` completo con `plan_catalog_matches_run`; `by_stage.council_r1 'copied-from-plan_json'` == `runs.council_json.r1.usage`, `r2/r3` medidas con caché; `by_stage_sum_matches_by_model` y `cache_sum_matches_by_model` true; USD > costo sin caché en el mismo fixture (multiplicador aplicado); `agents_invoked`: 17 `invoked`, `council:17/17`, ningún miembro `skipped-ad-hoc`, miembro caído `invoked` + `errored:<kind>`; id alucinado → visible en frozen y `deterministic_checks.council.n_hallucinated_votes`; `attested_text` con `ENSDARG00000099999` citado → `attestation_identifier_leak` inadmisible; sintetizador fake recibe `human_attestations` como llave hermana y `evidence` sin ella; `citations[].pertinent true` para un id votado y `'not-named-by-council (…)'` para otro; `WITT_COUNCIL=0` → keyset+valores 1.10 salvo excepciones (L.2), 0 llamadas al fake, 0 `stage.council.*`, `panel_signature` byte-igual con y sin; `RECOVERAGE=0` → `post_search 'not-run (kill-switch …)'`; sin plan → `'not-applicable (no-ledger)'`; cancelar a mitad de r2 → `skipped-cancelled` + usage parcial en `usage_json`; membresía congelada: `FULL=1` en la corrida con plan de 17 → N sigue 17; `urlopen` 0; `mcp_cache` idéntico |
| `smoke_competence.py` | 32 | **39/39** (+6 de C5; +1 del corrector: `incomplete (7/12 < quorum 8)` con `n_eligible`) | componente `checked/vacuous/incomplete/no-ledger/kill-switch/errored`; `gating` por env; `incomplete` → False con reason; must `attested/discarded/unsatisfiable` excluidos y contados; `compact` copia el bool; `cg-4` con `CG_COUNCIL_COMPONENT=0` == `cg-3` golden |
| `smoke_search_harness.py` | 51 (tabla) · **47 medido @ 9d90c01 por C3** | **65/65** (+18) | directivas `[openalex, monarch, string]` → `families = 5 auto ∪ 3`, `'directives+default'`; `openalex.query == query_en` de la directiva, `query_source 'council-directive:req-…'`; símbolos añadidos a zfin/alliance declarados; familia desconocida → `'unknown-family'`; `web` → excluida `unsatisfiable`; `directive_queries` de europepmc = 1 llamada extra dentro del presupuesto (fake cuenta), `skipped-budget` con presupuesto 0; ítems y filas con `directive_requirement_ids`; sin directivas → byte-idéntico a hoy (golden 51/51) |
| `smoke_models.py` | 82 (tabla) · **74 medido @ 9d90c01 por C3** | **87/87** (+13; gate M.4 de literales en PASS) | `resolve_role('council')` g2 opus-5 / g1 opus-4-8 con fuente; `WITT_MODEL_COUNCIL` respetado; fable → `excluded-model`; `max_tokens.council` 4000/1200; `panel_signature` byte-igual con y sin el rol (golden); `snapshot().fields['role.council', 'council.*']` sin secretos; `CACHE_MULTIPLIERS` con fuente/fecha; `cache_prices()` = 1.25×/2×/0.1× de `prices()`; `prices()` golden intacto; grep de literales = 0; ENV_TABLE (+22) ⊆ compose ∩ README |
| `smoke_panel_quorum.py` · `smoke_openai_responses.py` (caller) | 28 · 79 | **40/40** (+12) · **79/79** (un aserto relajado a llaves aditivas) | `system` str → body byte-igual a hoy (golden); `system` lista → bloques tal cual; `tools=` lista + `tool_choice` forzado; 429 con `Retry-After: 7` → espera 7 (reloj falso), `900` → 30 (cap), sin cabecera → 2·(n+1); semáforo 2 con 5 hilos → máximo 2 dentro de `urlopen` (contador); `audit()` con `directives=[…]` sigue `council_hook 'not-available'` (sin cambio) |
| `smoke_usage_http.py` | 25 | **32/32** (+7; `plans_council` sobre filas REALES de `plans`) | `plans_council` con plan no consumido; `by_stage.council_r*` agregados; `cache` en `by_model` |
| `smoke_thread_context.py` · `smoke_runs_list_http.py` · `smoke_gate_citations.py` | 37 · 21 · 48 | **40/40 · 24/24 · 52/52** (+3 · +3 · +4) | `council_summary` (tope 24, `truncated`; padre sin `council` → null); `plan_council_state` lista == detalle; `pertinent` true / not-named / not-available por mapping |
| resto (21 smokes sin tocar) | medidos igual (ADR-0081 tabla) | sin cambio — **medidos por C9**: `config_history_http` 29 · `config_ledger_db` 37 · `entities` 16 · `fetch_paper` 41 · `m5v2_http` 32 · `niches` 21 · `notes_http` 28 · `precedent` 30 · `pubmed_tool` 32 · `query_service` 47 · `question_agent_http` 40 · `ratings_calibration` 44 · `run_comments_http` 14 · `run_recovery` 40 · `runs_thread_http` 71 · `search_queries` 163 · `threads_db` 77 · `tools_a` 45 · `tools_b` 69 · `tools_c` 68 · `zfin_tool` 26 | 31 → **37 smokes en verde** con la máscara, una `.db` por smoke (`smoke_zfin_tool` requiere el golden gitignored de `rag_index/curation/quarantine/…/raw/wt1a.json` presente en el árbol) |
| `smoke_live_council.py --dry-run` (estático) | — | **exit 0 — MEDIDO por C8 el 2026-09-15 (3 filas: count_tokens 20 cuerpos · `literature-monitor` r1 · r2) y por C9 el 2026-09-16 (`--member domain-knowledge-curator --round r1`: cuerpo REAL capturado, `system` 2 bloques con `cache_control`, `tools` ×3 byte-idénticos, `tool_choice emit_information_requirements`, `max_tokens 4000`, `output_config.effort 'medium'`, `urlopen` reales 0, `db` no importado)** | body capturado: `system` 2 bloques con `cache_control`, `tools` ×3 byte-idénticos, `tool_choice` forzado, `max_tokens` 4000, `output_config.effort 'medium'`; `urlopen` 0; sin BD, sin archivo |

## Gates EN VIVO (los corre Emmanuel; cada uno gasta lo que dice; resultados al ADR como MEDICIÓN con fecha)

- **LG1 · MEDIR el prefijo y UNA ficha real ANTES de encender (≈ 20 llamadas a `count_tokens` = USD 0 + 2 llamadas reales ≤ 0.10
  USD):** `smoke_live_council.py --count-tokens` → 20 llamadas a `count_tokens` (base · tools · tools+A · 17 fichas; los tokens salen por
  DIFERENCIA, regla declarada en la salida) → tokens de `[tools + bloque A + §7]` (debe ser **≥ 512** o la caché no escribe:
  si no llega, el bloque A se completa con las reglas §7 íntegras, declarado) y de las 17 fichas (sustituye "≈ 305 tokens de
  media"); `--member literature-monitor --round r1 --repeat 2` → `tool_use` válido con todos los `required` bajo `max_tokens 4000`,
  `stop_reason 'tool_use'`, 1ª llamada `cache_creation_input_tokens > 0`, 2ª `cache_read_input_tokens ≈ tokens del prefijo` y
  `creation ≈ 0`; `thinking_tokens` y `output_tokens` impresos (E2 se decide con esta cifra); latencia. Sustituye TODOS los
  supuestos de la proyección.
- **LG2 · Un plan real en prod (17 llamadas r1, ≈ 0.7–1.3 USD [E]):** `POST /runs/plan` responde al instante con `council.state
  'queued'`; p95 del request MEDIDO y anotado contra el timeout del proxy Traefik/Dokploy (Emmanuel lo consulta: hoy nadie lo ha
  hecho); `GET /plans/{id}/stream` entrega 17 `stage.council.member` + `progress` sin cortarse (keep-alive 15 s) y llega a
  `applicable` en < 300 s; `n_valid/17`, `n_unsatisfiable`, `cache_read` ≥ 16 lecturas del prefijo compartido (si el #1 fue solo);
  ledger visible en M3; aprobar con 1 discard razonado y 1 aporto; `POST /runs` sin 409.
- **LG3 · Esa corrida (≈ 1.0–2.0 USD [E] de consejo):** Traza con `stage.council.ledger`, `round{r2}` (`n_valid/17`),
  `coverage{pre}`, `stage.competence` con `council_uncovered_must checked`, si hubo must sin cubrir: `stage.council.directives`,
  `stage.search.plan {families_source 'directives+default', n_directives ≥ 1}` con una familia directive-only entrando por
  directiva, `round{r3}` sobre subconjunto SÓLO si `n_admitted_total > 0`; `frozen.council` íntegro; `by_stage.council_r1
  'copied-from-plan_json'` + `r2/r3` con caché; `hit_ratio_r2` medido (hueco humano r1→r2 anotado: decide E3); M8 cuadra; hueco
  máximo entre eventos < 300 s (el reaper no sentenció).
- **LG4 · A/B con y sin consejo (`WITT_COUNCIL=0` vs `1`) sobre las 4 preguntas de referencia a361f566, ea96d70e, fd6850eb,
  9b3140ab (8 corridas ≈ 12–20 USD [E]; 2 de ellas con `WITT_COUNCIL_FULL=1` — E5):** hits relevantes por familia, disparos de
  Ruta B por decisor, veredictos CON y SIN `deterministic_checks.council` (¿mueve al panel?), Δ de confianza pass1→pass2, costo y
  latencia por etapa, `must_uncovered_post`, `n_agents_applicable` (v1.2 vs v1.3). Con n ≈ 4–8 el resultado se DECLARA descriptivo
  (sin poder) y se publica en el ADR con fecha.
- **LG5 · Presión sobre el proveedor (2 corridas simultáneas con consejo + 1 plan en cola):** cero `http-429` no reintentados;
  `meta.queue_wait_s > 0` en alguna llamada (el semáforo trabajó); `retry_after_honored_s` cuando hubo 429; ningún miembro
  `skipped-budget`; latido de ambas corridas < 300 s. Con `WITT_COUNCIL_MEMBER_TIMEOUT_S=5` provocado: filas `timeout`, la ronda
  sigue, `abandoned_threads` contado.
- **LG6 · Kill-switch en prod (`WITT_COUNCIL=0`, 1 corrida):** sin `stage.council.*`, componente kill-switch, plan sin job (`state
  'disabled …'`), `POST /runs` directo, `panel_signature` igual al de LG3 — el camino de `9d90c01`.
- **LG7 · `GET /council/search` tras ≥ 3 corridas cerradas con consejo:** ítems por kind (incl. `decision`), comentarios sólo con
  `kinds=comment`; `prior_observations {n ≥ 1}` en el `stage.council.round{r1}` del siguiente plan; `GET /council/demand` con conteos
  y `fired`.
- **LG8 · Redeploy:** `_migrate` añade las columnas de `plans`/`runs` y crea `plan_events` en el Postgres real sin error; planes
  pre-ADR se leen `'pre-adr-0082'`; un job r1 a medio correr durante el redeploy queda `errored (worker-lost-restart)` con evento y
  M3 lo pinta; docker-compose con las 27 env y sus defaults; `/config-history` gana las filas `role.council` / `council.*`.

## Proyección de costo y latencia (CLASE: PROYECCIÓN — calculada por regla desde supuestos DECLARADOS; ninguna llamada de consejo
se ha medido: LG1–LG3 sustituyen cada cifra)

**Tarifas** (models.py g2, `PRICES_AS_OF 2026-09`): `claude-opus-5` 5 / 25 USD por Mtok; caché escritura 1.25× (TTL 5 min) ·
2× (1 h) · lectura 0.1× (skill `claude-api`, `shared/prompt-caching.md`; mínimo cacheable Opus 5 = 512 tok). **Supuestos:** prefijo
COMPARTIDO `tools` (3 schemas ≈ 1.5k) + bloque A + §7 (≈ 0.9k) ≈ **2.4k tok** (medido en LG1; debe ser ≥ 512); ficha **≈ 0.3k tok
de media** (MEDIDO hoy en chars: 20 765 / 17 ≈ 1 221 chars; máx 757 tok) — el brief asumía 3–5k; payload r1 (pregunta, entidades,
juicio del plan, ≤ 5 prior observations) ≈ 1.5k; payload r2 (evidencia DI + path_b compacta ≤ 24 000 chars ≈ 6k + pass1 0.5k +
sus requisitos 0.3k) ≈ 6.8k; r3 ≈ 8k; salida: 0.6k útiles (r1) / 0.4k (r2) + pensamiento adaptativo **0.5–2k** (facturado como
salida; el supuesto MÁS incierto — `WITT_COUNCIL_EFFORT=medium` apunta al extremo bajo; LG1 mide `thinking_tokens`); N = 17;
`attempts` 1 (peor caso ×2 por reintentos de contenido, declarado). **Por miembro y llamada (sin caché):** r1 in 4.2k → 0.021 USD,
out 1.1–2.6k → 0.028–0.065 → **0.049–0.086**; r2 in 9.5k → 0.048, out 0.9–2.4k → 0.023–0.060 → **0.071–0.108**; r3 in 10.7k → 0.054 +
out 0.023–0.060 → **0.077–0.114**. **Por ronda (×17):** r1 **0.83–1.46 USD**; r2 **1.21–1.84 USD**; r3 (subconjunto 5–8 miembros, sólo
si la búsqueda admitió algo) **0.39–0.91 USD**. **Caché:** el prefijo compartido se escribe una vez (2.4k × 6.25/M = 0.015) y se lee
16× (2.4k × 0.5/M = 0.0012 vs 0.012 sin caché) → **−0.17 USD por ronda** [E]; la ficha (0.3k) cacheada ahorra ≈ 0.001 USD por lectura y
sólo se lee si r2 arranca < 5 min después de r1 — entre ambas está la lectura humana del ledger: normalmente NO (D1 sobre D3);
`WITT_COUNCIL_CACHE_TTL=1h` cuesta +0.0004 por ficha escrita y no cambia el orden de magnitud (E3 se decide con `hit_ratio_r2`
medido). **Consejo por turno:** competente sin búsqueda (r1 + r2, caché en el prefijo) ≈ **1.7–3.0 USD**; con búsqueda y r3 ≈
**2.0–3.8 USD**; full-council (N=25) × 1.47 en r1/r2. **Turno completo** = consejo + base medida hoy 0.208 USD (mediana de 3 corridas)
+ pass2/panel con más evidencia ≈ +0.3–0.6 → **≈ 2.2–4.4 USD por turno** (×10–20 frente a hoy), extremo bajo con `effort medium`,
extremo alto con pensamiento `high`; el peor caso de reintentos de contenido (×2 en una fracción de miembros) suma +0–1 USD. Ronda 1
de planes nunca corridos: gasto huérfano visible en `/usage.plans_council`. **Latencia [E]:** r1 en el JOB del plan (fuera del request
HTTP): miembro #1 solo 10–20 s + 16 en lanes de 6 → 3 oleadas × 10–20 s ≈ **40–80 s** (el plan aparece al instante; el ledger llega
por SSE); r2 **50–90 s** dentro de la corrida (entrada mayor); r3 20–40 s → **+1–2 min por turno** dentro de la corrida; hueco máximo
de latido 30 s (`progress`) frente a 300 s de aviso y 900 s de reaper. Toda cifra de arriba se sustituye por medición en LG1–LG4 y
se registra en el ADR con fecha.

## Decisiones abiertas para Emmanuel (mínimas; cada una con default)

- **E1 · Must `unsatisfiable-by-harness` (`web`, `tooluniverse`, `figure`).** Default = NO gatea: se cuenta (`must_unsatisfiable`,
  `GET /council/demand`) y se declara aparte, para que la rama competente no quede constante-falsa por algo que el harness no puede
  satisfacer. Alternativa: contar como `uncovered` (fuerza una búsqueda que no puede satisfacerlo).
- **E2 · Pensamiento del consejo.** Default propuesto `WITT_COUNCIL_EFFORT=medium` (17 llamadas de CRITERIO, no de síntesis; acota
  latencia y costo ≈ extremo bajo de la proyección). Alternativa: vacío = heredar `WITT_ANTHROPIC_EFFORT` (default de la API
  `high`; ≈ extremo alto). Se fija por ruta y no varía por corrida (invalida la caché). Decides con `thinking_tokens` de LG1.
- **E3 · TTL de la caché de la ficha.** Default `5m`. Alternativa `1h` (escritura 2×) si `hit_ratio_r2` medido en LG3 es 0 y el
  hueco humano r1→r2 típico cae en 5–60 min. Impacto en USD ≈ 0 en ambos casos (la ficha es ≈ 0.3k tok); es una decisión de
  medición, no de costo.
- **E4 · Correr sin aprobar el ledger.** Default = 409 hasta **Aprobar** (un clic "keep todo" salvo `hard_rule`) o **Saltar** con
  razón (decisión tomada; brief §4 A). Alternativa admisible si te frena (retro, no código): la corrida arranca, r2 queda
  `'not-applicable (ledger not approved)'` y el componente no gatea — sin gastar prosa no aprobada (D3). `causal-pruner` exige
  decisión explícita en cualquier caso (§7.1, no negociable).
- **E5 · Sintetizador CIEGO al consejo (default) y full-council en el A/B.** Los criterios no cubiertos NO entran a pass2 ni como
  pista de `gap_flags`: los ve el humano y el turno siguiente (`council_summary`); pasar "uncovered must" como pista tipada es un
  ADR con held-out. Y `WITT_COUNCIL_FULL=1` sólo en 2 de las 4 preguntas del A/B (LG4), 0 en producción.
- **E6 · Texto atestiguado para `budget_approval`** (ADR-0081 E3, ampliado) y confirmación del diferimiento de las lentes por
  nicho (K.a). Propuesta: *"Apruebo el consejo de criterio de 17 miembros con claude-opus-5 en hasta tres rondas por turno (r1 en el
  plan, r2 y r3 en la corrida; ≈ 2–4 USD por turno proyectados, medidos por etapa y con caché declarada), sin tope por corrida; toda
  cifra con clase. Las lentes del panel por nicho quedan para un ADR propio."* — confirmar tal cual o acotar. **Estado en esta obra (C8): placeholder literal `<pendiente E6>` — el archivo atestiguado `rag_index/config_history.json`
  conserva la entrada `budget_approval` de ADR-0081 (`<pendiente E3>`); ampliarla con el texto de arriba es un ACTO de Emmanuel al
  pasar a Accepted, no de esta obra (clase atestiguada: jamás la escribe el código).**

## Plan de implementación (rebanadas DISJUNTAS por archivo → integrador → 3 revisores → corrector)

Orden: **C1 → (C2 ∥ C3 ∥ C6 ∥ C7) → (C4 ∥ C5) → C8 → C9 integrador → R1/R2/R3 revisores (doctrina · corrección · contrato) →
corrector.** C1 congela la INTERFAZ que todos consumen (`catalog_cards.CARDS/CATALOG_SHA/card()`, `agent_matrix.COUNCIL_MEMBERSHIP/
council_members()`); C2 congela las firmas de `council.py` que C4/C5 llaman; hasta que aterricen, C4/C5 desarrollan contra un stub
local con esas firmas que C9 retira. Ningún archivo tiene dos dueños.

- **C1 · fichas + matriz** — dueño de: `analysis/scripts/lib/catalog_cards.py` (NUEVO) · `analysis/scripts/lib/agent_matrix.py` ·
  `rag_index/query_service/smoke_catalog_cards.py` (NUEVO) · `smoke_agent_matrix.py` (NUEVO). Entrega (A) y (B).
- **C2 · consejo puro + caller** — dueño de: `analysis/scripts/lib/council.py` (NUEVO) · `analysis/scripts/lib/composite_auditor.py`
  (`tools=`, `system` lista, `_INFLIGHT`, `Retry-After`, `CallerError.retry_after`) · `smoke_council.py` (NUEVO) ·
  `smoke_panel_quorum.py` (+caller) · `smoke_openai_responses.py` (sólo si un aserto se rompe). Entrega (C) y (D.1).
- **C3 · tabla de modelos + harness** — dueño de: `analysis/scripts/lib/models.py` · `analysis/scripts/lib/search_harness.py` ·
  `smoke_models.py` · `smoke_search_harness.py`. Entrega (D.2) y (G.3).
- **C4 · BD + job de ronda 1** — dueño de: `rag_index/query_service/db.py` · `council_jobs.py` (NUEVO) · `smoke_council_jobs_db.py`
  (NUEVO). Entrega (E.1) y (E.2).
- **C5 · corrida + compuerta + PDF** — dueño de: `rag_index/query_service/runs.py` · `competence.py` · `analysis/scripts/lib/
  verify_output.py` (`council_pertinence=`) · `record_pdf.py` (sección "CONSEJO DE CRITERIO") · `smoke_run_pipeline.py` ·
  `smoke_competence.py` · `smoke_gate_citations.py` · `smoke_thread_context.py`. Entrega (F.4 copia al encolar en `new_run`), (F.5),
  (G), (H), (J), `start_workers` lanza `council_jobs` (firma declarada por C4).
- **C6 · puertas HTTP** — dueño de: `rag_index/query_service/app.py` · `smoke_council_http.py` (NUEVO) · `smoke_usage_http.py` ·
  `smoke_runs_list_http.py`. Entrega (E.3), (F.1–F.3), las 8 rutas, `/usage.plans_council`, `_run_view.plan_council_state`.
- **C7 · índice del consejo** — dueño de: `rag_index/query_service/council_index.py` (NUEVO) · `smoke_council_index.py` (NUEVO).
  Entrega (I) salvo las rutas (C6 las cablea contra su firma).
- **C8 · doctrina + operación + vivo** — dueño de: `docs/decisions/0082-consejo-de-criterio-ejecutable.md` (este documento con
  conteos "C9 mide") · `docs/decisions/README.md` (fila 0082) · `rag_index/query_service/docker-compose.query.yml` (bloque ADR-0082
  tras `WITT_CONFIG_LEDGER`, 27 placeholders `${VAR:-default}` + nota "toda env = reinicio") · `rag_index/query_service/README.md`
  (rutas + tabla de env + sección "El consejo de criterio") · `skills/custom/organogenesis-agent-architect/references/
  agent-invocation-matrix.md` (v1.3: +5 filas §3, nota ADR-0082) · `analysis/scripts/smoke_live_council.py` (NUEVO, EN VIVO:
  `--count-tokens`, `--member <agent> --round r1|r2`, `--full-r1 --question`, `--dry-run`; usa `council.build_system/build_request` y
  `_anthropic_tool_call(return_meta=True)` reales; imprime usage con caché, `thinking_tokens`, latencia; escribe
  `analysis/outputs/live_council_<fecha>.json` sin secretos; rehúsa sin llave con `no-api-key`; jamás toca la BD). **Entregado por C8 el 2026-09-15**: `--dry-run` exit 0 (`py_compile` OK); modos `--count-tokens` (20 `count_tokens`, USD 0),
  `--member <agent> --round r1|r2 [--repeat N]`, `--full-r1 --question [--entities] [--full]`; palancas locales al proceso
  `--effort`, `--cache 0|1`, `--cache-ttl`, `--model`, `--max-tokens`, `--timeout`, `--concurrency`, `--budget-s`; mide al final
  `db_imported False` y `tools_static_check ok`.
- **C9 · integrador** — sin archivos propios: retira stubs, cose (M), corre los 31 + 6 gates con la máscara (una `.db` por smoke),
  `urlopen` 0, `mcp_cache` idéntico, grep de literales de modelo = 0, compose/README ⊇ env, reemplaza "C9 mide" por conteos, corre
  `tools/parity_check.py` de la webapp EN LECTURA y anota los huecos esperados, etiqueta `contract-1.11-frozen`. Commits por
  rebanada en `feat/adr-0082-consejo`; sin push (Emmanuel).
- **Revisores (3, en paralelo sobre el árbol de C9):** R1 doctrina (§7 literal: gate humano de `causal-pruner`, consejo sin
  respuesta/veredicto/despacho, atestiguado ≠ evidencia, clases de cifra, tres estados, "lo que NO se hace"); R2 corrección
  (kill-switch byte a byte con excepciones, cuórum, agregación determinista, eventos desde el orquestador, semáforo, cancelación,
  migraciones por dialecto, fakes sin red); R3 contrato (formas de (J) vs código vs lista de paridad; vocabularios congelados;
  fixtures 1.11 generables). **Corrector:** aplica los hallazgos marcándolos *(corrector)* en el ADR, re-corre los gates, actualiza
  conteos.

**Fixtures 1.11 que la webapp necesitará (los genera `gen_fixtures.py` contra `contract-1.11-frozen`; MANIFIESTO con '1.11', SHA
del backend y qué es real por el código y qué stub):** los existentes regenerados (todos ganan `council` — `'not-applicable
(no-ledger)'` en los que corren sin plan —, `deterministic_checks.council`, `token_usage.cache`, `citations[].pertinent` con razón)
· `consejo-completo.json` (17 ok, ledger aprobado con 1 discard + 1 aporto, 0 must sin cubrir → competente, sin ronda) ·
`consejo-must-sin-cubrir.json` (1 must uncovered → no competente → directivas → familia directive-only entra → r3 sobre
subconjunto) · `consejo-incompleto.json` (9/17 válidos → `False 'council-incomplete'`) · `consejo-voto-anulado.json`
(`hallucinated_evidence_ids`) · `consejo-causal-pruner-pendiente.json` (400 del ledger) · `consejo-kill-switch.json` (frozen 1.11
con `council.state 'disabled …'`; forma 1.10 + excepciones) · `consejo-skip.json` · `consejo-full-council.json` (25) ·
`plan-consejo-queued.json` / `plan-consejo-applicable.json` (GET /plans/{id}) · `plan-eventos-consejo.json` (`plan_events` con
`council.state`, `stage.council.member` ×17, `progress`, `aggregate`, `council.ledger`) · `eventos-consejo-corrida.json` (los 6
tipos `stage.council.*` en `run_events`) · `plan-respuesta-reused.json` (dedup) · `council-membership.json` ·
`council-search.json` + `council-search-vacio.json` · `council-demand.json` · `usage-plans-council.json` ·
`thread-context-council-summary.json`. Condiciones declaradas en el MANIFIESTO: los 17 miembros son FAKES inyectados (cero red),
`WITT_RUN_ORIGIN=fixture` con `WITT_COUNCIL_ORIGINS=fixture` para que el job r1 SÍ corra en el generador, y las 27 env nuevas se
quitan del proceso antes de importar (patrón `ENV_ADR_0081`).

# ADR-0081 — Política best-tier v2 y generación de modelos `g2-2026-09`: una tabla de modelos como única verdad, el modelo que CORRIÓ se mide (no se copia), el juez OpenAI habla Responses API con fallos tipados, el cuórum exige familias y lentes, y la configuración deja bitácora

- **Status:** Proposed — 2026-09-15 (llevado al repo por S6 desde el borrador del sintetizador; pasa a Accepted cuando Emmanuel
  apruebe las decisiones abiertas E1–E4; los conteos "S7 mide" YA fueron sustituidos por los MEDIDOS — S7, 2026-09-15, 31 smokes en verde, 1623 checks; corrector 2026-09-15: 31/31 en verde, 1632 checks). Origen: plan v3 del
  brief *Consejo de
  agentes* (§11 "Política best-tier v2", tabla ADR-0081, R6/R9, §17 hallazgo F3 de la auditoría externa Codex/Martín) aprobado por
  Emmanuel el 2026-09-14, y hallazgos del scout del 2026-09-15 (`mapa-adr-0081.md`, scratchpad del orquestador — no está en el repo;
  sus hallazgos están citados abajo por ruta:función): **cuatro constantes de modelo
  desincronizables y una env evaluada en import**; **el registro afirma qué modelo corrió copiando la constante, sin medirlo**;
  **el juez OpenAI habla `chat.completions` y `gpt-6-astra` exige la Responses API** (verificado en vivo por Emmanuel);
  **tres APPROVE Anthropic con el juez OpenAI caído aprueban en silencio**; **`/config-history` es un JSON manual de UNA
  entrada y la webapp afirma que la puerta no existe**; **no existe `GET /threads` listado y la webapp agrupa 50 corridas en el
  cliente**; **`/usage` no agrega `by_stage`**; **`root_run_no` sólo viaja en `/threads/{id}`**. Obra sobre
  `feat/adr-0080-competencia-harness` @ `f57a3d3` (backend) con paridad en `witt-webapp` @ `feat/adr-0080-paridad` (OTRO
  workflow). Síntesis de tres diseños (fidelidad-y-riesgo · webapp-primero · diff-mínimo) y dos juicios: parte del ganador
  (fidelidad-y-riesgo) e injerta lo que los jueces pidieron; donde los jueces divergen, la decisión y su porqué van marcados
  *(síntesis)*. Estilo de cita: **ruta:función** (los números de línea que aparecen son los del árbol @ `f57a3d3`, verificados
  hoy; el nombre de la función es lo estable).
- **Decisiones YA tomadas por Emmanuel (no se relitigan aquí):** `gpt-6-astra` es el ÚNICO juez OpenAI · exige la Responses API
  (chat.completions no sirve: verificado en vivo) · el panel CONSERVA `gpt-4o` hasta que un smoke EN VIVO con Astra pase y
  Emmanuel confirme que la llave tiene acceso · sintetizador/planner/elicitación/agente de preguntas = `claude-opus-5` ·
  `claude-fable-5-1` FUERA del panel y del sintetizador (400 observado en tool_choice forzado; retención 30 días) ·
  `claude-haiku-4-5-20251001` se retira ≥ 2026-10-15 → sucesor `claude-sonnet-5` con LENTE distinta · cuórum ≥ 2 FAMILIAS
  (`WITT_PANEL_MIN_FAMILIES=2`) con kill-switch, un panel de una sola familia JAMÁS aprueba · sin puente `gpt-5.6-sol` · el costo
  no es impedimento, pero toda cifra lleva clase y todo modelo sin precio se declara.
- **Estado de E1–E4 en esta obra (S6, 2026-09-15 — DEFAULTS aplicados, nada decidido por el código):** E1 `gpt-4o` sigue como
  juez reproducibility (`status 'bridge'`) hasta que LG2/LG3 pasen y Emmanuel confirme que la llave alcanza a Astra · E2
  `WITT_PANEL_AUTO_RETIRE=0` (retiro MANUAL de haiku; el aviso `retirement-due` se emite desde hoy, 30 días antes) · E3 la
  entrada atestiguada `budget_approval` de `rag_index/config_history.json` lleva el placeholder literal `<pendiente E3>` y
  `changed_at '<pendiente: fecha Accepted>'` (la entrada `model_generation` también espera la fecha Accepted; ninguna de las dos
  es medición) · E4 LG14 NO se corre. Ninguna de las cuatro se relitiga aquí: el ADR pasa a Accepted con el texto de E3 y las
  fechas; S7 ya reemplazó los conteos "S7 mide" por los medidos (2026-09-15).
- **Corrector (2026-09-15, tras R1 doctrina · R2 corrección · R3 contrato):** 22 hallazgos verificados contra el código, 22
  aplicados (0 rechazados), cada uno marcado *(corrector)* donde cambia una decisión o una forma. Código: (C.1/C.2) `refusal`
  por Responses (`content[].type 'refusal'`) SIN reintento · truncación decidida por `status` ANTES de parsear (un `function_call`
  parcial ya no es `arguments-unparseable`) · tope EFECTIVO del juez OpenAI en `attempts[]` (`max_output_tokens?`/`max_tokens?`);
  (A) `unknown-family` fail-loud también en los cuatro roles del pipeline; (H) `price_state 'not-measured'` (0 medido ≠ null no
  medido); (I) `config_ledger.boot()/observe()` serializados por `_LOCK` (dos workers no duplican una fila runtime-diff); (F)
  `new_run` falla en voz alta si la fila del INSERT no se lee; el modelo de la elicitación ya no se copia del sintetizador
  (`by_stage.elicit_*.model` y `stage.confidence.elicit.usage.model` null declarado con un stub). Doc alineada al código:
  `ModelSource` (+ `default-unset:`/`auto-retire:`), `ledger_state` (+ `not-booted`), `QUORUM_RULE` literal, `Ran.thinking_state`
  (4 literales) y `ran.question`, `WARNING_PREFIXES`, sobres de `/threads` y `/config-history`, `models_catalog.generation:
  string[]`, `states 'absent-in-record'`, lista (J) completa, `panel_duplicate_models`/`panel_source` en `audit` (no en
  `models`); (M.2) tres excepciones declaradas al kill-switch byte a byte; LG4 corregido (`openai.api 'table'`, `warnings` NO
  vacíos hasta LG1/E2); condiciones de los fixtures 1.10 declaradas; R14 (ámbar hasta LG1). Gates re-corridos con la máscara,
  una .db por smoke: 31/31 en verde, 1632 checks (tabla NO-SPEND) + `smoke_live_models --dry-run` exit 0.
- **Relates:** ADR-0043 (tres estados) · ADR-0047 d.4 (composición del panel; aquí cambia de generación) · ADR-0049 (auditoría en
  el 100% de las corridas) · ADR-0051 (`token_usage` medido + USD proyectados) · ADR-0055/0076 (misma vista lista/detalle; "el
  catálogo tiene historia") · ADR-0057 (`recover_trapped_params`) · ADR-0058 (`APPROVE_DECLINE` intacto) · ADR-0065 (elicitación
  dedicada: gana rol y env propios) · ADR-0067 (revisión acotada: el REVISE estructural la salta) · ADR-0072 (held-out sobre el run
  model: `run_held_out.py` toma panel y sintetizador de la tabla) · ADR-0078 (`missing_price_models`, lectores tolerantes) ·
  ADR-0079 (`thread`, `root_run_no` en el frozen; aquí también en la vista) · ADR-0080 (`by_stage`, `judge_retries`, kill-switches
  declarados, `directives_state 'empty-until-ADR-0082'`) · **ADR-0031 (cláusula "≥ 1 Fable en el panel"): SUPERSEDIDA por este
  ADR** — la exclusión de Fable la decidió Emmanuel (400 en tool_choice forzado, retención 30 días); queda declarada, no rota ·
  ADR-0082 (consejo: hueco declarado en (K)) · ADR-0083 (PDF completo: la deuda `[pdf]` va allá) · ADR-0087 (calibración: leerá
  `frozen.models.generation` y `panel_signature`).
- **Affects:** `analysis/scripts/lib/models.py` (NUEVO) · `analysis/scripts/lib/composite_auditor.py` · `rag_index/query_service/
  runs.py` (contrato **1.10**) · `question_agent.py` · `db.py` (tabla NUEVA `config_history`; JOIN a la raíz; `threads_index`) ·
  `app.py` (`GET /threads`, `/usage`, `/config-history`, lifespan) · `consulta_sistema.py` (sección `config`) ·
  `requirements.txt` · `docker-compose.query.yml` · `README.md` · `rag_index/config_history.json` (DOS entradas atestiguadas:
  `model_generation` + `budget_approval` con placeholder hasta E3 — *(S6)*, coherente con (I)) ·
  `evaluation/run_held_out.py` · `evaluation/scripts/ab_trapped_scalar.py` · smokes (6 NUEVOS + 7 tocados) ·
  `analysis/scripts/smoke_live_models.py` (NUEVO, EN VIVO, lo corre Emmanuel) · witt-webapp (tipar y pintar; ver *Consequences*).
  **Cero mutación de la DATA INAMOVIBLE, del registro congelado existente (ningún registro viejo se migra), de `mcp_cache` desde
  los gates; cero gasto de modelo en la obra (todo lo que gasta es un script de Emmanuel).**

## Context

1. **Cuatro verdades de modelo, una env en import.** `runs.SYNTH_MODEL = "claude-opus-4-8"` (L91) alimenta la elicitación
   (`_elicit_confidence`, L227), el planner (`_default_planner`, L350), la síntesis (`_default_synthesizer`, L1284) y los
   fallbacks de `_usage_by_stage`/`_token_usage` (L1520/1529/1532/1566/1570) y de los eventos (`_synth_usage_payload` L1821,
   `_elicit_event_payload` L1828, `stage.synthesize.start` L2120). `question_agent.QUESTION_MODEL` (L37) es otra copia.
   `composite_auditor.DEFAULT_PANEL` (L60-65) es la tercera y evalúa `os.environ.get("OPENAI_JUDGE_MODEL")` **al importar**: un
   smoke no puede probar la env sin reimportar. `evaluation/run_held_out.py` (L79-81) duplica panel y sintetizador. La tabla de
   precios `runs.PRICES_PER_MTOK_USD` (L1469-1476, `PRICES_AS_OF "2026-09"`) es la cuarta verdad — ya trae opus-5 (5/25),
   fable-5-1 (10/50), gpt-6-astra (10/50) y gpt-5.6-sol (4/20).
2. **El registro AFIRMA qué modelo corrió sin haberlo medido.** `_default_synthesizer` devuelve `"model": SYNTH_MODEL` (L1397);
   el planner escribe `"planner": {"model": SYNTH_MODEL…}` (L511); `_anthropic_tool_call` devuelve `(tool_input,
   payload.get("usage"))` y DESCARTA `payload["model"]` (L363); `_openai_tool_call` descarta `resp.model` (L384). Con dos
   generaciones conviviendo (históricos 4.8, nuevos opus-5) y un juez que cambia por env, `answer.model` es una constante copiada
   presentada como medición — exactamente lo que la disciplina de clases prohíbe.
3. **El juez OpenAI habla `chat.completions`.** `_openai_tool_call` usa `client.chat.completions.create` con `tools`/`tool_choice`
   function (L374-377), sin reintento propio, sin `max_retries=0` (el SDK reintenta 2 veces en silencio: `openai/_constants.py
   DEFAULT_MAX_RETRIES = 2`, medido en el venv de los gates `dev/.venvs/witt-query-service`, **openai 2.53.0**), y `audit()` guarda el
   fallo como prosa `f"{type(e).__name__}: {str(e)[:200]}"` (L466) que la webapp tipa como `string`. Emmanuel verificó en vivo que
   `gpt-6-astra` exige la Responses API. El SDK 2.53.0 expone `client.responses.create(model, instructions, input, tools,
   tool_choice, max_output_tokens, store, parallel_tool_calls, reasoning, timeout)`; `FunctionToolParam.strict` es
   `Required[Optional[bool]]` (hay que decidirlo explícito); `IncompleteDetails.reason ∈ max_output_tokens | content_filter`;
   `ResponseUsage.output_tokens_details.reasoning_tokens` e `input_tokens_details.cached_tokens` existen; el default de la API es
   `store: true` (retención 30 días del lado OpenAI). `requirements.txt` pide `openai>=1.40` — un build sin `client.responses`.
4. **El cuórum cuenta votos, no independencia.** `audit()` aprueba con `len(valid) >= min_valid` (L511); `family` es etiqueta. Con
   Astra como único juez OpenAI, su caída convierte tres APPROVE Anthropic en APPROVE silencioso (hallazgo F3, brief §17). La
   promesa está escrita en el propio módulo: `"families_valid / lenses_valid are NOT here (ADR-0081)"` (L41).
5. **`claude-opus-5` PIENSA por default.** Verificado hoy contra la referencia de la API (skill `claude-api`, guía de migración
   "Migrating to Claude Opus 5", *Breaking change 1*): una llamada que OMITE `thinking` corre thinking adaptativo en Opus 5 (en
   4.8 corría sin pensar) y **`max_tokens` acota pensamiento + respuesta**. Nuestras llamadas forzadas omiten `thinking` y sus
   topes se calibraron para 4.8 sin pensamiento: `CONF_TOOL max_tokens=300` (L227), `PLAN_TOOL 1200` (L350), `SYNTH_TOOL 2500`
   (L1284), `QUESTION_TOOL 1200` (`question_agent._default_drafter`), jueces 1200 (`_anthropic_tool_call` default). Riesgo
   concreto: la elicitación se corta por `max_tokens` sin `tool_use` → `'no valid forced tool_use'` en cada corrida. La misma
   referencia dice que `tool_choice {type:'tool'}` SIGUE aceptado en Opus 5 (sólo Fable 5.1 lo rechaza) y que apagar el
   pensamiento (`thinking {type:'disabled'}`) tiene dos modos de falla (tool call como texto; fuga de etiquetas) — la recomendación
   es dejarlo encendido y bajar `effort`. Ningún diseño lo decidía; los jueces lo marcaron como el hueco mayor.
   **Re-verificado por el orquestador el 2026-09-15 contra la documentación pública (WebFetch, no un skill):**
   `platform.claude.com/docs/en/models/opus-5/migration-guide` — *Breaking changes* 1 "Thinking on by default: On Claude Opus 4.8,
   requests without a `thinking` field run without thinking; on Claude Opus 5, the same requests run with adaptive thinking.
   `max_tokens` remains a hard limit on total output, thinking plus response text" · 2 "Disabling thinking is capped at `high`
   effort" (400 con `xhigh`/`max`) · "Effort default is `high`" · checklist: "Handle `stop_reason: 'refusal'`" con `stop_details`
   (categoría, público desde 4.7) y `fallbacks: 'default'` (beta, se RECHAZA en (L.h)) · "thinking tokens are billed as output tokens".
   `…/build-with-claude/thinking` — "Adaptive thinking, including on models where thinking is on by default, supports forced tool use,
   except on Claude Fable 5.1 and Claude Mythos 5.1"; "With thinking disabled, Claude Opus 5 can occasionally emit tool calls as plain
   text or include internal XML tags in its visible output"; `temperature/top_p/top_k` no-default → 400 en Opus 5 (no los enviamos).
   `…/build-with-claude/extended-thinking` — "monitor the `usage.output_tokens_details.thinking_tokens` field in the response, which
   reports how many of the billed output tokens were internal reasoning" (→ corrección en (C.4)). `…/models/fable-5-1/migration-guide`
   — "`{type: 'any'}` and `{type: 'tool', name: '...'}` return a 400 `invalid_request_error`: tool_choice: type 'tool' and 'any' are
   not supported for this model"; "Both models require 30-day data retention, aren't available under zero data retention (ZDR)
   arrangements unless expressly authorized" — las dos razones de la fila `excluded` de Fable quedan citadas, no sólo observadas.
6. **`/config-history` es un JSON manual de una entrada y M6 dice que la puerta no existe.** `app.config_history` lee
   `rag_index/config_history.json` (L1289-1308; `_CONFIG_HISTORY` L276): UNA entrada (`embed_model`, 2026-06-12). `Bitacora.tsx`
   pestaña SISTEMA afirma que el histórico "no tiene puerta HTTP" (falso). Un cambio de panel o de generación no deja huella.
   `_embed_model_changed_at` (L313-325) y `consulta_sistema` sección `config` (L123-133) leen el mismo archivo.
7. **`root_run_no` sólo en `/threads/{id}`.** `get_thread` lo deriva (L825); `_run_view` es passthrough de columnas (L508-561) y la
   vista no lo trae; `runs._root_run_no` (L1055-1065) hace `db.get_run(thread_id)` por corrida (N+1 sobre una lista de 50).
   `Traza.tsx` recorta `thread_id.slice(0, 8)` (L511/L850) porque "el nombre T-N no viaja". `db._list_select` (L753-766) es UNA
   definición para lista e investigación; `get_run` (L693-701) es `select(runs)`.
8. **No existe `GET /threads` listado.** Sólo `/threads/{thread_id}` (L774-847). `Bitacora.agruparPorInvestigacion` (L280) agrupa
   en el cliente las 50 corridas de `/runs`: sin denominador, sin paginación, "etiqueta desconocida" cuando la raíz no cargó.
9. **`/usage` no agrega `by_stage`.** `app.usage` lee sólo `u["by_model"]` (L1186-1284). `runs.TOKEN_STAGES` (L1486) y
   `_usage_by_stage` (L1492-1548) ya congelan `model` por etapa (plan/synth/elicit/revision) pero el panel se suma sin reviewer
   (L1540-1544) aunque el bucle ya itera las filas. `parity_debt.json` lo declaró "HUECO QUE EL GATE NO MIDE… el cierre es del
   backend". `familias-modelo.ts` adivina la familia por regex y manda `claude-fable-5-1` a "otros".
10. **Toda env implica reinicio.** El `os.environ` de un contenedor se fija al arrancar el proceso: cambiar una env en Dokploy no
    surte efecto hasta redeploy/restart. Dos diseños lo daban por sentado al revés. La lectura en tiempo de llamada (patrón
    `resolve_judge_retries`, L81-93) sigue siendo correcta — permite probar la env offline sin reimportar — pero NO elimina el
    reinicio; por eso una bitácora escrita al arrancar es completa PARA ENVS, y se declara qué no puede registrar (ver (I)).

## Decision

**(A) UNA tabla de modelos y dos generaciones — `analysis/scripts/lib/models.py` (NUEVO, stdlib puro, sin `from lib import`).**
`MODELS_TABLE_VERSION = 'g2-2026-09'`, `MODEL_TABLE_AS_OF = '2026-09-15'`. `MODELS[id] = {family ∈ anthropic|openai, api ∈
anthropic-messages|openai-responses|openai-chat-completions, api_verified: bool, status ∈ active|retiring|bridge|candidate|
excluded|not-adopted|previous-generation|embed, thinking_default ∈ adaptive|off|n/a, reasoning: bool, retire_not_before?,
successor?: {reviewer, lens}, price_in, price_out, verified_on, source, note}`. Filas: `claude-opus-5` (active, adaptive, 5/25) ·
`claude-sonnet-5` (active, adaptive, 2/10) · `claude-haiku-4-5-20251001` (retiring, `retire_not_before '2026-10-15'`, successor
`{claude-sonnet-5, evidence-grounding}`, off, 1/5) · `claude-opus-4-8` (previous-generation, off, 5/25) · `claude-fable-5-1`
(excluded: "400 en tool_choice forzado observado; retención 30 días", 10/50) · `gpt-4o` (bridge, openai-chat-completions,
`api_verified True` — el camino probado en vivo, 2.5/10; nota atestiguada del brief: su snapshot se apaga 2026-10-23) ·
`gpt-6-astra` (candidate, openai-responses, `reasoning True`, 10/50) · `gpt-5.6-sol` (not-adopted: "sin puente, decisión de
Emmanuel", 4/20, `api_verified False`) · `text-embedding-3-small` (embed, 0.02/0). **`prices()` devuelve EXACTAMENTE el dict de
`runs.PRICES_PER_MTOK_USD` de hoy** (golden en smoke) y `runs.PRICES_PER_MTOK_USD = models.prices()`, `runs.PRICES_AS_OF =
models.PRICES_AS_OF` conservan su NOMBRE (`app.usage` y los smokes los leen). Los literales de modelo viven SOLO en `models.py`.
`GENERATIONS = {'g2-2026-09': {…}, 'g1-2026-08': {…}}` con defaults por ROL y TOPES por rol: **g2** — synthesizer/planner/
elicitation/question_agent = `claude-opus-5`; panel correctness `claude-opus-5` · overclaim `claude-sonnet-5` · evidence-grounding
`claude-haiku-4-5-20251001` · reproducibility `gpt-4o`; `max_tokens` (topes, no gasto — ver (C.4)) synth 8000 · planner 4000 ·
elicitation 2000 · question 4000 · judge-anthropic 4000. **g1** = HOY byte a byte: `claude-opus-4-8` en synth/planner/elicit/
question/correctness, sonnet-5, haiku-4-5, gpt-4o; topes 2500 · 1200 · 300 · 1200 · 1200. `ROLE_ENVS = {synthesizer:
WITT_MODEL_SYNTH, planner: WITT_MODEL_PLANNER, elicitation: WITT_MODEL_ELICIT, question_agent: WITT_MODEL_QUESTION,
judge.correctness: WITT_JUDGE_CORRECTNESS, judge.overclaim: WITT_JUDGE_OVERCLAIM, judge.evidence-grounding: WITT_JUDGE_GROUNDING,
judge.reproducibility: OPENAI_JUDGE_MODEL}` (el último conserva su nombre: es la palanca que Emmanuel flipará).
**Resolución EN TIEMPO DE LLAMADA, jamás en import:** `resolve_role(role, env=None, today=None) -> {model, source, family,
family_source, api, api_source, known, priced, max_tokens, generation, generation_source}`. `source ∈ 'env:<VAR>' |
'default:<gen>' | 'default-invalid-env:<VAR> (<motivo>)' | 'default-unset:<VAR>' | 'auto-retire:<a>-><b>' | 'env:<VAR>
(unknown-to-table)'` *(corrector: la lista congelada es `models.SOURCE_PREFIXES = ('env:', 'default:', 'default-invalid-env:',
'default-unset:', 'auto-retire:')`; `default-unset:WITT_MODEL_GENERATION` es la `generation_source` de TODA corrida sin env — no un
caso borde — y `default-unset:<VAR>` la fuente de los campos de env del snapshot y del cuórum)*; motivos: `excluded-model` (fable
en cualquier rol), `wrong-family-for-
lens` (un `claude-*` en `OPENAI_JUDGE_MODEL`, o un `gpt-*` en una lente Anthropic), `same-model-same-lens` (dos asientos idénticos
por env). **Un id DESCONOCIDO para la tabla se USA tal cual** *(síntesis: fidelidad + injerto de familia por prefijo)* — `known
False`, `priced False`, `source 'env:<VAR> (unknown-to-table)'`, `family` por prefijo (`claude-*` → anthropic · `gpt-*`/`o[0-9]*` →
openai; `family_source 'prefix'`), sin prefijo que case → `family 'unknown'` y el asiento erra en la llamada con `error_kind
'unknown-family'` (fail-loud, no el `else: anthropic` de hoy) *(corrector: la MISMA regla rige los cuatro roles del PIPELINE —
`runs._anthropic_call`, sede única de synthesizer/planner/elicitation, y `question_agent._default_drafter` lanzan
`CallerError('unknown-family')` ANTES de construir la petición: cero llamadas, corrida `failed` / borrador `errored` con error
tipado; antes el id se mandaba tal cual a la Messages API → http-404 en producción; medido en `smoke_run_pipeline` y
`smoke_question_agent_http`)*. La tabla siempre irá detrás del proveedor (snapshots fechados):
sustituir la elección explícita del operador es corregir en silencio, aunque la fuente lo diga; sólo se rechaza lo que la tabla
sabe que ROMPE (excluded, familia incompatible). `WITT_MODEL_GENERATION` (default `g2-2026-09`; valor fuera de `GENERATIONS` →
`generation_source 'default-invalid-env:…'`). `panel(env=None, today=None, directives=None) -> PanelMember[4]` en orden fijo
correctness/overclaim/evidence-grounding/reproducibility con `{reviewer, family, family_source, lens, api, api_source, reviewer_source,
known, priced, max_tokens}`; `panel_signature(panel, roles) -> sha256[:16]` (injerto: cuando Emmanuel pinea una env la generación
sigue g2 pero el panel cambia — ADR-0087 segmenta por firma). `api_of(model, env)` → la api de la tabla, salvo
`WITT_OPENAI_API ∈ table(default)|responses|chat-completions` que fuerza el transporte de TODO juez OpenAI (`api_source
'env:WITT_OPENAI_API'`). `relation(requested, reported) -> exact|prefix|different|not-reported`. `past_retirement(env, today)` /
`retirement_due(env, today, days=30)`. `snapshot(env=None, today=None)` = el estado EFECTIVO con fuente por campo (insumo del
ledger, de `stage.models` y de `/config-history.current`; lista cerrada `SNAPSHOT_FIELDS`, jamás una llave API).
`provenance_block(roles, passes, planner_meta, panel_rows, question_meta=None)` arma `frozen.models` (ver (B)).
`runs.SYNTH_MODEL` y `question_agent.QUESTION_MODEL` se CONSERVAN como alias derivados (`models.resolve_role('synthesizer')['model']`
en import) — `ab_trapped_scalar.py` (L153/198/215/302) y `app.question_spec` (L1507) los leen; el pipeline resuelve en la llamada.
`composite_auditor` importa la tabla en DURO (`from lib import models`, mismo paquete): sin fallback literal — si falta, el módulo
no importa y el smoke lo dice a gritos; `DEFAULT_PANEL = models.panel(env={}, today=MODEL_TABLE_AS_OF)` queda como snapshot
documental y `runs._plan_structural` (L439) lista `models.panel()` EN LA LLAMADA + `panel_resolved[] {reviewer, family, lens,
reviewer_source}` (injerto: el plan es "structural — del código", debe decir lo que VA a correr, no el literal g1).

**(B) Procedencia MEDIDA del modelo que corrió, en el registro y en la Traza.** Los callers devuelven lo que la API dijo:
`_anthropic_tool_call(..., return_meta=False)` conserva su 2-tupla para todos los llamadores y fakes de hoy; con
`return_meta=True` devuelve `(tool_input, usage, meta)` con `meta = {model_reported: payload['model'], api: 'anthropic-messages',
stop_reason, stop_details? (la categoría del refusal, público desde Opus 4.7), response_id?}` y `usage` = lo numérico que la API
devolvió, con `output_tokens_details.thinking_tokens` aplanado como `thinking_tokens` cuando viene (ver (C.4)); `_openai_responses_call`/`_openai_chat_call` devuelven SIEMPRE 3-tupla; `_default_caller` devuelve
3-tupla y `audit()` acepta 2 o 3 (`meta = {}` con un caller viejo). **`model_reported` y `api` JAMÁS viajan dentro de `usage`**
*(corrección de los jueces: la webapp tipa `usage?: Record<string, number>`; `_acc`/`_usage_in_out` sólo suman numéricos, pero
`_usage_payload` copia el dict a eventos)*. Los wrappers de producción (`_default_synthesizer`, `_elicit_confidence`,
`_default_planner`, `question_agent._default_drafter`) escriben en su salida `model` (lo PEDIDO, resuelto), `model_source`,
`model_reported` (lo que la API devolvió; `None` con un stub) y `relation`. `frozen.models = {generation, generation_source,
table_version, table_as_of, panel_signature, roles: {synthesizer: RoleResolved, elicitation: RoleResolved, question_agent:
RoleResolved|null, planner: {model, model_source, provenance ∈ 'plan_json' | 'plan_json (pre-1.10: source not recorded)' |
'no-plan'}}, ran: {synthesize_pass1: Ran, synthesize_pass2: Ran|null, revision: Ran|null, elicit_pass1: Ran|null, elicit_pass2:
Ran|null, plan: Ran|null, question: Ran|null, panel: [{lens, reviewer, reported, relation, api_used, attempts}]}, rule}` con
`Ran = {requested, reported: string|null, relation, thinking_state}` *(corrector — forma congelada en `models.RAN_FIELDS`:
`thinking_state ∈ models.THINKING_STATES` = 'adaptive-by-api-default (tokens dentro de output_tokens)' | 'off-by-model-default' |
'not-applicable (sin pensamiento declarado en tabla)' | 'unknown-to-table' — este último es lo que produce TODO sintetizador stub o id
fuera de tabla, y la webapp lo verá en sus fixtures; `ran.question` es null en toda corrida de `execute_run` — sólo lo llena
`question_agent` fuera del pipeline)*. **`roles.planner` se COPIA de `plan_json.judgment.planner`** *(injerto B: el planner corrió en
`POST /runs/plan`, quizá antes del redeploy — un plan opus-4-8 con síntesis opus-5 es la verdad, no un bug; la Hoja lo pinta sin
"corregir")*. `relation 'prefix'` (alias → snapshot fechado) es NEUTRO, jamás error; `'different'` es objeción; `'not-reported'` es
gris. Evento NUEVO **`stage.models`** (`agent 'runs'`, PRIMER evento tras `run.state {running}`, antes de `stage.plan`): payload =
`models.snapshot()` reducido a `{generation, generation_source, table_version, panel_signature, roles (elección + fuente), panel[],
warnings[], unknown_models[]}` — la Traza dice qué va a correr ANTES de gastar *(corrector: `warnings[]` tiene vocabulario
CERRADO por prefijo `models.WARNING_PREFIXES = ('retirement-due:', 'past-retirement:', 'invalid-env:', 'api-unverified:',
'not-adopted:')`; el evento sale con `level 'warning'` si hay CUALQUIER aviso o `unknown_models` — incluido `api-unverified:`
mientras un modelo efectivo tenga `api_verified False`, es decir el 100% de las corridas g2 por default hasta que LG1 mida opus-5 y
su fila pase a `api_verified True`: consecuencia operativa declarada, R14 — no se baja a `info` para no esconder que el modelo de
producción no ha sido medido por este código)*. *(síntesis: evento propio, no una llave dentro de
`run.state{running}` — es el patrón de la casa (`stage.competence`, `stage.search.plan`) y el gate (C) de paridad mide tipos de
evento).* `stage.synthesize.start` gana payload `{model, model_source, generation}` (hoy sólo `agent=SYNTH_MODEL`).
`stage.audit.judge` += `family, api, api_source, reviewer_source`. `epistemic_summary` += `model_generation, panel_n_families_valid`.

**(C) El caller OpenAI por Responses API, vocabulario CERRADO de fallos, despacho por transporte, y el pensamiento de Opus 5.**
*(C.1 caller)* `_openai_client(timeout)` = factory de módulo (monkeypatcheable) que devuelve `OpenAI(timeout=timeout,
max_retries=0)` — **`max_retries=0`** *(injerto: el SDK reintenta 2× en silencio y `attempts[]` mentiría)*; sin `OPENAI_API_KEY`
lanza `CallerError('no-api-key')` ANTES de tocar red; sin `client.responses` → `'sdk-unavailable'`. `_responses_kwargs(model, system,
user_text, tool, max_output_tokens, store, reasoning_effort)` es UNA función pura que arma `{model, instructions: system, input:
user_text, tools: [{type:'function', name, description, parameters: tool['input_schema'], strict: False}], tool_choice:
{type:'function', name}, parallel_tool_calls: False, max_output_tokens, store, [reasoning: {effort}]}` — la comparten el caller y
el script en vivo, así no divergen. `strict: False` FIJO *(síntesis: `strict: true` exige todas las propiedades en `required` y
rompe el tres-estados de `domain_niches`/`citation_support`; una env que se sabe rompe el schema no se declara — `WITT_OPENAI_STRICT`
NO existe)*. `store: False` por default (`WITT_OPENAI_STORE`, 0/1): el default de la API es retención 30 días del lado OpenAI;
para un sustrato médico se apaga y se declara — sin afirmar ZDR. `reasoning.effort` se envía SÓLO si `WITT_OPENAI_REASONING_EFFORT
∈ low|medium|high` Y la tabla marca `reasoning True` para el modelo (gpt-4o lo rechazaría). `_openai_responses_call(model, system,
user_text, tool=None, timeout=None, retries=1, max_output_tokens=None, client=None)`: lee el ÚNICO ítem `output[].type ==
'function_call'` con `name == tool['name']` (los ítems `reasoning` previos se ignoran), `json.loads(arguments)`,
`recover_trapped_params` (ADR-0057, `_recovered_fields` declarado), valida `verdict ∈ VOCABULARY` si la tool es `VERDICT_TOOL`,
reintenta UNA vez los `required` ausentes y en el último intento devuelve lo recibido (misma disciplina que el caller Anthropic)
*(corrector — orden de decisión por respuesta: `status 'failed'` → `response-failed:<code>` · ítem `message` con `content[].type ==
'refusal'` → `refusal` SIN reintento (antes caía en `no-function-call` y se reintentaba, contra (C.2); un `function_call` junto al
rechazo NO se acepta) · `status 'incomplete'` (`max_output_tokens`|`content_filter`) → `incomplete:<reason>` ANTES de parsear — un
`function_call` PARCIAL (arguments cortados) ya no cae en `arguments-unparseable` (R1: el kind lo nombra) y uno completo bajo status
incomplete tampoco se devuelve: la API declaró la respuesta truncada · sin `function_call` → `no-function-call` · arguments
ilegibles → `arguments-unparseable`)*.
`usage = {input_tokens, output_tokens, reasoning_tokens (output_tokens_details; YA incluidos en output_tokens — informativos, nunca
se suman aparte), cached_tokens (input_tokens_details), total_tokens}` (todo numérico) y `meta = {model_reported: resp.model, api:
'openai-responses', response_id, status, incomplete_reason, max_output_tokens}` *(corrector: el tope EFECTIVO enviado —
`audit.panel[].max_tokens` es null para el asiento OpenAI porque su tope es del transporte, y sin esto el registro no decía contra
qué tope se truncó un juez `incomplete:max_output_tokens`; `_meta_into` lo copia al intento como `attempts[].max_output_tokens?`)*.
`_openai_chat_call` = el `_openai_tool_call` de HOY byte a byte (`max_tokens 1200`) + `max_retries=0` + `meta` (con `max_tokens
1200` declarado igual → `attempts[].max_tokens?` — *corrector*); el nombre viejo `_openai_tool_call` se conserva como alias del despachador.
*(C.2 vocabulario)* `class CallerError(RuntimeError)` con `.kind` y `legacy_type_name = 'RuntimeError'`; `audit()` escribe
`attempts[].error = f"{getattr(e,'legacy_type_name',type(e).__name__)}: {str(e)[:200]}"` — el string de hoy queda BYTE A BYTE
*(corrección del juez: sin esto todo `error` cambiaría a 'CallerError: …')* — y `attempts[].error_kind = getattr(e, 'kind',
'unclassified')`. `FAILURE_KINDS_EXACT = ('no-api-key', 'sdk-unavailable', 'network', 'refusal', 'no-function-call',
'arguments-unparseable', 'verdict-off-vocabulary', 'unknown-family', 'incomplete:max_output_tokens', 'incomplete:content_filter',
'unclassified')`, `FAILURE_KIND_PREFIXES = ('http-', 'response-failed:', 'required-missing:')`,
`failure_kind_in_vocabulary(kind)` (el predicado del gate de paridad, como `plan_state_in_vocabulary`). Clasificación por
duck-typing (`status_code` → `http-<code>`; clase `APIConnectionError`/`APITimeoutError` o `TimeoutError`/`OSError` → `network`) para
que el smoke las simule sin importar `openai`. **El caller Anthropic gana los MISMOS kinds sin cambiar sus mensajes:** HTTP →
`http-<code>`; URLError → `network`; `stop_reason 'max_tokens'` → `incomplete:max_output_tokens` (mismo literal que Responses: la
webapp glosa UNA palabra); `stop_reason 'refusal'` (clasificadores de Opus 5, HTTP 200) → `refusal` *(corrector: y en Responses el
ítem `message` con `content[].type 'refusal'` — el kind es de AMBOS transportes, como lo presenta `FAILURE_KINDS_EXACT`)*; sin
`tool_use` →
`no-function-call`; veredicto fuera → `verdict-off-vocabulary`. Reintento de TRANSPORTE una vez en `http-429/500/502/503/529` y
`network` (backoff como hoy); reintento de CONTENIDO una vez en `incomplete:*`, `no-function-call`, `verdict-off-vocabulary`,
`arguments-unparseable` (= el 'no valid forced tool_use' de hoy); **`refusal` y `http-4xx` NO se reintentan** (un clasificador
determinista no cambia de opinión; 400/401/403/404 son configuración). El vocabulario viaja congelado en
`audit.failure_kinds_vocabulary {exact, prefixes, rule}`. *(C.3 despacho)* `_default_caller(member, system, user_text)` despacha por
`member['api']` (un panel legado sin `api` lo infiere de la familia: `api_source 'inferred-from-family'`); `openai-responses` →
`_openai_responses_call`, `openai-chat-completions` → `_openai_chat_call`, `anthropic-messages` → `_anthropic_tool_call(...,
max_tokens=member['max_tokens'], return_meta=True)`, `family 'unknown'` → `CallerError('unknown-family')`. **Default
`WITT_OPENAI_API=table`** *(síntesis, contra dos diseños: la decisión tomada dice que el panel CONSERVA gpt-4o hasta el smoke vivo;
conmutar el transporte del juez actual el día del redeploy añade un punto de fallo — 100% REVISE estructural si algo difiere — sin
beneficio; `responses` fuerza el ensayo con gpt-4o cuando Emmanuel lo decida y `chat-completions` es el kill-switch byte a byte)*.
`WITT_OPENAI_TIMEOUT_S` (default 120 = hoy) es el timeout del juez OpenAI; regla declarada: `(1 + WITT_JUDGE_RETRIES) ×
timeout × 2 paneles ≤ WITT_REAP_STALE_S (900)` — con retries 1 y 120 s son 480 s; G3 mide la latencia de Astra con
`max_output_tokens 4000` y, si rebasa, Emmanuel sube el timeout hasta 225 s sin tocar el reaper.
*(C.4 el pensamiento de Opus 5 — lo que ningún diseño decidió)* Las llamadas Anthropic siguen OMITIENDO `thinking`: en g2 eso es
adaptativo por default de la API (medición honesta: el modelo piensa lo que decide, los tokens de pensamiento se facturan como
salida y quedan DENTRO de `usage.output_tokens`), en g1 es "sin pensar" como hoy — el cuerpo de la petición NO cambia entre
generaciones salvo `max_tokens`. **Los TOPES suben en g2** (tabla (A): elicitación 300 → 2000, planner/question 1200 → 4000, síntesis
2500 → 8000, jueces 1200 → 4000): son techos, no gasto; con 300 la mini-llamada de confianza se truncaría por pensamiento en cada
corrida. `WITT_ANTHROPIC_EFFORT` (default vacío → `output_config` NO se envía → default de la API `high`) y
`WITT_ANTHROPIC_EFFORT_ELICIT` (override sólo para `CONF_TOOL`: la mini-llamada de 300 tokens útiles es donde pensar a `high` es
gasto puro) se envían como `output_config: {effort}` SÓLO a modelos con `thinking_default 'adaptive'` en la tabla. **No se envía
`thinking {type:'disabled'}`** (dos modos de falla documentados: tool call como texto y fuga de etiquetas; la referencia recomienda
pensamiento encendido + `effort` bajo). **Anthropic SÍ reporta el desglose de pensamiento** *(corrección del orquestador
2026-09-15 contra la doc oficial: `usage.output_tokens_details.thinking_tokens` "reports how many of the billed output tokens were
internal reasoning")*: el caller aplana `usage.output_tokens_details.thinking_tokens` → `usage.thinking_tokens` (numérico,
informativo, YA dentro de `output_tokens`; ausente si la API no lo manda — jamás 0 inventado), simétrico al `reasoning_tokens` de la
Responses API (la webapp glosa UNA palabra: "tokens de razonamiento, ya contados en la salida"); `frozen.models.ran.*` declara
`thinking_state 'adaptive-by-api-default (tokens dentro de output_tokens)' | 'off-by-model-default'` por tabla. LG1 mide en vivo, con los schemas REALES forzados, que Opus 5 devuelve
`tool_use` con todos los `required` bajo estos topes, y compara `output_tokens` contra la mediana 4.8 de `synthesize_pass1`.

**(D) Cuórum por FAMILIAS y LENTES en `audit()`.** Firma `audit(claim, evidence, deterministic_checks=None, required_because='',
panel=None, caller=None, min_valid=3, judge_retries=None, min_families=None, min_lenses=None, directives=None)`; `panel = panel or
models.panel(directives=directives)` EN LA LLAMADA. Tras `valid`: `families_valid = sorted({r['family']} − {'unknown'})`,
`n_families_valid`, `lenses_valid`, `n_lenses_valid`, `panel_single_family = n_families_valid <= 1`, `quorum = {n_valid, min_valid,
min_families: {value, source}, min_lenses: {value, source}, families_present {family: n}, lenses_present[], n_valid_ok,
families_ok: bool|null (null = gating apagado), lenses_ok: bool|null, families_gating, lenses_gating, ok, failed: ('min_valid' |
'families' | 'lenses')[], rule: QUORUM_RULE, decided_by 'code'}` con `QUORUM_RULE` *(corrector: el literal que viaja con el dato es
el de `composite_auditor.QUORUM_RULE`; el del borrador gateaba con min=1, el código no — mismo veredicto, literal distinto)* =
'n_valid >= min_valid AND (NOT families_gating OR n_families_valid >= min_families) AND (NOT lenses_gating OR n_lenses_valid >=
min_lenses); *_gating = (min >= 2): 0|1 = kill-switch declarado (>= 1 es tautológico con n_valid >= 1) — con ambos apagados la regla
es EXACTAMENTE la de f57a3d3'. `WITT_PANEL_MIN_FAMILIES` default **2**, `WITT_PANEL_MIN_LENSES`
default **3** (= mínimo Mode 1 "three DISTINCT adversarial lenses"); `0` o `1` = kill-switch declarado (`gating false`; ≥ 1 es
tautológico); vacío/basura/negativo → default declarado; `min_families=`/`min_lenses=` del llamador → `source 'caller'`.
`¬ok` → `verdict 'REVISE'`, `panel_incomplete True`, **`panel_incomplete_reasons = quorum.failed`** (códigos CERRADOS, tipables;
los números viven en `quorum` — *síntesis: contra los literales con cifras del ganador*); `ok` → worst-of-N intacto
(`APPROVE_DECLINE` ADR-0058 se preserva). Con `MIN_FAMILIES ∈ {0,1}` y `MIN_LENSES ∈ {0,1}` el veredicto es EXACTAMENTE el de hoy
(golden en smoke). En `runs.execute_run` el REVISE con `panel_incomplete` sigue SIN revisión (ADR-0067) y `revision.skipped_reason
= 'panel_incomplete (<failed unidos por ", ">) — el REVISE es estructural (jueces caídos o sin diversidad), no un hallazgo sobre la
respuesta; la revisión no aplica'`; el literal viejo sigue válido en registros 1.9. `stage.audit.verdict` += `families_valid,
n_families_valid, lenses_valid, n_lenses_valid, panel_incomplete, panel_incomplete_reasons`. `audit_initial` (ADR-0067) copia además
`families_valid, n_families_valid, lenses_valid, n_lenses_valid, quorum, panel_incomplete?, panel_incomplete_reasons?`.
`apply_to_bundle` copia `families_valid, n_families_valid, lenses_valid, n_lenses_valid, panel_single_family, quorum,
panel_incomplete_reasons?, panel_source, failure_kinds_vocabulary` al `bundle['audit']`. Filas del panel += `family_source, api,
api_source, reviewer_source, max_tokens`; `attempts[]` += `error_kind` (sólo errored), `model_reported?`, `api?`,
`max_output_tokens?` (Responses) | `max_tokens?` (chat) *(corrector: el tope efectivo del juez OpenAI)*. Frontera declarada:
tras el retiro de haiku dos asientos `claude-sonnet-5` con lentes distintas dan `lenses_valid 4` y `families_valid 2` pero la
independencia DENTRO de Anthropic baja (mismo modelo, dos prompts) — se declara en `panel_duplicate_models[]`, no se disimula.

**(E) Retiro de haiku: la tabla declara el sucesor (DATO), la env lo ejecuta (ACTO), el aviso llega 30 días antes, y el
automatismo es opcional con freno.** *(síntesis entre los dos jueces: doctrina §7 — un cambio de composición del panel corta la
serie de calibración y no debe ocurrir sin autor; pero Emmanuel ya decidió el sucesor y no tiene por qué recordar una fecha.)*
Default `WITT_PANEL_AUTO_RETIRE=0`: el asiento no cambia solo; `models.retirement_due(today)` produce el aviso MEDIDO
`'retirement-due: claude-haiku-4-5-20251001 en judge.evidence-grounding (retire_not_before 2026-10-15, faltan N días; sucesor
declarado claude-sonnet-5 — fijar WITT_JUDGE_GROUNDING=claude-sonnet-5 o WITT_PANEL_AUTO_RETIRE=1)'` desde 30 días antes, y
`'past-retirement: …'` después, en `stage.models.warnings[]`, `/config-history.current.warnings[]` y `consulta_sistema.config`.
Con `WITT_PANEL_AUTO_RETIRE=1` y `today ≥ retire_not_before`, `panel()` sustituye el asiento (`reviewer_source 'auto-retire:
claude-haiku-4-5-20251001->claude-sonnet-5'`, `seat_substitutions[] {seat, retired, retire_not_before, successor, applied True}`)
y — para que la bitácora no quede ciega justo ahí — **`config_ledger_observe(snapshot)` al inicio de cada `execute_run`** compara
`panel_signature` y los campos del snapshot con `_LEDGER_STATE.last` y appendea filas `changed_by 'system:runtime-diff'` si
difieren (coste: un dict compare por corrida; escribe sólo en cambio). `today` es parámetro (los smokes lo fijan; producción = fecha
UTC del proceso). E2 queda como decisión mínima con default.

**(F) `root_run_no` nace en la BD, no en la vista.** `db._list_select()` y `db.get_run()` incorporan `root = runs.alias('root')`
con `outerjoin(root, root.c.run_id == runs.c.thread_id)` y la columna `root.c.run_no.label('root_run_no')` — UNA definición por
consulta, ambas la sirven por construcción (lección ADR-0055/0076); `app._run_view` NO cambia (passthrough: la llave fluye) →
`RunView.root_run_no: int|null` en lista, detalle, `POST /runs` y `/runs?thread=`. Raíz: == su `run_no`; hijo de raíz VIRTUAL
(padre pre-ADR con `thread_id NULL`): el JOIN encuentra al padre por `run_id` → su `run_no`; corrida pre-ADR: `null` declarado,
jamás rellenado. `runs.new_run` añade `run_no` y `thread.root_run_no` al evento `run.state {queued}` (`db.get_run(run_id)` tras el
INSERT: la fila ya trae el JOIN; `db.create_run` ya devuelve el `run_no` propio). `frozen.thread.root_run_no` (`_root_run_no`) no
cambia.

**(G) `GET /threads?mine=&limit=&after=` (NUEVA, declarada ANTES de `/threads/{thread_id}`).** `db.threads_index(user_id=None,
limit=50, after=None)`: UNA consulta `GROUP BY runs.thread_id, root.run_id` (agrupar por la PK del alias hace que Postgres acepte
`root.*` por dependencia funcional; SQLite lo tolera — declarado, G7 lo mide en Postgres) sobre `runs.thread_id IS NOT NULL` con
`outerjoin` a la raíz: `COUNT(*) n_turns_counted`, `SUM(CASE state='closed')`, `COUNT(frozen_record_json) n_with_record`,
`MAX(turn_no)`, `MIN/MAX(created_at)`, columnas de la raíz (`run_no, question, user_id, state, created_at, thread_id, root_question_id`);
`root.thread_id IS NULL` ⇒ raíz VIRTUAL pre-ADR. Orden `root_run_no DESC NULLS LAST, thread_id` (la identidad de una investigación
es su T-N); cursor `after` = `root_run_no` EXCLUSIVO; `limit_cap = RUNS_LIST_CAP` (50, reutilizado); `has_more` MEDIDO con
`limit+1`; una segunda consulta LIGERA (sin blobs) sobre los `thread_id` de la página para `authors[]`, `origins{}`, `states{}` y
`last_turn {run_id, run_no, turn_no, state}` (agregación en Python sobre ≤ 50 hilos: sin `string_agg`/`group_concat`, dialecto
neutral). **`n_turns` es IGUAL al de `/threads/{id}`** *(síntesis: la raíz virtual se cuenta +1 como hace `get_thread`; dos puertas
jamás dan dos números)* y `root_counted: false` declara CÓMO entró al GROUP BY. `mine` = investigaciones con ≥ 1 turno del usuario
de sesión (`mine_rule` declarada; las multi-autor existen). Sin `gap_flags_union` ni `total_cost_usd` (abren blobs por turno:
`costs 'not-aggregated (GET /threads/{id})'`). Fila: `{thread_id, root_run_id, root_run_no, label 'T-<n>'|null,
root_pre_adr_0079, root_counted, root_question (≤ 120), root_user_id, root_state, root_question_id, n_turns, n_closed,
n_with_record, n_turns_without_record, last_turn_no, first_created_at, last_created_at, last_turn, authors, origins, states}`. Sobre:
`{threads, n, limit, limit_cap, after, has_more, next_after, order, cursor_rule, mine, mine_rule, n_turns_rule, n_threads_total,
n_runs_without_thread, n_runs_without_thread_rule, costs}` *(corrector: las tres `*_rule` viajan en
`db.THREADS_INDEX_ENVELOPE_FIELDS`; `root_pre_adr_0079` es TRI-estado `true | false | null` — null = la fila raíz NO existe — no
boolean)*.
`limit < 1` → 400; `after` no entero → 400/422; sin token → 401.

**(H) `/usage` agrega por ETAPA y por MODELO×ETAPA.** Sobre los mismos `usage_json` que ya recorre: `by_stage {<stage de
TOKEN_STAGES>: {in, out (suma sólo de enteros), n_runs_measured, n_runs_null, states {<literal>: n}, model_split {model: {in,out}} |
null, estimated_cost_usd | null, price_state ∈ priced|missing|mixed|stage-without-model|not-measured}, embed {tokens, n_runs}, _sum
{in, out}}` *(corrector: `not-measured` = etapa sin NINGUNA corrida medida en el periodo (`n_runs_measured 0`) → USD null; antes una
suma vacía salía `0.0 'priced'` — 0 medido ≠ null no medido; M8 lo glosa "[?] etapa sin medición en el periodo"; `states` puede
traer además el literal del agregador `absent-in-record` = la etapa no viene en `by_stage` de ese registro)*;
`model_split` sale de `by_stage[stage].model` (plan/synth/elicit/revision, desde 1.9) y de **`by_stage.panel.by_model {reviewer:
{in,out}}` (NUEVO en `runs._usage_by_stage`, 1.10: el bucle L1540-1544 ya itera las filas; `Σ == panel.in/out` como check)** —
*injerto: opus-5 será sintetizador Y juez correctness; sólo la partición por etapa los separa*; registros 1.9 sin `panel.by_model`
suman su panel en `by_model_stage._unattributed.panel {in, out, n_runs}` (declarado, jamás repartido). `by_model_stage {<model>:
{<stage>: {in,out}}}`, `by_model_stage_coverage {n_runs_with_panel_by_model, n_runs_without}`, `n_runs_with_by_stage`,
`n_runs_without_by_stage` (pre-1.9 ≠ gasto cero), `n_runs_by_stage_mismatch` (corridas con `by_stage_sum_matches_by_model false`),
`by_stage_class 'MEDICION (tokens) · PROYECCION (USD con precios de hoy)'`. `by_model[m]` += `family, known`; `models_catalog {model: {family, api, status, known, generation: string[], price_state}}` desde
la tabla *(corrector: `generation` es la LISTA de generaciones donde el id es default — `[]` si ninguna)*;
`model_generation_current`. USD por etapa sólo cuando
TODOS sus tokens tienen modelo con precio; si no `null` + `price_state` — nunca 0. `totals/by_user/most_expensive` byte-iguales a hoy.

**(I) `/config-history` = archivo (ATESTIGUADA) + tabla `config_history` en BD (MEDICIÓN) + estado actual, sin mezclar formas.**
Tabla NUEVA `db.config_history` (`create_all`, sin ALTER): `id PK autoincrement · recorded_at DateTime(tz) · field String(64) ·
value Text · previous_value Text NULL · source Text · changed_by String(64) · scope String(24) · generation String(32) · boot_id
String(32) · note Text NULL`; índice `ix_config_history_field_recorded (field, recorded_at)`. `db.config_ledger_last_by_field()`,
`config_ledger_append(rows) -> {n_written, rejected[]}` (rechaza y declara cualquier `value` que parezca secreto: `sk-`, `key`,
`token` — cinturón), `config_ledger_list(limit=500)`. **`app.config_ledger_boot()`** (función llamable DIRECTA — los smokes HTTP
construyen `TestClient(app)` SIN lifespan, `smoke_runs_thread_http.py:128` lo declara; el lifespan sólo la cablea tras
`db.init_db()` y antes de `start_workers`): calcula `models.snapshot()` (campos cerrados: `model_generation, table_version,
panel_signature, role.synthesizer/planner/elicitation/question_agent, panel.correctness/overclaim/evidence-grounding/reproducibility,
panel.min_families, panel.min_lenses, panel.auto_retire, openai.api, openai.store, openai.max_output_tokens, openai.timeout_s,
openai.reasoning_effort, anthropic.effort, anthropic.effort_elicit, judge.retries, prices.as_of, contract.render_contract_version,
embed.model, competence.gate, search.harness, revision.cycle` — cada uno `{value, source}`), compara con la ÚLTIMA fila por campo y
APPENDEA una fila por campo que cambió (primer arranque: todas, `previous_value null`, `note 'first-boot-snapshot'`);
`changed_by 'system:boot-diff'`, `actor_state 'not-observable (env set outside the service)'` — no se afirma QUIÉN cambió la env.
`config_ledger_observe(snapshot)` (E) usa la misma comparación con `changed_by 'system:runtime-diff'`. Nunca reescribe ni borra;
un fallo del ledger JAMÁS impide el arranque (`try/except` → `_LEDGER_STATE`). Kill-switch `WITT_CONFIG_LEDGER=0`: cero
escrituras. **Invariante declarado (Context 10):** toda env cambia sólo con reinicio, así que el diff al boot es COMPLETO para
envs; lo que el ledger NO puede registrar: un `min_families=` pasado por un llamador (viaja en `audit.quorum.source 'caller'`,
no es configuración del servicio) y el reloj (el auto-retire lo cubre `runtime-diff`). La ruta responde `entries` (archivo, byte-
compatible) + `entries_class 'atestiguada (archivo human-maintained; fechas de ADRs)'` + `ledger[]` (`recorded_at DESC`,
`ledger_limit 500`) + `ledger_state ∈ 'ok' | 'kill-switch WITT_CONFIG_LEDGER=0' | 'table-missing' | 'error: <tipo>' | 'not-booted
(lifespan no corrió: config_ledger.boot() no se ha llamado)'` *(corrector: el quinto literal es el estado ANTES del lifespan — un
`TestClient(app)` sin lifespan lo sirve; `config_ledger.STATES_RULE` lo lista)* + `ledger_writer` (el `state_view()` del escritor) +
`ledger_encoding` ('text: str tal cual · bool → true|false · None → null · otros → JSON': `value`/`previous_value` son TEXTO
codificado → `ConfigLedgerRow.value: string`) + `ledger_scope_rule` + `current {recorded_at, boot_id, generation,
generation_source, table_version, table_as_of, panel_signature, fields, warnings, unknown_models, actor_state}` *(corrector:
`actor_state` vive UNA vez en `current`, no por fila del ledger; `fields['openai.api'].value ∈ table|responses|chat-completions` es
la ELECCIÓN de env, no el transporte efectivo — ése viaja por asiento en `audit.panel[].api` / `stage.models.panel[].api`)* +
`provenance.db {table, n_rows, last_recorded_at}` + `model_generation`; `provenance/user_history/store_version_history/refreshed_at` sin cambio.
`_embed_model_changed_at` sigue leyendo el archivo. `consulta_sistema` sección `config` += `models_effective` (= `current`) y
`ledger {n_rows, last_recorded_at, state}` para que la consulta del sistema y M6 digan lo mismo. `rag_index/config_history.json`
gana DOS entradas atestiguadas (append, nunca reescribe la de `embed_model`): `{field 'model_generation', value 'g2-2026-09',
changed_at '<fecha Accepted>', source 'ADR-0081 (efectivo al redeploy; la fecha MEDIDA vive en la tabla config_history)'}` y
`{field 'budget_approval', value '<texto literal de Emmanuel>', changed_at '<fecha>', source 'Emmanuel en chat <fecha> (brief v3
R6/§190: ADR-0081 registra la aprobación presupuestal explícita)'}` — la segunda espera E3. *(síntesis: la bitácora derivada de
`usage_json` por etapa ("observed-registry") NO entra a 0081 — ver (L).)*

**(J) Contrato 1.10 (aditivo), eventos, históricos.** `RENDER_CONTRACT_VERSION = "1.10"` — etiqueta que la webapp sólo imprime
(`Hoja.tsx` L3182) y `gen_fixtures.py` asserta por igualdad (L578); la siguiente será `"1.11"`. **frozen** += `models` (B) ·
`audit`/`audit_initial` += (D) · `audit.panel[]` += `family_source, api, api_source, reviewer_source, max_tokens`; `attempts[]` +=
`error_kind?, model_reported?, api?, max_output_tokens? (Responses) | max_tokens? (chat)` *(corrector)*; `usage` puede traer `reasoning_tokens` (OpenAI), `thinking_tokens` (Anthropic),
`cached_tokens, total_tokens` (numéricos; los de razonamiento YA están dentro de `output_tokens`) ·
`revision.skipped_reason` literal nuevo (D) · `answer` += `model_source, model_reported, relation` · `token_usage.by_stage.panel` +=
`by_model`; `by_stage.<synth|elicit|plan|revision>` += `model_source` *(corrector: `by_stage.elicit_*.model`/`model_source` salen
SÓLO de `elicitation_model`/`elicitation_model_source` — null declarado con un stub que no los reporta, jamás el del sintetizador;
lo mismo en `stage.confidence.elicit.usage.model`)* · `plan.judgment.planner` += `model_source, model_reported?, relation?`
*(corrector: lista completa)* (planes hechos con 1.10) · `plan.audit` += `panel_resolved[]` · `epistemic_summary` += `model_generation, panel_n_families_valid`. **Eventos** nuevos:
`stage.models`; ampliados: `run.state{queued}.{run_no, thread.root_run_no}`, `stage.synthesize.start{model, model_source,
generation}`, `stage.audit.judge{family, api, api_source, reviewer_source}`, `stage.audit.verdict{families_valid, n_families_valid,
lenses_valid, n_lenses_valid, panel_incomplete, panel_incomplete_reasons}` *(corrector: el EVENTO trae `panel_incomplete_reasons`
SIEMPRE — `[]` = cuórum ok — mientras `frozen.audit.panel_incomplete_reasons` sólo existe con ¬ok: la webapp tipa `[]` como "sin
razones" en el evento y la ausencia como "cuórum ok" en el registro; dos formas declaradas, no una contradicción)*. **Fuera del
pipeline:** `question_agent.draft_question` base += `model_source, generation, model_reported?, relation?,
model_requested_by_drafter?` *(corrector: `relation` acompaña a `model_reported`; `model_requested_by_drafter` se declara cuando el
redactor pidió otro modelo que el rol resuelto — inyección declarada, no corregida)*; `GET /notes/questions/spec` += `model_source,
generation`. **Históricos: NADA se
recalcula ni se backfillea.** Registros < 1.10 no ganan `models` ni `audit.families_valid`; la webapp y el PDF los leen como 'NO
INSTRUMENTADO (contrato < 1.10)'; su modelo observado vive donde ya vive (`answer.model`, `by_stage[*].model`, llaves de `by_model`).
`prices()` conserva TODOS los ids históricos (opus-4-8, haiku, gpt-4o, fable) para que `/usage` recotice sin `missing_price`. La
única novedad de esquema es la tabla `config_history` + el JOIN (SELECT); `_migrate` no gana ALTER.

**(K) El HUECO del consejo (ADR-0082), declarado sin implementarse.** `models.panel(env, today, directives=None)` acepta
`directives` y hoy lo ignora declarando `panel_source {generation, table_version, panel_signature, directives_state
'empty-until-ADR-0082', council_hook {state 'not-available (ADR-0082)', accepts 'directives[] → asientos/lentes por nicho',
lens_scope 'global'}, lens_charges_source 'composite_auditor._LENS_CHARGES'}`; `audit(directives=None)` lo pasa y lo congela en
`audit.panel_source`. Las lentes siguen en `_LENS_CHARGES`; una lente por nicho (N1–N6, CLAUDE.md §3) será una FILA más ahí, no otra
estructura. Mismo patrón que `competence.council_uncovered_must`.

**(L) Lo que NO se hace y por qué NO es deuda** *(injerto del diseño diff-mínimo)*: (a) validación en arranque contra `/v1/models`
(brief §11) — red en arranque viola §6 no-hang; la sustituyen la tabla + LG1/G2/G3; (b) modo `forced=False` + `strict` por bandera
para Fable — Fable está FUERA por decisión; código muerto hasta un ADR con held-out; (c) `gpt-5.6-sol` como puente — decidido en
contra; su precio queda en tabla por si aparece en un registro; (d) `WITT_PANEL_SPEC` (panel entero por CSV) — una env por lente
basta y cambiar el NÚMERO de lentes es obra de ADR-0082; (e) `WITT_PANEL_MIN_VALID` como env — `min_valid=3` sigue parámetro,
declarado en `quorum.min_valid`; (f) `WITT_OPENAI_STRICT` — se sabe que rompe `VERDICT_TOOL`; (g) `thinking {type:'disabled'}` en
Anthropic — dos modos de falla documentados; el freno es `WITT_ANTHROPIC_EFFORT` o `WITT_MODEL_GENERATION=g1-2026-08`; (h)
`fallbacks` server-side de Opus 5 — un cambio de modelo en el servidor rompería la medición `requested/reported`; un `refusal` es
un juez errado declarado, no un modelo sustituido en silencio; (i) "observed-registry" (transiciones de `by_stage[*].model` por
`run_no` sobre `db.runs_usage()`) — mide algo valioso (la PRIMERA corrida que usó cada modelo) pero recorre todo `usage_json` por
GET, no registra cuórum/transporte/retiro como cambios, y lo que mide ya viaja en `frozen.models.ran` (1.10) y `by_stage[*].model`
(1.9): va a ADR-0087 como serie por `run_no`; (j) PDF — `models`, `audit.quorum`, `by_stage.panel.by_model` y las 20 llaves
nominales van a ADR-0083 con línea de deuda `[pdf]` (`record_pdf.py` no se toca: cero conflicto de dueño en paralelo; el gate (D)
reportará `models` como OMITIDO EN PDF y esa línea ES el mecanismo previsto — *síntesis: se respeta la frontera del alcance; la
fila del pie que un diseño proponía queda como opción de ADR-0083*); (k) `model_generation` como dimensión de `/calibration` y
`question_calibration` — ADR-0087 lee `frozen.models.generation` y `panel_signature` que aquí nacen; (l) TTL-cache de
`/config-history` — 500 filas, una tabla; si midiera lento, patrón `_TAXONOMY_CACHE`; (m) costo por hilo en `GET /threads` — vive
en `/threads/{id}`; (n) migración de `evaluation/run_held_out.openai_verdict` a Responses — su `JUDGE_PANEL`/`SYNTH_MODEL` sí
salen de la tabla y su juez OpenAI delega en `composite_auditor._default_caller` (una línea; sin ella, con Astra fallaría por
chat.completions), pero el script GASTA y no se corre en la obra.

**(M) Invariantes operativos.** (1) Toda env implica reinicio (Context 10); el ADR y el compose lo dicen. (2) Kill-switches por env
con default declarado que devuelven el comportamiento de `f57a3d3`: `WITT_MODEL_GENERATION=g1-2026-08` (los 8 defaults y los 5
topes de hoy) · `WITT_OPENAI_API=chat-completions` (el caller de hoy) · `WITT_PANEL_MIN_FAMILIES=0` · `WITT_PANEL_MIN_LENSES=0`
(regla de hoy) · `WITT_CONFIG_LEDGER=0` (cero escrituras) · `WITT_PANEL_AUTO_RETIRE=0` (default: nada cambia solo). Con los cinco
primeros, el frozen menos las llaves aditivas 1.10 tiene EXACTAMENTE el keyset y los valores de un frozen 1.9 — medido en smoke
*(corrector — tres excepciones DECLARADAS que el golden de keysets por bloque no ve: (i) el `usage` de TODA llamada Anthropic pasa
por `_numeric_usage` (`runs._anthropic_call` pide `return_meta=True` siempre): `service_tier`, `cache_creation`, `server_tool_use`
dejan de viajar en `audit.panel[].usage` / `attempts[].usage` / `answer.usage` / `usage_raw` — decisión (B), la webapp tipa
`Record<string, number>`; (ii) los mensajes `no-api-key` / `sdk-unavailable` son nuevos (fail-before-network): f57a3d3 dejaba que
`OpenAI()` lanzara `OpenAIError: Missing credentials…`, así que `attempts[].error` cambia aun con `WITT_OPENAI_API=chat-completions`;
(iii) `stop_reason 'refusal'` ya no se reintenta bajo g1 (f57a3d3 reintentaba todo no-tool_use) → `attempts[]` 1 vs 2)*.
(3) Smokes 100% offline con fakes: cliente Responses inyectable por `_openai_client`, `urllib.request.urlopen` bloqueado y contado
(= 0), `sys.modules` sin `openai` al terminar la sección, `mcp_cache` byte-idéntico. (4) Ningún literal de modelo fuera de
`models.py` (gate estático; exentos: `docs/`, `evaluation/runs/*.json`, fixtures/MANIFIESTO, comentarios `# models-literal-doc`).
(5) Todo gate EN VIVO lo corre Emmanuel tras el redeploy con `analysis/scripts/smoke_live_models.py`; ningún smoke del CI gasta.

**(N) Integración (S7).** Costuras mínimas, cada una documentada en el archivo del dueño: `frozen.models.panel ==
audit.panel_source` asientos (misma `models.panel()`); `stage.audit.judge.api == audit.panel[].api`; `db._list_select.root_run_no ==
runs._root_run_no` en las 21 corridas del pipeline; el snapshot del boot usa `models.snapshot()` sin re-derivar; retirar los stubs
que S5 haya usado contra firmas de S4; regenerar la tabla NO-SPEND con conteos MEDIDOS; correr `tools/parity_check.py` de la webapp
EN MODO LECTURA para listar los huecos que la webapp paga (esperados: ruta `GET /threads`, llave `models`, evento `stage.models`,
`[pdf] models`).

**(N·S7) Lo cosido y lo MEDIDO (integrador, 2026-09-15)** *(S7)*: (1) `frozen.models.panel_signature == stage.models.panel_signature ==
audit.panel_source.panel_signature` — `models.provenance_block` gana el parámetro aditivo `signature_roles=None` y `runs.execute_run` le
pasa los 8 roles del snapshot de `stage.models` (antes firmaba sólo con synthesizer/elicitation y las tres firmas de una misma corrida
diferían); los asientos coinciden por tres puertas (`frozen.models.ran.panel[].reviewer == audit.panel[].reviewer == stage.models.panel[]
.reviewer`) — medido en `smoke_run_pipeline`. (2) `stage.audit.judge.api == audit.panel[].api` por CONSTRUCCIÓN: `runs._judge_identity`
usa `composite_auditor._member_api` (la misma función con la que `audit()` escribe la fila) en vez de una inferencia propia. (3)
`db._list_select.root_run_no == runs._root_run_no` medido en TODAS las corridas del gate (64: raíces, hijos, hijos de raíz VIRTUAL y
pre-ADR `null == null`); `runs.new_run` lee `row['root_run_no']` de la fila del INSERT (S4) sin fallback silencioso. (4) El snapshot del
boot sigue siendo `models.snapshot()` vía `config_ledger.take_snapshot` con `runs.snapshot_extra()` como ÚNICA sede de los 4 EXTRA_FIELDS
(`config_ledger.default_extra(env=None)` delega; el espejo sólo sirve a un `env` inyectado). (5) Tolerancias de la obra RETIRADAS:
`runs._config_ledger_observe` importa `config_ledger` en DURO (antes `module-missing`); `config_ledger._db_has_ledger` y la rama
`AttributeError → table-missing` (S4 es dependencia dura: un build sin `db.config_ledger_*` reporta `error: AttributeError`, no finge
`table-missing`); `evaluation/run_held_out.openai_verdict` delega SIEMPRE en `composite_auditor._default_caller(…, tool=)` (el camino
legado de chat.completions se retiró: una firma sin `tool=` erra en voz alta); las ramas `[S4 pendiente]`/`S4_THREADS` de
`smoke_config_history_http` y `smoke_runs_thread_http` son ahora mediciones duras. Se CONSERVA la tolerancia por inspección de firma
de `runs._anthropic_call` / `question_agent._default_drafter` (`effort=`/`return_meta=` sólo si el caller los acepta): no es un stub
contra S2 sino la compatibilidad declarada en (B) con los fakes de 2-tupla de los smokes. (6) Gate estático M.4 en PASS (lista vacía):
los literales de `smoke_usage_http`/`smoke_config_history_http`/`smoke_config_ledger_db` (S5) pasaron a la tabla; tres menciones
DOCUMENTALES preexistentes llevan la marca `# models-literal-doc` (`analysis/scripts/lib/rag_backend.py` comentario 1536-dim,
`analysis/scripts/phase1_minimal_set_reground.py` y `evaluation/run_held_out_v2.py` docstrings). (7) `tools/parity_check.py` de la webapp
EN LECTURA (copia en scratchpad apuntando al worktree; la webapp no se tocó): 228 filas · 29 huecos · 26 declarados en deuda · 3 SIN
declarar y ESPERADOS = `[registro] models` (congela sin tipo), `[etapas] stage.models` (sin caso en Traza), `[pdf] models`; `GET /threads`
ya aparece con ranura en `api/types.ts` (literal fuera de `client.ts`, método no medido) y `/config-history` sigue en la deuda declarada.
(8) Conteos de la tabla NO-SPEND = MEDIDOS por S7 (arriba); `smoke_zfin_tool` y los smokes de tools necesitan en un worktree las copias
gitignored (`mcp_cache/`, `rag_index/curation/quarantine/`) del árbol principal — datos, no código.

## Consequences

- **Contrato: `render_contract_version` sube a "1.10"** — todo aditivo (lista en (J)). Ninguna llave cambia de dominio salvo
  `revision.skipped_reason` (gana un literal) y `attempts[].error` que CONSERVA su string. `FALLBACK_TRIGGERS` intacto (gate (E) de
  paridad sin cambio).
- **La webapp debe tipar y pintar** (`witt-webapp/src/api/types.ts`, todo `?`; regla de tres estados aplicada a lo nuevo:
  ausente = backend/contrato anterior, `null` = declarado, valor): (1) `RunView.root_run_no?: number|null` y
  `RunStateEventPayload.{run_no?, thread.root_run_no?}` — `Traza.tsx` pinta "Investigación T-<root_run_no> · turno k" desde la
  vista y desde `run.state{queued}` (fallback al `slice(0,8)` SÓLO cuando la llave está ausente; `null` = "raíz sin número",
  jamás "T-?" inventado); `ListaCorridas.investigacionDe` lee `r.root_run_no` en vez de buscar la raíz cargada. (2)
  `RegistroCongelado.models?: ModelsBlock` (forma exacta de (B); `ModelSource` union por prefijo `'env:' | 'default:' |
  'default-unset:' | 'default-invalid-env:' | 'auto-retire:' | 'plan_json' | 'plan_json (pre-1.10: source not recorded)' | 'no-plan'
  | (string & {})` *(corrector: = `models.SOURCE_PREFIXES` + `models.PLANNER_PROVENANCES`; `default-unset:` = sin env, default de la
  tabla — TODO registro por default lo trae en `generation_source`)*; `Relation = 'exact'|'prefix'|'different'|'not-reported'`) —
  Hoja sección NUEVA "Modelos": generación + fuente, tabla roles (rol · modelo · fuente glosada · familia · api · known/priced ·
  tope), tabla `ran` (etapa · pedido · reportado · relation: `prefix` NEUTRO, `different` objeción, `not-reported` gris;
  `thinking_state` con `'unknown-to-table'` — stub o id fuera de tabla — y `'not-applicable (…)'` en gris — *corrector*), panel con
  `panel_signature`; `audit.panel_duplicate_models` como aviso y `audit.panel_source.council_hook` en gris declarado *(corrector:
  estas dos viven en `frozen.audit`, NO en `frozen.models` — `models.provenance_block` emite exactamente `PROVENANCE_FIELDS`)*;
  ausente → "NO INSTRUMENTADO (contrato < 1.10)". (3) `AuditBlock` += `families_valid, n_families_valid, lenses_valid, n_lenses_valid,
  panel_single_family, quorum, panel_incomplete_reasons?: ('min_valid'|'families'|'lenses'|(string&{}))[], panel_source,
  failure_kinds_vocabulary, panel_duplicate_models: string[], panel_origin: 'caller' | 'models.panel(directives)'` *(corrector: las
  dos últimas ya las emite `audit()` y `_BUNDLE_AUDIT_KEYS_1_10` las copia)*; `PanelRow` += `family_source, api, api_source,
  reviewer_source, max_tokens`; `JudgeAttempt` += `error_kind?, model_reported?, api?, max_output_tokens?, max_tokens?`
  *(corrector: el tope efectivo del juez OpenAI)*; `usage` puede traer `reasoning_tokens` (OpenAI) / `thinking_tokens` (Anthropic) /
  `cached_tokens` / `total_tokens` — una sola glosa "tokens de razonamiento, ya contados en la salida" — Hoja §7: veredicto
  dice "n_valid válidos · N familia(s) [..] · lentes [..]"; con `panel_incomplete_reasons` pinta LOS CÓDIGOS glosados ("REVISE
  ESTRUCTURAL: una sola familia votó — el panel no puede aprobar" / "panel delgado" / "lentes insuficientes") y la prosa fija de
  `Hoja.tsx:2961` queda como fallback < 1.10; `error_kind` como palabra-máquina junto al error (glosa por vocabulario:
  `incomplete:max_output_tokens` → "el juez no cupo en el tope de salida — sube WITT_OPENAI_MAX_OUTPUT_TOKENS"); `api` por juez
  ("vía Responses API"). (4) `EpistemicSummary` += `model_generation?, panel_n_families_valid?` — ListaCorridas/Banco: "3/4
  válidos · 1 familia" (1 familia en ámbar: jamás aprueba). (5) Traza: caso NUEVO `stage.models` (roles con fuente, generación,
  `warnings` en ámbar glosados POR PREFIJO — vocabulario CERRADO `models.WARNING_PREFIXES`: `retirement-due:` (sucesor declarado,
  30 días), `past-retirement:` (asiento retirado sigue), `invalid-env:` (env rechazada, default en uso), `api-unverified:`
  (transporte no medido en vivo por este código — hoy opus-5 hasta LG1: aparece en el 100% de las corridas g2 por default, R14),
  `not-adopted:` — *corrector* — y `unknown_models` en rojo); `stage.synthesize.start` con `payload.model` + fuente;
  `stage.audit.judge` "intento N de M · <api> · <family>"; `stage.audit.verdict` con familias/lentes/reasons. El gate (C) FALLA si no
  existe el caso `stage.models`. (6) `client.investigaciones(opts?: {mine?, limit?, after?}): Promise<ThreadsIndex>` → `GET
  /threads`; `ThreadsIndex`, `ThreadIndexRow` (forma exacta de (G): el sobre trae también `cursor_rule`, `n_turns_rule`,
  `n_runs_without_thread_rule`; `root_pre_adr_0079: boolean | null`, null = raíz sin fila — *corrector*); Bitácora INVESTIGACIONES
  consume la puerta (paginación con
  `next_after`, tope `limit_cap`, `n_runs_without_thread` del SERVIDOR, `root_pre_adr_0079` → "raíz anterior al contrato") y conserva
  `agruparPorInvestigacion` SOLO como fallback declarado ante 404 (backend anterior). El gate (A) exige consumidor fuera de
  `client.ts`. (7) `client.historialDeConfiguracion(): Promise<ConfigHistory>` → `GET /config-history`; `ConfigHistory,
  ConfigLedgerRow, ConfigSnapshot` (forma exacta de (I)); M6 SISTEMA: SUSTITUIR la placa "no tiene puerta HTTP" (`Bitacora.tsx`
  L81-92, falsa) por (a) `current` con fuente por campo y `warnings`, (b) `ledger` (clase medición: `recorded_at`, `field`,
  `previous → value` — TEXTO codificado según `ledger_encoding` —, `source`, `changed_by`) con `current.actor_state` pintado UNA vez
  verbatim *(corrector: las filas no lo traen; vive en `current`)*, (c) `entries` del archivo (clase atestiguada, incluida
  `budget_approval`), (d) `ledger_state ≠ 'ok'` como placa declarada — incluido `'not-booted (…)'` *(corrector: el estado sin
  lifespan; un fixture generado con `TestClient` sin llamar `app.config_ledger_boot()` lo mostrará)*. Pagar la deuda: quitar `/config-history` de
  `tools/parity_debt.json`. (8) `UsageReport` += `by_stage?, by_model_stage? (con _unattributed?), by_model_stage_coverage?,
  n_runs_with_by_stage?, n_runs_without_by_stage?, n_runs_by_stage_mismatch?, models_catalog?, model_generation_current?,
  by_stage_class?`; `UsageByModel` += `family?, known?` — M8: tabla por etapa (in/out/n_runs_measured/n_runs_null — null ≠ 0;
  `price_state 'stage-without-model'` como "[?] sin modelo por etapa"; `'not-measured'` como "[?] etapa sin medición en el periodo"
  — USD null, jamás 0.0 — *corrector*; `models_catalog[m].generation` es `string[]` y `by_stage[etapa].states` puede traer
  `absent-in-record` — *corrector*), matriz modelo×etapa con `_unattributed.panel` pintado como
  "panel sin reviewer (registros 1.9): N corridas" jamás repartido, "corridas sin by_stage (pre-1.9): N" aparte;
  `familias-modelo.ts`: `familiaDe(modelo, catalogo?)` usa `models_catalog[modelo].family` cuando viaja y cae al regex DECLARADO
  cuando no (arregla `claude-fable-5-1` → "otros"). **Regla D18 (injerto):** la "familia" de `familias-modelo.ts`
  (opus/sonnet/haiku/gpt) es GRUPO DE DISPLAY; la familia de PROVEEDOR (`anthropic|openai`) llega SIEMPRE del servidor y jamás se
  infiere en el cliente. (9) `specDePregunta` += `model_source, generation`. (10) `parity_debt.json`: quitar `/config-history`;
  añadir `[pdf] models`, `[pdf] audit.quorum`, `[pdf] token_usage.by_stage.panel.by_model` → 'ADR-0083 (record_pdf.py no lo lee)';
  renombrar las 18 líneas 'ADR-0081/0083' → 'ADR-0083'. (11) `gen_fixtures.py`: `model="claude-opus-4-8"` (L253) → el modelo de
  `models.resolve_role('synthesizer')`; regenerar los 30 fixtures a 1.10 (assert L578 automático) + NUEVOS: `panel-una-familia.json`
  (OpenAI errored + 3 APPROVE → REVISE estructural `failed ['families']`) + `eventos-panel-una-familia.json`,
  `modelos-g1-kill-switch.json` (`WITT_MODEL_GENERATION=g1-2026-08`: el frozen menos llaves 1.10 = forma 1.9), `modelos-por-env.json`
  (`WITT_MODEL_SYNTH=claude-sonnet-5` → `source 'env:…'`; `OPENAI_JUDGE_MODEL=gpt-6-astra` → `api 'openai-responses'`),
  `threads-index.json` (`GET /threads` con raíz virtual y paginación), `config-history.json` (ledger first-boot + una fila de cambio
  + `ledger_state` kill-switch en un segundo fixture), `usage-by-stage.json` (3 `usage_json` mixtos: 1.10 con `panel.by_model`, 1.9
  sin él, pre-1.9 sin `by_stage`); el MANIFIESTO declara qué es real por el código y qué stub. *(corrector — condiciones NO
  declaradas antes, verificadas contra `gen_fixtures.py` @ `feat/adr-0080-paridad`: (a) `stage-models-warnings.json` depende del
  RELOJ (`execute_run` no acepta `today`): tras el 2026-10-15 sale `past-retirement`, no `retirement-due` — el generador fija la
  fecha (monkeypatch `models._as_date`) y el MANIFIESTO lo dice; (b) `config-history.json` exige llamar `app.config_ledger_boot()`
  antes del GET (o documenta `not-booted` como caso propio) y el kill-switch va con `_con_env WITT_CONFIG_LEDGER=0`; (c)
  `usage-by-stage.json` es STUB por `db.update_run(usage_json=…)`, declarado; (d) el generador quita `models.ENV_TABLE` del
  `os.environ` como hace con `ENV_ADR_0080` (las 21 env heredadas del shell contaminan la generación); (e) además de L253, los
  asserts de dict exacto con `claude-opus-4-8` (L1532 `usage == {in 30, out 3, model}`, L1625 `stage.synthesize.pass2`) rompen al
  pasar el default a la tabla: leerlos de `models.resolve_role('synthesizer')`)*.
- **Qué mide el gate de paridad** (`tools/parity_check.py`, sin cambio de mecanismo): (A) rutas `GET /threads` y `GET /config-history`
  con wrapper en `client.ts` y consumidor fuera; (B) `models` como llave top-level CONGELADA → TIPADA → LEÍDA en M4Hoja; (C)
  `stage.models` con caso en Traza; (D) `models` leída por `record_pdf.py` — NO lo será: línea de deuda declarada hacia ADR-0083 (el
  gate la reporta como hueco declarado, no como falla); (E) `FALLBACK_TRIGGERS` sin cambio. Extensión pequeña recomendada del
  check de fixtures: fallar si un fixture 1.10 trae `audit.families_valid` con literal fuera de `{'anthropic','openai'}`, un
  `models.roles.*.source` que no empiece por un prefijo de `models.SOURCE_PREFIXES` (y un `roles.planner.provenance` fuera de
  `models.PLANNER_PROVENANCES`) *(corrector: `default-unset:` / `auto-retire:` son legítimos — el check contra el `ModelSource` del
  borrador rechazaría registros válidos)*, o un `attempts[].error_kind` que no cumpla
  `failure_kind_in_vocabulary` (patrón del check (E): vocabularios del backend vs fixtures).
- **Protocolo de corte con la webapp (otro workflow en paralelo):** la FORMA de (B)–(J) se congela al cerrar S1/S2/S3 (commit del
  integrador con etiqueta `contract-1.10-frozen`); la webapp regenera `gen_fixtures.py` contra ESE SHA; hasta entonces su gate corre
  contra `f57a3d3`. Ningún cambio de forma después de S7 sin corrector declarado.
- **Deuda declarada aquí, no en la lista de gates en vivo:** PDF (ver (L.j)); "observed-registry" (L.i) → ADR-0087; timeout del juez
  Anthropic sigue 120 s fijo (los jueces Anthropic no razonan por tope de 4000 con `effort` default; si LG1 midiera latencias > 120
  s, es una env más en corrección, no un cambio silencioso).
- **Riesgos** (con mitigación, cada uno con dueño): R1 Astra truncado por `max_output_tokens` → `incomplete:max_output_tokens` en
  cada corrida → 100% REVISE estructural (fail-loud, costoso): G3 obligatorio antes de flipar `OPENAI_JUDGE_MODEL`; default 4000;
  el kind lo nombra. R2 Transporte Responses NO medido en vivo en esta obra (la forma sale de los tipos Stainless del SDK 2.53.0):
  un cambio de `output[].type` cae en `no-function-call` declarado, nunca en veredicto fabricado; G2 con gpt-4o (≈0.01 USD) valida
  el transporte aparte del modelo. R3 Opus 5 piensa por default: topes subidos; `usage.output_tokens` de `synthesize_*` deja de ser
  comparable con la serie 4.8 (se declara con `generation`; ADR-0087 segmenta); LG1 mide truncación y latencia; el freno es
  `WITT_ANTHROPIC_EFFORT=low|medium` o g1. R4 OpenAI es punto único de fallo del cuórum: su caída = 100% REVISE estructural hasta que
  vuelva o el operador baje `WITT_PANEL_MIN_FAMILIES` — consecuencia literal de la decisión; se declara, no se suaviza. R5 Dos
  jueces sonnet-5 tras el retiro bajan la independencia intra-Anthropic: `panel_duplicate_models` lo declara. R6 `store=False` no
  es ZDR; el perímetro de datos hacia OpenAI NO cambia respecto a hoy (gpt-4o ya recibe claim + evidencia). R7 GROUP BY en Postgres
  (dependencia funcional): agrupar por `root.run_id` la satisface; G7 lo mide; un olvido sale 500 en prod, no en SQLite. R8 El
  JOIN toca TODAS las lecturas de `runs`: índice `ix_runs_thread_id` cubre; una sola definición evita la asimetría lista/detalle
  (smoke la compara campo a campo). R9 Ledger al boot con dos procesos duplicaría `first-boot` (append-only, `boot_id` distinto):
  `--workers 1` lo evita; declarado *(corrector: el riesgo de dos HILOS worker en un proceso — `WITT_RUN_WORKERS` default 2, dos
  `execute_run` observando el mismo cambio contra la misma baseline — se CERRÓ: `config_ledger.boot()/observe()` serializados por
  `_LOCK`, medido con 2 hilos en `smoke_config_history_http`: exactamente 1 fila por campo cambiado)*. R10 Smokes/fixtures que pinean `claude-opus-4-8` (`smoke_run_pipeline` L251/932,
  `smoke_run_recovery` L202/300, `gen_fixtures` L253) ROMPEN al cambiar el default: S3 los pasa a la tabla; la webapp regenera.
  R11 Alias fechado → `relation 'prefix'` en el 100% de las corridas: la paridad lo fija NEUTRO. R12 Costo: opus-5 = 4.8;
  Astra ≈ 4×/5× gpt-4o + reasoning → ≈ +0.05–0.15 USD por corrida (PROYECCIÓN sobre 10k in / 1k out + reasoning); M8 lo mide por
  etapa; E3 registra la aprobación. R13 `/usage.by_stage` recotiza con precios de HOY mientras `totals` suma proyecciones
  CONGELADAS: pueden diferir; `by_stage_class` y `price_state` lo dicen. R14 *(corrector)* `stage.models` abre en ámbar (`level
  'warning'`) en el 100% de las corridas g2 por default mientras opus-5 tenga `api_verified False` (`api-unverified:` es honesto:
  nada se afirma sin medirse); desaparece cuando LG1 mida y la fila de la tabla pase a `api_verified True` con `verified_on` nuevo
  (corrección declarada en `models.py`) — no se baja a `info` ni a una lista aparte para no esconder que el modelo de producción
  no ha sido medido por este código.

## Tabla de env (todas con default declarado; lectores tolerantes en tiempo de llamada; toda env = reinicio)

| Variable | Default | Lector | Efecto / fuente declarada |
|---|---|---|---|
| `WITT_MODEL_GENERATION` | `g2-2026-09` | `models.resolve_role` | generación de defaults y topes; `g1-2026-08` = hoy byte a byte; inválida → `default-invalid-env` |
| `WITT_MODEL_SYNTH` / `_PLANNER` / `_ELICIT` / `_QUESTION` | `claude-opus-5` (g2) · `claude-opus-4-8` (g1) | `models.resolve_role` | modelo por rol; `frozen.models.roles.*.source` |
| `WITT_JUDGE_CORRECTNESS` | `claude-opus-5` (g2) · `claude-opus-4-8` (g1) | `models.panel` | asiento correctness (anthropic) |
| `WITT_JUDGE_OVERCLAIM` | `claude-sonnet-5` | `models.panel` | asiento overclaim |
| `WITT_JUDGE_GROUNDING` | `claude-haiku-4-5-20251001` | `models.panel` | asiento evidence-grounding; el sucesor declarado (sonnet-5) se fija AQUÍ (E) |
| `OPENAI_JUDGE_MODEL` | `gpt-4o` (ya existía) | `models.panel` | asiento reproducibility; `gpt-6-astra` SÓLO tras G3 |
| `WITT_PANEL_AUTO_RETIRE` | `0` | `models.panel` | `1` = sucesor automático al llegar `retire_not_before` (declarado + fila `runtime-diff`) |
| `WITT_PANEL_MIN_FAMILIES` | `2` | `audit()` | cuórum de familias; `0|1` = kill-switch (`gating false`) |
| `WITT_PANEL_MIN_LENSES` | `3` | `audit()` | cuórum de lentes; `0|1` = kill-switch |
| `WITT_OPENAI_API` | `table` | `models.api_of` | `responses` fuerza Responses para todo juez OpenAI; `chat-completions` = caller de hoy |
| `WITT_OPENAI_STORE` | `0` | `_responses_kwargs` | `store` de `responses.create` (default de la API: true) |
| `WITT_OPENAI_MAX_OUTPUT_TOKENS` | `4000` | `_responses_kwargs` | tope (no gasto) del camino Responses; chat conserva 1200 |
| `WITT_OPENAI_REASONING_EFFORT` | vacío (no se envía) | `_responses_kwargs` | `reasoning.effort` sólo con `reasoning True` en tabla |
| `WITT_OPENAI_TIMEOUT_S` | `120` | `_openai_client` | timeout por llamada del juez OpenAI; regla `(1+retries)×timeout×2 ≤ 900` |
| `WITT_ANTHROPIC_EFFORT` | vacío (no se envía) | `_anthropic_tool_call` | `output_config.effort` sólo a modelos `thinking_default 'adaptive'` |
| `WITT_ANTHROPIC_EFFORT_ELICIT` | vacío (hereda) | `runs._elicit_confidence` | override para `CONF_TOOL` |
| `WITT_CONFIG_LEDGER` | `1` | `app.config_ledger_boot/observe` | `0` = cero escrituras; `ledger_state` lo dice |
| `WITT_JUDGE_RETRIES` | `1` (ADR-0080) | `audit()` | sin cambio; entra al snapshot |

## Gates NO-SPEND (máscara de siempre: `WITT_BACKEND_DB_URL` sqlite tmp · `NEO4J_URI=''` · `RAG_BACKEND=sparse` · `OPENAI_API_KEY=''` · `ANTHROPIC_API_KEY=''` · `WITT_RUN_ORIGIN=smoke`; venv `dev/.venvs/witt-query-service`, openai 2.53.0)

| Gate | Hoy (medido 2026-09-15 @ f57a3d3) | Tras ADR-0081 (MEDIDO por S7, 2026-09-15) | Qué MIDE de nuevo |
|---|---|---|---|
| `smoke_models.py` (NUEVO) | — | **74** | `prices()` == golden de hoy; defaults g1/g2 100% cotizados; `resolve_role`/`panel` con env inyectada (excluded, wrong-family, unknown→prefix, unknown-family); topes por generación; `relation`; `retirement_due/past_retirement` con `today`; `snapshot` sin secretos; `provenance_block` con stubs; grep de literales = 0; `models.py` sólo stdlib; `openai.__version__ >= 1.66` en el venv; env de la tabla ⊆ compose ∩ README (bidireccional) |
| `smoke_openai_responses.py` (NUEVO) | — | **79** (74 de S7 + 5 del corrector: refusal por Responses ×2, incomplete con function_call parcial y completo, tope efectivo en meta) | `_responses_kwargs` exactos (strict False, store False, parallel False, tool_choice function, reasoning sólo con env+tabla); `max_retries=0` en el cliente; éxito → `usage` numérico + `meta`; 429→retry, 400/404 sin retry, `network`, `incomplete:*`, `refusal`, `no-function-call`, `arguments-unparseable`, `verdict-off-vocabulary`, `required-missing` (retry y devolver); `no-api-key`/`sdk-unavailable` con cero llamadas; despacho por `api`; `WITT_OPENAI_API` fuerza; `audit()` con fake: `error_kind`, `error` string byte-igual a hoy, `failure_kinds_vocabulary`; `sys.modules` sin `openai`; `urlopen` = 0 |
| `smoke_panel_quorum.py` (NUEVO) | — | **28** | 4 válidos → APPROVE, familias 2, lentes 4; OpenAI caído + 3 APPROVE → REVISE `failed ['families']`; MIN_FAMILIES=0 → APPROVE con `panel_single_family true`; lentes repetidas → `['lenses']`; 2 válidos/1 familia → `['min_valid','families']` en orden fijo; `unknown` no cuenta; `caller` source; GOLDEN byte a byte del subconjunto 1.9 de `audit()` @ f57a3d3 con ambos kill-switches (ALL_A, 1-caído, 2-caídos, ilegible — incluido `error`); `apply_to_bundle` copia y re-sella |
| `smoke_run_pipeline.py` | 251 | **272** (271 de S7 + 1 del corrector: `unknown-family` en un rol del pipeline SIN llamar; incluye 2 costuras (N) de S7: firma única de configuración por tres puertas; `root_run_no` BD == `runs._root_run_no` en las 64 corridas del gate) | contrato '1.10' ×21; `frozen.models` (roles, `ran` con stub → `not-reported`; fake con `model_reported` → `prefix`/`different`; planner copiado de `plan_json` / `no-plan`); `stage.models` 2º evento; `stage.audit.verdict` con cuórum; juez OpenAI errored → REVISE estructural + `skipped_reason` + `panel_n_families_valid 1` + sin `stage.revision.start`; `audit_initial` con cuórum; KILL-SWITCH g1 + chat + MIN 0/0 → keyset 1.9 exacto y `by_model` bajo `claude-opus-4-8`; `run.state{queued}.thread.root_run_no` (raíz/hijo/virtual); `by_stage.panel.by_model` Σ == panel; `max_tokens` recibido por el fake == tope de la generación; `output_config` ausente sin env y presente con `WITT_ANTHROPIC_EFFORT=low`; 0 `urlopen`; `mcp_cache` idéntico |
| `smoke_run_recovery.py` | 40 (medido por S3; el borrador estimaba 41) | **40** | literales → tabla; precios iguales |
| `smoke_question_agent_http.py` | 35 | **40** (39 + 1 del corrector: `unknown-family` en question_agent SIN llamar) | `model_source`/`generation` en borrador y `/notes/questions/spec`; `WITT_MODEL_QUESTION` → `env:` |
| `smoke_threads_db.py` | 42 (medido por S4; el borrador estimaba 48) | **77** | `root_run_no` en `_list_select`/`get_run`/`thread_turns` (raíz, hijo, pre-ADR null, hijo de virtual); `threads_index` (orden, `n_turns` == `get_thread`, virtual `+1`, cursor exclusivo, `limit+1`, `mine`, errores); SQL compilado para `postgresql` sin funciones exclusivas de SQLite (límite declarado: no mide la dependencia funcional — G7) |
| `smoke_config_ledger_db.py` (NUEVO) | — | **37** | `create_all` crea la tabla; append/list/last_by_field; nunca update; `boot_id`; `rejected[]` ante `sk-` |
| `smoke_runs_thread_http.py` | 54 | **71** | `GET /threads` 401/200/400; `label` y `root_run_no` == `/threads/{id}` (misma verdad por dos puertas); paginación; `mine`; `n_runs_without_thread` |
| `smoke_runs_list_http.py` | 17 | **21** | `root_run_no` lista == detalle == `POST /runs`; pre-ADR null; blobs siguen fuera |
| `smoke_usage_http.py` (NUEVO) | — | **25** (24 + 1 del corrector: `price_state 'not-measured'`) | 3 `usage_json` mixtos → `by_stage`, `model_split`, `_unattributed.panel`, `n_runs_without_by_stage`, `n_runs_by_stage_mismatch`, `models_catalog`, `by_model[].family`; `totals/by_user/most_expensive` golden de hoy |
| `smoke_config_history_http.py` (NUEVO) | — | **29** (28 + 1 del corrector: `observe()` concurrente desde 2 hilos serializado por `_LOCK`; incluye la medición dura de `db.config_ledger_*`, S7) | `config_ledger_boot()` directo (sin lifespan): first-boot una fila por campo; 2º boot sin cambios → 0 filas; env cambiada → exactamente las filas esperadas con `previous_value`; `runtime-diff` con `today` inyectado y AUTO_RETIRE=1; kill-switch; append que lanza → arranque OK + `ledger_state 'error: …'`; ningún valor contiene los centinelas de las llaves; `/status` byte-igual; `consulta_sistema.config.models_effective` == `current` |
| `smoke_gate_citations.py` · `smoke_competence.py` · `smoke_thread_context.py` · resto (19 smokes sin tocar) | MEDIDO igual antes y después: `gate_citations` 48 · `competence` 31 · `thread_context` 37 · `entities` 16 · `fetch_paper` 41 · `m5v2_http` 32 · `niches` 21 · `notes_http` 28 · `precedent` 30 · `pubmed_tool` 32 · `query_service` 47 · `ratings_calibration` 44 · `run_comments_http` 14 · `search_harness` 47 · `search_queries` 163 · `tools_a` 45 · `tools_b` 69 · `tools_c` 68 · `zfin_tool` 26 (el borrador decía 49 · 31 · 36) | sin cambio (medido) | S7 los corrió todos con la máscara (una .db por smoke): 31/31 en verde, 1623 checks; el corrector los re-corrió igual (2026-09-15): 31/31 en verde, 1632 checks (`smoke_competence` sigue en 31: su aserto del modelo de la elicitación con stub pasó a null declarado); `smoke_zfin_tool` necesitó copiar al worktree el golden gitignored `rag_index/curation/quarantine/zfin_sweep_20260822T232036Z/raw/wt1a.json` y los smokes de tools el `mcp_cache/` (copias byte-idénticas desde el árbol principal; no son código) |
| `smoke_live_models.py --dry-run` (estático) | — | 1 gate (6 filas dry-run, exit 0: 5 roles Anthropic con cuerpo REAL capturado y `urlopen` 0 + el candidato por Responses con `kwargs_match_pure True`; sin BD, sin archivo; re-corrido por el corrector: `--roles all --dry-run` → resumen {n 5, n_ok 5, n_failed 0}, `--model gpt-6-astra --api responses --dry-run` → resumen {n 1, n_ok 1, n_failed 0}: `responses.create` capturado con `kwargs_match_pure True`, `max_output_tokens 4000`, `store False`, `strict False`, `reasoning` ausente sin env) | `ast` + kwargs construidos con la MISMA `_responses_kwargs` |

## Gates EN VIVO (los corre Emmanuel; cada uno gasta lo que dice; resultados al ADR como MEDICIÓN con fecha)

- **LG1 · Opus 5 con los schemas REALES forzados, ANTES del redeploy (≈ 4–5 llamadas, < 0.3 USD):** `python
  analysis/scripts/smoke_live_models.py --roles synthesizer,elicitation,planner,question_agent,judge-anthropic` → cada llamada
  devuelve `tool_use` con todos los `required` bajo los topes g2, `stop_reason 'tool_use'` (no `max_tokens`), `usage.output_tokens`
  medido y comparado contra la mediana 4.8 de `synthesize_pass1`; con `--effort low` repetir la elicitación. Si truncara →
  `WITT_ANTHROPIC_EFFORT_ELICIT=low` o subir el tope en tabla (corrección declarada); si Opus 5 rechazara `tool_choice` forzado (no
  esperado: la referencia y el brief dicen que lo acepta) → `WITT_MODEL_*=claude-opus-4-8` como freno y nota en el ADR.
- **LG2 · Transporte Responses con el modelo barato (1 llamada, ≈ 0.01 USD):** `--model gpt-4o --api responses` → verdict ∈
  VOCABULARY, `meta.model_reported` empieza con `gpt-4o`, kwargs impresos con `store False`, `strict False`. Si falla, el
  `error_kind` dice qué (`http-401/403` llave; `http-400` parámetros → reportar verbatim).
- **LG3 · Astra (1–2 llamadas, ≤ 0.05 USD):** `--model gpt-6-astra --api responses` → verdict válido, `usage.reasoning_tokens > 0`,
  `output_tokens ≥ reasoning_tokens`, latencia impresa (< 120 s o subir `WITT_OPENAI_TIMEOUT_S` ≤ 225). `http-404/400` con 'model' =
  la llave NO tiene acceso → E1. `incomplete:max_output_tokens` → repetir con `--max-output-tokens 8000` y fijar la env. SÓLO con LG3
  en verde: `OPENAI_JUDGE_MODEL=gpt-6-astra` en Dokploy + redeploy.
- **LG4 · Arranque tras el redeploy:** `GET /config-history` → `ledger_state 'ok'`, una fila por campo `first-boot-snapshot`,
  `current.fields.model_generation 'g2-2026-09'`, `panel.reproducibility 'gpt-4o'`, `openai.api 'table'` *(corrector: el campo
  registra la ELECCIÓN de env — `table|responses|chat-completions` — no el transporte efectivo, que es `audit.panel[3].api
  'openai-chat-completions'` en la primera corrida)*, `panel_source ≠ fallback`, `warnings == ['retirement-due:
  claude-haiku-4-5-20251001 en judge.evidence-grounding (…)', 'api-unverified: claude-opus-5 (…) — gate LG1']` *(corrector: NO `[]`
  — ambos avisos son honestos hasta E2 y LG1; `unknown_models []`)*; `/status` byte-igual; un segundo reinicio sin cambios NO añade
  filas.
- **LG5 · Primera corrida real con opus-5:** Traza abre con `stage.models`; `frozen.models.roles.synthesizer == {claude-opus-5,
  'default:g2-2026-09'}`, `ran.synthesize_pass1.relation ∈ exact|prefix`, `ran.elicit_pass1` medido, `roles.planner.provenance`
  según cuándo se hizo el plan; `token_usage.by_model` sin `claude-opus-4-8` (salvo plan viejo); M8 `models_catalog['claude-opus-5']
  .known true`; Hoja sección Modelos; comparar `synthesize_pass1.in/out` y latencia contra la mediana 4.8.
- **LG6 · Primera corrida con Astra (tras LG3):** `audit.panel[3].api 'openai-responses'`, `attempts[-1].model_reported` presente,
  `ran.panel[3].relation ∈ exact|prefix`, `by_model['gpt-6-astra']` cotizado 10/50 (`cost_projection_complete true`),
  `audit.usage.reasoning_tokens > 0`; el ledger ganó `panel.reproducibility gpt-4o → gpt-6-astra` y `openai.api → openai-responses`.
- **LG7 · Cuórum en vivo (1 corrida, ≈ 0.2 USD):** `OPENAI_JUDGE_MODEL=gpt-no-existe` + redeploy → `panel[3].status 'errored'`,
  `attempts[*].error_kind 'http-404'|'http-400'`, `verdict 'REVISE'`, `panel_incomplete_reasons ['families']`, `revision.performed
  false` con `skipped_reason` que cita `families`, `epistemic_summary.panel_n_families_valid 1`, ListaCorridas "1 familia"; restaurar
  (el ledger deja DOS filas: el cambio y la vuelta).
- **LG8 · `GET /threads` en Postgres:** sin 500 (dependencia funcional del GROUP BY); `n_threads_total == SELECT count(distinct
  thread_id) FROM runs WHERE thread_id IS NOT NULL`; cada `label`/`n_turns` == `/threads/{id}`; `n_runs_without_thread` == corridas
  pre-ADR-0079; `limit=1` → `has_more true`; M6 lista sin agrupar en el cliente.
- **LG9 · `root_run_no` en prod:** lista y detalle de un hijo == `/threads/{thread_id}.root_run_no`; Traza de una corrida encolada
  hoy muestra "Investigación T-<n>" desde `run.state{queued}`; una pre-ADR muestra null declarado.
- **LG10 · `/usage` por etapa en prod:** `by_stage._sum` == suma de `totals` restringida a corridas con `by_stage`;
  `n_runs_without_by_stage` == corridas congeladas antes de 1.9; `by_model_stage_coverage.n_runs_with_panel_by_model` == corridas
  1.10; `by_model['claude-opus-4-8'].family 'anthropic'`.
- **LG11 · Precios (atestiguado por Emmanuel):** confirmar en las páginas de precios que opus-5 5/25 · sonnet-5 2/10 · haiku-4.5 1/5 ·
  fable-5.1 10/50 · gpt-4o 2.5/10 · gpt-6-astra 10/50 · gpt-5.6-sol 4/20 siguen vigentes; si alguno cambió, fila en `models.py`
  con `verified_on` nuevo y `PRICES_AS_OF` (el `cost_class` lo imprime).
- **LG12 · Retiro de haiku (antes del 2026-10-15):** `stage.models.warnings` muestra `retirement-due` desde el 2026-09-15 (¡hoy: 30
  días!); al fijar `WITT_JUDGE_GROUNDING=claude-sonnet-5` (o `AUTO_RETIRE=1`) → fila del ledger, siguiente corrida con
  `lenses_valid 4`, `families_valid ['anthropic','openai']`, `panel_duplicate_models ['claude-sonnet-5']`, `warnings []`.
- **LG13 · Kill-switch byte a byte en prod (opcional, 1 corrida):** g1 + chat-completions + MIN 0/0 + LEDGER=0 → opus-4-8/gpt-4o por
  chat.completions, `quorum.families_gating false`, `ledger_state 'kill-switch…'`, registro menos llaves 1.10 = forma f57a3d3.
- **LG14 · Promesas del brief (gastan, decisión E4):** `evaluation/scripts/ab_trapped_scalar.py` con opus-5 (|Δ| del escalar
  atrapado ≤ 0.15 vs la serie 4.8, ADR-0065) y `run_held_out_v2` sin regresión de veredictos (advisory).

## Decisiones abiertas para Emmanuel (mínimas; cada una con default)

- **E1 · Acceso a Astra.** Correr LG2 y LG3 (< 0.1 USD). Si LG3 pasa: `OPENAI_JUDGE_MODEL=gpt-6-astra` (+ `WITT_OPENAI_MAX_OUTPUT_TOKENS`
  / `WITT_OPENAI_TIMEOUT_S` si LG3 lo pidió) en Dokploy y redeploy. Si la llave no tiene acceso (`http-404/400`): default = seguir con
  `gpt-4o` (declarado `bridge`; su snapshot se apaga el 2026-10-23 según el brief — antes de esa fecha hay que tener Astra o tomar
  otra decisión; Sol quedó descartado).
- **E2 · Retiro de haiku.** ¿Fijas `WITT_JUDGE_GROUNDING=claude-sonnet-5` tú antes del 2026-10-15 (default, aviso desde hoy) o
  activas `WITT_PANEL_AUTO_RETIRE=1` (sucesor automático declarado + fila `runtime-diff`)? Default si no contestas: manual (0).
- **E3 · Texto literal de la aprobación presupuestal** para la entrada atestiguada `budget_approval` de `config_history.json` y para
  este ADR (brief R6/§190). Propuesta: "Apruebo claude-opus-5 en síntesis, planner, elicitación y agente de preguntas (mismo precio
  que 4.8, pensamiento adaptativo por default medido en output_tokens) y gpt-6-astra como cuarto juez (10/50 USD/Mtok más reasoning
  tokens, ≈ 4× gpt-4o por juez), sin tope por corrida; toda cifra con clase." — confirmar tal cual o acotar.
- **E4 · ¿Correr LG14 (ab_trapped_scalar con opus-5 + held-out v2, ≈ 4–6 llamadas)?** El brief lo lista como gate en vivo. Default
  si no contestas: NO se corre y queda en gates vivos pendientes.

## Plan de implementación (rebanadas DISJUNTAS por archivo → integrador → 3 revisores → corrector)

Orden: **S1 → (S2 ∥ S3 ∥ S4 ∥ S5 ∥ S6) → S7 integrador → R1/R2/R3 revisores (doctrina · corrección · contrato) → corrector.**
S1 congela la INTERFAZ de `models.py` (firmas y formas de (A)/(B)); S2–S5 desarrollan contra ella y, hasta que aterrice, contra un
stub local con esas firmas que S7 retira. Ningún archivo tiene dos dueños.

- **S1 · tabla g2 + evaluación** — dueño de: `analysis/scripts/lib/models.py` (NUEVO) · `rag_index/query_service/smoke_models.py`
  (NUEVO) · `evaluation/run_held_out.py` (L79-81 desde la tabla; `openai_verdict` delega en `composite_auditor._default_caller`) ·
  `evaluation/scripts/ab_trapped_scalar.py` (sin cambio de código: sigue leyendo `runs_mod.SYNTH_MODEL`, alias conservado — S1
  verifica) · `rag_index/query_service/requirements.txt` (`openai>=1.66,<3`). Entrega la API exacta de (A) + el smoke de la tabla.
- **S2 · panel: caller Responses + vocabulario + cuórum** — dueño de: `analysis/scripts/lib/composite_auditor.py` ·
  `rag_index/query_service/smoke_openai_responses.py` (NUEVO) · `smoke_panel_quorum.py` (NUEVO). Entrega (C.1–C.3), (D), (K) en
  `audit()`, `return_meta`, `legacy_type_name`, `_responses_kwargs`, `_openai_client`, docstring L10-13/L41 corregidos.
- **S3 · registro y eventos (runs + question_agent)** — dueño de: `rag_index/query_service/runs.py` · `question_agent.py` ·
  `smoke_run_pipeline.py` · `smoke_run_recovery.py` · `smoke_question_agent_http.py` · `smoke_thread_context.py` /
  `smoke_competence.py` (sólo si un aserto se rompe por llaves nuevas). Entrega contrato 1.10, roles resueltos en llamada con topes
  g1/g2 y `output_config` por env (C.4), `frozen.models`, `stage.models`, `stage.synthesize.start` payload, `stage.audit.judge/verdict`,
  `skipped_reason`, `audit_initial`, `by_stage.panel.by_model` + `model_source`, `epistemic_summary`, `run.state{queued}` con
  `root_run_no`, `_plan_structural` con `panel_resolved`, `config_ledger_observe` llamado al inicio de `execute_run` (firma
  declarada, S5 la provee), `_agents_invoked.evidence_generated += 'families_valid:<n>'`.
- **S4 · BD** — dueño de: `rag_index/query_service/db.py` · `smoke_threads_db.py` · `smoke_config_ledger_db.py` (NUEVO). Entrega
  tabla `config_history` + `config_ledger_*`, JOIN a la raíz en `_list_select`/`get_run`, `threads_index` (dos consultas, dialecto
  neutral, GROUP BY por PK del alias), `count_runs_without_thread`.
- **S5 · puertas HTTP** — dueño de: `rag_index/query_service/app.py` · `consulta_sistema.py` · `smoke_runs_thread_http.py` ·
  `smoke_runs_list_http.py` · `smoke_usage_http.py` (NUEVO) · `smoke_config_history_http.py` (NUEVO). Entrega `GET /threads` (antes
  de `/threads/{id}`), `/usage` (H), `/config-history` (I), `config_ledger_boot`/`config_ledger_observe` + `_LEDGER_STATE`, lifespan
  cableado, `question_spec` += `model_source/generation`, `consulta_sistema.config` += `models_effective/ledger`; `_run_view` intacto
  (comentario ADR-0081).
- **S6 · doctrina + operación + vivo** — dueño de: `docs/decisions/0081-politica-best-tier-v2-y-generacion-de-modelos-g2.md`
  (este documento, con conteos "S7 mide") · `docs/decisions/README.md` (fila 0081) · `rag_index/query_service/docker-compose.query.yml`
  (las 18 env tras `WITT_JUDGE_RETRIES`, `${VAR:-default}` + comentario de una línea, y la nota "toda env = reinicio" —
  *(S6)* el bloque ADR-0081 va como bloque PROPIO al final del bloque ADR-0080, tras `WITT_OPENALEX_PER_PAGE`: después de
  `WITT_JUDGE_RETRIES` en el orden del archivo, sin partir el bloque 0080; son 18 FILAS de la tabla = 20 variables NUEVAS en el
  compose (las cuatro `WITT_MODEL_*` comparten fila; `WITT_JUDGE_RETRIES` ya estaba declarada y no se repite)) ·
  `rag_index/query_service/README.md` (tabla de env + sección ADR-0081) · `rag_index/config_history.json` (dos entradas
  atestiguadas; `budget_approval` con placeholder `<pendiente E3>` hasta tener el texto) · `analysis/scripts/smoke_live_models.py`
  (NUEVO, EN VIVO: `--roles`, `--model`, `--api responses|chat-completions`, `--max-output-tokens`, `--effort`, `--dry-run`; usa
  `_responses_kwargs` y `_anthropic_tool_call(return_meta=True)` reales; imprime fila/kind/usage/meta/latencia; escribe
  `analysis/outputs/live_models_<fecha>.json` sin secretos; rehúsa correr sin llave con `no-api-key`; jamás toca la BD).
- **S7 · integrador** — sin archivos propios: retira stubs, cose (N), corre los 25 + 6 gates con la máscara, verifica `urlopen` 0 y
  `mcp_cache` idéntico, grep de literales = 0, compose/README ⊇ env, reemplaza "S7 mide" por conteos, corre `parity_check.py` de la
  webapp en lectura y anota los huecos, etiqueta `contract-1.10-frozen`. Commits por rebanada en `feat/adr-0081-modelos-g2`; sin
  push (Emmanuel).
- **Revisores (3, en paralelo sobre el árbol de S7):** R1 doctrina (clases de cifra, tres estados, nada afirma sin medir, §7
  compuertas, "lo que NO se hace"); R2 corrección (kill-switches byte a byte, cuórum, caller, JOIN/GROUP BY, ledger idempotente,
  fakes sin red); R3 contrato (formas de (B)–(J) vs código vs lista de paridad; vocabularios congelados; fixtures 1.10 generables).
  **Corrector:** aplica los hallazgos marcándolos *(corrector)* en el ADR, re-corre los gates, actualiza conteos.

**Fixtures 1.10 que la webapp necesitará (los genera `gen_fixtures.py` contra `contract-1.10-frozen`):** los 30 existentes
regenerados (todos ganan `models`, `audit.quorum`, `families_valid…`, `by_stage.panel.by_model`; el SINTÉTICO pre-1.1 sigue sin
ellos) · `panel-una-familia.json` + `eventos-panel-una-familia.json` · `modelos-g1-kill-switch.json` · `modelos-por-env.json` ·
`modelos-relation-different.json` (fake que reporta otro modelo: la objeción roja tiene caso) · `threads-index.json` ·
`threads-index-pagina-2.json` · `config-history.json` · `config-history-kill-switch.json` · `usage-by-stage.json` ·
`stage-models-warnings.json` (evento con `retirement-due` y `unknown_models`) · `question-spec-1.10.json`. El MANIFIESTO registra
'1.10', el SHA del backend y qué es real por el código y qué stub.

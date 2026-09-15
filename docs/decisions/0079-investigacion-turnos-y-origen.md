# ADR-0079 — La investigación: turnos encadenados sobre una raíz, el turno anterior como precedente (jamás evidencia), el origen de cada corrida y los cuatro ejes del episodio

- **Status:** Accepted — 2026-09-15. Origen: plan v3 del brief *Consejo de agentes* aprobado por Emmanuel el
  2026-09-14 (§8: "continuar una corrida"); hallazgos de la auditoría externa Codex/Martín — **F4 (origen de
  corrida)**: el corpus de precedente y la calibración leían TODA corrida cerrada sin saber si nació en
  producción, en un smoke o en una simulación — y **v0.2 §4.2 (cuatro ejes)**: un solo enum de estado
  mezclaba lo que el mundo dice, lo que la inferencia sostiene y lo que la técnica logró. Obra en cinco
  rebanadas (T1 db · T2 runs · T3 app · T4 consumidores · T5 integrador) + un **corrector final** (tres revisiones:
  doctrina · corrección · contrato) en la rama `feat/adr-0079-investigacion`, apilada sobre
  `feat/adr-0078-higiene-ruta-ab` @ `34e95ba`; todas las cifras de este ADR son MEDICIONES de los gates offline del
  2026-09-15.
- **Relates:** ADR-0043 (tres estados, jamás `null` ambiguo) · ADR-0044 (identidad: `question_matches_run`) ·
  ADR-0050 (bitácora única + registro congelado) · ADR-0051 (`TokenUsage` medido, costo PROYECCIÓN) ·
  ADR-0053 (la capa de precedente: series DISJUNTAS — números = evidencia, letras = precedente;
  `admissible_as_evidence: false` estructural) · ADR-0055/0076 (lista y detalle sirven la MISMA vista; la
  asimetría rompió dos veces) · ADR-0056 (la procedencia la deriva el SERVIDOR, nunca el cliente) · ADR-0061
  (un `plan_id` se consume por UNA corrida) · ADR-0064/0075 (las calificaciones se enmascaran por solicitante
  y jamás se promedian) · ADR-0073 (PDF de servidor del registro) · ADR-0074 (el registro congelado es
  INMUTABLE; campos-lista con lectura tolerante) · ADR-0077 (los comentarios de corrida = "hilo": por eso
  aquí se dice **investigación**) · ADR-0078 (`_migrate` aditivo por tupla; `_env_int_tolerante`) · ADR
  2026-07-13 del vault (clases de cifra: medición / atestiguada / proyección).
- **Affects:** `rag_index/query_service/db.py` (7 columnas aditivas + 2 índices; `create_run`, `list_runs`,
  `get_children`, `thread_turns`, `max_turn_no`, `runs_by_thread`, `_origin_where`, `excluded_by_origin`,
  `closed_runs`/`runs_usage`/`plan_history`/`question_calibration` con `include_origins`) · `runs.py`
  (`derive_thread`, `build_thread_context`, `run_origin`, `frozen_sha256`, `parent_identifier_leak`,
  `episode_axes` + `EPISODE_AXES_MAP`, `synth_system(thread_context=)`, `THREAD_ANTI_LEAK_CLAUSE`,
  `new_run(parent_run_id=, from_question_id=)`, `plan_thread_context`, `ThreadError`; contrato **1.8**) ·
  `app.py` (`RunBody/PlanBody.parent_run_id`, `GET /runs?thread=&limit=&after=`, `GET /threads/{thread_id}`,
  `include_origins` en `/precedent/search`, `/calibration`, `/notes/questions/calibration`; `_run_view`) ·
  `precedent.py` (alcance por origen, `turn_item`, `serialize_disjoint` con pass-through) · `calibration.py`
  (alcance por origen) · `record_pdf.py` (secciones INVESTIGACION y EJES DEL EPISODIO) · gates nuevos
  `smoke_threads_db.py` · `smoke_thread_context.py` · `smoke_runs_thread_http.py` + `smoke_run_pipeline.py`
  (181 → 211) · `smoke_precedent.py` (15 → 28) · `smoke_ratings_calibration.py` (39 → 44) · `README.md` ·
  `docker-compose.query.yml` · witt-webapp (tipar y pintar; ver *Consequences*). **Cero mutación de la DATA
  INAMOVIBLE, del registro congelado existente y de las corridas anteriores (ninguna columna se backfillea).**

## Context

1. **Una pregunta de seguimiento nacía huérfana.** La única continuidad entre dos corridas sobre el mismo
   tema era el humano: releer el registro, copiar a mano lo que faltó (`gap_flags`), volver a preguntar. El
   sistema no sabía que la segunda corrida venía de la primera; el precedente (ADR-0053) existía como índice
   de búsqueda, pero ninguna etapa del pipeline lo usaba como insumo de una corrida concreta — `runs.py`
   importaba `precedent` sin invocar `serialize_disjoint` (la serie de letras no tenía llamador).
2. **F4: producción y prueba eran indistinguibles en el corpus.** `db.closed_runs` devolvía toda corrida
   `closed` sin origen; `precedent.search` y `calibration.report` la tomaban como precedente/ECE. Bastaba que
   un smoke o una simulación corriera contra la misma BD para que su respuesta sintética entrara al corpus con
   la misma autoridad que una corrida real de witt-ai.com.mx. Los smokes hoy usan SQLite temporal, pero la
   garantía era de disciplina, no de datos.
3. **Un enum para tres cosas (v0.2 §4.2).** `decision_state.state` (AUDIT_APPROVED/REJECTED), `absence_kind`,
   `audit.verdict` y `retrieval_summary.mode` viajaban sueltos; el lector tenía que componer a ojo si "aprobada"
   significaba *hay efecto*, *no hay efecto acotado* o *el store no sabe* — y si una corrida "completada"
   había recuperado en modo semántico o degradado. La composición es determinista: debe hacerla el código, por
   tabla, al congelar.
4. **La inmutabilidad del padre es medible.** Desde ADR-0074 el blob `frozen_record_json` no cambia; lo único
   que `close_run` le añade son `frozen_at` y `closed_by`. Eso permite un predicado exacto: el sha del padre al
   ENCOLAR al hijo debe ser el sha del padre al CONGELAR al hijo (sobre el blob sin esas dos llaves).
5. **La fuga por precedente es real y el gate no la ve.** `verify_output` es ciego a la procedencia por
   diseño (ADR-0053): un `PMID` copiado del turno anterior pasa si resuelve. Si el modelo ve la respuesta
   anterior, la única defensa determinista es comparar tres conjuntos — identificadores en el contexto del
   padre, en la respuesta del hijo y en la evidencia del hijo.

## Decision

**(A) Datos — siete columnas ADITIVAS en `runs`**, por la tupla de `_migrate` (patrón ADR-0076/0078), sin
backfill: `parent_run_id`, `thread_id`, `turn_no`, `turn_kind ∈ {root, refine, rerun, branch}`
(`db.TURN_KINDS`), `thread_context_json`, `origin` (`db.RUN_ORIGINS = production | dev-offline | replay | smoke
| simulation | fixture`), `root_question_id`; índices `ix_runs_thread_id`, `ix_runs_parent_run_id` (no únicos) y
**`ux_runs_thread_turn` ÚNICO sobre `(thread_id, turn_no)`** [corrector] — el patrón de `ix_runs_run_no`: cierra la
carrera de `turn_no` (dos hijos encolados a la vez) y, con ella, la pérdida de página del cursor `after` y la
clasificación errónea de `turn_kind`; las filas pre-ADR (NULL, NULL) no chocan.
La RAÍZ nace con `thread_id = run_id`, `turn_no 1`, `turn_kind 'root'` (inmutable). **Toda corrida anterior
queda NULL en las siete = "sin investigación" / origin `unknown-pre-adr-0079`** — ausencia declarada, jamás
rellenada. `list_runs` comparte el SELECT (`_list_select`) con `get_children` / `thread_turns` /
`runs_by_thread`; `thread_context_json` va a la lista de EXCLUSIÓN de `_run_view` (es un blob: vive en el
registro como `frozen.thread_context`). Costo declarado [corrector]: ese blob (hasta ~10 KB) viaja en el SELECT de
cada renglón de la lista general para que lista y detalle compartan columnas (ADR-0055/0076); `_run_view` lo descarta.
`db` NO deriva nada: persiste lo que `runs.py` deriva (`db.has_children` es sólo el booleano para `branch`).

**(B) Derivación al ENCOLAR, en el servidor** (`runs.derive_thread`, desde `new_run`; el cliente sólo REFIERE
`parent_run_id`): padre inexistente → `404 parent_not_found`; padre `∉ db.RATABLE_STATES` (queued/running) →
`409 parent_not_terminal` con `parent_state` (failed/cancelled SÍ son padres válidos: el hijo declara
`parent-without-frozen-record`). `thread_id = parent.thread_id or parent.run_id`; `turn_no = max(turno del
hilo, 1) + 1`; `turn_kind`: `rerun` si pregunta + `entities_csv` idénticos al padre (se evalúa ANTES que
branch), `branch` si el padre ya tenía otro hijo (`db.has_children`), `refine` en el resto; `root_question_id =
parent.root_question_id → borrador (`note_questions`) del padre → None` [corrector: en un turno con padre JAMÁS se
siembra desde el `from_question_id` del hijo — la llave dice "raíz" y ese borrador es del turno 2..N; vive en
`note_questions.run_id`]. **Carreras [corrector]:** `turn_no`/`turn_kind` se derivan fuera de la transacción del INSERT;
el índice único `ux_runs_thread_turn` rechaza al segundo hijo y `new_run` RE-DERIVA (hasta 5 intentos; sólo esa
violación se reintenta — SQLite `runs.thread_id, runs.turn_no` / Postgres `ux_runs_thread_turn`). **Padre pre-ADR (columnas NULL) = raíz VIRTUAL:**
`thread_id = parent.run_id`, hijo `turn_no 2`, `parent_pre_adr_0079: true` en snapshot y sobre; `GET /threads`
la lee como turno con `turn_no null` — derivación al servir, cero escritura. Ambas validaciones viven UNA vez
(`runs.ThreadError {status, detail}`); `app.py` sólo traduce a `HTTPException`. **Plan:** un `plan_id` se
consume por UNA corrida (409 `plan_already_used`, ya existía) — el hijo declara plan nuevo con `POST /runs/plan
{parent_run_id}` (el planner recibe un snapshot armado igual — y el registro AHORA puede probarlo [corrector]: el sobre
de `plan_thread_context` lleva `parent_run_id`, el plan guarda `thread_parent_run_id` + `thread_parent_frozen_sha256`,
y al congelar `plan_parent_matches_run` / `plan_snapshot_matches_run` (bool | null) con `_state ∈ checked | no-plan |
plan-predates-thread-declaration | no-parent | no-snapshot` — un plan hecho con el padre X que respalda una corrida con
padre Y queda `false`, declarado, sin 409: misma disciplina que `plan_question_matches_run`). La copia de `plan_json` con
`plan_declared 'inherited'`
que el brief mencionaba **NO se implementó** [T5]: haría `plan_question_matches_run` false en todo refine y
cambiaría `plan_declared` de bool a string (cambio de contrato); queda como decisión abierta de Emmanuel.

**(C) El snapshot del turno anterior (`thread_context`) lo arma el SERVIDOR al encolar**
(`runs.build_thread_context`, PURA: recibe la fila del padre + sus comentarios) desde `frozen_record_json` +
`run_comments`: `parent {run_id, run_no, question, entities_csv, state, verdict, decision_state}` ·
`previous_answer {direct_answer[:WITT_THREAD_ANSWER_CHARS] + direct_answer_truncated + chars_total,
stated_confidence, absence_kind, gap_flags (íntegros, lectura tolerante ADR-0074), confidence_by_subclaim}` ·
`previous_audit {verdict, n_valid, findings[:5]}` · `human_comments {items[{author_name, created_at, body}],
n_total, n_included, chars_included, truncated, class: 'atestiguada', limits}` (orden determinista; topes
`WITT_THREAD_COMMENTS_MAX` / `WITT_THREAD_COMMENTS_CHARS`) · `evidence_hints {entities[],
approved_evidence_ids[]}` (SOLO pistas para RE-RECUPERAR: el texto se vuelve a leer de la fuente) ·
`excluded: ['ratings values and notes (masked per requester, never averaged)']` · `bytes` (+`bytes_unit 'utf-8 bytes'`;
`human_comments.limits.unit 'chars (code points)'` — dos unidades, ambas etiquetadas [corrector]), `snapshot_at`,
`parent_frozen_sha256` + su regla, `kill_switch`. El orden de los comentarios es el de `db.list_run_comments`
(created_at con microsegundos, comment_id); el sobre sólo re-ordena ESTABLE por el segundo [corrector: desempatar por
uuid barajaba dos comentarios del mismo segundo]. Tres estados por construcción: padre con
`question_matches_run === false` → snapshot `null` + `skipped_reason 'parent-identity-invalid'` (la hija SÍ se
crea); padre sin registro → snapshot con `previous_answer`/`previous_audit` `null` declarados
(`frozen_absent_reason 'parent-without-frozen-record'`); raíz → `skipped_reason 'root-turn'`. Se persiste como
SOBRE `{snapshot, skipped_reason, kill_switch, built_at, origin}` en `runs.thread_context_json` (`origin` = la
procedencia completa `{value, source, raw?, truncated?}` derivada al ENCOLAR [corrector]); NULL en la columna
queda reservado a filas pre-ADR.

**(D) Inyección.** Al SINTETIZADOR como llave HERMANA de `evidence` (patrón `revision_input`): `user_text =
{question, evidence, thread_context}` — jamás dentro de `evidence`; `synth_system(pass_label,
thread_context=True)` añade `THREAD_ANTI_LEAK_CLAUSE` ("The previous turn (thread_context) is PRIOR ART, not
evidence; never cite or reuse an identifier from it unless it appears in evidence…") y `SYNTH_TOOL.description`
lleva la frase SIEMPRE; **sin turno anterior el system es byte-idéntico al de antes** (la medición de
`ab_trapped_scalar` no cambia). Al PLANNER como llave aparte del `user_text`; el plan declara
`thread_context_declared` / `thread_context_skipped_reason`. Al PANEL: evidencia LIMPIA (sin la llave, sin
comentarios ni texto del padre) + `deterministic_checks.thread {thread_id, turn_no, turn_kind, parent_run_id,
parent_run_no, parent_verdict, context_available}` — sabe que hubo turno previo, no lee su texto. Un
sintetizador/planner inyectado con la firma VIEJA sigue válido (`_call_with_optional` inspecciona la firma) y el
registro declara `context_delivery.synthesizer: false` + nota. **Kill-switch `WITT_THREAD_CONTEXT=0`**, releído al
encolar Y al ejecutar (patrón `WITT_REVISION_CYCLE`): las columnas se llenan, el snapshot no se arma o no viaja,
`skipped_reason` declarado; el sobre persistido no se toca.

**(E) Precedente ≠ evidencia, por construcción.** Al congelar, `precedent.serialize_disjoint(citations,
[precedent.turn_item(padre)])` → `frozen.precedent_citations = [{l: 'A', run_id, question[:200],
admissible_as_evidence: false, why_not_admissible: precedent.WHY_NOT_ADMISSIBLE, run_no, turn_no, kind: 'turn'}]`
(`turn_no null` declarado para un padre pre-ADR: la llave viaja aunque sea null) — **SÓLO si el padre está `closed`**
[corrector, ADR-0053 / `db.closed_runs`: una corrida es precedente únicamente tras la clausura humana explícita]. Un
padre `awaiting_closure` / `failed` / `cancelled` sigue siendo padre válido (su snapshot viaja como `thread_context`,
§B) pero no lleva letra: `precedent_citations []` + **`precedent_citations_state ∈ checked | no-parent |
parent-not-closed | parent-without-frozen-record`** y `disjoint_series_state 'parent-not-precedent'`. El estado del
padre se lee AL CONGELAR al hijo (un padre cerrado entre el encolado y la ejecución del hijo gana la letra; el sha sigue
casando porque la clausura sólo añade `frozen_at`/`closed_by`).
`frozen.citations` (serie numérica `n`) NO cambia de forma — la leen `record_pdf`, `niche_catalog` y la Hoja.
`deterministic_checks.disjoint_series = precedent.validate_disjoint(...)` (una `'label': 'A'` hecha a mano, una
letra dentro de la serie numérica o una `l` con `n` FALLAN — medido). **`parent_identifier_leak`** = identificadores
(`runs.IDENTIFIER_PATTERNS`, tal cual: `ENSDARG\d+` · `PMID:\s?\d+` · `PMC\d+` · `10\.\d{4,9}/[^\s"',;)\]}>]+` ·
`ZDB-[A-Z]+-\d+-\d+`; `extract_identifiers` normaliza a mayúsculas, quita el espacio tras `PMID:` y recorta `.`/`,`
finales — [corrector] el DOI arrastraba el punto de la prosa y un DOI legítimo presente en la evidencia salía como fuga)
presentes en el TEXTO del snapshot
Y en `answer.direct_answer` Y AUSENTES de la evidencia del hijo — sus `evidence_ids` **y el texto de la evidencia
que el modelo vio** (`_compact_evidence`, que incluye `entities_checked`: el ENSDARG de wt1a resuelto por el
store NO es fuga aunque el padre lo citara; flagarlo haría inadmisibles respuestas correctas — regla declarada en
`parent_identifier_leak_rule`). Fuga no vacía → predicado DURO vía `verify_output.admissible(extra_predicates=…)`
→ `admissible false` con `reasons` `'hard predicate failed: parent_identifier_leak'`; la corrida TERMINA
(inadmisible se declara, no tumba). Estados [corrector]: `parent_identifier_leak_state ∈ checked | no-parent |
no-snapshot` — `'no-snapshot'` cuando HAY padre pero el snapshot no viajó (kill-switch, identidad inválida): no se midió,
no se declara "sin padre" (mismo vocabulario que `thread_parent_matches_run_state`). Sin padre: `precedent_citations []`,
`disjoint_series_state` / `parent_identifier_leak_state` `'no-parent'`.

**(F) Origen de la corrida — `runs.run_origin()` al encolar, guardado en `runs.origin`:** `WITT_RUN_ORIGIN`
definida y en el enum → ese valor (`source 'env:WITT_RUN_ORIGIN'`); fuera del enum → `'invalid-env:<v>'`
DECLARADO (recortado a 24 chars con `truncated`; la corrida se crea igual — no se corrige ni se tumba); sin env →
`'dev-offline'` si `WITT_ALLOW_RUNS_OFFLINE == '1'` (`'derived:offline-mask'`), si no `'production'`
(`'default:production'`). `frozen.origin = {value (la COLUMNA), source, source_at_execution, note}` — **`source` es la
fuente AL ENCOLAR**, copiada del sobre `thread_context_json.origin` que `new_run` persiste [corrector: antes se
re-derivaba al ejecutar y, con el mismo valor y distinta fuente — `env:WITT_RUN_ORIGIN` al encolar, `default:production`
al ejecutar —, el registro presentaba la fuente de ejecución como procedencia]; `source_at_execution = {value, source,
same_value_as_column}` es la re-derivación al ejecutar, dato secundario declarado aparte; un sobre sin `origin`
(encolado antes del corrector) → `source 'unknown-at-enqueue (…)'`. **Consumidores:** `precedent._corpus` /
`GET /precedent/search`, `calibration.report` / `GET /calibration` y `GET /notes/questions/calibration` EXCLUYEN
`origin ∉ {'production'}` por default — el default se aplica en la PUERTA (`app`, vía `precedent.normalize_origins`;
`db.question_calibration(None)` sigue siendo "sin filtro" para llamadas de biblioteca y lo declara) [corrector: esa
tercera puerta pasaba `None` = sin filtro, con `origins_included null`] — **origin NULL (pre-ADR) se
INCLUYE y se declara** (`origin_unknown_included: n`) — y aceptan `include_origins` (lista / CSV; fuera del enum →
`400 invalid-origin` con `allowed`); toda respuesta trae `origins_included`, `excluded_by_origin {origin: n}`,
`origin_unknown_included`, `origin_policy`. UNA puerta para ambos consumidores: `precedent.closed_runs_scoped`
(filtro en SQL, `db._origin_where`) + `precedent.origin_declaration` (conteos sobre la MISMA base que el corpus,
aunque el corpus tenga LIMIT); la caché TF-IDF lleva el alcance en su llave (dos alcances = dos índices). **Sin
filtro, por decisión [T5]:** `/usage` (M8 suma gasto REAL: un smoke que gastó, gastó) y `db.plan_history`
(la mediana de estimaciones corre sobre la BD contra la que sirve el servicio; en producción sólo hay
producción). Los smokes corren con `WITT_RUN_ORIGIN=smoke` y piden `include_origins=smoke` explícito; el default se
prueba comprobando que sus corridas quedan CONTADAS fuera.

**(G) Los cuatro ejes del episodio — derivados AL CONGELAR, por TABLA (`runs.EPISODE_AXES_MAP`, clase
`derived-at-freeze`), jamás un enum único.** `frozen.episode_axes = {class, world, inference, technical,
provenance {origin, human_gates {plan_declared, closed: false at-freeze + closed_note, …}, turn {thread_id,
turn_no, turn_kind}}, map, notes[]}`; `epistemic_summary` gana `thread_id`, `turn_no`, `origin` (regla
frozen-counter: la lista no re-deriva). La tabla, tal como está en código (y en palabras en `record_pdf._AXIS_WORDS`):

| Eje | Regla (insumos del registro) | Mapeo |
|---|---|---|
| `world` | `decision_state.state × answer.absence_kind × audit.verdict` | `AUDIT_APPROVED × not-applicable` → **effect-claimed** · `AUDIT_APPROVED × evidence-of-no-effect` → **null-bounded** · `AUDIT_APPROVED × no-evidence-retrieved` → **indeterminate** · `AUDIT_APPROVED × <absence_kind ausente/fuera del enum>` → **indeterminate** (declarado en `notes`) · `AUDIT_REJECTED` (con veredicto) → **not-established** · `<sin veredicto>` → **not-assessed** (PRECEDE a `decision_state`: un `AUDIT_REJECTED` sin veredicto sale not-assessed) · `<veredicto presente> × decision_state ∉ {AUDIT_APPROVED, AUDIT_REJECTED}` → **not-assessed** (nota) [corrector: dos filas que la función ya producía y la tabla no decía] |
| `inference` | `audit.verdict` | `APPROVE` → **supported** · `APPROVE_MINOR` → **minor-issues** · `APPROVE_DECLINE` → **honest-decline** · `REVISE` → **insufficient** · `<none / fuera del vocabulario>` → **not-evaluated** (declarado) |
| `technical` | `run.state × retrieval_summary.mode` | `awaiting_closure\|closed × semantic` → **completed** · `awaiting_closure\|closed × <mode ≠ semantic>` → **degraded** (nota con el modo) · `failed` → **failed** · `cancelled` → **cancelled** |
| `provenance` | columnas + registro | `origin` (valor de la columna; `null` = pre-ADR) · `human_gates {plan_declared, closed}` (`closed` es `false` al congelar: la clausura ocurre DESPUÉS y vive en `frozen_at`/`closed_by`) · `turn {thread_id, turn_no, turn_kind}` |

Un registro anterior al contrato no tiene la llave: el PDF imprime `NO INSTRUMENTADO (contrato < 1.8)`; un
`episode_axes: null` se imprime "null declarado"; un literal fuera de tabla se imprime tal cual y se marca. **`technical
∈ failed | cancelled` son valores de la TABLA, no del registro** [corrector]: las corridas failed/cancelled no congelan
registro (`_finish` sin `frozen_record_json`), así que `frozen.episode_axes` sólo nace con `run_state 'awaiting_closure'`;
la función pura los produce (el gate lo mide) y `GET /threads` sirve `state` por turno para el eje técnico de los fallidos.

**(H) API.** `RunBody.parent_run_id?` (POST /runs) · `PlanBody.parent_run_id?` (POST /runs/plan; respuesta
`+parent_run_id, +thread_context_passed, +thread_context_skipped_reason` — `'root-turn'` sin padre) ·
`GET /runs?thread=<thread_id>&limit=&after=` (turnos en `turn_no ASC`, sin el tope 50, cursor `after` =
`turn_no` EXCLUSIVO — lossless porque `ux_runs_thread_turn` garantiza un turno por `turn_no` —, `has_more` MEDIDO con
`limit+1`, `next_after`; `after` sin `thread` → 400; **`limit < 1` → 400 en AMBOS ramales** [corrector: `limit=-1`
llegaba a `LIMIT -1` = sin tope en SQLite / 500 en Postgres]; la lista general gana `limit` y declara `limit_cap: 50`;
`db.runs_by_thread(thread_id, limit, after_run_no)` es variante de biblioteca con cursor por `run_no` — NO la puerta HTTP
[corrector: el parámetro dejó de llamarse `after` para que las dos semánticas no se confundan]) · **`GET /threads/{thread_id}`** → `{thread_id, root_run_id,
root_run_no, label 'T-<run_no raíz>', root_pre_adr_0079, root_question_id, turns[{run_id, run_no, turn_no,
turn_kind, parent_run_id, state, verdict, decision_state, origin, created_at, user_id, closed_by,
has_frozen_record, n_gap_flags, gap_flags_unreadable, estimated_cost_usd [PROYECCIÓN],
cost_projection_complete}], n_turns, n_closed, n_turns_without_record, authors[], date_range,
gap_flags_union[{text, count, first_turn, last_turn}] (igualdad lower/strip, conteo POR TURNO, texto de la
PRIMERA aparición — jamás prosa nueva), total_cost_usd {value [PROYECCIÓN], complete, n_turns_without_usage,
n_turns_cost_incomplete, n_turns_cost_unknown, cost_class}, pivot_suggested {value, rule, threshold,
turns_considered, reason, threshold_source} (regla: los últimos `WITT_PIVOT_TURNS` turnos con registro cuyo conjunto de
`gap_flags` NO se redujo — "se redujo" = subconjunto PROPIO del anterior — y último conjunto no vacío; con menos
turnos → `false` + `'insufficient-turns'`), origins {origin: n}, origin_unknown_label}`; 404
`thread_not_found`. **Todo es conteo o suma etiquetada sobre valores YA congelados; nada del modelo.** `_run_view`
expone `parent_run_id, thread_id, turn_no, turn_kind, origin, root_question_id` TAL CUAL de la fila (sin
`setdefault`: si `list_runs` olvidara una columna, la lista debe VERSE distinta del detalle — el gate lo mide).

**(I) Contrato `render_contract_version "1.8"`.** `frozen.thread = {thread_id, parent_run_id, turn_no, turn_kind,
parent_state, parent_run_no, root_question_id, root_run_no [T5], context_delivery {synthesizer: null|bool,
panel: false, skipped_reason, prompt_components[], synthesizer_note?}}` · `frozen.thread_context` = snapshot
íntegro que el modelo VIO (igual que `plan`) | `null` + `frozen.thread_context_skipped_reason` (`'root-turn'` |
`'parent-identity-invalid'` | `'kill-switch WITT_THREAD_CONTEXT=0'` | `'… at execution …'` |
`'thread_context_json-absent …'` | `'thread_context_json-unparseable'`) · `frozen.thread_parent_matches_run` (bool |
`null`) + `_state ∈ checked | no-parent | no-snapshot | parent-without-frozen-record` + `_rule` (`THREAD_SHA_RULE`: sha256
del blob sin `{frozen_at, closed_by}`; `None == None` jamás se lee como `true`) · `frozen.precedent_citations` +
**`precedent_citations_state ∈ checked | no-parent | parent-not-closed | parent-without-frozen-record`** [corrector] ·
`frozen.origin {value, source (al encolar), source_at_execution {value, source, same_value_as_column}, note}` ·
`frozen.episode_axes` · **`frozen.plan_parent_matches_run` / `plan_snapshot_matches_run` (bool | `null`) + `_state ∈
checked | no-plan | plan-predates-thread-declaration | no-parent | no-snapshot`** [corrector] ·
`deterministic_checks.{thread, parent_identifier_leak (+_state ∈ checked | no-parent | no-snapshot, +_rule),
disjoint_series (+_state ∈ checked | no-parent | parent-not-precedent)}` · `epistemic_summary +thread_id/turn_no/origin`
· `plan.{thread_parent_run_id, thread_parent_frozen_sha256}`. El PDF pinta el `null` de `thread_parent_matches_run` por
su `_state` (`no-parent` → "no aplica (turno raíz)"; `no-snapshot` → "no verificable: el snapshot no viajó";
`parent-without-frozen-record` → "no verificable: el padre no tiene registro"; sin `_state` → "estado no consta") y el
precedente vacío con su razón; la etiqueta `T-<run_no raíz>` sale ÚNICAMENTE de `thread.root_run_no` (los dos fallbacks
que inferían se quitaron) [corrector]. La versión sigue en "1.8": el contrato aún no se ha desplegado. Eventos: `run.state {queued, origin
{value, source}, thread {…, context 'built'|'skipped', context_skipped_reason, context_bytes,
n_comments_included}}` y `stage.thread_context` (agente `runs`) con `bytes`, `n_comments_included`,
`comments_truncated`, `previous_answer_present`.

**Costuras del integrador [T5]** (documentadas en código con "T5"): (1) `db.closed_runs` SELECTea también
`turn_kind` y `parent_run_id` — sin ello el item de precedente salía `turn_kind: null` en una raíz REAL (=
"sin investigación" falso; la lesión lista/detalle de ADR-0055/0076, medida por `smoke_precedent` ADR-0079b); (2)
`frozen.thread.root_run_no` (`runs._root_run_no`: la propia corrida si `thread_id == run_id`, si no la fila
`thread_id`, raíz real o virtual) — el insumo de la etiqueta `T-<run_no raíz>` que `record_pdf._thread_label`
imprime en CUALQUIER turno (sin él declaraba `T-?`); (3) `record_pdf` lee `human_comments` como el SOBRE dict que
`runs.py` persiste (`'n_included de n_total'`, `truncated` del sobre) — leía una lista y habría impreso "no
consta" con comentarios presentes; (4) `smoke_run_pipeline.py` asserta el contrato contra
`runs.RENDER_CONTRACT_VERSION` (el literal `"1.8"` se asserta UNA vez, en la sección ADR-0079 — `smoke_thread_context`
también lo asserta ahora contra la constante [corrector]).

**Corrector final** (tres revisiones — doctrina · corrección · contrato —, marcado "corrector ADR-0079" en código): (1)
default `'production'` en `GET /notes/questions/calibration` (alta); (2) `limit < 1` → 400 en ambos ramales de `GET /runs`
+ `ValueError` en `db.list_runs` (alta); (3) letra de precedente sólo con padre `closed` + `precedent_citations_state`
(media, decisión de §E cambiada); (4) `parent_identifier_leak_state 'no-snapshot'` (media); (5) el PDF lee
`thread_parent_matches_run_state` (media); (6) `frozen.origin.source` copiada del sobre de encolado +
`source_at_execution` (media); (7) `plan_parent_matches_run` / `plan_snapshot_matches_run` (media); (8) índice único
`ux_runs_thread_turn` + re-derivación en `new_run` — cierra las carreras de `turn_no` y `turn_kind` y la pérdida de
página del cursor (media ×3); (9) DOI sin punto final (media); (10) `WITT_PIVOT_TURNS` tolerante + `threshold_source`
(media); (11) `root_question_id` sin sembrar del hijo; `precedent.turn_item` en el camino real (+ passthrough de llaves
null); `_thread_label` sin inferencia; `runs_by_thread(after_run_no)`; unidades `chars`/`bytes` declaradas;
`db.has_children`; filas de precedencia en `EPISODE_AXES_MAP`; orden estable de comentarios (bajas). Fuera del alcance
del corrector (webapp / evaluation, otros dueños): `witt-webapp/tools/gen_fixtures.py` y `evaluation/run_held_out_v2.py`
no fijan `WITT_RUN_ORIGIN` → sus corridas nacen `production` (ver Decisiones abiertas).

## Consequences

- **Contrato: `render_contract_version` sube a "1.8"** — campos aditivos (lista en (I)); `citations` NO cambia
  de forma; ningún campo existente cambia de tipo o dominio. La regla de paridad de ADR-0078 se aplica igual: la
  webapp tipa lo nuevo como opcional (`?`), no congela el número.
- **La webapp debe tipar y pintar** (`witt-webapp/src/api/types.ts`, todo `?`): (1) la vista de corrida —
  `parent_run_id`, `thread_id`, `turn_no`, `turn_kind`, `origin`, `root_question_id` (NULL = "anterior al
  contrato", jamás `0` ni "turno 1"); (2) `RunBody.parent_run_id`, `PlanBody.parent_run_id` y los tres campos
  nuevos de la respuesta de `POST /runs/plan`; los errores tipados `404 {state: 'parent_not_found'}` y `409
  {state: 'parent_not_terminal', parent_state}`; (3) la respuesta paginada de `GET /runs?thread=` (`runs, thread_id,
  limit, after, n, has_more, next_after, order`) y `limit`/`limit_cap` en la lista general; (4) `GET
  /threads/{id}` completo — la pantalla "investigación T-N": turnos en orden, `gap_flags_union` como conteos,
  `total_cost_usd` con `complete` (INCOMPLETO cuando `false`, igual que M8), `pivot_suggested` como sugerencia
  con su regla (+`threshold_source`), `root_pre_adr_0079` como "raíz anterior al contrato"; (5) el registro congelado 1.8 —
  `thread`, `thread_context` (el insumo, plegado por default; `bytes`), `thread_context_skipped_reason`,
  `thread_parent_matches_run` (+`_state`: tres estados, jamás un check verde por `null`), `precedent_citations` +
  `precedent_citations_state` (letras, "NO ADMISIBLE COMO EVIDENCIA"; vacío con su razón), `origin {value, source,
  source_at_execution}`, `episode_axes` (cuatro ejes en palabras, tabla de (G)), `plan_parent_matches_run` /
  `plan_snapshot_matches_run` (+`_state`), `deterministic_checks.{thread, parent_identifier_leak (+_state 'no-snapshot'),
  disjoint_series (+_state 'parent-not-precedent')}`; `epistemic_summary
  .{thread_id, turn_no, origin}` en la fila del Banco; (6) `include_origins` en `/precedent/search`,
  `/calibration` y `/notes/questions/calibration` y sus declaraciones `origins_included` / `excluded_by_origin` /
  `origin_unknown_included` (el número nunca sin su alcance); (7) los eventos `run.state.thread` y
  `stage.thread_context` en la Traza.
- **Producción.** Al redeploy `_migrate` añade las 7 columnas y 3 índices (`ix_runs_thread_id`, `ix_runs_parent_run_id`,
  `ux_runs_thread_turn` ÚNICO; `IF NOT EXISTS`, idempotente; el índice que no aplique deja huella en stderr). **Toda corrida existente queda NULL** en las siete: la vista las
  sirve así, `GET /threads/{id}` las lee como raíz virtual, el precedente las INCLUYE y las DECLARA
  (`origin_unknown_included = n`). Toda corrida nueva nace `origin 'production'` (`source 'default:production'`;
  si se fija `WITT_RUN_ORIGIN=production` en Dokploy, `'env:WITT_RUN_ORIGIN'`). El compose lleva placeholders
  con los defaults declarados; vacío = default (jamás un crash de import).
- **Históricos NO se recalculan.** Ningún registro anterior gana `thread`/`origin`/`episode_axes`; el PDF y la
  Hoja lo declaran (`NO INSTRUMENTADO (contrato < 1.8)`). Un backfill sería ADR aparte.
- **Costo de modelo.** Un turno con snapshot manda al sintetizador y al planner hasta ~1200 chars de respuesta
  anterior + ≤8 comentarios/8000 chars + hallazgos del panel: el prompt crece (proyección; `bytes` viaja en el
  evento `stage.thread_context` y en el snapshot — el gate EN VIVO 1 lo mide). El PANEL no crece: recibe el
  resumen, no el texto.
- **Fronteras declaradas, no resueltas:** (a) ~~carrera de `turn_no`~~ RESUELTA por el corrector (índice único
  `ux_runs_thread_turn` + re-derivación en `new_run`; también la de `turn_kind`, que no estaba declarada); (b)
  `GET /runs?thread=&mine=true` filtra además por usuario (turnos ajenos de la misma investigación no salen); (c) una
  corrida con `origin 'invalid-env:<v>'` no puede pedirse por `include_origins` (400: el enum manda); (d) plan heredado
  (ver (B)); **(e) la fuga por PARÁFRASIS, símbolos de gen o cifras del turno anterior no tiene predicado
  determinista** — `parent_identifier_leak` cubre 5 patrones de identificador; ~1200 chars de prosa del padre, sus
  `gap_flags`, hallazgos y comentarios viajan al sintetizador y una afirmación re-formulada puede reaparecer en el hijo
  sin que nada la marque; sólo la cláusula anti-fuga (prompt) y el juicio del lector — el registro conserva el snapshot
  íntegro (`frozen.thread_context`) para auditarla a mano; el panel no ve el texto del padre y tampoco puede señalarla.
- **Decisiones abiertas para Emmanuel:** `plan_declared 'inherited'` (copiar el plan del padre) vs. plan nuevo
  siempre (lo implementado); si `/usage` y `plan_history` deben filtrar por origen (hoy no, declarado en (F));
  **procedencia de los fixtures y las evaluaciones** [corrector, fuera de este repo/obra]: `witt-webapp/tools/gen_fixtures.py`
  fija la máscara hermética pero no `WITT_RUN_ORIGIN` → sus corridas nacen `origin 'production'` cuando el enum tiene
  `fixture` para ellas (una línea: `os.environ["WITT_RUN_ORIGIN"] = "fixture"` antes de importar `runs`, y asertar
  `origin == 'fixture'` en el gate de la webapp); igual `evaluation/run_held_out_v2.py` (`setdefault("WITT_RUN_ORIGIN",
  "replay")`). Los dueños de esos archivos deciden.

### Variables de entorno (defaults declarados en código; el valor efectivo y su fuente viajan en el registro)

| Variable | Default | Lector | Efecto |
|---|---|---|---|
| `WITT_THREAD_CONTEXT` | `1` | `runs._thread_context_enabled` (al encolar Y al ejecutar) | `0` = kill-switch: columnas sí, snapshot no arma / no viaja; `skipped_reason` declarado; `kill_switch` en el sobre |
| `WITT_THREAD_COMMENTS_MAX` | 8 | `runs._thread_limits` (`_env_int_tolerante`) | comentarios del padre en el snapshot; `truncated: true` + `limits` declarados |
| `WITT_THREAD_COMMENTS_CHARS` | 8000 | idem | chars TOTALES de esos comentarios |
| `WITT_THREAD_ANSWER_CHARS` | 1200 | idem | `previous_answer.direct_answer[:n]` + `direct_answer_truncated` + `chars_total` |
| `WITT_RUN_ORIGIN` | sin default explícito (derivación: `dev-offline` con `WITT_ALLOW_RUNS_OFFLINE=1`, si no `production`) | `runs.run_origin` | `runs.origin` + `frozen.origin {value, source}`; fuera del enum → `invalid-env:<v>` declarado |
| `WITT_PIVOT_TURNS` | 3 | `app.PIVOT_TURNS` (al importar, vía `runs._env_int_tolerante`: vacía / no numérica / ≤ 0 → 3 DECLARADO, jamás un crash de import [corrector]) | ventana de `pivot_suggested` en `GET /threads`; la regla y `threshold_source` viajan en la respuesta |
| `WITT_ALLOW_RUNS_OFFLINE` | ya existía | `runs.run_origin` (insumo nuevo) | `1` → origen `dev-offline` cuando `WITT_RUN_ORIGIN` no está |

### Gates NO-SPEND (corridos el 2026-09-15, offline, máscara `WITT_BACKEND_DB_URL="sqlite:///…/witt-smokes/smoke-<nombre>.db"` · `NEO4J_URI=""` · `RAG_BACKEND=sparse` · `OPENAI_API_KEY=""` · `ANTHROPIC_API_KEY=""` · `WITT_RUN_ORIGIN=smoke`)

| Gate | Resultado |
|---|---|
| `smoke_run_pipeline.py` (integrador; +30 checks ADR-0079 y +6 del corrector — `limit` negativo, DOI con punto, fuente del origen al encolar, plan↔padre, carrera de `turn_no` contra `ux_runs_thread_turn`, filas de precedencia de los ejes; la raíz se cierra ENTRE el encolado del hijo y su ejecución: raíz/refine/rerun/branch por la puerta, camino REAL del sintetizador con el `user_text` capturado — `{question, evidence, thread_context}` —, panel con evidencia limpia, snapshot sin la nota de calificación, `precedent_citations` letra A + `validate_disjoint` (y la `'label':'A'` a mano que FALLA), `thread_parent_matches_run`, fuga `PMID` → inadmisible, kill-switch al encolar y al ejecutar, `GET /threads` con `gap_flags_union`/costo/pivot, `GET /runs?thread=` paginado, `/precedent/search` y `/calibration` con `include_origins`, fila pre-ADR NULL + raíz virtual, `episode_axes` sobre 6 registros + la función pura, PDF INVESTIGACION/EJES) | 181/181 → 211/211 → **217/217 PASS** (corrector; corrido dos veces: el orden de comentarios ya no depende del uuid) |
| `smoke_threads_db.py` (T1: migración aditiva e idempotente, NULL sin backfill, `list_runs(thread_id, after)`, `get_children`/`has_children`/`thread_turns`/`max_turn_no`/`runs_by_thread(after_run_no)`, filtro por origen + contador, `ux_runs_thread_turn`, `list_runs(limit=-1)` → ValueError) | 39/39 → **42/42 PASS** |
| `smoke_thread_context.py` (T2: derivación, snapshot, inyección stub y REAL, precedente≠evidencia, fuga y control, origen ×4, ejes ×5, contrato 1.8, kill-switch, identidad inválida, padre failed, padre pre-ADR (cerrado a mano), padre cerrado con la letra [A] vía `turn_item`; padre awaiting_closure SIN letra + `parent-not-closed`; `no-snapshot` en la fuga) | 35/35 → **36/36 PASS** |
| `smoke_runs_thread_http.py` (T3: ASGI TestClient — 404/409, raíz/refine/rerun/branch, lista=detalle, NULL, snapshot sin ratings, comentarios truncados, `GET /threads`, paginación, `limit` -1/500/0, `WITT_PIVOT_TURNS` tolerante + `threshold_source`, origin, `include_origins`, default del tablero del agente, identidad inválida, plan con padre) | 51/51 → **54/54 PASS** |
| `smoke_precedent.py` (T4: filtro por origen default + `include_origins`, dos alcances = dos índices, `turn_item` → letra 'A' kind 'turn', PDF INVESTIGACION/EJES, registro pre-1.8 → NO INSTRUMENTADO, los tres estados del `null` en el PDF y `T-?` sin inferencia) | 15/15 → 27/28 → 28/28 → **30/30 PASS** |
| `smoke_ratings_calibration.py` (T4: `origins_included` default, smoke/simulation excluidas y contadas, `include_origins`, 400 fuera del enum) | 39/39 → **44/44 PASS** |
| `smoke_question_agent_http.py` (el tablero del agente: SIN parámetro `origins_included ['production']`, el borrador respaldado por la corrida `smoke` FUERA y CONTADO — `excluded_by_origin {smoke: 1}`, `n_borradores_excluidos_por_origen 1` —; con `include_origins=smoke` el tablero completo) | 33/33 → **35/35 PASS** |
| resto del directorio (`entities` 16 · `fetch_paper` 41 · `m5v2_http` 32 · `niches` 21 · `notes_http` 28 · `pubmed_tool` 32 · `query_service` 47 · `run_comments_http` 14 · `run_recovery` 40 · `runs_list_http` 17 · `search_queries` 163 · `zfin_tool` 26) | todos PASS, exit 0 |

### Gates EN VIVO pendientes (NO ejecutados en esta obra — gastan modelo o requieren el redeploy; los corre Emmanuel)

1. **Continuar una corrida real en prod**: `POST /runs {question, entities, parent_run_id: <run cerrada de
   witt-ai.com.mx>}` → en la vista `turn_no 2`, `turn_kind 'refine'`, `thread_id = run_id del padre`; en la Traza
   el evento `stage.thread_context` con `bytes` y `n_comments_included`; en el registro `thread_context` íntegro,
   `precedent_citations [{l: 'A', …}]`, `thread_parent_matches_run: true`, `deterministic_checks
   .parent_identifier_leak []` con el sintetizador REAL (que la cláusula anti-fuga baste); `token_usage` del turno
   comparado con la mediana histórica (el snapshot crece el prompt — medir).
2. **Origen `production` en la vista**: la primera corrida nueva tras el redeploy muestra `origin: "production"`
   en `GET /runs` y `frozen.origin.source` (`default:production`, o `env:WITT_RUN_ORIGIN` si se fijó en Dokploy);
   las anteriores `origin: null`.
3. **Precedente excluyendo smokes**: `GET /precedent/search?q=…` en prod devuelve `origins_included
   ["production"]`, `excluded_by_origin {}` (ningún smoke corre contra la BD de prod — verificarlo, no
   asumirlo) y `origin_unknown_included = n` de corridas cerradas pre-ADR; con `include_origins=smoke` el corpus
   no cambia.
4. **`GET /threads/{id}` sobre la investigación real** del gate 1: `label T-<run_no>`, `n_turns 2`,
   `total_cost_usd.complete` según los turnos, `pivot_suggested {value: false, reason: 'insufficient-turns…'}`.
5. **`_migrate` en el log de arranque** sin error (7 `ADD COLUMN` + 3 índices, uno ÚNICO) y `GET /runs/{id}/record.pdf` del
   turno 2 con las secciones INVESTIGACION (`T-<run_no raíz>`, `[A]`, `COINCIDE`, `comentarios humanos: n de m`) y
   EJES DEL EPISODIO.

<!-- ADR-0086 del repo. El cuerpo de abajo es el DISEÑO (síntesis de 3 diseñadores + 2 jueces, 2026-09-16) y se conserva
     como registro de por qué cada cosa es como es. Lo que de veras se construyó, con su commit y su gate MEDIDO, está en la
     sección «Lo construido» que sigue al Status: donde el diseño y lo construido difieran, MANDA «Lo construido» y la
     diferencia está declarada ahí. Decisión del orquestador incorporada: WITT_ATTESTED_PATIENT_MATERIAL default 0. -->

# ADR-0086 — Imágenes ATESTIGUADAS del laboratorio: una imagen que aporta una persona es PRIOR ART con procedencia registrada (quién, cuándo, consentimiento, licencia declarada), jamás evidencia ni cita; entra SÓLO por el ledger del consejo, sus bytes viven FUERA del registro en almacenamiento PRIVADO (disco local declarado hoy → MinIO privado cuando Emmanuel confirme), los ven a lo sumo DOS lentes del panel como juicio y NUNCA el sintetizador, se sirven sólo al autor por default, jamás en el PDF, y se retiran por tombstone sin tocar el registro (contrato 1.14)

- **Status:** Proposed — diseño 2026-09-16, **obra 2026-09-21: diez de trece rebanadas commiteadas y medidas (ver «Lo construido»); faltan F9 (integrador + tres revisores) y el tag `contract-1.14-frozen`**. Pasa a Accepted cuando Emmanuel apruebe OE1–OE6 y los gates EN VIVO sustituyan las proyecciones de costo por medición con fecha. Origen: plan v3
  del brief *Consejo de agentes* aprobado el 2026-09-14 — §3 R5 («la evidencia puede ser imagen»: lectura sólo por dos lentes del
  panel etiquetada juicio; el sintetizador nunca recibe bytes), §4 A («Aprobar y correr: keep / discard con razón / «yo lo aporto»
  (atestiguado) + «qué sabes ahora» + imágenes — único punto donde la prosa se vuelve gasto»), §7 último párrafo («Imágenes
  atestiguadas del laboratorio (ADR-0086): … clase ATESTIGUADA … vistas solo por el panel. Dónde viven los bytes es decisión tuya»),
  §14 («dónde viven los bytes de las imágenes atestiguadas» — MinIO privado por default del plan), la fila ADR-0086 de la tabla de
  ADRs (gate NO-SPEND: «tope, mime, sha verificado, autor derivado, sin DELETE; la imagen del padre aparece en el hijo como
  image-attested») y §18 paridad («cada capacidad del backend nace con su ranura»). **Apila sobre ADR-0084 (contrato 1.13)** —
  ADR-0084 se está IMPLEMENTANDO en el worktree `witt-organogenesis-0084` desde su borrador
  (`scratchpad/adr-0084-diseno.md`); este ADR NO toca ese worktree y asume sus formas 1.13 (ver «Formas 1.13 que asume»). Árbol
  de referencia: `feat/adr-0083-figuras-pdf` @ `7d9ce15` (tag `contract-1.12-frozen`, ADR-0078…0083 commiteados). La webapp
  `witt-webapp` está en `feat/adr-0083-paridad` @ `32e2996` (paridad 1.12 completa); la paridad 1.14 se lista aquí y la hace OTRO
  workflow. Síntesis de tres diseños (A doctrina-privacidad-fidelidad · B webapp-primero · C operación-almacenamiento-riesgo) y
  dos juicios (juez 1: A 32 · C 31 · B 30; juez 2: A 34 · B 31 · C 30): parte del ganador (A) e injerta lo que ambos jueces
  pidieron de B y C; donde los jueces divergen (el TRANSPORTE), la decisión y su porqué van marcados *(síntesis)*. Estilo de
  cita: **ruta:función** con los números de línea del árbol @ `7d9ce15`, VERIFICADOS hoy (el nombre de la función es lo estable).
- **Decisiones YA tomadas por Emmanuel (no se relitigan aquí):** una imagen que aporta una persona es ATESTIGUADA (clase
  atestiguada; procedencia registrada: quién, cuándo, con qué consentimiento/licencia declarada), NUNCA evidencia ni medición ·
  vive junto a `human_attestations` (llave HERMANA de `evidence`), jamás entra a `citations` ni al gating de citas;
  `attestation_identifier_leak` sigue vigente · el sintetizador recibe a lo sumo caption y metadatos declarados por la persona
  (rotulados atestiguados), JAMÁS bytes · sólo las dos lentes de visión pueden ver los bytes (juicio, con la regla literal de no
  derivar números) y se declara qué vieron · bytes FUERA del blob (ADR-0074) en almacenamiento PRIVADO — MinIO en Dokploy por
  default del plan (credenciales PENDIENTES de Emmanuel: la obra funciona con un backend de disco local DECLARADO hasta entonces) ·
  sha256 al subir y recalculado al servir · tope de tamaño y de número · tipos permitidos por magic bytes (PDF jamás) ·
  EXIF/metadatos eliminados o declarados · material de paciente → bandera del `regulatory-ethics-advisor` §7 y consentimiento
  explícito obligatorio · puerta `GET …/attestations/{sha256}` con autorización (sesión; 403 por default fuera del autor) y JAMÁS
  embebida en PDF ni redistribuida · kill-switch `WITT_ATTESTED_IMAGES=0` byte a byte · smokes offline con fixtures sintéticos ·
  contrato ADITIVO 1.14 · toda llave nueva del frozen con sección en el PDF (gate 0083 K) y ranura en la webapp · costo de
  visión medido/proyectado por imagen · proceso único `--workers 1`; SQLite/Postgres; migraciones aditivas; §6 no-hang; §7
  compuertas humanas; sin dependencias nuevas pesadas (stdlib primero).
- **Relates:** ADR-0043 (tres estados) · ADR-0047 (permisos planos: toda sesión lee; aquí los BYTES son la excepción declarada) ·
  ADR-0051/0081 (tokens MEDIDOS, USD PROYECTADOS; `models.vision_tokens` única sede de la fórmula) · ADR-0056 (autoría y hora las
  pone el servidor; el cliente REFIERE por id/sha, jamás manda el objeto) · ADR-0061 (cada componente que gasta cuadra en M8) ·
  ADR-0074 (nada binario en el blob; el blob congelado jamás se reescribe) · ADR-0077 (comentarios: público, append-only, «un
  retirado tachado y legible, no un DELETE») · ADR-0079 (`thread_context` como llave hermana; `parent_identifier_leak`) ·
  ADR-0082 (F: el ledger humano — `aporto`/`knowledge_now` clase ATESTIGUADA, `human_attestations` FUERA de `evidence`,
  `ATTESTATION_ANTI_LEAK_CLAUSE`, predicado DURO `attestation_identifier_leak`, `covered-by-attestation` fuera del gating,
  `POST /plans/{id}/council/ledger`, copia server-side al encolar F.4) · ADR-0083 (figuras: `lib/figures.py` reutilizable —
  `sniff_mime`, `image_dims`, guardia 40 MP, transportes de bloques —, dos lentes de visión, `figure_readings` class
  `model-judgment`, `FIGURE_READING_RULE`, `GET /runs/{id}/figures/{sha256}` con sha recalculado, kill-switch con EXACTAMENTE 3
  excepciones, gate de cobertura del PDF, `_FiguresUsageAccumulator`) · ADR-0084 (1.13: `frozen.web_locator`, `SECCIONES` 53,
  `WEB_DECLARED_EXCEPTIONS`; borrador) · CLAUDE.md §7 («Compliance and budget decisions never go through automatic filtering.
  Direct human gate, no exceptions» :149; «Figure-only claims are NOT asserted» :156; la DI jamás se muta :157).
- **Affects:** `analysis/scripts/lib/attestations.py` (NUEVO) · `figures.py` (sólo los tres builders de bloques: `attested=None`
  aditivo) · `composite_auditor.py` (`audit(..., attested=None)`, `ATTESTED_READING_RULE`, `VERDICT_TOOL.attested_readings`,
  `saw_attested`) · `verify_output.py` (`attested_predicates`) · `models.py` (`ENV_TABLE` += 14 filas `adr '0086'`;
  `SNAPSHOT_FIELDS` += 4 FUERA de `panel_signature`) · `council.py` (`R2_PREAMBLE_ATTESTED_IMAGES` condicional;
  `apply_ledger_decisions(images=)`; `summary_for_thread += n_attested_images`) · `council_jobs.py` (una línea:
  `_inherited_criteria` propaga el conteo) · `rag_index/query_service/runs.py` (contrato **1.14**; `frozen.attested_images`;
  `human_attestations.images[]`; `deterministic_checks.attested_images`; eventos `stage.attestations.*`;
  `thread_context.parent_attested_images[]`; `token_usage.attested_images`; `ATTESTED_DECLARED_EXCEPTIONS`) · `db.py` (tabla NUEVA
  `plan_attested_images`, sin ALTER; `plan_add_event(..., heartbeat=True)` aditivo) · `app.py` (7 rutas NUEVAS; `LedgerBody.images` /
  `decisions[].images` / `patient_material_acknowledged`; `_plan_view.attested_images`; `/usage += attested_images`;
  `ATTESTED_EXPOSE_HEADERS`) · `record_pdf.py` (`SECCIONES` 53 → 54: `attested_images`/`imagenes-aportadas`, SIN miniaturas) ·
  `requirements.txt` (`minio>=7.2,<8` pin; `python-multipart>=0.0.9` — la MISMA línea que `ingest_service`) ·
  `docker-compose.query.yml` · `README.md` · `.gitignore` (`attested_private/`) · `docs/decisions/README.md` · CLAUDE.md §7 (una
  viñeta) · fixtures SINTÉTICOS generados por código (`fixtures/attested/MANIFEST.json`, cero binarios nuevos en git) · smokes (2
  NUEVOS + 10 tocados) · `analysis/scripts/smoke_live_attestations.py` (NUEVO, instrumento de los gates en vivo) · witt-webapp
  (proxy `route.ts` + tipar y pintar; ver *Consequences*). **Cero mutación de la DATA INAMOVIBLE, del registro congelado existente y
  de `mcp_cache`; cero gasto de modelo en la obra; CERO red en los smokes (`urlopen` bloqueado y contado); `.secrets/deploy.env`
  existe y NO se lee.**
- **Anclas @ 7d9ce15 (verificadas hoy):** `runs.py` (5 200 líneas): `RENDER_CONTRACT_VERSION = "1.12"` :51 · `SYNTH_TOOL` :244 ·
  `_agents_invoked` :892 · `_panel_findings` :1008 · `THREAD_CONTEXT_EXCLUDED` :1041 · `build_thread_context` :1185
  (`human_comments` :1221; `council_summary` :1281) · `extract_identifiers` :1317 · `parent_identifier_leak` :1329 ·
  `_PROMPT_FIGURE_KEYS` :1559 · `_compact_evidence` :1608 · `THREAD_ANTI_LEAK_CLAUSE` :1650 · `ATTESTATION_ANTI_LEAK_CLAUSE`
  :1665 · `synth_system(pass_label, thread_context=False, human_attestations=False, vision_findings=False)` :1671 ·
  `_default_synthesizer` :1720 (`payload["human_attestations"]` :1740) · `TOKEN_STAGES` :1961 · `_vision_tokens` :2076 ·
  `_token_usage` :2226 · `_gate(answer, bundle, thread_snapshot, run, pass_no, attestations=None, figures_cfg=None,
  figures_cache_root=None)` :2594 · `snapshot_extra` :2930 · `FIGURES_DECLARED_EXCEPTIONS` :3012 (constantes
  `FIGURES_TOOL_UNAVAILABLE_*` :3013-3016) · `FIGURES_EVENT_TYPES` :3092 · `_figures_stage` :3095 · `_figures_for_panel` :3174 ·
  `_audit_accepts_figures` (inspect.signature) :3201 · `_figures_panel_kwargs` :3212 · `council_ledger_from` :3375 ·
  `human_attestations_of` :3455 (`ledger.get("state") != "approved" → None` :3459) · `attestation_identifier_leak` :3480
  (`json.dumps(attestations)` :3484) · `_attestation_leak_check` :3492 · `council_run_gate` :3529 · `_frozen_ledger_view` :3617 ·
  `execute_run` :3716 (`fig_cfg/fig_enabled/fig_cache_root/fig_lenses/figures_holder` :3770-3774; `c_attest =
  human_attestations_of(c_ledger)` :3870; `stage.council.ledger` :3882; `wanted["human_attestations"]` :3957;
  `attest_delivery["synthesizer"]` :3973; `_gate(... pass1)` :4009; ctx r2 `human_attestations` :4040; `_figures_stage` :4247;
  ctx r3 :4287; `_gate(... pass2)` :4391; `_figures_panel_kwargs` + `audit(**fig_kw)` :4408-4416; revisión :4465-4479;
  `_figures_fill` :4506; `frozen_council.human_attestations` :4559-4563; `frozen = {` :4596; `agents_invoked` :4671; `"council"`
  :4674; `"figures"` :4678; `deterministic_checks`/`token_usage` :4696-4697; `epistemic_summary` :4830 (`figures_*` :4856-4858);
  `update_run(epistemic_summary_json=)` :4864) · `compose_council_json` :4929 · `new_run` :4964. `app.py` (2 981):
  `FIGURE_EXPOSE_HEADERS` :124 · `CORSMiddleware(allow_methods=["GET","POST"], allow_headers=["Authorization","Content-Type"],
  expose_headers=…)` :129-132 · `_user_of` :137 · `COUNCIL_LEDGER_STATES` :590 · `_compose_run_council_json` :888 · `_run_view`
  :921 · `create_run` :999 (`council_copy` :1053; `mark_plan_used` :1068) · `create_run_comment` :1367 · `get_record_pdf` :1399 ·
  `_frozen_o_409` :1441 · `_identidad_o_409` :1452 · `get_run_figures` :1495 · `get_figure_bytes` :1558 (sha recalculado «sobre
  LOS BYTES QUE SALEN» :1614; headers :1620-1627) · `/runs/{run_id}/events` :1632 · `_plan_view` :1700 · `GET /plans/{plan_id}`
  :1736 · `/plans/{plan_id}/events` :1744 · `LedgerDecisionBody` :1773 · `LedgerBody {decisions, knowledge_now, approve}` :1780 ·
  `_ledger_precondiciones` :1790 · `_plan_event(plan_id, type_, payload)` (agent 'council') :1823 · `council_ledger` :1827
  (`hard_rule_requirements_undecided` :1898; evento `council.ledger` al aprobar) · `/council/skip` :1945 ·
  `_FiguresUsageAccumulator` :2282 · `GET /usage` :2560 · `GET /config-history` :2705. `db.py` (2 308): `runs.frozen_record_json`
  :96 · `plans` :112 (`council_ledger_json` :131; `council_last_event_at` :137) · `plan_events` :148 · `run_comments` :246 ·
  `init_db` → `metadata.create_all` :317-318 · `_migrate` (sólo `ADD COLUMN`) :322 · `council_schema_state` :478 ·
  `validate_token` :560 · `get_plan` :672 · `mark_plan_used` (`WHERE run_id IS NULL`) :678 · `plan_add_event` :776 (refresca
  `council_last_event_at` :788) · `set_plan_ledger` :870. `figures.py` (1 572): `MODULE_VERSION` :54 · `REQUEST_B64_MB = 8` :69 ·
  `MAX_MEGAPIXELS = 40` :70 · `CHUNK_BYTES` :71 · `LICENSES` :79 · `MEDIA_TYPES` :134 · `FORBIDDEN_PROMPT_KEYS` :150 · `ENV_SPECS`
  :188 · `env_config` :280 · `sniff_mime` :620 · `image_dims` :635 · `cache_dir` :689 · `cache_dir_state` :710 · `verify_cached`
  :736 · `evict_lru` :761 · `select_for_panel` :1419 · `figure_text_label` :1478 · `anthropic_blocks` :1484 ·
  `openai_responses_parts` :1495 · `openai_chat_parts` :1507. `composite_auditor.py` (1 743): `VISION_LENSES` :147 ·
  `VISION_LENSES_MAX = 2` :151 · `SAW_FIGURES_DETAILS` :155 · `FIGURE_READING_RULE` :160 · `vision_lenses` :178 ·
  `parse_figure_readings` :457 · `VERDICT_TOOL` :507 (`figure_readings` :565) · `_anthropic_tool_call(..., user_content=None)` :746 ·
  `_responses_kwargs` :933 · `_openai_chat_call` :1123 · `_default_caller` :1202 (`member.get("figures")` → bloques por transporte
  :1216-1228) · `_vision_plan` :1275 · `_figures_for_member` :1296 · `_vision_summary` :1402 · `audit(..., figures=None,
  vision_lenses=None)` :1446 · `system + FIGURE_READING_RULE` sólo si viajan :1546 · fila `saw_figures`/`figure_readings`
  :1618-1626. `verify_output.py`: `admissible(..., extra_predicates=None)` :227 (conjunción :252) · `FIGURE_PREDICATES` :631 ·
  `FIGURE_RULES` :644 · `_mk_pred` :808 · `figure_predicates` :821. `models.py`: `prices` :147 · `LENSES` :182 · `ENV_TABLE` :283
  (filas `"adr": "0083"` :341-360) · `WITT_OPENAI_STORE` :298 · `SNAPSHOT_FIELDS` :378 · `panel_signature` :838 · `snapshot` :873 ·
  `VISION_TIER_LIMITS` :1061 · `VISION_TILE` :1068 · `vision_tokens` :1108. `council.py`: `FLAG_KINDS` (incluye
  `'patient-material'`) :104 · `R2_PREAMBLE` :560 · `payload_r1` :575 (`human_attestations` :589) · `payload_r2` :620 (:642) ·
  bandera `{kind, statement, gate 'human', emitted_by [a]}` (LISTA) :1569 · `apply_ledger_decisions` :1605 · `judge_coverage`
  :1717 (`covered-by-attestation` :1774) · `summary_for_thread` :1969. `council_jobs._inherited_criteria` :182.
  `council_index.py`: kind `decision` = `{requirement_id, decision, gap ≤200}` SIN `attested_text` :400-408. `record_pdf.py`
  (1 902): `KEY_BORN` :119 (`figures: '1.12'` :137) · `SERVICE_KEYS` :142 · `SECCIONES` :150 (52 filas; `figures` :179) ·
  `ORDEN_SECCIONES` :207 · asserts :234-236 · `_tres_estados` :309 · `pdf_sections_cover` :322 · `_section_figuras` :1224 ·
  `_section_gate` :1434 (`dc.figures` :1481; `conocidas` :1495-1498) · `_section_consejo` :1624 · `build_pdf` :1866.
  `raw_store.py`: `DEFAULT_BUCKET 'data-inamovible-raw'` :37 · `_client()` lazy `from minio import Minio` :66-71 ·
  `fput_object(..., metadata={"sha256": sha})` :89-90 · `presign` :96. `requirements.txt:10` `minio>=7.2` (SIN tope mayor) ·
  `rag_index/ingest_service/requirements.txt:4` `python-multipart>=0.0.9   # file uploads (UploadFile)` · `pyproject.toml:28`
  `minio==7.2.20` · `docker-compose.query.yml`: `networks: [default, neo4j_net, minio_net, dokploy-network]` :15 · `MINIO_ENDPOINT /
  ACCESS_KEY / SECRET_KEY / SECURE` :25-28 · bloque ADR-0083 :177-212 · `minio_net` :225-227 · **NINGÚN `volumes:`** (medido:
  `grep volumes` = 0) · `rag_index/deploy/docker-compose.minio.yml` publica `9100:9000` y `9101:9001` en el HOST :10-12 y monta
  `minio_data` :16-17 · `.gitignore:22` `.secrets/` · `:104` `mcp_cache/` · `Dockerfile:18` `uvicorn … --workers 1` · venv
  `dev/.venvs/witt-query-service`: `minio-7.2.20` (`api.py:1832` `put_object(self, bucket_name, object_name, data, length,
  content_type=…, metadata=None, …)` — posicional, `metadata=`), `python_multipart-0.0.32`, `starlette-1.6.0`, `fastapi-0.141.1`,
  `pillow-12.3.0` (sólo `record_pdf`). **witt-webapp @ 32e2996:** `src/app/api/[...ruta]/route.ts` (69): allowlist hacia adentro
  SÓLO `authorization`/`content-type`/`accept` :26-34 · `body: await req.arrayBuffer()` :42 · hacia afuera SÓLO `content-type` +
  `cache-control: no-store` :56-60 → **toda cabecera de respuesta del backend se descarta** · `client.ts`: `BASE = "/api"` :62 ·
  `request()` pone `Content-Type: application/json` si hay body :90-98 · `bytesDeFigura` :388 (lee `X-Witt-Figure-*` :405-408 →
  hoy `null` detrás del proxy) · `Preguntar.tsx` (2 385): `declararPlan` :565 · `crearCorrida(pregunta, entidades, planVigente,
  desde)` :597-604 (reforzar = plan nuevo con `parent_run_id`) · `DecisionLocal` :1719 · `leerErrorLedger` :1734 ·
  `precargarDecisiones` :1757 · `LedgerConsejo` :1785 · `cuerpo()` :1842 (PATCH-like `knowledge_now` :1852) · `enviar` :1856 ·
  BANDERAS `f.emitted_by.join(", ")` :1998-2006 · «¿Qué sabes ahora?» :2047 · `FilaRequisito` :2183 · radios :2337 · fieldset
  `aporto` :2362 · `Hoja.tsx` (11 301): `Entrada clave="figuras"` :669-676 · `CompuertasDelConsejo` :2125 · `GateDeterminista`
  :5581 · consumo por reviewer :7241 · `BloqueAtestiguado` :7793 · `ConsejoLedger` :7854 (`knowledge_now` :7954; «viajaron al
  sintetizador» :8030) · `EstadoFiguras` :9533 · `SeccionFiguras` :9575 · miniatura vía `bytesDeFigura` :10631-10651 ·
  `Traza.tsx` (5 167): `describir` :899 · `stage.audit.judge` :1164 · `stage.figures.*` :1463-1493 · `stage.council.ledger` :1783 ·
  `Visuales.tsx`: `ORDEN_KIND` :264 · `PanelJueces` :499 · bloque visión :584-619 · `ListaCorridas.tsx` chip figuras :494-528 ·
  `types.ts` (7 192): `RunEvent` :560 · `PanelRow` :975 · `AuditBlock` :1025 · `TokenUsage` :1155 · `DeterministicChecks` :1285
  (`attestation_identifier_leak(+_state,+_rule)` :1342-1345) · `RegistroCongelado` :2868 (`council?` :2993; `figures?` :3001) ·
  `EpistemicSummary` :3256 · `UsageReport` :3857 · `LedgerDecisionRequestKind` :4311 · `CouncilFlag` :4621 ·
  `CouncilHumanAttestationsBlock {present, n_attestations, knowledge_now_present, delivery, class?}` :5026 · `PlanView` :5558 ·
  `PlanEvent` :5595 · `LedgerDecisionRequest {requirement_id, decision, reason?, attested_text?}` :5840 · `LedgerRequest {decisions,
  knowledge_now?, approve}` :5851 · `FigureItem` :6400 · `FiguresBlock` :6639 · `FiguresIndex` :7068 · `FiguraBytesResultado` :7165 ·
  `tools/parity_check.py` (2 497): `check_rutas` :266 · `frozen_keys` :357 · `check_registro` :446 · `check_etapas` :541
  (`plan_events` :563) · `PDF_ACCESS_RE` :582 · `SECCIONES_RE` anclada :595 · `PDF_NESTED` :635 · `check_pdf` :678 ·
  `tools/gen_fixtures.py` (4 920): `ENV_ADR_0080` pop :165-171 · `ENV_ADR_0081/0083` :185-194 · `tools/parity_debt.json` =
  `{_doc[], deuda[]}`.
- **Formas 1.13 que este ADR ASUME del borrador de ADR-0084 (no las toca; si 0084 se retrasa, 0086 aterriza como 1.13 y sólo
  cambia el literal — ver (Q)):** `RENDER_CONTRACT_VERSION = "1.13"` con línea de historial · `frozen.web_locator` top-level
  SIEMPRE presente · `KEY_BORN['web_locator'] = '1.13'` y `SECCIONES` 52 → 53 (`('web_locator', 'localizador')`) ·
  `runs.WEB_DECLARED_EXCEPTIONS` (3) junto a `FIGURES_DECLARED_EXCEPTIONS` · `_gate` cablea `verify_output.web_predicates` y
  `deterministic_checks.web_locator` · `token_usage.web_locator` y `/usage.web_locator` (`_WebLocatorUsageAccumulator`) · evento
  `stage.web.locate` · tabla NUEVA `db.web_locator_usage` (create_all) · `models.ENV_TABLE` += 17 filas `adr '0084'` y
  `SNAPSHOT_FIELDS += ('web.locator', 'web.provider')` · CERO rutas HTTP nuevas · `precedent.py`, `composite_auditor.py`,
  `fetch_paper.py` sin tocar. **Ningún nombre de 0086 colisiona con 0084** (`WITT_ATTESTED_*` vs `WITT_WEB_*`/`BRAVE_API_KEY`;
  `frozen.attested_images` vs `frozen.web_locator`; `plan_attested_images` vs `web_locator_usage`; `stage.attestations.*` vs
  `stage.web.locate`).

## Lo construido (2026-09-21) — MANDA sobre el diseño de abajo

El cuerpo que sigue a esta sección es el DISEÑO: se conserva porque explica por qué cada cosa es como es. Esta sección es
lo que de veras existe en el árbol, con su commit y su gate MEDIDO. Donde diseño y obra difieran, manda esto, y la
diferencia está declarada abajo en «Dónde la obra se apartó del diseño».

Rama `feat/adr-0086-imagenes-atestiguadas` sobre `d413c28` (tag `contract-1.13-frozen`). Todos los conteos son MEDICIÓN:
los corrí yo, offline, con una base de datos, un caché y un almacén temporales por prueba, `urlopen` bloqueado y contado
en 0, y el `mcp_cache` real byte-idéntico antes y después.

| Rebanada | Commit | Qué quedó | Gate |
|---|---|---|---|
| F1 · biblioteca | `7bd721e` | `analysis/scripts/lib/attestations.py` (stdlib pura): magic bytes, borrado de metadatos sin recodificar (walkers JPEG/PNG/WebP/GIF), identidad por sha256, almacén intercambiable (`LocalStorage` 0o700/0o600 · `MinioStorage` en bucket dedicado · `FakeMemoryStorage`), vocabularios CERRADOS, fixtures SINTÉTICOS generados por código | `smoke_attestations` 100 |
| F2 · predicados | `be70d3f` | `verify_output.attested_predicates`: dos DUROS (citar una imagen aportada por id o por sha → inadmisible; su sha entre los identificadores de evidencia → inadmisible) + uno informativo; `attpred-1` | `smoke_gate_citations` 114 |
| F3a · configuración | `abc90f1` | 15 filas `WITT_ATTESTED_*` en `models.ENV_TABLE` con `adr '0086'` y `SNAPSHOT_FIELDS += ATTESTED_SNAPSHOT_FIELDS`, FUERA de `panel_signature`; la ruta y las dos credenciales quedan fuera de la tabla | `smoke_models` 102 |
| F3b · panel | `0feb489` · corrector `01674fe` | Los BYTES sólo a <= 2 lentes con visión, rotulados y separados de las figuras, con presupuesto b64 COMPARTIDO; `saw_attested` por asiento; `VERDICT_TOOL.attested_readings` + `parse_attested_readings` | `smoke_panel_vision` 77 |
| F5a · base | `3030b57` | Tabla `plan_attested_images` por `create_all` (CERO ALTER) + 9 funciones; identidad y procedencia, ningún byte | `smoke_attestations_db` 24 |
| F4 · contrato 1.14 | `6133072` · `0a8db67` | `frozen.attested_images` SIEMPRE presente en >= 1.14 con sus cuatro estados; eventos `stage.attestations.*`; `deterministic_checks.attested_images`; `epistemic_summary.attested_*`; `token_usage.attested_images`; fila en `agents_invoked`; `thread_context.parent_attested_images`; `frozen.council.ledger.images[]`; `by_model[*].attested_vision` | `smoke_run_pipeline` 423 |
| F7 · PDF | `92e7bff` | Sección 54 (`aportadas`), tres estados con el contrato de nacimiento CALCULADO, SIN miniaturas jamás, y sin el pie de foto de una imagen de paciente | `smoke_record_pdf` 78 |
| F5b · puertas | `4ad1497` | Las 7 rutas HTTP con su gate nuevo; CORS expone `X-Witt-Attested-*`; `plan_add_event(heartbeat=False)` para que `attestation.*` no mueva el latido del consejo | `smoke_attestations_http` 63 |
| J · el ledger sella | `6fb8cbc` | `images[]` en el ledger (PATCH-like), las siete validaciones, el sellado write-once con `attached_by_is_uploader` declarado, la bandera `patient-material` con gate humano, `GET /plans/{id}.attested_images` | `smoke_attestations_http` 63 |
| F6 · consejo | `cea20f5` | La cláusula de imágenes en r1/r2/r3 sólo cuando viajan; `apply_ledger_decisions(images=)`; `judge_coverage.n_with_image`; `summary_for_thread.n_attested_images`; `frozen.council.human_attestations.n_images` | `smoke_council` 85 |
| F8 · operación | este commit | Compose con las 18 variables y **los volúmenes**; `CLAUDE.md` §7; el índice de decisiones; `/usage.attested_images`; `analysis/scripts/smoke_live_attestations.py` con `--dry-run` por default | `smoke_usage_http`, compose validado |

**Barrido completo: 48 smokes en exit 0.** `urlopen` 0 en todos.

### Cuatro fallos REALES que los gates destaparon (ninguno se ve leyendo el código)

1. **El interruptor de privacidad no cerraba nada.** `view_rule` leía el envoltorio `{value, source}` de `team_view` como
   si fuera un sí/no, y un envoltorio nunca está vacío: con `WITT_ATTESTED_TEAM_VIEW=0` cualquier compañero habría
   seguido viendo lo que alguien declaró de equipo. Corregido en F1 y medido en los dos sentidos.
2. **La compuerta de citas estaba inerte justo cuando había imágenes.** `_attested_checks` le pasaba a `verify_output` el
   estado del BLOQUE (`attached`) donde va el de COMPUERTA, así que la biblioteca respetaba el literal del llamador y
   NINGÚN predicado duro entraba a la conjunción. El registro decía «adjuntas» donde debía decir «revisado». Corregido
   con `ATTESTED_CHECK_STATE_OF` en F4.
3. **Un cero estructural presentado como medición.** `ATTESTED_READING_RULE` manda al juez a reportar en
   `attested_readings` y `VERDICT_TOOL` no tenía esa llave: el modelo no podía obedecer y `n_readings` salía siempre 0.
   Corregido con la llave, su parser determinista y el cableado (`01674fe`).
4. **El 503 del almacén no existía: reventaba.** `StorageUnavailable.to_error()` pasaba su extra bajo la llave `state`,
   que `error(status, state, **detail)` ya ocupa → `TypeError` siempre. El camino que declara «almacén no disponible»
   sólo se recorre cuando algo falla de verdad, que es cuando más importa. Corregido en F5b.

Además, dos trampas de gate que se cerraron al pasar: `smoke_config_ledger_db` tenía una fecha fija (2026-09-17) que el
calendario alcanzó el 2026-09-18 (`ee2ee79`), y el fake del consejo en `smoke_run_pipeline` parseaba el payload por
`split("\n\n", 1)` — un bloque nuevo en el preámbulo lo rompía DENTRO del fake y `run_round` lo traducía a 17 miembros
`errored`, o sea el gate se degradaba a medir otra corrida en vez de fallar. Ahora localiza el JSON por su llave de
apertura y falla ruidosamente.

### Dónde la obra se apartó del diseño (declarado, no silencioso)

- **La forma del ítem congelado la declara la biblioteca, no el llamador.** El diseño listaba `n_seen_by_lenses` en el
  ítem; `runs._attested_fill` lo añadía y el ítem quedaba con 41 llaves donde `ATTESTED_FROZEN_KEYS` declara 40,
  invalidando el propio `assert` de forma de `frozen_item`. Se quitó: los lectores usan `len(seen_by_lenses)`, y
  `_attested_fill` sólo rellena dos llaves que ya existen en la forma (`seen_by_lenses` y `n_readings`).
- **`_req_prompt_view` no cambió.** El diseño contemplaba anunciar las imágenes por requisito en la vista de prompt; no
  hacía falta: las imágenes ya viajan en `human_attestations.images[]` con su `requirement_id`, así que el juez puede
  asociarlas sin una llave nueva en cada payload (y sin mover la forma de 1.12 para las corridas sin imágenes).
- **El 413 «0 bytes leídos» se prueba por la rama de `Content-Length` y por lo que NO quedó escrito**, no con un espía
  del `receive` del ASGI: el gate afirma que el detalle viene de esa rama y que no hay fila ni archivo. La afirmación es
  más chica que la del diseño, y es la que de veras se mide.
- **El gate HTTP cierra con 63 verificaciones, no con las >= 90 que el diseño proyectó.** Cada una es una conjunción de
  varias condiciones; el número de la tabla del ADR era una estimación del diseñador, no un contrato. Lo que importa es
  qué superficies quedaron medidas, y están enumeradas en el docstring del gate.
- **`apply_ledger_decisions(images=)` y el armado del ledger en `app.py` son dos caminos** (herencia de ADR-0082: la
  ruta pura devuelve `requirements[]`, la HTTP devuelve `decisions[]`). F6 les dio el MISMO vocabulario de rechazo
  (`images_without_aporto`) para que no puedan divergir en silencio, pero siguen siendo dos implementaciones.

### Lo que los tres revisores adversarios encontraron, y qué se hizo con cada cosa (2026-09-21)

Tres revisores con lentes distintas —privacidad y fuga de bytes · doctrina de la casa · corrección y **caza de
verificaciones vacuas**— leyeron el árbol ya commiteado. El tercero rompió el código a propósito en copias y midió si los
gates se ponían rojos. Volvieron con 40 hallazgos; **ninguno lo atrapaban los 48 gates en verde**.

**Arreglado, con su gate** (commits `973fe50`, `b65f572` y el de las olas 3–4):

- El **caption de una imagen de paciente salía al PDF y al prompt del turno siguiente** por `flags[].statement` — y el
  §I(iii) de este mismo ADR lo mandaba mientras el §M juraba lo contrario. Corregido el código Y el ADR.
- Un **almacén roto saltaba el kill-switch maestro**: las dos lecturas iban en el mismo `try`.
- La corrida **confiaba en la columna `attached_to`** en vez de cruzar con el ledger que la gobierna (el K.1 que este
  documento ya pedía y la obra se había saltado): aprobar y luego saltar el consejo dejaba una imagen entrando a una
  corrida que su ledger no menciona.
- El **retiro prometía más de lo que borraba**: cascada de un solo nivel (los nietos conservaban bytes servibles) y el
  resultado de cada borrado heredado se descartaba con `except: pass`.
- Dos **ceros estructurales** más (`attempts_with_images`; `n_requirements_with_image`), un **resumen que se perdía** al
  apagar un kill-switch ajeno (`WITT_FIGURES=0` borraba del registro quién vio una imagen aportada), y varias cifras que
  decían ser otra cosa: bytes guardados servidos como bytes enviados; «filas vivas» que contaban las retiradas;
  `[MEDIDO]` impreso en estados donde nadie contó.
- La **licencia y el alcance** los decidía un `or` y se imprimían como declaración de una persona. Ahora se exigen.
- Y **siete verificaciones vacuas**: un `or True` literal; un check que comparaba el registro con la fórmula que lo
  produjo (el revisor hizo que el registro MINTIERA sobre qué lentes vieron la imagen y el gate siguió en verde); un
  rótulo que casaba siempre porque cada id empieza por `attested:` (se podía borrar entera la advertencia «esto no es
  evidencia» sin que nadie se enterara); una paridad de vocabulario que se auto-desactivaba si la biblioteca no
  importaba; un «dice en palabras» que sólo medía el largo de un JSON; un nombre que prometía una cosa y una condición
  que medía otra; y un tope flojo donde el número es exacto.

**Declarado y NO arreglado** (deuda con nombre, no silencio):

- **Los topes son read-then-act.** Subir lee el cupo y después escribe, sin transacción: con peticiones simultáneas se
  rebasan (el revisor midió 5 filas con el tope en 2). Cerrarlo bien pide una reserva atómica como la de la cuota web
  (`web_locator_usage`), que es una rebanada propia.
- **Carrera de `mkdir` en `LocalStorage`**: bajo concurrencia devuelve 503 con el disco sano. Misma rebanada.
- **Permisos planos (ADR-0047): cualquier sesión sube al plan de otra persona.** Es regla declarada de la casa, pero la
  ASIMETRÍA no lo estaba: quien sube consume el cupo del plan ajeno y su dueño no puede retirarlo
  (`withdraw-not-uploader`). Queda dicho aquí hasta que se decida si el dueño del plan hereda derecho de retiro.
- **`uploaded_at` de una imagen heredada es el original**, así que una subida de ayer heredada hoy escribe bytes hoy y no
  cuenta en el tope diario de hoy (la herencia como acto sí cuenta ya, corregido en la ola 4).
- **La proyección de tokens de visión de lo atestiguado** usa el `detail` por default en vez del que se usó al enviar, y
  no declara cuál asumió. Hoy coinciden (`high` en ambos); con `WITT_FIGURES_OPENAI_DETAIL=low` sobreestimaría.
- **`WITT_ATTESTED_EXIF=declare`** apaga el borrado de metadatos sin excepción para material de paciente, y lo que
  `strip_metadata` MIDIÓ (`exif_present`, qué había) no se persiste: el registro no puede decir si esa imagen llevaba GPS.
- **El `consent_text` de una imagen de paciente lo ve toda sesión** en el índice (los bytes no). Si la promesa es
  «material de paciente author-only SIEMPRE», hoy es cierta de los píxeles y no del texto de consentimiento.

### Lo que falta

- **F9 · integrador y tres revisores adversarios.** El integrador mide lo que ninguna prueba individual puede medir: que
  una corrida SIN imágenes aportadas sea byte a byte la de 1.13 salvo EXACTAMENTE las tres excepciones declaradas. Luego
  los revisores, el corrector, el barrido completo y el tag `contract-1.14-frozen`.
- **La paridad en la webapp** (regla de la casa: el alcance del backend tiene que estar representado en el front, sin
  limitantes, y `tools/parity_check.py` lo mide). Depende del tag.
- **Los gates EN VIVO (LG1–LG5)** los corre Emmanuel: `analysis/scripts/smoke_live_attestations.py` ya construye todo en
  seco y mide cero red; `--store minio` necesita el bucket privado dedicado y sus credenciales; `--vision` necesita su
  autorización explícita de gasto. Cada cifra de costo de este ADR es PROYECCIÓN hasta que esos gates la sustituyan por
  medición con fecha.
- **El volumen persistente en Dokploy.** Sin él el almacén privado es efímero: el servidor lo DECLARA
  (`frozen.attested_images.storage.durability`, y la puerta de bytes responde 404 `bytes-missing` en vez de mentir), pero
  declararlo no lo arregla — nadie podría volver a ver su propia imagen al día siguiente.

## Context

1. **Hoy lo atestiguado es SÓLO texto y ya tiene la disciplina que las imágenes necesitan.** `human_attestations_of(ledger)`
   (runs.py:3455) devuelve `{knowledge_now, attestations[] {requirement_id, text, by, at, class 'attested'}, n_attestations,
   class, rule}` SÓLO con `ledger.state == 'approved'` (:3459) y `None` en cualquier otro caso; viaja al sintetizador como llave
   HERMANA `payload["human_attestations"]` (:1740) — jamás dentro de `evidence` —, `synth_system(human_attestations=True)` añade
   `ATTESTATION_ANTI_LEAK_CLAUSE` (:1665-1671) SÓLO cuando viajan (sin ellas el system es byte a byte el de antes), a r2/r3 llega
   como PRIOR ART etiquetado (`payload_r1/r2` :589/:642), y el predicado DURO `attestation_identifier_leak` (:3480) hace
   `extract_identifiers(json.dumps(attestations))` (:3484): TODO lo que viaje dentro del dict `human_attestations` — captions
   incluidos — entra al conjunto de identificadores atestiguados **por construcción, sin código nuevo**. La copia al encolar es
   server-side: `compose_council_json(prow)` (:4929) copia `plans.council_ledger_json` ÍNTEGRO a `runs.council_json.ledger` (F.4);
   `_frozen_ledger_view` (:3617) recorta el texto a 600 chars y declara `truncated`. Las imágenes se apilan sobre este camino: son
   `human_attestations.images[]`, no una llave nueva junto a `evidence`.
2. **El ledger es el ÚNICO punto donde la prosa humana se vuelve gasto — y el ÚNICO donde hoy puede aportarse algo.**
   `POST /plans/{plan_id}/council/ledger` (app.py:1827) recibe `LedgerBody {decisions[] {requirement_id, decision, reason?,
   attested_text?}, knowledge_now?, approve}` (:1773-1783), lo persiste ÍNTEGRO en `plans.council_ledger_json` (db.py:131,
   `set_plan_ledger` :870 atómico contra el sello) en CADA borrador (`n_saves`), y el 409 `plan_already_used` (:1790-1800) cierra la
   puerta tras el sello. Reforzar la pregunta (turno N+1) NO es una ruta: la webapp declara un plan NUEVO con `parent_run_id`
   (`declararPlan` Preguntar.tsx:565) y aprueba SU ledger antes de `crearCorrida(pregunta, entidades, planVigente, desde)`
   (:597-604) — así que «(b) reforzar» entra por la MISMA compuerta que «(a) aprobar». Los comentarios (ADR-0077) son públicos,
   append-only, fuera del registro y viajan verbatim al hijo como `thread_context.human_comments` (runs.py:1221): una imagen ahí
   sería pública por construcción y saltaría consentimiento, lentes y sello — «(c) comentarios» queda declarado NO.
   *(Reconciliación con el brief: §7 hablaba de `run_images`, `POST /runs/{id}/images` y «entran al turno SIGUIENTE»; el §4 A
   posterior y las decisiones tomadas ponen las imágenes en «Aprobar y correr». Este ADR SUSTITUYE conscientemente la forma del
   §7 por la del §4 y actualiza la fila de la tabla de ADRs — ver (Q.3) — para que el próximo lector no vea dos verdades.)*
3. **Los bytes ya tienen molde: `figures.py` y `get_figure_bytes`.** `sniff_mime` (figures.py:620) decide `media_type` por magic
   bytes (jpeg/png/gif/webp), `image_dims` (:635) lee las dims de la CABECERA (JPEG SOF / PNG IHDR / GIF LSD / WebP VP8|VP8L|VP8X)
   sin decodificar, `MAX_MEGAPIXELS = 40` (:70) es la guardia anti-bomba, `REQUEST_B64_MB = 8` (:69) el cap b64 por petición de
   juez, y los tres builders `anthropic_blocks / openai_responses_parts / openai_chat_parts` (:1484-1520) arman `[rótulo, imagen]
   × N + texto`. `get_figure_bytes` (app.py:1558) valida `^[0-9a-f]{64}$`, busca el sha en el registro, recalcula el sha «sobre LOS
   BYTES QUE SALEN» (:1614 → 409 `figure-bytes-mismatch`, jamás se sirve) y responde con `ETag`, `Cache-Control`, `X-Witt-Figure-*`
   y `Content-Disposition: inline` (:1620-1627). `_figures_for_panel` / `_audit_accepts_figures` / `_figures_panel_kwargs`
   (runs.py:3174-3240) entregan las imágenes DENTRO del `member` de las dos lentes con `inspect.signature` tolerante:
   `composite_auditor._figures_for_member` (:1296) decide por asiento con `saw_figures.detail` cerrado y `_default_caller` (:1216-1228)
   arma los bloques por transporte. Nada de esto hay que reescribir: se APILA con `attested=` como llave distinta de `figures`.
4. **El sistema NO tiene almacenamiento privado durable — y la caché es evictable.** `mcp_cache/` es CACHÉ (ADR-0083 Context 10:
   5.6 GB efímeros sin sweeper; `.gitignore:104`; `evict_lru` figures.py:761 con `WITT_FIGURES_CACHE_MAX_MB`); el compose del
   servicio NO monta `volumes:` (medido hoy) y el README de 0083 (E4) recomienda un volumen que no existe. A diferencia de las
   figuras (re-bajables por sha de Europe PMC), **los bytes de una persona no tienen fuente**: perderlos es permanente. De aquí:
   raíz PROPIA `<repo>/attested_private` (no bajo `mcp_cache`), `.gitignore`, placeholder de volumen COMENTADO en el compose,
   `durability` declarado en cada 201 y gate en vivo ANTES de anunciar la función al laboratorio *(injerto de B/C, veredicto de
   ambos jueces contra la raíz `<mcp_cache>/attested-private` del ganador)*.
5. **MinIO ya está — cliente, red y credenciales — pero su API cambia de forma en el mayor siguiente.** `minio>=7.2` está en
   `requirements.txt:10` de este servicio (y en los otros dos), `pyproject.toml:28` pinea `7.2.20`, `raw_store._client()` (:66-71)
   ya construye `Minio(endpoint, access_key=, secret_key=, secure=)` desde `MINIO_*`, y el compose inyecta `MINIO_ENDPOINT/ACCESS_KEY/
   SECRET_KEY/SECURE` (:25-28) y une `minio_net` (:15, :225-227) para `/raw`. Verificado hoy en el venv: `minio 7.2.20`
   `put_object(bucket_name, object_name, data, length, content_type=…, metadata=None, …)` POSICIONAL con `metadata=`; la doc
   master de minio-py ya muestra `put_object(self, *, … user_metadata=…)` keyword-only *(medido por los dos jueces)*: sin tope
   mayor un `pip install` futuro rompería `raw_store.put` y el backend nuevo en silencio → pin `minio>=7.2,<8` y adaptador con la
   firma 7.2 (A; el diseño C, implementado tal cual, lanzaría `TypeError` en el primer `put` real y ningún `FakeMinio` lo
   detectaría). `docker-compose.minio.yml` PUBLICA `9100:9000` y `9101:9001` en el host (:10-12): una política de bucket pública
   convertiría lo privado en público — riesgo operativo que un gate en vivo mide (LG3). **Ni SDK nuevo ni SigV4 a mano:** ~150
   líneas de criptografía propia para un paquete ya instalado (evaluado y rechazado, injerto de C).
6. **`python-multipart` no es dependencia nueva de la CASA, sólo de este `requirements.txt`.** `rag_index/ingest_service/
   requirements.txt:4` la declara para `UploadFile/File/Form`; el venv de los gates la tiene (`python_multipart-0.0.32`); FastAPI la
   exige textualmente («To receive uploaded files, first install `python-multipart`» — fastapi.tiangolo.com/tutorial/request-files,
   verificado hoy) y `UploadFile` usa un archivo «spooled» (memoria hasta un tope, luego disco). Frente a base64-en-JSON (ganador A):
   pydantic parsea el cuerpo ENTERO en memoria (5 MB crudos → 6.7 MB b64 por imagen; A permitía 4 por petición → ~27 MB) antes de
   cualquier tope, y `uvicorn`/FastAPI no limitan el cuerpo por default (`Dockerfile:18` sin `--limit`). **Pero ningún diseño logra
   el 413 «antes de leer» como está escrito** *(juez 2)*: FastAPI resuelve `UploadFile` ANTES de que corra el handler y starlette
   1.6.0 spoolea las partes de archivo sin tope. La forma correcta es un handler que declare SÓLO `request: Request`, lea
   `Content-Length` (→ 413 sin consumir), consuma `request.stream()` con tope duro (→ 413 al rebasar, también sin
   `Content-Length`) y SÓLO entonces parsee el multipart desde el buffer acotado (`Request(scope, receive)` re-inyectado) — y
   CPU (strip, sha, escritura) fuera del event loop (`run_in_threadpool`) para no bloquear el SSE con `--workers 1` *(hueco de ambos
   jueces; ver (C))*. El proxy Next hace `await req.arrayBuffer()` (route.ts:42) en cualquiera de los dos transportes: el cuerpo se
   bufferiza también en Next — el precheck de `Content-Length` debe vivir TAMBIÉN ahí (W0).
7. **El proxy Next DESCARTA todas las cabeceras de respuesta del backend — defecto LATENTE de ADR-0083 que ningún diseño vio.**
   `route.ts` construye `salida` SÓLO con `content-type` + `cache-control: no-store` (:56-60) y hacia adentro reenvía SÓLO
   `authorization`/`content-type`/`accept` (:26-34). Consecuencia MEDIDA en lectura: `bytesDeFigura` (client.ts:405-408) lee
   `X-Witt-Figure-License/Sha256/Refetch` y `ETag` → `null` en producción (el navegador habla con `/api`, no con el servicio:
   `expose_headers` del CORS es irrelevante detrás del proxy), e `If-None-Match` nunca llega al backend (el 304 de 0083 está
   muerto). Este ADR añade al proxy una allowlist de cabeceras de RESPUESTA (`ETag`, `Content-Disposition`, `X-Witt-*`) — y lo
   declara como corrección aditiva que también repara 0083 *(hueco del juez 1)*.
8. **La compuerta de compliance es humana y el vocabulario ya existe.** `council.FLAG_KINDS` incluye `'patient-material'` (:104) y
   la bandera tiene forma LISTA `{kind, statement, gate 'human', emitted_by [a]}` (:1569; la webapp hace `emitted_by.join`,
   Preguntar.tsx:2006); CLAUDE.md §7 :149 prohíbe el filtrado automático de compliance. Por eso material de paciente NO se filtra:
   se exige consentimiento DECLARADO (`kind 'patient-consented'` + texto + desidentificación declarada), se emite la bandera con
   gate humano desde el código al SUBIR, y APROBAR exige un acuse literal (`patient_material_acknowledged: true`) — la compuerta
   hecha código, no placa *(unión de A + B + C, veredicto de ambos jueces)*.
9. **Los límites públicos del proveedor de visión, verificados HOY (platform.claude.com/docs/en/build-with-claude/vision,
   2026-09-16):** formatos `image/jpeg, image/png, image/gif, image/webp` — «Animations are unsupported, and only the first frame is
   used» · 10 MB (base64) por imagen en la API directa · 100 imágenes por request (modelos 200k) · 8000×8000 px · **más de 20
   imágenes en una request ⇒ cada una ≤ 2000 px o `invalid_request_error` «many-image requests»** · 32 MB por request · tokens
   `⌈w/28⌉×⌈h/28⌉`, tier estándar 1568 px / 1568 tokens, alta resolución 2576 px / 4784 tokens · «Claude does not parse or receive
   any metadata from images» · «Image uploads are ephemeral … Anthropic does not use uploaded images to train models» · «Claude
   cannot be used to name people in images and refuses to do so» · «not designed to interpret complex diagnostic scans such as CTs
   or MRIs». De aquí: GIF fuera por default (ambigüedad sobre qué frame vio la lente), invariante `figures.max_per_lens +
   attested_max_per_lens ≤ 20`, tope 5 MB crudos (clamp ≤ 7: 9.3 MB b64 < 10 MB), la limitación clínica en la regla literal de la
   lente y en la placa de material de paciente, y el aviso de consentimiento hacia terceros (los bytes SALEN a Anthropic y, con
   `gpt-4o`/Astra en `reproducibility`, a OpenAI con `WITT_OPENAI_STORE=0` — models.py:298).
10. **Tres estados y kill-switch byte a byte son la disciplina medida.** `FIGURES_DECLARED_EXCEPTIONS` (runs.py:3012) son
    EXACTAMENTE 3 y el smoke mide el diff de paths == ∅ contra la corrida encendida (smoke_run_pipeline.py:5000-5036); 0084 repite
    el patrón (`WEB_DECLARED_EXCEPTIONS`). `record_pdf` exige por asserts (:234-236) que toda llave del frozen tenga sección y
    contrato de nacimiento; `pdf_sections_cover` (:322) es el gate (0083 K); `parity_check.py` mide rutas ↔ `client.ts`, llaves ↔
    tipos ↔ lectores, etapas ↔ `describir()`, PDF por dos fuentes y vocabularios. Cada pieza nueva de 0086 nace con su ranura en
    esos cuatro gates.
11. **Borrado vs registro inmutable se resuelve separando IDENTIDAD de BYTES.** ADR-0074 (3): el blob congelado jamás se
    reescribe; ADR-0077: «si algún día hace falta retirar algo… un retirado tachado y legible, no un DELETE». El blob guardará sha,
    dims, caption ≤ 600, consentimiento y qué lentes la vieron — nunca bytes —; los bytes se borran del backend dejando un
    tombstone declarado (`withdrawn_by/at/reason`, 410 en la puerta). El CORS del servicio no admite `DELETE` (app.py:131) y el
    retiro no puede depender de una bandera de producto: funciona bajo kill-switch y con el plan sellado *(A; veredicto de ambos
    jueces)*.
12. **La imagen del padre en el hijo.** `build_thread_context` (runs.py:1185-1290) arma el snapshot con `previous_answer`,
    `previous_audit`, `human_comments`, `evidence_hints`, `council_summary` — **NO arrastra `human_attestations` del padre**
    (medido: ninguna llave; `summary_for_thread` :1969 devuelve requisitos/flags/`knowledge_now_present`, sin textos). Sin código
    nuevo el hijo no sabría que el padre tuvo imágenes. La fila ADR-0086 del brief pide que «aparezca en el hijo como
    image-attested»: se cumple con METADATOS (`thread_context.parent_attested_images[]`, ≤ 200 chars de caption, sin bytes,
    cubiertos por `parent_identifier_leak` que serializa el snapshot :1329-1340) y bytes SÓLO por acto humano explícito del MISMO
    uploader (`POST …/attestations/inherit`) — el consentimiento cubrió una pregunta; extenderlo al turno siguiente lo decide una
    persona con nombre en el registro *(C + juez 2; el ganador lo negaba en LG5)*.
13. **Proyección de tokens: `models.vision_tokens` es la única sede y dos diseños la aplicaron mal.** Para una foto de laboratorio
    1600×1200: tier estándar (haiku) reescala por ÁREA a 1092² → 1261×946 → 46×34 = **1 564** tokens; tier alto (opus-5/sonnet-5)
    NO reescala → 58×43 = **2 494** (el ganador decía 1 568: subestimaba ×1.6); gpt-4o tiles → 1024×768 → 4 tiles → **765**; Astra
    parches ⌈1600/32⌉×⌈1200/32⌉ = 1 900 ×1.2 = **2 280**. Foto de teléfono 4032×3024: 1 564 / 4 784 (cap) / 765 / 3 000 (cap 2 500
    ×1.2). Toda cifra de este ADR sale de esa función (Proyección).
14. **Dos ADRs en obra comparten archivos.** 0084 toca `runs.py`, `record_pdf.py`, `models.py`, `db.py`, `app.py`, compose y
    README en puntos que este ADR NO toca (ver «Formas 1.13»); el orden de aterrizaje es 0084 → 0086 (J.5 de 0083: «dos ADRs en
    obra no comparten archivo salvo por orden declarado»). Si 0084 se retrasa, 0086 aterriza como 1.13 y la rebanada de docs lo
    declara — sólo cambia un literal (Q).

## Decision

**(A) `analysis/scripts/lib/attestations.py` (NUEVO, stdlib: `hashlib, struct, io, os, json, re, time, base64, pathlib`; importa
`figures.sniff_mime / image_dims / MAX_MEGAPIXELS / MEDIA_TYPES / REQUEST_B64_MB` y hace `from minio import Minio` PEREZOSO, patrón
`raw_store._client` :66) — el módulo puro cuya INTERFAZ congela F1.** *(A.1 vocabularios CERRADOS, exportados para el gate de
paridad y congelados en `frozen.attested_images.vocabulary`)* `MODULE_VERSION 'att-1'` · `ATTESTED_CLASS 'attested (human-provided;
provenance recorded: uploader, time, consent, declared license; never evidence, never cited, never embedded)'` ·
`ATTESTED_STATES_EXACT = ('attached', 'no-attested-images', 'not-applicable (no-ledger)', 'kill-switch WITT_ATTESTED_IMAGES=0')`,
`ATTESTED_STATES_PREFIXES = ('error: ', 'tool-unavailable (')` · `STORAGE_BACKENDS = ('local', 'minio')` · `STORAGE_STATES =
('stored', 'bytes-missing', 'withdrawn (tombstone)', 'mismatch', 'backend-not-configured-now', 'storage-unavailable', 'not-probed')` ·
`DIR_STATES = ('writable', 'read-only', 'missing', 'permissions-not-applied (win32)')` · `EXIF_STATES_EXACT = ('none-found',
'declared-not-stripped', 'strip-failed')`, `EXIF_STATES_PREFIXES = ('stripped (',)` (el sufijo lista los segmentos quitados) ·
`CONSENT_KINDS = ('own-work', 'lab-internal', 'third-party-permission', 'patient-consented', 'public-domain')` · `SHARE_SCOPES =
('author-only', 'team')` · `LICENSES_DECLARED = ('private-team-only', 'cc-by', 'cc0', 'cc-by-sa', 'cc-by-nc', 'cc-by-nd',
'cc-by-nc-sa', 'cc-by-nc-nd', 'all-rights-reserved', 'other-declared')` (NO se reutiliza `figures.LICENSES`: `zfin-display-only`/
`unknown`/`cc-by-prose-unconfirmed` no tienen sentido para una foto humana — juez 2) · `LEDGER_IMAGE_STATES = ('staged',
'attached', 'withdrawn-before-approve', 'withdrawn-before-run', 'inherited')` · `SERVABLE_STATES = ('yes', 'forbidden (author-only)',
'withdrawn', 'bytes-missing', 'bytes-mismatch', 'backend-not-configured-now', 'storage-unavailable', 'kill-switch')` ·
`SAW_ATTESTED_DETAILS = ('sent', 'lens-not-in-vision-lenses', 'kill-switch WITT_ATTESTED_VISION=0', 'kill-switch
WITT_FIGURES_VISION=0', 'no-eligible-images', 'model-vision-unknown', 'api-form-not-verified')` · `ATTESTED_EVENT_TYPES =
('stage.attestations.plan', 'stage.attestations.image', 'stage.attestations.summary', 'stage.attestations.panel')` ·
`PLAN_EVENT_TYPES = ('attestation.uploaded', 'attestation.inherited', 'attestation.withdrawn', 'attestation.bytes_served')` ·
`ATTESTED_ITEM_KEYS` (forma EXACTA de `AttestedImageItem`, (L)) · `PANEL_ATTESTED_KEYS = ('id', 'sha256', 'sha256_short',
'caption', 'media_type', 'b64', 'dims', 'consent_kind', 'class')` · `PROMPT_ATTESTED_KEYS = ('id', 'sha256_short', 'caption',
'media_type', 'dims', 'requirement_id', 'attached_to', 'consent', 'patient_material', 'license_declared', 'uploaded_by',
'uploaded_at', 'class', 'bytes_delivered')` · `FORBIDDEN_ATTESTED_PROMPT_KEYS = ('b64', 'data', 'bytes_b64', 'storage_key', 'path',
'cache_path')` con `assert not set(PROMPT_ATTESTED_KEYS) & set(FORBIDDEN_ATTESTED_PROMPT_KEYS)` (molde figures.py:150-152) ·
`ATTESTED_DECLARED_EXCEPTIONS = ('render_contract_version', 'attested_images', 'deterministic_checks.attested_images')` (el literal
vive aquí y `runs` lo importa) · `ATTESTED_ID_PREFIX = 'attested:'` (id = `'attested:<sha12>'`) · `VOCABULARY = {…}` con todos.
*(A.2 `ENV_SPECS` (14) + `env_config(env=None)` tolerante, molde figures.py:188-320: vacía/basura → default con `source ∈
'env:<VAR>' | 'default-unset:<VAR>' | 'default-invalid-env:<VAR>'`; clamps declarados; ver la tabla de env.)* *(A.3
`validate_form(fields, cfg) -> (ok_fields | error {status, state, detail})`)* caption (≥ 10 y ≤ `caption_chars`), `consent_kind ∈
CONSENT_KINDS`, `consent_declared == true`, `consent_text` (≤ 600; OBLIGATORIO con `third-party-permission` y `patient-consented`,
≥ 20 chars), `third_party_processing_acknowledged == true` (el aviso literal de (C.4)), `patient_material: bool` SIN default,
`deidentified_declared: bool`, `license_declared ∈ LICENSES_DECLARED` (default `private-team-only`; NO gatea nada: la imagen jamás
se redistribuye — la compuerta es el consentimiento), `share_scope ∈ SHARE_SCOPES` (default `author-only`), `requirement_id?`,
`date_taken?` (ISO, ≤ 32), `method?` (≤ 300). Reglas de paciente: `patient_material → consent_kind == 'patient-consented' ∧
deidentified_declared ∧ consent_text ≥ 20` (si no, 400 `patient_material_without_consent` | `patient_material_not_deidentified`).
*(A.4 `validate_bytes(data, declared_ct, cfg) -> (fields | error)`)* `media_type = figures.sniff_mime(data)` (el `Content-Type`
declarado se REGISTRA como `media_type_declared`, jamás decide); `media_type ∈ cfg['allowed_media']` (default `image/jpeg,
image/png, image/webp`; `image/gif` sólo si la env lo lista; PDF/TIFF/SVG/HEIC/DICOM → 415 `unsupported-media-type {sniffed, declared,
allowed[]}`); `dims = figures.image_dims(data)` (None → 422 `undecodable-header`); `w×h ≤ figures.MAX_MEGAPIXELS` (→ 422
`image-too-many-pixels {w, h, max_mp}`); `min(w, h) ≥ 16` (→ 422 `image-too-small`); `len(data) ≤ max_image_mb` (→ 413
`attested_image_too_large {bytes, max_mb, max_mb_source}` — segunda línea de defensa tras el precheck de (C.2)). *(A.5
`strip_metadata(data, media_type, mode) -> {data, exif_state, removed[], exif_present}`)* SIN recodificar (los píxeles quedan
byte-idénticos; `image_dims` antes == después, medido): **JPEG** quita `APP1` (Exif/XMP), `APP2` salvo si empieza por
`ICC_PROFILE\0` (así cae `MPF\0` — thumbnails embebidos, privacidad), `APP3-APP13` (IPTC/IRB en APP13), `COM`; conserva `APP0`
(JFIF), `APP2 ICC`, `APP14` (Adobe, necesario para CMYK), `DQT/DHT/SOF*/DRI/SOS…EOI`; **PNG** quita `tEXt/zTXt/iTXt/eXIf/tIME`
(chunks completos; los CRC de los chunks conservados NO se tocan); **WebP** quita `EXIF`/`XMP`, corrige el tamaño RIFF (bytes
4-8) Y baja los bits de bandera correspondientes del chunk `VP8X` (juez 2); **GIF** (si la env lo habilita) quita Comment
Extension (`0x21 0xFE`) y Application Extension `XMP DataXMP`. Modo `strip` (default): walker que no puede GARANTIZAR el resultado
(segmento truncado, longitud inconsistente) → `strip-failed` y el llamador responde 422 `metadata-strip-failed {media_type, detail}`
**sin almacenar nada**; modo `declare`: se almacena tal cual con `exif_present` MEDIDO y `exif_state 'declared-not-stripped'`.
*(A.6 identidad)* `sha256 = sha256(bytes ALMACENADOS)` (post-strip: es lo que se sirve y se recalcula, patrón app.py:1614);
`sha256_received = sha256(bytes recibidos)` y `bytes_received` se registran aparte (la persona coteja su archivo original);
`sha256_short = sha256[:12]`; `id = 'attested:<sha256_short>'`. *(A.7 `Storage`)* clase base con `put(plan_id, sha256, data,
media_type) -> {key, state}`, `get(key) -> bytes | None`, `stat(key) -> {exists, bytes}`, `delete(key) -> bool`, `probe() ->
{backend, state, detail, sdk_version?}`; **`LocalStorage(root)`**: raíz `WITT_ATTESTED_DIR` (vacía → `<repo>/attested_private`,
línea NUEVA en `.gitignore`; JAMÁS bajo `mcp_cache`: caché ≠ almacenamiento — Context 4), `mkdir` `0o700` y archivos `0o600` vía
`os.open` (win32 → `dir_state 'permissions-not-applied (win32)'` declarado), layout `<plan_id>/<sha256>.<ext>`, escritura ATÓMICA
`.part` + `os.replace` (doble clic → el segundo ve el sha ya presente: 409 sin bytes a medias — injerto de B), `dir_state` medido
por sonda (patrón `figures.cache_dir_state` :710); **`MinioStorage(client_factory=None)`**: cliente perezoso con
`WITT_ATTESTED_MINIO_ACCESS_KEY/SECRET_KEY` si están (usuario DEDICADO con política acotada al bucket — recomendación operativa) y si
no `MINIO_ACCESS_KEY/SECRET_KEY` (`credentials_source` declarado), `MINIO_ENDPOINT`/`MINIO_SECURE`, bucket DEDICADO
`WITT_ATTESTED_MINIO_BUCKET` (default `witt-attested-private`, ≠ `data-inamovible-raw`: lo atestiguado NO es DATA INAMOVIBLE),
`bucket_exists/make_bucket` en `probe()` (declarado, jamás en cada put), `put_object(bucket, key, io.BytesIO(data), len(data),
content_type=media_type, metadata={"sha256": sha256})` — la firma 7.2 POSICIONAL con `metadata=` (verificada en el venv;
`requirements.txt` gana el pin `minio>=7.2,<8` y `probe()` registra `minio.__version__` en `sdk_version`), `get_object(...)` →
`.read()` + `close()`/`release_conn()`, `stat_object`, `remove_object`; **`presigned_get_object` PROHIBIDO** para este bucket (un
presign es una URL compartible = redistribución); sin `MINIO_ENDPOINT/ACCESS_KEY/SECRET_KEY` → `probe().state 'storage-unavailable
(missing env: …)'` y la subida responde 503 — **jamás cae a `local` en silencio** (A/C; veredicto de ambos jueces contra B);
**`FakeMemoryStorage`** (misma interfaz; smokes) y `set_client_factory(fn)` para inyectar un `FakeMinio`. `storage_backend(cfg) ->
(backend, probe)`: `WITT_ATTESTED_BACKEND` fuera de vocabulario → `local` con `source 'default-invalid-env:…'`. *(A.8
`serve_check(storage, row) -> {state ∈ SERVABLE_STATES, data | None, sha256_actual}`)* relee la fila viva (tombstone → `withdrawn`),
`stat`/`get` del backend DE LA FILA (`row.storage_backend`, no el de hoy → `backend-not-configured-now` si ese backend no está
configurado ahora), recalcula el sha sobre los bytes leídos (≠ → `bytes-mismatch`, jamás se sirve). *(A.9
`select_for_panel(items, storage, cfg, figures_n) -> {attested[] (PANEL_ATTESTED_KEYS con b64), n_eligible, n_delivered, n_dropped
{withdrawn, missing, mismatch, size, lens_cap, request_cap, many_image_guard}, bytes_b64_total, rule}`)* elegibles = `attached ∧
¬withdrawn ∧ storage 'stored' ∧ sha recalculado ok ∧ bytes ≤ max_image_mb` (el consentimiento ya es condición de EXISTENCIA de la
fila — A.3 —, no hay env que lo relaje); orden de subida (`uploaded_at`); tope `max_per_lens`; cap b64 por petición
`figures.REQUEST_B64_MB` COMPARTIDO con las figuras — las figuras van PRIMERO (evidencia precede a prior art) y las atestiguadas
que no caben caen a `request_cap`; invariante «many-image» `figures_n + n ≤ 20` (Context 9) → recorte declarado `many_image_guard`.
*(A.10 builders)* `attested_text_label(k, img) = 'ATTESTED IMAGE {k} — {id} (human-provided PRIOR ART, NOT evidence; consent:
{consent_kind}; uploaded by {uploaded_by} on {date}): {caption}'`; `attested_separator_text = 'HUMAN-ATTESTED IMAGES follow —
prior art provided by a person, never evidence; judge them ONLY per the attested-image rule.'`; los tres builders de `figures.py`
(`anthropic_blocks`, `openai_responses_parts`, `openai_chat_parts` :1484-1520) ganan `attested=None` ADITIVO: con `None` la salida
es BYTE A BYTE la de 1.13; con lista → `[bloques de figuras…] + [{text: separador}] + [{text: rótulo_k}, {image_k}] × N +
[{text: user_text}]` — las atestiguadas van DESPUÉS de las figuras y ANTES del texto, jamás mezcladas (namespaces distintos:
`'<PMCID>#<fig_id>'` vs `'attested:<sha12>'`). *(A.11 proyecciones sin bytes)* `public_item(row, viewer=None) -> AttestedImageItem`
(SIN `b64`/`storage_key`/ruta; `viewer_may_view` calculado en el servidor cuando hay `viewer`), `prompt_item(row) ->
PROMPT_ATTESTED_KEYS` (lo ÚNICO que ve el sintetizador y el consejo), `frozen_item(row, cap=600)` (caption recortado +
`caption_truncated`). *(A.12 `ATTESTED_READING_RULE`, literal congelado en `frozen.attested_images.vision.rule`)* «You may be shown
images labelled ATTESTED IMAGE: they were provided by a person as PRIOR ART and are NOT evidence. Use them ONLY to judge whether
the claim is consistent with what the person says they show. NEVER derive, read off or estimate numbers, counts, sizes or
statistics from an attested image; never treat one as support for any citation; never cite one. Report anything you conclude
from an attested image ONLY in `attested_readings` — it is model judgment, never a measurement; never in `caught`, `reasons` or
`correction_applied`. You are not a diagnostic tool: never interpret patient material clinically.» *(A.13
`synthetic_fixtures() -> {name: bytes}` + `fixtures/attested/MANIFEST.json`)* PNG 1×1 con `tEXt`+`tIME` (`png_text.png`), PNG
64×48 limpio, JPEG 80×60 mínimo con `APP1 'Exif\0\0'` sintético (GPS/fecha ficticios) + `APP2 'MPF\0'` + `COM`
(`jpeg_exif_mpf_com.jpg`), WebP VP8L 32×32 con chunk `EXIF` y `VP8X` (`webp_exif.webp`), GIF89a 1×1 con Comment (`gif_comment.gif`),
`%PDF-1.4` (`not_image.pdf`), PNG con IHDR 8000×8000 (64 MP > 40), PNG 8×8 (too-small), JPEG truncado tras `APP1` (strip-failed);
generados con `struct`/`zlib` por CÓDIGO en el smoke y en `gen_fixtures.py` de la webapp desde la MISMA función; el `MANIFEST.json`
(texto) declara sha256 esperado ANTES y DESPUÉS del strip y los segmentos quitados; **cero binarios nuevos en git, cero material
real** (M.5 de 0083).

**(B) DÓNDE y CUÁNDO aporta la persona: UN solo sitio, el ledger del plan; DOS fases; reforzar = mismo camino; comentarios NO;
la imagen del padre en el hijo por metadatos + acto humano.** *(B.1 un solo sitio)* Las imágenes cuelgan del ledger del consejo
(F de 0082): de un requisito con `decision 'aporto'` (`requirement_id`) o de «qué sabes ahora» (`requirement_id null`,
`attached_to 'knowledge_now'`). Es el ÚNICO punto donde la prosa humana se vuelve gasto (brief §4 A) y el único canal atestiguado
que hoy existe (Context 1-2). *(B.2 dos fases)* **Subir** (`POST /plans/{plan_id}/attestations`, (C)) crea la fila `staged` con
bytes en el backend y responde el sha; **aportar** = el ledger REFIERE `sha256` (`decisions[].images[]` con `aporto`, `images[]`
top-level junto a `knowledge_now`) y al APROBAR el servidor sella `attached_to/attached_at/attached_by` (write-once). Razón: el
ledger se re-guarda ÍNTEGRO en cada borrador (db.py:131, `n_saves`) — meter bytes/b64 en su cuerpo los llevaría al blob (ADR-0074)
y reenviaría megabytes por borrador; referir por sha es el patrón `plan_id`/`from_question_id` (ADR-0056: el cliente refiere,
jamás manda el objeto). Un 413/415/422/503 de una imagen no toca las decisiones keep/discard/aporto ya escritas (§6 aislamiento).
*(B.3 reforzar)* Turno N+1 = plan NUEVO con `parent_run_id` (Preguntar.tsx:565/:597-604) → ronda 1 → ledger → `POST /runs
{plan_id}`: las imágenes del refuerzo entran por (B.2) sin ruta ni estado nuevos; **`POST /runs` NO cambia de cuerpo** (el brief
decía «POST /runs acepta attested images»: sustituido, declarado en (Q.3)). *(B.4 comentarios: NO)* ADR-0077 los hace públicos,
append-only y fuera del registro; viajan verbatim al hijo (runs.py:1221) sin consentimiento, lentes ni sello — una imagen ahí sería
pública por construcción. No es deuda: es otra semántica (ADR-0077 Context 2). *(B.5 sin consejo no hay imágenes — y se falla
TEMPRANO)* si `plans.council_state ∉ {queued, running} ∪ COUNCIL_LEDGER_STATES` (`not-requested (…)`, `disabled (…)`, `errored
(…)`, `skipped-by-human`, `pre-adr-0082`, BD sin superficie) la subida responde 409 `attestations_require_ledger {council_state}`
(injerto de B, juez 1) — la persona no sube material que jamás viajará; con r1 `queued|running` la subida SÍ se acepta (staging;
el ledger espera). Una corrida sin `plan_id` o con ledger no aprobado → `frozen.attested_images.state 'not-applicable (no-ledger)'`,
cero imágenes al panel y al sintetizador (mismo camino que `human_attestations_of` :3459). *(B.6 la imagen del padre en el hijo)*
(i) `build_thread_context` (:1185) gana `parent_attested_images[] {id, sha256_short, caption (≤ 200, truncated), by, at,
consent_kind, patient_material, seen_by_lenses[], class 'attested'}` | `[]` (padre 1.14 sin imágenes) | AUSENTE (padre < 1.14) —
METADATOS, sin bytes; llega al planner (`plan_thread_context`) y al sintetizador del hijo dentro del snapshot con
`THREAD_ANTI_LEAK_CLAUSE`, cubierto por `parent_identifier_leak` (:1329-1340 serializa el snapshot) — se DECLARA que los captions
del padre viajan al hijo sin acto humano (molde `human_comments`, juez 1); `council_summary += n_attested_images` (conteo; el
sintetizador del hijo no lo recibe, E5 de 0082). (ii) Los BYTES del padre llegan al hijo SÓLO por acto humano del MISMO uploader:
`POST /plans/{plan_id}/attestations/inherit {sha256, from_run_id}` → el servidor exige `sesión == uploaded_by` de la fila del
padre (si no 403 `inherit-not-uploader`), que el sha esté en `frozen.attested_images.items[]` del padre con `storage.state 'stored'`
y no retirado (si no 400 `attested_image_not_inheritable {sha256, state}`), COPIA los bytes al plan hijo (sha verificado al copiar;
un plan, sus bytes — sin refcount ni clave compartida: A/B sobre C, ambos jueces), crea la fila con `inherited_from_plan_id /
inherited_from_run_id`, `ledger_state 'inherited'`, misma procedencia (consent, license, patient_material, share_scope) y `uploaded_at`
NUEVO (la hora del acto); evento `attestation.inherited`. El retiro CASCADA (H.3). La webapp «Reforzar» lista las imágenes del padre
con casilla «volver a adjuntar» → inherit → sha en escena.

**(C) Recepción: MULTIPART, UNA imagen por petición, 413 ANTES de parsear, CPU fuera del event loop, formulario OBLIGATORIO.**
*(síntesis — los jueces DIVERGEN: juez 1 → multipart (B/C); juez 2 → base64-JSON (A) «por sin dependencia nueva y client.ts sin
cambio», con el caveat de que NINGUNO logra el 413 temprano. DECISIÓN: multipart, porque (i) `python-multipart` YA es dependencia de
la casa — `ingest_service/requirements.txt:4`, venv 0.0.32, exigida por FastAPI para `UploadFile` (Context 6) —: se añade la
MISMA línea a este `requirements.txt`, no una librería nueva; (ii) memoria bajo `--workers 1`: b64-JSON obliga a pydantic a parsear
el cuerpo entero (×1.33) antes de cualquier tope; multipart con lectura por stream acotada da un 413 REAL; (iii) UNA imagen por
petición aísla la falla (§6) y da progreso por imagen; (iv) `client.ts.request()` NO se toca: el wrapper nuevo hace `fetch` con
`FormData` sin `Content-Type` manual (el browser pone el boundary), patrón `bytesDeFigura` :388. El caveat del juez 2 se resuelve
en (C.2) y se MIDE.)* *(C.1 forma)* `POST /plans/{plan_id}/attestations` `multipart/form-data` con partes `file` (los bytes; UNA
sola) y los campos de (A.3): `caption, consent_kind, consent_declared, consent_text?, third_party_processing_acknowledged,
patient_material, deidentified_declared, license_declared?, share_scope?, requirement_id?, date_taken?, method?`; el `Content-Type`
de la parte `file` se registra como `media_type_declared`. *(C.2 tope ANTES de parsear — la forma que SÍ da 413)* el handler es
`async def` y declara SÓLO `request: Request` (ningún `UploadFile` en la firma: FastAPI no parsea nada antes de entrar): (1)
`Content-Length` presente y `> max_body_bytes = max_image_mb·2^20 + FORM_OVERHEAD (64 KiB)` → 413 `attested_image_too_large
{content_length, max_bytes, max_mb, max_mb_source}` con CERO bytes leídos (medido: contador del `receive` falso == 0); (2)
`request.stream()` se consume en chunks (`figures.CHUNK_BYTES`) a un buffer ACOTADO — al rebasar el tope se responde 413 y se
deja de leer (también sin `Content-Length`: cuerpo `chunked`); (3) el buffer se re-inyecta como `receive` de un
`starlette.requests.Request(scope, receive)` y `await req.form(max_files=1, max_fields=16)` parsea el multipart (python-multipart
spoolea a disco; aquí ya está acotado); (4) validación, strip, sha y `storage.put` corren en `run_in_threadpool` (CPU fuera del
loop: los heartbeats SSE de `/runs/{id}/stream` no se bloquean — hueco de ambos jueces); (5) sólo entonces se escribe la fila. El
smoke mide (1), (2) con tope 0.001 MB y cuerpo sin `Content-Length`, y que un 503 de almacenamiento deja la tabla VACÍA. *(C.3
topes de conjunto)* `WITT_ATTESTED_MAX_PER_PLAN` (8) cuenta filas VIVAS (no retiradas — un retiro libera el cupo; A contaba las
retiradas y 8 errores bloqueaban el plan: juez 1), `WITT_ATTESTED_MAX_TOTAL_MB` (24) suma bytes vivos → 409 `attestations_cap_reached
{n | total_mb, cap, scope 'plan' | 'total_mb'}`; `WITT_ATTESTED_MAX_PER_USER_PER_DAY` (30) contado en BD por `uploaded_by ∧
uploaded_at ≥ hoy UTC` → 429 `upload-rate-limited {n_today, cap, resets_at}` (protege disco/bucket de un cliente en bucle —
injerto de C). *(C.4 el formulario es la procedencia)* los campos de (A.3) son OBLIGATORIOS y el 400 es tipado por campo
(`caption-missing | caption-too-long {max_chars} | invalid-consent-kind {allowed[]} | consent-not-declared | consent_text-required
{kind} | third_party_processing_not_acknowledged | patient_material-required | patient_material_without_consent |
patient_material_not_deidentified | invalid-license {allowed[]} | invalid-share-scope {allowed[]} | unknown_requirement_id {known[]}`);
`uploaded_by/uploaded_by_role/uploaded_at` los pone el SERVIDOR (ADR-0056; `validate_token` db.py:560 trae `role`). El aviso literal
que el formulario muestra y `third_party_processing_acknowledged` acusa: «Esta imagen NO es evidencia: el modelo que redacta recibe
SÓLO tu caption y metadatos; sus BYTES los verán a lo sumo dos lentes del panel y para ello SALEN a los proveedores de esas
lentes (Anthropic — procesamiento efímero, sin entrenamiento, según su documentación; OpenAI con `WITT_OPENAI_STORE=0`); el CAPTION
NO es privado: lo lee toda sesión del equipo, el sintetizador y los miembros del consejo; la imagen jamás sale en el PDF ni se
redistribuye; puedes retirar los bytes cuando quieras (queda constancia: sha y metadatos).» *(injerto de B + hueco de ambos
jueces)*. *(C.5 idempotencia)* mismo sha ya en el plan → 409 `attested_image_already_uploaded {sha256, uploaded_by_is_viewer}`
(UNIQUE `(plan_id, sha256)`); si lo subió OTRA persona, su consentimiento NO se registra (límite declarado, (P)). *(C.6 HEIC y
teléfonos)* el servidor RECHAZA HEIC por magic bytes (415) — correcto —; la webapp intenta re-codificar en el cliente
(`createImageBitmap` → canvas → JPEG q 0.9, lo que además quita EXIF y acota tamaño del lado del cliente) y, si el navegador no
decodifica HEIC, muestra el literal «convierte a JPEG/PNG antes de subir»; el strip del servidor sigue siendo OBLIGATORIO (hueco del
juez 1).

**(D) Validación DETERMINISTA por código y strip de metadatos — todo en (A.4)/(A.5); aquí sólo las reglas de orden y estado.**
Orden: tope de cuerpo (C.2) → formulario (A.3) → `sniff_mime` → `allowed_media` → `image_dims` → 40 MP → mínimo → tope de bytes →
`strip_metadata` → sha ×2 → cupos (C.3) → `storage.put` → fila → evento. Nada se escribe antes del último paso; un fallo en
`storage.put` (503) no deja fila. `exif_state` viaja a la fila, al índice, al frozen, a la Hoja y al PDF; `exif_removed[]` lista
los segmentos/chunks quitados (auditable). Declarado ≠ medido se REGISTRA (`media_type_declared_mismatch: bool`), no se corrige ni
se rechaza.

**(E) Almacenamiento con backend INTERCAMBIABLE, PRIVADO, fuera del blob — y lo que pasa sin volumen o sin MinIO se DECLARA.**
*(E.1)* `WITT_ATTESTED_BACKEND=local` (default de esta obra: funciona sin credenciales) | `minio` (default del plan cuando Emmanuel
confirme bucket y credenciales — OE1). Cada FILA conserva `storage_backend/storage_key/storage_state`; cambiar la env NO migra
(una GET lee del backend DE LA FILA y declara `backend-not-configured-now` si ese backend ya no está; migración = CLI declarado NO
construido, (P)). *(E.2 durabilidad declarada)* la respuesta 201 trae `durability {backend, dir_source ∈ 'env' | 'default',
dir_state, note}` con la nota literal cuando `local` y `dir_source 'default'`: «el directorio por default vive DENTRO del contenedor:
sin volumen montado los bytes se pierden en el siguiente redeploy (el registro sha/metadatos permanece); monta un volumen o fija
WITT_ATTESTED_DIR»; el compose gana el bloque `volumes:` con `attested_private:/app/attested_private` COMENTADO e instrucción (LG2
mide si está activo); la Hoja pinta la nota. *(E.3 sin fuente = sin refetch)* a diferencia de `get_figure_bytes` no hay
`REFETCH_ON_GET`: `bytes-missing` es permanente y se dice así (índice, Hoja, PDF). *(E.4 respaldo y versionado)* el README declara:
los bytes atestiguados no tienen fuente — el respaldo del volumen/bucket es del operador; **el bucket `witt-attested-private` debe
tener versioning OFF** (con versioning, `remove_object` deja un *delete marker* y los bytes sobreviven al retiro — LG3 lo verifica con
`get_bucket_versioning`); la retención de respaldos queda como LÍMITE declarado del derecho de borrado (juez 2). *(E.5 MinIO
operativo)* usuario MinIO DEDICADO con política acotada al bucket (recomendación; `WITT_ATTESTED_MINIO_ACCESS_KEY/SECRET_KEY`
opcionales, fallback a `MINIO_*` declarado); política del bucket JAMÁS pública (LG3: anónimo → 403; `9100/9101` publicados en el host
por `docker-compose.minio.yml:10-12` deben estar cerrados por firewall); credenciales SÓLO en la pestaña Environment de Dokploy
(`.secrets/deploy.env` local, jamás git/vault/memoria); en el registro viaja SÓLO su PRESENCIA (`storage.credentials_source`).

**(F) Datos: tabla NUEVA `plan_attested_images` por `create_all` (CERO `ALTER`), eventos de plan SIN tocar el latido.** *(F.1
tabla, molde `run_comments` db.py:246 / `plan_events` :148)* `image_id` PK (String 64) · `plan_id` FK `plans.plan_id` · `sha256`
(64) · `sha256_received` (64) · `bytes` · `bytes_received` · `media_type` · `media_type_declared` · `dims_w` · `dims_h` · `caption`
(Text) · `caption_chars` · `consent_kind` · `consent_declared` (Boolean) · `consent_text` (Text) · `third_party_ack` (Boolean) ·
`patient_material` (Boolean) · `deidentified_declared` (Boolean) · `license_declared` · `share_scope` · `requirement_id` (String 64
| NULL) · `date_taken` · `method` · `exif_state` · `exif_removed_json` (Text) · `storage_backend` · `storage_key` · `storage_state` ·
`uploaded_by` FK `users.user_id` · `uploaded_by_role` · `uploaded_at` `DateTime(timezone=True)` (lección ADR-0078: nunca
`DATETIME` a mano) · `attached_to` (String 96: `'requirement:<id>' | 'knowledge_now'` | NULL) · `attached_at` · `attached_by` ·
`inherited_from_plan_id` · `inherited_from_run_id` · `withdrawn_by` · `withdrawn_at` · `withdraw_reason` (Text) · `withdraw_cascade_n`
(Integer); `UNIQUE(plan_id, sha256)`; `ix_plan_attested_images_plan(plan_id)`; `ix_plan_attested_images_uploader(uploaded_by,
uploaded_at)` (rate limit). Identidad y procedencia INMUTABLES; SÓLO `attached_*` y `withdrawn_*` escriben UNA vez (`WHERE … IS
NULL`, patrón `mark_plan_used` :678). NADA binario en la BD ni columnas nuevas en `plans`/`runs`: los metadatos viajan dentro de
`plans.council_ledger_json.images[]` → `runs.council_json.ledger` por `compose_council_json` (ya copia el ledger, :4929) y los ítems
se RELEEN de la tabla al ejecutar y al servir (la fila es la verdad VIVA de los bytes; el frozen, la del momento de la corrida).
*(F.2 funciones)* `create_plan_attested_image(row)`, `list_plan_attested_images(plan_id, include_withdrawn=True)`,
`get_plan_attested_image(plan_id, sha256)`, `count_live_plan_attested_images(plan_id) -> (n, bytes)`,
`count_attested_uploads_today(user_id, now)`, `attach_plan_attested_images(plan_id, [(sha256, attached_to)], by, at) -> n`
(write-once), `withdraw_plan_attested_image(plan_id, sha256, by, reason, at) -> bool` (write-once), `attested_images_usage(frm, to,
include_origins)` para `/usage`, `attested_schema_state()` (patrón `council_schema_state` :478) → 503 `attested-db-unavailable`
declarado si la BD conectada no tiene la tabla. *(F.3 SQL medido para Postgres)* el smoke compila `CREATE TABLE` para el dialecto
`postgresql` (sin funciones exclusivas de SQLite) y ejecuta `create_all` sobre una BD SQLite PRE-POBLADA (plans/runs/users con
filas) midiendo que sólo aparece la tabla nueva y ninguna fila cambia (injerto de B; lección ADR-0078). *(F.4 eventos de plan sin
latido)* `db.plan_add_event(plan_id, type, payload, agent, tool, level, degraded, heartbeat=True)` gana el kwarg ADITIVO
`heartbeat` (default True = byte a byte hoy); los eventos `attestation.*` pasan `heartbeat=False` para NO refrescar
`plans.council_last_event_at` (:788) — un upload o un retiro sobre un plan terminal no debe mover `heartbeat_age_s` de `GET
/plans/{id}` (hueco del juez 2). Tipos (agent `attestations`): `attestation.uploaded {id, sha256_short, bytes, media_type, dims,
consent_kind, patient_material, share_scope, exif_state, storage {backend, state}, requirement_id, by}` ·
`attestation.inherited {id, from_run_id, from_plan_id, by}` · `attestation.withdrawn {id, by, reason_present, cascade_n}` ·
`attestation.bytes_served {id, viewer, http_status 200}` (SÓLO en 200: la bitácora de acceso que el laboratorio podrá pedir —
juez 2; sin bytes, sin ruta).

**(G) Autorización y puertas de BYTES: sesión SIEMPRE, sólo el autor por default, el alcance lo declara quien sube, material de
paciente SIEMPRE sólo autor; jamás presign, jamás PDF, jamás `<img src>` directo.** *(G.1 regla)* `view_rule(row, viewer, cfg) ∈
'author-only' | 'team' | 'author-only (patient-material)'`: (i) sesión válida obligatoria (401, `_user_of` app.py:137); (ii)
`patient_material == true` → SÓLO `uploaded_by == viewer`, con independencia de `share_scope` y de la env (injerto de C); (iii) si
no, `share_scope 'team'` ∧ `WITT_ATTESTED_TEAM_VIEW=1` → toda sesión; (iv) si no, `uploaded_by == viewer`; fuera → 403 `{state
'forbidden (author-only)', share_scope, uploaded_by_is_viewer false, team_view_env, rule}`. Se RECHAZA «autor = uploader ∪ autor del
plan ∪ autor de la corrida» (C): cualquier sesión aprueba ledgers (permisos planos, 0082 F.1) y ampliaría el acceso sin el
consentimiento de quien subió (juez 2). El ÍNDICE (metadatos + caption, sin bytes) lo lee toda sesión (ADR-0047) e informa
`viewer_may_view` calculado en el servidor: la Hoja pinta lo que el servidor dijo, jamás decide privacidad (doctrina
`src/lenguaje/figuras.ts` — «una miniatura se muestra SÓLO si el servidor la sirvió»). *(G.2 servir)* `GET /plans/{plan_id}/attestations/{sha256}`
(previsualización del uploader ANTES de correr) y `GET /runs/{run_id}/attestations/{sha256}` (desde el registro; molde
`get_figure_bytes` :1558): `^[0-9a-f]{64}$` (400 `bad-sha256`) → membresía (plan: fila; corrida: `frozen.attested_images.items[]`,
409 identidad `question_matches_run false` como `record.pdf`) → kill-switch (404) → `view_rule` (403) → `serve_check` (410
`withdrawn` · 404 `bytes-missing` · 503 `storage-unavailable` · 404 `backend-not-configured-now` · 409 `attested-bytes-mismatch
{expected, actual}` JAMÁS se sirve) → 200 bytes con `Content-Type` = `media_type` medido, `ETag "<sha256>"` (identidad, informativo),
**`Cache-Control: private, no-store`** (una imagen de paciente no queda en cachés intermedias; por eso NO se promete `304`/
`If-None-Match`: con `no-store` el navegador no guarda nada que revalidar — juez 2), **`X-Content-Type-Options: nosniff`** (con
`Content-Disposition: inline` un archivo políglota podría interpretarse; una línea que `get_figure_bytes` hoy no pone — F5 la añade
también ahí, aditiva y declarada; hueco del juez 1), `X-Witt-Attested-Sha256`, `X-Witt-Attested-Class: attested`,
`X-Witt-Attested-View: <rule>`, `Content-Disposition: inline; filename="attested_<sha12>.<ext>"`; evento `attestation.bytes_served`
(F.4). `ATTESTED_EXPOSE_HEADERS = ('X-Witt-Attested-Sha256', 'X-Witt-Attested-Class', 'X-Witt-Attested-View')` se SUMAN a
`expose_headers` del `CORSMiddleware` (:132) — y el PROXY Next las reenvía (O.1), porque sin eso ni éstas ni las de 0083 llegan al
navegador (Context 7). *(G.3 nunca)* sin `presigned_get_object` para este bucket; sin miniaturas en el PDF (no existe env que lo
habilite); sin `<img src="/api/…">` directo (no manda `Authorization`): la webapp baja por `fetch` con bearer → blob →
`URL.revokeObjectURL` al desmontar (patrón `bytesDeFigura`); assert en smoke: ningún b64 ni `storage_key` en `frozen_record_json`,
`bundle_json`, `plans.council_ledger_json`, `runs.council_json`, `run_events`, `plan_events` ni en los bytes del PDF.

**(H) Retiro = TOMBSTONE, jamás `DELETE`; borra los BYTES, conserva la identidad; cascada a las heredadas; vive bajo kill-switch y
con el plan sellado.** *(H.1)* `POST /plans/{plan_id}/attestations/{sha256}/withdraw {reason}` → SÓLO `uploaded_by == sesión`
(403 `withdraw-not-uploader {uploaded_by_is_viewer false}`; `WITT_ATTESTED_WITHDRAW=uploader` default | `team` opcional); `reason`
obligatoria (400 `withdraw_without_reason`); 404 si el sha no está en el plan; 409 `already-withdrawn {withdrawn_at}` la segunda
vez. Efecto: `storage.delete(key)` (local `os.unlink`; minio `remove_object`; el resultado `bytes_deleted: bool | null` y
`storage_delete_state` se DECLARAN — un backend inalcanzable deja `bytes_deleted null` y `storage_state 'withdrawn (tombstone;
delete-pending: <detail>)'`, el sweeper NO existe: se reintenta en el siguiente GET/withdraw y se declara), fila
`withdrawn_by/withdrawn_at/withdraw_reason` (write-once), `storage_state 'withdrawn (tombstone)'`, evento `attestation.withdrawn`. *(H.2
lo que NO cambia)* el `frozen_record_json` de corridas ya congeladas NO se reescribe (ADR-0074 (3): sha, dims, caption ≤ 600,
consentimiento, lentes que la vieron y sus lecturas PERMANECEN — el retiro no borra que el panel la vio; el tombstone lo declara
`note 'bytes already shown to <lenses> in run <id>; irreversible'`, injerto de C); el índice de la corrida mide `servable
'withdrawn'` al pedir; la puerta de bytes responde 410 `{state 'withdrawn', withdrawn_at, reason_present}`. Antes de aprobar →
`ledger_state 'withdrawn-before-approve'` y el ledger la rechaza (400 `attested_image_withdrawn [ids]`); entre aprobar y correr →
`withdrawn-before-run` en el ítem congelado y NO viaja al panel (contada). *(H.3 cascada)* un retiro tombstonea también toda fila
con `inherited_from_plan_id == plan_id ∧ sha256 ==` (recursivo) del MISMO uploader — una persona retira SU imagen de todos los turnos
con un solo acto — y declara `withdraw_cascade_n`. *(H.4 no se apaga)* funciona con `plans.run_id` sellado (no aplica
`plan_already_used`) y bajo `WITT_ATTESTED_IMAGES=0` (la privacidad no depende de una bandera de producto — A; ambos jueces). No
existe `DELETE` (405 medido; CORS `allow_methods GET/POST` :131 intacto). *(H.5 retención)* SIN retención automática (`TTL`/sweeper)
en 0086: contradiría el registro append-only y «ningún agente muta unilateralmente» (§7); las imágenes `staged` nunca adjuntadas
permanecen hasta withdraw y cuentan en el cupo del plan (OE6).

**(I) Material de paciente: TRES declaraciones al subir + ACUSE literal al aprobar + bandera LISTA con gate humano; NADA
automático filtra (§7 :149).** (i) `patient_material: bool` SIN default (400 `patient_material-required`); (ii) `true` exige
`consent_kind 'patient-consented'` ∧ `consent_text ≥ 20` ∧ `deidentified_declared == true` (400 tipados, A.3); (iii) al subir, el
CÓDIGO emite en el ledger (`ledger.flags[]`, forma de council.py:1569) `{kind 'patient-material', statement 'imagen
atestiguada <sha12> declarada material de paciente por <user> — requiere acuse humano al aprobar el ledger', gate 'human',
emitted_by ['attestations (human-upload)'], sha256_short, source 'human-upload', caption_omitted '<razón>'}`
**[CORREGIDO 2026-09-21 — el diseño original de este inciso decía `statement '<caption ≤ 120> — …'` y se CONTRADECÍA con (M):
la bandera viaja a `frozen.council.ledger.flags[]`, de donde el PDF del servidor la imprime VERBATIM en la sección del consejo
—1.100 líneas debajo de la sección 54, que sí suprime el caption del paciente— y `council.summary_for_thread` la copia al
`thread_context` del turno siguiente, que alimenta al planner y a la ronda 1 de los 17 miembros. O sea: el caption de una
biopsia salía en un PDF que circula fuera de la app y en prompts que van a proveedores externos. Lo encontró el revisor
adversario 1 midiendo el PDF renderizado. Una bandera es un AVISO, no un canal de contenido: identifica por sha corto y por
quién la aportó, y para leer el caption hay que pedir el ítem por su puerta, con su autorización.]** (forma LISTA: la webapp hace `emitted_by.join`, Preguntar.tsx:2006 — juez 2); (iv) APROBAR con
alguna imagen `patient_material` adjunta exige `LedgerBody.patient_material_acknowledged: true` → si no, 400
`patient_material_unacknowledged [sha256_short…]` (la compuerta §7 «direct human gate» hecha CÓDIGO, no placa — C; ambos jueces); (v)
`view_rule 'author-only (patient-material)'` siempre (G.1); (vi) `n_patient_material` viaja en frozen, `stage.attestations.summary`,
`epistemic_summary.attested_has_patient_material` y la placa §7 en Hoja/PDF lleva la limitación literal del proveedor («not
designed to interpret complex diagnostic scans») junto a `ATTESTED_READING_RULE`. La bandera del `regulatory-ethics-advisor` y la
de la subida comparten `kind` y se pintan con la MISMA placa (brief §5.1). Si el laboratorio no debe aceptar material de paciente en
Fase I, `patient_material=true` → 400 `patient_material_not_allowed` por env `WITT_ATTESTED_PATIENT_MATERIAL=0` (OE4; DEFAULT `0` por decisión del orquestador; `1` =
permitido con consentimiento).

**(J) El ledger gana imágenes por REFERENCIA; el servidor valida, sella y declara.** *(J.1 cuerpo, `app.LedgerBody` :1780
ADITIVO)* `decisions[].images?: [sha256]` (sólo con `decision 'aporto'`) · `images?: [sha256]` (adjuntas a «qué sabes ahora»;
`requirement_id null`) · `patient_material_acknowledged?: bool`. PATCH-like como `knowledge_now` (:1852): `images` NO mandado = se
conservan las vinculaciones del borrador anterior; `[]` explícito desvincula. *(J.2 validación)* cada sha ∈ `plan_attested_images`
del plan (400 `unknown_attested_image [ids]`), no retirado (400 `attested_image_withdrawn [ids]`), sin duplicados (400
`duplicated_attested_image [ids]`), `decisions[].images` sólo con `aporto` (400 `images_without_aporto [requirement_ids]`), una
imagen subida con `requirement_id X` puede vincularse a otro requisito (`requirement_id` de la subida es sugerencia; la
vinculación la fija el ledger: `attached_to` gana), `n ≤ WITT_ATTESTED_MAX_PER_PLAN` (400 `too_many_attested_images {n, cap}`),
kill-switch → 400 `attested_images_disabled`, acuse de paciente (I.iv). *(J.3 al aprobar)* `attach_plan_attested_images(...)`
sella `attached_to/attached_at/attached_by` (write-once; una 2.ª aprobación tras un borrador NO lo mueve — el ledger vuelve a
`draft` pero la adjunción registrada permanece y `attached_by_is_uploader: bool` se declara por imagen: quien aprueba puede no ser
quien subió — permisos planos — y el registro lo dice; juez 2); `flags[]` gana las filas `patient-material` de (I.iii); evento
`council.ledger` += `n_images, has_patient_material, patient_material_acknowledged`. *(J.4 respuesta)* `ledger` gana `n_images`,
`images[] AttestedImageLedgerItem {id, sha256, sha256_short, attached_to, requirement_id, caption (≤ 600, truncated), media_type,
dims {w, h}, bytes, consent {kind, declared, text_present}, patient_material, deidentified_declared, license_declared, share_scope,
exif_state, uploaded_by, uploaded_at, attached_by_is_uploader, ledger_state, class 'attested'}`, `decisions[].images[]` (mismos
ítems), `images_source ∈ 'body.images' | 'kept-from-previous-draft' | 'none'`, `has_patient_material`,
`patient_material_acknowledged`; `_frozen_ledger_view` (:3617) los copia con caption ≤ 600; `GET /plans/{id}` (`_plan_view` :1700)
gana `attested_images` (el índice de (L.HTTP.3), misma forma) para que Preguntar pinte con UNA llamada; `council.apply_ledger_decisions`
(:1605) acepta `images=` por fila y top-level para la ruta pura (rechaza imágenes en keep/discard con el mismo error).
`council_index` NO cambia: indexa SÓLO `{requirement_id, decision, gap}` (:400-408) — los captions no entran al corpus buscable por
construcción (se declara, no se añade código).

**(K) La corrida — `runs.execute_run` (:3716): qué ve el sintetizador, qué ve el consejo, qué ven las DOS lentes, qué mide el
gate, qué se congela.** *(K.1 relectura viva)* tras `stage.council.ledger` (:3882) se lee `db.list_plan_attested_images(plan_id)`
y se cruza con `c_ledger.images[]/decisions[].images[]`: ítems `attached ∧ ¬withdrawn` son los CANDIDATOS; un ítem retirado entre
aprobar y correr queda `ledger_state 'withdrawn-before-run'` (contado, no viaja); `serve_check` mide `storage.state_at_run` por ítem
(`bytes-missing`/`mismatch` → no viaja, declarado — §6: jamás tumba la corrida). Evento `stage.attestations.plan` y UN
`stage.attestations.image` por candidato (latido, patrón `stage.figures.figure`). *(K.2 sintetizador — captions, JAMÁS bytes)*
`human_attestations_of(ledger, images=None)` (:3455, firma ADITIVA) gana `images[] = [prompt_item(row) …]` (`PROMPT_ATTESTED_KEYS`:
`{id, sha256_short, caption, media_type, dims, requirement_id, attached_to, consent {kind, declared}, patient_material,
license_declared, uploaded_by, uploaded_at, class 'attested', bytes_delivered false}`), `n_images` y `rule` extendida («human-provided
images are described ONLY by their human captions; the synthesizer never receives them»); devuelve un dict también cuando SÓLO hay
imágenes (sin `aporto` ni `knowledge_now` de texto). `synth_system(pass_label, thread_context=False, human_attestations=False,
vision_findings=False, attested_images=False)` (:1671, ADITIVO) añade `ATTESTED_IMAGES_CLAUSE` («Human-provided images
(human_attestations.images) were NEVER shown to you: you know them only by their human captions; never state what an image shows,
never cite one, never use its identifier; identifiers inside captions are PRIOR ART») SÓLO cuando `n_images > 0` — sin imágenes el
system es BYTE A BYTE el de 1.13 (medido) y **`SYNTH_TOOL.description` NO se toca** (A/B; ambos jueces: evita una tanda de held-out;
si Emmanuel quiere cobertura a nivel tool será un 0086.1 con su held-out). `_default_synthesizer` (:1720) pasa `attested_images =
bool(human_attestations and human_attestations.get("n_images"))`. Assert estático: `FORBIDDEN_ATTESTED_PROMPT_KEYS ∩
llaves(user_text)` = ∅ y la b64 del fixture ∉ `user_text`. *(K.3 consejo r2/r3)* el ctx `human_attestations` (:4040/:4287) lleva la
MISMA vista; `payload_r2` (:620) no cambia de forma; `R2_PREAMBLE_ATTESTED_IMAGES` («Attested images arrive as caption + metadata
only: prior art, never evidence, never a requirement's coverage by themselves») se APPENDEA al preámbulo SÓLO cuando `n_images > 0`
(byte a byte sin ellas; injerto de B); `judge_coverage` (:1717) NO cambia: un `aporto` con imagen sigue `covered-by-attestation` por
su TEXTO — la imagen no cubre nada sola (`n_with_image` contado). *(K.4 panel — dos lentes, bloques APARTE)* `_attested_for_panel(items,
storage, cfg, figures_n)` (molde `_figures_for_panel` :3174) llama `attestations.select_for_panel`; `_audit_accepts_attested()`
(inspect.signature, molde :3201) y `_attested_panel_kwargs(...)` (molde :3212) añaden `attested=[...]` a `audit(**kw)` (:4410/:4479)
sólo si la firma lo acepta (si no, `vision.state 'tool-unavailable (composite_auditor.audit without attested= — ADR-0086)'`).
`composite_auditor.audit(..., attested=None)` (:1446, ADITIVO): `_attested_for_member(member, api, vis)` (molde `_figures_for_member`
:1296) decide por asiento con `saw_attested.detail ∈ SAW_ATTESTED_DETAILS` — MISMAS dos lentes (`VISION_LENSES`, `VISION_LENSES_MAX
= 2`; ninguna lente distinta por clase), `WITT_FIGURES_VISION=0` O `WITT_ATTESTED_VISION=0` → 0 bytes —; el `member` gana
`attested[]` (llave distinta de `figures`); `_default_caller` (:1216-1228) pasa `attested=` a los tres builders (A.10) → los bloques
atestiguados van DESPUÉS de las figuras y ANTES de `user_text`, con separador y rótulo; `system += ATTESTED_READING_RULE` SÓLO
cuando viajan (:1546 patrón); `VERDICT_TOOL.input_schema.properties += attested_readings` OPCIONAL (`{id 'attested:<sha12>', reading
≤ 400, consistent_with_caption: bool|null}`; description: «vision lenses ONLY and only for images labelled ATTESTED IMAGE: your
JUDGMENT, never a measurement; never numbers read off the image; never repeat in caught/reasons/correction_applied»);
`parse_attested_readings(raw, delivered)` (molde :457) descarta y CUENTA ids no entregados, duplicados y formas fuera de vocabulario,
mide `numerals_present`; la fila gana `saw_attested {n, sha256s[], bytes_b64_total, detail, attempts_with_images, n_dropped
{lens_cap, request_cap, many_image_guard, withdrawn, missing, mismatch, size}, tier, visual_tokens_projected, projection_class}`,
`attested_readings?[]`, `attested_readings_class 'model-judgment'`, `attested_readings_dropped`, y `citation_support_vision_informed =
saw_figures.n > 0 ∨ saw_attested.n > 0` (B/C); `audit.attested_vision {state, lenses[], n_images_by_lens{}, bytes_b64_sent_total,
readings {n_rows, n_readings, n_dropped, class}}` (también en `audit_initial`: `AUDIT_INITIAL_QUORUM_KEYS += 'attested_vision'`);
`attested_readings` JAMÁS entra a `_panel_findings` (:1008) ni a la revisión (lazo D.4 de 0083 cerrado igual);
`attested_readings_in_caught` (aviso MEDIDO: `'attested:'` o `'ATTESTED IMAGE'` en `caught/reasons`) y `attested_ids_in_figure_channel`
(lecturas atestiguadas coladas en `figure_readings` — canal cruzado, juez 2) se cuentan, no gatean. *(K.5 predicados DUROS, `_gate`
:2594 += `attested_predicates`)* `verify_output.attested_predicates(citations, attested_items, answer_text) -> (fragmento,
extra_predicates[])` (molde `figure_predicates` :821): `attested_images_not_cited` — cualquier cita cuyo `id` normalizado contenga el
sha256 completo, ≥ 12 hex consecutivos de un sha atestiguado, `sha256_short` o el prefijo `attested:` → inadmisible (`reasons +=
'hard predicate failed: attested_images_not_cited'`), `cited[] {n, id, matched_sha256_short}` congelado; un id de figura
`'<PMCID>#F1'` jamás casa (medido). `attestation_identifier_leak` cubre captions POR CONSTRUCCIÓN (:3484) y su regla gana el sufijo
`'+ image captions (ADR-0086)'` con `attestation_identifier_leak_scope 'knowledge_now + attested_text + image captions'`. Fragmento
`deterministic_checks.attested_images {state ∈ 'checked' | 'no-attested-images' | 'not-applicable (no-ledger)' | 'kill-switch
WITT_ATTESTED_IMAGES=0' | 'tool-unavailable (verify_output.attested_predicates not in tree — ADR-0086)', attested_images_not_cited
{ok, gating true, cited[], n_checked, n_citations_valid}, rules {attested_images_not_cited: <literal>}, predicates_version 'attpred-1',
decided_by 'code'}`; sin imágenes NINGÚN predicado entra a la conjunción (la admisibilidad de hoy byte a byte). Al PANEL no viaja
prosa: sólo este fragmento dentro de `deterministic_checks` (conteos). *(K.6 congelar)* `frozen["attested_images"]` junto a
`"figures"` (:4678) SIEMPRE en ≥ 1.14 (forma exacta en (L)); `frozen_council.human_attestations` (:4559) += `n_images`,
`images_delivery {synthesizer 'captions-only' | false, panel_lenses [<lens>…], council_rounds true}`; `_frozen_ledger_view` (J.4);
`epistemic_summary` (:4830) += `attested_images_state: string|null, attested_n_images: int|null, attested_has_patient_material:
bool|null` (0 medido ≠ null < 1.14 o kill-switch — B/C); `_agents_invoked` (:892) += fila `{agent 'attestations
(lib/attestations.py — human-provided images: magic bytes + sha256 + metadata strip + private storage; bytes to ≤2 vision lenses
only)', status 'invoked' | 'not-applicable', invocation_id 'attestations:<n_delivered>/<n_attached>', reason?, evidence_generated
['attached:<n>', 'lenses:<csv>', 'synthesizer:captions-only', 'never-evidence']}` (ausente bajo kill-switch); `_token_usage` (:2226)
+= `attested_images {state, n_attached, n_delivered_panel, bytes_b64_sent_total, vision {tokens_projected, usd_projected, class
'proyección'}}` y `by_stage.panel.by_model[*].attested_vision {n_images, tokens_projected, formula, tier, class}` APARTE de
`vision` (nada se suma dos veces: los `input_tokens` medidos del juez YA incluyen la imagen; `by_stage_sum_matches_by_model` intacto);
`app._AttestedUsageAccumulator` (molde `_FiguresUsageAccumulator` :2282) alimenta `/usage.attested_images`. *(K.7 costo)* por imagen
entregada a una lente `models.vision_tokens(reviewer, w, h, detail)` (:1108, ÚNICA sede; `WITT_FIGURES_OPENAI_DETAIL` reutilizado)
→ `frozen.attested_images.vision.cost_projection {per_lens [{reviewer, model, tier, n_images, tokens_projected, usd_projected}],
total_usd_projected, prices_source 'models.prices() (ADR-0081)', class 'proyección'}`; `WITT_FIGURES_COUNT_TOKENS=1` ya separa los
bloques `image` (`_anthropic_count_tokens` :871) — se reutiliza para `saw_attested.tokens_measured`. *(K.8 eventos, literales en
`db.add_event`)* `stage.attestations.plan {plan_id, n_images_in_ledger, n_attached, n_withdrawn_before_run, n_patient_material,
storage {backend, state}, lenses[], caps {…}, view_rule_default, kill_switch}` (tras `stage.council.ledger`) ·
`stage.attestations.image {id, sha256_short, media_type, dims, bytes, consent_kind, patient_material, requirement_id | 'knowledge_now',
storage_state_at_run, exif_state, heartbeat true}` × N · `stage.attestations.panel {n_images_by_lens{}, n_dropped{}, bytes_b64_sent}`
(sólo si entregó ≥ 1) · `stage.attestations.summary {state, n_attached, n_delivered_panel, n_readings, n_patient_material,
visual_tokens_projected_total, class}` (tras el panel; SIEMPRE uno, también bajo kill-switch con `{state 'kill-switch …'}`) ·
`stage.audit.judge += attested_sent: int, attested_sha256: []` · `stage.council.ledger += n_images, has_patient_material` ·
`stage.deterministic_gate += attested_images_state`. *(K.9 orden de la Traza)* `stage.council.ledger → stage.attestations.plan →
image × N → thread_context → retrieve → pass1 → … → stage.figures.* → pass2 → panel (stage.attestations.panel) →
stage.attestations.summary → …`.

**(L) Contrato ADITIVO 1.14 (`RENDER_CONTRACT_VERSION = "1.14"`, runs.py:51 + línea de historial «1.14 = ADR-0086: +attested_images,
+deterministic_checks.attested_images, +council.human_attestations.{n_images,images_delivery}, +council.ledger.{images[],
decisions[].images[], n_images, has_patient_material, patient_material_acknowledged}, +audit.panel[].{saw_attested,
attested_readings*}, +audit.attested_vision, +token_usage.attested_images, +by_model[*].attested_vision,
+thread_context.parent_attested_images[]») apilado sobre 1.13 — forma EXACTA.**
**`frozen.attested_images`** (top-level NUEVA, SIEMPRE presente en ≥ 1.14) = `{state ∈ ATTESTED_STATES_EXACT | prefijos 'error: ' |
'tool-unavailable (', module_version 'att-1', class ATTESTED_CLASS, plan_id, n_items (filas del plan referidas por el ledger),
n_attached, n_withdrawn_before_run, n_inherited, n_patient_material, n_eligible_panel, n_delivered_panel, n_readings, consent_kinds_count
{<kind>: n}, storage {backend ∈ STORAGE_BACKENDS, backend_source, state (probe al congelar), dir_source ∈ 'env' | 'default' | null,
dir_state ∈ DIR_STATES | null, bucket: string | null, credentials_source: string | null, sdk_version: string | null}, caps
{max_image_mb, max_per_plan, max_total_mb, max_per_lens, request_b64_mb, caption_chars, allowed_media[], many_image_limit 20 — cada
uno {value, source}}, exif_mode {value ∈ 'strip' | 'declare', source}, view_rule_default {value ∈ 'author-only' | 'team', source},
items [AttestedImageFrozen], delivery {synthesizer 'captions-only (human_attestations.images[])', bytes_to_synthesizer false,
council_rounds 'captions-only', panel 'bytes to <= 2 vision lenses', pdf 'never'}, vision {state ∈ 'sent' | 'no-eligible-images' |
'kill-switch WITT_ATTESTED_VISION=0' | 'kill-switch WITT_FIGURES_VISION=0' | prefijos 'tool-unavailable (' | 'error: ', lenses[],
lenses_source, rule (ATTESTED_READING_RULE verbatim), openai_detail, max_per_lens, sent {n_panels, n_attempts_with_images,
bytes_b64_sent_total, visual_tokens_projected_total, tokens_state}, panels [{state, n_images, sha256s[], delivered}],
cost_projection {per_lens[], total_usd_projected, prices_source, formula_source, class 'proyección'}, readings {n_rows, n_readings,
n_dropped, n_in_caught, n_in_figure_channel, class 'model-judgment'}}, flags [{kind 'patient-material', statement, gate 'human',
emitted_by ['attestations (human-upload)'], sha256_short, source 'human-upload'}], kill_switch? {WITT_ATTESTED_IMAGES: '0',
declared_exceptions [3]}, vocabulary {ATTESTED_STATES_EXACT, ATTESTED_STATES_PREFIXES, STORAGE_BACKENDS, STORAGE_STATES, DIR_STATES,
EXIF_STATES_EXACT, EXIF_STATES_PREFIXES, CONSENT_KINDS, SHARE_SCOPES, LICENSES_DECLARED, LEDGER_IMAGE_STATES, SERVABLE_STATES,
SAW_ATTESTED_DETAILS}, rule 'human-provided images are ATTESTED prior art: never evidence, never cited, never embedded, never
redistributed; bytes only to <= 2 vision lenses (judgment); synthesizer and council see captions only'}`; bajo kill-switch la forma
BASE con conteos 0, `items []`, `storage null`, sin `vision`, + `state` + `kill_switch` (excepción declarada, M.1 de 0083).
**`AttestedImageFrozen`** = `{id 'attested:<sha12>', sha256, sha256_short (12), sha256_received, bytes, bytes_received, media_type,
media_type_declared: string|null, media_type_declared_mismatch: bool|null, dims {w, h}, dims_source 'header', caption (≤ 600),
caption_truncated, caption_chars, requirement_id: string|null, attached_to ∈ 'requirement:<id>' | 'knowledge_now' | null,
attached_by, attached_by_is_uploader: bool|null, date_taken: string|null, method: string|null, consent {kind ∈ CONSENT_KINDS, declared
true, text (≤ 300, truncated), text_present}, third_party_ack true, patient_material, deidentified_declared, license_declared ∈
LICENSES_DECLARED, share_scope ∈ SHARE_SCOPES, exif_state, exif_removed[], uploaded_by, uploaded_by_role, uploaded_at, plan_id,
ledger_state ∈ LEDGER_IMAGE_STATES, inherited_from {plan_id, run_id} | null, storage {backend, key_present true, state_at_run ∈
STORAGE_STATES}, withdrawn {at, by_present, reason_present, note} | null, seen_by_lenses [<lens>…], n_readings, delivered_to_synthesizer
'captions-only', class 'attested'}` — SIN `b64`, SIN `storage_key`, SIN ruta. **`AttestedImageItem`** (índices HTTP) = el mismo
objeto + `viewer_may_view: bool` + `view_rule` + `servable {state ∈ SERVABLE_STATES, reason?}` MEDIDO al pedir + `url` +
`withdraw_url?` (sólo al uploader) + `storage.state` VIVO.
**`human_attestations`** (llave hermana al sintetizador y ctx r2/r3) += `images [PROMPT_ATTESTED_KEYS…]`, `n_images`, `rule`
extendida; `synth_system(..., attested_images=True)` añade `ATTESTED_IMAGES_CLAUSE` SÓLO con `n_images > 0`.
**`deterministic_checks.attested_images`** (K.5) + `deterministic_checks.reasons[] += 'hard predicate failed:
attested_images_not_cited'` + `attestation_identifier_leak_scope` (aditiva; ausente bajo kill-switch).
**`frozen.council.ledger`** += `images[] AttestedImageLedgerItem`, `decisions[].images[]`, `n_images`, `images_source`,
`has_patient_material`, `patient_material_acknowledged: bool|null`; **`frozen.council.human_attestations`** += `n_images`,
`images_delivery`. **`audit.panel[]`** += `saw_attested`, `attested_readings?`, `attested_readings_class?`,
`attested_readings_dropped?`; **`audit.attested_vision`** (también `audit_initial`); `citation_support_vision_informed` ampliado;
**`VERDICT_TOOL.attested_readings`** opcional. **`token_usage.attested_images`**, **`by_stage.panel.by_model[*].attested_vision`**;
**`/usage.attested_images {state ∈ 'measured' | 'not-measured', n_runs_with_attested, n_images_attached, n_patient_material,
bytes_stored_now: int|null, vision_tokens_projected_by_model {}, usd_projected, class, rule}`**. **`epistemic_summary`** +=
`attested_images_state`, `attested_n_images`, `attested_has_patient_material`. **`thread_context.parent_attested_images[]`** (B.6).
**`agents_invoked`** fila `attestations` (K.6). **Eventos** (K.8) + `plan_events` (F.4).
**HTTP (7 rutas NUEVAS, declaradas junto a `/plans/{plan_id}/council/ledger` :1827 y a `/runs/{run_id}/figures` :1495; `inherit`
ANTES de `{sha256}`; sin solapes con `/events` :1632/:1744):** (1) `POST /plans/{plan_id}/attestations` (multipart, C) → 201
`{plan_id, item AttestedImageItem, n_live, caps, durability, storage {backend, state}, class 'attested'}`; 401 · 404 `plan_not_found` ·
409 `plan_already_used {run_id}` · 409 `attestations_require_ledger {council_state}` · 409 `attested_images_disabled` (kill-switch) ·
409 `attested_image_already_uploaded {sha256, uploaded_by_is_viewer}` · 409 `attestations_cap_reached {…}` · 400 (C.4) · 413
`attested_image_too_large {…}` · 415 `unsupported-media-type {sniffed, declared, allowed[]}` · 422 `undecodable-header |
image-too-many-pixels {w, h, max_mp} | image-too-small | metadata-strip-failed {media_type, detail}` · 429 `upload-rate-limited {…}`
· 503 `attested-storage-unavailable {backend, state, detail}` (nada escrito) · 503 `attested-db-unavailable`. (2) `POST
/plans/{plan_id}/attestations/inherit {sha256, from_run_id}` → 201 (mismo sobre, `item.ledger_state 'inherited'`); 400
`attested_image_not_inheritable {sha256, state}` · 403 `inherit-not-uploader` · 404 `from_run_id` sin registro · 409 los de (1). (3)
`GET /plans/{plan_id}/attestations` → 200 `{plan_id, n, n_live, items [AttestedImageItem], caps, storage {backend, state}, view_rule_default,
kill_switch, class, servable_rule, vocabulary}` (toda sesión; metadatos, sin bytes). (4) `GET /plans/{plan_id}/attestations/{sha256}`
→ bytes (G.2; misma política que (7)). (5) `POST /plans/{plan_id}/attestations/{sha256}/withdraw {reason}` → 200 `{plan_id, sha256,
state 'withdrawn (tombstone)', withdrawn_at, bytes_deleted: bool|null, storage_delete_state, cascade_n}`; 400 `bad-sha256 |
withdraw_without_reason` · 403 `withdraw-not-uploader` · 404 · 409 `already-withdrawn {withdrawn_at}`; funciona con plan sellado y
bajo kill-switch; `DELETE` → 405. (6) `GET /runs/{run_id}/attestations` → 401 · 404 corrida · 409 `{state, note 'no frozen record
yet'}` · 409 identidad · 200 `{run_id, run_no, render_contract_version, state, n_items, n_attached, n_withdrawn_now, n_patient_material,
items [AttestedImageItem + servable medido + url], storage {backend, state}, kill_switch, class, servable_rule, vocabulary}`;
registro < 1.14 → `{state 'not-instrumented (contrato < 1.14)', items []}`; con backend `minio` el índice mide `servable` por
`stat_object` (`sha_verified_on_index false`) y recalcula el sha SÓLO al servir (si no, cada GET del índice descargaría todos los
objetos — juez 2). (7) `GET /runs/{run_id}/attestations/{sha256}` → (G.2). **`POST /plans/{plan_id}/council/ledger`** (J). **`POST
/runs`** sin cambio. **`GET /plans/{plan_id}`** += `attested_images` (J.4). **CORS** `expose_headers += ATTESTED_EXPOSE_HEADERS`.
**`record_pdf`** (M). **`models.ENV_TABLE`** += 14 filas `adr '0086'`; `SNAPSHOT_FIELDS += ('attested.enabled', 'attested.backend',
'attested.vision', 'attested.team_view')` FUERA de `panel_signature` (patrón 0083 O.5); `MINIO_*`, `WITT_ATTESTED_MINIO_*_KEY` y
`WITT_ATTESTED_DIR` FUERA de `ENV_TABLE` (secretos/rutas: sólo su PRESENCIA viaja). **`db`** (F). **Vocabularios cerrados** (A.1)
viajan en `frozen.attested_images.vocabulary` y los lee `parity_check`. **Históricos: NADA se recalcula ni se backfillea** —
registros < 1.14 no ganan `attested_images`; webapp y PDF los leen 'NO INSTRUMENTADO (contrato < 1.14)'; etiqueta
`contract-1.14-frozen` tras el integrador; `gen_fixtures.py CONTRATO = "1.14"`.

**(M) PDF: sección 54 `imagenes-aportadas`, TRES estados, SIN miniaturas JAMÁS, sin ruta de bytes.** `KEY_BORN['attested_images'] =
'1.14'` (record_pdf.py:119); `SECCIONES += ('attested_images', 'imagenes-aportadas')` (53 → 54; asserts :234-236 intactos);
`ORDEN_SECCIONES += ('imagenes-aportadas', 'IMAGENES APORTADAS POR PERSONAS (ADR-0086) - ATESTIGUADO, jamas evidencia ni cita; los
bytes son PRIVADOS: este PDF no los embebe ni los enlaza')` tras `consejo` y antes de `consumo`; `_section_imagenes_aportadas` (molde
`_section_figuras` :1224 SIN `_thumb`) por `_tres_estados` (:309): ausente → 'NO INSTRUMENTADO (contrato < 1.14)'; `null` + state →
'null declarado — razón'; valor → cabecera (`state` · n_items/n_attached/n_withdrawn_before_run/n_patient_material · backend/state al
congelar · view_rule_default · lentes que vieron · `kill_switch.declared_exceptions`) + UNA línea por ítem: `attested:<sha12> ·
<media_type> · <w>×<h> · <bytes> · aportada por <user> (<rol>) <fecha> · adjunta a <requisito | que-sabes-ahora> · consentimiento
<kind> (declarado SI/NO; texto SI/NO) · material de paciente SI/NO (desidentificado SI/NO; acuse al aprobar SI/NO) · licencia
declarada <id> · alcance <scope> · EXIF <state> · almacenamiento <backend/state_at_run> · vista por lentes <a,b | ninguna>: JUICIO ·
retirada <SI (fecha) | NO>` + caption ≤ 200 verbatim + la línea fija «MINIATURA: NO SE IMPRIME (privado por diseno); estado de hoy
no consultado» + la regla; `_section_gate` (:1434) imprime `dc.attested_images` con el patrón de `figures` (:1481) y `conocidas`
(:1495) gana `'attested_images'` y `'attestation_identifier_leak_scope'`; `pdf_sections_cover(frozen 1.14 real) == {missing [], extra
[]}`; el smoke asserta `b64 ∉ pdf`, ningún sha de 64 completo de `storage_key`, 0 `/Subtype /Image` nuevos respecto al mismo
registro sin atestiguadas, ≤ 3 KB por ítem.

**(N) Kill-switch byte a byte (M.1 de la casa) e invariantes operativos.** *(N.1 `WITT_ATTESTED_IMAGES=0`, default `1`)*
subida e inherit → 409 `attested_images_disabled`; ledger con `images[]` no vacío → 400 `attested_images_disabled`; corrida: cero
imágenes al panel y al sintetizador aunque el ledger aprobado las tenga (`human_attestations` SIN llave `images`: byte a byte 1.13),
`user_text` de pass1/pass2 byte-idéntico, `audit()` sin `attested=`, ninguna fila gana `saw_attested`, `by_model[*]` sin
`attested_vision`, `agents_invoked` sin fila, UN `stage.attestations.summary {state 'kill-switch …'}` y 0 `stage.attestations.image`,
GET índices conservan los ítems congelados (medición) con `servable 'kill-switch'`, GET bytes 404 `{state 'kill-switch
WITT_ATTESTED_IMAGES=0'}`, **withdraw SIGUE vivo**; **el frozen es igual al 1.13 del MISMO fixture (json sort_keys, keyset Y valores)
salvo EXACTAMENTE `ATTESTED_DECLARED_EXCEPTIONS`** — el smoke mide diff de paths == ∅ tras restar las aditivas 1.14 e identidad de
corrida (smoke_run_pipeline.py:5000-5036 como molde). *(N.2 `WITT_ATTESTED_VISION=0`)* captions al sintetizador y al consejo
siguen; ninguna lente recibe bytes (`saw_attested.detail 'kill-switch WITT_ATTESTED_VISION=0'`); `WITT_FIGURES_VISION=0` apaga
TAMBIÉN los bytes atestiguados (la lente no tiene visión) con su propio literal. *(N.3 §6 no-hang)* un backend inalcanzable al
ejecutar → ítems `storage-unavailable`, corrida sigue sin imágenes, declarado; un retiro durante `running` → `select_for_panel`
relee la fila justo antes de leer y un archivo ya borrado cae a `missing` contado; la subida jamás bloquea el loop (C.2). *(N.4
toda env en la llamada, toda env = reinicio)* `attestations.env_config()` tolerante; placeholders al compose (bloque ADR-0086 tras
el bloque 0084) y `models.ENV_TABLE` (el check env ⊆ compose ∩ README de `smoke_models` las cubre). *(N.5 smokes 100 % offline y
portables)* `urlopen` bloqueado y contado = 0; `mcp_cache` byte-idéntico; `WITT_ATTESTED_DIR` = `mkdtemp` por smoke (jamás la raíz
real); `FakeMemoryStorage`/`FakeMinio` inyectados; fixtures sintéticos por código (A.13); assert GLOBAL anti-binario sobre TODA la
BD del gate ampliado a las b64 de los fixtures. *(N.6 límites del proveedor como invariantes de configuración)* `MAX_IMAGE_MB ≤ 7`
(clamp), `figures.max_per_lens + attested_max_per_lens ≤ 20` (recorte declarado), b64 por petición ≤ 8 MB compartido.

**(O) El proxy Next y la webapp (OTRO workflow, contra `contract-1.14-frozen`; aquí la ranura).** *(O.1 `route.ts` — corrige
también 0083)* hacia afuera reenvía la allowlist `content-type, cache-control (no-store del proxy gana), etag, content-disposition,
x-witt-*` (:56-60); hacia adentro añade `if-none-match` (para 0083) e `x-requested-with` NO; precheck `content-length > WITT_PROXY_MAX_BODY_MB
(6 MB default) → 413 {detail: {state 'attested_image_too_large', max_mb, source 'proxy'}}` ANTES de `req.arrayBuffer()` (:42) —
el mismo `state` que el backend para que la UI glose igual; vitest del proxy (headers reenviados; 413). *(O.2 `client.ts`)*
`subirImagenAtestiguada(planId, FormData) → 201 | {status ∈ 400|401|403|404|409|413|415|422|429|503, detail}` (fetch con bearer, SIN
`Content-Type` manual), `heredarImagenAtestiguada(planId, sha256, fromRunId)`, `imagenesAtestiguadasDePlan(planId)`,
`bytesDeImagenAtestiguadaDePlan(planId, sha)`, `retirarImagenAtestiguada(planId, sha, reason)`, `imagenesAtestiguadasDeCorrida(runId)`,
`bytesDeImagenAtestiguada(runId, sha)` (molde `bytesDeFigura` :388: `200 blob` · `400|401|403|404|409|410|503` tipados por
`detail.state`; revoke al desmontar), `urlDeImagenAtestiguada`; `aprobarLedger` sin cambio de firma (el body crece). *(O.3
Preguntar)* ver Consequences (3)-(4). *(O.4 Hoja/Traza/Lista/M8)* ver Consequences (5)-(12).

**(P) Lo que NO se hace y por qué NO es deuda** — sección propia al final.

**(Q) Costura con ADR-0084 (1.13), orden de aterrizaje y reconciliación con el brief.** *(Q.1)* Todas las rebanadas arrancan sobre
`contract-1.13-frozen` cuando exista; si 0084 se retrasa, arrancan sobre `contract-1.12-frozen` @ 7d9ce15 y la rebanada de docs
declara «1.14 apilado directamente sobre 1.12 — 0084 aterrizará después como 1.15» (sólo cambian `RENDER_CONTRACT_VERSION`,
`KEY_BORN`, la fila de `SECCIONES` y la línea de historial: una línea cada uno). *(Q.2 puntos de contacto DISJUNTOS)* `runs.py`:
0084 toca `_gate` (web_predicates), `frozen['web_locator']`, `stage.web.locate`, `_token_usage.web_locator`; 0086 toca
`human_attestations_of`, `synth_system`, `_gate` (attested_predicates — MISMA función, línea distinta: el integrador cose ambas
conjunciones en orden `leak → att → pc → fig → web → attested`), `frozen['attested_images']`, `stage.attestations.*`,
`_token_usage.attested_images`, `build_thread_context`. `record_pdf.py`: 0084 fila 53, 0086 fila 54 (ambas aditivas al final).
`models.py`: filas `adr '0084'` vs `'0086'`; `SNAPSHOT_FIELDS` +2 vs +4. `db.py`: `web_locator_usage` vs `plan_attested_images`.
`app.py`: 0084 CERO rutas; 0086 siete. compose/README: bloques consecutivos. *(Q.3 reconciliación con el brief)* la forma del §7
(`run_images`, `POST /runs/{id}/images`, «entran al turno SIGUIENTE», `409 image_already_used`) queda SUSTITUIDA por la del §4 A y
las decisiones tomadas: tabla `plan_attested_images`, `POST /plans/{id}/attestations` + referencia por sha en el ledger, «entran en
ESTE turno al aprobar; al siguiente por metadatos y por acto humano (inherit)», `409 attested_image_already_uploaded`; la fila
ADR-0086 de `docs/decisions/README.md` y el README del servicio lo dicen con esta redacción, y el gate de la fila del brief («tope,
mime, sha verificado, autor derivado, sin DELETE; la imagen del padre aparece en el hijo como image-attested») se cumple punto por
punto en `smoke_attestations_http` + `smoke_thread_context`. *(Q.4 CLAUDE.md §7)* viñeta NUEVA junto a la de figure-only (:156):
«**Human-provided images are ATTESTED prior art, never evidence (ADR-0086).** Their provenance (uploader, time, consent, declared
license) is recorded by code; their bytes live in private storage outside the frozen record, are seen by at most two panel lenses as
judgment (`attested_readings`, never in `caught`/`reasons`), never reach the synthesizer, are never cited, embedded or redistributed,
and can be withdrawn by their uploader (tombstone). Patient material requires declared consent, declared de-identification and an
explicit human acknowledgement at approval; nothing filters it automatically.»

## Consequences

- **Contrato: `render_contract_version` sube a "1.14"** — todo aditivo (lista en (L)). Ningún enum existente cambia de dominio
  (`citations[].kind` NO gana literal: una imagen atestiguada jamás es cita); `FALLBACK_TRIGGERS` intacto; `SOURCE_STATES` intacto.
  Históricos sin backfill.
- **La webapp debe tipar y pintar** (`witt-webapp/src/api/types.ts`, todo `?`; tres estados en lo nuevo; OTRO workflow contra
  `contract-1.14-frozen`): **(1) tipos:** `AttestedImagesBlock` (forma EXACTA de (L)), `AttestedImageFrozen`, `AttestedImageItem`
  (+ `viewer_may_view`, `view_rule`, `servable {state, reason?}`, `url`, `withdraw_url?`), `AttestedImageLedgerItem`,
  `DeterministicChecksAttested`, unions CERRADOS sin escape `(string & {})` en los exactos: `AttestedState` (exactos + prefijos
  `error: ` · `tool-unavailable (`), `AttestedStorageBackend`, `AttestedStorageState`, `AttestedDirState`, `AttestedExifState`
  (exactos + prefijo `stripped (`), `ConsentKind`, `ShareScope`, `LicenseDeclared`, `LedgerImageState`, `AttestedServableState`,
  `SawAttestedDetail`; `RegistroCongelado.attested_images?`; `DeterministicChecks.attested_images?` y `attestation_identifier_leak_scope?`;
  `CouncilLedgerFrozen.images?[] / decisions[].images?[] / n_images? / images_source? / has_patient_material? /
  patient_material_acknowledged?`; `CouncilHumanAttestationsBlock.n_images? / images_delivery?` (:5026);
  `PanelRow.saw_attested? / attested_readings? / attested_readings_class? / attested_readings_dropped?` (:975);
  `AuditBlock.attested_vision?` (también `audit_initial`); `TokenUsage.attested_images?` y `ByStagePanelByModel[reviewer].attested_vision?`;
  `UsageReport.attested_images?`; `EpistemicSummary.attested_images_state? / attested_n_images? / attested_has_patient_material?`;
  `ThreadContextSnapshot.parent_attested_images?[]` y `council_summary.n_attested_images?`; `LedgerDecisionRequest.images?: string[]`
  (:5840), `LedgerRequest.images?: string[]`, `LedgerRequest.patient_material_acknowledged?: boolean` (:5851); `PlanView.attested_images?`
  (:5558); `AttestedUploadResponse`, `AttestedIndex` (plan y corrida), `AttestedWithdrawResponse`, `AttestedBytesResultado` (`200 blob` |
  `400|401|403|404|409|410|503` con `detail.state` tipado), los `detail.state` de las 7 rutas (400/403/404/409/410/413/415/422/429/503);
  payloads `StageAttestationsPlan | Image | Panel | Summary`; `StageAuditJudge += attested_sent?, attested_sha256?`;
  `StageCouncilLedgerPayload += n_images?, has_patient_material?`; `DeterministicGateEventPayload.attested_images_state?`; `PlanEvent`
  tipos `attestation.uploaded | inherited | withdrawn | bytes_served`; `CouncilFlag.sha256_short?` y `source?`. **(2) `client.ts`** (O.2)
  — y `route.ts` (O.1) ANTES que nada: sin la allowlist de cabeceras la Hoja no lee `X-Witt-Attested-*` ni `X-Witt-Figure-*`. **(3)
  Preguntar (M3), la compuerta humana** (`LedgerConsejo` :1785): en la fila `aporto` de cada requisito (`FilaRequisito` :2183, bajo el
  textarea del fieldset :2362) y junto a «¿Qué sabes ahora?» (:2047) un control «Adjuntar imagen (atestiguada)» → formulario
  OBLIGATORIO antes de subir: caption («qué es, fecha, método»), consentimiento (`kind` + «declaro»), texto de consentimiento
  (obligatorio con terceros/paciente), «¿material de paciente?» SÍ/NO sin default (+ «desidentificada»), licencia declarada, alcance
  (sólo yo | equipo), la casilla del aviso literal de (C.4) (`third_party_processing_acknowledged`); `input type=file` → re-codificado
  cliente cuando aplica (C.6) → `FormData` → POST → fila `attested:<sha12> · WxH · KB · EXIF <estado> · en escena`; errores por
  literal + glosa (413 con `max_mb`; 415 con `sniffed/allowed`; 422; 429 con `resets_at`; 503 «nada se guardó»); lista de imágenes del
  plan (índice del `PlanView`) con estado, `durability.note` visible, vista previa por blob SÓLO si `viewer_may_view` y el GET dio 200,
  botón «Retirar (borra los bytes, deja constancia)» con razón obligatoria sólo para el uploader; `cuerpo()` (:1842) manda
  `decisions[].images[]` (sólo `aporto`) e `images[]` top-level (PATCH-like) y `patient_material_acknowledged` cuando hay material de
  paciente adjunto — sin el acuse el botón Aprobar se deshabilita y el 400 del servidor se glosa igual; contador `n_live /
  WITT_ATTESTED_MAX_PER_PLAN` desde `caps`; BANDERAS (:1998) pinta las filas `source 'human-upload'` con la misma placa §7; al
  Reforzar (`desde`), la MISMA card lista `parent_attested_images` del padre con casilla «volver a adjuntar» → inherit; solo lectura
  tras aprobar. **(4) `leerErrorLedger` (:1734)** gana los 400 nuevos (`unknown_attested_image`, `attested_image_withdrawn`,
  `images_without_aporto`, `too_many_attested_images`, `patient_material_unacknowledged`, `attested_images_disabled`). **(5) Hoja (M4)
  Entrada NUEVA `clave="imagenes-aportadas"` numero «2d»** tras `figuras` (:669-676), hora de `stage.attestations.*`: ausente → 'NO
  INSTRUMENTADO (contrato < 1.14)'; `state ≠ 'attached'` → literal por vocabulario en palabras ('sin imágenes aportadas', 'sin ledger',
  'kill-switch'); valor → cabecera (`n_attached / n_withdrawn_before_run / n_patient_material / n_delivered_panel` [M]; backend/state al
  congelar; `view_rule_default`; `exif_mode`; `kill_switch.declared_exceptions`) + tabla `hoja-atestiguadas-tabla` UNA FILA por ítem
  (`data-attested-id`): miniatura SÓLO si el servidor la sirvió (200; 403 → «privada: sólo su autor la ve» · 404 → «bytes no disponibles
  (permanente: sin fuente)» · 409 → «BYTES NO CUADRAN — no se muestra» · 410 → «RETIRADA por su autor el <at>; sha y metadatos
  permanecen» · 503 → «almacenamiento no disponible») · `BloqueAtestiguado` (:7793) con caption/autor/hora · consentimiento en
  palabras + texto presente · placa §7 ámbar «material de paciente — consentimiento declarado; acuse al aprobar por <approved_by>» +
  la limitación clínica literal · licencia declarada · alcance · `exif_state` + `exif_removed[]` · almacenamiento (backend/state al
  congelar y estado VIVO del índice) · «vista por <lentes>: JUICIO — el sintetizador recibió caption + metadatos, NO la imagen»
  desde `seen_by_lenses`/`delivery.bytes_to_synthesizer false` (del servidor, sin inferir) · `ledger_state` · botón Retirar (uploader)
  + bloque VISIÓN (lentes, `rule` verbatim, `sent` [M], `cost_projection` [E]) + `durability` nota cuando `local/default`. **(6) Hoja
  `ConsejoLedger` (:7854):** cada `aporto` lista sus imágenes (sha12 + caption) SEPARADAS del texto atestiguado; «qué sabes ahora»
  (:7954) lista las suyas; `human_attestations` (:8030) dice «viajaron al sintetizador: N textos + M captions (sin bytes)». **(7) Hoja
  `GateDeterminista` (:5581):** fila `attested_images_not_cited` (ok / INADMISIBLE con `cited[]` en rojo / no aplica) y
  `CompuertasDelConsejo` (:2125) imprime `attestation_identifier_leak_scope` junto a la regla. **(8) `Visuales.PanelJueces` (:499,
  bloque :584):** por juez «vio N imágenes aportadas (attested:…) · ~T tokens de visión [E]» o el `detail` glosado; `attested_readings[]`
  con la placa fija «JUICIO DEL JUEZ SOBRE UNA IMAGEN APORTADA — atestiguado, no evidencia, no medición; jamás entra al gate ni a la
  escalera»; `attested_readings_dropped`. **(9) Hoja Consumo (:7241):** `attested_vision` por reviewer y `token_usage.attested_images`
  como bloque APARTE [E]. **(10) Traza `describir()` (:899):** casos EXACTOS `stage.attestations.plan` («imágenes aportadas: N adjuntas
  · K retiradas antes de correr · P material de paciente · backend <x> (<state>) · lentes …»), `stage.attestations.image` (latido:
  «attested:<sha12> · <mime> · <w>×<h> · <consentimiento> · exif <state> · <storage_state_at_run>»), `stage.attestations.panel`,
  `stage.attestations.summary` (kill-switch en voz alerta); `stage.audit.judge` (:1164) «+ N imágenes aportadas»; `stage.council.ledger`
  (:1783) «N imágenes aportadas · material de paciente acusado SÍ/NO»; Traza del PLAN: `attestation.uploaded | inherited | withdrawn |
  bytes_served` con caso. **(11) Lista/Banco (`ListaCorridas` :494-528):** chip «N imágenes aportadas» desde `epistemic_summary`
  (null → nada; 0 → «0 (medido)») + placa ámbar si `attested_has_patient_material`. **(12) M8 Consumo:** bloque `usage.attested_images`
  APARTE del medido [E]; M6 «Configuración» muestra `attested.*` por la vía genérica de `/config-history`. **(13)
  `src/lenguaje/atestiguado.ts`** (molde `figuras.ts`): tablas palabra-máquina para cada vocabulario de (A.1); fuera de vocabulario →
  `LiteralDesconocido`; glosas `GLOSA_IMAGEN_ATESTIGUADA`, `GLOSA_PRIVADA_SOLO_AUTOR`, `GLOSA_RETIRADA_TOMBSTONE`,
  `GLOSA_NO_VIO_SINTETIZADOR`, `GLOSA_LECTURA_JUICIO`, `GLOSA_MATERIAL_PACIENTE`, `GLOSA_CAPTION_NO_PRIVADO`, `GLOSA_NO_INSTRUMENTADO_1_14`.
- **Qué mide el gate de paridad (`tools/parity_check.py`):** (A) 7 rutas nuevas con wrapper del método correcto en `client.ts` Y
  consumidor fuera de `client.ts` (multipart POST incluido: `check_rutas` :266 casa por literal `/attestations`); `/usage.attested_images`
  leído en M8; `GET /plans/{id}.attested_images` leído en Preguntar. (B) `attested_images` en frozen ⇄ `RegistroCongelado.attested_images`
  ⇄ lector en Hoja Y `record_pdf` (`PDF_ACCESS_RE` :582; `SECCIONES` anclada :595 → 54); `deterministic_checks.attested_images`,
  `council.human_attestations.n_images`, `council.ledger.images[]`, `audit.panel[].saw_attested`, `token_usage.attested_images`,
  `epistemic_summary.attested_*`, `thread_context.parent_attested_images` tipados y leídos. (C) los 4 `stage.attestations.*` con caso en
  `describir()` (la superficie lee `add_event(run_id, "literal"`) + los 4 `plan_events attestation.*` (:563). (D) PDF: 0 huecos;
  `PDF_NESTED += ('attested_images.items[]', 'attested_images.vision', 'council.ledger.images[]')`. (F) vocabularios de `attestations.VOCABULARY`
  + `verify_output.ATTESTED_CHECK_STATES_*` + `runs.ATTESTED_DECLARED_EXCEPTIONS` (3) == unions TS sin escape == tablas de
  `atestiguado.ts` == TODOS los fixtures por ruta (`attested_images.state`, `items[].storage.state_at_run`, `items[].consent.kind`,
  `items[].exif_state`, `items[].ledger_state`, `audit.panel[].saw_attested.detail`, `deterministic_checks.attested_images.state`, los
  `detail.state` HTTP). Regla nueva medida: cada ítem del fixture pinta «vista por <lentes>» desde `seen_by_lenses` y «el sintetizador
  NO la vio» desde `delivery.bytes_to_synthesizer false` — del servidor, sin inferirlo. `parity_debt.json`: 0 líneas nuevas (la ranura
  nace con el ADR) o UNA por hueco con `adr 'ADR-0086'` si la webapp llega después; ninguna `[pdf]`.
- **Gate de cobertura del PDF (ADR-0083 K):** `frozen_keys` 53 → 54 con `attested_images`; `pdf_sections_cover(frozen 1.14 real) ==
  {missing [], extra []}`; born `'1.14'`; regex ANCLADA devuelve 54; `smoke_record_pdf` ≥ 63 → ≥ 72.
- **Redeploy (Dokploy):** las 14 env `WITT_ATTESTED_*` con defaults en compose; `python-multipart` y el pin `minio<8` entran con el
  build; la tabla nace por `create_all` en el primer arranque (Postgres: SQL medido en F.3); UNA fila `new-field` en `config_history`
  por `attested.enabled/backend/vision/team_view` al arrancar (excepción DECLARADA del kill-switch, patrón 0082 L.2 ii / 0083 O.5);
  **antes de anunciar la función al laboratorio**: volumen `attested_private` montado o `WITT_ATTESTED_BACKEND=minio` con bucket
  privado verificado (LG2/LG3); el redeploy pendiente de ADR-0076…0084 debe estar en prod ANTES. Sin volumen: subir → redeploy → GET
  bytes 404 `bytes-missing` PERMANENTE declarado (a diferencia de las figuras no hay refetch) — honesto, no roto; la `durability.note`
  lo avisa en el 201 y en la Hoja.
- **Held-out (ADR-0072):** `SYNTH_TOOL.description` NO cambia y `synth_system` sólo gana la cláusula cuando viajan imágenes → la
  serie `ab_trapped_scalar` sigue comparable sin tanda nueva (a diferencia de 0083 LG9). Declarado.
- **Consejo (0082):** un `aporto` con imagen sigue `covered-by-attestation` por su texto; la imagen no cubre nada por sí sola y el
  registro lo dice (`n_with_image`).
- **Límites declarados (no se disfrazan):** las CIFRAS escritas en un caption no tienen predicado duro (sólo los IDENTIFICADORES vía
  `attestation_identifier_leak`): misma clase y misma cláusula que `knowledge_now` hoy; la Hoja pinta el caption con [A] para
  auditarlo a mano; candidato a `attested_numerals_grounded` informativo en 0086.1 tras medir en LG4 · una lente puede describir la
  imagen en `caught` ignorando la regla: `attested_readings_in_caught` lo MIDE, REVISE no consume `attested_readings`, y el registro
  lo etiqueta juicio — no lo corrige · el registro no puede distinguir un `citation_support 'supported'` informado por píxeles de
  uno por texto: `citation_support_vision_informed` lo DECLARA (misma limitación que 0083) · el strip de metadatos no redacta
  contenido VISUAL (rostros, etiquetas, pantallas de equipo): la desidentificación es DECLARADA por la persona; ninguna redacción
  automática (P) · los bytes salen a los proveedores de las dos lentes: la persona lo acusa al subir (C.4); Anthropic declara
  procesamiento efímero sin entrenamiento (Context 9), OpenAI con `WITT_OPENAI_STORE=0` · el mismo sha subido por dos personas al
  mismo plan registra UN consentimiento (C.5) · quien aprueba puede no ser quien subió (`attached_by_is_uploader` lo declara) · un
  volumen perdido o un backup restaurado no obedecen al tombstone (E.4) · el caption del padre viaja al hijo sin acto humano (B.6.i) ·
  `bytes-missing` es permanente: no hay fuente de la que re-bajar.

## Tabla de env (todas con default declarado; lector `attestations.env_config()` tolerante en tiempo de llamada; toda env = reinicio; las 14 `WITT_ATTESTED_*` entran a `models.ENV_TABLE` con `adr '0086'`; `SNAPSHOT_FIELDS += ('attested.enabled', 'attested.backend', 'attested.vision', 'attested.team_view')` FUERA de `panel_signature`; `WITT_ATTESTED_DIR`, `WITT_ATTESTED_MINIO_*_KEY` y `MINIO_*` quedan FUERA de `ENV_TABLE` — la tabla no registra rutas ni secretos — y sólo su PRESENCIA viaja)

| Variable | Default | Lector | Efecto / fuente declarada |
|---|---|---|---|
| `WITT_ATTESTED_IMAGES` | `1` | `app` · `runs` · `audit()` | kill-switch maestro (N.1): `0` = frozen 1.13 byte a byte salvo `ATTESTED_DECLARED_EXCEPTIONS` (3); subida/inherit 409, ledger con `images[]` 400, GET índices 'kill-switch', bytes 404; **withdraw sigue vivo** |
| `WITT_ATTESTED_VISION` | `1` | `audit()` | `0` = ninguna lente recibe bytes atestiguados; captions al sintetizador y al consejo siguen (N.2); `WITT_FIGURES_VISION=0` también los apaga (literal propio) |
| `WITT_ATTESTED_BACKEND` | `local` | `attestations.storage_backend` | `local` \| `minio`; fuera de vocabulario → `local` con `source 'default-invalid-env:…'`; `minio` sin `MINIO_ENDPOINT/ACCESS_KEY/SECRET_KEY` → `storage-unavailable (missing env: …)` y 503 en la subida (JAMÁS cae a local); cada fila conserva su backend; cambiar la env no migra |
| `WITT_ATTESTED_DIR` | (vacía = `<repo>/attested_private`) | `attestations.LocalStorage` | raíz PRIVADA del backend local (`0o700`/`0o600`; `dir_state` medido; win32 declarado); JAMÁS bajo `mcp_cache`; en Dokploy exige VOLUMEN (`attested_private:/app/attested_private` comentado en el compose) — sin él, `bytes-missing` permanente tras redeploy, declarado en `durability.note`; FUERA de `ENV_TABLE` |
| `WITT_ATTESTED_MINIO_BUCKET` | `witt-attested-private` | `attestations.MinioStorage` | bucket PRIVADO dedicado (≠ `data-inamovible-raw`); `bucket_exists/make_bucket` en `probe()`; versioning OFF (E.4); jamás presigned |
| `WITT_ATTESTED_MINIO_ACCESS_KEY` / `WITT_ATTESTED_MINIO_SECRET_KEY` | (unset ⇒ `MINIO_ACCESS_KEY/SECRET_KEY`) | `attestations.MinioStorage` | credenciales de un usuario MinIO DEDICADO con política acotada al bucket (recomendación E.5); sólo en Dokploy Environment; FUERA de `ENV_TABLE`; `credentials_source` declara cuál se usó |
| `MINIO_ENDPOINT` / `MINIO_SECURE` | (ya existen en el compose :25-28) | `attestations.MinioStorage` (patrón `raw_store._client`) | endpoint interno (`minio_net`); FUERA de `ENV_TABLE` |
| `WITT_ATTESTED_MAX_IMAGE_MB` | `5` (clamp 0.1..7) | `app` (C.2 precheck y stream) · `attestations.validate_bytes` · `select_for_panel` | bytes CRUDOS por imagen; 413 por `Content-Length` sin leer y por stream con tope; 7 MB ≈ 9.3 MB b64 < 10 MB/imagen de la API (Context 9) |
| `WITT_ATTESTED_MAX_PER_PLAN` | `8` (clamp 1..24) | `app` · ledger | filas VIVAS (no retiradas) por plan → 409 `attestations_cap_reached {scope 'plan'}`; al aprobar 400 `too_many_attested_images` |
| `WITT_ATTESTED_MAX_TOTAL_MB` | `24` (clamp 1..168) | `app` | suma de bytes vivos por plan → 409 `attestations_cap_reached {scope 'total_mb'}` |
| `WITT_ATTESTED_MAX_PER_LENS` | `4` (clamp 0..8) | `attestations.select_for_panel` | imágenes atestiguadas por petición de lente, APARTE de `WITT_FIGURES_MAX_PER_LENS`; invariante `figures + attested ≤ 20` con recorte declarado `many_image_guard`; cap b64 8 MB por petición COMPARTIDO (figuras primero) |
| `WITT_ATTESTED_MAX_PER_USER_PER_DAY` | `30` (clamp 1..500) | `app` (`db.count_attested_uploads_today`) | rate limit de subida por cuenta (UTC) → 429 `upload-rate-limited {n_today, cap, resets_at}` |
| `WITT_ATTESTED_CAPTION_CHARS` | `1000` (clamp 100..4000) | `attestations.validate_form` | tope del caption OBLIGATORIO (≥ 10; 400 `caption-too-long`); íntegro en la tabla y en `plans.council_ledger_json`; ≤ 600 en el frozen (`caption_truncated`); ≤ 200 en `parent_attested_images` |
| `WITT_ATTESTED_ALLOWED_MEDIA` | `image/jpeg,image/png,image/webp` | `attestations.validate_bytes` | CSV acotado a `figures.MEDIA_TYPES` (GIF habilitable; fuera de tabla se ignora y se declara `allowed_media_env_ignored[]`); PDF/TIFF/HEIC/SVG/DICOM → 415 siempre |
| `WITT_ATTESTED_EXIF` | `strip` | `attestations.strip_metadata` | `strip` = quitar APP1/APP2≠ICC/APP3-13/COM (JPEG), tEXt/zTXt/iTXt/eXIf/tIME (PNG), EXIF/XMP + VP8X (WebP), Comment/XMP (GIF) ANTES de hashear/almacenar; fallo → 422 `metadata-strip-failed`, nada se guarda; `declare` = tal cual con `exif_present` medido y `exif_state 'declared-not-stripped'` |
| `WITT_ATTESTED_TEAM_VIEW` | `1` | `app.view_rule` | `1` = honrar `share_scope 'team'` declarado por quien sube; `0` = author-only para todos aunque la persona haya declarado team; material de paciente es author-only SIEMPRE |
| `WITT_ATTESTED_WITHDRAW` | `uploader` | `app` withdraw | quién retira: `uploader` \| `team` (403 `withdraw-not-uploader` con la regla) |
| `WITT_ATTESTED_PATIENT_MATERIAL` | `0` | `attestations.validate_form` | `1` = material de paciente permitido con consentimiento declarado + desidentificación + acuse al aprobar; `0` = 400 `patient_material_not_allowed` (Fase I sin material de paciente — OE4) |
| `WITT_FIGURES_VISION` / `WITT_FIGURES_VISION_LENSES` / `WITT_FIGURES_OPENAI_DETAIL` / `WITT_FIGURES_COUNT_TOKENS` | (ya existen, ADR-0083) | `composite_auditor` · `runs` | REUTILIZADAS sin fila nueva: las MISMAS ≤ 2 lentes, el mismo `detail` para la proyección, la misma medición opcional por `count_tokens` |
| `WITT_PROXY_MAX_BODY_MB` (webapp, `route.ts`) | `6` | proxy Next | precheck `content-length` → 413 con el mismo `state` que el backend ANTES de `arrayBuffer()` (O.1) |

Constantes declaradas (viajan en `caps` con `source 'constant (ADR-0086)'`): `FORM_OVERHEAD` 64 KiB; `SHA_SHORT` 12; caption ≤ 600 en el
frozen y ≤ 200 en el snapshot del hijo; consent_text ≤ 600 (≤ 300 en el frozen); límite many-image 20; `expose_headers` fijos (G.2).

## Gates NO-SPEND (máscara de siempre: `WITT_BACKEND_DB_URL` sqlite tmp · `NEO4J_URI=''` · `RAG_BACKEND=sparse` · `OPENAI_API_KEY=''` · `ANTHROPIC_API_KEY=''` · `BRAVE_API_KEY=''` · `MINIO_ENDPOINT=''` · `WITT_RUN_ORIGIN=smoke` · `WITT_MCP_CACHE_DIR=<tmp>` · **`WITT_ATTESTED_DIR=<tmp fresco por smoke>`**; venv `dev/.venvs/witt-query-service`: fastapi 0.141.1 · starlette 1.6.0 · python-multipart 0.0.32 · minio 7.2.20 · fpdf2 2.8.8 + Pillow 12.3.0; `urlopen` bloqueado y contado = 0 en TODOS; `mcp_cache` real byte-idéntico; conteos «F9 mide» hasta el integrador)

| Gate | Hoy @ 7d9ce15 (tras 0084 borrador) | Tras ADR-0086 | Qué MIDE de nuevo |
|---|---|---|---|
| `smoke_attestations.py` (NUEVO, lib puro, 0 BD) | — | **≥ 70** (F9 mide) | fixtures sintéticos (A.13) → `sniff_mime`/`image_dims`/sha == MANIFEST antes y después del strip · `%PDF`/TIFF/SVG/HEIC/basura → `unsupported-media-type` con `sniffed` · GIF fuera por default y dentro con `WITT_ATTESTED_ALLOWED_MEDIA=…,image/gif` · IHDR 8000² → `image-too-many-pixels` SIN decodificar · 8×8 → `image-too-small` · strip JPEG quita APP1+APP2(MPF)+COM, conserva APP0/APP2-ICC/APP14 y SOF (dims iguales; bytes desde SOS idénticos), `exif_removed == ['APP1','APP2:MPF','COM']`, sha ≠ sha_received · PNG quita tEXt/tIME, IDAT idéntico, CRC de los conservados intactos · WebP quita EXIF, RIFF size == len−8, bit VP8X bajado · GIF quita Comment · sin metadatos → `none-found` y sha == sha_received · JPEG truncado → `strip-failed` (nada se guarda) · `EXIF=declare` → `declared-not-stripped` + `exif_present true` · `validate_form`: cada 400 tipado (caption < 10, consent kinds, texto obligatorio con terceros/paciente, `third_party_ack`, `patient_material` sin default, paciente sin consented/desidentificación, licencias, scope) · `LocalStorage` put/get/stat/delete atómico (`.part` ausente tras put; segundo put mismo sha → ya presente), `0o700/0o600` en POSIX, `dir_state` read-only/missing/win32 por sonda, raíz ≠ `mcp_cache` (assert de ruta) · `MinioStorage` con `FakeMinio`: `put_object(bucket, key, BytesIO, length, content_type=, metadata=)` POSICIONAL medido por firma (un fake con `user_metadata` keyword-only FALLA en claro), `get`/`stat`/`remove`, `bucket_exists False → make_bucket` en `probe`, `sdk_version`; sin `MINIO_*` → `storage-unavailable (missing env: …)` sin importar `minio`; `WITT_ATTESTED_BACKEND=basura` → `local` declarado · `serve_check`: byte alterado en disco → `bytes-mismatch` sin datos; archivo ausente → `bytes-missing`; tombstone → `withdrawn`; backend de la fila ≠ configurado → `backend-not-configured-now` · `select_for_panel`: excluye withdrawn/missing/mismatch/size contadas, `max_per_lens`, request cap 8 MB compartido con figuras PRIMERO, `many_image_guard` (12 figuras + 9 → 8 atestiguadas), orden por `uploaded_at` · builders: `attested=None` byte a byte 1.13 en los TRES transportes; con lista → figuras → separador → `[rótulo, imagen] × N` → texto (orden medido) · `prompt_item ∩ FORBIDDEN == ∅`; `public_item` sin `b64`/`storage_key`/ruta · `ENV_SPECS` 14/14 tolerantes con `source` · vocabularios sin duplicados y `ATTESTED_DECLARED_EXCEPTIONS == 3` |
| `smoke_gate_citations.py` | 80 (≥ 92 tras 0084) | **+ ≥ 10** | cita con `id == sha256` → inadmisible con la razón literal · `id` con 12 hex del sha → inadmisible · `'attested:<sha12>'` → inadmisible · cita PMC legítima + ítems atestiguados → ok · id de figura `'<PMCID>#F1'` con prefijo hex parecido NO casa · sin ítems → `'no-attested-images'` y 0 predicados en la conjunción (admisibilidad de hoy byte a byte) · fragmento con todas las llaves y ceros medidos · closure recibe ninguna confianza (R2) · `attestation_identifier_leak` con caption `PMID:99999999` repetido en la respuesta sin evidencia → fuga (extensión por construcción medida) |
| `smoke_panel_vision.py` | 60 | **+ ≥ 22** | `VERDICT_TOOL` sin `attested_readings` byte a byte el golden de 1.13; `audit(attested=[2])` con caller espía: SÓLO evidence-grounding y reproducibility reciben `member['attested']`, su `system` termina en `ATTESTED_READING_RULE` y los otros dos no; sin atestiguadas el `system` y el cuerpo son byte a byte 1.13; bloques atestiguados DESPUÉS de los de figuras, con separador y rótulo `ATTESTED IMAGE k — attested:<sha12>`, en los TRES transportes; `saw_attested` keyset cerrado, `detail` ∈ `SAW_ATTESTED_DETAILS` en cada caso (`lens-not-in-vision-lenses`, `no-eligible-images`, `kill-switch WITT_ATTESTED_VISION=0`, `kill-switch WITT_FIGURES_VISION=0`, `model-vision-unknown`); `attested_readings` con id no entregado → dropped; string → `[]` + 1; una lectura en `caught` → conservada verbatim + `attested_readings_in_caught` contado, `_panel_findings` la ignora; id `attested:` colado en `figure_readings` → `attested_ids_in_figure_channel`; `citation_support_vision_informed` true con `saw_attested.n > 0`; proyección por `models.vision_tokens` (1600×1200: haiku 1564 · gpt-4o 765); `panel_signature` idéntica con/sin; `WITT_ATTESTED_IMAGES=0` con `attested=` pasado → ninguna fila trae `saw_attested` (M.1); `urlopen` 0 |
| `smoke_openai_responses.py` · `smoke_panel_quorum.py` | 81 · 42 | **+2 c/u** | golden byte a byte del cuerpo SIN `attested` — nada cambia para los llamadores de hoy |
| `smoke_models.py` | 96 (≥ 101 tras 0084) | **+ ≥ 6** | 14 filas `adr '0086'` en `ENV_TABLE` ⊆ compose ∩ README con defaults byte-iguales a `attestations.ENV_SPECS` (bidireccional); `WITT_ATTESTED_DIR`/`*_MINIO_*_KEY`/`MINIO_*` NO en `ENV_TABLE` pero SÍ en compose/README con «never git»; `SNAPSHOT_FIELDS` +4 FUERA de `panel_signature` (firma golden intacta); `snapshot()` trae `attested.*` con fuente |
| `smoke_council.py` · `smoke_council_jobs_db.py` | 70 · 59 | **+ ≥ 8 · +2** | `payload_r2` con `human_attestations.images[]` serializa captions y JAMÁS b64 (substring del fixture); sin imágenes byte a byte 1.13 (golden); `R2_PREAMBLE` gana el sufijo SÓLO con imágenes; `judge_coverage`: `aporto` con imagen → `covered-by-attestation`, `n_with_image 1`; `summary_for_thread += n_attested_images` sin caption ni sha; `apply_ledger_decisions(images=)` conserva en `aporto` y rechaza en keep/discard; `_inherited_criteria` propaga el conteo |
| `smoke_run_pipeline.py` | 372 (≥ 410 tras 0084) | **+ ≥ 48** | contrato `'1.14'`; `ATTESTED_DECLARED_EXCEPTIONS` EXACTAMENTE 3; fixture «atestiguadas-completo» (ledger aprobado: 1 `aporto` + 1 imagen, 1 imagen en `knowledge_now`, 1 material de paciente acusado, 1 retirada entre aprobar y correr, `FakeMemoryStorage`): `user_text` del sintetizador (capturado) trae `human_attestations.images[]` con caption y SIN b64/`storage_key`/`data:image` (assert por llaves y por substring); `system` con `ATTESTED_IMAGES_CLAUSE` sólo en ese fixture (igualdad byte a byte en los demás); ctx r2/r3 misma vista; panel espía: SOLO 2 lentes con `member['attested']`, `stage.audit.judge.attested_sent == saw_attested.n` por (reviewer, lens); `frozen.attested_images` keyset EXACTO (L) con `n_attached 2`, `n_withdrawn_before_run 1`, `n_patient_material 1`, `storage.state_at_run 'stored'`, `seen_by_lenses`, `vision.rule == ATTESTED_READING_RULE`, `cost_projection` clase proyección; `deterministic_checks.attested_images 'checked'` ok; stub que cita `attested:<sha12>` → pass2 inadmisible con la razón literal; caption con `ENSDARG00000099999` repetido sin evidencia → `attestation_identifier_leak` con `_scope`; archivo borrado tras aprobar → ítem `bytes-missing`, no al panel, corrida sigue; byte alterado → `mismatch` excluida; bandera `patient-material` con `emitted_by` LISTA en ledger y frozen; `epistemic_summary.attested_*` y `_run_view`; `agents_invoked` fila `attestations:2/2`; `token_usage.attested_images` cuadra con `saw_attested`; `by_stage_sum_matches_by_model` true; eventos: `stage.attestations.plan → image ×2 → … → panel → summary` (UN summary siempre, también kill-switch); `pdf_sections_cover(frozen real) == {missing [], extra []}`; sin plan → `'not-applicable (no-ledger)'`; **KILL-SWITCH M.1: `WITT_ATTESTED_IMAGES=0` → frozen == corrida encendida del MISMO fixture (sort_keys, keyset y valores) tras restar aditivas 1.14 e identidad, salvo EXACTAMENTE las 3 excepciones (diff de paths listado), 0 `stage.attestations.image`, `user_text` 1.13 byte a byte, `human_attestations` SIN llave `images`**; assert GLOBAL anti-binario sobre TODA la BD del gate ampliado a las b64 sintéticas; `urlopen` 0; `mcp_cache` idéntico |
| `smoke_thread_context.py` | 42 | **+ ≥ 6** | padre 1.14 con 2 imágenes → `parent_attested_images` 2 filas, caption ≤ 200, sin bytes, `seen_by_lenses`; padre 1.14 sin imágenes → `[]`; padre 1.13 → llave AUSENTE; `parent_identifier_leak` cubre un PMID puesto en el caption del padre; `council_summary.n_attested_images`; el sintetizador del hijo recibe el snapshot sin `council_summary` (E5 intacto) |
| `smoke_attestations_http.py` (NUEVO, TestClient ASGI sin lifespan, `WITT_ATTESTED_DIR` mkdtemp, `FakeMinio` inyectado) | — | **≥ 90** (F9 mide) | 401 sin sesión en las 7 · 404 plan · 409 `plan_already_used` · plan `not-requested`/`disabled`/`skipped` → 409 `attestations_require_ledger`; `queued` → 201 (staging) · `Content-Length` > tope → 413 con **0 bytes leídos** (receive espía) · cuerpo `chunked` sin `Content-Length` con tope 0.001 MB → 413 al rebasar · PNG sintético → 201 `{item sin b64/key, sha256 == MANIFEST post-strip, sha256_received == pre-strip, exif_state 'stripped (…)', storage {local, stored}, durability {default, note}}` y fila en BD; `Content-Type` mentiroso `image/jpeg` sobre PNG → `media_type 'image/png'` + `media_type_declared_mismatch true` · mismo sha → 409 `attested_image_already_uploaded`; por OTRA sesión → `uploaded_by_is_viewer false` · GIF → 415 (default) · `%PDF` → 415 con `sniffed null` · IHDR 8000² → 422 · JPEG truncado → 422 `metadata-strip-failed` y tabla sin fila · cada 400 de (C.4) · `MAX_PER_PLAN=2` → 3.º 409 `scope 'plan'`; `MAX_TOTAL_MB` → `scope 'total_mb'`; retirar libera cupo · `MAX_PER_USER_PER_DAY=1` → 429 con `resets_at` · `backend=minio` sin env → 503 `attested-storage-unavailable` (0 imports de minio, tabla vacía); `FakeMinio` que lanza → 503 y tabla vacía · kill-switch → subida 409, inherit 409, ledger con `images` 400, índice de plan `kill_switch`, bytes 404, **withdraw 200** · ledger: sha ajeno → 400 `unknown_attested_image`; imagen en `keep` → 400 `images_without_aporto`; retirada → 400 `attested_image_withdrawn`; paciente sin acuse → 400 `patient_material_unacknowledged`; con acuse → 200 `ledger.images[]`, `flags[]` con `emitted_by` LISTA y `source 'human-upload'`, `attached_to` sellado (2.ª aprobación tras borrador NO lo mueve), `attached_by_is_uploader` false cuando aprueba otra sesión; `images` omitido en borrador posterior conserva la vinculación; `[]` desvincula · `GET /plans/{id}` trae `attested_images` · `POST /runs {plan_id}` → `runs.council_json.ledger.images[]` (copia F.4); tras el sello upload 409 pero withdraw 200 · índice de plan: toda sesión 200 con `viewer_may_view` por sesión y `servable` medido · bytes (plan y corrida con frozen 1.14 sembrado): uploader 200 con `Content-Type` medido, `ETag`, `Cache-Control: private, no-store`, `X-Content-Type-Options: nosniff`, `X-Witt-Attested-*`, `Content-Disposition`, body sha == path, evento `attestation.bytes_served`; otra sesión → 403 `forbidden (author-only)`; `share_scope team` + `TEAM_VIEW=1` → 200; `TEAM_VIEW=0` → 403; `patient_material` + team → 403 SIEMPRE; archivo alterado → índice `bytes-mismatch` y GET 409 (jamás 200); archivo borrado → 404 `bytes-missing`; fila `minio` con backend hoy `local` → `backend-not-configured-now` · withdraw: sin razón 400; otra sesión 403; uploader 200 `bytes_deleted true` + archivo ausente + GET 410 con tombstone + índice `withdrawn (tombstone)` + evento; 2.º → 409; frozen de la corrida NO cambió (`frozen_sha256` igual); cascada a la heredada (`cascade_n 1`) · inherit: uploader → 201 `ledger_state 'inherited'` con bytes COPIADOS y sha igual; otra sesión → 403 `inherit-not-uploader`; sha retirado en el padre → 400 `attested_image_not_inheritable` · `DELETE` → 405 · registro 1.13 → índice `not-instrumented (contrato < 1.14)` · identidad rota → 409 · CORS preflight expone `X-Witt-Attested-*` · `/runs/{id}/attestations` no captura `/runs/{id}/events`; `/plans/{id}/attestations` no captura `/plans/{id}/events` · `plan_events attestation.*` NO mueven `council_last_event_at` · `/usage.attested_images` cuenta 1 corrida · nada binario en ninguna respuesta JSON · `urlopen` 0 |
| `smoke_attestations_db.py` (NUEVO) | — | **≥ 20** | `create_all` idempotente ×2 (SQLite) sobre una BD PRE-POBLADA: sólo aparece `plan_attested_images`, ninguna fila de plans/runs/users cambia; SQL compilado para el dialecto `postgresql` sin funciones exclusivas de SQLite y con `TIMESTAMP WITH TIME ZONE` en las fechas (lección ADR-0078); UNIQUE `(plan_id, sha256)` rechaza duplicado; `attach` y `withdraw` write-once (2.ª → False/0); `count_live` excluye retiradas; `count_attested_uploads_today` por UTC; `attested_schema_state()` `{ready True}` / `{missing}` sobre una BD vieja simulada; FK a `plans`/`users` |
| `smoke_record_pdf.py` | 56 (≥ 63 tras 0084) | **≥ 72** | regex ANCLADA devuelve 54 llaves; frozen 1.14 real → cover `{missing [], extra []}`; quitar `attested_images` → 'NO INSTRUMENTADO (contrato < 1.14)'; `null` + state → 'null declarado — razón'; fixture completo → 2 ítems con `attested:<sha12>`, consentimiento en palabras, 'material de paciente SI (desidentificado SI; acuse al aprobar SI)', 'EXIF stripped (…)', 'almacenamiento local/stored', 'vista por 2 lentes: JUICIO', 'MINIATURA: NO SE IMPRIME (privado…)'; ítem retirado → 'retirada SI (<fecha>)'; kill-switch → estado + excepciones; `dc.attested_images` impreso; `b64 ∉ pdf`, ningún sha de 64 de `storage_key`, 0 `/Subtype /Image` nuevos respecto al mismo registro sin atestiguadas; ≤ 3 KB por ítem; determinismo (dos `build_pdf` iguales); checks ADR-0073 a–f y 0083 (6) siguen verdes; `urlopen` 0 |
| `smoke_council_http.py` · `smoke_usage_http.py` · `smoke_runs_list_http.py` | 74 · 34 · 25 | **+4 · +3 · +1** | respuesta del ledger con `n_images`/`images[]`/`has_patient_material` y evento `council.ledger` con `n_images`; `/usage.attested_images` forma `{state, n_runs_with_attested, n_images_attached, n_patient_material, bytes_stored_now, vision_tokens_projected_by_model, usd_projected, class, rule}` con 0 medido ≠ null; `epistemic_summary.attested_*` lista == detalle |
| resto (competence 39 · run_recovery 40 · query_service 47 · precedent 30 · council_index 63 · …) | medido igual | **43+/43+ smokes exit 0 (F9 mide)** | `precedent.py` sin tocar (`grep attested` = 0 medido hoy); `council_index` sin tocar (indexa `decision` sin `attested_text`, :400-408); los demás sólo si un aserto se rompe por llaves nuevas |
| `smoke_live_attestations.py --dry-run` (estático) | — | **exit 0** | con `FakeMemoryStorage`: sube la PNG sintética por el código REAL de `validate_bytes`/`strip_metadata`/`sha`, imprime la petición EXACTA que recibiría cada lente con 1 imagen atestiguada + 1 figura (orden, rótulos, tamaño b64) en los TRES transportes con los callers reales CAPTURADOS (`urlopen` bloqueado, cliente OpenAI falso; `content_equals_blocks True` ×3); ningún módulo de BD importado; nada escrito |
| paridad en LECTURA (`witt-webapp/tools/parity_check.py` copiado al scratchpad con `BACKEND` = este worktree; la webapp NO se toca) | — | huecos ESPERADOS declarados | `[registro] attested_images` · `[rutas] 7` · `[etapas] stage.attestations.plan \| image \| panel \| summary` + 4 `plan_events` · `[pdf] 0` (el backend la pinta) — hasta que W1–W5 aterricen |

## Gates EN VIVO (los corre Emmanuel; cada uno gasta lo que dice; resultados al ADR como MEDICIÓN con fecha)

- **LG1 · Subida real desde la webapp (0 USD):** en un plan de prueba con consejo `applicable`, subir 1 PNG propio y 1 JPEG con EXIF
  REAL (foto propia, NO paciente; GPS/fecha presentes) → 201, `exif_state 'stripped (APP1, …)'`, `sha256 ≠ sha256_received`; bajar por
  la Hoja como autor → sha256 de lo descargado == sha256 del índice y `exiftool`/`python -c` no encuentra APP1 (LG-A5 de C); otra
  sesión (Natalia) → 403 «privada: sólo su autor» y SÍ ve el caption; un `.gif` → 415 glosado; un `.heic` → re-codificado por la
  webapp o el literal «convierte a JPEG/PNG»; un archivo de 6 MB → 413 del PROXY (mismo `state`) y, con `WITT_PROXY_MAX_BODY_MB=20`,
  413 del backend con 0 bytes leídos (log). Anotar `strip_ms`, `sha_ms`, `storage_put_ms` del evento `attestation.uploaded` (p95 > 10 s
  → revisar Traefik/tamaño).
- **LG2 · Volumen/persistencia (0 USD; decide OE1 por MEDICIÓN):** activar `attested_private:/app/attested_private` (o
  `WITT_ATTESTED_DIR` a una ruta montada) → tras redeploy GET bytes → 200; sin volumen → 404 `bytes-missing` PERMANENTE declarado y
  la Hoja lo dice — el resultado fija el default operativo (`local` + volumen vs `minio`). `/config-history` ganó
  `attested.enabled/backend/vision/team_view` (`first-boot-snapshot`).
- **LG3 · MinIO privado (0 USD; sólo si OE1 = minio):** crear usuario dedicado + política acotada + bucket `witt-attested-private`
  (consola 9101) con versioning OFF; `WITT_ATTESTED_BACKEND=minio` + credenciales en Dokploy + redeploy → `probe().state 'stored'`,
  `sdk_version '7.2.20'`; `smoke_live_attestations.py --probe-storage --backend minio` desde la Terminal del servicio: put/get/remove
  de 1 objeto sintético con sha igual, `stat_object → NoSuchKey` tras retirar, `get_bucket_versioning` == off; anónimo → 403 (`mc
  anonymous get` / `curl http://<host>:9100/witt-attested-private/<key>` sin firma); `9100/9101` del host cerrados por firewall
  (`docker-compose.minio.yml:10-12` los publica); conteo de objetos de `data-inamovible-raw` antes == después.
- **LG4 · UNA corrida real con 2 imágenes SINTÉTICAS aportadas (dominio público; ≈ +0.02–0.06 USD sobre la base 0.208 [E], panel de
  hoy):** ledger aprobado con `aporto` + imagen y `knowledge_now` + imagen → Traza `stage.council.ledger → stage.attestations.plan →
  image ×2 → … → panel → summary`; `frozen.attested_images.state 'attached'`; `audit.panel[].saw_attested.n == 2` EXACTAMENTE en
  evidence-grounding y reproducibility (0 en las otras); `attempts[].error_kind` sin `http-400` (la forma de bloques con separador y
  rótulo fue aceptada por Anthropic Y por el juez OpenAI); `attested_readings` presentes, etiquetadas, y JAMÁS en `caught/reasons`
  (revisión manual + `attested_readings_in_caught 0`); pass2 con `bytes_b64` en el `user_text` del sintetizador == 0 (medido);
  `deterministic_checks.attested_images 'checked'` ok; `input_tokens` de las dos lentes vs la misma corrida con
  `WITT_ATTESTED_VISION=0` → Δ descriptivo vs `visual_tokens_projected` (sustituye la proyección); con `WITT_FIGURES_COUNT_TOKENS=1`
  → `saw_attested.tokens_measured` en haiku.
- **LG5 · Turno N+1 (≈ 0.2 USD):** «Reforzar la pregunta» desde LG4 → plan nuevo → `parent_attested_images` (2, ≤ 200 chars, sin
  bytes) en el snapshot del hijo y en `council_summary.n_attested_images`; marcar «volver a adjuntar» en UNA → `POST …/inherit` 201
  con `ledger_state 'inherited'`; desde OTRA sesión el inherit da 403; correr → el hijo declara 1 imagen propia (heredada) y el
  `user_text` del hijo no trae sha ni caption del padre como evidencia (`parent_identifier_leak` + `attestation_identifier_leak` ok).
- **LG6 · Retiro en vivo (0 USD):** withdraw desde la Hoja de la imagen heredada del padre → 410 en GET, miniatura → «RETIRADA»,
  índice `withdrawn (tombstone)`, `cascade_n 1` (la copia del hijo también), el PDF de la corrida ya congelada imprime la MISMA
  línea que antes (sha y metadatos) y `record.pdf` sigue 200; `frozen_sha256` igual antes/después.
- **LG7 · Material de paciente (SÓLO con consentimiento REAL y desidentificado; 0 USD sin correr):** subir con
  `patient_material=true` sin `patient-consented` → 400 `patient_material_without_consent`; con consentimiento + desidentificación →
  201 y bandera `patient-material · gate human · emitted_by attestations (human-upload)` visible en la card del ledger, la Hoja y el
  PDF; aprobar sin acuse → 400 `patient_material_unacknowledged` y el botón deshabilitado; con `share_scope team` → 403 para otra
  sesión de todas formas; abrir el PDF y contar `/Subtype /Image`: 0 nuevos.
- **LG8 · Kill-switch en prod (0 USD):** `WITT_ATTESTED_IMAGES=0` + redeploy → subida 409 `attested_images_disabled`, ledger sigue
  funcionando sin `images`, corrida nueva con `frozen.attested_images {state 'kill-switch …', kill_switch}`, withdraw 200; reencender.
- **LG9 · Paridad y PDF en prod (0 USD):** `npm run gate` (tsc + vitest + `parity_check.py`) verde contra `contract-1.14-frozen`;
  la Hoja LEE `X-Witt-Attested-*` y `X-Witt-Figure-*` (route.ts corregido: `bytesDeFigura().license` deja de ser `null`); PDF de LG4:
  sección «IMAGENES APORTADAS» sin miniatura, con consentimiento y material de paciente en palabras.

## Proyección de costo y latencia (CLASE: PROYECCIÓN — calculada con `models.vision_tokens` (fórmulas públicas verificadas HOY, Context 9) y tarifas g2 de `models.prices()`: haiku 1/5 · sonnet-5 2/10 · opus-5 5/25 · gpt-4o 2.5/10 · astra 10/50 USD/Mtok; supuestos DECLARADOS; ninguna imagen atestiguada se ha enviado desde este código; LG4/LG5 sustituyen cada cifra)

**Supuestos:** foto de laboratorio típica **1600×1200 px** JPEG 0.4–0.9 MB (0.55–1.2 MB b64) o foto de teléfono 4032×3024 (12 MP,
2–5 MB); caption ≈ 300 chars ≈ 75 tokens; 1–2 imágenes por corrida con imágenes; tope 4 por lente. **Tokens de visión por imagen
(1600×1200 / 4032×3024):** haiku (estándar) 1 564 / 1 564 · sonnet-5/opus-5 (alta) 2 494 / 4 784 (cap) · gpt-4o (tiles, `high`) 765 /
765 · astra (parches) 2 280 / 3 000 (cap). **Escenario A — panel de HOY (grounding = haiku, reproducibility = gpt-4o), 1 imagen
1600×1200, 1 panel:** visión 1 564×1e-6 + 765×2.5e-6 = 0.0016 + 0.0019 = **0.0035 USD**; captions (75 tok) al sintetizador pass1+pass2
(opus-5) 0.0008; captions a los 4 jueces ≈ 0.0008; `attested_readings` de salida (≈ 200 tok × 2 lentes: haiku 5/M + gpt-4o 10/M)
0.003; consejo r2 con 17 miembros opus-5 (75 × 17 × 5e-6) 0.0064 (+ r3 igual si corre) ⇒ **≈ 0.008 USD por imagen sin consejo ·
≈ 0.015–0.021 con consejo**; con REVISE (2.º panel) ×1.8 en la parte de panel; **4 imágenes ≈ 0.03–0.07 USD**. **Escenario B —
sucesor sonnet-5 en grounding:** +0.003 por imagen (2 494 × 2e-6 + salida). **Escenario C — Astra en reproducibility:** 2 280 × 10e-6 =
0.023 + salida 0.01 ⇒ **+0.03 por imagen** (+ reasoning tokens no proyectables). **Tope duro (8 imágenes/plan, 4/lente,
opus-5 alta + astra, fotos 12 MP):** 4×4 784×5e-6 + 4×3 000×10e-6 = 0.096 + 0.12 = **0.22 USD de visión por panel**. **Base medida
hoy 0.208 USD (mediana ADR-0081)** ⇒ **+4 % (A, 1 imagen, sin consejo) a +30 % (C, 4 imágenes, REVISE)**; el rubro dominante con
consejo encendido son los CAPTIONS a 17 miembros, no los píxeles (injerto de B). **Latencia [E]:** subida 1–5 s por imagen de 1–5 MB
(LAN Dokploy); precheck 0 ms; strip stdlib O(n) < 50 ms; sha < 20 ms; `put` local < 50 ms / MinIO interno 50–300 ms; el panel gana
≈ 1–3 s por lente con imágenes; ninguna etapa nueva con red externa. **Petición:** ≤ 12 figuras + 4 atestiguadas ≤ 20 imágenes
(fuera del régimen many-image) y b64 ≤ 8 MB ≪ 32 MB. **Almacenamiento [E]:** ≤ 24 MB por plan (8 × ≤ 5 MB, tope total); 30 planes/mes
con imágenes ⇒ ≤ 0.7 GB/mes peor caso, 0.1–0.2 GB típico; un volumen o bucket de 10 GB cubre > 1 año. **Registro:** ≈ 1.3 KB por ítem
sin bytes (8 ítems ≈ 10 KB). **Mensual a 30 corridas con 1–2 imágenes:** 0.3–1.3 USD (A) · 1–3 USD (C). Lo MEDIDO será `input_tokens`
por lente, `bytes` por ítem y `strip_ms/sha_ms/storage_put_ms`; todo lo demás viaja con clase 'proyección' en
`frozen.attested_images.vision.cost_projection`.

## Decisiones abiertas para Emmanuel (mínimas; cada una con default)

- **OE1 · Backend en producción.** Default de esta obra: `WITT_ATTESTED_BACKEND=local` CON volumen `attested_private` montado
  (LG2). Alternativa (default del plan §14, recomendada en cuanto haya bucket y credenciales — hoy PENDIENTES): `minio` con bucket
  privado `witt-attested-private`, usuario dedicado y versioning OFF (LG3). Ninguna migra a la otra sin CLI (declarado no
  construido). Registrar la decisión de almacenamiento con fecha en el ADR y en el README.
- **OE2 · Quién ve los BYTES.** Default: sólo el autor (`author-only`) y `share_scope 'team'` sólo si la persona lo declara al subir
  (`WITT_ATTESTED_TEAM_VIEW=1`); material de paciente SIEMPRE sólo autor. Alternativa estricta: `WITT_ATTESTED_TEAM_VIEW=0`.
  Alternativa laxa (NO recomendada; contradice «403 por default»): equipo por default.
- **OE3 · Encendido desde el merge.** Default: `WITT_ATTESTED_IMAGES=1` aun sin volumen (los bytes se DECLARAN efímeros en el 201
  y en la Hoja; el registro sha/metadatos permanece). Alternativa: `0` hasta LG2 en verde.
- **OE4 · Material de paciente en Fase I.** Default (DECISIÓN del orquestador 2026-09-16, revierte el default de la síntesis):
  `WITT_ATTESTED_PATIENT_MATERIAL=0` → 400 `patient_material_not_allowed` declarado, porque es la única pregunta de compliance que
  ninguna doctrina escrita responde (retención, base legal, jurisdicción) y el laboratorio trabaja con pez cebra: negar por default
  no cuesta nada y el interruptor es una env. Alternativa (la que la síntesis proponía): `1` = permitido con consentimiento
  declarado + desidentificación declarada + acuse literal al aprobar — encenderla es decisión de Emmanuel CON política escrita de
  retención; la maquinaria (tres declaraciones, acuse, bandera §7, author-only) se CONSTRUYE igual y se mide con `1` en los smokes,
  para que el interruptor sólo cambie el 400. Redacción previa: permitido por default hasta que el
  laboratorio tenga política escrita de retención (única pregunta de compliance que ninguna doctrina escrita responde — B/juez 1).
- **OE5 · Texto literal de la aprobación presupuestal (brief R6) y autorización de LG4/LG5 (≈ 0.3–0.5 USD en total).** Propuesta:
  «Apruebo hasta 8 imágenes atestiguadas por plan (≤ 5 MB c/u, ≤ 24 MB) entregadas a las dos lentes con visión (≤ 4 por lente; ≈
  +0.01–0.07 USD por corrida con el panel de hoy; ≈ +0.03 por imagen con Astra), captions al sintetizador, al consejo y a los
  jueces, sin bytes al sintetizador, sin tope de USD por corrida; toda cifra con clase.» — confirmar tal cual o acotar
  (`WITT_ATTESTED_MAX_PER_PLAN`, `MAX_PER_LENS`, `WITT_FIGURES_OPENAI_DETAIL=low`).
- **OE6 · Imágenes `staged` nunca adjuntadas.** Default: permanecen hasta withdraw (append-only) y cuentan en el cupo VIVO del
  plan. Alternativa: tombstone automático a N días (`WITT_ATTESTED_STAGED_TTL_DAYS`) — NO recomendada sin decisión humana explícita
  (§7); sería un ADR aditivo con borrado por evento declarado, jamás un cron silencioso.

(No son preguntas — defaults declarados + gate: EXIF `strip` (fallo → 422, nada se guarda; `declare` por env), GIF fuera por default
(env), topes 5 MB / 8 / 24 MB / 4 por lente / 30 por día (env), retiro sólo por el uploader (env), orden de aterrizaje 0084 → 0086
(ingeniería, Q.1).)

## Plan de implementación (rebanadas DISJUNTAS por archivo → integrador → 3 revisores → corrector)

Orden: **F1 → (F2 ∥ F3 ∥ F4 ∥ F5 ∥ F6 ∥ F7 ∥ F8) → F9 integrador → R1 / R2 / R3 → corrector.** F1 congela la INTERFAZ de
`attestations.py` (firmas de (A), forma de `AttestedImageItem`/`AttestedImageFrozen`, `Storage`, vocabularios); F2–F8 desarrollan
contra ella y, hasta que aterrice, contra un stub local con esas firmas que F9 retira. Todas las rebanadas arrancan sobre
`contract-1.13-frozen` (o `contract-1.12-frozen` @ 7d9ce15 si 0084 se retrasa — Q.1); ningún archivo tiene dos dueños en 0086; el
doble dueño con 0084 se resuelve por orden de aterrizaje (Q.2). Sin push (Emmanuel); commits por rebanada en
`feat/adr-0086-imagenes-atestiguadas` apilada.

- **F1 · `lib/attestations.py` + fixtures sintéticos + `smoke_attestations.py` + pin** — dueño de: `analysis/scripts/lib/attestations.py`
  (NUEVO: todo (A)), `rag_index/query_service/fixtures/attested/MANIFEST.json` (NUEVO, texto: shas pre/post strip y segmentos por
  fixture; los bytes los genera `attestations.synthetic_fixtures()`), `rag_index/query_service/smoke_attestations.py` (NUEVO),
  `rag_index/query_service/requirements.txt` (:10 → `minio>=7.2,<8   # ADR-0086: la 7.2 usa metadata= posicional; master es
  keyword-only user_metadata` + `python-multipart>=0.0.9   # ADR-0086: UploadFile/Form — la misma línea que ingest_service`),
  `.gitignore` (+ `attested_private/` tras :104). Interfaz congelada al cerrar F1.
- **F2 · `verify_output.py` + `smoke_gate_citations.py`** — dueño de: `analysis/scripts/lib/verify_output.py` (`attested_predicates(citations,
  attested_items, answer_text) -> (fragmento deterministic_checks.attested_images, extra_predicates[])`, `ATTESTED_CHECK_STATES_EXACT/
  PREFIXES`, `PREDICATE_ATTESTED_IMAGES_NOT_CITED`, `ATTESTED_RULES`, `ATTESTED_PREDICATES_VERSION 'attpred-1'`; molde `figure_predicates`
  :821 y `_mk_pred` :808) · `smoke_gate_citations.py` (+≥ 10).
- **F3 · `composite_auditor.py` + `models.py` + `figures.py` (sólo :1478-1520) + smokes del panel** — dueño de:
  `analysis/scripts/lib/composite_auditor.py` (`ATTESTED_READING_RULE` importada de attestations, `SAW_ATTESTED_DETAILS`,
  `VERDICT_TOOL.attested_readings` :565 patrón, `parse_attested_readings`, `attested_readings_from_panel`, `audit(..., attested=None)`
  :1446, `_attested_for_member` molde :1296, `_default_caller` :1216-1228 pasa `attested=` a los builders, `system += ATTESTED_READING_RULE`
  :1546 patrón, fila `saw_attested`/`attested_readings*` :1618-1626 patrón, `citation_support_vision_informed` ampliado,
  `_vision_summary` += `attested_vision` :1402, `AUDIT_INITIAL_QUORUM_KEYS += 'attested_vision'`, `attested_readings_in_caught`,
  `attested_ids_in_figure_channel`, `apply_to_bundle` copia) · `analysis/scripts/lib/models.py` (`ENV_TABLE` += 14 filas `adr '0086'`
  :283, `ENV_ADR_0086`, `SNAPSHOT_FIELDS += ATTESTED_SNAPSHOT_FIELDS` :378 FUERA de `panel_signature`; `vision_tokens` sin cambio) ·
  `analysis/scripts/lib/figures.py` (SÓLO `anthropic_blocks`/`openai_responses_parts`/`openai_chat_parts` ganan `attested=None`
  aditivo :1484-1520) · `smoke_panel_vision.py` (+≥ 22) · `smoke_models.py` (+≥ 6) · `smoke_openai_responses.py` (+2) ·
  `smoke_panel_quorum.py` (+2).
- **F4 · `runs.py` + `smoke_run_pipeline.py` + `smoke_thread_context.py`** — dueño de: `rag_index/query_service/runs.py` (contrato
  `'1.14'` :51; `ATTESTED_IMAGES_CLAUSE` junto a :1665; `synth_system(..., attested_images=False)` :1671; `_default_synthesizer` :1720;
  `human_attestations_of(ledger, images=None)` :3455; `_attestation_leak_check` += `_scope` :3492; `_gate` += `attested_predicates` :2594
  (orden `leak → att → pc → fig → [web] → attested`); `ATTESTED_*` constantes junto a :3012 (`ATTESTED_TOOL_UNAVAILABLE_GATE/PANEL`);
  `_attested_stage` (K.1) tras `stage.council.ledger` :3882; `_attested_for_panel`/`_audit_accepts_attested`/`_attested_panel_kwargs`
  molde :3174-3240 y llamadas :4408/:4477; `_attested_fill` (seen_by_lenses, n_readings, vision, cost_projection) molde `_figures_fill`;
  `frozen["attested_images"]` junto a :4678; `frozen_council.human_attestations` += `n_images`/`images_delivery` :4559;
  `_frozen_ledger_view` += imágenes :3617; `epistemic_summary` += `attested_*` :4830; `_agents_invoked(attested=)` :892; `_token_usage`
  += `attested_images` y `by_model[*].attested_vision` :2226; `build_thread_context` += `parent_attested_images` :1185 y
  `council_summary.n_attested_images`; `db.plan_add_event(..., heartbeat=False)` en los eventos de plan que runs emita — ninguno: runs
  emite `run_events`) · `smoke_run_pipeline.py` (+≥ 48) · `smoke_thread_context.py` (+≥ 6) · `smoke_competence.py`/`smoke_run_recovery.py`
  sólo si un aserto se rompe por llaves nuevas.
- **F5 · `db.py` + `app.py` + smokes HTTP/DB** — dueño de: `rag_index/query_service/db.py` (tabla `plan_attested_images` junto a
  :148/:246; funciones (F.2); `plan_add_event(..., heartbeat=True)` :776; `attested_schema_state`; `attested_images_usage`) ·
  `rag_index/query_service/app.py` (7 rutas (L.HTTP) junto a :1495 y :1827; `LedgerDecisionBody.images?`/`LedgerBody.images?`/
  `patient_material_acknowledged?` :1773-1783; `council_ledger` valida/sella/flags/evento (J) :1827; `_plan_view.attested_images`
  :1700; `ATTESTED_EXPOSE_HEADERS` + :132; `X-Content-Type-Options: nosniff` también en `get_figure_bytes` :1620 (aditivo, declarado);
  `_AttestedUsageAccumulator` molde :2282 y `/usage` :2560; `view_rule`; handler de subida `async def` con stream acotado +
  `run_in_threadpool` (C.2)) · `smoke_attestations_http.py` (NUEVO) · `smoke_attestations_db.py` (NUEVO) · `smoke_council_http.py`
  (+4) · `smoke_usage_http.py` (+3) · `smoke_runs_list_http.py` (+1).
- **F6 · `council.py` + `council_jobs.py` + smokes del consejo** — dueño de: `analysis/scripts/lib/council.py`
  (`R2_PREAMBLE_ATTESTED_IMAGES` sufijo condicional en `payload_r2` :620; `apply_ledger_decisions(..., images=None)` :1605 con error
  `images_without_aporto`; `judge_coverage` += `n_with_image` :1717 sin cambiar la cobertura; `summary_for_thread += n_attested_images`
  :1969) · `rag_index/query_service/council_jobs.py` (`_inherited_criteria` :182 propaga `n_attested_images`) · `smoke_council.py`
  (+≥ 8) · `smoke_council_jobs_db.py` (+2).
- **F7 · `record_pdf.py` + `smoke_record_pdf.py`** — dueño de: `rag_index/query_service/record_pdf.py` (`KEY_BORN['attested_images']
  = '1.14'` :119; `SECCIONES` 54 :150; `ORDEN_SECCIONES` :207; `_section_imagenes_aportadas` molde :1224 SIN `_thumb`; `_section_gate`
  :1481/:1495; asserts :234-236 intactos; `RENDERERS`) · `smoke_record_pdf.py` (≥ 72).
- **F8 · doctrina + operación + vivo** — dueño de: `docs/decisions/0086-imagenes-atestiguadas-del-laboratorio.md` (este documento
  con conteos «F9 mide» y la fecha de la decisión de almacenamiento cuando Emmanuel confirme OE1) · `docs/decisions/README.md` (fila
  0086 con la redacción de Q.3) · `CLAUDE.md` §7 (viñeta Q.4) · `rag_index/query_service/docker-compose.query.yml` (bloque ADR-0086
  tras el de 0084: 14 `${VAR:-default}` + comentario «MINIO_* arriba (ya existen); WITT_ATTESTED_MINIO_*_KEY y WITT_ATTESTED_DIR: never
  git» + `volumes:` con `attested_private:/app/attested_private` COMENTADO e instrucción) · `rag_index/query_service/README.md` (tabla
  de rutas +7; tabla de env +14; sección «Imágenes atestiguadas del laboratorio (ADR-0086)»: privacidad, quién ve qué, volumen o
  bucket y qué pasa sin ellos, versioning OFF, respaldo como límite, contrato 1.14, `/usage.attested_images`, gates) ·
  `analysis/scripts/smoke_live_attestations.py` (NUEVO, EN VIVO: `--probe-storage [--backend local|minio]` sin escribir · `--upload
  <png> --plan <id>` contra el servicio con sesión · `--exif-check <sha>` baja por la puerta y verifica 0 APP1/tEXt · `--judge <model>
  --api <api> --image <sha>` una llamada con bloque ATTESTED (imprime usage) · `--dry-run` (Gates); JSON sin secretos a
  `analysis/outputs/live_attestations_<fecha>.json`; rehúsa correr sin llave; jamás toca la BD).
- **F9 · integrador** — sin archivos propios: rebase sobre `contract-1.13-frozen`, retira stubs, cose: `frozen.attested_images.items[].
  sha256 == plan_attested_images.sha256 == sha entregado a lentes ⊇ audit.panel[].saw_attested.sha256s`; `stage.audit.judge.attested_sent
  == saw_attested.n` por (reviewer, lens); `epistemic_summary.attested_n_images == frozen.attested_images.n_attached`;
  `record_pdf.pdf_sections_cover(frozen_keys) == {missing [], extra []}` (54); conjunción de `_gate` en el orden declarado (Q.2); corre
  TODOS los smokes con la máscara (una `.db` y un `WITT_ATTESTED_DIR` TMP por smoke), verifica `urlopen` 0 y `mcp_cache` byte-idéntico,
  `grep -c 'ATTESTED prior art' CLAUDE.md ≥ 1`, compose/README ⊇ 14 env (bidireccional con `ENV_SPECS`), `grep attested precedent.py` = 0,
  `grep attested council_index.py` = 0, corre `witt-webapp/tools/parity_check.py` EN LECTURA (esperados: `[registro] attested_images`,
  `[rutas] 7`, `[etapas] 4 + 4 plan_events`, `[pdf] 0`), sustituye «F9 mide» por conteos, etiqueta `contract-1.14-frozen`.
- **Revisores (3, en paralelo sobre el árbol de F9):** R1 doctrina (clase ATESTIGUADA en cuatro sedes: `human_attestations`, panel,
  frozen, PDF; ¿entra un byte o un caption por algún camino a `evidence`, `citations`, el precedente, el índice del consejo, el
  snapshot del hijo como evidencia?; tres estados; §7 compuertas humanas hechas código; «lo que NO se hace») · R2 corrección
  (413 con 0 bytes leídos y con `chunked`; strip byte-idéntico en píxeles y CRC; sha recalculado en gate/GET/copia; kill-switch byte a
  byte con EXACTAMENTE 3 excepciones; withdraw bajo kill-switch y sellado; cascada; `heartbeat=False`; Postgres SQL; no-hang; fakes
  sin red; portabilidad sin `mcp_cache`) · R3 contrato y paridad (formas de (L) vs código vs lista «tipar y pintar»; vocabularios
  congelados; 54 secciones vs 53+1 llaves; fixtures 1.14 generables por código; `route.ts` allowlist). **Corrector:** aplica los
  hallazgos marcándolos *(corrector)*, re-corre los gates, actualiza conteos.
- **Webapp (OTRO workflow, contra `contract-1.14-frozen`):** **W0** `src/app/api/[...ruta]/route.ts` (allowlist de cabeceras de
  respuesta `etag, content-disposition, x-witt-*`; `if-none-match` hacia adentro; precheck `content-length` → 413 con `state`;
  vitest del proxy) — PRIMERO: repara 0083 · **W1** `types.ts` + `client.ts` (O.2) + `src/lenguaje/atestiguado.ts` +
  `tests/atestiguado-lenguaje.test.ts` · **W2** `Preguntar.tsx` (Consequences 3-4) + `tests/m3.test.tsx` (formulario bloquea sin
  consentimiento/`third_party_ack`/`patient_material` decidido; `FormData` con los campos y `requirement_id`; re-codificado cliente
  con fake `createImageBitmap`; 413/415/422/429/503 glosados; `cuerpo()` manda `images[]` y `patient_material_acknowledged`; Aprobar
  deshabilitado sin acuse; vista previa sólo tras 200; retirar pide razón; Reforzar lista `parent_attested_images` y hereda) · **W3**
  `Hoja.tsx` + `Visuales.tsx` (Consequences 5-9) + `tests/hoja.test.tsx` (tres estados; 403 «privada: sólo su autor»; 410 «RETIRADA…»;
  404 «permanente»; 409 «no cuadran»; placa paciente con acuse; `attested_images_not_cited` fallido pintado inadmisible;
  `attested_readings` con placa JUICIO; «el sintetizador NO la vio» desde `delivery`) · **W4** `Traza.tsx` + `ListaCorridas.tsx` + M8 +
  tests (4 casos exactos + 4 `plan_events`; latido por imagen; summary kill-switch en voz alerta; chip; bloque [E]) · **W5**
  `tools/parity_check.py` (superficie ATESTIGUADO: vocabularios de `attestations.VOCABULARY` + `verify_output.ATTESTED_CHECK_STATES_*` +
  `runs.ATTESTED_DECLARED_EXCEPTIONS` leídos del código ↔ unions ↔ tablas ↔ fixtures; 7 rutas; `attested_images` ↔ tipos ↔ Hoja ↔
  `SECCIONES` 54; `PDF_NESTED` ampliado; 8 eventos) · `tools/parity_debt.json` (0 líneas nuevas) · `tools/gen_fixtures.py`
  (`CONTRATO '1.14'`; `ENV_ADR_0086` quitadas del proceso patrón :185-194; `WITT_ATTESTED_DIR = TMP` fijado tras el pop — jamás la raíz
  real; `FakeMemoryStorage` inyectado; los bytes sintéticos desde `attestations.synthetic_fixtures()` del backend, nunca a mano).

**Fixtures 1.14 que la webapp necesitará (los genera `gen_fixtures.py` contra `contract-1.14-frozen` con el código REAL y stubs de
sintetizador/panel/consejo; `MANIFIESTO.md` declara que TODOS los bytes son sintéticos):** los existentes regenerados (todos ganan
`attested_images {state …}`, `deterministic_checks.attested_images`, `saw_attested` por fila; el SINTÉTICO pre-1.1 sigue sin ellos) ·
`atestiguadas-completo.json` (ledger aprobado: `aporto` + 1 imagen PNG, `knowledge_now` + 1 JPEG con EXIF sintético stripped, 2 lentes
las vieron, `attested_readings` en ambas, `attached_by_is_uploader true`) · `atestiguadas-material-paciente.json` (bandera
`human-upload`, acuse `true`, `view_rule 'author-only (patient-material)'`) · `atestiguadas-retirada-antes-de-correr.json`
(`withdrawn-before-run`, no entregada) · `atestiguadas-bytes-missing.json` (índice `servable 'bytes-missing'`) ·
`atestiguadas-cita-inadmisible.json` (`attested_images_not_cited` fallido, `reasons` visible) · `atestiguadas-fuga-caption.json`
(`attestation_identifier_leak` con `_scope`) · `atestiguadas-kill-switch.json` (3 excepciones) · `atestiguadas-vision-apagada.json`
(`WITT_ATTESTED_VISION=0`) · `atestiguadas-heredada.json` (`ledger_state 'inherited'`, `inherited_from`) · `atestiguadas-sin-ledger.json`
(`not-applicable (no-ledger)`) · `attestations-index-plan.json` / `attestations-index-run.json` (con `viewer_may_view` en ambos valores) ·
`attestations-bytes-403.json` / `-404.json` / `-409.json` / `-410.json` / `-503.json` (sobres tipados) · `attestations-upload-201.json` /
`-400-*.json` / `-413.json` / `-415.json` / `-422.json` / `-429.json` / `-503.json` · `attestations-withdraw-200.json` /
`-409.json` · `attestations-inherit-201.json` / `-403.json` · `eventos-atestiguadas.json` (los 4 `stage.attestations.*` + `stage.audit.judge`
con `attested_sent` + `stage.council.ledger` con `n_images`) · `plan-eventos-attestation.json` (los 4 `attestation.*`) ·
`usage-attested.json` · `thread-context-parent-attested.json` · `attested-vocabulary.json` (para el test de `atestiguado.ts`).

## Qué NO se hace y por qué NO es deuda

(a) **OCR / extracción de cifras de la imagen** — §7 «figure-only NOT asserted» y la decisión tomada: lo que la imagen dice es
juicio de ≤ 2 lentes, jamás medición. (b) **Embeber en el PDF, presigned URLs, URL pública, Files API, redistribución** — atestiguado
privado por decisión y ADR-0073 (el PDF es el único derivado que circula). (c) **Identificación de personas / reconocimiento facial /
redacción visual automática** — AUP de Anthropic («cannot be used to name people in images», verificado hoy) y §7; la desidentificación
es DECLARADA por la persona. (d) **Imágenes como evidencia, cita, cobertura o precedente** — `citations[].kind` no gana literal,
`precedent.serialize_disjoint` intacto (`grep attested precedent.py` = 0), `judge_coverage` no cambia, predicado duro
`attested_images_not_cited`. (e) **Imágenes en comentarios (ADR-0077)** — otra semántica (B.4). (f) **Retención automática /
sweeper / TTL** — contradice el registro append-only y «ningún agente muta unilateralmente» (H.5; OE6). (g) **Recodificación o
miniaturas server-side (Pillow en lib)** — rompería stdlib-puro y cambiaría los píxeles que las lentes juzgan; el cliente reduce
(C.6). (h) **DICOM / TIFF / OME / `.tif` de la DATA INAMOVIBLE** — ADR-0083 (N)(g), brief §7 «fuera de esta fase». (i)
**`evidence_kind 'attested-image'` para el consejo** — el consejo pide evidencia, no imágenes de la persona. (j) **Migración
local → MinIO** — CLI declarado; se construye cuando OE1 lo pida. (k) **Clave content-addressed compartida entre planes con
refcount** — un retiro que NO borra bytes porque otro plan los referencia sorprende a quien retira y acopla la privacidad de dos
personas (A/B sobre C, ambos jueces); a ≤ 8 imágenes por plan la dedup no vale nada. (l) **SigV4 stdlib** — ~150 líneas de
criptografía propia para un SDK ya instalado y pineado. (m) **Tocar `SYNTH_TOOL.description`** — cláusula condicional en
`synth_system`; evita una tanda de held-out (0086.1 si Emmanuel quiere cobertura a nivel tool). (n) **Backfill de registros <
1.14.** (o) **`WITT_ATTESTED_PANEL_REQUIRES_CONSENT`** (A) — redundante: sin consentimiento declarado no existe la fila. (p)
**304/If-None-Match en la puerta de bytes** — con `Cache-Control: no-store` el navegador no revalida; prometerlo es humo (juez 2).
(q) **`author` = uploader ∪ autor del plan ∪ autor de la corrida** (C) — ampliaría el acceso sin el consentimiento de quien subió.
(r) **Fallback minio → local en silencio** (B) — reubicaría material privado en disco efímero cuando el operador pidió MinIO. (s)
**Registrar consentimiento de una segunda persona sobre el mismo sha** — UNIQUE `(plan_id, sha256)`; declarado (C.5). (t)
**Familia `attested` en `SEARCH_DISPATCH` o etapa en `TOKEN_STAGES`** — no busca ni gasta modelo. (u) **Cambiar `POST /runs` ni
`run_images`/`POST /runs/{id}/images` del brief** — sustituidos por el ledger del plan (Q.3).

## Contradicciones entre diseños/jueces y cómo se resolvieron (síntesis)

| Tema | A (ganador) | B | C | Jueces | DECISIÓN |
|---|---|---|---|---|---|
| Transporte | base64 en JSON, 4 por petición | multipart + `python-multipart` | multipart, UNA por petición, 413 por `Content-Length` | **DIVERGEN**: juez 1 → B/C; juez 2 → A (sin dependencia nueva), pero «ninguno logra el 413 antes de leer» | **multipart, UNA imagen por petición** (dependencia ya de la casa; memoria; aislamiento §6) + handler `Request`-only con `Content-Length` precheck y stream acotado re-inyectado + `run_in_threadpool` (C.2) — el caveat del juez 2 resuelto y MEDIDO |
| Raíz local por default | `<mcp_cache>/attested-private` | `<repo>/attested_private` | `<repo>/attested_private` + volumen | unánime: B/C (caché ≠ almacenamiento) | **`<repo>/attested_private`** + `.gitignore` + volumen comentado + `durability.note` |
| MinIO sin credenciales | 503 | cae a `local` declarado | 503 | unánime: A/C | **503 `attested-storage-unavailable`**; jamás fallback |
| Quién ve los bytes | author-only + `share_scope` por quien sube + `TEAM_VIEW` | env `author` | env `team` por default; paciente author-only | unánime: A (+ injerto C para paciente); RECHAZO de «autor = uploader ∪ plan ∪ corrida» | **A + paciente SIEMPRE author-only** |
| `SYNTH_TOOL.description` | condicional en `synth_system` | idem | incondicional + held-out | unánime: A/B | **no se toca**; cláusula condicional |
| Imagen del padre en el hijo | «no se hereda sola» (LG5) | sólo conteo | `parent_attested_images[]` + `inherit_from_run` por cualquier aprobador | unánime: C para metadatos; juez 2: inherit SÓLO por el uploader | **metadatos en `thread_context` + `POST …/inherit` sólo `sesión == uploaded_by`, copia por plan, cascada al retirar** |
| Firma minio-py | `metadata=` + pin `<8` | sin pin | `user_metadata=` (master) | unánime: A (7.2.20 verificado) | **A**; `probe()` registra `sdk_version` |
| GIF | aceptado | rechazado | fuera por default, env | unánime: C | **fuera por default**, `WITT_ATTESTED_ALLOWED_MEDIA` |
| Layout de almacenamiento | `<plan_id>/<sha>` | `<plan_id>/<sha>.<ext>` | content-addressed + refcount | unánime: A/B | **`<plan_id>/<sha256>.<ext>`**, sin refcount; inherit COPIA |
| Strip que falla | 400, no se guarda | no definido | 422, no se guarda | unánime: A/C | **422 `metadata-strip-failed`, nada se guarda** |
| Withdraw bajo kill-switch | vivo | no dicho | no dicho | unánime: A | **vivo** (también con plan sellado) |
| Material de paciente | consented + `deidentified_declared` | `consent_text ≥ 20` | + acuse `patient_material_acknowledged` al aprobar | unánime: la UNIÓN + acuse (C) | **las tres declaraciones + acuse literal + bandera LISTA**; env `WITT_ATTESTED_PATIENT_MATERIAL` para Fase I (OE4) — default `0` (orquestador): negar hasta política escrita |
| Sin consejo | `not-applicable` al correr | 409 al SUBIR | `not-applicable` al correr | juez 1: B (fallar temprano) | **409 `attestations_require_ledger` al subir** + `not-applicable (no-ledger)` al correr |
| Cupo por plan | cuenta retiradas | vivas | vivas | juez 1: retiradas bloquean | **filas VIVAS** (+ tope de MB) |
| Fixtures | binarios commiteados + MANIFEST | binarios + generador | generados en el smoke con `struct` | juez 2: cualquiera; preferible por código compartido con `gen_fixtures` | **generados por CÓDIGO (`synthetic_fixtures`) desde la lib; MANIFEST de texto; cero binarios** |
| Proyección Anthropic tier alto | 1 568 para 1600×1200 | 1 419 (1200×900) | 4 784/1 564 (4032×3024) | juez 2: A subestima ×1.6 | **recalculado con `models.vision_tokens`: 2 494 (alta) / 1 564 (estándar)** |
| `Cache-Control` + 304 | `no-store` + 304 | idem | idem | juez 2: 304 inalcanzable | **`no-store` sin prometer 304**; `ETag` informativo; `nosniff` (juez 1) |
| Bandera `emitted_by` | — | string | lista | juez 2: lista (council.py:1569, `.join`) | **lista `['attestations (human-upload)']`** |
| Bitácora de acceso | — | — | declarado no hecho | juez 2: barato y única prueba | **`attestation.bytes_served` en 200, sin latido** |
| Licencias declaradas | `figures.LICENSES + all-rights-reserved` | vocabulario propio | vocabulario propio | juez 2: `zfin-display-only/unknown` sin sentido | **`LICENSES_DECLARED` propio (10)**; no gatea |
| Consentimiento hacia terceros | — | riesgo declarado | — | ambos jueces: falta el aviso literal | **aviso literal + `third_party_processing_acknowledged` obligatorio** (C.4) |
| Proxy Next | — | — | — | ambos jueces: descarta cabeceras; bufferiza | **W0 `route.ts`**: allowlist + precheck 413 (repara 0083) |
| Rutas | 5 | 6 | 7 | — | **7** (inherit como puerta propia; `POST /runs` intacto) |

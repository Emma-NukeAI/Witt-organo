# HANDOFF — Agente constructor de la webapp · Witt × Organogenesis

> **Fecha:** 2026-08-10 · **De:** el backend (`Emma-NukeAI/Witt-organo`, ADR-0043–0054) · **Para:** la sesión
> que construya la webapp. Pegar el prompt corto del final al iniciar la sesión en
> `c:/Users/Emmanuel/dev/witt-ui-lab`; este documento es el estado + la especificación.

---

## Contexto

El diseño de la UI está TERMINADO como especificación en `witt-ui-lab` (no se rediseña — se implementa).
El backend que ese diseño pedía **ya existe, está desplegado y verificado en producción**: los 4 tapones
cerrados, los 6 bloques de `witt-ui-lab/05-backend/faltantes-backend.md` entregados (ADR-0043–0053), y el
ciclo completo ejercido en vivo (ADR-0054): corridas auditadas por panel en el 100%, registro congelado
persistido en Postgres, ingesta human-gated con push-back a git funcionando, y capa de precedente. Existe
**una corrida real cerrada** (`a361f566d67f470eb195c78b2b3cb7b6`, wt1a/pronephros) — tu primera hoja.

Tu trabajo: construir la webapp sobre estos contratos. Es la ÚNICA superficie que se expondrá al internet
(ADR-0047 d.5); todo lo demás vive en la red interna de Dokploy.

## Lo que hay que leer antes (en este orden)

| Qué | Dónde |
|---|---|
| El contrato de lectura del registro congelado | `witt-ui-lab/01-mapa/registro-congelado.md` |
| Contratos de datos + superficie API propuesta | `witt-ui-lab/00-fuentes/UI-DATA-CONTRACTS.md` |
| Los bocetos/módulos M1–M9 y el lenguaje visual | el resto de `witt-ui-lab` (recórrelo completo) |
| **La API real** (endpoints, auth, deploy, trampas) | `../witt-organogenesis/rag_index/query_service/README.md` |
| Decisiones vinculantes del backend | `../witt-organogenesis/docs/decisions/0043–0054` (léelos todos; son cortos) |
| La forma real del registro congelado v1.1 | `../witt-organogenesis/rag_index/query_service/runs.py` (bloque `frozen`) |
| Riesgos de render (derivados limpios, print) | `witt-ui-lab/04-abierto/riesgos-y-huecos.md` |

**Regla de verificación (la misma que este backend heredó y que le encontró 10/10 hallazgos a su
antecesor):** no des por buena ninguna afirmación de estos documentos — ni de ESTE — sin verificarla
contra el código o el servicio vivo. La prosa se pudre; el código no miente.

## La API real (viva hoy, `witt-query-service`, puerto interno 8078)

Auth: `POST /login {username, password}` → bearer token (sesiones expirables; 5 cuentas planas; `role` =
`rater_profile` medico|dev, NO es nivel de permiso). Todo lo demás lleva `Authorization: Bearer <t>`.

| Endpoint | Para |
|---|---|
| `GET /health` | liveness (sin auth, sin spend) — healthcheck, no para UI |
| `GET /status` (alias `/rack/status`) | StoreStatus 9 campos, NO-SPEND, TTL 60s — el indicador de cabecera puede refrescar por siempre |
| `GET /query?q=&k=` (alias `/rack/search`) | el sobre ADR-0043: `{degraded, n_hits, hits[], last_error, index_version, store_version}`; hits CORPUS-* traen `record{verification_tier, approval_status, approved_by, data_niche}` |
| `GET /resolve?key=` (alias `/rack/resolve`) | VerifiedRecord completo + `tier` SIEMPRE junto a `tier_weight` (peso de calibración, NO fuerza probatoria) |
| `GET /raw?key=&filename=` | drill al crudo (URL presignada MinIO o source_url+sha256) |
| `POST /runs {question, entities[]}` | encola corrida (async); estados `queued→running→awaiting_closure→closed` + `failed`/`cancelled` |
| `GET /runs` · `GET /runs/{id}` | listado / estado con `heartbeat_age_s` + `heartbeat_stale` |
| `GET /runs/{id}/stream` (SSE) · `GET /runs/{id}/events?after=` | traza viva y replay — LEEN LAS MISMAS FILAS; no pueden divergir |
| `GET /runs/{id}/record` | **el registro congelado v1.1** — la fuente única de la hoja, el PDF y la bitácora |
| `POST /runs/{id}/cancel` · `POST /runs/{id}/close` | cancelación de primera clase · cierre explícito (congela; requisito para precedente) |
| `GET /precedent/search?q=&k=` | corridas CERRADAS por relevancia; `admissible_as_evidence: false` estructural; scorer declarado |
| `GET /artifacts` + `/artifacts/report/{name}` + `/artifacts/run/{set}/{name}` | históricos ADR-0046: 48 HTML + runs con `instrumented: false` |

## Las reglas epistémicas de render (la tesis; NO son negociables)

1. **Nada se renderiza sin su estado epistémico.** `retrieval.mode` es un enum de 4 literales
   (`semantic | degraded-dense-failed | reduced-by-config | not-measured`) — cada uno tiene SU dibujo;
   ninguno se hereda de otro; `not-measured` pinta el peor caso. `last_error` es el diagnóstico
   ("Neo4j inalcanzable"), no solo la banda.
2. **Degradado+vacío ≠ sano+vacío.** Son conclusiones OPUESTAS (hueco real de la DI vs buscador roto) y
   se dibujan distinto. El sobre siempre lo dice (`degraded` + `n_hits: 0`).
3. **Confianza en tres estados** (`confidence.state`): valor medido vs `absent-not-calibratable` — un
   null jamás se pinta como limpio. `confidence_by_subclaim` se muestra desglosado, NUNCA promediado.
   **`pass1`/`pass2`/`delta` son primera clase**: cuando el fallback disparó hubo DOS respuestas; el
   delta es el dato más informativo de la corrida.
4. **`fallback.trigger`** (`structural | confidence | null`) se declara — cuál decidor disparó la Ruta B.
5. **`absence_kind`**: `no-evidence-retrieved` (el store no sabe) y `evidence-of-no-effect` (evidencia
   de efecto nulo) son estados epistémicos opuestos — renders distintos.
6. **El panel de auditoría se muestra como TABLA** (reviewer/family/lens/verdict/caught/correction), con
   `source_vocabulary` visible y jamás colapsado a un semáforo; `panel_incomplete: true` y los jueces
   `errored` se ven. Los 4 vocabularios históricos conservan el suyo.
7. **Citas: números = evidencia, letras = precedente.** El precedente lleva SIEMPRE su
   `admissible_as_evidence: false` — se muestra como prior art, jamás como evidencia.
8. **`question_matches_run: false` ⇒ la hoja NO se dibuja** (identidad de bundle, ADR-0044).
9. **Históricos con `instrumented: false` se marcan como no-instrumentados** — nunca como limpios. Va a
   ser el estado más frecuente de la bitácora al inicio; el diseño ya lo contempla.
10. **`cancelled` ≠ `failed`** (un cancelado que se ve muerto miente) y **`heartbeat_stale`** distingue
    una corrida trabajando de una atorada.
11. **`token_usage.estimated_cost_usd` se etiqueta como PROYECCIÓN** (los tokens son medición; los
    dólares no) — `cost_class` viene en el registro.
12. **Exportar = PDF generado en servidor desde el JSON congelado. Nunca `window.print()`** — el derivado
    fuera de pantalla sale limpio y eso es la fuga que este producto existe para cerrar (el PDF server-side
    es backend pendiente: constrúyelo como parte de M4 o decláralo bloqueado, no lo simules).

## Lo que NO existe todavía (no lo simules — decláralo)

- **`ratings[]` / consenso (M5):** el registro congelado tiene las zonas definidas (mediciones inmutables ·
  ratings append-only) pero los endpoints de calificación NO existen. Se construyen como extensión del
  backend cuando M5 lo pida (avisar a Emmanuel; es un bloque chico sobre `db.py`).
- **`POST /runs/plan` (el Plan condicional de M3):** no hay planner; el diseño lo pide condicional con
  proyecciones etiquetadas. Bloqueado hasta su bloque.
- **`/rack/node/{id}` (browse del grafo):** la operación no existe en ninguna puerta.
- **Correo M9 (Resend):** no existe.
- **Alta/reset de usuarios por HTTP:** NO existe A PROPÓSITO (asimetría local de Emmanuel, ADR-0048).
- Donde el diseño espere un campo que el registro v1.1 no trae: se reporta (el contrato es documento
  vivo), no se inventa (la regla `no inventes campos` del handoff original sigue vigente).

## Cómo desarrollar (loop local) y cómo desplegar

- **Dev local:** el query service corre local desde el checkout hermano: venv con
  `rag_index/query_service/requirements.txt` → `uvicorn app:app --port 8078` en esa carpeta → SQLite
  automático + `python seed_users.py init` local + modo sparse offline (sin `NEO4J_URI` el `/status`
  reporta `OFFLINE` honesto — perfecto para desarrollar los estados degradados). La UI se desarrolla
  contra `http://localhost:8078`.
- **Deploy (cuando haya algo que ver):** servicio Dokploy nuevo en el MISMO proyecto, red interna,
  hablándole a `witt-query-service` por nombre interno; la webapp es la única con dominio público
  (Traefik + TLS). `WITT_CORS_ORIGINS` del query service = el origen de la webapp. El patrón de compose
  y de redes está en `docker-compose.query.yml` (imítalo). **Watch Paths desde el día uno** (lección
  ADR-0054: un push ajeno no debe reconstruirte a media operación).

## Decisiones a consultar con Emmanuel ANTES de empezar (Método 2)

1. **Dónde vive el código de la webapp:** repo privado nuevo `Emma-NukeAI/witt-webapp` (recomendado:
   separación limpia lab-de-diseño / app, autodeploy propio) vs subdirectorio en un repo existente.
2. **Stack de frontend**, SI el lab no lo fija ya (léelo primero; si lo fija, se respeta).
3. **El dominio público** de la webapp (para Traefik/TLS y CORS).

## Restricciones duras

- **`witt-organogenesis` es SOLO LECTURA.** Los gaps del backend se reportan a Emmanuel, no se parchan
  desde la sesión de UI. **`witt-ui-lab` (los diseños) tampoco se redisenan** — se implementan; las
  fricciones de implementación se reportan.
- **Método 2:** decisiones de producto/arquitectura se consultan con Emmanuel; la implementación es
  ingeniería normal.
- **Cero secretos en git** (tokens, contraseñas, URLs con credenciales). CLAUDE.md §7 aplica.
- **Commits chicos y verificables.** Los gates del proyecto son deterministas; los tuyos también
  (el smoke de UI mínimo: los estados epistémicos de render con fixtures del registro v1.1 real).

## Orden recomendado (prueba pequeño antes de armar bien)

1. **M1 — shell + login + StoreStatus en cabecera** (contra el dev local; el status NO-SPEND refresca).
2. **M4 primero como LECTOR: la hoja del registro congelado**, renderizando `GET /runs/{id}/record` de la
   corrida real `a361f566…` (existe, está cerrada, tiene panel con REVISE y confianza ausente — ejercita
   los estados difíciles de una vez). Criterio de aceptación: la hoja muestra visiblemente decision_state,
   el panel-tabla, confidence 3-estados, fallback.trigger, citas numéricas y token_usage etiquetado.
3. **M2 — el Rack** (`/query` con su banda de degradación + `/resolve` + `/raw` + `/status`).
4. **M3 — someter corrida + traza viva SSE** (+ cancel + latido) y **M6 — bitácora/replay + precedente**
   (leen la misma bitácora y el índice de históricos).
5. **M7 — el gate de ingesta** (`/pending`, `/pending/{sid}` detalle completo, approve/reject con razón,
   `/actions`) — contra el ingest service.
6. **M8 — usage agregado** · **M5/M9** cuando sus bloques de backend existan.

## Cómo reportar

Al cerrar cada milestone: qué quedó, qué gap del contrato apareció (campo faltante, forma distinta), y qué
decisión necesita Emmanuel. El backend responde del otro lado — el contrato es vivo en ambas direcciones.

---

## PROMPT CORTO (pegar tal cual en la sesión de `witt-ui-lab`)

> Vas a construir la webapp de Witt × Organogenesis. El diseño ya está terminado como especificación en
> este repo (`witt-ui-lab`) — no lo rediseñes, impleméntalo. El backend que el diseño pedía ya existe,
> está desplegado y verificado (ADR-0043–0054 en `../witt-organogenesis`).
> Lee y ejecuta el handoff completo: `../witt-organogenesis/docs/HANDOFF_UI_BUILDER.md` — orden de
> lectura, la API real, las 12 reglas epistémicas de render (la tesis del producto), lo que NO existe
> todavía (no lo simules), el loop de desarrollo local, y el orden de milestones.
> Restricciones desde ya: `../witt-organogenesis` es SOLO LECTURA · Método 2 (las decisiones se consultan
> con Emmanuel — empieza por las 3 marcadas en el handoff) · cero secretos en git · commits chicos con
> gates deterministas · no des por buena ninguna afirmación de los documentos sin verificarla contra el
> código o el servicio vivo.
> Primer entregable: M1 (login + StoreStatus) y la hoja del registro congelado de la corrida real
> `a361f566d67f470eb195c78b2b3cb7b6` renderizada con sus estados epistémicos visibles.

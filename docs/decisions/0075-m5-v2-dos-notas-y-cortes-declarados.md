# ADR-0075 — M5 v2: dos notas separadas, anclas con palabra, y los cortes que declaran de qué descansa el ECE

- **Status:** Accepted — 2026-08-26. Origen: el banco de calibración v1 volvió de los tres médicos
  (Nat 30/30, Martín 11/30, Marcelo 11/30) y su análisis
  (`reports/2026-08-26_banco-calibracion-rescate-plan_v1.html`) midió QUÉ del instrumento funcionó y
  qué no. Decisión de Emmanuel el mismo día: **no se re-corre el banco ni se les pide una segunda
  ronda** — los médicos tienen otras actividades; la calificación tiene que salir de las corridas que
  ellos ya van a hacer en la webapp, y el back sólo se toca donde la UI ya lo consume.
- **Relates:** ADR-0064 (M5 ratings append-only + `/calibration` con poder declarado — este ADR lo
  extiende, no lo reemplaza) · ADR-0058 (`APPROVE_DECLINE`: la declinación honesta APRUEBA) ·
  ADR-0051 (`absence_kind`: no-evidence-retrieved ≠ evidence-of-no-effect) · ADR-0056 (procedencia
  DERIVADA en el servidor) · ADR-0005/0030 (poder declarado; "aggregate-captured" ≠ "satisfied") ·
  ADR-0037/0038 (el juez no es verdad-terreno; el ancla es humana o determinista).
- **Affects:** `rag_index/query_service/db.py` (columna `note_question` + migración) ·
  `app.py` (`RatingBody.note_question` + tope 4000) · `calibration.py` (tres bloques paralelos +
  tres declaraciones en `OUTCOME_MAPPING_DECL`) · `consulta_sistema.py` (denominador honesto del
  corpus) · `smoke_ratings_calibration.py` (29 → **39**) · witt-webapp:
  `src/api/types.ts`, `M5Calificaciones/{FormularioCalificacion,BloqueCalificaciones,Calibracion}.tsx`,
  `tests/m5.test.tsx` (173 → **177**). **Cero mutación de la DATA INAMOVIBLE.**

## Context

El banco v1 no fracasó por los revisores: fracasó el instrumento, y quedó medido cómo.

1. **Los tres ejes de INPUT no midieron un constructo compartido.** Corregido por azar con las
   frecuencias reales, kappa: objetividad −0.099, contexto −0.004, especificidad −0.140. En
   especificidad los tres pares tienen Spearman NEGATIVO (−0.121, −0.313, −0.289): los revisores
   ordenaron las preguntas en sentidos contrarios. El piso de azar real fue ~0.50 y no 0.33 porque las
   anclas bajas estaban MUERTAS ("Vaga" 0 de 33 usos, "Fuera de alcance" 1 de 33, "Genérica" 2 de 33).
2. **El texto libre fue lo único que produjo diagnóstico accionable.** Las 68 celdas de comentario
   dieron TODOS los hallazgos del reporte; los cinco ejes categóricos casi nada. Y la atribución sólo
   fue posible porque el banco tenía DOS columnas separadas: `P_comentario` (sobre la pregunta) y
   `R_que_falta` (sobre la respuesta). M5 tenía UNA sola nota para los dos ejes: una regresión sobre
   el único canal que demostró servir.
3. **El instrumento no tenía dónde poner lo que la gente quería decir.** Las tres veces que alguien
   marcó "Fuera de alcance" significaba otra cosa: "muy ambiciosa, la partiría en 2" (tamaño),
   "es bueno cuestionarnos la arquitectura" (meta-gobernanza, y era elogio) y "me gustaría entender de
   dónde surgió esta pregunta" (procedencia).
4. **`rating_input` nunca ha entrado al ECE.** Verificable: no aparece en `calibration.py`; el mapeo de
   outcomes es enteramente `rating_output`. Se le cobraba al calificador una decisión que no alimenta
   nada, y encima era la peor medida.
5. **La severidad del calificador decide la etiqueta.** Medido en el banco: dos revisores etiquetaron
   100% positivo y la tercera 69%. Con UN calificador por corrida —el caso modal, `m5-cierre`— la
   "mayoría estricta" es una perífrasis de esa persona. Hoy el 100% del dataset de producción es una
   sola autocalificación del autor.
6. **La declinación honesta envenena el ECE.** `calibration.py` no mira el veredicto del panel. Una
   `APPROVE_DECLINE` (ADR-0058) trae confianza baja POR CONSTRUCCIÓN y es la conducta correcta; si el
   humano la califica alto, el par entra como error máximo justo cuando no hubo error.

Y de la junta con Natalia (2026-08-26): las preguntas abarcaban demasiado para una sola respuesta; los
listados de genes salían incompletos; y **"sentimos una inclinación en la balanza a pronefros como a
genética"**.

## Decision

**(1) DOS notas, no una.** `note` queda re-clavada a la RESPUESTA; nace `note_question` para la
PREGUNTA. Las dos opcionales y las dos **SIEMPRE VISIBLES**. La visibilidad incondicional no es un
detalle de UI: se corrió el disparador condicional propuesto contra las 11 filas reales de Martín y
habría **OCULTADO 7 de los 9 comentarios de pregunta que él sí escribió** (9/11 = 82% de sus filas, y
fue su aporte principal — su texto no fue a la respuesta, fue a la pregunta). Un condicional aquí no
compra presupuesto de interacción: cuesta cero clics escribir nada, y compra pérdida de señal medida.

**(2) Anclas CON PALABRA en los cinco puntos de los dos ejes.** El formulario mostraba "1 2 3 4 5"
pelones — peor que el banco, que al menos tenía palabras. Un ancla que nadie usa no es neutral: sube el
piso de azar y destruye la métrica. Dos anclas están escritas contra hallazgos específicos: el **2**
cubre OMISIÓN y no sólo error (la omisión es el defecto modal medido: 10 de las 24 respuestas
calificadas "Sí sólida" traían igualmente algo escrito en "qué falta", y es el punto 3 de Natalia en la
junta); y el **3** no invita a no comprometerse ("a medias — partes sí y partes no" obliga a mirar el
contenido), porque el mapeo hace que el 3 se ABSTENGA y cada 3 es un par perdido.

**(3) El eje PREGUNTA se re-clava a UN constructo y se declara descriptivo.** Pasa de "objetiva, con
contexto, específica" —tres constructos en un número, la configuración que dio kappa ≤ 0— a **"¿cabía
completa en una sola respuesta?"**. El constructo no es de escritorio: es lo que los tres revisores
dijeron espontáneamente cuando la rúbrica no tenía casilla. El esquema no cambia (sigue aceptando 1-5),
y la UI declara en pantalla que **este eje NO entra al ECE**.

**(4) El eje RESPUESTA va PRIMERO.** Es el único que se mapea a outcome y financia la calibración; la
atención del calificador decae con cada fila.

**(5) Tres cortes PARALELOS en `/calibration`, y el titular NO se toca.** Cambiar en silencio una cifra
ya publicada es justo lo que la casa prohíbe, así que `ece` se queda como está y al lado se ofrece el
mismo cálculo sobre subconjuntos declarados:
- `by_authorship` — `m5-consenso` (el ECE **sin autoexamen**) y `m5-cierre` (el autor calificándose).
- `raters` — `n_runs_author_only`, `n_runs_single_rater` y el reparto por número de calificadores: de
  cuántas cabezas depende el número.
- `ece_excluding_declines` — el mismo ECE quitando las corridas con verdict `APPROVE_DECLINE`, con la
  cuenta de cuántas se apartaron.
Y tres declaraciones nuevas en `OUTCOME_MAPPING_DECL` (`axis_roles`, `author_caveat`,
`honest_decline`), que la UI ya renderiza genéricamente — cero cambio de front para que aparezcan.

**(6) El denominador honesto del corpus.** `/consulta-sistema` ya pintaba `corpus.por_nicho` y se leía
como EL reparto del acervo, cuando es el reparto de lo **catalogado** en el manifest: 9 registros contra
34 documentos indexados. Se agregan `n_docs_indexados`, `cobertura_del_reparto` y un caveat. Los dos
números ya vivían en el mismo snapshot: el arreglo es de lectura, no de datos.

## Alternatives considered

- **Un campo `failure_locus` de atribución causal** (nada falló / la pregunta / el sistema / los datos).
  **Rechazado por tasa base medida:** las tres únicas veces que un médico atribuyó un defecto en el
  banco (Q05, Q23, Q30) fueron **malas lecturas de respuestas correctas**, verificadas contra el texto
  congelado. El campo no agrega un mecanismo de verdad: agrega una etiqueta equivocada con apariencia
  de diagnóstico. Peor: separar "el sistema razonó mal" de "los datos no estaban" exige saber si la
  evidencia existe en el mundo — y Natalia declaró en la misma junta que no tiene acceso a artículos de
  paga. Sería pedirle justo el juicio que dijo no poder emitir. El desempate lo hace el sistema con lo
  que ya mide (`absence_kind`, `retrieval_summary.mode`, `fallback.trigger`).
- **Un eje nuevo `rating_transfer`** ("¿te sirve?"), que es el eje que Martín calificó cuatro veces sin
  tener dónde. **Rechazado:** en `m5-cierre` —el instrumento dominante— el calificador ES el autor, y
  preguntarle si le sirve la respuesta que él mismo pidió es la pregunta con más deseabilidad social del
  formulario. Su señal se recoge donde ya demostró vivir: la nota de la pregunta, siempre visible.
- **`cannot_rate_reason` como lista de seis opciones.** Rechazado: predicción cuantificada de anclas
  nacidas muertas, y varias de sus razones son cosas que el registro congelado ya sabe y debería
  MOSTRAR en vez de preguntar.
- **Un histograma de cobertura de corridas por nicho** para medir el sesgo que reportó Natalia.
  **Rechazado por falta de nulo válido:** `agent_matrix.py` declara la activación por fase (N1/N3/N4
  activos, N2 Fase II, N5 exploratorio, N6 Fase III). En Fase I, cero corridas en N2/N6 es
  **cumplimiento de PROJECT_SCOPE, no sesgo**, y un reporte que pinte esos ceros en rojo estaría
  acusando al sistema de obedecer su propio alcance. Además la n es de ~3 preguntas independientes (de
  las 5 corridas de producción, una es `failed` y dos son literalmente la misma pregunta re-corrida), y
  el eje N1–N6 es ciego al fenómeno que ella nombró: no tiene eje de tejido ni de modalidad, así que no
  podría distinguir "sesgo a pronefros" de "sesgo a genómica". Lo que SÍ se puede afirmar hoy es del
  lado del acervo, y es un censo, no una muestra.
- **Excluir del ECE las corridas calificadas sólo por su autor.** Rechazado: la doctrina de la casa es
  **declarar el poder, no excluir en silencio** (ADR-0005/0030). Se cuenta, se nombra en pantalla
  ("autoexamen, no consenso") y se ofrece el bloque limpio al lado.
- **Cambiar la escala 1-5.** Rechazado: los cortes ≥4/≤2/3-se-abstiene están PUBLICADOS en el cuerpo de
  la respuesta y la UI los renderiza verbatim; cambiar la escala reescribe un método ya publicado y
  rompe la comparabilidad con la única calificación real de producción.

## Consequences

- El instrumento gana el canal que demostró servir (texto libre atribuible) sin costar un solo clic
  adicional en el camino feliz, y pierde la decisión que no alimentaba nada.
- `/calibration` deja de presentar una cifra cuyo sostén no se ve. Con el dataset de hoy el reporte va a
  decir, correctamente, que el titular descansa entero en autoexamen — eso es el comportamiento
  deseado, no un defecto.
- **Retrocompatibilidad:** la migración es aditiva (`ALTER TABLE run_ratings ADD COLUMN note_question
  TEXT DEFAULT ''`, legal sobre la tabla con filas del Postgres de producción sin reescribirla). La
  calificación real existente no se toca ni se re-califica. En el front todos los campos nuevos son
  **opcionales**: el backend se despliega A MANO en Dokploy y la webapp tiene autodeploy on push, así
  que la UI tiene que tolerar un backend que todavía no los manda — hay un test que lo fija.
- **Lo que NO cambia:** las dos zonas del registro congelado · append-only · procedencia derivada ·
  enmascaramiento server-side (la proyección enmascarada es allowlist, así que `note_question` no se
  filtra por construcción — con test) · el evento `rating.added` sin scores · consenso = conteos ·
  la ausencia declarada · "calificar jamás bloquea una corrida" · `/calibration` NO-SPEND ·
  ADR-0064 §6 (el banco CSV sigue siendo OTRO instrumento y no entra aquí).
- Gates: **`smoke_m5v2_http.py` NUEVO 32/32** · `smoke_ratings_calibration.py` **39/39** (+10) ·
  `smoke_run_pipeline.py` 121/121 · `smoke_query_service.py` 45/45 · `smoke_precedent.py` 15/15 ·
  `smoke_ingest_gate.py` 22/22 · `smoke_zfin_sweep.py` 12/12 · `smoke_run_held_out_v2.py` 12/12 ·
  `doc_coherence_check` 7/7 · webapp `npm run gate` **177/177** (+4) + build verde.
- **`smoke_m5v2_http.py` existe por una razón específica.** Los otros gates llaman
  `app.add_rating(...)` como FUNCIÓN de Python: saltan el parseo del cuerpo por Pydantic, el ruteo y la
  serialización a JSON. Un campo nuevo puede persistir perfecto por la vía directa y no llegar nunca
  por HTTP. Este gate usa `TestClient` (stack ASGI completo, el mismo camino de la webapp) y fija:
  que `note_question` sobrevive el viaje de ida y de vuelta · que el enmascaramiento **no la filtra**
  sobre el JSON ya serializado · que una procedencia falsificada por el cliente se ignora (ADR-0056) ·
  que un cliente VIEJO (sin el campo) sigue dando 200 · y que los tres cortes de `/calibration` más el
  denominador del corpus viajan de verdad. Es la lección permanente del RIL aplicada: antes de
  reportar verde hay que verificar que el gate VIO el campo, no sólo que no explotó.
- **Ventana de pérdida silenciosa entre despliegues (medida).** El front autodespliega on push y el
  backend se despliega A MANO. Con el front nuevo contra el backend viejo, Pydantic **descarta
  `note_question` en silencio** (no da 422): la calificación se guarda y la nota de la pregunta se
  pierde. El resto degrada limpio (los bloques de `/calibration` no viajan y la UI no los pinta —
  hay test). Consecuencia operativa: **el redeploy de `witt-query-service` no es opcional ni
  posponible** una vez que el front está vivo.

## Evidence

- `reports/2026-08-26_banco-calibracion-rescate-plan_v1.html` — el análisis completo del banco devuelto.
- `reports/calibracion_banco_20260826.json` — salida del scorer determinista (kappa, acuerdos, gaps).
- `evaluation/gold_set/respuestas/{nat,martin,marcelo}.csv` — las tres hojas convertidas de los .xlsx.
- Junta con Natalia y Sharon, 2026-08-26 (los seis puntos de Nat; el sesgo pronefros/genética).
- `rag_index/corpus_manifest.json` — 9 registros, 6 con N3 como dominio primario; RN13 en 0.

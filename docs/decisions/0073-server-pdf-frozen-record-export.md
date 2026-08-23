# ADR-0073 — El PDF de servidor del registro congelado (`GET /runs/{id}/record.pdf`, M4 export)

- **Status:** Accepted — 2026-08-22. Cierra el pendiente "PDF server-side (M4)" del handoff. Es el
  tapón de la fuga que `registro-congelado.md` documenta como no-ignorable: *"cualquier derivado
  fuera de la pantalla sale limpio"* — los médicos van a pegar respuestas en Word/WhatsApp/correo,
  y ese derivado limpio (prosa y números sin su estado epistémico) es exactamente lo que el
  producto existe para hacer imposible.
- **Relates:** ADR-0046 (una fuente, tres lectores: URL + PDF + bitácora — este es el segundo
  lector), ADR-0044 (identidad: si no cuadra, no se dibuja — aplica igual al PDF), ADR-0067
  (la revisión viaja al PDF: nada se borra), ADR-0062 (la disciplina de dependencias medidas),
  las dos reglas del fundador en registro-congelado.md.
- **Affects:** **NUEVO** `rag_index/query_service/record_pdf.py` · `app.py`
  (`GET /runs/{run_id}/record.pdf`) · `requirements.txt` (+`fpdf2`) · `smoke_run_pipeline.py` (+6).

## Context

Las dos reglas del contrato (decisión del fundador 2026-08-04): (1) **jamás "imprimir la página"**
— el PDF se genera DEL JSON CONGELADO con plantilla propia (un `window.print()` produce justo el
artefacto limpio a evitar); (2) **la variante impresa no usa textura de fondo** (los navegadores y
clientes de correo la tiran) — usa lo que sobrevive: la palabra impresa SIEMPRE, reglas y bordes, y
las bandas dicen las palabras completas.

## Decision

`record_pdf.build_pdf(record) -> bytes`, plantilla propia sobre el JSON congelado con el MISMO orden
de lectura que la hoja (el estado epistémico ARRIBA de la respuesta):

1. Identidad → **banda de MODO con palabras completas** (SELLADA LIMPIA / DEGRADADA con causa /
   REDUCIDO POR CONFIGURACIÓN / NO INSTRUMENTADO / literal desconocido tratado como degradado por
   regla) → decision_state con glosa → **auditoría** (veredicto + panel fila por fila, jueces
   errored declarados; OBJETADA con doble regla) → **ciclo de revisión** cuando existió (ronda 0
   completa marcada SUPERADA — nada se borra) → respuesta (con la cinta RESPONDE CON HUECO
   DECLARADO cuando aplica, y la glosa de absence_kind) → **confianza con su procedencia** en
   palabras (elicitación dedicada / recuperada-NO-medición-limpia / derivada) + pass1/pass2/delta/
   revision + cross-check in-line + by_subclaim sin promedio → citas numeradas / huecos /
   alternativas con sus 3 estados → costo ([MEDICIÓN] tokens, [PROYECCIÓN] dólares) → consenso como
   CONTEO abierto (los valores individuales viven en la app) → pie: sha de identidad, "el único
   canal autorizado — copiar y pegar pierde el estado epistémico", y el saneo declarado.
2. **Identidad rota ⇒ el PDF NO se genera** (`ValueError` → 409), la misma regla que la hoja.
3. Registros pre-1.1: cada ausencia se DECLARA (`[?] no consta`), jamás se rellena.
4. Tipografía: fuentes core latin-1 con **saneo declarado** (em-dash→'-', etc.; nota en el pie) —
   la fidelidad exigida es epistémica, no tipográfica; embeber un TTF queda como pulido futuro.

**Dependencia medida** (disciplina ADR-0062): `fpdf2` 2.8.8 = 4 paquetes puros
(fpdf2/defusedxml/fonttools/Pillow), sin cairo/playwright/sistema — instalable en el contenedor
py3.12-slim sin fricción.

## Alternatives considered

- **Render de la página (headless browser / window.print)** — prohibido por el contrato: es
  exactamente el derivado limpio que hay que evitar, y arrastraría playwright al contenedor.
- **weasyprint/reportlab** — weasyprint requiere cairo/pango del sistema; reportlab es más pesado
  sin ganancia para una plantilla de texto con reglas y bordes.
- **Exportar los scores individuales de calificación** — v1 exporta solo el CONTEO del consenso:
  el PDF circula fuera de la app y los valores individuales (con autoría) viven bajo la disciplina
  de enmascaramiento de M5 (ADR-0064).

## Consequences

- M4 queda completo del lado backend: la UI solo necesita el botón que descargue
  `GET /runs/{id}/record.pdf` (con la leyenda junto al botón: es la única exportación autorizada).
- El PDF de una corrida con revisión enseña AMBAS rondas — el rastro completo circula fuera de la
  app sin perder nada.
- Muestra real generada del piloto ADR-0072 (Q01: APPROVE_DECLINE + stated-second-elicitation) y
  entregada a Emmanuel.
- Gates: `smoke_run_pipeline.py` **118/118** (+6: banda completa, revisión al PDF, identidad rota
  409, NO INSTRUMENTADO, endpoint application/pdf, pie con canal único + saneo).

"""
record_pdf.py — el PDF de servidor del registro congelado (M4 export, ADR-0073).

El tapón de la fuga que registro-congelado.md documenta: *"cualquier derivado fuera de la pantalla
sale limpio"* — impresión, copy-paste a Word/WhatsApp y correo tiran la textura/riel/cinta y
conservan la prosa y los números; el artefacto que circula fuera de la app es exactamente lo que
este producto existe para hacer imposible. Reglas del contrato (decisión del fundador 2026-08-04):

  1. **Jamás "imprimir la página"**: el PDF se genera DEL JSON CONGELADO con plantilla propia
     (una fuente, tres lectores: URL, PDF, bitácora — no pueden divergir).
  2. **La variante impresa no usa textura de fondo**: usa lo que sobrevive — LA PALABRA IMPRESA
     SIEMPRE, reglas y bordes, y las bandas dicen las palabras completas (la banda de
     NO INSTRUMENTADO no se apoya en punteados).
  3. El estado epistémico va ARRIBA de la respuesta (el orden de lectura es el orden de confianza).
  4. La identidad manda: `question_matches_run == false` ⇒ el PDF NO SE GENERA (misma regla que
     la hoja, ADR-0044).

Tipografía: fuentes core (latin-1) con saneo DECLARADO de caracteres fuera de latin-1 (em-dash→'-',
etc.) — la fidelidad exigida es EPISTÉMICA (el estado viaja), no tipográfica; embeber un TTF queda
como pulido futuro. Dependencia medida (ADR-0062-style): fpdf2 2.8.8 = 4 paquetes puros
(fpdf2+defusedxml+fonttools+Pillow), nada de playwright/cairo.
"""
import datetime
import json

from fpdf import FPDF

# saneo latin-1 DECLARADO: el registro usa em-dashes/flechas/comillas tipográficas que las fuentes
# core no cargan; se mapean a equivalentes imprimibles (jamás se tira contenido en silencio).
_LATIN1_MAP = {
    "—": "-", "–": "-", "‘": "'", "’": "'", "“": '"', "”": '"',
    "…": "...", "→": "->", "←": "<-", "·": "-", "•": "-",
    "≤": "<=", "≥": ">=", "≈": "~", "τ": "tau", "✖": "x", "✓": "ok",
}


def _t(s):
    if s is None:
        return "no consta"
    s = str(s)
    for k, v in _LATIN1_MAP.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


_MODE_BAND = {
    "semantic": "MODO DE RECUPERACION: SELLADA LIMPIA - busqueda semantica medida",
    "degraded-dense-failed": ("MODO: DEGRADADA - la busqueda por significado FALLO; el resultado es "
                              "sparse-only y NO es semantico"),
    "reduced-by-config": "MODO: REDUCIDO POR CONFIGURACION - es configuracion, no falla",
    "not-measured": "NO INSTRUMENTADO - el modo de recuperacion no se midio (se lee como el peor caso)",
}

_STATE_GLOSS = {
    "DI_SUFFICIENT": "la DATA INAMOVIBLE alcanzo",
    "FALLBACK_FETCHED": "se recupero material externo - falta auditarlo",
    "AUDIT_APPROVED": "auditoria aprobada",
    "AUDIT_REJECTED": "ninguna evidencia paso la auditoria",
}

_SOURCE_GLOSS = {
    "stated-second-elicitation": "elicitacion dedicada post-sintesis (la medicion autoritativa, ADR-0065)",
    "stated": "declarada in-line por el modelo",
    "recovered-from-malformed-tool-call": "RECUPERADA de un tool call malformado - valor real, NO medicion limpia",
    "derived-min-of-subclaims": "derivada (min de sub-claims, peor-de-N declarado)",
}

_ABSENCE_GLOSS = {
    "not-applicable": "afirma evidencia positiva",
    "no-evidence-retrieved": "el store no sabe - NO dice nada del mundo (dispara re-ingesta, no conclusion)",
    "evidence-of-no-effect": "evidencia ACTIVA de efecto nulo - estado OPUESTO a no-encontrado",
}


class _Doc(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.cell(0, 5, "WITT x ORGANOGENESIS - REGISTRO CONGELADO (exportacion de servidor)",
                  new_x="LMARGIN", new_y="NEXT", align="C")
        self.ln(1)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 7)
        self.cell(0, 4, f"pagina {self.page_no()}/{{nb}}", align="C")


def _rule(pdf):
    pdf.ln(1)
    pdf.set_draw_color(0)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(2)


def _h(pdf, text):
    pdf.set_font("Helvetica", "B", 10)
    pdf.multi_cell(0, 5, _t(text), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)


def _p(pdf, text, style="", size=9):
    pdf.set_font("Helvetica", style, size)
    pdf.multi_cell(0, 4.6, _t(text), new_x="LMARGIN", new_y="NEXT")


def _band(pdf, text, double=False):
    """Banda con BORDE y palabras completas (regla 2: nada de textura; la palabra impresa siempre)."""
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.multi_cell(0, 6, _t(text), border=1, new_x="LMARGIN", new_y="NEXT", align="C")
    if double:
        y = pdf.get_y() + 0.6
        pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
        pdf.ln(1.4)
    pdf.ln(1.2)
    pdf.set_font("Helvetica", "", 9)


def build_pdf(record, compress=True):
    """El PDF (bytes) desde el registro congelado — jamás desde la página. Identidad primero."""
    if record.get("question_matches_run") is False:
        raise ValueError("identidad rota: el registro no corresponde a la pregunta de la corrida "
                         "(question_matches_run=false) - la hoja no se dibuja y el PDF tampoco (ADR-0044)")

    pdf = _Doc(format="A4")
    pdf.set_compression(compress)
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()

    # --- identidad de la corrida -----------------------------------------------------------------
    _p(pdf, f"run_id: {record.get('run_id')}   -   contrato de render: "
            f"{record.get('render_contract_version')}", size=8)
    _p(pdf, f"PREGUNTA: {record.get('question')}", style="B", size=11)
    frozen_at = record.get("frozen_at")
    if frozen_at:
        _p(pdf, f"CERRADA por {record.get('closed_by')} el {frozen_at} - es precedente consultable", size=8)
    else:
        _p(pdf, "SIN CERRAR - esperando cierre: NO es precedente todavia", size=8)
    _rule(pdf)

    # --- 1. el estado epistemico ARRIBA ----------------------------------------------------------
    rs = record.get("retrieval_summary")
    if rs is None:
        _band(pdf, _MODE_BAND["not-measured"])
    else:
        mode = rs.get("mode")
        texto = _MODE_BAND.get(mode, f"LITERAL DESCONOCIDO: {mode} - se trata como DEGRADADO por regla")
        extra = f" ({rs.get('retrievals')} recuperaciones, agregacion {rs.get('aggregation')})"
        _band(pdf, texto + extra)

    ds = record.get("decision_state") or {}
    st = ds.get("state")
    _p(pdf, f"decision_state: {st} - {_STATE_GLOSS.get(st, 'estado fuera del vocabulario conocido')}"
            f"   |   may_answer_now: {'SI' if ds.get('may_answer_now') else 'NO'}"
            f"   |   may_propose_now: {'SI' if ds.get('may_propose_now') else 'NO'}")
    _rule(pdf)

    # --- 2. auditoria adversarial (siempre; el estado sano tambien se declara) --------------------
    audit = record.get("audit") or {}
    verdict = audit.get("verdict")
    _h(pdf, "REVISION ADVERSARIAL - obligatoria en el 100% de las corridas")
    if audit:
        objetada = verdict == "REVISE"
        _band(pdf, (f"OBJETADA - {audit.get('tally', {}).get('REVISE', '?')} REVISE de "
                    f"{audit.get('n_valid')} validos - hallazgo negativo de primera clase") if objetada
              else f"APROBADA ({verdict}) - {audit.get('n_valid')} jueces validos",
              double=objetada)
        _p(pdf, f"vocabulario: {audit.get('source_vocabulary')}", size=8)
        for row in audit.get("panel", []):
            if row.get("status") == "errored":
                _p(pdf, f"  - {row.get('reviewer')} ({row.get('lens')}): ERRORED - excluido, "
                        f"jamas fabricado", size=8)
            else:
                caught = f" | atrapo: {row.get('caught')}" if row.get("caught") else ""
                _p(pdf, f"  - {row.get('reviewer')} ({row.get('lens')}): {row.get('verdict')}{caught}",
                   size=8)
    else:
        _band(pdf, "REQUERIDA Y PENDIENTE - sin veredicto registrado")

    # --- 2b. ciclo de revision (ADR-0067): nada se borra ------------------------------------------
    rev = record.get("revision") or {}
    if rev.get("performed"):
        _p(pdf, f"HUBO CICLO DE REVISION ({rev.get('cap')} de max {rev.get('cap')}, ADR-0067): "
                f"veredicto inicial {rev.get('initial_verdict')} -> final {rev.get('final_verdict')}. "
                f"La tabla de arriba es la ronda 1 (post-revision); la ronda 0 persiste abajo - "
                f"NADA SE BORRA.", style="B")
        ai = record.get("answer_initial") or {}
        _p(pdf, f"RONDA 0 - respuesta inicial (SUPERADA, no borrada): {ai.get('direct_answer')}",
           style="I", size=8)
        auditi = record.get("audit_initial") or {}
        for row in auditi.get("panel", []):
            if "verdict" in row:
                _p(pdf, f"  - [ronda 0] {row.get('reviewer')} ({row.get('lens')}): {row.get('verdict')}",
                   size=8)
    elif rev.get("skipped_reason"):
        _p(pdf, f"[?] REVISE sin ciclo de revision - {rev['skipped_reason']}", size=8)
    _rule(pdf)

    # --- 3. la respuesta (despues del estado - el orden de lectura es el orden de confianza) ------
    _h(pdf, "RESPUESTA")
    ans = record.get("answer") or {}
    if verdict == "REVISE" or (ans.get("gap_flags") or []):
        _band(pdf, "RESPONDE CON HUECO DECLARADO - leer los huecos junto con la respuesta")
    _p(pdf, ans.get("direct_answer") or "(sin respuesta registrada)", size=10)
    ak = ans.get("absence_kind")
    if ak and ak != "not-applicable":
        _p(pdf, f"absence_kind: {ak} - {_ABSENCE_GLOSS.get(ak, ak)}", style="B", size=8)
    _rule(pdf)

    # --- 4. confianza con su procedencia -----------------------------------------------------------
    _h(pdf, "CONFIANZA DECLARADA - autoreporte del modelo, NO medicion")
    conf = record.get("confidence")
    if conf:
        if conf.get("state") == "value" and conf.get("final") is not None:
            _p(pdf, f"final: {conf['final']}   |   procedencia: "
                    f"{_SOURCE_GLOSS.get(conf.get('source'), conf.get('source') or 'no consta')}")
        else:
            _p(pdf, "SIN MEDIR - absent-not-calibratable: el modelo la omitio (declarado, "
                    "no un null silencioso)", style="B")
        partes = [f"pass1: {conf.get('pass1')}"]
        if conf.get("pass2") is not None:
            partes += [f"pass2: {conf.get('pass2')}", f"delta: {conf.get('delta')}"]
        if conf.get("revision") is not None:
            partes.append(f"revision: {conf.get('revision')}")
        if conf.get("pass1_inline") is not None:
            partes.append(f"cross-check in-line: {conf.get('pass1_inline')} (el instrumento previo "
                          f"persiste, ADR-0065)")
        _p(pdf, "   |   ".join(partes), size=8)
        subs = conf.get("by_subclaim") or {}
        for k, v in subs.items():
            _p(pdf, f"  - {k}: {v}", size=8)
        if subs:
            _p(pdf, "el agregado NO sustituye el perfil - no se imprime promedio (SS5)", size=7)
    else:
        _p(pdf, "[?] el bloque confidence no viaja en este registro (contrato pre-1.1)", style="I")
    fb = record.get("fallback") or {}
    if fb:
        _p(pdf, f"fallback.trigger: {fb.get('trigger')}"
                + (f" (tau={((fb.get('fb_meta') or {}).get('tau'))})" if fb.get("fb_meta") else ""), size=8)
    _rule(pdf)

    # --- 5. evidencia, huecos, alternativas --------------------------------------------------------
    _h(pdf, "EVIDENCIA CITADA (numeros = evidencia; letras reservadas a precedente)")
    cits = record.get("citations") or []
    if cits:
        for c in cits:
            _p(pdf, f"  [{c.get('n')}] {c.get('kind')}: {c.get('id')}"
                    + (f" - {c.get('note')}" if c.get("note") else ""), size=8)
    else:
        _p(pdf, "[?] citas tipadas no constan (contrato pre-1.1) - no se rellena", style="I", size=8)
    gaps = ans.get("gap_flags") or []
    if gaps:
        _h(pdf, "HUECOS DECLARADOS")
        for g in gaps:
            _p(pdf, f"  ! {g}", size=8)
    alts = record.get("alternatives_considered")
    _h(pdf, "ALTERNATIVAS CONSIDERADAS")
    if alts is None:
        _p(pdf, "[?] AUSENTE - hueco del sistema (distinto de 'no habia alternativas')", style="I", size=8)
    elif not alts:
        _p(pdf, "se consideraron y NO hubo alternativas viables (lista vacia declarada)", size=8)
    else:
        for a in alts:
            _p(pdf, f"  - {a}", size=8)
    _rule(pdf)

    # --- 6. costo + consenso + pie ------------------------------------------------------------------
    tu = record.get("token_usage")
    if tu:
        _p(pdf, f"COSTO: {tu.get('input_tokens'):,} entrada / {tu.get('output_tokens'):,} salida "
                f"[MEDICION] - USD {tu.get('estimated_cost_usd')} [PROYECCION: los tokens son medicion, "
                f"los dolares no]", size=8)
    cons = record.get("consensus")
    if cons:
        _p(pdf, f"CONSENSO DE CALIFICACION: {cons.get('received')} de {cons.get('invited')} - "
                f"{'ABIERTO' if cons.get('open') else 'completo'} (conteo, jamas promedio - los "
                f"valores individuales viven en la app)", size=8)
    _rule(pdf)
    ident = record.get("bundle_identity") or {}
    _p(pdf, f"Exportado del registro congelado el "
            f"{datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')} - "
            f"identidad sha256: {str(ident.get('sha256', 'no consta'))[:16]}...  -  "
            f"Esta exportacion de servidor es EL UNICO canal autorizado para sacar una respuesta de "
            f"la app: copiar y pegar desde la pantalla pierde el estado epistemico. Texto normalizado "
            f"a latin-1 para el PDF (saneo declarado).", style="I", size=7)

    out = pdf.output()
    return bytes(out)


def build_pdf_from_json(path, compress=True):
    return build_pdf(json.loads(open(path, encoding="utf-8").read()), compress=compress)

"""
question_agent.py — el agente que convierte un APUNTE en una PREGUNTA que opera en Witt
(2026-09-04, pedido del fundador).

Este módulo NO es "pídele al modelo que redacte". Es una ESPECIFICACIÓN VERSIONADA de qué es
una pregunta bien formada aquí, más la llamada que la aplica. La spec se depura con
resultados; por eso cada borrador se guarda con la versión que lo produjo (db.note_questions)
y refinar la spec no reescribe la historia.

DE DÓNDE SALE LA ESPECIFICACIÓN — no de la intuición, de una medición del propio proyecto:
el banco de calibración midió que preguntar por tres constructos a la vez («objetiva, con
contexto, específica») dio kappa <= 0 en los tres, y que lo que los tres revisores dijeron
espontáneamente, sin casilla que se los pidiera, fue el TAMAÑO: «muy ambiciosa, la partiría
en 2». Por eso el eje PREGUNTA de M5 se re-clavó a un solo constructo (ADR-0075) y por eso
la regla 1 de esta spec es el tamaño. El agente apunta a la medición que YA EXISTE.

EL LAZO DE CALIBRACIÓN, cerrado:
    apunte -> [agente, spec vN] -> borrador (afirma fits_one_run)
           -> la persona lo lleva a Preguntar -> /runs/plan lo juzga -> /runs lo corre
           -> M5 lo califica en el EJE PREGUNTA (rating_input = TAMAÑO)
           -> db.question_calibration() enfrenta lo AFIRMADO con lo MEDIDO, por versión de spec.
El agente no se califica solo: lo califica el mismo instrumento humano que califica todo aquí.

NO-HANG (§6): el agente puede fallar sin tumbar nada. Un borrador errored SIGUE siendo un
borrador — declara que la redacción no se pudo hacer, que es distinto de no haberla intentado
(mismo principio que judgment.state=errored del planner).
"""
import json

# composite_auditor se importa PEREZOSAMENTE dentro de _default_drafter: sólo la llamada real al
# modelo lo necesita, y sólo es importable después de que `server` ajusta el sys.path. Así este
# módulo se puede importar (y su spec leer) sin arrastrar la pila del modelo — que es lo que
# permite que los gates lo carguen antes que la app.

# El modelo: misma política best-tier que la síntesis y el planner (directiva 2026-06-13) —
# jamás se degrada para ahorrar. El fundador pidió Opus explícitamente para este rol.
QUESTION_MODEL = "claude-opus-4-8"

# v1 (2026-09-04): las cinco reglas de abajo. Al cambiarlas SUBE esta versión — los borradores
# viejos conservan la suya y el tablero de calibración compara versión contra versión.
QUESTION_SPEC_VERSION = "1"

# --- LA ESPECIFICACIÓN ---------------------------------------------------------------------------
# Se manda al modelo VERBATIM y se sirve VERBATIM a la UI: la persona lee la misma regla que el
# agente obedeció. Una regla que el operador no puede leer no se puede depurar.
QUESTION_SPEC = {
    "version": QUESTION_SPEC_VERSION,
    "objetivo": (
        "Convertir un apunte (teoría o idea en texto libre) en UNA pregunta que el pipeline de "
        "Witt pueda contestar contra la DATA INAMOVIBLE."
    ),
    "reglas": [
        {
            "id": "R1",
            "nombre": "Cabe en una corrida",
            "regla": (
                "UNA afirmación, UNA respuesta. Si el apunte contiene varias preguntas, redacta "
                "la PRINCIPAL y declara las demás en sibling_questions — jamás las fusiones con "
                "'y' para no dejar nada fuera."
            ),
            "por_que": (
                "Es el ÚNICO constructo del eje pregunta de M5 (ADR-0075). Medido: pedir tres "
                "constructos a la vez dio kappa <= 0; el tamaño fue lo que los revisores "
                "señalaron solos ('la partiría en 2')."
            ),
        },
        {
            "id": "R2",
            "nombre": "Nombra sus entidades",
            "regla": (
                "Los símbolos (genes, estructuras) van EXPLÍCITOS en el texto de la pregunta y "
                "repetidos en `entities`, tal como los escribió el apunte."
            ),
            "por_que": "Sin símbolo nombrado, /resolve no puede anclar la pregunta al store verificado.",
        },
        {
            "id": "R3",
            "nombre": "Declara su alcance",
            "regla": (
                "Organismo, estructura y etapa cuando el apunte los dé (p. ej. 'en pez cebra', "
                "'pronefros'). Si el apunte NO los da, no los inventes: decláralo en assumptions."
            ),
            "por_que": "Una pregunta sin alcance admite respuestas de organismos que no vienen al caso.",
        },
        {
            "id": "R4",
            "nombre": "Es decidible contra la evidencia",
            "regla": (
                "La pregunta se debe poder contestar con evidencia recuperable, no con "
                "especulación abierta. Prefiere '¿es requerido X para Y?' sobre '¿qué opinas de X?'."
            ),
            "por_que": "El pipeline responde desde evidencia citada; una pregunta abierta no tiene gate.",
        },
        {
            "id": "R5",
            "nombre": "No trae la respuesta adentro",
            "regla": (
                "No redactes una pregunta dirigida que sólo pida confirmar la teoría del apunte. "
                "La pregunta debe poder contestarse que NO."
            ),
            "por_que": "Una pregunta que sólo admite 'sí' convierte al pipeline en un espejo del autor.",
        },
    ],
    "prohibido": (
        "Inventar biología que no está en el apunte. Todo lo que agregues para que la pregunta "
        "se sostenga va DECLARADO en assumptions. Lo del apunte que no puedas convertir en "
        "pregunta va DECLARADO en unsupported — jamás se descarta en silencio."
    ),
}


def spec_digest() -> str:
    """La spec como texto para el system prompt: el modelo obedece exactamente lo que la UI muestra."""
    lineas = [QUESTION_SPEC["objetivo"], "", "REGLAS:"]
    for r in QUESTION_SPEC["reglas"]:
        lineas.append(f"{r['id']} · {r['nombre']}: {r['regla']} (POR QUÉ: {r['por_que']})")
    lineas += ["", "PROHIBIDO: " + QUESTION_SPEC["prohibido"]]
    return "\n".join(lineas)


QUESTION_TOOL = {
    "name": "emit_question_draft",
    "description": (
        "Turn the researcher's free-form note into ONE well-formed question for the Witt pipeline. "
        "You are NOT answering it. Obey the five rules given in the system prompt. Everything you "
        "add that the note did not say goes in `assumptions`; everything in the note you could not "
        "turn into this question goes in `unsupported`."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "THE question, in the note's own language. One claim, one answer (R1).",
            },
            "entities": {
                "type": "array", "items": {"type": "string"},
                "description": "Symbols named in the question, verbatim from the note (R2).",
            },
            "scope": {
                "type": "string",
                "description": "Organism / structure / stage the question is bounded to (R3). Empty if the note gave none.",
            },
            "fits_one_run": {
                "type": "boolean",
                "description": (
                    "YOUR judgment on R1: does this fit in a single run — one question, one answer? "
                    "This claim is scored later against the human's EJE PREGUNTA rating, so be honest: "
                    "false with a good reason is worth more than an optimistic true."
                ),
            },
            "fits_rationale": {
                "type": "string",
                "description": "One line: why it fits, or what makes it tight.",
            },
            "sibling_questions": {
                "type": "array", "items": {"type": "string"},
                "description": "The OTHER questions in the note, kept whole and separate (R1). Never merged in.",
            },
            "assumptions": {
                "type": "array", "items": {"type": "string"},
                "description": "What you added that the note did not say. Empty list if you added nothing.",
            },
            "unsupported": {
                "type": "array", "items": {"type": "string"},
                "description": "What the note says that this question does NOT carry. Declared, never dropped silently.",
            },
        },
        "required": ["question", "entities", "fits_one_run", "fits_rationale"],
    },
}


def _default_drafter(note: dict):
    """UNA llamada al modelo con la spec como system prompt. Inyectable: los gates corren con un
    redactor falso y CERO gasto (mismo patrón que runs._default_planner)."""
    # perezoso Y con la ruta de PAQUETE: composite_auditor vive en analysis/scripts/lib/, y sólo
    # resuelve como `from lib import ...` después de que runs.py mete analysis/scripts en el
    # sys.path. Un `import composite_auditor` pelón falla SIEMPRE — y el §6 no-hang lo convertiría
    # en un borrador errored perfectamente plausible, o sea un agente muerto en silencio.
    from lib import composite_auditor

    system = (
        "You are the question-drafting agent of the Witt × Organogenesis webapp. You convert a "
        "researcher's free-form note into ONE question the pipeline can answer. You do NOT answer "
        "it, and you do NOT invent biology.\n\n" + spec_digest()
    )
    user_text = json.dumps({
        "title": note.get("title", ""),
        "body": note.get("body", ""),
        "entities_cited": note.get("entities", []),
        "niches_cited": note.get("niches", []),
    }, ensure_ascii=False)
    return composite_auditor._anthropic_tool_call(
        QUESTION_MODEL, system, user_text, tool=QUESTION_TOOL, max_tokens=1200)


def draft_question(note: dict, drafter=None) -> tuple[dict, dict | None]:
    """apunte -> (borrador, usage). El borrador SIEMPRE trae su spec_version y su state.

    §6 no-hang: si el modelo falla, se devuelve un borrador `errored` con la causa VERBATIM en
    vez de propagar la excepción — declarar que la redacción no se pudo hacer es distinto de no
    haberla intentado, y el apunte no se pierde por eso.
    """
    drafter = drafter or _default_drafter
    base = {
        "spec_version": QUESTION_SPEC_VERSION,
        "model": QUESTION_MODEL,
        "spec": QUESTION_SPEC,          # verbatim: la UI muestra la MISMA regla que el agente obedeció
        "source_note_id": note.get("note_id"),
    }
    try:
        out, usage = drafter(note)
    except Exception as e:
        return {**base, "state": "errored", "error": f"{type(e).__name__}: {e}",
                "question": "", "entities": [], "scope": "", "fits_one_run": None,
                "fits_rationale": "", "sibling_questions": [], "assumptions": [],
                "unsupported": []}, None

    pregunta = (out.get("question") or "").strip()
    if not pregunta:
        # el modelo respondió pero sin pregunta: es una falla del agente, no un borrador vacío
        return {**base, "state": "errored",
                "error": "el agente no devolvió pregunta (question vacío)",
                "question": "", "entities": [], "scope": "", "fits_one_run": None,
                "fits_rationale": "", "sibling_questions": [], "assumptions": [],
                "unsupported": []}, usage

    def _lista(clave):
        v = out.get(clave)
        return [str(x).strip() for x in v if str(x).strip()] if isinstance(v, list) else []

    cabe = out.get("fits_one_run")
    return {
        **base,
        "state": "drafted",
        "question": pregunta,
        "entities": _lista("entities"),
        "scope": (out.get("scope") or "").strip(),
        # el juicio del agente se guarda como llegó: True/False, o None si no lo emitió —
        # un None NO se convierte en False (eso inventaría una afirmación que no hizo)
        "fits_one_run": bool(cabe) if isinstance(cabe, bool) else None,
        "fits_rationale": (out.get("fits_rationale") or "").strip(),
        "sibling_questions": _lista("sibling_questions"),
        "assumptions": _lista("assumptions"),
        "unsupported": _lista("unsupported"),
    }, usage

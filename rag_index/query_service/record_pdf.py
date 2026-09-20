"""
record_pdf.py — el PDF de servidor del registro congelado (M4 export, ADR-0073), COMPLETO por TABLA (ADR-0083 J).

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
  5. ADR-0079: 'EJES DEL EPISODIO' (junto al estado, arriba) e 'INVESTIGACION' (turno, padre, precedente
     en LETRAS marcado NO ADMISIBLE COMO EVIDENCIA, identidad del padre con la REGLA del sha leída del registro).
  6. **ADR-0083 (J) — RE-ESTRUCTURA POR TABLA.** Cada llave top-level del registro congelado tiene una sección
     espejo (`SECCIONES`), un contrato de nacimiento (`KEY_BORN`) y TRES estados CALCULADOS por `_tres_estados`:
     llave AUSENTE ⇒ 'NO INSTRUMENTADO (contrato < <KEY_BORN>) - el registro nacio antes; no se rellena' (el
     número sale de la TABLA, jamás de un literal fijo: un registro 1.9 sin `models` dice '< 1.10', no '< 1.8');
     null DECLARADO con su razón (`<key>_state` / `skipped_reason` si existen); VALOR impreso. Las llaves de la
     zona de servicio que `app._ratings_view` fusiona al leer (`SERVICE_KEYS`) quedan blanqueadas del gate.
     `pdf_sections_cover(frozen_keys)` es la API del gate de cobertura (smoke_record_pdf.py y la segunda fuente
     de `witt-webapp/tools/parity_check.py`): una llave nueva del frozen sin sección ROMPE el gate.

REGLA ESCRITA (R10 del ADR-0083): cada sección llama LITERALMENTE `record.get("<key>")` por cada llave que imprime.
El gate de paridad de la webapp mide por regex (`PDF_ACCESS_RE` sobre este archivo) — una refactorización a
`record.get(key)` genérico lo cegaría. `_tres_estados(record, key)` calcula el estado; la LECTURA del valor
sigue siendo literal en cada sección.

GRUPOS Y ANCLAS: las llaves de una sección se agrupan por ANCLA (la primera llave del grupo en `SECCIONES`). Si
el ancla NO está en el registro, el grupo entero se declara en UNA línea (la llave ancla con su contrato y las
facetas con el suyo si nacieron después: un registro < 1.8 no imprime catorce líneas iguales). Si el ancla está,
cada faceta se imprime con sus tres estados; una faceta del MISMO contrato que su ancla y ausente se lee 'no
consta' (p. ej. `thread_parent_matches_run_rule` → 'regla no declarada en este registro'), porque el registro
SÍ nació con ese contrato — decir 'NO INSTRUMENTADO' sería falso.

MINIATURAS (ADR-0083 J.2): una figura se embebe SOLO si `license.embeddable` ∧ `WITT_FIGURES_PDF_THUMBS=1` (o
`thumbs=True`) ∧ el archivo está en `cache_dir` ∧ su sha256 RECALCULADO == el congelado (figures.verify_cached,
ADR-0077) ∧ ≤ WITT_FIGURES_MAX_IMAGE_MB ∧ ≤ 12 miniaturas por PDF ∧ el PDF no rebasa 8 MB (presupuesto de bytes
embebidos). Si no: palabras + `source_url` ('no embebible: <licencia>' | 'bytes no en caché' | 'bytes: mismatch').
El PDF jamás toca la red; nada binario sale del registro (los bytes viven en mcp_cache, ADR-0074).

  7. **ADR-0084 (J) — LOCALIZADOR WEB (sección `localizador`, llave `web_locator`, nace en 1.13).** La web LOCALIZA
     identificadores y jamás es fuente: el PDF imprime estado (vocabulario cerrado de lib/web_locator.py + glosa), proveedor
     y fuente, consultas verbatim, la tabla localizado → identificador (id · kind · regla · confianza · entró como · estado ·
     materializado · seleccionado · fetched — SIN la URL hallada: vive sólo en `frozen.web_locator.located[]`), el ledger de NO
     resueltos con URL y razón rotulado NO ADMISIBLE COMO EVIDENCIA (la brecha declarada que el humano revisa; el título del
     buscador rotulado 'no es evidencia'), contadores [MEDICION], cuota n/cap con su regla y costo con clase [PROYECCION].
     `deterministic_checks.web_locator` (4 predicados) va en GATE; `token_usage.web_locator` y el total proyectado en CONSUMO;
     `citations[].located_via` en EVIDENCIA. Bajo kill-switch se imprime el literal y las 3 excepciones declaradas.

Tipografía: fuentes core (latin-1) con saneo DECLARADO de caracteres fuera de latin-1 (em-dash→'-',
etc.) — la fidelidad exigida es EPISTÉMICA (el estado viaja), no tipográfica; embeber un TTF queda
como pulido futuro. Dependencia medida (ADR-0062-style): fpdf2 2.8.8 = 4 paquetes puros
(fpdf2+defusedxml+fonttools+Pillow), nada de playwright/cairo. Pillow sólo la usa fpdf2 para las miniaturas.
"""
import datetime
import io
import json
import sys
from pathlib import Path

from fpdf import FPDF

# lib.figures (ADR-0083 F1): verify_cached / env_config / cache_dir / LICENSE_TABLE. Import TOLERANTE — sin el
# módulo el PDF sigue saliendo (palabras + enlace) y lo DECLARA ('lib.figures no disponible').
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "analysis" / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "analysis" / "scripts"))
try:
    from lib import figures as _figures  # noqa: E402
except Exception:   # pragma: no cover — depende del árbol
    _figures = None

# --- constantes DECLARADAS del ADR-0083 (J.2) ---------------------------------------------------------------
PDF_MAX_MB = 8.0                 # tope del PDF: al acercarse, las miniaturas siguientes degradan a palabras + enlace
PDF_TEXT_RESERVE_BYTES = 512 * 1024   # reserva para texto/estructura al presupuestar bytes de imagen (declarada)
THUMBS_MAX_N = 12                # tope de miniaturas por PDF
THUMB_W_MM = 60.0                # ancho de miniatura (constante)
THUMB_RULE = ("miniatura SOLO si license.embeddable (congelado) Y la licencia sigue permitida por WITT_FIGURES_EMBED_LICENSES de HOY "
              "(la misma puerta que el 403 de GET /figures — corrector) y WITT_FIGURES_PDF_THUMBS=1 y archivo en cache_dir y sha256 "
              "recalculado == congelado y <= WITT_FIGURES_MAX_IMAGE_MB y <= 12 por PDF y PDF <= 8 MB; si no, palabras + enlace")

# saneo latin-1 DECLARADO: el registro usa em-dashes/flechas/comillas tipográficas que las fuentes
# core no cargan; se mapean a equivalentes imprimibles (jamás se tira contenido en silencio).
_LATIN1_MAP = {
    "—": "-", "–": "-", "‘": "'", "’": "'", "“": '"', "”": '"',
    "…": "...", "→": "->", "←": "<-", "·": "-", "•": "-",
    "≤": "<=", "≥": ">=", "≈": "~", "τ": "tau", "✖": "x", "✓": "ok", "✗": "x",
    "∧": "y", "≠": "!=", "⇒": "=>", "⌈": "ceil(", "⌉": ")", "Σ": "sum", "∈": "en", "∩": "n",
}


def _t(s):
    if s is None:
        return "no consta"
    s = str(s)
    for k, v in _LATIN1_MAP.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


def _j(v, n=240):
    """JSON compacto acotado para imprimir sub-llaves que no tienen glosa propia (nada se tira en silencio)."""
    try:
        s = json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        s = str(v)
    return s if len(s) <= n else s[:n - 3] + "..."


def _si(v):
    return "SI" if v is True else "NO" if v is False else "null (no consta)"


# ============================================================================================================
# (J.1) TABLA: contrato de nacimiento por llave + secciones + zona de servicio
# ============================================================================================================
# Fijado leyendo el historial de RENDER_CONTRACT_VERSION en runs.py:50-100 y los ADR que lo suben (0050 → 1.0;
# 0051 → 1.1; 0060 → 1.3; 0061 → 1.4; 0065 → 1.5; 0067 → 1.6; 0078 → 1.7; 0079 (+corrector) → 1.8; 0080 → 1.9;
# 0081 → 1.10; 0082 → 1.11; 0083 → 1.12; 0084 → 1.13). Donde el borrador del ADR-0083 (J.1) difería del historial, MANDA el
# historial (regla del propio ADR): reasoning / agents_invoked / alternatives_considered nacen en 1.3 (ADR-0060),
# fallback y confidence en 1.1 (ADR-0051 'block 4'). `niches`: 1.7 según el ADR-0083; el historial de runs.py no lo
# registra (LOTE-02·3, 2026-09-05) — se toma el valor del ADR y se declara en el smoke.
KEY_BORN = {
    "render_contract_version": "1.0", "run_id": "1.0", "user_id": "1.0", "question": "1.0", "measured_at": "1.0",
    "store_at_retrieval": "1.0", "retrieval_summary": "1.0", "decision_state": "1.0", "audit": "1.0", "answer": "1.0",
    "deterministic_checks": "1.0", "token_usage": "1.0", "usage_raw": "1.0", "bundle_identity": "1.0",
    "question_matches_run": "1.0", "frozen_at": "1.0", "closed_by": "1.0",
    "fallback": "1.1", "confidence": "1.1", "citations": "1.1",
    "reasoning": "1.3", "agents_invoked": "1.3", "alternatives_considered": "1.3",
    "plan": "1.4", "plan_declared": "1.4", "plan_question_matches_run": "1.4",
    "audit_initial": "1.6", "answer_initial": "1.6", "revision": "1.6",
    "citations_schema": "1.7", "evidence_cited_raw": "1.7", "niches": "1.7",
    "thread": "1.8", "thread_context": "1.8", "thread_context_skipped_reason": "1.8",
    "thread_parent_matches_run": "1.8", "thread_parent_matches_run_state": "1.8", "thread_parent_matches_run_rule": "1.8",
    "precedent_citations": "1.8", "precedent_citations_state": "1.8", "origin": "1.8",
    "plan_parent_matches_run": "1.8", "plan_parent_matches_run_state": "1.8",
    "plan_snapshot_matches_run": "1.8", "plan_snapshot_matches_run_state": "1.8", "episode_axes": "1.8",
    "competence": "1.9", "search_ledger": "1.9", "citations_support_summary": "1.9",
    "models": "1.10",
    "council": "1.11",
    "figures": "1.12",
    "web_locator": "1.13",
    "attested_images": "1.14",
}
BORN_UNKNOWN = "contrato desconocido, declarado"

# Zona de SERVICIO: llaves que app._ratings_view FUSIONA al leer (no las congela runs.py) — blanqueadas del gate.
SERVICE_KEYS = ("consensus", "ratings", "ratings_masked", "ratings_masking_note")

# SECCIONES: (llave top-level del frozen, id de sección). El ORDEN dentro de una sección define los GRUPOS: cada
# llave listada en ANCLAS abre un grupo; las siguientes son sus facetas. La webapp lee este literal como SEGUNDA
# fuente del gate con la regex ANCLADA `^SECCIONES\s*=\s*\($` (re.M) y luego `("<key>", "<seccion>")` hasta el
# parentesis de cierre a profundidad 0 — NO cambiar la forma del literal. (corrector: una regex SIN anclar casa antes
# ORDEN_SECCIONES o un comentario y devuelve 0 llaves; este comentario ya no contiene el texto del literal.
# Fuente programatica equivalente: record_pdf.SECTION_KEYS.)
SECCIONES = (
    ("run_id", "identidad"),
    ("render_contract_version", "identidad"),
    ("question", "identidad"),
    ("frozen_at", "identidad"),
    ("closed_by", "identidad"),
    ("user_id", "identidad"),
    ("measured_at", "identidad"),
    ("store_at_retrieval", "identidad"),
    ("question_matches_run", "identidad"),
    ("bundle_identity", "identidad"),
    ("origin", "identidad"),
    ("retrieval_summary", "estado"),
    ("decision_state", "estado"),
    ("episode_axes", "ejes"),
    ("competence", "competencia"),
    ("search_ledger", "busqueda"),
    ("web_locator", "localizador"),
    ("attested_images", "aportadas"),
    ("fallback", "fallback"),
    ("models", "modelos"),
    ("audit", "auditoria"),
    ("revision", "auditoria"),
    ("audit_initial", "auditoria"),
    ("answer_initial", "auditoria"),
    ("answer", "respuesta"),
    ("confidence", "confianza"),
    ("citations", "evidencia"),
    ("citations_schema", "esquema"),
    ("evidence_cited_raw", "esquema"),
    ("citations_support_summary", "soporte"),
    ("figures", "figuras"),
    ("alternatives_considered", "alternativas"),
    ("reasoning", "razonamiento"),
    ("agents_invoked", "agentes"),
    ("plan", "plan"),
    ("plan_declared", "plan"),
    ("plan_question_matches_run", "plan"),
    ("plan_parent_matches_run", "plan"),
    ("plan_parent_matches_run_state", "plan"),
    ("plan_snapshot_matches_run", "plan"),
    ("plan_snapshot_matches_run_state", "plan"),
    ("deterministic_checks", "gate"),
    ("niches", "nichos"),
    ("thread", "investigacion"),
    ("thread_context", "investigacion"),
    ("thread_context_skipped_reason", "investigacion"),
    ("thread_parent_matches_run", "investigacion"),
    ("thread_parent_matches_run_state", "investigacion"),
    ("thread_parent_matches_run_rule", "investigacion"),
    ("precedent_citations", "investigacion"),
    ("precedent_citations_state", "investigacion"),
    ("council", "consejo"),
    ("token_usage", "consumo"),
    ("usage_raw", "consumo"),
)
# Anclas de grupo (la primera llave de cada sección es ancla implícita; aquí las adicionales).
ANCLAS_EXTRA = ("origin", "revision", "precedent_citations", "usage_raw", "decision_state", "evidence_cited_raw")
# Orden de lectura (= orden de confianza, regla 3) y rótulos.
ORDEN_SECCIONES = (
    ("identidad", None),
    ("estado", None),
    ("ejes", "EJES DEL EPISODIO (ADR-0079) - derivados al congelar, cuatro ejes, jamas un enum unico"),
    ("competencia", "COMPETENCIA (ADR-0080) - la compuerta que decide si la pasada 1 basta; conjuncion decidida por CODIGO"),
    ("busqueda", "BUSQUEDA (ADR-0080/0082) - plan, rondas y UNA FILA POR FUENTE del harness"),
    ("localizador", "LOCALIZADOR WEB (ADR-0084) - la web LOCALIZA identificadores, jamas es fuente: ningun texto ni URL de la web "
                    "entra a la evidencia; lo localizado se materializo por Europe PMC con raw cacheado, lo no resuelto se declara "
                    "y se cuenta"),
    ("fallback", "FALLBACK - quien disparo la Ruta B (trigger, fb_meta integro)"),
    ("modelos", "MODELOS (ADR-0081) - procedencia MEDIDA del modelo que corrio (roles, ran, firma del panel)"),
    ("auditoria", "REVISION ADVERSARIAL - obligatoria en el 100% de las corridas"),
    ("respuesta", "RESPUESTA"),
    ("confianza", "CONFIANZA DECLARADA - autoreporte del modelo, NO medicion"),
    ("evidencia", "EVIDENCIA CITADA (numeros = evidencia; letras reservadas a precedente)"),
    ("esquema", "ESQUEMA DE CITAS (ADR-0078) - como llego evidence_cited: cinco estados, cinco frases"),
    ("soporte", "RESUMEN DE SOPORTE (ADR-0080) - la escalera de cinco peldanos, siempre los cinco"),
    ("figuras", "FIGURAS DE PAPERS (ADR-0083) - evidencia OBSERVADA por source-pointer (fig_id + sha256 + licencia "
                "verificadas por codigo); lo que la imagen dice es JUICIO de las lentes, jamas medicion"),
    ("aportadas", "IMAGENES APORTADAS POR UNA PERSONA (ADR-0086) - ATESTIGUADAS: procedencia registrada (quien, cuando, "
                  "con que consentimiento y que licencia declaro), JAMAS evidencia y JAMAS citables. Este PDF no lleva "
                  "miniaturas de ellas: son privadas y viven en el almacen, no aqui"),
    ("alternativas", "ALTERNATIVAS CONSIDERADAS"),
    ("razonamiento", "RAZONAMIENTO (ADR-0060) - marco declarado (self-report) y marcos estructurales del pipeline"),
    ("agentes", "AGENTES INVOCADOS (ADR-0060) - derivados de lo que CORRIO, jamas autoreporte"),
    ("plan", "PLAN DECLARADO (ADR-0061) - el juicio del planner antes de encolar; procedencia plan<->padre"),
    ("gate", "GATE DETERMINISTA (verify_output, clase Logic-LM) - llave por llave"),
    ("nichos", "NICHOS - dos fuentes sin fundir: catalogo MEDIDO y panel JUZGADO"),
    ("investigacion", "INVESTIGACION (ADR-0079) - turnos encadenados; el turno previo es PRECEDENTE, jamas evidencia"),
    ("consejo", "CONSEJO DE CRITERIO (ADR-0082) - requisitos de informacion y cobertura; JAMAS escribe la respuesta"),
    ("consumo", "CONSUMO - tokens MEDIDOS, USD y tokens de vision PROYECTADOS"),
)
SECTION_KEYS = tuple(k for k, _s in SECCIONES)
assert len(set(SECTION_KEYS)) == len(SECTION_KEYS), "una llave del frozen tiene UNA sección espejo (J.1)"
assert set(SECTION_KEYS) == set(KEY_BORN), "toda llave con sección tiene contrato de nacimiento y viceversa (J.1)"
assert {s for _k, s in SECCIONES} == {s for s, _t in ORDEN_SECCIONES}, "toda sección se pinta y toda pintada tiene llaves"


def keys_of_section(seccion_id):
    return tuple(k for k, s in SECCIONES if s == seccion_id)


def grupos_de(seccion_id):
    """Los GRUPOS (tuplas de llaves; la primera es el ANCLA) de una sección, en orden."""
    grupos, actual = [], []
    for k in keys_of_section(seccion_id):
        if actual and k in ANCLAS_EXTRA:
            grupos.append(tuple(actual))
            actual = []
        actual.append(k)
    if actual:
        grupos.append(tuple(actual))
    return grupos


GRUPOS = {s: grupos_de(s) for s, _t in ORDEN_SECCIONES}


def grupo_de(key):
    for grupos in GRUPOS.values():
        for g in grupos:
            if key in g:
                return g
    return (key,)


def born_of(key):
    """Contrato en que nació la llave, o 'contrato desconocido, declarado' — nunca se inventa (J.1)."""
    return KEY_BORN.get(key, BORN_UNKNOWN)


def contract_of(x):
    """API del gate (J.3). Con un REGISTRO (dict): su `render_contract_version` declarado (str | None). Con una LLAVE
    (str): el contrato en que nació (`born_of`)."""
    if isinstance(x, dict):
        v = x.get("render_contract_version")
        return None if v is None else str(v)
    return born_of(x)


def _no_instrumentado_msg(key):
    born = born_of(key)
    if born == "1.0":
        # no existe un contrato anterior al 1.0: la llave es del contrato base y NO consta — se dice tal cual
        return f"NO INSTRUMENTADO (contrato base 1.0: la llave '{key}' no consta en este registro) - no se rellena"
    if born == BORN_UNKNOWN:
        return f"NO INSTRUMENTADO ({BORN_UNKNOWN}) - la llave '{key}' no consta; no se rellena"
    return f"NO INSTRUMENTADO (contrato < {born}) - el registro nacio antes; no se rellena"


def _null_reason(record, key):
    """Razón declarada de un null: `<key>_state`, `<key>_skipped_reason`, `thread_context_skipped_reason`, o lo que
    el bloque hermano diga (revision.performed false para audit_initial/answer_initial; plan_declared para plan)."""
    for suffix in ("_state", "_skipped_reason", "_reason"):
        v = record.get(key + suffix)
        if v:
            return str(v)
    if key in ("audit_initial", "answer_initial"):
        rev = record.get("revision")
        if isinstance(rev, dict) and rev.get("performed") is False:
            return "sin ciclo de revision (revision.performed false, ADR-0067)"
    if key == "plan" and record.get("plan_declared") is False:
        return "plan_declared false - la corrida se encolo sin plan"
    if key == "alternatives_considered":
        return "AUSENTE - hueco del sistema (distinto de 'no habia alternativas')"
    return None


def _tres_estados(record, key):
    """Los tres estados de una llave (ADR-0043/0074, ADR-0083 J.1):
      ('no-instrumentado', 'NO INSTRUMENTADO (contrato < <KEY_BORN>) - ...')  la llave NO existe en el registro
      ('null', <razón declarada | None>)                                        existe y es null
      ('valor', v)                                                              existe con valor"""
    if key not in record:
        return "no-instrumentado", _no_instrumentado_msg(key)
    v = record[key]
    if v is None:
        return "null", _null_reason(record, key)
    return "valor", v


def pdf_sections_cover(frozen_keys, service_keys=SERVICE_KEYS):
    """API del gate de cobertura (J.3/K): {missing: llaves del frozen sin sección (fuera de la zona de servicio),
    extra: llaves con sección que el frozen no trae}."""
    fk = [k for k in frozen_keys]
    missing = [k for k in fk if k not in SECTION_KEYS and k not in service_keys]
    extra = [k for k in SECTION_KEYS if k not in fk]
    return {"missing": missing, "extra": extra}


# ============================================================================================================
# glosas (tablas cerradas: la palabra viene del enum; un literal fuera de tabla se imprime y se marca)
# ============================================================================================================
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

_TURN_KIND_GLOSS = {
    "root": "raiz - abre la investigacion",
    "refine": "refinamiento - pregunta o entidades cambiaron respecto al padre",
    "rerun": "re-ejecucion - misma pregunta y entidades que el padre",
    "branch": "rama - el padre ya tenia otro hijo",
}

_ORIGIN_GLOSS = {
    "production": "produccion - cuenta como precedente y para calibracion",
    "dev-offline": "desarrollo sin red - NO cuenta como precedente ni para calibracion",
    "replay": "re-ejecucion de registro - NO cuenta",
    "smoke": "prueba automatizada - NO cuenta",
    "simulation": "simulacion - NO cuenta",
    "fixture": "fixture de prueba - NO cuenta",
    None: "unknown-pre-adr-0079 - anterior a la columna origin; incluida en precedente y DECLARADA como desconocida",
}

# Tabla de mapeo de los cuatro ejes (ADR-0079 G, clase 'derived-at-freeze'): la palabra viene del enum,
# el enum viene del registro. Un literal fuera de tabla se imprime tal cual y se marca.
_AXIS_WORDS = {
    "world": {
        "effect-claimed": "MUNDO: se afirma un efecto (aprobada, evidencia positiva)",
        "null-bounded": "MUNDO: efecto nulo ACOTADO por evidencia activa (opuesto a no-encontrado)",
        "indeterminate": "MUNDO: INDETERMINADO - el store no sabe; no dice nada del mundo",
        "not-established": "MUNDO: NO ESTABLECIDO - la auditoria rechazo la respuesta",
        "not-assessed": "MUNDO: SIN EVALUAR - no hubo auditoria",
    },
    "inference": {
        "supported": "INFERENCIA: sostenida (APPROVE)",
        "minor-issues": "INFERENCIA: sostenida con observaciones menores (APPROVE_MINOR)",
        "honest-decline": "INFERENCIA: declinacion honesta (APPROVE_DECLINE) - el sistema hizo lo correcto",
        "insufficient": "INFERENCIA: insuficiente (REVISE)",
        "not-evaluated": "INFERENCIA: sin veredicto",
    },
    "technical": {
        "completed": "TECNICO: completada con recuperacion semantica",
        "degraded": "TECNICO: DEGRADADA - termino, pero la recuperacion no fue semantica",
        "failed": "TECNICO: fallo",
        "cancelled": "TECNICO: cancelada",
    },
}

# Corrector ADR-0079: por que thread_parent_matches_run es null — tres estados, cada uno con su glosa
_PARENT_MATCH_NULL_GLOSS = {
    "no-parent": "no aplica (turno raiz)",
    "no-snapshot": "no verificable: el snapshot no viajo (ver thread_context_skipped_reason)",
    "parent-without-frozen-record": "no verificable: el padre no tiene registro congelado",
}
# Corrector ADR-0079: por que precedent_citations esta vacio (la letra solo se emite con padre 'closed')
_PRECEDENT_EMPTY_GLOSS = {
    "no-parent": "sin turno previo",
    "parent-not-closed": "el padre no esta cerrado - no es precedente (ADR-0053) aunque su snapshot viaje",
    "parent-without-frozen-record": "el padre no tiene registro congelado (failed/cancelled)",
}
# Corrector ADR-0079: procedencia plan<->padre — por que plan_parent/plan_snapshot_matches_run es null
_PLAN_MATCH_NULL_GLOSS = {
    "no-plan": "no aplica (corrida sin plan)",
    "plan-predates-thread-declaration": "el plan es anterior a la declaracion de padre (no verificable)",
    "no-parent": "no aplica (ni el plan ni la corrida declaran padre)",
    "no-snapshot": "no verificable (ni el plan ni la corrida traen sha del padre)",
}

# ADR-0078 (J.2): los CINCO literales de citations_schema.source en CINCO frases DISTINTAS
_SCHEMA_SOURCE_PHRASE = {
    "list": "lista tipada ({n_raw} crudas / {n_valid} validas)",
    "string-reparsed": "llegaron SERIALIZADAS y se re-parsearon (procedencia declarada; {n_raw} crudas / {n_valid} validas)",
    "string-unparseable": "0 citas DERIVABLES - el sintetizador cito en texto no tipable; NO es \"cito 0\"",
    "absent": "el bloque llego AUSENTE - no es \"cito 0\"",
    "unsupported-type": "tipo no soportado ({raw_type}) - declarado, no forzado",
}

# ADR-0082: CONSEJO DE CRITERIO — glosas
_COUNCIL_STATE_GLOSS = {
    "applicable": "el consejo JUZGO la cobertura (ronda valida, cuorum alcanzado)",
    "incomplete": "ronda INCOMPLETA (k/N < cuorum) - la compuerta la cuenta como NO competente, se declara",
    "skipped-by-human": "el humano SALTO el consejo con razon - ledger vacio declarado",
    "not-applicable (no-ledger)": "sin ledger del consejo (corrida sin plan o plan sin ronda 1 aprobada)",
    "disabled (kill-switch WITT_COUNCIL=0)": "APAGADO por kill-switch - camino sin consejo, componente informativo",
    "pre-adr-0082": "plan anterior al ADR - sin consejo, declarado",
}
_COVERAGE_GLOSS = {
    "covered": "cubierto", "partial": "PARCIAL (cuenta como sin cubrir)", "uncovered": "SIN CUBRIR",
    "not-judged": "SIN JUZGAR (cuenta como sin cubrir)", "covered-by-attestation": "cubierto por ATESTIGUACION humana (no evidencia)",
    "discarded": "descartado por el humano",
}
_AFTER_SEARCH_GLOSS = {
    "retrieved-for": "se RECUPERO evidencia para su directiva (medicion estructural, no juicio)",
    "still-uncovered": "directiva compilada, nada admitido", "not-searched": "sin directiva (no se busco)",
    "covered-pre": "ya cubierto antes de buscar",
}

# ADR-0083: FIGURAS — glosas cerradas
_FIGURES_STATE_GLOSS = {
    "attached": "figuras adheridas a los papers de la Ruta B (sha256 recalculado al leer: medicion)",
    "no-path-b": "sin Ruta B en esta corrida - no habia papers de los que leer figuras",
    "no-papers-with-xml": "ningun paper seleccionado trajo XML de texto completo - nada que parsear",
    "kill-switch WITT_FIGURES=0": "APAGADO por kill-switch - camino 1.11; las excepciones declaradas viajan en kill_switch",
}
_LICENSE_SOURCE_GLOSS = {
    "ali-license-ref": "leida de <ali:license_ref>",
    "ext-link": "leida de <ext-link> dentro de <license>",
    "license-p-url": "leida de la URL en <license-p>",
    "license-p-token": "leida de un token en prosa de <license-p>",
    "license-p-prose": "leida de la prosa 'Creative Commons Attribution' sin URL (WITT_FIGURES_PROSE_LICENSE=1)",
    "epmc-search": "leida del campo license del search de EPMC (el XML no dio licencia)",
    "none": "sin <permissions> legible en el XML",
}
_VISION_STATE_GLOSS = {
    "sent": "las lentes con vision RECIBIERON imagenes",
    "kill-switch WITT_FIGURES_VISION=0": "APAGADA por kill-switch - ninguna lente recibio imagenes",
    "no-eligible-figures": "ninguna figura elegible (licencia, bytes o caption) - nada se envio",
}
_SAW_DETAIL_GLOSS = {
    "sent": "recibio imagenes", "lens-not-in-vision-lenses": "lente sin vision",
    "kill-switch WITT_FIGURES_VISION=0": "vision apagada por kill-switch", "no-eligible-figures": "sin figuras elegibles",
    "model-vision-unknown": "modelo sin vision en la tabla", "api-form-not-verified": "forma de API no verificada",
}

# ADR-0084: LOCALIZADOR WEB — glosas CERRADAS. Espejan los vocabularios de lib/web_locator.py (W2: WEB_STATES_EXACT/_PREFIXES,
# FEED_STATES_*, UNRESOLVED_REASONS, QUOTA_STATES_EXACT, PROVIDERS, FED_TO) SIN importar el modulo: el registro congelado es la
# unica fuente del PDF (regla 1) y smoke_record_pdf mide que cada literal del vocabulario tiene glosa. Un literal fuera de tabla
# se imprime tal cual y se marca.
WEB_LOCATOR_CINTILLO = ("LA WEB LOCALIZA, NO ES FUENTE (ADR-0084): ningun titulo, snippet ni URL de la web entra al bundle, al "
                        "sintetizador, al panel ni al consejo; solo identificadores resueltos por CODIGO (tabla de patrones por host) y "
                        "materializados por Europe PMC en la misma ronda entran como candidatos (source europepmc, source_family web, "
                        "identifier_provenance web-located:<regla>). Las URLs halladas viven SOLO en frozen.web_locator; este PDF imprime "
                        "una URL UNICAMENTE en el ledger de NO resueltos (brecha declarada, NO ADMISIBLE COMO EVIDENCIA).")
WEB_GATE_PREDICATES = ("web_text_not_cited", "web_located_cited_requires_fetch", "web_items_native_only", "web_urls_not_in_answer")
_WEB_STATE_GLOSS = {
    "located": "la web LOCALIZO >= 1 identificador; lo materializado entro por Europe PMC, lo demas se declara y se cuenta",
    "no-results": "las consultas MIDIERON y no localizaron nada (0 URLs o 0 identificadores) - contadores abajo; 0 medido != null",
    "not-requested (no web directive)": ("hubo ronda de busqueda pero el consejo NO emitio directiva web (gate directive-only) - "
                                         "no se consulto la web"),
    "not-requested (no search round)": "corrida competente sin Ruta B por harness - el localizador no aplica",
    "kill-switch WITT_WEB_LOCATOR=off": ("APAGADO por kill-switch explicito - camino 1.12 byte a byte; las excepciones declaradas "
                                         "viajan en kill_switch"),
}
_WEB_STATE_PREFIX_GLOSS = (
    ("tool-unavailable (ADR-0084", "localizador NO DISPONIBLE (sin llave o proveedor no configurado) - CERO red; la causa viaja en el literal"),
    ("skipped-cap (", "SALTADO por tope (cuota mensual o consultas por ronda) - cero red; el detalle viaja en el literal"),
    ("skipped-budget (", "SALTADO por presupuesto de la ronda - cero red"),
    ("error: ", "el proveedor FALLO - fila declarada, la ronda siguio sin la web"),
)
_WEB_PROVIDER_GLOSS = {
    "brave": ("Brave Search API REST (plan Search) SIN modelo: devuelve URLs; description/extra_snippets se descartan en la salida "
              "de la tool"),
    "anthropic": ("Anthropic web_search (server-tool) via despachador - ALTERNO EXPLICITO sin failover: el modelo despachador LEE "
                  "texto web en este camino (propiedad declarada), solo se conservan URLs"),
    "off": "apagado - ninguna consulta a la web",
}
_WEB_FEED_GLOSS = {
    "materialized-same-round": "materializado en la MISMA ronda por Europe PMC (candidato source europepmc, source_family web)",
    "fed-same-round": "alimentado a ctx en la misma ronda (DOI -> unpaywall_crossref; curie -> monarch)",
    "already-present": "ya presente - lo nativo ya lo traia",
    "duplicate-in-response": "duplicado dentro de la misma respuesta del buscador",
    "not-found-in-europepmc": "el patron caso pero Europe PMC NO lo tiene - NO es candidato",
    "not-materialized (feed cap)": "no materializado: tope WITT_WEB_MAX_MATERIALIZE",
    "not-materialized (budget)": "no materializado: presupuesto de la familia agotado",
    "no-sink-in-1.13": "sin consumidor en 1.13 - localizado y contado, no alimenta nada",
}
_WEB_FEED_PREFIX_GLOSS = (
    ("already-present (dup of ", "ya presente - duplicado de un id nativo (selection.duplicates)"),
    ("no-sink-in-1.13 (", "sin consumidor en 1.13 - localizado y contado, no alimenta nada"),
    ("error: ", "error al materializar - declarado, la ronda siguio"),
)
_WEB_UNRESOLVED_GLOSS = {
    "no-identifier-pattern": "ningun patron de la tabla del resolutor caso",
    "host-not-allowed": "host fuera de WITT_WEB_ALLOWED_HOSTS",
    "unsupported-scheme": "esquema no http(s)",
    "malformed-url": "URL malformada",
}
_WEB_QUOTA_GLOSS = {
    "under-cap": "bajo el tope",
    "cap-reached": "TOPE ALCANZADO - cero red hasta el mes siguiente",
    "not-enforced (no quota callable)": "sin cuota inyectada - no se aplico tope (declarado)",
    "disabled (WITT_WEB_MONTHLY_CAP=0)": "sin tope declarado por env",
    "not-consumed (cache-hit)": "no consumida - respondio la cache por dia",
}
_WEB_FED_TO_WORDS = {
    "pool:literature-candidate (materialized by europepmc)": "pool de literatura (materializado por Europe PMC)",
    "ctx:dois": "ctx:dois -> unpaywall_crossref (misma ronda)",
    "ctx:curies": "ctx:curies -> monarch (misma ronda)",
    None: "sin consumidor (solo localizado y contado)",
}


def _gloss_by_table(value, exact, prefixes, fuera):
    if value in exact:
        return exact[value]
    if isinstance(value, str):
        for pre, g in prefixes:
            if value.startswith(pre):
                return g
    return f"{fuera}: {value}"


def _web_state_gloss(state):
    return _gloss_by_table(state, _WEB_STATE_GLOSS, _WEB_STATE_PREFIX_GLOSS, "estado fuera de vocabulario")


def _web_feed_gloss(fs):
    return _gloss_by_table(fs, _WEB_FEED_GLOSS, _WEB_FEED_PREFIX_GLOSS, "feed_state fuera de vocabulario")


def _council_state_gloss(state):
    if state in _COUNCIL_STATE_GLOSS:
        return _COUNCIL_STATE_GLOSS[state]
    if isinstance(state, str) and state.startswith("errored ("):
        return "la ronda del consejo FALLO - declarado, la corrida siguio sin cobertura"
    if isinstance(state, str) and state.startswith("not-requested ("):
        return "la ronda 1 NO se pidio para este plan (compuerta de gasto declarada)"
    return f"estado fuera de tabla: {state}"


def _figures_state_gloss(state):
    if state in _FIGURES_STATE_GLOSS:
        return _FIGURES_STATE_GLOSS[state]
    if isinstance(state, str) and state.startswith("error: "):
        return "la etapa de figuras FALLO - declarado; la corrida siguio sin figuras"
    return f"estado fuera de tabla: {state}"


def _bytes_state_words(bs):
    if bs == "verified":
        return "bytes verificados por sha256 [MEDICION]"
    if bs == "mismatch":
        return "bytes: mismatch - el sha RECALCULADO no cuadra con el congelado; no se sirve ni se embebe"
    if bs == "never (zfin-display-only)":
        return "jamas bytes (ZFIN: 'permission only to display')"
    if bs == "not-requested (kill-switch)":
        return "no pedidos (kill-switch)"
    if isinstance(bs, str) and bs.startswith("not-fetched ("):
        return f"no bajados {bs[len('not-fetched '):]} - fila declarada, la corrida siguio"
    if isinstance(bs, str) and bs.startswith("error: "):
        return f"descarga con error declarado: {bs}"
    return f"estado de bytes fuera de vocabulario: {bs}"


# ============================================================================================================
# primitivas de dibujo (smoke_precedent / smoke_run_pipeline las ENVUELVEN para capturar texto: seguir llamandolas
# por nombre de modulo)
# ============================================================================================================
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


def _grupo_ausente(pdf, record, grupo, prefijo=""):
    """Si el ANCLA del grupo no está en el registro: UNA línea NO INSTRUMENTADO para todo el grupo (el ancla con su
    contrato; las facetas nacidas después con el suyo) y True. Si el ancla está: False (cada faceta se imprime aparte)."""
    ancla = grupo[0]
    if ancla in record:
        return False
    born = born_of(ancla)
    facetas = [k + (f" (nacida en {born_of(k)})" if born_of(k) != born else "") for k in grupo[1:]]
    _p(pdf, f"{prefijo}[?] {_no_instrumentado_msg(ancla)}"
            + (f"   |   facetas del grupo tampoco constan: {', '.join(facetas)}" if facetas else ""),
       style="I", size=8)
    return True


def _facet(pdf, record, key, label, value, fmt=None, size=8, style="", null_gloss=None):
    """UNA línea de tres estados para la llave `key`, cuyo `value` el llamador leyó con record.get("<key>") LITERAL
    (R10). Devuelve el valor cuando hay valor, None si no."""
    st, payload = _tres_estados(record, key)
    if st == "no-instrumentado":
        _p(pdf, f"{label}: [?] {payload}", style="I", size=size)
        return None
    if st == "null":
        razon = payload or "no consta"
        if null_gloss:
            razon = null_gloss.get(payload, f"estado fuera de tabla: {payload}" if payload else "estado no consta")
        _p(pdf, f"{label}: null declarado - razon: {razon}", size=size)
        return None
    _p(pdf, f"{label}: {fmt(value) if fmt else value}", size=size, style=style)
    return value


# ============================================================================================================
# secciones — cada una llama LITERALMENTE record.get("<key>") por llave (R10)
# ============================================================================================================
def _section_identidad(pdf, record, ctx):
    run_no = record.get("run_no")   # pasajero de la vista de corrida (ADR-0076) — no es llave del frozen; si viaja se imprime
    _p(pdf, f"run_id: {record.get('run_id')}" + (f"   -   corrida #{run_no}" if run_no is not None else "")
            + f"   -   contrato de render: {record.get('render_contract_version') or 'no consta'}", size=8)
    _p(pdf, f"PREGUNTA: {record.get('question')}", style="B", size=11)
    frozen_at = record.get("frozen_at")
    if frozen_at:
        _p(pdf, f"CERRADA por {record.get('closed_by')} el {frozen_at} - es precedente consultable", size=8)
    else:
        _p(pdf, "SIN CERRAR - esperando cierre: NO es precedente todavia", size=8)
    _facet(pdf, record, "user_id", "quien corrio (user_id)", record.get("user_id"))
    _facet(pdf, record, "measured_at", "medida el (measured_at)", record.get("measured_at"))
    _facet(pdf, record, "store_at_retrieval", "store al recuperar", record.get("store_at_retrieval"),
           fmt=lambda s: (f"store_version {s.get('store_version')} - index_version {s.get('index_version')}"
                          if isinstance(s, dict) else _j(s)))
    _facet(pdf, record, "question_matches_run", "identidad pregunta<->corrida", record.get("question_matches_run"),
           fmt=lambda v: "COINCIDE - el bundle es el de esta pregunta (ADR-0044)" if v else f"{v}")
    _facet(pdf, record, "bundle_identity", "identidad del bundle", record.get("bundle_identity"),
           fmt=lambda b: (f"sha256 {b.get('sha256')}" + "".join(f"   |   {k} {b.get(k)}" for k in sorted(b) if k != "sha256")
                          if isinstance(b, dict) else _j(b)))
    # origen (ADR-0079 F): grupo propio — tres estados
    if not _grupo_ausente(pdf, record, grupo_de("origin"), prefijo="origen: "):
        og = record.get("origin")
        if og is None:
            _p(pdf, "origen: null declarado - razon: no consta", size=8)
        else:
            val = og.get("value") if isinstance(og, dict) else og
            src = og.get("source") if isinstance(og, dict) else "no consta"
            gloss = _ORIGIN_GLOSS.get(val, f"fuera del enum ({val}) - declarado, la corrida se creo igual")
            _p(pdf, f"origen: {val if val is not None else 'null'} - {gloss}   |   fuente (al encolar): {src}", size=8)
            sae = og.get("source_at_execution") if isinstance(og, dict) else None
            if isinstance(sae, dict) and sae.get("same_value_as_column") is False:
                # corrector ADR-0079: el entorno al ejecutar derivaba OTRO valor — se declara, no se funde en `source`
                _p(pdf, f"  al ejecutar el entorno derivaba {sae.get('value')!r} ({sae.get('source')}) - "
                        "distinto de la columna; la columna manda", size=7)
    _rule(pdf)


def _section_estado(pdf, record, ctx):
    rs = record.get("retrieval_summary")
    if rs is None:
        _band(pdf, _MODE_BAND["not-measured"])
        st, payload = _tres_estados(record, "retrieval_summary")
        _p(pdf, f"retrieval_summary: {'[?] ' + payload if st == 'no-instrumentado' else 'null declarado - razon: ' + str(payload or 'no consta')}",
           style="I", size=8)
    else:
        mode = rs.get("mode")
        texto = _MODE_BAND.get(mode, f"LITERAL DESCONOCIDO: {mode} - se trata como DEGRADADO por regla")
        extra = f" ({rs.get('retrievals')} recuperaciones, agregacion {rs.get('aggregation')})"
        _band(pdf, texto + extra)
        resto = {k: v for k, v in rs.items() if k not in ("mode", "retrievals", "aggregation")}
        if resto:
            _p(pdf, f"retrieval_summary: {_j(resto, 300)}", size=7)
    if not _grupo_ausente(pdf, record, grupo_de("decision_state"), prefijo="decision_state: "):
        ds = record.get("decision_state") or {}
        st = ds.get("state")
        _p(pdf, f"decision_state: {st} - {_STATE_GLOSS.get(st, 'estado fuera del vocabulario conocido')}"
                f"   |   may_answer_now: {_si(ds.get('may_answer_now'))}"
                f"   |   may_propose_now: {_si(ds.get('may_propose_now'))}"
                + (f"   |   siguiente: {ds.get('required_next_action')}" if ds.get("required_next_action") else ""))
    _rule(pdf)


def _section_ejes(pdf, record, ctx):
    """ADR-0079 G: los cuatro ejes del episodio en palabras (clase derived-at-freeze, tabla de mapeo)."""
    if _grupo_ausente(pdf, record, grupo_de("episode_axes")):
        _rule(pdf)
        return
    axes = record.get("episode_axes")
    if not axes:
        _p(pdf, "episode_axes: null declarado - los ejes no se derivaron", style="I", size=8)
        _rule(pdf)
        return
    for axis in ("world", "inference", "technical"):
        v = axes.get(axis)
        words = _AXIS_WORDS[axis].get(v)
        if words is None:
            words = (f"{axis.upper()}: {'null declarado' if v is None else f'LITERAL FUERA DE TABLA: {v}'}")
        _p(pdf, "  - " + words, size=8)
    prov = axes.get("provenance") or {}
    gates = prov.get("human_gates") or {}
    turn = prov.get("turn") or {}
    _p(pdf, f"  - PROCEDENCIA: origen {prov.get('origin') if prov.get('origin') is not None else 'null'}   |   "
            f"plan declarado: {'SI' if gates.get('plan_declared') else 'NO'}   |   "
            f"cerrada por humano: {'SI' if gates.get('closed') else 'NO'}   |   "
            f"turno {turn.get('turn_no')} ({turn.get('turn_kind')}) de {turn.get('thread_id')}", size=8)
    _p(pdf, "clase: derived-at-freeze - cada eje sale de una tabla de mapeo declarada (decision_state x "
            "absence_kind x veredicto x estado x modo de recuperacion); no es medicion nueva", size=7)
    _rule(pdf)


def _section_competencia(pdf, record, ctx):
    if _grupo_ausente(pdf, record, grupo_de("competence")):
        _rule(pdf)
        return
    comp = record.get("competence")
    if not isinstance(comp, dict):
        _p(pdf, "competence: null declarado - la compuerta no dejo bloque", style="I", size=8)
        _rule(pdf)
        return
    c = comp.get("competent")
    head = ("COMPETENTE - la pasada 1 basto" if c is True else "NO COMPETENTE - se abrio la Ruta B" if c is False
            else "null declarado" + (f" - {comp.get('skipped_reason')}" if comp.get("skipped_reason") else ""))
    _p(pdf, f"competent: {head}   |   not_applicable: {_si(comp.get('not_applicable'))}   |   decidido por: "
            f"{comp.get('decided_by')}   |   modulo {comp.get('module_version')}", style="B", size=9)
    if comp.get("skipped_reason") and c is not None:
        _p(pdf, f"skipped_reason: {comp.get('skipped_reason')}", size=8)
    comps = comp.get("components") if isinstance(comp.get("components"), dict) else {}
    for name, cv in comps.items():
        if not isinstance(cv, dict):
            _p(pdf, f"  - {name}: {_j(cv)}", size=7)
            continue
        val = cv.get("sufficient") if name == "calibration_coverage" and "sufficient" in cv else cv.get("value")
        gating = cv.get("gating")
        extras = {k: v for k, v in cv.items() if k not in ("value", "gating", "reason", "class", "sufficient")}
        _p(pdf, f"  - {name}: {_si(val)}"
                + (f"   |   {'GATEA' if gating else 'informativo (no gatea)'}" if gating is not None else "   |   gatea (por defecto)")
                + (f"   |   razon: {cv.get('reason')}" if cv.get("reason") else "")
                + (f"   |   clase: {cv.get('class')}" if cv.get("class") else "")
                + (f"   |   {_j(extras, 200)}" if extras else ""), size=7)
    _p(pdf, f"conjuncion (orden): {comp.get('conjunction')}   |   razones de NO competencia: {comp.get('reasons')}", size=7)
    sr = comp.get("self_report")
    if isinstance(sr, dict):
        _p(pdf, f"self_report (clase {sr.get('class')}): stated_confidence {sr.get('stated_confidence')} - {sr.get('note')}",
           style="I", size=7)
    cfg = comp.get("config")
    if isinstance(cfg, dict):
        _p(pdf, f"config: gate_enabled {cfg.get('gate_enabled')} | tau {cfg.get('tau')} ({cfg.get('tau_source')}) | "
                f"require_calibration {cfg.get('require_calibration')} | conf_component_gating {cfg.get('conf_component_gating')} | "
                f"council_component_gating {cfg.get('council_component_gating')} ({cfg.get('council_component_gating_source')}) | "
                f"min_history {cfg.get('min_history')} ({cfg.get('min_history_source')})", size=7)
    if "decision" in comp:
        _p(pdf, f"decision: {_j(comp.get('decision'), 300)}", size=7)
    _rule(pdf)


def _section_busqueda(pdf, record, ctx):
    if _grupo_ausente(pdf, record, grupo_de("search_ledger")):
        _rule(pdf)
        return
    sl = record.get("search_ledger")
    if not isinstance(sl, dict):
        _p(pdf, "search_ledger: null declarado - el harness no dejo ledger", style="I", size=8)
        _rule(pdf)
        return
    n_rounds = sl.get("n_rounds")
    _p(pdf, f"estado: {sl.get('state')}   |   plan_state: {sl.get('plan_state')}   |   rondas "
            f"{n_rounds if n_rounds is not None else 'null (el harness no midio)'} / cap {sl.get('cap')}"
            + (f"   |   stop: {sl.get('stop_reason')}" if sl.get("stop_reason") else "")
            + (f"   |   presupuesto por ronda {sl.get('round_budget_s')} s" if sl.get("round_budget_s") is not None else ""),
       style="B", size=9)
    plan = sl.get("plan")
    if isinstance(plan, dict):
        fams = plan.get("families")
        if isinstance(fams, list):
            fam_words = ", ".join((f"{f.get('family')}" + (f" [gate {f.get('gate')}]" if isinstance(f, dict) and f.get("gate") else ""))
                                  if isinstance(f, dict) else str(f) for f in fams)
        else:
            fam_words = _j(fams)
        _p(pdf, f"plan: familias {fam_words or 'ninguna'}   |   fuente {plan.get('families_source')}   |   directivas "
                f"{len(plan.get('directives') or [])} ({plan.get('directives_state')})"
                + (f"   |   excluidas {plan.get('families_excluded')}" if plan.get("families_excluded") else "")
                + (f"   |   orden: {plan.get('families_order_rule')}" if plan.get("families_order_rule") else ""), size=7)
    elif "plan" in sl:
        _p(pdf, "plan: null declarado (sin plan de busqueda)", size=7)
    cs = sl.get("config_source")
    if isinstance(cs, dict):
        _p(pdf, f"config_source: familias {cs.get('families')} | cap {cs.get('cap')} | round_budget_s {cs.get('round_budget_s')}"
                + (f"   |   familias default {sl.get('families_default')}" if sl.get("families_default") else ""), size=7)
    for rd in sl.get("rounds") or []:
        if not isinstance(rd, dict):
            continue
        _p(pdf, f"ronda {rd.get('round')} (trigger {rd.get('trigger')}, presupuesto {rd.get('budget_s')} s): admitidos "
                f"{rd.get('n_admitted')}   |   {rd.get('elapsed_s')} s"
                + (f"   |   stop {rd.get('stop_reason')}" if rd.get("stop_reason") else ""), style="B", size=7)
        for s in rd.get("sources") or []:
            if not isinstance(s, dict):
                continue
            nf = s.get("n_found")
            _p(pdf, f"    {rd.get('round')} | {s.get('family')} | {s.get('status')} | n_found "
                    f"{nf if nf is not None else 'null (no midio)'} | n_new {s.get('n_new') if s.get('n_new') is not None else 'null'}"
                    f" | {s.get('elapsed_s')} s | cache_hit {s.get('cache_hit')} | label {s.get('label')}"
                    + (f" | query {str(s.get('query_sent'))[:120]}" if s.get("query_sent") else "")
                    + (f" | {s.get('detail') or s.get('error')}" if (s.get("detail") or s.get("error")) else "")
                    # ADR-0084 (C.7): la fila web trae proveedor y contadores del localizador; las otras 14 familias no
                    + (f" | proveedor {s.get('provider')} - consultas {s.get('n_queries')} - localizados {s.get('n_located')} - "
                       f"materializados {s.get('n_materialized')} - sin resolver {s.get('n_unresolved')} - ya presentes "
                       f"{s.get('n_already_present')} - USD {s.get('cost_usd_projected')} [PROYECCION] - cuota {s.get('quota_state')} "
                       f"(la web localiza, no es fuente)" if "provider" in s else ""), size=7)
    if "n_items_for_directives" in sl:
        _p(pdf, f"items para directivas del consejo (ADR-0082): {sl.get('n_items_for_directives')}", size=7)
    _rule(pdf)


# ADR-0086 (M): IMAGENES APORTADAS — glosas CERRADAS (espejo de lib/attestations.py). El PDF circula FUERA de la app: aqui
# no hay miniaturas, ni bytes, ni llaves de almacen, ni rutas; de una imagen de paciente tampoco se imprime el caption.
ATTESTED_CINTILLO = ("ATESTIGUADO: lo aporto una persona como PRIOR ART con su procedencia; no es evidencia, no se cita y "
                     "no sostiene ninguna afirmacion. Los bytes viven en almacenamiento privado; este PDF no los lleva.")
ATTESTED_STATE_GLOSS = {
    "attached": "hay imagenes aportadas y adjuntadas por la compuerta humana",
    "no-attested-images": "el plan no adjunto ninguna imagen (MEDIDO: no es que no se pudiera)",
    "not-applicable (no-ledger)": "la corrida no tuvo plan con consejo: no hay canal para aportar",
    "kill-switch WITT_ATTESTED_IMAGES=0": "funcion apagada por variable de entorno",
}


def _attested_state_gloss(state):
    if not isinstance(state, str):
        return "sin estado declarado"
    if state in ATTESTED_STATE_GLOSS:
        return ATTESTED_STATE_GLOSS[state]
    for pfx, g in (("tool-unavailable (", "la biblioteca no esta en el arbol: no se pudo medir"),
                   ("error: ", "fallo al medir; se declara")):
        if state.startswith(pfx):
            return g
    return "estado fuera del vocabulario conocido: se imprime crudo"


def _section_aportadas(pdf, record, ctx):
    """ADR-0086 (M): la seccion 'IMAGENES APORTADAS' nace con frozen.attested_images (1.14). Tres estados: llave ausente
    (registro < 1.14) -> NO INSTRUMENTADO calculado de KEY_BORN; null declarado; valor (estado + glosa, entrega, almacen con
    su durabilidad, y UNA FILA POR IMAGEN con identidad corta, tipo, dimensiones, quien la aporto y cuando, consentimiento y
    licencia DECLARADOS, que lentes la vieron y cuantas lecturas hubo — JUICIO, jamas medicion). Sin miniaturas y sin la
    llave del almacen. De una imagen marcada como material de paciente NO se imprime el caption."""
    if _grupo_ausente(pdf, record, grupo_de("attested_images")):
        _rule(pdf)
        return
    ai = record.get("attested_images")
    if not isinstance(ai, dict):
        _p(pdf, "attested_images: null declarado - la corrida no dejo bloque", style="I", size=8)
        _rule(pdf)
        return
    _p(pdf, ATTESTED_CINTILLO, style="I", size=7)
    state = ai.get("state")
    _p(pdf, f"estado: {state} - {_attested_state_gloss(state)}", style="B", size=9)
    entrega = ai.get("delivery") if isinstance(ai.get("delivery"), dict) else {}
    if entrega:
        _p(pdf, f"entrega: sintetizador {entrega.get('synthesizer')} (bytes al sintetizador: "
                f"{entrega.get('bytes_to_synthesizer')}) - consejo {entrega.get('council')} - panel {entrega.get('panel')}",
           size=8)
    alm = ai.get("storage") if isinstance(ai.get("storage"), dict) else {}
    if alm:
        dur = alm.get("durability") if isinstance(alm.get("durability"), dict) else {}
        _p(pdf, f"almacen: {alm.get('backend')} [{alm.get('state')}]"
                + (f" - {dur.get('note')}" if dur.get("note") else ""), size=8)
    items = ai.get("items") if isinstance(ai.get("items"), list) else []
    if not items:
        _p(pdf, "sin imagenes aportadas en esta corrida [MEDIDO: 0 != ausente]", size=8)
        _rule(pdf)
        return
    vision = ai.get("vision") if isinstance(ai.get("vision"), dict) else {}
    _p(pdf, f"{len(items)} imagen(es) adjuntada(s) - vistas por el panel: {ai.get('n_seen_by_panel')} - lecturas de las "
            f"lentes: {vision.get('n_readings')} [{vision.get('readings_class') or 'model-judgment'}: JUICIO, no medicion]",
       size=8)
    for it in items:
        if not isinstance(it, dict):
            continue
        dims = it.get("dims") if isinstance(it.get("dims"), dict) else {}
        consent = it.get("consent") if isinstance(it.get("consent"), dict) else {}
        paciente = bool(it.get("patient_material"))
        _p(pdf, f"  {it.get('id') or it.get('sha256_short')} - {it.get('media_type')} "
                f"{dims.get('w')}x{dims.get('h')} - {it.get('bytes')} bytes - aportada por {it.get('uploaded_by')} "
                f"el {it.get('uploaded_at')}", style="B", size=7)
        _p(pdf, f"      adjunta a {it.get('attached_to')}"
                + (f" ({it.get('requirement_id')})" if it.get("requirement_id") else "")
                + f" - consentimiento {consent.get('kind') or it.get('consent_kind')} "
                f"[declarado {consent.get('declared') if 'declared' in consent else it.get('consent_declared')}]"
                f" - licencia declarada {it.get('license_declared')} - alcance {it.get('share_scope')}"
                f" - metadatos {it.get('exif_state')}", size=7)
        lentes = it.get("seen_by_lenses") if isinstance(it.get("seen_by_lenses"), list) else []
        _p(pdf, f"      vista por {len(lentes)} lente(s): {', '.join(lentes) if lentes else 'ninguna'}"
                + ("   |   MATERIAL DE PACIENTE: caption no impreso (privacidad)" if paciente else ""), size=7)
        if not paciente and it.get("caption"):
            _p(pdf, f"      dice la persona: \"{it.get('caption')}\"", style="I", size=7)
    _p(pdf, "ninguna de estas imagenes es citable ni cuenta como evidencia; el sintetizador no vio sus pixeles", style="I",
       size=7)
    _rule(pdf)


def _section_localizador(pdf, record, ctx):
    """ADR-0084 (J): la seccion 'LOCALIZADOR WEB' nace con frozen.web_locator (1.13). Tres estados: llave ausente (registro
    < 1.13) -> NO INSTRUMENTADO calculado de KEY_BORN; null declarado; valor (estado del vocabulario cerrado + glosa, proveedor
    y fuente, consultas verbatim, localizados -> identificador, no resueltos como brechas, contadores MEDICION, cuota y costo
    con clase). La URL HALLADA de un localizado NO se imprime (vive solo en frozen.web_locator.located[]; este PDF circula fuera
    de la app); la URL de un NO resuelto SI, rotulada NO ADMISIBLE COMO EVIDENCIA (es la brecha declarada que el humano revisa)."""
    if _grupo_ausente(pdf, record, grupo_de("web_locator")):
        _rule(pdf)
        return
    wl = record.get("web_locator")
    if not isinstance(wl, dict):
        _p(pdf, "web_locator: null declarado - el localizador no dejo bloque", style="I", size=8)
        _rule(pdf)
        return
    _p(pdf, WEB_LOCATOR_CINTILLO, style="I", size=7)
    state = wl.get("state")
    _p(pdf, f"estado: {state} - {_web_state_gloss(state)}", style="B", size=9)
    ks = wl.get("kill_switch")
    if isinstance(ks, dict):
        _p(pdf, f"kill_switch WITT_WEB_LOCATOR={ks.get('WITT_WEB_LOCATOR')} ({ks.get('source') or 'fuente no consta'}) - excepciones "
                f"declaradas al 1.12 byte a byte: {ks.get('declared_exceptions')}", size=7)
    prov = wl.get("provider")
    prov_w = _WEB_PROVIDER_GLOSS.get(prov, f"proveedor fuera de vocabulario: {prov}")
    _p(pdf, f"proveedor: {prov} - {prov_w}   |   fuente {wl.get('provider_source') or 'no consta'}   |   gate {wl.get('gate') or 'no consta'}"
            + (f"   |   entro por: {wl.get('entered_by')}" if wl.get("entered_by") else "   |   la familia web NO entro a la ronda")
            + (f"   |   requisitos del consejo {wl.get('directive_requirement_ids')}" if wl.get("directive_requirement_ids") else ""), size=8)
    tool_v = wl.get("tool_version")
    _p(pdf, f"modulo {wl.get('module_version')} - resolutor {wl.get('resolver_version')} - tool "
            f"{tool_v if tool_v is not None else 'null (tool no cargado)'}"
            + (f"   |   orden de ronda: {wl.get('families_order_rule')}" if wl.get("families_order_rule") else ""), size=7)
    if "n_queries" in wl:
        # contadores: 0 = medido; AUSENTES bajo kill-switch / tool-unavailable (G.2) — por eso la llave se prueba, no el valor
        _p(pdf, f"consultas {wl.get('n_queries')} (descartadas por tope {wl.get('n_queries_dropped_by_cap')}) - resultados (URLs) "
                f"{wl.get('n_results')} - localizados {wl.get('n_located')} - materializados por Europe PMC {wl.get('n_materialized')} - "
                f"no encontrados en Europe PMC {wl.get('n_not_found_in_europepmc')} - alimentados a ctx {wl.get('n_fed_ctx')} - "
                f"localizados sin consumidor {wl.get('n_located_not_fed')} - ya presentes {wl.get('n_already_present')} - sin resolver "
                f"{wl.get('n_unresolved')} - seleccionados {wl.get('n_located_selected')} / no seleccionados {wl.get('n_located_not_selected')} - "
                f"papers web-localizados en el bundle {wl.get('n_papers_web_located')} [MEDICION: 0 medido != null]", size=8)
    queries = wl.get("queries") if isinstance(wl.get("queries"), list) else []
    for q in queries:
        if not isinstance(q, dict):
            continue
        qst = q.get("provider_status") if "provider_status" in q else q.get("status")
        qtxt = q.get("query_en") if "query_en" in q else q.get("q_sent")
        quota = q.get("quota") if isinstance(q.get("quota"), dict) else {}
        q_used = quota.get("n_after") if quota.get("n_after") is not None else quota.get("used")
        q_cap = quota.get("cap")
        _p(pdf, f"  consulta r{q.get('round')} [{qst}]: \"{qtxt}\"   |   fuente {q.get('query_source') or 'no consta'}"
                + (f"   |   req {q.get('requirement_ids')}" if q.get("requirement_ids") else "")
                + (f"   |   proveedor {q.get('provider')}" if q.get("provider") else "")
                + (f"   |   pais/idioma {q.get('country_sent') or '-'}/{q.get('search_lang_sent') or '-'}"
                   if ("country_sent" in q or "search_lang_sent" in q) else "")
                + (f"   |   freshness {q.get('freshness_sent')}" if q.get("freshness_sent") else ""),
           style="B" if qst not in ("success", "no-match") else "", size=7)
        _p(pdf, f"      resultados {q.get('n_results')} - localizados {q.get('n_located')}"
                + (f" - materializados {q.get('n_materialized')}" if "n_materialized" in q else "")
                + f" - sin resolver {q.get('n_unresolved')} [MEDICION]   |   cache_hit {q.get('cache_hit')}"
                + (f"   |   HTTP {q.get('http_status')}" if q.get("http_status") is not None else "")
                + (f"   |   {q.get('elapsed_s')} s" if q.get("elapsed_s") is not None else "")
                + (f" (throttle {q.get('throttle_wait_s')} s)" if q.get("throttle_wait_s") is not None else "")
                + (f"   |   USD {q.get('cost_usd_projected')} [PROYECCION]" if "cost_usd_projected" in q else "")
                + (f"   |   facturable {_si(q.get('billable'))}" if "billable" in q else "")
                + (f"   |   cuota {quota.get('state')} {q_used if q_used is not None else '?'}/{q_cap if q_cap is not None else 'sin tope'}" if quota else "")
                + ("   |   consulta RECORTADA al tope WITT_WEB_MAX_QUERY_CHARS" if q.get("query_truncated") else "")
                + ("   |   el proveedor ALTERO la consulta (query_altered_by_provider)" if q.get("query_altered_by_provider") else "")
                + (f"   |   error: {q.get('error')}" if q.get("error") else "")
                + (f"   |   {q.get('detail')}" if q.get("detail") else ""), size=7)
    located = wl.get("located") if isinstance(wl.get("located"), list) else []
    unresolved = wl.get("unresolved") if isinstance(wl.get("unresolved"), list) else []
    if located:
        _p(pdf, f"LOCALIZADOS -> IDENTIFICADOR ({len(located)}): id - kind - regla (confianza) - host - entro como - estado - materializado - "
                "seleccionado - fetched. La URL hallada NO se imprime: vive solo en frozen.web_locator.located[] (ADR-0084)", style="B", size=7)
        for l in located:
            if not isinstance(l, dict):
                continue
            rule_id = l.get("resolver_rule") if "resolver_rule" in l else l.get("rule_id")
            fs = l.get("feed_state")
            mat = l.get("materialized") if "materialized" in l else (fs == "materialized-same-round" if fs is not None else None)
            sel = l.get("selected")
            sel_w = (f"seleccionado (rango {l.get('selection_rank')})" if sel is True else "no seleccionado" if sel is False
                     else "seleccion: no consta")
            ff = l.get("fetched_found")
            ff_w = ("fetched (registro y texto de Europe PMC)" if ff is True
                    else "NO fetched - una cita a este id es INADMISIBLE (web_located_cited_requires_fetch)" if ff is False
                    else "fetched: no consta")
            adm = l.get("admitted")
            adm_w = ("admitido al pool" if adm is True else f"duplicado de {l.get('duplicate_of')}" if adm is False and l.get("duplicate_of")
                     else "no admitido" if adm is False else None)
            fed_to = l.get("fed_to")
            fed_w = _WEB_FED_TO_WORDS.get(fed_to, f"{fed_to} (fuera de tabla)")
            _p(pdf, f"  {l.get('id')} ({l.get('kind')})   |   regla {rule_id} ({l.get('confidence') or 'confianza no consta'})   |   host "
                    f"{l.get('host')}   |   entro como: {fed_w}", style="B", size=7)
            _p(pdf, f"      {fs} - {_web_feed_gloss(fs)}   |   materializado por Europe PMC: {_si(mat)}   |   {sel_w}   |   {ff_w}"
                    + (f"   |   {adm_w}" if adm_w else "")
                    + (f"   |   evidence_id {l.get('evidence_id')}" if l.get("evidence_id") else "")
                    + (f"   |   store: {l.get('store_state')}" if l.get("store_state") else "")
                    + (f"   |   ronda {l.get('round')}" if l.get("round") is not None else "")
                    + (f"   |   req {l.get('requirement_ids')}" if l.get("requirement_ids") else ""), size=7)
    elif "n_located" in wl:
        _p(pdf, "localizados: ninguno (lista vacia medida)", size=7)
    if unresolved:
        _p(pdf, f"SIN RESOLVER ({len(unresolved)}) - brechas DECLARADAS, NO ADMISIBLE COMO EVIDENCIA: URL - host - razon - titulo del "
                "buscador (rotulado: no es evidencia, no entro al bundle)", style="B", size=7)
        for u in unresolved:
            if not isinstance(u, dict):
                continue
            reason = u.get("reason")
            reason_w = _WEB_UNRESOLVED_GLOSS.get(reason, f"razon fuera de vocabulario: {reason}")
            tw = u.get("title_web")
            _p(pdf, f"  NO ADMISIBLE: {u.get('url')}   |   host {u.get('host')}   |   razon {reason} - {reason_w}"
                    + (f"   |   ronda {u.get('round')}" if u.get("round") is not None else "")
                    + (f"   |   req {u.get('requirement_ids')}" if u.get("requirement_ids") else ""), size=7)
            _p(pdf, f"      titulo del buscador (NO es evidencia, no entro al bundle): {tw if tw else 'no consta'}", style="I", size=7)
    elif "n_unresolved" in wl:
        _p(pdf, "sin resolver: ninguno (lista vacia medida)", size=7)
    gft = wl.get("gap_flags_typed")
    if isinstance(gft, list):
        kinds = {}
        for g in gft:
            k = g.get("kind") if isinstance(g, dict) else str(g)
            kinds[k] = kinds.get(k, 0) + 1
        _p(pdf, f"brechas tipadas (gap_flags_typed): {len(gft)} - por clase {_j(kinds, 200)} - answer.gap_flags lleva CONTEO por clase, "
                "jamas URLs (ese canal viaja al modelo del turno siguiente)", size=7)
    quota = wl.get("quota") if isinstance(wl.get("quota"), dict) else None
    if quota:
        used = quota.get("n_after") if quota.get("n_after") is not None else quota.get("used")
        cap = quota.get("cap")
        qstate = quota.get("state")
        q_w = _WEB_QUOTA_GLOSS.get(qstate, f"estado de cuota fuera de vocabulario: {qstate}")
        _p(pdf, f"cuota mensual ({quota.get('month') or 'mes no consta'}, {quota.get('provider') or prov}): "
                f"{used if used is not None else '?'}/{cap if cap is not None else 'sin tope'} consultas"
                + (f" (antes de esta corrida {quota.get('n_before')})" if quota.get("n_before") is not None else "")
                + (f" (reservadas {quota.get('reserved')})" if quota.get("reserved") is not None else "")
                + (f" - cap {quota.get('cap_source')}" if quota.get("cap_source") else "")
                + f" - estado {qstate} - {q_w}", size=7)
        if quota.get("rule"):
            _p(pdf, f"  regla de la cuota: {quota.get('rule')}", style="I", size=7)
    cost = wl.get("cost") if isinstance(wl.get("cost"), dict) else None
    if cost:
        _p(pdf, f"costo del localizador [PROYECCION, clase {cost.get('class')}]: USD {cost.get('usd_projected')}"
                + (f" - {cost.get('n_queries_billable')} consultas facturables" if "n_queries_billable" in cost else "")
                + (f" x USD {cost.get('price_usd_per_1k')}/1k" if cost.get("price_usd_per_1k") is not None else "")
                + (f" ({cost.get('provider')}, precios al {cost.get('price_as_of')})" if cost.get("price_as_of") else "")
                + " - APARTE de estimated_cost_usd (tokens); el total que cuadra viaja en token_usage.estimated_cost_usd_total_projected", size=7)
        toks = cost.get("tokens") if isinstance(cost.get("tokens"), dict) else None
        if toks:
            _p(pdf, f"  tokens del despachador (anthropic): in {toks.get('in')} / out {toks.get('out')} [{str(toks.get('class') or 'medicion').upper()}]"
                    + (f" - USD {cost.get('tokens_usd_projected')} [PROYECCION]" if "tokens_usd_projected" in cost else ""), size=7)
        pdet = cost.get("provider_detail") if isinstance(cost.get("provider_detail"), dict) else None
        if pdet:
            # corrector ADR-0084 (I): el alterno DECLARA en el registro el tipo de server-tool y que el modelo despachador LEE texto web
            _p(pdf, f"  alterno Anthropic: server-tool {pdet.get('tool_type')} ({pdet.get('tool_type_source')}; admitidos "
                    f"{pdet.get('tool_types_allowed')}) - EL MODELO DESPACHADOR LEE TEXTO WEB EN ESTE CAMINO "
                    f"(reads_web_text {_si(pdet.get('reads_web_text'))}): los resultados cuentan como tokens de entrada aunque "
                    f"el caller descarte todo texto; por eso es alterno EXPLICITO sin failover", style="B", size=7)
    ah = wl.get("allowed_hosts")
    gd = wl.get("generic_doi_rule")
    rules = wl.get("resolver_rules")
    parts = []
    if isinstance(ah, dict):
        parts.append(f"hosts permitidos: {ah.get('value')} ({ah.get('source')})")
    if isinstance(gd, dict):
        parts.append(f"regla DOI generica (doi-in-url-any-host): {'ENCENDIDA' if gd.get('enabled') else 'apagada'} ({gd.get('source')})")
    if isinstance(rules, list):
        parts.append(f"tabla del resolutor: {len(rules)} reglas ({', '.join(str(r.get('rule_id')) for r in rules if isinstance(r, dict))})")
    if parts:
        _p(pdf, "   |   ".join(parts), size=7)
    if wl.get("text_policy"):
        _p(pdf, f"politica de texto (verbatim): {wl.get('text_policy')}", style="I", size=7)
    if wl.get("rule"):
        _p(pdf, f"regla (verbatim): {wl.get('rule')}", style="I", size=7)
    _rule(pdf)


def _section_fallback(pdf, record, ctx):
    if _grupo_ausente(pdf, record, grupo_de("fallback")):
        _rule(pdf)
        return
    fb = record.get("fallback")
    if not isinstance(fb, dict):
        _p(pdf, "fallback: null declarado", style="I", size=8)
        _rule(pdf)
        return
    fbm = fb.get("fb_meta") if isinstance(fb.get("fb_meta"), dict) else {}
    _p(pdf, f"fallback.trigger: {fb.get('trigger') if fb.get('trigger') is not None else 'null (no se disparo)'}"
            + (f" (tau={fbm.get('tau')})" if "tau" in fbm else ""), style="B", size=9)
    comp_meta = fbm.get("competence") if isinstance(fbm.get("competence"), dict) else None
    if comp_meta is not None or "trigger_decided_by" in fbm:
        _p(pdf, f"  decidido por: {fbm.get('trigger_decided_by') or 'NO DECLARADO'}"
                + (f" | competence: {comp_meta.get('competent')} ({comp_meta.get('decision_source')})" if comp_meta else "")
                + (f" | trigger legado por confianza: {fbm.get('trigger_legacy')}" if "trigger_legacy" in fbm else ""), size=7)
    else:
        _p(pdf, "  compuerta de competencia: el fb_meta no trae trigger_decided_by (registro anterior a ADR-0080)", style="I", size=7)
    if "council" in fbm:
        _p(pdf, f"  consejo (ADR-0082): {_j(fbm.get('council'), 300)}", size=7)
    resto = {k: v for k, v in fbm.items() if k not in ("tau", "competence", "trigger_decided_by", "trigger_legacy", "council")}
    if resto:
        _p(pdf, f"  fb_meta: {_j(resto, 400)}", size=7)
    otros = {k: v for k, v in fb.items() if k not in ("trigger", "fb_meta")}
    if otros:
        _p(pdf, f"  {_j(otros, 300)}", size=7)
    _rule(pdf)


def _section_modelos(pdf, record, ctx):
    if _grupo_ausente(pdf, record, grupo_de("models")):
        _rule(pdf)
        return
    m = record.get("models")
    if not isinstance(m, dict):
        _p(pdf, "models: null declarado", style="I", size=8)
        _rule(pdf)
        return
    _p(pdf, f"generacion {m.get('generation')} ({m.get('generation_source')})   |   tabla {m.get('table_version')} al "
            f"{m.get('table_as_of')}   |   panel_signature {m.get('panel_signature')}", style="B", size=9)
    roles = m.get("roles") if isinstance(m.get("roles"), dict) else {}
    for rol, r in roles.items():
        if isinstance(r, dict):
            _p(pdf, f"  rol {rol}: {r.get('model')}   |   fuente {r.get('model_source') or r.get('source')}"
                    + (f"   |   familia {r.get('family')}" if r.get("family") else "")
                    + (f"   |   api {r.get('api')}" if r.get("api") else "")
                    + (f"   |   procedencia {r.get('provenance')}" if r.get("provenance") else ""), size=7)
        else:
            _p(pdf, f"  rol {rol}: {'null declarado' if r is None else _j(r)}", size=7)
    ran = m.get("ran") if isinstance(m.get("ran"), dict) else {}
    for pasada, r in ran.items():
        if pasada == "panel":
            for pr in r or []:
                _p(pdf, f"  corrio panel/{pr.get('lens')}: pedido {pr.get('reviewer')} - reportado {pr.get('reported')} - "
                        f"relacion {pr.get('relation')} - api {pr.get('api_used')} - intentos {pr.get('attempts')}", size=7)
        elif isinstance(r, dict):
            _p(pdf, f"  corrio {pasada}: pedido {r.get('requested')} - reportado {r.get('reported')} - relacion {r.get('relation')}"
                    f" - thinking {r.get('thinking_state')}", size=7)
        else:
            _p(pdf, f"  corrio {pasada}: null declarado (la pasada no corrio)", size=7)
    if m.get("rule"):
        _p(pdf, f"regla: {m.get('rule')}", style="I", size=7)
    _rule(pdf)


def _panel_row(pdf, row, prefix="  - "):
    """Una fila del panel INTEGRA: identidad del juez, veredicto, hallazgos, intentos con error_kind, citation_support,
    y (ADR-0083 G.6) saw_figures en palabras + figure_readings con la placa JUICIO."""
    who = (f"{row.get('reviewer')} ({row.get('lens')}"
           + (f", familia {row.get('family')}" if row.get("family") else "")
           + (f", api {row.get('api')}" if row.get("api") else "") + ")")
    if row.get("status") == "errored":
        _p(pdf, f"{prefix}{who}: ERRORED - excluido, jamas fabricado"
                + (f" | error: {row.get('error')}" if row.get("error") else ""), size=8)
    else:
        caught = f" | atrapo: {row.get('caught')}" if row.get("caught") else ""
        _p(pdf, f"{prefix}{who}: {row.get('verdict')}{caught}"
                + (f" | confianza del juez {row.get('confidence')}" if row.get("confidence") is not None else ""), size=8)
        if row.get("reasons"):
            _p(pdf, f"      razones: {_j(row.get('reasons'), 400)}", size=7)
        if row.get("correction_applied"):
            _p(pdf, f"      correccion propuesta: {str(row.get('correction_applied'))[:400]}", size=7)
    meta = []
    for k in ("api_source", "reviewer_source", "max_tokens", "seat", "retries_judge"):
        if k in row and row.get(k) is not None:
            meta.append(f"{k} {row.get(k)}")
    attempts = row.get("attempts") if isinstance(row.get("attempts"), list) else []
    kinds = [a.get("error_kind") for a in attempts if isinstance(a, dict) and a.get("error_kind")]
    if attempts:
        meta.append(f"intentos {len(attempts)}" + (f" (error_kind: {', '.join(kinds)})" if kinds else ""))
    if isinstance(row.get("citation_support"), list):
        meta.append(f"citation_support {len(row['citation_support'])} filas")
    if meta:
        _p(pdf, "      " + "   |   ".join(meta), size=7)
    # ADR-0083 (G.6): lo que el juez VIO — medido desde lo entregado al caller
    sf = row.get("saw_figures")
    if isinstance(sf, dict):
        n = sf.get("n")
        detail = sf.get("detail")
        _p(pdf, f"      vio {n} figuras ({_SAW_DETAIL_GLOSS.get(detail, f'detalle fuera de tabla: {detail}')})"
                + (f" - sha {', '.join(str(s)[:12] for s in (sf.get('sha256s') or [])[:6])}" if sf.get("sha256s") else "")
                + (f" - {sf.get('bytes_b64_total')} bytes b64" if sf.get("bytes_b64_total") else ""), size=7)
    frs = row.get("figure_readings")
    if isinstance(frs, list) and frs:
        _p(pdf, f"      LECTURAS DE IMAGEN ({row.get('figure_readings_class') or 'model-judgment'}) - JUICIO DEL JUEZ SOBRE LA "
                "IMAGEN, no es medicion; nunca entra al gate ni a la compuerta:", style="B", size=7)
        for fr in frs:
            if isinstance(fr, dict):
                cwc = fr.get("consistent_with_caption")
                _p(pdf, f"        {fr.get('fig_id')}: {str(fr.get('reading'))[:400]} - "
                        f"{'consistente con el caption' if cwc is True else 'INCONSISTENTE con el caption' if cwc is False else 'consistencia no evaluada'}",
                   style="I", size=7)
    if row.get("figure_readings_dropped"):
        _p(pdf, f"      {row.get('figure_readings_dropped')} lecturas de imagen DESCARTADAS (fuera de vocabulario o id no entregado)", size=7)


def _section_auditoria(pdf, record, ctx):
    if _grupo_ausente(pdf, record, grupo_de("audit")):
        _rule(pdf)
        return
    audit = record.get("audit") or {}
    verdict = audit.get("verdict")
    ctx["verdict"] = verdict
    if audit:
        objetada = verdict == "REVISE"
        _band(pdf, (f"OBJETADA - {audit.get('tally', {}).get('REVISE', '?')} REVISE de "
                    f"{audit.get('n_valid')} validos - hallazgo negativo de primera clase") if objetada
              else f"APROBADA ({verdict}) - {audit.get('n_valid')} jueces validos",
              double=objetada)
        _p(pdf, f"vocabulario: {audit.get('source_vocabulary')}"
                + (f"   |   requerida porque: {audit.get('required_because')}" if audit.get("required_because") else "")
                + (f"   |   panel incompleto: {audit.get('panel_incomplete_reasons')}" if audit.get("panel_incomplete") else ""), size=8)
        for row in audit.get("panel", []):
            _panel_row(pdf, row)
        vis = audit.get("vision")
        if isinstance(vis, dict):
            _p(pdf, f"  vision del panel (ADR-0083): {'ENCENDIDA' if vis.get('enabled') else 'apagada'} - lentes "
                    f"{vis.get('lenses')} ({vis.get('lenses_source')}) - imagenes por lente {_j(vis.get('n_images_by_lens'), 200)} - "
                    f"{vis.get('bytes_b64_sent_total')} bytes b64 enviados [MEDICION del envio]", size=7)
        # --- CUORUM (ADR-0081 D) -----------------------------------------------------------------------------
        _h(pdf, "CUORUM (ADR-0081) - familias y lentes que votaron validas; la regla verbatim")
        q = audit.get("quorum")
        if isinstance(q, dict):
            def _gating(flag, val):
                return "APAGADA" if not flag else f"exige {val}"
            _p(pdf, f"validos {q.get('n_valid')} / minimo {q.get('min_valid')} ({_si(q.get('n_valid_ok'))})   |   familias presentes "
                    f"{_j(q.get('families_present'), 160)} - regla de familias {_gating(q.get('families_gating'), (q.get('min_families') or {}).get('value'))}"
                    f" ({(q.get('min_families') or {}).get('source')}) -> {_si(q.get('families_ok'))}   |   lentes presentes "
                    f"{q.get('lenses_present')} - regla de lentes {_gating(q.get('lenses_gating'), (q.get('min_lenses') or {}).get('value'))}"
                    f" ({(q.get('min_lenses') or {}).get('source')}) -> {_si(q.get('lenses_ok'))}", size=7)
            _p(pdf, f"cuorum {'OK' if q.get('ok') else 'FALLADO'} - fallos {q.get('failed')} - decidido por {q.get('decided_by')}", style="B", size=7)
            if q.get("rule"):
                _p(pdf, f"regla: {q.get('rule')}", style="I", size=7)
        else:
            _p(pdf, "audit.quorum: no consta en este registro (audit() anterior a ADR-0081 no midio cuorum por familias)", style="I", size=7)
        ps = audit.get("panel_source") if isinstance(audit.get("panel_source"), dict) else {}
        _p(pdf, f"familias validas {audit.get('families_valid')} ({audit.get('n_families_valid')})   |   lentes validas "
                f"{audit.get('lenses_valid')} ({audit.get('n_lenses_valid')})   |   modelos duplicados en el panel "
                f"{audit.get('panel_duplicate_models')}   |   origen del panel {audit.get('panel_origin')}"
                + (f"   |   council_hook {ps.get('council_hook')}" if ps else "")
                + (f"   |   reintentos por juez {(audit.get('judge_retries') or {}).get('value')} ({(audit.get('judge_retries') or {}).get('source')})"
                   if isinstance(audit.get("judge_retries"), dict) else ""), size=7)
    else:
        _band(pdf, "REQUERIDA Y PENDIENTE - sin veredicto registrado")
    # --- ciclo de revision (ADR-0067): nada se borra — grupo revision/audit_initial/answer_initial ------------------
    if not _grupo_ausente(pdf, record, grupo_de("revision"), prefijo="ciclo de revision: "):
        rev = record.get("revision") or {}
        if rev.get("performed"):
            _p(pdf, f"HUBO CICLO DE REVISION ({rev.get('cap')} de max {rev.get('cap')}, ADR-0067): "
                    f"veredicto inicial {rev.get('initial_verdict')} -> final {rev.get('final_verdict')}. "
                    f"La tabla de arriba es la ronda 1 (post-revision); la ronda 0 persiste abajo - "
                    f"NADA SE BORRA." + (f" Hallazgos usados: {rev.get('findings_used')}" if rev.get("findings_used") is not None else ""),
               style="B")
            ai = record.get("answer_initial") or {}
            _p(pdf, f"RONDA 0 - respuesta inicial (SUPERADA, no borrada): {ai.get('direct_answer')}",
               style="I", size=8)
            auditi = record.get("audit_initial") or {}
            for row in auditi.get("panel", []):
                if "verdict" in row:
                    _p(pdf, f"  - [ronda 0] {row.get('reviewer')} ({row.get('lens')}): {row.get('verdict')}",
                       size=8)
            q0 = auditi.get("quorum")
            if isinstance(q0, dict):
                _p(pdf, f"  [ronda 0] cuorum {'OK' if q0.get('ok') else 'FALLADO'} - {q0.get('n_valid')}/{q0.get('min_valid')} validos", size=7)
        elif rev.get("skipped_reason"):
            _p(pdf, f"[?] REVISE sin ciclo de revision - {rev['skipped_reason']}", size=8)
        elif rev:
            _p(pdf, f"ciclo de revision: no hubo (enabled {rev.get('enabled')}, cap {rev.get('cap')}) - audit_initial/answer_initial "
                    f"null declarados: {record.get('audit_initial') is None and record.get('answer_initial') is None}", size=7)
        else:
            _p(pdf, "revision: null declarado", size=7)
    _rule(pdf)


def _section_respuesta(pdf, record, ctx):
    if _grupo_ausente(pdf, record, grupo_de("answer")):
        _rule(pdf)
        return
    ans = record.get("answer") or {}
    if ctx.get("verdict") == "REVISE" or (ans.get("gap_flags") or []):
        _band(pdf, "RESPONDE CON HUECO DECLARADO - leer los huecos junto con la respuesta")
    _p(pdf, ans.get("direct_answer") or "(sin respuesta registrada)", size=10)
    ak = ans.get("absence_kind")
    if ak and ak != "not-applicable":
        _p(pdf, f"absence_kind: {ak} - {_ABSENCE_GLOSS.get(ak, ak)}", style="B", size=8)
    if "model" in ans:
        _p(pdf, f"modelo: {ans.get('model')} ({ans.get('model_source') or 'fuente no consta'})   |   reportado por la API: "
                f"{ans.get('model_reported')}   |   relacion {ans.get('relation')}", size=7)
    gaps = ans.get("gap_flags") or []
    if gaps:
        _h(pdf, "HUECOS DECLARADOS")
        for g in gaps:
            _p(pdf, f"  ! {g}", size=8)
    _rule(pdf)


def _section_confianza(pdf, record, ctx):
    if _grupo_ausente(pdf, record, grupo_de("confidence")):
        _rule(pdf)
        return
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
            partes.append(f"revision: {conf.get('revision')} ({conf.get('revision_source')})")
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
        _p(pdf, "confidence: null declarado", style="I")
    _rule(pdf)


def _pertinent_words(c):
    p = c.get("pertinent")
    if p is True:
        return f"pertinente (nombrada por el consejo para {c.get('pertinent_to')}; fuente {c.get('pertinent_source')})"
    if p is False:
        return "NO pertinente segun el consejo"
    if isinstance(p, str):
        return f"{p} (literal del consejo, ADR-0082)"
    return None


def _section_evidencia(pdf, record, ctx):
    if _grupo_ausente(pdf, record, grupo_de("citations")):
        _rule(pdf)
        return
    cits = record.get("citations")
    if cits is None:
        _p(pdf, "citations: null declarado", style="I", size=8)
    elif cits:
        for c in cits:
            support = (f"  -  soporte: {c.get('support_state')}" if "support_state" in c
                       else f"  -  soporte: NO INSTRUMENTADO (contrato < {born_of('citations_support_summary')})")
            pw = _pertinent_words(c)
            _p(pdf, f"  [{c.get('n')}] {c.get('kind')}: {c.get('id')}"
                    + (f" - {c.get('note')}" if c.get("note") else "") + support
                    + (f"  -  pertinente: {pw}" if pw else "")
                    + (f"  -  resuelta a {c.get('resolved_to')}" if c.get("resolved_to") else "")
                    # ADR-0084 (G.5): la cita a un paper web-localizado se marca sin fundirse con las nativas
                    + ("  -  localizado en la web (registro y texto de Europe PMC; ADR-0084)" if c.get("located_via") == "web" else ""), size=8)
            fv = c.get("figure_verification")
            if c.get("kind") == "figure" or isinstance(fv, dict):
                if isinstance(fv, dict):
                    b = fv.get("bytes")
                    bw = ("verificados por sha" if b == "verified" else "NO CUADRAN (mismatch)" if b == "mismatch"
                          else "no es una figura del bundle" if b == "not-a-figure" else f"{b}")
                    cw = "juicio del panel (lentes con vision)" if fv.get("content") == "panel-judgment" else "no evaluado"
                    _p(pdf, f"      figura {fv.get('figure_id')}: bytes {bw}   -   contenido: {cw} (la cita sostiene SOLO su caption)", size=7)
                else:
                    _p(pdf, "      figura: figure_verification no consta en esta cita", style="I", size=7)
    else:
        # [] con citations_schema: el esquema dice si es 'cito 0' medido o un bloque perdido; sin esquema no se distingue
        if "citations_schema" in record:
            _p(pdf, "citas: lista vacia MEDIDA - ver ESQUEMA DE CITAS para como llego el bloque", size=8)
        else:
            _p(pdf, f"citas []: medido-vacio o NO INSTRUMENTADO (contrato < {born_of('citations_schema')}): no distinguible, declarado",
               style="I", size=8)
    _rule(pdf)


def _section_esquema(pdf, record, ctx):
    if not _grupo_ausente(pdf, record, grupo_de("citations_schema")):
        cs = record.get("citations_schema")
        if not isinstance(cs, dict):
            _p(pdf, "citations_schema: null declarado", style="I", size=8)
        else:
            src = cs.get("source")
            phrase = _SCHEMA_SOURCE_PHRASE.get(src)
            if phrase is None:
                phrase = f"fuente fuera del vocabulario ({src}) - declarada"
            phrase = phrase.format(n_raw=cs.get("n_raw"), n_valid=cs.get("n_valid"), raw_type=cs.get("raw_type"))
            _p(pdf, f"source {src}: {phrase}", style="B", size=8)
            _p(pdf, f"n_raw {cs.get('n_raw')}   |   n_valid {cs.get('n_valid')}"
                    + (f"   |   raw_len_chars {cs.get('raw_len_chars')}" if cs.get("raw_len_chars") is not None else "")
                    + (f"   |   raw_type {cs.get('raw_type')}" if cs.get("raw_type") else "")
                    + (f"   |   nota: {cs.get('note')}" if cs.get("note") else ""), size=7)
    if not _grupo_ausente(pdf, record, grupo_de("evidence_cited_raw"), prefijo="evidence_cited_raw: "):
        raw = record.get("evidence_cited_raw")
        if raw is None:
            _p(pdf, "evidence_cited_raw: null declarado - no llego string crudo (el bloque vino tipado o ausente)", size=7)
        else:
            s = str(raw)
            _p(pdf, f"evidence_cited_raw (verbatim, raw_len {len(s)}{', plegado a 600' if len(s) > 600 else ''}): {s[:600]}", size=7)
    _rule(pdf)


def _section_soporte(pdf, record, ctx):
    if _grupo_ausente(pdf, record, grupo_de("citations_support_summary")):
        _rule(pdf)
        return
    s = record.get("citations_support_summary")
    if not isinstance(s, dict):
        _p(pdf, "citations_support_summary: null declarado", style="I", size=8)
        _rule(pdf)
        return
    ladder = s.get("ladder") or ["unresolved", "resolved", "passage_delivered", "supported", "unsupported"]
    by = s.get("by_state") if isinstance(s.get("by_state"), dict) else {}
    peldanos = "   |   ".join(f"{r}: {by.get(r) if by.get(r) is not None else 'null: no midio'}" for r in ladder)
    _p(pdf, f"estado {s.get('state')}   |   n {s.get('n')}   |   {peldanos}", style="B", size=8)
    extra_by = {k: v for k, v in by.items() if k not in ladder}
    if extra_by:
        _p(pdf, f"peldanos fuera de la escalera declarados: {_j(extra_by)}", size=7)
    pert = s.get("pertinent")
    if isinstance(pert, dict):
        _p(pdf, f"pertinencia (ADR-0082): {pert.get('state')} - true {pert.get('n_true')} | no nombradas {pert.get('n_not_named')} | "
                f"no disponible {pert.get('n_not_available')}" + (f" | regla: {pert.get('rule')}" if pert.get("rule") else ""), size=7)
    fc = s.get("figure_citations")
    if isinstance(fc, dict):
        _p(pdf, f"citas de figura (ADR-0083): n {fc.get('n')} - bytes verificados {fc.get('n_verified_bytes')} - no bajadas "
                f"{fc.get('n_not_fetched')} - error {fc.get('n_error') if 'n_error' in fc else 'no consta (< corrector)'} - mismatch "
                f"{fc.get('n_mismatch')} - sin resolver {fc.get('n_unresolved')}"
                + (f" - id de figura con otro kind {fc.get('n_figure_shaped_other_kind')}" if fc.get("n_figure_shaped_other_kind") else ""), size=7)
    if "n_located_via_web" in s:
        _p(pdf, f"citas a papers localizados por la web (ADR-0084): {s.get('n_located_via_web')} [MEDICION] - registro y texto de Europe PMC; "
                "la web solo localizo el identificador", size=7)
    if s.get("grounding_rows") is not None:
        _p(pdf, f"filas de grounding del panel: {s.get('grounding_rows')}", size=7)
    if s.get("ladder_rule"):
        _p(pdf, f"regla de la escalera: {s.get('ladder_rule')}", style="I", size=7)
    _rule(pdf)


# --- FIGURAS (ADR-0083 J.2) -----------------------------------------------------------------------------------
def _license_words(item, fg, ctx=None):
    lic = item.get("license") if isinstance(item.get("license"), dict) else {}
    lid = lic.get("id")
    table = fg.get("license_table") if isinstance(fg.get("license_table"), dict) else {}
    words = (table.get(lid) or {}).get("words_es")
    if not words and _figures is not None:
        words = (_figures.LICENSE_TABLE.get(lid) or {}).get("words_es")
    if not words:
        words = f"licencia fuera de vocabulario ({lid})"
    src = lic.get("source")
    parts = [words]
    if lic.get("version"):
        parts.append(f"v{lic.get('version')}")
    parts.append(_LICENSE_SOURCE_GLOSS.get(src, f"fuente fuera de tabla: {src}"))
    if lic.get("scope") == "figure-level":
        parts.append("licencia a nivel FIGURA (<fig>//<permissions>)")
    if isinstance(lic.get("conflict"), dict):
        parts.append(f"CONFLICTO xml {lic['conflict'].get('xml')} vs search {lic['conflict'].get('search')} - gana el XML")
    # el veredicto EFECTIVO viaja por figura (tabla ∧ env): se imprime el del registro, no el de la tabla sola
    if item.get("embeddable") and not _embeddable_now(item, ctx):
        # corrector: la env de HOY (WITT_FIGURES_EMBED_LICENSES) restringe una licencia que al congelar era embebible — la misma
        # puerta que el 403 del GET; el PDF (canal unico de salida, ADR-0073) no puede embeber lo que el GET niega
        parts.append("embebible al congelar; NO embebible HOY (restringida por WITT_FIGURES_EMBED_LICENSES)")
    else:
        parts.append("embebible" if item.get("embeddable") else "NO embebible")
    return " - ".join(parts)


def _embeddable_now(item, ctx):
    """embeddable EFECTIVO al imprimir = el congelado ∧ la tabla restringida por la env de HOY (misma regla que app._embeddable_now
    para GET 200/403 — corrector ADR-0083). Sin lib.figures o sin cfg legible se imprime el congelado (declarado en ctx['cfg_state'])."""
    if not item.get("embeddable"):
        return False
    cfg = (ctx or {}).get("cfg")
    if cfg is None or _figures is None:
        return True
    lic_id = (item.get("license") or {}).get("id")
    try:
        return bool(_figures.license_flags(lic_id, cfg)[0])
    except Exception:
        return True


def _thumb(pdf, item, ctx):
    """Decide y (si procede) EMBEBE la miniatura. Devuelve la línea de palabras que la acompaña o la sustituye."""
    src_url = item.get("source_url") or "sin source_url"
    lic_id = (item.get("license") or {}).get("id")
    if not item.get("embeddable"):
        return f"miniatura: no embebible: {lic_id} - caption + enlace {src_url}"
    if not _embeddable_now(item, ctx):
        return (f"miniatura: embebible al congelar; NO embebible HOY (licencia {lic_id} restringida por WITT_FIGURES_EMBED_LICENSES de "
                f"la env actual - la misma puerta que el 403 de GET /figures) - caption + enlace {src_url}")
    if not ctx["thumbs"]:
        return f"miniatura: omitida por WITT_FIGURES_PDF_THUMBS=0 ({ctx['thumbs_source']}) - palabras + enlace {src_url}"
    if item.get("bytes_state") != "verified" or not item.get("sha256") or not item.get("cache_path_rel"):
        return f"miniatura: sin bytes verificados en el registro ({item.get('bytes_state')}) - enlace {src_url}"
    if _figures is None:
        return f"miniatura: lib.figures no disponible - no se puede verificar el sha; palabras + enlace {src_url}"
    if ctx["cache_dir"] is None:
        return f"miniatura: sin cache_dir - bytes no en caché; enlace {src_url}"
    chk = _figures.verify_cached(ctx["cache_dir"], item)
    if chk["state"] == "missing":
        return (f"miniatura: bytes no en caché del servidor (caché efímera, ADR-0083 E4) - sha {str(item.get('sha256'))[:12]} "
                f"declarado; enlace {src_url}")
    if chk["state"] == "mismatch":
        return (f"miniatura: bytes: mismatch - sha recalculado {str(chk.get('sha256_actual'))[:12]} != congelado "
                f"{str(item.get('sha256'))[:12]}; NO se embebe (ADR-0077); enlace {src_url}")
    size = chk.get("bytes") or 0
    if size > ctx["max_image_bytes"]:
        return f"miniatura omitida: {size} bytes > tope WITT_FIGURES_MAX_IMAGE_MB - enlace {src_url}"
    if ctx["n_thumbs"] >= THUMBS_MAX_N:
        return f"miniatura omitida por tope de {THUMBS_MAX_N} miniaturas por PDF - enlace {src_url}"
    if ctx["bytes_embedded"] + size > ctx["pdf_budget_bytes"]:
        return (f"miniatura omitida por tope de tamano del PDF ({ctx['pdf_max_mb']} MB; {ctx['bytes_embedded']} bytes ya embebidos) "
                f"- enlace {src_url}")
    try:
        data = Path(chk["path"]).read_bytes()
        pdf.image(io.BytesIO(data), w=THUMB_W_MM)
        ctx["n_thumbs"] += 1
        ctx["bytes_embedded"] += size
        return f"miniatura embebida ({size} bytes, sha256 recalculado == congelado; ancho {THUMB_W_MM:g} mm) - original: {src_url}"
    except Exception as e:   # un JPEG que fpdf/Pillow no decodifica: palabras + thumb_error, jamas un PDF roto
        return f"miniatura: thumb_error {type(e).__name__}: {str(e)[:120]} - palabras + enlace {src_url}"


def _section_figuras(pdf, record, ctx):
    if _grupo_ausente(pdf, record, grupo_de("figures")):
        _rule(pdf)
        return
    fg = record.get("figures")
    if not isinstance(fg, dict):
        _p(pdf, "figures: null declarado", style="I", size=8)
        _rule(pdf)
        return
    state = fg.get("state")
    _p(pdf, f"estado: {state} - {_figures_state_gloss(state)}", style="B", size=9)
    ks = fg.get("kill_switch")
    if isinstance(ks, dict):
        _p(pdf, f"kill_switch WITT_FIGURES={ks.get('WITT_FIGURES')} - excepciones declaradas al 1.11 byte a byte: "
                f"{ks.get('declared_exceptions')}", size=7)
    budget = fg.get("budget") if isinstance(fg.get("budget"), dict) else {}
    cache = fg.get("cache") if isinstance(fg.get("cache"), dict) else {}
    if "n_figures" in fg:
        _p(pdf, f"figuras {fg.get('n_figures')} - con caption {fg.get('n_with_caption')} - verificadas {fg.get('n_verified')} - "
                f"embebibles {fg.get('n_embeddable')} - vistas por el panel {fg.get('n_panel_view')} - licencia desconocida "
                f"{fg.get('n_unknown_license')} - no bajadas {fg.get('n_not_fetched')} - error {fg.get('n_error') if 'n_error' in fg else 'no consta'} - mismatch {fg.get('n_mismatch')} - "
                f"citadas {fg.get('n_cited') if fg.get('n_cited') is not None else 'null (no midio)'} [MEDICION]", size=8)
        _p(pdf, f"papers elegibles {fg.get('n_papers_eligible')} / seleccionados {fg.get('n_papers_selected')} / con XML "
                f"{fg.get('n_papers_with_xml')}   |   mecanismo {fg.get('mechanism')}   |   parser {fg.get('parser_version')} - "
                f"modulo {fg.get('module_version')} - tabla de licencias {fg.get('license_table_version')}"
                + (f" (env ignorada: {fg.get('license_table_env_ignored')})" if fg.get("license_table_env_ignored") else ""), size=7)
    if budget:
        _p(pdf, f"presupuesto {budget.get('used_s')} / {budget.get('total_s')} s"
                + (" - SOBREPASADO (papers pendientes declarados budget-exhausted)" if budget.get("over_budget") else "")
                + (f"   |   cache {cache.get('dir_source')} / {cache.get('dir_state')} - ttl {cache.get('ttl_days')} d - tope "
                   f"{cache.get('cache_max_mb')} MB - evicted {cache.get('evicted_n')}" if cache else ""), size=7)
    if fg.get("zfin_figures_state"):
        _p(pdf, f"ZFIN: {fg.get('zfin_figures_state')}", size=7)
    sel = fg.get("selection") if isinstance(fg.get("selection"), dict) else {}
    if sel:
        _p(pdf, f"seleccion: {sel.get('rule')}   |   enviadas al panel por lente {_j(sel.get('n_sent_to_panel_by_lens'), 200)}", size=7)
    vis = fg.get("vision") if isinstance(fg.get("vision"), dict) else None
    if vis is not None:
        vst = vis.get("state")
        _p(pdf, f"VISION: {vst} - {_VISION_STATE_GLOSS.get(vst, f'estado fuera de tabla: {vst}')}   |   lentes {vis.get('lenses')} "
                f"({vis.get('lenses_source')})   |   detail OpenAI {vis.get('openai_detail')}", style="B", size=7)
        sent = vis.get("sent") if isinstance(vis.get("sent"), dict) else None
        if sent:
            _p(pdf, f"envio: {sent.get('n_panels')} paneles - {sent.get('n_attempts_with_images')} intentos con imagenes - "
                    f"{sent.get('bytes_b64_sent_total')} bytes b64 [MEDICION] - tokens de vision proyectados "
                    f"{sent.get('visual_tokens_projected_total')} [PROYECCION]", size=7)
        cp = vis.get("cost_projection") if isinstance(vis.get("cost_projection"), dict) else None
        if cp:
            _p(pdf, f"costo de vision [PROYECCION, {cp.get('prices_source')}]: USD {cp.get('total_usd_projected')} - por lente "
                    f"{_j(cp.get('per_lens'), 300)}", size=7)
        if vis.get("rule"):
            _p(pdf, f"regla de lectura (verbatim): {vis.get('rule')}", style="I", size=7)
    if fg.get("license_table_rule"):
        _p(pdf, f"limite declarado de la licencia: {fg.get('license_table_rule')}", style="I", size=7)
    items = fg.get("items") if isinstance(fg.get("items"), list) else []
    if not items and state == "attached":
        _p(pdf, "items: lista vacia medida (papers con XML sin <fig>)", size=7)
    for it in items:
        if not isinstance(it, dict):
            continue
        dm = it.get("dims_measured") if isinstance(it.get("dims_measured"), dict) else None
        dims = (f"{dm.get('w')}x{dm.get('h')} px" if dm else "dims no medidas")
        match = it.get("dims_match")
        dims += (" (== declaradas)" if match is True else " (!= declaradas)" if match is False else " (declaradas no constan)")
        lenses = it.get("seen_by_lenses") or []
        vista = (f"vista por {len(lenses)} lentes ({', '.join(lenses)}): JUICIO - el sintetizador solo leyo el caption"
                 if lenses else "ninguna lente la vio")
        cited = it.get("cited_by_answer") or []
        _p(pdf, f"  {it.get('id')}   |   {it.get('label') or 'sin label'}   |   {_license_words(it, fg, ctx)}", style="B", size=8)
        _p(pdf, f"      sha256 {str(it.get('sha256'))[:16] if it.get('sha256') else 'sin sha (no bajada)'}   |   {dims}   |   "
                f"{it.get('media_type') or 'mime no medido'}{' (extension dice ' + str(it.get('mime_from_extension')) + ')' if it.get('mime_from_extension') and it.get('media_type') and it.get('mime_from_extension') != it.get('media_type') else ''}"
                f"   |   {it.get('bytes') if it.get('bytes') is not None else '?'} bytes   |   {_bytes_state_words(it.get('bytes_state'))}", size=7)
        _p(pdf, f"      {vista}   |   {'citada como ' + ', '.join(f'[{n}]' for n in cited) if cited else 'no citada por la respuesta'}"
                f"   |   entregada al sintetizador (caption): {_si(it.get('delivered_to_synthesizer'))}"
                + ("   |   caption duplica texto ya entregado" if it.get("caption_in_excerpt") else "")
                + (f"   |   cache_hit {it.get('cache_hit')}" if it.get("cache_hit") is not None else ""), size=7)
        cap = it.get("caption") or ""
        if it.get("caption_state") == "present" and cap:
            _p(pdf, f"      caption: {cap[:400]}{'...' if len(cap) > 400 else ''}"
                    + (" [caption RECORTADO al tope al parsear]" if it.get("caption_truncated") else "")
                    + (f" (lang {it.get('caption_lang')})" if it.get("caption_lang") else ""), style="I", size=7)
        else:
            _p(pdf, "      caption: AUSENTE en el XML - no se entrego al sintetizador ni a las lentes", style="I", size=7)
        _p(pdf, f"      {_thumb(pdf, it, ctx)}", size=7)
    if items:
        _p(pdf, f"miniaturas embebidas: {ctx['n_thumbs']} ({ctx['bytes_embedded']} bytes) - regla: {THUMB_RULE}", size=7)
    _rule(pdf)


def _section_alternativas(pdf, record, ctx):
    if _grupo_ausente(pdf, record, grupo_de("alternatives_considered")):
        _rule(pdf)
        return
    alts = record.get("alternatives_considered")
    if alts is None:
        _p(pdf, "[?] null declarado - AUSENTE: hueco del sistema (distinto de 'no habia alternativas')", style="I", size=8)
    elif not alts:
        _p(pdf, "se consideraron y NO hubo alternativas viables (lista vacia declarada)", size=8)
    else:
        for a in alts:
            _p(pdf, f"  - {a}", size=8)
    _rule(pdf)


def _section_razonamiento(pdf, record, ctx):
    if _grupo_ausente(pdf, record, grupo_de("reasoning")):
        _rule(pdf)
        return
    r = record.get("reasoning")
    if not isinstance(r, dict):
        _p(pdf, "reasoning: null declarado", style="I", size=8)
        _rule(pdf)
        return
    fa = r.get("framework_applied")
    if isinstance(fa, dict):
        _p(pdf, f"marco declarado (clase self-report): {fa.get('name') or fa.get('framework') or 'ninguno'}"
                + (f"   |   seccion {fa.get('section')}" if fa.get("section") else "")
                + (f"   |   tier {fa.get('tier')}" if fa.get("tier") else "")
                + (f"   |   criterio en catalogo: {_si(fa.get('criterion_matches_catalog'))}" if "criterion_matches_catalog" in fa else "")
                + (f"   |   estado {fa.get('state')}" if fa.get("state") else ""), size=8)
        resto = {k: v for k, v in fa.items() if k not in ("name", "framework", "section", "tier", "criterion_matches_catalog", "state")}
        if resto:
            _p(pdf, f"  {_j(resto, 400)}", size=7)
    else:
        _p(pdf, f"marco declarado: {'null declarado' if fa is None else _j(fa)}", size=8)
    sf = r.get("structural_frameworks")
    if isinstance(sf, list):
        _p(pdf, f"marcos estructurales del pipeline (derivados del codigo, {len(sf)}): "
                + "; ".join((f"{x.get('name') or x.get('framework')} ({x.get('where') or x.get('section') or ''})".strip()
                            if isinstance(x, dict) else str(x)) for x in sf), size=7)
    else:
        _p(pdf, f"marcos estructurales: {'null declarado' if sf is None else _j(sf)}", size=7)
    _rule(pdf)


def _section_agentes(pdf, record, ctx):
    if _grupo_ausente(pdf, record, grupo_de("agents_invoked")):
        _rule(pdf)
        return
    rows = record.get("agents_invoked")
    if rows is None:
        _p(pdf, "agents_invoked: null declarado", style="I", size=8)
    elif not rows:
        _p(pdf, "agents_invoked: lista vacia declarada", size=8)
    else:
        for a in rows:
            if not isinstance(a, dict):
                _p(pdf, f"  - {_j(a)}", size=7)
                continue
            st = a.get("status")
            _p(pdf, f"  - {a.get('agent')}   |   {st}{' - CORRIO AD-HOC dentro de la sintesis (sin componente propio)' if st == 'skipped-ad-hoc' else ''}"
                    + (f"   |   invocation_id {a.get('invocation_id')}" if a.get("invocation_id") else "")
                    + (f"   |   razon: {a.get('reason')}" if a.get("reason") else "")
                    + (f"   |   proveedor {a.get('provider')}" if a.get("provider") else "")   # fila web_locator (ADR-0084 G.9)
                    + (f"   |   evidencia: {_j(a.get('evidence_generated'), 300)}" if a.get("evidence_generated") else ""), size=7)
    _rule(pdf)


def _section_plan(pdf, record, ctx):
    if _grupo_ausente(pdf, record, grupo_de("plan")):
        _rule(pdf)
        return
    plan = record.get("plan")
    _facet(pdf, record, "plan_declared", "plan declarado", record.get("plan_declared"), fmt=_si)
    _facet(pdf, record, "plan_question_matches_run", "la pregunta del plan es la de la corrida", record.get("plan_question_matches_run"),
           fmt=lambda v: "COINCIDE" if v else "NO COINCIDE - un plan hecho para OTRA pregunta (ADR-0044)")
    if plan is None:
        _p(pdf, f"plan: null declarado - razon: {_null_reason(record, 'plan') or 'no consta'}", size=8)
    elif isinstance(plan, dict):
        j = plan.get("judgment") if isinstance(plan.get("judgment"), dict) else {}
        pl = j.get("planner") if isinstance(j.get("planner"), dict) else {}
        _p(pdf, f"plan {plan.get('plan_id') or ''} - juicio del planner (clase {j.get('class')}, estado {j.get('state') or 'ok'}): "
                f"work_type {j.get('work_type')} - ruta {j.get('route')}   |   planner {pl.get('model')} ({pl.get('model_source')}; "
                f"procedencia {pl.get('provenance')})", size=8)
        agents = j.get("agents_applicable") if isinstance(j.get("agents_applicable"), list) else []
        niches = j.get("niches") if isinstance(j.get("niches"), list) else []
        _p(pdf, f"  agentes aplicables ({len(agents)}): {', '.join(str(a.get('agent') if isinstance(a, dict) else a) for a in agents) or 'ninguno'}"
                f"   |   nichos predichos ({len(niches)}): {', '.join(str(n.get('code') if isinstance(n, dict) else n) for n in niches) or 'ninguno'}"
                + (f"   |   council_state {j.get('council_state') or plan.get('council_state')}" if (j.get("council_state") or plan.get("council_state")) else ""), size=7)
        if "thread_parent_run_id" in plan:
            _p(pdf, f"  el plan declaro padre {plan.get('thread_parent_run_id')} con sha "
                    f"{str(plan.get('thread_parent_frozen_sha256'))[:16] if plan.get('thread_parent_frozen_sha256') else 'null'}", size=7)
        if j.get("error"):
            _p(pdf, f"  el juicio del planner FALLO: {j.get('error')} (un plan con juicio errado sigue siendo plan, §6)", size=7)
    else:
        _p(pdf, f"plan: {_j(plan)}", size=8)
    # corrector ADR-0079: procedencia plan<->padre (facetas 1.8 del grupo `plan`)
    _facet(pdf, record, "plan_parent_matches_run", "procedencia plan<->padre", record.get("plan_parent_matches_run"),
           fmt=lambda v: "COINCIDE - el padre que el plan declaro es el de la corrida" if v else "NO COINCIDE - el plan declaro OTRO padre",
           null_gloss=_PLAN_MATCH_NULL_GLOSS if "plan_parent_matches_run_state" in record else None,
           style="B" if record.get("plan_parent_matches_run") is False else "")
    if record.get("plan_parent_matches_run") is None and "plan_parent_matches_run" in record:
        _p(pdf, f"  plan_parent_matches_run_state: {record.get('plan_parent_matches_run_state') or 'no consta'}", size=7)
    _facet(pdf, record, "plan_snapshot_matches_run", "procedencia plan<->snapshot del padre", record.get("plan_snapshot_matches_run"),
           fmt=lambda v: "COINCIDE - el sha del padre que el plan declaro es el del snapshot que viajo" if v else "NO COINCIDE - el plan vio OTRO sha del padre",
           null_gloss=_PLAN_MATCH_NULL_GLOSS if "plan_snapshot_matches_run_state" in record else None,
           style="B" if record.get("plan_snapshot_matches_run") is False else "")
    if record.get("plan_snapshot_matches_run") is None and "plan_snapshot_matches_run" in record:
        _p(pdf, f"  plan_snapshot_matches_run_state: {record.get('plan_snapshot_matches_run_state') or 'no consta'}", size=7)
    _rule(pdf)


def _gating_words(pred):
    g = pred.get("gating")
    return "GATEA" if g else "informativo (gating false)" if g is False else "gating no consta"


def _ok_words(ok):
    return "OK" if ok is True else "FALLA" if ok is False else "null (no midio)"


def _section_gate(pdf, record, ctx):
    if _grupo_ausente(pdf, record, grupo_de("deterministic_checks")):
        _rule(pdf)
        return
    dc = record.get("deterministic_checks")
    if not isinstance(dc, dict):
        _p(pdf, "deterministic_checks: null declarado", style="I", size=8)
        _rule(pdf)
        return
    _p(pdf, f"pasada {dc.get('pass')}   |   admisible: {_si(dc.get('admissible'))}   |   razones: {dc.get('reasons')}"
            + (f"   |   pass1_admissible {_si(dc.get('pass1_admissible'))}" if "pass1_admissible" in dc else ""), style="B", size=8)
    ir = dc.get("identifier_report")
    if isinstance(ir, dict):
        conteos = {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in ir.items()}
        _p(pdf, f"identifier_report (conteos): {_j(conteos, 400)}", size=7)
    if "positive_claim_requires_citations" in dc:
        _p(pdf, f"positive_claim_requires_citations: {_si(dc.get('positive_claim_requires_citations'))}"
                f" ({dc.get('positive_claim_requires_citations_state') or 'estado no consta'})", size=7)
    cg = dc.get("competence_gate")
    if isinstance(cg, dict):
        _p(pdf, f"competence_gate (compacto): competent {cg.get('competent')} - not_applicable {cg.get('not_applicable')} - razones "
                f"{cg.get('reasons')} - componentes {_j(cg.get('components'), 240)}"
                + (f" - {cg.get('skipped_reason')}" if cg.get("skipped_reason") else ""), size=7)
    elif "competence_gate" in dc:
        _p(pdf, "competence_gate: null declarado", size=7)
    th = dc.get("thread")
    if isinstance(th, dict):
        _p(pdf, f"thread (resumen para el panel, sin prosa): turno {th.get('turn_no')} {th.get('turn_kind')} - padre "
                f"{th.get('parent_run_id') or 'ninguno'} (#{th.get('parent_run_no')}, veredicto {th.get('parent_verdict')}) - contexto disponible "
                f"{_si(th.get('context_available'))}", size=7)
    if "parent_identifier_leak" in dc:
        leak = dc.get("parent_identifier_leak")
        _p(pdf, f"parent_identifier_leak: {len(leak) if isinstance(leak, list) else leak} ({dc.get('parent_identifier_leak_state') or 'estado no consta'})"
                + (f" - IDENTIFICADORES DEL PADRE EN LA RESPUESTA: {leak}" if leak else ""), style="B" if leak else "", size=7)
    if "disjoint_series" in dc:
        _p(pdf, f"disjoint_series (numeros=evidencia, letras=precedente): {_si(dc.get('disjoint_series'))} "
                f"({dc.get('disjoint_series_state') or 'estado no consta'})", size=7)
    if "attestation_identifier_leak" in dc:
        leak = dc.get("attestation_identifier_leak")
        _p(pdf, f"attestation_identifier_leak (ADR-0082): {len(leak) if isinstance(leak, list) else leak} "
                f"({dc.get('attestation_identifier_leak_state') or 'estado no consta'})"
                + (f" - regla: {dc.get('attestation_identifier_leak_rule')}" if dc.get("attestation_identifier_leak_rule") else ""), size=7)
    cc = dc.get("council")
    if isinstance(cc, dict):
        _p(pdf, f"council (ADR-0082, clase {cc.get('class')}): estado {cc.get('state')} - must sin cubrir pre {cc.get('must_uncovered_pre')} / post "
                f"{cc.get('must_uncovered_post')} - votos alucinados {cc.get('n_hallucinated_votes')} - directivas {cc.get('n_directives')} - "
                f"requisitos keep {cc.get('n_requirements_kept')}", size=7)
    fgc = dc.get("figures")
    if isinstance(fgc, dict):
        _p(pdf, f"figures (ADR-0083): estado {fgc.get('state')} - decidido por {fgc.get('decided_by')}", style="B", size=7)
        for name in ("figure_id_resolves", "figure_sha_matches", "figure_only_not_asserted", "figure_numerals_grounded", "figure_license_known"):
            pred = fgc.get(name)
            if not isinstance(pred, dict):
                if name in fgc:
                    _p(pdf, f"  {name}: {_j(pred)}", size=7)
                continue
            extras = {k: v for k, v in pred.items() if k not in ("ok", "gating")}
            _p(pdf, f"  {name}: {_ok_words(pred.get('ok'))} - {_gating_words(pred)}" + (f" - {_j(extras, 300)}" if extras else ""), size=7)
        if isinstance(fgc.get("rules"), dict):
            for rn, rt in fgc["rules"].items():
                _p(pdf, f"  regla {rn}: {rt}", style="I", size=7)
    # ADR-0084 (E/G.3): 4 predicados web — 3 GATEAN (texto web no citado, cita web-localizada exige fetch, items solo nativos),
    # 1 informativo (URLs del ledger en la respuesta); bajo kill-switch EXACTAMENTE {state}; 'no-web-items' = medido con ceros
    wlc = dc.get("web_locator")
    if isinstance(wlc, dict):
        _p(pdf, f"web_locator (ADR-0084): estado {wlc.get('state')}"
                + (f" - decidido por {wlc.get('decided_by')}" if wlc.get("decided_by") else "")
                + (f" - modulo {wlc.get('module_version')}" if wlc.get("module_version") else "")
                + (" - la web localiza, no es fuente: 3 predicados GATEAN + 1 informativo" if any(k in wlc for k in WEB_GATE_PREDICATES) else ""),
           style="B", size=7)
        for name in WEB_GATE_PREDICATES:
            pred = wlc.get(name)
            if not isinstance(pred, dict):
                if name in wlc:
                    _p(pdf, f"  {name}: {_j(pred)}", size=7)
                continue
            extras = {k: v for k, v in pred.items() if k not in ("ok", "gating")}
            _p(pdf, f"  {name}: {_ok_words(pred.get('ok'))} - {_gating_words(pred)}" + (f" - {_j(extras, 300)}" if extras else ""), size=7)
        if isinstance(wlc.get("rules"), dict):
            for rn, rt in wlc["rules"].items():
                _p(pdf, f"  regla {rn}: {rt}", style="I", size=7)
    conocidas = {"pass", "admissible", "reasons", "identifier_report", "pass1_admissible", "positive_claim_requires_citations",
                 "positive_claim_requires_citations_state", "competence_gate", "thread", "parent_identifier_leak",
                 "parent_identifier_leak_state", "disjoint_series", "disjoint_series_state", "attestation_identifier_leak",
                 "attestation_identifier_leak_state", "attestation_identifier_leak_rule", "council", "figures", "web_locator"}
    resto = {k: v for k, v in dc.items() if k not in conocidas}
    if resto:
        _p(pdf, f"otras llaves del gate (sin glosa, verbatim): {_j(resto, 500)}", size=7)
    _rule(pdf)


def _section_nichos(pdf, record, ctx):
    if _grupo_ausente(pdf, record, grupo_de("niches")):
        _rule(pdf)
        return
    n = record.get("niches")
    if not isinstance(n, dict):
        _p(pdf, "niches: null declarado", style="I", size=8)
        _rule(pdf)
        return
    cat = n.get("catalogo")
    if isinstance(cat, dict):
        _p(pdf, f"catalogo [MEDICION, fichas del corpus citadas]: cobertura {cat.get('coverage')}   |   tipo de dato "
                f"{_j(cat.get('data') or cat.get('tipo_dato'), 160)}   |   dominio {_j(cat.get('dominio') or cat.get('domain'), 160)}"
                + (f"   |   sin ficha: {_j(cat.get('sin_ficha'), 160)}" if cat.get("sin_ficha") else ""), size=7)
    else:
        _p(pdf, f"catalogo: {'null declarado' if cat is None else _j(cat)}", size=7)
    pan = n.get("panel")
    if isinstance(pan, dict):
        _p(pdf, f"panel [JUICIO, clase {pan.get('class')}]: conteos {_j(pan.get('counts'), 200)} - clasificaron {pan.get('n_classified')} de "
                f"{pan.get('n_valid')} validos - jamas un ganador", size=7)
    else:
        _p(pdf, f"panel: {'null declarado (el panel no clasifico)' if pan is None else _j(pan)}", size=7)
    _rule(pdf)


def _thread_label(record, thread):
    """'T-<run_no de la raiz>' leido UNICAMENTE de thread.root_run_no (costura T5: runs._root_run_no lo sella
    en todo turno); si no consta, se DECLARA — jamas se infiere del run_id, del parent_run_no ni del turn_no."""
    root_no = thread.get("root_run_no")
    if root_no is not None:
        return f"T-{root_no}"
    return f"T-? (el run_no de la raiz no consta en el registro; thread_id={thread.get('thread_id')})"


def _section_investigacion(pdf, record, ctx):
    """ADR-0079: la investigacion a la que pertenece la corrida + precedente en LETRAS. Dos grupos: el hilo (ancla
    `thread`) y el precedente (ancla `precedent_citations`); el origen vive en IDENTIDAD."""
    if not _grupo_ausente(pdf, record, grupo_de("thread")):
        thread = record.get("thread") or {}
        if not thread:
            _p(pdf, "thread: null declarado - la corrida no pertenece a ninguna investigacion", style="I", size=8)
        else:
            kind = thread.get("turn_kind")
            _p(pdf, f"investigacion {_thread_label(record, thread)}   |   turno {thread.get('turn_no')} - "
                    f"{_TURN_KIND_GLOSS.get(kind, f'clase fuera de tabla: {kind}')}", style="B", size=9)
            if thread.get("parent_run_id"):
                _p(pdf, f"padre: corrida #{thread.get('parent_run_no')} ({thread.get('parent_run_id')}) en estado "
                        f"{thread.get('parent_state')}", size=8)
            else:
                _p(pdf, "padre: ninguno (turno raiz)", size=8)
            if thread.get("root_question_id"):
                _p(pdf, f"pregunta raiz (apunte): {thread.get('root_question_id')}", size=8)
            if "context_delivery" in thread:
                _p(pdf, f"entrega del contexto al sintetizador: {_j(thread.get('context_delivery'), 200)}", size=7)
        # el snapshot que el modelo vio: se declara si viajo o por que no (nunca se imprime entero)
        if "thread_context" in record:
            tc = record.get("thread_context")
            skipped = ((tc or {}).get("skipped_reason") or thread.get("thread_context_skipped_reason")
                       or thread.get("skipped_reason") or record.get("thread_context_skipped_reason"))
            if tc is None:
                _p(pdf, f"thread_context: null declarado - razon: {skipped or 'no consta'}", size=8)
            else:
                ks = tc.get("kill_switch") or {}
                hc = tc.get("human_comments")
                # T5 (integrador, ADR-0079 C): runs.py persiste human_comments como SOBRE {items, n_total,
                # n_included, truncated, class 'atestiguada'}; una lista cruda se tolera (lectura ADR-0074);
                # cualquier otra forma = 'no consta' (jamas se cuenta lo que no se sabe contar).
                if isinstance(hc, dict):
                    n_hc = f"{hc.get('n_included', '?')} de {hc.get('n_total', '?')}"
                    hc_trunc = bool(hc.get("truncated"))
                elif isinstance(hc, list):
                    n_hc, hc_trunc = str(len(hc)), bool(tc.get("truncated"))
                else:
                    n_hc, hc_trunc = "no consta", False
                _p(pdf, f"thread_context: viajo al modelo ({tc.get('bytes', '?')} bytes, snapshot {tc.get('snapshot_at')})"
                        f" - comentarios humanos: {n_hc}"
                        f"{' (TRUNCADOS al tope)' if hc_trunc else ''}"
                        f" - kill_switch WITT_THREAD_CONTEXT={ks.get('WITT_THREAD_CONTEXT', 'no consta')}"
                        + (f" - {skipped}" if skipped else "")
                        + (" - PADRE PRE-ADR-0079 (raiz virtual)" if tc.get("parent_pre_adr_0079") else ""),
                   size=8)
                _p(pdf, "excluido del snapshot por regla: valores y notas de calificacion (enmascarados por "
                        "solicitante, jamas promediados)", size=7)
        else:
            _p(pdf, "thread_context: no consta en este registro", size=7)
        if "thread_parent_matches_run" in record:
            m = record.get("thread_parent_matches_run")
            if m is None:
                # corrector ADR-0079: null NO es 'turno raiz' — el estado dice por que es null (un hijo con
                # kill-switch o con padre failed tambien trae null); estado ausente = no consta
                st = record.get("thread_parent_matches_run_state")
                glosa = _PARENT_MATCH_NULL_GLOSS.get(st, f"estado fuera de tabla: {st}" if st else "estado no consta")
                _p(pdf, f"identidad del padre: {glosa} - null declarado", size=8)
            else:
                _p(pdf, "identidad del padre: " + ("COINCIDE - el snapshot que vio el modelo es el registro "
                                                    "congelado del padre"
                                                    if m else
                                                    "NO COINCIDE - el snapshot NO corresponde al registro del padre"),
                   style="B" if m is False else "", size=8)
        else:
            _p(pdf, "identidad del padre: no consta en este registro", size=7)
        # ADR-0079/0083: la REGLA del sha se imprime LEIDA de la llave — jamas prosa fija
        rule = record.get("thread_parent_matches_run_rule")
        _p(pdf, f"regla del sha del padre: {rule if rule else 'regla no declarada en este registro'}", style="I", size=7)
    # precedente en LETRAS: la serie que no puede producir numeros
    if not _grupo_ausente(pdf, record, grupo_de("precedent_citations"), prefijo="precedente citado: "):
        pcs = record.get("precedent_citations") or []
        if not pcs:
            pst = record.get("precedent_citations_state")
            razon = _PRECEDENT_EMPTY_GLOSS.get(pst, f"estado fuera de tabla: {pst}" if pst else "razon no consta")
            _p(pdf, f"precedente citado: ninguno (lista vacia declarada - {razon})", size=8)
        for c in pcs:
            who = f"turno {c.get('turn_no')} - " if c.get("turn_no") is not None else ""
            no = f"corrida #{c.get('run_no')}" if c.get("run_no") is not None else c.get("run_id")
            _p(pdf, f"  [{c.get('l')}] {c.get('kind') or 'precedente'}: {who}{no} - {c.get('question')}"
                    f"  -  NO ADMISIBLE COMO EVIDENCIA", size=8)
    _rule(pdf)


def _section_consejo(pdf, record, ctx):
    """ADR-0082 (K.m): la seccion 'CONSEJO DE CRITERIO' nace con el bloque frozen.council. Tres estados: llave ausente
    (registro < 1.11) -> NO INSTRUMENTADO (calculado de KEY_BORN); `state` declarado sin rondas (kill-switch, no-ledger,
    not-requested, skip, errored); valor (membresia, ledger con decisiones, cobertura pre/post, rondas n/N, catalog_sha,
    costo r1/r2/r3). El consejo NUNCA escribe la respuesta: aqui solo se imprimen sus requisitos, decisiones humanas y coberturas."""
    if _grupo_ausente(pdf, record, grupo_de("council")):
        _rule(pdf)
        return
    c = record.get("council")
    if not isinstance(c, dict):
        _p(pdf, "council: null declarado - la corrida no congelo consejo", style="I", size=8)
        _rule(pdf)
        return
    state = c.get("state")
    _p(pdf, f"estado: {state} - {_council_state_gloss(state)}"
            + (f"   |   razon: {c.get('state_reason')}" if c.get("state_reason") else ""), style="B", size=9)
    ledger = c.get("ledger") if isinstance(c.get("ledger"), dict) else None
    rounds = [r for r in (c.get("rounds") or []) if isinstance(r, dict)]
    if ledger is None and not rounds:
        # estado declarado SIN rondas: nada mas que imprimir salvo la version y la membresia
        _p(pdf, f"membresia {c.get('membership_version')} - {c.get('n_members')} miembros"
                f"{' (full-council)' if c.get('full_council') else ''}   |   catalog_sha "
                f"{str(c.get('catalog_sha') or 'no consta')[:16]}...   |   kill_switch WITT_COUNCIL="
                f"{((c.get('kill_switch') or {}).get('WITT_COUNCIL') or 'unset')}", size=8)
        _rule(pdf)
        return
    model = c.get("model") or {}
    _p(pdf, f"membresia {c.get('membership_version')} ({c.get('membership_source')}) - {c.get('n_members')} miembros"
            f"{' (full-council)' if c.get('full_council') else ''} - cuorum {c.get('quorum_required')}   |   modelo "
            f"{model.get('requested')} ({model.get('source')}; effort {model.get('effort') or 'no enviado'})", size=8)
    pcm = c.get("plan_catalog_matches_run")
    _p(pdf, f"catalog_sha (al ejecutar) {str(c.get('catalog_sha') or 'no consta')[:16]}...   |   fichas del plan "
            + ("COINCIDEN" if pcm is True else "NO COINCIDEN - las fichas cambiaron entre plan y corrida" if pcm is False
               else "no verificable (plan sin catalog_sha)"), size=8)
    # ledger: decisiones humanas
    if ledger is not None:
        kn = ledger.get("knowledge_now") or {}
        _p(pdf, f"LEDGER {ledger.get('state')} - {ledger.get('n_requirements')} requisitos: {ledger.get('n_kept')} keep, "
                f"{ledger.get('n_discarded')} discard, {ledger.get('n_attested')} aportados, {ledger.get('n_pending')} pendientes, "
                f"{ledger.get('n_hard_rule')} hard-rule (causal-pruner)   |   aprobado por {ledger.get('approved_by') or 'nadie'}"
                f"{' (autor del plan)' if ledger.get('approved_by_is_author') else ''}"
                + (f"   |   saltado por {ledger.get('skipped_by')}: {ledger.get('skip_reason')}" if ledger.get("skipped_by") else ""),
           style="B", size=8)
        if kn.get("present"):
            _p(pdf, f"QUE SABES AHORA (ATESTIGUADO por {kn.get('by')}, {kn.get('chars')} chars"
                    f"{', RECORTADO a 600 en el registro' if kn.get('truncated') else ''}; NO es evidencia): {kn.get('text')}",
               style="I", size=8)
        cov = c.get("coverage") or {}
        pre = cov.get("pre_search") if isinstance(cov.get("pre_search"), dict) else {}
        post = cov.get("post_search") if isinstance(cov.get("post_search"), dict) else {}
        after = cov.get("after_search") if isinstance(cov.get("after_search"), dict) else {}
        pre_by = {b["requirement_id"]: b for b in (pre.get("by_requirement") or []) if isinstance(b, dict)}
        post_by = {b["requirement_id"]: b for b in (post.get("by_requirement") or []) if isinstance(b, dict)}
        after_by = {b["requirement_id"]: b for b in (after.get("by_requirement") or []) if isinstance(b, dict)}
        for r in ledger.get("requirements") or []:
            rid = r.get("requirement_id")
            head = (f"  [{r.get('priority')}] {rid}: {r.get('gap')}   -   {r.get('source_family')}/{r.get('evidence_kind')}"
                    f"   -   pedido por {r.get('n_requested_by')} de {r.get('n_members')}   -   decision {r.get('decision')}"
                    f" ({r.get('decided_by') or 'sin decidir'})")
            if r.get("hard_rule_gate"):
                head += "   -   HARD-RULE §7.1 (decision humana explicita)"
            if r.get("priority_downgraded_from"):
                head += f"   -   degradado de {r['priority_downgraded_from']} (exploratorio)"
            if r.get("harness_state") and r.get("harness_state") != "satisfiable":
                head += f"   -   {r['harness_state']} (no gatea, contado)"
            _p(pdf, head, size=7)
            if r.get("decision_reason"):
                _p(pdf, f"      razon del humano: {r['decision_reason']}", size=7)
            if r.get("attested_text"):
                _p(pdf, f"      ATESTIGUADO ({r.get('attested_chars')} chars{', recortado a 600' if r.get('attested_text_truncated') else ''}; "
                        f"no es evidencia): {r['attested_text']}", style="I", size=7)
            pb, qb, ab = pre_by.get(rid), post_by.get(rid), after_by.get(rid)
            if pb or qb or ab:
                partes = []
                if pb:
                    partes.append(f"pre-busqueda {pb.get('coverage_final')} ({_COVERAGE_GLOSS.get(pb.get('coverage_final'), '?')}; "
                                  f"{pb.get('n_valid_votes')} votos validos, {pb.get('n_annulled_votes')} anulados)")
                if ab and ab.get("state"):
                    partes.append(f"tras buscar: {ab['state']} ({_AFTER_SEARCH_GLOSS.get(ab['state'], '?')}"
                                  + (f", {ab.get('n_items_retrieved')} items" if ab.get("n_items_retrieved") else "") + ")")
                if qb:
                    partes.append(f"post-busqueda {qb.get('coverage_final')} ({qb.get('n_valid_votes')} votos validos)")
                _p(pdf, "      cobertura: " + "   |   ".join(partes), size=7)
                for v in (pb or {}).get("votes") or []:
                    if v.get("annulled"):
                        _p(pdf, f"      voto ANULADO de {v.get('agent')}: {v.get('annul_reason')} "
                                f"{v.get('hallucinated_evidence_ids') or ''}", style="B", size=7)
        for f in ledger.get("flags") or []:
            _p(pdf, f"  BANDERA §7 (gate humano) {f.get('kind')}: {f.get('statement')}   -   emitida por "
                    f"{', '.join(f.get('emitted_by') or [])}", style="B", size=7)
        if pre:
            _p(pdf, f"must: total {pre.get('must_total')} | SIN CUBRIR {pre.get('must_uncovered')} (uncovered {pre.get('must_uncovered_strict')}"
                    f" + partial {pre.get('must_partial')} + sin juzgar {pre.get('must_not_judged')}) | atestiguados {pre.get('must_attested')}"
                    f" | descartados {pre.get('must_discarded')} | no satisfacibles por el harness {pre.get('must_unsatisfiable')} (no gatean, E1)"
                    f" | votos alucinados {pre.get('n_hallucinated_votes')}   -   clase: {pre.get('class')}", size=7)
        elif isinstance(cov.get("pre_search"), dict):
            _p(pdf, f"cobertura pre-busqueda: {cov['pre_search'].get('state')}", size=7)
        if post and post.get("state") == "judged":
            _p(pdf, f"post-busqueda (r3 sobre {len((post.get('r3') or {}).get('members') or [])} duenos): must SIN CUBRIR "
                    f"{post.get('must_uncovered')}   -   INFORMATIVA (jamas re-gatea)", size=7)
        elif isinstance(cov.get("post_search"), dict):
            _p(pdf, f"post-busqueda: {cov['post_search'].get('state')}", size=7)
        if isinstance(after, dict) and "figures_available_n" in after:
            _p(pdf, f"figuras disponibles tras buscar (ADR-0083 O.2): {after.get('figures_available_n')}", size=7)
        d = c.get("directives") or []
        _p(pdf, f"directivas de busqueda compiladas por CODIGO: {len(d)} ({c.get('directives_state')})"
                + (f" -> familias {sorted({x.get('family') for x in d})}" if d else "")
                + (f"   |   excluidas {len(c.get('directives_excluded') or [])}" if c.get("directives_excluded") else ""), size=7)
    # rondas n/N y costo
    for r in rounds:
        u = r.get("usage") or {}
        cache = f" | cache creation {u.get('cache_creation')} / read {u.get('cache_read')}" if isinstance(u, dict) and ("cache_creation" in u or "cache_read" in u) else ""
        tag = " (COPIADA del plan: gastada ANTES de encolar)" if r.get("copied_from_plan_id") else ""
        _p(pdf, f"ronda {r.get('round')} ({r.get('kind')}, fase {r.get('phase')}){tag}: {r.get('n_valid')}/{r.get('n_members')} validos"
                f" - estado {r.get('state')} - invocados {r.get('n_invoked')} - errored {r.get('n_errored')} - timeout {r.get('n_timeout')}"
                f" - {r.get('elapsed_s')} s - tokens in {u.get('in') if isinstance(u, dict) else '?'} / out "
                f"{u.get('out') if isinstance(u, dict) else '?'}{cache} [MEDICION]", size=7)
    for s in c.get("rounds_skipped") or []:
        _p(pdf, f"ronda {s.get('round')} NO corrio: {s.get('reason')}", size=7)
    cache = c.get("cache") or {}
    if cache:
        _p(pdf, f"cache de prompt: {'activa' if cache.get('enabled') else 'apagada'} (ttl {cache.get('ttl')}) - hit_ratio_r2 "
                f"{cache.get('hit_ratio_r2') if cache.get('hit_ratio_r2') is not None else 'no medido'} [MEDICION]", size=7)
    _rule(pdf)


def _section_consumo(pdf, record, ctx):
    if not _grupo_ausente(pdf, record, grupo_de("token_usage")):
        tu = record.get("token_usage")
        if not isinstance(tu, dict):
            _p(pdf, "token_usage: null declarado", style="I", size=8)
        else:
            ti, to = tu.get("input_tokens"), tu.get("output_tokens")
            _p(pdf, f"COSTO: {ti:,} entrada / {to:,} salida [MEDICION]" if isinstance(ti, int) and isinstance(to, int)
                    else f"COSTO: {ti} entrada / {to} salida [MEDICION]", style="B", size=8)
            _p(pdf, f"USD {tu.get('estimated_cost_usd')} [PROYECCION: los tokens son medicion, los dolares no]"
                    + (f"   |   entrada TOTAL con cache {tu.get('input_tokens_total')}" if "input_tokens_total" in tu else "")
                    + (f"   |   proyeccion completa: {_si(tu.get('cost_projection_complete'))}" if "cost_projection_complete" in tu else "")
                    + (f"   |   SIN PRECIO (excluidos): {tu.get('missing_price_models')}" if tu.get("missing_price_models") else ""), size=8)
            if tu.get("cost_class"):
                _p(pdf, f"clase: {tu.get('cost_class')}", style="I", size=7)
            # ADR-0084 (G.7): el costo del localizador viaja APARTE (requests x tarifa) y el total que cuadra lleva su clase
            wlu = tu.get("web_locator")
            if isinstance(wlu, dict):
                _p(pdf, f"  localizador web (ADR-0084) - APARTE de los tokens [PROYECCION, clase {wlu.get('class')}]: USD {wlu.get('usd_projected')} - "
                        f"{wlu.get('n_queries_billable')} facturables de {wlu.get('n_queries')} consultas ({wlu.get('provider')}, USD "
                        f"{wlu.get('price_usd_per_1k')}/1k al {wlu.get('price_as_of')}) - resultados {wlu.get('n_results')} - localizados "
                        f"{wlu.get('n_located')} [MEDICION] - cuota {wlu.get('quota_state')}", size=7)
                wtk = wlu.get("tokens") if isinstance(wlu.get("tokens"), dict) else None
                if wtk:
                    _p(pdf, f"      tokens del despachador: in {wtk.get('in')} / out {wtk.get('out')} [MEDICION] - entran a by_model y a "
                            f"estimated_cost_usd bajo la etapa search", size=7)
            elif "web_locator" in tu:
                _p(pdf, "  localizador web (ADR-0084): null declarado", size=7)
            if "estimated_cost_usd_total_projected" in tu:
                _p(pdf, f"  TOTAL PROYECTADO (tokens x precio + localizador x tarifa): USD {tu.get('estimated_cost_usd_total_projected')} - "
                        f"clase: {tu.get('total_class') or 'no consta'}", size=7)
            bm = tu.get("by_model") if isinstance(tu.get("by_model"), dict) else {}
            for model, mv in bm.items():
                if isinstance(mv, dict):
                    _p(pdf, f"  modelo {model}: in {mv.get('in')} / out {mv.get('out')}"
                            + (f" - USD {mv.get('usd')} [E]" if "usd" in mv else "")
                            + (f" - {mv.get('price_state')}" if mv.get("price_state") else "")
                            + (f" - cache creation {mv.get('cache_creation')} / read {mv.get('cache_read')}" if ("cache_creation" in mv or "cache_read" in mv) else ""),
                       size=7)
            by_stage = tu.get("by_stage") if isinstance(tu.get("by_stage"), dict) else {}
            for stage, sv in by_stage.items():
                if not isinstance(sv, dict):
                    continue
                if stage == "panel":
                    _p(pdf, f"  etapa panel: in {sv.get('in')} / out {sv.get('out')} - por reviewer:", size=7)
                    for reviewer, rv in (sv.get("by_model") or {}).items():
                        vis = rv.get("vision") if isinstance(rv, dict) and isinstance(rv.get("vision"), dict) else None
                        _p(pdf, f"      {reviewer}: in {rv.get('in') if isinstance(rv, dict) else '?'} / out {rv.get('out') if isinstance(rv, dict) else '?'}"
                                + (f" - vision: {vis.get('n_images')} imagenes, ~{vis.get('visual_tokens_projected')} tokens [PROYECCION por "
                                   f"{vis.get('formula')}; ya incluidos en los input_tokens medidos"
                                   + (f"; medidos {vis.get('tokens_measured')}" if vis.get("tokens_measured") is not None else "") + "]" if vis else ""),
                           size=7)
                    continue
                if stage == "embed":
                    _p(pdf, f"  etapa embed: {sv.get('tokens')} tokens ({sv.get('unit')})", size=7)
                    continue
                if stage == "_sum":
                    _p(pdf, f"  suma de etapas: in {sv.get('in')} / out {sv.get('out')} - cuadra con by_model: "
                            f"{_si(tu.get('by_stage_sum_matches_by_model'))}", size=7)
                    continue
                inn, out = sv.get("in"), sv.get("out")
                _p(pdf, f"  etapa {stage}: in {inn if inn is not None else 'null'} / out {out if out is not None else 'null'}"
                        + (f" - modelo {sv.get('model')}" if "model" in sv else "")
                        + (f" ({sv.get('model_source')})" if sv.get("model_source") else "")
                        + (f" - estado {sv.get('state')}" if sv.get("state") else "")
                        + (f" - cache creation {sv.get('cache_creation')} / read {sv.get('cache_read')}" if ("cache_creation" in sv or "cache_read" in sv) else "")
                        + (f" - localizador web USD {sv.get('web_locator_usd_projected')} [PROYECCION]" if "web_locator_usd_projected" in sv else "")
                        + (f" - {sv.get('note')}" if sv.get("note") else ""), size=7)
            cache = tu.get("cache")
            if isinstance(cache, dict):
                _p(pdf, f"  cache de prompt (ADR-0082): creation {cache.get('creation_input_tokens')} / read {cache.get('read_input_tokens')} "
                        f"[MEDICION] - USD {cache.get('usd_projected')} [PROYECCION] - estado {cache.get('state')} - cuadra: "
                        f"{_si(tu.get('cache_sum_matches_by_model'))}", size=7)
            for k in ("plan_judgment", "council_judgment", "embedding"):
                if k in tu:
                    _p(pdf, f"  {k}: {'null declarado' if tu.get(k) is None else _j(tu.get(k), 300)}", size=7)
    if not _grupo_ausente(pdf, record, grupo_de("usage_raw"), prefijo="usage_raw: "):
        ur = record.get("usage_raw")
        if not isinstance(ur, dict):
            _p(pdf, "usage_raw: null declarado", size=7)
        else:
            passes = ur.get("passes") if isinstance(ur.get("passes"), dict) else {}
            _p(pdf, "usage_raw (crudo por pasada): " + "   |   ".join(f"{lab}: {_j(u, 120)}" for lab, u in passes.items())
                    + (f"   |   panel_total: {_j(ur.get('panel_total'), 120)}" if "panel_total" in ur else ""), size=7)
    cons = record.get("consensus")   # zona de servicio (app._ratings_view): conteos, jamas promedio
    if cons:
        _p(pdf, f"CONSENSO DE CALIFICACION: {cons.get('received')} de {cons.get('invited')} - "
                f"{'ABIERTO' if cons.get('open') else 'completo'} (conteo, jamas promedio - los "
                f"valores individuales viven en la app)", size=8)
    _rule(pdf)


RENDERERS = {
    "identidad": _section_identidad, "estado": _section_estado, "ejes": _section_ejes, "competencia": _section_competencia,
    "busqueda": _section_busqueda, "localizador": _section_localizador, "aportadas": _section_aportadas, "fallback": _section_fallback, "modelos": _section_modelos, "auditoria": _section_auditoria,
    "respuesta": _section_respuesta, "confianza": _section_confianza, "evidencia": _section_evidencia, "esquema": _section_esquema,
    "soporte": _section_soporte, "figuras": _section_figuras, "alternativas": _section_alternativas,
    "razonamiento": _section_razonamiento, "agentes": _section_agentes, "plan": _section_plan, "gate": _section_gate,
    "nichos": _section_nichos, "investigacion": _section_investigacion, "consejo": _section_consejo, "consumo": _section_consumo,
}
assert set(RENDERERS) == {s for s, _t in ORDEN_SECCIONES}


# ============================================================================================================
# build_pdf
# ============================================================================================================
def _figures_ctx(cache_dir, thumbs, pdf_max_mb):
    """Contexto de miniaturas: env leída EN LA LLAMADA (M.4) vía figures.env_config(); kwargs de los smokes mandan."""
    cfg = None
    if _figures is not None:
        try:
            cfg = _figures.env_config()
        except Exception:
            cfg = None
    if thumbs is None:
        thumbs_eff = bool(cfg["pdf_thumbs"]) if cfg else True
        thumbs_src = (cfg["sources"].get("pdf_thumbs") if cfg else "default (lib.figures no disponible)")
    else:
        thumbs_eff, thumbs_src = bool(thumbs), "kwarg thumbs"
    if cache_dir is not None:
        root = Path(cache_dir)
    elif _figures is not None:
        root = _figures.cache_dir()[0]
    else:
        root = None
    max_mb = float(pdf_max_mb) if pdf_max_mb is not None else PDF_MAX_MB
    return {"cache_dir": root, "thumbs": thumbs_eff, "thumbs_source": thumbs_src, "n_thumbs": 0, "bytes_embedded": 0,
            "pdf_max_mb": max_mb, "pdf_budget_bytes": max(0, int(max_mb * 1024 * 1024) - PDF_TEXT_RESERVE_BYTES),
            "max_image_bytes": (float(cfg["max_image_mb"]) if cfg else 5.0) * 1024 * 1024,
            # corrector: la cfg de HOY gobierna tambien la miniatura (WITT_FIGURES_EMBED_LICENSES restringe; jamas amplia)
            "cfg": cfg, "cfg_state": "env leida en la llamada (figures.env_config)" if cfg else "lib.figures no disponible: veredicto congelado"}


def build_pdf(record, compress=True, cache_dir=None, thumbs=None, now=None, pdf_max_mb=None):
    """El PDF (bytes) desde el registro congelado — jamás desde la página. Identidad primero.

    `cache_dir` (Path|str|None): raíz de la caché de figuras (default figures.cache_dir() por env); `thumbs` (bool|None):
    fuerza miniaturas sí/no (default WITT_FIGURES_PDF_THUMBS); `now` (datetime|None): fecha del pie y de creación del PDF
    (fija → bytes deterministas; default UTC ahora); `pdf_max_mb` (float|None): tope del PDF (default 8 MB)."""
    if record.get("question_matches_run") is False:
        raise ValueError("identidad rota: el registro no corresponde a la pregunta de la corrida "
                         "(question_matches_run=false) - la hoja no se dibuja y el PDF tampoco (ADR-0044)")
    now = now or datetime.datetime.now(datetime.timezone.utc)
    pdf = _Doc(format="A4")
    pdf.set_compression(compress)
    pdf.set_creation_date(now)
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()
    ctx = _figures_ctx(cache_dir, thumbs, pdf_max_mb)

    for seccion_id, titulo in ORDEN_SECCIONES:
        if titulo:
            _h(pdf, titulo)
        RENDERERS[seccion_id](pdf, record, ctx)

    ident = record.get("bundle_identity") or {}
    _p(pdf, f"Exportado del registro congelado el {now.isoformat(timespec='seconds')} - "
            f"identidad sha256: {str(ident.get('sha256', 'no consta'))[:16]}...  -  "
            f"Esta exportacion de servidor es EL UNICO canal autorizado para sacar una respuesta de "
            f"la app: copiar y pegar desde la pantalla pierde el estado epistemico. Texto normalizado "
            f"a latin-1 para el PDF (saneo declarado). Miniaturas: {ctx['n_thumbs']} embebidas, solo de figuras con licencia "
            f"embebible y sha256 verificado; el PDF jamas toca la red.", style="I", size=7)

    out = pdf.output()
    return bytes(out)


def build_pdf_from_json(path, compress=True, **kw):
    return build_pdf(json.loads(open(path, encoding="utf-8").read()), compress=compress, **kw)

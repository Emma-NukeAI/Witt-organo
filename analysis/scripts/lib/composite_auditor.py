"""
composite_auditor.py — the INVOKABLE composite auditor (tapón 3 / ADR-0049; block 3 of the webapp plan).

Until now `composite-auditor` was a ROLE agents played in-session (CLAUDE.md §7); the audit gate was
closed by a prose string (`required_next_action`) an agent had to read and obey, `record_audit()` had
zero callers, and the `audit` key was missing from 100% of producible runs. This module makes it a
COMPONENT with typed input/output — the founder decision of 2026-08-09 (audit on 100% of runs) is only
promisable if something actually audits.

Panel (ADR-0047 decision 4 — composición; ADR-0081 (A) — generación): los asientos salen de la TABLA
`lib/models.py` EN TIEMPO DE LLAMADA (`models.panel()`), jamás de un literal aquí — ningún id de modelo se
escribe en este módulo (gate estático M.4). g2-2026-09 (`models.GENERATIONS['g2-2026-09'].defaults`): tres
jueces Anthropic con three DISTINCT adversarial lenses (correctness = el modelo del sintetizador; overclaim =
el sonnet vigente; evidence-grounding = el haiku que se retira ≥ 2026-10-15 con sucesor declarado en la fila
`retiring` de la tabla) + un juez OpenAI (real cross-provider independence, ADR-0038; el puente
chat.completions hasta que el candidato Responses pase el gate en vivo LG3). La fila `excluded` de la tabla
(Fable) is EXCLUDED del panel (ADR-0081 supersede ADR-0031: 400 en tool_choice forzado observado y documentado
en su guía de migración; retención 30 días — decisión de Emmanuel). Kill-switch declarado:
WITT_MODEL_GENERATION=g1-2026-08 restaura el panel de f57a3d3 byte a byte.

Discipline inherited from the audited eval harness (ADR-0037/0038):
  - judges are HANDED the deterministic check results (verify_output / resolve_id) and FORBIDDEN to
    claim verification they did not run (the judge-fabrication fix);
  - an errored/unparseable judge is EXCLUDED and recorded as errored — never fabricated;
  - fewer than `min_valid` (default 3 — composite-auditor Mode 1 minimum) valid verdicts can NEVER
    approve: the overall verdict degrades to REVISE with `panel_incomplete: true` (conservative).

Vocabulary (ADR-0049): new runs speak `APPROVE | APPROVE_MINOR | REVISE`; every audit object carries
`source_vocabulary` so historic artifacts (record_audit approved/rejected · judge_answer 5-way ·
S-bank CONFIRMED/REVISE/REFUTED) keep their original vocabulary and are never force-mapped.
Aggregation is worst-of-N across valid reviewers (house rule — cf. retrieval_summary): a panel where
anyone caught something real must not average away the catch.

LLM calls are stdlib urllib (Anthropic) / openai SDK (OpenAI: Responses API por default de la tabla,
chat.completions como kill-switch byte a byte) — the exact pattern battle-tested in
evaluation/run_held_out.py. The caller is INJECTABLE so gates run offline and deterministic; el cliente
OpenAI se construye en `_openai_client()` (factory monkeypatcheable) y se puede inyectar por `client=`.

ADR-0080 (E — gate y panel):
  - VERDICT_TOOL gains the OPTIONAL property `citation_support: [{n, verdict}]` — only the
    evidence-grounding lens is charged with filling it (per numbered citation of the claim); every other
    judge ignores it. It feeds verify_output.support_state_for (the per-citation support ladder) and is
    parsed deterministically (parse_citation_support): an off-vocabulary entry is DROPPED and counted,
    never corrected in silence.
  - one ADDITIONAL attempt per errored/unparseable judge before excluding it (WITT_JUDGE_RETRIES,
    default 1; resolve_judge_retries declares the effective value + source). The row carries
    `retries_judge: n` (extra attempts actually made) and `attempts: [{attempt, status, error?}]` —
    a retried judge is visible, an exhausted one is `errored`; nothing is fabricated (ADR-0038).

ADR-0081 (C, D, K — este módulo):
  - (C.1) el juez OpenAI habla la Responses API (`_openai_responses_call`, kwargs de `_responses_kwargs`:
    strict False · store por WITT_OPENAI_STORE (default 0) · parallel_tool_calls False · tool_choice
    function · max_output_tokens por WITT_OPENAI_MAX_OUTPUT_TOKENS (default 4000) · reasoning.effort SÓLO
    con env + tabla `reasoning True`); `_openai_chat_call` = el caller de f57a3d3 byte a byte + max_retries=0
    + meta; `_default_caller` despacha por `member['api']` (C.3) y devuelve 3-tupla (out, usage, meta).
  - (C.2) vocabulario CERRADO de fallos: `CallerError(kind)` (legacy_type_name 'RuntimeError' → el string
    `attempts[].error` de hoy queda byte a byte) + `attempts[].error_kind`; FAILURE_KINDS_EXACT /
    FAILURE_KIND_PREFIXES / failure_kind_in_vocabulary (predicado del gate de paridad). El caller Anthropic
    gana los MISMOS kinds sin cambiar sus mensajes; `return_meta=True` devuelve (tool_input, usage, meta).
    Corrector (2026-09-15): en Responses un ítem `message` con content[].type 'refusal' → kind 'refusal' SIN
    reintento (antes caía en no-function-call y se reintentaba); la TRUNCACIÓN se decide por `status` ANTES de
    parsear (un function_call parcial ya no cae en arguments-unparseable); `meta` lleva el tope EFECTIVO de la
    llamada (max_output_tokens en Responses / max_tokens 1200 en chat) y _meta_into lo copia al intento —
    audit.panel[].max_tokens es null para el asiento OpenAI (su tope es del transporte) y el intento lo declara.
  - (D) cuórum por FAMILIAS y LENTES: families_valid / lenses_valid VIVEN AQUÍ (la promesa de ADR-0080 L41
    se cumple); WITT_PANEL_MIN_FAMILIES (default 2) y WITT_PANEL_MIN_LENSES (default 3), 0|1 = kill-switch
    declarado; ¬ok → REVISE estructural con `panel_incomplete_reasons` (códigos cerrados) — worst-of-N
    intacto cuando ok. Con ambos kill-switches el veredicto es EXACTAMENTE el de f57a3d3 (golden en
    smoke_panel_quorum.py).
  - (K) `directives` (ADR-0082) se acepta, se ignora y se DECLARA en `audit.panel_source`.

ADR-0082 (D.1 — el caller, aditivo; el consejo de criterio vive en lib/council.py):
  - `_anthropic_tool_call(..., tools=None)`: lista COMPLETA de tools a enviar (el consejo manda sus TRES byte a byte y
    fuerza la ronda con `tool_choice`); sin `tools=` el cuerpo es `[tool]`, el de hoy. `system` acepta `str` o
    `list[block]` con `cache_control` tal cual (prompt caching: bloque A compartido + ficha verbatim).
  - `_INFLIGHT = threading.BoundedSemaphore(WITT_ANTHROPIC_MAX_INFLIGHT=8)` alrededor de urlopen para TODA llamada
    Anthropic del proceso (consejo, síntesis, elicitación, planner, jueces) — `meta.queue_wait_s` lo mide.
  - `Retry-After` honrado en http-429/529 con tope WITT_ANTHROPIC_RETRY_AFTER_CAP_S (default 30); sin cabecera, el
    `_backoff(2·(intento+1))` de hoy; `CallerError.retry_after` y `meta.retry_after_honored_s`.
  - `meta.attempts` (intentos HECHOS) y `meta.usage_prior_attempts` (lo que la API cobró en intentos fallidos) para que
    el consejo sume TODO gasto de todo intento (C.3). La 2-tupla `return_meta=False` sigue byte a byte.
"""
import email.utils
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

# ADR-0081 (A): la tabla de modelos se importa EN DURO — sin fallback literal. Si falta, el módulo no
# importa y el smoke lo dice a gritos (mejor que un panel fantasma con literales desincronizados).
from lib import models

# ADR-0058 (decisión de Emmanuel, 2026-08-16): APPROVE_DECLINE distingue la DECLINACIÓN CORRECTA del
# claim rechazado. Las dos únicas corridas reales terminaron AUDIT_REJECTED por decir la verdad sobre
# una ausencia — si el panel castiga sistemáticamente la honestidad, todo hallazgo negativo (dato de
# primera clase en este proyecto) nace objetado y el equipo aprende a ignorar el veredicto. Una
# declinación correcta APRUEBA (severidad entre APPROVE y APPROVE_MINOR: la caracterización específica
# domina al approve genérico; cualquier issue real domina a ambas).
VOCABULARY = ("APPROVE", "APPROVE_DECLINE", "APPROVE_MINOR", "REVISE")
SOURCE_VOCABULARY = "APPROVE|APPROVE_DECLINE|APPROVE_MINOR|REVISE"
_SEVERITY = {"APPROVE": 0, "APPROVE_DECLINE": 1, "APPROVE_MINOR": 2, "REVISE": 3}

# ADR-0081 (A): snapshot DOCUMENTAL del panel g2 (env VACÍA, today = fecha de la tabla): NO es lo que corre.
# audit() resuelve `models.panel()` EN LA LLAMADA (env real, fecha real). El nombre se conserva para los
# lectores de f57a3d3 (runs._plan_structural lo listaba); no lee ninguna env en import.
DEFAULT_PANEL = models.panel(env={}, today=models.MODEL_TABLE_AS_OF)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# ADR-0080 (E): vocabulario del soporte por cita (mismo que verify_output.SUPPORT_VERDICTS — se
# duplica como literal para que este módulo siga sin importar lib.verify_output; el smoke los compara).
CITATION_SUPPORT_VERDICTS = ("supported", "unsupported", "not-assessable")
CITATION_SUPPORT_LENS = "evidence-grounding"

# ADR-0080 (E): UN reintento adicional por juez caído/ilegible antes de excluirlo. Lector: audit().
# Vacío o basura en la env → default DECLARADO (patrón _env_int_tolerante de ADR-0078), nunca tumba el import.
JUDGE_RETRIES_DEFAULT = 1
JUDGE_RETRIES_ENV = "WITT_JUDGE_RETRIES"

# ADR-0081 (C.1): el tope del camino chat.completions de f57a3d3 se CONSERVA (el kill-switch es byte a byte);
# el camino Responses lee WITT_OPENAI_MAX_OUTPUT_TOKENS (default 4000) de la tabla de env.
OPENAI_CHAT_MAX_TOKENS = 1200
# Tope por default del juez Anthropic cuando el member NO trae `max_tokens` (panel legado sin tabla): el de f57a3d3.
ANTHROPIC_JUDGE_MAX_TOKENS_LEGACY = 1200


def resolve_judge_retries(env=None):
    """(n_retries, source) con source ∈ 'env:WITT_JUDGE_RETRIES' | 'default-unset:WITT_JUDGE_RETRIES' |
    'default-invalid-env:WITT_JUDGE_RETRIES' | 'caller'. Negativos son inválidos (→ default declarado)."""
    raw = (os.environ if env is None else env).get(JUDGE_RETRIES_ENV)
    if raw is None or str(raw).strip() == "":
        return JUDGE_RETRIES_DEFAULT, f"default-unset:{JUDGE_RETRIES_ENV}"
    try:
        n = int(str(raw).strip())
    except ValueError:
        return JUDGE_RETRIES_DEFAULT, f"default-invalid-env:{JUDGE_RETRIES_ENV}"
    if n < 0:
        return JUDGE_RETRIES_DEFAULT, f"default-invalid-env:{JUDGE_RETRIES_ENV}"
    return n, f"env:{JUDGE_RETRIES_ENV}"


# ---------------------------------------------------------------------------------------------------------------
# ADR-0081 (C.2): vocabulario CERRADO de fallos del caller (viaja congelado en audit.failure_kinds_vocabulary)
# ---------------------------------------------------------------------------------------------------------------
class CallerError(RuntimeError):
    """Fallo TIPADO de un caller (Anthropic / OpenAI): `.kind` ∈ vocabulario (C.2). Hereda de RuntimeError para que
    ningún llamador de f57a3d3 (`except RuntimeError`) cambie; `legacy_type_name` = el nombre que audit() imprime
    en `attempts[].error` — 'RuntimeError' por default (el string de hoy queda BYTE A BYTE) o el nombre de la
    excepción del SDK que se envolvió (`_wrap`), para que un error de chat.completions se lea igual que en 1.9.
    `.usage` / `.meta` (opcionales): lo MEDIDO de un intento que erró después de que la API respondió (tokens
    cobrados, model_reported) — audit() lo conserva en el intento; una medición jamás se tira.
    `.retry_after` (ADR-0082 D.1): los segundos que la cabecera `Retry-After` pidió en el ÚLTIMO http-429/529 (None sin
    cabecera o sin ese código) — el consejo lo congela en la fila del miembro; el caller ya lo honró con tope."""
    legacy_type_name = "RuntimeError"

    def __init__(self, kind, message, legacy_type_name=None, usage=None, meta=None, retry_after=None):
        super().__init__(message)
        self.kind = kind
        if legacy_type_name:
            self.legacy_type_name = legacy_type_name
        self.usage = usage if isinstance(usage, dict) else None
        self.meta = meta if isinstance(meta, dict) else None
        self.retry_after = retry_after if isinstance(retry_after, (int, float)) and not isinstance(retry_after, bool) else None


FAILURE_KINDS_EXACT = ("no-api-key", "sdk-unavailable", "network", "refusal", "no-function-call",
                       "arguments-unparseable", "verdict-off-vocabulary", "unknown-family",
                       "incomplete:max_output_tokens", "incomplete:content_filter", "unclassified")
FAILURE_KIND_PREFIXES = ("http-", "response-failed:", "required-missing:")
FAILURE_KINDS_RULE = ("kind ∈ FAILURE_KINDS_EXACT o empieza por un FAILURE_KIND_PREFIXES ('http-<código>', "
                      "'response-failed:<código>', 'required-missing:<campos>'). Reintento de TRANSPORTE una vez en "
                      "http-429/500/502/503/529 y network; de CONTENIDO una vez en incomplete:*, no-function-call, "
                      "verdict-off-vocabulary, arguments-unparseable, required-missing:*; refusal y http-4xx NO se "
                      "reintentan (un clasificador determinista no cambia de opinión; 400/401/403/404 son configuración). "
                      "'unclassified' = excepción ajena al vocabulario (se registra tal cual, nunca se adivina).")
# (C.2) política de reintento del CALLER (la de audit(), WITT_JUDGE_RETRIES, es otra capa — ADR-0080, sin cambio).
RETRY_TRANSPORT_KINDS = ("http-429", "http-500", "http-502", "http-503", "http-529", "network")
RETRY_CONTENT_KINDS = ("incomplete:max_output_tokens", "incomplete:content_filter", "no-function-call",
                       "verdict-off-vocabulary", "arguments-unparseable")


def failure_kind_in_vocabulary(kind):
    """Predicado del gate de paridad (como plan_state_in_vocabulary): True si `kind` es exacto o lleva un prefijo
    del vocabulario con algo detrás."""
    if not isinstance(kind, str) or not kind:
        return False
    if kind in FAILURE_KINDS_EXACT:
        return True
    return any(kind.startswith(p) and len(kind) > len(p) for p in FAILURE_KIND_PREFIXES)


def failure_kinds_vocabulary():
    """{exact, prefixes, rule} — viaja congelado junto al dato (audit.failure_kinds_vocabulary)."""
    return {"exact": list(FAILURE_KINDS_EXACT), "prefixes": list(FAILURE_KIND_PREFIXES), "rule": FAILURE_KINDS_RULE}


def failure_kind_of(exc):
    """kind de CUALQUIER excepción por duck-typing (para que el smoke simule al SDK sin importar `openai`):
    `.kind` si ya es CallerError · `status_code` (int) → 'http-<code>' (HTTPError de urllib: `.code`) · clase
    APIConnectionError/APITimeoutError del SDK, TimeoutError, OSError, URLError → 'network' · resto → 'unclassified'."""
    kind = getattr(exc, "kind", None)
    if isinstance(kind, str) and kind:
        return kind
    code = getattr(exc, "status_code", None)
    if code is None and isinstance(exc, urllib.error.HTTPError):
        code = exc.code
    if isinstance(code, int) and not isinstance(code, bool):
        return f"http-{code}"
    names = {c.__name__ for c in type(exc).__mro__}
    if names & {"APIConnectionError", "APITimeoutError", "TimeoutError", "OSError", "URLError"}:
        return "network"
    return "unclassified"


def _error_string(e):
    """El string de `attempts[].error`: f"{tipo}: {mensaje[:200]}" — con `legacy_type_name` cuando la excepción lo
    trae, para que un CallerError se lea 'RuntimeError: …' (byte a byte con f57a3d3)."""
    return f"{getattr(e, 'legacy_type_name', type(e).__name__)}: {str(e)[:200]}"


def _wrap(e, kind=None):
    """Envuelve una excepción ajena (SDK openai, json) en CallerError conservando su NOMBRE de tipo y su mensaje
    (el `error` de hoy queda igual) y clasificándola por duck-typing si no se pasa `kind`."""
    if isinstance(e, CallerError):
        return e
    err = CallerError(kind or failure_kind_of(e), str(e), legacy_type_name=type(e).__name__)
    err.__cause__ = e
    return err


def _backoff(seconds):
    """Espera entre reintentos (2·(intento+1) s transporte, 1 s contenido — como f57a3d3). Separada para que
    los smokes la anulen sin tocar `time.sleep` global."""
    time.sleep(seconds)


# ---------------------------------------------------------------------------------------------------------------
# ADR-0082 (D.1): semáforo de PROCESO alrededor de urlopen para TODA llamada Anthropic (consejo, síntesis, elicitación,
# planner, jueces) y Retry-After honrado con tope en http-429/529. Lectores TOLERANTES: `models.ENV_TABLE` si C3 ya
# declaró la env (una sola verdad), si no un default local declarado — jamás tumba el import.
# ---------------------------------------------------------------------------------------------------------------
INFLIGHT_ENV = "WITT_ANTHROPIC_MAX_INFLIGHT"
INFLIGHT_DEFAULT = 8
RETRY_AFTER_CAP_ENV = "WITT_ANTHROPIC_RETRY_AFTER_CAP_S"
RETRY_AFTER_CAP_DEFAULT = 30
RETRY_AFTER_KINDS = ("http-429", "http-529")      # sólo aquí se lee la cabecera; 500/502/503 conservan el backoff de hoy


def _env_int_tolerant(name, default, minimum=0, env=None):
    """(valor, fuente): models.env_value si la env está en la tabla; si no, lectura local con el MISMO contrato
    (vacía → default-unset, basura/negativa → default-invalid-env)."""
    try:
        return models.env_value(name, env)
    except KeyError:
        pass
    raw = (os.environ if env is None else env).get(name)
    if raw is None or str(raw).strip() == "":
        return default, f"default-unset:{name}"
    try:
        v = int(str(raw).strip())
    except (ValueError, TypeError):
        return default, f"default-invalid-env:{name}"
    if v < minimum:
        return default, f"default-invalid-env:{name}"
    return v, f"env:{name}"


def inflight_limit(env=None):
    """(n, fuente) del tope de peticiones Anthropic en vuelo por proceso (default 8). Se lee al IMPORTAR (un
    BoundedSemaphore no se redimensiona; toda env = reinicio, ADR-0081 Context 10)."""
    return _env_int_tolerant(INFLIGHT_ENV, INFLIGHT_DEFAULT, minimum=1, env=env)


_INFLIGHT_LIMIT, _INFLIGHT_SOURCE = inflight_limit()
_INFLIGHT = threading.BoundedSemaphore(_INFLIGHT_LIMIT)
_INFLIGHT_RULE = ("BoundedSemaphore(WITT_ANTHROPIC_MAX_INFLIGHT) acquired around urlopen for EVERY Anthropic call in the "
                  "process (council members, synthesizer, elicitation, planner, judges); meta.queue_wait_s measures the "
                  "wait; it bounds REQUESTS in flight, not tokens per minute (ADR-0082 L.7)")


def retry_after_cap(env=None):
    return _env_int_tolerant(RETRY_AFTER_CAP_ENV, RETRY_AFTER_CAP_DEFAULT, minimum=0, env=env)


def _retry_after_seconds(headers):
    """Segundos de la cabecera Retry-After (entero o HTTP-date, RFC 7231 §7.1.3) o None sin cabecera / ilegible.
    Nunca negativo. `headers` es HTTPMessage (urllib) o dict (fakes) — se lee por duck-typing."""
    if headers is None:
        return None
    try:
        raw = headers.get("Retry-After") if hasattr(headers, "get") else None
        if raw is None and hasattr(headers, "get"):
            raw = headers.get("retry-after")
    except Exception:
        return None
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return max(0.0, float(s))
    except ValueError:
        pass
    try:
        dt = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError, IndexError):
        return None
    if dt is None:
        return None
    try:
        now = email.utils.parsedate_to_datetime(email.utils.formatdate(usegmt=True))
        return max(0.0, (dt - now).total_seconds())
    except Exception:
        return None


def _transport_wait(code, headers, attempt, cap_s):
    """(segundos a esperar, retry_after_crudo | None, honrado: bool) para un reintento de transporte: Retry-After con
    tope en 429/529; sin cabecera (o en 500/502/503) el `2·(intento+1)` de f57a3d3."""
    ra = _retry_after_seconds(headers) if f"http-{code}" in RETRY_AFTER_KINDS else None
    if ra is None:
        return 2 * (attempt + 1), None, False
    return min(ra, float(cap_s)), ra, True


def parse_citation_support(raw):
    """Parseo DETERMINISTA de `citation_support` tal como lo emitió el juez: (válidos, n_dropped).
    Válido = dict con n entero ≥1 y verdict del vocabulario; el primer veredicto por n gana, los demás y
    todo lo fuera de forma se DESCARTAN y se cuentan (ADR-0080: nada se corrige en silencio).
    raw que no es lista → ([], 0) con `emitted=False` decidido por el caller (no emitió ≠ emitió vacío)."""
    if not isinstance(raw, list):
        return [], 0
    out, seen, dropped = [], set(), 0
    for item in raw:
        if not isinstance(item, dict):
            dropped += 1
            continue
        n, v = item.get("n"), item.get("verdict")
        if isinstance(n, bool) or not isinstance(n, (int, float)) or int(n) != n or int(n) < 1 \
                or v not in CITATION_SUPPORT_VERDICTS or int(n) in seen:
            dropped += 1
            continue
        seen.add(int(n))
        out.append({"n": int(n), "verdict": v})
    return out, dropped


def citation_support_from_panel(rows):
    """La lista `citation_support` del juez de la lente evidence-grounding, para verify_output.
    support_state_for(grounding=...). None cuando ese juez erró o no la emitió (→ cada cita queda
    'not-evaluated': declarado, no rellenado). Si hubiera varios jueces con esa lente, se toma el
    primero con veredicto válido (el panel por default trae uno)."""
    for r in (rows or []):
        if r.get("lens") == CITATION_SUPPORT_LENS and "verdict" in r and isinstance(r.get("citation_support"), list):
            return r["citation_support"]
    return None

VERDICT_TOOL = {
    "name": "emit_audit_verdict",
    "description": ("Emit your adversarial audit verdict for the claim under your assigned lens. "
                    "APPROVE = no material issue found; "
                    "APPROVE_DECLINE = the claim HONESTLY DECLINES to answer (absence_kind declared) and "
                    "declining IS the correct epistemic move given the evidence — a correctly identified "
                    "absence is a first-class negative finding (it routes to re-ingest), NOT a defect; "
                    "APPROVE_MINOR = real but minor issues, state them; "
                    "REVISE = a material problem the answer must fix before it may be shown (including a "
                    "LAZY decline: refusing to answer when the evidence actually supported answering). "
                    "Report ONLY what you actually found in the provided material; you are handed the "
                    "deterministic verification results — do NOT claim any verification you did not run."),
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": list(VOCABULARY)},
            "caught": {"type": "string", "description": "the most important issue found ('' if none)"},
            "correction_applied": {"type": "string",
                                   "description": "the concrete correction the answer needs ('' if none)"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "reasons": {"type": "array", "items": {"type": "string"}},
            # 2026-09-05 (decisión del fundador): el eje de DOMINIO CIENTÍFICO lo pone el panel y
            # no el sintetizador, por la misma razón por la que el panel existe — la síntesis
            # calificándose a sí misma acompaña a su propio error. Va aquí, en la llamada que YA
            # corre en el 100% de las corridas: cuesta unos tokens de salida, no una llamada nueva.
            # Es OPCIONAL en `required`: un juez que no lo emita se cuenta como "no clasificó", que
            # es distinto de clasificar mal.
            "domain_niches": {
                "type": "array", "items": {"type": "string"},
                "description": ("Scientific-domain niches (N1–N6) this ANSWER belongs to, judged from "
                                "the claim and the evidence you were shown — codes ONLY, from the table "
                                "in your system prompt. Most specific first. Emit [] if the answer gives "
                                "you no basis: an empty list is an honest 'I cannot place it', and is "
                                "worth more than a guess. This is the DOMAIN axis (what field), never the "
                                "data-type axis (RN*) — that one is read from the catalog, not judged."),
            },
            # ADR-0080 (E): soporte POR CITA — sólo la lente evidence-grounding lo emite (su charge lo
            # pide); los demás jueces lo omiten. OPCIONAL en `required`: un juez que no lo emite "no
            # evaluó las citas" (support_state se queda en el peldaño determinista), que es distinto de
            # evaluar mal. verify_output.support_state_for lo consume; nunca se fabrica.
            "citation_support": {
                "type": "array",
                "items": {"type": "object",
                          "properties": {"n": {"type": "integer", "minimum": 1},
                                         "verdict": {"type": "string",
                                                     "enum": list(CITATION_SUPPORT_VERDICTS)}},
                          "required": ["n", "verdict"]},
                "description": ("evidence-grounding lens ONLY (other lenses: omit). For EACH numbered "
                                "citation [n] the claim makes, judge whether the passage delivered for "
                                "that citation in `evidence` supports the sentence it is attached to: "
                                "'supported' | 'unsupported' | 'not-assessable' (no passage shown for it, "
                                "or the claim sentence cannot be located). Judge ONLY citations whose "
                                "passage you were shown; never assert support from memory."),
            },
        },
        "required": ["verdict", "confidence"],
    },
}

_LENS_CHARGES = {
    "correctness": ("Try to REFUTE the claim: hunt for factual errors, wrong causal direction, or "
                    "conclusions the cited evidence does not support. Default toward REVISE when uncertain."),
    "overclaim": ("Hunt for OVER-CLAIMING: confidence not warranted by the evidence tier, 'validated' where "
                  "only 'measured' holds, hypothesis presented as finding, missing gap_flags. This project's "
                  "history shows over-claiming is its most recurrent failure."),
    "evidence-grounding": ("Check GROUNDING: does every asserted identifier/citation trace to the provided "
                           "evidence and the deterministic check results? Flag anything asserted from memory. "
                           "An identifier the deterministic gate marked unresolved is an automatic REVISE. "
                           "ADDITIONALLY (ADR-0080) fill `citation_support`: for EACH numbered citation [n] "
                           "in the claim, emit {n, verdict} with verdict 'supported' (the passage delivered "
                           "for it in `evidence` supports the sentence it is attached to), 'unsupported' "
                           "(the passage does not), or 'not-assessable' (no passage was delivered for that "
                           "citation, or the sentence cannot be located). Judge ONLY passages you were "
                           "shown; a citation with no passage is 'not-assessable', never 'supported'."),
    "reproducibility": ("As a cross-provider reviewer, check the reasoning chain END-TO-END: could an "
                        "independent reader reproduce the conclusion from the evidence shown? Flag leaps, "
                        "missing steps, and reliance on unstated knowledge. An honest decline IS "
                        "reproducible when an independent reader of the same evidence would also conclude "
                        "it is insufficient — that is APPROVE_DECLINE, not a defect (ADR-0058: this exact "
                        "lens vetoed both real runs for telling the truth about an absence)."),
}


def _niche_table() -> str:
    """La tabla de nichos de dominio, VISIBLE para el juez. Mismo principio que agent_matrix.digest():
    un juicio contra una tabla que el modelo nunca vio fabrica coincidencias. Si la matriz no se
    puede importar, se devuelve una instrucción que APAGA la clasificación en vez de dejar al juez
    inventando códigos contra un vocabulario que no conoce."""
    try:
        from lib import agent_matrix
        filas = "\n".join(f"  {c}: {d['name']} (fase: {d['phase_i']})"
                          for c, d in sorted(agent_matrix.NICHES.items()))
        return ("DOMAIN-NICHE TABLE (for `domain_niches` — use these codes and no others):\n"
                f"{filas}\n"
                "Place the ANSWER, not the question. Use [] when the answer gives you no basis; "
                "an honest empty list beats a guess. Do NOT emit RN* codes here: the data-type "
                "axis is read from the catalog, never judged.")
    except Exception:
        return ("DOMAIN-NICHE TABLE unavailable: emit `domain_niches` as [] — classifying against a "
                "vocabulary you were not shown would manufacture codes.")


def tally_domain_niches(rows, n_valid: int) -> dict:
    """Consenso del eje de dominio: CONTEOS, jamás un ganador (regla de la casa — promediar u
    'olegir el más votado' convertiría cuatro opiniones en un hecho). El denominador viaja: sin él,
    'N3: 2' no se distingue de 'N3: 2 de 2' contra 'N3: 2 de 4'.

    Un juez que erró NO clasificó: no cuenta ni a favor ni en contra, y su ausencia queda en la
    diferencia entre `n_valid` y `n_classified` (jamás se rellena)."""
    conteo, clasificaron = {}, 0
    for r in rows:
        if "verdict" not in r:
            continue                      # juez caído: excluido, nunca fabricado (ADR-0038)
        codigos = r.get("domain_niches")
        if not isinstance(codigos, list):
            continue                      # no emitió el campo: "no clasificó" ≠ "clasificó vacío"
        clasificaron += 1
        for c in {str(x).strip() for x in codigos if str(x).strip()}:
            conteo[c] = conteo.get(c, 0) + 1
    return {
        "class": "juicio",                # opinión del panel; el eje medido vive en el catálogo
        "counts": dict(sorted(conteo.items(), key=lambda kv: (-kv[1], kv[0]))),
        "n_valid": n_valid,
        "n_classified": clasificaron,
        "note": ("conteos de jueces por código, jamás un ganador: cuatro opiniones no hacen un "
                 "hecho. n_classified < n_valid = jueces que no clasificaron; su silencio no se "
                 "reparte entre los demás."),
    }


_TRAP_RE = re.compile(r'<parameter\s+name="([^"]+)">\s*([^<]*)', re.S)


def recover_trapped_params(tool_input):
    """Deterministic recovery of tool parameters the model emitted as XML-ish TEXT inside a string
    field — the finding of BOTH real production runs (LOTE-03 / ADR-0057): direct_answer ended with
    `…</parameter>\\n<parameter name="confidence">0.15`, so the value EXISTED but arrived as prose and
    the field read None ("ABSENT after retry" — falsely).

    A regex, not a judgment: (1) cut each string field at the first serialization artifact
    (`</parameter>` or `<parameter name=`) so the prose a doctor reads never ends in garbage;
    (2) lift trapped values into their fields ONLY where the field is absent/None (never overwrite a
    properly emitted value); (3) list what was lifted in `_recovered_fields` — a recovered value is
    NEVER silent: callers must surface provenance (the UI renders recovered ≠ clean measurement);
    (4) a trapped value that is itself a serialized JSON container (a LIST field like
    alternatives_considered trapped as text — ADR-0074, real run 9b3140ab froze it double-serialized
    and the sheet crashed) is parsed back; a failed parse keeps the raw string — never invented."""
    trapped, cuts = {}, {}
    for key, val in tool_input.items():
        if not isinstance(val, str):
            continue
        idxs = [i for i in (val.find("</parameter>"), val.find("<parameter name=")) if i != -1]
        if not idxs:
            continue
        cut = min(idxs)
        cuts[key] = val[:cut].rstrip()
        for name, raw in _TRAP_RE.findall(val[cut:]):
            raw = raw.strip()
            if not raw or name in trapped:
                continue
            if re.fullmatch(r"-?\d+(\.\d+)?", raw):
                trapped[name] = float(raw)
            elif raw[:1] in "[{":
                # ADR-0074: contenedor JSON atrapado como texto -> se parsea de vuelta (un array
                # con "<" adentro llega truncado por _TRAP_RE, el parse falla y el crudo queda)
                try:
                    trapped[name] = json.loads(raw)
                except ValueError:
                    trapped[name] = raw
            else:
                trapped[name] = raw
    tool_input.update(cuts)
    recovered = [n for n, v in trapped.items() if tool_input.get(n) is None]
    for n in recovered:
        tool_input[n] = trapped[n]
    if recovered:
        tool_input["_recovered_fields"] = sorted(recovered)
    return tool_input


def _numeric_usage(raw):
    """Lo NUMÉRICO que la API devolvió (la webapp tipa usage como Record<string, number>; ADR-0081 (B): ni
    `model_reported` ni `api` viajan dentro de usage). Aplana `output_tokens_details.thinking_tokens` →
    `thinking_tokens` (C.4: informativo, YA dentro de output_tokens; ausente si la API no lo manda — jamás 0)."""
    out = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = v
    details = raw.get("output_tokens_details")
    if isinstance(details, dict):
        tt = details.get("thinking_tokens")
        if isinstance(tt, (int, float)) and not isinstance(tt, bool):
            out["thinking_tokens"] = tt
    return out


def _anthropic_effort_for(model, env=None):
    """(C.4) `output_config.effort` para una llamada Anthropic: WITT_ANTHROPIC_EFFORT ∈ ANTHROPIC_EFFORTS Y el modelo
    tiene `thinking_default 'adaptive'` en la tabla; si no, None (= no se envía; default de la API). Un id que la
    tabla no conoce NO recibe effort (no se afirma que piense)."""
    effort, _ = models.env_value("WITT_ANTHROPIC_EFFORT", env)
    row = models.MODELS.get(model)
    return effort if (effort and row and row["thinking_default"] == "adaptive") else None


def _anthropic_content_kind(stop_reason, bad_verdict):
    """kind (C.2) cuando la respuesta NO trae un tool_use válido: stop_reason 'max_tokens' → incomplete:max_output_tokens
    (mismo literal que Responses: la webapp glosa UNA palabra) · 'refusal' (clasificadores de Opus 5, HTTP 200) →
    refusal · veredicto fuera del vocabulario → verdict-off-vocabulary · resto → no-function-call."""
    if stop_reason == "max_tokens":
        return "incomplete:max_output_tokens"
    if stop_reason == "refusal":
        return "refusal"
    if bad_verdict:
        return "verdict-off-vocabulary"
    return "no-function-call"


def _anthropic_tool_call(model, system, user_text, tool=None, timeout=120, retries=1, max_tokens=1200,
                         effort=None, return_meta=False, tools=None):
    """Forced-tool Messages call (urllib; the run_held_out.py pattern). Returns (tool_input, usage) — la 2-tupla de
    f57a3d3, INTACTA para todos los llamadores y fakes de hoy — o, con `return_meta=True` (ADR-0081 B),
    (tool_input, usage, meta) con meta = {model_reported: payload['model'], api: 'anthropic-messages', stop_reason,
    stop_details? (categoría del refusal, cuando la API la manda), response_id?, attempts (ADR-0082: intentos HECHOS),
    usage_prior_attempts? (el usage NUMÉRICO de los intentos previos que la API SÍ cobró — el consejo lo suma),
    queue_wait_s (espera en el semáforo de proceso, sumada sobre los intentos), retry_after_honored_s? (sólo si un
    429/529 trajo Retry-After y se esperó)} y usage NUMÉRICO con `thinking_tokens` aplanado (C.4). `tool` defaults
    to VERDICT_TOOL; the run synthesizer reuses this with its own schema (ADR-0050). `effort` (C.4): `output_config:
    {effort}` se envía SÓLO si el llamador lo pasa (S3/_default_caller lo deciden por env + tabla); el cuerpo NO cambia
    entre generaciones salvo `max_tokens` y ese bloque.
    ADR-0082 (D.1), aditivo: `tools=` es la lista COMPLETA a enviar (el consejo manda sus TRES tools byte a byte en
    toda llamada; `tool` sigue nombrando el forzado y debe estar en la lista) — sin `tools=` el cuerpo lleva `[tool]`,
    byte a byte el de hoy; `system` puede ser `str` (hoy) o `list[block]` (bloques `{type:'text', text, cache_control}`
    tal cual — el JSON los serializa igual); el semáforo de PROCESO `_INFLIGHT` se adquiere alrededor de urlopen;
    `Retry-After` se honra en http-429/529 con tope WITT_ANTHROPIC_RETRY_AFTER_CAP_S (sin cabecera, el backoff de hoy).
    Fallos → CallerError con kind (C.2) y los MISMOS mensajes de f57a3d3; refusal y http-4xx no se reintentan."""
    tool = tool or VERDICT_TOOL
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise CallerError("no-api-key",
                          "ANTHROPIC_API_KEY not set — add to .secrets/deploy.env / service env (never git).")
    if tools is not None:
        tools = list(tools)
        if tool["name"] not in {t.get("name") for t in tools}:
            raise ValueError(f"forced tool {tool['name']!r} is not in tools= {[t.get('name') for t in tools]}")
    body = {"model": model, "max_tokens": max_tokens, "system": system,
            "messages": [{"role": "user", "content": user_text}],
            "tools": tools if tools is not None else [tool], "tool_choice": {"type": "tool", "name": tool["name"]}}
    if effort:
        body["output_config"] = {"effort": effort}
    headers = {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}
    cap_s, _cap_src = retry_after_cap()
    last = None
    prior_usages = []                # (D.1) lo que la API cobró en intentos que NO valieron — nunca se tira
    queue_wait_total = 0.0
    honored_total = 0.0
    honored_any = False
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(ANTHROPIC_URL, data=json.dumps(body).encode("utf-8"),
                                         headers=headers, method="POST")
            t_q = time.monotonic()
            with _INFLIGHT:
                queue_wait_total += time.monotonic() - t_q
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            wait_s, ra, honored = _transport_wait(e.code, getattr(e, "headers", None), attempt, cap_s)
            last = CallerError(f"http-{e.code}", f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}",
                               meta={"api": "anthropic-messages", "attempts": attempt + 1,
                                     **({"usage_prior_attempts": list(prior_usages)} if prior_usages else {})},
                               retry_after=ra)
            if e.code in (429, 500, 502, 503, 529) and attempt < retries:
                if honored:
                    honored_any, honored_total = True, honored_total + wait_s
                _backoff(wait_s)
                continue
            raise last
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = CallerError("network", f"network error: {e}",
                               meta={"api": "anthropic-messages", "attempts": attempt + 1,
                                     **({"usage_prior_attempts": list(prior_usages)} if prior_usages else {})})
            if attempt < retries:
                _backoff(2 * (attempt + 1))
                continue
            raise last
        usage = payload.get("usage", {})
        meta = {"model_reported": payload.get("model"), "api": "anthropic-messages",
                "stop_reason": payload.get("stop_reason"), "attempts": attempt + 1,
                "queue_wait_s": round(queue_wait_total, 3)}
        if prior_usages:
            meta["usage_prior_attempts"] = list(prior_usages)
        if honored_any:
            meta["retry_after_honored_s"] = round(honored_total, 3)
        if payload.get("stop_details") is not None:
            meta["stop_details"] = payload["stop_details"]
        if payload.get("id"):
            meta["response_id"] = payload["id"]
        tool_input = next((b["input"] for b in payload.get("content", [])
                           if b.get("type") == "tool_use" and b.get("name") == tool["name"]), None)
        if tool_input is not None:
            # ADR-0057: recover BEFORE the required-fields check — a value trapped as text satisfies
            # `required` once lifted (with provenance), instead of burning a retry that repeats the
            # same malformation (observed: the retry ran and the model derailed identically).
            tool_input = recover_trapped_params(dict(tool_input))
        # (C.2) `bad_verdict` sólo aplica cuando SÍ hubo tool_use: sin tool_use el kind lo decide stop_reason
        # (max_tokens → incomplete · refusal → refusal · resto → no-function-call), no un verdict inexistente.
        bad_verdict = (tool_input is not None and tool["name"] == VERDICT_TOOL["name"]
                       and tool_input.get("verdict") not in VOCABULARY)
        if tool_input is None or bad_verdict:
            kind = _anthropic_content_kind(payload.get("stop_reason"), bad_verdict)
            last = CallerError(kind, f"no valid forced tool_use (stop_reason={payload.get('stop_reason')})",
                               usage=_numeric_usage(usage), meta=meta)
            # (C.2) el refusal es un clasificador determinista: repetir la misma petición no cambia la respuesta
            if kind != "refusal" and attempt < retries:
                prior_usages.append(_numeric_usage(usage))
                _backoff(1)
                continue
            raise last
        # The API does NOT enforce `required` (run_held_out lesson) — the FIRST real production run
        # (a361f566, 2026-08-10) came back with confidence omitted and it slipped through as a silent
        # null. Retry once on missing required fields; on the final attempt return what we got (the
        # caller flags the absence explicitly — a null must never masquerade as a measurement).
        required = tool.get("input_schema", {}).get("required", [])
        missing = [k for k in required if tool_input.get(k) is None]
        if missing and attempt < retries:
            last = CallerError(f"required-missing:{','.join(missing)}", f"tool_use omitted required fields {missing}",
                               usage=_numeric_usage(usage), meta=meta)
            prior_usages.append(_numeric_usage(usage))
            _backoff(1)
            continue
        if not return_meta:
            return tool_input, usage            # f57a3d3: la 2-tupla y el usage crudo, byte a byte
        return tool_input, _numeric_usage(usage), meta
    raise last  # pragma: no cover


# ---------------------------------------------------------------------------------------------------------------
# ADR-0081 (C.1): el juez OpenAI por la Responses API (el candidato de la tabla la EXIGE; verificado en vivo por Emmanuel)
# ---------------------------------------------------------------------------------------------------------------
def _openai_client(timeout=None):
    """Factory del cliente OpenAI (monkeypatcheable: los smokes devuelven un fake con .responses.create /
    .chat.completions.create). `OpenAI(timeout=timeout, max_retries=0)`: el SDK reintenta 2× EN SILENCIO por
    default (openai/_constants.py DEFAULT_MAX_RETRIES = 2) y `attempts[]` mentiría. Sin OPENAI_API_KEY →
    CallerError('no-api-key') ANTES de importar el SDK o tocar red; SDK no importable → 'sdk-unavailable'.
    `timeout` None → WITT_OPENAI_TIMEOUT_S (default 120 = f57a3d3)."""
    if timeout is None:
        timeout, _ = models.env_value("WITT_OPENAI_TIMEOUT_S")
    if not os.environ.get("OPENAI_API_KEY"):
        raise CallerError("no-api-key",
                          "OPENAI_API_KEY not set — add to .secrets/deploy.env / service env (never git).")
    try:
        from openai import OpenAI
    except ImportError as e:
        raise CallerError("sdk-unavailable", f"openai SDK not importable: {e}") from e
    return OpenAI(timeout=timeout, max_retries=0)


def _reasoning_effort_for(model, env=None):
    """(C.1) `reasoning.effort` SÓLO si WITT_OPENAI_REASONING_EFFORT ∈ low|medium|high Y la tabla marca
    `reasoning True` para el modelo (el puente chat lo rechazaría con 400); si no, None (no se envía)."""
    effort, _ = models.env_value("WITT_OPENAI_REASONING_EFFORT", env)
    row = models.MODELS.get(model)
    return effort if (effort and row and row["reasoning"]) else None


def _responses_kwargs(model, system, user_text, tool, max_output_tokens, store, reasoning_effort=None):
    """UNA función PURA que arma los kwargs de `client.responses.create` — la comparten el caller y
    analysis/scripts/smoke_live_models.py (S6), así no divergen. `strict: False` FIJO: `strict: true` exige todas
    las propiedades en `required` y rompería el tres-estados de `domain_niches`/`citation_support` (WITT_OPENAI_STRICT
    NO existe: una env que se sabe rompe el schema no se declara). `parallel_tool_calls: False` (un solo function_call).
    `store` (WITT_OPENAI_STORE, default 0: el default de la API es retención 30 días del lado OpenAI — se apaga y se
    declara, sin afirmar ZDR). `reasoning` sólo cuando `reasoning_effort` viene (ver _reasoning_effort_for)."""
    kwargs = {
        "model": model,
        "instructions": system,
        "input": user_text,
        "tools": [{"type": "function", "name": tool["name"], "description": tool.get("description", ""),
                   "parameters": tool["input_schema"], "strict": False}],
        "tool_choice": {"type": "function", "name": tool["name"]},
        "parallel_tool_calls": False,
        "max_output_tokens": int(max_output_tokens),
        "store": bool(store),
    }
    if reasoning_effort:
        kwargs["reasoning"] = {"effort": reasoning_effort}
    return kwargs


def _attr(obj, name, default=None):
    """Lectura duck-typed (objeto del SDK o dict de un fake)."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _responses_usage(usage):
    """usage NUMÉRICO de una Response: {input_tokens, output_tokens, reasoning_tokens (output_tokens_details; YA
    incluidos en output_tokens — informativos, nunca se suman aparte), cached_tokens (input_tokens_details),
    total_tokens} — sólo lo que la API mandó (jamás un 0 inventado)."""
    out = {}
    for k in ("input_tokens", "output_tokens", "total_tokens"):
        v = _num(_attr(usage, k))
        if v is not None:
            out[k] = v
    rt = _num(_attr(_attr(usage, "output_tokens_details"), "reasoning_tokens"))
    if rt is not None:
        out["reasoning_tokens"] = rt
    ct = _num(_attr(_attr(usage, "input_tokens_details"), "cached_tokens"))
    if ct is not None:
        out["cached_tokens"] = ct
    return out


def _responses_refusal(items):
    """(C.2, corrector) Texto del PRIMER `content[].type == 'refusal'` de un ítem `message` de una Response (el clasificador
    de OpenAI rehusó con HTTP 200 — el SDK lo modela como ResponseOutputRefusal) o None si no hay rechazo."""
    for it in items:
        if _attr(it, "type") != "message":
            continue
        for part in (_attr(it, "content") or []):
            if _attr(part, "type") == "refusal":
                return str(_attr(part, "refusal") or "")
    return None


def _openai_responses_call(model, system, user_text, tool=None, timeout=None, retries=1, max_output_tokens=None,
                           client=None, store=None, reasoning_effort=None):
    """Juez OpenAI por la Responses API. Devuelve SIEMPRE (tool_input, usage, meta) con meta = {model_reported:
    resp.model, api: 'openai-responses', response_id, status, incomplete_reason, max_output_tokens (el tope EFECTIVO
    enviado — corrector)}. Lee el ÚNICO ítem `output[].type == 'function_call'` con `name == tool['name']` (los ítems
    `reasoning` previos se ignoran; con parallel_tool_calls False no hay más de uno — si hubiera, se toma el primero),
    `json.loads(arguments)`, recover_trapped_params (ADR-0057), valida `verdict ∈ VOCABULARY` si la tool es
    VERDICT_TOOL, reintenta UNA vez los `required` ausentes y en el último intento devuelve lo recibido (misma disciplina
    que el caller Anthropic). Orden de decisión por respuesta (corrector): status 'failed' → response-failed:<code> ·
    ítem message con content[].type 'refusal' → 'refusal' SIN reintento (un clasificador determinista no cambia de
    opinión; un function_call junto a un rechazo NO se acepta) · status 'incomplete' (max_output_tokens|content_filter)
    → 'incomplete:<reason>' ANTES de parsear (un function_call parcial no es un bug de parseo; uno completo bajo status
    incomplete tampoco se devuelve: la API declaró la respuesta truncada) · sin function_call → 'no-function-call' ·
    arguments ilegibles → 'arguments-unparseable'. Reintentos (C.2): transporte en RETRY_TRANSPORT_KINDS, contenido en
    RETRY_CONTENT_KINDS; refusal, http-4xx y response-failed NO se reintentan.
    None en timeout/max_output_tokens/store/reasoning_effort → env de la tabla (WITT_OPENAI_*)."""
    tool = tool or VERDICT_TOOL
    if max_output_tokens is None:
        max_output_tokens, _ = models.env_value("WITT_OPENAI_MAX_OUTPUT_TOKENS")
    if store is None:
        store, _ = models.env_value("WITT_OPENAI_STORE")
    if reasoning_effort is None:
        reasoning_effort = _reasoning_effort_for(model)
    kwargs = _responses_kwargs(model, system, user_text, tool, max_output_tokens, store, reasoning_effort)
    if client is None:
        client = _openai_client(timeout)
    responses = getattr(client, "responses", None)
    if responses is None or not hasattr(responses, "create"):
        raise CallerError("sdk-unavailable",
                          "openai SDK without client.responses — the Responses API needs openai>=1.66 (requirements.txt)")
    last = None
    for attempt in range(retries + 1):
        try:
            resp = responses.create(**kwargs)
        except CallerError:
            raise
        except Exception as e:
            last = _wrap(e)
            if last.kind in RETRY_TRANSPORT_KINDS and attempt < retries:
                _backoff(2 * (attempt + 1))
                continue
            raise last
        status = _attr(resp, "status")
        inc = _attr(resp, "incomplete_details")
        inc_reason = _attr(inc, "reason") if inc is not None else None
        meta = {"model_reported": _attr(resp, "model"), "api": "openai-responses",
                "response_id": _attr(resp, "id"), "status": status, "incomplete_reason": inc_reason,
                # corrector: el tope EFECTIVO bajo el que corrió el juez (audit.panel[].max_tokens es null para OpenAI)
                "max_output_tokens": kwargs["max_output_tokens"]}
        usage = _responses_usage(_attr(resp, "usage"))
        if status == "failed":
            err = _attr(resp, "error")
            code = _attr(err, "code") if err is not None else None
            msg = _attr(err, "message") if err is not None else None
            raise CallerError(f"response-failed:{code or 'unknown'}",
                              f"openai responses: status failed ({code}: {str(msg)[:160]})", usage=usage, meta=meta)
        items = _attr(resp, "output") or []
        calls = [it for it in items
                 if _attr(it, "type") == "function_call" and _attr(it, "name") == tool["name"]]
        # (C.2, corrector) el clasificador de OpenAI rehusó (HTTP 200: ítem `message` con content[].type 'refusal') →
        # kind 'refusal' SIN reintento — el mismo guard que el caller Anthropic aplica a stop_reason 'refusal'. Un
        # function_call junto al rechazo no se acepta: de una respuesta que contiene un rechazo no se fabrica veredicto.
        refusal = _responses_refusal(items)
        if refusal is not None:
            raise CallerError("refusal", f"openai responses: refusal ({refusal[:120]})", usage=usage, meta=meta)
        # (C.2, corrector) la TRUNCACIÓN se decide por `status` ANTES de parsear: con status 'incomplete' un function_call
        # PARCIAL (arguments cortados) caía en 'arguments-unparseable' y el operador buscaba un bug de parseo donde la
        # causa era el tope (R1: el kind lo nombra → la webapp glosa 'sube WITT_OPENAI_MAX_OUTPUT_TOKENS'). Un
        # function_call completo bajo status 'incomplete' tampoco se devuelve: la API declaró la respuesta truncada.
        if status == "incomplete" and inc_reason in ("max_output_tokens", "content_filter"):
            fc_state = "presente (se descarta: la API declaró la respuesta truncada)" if calls else "ausente"
            last = CallerError(f"incomplete:{inc_reason}",
                               f"openai responses: incomplete ({inc_reason}); function_call {tool['name']!r} {fc_state}; "
                               f"output_types={[_attr(it, 'type') for it in items]}",
                               usage=usage, meta=meta)
            if attempt < retries:
                _backoff(1)
                continue
            raise last
        if not calls:
            last = CallerError("no-function-call",
                               f"openai responses: no function_call {tool['name']!r} (status={status}, "
                               f"incomplete_reason={inc_reason}, "
                               f"output_types={[_attr(it, 'type') for it in items]})",
                               usage=usage, meta=meta)
            if attempt < retries:
                _backoff(1)
                continue
            raise last
        args = _attr(calls[0], "arguments")
        try:
            out = args if isinstance(args, dict) else json.loads(args or "")
            if not isinstance(out, dict):
                raise ValueError("function_call.arguments is not a JSON object")
        except (ValueError, TypeError) as e:
            last = CallerError("arguments-unparseable",
                               f"openai responses: arguments not parseable ({type(e).__name__}: {str(e)[:120]})",
                               usage=usage, meta=meta)
            if attempt < retries:
                _backoff(1)
                continue
            raise last
        out = recover_trapped_params(dict(out))
        if tool["name"] == VERDICT_TOOL["name"] and out.get("verdict") not in VOCABULARY:
            last = CallerError("verdict-off-vocabulary", f"openai: invalid verdict {out.get('verdict')!r}",
                               usage=usage, meta=meta)
            if attempt < retries:
                _backoff(1)
                continue
            raise last
        required = tool.get("input_schema", {}).get("required", [])
        missing = [k for k in required if out.get(k) is None]
        if missing and attempt < retries:
            last = CallerError(f"required-missing:{','.join(missing)}", f"tool_use omitted required fields {missing}",
                               usage=usage, meta=meta)
            _backoff(1)
            continue
        return out, usage, meta
    raise last  # pragma: no cover


def _openai_chat_call(model, system, user_text, timeout=None, tool=None, client=None):
    """Cross-provider judge por chat.completions = el `_openai_tool_call` de f57a3d3 BYTE A BYTE en la petición
    (`max_tokens 1200`, tools/tool_choice function, messages system+user) + `max_retries=0` (vía _openai_client) +
    meta. Kill-switch declarado: WITT_OPENAI_API=chat-completions. Devuelve (verdict, usage, meta) con usage =
    `resp.usage.model_dump()` (como hoy) y meta = {model_reported: resp.model, api: 'openai-chat-completions',
    response_id, finish_reason, max_tokens (OPENAI_CHAT_MAX_TOKENS: el tope EFECTIVO — corrector)}. `tool` (ADR-0081 L.n: run_held_out delega aquí con SU tool) — la validación de
    `verdict` sólo aplica a VERDICT_TOOL. Sin reintentos propios (como hoy): audit() reintenta por WITT_JUDGE_RETRIES."""
    tool = tool or VERDICT_TOOL
    if timeout is None:
        timeout, _ = models.env_value("WITT_OPENAI_TIMEOUT_S")
    if client is None:
        client = _openai_client(timeout)
    fn = {"type": "function", "function": {"name": tool["name"],
                                           "description": tool["description"],
                                           "parameters": tool["input_schema"]}}
    try:
        resp = client.chat.completions.create(
            model=model, max_tokens=OPENAI_CHAT_MAX_TOKENS, timeout=timeout,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user_text}],
            tools=[fn], tool_choice={"type": "function", "function": {"name": tool["name"]}})
    except CallerError:
        raise
    except Exception as e:
        raise _wrap(e) from e
    choice = resp.choices[0]
    msg = choice.message
    finish = getattr(choice, "finish_reason", None)
    meta = {"model_reported": getattr(resp, "model", None), "api": "openai-chat-completions",
            "response_id": getattr(resp, "id", None), "finish_reason": finish,
            "max_tokens": OPENAI_CHAT_MAX_TOKENS}   # corrector: el tope EFECTIVO del camino chat, declarado
    usage = resp.usage.model_dump() if getattr(resp, "usage", None) else {}
    if not msg.tool_calls:
        kind = ("incomplete:max_output_tokens" if finish == "length"
                else "incomplete:content_filter" if finish == "content_filter" else "no-function-call")
        raise CallerError(kind, f"openai: no tool_call (finish_reason={finish})", usage=usage, meta=meta)
    try:
        out = json.loads(msg.tool_calls[0].function.arguments)
    except ValueError as e:
        raise CallerError("arguments-unparseable", str(e), legacy_type_name=type(e).__name__,
                          usage=usage, meta=meta) from e
    if tool["name"] == VERDICT_TOOL["name"] and out.get("verdict") not in VOCABULARY:
        raise CallerError("verdict-off-vocabulary", f"openai: invalid verdict {out.get('verdict')!r}",
                          usage=usage, meta=meta)
    return out, usage, meta


def _openai_tool_call(model, system, user_text, timeout=None, tool=None, client=None):
    """Nombre de f57a3d3, conservado como ALIAS del despachador OpenAI: el transporte lo decide la tabla
    (`models.api_of(model)`: el puente → chat.completions · el candidato / ids nuevos → Responses; WITT_OPENAI_API lo
    fuerza). Devuelve 3-tupla (out, usage, meta)."""
    api, _ = models.api_of(model)
    if api == "openai-chat-completions":
        return _openai_chat_call(model, system, user_text, timeout=timeout, tool=tool, client=client)
    return _openai_responses_call(model, system, user_text, tool=tool, timeout=timeout, client=client)


def _member_api(member):
    """(api, api_source) de un miembro del panel. Un PanelMember de la tabla trae `api`/`api_source`; un panel LEGADO
    (reviewer/family/lens de f57a3d3) lo infiere de la familia: anthropic → anthropic-messages · openai → la api de la
    tabla para ese id (el puente → chat.completions, como hoy; WITT_OPENAI_API la fuerza; id desconocido → Responses)
    con api_source 'inferred-from-family' · familia desconocida → (None, 'unknown-family')."""
    api = member.get("api")
    if api:
        return api, member.get("api_source") or "caller"
    fam = member.get("family") or models.family_of(member.get("reviewer"))[0]
    if fam == "anthropic":
        return "anthropic-messages", "inferred-from-family"
    if fam == "openai":
        api, _ = models.api_of(member.get("reviewer"))
        return (api or "openai-responses"), "inferred-from-family"
    return None, "unknown-family"


def _default_caller(member, system, user_text, tool=None):
    """(C.3) Despacho por `member['api']` (inferido de la familia si falta — _member_api): 'openai-responses' →
    _openai_responses_call · 'openai-chat-completions' → _openai_chat_call · 'anthropic-messages' →
    _anthropic_tool_call(max_tokens=member['max_tokens'] (tope de la generación; 1200 si el member no lo trae),
    effort por WITT_ANTHROPIC_EFFORT + tabla, return_meta=True) · familia desconocida → CallerError('unknown-family')
    SIN llamar a nada (fail-loud, no el `else: anthropic` de f57a3d3). Devuelve SIEMPRE (out, usage, meta).
    `tool` (ADR-0081 L.n): run_held_out.openai_verdict delega aquí con su propio tool."""
    api, _api_source = _member_api(member)
    reviewer = member.get("reviewer")
    if api == "openai-responses":
        return _openai_responses_call(reviewer, system, user_text, tool=tool)
    if api == "openai-chat-completions":
        return _openai_chat_call(reviewer, system, user_text, tool=tool)
    if api == "anthropic-messages":
        mt = member.get("max_tokens")
        max_tokens = mt if isinstance(mt, int) and not isinstance(mt, bool) and mt > 0 else ANTHROPIC_JUDGE_MAX_TOKENS_LEGACY
        return _anthropic_tool_call(reviewer, system, user_text, tool=tool, max_tokens=max_tokens,
                                    effort=_anthropic_effort_for(reviewer), return_meta=True)
    raise CallerError("unknown-family",
                      f"unknown-family: reviewer {reviewer!r} (family={member.get('family')!r}, api={api!r}) — "
                      f"la tabla no lo conoce y el prefijo no casa; se erra en voz alta, no se asume anthropic (ADR-0081 A)")


def _unpack_caller_result(res):
    """(out, usage, meta): acepta la 2-tupla de f57a3d3 (meta = {}) o la 3-tupla de ADR-0081 (B)."""
    if isinstance(res, tuple) and len(res) == 3:
        out, usage, meta = res
        return out, usage, (meta if isinstance(meta, dict) else {})
    out, usage = res
    return out, usage, {}


def _meta_into(entry, meta):
    """attempts[] += model_reported? / api? / max_output_tokens? (Responses) / max_tokens? (chat) — SÓLO cuando el caller
    los reportó (ausente ≠ null declarado). El tope efectivo (corrector) deja legible contra qué tope se truncó un juez
    OpenAI cuyo `audit.panel[].max_tokens` es null (su tope es del transporte, no de la tabla)."""
    if not isinstance(meta, dict):
        return
    if meta.get("model_reported"):
        entry["model_reported"] = meta["model_reported"]
    if meta.get("api"):
        entry["api"] = meta["api"]
    for k in ("max_output_tokens", "max_tokens"):
        v = meta.get(k)
        if isinstance(v, int) and not isinstance(v, bool):
            entry[k] = v


QUORUM_RULE = ("n_valid >= min_valid AND (NOT families_gating OR n_families_valid >= min_families) AND "
               "(NOT lenses_gating OR n_lenses_valid >= min_lenses); *_gating = (min >= 2): 0|1 = kill-switch declarado "
               "(>= 1 es tautológico con n_valid >= 1) — con ambos apagados la regla es EXACTAMENTE la de f57a3d3")


def _resolve_min(name, value):
    """(valor, fuente) de un mínimo del cuórum: del llamador ('caller', >= 0) o de la env de la tabla (tolerante)."""
    if value is None:
        return models.env_value(name)
    return max(0, int(value)), "caller"


def audit(claim, evidence, deterministic_checks=None, required_because="", panel=None,
          caller=None, min_valid=3, judge_retries=None, min_families=None, min_lenses=None, directives=None):
    """Run the Mode 1 split-and-vote panel over (claim, evidence). Returns the audit object the §5
    contract and the frozen record carry VISIBLY:

        {required, required_because, panel: [{reviewer, family, lens, verdict, caught,
         correction_applied, confidence, …, family_source, api, api_source, reviewer_source, max_tokens} |
         {reviewer, family, lens, status: 'errored', error, …}],
         tally, verdict, source_vocabulary, panel_incomplete?, panel_incomplete_reasons?, usage,
         domain_niches, judge_retries,
         families_valid, n_families_valid, lenses_valid, n_lenses_valid, panel_single_family, quorum,
         panel_duplicate_models, panel_origin, panel_source, failure_kinds_vocabulary}

    `deterministic_checks` (dict) is verify_output/resolve_id output — handed to every judge so nobody
    invents verification (ADR-0038). `caller(member, system, user_text) -> (verdict_dict, usage[, meta])` is
    injectable for offline gates; default = live Anthropic/OpenAI calls (_default_caller, 3-tupla); la 2-tupla de
    f57a3d3 sigue aceptada (meta = {}).

    ADR-0080 (E): `judge_retries` = ADDITIONAL attempts per errored/unparseable judge before it is
    excluded (None → WITT_JUDGE_RETRIES, default 1; declared in out["judge_retries"] {value, source}).
    Every row carries `retries_judge` (extra attempts actually made) and `attempts` [{attempt, status,
    error?, error_kind?, usage?, model_reported?, api?, max_output_tokens? | max_tokens? (tope efectivo del juez
    OpenAI — corrector)}]; the `member` handed to the caller carries `attempt: k`
    (1-based) so a heartbeat wrapper (runs.panel_caller → stage.audit.judge) can declare which attempt it
    announces. A judge that errors on every attempt stays `status: 'errored'` with the LAST error — never
    fabricated. The evidence-grounding judge's OPTIONAL `citation_support` is parsed (parse_citation_support)
    onto its row as `citation_support` + `citation_support_dropped`; a judge that did not emit it has no key.

    ADR-0081: `panel = panel or models.panel(directives=directives)` EN LA LLAMADA (A/K) — `panel_origin` declara si
    el panel vino del llamador o de la tabla; (D) cuórum por familias y lentes (WITT_PANEL_MIN_FAMILIES default 2,
    WITT_PANEL_MIN_LENSES default 3; `min_families=`/`min_lenses=` del llamador → source 'caller'; 0|1 = kill-switch):
    ¬ok → 'REVISE' + panel_incomplete True + panel_incomplete_reasons = quorum.failed (códigos cerrados: 'min_valid' |
    'families' | 'lenses', orden fijo); ok → worst-of-N intacto (APPROVE_DECLINE ADR-0058 se preserva). (C.2)
    attempts[].error conserva el string de f57a3d3 y gana error_kind (vocabulario en failure_kinds_vocabulary).
    """
    # ADR-0081 (A)/(K): el panel se resuelve EN LA LLAMADA (env y fecha reales); `directives` (ADR-0082) se acepta,
    # se ignora y se declara en panel_source. Con panel del llamador, panel_source describe la tabla de ESTA
    # llamada y `panel_origin 'caller'` deja claro que los asientos no salieron de ella.
    if panel:
        panel_origin, panel_source = "caller", models.panel_source(directives=directives)
    else:
        resolved = models.resolve_panel(directives=directives)
        panel, panel_source, panel_origin = resolved["panel"], resolved["panel_source"], "models.panel(directives)"
    caller = caller or _default_caller
    if judge_retries is None:
        judge_retries, retries_source = resolve_judge_retries()
    else:
        judge_retries, retries_source = max(0, int(judge_retries)), "caller"
    # ADR-0081 (D): mínimos del cuórum — env de la tabla (tolerante, default declarado) o llamador
    min_families, min_families_source = _resolve_min("WITT_PANEL_MIN_FAMILIES", min_families)
    min_lenses, min_lenses_source = _resolve_min("WITT_PANEL_MIN_LENSES", min_lenses)
    user_text = json.dumps({
        "claim": claim,
        "evidence": evidence,
        "deterministic_checks": deterministic_checks or {"note": "none provided"},
    }, ensure_ascii=False, indent=2, default=str)

    rows, usage_total = [], {}
    for member in panel:
        system = (f"You are one reviewer on an adversarial composite-audit panel (zebrafish pronephros "
                  f"research substrate). Your assigned lens: {member['lens']}. {_LENS_CHARGES[member['lens']]} "
                  f"HONEST-DECLINE DOCTRINE (ADR-0058): when the claim declines to answer WITH its "
                  f"absence_kind declared, judge whether DECLINING is the correct move given the evidence "
                  f"shown (external literature included, if fetched) — do NOT punish the decline for the "
                  f"absence itself: a correctly identified absence is a first-class negative finding of "
                  f"this system (it triggers the re-ingest loop). Correct decline -> APPROVE_DECLINE; "
                  f"decline despite sufficient evidence (lazy) -> REVISE. "
                  f"You are handed deterministic verification results in the input — cite them; NEVER claim "
                  f"a verification you did not run. Vote independently; other reviewers cover other lenses."
                  f"\n\n{_niche_table()}")
        # ADR-0081 (D): la identidad declarada del asiento viaja a la fila. Un PanelMember de la tabla trae todo; un
        # panel legado (reviewer/family/lens) lo declara como del llamador — jamás se rellena con la tabla.
        api, api_source = _member_api(member)
        family = member.get("family") or models.family_of(member.get("reviewer"))[0]
        family_source = member.get("family_source") or ("caller" if member.get("family") else "prefix")
        seat = {"family_source": family_source, "api": api, "api_source": api_source,
                "reviewer_source": member.get("reviewer_source") or "caller",
                "max_tokens": member.get("max_tokens")}
        # ADR-0080 (E): hasta 1 + judge_retries intentos por juez; cada intento queda en `attempts`.
        # El gasto MEDIDO de cada intento que devolvió usage (incluido un intento ILEGIBLE: la API cobró
        # esos tokens aunque el veredicto se descarte) se conserva por intento y se SUMA en la fila
        # (`usage`) — nunca se tira una medición (ADR-0051 / M8 reconcilia contra el gasto real).
        attempts, verdict, last_error, judge_usage = [], None, None, {}

        def _acc(into, usage):
            for k, v in (usage or {}).items():
                if isinstance(v, (int, float)):
                    into[k] = into.get(k, 0) + v

        for attempt in range(1, judge_retries + 2):
            entry = {"attempt": attempt}
            try:
                out_v, usage, meta = _unpack_caller_result(caller(dict(member, attempt=attempt), system, user_text))
                if isinstance(usage, dict) and usage:
                    entry["usage"] = usage
                    _acc(judge_usage, usage)
                _meta_into(entry, meta)     # ADR-0081 (B): lo que la API DIJO, medido — jamás copiado del member
                got = out_v.get("verdict") if isinstance(out_v, dict) else None
                if got not in VOCABULARY:
                    raise CallerError("verdict-off-vocabulary", f"unparseable judge output: verdict={got!r}")
                verdict = out_v
                entry["status"] = "ok"
                attempts.append(entry)
                break
            except Exception as e:
                last_error = _error_string(e)
                # ADR-0081 (C.2): el string `error` de f57a3d3 byte a byte + la palabra-máquina `error_kind`
                entry.update({"status": "errored", "error": last_error, "error_kind": failure_kind_of(e)})
                # un CallerError puede traer lo MEDIDO del intento fallido (la API respondió y cobró): se conserva
                e_usage = getattr(e, "usage", None)
                if isinstance(e_usage, dict) and e_usage and "usage" not in entry:
                    entry["usage"] = e_usage
                    _acc(judge_usage, e_usage)
                _meta_into(entry, getattr(e, "meta", None))
                attempts.append(entry)
                verdict = None
        retries_used = len(attempts) - 1
        usage = judge_usage
        if verdict is not None:
            row = {"reviewer": member["reviewer"], "family": family, "lens": member["lens"],
                   "verdict": verdict["verdict"], "caught": verdict.get("caught", ""),
                   "correction_applied": verdict.get("correction_applied", ""),
                   "confidence": verdict.get("confidence"),
                   "reasons": verdict.get("reasons", []),
                   # el eje de dominio POR JUEZ: se conserva crudo para que el consenso se
                   # pueda auditar renglón por renglón (y un código fuera de la tabla quede
                   # visible, no corregido en silencio)
                   **({"domain_niches": verdict["domain_niches"]}
                      if isinstance(verdict.get("domain_niches"), list) else {}),
                   "retries_judge": retries_used, "attempts": attempts,
                   "usage": usage or {},   # per-reviewer usage -> TokenUsage.by_model (ADR-0051)
                   **seat}
            # ADR-0080 (E): soporte por cita — sólo si el juez lo EMITIÓ como lista (no emitir ≠ emitir [])
            if isinstance(verdict.get("citation_support"), list):
                parsed, dropped = parse_citation_support(verdict["citation_support"])
                row["citation_support"] = parsed
                row["citation_support_dropped"] = dropped
            rows.append(row)
            for k, v in (usage or {}).items():
                if isinstance(v, (int, float)):
                    usage_total[k] = usage_total.get(k, 0) + v
        else:  # errored judge: EXCLUDED and recorded — never fabricated (ADR-0038)
            row = {"reviewer": member["reviewer"], "family": family, "lens": member["lens"],
                   "status": "errored", "error": last_error,
                   "retries_judge": retries_used, "attempts": attempts, **seat}
            if judge_usage:   # un intento ilegible que SÍ cobró tokens: gasto medido, declarado aquí también
                row["usage"] = judge_usage
                _acc(usage_total, judge_usage)
            rows.append(row)

    valid = [r for r in rows if "verdict" in r]
    tally = {v: sum(1 for r in valid if r["verdict"] == v) for v in VOCABULARY}
    # ADR-0081 (D): cuórum por FAMILIAS y LENTES. `families_valid` excluye 'unknown' (y cualquier etiqueta fuera de
    # models.FAMILIES): un asiento cuya familia no se sabe no aporta independencia — se ve en families_present.
    families_present, lenses_present = {}, []
    for r in valid:
        families_present[r["family"]] = families_present.get(r["family"], 0) + 1
        lenses_present.append(r["lens"])
    families_valid = sorted(f for f in families_present if f in models.FAMILIES)
    lenses_valid = list(dict.fromkeys(lenses_present))       # distintas, en el orden del panel
    n_valid, n_families_valid, n_lenses_valid = len(valid), len(families_valid), len(lenses_valid)
    families_gating, lenses_gating = min_families >= 2, min_lenses >= 2
    n_valid_ok = n_valid >= min_valid
    families_ok = (n_families_valid >= min_families) if families_gating else None
    lenses_ok = (n_lenses_valid >= min_lenses) if lenses_gating else None
    failed = [code for code, ok in (("min_valid", n_valid_ok), ("families", families_ok), ("lenses", lenses_ok))
              if ok is False]
    quorum = {"n_valid": n_valid, "min_valid": min_valid,
              "min_families": {"value": min_families, "source": min_families_source},
              "min_lenses": {"value": min_lenses, "source": min_lenses_source},
              "families_present": families_present, "lenses_present": lenses_present,
              "n_valid_ok": n_valid_ok, "families_ok": families_ok, "lenses_ok": lenses_ok,
              "families_gating": families_gating, "lenses_gating": lenses_gating,
              "ok": not failed, "failed": failed, "rule": QUORUM_RULE, "decided_by": "code"}
    counts = {}
    for m in panel:
        counts[m.get("reviewer")] = counts.get(m.get("reviewer"), 0) + 1
    out = {"required": True, "required_because": required_because, "panel": rows, "tally": tally,
           "source_vocabulary": SOURCE_VOCABULARY, "n_valid": n_valid, "usage": usage_total,
           "domain_niches": tally_domain_niches(rows, n_valid),
           # ADR-0080 (E): el reintento por juez viaja DECLARADO (valor efectivo + procedencia)
           "judge_retries": {"value": judge_retries, "source": retries_source,
                             "scope": "judge-call (additional attempts before exclusion)"},
           # ADR-0081 (D): cuórum declarado — los números viven aquí; los códigos en panel_incomplete_reasons
           "families_valid": families_valid, "n_families_valid": n_families_valid,
           "lenses_valid": lenses_valid, "n_lenses_valid": n_lenses_valid,
           "panel_single_family": n_families_valid <= 1, "quorum": quorum,
           # frontera declarada (D): el mismo modelo en dos lentes (p. ej. sonnet-5 tras el retiro de haiku) baja
           # la independencia DENTRO de la familia — se declara, no se disimula
           "panel_duplicate_models": sorted(mid for mid, n in counts.items() if n > 1),
           "panel_origin": panel_origin,
           # ADR-0081 (K): el hueco del consejo (ADR-0082), declarado sin implementarse
           "panel_source": panel_source,
           # ADR-0081 (C.2): el vocabulario de error_kind viaja congelado junto al dato
           "failure_kinds_vocabulary": failure_kinds_vocabulary()}
    if failed:
        # a thin panel — or one without cross-family / cross-lens independence — can NEVER approve:
        # REVISE ESTRUCTURAL (jueces caídos o sin diversidad, no un hallazgo sobre la respuesta — ADR-0067 la
        # revisión no aplica); conservative by construction (Mode 1 minimum >=3, ADR-0081 D)
        out["verdict"] = "REVISE"
        out["panel_incomplete"] = True
        out["panel_incomplete_reasons"] = failed
    else:
        out["verdict"] = max((r["verdict"] for r in valid), key=_SEVERITY.__getitem__)
    return out


# Llaves aditivas de ADR-0081 que apply_to_bundle copia al bundle['audit'] cuando el audit_result las trae.
_BUNDLE_AUDIT_KEYS_1_10 = ("families_valid", "n_families_valid", "lenses_valid", "n_lenses_valid",
                           "panel_single_family", "quorum", "panel_incomplete_reasons", "panel_duplicate_models",
                           "panel_origin", "panel_source", "failure_kinds_vocabulary")


def apply_to_bundle(bundle, audit_result, evidence_ids, answer_pipeline_module=None):
    """Feed the panel verdict to answer_pipeline.record_audit — its FIRST real caller — and enrich the
    bundle's `audit` key with the full panel table (visible, not just approved/rejected lists). The
    bundle identity is re-stamped after the enrichment (ADR-0044)."""
    if answer_pipeline_module is None:
        from lib import answer_pipeline as answer_pipeline_module
    approved_overall = audit_result["verdict"] in ("APPROVE", "APPROVE_DECLINE", "APPROVE_MINOR")
    # v1 granularity: the panel audits the claim+evidence as a whole; per-item verdicts are a refinement
    # (noted in ADR-0049). APPROVE/APPROVE_DECLINE/APPROVE_MINOR admits; REVISE rejects. ADR-0058: a
    # CORRECT decline terminates AUDIT_APPROVED — the negative finding is admitted as first-class.
    approved = list(evidence_ids) if approved_overall else []
    rejected = [] if approved_overall else list(evidence_ids)
    bundle = answer_pipeline_module.record_audit(
        bundle, approved, rejected,
        note=f"composite-auditor Mode 1: {audit_result['verdict']} "
             f"(valid {audit_result['n_valid']}/{len(audit_result['panel'])}, {SOURCE_VOCABULARY})")
    bundle["audit"].update({k: audit_result[k] for k in
                            ("required", "required_because", "panel", "tally", "verdict",
                             "source_vocabulary", "n_valid", "usage")})
    if "judge_retries" in audit_result:
        # ADR-0080 (E) C7 costura: la declaración {value, source} de los reintentos por juez acompaña a las
        # filas (retries_judge / attempts) hasta el registro congelado — sin ella el lector ve el reintento
        # pero no la regla que lo permitió
        bundle["audit"]["judge_retries"] = audit_result["judge_retries"]
    if audit_result.get("panel_incomplete"):
        bundle["audit"]["panel_incomplete"] = True
    # ADR-0081 (D)/(K)/(C.2): el cuórum, su regla, el hueco del consejo y el vocabulario de fallos viajan al registro
    # congelado junto a las filas (presentes sólo si el audit_result los trae: un resultado 1.9 no gana llaves)
    for k in _BUNDLE_AUDIT_KEYS_1_10:
        if k in audit_result:
            bundle["audit"][k] = audit_result[k]
    bundle["bundle_identity"] = answer_pipeline_module._identity(bundle)
    return bundle

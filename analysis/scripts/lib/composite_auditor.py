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

ADR-0083 (G — panel con visión; rebanada F3):
  - (G.1) VISION_LENSES = ('evidence-grounding', 'reproducibility'); `vision_lenses(env)` valida WITT_FIGURES_VISION_LENSES
    contra models.LENSES (fuera de vocabulario → default DECLARADO). (G.2) `audit(..., figures=None, vision_lenses=None)`:
    las figuras (figures.select_for_panel: panel_view ∧ verified ∧ caption present, b64 ya leída de la caché con el sha
    RECALCULADO) viajan DENTRO del `member` que recibe el caller — la firma caller(member, system, user_text) y todos los
    fakes/llamadores de hoy se conservan; la fila copia sólo reviewer/family/lens/seat → la b64 JAMÁS fuga al frozen.
  - (G.3) tres transportes: `_anthropic_tool_call(..., user_content=None)` (None → "content": user_text BYTE A BYTE),
    `_responses_kwargs/_openai_responses_call(..., user_content=None)` (None → "input": user_text) y `_openai_chat_call(...,
    user_content=None)` (None → content: user_text) — `_default_caller` arma los bloques con figures.anthropic_blocks /
    openai_responses_parts / openai_chat_parts (imágenes ANTES del texto, rotuladas) y sólo pasa el kwarg cuando hay
    figuras. El puente chat.completions ES la lente reproducibility de hoy: sin él "dos lentes" sería UNA en producción
    (forma declarada figures.OPENAI_CHAT_FORM_STATE; LG4 la mide). FIGURE_READING_RULE (literal) entra al system SOLO cuando
    de veras viajan imágenes.
  - (G.4) models.vision_tier_of / vision_tokens deciden si el asiento ve (none|unknown → 0 bloques, saw_figures.detail
    'model-vision-unknown') y PROYECTAN tokens de visión (clase proyección: ninguna API los separa en usage). (G.5)
    VERDICT_TOOL.figure_readings OPCIONAL — JUICIO ('model-judgment'); parse_figure_readings descarta y CUENTA ids no
    entregados y formas fuera de vocabulario; figure_readings_from_panel alimenta verify_output (content 'panel-judgment').
    (G.6) cada fila (también errored) gana `saw_figures` MEDIDO desde lo entregado al caller; `audit.vision` resume y
    apply_to_bundle lo copia. (H) WITT_FIGURES_COUNT_TOKENS=1 → saw_figures.tokens_measured = input_tokens medidos −
    count_tokens de la MISMA petición sin imágenes (medición derivada). Kill-switch WITT_FIGURES=0 (M.1): NINGUNA llave nueva
    se emite; member, system y cuerpos son los de 1.11 byte a byte. panel_signature no cambia con o sin figuras.
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
# ADR-0083 (G): la librería de figuras se importa EN DURO (bloques por transporte, env tolerante, vocabularios). Si falta,
# el módulo no importa y el smoke lo dice a gritos — mejor que un panel que "ve" a ciegas.
from lib import figures as _figures
try:                                    # ADR-0086 (F3): un árbol sin la biblioteca sigue corriendo y lo DECLARA
    from lib import attestations as _attested
except Exception:                       # pragma: no cover
    _attested = None

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

# ---------------------------------------------------------------------------------------------------------------
# ADR-0083 (G): panel con visión — DOS lentes ven las figuras (JUICIO etiquetado); el resto y el sintetizador jamás bytes
# ---------------------------------------------------------------------------------------------------------------
VISION_LENSES = ("evidence-grounding", "reproducibility")     # (G.1) default declarado (= figures._DEFAULT_LENSES, paridad medida)
VISION_LENSES_ENV = "WITT_FIGURES_VISION_LENSES"
# corrector (ADR-0083 G.1 / CLAUDE.md §7 «at most two panel lenses» / (N)(h)): la doctrina la HACE CUMPLIR el código — un CSV o
# un llamador con > 2 lentes cae al default DECLARADO (patrón M.8: fuera de rango → default con fuente), jamás se amplía en silencio.
VISION_LENSES_MAX = 2
VISION_LENSES_MAX_RULE = ("at most VISION_LENSES_MAX (2) panel lenses may receive images (CLAUDE.md §7, ADR-0083 N.h); a CSV or "
                          "caller list with more falls back to VISION_LENSES with lenses_source '... (>2 lenses)'")
# (G.6) `saw_figures.detail`, MEDIDO desde lo que se le entregó al caller — vocabulario CERRADO (viaja al gate de paridad)
SAW_FIGURES_DETAILS = ("sent", "lens-not-in-vision-lenses", "kill-switch WITT_FIGURES_VISION=0", "no-eligible-figures",
                       "model-vision-unknown", "api-form-not-verified")
VISION_STATES = ("sent", "kill-switch WITT_FIGURES_VISION=0", "no-eligible-figures")      # audit.vision.state (L)
# ADR-0086 (F3) · `saw_attested.detail`, MEDIDO desde lo que se le entregó al caller — vocabulario CERRADO (va al gate)
SAW_ATTESTED_DETAILS = ("sent", "lens-not-in-vision-lenses", "kill-switch WITT_ATTESTED_VISION=0",
                        "kill-switch WITT_ATTESTED_IMAGES=0", "no-eligible-attested", "model-vision-unknown",
                        "api-form-not-verified", "tool-unavailable (lib/attestations.py not importable)")
ATTESTED_VISION_STATES = ("sent", "kill-switch WITT_ATTESTED_VISION=0", "kill-switch WITT_ATTESTED_IMAGES=0",
                          "no-eligible-attested", "tool-unavailable (lib/attestations.py not importable)")
ATTESTED_READINGS_CLASS = "model-judgment"      # lo que una lente dice de una imagen APORTADA es juicio, jamás medición
API_FORM_VERIFIED = "verified by doc (2026-09-15)"      # Anthropic Messages y OpenAI Responses (ADR-0083 Context 8); chat: figures.OPENAI_CHAT_FORM_STATE
# (G.3) LA REGLA, literal: va al system de las lentes que reciben imágenes y congelada en frozen.figures.vision.rule (F4).
FIGURE_READING_RULE = ("You may be shown figure images from the cited papers. Use them ONLY to judge whether the claim "
                       "misrepresents what the figure shows. NEVER derive, read off or estimate numbers, counts, sizes or "
                       "statistics from an image — numbers must come from text. Never put figure-derived numbers or "
                       "observations in `caught`, `reasons` or `correction_applied`; report anything you conclude from an "
                       "image ONLY in `figure_readings` — it is model judgment, never a measurement. For `citation_support` "
                       "on a kind 'figure' citation judge the CAPTION text delivered in `evidence` only — the image never "
                       "decides support.")
FIGURE_READING_RULE_SHORT = "never derive numbers from the image"    # la forma corta de la doctrina §7 (D.5); vive en el tool
FIGURE_READINGS_CLASS = "model-judgment"
FIGURE_READING_MAX_CHARS = 400
# (H) estados de saw_figures.tokens_measured_state (exactos + prefijo 'error: <kind>')
TOKENS_MEASURED_STATES = ("measured (input_tokens - count_tokens text-only; last attempt)",
                          "not-requested (WITT_FIGURES_COUNT_TOKENS=0)",
                          "not-available (provider does not separate image tokens)", "no-images", "no-usage")
TOKENS_MEASURED_PREFIXES = ("error: ",)
_NUMERAL_RE = re.compile(r"\d")


def vision_lenses(env=None):
    """(lentes, fuente) — (G.1) WITT_FIGURES_VISION_LENSES (CSV) validado contra models.LENSES: vacía → VISION_LENSES con
    'default-unset:…'; algún token fuera del vocabulario, o CSV vacío/basura → VISION_LENSES con 'default-invalid-env:…'
    (declarado, jamás corregido en silencio); válida → los tokens DISTINTOS en su orden con 'env:…'."""
    cfg = _figures.env_config(env)
    toks = list(dict.fromkeys(str(t).strip() for t in cfg["vision_lenses"] if str(t).strip()))
    src = cfg["sources"]["vision_lenses"]
    if not toks or any(t not in models.LENSES for t in toks):
        return tuple(VISION_LENSES), f"default-invalid-env:{VISION_LENSES_ENV}"
    if len(toks) > VISION_LENSES_MAX:      # corrector: > 2 lentes con visión contradice §7 — default declarado, no se amplía
        return tuple(VISION_LENSES), f"default-invalid-env:{VISION_LENSES_ENV} (>{VISION_LENSES_MAX} lenses)"
    if src.startswith("default-"):
        return tuple(VISION_LENSES), src
    return tuple(toks), src

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


def _delivered_index(delivered):
    """{id compuesto → (id, fig_id, sha256)} y {fig_id pelón → …} (este último SÓLO cuando el fig_id es único entre lo
    entregado: dos papers con 'fig1' no se adivinan)."""
    by_id, by_fig, dup = {}, {}, set()
    for f in delivered or []:
        if not isinstance(f, dict) or not f.get("id"):
            continue
        rec = (f["id"], f.get("fig_id"), f.get("sha256"))
        by_id[f["id"]] = rec
        fid = f.get("fig_id")
        if fid:
            if fid in by_fig:
                dup.add(fid)
            by_fig[fid] = rec
    for fid in dup:
        by_fig.pop(fid, None)
    return by_id, by_fig


def parse_figure_readings(raw, delivered):
    """(válidas, n_dropped) — parseo DETERMINISTA de `figure_readings` tal como lo emitió el juez (ADR-0083 G.5).
    `delivered` = las figuras que ESA lente recibió (PANEL_FIGURE_KEYS: id, fig_id, sha256, …). Válida = dict cuyo fig_id
    resuelve a una figura ENTREGADA (por id compuesto '<PMCID>#<fig_id>', o por fig_id pelón cuando es único) con `reading`
    str no vacío; la primera lectura por figura gana. Se DESCARTAN y CUENTAN: ids no entregados, duplicados, formas fuera de
    vocabulario (consistent_with_caption ∉ {true, false, null}) e ítems que no son dict. `reading` se corta a 400 chars
    (reading_truncated declarado) y se MIDE `numerals_present` (hay un dígito: un juez que ignoró la regla queda VISIBLE, no
    corregido — jamás sube la escalera). raw que no es lista (el juez emitió un string) → ([], 1): emitió algo fuera de forma,
    que no es lo mismo que no emitir (el caller decide `emitted` por la presencia de la llave)."""
    if not isinstance(raw, list):
        return [], 1
    by_id, by_fig = _delivered_index(delivered)
    out, seen, dropped = [], set(), 0
    for item in raw:
        if not isinstance(item, dict):
            dropped += 1
            continue
        fid, reading, cwc = item.get("fig_id"), item.get("reading"), item.get("consistent_with_caption", None)
        rec = by_id.get(fid) if isinstance(fid, str) else None
        if rec is None and isinstance(fid, str):
            rec = by_fig.get(fid)
        if (rec is None or not isinstance(reading, str) or not reading.strip() or rec[0] in seen
                or not (cwc is None or isinstance(cwc, bool))):
            dropped += 1
            continue
        seen.add(rec[0])
        text = reading.strip()
        out.append({"fig_id": rec[1], "id": rec[0], "sha256": rec[2], "reading": text[:FIGURE_READING_MAX_CHARS],
                    "reading_truncated": len(text) > FIGURE_READING_MAX_CHARS, "consistent_with_caption": cwc,
                    "numerals_present": bool(_NUMERAL_RE.search(text))})
    return out, dropped


def figure_readings_from_panel(rows):
    """{'<PMCID>#<fig_id>': [{lens, reviewer, sha256, reading, consistent_with_caption, numerals_present}]} — las lecturas
    de imagen de TODAS las filas VÁLIDAS que las emitieron (ADR-0083 E: `figure_verification.content 'panel-judgment'` ⇔ el
    id está aquí; ausente → 'not-evaluated', declarado). Clase FIGURE_READINGS_CLASS: jamás entra a _panel_findings ni a la
    escalera de soporte (D.4)."""
    out = {}
    for r in (rows or []):
        if "verdict" not in r or not isinstance(r.get("figure_readings"), list):
            continue
        for fr in r["figure_readings"]:
            out.setdefault(fr["id"], []).append({"lens": r.get("lens"), "reviewer": r.get("reviewer"),
                                                 "sha256": fr.get("sha256"), "reading": fr.get("reading"),
                                                 "consistent_with_caption": fr.get("consistent_with_caption"),
                                                 "numerals_present": fr.get("numerals_present")})
    return out


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
            # ADR-0083 (G.5): lecturas de imagen — SÓLO las lentes con visión (las que recibieron bloques de imagen) lo
            # emiten; es JUICIO del modelo (figure_readings_class 'model-judgment'), jamás medición: nunca sube la escalera
            # de soporte ni entra a la revisión (D.4). parse_figure_readings descarta y CUENTA ids no entregados y formas
            # fuera de vocabulario; no emitir ≠ emitir []. OPCIONAL en `required`.
            "figure_readings": {
                "type": "array",
                "items": {"type": "object",
                          "properties": {"fig_id": {"type": "string"},
                                         "reading": {"type": "string", "maxLength": FIGURE_READING_MAX_CHARS},
                                         "consistent_with_caption": {"type": ["boolean", "null"]}},
                          "required": ["fig_id", "reading"]},
                "description": ("vision lenses ONLY (other lenses: omit) — and only when figure images were shown to you. "
                                "For EACH figure image you were shown, emit {fig_id (exactly as labelled: "
                                "'<PMCID>#<fig_id>'), reading (<= 400 chars: does the image support, contradict or not "
                                "bear on what the claim says about it?), consistent_with_caption (true | false | null = "
                                "cannot tell)}. This is your JUDGMENT, never a measurement: " + FIGURE_READING_RULE_SHORT +
                                " — never numbers read off the image, no counts, sizes or statistics; numbers must come "
                                "from text. Never repeat these readings in `caught`, `reasons` or `correction_applied`."),
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
                         effort=None, return_meta=False, tools=None, user_content=None):
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
    Fallos → CallerError con kind (C.2) y los MISMOS mensajes de f57a3d3; refusal y http-4xx no se reintentan.
    ADR-0083 (G.3), aditivo: `user_content=` None → "content": user_text BYTE A BYTE (el cuerpo de 1.11); lista de bloques →
    "content": user_content tal cual (figures.anthropic_blocks: rótulo + imagen base64 × N + texto; imágenes ANTES del texto).
    SOLO _default_caller la pasa, y sólo a una lente con visión con figuras entregadas."""
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
            "messages": [{"role": "user", "content": user_text if user_content is None else user_content}],
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


ANTHROPIC_COUNT_TOKENS_URL = "https://api.anthropic.com/v1/messages/count_tokens"


def _anthropic_count_tokens(model, system, user_text, tool=None, tools=None, timeout=60, user_content=None):
    """ADR-0083 (H): los `input_tokens` que la API CUENTA para la MISMA petición del juez SIN imágenes (system, texto, tools,
    tool_choice). Una llamada gratuita por lente, sólo con WITT_FIGURES_COUNT_TOKENS=1; audit() deriva
    `saw_figures.tokens_measured = input_tokens medidos del intento − este conteo` (clase medición DERIVADA). Sin reintentos;
    fallos → CallerError con kind (C.2) que el llamador DECLARA en tokens_measured_state, jamás inventa. Cero llamadas sin
    llave. Costura de red: urllib.request.urlopen (los smokes la bloquean y falsean esta función).
    corrector: `user_content` (lista de bloques) = la MISMA petición del juez MENOS los bloques `image` — los rótulos de texto
    'Figure k — …: <caption>' que viajan junto a cada imagen SÍ se cuentan (antes se atribuían a visión: sesgo al alza por
    construcción); None → sólo `user_text` (llamador de 1.11)."""
    tool = tool or VERDICT_TOOL
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise CallerError("no-api-key", "ANTHROPIC_API_KEY not set — count_tokens skipped (never git).")
    content = user_content if isinstance(user_content, list) else user_text
    body = {"model": model, "system": system, "messages": [{"role": "user", "content": content}],
            "tools": list(tools) if tools is not None else [tool], "tool_choice": {"type": "tool", "name": tool["name"]}}
    headers = {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}
    req = urllib.request.Request(ANTHROPIC_COUNT_TOKENS_URL, data=json.dumps(body).encode("utf-8"), headers=headers,
                                 method="POST")
    try:
        with _INFLIGHT:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise CallerError(f"http-{e.code}", f"count_tokens HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise CallerError("network", f"count_tokens network error: {e}") from e
    n = payload.get("input_tokens") if isinstance(payload, dict) else None
    if not isinstance(n, int) or isinstance(n, bool):
        raise CallerError("unclassified", f"count_tokens: payload without integer input_tokens ({str(payload)[:120]})")
    return n


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


def _responses_kwargs(model, system, user_text, tool, max_output_tokens, store, reasoning_effort=None, user_content=None):
    """UNA función PURA que arma los kwargs de `client.responses.create` — la comparten el caller y
    analysis/scripts/smoke_live_models.py (S6), así no divergen. `strict: False` FIJO: `strict: true` exige todas
    las propiedades en `required` y rompería el tres-estados de `domain_niches`/`citation_support` (WITT_OPENAI_STRICT
    NO existe: una env que se sabe rompe el schema no se declara). `parallel_tool_calls: False` (un solo function_call).
    `store` (WITT_OPENAI_STORE, default 0: el default de la API es retención 30 días del lado OpenAI — se apaga y se
    declara, sin afirmar ZDR). `reasoning` sólo cuando `reasoning_effort` viene (ver _reasoning_effort_for).
    ADR-0083 (G.3), aditivo: `user_content` None → "input": user_text (byte a byte); lista de partes → "input": [{role user,
    content: partes}] (figures.openai_responses_parts: input_text + input_image data URL × N + input_text)."""
    kwargs = {
        "model": model,
        "instructions": system,
        "input": user_text if user_content is None else [{"role": "user", "content": user_content}],
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
                           client=None, store=None, reasoning_effort=None, user_content=None):
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
    kwargs = _responses_kwargs(model, system, user_text, tool, max_output_tokens, store, reasoning_effort,
                               user_content=user_content)    # ADR-0083 (G.3): None → byte a byte
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


def _openai_chat_call(model, system, user_text, timeout=None, tool=None, client=None, user_content=None):
    """Cross-provider judge por chat.completions = el `_openai_tool_call` de f57a3d3 BYTE A BYTE en la petición
    (`max_tokens 1200`, tools/tool_choice function, messages system+user) + `max_retries=0` (vía _openai_client) +
    meta. Kill-switch declarado: WITT_OPENAI_API=chat-completions. Devuelve (verdict, usage, meta) con usage =
    `resp.usage.model_dump()` (como hoy) y meta = {model_reported: resp.model, api: 'openai-chat-completions',
    response_id, finish_reason, max_tokens (OPENAI_CHAT_MAX_TOKENS: el tope EFECTIVO — corrector)}. `tool` (ADR-0081 L.n: run_held_out delega aquí con SU tool) — la validación de
    `verdict` sólo aplica a VERDICT_TOOL. Sin reintentos propios (como hoy): audit() reintenta por WITT_JUDGE_RETRIES.
    ADR-0083 (G.3), aditivo — OBLIGATORIO por los dos jueces del ADR: el puente chat.completions ES la lente reproducibility de
    hoy; `user_content` None → content: user_text (byte a byte); lista → messages[1].content = partes
    (figures.openai_chat_parts: text + image_url {url data:…, detail} × N + text). Forma declarada
    figures.OPENAI_CHAT_FORM_STATE ('public form; not re-verified by doc in this work'); LG4 la mide; un http-400 cae en el
    vocabulario de fallos (C.2) y la corrida sigue."""
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
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user_text if user_content is None else user_content}],
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
    `tool` (ADR-0081 L.n): run_held_out.openai_verdict delega aquí con su propio tool.
    ADR-0083 (G.3): si el member trae `figures` (lista PANEL_FIGURE_KEYS con b64 — SOLO audit() la pone, y sólo a una lente
    con visión), el contenido de usuario se arma POR TRANSPORTE con figures.anthropic_blocks / openai_responses_parts /
    openai_chat_parts (imágenes ANTES del texto, cada una rotulada; `detail` de WITT_FIGURES_OPENAI_DETAIL) y viaja como
    `user_content=`; sin `figures` el kwarg NO se pasa → fakes de 3 argumentos y cuerpos de 1.11 quedan byte a byte."""
    api, _api_source = _member_api(member)
    reviewer = member.get("reviewer")
    figs = member.get("figures")
    figs = list(figs) if isinstance(figs, list) and figs else None
    # ADR-0086 (F3): las imágenes ATESTIGUADAS viajan en el MISMO contenido, detrás de su separador y después de las
    # figuras — nunca mezcladas con ellas. Sólo audit() las pone en el member, y sólo a una lente con visión.
    att = member.get("attested")
    att = list(att) if isinstance(att, list) and att else None
    detail = _figures.env_config()["openai_detail"] if (figs or att) else None
    if api == "openai-responses":
        ab = _attested.openai_responses_attested_parts(att, detail) if (att and _attested is not None) else None
        kw = ({"user_content": _figures.openai_responses_parts(figs, user_text, detail, attested_parts=ab)}
              if (figs or ab) else {})
        return _openai_responses_call(reviewer, system, user_text, tool=tool, **kw)
    if api == "openai-chat-completions":
        ab = _attested.openai_chat_attested_parts(att, detail) if (att and _attested is not None) else None
        kw = ({"user_content": _figures.openai_chat_parts(figs, user_text, detail, attested_parts=ab)}
              if (figs or ab) else {})
        return _openai_chat_call(reviewer, system, user_text, tool=tool, **kw)
    if api == "anthropic-messages":
        mt = member.get("max_tokens")
        max_tokens = mt if isinstance(mt, int) and not isinstance(mt, bool) and mt > 0 else ANTHROPIC_JUDGE_MAX_TOKENS_LEGACY
        ab = _attested.anthropic_attested_blocks(att) if (att and _attested is not None) else None
        kw = ({"user_content": _figures.anthropic_blocks(figs, user_text, attested_blocks=ab)} if (figs or ab) else {})
        return _anthropic_tool_call(reviewer, system, user_text, tool=tool, max_tokens=max_tokens,
                                    effort=_anthropic_effort_for(reviewer), return_meta=True, **kw)
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


# ---------------------------------------------------------------------------------------------------------------
# ADR-0083 (G.2 / G.6 / H): el plan de visión de UNA llamada a audit(), lo que ve CADA asiento y el resumen audit.vision
# ---------------------------------------------------------------------------------------------------------------
def _vision_plan(fcfg, figures, lenses_arg):
    """{figures_on, vision_on, lenses, lenses_source, openai_detail, count_tokens, count_tokens_source, max_per_lens,
    candidates}. `lenses_arg` del llamador (validado contra models.LENSES; inválido → default con 'default-invalid-caller')
    o vision_lenses(env). Con WITT_FIGURES=0 → figures_on False: audit() no emite ninguna llave nueva (M.1)."""
    plan = {"figures_on": bool(fcfg["figures"]), "vision_on": bool(fcfg["vision"]), "openai_detail": fcfg["openai_detail"],
            "count_tokens": bool(fcfg["count_tokens"]), "count_tokens_source": fcfg["sources"]["count_tokens"],
            "max_per_lens": int(fcfg["max_per_lens"]),
            "candidates": [f for f in (figures or []) if isinstance(f, dict)]}
    if lenses_arg is not None:
        toks = tuple(dict.fromkeys(str(t) for t in lenses_arg))
        if toks and all(t in models.LENSES for t in toks) and len(toks) <= VISION_LENSES_MAX:
            plan["lenses"], plan["lenses_source"] = toks, "caller"
        elif toks and all(t in models.LENSES for t in toks):     # corrector: el llamador tampoco puede pasar de 2 (§7)
            plan["lenses"], plan["lenses_source"] = tuple(VISION_LENSES), f"default-invalid-caller (>{VISION_LENSES_MAX} lenses)"
        else:
            plan["lenses"], plan["lenses_source"] = tuple(VISION_LENSES), "default-invalid-caller"
    else:
        plan["lenses"], plan["lenses_source"] = vision_lenses()
    return plan


def _attested_plan(attested, vis):
    """{on, vision_on, lenses, max_per_lens, candidates, state_reason} — ADR-0086 (F3). Las lentes son las MISMAS que ven
    figuras (VISION_LENSES: a lo sumo dos, §7); los topes salen de attestations.env_config() EN LA LLAMADA. Con
    WITT_ATTESTED_IMAGES=0 o WITT_ATTESTED_VISION=0 no viaja ni un byte y el estado lo dice."""
    if _attested is None:
        return {"on": False, "vision_on": False, "lenses": tuple(vis["lenses"]), "max_per_lens": 0, "candidates": [],
                "state_reason": "tool-unavailable (lib/attestations.py not importable)"}
    try:
        cfg = _attested.env_config()
    except Exception as e:                                  # el lector es tolerante; un árbol roto se declara
        return {"on": False, "vision_on": False, "lenses": tuple(vis["lenses"]), "max_per_lens": 0, "candidates": [],
                "state_reason": f"error: {type(e).__name__}"}
    enabled, vision = bool(cfg.get("enabled", True)), bool(cfg.get("vision", True))
    return {"on": enabled, "vision_on": vision, "lenses": tuple(vis["lenses"]),
            "max_per_lens": int(cfg.get("max_per_lens") or 0),
            "candidates": [a for a in (attested or []) if isinstance(a, dict)],
            "state_reason": None if (enabled and vision) else (
                "kill-switch WITT_ATTESTED_IMAGES=0" if not enabled else "kill-switch WITT_ATTESTED_VISION=0")}


def _attested_for_member(member, api, ap, figs_bytes=0):
    """(saw_attested, imágenes a entregar | None) para UN asiento — MEDIDO desde lo que se le entrega al caller.
    Mismo orden de decisión que las figuras y una regla más: el presupuesto b64 de la petición es COMPARTIDO y las
    figuras van primero (`figs_bytes` ya consumido). Bajo el kill-switch maestro devuelve (None, None): nada se emite."""
    # Sin imágenes aportadas (o con el kill-switch maestro) NO nace ninguna llave: una corrida sin ellas es byte a byte
    # la de 1.13 (M.1 de la casa). Que no haya ninguna lo DECLARA el registro (frozen.attested_images.state), no el panel.
    if not ap["candidates"] or (not ap["on"] and ap["state_reason"] in (None, "kill-switch WITT_ATTESTED_IMAGES=0")):
        return None, None
    lens = member.get("lens")
    tier, _m, _v, _s = models.vision_tier_of(member.get("reviewer"))
    saw = {"n": 0, "sha256s": [], "bytes_b64_total": 0, "detail": None, "attempts_with_images": 0,
           "n_dropped": {"lens_cap": 0, "request_cap": 0, "invalid": 0}, "tier": tier,
           "class": ATTESTED_READINGS_CLASS}
    if ap["state_reason"]:
        saw["detail"] = ap["state_reason"]
        return saw, None
    if lens not in ap["lenses"]:
        saw["detail"] = "lens-not-in-vision-lenses"
        return saw, None
    if not ap["candidates"]:
        saw["detail"] = "no-eligible-attested"
        return saw, None
    if tier in ("none", "unknown"):
        saw["detail"] = "model-vision-unknown"
        return saw, None
    if api not in models.TOOL_CALL_APIS:
        saw["detail"] = "api-form-not-verified"
        return saw, None
    cap = int(ap["max_per_lens"])
    req_cap = int(float(_figures.REQUEST_B64_MB) * 1024 * 1024)
    sel, total = [], int(figs_bytes or 0)
    for a in ap["candidates"]:
        b64 = a.get("b64")
        if not (isinstance(b64, str) and b64 and a.get("sha256") and a.get("id")
                and a.get("media_type") in _figures.MEDIA_TYPES):
            saw["n_dropped"]["invalid"] += 1
            continue
        if len(sel) >= cap:
            saw["n_dropped"]["lens_cap"] += 1
            continue
        if total + len(b64) > req_cap:
            saw["n_dropped"]["request_cap"] += 1
            continue
        sel.append(a)
        total += len(b64)
    if not sel:
        saw["detail"] = "no-eligible-attested"
        return saw, None
    saw.update({"n": len(sel), "sha256s": [a["sha256"] for a in sel],
                "bytes_b64_total": total - int(figs_bytes or 0), "detail": "sent"})
    return saw, sel


def _attested_summary(rows, ap):
    """{state, enabled, lenses, rule, n_candidates, n_images_by_lens, n_attempts_with_images, bytes_b64_sent_total,
    readings {n_rows, n_readings, class}, saw_attested_details} — el resumen de QUIÉN vio bytes aportados por una persona.
    Ningún caption ni byte viaja aquí: shas y conteos."""
    n_by, n_att, b64 = {}, 0, 0
    n_rows_r, n_read = 0, 0
    for r in rows:
        s = r.get("saw_attested")
        if not isinstance(s, dict):
            continue
        n = int(s.get("n") or 0)
        n_by[r.get("lens")] = n_by.get(r.get("lens"), 0) + n
        att = int(s.get("attempts_with_images") or 0)
        n_att += att
        b64 += int(s.get("bytes_b64_total") or 0) * att
        if isinstance(r.get("attested_readings"), list):
            n_rows_r += 1
            n_read += len(r["attested_readings"])
    any_sent = any(n > 0 for n in n_by.values())
    state = "sent" if any_sent else (ap["state_reason"] or "no-eligible-attested")
    return {"state": state, "enabled": bool(ap["on"] and ap["vision_on"]), "lenses": list(ap["lenses"]),
            "rule": (_attested.ATTESTED_READING_RULE if _attested is not None else None),
            "n_candidates": len(ap["candidates"]), "n_images_by_lens": n_by, "n_attempts_with_images": n_att,
            "bytes_b64_sent_total": b64,
            "readings": {"n_rows": n_rows_r, "n_readings": n_read, "class": ATTESTED_READINGS_CLASS},
            "saw_attested_details": list(SAW_ATTESTED_DETAILS)}


def _figures_for_member(member, api, vis):
    """(saw_figures, figuras a entregar | None) para UN asiento — MEDIDO desde lo que se le entrega al caller (G.6).
    Orden de decisión del `detail`: kill-switch WITT_FIGURES_VISION=0 · lente ∉ vision_lenses · sin candidatas
    ('no-eligible-figures') · vision_tier none|unknown por tabla ('model-vision-unknown', G.4: un id fuera de tabla o la fila embed
    no reciben imágenes) · api sin forma de bloques conocida ('api-form-not-verified': un member con `api` explícita fuera de
    models.TOOL_CALL_APIS) · selección con topes (max_per_lens; b64 acumulada ≤ figures.REQUEST_B64_MB por petición; forma
    válida: b64 str, sha256, id, media_type ∈ MEDIA_TYPES) → 'sent' si quedó ≥ 1, si no 'no-eligible-figures' con n_dropped
    declarado. Bajo WITT_FIGURES=0 → (None, None): nada se emite. La proyección de tokens es models.vision_tokens (clase
    proyección; ausente = None cuando una imagen no trae dims)."""
    if not vis["figures_on"]:
        return None, None
    reviewer, lens = member.get("reviewer"), member.get("lens")
    tier, _mult, _ver, _src = models.vision_tier_of(reviewer)
    saw = {"n": 0, "sha256s": [], "bytes_b64_total": 0, "detail": None, "attempts_with_images": 0,
           "n_dropped": {"lens_cap": 0, "request_cap": 0, "invalid": 0}, "tier": tier, "api_form_state": None,
           "openai_detail": None, "visual_tokens_projected": None, "n_images_unprojected": 0, "formula": None,
           "projection_class": models.VISION_CLASS, "tokens_measured": None, "tokens_measured_state": "no-images"}
    if not vis["vision_on"]:
        saw["detail"] = "kill-switch WITT_FIGURES_VISION=0"
        return saw, None
    if lens not in vis["lenses"]:
        saw["detail"] = "lens-not-in-vision-lenses"
        return saw, None
    if not vis["candidates"]:
        saw["detail"] = "no-eligible-figures"
        return saw, None
    if tier in ("none", "unknown"):
        saw["detail"] = "model-vision-unknown"
        return saw, None
    if api not in models.TOOL_CALL_APIS:
        saw["detail"] = "api-form-not-verified"
        return saw, None
    cap = int(vis["max_per_lens"])
    req_cap = int(float(_figures.REQUEST_B64_MB) * 1024 * 1024)    # leído EN LA LLAMADA (los smokes lo parchean)
    sel, total = [], 0
    for f in vis["candidates"]:
        b64 = f.get("b64")
        if not (isinstance(b64, str) and b64 and f.get("sha256") and f.get("id")
                and f.get("media_type") in _figures.MEDIA_TYPES):
            saw["n_dropped"]["invalid"] += 1
            continue
        if len(sel) >= cap:
            saw["n_dropped"]["lens_cap"] += 1
            continue
        if total + len(b64) > req_cap:
            saw["n_dropped"]["request_cap"] += 1
            continue
        sel.append(f)
        total += len(b64)
    if not sel:
        saw["detail"] = "no-eligible-figures"
        return saw, None
    detail = vis["openai_detail"] if api != "anthropic-messages" else None
    proj, unproj, formula = 0, 0, None
    for f in sel:
        dm = f.get("dims_measured") or {}
        vt = models.vision_tokens(reviewer, dm.get("w"), dm.get("h"), detail)
        if vt is None:
            unproj += 1
        else:
            proj += vt["tokens"]
            formula = vt["formula"]
    if not vis["count_tokens"]:
        tm_state = "not-requested (WITT_FIGURES_COUNT_TOKENS=0)"
    elif api != "anthropic-messages":
        tm_state = "not-available (provider does not separate image tokens)"
    else:
        tm_state = "pending"      # _tokens_measured_into lo resuelve tras los intentos
    saw.update({"n": len(sel), "sha256s": [f["sha256"] for f in sel], "bytes_b64_total": total, "detail": "sent",
                "api_form_state": _figures.OPENAI_CHAT_FORM_STATE if api == "openai-chat-completions" else API_FORM_VERIFIED,
                "openai_detail": detail, "visual_tokens_projected": proj if unproj < len(sel) else None,
                "n_images_unprojected": unproj, "formula": formula, "tokens_measured_state": tm_state})
    return saw, sel


def _tokens_measured_into(saw, attempts, reviewer, system, user_text, figs=None):
    """(H) saw_figures.tokens_measured — SÓLO con WITT_FIGURES_COUNT_TOKENS=1, lente Anthropic e imágenes enviadas (estado
    'pending'): input_tokens MEDIDOS del ÚLTIMO intento con usage − count_tokens de la MISMA petición SIN imágenes (clase
    medición derivada). Sin usage → 'no-usage'; fallo del conteo → None + 'error: <kind>' (declarado, jamás relanza).
    corrector: la petición contada = figures.anthropic_blocks(figs, user_text) MENOS los bloques `image` (los rótulos de
    texto por figura se cuentan como texto, no como visión); `tokens_measured_counted_blocks` declara cuántos bloques de
    texto entraron al conteo."""
    if saw.get("tokens_measured_state") != "pending":
        return
    last_in = None
    for a in reversed(attempts):
        u = a.get("usage") if isinstance(a, dict) else None
        v = u.get("input_tokens") if isinstance(u, dict) else None
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            last_in = v
            break
    if last_in is None:
        saw["tokens_measured_state"] = "no-usage"
        return
    blocks = [b for b in _figures.anthropic_blocks(figs, user_text) if b.get("type") != "image"] if figs else None
    try:
        text_only = _anthropic_count_tokens(reviewer, system, user_text, user_content=blocks)
    except Exception as e:  # noqa: BLE001 — el conteo es opcional y gratuito: se declara, nunca tumba el panel
        saw["tokens_measured_state"] = f"error: {failure_kind_of(e)}"
        return
    saw["tokens_measured"] = int(last_in) - int(text_only)
    saw["tokens_measured_text_only"] = int(text_only)
    saw["tokens_measured_counted_blocks"] = len(blocks) if blocks is not None else 1
    saw["tokens_measured_state"] = TOKENS_MEASURED_STATES[0]


def _vision_summary(vis, rows):
    """audit.vision (G.6 / L): {state ∈ VISION_STATES, enabled, lenses, lenses_source, rule, openai_detail, n_candidates,
    n_images_by_lens {lens: n}, n_attempts_with_images, bytes_b64_sent_total (reenvío MEDIDO: bytes × intentos con imágenes),
    visual_tokens_projected_by_lens {lens: int|None} (sólo lentes que vieron), visual_tokens_projected_total (una petición),
    visual_tokens_projected_sent_total (× intentos), projection_class, formula_source, count_tokens {requested, source},
    readings {n_rows, n_readings, n_dropped, class}, saw_figures_details (vocabulario)}. Clase: conteos y bytes MEDIDOS;
    tokens PROYECTADOS (los input_tokens medidos del juez ya los incluyen — nada se suma dos veces, ADR-0083 H)."""
    n_by, tok_by = {}, {}
    n_att, b64_sent, tok_req, tok_sent = 0, 0, 0, 0
    n_rows_r, n_read, n_drop = 0, 0, 0
    for r in rows:
        s = r.get("saw_figures")
        if not isinstance(s, dict):
            continue
        lens, n = r.get("lens"), int(s.get("n") or 0)
        n_by[lens] = n_by.get(lens, 0) + n
        att = int(s.get("attempts_with_images") or 0)
        n_att += att
        b64_sent += int(s.get("bytes_b64_total") or 0) * att
        if n > 0:
            vt = s.get("visual_tokens_projected")
            if isinstance(vt, int):
                tok_by[lens] = (tok_by.get(lens) or 0) + vt
                tok_req += vt
                tok_sent += vt * att
            else:
                tok_by.setdefault(lens, None)
        if isinstance(r.get("figure_readings"), list):
            n_rows_r += 1
            n_read += len(r["figure_readings"])
            n_drop += int(r.get("figure_readings_dropped") or 0)
    any_sent = any(n > 0 for n in n_by.values())
    state = "sent" if any_sent else ("kill-switch WITT_FIGURES_VISION=0" if not vis["vision_on"] else "no-eligible-figures")
    return {"state": state, "enabled": bool(vis["vision_on"]), "lenses": list(vis["lenses"]),
            "lenses_source": vis["lenses_source"], "rule": FIGURE_READING_RULE, "openai_detail": vis["openai_detail"],
            "n_candidates": len(vis["candidates"]), "n_images_by_lens": n_by, "n_attempts_with_images": n_att,
            "bytes_b64_sent_total": b64_sent, "visual_tokens_projected_by_lens": tok_by,
            "visual_tokens_projected_total": tok_req, "visual_tokens_projected_sent_total": tok_sent,
            "projection_class": models.VISION_CLASS, "formula_source": dict(models.VISION_FORMULA_SOURCE),
            "count_tokens": {"requested": bool(vis["count_tokens"]), "source": vis["count_tokens_source"]},
            "readings": {"n_rows": n_rows_r, "n_readings": n_read, "n_dropped": n_drop, "class": FIGURE_READINGS_CLASS},
            "saw_figures_details": list(SAW_FIGURES_DETAILS)}


def audit(claim, evidence, deterministic_checks=None, required_because="", panel=None,
          caller=None, min_valid=3, judge_retries=None, min_families=None, min_lenses=None, directives=None,
          figures=None, vision_lenses=None, attested=None):
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

    ADR-0083 (G): `figures` = la lista que runs arma con figures.select_for_panel (PANEL_FIGURE_KEYS: id, fig_id, label,
    caption, license {id}, sha256, media_type, b64, dims_measured — panel_view ∧ verified ∧ caption present, ya ordenada:
    citadas primero, luego rank, luego documento); `vision_lenses` = las lentes que las VEN (None → vision_lenses(env):
    WITT_FIGURES_VISION_LENSES validada contra models.LENSES, default evidence-grounding + reproducibility). Para un member
    cuya lente ∈ vision_lenses — con WITT_FIGURES_VISION=1, api con forma de bloques conocida y vision_tier ≠ none|unknown en
    la tabla — el caller recibe `dict(member, attempt=k, figures=[…])` (topes: max_per_lens y b64 ≤ REQUEST_B64_MB por
    petición, n_dropped declarado): la firma caller(member, system, user_text) NO cambia y la fila copia sólo
    reviewer/family/lens/seat, así la b64 jamás fuga al frozen; su system gana FIGURE_READING_RULE. Cada fila (también
    errored) gana `saw_figures` {n, sha256s, bytes_b64_total, detail ∈ SAW_FIGURES_DETAILS, attempts_with_images, n_dropped,
    tier, api_form_state, openai_detail, visual_tokens_projected, n_images_unprojected, formula, projection_class,
    tokens_measured, tokens_measured_state} MEDIDO desde lo entregado al caller; una fila válida que emitió `figure_readings`
    gana figure_readings (parseadas contra lo entregado) + figure_readings_class 'model-judgment' + figure_readings_dropped.
    `out['vision']` = el resumen (_vision_summary). Kill-switch WITT_FIGURES=0 (M.1): NINGUNA de estas llaves se emite y
    member, system y cuerpos son los de 1.11 byte a byte (aunque el llamador pase `figures`).
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
    # ADR-0083 (G): configuración de figuras EN LA LLAMADA (figures.env_config tolerante) y plan de visión de este panel
    fcfg = _figures.env_config()
    vis = _vision_plan(fcfg, figures, vision_lenses)
    # ADR-0086 (F3): plan de las imágenes ATESTIGUADAS — mismas lentes (a lo sumo dos), tope propio, presupuesto b64
    # compartido con las figuras (las figuras van primero). Con el kill-switch maestro no se emite ninguna llave nueva.
    ap = _attested_plan(attested, vis)
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
        # ADR-0083 (G.2/G.6): qué figuras ve ESTE asiento — (None, None) bajo WITT_FIGURES=0: nada cambia (M.1)
        saw, figs_for_member = _figures_for_member(member, api, vis)
        if figs_for_member:
            system = system + "\n\n" + FIGURE_READING_RULE      # (G.3) la regla viaja SOLO cuando de veras viajan imágenes
        saw_att, att_for_member = _attested_for_member(member, api, ap, int((saw or {}).get("bytes_b64_total") or 0))
        if att_for_member and _attested is not None:
            # la regla de lo ATESTIGUADO viaja SÓLO cuando de veras viajan imágenes aportadas por una persona
            system = system + "\n\n" + _attested.ATTESTED_READING_RULE
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
                m_call = dict(member, attempt=attempt)
                if figs_for_member:
                    m_call["figures"] = figs_for_member     # (G.2) DENTRO del member; la fila no lo copia (b64 no fuga)
                if att_for_member:
                    m_call["attested"] = att_for_member     # idem: los bytes aportados no tocan la fila ni el registro
                out_v, usage, meta = _unpack_caller_result(caller(m_call, system, user_text))
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
        if saw is not None:
            # (H) reenvío MEDIDO: cada intento que llevó imágenes las reenvió y la API las facturó
            saw["attempts_with_images"] = len(attempts) if saw["n"] > 0 else 0
            _tokens_measured_into(saw, attempts, member.get("reviewer"), system, user_text, figs=figs_for_member)
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
                # corrector (ADR-0083 E/G, límite declarado): la lente evidence-grounding es a la vez lente con VISIÓN y la
                # única que emite citation_support — se DECLARA si el veredicto de soporte pudo estar informado por píxeles
                # (la fila vio imágenes); el registro no puede distinguir un 'supported' de caption de uno de imagen. La
                # instrucción «judge the CAPTION only» vive en FIGURE_READING_RULE (system, sólo cuando viajan imágenes): la
                # description de `citation_support` NO cambia — VERDICT_TOOL sin figure_readings sigue byte a byte el de 1.11.
                if saw is not None:
                    row["citation_support_vision_informed"] = bool(saw.get("n"))
            # ADR-0083 (G.6): lo que el juez VIO (medido) y lo que LEYÓ en las imágenes (juicio etiquetado; sólo si emitió)
            if saw is not None:
                row["saw_figures"] = saw
                if verdict.get("figure_readings") is not None:
                    fr, fr_dropped = parse_figure_readings(verdict["figure_readings"], figs_for_member or [])
                    row["figure_readings"] = fr
                    row["figure_readings_class"] = FIGURE_READINGS_CLASS
                    row["figure_readings_dropped"] = fr_dropped
            if saw_att is not None:                      # ADR-0086 (F3): qué imágenes APORTADAS vio este asiento
                row["saw_attested"] = saw_att
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
            if saw is not None:   # ADR-0083 (G.6): también la fila errored declara lo que se le entregó (y reenvió)
                row["saw_figures"] = saw
            if saw_att is not None:                      # ADR-0086 (F3): qué imágenes APORTADAS vio este asiento
                row["saw_attested"] = saw_att
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
    if vis["figures_on"]:
        # ADR-0083 (G.6): el resumen de visión del panel (ausente bajo WITT_FIGURES=0: tres estados, M.1)
        out["vision"] = _vision_summary(vis, rows)
    # ADR-0086 (F3): el resumen de lo ATESTIGUADO — quién vio bytes aportados por una persona y qué dijo de ellos.
    # Vive junto al de visión cuando las figuras están encendidas, y solo cuando no (el kill-switch de figuras no debe
    # esconder que alguien aportó imágenes). Ausente bajo WITT_ATTESTED_IMAGES=0: ninguna llave nueva (M.1).
    if ap["candidates"] and (ap["on"] or ap["state_reason"] not in (None, "kill-switch WITT_ATTESTED_IMAGES=0")):
        resumen_att = _attested_summary(rows, ap)
        if isinstance(out.get("vision"), dict):
            out["vision"]["attested"] = resumen_att
        else:
            out["attested_vision"] = resumen_att
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
# ADR-0083 (G.6): audit.vision viaja al bundle cuando el audit_result lo trae (ausente bajo WITT_FIGURES=0 — tres estados).
_BUNDLE_AUDIT_KEYS_1_12 = ("vision",)


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
    for k in _BUNDLE_AUDIT_KEYS_1_10 + _BUNDLE_AUDIT_KEYS_1_12:
        if k in audit_result:
            bundle["audit"][k] = audit_result[k]
    bundle["bundle_identity"] = answer_pipeline_module._identity(bundle)
    return bundle

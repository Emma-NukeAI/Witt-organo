"""smoke_openai_responses.py — gate determinista de la rebanada S2 de ADR-0081 (C.1–C.3): el juez OpenAI por la
Responses API con cliente FAKE inyectado, el vocabulario CERRADO de fallos (CallerError.kind → attempts[].error_kind),
el despacho por transporte (_default_caller por member['api']; WITT_OPENAI_API fuerza) y el caller Anthropic con
return_meta (B) / output_config.effort (C.4).

Qué MIDE (todo offline; el SDK openai se importa UNA vez para comparar firmas y se purga de sys.modules):
  - _responses_kwargs EXACTOS: strict False · store por WITT_OPENAI_STORE (default 0) · parallel_tool_calls False ·
    tool_choice function · max_output_tokens por WITT_OPENAI_MAX_OUTPUT_TOKENS (default 4000) · reasoning.effort SÓLO
    con env + tabla `reasoning True`; kwargs ⊆ la firma REAL de openai.resources.responses.Responses.create.
  - _openai_client: OpenAI(timeout=WITT_OPENAI_TIMEOUT_S, max_retries=0); 'no-api-key' ANTES de importar el SDK;
    'sdk-unavailable' con el SDK bloqueado o sin client.responses — cero llamadas.
  - _openai_responses_call: éxito → 3-tupla (out, usage NUMÉRICO con reasoning/cached, meta); recover_trapped_params;
    429/network → UN reintento; 400/401/404 SIN reintento; incomplete:* / no-function-call / arguments-unparseable /
    verdict-off-vocabulary → UN reintento de contenido; required-missing → reintento y devolver lo recibido;
    response-failed sin reintento; el intento que erró CONSERVA usage/meta medidos (la API cobró).
    Corrector: refusal (ítem message con content[].type 'refusal') SIN reintento; truncación decidida por status ANTES
    de parsear (function_call PARCIAL → incomplete:*, no arguments-unparseable); meta lleva el tope EFECTIVO
    (max_output_tokens en Responses / max_tokens 1200 en chat) y attempts[] lo copia.
  - _openai_chat_call = la petición de f57a3d3 byte a byte (max_tokens 1200) + meta + kinds; sin reintento propio.
  - _default_caller: despacho por api (tabla, env, panel legado inferido de la familia), max_tokens/effort al caller
    Anthropic, 'unknown-family' sin llamar a nada; alias _openai_tool_call por tabla; `tool=` pasa entero.
  - audit() con fake: filas con family_source/api/api_source/reviewer_source/max_tokens; attempts[].error byte-igual a
    hoy + error_kind + model_reported/api; failure_kinds_vocabulary congelado; juez OpenAI caído → REVISE ['families'].
  - _anthropic_tool_call con urlopen FAKE (transporte simulado, no red): 2-tupla INTACTA con usage crudo;
    return_meta=True → meta + thinking_tokens aplanado; output_config sólo con effort; refusal SIN reintento;
    stop_reason max_tokens → incomplete:max_output_tokens; HTTP 4xx sin reintento; 529/URLError con reintento.
  - urllib.request.urlopen REAL bloqueado y contado = 0; sys.modules sin 'openai' al terminar.

100% offline: cero red, cero gasto de modelo, cero BD, cero mutación de la DATA INAMOVIBLE. Exit 0 = todo PASS.
Ningún id de modelo se escribe aquí como literal: todos salen de models.py (gate estático M.4).

Corre (máscara offline):
  WITT_BACKEND_DB_URL="sqlite:///C:/Users/Emmanuel/AppData/Local/Temp/claude/witt-smokes/adr81-openai-responses.db"
  NEO4J_URI="" RAG_BACKEND=sparse OPENAI_API_KEY="" ANTHROPIC_API_KEY="" WITT_RUN_ORIGIN=smoke
  python rag_index/query_service/smoke_openai_responses.py
"""
import inspect
import io
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
_ADR81_ENVS = ("WITT_MODEL_GENERATION", "WITT_MODEL_SYNTH", "WITT_MODEL_PLANNER", "WITT_MODEL_ELICIT",
               "WITT_MODEL_QUESTION", "WITT_JUDGE_CORRECTNESS", "WITT_JUDGE_OVERCLAIM", "WITT_JUDGE_GROUNDING",
               "OPENAI_JUDGE_MODEL", "WITT_PANEL_AUTO_RETIRE", "WITT_PANEL_MIN_FAMILIES", "WITT_PANEL_MIN_LENSES",
               "WITT_OPENAI_API", "WITT_OPENAI_STORE", "WITT_OPENAI_MAX_OUTPUT_TOKENS", "WITT_OPENAI_REASONING_EFFORT",
               "WITT_OPENAI_TIMEOUT_S", "WITT_ANTHROPIC_EFFORT", "WITT_ANTHROPIC_EFFORT_ELICIT", "WITT_CONFIG_LEDGER",
               "WITT_JUDGE_RETRIES")
for _k in _ADR81_ENVS:
    os.environ.pop(_k, None)

# --- red BLOQUEADA y contada: la función real jamás se alcanza (= 0 al final) ----------------------------------------
_NET_CALLS = []


def _blocked_urlopen(*a, **k):
    _NET_CALLS.append(getattr(a[0], "full_url", repr(a[0])) if a else repr(k))
    raise AssertionError("smoke: urllib.request.urlopen bloqueado (cero red)")


urllib.request.urlopen = _blocked_urlopen

from lib import composite_auditor as ca  # noqa: E402
from lib import models  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


def _no_openai_loaded():
    return not any(k == "openai" or k.startswith("openai.") for k in sys.modules)


def _purge_openai():
    for k in [k for k in sys.modules if k == "openai" or k.startswith("openai.")]:
        sys.modules.pop(k, None)


def _raises(fn):
    """Devuelve la excepción que `fn` lanza (None si no lanza)."""
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        return e
    return None


ca._backoff = lambda seconds: None   # sin esperas en el gate: la política de reintento se mide por CONTEO de intentos

# ids SIN literal: todos de la tabla (gate estático M.4)
G2 = models.GENERATIONS["g2-2026-09"]["defaults"]
OPUS = G2["synthesizer"]                                                          # thinking_default adaptive
HAIKU = G2["judge.evidence-grounding"]                                            # thinking_default off
SONNET = G2["judge.overclaim"]
GPT_BRIDGE = G2["judge.reproducibility"]                                          # api openai-chat-completions (puente)
ASTRA = next(m for m, r in models.MODELS.items() if r["status"] == "candidate")   # openai-responses, reasoning True
SOL = next(m for m, r in models.MODELS.items() if r["status"] == "not-adopted")   # openai-responses, reasoning True
ASTRA_REPORTED = ASTRA + "-2026-09-01"                                            # alias → snapshot (relation 'prefix')
BRIDGE_REPORTED = GPT_BRIDGE + "-2024-08-06"
FAKE_KEY = "smoke-fake-openai-key-not-a-secret"
VERDICT_OK = {"verdict": "APPROVE", "caught": "", "correction_applied": "", "confidence": 0.8, "reasons": ["ok"]}
OTHER_TOOL = {"name": "emit_verdict", "description": "otro schema (run_held_out)",
              "input_schema": {"type": "object",
                               "properties": {"verdict": {"type": "string"}, "overall_score": {"type": "number"}},
                               "required": ["verdict", "overall_score"]}}


# --- fakes duck-typed (la FORMA de los objetos Pydantic del SDK, sin importar openai) --------------------------------
class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _fc(arguments, name=None):
    return _Obj(type="function_call", call_id="call_1", name=name or ca.VERDICT_TOOL["name"],
                arguments=arguments if isinstance(arguments, str) else json.dumps(arguments))


def _reasoning():
    return _Obj(type="reasoning", id="rs_1", summary=[])


def _usage(inp=100, out=40, reasoning=30, cached=10, total=140):
    return _Obj(input_tokens=inp, output_tokens=out, total_tokens=total,
                output_tokens_details=_Obj(reasoning_tokens=reasoning), input_tokens_details=_Obj(cached_tokens=cached))


def _resp(output, model=None, status="completed", incomplete_reason=None, usage="default", rid="resp_fake_1",
          error=None):
    return _Obj(id=rid, model=model or ASTRA_REPORTED, status=status, output=list(output),
                incomplete_details=(_Obj(reason=incomplete_reason) if incomplete_reason else None),
                usage=(_usage() if usage == "default" else usage), error=error)


class _Endpoint:
    """Guion de respuestas/excepciones; registra los kwargs de cada create()."""
    def __init__(self, script):
        self.script, self.calls = list(script), []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.script:
            raise AssertionError("fake: guion agotado (llamada no prevista)")
        nxt = self.script.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt


class _FakeClient:
    def __init__(self, responses=(), chat=(), with_responses=True):
        if with_responses:
            self.responses = _Endpoint(responses)
        self.chat = _Obj(completions=_Endpoint(chat))


class FakeAPIStatusError(Exception):      # forma del SDK: .status_code
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(FakeAPIStatusError):
    pass


class APIConnectionError(Exception):      # el clasificador mira el NOMBRE en el MRO, como con el SDK real
    pass


def _chat_resp(args=VERDICT_OK, finish="tool_calls", model=None, with_tool_call=True):
    tc = ([_Obj(function=_Obj(arguments=json.dumps(args) if isinstance(args, dict) else args))]
          if with_tool_call else None)
    return _Obj(id="chatcmpl_1", model=model or BRIDGE_REPORTED,
                choices=[_Obj(finish_reason=finish, message=_Obj(tool_calls=tc))],
                usage=_Obj(model_dump=lambda: {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70}))


EXPECTED_USAGE = {"input_tokens": 100, "output_tokens": 40, "total_tokens": 140, "reasoning_tokens": 30, "cached_tokens": 10}

# =====================================================================================================================
# 1. _responses_kwargs (C.1): función PURA, kwargs exactos
# =====================================================================================================================
kw = ca._responses_kwargs(ASTRA, "SYS", "USER", ca.VERDICT_TOOL, 4000, False, None)
check("(C.1) _responses_kwargs EXACTOS: {model, instructions=system, input=user_text, tools[{type function, name, "
      "description, parameters=input_schema, strict False}], tool_choice {type function, name}, parallel_tool_calls "
      "False, max_output_tokens 4000, store False} y SIN `reasoning` cuando no hay effort",
      kw == {"model": ASTRA, "instructions": "SYS", "input": "USER",
             "tools": [{"type": "function", "name": ca.VERDICT_TOOL["name"],
                        "description": ca.VERDICT_TOOL["description"],
                        "parameters": ca.VERDICT_TOOL["input_schema"], "strict": False}],
             "tool_choice": {"type": "function", "name": ca.VERDICT_TOOL["name"]},
             "parallel_tool_calls": False, "max_output_tokens": 4000, "store": False}, json.dumps(kw)[:300])
check("(C.1) con reasoning_effort='medium' → kwargs['reasoning'] == {'effort': 'medium'}; store=True viaja como bool",
      ca._responses_kwargs(ASTRA, "S", "U", ca.VERDICT_TOOL, 8000, True, "medium")["reasoning"] == {"effort": "medium"}
      and ca._responses_kwargs(ASTRA, "S", "U", ca.VERDICT_TOOL, 8000, True, "medium")["store"] is True)
check("(C.1) _reasoning_effort_for: SÓLO env ∈ low|medium|high (normalizada a minúsculas) Y tabla reasoning True — "
      "candidato Responses 'MEDIUM' → 'medium'; puente chat (reasoning False) → None; candidato sin env → None; "
      "effort inválido 'ultra' → None; not-adopted (reasoning True) 'low' → 'low'",
      ca._reasoning_effort_for(ASTRA, env={"WITT_OPENAI_REASONING_EFFORT": "MEDIUM"}) == "medium"
      and ca._reasoning_effort_for(GPT_BRIDGE, env={"WITT_OPENAI_REASONING_EFFORT": "medium"}) is None
      and ca._reasoning_effort_for(ASTRA, env={}) is None
      and ca._reasoning_effort_for(ASTRA, env={"WITT_OPENAI_REASONING_EFFORT": "ultra"}) is None
      and ca._reasoning_effort_for(SOL, env={"WITT_OPENAI_REASONING_EFFORT": "low"}) == "low")
check("(C.1) defaults de env por la TABLA (models.env_value): WITT_OPENAI_STORE (False, default-unset), "
      "WITT_OPENAI_MAX_OUTPUT_TOKENS 4000, WITT_OPENAI_TIMEOUT_S 120; chat conserva OPENAI_CHAT_MAX_TOKENS 1200",
      models.env_value("WITT_OPENAI_STORE", {}) == (False, "default-unset:WITT_OPENAI_STORE")
      and models.env_value("WITT_OPENAI_MAX_OUTPUT_TOKENS", {})[0] == 4000
      and models.env_value("WITT_OPENAI_TIMEOUT_S", {})[0] == 120 and ca.OPENAI_CHAT_MAX_TOKENS == 1200)

# =====================================================================================================================
# 2. El SDK real, UNA vez y sin red: firma de Responses.create ⊇ kwargs; OpenAI(timeout, max_retries=0); luego se purga
# =====================================================================================================================
try:
    import openai as _oai  # noqa: E402
    from openai.resources.responses import Responses as _Responses  # noqa: E402
    _params = set(inspect.signature(_Responses.create).parameters)
    check(f"(C.1) kwargs de _responses_kwargs (+reasoning) ⊆ parámetros REALES de openai.resources.responses.Responses.create "
          f"(openai {_oai.__version__}) — la forma no diverge del SDK del venv",
          (set(kw) | {"reasoning"}) <= _params, f"faltan: {sorted((set(kw) | {'reasoning'}) - _params)}")
    os.environ["OPENAI_API_KEY"] = FAKE_KEY
    _cl = ca._openai_client()
    os.environ["WITT_OPENAI_TIMEOUT_S"] = "33"
    _cl33 = ca._openai_client()
    _cl7 = ca._openai_client(7)
    os.environ.pop("WITT_OPENAI_TIMEOUT_S", None)
    os.environ["OPENAI_API_KEY"] = ""
    check("(C.1) _openai_client(): OpenAI REAL construido sin red con max_retries=0 (el SDK reintentaría 2× en silencio y "
          "attempts[] mentiría) y timeout = WITT_OPENAI_TIMEOUT_S (default 120; env 33; explícito 7); expone .responses.create",
          _cl.max_retries == 0 and _cl33.max_retries == 0 and float(_cl.timeout) == 120.0 and float(_cl33.timeout) == 33.0
          and float(_cl7.timeout) == 7.0 and callable(getattr(getattr(_cl, "responses", None), "create", None)),
          f"max_retries={_cl.max_retries} timeout={_cl.timeout!r}/{_cl33.timeout!r}/{_cl7.timeout!r}")
    del _cl, _cl33, _cl7, _Responses, _oai
except Exception as e:  # pragma: no cover
    check("(C.1) import openai en el venv de los gates", False, f"{type(e).__name__}: {e}")
_purge_openai()
check("(M.3) sys.modules SIN 'openai' tras la sección del SDK (se purga; el resto del gate corre con fakes)", _no_openai_loaded())

# =====================================================================================================================
# 3. no-api-key ANTES del import y de la red · sdk-unavailable (SDK bloqueado / cliente sin .responses)
# =====================================================================================================================
e = _raises(lambda: ca._openai_client())
check("(C.1) sin OPENAI_API_KEY → CallerError('no-api-key') ANTES de importar el SDK (sys.modules sigue sin openai) y sin red; "
      "isinstance RuntimeError; _error_string 'RuntimeError: OPENAI_API_KEY not set …'",
      isinstance(e, ca.CallerError) and e.kind == "no-api-key" and isinstance(e, RuntimeError) and _no_openai_loaded()
      and ca._error_string(e).startswith("RuntimeError: OPENAI_API_KEY not set") and _NET_CALLS == [])
e = _raises(lambda: ca._openai_responses_call(ASTRA, "S", "U"))
check("(C.1) _openai_responses_call sin llave → 'no-api-key' con CERO llamadas (el cliente no se construye)",
      isinstance(e, ca.CallerError) and e.kind == "no-api-key")
os.environ["OPENAI_API_KEY"] = FAKE_KEY
sys.modules["openai"] = None      # `import openai` → ImportError: el SDK "no está"
try:
    e = _raises(lambda: ca._openai_client())
finally:
    sys.modules.pop("openai", None)
    os.environ["OPENAI_API_KEY"] = ""
check("(C.1) SDK no importable → CallerError('sdk-unavailable') (llave presente, cero red)",
      isinstance(e, ca.CallerError) and e.kind == "sdk-unavailable" and _NET_CALLS == [], str(e)[:120])
_old = _FakeClient(with_responses=False)
e = _raises(lambda: ca._openai_responses_call(ASTRA, "S", "U", client=_old))
check("(C.1) cliente SIN client.responses (SDK viejo) → 'sdk-unavailable' antes de cualquier create()",
      isinstance(e, ca.CallerError) and e.kind == "sdk-unavailable" and _old.chat.completions.calls == [])

# =====================================================================================================================
# 4. Éxito por Responses: 3-tupla, usage numérico, meta, kwargs enviados == _responses_kwargs, env → kwargs
# =====================================================================================================================
fk = _FakeClient([_resp([_reasoning(), _fc(VERDICT_OK)])])
out, usage, meta = ca._openai_responses_call(ASTRA, "SYS", "USER", client=fk)
check("(C.1) éxito: los ítems `reasoning` se ignoran y se lee el ÚNICO function_call → out == veredicto; usage NUMÉRICO "
      "{input 100, output 40, total 140, reasoning_tokens 30 (YA dentro de output), cached_tokens 10}; meta {model_reported, "
      "api 'openai-responses', response_id, status 'completed', incomplete_reason None, max_output_tokens 4000 (tope EFECTIVO "
      "— corrector)}; 1 llamada",
      out == VERDICT_OK and usage == EXPECTED_USAGE
      and meta == {"model_reported": ASTRA_REPORTED, "api": "openai-responses", "response_id": "resp_fake_1",
                   "status": "completed", "incomplete_reason": None, "max_output_tokens": 4000}
      and len(fk.responses.calls) == 1, json.dumps([usage, meta]))
check("(C.1) los kwargs ENVIADOS == _responses_kwargs(model, system, user_text, VERDICT_TOOL, 4000, False, None) con los "
      "defaults de la tabla (store False, max 4000, sin reasoning, strict False, parallel False)",
      fk.responses.calls[0] == ca._responses_kwargs(ASTRA, "SYS", "USER", ca.VERDICT_TOOL, 4000, False, None))
check("(B) usage: sólo números (ni model_reported ni api dentro; la webapp tipa Record<string, number>) y relation(pedido, "
      "reportado) == 'prefix' (alias → snapshot fechado: NEUTRO)",
      all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in usage.values())
      and not ({"model_reported", "api"} & set(usage)) and models.relation(ASTRA, meta["model_reported"]) == "prefix")
fk = _FakeClient([_resp([_fc(VERDICT_OK)], usage=_Obj(input_tokens=5, output_tokens=3, total_tokens=8))])
_, usage2, _ = ca._openai_responses_call(ASTRA, "S", "U", client=fk)
check("(C.1) usage sin details → reasoning_tokens/cached_tokens AUSENTES (la API no los mandó: jamás un 0 inventado)",
      usage2 == {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8})
os.environ.update({"WITT_OPENAI_REASONING_EFFORT": "high", "WITT_OPENAI_STORE": "1", "WITT_OPENAI_MAX_OUTPUT_TOKENS": "8000"})
fk_a = _FakeClient([_resp([_fc(VERDICT_OK)])])
ca._openai_responses_call(ASTRA, "S", "U", client=fk_a)
fk_b = _FakeClient([_resp([_fc(VERDICT_OK)], model=BRIDGE_REPORTED)])
ca._openai_responses_call(GPT_BRIDGE, "S", "U", client=fk_b)
for _k in ("WITT_OPENAI_REASONING_EFFORT", "WITT_OPENAI_STORE", "WITT_OPENAI_MAX_OUTPUT_TOKENS"):
    os.environ.pop(_k, None)
check("(C.1) env → kwargs EN LA LLAMADA (sin reimportar): REASONING_EFFORT=high + STORE=1 + MAX_OUTPUT_TOKENS=8000 → el "
      "candidato (reasoning True) manda reasoning {effort high}, store True, max 8000; el puente (reasoning False) NO manda "
      "reasoning con la misma env",
      fk_a.responses.calls[0]["reasoning"] == {"effort": "high"} and fk_a.responses.calls[0]["store"] is True
      and fk_a.responses.calls[0]["max_output_tokens"] == 8000
      and "reasoning" not in fk_b.responses.calls[0] and fk_b.responses.calls[0]["store"] is True)
fk = _FakeClient([_resp([_fc({**VERDICT_OK, "confidence": None,
                              "caught": 'issue</parameter>\n<parameter name="confidence">0.4'})])])
out, _, _ = ca._openai_responses_call(ASTRA, "S", "U", client=fk)
check("(ADR-0057) recover_trapped_params en el camino Responses: confidence atrapada como texto se levanta (0.4), "
      "`caught` se corta en el artefacto, `_recovered_fields ['confidence']` declarado; sin reintento (1 llamada)",
      out["confidence"] == 0.4 and out["caught"] == "issue" and out["_recovered_fields"] == ["confidence"]
      and len(fk.responses.calls) == 1)
fk = _FakeClient([_resp([_fc(json.dumps({"verdict": "correct", "overall_score": 0.7}), name="emit_verdict")])])
out, _, _ = ca._openai_responses_call(ASTRA, "S", "U", tool=OTHER_TOOL, client=fk)
check("(L.n) tool= ajeno (run_held_out): se busca el function_call de ESE nombre y NO se valida `verdict` contra VOCABULARY",
      out == {"verdict": "correct", "overall_score": 0.7}
      and fk.responses.calls[0]["tools"][0]["name"] == "emit_verdict"
      and fk.responses.calls[0]["tool_choice"] == {"type": "function", "name": "emit_verdict"})

# =====================================================================================================================
# 5. Fallos de TRANSPORTE (C.2): 429/network reintentan UNA vez; 400/401/404 no; genérico 'unclassified' sin reintento
# =====================================================================================================================
fk = _FakeClient([RateLimitError(429, "Error code: 429 - rate limited"), _resp([_fc(VERDICT_OK)])])
out, _, _ = ca._openai_responses_call(ASTRA, "S", "U", client=fk)
check("(C.2) http-429 → UN reintento de transporte y éxito: 2 llamadas, veredicto", out == VERDICT_OK and len(fk.responses.calls) == 2)
fk = _FakeClient([RateLimitError(429, "Error code: 429 - rate limited")] * 2)
e = _raises(lambda: ca._openai_responses_call(ASTRA, "S", "U", client=fk))
check("(C.2) http-429 ×2 → CallerError kind 'http-429' tras 2 llamadas; legacy_type_name = la clase del SDK → "
      "_error_string byte-igual al f\"{type(e).__name__}: {str(e)[:200]}\" de f57a3d3",
      isinstance(e, ca.CallerError) and e.kind == "http-429" and len(fk.responses.calls) == 2
      and ca._error_string(e) == "RateLimitError: Error code: 429 - rate limited" and e.legacy_type_name == "RateLimitError")
for code in (400, 401, 404):
    fk = _FakeClient([FakeAPIStatusError(code, f"Error code: {code} - configuración")] * 2)
    e = _raises(lambda: ca._openai_responses_call(ASTRA, "S", "U", client=fk))
    check(f"(C.2) http-{code} → SIN reintento (1 llamada; 4xx es configuración), kind 'http-{code}'",
          isinstance(e, ca.CallerError) and e.kind == f"http-{code}" and len(fk.responses.calls) == 1)
fk = _FakeClient([APIConnectionError("Connection error."), APIConnectionError("Connection error.")])
e = _raises(lambda: ca._openai_responses_call(ASTRA, "S", "U", client=fk))
check("(C.2) APIConnectionError (duck: nombre de clase) → 'network', UN reintento y luego raise (2 llamadas); "
      "TimeoutError builtin también clasifica 'network'",
      isinstance(e, ca.CallerError) and e.kind == "network" and len(fk.responses.calls) == 2
      and ca.failure_kind_of(TimeoutError("t")) == "network")
fk = _FakeClient([ValueError("boom"), _resp([_fc(VERDICT_OK)])])
e = _raises(lambda: ca._openai_responses_call(ASTRA, "S", "U", client=fk))
check("(C.2) excepción ajena al vocabulario → 'unclassified' SIN reintento (no se adivina); mensaje conservado",
      isinstance(e, ca.CallerError) and e.kind == "unclassified" and len(fk.responses.calls) == 1
      and ca._error_string(e) == "ValueError: boom")

# =====================================================================================================================
# 6. Fallos de CONTENIDO (C.2): UN reintento; el intento fallido conserva usage/meta MEDIDOS; response-failed sin reintento
# =====================================================================================================================
fk = _FakeClient([_resp([_reasoning()], status="incomplete", incomplete_reason="max_output_tokens")] * 2)
e = _raises(lambda: ca._openai_responses_call(ASTRA, "S", "U", client=fk))
check("(C.2) status 'incomplete' + reason max_output_tokens sin function_call → 'incomplete:max_output_tokens', UN reintento "
      "(2 llamadas); la excepción trae usage MEDIDO y meta {incomplete_reason 'max_output_tokens', model_reported}",
      isinstance(e, ca.CallerError) and e.kind == "incomplete:max_output_tokens" and len(fk.responses.calls) == 2
      and e.usage == EXPECTED_USAGE and e.meta["incomplete_reason"] == "max_output_tokens"
      and e.meta["model_reported"] == ASTRA_REPORTED and e.meta["status"] == "incomplete")
fk = _FakeClient([_resp([], status="incomplete", incomplete_reason="content_filter")])
e = _raises(lambda: ca._openai_responses_call(ASTRA, "S", "U", client=fk, retries=0))
check("(C.2) incomplete content_filter → 'incomplete:content_filter' (retries=0: 1 llamada)",
      isinstance(e, ca.CallerError) and e.kind == "incomplete:content_filter" and len(fk.responses.calls) == 1)


# corrector ADR-0081 (C.2): refusal del clasificador de OpenAI (HTTP 200) y truncación con function_call PARCIAL/COMPLETO
def _refusal_msg(text="I can't help with that request."):
    return _Obj(type="message", id="msg_1", role="assistant", status="completed",
                content=[_Obj(type="refusal", refusal=text)])


fk = _FakeClient([_resp([_refusal_msg()])] * 2)
e = _raises(lambda: ca._openai_responses_call(ASTRA, "S", "U", client=fk))
check("(C.2, corrector) ítem message con content[].type 'refusal' → kind 'refusal' SIN reintento (1 llamada; antes caía en "
      "no-function-call y se reintentaba); el mensaje cita el texto del rechazo; usage/meta MEDIDOS conservados; _error_string "
      "'RuntimeError: …' (legacy_type_name)",
      isinstance(e, ca.CallerError) and e.kind == "refusal" and len(fk.responses.calls) == 1
      and str(e) == "openai responses: refusal (I can't help with that request.)" and e.usage == EXPECTED_USAGE
      and e.meta["model_reported"] == ASTRA_REPORTED and ca._error_string(e) == "RuntimeError: " + str(e))
fk = _FakeClient([_resp([_refusal_msg(), _fc(VERDICT_OK)])] * 2)
e = _raises(lambda: ca._openai_responses_call(ASTRA, "S", "U", client=fk))
check("(C.2, corrector) refusal JUNTO a un function_call válido → 'refusal' igual (de una respuesta con rechazo no se fabrica "
      "veredicto), 1 llamada",
      isinstance(e, ca.CallerError) and e.kind == "refusal" and len(fk.responses.calls) == 1)
fk = _FakeClient([_resp([_reasoning(), _fc('{"verdict": "APPRO')], status="incomplete", incomplete_reason="max_output_tokens")] * 2)
e = _raises(lambda: ca._openai_responses_call(ASTRA, "S", "U", client=fk))
check("(C.2, corrector) status 'incomplete' (max_output_tokens) CON function_call PARCIAL (arguments cortados) → "
      "'incomplete:max_output_tokens' (no 'arguments-unparseable': la causa es el tope, R1), UN reintento (2 llamadas); el "
      "mensaje declara 'function_call … presente'",
      isinstance(e, ca.CallerError) and e.kind == "incomplete:max_output_tokens" and len(fk.responses.calls) == 2
      and "presente" in str(e) and e.meta["incomplete_reason"] == "max_output_tokens")
fk = _FakeClient([_resp([_fc(VERDICT_OK)], status="incomplete", incomplete_reason="max_output_tokens")] * 2)
e = _raises(lambda: ca._openai_responses_call(ASTRA, "S", "U", client=fk))
check("(C.2, corrector) status 'incomplete' con function_call COMPLETO y parseable → tampoco se devuelve veredicto: "
      "'incomplete:max_output_tokens' (la API declaró la respuesta truncada; no se afirma un veredicto sobre ella), 2 llamadas",
      isinstance(e, ca.CallerError) and e.kind == "incomplete:max_output_tokens" and len(fk.responses.calls) == 2)
fk = _FakeClient([_resp([_reasoning()], status="incomplete", incomplete_reason="max_output_tokens")])
e = _raises(lambda: ca._openai_responses_call(ASTRA, "S", "U", client=fk, retries=0))
check("(C.2, corrector) sin function_call y status incomplete: el mensaje declara 'function_call … ausente'; meta lleva "
      "max_output_tokens 4000 (el tope EFECTIVO bajo el que se truncó — audit.panel[].max_tokens es null para OpenAI)",
      isinstance(e, ca.CallerError) and "ausente" in str(e) and e.meta["max_output_tokens"] == 4000)
fk = _FakeClient([_resp([_reasoning()])] * 2)
e = _raises(lambda: ca._openai_responses_call(ASTRA, "S", "U", client=fk))
check("(C.2) completed sin function_call → 'no-function-call' tras reintento (2 llamadas); el mensaje lista los tipos de output",
      isinstance(e, ca.CallerError) and e.kind == "no-function-call" and len(fk.responses.calls) == 2
      and "output_types=['reasoning']" in str(e))
fk = _FakeClient([_resp([_fc(VERDICT_OK, name="otra_tool")])] * 2)
e = _raises(lambda: ca._openai_responses_call(ASTRA, "S", "U", client=fk))
check("(C.2) function_call con OTRO nombre → 'no-function-call' (sólo cuenta el de la tool pedida)",
      isinstance(e, ca.CallerError) and e.kind == "no-function-call")
fk = _FakeClient([_resp([_fc("{bad json")])] * 2)
e = _raises(lambda: ca._openai_responses_call(ASTRA, "S", "U", client=fk))
check("(C.2) arguments no parseables → 'arguments-unparseable' tras reintento (2 llamadas)",
      isinstance(e, ca.CallerError) and e.kind == "arguments-unparseable" and len(fk.responses.calls) == 2)
fk = _FakeClient([_resp([_fc({**VERDICT_OK, "verdict": "MAYBE"})])] * 2)
e = _raises(lambda: ca._openai_responses_call(ASTRA, "S", "U", client=fk))
check("(C.2) verdict fuera del vocabulario → 'verdict-off-vocabulary' tras reintento; mensaje \"openai: invalid verdict 'MAYBE'\" "
      "byte-igual al de f57a3d3",
      isinstance(e, ca.CallerError) and e.kind == "verdict-off-vocabulary" and len(fk.responses.calls) == 2
      and str(e) == "openai: invalid verdict 'MAYBE'")
fk = _FakeClient([_resp([_fc({**VERDICT_OK, "confidence": None})]), _resp([_fc(VERDICT_OK)])])
out, _, _ = ca._openai_responses_call(ASTRA, "S", "U", client=fk)
check("(C.2) required ausente (confidence) → UN reintento y el 2º completo se devuelve (2 llamadas)",
      out == VERDICT_OK and len(fk.responses.calls) == 2)
fk = _FakeClient([_resp([_fc({**VERDICT_OK, "confidence": None})])] * 2)
out, _, _ = ca._openai_responses_call(ASTRA, "S", "U", client=fk)
check("(C.2) required ausente en AMBOS intentos → se devuelve lo recibido (confidence None DECLARADO, no se lanza): "
      "el llamador marca la ausencia (misma disciplina que el caller Anthropic)",
      out.get("confidence") is None and out["verdict"] == "APPROVE" and len(fk.responses.calls) == 2)
fk = _FakeClient([_resp([], status="failed", error=_Obj(code="server_error", message="The server had an error"))] * 2)
e = _raises(lambda: ca._openai_responses_call(ASTRA, "S", "U", client=fk))
check("(C.2) status 'failed' → 'response-failed:server_error' SIN reintento (1 llamada); en vocabulario por prefijo",
      isinstance(e, ca.CallerError) and e.kind == "response-failed:server_error" and len(fk.responses.calls) == 1
      and ca.failure_kind_in_vocabulary(e.kind))
fk = _FakeClient([_resp([_reasoning()], status="incomplete", incomplete_reason="max_output_tokens"), _resp([_fc(VERDICT_OK)])])
out, _, meta = ca._openai_responses_call(ASTRA, "S", "U", client=fk)
check("(C.2) contenido reintentado con éxito: incomplete y luego completo → veredicto, 2 llamadas, meta del 2º",
      out == VERDICT_OK and len(fk.responses.calls) == 2 and meta["status"] == "completed")

# =====================================================================================================================
# 7. _openai_chat_call: la petición de f57a3d3 byte a byte + meta + kinds (kill-switch WITT_OPENAI_API=chat-completions)
# =====================================================================================================================
fk = _FakeClient(chat=[_chat_resp()])
out, usage, meta = ca._openai_chat_call(GPT_BRIDGE, "SYS", "USER", client=fk)
check("(C.1) chat byte a byte: kwargs {model, max_tokens 1200, timeout 120, messages system+user, tools [function], "
      "tool_choice function}; usage = resp.usage.model_dump() como hoy; meta {model_reported, api 'openai-chat-completions', "
      "response_id, finish_reason, max_tokens 1200 (tope EFECTIVO — corrector)}",
      fk.chat.completions.calls[0] == {
          "model": GPT_BRIDGE, "max_tokens": 1200, "timeout": 120,
          "messages": [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USER"}],
          "tools": [{"type": "function", "function": {"name": ca.VERDICT_TOOL["name"],
                                                     "description": ca.VERDICT_TOOL["description"],
                                                     "parameters": ca.VERDICT_TOOL["input_schema"]}}],
          "tool_choice": {"type": "function", "function": {"name": ca.VERDICT_TOOL["name"]}}}
      and out == VERDICT_OK and usage == {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70}
      and meta == {"model_reported": BRIDGE_REPORTED, "api": "openai-chat-completions", "response_id": "chatcmpl_1",
                   "finish_reason": "tool_calls", "max_tokens": 1200}, json.dumps(fk.chat.completions.calls[0])[:200])
fk = _FakeClient(chat=[_chat_resp(finish="length", with_tool_call=False)] * 2)
e = _raises(lambda: ca._openai_chat_call(GPT_BRIDGE, "S", "U", client=fk))
check("(C.2) chat sin tool_call (finish_reason length) → 'incomplete:max_output_tokens'; mensaje 'openai: no tool_call "
      "(finish_reason=length)' byte-igual; SIN reintento propio (1 llamada: audit() reintenta por WITT_JUDGE_RETRIES); usage/meta medidos",
      isinstance(e, ca.CallerError) and e.kind == "incomplete:max_output_tokens" and len(fk.chat.completions.calls) == 1
      and str(e) == "openai: no tool_call (finish_reason=length)" and e.usage["prompt_tokens"] == 50
      and e.meta["model_reported"] == BRIDGE_REPORTED)
fk = _FakeClient(chat=[_chat_resp(args={**VERDICT_OK, "verdict": "MAYBE"})])
e = _raises(lambda: ca._openai_chat_call(GPT_BRIDGE, "S", "U", client=fk))
check("(C.2) chat verdict fuera → 'verdict-off-vocabulary' con el mensaje de f57a3d3",
      isinstance(e, ca.CallerError) and e.kind == "verdict-off-vocabulary" and str(e) == "openai: invalid verdict 'MAYBE'")
fk = _FakeClient(chat=[FakeAPIStatusError(500, "Error code: 500 - server")])
e = _raises(lambda: ca._openai_chat_call(GPT_BRIDGE, "S", "U", client=fk))
check("(C.2) chat: excepción del SDK envuelta → kind 'http-500', nombre de clase conservado en _error_string",
      isinstance(e, ca.CallerError) and e.kind == "http-500" and ca._error_string(e) == "FakeAPIStatusError: Error code: 500 - server")
fk = _FakeClient(chat=[_chat_resp(args={"verdict": "correct", "overall_score": 0.7})])
out, _, _ = ca._openai_chat_call(GPT_BRIDGE, "S", "U", tool=OTHER_TOOL, client=fk)
check("(L.n) chat con tool= ajeno: tools[0].function.name == 'emit_verdict' y sin validación VOCABULARY",
      out == {"verdict": "correct", "overall_score": 0.7}
      and fk.chat.completions.calls[0]["tools"][0]["function"]["name"] == "emit_verdict")

# =====================================================================================================================
# 8. Despacho (C.3): _default_caller por member['api']; legado inferido de la familia; WITT_OPENAI_API fuerza; alias
# =====================================================================================================================
_ORIG_ANTHROPIC, _ORIG_CLIENT = ca._anthropic_tool_call, ca._openai_client
_cap = {}


def _fake_anthropic(model, system, user_text, tool=None, timeout=120, retries=1, max_tokens=1200, effort=None,
                    return_meta=False):
    _cap.update({"model": model, "tool": tool, "max_tokens": max_tokens, "effort": effort, "return_meta": return_meta,
                 "timeout": timeout})
    return ({**VERDICT_OK}, {"input_tokens": 1, "output_tokens": 1},
            {"model_reported": model + "-20260901", "api": "anthropic-messages", "stop_reason": "tool_use"})


_clients = {"responses": None, "chat": None}


def _fake_client(timeout=None):
    _clients["timeout"] = timeout
    return _clients["current"]


ca._anthropic_tool_call = _fake_anthropic
ca._openai_client = _fake_client
try:
    PM = models.panel(env={}, today=models.MODEL_TABLE_AS_OF)
    res = ca._default_caller(PM[0], "S", "U")
    check("(C.3) member anthropic de la TABLA (g2 correctness) → _anthropic_tool_call(model, tool None, max_tokens 4000 = tope "
          "judge-anthropic g2, effort None sin env, return_meta True); 3-tupla con meta.api 'anthropic-messages'",
          _cap == {"model": OPUS, "tool": None, "max_tokens": 4000, "effort": None, "return_meta": True, "timeout": 120}
          and isinstance(res, tuple) and len(res) == 3 and res[2]["api"] == "anthropic-messages", json.dumps(_cap))
    os.environ["WITT_ANTHROPIC_EFFORT"] = "low"
    ca._default_caller(PM[0], "S", "U")
    eff_opus = _cap["effort"]
    ca._default_caller(PM[2], "S", "U")
    eff_haiku = _cap["effort"]
    os.environ.pop("WITT_ANTHROPIC_EFFORT", None)
    check("(C.4) WITT_ANTHROPIC_EFFORT=low → effort 'low' SÓLO al modelo con thinking_default 'adaptive' (correctness g2); al de "
          "thinking_default 'off' (evidence-grounding g2) NO se envía (None)",
          eff_opus == "low" and eff_haiku is None)
    ca._default_caller({"reviewer": SONNET, "family": "anthropic", "lens": "overclaim"}, "S", "U", tool=OTHER_TOOL)
    check("(C.3) member LEGADO anthropic (sin api/max_tokens) → api inferido de la familia, max_tokens 1200 (el default de f57a3d3), "
          "tool= pasa entero",
          _cap["max_tokens"] == 1200 and _cap["tool"] is OTHER_TOOL and _cap["model"] == SONNET
          and ca._member_api({"reviewer": SONNET, "family": "anthropic", "lens": "overclaim"}) == ("anthropic-messages", "inferred-from-family"))
    _clients["current"] = _FakeClient(chat=[_chat_resp()])
    res = ca._default_caller(PM[3], "S", "U")
    check("(C.3) member openai de la tabla con api 'openai-chat-completions' (puente) → _openai_chat_call: 1 create en chat, "
          "meta.api 'openai-chat-completions'; el cliente se pidió con timeout None (→ env en el caller)",
          len(_clients["current"].chat.completions.calls) == 1 and res[2]["api"] == "openai-chat-completions"
          and _clients["timeout"] in (None, 120))
    PM_ASTRA = models.panel(env={"OPENAI_JUDGE_MODEL": ASTRA}, today=models.MODEL_TABLE_AS_OF)
    _clients["current"] = _FakeClient(responses=[_resp([_fc(VERDICT_OK)])])
    res = ca._default_caller(PM_ASTRA[3], "S", "U")
    check("(C.3) OPENAI_JUDGE_MODEL=candidato → member.api 'openai-responses' (tabla) → _openai_responses_call: 1 create en "
          "responses, 0 en chat; meta.api 'openai-responses'",
          PM_ASTRA[3]["api"] == "openai-responses" and len(_clients["current"].responses.calls) == 1
          and _clients["current"].chat.completions.calls == [] and res[2]["api"] == "openai-responses")
    PM_FORCE_R = models.panel(env={"WITT_OPENAI_API": "responses"}, today=models.MODEL_TABLE_AS_OF)
    _clients["current"] = _FakeClient(responses=[_resp([_fc(VERDICT_OK)], model=BRIDGE_REPORTED)])
    res_r = ca._default_caller(PM_FORCE_R[3], "S", "U")
    PM_FORCE_C = models.panel(env={"WITT_OPENAI_API": "chat-completions", "OPENAI_JUDGE_MODEL": ASTRA}, today=models.MODEL_TABLE_AS_OF)
    _clients["current"] = _FakeClient(chat=[_chat_resp(model=ASTRA_REPORTED)])
    res_c = ca._default_caller(PM_FORCE_C[3], "S", "U")
    check("(C.3) WITT_OPENAI_API=responses FUERZA al puente a Responses (api_source 'env:WITT_OPENAI_API'); "
          "'chat-completions' fuerza al candidato a chat (kill-switch)",
          PM_FORCE_R[3]["api"] == "openai-responses" and PM_FORCE_R[3]["api_source"] == "env:WITT_OPENAI_API"
          and res_r[2]["api"] == "openai-responses" and PM_FORCE_C[3]["api"] == "openai-chat-completions"
          and res_c[2]["api"] == "openai-chat-completions" and res_c[0] == VERDICT_OK)
    legacy_oai = {"reviewer": GPT_BRIDGE, "family": "openai", "lens": "reproducibility"}
    _clients["current"] = _FakeClient(chat=[_chat_resp()])
    ca._default_caller(legacy_oai, "S", "U")
    n_chat_legacy = len(_clients["current"].chat.completions.calls)
    os.environ["WITT_OPENAI_API"] = "responses"
    _clients["current"] = _FakeClient(responses=[_resp([_fc(VERDICT_OK)])])
    api_forced = ca._member_api(legacy_oai)
    ca._default_caller(legacy_oai, "S", "U")
    n_resp_forced = len(_clients["current"].responses.calls)
    os.environ.pop("WITT_OPENAI_API", None)
    check("(C.3) member LEGADO openai (sin api): api inferido de la familia por la tabla del id → chat (como hoy); con "
          "WITT_OPENAI_API=responses en os.environ → Responses (api_source 'inferred-from-family')",
          n_chat_legacy == 1 and api_forced == ("openai-responses", "inferred-from-family") and n_resp_forced == 1)
    check("(C.3) _member_api: PanelMember de la tabla → (api, 'table'); legado openai con id desconocido → "
          "('openai-responses', 'inferred-from-family'); sin familia y sin prefijo → (None, 'unknown-family')",
          ca._member_api(PM[3]) == ("openai-chat-completions", "table")
          and ca._member_api({"reviewer": "j-repro", "family": "openai", "lens": "reproducibility"}) == ("openai-responses", "inferred-from-family")
          and ca._member_api({"reviewer": "llama-9", "lens": "correctness"}) == (None, "unknown-family"))
    _clients["current"] = _FakeClient(responses=[_resp([_fc(VERDICT_OK)])], chat=[_chat_resp()])
    _cap.clear()
    e = _raises(lambda: ca._default_caller({"reviewer": "llama-9", "family": "unknown", "lens": "correctness"}, "S", "U"))
    check("(A/C.3) familia 'unknown' → CallerError('unknown-family') SIN llamar a nada (ni anthropic ni openai): fail-loud, "
          "no el `else: anthropic` de f57a3d3",
          isinstance(e, ca.CallerError) and e.kind == "unknown-family" and _cap == {}
          and _clients["current"].responses.calls == [] and _clients["current"].chat.completions.calls == [])
    _clients["current"] = _FakeClient(responses=[_resp([_fc(VERDICT_OK)])], chat=[_chat_resp()])
    r1 = ca._openai_tool_call(GPT_BRIDGE, "S", "U")
    r2 = ca._openai_tool_call(ASTRA, "S", "U")
    check("(C.1) alias _openai_tool_call (nombre de f57a3d3) despacha por la TABLA: puente → chat, candidato → Responses; 3-tuplas",
          len(_clients["current"].chat.completions.calls) == 1 and len(_clients["current"].responses.calls) == 1
          and r1[2]["api"] == "openai-chat-completions" and r2[2]["api"] == "openai-responses")

    # =================================================================================================================
    # 9. audit() con el fake: filas 1.10, attempts con error byte-igual + error_kind + model_reported/api, vocabulario
    # =================================================================================================================
    os.environ["OPENAI_JUDGE_MODEL"] = ASTRA
    _clients["current"] = _FakeClient(responses=[_resp([_reasoning(), _fc(VERDICT_OK)])])
    r = ca.audit({"c": 1}, {"e": 1})
    row = r["panel"][3]
    check("(D/B) audit() panel=None → models.panel() EN LA LLAMADA con OPENAI_JUDGE_MODEL del os.environ: fila reproducibility "
          "{reviewer candidato, family openai, family_source 'table', api 'openai-responses', api_source 'table', reviewer_source "
          "'env:OPENAI_JUDGE_MODEL', max_tokens None}; attempts[0] {status ok, usage numérico, model_reported, api, "
          "max_output_tokens 4000 (el tope EFECTIVO del transporte — corrector: la fila lo lleva null)}; APPROVE 4/4 con 2 familias",
          row["reviewer"] == ASTRA and row["family"] == "openai" and row["family_source"] == "table"
          and row["api"] == "openai-responses" and row["api_source"] == "table"
          and row["reviewer_source"] == "env:OPENAI_JUDGE_MODEL" and row["max_tokens"] is None
          and row["attempts"] == [{"attempt": 1, "usage": EXPECTED_USAGE, "model_reported": ASTRA_REPORTED,
                                   "api": "openai-responses", "max_output_tokens": 4000, "status": "ok"}]
          and r["verdict"] == "APPROVE" and r["n_valid"] == 4 and r["families_valid"] == ["anthropic", "openai"],
          json.dumps(row)[:400])
    row0 = r["panel"][0]
    check("(B) filas Anthropic: attempts[0].model_reported = lo que la API (fake) DIJO (alias + fecha) y api 'anthropic-messages'; "
          "max_tokens 4000 (tope g2 judge-anthropic); reviewer_source 'default:g2-2026-09'",
          row0["attempts"][0]["model_reported"] == OPUS + "-20260901" and row0["attempts"][0]["api"] == "anthropic-messages"
          and row0["max_tokens"] == 4000 and row0["reviewer_source"] == "default:g2-2026-09" and row0["api_source"] == "table")
    _clients["current"] = _FakeClient(responses=[FakeAPIStatusError(400, "Error code: 400 - Unsupported parameter")] * 2)
    r2 = ca.audit({"c": 1}, {"e": 1})
    row = r2["panel"][3]
    check("(C.2/D) juez OpenAI 400 en ambos intentos de audit() (WITT_JUDGE_RETRIES=1, capa ADR-0080 intacta): "
          "attempts[].error == 'FakeAPIStatusError: Error code: 400 - Unsupported parameter' (byte-igual al string de f57a3d3), "
          "error_kind 'http-400' en cada intento, sin model_reported (no hubo respuesta); fila errored; REVISE estructural "
          "panel_incomplete_reasons ['families'] (3 APPROVE Anthropic NO aprueban solos)",
          row["status"] == "errored" and row["error"] == "FakeAPIStatusError: Error code: 400 - Unsupported parameter"
          and len(row["attempts"]) == 2 and all(a["error_kind"] == "http-400" for a in row["attempts"])
          and all("model_reported" not in a for a in row["attempts"])
          and r2["verdict"] == "REVISE" and r2["panel_incomplete"] is True and r2["panel_incomplete_reasons"] == ["families"]
          and r2["n_valid"] == 3 and r2["families_valid"] == ["anthropic"], json.dumps(row)[:400])
    check("(C.2) audit.failure_kinds_vocabulary congelado == {exact: FAILURE_KINDS_EXACT, prefixes: FAILURE_KIND_PREFIXES, rule}; "
          "todo error_kind medido en este gate cumple failure_kind_in_vocabulary",
          r2["failure_kinds_vocabulary"] == {"exact": list(ca.FAILURE_KINDS_EXACT), "prefixes": list(ca.FAILURE_KIND_PREFIXES),
                                             "rule": ca.FAILURE_KINDS_RULE}
          and all(ca.failure_kind_in_vocabulary(a["error_kind"]) for rr in (r, r2) for x in rr["panel"]
                  for a in x["attempts"] if "error_kind" in a))
    _clients["current"] = _FakeClient(responses=[_resp([_reasoning()], status="incomplete", incomplete_reason="max_output_tokens")] * 4)
    r3 = ca.audit({"c": 1}, {"e": 1})
    row = r3["panel"][3]
    check("(C.2) juez truncado (incomplete:max_output_tokens en los 2 intentos del caller × 2 de audit = 4 llamadas): cada intento de "
          "audit lleva error_kind 'incomplete:max_output_tokens', usage MEDIDO del intento fallido (la API cobró) y model_reported/api; "
          "la fila errored suma ese gasto en `usage` y audit.usage lo incluye",
          row["status"] == "errored" and len(_clients["current"].responses.calls) == 4
          and all(a["error_kind"] == "incomplete:max_output_tokens" and a["usage"] == EXPECTED_USAGE
                  and a["model_reported"] == ASTRA_REPORTED and a["api"] == "openai-responses" for a in row["attempts"])
          and row["usage"]["input_tokens"] == 200 and r3["usage"]["input_tokens"] == 200 + 3
          and r3["panel_incomplete_reasons"] == ["families"], json.dumps(row)[:400])
    os.environ.pop("OPENAI_JUDGE_MODEL", None)
finally:
    ca._anthropic_tool_call, ca._openai_client = _ORIG_ANTHROPIC, _ORIG_CLIENT

# =====================================================================================================================
# 10. _anthropic_tool_call REAL con urlopen FAKE (transporte simulado — cero red): 2-tupla intacta, return_meta, kinds
# =====================================================================================================================
_ANT_CALLS = []


class _FakeHTTPResp:
    def __init__(self, payload):
        self._p = payload

    def read(self):
        return json.dumps(self._p).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _mk_urlopen(script):
    script = list(script)

    def _fake(req, timeout=None):
        _ANT_CALLS.append({"body": json.loads(req.data.decode("utf-8")), "timeout": timeout,
                           "headers": {k.lower(): v for k, v in req.header_items()}})
        nxt = script.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return _FakeHTTPResp(nxt)
    return _fake


def _payload(content, stop="tool_use", model=None, usage=None, extra=None):
    p = {"id": "msg_1", "model": model or (OPUS + "-20260901"), "stop_reason": stop, "content": content,
         "usage": usage if usage is not None else {"input_tokens": 120, "output_tokens": 80,
                                                   "output_tokens_details": {"thinking_tokens": 50},
                                                   "service_tier": "standard", "cache_creation_input_tokens": 0}}
    p.update(extra or {})
    return p


TOOL_USE = [{"type": "tool_use", "id": "tu_1", "name": ca.VERDICT_TOOL["name"], "input": dict(VERDICT_OK)}]
RAW_USAGE = _payload(TOOL_USE)["usage"]
os.environ["ANTHROPIC_API_KEY"] = "smoke-fake-anthropic-key-not-a-secret"
try:
    urllib.request.urlopen = _mk_urlopen([_payload(TOOL_USE)])
    res = ca._anthropic_tool_call(OPUS, "S", "U")
    check("(B) return_meta=False (default): 2-TUPLA INTACTA (tool_input, usage CRUDO byte a byte con f57a3d3 — incluye "
          "service_tier y output_tokens_details); cuerpo SIN output_config; max_tokens 1200 default; headers x-api-key/anthropic-version",
          isinstance(res, tuple) and len(res) == 2 and res[0] == VERDICT_OK and res[1] == RAW_USAGE
          and "output_config" not in _ANT_CALLS[-1]["body"] and _ANT_CALLS[-1]["body"]["max_tokens"] == 1200
          and _ANT_CALLS[-1]["body"]["tool_choice"] == {"type": "tool", "name": ca.VERDICT_TOOL["name"]}
          and _ANT_CALLS[-1]["headers"]["anthropic-version"] == ca.ANTHROPIC_VERSION, json.dumps(res[1]))
    urllib.request.urlopen = _mk_urlopen([_payload(TOOL_USE)])
    out, usage, meta = ca._anthropic_tool_call(OPUS, "S", "U", max_tokens=4000, effort="low", return_meta=True)
    check("(B/C.4) return_meta=True: 3-tupla; usage NUMÉRICO con thinking_tokens APLANADO (50, ya dentro de output_tokens 80) y sin "
          "service_tier/output_tokens_details; meta {model_reported, api 'anthropic-messages', stop_reason 'tool_use', response_id}; "
          "cuerpo con max_tokens 4000 y output_config {effort low}",
          usage == {"input_tokens": 120, "output_tokens": 80, "cache_creation_input_tokens": 0, "thinking_tokens": 50}
          and meta == {"model_reported": OPUS + "-20260901", "api": "anthropic-messages", "stop_reason": "tool_use",
                       "response_id": "msg_1"}
          and _ANT_CALLS[-1]["body"]["max_tokens"] == 4000 and _ANT_CALLS[-1]["body"]["output_config"] == {"effort": "low"},
          json.dumps([usage, meta]))
    urllib.request.urlopen = _mk_urlopen([_payload(TOOL_USE, usage={"input_tokens": 7, "output_tokens": 3})])
    _, usage_nt, _ = ca._anthropic_tool_call(OPUS, "S", "U", return_meta=True)
    check("(C.4) sin output_tokens_details → thinking_tokens AUSENTE (jamás 0 inventado)",
          usage_nt == {"input_tokens": 7, "output_tokens": 3})
    n0 = len(_ANT_CALLS)
    urllib.request.urlopen = _mk_urlopen([_payload([], stop="refusal", extra={"stop_details": {"category": "harmful"}},
                                                   usage={"input_tokens": 10, "output_tokens": 0})])
    e = _raises(lambda: ca._anthropic_tool_call(OPUS, "S", "U"))
    check("(C.2) stop_reason 'refusal' (HTTP 200, clasificador de Opus 5) → kind 'refusal' SIN reintento (1 llamada); mensaje "
          "'no valid forced tool_use (stop_reason=refusal)' byte-igual; la excepción trae meta.stop_details y usage medidos",
          isinstance(e, ca.CallerError) and e.kind == "refusal" and len(_ANT_CALLS) - n0 == 1
          and str(e) == "no valid forced tool_use (stop_reason=refusal)"
          and e.meta["stop_details"] == {"category": "harmful"} and e.usage == {"input_tokens": 10, "output_tokens": 0}
          and ca._error_string(e) == "RuntimeError: no valid forced tool_use (stop_reason=refusal)")
    n0 = len(_ANT_CALLS)
    urllib.request.urlopen = _mk_urlopen([_payload([], stop="max_tokens")] * 2)
    e = _raises(lambda: ca._anthropic_tool_call(OPUS, "S", "U"))
    check("(C.2) stop_reason 'max_tokens' sin tool_use → 'incomplete:max_output_tokens' (mismo literal que Responses), UN "
          "reintento de contenido (2 llamadas)",
          isinstance(e, ca.CallerError) and e.kind == "incomplete:max_output_tokens" and len(_ANT_CALLS) - n0 == 2)
    n0 = len(_ANT_CALLS)
    urllib.request.urlopen = _mk_urlopen([_payload([{"type": "text", "text": "hola"}], stop="end_turn")] * 2)
    e = _raises(lambda: ca._anthropic_tool_call(OPUS, "S", "U"))
    check("(C.2) end_turn sin tool_use → 'no-function-call' tras reintento (2 llamadas)",
          isinstance(e, ca.CallerError) and e.kind == "no-function-call" and len(_ANT_CALLS) - n0 == 2)
    urllib.request.urlopen = _mk_urlopen([_payload([{**TOOL_USE[0], "input": {**VERDICT_OK, "verdict": "MAYBE"}}])] * 2)
    e = _raises(lambda: ca._anthropic_tool_call(OPUS, "S", "U"))
    check("(C.2) veredicto fuera del vocabulario → 'verdict-off-vocabulary' (mensaje de f57a3d3 conservado)",
          isinstance(e, ca.CallerError) and e.kind == "verdict-off-vocabulary" and str(e).startswith("no valid forced tool_use"))
    n0 = len(_ANT_CALLS)
    urllib.request.urlopen = _mk_urlopen([urllib.error.HTTPError(ca.ANTHROPIC_URL, 400, "Bad Request", {},
                                                                 io.BytesIO(b'{"error":{"type":"invalid_request_error"}}'))])
    e = _raises(lambda: ca._anthropic_tool_call(OPUS, "S", "U"))
    check("(C.2) HTTP 400 → kind 'http-400' SIN reintento (1 llamada); mensaje 'HTTP 400: …' byte-igual a f57a3d3",
          isinstance(e, ca.CallerError) and e.kind == "http-400" and len(_ANT_CALLS) - n0 == 1
          and str(e).startswith('HTTP 400: {"error"') and ca._error_string(e).startswith("RuntimeError: HTTP 400: "))
    n0 = len(_ANT_CALLS)
    urllib.request.urlopen = _mk_urlopen([urllib.error.HTTPError(ca.ANTHROPIC_URL, 529, "Overloaded", {}, io.BytesIO(b"overloaded"))] * 2)
    e = _raises(lambda: ca._anthropic_tool_call(OPUS, "S", "U"))
    check("(C.2) HTTP 529 → UN reintento de transporte (2 llamadas) y kind 'http-529'",
          isinstance(e, ca.CallerError) and e.kind == "http-529" and len(_ANT_CALLS) - n0 == 2)
    n0 = len(_ANT_CALLS)
    urllib.request.urlopen = _mk_urlopen([urllib.error.URLError("connection refused")] * 2)
    e = _raises(lambda: ca._anthropic_tool_call(OPUS, "S", "U"))
    check("(C.2) URLError → 'network' con UN reintento (2 llamadas); mensaje 'network error: …' byte-igual",
          isinstance(e, ca.CallerError) and e.kind == "network" and len(_ANT_CALLS) - n0 == 2
          and str(e).startswith("network error: "))
    n0 = len(_ANT_CALLS)
    urllib.request.urlopen = _mk_urlopen([_payload([{**TOOL_USE[0], "input": {**VERDICT_OK, "confidence": None}}]),
                                          _payload(TOOL_USE)])
    out, usage = ca._anthropic_tool_call(OPUS, "S", "U")
    check("(C.2) required ausente → UN reintento (required-missing:confidence) y el 2º completo se devuelve (2 llamadas)",
          out == VERDICT_OK and len(_ANT_CALLS) - n0 == 2)
    os.environ["ANTHROPIC_API_KEY"] = ""
    n0 = len(_ANT_CALLS)
    e = _raises(lambda: ca._anthropic_tool_call(OPUS, "S", "U"))
    check("(C.2) sin ANTHROPIC_API_KEY → 'no-api-key' con CERO llamadas; mensaje de f57a3d3 byte-igual",
          isinstance(e, ca.CallerError) and e.kind == "no-api-key" and len(_ANT_CALLS) == n0
          and str(e) == "ANTHROPIC_API_KEY not set — add to .secrets/deploy.env / service env (never git).")
finally:
    os.environ["ANTHROPIC_API_KEY"] = ""
    urllib.request.urlopen = _blocked_urlopen

# =====================================================================================================================
# 11. Vocabulario (C.2): tuplas exactas, predicado, clasificador duck-typed, CallerError
# =====================================================================================================================
check("(C.2) FAILURE_KINDS_EXACT / FAILURE_KIND_PREFIXES == los del ADR-0081 (vocabulario CERRADO)",
      ca.FAILURE_KINDS_EXACT == ("no-api-key", "sdk-unavailable", "network", "refusal", "no-function-call",
                                 "arguments-unparseable", "verdict-off-vocabulary", "unknown-family",
                                 "incomplete:max_output_tokens", "incomplete:content_filter", "unclassified")
      and ca.FAILURE_KIND_PREFIXES == ("http-", "response-failed:", "required-missing:"))
check("(C.2) failure_kind_in_vocabulary: todos los exactos True; 'http-404', 'required-missing:confidence', "
      "'response-failed:server_error' True; 'bogus', 'http-' (prefijo pelón), '', None False",
      all(ca.failure_kind_in_vocabulary(k) for k in ca.FAILURE_KINDS_EXACT)
      and ca.failure_kind_in_vocabulary("http-404") and ca.failure_kind_in_vocabulary("required-missing:confidence")
      and ca.failure_kind_in_vocabulary("response-failed:server_error")
      and not ca.failure_kind_in_vocabulary("bogus") and not ca.failure_kind_in_vocabulary("http-")
      and not ca.failure_kind_in_vocabulary("") and not ca.failure_kind_in_vocabulary(None))
check("(C.2) failure_kind_of por duck-typing: status_code 503 → 'http-503'; APIConnectionError → 'network'; TimeoutError → "
      "'network'; urllib HTTPError 429 → 'http-429'; ValueError → 'unclassified'; CallerError('refusal') → 'refusal'",
      ca.failure_kind_of(FakeAPIStatusError(503, "x")) == "http-503"
      and ca.failure_kind_of(APIConnectionError("x")) == "network" and ca.failure_kind_of(TimeoutError("x")) == "network"
      and ca.failure_kind_of(urllib.error.HTTPError("u", 429, "m", {}, io.BytesIO(b""))) == "http-429"
      and ca.failure_kind_of(ValueError("x")) == "unclassified" and ca.failure_kind_of(ca.CallerError("refusal", "m")) == "refusal")
ce = ca.CallerError("no-function-call", "msg")
check("(C.2) CallerError: RuntimeError con .kind, legacy_type_name 'RuntimeError' → _error_string 'RuntimeError: msg'; usage/meta None "
      "por default; _wrap conserva el nombre de la clase del SDK y encadena __cause__",
      isinstance(ce, RuntimeError) and ce.kind == "no-function-call" and ce.legacy_type_name == "RuntimeError"
      and ca._error_string(ce) == "RuntimeError: msg" and ce.usage is None and ce.meta is None
      and ca._wrap(RateLimitError(429, "rl")).legacy_type_name == "RateLimitError"
      and isinstance(ca._wrap(RateLimitError(429, "rl")).__cause__, RateLimitError)
      and ca._wrap(RateLimitError(429, "rl")).kind == "http-429")
check("(D/E) ENV_TABLE de models.py declara como lector a composite_auditor las envs que ESTE módulo lee (S2 no duplica defaults)",
      models.ENV_TABLE["WITT_OPENAI_STORE"]["reader"].startswith("composite_auditor")
      and models.ENV_TABLE["WITT_OPENAI_MAX_OUTPUT_TOKENS"]["reader"].startswith("composite_auditor")
      and models.ENV_TABLE["WITT_OPENAI_REASONING_EFFORT"]["reader"].startswith("composite_auditor")
      and models.ENV_TABLE["WITT_OPENAI_TIMEOUT_S"]["reader"].startswith("composite_auditor")
      and models.ENV_TABLE["WITT_PANEL_MIN_FAMILIES"]["reader"] == "composite_auditor.audit"
      and models.ENV_TABLE["WITT_PANEL_MIN_LENSES"]["reader"] == "composite_auditor.audit")

# =====================================================================================================================
# 12. Cierre: cero red, sin openai cargado
# =====================================================================================================================
check("(M.3) urllib.request.urlopen REAL bloqueado y contado: 0 llamadas en todo el gate", _NET_CALLS == [], str(_NET_CALLS[:3]))
check("(M.3) sys.modules sin 'openai' al terminar", _no_openai_loaded())

npass = sum(CHECKS)
print("\n== %d/%d PASS ==" % (npass, len(CHECKS)))
sys.exit(0 if npass == len(CHECKS) else 1)

"""
smoke_live_models.py — ADR-0081 (M.5): el gate EN VIVO de modelos. Lo corre Emmanuel; GASTA lo que dice; jamás toca la BD.

Ningún smoke del CI gasta modelo ni red (ADR-0081 (M.3)): todo lo que aquí llama a una API la llama con la llave del
entorno del proceso de Emmanuel. Este script es el instrumento de los gates LG1–LG3 (y de cualquier re-medición en
`docs/decisions/0081-*.md` § Gates EN VIVO):

  LG1  --roles synthesizer,elicitation,planner,question_agent,judge-anthropic
       Los cuatro roles del pipeline + un juez Anthropic con los SCHEMAS REALES forzados (runs.SYNTH_TOOL / CONF_TOOL /
       PLAN_TOOL, question_agent.QUESTION_TOOL, composite_auditor.VERDICT_TOOL) y los TOPES de la generación efectiva:
       ¿devuelve `tool_use` con todos los `required`? ¿`stop_reason 'tool_use'` y no `max_tokens`? ¿cuántos tokens de
       salida (con `thinking_tokens` dentro) y qué latencia?
  LG2  --model <puente de la tabla, status 'bridge'> --api responses     → transporte Responses con el modelo barato
  LG3  --model <candidato de la tabla, status 'candidate'> --api responses → el juez OpenAI decidido; reasoning_tokens

Doctrina (CLAUDE.md §7 del repo + ADR-0043/0081): nada se afirma sin medirse — cada fila lleva `model_requested` (resuelto
por la tabla/env) y `model_reported` (lo que la API dijo) con su `relation`; `kind` es 'ok' o un `error_kind` del
vocabulario cerrado de composite_auditor; ausente ≠ null ≠ valor (un `thinking_tokens` que la API no mandó queda ausente,
jamás 0). Los callers son los REALES (S2): `composite_auditor._responses_kwargs`, `_openai_responses_call`,
`_openai_chat_call`, `_anthropic_tool_call(return_meta=True)` — este script NO los replica; si faltan, lo dice y sale con 2.

  --dry-run   construye los kwargs/cuerpos EXACTOS que irían a la red (Responses: la función pura `_responses_kwargs` Y los
              kwargs que el caller real entrega a `client.responses.create` — se comparan; Anthropic: el cuerpo real que
              `_anthropic_tool_call` arma, capturado con `urllib.request.urlopen` BLOQUEADO y contado) y los imprime SIN
              red, SIN llave y SIN escribir archivo (salvo --out). Es el único modo que corre el integrador (S7).

Salida en vivo: una línea por llamada (fila · kind · usage · meta · latencia) y `analysis/outputs/live_models_<fecha>.json`
(append por invocación) pasado por un cinturón anti-secreto: nunca se serializan headers, env ni llaves — sólo su PRESENCIA.
Sin llave para la familia pedida rehúsa con `no-api-key` (exit 2), antes de tocar red. No importa `db` ni abre conexión
alguna: `runs`/`question_agent` se importan sólo por sus schemas y prompts (db crea su engine perezosamente y aquí nadie lo
invoca).

Uso (venv de los gates: dev/.venvs/witt-query-service):
  python analysis/scripts/smoke_live_models.py --roles all --dry-run
  python analysis/scripts/smoke_live_models.py --roles synthesizer,elicitation --effort low --baseline-median-out 900
  python analysis/scripts/smoke_live_models.py --model <id> --api responses [--max-output-tokens 8000] [--effort medium]
"""
import argparse
import contextlib
import datetime as _dt
import inspect
import json
import os
import re
import sys
import time
import types
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
sys.path.insert(0, str(ROOT / "rag_index" / "query_service"))

# Windows: la consola/pipe de Emmanuel puede ser cp1252 y este script imprime UTF-8 (avisos de la tabla, glosas).
# Reemplazar en vez de tumbar la corrida: un gate en vivo que gastó no debe morir al imprimir su resultado.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # pragma: no cover
            pass

from lib import models  # noqa: E402  — S1: la única tabla de modelos (stdlib puro)

OUT_DIR = ROOT / "analysis" / "outputs"
ROLE_ITEMS = ("synthesizer", "elicitation", "planner", "question_agent", "judge-anthropic")
API_FLAG = {"responses": "openai-responses", "chat-completions": "openai-chat-completions"}
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
EXIT_OK, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2

# Lo que S2 debe exponer para que este script mida con los callers REALES (ADR-0081 (B)/(C.1)); sin replicar nada.
S2_OPENAI_SURFACE = ("_responses_kwargs", "_openai_client", "_openai_responses_call", "_openai_chat_call", "CallerError")


# ---------------------------------------------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------------------------------------------
def _accepts(fn, name):
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    return name in params or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())


def _filter_kwargs(fn, kwargs):
    """Pasa sólo los kwargs que la firma REAL acepta; devuelve (kwargs, descartados) para declararlos."""
    kept, dropped = {}, []
    for k, v in kwargs.items():
        (kept.__setitem__(k, v) if _accepts(fn, k) else dropped.append(k))
    return kept, dropped


def _numeric(usage):
    return {k: v for k, v in (usage or {}).items() if isinstance(v, (int, float)) and not isinstance(v, bool)}


def _err(e):
    return f"{getattr(e, 'legacy_type_name', type(e).__name__)}: {str(e)[:200]}"


def _kind(e):
    return getattr(e, "kind", None) or "unclassified"


_SECRET_VALUE_RE = re.compile(r"(?i)(sk-[A-Za-z0-9_\-]{8,}|bearer\s+[A-Za-z0-9._\-]{8,}|api[_-]?key\s*[:=]\s*\S+)")
_SECRET_KEY_RE = re.compile(r"(?i)(api[_-]?key|authorization|x-api-key|secret|password|token$)")


def _redact(obj):
    """Cinturón: ningún valor que parezca llave sale al archivo; llaves de dict con nombre de credencial se eliminan
    (declarado en `_redacted_keys`). Los nombres `*_tokens` de usage NO son secretos (la regex exige 'token' al final
    de la llave, y las llaves de usage terminan en 'tokens')."""
    if isinstance(obj, dict):
        out, dropped = {}, []
        for k, v in obj.items():
            if isinstance(k, str) and _SECRET_KEY_RE.search(k) and k != "key_present":
                dropped.append(k)
                continue
            out[k] = _redact(v)
        if dropped:
            out["_redacted_keys"] = dropped
        return out
    if isinstance(obj, (list, tuple)):
        return [_redact(x) for x in obj]
    if isinstance(obj, str) and _SECRET_VALUE_RE.search(obj):
        return "<redactado: parece llave>"
    return obj


def _today():
    return _dt.datetime.now(_dt.timezone.utc)


# ---------------------------------------------------------------------------------------------------------------
# Imports perezosos con mensaje claro (S2 provee los callers; runs/question_agent proveen schemas y prompts)
# ---------------------------------------------------------------------------------------------------------------
def _load_auditor(need_openai, need_anthropic):
    from lib import composite_auditor as ca
    missing = []
    if need_openai:
        missing += [n for n in S2_OPENAI_SURFACE if not hasattr(ca, n)]
    if need_anthropic and not _accepts(ca._anthropic_tool_call, "return_meta"):
        missing.append("_anthropic_tool_call(return_meta=True)")
    return ca, missing


def _load_runs():
    try:
        import runs as runs_mod  # noqa: E402  — sólo SYNTH_TOOL / CONF_TOOL / PLAN_TOOL / ELICIT_SYSTEM / synth_system
        return runs_mod, None
    except Exception as e:  # pragma: no cover — se declara, no se disimula
        return None, f"runs no importable ({_err(e)}); el schema REAL del sintetizador/elicitación/planner no está disponible"


def _load_question_agent():
    try:
        import question_agent as qa  # noqa: E402  — sólo QUESTION_TOOL / spec_digest
        return qa, None
    except Exception as e:  # pragma: no cover
        return None, f"question_agent no importable ({_err(e)})"


# ---------------------------------------------------------------------------------------------------------------
# Prompts REALES (o réplica DECLARADA cuando el módulo dueño no los factoriza)
# ---------------------------------------------------------------------------------------------------------------
def _judge_system(ca, lens):
    """El system del juez tal como lo arma composite_auditor.audit(). Si S2 lo factorizó (`_judge_system(member)` o
    `judge_system(lens)`), se usa ESE; si no, la réplica literal del f-string de audit() @ f57a3d3, declarada."""
    for name in ("_judge_system", "judge_system"):
        fn = getattr(ca, name, None)
        if callable(fn):
            try:
                return fn({"lens": lens}) if _accepts(fn, "member") else fn(lens), f"composite_auditor.{name}"
            except Exception:
                pass
    system = (f"You are one reviewer on an adversarial composite-audit panel (zebrafish pronephros "
              f"research substrate). Your assigned lens: {lens}. {ca._LENS_CHARGES[lens]} "
              f"HONEST-DECLINE DOCTRINE (ADR-0058): when the claim declines to answer WITH its "
              f"absence_kind declared, judge whether DECLINING is the correct move given the evidence "
              f"shown (external literature included, if fetched) — do NOT punish the decline for the "
              f"absence itself: a correctly identified absence is a first-class negative finding of "
              f"this system (it triggers the re-ingest loop). Correct decline -> APPROVE_DECLINE; "
              f"decline despite sufficient evidence (lazy) -> REVISE. "
              f"You are handed deterministic verification results in the input — cite them; NEVER claim "
              f"a verification you did not run. Vote independently; other reviewers cover other lenses."
              f"\n\n{ca._niche_table()}")
    return system, "replica-of composite_auditor.audit() inline f-string @ f57a3d3 (declared)"


def _planner_system(runs_mod):
    fn = getattr(runs_mod, "plan_system", None) or getattr(runs_mod, "planner_system", None)
    if callable(fn):
        return fn(), "runs.plan_system"
    from lib import agent_matrix
    return ("You are the §11 agent-invocation preflight of the Witt × Organogenesis webapp: classify "
            "the incoming question BEFORE the pipeline runs. Judge strictly against the matrix and "
            "niches below; do NOT answer the question itself.\n\n" + agent_matrix.digest()), \
        "replica-of runs._default_planner inline string @ f57a3d3 (declared)"


def _question_system(qa):
    for name in ("question_system", "drafter_system"):
        fn = getattr(qa, name, None)
        if callable(fn):
            return fn(), f"question_agent.{name}"
    return ("You are the question-drafting agent of the Witt × Organogenesis webapp. You convert a "
            "researcher's free-form note into ONE question the pipeline can answer. You do NOT answer "
            "it, and you do NOT invent biology.\n\n" + qa.spec_digest()), \
        "replica-of question_agent._default_drafter inline string @ f57a3d3 (declared)"


# ---------------------------------------------------------------------------------------------------------------
# Fixture: sintético y DECLARADO — sin identificadores externos (§7: ninguno sale de memoria), sin afirmación biológica.
# Lo que se mide es el TRANSPORTE con los schemas reales (tool_use, required, stop_reason, tokens, latencia).
# ---------------------------------------------------------------------------------------------------------------
def default_fixture():
    return {
        "question": ("Smoke fixture (ADR-0081 LG1): from the evidence shown, which statements about zebrafish "
                     "pronephros development are supported? Answer ONLY from the evidence shown."),
        "entities": [],
        "evidence": [{"id": "smoke-fixture-1", "kind": "smoke-fixture",
                      "text": ("SYNTHETIC SMOKE PASSAGE — not evidence. This item exists only to exercise the forced "
                               "tool call end to end; it makes no biological claim and names no identifier.")}],
        "direct_answer": ("The evidence shown is a synthetic smoke fixture that makes no biological claim; no statement "
                          "about pronephros development can be supported from it."),
        "gap_flags": ["smoke-fixture: no evidence"],
        "absence_kind": "no-evidence-retrieved",
        "note": {"title": "Smoke fixture (ADR-0081 LG1)",
                 "body": ("Which early events of zebrafish pronephros development does the evidence shown support? "
                          "(synthetic smoke note; no identifiers, no claims)"),
                 "entities": [], "niches": []},
    }


def _claim_payload(fx):
    return json.dumps({"claim": {"direct_answer": fx["direct_answer"], "confidence": 0.1,
                                 "absence_kind": fx["absence_kind"], "gap_flags": fx["gap_flags"],
                                 "evidence_cited": []},
                       "evidence": fx["evidence"],
                       "deterministic_checks": {"note": "none provided (smoke fixture)"}},
                      ensure_ascii=False, indent=2, default=str)


# ---------------------------------------------------------------------------------------------------------------
# Construcción de ítems (qué llamada, con qué schema, con qué modelo y tope)
# ---------------------------------------------------------------------------------------------------------------
def build_role_items(role_names, fx, ca, runs_mod, qa):
    items, problems = [], []
    for name in role_names:
        if name == "judge-anthropic":
            rr = models.resolve_role("judge.correctness")
            system, src = _judge_system(ca, "correctness")
            items.append({"item": name, "role": "judge.correctness", "lens": "correctness", "resolved": rr,
                          "tool": ca.VERDICT_TOOL, "system": system, "system_source": src,
                          "user_text": _claim_payload(fx)})
            continue
        rr = models.resolve_role(name)
        if name in ("synthesizer", "elicitation", "planner"):
            if runs_mod is None:
                problems.append(f"{name}: runs no importable — sin schema real")
                continue
            if name == "synthesizer":
                tool, system, src = runs_mod.SYNTH_TOOL, runs_mod.synth_system("pass1"), "runs.synth_system('pass1')"
                user_text = json.dumps({"question": fx["question"], "evidence": fx["evidence"]},
                                       ensure_ascii=False, default=str)
            elif name == "elicitation":
                tool, system, src = runs_mod.CONF_TOOL, runs_mod.ELICIT_SYSTEM, "runs.ELICIT_SYSTEM"
                user_text = json.dumps({"question": fx["question"], "evidence": fx["evidence"],
                                        "produced_answer": {"pass": "pass1", "direct_answer": fx["direct_answer"],
                                                            "gap_flags": fx["gap_flags"]}},
                                       ensure_ascii=False, default=str)
            else:
                tool = runs_mod.PLAN_TOOL
                system, src = _planner_system(runs_mod)
                user_text = json.dumps({"question": fx["question"], "entities": fx.get("entities") or []},
                                       ensure_ascii=False, default=str)
        else:  # question_agent
            if qa is None:
                problems.append("question_agent: no importable — sin schema real")
                continue
            tool = qa.QUESTION_TOOL
            system, src = _question_system(qa)
            n = fx["note"]
            user_text = json.dumps({"title": n.get("title", ""), "body": n.get("body", ""),
                                    "entities_cited": n.get("entities", []), "niches_cited": n.get("niches", [])},
                                   ensure_ascii=False)
        items.append({"item": name, "role": name, "lens": None, "resolved": rr, "tool": tool, "system": system,
                      "system_source": src, "user_text": user_text})
    return items, problems


def build_model_item(model, lens, api_flag, fx, ca):
    member = models.member_for(model, lens)
    api = API_FLAG[api_flag] if api_flag else member["api"]
    api_source = f"cli:--api {api_flag}" if api_flag else member["api_source"]
    if member["family"] == models.FAMILY_UNKNOWN:
        return None, (f"unknown-family: {model!r} no casa con ningún prefijo de la tabla (claude-* / gpt-* / o[0-9]* / "
                      f"text-embedding-*) — el caller erraría en voz alta; no se llama")
    if api_flag and member["family"] != "openai":
        return None, f"--api sólo aplica a la familia openai; {model!r} es {member['family']}"
    system, src = _judge_system(ca, lens)
    resolved = {"model": model, "source": "cli:--model", "family": member["family"], "family_source": member["family_source"],
                "api": api, "api_source": api_source, "known": member["known"], "priced": member["priced"],
                "max_tokens": member["max_tokens"], "generation": None, "generation_source": "n/a (modelo arbitrario)"}
    return {"item": f"model:{model}", "role": None, "lens": lens, "resolved": resolved, "tool": ca.VERDICT_TOOL,
            "system": system, "system_source": src, "user_text": _claim_payload(fx)}, None


# ---------------------------------------------------------------------------------------------------------------
# Dry-run: red BLOQUEADA y contada; cliente OpenAI falso que captura kwargs
# ---------------------------------------------------------------------------------------------------------------
class _DryRunBlocked(Exception):
    """Sin status_code ni herencia de red: el caller la clasifica 'unclassified' y NO reintenta (ADR-0081 C.2)."""


class _FakeCreate:
    def __init__(self, sink, path):
        self._sink, self._path = sink, path

    def create(self, **kw):
        self._sink.append({"path": self._path, "kwargs": kw})
        raise _DryRunBlocked(f"dry-run: {self._path} BLOQUEADO (sin red)")


class _FakeOpenAIClient:
    def __init__(self, sink):
        self.responses = _FakeCreate(sink, "responses.create")
        self.chat = types.SimpleNamespace(completions=_FakeCreate(sink, "chat.completions.create"))
        self.max_retries = 0


@contextlib.contextmanager
def _blocked_urlopen(sink):
    real = urllib.request.urlopen

    def blocked(req, *a, **kw):
        data = getattr(req, "data", None)
        try:
            body = json.loads(data.decode("utf-8")) if data else None
        except Exception:
            body = {"_raw_len": len(data or b"")}
        sink.append({"url": getattr(req, "full_url", str(req)), "body": body})
        raise urllib.error.URLError("dry-run: red BLOQUEADA (ADR-0081 M.3)")

    urllib.request.urlopen = blocked
    try:
        yield
    finally:
        urllib.request.urlopen = real


@contextlib.contextmanager
def _placeholder_key(var):
    """Sólo en --dry-run: el caller exige la env antes de armar el cuerpo; se pone un placeholder que NO es llave, sólo
    en este proceso, y se restaura tal cual (la máscara vacía de los gates vuelve a quedar vacía)."""
    prev = os.environ.get(var)
    os.environ[var] = prev or "dry-run-placeholder-not-a-credential"
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = prev


@contextlib.contextmanager
def _patched_attr(obj, name, value):
    had, prev = hasattr(obj, name), getattr(obj, name, None)
    setattr(obj, name, value)
    try:
        yield
    finally:
        if had:
            setattr(obj, name, prev)
        else:
            delattr(obj, name)


# ---------------------------------------------------------------------------------------------------------------
# Ejecución de un ítem
# ---------------------------------------------------------------------------------------------------------------
def _effort_for(family, effort):
    """Valida --effort contra el vocabulario de la familia (ADR-0081 (C.1)/(C.4))."""
    if not effort:
        return None, None
    vocab = models.ANTHROPIC_EFFORTS if family == "anthropic" else models.REASONING_EFFORTS
    if effort not in vocab:
        return None, f"--effort {effort!r} fuera del vocabulario de {family}: {vocab}"
    return effort, None


def run_item(it, args, ca, dry_run):
    rr = it["resolved"]
    family, api, model = rr["family"], rr["api"], rr["model"]
    tool = it["tool"]
    row = {"item": it["item"], "role": it["role"], "lens": it["lens"], "family": family, "family_source": rr["family_source"],
           "api": api, "api_source": rr["api_source"], "model_requested": model, "model_source": rr["source"],
           "known": rr["known"], "priced": rr["priced"], "generation": rr["generation"],
           "generation_source": rr["generation_source"], "tool": tool["name"], "required": list(tool["input_schema"].get("required", [])),
           "system_source": it["system_source"], "dry_run": dry_run, "kind": None, "error": None}
    effort, bad = _effort_for(family, args.effort)
    if bad:
        row.update(kind="bad-args", error=bad)
        return row
    row["effort_requested"] = args.effort or None
    t0 = time.perf_counter()
    net = []
    try:
        if api == "anthropic-messages":
            max_tokens = args.max_output_tokens or rr["max_tokens"]
            row["max_tokens_sent"] = max_tokens
            row["max_tokens_source"] = "cli:--max-output-tokens" if args.max_output_tokens else f"table:{rr['generation']} tope"
            kw = {"tool": tool, "timeout": args.timeout or 120, "retries": 0, "max_tokens": max_tokens, "return_meta": True}
            if effort:
                if _accepts(ca._anthropic_tool_call, "effort"):
                    kw["effort"] = effort
                    row["effort_applied_via"] = "kwarg effort= de _anthropic_tool_call"
                else:
                    os.environ["WITT_ANTHROPIC_EFFORT"] = effort
                    row["effort_applied_via"] = "process-env WITT_ANTHROPIC_EFFORT (sólo este proceso)"
            kw, dropped = _filter_kwargs(ca._anthropic_tool_call, kw)
            row["kwargs_dropped_by_signature"] = dropped
            if dry_run:
                with _placeholder_key(KEY_ENV["anthropic"]), _blocked_urlopen(net):
                    try:
                        ca._anthropic_tool_call(model, it["system"], it["user_text"], **kw)
                    except Exception as e:
                        row["caller_reaction"] = {"kind": _kind(e), "error": _err(e)}
                body = net[0]["body"] if net else None
                row.update(kind="dry-run", urlopen_attempts=len(net), network_calls_real=0,
                           url=(net[0]["url"] if net else None), body=body)
                if isinstance(body, dict):
                    row["body_summary"] = {"model": body.get("model"), "max_tokens": body.get("max_tokens"),
                                           "tool": (body.get("tools") or [{}])[0].get("name"),
                                           "tool_choice": body.get("tool_choice"),
                                           "output_config": body.get("output_config", "<ausente>"),
                                           "thinking": body.get("thinking", "<ausente>"),
                                           "system_chars": len(body.get("system") or ""),
                                           "user_chars": sum(len(m.get("content") or "") for m in body.get("messages", []))}
                return row
            tool_input, usage, meta = ca._anthropic_tool_call(model, it["system"], it["user_text"], **kw)
        else:
            store, store_src = models.env_value("WITT_OPENAI_STORE")
            mot, mot_src = models.env_value("WITT_OPENAI_MAX_OUTPUT_TOKENS")
            max_out = args.max_output_tokens or mot
            row["max_output_tokens_sent"] = max_out
            row["max_output_tokens_source"] = "cli:--max-output-tokens" if args.max_output_tokens else mot_src
            row["store"] = {"value": store, "source": store_src}
            table_row = models.MODELS.get(model)
            reasoning_ok = bool(table_row and table_row.get("reasoning"))
            row["effort_sent"] = effort if (effort and reasoning_ok and api == "openai-responses") else None
            if effort and not row["effort_sent"]:
                row["effort_not_sent_reason"] = ("la tabla no marca reasoning True para este modelo (o es desconocido)"
                                                 if api == "openai-responses" else "el camino chat no lleva reasoning.effort")
            timeout = args.timeout or models.env_value("WITT_OPENAI_TIMEOUT_S")[0]
            row["timeout_s"] = timeout
            if effort and api == "openai-responses":
                if _accepts(ca._openai_responses_call, "reasoning_effort"):
                    row["effort_applied_via"] = "kwarg reasoning_effort= de _openai_responses_call (la tabla gatea: effort_sent)"
                else:
                    os.environ["WITT_OPENAI_REASONING_EFFORT"] = effort
                    row["effort_applied_via"] = "process-env WITT_OPENAI_REASONING_EFFORT (sólo este proceso; la tabla gatea)"
            if api == "openai-responses":
                kw_pure, dropped_pure = _filter_kwargs(ca._responses_kwargs, {
                    "model": model, "system": it["system"], "user_text": it["user_text"], "tool": tool,
                    "max_output_tokens": max_out, "store": store, "reasoning_effort": row["effort_sent"]})
                pure = ca._responses_kwargs(**kw_pure)
                row["kwargs_pure"] = pure
                row["kwargs_pure_dropped_by_signature"] = dropped_pure
                row["kwargs_summary"] = {"model": pure.get("model"), "tool_choice": pure.get("tool_choice"),
                                         "strict": (pure.get("tools") or [{}])[0].get("strict", "<ausente>"),
                                         "parallel_tool_calls": pure.get("parallel_tool_calls", "<ausente>"),
                                         "max_output_tokens": pure.get("max_output_tokens"), "store": pure.get("store", "<ausente>"),
                                         "reasoning": pure.get("reasoning", "<ausente>")}
                fn = ca._openai_responses_call
                # los MISMOS valores que la función pura: si el caller los acepta como kwargs viajan explícitos
                kw = {"tool": tool, "timeout": timeout, "retries": 0, "max_output_tokens": max_out,
                      "store": store, "reasoning_effort": row["effort_sent"]}
            else:
                fn = ca._openai_chat_call
                kw = {"tool": tool, "timeout": timeout}
            kw, dropped = _filter_kwargs(fn, kw)
            row["kwargs_dropped_by_signature"] = dropped
            if dry_run:
                sink = []
                fake = _FakeOpenAIClient(sink)
                if _accepts(fn, "client"):
                    kw["client"] = fake
                    row["fake_client_via"] = "kwarg client="
                    cm = contextlib.nullcontext()
                else:
                    row["fake_client_via"] = "monkeypatch composite_auditor._openai_client (factory declarada en (C.1))"
                    cm = _patched_attr(ca, "_openai_client", lambda *a, **k: fake)
                with cm:
                    try:
                        fn(model, it["system"], it["user_text"], **kw)
                    except Exception as e:
                        row["caller_reaction"] = {"kind": _kind(e), "error": _err(e)}
                captured = sink[0] if sink else None
                row.update(kind="dry-run", network_calls_real=0, create_calls=len(sink),
                           kwargs_captured=(captured or {}).get("kwargs"), create_path=(captured or {}).get("path"))
                if api == "openai-responses" and captured is not None:
                    row["kwargs_match_pure"] = captured["kwargs"] == pure
                elif captured is not None:   # camino chat (byte a byte f57a3d3 + max_retries=0): resumen desde lo CAPTURADO
                    ck = captured["kwargs"]
                    fn0 = ((ck.get("tools") or [{}])[0].get("function") or {})
                    row["kwargs_summary"] = {"model": ck.get("model"), "tool_choice": ck.get("tool_choice"),
                                             "tool": fn0.get("name"), "max_tokens": ck.get("max_tokens"),
                                             "timeout": ck.get("timeout"), "strict": "<n/a chat>",
                                             "parallel_tool_calls": ck.get("parallel_tool_calls", "<ausente>"),
                                             "max_output_tokens": "<n/a chat: max_tokens>", "store": "<n/a chat>",
                                             "reasoning": "<n/a chat>"}
                return row
            tool_input, usage, meta = fn(model, it["system"], it["user_text"], **kw)
        # --- éxito en vivo ---------------------------------------------------------------------------------------
        row["latency_s"] = round(time.perf_counter() - t0, 3)
        meta = meta or {}
        usage = _numeric(usage)
        reported = meta.get("model_reported")
        required = row["required"]
        missing = [k for k in required if not isinstance(tool_input, dict) or tool_input.get(k) is None]
        row.update(kind="ok", model_reported=reported, relation=models.relation(model, reported),
                   thinking_state=models.thinking_state(model), stop_reason=meta.get("stop_reason"),
                   status=meta.get("status"), incomplete_reason=meta.get("incomplete_reason"),
                   stop_details=meta.get("stop_details"), response_id=meta.get("response_id"), api_reported=meta.get("api"),
                   usage=usage, required_missing=missing,
                   recovered_fields=(tool_input or {}).get("_recovered_fields") if isinstance(tool_input, dict) else None,
                   tool_input=tool_input)
        if tool["name"] == ca.VERDICT_TOOL["name"]:
            v = (tool_input or {}).get("verdict") if isinstance(tool_input, dict) else None
            row["verdict"] = v
            row["verdict_in_vocabulary"] = v in ca.VOCABULARY
        # medidas informativas (ya dentro de output_tokens) — ausentes si la API no las mandó, jamás 0 inventado
        for k in ("thinking_tokens", "reasoning_tokens", "cached_tokens"):
            if k in usage:
                row[k] = usage[k]
        if "reasoning_tokens" in usage and "output_tokens" in usage:
            row["output_ge_reasoning"] = usage["output_tokens"] >= usage["reasoning_tokens"]
        if row["stop_reason"] is not None:
            row["stop_reason_is_tool_use"] = row["stop_reason"] == "tool_use"
        if args.baseline_median_out and "output_tokens" in usage:
            row["output_tokens_vs_baseline"] = {"baseline_median_out": args.baseline_median_out,
                                                "ratio": round(usage["output_tokens"] / args.baseline_median_out, 3),
                                                "baseline_class": "atestiguada (M8 by_stage synthesize_pass1, dada por CLI)"}
        elif "output_tokens" in usage:
            row["output_tokens_vs_baseline"] = "not-provided (pasar --baseline-median-out N desde M8)"
        return row
    except Exception as e:
        row.update(kind=_kind(e), error=_err(e), latency_s=round(time.perf_counter() - t0, 3))
        return row


def _print_row(r):
    if r["kind"] == "dry-run":
        if r["api"] == "anthropic-messages":
            s = r.get("body_summary") or {}
            print(f"[{r['item']}] DRY-RUN {r['model_requested']} via {r['api']} (fuente {r['model_source']}) → cuerpo REAL "
                  f"capturado: model={s.get('model')} max_tokens={s.get('max_tokens')} tool={s.get('tool')} "
                  f"tool_choice={s.get('tool_choice')} output_config={s.get('output_config')} thinking={s.get('thinking')} "
                  f"system_chars={s.get('system_chars')} user_chars={s.get('user_chars')} · urlopen intentos={r.get('urlopen_attempts')} "
                  f"reales=0 · caller={r.get('caller_reaction')}")
        else:
            s = r.get("kwargs_summary") or {}
            print(f"[{r['item']}] DRY-RUN {r['model_requested']} via {r['api']} ({r['api_source']}) → {r.get('create_path')} "
                  f"capturado (fake client: {r.get('fake_client_via')}): model={s.get('model')} tool_choice={s.get('tool_choice')} "
                  f"strict={s.get('strict')} parallel={s.get('parallel_tool_calls')} max_output_tokens={s.get('max_output_tokens')} "
                  f"store={s.get('store')} reasoning={s.get('reasoning')} · kwargs_match_pure={r.get('kwargs_match_pure')} · "
                  f"caller={r.get('caller_reaction')}")
        return
    u = r.get("usage") or {}
    print(f"[{r['item']}] {r['model_requested']} via {r['api']} (fuente {r['model_source']}) → kind={r['kind']} "
          f"reported={r.get('model_reported')} relation={r.get('relation')} stop={r.get('stop_reason') or r.get('status')} "
          f"incomplete={r.get('incomplete_reason')} in={u.get('input_tokens')} out={u.get('output_tokens')} "
          f"think={r.get('thinking_tokens', '<ausente>')} reasoning={r.get('reasoning_tokens', '<ausente>')} "
          f"latency={r.get('latency_s')}s required_missing={r.get('required_missing')} verdict={r.get('verdict', '-')}"
          + (f" ERROR {r['error']}" if r.get("error") else ""))


# ---------------------------------------------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roles", default="", help="CSV con valores de {" + ",".join(ROLE_ITEMS) + "} o 'all' (LG1: schemas reales + topes g2)")
    ap.add_argument("--model", default=None, help="id de modelo arbitrario para una llamada de JUEZ (LG2 puente / LG3 candidato; "
                                                 "también un id Anthropic); la familia se toma de la tabla o del prefijo")
    ap.add_argument("--api", choices=sorted(API_FLAG), default=None, help="fuerza el transporte OpenAI del --model")
    ap.add_argument("--lens", choices=models.LENSES, default="reproducibility", help="lente del juez para --model")
    ap.add_argument("--max-output-tokens", type=int, default=None, help="tope: max_output_tokens (Responses) / max_tokens (Anthropic)")
    ap.add_argument("--effort", default=None, help="Anthropic: output_config.effort (low|medium|high|xhigh|max); OpenAI: reasoning.effort (low|medium|high)")
    ap.add_argument("--timeout", type=int, default=None, help="timeout por llamada (s); default 120 / WITT_OPENAI_TIMEOUT_S")
    ap.add_argument("--baseline-median-out", type=int, default=None, help="mediana ATESTIGUADA de output_tokens (M8) para el ratio")
    ap.add_argument("--fixture", default=None, help="JSON que sobreescribe llaves del fixture sintético (question, evidence, note…)")
    ap.add_argument("--dry-run", action="store_true", help="construye e imprime los kwargs/cuerpos SIN red ni llave (lo que corre el CI)")
    ap.add_argument("--out", default=None, help="ruta del JSON de salida (default: analysis/outputs/live_models_<fecha>.json; --dry-run no escribe salvo --out)")
    ap.add_argument("--verbose", action="store_true", help="imprime los kwargs/cuerpos completos en --dry-run y el tool_input en vivo")
    args = ap.parse_args(argv)

    if args.effort:
        args.effort = args.effort.strip().lower()
    role_names = [] if not args.roles else (list(ROLE_ITEMS) if args.roles.strip() == "all"
                                            else [r.strip() for r in args.roles.split(",") if r.strip()])
    bad = [r for r in role_names if r not in ROLE_ITEMS]
    if bad or (not role_names and not args.model):
        print(json.dumps({"kind": "bad-args", "error": f"roles desconocidos {bad}" if bad else "nada que correr: --roles y/o --model",
                          "roles_validos": ROLE_ITEMS}, ensure_ascii=False))
        return EXIT_REFUSED

    fx = default_fixture()
    if args.fixture:
        fx.update(json.loads(Path(args.fixture).read_text(encoding="utf-8")))

    # ¿qué familias vamos a tocar? (decide llaves requeridas y superficie S2 requerida)
    need_anthropic = bool(role_names)
    need_openai = False
    if args.model:
        fam, _ = models.family_of(args.model)
        api_flag_family = "openai" if args.api else fam
        need_openai = need_openai or api_flag_family == "openai"
        need_anthropic = need_anthropic or (fam == "anthropic" and not args.api)

    ca, missing = _load_auditor(need_openai, need_anthropic)
    if missing:
        print(json.dumps({"kind": "s2-pending", "error": "composite_auditor no expone la superficie de ADR-0081 (S2) que este script usa "
                          "con los callers REALES — no se replica nada", "missing": missing,
                          "expected": {"openai": list(S2_OPENAI_SURFACE), "anthropic": "_anthropic_tool_call(..., return_meta=True)"}},
                         ensure_ascii=False, indent=2))
        return EXIT_REFUSED

    runs_mod, runs_err = (None, None)
    qa, qa_err = (None, None)
    if any(r in ("synthesizer", "elicitation", "planner") for r in role_names):
        runs_mod, runs_err = _load_runs()
    if "question_agent" in role_names:
        qa, qa_err = _load_question_agent()

    items, problems = build_role_items(role_names, fx, ca, runs_mod, qa)
    for p in filter(None, (runs_err, qa_err)):
        problems.append(p)
    if args.model:
        it, prob = build_model_item(args.model, args.lens, args.api, fx, ca)
        (items.append(it) if it else problems.append(prob))
    if not items:
        print(json.dumps({"kind": "bad-args", "error": "ningún ítem construible", "problems": problems}, ensure_ascii=False, indent=2))
        return EXIT_REFUSED

    # llaves: sólo PRESENCIA; en vivo se rehúsa ANTES de tocar red
    fams = sorted({it["resolved"]["family"] for it in items})
    key_present = {fam: bool(os.environ.get(KEY_ENV[fam])) for fam in fams if fam in KEY_ENV}
    if not args.dry_run:
        absent = [KEY_ENV[f] for f, ok in key_present.items() if not ok]
        if absent:
            print(json.dumps({"kind": "no-api-key", "error": "sin llave en el entorno del proceso para la(s) familia(s) pedida(s); "
                              "nada se llamó", "missing_env": absent, "families": fams,
                              "hint": "exporta la llave en ESTA shell (jamás en git ni en archivos del repo)"}, ensure_ascii=False, indent=2))
            return EXIT_REFUSED
        print(f"ESTA CORRIDA GASTA: {len(items)} llamada(s) en vivo ({', '.join(fams)}). Sin BD, sin caché, sin git.")

    snap = models.snapshot()
    header = {"invoked_at": _today().strftime("%Y-%m-%dT%H:%M:%SZ"), "argv": sys.argv[1:], "dry_run": args.dry_run,
              "generation": snap["generation"], "generation_source": snap["generation_source"],
              "table_version": snap["table_version"], "table_as_of": snap["table_as_of"],
              "panel_signature": snap["panel_signature"], "warnings": snap["warnings"], "unknown_models": snap["unknown_models"],
              "key_present": key_present, "problems": problems}
    print(f"ADR-0081 · tabla {header['table_version']} @ {header['table_as_of']} · generación {header['generation']} "
          f"({header['generation_source']}) · panel_signature {header['panel_signature']} · warnings={len(snap['warnings'])} · "
          f"unknown_models={len(snap['unknown_models'])}" + (" · DRY-RUN (sin red, sin llave)" if args.dry_run else ""))
    for w in snap["warnings"]:
        print("  aviso:", w)
    for p in problems:
        print("  problema:", p)

    rows = []
    for it in items:
        r = run_item(it, args, ca, args.dry_run)
        rows.append(r)
        _print_row(r)
        if args.verbose:
            print(json.dumps(_redact({k: r.get(k) for k in ("body", "kwargs_pure", "kwargs_captured", "tool_input") if k in r}),
                             ensure_ascii=False, indent=2, default=str))

    n_ok = sum(1 for r in rows if r["kind"] in ("ok", "dry-run"))
    n_failed = len(rows) - n_ok
    summary = {"n": len(rows), "n_ok": n_ok, "n_failed": n_failed,
               "failed_kinds": sorted({r["kind"] for r in rows if r["kind"] not in ("ok", "dry-run")})}
    exit_code = EXIT_OK if n_failed == 0 else EXIT_FAILED
    run = _redact({**header, "items": rows, "summary": summary, "exit_code": exit_code})

    out_path = Path(args.out) if args.out else (OUT_DIR / f"live_models_{_today().strftime('%Y%m%d')}.json")
    if args.out or not args.dry_run:
        doc = {"script": "analysis/scripts/smoke_live_models.py", "adr": "ADR-0081", "runs": []}
        if out_path.exists():
            try:
                doc = json.loads(out_path.read_text(encoding="utf-8"))
                doc.setdefault("runs", [])
            except Exception:
                doc = {"script": "analysis/scripts/smoke_live_models.py", "adr": "ADR-0081", "runs": [],
                       "_previous_unreadable": True}
        doc["runs"].append(run)
        text = json.dumps(doc, ensure_ascii=False, indent=2, default=str)
        assert not _SECRET_VALUE_RE.search(text), "cinturón: el JSON de salida contiene algo que parece llave — no se escribe"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"escrito: {out_path.relative_to(ROOT).as_posix() if out_path.is_relative_to(ROOT) else out_path} "
              f"({len(doc['runs'])} invocación(es); sin secretos: cinturón aplicado)")
    else:
        print("dry-run: nada escrito (usa --out para guardar los kwargs)")
    print(f"resumen: {summary}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

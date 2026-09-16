"""
smoke_live_council.py — ADR-0082 (L.6): el gate EN VIVO del consejo de criterio. Lo corre Emmanuel; GASTA lo que dice;
jamás toca la BD.

Ningún smoke del CI gasta modelo ni red (ADR-0082 (L.3)): todo lo que aquí llama a la API la llama con la llave del
entorno del proceso de Emmanuel. Este script es el instrumento de los gates LG1–LG2 del ADR (y de cualquier re-medición en
`docs/decisions/0082-consejo-de-criterio-ejecutable.md` § Gates EN VIVO):

  LG1  --count-tokens
       `POST /v1/messages/count_tokens` (USD 0) sobre los cuerpos REALES: tokens de [tools ×3 + bloque A (fijo + §7)] —
       el PREFIJO COMPARTIDO que la caché escribe una vez y lee N−1 (debe ser ≥ 512 = MIN_CACHEABLE_TOKENS o la API
       devuelve `cache_creation_input_tokens 0` en silencio) — y de cada una de las 17 fichas VERBATIM (sustituye la
       proyección "≈ 0.3k tok de media" por MEDICIÓN). ≈ 20 llamadas, ninguna cobra.
  LG1  --member <agent> --round r1|r2 [--repeat 2]
       UNA llamada real de un miembro con `council.build_request` (los TRES tools byte a byte, `tool_choice` forzado,
       `system` en dos bloques con `cache_control`, `output_config.effort` pinneado) y `composite_auditor.
       _anthropic_tool_call(return_meta=True, tools=…)` a través de `council.default_caller`: ¿`stop_reason 'tool_use'`
       con todos los `required` bajo `max_tokens 4000`? ¿`cache_creation_input_tokens > 0` en la 1ª y
       `cache_read_input_tokens ≈ prefijo` en la 2ª (--repeat 2)? ¿`thinking_tokens`, `output_tokens`, latencia? La salida
       pasa por `council.validate_tool_input` (lo que el consejo REALMENTE conservaría).
  LG2  --full-r1 --question "<pregunta>" [--entities a,b] [--full]
       Una RONDA 1 completa por `council.run_round` (17 llamadas; 25 con --full) + `council.aggregate_r1` — el mismo
       código que corre el worker del plan (council_jobs.execute_round1), SIN plan ni BD: mide cuórum, escalonado
       (`stagger_wait_s`), caché por miembro, `n_unsatisfiable`, `aggregation_sha`. Los eventos `stage.council.*` se
       imprimen conforme llegan (latido visible).

Doctrina (CLAUDE.md §7 del repo + ADR-0043/0082): el consejo NUNCA escribe respuesta, veredicto, ranking ni despacha —
este script tampoco: sólo pide requisitos/juicios por sus tools y los valida por CÓDIGO. Nada se afirma sin medirse —
cada fila lleva `model_requested` (tabla/env, `models.resolve_role('council')`) y `model_reported` (lo que la API dijo)
con su `relation`; `kind` es 'ok' o un `error_kind` del vocabulario cerrado de composite_auditor; ausente ≠ null ≠ valor
(un `thinking_tokens` que la API no mandó queda ausente, jamás 0; un `cache_read_input_tokens 0` es MEDICIÓN de que no
leyó). Los callers son los REALES (C2/D.1): `council.build_request`, `council.default_caller`, `council.run_round`,
`composite_auditor._anthropic_tool_call(return_meta=True, tools=)` — este script NO los replica; si faltan, lo dice y
sale con 2. El fixture es SINTÉTICO y DECLARADO: sin identificadores externos, sin afirmación biológica.

  --dry-run   construye la PETICIÓN real de un miembro (`build_request`) y el cuerpo EXACTO que `_anthropic_tool_call`
              arma (capturado con `urllib.request.urlopen` BLOQUEADO y contado), más los cuerpos de count_tokens, y los
              imprime SIN red, SIN llave y SIN escribir archivo (salvo --out). Mide: `system` 2 bloques con
              `cache_control` (sha del bloque A == SHARED_BLOCK_SHA, sha del bloque B == CARDS[agent].sha), `tools` ×3
              byte-idénticos a council.TOOLS, `tool_choice` forzado, `max_tokens` 4000, `output_config.effort 'medium'`,
              test estático de los tools (sin campos prohibidos), `urlopen` reales = 0, `db` no importado. Es el ÚNICO
              modo que corre el integrador (C9).

Salida en vivo: una línea por llamada (fila · kind · usage con caché · meta · latencia) y
`analysis/outputs/live_council_<fecha>.json` (append por invocación) pasado por un cinturón anti-secreto: nunca se
serializan headers, env ni llaves — sólo su PRESENCIA. Sin `ANTHROPIC_API_KEY` en el entorno rehúsa con `no-api-key`
(exit 2) ANTES de tocar red. No importa `db`, `runs` ni `app`: `lib.council` importa `agent_matrix`, `catalog_cards`,
`composite_auditor`, `models` y `search_harness` — ninguno abre conexión alguna (medido al final: `db_imported False`).

Uso (venv de los gates: dev/.venvs/witt-query-service; la llave en ESTA shell, jamás en git):
  python analysis/scripts/smoke_live_council.py --dry-run
  python analysis/scripts/smoke_live_council.py --count-tokens
  python analysis/scripts/smoke_live_council.py --member literature-monitor --round r1 --repeat 2
  python analysis/scripts/smoke_live_council.py --member literature-monitor --round r2
  python analysis/scripts/smoke_live_council.py --full-r1 --question "..." --entities pax2a,wt1a
"""
import argparse
import contextlib
import datetime as _dt
import hashlib
import inspect
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))

# Windows: la consola/pipe de Emmanuel puede ser cp1252 y este script imprime UTF-8 (glosas, fichas).
# Reemplazar en vez de tumbar la corrida: un gate en vivo que gastó no debe morir al imprimir su resultado.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # pragma: no cover
            pass

from lib import models  # noqa: E402  — la única tabla de modelos (ADR-0081; rol `council` ADR-0082 D.2)

OUT_DIR = ROOT / "analysis" / "outputs"
KEY_ENV = "ANTHROPIC_API_KEY"
COUNT_TOKENS_URL = "https://api.anthropic.com/v1/messages/count_tokens"
EXIT_OK, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2
DEFAULT_MEMBER = "literature-monitor"          # el miembro que nombra el ADR en LG1
ROUNDS_LIVE = ("r1", "r2")                      # r3 comparte tool y payload con r2 (kind 'recoverage'); se mide como r2

# Lo que C2 debe exponer para que este script mida con el código REAL (ADR-0082 (C)); sin replicar nada.
C2_SURFACE = ("build_request", "default_caller", "run_round", "aggregate_r1", "validate_tool_input", "config",
              "resolve_council_model", "tools_static_check", "TOOLS", "TOOLS_SHA", "SHARED_BLOCK_SHA",
              "MIN_CACHEABLE_TOKENS", "requirement_id", "COUNCIL_SOURCE_FAMILIES", "COUNCIL_EVIDENCE_KINDS")

# Probe MÍNIMO para count_tokens: los tokens del prefijo se obtienen por DIFERENCIA contra este mensaje (regla declarada).
COUNT_PROBE = "count"


# ---------------------------------------------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------------------------------------------
def _accepts(fn, name):
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    return name in params or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())


def _numeric(usage):
    return {k: v for k, v in (usage or {}).items() if isinstance(v, (int, float)) and not isinstance(v, bool)}


def _err(e):
    return f"{getattr(e, 'legacy_type_name', type(e).__name__)}: {str(e)[:200]}"


def _kind(e):
    return getattr(e, "kind", None) or "unclassified"


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canon(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


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
# Imports perezosos con mensaje claro (C1/C2 proveen fichas, membresía, tools, request y caller)
# ---------------------------------------------------------------------------------------------------------------
def _load_council():
    try:
        from lib import council, agent_matrix, catalog_cards, composite_auditor
    except Exception as e:  # pragma: no cover — se declara, no se disimula
        return None, [f"lib.council no importable ({_err(e)})"]
    missing = [n for n in C2_SURFACE if not hasattr(council, n)]
    if not _accepts(composite_auditor._anthropic_tool_call, "tools"):
        missing.append("_anthropic_tool_call(tools=)")
    if not _accepts(composite_auditor._anthropic_tool_call, "return_meta"):
        missing.append("_anthropic_tool_call(return_meta=True)")
    mods = {"council": council, "agent_matrix": agent_matrix, "catalog_cards": catalog_cards,
            "composite_auditor": composite_auditor}
    return mods, missing


# ---------------------------------------------------------------------------------------------------------------
# Fixture: sintético y DECLARADO — sin identificadores externos (§7: ninguno sale de memoria), sin afirmación biológica.
# Lo que se mide es el TRANSPORTE con los schemas y prompts reales (tool_use, required, stop_reason, caché, latencia).
# ---------------------------------------------------------------------------------------------------------------
def default_fixture():
    return {
        "question": ("Smoke fixture (ADR-0082 LG1): which information would be needed to judge whether the early "
                     "zebrafish pronephros patterning literature supports a given marker-expression statement? "
                     "State the requirements only; do not answer."),
        "entities": [],
        "judgment": {"work_type": "literature-synthesis", "route": "evidence-run",
                     "niches": ["pronephros-patterning"], "clarifying_questions": [], "state": "declared"},
        "evidence": [{"evidence_id": "smoke-fixture-1", "kind": "smoke-fixture", "source_family": "smoke",
                      "text": ("SYNTHETIC SMOKE PASSAGE — not evidence. This item exists only to exercise the forced "
                               "tool call end to end; it makes no biological claim and names no identifier.")}],
        "pass1": {"direct_answer": ("The evidence shown is a synthetic smoke fixture that makes no biological claim; "
                                    "no statement can be supported from it."),
                  "gap_flags": ["smoke-fixture: no evidence"], "absence_kind": "no-evidence-retrieved",
                  "citations": []},
    }


def _ctx_for(round_, agent, fx, council):
    """El `ctx` que `council.payload_r1/payload_r2` esperan (contrato C2). r2: UN requisito kept pedido por ESTE
    miembro — el único insumo suyo — con una vista de evidencia sintética de UN ítem citable."""
    base = {"question": fx["question"], "entities": list(fx.get("entities") or []), "phase": "plan" if round_ == "r1" else "run"}
    if round_ == "r1":
        base.update({"judgment": fx.get("judgment"), "prior_observations": [],
                     "prior_observations_state": "not-run (live smoke: council_index not consulted)",
                     "inherited_criteria": None, "human_attestations": None})
        return base
    fam = "europepmc" if "europepmc" in council.COUNCIL_SOURCE_FAMILIES else council.COUNCIL_SOURCE_FAMILIES[0]
    kind = "paper" if "paper" in council.COUNCIL_EVIDENCE_KINDS else council.COUNCIL_EVIDENCE_KINDS[0]
    query_en = "zebrafish pronephros marker expression early patterning"
    rid = council.requirement_id(fam, kind, query_en, [])
    req = {"requirement_id": rid, "gap": "Primary literature stating which markers delimit early pronephros territories",
           "evidence_kind": kind, "source_family": fam, "query_en": query_en, "entities": [],
           "acceptance_test": "at least one primary paper with an explicit expression-domain statement",
           "priority": "must", "requested_by": [agent], "n_requested_by": 1, "n_members": 17,
           "hard_rule_gate": False, "exploratory": False, "from_operative": False, "harness_state": "satisfiable",
           "decision": "keep", "decided_by": "human:smoke-live (synthetic ledger, declared)"}
    base.update({"ledger": {"requirements": [req]}, "evidence_view": {"items": fx["evidence"], "state": "synthetic (live smoke)"},
                 "evidence_ids": [e["evidence_id"] for e in fx["evidence"]], "pass1": fx.get("pass1"),
                 "human_attestations": None})
    return base


# ---------------------------------------------------------------------------------------------------------------
# Dry-run: red BLOQUEADA y contada; llave placeholder que NO es credencial
# ---------------------------------------------------------------------------------------------------------------
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
        raise urllib.error.URLError("dry-run: red BLOQUEADA (ADR-0082 L.3)")

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


# ---------------------------------------------------------------------------------------------------------------
# Configuración del consejo para ESTE proceso (env local: la env del proceso NO se muta salvo el placeholder)
# ---------------------------------------------------------------------------------------------------------------
def _env_for(args):
    env = dict(os.environ)
    if args.effort:
        env["WITT_COUNCIL_EFFORT"] = args.effort
    if args.cache is not None:
        env["WITT_COUNCIL_CACHE"] = "1" if args.cache else "0"
    if args.cache_ttl:
        env["WITT_COUNCIL_CACHE_TTL"] = args.cache_ttl
    if args.model:
        env["WITT_MODEL_COUNCIL"] = args.model
    return env


def _cfg_for(args, council, env, dry_run):
    overrides = {}
    if args.timeout:
        overrides["member_timeout_s"] = int(args.timeout)
    if args.concurrency:
        overrides["concurrency"] = int(args.concurrency)
    if args.budget_s:
        overrides["budget_s"] = int(args.budget_s)
    if dry_run:
        overrides["member_retries"] = 0        # un solo urlopen bloqueado por petición: `urlopen_attempts` = 1
    return council.config(env, **overrides)


def _system_summary(system, council, catalog_cards, agent):
    """Resumen MEDIDO del `system`: bloques, chars, cache_control y shas contra las constantes de C1/C2."""
    card = catalog_cards.card(agent)
    if isinstance(system, list):
        blocks = []
        for i, b in enumerate(system):
            text = b.get("text") or ""
            blocks.append({"i": i, "chars": len(text), "sha": _sha256(text), "cache_control": b.get("cache_control", "<ausente>")})
        return {"kind": "list", "n_blocks": len(blocks), "blocks": blocks,
                "block_a_is_shared_block": bool(blocks) and blocks[0]["sha"] == council.SHARED_BLOCK_SHA,
                "block_b_is_card_verbatim": len(blocks) > 1 and card is not None and blocks[1]["sha"] == card["sha"],
                "cache_control_on_all_blocks": all(b["cache_control"] != "<ausente>" for b in blocks)}
    text = system if isinstance(system, str) else ""
    return {"kind": "str", "chars": len(text), "sha": _sha256(text),
            "equals_shared_plus_card": card is not None and text == council.SHARED_BLOCK_TEXT + "\n\n" + card["text_verbatim"]}


def _body_summary(body, council, catalog_cards, agent, request):
    """Lo que la API VERÍA (cuerpo real capturado): system, tools ×3 byte a byte, tool_choice, topes, effort."""
    if not isinstance(body, dict):
        return None
    tools = body.get("tools") or []
    return {
        "model": body.get("model"), "max_tokens": body.get("max_tokens"),
        "tool_choice": body.get("tool_choice"),
        "tool_choice_matches_request": body.get("tool_choice") == request["tool_choice"],
        "tools_names": [t.get("name") for t in tools], "n_tools": len(tools),
        "tools_byte_identical_to_council_TOOLS": _canon(tools) == _canon(list(council.TOOLS)),
        "tools_sha": _sha256(_canon(tools)), "tools_sha_matches": _sha256(_canon(tools)) == council.TOOLS_SHA,
        "output_config": body.get("output_config", "<ausente>"),
        "thinking": body.get("thinking", "<ausente>"),
        "system": _system_summary(body.get("system"), council, catalog_cards, agent),
        "user_chars": sum(len(m.get("content") or "") if isinstance(m.get("content"), str) else 0
                          for m in body.get("messages", [])),
        "n_messages": len(body.get("messages", [])),
    }


# ---------------------------------------------------------------------------------------------------------------
# Un miembro, una ronda (LG1) — dry-run o en vivo
# ---------------------------------------------------------------------------------------------------------------
def run_member(agent, round_, fx, args, mods, env, cfg, dry_run, attempt_no=1):
    council, catalog_cards, ca = mods["council"], mods["catalog_cards"], mods["composite_auditor"]
    row = {"item": f"member:{agent}:{round_}", "agent": agent, "round": round_, "attempt_no": attempt_no,
           "dry_run": dry_run, "kind": None, "error": None}
    try:
        ctx = _ctx_for(round_, agent, fx, council)
        request = council.build_request(agent, round_, ctx, cfg, env)
    except Exception as e:
        row.update(kind="bad-request", error=_err(e))
        return row
    if args.max_tokens:
        request["max_tokens"] = int(args.max_tokens)
        row["max_tokens_source"] = "cli:--max-tokens"
    else:
        row["max_tokens_source"] = "models.resolve_role('council').max_tokens (tabla)"
    if dry_run:
        request["retries"] = 0
    row.update({
        "seat": request["seat"], "group": request["group"], "mode": request["mode"], "kind_round": request["kind"],
        "tool": request["tool"], "tool_choice": request["tool_choice"], "tools_sha": request["tools_sha"],
        "tools_sha_matches_council": request["tools_sha"] == council.TOOLS_SHA,
        "system_sha": request["system_sha"], "card_sha": request["card_sha"], "shared_block_sha": request["shared_block_sha"],
        "rules_sha": request["rules_sha"], "cache": request["cache"],
        "payload_chars": request["payload_chars"], "payload_truncated": request["payload_truncated"],
        "model_requested": request["model"], "model_source": request["model_source"],
        "max_tokens_sent": request["max_tokens"],
        "effort_pinned": request.get("effort_pinned"), "effort_sent": request["effort"], "effort_source": request["effort_source"],
        "timeout_s": request["timeout_s"], "retries": request["retries"],
        "required": list(request["tool_def"]["input_schema"].get("required", [])),
        "system_summary": _system_summary(request["system"], council, catalog_cards, agent),
    })
    t0 = time.perf_counter()
    net = []
    try:
        if dry_run:
            with _placeholder_key(KEY_ENV), _blocked_urlopen(net):
                try:
                    council.default_caller(request)
                except Exception as e:
                    row["caller_reaction"] = {"kind": _kind(e), "error": _err(e)}
            body = net[0]["body"] if net else None
            row.update(kind="dry-run", urlopen_attempts=len(net), network_calls_real=0,
                       url=(net[0]["url"] if net else None),
                       body_summary=_body_summary(body, council, catalog_cards, agent, request))
            if args.verbose:
                row["body"] = body
            return row
        tool_input, usage, meta = council.default_caller(request)
        row["latency_s"] = round(time.perf_counter() - t0, 3)
        meta = meta or {}
        usage = _numeric(usage)
        reported = meta.get("model_reported")
        clean, report = council.validate_tool_input(agent, round_, tool_input, cfg)
        missing = [k for k in row["required"] if not isinstance(tool_input, dict) or tool_input.get(k) is None]
        row.update(kind="ok", model_reported=reported, relation=models.relation(request["model"], reported),
                   thinking_state=models.thinking_state(request["model"]), stop_reason=meta.get("stop_reason"),
                   stop_details=meta.get("stop_details"), response_id=meta.get("response_id"), api_reported=meta.get("api"),
                   attempts=meta.get("attempts"), queue_wait_s=meta.get("queue_wait_s"),
                   retry_after_honored_s=meta.get("retry_after_honored_s"), usage=usage, required_missing=missing,
                   validation={k: report.get(k) for k in ("tool", "kind", "n_items_raw", "n_items_kept", "n_dropped_over_cap",
                                                            "dropped_fields", "prohibited_fields_seen", "off_vocabulary",
                                                            "truncated_fields", "dropped_items")},
                   clean_output=clean, tool_input=tool_input if args.verbose else "<usa --verbose>")
        for k in ("thinking_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
            row[k] = usage[k] if k in usage else "<ausente>"        # ausente ≠ 0: la API no lo mandó
        if row["stop_reason"] is not None:
            row["stop_reason_is_tool_use"] = row["stop_reason"] == "tool_use"
        if isinstance(usage.get("cache_read_input_tokens"), (int, float)):
            row["cache_read_gt_0"] = usage["cache_read_input_tokens"] > 0
        if isinstance(usage.get("cache_creation_input_tokens"), (int, float)):
            row["cache_creation_gt_0"] = usage["cache_creation_input_tokens"] > 0
        return row
    except Exception as e:
        row.update(kind=_kind(e), error=_err(e), latency_s=round(time.perf_counter() - t0, 3))
        u = getattr(e, "usage", None)
        if u:
            row["usage_of_failed_attempts"] = _numeric(u)       # la API cobró aunque el intento no valiera (D.1)
        return row


# ---------------------------------------------------------------------------------------------------------------
# count_tokens (LG1): tokens del prefijo compartido y de cada ficha — MEDICIÓN, USD 0
# ---------------------------------------------------------------------------------------------------------------
def _strip_cache_control(system):
    if isinstance(system, list):
        return [{k: v for k, v in b.items() if k != "cache_control"} for b in system]
    return system


def _count_body(model, system=None, tools=None):
    body = {"model": model, "messages": [{"role": "user", "content": COUNT_PROBE}]}
    if system is not None:
        body["system"] = _strip_cache_control(system)
    if tools is not None:
        body["tools"] = list(tools)
    return body


def _count_tokens_call(body, timeout):
    key = os.environ.get(KEY_ENV)
    if not key:
        raise RuntimeError("no-api-key")
    from lib import composite_auditor as ca
    headers = {"x-api-key": key, "anthropic-version": ca.ANTHROPIC_VERSION, "content-type": "application/json"}
    req = urllib.request.Request(COUNT_TOKENS_URL, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    n = payload.get("input_tokens")
    if not isinstance(n, int):
        raise RuntimeError(f"count_tokens sin input_tokens numérico: {str(payload)[:200]}")
    return n


def run_count_tokens(args, mods, env, cfg, dry_run):
    council, catalog_cards, agent_matrix = mods["council"], mods["catalog_cards"], mods["agent_matrix"]
    mres = council.resolve_council_model(env, cfg)
    model = mres["model"]
    members = agent_matrix.council_members(env, full=bool(args.full))
    shared_system = [{"type": "text", "text": council.SHARED_BLOCK_TEXT}]
    bodies = [("base", _count_body(model)), ("tools_only", _count_body(model, tools=council.TOOLS)),
              ("tools+blockA", _count_body(model, system=shared_system, tools=council.TOOLS))]
    for a in members:
        card = catalog_cards.card(a)
        if card is None:
            bodies.append((f"card:{a}", None))
            continue
        bodies.append((f"card:{a}", _count_body(model, system=shared_system + [{"type": "text", "text": card["text_verbatim"]}],
                                                tools=council.TOOLS)))
    row = {"item": "count-tokens", "dry_run": dry_run, "model_requested": model, "model_source": mres["source"],
           "n_members": len(members), "n_calls_planned": sum(1 for _, b in bodies if b is not None),
           "min_cacheable_tokens": council.MIN_CACHEABLE_TOKENS,
           "rule": ("shared_prefix_tokens = count(tools+blockA) - count(base); tools_tokens = count(tools_only) - count(base); "
                    "blockA_tokens = count(tools+blockA) - count(tools_only); card_tokens = count(tools+blockA+card) - "
                    "count(tools+blockA); cache_control stripped for counting (token count is identical); probe = 'count'"),
           "class": "medicion (count_tokens)" if not dry_run else "not-measured (dry-run: bodies built, no call)",
           "bodies_chars": {name: (len(json.dumps(b, ensure_ascii=False)) if b else None) for name, b in bodies},
           "kind": None}
    if dry_run:
        row.update(kind="dry-run", network_calls_real=0, note="20 cuerpos construidos; ninguna llamada (USD 0 también en vivo)")
        return row
    counts, errors = {}, {}
    t0 = time.perf_counter()
    for name, body in bodies:
        if body is None:
            errors[name] = "no-card-in-catalog"
            continue
        try:
            counts[name] = _count_tokens_call(body, args.timeout or 60)
        except Exception as e:
            errors[name] = _err(e)
    row["latency_s_total"] = round(time.perf_counter() - t0, 3)
    row["counts"] = counts
    row["errors"] = errors
    if all(k in counts for k in ("base", "tools_only", "tools+blockA")):
        shared = counts["tools+blockA"] - counts["base"]
        row["shared_prefix_tokens"] = shared
        row["tools_tokens"] = counts["tools_only"] - counts["base"]
        row["blockA_tokens"] = counts["tools+blockA"] - counts["tools_only"]
        row["shared_prefix_cacheable"] = shared >= council.MIN_CACHEABLE_TOKENS
        row["shared_prefix_rule"] = ("cacheable iff shared_prefix_tokens >= MIN_CACHEABLE_TOKENS (512, Opus 5); if false the "
                                     "cache never writes (cache_creation_input_tokens 0 silently) — ADR-0082 LG1")
        cards = {}
        for a in members:
            k = f"card:{a}"
            if k in counts:
                cards[a] = counts[k] - counts["tools+blockA"]
        row["card_tokens"] = cards
        if cards:
            vals = sorted(cards.values())
            row["card_tokens_stats"] = {"n": len(vals), "min": vals[0], "max": vals[-1],
                                        "median": vals[len(vals) // 2], "sum": sum(vals),
                                        "class": "medicion (count_tokens); sustituye la proyección '≈ 0.3k tok de media'"}
        row["kind"] = "ok" if not errors else "partial"
    else:
        row["kind"] = "failed"
    return row


# ---------------------------------------------------------------------------------------------------------------
# Ronda 1 completa (LG2): el MISMO run_round + aggregate_r1 del worker, sin plan ni BD
# ---------------------------------------------------------------------------------------------------------------
def run_full_r1(args, mods, env, cfg, dry_run):
    council, agent_matrix = mods["council"], mods["agent_matrix"]
    fx = default_fixture()
    fx["question"] = args.question
    fx["entities"] = [e.strip() for e in (args.entities or "").split(",") if e.strip()]
    members = agent_matrix.council_members(env, full=bool(args.full))
    ctx = _ctx_for("r1", members[0], fx, council)
    row = {"item": "full-r1", "dry_run": dry_run, "n_members": len(members), "members": members,
           "full_council": bool(args.full), "question_chars": len(args.question), "entities": fx["entities"], "kind": None}
    if dry_run:
        reqs = {}
        for a in members:
            try:
                r = council.build_request(a, "r1", ctx, cfg, env)
                reqs[a] = {"tool": r["tool"], "payload_chars": r["payload_chars"], "system_sha": r["system_sha"], "card_sha": r["card_sha"]}
            except Exception as e:
                reqs[a] = {"error": _err(e)}
        shas = {v.get("system_sha") for v in reqs.values() if "system_sha" in v}
        row.update(kind="dry-run", network_calls_real=0, requests=reqs, n_requests_built=sum(1 for v in reqs.values() if "tool" in v),
                   system_sha_distinct=len(shas), note="17 peticiones construidas; cero llamadas (run_round NO se invoca en dry-run)")
        return row
    events = []

    def on_event(etype, payload):
        events.append({"type": etype, "payload": payload})
        p = payload or {}
        if etype == "stage.council.member":
            print(f"  · {etype} {p.get('agent')} {p.get('phase')} {p.get('status') or ''} {p.get('error_kind') or ''} "
                  f"{('%.1fs' % p['elapsed_s']) if isinstance(p.get('elapsed_s'), (int, float)) else ''} "
                  f"cache_read={p.get('cache_read', '<ausente>')}")
        elif etype == "stage.council.progress":
            print(f"  · latido {p.get('n_done')}/{(p.get('n_done') or 0) + (p.get('n_pending') or 0)} listos · {p.get('elapsed_s')}s")
        elif etype == "stage.council.round":
            print(f"  · ronda {p.get('round')} {p.get('state')} · válidos {p.get('n_valid')}/{p.get('n_members')} · quórum {p.get('quorum')} · "
                  f"errored {p.get('n_errored')} timeout {p.get('n_timeout')} · stagger {p.get('stagger_wait_s')}s · {p.get('elapsed_s')}s")

    t0 = time.perf_counter()
    try:
        rr = council.run_round(members, "r1", ctx, caller=council.default_caller, on_event=on_event, cfg=cfg, env=env)
    except Exception as e:
        row.update(kind=_kind(e), error=_err(e), latency_s=round(time.perf_counter() - t0, 3), events=events)
        return row
    row["latency_s"] = round(time.perf_counter() - t0, 3)
    keep = ("state", "n_members", "n_invoked", "n_valid", "n_ok", "n_not_applicable", "n_errored", "n_timeout",
            "n_skipped_budget", "n_skipped_cancelled", "quorum", "budget_s", "elapsed_s", "over_budget", "stagger_wait_s",
            "stagger_first", "concurrency", "abandoned_threads", "abandoned_cost_upper_usd", "cache_prefix_identical_across_members",
            "cache", "model", "usage", "tools_sha", "rules_sha", "shared_block_sha", "catalog_sha", "events")
    row["round"] = {k: rr.get(k) for k in keep if k in rr}
    row["members_rows"] = [{k: m.get(k) for k in ("agent", "status", "error_kind", "attempts", "elapsed_s", "queue_wait_s",
                                                    "usage", "model_reported", "relation", "stop_reason", "payload_chars")}
                           for m in rr.get("members", [])]
    try:
        agg = council.aggregate_r1(rr, members=members, cfg=cfg)     # resolver default = resolve_id (DATA INAMOVIBLE, sólo lectura)
        row["aggregation"] = {k: agg.get(k) for k in ("state", "n_valid", "n_raw", "n_dedup", "n_requirements", "n_must", "n_should",
                                                       "truncated", "n_truncated", "n_unsatisfiable", "n_hard_rule", "n_exploratory",
                                                       "n_from_operative", "n_flags", "entities_resolution_state", "aggregation_sha",
                                                       "decided_by")}
        row["requirements"] = [{k: r.get(k) for k in ("requirement_id", "gap", "priority", "priority_downgraded_from", "source_family",
                                                       "evidence_kind", "query_en", "n_requested_by", "n_members", "hard_rule_gate",
                                                       "exploratory", "harness_state", "entities", "entities_resolved", "entities_unresolved")}
                               for r in agg.get("requirements", [])]
        row["flags"] = agg.get("flags", [])
        row["notes_for_human"] = agg.get("notes_for_human", [])
        row["aggregation_resolver"] = "council._default_resolver → resolve_id.resolve (DATA INAMOVIBLE, read-only; declared)"
    except Exception as e:
        row["aggregation_error"] = _err(e)
    row["kind"] = "ok" if rr.get("state") == "applicable" else f"round-{rr.get('state')}"
    row["events_n"] = len(events)
    row["events_from_orchestrator_thread"] = (rr.get("events") or {}).get("emitted_from")
    return row


# ---------------------------------------------------------------------------------------------------------------
# Impresión
# ---------------------------------------------------------------------------------------------------------------
def _print_row(r):
    if r["item"] == "count-tokens":
        if r["kind"] == "dry-run":
            print(f"[count-tokens] DRY-RUN {r['model_requested']} (fuente {r['model_source']}) → {r['n_calls_planned']} cuerpos "
                  f"construidos para {COUNT_TOKENS_URL}; reales=0 · chars base/tools/tools+A: {r['bodies_chars'].get('base')}/"
                  f"{r['bodies_chars'].get('tools_only')}/{r['bodies_chars'].get('tools+blockA')}")
        else:
            st = r.get("card_tokens_stats") or {}
            print(f"[count-tokens] {r['model_requested']} → kind={r['kind']} prefijo_compartido={r.get('shared_prefix_tokens')} tok "
                  f"(tools {r.get('tools_tokens')} + bloqueA {r.get('blockA_tokens')}) cacheable(≥512)={r.get('shared_prefix_cacheable')} · "
                  f"fichas n={st.get('n')} min/mediana/max={st.get('min')}/{st.get('median')}/{st.get('max')} suma={st.get('sum')} · "
                  f"{r.get('latency_s_total')}s" + (f" · errores {r['errors']}" if r.get("errors") else ""))
        return
    if r["item"] == "full-r1":
        if r["kind"] == "dry-run":
            print(f"[full-r1] DRY-RUN N={r['n_members']} → {r['n_requests_built']} peticiones construidas, system_sha distintos="
                  f"{r['system_sha_distinct']} (uno por ficha), reales=0")
        else:
            rd, ag = r.get("round") or {}, r.get("aggregation") or {}
            u = rd.get("usage") or {}
            print(f"[full-r1] N={r['n_members']} → {rd.get('state')} válidos {rd.get('n_valid')}/{rd.get('n_members')} quórum "
                  f"{(rd.get('quorum') or {}).get('required')} errored={rd.get('n_errored')} timeout={rd.get('n_timeout')} "
                  f"stagger={rd.get('stagger_wait_s')}s elapsed={rd.get('elapsed_s')}s · usage in={u.get('in')} out={u.get('out')} "
                  f"cache_creation={u.get('cache_creation')} cache_read={u.get('cache_read')} think={u.get('thinking_tokens', '<ausente>')} · "
                  f"prefijo idéntico={rd.get('cache_prefix_identical_across_members')} · agregado: {ag.get('n_requirements')} req "
                  f"(must {ag.get('n_must')} / should {ag.get('n_should')}) hard_rule={ag.get('n_hard_rule')} unsatisfiable="
                  f"{ag.get('n_unsatisfiable')} flags={ag.get('n_flags')} sha={str(ag.get('aggregation_sha'))[:16]}"
                  + (f" ERROR {r['error']}" if r.get("error") else ""))
            for q in r.get("requirements", []):
                print(f"    - {q['requirement_id']} [{q['priority']}] {q['source_family']}/{q['evidence_kind']} pedido por "
                      f"{q['n_requested_by']}/{q['n_members']}{' HARD-RULE' if q.get('hard_rule_gate') else ''}"
                      f"{' ' + q['harness_state'] if q.get('harness_state') != 'satisfiable' else ''}: {str(q.get('gap'))[:110]}")
        return
    if r["kind"] == "dry-run":
        s = r.get("body_summary") or {}
        sy = s.get("system") or {}
        print(f"[{r['item']}] DRY-RUN {r['model_requested']} (fuente {r['model_source']}) → cuerpo REAL capturado: model={s.get('model')} "
              f"max_tokens={s.get('max_tokens')} tools={s.get('tools_names')} byte-idénticos={s.get('tools_byte_identical_to_council_TOOLS')} "
              f"tool_choice={s.get('tool_choice')} output_config={s.get('output_config')} thinking={s.get('thinking')} "
              f"system={sy.get('kind')}×{sy.get('n_blocks', 1)} cache_control_all={sy.get('cache_control_on_all_blocks', 'n/a')} "
              f"A==SHARED={sy.get('block_a_is_shared_block', sy.get('equals_shared_plus_card'))} B==ficha={sy.get('block_b_is_card_verbatim', 'n/a')} "
              f"user_chars={s.get('user_chars')} · effort pinneado={r.get('effort_pinned')} enviado={r.get('effort_sent')} · "
              f"urlopen intentos={r.get('urlopen_attempts')} reales=0 · caller={r.get('caller_reaction')}")
        return
    if r["kind"] in ("bad-request",):
        print(f"[{r['item']}] {r['kind']}: {r.get('error')}")
        return
    u = r.get("usage") or {}
    v = r.get("validation") or {}
    print(f"[{r['item']}] intento {r['attempt_no']} {r['model_requested']} (fuente {r['model_source']}) → kind={r['kind']} "
          f"reported={r.get('model_reported')} relation={r.get('relation')} stop={r.get('stop_reason')} in={u.get('input_tokens')} "
          f"out={u.get('output_tokens')} think={r.get('thinking_tokens', '<ausente>')} cache_creation={r.get('cache_creation_input_tokens', '<ausente>')} "
          f"cache_read={r.get('cache_read_input_tokens', '<ausente>')} latency={r.get('latency_s')}s queue_wait={r.get('queue_wait_s')} "
          f"required_missing={r.get('required_missing')} validation={v.get('kind')} kept={v.get('n_items_kept')}/{v.get('n_items_raw')} "
          f"dropped_fields={v.get('dropped_fields')} off_vocab={len(v.get('off_vocabulary') or [])}"
          + (f" ERROR {r['error']}" if r.get("error") else ""))


# ---------------------------------------------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count-tokens", action="store_true", help="LG1: count_tokens del prefijo compartido y de las 17 fichas (USD 0)")
    ap.add_argument("--member", default=None, help="LG1: UN miembro de la membresía cm-1 (p. ej. literature-monitor)")
    ap.add_argument("--round", dest="round_", choices=ROUNDS_LIVE, default="r1", help="ronda del miembro: r1 (requisitos) | r2 (cobertura)")
    ap.add_argument("--repeat", type=int, default=1, help="repite la MISMA petición N veces seguidas (2 = medir escritura y lectura de caché)")
    ap.add_argument("--full-r1", action="store_true", help="LG2: ronda 1 completa por council.run_round + aggregate_r1 (17 llamadas; 25 con --full)")
    ap.add_argument("--question", default=None, help="pregunta para --full-r1 (obligatoria con él)")
    ap.add_argument("--entities", default=None, help="CSV de símbolos para --full-r1 (se resuelven por resolve_id, sólo lectura)")
    ap.add_argument("--full", action="store_true", help="membresía full-council (N=25: los 8 operativos también) — E5: sólo A/B")
    ap.add_argument("--model", default=None, help="WITT_MODEL_COUNCIL sólo en este proceso (la tabla puede rechazarlo: excluded-model)")
    ap.add_argument("--effort", default=None, help="WITT_COUNCIL_EFFORT sólo en este proceso (low|medium|high|xhigh|max|inherit); E2")
    ap.add_argument("--cache", type=int, choices=(0, 1), default=None, help="WITT_COUNCIL_CACHE sólo en este proceso (A/B)")
    ap.add_argument("--cache-ttl", choices=("5m", "1h"), default=None, help="WITT_COUNCIL_CACHE_TTL sólo en este proceso (E3)")
    ap.add_argument("--max-tokens", type=int, default=None, help="tope max_tokens (default: tabla, 4000 en g2)")
    ap.add_argument("--timeout", type=int, default=None, help="timeout por miembro (s); default WITT_COUNCIL_MEMBER_TIMEOUT_S 120")
    ap.add_argument("--concurrency", type=int, default=None, help="max_workers del pool para --full-r1 (default WITT_COUNCIL_CONCURRENCY 6)")
    ap.add_argument("--budget-s", type=int, default=None, help="presupuesto de ronda para --full-r1 (default WITT_COUNCIL_ROUND_BUDGET_S 300)")
    ap.add_argument("--fixture", default=None, help="JSON que sobreescribe llaves del fixture sintético (question, entities, judgment, evidence, pass1)")
    ap.add_argument("--dry-run", action="store_true", help="construye e imprime peticiones y cuerpos SIN red ni llave (lo que corre C9)")
    ap.add_argument("--out", default=None, help="ruta del JSON de salida (default: analysis/outputs/live_council_<fecha>.json; --dry-run no escribe salvo --out)")
    ap.add_argument("--verbose", action="store_true", help="imprime el cuerpo completo en --dry-run y el tool_input en vivo")
    args = ap.parse_args(argv)

    if args.effort:
        args.effort = args.effort.strip().lower()
    if args.repeat < 1:
        args.repeat = 1
    if args.full_r1 and not args.question:
        print(json.dumps({"kind": "bad-args", "error": "--full-r1 exige --question"}, ensure_ascii=False))
        return EXIT_REFUSED

    mods, missing = _load_council()
    if mods is None or missing:
        print(json.dumps({"kind": "c2-pending", "error": "lib.council / composite_auditor no exponen la superficie de ADR-0082 (C2/D.1) que "
                          "este script usa con el código REAL — no se replica nada", "missing": missing,
                          "expected": {"council": list(C2_SURFACE), "composite_auditor": "_anthropic_tool_call(..., tools=, return_meta=True)"}},
                         ensure_ascii=False, indent=2))
        return EXIT_REFUSED
    council, agent_matrix, catalog_cards = mods["council"], mods["agent_matrix"], mods["catalog_cards"]

    # modo por default en --dry-run: el miembro del ADR en r1 y r2 + los cuerpos de count_tokens (lo que C9 corre)
    default_mode = not (args.count_tokens or args.member or args.full_r1)
    if default_mode and not args.dry_run:
        print(json.dumps({"kind": "bad-args", "error": "nada que correr: --count-tokens y/o --member y/o --full-r1 (o --dry-run)"},
                         ensure_ascii=False))
        return EXIT_REFUSED

    fx = default_fixture()
    if args.fixture:
        fx.update(json.loads(Path(args.fixture).read_text(encoding="utf-8")))

    env = _env_for(args)
    cfg = _cfg_for(args, council, env, args.dry_run)
    enabled, enabled_src = council.enabled(env)
    mres = council.resolve_council_model(env, cfg)
    members_all = agent_matrix.council_members(env, full=bool(args.full))
    if args.member and args.member not in members_all:
        print(json.dumps({"kind": "bad-args", "error": f"{args.member!r} no está en la membresía cm-1" + (" (ni en full-council)" if args.full else ""),
                          "members": members_all}, ensure_ascii=False, indent=2))
        return EXIT_REFUSED
    if not mres["model"]:
        print(json.dumps({"kind": "no-model", "error": "models.resolve_role('council') no resolvió modelo", "source": mres["source"]}, ensure_ascii=False))
        return EXIT_REFUSED

    # plan de llamadas (para decir ANTES cuánto gasta)
    plan = []
    if args.count_tokens or default_mode:
        plan.append(("count-tokens", 3 + len(members_all), "USD 0 (count_tokens no cobra)"))
    if args.member:
        plan.append((f"member:{args.member}:{args.round_}", args.repeat, "1 llamada real por repetición"))
    elif default_mode:
        plan.append((f"member:{DEFAULT_MEMBER}:r1+r2", 2, "dry-run"))
    if args.full_r1:
        plan.append(("full-r1", len(members_all), f"{len(members_all)} llamadas reales (ronda 1 completa)"))

    key_present = bool(os.environ.get(KEY_ENV))
    if not args.dry_run:
        if not key_present:
            print(json.dumps({"kind": "no-api-key", "error": "sin ANTHROPIC_API_KEY en el entorno del proceso; nada se llamó",
                              "missing_env": [KEY_ENV], "hint": "exporta la llave en ESTA shell (jamás en git ni en archivos del repo)"},
                             ensure_ascii=False, indent=2))
            return EXIT_REFUSED
        n_live = sum(n for name, n, _ in plan if not name.startswith("count-tokens"))
        print(f"ESTA CORRIDA GASTA: {n_live} llamada(s) en vivo a {mres['model']} (fuente {mres['source']}; effort pinneado "
              f"{mres['effort']!r} → enviado {mres['effort_sent']!r}; max_tokens {mres['max_tokens']}) + "
              f"{sum(n for name, n, _ in plan if name.startswith('count-tokens'))} count_tokens (USD 0). Sin BD, sin git.")

    static = council.tools_static_check()
    cc = cfg["cache"]
    header = {"invoked_at": _today().strftime("%Y-%m-%dT%H:%M:%SZ"), "argv": sys.argv[1:], "dry_run": args.dry_run,
              "adr": "ADR-0082", "council_module_version": council.MODULE_VERSION, "membership_version": council.MEMBERSHIP_VERSION,
              "matrix_version": agent_matrix.MATRIX_VERSION, "catalog_module_version": catalog_cards.MODULE_VERSION,
              "catalog_sha": catalog_cards.CATALOG_SHA, "catalog_state": catalog_cards.CATALOG_STATE,
              "n_cards": catalog_cards.CARDS_COUNT, "rules_sha": council.RULES_SHA, "shared_block_sha": council.SHARED_BLOCK_SHA,
              "tools_sha": council.TOOLS_SHA, "tools_static_check": static,
              "council_enabled": enabled, "council_enabled_source": enabled_src,
              "n_members": len(members_all), "full_council": bool(args.full),
              "model": {k: mres.get(k) for k in ("model", "source", "generation", "known", "max_tokens", "max_tokens_source",
                                                 "effort", "effort_source", "effort_sent", "effort_sent_source")},
              "cache": {"enabled": cc["enabled"], "enabled_source": cc["enabled_source"], "ttl_card": cc["ttl_card"],
                        "ttl_shared": cc["ttl_shared"], "ttl_source": cc["ttl_source"], "min_cacheable_tokens": cc["min_cacheable_tokens"]},
              "budget": {"member_timeout_s": cfg["member_timeout_s"], "round_budget_s": cfg["budget_s"], "concurrency": cfg["concurrency"],
                         "member_retries": cfg["member_retries"], "quorum": cfg["quorum"]},
              "key_present": key_present, "plan": [{"item": n, "n_calls": k, "note": note} for n, k, note in plan]}
    print(f"ADR-0082 · council {header['council_module_version']} · membresía {header['membership_version']} (matriz {header['matrix_version']}, "
          f"N={header['n_members']}) · catálogo {header['n_cards']} fichas sha {str(header['catalog_sha'])[:16]} ({header['catalog_state']}) · "
          f"modelo {mres['model']} ({mres['source']}) effort {mres['effort']!r}→{mres['effort_sent']!r} max_tokens {mres['max_tokens']} · "
          f"caché {'ON' if cc['enabled'] else 'OFF'} ttl ficha {cc['ttl_card']} / A {cc['ttl_shared']} · tools_static_check ok={static.get('ok')} "
          f"prohibidos={static.get('prohibited_found')}" + (" · DRY-RUN (sin red, sin llave)" if args.dry_run else ""))
    if not enabled:
        print(f"  aviso: WITT_COUNCIL={env.get('WITT_COUNCIL')!r} ({enabled_src}) — el consejo está APAGADO en producción; este script mide igual")

    rows = []
    if args.count_tokens or default_mode:
        r = run_count_tokens(args, mods, env, cfg, args.dry_run)
        rows.append(r)
        _print_row(r)
    if args.member:
        for i in range(args.repeat):
            r = run_member(args.member, args.round_, fx, args, mods, env, cfg, args.dry_run, attempt_no=i + 1)
            rows.append(r)
            _print_row(r)
            if args.verbose and args.dry_run and r.get("body") is not None:
                print(json.dumps(_redact(r["body"]), ensure_ascii=False, indent=2, default=str))
    elif default_mode:
        for rn in ROUNDS_LIVE:
            r = run_member(DEFAULT_MEMBER, rn, fx, args, mods, env, cfg, True)
            rows.append(r)
            _print_row(r)
            if args.verbose and r.get("body") is not None:
                print(json.dumps(_redact(r["body"]), ensure_ascii=False, indent=2, default=str))
    if args.full_r1:
        r = run_full_r1(args, mods, env, cfg, args.dry_run)
        rows.append(r)
        _print_row(r)

    # guardas MEDIDAS del propio script: sin BD, sin runs/app; los cuerpos dry-run cumplen la forma del ADR
    db_imported = any(m in sys.modules for m in ("db", "runs", "app", "council_jobs", "council_index"))
    dry_ok = True
    if args.dry_run:
        for r in rows:
            if r["item"].startswith("member:"):
                s = r.get("body_summary") or {}
                sy = s.get("system") or {}
                ok = (r.get("kind") == "dry-run" and r.get("urlopen_attempts") == 1 and s.get("tools_byte_identical_to_council_TOOLS") is True
                      and s.get("tool_choice_matches_request") is True and s.get("n_tools") == 3
                      and (sy.get("kind") == "str" or (sy.get("n_blocks") == 2 and sy.get("block_a_is_shared_block") and sy.get("block_b_is_card_verbatim")
                                                       and (not cc["enabled"] or sy.get("cache_control_on_all_blocks")))))
                r["dry_run_shape_ok"] = ok
                dry_ok = dry_ok and ok
            elif r.get("kind") != "dry-run":
                dry_ok = False
    n_ok = sum(1 for r in rows if r["kind"] in ("ok", "dry-run"))
    n_failed = len(rows) - n_ok
    summary = {"n": len(rows), "n_ok": n_ok, "n_failed": n_failed, "failed_kinds": sorted({r["kind"] for r in rows if r["kind"] not in ("ok", "dry-run")}),
               "tools_static_check_ok": bool(static.get("ok")), "db_imported": db_imported, "dry_run_shape_ok": dry_ok if args.dry_run else None}
    exit_code = EXIT_OK if (n_failed == 0 and static.get("ok") and not db_imported and dry_ok) else EXIT_FAILED
    run = _redact({**header, "items": rows, "summary": summary, "exit_code": exit_code})

    out_path = Path(args.out) if args.out else (OUT_DIR / f"live_council_{_today().strftime('%Y%m%d')}.json")
    if args.out or not args.dry_run:
        doc = {"script": "analysis/scripts/smoke_live_council.py", "adr": "ADR-0082", "runs": []}
        if out_path.exists():
            try:
                doc = json.loads(out_path.read_text(encoding="utf-8"))
                doc.setdefault("runs", [])
            except Exception:
                doc = {"script": "analysis/scripts/smoke_live_council.py", "adr": "ADR-0082", "runs": [], "_previous_unreadable": True}
        doc["runs"].append(run)
        text = json.dumps(doc, ensure_ascii=False, indent=2, default=str)
        assert not _SECRET_VALUE_RE.search(text), "cinturón: el JSON de salida contiene algo que parece llave — no se escribe"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"escrito: {out_path.relative_to(ROOT).as_posix() if out_path.is_relative_to(ROOT) else out_path} "
              f"({len(doc['runs'])} invocación(es); sin secretos: cinturón aplicado)")
    else:
        print("dry-run: nada escrito (usa --out para guardar las peticiones)")
    print(f"resumen: {summary}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

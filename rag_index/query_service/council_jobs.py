"""
council_jobs.py — el JOB de la RONDA 1 del consejo de criterio sobre el PLAN (ADR-0082 (E.2); BD en db.py (E.1)).

La ronda 1 NO es una corrida ni una tabla `jobs` genérica: es un job del plan (plans.council_state 'queued' → 'running' →
'applicable' | 'incomplete' | 'errored (<kind>)'), porque el plan YA es el objeto que el humano aprueba ANTES de gastar
(F.1). Este módulo es el WORKER de ese job: hilos daemon `council-worker-<i>` (WITT_COUNCIL_WORKERS, default 1) con el
patrón de runs.worker_loop, que reclaman de forma optimista (db.claim_next_council_plan, FIFO, `claimed_by =
boot:pid:hilo`) SÓLO planes cuyo `origin ∈ WITT_COUNCIL_ORIGINS` (default 'production'; 'all' = sin filtro): el loop
dev-offline, los smokes (`WITT_RUN_ORIGIN=smoke`) y gen_fixtures (`fixture`) NO disparan 17 llamadas de opus-5 por
accidente (Context 9). Por cada plan reclamado: `execute_round1` → `council.run_round(members, 'r1', ctx, caller, …)`
(C2; caller INYECTABLE — los smokes lo fakean, cero red) → `council.aggregate_r1` (código byte a byte) → persistir.

Doctrina (CLAUDE.md §7, ADR-0082 (L.5)):
  · el consejo NUNCA escribe respuesta, veredicto, ranking ni despacha: aquí sólo se recogen REQUISITOS y BANDERAS y se
    agregan por código; las decisiones (keep/discard/aporto) las toma el humano en el ledger (app, F.1) — este módulo no
    escribe NUNCA plans.council_ledger_json;
  · `causal-pruner` es hard-rule: sus requisitos nacen `hard_rule_gate True` (lo pone council.aggregate_r1) y el ledger
    exige decisión humana explícita — aquí no se toma ningún default;
  · persistencia INCREMENTAL: tras CADA miembro recogido (evento `stage.council.member` phase 'done', emitido por el hilo
    orquestador de run_round) se reescriben plans.council_json (rounds[0].members parciales) y council_usage_json — un
    redeploy a media ronda conserva lo gastado por los que SÍ respondieron (LOTE-01·A4 aplicado al plan);
  · TODOS los eventos van a plan_events desde el hilo orquestador (run_round garantiza `on_event` desde el hilo llamador;
    Context 6: db.plan_add_event no es reentrante) — el latido (`stage.council.progress` cada ≤ 30 s) refresca
    plans.council_last_event_at, que es lo que mide el reaper (30 < HEARTBEAT_STALE_S 300 < WITT_REAP_STALE_S 900);
  · una excepción del worker deja `errored (<Tipo>)` con council_error y lo persistido hasta ahí, y NO tumba el hilo
    (§6 no-hang); una muerte del PROCESO deja el plan 'running' y el reaper (propio o el de runs) lo sentencia
    'errored (worker-lost)' / 'errored (worker-lost-restart)' — jamás re-encola (nada se re-ejecuta solo);
  · tres estados (ADR-0043): ausente ≠ null declarado ≠ valor; un usage None es "no medido", nunca 0;
  · kill-switch WITT_COUNCIL=0 (C.9/L.2): start_council_workers lanza CERO hilos y no siega ni toca la BD (el subsistema
    queda congelado: los jobs queued/running preexistentes se DECLARAN en la salida y en stderr, no se mutan);
    worker_loop no reclama; execute_round1 llamado a mano marca el plan 'disabled (kill-switch WITT_COUNCIL=0)' con CERO
    llamadas y CERO eventos `stage.council.*`.

Costuras: C5 (`runs.start_workers`) llama `start_council_workers(n=None)` junto a los `run-worker-N`; si su `_reap_once`
gana la segunda tabla (db.reap_stale_council_plans) llama `start_council_workers(..., reaper=False)` para no segar dos
veces; `runs.stop_workers` puede llamar `stop_council_workers()`. C6 (`app.py`) sólo habla con db.py (E.1). C9 mide con
smoke_council_jobs_db.py (17 miembros FAKEADOS, urlopen bloqueado = 0).
"""
import datetime
import json
import os
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import council_index  # noqa: E402  (ADR-0082 I: prior observations de r1; sin ciclo — no importa council_jobs ni runs)
import db  # noqa: E402
from lib import agent_matrix, catalog_cards, council, models  # noqa: E402

MODULE_VERSION = "council-jobs-1"
WORKER_THREAD_PREFIX = "council-worker-"
REAPER_THREAD_NAME = "council-reaper"
REAP_STALE_S_DEFAULT = 900             # == runs.REAP_STALE_S_DEFAULT (ADR-0078): el MISMO umbral siega jobs de plan
REAP_STALE_S_ENV = "WITT_REAP_STALE_S"
WORKERS_ENV = "WITT_COUNCIL_WORKERS"
ORIGINS_ENV = "WITT_COUNCIL_ORIGINS"
ORIGINS_ALL = "all"
STATE_DISABLED = "disabled (kill-switch WITT_COUNCIL=0)"      # ∈ council.COUNCIL_STATES_EXACT
STATE_RUNNING = "running"
PERSIST_RULE = ("plans.council_json + council_usage_json rewritten after EVERY collected member (stage.council.member "
                "phase done, orchestrator thread); the final write replaces the partial rounds[0] with the full "
                "RoundResult + aggregation (ADR-0082 E.2; LOTE-01·A4 applied to the plan)")
ORIGINS_RULE = ("claim only plans whose origin is in WITT_COUNCIL_ORIGINS (CSV; 'all' = no filter): smoke/fixture/dev-"
                "offline plans stay queued in a production process (Context 9)")
KILL_SWITCH_RULE = ("WITT_COUNCIL=0: zero council-worker threads, zero claims, zero council calls, zero DB writes from "
                    "this module; pre-existing queued/running jobs are declared, not mutated (ADR-0082 C.9/L.2)")

assert STATE_DISABLED in council.COUNCIL_STATES_EXACT
assert STATE_RUNNING in council.COUNCIL_STATES_EXACT

_STOP = threading.Event()
_BOOT_ID = uuid.uuid4().hex[:8]


# ── env (lectores tolerantes, una env un default) ─────────────────────────────────────────────────────────────────

def _env_int_tolerante(name, default, env=None):
    """(valor, fuente) — la MISMA regla que runs._env_int_tolerante (ADR-0078): env vacía / no numérica / <= 0 → default
    DECLARADO. Sólo para WITT_REAP_STALE_S, que no está en models.ENV_TABLE."""
    env = os.environ if env is None else env
    raw = (env.get(name) or "").strip()
    if not raw:
        return default, f"default-unset:{name}"
    try:
        v = int(raw)
    except ValueError:
        return default, f"default-invalid-env:{name}"
    return (v, f"env:{name}") if v > 0 else (default, f"default-invalid-env:{name}")


def reap_stale_s_of(env=None):
    """(segundos, fuente) del umbral del segador — WITT_REAP_STALE_S, el mismo de runs.reaper_loop."""
    return _env_int_tolerante(REAP_STALE_S_ENV, REAP_STALE_S_DEFAULT, env)


def council_workers_n(env=None):
    """(n, fuente) de hilos council-worker — WITT_COUNCIL_WORKERS vía models.env_value (int ≥ 0; basura → default 1)."""
    v, src = models.env_value(WORKERS_ENV, env)
    return int(v), src


def council_origins(env=None):
    """(lista | None, fuente): los orígenes de PLAN que este proceso reclama — WITT_COUNCIL_ORIGINS (CSV tolerante,
    default 'production'); 'all' → None = sin filtro DECLARADO. Un origen fuera de db.RUN_ORIGINS se conserva tal cual
    (no casa con ningún plan y se declara en la fuente)."""
    raw, src = models.env_value(ORIGINS_ENV, env)
    items = [x.strip() for x in str(raw or "").split(",") if x.strip()]
    if not items:
        return ["production"], f"{src} (empty → production)"
    if any(x.lower() == ORIGINS_ALL for x in items):
        return None, f"{src} ('all' → no filter)"
    unknown = [x for x in items if x not in db.RUN_ORIGINS]
    if unknown:
        src = f"{src} (not in db.RUN_ORIGINS, declared: {unknown})"
    return items, src


# ── identidad del worker ──────────────────────────────────────────────────────────────────────────────────────────

def boot_id():
    """La identidad del PROCESO en council_claimed_by: la de runs.WORKER_BOOT_ID cuando runs ya está cargado (el app lo
    carga siempre → un solo boot_id por proceso, correlacionable con runs.claimed_by), la propia si no (smokes aislados).
    sys.modules.get: no dispara el import de runs (evita el ciclo runs.start_workers → council_jobs → runs)."""
    runs_mod = sys.modules.get("runs")
    bid = getattr(runs_mod, "WORKER_BOOT_ID", None) if runs_mod is not None else None
    return bid or _BOOT_ID


def worker_id_for(thread_name):
    """'<boot_id>:<pid>:<hilo>' (<= 64 chars) — el patrón de runs.worker_id_for (ADR-0078 corrector)."""
    return f"{boot_id()}:{os.getpid()}:{thread_name}"[:64]


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(dt):
    return dt.isoformat(timespec="seconds") if isinstance(dt, datetime.datetime) else dt


def _json_or_none(s):
    if not s:
        return None
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return None


def _errored_state(exc):
    """'errored (<Tipo>)' acotado a la columna (VARCHAR(40)): 'errored (' + tipo[:30] + ')'."""
    return f"errored ({type(exc).__name__[:30]})"


# ── insumos de la ronda 1 (sólo lectura; nada de esto es evidencia) ───────────────────────────────────────────────

def _prior_observations(question, entities, env):
    """(I) council_index.prior_observations — PRIOR ART para el user message de r1 (letras P-A…, sin `comment` por
    default). NUNCA lanza: un índice que truena → 'errored (…)' declarado y el job sigue (§6 no-hang). Devuelve el sobre
    del índice o uno mínimo {state, items[], n, kinds[]}."""
    try:
        out = council_index.prior_observations(question, entities=entities, env=env)
        if not isinstance(out, dict):
            return {"state": "errored (prior_observations returned non-dict)", "items": [], "n": 0, "kinds": []}
        out.setdefault("items", [])
        out.setdefault("n", len(out["items"]))
        out.setdefault("kinds", [])
        out.setdefault("state", "delivered" if out["items"] else "empty-corpus")
        return out
    except Exception as e:  # noqa: BLE001
        return {"state": f"errored ({type(e).__name__}: {str(e)[:120]})", "items": [], "n": 0, "kinds": []}


def _inherited_criteria(plan):
    """(G.9) Los criterios heredados del turno anterior: `council_summary` del registro congelado del PADRE
    (plan_json.thread_parent_run_id → runs.frozen_record_json.council → council.summary_for_thread). Sólo lectura;
    None declarado (con `state`) cuando no hay padre, no hay registro o el padre no tuvo consejo."""
    parent = (plan or {}).get("thread_parent_run_id") if isinstance(plan, dict) else None
    if not parent:
        return None, "not-applicable (root turn: no parent)"
    try:
        row = db.get_run(parent)
    except Exception as e:  # noqa: BLE001
        return None, f"errored (db.get_run: {type(e).__name__})"
    if row is None:
        return None, f"not-available (parent {parent} not found)"
    frozen = _json_or_none(row.get("frozen_record_json"))
    if not isinstance(frozen, dict):
        return None, f"not-available (parent {parent} without frozen record)"
    try:
        summ = council.summary_for_thread(frozen.get("council"))
    except Exception as e:  # noqa: BLE001
        return None, f"errored (summary_for_thread: {type(e).__name__})"
    if summ is None:
        return None, f"not-available (parent {parent} without council block)"
    return {"source": f"thread_context.council_summary (parent run {parent})", **summ}, "delivered"


# ── el caller que MIDE lo que cada miembro gastó (para la persistencia incremental) ───────────────────────────────

class _CapturingCaller:
    """Envuelve al caller real (o fake) para capturar, por miembro, usage/meta del intento final — o CallerError.usage /
    .meta cuando falló — desde el hilo del pool, bajo lock; el hilo ORQUESTADOR lo lee en el evento 'done' (take). La
    excepción se relanza tal cual: run_round la clasifica (fila errored con kind). No cambia el contrato del caller."""

    def __init__(self, inner):
        self.inner = inner
        self._lock = threading.Lock()
        self._seen = {}
        self.n_calls = 0

    def __call__(self, request):
        agent = request.get("agent") if isinstance(request, dict) else None
        with self._lock:
            self.n_calls += 1
        try:
            res = self.inner(request)
        except BaseException as e:  # noqa: BLE001 — se captura lo medible y se RELANZA
            with self._lock:
                self._seen[agent] = {"usage": getattr(e, "usage", None), "meta": getattr(e, "meta", None),
                                     "error": f"{type(e).__name__}: {e}"[:300]}
            raise
        usage, meta = None, {}
        if isinstance(res, tuple) and len(res) >= 2:
            usage = res[1]
            if len(res) >= 3 and isinstance(res[2], dict):
                meta = res[2]
        with self._lock:
            self._seen[agent] = {"usage": usage, "meta": meta, "error": None}
        return res

    def take(self, agent):
        with self._lock:
            return self._seen.get(agent)


def _usage_from_capture(cap):
    """usage de la fila parcial = TODOS los intentos (respuesta final o CallerError.usage + meta.usage_prior_attempts) —
    la MISMA suma que council._member_usage aplica en la fila final; None = nada medido."""
    if not cap:
        return None
    err = None
    if cap.get("error") is not None:
        class _E:  # portador mínimo para reutilizar la regla de council._member_usage
            pass
        err = _E()
        err.usage = cap.get("usage")
        err.meta = cap.get("meta")
        return council._member_usage(None, None, err=err)
    return council._member_usage(cap.get("usage"), cap.get("meta"))


def _usage_summary(rows, model, model_source, state):
    """council_usage_json: {round 'r1', model, model_source, in, out, cache_creation, cache_read, thinking_tokens?,
    n_members_measured, n_calls, by_model {m: {in, out, cache_creation, cache_read}}, state, class 'medicion',
    written_at} — la forma que GET /usage.plans_council lee (in|input_tokens…, by_model). Sólo enteros medidos; un
    miembro sin usage NO suma (ausente ≠ 0)."""
    tot = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    thinking = None
    by_model, n_meas, n_calls = {}, 0, 0
    for r in rows:
        n_calls += int(r.get("attempts") or 0)
        u = r.get("usage")
        if not isinstance(u, dict):
            continue
        n_meas += 1
        m = r.get("model_reported") or model or "_unattributed"
        bm = by_model.setdefault(m, {"in": 0, "out": 0, "cache_creation": 0, "cache_read": 0})
        for k, short in (("input_tokens", "in"), ("output_tokens", "out"),
                         ("cache_creation_input_tokens", "cache_creation"), ("cache_read_input_tokens", "cache_read")):
            v = u.get(k)
            if isinstance(v, int) and not isinstance(v, bool):
                tot[k] += v
                bm[short] += v
        if isinstance(u.get("thinking_tokens"), int):
            thinking = (thinking or 0) + u["thinking_tokens"]
    out = {"round": "r1", "model": model, "model_source": model_source,
           "in": tot["input_tokens"], "out": tot["output_tokens"],
           "cache_creation": tot["cache_creation_input_tokens"], "cache_read": tot["cache_read_input_tokens"],
           "n_members_measured": n_meas, "n_calls": n_calls, "by_model": by_model,
           "state": state, "class": "medicion", "written_at": _iso(_now())}
    if thinking is not None:
        out["thinking_tokens"] = thinking
    return out


class _IncrementalPersister:
    """Lo que el worker escribe en plans.council_json / council_usage_json tras CADA miembro recogido y al cerrar. Las
    filas parciales nacen del payload 'done' (agent, tool, status, error_kind, elapsed_s, attempts) + lo capturado del
    caller (usage, model_reported); la escritura final las reemplaza por el RoundResult íntegro + la agregación."""

    def __init__(self, plan_id, members, base):
        self.plan_id = plan_id
        self.members = list(members)
        self.base = base
        self.rows = {}
        self.n_writes = 0
        self.conflict = None            # corrector ADR-0082 (E.2): el cierre perdió contra el reaper → {attempted, found, …}
        self.last_error = None

    def member_done(self, payload, cap):
        agent = payload.get("agent")
        card = catalog_cards.card(agent) if agent else None
        row = {"agent": agent, "round": "r1", "tool": payload.get("tool"), "status": payload.get("status"),
               "error_kind": payload.get("error_kind"), "error": (cap or {}).get("error"),
               "elapsed_s": payload.get("elapsed_s"), "attempts": payload.get("attempts"),
               "usage": _usage_from_capture(cap), "model_reported": ((cap or {}).get("meta") or {}).get("model_reported"),
               "card_sha": card["sha"] if card else None,
               "source": "incremental (stage.council.member phase done; orchestrator thread)"}
        if payload.get("status") in ("timeout",):
            row["late_usage_state"] = "unrecoverable (thread abandoned; provider bills up to max_tokens)"
        self.rows[agent] = row
        self.write_partial()

    def partial_round(self, state=None):
        rows = [self.rows[a] for a in self.members if a in self.rows]
        n_valid = sum(1 for r in rows if r["status"] in ("ok", "not-applicable"))
        return {"round": "r1", "kind": council.ROUND_KIND_OF["r1"], "phase": "plan",
                "state": state or f"running (partial: {len(rows)} of {len(self.members)} members collected)",
                "n_members": len(self.members), "members_order": list(self.members), "members": rows,
                "n_collected": len(rows), "n_valid": n_valid,
                "n_errored": sum(1 for r in rows if r["status"] == "errored"),
                "n_timeout": sum(1 for r in rows if r["status"] == "timeout"),
                "usage": {k: v for k, v in _usage_summary(rows, self.base["model"]["requested"],
                                                          self.base["model"]["source"], "partial").items()
                          if k in ("in", "out", "cache_creation", "cache_read", "thinking_tokens", "n_members_measured")},
                "persisted_at": _iso(_now())}

    def compose(self, round_result=None, aggregation=None, state=None, error=None):
        cj = dict(self.base)
        cj["jobs_module_version"] = MODULE_VERSION
        if round_result is not None:
            cj["rounds"] = [round_result]
            cj["state"] = state or (aggregation or {}).get("state") or round_result.get("state")
        else:
            cj["rounds"] = [self.partial_round()]
            cj["state"] = state or STATE_RUNNING
        if aggregation is not None:
            cj["aggregation"] = aggregation
            cj["requirements"] = aggregation["requirements"]
            cj["flags"] = aggregation["flags"]
            cj["notes_for_human"] = aggregation["notes_for_human"]
            cj["not_applicable_members"] = aggregation["not_applicable_members"]
            for k in ("n_requirements", "n_must", "n_should", "n_hard_rule", "n_exploratory", "n_from_operative",
                      "n_unsatisfiable", "n_flags", "truncated", "n_truncated", "truncated_ids", "n_raw", "n_dedup",
                      "aggregation_sha", "entities_resolution_state"):
                cj[k] = aggregation[k]
            cj["n_valid"] = aggregation["n_valid"]
        else:
            cj["aggregation"] = None
            cj["requirements"] = []
            cj["flags"] = []
            cj["aggregation_sha"] = None
            cj["n_requirements"] = None          # no medido todavía (ausente ≠ 0)
        cj["persisted"] = {"state": ("final" if round_result is not None else
                                     f"partial ({len(self.rows)} of {len(self.members)} members collected)"),
                           "n_members_persisted": (len(round_result["members"]) if round_result is not None else len(self.rows)),
                           "n_writes": self.n_writes + 1, "written_at": _iso(_now()), "rule": PERSIST_RULE}
        if error is not None:
            cj["error"] = error
        return cj

    def write_partial(self):
        rows = [self.rows[a] for a in self.members if a in self.rows]
        cj = self.compose()
        usage = _usage_summary(rows, self.base["model"]["requested"], self.base["model"]["source"],
                               f"partial ({len(rows)} of {len(self.members)} members collected)")
        db.update_plan_council(self.plan_id, council_json=json.dumps(cj, ensure_ascii=False, default=str),
                               council_usage_json=json.dumps(usage, ensure_ascii=False, default=str))
        self.n_writes += 1

    def _close(self, state, cj, usage, **terminal):
        """corrector ADR-0082 (E.2): cierre CONDICIONAL a council_state == 'running' (patrón db.finish_run / runs._finish,
        ADR-0078). rowcount 0 = el reaper ya sentenció 'errored (worker-lost[-restart])' (o el humano saltó) mientras este
        hilo seguía vivo — p. ej. solape de contenedores en un redeploy: NO se pisa el veredicto terminal (antes ganaba el
        último y el plan tenía dos veredictos). Lo GASTADO (council_json / council_usage_json) SÍ se conserva porque es
        medición, y queda UN evento council.state.conflict {attempted, found, found_error, ignored True}. Devuelve True si
        el cierre se escribió."""
        cj_s = json.dumps(cj, ensure_ascii=False, default=str)
        us_s = json.dumps(usage, ensure_ascii=False, default=str)
        ok = db.update_plan_council(self.plan_id, expected_state=STATE_RUNNING, council_state=state,
                                    council_json=cj_s, council_usage_json=us_s, **terminal)
        self.n_writes += 1
        if ok:
            self.conflict = None
            return True
        row = db.get_plan(self.plan_id) or {}
        db.update_plan_council(self.plan_id, council_json=cj_s, council_usage_json=us_s)   # lo gastado es medición
        self.n_writes += 1
        self.conflict = {"attempted": state, "found": row.get("council_state"), "found_error": row.get("council_error"),
                         "ignored": True, "note": "finished-after-reap: the worker outlived the reaper's verdict; the terminal "
                                                  "state is NOT overwritten (council_json/usage preserved — measured spend)"}
        db.plan_add_event(self.plan_id, "council.state.conflict",
                          payload={**self.conflict, "plan_id": self.plan_id, "claimed_by": self.base.get("claimed_by")},
                          agent="council", level="warning")
        return False

    def write_final(self, round_result, aggregation, state, finished_at):
        cj = self.compose(round_result, aggregation, state)
        usage = _usage_summary(round_result["members"], self.base["model"]["requested"], self.base["model"]["source"],
                               "measured (round closed)")
        written = self._close(state, cj, usage, council_finished_at=finished_at, council_error=None)
        return cj, usage, written

    def write_errored(self, state, error, finished_at):
        rows = [self.rows[a] for a in self.members if a in self.rows]
        cj = self.compose(state=state, error=error)
        usage = _usage_summary(rows, self.base["model"]["requested"], self.base["model"]["source"],
                               f"partial ({len(rows)} of {len(self.members)} members collected; worker errored)")
        written = self._close(state, cj, usage, council_finished_at=finished_at, council_error=error)
        return cj, usage, written


# ── el job: una ronda 1 sobre un plan reclamado ───────────────────────────────────────────────────────────────────

def execute_round1(plan_row, caller=None, env=None, on_event=None, clock=None, cfg=None, resolver=None,
                   payload_for=None, prior=None, inherited=None):
    """ADR-0082 (E.2): ejecuta la RONDA 1 sobre un plan YA reclamado (fila de db.claim_next_council_plan) y persiste.
    Inyectables (smokes, cero red): `caller(request) -> (tool_input, usage, meta)`; `clock`; `payload_for`; `resolver`
    (entidades, default resolve_id.resolve — DATA INAMOVIBLE sólo lectura); `prior` (sobre de prior observations; None →
    council_index) e `inherited` (criterios heredados; None → del padre). `on_event(type, payload)` se llama DESPUÉS de
    persistir y de escribir el evento en plan_events (hilo orquestador).

    Escribe: council.state {running} → stage.council.member/progress/round (los de run_round, tal cual) →
    stage.council.aggregate → council.state {applicable | incomplete}; plans.council_json / council_usage_json tras cada
    miembro (parcial) y al cerrar (final); council_finished_at. Una excepción → 'errored (<Tipo>)' + council_error +
    lo persistido hasta ahí (NO relanza: el hilo sigue). BaseException (KeyboardInterrupt/SystemExit: el proceso muere)
    sube tal cual y el plan queda 'running' para el reaper. Con kill-switch → 'disabled (kill-switch WITT_COUNCIL=0)',
    cero llamadas, cero eventos stage.council.*. Devuelve un resumen {plan_id, state, n_members, n_valid, n_invoked,
    n_calls, n_requirements, elapsed_s, error?}."""
    env = os.environ if env is None else env
    plan_id = plan_row["plan_id"]
    claimed_by = plan_row.get("council_claimed_by")
    t0 = time.monotonic()
    enabled, en_src = council.enabled(env)
    if not enabled:
        ahora = _now()
        db.update_plan_council(plan_id, council_state=STATE_DISABLED, council_finished_at=ahora, council_error=None)
        db.plan_add_event(plan_id, "council.state",
                          payload={"state": STATE_DISABLED, "plan_id": plan_id, "claimed_by": claimed_by,
                                   "reason": f"kill-switch ({en_src}); no council call was made", "rule": KILL_SWITCH_RULE},
                          agent="council")
        return {"plan_id": plan_id, "state": STATE_DISABLED, "n_members": None, "n_valid": None, "n_invoked": 0,
                "n_calls": 0, "n_requirements": None, "elapsed_s": round(time.monotonic() - t0, 3)}

    cfg = cfg or council.config(env)
    full, full_src = agent_matrix.council_full(env)
    members = agent_matrix.council_members(env)
    mres = council.resolve_council_model(env, cfg)
    plan = _json_or_none(plan_row.get("plan_json")) or {}
    question = plan_row.get("question")
    entities = [e for e in (plan_row.get("entities_csv") or "").split(",") if e]
    base = {
        "module_version": council.MODULE_VERSION, "membership_version": council.MEMBERSHIP_VERSION,
        "council_version": council.COUNCIL_VERSION, "matrix_version": agent_matrix.MATRIX_VERSION,
        "plan_id": plan_id, "claimed_by": claimed_by,
        "n_members": len(members), "members": list(members), "full_council": bool(full), "full_council_source": full_src,
        "catalog_sha": catalog_cards.CATALOG_SHA, "catalog_state": catalog_cards.CATALOG_STATE,
        "rules_sha": council.RULES_SHA, "tools_sha": council.TOOLS_SHA, "shared_block_sha": council.SHARED_BLOCK_SHA,
        "model": {"requested": mres["model"], "source": mres["source"], "generation": mres["generation"],
                  "effort": mres["effort_sent"], "effort_source": mres["effort_sent_source"],
                  "max_tokens": mres["max_tokens"]},
        "cache": {"enabled": cfg["cache"]["enabled"], "ttl": cfg["cache"]["ttl_card"],
                  "ttl_shared": cfg["cache"]["ttl_shared"], "min_cacheable_tokens": council.MIN_CACHEABLE_TOKENS},
        "budget": {"member_timeout_s": cfg["member_timeout_s"], "round_budget_s": cfg["budget_s"],
                   "concurrency": cfg["concurrency"], "quorum": cfg["quorum"],
                   "quorum_required": council.quorum_required(len(members), cfg["quorum"])},
        "prior_observations": None, "inherited_criteria_state": None,
        "source": "council_jobs.execute_round1 (worker; council.run_round r1 + council.aggregate_r1)",
    }
    persister = _IncrementalPersister(plan_id, members, base)
    capt = _CapturingCaller(caller or council.default_caller)
    try:
        prior_obs = prior if prior is not None else _prior_observations(question, entities, env)
        inherited_val, inherited_state = (inherited, "injected") if inherited is not None else _inherited_criteria(plan)
        base["prior_observations"] = {"n": prior_obs.get("n", len(prior_obs.get("items") or [])),
                                      "kinds": list(prior_obs.get("kinds") or []), "state": prior_obs.get("state"),
                                      "scorer": prior_obs.get("scorer"), "class": "prior-art"}
        base["inherited_criteria_state"] = inherited_state
        ctx = {"question": question, "entities": entities, "judgment": plan.get("judgment"),
               "prior_observations": prior_obs.get("items") or [], "prior_observations_state": prior_obs.get("state"),
               "inherited_criteria": inherited_val, "human_attestations": None, "phase": "plan"}
        db.plan_add_event(plan_id, "council.state",
                          payload={"state": STATE_RUNNING, "plan_id": plan_id, "claimed_by": claimed_by,
                                   "n_members": len(members), "full_council": bool(full),
                                   "membership_version": council.MEMBERSHIP_VERSION,
                                   "catalog_sha": catalog_cards.CATALOG_SHA, "model": base["model"],
                                   "prior_observations": base["prior_observations"],
                                   "inherited_criteria_state": inherited_state, "reason": None},
                          agent="council")

        def _emit(etype, payload):
            if etype == "stage.council.member" and (payload or {}).get("phase") == "done":
                persister.member_done(payload, capt.take(payload.get("agent")))
            db.plan_add_event(plan_id, etype, payload=payload, agent="council", tool=(payload or {}).get("tool"))
            if on_event is not None:
                on_event(etype, payload)

        rr = council.run_round(members, "r1", ctx, caller=capt, on_event=_emit, cfg=cfg, env=env, clock=clock,
                               payload_for=payload_for, phase="plan")
        rr["prior_observations"] = base["prior_observations"]
        agg = council.aggregate_r1(rr, members=members, cfg=cfg, resolver=resolver)
        state = agg["state"]
        ahora = _now()
        cj, usage, written = persister.write_final(rr, agg, state, ahora)
        db.plan_add_event(plan_id, "stage.council.aggregate",
                          payload={"n_raw": agg["n_raw"], "n_dedup": agg["n_dedup"], "n_requirements": agg["n_requirements"],
                                   "n_must": agg["n_must"], "n_should": agg["n_should"], "n_truncated": agg["n_truncated"],
                                   "n_unsatisfiable": agg["n_unsatisfiable"], "n_hard_rule": agg["n_hard_rule"],
                                   "n_flags": agg["n_flags"], "n_valid": agg["n_valid"], "n_members": agg["n_members"],
                                   "catalog_sha": agg["catalog_sha"], "aggregation_sha": agg["aggregation_sha"],
                                   "state": state, "decided_by": agg["decided_by"]},
                          agent="council")
        if written:   # corrector ADR-0082 (E.2): si el reaper ya sentenció, el evento terminal es council.state.conflict, no éste
            db.plan_add_event(plan_id, "council.state",
                              payload={"state": state, "plan_id": plan_id, "claimed_by": claimed_by,
                                       "n_valid": rr["n_valid"], "n_members": rr["n_members"], "quorum": rr["quorum"],
                                       "n_requirements": agg["n_requirements"], "n_hard_rule": agg["n_hard_rule"],
                                       "elapsed_s": rr["elapsed_s"], "usage": {k: usage[k] for k in ("in", "out", "cache_creation", "cache_read")},
                                       "reason": None},
                              agent="council")
        return {"plan_id": plan_id, "state": state, "state_written": written, "conflict": persister.conflict,
                "n_members": rr["n_members"], "n_valid": rr["n_valid"],
                "n_invoked": rr["n_invoked"], "n_calls": capt.n_calls, "n_requirements": agg["n_requirements"],
                "aggregation_sha": agg["aggregation_sha"], "n_writes": persister.n_writes,
                "elapsed_s": round(time.monotonic() - t0, 3)}
    except Exception as e:  # noqa: BLE001 — el hilo NO cae; el plan queda errored con lo persistido hasta aquí
        state = _errored_state(e)
        error = f"{type(e).__name__}: {e}"[:1500]
        print(f"[council_jobs] plan {plan_id}: ronda 1 errored → {state}: {error[:200]}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        try:
            _cj, _usage, written = persister.write_errored(state, error, _now())
            if written:   # corrector ADR-0082 (E.2): cierre condicional — tras la siega sólo queda council.state.conflict
                db.plan_add_event(plan_id, "council.state",
                                  payload={"state": state, "plan_id": plan_id, "claimed_by": claimed_by, "error": error,
                                           "reason": "worker exception (execute_round1)",
                                           "n_members_persisted": len(persister.rows)},
                                  agent="council", level="error")
        except Exception as e2:  # noqa: BLE001 — la BD también falló: huella en stderr; el reaper lo verá 'running'
            print(f"[council_jobs] plan {plan_id}: no se pudo persistir el error ({type(e2).__name__}: {e2})",
                  file=sys.stderr)
        return {"plan_id": plan_id, "state": state, "state_written": persister.conflict is None, "conflict": persister.conflict,
                "error": error, "n_members": len(members),
                "n_valid": None, "n_invoked": None, "n_calls": capt.n_calls, "n_requirements": None,
                "n_writes": persister.n_writes, "elapsed_s": round(time.monotonic() - t0, 3)}


# ── worker, reaper y arranque ─────────────────────────────────────────────────────────────────────────────────────

def worker_loop(poll_seconds=1.0, caller=None, env=None, stop=None, max_jobs=None, job_kwargs=None):
    """Hilo `council-worker-<i>` (patrón runs.worker_loop): reclama (db.claim_next_council_plan, FIFO, sólo
    origin ∈ WITT_COUNCIL_ORIGINS) y ejecuta execute_round1; sin trabajo, duerme poll_seconds. Bajo kill-switch NO
    reclama. Un fallo de la BD al reclamar o un error no persistido deja huella en stderr y el hilo sigue (§6 no-hang).
    `stop` (Event), `max_jobs` (termina tras N jobs) y `job_kwargs` (→ execute_round1: resolver=, prior=, inherited=,
    clock=, cfg=) son para smokes/gates; default _STOP global. Devuelve n jobs."""
    stop = _STOP if stop is None else stop
    worker_id = worker_id_for(threading.current_thread().name)
    n = 0
    while not stop.is_set():
        enabled, _ = council.enabled(env)
        if not enabled:
            stop.wait(poll_seconds)
            continue
        origins, _ = council_origins(env)
        try:
            row = db.claim_next_council_plan(worker_id, origins=origins)
        except Exception as e:  # noqa: BLE001
            print(f"[council_jobs] {worker_id}: claim falló ({type(e).__name__}: {str(e)[:160]}) — se reintenta",
                  file=sys.stderr)
            stop.wait(poll_seconds)
            continue
        if row is None:
            if max_jobs is not None and n >= max_jobs:
                return n
            stop.wait(poll_seconds)
            continue
        try:
            execute_round1(row, caller=caller, env=env, **(job_kwargs or {}))
        except Exception as e:  # noqa: BLE001 — execute_round1 ya persiste; último cinturón
            print(f"[council_jobs] {worker_id}: execute_round1 lanzó ({type(e).__name__}: {str(e)[:160]})",
                  file=sys.stderr)
        n += 1
        if max_jobs is not None and n >= max_jobs:
            return n
    return n


def reap_once(stale_s, label, reason="worker-lost", env=None):
    """Una pasada del segador de jobs de plan (db.reap_stale_council_plans). Su fallo NO tumba el hilo ni el arranque
    (§6 no-hang): huella en stderr y se reintenta en la siguiente ronda. Devuelve los plan_id segados."""
    _, src = reap_stale_s_of(env)
    try:
        segados = db.reap_stale_council_plans(stale_s, reason=reason, stale_s_source=src)
        if segados:
            print(f"[council_jobs.reaper] {label}: {len(segados)} job(s) de ronda 1 running "
                  + ("sin worker en este proceso" if reason == "worker-lost-restart" else f"sin latido por >{stale_s}s")
                  + f" -> errored ({reason}) (ADR-0082 E.2): {segados}", file=sys.stderr)
        return segados
    except Exception as e:  # noqa: BLE001
        print(f"[council_jobs.reaper] {label}: reap_stale_council_plans falló ({type(e).__name__}: {str(e)[:160]}) — "
              "se reintenta en la siguiente ronda", file=sys.stderr)
        return []


def reaper_loop(stale_s=None, stop=None, env=None):
    """Hilo daemon `council-reaper`: reap_once cada stale_s/3 s (tres oportunidades por umbral, patrón
    runs.reaper_loop). Termina con `stop` (default _STOP)."""
    stop = _STOP if stop is None else stop
    stale_s = reap_stale_s_of(env)[0] if stale_s is None else stale_s
    period = max(1.0, float(stale_s) / 3.0)
    while not stop.wait(period):
        reap_once(stale_s, "ronda", env=env)


def _orphans(env=None):
    """Jobs preexistentes que este proceso NO va a atender (declarados, no mutados): {queued, running}."""
    try:
        return {"queued": db.count_plans_council(states=("queued",)),
                "running": db.count_plans_council(states=("running",))}
    except Exception as e:  # noqa: BLE001
        return {"queued": None, "running": None, "error": f"{type(e).__name__}"}


def start_council_workers(n=None, reap_stale_s=None, env=None, caller=None, reaper=True, poll_seconds=1.0,
                          job_kwargs=None):
    """ADR-0082 (E.2): lo que runs.start_workers (C5) llama junto a los run-worker-N. Con WITT_COUNCIL=1: siega al
    arranque con umbral 0 ('worker-lost-restart': con --workers 1 TODO job 'running' al nacer el proceso es huérfano por
    construcción, ADR-0078), lanza `n` hilos daemon council-worker-<i> (default WITT_COUNCIL_WORKERS) y, con
    `reaper=True`, un hilo `council-reaper` con WITT_REAP_STALE_S (C5 pasa reaper=False si su _reap_once ya gana la
    segunda tabla). Con WITT_COUNCIL=0: CERO hilos, CERO escrituras (ni siega): el subsistema queda congelado y los
    jobs preexistentes se DECLARAN en `orphans` y en stderr (KILL_SWITCH_RULE). Devuelve la declaración del arranque."""
    env_read = os.environ if env is None else env
    enabled, en_src = council.enabled(env_read)
    n_env, n_src = council_workers_n(env_read)
    n_workers = n_env if n is None else int(n)
    stale_s, stale_src = (reap_stale_s_of(env_read) if reap_stale_s is None else (float(reap_stale_s), "param"))
    origins, o_src = council_origins(env_read)
    out = {"module_version": MODULE_VERSION, "boot_id": boot_id(), "enabled": enabled, "enabled_source": en_src,
           "n_workers": 0, "n_workers_source": (n_src if n is None else "param"), "threads": [], "reaper": False,
           "reap_stale_s": stale_s, "reap_stale_s_source": stale_src, "origins": origins, "origins_source": o_src,
           "origins_rule": ORIGINS_RULE, "reaped_at_boot": [], "orphans": None, "rule": KILL_SWITCH_RULE}
    if not enabled:
        out["orphans"] = _orphans(env_read)
        print(f"[council_jobs] arranque: kill-switch ({en_src}) — 0 council-worker, sin siega; jobs preexistentes "
              f"declarados: {out['orphans']}", file=sys.stderr)
        return out
    out["reaped_at_boot"] = reap_once(0.0, "arranque", reason="worker-lost-restart", env=env_read)
    for i in range(n_workers):
        name = f"{WORKER_THREAD_PREFIX}{i}"
        threading.Thread(target=worker_loop, kwargs={"poll_seconds": poll_seconds, "caller": caller, "env": env,
                                                     "job_kwargs": job_kwargs},
                         name=name, daemon=True).start()
        out["threads"].append(name)
    out["n_workers"] = n_workers
    if reaper:
        threading.Thread(target=reaper_loop, kwargs={"stale_s": stale_s, "env": env}, name=REAPER_THREAD_NAME,
                         daemon=True).start()
        out["reaper"] = True
        out["threads"].append(REAPER_THREAD_NAME)
    print(f"[council_jobs] arranque: {n_workers} council-worker ({out['n_workers_source']}); origins={origins} "
          f"({o_src}); REAP_STALE_S={stale_s} ({stale_src}); reaper={'propio' if reaper else 'runs._reap_once'}; "
          f"boot_id={out['boot_id']}", file=sys.stderr)
    return out


def stop_council_workers():
    _STOP.set()


def status():
    """Hilos vivos de este módulo (por nombre) + identidad del proceso — para /health y smokes."""
    alive = [t.name for t in threading.enumerate()
             if t.name.startswith(WORKER_THREAD_PREFIX) or t.name == REAPER_THREAD_NAME]
    return {"module_version": MODULE_VERSION, "boot_id": boot_id(), "stop_set": _STOP.is_set(), "threads_alive": alive}

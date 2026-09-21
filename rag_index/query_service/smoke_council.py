"""smoke_council.py — gate determinista de la rebanada C2 de ADR-0082 (C.1–C.9): el consejo de criterio como CÓDIGO.

Qué MIDE (todo offline; los 17 miembros son FAKES inyectados por `caller`; cero red, cero modelo, cero BD):
  (1) 17 fakes ok → cuórum (11/17), ronda `applicable`, agregado ≤ 24 requisitos;
  (2) misma familia con tokens permutados ×4 → UN requisito `n_requested_by 4`, `variants` 3, `query_en` del 1º por tabla;
  (3) 7 requisitos de un miembro → 5 + `n_dropped_over_cap 2`; 16×5 distintos → `truncated`, 24 kept;
  (4) CallerError http-529 → fila `errored` con kind, la ronda sigue; (5) miembro lento > timeout → fila `timeout`, abandonado
  y contado; (6) 8/17 caídos → `incomplete`; (7) `source_family 'pubmed-central'` → `off_vocabulary`, ítem descartado;
  (8) `direct_answer`/`confidence` en la salida → `dropped_fields` + `prohibited_fields_seen`, no viajan;
  (9) regulatory-ethics con requisitos → `wrong-tool`; causal-pruner → `hard_rule_gate True`; (10) cross-field must → should +
  `priority_downgraded_from`; (11) `web`/`figure` → `unsatisfiable-by-harness`, `n_unsatisfiable`; (12) agregar BARAJADO → JSON
  byte-idéntico, mismos ids y sha; (13) r2: `PMID:999` ∉ bundle → voto anulado + `hallucinated_evidence_ids`; todos anulados →
  `not-judged` → cuenta como must sin cubrir; id ajeno → `foreign`; (14) covered+partial → partial (worst-of);
  (15) `system == [A+§7, ficha]` y sha256(bloque B) == CARDS[agent].sha ×17; (16) el fake recibe `tools` byte-idéntico en
  r1/r2/r3 y `tool_choice` distinto; (17) `cache_control` ×2 con CACHE=1, string con 0, ttl 1h por env (A también 1h: regla
  "1h antes de 5m"); (18) `usage` con `cache_*` sobrevive por miembro y por ronda; (19) test estático de los tools;
  (20) full-council 25 + `from_operative`; (21) escalonado: el #1 arranca y TERMINA antes de que arranque el #2;
  (22) presupuesto 0.3 s con el #1 lento → `skipped-budget` sin llamadas + `abandoned_threads 1`; (23) `cancel_check` a mitad →
  `skipped-cancelled` + usage de los recogidos + RoundCancelled / excepción propia relanzada; (24) eventos `on_event` emitidos
  en el hilo llamador (id de hilo medido) + latido `progress`; (25) `directives_from` sin `search_directive` → directiva desde el
  requisito; con él → `refined_by_members`; (26) `coverage_after_search` → retrieved-for / still-uncovered / not-searched /
  covered-pre; (27) `council_vocabulary()` == tuplas congeladas; ledger (F.1) por código; `summary_for_thread`; env tolerante;
  `urlopen` REAL bloqueado y contado = 0; `openai` jamás importado.
  ADR-0084 (W6 — F.1/F.2/F.4): (11) bajo off (máscara sin BRAVE_API_KEY) `harness_state_for('web','web')` == literal de 7d9ce15
  byte-idéntico al golden `fixtures/golden_plan_web_directive_7d9ce15.json` e importado de `search_harness.WEB_UNSATISFIABLE_LITERAL`;
  (11b) `env` con llave fake → 'satisfiable'; `WITT_WEB_LOCATOR=brave|anthropic` sin llave → literal con causa; `off` explícito con
  llave → literal exacto; (11c) `aggregate_r1` con llave fake en os.environ → la directiva web nace `satisfiable`, `n_unsatisfiable 1`,
  la llave JAMÁS en el agregado; (25d) `directives_from` RECOMPUTA el harness_state de la familia web al compilar: guardado
  'unsatisfiable' + llave → directiva `compiled` con `query_en` y `harness_state_at_plan/at_compile/recomputed True`; sin llave →
  `excluded-unsatisfiable` sin llaves de recomputo (iguales); guardado 'satisfiable' + off → excluida con `recomputed True`; familia
  estática conserva el guardado byte a byte; (26b) `coverage_after_search(…, web_locator=)` → `web_locator {n_queries, n_results,
  n_located, n_materialized, n_unresolved}` SÓLO en el requisito web (también desde `rounds[].sources[web]`), 0 URLs/títulos en la
  salida; sin web la forma es la de 1.12 byte a byte.

Corre (máscara offline):
  WITT_BACKEND_DB_URL="sqlite:///C:/Users/Emmanuel/AppData/Local/Temp/claude/witt-smokes/adr82-smoke_council.db"
  NEO4J_URI="" RAG_BACKEND=sparse OPENAI_API_KEY="" ANTHROPIC_API_KEY="" WITT_RUN_ORIGIN=smoke
  python rag_index/query_service/smoke_council.py
"""
import hashlib
import inspect
import json
import os
import random
import re
import sys
import threading
import time
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
for _k in list(os.environ):
    if _k.startswith("WITT_COUNCIL") or _k in ("WITT_MODEL_COUNCIL", "WITT_CG_COUNCIL_COMPONENT", "WITT_ANTHROPIC_MAX_INFLIGHT",
                                                "WITT_ANTHROPIC_RETRY_AFTER_CAP_S", "WITT_ANTHROPIC_EFFORT",
                                                "WITT_MODEL_GENERATION"):
        os.environ.pop(_k, None)

_NET_CALLS = []


def _blocked_urlopen(*a, **k):
    _NET_CALLS.append(getattr(a[0], "full_url", repr(a[0])) if a else repr(k))
    raise AssertionError("smoke: urllib.request.urlopen bloqueado (cero red)")


urllib.request.urlopen = _blocked_urlopen

from lib import agent_matrix, catalog_cards, council, models  # noqa: E402
from lib import composite_auditor as ca  # noqa: E402
from lib import search_harness as sh  # noqa: E402
from lib import web_locator as wl  # noqa: E402
# ADR-0084 (L / W0): la vara del literal de exclusión grabada EN 7d9ce15 antes de la primera línea de la obra
GOLDEN_W0 = json.loads((ROOT / "rag_index" / "query_service" / "fixtures" / "golden_plan_web_directive_7d9ce15.json")
                       .read_text(encoding="utf-8"))
FAKE_BRAVE_KEY = "smoke-fake-brave-key-never-sent-0084"      # sólo PRESENCIA: provider_state jamás la lee ni la envía

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


def _sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


MEMBERS = agent_matrix.council_members({})
FULL = agent_matrix.council_members({}, full=True)
REG = "regulatory-ethics-advisor"
CP = "causal-pruner"
XF = "cross-field-bridge-agent"
MAIN_THREAD = threading.get_ident()
ENV0 = {}                                   # env vacía = defaults declarados
COUNCIL_MODEL = models.resolve_role("council", {})["model"]   # de la TABLA: ningún literal de modelo aquí (gate M.4)
CFG = council.config(ENV0, heartbeat_s=0.05, model=COUNCIL_MODEL, model_source="smoke")
REPORTED = COUNCIL_MODEL + "-20260901"
CTX_R1 = {"question": "¿wt1a marca el pronefros a 24 hpf?", "entities": ["wt1a", "pax2a"],
          "judgment": {"work_type": "evidence", "route": "evidence-run", "niches": ["N3"], "clarifying_questions": [],
                       "state": "declared"},
          "prior_observations": [], "phase": "plan"}


def req(gap, family="zfin", kind="phenotype", query="wt1a pronephros expression 24 hpf", entities=("wt1a",),
        priority="must", acc="a ZFIN phenotype/expression record for wt1a at 24 hpf"):
    return {"gap": gap, "evidence_kind": kind, "source_family": family, "query_en": query, "entities": list(entities),
            "acceptance_test": acc, "priority": priority}


def default_output(agent, i=0):
    """Salida VÁLIDA por miembro: 1 requisito propio + (para los 4 primeros de MEMBERS) el requisito común permutado."""
    if agent == REG:
        return {"applicable": True, "flags": [{"kind": "compliance", "statement": "zebrafish work under IACUC protocol"}]}
    items = [req(f"{agent} needs {i}", query=f"{agent} specific query {i} pronephros", entities=("pax2a",),
                 priority="must" if agent in (CP, "sim-orchestrator") else "should", family="europepmc", kind="paper")]
    perms = ["wt1a pronephros expression 24 hpf", "pronephros wt1a 24 hpf expression", "expression 24 hpf wt1a pronephros",
             "24 hpf expression pronephros wt1a"]
    k = MEMBERS.index(agent) if agent in MEMBERS else -1
    if 0 <= k < 4:
        items.append(req("is wt1a expressed in the pronephros at 24 hpf", query=perms[k]))
    return {"applicable": True, "requirements": items}


def usage_for(n_call):
    return {"input_tokens": 1200, "output_tokens": 300,
            "cache_creation_input_tokens": 2400 if n_call == 0 else 0,
            "cache_read_input_tokens": 0 if n_call == 0 else 2400,
            "thinking_tokens": 120}


class Fake:
    """caller(request) → (tool_input, usage, meta) según `plan[agent]`: ('ok', out) | ('raise', exc) | ('slow', event, out) |
    callable(request) → out. Registra cada request (tools/tool_choice/system) y los tiempos start/end por agente."""

    def __init__(self, plan=None, round_="r1", ledger=None, judge=None):
        self.plan = plan or {}
        self.calls = []
        self.times = {}
        self.round = round_
        self.ledger = ledger
        self.judge = judge
        self._lock = threading.Lock()

    def __call__(self, request):
        a = request["agent"]
        with self._lock:
            n = len(self.calls)
            self.calls.append(request)
            self.times.setdefault(a, {})["start"] = time.monotonic()
        try:
            spec = self.plan.get(a)
            if spec is None:
                if request["round"] == "r1":
                    out = default_output(a, n)
                else:
                    out = self.judge(a, request) if self.judge else {"judgments": []}
            elif callable(spec):
                out = spec(request)
            elif spec[0] == "raise":
                raise spec[1]
            elif spec[0] == "slow":
                spec[1].wait(10)
                out = spec[2] if len(spec) > 2 else default_output(a, n)
            else:
                out = spec[1]
            return out, usage_for(n), {"model_reported": REPORTED, "attempts": 1, "queue_wait_s": 0.0, "api": "anthropic-messages"}
        finally:
            with self._lock:
                self.times[a]["end"] = time.monotonic()


def run(fake, members=MEMBERS, round_="r1", ctx=None, cfg=None, **kw):
    events = []
    threads = set()

    def on_event(t, p):
        threads.add(threading.get_ident())
        events.append((t, p))
    res = council.run_round(members, round_, ctx or CTX_R1, caller=fake, on_event=on_event, cfg=cfg or CFG, env=ENV0, **kw)
    return res, events, threads


# =====================================================================================================================
# (19) test ESTÁTICO de los tools + (27) vocabularios + re-exports
# =====================================================================================================================
st = council.tools_static_check()
check("(19) test estático: 3 tools en orden fijo, ningún campo prohibido en ningún input_schema, evidence_ids SIN enum, sin strict",
      st["ok"] and st["names"] == ("emit_information_requirements", "emit_flags", "emit_coverage_judgment")
      and st["prohibited_found"] == [] and st["evidence_ids_has_enum"] is False and st["strict_present"] is False, str(st))
check("(C.2) COUNCIL_EVIDENCE_KINDS = nombres de SEARCH_DISPATCH ∪ figure (13) y COUNCIL_SOURCE_FAMILIES = sorted(SEARCH_DISPATCH) (15); "
      "los enums del tool son ESOS",
      council.COUNCIL_EVIDENCE_KINDS == ('dataset', 'expression', 'figure', 'gene-phenotype-association', 'homology', 'interaction',
                                         'oa-location', 'ortholog', 'paper', 'pathway', 'phenotype', 'protein-record', 'web')
      and len(council.COUNCIL_SOURCE_FAMILIES) == 15 and "web" in council.COUNCIL_SOURCE_FAMILIES
      and council.REQ_TOOL["input_schema"]["properties"]["requirements"]["items"]["properties"]["evidence_kind"]["enum"] == list(council.COUNCIL_EVIDENCE_KINDS)
      and council.REQ_TOOL["input_schema"]["properties"]["requirements"]["items"]["properties"]["source_family"]["enum"] == list(council.COUNCIL_SOURCE_FAMILIES))
check("(C.1) re-exports: COUNCIL_FIXED_BLOCK/COUNCIL_RULES/RULES_SHA/build_system/system_sha/cache_config/PROHIBITED_OUTPUT_FIELDS son los de catalog_cards; "
      "COUNCIL_VERSION 'cm-1' == agent_matrix.MEMBERSHIP_VERSION; MODULE_VERSION 'council-1'; TOOLS_SHA = sha256 del JSON canónico",
      council.COUNCIL_FIXED_BLOCK is catalog_cards.COUNCIL_FIXED_BLOCK and council.RULES_SHA == catalog_cards.RULES_SHA
      and council.build_system is catalog_cards.build_system and council.PROHIBITED_OUTPUT_FIELDS == catalog_cards.PROHIBITED_OUTPUT_FIELDS
      and council.COUNCIL_VERSION == "cm-1" == agent_matrix.MEMBERSHIP_VERSION and council.MODULE_VERSION == "council-1"
      and council.TOOLS_SHA == _sha(json.dumps(list(council.TOOLS), sort_keys=True, ensure_ascii=False, separators=(",", ":"))))
voc = council.council_vocabulary()
check("(27) corrector (H/gate F): council_vocabulary() gana usage_stage_states {exact 5 (incl. 'measured (partial: round cancelled)'), "
      "prefixes ['not-run (']} — ÚNICA fuente de token_usage.by_stage.council_r*.state — y quorum_rule",
      voc["usage_stage_states"] == {"exact": ["measured", "measured (partial: round cancelled)", "copied-from-plan_json",
                                              "plan-without-council", "kill-switch WITT_COUNCIL=0"], "prefixes": ["not-run ("]}
      and voc["quorum_rule"] == council.QUORUM_SOURCE and council.USAGE_STAGE_STATES_EXACT[1] == "measured (partial: round cancelled)")
check("(27) council_vocabulary(): coverage_states 6 · decision_states 4 · directive_states 3 · member_states 7 · round_kinds 3 · "
      "decided_by_prefixes 3 · council_states exactos 8 + prefijos 2; predicados por exacto+prefijo",
      voc["coverage_states"] == ["covered", "partial", "uncovered", "not-judged", "covered-by-attestation", "discarded"]
      and voc["decision_states"] == ["keep", "discard", "aporto", "pending"]
      and voc["directive_states"] == ["compiled", "excluded-unknown-family", "excluded-unsatisfiable"]
      and voc["member_states"] == ["ok", "not-applicable", "errored", "timeout", "skipped-budget", "skipped-cancelled", "not-invoked"]
      and voc["round_kinds"] == ["requirements", "coverage", "recoverage"]
      and voc["decided_by_prefixes"] == ["human:", "default-keep", "gate-human-pending"]
      and len(voc["council_states"]["exact"]) == 8 and voc["council_states"]["prefixes"] == ["errored (", "not-requested ("]
      and council.council_state_in_vocabulary("errored (worker-lost)") and council.council_state_in_vocabulary("queued")
      and not council.council_state_in_vocabulary("errored (") and not council.council_state_in_vocabulary("bogus")
      and voc["member_error_kinds"]["caller_exact"] == list(ca.FAILURE_KINDS_EXACT))

# =====================================================================================================================
# env tolerante + kill-switch + modelo/effort (D.2 vía models cuando C3 está)
# =====================================================================================================================
ec = council.env_config({"WITT_COUNCIL_CONCURRENCY": "abc", "WITT_COUNCIL_QUORUM": "1.7", "WITT_COUNCIL_CACHE_TTL": "2h",
                         "WITT_COUNCIL_MEMBER_TIMEOUT_S": "", "WITT_COUNCIL_MAX_REQUIREMENTS": "12"})
check("env_config: 27 env; basura → default DECLARADO con fuente (CONCURRENCY 'abc' → 6; QUORUM 1.7 → 0.6; CACHE_TTL '2h' → 5m; "
      "TIMEOUT '' → 120); válida → valor con fuente env (MAX_REQUIREMENTS 12)",
      len(ec) == 27 and ec["WITT_COUNCIL_CONCURRENCY"]["value"] == 6 and "default" in ec["WITT_COUNCIL_CONCURRENCY"]["source"]
      and abs(ec["WITT_COUNCIL_QUORUM"]["value"] - 0.6) < 1e-9 and "default" in ec["WITT_COUNCIL_QUORUM"]["source"]
      and ec["WITT_COUNCIL_CACHE_TTL"]["value"] == "5m" and ec["WITT_COUNCIL_MEMBER_TIMEOUT_S"]["value"] == 120
      and ec["WITT_COUNCIL_MAX_REQUIREMENTS"]["value"] == 12 and "env" in ec["WITT_COUNCIL_MAX_REQUIREMENTS"]["source"],
      json.dumps({k: ec[k] for k in ("WITT_COUNCIL_CONCURRENCY", "WITT_COUNCIL_QUORUM")}))
check("(C.9) enabled(): default True con fuente; '0'/'false'/'off' → False; basura → True declarado",
      council.enabled({}) [0] is True and council.enabled({"WITT_COUNCIL": "0"})[0] is False
      and council.enabled({"WITT_COUNCIL": "off"})[0] is False and council.enabled({"WITT_COUNCIL": "maybe"})[0] is True
      and "default" in council.enabled({"WITT_COUNCIL": "maybe"})[1])
check("quorum_required: ceil(0.6·17) = 11, ceil(0.6·25) = 15; cfg quorum default 0.6", council.quorum_required(17) == 11
      and council.quorum_required(25) == 15 and council.quorum_required(17, 0.5) == 9 and abs(CFG["quorum"] - 0.6) < 1e-9)
mres = council.resolve_council_model(ENV0, council.config(ENV0))
mres_low = council.resolve_council_model({"WITT_COUNCIL_EFFORT": "low"}, council.config({"WITT_COUNCIL_EFFORT": "low"}))
mres_bad = council.resolve_council_model({"WITT_COUNCIL_EFFORT": "turbo"}, council.config({"WITT_COUNCIL_EFFORT": "turbo"}))
check("(D.2) resolve_council_model: sin literal de modelo aquí — el rol 'council' sale de models (o se declara not-available); "
      "effort default 'medium' con fuente; 'low' por env; basura → 'medium' declarado; effort_sent sólo a modelos adaptive",
      (mres["model"] is None and mres["source"].startswith("not-available")) or (mres["model"] and mres["source"])
      and mres["effort"] == "medium" and mres_low["effort"] == "low" and mres_bad["effort"] == "medium"
      and (mres["effort_sent"] in (None, "medium")), json.dumps(mres))

# =====================================================================================================================
# (15)(16)(17) system/tools/cache por miembro — puro, sin red
# =====================================================================================================================
ok15 = True
for a in MEMBERS:
    r = council.build_request(a, "r1", CTX_R1, CFG, ENV0)
    s = r["system"]
    ok15 = ok15 and isinstance(s, list) and len(s) == 2 and s[0]["text"] == catalog_cards.SHARED_BLOCK_TEXT \
        and s[0]["text"] == catalog_cards.COUNCIL_FIXED_BLOCK + "\n\n" + catalog_cards.COUNCIL_RULES \
        and _sha(s[1]["text"]) == catalog_cards.CARDS[a]["sha"] == r["card_sha"] and r["system_sha"] == council.system_sha(s) \
        and r["tools"] == list(council.TOOLS) and r["tool_choice"] == {"type": "tool", "name": r["tool"]}
check("(15) build_request ×17: system == [bloque A (FIXED + §7), ficha VERBATIM]; sha256(bloque B) == CARDS[agent].sha == card_sha; "
      "system_sha congelado; tools = los TRES; tool_choice forzado", ok15)
r_cp = council.build_request(CP, "r1", CTX_R1, CFG, ENV0)
r_reg = council.build_request(REG, "r1", CTX_R1, CFG, ENV0)
check("(16) tool_for por tabla: causal-pruner r1 → emit_information_requirements; regulatory-ethics-advisor r1 → emit_flags; "
      "todos r2/r3 → emit_coverage_judgment; tools byte-idénticos entre rondas (TOOLS_SHA)",
      r_cp["tool"] == "emit_information_requirements" and r_reg["tool"] == "emit_flags"
      and council.tool_for(agent_matrix.council_member(REG), "r2") == "emit_coverage_judgment"
      and council.tool_for(agent_matrix.council_member(CP), "r3") == "emit_coverage_judgment"
      and r_cp["tools_sha"] == r_reg["tools_sha"] == council.TOOLS_SHA)
cfg_nc = council.config({"WITT_COUNCIL_CACHE": "0"}, model=COUNCIL_MODEL)
r_nc = council.build_request(CP, "r1", CTX_R1, cfg_nc, {"WITT_COUNCIL_CACHE": "0"})
cfg_1h = council.config({"WITT_COUNCIL_CACHE_TTL": "1h"}, model=COUNCIL_MODEL)
r_1h = council.build_request(CP, "r1", CTX_R1, cfg_1h, {"WITT_COUNCIL_CACHE_TTL": "1h"})
check("(17) cache_control ×2 con CACHE=1 ({type ephemeral} = 5m); con CACHE=0 el system es el STRING A+'\\n\\n'+B; con TTL=1h ambos "
      "bloques llevan ttl '1h' (regla API: una entrada 1h antes que las 5m — el A hereda 1h, declarado en CACHE_TTL_RULE)",
      r_cp["system"][0]["cache_control"] == {"type": "ephemeral"} and r_cp["system"][1]["cache_control"] == {"type": "ephemeral"}
      and isinstance(r_nc["system"], str) and r_nc["system"] == catalog_cards.SHARED_BLOCK_TEXT + "\n\n" + catalog_cards.CARDS[CP]["text_verbatim"]
      and r_1h["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
      and r_1h["system"][1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"} and r_1h["cache"]["ttl_shared"] == "1h")
check("(C.1) lo VOLÁTIL va en el user message: pregunta, entidades y juicio del plan están en user_text y NO en el system; "
      "el bloque FIJO no contiene la pregunta ni fechas (las reglas §7 literales sí citan fechas de sesión: son texto de CLAUDE.md)",
      "wt1a marca el pronefros" in r_cp["user_text"] and "pax2a" in r_cp["user_text"] and "evidence-run" in r_cp["user_text"]
      and "wt1a marca" not in json.dumps(r_cp["system"]) and "2026" not in catalog_cards.COUNCIL_FIXED_BLOCK
      and "20" not in catalog_cards.COUNCIL_FIXED_BLOCK.replace("Absence", ""))
try:
    council.build_request("html-report-emitter", "r1", CTX_R1, CFG, ENV0)
    e_nim = None
except ValueError as e:
    e_nim = e
try:
    council.build_request("no-such-agent", "r1", CTX_R1, CFG, ENV0)
    e_nsa = None
except ValueError as e:
    e_nsa = e
check("build_request: agente fuera de la membresía → ValueError('not-in-membership: …') (sustrato y desconocidos)",
      e_nim is not None and str(e_nim).startswith("not-in-membership") and e_nsa is not None and str(e_nsa).startswith("not-in-membership"))

# =====================================================================================================================
# (1)(2)(9)(10)(11)(18)(21)(24) ronda 1 con 17 fakes válidos
# =====================================================================================================================
plan1 = {
    XF: ("ok", {"applicable": True, "requirements": [
        req("cross-field: optical clearing of pronephros analog", family="openalex", kind="paper",
            query="optical clearing kidney organoid imaging", entities=(), priority="must")]}),
    "literature-monitor": ("ok", {"applicable": True, "requirements": [
        req("web-only demand", family="web", kind="web", query="latest preprints pronephros wt1a", entities=("wt1a",)),
        req("figure demand", family="zfin", kind="figure", query="wt1a in situ figure 24 hpf", entities=("wt1a",)),
        req("lit", family="europepmc", kind="paper", query="wt1a pronephros literature", entities=("wt1a",), priority="should")]}),
}
f1 = Fake(plan1)
res1, ev1, thr1 = run(f1)
rows1 = {r["agent"]: r for r in res1["members"]}
check("(1) 17 fakes ok → state 'applicable', n_valid 17 ≥ quorum.required 11, n_invoked 17, n_errored 0, sin abandonados, "
      "cache_prefix_identical_across_members True, model.requested del cfg, relation 'prefix' (reported es snapshot)",
      res1["state"] == "applicable" and res1["n_valid"] == 17 and res1["quorum"] == {**res1["quorum"], "required": 11, "met": True}
      and res1["n_invoked"] == 17 and res1["n_errored"] == 0 and res1["abandoned_threads"] == 0
      and res1["cache_prefix_identical_across_members"] is True and res1["model"]["requested"] == COUNCIL_MODEL
      and all(r["relation"] == "prefix" and r["model_reported"] == REPORTED for r in res1["members"]),
      f"state={res1['state']} n_valid={res1['n_valid']} quorum={res1['quorum']}")
check("(18) usage por miembro conserva cache_creation/cache_read/thinking_tokens; usage de ronda: in 17×1200, cache_creation 2400 (sólo el #1), "
      "cache_read 16×2400, thinking 17×120, n_members_measured 17",
      res1["usage"] == {"in": 17 * 1200, "out": 17 * 300, "cache_creation": 2400, "cache_read": 16 * 2400, "n_members_measured": 17,
                        "thinking_tokens": 17 * 120}
      and rows1[MEMBERS[1]]["usage"]["cache_read_input_tokens"] == 2400 and rows1[MEMBERS[0]]["usage"]["cache_creation_input_tokens"] == 2400,
      json.dumps(res1["usage"]))
first = MEMBERS[0]
t_first_end = f1.times[first]["end"]
others_start = min(f1.times[a]["start"] for a in MEMBERS if a != first)
check("(21) escalonado: el miembro #1 (causal-pruner, primero de la tabla) arranca y TERMINA antes de que arranque cualquier otro; "
      "stagger_wait_s medido; stagger_first = {agent, status ok}",
      f1.calls[0]["agent"] == first and t_first_end <= others_start and res1["stagger_wait_s"] is not None
      and res1["stagger_first"] == {"agent": first, "status": "ok"})
check("(16) el fake recibió `tools` byte-idénticos en las 17 llamadas y tool_choice = su tool (emit_flags sólo para regulatory-ethics)",
      all(c["tools"] == list(council.TOOLS) for c in f1.calls)
      and {c["tool_choice"]["name"] for c in f1.calls if c["agent"] != REG} == {"emit_information_requirements"}
      and next(c for c in f1.calls if c["agent"] == REG)["tool_choice"] == {"type": "tool", "name": "emit_flags"})
types1 = [t for t, _ in ev1]
check("(24) eventos: TODOS emitidos desde el hilo llamador (id medido); stage.council.member start/done ×17 cada uno; "
      "stage.council.round al cerrar con n_valid/quorum/state; events.emitted_from 'orchestrator-thread'",
      thr1 == {MAIN_THREAD} and types1.count("stage.council.member") == 34 and types1[-1] == "stage.council.round"
      and ev1[-1][1]["n_valid"] == 17 and ev1[-1][1]["state"] == "applicable" and ev1[-1][1]["quorum"]["required"] == 11
      and sum(1 for t, p in ev1 if t == "stage.council.member" and p["phase"] == "start") == 17
      and sum(1 for t, p in ev1 if t == "stage.council.member" and p["phase"] == "done" and p["status"] == "ok") == 17
      and res1["events"]["emitted_from"] == "orchestrator-thread" and all(p.get("heartbeat") is True for _, p in ev1))

agg1 = council.aggregate_r1(res1, MEMBERS, CFG, resolver=lambda e: "ENSDARG00000000000" if e == "wt1a" else None)
by_id1 = {r["requirement_id"]: r for r in agg1["requirements"]}
common = [r for r in agg1["requirements"] if r["gap"] == "is wt1a expressed in the pronephros at 24 hpf"]
check("(2) misma familia/kind con tokens PERMUTADOS ×4 → UN requisito: n_requested_by 4 (pedido por 4 de 17: n_members 17 al lado), "
      "variants 3 (las otras 3 frases), query_en del PRIMER emisor por tabla (causal-pruner), requested_by en orden de tabla",
      len(common) == 1 and common[0]["n_requested_by"] == 4 and common[0]["n_members"] == 17 and len(common[0]["variants"]) == 3
      and common[0]["query_en"] == "wt1a pronephros expression 24 hpf" and common[0]["requested_by"] == MEMBERS[:4]
      and common[0]["requirement_id"] == council.requirement_id("zfin", "phenotype", "24 hpf expression pronephros wt1a", ["wt1a"]),
      json.dumps(common[0] if common else agg1["n_requirements"]))
check("(9) causal-pruner → requisito con hard_rule_gate True (aunque otros 3 también lo pidieron); su requisito propio también; "
      "n_hard_rule ≥ 2; regulatory-ethics → flags[] con gate 'human' y emitted_by, n_flags 1",
      common and common[0]["hard_rule_gate"] is True and agg1["n_hard_rule"] >= 2
      and agg1["flags"] == [{"kind": "compliance", "statement": "zebrafish work under IACUC protocol", "gate": "human", "emitted_by": [REG]}]
      and agg1["n_flags"] == 1)
xf_req = [r for r in agg1["requirements"] if XF in r["requested_by"] and r["gap"].startswith("cross-field")]
check("(10) cross-field-bridge-agent SOLO emisor con must → priority 'should' + priority_downgraded_from 'must' + razón §7; exploratory True; "
      "el requisito común (4 emisores, ninguno exploratorio) sigue must sin downgrade",
      len(xf_req) == 1 and xf_req[0]["priority"] == "should" and xf_req[0]["priority_downgraded_from"] == "must"
      and xf_req[0]["exploratory"] is True and "Test 5" in xf_req[0]["priority_downgrade_reason"]
      and common[0]["priority"] == "must" and "priority_downgraded_from" not in common[0] and common[0]["exploratory"] is False)
uns = [r for r in agg1["requirements"] if r["harness_state"] != "satisfiable"]
check("(11) bajo off DERIVADO (máscara: BRAVE_API_KEY vacía, WITT_WEB_LOCATOR unset) source_family 'web' → el literal de 7d9ce15 "
      "'unsatisfiable-by-harness (tool-unavailable (ADR-0084))' == search_harness.WEB_UNSATISFIABLE_LITERAL == golden W0 (byte a byte); "
      "evidence_kind 'figure' → 'unsatisfiable-by-harness (evidence_kind figure — ADR-0083)'; n_unsatisfiable 2; europepmc (tool_module "
      "None pero fn) SÍ es satisfiable; tooluniverse sigue unsatisfiable (ADR-0085)",
      os.environ.get("BRAVE_API_KEY", "") == "" and not os.environ.get("WITT_WEB_LOCATOR")
      and agg1["n_unsatisfiable"] == 2 and {r["harness_state"] for r in uns} == {sh.WEB_UNSATISFIABLE_LITERAL,
                                                                                  "unsatisfiable-by-harness (evidence_kind figure — ADR-0083)"}
      and sh.WEB_UNSATISFIABLE_LITERAL == "unsatisfiable-by-harness (tool-unavailable (ADR-0084))" == GOLDEN_W0["harness_state_web"]
      and council.harness_state_for("web", "web") == GOLDEN_W0["harness_state_web"]
      and council.harness_state_for("europepmc", "paper") == "satisfiable"
      and council.harness_state_for("tooluniverse", "paper") == "unsatisfiable-by-harness (tool-unavailable (ADR-0085))"
      and council.harness_state_for("no-such-family", "paper") == "unsatisfiable-by-harness (unknown-family)"
      and all(council.harness_state_in_vocabulary(r["harness_state"]) for r in agg1["requirements"]),
      json.dumps({r["source_family"]: r["harness_state"] for r in uns}))
HS_BRAVE_NO_KEY = f"{sh.UNSATISFIABLE_PREFIX}{wl.UNAVAILABLE_BRAVE_NO_KEY})"
HS_ANTH_NO_KEY = f"{sh.UNSATISFIABLE_PREFIX}{wl.UNAVAILABLE_ANTHROPIC_NO_KEY})"
check("(11b) ADR-0084 F.1 — harness_state_for DINÁMICA por env (family_available leída en la llamada): llave fake → 'satisfiable'; "
      "WITT_WEB_LOCATOR=brave sin llave → 'unsatisfiable-by-harness (tool-unavailable (ADR-0084: BRAVE_API_KEY unset))'; anthropic sin "
      "llave → '… ANTHROPIC_API_KEY unset)'; off EXPLÍCITO con llave → literal exacto de 7d9ce15; env basura → literal exacto (provider off "
      "derivado); todos en vocabulario por prefijo; figure gana siempre (family web + kind figure → literal 0083)",
      council.harness_state_for("web", "web", env={"BRAVE_API_KEY": FAKE_BRAVE_KEY}) == "satisfiable"
      and council.harness_state_for("web", "web", env={"WITT_WEB_LOCATOR": "brave", "BRAVE_API_KEY": FAKE_BRAVE_KEY}) == "satisfiable"
      and council.harness_state_for("web", "web", env={"WITT_WEB_LOCATOR": "brave"}) == HS_BRAVE_NO_KEY
      == "unsatisfiable-by-harness (tool-unavailable (ADR-0084: BRAVE_API_KEY unset))"
      and council.harness_state_for("web", "web", env={"WITT_WEB_LOCATOR": "anthropic"}) == HS_ANTH_NO_KEY
      and council.harness_state_for("web", "web", env={"WITT_WEB_LOCATOR": "off", "BRAVE_API_KEY": FAKE_BRAVE_KEY}) == sh.WEB_UNSATISFIABLE_LITERAL
      and council.harness_state_for("web", "web", env={"WITT_WEB_LOCATOR": "duckduckgo", "BRAVE_API_KEY": FAKE_BRAVE_KEY}) == sh.WEB_UNSATISFIABLE_LITERAL
      and council.harness_state_for("web", "figure", env={"BRAVE_API_KEY": FAKE_BRAVE_KEY}) == "unsatisfiable-by-harness (evidence_kind figure — ADR-0083)"
      and council.harness_state_for("europepmc", "paper", env={}) == "satisfiable"
      and all(council.harness_state_in_vocabulary(x) for x in (HS_BRAVE_NO_KEY, HS_ANTH_NO_KEY, sh.WEB_UNSATISFIABLE_LITERAL))
      and list(inspect.signature(council.harness_state_for).parameters) == ["source_family", "evidence_kind", "env"])
_prev_brave = os.environ.get("BRAVE_API_KEY")
os.environ["BRAVE_API_KEY"] = FAKE_BRAVE_KEY
try:
    agg_key = council.aggregate_r1(res1, MEMBERS, CFG, resolver=lambda e: "ENSDARG00000000000" if e == "wt1a" else None)
finally:
    if _prev_brave is None:
        os.environ.pop("BRAVE_API_KEY", None)
    else:
        os.environ["BRAVE_API_KEY"] = _prev_brave
web_key = [r for r in agg_key["requirements"] if r["source_family"] == "web"]
check("(11c) ADR-0084 F.1 — aggregate_r1 con BRAVE_API_KEY fake en os.environ (misma ronda 1): el requisito web nace 'satisfiable', "
      "n_unsatisfiable 1 (sólo figure), mismos requirement_id que bajo off (el id no depende del harness_state), aggregation_sha "
      "DISTINTO (el estado viaja), rules.harness_state == HARNESS_STATE_RULE (declara family_available y ADR-0084), la llave fake "
      "JAMÁS en el agregado; tras restaurar la máscara harness_state_for vuelve al literal",
      len(web_key) == 1 and web_key[0]["harness_state"] == "satisfiable" and agg_key["n_unsatisfiable"] == 1
      and [r["requirement_id"] for r in agg_key["requirements"]] == [r["requirement_id"] for r in agg1["requirements"]]
      and agg_key["aggregation_sha"] != agg1["aggregation_sha"]
      and agg_key["rules"]["harness_state"] == council.HARNESS_STATE_RULE == agg1["rules"]["harness_state"]
      and "family_available" in council.HARNESS_STATE_RULE and "ADR-0084" in council.HARNESS_STATE_RULE
      and FAKE_BRAVE_KEY not in json.dumps(agg_key) and FAKE_BRAVE_KEY not in json.dumps(agg1)
      and council.harness_state_for("web", "web") == sh.WEB_UNSATISFIABLE_LITERAL
      and os.environ.get("BRAVE_API_KEY", "") == "")
check("(C.4) entidades por resolver inyectado: wt1a → entities_resolved, pax2a → entities_unresolved (nunca afirmadas); orden must > should, "
      "n_requested_by desc, id asc; n_raw 16×1 + 4 + 2 (xf/lit) = 22 → n_dedup 19; state 'applicable'; aggregation_sha presente",
      common[0]["entities_resolved"] == ["wt1a"] and common[0]["entities_unresolved"] == []
      and all(r["entities_unresolved"] == ["pax2a"] for r in agg1["requirements"] if r["entities"] == ["pax2a"])
      and agg1["requirements"][0]["priority"] == "must" and agg1["requirements"][0]["n_requested_by"] == 4
      and agg1["n_raw"] == 22 and agg1["n_dedup"] == 19 and agg1["n_requirements"] == 19 and agg1["state"] == "applicable"
      and len(agg1["aggregation_sha"]) == 64 and agg1["truncated"] is False,
      f"n_raw={agg1['n_raw']} n_dedup={agg1['n_dedup']}")

# (12) barajado → byte-idéntico
shuffled = dict(res1)
rows_sh = list(res1["members"])
random.Random(7).shuffle(rows_sh)
shuffled["members"] = rows_sh
agg_sh = council.aggregate_r1(shuffled, MEMBERS, CFG, resolver=lambda e: "ENSDARG00000000000" if e == "wt1a" else None)
check("(12) agregar con las filas BARAJADAS → JSON byte-idéntico, mismos requirement_id, mismo aggregation_sha",
      json.dumps(agg_sh, sort_keys=True) == json.dumps(agg1, sort_keys=True) and agg_sh["aggregation_sha"] == agg1["aggregation_sha"]
      and [r["requirement_id"] for r in agg_sh["requirements"]] == [r["requirement_id"] for r in agg1["requirements"]])
agg_sh2 = council.aggregate_r1(shuffled, list(reversed(MEMBERS)), CFG, resolver=lambda e: None)
check("(12b) el ORDEN de `members` es identidad: con la tabla invertida el requisito común toma la query del nuevo primero y requested_by cambia de orden",
      next(r for r in agg_sh2["requirements"] if r["gap"] == common[0]["gap"])["query_en"] == "24 hpf expression pronephros wt1a"
      and agg_sh2["aggregation_sha"] != agg1["aggregation_sha"])

# =====================================================================================================================
# (3)(7)(8)(9) validación por código
# =====================================================================================================================
seven = {"applicable": True, "requirements": [req(f"g{i}", query=f"query number {i} pronephros") for i in range(7)]}
clean7, rep7 = council.validate_tool_input("sim-orchestrator", "r1", seven, CFG)
check("(3) 7 requisitos → 5 conservados en ORDEN + n_dropped_over_cap 2 (tope WITT_COUNCIL_MAX_PER_MEMBER=5; el schema fija maxItems 5)",
      len(clean7["requirements"]) == 5 and rep7["n_dropped_over_cap"] == 2 and clean7["requirements"][0]["gap"] == "g0"
      and clean7["requirements"][4]["gap"] == "g4" and rep7["kind"] is None
      and council.REQ_TOOL["input_schema"]["properties"]["requirements"]["maxItems"] == 5)
offv = {"applicable": True, "requirements": [req("a", family="pubmed-central"), req("b", kind="text-literature"),
                                             req("c", priority="urgent"), req("d")]}
clean_off, rep_off = council.validate_tool_input("sim-orchestrator", "r1", offv, CFG)
check("(7) enums fuera de vocabulario ('pubmed-central', 'text-literature', 'urgent') → off_vocabulary[] con el valor CRUDO (jamás corregido), "
      "ítem descartado; el válido sobrevive (1 de 4)",
      len(clean_off["requirements"]) == 1 and clean_off["requirements"][0]["gap"] == "d" and len(rep_off["off_vocabulary"]) == 3
      and {o["value"] for o in rep_off["off_vocabulary"]} == {"pubmed-central", "text-literature", "urgent"}
      and len(rep_off["dropped_items"]) == 3)
proh = {"applicable": True, "direct_answer": "wt1a marks the pronephros", "confidence": 0.9, "verdict": "APPROVE",
        "requirements": [{**req("x"), "score": 3, "ranking": 1, "extra": "y"}]}
clean_p, rep_p = council.validate_tool_input("sim-orchestrator", "r1", proh, CFG)
check("(8) direct_answer/confidence/verdict/score/ranking en la salida → dropped_fields + prohibited_fields_seen; NO viajan en clean; "
      "campo desconocido no prohibido ('extra') sólo dropped",
      set(rep_p["prohibited_fields_seen"]) == {"direct_answer", "confidence", "verdict", "0.score", "0.ranking"}
      and "0.extra" in rep_p["dropped_fields"] and "0.extra" not in rep_p["prohibited_fields_seen"]
      and "direct_answer" not in json.dumps(clean_p) and "score" not in clean_p["requirements"][0] and clean_p["requirements"][0]["gap"] == "x")
clean_wt, rep_wt = council.validate_tool_input(REG, "r1", {"applicable": True, "requirements": [req("z")]}, CFG)
clean_wt2, rep_wt2 = council.validate_tool_input("sim-orchestrator", "r1", {"judgments": []}, CFG)
check("(9) regulatory-ethics-advisor emitiendo `requirements` → kind 'wrong-tool' (esperaba emit_flags), clean None; miembro de requisitos "
      "emitiendo `judgments` en r1 → 'wrong-tool'",
      clean_wt is None and rep_wt["kind"] == "wrong-tool" and rep_wt["tool_seen"] == "emit_information_requirements"
      and rep_wt["tool"] == "emit_flags" and clean_wt2 is None and rep_wt2["kind"] == "wrong-tool")
clean_na, rep_na = council.validate_tool_input("sim-orchestrator", "r1", {"applicable": False, "not_applicable_reason": "no sim here"}, CFG)
clean_s, rep_s = council.validate_tool_input("sim-orchestrator", "r1", "just text", CFG)
clean_m, rep_m = council.validate_tool_input("sim-orchestrator", "r1", {}, CFG)
clean_long, rep_long = council.validate_tool_input("sim-orchestrator", "r1", {"applicable": True, "requirements": [req("g" * 400)]}, CFG)
check("validación: applicable False → clean {applicable False, requirements []} (fila not-applicable); salida no-objeto → 'invalid-output'; "
      "{} → 'required-missing:applicable,requirements'; gap de 400 chars → recortado a 300 y declarado en truncated_fields",
      clean_na["applicable"] is False and clean_na["requirements"] == [] and clean_na["not_applicable_reason"] == "no sim here"
      and rep_s["kind"] == "invalid-output" and rep_m["kind"] == "required-missing:applicable,requirements"
      and len(clean_long["requirements"][0]["gap"]) == 300 and rep_long["truncated_fields"] == [{"index": 0, "field": "gap", "chars": 400, "cap": 300}])

# (3b) 16×5 distintos → truncado a 24
plan_many = {a: ("ok", {"applicable": True, "requirements": [req(f"{a} g{i}", query=f"{a} unique query {i}", family="europepmc", kind="paper",
                                                                 priority="must" if i % 2 == 0 else "should") for i in range(5)]})
             for a in MEMBERS if a != REG}
res_many, _, _ = run(Fake(plan_many))
agg_many = council.aggregate_r1(res_many, MEMBERS, CFG, resolver=lambda e: None)
check("(3b) 16×5 = 80 requisitos distintos → n_dedup 80, tope 24: truncated True, n_requirements 24, n_truncated 56, truncated_ids 56, "
      "los 24 son must (48 must > 24) y ordenados por id",
      agg_many["n_dedup"] == 80 and agg_many["truncated"] is True and agg_many["n_requirements"] == 24 and agg_many["n_truncated"] == 56
      and len(agg_many["truncated_ids"]) == 56 and agg_many["n_must"] == 24
      and [r["requirement_id"] for r in agg_many["requirements"]] == sorted(r["requirement_id"] for r in agg_many["requirements"]))

# =====================================================================================================================
# (4)(6) miembros caídos; (20) full-council; not-applicable cuenta como válido
# =====================================================================================================================
plan4 = {"imaging-analyst": ("raise", ca.CallerError("http-529", "HTTP 529: overloaded", retry_after=7,
                                                      meta={"attempts": 2, "api": "anthropic-messages"})),
         "marker-validator": ("raise", ca.CallerError("refusal", "no valid forced tool_use (stop_reason=refusal)",
                                                       usage={"input_tokens": 50, "output_tokens": 0}, meta={"attempts": 1})),
         "histology-reviewer": ("raise", RuntimeError("boom")),
         "scrna-seq-analyst": ("ok", {"applicable": False, "not_applicable_reason": "no single-cell data implicated"})}
res4, ev4, _ = run(Fake(plan4))
rows4 = {r["agent"]: r for r in res4["members"]}
check("(4) CallerError http-529 → fila errored error_kind 'http-529', attempts 2 (del meta del caller), retry_after_s 7 congelado; refusal → errored "
      "con usage MEDIDO (50 in) conservado; RuntimeError ajeno → 'caller-exception'; la ronda SIGUE: n_valid 14 ≥ 11 → applicable",
      rows4["imaging-analyst"]["status"] == "errored" and rows4["imaging-analyst"]["error_kind"] == "http-529"
      and rows4["imaging-analyst"]["attempts"] == 2 and rows4["imaging-analyst"]["retry_after_s"] == 7
      and rows4["marker-validator"]["error_kind"] == "refusal" and rows4["marker-validator"]["usage"] == {"input_tokens": 50, "output_tokens": 0}
      and rows4["histology-reviewer"]["error_kind"] == "caller-exception" and rows4["histology-reviewer"]["error"].startswith("RuntimeError: boom")
      and res4["n_errored"] == 3 and res4["n_valid"] == 14 and res4["state"] == "applicable",
      f"n_valid={res4['n_valid']} errored={res4['n_errored']}")
check("(C.3) un `not-applicable` EMITIDO por el miembro cuenta como válido (respondió): status 'not-applicable', not_applicable_reason, "
      "n_not_applicable 1; el evento member done lleva status 'not-applicable' y error_kind None",
      rows4["scrna-seq-analyst"]["status"] == "not-applicable" and rows4["scrna-seq-analyst"]["not_applicable_reason"] == "no single-cell data implicated"
      and res4["n_not_applicable"] == 1
      and any(t == "stage.council.member" and p["agent"] == "scrna-seq-analyst" and p["phase"] == "done" and p["status"] == "not-applicable"
              and p["error_kind"] is None for t, p in ev4))
agg4 = council.aggregate_r1(res4, MEMBERS, CFG, resolver=lambda e: None)
check("(C.4) el agregado declara not_applicable_members[] con razón y n_valid 14; las filas errored no aportan requisitos",
      agg4["not_applicable_members"] == [{"agent": "scrna-seq-analyst", "reason": "no single-cell data implicated"}] and agg4["n_valid"] == 14
      and not any("imaging-analyst" in r["requested_by"] for r in agg4["requirements"]))
plan6 = {a: ("raise", ca.CallerError("http-529", "HTTP 529")) for a in MEMBERS[3:11]}
res6, ev6, _ = run(Fake(plan6))
check("(6) 8/17 caídos → n_valid 9 < 11 → state 'incomplete', quorum.met False; el evento round lo dice; el agregado hereda 'incomplete'",
      res6["n_errored"] == 8 and res6["n_valid"] == 9 and res6["state"] == "incomplete" and res6["quorum"]["met"] is False
      and ev6[-1][1]["state"] == "incomplete" and council.aggregate_r1(res6, MEMBERS, CFG, resolver=lambda e: None)["state"] == "incomplete")
plan20 = {"budget-tracker": ("ok", {"applicable": True, "requirements": [req("budget wants reagent cost evidence", family="openalex", kind="paper",
                                                                             query="reagent cost pronephros assay", entities=(), priority="should")]})}
cfg_full = council.config({"WITT_COUNCIL_FULL": "1"}, heartbeat_s=0.05, model=COUNCIL_MODEL)
res20, _, _ = run(Fake(plan20), members=FULL, cfg=cfg_full)
agg20 = council.aggregate_r1(res20, FULL, cfg_full, resolver=lambda e: None)
bt = [r for r in agg20["requirements"] if "budget-tracker" in r["requested_by"]]
check("(20) full-council: 25 miembros (los 17 primero, luego los 8 operativos), quorum 15, state applicable; el requisito del operativo lleva "
      "from_operative True; los 8 operativos (fakes por default) emiten → 25 dedup > tope 24 (1 truncado, should) → n_from_operative 7|8, ninguno de los 17 lo lleva; seat 'operative (full-council only)' en su fila",
      res20["n_members"] == 25 and res20["members_order"][:17] == MEMBERS and res20["quorum"]["required"] == 15 and res20["state"] == "applicable"
      and len(bt) == 1 and bt[0]["from_operative"] is True and agg20["n_dedup"] == 25 and agg20["truncated"] is True
      and agg20["n_truncated"] == 1 and agg20["n_from_operative"] in (7, 8) and bt[0]["n_members"] == 25
      and all(r["from_operative"] is False for r in agg20["requirements"] if not (set(r["requested_by"]) & set(agent_matrix.OPERATIVES)))
      and next(r for r in res20["members"] if r["agent"] == "budget-tracker")["seat"] == "operative (full-council only)")

# =====================================================================================================================
# (5)(22)(23)(24b) tiempo: timeout por miembro, presupuesto, cancelación, latido
# =====================================================================================================================
ev_slow = threading.Event()
cfg_t = council.config(ENV0, heartbeat_s=0.05, model=COUNCIL_MODEL)
cfg_t["member_timeout_s"] = 0.25
res5, ev5, _ = run(Fake({"imaging-analyst": ("slow", ev_slow)}), cfg=cfg_t)
ev_slow.set()
r5 = next(r for r in res5["members"] if r["agent"] == "imaging-analyst")
check("(5) miembro lento > WITT_COUNCIL_MEMBER_TIMEOUT_S (0.25 s) → fila 'timeout' error_kind 'timeout', abandoned True, usage None + "
      "late_usage_state declarado; abandoned_threads 1 + abandoned_cost_upper_usd PROYECCIÓN con usd > 0 (modelo cotizado); la ronda SIGUE: "
      "16 válidos → applicable; el evento member done dice timeout",
      r5["status"] == "timeout" and r5["error_kind"] == "timeout" and r5["abandoned"] is True and r5["usage"] is None
      and r5["late_usage_state"].startswith("unrecoverable") and res5["abandoned_threads"] == 1
      and res5["abandoned_cost_upper_usd"]["class"] == "PROJECTION" and res5["abandoned_cost_upper_usd"]["usd"] > 0
      and res5["n_valid"] == 16 and res5["state"] == "applicable" and res5["n_timeout"] == 1
      and any(t == "stage.council.member" and p["agent"] == "imaging-analyst" and p.get("status") == "timeout" for t, p in ev5),
      json.dumps({k: res5[k] for k in ("abandoned_threads", "abandoned_cost_upper_usd", "n_valid")}))
check("(H) abandoned_cost_upper: n=0 → usd 0.0 medido; modelo desconocido → usd None declarado 'not-priced'; regla declarada",
      council.abandoned_cost_upper(0, 0, 4000, COUNCIL_MODEL)["usd"] == 0.0
      and council.abandoned_cost_upper(2, 8000, 4000, "no-such-model")["usd"] is None
      and council.abandoned_cost_upper(2, 8000, 4000, "no-such-model")["state"].startswith("not-priced")
      and council.abandoned_cost_upper(1, 4000, 4000, COUNCIL_MODEL)["assumptions"]["payload_tokens_est"] == 1000)
_ac1 = council.abandoned_cost_upper(1, 4000, 4000, COUNCIL_MODEL)
_ac2 = council.abandoned_cost_upper(1, 4000, 4000, COUNCIL_MODEL, attempts_possible=2)
check("(H) corrector: la cota de abandonados multiplica por los intentos POSIBLES del hilo (retries+1): attempts_possible 2 → usd ×2, "
      "n_calls_upper 2; la ronda (5) la declara con attempts_possible == member_retries+1 == 2",
      _ac2["usd"] == round(_ac1["usd"] * 2, 6) and _ac2["attempts_possible"] == 2 and _ac2["n_calls_upper"] == 2
      and _ac1["attempts_possible"] == 1 and res5["abandoned_cost_upper_usd"]["attempts_possible"] == 2
      and res5["abandoned_cost_upper_usd"]["n_calls_upper"] == 2 and "attempts_possible" in _ac2["rule"])
check("(J) corrector: stage.council.member lleva la MISMA llave `attempt` en phase 'start' y 'done' (done conserva `attempts` = total); "
      "medido en la ronda (5): done ok attempt 1 == attempts 1; el timeout también trae attempt",
      all("attempt" in p and "max_attempts" in p for t, p in ev5 if t == "stage.council.member")
      and all(p["attempt"] == p["attempts"] for t, p in ev5 if t == "stage.council.member" and p["phase"] == "done" and p["status"] == "ok")
      and next(p for t, p in ev5 if t == "stage.council.member" and p.get("status") == "timeout")["attempt"] == 1
      and council.socket_timeout_s({"member_timeout_s": 120, "member_retries": 1}) == 59
      and council.socket_timeout_s({"member_timeout_s": 120, "member_retries": 0}) == 120
      and council.socket_timeout_s({"member_timeout_s": 12, "member_retries": 1}) == 10)

ev_budget = threading.Event()
f22 = Fake({MEMBERS[0]: ("slow", ev_budget)})
cfg_b = council.config(ENV0, heartbeat_s=0.05, model=COUNCIL_MODEL)
cfg_b["member_timeout_s"] = 5            # el presupuesto de RONDA (0.3 s) vence antes que el timeout por miembro
res22, ev22, _ = run(f22, cfg=cfg_b, budget_s=0.3)
ev_budget.set()
check("(22) presupuesto 0.3 s con el #1 lento: el #1 queda 'timeout' abandon_reason 'round-budget' (dispatched), los 16 restantes "
      "'skipped-budget' con CERO llamadas (1 sola llamada al fake), abandoned_threads 1, over_budget True, state incomplete",
      len(f22.calls) == 1 and res22["members"][0]["status"] == "timeout" and res22["members"][0]["abandon_reason"] == "round-budget"
      and res22["n_skipped_budget"] == 16 and all(r["status"] == "skipped-budget" and r["dispatched"] is False for r in res22["members"][1:])
      and res22["abandoned_threads"] == 1 and res22["over_budget"] is True and res22["state"] == "incomplete" and res22["n_invoked"] == 1,
      f"calls={len(f22.calls)} skipped={res22['n_skipped_budget']}")

collected = {"n": 0}
cfg_c = council.config(ENV0, heartbeat_s=0.05, model=COUNCIL_MODEL)
cfg_c["concurrency"] = 1          # un despacho a la vez → la cancelación cae en una frontera medible


def cancel_after_5():
    return collected["n"] >= 5


class F23(Fake):
    def __call__(self, request):
        out = super().__call__(request)
        collected["n"] += 1
        return out


f23 = F23()
events23 = []
try:
    council.run_round(MEMBERS, "r1", CTX_R1, caller=f23, on_event=lambda t, p: events23.append((t, p)), cfg=cfg_c, env=ENV0,
                      cancel_check=cancel_after_5)
    exc23 = None
except council.RoundCancelled as e:
    exc23 = e
res23 = exc23.result if exc23 else None
check("(23) cancel_check verdadero a mitad → RoundCancelled con .result PARCIAL: cancelled True, 5 ok recogidos con usage, resto "
      "'skipped-cancelled' (dispatched False), n_skipped_cancelled 12, usage de los recogidos preservado (5×1200 in), state incomplete",
      exc23 is not None and res23["cancelled"] is True and res23["n_ok"] == 5 and res23["n_skipped_cancelled"] == 12
      and res23["usage"]["in"] == 5 * 1200 and res23["usage"]["n_members_measured"] == 5 and res23["state"] == "incomplete"
      and all(r["dispatched"] is False for r in res23["members"] if r["status"] == "skipped-cancelled")
      and events23[-1][0] == "stage.council.round" and events23[-1][1]["cancelled"] is True,
      f"ok={res23['n_ok'] if res23 else None}")


class MyCancel(Exception):
    pass


def cancel_raises():
    if collected["n"] >= 8:
        raise MyCancel("run cancelled by user")


collected["n"] = 0
try:
    council.run_round(MEMBERS, "r1", CTX_R1, caller=F23(), cfg=cfg_c, env=ENV0, cancel_check=cancel_raises, cancel_exc=(MyCancel,))
    exc23b = None
except MyCancel as e:
    exc23b = e
check("(23b) cancel_check que LANZA la excepción de cancelación DECLARADA (cancel_exc=(MyCancel,); runs pasa RunCancelled) → se "
      "relanza ESA excepción con .council_round_result adjunto (8 ok, resto skipped-cancelled)",
      isinstance(exc23b, MyCancel) and hasattr(exc23b, "council_round_result") and exc23b.council_round_result["cancelled"] is True
      and exc23b.council_round_result["n_ok"] == 8 and exc23b.council_round_result["n_skipped_cancelled"] == 9)


def cancel_check_flaky():
    """corrector ADR-0082 (C.3): un fallo TRANSITORIO de la consulta de cancelación (OSError/OperationalError) NO es una
    cancelación — antes marcaba a los pendientes 'skipped-cancelled' y relanzaba el error."""
    if 2 <= collected["n"] <= 3:
        raise OSError("db hiccup while reading cancel_requested")
    return False


collected["n"] = 0
res23c, ev23c, _ = run(F23(), cfg=cfg_c, cancel_check=cancel_check_flaky)
check("(23c) corrector: cancel_check que LANZA OSError (no es la excepción de cancelación declarada) → la ronda SIGUE completa "
      "(17 ok, cancelled False, 0 skipped-cancelled), el fallo queda MEDIDO en cancel_check_errors[] {kind 'OSError', error, at_s} "
      "y n_cancel_check_errors ≥ 1; el evento round dice cancelled False",
      res23c["cancelled"] is False and res23c["n_ok"] == 17 and res23c["n_skipped_cancelled"] == 0 and res23c["state"] == "applicable"
      and res23c["n_cancel_check_errors"] >= 1 and res23c["cancel_check_errors"][0]["kind"] == "OSError"
      and "db hiccup" in res23c["cancel_check_errors"][0]["error"] and ev23c[-1][1]["cancelled"] is False,
      json.dumps({"errors": res23c["cancel_check_errors"], "n_ok": res23c["n_ok"]}))

ev_hb = threading.Event()
cfg_hb = council.config(ENV0, heartbeat_s=0.02, model=COUNCIL_MODEL)
cfg_hb["member_timeout_s"] = 0.3
res_hb, ev_hb_list, thr_hb = run(Fake({"fitness-curator": ("slow", ev_hb)}), cfg=cfg_hb)
ev_hb.set()
prog = [p for t, p in ev_hb_list if t == "stage.council.progress"]
check("(24b) latido: con un miembro colgado y heartbeat_s 0.02 s se emiten stage.council.progress {n_done, n_pending, elapsed_s, heartbeat True} "
      "desde el hilo llamador; n_pending ≥ 1 mientras cuelga",
      len(prog) >= 1 and all(p["heartbeat"] is True and p["n_pending"] >= 1 and "elapsed_s" in p for p in prog) and thr_hb == {MAIN_THREAD}
      and res_hb["heartbeat_s"] == 0.02, f"progress={len(prog)}")

# =====================================================================================================================
# ledger (F.1) por código → r2 (13)(14) → directivas (25) → after_search (26) → summary (G.9)
# =====================================================================================================================
led_draft = council.apply_ledger_decisions(agg1, decisions=[], approve=True, decided_by="emmanuel", decided_at="2026-09-15T10:00:00Z")
hard_ids = [r["requirement_id"] for r in agg1["requirements"] if r["hard_rule_gate"]]
check("(F.1) approve con hard_rule pendientes → state 'draft', errors.hard_rule_requirements_undecided = ids de causal-pruner, esos quedan "
      "decided_by 'gate-human-pending'; los demás pending → keep 'default-keep' (ningún requisito se descarta solo)",
      led_draft["state"] == "draft" and sorted(led_draft["errors"]["hard_rule_requirements_undecided"]) == sorted(hard_ids) and hard_ids
      and all(r["decided_by"] == "gate-human-pending" and r["decision"] == "pending" for r in led_draft["requirements"] if r["hard_rule_gate"])
      and all(r["decision"] == "keep" and r["decided_by"] == "default-keep" for r in led_draft["requirements"] if not r["hard_rule_gate"]))
bad = council.apply_ledger_decisions(agg1, decisions=[{"requirement_id": "req-nope", "decision": "keep"},
                                                      {"requirement_id": hard_ids[0], "decision": "discard"},
                                                      {"requirement_id": agg1["requirements"][-1]["requirement_id"], "decision": "aporto"}])
check("(F.1) unknown_requirement_id / discard_without_reason / aporto_without_text → errors por lista, has_errors True, nada aplicado",
      bad["errors"]["unknown_requirement_id"] == ["req-nope"] and bad["errors"]["discard_without_reason"] == [hard_ids[0]]
      and bad["errors"]["aporto_without_text"] == [agg1["requirements"][-1]["requirement_id"]] and bad["has_errors"] is True)
lit_web = next(r["requirement_id"] for r in agg1["requirements"] if r["source_family"] == "web")
aporto_id = next(r["requirement_id"] for r in agg1["requirements"] if r["gap"].startswith("domain-knowledge-curator needs"))
decisions = [{"requirement_id": h, "decision": "keep"} for h in hard_ids]
decisions += [{"requirement_id": lit_web, "decision": "discard", "reason": "harness cannot reach the web (ADR-0084)"},
              {"requirement_id": aporto_id, "decision": "aporto", "attested_text": "Emmanuel: the 2025 review PMID:40000001 covers this. " * 120}]
ledger = council.apply_ledger_decisions(agg1, decisions=decisions, approve=True, decided_by="emmanuel", decided_at="2026-09-15T10:05:00Z",
                                        knowledge_now="wt1a is a known podocyte marker in our hands", attestation_chars=4000)
check("(F.1) ledger aprobado: state 'approved', approved_by, n_kept = n − 2, n_discarded 1 (razón), n_attested 1 (attested_text íntegro hasta 4000 y "
      "attested_text_truncated True, clase 'attested'), knowledge_now {text, class attested, chars, truncated False}; decided_by 'human:emmanuel' / "
      "'default-keep'; n_hard_rule ≥ 2",
      ledger["state"] == "approved" and ledger["approved_by"] == "emmanuel" and ledger["n_kept"] == ledger["n_requirements"] - 2
      and ledger["n_discarded"] == 1 and ledger["n_attested"] == 1 and ledger["has_errors"] is False
      and next(r for r in ledger["requirements"] if r["requirement_id"] == aporto_id)["attested_text_truncated"] is True
      and len(next(r for r in ledger["requirements"] if r["requirement_id"] == aporto_id)["attested_text"]) == 4000
      and ledger["knowledge_now"]["class"] == "attested" and ledger["knowledge_now"]["truncated"] is False
      and {r["decided_by"] for r in ledger["requirements"]} == {"human:emmanuel", "default-keep"} and ledger["n_hard_rule"] >= 2)

BUNDLE_IDS = ["PMID:31000001", "PMID:31000002", "zfin:ZDB-GENE-980526-558", "doc-42"]
common_id = common[0]["requirement_id"]
cp_own = next(r["requirement_id"] for r in ledger["requirements"] if r["gap"].startswith("causal-pruner needs"))
sim_own = next(r["requirement_id"] for r in ledger["requirements"] if r["gap"].startswith("sim-orchestrator needs"))


def judge13(agent, request):
    mine = council.requirements_for_member(ledger, agent)
    out = []
    for r in mine:
        rid = r["requirement_id"]
        if rid == common_id:
            # 4 dueños: causal-pruner cita PMID:999 (alucinado) → anulado; sim-orchestrator 'covered' SIN ids → anulado;
            # benchmark-designer covered con id real; fitness-curator partial con id real → worst-of = partial
            if agent == CP:
                out.append({"requirement_id": rid, "coverage": "covered", "evidence_ids": ["PMID:999"], "rationale": "hallucinated"})
            elif agent == "sim-orchestrator":
                out.append({"requirement_id": rid, "coverage": "covered", "evidence_ids": [], "rationale": "no ids"})
            elif agent == "benchmark-designer":
                out.append({"requirement_id": rid, "coverage": "covered", "evidence_ids": ["PMID:31000001"], "rationale": "ok"})
            else:
                out.append({"requirement_id": rid, "coverage": "partial", "evidence_ids": ["PMID:31000002"], "rationale": "partly",
                            "search_directive": {"query_en": "wt1a pronephros 24 hpf in situ", "entities": ["wt1a", "lhx1a"]}})
        elif rid == cp_own:
            out.append({"requirement_id": rid, "coverage": "covered", "evidence_ids": ["PMID:999", "doc-42"], "rationale": "one bad id"})
        elif rid == sim_own:
            out.append({"requirement_id": rid, "coverage": "uncovered", "evidence_ids": [], "rationale": "nothing here",
                        "search_directive": {"query_en": "refined sim query", "entities": []}})
        elif r["evidence_kind"] == "figure":
            out.append({"requirement_id": rid, "coverage": "uncovered", "evidence_ids": [], "rationale": "no figure in the bundle"})
        else:
            out.append({"requirement_id": rid, "coverage": "covered", "evidence_ids": ["doc-42"], "rationale": "ok"})
    if agent == "imaging-analyst":
        out.append({"requirement_id": common_id, "coverage": "covered", "evidence_ids": ["doc-42"], "rationale": "not mine"})
        out.append({"requirement_id": "req-000000000000", "coverage": "covered", "evidence_ids": ["doc-42"], "rationale": "unknown"})
    return {"judgments": out}


CTX_R2 = {"question": CTX_R1["question"], "entities": CTX_R1["entities"], "ledger": ledger, "evidence_ids": BUNDLE_IDS,
          "evidence_view": {"path_a_hits": [{"doc_id": "doc-42", "text": "wt1a " * 3000}], "path_b": {"papers": []}},
          "pass1": {"direct_answer": "…", "gap_flags": ["x"], "absence_kind": None, "citations": []},
          "human_attestations": {"knowledge_now": ledger["knowledge_now"], "attestations": []}, "phase": "run"}
f13 = Fake(round_="r2", judge=judge13)
cfg_r2 = council.config(ENV0, heartbeat_s=0.05, model=COUNCIL_MODEL)
cfg_r2["r2_evidence_chars"] = 2000
res_r2, ev_r2, _ = run(f13, round_="r2", ctx=CTX_R2, cfg=cfg_r2)
rows_r2 = {r["agent"]: r for r in res_r2["members"]}
check("(C.5) r2: SÓLO los dueños de requisitos kept se invocan; regulatory-ethics (sin requisitos) → 'not-invoked' con razón; el dueño del "
      "requisito atestiguado (domain-knowledge-curator, su único requisito) tampoco se invoca (aporto → no se le envía nada); tool_choice "
      "emit_coverage_judgment; tools byte-idénticos a r1; phase 'run'; n_invoked 15",
      rows_r2[REG]["status"] == "not-invoked" and "no kept requirement" in rows_r2[REG]["not_invoked_reason"]
      and rows_r2["domain-knowledge-curator"]["status"] == "not-invoked"
      and all(c["tool_choice"]["name"] == "emit_coverage_judgment" for c in f13.calls) and all(c["tools"] == list(council.TOOLS) for c in f13.calls)
      and aporto_id not in json.dumps([c["user_text"] for c in f13.calls])
      and res_r2["phase"] == "run" and res_r2["n_not_invoked"] == 2 and res_r2["n_invoked"] == 15)
check("(C.3/C.5) corrector: el cuórum de r2 se mide sobre los ELEGIBLES — quorum {n_members 17, n_eligible 15, n_not_invoked 2, "
      "required 9 = ceil(0.6·15), required_full_membership 11, met True, state 'met', rule}; n_eligible también en la fila y en el "
      "evento round; r1 sigue con n_eligible == N (17 → 11)",
      res_r2["quorum"] == {**res_r2["quorum"], "n_members": 17, "n_eligible": 15, "n_not_invoked": 2, "required": 9,
                           "required_full_membership": 11, "met": True, "state": "met", "rule": council.QUORUM_SOURCE}
      and res_r2["n_eligible"] == 15 and ev_r2[-1][1]["n_eligible"] == 15 and ev_r2[-1][1]["quorum"]["required"] == 9
      and res1["quorum"]["n_eligible"] == 17 and res1["quorum"]["required"] == 11 and "n_eligible" in council.QUORUM_SOURCE,
      json.dumps(res_r2["quorum"]))
_led3 = {"state": "approved", "requirements": [
    {"requirement_id": f"req-owner{i:07d}", "gap": f"only {a} asks", "evidence_kind": "paper", "source_family": "europepmc",
     "query_en": f"{a} query", "entities": ["wt1a"], "acceptance_test": "x", "priority": "must", "requested_by": [a],
     "n_requested_by": 1, "n_members": 17, "hard_rule_gate": False, "exploratory": False, "from_operative": False,
     "harness_state": "satisfiable", "decision": "keep", "decided_by": "human:emmanuel", "decided_at": "2026-09-15T10:05:00Z"}
    for i, a in enumerate(MEMBERS[:3])], "knowledge_now": None, "flags": []}


def judge3(agent, request):
    return {"judgments": [{"requirement_id": r["requirement_id"], "coverage": "covered", "evidence_ids": ["doc-42"], "rationale": "ok"}
                          for r in council.requirements_for_member(_led3, agent)]}


res_r2c, ev_r2c, _ = run(Fake(round_="r2", judge=judge3), round_="r2", ctx={**CTX_R2, "ledger": _led3}, cfg=cfg_r2)
cov3 = council.judge_coverage(res_r2c, _led3, BUNDLE_IDS, phase="pre-search")
check("(C.3/C.5) corrector: 3 dueños de requisitos kept (14 'not-invoked') que votan covered con id válido → r2 'applicable' con "
      "quorum {n_eligible 3, required 2, n_valid 3, met True} — antes 3/17 < 11 era 'incomplete' POR CONSTRUCCIÓN (la compuerta "
      "declaraba no competente sin medir nada); cobertura must_uncovered 0 · must_covered 3",
      res_r2c["state"] == "applicable" and res_r2c["n_invoked"] == 3 and res_r2c["n_not_invoked"] == 14
      and res_r2c["quorum"]["n_eligible"] == 3 and res_r2c["quorum"]["required"] == 2 and res_r2c["quorum"]["met"] is True
      and res_r2c["quorum"]["required_full_membership"] == 11 and cov3["must_uncovered"] == 0 and cov3["must_covered"] == 3,
      json.dumps({"state": res_r2c["state"], "quorum": res_r2c["quorum"]}))
lm_call = next(c for c in f13.calls if c["agent"] == "literature-monitor")
check("(C.5) payload r2 recortado a WITT_COUNCIL_R2_EVIDENCE_CHARS (2000): payload_truncated True en request y fila; evidence_ids_available, "
      "pass1 y human_attestations (PRIOR ART) en el user message; evidence_view declarada 'DI + path_b (structural, if fired)'",
      lm_call["payload_truncated"] is True and rows_r2["literature-monitor"]["payload_truncated"] is True and lm_call["evidence_chars"] == 2000
      and "PMID:31000001" in lm_call["user_text"] and "gap_flags" in lm_call["user_text"] and "knowledge_now" in lm_call["user_text"]
      and council.EVIDENCE_VIEW_STATE in lm_call["user_text"] and "TRUNCATED at 2000" in lm_call["user_text"])
cov = council.judge_coverage(res_r2, ledger, BUNDLE_IDS, phase="pre-search")
by_cov = {b["requirement_id"]: b for b in cov["by_requirement"]}
cm = by_cov[common_id]
check("(13)(14) requisito común: voto de causal-pruner con PMID:999 ∉ bundle → annulled + hallucinated_evidence_ids ['PMID:999']; 'covered' sin ids "
      "→ annulled; covered + partial válidos → coverage_final 'partial' (worst-of); n_valid_votes 2, n_annulled 2; pertinence de PMID:31000001/2",
      cm["coverage_final"] == "partial" and cm["n_valid_votes"] == 2 and cm["n_annulled_votes"] == 2
      and next(v for v in cm["votes"] if v["agent"] == CP)["hallucinated_evidence_ids"] == ["PMID:999"]
      and next(v for v in cm["votes"] if v["agent"] == "sim-orchestrator")["annul_reason"].startswith("covered without")
      and cov["pertinence"]["PMID:31000001"] == [common_id] and cov["pertinence"]["PMID:31000002"] == [common_id],
      json.dumps({k: cm[k] for k in ("coverage_final", "n_valid_votes", "n_annulled_votes")}))
check("(13) requisito propio de causal-pruner: ÚNICO voto con un id alucinado → todos anulados → 'not-judged' → cuenta como must SIN cubrir; "
      "id ajeno (imaging-analyst sobre el común) → foreign 'not-requested-by-member'; id inexistente → foreign 'unknown-requirement'; "
      "n_hallucinated_votes 2",
      by_cov[cp_own]["coverage_final"] == "not-judged" and cp_own in cov["uncovered_must_ids"]
      and {(f["agent"], f["reason"]) for f in cov["foreign_requirement_ids"]} == {("imaging-analyst", "not-requested-by-member"),
                                                                                  ("imaging-analyst", "unknown-requirement")}
      and cov["n_hallucinated_votes"] == 2)
check("(C.5) conteos: must_total = must del ledger; atestiguado → 'covered-by-attestation' (must_attested 0: era should); discard → 'discarded' "
      "(web, must_discarded 1); figure → must_unsatisfiable 1 (NO gatea, E1); must_uncovered = strict + partial + not-judged (común partial + "
      "cp not-judged + …); must_covered contado; class y rule declaradas",
      by_cov[aporto_id]["coverage_final"] == "covered-by-attestation" and by_cov[lit_web]["coverage_final"] == "discarded"
      and cov["must_discarded"] == 1 and cov["must_unsatisfiable"] == 1 and cov["must_total"] == agg1["n_must"]
      and cov["must_uncovered"] == cov["must_uncovered_strict"] + cov["must_partial"] + cov["must_not_judged"]
      and cov["must_partial"] == 1 and cov["must_not_judged"] == 1 and cov["must_uncovered_strict"] == 1 and cov["must_uncovered"] == 3
      and cov["must_gateable"] == 3 and cov["must_total"] == 5 and cov["must_covered"] == 0
      and cov["must_gateable"] == cov["must_covered"] + cov["must_uncovered"]
      and cov["class"].startswith("model-judgment aggregated by code") and cov["state"] == "judged" and cov["phase"] == "pre-search",
      json.dumps({k: cov[k] for k in ("must_total", "must_gateable", "must_covered", "must_uncovered", "must_partial", "must_not_judged",
                                      "must_attested", "must_discarded", "must_unsatisfiable")}))
sim_cov = by_cov[sim_own]
check("(14b) voto único 'uncovered' sin ids es VÁLIDO (uncovered no exige id) → coverage_final 'uncovered'; el search_directive viaja en el voto",
      sim_cov["coverage_final"] == "uncovered" and sim_cov["n_valid_votes"] == 1 and sim_cov["votes"][0]["search_directive"]["query_en"] == "refined sim query")

dirs = council.directives_from(cov, ledger, MEMBERS)
d_by = {d["requirement_id"]: d for d in dirs["directives"]}
check("(25) directivas COMPILADAS por código: una por requisito kept sin cubrir y satisfiable; la del común lleva family zfin, evidence_kind, "
      "requested_by 4, symbols ['wt1a'] (resueltos), query_en REFINADA por fitness-curator (refined_by_members) con query_en_original; la de "
      "causal-pruner (not-judged, sin search_directive) sale del REQUISITO con refined_by_members []; state 'compiled'; orden must primero",
      common_id in d_by and d_by[common_id]["family"] == "zfin" and d_by[common_id]["requested_by"] == MEMBERS[:4]
      and d_by[common_id]["symbols"] == ["wt1a"] and d_by[common_id]["query_en"] == "wt1a pronephros 24 hpf in situ"
      and d_by[common_id]["query_en_original"] == "wt1a pronephros expression 24 hpf" and d_by[common_id]["refined_by_members"] == ["fitness-curator"]
      and "lhx1a" in d_by[common_id]["entities"] and cp_own in d_by and d_by[cp_own]["refined_by_members"] == []
      and d_by[cp_own]["query_en"] == "causal-pruner specific query 0 pronephros"
      and all(d["state"] == "compiled" for d in dirs["directives"]) and dirs["directives"][0]["priority"] == "must"
      and dirs["state"] == "provided" and dirs["n"] == len(dirs["directives"]))
fig_id = next(r["requirement_id"] for r in ledger["requirements"] if r["evidence_kind"] == "figure")
check("(25b) excluidas: figure (must kept, voto uncovered) → 'excluded-unsatisfiable' con la razón del harness_state; web discarded NO aparece "
      "(no es kept); familias en orden de aparición; n_excluded 1",
      dirs["n_excluded"] == 1 and dirs["excluded"][0]["requirement_id"] == fig_id and dirs["excluded"][0]["state"] == "excluded-unsatisfiable"
      and lit_web not in d_by and lit_web not in {e["requirement_id"] for e in dirs["excluded"]} and "zfin" in dirs["families"])
cov_all = council.judge_coverage({"members": [], "round": "r2"}, {"requirements": [{**r, "decision": "aporto"} for r in ledger["requirements"]]}, BUNDLE_IDS)
check("(25c) todo atestiguado → 0 directivas, state 'none (all must covered)'; sin votos → must_uncovered 0 (todos covered-by-attestation, "
      "must_attested = must_total)",
      council.directives_from(cov_all, {"requirements": [{**r, "decision": "aporto"} for r in ledger["requirements"]]})["state"] == "none (all must covered)"
      and cov_all["must_uncovered"] == 0 and cov_all["must_attested"] == cov_all["must_total"])

# ---- ADR-0084 (F.2): el harness_state guardado en r1 es lo que vio el PLAN; la compilación lo RECOMPUTA para la familia web ----
web_req_off = dict(next(r for r in ledger["requirements"] if r["requirement_id"] == lit_web))
web_req_off.update(decision="keep", decided_by="human:emmanuel")
zfin_req = dict(next(r for r in ledger["requirements"] if r["requirement_id"] == common_id))
assert web_req_off["harness_state"] == sh.WEB_UNSATISFIABLE_LITERAL and zfin_req["harness_state"] == "satisfiable"
ledger_web = {"requirements": [web_req_off, zfin_req]}
cov_web = {"by_requirement": [{"requirement_id": lit_web, "coverage_final": "uncovered", "votes": []},
                              {"requirement_id": common_id, "coverage_final": "uncovered", "votes": []}]}
KEY_ENV = {"BRAVE_API_KEY": FAKE_BRAVE_KEY}
RECOMP_KEYS = ("harness_state_at_plan", "harness_state_at_compile", "harness_state_recomputed")
d_key = council.directives_from(cov_web, ledger_web, MEMBERS, env=KEY_ENV)
dk_by = {d["requirement_id"]: d for d in d_key["directives"]}
check("(25d) ADR-0084 F.2 — plan aprobado bajo off (web guardado 'unsatisfiable…') y llave presente al COMPILAR → la directiva web se "
      "compila SIN re-planear: state 'compiled', family 'web', evidence_kind 'web', query_en del requisito, harness_state_at_plan == literal, "
      "harness_state_at_compile 'satisfiable', harness_state_recomputed True; la de zfin (estática) NO gana ninguna de las 3 llaves; "
      "families ∋ web; n_excluded 0; harness_state_recompute_rule declarada; rule == DIRECTIVES_RULE de 1.12 BYTE A BYTE (corrector L: sin "
      "ADR-0084 en el literal compartido) y availability_rule == DIRECTIVES_AVAILABILITY_RULE (nombra ADR-0084 F.2) SÓLO porque hubo recomputo",
      lit_web in dk_by and dk_by[lit_web]["state"] == "compiled" and dk_by[lit_web]["family"] == "web"
      and dk_by[lit_web]["evidence_kind"] == "web" and dk_by[lit_web]["query_en"] == "latest preprints pronephros wt1a"
      and dk_by[lit_web]["harness_state_at_plan"] == sh.WEB_UNSATISFIABLE_LITERAL
      and dk_by[lit_web]["harness_state_at_compile"] == "satisfiable" and dk_by[lit_web]["harness_state_recomputed"] is True
      and common_id in dk_by and not any(k in dk_by[common_id] for k in RECOMP_KEYS)
      and "web" in d_key["families"] and d_key["n_excluded"] == 0 and d_key["n"] == 2
      and d_key["harness_state_recompute_rule"] == council.HARNESS_STATE_RECOMPUTE_RULE and d_key["rule"] == council.DIRECTIVES_RULE
      and "ADR-0084" not in d_key["rule"] and d_key["availability_rule"] == council.DIRECTIVES_AVAILABILITY_RULE
      and "ADR-0084 F.2" in d_key["availability_rule"]
      and FAKE_BRAVE_KEY not in json.dumps(d_key),
      json.dumps(dk_by.get(lit_web)))
d_off = council.directives_from(cov_web, ledger_web, MEMBERS, env={})
check("(25d-bis, corrector ADR-0084 L) sin recomputo (guardado == recomputado bajo off) directives_from NO emite availability_rule: la salida "
      "conserva el keyset de 1.12 + harness_state_recompute_rule; DIRECTIVES_RULE y AFTER_SEARCH_RULE son los literales de 1.12 (sin 'ADR-0084')",
      "availability_rule" not in d_off and "ADR-0084" not in council.DIRECTIVES_RULE and "ADR-0084" not in council.AFTER_SEARCH_RULE
      and "ADR-0084 F.4" in council.WEB_LOCATOR_COVERAGE_RULE, json.dumps(sorted(d_off)))
web_req_sat = {**web_req_off, "harness_state": "satisfiable"}
d_left = council.directives_from(cov_web, {"requirements": [web_req_sat, zfin_req]}, MEMBERS, env={})
zfin_stale = {**zfin_req, "harness_state": "unsatisfiable-by-harness (stale-static-value)"}
d_stale = council.directives_from(cov_web, {"requirements": [web_req_off, zfin_stale]}, MEMBERS, env=KEY_ENV)
ex_off = {e["requirement_id"]: e for e in d_off["excluded"]}
ex_left = {e["requirement_id"]: e for e in d_left["excluded"]}
ex_stale = {e["requirement_id"]: e for e in d_stale["excluded"]}
check("(25e) ADR-0084 F.2 — sin llave: web 'excluded-unsatisfiable' con el literal EXACTO y SIN llaves de recomputo (guardado == recomputado: "
      "byte-idéntico a 1.12); guardado 'satisfiable' + llave que SE FUE → excluida con reason literal + harness_state_at_plan 'satisfiable' + "
      "recomputed True; familia ESTÁTICA (zfin) con guardado obsoleto → se respeta el guardado (excluida con ese texto, sin recomputo); "
      "directives_from acepta env= (firma [coverage, ledger, members_order, env])",
      lit_web in ex_off and ex_off[lit_web]["state"] == "excluded-unsatisfiable" and ex_off[lit_web]["reason"] == sh.WEB_UNSATISFIABLE_LITERAL
      and not any(k in ex_off[lit_web] for k in RECOMP_KEYS) and d_off["n"] == 1 and d_off["families"] == ["zfin"]
      and lit_web in ex_left and ex_left[lit_web]["reason"] == sh.WEB_UNSATISFIABLE_LITERAL
      and ex_left[lit_web]["harness_state_at_plan"] == "satisfiable" and ex_left[lit_web]["harness_state_at_compile"] == sh.WEB_UNSATISFIABLE_LITERAL
      and ex_left[lit_web]["harness_state_recomputed"] is True
      and common_id in ex_stale and ex_stale[common_id]["reason"] == "unsatisfiable-by-harness (stale-static-value)"
      and not any(k in ex_stale[common_id] for k in RECOMP_KEYS) and lit_web in {d["requirement_id"] for d in d_stale["directives"]}
      and list(inspect.signature(council.directives_from).parameters) == ["coverage", "ledger", "members_order", "env"],
      json.dumps({"off": ex_off.get(lit_web), "left": ex_left.get(lit_web)}))

search_ledger = {"plan": {"directives": [dict(d) for d in dirs["directives"]]},
                 "rounds": [{"round": 1, "items": [
                     {"evidence_id": "zfin:ZDB-GENE-000000-1", "source_family": "zfin", "kind": "phenotype", "directive_requirement_ids": [common_id]},
                     {"evidence_id": "zfin:ZDB-GENE-000000-2", "source_family": "zfin", "kind": "phenotype", "directive_requirement_ids": [common_id]},
                     {"evidence_id": "PMID:5", "source_family": "europepmc", "kind": "paper", "directive_requirement_ids": []}]}],
                 "n_admitted_total": 3}
after = council.coverage_after_search(cov, search_ledger)
a_by = {b["requirement_id"]: b for b in after["by_requirement"]}
check("(26) coverage_after_search (código, siempre): común → 'retrieved-for' (2 ítems, families ['zfin']); causal-pruner propio → "
      "'still-uncovered' (directiva sin ítems); figure → 'not-searched' (sin directiva); atestiguado → 'covered-pre'; n_items_for_directives "
      "{común: 2}; state 'measured'; sin ledger → 'not-run (no search ledger)'",
      a_by[common_id]["state"] == "retrieved-for" and a_by[common_id]["n_items_retrieved"] == 2 and a_by[common_id]["families"] == ["zfin"]
      and a_by[cp_own]["state"] == "still-uncovered" and a_by[fig_id]["state"] == "not-searched" and a_by[aporto_id]["state"] == "covered-pre"
      and after["n_items_for_directives"] == {common_id: 2} and after["state"] == "measured"
      and council.coverage_after_search(cov, None)["state"] == "not-run (no search ledger)")
KEYS_112_TOP = {"state", "by_requirement", "n_retrieved_for", "n_still_uncovered", "n_not_searched", "n_covered_pre",
                "n_items_for_directives", "rule", "decided_by"}
KEYS_112_ROW = {"requirement_id", "priority", "state", "n_items_retrieved", "families"}
check("(26a) ADR-0084 F.4 — sin ledger web la forma de coverage_after_search es la de 1.12 byte a byte: llaves de nivel superior y de fila "
      "EXACTAS (ni web_locator, ni web_locator_source, ni web_locator_rule); firma [coverage_pre, search_ledger, directives, web_locator]",
      set(after) == KEYS_112_TOP and all(set(b) == KEYS_112_ROW for b in after["by_requirement"])
      and set(council.coverage_after_search(cov, None)) == KEYS_112_TOP
      and list(inspect.signature(council.coverage_after_search).parameters) == ["coverage_pre", "search_ledger", "directives", "web_locator"])
# el ledger del localizador (forma W3/D.4: queries[]/located[]/unresolved[] con requirement_ids; las URLs y title_web viven SÓLO ahí)
WL_BLOCK = {"queries": [{"round": 1, "requirement_ids": [lit_web], "query_en": "latest preprints pronephros wt1a", "n_results": 6,
                         "provider_status": "success", "cache_hit": False},
                        {"round": 1, "requirement_ids": [lit_web], "query_en": "latest preprints pronephros wt1a", "n_results": None,
                         "provider_status": "skipped-cap", "detail": "WITT_WEB_MAX_QUERIES=1 reached"}],
            "located": [{"round": 1, "requirement_ids": [lit_web], "id": "PMID:7", "kind": "pmid", "resolver_rule": "pubmed-path",
                         "feed_state": "materialized-same-round", "url": "https://pubmed.ncbi.nlm.nih.gov/7/", "evidence_id": "PMID:7"},
                        {"round": 1, "requirement_ids": [lit_web], "id": "PMID:8", "kind": "pmid", "resolver_rule": "pubmed-path",
                         "feed_state": "not-found-in-europepmc", "url": "https://pubmed.ncbi.nlm.nih.gov/8/"},
                        {"round": 1, "requirement_ids": [lit_web], "id": "10.1000/smoke.x", "kind": "doi", "resolver_rule": "doi-org-path",
                         "feed_state": "already-present (dup of PMID:9)", "url": "https://doi.org/10.1000/smoke.x"}],
            "unresolved": [{"round": 1, "requirement_ids": [lit_web], "host": "www.researchgate.net", "reason": "no-identifier-pattern",
                            "url": "https://www.researchgate.net/publication/SECRET-URL-1", "title_web": "SECRET-TITLE-WEB-1"},
                           {"round": 1, "requirement_ids": [lit_web], "host": "en.wikipedia.org", "reason": "no-identifier-pattern",
                            "url": "https://en.wikipedia.org/wiki/SECRET-URL-2", "title_web": "SECRET-TITLE-WEB-2"}]}
WEB_ITEM = {"evidence_id": "PMID:7", "source": "europepmc", "source_family": "web", "kind": "literature-candidate",
            "identifier_provenance": "web-located:pubmed-path", "directive_requirement_ids": [lit_web]}
ledger_w = {"plan": {"directives": [dict(d) for d in d_key["directives"]]}, "items": [WEB_ITEM]}      # la forma que runs pasa
after_w = council.coverage_after_search(cov_web, ledger_w, web_locator=WL_BLOCK)
aw_by = {b["requirement_id"]: b for b in after_w["by_requirement"]}
EXPECT_WL = {"n_queries": 2, "n_results": 6, "n_located": 3, "n_materialized": 1, "n_unresolved": 2}
ledger_r = {"plan": {"directives": [dict(d) for d in d_key["directives"]]},
            "rounds": [{"round": 1, "items": [WEB_ITEM],
                        "sources": [{"family": "web", "status": "success", "n_found": 6, "web_locator": WL_BLOCK},
                                    {"family": "zfin", "status": "no-match", "n_found": 0}]}]}
after_r = council.coverage_after_search(cov_web, ledger_r)
ar_by = {b["requirement_id"]: b for b in after_r["by_requirement"]}
check("(26b) ADR-0084 F.4 — coverage_after_search(web_locator=block D.4): el requisito web queda 'retrieved-for' (1 candidato admitido "
      "source_family 'web' — materializado por EPMC), families ['web'], web_locator {n_queries 2, n_results 6 (None no cuenta), n_located 3, "
      "n_materialized 1 (feed_state 'materialized-same-round' == web_locator.FEED_STATES_EXACT[0]), n_unresolved 2}; el requisito zfin "
      "('still-uncovered') NO lleva web_locator; web_locator_source 'caller (web_locator=)' y web_locator_rule declaradas; la MISMA "
      "medición desde rounds[].sources[web].web_locator (ledger íntegro del harness) con su fuente; 0 URLs (regex https?://) y 0 "
      "title_web en la salida — las URLs viven SÓLO en el ledger",
      aw_by[lit_web]["state"] == "retrieved-for" and aw_by[lit_web]["n_items_retrieved"] == 1 and aw_by[lit_web]["families"] == ["web"]
      and aw_by[lit_web]["web_locator"] == EXPECT_WL and "web_locator" not in aw_by[common_id]
      and aw_by[common_id]["state"] == "still-uncovered"
      and after_w["web_locator_source"] == "caller (web_locator=)" and after_w["web_locator_rule"] == council.WEB_LOCATOR_COVERAGE_RULE
      and council._WEB_MATERIALIZED_FEED_STATE == wl.FEED_STATES_EXACT[0] == "materialized-same-round"
      and tuple(EXPECT_WL) == council.WEB_LOCATOR_COVERAGE_KEYS
      and ar_by[lit_web]["web_locator"] == EXPECT_WL and "web_locator" not in ar_by[common_id]
      and after_r["web_locator_source"] == "search_ledger.rounds[].sources[web].web_locator"
      and not re.search(r"https?://", json.dumps(after_w) + json.dumps(after_r))
      and "SECRET" not in json.dumps(after_w) + json.dumps(after_r)
      and set(after_w) == KEYS_112_TOP | {"web_locator_source", "web_locator_rule"}
      and set(aw_by[lit_web]) == KEYS_112_ROW | {"web_locator"} and set(aw_by[common_id]) == KEYS_112_ROW,
      json.dumps({"web": aw_by.get(lit_web), "src": after_w.get("web_locator_source")}))
after_nowl = council.coverage_after_search(cov_web, ledger_w)          # directiva web compilada pero SIN ledger del localizador
check("(26c) ADR-0084 F.4 — directiva web compilada pero sin ledger del localizador (web_locator ausente) → ninguna llave web: no se "
      "inventan ceros (ausente ≠ 0 medido, ADR-0043); el requisito web sigue 'retrieved-for' por el ítem admitido",
      "web_locator" not in {k for b in after_nowl["by_requirement"] for k in b} and "web_locator_source" not in after_nowl
      and {b["requirement_id"]: b["state"] for b in after_nowl["by_requirement"]}[lit_web] == "retrieved-for")

owners = council.recoverage_members(cov, ledger)
check("(C.7) recoverage_members: los DUEÑOS de los must kept sin cubrir, en orden de tabla, subconjunto < 17 (incluye causal-pruner y los 4 del común)",
      set(MEMBERS[:4]) <= set(owners) and len(owners) < 17 and owners == [a for a in FULL if a in set(owners)])

frozen_council = {"state": "applicable", "ledger": ledger, "coverage": {"pre_search": cov, "post_search": {"state": "not-run (nothing admitted)"}}}
summ = council.summary_for_thread(frozen_council, cap=5)
check("(G.9) summary_for_thread: requisitos ≤ cap con gap ≤ 200, priority, coverage_final (pre_search cuando post no juzgó), decision, "
      "n_requested_by; flags; knowledge_now_present True; must_uncovered_post None (declarado: post no corrió); truncated True; sin prosa "
      "atestiguada; sin consejo → None",
      summ is not None and len(summ["requirements"]) == 5 and summ["truncated"] is True and summ["n_total"] == ledger["n_requirements"]
      and summ["requirements"][0]["coverage_final"] == by_cov[summ["requirements"][0]["requirement_id"]]["coverage_final"]
      and summ["knowledge_now_present"] is True and summ["must_uncovered_post"] is None and summ["coverage_source"] == "pre_search"
      and "Emmanuel: the 2025 review" not in json.dumps(summ) and summ["flags"] == [{"kind": "compliance", "statement": "zebrafish work under IACUC protocol"}]
      and council.summary_for_thread(None) is None and council.summary_for_thread({"state": "disabled (kill-switch WITT_COUNCIL=0)"}) is None)
post = dict(cov)
post["state"], post["must_uncovered"] = "judged", 1
summ2 = council.summary_for_thread({"ledger": ledger, "coverage": {"pre_search": cov, "post_search": post}})
check("(G.9) con post_search juzgado → must_uncovered_post 1 y coverage_source 'post_search'; cap default 24",
      summ2["must_uncovered_post"] == 1 and summ2["coverage_source"] == "post_search" and summ2["cap"] == 24)

# =====================================================================================================================
# contrato C2 (firmas), sin red, sin openai
# =====================================================================================================================
check("contrato C2: run_round(members, round_, ctx, caller=None, budget_s=None, on_event=None, cancel_check=None, cfg=None, env=None, clock=None, cancel_exc=None (corrector), "
      "payload_for=None, phase=None); aggregate_r1(round_result, members=None, cfg=None, resolver=None); judge_coverage(round_result, ledger, "
      "evidence_ids, phase='pre-search', round_=None); directives_from(coverage, ledger, members_order=None, env=None) (ADR-0084 F.2); "
      "coverage_after_search(coverage_pre, search_ledger, directives=None, web_locator=None) (ADR-0084 F.4); summary_for_thread(council, cap=24); "
      "validate_tool_input(agent, round_, raw, cfg=None); aliases",
      list(inspect.signature(council.run_round).parameters) == ["members", "round_", "ctx", "caller", "budget_s", "on_event", "cancel_check",
                                                                  "cfg", "env", "clock", "payload_for", "phase", "cancel_exc"]
      and list(inspect.signature(council.aggregate_r1).parameters) == ["round_result", "members", "cfg", "resolver"]
      and list(inspect.signature(council.judge_coverage).parameters) == ["round_result", "ledger", "evidence_ids", "phase", "round_"]
      and list(inspect.signature(council.directives_from).parameters) == ["coverage", "ledger", "members_order", "env"]
      and list(inspect.signature(council.coverage_after_search).parameters) == ["coverage_pre", "search_ledger", "directives", "web_locator"]
      and list(inspect.signature(council.summary_for_thread).parameters) == ["council", "cap"]
      and council.aggregate_requirements is council.aggregate_r1 and council.aggregate_coverage is council.judge_coverage
      and council.compile_directives is council.directives_from)
check("(D.1) contrato del caller: _anthropic_tool_call(..., return_meta=False, tools=None, user_content=None) — `user_content` se APILA "
      "tras `tools` (ADR-0083 G.3, F3; None → content: user_text byte a byte); CallerError(kind, message, legacy_type_name=None, "
      "usage=None, meta=None, retry_after=None); _INFLIGHT BoundedSemaphore con límite/fuente declarados; default_caller usa tools=TOOLS",
      list(inspect.signature(ca._anthropic_tool_call).parameters) == ["model", "system", "user_text", "tool", "timeout", "retries",
                                                                       "max_tokens", "effort", "return_meta", "tools", "user_content"]
      and inspect.signature(ca._anthropic_tool_call).parameters["user_content"].default is None
      and list(inspect.signature(ca.CallerError.__init__).parameters)[1:] == ["kind", "message", "legacy_type_name", "usage", "meta", "retry_after"]
      and isinstance(ca._INFLIGHT, type(threading.BoundedSemaphore())) and ca._INFLIGHT_LIMIT == 8 and "default-unset" in ca._INFLIGHT_SOURCE
      and "tools=request[\"tools\"]" in inspect.getsource(council.default_caller))
# =====================================================================================================================
# default_caller de punta a punta con urlopen FAKE (transporte simulado, cero red): el cuerpo que verá la API (dry-run del ADR)
# =====================================================================================================================
_DC_CALLS = []


class _DCResp:
    def __init__(self, payload):
        self._p = payload

    def read(self):
        return json.dumps(self._p).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _dc_urlopen(request_obj, timeout=None):
    body = json.loads(request_obj.data.decode("utf-8"))
    _DC_CALLS.append({"body": body, "timeout": timeout})
    return _DCResp({"id": "msg_dc", "model": REPORTED, "stop_reason": "tool_use",
                    "content": [{"type": "tool_use", "id": "t", "name": body["tool_choice"]["name"],
                                 "input": {"applicable": True, "requirements": [req("dry-run gap")]}}],
                    "usage": {"input_tokens": 3000, "output_tokens": 400, "cache_creation_input_tokens": 2400,
                              "cache_read_input_tokens": 0, "output_tokens_details": {"thinking_tokens": 90}}})


os.environ["ANTHROPIC_API_KEY"] = "smoke-fake-anthropic-key-not-a-secret"
try:
    urllib.request.urlopen = _dc_urlopen
    req_dc = council.build_request("sim-orchestrator", "r1", CTX_R1, council.config(ENV0), ENV0)
    out_dc, usage_dc, meta_dc = council.default_caller(req_dc)
    body_dc = _DC_CALLS[-1]["body"]
    check("default_caller → _anthropic_tool_call: cuerpo con system = 2 bloques con cache_control, tools = los TRES byte-idénticos, tool_choice "
          "forzado, max_tokens del rol (4000 g2), output_config.effort 'medium' (pinneado, modelo adaptive), timeout del SOCKET 59 = "
          "(120 − 2·retries) // (retries+1) (corrector: los 2 intentos caben en la ventana de 120 s del orquestador), 1 llamada; usage numérico "
          "con cache_creation 2400 y thinking_tokens aplanado; meta.attempts 1; el modelo del cuerpo es el de la tabla (sin literal aquí)",
          len(_DC_CALLS) == 1 and body_dc["system"] == req_dc["system"] and len(body_dc["system"]) == 2 and body_dc["tools"] == list(council.TOOLS)
          and body_dc["tool_choice"] == {"type": "tool", "name": "emit_information_requirements"} and body_dc["max_tokens"] == 4000
          and body_dc["output_config"] == {"effort": "medium"} and _DC_CALLS[-1]["timeout"] == 59 == council.socket_timeout_s(council.config(ENV0))
          and req_dc["timeout_s"] == 59 and req_dc["member_timeout_s"] == 120 and req_dc["timeout_rule"] == council.SOCKET_TIMEOUT_RULE
          and body_dc["model"] == COUNCIL_MODEL
          and usage_dc["cache_creation_input_tokens"] == 2400 and usage_dc["thinking_tokens"] == 90 and meta_dc["attempts"] == 1
          and out_dc["requirements"][0]["gap"] == "dry-run gap", json.dumps({k: body_dc[k] for k in ("max_tokens", "tool_choice", "output_config")}))
    n_dc = len(_DC_CALLS)
    req_nomodel = dict(req_dc, model=None, model_source="not-available (test)")
    try:
        council.default_caller(req_nomodel)
        e_nm = None
    except ca.CallerError as e:
        e_nm = e
    check("default_caller sin modelo resuelto → CallerError('no-model') SIN llamar (cero gasto); en run_round sería fila errored 'no-model'",
          e_nm is not None and e_nm.kind == "no-model" and len(_DC_CALLS) == n_dc)
    res_dc, _, _ = run(council.default_caller, members=MEMBERS[:3], cfg=council.config(ENV0, heartbeat_s=0.05))
    check("run_round con el caller REAL sobre urlopen fake (3 miembros): 3 filas ok, usage por fila con cache_creation, model_reported de la API, "
          "relation 'prefix', n_valid 3 (quorum 2 de 3)",
          res_dc["n_ok"] == 3 and all(r["usage"]["cache_creation_input_tokens"] == 2400 and r["model_reported"] == REPORTED
                                      and r["relation"] == "prefix" for r in res_dc["members"]) and res_dc["quorum"]["required"] == 2)
finally:
    os.environ["ANTHROPIC_API_KEY"] = ""
    urllib.request.urlopen = _blocked_urlopen


# =====================================================================================================================
# ADR-0086 (F6) · las IMÁGENES que aporta una persona en el consejo: pies de foto, jamás píxeles
# =====================================================================================================================
_SHA_I1 = "1" * 64
_SHA_I2 = "2" * 64
_CAP_I1 = "micrografia de pronefros a 48 hpf: los podocitos wt1a+ rodean el glomerulo"
_ATT_IMGS = [{"id": "attested:" + _SHA_I1[:12], "sha256_short": _SHA_I1[:12], "caption": _CAP_I1,
              "media_type": "image/png", "dims": {"w": 1024, "h": 768}, "requirement_id": None,
              "attached_to": "knowledge_now", "consent": {"kind": "own-work", "declared": True},
              "patient_material": False, "license_declared": "all-rights-reserved", "uploaded_by": "natalia",
              "uploaded_at": "2026-09-18T10:00:00+00:00", "class": "attested", "bytes_delivered": False}]
_ATT_CON = {"knowledge_now": {"text": "wt1a marca podocitos en nuestras manos", "class": "attested"},
            "attestations": [], "n_attestations": 0, "images": _ATT_IMGS, "n_images": 1,
            "images_delivery": "captions only", "class": "attested"}
_ATT_SIN = {k: v for k, v in _ATT_CON.items() if k not in ("images", "n_images", "images_delivery")}
_CTX_I = {"question": "¿wt1a marca podocitos?", "entities": ["wt1a"], "ledger": ledger,
          "evidence_ids": BUNDLE_IDS, "evidence_view": {"x": 1}, "pass1": {"direct_answer": "sí"}}
_t_con, _m_con = council.payload_r2(CP, {**_CTX_I, "human_attestations": _ATT_CON})
_t_sin, _m_sin = council.payload_r2(CP, {**_CTX_I, "human_attestations": _ATT_SIN})
_t1_con, _m1_con = council.payload_r1(CP, {**_CTX_I, "human_attestations": _ATT_CON})
_t1_sin, _m1_sin = council.payload_r1(CP, {**_CTX_I, "human_attestations": _ATT_SIN})
check("(F6) la CLÁUSULA de imágenes aportadas viaja SÓLO cuando viajan imágenes — en r1 y en r2 — y dice las dos cosas que "
      "un juez podría suponer mal: que NO ha visto los píxeles y que un requisito `aporto` está cubierto por la DECISIÓN "
      "HUMANA, no por la existencia de una foto; el meta declara n_attested_images y la regla. Sin imágenes, el payload es "
      "byte a byte el de 1.13 (M.1): ni cláusula ni llaves nuevas en el meta",
      council.ATTESTED_IMAGES_COUNCIL_CLAUSE in _t_con and council.ATTESTED_IMAGES_COUNCIL_CLAUSE in _t1_con
      and "you have NOT seen the pixels" in council.ATTESTED_IMAGES_COUNCIL_CLAUSE
      and "never by the existence of a picture" in council.ATTESTED_IMAGES_COUNCIL_CLAUSE
      and "never cite one" in council.ATTESTED_IMAGES_COUNCIL_CLAUSE
      and _m_con["n_attested_images"] == 1 and _m1_con["n_attested_images"] == 1
      and _m_con["attested_images_rule"] == council.ATTESTED_IMAGES_COUNCIL_RULE
      and council.ATTESTED_IMAGES_COUNCIL_CLAUSE not in _t_sin and council.ATTESTED_IMAGES_COUNCIL_CLAUSE not in _t1_sin
      and "n_attested_images" not in _m_sin and "attested_images_rule" not in _m_sin
      and "n_attested_images" not in _m1_sin,
      json.dumps({"r2_con": _m_con.get("n_attested_images"), "r2_sin": sorted(_m_sin)}))
check("(F6, corrector) la cláusula va DENTRO del bloque del preámbulo (un salto de línea, no dos): el cuerpo JSON sigue "
      "siendo el bloque que empieza tras el PRIMER renglón en blanco, que es la forma de la que dependen sus lectores "
      "— con dos saltos, el fake del gate de pipeline dejaba de parsear y los 17 miembros salían 'errored' (el gate se "
      "degradaba a otra corrida en vez de fallar). El caption SÍ viaja (es lo único que el consejo ve de la imagen) y "
      "NINGÚN byte: ni 'b64', ni 'data:image', ni llave de almacén",
      json.loads(_t_con.split("\n\nEVIDENCE (", 1)[0].split("\n\n", 1)[1])["human_attestations"]["n_images"] == 1
      and _CAP_I1 in _t_con and '"b64"' not in _t_con and "data:image" not in _t_con
      and "storage_key" not in _t_con and "bytes_delivered" in _t_con,
      json.dumps({"bloques_antes_del_json": _t_con.split("\n\n", 1)[0].count("\n")}))
_led_img = council.apply_ledger_decisions(
    agg1, decisions=[{"requirement_id": h, "decision": "keep"} for h in hard_ids]
    + [{"requirement_id": aporto_id, "decision": "aporto", "attested_text": "lo medimos en el laboratorio",
        "images": [_SHA_I2]}],
    approve=True, decided_by="emmanuel", decided_at="2026-09-15T10:05:00Z", images=[_SHA_I1])
check("(F6/J.1) apply_ledger_decisions acepta imágenes por IDENTIDAD: `images=` se adjunta a «qué sabes ahora» y "
      "`decisions[].images` al requisito que la persona APORTA; el ledger declara images, images_by_requirement, n_images "
      "y su regla. Aquí viajan sha, jamás bytes ni llaves de almacén",
      _led_img["n_images"] == 2 and _led_img["images"] == [_SHA_I1]
      and _led_img["images_by_requirement"] == {aporto_id: [_SHA_I2]}
      and next(r for r in _led_img["requirements"] if r["requirement_id"] == aporto_id)["n_images"] == 1
      and _led_img["images_rule"] == council.ATTESTED_IMAGES_LEDGER_RULE
      and _led_img["images_class"] == "attested" and _led_img["has_errors"] is False
      and '"b64"' not in json.dumps(_led_img) and "storage_key" not in json.dumps(_led_img),
      json.dumps({"n": _led_img["n_images"], "por_requisito": _led_img["images_by_requirement"]}))
_led_mal = council.apply_ledger_decisions(
    agg1, decisions=[{"requirement_id": hard_ids[0], "decision": "keep", "images": [_SHA_I1]},
                     {"requirement_id": lit_web, "decision": "discard", "reason": "no alcanza", "images": [_SHA_I2]}])
check("(F6/J.2) una imagen colgada de un requisito que se MANTIENE o se DESCARTA es un error, no un default: "
      "errors.images_without_aporto con los dos requirement_id y has_errors True — aportar es una decisión distinta de "
      "mantener, y el ledger no la adivina",
      sorted(_led_mal["errors"]["images_without_aporto"]) == sorted([hard_ids[0], lit_web])
      and _led_mal["has_errors"] is True
      and all("images" not in r for r in _led_mal["requirements"]),
      json.dumps(_led_mal["errors"]["images_without_aporto"]))
check("(F6, M.1) sin imágenes NINGUNA llave nueva nace en el ledger: el aprobado de arriba (mismas decisiones, sin "
      "`images`) no trae images, images_by_requirement, n_images, images_rule ni images_class",
      not ({"images", "images_by_requirement", "n_images", "images_rule", "images_class"} & set(ledger)),
      json.dumps(sorted(k for k in ledger if "image" in k)))
_cov_img = council.judge_coverage(res_r2, _led_img, BUNDLE_IDS, phase="pre-search")
_cov_sin = council.judge_coverage(res_r2, ledger, BUNDLE_IDS, phase="pre-search")
_b_img = {b["requirement_id"]: b for b in _cov_img["by_requirement"]}
check("(F6) la cobertura CUENTA las imágenes y no las convierte en cobertura: n_with_image, n_attested_with_image, "
      "must_attested_with_image y n_images_total, con la regla que lo dice — el requisito sigue 'covered-by-attestation' "
      "por la DECISIÓN de la persona (que ya se cuenta en must_attested), no por la foto; y sin imágenes en el ledger "
      "ninguna de esas llaves nace (M.1)",
      _cov_img["n_with_image"] == 1 and _cov_img["n_attested_with_image"] == 1 and _cov_img["n_images_total"] == 1
      and _cov_img["attested_images_rule"] == council.ATTESTED_IMAGES_COUNCIL_RULE
      and _b_img[aporto_id]["coverage_final"] == "covered-by-attestation"
      and _cov_img["must_attested"] == _cov_sin["must_attested"]
      and _cov_img["must_uncovered"] == _cov_sin["must_uncovered"]
      and not ({"n_with_image", "n_attested_with_image", "must_attested_with_image", "n_images_total",
                "attested_images_rule"} & set(_cov_sin)),
      json.dumps({k: _cov_img[k] for k in ("n_with_image", "n_attested_with_image", "n_images_total")}))
_summ_img = council.summary_for_thread({"ledger": _led_img, "coverage": {"pre_search": _cov_img}})
_summ_sin = council.summary_for_thread({"ledger": ledger, "coverage": {"pre_search": _cov_sin}})
check("(F6) el turno SIGUIENTE hereda CUÁNTAS imágenes aportó una persona, no lo que dicen: n_attested_images y "
      "n_requirements_with_image, sin un solo caption (el planner no necesita leer la prosa de nadie para planear; el "
      "caption recortado viaja aparte, en thread_context.parent_attested_images). Sin imágenes, la llave no nace",
      _summ_img["n_attested_images"] == 2 and _summ_img["n_requirements_with_image"] == 1
      and _CAP_I1 not in json.dumps(_summ_img, default=str)
      and not ({"n_attested_images", "n_requirements_with_image"} & set(_summ_sin)),
      json.dumps({"con": _summ_img["n_attested_images"], "sin": sorted(k for k in _summ_sin if "image" in k)}))

check("(M.3) urllib.request.urlopen REAL bloqueado: 0 llamadas en todo el gate; 'openai' jamás importado; sin BD tocada (council no importa db)",
      _NET_CALLS == [] and "openai" not in sys.modules and "db" not in sys.modules and "rag_index.query_service.db" not in sys.modules)

npass = sum(CHECKS)
print("\n== %d/%d PASS ==" % (npass, len(CHECKS)))
sys.exit(0 if npass == len(CHECKS) else 1)

"""
smoke_agent_matrix.py — gate NO-SPEND de la MATRIZ v1.3 y la MEMBRESÍA POR TABLA del consejo
(ADR-0082 (B); rebanada C1).

Mide, no supone:
  · 34 filas (29 de v1.2 intactas + 5 nuevas); `category` ∈ 6 en TODAS; `card` en todas y exactamente 3
    'no-card-in-catalog'; donde la categoría de la matriz diverge de la sección del catálogo, la fila lo
    DECLARA en `category_note` (4 operativos) — nunca en silencio.
  · COUNCIL_MEMBERSHIP cm-1 = los 17 nombres EXACTOS del brief §5.1 en su orden fijo (5/7/3/1/1); modos por
    tabla: causal-pruner `requirements-human-gated` + `hard_rule_gate True` (el ÚNICO), regulatory-ethics
    `flags-only` → `emit_flags`, cross-field `exploratory`, los otros 14 `requirements`; todos con ficha.
  · 8 operativos `not-applicable-by-category` (== filas con category operations-reporting), `from_operative`;
    9 de sustrato con su estado declarado; 17 + 8 + 9 = 34 disjuntos.
  · `componentized` 19/34 (17 → ('lib/council.py', 'council member r1-r2 (ADR-0082)') + los 2 de siempre).
  · `council_members({})` 17 · `FULL=1` 25 en orden fijo (17 primero) · env tolerante · `full=` explícito gana.
  · `digest()` incluye los 34 (CAMBIA respecto a v1.2: declarado) y los 6 nichos; ENUM ⊇ membresía.
  · `membership_view()` == tabla + shas del catálogo; cards_without_row == []; rows_without_card == 3.
  · las notas que otros smokes leen siguen (ADR-0046 en html-report-emitter, SUSPENDIDO en investor-relations).
  · urlopen bloqueado y contado = 0. Sin BD, sin modelo.

Uso (máscara offline de siempre):  python rag_index/query_service/smoke_agent_matrix.py
"""
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "analysis" / "scripts"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

N_URLOPEN = [0]


def _blocked_urlopen(*a, **k):
    N_URLOPEN[0] += 1
    raise AssertionError("network blocked: NO-SPEND smoke")


urllib.request.urlopen = _blocked_urlopen

from lib import agent_matrix as am, catalog_cards as cc  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  -> {detail}" if detail else ""))


# golden del brief §5.1 (aprobado 2026-09-14), en su orden
MEMBERS_17 = [
    "causal-pruner", "sim-orchestrator", "benchmark-designer", "fitness-curator", "squidiff-in-silico-gate",
    "experiment-designer", "imaging-analyst", "marker-validator", "scrna-seq-analyst", "spatial-omics-analyst",
    "histology-reviewer", "cross-modality-integrator",
    "literature-monitor", "domain-knowledge-curator", "hypothesis-generator",
    "cross-field-bridge-agent",
    "regulatory-ethics-advisor",
]
OPERATIVES_8 = ["program-manager", "budget-tracker", "bwh-coordinator", "reagent-procurement",
                "ip-patent-watcher", "case-capture-elicitor", "risk-register-agent", "investor-relations-drafter"]
SUBSTRATE_9 = ["composite-auditor", "identifier-verification-gate", "reasoning-exposer", "calibration-tracker",
               "evaluation-runner", "retrospector", "accumulator", "html-report-emitter", "type-c-viz-emitter"]
ROWS_V12 = [   # las 29 filas de v1.2 @ 9d90c01 — ninguna se pierde
    "causal-pruner", "composite-auditor", "cross-field-bridge-agent", "experiment-designer",
    "regulatory-ethics-advisor", "html-report-emitter", "type-c-viz-emitter", "identifier-verification-gate",
    "reasoning-exposer", "calibration-tracker", "evaluation-runner", "scrna-seq-analyst", "spatial-omics-analyst",
    "histology-reviewer", "imaging-analyst", "cross-modality-integrator", "marker-validator", "hypothesis-generator",
    "literature-monitor", "ip-patent-watcher", "case-capture-elicitor", "accumulator", "program-manager",
    "budget-tracker", "risk-register-agent", "investor-relations-drafter", "sim-orchestrator", "benchmark-designer",
    "domain-knowledge-curator",
]
NEW_5 = ["bwh-coordinator", "fitness-curator", "reagent-procurement", "retrospector", "squidiff-in-silico-gate"]

# ── 1 · la tabla: 34 filas, category y card en todas ───────────────────────────────────────────────
check("MATRIX_VERSION 'v1.3' y MEMBERSHIP_VERSION 'cm-1'",
      am.MATRIX_VERSION == "v1.3" and am.MEMBERSHIP_VERSION == "cm-1" == am.COUNCIL_MEMBERSHIP["version"])
check("34 filas = 29 de v1.2 (ninguna perdida) + 5 nuevas exactas", len(am.AGENTS) == 34
      and set(ROWS_V12) <= set(am.AGENTS) and sorted(set(am.AGENTS) - set(ROWS_V12)) == NEW_5,
      f"n={len(am.AGENTS)} nuevas={sorted(set(am.AGENTS) - set(ROWS_V12))}")
check("ENUM ordenado con 34 nombres y ENUM ⊇ membresía (el planner ve los 34; digest CAMBIA — declarado)",
      am.ENUM == sorted(am.AGENTS) and len(am.ENUM) == 34 and set(MEMBERS_17) <= set(am.ENUM))
check("category en TODA fila ∈ vocabulario de 6 (== catalog_cards.CATEGORY_VOCABULARY)",
      all(r.get("category") in am.CATEGORIES for r in am.AGENTS.values())
      and tuple(am.CATEGORIES) == tuple(cc.CATEGORY_VOCABULARY))
check("card en TODA fila ∈ {'present','no-card-in-catalog'}; exactamente las 3 sin ficha",
      all(r.get("card") in am.CARD_STATES for r in am.AGENTS.values())
      and sorted(n for n, r in am.AGENTS.items() if r["card"] == "no-card-in-catalog")
      == ["html-report-emitter", "identifier-verification-gate", "type-c-viz-emitter"])
check("gate ∈ {hard-rule, required, recommended} en las 34; las 5 nuevas 'recommended' (provisional, §3)",
      all(r["gate"] in am.GATES for r in am.AGENTS.values())
      and all(am.AGENTS[n]["gate"] == "recommended" for n in NEW_5))
check("toda fila conserva las llaves de v1.2 (gate, signal, pattern, evidence, componentized, note)",
      all({"gate", "signal", "pattern", "evidence", "componentized", "note"} <= set(r) for r in am.AGENTS.values()))

# ── 2 · category de la matriz vs sección del catálogo: coincide o se DECLARA ───────────────────────
diverge = sorted(n for n, r in am.AGENTS.items()
                 if r["card"] == "present" and r["category"] != cc.CARDS[n]["category"])
check("category == sección del catálogo en 27 de 31 fichas con fila; las 4 divergencias son operativos y llevan "
      "category_note que nombra la sección del catálogo",
      diverge == ["bwh-coordinator", "case-capture-elicitor", "ip-patent-watcher", "reagent-procurement"]
      and all(am.AGENTS[n].get("category_note") and cc.CARDS[n]["category"] in am.AGENTS[n]["category_note"]
              for n in diverge)
      and not any(am.AGENTS[n].get("category_note") for n in am.AGENTS if n not in diverge), f"{diverge}")
check("los 17 miembros tienen category == sección del catálogo (sin divergencias en la membresía)",
      all(am.AGENTS[m]["category"] == cc.CARDS[m]["category"] for m in MEMBERS_17))
check("las 3 filas sin ficha son substrate-instrumentation (los 9 de sustrato viven ahí)",
      all(am.AGENTS[n]["category"] == "substrate-instrumentation"
          for n in ("html-report-emitter", "identifier-verification-gate", "type-c-viz-emitter")))

# ── 3 · COUNCIL_MEMBERSHIP cm-1: los 17 exactos, en orden, con modos por tabla ─────────────────────
M = am.COUNCIL_MEMBERSHIP["members"]
check("members == los 17 nombres EXACTOS del brief §5.1 en su orden FIJO (identidad de la agregación)",
      list(M) == MEMBERS_17 and list(am.MEMBERS) == MEMBERS_17, f"{list(M)}")
groups = {}
for e in M.values():
    groups[e["group"]] = groups.get(e["group"], 0) + 1
check("grupos 5 compute / 7 lab / 3 knowledge / 1 cross-field / 1 flags",
      groups == {"compute": 5, "lab": 7, "knowledge": 3, "cross-field": 1, "flags": 1}, f"{groups}")
modes = {}
for e in M.values():
    modes[e["mode"]] = modes.get(e["mode"], 0) + 1
check("modos por tabla: requirements 14 · requirements-human-gated 1 · flags-only 1 · exploratory 1 (=17; el ADR "
      "escribió '13' — conteo MEDIDO)",
      modes == {"requirements": 14, "requirements-human-gated": 1, "flags-only": 1, "exploratory": 1}
      and all(e["mode"] in am.COUNCIL_MEMBERSHIP["modes"] for e in M.values()), f"{modes}")
check("causal-pruner: mode requirements-human-gated, hard_rule_gate True, rule cita §7 :146 y el 400 del ledger",
      M["causal-pruner"]["mode"] == "requirements-human-gated" and M["causal-pruner"]["hard_rule_gate"] is True
      and "§7" in M["causal-pruner"]["rule"] and "hard_rule_requirements_undecided" in M["causal-pruner"]["rule"])
check("hard_rule_gate True SÓLO en causal-pruner (miembros y operativos)",
      [n for n, e in M.items() if e["hard_rule_gate"]] == ["causal-pruner"]
      and not any(e["hard_rule_gate"] for e in am.COUNCIL_MEMBERSHIP["operatives"].values()))
check("regulatory-ethics-advisor: flags-only → tool emit_flags (el gate 'human' lo pone el código)",
      M["regulatory-ethics-advisor"]["mode"] == "flags-only" and M["regulatory-ethics-advisor"]["tool"] == "emit_flags"
      and "emit_flags" in M["regulatory-ethics-advisor"]["rule"])
check("cross-field-bridge-agent: exploratory True (must → should con priority_downgraded_from, §7 Test 5)",
      M["cross-field-bridge-agent"]["mode"] == "exploratory" and M["cross-field-bridge-agent"]["exploratory"] is True
      and "priority_downgraded_from" in M["cross-field-bridge-agent"]["rule"]
      and [n for n, e in M.items() if e["exploratory"]] == ["cross-field-bridge-agent"])
check("los otros 14: mode requirements, tool emit_information_requirements, sin hard_rule ni exploratory",
      all(e["mode"] == "requirements" and e["tool"] == "emit_information_requirements"
          and not e["hard_rule_gate"] and not e["exploratory"]
          for n, e in M.items() if n not in ("causal-pruner", "regulatory-ethics-advisor", "cross-field-bridge-agent")))
check("from_operative False en los 17; cada miembro tiene ficha ('present') y su ficha ∈ CARDS",
      all(e["from_operative"] is False for e in M.values())
      and all(am.AGENTS[m]["card"] == "present" and m in cc.CARDS for m in MEMBERS_17))

# ── 4 · los 8 operativos y los 9 de sustrato ───────────────────────────────────────────────────────
OPS = am.COUNCIL_MEMBERSHIP["operatives"]
check("operatives == los 8 exactos del brief, from_operative True, tool emit_information_requirements",
      list(OPS) == OPERATIVES_8 and list(am.OPERATIVES) == OPERATIVES_8
      and all(e["from_operative"] is True and e["tool"] == "emit_information_requirements" for e in OPS.values()))
check("not_applicable_by_category == ('operations-reporting',) y == el conjunto de filas con esa category (por TABLA)",
      am.COUNCIL_MEMBERSHIP["not_applicable_by_category"] == ("operations-reporting",)
      and set(n for n, r in am.AGENTS.items() if r["category"] in am.COUNCIL_MEMBERSHIP["not_applicable_by_category"])
      == set(OPERATIVES_8))
SUB = am.COUNCIL_MEMBERSHIP["substrate"]
check("substrate == los 9 exactos con estado declarado no vacío",
      set(SUB) == set(SUBSTRATE_9) and len(SUB) == 9 and all(isinstance(s, str) and s for s in SUB.values()))
check("estados reales: composite-auditor / identifier-verification-gate 'invoked (component)' y componentizados; "
      "accumulator 'replaced-by-code'; reasoning-exposer 'absorbed'; calibration/evaluation 'tapón 4/5'; "
      "html/type-c 'derogated (ADR-0046)'; retrospector 'agent-session only (ADR-0009)'",
      SUB["composite-auditor"] == SUB["identifier-verification-gate"] == "invoked (component)"
      and am.AGENTS["composite-auditor"]["componentized"] and am.AGENTS["identifier-verification-gate"]["componentized"]
      and SUB["accumulator"].startswith("replaced-by-code") and SUB["reasoning-exposer"].startswith("absorbed")
      and SUB["calibration-tracker"] == SUB["evaluation-runner"] == "tapón 4/5 (not in webapp run)"
      and SUB["html-report-emitter"] == SUB["type-c-viz-emitter"] == "derogated (ADR-0046)"
      and SUB["retrospector"] == "agent-session only (ADR-0009)" == am.AGENTS["retrospector"]["note"])
check("17 + 8 + 9 = 34 y los tres conjuntos son DISJUNTOS y cubren la matriz",
      set(MEMBERS_17) | set(OPERATIVES_8) | set(SUBSTRATE_9) == set(am.AGENTS)
      and not (set(MEMBERS_17) & set(OPERATIVES_8)) and not (set(MEMBERS_17) & set(SUBSTRATE_9))
      and not (set(OPERATIVES_8) & set(SUBSTRATE_9)))

# ── 5 · componentized 19/34 ─────────────────────────────────────────────────────────────────────────
comp = sorted(n for n, r in am.AGENTS.items() if r["componentized"])
check("componentized 19/34: los 17 miembros + composite-auditor + identifier-verification-gate (antes 2/29)",
      len(comp) == 19 and set(comp) == set(MEMBERS_17) | {"composite-auditor", "identifier-verification-gate"},
      f"n={len(comp)}")
check("los 17 llevan EXACTAMENTE ('lib/council.py', 'council member r1-r2 (ADR-0082)')",
      all(am.AGENTS[m]["componentized"] == ("lib/council.py", "council member r1-r2 (ADR-0082)") for m in MEMBERS_17)
      and am.COUNCIL_COMPONENT == ("lib/council.py", "council member r1-r2 (ADR-0082)"))
check("operativos y sustrato (salvo los 2 componentes de siempre) siguen componentized None",
      all(am.AGENTS[n]["componentized"] is None for n in OPERATIVES_8)
      and all(am.AGENTS[n]["componentized"] is None for n in SUBSTRATE_9
              if n not in ("composite-auditor", "identifier-verification-gate")))

# ── 6 · council_members: 17 | 25, orden fijo, env tolerante ─────────────────────────────────────────
check("council_members({}) → los 17 en orden fijo", am.council_members({}) == MEMBERS_17)
check("council_members(FULL=1) → 25 = los 17 primero + los 8 operativos en su orden",
      am.council_members({"WITT_COUNCIL_FULL": "1"}) == MEMBERS_17 + OPERATIVES_8)
check("env tolerante: 'true'/'yes'/'on' → 25; ''/'0'/'false'/'basura' → 17 (default DECLARADO)",
      all(len(am.council_members({"WITT_COUNCIL_FULL": v})) == 25 for v in ("true", "YES", "on"))
      and all(len(am.council_members({"WITT_COUNCIL_FULL": v})) == 17 for v in ("", "0", "false", "basura"))
      and "unparseable" in am.council_full({"WITT_COUNCIL_FULL": "basura"})[1]
      and "unset" in am.council_full({})[1])
check("full= explícito GANA sobre la env (la corrida usa la N congelada en el plan, F.4)",
      am.council_members({"WITT_COUNCIL_FULL": "1"}, full=False) == MEMBERS_17
      and am.council_members({}, full=True) == MEMBERS_17 + OPERATIVES_8
      and am.council_full({}, full=True)[1].startswith("explicit"))
check("council_size 17 / 25 y el cuórum 0.6 daría 11 / 15 (ceil) — la fracción la aplica council.py (C2)",
      am.council_size({}) == 17 and am.council_size({}, full=True) == 25
      and -(-17 * 6 // 10) == 11 and -(-25 * 6 // 10) == 15)
cm = am.council_member("causal-pruner")
check("council_member(name): entrada con agent, seat 'member', mode, group, category, gate, card, componentized",
      cm["agent"] == "causal-pruner" and cm["seat"] == "member" and cm["mode"] == "requirements-human-gated"
      and cm["category"] == "compute-simulation" and cm["gate"] == "hard-rule" and cm["card"] == "present"
      and cm["componentized"] == am.COUNCIL_COMPONENT)
check("council_member de un operativo: seat 'operative (full-council only)', from_operative True; sustrato → None",
      am.council_member("budget-tracker")["seat"].startswith("operative")
      and am.council_member("budget-tracker")["from_operative"] is True
      and am.council_member("composite-auditor") is None and am.council_member("nadie") is None)

# ── 7 · digest / resolve: el planner ve los 34 (declarado) y los nichos siguen ─────────────────────
d = am.digest()
check("digest() lista los 34 nombres con su gate y señal (CAMBIA vs v1.2 → PLAN_VERSION '4', dueño C5)",
      all(f"  - {n} ({am.AGENTS[n]['gate']}): " in d for n in am.AGENTS) and d.count("\n  - ") == 34 + 6)
check("digest() conserva los 6 nichos §3 y NO viaja gate como salida ni componentización",
      all(f"  - {c}: {am.NICHES[c]['name']}" in d for c in am.NICHE_ENUM) and "componentized" not in d)
check("resolve() resuelve las 5 filas nuevas y None fuera de matriz",
      all(am.resolve(n) is am.AGENTS[n] for n in NEW_5) and am.resolve("nadie") is None)
check("notas que otros gates leen siguen intactas: ADR-0046 (html-report-emitter), SUSPENDIDO (investor-relations)",
      "ADR-0046" in am.AGENTS["html-report-emitter"]["note"]
      and "SUSPENDIDO" in am.AGENTS["investor-relations-drafter"]["note"])
check("nueva fila squidiff-in-silico-gate: señal del catálogo, evidence test_1/test_4, nota 'sólo emite requisitos'",
      "Squidiff" in am.AGENTS["squidiff-in-silico-gate"]["signal"]
      and am.AGENTS["squidiff-in-silico-gate"]["evidence"] == ["test_1", "test_4"]
      and "requisitos" in am.AGENTS["squidiff-in-silico-gate"]["note"])
check("nueva fila retrospector: note 'agent-session only (ADR-0009)' y evidence test_3/test_1/test_4",
      am.AGENTS["retrospector"]["note"] == "agent-session only (ADR-0009)"
      and set(am.AGENTS["retrospector"]["evidence"]) == {"test_1", "test_3", "test_4"})

# ── 8 · membership_view: lo que servirá GET /council/membership (C6) ───────────────────────────────
v = am.membership_view({})
check("membership_view: cm-1 · v1.3 · catalog_sha == catalog_cards.CATALOG_SHA · n_members 17 · full False",
      v["membership_version"] == "cm-1" and v["matrix_version"] == "v1.3" and v["catalog_sha"] == cc.CATALOG_SHA
      and v["catalog_state"] == "parsed" and v["n_members"] == 17 and v["full_council"] is False
      and v["full_council_env"] == "WITT_COUNCIL_FULL")
check("members[] en orden fijo con card_sha == CARDS[agent].sha, group, mode, tool, gate, hard_rule_gate",
      [m["agent"] for m in v["members"]] == MEMBERS_17
      and all(m["card_sha"] == cc.CARDS[m["agent"]]["sha"] and m["card"] == "present" for m in v["members"])
      and all({"group", "mode", "tool", "gate", "hard_rule_gate", "exploratory", "from_operative", "category",
               "componentized"} <= set(m) for m in v["members"]))
check("not_applicable[] = los 8 con estado declarado; substrate[] = 9; cards_without_row == []; rows_without_card == 3",
      [x["agent"] for x in v["not_applicable"]] == OPERATIVES_8 and len(v["substrate"]) == 9
      and v["cards_without_row"] == [] and len(v["rows_without_card"]) == 3
      and v["n_rows"] == 34 and v["n_componentized"] == 19)
vf = am.membership_view({"WITT_COUNCIL_FULL": "1"})
check("membership_view(FULL=1): 25 miembros, los 8 con from_operative True y not_applicable vacío",
      vf["n_members"] == 25 and vf["full_council"] is True and vf["not_applicable"] == []
      and sum(1 for m in vf["members"] if m["from_operative"]) == 8)
vi = am.membership_view({}, cards={n: cc.CARDS[n] for n in list(cc.CARDS)[:3]})
check("membership_view con cards INYECTADAS: catalog_state 'injected', card_sha None declarado donde no hay ficha",
      vi["catalog_state"] == "injected" and any(m["card_sha"] is None for m in vi["members"]))

# ── 9 · NO-SPEND ───────────────────────────────────────────────────────────────────────────────────
check("urlopen bloqueado y contado = 0 (sin red, sin modelo, sin BD)", N_URLOPEN[0] == 0, f"n={N_URLOPEN[0]}")

n_pass = sum(CHECKS)
print(f"\n{n_pass}/{len(CHECKS)} PASS")
sys.exit(0 if n_pass == len(CHECKS) else 1)

"""
smoke_council_index.py — gate NO-SPEND del ÍNDICE DEL CONSEJO (ADR-0082 (I); rebanada C7).

Mide, no supone (corpus SINTÉTICO en la SQLite de la máscara; cero red, cero modelo, cero DI):
  · corpus = corridas CLOSED del alcance de origen (2 production, 1 smoke EXCLUIDA y CONTADA, 1 sin cerrar
    fuera, 1 cerrada sin registro congelado contada) + planes con `council_json` (1 nunca corrido, 1 consumido
    por una corrida indexada → excluido y contado, 1 de origen smoke → excluido, 1 con origin NULL → incluido
    y declarado); ANTES de simular la columna de C4, `plans_state 'not-available (…E.1 pending)'` declarado.
  · ítems por kind (requirement / coverage / decision / gap_flag / alternative / panel_finding / comment) con
    sus conteos exactos; `decision` SIN la razón humana, SIN el texto atestiguado, SIN el user_id; la
    rationale de un voto ANULADO jamás es el texto de la cobertura; una corrida sin `council` aporta sólo
    gap_flags / alternatives / hallazgos.
  · letras `A..` secuenciales, `admissible_as_evidence false` en el 100 %, `validate_disjoint` acepta la serie;
    scorer DECLARADO (sparse-tfidf con sklearn · stdlib-tfidf-fallback forzado por monkeypatch) y el ranking
    sigue; `kinds` y `filters` cerrados (400 fuera del enum), `q` vacía 400, k clamp 1..50.
  · `prior_observations`: default k=5 sin `comment`, letras `P-A…`, SÓLO campos estructurados; con
    WITT_COUNCIL_PRIOR_KINDS=comment entran con autor y ≤280; PRIOR_K clamp 0..12 (99→12, basura→5, 0→disabled).
  · kill-switch WITT_COUNCIL_INDEX=0: search → CouncilIndexDisabled 503, prior_observations 'disabled',
    demand sigue contando con `index_enabled false`.
  · `demand()`: conteos exactos por familia (web 1 · tooluniverse 2 · figure 1), `harness_state` de C2 al
    lado, `fired` false con 3 unidades; al cruzar el umbral (5 corridas, ≥3 tooluniverse) `fired` true SÓLO
    para tooluniverse; `n_runs_with_tooluniverse_uncovered` 4.
  · reconstrucción del índice al cambiar la llave (n_builds +1 exactamente) y NO al repetir la búsqueda.
  · `_panel_findings` espejo == runs._panel_findings; membership() con card_sha == catalog_cards.
  · ADR-0084 (W6 — F.3): `DEMAND_FAMILIES` ESTÁTICA ('figure', 'tooluniverse', 'web') — la web se sigue CONTANDO como
    demanda aunque haya llave (la serie medida no se rompe); `unsatisfiable_families(env)` derivada EN LA LLAMADA
    (('tooluniverse', 'web') bajo off · ('tooluniverse',) con llave fake); `demand()` += `web_locator_provider_state
    {provider, provider_source, available, unavailable_reason}` + `unsatisfiable_families_source` + `demand_families_rule`;
    bajo off el literal es byte-idéntico a 7d9ce15 ('tool-unavailable (ADR-0084)').
  · urlopen bloqueado y contado = 0.

Uso (máscara offline de siempre; UNA .db por smoke):
  WITT_BACKEND_DB_URL=sqlite:///…/adr82-smoke_council_index.db NEO4J_URI= RAG_BACKEND=sparse OPENAI_API_KEY= \
  ANTHROPIC_API_KEY= WITT_RUN_ORIGIN=smoke python rag_index/query_service/smoke_council_index.py
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ── máscara offline (los defaults sólo aplican si el orquestador no la fijó) ────────────────────────────
_SMOKES = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Temp" / "claude" / "witt-smokes"
if not os.environ.get("WITT_BACKEND_DB_URL"):
    _SMOKES.mkdir(parents=True, exist_ok=True)
    _DB = _SMOKES / "adr82-smoke_council_index.db"
    if _DB.exists():
        _DB.unlink()
    os.environ["WITT_BACKEND_DB_URL"] = f"sqlite:///{_DB.as_posix()}"
os.environ["NEO4J_URI"] = ""
os.environ.pop("NEO4J_URI", None)
os.environ.setdefault("RAG_BACKEND", "sparse")
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ.setdefault("WITT_RUN_ORIGIN", "smoke")
os.environ.setdefault("WITT_ALLOW_RUNS_OFFLINE", "1")
for _v in ("WITT_COUNCIL_INDEX", "WITT_COUNCIL_PRIOR_K", "WITT_COUNCIL_PRIOR_KINDS", "WITT_COUNCIL_INDEX_ORIGINS"):
    os.environ.pop(_v, None)   # el smoke mide los DEFAULTS y pasa env explícitas por parámetro

N_URLOPEN = [0]


def _blocked_urlopen(*a, **k):
    N_URLOPEN[0] += 1
    raise AssertionError("network blocked: NO-SPEND smoke")


urllib.request.urlopen = _blocked_urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "analysis" / "scripts"))
import db  # noqa: E402
import precedent  # noqa: E402
import council_index as ci  # noqa: E402
from lib import catalog_cards as cc, models, search_harness  # noqa: E402
# ids de modelo del fixture de panel LEÍDOS de la tabla g2 (cero literales fuera de models.py — gate M.4 de ADR-0081)
_G2 = models.GENERATIONS["g2-2026-09"]["defaults"]
JUDGE_ANTHROPIC, JUDGE_OPENAI = _G2["judge.correctness"], _G2["judge.reproducibility"]
from sqlalchemy import text as sa_text  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  -> {detail}" if detail else ""))


def _err(fn, *a, **kw):
    try:
        fn(*a, **kw)
        return None
    except ci.CouncilIndexError as e:
        return e


# ── fixtures ─────────────────────────────────────────────────────────────────────────────────────────────
RUN_A, RUN_B, RUN_C, RUN_D, RUN_F = "a" * 32, "b" * 32, "c" * 32, "d" * 32, "f" * 32
RID_A, RID_B, RID_C, RID_D, RID_E = ("req-aaaa00000001", "req-bbbb00000002", "req-cccc00000003",
                                     "req-dddd00000004", "req-eeee00000005")
SECRET_REASON = "SECRETO-RAZON preprints are not admissible for this question"
SECRET_ATTEST = "SECRETO-ATESTIGUADO ENSDARG00000099999 is annotated in the lab notebook"
ANNULLED_RATIONALE = "HALLUCINATED-RATIONALE must never be the coverage text"


def _req(rid, gap, family, kind, priority, requested_by, harness_state="satisfiable", decision="keep",
         decided_by="human:natalia", **extra):
    r = {"requirement_id": rid, "gap": gap, "evidence_kind": kind, "source_family": family,
         "query_en": gap.lower(), "variants": [], "entities": extra.pop("entities", []),
         "entities_resolved": [], "entities_unresolved": [], "acceptance_test": "an item of that kind exists",
         "priority": priority, "requested_by": requested_by, "n_requested_by": len(requested_by), "n_members": 17,
         "hard_rule_gate": False, "exploratory": False, "from_operative": False, "harness_state": harness_state,
         "decision": decision, "decided_by": decided_by, "decided_at": "2026-09-15T10:00:00"}
    r.update(extra)
    return r


REQS_A = [
    _req(RID_A, "Need the wt1a expression pattern in the pronephros at 24 hpf", "zfin_expression", "expression",
         "must", ["marker-validator", "imaging-analyst"], entities=["wt1a"]),
    _req(RID_B, "Need a web search for recent preprints on wt1a knockdown", "web", "web", "should",
         ["literature-monitor"], harness_state="unsatisfiable-by-harness (tool-unavailable (ADR-0084))",
         decision="discard", decision_reason=SECRET_REASON),
    _req(RID_C, "Need a ToolUniverse gene ontology lookup for wt1a", "tooluniverse", "paper", "must",
         ["domain-knowledge-curator"], harness_state="unsatisfiable-by-harness (tool-unavailable (ADR-0085))",
         decision="aporto", attested_text=SECRET_ATTEST),
    _req(RID_D, "Need the figure panel showing glomerular filtration at 48 hpf", "europepmc", "figure", "must",
         ["histology-reviewer"], harness_state="unsatisfiable-by-harness (evidence_kind figure — ADR-0083)",
         decided_by="default-keep"),
    _req(RID_E, "Need causal ranking inputs: pax2a knockdown phenotype series", "zfin", "phenotype", "must",
         ["causal-pruner"], decision="pending", decided_by="gate-human-pending", hard_rule_gate=True),
]
COUNCIL_A = {
    "state": "applicable", "module_version": "council-1", "membership_version": "cm-1",
    "catalog_sha": cc.CATALOG_SHA,
    "ledger": {"plan_id": "p2", "state": "approved", "requirements": REQS_A, "flags": []},
    "coverage": {
        "pre_search": {"state": "judged", "by_requirement": [
            {"requirement_id": RID_A, "priority": "must", "coverage_final": "partial", "n_valid_votes": 1,
             "votes": [
                 {"agent": "imaging-analyst", "coverage": "covered", "evidence_ids": ["PMID:999"], "annulled": True,
                  "hallucinated_evidence_ids": ["PMID:999"], "rationale": ANNULLED_RATIONALE},
                 {"agent": "marker-validator", "coverage": "partial", "evidence_ids": ["PMID:1"], "annulled": False,
                  "hallucinated_evidence_ids": [],
                  "rationale": "Only a whole-mount ISH at 48 hpf was found; the 24 hpf timepoint is missing"}]},
            {"requirement_id": RID_C, "priority": "must", "coverage_final": "covered-by-attestation",
             "n_valid_votes": 0, "votes": []},
            {"requirement_id": RID_D, "priority": "must", "coverage_final": "not-judged", "n_valid_votes": 0,
             "votes": []}]},
        "post_search": {"state": "not-run (all must covered)"},
    },
}
AUDIT_A = {"verdict": "REVISE", "panel": [
    {"lens": "faithfulness", "reviewer": JUDGE_ANTHROPIC, "verdict": "REVISE",
     "caught": "cites a 48 hpf ISH panel as 24 hpf evidence", "correction_applied": "", "reasons": ["timepoint mismatch"]},
    {"lens": "domain", "reviewer": JUDGE_OPENAI, "verdict": "APPROVE", "caught": "", "reasons": []}]}
AUDIT_OK = {"verdict": "APPROVE", "panel": [{"lens": "domain", "reviewer": JUDGE_OPENAI, "verdict": "APPROVE", "caught": "", "reasons": []}]}
AUDIT_B = {"verdict": "APPROVE_MINOR", "panel": [
    {"lens": "domain", "reviewer": JUDGE_OPENAI, "verdict": "APPROVE_MINOR", "caught": "overstates penetrance of pax2a",
     "correction_applied": "", "reasons": []}]}


def _mk_run(run_id, question, frozen, state="closed", origin="production", **turn):
    db.create_run(run_id, "natalia", question, origin=origin, **turn)
    values = {"state": state}
    if frozen is not None:
        values["frozen_record_json"] = json.dumps(frozen, ensure_ascii=False)
    if state == "closed":
        values.update(frozen_at=db._now(), closed_by="natalia")
    db.update_run(run_id, **values)


def _frozen(answer, gap_flags, alternatives, audit, council=None, contract="1.11"):
    rec = {"render_contract_version": contract,
           "answer": {"direct_answer": answer, "gap_flags": gap_flags, "stated_confidence": 0.6},
           "alternatives_considered": alternatives, "audit": audit, "confidence": {"final": 0.6},
           "decision_state": {"state": "AUDIT_" + audit["verdict"]}}
    if council is not None:
        rec["council"] = council
    return rec


db.init_db()
db.upsert_user("natalia", "Natalia", "medico", "pw-natalia-123")
db.upsert_user("emmanuel", "Emmanuel", "dev", "pw-emmanuel-123")

# ── 0. superficie E.1 REAL (db.init_db → _migrate) y sin corpus: estados DECLARADOS ──────────────────────
# C9: la columna plans.council_json existe desde db.init_db (C4); `_plans_rows` lee por db.plans_with_council y declara
# 'not-available (…)' SÓLO si db.council_schema_state la reporta ausente (BD sin migrar) — se mide simulando ese estado.
schema0 = db.council_schema_state()
rows0, meta0 = ci._plans_rows(("production",))
check("0a. la BD del gate tiene la superficie E.1 (council_schema_state ready) y sin planes con ronda 1 → plans_state 'empty' "
      "(tres estados: 'empty' ≠ 'not-available')",
      schema0["ready"] is True and rows0 == [] and meta0["state"] == "empty" and meta0["n_rows"] == 0,
      json.dumps({"ready": schema0["ready"], "state": meta0["state"]}))
_real_schema_state = db.council_schema_state
db.council_schema_state = lambda: {"plans_missing": ["council_json"], "runs_missing": [], "plan_events_table": True, "ready": False}
rows_na, meta_na = ci._plans_rows(("production",))
db.council_schema_state = _real_schema_state
check("0a'. BD SIN la columna (council_schema_state simulado) → plans_state 'not-available (…)' declarado, rows [] — jamás un except silencioso",
      rows_na == [] and meta_na["state"] == ci.PLANS_STATE_NOT_AVAILABLE and meta_na["n_rows"] == 0, meta_na["state"])
r0 = ci.search("anything")
check("0b. corpus vacío: corpus_state 'empty-corpus', items [], scorer declarado, plans_state 'empty' (columna presente, 0 planes)",
      r0["corpus_state"] == "empty-corpus" and r0["items"] == [] and r0["scorer"] in ci.SCORERS
      and r0["plans_state"] == "empty" and r0["n_runs_indexed"] == 0,
      f"scorer={r0['scorer']} plans_state={r0['plans_state']}")
p0 = ci.prior_observations("anything")
check("0c. prior_observations sin corpus → state 'empty-corpus', n 0, k 5 default, kinds default sin comment",
      p0["state"] == "empty-corpus" and p0["n"] == 0 and p0["k"] == 5 and "comment" not in p0["kinds"]
      and p0["kinds"] == list(ci.PRIOR_KINDS_DEFAULT), json.dumps({"state": p0["state"], "kinds": p0["kinds"]}))

# (C9) La migración E.1 la hizo db.init_db (columnas reales de C4: council_json, origin, council_state VARCHAR(96)) —
# el ALTER simulado de la ventana "C4 pendiente" se retiró; los planes del corpus se escriben en las columnas reales.

# ── corpus sintético ──────────────────────────────────────────────────────────────────────────────────────
_mk_run(RUN_A, "Is wt1a required for zebrafish pronephros development at 24 hpf?",
        _frozen("The DI lacks a 24 hpf wt1a timepoint.", ["no 24 hpf timepoint in the DI for wt1a"],
                ["wt1b compensates for wt1a loss in the pronephros"], AUDIT_A, council=COUNCIL_A),
        thread_id=RUN_A, turn_no=1, turn_kind="root")
_mk_run(RUN_B, "What does pax2a do in pronephric tubule differentiation?",
        _frozen("pax2a is required for tubule differentiation.", ["pax2a data limited to 48 hpf"],
                ["osr1 acts upstream of pax2a"], AUDIT_B, contract="1.10"))
_mk_run(RUN_C, "smoke-origin question about wt1a pronephros",
        _frozen("smoke answer", [], [], AUDIT_B,
                council={"state": "applicable", "ledger": {"plan_id": "p3", "requirements": [
                    _req("req-smok00000009", "Need a web search on wt1a smoke", "web", "web", "must",
                         ["literature-monitor"], harness_state="unsatisfiable-by-harness (tool-unavailable (ADR-0084))")]}}),
        origin="smoke")
_mk_run(RUN_D, "awaiting closure question about wt1a pronephros", _frozen("pending", [], [], AUDIT_B, council=COUNCIL_A),
        state="awaiting_closure")
_mk_run(RUN_F, "closed but without frozen record (tolerance)", None)
db.create_run_comment("cm1", RUN_A, "natalia", "We should check the 24 hpf ISH in the Drummond lab atlas.")
LONG_COMMENT = ("Long comment about wt1a pronephros " * 12).strip()
assert len(LONG_COMMENT) > 280
db.create_run_comment("cm2", RUN_A, "emmanuel", LONG_COMMENT)

LONG_GAP = ("Need lhx1a literature on pronephros induction " * 8).strip()
assert len(LONG_GAP) > 300
PLANS = {
    "p1": ("production", None, {"requirements": [
        _req("req-pppp00000006", "Need a ToolUniverse pathway lookup for osr1", "tooluniverse", "paper", "must",
             ["domain-knowledge-curator"], harness_state="unsatisfiable-by-harness (tool-unavailable (ADR-0085))",
             decision=None, decided_by=None),
        _req("req-qqqq00000007", "Need the osr1 mutant pronephros phenotype", "zfin", "phenotype", "must",
             ["experiment-designer"], decision=None, decided_by=None)], "aggregation_sha": "deadbeef"}),
    "p2": ("production", RUN_A, {"requirements": REQS_A}),                     # consumido por RUN_A (indexada)
    "p3": ("smoke", None, {"requirements": [_req("req-ssss00000008", "smoke plan web need", "web", "web", "must",
                                                 ["literature-monitor"], decision=None, decided_by=None)]}),
    "p4": (None, None, {"r1": {"aggregation": {"requirements": [
        _req("req-rrrr00000010", LONG_GAP, "europepmc", "paper", "should", ["literature-monitor"],
             decision=None, decided_by=None)]}}}),
}
for pid, (origin, run_id, cj) in PLANS.items():
    db.create_plan(pid, "natalia", f"plan question {pid}", ["wt1a"], json.dumps({"plan_version": "4"}))
    with db.engine().begin() as cx:
        cx.execute(sa_text("UPDATE plans SET council_json=:cj, origin=:o, run_id=:r, council_state='applicable' "
                           "WHERE plan_id=:p"), {"cj": json.dumps(cj, ensure_ascii=False), "o": origin, "r": run_id, "p": pid})
ci._IDX["key"] = None

# ── 1. corpus: alcance por origen, planes, conteos por kind ───────────────────────────────────────────────
items, meta = ci._corpus()
check("1a. corridas: 3 closed en alcance (A, B, F), 2 indexadas (F sin frozen contada), smoke EXCLUIDA y contada, "
      "awaiting_closure fuera",
      meta["n_runs_closed_in_scope"] == 3 and meta["n_runs_indexed"] == 2 and meta["n_runs_frozen_absent"] == 1
      and meta["excluded_by_origin"] == {"smoke": 1} and meta["origins_included"] == ["production"],
      json.dumps({k: meta[k] for k in ("n_runs_closed_in_scope", "n_runs_indexed", "n_runs_frozen_absent", "excluded_by_origin")}))
check("1b. council: 1 con ledger (A), 1 ausente (B, contrato 1.10) — declarados por separado",
      meta["n_runs_council_with_ledger"] == 1 and meta["n_runs_council_absent"] == 1
      and meta["n_runs_council_without_ledger"] == 0)
check("1c. planes: 3 filas con council_json en alcance (p1, p2, p4), p3 excluido por origen, p2 excluido por "
      "consumido por corrida indexada, p4 origin NULL incluido y declarado → 2 indexados",
      meta["plans_state"] == "indexed" and meta["n_plans_indexed"] == 2
      and meta["n_plans_excluded_consumed_by_indexed_run"] == 1 and meta["plans_excluded_by_origin"] == {"smoke": 1}
      and meta["plans_origin_unknown_included"] == 1,
      json.dumps({k: meta[k] for k in ("n_plans_indexed", "n_plans_excluded_consumed_by_indexed_run",
                                       "plans_excluded_by_origin", "plans_origin_unknown_included")}))
by_kind = meta["n_items_by_kind"]
check("1d. ítems por kind EXACTOS: requirement 8 (A5+p1 2+p4 1) · coverage 3 · decision 4 (pending fuera) · "
      "gap_flag 2 · alternative 2 · panel_finding 2 (APPROVE fuera) · comment 2",
      by_kind == {"requirement": 8, "coverage": 3, "decision": 4, "gap_flag": 2, "alternative": 2,
                  "panel_finding": 2, "comment": 2} and meta["n_items_indexed"] == 23, json.dumps(by_kind))
blob = json.dumps([ci._public(i) for i in items], ensure_ascii=False)
check("1e. la razón humana, el texto atestiguado y la rationale del voto ANULADO NO están en ningún ítem",
      "SECRETO" not in blob and "ENSDARG00000099999" not in blob and "HALLUCINATED-RATIONALE" not in blob)
decisions = [i for i in items if i["kind"] == "decision"]
check("1f. decision = {requirement_id, decision, gap ≤200, decided_by_kind}: 4 decisiones, kinds ∈ {human, "
      "default-keep}, sin user_id, sin decision_reason/attested_text",
      sorted(d["decision"] for d in decisions) == ["aporto", "discard", "keep", "keep"]
      and {d["decided_by_kind"] for d in decisions} == {"human", "default-keep"}
      and "natalia" not in json.dumps(decisions).lower()
      and all("decision_reason" not in d and "attested_text" not in d and len(d["text"]) <= 200 for d in decisions))
cov = {i["requirement_id"]: i for i in items if i["kind"] == "coverage"}
check("1g. coverage: rationale del primer voto VÁLIDO (no del anulado) para req-aaaa; not-judged sin rationale → "
      "texto 'gap — not-judged' con rationale_present false; covered-by-attestation presente; fase pre_search",
      cov[RID_A]["text"].startswith("Only a whole-mount ISH") and cov[RID_A]["rationale_present"] is True
      and cov[RID_D]["rationale_present"] is False and cov[RID_D]["text"].endswith("— not-judged")
      and cov[RID_C]["coverage_final"] == "covered-by-attestation"
      and all(c["phase"] == "pre_search" for c in cov.values()) and len(cov) == 3)
b_items = [i for i in items if i["run_id"] == RUN_B]
check("1h. corrida SIN council (B) aporta sólo gap_flag / alternative / panel_finding (3 ítems)",
      len(b_items) == 3 and {i["kind"] for i in b_items} == {"gap_flag", "alternative", "panel_finding"})
pf = {i["run_id"]: i for i in items if i["kind"] == "panel_finding"}
check("1i. panel_finding: REVISE (A) con caught + reasons, APPROVE_MINOR (B); APPROVE no es hallazgo",
      pf[RUN_A]["verdict"] == "REVISE" and "timepoint mismatch" in pf[RUN_A]["text"] and pf[RUN_A]["n_reasons"] == 1
      and pf[RUN_B]["verdict"] == "APPROVE_MINOR" and len(pf) == 2)
p1 = [i for i in items if i["plan_id"] == "p1"]
p4 = [i for i in items if i["plan_id"] == "p4"]
check("1j. ítems de plan: p1 → 2 requirement con plan_id y run_id null; p4 leído por la ruta tolerante "
      "'r1.aggregation.requirements', origin None declarado, gap > 300 RECORTADO con text_truncated",
      len(p1) == 2 and all(i["kind"] == "requirement" and i["run_id"] is None for i in p1)
      and len(p4) == 1 and p4[0]["source"].endswith("r1.aggregation.requirements") and p4[0]["origin"] is None
      and p4[0]["text_truncated"] is True and len(p4[0]["text"]) == 300)
check("1k. _requirements_of tolerante: 'requirements' · 'ledger.requirements' · 'r1.aggregation.requirements' · {} → ([], None)",
      ci._requirements_of({"requirements": [{"a": 1}]})[1] == "requirements"
      and ci._requirements_of({"ledger": {"requirements": [{"a": 1}]}})[1] == "ledger.requirements"
      and ci._requirements_of({"r1": {"aggregation": {"requirements": []}}})[1] == "r1.aggregation.requirements"
      and ci._requirements_of({}) == ([], None) and ci._requirements_of(None) == ([], None))
check("1l. ítem de plan consumido: los requisitos de p2 (== A) NO se duplican (8 requirement, no 13)",
      by_kind["requirement"] == 8)

# ── 2. búsqueda: letras, admisibilidad, scorer, kinds, filtros ────────────────────────────────────────────
r = ci.search("wt1a expression pronephros 24 hpf", k=10)
check("2a. scorer DECLARADO ∈ SCORERS y corpus_state 'indexed'",
      r["scorer"] in ci.SCORERS and r["corpus_state"] == "indexed" and r["index_version"] == ci.INDEX_VERSION,
      r["scorer"])
try:
    import sklearn  # noqa: F401
    _has_sklearn = True
except Exception:
    _has_sklearn = False
check("2b. con sklearn presente el scorer es 'sparse-tfidf'; sin él, el fallback stdlib con su nombre",
      (r["scorer"] == "sparse-tfidf") == _has_sklearn, f"sklearn={_has_sklearn} scorer={r['scorer']}")
check("2c. letras A.. secuenciales, score > 0 decreciente, ≤ k",
      [i["l"] for i in r["items"]] == [precedent.letter_label(n) for n in range(1, len(r["items"]) + 1)]
      and all(i["score"] > 0 for i in r["items"]) and 0 < len(r["items"]) <= 10
      and all(r["items"][j]["score"] >= r["items"][j + 1]["score"] for j in range(len(r["items"]) - 1)))
check("2d. admissible_as_evidence false + why_not_admissible en el 100 %; validate_disjoint acepta la serie (letras, sin n)",
      all(i["admissible_as_evidence"] is False and i["why_not_admissible"] for i in r["items"])
      and precedent.validate_disjoint({"evidence": [{"n": 1}], "precedent": r["items"]}) is True)
check("2e. relevancia: el primer ítem es de wt1a/24 hpf (req-aaaa: requirement o coverage) de la corrida A",
      r["items"][0]["run_id"] == RUN_A and r["items"][0].get("requirement_id") == RID_A
      and r["items"][0]["kind"] in ("requirement", "coverage", "decision"),
      f"top={r['items'][0]['kind']} {r['items'][0].get('requirement_id')} score={r['items'][0]['score']}")
check("2f. el sobre declara alcance y conteos (origins_included, excluded_by_origin, n_runs/plans/comments, kinds)",
      r["origins_included"] == ["production"] and r["excluded_by_origin"] == {"smoke": 1}
      and r["n_runs_indexed"] == 2 and r["n_plans_indexed"] == 2 and r["n_comments_indexed"] == 2
      and r["kinds_included"] == list(ci.KINDS) and r["note"] == ci.DISJOINT_NOTE and "SECRETO" not in json.dumps(r))
rc = ci.search("wt1a pronephros Drummond atlas ISH", k=10, kinds="comment")
check("2g. kinds=comment → sólo comentarios con AUTOR (display name de la cuenta) y ≤280; el largo truncated",
      len(rc["items"]) == 2 and all(i["kind"] == "comment" and i["author"] in ("Natalia", "Emmanuel")
                                    and len(i["text"]) <= 280 for i in rc["items"])
      and any(i["text_truncated"] and len(i["text"]) == 280 for i in rc["items"])
      and rc["kinds_included"] == ["comment"])
e = _err(ci.search, "wt1a", kinds="bogus")
check("2h. kind fuera del enum → CouncilIndexError 400 unknown_kind con allowed",
      e is not None and e.status == 400 and e.detail["error"] == "unknown_kind" and e.detail["unknown"] == ["bogus"]
      and e.detail["allowed"] == list(ci.KINDS))
e = _err(ci.search, "   ")
check("2i. q vacía → 400 missing_q", e is not None and e.status == 400 and e.detail["error"] == "missing_q")
rf = ci.search("wt1a web preprints", k=20, filters={"source_family": "web"})
check("2j. filters {source_family: web} → sólo ítems web (requirement + decision de req-bbbb)",
      rf["items"] and all(i["source_family"] == "web" and i["requirement_id"] == RID_B for i in rf["items"])
      and {i["kind"] for i in rf["items"]} == {"requirement", "decision"} and rf["filters"] == {"source_family": "web"})
e = _err(ci.search, "wt1a", filters={"nope": 1})
check("2k. filtro desconocido → 400 unknown_filter", e is not None and e.status == 400 and e.detail["error"] == "unknown_filter")
rq = ci.search("pax2a knockdown phenotype series causal ranking", k=20, filters={"requested_by": "causal-pruner"})
check("2l. filters {requested_by} es pertenencia → el requisito hard_rule de causal-pruner (pending: sin decision item)",
      [i["requirement_id"] for i in rq["items"]] == [RID_E] and rq["items"][0]["hard_rule_gate"] is True)
check("2m. k clamp: k=0 → 1 ítem; k=999 → k 50",
      ci.search("wt1a pronephros", k=0)["k"] == 1 and len(ci.search("wt1a pronephros", k=0)["items"]) == 1
      and ci.search("wt1a", k=999)["k"] == 50)
rs = ci.search("wt1a pronephros smoke", k=5, include_origins="smoke")
check("2n. include_origins=smoke: el alcance CAMBIA (corrida C indexada, production excluida y contada), otra llave",
      rs["origins_included"] == ["smoke"] and rs["n_runs_indexed"] == 1 and rs["excluded_by_origin"].get("production") == 3
      and all(i["run_id"] in (RUN_C, None) for i in rs["items"]))
ra = ci.search("wt1a pronephros", k=5, include_origins="all")
check("2o. include_origins=all: sin filtro DECLARADO (origins_included None) → 3 corridas indexadas (A, B, C)",
      ra["origins_included"] is None and ra["n_runs_indexed"] == 3 and ra["excluded_by_origin"] == {})

# ── 3. scorer fallback FORZADO (monkeypatch del import de sklearn) ─────────────────────────────────────────
_saved = {k: sys.modules.get(k) for k in ("sklearn.feature_extraction.text",)}
sys.modules["sklearn.feature_extraction.text"] = None      # ImportError determinista
ci._IDX["key"] = None
rfb = ci.search("wt1a expression pronephros 24 hpf", k=10)
check("3a. sin sklearn el scorer es 'stdlib-tfidf-fallback' (DECLARADO, con nombre propio) y el ranking sigue: "
      "req-aaaa primero, letras A.., admisibilidad false",
      rfb["scorer"] == "stdlib-tfidf-fallback" and rfb["items"][0].get("requirement_id") == RID_A
      and [i["l"] for i in rfb["items"]] == [precedent.letter_label(n) for n in range(1, len(rfb["items"]) + 1)]
      and all(i["admissible_as_evidence"] is False for i in rfb["items"]), rfb["scorer"])
tf = ci._StdlibTfidf(["wt1a pronephros", "pax2a tubule", "wt1a wt1a kidney"])
sc = tf.scores("wt1a")
check("3b. TF-IDF stdlib: coseno en [0,1], el doc sin el término da 0, idf suavizado como sklearn",
      abs(sc[1]) < 1e-12 and 0 < sc[0] <= 1.0 + 1e-9 and 0 < sc[2] <= 1.0 + 1e-9
      and abs(tf.idf["wt1a"] - (__import__("math").log((1 + 3) / (1 + 2)) + 1.0)) < 1e-12)
for k_, v_ in _saved.items():
    if v_ is None:
        sys.modules.pop(k_, None)
    else:
        sys.modules[k_] = v_
ci._IDX["key"] = None
r_back = ci.search("wt1a", k=3)
check("3c. restaurado sklearn el scorer vuelve al principal (o al fallback si no está instalado) — nunca ambiguo",
      r_back["scorer"] == ("sparse-tfidf" if _has_sklearn else "stdlib-tfidf-fallback"))

# ── 4. prior_observations ─────────────────────────────────────────────────────────────────────────────────
po = ci.prior_observations("Is wt1a required for pronephros development at 24 hpf?", entities=["wt1a"])
allowed_keys = set(ci.PRIOR_COMMON_FIELDS) | {"l", "score", "admissible_as_evidence"}
for kind_, fs in ci.PRIOR_FIELDS.items():
    allowed_keys |= set(fs)
check("4a. default: state 'delivered', k 5 (fuente default), n ≤ 5, letras P-A.., SIN comment, SÓLO campos estructurados, "
      "admissible false, instrucción 'prior art' presente",
      po["state"] == "delivered" and po["k"] == 5 and "default" in po["k_source"] and 0 < po["n"] <= 5
      and [i["l"] for i in po["items"]] == ["P-" + precedent.letter_label(n) for n in range(1, po["n"] + 1)]
      and all(i["kind"] != "comment" for i in po["items"])
      and all(set(i) <= allowed_keys for i in po["items"])
      and all(i["admissible_as_evidence"] is False for i in po["items"])
      and "NOT evidence" in po["instruction"] and po["class"] == "prior-art" and "SECRETO" not in json.dumps(po),
      json.dumps({"n": po["n"], "kinds": [i["kind"] for i in po["items"]]}))
check("4b. una observación previa de kind requirement no lleva texto libre fuera de gap/query_en (sin variants, entities ni requested_by)",
      all(not ({"variants", "entities", "requested_by", "acceptance_test", "why_not_admissible"} & set(i))
          for i in po["items"]))
poc = ci.prior_observations("Drummond lab atlas 24 hpf ISH", env={"WITT_COUNCIL_PRIOR_KINDS": "comment,requirement"})
check("4c. WITT_COUNCIL_PRIOR_KINDS=comment,requirement → el comentario ENTRA con autor y ≤280; kinds en orden canónico",
      poc["kinds"] == ["requirement", "comment"] and any(i["kind"] == "comment" and i["author"] == "Natalia"
                                                          and len(i["text"]) <= 280 for i in poc["items"]))
check("4d. env tolerante: PRIOR_K=99 → 12 (clamp declarado); 'abc' → 5 default declarado; kinds basura → default declarado",
      ci.env_config({"WITT_COUNCIL_PRIOR_K": "99"})["prior_k"] == 12
      and "clamped" in ci.env_config({"WITT_COUNCIL_PRIOR_K": "99"})["prior_k_source"]
      and ci.env_config({"WITT_COUNCIL_PRIOR_K": "abc"})["prior_k"] == 5
      and "unparseable" in ci.env_config({"WITT_COUNCIL_PRIOR_K": "abc"})["prior_k_source"]
      and ci.env_config({"WITT_COUNCIL_PRIOR_KINDS": "zzz"})["prior_kinds"] == tuple(ci.PRIOR_KINDS_DEFAULT)
      and ci.env_config({"WITT_COUNCIL_PRIOR_KINDS": "zzz"})["prior_kinds_dropped"] == ["zzz"])
pz = ci.prior_observations("wt1a", env={"WITT_COUNCIL_PRIOR_K": "0"})
check("4e. PRIOR_K=0 → state 'disabled' con disabled_reason, items [] (0 pedidas ≠ corpus vacío)",
      pz["state"] == "disabled" and pz["disabled_reason"] == "WITT_COUNCIL_PRIOR_K=0" and pz["items"] == [] and pz["k"] == 0)
pk = ci.prior_observations("wt1a pronephros", k=2)
check("4f. k explícito gana (k=2 → n 2, k_source 'param k'); k=99 → clamp 12",
      pk["k"] == 2 and pk["n"] == 2 and pk["k_source"] == "param k" and ci.prior_observations("wt1a", k=99)["k"] == 12)
pn = ci.prior_observations("zzzz qqqq nothing matches")
check("4g. corpus con ítems pero sin match → state 'no-match' (declarado en C7: 0 entregadas ≠ empty-corpus)",
      pn["state"] == "no-match" and pn["n"] == 0 and pn["n_items_indexed"] > 0)
fib = ci.frozen_index_block(po)
check("4h. frozen_index_block → {index_version, state, prior_observations_n, scorer, origins_included, kinds_included}",
      set(fib) == {"index_version", "state", "prior_observations_n", "scorer", "origins_included", "kinds_included"}
      and fib["prior_observations_n"] == po["n"] and fib["state"] == "delivered" and fib["origins_included"] == ["production"])
check("4i. PRIOR_STATES cerrado y cada estado observado ∈ vocabulario",
      {po["state"], pz["state"], pn["state"], p0["state"]} <= set(ci.PRIOR_STATES))

# ── 5. kill-switch WITT_COUNCIL_INDEX=0 ───────────────────────────────────────────────────────────────────
OFF = {"WITT_COUNCIL_INDEX": "0"}
e = _err(ci.search, "wt1a", env=OFF)
check("5a. INDEX=0: search → CouncilIndexDisabled (status 503) con state 'disabled (kill-switch WITT_COUNCIL_INDEX=0)'",
      isinstance(e, ci.CouncilIndexDisabled) and e.status == 503
      and e.detail["state"] == "disabled (kill-switch WITT_COUNCIL_INDEX=0)")
pd = ci.prior_observations("wt1a", env=OFF)
check("5b. INDEX=0: prior_observations NO lanza → state 'disabled', disabled_reason kill-switch, items []",
      pd["state"] == "disabled" and "WITT_COUNCIL_INDEX=0" in pd["disabled_reason"] and pd["items"] == [])
dd = ci.demand(env=OFF)
check("5c. INDEX=0: demand sigue MIDIENDO (es conteo, no búsqueda) con index_enabled false declarado",
      dd["index_enabled"] is False and dd["n_runs_scanned"] == 1)
check("5d. index_view bajo INDEX=0 → state disabled; env basura → enabled por default declarado",
      ci.index_view(env=OFF)["state"].startswith("disabled") and ci.env_config({"WITT_COUNCIL_INDEX": "maybe"})["enabled"] is True
      and "unparseable" in ci.env_config({"WITT_COUNCIL_INDEX": "maybe"})["enabled_source"])

# ── 6. demand(): el criterio MEDIDO de los sidecars ───────────────────────────────────────────────────────
FAKE_BRAVE_KEY = "smoke-fake-brave-key-never-sent-0084"       # sólo PRESENCIA (provider_state); jamás viaja ni se envía
KEY_ENV = {**dict(os.environ), "BRAVE_API_KEY": FAKE_BRAVE_KEY}
assert os.environ.get("BRAVE_API_KEY", "") == "" and not os.environ.get("WITT_WEB_LOCATOR"), "la máscara debe dejar el localizador off"
PS_OFF = {"provider": "off", "provider_source": "default-derived:BRAVE_API_KEY absent", "available": False,
          "unavailable_reason": "tool-unavailable (ADR-0084)"}
check("6a. ADR-0084 F.3 — DEMAND_FAMILIES ESTÁTICA == ('figure', 'tooluniverse', 'web') (== sorted(DEMAND_SOURCE_FAMILIES ∪ figure)); "
      "unsatisfiable_families(env) derivada EN LA LLAMADA vía search_harness: bajo off ('tooluniverse', 'web') y con llave fake "
      "('tooluniverse',) (== search_harness.unsatisfiable_families(env)); europepmc NUNCA (tool_module None pero fn real); la fuente es el "
      "literal del ADR; UNSATISFIABLE_FAMILIES estática de import YA NO existe (Context 1: `fn is None` mentiría con la fila web real)",
      ci.DEMAND_FAMILIES == ("figure", "tooluniverse", "web") and ci.DEMAND_SOURCE_FAMILIES == ("tooluniverse", "web")
      and ci.unsatisfiable_families(env=OFF) == ("tooluniverse", "web") == search_harness.unsatisfiable_families(OFF)
      and ci.unsatisfiable_families(env=KEY_ENV) == ("tooluniverse",) == search_harness.unsatisfiable_families(KEY_ENV)
      and ci.unsatisfiable_families() == ("tooluniverse", "web")
      and "europepmc" not in ci.unsatisfiable_families(env=OFF) and search_harness.SEARCH_DISPATCH["europepmc"]["tool_module"] is None
      and ci.UNSATISFIABLE_FAMILIES_SOURCE == "derived: SEARCH_DISPATCH fn None ∪ web_locator.provider_state not available"
      and not hasattr(ci, "UNSATISFIABLE_FAMILIES"),
      repr((ci.unsatisfiable_families(env=OFF), ci.unsatisfiable_families(env=KEY_ENV))))
d1 = ci.demand()
check("6b. conteos exactos: 1 corrida con ledger + 2 planes (3 unidades), 8 requisitos; web 1 · tooluniverse 2 · figure 1; "
      "harness_state de C2 al lado = 4; tooluniverse abierto en 0 corridas (aporto → covered-by-attestation); ADR-0084: bajo off "
      "unsatisfiable_families ['tooluniverse', 'web'] con su fuente y web_locator_provider_state {off, derivado por ausencia de llave, "
      "available False, 'tool-unavailable (ADR-0084)' byte-idéntico}; demand_families estáticas + demand_families_rule",
      d1["n_runs_scanned"] == 1 and d1["n_plans_scanned"] == 2 and d1["n_units_scanned"] == 3
      and d1["n_requirements_scanned"] == 8
      and d1["n_requirements_unsatisfiable_by_family"] == {"figure": 1, "tooluniverse": 2, "web": 1}
      and d1["n_requirements_unsatisfiable_total"] == 4 and d1["n_requirements_harness_state_unsatisfiable"] == 4
      and d1["n_runs_with_tooluniverse_uncovered"] == 0 and d1["by_family_units"]["tooluniverse"] == {"n_runs": 1, "n_plans": 1}
      and d1["unsatisfiable_families"] == ["tooluniverse", "web"] and d1["unsatisfiable_families_source"] == ci.UNSATISFIABLE_FAMILIES_SOURCE
      and d1["web_locator_provider_state"] == PS_OFF and d1["demand_families"] == ["figure", "tooluniverse", "web"]
      and d1["demand_families_rule"] == ci.DEMAND_FAMILIES_RULE and "ADR-0084" in d1["rule"] and "static" in d1["rule"],
      json.dumps({k: d1[k] for k in ("n_runs_scanned", "n_plans_scanned", "n_requirements_unsatisfiable_by_family",
                                     "n_requirements_harness_state_unsatisfiable", "unsatisfiable_families", "web_locator_provider_state")}))
check("6c. umbral {min_runs 5, min_requirements 3, source 'brief §6.3'}; fired false con 3 unidades; clase literal del ADR; "
      "los declarados (council absent 1, consumido 1, smoke excluido) viajan",
      d1["threshold"] == {"min_runs": 5, "min_requirements": 3, "source": "brief §6.3"} and d1["fired"] is False
      and d1["fired_by_family"] == {"figure": False, "tooluniverse": False, "web": False}
      and d1["class"] == "medicion (frozen.council + plans.council_json, origin production)"
      and d1["n_runs_council_absent"] == 1 and d1["n_plans_excluded_consumed_by_indexed_run"] == 1
      and d1["excluded_by_origin"] == {"smoke": 1} and "ADR-0083" in d1["rule"])
# cruzar el umbral: 4 corridas cerradas más, cada una con UN must tooluniverse sin cubrir
n_builds_before = ci._IDX["n_builds"]
for n in range(1, 5):
    rid = f"req-gggg0000001{n}"
    council = {"state": "applicable", "ledger": {"plan_id": None, "state": "approved", "requirements": [
        _req(rid, f"Need ToolUniverse lookup number {n} for lhx1a", "tooluniverse", "paper", "must",
             ["domain-knowledge-curator"], harness_state="unsatisfiable-by-harness (tool-unavailable (ADR-0085))")]},
        "coverage": {"pre_search": {"state": "judged", "by_requirement": [
            {"requirement_id": rid, "priority": "must", "coverage_final": "uncovered", "n_valid_votes": 1,
             "votes": [{"agent": "domain-knowledge-curator", "coverage": "uncovered", "evidence_ids": [], "annulled": False,
                        "hallucinated_evidence_ids": [], "rationale": "no item of that kind in the bundle"}]}]},
            "post_search": {"state": "not-run (search not triggered)"}}}
    _mk_run(f"{n}" * 32, f"lhx1a question number {n}", _frozen(f"answer {n}", [], [], AUDIT_OK, council=council))
d2 = ci.demand()
check("6d. al cruzar el umbral: 5 corridas con ledger + 2 planes; tooluniverse 6 → fired SÓLO tooluniverse; web 1 y figure 1 no; "
      "n_runs_with_tooluniverse_uncovered 4",
      d2["n_runs_scanned"] == 5 and d2["n_units_scanned"] == 7
      and d2["n_requirements_unsatisfiable_by_family"] == {"figure": 1, "tooluniverse": 6, "web": 1}
      and d2["fired_by_family"] == {"figure": False, "tooluniverse": True, "web": False} and d2["fired"] is True
      and d2["n_runs_with_tooluniverse_uncovered"] == 4, json.dumps(d2["fired_by_family"]))
check("6e. demand no construye el índice TF-IDF (n_builds intacto): es un conteo",
      ci._IDX["n_builds"] == n_builds_before)
d_key = ci.demand(env=KEY_ENV)
check("6f. ADR-0084 F.3 — CON llave fake la demanda web SIGUE contándose (conteo ESTÁTICO: web 1 en el histórico, mismos conteos que 6d) "
      "mientras unsatisfiable_families pasa a ['tooluniverse'] y web_locator_provider_state {brave, 'default-derived:BRAVE_API_KEY present', "
      "available True, unavailable_reason None}; fired_by_family conserva la llave web; la llave fake JAMÁS viaja en la respuesta",
      d_key["n_requirements_unsatisfiable_by_family"] == d2["n_requirements_unsatisfiable_by_family"] == {"figure": 1, "tooluniverse": 6, "web": 1}
      and d_key["unsatisfiable_families"] == ["tooluniverse"] and d_key["unsatisfiable_families_source"] == ci.UNSATISFIABLE_FAMILIES_SOURCE
      and d_key["web_locator_provider_state"] == {"provider": "brave", "provider_source": "default-derived:BRAVE_API_KEY present",
                                                  "available": True, "unavailable_reason": None}
      and set(d_key["fired_by_family"]) == {"figure", "tooluniverse", "web"} and d_key["fired_by_family"]["web"] is False
      and d_key["n_requirements_harness_state_unsatisfiable"] == d2["n_requirements_harness_state_unsatisfiable"]
      and FAKE_BRAVE_KEY not in json.dumps(d_key),
      json.dumps({k: d_key[k] for k in ("unsatisfiable_families", "web_locator_provider_state")}))
d_brave_nokey = ci.demand(env={**dict(os.environ), "WITT_WEB_LOCATOR": "brave"})
d_off_key = ci.demand(env={**KEY_ENV, "WITT_WEB_LOCATOR": "off"})
check("6g. ADR-0084 B.3/F.3 — WITT_WEB_LOCATOR=brave sin llave → provider brave, source 'env:WITT_WEB_LOCATOR', available False, "
      "'tool-unavailable (ADR-0084: BRAVE_API_KEY unset)' y unsatisfiable_families ['tooluniverse', 'web']; off EXPLÍCITO con llave → "
      "provider off, available False, literal EXACTO 'tool-unavailable (ADR-0084)' (kill-switch); el conteo web no cambia en ninguno",
      d_brave_nokey["web_locator_provider_state"] == {"provider": "brave", "provider_source": "env:WITT_WEB_LOCATOR", "available": False,
                                                      "unavailable_reason": "tool-unavailable (ADR-0084: BRAVE_API_KEY unset)"}
      and d_brave_nokey["unsatisfiable_families"] == ["tooluniverse", "web"]
      and d_off_key["web_locator_provider_state"] == {"provider": "off", "provider_source": "env:WITT_WEB_LOCATOR", "available": False,
                                                      "unavailable_reason": "tool-unavailable (ADR-0084)"}
      and d_off_key["unsatisfiable_families"] == ["tooluniverse", "web"]
      and d_brave_nokey["n_requirements_unsatisfiable_by_family"]["web"] == d_off_key["n_requirements_unsatisfiable_by_family"]["web"] == 1,
      json.dumps({"brave_nokey": d_brave_nokey["web_locator_provider_state"], "off_key": d_off_key["web_locator_provider_state"]}))
GOLDEN_W0 = json.loads((Path(__file__).resolve().parent / "fixtures" / "golden_plan_web_directive_7d9ce15.json").read_text(encoding="utf-8"))
G_DEMAND = GOLDEN_W0["demand"]
SAME_AS_GOLDEN = ("index_version", "unsatisfiable_families", "unsatisfiable_evidence_kinds", "threshold", "class")
# llaves cuyo VALOR depende de la BD escaneada (el golden se grabó sobre una BD VACÍA; ésta tiene corridas y planes)
DATA_DEPENDENT = {"by_family_units", "excluded_by_origin", "plans_excluded_by_origin", "plans_state", "plans_origin_unknown_included",
                  "origin_unknown_included", "fired", "fired_by_family"}
check("6i. ADR-0084 L/W0 — la FORMA de demand() bajo off es ADITIVA sobre el golden grabado en 7d9ce15: todas las llaves del golden siguen "
      "presentes; index_version, unsatisfiable_families (['tooluniverse', 'web']), unsatisfiable_evidence_kinds, threshold y class son "
      "byte-idénticos; n_requirements_unsatisfiable_by_family y fired_by_family conservan EXACTAMENTE las 3 familias del golden (la serie "
      "medida no cambia de llaves); las únicas llaves del golden con valor distinto son los literales que F.3 cambia a propósito "
      "(unsatisfiable_families_source, rule) más los conteos (esta BD no está vacía)",
      set(G_DEMAND) <= set(d1) and all(d1[k] == G_DEMAND[k] for k in SAME_AS_GOLDEN)
      and set(d1["n_requirements_unsatisfiable_by_family"]) == set(G_DEMAND["n_requirements_unsatisfiable_by_family"]) == {"figure", "tooluniverse", "web"}
      and set(d1["fired_by_family"]) == set(G_DEMAND["fired_by_family"])
      and G_DEMAND["unsatisfiable_families_source"] == "derived: search_harness.SEARCH_DISPATCH rows with fn None"
      and d1["unsatisfiable_families_source"] != G_DEMAND["unsatisfiable_families_source"]
      and {k for k in G_DEMAND if d1[k] != G_DEMAND[k] and not k.startswith("n_") and k not in DATA_DEPENDENT}
      == {"unsatisfiable_families_source", "rule"},
      json.dumps(sorted(k for k in G_DEMAND if d1[k] != G_DEMAND[k])))
check("6h. ADR-0084 — web_locator_provider_state(env) es la proyección de 4 llaves de web_locator.provider_state (misma verdad que el "
      "harness); _is_unsatisfiable cuenta por pertenencia ESTÁTICA (web con llave sigue siendo demanda; zfin nunca)",
      set(ci.web_locator_provider_state(OFF)) == {"provider", "provider_source", "available", "unavailable_reason"}
      and ci.web_locator_provider_state(KEY_ENV)["available"] is True
      and ci._is_unsatisfiable({"source_family": "web", "evidence_kind": "web"}) == "web"
      and ci._is_unsatisfiable({"source_family": "zfin", "evidence_kind": "figure"}) == "figure"
      and ci._is_unsatisfiable({"source_family": "zfin", "evidence_kind": "phenotype"}) is None)

# ── 7. reconstrucción del índice al cambiar la llave — y NO al repetir ────────────────────────────────────
r7 = ci.search("lhx1a ToolUniverse lookup", k=10)
check("7a. la llave cambió (4 corridas nuevas) → UNA reconstrucción exacta; n_runs_indexed 6; los ítems nuevos rankean",
      ci._IDX["n_builds"] == n_builds_before + 1 and r7["n_runs_indexed"] == 6
      and r7["items"] and r7["items"][0]["source_family"] == "tooluniverse")
ci.search("lhx1a ToolUniverse lookup", k=10)
ci.prior_observations("lhx1a")
check("7b. misma llave → cero reconstrucciones adicionales (search + prior_observations comparten el índice)",
      ci._IDX["n_builds"] == n_builds_before + 1)
iv = ci.index_view()
check("7c. index_view: state indexed, scorer declarado, n_builds, conteos del corpus",
      iv["state"] == "indexed" and iv["scorer"] in ci.SCORERS and iv["n_builds"] == n_builds_before + 1
      and iv["n_items_indexed"] == 23 + 4 * 3)   # por corrida nueva: requirement + coverage + decision(keep)

# ── 8. espejos y membresía ────────────────────────────────────────────────────────────────────────────────
import runs as runs_mod  # noqa: E402  — sólo para MEDIR el espejo; council_index no importa runs (ciclo)
check("8a. _panel_findings espejo == runs._panel_findings (:782) sobre ambos paneles",
      ci._panel_findings(AUDIT_A) == runs_mod._panel_findings(AUDIT_A)
      and ci._panel_findings(AUDIT_B) == runs_mod._panel_findings(AUDIT_B)
      and ci._panel_findings({}) == runs_mod._panel_findings({}) == [])
check("8b. _list_of_strings espejo de runs._gap_flags_tolerante: lista, string JSON, string suelto, None",
      ci._list_of_strings(["a", "b"]) == ["a", "b"] and ci._list_of_strings('["x"]') == ["x"]
      and ci._list_of_strings("loose") == ["loose"] and ci._list_of_strings(None) == []
      and runs_mod._gap_flags_tolerante('["x"]') == ["x"] and runs_mod._gap_flags_tolerante("loose") == ["loose"])
mb = ci.membership()
check("8c. membership(): 17 miembros, card_shas[m] == catalog_cards.CARDS[m].sha, catalog_sha == CATALOG_SHA, cm-1",
      mb["n_members"] == 17 and mb["membership_version"] == "cm-1" and mb["catalog_sha"] == cc.CATALOG_SHA
      and all(mb["card_shas"][m] == cc.CARDS[m]["sha"] for m in mb["card_shas"]) and len(mb["card_shas"]) == 17
      and mb["index_version"] == ci.INDEX_VERSION)
mbf = ci.membership(env={"WITT_COUNCIL_FULL": "1"})
check("8d. membership(FULL=1): 25 con los 17 primero; los operativos sin ficha propia declaran card_sha según catálogo",
      mbf["n_members"] == 25 and list(mbf["card_shas"])[:17] == list(mb["card_shas"]))
check("8e. decided_by_kind: 'human:<id>' → 'human' (el id no viaja); default-keep; gate-human-pending; None → None; otro → 'other'",
      ci._decided_by_kind("human:natalia") == "human" and ci._decided_by_kind("default-keep") == "default-keep"
      and ci._decided_by_kind("gate-human-pending") == "gate-human-pending" and ci._decided_by_kind(None) is None
      and ci._decided_by_kind("robot") == "other")
voc = ci.vocabulary()
check("8f. vocabulary(): kinds 7, prior_states 4, scorers 3, decision_kinds 3, text_caps por kind, demand_families 3 (estáticas, ADR-0084 F.3) "
      "+ demand_source_families ['tooluniverse', 'web'] + demand_families_rule",
      voc["kinds"] == list(ci.KINDS) and len(voc["prior_states"]) == 4 and len(voc["scorers"]) == 3
      and voc["decision_kinds"] == ["keep", "discard", "aporto"] and set(voc["text_caps"]) == set(ci.KINDS)
      and voc["demand_families"] == ["figure", "tooluniverse", "web"] and voc["demand_source_families"] == ["tooluniverse", "web"]
      and voc["demand_families_rule"] == ci.DEMAND_FAMILIES_RULE)
check("8g. env_config: origins default ('production',) con fuente; 'all' → None declarado; CSV normalizado",
      ci.env_config({})["origins"] == ("production",) and ci.env_config({"WITT_COUNCIL_INDEX_ORIGINS": "all"})["origins"] is None
      and ci.env_config({"WITT_COUNCIL_INDEX_ORIGINS": "smoke, production"})["origins"] == ("production", "smoke"))

check("9. urlopen bloqueado y contado = 0 (sin red, sin modelo)", N_URLOPEN[0] == 0, f"n={N_URLOPEN[0]}")

n_ok, n = sum(CHECKS), len(CHECKS)
print(f"\n{n_ok}/{n} PASS")
sys.exit(0 if n_ok == n else 1)

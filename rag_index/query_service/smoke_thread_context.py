"""smoke_thread_context.py — gate determinista de la REBANADA T2 de ADR-0079 (investigación = turnos
encadenados) en runs.py: derivación de investigación al encolar (B), snapshot del turno anterior armado en
el servidor (C), inyección al sintetizador/planner como llave hermana y NO al panel (D), precedente ≠
evidencia + fuga de identificadores del padre (E), procedencia de la corrida (F), ejes del episodio (G) y
contrato 1.8 con thread/thread_context/thread_parent_matches_run (I). Kill-switch WITT_THREAD_CONTEXT.

100% offline: SQLite en %LOCALAPPDATA%/Temp/claude/witt-smokes, rag_backend/path_b/sintetizador/panel
inyectados — cero red, cero modelo, cero mutación de la DATA INAMOVIBLE. Exit 0 = todo PASS.

Corre (máscara offline):
  WITT_BACKEND_DB_URL="sqlite:///C:/Users/Emmanuel/AppData/Local/Temp/claude/witt-smokes/smoke-t2-thread.db"
  NEO4J_URI="" RAG_BACKEND=sparse OPENAI_API_KEY="" ANTHROPIC_API_KEY="" WITT_RUN_ORIGIN=smoke
  python rag_index/query_service/smoke_thread_context.py
"""
import json
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# --- máscara offline (ADR-0079 smokes): la env manda; si falta, se fija aquí -----------------------------
_SMOKES = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Temp" / "claude" / "witt-smokes"
_SMOKES.mkdir(parents=True, exist_ok=True)
_DB = _SMOKES / "smoke-t2-thread.db"
if _DB.exists():
    _DB.unlink()
# Se FUERZA (no setdefault): este smoke asume una BD vacía (FIFO del claim, comment_id fijos); con una BD
# compartida por el gate agregado el check (B) reclamaba una corrida ajena. Mismo patrón que
# evaluation/run_held_out_v2.py (la BD del harness se fuerza, jamás se hereda del shell).
os.environ["WITT_BACKEND_DB_URL"] = f"sqlite:///{_DB.as_posix()}"
os.environ["NEO4J_URI"] = ""
os.environ.pop("NEO4J_URI", None)
os.environ.setdefault("RAG_BACKEND", "sparse")
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["WITT_RUN_ORIGIN"] = "smoke"
os.environ["WITT_ALLOW_RUNS_OFFLINE"] = "1"
os.environ["WITT_THREAD_CONTEXT"] = "1"
# ADR-0080 (C7): este gate prueba la INVESTIGACIÓN, no la compuerta de competencia. Sus corridas nacen por new_run
# SIN plan y bajo la compuerta serían 'no-plan' -> ronda + pass2 (eso lo prueban smoke_competence.py y la sección
# ADR-0080 de smoke_run_pipeline.py). El kill-switch DECLARADO deja gobernar la regla legada `pass1 < tau` (conf
# 0.8 -> UNA pasada), que es lo que estos checks miden (len(SYNTH_CALLS) == 1); frozen.competence queda
# {competent: null, skipped_reason: 'kill-switch …'} en todas las corridas de este gate.
os.environ["WITT_COMPETENCE_GATE"] = "0"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402
import precedent  # noqa: E402
import runs as runs_mod  # noqa: E402
from lib import answer_pipeline, composite_auditor, rag_backend  # noqa: E402
from lib.rag_backend import Hit, HitList  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


# ---- stubs deterministas ----------------------------------------------------------------------------------
ALL_A = {"correctness": "APPROVE", "overclaim": "APPROVE", "evidence-grounding": "APPROVE",
         "reproducibility": "APPROVE"}
PANEL_TEXTS = []      # user_text que recibió cada juez (para asegurar que thread_context NO viaja al panel)
SYNTH_CALLS = []      # (pass_label, thread_context) que recibió el sintetizador stub NUEVO


def _panel(verdicts):
    def _caller(member, system, user_text):
        PANEL_TEXTS.append(user_text)
        return ({"verdict": verdicts[member["lens"]], "caught": f"({member['lens']})",
                 "correction_applied": "", "confidence": 0.9, "reasons": []},
                {"input_tokens": 10, "output_tokens": 5})
    return _caller


def _answer(direct_answer, **extra):
    out = {"direct_answer": direct_answer, "stated_confidence": 0.8,
           "confidence_by_subclaim": {"marker-expression": 0.9}, "absence_kind": "not-applicable",
           "gap_flags": ["thin coverage of late stages"],
           "evidence_cited": [{"kind": "di-record", "id": "CORPUS-2026-0001"}],
           "alternatives_considered": ["wt1b como paralogo redundante: descartado"],
           "framework_applied": "Logic-LM",
           "framework_criterion": "for any task whose criteria are formalizable",
           "framework_reason": "la admisibilidad del identificador es formalizable",
           "model": "stub-synth", "usage": {"input_tokens": 100, "output_tokens": 50}}
    out.update(extra)
    return out


def _synth_new(direct_answer, **extra):
    """Sintetizador con la firma NUEVA (acepta thread_context) — registra qué recibió."""
    def _s(question, evidence, pass_label, thread_context=None):
        SYNTH_CALLS.append((pass_label, thread_context))
        assert "thread_context" not in (evidence or {}), "thread_context jamás DENTRO de evidence"
        return _answer(direct_answer, **extra)
    return _s


def _synth_old(direct_answer):
    """Sintetizador con la firma VIEJA (question, evidence, pass_label) — debe seguir siendo válido."""
    def _s(question, evidence, pass_label):
        return _answer(direct_answer)
    return _s


def _chunk(text):
    return Hit(doc_id="CORPUS-2026-0003#c000", type="chunk", score=0.9, text=text, metadata={})


answer_pipeline.path_b = lambda q, n=2, **kw: []
rag_backend.query = lambda text, k=6: HitList([_chunk("pronephros evidence")], degraded=None)


def _run(run_id, synth, panel=None):
    claimed = db.claim_next_queued(worker_id="smoke-t2")
    assert claimed and claimed["run_id"] == run_id, "FIFO: la corrida reclamada debe ser la esperada"
    runs_mod.execute_run(claimed, synthesizer=synth, panel_caller=panel or _panel(ALL_A))
    row = db.get_run(run_id)
    return row, json.loads(row["frozen_record_json"] or "null")


db.init_db()
db.upsert_user("natalia", "Natalia", "medico", "pw-natalia-123")
db.upsert_user("dev", "Dev", "dev", "pw-dev-123")

# ---- (F) run_origin ---------------------------------------------------------------------------------------
o_smoke = runs_mod.run_origin()
os.environ["WITT_RUN_ORIGIN"] = "bogus"
o_bad = runs_mod.run_origin()
os.environ["WITT_RUN_ORIGIN"] = "a-very-long-invalid-origin-value"
o_long = runs_mod.run_origin()
del os.environ["WITT_RUN_ORIGIN"]
o_off = runs_mod.run_origin()
os.environ["WITT_ALLOW_RUNS_OFFLINE"] = "0"
o_prod = runs_mod.run_origin()
os.environ["WITT_ALLOW_RUNS_OFFLINE"] = "1"
os.environ["WITT_RUN_ORIGIN"] = "smoke"
check("(F) run_origin: env en enum → smoke/env; fuera del enum → 'invalid-env:<v>' declarado (recortado a 24 "
      "chars con truncated=True si no cabe en la columna); sin env → dev-offline (máscara) / production (default)",
      o_smoke == {"value": "smoke", "source": "env:WITT_RUN_ORIGIN"}
      and o_bad["value"] == "invalid-env:bogus" and o_bad["source"] == "env:WITT_RUN_ORIGIN"
      and "truncated" not in o_bad
      and o_long["value"] == "invalid-env:a-very-long-invalid-origin-value"[:24] and o_long["truncated"] is True
      and o_long["raw"] == "a-very-long-invalid-origin-value"
      and o_off == {"value": "dev-offline", "source": "derived:offline-mask"}
      and o_prod == {"value": "production", "source": "default:production"},
      json.dumps([o_smoke, o_bad, o_long, o_off, o_prod]))

# ---- (B) raíz -----------------------------------------------------------------------------------------------
ROOT = runs_mod.new_run("natalia", "does wt1a mark the pronephros?", ["wt1a"], from_question_id="q-root-1")
root = db.get_run(ROOT)
root_env = json.loads(root["thread_context_json"])
check("(B) la RAÍZ nace con thread_id=run_id, turn_no=1, turn_kind='root', parent NULL, origin 'smoke', "
      "root_question_id sembrado; sobre con skipped_reason 'root-turn'",
      root["thread_id"] == ROOT and root["turn_no"] == 1 and root["turn_kind"] == "root"
      and root["parent_run_id"] is None and root["origin"] == "smoke"
      and root["root_question_id"] == "q-root-1"
      and root_env["snapshot"] is None and root_env["skipped_reason"] == "root-turn")

# 404 / 409 ANTES de insertar
try:
    runs_mod.new_run("natalia", "x", [], parent_run_id="nope")
    e404 = None
except runs_mod.ThreadError as e:
    e404 = e
try:
    runs_mod.new_run("natalia", "x", [], parent_run_id=ROOT)   # la raíz está 'queued' (no terminal)
    e409 = None
except runs_mod.ThreadError as e:
    e409 = e
n_runs_before = len(db.list_runs(limit=1000))
check("(B) padre inexistente → ParentNotFound 404 'parent_not_found'; padre no terminal (queued) → "
      "ParentNotTerminal 409 'parent_not_terminal'; ninguna fila insertada",
      e404 is not None and e404.status == 404 and e404.detail["state"] == "parent_not_found"
      and e409 is not None and e409.status == 409 and e409.detail["state"] == "parent_not_terminal"
      and e409.detail["parent_state"] == "queued" and n_runs_before == 1)

root_row, root_frozen = _run(ROOT, _synth_new("wt1a (ENSDARG00000031420) marks the zebrafish pronephros."))
check("(I) raíz congelada: contract == runs.RENDER_CONTRACT_VERSION (el literal se asserta UNA vez, en smoke_run_pipeline), thread root, thread_context null + skipped 'root-turn', "
      "thread_parent_matches_run null, precedent_citations [] + disjoint_series True 'no-parent', "
      "origin {smoke, env}, episode_axes.provenance.turn = root",
      root_row["state"] == "awaiting_closure"
      and root_frozen["render_contract_version"] == runs_mod.RENDER_CONTRACT_VERSION
      and root_frozen["thread"]["turn_kind"] == "root" and root_frozen["thread"]["turn_no"] == 1
      and root_frozen["thread"]["thread_id"] == ROOT and root_frozen["thread"]["parent_run_id"] is None
      and root_frozen["thread_context"] is None
      and root_frozen["thread_context_skipped_reason"] == "root-turn"
      and root_frozen["thread_parent_matches_run"] is None
      and root_frozen["thread_parent_matches_run_state"] == "no-parent"
      and root_frozen["precedent_citations"] == []
      and root_frozen["deterministic_checks"]["disjoint_series"] is True
      and root_frozen["deterministic_checks"]["disjoint_series_state"] == "no-parent"
      and root_frozen["deterministic_checks"]["parent_identifier_leak_state"] == "no-parent"
      and root_frozen["origin"]["value"] == "smoke" and root_frozen["origin"]["source"] == "env:WITT_RUN_ORIGIN"
      and root_frozen["origin"]["note"] is None
      # corrector: la fuente es la de ENCOLAR (copiada del sobre); la re-derivación al ejecutar viaja aparte
      and root_frozen["origin"]["source_at_execution"] == {"value": "smoke", "source": "env:WITT_RUN_ORIGIN",
                                                            "same_value_as_column": True}
      and root_frozen["episode_axes"]["provenance"]["turn"] == {"thread_id": ROOT, "turn_no": 1,
                                                                 "turn_kind": "root"},
      json.dumps({k: root_frozen.get(k) for k in ("thread", "origin", "thread_context_skipped_reason")}))
check("(D) raíz: el sintetizador NUEVO recibió thread_context=None (sin turno anterior no viaja nada) y el "
      "prompt del panel no lleva 'thread_context'",
      all(tc is None for _l, tc in SYNTH_CALLS) and len(SYNTH_CALLS) == 1
      and all("thread_context" not in t for t in PANEL_TEXTS))
es_root = json.loads(root_row["epistemic_summary_json"])
check("(G) epistemic_summary de la raíz gana thread_id/turn_no/origin (derivados al congelar)",
      es_root["thread_id"] == ROOT and es_root["turn_no"] == 1 and es_root["origin"] == "smoke")

# ---- (C) snapshot: comentarios con tope, sin calificaciones -------------------------------------------------
for i in range(10):
    db.create_run_comment(f"c{i:02d}", ROOT, "dev" if i % 2 else "natalia", f"comentario {i}: falta el estadio tardío")
# las calificaciones NO entran al snapshot por construcción (build_thread_context lee frozen + comentarios,
# jamás run_ratings): la exclusión se comprueba sobre el texto del snapshot, no sembrando una calificación.

SYNTH_CALLS.clear()
PANEL_TEXTS.clear()
CHILD = runs_mod.new_run("natalia", "does wt1a mark the pronephros at 48 hpf?", ["wt1a"], parent_run_id=ROOT)
child = db.get_run(CHILD)
child_env = json.loads(child["thread_context_json"])
snap = child_env["snapshot"]
check("(B) hijo con pregunta distinta: turn_no=2, turn_kind='refine', thread_id=raíz, parent=raíz, "
      "root_question_id heredado de la raíz",
      child["turn_no"] == 2 and child["turn_kind"] == "refine" and child["thread_id"] == ROOT
      and child["parent_run_id"] == ROOT and child["root_question_id"] == "q-root-1")
snap_text = json.dumps(snap, ensure_ascii=False)
check("(C) snapshot armado en el SERVIDOR desde el frozen del padre: parent {run_id, run_no=1, verdict}, "
      "previous_answer recortada con gap_flags íntegros, previous_audit {verdict, n_valid, findings}, "
      "evidence_hints (pistas), excluded declara ratings, sha del padre, class 'atestiguada' en comentarios",
      snap["parent"]["run_id"] == ROOT and snap["parent"]["run_no"] == 1
      and snap["parent"]["verdict"] == "APPROVE" and snap["parent"]["decision_state"] == "AUDIT_APPROVED"
      and snap["previous_answer"]["direct_answer"].startswith("wt1a (ENSDARG00000031420)")
      and snap["previous_answer"]["gap_flags"] == ["thin coverage of late stages"]
      and snap["previous_answer"]["absence_kind"] == "not-applicable"
      and snap["previous_audit"]["verdict"] == "APPROVE" and snap["previous_audit"]["n_valid"] == 4
      and isinstance(snap["previous_audit"]["findings"], list)
      and snap["evidence_hints"]["entities"] == ["wt1a"]
      and snap["evidence_hints"]["approved_evidence_ids"] == ["CORPUS-2026-0003#c000"]
      and snap["excluded"] == runs_mod.THREAD_CONTEXT_EXCLUDED
      and len(snap["parent_frozen_sha256"]) == 64 and snap["bytes"] > 0
      and snap["human_comments"]["class"] == "atestiguada"
      and "rating" not in snap_text.replace("ratings values and notes", "")
      and "nota-secreta" not in snap_text)
hc = snap["human_comments"]
check("(C) comentarios: 10 en el padre → 8 incluidos (WITT_THREAD_COMMENTS_MAX default), truncated=True, "
      "orden determinista, n_total declarado",
      hc["n_total"] == 10 and hc["n_included"] == 8 and hc["truncated"] is True
      and [c["body"][:13] for c in hc["items"]] == [f"comentario {i}:" for i in range(8)]
      and hc["items"][0]["author_name"] == "Natalia")

# tope de CARACTERES (env leída en tiempo de corrida) sobre la función PURA
os.environ["WITT_THREAD_COMMENTS_CHARS"] = "50"
env_small = runs_mod.build_thread_context(db.get_run(ROOT), db.list_run_comments(ROOT), db._now())
del os.environ["WITT_THREAD_COMMENTS_CHARS"]
hc2 = env_small["snapshot"]["human_comments"]
check("(C) WITT_THREAD_COMMENTS_CHARS=50 → chars_included <= 50, truncated=True, límite declarado",
      hc2["chars_included"] <= 50 and hc2["truncated"] is True and hc2["limits"]["chars"] == 50)

# ---- (D) inyección: llave hermana al sintetizador, NO al panel; (E) precedente en letras ----------------------
# la respuesta del hijo cita un PMID que NO está en su evidencia: verify_output lo FLAGEA (gap honesto, no
# fallo) — y ese PMID será el identificador "solo en el contexto del padre" de la prueba de fuga de abajo
child_row, child_frozen = _run(CHILD, _synth_new("wt1a marks the pronephros at 48 hpf as well (PMID:31415926)."))
_d = {
    "synth_called_once_with_snapshot": len(SYNTH_CALLS) == 1 and SYNTH_CALLS[0][1] is not None
    and SYNTH_CALLS[0][1]["parent"]["run_id"] == ROOT,
    "panel_4_judges": len(PANEL_TEXTS) == 4,
    "panel_without_thread_context_key": all('"thread_context"' not in t for t in PANEL_TEXTS),
    "panel_thread_summary": all(json.loads(t)["deterministic_checks"]["thread"] == {
        "thread_id": ROOT, "turn_no": 2, "turn_kind": "refine", "parent_run_id": ROOT,
        "parent_run_no": 1, "parent_verdict": "APPROVE", "context_available": True} for t in PANEL_TEXTS),
    "panel_without_parent_comments": all("comentario 0" not in t for t in PANEL_TEXTS),
    "panel_without_parent_answer_text": all("ENSDARG00000031420" not in json.dumps(json.loads(t)["evidence"])
                                            or "ENSDARG00000031420" in json.dumps(json.loads(t)["evidence"]["entities_checked"])
                                            for t in PANEL_TEXTS),
}
check("(D) el sintetizador NUEVO recibió el snapshot como thread_context (parent.run_id = raíz) en pass1 y "
      "el PANEL no recibió la llave 'thread_context' ni los comentarios del padre, pero sí "
      "deterministic_checks.thread {turn_no 2, parent_run_no 1, parent_verdict APPROVE}",
      all(_d.values()), json.dumps({k: v for k, v in _d.items() if not v}))
pc = child_frozen["precedent_citations"]
check("(E) corrector ADR-0079: el padre está awaiting_closure (sin clausura humana) → NO es precedente (ADR-0053): "
      "precedent_citations [] + precedent_citations_state 'parent-not-closed', disjoint_series True con estado "
      "'parent-not-precedent'; citations NO cambian de forma (n entero). La letra se mide abajo con el padre CERRADO",
      pc == [] and child_frozen["precedent_citations_state"] == "parent-not-closed"
      and child_frozen["deterministic_checks"]["disjoint_series"] is True
      and child_frozen["deterministic_checks"]["disjoint_series_state"] == "parent-not-precedent"
      and all(isinstance(c["n"], int) and "l" not in c for c in child_frozen["citations"])
      and precedent.validate_disjoint({"evidence": child_frozen["citations"], "precedent": pc}) is True)
check("(E) una cita de precedente hecha a mano con 'label':'A' (sin 'l') DEBE fallar validate_disjoint; "
      "una letra dentro de la serie de evidencia también",
      precedent.validate_disjoint({"evidence": [], "precedent": [{"label": "A", "run_id": ROOT,
                                                                 "admissible_as_evidence": False}]}) is False
      and precedent.validate_disjoint({"evidence": [{"n": 1, "l": "A", "id": "x"}], "precedent": []}) is False)
check("(I) hijo congelado: thread {turn_no 2, refine, parent_state awaiting_closure, parent_run_no 1}, "
      "thread_context = snapshot íntegro (sha del padre), thread_parent_matches_run True (padre inmutable), "
      "context_delivery.synthesizer True / panel False, prompt_components declarados, admisible (sin fuga)",
      child_frozen["thread"]["turn_no"] == 2 and child_frozen["thread"]["turn_kind"] == "refine"
      and child_frozen["thread"]["parent_state"] == "awaiting_closure"
      and child_frozen["thread"]["parent_run_no"] == 1
      and child_frozen["thread_context"]["parent_frozen_sha256"] == snap["parent_frozen_sha256"]
      and child_frozen["thread_context_skipped_reason"] is None
      and child_frozen["thread_parent_matches_run"] is True
      and child_frozen["thread"]["context_delivery"]["synthesizer"] is True
      and child_frozen["thread"]["context_delivery"]["panel"] is False
      and len(child_frozen["thread"]["context_delivery"]["prompt_components"]) == 3
      and child_frozen["deterministic_checks"]["parent_identifier_leak"] == []
      and child_frozen["deterministic_checks"]["admissible"] is True)
es_child = json.loads(child_row["epistemic_summary_json"])
check("(G) episode_axes del hijo: world effect-claimed, inference supported, technical completed (el stub de "
      "retrieval reporta mode 'semantic'), provenance.turn turn_no 2, origin smoke; epistemic_summary turn_no 2",
      child_frozen["episode_axes"]["world"] == "effect-claimed"
      and child_frozen["episode_axes"]["inference"] == "supported"
      and child_frozen["episode_axes"]["technical"] == "completed"
      and child_frozen["retrieval_summary"]["mode"] == "semantic"
      and child_frozen["episode_axes"]["provenance"]["origin"] == "smoke"
      and child_frozen["episode_axes"]["provenance"]["turn"]["turn_no"] == 2
      and child_frozen["episode_axes"]["provenance"]["human_gates"] ["plan_declared"] is False
      and es_child["turn_no"] == 2 and es_child["thread_id"] == ROOT)

# ---- (D) camino REAL: _default_synthesizer arma user_text {question, evidence, thread_context} -------------------
REAL = []
_real_call = composite_auditor._anthropic_tool_call


def _capture(model, system, user_text, tool=None, **kw):
    REAL.append((system, user_text, tool))
    return ({"direct_answer": "stub", "confidence": 0.5, "absence_kind": "not-applicable",
             "alternatives_considered": ["x"], "framework_applied": "Logic-LM", "evidence_cited": []},
            {"input_tokens": 1, "output_tokens": 1})


composite_auditor._anthropic_tool_call = _capture
try:
    runs_mod._default_synthesizer("q?", {"path_a_hits": []}, "pass1", thread_context=snap)
    runs_mod._default_synthesizer("q?", {"path_a_hits": []}, "pass1")
finally:
    composite_auditor._anthropic_tool_call = _real_call
with_ctx = json.loads(REAL[0][1])
without_ctx = json.loads(REAL[2][1])
check("(D) CAMINO REAL: con snapshot el user_text tiene las llaves {question, evidence, thread_context} (hermana, "
      "no dentro de evidence) y el system lleva la cláusula anti-fuga; sin snapshot el user_text y el system son "
      "EXACTAMENTE los de antes; SYNTH_TOOL.description lleva 'PRIOR ART'",
      set(with_ctx) == {"question", "evidence", "thread_context"}
      and "thread_context" not in with_ctx["evidence"]
      and with_ctx["thread_context"]["parent"]["run_id"] == ROOT
      and runs_mod.THREAD_ANTI_LEAK_CLAUSE in REAL[0][0]
      and set(without_ctx) == {"question", "evidence"}
      and REAL[2][0] == runs_mod.synth_system("pass1")
      and runs_mod.THREAD_ANTI_LEAK_CLAUSE not in REAL[2][0]
      and "PRIOR ART" in runs_mod.SYNTH_TOOL["description"])

# ---- (E) fuga: identificador SOLO en el contexto del padre → inadmisible -------------------------------------------
# NOTA de diseño medida aquí: el ENSDARG de wt1a NO cuenta como fuga aunque venga del padre, porque la
# resolución del store (entities_checked) forma parte de la evidencia del hijo — la regla mira la evidencia que
# el modelo VIO, no sólo los evidence_ids. El identificador "solo en el contexto del padre" es el PMID.
SYNTH_CALLS.clear()
RERUN = runs_mod.new_run("natalia", "does wt1a mark the pronephros at 48 hpf?", ["wt1a"], parent_run_id=CHILD)
rr = db.get_run(RERUN)
check("(B) hijo con la MISMA pregunta+entities que su padre (CHILD) → turn_kind='rerun', turn_no=3 (max del "
      "hilo + 1), thread_id = raíz (heredado, no el padre)",
      rr["turn_kind"] == "rerun" and rr["turn_no"] == 3 and rr["thread_id"] == ROOT and rr["parent_run_id"] == CHILD)
rerun_row, rerun_frozen = _run(RERUN, _synth_new("wt1a marks the pronephros at 48 hpf (PMID:31415926)."))
dc = rerun_frozen["deterministic_checks"]
check("(E) PMID:31415926 está en el snapshot del padre Y en la respuesta del hijo Y NO en su evidencia → "
      "parent_identifier_leak=['PMID:31415926'] → predicado duro → admissible False con la razón declarada "
      "(el ENSDARG resuelto por el store NO figura: está en entities_checked del hijo)",
      dc["parent_identifier_leak"] == ["PMID:31415926"] and dc["admissible"] is False
      and any("parent_identifier_leak" in r for r in dc["reasons"])
      and "PMID:31415926" in rerun_frozen["thread_context"]["previous_answer"]["direct_answer"],
      json.dumps({"leak": dc["parent_identifier_leak"], "reasons": dc["reasons"]}))
# control: el MISMO identificador, pero presente en la evidencia del hijo → no es fuga
rag_backend.query = lambda text, k=6: HitList([_chunk("wt1a pronephros evidence (PMID:31415926)")], degraded=None)
BRANCH = runs_mod.new_run("natalia", "is wt1a required for pronephros function?", ["wt1a"], parent_run_id=CHILD)
br = db.get_run(BRANCH)
check("(B) segundo hijo de CHILD con pregunta nueva (CHILD ya tenía a RERUN) → turn_kind='branch', turn_no=4",
      br["turn_kind"] == "branch" and br["turn_no"] == 4 and br["parent_run_id"] == CHILD)
branch_row, branch_frozen = _run(BRANCH, _synth_new("wt1a is required (PMID:31415926)."))
rag_backend.query = lambda text, k=6: HitList([_chunk("pronephros evidence")], degraded=None)
check("(E) control: el identificador también está en la EVIDENCIA del hijo → no es fuga (leak [], admisible); "
      "la regla queda declarada en deterministic_checks.parent_identifier_leak_rule",
      branch_frozen["deterministic_checks"]["parent_identifier_leak"] == []
      and branch_frozen["deterministic_checks"]["admissible"] is True
      and "PMID" in branch_frozen["deterministic_checks"]["parent_identifier_leak_rule"])

# ---- firma vieja del sintetizador: sigue válida, el registro declara que no recibió el contexto -----------------
OLD = runs_mod.new_run("natalia", "old-signature stub child", ["wt1a"], parent_run_id=CHILD)
old_row, old_frozen = _run(OLD, _synth_old("wt1a marks the pronephros."))
check("(D) sintetizador con firma VIEJA (sin thread_context): la corrida completa, "
      "context_delivery.synthesizer=False + nota; thread_context sigue congelado (el insumo existía)",
      old_row["state"] == "awaiting_closure"
      and old_frozen["thread"]["context_delivery"]["synthesizer"] is False
      and "signature" in old_frozen["thread"]["context_delivery"]["synthesizer_note"]
      and old_frozen["thread_context"] is not None and old_frozen["thread"]["turn_no"] == 5
      and old_frozen["thread"]["parent_run_id"] == CHILD)

# ---- kill-switch WITT_THREAD_CONTEXT=0 (al encolar y al ejecutar) ----------------------------------------------------
os.environ["WITT_THREAD_CONTEXT"] = "0"
KS = runs_mod.new_run("natalia", "kill-switch child", ["wt1a"], parent_run_id=ROOT)
ks = db.get_run(KS)
ks_env = json.loads(ks["thread_context_json"])
SYNTH_CALLS.clear()
ks_row, ks_frozen = _run(KS, _synth_new("wt1a marks the pronephros."))
os.environ["WITT_THREAD_CONTEXT"] = "1"
check("kill-switch al ENCOLAR: las columnas se llenan (turn_no 6, branch, thread_id raíz) pero el snapshot no se "
      "arma (skipped_reason 'kill-switch WITT_THREAD_CONTEXT=0'); al ejecutar el sintetizador recibe None y el "
      "frozen declara thread_context null + skipped_reason",
      ks["turn_no"] == 6 and ks["turn_kind"] == "branch" and ks["thread_id"] == ROOT
      and ks_env["snapshot"] is None and ks_env["skipped_reason"] == "kill-switch WITT_THREAD_CONTEXT=0"
      and ks_env["kill_switch"]["WITT_THREAD_CONTEXT"] == "0"
      and all(tc is None for _l, tc in SYNTH_CALLS)
      and ks_frozen["thread_context"] is None
      and ks_frozen["thread_context_skipped_reason"] == "kill-switch WITT_THREAD_CONTEXT=0"
      and ks_frozen["thread"]["turn_no"] == 6)
KS2 = runs_mod.new_run("natalia", "kill-switch at execution", ["wt1a"], parent_run_id=ROOT)
assert json.loads(db.get_run(KS2)["thread_context_json"])["snapshot"] is not None
os.environ["WITT_THREAD_CONTEXT"] = "0"
SYNTH_CALLS.clear()
ks2_row, ks2_frozen = _run(KS2, _synth_new("wt1a marks the pronephros."))
os.environ["WITT_THREAD_CONTEXT"] = "1"
check("kill-switch al EJECUTAR (snapshot ya persistido): no viaja al modelo, frozen.thread_context null con "
      "skipped_reason 'at execution' — el sobre persistido no se toca",
      all(tc is None for _l, tc in SYNTH_CALLS)
      and ks2_frozen["thread_context"] is None
      and "at execution" in ks2_frozen["thread_context_skipped_reason"]
      and json.loads(db.get_run(KS2)["thread_context_json"])["snapshot"] is not None)

# ---- padre con identidad inválida → snapshot null (la corrida SÍ se crea) --------------------------------------------
bad_frozen = dict(child_frozen)
bad_frozen["question_matches_run"] = False
pure = runs_mod.build_thread_context({**db.get_run(CHILD), "frozen_record_json": json.dumps(bad_frozen)}, [], db._now())
db.update_run(OLD, frozen_record_json=json.dumps({**old_frozen, "question_matches_run": False}))
INV = runs_mod.new_run("natalia", "child of invalid identity", ["wt1a"], parent_run_id=OLD)
inv_env = json.loads(db.get_run(INV)["thread_context_json"])
check("padre con question_matches_run=false → build_thread_context (puro) y new_run: snapshot null + "
      "skipped_reason 'parent-identity-invalid'; la corrida hija SÍ se crea (mismo hilo raíz, turn_no 8)",
      pure["snapshot"] is None and pure["skipped_reason"] == "parent-identity-invalid"
      and inv_env["snapshot"] is None and inv_env["skipped_reason"] == "parent-identity-invalid"
      and db.get_run(INV)["turn_no"] == 8 and db.get_run(INV)["thread_id"] == ROOT)
SYNTH_CALLS.clear()
inv_row, inv_frozen = _run(INV, _synth_new("wt1a marks the pronephros."))
check("hijo de identidad inválida congelado: thread_context null + skipped 'parent-identity-invalid', "
      "thread_parent_matches_run null con estado 'no-snapshot', parent_identifier_leak_state 'no-snapshot' (corrector: hay "
      "padre, no se midió), precedent_citations [] con estado 'parent-not-closed' (el padre no está cerrado), "
      "sintetizador recibió None",
      inv_frozen["thread_context"] is None
      and inv_frozen["thread_context_skipped_reason"] == "parent-identity-invalid"
      and inv_frozen["thread_parent_matches_run"] is None
      and inv_frozen["thread_parent_matches_run_state"] == "no-snapshot"
      and inv_frozen["deterministic_checks"]["parent_identifier_leak_state"] == "no-snapshot"
      and inv_frozen["precedent_citations"] == [] and inv_frozen["precedent_citations_state"] == "parent-not-closed"
      and all(tc is None for _l, tc in SYNTH_CALLS))

# ---- padre SIN registro congelado (failed) → previous_answer/previous_audit null DECLARADOS ------------------------------
FAILED = runs_mod.new_run("natalia", "a run that will fail", ["wt1a"])
db.update_run(FAILED, state="failed", error="boom")
NF = runs_mod.new_run("natalia", "child of a failed parent", ["wt1a"], parent_run_id=FAILED)
nf_env = json.loads(db.get_run(NF)["thread_context_json"])
nfs = nf_env["snapshot"]
check("padre failed sin frozen → snapshot CON previous_answer null y previous_audit null declarados "
      "(frozen_absent_reason 'parent-without-frozen-record'), parent.state 'failed', sha null; hijo turn_no 2 "
      "en el hilo del padre",
      nfs is not None and nfs["previous_answer"] is None and nfs["previous_audit"] is None
      and nfs["frozen_absent_reason"] == "parent-without-frozen-record"
      and nfs["parent"]["state"] == "failed" and nfs["parent_frozen_sha256"] is None
      and db.get_run(NF)["turn_no"] == 2 and db.get_run(NF)["thread_id"] == FAILED)
nf_row, nf_frozen = _run(NF, _synth_new("wt1a marks the pronephros."))
check("hijo de padre failed congelado: thread_parent_matches_run null con estado 'parent-without-frozen-record' "
      "(jamás un True vacío de None == None), parent_state 'failed', previous_answer null en el snapshot congelado",
      nf_frozen["thread_parent_matches_run"] is None
      and nf_frozen["thread_parent_matches_run_state"] == "parent-without-frozen-record"
      and nf_frozen["precedent_citations"] == []
      and nf_frozen["precedent_citations_state"] == "parent-without-frozen-record"
      and nf_frozen["thread"]["parent_state"] == "failed"
      and nf_frozen["thread_context"]["previous_answer"] is None)

# ---- padre PRE-ADR (columnas NULL) → raíz VIRTUAL ---------------------------------------------------------------------
PRE = "pre0079" + "0" * 25
db.create_run(PRE, "natalia", "pre-adr question", ["wt1a"])   # sin thread_id/turn_no/origin: fila anterior al contrato
db.update_run(PRE, state="closed", frozen_at=db._now(), closed_by="natalia",   # corrector: la letra sólo con padre CERRADO
              frozen_record_json=json.dumps(root_frozen))
pre = db.get_run(PRE)
CH_PRE = runs_mod.new_run("natalia", "child of pre-adr parent", ["wt1a"], parent_run_id=PRE)
chp = db.get_run(CH_PRE)
chp_env = json.loads(chp["thread_context_json"])
check("corrida pre-ADR: columnas NULL (sin backfill) · su hijo la trata como raíz VIRTUAL: thread_id = "
      "parent.run_id, turn_no 2, snapshot.parent_pre_adr_0079 True y sobre.parent_pre_adr_0079 True",
      pre["thread_id"] is None and pre["turn_no"] is None and pre["origin"] is None
      and chp["thread_id"] == PRE and chp["turn_no"] == 2 and chp["turn_kind"] == "refine"
      and chp_env["snapshot"]["parent_pre_adr_0079"] is True and chp_env["parent_pre_adr_0079"] is True)
chp_row, chp_frozen = _run(CH_PRE, _synth_new("wt1a marks the pronephros."))
check("hijo de padre pre-ADR (CERRADO) congelado: precedent_citations[0] con run_no del padre y turn_no null (el padre no "
      "tiene turno — ausencia declarada, no se le inventa 1), estado 'checked', thread_parent_matches_run True",
      chp_frozen["precedent_citations_state"] == "checked"
      and chp_frozen["precedent_citations"][0]["run_id"] == PRE
      and chp_frozen["precedent_citations"][0]["run_no"] == pre["run_no"]
      and chp_frozen["precedent_citations"][0]["turn_no"] is None
      and chp_frozen["thread_parent_matches_run"] is True
      and chp_frozen["thread_context"]["parent_pre_adr_0079"] is True)

# ---- inmutabilidad: el sha ignora frozen_at/closed_by; un hijo de un padre CERRADO sigue casando ----------------------
blob = db.get_run(ROOT)["frozen_record_json"]
blob_closed = json.dumps({**json.loads(blob), "frozen_at": "2026-09-15T00:00:00", "closed_by": "natalia"})
runs_mod.close_run(ROOT, by="natalia")
AFTER_CLOSE = runs_mod.new_run("natalia", "child after closure", ["wt1a"], parent_run_id=ROOT)
ac_row, ac_frozen = _run(AFTER_CLOSE, _synth_new("wt1a marks the pronephros."))
check("frozen_sha256 ignora frozen_at/closed_by (THREAD_SHA_RULE) · hijo de un padre CERRADO: "
      "thread_parent_matches_run True, parent_state 'closed', regla declarada en el registro",
      runs_mod.frozen_sha256(blob) == runs_mod.frozen_sha256(blob_closed)
      and runs_mod.frozen_sha256(blob) != runs_mod.frozen_sha256(json.dumps({**json.loads(blob), "x": 1}))
      and ac_frozen["thread_parent_matches_run"] is True
      and ac_frozen["thread_parent_matches_run_state"] == "checked"
      and ac_frozen["thread"]["parent_state"] == "closed"
      and ac_frozen["thread_parent_matches_run_rule"] == runs_mod.THREAD_SHA_RULE)
pc_ac = ac_frozen["precedent_citations"]
check("(E) hijo de un padre CERRADO: frozen.precedent_citations = [{l:'A', run_id raíz, admissible_as_evidence False, run_no 1, "
      "turn_no 1, kind 'turn', why_not_admissible}] (precedent.turn_item → serialize_disjoint, sin re-copia manual) · "
      "precedent_citations_state 'checked' · validate_disjoint True · disjoint_series 'checked'",
      len(pc_ac) == 1 and pc_ac[0]["l"] == "A" and pc_ac[0]["run_id"] == ROOT
      and pc_ac[0]["admissible_as_evidence"] is False and pc_ac[0]["run_no"] == 1 and pc_ac[0]["turn_no"] == 1
      and pc_ac[0]["kind"] == "turn" and pc_ac[0]["why_not_admissible"] == precedent.WHY_NOT_ADMISSIBLE
      and pc_ac[0] == {**precedent.serialize_disjoint([], [precedent.turn_item(db.get_run(ROOT))])["precedent"][0]}
      and ac_frozen["precedent_citations_state"] == "checked"
      and ac_frozen["deterministic_checks"]["disjoint_series"] is True
      and ac_frozen["deterministic_checks"]["disjoint_series_state"] == "checked"
      and precedent.validate_disjoint({"evidence": ac_frozen["citations"], "precedent": pc_ac}) is True)

# ---- (G) episode_axes por tabla: 5 combinaciones ---------------------------------------------------------------------
ax = runs_mod.episode_axes
t = {"thread_id": "t", "turn_no": 1, "turn_kind": "root"}
a1 = ax("AUDIT_APPROVED", "not-applicable", "APPROVE", "awaiting_closure", "semantic", "production", True, False, t)
a2 = ax("AUDIT_APPROVED", "evidence-of-no-effect", "APPROVE_DECLINE", "closed", "sparse", "smoke", False, True, t)
a3 = ax("AUDIT_APPROVED", "no-evidence-retrieved", "APPROVE_MINOR", "awaiting_closure", "semantic", None, False, False, t)
a4 = ax("AUDIT_REJECTED", "not-applicable", "REVISE", "awaiting_closure", "semantic", "smoke", False, False, t)
a5 = ax("FALLBACK_FETCHED", None, None, "failed", None, "smoke", False, False, None)
check("(G) EPISODE_AXES_MAP: APPROVED×not-applicable×APPROVE → effect-claimed/supported/completed · "
      "×evidence-of-no-effect×APPROVE_DECLINE×sparse → null-bounded/honest-decline/degraded · "
      "×no-evidence-retrieved×APPROVE_MINOR → indeterminate/minor-issues · REJECTED×REVISE → "
      "not-established/insufficient · sin veredicto×failed → not-assessed/not-evaluated/failed; clase declarada",
      (a1["world"], a1["inference"], a1["technical"]) == ("effect-claimed", "supported", "completed")
      and (a2["world"], a2["inference"], a2["technical"]) == ("null-bounded", "honest-decline", "degraded")
      and a2["provenance"]["human_gates"] == {"plan_declared": False, "closed": True,
                                              "closed_note": a2["provenance"]["human_gates"]["closed_note"]}
      and (a3["world"], a3["inference"], a3["technical"]) == ("indeterminate", "minor-issues", "completed")
      and (a4["world"], a4["inference"], a4["technical"]) == ("not-established", "insufficient", "completed")
      and (a5["world"], a5["inference"], a5["technical"]) == ("not-assessed", "not-evaluated", "failed")
      and a5["provenance"]["turn"] == {"thread_id": None, "turn_no": None, "turn_kind": None}
      and all(a["class"] == "derived-at-freeze" for a in (a1, a2, a3, a4, a5))
      and runs_mod.EPISODE_AXES_MAP["world"]["AUDIT_REJECTED"] == "not-established")

# ---- lectura tolerante (ADR-0074) de gap_flags serializados en el frozen del padre ------------------------------------------
tol_frozen = {**root_frozen, "answer": {**root_frozen["answer"], "gap_flags": json.dumps(["a", "b"])}}
tol = runs_mod.build_thread_context({**db.get_run(ROOT), "frozen_record_json": json.dumps(tol_frozen)}, [], db._now())
tol2 = runs_mod.build_thread_context({**db.get_run(ROOT), "frozen_record_json": json.dumps(
    {**tol_frozen, "answer": {**tol_frozen["answer"], "gap_flags": "not json"}})}, [], db._now())
check("(C) gap_flags del padre como STRING JSON → lista parseada; string no-JSON → [string] (nunca chars ni [])",
      tol["snapshot"]["previous_answer"]["gap_flags"] == ["a", "b"]
      and tol2["snapshot"]["previous_answer"]["gap_flags"] == ["not json"])

# ---- (D) planner: thread_context como llave aparte; el plan lo declara ----------------------------------------------------
PLAN_CALLS = []


def _planner_new(question, entities, thread_context=None):
    PLAN_CALLS.append(thread_context)
    return ({"work_type": "marker", "route": "evidence-run", "niches": [], "agents_applicable": [],
             "out_of_scope_reason": "smoke"}, {"input_tokens": 1, "output_tokens": 1})


def _planner_old(question, entities):
    PLAN_CALLS.append("old")
    return ({"work_type": "marker", "route": "evidence-run", "niches": [], "agents_applicable": []},
            {"input_tokens": 1, "output_tokens": 1})


env_for_plan = runs_mod.plan_thread_context(CHILD)
p1 = runs_mod.build_plan("q?", ["wt1a"], planner=_planner_new, history_rows=[], thread_context=env_for_plan)
p2 = runs_mod.build_plan("q?", ["wt1a"], planner=_planner_new, history_rows=[])
p3 = runs_mod.build_plan("q?", ["wt1a"], planner=_planner_old, history_rows=[], thread_context=env_for_plan)
try:
    runs_mod.plan_thread_context("nope")
    pe = None
except runs_mod.ThreadError as e:
    pe = e.status
check("(D) planner: plan_thread_context(CHILD) da el sobre (404 si no existe); build_plan lo pasa como llave aparte "
      "→ thread_context_declared True + planner.thread_context_delivered True; sin sobre → False/None; planner "
      "con firma vieja → delivered False (declarado, no roto)",
      pe == 404 and env_for_plan["snapshot"]["parent"]["run_id"] == CHILD
      and PLAN_CALLS[0] is not None and PLAN_CALLS[0]["parent"]["run_id"] == CHILD
      and p1["thread_context_declared"] is True and p1["judgment"]["planner"]["thread_context_delivered"] is True
      and PLAN_CALLS[1] is None and p2["thread_context_declared"] is False
      and p2["judgment"]["planner"]["thread_context_delivered"] is None
      and PLAN_CALLS[2] == "old" and p3["judgment"]["planner"]["thread_context_delivered"] is False)

# ---- (D) camino real del planner: user_text con llave thread_context ----------------------------------------------------
REAL.clear()
composite_auditor._anthropic_tool_call = _capture
try:
    runs_mod._default_planner("q?", ["wt1a"], thread_context=snap)
    runs_mod._default_planner("q?", ["wt1a"])
finally:
    composite_auditor._anthropic_tool_call = _real_call
check("(D) CAMINO REAL del planner: con snapshot user_text = {question, entities, thread_context}; sin él, "
      "{question, entities} exacto",
      set(json.loads(REAL[0][1])) == {"question", "entities", "thread_context"}
      and json.loads(REAL[1][1]) == {"question": "q?", "entities": ["wt1a"]})

# ---- (corrector ADR-0080) UNA corrida encadenada con la compuerta ENCENDIDA: el camino de prod ---------------------------------
os.environ["WITT_COMPETENCE_GATE"] = "1"
GATED = runs_mod.new_run("natalia", "gated child: does wt1a mark the pronephros at 72 hpf?", ["wt1a"], parent_run_id=CHILD)
SYNTH_CALLS.clear()
gated_row, gated_frozen = _run(GATED, _synth_new("wt1a marks the pronephros at 72 hpf as well."))
os.environ["WITT_COMPETENCE_GATE"] = "0"
check("(corrector ADR-0080) turno hijo con WITT_COMPETENCE_GATE=1 (el camino de prod): sin plan -> competence.reasons "
      "['route_evidence_run','niches_nonempty'] -> trigger 'competence' -> DOS pasadas, AMBAS con el snapshot del padre inyectado "
      "(thread_context como llave hermana en pass1 y pass2), deterministic_checks.pass 'pass2' y parent_identifier_leak evaluado "
      "sobre la candidata (pass2) con state 'checked'; frozen.competence.competent False, path_b_bundle aceptó el plan "
      "(harness_used True; el stub devuelve [] -> search_ledger 'harness-without-ledger…' declarado)",
      gated_row["state"] == "awaiting_closure"
      and gated_frozen["competence"]["competent"] is False
      and gated_frozen["competence"]["reasons"] == ["route_evidence_run", "niches_nonempty"]
      and gated_frozen["fallback"]["trigger"] == "competence"
      and [lbl for lbl, _tc in SYNTH_CALLS] == ["pass1", "pass2"]
      and all(tc is not None and tc["parent"]["run_id"] == CHILD for _l, tc in SYNTH_CALLS)
      and gated_frozen["deterministic_checks"]["pass"] == "pass2"
      and gated_frozen["deterministic_checks"]["parent_identifier_leak_state"] == "checked"
      and gated_frozen["deterministic_checks"]["parent_identifier_leak"] == []
      and gated_frozen["thread_context"] is not None
      and gated_frozen["search_ledger"]["state"].startswith("harness-without-ledger"),
      json.dumps({"reasons": gated_frozen["competence"]["reasons"], "passes": [l for l, _ in SYNTH_CALLS],
                  "gate_reasons": gated_frozen["deterministic_checks"]["reasons"],
                  "ledger": gated_frozen["search_ledger"]["state"]}))

# ---- lista y detalle: mismas columnas de investigación (T1) vistas desde runs.py ----------------------------------------------
lst = {r["run_id"]: r for r in db.list_runs(limit=1000)}
check("lista y detalle traen las MISMAS columnas de investigación para el hijo (thread_id, turn_no, turn_kind, "
      "parent_run_id, origin, root_question_id)",
      all(lst[CHILD][k] == db.get_run(CHILD)[k] for k in
          ("thread_id", "turn_no", "turn_kind", "parent_run_id", "origin", "root_question_id")))

n_ok, n = sum(CHECKS), len(CHECKS)
print(f"\n{n_ok}/{n} checks PASS" + ("" if n_ok == n else f"  ({n - n_ok} FAIL)"))
sys.exit(0 if n_ok == n else 1)

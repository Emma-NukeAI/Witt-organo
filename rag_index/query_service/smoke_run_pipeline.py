"""smoke_run_pipeline.py — gate determinista del bloque 3 (ADR-0049/0050).

Cubre: la reforma de la maquina de estados (DI_SUFFICIENT ya NO autoriza responder — auditoria en el
100% de las corridas), el composite_auditor invocable (agregacion worst-of, vocabulario homologado,
panel delgado NUNCA aprueba, jueces errados excluidos y registrados), record_audit con su PRIMER
llamador real, el modelo de corrida end-to-end (queued -> running -> awaiting_closure -> closed),
cancelacion como estado de primera clase, latido, y la bitacora UNICA (replay == traza viva).

100% offline: SQLite tmp, rag_backend/path_b/sintetizador/panel monkeypatcheados — cero red, cero
OpenAI/Anthropic, cero mutacion de la DATA INAMOVIBLE. Exit 0 = todo PASS.

Corre:  python rag_index/query_service/smoke_run_pipeline.py
(necesita fastapi + sqlalchemy; venv desechable — NO el .venv del MCP, ADR-0039.)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TMP = Path(tempfile.mkdtemp(prefix="smoke_run_pipeline_"))
os.environ["WITT_BACKEND_DB_URL"] = f"sqlite:///{TMP / 'backend.db'}"
os.environ.pop("NEO4J_URI", None)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402
import db  # noqa: E402
import runs as runs_mod  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from lib import answer_pipeline, composite_auditor, rag_backend  # noqa: E402
from lib.rag_backend import Hit, HitList  # noqa: E402

os.environ.pop("NEO4J_URI", None)

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


def _http_error(fn, *a, **kw):
    try:
        fn(*a, **kw)
        return None
    except HTTPException as e:
        return e.status_code


# ---- stubs deterministas ----------------------------------------------------------------------------
def _stub_caller_factory(verdicts):
    """caller inyectado: devuelve verdicts[lens] o lanza si el valor es una excepcion."""
    def _caller(member, system, user_text):
        v = verdicts[member["lens"]]
        if isinstance(v, Exception):
            raise v
        return ({"verdict": v, "caught": f"({member['lens']})", "correction_applied": "",
                 "confidence": 0.9, "reasons": []}, {"input_tokens": 10, "output_tokens": 5})
    return _caller


def _stub_synth(question, bundle):
    return {"direct_answer": "wt1a (ENSDARG00000031420) marks the zebrafish pronephros.",
            "stated_confidence": 0.8, "gap_flags": [], "evidence_cited": ["CORPUS-2026-0001"],
            "model": "stub-synth", "usage": {"input_tokens": 100, "output_tokens": 50}}


_chunk = Hit(doc_id="CORPUS-2026-0003#c000", type="chunk", score=0.9, text="pronephros evidence",
             metadata={})
answer_pipeline.path_b = lambda q, n=2, **kw: []
rag_backend.query = lambda text, k=6: HitList([_chunk], degraded=None)

# ---- 1. reforma ADR-0049: DI_SUFFICIENT ya NO autoriza responder ------------------------------------
b = answer_pipeline.retrieve("well covered question")
check("DI_SUFFICIENT es intermedio: may_answer_now=False + required_next=AUDIT (ADR-0049)",
      b["decision_state"]["state"] == "DI_SUFFICIENT"
      and b["decision_state"]["may_answer_now"] is False
      and "AUDIT" in b["decision_state"]["required_next_action"])

# ---- 2. composite_auditor: agregacion worst-of + vocabulario ----------------------------------------
ALL_A = {"correctness": "APPROVE", "overclaim": "APPROVE", "evidence-grounding": "APPROVE",
         "reproducibility": "APPROVE"}
r = composite_auditor.audit({"c": 1}, {"e": 1}, caller=_stub_caller_factory(ALL_A))
check("panel 4/4 APPROVE -> APPROVE, tally correcto, source_vocabulary presente",
      r["verdict"] == "APPROVE" and r["tally"]["APPROVE"] == 4
      and r["source_vocabulary"] == "APPROVE|APPROVE_MINOR|REVISE" and r["n_valid"] == 4)
r = composite_auditor.audit({"c": 1}, {"e": 1}, caller=_stub_caller_factory(
    {**ALL_A, "overclaim": "APPROVE_MINOR"}))
check("worst-of: un APPROVE_MINOR degrada el verdict global", r["verdict"] == "APPROVE_MINOR")
r = composite_auditor.audit({"c": 1}, {"e": 1}, caller=_stub_caller_factory(
    {**ALL_A, "evidence-grounding": "REVISE"}))
check("worst-of: un REVISE manda (nunca se promedia el catch)", r["verdict"] == "REVISE")

# ---- 3. panel delgado NUNCA aprueba (Mode 1 minimo >=3) ---------------------------------------------
r = composite_auditor.audit({"c": 1}, {"e": 1}, caller=_stub_caller_factory(
    {"correctness": "APPROVE", "overclaim": RuntimeError("judge down"),
     "evidence-grounding": RuntimeError("judge down"), "reproducibility": "APPROVE"}))
errored = [p for p in r["panel"] if p.get("status") == "errored"]
check("2 jueces caidos (<3 validos) -> REVISE + panel_incomplete (conservador)",
      r["verdict"] == "REVISE" and r.get("panel_incomplete") is True and r["n_valid"] == 2)
check("jueces errados quedan REGISTRADOS como errored (excluidos, jamas fabricados)",
      len(errored) == 2 and all("error" in p for p in errored))

# ---- 4. apply_to_bundle: el PRIMER llamador real de record_audit ------------------------------------
b = answer_pipeline.retrieve("q for audit")
r_ok = composite_auditor.audit({"c": 1}, {"e": 1}, caller=_stub_caller_factory(ALL_A))
b = composite_auditor.apply_to_bundle(b, r_ok, ["CORPUS-2026-0003#c000"])
import hashlib
payload = {k: v for k, v in b.items() if k != "bundle_identity"}
sha = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
check("APPROVE -> record_audit -> AUDIT_APPROVED + panel visible en bundle.audit + identidad re-estampada",
      b["decision_state"]["state"] == "AUDIT_APPROVED" and len(b["audit"]["panel"]) == 4
      and b["audit"]["verdict"] == "APPROVE" and b["bundle_identity"]["sha256"] == sha)
b2 = answer_pipeline.retrieve("q for reject")
r_rev = composite_auditor.audit({"c": 1}, {"e": 1}, caller=_stub_caller_factory(
    {**ALL_A, "correctness": "REVISE"}))
b2 = composite_auditor.apply_to_bundle(b2, r_rev, ["x"])
check("REVISE -> AUDIT_REJECTED (evidencia rechazada, gap explicito)",
      b2["decision_state"]["state"] == "AUDIT_REJECTED")

# ---- 5. corrida end-to-end (worker sincrono, panel/sintesis stubbeados) ------------------------------
db.init_db()
db.upsert_user("natalia", "Natalia", "medico", "pw-natalia-123")
AUTH = "Bearer " + app.login(app.LoginBody(username="natalia", password="pw-natalia-123"))["token"]
rv = app.create_run(app.RunBody(question="does wt1a mark the pronephros?", entities=[]),
                    authorization=AUTH)
RID = rv["run_id"]
check("POST /runs -> queued con run_id + evento inicial", rv["state"] == "queued" and len(RID) == 32)
claimed = db.claim_next_queued()
check("claim atomico: queued -> running (FIFO)", claimed["run_id"] == RID
      and db.get_run(RID)["state"] == "running")
runs_mod.execute_run(claimed, synthesizer=_stub_synth,
                     panel_caller=_stub_caller_factory(ALL_A))
run = db.get_run(RID)
check("corrida termina awaiting_closure (terminal SIEMPRE post-audit, ADR-0049)",
      run["state"] == "awaiting_closure" and run["finished_at"] is not None)
ev = app.get_events(RID, after=0, authorization=AUTH)["events"]
types = [e["type"] for e in ev]
check("bitacora: eventos por etapa con seq monotonico (replay == traza viva)",
      [e["seq"] for e in ev] == list(range(1, len(ev) + 1))
      and "stage.path_a" in types and "stage.assess_sufficiency" in types
      and "stage.synthesize.done" in types and "stage.deterministic_gate" in types
      and "stage.audit.verdict" in types, f"n={len(ev)}")
rec = app.get_frozen_record(RID, authorization=AUTH)
check("registro congelado persistido en backend: contrato + audit + store_at_retrieval + identidad",
      rec["render_contract_version"] == "1.0" and rec["audit"]["verdict"] == "APPROVE"
      and rec["question_matches_run"] is True and rec["decision_state"]["state"] == "AUDIT_APPROVED"
      and "store_version" in rec["store_at_retrieval"] and rec["bundle_identity"]["run_id"] == RID)
view = app.get_run(RID, authorization=AUTH)
check("latido expuesto (heartbeat_age_s) y no-stale tras actividad",
      view["heartbeat_age_s"] is not None and view["heartbeat_stale"] is False)

# ---- 6. cierre explicito ------------------------------------------------------------------------------
res = app.close_run(RID, authorization=AUTH)
rec2 = app.get_frozen_record(RID, authorization=AUTH)
check("close: awaiting_closure -> closed + frozen_at + closed_by en el registro",
      res["closed"] and db.get_run(RID)["state"] == "closed"
      and rec2.get("frozen_at") and rec2.get("closed_by") == "natalia")
check("close doble -> 409 (el cierre es unico)", _http_error(app.close_run, RID, authorization=AUTH) == 409)

# ---- 7. cancelacion como estado de primera clase -----------------------------------------------------
rv = app.create_run(app.RunBody(question="cancel me", entities=[]), authorization=AUTH)
RID2 = rv["run_id"]
app.cancel_run(RID2, authorization=AUTH)
check("cancel de un run queued -> cancelled inmediato (no failed, no muerto)",
      db.get_run(RID2)["state"] == "cancelled")
rv = app.create_run(app.RunBody(question="cancel mid-flight", entities=[]), authorization=AUTH)
RID3 = rv["run_id"]
claimed = db.claim_next_queued()


def _synth_then_cancel(question, bundle):
    db.request_cancel(RID3)   # la cancelacion llega mientras la corrida trabaja
    return _stub_synth(question, bundle)


runs_mod.execute_run(claimed, synthesizer=_synth_then_cancel,
                     panel_caller=_stub_caller_factory(ALL_A))
check("cancel en vuelo: se detecta en la frontera de etapa -> cancelled (jamas disfrazado de failed)",
      db.get_run(RID3)["state"] == "cancelled" and db.get_run(RID3)["error"] is None)

# ---- 8. fallo honesto ---------------------------------------------------------------------------------
rv = app.create_run(app.RunBody(question="explode", entities=[]), authorization=AUTH)
claimed = db.claim_next_queued()


def _synth_boom(question, bundle):
    raise ValueError("synth exploded (smoke)")


runs_mod.execute_run(claimed, synthesizer=_synth_boom, panel_caller=_stub_caller_factory(ALL_A))
run = db.get_run(rv["run_id"])
check("fallo -> failed con error registrado + evento level=error",
      run["state"] == "failed" and "synth exploded" in (run["error"] or ""))

npass = sum(CHECKS)
print("\n== %d/%d PASS ==" % (npass, len(CHECKS)))
sys.exit(0 if npass == len(CHECKS) else 1)

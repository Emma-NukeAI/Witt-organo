"""
runs.py — run model + execution worker for the webapp backend (block 3, ADR-0050).

A run is the unit the webapp submits: question -> retrieve (answer_pipeline, ONE state machine — never
re-assembled) -> synthesize (Claude, best-tier policy) -> deterministic anti-fabrication gate
(verify_output) -> composite-audit panel (ADR-0049, 100% of runs) -> terminal AUDIT_APPROVED|REJECTED
-> frozen record persisted in the backend DB (ADR-0047 decision 2: the webapp only reads).

Events: every stage appends to run_events (db.add_event) — the ONE log the live SSE trace and the
replay both read. The heartbeat is last_event_at: a run with no event for N minutes is distinguishable
from a working one (the 1800s sklearn-deadlock lesson). Cancellation is a flag checked at stage
boundaries — a cancelled run is CANCELLED, never disguised as failed.

ZERO DATA INAMOVIBLE mutation: runs read the DI and write only to the backend DB (runs/run_events) +
the gitignored mcp_cache. Approved external evidence still re-enters the DI ONLY via the human-gated
ingest path.

Spend per run (authorized, measured, never capped — ADR-0047 d.3): 1 query embed (path_a) + 1 synthesis
(opus) + the 4-reviewer panel (~1-2.50 USD). Usage is accumulated into the frozen record.
"""
import json
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import db  # noqa: E402
from lib import answer_pipeline, composite_auditor, resolve_id, verify_output  # noqa: E402

RENDER_CONTRACT_VERSION = "1.0"
SYNTH_MODEL = "claude-opus-4-8"   # best-tier policy (2026-06-13 directive) — never downgraded to save cost

SYNTH_TOOL = {
    "name": "emit_answer",
    "description": ("Answer the biology question using ONLY the provided evidence bundle. If the bundle "
                    "is thin, say so in gap_flags and keep confidence honest. NEVER invent identifiers: "
                    "only assert gene IDs that appear in the evidence or the verified-store resolutions."),
    "input_schema": {
        "type": "object",
        "properties": {
            "direct_answer": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "gap_flags": {"type": "array", "items": {"type": "string"}},
            "evidence_cited": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["direct_answer", "confidence"],
    },
}


class RunCancelled(Exception):
    pass


def _compact_evidence(bundle):
    """The evidence view handed to the synthesizer and the panel — compact, never the raw 100K bundle."""
    return {
        "path_a_hits": [{"doc_id": h["doc_id"], "type": h["type"], "score": h["score"], "text": h["text"]}
                        for h in bundle["path_a"]["hits"]],
        "retrieval": bundle["path_a"]["retrieval"],
        "entities_checked": bundle["entities_checked"],
        "sufficiency": bundle["sufficiency"],
        "path_b": {k: v for k, v in bundle["path_b"].items() if k != "tool_universe_directive"},
    }


def _evidence_ids(bundle):
    ids = [h["doc_id"] for h in bundle["path_a"]["hits"]]
    for p in bundle["path_b"].get("papers", []):
        rec = p.get("search_rec", {})
        ids.append(f"PMID:{rec['pmid']}" if rec.get("pmid") else (rec.get("pmcid") or rec.get("doi") or "paper"))
    return ids


def _default_synthesizer(question, bundle):
    """Single-pass synthesis from the bundle (v1; the two-pass delta is block 4). Returns
    {direct_answer, stated_confidence, gap_flags, evidence_cited, model, usage}."""
    system = ("You answer zebrafish pronephros research questions for a medical team, from a curated "
              "evidence bundle (DATA INAMOVIBLE). Use ONLY the bundle. Be direct; keep confidence honest "
              "(a thin bundle means LOW confidence + explicit gap_flags); technical identifiers stay in "
              "English. Never assert an identifier that is not in the evidence.")
    user_text = json.dumps({"question": question, "evidence": _compact_evidence(bundle)},
                           ensure_ascii=False, default=str)
    out, usage = composite_auditor._anthropic_tool_call(
        SYNTH_MODEL, system, user_text, tool=SYNTH_TOOL, max_tokens=2000)
    gap_flags = list(out.get("gap_flags", []))
    if out.get("confidence") is None:
        # run a361f566 (first real run) surfaced this: the model may omit the field even when required.
        # Three-state confidence discipline (UI contract §4): an absent value is DECLARED, never a
        # silent null that could read as "not measured" or "clean".
        gap_flags.append("stated_confidence ABSENT (synthesizer omitted it after retry) — not calibratable")
    return {"direct_answer": out["direct_answer"], "stated_confidence": out.get("confidence"),
            "gap_flags": gap_flags, "evidence_cited": out.get("evidence_cited", []),
            "model": SYNTH_MODEL, "usage": usage}


def execute_run(run, synthesizer=None, panel_caller=None):
    """Execute one claimed run end-to-end. Deterministic under injected synthesizer/panel_caller (the
    offline gate); live otherwise. Never raises — every exit is a recorded terminal state + event."""
    run_id = run["run_id"]
    synthesizer = synthesizer or _default_synthesizer

    def _check_cancel():
        if db.cancel_requested(run_id):
            raise RunCancelled()

    def _on_stage(name, payload):
        degraded = None
        if name == "path_a":
            mode = payload.get("retrieval", {}).get("mode")
            degraded = None if mode == "semantic" else mode
        db.add_event(run_id, f"stage.{name}", payload=payload, agent="answer_pipeline",
                     degraded=degraded)
        _check_cancel()

    try:
        db.add_event(run_id, "run.state", payload={"state": "running"})
        _check_cancel()

        # 1) retrieve — the ONE state machine, instrumented via on_stage (never re-assembled)
        bundle = answer_pipeline.retrieve(run["question"],
                                          entities=[e for e in run["entities_csv"].split(",") if e],
                                          on_stage=_on_stage)
        # one identity end-to-end: the run's id IS the bundle's id (ADR-0044)
        bundle["run_id"] = run_id
        bundle["bundle_identity"] = answer_pipeline._identity(bundle)

        # 2) synthesize (v1 single-pass)
        db.add_event(run_id, "stage.synthesize.start", agent=SYNTH_MODEL)
        answer = synthesizer(run["question"], bundle)
        db.add_event(run_id, "stage.synthesize.done", agent=answer.get("model"),
                     payload={"stated_confidence": answer.get("stated_confidence"),
                              "gap_flags": answer.get("gap_flags", [])})
        _check_cancel()

        # 3) deterministic anti-fabrication gate (Logic-LM-class, NOT an LLM) — handed to the panel
        adm, reasons = verify_output.admissible({"direct_answer": answer["direct_answer"],
                                                 "evidence_cited": answer.get("evidence_cited", [])})
        report = verify_output.verify_identifiers(answer["direct_answer"]).as_dict()
        checks = {"admissible": adm, "reasons": reasons, "identifier_report": report}
        db.add_event(run_id, "stage.deterministic_gate", tool="verify_output",
                     payload=checks, level="info" if adm else "warning")
        _check_cancel()

        # 4) composite audit — 100% of runs (ADR-0049), the terminal transition
        db.add_event(run_id, "stage.audit.start", agent="composite-auditor")
        audit_result = composite_auditor.audit(
            claim={"direct_answer": answer["direct_answer"],
                   "stated_confidence": answer.get("stated_confidence")},
            evidence=_compact_evidence(bundle), deterministic_checks=checks,
            required_because=bundle["decision_state"]["state"], caller=panel_caller)
        bundle = composite_auditor.apply_to_bundle(bundle, audit_result, _evidence_ids(bundle))
        db.add_event(run_id, "stage.audit.verdict", agent="composite-auditor",
                     payload={"verdict": audit_result["verdict"], "tally": audit_result["tally"],
                              "n_valid": audit_result["n_valid"],
                              "source_vocabulary": audit_result["source_vocabulary"]},
                     level="info" if audit_result["verdict"] != "REVISE" else "warning")

        # 5) frozen record (backend-persisted; the webapp only reads — ADR-0047 d.2)
        frozen = {
            "render_contract_version": RENDER_CONTRACT_VERSION,
            "run_id": run_id, "user_id": run["user_id"], "question": run["question"],
            "measured_at": bundle["stamp"],
            "store_at_retrieval": {"store_version": _safe(resolve_id.store_version),
                                   "index_version": _index_version()},
            "retrieval_summary": bundle["retrieval_summary"],
            "decision_state": bundle["decision_state"],
            "audit": bundle["audit"],
            "answer": {"direct_answer": answer["direct_answer"],
                       "stated_confidence": answer.get("stated_confidence"),
                       "gap_flags": answer.get("gap_flags", []),
                       "evidence_cited": answer.get("evidence_cited", []),
                       "model": answer.get("model")},
            "deterministic_checks": checks,
            "usage": {"synthesis": answer.get("usage", {}), "panel": audit_result.get("usage", {})},
            "bundle_identity": bundle["bundle_identity"],
            "question_matches_run": bundle["question"] == run["question"],
        }
        db.update_run(run_id, state="awaiting_closure", finished_at=db._now(),
                      bundle_json=json.dumps(bundle, ensure_ascii=False, default=str),
                      frozen_record_json=json.dumps(frozen, ensure_ascii=False, default=str))
        db.add_event(run_id, "run.state", payload={"state": "awaiting_closure",
                                                   "verdict": audit_result["verdict"]})
    except RunCancelled:
        db.update_run(run_id, state="cancelled", finished_at=db._now())
        db.add_event(run_id, "run.state", payload={"state": "cancelled"}, level="warning")
    except Exception as e:
        db.update_run(run_id, state="failed", finished_at=db._now(),
                      error=f"{type(e).__name__}: {str(e)[:400]}")
        db.add_event(run_id, "error", payload={"error": f"{type(e).__name__}: {str(e)[:400]}"},
                     level="error")
        db.add_event(run_id, "run.state", payload={"state": "failed"}, level="error")


def _safe(fn):
    try:
        return fn()
    except Exception:
        return None


def _index_version():
    try:
        import server
        return server._index_version()
    except Exception:
        return None


def close_run(run_id, by):
    """Explicit closure (the requirement for a run to become precedent — pending closure ADR): freezes
    the record (frozen_at) and stops further measurement mutation. ratings[] append AFTER this point."""
    run = db.get_run(run_id)
    if run is None:
        return None
    if run["state"] != "awaiting_closure":
        return {"closed": False, "state": run["state"],
                "note": "only an awaiting_closure run can be closed"}
    now = db._now()
    frozen = json.loads(run["frozen_record_json"] or "{}")
    frozen["frozen_at"] = now.isoformat(timespec="seconds")
    frozen["closed_by"] = by
    db.update_run(run_id, state="closed", frozen_at=now, closed_by=by,
                  frozen_record_json=json.dumps(frozen, ensure_ascii=False, default=str))
    db.add_event(run_id, "run.state", payload={"state": "closed", "closed_by": by})
    return {"closed": True, "run_id": run_id, "frozen_at": frozen["frozen_at"]}


def new_run(user_id, question, entities=None):
    run_id = uuid.uuid4().hex
    db.create_run(run_id, user_id, question, entities)
    db.add_event(run_id, "run.state", payload={"state": "queued"})
    return run_id


# --- worker threads ----------------------------------------------------------------------------------

_STOP = threading.Event()


def worker_loop(poll_seconds=1.0):
    while not _STOP.is_set():
        run = db.claim_next_queued()
        if run is None:
            time.sleep(poll_seconds)
            continue
        execute_run(run)


def start_workers(n=2):
    """In-process daemon workers (single uvicorn process, ADR-0048). sklearn is already preloaded on the
    MAIN thread by the app lifespan before workers start — the 1800s deadlock cannot recur here."""
    for i in range(n):
        threading.Thread(target=worker_loop, name=f"run-worker-{i}", daemon=True).start()


def stop_workers():
    _STOP.set()

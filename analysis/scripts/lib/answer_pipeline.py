"""
answer_pipeline.py — DI-first / external-fallback retrieval orchestrator (ADR-0022, slice 1b).

Given a question, gathers evidence on TWO paths:
  Path A — DATA INAMOVIBLE first: semantic query (rag_backend, live Neo4j) + resolve key entities.
  Path B — external fallback (only when A is insufficient): Europe PMC search + fetch_paper full text.
  NEVER-STOPPER (founder rule, 2026-06-13): absence in DI never stops the answer — it TRIGGERS Path B.

Output = an auditor-ready EVIDENCE BUNDLE. This stage only gathers + routes; it does NOT audit
(slice 1c, composite-auditor) or synthesize the final answer. Sufficiency signal (v1):
  insufficient if DI has no paper/chunk evidence on the topic, OR a key entity is absent from DI.
As the human-gated re-ingest loop (slice 1d) adds papers, chunk hits appear and Path A becomes
sufficient on its own — the store reinforces itself.

Spend: Path A embeds the query (OpenAI, authorized 2026-06-13); Path B (Europe PMC) is free.
Bundle cached to mcp_cache/answer_bundle_<run_id>.json — named by run_id, NEVER by question-slug+date
(ADR-0044: a hardcoded date + 40-char slug silently overwrote bundles across users/days; the collision
rendered as a perfectly-instrumented sheet showing someone else's data).

Epistemic state travels with the bundle (ADR-0043): path_a carries `retrieval` {mode, raw_marker, n_hits,
k_requested} where `mode` is a 4-literal enum (RETRIEVAL_MODES) and NEVER None/nullable — `null` cannot
distinguish "measured clean" from "not measured". The run-level aggregate is `retrieval_summary`
(worst-of-n, declared).

Decision pathway (explicit state machine — the route to an answer is STRUCTURAL, not contract-dependent):
  RETRIEVE -> Path A (DI)
     |- sufficient ----------------------> [DI_SUFFICIENT]   may_answer=Y           -> ANSWER (from DI)
     |- insufficient -> Path B (external) -> [FALLBACK_FETCHED] may_answer=N -> AUDIT (composite >=3, REQUIRED)
                                                |- record_audit, approved -> [AUDIT_APPROVED] Y -> ANSWER + PROPOSE(gate)
                                                |- record_audit, none     -> [AUDIT_REJECTED]   -> ANSWER(gap) / REFINE
  The bundle's `decision_state` carries may_answer_now + required_next_action, so a consumer (agent,
  human, orchestrator) CANNOT answer external evidence without an audit verdict (record_audit()).
  Audit + propose are wired transitions, not steps an agent is trusted to remember (CLAUDE.md §7).

CLI:
  python analysis/scripts/lib/answer_pipeline.py "Is osr1 required for zebrafish pronephros?" --entities osr1,prkci,pax2a
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import pathlib
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2].parent
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
_env = ROOT / ".secrets" / "deploy.env"
if not os.environ.get("NEO4J_URI") and _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())
os.environ.setdefault("RAG_BACKEND", "neo4j")

from lib import rag_backend, resolve_id, fetch_paper  # noqa: E402

CACHE = ROOT / "mcp_cache"

# --- retrieval-mode enum (ADR-0043) -----------------------------------------------------------
# Four EXPLICIT literals, never None/nullable: `null` cannot distinguish "measured clean" from
# "not measured", which forces any consumer (the webapp UI in particular) to paint the worst case.
RETRIEVAL_MODES = ("semantic", "degraded-dense-failed", "reduced-by-config", "not-measured")
_MODE_SEVERITY = {"semantic": 0, "reduced-by-config": 1, "not-measured": 2, "degraded-dense-failed": 3}
_MARKER_MISSING = object()   # sentinel: the result carried NO `degraded` attribute at all


def _mode_of(marker):
    """Map a raw HitList.degraded marker to the 4-literal enum. Unknown truthy markers (including the
    server-level 'sparse' timeout-fallback stamp) map to 'degraded-dense-failed' — degraded-somehow must
    never render as clean; `raw_marker` preserves the original literal untranslated."""
    if marker is _MARKER_MISSING:
        return "not-measured"
    if marker is None:
        return "semantic"
    if marker == "sparse-by-config":
        return "reduced-by-config"
    return "degraded-dense-failed"   # 'dense-failed:sparse-only', 'sparse', any unknown degradation


def _identity(bundle):
    """bundle_identity (ADR-0044): sha256 over the canonical payload (bundle minus bundle_identity), so a
    consumer can re-verify that the sheet it renders is the run it claims to be. Recomputed on every
    mutation of the bundle (record_audit re-stamps it)."""
    payload = {k: v for k, v in bundle.items() if k != "bundle_identity"}
    sha = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {"sha256": sha, "run_id": bundle.get("run_id"), "question": bundle.get("question")}


def path_a(question, k=6):
    """DATA INAMOVIBLE first: live semantic retrieval + a literature-presence signal. The degradation
    marker travels ON the returned dict as `retrieval` (envelope-level, ADR-0043) — serializing only the
    hits dropped HitList.degraded silently, and with 0 hits there was nothing to stamp it on at all."""
    hits = rag_backend.query(question, k)
    marker = getattr(hits, "degraded", _MARKER_MISSING)
    serial = [{"doc_id": h.doc_id, "type": h.type, "score": round(h.score, 4),
               "text": (h.text or "")[:140]} for h in hits]
    return {"n_hits": len(serial), "top_score": serial[0]["score"] if serial else 0.0,
            "has_literature_chunks": any(h.type == "chunk" for h in hits),
            "retrieval": {"mode": _mode_of(marker),
                          "raw_marker": None if marker is _MARKER_MISSING else marker,
                          "n_hits": len(serial), "k_requested": k},
            "hits": serial}


def check_entities(entities):
    """Resolve each key entity against the verified store (feeds the auditor's absence re-check, 1c)."""
    out = {}
    for e in entities or []:
        r = resolve_id.resolve(e)
        out[e] = {"in_di": r is not resolve_id.NOT_FOUND,
                  "ensdarg": None if r is resolve_id.NOT_FOUND else r.ensdarg}
    return out


def assess_sufficiency(a, ent):
    reasons = []
    if not a["has_literature_chunks"]:
        reasons.append("DI has no paper/chunk evidence on this topic (catalog-only)")
    missing = [e for e, v in ent.items() if not v["in_di"]]
    if missing:
        reasons.append(f"key entities absent from DI: {missing}")
    return {"sufficient": not reasons, "reasons": reasons, "missing_entities": missing}


def _search_tooluniverse(question, n):
    """Tool Universe literature breadth (PubMed + many DBs) — the ADDITIONAL Path-B source beyond
    Europe PMC. Activates when the `tooluniverse` MCP is connected (agent context) or its SDK is installed.
    Not reachable from this standalone script today (SDK absent in .venv; MCP is per-session), so it returns
    [] and Europe PMC stays the dependency-free default. The explicit MCP query an agent should run is
    surfaced by tool_universe_directive() and threaded into the bundle (path_b.tool_universe_directive),
    so Tool Universe is NAMED + actionable by the agent rather than silently dropped (ADR-0022 / ADR-0026)."""
    return []


def tool_universe_directive(question, n=2):
    """The explicit Tool Universe query an agent should run via the connected `tooluniverse` MCP when Path B
    triggers (R4 / ADR-0026). The standalone pipeline cannot reach the MCP (per-session; SDK absent in
    .venv), so instead of silently dropping Tool Universe this NAMES the exact call — the orchestrating
    agent executes it and merges hits (source='tooluniverse') through the SAME composite-auditor gate
    (ADR-0022) before any answer/propose. Live execution requires the MCP connected (reopen Claude Code +
    approve .mcp.json); it is NOT verifiable from this standalone script."""
    return {
        "requires_mcp": "tooluniverse (uvx tooluniverse; project-scoped .mcp.json)",
        "tools": ["PubMed_search_articles", "EuropePMC_search", "tooluniverse-literature-deep-research"],
        "query": question,
        "n": n,
        "merge_back": ("add hits as path_b papers with source='tooluniverse', then route through the SAME "
                       "composite-auditor Mode 1 (>=3) audit gate (ADR-0022) before any answer/propose"),
        "live": False,
        "note": "Not executed by this standalone script (MCP is per-session). Surfaced for the agent to run.",
    }


def path_b(question, n=2, full_text=True, sources=("europepmc", "tooluniverse")):
    """External fallback — MULTI-SOURCE, never a stopper. Europe PMC is the built-in dependency-free
    source; Tool Universe (PubMed + more DBs) layers in when reachable. Each paper records its `source`."""
    papers = []
    if "europepmc" in sources:
        for rec in fetch_paper.search_europepmc(question, n=n):
            ident = f"PMID:{rec['pmid']}" if rec.get("pmid") else (rec.get("pmcid") or rec.get("doi"))
            got = fetch_paper.fetch_external(ident, want_full_text=full_text) if ident else {"found": False}
            papers.append({
                "source": "europepmc",
                "search_rec": {k: rec.get(k) for k in ("pmid", "pmcid", "doi", "title", "year", "journal", "is_oa", "cited_by")},
                "fetched": {k: got.get(k) for k in ("found", "full_text", "n_chunks", "raw_cached", "raw_ref")},
            })
    if "tooluniverse" in sources:
        papers += _search_tooluniverse(question, n)  # documented breadth hook (live when MCP/SDK present)
    return papers


def _state(name, may_answer, may_propose, required_next):
    """A node in the explicit decision-state machine (see module docstring)."""
    return {"state": name, "may_answer_now": may_answer, "may_propose_now": may_propose,
            "required_next_action": required_next}


def retrieve(question, entities=None, n_papers=2):
    """The orchestrator: Path A, then Path B iff A is insufficient. Never a stopper. The returned bundle
    carries an explicit `decision_state` that GATES what may happen next — answering external evidence is
    blocked until an audit verdict is recorded (record_audit())."""
    a = path_a(question)
    ent = check_entities(entities)
    suf = assess_sufficiency(a, ent)
    bundle = {"question": question,
              "run_id": uuid.uuid4().hex,
              "stamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
              "question_slug": re.sub(r"[^a-z0-9]+", "-", question.lower())[:40].strip("-"),
              "entities_checked": ent, "path_a": a, "sufficiency": suf}
    if suf["sufficient"]:
        bundle["path_b"] = {"triggered": False, "reason": "DI sufficient (literature present + entities resolved)"}
        bundle["decision_state"] = _state(
            "DI_SUFFICIENT", may_answer=True, may_propose=False,
            required_next="ANSWER — synthesize from the DI Path-A hits. No external evidence involved.")
    else:
        bundle["path_b"] = {"triggered": True, "triggered_by": suf["reasons"],
                            "papers": path_b(question, n=n_papers),
                            "tool_universe_directive": tool_universe_directive(question, n_papers)}
        bundle["decision_state"] = _state(
            "FALLBACK_FETCHED", may_answer=False, may_propose=False,
            required_next="AUDIT — composite-auditor Mode 1 (>=3 adversarial) MUST verdict each Path-B paper "
                          "(DI absence re-check + external veracity) BEFORE any answer. Do NOT synthesize from "
                          "unaudited external evidence (CLAUDE.md §7). For full breadth ALSO run "
                          "path_b.tool_universe_directive via the connected tooluniverse MCP and audit those "
                          "hits the SAME way. Feed all verdicts to record_audit().")
    # Run-level epistemic aggregate (ADR-0043): one run may hold several retrievals; the band is ONE.
    # worst-of-n, declared — aggregating by "first" or "majority" paints a half-degraded run clean.
    modes = [a["retrieval"]["mode"]]
    bundle["retrieval_summary"] = {"mode": max(modes, key=_MODE_SEVERITY.__getitem__),
                                   "retrievals": len(modes), "aggregation": "worst-of-n"}
    bundle["bundle_identity"] = _identity(bundle)
    return bundle


def record_audit(bundle, approved, rejected, note=""):
    """Transition the pathway AFTER the composite-auditor returns. `approved`/`rejected` = lists of paper
    ids. Structural enforcement: answering / proposing external evidence is only unlocked once a verdict is
    recorded here — the path is marked, not left to the agent's memory of the contract."""
    bundle["audit"] = {"approved": list(approved), "rejected": list(rejected), "note": note}
    if approved:
        bundle["decision_state"] = _state(
            "AUDIT_APPROVED", may_answer=True, may_propose=True,
            required_next=f"ANSWER from approved evidence {list(approved)} + PROPOSE to the DI via "
                          "propose_from_external.py (human gate). Rejected/absent items -> gap_flags.")
    else:
        bundle["decision_state"] = _state(
            "AUDIT_REJECTED", may_answer=True, may_propose=False,
            required_next="ANSWER with the gap EXPLICIT (no on-target evidence passed audit) + record a gap_flag; "
                          "optionally REFINE (e.g. follow an auditor-surfaced lead) and re-run retrieve().")
    bundle["bundle_identity"] = _identity(bundle)   # the audit mutated the bundle -> re-stamp (ADR-0044)
    return bundle


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--entities", default="", help="comma-separated gene symbols to check in DI")
    ap.add_argument("--papers", type=int, default=2)
    a = ap.parse_args()
    ents = [e.strip() for e in a.entities.split(",") if e.strip()]
    bundle = retrieve(a.question, entities=ents, n_papers=a.papers)
    # ADR-0044: filename by run_id — a slug+date name silently overwrote bundles across users/days.
    (CACHE / f"answer_bundle_{bundle['run_id']}.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print(json.dumps(bundle, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""
answer_pipeline.py — DI-first / external-fallback retrieval orchestrator (ADR-0022, slice 1b).

Given a question, gathers evidence on TWO paths:
  Path A — DATA INAMOVIBLE first: semantic query (rag_backend, live Neo4j) + resolve key entities.
  Path B — external fallback (only when A is insufficient), MULTI-SOURCE (see PATH_B_SOURCES):
             europepmc — literature search + fetch_paper full text (free, no key)
             zfin      — NATIVE zebrafish mutant/knockdown phenotypes with PMIDs, from the project's own
                         Tool Universe workspace tool (tapón 1·A, 2026-08-19). A stronger evidence tier
                         than generic literature for a pronephros claim; keys on gene SYMBOLS.
             tooluniverse — the PACKAGE tools; still a named directive until the SDK ships (tapón 1·B).
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

Decision pathway (explicit state machine — the route to an answer is STRUCTURAL, not contract-dependent).
REFORMED by ADR-0049 (founder decision 2026-08-09: the audit runs on 100% of runs, DI-sufficient included;
cost is measured, never capped). DI_SUFFICIENT and FALLBACK_FETCHED are now INTERMEDIATE states; the
terminal of every run is AUDIT_APPROVED | AUDIT_REJECTED:
  RETRIEVE -> Path A (DI)
     |- sufficient ----------------------> [DI_SUFFICIENT]    may_answer=N -> AUDIT (composite >=3, REQUIRED)
     |- insufficient -> Path B (external) -> [FALLBACK_FETCHED] may_answer=N -> AUDIT (composite >=3, REQUIRED)
                                                |- record_audit, approved -> [AUDIT_APPROVED] Y -> ANSWER + PROPOSE(gate)
                                                |- record_audit, none     -> [AUDIT_REJECTED]   -> ANSWER(gap) / REFINE
  The bundle's `decision_state` carries may_answer_now + required_next_action, so a consumer (agent,
  human, orchestrator) CANNOT answer without an audit verdict (record_audit()) on EITHER branch.
  The invokable panel lives in lib/composite_auditor.py (record_audit's first real caller).
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
import time
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
    so Tool Universe is NAMED + actionable by the agent rather than silently dropped (ADR-0022 / ADR-0026).

    NOTE (tapón 1·A): the WORKSPACE tools of `.tooluniverse/tools/` do NOT go through here — they are
    stdlib-pure and importable by path, so they run for real (see _search_zfin). This hook stays for the
    PACKAGE tools, which still need the SDK (tapón 1·B)."""
    return []


# --- Tool Universe workspace tools (tapón 1·A) --------------------------------------------------
# `.tooluniverse/tools/*.py` are the project's OWN tools: stdlib-pure and explicitly "importable +
# testable without the tooluniverse package installed" (their own docstrings). They are tracked in git,
# so the service container gets them with `COPY . /app`. Loading them BY PATH is required: the directory
# is dot-prefixed, hence not an importable package.
_TU_WORKSPACE = ROOT / ".tooluniverse" / "tools"
_WS_CACHE = {}


def _workspace_tool(filename, attr):
    """Load one workspace-tool callable by path. Returns None when absent/unloadable — a missing tool
    DEGRADES its source and is declared in the ledger; it never breaks a run (§6 no-hang rule)."""
    key = (filename, attr)
    if key not in _WS_CACHE:
        fn = None
        try:
            import importlib.util
            path = _TU_WORKSPACE / filename
            spec = importlib.util.spec_from_file_location(f"_witt_ws_{path.stem}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            fn = getattr(mod, attr, None)
        except Exception:
            fn = None
        _WS_CACHE[key] = fn
    return _WS_CACHE[key]


# Anatomy filter for ZFIN phenotype statements. ZFIN statements are ENGLISH; the team asks in Spanish,
# so the table maps BOTH (the LOTE-03 lesson: an index in another language returns zero and it looks
# identical to "nothing exists"). Deterministic and DECLARED — never a model deciding the filter.
ZFIN_ANATOMY_TERMS = (
    ("pronephr", ("pronephr", "pronefr", "prone fr")),
    ("glomer",   ("glomer", "glomér")),
    ("duct",     ("duct", "ducto", "conducto")),
    ("tubul",    ("tubul", "túbul", "tubul")),
    ("podocyte", ("podocyte", "podocito")),
    ("kidney",   ("kidney", "riñón", "rinon", "renal")),
)
ZFIN_BUDGET_S = float(os.environ.get("WITT_ZFIN_BUDGET_S", "45"))
ZFIN_MAX_ENTITIES = int(os.environ.get("WITT_ZFIN_MAX_ENTITIES", "6"))
ZFIN_MAX_STATEMENTS = int(os.environ.get("WITT_ZFIN_MAX_STATEMENTS", "12"))


def zfin_anatomy_filter(question):
    """(term, source) — the anatomy keyword sent to ZFIN, derived deterministically from the question.
    None means "no filter" (all phenotypes), which is a WIDER search, never a failed one."""
    q = (question or "").lower()
    for term, needles in ZFIN_ANATOMY_TERMS:
        if any(nd in q for nd in needles):
            return term, "question-keyword-table"
    return None, "no-anatomy-term-in-question"


def _search_zfin(entities, question, budget_s=None, max_entities=None, max_statements=None):
    """Native zebrafish loss-of-function evidence (ZFIN via the Alliance of Genome Resources), the
    Path-B source the human-centric tools cannot provide. Symbol -> ZFIN curie -> observed mutant/
    knockdown phenotype STATEMENTS with backing PMIDs, taxon 7955, no API key.

    Returns (items, ledger):
      items  — evidence items (ONLY symbols that actually matched), same shape as the Europe PMC items
      ledger — one row PER SYMBOL ATTEMPTED with an explicit status. This is the diagnostic LOTE-03
               demanded: `no-match` ("searched, ZFIN has nothing on this anatomy") must never look like
               `error` ("the search itself failed") or like a symbol we never tried.

    Bounded by construction (§6 no-hang): a wall-clock budget stops the loop and the remaining symbols
    are recorded as `skipped-budget`. Statements per gene are capped and the truncation is DECLARED —
    a silent cut would render as "that is all ZFIN knows".
    """
    budget_s = ZFIN_BUDGET_S if budget_s is None else budget_s
    max_entities = ZFIN_MAX_ENTITIES if max_entities is None else max_entities
    max_statements = ZFIN_MAX_STATEMENTS if max_statements is None else max_statements

    symbols = [e.strip() for e in (entities or []) if e and e.strip()]
    query_zfin = _workspace_tool("zfin_zebrafish.py", "query_zfin")
    anatomy, anatomy_source = zfin_anatomy_filter(question)
    considered, over_cap = symbols[:max_entities], symbols[max_entities:]
    items, ledger = [], []

    if query_zfin is None:
        return [], [{"symbol": s, "status": "tool-unavailable",
                     "detail": f"{_TU_WORKSPACE / 'zfin_zebrafish.py'} not importable"}
                    for s in considered]
    if not symbols:
        return [], []

    t0 = time.monotonic()
    for sym in considered:
        if time.monotonic() - t0 > budget_s:
            ledger.append({"symbol": sym, "status": "skipped-budget",
                           "detail": f"ZFIN wall-clock budget {budget_s}s exhausted"})
            continue
        res = query_zfin(sym, anatomy=anatomy, limit=max_statements)
        if res.get("status") != "success":
            ledger.append({"symbol": sym, "status": "error", "detail": res.get("error", "")[:200]})
            continue
        d = res["data"]
        n_matched = d.get("n_matched") or 0
        row = {"symbol": sym, "status": "success" if n_matched else "no-match",
               "curie": d.get("zfin_curie"), "n_matched": n_matched,
               "n_phenotypes_total": d.get("n_phenotypes_total"),
               "anatomy_filter": anatomy}
        ledger.append(row)
        if not n_matched:
            continue
        phenos = d.get("phenotypes", [])[:max_statements]
        cached = _cache_zfin(sym, res)
        items.append({
            "source": "zfin",
            # a REAL external identifier, resolved live from the symbol (never minted) — this is what
            # the auditor's approved/rejected lists key on, so it must be unique and resolvable
            "evidence_id": d.get("zfin_curie") or f"ZFIN:unresolved:{sym}",
            "search_rec": {"pmid": None, "pmcid": None, "doi": None,
                           "title": (f"ZFIN phenotypes — {sym}"
                                     + (f" (anatomy: {anatomy})" if anatomy else " (all anatomies)")),
                           "year": None, "journal": "ZFIN via Alliance of Genome Resources",
                           "is_oa": True, "cited_by": None},
            "fetched": {"found": True, "full_text": False, "n_chunks": None,
                        "raw_cached": cached, "raw_ref": None},
            "zfin": {"symbol": sym, "curie": d.get("zfin_curie"), "taxon": d.get("taxon"),
                     "anatomy_filter": anatomy, "anatomy_filter_source": anatomy_source,
                     "n_phenotypes_total": d.get("n_phenotypes_total"), "n_matched": n_matched,
                     "n_returned": len(phenos), "truncated": n_matched > len(phenos),
                     "phenotypes": phenos,
                     # the PMIDs come straight from the authoritative API, not from a model; they are
                     # RETRIEVED with provenance, NOT verified-for-citation (CLAUDE.md §7 — verify_output
                     # still gates whatever the synthesizer chooses to cite)
                     "identifier_provenance": "alliance-genome-api-live"},
        })
    for sym in over_cap:
        ledger.append({"symbol": sym, "status": "skipped-cap",
                       "detail": f"more than max_entities={max_entities} symbols in the run"})
    return items, ledger


def _cache_zfin(symbol, res):
    """Persist the tool's DETERMINISTIC envelope under mcp_cache (§6 cache discipline). Named without
    the `raw_` prefix on purpose: it is one deterministic transform away from the Alliance response —
    the phenotype statements and PMIDs are verbatim, but it is not the untouched HTTP body, and this
    project does not let a near-raw artifact borrow the word `raw`."""
    try:
        CACHE.mkdir(exist_ok=True)
        date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
        slug = re.sub(r"[^a-z0-9]+", "-", symbol.lower()).strip("-") or "symbol"
        p = CACHE / f"zfin_{slug}_{date}.json"
        p.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        return [str(p.relative_to(ROOT))]
    except Exception:
        return []


def n_results_by_source(papers):
    """Per-source result counts for the bundle + the event payload (ADR-0057 made the total auditable;
    per-source is what distinguishes 'this source found nothing' from 'this source never ran'). ONE
    implementation, called from both Path-B trigger sites — a re-derived counter drifts."""
    counts = {}
    for p in papers or []:
        src = p.get("source") or "unknown"
        counts[src] = counts.get(src, 0) + 1
    counts.setdefault("europepmc", 0)
    return counts


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


def build_external_query(question, entities=None):
    """The query actually SENT to external literature (ADR-0057). Europe PMC is an ENGLISH biomedical
    index: sending the team's Spanish question verbatim returns ZERO results (verified live: ES→0,
    EN→3, entities→3 — production run 99986dbb). Deterministic rule: resolved entities (English gene
    symbols, the strongest signal) when present; the raw question otherwise. Callers RECORD what was
    sent — 'searched badly' must never look identical to 'nothing exists'."""
    ents = [e.strip() for e in (entities or []) if e and e.strip()]
    if ents:
        return " ".join(ents), "entities"
    return question, "question-verbatim"


PATH_B_SOURCES = ("europepmc", "zfin", "tooluniverse")


def path_b(question, n=2, full_text=True, sources=PATH_B_SOURCES, query=None, entities=None,
           ledger_out=None):
    """External fallback — MULTI-SOURCE, never a stopper. Each item records its `source`:
      europepmc   — literature (built-in, dependency-free)
      zfin        — NATIVE zebrafish loss-of-function phenotypes (tapón 1·A): a STRONGER evidence tier
                    than generic literature for a pronephros claim, and invisible to the human-centric
                    tools. Needs `entities` (gene symbols), not a free-text query.
      tooluniverse— the PACKAGE tools; still a documented hook until the SDK ships (tapón 1·B).
    `query` (ADR-0057): the search string actually sent to the external literature index; defaults to
    the raw question ONLY as last resort (see build_external_query — Spanish questions return zero).
    `ledger_out` (dict, optional): side channel for per-source search ledgers — the diagnostic that
    keeps "searched and found nothing" distinguishable from "the search failed".

    This function is the ONE seam the offline gates stub: everything that touches the network lives
    here, so a stubbed path_b is a genuinely offline run."""
    q_sent = query or question
    papers = []
    if "europepmc" in sources:
        for rec in fetch_paper.search_europepmc(q_sent, n=n):
            ident = f"PMID:{rec['pmid']}" if rec.get("pmid") else (rec.get("pmcid") or rec.get("doi"))
            got = fetch_paper.fetch_external(ident, want_full_text=full_text) if ident else {"found": False}
            papers.append({
                "source": "europepmc",
                "evidence_id": ident or "paper",
                "search_rec": {k: rec.get(k) for k in ("pmid", "pmcid", "doi", "title", "year", "journal", "is_oa", "cited_by")},
                "fetched": {k: got.get(k) for k in ("found", "full_text", "n_chunks", "raw_cached", "raw_ref")},
            })
    if "zfin" in sources:
        zfin_items, zfin_ledger = _search_zfin(entities, question)
        papers += zfin_items
        if ledger_out is not None:
            ledger_out["zfin_searched"] = zfin_ledger
    if "tooluniverse" in sources:
        papers += _search_tooluniverse(question, n)  # documented breadth hook (live when MCP/SDK present)
    return papers


def path_b_bundle(question, entities=None, n=2, query=None, query_source=None, triggered_by=None,
                  sources=PATH_B_SOURCES):
    """The `path_b` block of the bundle, built in ONE place. Both trigger sites (structural, inside
    retrieve(); confidence-gated, inside runs.execute_run) call this — a re-assembled block is how the
    per-source counters drift apart, and drifting counters are how a broken search looks like an empty
    world (LOTE-03·1)."""
    if query is None:
        query, query_source = build_external_query(question, entities)
    ledger = {}
    papers = path_b(question, n=n, query=query, entities=entities, sources=sources, ledger_out=ledger)
    block = {"triggered": True,
             "triggered_by": list(triggered_by or []),
             "papers": papers,
             # ADR-0057: what was ACTUALLY searched, auditable — a Path B that searched badly must
             # never look identical to a Path B that found nothing.
             "query_sent": query, "query_source": query_source,
             "n_results_by_source": n_results_by_source(papers),
             "sources_requested": list(sources),
             "tool_universe_directive": tool_universe_directive(question, n)}
    block.update(ledger)   # zfin_searched: the per-symbol status ledger, when the source ran
    return block


def path_b_event_payload(block, trigger=None):
    """The event payload for `stage.path_b` — the live trace and the replay read the SAME summary."""
    p = {"triggered": True, "n_papers": len(block.get("papers", [])),
         "query_sent": block.get("query_sent"), "query_source": block.get("query_source"),
         "n_results_by_source": block.get("n_results_by_source", {})}
    if trigger:
        p["trigger"] = trigger
    if "zfin_searched" in block:
        led = block["zfin_searched"]
        p["zfin_searched"] = led
        p["zfin_status_tally"] = {s: sum(1 for r in led if r.get("status") == s)
                                  for s in sorted({r.get("status") for r in led})}
    return p


def _state(name, may_answer, may_propose, required_next):
    """A node in the explicit decision-state machine (see module docstring)."""
    return {"state": name, "may_answer_now": may_answer, "may_propose_now": may_propose,
            "required_next_action": required_next}


def retrieve(question, entities=None, n_papers=2, on_stage=None):
    """The orchestrator: Path A, then Path B iff A is insufficient. Never a stopper. The returned bundle
    carries an explicit `decision_state` that GATES what may happen next — answering (on EITHER branch,
    ADR-0049) is blocked until an audit verdict is recorded (record_audit()).

    `on_stage(stage_name, payload)` (optional) is called after each stage — the event-emission hook the
    run model uses (ADR-0050) so the live trace and the replay read ONE state machine, not a re-built
    copy of it (the run_held_out.py re-assembly is exactly what left 31 historic runs without a
    decision_state). It may raise to abort (e.g. cancellation): the exception propagates."""
    def _stage(name, payload):
        if on_stage:
            on_stage(name, payload)

    a = path_a(question)
    _stage("path_a", {"n_hits": a["n_hits"], "retrieval": a["retrieval"]})
    ent = check_entities(entities)
    _stage("check_entities", {e: v["in_di"] for e, v in ent.items()})
    suf = assess_sufficiency(a, ent)
    _stage("assess_sufficiency", suf)
    bundle = {"question": question,
              "run_id": uuid.uuid4().hex,
              "stamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
              "question_slug": re.sub(r"[^a-z0-9]+", "-", question.lower())[:40].strip("-"),
              "entities_checked": ent, "path_a": a, "sufficiency": suf}
    if suf["sufficient"]:
        bundle["path_b"] = {"triggered": False, "reason": "DI sufficient (literature present + entities resolved)"}
        # ADR-0049 (founder, 2026-08-09): DI-sufficiency no longer authorizes a direct answer — the
        # composite audit runs on 100% of runs. This state is now INTERMEDIATE.
        bundle["decision_state"] = _state(
            "DI_SUFFICIENT", may_answer=False, may_propose=False,
            required_next="AUDIT — composite-auditor Mode 1 (>=3 adversarial) MUST verdict the DI-grounded "
                          "answer BEFORE it may be shown (ADR-0049: audit on 100% of runs, DI-sufficient "
                          "included). Feed the verdict to record_audit(); lib/composite_auditor.py is the "
                          "invokable panel.")
    else:
        bundle["path_b"] = path_b_bundle(question, entities=entities, n=n_papers,
                                         triggered_by=suf["reasons"])
        _stage("path_b", path_b_event_payload(bundle["path_b"], trigger="structural"))
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
    _stage("decision_state", bundle["decision_state"])
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

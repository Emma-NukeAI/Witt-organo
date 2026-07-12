"""
run_held_out.py — Test 3 (iteration loop) + Test 1 (reasoning) baseline runner (plan Track A / A1).

Runs the frozen held-out set (evaluation/held_out_set_v1.json, 30 Q) through a 3-STAGE pipeline per
question and writes claim-record-conforming outputs so compute_ece.py + noise_probe.py can measure the
baseline. This is the step that moves Test 3 from SCAFFOLD -> measured and produces the first REAL EPS.

    Stage 1 RETRIEVE  (deterministic, reuses answer_pipeline): DATA INAMOVIBLE Path A (rag_backend) +
                       resolve key entities (resolve_id). Optional Path B (Europe PMC) with --pathb.
    Stage 2 SYNTHESIZE (Anthropic Messages API via urllib — NO SDK dependency, repo stdlib idiom):
                       claude-opus-4-8 consumes the evidence bundle and emits the CLAUDE.md §5 output
                       contract as a forced tool call (direct_answer + confidence + evidence + ...).
    Stage 3 SCORE against INDEPENDENT ground truth (anti-circularity — plan Track A golden rule):
                       (a) DETERMINISTIC for identifier-bearing Q: verify_output.admissible() over the
                           answer's ENSDARG/bindings against the verified store -> positive/negative.
                       (b) JUDGE PANEL (multi-family: Opus + Fable + Sonnet, ADR-0031) for open Q vs the
                           question's expected_evidence + the §4 rubric; inter-reviewer disagreement logged
                           (Fable-5 rec #2). Disagreement/abstain -> unfalsifiable (excluded), not forced.

REUSE (never re-implemented): answer_pipeline (retrieve), rag_backend (query), resolve_id (resolve),
verify_output (admissible / verify_identifiers). Outputs conform to the claim-record schema consumed by
substrate_calibration/tools/compute_ece.py.

Layout written under evaluation/runs/<month>/ :
    <month>/Q<NN>.json         final scored claim record (primary backend, run 1) -> compute_ece reads THESE
    <month>/_raw/<backend>_run<r>_Q<NN>.json   every retrieve+synthesize+score raw output (paired runs)
    <month>/_panel/Q<NN>.json  judge-panel detail (per-judge verdicts + disagreement)
  (compute_ece's os.listdir is non-recursive, so the _raw/_panel subdirs are ignored by it.)

Spend: Stage 1 Path A embeds the query only under RAG_BACKEND=neo4j (OpenAI, authorized); RAG_BACKEND=sparse
is NO-SPEND. Stage 2/3 call the Anthropic API (authorized; best-tier models per the no-downgrade rule —
the Sonnet judge is for FAMILY DIVERSITY per ADR-0031, not a cost downgrade). Prerequisite: ANTHROPIC_API_KEY
in .secrets/deploy.env (added by the human; never in git).

CLI:
    # NO-SPEND offline smoke (no API key needed): stage-1 retrieval only, sparse backend, subset
    python evaluation/run_held_out.py run --backend sparse --no-synth --questions Q01,Q22,Q26

    # full baseline month_0 (needs ANTHROPIC_API_KEY; --runs 2 => paired runs for EPS)
    python evaluation/run_held_out.py run --month month_0 --backend neo4j --runs 2 --pathb
    python evaluation/run_held_out.py eps  --month month_0            # -> noise_probe real axes a/b
    # then: python substrate_calibration/tools/compute_ece.py --records-dir evaluation/runs/month_0 \
    #              --output reports/ece_month0_<YYYYMMDD>.json
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))

HELD_OUT = ROOT / "evaluation" / "held_out_set_v1.json"
RUNS = ROOT / "evaluation" / "runs"

# Identifier-bearing question types get a DETERMINISTIC store-grounded outcome (the falsifiable subset).
ID_TYPES = {"marker_identification", "ortholog_mapping", "specificity_ratio"}

# Multi-family judge panel (ADR-0031 reviewer independence): three DISTINCT families for diversity of
# failure modes, NOT a cost downgrade of the deliverable (the ANSWER is synthesized by Opus 4.8 below).
# Fable-5 was the intended 3rd family but CONSISTENTLY REFUSES the forced-tool judging call
# (stop_reason=refusal, empty input, 3/3 — both forced and auto tool_choice, 2026-07-11), so Haiku 4.5
# takes the 3rd slot. Haiku's role here is INDEPENDENT REVIEW, not primary reasoning — consistent with the
# no-downgrade rule (which governs the substantive answer, not judge-panel family diversity).
JUDGE_MODELS = ["claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5-20251001"]
SYNTH_MODEL = "claude-opus-4-8"

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


# --------------------------------------------------------------------------- helpers
def _today():
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_secrets():
    """Load .secrets/deploy.env into os.environ (same pattern as answer_pipeline) — never in git."""
    env = ROOT / ".secrets" / "deploy.env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _reconfigure_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows cp1252 guard
    except Exception:
        pass


# --------------------------------------------------------------------------- Anthropic (urllib, no SDK)
def anthropic_tool_call(model, system, user_text, tool, max_tokens=2000, timeout=120, retries=1):
    """Call the Messages API forcing `tool`; return (tool_input: dict, usage: dict).

    No SDK dependency (repo stdlib idiom, cf. .tooluniverse lenses). Bounded wait + one retry; raises on
    a hard failure so the caller records the question as PENDING rather than fabricating an answer."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set — add it to .secrets/deploy.env (never to git).")
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user_text}],
        "tools": [tool],
        "tool_choice": {"type": "tool", "name": tool["name"]},
    }
    data = json.dumps(body).encode("utf-8")
    headers = {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION,
               "content-type": "application/json"}
    required = tool.get("input_schema", {}).get("required", [])
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(ANTHROPIC_URL, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            last = RuntimeError(f"HTTP {e.code}: {detail}")
            if e.code in (429, 500, 502, 503, 529) and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise last
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = RuntimeError(f"network error: {e}")
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise last
        # extract the forced tool call; retry once if it is missing or omits required fields (some model
        # families under-populate tool inputs — the API does NOT enforce `required`).
        tool_input = next((b["input"] for b in payload.get("content", [])
                           if b.get("type") == "tool_use" and b.get("name") == tool["name"]), None)
        if tool_input is None:
            last = RuntimeError(f"no forced tool_use (stop_reason={payload.get('stop_reason')})")
            if attempt < retries:
                time.sleep(1)
                continue
            raise last
        missing = [k for k in required if tool_input.get(k) is None]
        if missing and attempt < retries:
            last = RuntimeError(f"tool_use omitted required fields {missing}")
            time.sleep(1)
            continue
        return tool_input, payload.get("usage", {})
    raise last  # pragma: no cover


# --------------------------------------------------------------------------- tool schemas (§5 contract, verdict)
CONTRACT_TOOL = {
    "name": "emit_contract",
    "description": ("Emit the substrate output contract (CLAUDE.md §5). Answer the biology question using "
                    "ONLY the provided evidence bundle; if the bundle is thin, say so in gap_flags and keep "
                    "confidence honest. NEVER invent gene IDs — put every gene symbol you assert together "
                    "with its ENSDARG (if you state one) in identifier_bindings so it can be checked against "
                    "the verified store."),
    "input_schema": {
        "type": "object",
        "properties": {
            "direct_answer": {"type": "string", "description": "The answer to the question."},
            "confidence": {"type": "number",
                           "description": ("MANDATORY. Your calibrated probability that direct_answer is "
                                           "correct, a number in [0,1]. ALWAYS provide it, even when you are "
                                           "unsure or cannot answer — use a LOW value (e.g. 0.1) rather than "
                                           "omitting the field. Never leave this out.")},
            "evidence_cited": {"type": "array", "items": {"type": "string"},
                               "description": "Bundle doc_ids / PMIDs / accessions actually used."},
            "identifier_bindings": {
                "type": "array",
                "items": {"type": "object",
                          "properties": {"symbol": {"type": "string"}, "ensdarg": {"type": "string"}},
                          "required": ["symbol"]},
                "description": "Every gene symbol asserted, paired with its ENSDARG if stated (else omit ensdarg)."},
            "alternatives_considered": {"type": "array", "items": {"type": "string"}},
            "gap_flags": {"type": "array", "items": {"type": "string"}},
            "framework_applied": {"type": "string",
                                  "description": "Reasoning framework + why (per reasoning-frameworks-catalog)."},
            "search_query": {"type": "string",
                             "description": ("A focused KEYWORD query (gene symbols + biology terms, e.g. "
                                             "'zebrafish pronephros osr1 wnt2ba intermediate mesoderm') for an "
                                             "external literature/database search to run IF your confidence is "
                                             "low. Keywords only — omit tool/format words like 'Morpheus' or "
                                             "'BioNetGen'. Always provide it when confidence < 0.6.")},
        },
        "required": ["direct_answer", "confidence", "evidence_cited", "identifier_bindings",
                     "alternatives_considered", "gap_flags", "framework_applied", "search_query"],
    },
}

VERDICT_TOOL = {
    "name": "emit_verdict",
    "description": ("Score the candidate answer against the question's expected_evidence and the §4 rubric. "
                    "Be adversarial: reward correctness and honest uncertainty, penalize overclaiming and "
                    "fabricated specifics. If you cannot tell, use 'abstain' — do not guess."),
    "input_schema": {
        "type": "object",
        "properties": {
            "rubric": {
                "type": "object",
                "description": "Each axis in [0,1].",
                "properties": {
                    "factuality": {"type": "number"}, "citation_correctness": {"type": "number"},
                    "completeness": {"type": "number"}, "testability": {"type": "number"},
                    "uncertainty_calibration": {"type": "number"}, "safety_ethics": {"type": "number"},
                },
            },
            "overall_score": {"type": "number",
                              "description": "MANDATORY. Overall answer quality in [0,1]. Always provide it."},
            "verdict": {"type": "string", "enum": ["correct", "partial", "incorrect", "abstain"],
                        "description": ("MANDATORY. One of: correct / partial / incorrect / abstain. ALWAYS "
                                        "provide it — use 'abstain' only if you truly cannot judge, never omit.")},
            "justification": {"type": "string", "description": "MANDATORY. One-paragraph rationale."},
        },
        "required": ["overall_score", "verdict", "justification"],
    },
}


# --------------------------------------------------------------------------- stage 1: retrieve
def extract_entities(question):
    """Gene symbols PRESENT IN THE QUESTION that resolve in the verified store (no fabrication, no leakage
    from expected_evidence). Used only for the sufficiency signal, not for scoring."""
    from lib import resolve_id
    seen, out = set(), []
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9]{1,9}", question):
        t = tok.lower()
        if t in seen:
            continue
        seen.add(t)
        if resolve_id.resolve(t) is not resolve_id.NOT_FOUND:
            out.append(t)
    return out


_TU = None


def get_tu():
    """Lazy singleton of the Tool Universe SDK (Layer 3, CLAUDE.md §6). Loads the 2223-tool registry once
    (~seconds) and reuses it across questions. This is the SAME pinned package the project standardizes on
    via .mcp.json (tooluniverse@1.2.6) — the reproducible, script-native form of the Path-B MCP fallback."""
    global _TU
    if _TU is None:
        import warnings
        warnings.filterwarnings("ignore")
        from tooluniverse import ToolUniverse
        _TU = ToolUniverse()
        _TU.load_tools()
    return _TU


def tu_literature(query, n=3):
    """Path B via Tool Universe: literature search (EuropePMC_search_articles) with abstracts. `query` is a
    focused KEYWORD string (the model's search_query, else the question). Returns normalized paper dicts.
    Never a stopper — on any error returns []. (Level 1 fallback: literature. Richer multi-tool TU use —
    ensembl/zfin/reactome/string via find_tools — is the Level 2 follow-up.)"""
    try:
        tu = get_tu()
        res = tu.run({"name": "EuropePMC_search_articles", "arguments": {"query": query, "limit": n}})
        data = (res if isinstance(res, dict) else json.loads(res)).get("data", []) or []
    except Exception as e:
        return {"error": str(e), "papers": []}
    papers = [{
        "source": "tooluniverse:EuropePMC_search_articles",
        "search_rec": {k: p.get(k) for k in ("pmid", "pmcid", "doi", "title", "year", "journal", "citations")},
        "abstract": (p.get("abstract") or "")[:1200],
        "open_access": p.get("open_access"),
    } for p in data]
    return {"papers": papers}


def stage_retrieve(question):
    """Path A only (DATA INAMOVIBLE). Reuses answer_pipeline. Path B is added later, only when a fallback
    trigger fires (structural OR confidence), by add_path_b()."""
    from lib import answer_pipeline as ap
    ents = extract_entities(question)
    a = ap.path_a(question)
    ent = ap.check_entities(ents)
    suf = ap.assess_sufficiency(a, ent)
    return {"question": question, "entities_checked": ent, "path_a": a, "sufficiency": suf,
            "path_b": {"triggered": False, "reason": "not yet evaluated"}}


_Q_STOP = {"reconstruct", "suitable", "network", "using", "would", "which", "about", "between", "across",
           "described", "given", "there", "these", "their", "should", "could", "assemble", "evidence",
           "additional", "layers", "identify", "distinguish", "propose", "summarize", "compute", "predict"}
_Q_TOOLING = {"morpheus", "bionetgen", "bngl", "runpod", "squidiff", "alphafold", "csv", "json", "xml",
              "vtk", "vtu", "cgns", "tiff", "mat", "ome", "pdb", "sdf", "mol"}


def _fallback_query(q_dict, bundle):
    """Deterministic keyword query for Path B when the model's search_query is missing or too long — biology
    terms only (system + resolved entities + salient question tokens), stripping tool/format words that make
    a literature search return nothing (the Q07 failure mode)."""
    sys_ = q_dict.get("system", "")
    sys_ = "" if sys_ in ("any", "") else sys_
    ents = list(bundle.get("entities_checked", {}).keys())[:5]
    toks = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z\-]{4,}", q_dict.get("q", ""))]
    toks = [w for w in toks if w not in _Q_STOP and w not in _Q_TOOLING]
    toks = list(dict.fromkeys(toks))[:6]
    parts = ["zebrafish", sys_] + ents + toks
    return " ".join(p for p in parts if p).strip()


def add_path_b(bundle, question, source, trigger, detail, query=None):
    """Mutate `bundle` with Path B evidence from `source` (europepmc | tooluniverse). `query` is the focused
    keyword search string (the model's search_query); falls back to the raw question. `trigger`/`detail`
    record WHY the fallback fired (structural insufficiency, or low synthesized confidence)."""
    from lib import answer_pipeline as ap
    q = (query or "").strip() or question
    try:
        r = tu_literature(q, n=3) if source == "tooluniverse" else {"papers": ap.path_b(q, n=2)}
        bundle["path_b"] = {"triggered": True, "source": source, "trigger": trigger, "detail": detail,
                            "query": q, **r}
    except Exception as e:
        bundle["path_b"] = {"triggered": True, "source": source, "trigger": trigger, "detail": detail,
                            "query": q, "error": str(e), "papers": []}
    return bundle


# --------------------------------------------------------------------------- stage 2: synthesize
def bundle_to_prompt(q, bundle):
    hits = bundle["path_a"].get("hits", [])
    lines = [f"- [{h['doc_id']} · {h['type']} · score={h['score']}] {h['text']}" for h in hits] or ["(none)"]
    ent = "; ".join(f"{k}={'in-DI' if v['in_di'] else 'ABSENT'}" for k, v in bundle["entities_checked"].items()) or "(none checked)"
    pb = bundle.get("path_b", {})
    papers = pb.get("papers", [])
    plines = []
    for p in papers:
        sr = p.get("search_rec", {})
        ab = (p.get("abstract") or "").strip()
        plines.append(f"- [{p.get('source')}] PMID:{sr.get('pmid')} · {sr.get('title')} ({sr.get('year')})"
                      + (f"\n    {ab}" if ab else ""))
    ptxt = "\n".join(plines) if plines else (
        f"(Path B triggered but no papers: {pb.get('error')})" if pb.get("triggered")
        else "(Path B not triggered — DI-only or DI sufficient)")
    return (f"QUESTION:\n{q['q']}\n\n"
            f"(type={q['type']}, niche={q.get('niche')}, system={q.get('system')})\n\n"
            f"DATA INAMOVIBLE retrieval (Path A):\n" + "\n".join(lines) + "\n\n"
            f"Key entities resolved in DI: {ent}\n\n"
            f"External literature (Path B):\n{ptxt}\n\n"
            "Answer using ONLY this evidence. Be honest about gaps; keep confidence calibrated.")


SYNTH_SYSTEM = ("You are a zebrafish developmental-biology research assistant operating under the Witt "
                "substrate output contract. Ground every claim in the provided evidence bundle. Never assert "
                "a gene ENSDARG from memory. Expose confidence, evidence, alternatives, and gaps honestly. "
                "You MUST always populate every field of emit_contract — especially a numeric `confidence` "
                "in [0,1] (use a low value when unsure; never omit it).")


_LEAKED_CONF_RE = re.compile(r'name="confidence"\s*>\s*([0-9]*\.?[0-9]+)')


def _recover_leaked_confidence(contract):
    """Some tool-call responses leak trailing parameters as TEXT into direct_answer (e.g.
    '...</parameter>\\n<parameter name="confidence">0.15'), leaving the structured confidence=None.
    Recover the value + strip the leaked tail. Forward fix for the run_held_out parser bug the closing
    composite-audit caught (2026-07-11): 8/30 month_0 records lost their confidence this way, dropping 2 of
    3 real negatives from the ECE aggregate and inflating the headline accuracy."""
    da = contract.get("direct_answer") or ""
    if contract.get("confidence") is None:
        m = _LEAKED_CONF_RE.search(da)
        if m:
            try:
                contract["confidence"] = float(m.group(1))
                contract["_confidence_recovered"] = True
            except ValueError:
                pass
    cut = da.find("</parameter>")
    if cut != -1:
        contract["direct_answer"] = da[:cut].rstrip()
    return contract


def stage_synthesize(q, bundle):
    prompt = bundle_to_prompt(q, bundle)
    # retries=2 (3 attempts): `confidence` omission is intermittent across questions; extra attempts
    # maximize the fraction of records that carry a stated_confidence (required by compute_ece).
    contract, usage = anthropic_tool_call(SYNTH_MODEL, SYNTH_SYSTEM, prompt, CONTRACT_TOOL, retries=2)
    contract = _recover_leaked_confidence(contract)   # salvage confidence leaked as text into direct_answer
    contract["_usage"] = usage
    contract["_model"] = SYNTH_MODEL
    return contract


# --------------------------------------------------------------------------- stage 3: scoring
def score_deterministic(contract, qtype, reingest_cache=None):
    """Store-grounded outcome for identifier-bearing questions (INDEPENDENT ground truth).
    positive = every ENSDARG resolves (or is a re-ingest candidate) and bindings are consistent;
    negative = a fabricated/misbound id. `reingest_cache` (ADR-0036): §7.9 raw cache path(s) produced by a
    live fetch this question — an out-of-store id present there is a re-ingest CANDIDATE (surfaced, not a
    fabrication fail), so the Q08 case (real Ensembl ids not yet in the store) is no longer a false negative.
    Returns dict or None when the question isn't identifier-type or the answer carries no identifiers."""
    from lib import verify_output
    rep = verify_output.verify_identifiers(contract, reingest_cache=reingest_cache)
    has_ids = bool(rep.verified_raw or rep.verified_derived or rep.unresolved
                   or rep.reingest_candidates or rep.misbound)
    if qtype not in ID_TYPES or not has_ids:
        return None
    adm, reasons = verify_output.admissible(contract, reingest_cache=reingest_cache)
    return {"admissible": adm, "outcome": "positive" if adm else "negative",
            "report": rep.as_dict(), "reasons": reasons,
            "reingest_candidates": sorted(rep.reingest_candidates)}


def judge_answer(q, contract):
    """Multi-family panel (ADR-0031). Each family scores independently vs expected_evidence + §4 rubric.
    Returns per-judge verdicts + a disagreement metric + a majority outcome. Judges are independent of the
    answering model family for the non-Opus members (reviewer-independence signal, Fable-5 rec #2)."""
    system = ("You are an adversarial expert reviewer scoring an AI answer to a zebrafish-biology question "
              "against the expected evidence and a rubric. Independence matters: judge only what is shown. "
              "You MUST call emit_verdict with ALL required fields populated: a numeric overall_score in "
              "[0,1], a verdict (correct/partial/incorrect/abstain), and a justification. Never omit a field.")
    user = (f"QUESTION:\n{q['q']}\n\nEXPECTED EVIDENCE (what a good answer contains):\n{q.get('expected_evidence','')}\n\n"
            f"CANDIDATE ANSWER:\n{contract.get('direct_answer','')}\n\n"
            f"Candidate's stated confidence: {contract.get('confidence')}\n"
            f"Candidate's cited evidence: {contract.get('evidence_cited')}\n"
            f"Candidate's gap_flags: {contract.get('gap_flags')}\n\n"
            "Score against the rubric and give an overall verdict.")
    verdicts = []
    for model in JUDGE_MODELS:
        try:
            v, usage = anthropic_tool_call(model, system, user, VERDICT_TOOL, max_tokens=1200)
            verdicts.append({"model": model, **v, "usage": usage})
        except Exception as e:
            verdicts.append({"model": model, "verdict": "error", "error": str(e)})
    scored = [v for v in verdicts if v.get("verdict") in ("correct", "partial", "incorrect", "abstain")]
    labels = [v["verdict"] for v in scored]
    overalls = [float(v["overall_score"]) for v in scored if isinstance(v.get("overall_score"), (int, float))]
    # disagreement = 1 - (max label share); + spread of overall scores
    if labels:
        share = max(labels.count(x) for x in set(labels)) / len(labels)
        disagreement = round(1.0 - share, 3)
    else:
        disagreement = None
    spread = round(max(overalls) - min(overalls), 3) if len(overalls) >= 2 else None
    mean_overall = round(sum(overalls) / len(overalls), 3) if overalls else None
    abstain_frac = (labels.count("abstain") / len(labels)) if labels else 1.0
    # OUTCOME (LLM-as-judge quality threshold on the panel MEAN, with independence guards):
    #   - high inter-judge disagreement (>=0.5) or abstain-dominated (>=0.5) -> unfalsifiable (excluded)
    #   - else mean quality >=0.6 -> positive ; <=0.4 -> negative ; the 0.4-0.6 band -> unfalsifiable (borderline)
    # This is the falsifiable calibration target for OPEN questions (the ID subset uses the deterministic
    # store outcome instead). Borderline/contested answers are honestly excluded, not forced to a label.
    if not labels or disagreement is None or disagreement >= 0.5 or abstain_frac >= 0.5 or mean_overall is None:
        outcome = "unfalsifiable_in_phase_I"
    elif mean_overall >= 0.60:
        outcome = "positive"
    elif mean_overall <= 0.40:
        outcome = "negative"
    else:
        outcome = "unfalsifiable_in_phase_I"
    return {"models": JUDGE_MODELS, "verdicts": verdicts, "label_disagreement": disagreement,
            "overall_spread": spread, "outcome": outcome, "mean_overall": mean_overall,
            "outcome_rule": "mean_overall>=0.6 positive / <=0.4 negative / else unfalsifiable; guarded by disagreement<0.5 & abstain<0.5"}


# --------------------------------------------------------------------------- record assembly
def make_record(q, backend, contract, deterministic, panel, month="month_0", fb_meta=None):
    primary = deterministic["outcome"] if deterministic else (panel["outcome"] if panel else None)
    method = "deterministic-store" if deterministic and not panel else \
             "both" if deterministic and panel else \
             "judge-panel" if panel else "unscored"
    niche = q.get("niche", ["unspecified"])
    return {
        "claim_id": f"held_out_{month}_{q['id']}",
        "claim_timestamp": _now_iso(),
        "session_id": f"evaluation/runs/{month} (run_held_out.py A1 baseline)",
        "skill_origin": "held-out-runner",
        "skill_version": "run_held_out-1.1",
        "fallback": fb_meta or {"fired": False},
        "stream": "biomedical",
        "sub_domain": niche[0] if isinstance(niche, list) and niche else "unspecified",
        "claim_category": q["type"],
        "question_id": q["id"],
        "question": q["q"],
        "backend": backend,
        "direct_answer": contract.get("direct_answer") if contract else None,
        "stated_confidence": float(contract["confidence"]) if contract and contract.get("confidence") is not None else None,
        "prior": float(contract["confidence"]) if contract and contract.get("confidence") is not None else None,
        "evidence_cited": contract.get("evidence_cited", []) if contract else [],
        "identifier_bindings": contract.get("identifier_bindings", []) if contract else [],
        "alternatives_considered": contract.get("alternatives_considered", []) if contract else [],
        "gap_flags": contract.get("gap_flags", []) if contract else [],
        "framework_applied": contract.get("framework_applied") if contract else None,
        "observed_outcome": primary,
        "observed_at": _now_iso() if primary else None,
        "scoring": {"method": method, "deterministic": deterministic, "panel": panel},
        "test_mapping": ["test_1", "test_3", "test_4"],
        "agents_invoked": [
            {"agent": "held-out-runner", "status": "invoked", "evidence_generated": ["test_1", "test_3"]},
            {"agent": "verify_output.admissible", "status": "invoked" if deterministic else "not-applicable",
             "reason": "deterministic identifier grounding" if deterministic else "no identifiers to gate"},
            {"agent": "judge-panel (multi-family, ADR-0031)", "status": "invoked" if panel else "skipped-ad-hoc",
             "reason": "reviewer-independence scoring" if panel else "deterministic outcome sufficed / synth skipped"},
            {"agent": "tooluniverse (Path B fallback, MCP/SDK)",
             "status": "invoked" if (fb_meta and fb_meta.get("fired") and fb_meta.get("source") == "tooluniverse") else "not-applicable",
             "reason": (f"confidence-gated fallback: {fb_meta.get('detail')}" if (fb_meta and fb_meta.get("fired"))
                        else "DI sufficient / fallback disabled")},
        ],
    }


# --------------------------------------------------------------------------- orchestration
def load_questions(subset=None):
    data = json.loads(HELD_OUT.read_text(encoding="utf-8"))["questions"]
    if subset:
        want = {s.strip() for s in subset.split(",")}
        data = [q for q in data if q["id"] in want]
    return data


def run(args):
    _load_secrets()
    os.environ["RAG_BACKEND"] = args.backend  # sparse = NO-SPEND offline; neo4j = live hosted store
    if args.backend == "neo4j":
        # The hosted vector index is 1536-dim (OpenAI text-embedding-3-small). The QUERY must be embedded
        # with the SAME model or the dim mismatch makes Neo4jGraphRetriever throw — which HybridRetriever
        # silently swallows into sparse-only (the Track B silent-degradation trap). Force OpenAI here.
        os.environ["EMBED_MODEL"] = "openai"
    month_dir = RUNS / args.month
    raw_dir, panel_dir = month_dir / "_raw", month_dir / "_panel"
    for d in (month_dir, raw_dir, panel_dir):
        d.mkdir(parents=True, exist_ok=True)
    questions = load_questions(args.questions)
    print(f"[run_held_out] {len(questions)} Q · backend={args.backend} · runs={args.runs} · synth="
          f"{'off' if args.no_synth else 'on'} · fallback={args.fallback} (trigger={args.fallback_trigger}, "
          f"tau={args.conf_threshold})")

    def _num(x):
        return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None

    for q in questions:
        for r in range(1, args.runs + 1):
            bundle = stage_retrieve(q["q"])              # Path A only
            contract, deterministic, panel, fb_meta = None, None, None, {"fired": False}
            if not args.no_synth:
                try:
                    contract = stage_synthesize(q, bundle)                 # PASS 1 — DI-only
                    conf1 = _num(contract.get("confidence"))
                    # FALLBACK TRIGGER (answers "who determines insufficiency?"):
                    #   confidence = the model's own pass-1 confidence < tau (the real "is my store enough?" signal;
                    #                the structural check is fooled by any-chunk-present — see Q07);
                    #   structural  = the pre-synth heuristic (kept for comparison).
                    #   Automatic, never human-gated: fetching is cheap+reversible (no-hang rule). The HUMAN GATE
                    #   lives at re-ingest of fetched evidence into the DI, not at the fetch decision.
                    fire, trigger, detail = False, None, None
                    if args.fallback != "none":
                        if args.fallback_trigger == "confidence":
                            if conf1 is not None and conf1 < args.conf_threshold:
                                fire, trigger, detail = True, "confidence", f"pass1_confidence={conf1} < tau={args.conf_threshold}"
                        elif not bundle["sufficiency"]["sufficient"]:
                            fire, trigger, detail = True, "structural", bundle["sufficiency"]["reasons"]
                    if fire:
                        sq = (contract.get("search_query") or "").strip()
                        if not sq or len(sq.split()) > 12:          # missing or a copied-question, not keywords
                            sq = _fallback_query(q, bundle)
                        add_path_b(bundle, q["q"], args.fallback, trigger, detail, query=sq)
                        contract2 = stage_synthesize(q, bundle)            # PASS 2 — DI + Path B
                        conf2 = _num(contract2.get("confidence"))
                        fb_meta = {"fired": True, "trigger": trigger, "source": args.fallback, "detail": detail,
                                   "pass1_confidence": conf1, "pass2_confidence": conf2,
                                   "n_path_b_papers": len(bundle["path_b"].get("papers", []))}
                        contract = contract2                                # final answer = pass 2
                    else:
                        fb_meta = {"fired": False, "pass1_confidence": conf1,
                                   "reason": "confidence>=tau" if args.fallback != "none" else "fallback disabled"}
                    deterministic = score_deterministic(contract, q["type"])
                    if not args.no_judge and r == 1:
                        panel = judge_answer(q, contract)
                except Exception as e:
                    contract = {"_error": str(e), "direct_answer": None, "confidence": None,
                                "evidence_cited": [], "identifier_bindings": []}
                    print(f"  ! {q['id']} run{r}: synth/score PENDING ({e})")
            raw = {"question_id": q["id"], "run": r, "backend": args.backend, "type": q["type"],
                   "bundle": bundle, "contract": contract, "deterministic": deterministic,
                   "panel": panel, "fallback": fb_meta}
            (raw_dir / f"{args.backend}_run{r}_{q['id']}.json").write_text(
                json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
            if r == 1:                                    # compute_ece reads month_dir top level only
                rec = make_record(q, args.backend, contract, deterministic, panel, month=args.month, fb_meta=fb_meta)
                (month_dir / f"{q['id']}.json").write_text(
                    json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
                if panel:
                    (panel_dir / f"{q['id']}.json").write_text(
                        json.dumps(panel, ensure_ascii=False, indent=2), encoding="utf-8")
            oc = (deterministic or panel or {}).get("outcome") if (deterministic or panel) else "unscored"
            fbtag = f" fb={fb_meta['pass1_confidence']}->{fb_meta.get('pass2_confidence')}" if fb_meta.get("fired") else ""
            print(f"  {q['id']} run{r}: hits={bundle['path_a']['n_hits']} suf={bundle['sufficiency']['sufficient']} "
                  f"conf={contract.get('confidence') if contract else '-'} outcome={oc}{fbtag}")
    print(f"[run_held_out] wrote records -> {month_dir}")


def _load_bge_embedder():
    """Local bge embedder (NO-SPEND) for the SEMANTIC axis c. Mirrors rag_backend's import pattern
    (rag_index/graphrag/embeddings.get_embedder). EMBED_MODEL is forced to bge so it never spends on
    OpenAI. Returns embed(list[str])->list[vec] or None if fastembed/model is unavailable."""
    os.environ["EMBED_MODEL"] = "bge"
    try:
        sys.path.insert(0, str(ROOT / "rag_index" / "graphrag"))
        from embeddings import get_embedder
        return get_embedder()
    except Exception as e:
        print(f"[eps] bge embedder unavailable ({e}); axis c falls back to the lexical proxy")
        return None


def run_eps(args):
    """Build paired_runs from _raw/run1 vs _raw/run2 and feed noise_probe (real axes a/b, + axis c)."""
    sys.path.insert(0, str(ROOT / "substrate_calibration" / "tools"))
    import noise_probe
    embedder = _load_bge_embedder() if args.axis_c == "bge" else None
    raw_dir = RUNS / args.month / "_raw"
    pairs = []
    for f1 in sorted(raw_dir.glob(f"{args.backend}_run1_*.json")):
        qid = f1.stem.split("_")[-1]
        f2 = raw_dir / f"{args.backend}_run2_{qid}.json"
        if not f2.exists():
            continue
        a, b = json.loads(f1.read_text(encoding="utf-8")), json.loads(f2.read_text(encoding="utf-8"))
        ra = [h["doc_id"] for h in a["bundle"]["path_a"].get("hits", [])]
        rb = [h["doc_id"] for h in b["bundle"]["path_a"].get("hits", [])]
        ca = (a.get("contract") or {}).get("evidence_cited", []) or []
        cb = (b.get("contract") or {}).get("evidence_cited", []) or []
        ha = (a.get("contract") or {}).get("direct_answer", "") or ""
        hb = (b.get("contract") or {}).get("direct_answer", "") or ""
        pairs.append({"retrieval_a": ra, "retrieval_b": rb, "citations_a": ca, "citations_b": cb,
                      "hyp_a": ha, "hyp_b": hb})
    if not pairs:
        print(f"[eps] no paired runs found in {raw_dir} (need --runs 2). Nothing to do.")
        return
    res = noise_probe.probe(pairs, month_tag=args.month, config_hash=f"held-out-{args.backend}",
                            embedder=embedder)
    out = RUNS / args.month / f"eps_{args.backend}.json"
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _reconfigure_stdout()
    print(json.dumps(res["axes"], indent=2))
    print(f"[eps] wrote {out} (n_pairs={res['n_pairs']}) — REAL axes a/b (replaces synthetic self-test)")


def main():
    _reconfigure_stdout()
    ap = argparse.ArgumentParser(description="Test 3/Test 1 held-out baseline runner (plan A1).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run retrieve->synthesize->score over the held-out set")
    r.add_argument("--month", default="month_0")
    r.add_argument("--backend", default="sparse", choices=["sparse", "neo4j"])
    r.add_argument("--runs", type=int, default=1, help="paired runs (2 for EPS)")
    r.add_argument("--questions", default="", help="comma-separated subset, e.g. Q01,Q22")
    r.add_argument("--fallback", default="none", choices=["none", "europepmc", "tooluniverse"],
                   help="Path B when DI insufficient: none (DI-only) | europepmc (urllib) | tooluniverse (SDK)")
    r.add_argument("--fallback-trigger", default="confidence", choices=["confidence", "structural"],
                   help="what decides insufficiency: confidence (pass-1 conf < tau, recommended) | structural")
    r.add_argument("--conf-threshold", type=float, default=0.5,
                   help="tau: pass-1 confidence below this triggers the Path B fallback (default 0.5)")
    r.add_argument("--no-synth", action="store_true", help="stage 1 only (NO-SPEND, no API key)")
    r.add_argument("--no-judge", action="store_true", help="skip the judge panel (deterministic scoring only)")
    r.set_defaults(func=run)

    e = sub.add_parser("eps", help="compute real EPS axes a/b (+ semantic axis c) from paired runs")
    e.add_argument("--month", default="month_0")
    e.add_argument("--backend", default="sparse", choices=["sparse", "neo4j"])
    e.add_argument("--axis-c", default="bge", choices=["bge", "lexical"],
                   help="bge = local semantic embedder (NO-SPEND); lexical = TF-IDF proxy")
    e.set_defaults(func=run_eps)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

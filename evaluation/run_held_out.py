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
        },
        "required": ["direct_answer", "confidence", "evidence_cited", "identifier_bindings",
                     "alternatives_considered", "gap_flags", "framework_applied"],
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


def stage_retrieve(question, use_pathb):
    """Reuse answer_pipeline. Path A always; Path B only if requested (network)."""
    from lib import answer_pipeline as ap
    ents = extract_entities(question)
    a = ap.path_a(question)
    ent = ap.check_entities(ents)
    suf = ap.assess_sufficiency(a, ent)
    bundle = {"question": question, "entities_checked": ent, "path_a": a, "sufficiency": suf}
    if use_pathb and not suf["sufficient"]:
        try:
            bundle["path_b"] = {"triggered": True, "papers": ap.path_b(question, n=2)}
        except Exception as e:
            bundle["path_b"] = {"triggered": True, "error": str(e), "papers": []}
    else:
        bundle["path_b"] = {"triggered": False}
    return bundle


# --------------------------------------------------------------------------- stage 2: synthesize
def bundle_to_prompt(q, bundle):
    hits = bundle["path_a"].get("hits", [])
    lines = [f"- [{h['doc_id']} · {h['type']} · score={h['score']}] {h['text']}" for h in hits] or ["(none)"]
    ent = "; ".join(f"{k}={'in-DI' if v['in_di'] else 'ABSENT'}" for k, v in bundle["entities_checked"].items()) or "(none checked)"
    papers = bundle.get("path_b", {}).get("papers", [])
    plines = []
    for p in papers:
        sr = p.get("search_rec", {})
        plines.append(f"- [{p.get('source')}] PMID:{sr.get('pmid')} {sr.get('title')} ({sr.get('year')})")
    ptxt = "\n".join(plines) if plines else "(Path B not triggered / no papers)"
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


def stage_synthesize(q, bundle):
    prompt = bundle_to_prompt(q, bundle)
    # retries=2 (3 attempts): `confidence` omission is intermittent across questions; extra attempts
    # maximize the fraction of records that carry a stated_confidence (required by compute_ece).
    contract, usage = anthropic_tool_call(SYNTH_MODEL, SYNTH_SYSTEM, prompt, CONTRACT_TOOL, retries=2)
    contract["_usage"] = usage
    contract["_model"] = SYNTH_MODEL
    return contract


# --------------------------------------------------------------------------- stage 3: scoring
def score_deterministic(contract, qtype):
    """Store-grounded outcome for identifier-bearing questions (INDEPENDENT ground truth).
    positive = every ENSDARG resolves and bindings are consistent; negative = a fabricated/misbound id.
    Returns dict or None when the question isn't identifier-type or the answer carries no identifiers."""
    from lib import verify_output
    rep = verify_output.verify_identifiers(contract)
    has_ids = bool(rep.verified_raw or rep.verified_derived or rep.unresolved or rep.misbound)
    if qtype not in ID_TYPES or not has_ids:
        return None
    adm, reasons = verify_output.admissible(contract)
    return {"admissible": adm, "outcome": "positive" if adm else "negative",
            "report": rep.as_dict(), "reasons": reasons}


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
def make_record(q, backend, contract, deterministic, panel):
    primary = deterministic["outcome"] if deterministic else (panel["outcome"] if panel else None)
    method = "deterministic-store" if deterministic and not panel else \
             "both" if deterministic and panel else \
             "judge-panel" if panel else "unscored"
    niche = q.get("niche", ["unspecified"])
    return {
        "claim_id": f"held_out_month0_{q['id']}",
        "claim_timestamp": _now_iso(),
        "session_id": "evaluation/runs/month_0 (run_held_out.py A1 baseline)",
        "skill_origin": "held-out-runner",
        "skill_version": "run_held_out-1.0",
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
    print(f"[run_held_out] {len(questions)} Q · backend={args.backend} · runs={args.runs} · "
          f"synth={'off' if args.no_synth else 'on'} · pathb={'on' if args.pathb else 'off'}")

    for q in questions:
        for r in range(1, args.runs + 1):
            bundle = stage_retrieve(q["q"], use_pathb=args.pathb)
            contract, deterministic, panel = None, None, None
            if not args.no_synth:
                try:
                    contract = stage_synthesize(q, bundle)
                    deterministic = score_deterministic(contract, q["type"])
                    # judge panel only on run 1 (the scored record); run 2 exists only for the EPS pair,
                    # which needs the synthesized hypothesis + retrieval, not a second panel — halves judge spend.
                    if not args.no_judge and r == 1:
                        panel = judge_answer(q, contract)
                except Exception as e:
                    contract = {"_error": str(e), "direct_answer": None, "confidence": None,
                                "evidence_cited": [], "identifier_bindings": []}
                    print(f"  ! {q['id']} run{r}: synth/score PENDING ({e})")
            raw = {"question_id": q["id"], "run": r, "backend": args.backend, "type": q["type"],
                   "bundle": bundle, "contract": contract, "deterministic": deterministic, "panel": panel}
            (raw_dir / f"{args.backend}_run{r}_{q['id']}.json").write_text(
                json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
            # primary record + panel detail written only from run 1 (compute_ece reads month_dir top level)
            if r == 1:
                rec = make_record(q, args.backend, contract, deterministic, panel)
                (month_dir / f"{q['id']}.json").write_text(
                    json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
                if panel:
                    (panel_dir / f"{q['id']}.json").write_text(
                        json.dumps(panel, ensure_ascii=False, indent=2), encoding="utf-8")
            oc = (deterministic or panel or {}).get("outcome") if (deterministic or panel) else "unscored"
            print(f"  {q['id']} run{r}: hits={bundle['path_a']['n_hits']} suf={bundle['sufficiency']['sufficient']} "
                  f"conf={contract.get('confidence') if contract else '-'} outcome={oc}")
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
    r.add_argument("--pathb", action="store_true", help="enable Path B (Europe PMC; network)")
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

"""
composite_auditor.py — the INVOKABLE composite auditor (tapón 3 / ADR-0049; block 3 of the webapp plan).

Until now `composite-auditor` was a ROLE agents played in-session (CLAUDE.md §7); the audit gate was
closed by a prose string (`required_next_action`) an agent had to read and obey, `record_audit()` had
zero callers, and the `audit` key was missing from 100% of producible runs. This module makes it a
COMPONENT with typed input/output — the founder decision of 2026-08-09 (audit on 100% of runs) is only
promisable if something actually audits.

Panel (ADR-0047 decision 4): claude-opus-4-8 + claude-sonnet-5 + claude-haiku-4-5-20251001 (Anthropic,
three DISTINCT adversarial lenses) + gpt-4o (OpenAI — real cross-provider independence, ADR-0038).
Fable-5 is EXCLUDED (refuses forced tool-calls; founder: "no creo que sea un modelo que podamos meter
por el momento").

Discipline inherited from the audited eval harness (ADR-0037/0038):
  - judges are HANDED the deterministic check results (verify_output / resolve_id) and FORBIDDEN to
    claim verification they did not run (the judge-fabrication fix);
  - an errored/unparseable judge is EXCLUDED and recorded as errored — never fabricated;
  - fewer than `min_valid` (default 3 — composite-auditor Mode 1 minimum) valid verdicts can NEVER
    approve: the overall verdict degrades to REVISE with `panel_incomplete: true` (conservative).

Vocabulary (ADR-0049): new runs speak `APPROVE | APPROVE_MINOR | REVISE`; every audit object carries
`source_vocabulary` so historic artifacts (record_audit approved/rejected · judge_answer 5-way ·
S-bank CONFIRMED/REVISE/REFUTED) keep their original vocabulary and are never force-mapped.
Aggregation is worst-of-N across valid reviewers (house rule — cf. retrieval_summary): a panel where
anyone caught something real must not average away the catch.

LLM calls are stdlib urllib (Anthropic) / openai SDK (OpenAI) — the exact pattern battle-tested in
evaluation/run_held_out.py. The caller is INJECTABLE so gates run offline and deterministic.
"""
import json
import os
import time
import urllib.error
import urllib.request

VOCABULARY = ("APPROVE", "APPROVE_MINOR", "REVISE")
SOURCE_VOCABULARY = "APPROVE|APPROVE_MINOR|REVISE"
_SEVERITY = {"APPROVE": 0, "APPROVE_MINOR": 1, "REVISE": 2}

DEFAULT_PANEL = [
    {"reviewer": "claude-opus-4-8", "family": "anthropic", "lens": "correctness"},
    {"reviewer": "claude-sonnet-5", "family": "anthropic", "lens": "overclaim"},
    {"reviewer": "claude-haiku-4-5-20251001", "family": "anthropic", "lens": "evidence-grounding"},
    {"reviewer": os.environ.get("OPENAI_JUDGE_MODEL", "gpt-4o"), "family": "openai", "lens": "reproducibility"},
]

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

VERDICT_TOOL = {
    "name": "emit_audit_verdict",
    "description": ("Emit your adversarial audit verdict for the claim under your assigned lens. "
                    "APPROVE = no material issue found; APPROVE_MINOR = real but minor issues, state them; "
                    "REVISE = a material problem the answer must fix before it may be shown. "
                    "Report ONLY what you actually found in the provided material; you are handed the "
                    "deterministic verification results — do NOT claim any verification you did not run."),
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": list(VOCABULARY)},
            "caught": {"type": "string", "description": "the most important issue found ('' if none)"},
            "correction_applied": {"type": "string",
                                   "description": "the concrete correction the answer needs ('' if none)"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "reasons": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["verdict", "confidence"],
    },
}

_LENS_CHARGES = {
    "correctness": ("Try to REFUTE the claim: hunt for factual errors, wrong causal direction, or "
                    "conclusions the cited evidence does not support. Default toward REVISE when uncertain."),
    "overclaim": ("Hunt for OVER-CLAIMING: confidence not warranted by the evidence tier, 'validated' where "
                  "only 'measured' holds, hypothesis presented as finding, missing gap_flags. This project's "
                  "history shows over-claiming is its most recurrent failure."),
    "evidence-grounding": ("Check GROUNDING: does every asserted identifier/citation trace to the provided "
                           "evidence and the deterministic check results? Flag anything asserted from memory. "
                           "An identifier the deterministic gate marked unresolved is an automatic REVISE."),
    "reproducibility": ("As a cross-provider reviewer, check the reasoning chain END-TO-END: could an "
                        "independent reader reproduce the conclusion from the evidence shown? Flag leaps, "
                        "missing steps, and reliance on unstated knowledge."),
}


def _anthropic_tool_call(model, system, user_text, tool=None, timeout=120, retries=1, max_tokens=1200):
    """Forced-tool Messages call (urllib; the run_held_out.py pattern). Returns (tool_input, usage).
    `tool` defaults to VERDICT_TOOL; the run synthesizer reuses this with its own schema (ADR-0050)."""
    tool = tool or VERDICT_TOOL
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set — add to .secrets/deploy.env / service env (never git).")
    body = {"model": model, "max_tokens": max_tokens, "system": system,
            "messages": [{"role": "user", "content": user_text}],
            "tools": [tool], "tool_choice": {"type": "tool", "name": tool["name"]}}
    headers = {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(ANTHROPIC_URL, data=json.dumps(body).encode("utf-8"),
                                         headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}")
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
        tool_input = next((b["input"] for b in payload.get("content", [])
                           if b.get("type") == "tool_use" and b.get("name") == tool["name"]), None)
        bad_verdict = (tool["name"] == VERDICT_TOOL["name"]
                       and (tool_input or {}).get("verdict") not in VOCABULARY)
        if tool_input is None or bad_verdict:
            last = RuntimeError(f"no valid forced tool_use (stop_reason={payload.get('stop_reason')})")
            if attempt < retries:
                time.sleep(1)
                continue
            raise last
        # The API does NOT enforce `required` (run_held_out lesson) — the FIRST real production run
        # (a361f566, 2026-08-10) came back with confidence omitted and it slipped through as a silent
        # null. Retry once on missing required fields; on the final attempt return what we got (the
        # caller flags the absence explicitly — a null must never masquerade as a measurement).
        required = tool.get("input_schema", {}).get("required", [])
        missing = [k for k in required if tool_input.get(k) is None]
        if missing and attempt < retries:
            last = RuntimeError(f"tool_use omitted required fields {missing}")
            time.sleep(1)
            continue
        return tool_input, payload.get("usage", {})
    raise last  # pragma: no cover


def _openai_tool_call(model, system, user_text, timeout=120):
    """Cross-provider judge (openai SDK, function-calling forced; same schema). Returns (verdict, usage)."""
    from openai import OpenAI
    client = OpenAI()
    fn = {"type": "function", "function": {"name": VERDICT_TOOL["name"],
                                           "description": VERDICT_TOOL["description"],
                                           "parameters": VERDICT_TOOL["input_schema"]}}
    resp = client.chat.completions.create(
        model=model, max_tokens=1200, timeout=timeout,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user_text}],
        tools=[fn], tool_choice={"type": "function", "function": {"name": VERDICT_TOOL["name"]}})
    msg = resp.choices[0].message
    if not msg.tool_calls:
        raise RuntimeError(f"openai: no tool_call (finish_reason={resp.choices[0].finish_reason})")
    out = json.loads(msg.tool_calls[0].function.arguments)
    if out.get("verdict") not in VOCABULARY:
        raise RuntimeError(f"openai: invalid verdict {out.get('verdict')!r}")
    return out, (resp.usage.model_dump() if resp.usage else {})


def _default_caller(member, system, user_text):
    if member["family"] == "openai":
        return _openai_tool_call(member["reviewer"], system, user_text)
    return _anthropic_tool_call(member["reviewer"], system, user_text)


def audit(claim, evidence, deterministic_checks=None, required_because="", panel=None,
          caller=None, min_valid=3):
    """Run the Mode 1 split-and-vote panel over (claim, evidence). Returns the audit object the §5
    contract and the frozen record carry VISIBLY:

        {required, required_because, panel: [{reviewer, family, lens, verdict, caught,
         correction_applied, confidence} | {reviewer, family, lens, status: 'errored', error}],
         tally, verdict, source_vocabulary, panel_incomplete?, usage}

    `deterministic_checks` (dict) is verify_output/resolve_id output — handed to every judge so nobody
    invents verification (ADR-0038). `caller(member, system, user_text) -> (verdict_dict, usage)` is
    injectable for offline gates; default = live Anthropic/OpenAI calls.
    """
    panel = panel or DEFAULT_PANEL
    caller = caller or _default_caller
    user_text = json.dumps({
        "claim": claim,
        "evidence": evidence,
        "deterministic_checks": deterministic_checks or {"note": "none provided"},
    }, ensure_ascii=False, indent=2, default=str)

    rows, usage_total = [], {}
    for member in panel:
        system = (f"You are one reviewer on an adversarial composite-audit panel (zebrafish pronephros "
                  f"research substrate). Your assigned lens: {member['lens']}. {_LENS_CHARGES[member['lens']]} "
                  f"You are handed deterministic verification results in the input — cite them; NEVER claim "
                  f"a verification you did not run. Vote independently; other reviewers cover other lenses.")
        try:
            verdict, usage = caller(member, system, user_text)
            rows.append({"reviewer": member["reviewer"], "family": member["family"], "lens": member["lens"],
                         "verdict": verdict["verdict"], "caught": verdict.get("caught", ""),
                         "correction_applied": verdict.get("correction_applied", ""),
                         "confidence": verdict.get("confidence"),
                         "reasons": verdict.get("reasons", []),
                         "usage": usage or {}})   # per-reviewer usage -> TokenUsage.by_model (ADR-0051)
            for k, v in (usage or {}).items():
                if isinstance(v, (int, float)):
                    usage_total[k] = usage_total.get(k, 0) + v
        except Exception as e:  # errored judge: EXCLUDED and recorded — never fabricated (ADR-0038)
            rows.append({"reviewer": member["reviewer"], "family": member["family"], "lens": member["lens"],
                         "status": "errored", "error": f"{type(e).__name__}: {str(e)[:200]}"})

    valid = [r for r in rows if "verdict" in r]
    tally = {v: sum(1 for r in valid if r["verdict"] == v) for v in VOCABULARY}
    out = {"required": True, "required_because": required_because, "panel": rows, "tally": tally,
           "source_vocabulary": SOURCE_VOCABULARY, "n_valid": len(valid), "usage": usage_total}
    if len(valid) < min_valid:
        # a thin panel can NEVER approve — conservative by construction (Mode 1 minimum >=3)
        out["verdict"] = "REVISE"
        out["panel_incomplete"] = True
    else:
        out["verdict"] = max((r["verdict"] for r in valid), key=_SEVERITY.__getitem__)
    return out


def apply_to_bundle(bundle, audit_result, evidence_ids, answer_pipeline_module=None):
    """Feed the panel verdict to answer_pipeline.record_audit — its FIRST real caller — and enrich the
    bundle's `audit` key with the full panel table (visible, not just approved/rejected lists). The
    bundle identity is re-stamped after the enrichment (ADR-0044)."""
    if answer_pipeline_module is None:
        from lib import answer_pipeline as answer_pipeline_module
    approved_overall = audit_result["verdict"] in ("APPROVE", "APPROVE_MINOR")
    # v1 granularity: the panel audits the claim+evidence as a whole; per-item verdicts are a refinement
    # (noted in ADR-0049). APPROVE/APPROVE_MINOR admits the evidence set; REVISE rejects it.
    approved = list(evidence_ids) if approved_overall else []
    rejected = [] if approved_overall else list(evidence_ids)
    bundle = answer_pipeline_module.record_audit(
        bundle, approved, rejected,
        note=f"composite-auditor Mode 1: {audit_result['verdict']} "
             f"(valid {audit_result['n_valid']}/{len(audit_result['panel'])}, {SOURCE_VOCABULARY})")
    bundle["audit"].update({k: audit_result[k] for k in
                            ("required", "required_because", "panel", "tally", "verdict",
                             "source_vocabulary", "n_valid", "usage")})
    if audit_result.get("panel_incomplete"):
        bundle["audit"]["panel_incomplete"] = True
    bundle["bundle_identity"] = answer_pipeline_module._identity(bundle)
    return bundle

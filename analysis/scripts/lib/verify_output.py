"""
verify_output.py — Deterministic anti-fabrication verification gate (GWT v1.1 §6.4).

This is a Logic-LM-class (symbolic, NOT an LLM) check: every external identifier that appears
in an agent output must resolve through the verified-identifier store, OR be flagged. It is the
operational enforcement of CLAUDE.md §7 ("external identifiers never from memory") + §7.9
(raw-cache discipline). It is the structural fix for the documented ENSDARG error rate and for
the wt1a fabricated-expression row (a wrong ID that collided with an unrelated gene).

It does NOT replace `composite-auditor` (which judges reasoning/verdict validity). They compose:
this gate first (cheap, deterministic, blocks fabrication early); the auditor second.

v1 scope (NO-SPEND, offline): ENSDARG genes resolve against the local store; PMIDs and
GEO/SRA/PXD accessions cannot be verified offline (no literature store yet) so they are
honestly FLAGGED (surfaced to gap_flags), never silently passed. UniProt regex is intentionally
omitted in v1 (too false-positive-prone against gene symbols); add when the store carries
uniprot_acc values.
"""
import json
import re
from dataclasses import dataclass, field
from typing import List

from . import resolve_id

ENSDARG_RE = re.compile(r"ENSDARG\d{11}")
PMID_RE = re.compile(r"\bPMID:?\s?(\d{4,9})\b")
GEO_RE = re.compile(r"\b(?:GSE|GSM|SRR|SRP|SRX|PRJNA|PXD|MSV)\d+\b")


@dataclass
class VerificationReport:
    ok: bool = True
    verified_raw: List[str] = field(default_factory=list)        # resolved + raw §7.9 cache on disk
    verified_derived: List[str] = field(default_factory=list)    # resolved but DERIVED tier only
    not_found_positive: List[str] = field(default_factory=list)  # store says "looked, absent"
    unresolved: List[str] = field(default_factory=list)          # in output, not in store => FAILURE
    flagged_external: List[str] = field(default_factory=list)    # PMID/GEO — can't verify offline (gap_flag)

    def as_dict(self):
        return {
            "ok": self.ok,
            "identifier_admissible": self.identifier_admissible,
            "verified_raw": sorted(self.verified_raw),
            "verified_derived": sorted(self.verified_derived),
            "not_found_positive": sorted(self.not_found_positive),
            "unresolved": sorted(self.unresolved),
            "flagged_external": sorted(self.flagged_external),
        }

    @property
    def identifier_admissible(self) -> bool:
        """The IDENTIFIER hard-predicate component of H(c): True iff no ENSDARG in the output is unresolved.
        This is PARTIAL by design — the only full composite admissibility gate is the module-level
        admissible() (R2 / ADR-0024), which ANDs this with any additional hard invariants. Named distinctly
        from admissible() so a caller never mistakes the identifier component for the full H(c)."""
        return self.ok


def verify_identifiers(text_or_obj, store=None) -> VerificationReport:
    """Extract external identifiers from a string or JSON-serializable object and gate them.

    GATE FAILURE (report.ok == False) iff any ENSDARG in the output does not resolve in the store.
    PMIDs/GEO accessions are flagged (honest gap), not failures, in v1.
    """
    sot = store or resolve_id._get_default()
    text = text_or_obj if isinstance(text_or_obj, str) else json.dumps(text_or_obj)
    report = VerificationReport()

    for ens in sorted(set(ENSDARG_RE.findall(text))):
        rec = sot.resolve(ens)
        if rec is resolve_id.NOT_FOUND:
            report.unresolved.append(ens)
            report.ok = False
        elif rec.is_raw_verified:
            report.verified_raw.append(ens)
        else:
            report.verified_derived.append(ens)

    for pmid in sorted(set(PMID_RE.findall(text))):
        report.flagged_external.append(f"PMID:{pmid}")
    for acc in sorted(set(GEO_RE.findall(text))):
        report.flagged_external.append(acc)

    return report


# --- R2 (ADR-0024): Bayes-purity tier weights + the explicit admissibility predicate ----------
# Bayes-purity invariant: only verifier-confirmed records may carry label-weight in calibration —
# ledger purity = s*p / (s*p + f*(1-p)) contracts to 1 ONLY on the deterministic subclass where the
# false-accept rate f -> 0 (RAW tier). DERIVED is resolved-but-raw-response-not-retained (partial
# weight); NOT_FOUND / unknown carry zero label-weight. compute_ece consumes weights from here.
# RAW=1.0 and NOT_FOUND=0.0 are the rigorous endpoints (ledger purity -> 1 only as the false-accept rate
# f -> 0). DERIVED=0.7 is a PROVISIONAL placeholder (resolved, but the raw §7.9 response was not retained)
# — NOT a derived value; it MUST be calibrated from an estimated DERIVED-tier f before compute_ece ever
# down-weights real records by it (gap_flag). UNVERIFIED is listed for parity with the corpus_manifest
# verification_tier enum; any unrecognized tier falls to 0.0 via the .get default.
TIER_WEIGHT = {"RAW": 1.0, "DERIVED": 0.7, "NOT_FOUND": 0.0, "UNVERIFIED": 0.0}


def tier_weight(tier):
    """Calibration label-weight for a verification-tier string (RAW=1.0 / DERIVED=0.7 provisional / else 0.0)."""
    return TIER_WEIGHT.get(tier, 0.0)


def tier_weight_for_record(rec):
    """Label-weight for a resolve_id result; DELEGATES to tier_weight() via the canonical tier string so the
    record path and the string path cannot diverge. RAW (raw §7.9 cache on disk) -> 'RAW'; resolved-not-raw
    -> 'DERIVED'; NOT_FOUND/None -> 'NOT_FOUND'."""
    if rec is resolve_id.NOT_FOUND or rec is None:
        return tier_weight("NOT_FOUND")
    return tier_weight("RAW" if getattr(rec, "is_raw_verified", False) else "DERIVED")


def admissible(text_or_obj, store=None, extra_predicates=None):
    """Hard admissibility predicate H(c) in {0,1} (R2 / ADR-0024).

    H is a CONJUNCTION of hard invariants, and is EXTENSIBLE by design (the additive principle): adding a
    new hard rule = adding one predicate, no rewrite. v1 base invariant: every external ENSDARG in the
    output resolves in the store (verify_identifiers().ok). A claim with H(c)=0 is INADMISSIBLE — and the
    theorem this makes explicit is that no soft score can rescue it: admissibility is computed from hard
    predicates ONLY, never from a confidence/quality value, so a graded score g(Q(c)) can never flip H
    from 0 to 1. (Soft scoring is defined only on the admissible set H^{-1}(1).)

    extra_predicates: optional list of callables (text_or_obj, report) -> (name: str, ok: bool) to AND in.
        CONTRACT: each callable MUST be a deterministic HARD invariant; by design it receives NO confidence
        and MUST NOT derive one from text_or_obj — that is what structurally keeps soft scores out of H
        (the theorem). When the hard-predicate set grows beyond the base, prefer a registry of named
        predicates over free-form callables so the conjunction stays auditable.
    Returns (admissible: bool, reasons: list[str]).
    """
    report = verify_identifiers(text_or_obj, store=store)
    reasons = []
    if not report.ok:
        reasons.append(f"unresolved external identifiers (hard fail): {sorted(report.unresolved)}")
    for pred in (extra_predicates or []):
        name, ok = pred(text_or_obj, report)
        if not ok:
            reasons.append(f"hard predicate failed: {name}")
    return (len(reasons) == 0), reasons


def info_priority_order(candidates, store=None):
    """v1 PLACEHOLDER ordering over candidates (NOT a calibrated EVPI — see ADR-0024 'honest limits').

    Full EVPI = E_theta[max_a U(a,theta)] - max_a E_theta[U(a,theta)] needs a decision-utility model the
    substrate does not yet formalize (DEFERRED). This is a transparent proxy for 'which admissible
    candidate to resolve next': surface the entities whose resolution would most reduce uncertainty first
    — operationalized as NOT_FOUND-but-needed entities (highest info to resolve) before already-verified
    ones, then by descending stated prior. Each item is returned tagged with its proxy reason and a
    `placeholder: True` flag so it is NEVER mistaken for a calibrated value-of-information.

    candidates: list of dicts, each at least {"symbol": str, "prior"?: float}.
    """
    sot = store or resolve_id._get_default()
    scored = []
    for c in candidates:
        rec = sot.resolve(c.get("symbol", ""))
        not_found = rec is resolve_id.NOT_FOUND
        # proxy info-gain: resolving an unknown is high-info; re-confirming a known is low-info. The prior
        # is assumed a probability and clamped to [0,1] so the 0.001 tie-break never crosses the NOT_FOUND partition.
        prior = max(0.0, min(1.0, float(c.get("prior", 0.0))))
        proxy = (1.0 if not_found else 0.0) + 0.001 * prior
        scored.append({**c, "_proxy_info": proxy, "not_found": not_found,
                       "reason": "NOT_FOUND -> high info to resolve" if not_found else "already verified -> low info",
                       "placeholder": True})
    return sorted(scored, key=lambda x: x["_proxy_info"], reverse=True)


if __name__ == "__main__":
    # Smoke test (NO-SPEND): the wt1a fabrication must FAIL; the correct ID must pass.
    bad = "wt1a is ENSDARG00000054611 (the value the buggy 01_schoels used)"
    good = "wt1a is ENSDARG00000031420 per the verified store; see PMID:37844491 and GSE162031"
    for label, txt in (("BAD", bad), ("GOOD", good)):
        rep = verify_identifiers(txt)
        adm, reasons = admissible(txt)
        print(label, "ok=", rep.ok, "admissible=", adm, reasons or "")
    # R2 (ADR-0024): tier weights (Bayes-purity) — only RAW carries full calibration label-weight.
    print("tier_weight RAW/DERIVED/NOT_FOUND =", tier_weight("RAW"), tier_weight("DERIVED"), tier_weight("NOT_FOUND"))
    # info_priority_order PLACEHOLDER: a NOT_FOUND (clcnkb) outranks a verified symbol (wt1a) for resolution.
    print("info_priority_order =",
          [(c["symbol"], c["reason"]) for c in info_priority_order(
              [{"symbol": "clcnkb", "prior": 0.8}, {"symbol": "wt1a", "prior": 0.9}])])

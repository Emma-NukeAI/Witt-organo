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

# N2 (ADR-0027 close): the extractor is TOLERANT — case-insensitive, optional separator, optional version
# suffix — so a reformatted id ('Ensdarg00000054611', 'ENSDARG_00000054611', 'ENSDARG00000054611.1') is
# still extracted, then CANONICALIZED to 'ENSDARG<11 digits>' before resolving. Without this, a fabricated
# id evaded the gate simply by lowercasing it or inserting a separator.
ENSDARG_RE = re.compile(r"ENSDARG[\s_\-]?\d{11}(?:\.\d+)?", re.I)          # tolerant matcher (binding fullmatch)
_ENSDARG_EXTRACT = re.compile(r"ENSDARG[\s_\-]?(\d{11})(?:\.\d+)?", re.I)  # captures the 11 digits
PMID_RE = re.compile(r"\bPMID:?\s?(\d{4,9})\b")
GEO_RE = re.compile(r"\b(?:GSE|GSM|SRR|SRP|SRX|PRJNA|PXD|MSV)\d+\b")


def _canonical_ensdarg(s):
    """Canonical 'ENSDARG<11 digits>' for any case/separator/version variant, else None (not an ENSDARG)."""
    m = _ENSDARG_EXTRACT.fullmatch(str(s).strip())
    return ("ENSDARG" + m.group(1)) if m else None


@dataclass
class VerificationReport:
    ok: bool = True
    verified_raw: List[str] = field(default_factory=list)        # resolved + raw §7.9 cache on disk
    verified_derived: List[str] = field(default_factory=list)    # resolved but DERIVED tier only
    not_found_positive: List[str] = field(default_factory=list)  # store says "looked, absent"
    unresolved: List[str] = field(default_factory=list)          # in output, not in store => FAILURE
    flagged_external: List[str] = field(default_factory=list)    # PMID/GEO — can't verify offline (gap_flag)
    misbound: List[str] = field(default_factory=list)            # symbol<->ENSDARG pair that contradicts the store (N1)

    def as_dict(self):
        return {
            "ok": self.ok,
            "identifier_admissible": self.identifier_admissible,
            "verified_raw": sorted(self.verified_raw),
            "verified_derived": sorted(self.verified_derived),
            "not_found_positive": sorted(self.not_found_positive),
            "unresolved": sorted(self.unresolved),
            "flagged_external": sorted(self.flagged_external),
            "misbound": sorted(self.misbound),
        }

    @property
    def identifier_admissible(self) -> bool:
        """The IDENTIFIER hard-predicate component of H(c): True iff no ENSDARG in the output is unresolved.
        This is PARTIAL by design — the only full composite admissibility gate is the module-level
        admissible() (R2 / ADR-0024), which ANDs this with any additional hard invariants. Named distinctly
        from admissible() so a caller never mistakes the identifier component for the full H(c)."""
        return self.ok


# N1 (ADR-0027): keys under which an output may carry an EXPLICIT symbol<->ENSDARG pairing.
# The binding check is HARD only on STRUCTURED pairs (a dict carrying both a symbol-key and an
# ensdarg-key). Free-text "<symbol> is <ENSDARG>" pairing is NOT inferred (it would over-fire on
# any text that mentions a gene and, separately, an accession) — that remains an honest gap_flag.
# Symbol/ENSDARG pairing keys. Includes `marker`/`ens_id` — the ACTUAL field names emitted by
# 01_schoels_analysis.py (the script N1 cites as the corruption it fixes); the closing composite-audit
# (ADR-0027) found the original allowlist MISSED that real output shape. The allowlist is inherently a
# subset (gap_flag); the reverse-binding check below is key-agnostic in spirit (any recognized pair whose
# ENSDARG belongs to a different stored symbol is caught even when the paired symbol is NOT_FOUND).
_SYMBOL_KEYS = ("symbol", "gene", "gene_symbol", "marker")
_ENSDARG_KEYS = ("ensdarg", "ensembl_gene_id", "gene_id", "ens_id")


def _walk_bindings(obj):
    """Yield (symbol, ensdarg) from any nested dict that carries BOTH a symbol-key and an ensdarg-key.
    Only well-formed ENSDARG values are yielded (so a gene_id holding a non-ENSDARG is ignored)."""
    if isinstance(obj, dict):
        sym = next((obj[k] for k in _SYMBOL_KEYS if isinstance(obj.get(k), str)), None)
        ens_raw = next((obj[k] for k in _ENSDARG_KEYS if isinstance(obj.get(k), str)), None)
        ens = _canonical_ensdarg(ens_raw) if ens_raw else None    # N2: normalize case/separator/version
        if sym and ens:
            yield str(sym).strip(), ens
        for v in obj.values():
            yield from _walk_bindings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_bindings(v)


def verify_bindings(obj, store=None) -> List[str]:
    """N1: validate EXPLICIT symbol<->ENSDARG pairs against the store. Returns a list of mis-binding
    descriptions (empty = all consistent). A pair is MIS-BOUND when EITHER direction contradicts the store:
      - FORWARD: the store resolves the symbol to a DIFFERENT ENSDARG than the one paired with it.
      - REVERSE: the paired ENSDARG belongs in the store to a DIFFERENT symbol (catches the case where the
        paired symbol is NOT_FOUND but the ENSDARG is a real id of an unrelated gene — the 'collided with an
        unrelated gene' corruption, failure_log line 1, which a forward-only check misses).
    """
    sot = store or resolve_id._get_default()
    out = []
    for sym, ens in _walk_bindings(obj):
        rec = sot.resolve(sym)
        if rec is not resolve_id.NOT_FOUND and rec.ensdarg and rec.ensdarg != ens:
            out.append(f"{sym} paired with {ens} but store binds {sym}->{rec.ensdarg}")
        rec_e = sot.resolve(ens)
        if rec_e is not resolve_id.NOT_FOUND and rec_e.symbol and rec_e.symbol.lower() != sym.lower():
            out.append(f"{ens} paired with '{sym}' but store binds that id to '{rec_e.symbol}'")
    return sorted(set(out))


def verify_identifiers(text_or_obj, store=None) -> VerificationReport:
    """Extract external identifiers from a string or JSON-serializable object and gate them.

    GATE FAILURE (report.ok == False) iff any ENSDARG in the output does not resolve in the store,
    OR any EXPLICIT structured symbol<->ENSDARG pair contradicts the store binding (N1 / ADR-0027).
    PMIDs/GEO accessions are flagged (honest gap), not failures, in v1.
    """
    sot = store or resolve_id._get_default()
    text = text_or_obj if isinstance(text_or_obj, str) else json.dumps(text_or_obj)
    report = VerificationReport()

    for digits in sorted(set(_ENSDARG_EXTRACT.findall(text))):
        ens = "ENSDARG" + digits   # N2: canonical form (case/separator/version normalized) before resolving
        rec = sot.resolve(ens)
        if rec is resolve_id.NOT_FOUND:
            report.unresolved.append(ens)
            report.ok = False
        elif rec.is_raw_verified:
            report.verified_raw.append(ens)
        else:
            report.verified_derived.append(ens)

    # N1: hard binding check over EXPLICIT structured pairs (never inferred from free text).
    if not isinstance(text_or_obj, str):
        report.misbound = verify_bindings(text_or_obj, store=sot)
        if report.misbound:
            report.ok = False

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
    if report.unresolved:
        reasons.append(f"unresolved external identifiers (hard fail): {sorted(report.unresolved)}")
    if report.misbound:
        reasons.append(f"mis-bound symbol<->ENSDARG pairs (hard fail, N1): {sorted(report.misbound)}")
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
    # N1 (ADR-0027): a STRUCTURED mis-binding (pax2a paired with wt1a's verified ENSDARG) must FAIL,
    # while the correct structured pair passes. Free-text pairing is intentionally NOT inferred.
    misbound = {"identifier_bindings": [{"symbol": "pax2a", "ensdarg": "ENSDARG00000031420"}]}  # wt1a's id
    correct = {"identifier_bindings": [{"symbol": "wt1a", "ensdarg": "ENSDARG00000031420"}]}
    # ADR-0027 close: the REAL 01_schoels output shape uses {marker, ens_id}; and a NOT_FOUND symbol
    # bound to a real-but-other-gene id must be caught by the REVERSE check.
    real_shape = {"canonical_rows": [{"marker": "pax2a", "ens_id": "ENSDARG00000031420"}]}  # wt1a's id
    notfound_sym = {"markers": [{"symbol": "osr1", "ensdarg": "ENSDARG00000031420"}]}        # osr1 NOT_FOUND
    for label, obj in (("N1 MISBOUND {symbol,ensdarg}", misbound), ("N1 OK", correct),
                       ("N1 MISBOUND {marker,ens_id} (real 01_schoels shape)", real_shape),
                       ("N1 REVERSE (NOT_FOUND symbol -> other gene id)", notfound_sym)):
        adm, reasons = admissible(obj)
        print(label, "admissible=", adm, reasons or "")
    # N2 (ADR-0027 close): a reformatted fabricated id (lowercase / separator / version) must NOT evade.
    for label, txt in (("N2 lowercase", "wt1a is Ensdarg00000054611"),
                       ("N2 separator", "wt1a is ENSDARG_00000054611"),
                       ("N2 versioned", "wt1a is ENSDARG00000054611.1")):
        adm, reasons = admissible(txt)
        print(label, "admissible=", adm, "(expect False — caught after canonicalization)")
    # R2 (ADR-0024): tier weights (Bayes-purity) — only RAW carries full calibration label-weight.
    print("tier_weight RAW/DERIVED/NOT_FOUND =", tier_weight("RAW"), tier_weight("DERIVED"), tier_weight("NOT_FOUND"))
    # info_priority_order PLACEHOLDER: a NOT_FOUND (clcnkb) outranks a verified symbol (wt1a) for resolution.
    print("info_priority_order =",
          [(c["symbol"], c["reason"]) for c in info_priority_order(
              [{"symbol": "clcnkb", "prior": 0.8}, {"symbol": "wt1a", "prior": 0.9}])])

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
            "verified_raw": sorted(self.verified_raw),
            "verified_derived": sorted(self.verified_derived),
            "not_found_positive": sorted(self.not_found_positive),
            "unresolved": sorted(self.unresolved),
            "flagged_external": sorted(self.flagged_external),
        }


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


if __name__ == "__main__":
    # Smoke test (NO-SPEND): the wt1a fabrication must FAIL; the correct ID must pass.
    bad = "wt1a is ENSDARG00000054611 (the value the buggy 01_schoels used)"
    good = "wt1a is ENSDARG00000031420 per the verified store; see PMID:37844491 and GSE162031"
    for label, txt in (("BAD", bad), ("GOOD", good)):
        rep = verify_identifiers(txt)
        print(label, "ok=", rep.ok, rep.as_dict())

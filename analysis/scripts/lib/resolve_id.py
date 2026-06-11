"""
resolve_id.py — Read-only resolver for the verified-identifier store (DATA INAMOVIBLE v1).

NO-SPEND, file-read only, ZERO network calls. This is the stable source-of-truth interface
(GWT v1.1 §6.2). The implementation behind it is a flat versioned JSON today; it may later
become a RAG / graph backend (FAISS / Neo4j / graphify — architecture still open, see plan §A)
WITHOUT changing callers, because the interface is the load-bearing contract:

    resolve(key)        -> VerifiedRecord | NOT_FOUND   (symbol | ENSDARG | UniProt accession)
    require(key)        -> VerifiedRecord                (raises ResolveError on NOT_FOUND)
    lookup_prior(topic) -> [VerifiedRecord]              (substring v1; semantic later)
    store_version()     -> str

`NOT_FOUND` is a distinct sentinel (not None): it means "we looked, the key does not resolve"
— a *positive* absence (e.g., clcnkb, slc12a1a), not "never checked". This distinction is the
point: it converts a silent wrong-ID into either a real record or a loud, explicit miss.
"""
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Union
import json

_DEFAULT_STORE = Path(__file__).resolve().parents[2] / "outputs" / "verified_identifiers.json"


class _NotFound:
    """Singleton sentinel: positive 'looked, does not resolve' (distinct from None)."""
    def __repr__(self):
        return "NOT_FOUND"

    def __bool__(self):
        return False


NOT_FOUND = _NotFound()


class ResolveError(KeyError):
    """Raised by require() when a key does not resolve in the store."""


@dataclass(frozen=True)
class VerifiedRecord:
    symbol: str
    ensdarg: Optional[str]
    taxon: Optional[int]
    source_db: Optional[str]
    resolver: Optional[str]
    raw_cache_ref: Optional[str]
    verified_on: Optional[str]
    provenance: Optional[str]
    confidence: float
    anchor_match: Optional[bool] = None
    ensdarp: Optional[str] = None
    ensdart: Optional[str] = None
    uniprot_acc: Optional[str] = None
    assembly: Optional[str] = None
    ensembl_release: Optional[int] = None
    notes: str = ""

    @property
    def is_raw_verified(self) -> bool:
        return bool(self.raw_cache_ref) and str(self.raw_cache_ref).startswith("RAW:")


class SourceOfTruth:
    def __init__(self, store_path: Union[str, Path] = _DEFAULT_STORE):
        self.store_path = Path(store_path)
        envelope = json.loads(self.store_path.read_text(encoding="utf-8"))
        self._version = envelope.get("store_version")
        self._by_symbol = {}
        self._by_ensdarg = {}
        self._by_uniprot = {}
        for row in envelope.get("records", []):
            rec = VerifiedRecord(
                symbol=row["symbol"],
                ensdarg=row.get("ensdarg"),
                taxon=row.get("taxon"),
                source_db=row.get("source_db"),
                resolver=row.get("resolver"),
                raw_cache_ref=row.get("raw_cache_ref"),
                verified_on=row.get("verified_on"),
                provenance=row.get("provenance"),
                confidence=row.get("confidence", 0.0),
                anchor_match=row.get("anchor_match"),
                ensdarp=row.get("ensdarp"),
                ensdart=row.get("ensdart"),
                uniprot_acc=row.get("uniprot_acc"),
                assembly=row.get("assembly"),
                ensembl_release=row.get("ensembl_release"),
                notes=row.get("notes", ""),
            )
            self._by_symbol[rec.symbol.lower()] = rec
            if rec.ensdarg:
                self._by_ensdarg[rec.ensdarg] = rec
            if rec.uniprot_acc:
                self._by_uniprot[rec.uniprot_acc] = rec

    def store_version(self) -> Optional[str]:
        return self._version

    def resolve(self, key: str) -> Union[VerifiedRecord, _NotFound]:
        if not key:
            return NOT_FOUND
        k = str(key).strip()
        rec = self._by_symbol.get(k.lower())
        if rec is not None:
            # A symbol present but with ensdarg=null is a positive NOT_FOUND.
            return rec if rec.ensdarg is not None else NOT_FOUND
        if k in self._by_ensdarg:
            return self._by_ensdarg[k]
        if k in self._by_uniprot:
            return self._by_uniprot[k]
        return NOT_FOUND

    def require(self, key: str) -> VerifiedRecord:
        rec = self.resolve(key)
        if rec is NOT_FOUND:
            raise ResolveError(
                f"{key!r} does not resolve in the verified-identifier store "
                f"({self.store_path}). Verify it against an authoritative source and cache the "
                f"raw response (CLAUDE.md §7.9) before using it. IDs are never used from memory."
            )
        return rec

    def lookup_prior(self, topic: str) -> List[VerifiedRecord]:
        t = (topic or "").lower()
        return [r for r in self._by_symbol.values()
                if t in r.symbol.lower() or t in (r.notes or "").lower()]


_default: Optional[SourceOfTruth] = None


def _get_default() -> SourceOfTruth:
    global _default
    if _default is None:
        _default = SourceOfTruth()
    return _default


def resolve(key):
    return _get_default().resolve(key)


def require(key):
    return _get_default().require(key)


def lookup_prior(topic):
    return _get_default().lookup_prior(topic)


def store_version():
    return _get_default().store_version()


if __name__ == "__main__":
    # Self-check / smoke test (NO-SPEND).
    sot = SourceOfTruth()
    print("store_version:", sot.store_version())
    for k in ("wt1a", "pax2a", "clcnkb", "ENSDARG00000028148", "nonsense"):
        r = sot.resolve(k)
        print(f"  resolve({k!r}) -> {r if r is NOT_FOUND else (r.symbol, r.ensdarg, r.raw_cache_ref)}")

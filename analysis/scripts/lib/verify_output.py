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
from pathlib import Path
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
    unresolved: List[str] = field(default_factory=list)          # in output, not in store, NO live provenance => FAILURE
    reingest_candidates: List[str] = field(default_factory=list) # not in store BUT present in a §7.9 raw cache => re-ingest candidate, NOT a failure (ADR-0036)
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
            "reingest_candidates": sorted(self.reingest_candidates),
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


def _live_verified_ids(reingest_cache) -> set:
    """Canonical ENSDARG present in the §7.9 raw cache file(s) — the deterministic, OFFLINE provenance that an
    out-of-store ID was fetched from an authoritative source (Ensembl), NOT fabricated (ADR-0036).

    An id counts as a re-ingest candidate ONLY if it literally appears in a real cached raw response; a bare
    assertion (no backing raw file, or file missing) does NOT — so this NEVER weakens the anti-fabrication
    gate. `reingest_cache` is a path or iterable of paths; unreadable paths are skipped."""
    if not reingest_cache:
        return set()
    paths = [reingest_cache] if isinstance(reingest_cache, (str, Path)) else list(reingest_cache)
    ids = set()
    for p in paths:
        try:
            txt = Path(p).read_text(encoding="utf-8")
        except Exception:
            continue
        for digits in _ENSDARG_EXTRACT.findall(txt):
            ids.add("ENSDARG" + digits)
    return ids


def verify_identifiers(text_or_obj, store=None, reingest_cache=None) -> VerificationReport:
    """Extract external identifiers from a string or JSON-serializable object and gate them.

    GATE FAILURE (report.ok == False) iff any ENSDARG in the output does not resolve in the store AND lacks
    live §7.9 provenance, OR any EXPLICIT structured symbol<->ENSDARG pair contradicts the store binding
    (N1 / ADR-0027). PMIDs/GEO accessions are flagged (honest gap), not failures, in v1.

    reingest_cache (ADR-0036): optional path(s) to §7.9 raw cache file(s). An out-of-store ENSDARG that
    appears in such a cached raw response is a *re-ingest candidate* (real, fetched live, not yet in the
    store) — surfaced in report.reingest_candidates and does NOT fail the gate. An out-of-store ENSDARG with
    NO such backing is `unresolved` and STILL fails (possible fabrication). Default None => identical to the
    prior behavior (no candidates; every out-of-store id is unresolved). Offline + deterministic.
    """
    sot = store or resolve_id._get_default()
    text = text_or_obj if isinstance(text_or_obj, str) else json.dumps(text_or_obj)
    report = VerificationReport()
    live_ids = _live_verified_ids(reingest_cache)

    for digits in sorted(set(_ENSDARG_EXTRACT.findall(text))):
        ens = "ENSDARG" + digits   # N2: canonical form (case/separator/version normalized) before resolving
        rec = sot.resolve(ens)
        if rec is resolve_id.NOT_FOUND:
            if ens in live_ids:
                report.reingest_candidates.append(ens)  # real (raw §7.9 backing), not in store yet -> re-ingest
            else:
                report.unresolved.append(ens)            # no provenance -> possible fabrication -> FAIL
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


def admissible(text_or_obj, store=None, extra_predicates=None, reingest_cache=None):
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
    report = verify_identifiers(text_or_obj, store=store, reingest_cache=reingest_cache)
    reasons = []
    if report.unresolved:
        reasons.append(f"unresolved external identifiers (hard fail): {sorted(report.unresolved)}")
    # NOTE: report.reingest_candidates are deliberately NOT a reason — an out-of-store id with §7.9 raw
    # backing is admissible + surfaced for the human-gated re-ingest loop (ADR-0036), not a fabrication fail.
    if report.misbound:
        reasons.append(f"mis-bound symbol<->ENSDARG pairs (hard fail, N1): {sorted(report.misbound)}")
    for pred in (extra_predicates or []):
        name, ok = pred(text_or_obj, report)
        if not ok:
            reasons.append(f"hard predicate failed: {name}")
    return (len(reasons) == 0), reasons


# --- ADR-0080 (E): afirmación positiva sin citas es INADMISIBLE + escalera de soporte por cita ---------
# La compuerta de competencia (ADR-0080 §4) y el panel necesitan dos cosas que hoy nadie calcula por código:
#   (1) un predicado DURO para H(c): una AFIRMACIÓN POSITIVA (absence_kind == 'not-applicable' — o AUSENTE:
#       lectura conservadora del corrector ADR-0080, la omisión del campo no puede ser la vía de escape) con
#       CERO citas válidas es inadmisible — el modelo afirmó algo y no señaló evidencia; una DECLINACIÓN
#       (absence_kind declarado != 'not-applicable') puede no citar: declarar una ausencia no exige una cita…
#       salvo que la "declinación" afirme identificadores RESUELTOS (verify_identifiers) sin citar: eso es
#       afirmar cosas concretas bajo la etiqueta de ausencia, y dispara igual (corrector ADR-0080).
#   (2) por cada cita, el peldaño más alto que ALCANZÓ en la escalera de soporte:
#         unresolved -> resolved -> passage_delivered -> supported | unsupported
#       Cada peldaño es una medición distinta (¿el id resuelve a un ítem del bundle? ¿el bundle entregó
#       texto para ese ítem? ¿un juez lo evaluó?) y NUNCA se funden: `resolved`, `passage_delivered`,
#       `pertinent` y `supported` viajan como campos separados junto al `support_state` derivado.
POSITIVE_CLAIM_ABSENCE_KIND = "not-applicable"
PREDICATE_POSITIVE_CLAIM_REQUIRES_CITATIONS = "positive_claim_requires_citations"
SUPPORT_LADDER = ("unresolved", "resolved", "passage_delivered", "supported", "unsupported")
SUPPORT_VERDICTS = ("supported", "unsupported", "not-assessable")
PERTINENT_NOT_AVAILABLE = "not-available (ADR-0082)"
SUPPORT_LADDER_RULE = ("support_state = highest rung REACHED, rungs are sequential: a judge verdict "
                       "(supported|unsupported) only lifts a citation whose passage was delivered; "
                       "'not-assessable' or 'not-evaluated' leave the state at the deterministic rung; "
                       "the raw judge word is kept in `supported` regardless (fields never fuse). ADR-0080")


def count_valid_citations(citations):
    """n de citas VÁLIDAS (id no vacío) — misma regla que runs._normalize_citations.n_valid (ADR-0078).
    Acepta un entero ya contado, una lista de citas tipadas ({n, kind, id, note}) o de ids crudos.
    Devuelve (n: int, state) con state ∈ 'counted' | 'given' | 'absent' (None → 0 declarado como
    'absent': no medido, no rellenado en silencio — ADR-0043)."""
    if citations is None or isinstance(citations, bool):
        return 0, "absent"
    if isinstance(citations, int):
        return max(0, citations), "given"
    if isinstance(citations, (list, tuple)):
        n = 0
        for c in citations:
            ident = c.get("id") if isinstance(c, dict) else c
            if ident is not None and str(ident).strip():
                n += 1
        return n, "counted"
    return 0, "absent"


POSITIVE_CLAIM_RULE = ("inadmissible iff (absence_kind == 'not-applicable' OR absence_kind absent — conservative "
                       "default) and n_citations_valid == 0; ALSO inadmissible iff a declination names resolved "
                       "identifiers (verify_identifiers verified_raw|verified_derived) and n_citations_valid == 0 "
                       "(ADR-0080, corrector)")


def _resolved_ids_of(identifier_report):
    """Identificadores RESUELTOS del informe de verify_identifiers (as_dict o VerificationReport): los que el
    store conoce (verified_raw | verified_derived). None = no se recibió informe (declarado, no inferido)."""
    if identifier_report is None:
        return None
    rep = identifier_report.as_dict() if hasattr(identifier_report, "as_dict") else identifier_report
    if not isinstance(rep, dict):
        return None
    out = []
    for key in ("verified_raw", "verified_derived"):
        for ident in rep.get(key) or []:
            if ident not in out:
                out.append(str(ident))
    return sorted(out)


def evaluate_positive_claim_citations(absence_kind, citations_valid, resolved_identifiers=None):
    """Evaluación PURA del predicado (ADR-0080 §4, corrector): dict con la decisión y su porqué, sin efectos.

    positive_claim = (absence_kind is None) ∨ (absence_kind == 'not-applicable') — un absence_kind AUSENTE se
    trata como afirmación positiva (lectura CONSERVADORA declarada en `absence_kind_state`: la omisión del campo
    era la vía de escape más barata para pasar el gate sin citar; el eje `world` del episodio sigue llevándolo a
    indeterminate — aquí sólo se exige evidencia). ok = ¬positive_claim ∨ n_citations_valid > 0, y además una
    DECLINACIÓN que nombra identificadores resueltos (`resolved_identifiers`, de verify_identifiers) con 0 citas
    también es inadmisible: afirma cosas concretas bajo la etiqueta de ausencia. `resolved_identifiers` None =
    informe no recibido (`resolved_identifiers_state 'not-provided'`), la segunda regla no se evalúa."""
    n_valid, cit_state = count_valid_citations(citations_valid)
    kind_state = ("absent -> treated-as-positive (ADR-0080 conservative default)" if absence_kind is None
                  else "declared")
    positive = absence_kind is None or absence_kind == POSITIVE_CLAIM_ABSENCE_KIND
    resolved = list(resolved_identifiers) if isinstance(resolved_identifiers, (list, tuple, set)) else None
    resolved_state = "not-provided" if resolved is None else "checked"
    declination_with_ids = (not positive) and bool(resolved) and n_valid == 0
    ok = ((not positive) or n_valid > 0) and not declination_with_ids
    if positive and not ok:
        reason = ("positive claim (absence_kind 'not-applicable') with 0 valid citations" if absence_kind is not None
                  else "absence_kind absent -> treated as positive claim (conservative default) with 0 valid citations")
    elif positive:
        reason = f"positive claim with {n_valid} valid citation(s)" + (" (absence_kind absent)" if absence_kind is None else "")
    elif declination_with_ids:
        reason = f"declination with resolved identifiers {sorted(resolved)} and 0 citations"
    else:
        reason = f"declination (absence_kind {absence_kind!r}) may go uncited"
    return {"name": PREDICATE_POSITIVE_CLAIM_REQUIRES_CITATIONS, "ok": ok,
            "positive_claim": positive, "absence_kind": absence_kind, "absence_kind_state": kind_state,
            "n_citations_valid": n_valid, "citations_state": cit_state,
            "resolved_identifiers": sorted(resolved) if resolved is not None else None,
            "resolved_identifiers_state": resolved_state,
            "reason": reason, "rule": POSITIVE_CLAIM_RULE, "decided_by": "code"}


def positive_claim_requires_citations(answer, citations_valid, identifier_report=None):
    """Predicado DURO para admissible(extra_predicates=[...]) (ADR-0080 §4).

    `answer` es el dict del sintetizador (se lee `absence_kind` y, para la segunda regla, `direct_answer`);
    `citations_valid` es el n de citas válidas ya contado (int), la lista de citas normalizadas, o None
    (declarado 'absent' → 0); `identifier_report` (corrector ADR-0080) es el informe de verify_identifiers que
    el gate ya midió sobre la misma respuesta (as_dict) — si no llega y hay `direct_answer`, se mide aquí
    (offline, determinista); sin texto queda 'not-provided'. Devuelve el callable (text_or_obj, report) ->
    (name, ok) que admissible() ANDea; la evaluación completa queda en `pred.evaluation` para que el caller la
    congele en deterministic_checks sin recalcular. Recibe NINGUNA confianza — la conjunción H sigue hecha sólo
    de invariantes duros (R2 / ADR-0024)."""
    absence_kind = answer.get("absence_kind") if isinstance(answer, dict) else None
    if identifier_report is None and isinstance(answer, dict) and isinstance(answer.get("direct_answer"), str):
        try:
            identifier_report = verify_identifiers(answer["direct_answer"]).as_dict()
        except Exception:   # el informe es insumo opcional; su fallo no tumba el predicado (queda not-provided)
            identifier_report = None
    evaluation = evaluate_positive_claim_citations(absence_kind, citations_valid,
                                                   resolved_identifiers=_resolved_ids_of(identifier_report))

    def _pred(_text_or_obj, _report):
        return evaluation["name"], evaluation["ok"]

    _pred.evaluation = evaluation
    _pred.__name__ = PREDICATE_POSITIVE_CLAIM_REQUIRES_CITATIONS
    return _pred


def _citation_keys(cit):
    """Variantes DETERMINISTAS bajo las que una cita puede nombrar un ítem del bundle: el id tal cual, en
    mayúsculas, con/sin prefijo 'PMID:' cuando es numérico, DOI sin 'https://doi.org/'. Nada se infiere del
    texto libre de la nota."""
    ident = cit.get("id") if isinstance(cit, dict) else cit
    s = str(ident or "").strip()
    if not s:
        return set()
    up = s.upper()
    keys = {s, up}
    if up.startswith("PMID:"):
        keys.add(up[5:].strip())
    elif re.fullmatch(r"\d{4,9}", s):
        keys.add(f"PMID:{s}")
    if up.startswith("HTTPS://DOI.ORG/"):
        keys.add(up[len("HTTPS://DOI.ORG/"):])
    return keys


def _bundle_evidence_index(bundle):
    """{clave normalizada -> (evidence_id canónico, passage_delivered: bool)} para todo ítem del bundle:
    path_a.hits (doc_id; texto = `text`), path_b.papers (evidence_id + pmid/pmcid/doi del search_rec;
    texto = abstract | text_excerpt | statement; para zfin ≥1 `phenotypes[].statement`)."""
    idx = {}
    b = bundle or {}

    def _put(key, ident, delivered):
        k = str(key or "").strip()
        if not k:
            return
        for var in (k, k.upper()):
            idx.setdefault(var, (ident, delivered))

    for h in ((b.get("path_a") or {}).get("hits") or []):
        if not isinstance(h, dict):
            continue
        ident = h.get("doc_id")
        _put(ident, ident, bool(str(h.get("text") or "").strip()))
    for p in ((b.get("path_b") or {}).get("papers") or []):
        if not isinstance(p, dict):
            continue
        ident = p.get("evidence_id")
        delivered = any(str(p.get(k) or "").strip() for k in ("abstract", "text_excerpt", "statement"))
        z = p.get("zfin")
        if not delivered and isinstance(z, dict):
            delivered = any(str((ph or {}).get("statement") or "").strip()
                            for ph in (z.get("phenotypes") or []) if isinstance(ph, dict))
        _put(ident, ident, delivered)
        rec = p.get("search_rec") or {}
        if rec.get("pmid"):
            _put(f"PMID:{rec['pmid']}", ident, delivered)
            _put(str(rec["pmid"]), ident, delivered)
        if rec.get("pmcid"):
            _put(rec["pmcid"], ident, delivered)
        if rec.get("doi"):
            _put(str(rec["doi"]).lower().replace("https://doi.org/", ""), ident, delivered)
    return idx


def _grounding_by_n(grounding):
    """{n -> verdict} desde la salida OPCIONAL de la lente evidence-grounding (composite_auditor
    VERDICT_TOOL.citation_support: [{n, verdict}]) o de un dict {n: verdict}. Un veredicto fuera del
    vocabulario o un n no entero se DESCARTA y se cuenta (nunca se corrige en silencio)."""
    out, dropped = {}, 0
    if grounding is None:
        return out, dropped
    if isinstance(grounding, dict):
        items = list(grounding.items())
    elif isinstance(grounding, (list, tuple)):
        items = [(g.get("n"), g.get("verdict")) for g in grounding if isinstance(g, dict)]
    else:
        items = []
    for n, v in items:
        try:
            n_int = int(n)
        except (TypeError, ValueError):
            dropped += 1
            continue
        if v in SUPPORT_VERDICTS and n_int not in out:
            out[n_int] = v
        else:
            dropped += 1
    return out, dropped


def support_state_for(citations, bundle, grounding=None):
    """Escalera de soporte POR CITA (ADR-0080 §4 / hallazgo de la auditoría externa: 'citas explotadas').

    Por cada cita normalizada {n, kind, id, note} devuelve
      {n, id, resolved: bool, resolved_to, passage_delivered: bool, pertinent: 'not-available (ADR-0082)',
       supported: 'supported'|'unsupported'|'not-assessable'|'not-evaluated', support_state, ladder_rule}
    - resolved: el id nombra un ítem del bundle (path_a hit / path_b paper / zfin) por clave determinista.
    - passage_delivered: ese ítem trae abstract | text_excerpt | statement (o ≥1 statement zfin) no vacío.
    - pertinent: NO disponible hasta ADR-0082 (el consejo no juzga pertinencia todavía) — literal declarado.
    - supported: la palabra del juez evidence-grounding para ese n, o 'not-evaluated' (sin grounding /
      sin entrada para ese n). Jamás se fabrica.
    - support_state: el peldaño más alto ALCANZADO (SUPPORT_LADDER_RULE): un veredicto sólo eleva una cita
      con pasaje entregado; los campos nunca se funden.
    grounding: lista [{n, verdict}] (citation_support del panel) o dict {n: verdict}; None = no evaluado."""
    idx = _bundle_evidence_index(bundle)
    verdicts, _dropped = _grounding_by_n(grounding)
    rows = []
    for c in (citations or []):
        cit = c if isinstance(c, dict) else {"id": c}
        n = cit.get("n")
        hit = next((idx[k] for k in _citation_keys(cit) if k in idx), None)
        resolved = hit is not None
        delivered = bool(hit[1]) if resolved else False
        try:
            judged = verdicts.get(int(n)) if n is not None else None
        except (TypeError, ValueError):
            judged = None
        supported = judged if judged in SUPPORT_VERDICTS else "not-evaluated"
        if not resolved:
            state = "unresolved"
        elif not delivered:
            state = "resolved"
        elif supported in ("supported", "unsupported"):
            state = supported
        else:
            state = "passage_delivered"
        rows.append({"n": n, "id": str(cit.get("id", "")), "resolved": resolved,
                     "resolved_to": hit[0] if resolved else None,
                     "passage_delivered": delivered, "pertinent": PERTINENT_NOT_AVAILABLE,
                     "supported": supported, "support_state": state, "ladder_rule": SUPPORT_LADDER_RULE})
    return rows


def support_summary(rows):
    """frozen.citations_support_summary (ADR-0080 §13): {n, by_state} con TODOS los peldaños presentes
    (un 0 aquí es medido: la escalera se corrió sobre n citas; sin citas n=0 y todo 0)."""
    by_state = {s: 0 for s in SUPPORT_LADDER}
    for r in (rows or []):
        s = r.get("support_state")
        if s in by_state:
            by_state[s] += 1
    return {"n": len(rows or []), "by_state": by_state, "ladder": list(SUPPORT_LADDER),
            "pertinent": PERTINENT_NOT_AVAILABLE}


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
    # ADR-0036: an out-of-store id WITH §7.9 raw backing is a re-ingest candidate (admissible), one WITHOUT
    # backing is still a fabrication fail. Uses a temp cache holding one syntactically-valid out-of-store id.
    import tempfile as _tf, os as _os
    _fake = "ENSDARG00000099999"; _other = "ENSDARG00000088888"   # neither is in the store
    _cache = _os.path.join(_tf.gettempdir(), "verify_output_reingest_selftest.json")
    Path(_cache).write_text(json.dumps({"responses": {"foo": {"id": _fake}}}), encoding="utf-8")
    adm_nocache, _ = admissible(f"gene X is {_fake}")                        # no backing -> FAIL
    adm_cache, _ = admissible(f"gene X is {_fake}", reingest_cache=_cache)   # backed -> candidate, admissible
    adm_other, _ = admissible(f"gene Y is {_other}", reingest_cache=_cache)  # not in cache -> FAIL
    rep = verify_identifiers(f"gene X is {_fake}", reingest_cache=_cache)
    print(f"ADR-0036 reingest: no_cache_admissible={adm_nocache} (expect False) | "
          f"cache_backed_admissible={adm_cache} (expect True) | other_id_admissible={adm_other} (expect False) | "
          f"reingest_candidates={rep.reingest_candidates}")
    _os.remove(_cache)

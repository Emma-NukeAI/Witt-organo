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

# ADR-0083 (F): los predicados de figuras recalculan el sha256 al gatear con lib/figures.verify_cached (F1, stdlib puro).
# Import TOLERANTE: un árbol sin figures.py declara 'tool-unavailable (…)' en deterministic_checks.figures — jamás se
# re-implementa aquí ni se rellena (§6 no-hang; mismo patrón que runs._positive_claim_check para este módulo).
try:
    from . import figures as _figures
except Exception:  # pragma: no cover — sólo en un árbol parcial
    _figures = None

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
# ADR-0082 (G.4): el peldaño `pertinent` deja de ser gris cuando el consejo juzgó cobertura. Tres literales/valores:
#   True                       — algún voto VÁLIDO de r2/r3 con coverage ∈ {covered, partial} nombró el id (pertinent_to[]).
#   PERTINENT_NOT_NAMED        — hubo ronda válida y ningún voto citó el id: un miembro sólo juzga SUS requisitos, así que
#                                que nadie la nombrara NO niega su pertinencia (ausencia ≠ cero; jamás `false`).
#   'not-available (council <state>)' — sin ronda válida (kill-switch, no-ledger, incomplete, errored…): la escalera no
#                                cambia de peldaños; el literal viejo PERTINENT_NOT_AVAILABLE sigue válido en registros ≤ 1.10.
PERTINENT_NOT_NAMED = "not-named-by-council (valid round; no vote cites this id)"
PERTINENT_NOT_AVAILABLE_PREFIX = "not-available ("
PERTINENT_RULE = ("pertinent: true when a VALID council vote (r2|r3, coverage covered|partial) cites this citation's "
                  "resolved id (pertinent_to = requirement_ids); 'not-named-by-council (…)' when a valid round ran and no "
                  "vote cites it (never false: members judge only their own requirements); 'not-available (council "
                  "<state>)' without a valid round (ADR-0082 G.4)")
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


def _figure_items(bundle):
    """Los FigureItem del bundle en orden paper → documento (ADR-0083 (C)/(E)): `path_b.papers[].figures.items[]`
    (la mutación en sitio de figures.attach); si ningún paper los trae, `bundle.figures_ledger.items[]` (F4 puede
    pop('papers') del resumen; los ítems quedan). Dedupe por `id`; nada se infiere de otra parte."""
    b = bundle or {}
    out, seen = [], set()

    def _take(items):
        for it in items or []:
            if isinstance(it, dict) and it.get("id") and it["id"] not in seen:
                seen.add(it["id"])
                out.append(it)

    for p in ((b.get("path_b") or {}).get("papers") or []):
        if isinstance(p, dict) and isinstance(p.get("figures"), dict):
            _take(p["figures"].get("items"))
    if not out and isinstance(b.get("figures_ledger"), dict):
        _take(b["figures_ledger"].get("items"))
    return out


def _bundle_evidence_index(bundle):
    """{clave normalizada -> (evidence_id canónico, passage_delivered: bool)} para todo ítem del bundle:
    path_a.hits (doc_id; texto = `text`), path_b.papers (evidence_id + pmid/pmcid/doi del search_rec;
    texto = abstract | text_excerpt | statement; para zfin ≥1 `phenotypes[].statement`).
    ADR-0083 (E): cada figura `papers[].figures.items[]` es un ítem PROPIO bajo su id '<PMCID>#<fig_id>' con
    `delivered` = el caption se entregó (caption_state 'present'). Una figura SIN caption no se entrega al sintetizador
    ni a las lentes (A.1: no puede sostener texto) → NO se indexa: citarla es citar algo no entregado (unresolved)."""
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
    for it in _figure_items(b):   # ADR-0083 (E): la figura como ítem propio; sólo con caption entregado
        if it.get("caption_state") == "present":
            _put(it["id"], it["id"], True)
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


def _pertinent_for(cit, resolved_to, council_pertinence):
    """(pertinent, pertinent_to) de UNA cita contra el mapa {evidence_id: [requirement_id]} de votos VÁLIDOS del
    consejo (ADR-0082 G.4). Se casan las variantes deterministas del id (_citation_keys) y el id canónico al que
    resolvió; nada se infiere del texto de la nota."""
    keys = set(_citation_keys(cit))
    if resolved_to:
        keys |= {str(resolved_to), str(resolved_to).upper()}
    rids = []
    for k in keys:
        for rid in (council_pertinence.get(k) or []):
            if rid not in rids:
                rids.append(rid)
    if rids:
        return True, sorted(rids)
    return PERTINENT_NOT_NAMED, []


def support_state_for(citations, bundle, grounding=None, council_pertinence=None, council_state=None,
                      council_source=None):
    """Escalera de soporte POR CITA (ADR-0080 §4 / hallazgo de la auditoría externa: 'citas explotadas').

    Por cada cita normalizada {n, kind, id, note} devuelve
      {n, id, resolved: bool, resolved_to, passage_delivered: bool, pertinent: true | 'not-named-by-council (…)' |
       'not-available (council <state>)' | 'not-available (ADR-0082)', pertinent_to?[], pertinent_source?,
       supported: 'supported'|'unsupported'|'not-assessable'|'not-evaluated', support_state, ladder_rule}
    - resolved: el id nombra un ítem del bundle (path_a hit / path_b paper / zfin) por clave determinista.
    - passage_delivered: ese ítem trae abstract | text_excerpt | statement (o ≥1 statement zfin) no vacío.
    - pertinent (ADR-0082 G.4): con `council_pertinence` = {evidence_id: [requirement_id…]} derivado SÓLO de
      votos VÁLIDOS de r2/r3 con coverage ∈ {covered, partial}, la cita resuelta gana `pertinent: true` +
      `pertinent_to[]` cuando su id (o su `resolved_to`) está en el mapa, y PERTINENT_NOT_NAMED cuando no —
      jamás `false` (un miembro sólo juzga SUS requisitos: que nadie nombrara una cita no niega su pertinencia).
      Sin mapa: 'not-available (council <council_state>)' cuando el llamador declara el estado del consejo,
      o el literal viejo PERTINENT_NOT_AVAILABLE (registros/llamadores ≤ 1.10). La escalera NO cambia de peldaños.
    - supported: la palabra del juez evidence-grounding para ese n, o 'not-evaluated' (sin grounding /
      sin entrada para ese n). Jamás se fabrica.
    - support_state: el peldaño más alto ALCANZADO (SUPPORT_LADDER_RULE): un veredicto sólo eleva una cita
      con pasaje entregado; los campos nunca se funden.
    grounding: lista [{n, verdict}] (citation_support del panel) o dict {n: verdict}; None = no evaluado."""
    idx = _bundle_evidence_index(bundle)
    verdicts, _dropped = _grounding_by_n(grounding)
    has_council = isinstance(council_pertinence, dict)
    not_available = (f"{PERTINENT_NOT_AVAILABLE_PREFIX}council {council_state})" if council_state
                     else PERTINENT_NOT_AVAILABLE)
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
        row = {"n": n, "id": str(cit.get("id", "")), "resolved": resolved,
               "resolved_to": hit[0] if resolved else None,
               "passage_delivered": delivered, "pertinent": not_available,
               "supported": supported, "support_state": state, "ladder_rule": SUPPORT_LADDER_RULE}
        if has_council:
            pert, to = _pertinent_for(cit, hit[0] if resolved else None, council_pertinence)
            row["pertinent"] = pert
            row["pertinent_to"] = to
            row["pertinent_source"] = council_source or "council (covered|partial votes)"
        rows.append(row)
    return rows


def support_summary(rows):
    """frozen.citations_support_summary (ADR-0080 §13): {n, by_state} con TODOS los peldaños presentes
    (un 0 aquí es medido: la escalera se corrió sobre n citas; sin citas n=0 y todo 0).
    ADR-0082 (G.4): `pertinent` pasa de literal a {state, n_true, n_not_named, n_not_available, literal} — aditivo:
    el literal viejo (PERTINENT_NOT_AVAILABLE) sigue DENTRO (`literal`), `state` dice si el consejo juzgó ('checked')
    o el literal not-available que las filas llevan."""
    by_state = {s: 0 for s in SUPPORT_LADDER}
    n_true = n_named = n_na = 0
    na_literal = None
    for r in (rows or []):
        s = r.get("support_state")
        if s in by_state:
            by_state[s] += 1
        p = r.get("pertinent")
        if p is True:
            n_true += 1
        elif p == PERTINENT_NOT_NAMED:
            n_named += 1
        else:
            n_na += 1
            if isinstance(p, str) and na_literal is None:
                na_literal = p
    if n_true or n_named:
        p_state = "checked"
    else:
        p_state = na_literal or PERTINENT_NOT_AVAILABLE
    return {"n": len(rows or []), "by_state": by_state, "ladder": list(SUPPORT_LADDER),
            "pertinent": {"state": p_state, "n_true": n_true, "n_not_named": n_named, "n_not_available": n_na,
                          "literal": PERTINENT_NOT_AVAILABLE, "rule": PERTINENT_RULE}}


# --- ADR-0083 (F): CINCO predicados DETERMINISTAS sobre citas kind 'figure' (clase Logic-LM, ciegos a píxeles) ----------
# Una figura es MEDICIÓN sólo cuando el código verifica identidad (fig_id del JATS), bytes (sha256 recalculado al gatear)
# y licencia (tabla cerrada, F1). Lo que la imagen DICE es JUICIO de dos lentes del panel y jamás entra aquí: estos
# predicados leen el bundle (ítems FigureItem con caption/sha/licencia), la caché (bytes) y el TEXTO de la respuesta —
# nunca un píxel. Tres son DUROS (entran a la conjunción H(c) de admissible()); dos son INFORMATIVOS (gating False:
# se congelan, jamás tumban). El sintetizador sólo vio caption + metadatos (D.1), así que la doctrina §7 «figure-only
# NOT asserted» se hace mecánica en figure_only_not_asserted: la figura CORROBORA; el TEXTO porta la evidencia.
FIGURE_PREDICATES_VERSION = "figpred-1"
PREDICATE_FIGURE_ID_RESOLVES = "figure_id_resolves"
PREDICATE_FIGURE_SHA_MATCHES = "figure_sha_matches"
PREDICATE_FIGURE_ONLY_NOT_ASSERTED = "figure_only_not_asserted"
PREDICATE_FIGURE_NUMERALS_GROUNDED = "figure_numerals_grounded"
PREDICATE_FIGURE_LICENSE_KNOWN = "figure_license_known"
FIGURE_PREDICATES = (PREDICATE_FIGURE_ID_RESOLVES, PREDICATE_FIGURE_SHA_MATCHES, PREDICATE_FIGURE_ONLY_NOT_ASSERTED,
                     PREDICATE_FIGURE_NUMERALS_GROUNDED, PREDICATE_FIGURE_LICENSE_KNOWN)
# gating por predicado (F): DURO = entra a la conjunción; INFORMATIVO = se congela y no gatea (LG3 decide si sube, 0083.1)
FIGURE_GATING = {PREDICATE_FIGURE_ID_RESOLVES: True, PREDICATE_FIGURE_SHA_MATCHES: True,
                 PREDICATE_FIGURE_ONLY_NOT_ASSERTED: True, PREDICATE_FIGURE_NUMERALS_GROUNDED: False,
                 PREDICATE_FIGURE_LICENSE_KNOWN: False}
FIGURE_CHECK_STATE_KILL_SWITCH = "kill-switch WITT_FIGURES=0"
FIGURE_CHECK_STATES_EXACT = ("checked", "no-figure-citations", FIGURE_CHECK_STATE_KILL_SWITCH)
FIGURE_CHECK_STATES_PREFIXES = ("tool-unavailable (", "error: ")
FIGURE_CHECK_STATE_TOOL_UNAVAILABLE = "tool-unavailable (lib/figures.py not importable — ADR-0083 F1)"
FIGURE_NUMERALS_STATES = ("checked", "no-markers: whole-answer fallback",
                          "partial-markers: whole-answer fallback for unmarked", "no-figure-citations")
# Los CINCO literales congelados en deterministic_checks.figures.rules (F): qué mide cada uno y qué NO.
FIGURE_RULES = {
    PREDICATE_FIGURE_ID_RESOLVES: (
        "HARD. Every figure citation (kind 'figure', or an id shaped '<PMCID>#<fig_id>', or an id that names a figure "
        "item — the conservative superset: the label the model chose never rescues a figure-shaped id) must resolve to a "
        "figure item of the bundle whose caption was DELIVERED (caption_state 'present'); a figure without caption was never "
        "delivered to the synthesizer and cannot be cited. Unresolved -> inadmissible ('hard predicate failed: "
        "figure_id_resolves'), same discipline as an unresolved ENSDARG. ADR-0083 F.1"),
    PREDICATE_FIGURE_SHA_MATCHES: (
        "HARD only on MISMATCH. For each cited figure whose item is bytes_state 'verified', the sha256 of the cached file is "
        "RECOMPUTED at gate time (figures.verify_cached, ADR-0077) and must equal the bundle sha256; any inequality -> "
        "inadmissible with mismatches[{id, expected, actual}]. An item not-fetched/mismatch, a missing file or no cache_dir "
        "is n_not_verifiable (declared, the citation still supports only its caption) and does NOT fail: absence is not "
        "alteration (§6). ok null = nothing was checkable. ADR-0083 F.2"),
    PREDICATE_FIGURE_ONLY_NOT_ASSERTED: (
        "HARD (CLAUDE.md §7 'figure-only NOT asserted', by kinds). A POSITIVE claim (absence_kind 'not-applicable' or "
        "absent/not provided — the conservative reading of POSITIVE_CLAIM_RULE) with >= 1 figure citation and NO non-figure "
        "citation whose id RESOLVES to a bundle item with a DELIVERED text passage is inadmissible: a figure corroborates, "
        "the TEXT carries the evidence — and only text that was actually delivered can carry it (corrector: a hallucinated "
        "or unresolved text id beside the figure does NOT rescue the claim; counted in n_non_figure_citations_unresolved). "
        "A declination (absence_kind declared != 'not-applicable') may rest on figures alone. With 0 valid citations this "
        "predicate is vacuously ok (positive_claim_requires_citations decides). Measured, not gated (D.2 'may only accompany "
        "a text citation of the same paper'): same_paper_text_citation per figure citation. Declared limit: a QUALITATIVE "
        "figure-only assertion with one DELIVERED text citation beside it is not caught here (vision lenses judge it; F.4 "
        "only measures). ADR-0083 F.3"),
    PREDICATE_FIGURE_NUMERALS_GROUNDED: (
        "INFORMATIVE (gating false; LG3 measures its false-positive rate before 0083.1 may promote it). For each figure "
        "citation with an inline marker [n] in direct_answer, its sentence is taken and every numeral (\\d+(?:[.,]\\d+)?\\s*%?, "
        "markers stripped) must occur in that figure's caption or in a DELIVERED text passage (abstract | text_excerpt | "
        "statement | zfin statements | another cited figure's caption) of another citation in the SAME sentence; without a "
        "marker for that citation the WHOLE answer is checked against the union of the cited figures' captions and the "
        "non-figure citations' passages ('no-marker: whole-answer fallback') and n_marker_absent counts it as a measured "
        "limit — never a silent ok. Numerals match as substrings not embedded in a longer number; separators ('0,5' vs '0.5') "
        "are NOT normalized; years and sample sizes count. ADR-0083 F.4"),
    PREDICATE_FIGURE_LICENSE_KNOWN: (
        "INFORMATIVE (gating false). license.id != 'unknown' for every cited figure that resolves; unknown[] frozen. The "
        "license gates EMBEDDING (GET /figures, panel bytes, PDF thumbnails), never the truth of the citation. ADR-0083 F.5"),
}
_FIGURE_ID_RE = re.compile(r"^PMC\d+#\S+$", re.I)          # forma '<PMCID>#<fig_id>' (L)
_MARKER_RE = re.compile(r"\[(\d+)\]")                        # marcador inline [n] (D.2)
_NUMERAL_RE = re.compile(r"\d+(?:[.,]\d+)?\s*%?")            # el numeral del ADR (F.4), tal cual
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_MARKERS_ONLY_RE = re.compile(r"^\s*(?:\[\d+\]\s*)+[.!?]?\s*$")


def _is_figure_citation(cit, fig_index):
    """Superset conservador (F.1): kind 'figure' ∨ id con forma '<PMCID>#<fig_id>' ∨ id que nombra un ítem figura."""
    if not isinstance(cit, dict):
        return False
    ident = str(cit.get("id") or "").strip()
    if not ident:
        return False
    if cit.get("kind") == "figure" or _FIGURE_ID_RE.match(ident):
        return True
    return any(k in fig_index for k in _citation_keys(cit))


def _resolve_figure(cit, fig_index):
    """El FigureItem al que la cita resuelve (por las variantes deterministas de _citation_keys) o None."""
    for k in _citation_keys(cit):
        if k in fig_index:
            return fig_index[k]
    return None


def _bundle_passages(bundle):
    """{clave normalizada -> texto ENTREGADO} para F.4: path_a hits (text), papers (abstract + text_excerpt + statement +
    zfin statements) bajo evidence_id/PMID/PMCID/DOI, y cada figura con caption 'present' bajo su id (el caption ES el
    pasaje entregado de una figura). Sólo texto que el bundle entregó; nada se infiere."""
    out = {}
    b = bundle or {}

    def _put(key, text):
        k = str(key or "").strip()
        if k and text:
            for var in (k, k.upper()):
                out.setdefault(var, text)

    for h in ((b.get("path_a") or {}).get("hits") or []):
        if isinstance(h, dict):
            _put(h.get("doc_id"), str(h.get("text") or ""))
    for p in ((b.get("path_b") or {}).get("papers") or []):
        if not isinstance(p, dict):
            continue
        parts = [str(p.get(k) or "") for k in ("abstract", "text_excerpt", "statement")]
        z = p.get("zfin")
        if isinstance(z, dict):
            parts.extend(str((ph or {}).get("statement") or "") for ph in (z.get("phenotypes") or []) if isinstance(ph, dict))
        text = " ".join(t for t in parts if t.strip())
        if not text:
            continue
        _put(p.get("evidence_id"), text)
        rec = p.get("search_rec") or {}
        if rec.get("pmid"):
            _put(f"PMID:{rec['pmid']}", text)
            _put(str(rec["pmid"]), text)
        if rec.get("pmcid"):
            _put(rec["pmcid"], text)
        if rec.get("doi"):
            _put(str(rec["doi"]).lower().replace("https://doi.org/", ""), text)
    for it in _figure_items(b):
        if it.get("caption_state") == "present" and str(it.get("caption") or "").strip():
            _put(it["id"], str(it["caption"]))
    return out


def _passage_of(cit, passages):
    for k in _citation_keys(cit):
        if k in passages:
            return passages[k]
    return None


def _norm_numeral(s):
    return re.sub(r"\s+", "", str(s))


def _numeral_in(numeral, text):
    """El numeral (normalizado sin espacios) consta en `text` como substring NO incrustado en un número más largo
    ('12' no casa en '2012' ni en '12.5'; '42%' casa en '42 %'). Separadores decimales NO se normalizan (declarado)."""
    if not text:
        return False
    src = re.sub(r"(\d)\s+%", r"\1%", str(text))
    num = _norm_numeral(numeral)
    core = num[:-1] if num.endswith("%") else num
    pat = r"(?<![\d.,])" + re.escape(core) + (r"\s*%" if num.endswith("%") else r"(?![\d.,]?\d)")
    return re.search(pat, src) is not None


def _sentences_with_markers(text):
    """[(oración, {n…})] — oraciones por puntuación terminal; un fragmento que sólo trae marcadores ('[3][5].') se
    funde con la oración anterior (el marcador cierra la oración que lo precede)."""
    out = []
    for frag in _SENTENCE_SPLIT_RE.split(str(text or "")):
        if not frag.strip():
            continue
        if out and _MARKERS_ONLY_RE.match(frag):
            prev_s, prev_ns = out[-1]
            out[-1] = (prev_s + " " + frag, prev_ns | {int(m) for m in _MARKER_RE.findall(frag)})
            continue
        out.append((frag, {int(m) for m in _MARKER_RE.findall(frag)}))
    return out


def _numerals_of(text):
    """Numerales (F.4) del texto con los marcadores [n] QUITADOS antes (el n de una cita no es una cifra del texto);
    orden de aparición, sin duplicados, normalizados sin espacios internos ('42 %' -> '42%')."""
    stripped = _MARKER_RE.sub(" ", str(text or ""))
    seen, out = set(), []
    for m in _NUMERAL_RE.findall(stripped):
        n = _norm_numeral(m)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _block(name, ok, reason, **fields):
    """Bloque por predicado (F): {ok, gating, reason, rule: <name>, …medidas}. `ok` es el valor (bool | null = no medido)."""
    d = {"ok": ok, "gating": FIGURE_GATING[name], "reason": reason, "rule": name}
    d.update(fields)
    return d


def _mk_pred(name, ok, block):
    """Closure (text_or_obj, report) -> (name, ok) para admissible(extra_predicates); recibe NINGUNA confianza (R2)."""
    def _pred(_text_or_obj, _report):
        return name, ok
    _pred.evaluation = block
    _pred.__name__ = name
    return _pred


_UNSET = object()
ABSENCE_KIND_NOT_PROVIDED_STATE = ("not-provided by caller (answer_text is a str and no absence_kind= was passed) -> "
                                   "treated-as-positive (ADR-0080 conservative default)")


def figure_predicates(citations, bundle, cache_dir, answer_text, absence_kind=_UNSET, cfg=None):
    """(fragmento deterministic_checks.figures, extra_predicates[]) — ADR-0083 (F), clase Logic-LM, ciego a píxeles.

    citations: citas NORMALIZADAS ({n, kind, id, note}, runs._normalize_citations) o ids crudos. bundle: el bundle con
    `path_b.papers[].figures.items[]` (figures.attach). cache_dir: raíz de la caché de figuras (Path|str) o None (nada
    verificable → declarado). answer_text: el DICT del sintetizador (preferido: se leen `direct_answer` y `absence_kind`)
    o sólo el `direct_answer` (str). `absence_kind=` explícito gana. Si el llamador pasó SÓLO texto y ningún absence_kind,
    F.3 no puede distinguir declinación de afirmación: se aplica la lectura CONSERVADORA (positiva) y el bloque lo DECLARA
    con `absence_kind_state` = ABSENCE_KIND_NOT_PROVIDED_STATE (distinto del 'absent -> …' del campo omitido por el
    sintetizador) — el registro nombra la causa, nada se disfraza. cfg: figures.env_config() inyectable (smokes); default se
    lee EN LA LLAMADA (M.4).

    Estados del fragmento: 'checked' (≥1 cita figura: los 3 DUROS entran a la conjunción, los 2 informativos se congelan) |
    'no-figure-citations' (los 5 bloques se miden — ceros medidos — pero NINGÚN predicado entra: admisibilidad de hoy) |
    'kill-switch WITT_FIGURES=0' (fragmento EXACTAMENTE {state}, M.1: una de las 3 excepciones declaradas del frozen 1.11) |
    'tool-unavailable (…)' (lib/figures.py no importable). Jamás relanza: un error interno se declara en `state`."""
    if isinstance(answer_text, dict):
        text = str(answer_text.get("direct_answer") or "")
        if absence_kind is _UNSET:
            absence_kind = answer_text.get("absence_kind")
        absence_provided = True
    else:
        text = str(answer_text or "")
        absence_provided = absence_kind is not _UNSET
        if not absence_provided:
            absence_kind = None
    if _figures is None:
        return {"state": FIGURE_CHECK_STATE_TOOL_UNAVAILABLE}, []
    try:
        cfg = cfg or _figures.env_config()
    except Exception as e:  # el lector es tolerante; esto sólo ocurre en un árbol roto — se declara
        return {"state": f"error: {type(e).__name__}: {str(e)[:120]}"}, []
    ledger_state = ((bundle or {}).get("figures_ledger") or {}).get("state") if isinstance(bundle, dict) else None
    if not cfg.get("figures", True) or ledger_state == FIGURE_CHECK_STATE_KILL_SWITCH:
        return {"state": FIGURE_CHECK_STATE_KILL_SWITCH}, []

    items = _figure_items(bundle)
    fig_index = {}
    for it in items:
        if it.get("caption_state") == "present":
            for var in (str(it["id"]), str(it["id"]).upper()):
                fig_index.setdefault(var, it)
    absent_ids = {str(it["id"]).upper() for it in items if it.get("caption_state") != "present"}

    cits = [c if isinstance(c, dict) else {"id": c} for c in (citations or []) if c is not None]
    valid = [c for c in cits if str(c.get("id") or "").strip()]
    fig_cits = [c for c in valid if _is_figure_citation(c, fig_index)]
    fig_kind = sum(1 for c in fig_cits if c.get("kind") == "figure")
    non_fig = [c for c in valid if not _is_figure_citation(c, fig_index)]
    n_non_fig = len(non_fig)
    resolved = [(c, _resolve_figure(c, fig_index)) for c in fig_cits]
    # corrector (F.3): una cita de TEXTO sólo porta evidencia si RESUELVE a un ítem del bundle con pasaje ENTREGADO
    # (_bundle_evidence_index: (evidence_id, passage_delivered)); un id inventado o sin pasaje no rescata la afirmación.
    ev_idx = _bundle_evidence_index(bundle)

    def _ev_hit(c):
        return next((ev_idx[k] for k in _citation_keys(c) if k in ev_idx), None)

    non_fig_hits = [(c, _ev_hit(c)) for c in non_fig]
    non_fig_resolved = [(c, h) for c, h in non_fig_hits if h is not None]
    non_fig_delivered = [(c, h) for c, h in non_fig_resolved if h[1]]
    n_non_fig_unresolved = len(non_fig) - len(non_fig_resolved)

    # --- F.1 figure_id_resolves (DURO) -----------------------------------------------------------------------------
    unresolved, detail = [], []
    for c, it in resolved:
        if it is None:
            ident = str(c.get("id"))
            unresolved.append(ident)
            detail.append({"id": ident, "reason": ("caption-absent (never delivered)" if ident.strip().upper() in absent_ids
                                                   else "not-in-bundle")})
    b_res = _block(PREDICATE_FIGURE_ID_RESOLVES, not unresolved,
                   (f"{len(fig_cits)} figure citation(s), all resolve to delivered figure items" if not unresolved
                    else f"{len(unresolved)} of {len(fig_cits)} figure citation(s) do not resolve: {unresolved}"),
                   n_checked=len(fig_cits), unresolved_ids=unresolved, unresolved_detail=detail)

    # --- F.2 figure_sha_matches (DURO sólo en MISMATCH; ausencia ≠ alteración) ---------------------------------------
    checked_ids, mismatches, not_verifiable, seen = [], [], [], set()
    for c, it in resolved:
        if it is None or str(it["id"]).upper() in seen:
            continue
        seen.add(str(it["id"]).upper())
        bstate = it.get("bytes_state")
        if bstate != "verified":
            not_verifiable.append({"id": it["id"], "reason": f"bytes-state: {bstate}"})
            continue
        if cache_dir is None:
            not_verifiable.append({"id": it["id"], "reason": "no-cache-dir"})
            continue
        try:
            vc = _figures.verify_cached(cache_dir, it)
        except Exception as e:  # jamás tumba la corrida: se declara como no verificable
            not_verifiable.append({"id": it["id"], "reason": f"error: {type(e).__name__}: {str(e)[:120]}"})
            continue
        if vc.get("state") == "verified":
            checked_ids.append(it["id"])
        elif vc.get("state") == "mismatch":
            mismatches.append({"id": it["id"], "expected": vc.get("sha256_expected"), "actual": vc.get("sha256_actual")})
        else:
            not_verifiable.append({"id": it["id"], "reason": "file-missing"})
    sha_ok = False if mismatches else (True if checked_ids else None)
    b_sha = _block(PREDICATE_FIGURE_SHA_MATCHES, sha_ok,
                   (f"{len(mismatches)} cited figure(s) with ALTERED bytes (sha256 recomputed != bundle)" if mismatches
                    else f"{len(checked_ids)} cited figure(s) re-hashed and equal; {len(not_verifiable)} not verifiable (declared)"
                    if checked_ids else f"nothing checkable: {len(not_verifiable)} not verifiable (declared), none altered"),
                   n_checked=len(checked_ids), n_not_verifiable=len(not_verifiable), mismatches=mismatches,
                   not_verifiable=not_verifiable, checked_ids=checked_ids,
                   cache_dir_state="provided" if cache_dir is not None else "not-provided",
                   sha_source="sha256 recomputed at gate time (figures.verify_cached, ADR-0077)")

    # --- F.3 figure_only_not_asserted (DURO, por kinds) ----------------------------------------------------------------
    positive = absence_kind is None or absence_kind == POSITIVE_CLAIM_ABSENCE_KIND
    if not absence_provided:
        kind_state = ABSENCE_KIND_NOT_PROVIDED_STATE            # el llamador no pasó el dict ni absence_kind= (declarado)
    elif absence_kind is None:
        kind_state = "absent -> treated-as-positive (ADR-0080 conservative default)"   # el sintetizador omitió el campo
    else:
        kind_state = "declared"
    figure_only = positive and len(fig_cits) > 0 and len(non_fig_delivered) == 0
    # D.2 «may only accompany a text citation of the same paper» — MEDIDO por cita figure (informativo, no gatea):
    # ¿alguna cita de texto RESUELTA nombra el mismo paper (evidence_id del ítem figura)?
    same_paper = []
    for c, it in resolved:
        if it is None:
            continue
        pid = it.get("evidence_id")
        same_paper.append({"id": it["id"], "same_paper_text_citation": bool(pid) and any(h[0] == pid for _c, h in non_fig_resolved)})
    b_only = _block(PREDICATE_FIGURE_ONLY_NOT_ASSERTED, not figure_only,
                    ("positive claim sustained ONLY by figure citations — the figure corroborates, the text carries the "
                     "evidence (§7 figure-only NOT asserted)" + (f"; {n_non_fig} non-figure citation(s) beside it do NOT resolve "
                     "to a delivered passage (hallucinated or undelivered text does not rescue the claim)" if n_non_fig else "")
                     if figure_only
                     else "declination may rest on figures" if not positive
                     else f"positive claim with {len(non_fig_delivered)} delivered non-figure and {len(fig_cits)} figure citation(s)"),
                    positive_claim=positive, absence_kind=absence_kind, absence_kind_state=kind_state,
                    n_figure_citations=len(fig_cits), n_figure_citations_kind_figure=fig_kind,
                    n_non_figure_citations=n_non_fig, n_non_figure_citations_resolved=len(non_fig_resolved),
                    n_non_figure_citations_delivered=len(non_fig_delivered),
                    n_non_figure_citations_unresolved=n_non_fig_unresolved,
                    figure_citations_same_paper=same_paper,
                    n_figure_citations_without_same_paper_text=sum(1 for x in same_paper if not x["same_paper_text_citation"]),
                    n_citations_valid=len(valid))

    # --- F.4 figure_numerals_grounded (INFORMATIVO): el proxy numérico, medido, jamás gatea -----------------------------
    passages = _bundle_passages(bundle)
    sentences = _sentences_with_markers(text)
    by_n = {}
    for c in valid:
        try:
            by_n.setdefault(int(c.get("n")), c)
        except (TypeError, ValueError):
            pass
    fig_ids_upper = {str(it["id"]).upper() for _c, it in resolved if it is not None}
    non_fig_passages = [(str(c.get("id")), _passage_of(c, passages)) for c in valid if not _is_figure_citation(c, fig_index)]
    evaluations, n_marker_absent = [], 0
    for c, it in resolved:
        try:
            n = int(c.get("n"))
        except (TypeError, ValueError):
            n = None
        caption = it.get("caption") if (it is not None and it.get("caption_state") == "present") else None
        own = [(f"caption:{it['id']}", caption)] if caption else []
        marked = [(s, ns) for s, ns in sentences if n is not None and n in ns]
        if marked:
            state = "marker-sentence"
            numerals, sources = [], []
            for s, ns in marked:
                others = own + [(f"passage:{by_n[m].get('id')}", _passage_of(by_n[m], passages))
                                for m in sorted(ns) if m != n and m in by_n]
                for num in _numerals_of(s):
                    if num not in numerals:
                        numerals.append(num)
                sources.append(others)
        else:
            state = "no-marker: whole-answer fallback"
            n_marker_absent += 1
            numerals = _numerals_of(text)
            union = own + [(f"caption:{it2['id']}", it2.get("caption")) for _c2, it2 in resolved
                           if it2 is not None and it2 is not it and it2.get("caption_state") == "present"]
            union += [(f"passage:{cid}", ptxt) for cid, ptxt in non_fig_passages if ptxt]
            sources = [union]
        unsupported, supporting = [], []
        for num in numerals:
            hit = False
            for group in sources:
                for label, src in group:
                    if src and _numeral_in(num, src):
                        hit = True
                        if label not in supporting:
                            supporting.append(label)
            if not hit and num not in unsupported:
                unsupported.append(num)
        evaluations.append({"n": n, "id": str(c.get("id")), "state": state, "numerals": numerals,
                            "numerals_unsupported": unsupported, "supporting_sources": supporting})
    if not fig_cits:
        num_state, num_ok = "no-figure-citations", None
    elif n_marker_absent == 0:
        num_state, num_ok = "checked", all(not e["numerals_unsupported"] for e in evaluations)
    elif n_marker_absent == len(evaluations):
        num_state, num_ok = "no-markers: whole-answer fallback", all(not e["numerals_unsupported"] for e in evaluations)
    else:
        num_state = "partial-markers: whole-answer fallback for unmarked"
        num_ok = all(not e["numerals_unsupported"] for e in evaluations)
    n_unsup = sum(len(e["numerals_unsupported"]) for e in evaluations)
    b_num = _block(PREDICATE_FIGURE_NUMERALS_GROUNDED, num_ok,
                   ("no figure citations: nothing to measure" if not fig_cits
                    else f"{n_unsup} numeral(s) without caption/text backing across {len(evaluations)} figure citation(s); "
                         f"{n_marker_absent} without inline marker (measured limit)"),
                   state=num_state, n_marker_absent=n_marker_absent, n_numerals_unsupported=n_unsup, evaluations=evaluations)

    # --- F.5 figure_license_known (INFORMATIVO) --------------------------------------------------------------------------
    unknown = sorted({str(it["id"]) for _c, it in resolved if it is not None and (it.get("license") or {}).get("id") == "unknown"})
    n_lic = len({str(it["id"]) for _c, it in resolved if it is not None})
    b_lic = _block(PREDICATE_FIGURE_LICENSE_KNOWN, (None if n_lic == 0 else not unknown),
                   ("no resolved figure citation: nothing to measure" if n_lic == 0
                    else f"{len(unknown)} of {n_lic} cited figure(s) with license 'unknown' (gates embedding, not truth)"),
                   n_checked=n_lic, unknown=unknown)

    state = "checked" if fig_cits else "no-figure-citations"
    frag = {"state": state, "n_figure_citations": len(fig_cits), "n_figures_in_bundle": len(items),
            "n_figures_delivered": sum(1 for it in items if it.get("caption_state") == "present"),
            PREDICATE_FIGURE_ID_RESOLVES: b_res, PREDICATE_FIGURE_SHA_MATCHES: b_sha,
            PREDICATE_FIGURE_ONLY_NOT_ASSERTED: b_only, PREDICATE_FIGURE_NUMERALS_GROUNDED: b_num,
            PREDICATE_FIGURE_LICENSE_KNOWN: b_lic, "gating": dict(FIGURE_GATING), "rules": dict(FIGURE_RULES),
            "predicates_version": FIGURE_PREDICATES_VERSION, "decided_by": "code"}
    if state != "checked":   # sin citas figura NINGÚN predicado entra a la conjunción: admisibilidad de hoy (F)
        return frag, []
    preds = [_mk_pred(PREDICATE_FIGURE_ID_RESOLVES, b_res["ok"], b_res),
             _mk_pred(PREDICATE_FIGURE_SHA_MATCHES, not mismatches, b_sha),      # null (nada verificable) NO falla
             _mk_pred(PREDICATE_FIGURE_ONLY_NOT_ASSERTED, b_only["ok"], b_only)]
    return frag, preds


def figure_check_state_in_vocabulary(s):
    """True si `s` es un estado válido de deterministic_checks.figures.state (patrón plan_state_in_vocabulary)."""
    return s in FIGURE_CHECK_STATES_EXACT or (isinstance(s, str) and s.startswith(FIGURE_CHECK_STATES_PREFIXES))


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

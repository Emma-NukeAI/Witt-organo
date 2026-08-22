"""
calibration.py — ECE over CLOSED webapp runs, anchored on human ratings (M5 → Test 4; ADR-0064).

Tapón 4 of PENDIENTES DE BACK (HANDOFF-2026-08-22): the compute exists in
`substrate_calibration/tools/compute_ece.py` — this module REUSES it (never re-implements the binning)
and assembles its inputs from the backend DB: stated confidence from the frozen record + a human
outcome label derived from `run_ratings`.

Declared-power discipline (the whole point of the tapón): with today's ~4 real runs and 0 ratings,
n_scored is far below the ADR-0005/0030 threshold — the report SAYS so (`power.sufficient: false`,
status "infrastructure populated" / "case capture") instead of silently shipping a blind number.
`ece_raw` at n<10 is descriptive-only, exactly like compute_ece.py labels it.

Outcome mapping v1 (every rule declared in the response so the UI can render the method, not just
the number):
  - per rating: rating_output >= 4 -> positive; <= 2 -> negative; == 3 or non-value state -> abstain
  - per rater:  their LATEST rating row counts (append-only log; corrections are later rows)
  - per run:    STRICT majority over non-abstain binaries (same majority() rule as
                evaluation/scripts/score_calibration.py); tie or zero votes -> excluded, counted
  - confidence: frozen_record.confidence.final where state == "value" (recovered/derived sources
                count as values — their provenance is tallied in confidence_sources)

Instrument discipline (registro-congelado.md): aggregating across instruments or blind states is
allowed only DECLARED. This report mixes m5-cierre + m5-consenso and says so; the CSV bank
(banco_calibracion_v1, 0-2 categorical axes) is a DIFFERENT instrument and never enters here.

NO-SPEND by construction: pure DB reads + arithmetic — no embeds, no model calls, no network.
"""
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

import db  # noqa: E402

MIN_N = 10          # ADR-0005/0030 threshold: below this, no aggregate claim — descriptive only
POSITIVE_MIN = 4    # rating_output >= 4 -> positive
NEGATIVE_MAX = 2    # rating_output <= 2 -> negative; 3 abstains (neutral is not a label)

OUTCOME_MAPPING_DECL = {
    "per_rating": f"rating_output >= {POSITIVE_MIN} -> positive; <= {NEGATIVE_MAX} -> negative; "
                  "== 3 o estado no-'value' -> se abstiene (neutral no es etiqueta; "
                  "[?] no-puedo-calificar JAMAS cuenta como negativo — M5)",
    "per_rater": "cuenta la ULTIMA calificacion de cada persona (log append-only)",
    "per_run": "mayoria ESTRICTA sobre los votos binarios no-abstenidos (misma regla majority() del "
               "banco); empate o cero votos -> corrida excluida y contada",
    "confidence": "frozen_record.confidence.final con state=='value'; la procedencia "
                  "(stated/recovered/derived) se tally en confidence_sources",
    "version": "v1 (ADR-0064) — recalibrable con volumen; el mapeo viaja en la respuesta para que "
               "ningun numero circule sin su metodo",
}


def _binary(rating_row):
    """One rating row -> 1.0 / 0.0 / None (abstain)."""
    if rating_row.get("rating_output_state") != "value":
        return None
    v = rating_row.get("rating_output")
    if not isinstance(v, int):
        return None
    if v >= POSITIVE_MIN:
        return 1.0
    if v <= NEGATIVE_MAX:
        return 0.0
    return None


def _latest_by_rater(rows):
    latest = {}
    for r in rows:                     # chronological — later rows overwrite
        latest[r["rated_by"]] = r
    return list(latest.values())


def _majority_label(rows):
    """Strict majority over non-abstain binaries; None when no votes or tie."""
    votes = [b for b in (_binary(r) for r in rows) if b is not None]
    if not votes:
        return None, 0
    pos = sum(votes)
    if pos * 2 > len(votes):
        return 1.0, len(votes)
    if pos * 2 < len(votes):
        return 0.0, len(votes)
    return None, len(votes)            # tie -> excluded (counted by caller)


def _status_of(n):
    """ADR-0005/0030 test-claim language — mirrors compute_ece.py exactly."""
    if n == 0:
        return "infrastructure populated"
    return "case capture" if n < MIN_N else "aggregate-captured"


def _pairs_to_block(pairs):
    """(confidence, label) pairs -> {n, ece_raw, class} reusing compute_ece's binning."""
    block = {"n": len(pairs), "ece_raw": None,
             "class": None if pairs else "no-pairs"}
    if not pairs:
        return block
    sys.path.insert(0, str(ROOT / "substrate_calibration" / "tools"))
    import compute_ece as ece_mod      # lazy: numpy only loads when there is something to compute
    confs = [c for c, _ in pairs]
    outs = [o for _, o in pairs]
    block["ece_raw"] = round(float(ece_mod.compute_ece(confs, outs)), 4)
    block["class"] = ("aggregate" if len(pairs) >= MIN_N
                      else f"descriptive-only (n<{MIN_N} — sin poder, ADR-0005/0030)")
    if len(pairs) >= MIN_N:
        cal = ece_mod.apply_isotonic_calibration(confs, outs)
        block["ece_after_isotonic"] = round(float(ece_mod.compute_ece(cal.tolist(), outs)), 4)
    return block


def report():
    """The /calibration payload. Deterministic, NO-SPEND, self-declaring."""
    closed = db.closed_runs(limit=1000)
    n_with_conf = n_with_label = 0
    excluded = {"no_confidence": 0, "no_ratings": 0, "no_majority_or_tie": 0}
    conf_sources = {}
    instruments = {}
    pairs_all, pairs_by_profile = [], {"medico": [], "dev": []}

    for row in closed:
        try:
            rec = json.loads(row["frozen_record_json"] or "{}")
        except Exception:
            rec = {}
        conf_block = rec.get("confidence") or {}
        conf = conf_block.get("final") if conf_block.get("state") == "value" else None
        if isinstance(conf, (int, float)):
            n_with_conf += 1
            src = conf_block.get("source") or "unknown"
            conf_sources[src] = conf_sources.get(src, 0) + 1
        ratings = db.ratings_for(row["run_id"])
        for r in ratings:
            instruments[r["instrument"]] = instruments.get(r["instrument"], 0) + 1
        latest = _latest_by_rater(ratings)
        label, n_votes = _majority_label(latest)
        if label is not None:
            n_with_label += 1

        if not isinstance(conf, (int, float)):
            excluded["no_confidence"] += 1
            continue
        if not ratings:
            excluded["no_ratings"] += 1
            continue
        if label is None:
            excluded["no_majority_or_tie"] += 1
            continue
        pairs_all.append((float(conf), label))
        for profile in ("medico", "dev"):
            p_label, _ = _majority_label([r for r in latest if r["rater_profile"] == profile])
            if p_label is not None:
                pairs_by_profile[profile].append((float(conf), p_label))

    n_scored = len(pairs_all)
    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "scope": "corridas CERRADAS con registro congelado (el corpus de precedente, ADR-0053)",
        "n_closed": len(closed),
        "n_with_confidence": n_with_conf,
        "n_with_human_label": n_with_label,
        "n_scored": n_scored,
        "excluded": excluded,
        "outcome_mapping": OUTCOME_MAPPING_DECL,
        "power": {
            "n_scored": n_scored, "min_required": MIN_N, "sufficient": n_scored >= MIN_N,
            "status": _status_of(n_scored),
            "note": ("n < umbral SE DECLARA, no se calcula a ciegas (tapon 4, ADR-0064): un ECE con "
                     f"n<{MIN_N} es descriptivo y sin poder; 'satisfied' ademas exige el arco "
                     "longitudinal (ADR-0030) que este endpoint no puede atestiguar"),
        },
        "ece": _pairs_to_block(pairs_all),
        "by_rater_profile": {p: _pairs_to_block(pairs) for p, pairs in pairs_by_profile.items()},
        "by_instrument": {
            **instruments,
            "note": ("el agregado MEZCLA m5-cierre y m5-consenso — declarado aqui, jamas en silencio "
                     "(registro-congelado.md). El banco CSV (escalas categoricas 0-2) es OTRO "
                     "instrumento y NO entra en este calculo; su puerta es "
                     "evaluation/scripts/score_calibration.py"),
        },
        "confidence_sources": conf_sources,
        "cost_class": "NO-SPEND (lecturas de BD + aritmetica; cero embeds, cero modelo, cero red)",
    }

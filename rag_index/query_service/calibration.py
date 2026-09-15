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

Origin discipline (ADR-0079 F): the corpus is scoped by `runs.origin` through the SAME door as the
precedent layer (precedent.closed_runs_scoped) — by default only 'production' runs are calibrated;
smoke/simulation/fixture/replay/dev-offline runs are excluded AND COUNTED (`excluded_by_origin`), NULL
origins (born before the column) are included AND DECLARED (`origin_unknown_included`). Same
discipline as `power`: the number never travels without the scope it stands on (`origins_included`).
"""
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

import db  # noqa: E402
import precedent  # noqa: E402  (ADR-0079: ONE origin filter for both consumers — never two rules)

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
    # --- declaraciones agregadas por M5 v2 (ADR-0075). Ninguna cambia el numero titular: lo que hacen es
    # --- decir en voz alta lo que el numero SIEMPRE fue, y ofrecer al lado el bloque no contaminado.
    "axis_roles": "rating_output es el UNICO eje que se mapea a outcome. rating_input NUNCA ha entrado "
                  "al ECE — ni antes ni ahora (verificable: no aparece en este modulo); es un eje "
                  "DESCRIPTIVO. Antecedente CRUZADO DE INSTRUMENTO (hipotesis sobre M5, jamas medicion "
                  "de M5, ADR-0064 s6): en el banco CSV los tres ejes de input dieron kappa <= 0 "
                  "corregido por azar. La fiabilidad de rating_input DENTRO de M5 esta SIN MEDIR",
    "author_caveat": "una corrida calificada SOLO por su autor (m5-cierre) tiene su etiqueta decidida "
                     "por una sola persona con interes en el resultado: es autoexamen, no consenso. "
                     "NO se excluye del agregado (se declara, no se esconde), pero el bloque "
                     "by_authorship trae el ECE de m5-consenso POR SEPARADO — ese es el numero sin "
                     "autoexamen. Cuenta de corridas afectadas en raters.n_runs_author_only",
    "honest_decline": "una declinacion honesta (verdict APPROVE_DECLINE, ADR-0058) trae confianza baja "
                      "POR CONSTRUCCION y el sistema hizo lo correcto. Si el humano la califica alto, "
                      "el par entra como error maximo justo cuando no hubo error. NO se excluye del "
                      "agregado; se cuenta y se ofrece ece_excluding_declines al lado",
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


def report(include_origins=None):
    """The /calibration payload. Deterministic, NO-SPEND, self-declaring.

    ADR-0079: `include_origins` (list | CSV | None) widens the origin scope; None = default
    ('production' + NULL declared). The scope and the exclusions travel in the response
    (origins_included / excluded_by_origin / origin_unknown_included) — n_closed counts the runs
    that ENTERED the scope; the excluded ones are counted next to it, never silently dropped."""
    closed, origin_meta = precedent.closed_runs_scoped(include_origins, limit=1000)
    n_with_conf = n_with_label = 0
    excluded = {"no_confidence": 0, "no_ratings": 0, "no_majority_or_tie": 0}
    conf_sources = {}
    instruments = {}
    pairs_all, pairs_by_profile = [], {"medico": [], "dev": []}
    # M5 v2 (ADR-0075): bloques PARALELOS. El numero titular (`ece`) no cambia — cambiar en silencio una
    # cifra ya publicada seria justo lo que la casa prohibe. Lo que se agrega es el mismo calculo sobre
    # subconjuntos declarados, para que el lector vea de que descansa el titular.
    pairs_by_authorship = {"m5-consenso": [], "m5-cierre": []}
    pairs_sin_declinacion = []
    n_runs_author_only = n_runs_single_rater = n_pairs_honest_decline = 0
    raters_hist = {}

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
        # Cuantas PERSONAS distintas calificaron esta corrida, y si alguna fue alguien mas que el autor.
        # Se cuenta sobre TODAS las cerradas con calificaciones (no solo las que llegan al par): el
        # lector necesita saber de cuantas cabezas depende el numero, no de cuantos pares sobrevivieron.
        if latest:
            k = len(latest)
            raters_hist[str(k)] = raters_hist.get(str(k), 0) + 1
            if k == 1:
                n_runs_single_rater += 1
            if all(r["is_author"] for r in latest):
                n_runs_author_only += 1

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

        # --- los tres cortes declarados de M5 v2 (ADR-0075), todos sobre el MISMO par ya admitido ---
        # (1) por autoria: m5-consenso es el numero sin autoexamen; m5-cierre se reporta aparte.
        for inst in ("m5-consenso", "m5-cierre"):
            i_label, _ = _majority_label([r for r in latest if r["instrument"] == inst])
            if i_label is not None:
                pairs_by_authorship[inst].append((float(conf), i_label))
        # (2) declinacion honesta: se cuenta y se ofrece el ECE sin ella al lado.
        if (rec.get("audit") or {}).get("verdict") == "APPROVE_DECLINE":
            n_pairs_honest_decline += 1
        else:
            pairs_sin_declinacion.append((float(conf), label))

    n_scored = len(pairs_all)
    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "scope": "corridas CERRADAS con registro congelado (el corpus de precedente, ADR-0053), "
                 "acotadas por origin (ADR-0079: ver origins_included / excluded_by_origin)",
        "n_closed": len(closed),
        # --- ADR-0079 F: el alcance por origen viaja con el numero (misma disciplina que `power`) ---
        "origins_included": origin_meta["origins_included"],
        "excluded_by_origin": origin_meta["excluded_by_origin"],
        "origin_unknown_included": origin_meta["origin_unknown_included"],
        "origin_policy": origin_meta["origin_policy"],
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
        # --- M5 v2 (ADR-0075): los cortes que dicen de que descansa el titular -----------------------
        "by_authorship": {
            **{i: _pairs_to_block(p) for i, p in pairs_by_authorship.items()},
            "note": ("m5-consenso = el ECE SIN autoexamen (lo calificó alguien distinto del autor); "
                     "m5-cierre = la calificación del propio autor. Cuando sólo calificó el autor, el "
                     "titular `ece` descansa entero en autoexamen — la cuenta está en "
                     "raters.n_runs_author_only. Ninguno de los dos reemplaza al titular: se leen al lado"),
        },
        "raters": {
            "n_runs_author_only": n_runs_author_only,
            "n_runs_single_rater": n_runs_single_rater,
            "por_n_calificadores": dict(sorted(raters_hist.items())),
            "note": ("cuántas personas distintas calificaron cada corrida cerrada. Con UN calificador la "
                     "mayoría estricta es una perífrasis de esa persona: su severidad decide la etiqueta. "
                     "Medido en el banco de calibración (OTRO instrumento — antecedente, no medición de "
                     "M5): la tasa de etiquetas positivas fue 100% para dos revisores y 69% para la "
                     "tercera, un swing mayor que cualquier efecto de calibración que se quiera detectar"),
        },
        "ece_excluding_declines": {
            **_pairs_to_block(pairs_sin_declinacion),
            "n_excluded_declines": n_pairs_honest_decline,
            "note": ("el mismo ECE quitando las corridas con verdict APPROVE_DECLINE. Una declinación "
                     "honesta trae confianza baja por construcción y ES la conducta correcta: si el "
                     "humano la califica alto, el par entra al titular como error máximo sin que haya "
                     "habido error. Bloque paralelo — el titular no se toca"),
        },
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

"""
score_calibration.py — test de calibración del BANCO DE CALIBRACIÓN v1 (LATIMED × Witt).

Ingiere las hojas llenadas por el equipo médico (exportadas de Google Sheets a CSV) y computa,
de forma 100% determinista (stdlib pura — CLAUDE.md: el cómputo repetible va a un ejecutable, no
al modelo), el test de calibración de DOS ejes:

  EJE INPUT  (calibrar las PREGUNTAS)  : objetividad · en-contexto · especificidad percibida
  EJE OUTPUT (calibrar las RESPUESTAS) : correcta/útil · la usarías · (confianza IA vs juicio experto)

Métricas que produce:
  1. Cobertura de llenado (cuántas celdas de 30×N revisores).
  2. Distribución por eje (INPUT y OUTPUT), por revisor y agregada.
  3. Acuerdo inter-revisor por eje (proporción de preguntas con mayoría + acuerdo par-a-par medio).
  4. Acuerdo revisor-vs-etiqueta-intencional (¿el diseño de las preguntas coincide con la percepción
     experta?) — usa la LLAVE OCULTA (banco_llave_v1.json), que los revisores NO ven.
  5. Relación INPUT→OUTPUT (hipótesis central de Emmanuel): ¿preguntas más específicas / en-foco /
     objetivas producen mejores respuestas? — correlación de rangos (Spearman, sin numpy).
  6. Calibración anclada en humanos (ADR-0037): confianza declarada por la IA (de los records) vs
     calidad juzgada por los expertos → brecha media + preguntas SOBRE-confiadas / SUB-confiadas.
  7. Tabla por-pregunta.

Entradas:
  --key    evaluation/gold_set/banco_llave_v1.json   (llave oculta: etiquetas intencionales + confianza IA)
  --sheets <dir|glob>  carpeta o glob de CSVs llenados. Un CSV por revisor, O un CSV combinado con
                       columna 'revisor'. El id de revisor sale de esa columna, o del nombre del archivo.

Salidas:
  --out    reports/calibracion_banco_<fecha>.json   (resumen máquina-legible)
  y un resumen impreso a stdout.

Uso:
  python evaluation/scripts/score_calibration.py \
      --key evaluation/gold_set/banco_llave_v1.json \
      --sheets evaluation/gold_set/respuestas/ \
      --out reports/calibracion_banco_20260718.json

Nota: no falla si faltan columnas o hay valores en blanco; los reporta como huecos. Robusto a
acentos/mayúsculas en los valores (se normalizan).
"""
import argparse
import csv
import glob
import json
import os
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------- normalización
def _norm(s):
    """minúsculas, sin acentos, sin espacios extremos — para casar valores tecleados a mano."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    return s.strip().lower()


# Mapas de valor -> ordinal. Aceptan variantes comunes que un revisor podría teclear.
INPUT_AXES = {
    "P_objetiva": {  # objetividad: 2 objetiva / 1 parcial / 0 vaga
        "objetiva": 2, "objetivo": 2, "si objetiva": 2,
        "parcial": 1, "mas o menos": 1, "medio": 1,
        "vaga": 0, "abierta": 0, "vaga o abierta": 0, "no objetiva": 0, "subjetiva": 0,
    },
    "P_en_contexto": {  # 2 en foco / 1 exploratoria / 0 fuera de alcance
        "en foco": 2, "enfoco": 2, "en-foco": 2, "en foco (nucleo)": 2, "nucleo": 2, "central": 2,
        "exploratoria": 1, "exploratorio": 1,
        "fuera de alcance": 0, "fuera": 0, "fuera de contexto": 0, "no en contexto": 0, "off": 0,
    },
    "P_especificidad": {  # ESCALA de especificidad: 0 genérica / 1 intermedia / 2 muy específica
        "generica": 0, "general": 0,
        "intermedia": 1, "media": 1, "intermedio": 1,
        "muy especifica": 2, "especifica": 2, "especifico": 2, "muy especifico": 2,
    },
}
OUTPUT_AXES = {
    "R_correcta_util": {  # 2 sí sólida / 1 más o menos / 0 no
        "si solida": 2, "si, solida": 2, "solida": 2, "si": 2, "buena": 2,
        "mas o menos": 1, "regular": 1, "parcial": 1,
        "no": 0, "mala": 0, "incorrecta": 0,
    },
    "R_la_usarias": {  # 1 sí / 0 no
        "si": 1, "si la usaria": 1, "usaria": 1, "yes": 1,
        "no": 0, "no la usaria": 0,
    },
}
ALL_AXES = {**INPUT_AXES, **OUTPUT_AXES}


def code(axis, raw):
    """Devuelve el ordinal para el valor tecleado, o None si vacío / irreconocible."""
    n = _norm(raw)
    if not n:
        return None
    return ALL_AXES[axis].get(n)


# --------------------------------------------------------------------------- carga de hojas
def load_sheets(spec):
    """Lee CSV(s). Devuelve lista de filas dict con al menos 'id','revisor' + columnas de ejes.
    `spec` es una carpeta, un glob, o un archivo. Un CSV por revisor (revisor = nombre de archivo)
    o un CSV combinado (columna 'revisor')."""
    paths = []
    p = Path(spec)
    if p.is_dir():
        paths = sorted(glob.glob(str(p / "*.csv")))
    elif any(ch in spec for ch in "*?["):
        paths = sorted(glob.glob(spec))
    elif p.is_file():
        paths = [str(p)]
    if not paths:
        sys.exit(f"[calib] no encontré CSVs en: {spec}")
    rows = []
    for path in paths:
        default_rev = Path(path).stem  # nombre de archivo como revisor por defecto
        with open(path, encoding="utf-8-sig", newline="") as f:
            rdr = csv.DictReader(f)
            for r in rdr:
                r = { (k or "").strip(): v for k, v in r.items() }
                qid = (r.get("id") or "").strip().upper()
                if not qid or not qid.startswith("Q"):
                    continue
                rev = (r.get("revisor") or "").strip() or default_rev
                r["_qid"] = qid
                r["_rev"] = rev
                rows.append(r)
    return rows, paths


# --------------------------------------------------------------------------- estadística sin numpy
def spearman(pairs):
    """Correlación de rangos de Spearman sobre lista de (x,y). None si <3 puntos o varianza nula."""
    pts = [(x, y) for x, y in pairs if x is not None and y is not None]
    if len(pts) < 3:
        return None
    xs = [x for x, _ in pts]
    ys = [y for _, y in pts]

    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        rk = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                rk[order[k]] = avg
            i = j + 1
        return rk

    rx, ry = ranks(xs), ranks(ys)
    n = len(pts)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = sum((rx[i] - mx) ** 2 for i in range(n))
    dy = sum((ry[i] - my) ** 2 for i in range(n))
    if dx == 0 or dy == 0:
        return None
    return round(num / (dx * dy) ** 0.5, 3)


def pairwise_agreement(codes):
    """Proporción de pares de revisores que coinciden EXACTAMENTE. codes = lista de ordinales (no None)."""
    cs = [c for c in codes if c is not None]
    if len(cs) < 2:
        return None
    agree = tot = 0
    for i in range(len(cs)):
        for j in range(i + 1, len(cs)):
            tot += 1
            agree += 1 if cs[i] == cs[j] else 0
    return agree / tot if tot else None


def majority(codes):
    cs = [c for c in codes if c is not None]
    if not cs:
        return None
    c = Counter(cs)
    top, n = c.most_common(1)[0]
    return top if n > len(cs) / 2 else None  # mayoría estricta


# --------------------------------------------------------------------------- núcleo
def analyze(rows, key):
    kq = {k["id"]: k for k in key["questions"]}
    revisers = sorted({r["_rev"] for r in rows})
    qids = sorted(kq.keys(), key=lambda x: int(x[1:]))

    # index: (qid, rev) -> row
    idx = {}
    for r in rows:
        idx[(r["_qid"], r["_rev"])] = r

    # ---- cobertura
    filled = defaultdict(int)
    for (qid, rev), r in idx.items():
        for axis in ALL_AXES:
            if code(axis, r.get(axis)) is not None:
                filled[axis] += 1
    n_cells = len(qids) * len(revisers)

    # ---- distribuciones agregadas por eje
    dist = {}
    for axis in ALL_AXES:
        c = Counter()
        for r in rows:
            v = code(axis, r.get(axis))
            if v is not None:
                c[v] += 1
        dist[axis] = dict(c)

    # ---- acuerdo inter-revisor por eje + por pregunta
    inter = {}
    for axis in ALL_AXES:
        per_q_pw, has_majority = [], 0
        n_q_scored = 0
        for qid in qids:
            codes = [code(axis, idx[(qid, rev)].get(axis)) for rev in revisers if (qid, rev) in idx]
            codes = [c for c in codes if c is not None]
            if len(codes) >= 2:
                n_q_scored += 1
                pw = pairwise_agreement(codes)
                if pw is not None:
                    per_q_pw.append(pw)
                if majority(codes) is not None:
                    has_majority += 1
        inter[axis] = {
            "mean_pairwise_agreement": round(statistics.mean(per_q_pw), 3) if per_q_pw else None,
            "pct_questions_with_majority": round(100 * has_majority / n_q_scored, 1) if n_q_scored else None,
            "n_questions_scored_by_2plus": n_q_scored,
        }

    # ---- revisor vs etiqueta intencional (INPUT: objetividad/contexto/especificidad)
    LABEL_TO_CODE = {
        "P_objetiva": {"objetiva": 2, "parcial": 1, "abierta": 0, "vaga": 0},
        "P_en_contexto": {"en_foco": 2, "exploratoria": 1, "fuera_de_alcance": 0},
        "P_especificidad": {"generica": 0, "intermedia": 1, "especifica": 2},
    }
    INTENDED_KEY = {"P_objetiva": "objetividad", "P_en_contexto": "contexto", "P_especificidad": "especificidad"}
    vs_intended = {}
    for axis, keyname in INTENDED_KEY.items():
        match = total = 0
        per_q = {}
        for qid in qids:
            intended_lbl = kq[qid]["intended_labels"][keyname]
            intended_code = LABEL_TO_CODE[axis].get(intended_lbl)
            codes = [code(axis, idx[(qid, rev)].get(axis)) for rev in revisers if (qid, rev) in idx]
            codes = [c for c in codes if c is not None]
            if not codes or intended_code is None:
                continue
            maj = majority(codes)
            q_match = (maj == intended_code) if maj is not None else None
            per_q[qid] = {"intended": intended_lbl, "intended_code": intended_code,
                          "reviewer_majority_code": maj, "match": q_match}
            if q_match is not None:
                total += 1
                match += 1 if q_match else 0
        vs_intended[axis] = {"pct_majority_matches_intended": round(100 * match / total, 1) if total else None,
                             "n_compared": total, "per_question": per_q}

    # ---- INPUT -> OUTPUT (hipótesis central): mean(perceived axis) vs mean(quality) por pregunta
    def mean_axis(qid, axis):
        vals = [code(axis, idx[(qid, rev)].get(axis)) for rev in revisers if (qid, rev) in idx]
        vals = [v for v in vals if v is not None]
        return statistics.mean(vals) if vals else None

    quality_by_q = {qid: mean_axis(qid, "R_correcta_util") for qid in qids}
    input_output = {}
    for axis in INPUT_AXES:
        pairs = [(mean_axis(qid, axis), quality_by_q[qid]) for qid in qids]
        input_output[axis] = {
            "spearman_vs_quality": spearman(pairs),
            "interpretation": "correlación de rangos entre el eje de la PREGUNTA percibido y la calidad de la RESPUESTA (R_correcta_util). Positiva alta ⇒ ese atributo de la pregunta predice mejor respuesta.",
        }

    # ---- calibración anclada en humanos: confianza IA (llave) vs calidad experta
    calib = {"per_question": {}, "overconfident": [], "underconfident": [], "well_calibrated": []}
    gaps = []
    for qid in qids:
        ia = kq[qid].get("ia_confidence")
        q = quality_by_q[qid]
        if ia is None or q is None:
            calib["per_question"][qid] = {"ia_confidence": ia, "expert_quality_0_1": None if q is None else round(q / 2, 3), "gap": None}
            continue
        eq = q / 2.0  # normaliza 0..2 -> 0..1
        gap = ia - eq
        gaps.append(abs(gap))
        entry = {"ia_confidence": ia, "expert_quality_0_1": round(eq, 3), "gap": round(gap, 3)}
        calib["per_question"][qid] = entry
        if gap >= 0.25:
            calib["overconfident"].append(qid)   # IA se declaró más segura de lo que el experto valida
        elif gap <= -0.25:
            calib["underconfident"].append(qid)   # IA se sub-declaró; el experto la valida más
        else:
            calib["well_calibrated"].append(qid)
    calib["mean_abs_gap"] = round(statistics.mean(gaps), 3) if gaps else None
    calib["note"] = ("Ancla humana (ADR-0037): la confianza de la IA es AUTO-REPORTE; la calidad experta es el "
                     "gold-set humano. gap = ia_confidence - calidad_experta_normalizada. |gap| pequeño ⇒ bien "
                     "calibrada. gap>0 ⇒ sobre-confianza; gap<0 ⇒ sub-confianza.")

    # ---- tabla por pregunta
    per_q_table = []
    for qid in qids:
        per_q_table.append({
            "id": qid,
            "tema": kq[qid].get("tema"),
            "intended": kq[qid]["intended_labels"],
            "ia_confidence": kq[qid].get("ia_confidence"),
            "perceived": {ax: round(mean_axis(qid, ax), 2) if mean_axis(qid, ax) is not None else None
                          for ax in INPUT_AXES},
            "quality_mean": round(quality_by_q[qid], 2) if quality_by_q[qid] is not None else None,
            "would_use_mean": round(mean_axis(qid, "R_la_usarias"), 2) if mean_axis(qid, "R_la_usarias") is not None else None,
        })

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_reviewers": len(revisers), "reviewers": revisers, "n_questions": len(qids),
        "coverage": {"cells_per_axis_filled": dict(filled), "cells_expected_per_axis": n_cells,
                     "pct_by_axis": {ax: round(100 * filled[ax] / n_cells, 1) if n_cells else None for ax in ALL_AXES}},
        "distributions": dist,
        "inter_reviewer_agreement": inter,
        "reviewer_vs_intended_design": vs_intended,
        "input_to_output_hypothesis": input_output,
        "human_anchored_calibration": calib,
        "per_question": per_q_table,
    }


def print_summary(res):
    def _reconfig():
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    _reconfig()
    print("\n" + "=" * 66)
    print(f"TEST DE CALIBRACIÓN — Banco v1  ·  {res['n_reviewers']} revisores · {res['n_questions']} preguntas")
    print("=" * 66)
    cov = res["coverage"]["pct_by_axis"]
    print("\n[1] Cobertura de llenado (% de celdas):")
    for ax, pct in cov.items():
        print(f"    {ax:18} {pct}%")
    print("\n[3] Acuerdo inter-revisor:")
    for ax, d in res["inter_reviewer_agreement"].items():
        print(f"    {ax:18} par-a-par={d['mean_pairwise_agreement']}  mayoría={d['pct_questions_with_majority']}%  (n={d['n_questions_scored_by_2plus']})")
    print("\n[4] Diseño de preguntas vs percepción experta (¿nuestras etiquetas coinciden?):")
    for ax, d in res["reviewer_vs_intended_design"].items():
        print(f"    {ax:18} coincide con lo intencional: {d['pct_majority_matches_intended']}%  (n={d['n_compared']})")
    print("\n[5] INPUT→OUTPUT (¿la pregunta predice la calidad de la respuesta?) — Spearman:")
    for ax, d in res["input_to_output_hypothesis"].items():
        print(f"    {ax:18} ρ = {d['spearman_vs_quality']}")
    c = res["human_anchored_calibration"]
    print("\n[6] Calibración anclada en humanos (confianza IA vs juicio experto):")
    print(f"    brecha |gap| media = {c['mean_abs_gap']}")
    print(f"    SOBRE-confiadas: {c['overconfident']}")
    print(f"    SUB-confiadas:   {c['underconfident']}")
    print(f"    bien calibradas: {len(c['well_calibrated'])} preguntas")
    print("\n(resumen completo en el JSON de salida)\n")


def main():
    ap = argparse.ArgumentParser(description="Test de calibración del banco (INPUT preguntas + OUTPUT respuestas).")
    ap.add_argument("--key", default="evaluation/gold_set/banco_llave_v1.json",
                    help="llave oculta (etiquetas intencionales + confianza IA)")
    ap.add_argument("--sheets", required=True, help="carpeta / glob / archivo de CSVs llenados por los revisores")
    ap.add_argument("--out", default=None, help="ruta del JSON de salida (default: reports/calibracion_banco_<fecha>.json)")
    args = ap.parse_args()

    key = json.loads(Path(args.key).read_text(encoding="utf-8"))
    rows, paths = load_sheets(args.sheets)
    res = analyze(rows, key)
    res["input_files"] = paths

    out = args.out or f"reports/calibracion_banco_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print_summary(res)
    print(f"[calib] escrito -> {out}  (leídos {len(paths)} archivo(s), {len(rows)} filas)")


if __name__ == "__main__":
    main()

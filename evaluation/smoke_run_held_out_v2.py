"""smoke_run_held_out_v2.py — gate determinista del harness held-out v2 (ADR-0072).

Cubre: la BD del harness FORZADA (un WITT_BACKEND_DB_URL de producción en el shell jamás captura
corridas de eval), la ejecución por el run model REAL (el récord sale INSTRUMENTADO: decision_state
+ confianza con procedencia + veredicto del panel del run), el outcome determinista desde el gate
del propio run, el juez advisory inyectable con sus literales, el modo di-only a prueba de fugas
(las funciones de búsqueda externa REVIENTAN si alguien las llama — y nadie las llama), el récord
honesto de una corrida muerta, compute_ece consumiendo el set, y el builder de pares EPS.

100% offline: sintetizador/panel/juez inyectados, retrieval stubbeado — cero red, cero spend.
Corre:  python evaluation/smoke_run_held_out_v2.py   (venv del servicio, NO el del MCP)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = Path(tempfile.mkdtemp(prefix="smoke_heldout_v2_"))
# simular un shell CONTAMINADO con la BD de producción ANTES de importar el harness:
os.environ["WITT_BACKEND_DB_URL"] = "postgresql+psycopg://SIMULA-PRODUCCION/witt"
os.environ["WITT_EVAL_DB_URL"] = f"sqlite:///{TMP / 'eval.db'}"
os.environ.pop("NEO4J_URI", None)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_held_out_v2 as v2  # noqa: E402  (fuerza la BD al importar)

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


check("BD FORZADA: el WITT_BACKEND_DB_URL 'de producción' del shell quedó reemplazado por la de eval",
      os.environ["WITT_BACKEND_DB_URL"] == f"sqlite:///{TMP / 'eval.db'}")

v1, db, runs_mod, answer_pipeline = v2._boot("sparse")
os.environ.pop("NEO4J_URI", None)   # deploy.env pudo re-sembrarlo via setdefault

check("usuario eval-harness sembrado SOLO en la BD de eval",
      "eval-harness" in {u["user_id"] for u in db.list_users()})

# ---- stubs deterministas (mismo patrón que smoke_run_pipeline) ----------------------------------------
from lib.rag_backend import Hit, HitList  # noqa: E402

_chunk = Hit(doc_id="CORPUS-2026-0003#c000", type="chunk", score=0.9,
             text="wt1a ENSDARG00000031420 pronephros evidence", metadata={})


def _caller_ok(member, system, user_text):
    return ({"verdict": "APPROVE", "caught": "", "correction_applied": "",
             "confidence": 0.9, "reasons": []}, {"input_tokens": 10, "output_tokens": 5})


def _mk_synth(conf, answer_text="wt1a (ENSDARG00000031420) marks the pronephros."):
    def _s(question, evidence, pass_label):
        return {"direct_answer": answer_text, "stated_confidence": conf,
                "confidence_by_subclaim": None, "absence_kind": "not-applicable",
                "gap_flags": [], "evidence_cited": [{"kind": "di-chunk", "id": "CORPUS-2026-0003#c000"}],
                "alternatives_considered": ["x"], "framework_applied": "Logic-LM",
                "framework_criterion": "for any task whose criteria are formalizable",
                "framework_reason": "smoke", "model": "stub-synth",
                "usage": {"input_tokens": 100, "output_tokens": 50}}
    return _s


def _judge_pos(q, contract):
    return {"outcome": "positive", "mean_overall": 0.8, "label_disagreement": 0.0,
            "verdicts": [{"provider": "stub", "model": "stub-judge", "verdict": "correct"}]}


import lib.answer_pipeline as ap  # noqa: E402
ap.path_b = lambda q, n=2, **kw: []
from lib import rag_backend  # noqa: E402
rag_backend.query = lambda text, k=6: HitList([_chunk], degraded=None)
rag_backend.query_sparse = lambda text, k=6: HitList([_chunk], degraded=None)

Q_ID = {"id": "QS1", "niche": ["RN1"], "system": "pronephros", "type": "marker_identification",
        "q": "Which TF marks the pronephros?", "expected_evidence": "wt1a"}
Q_OPEN = {"id": "QS2", "niche": ["RN3"], "system": "pronephros", "type": "mechanism",
          "q": "How does RA position the field?", "expected_evidence": "RA gradient"}

# ---- 1. la pregunta corre por el RUN MODEL y el récord sale INSTRUMENTADO ------------------------------
rec, frozen, run, panel = v2.run_question(v1, db, runs_mod, Q_ID, "smoke_set", "di+structured",
                                          model_cutoff="atestiguado-en-smoke",
                                          synthesizer=_mk_synth(0.8), panel_caller=_caller_ok,
                                          judge_fn=_judge_pos)
check("el récord lleva el RUN MODEL completo: decision_state + run_id + contrato 1.6 (v1 no podía)",
      rec["decision_state"]["state"] == "AUDIT_APPROVED" and len(rec["run_id"]) == 32
      and rec["render_contract_version"] == "1.6" and rec["audit"]["verdict"] == "APPROVE")
check("la confianza viaja CON su procedencia (bloque completo ADR-0057/0065) + escalar para compute_ece",
      rec["stated_confidence"] == 0.8 and rec["confidence"]["final"] == 0.8
      and "source" in rec["confidence"] and rec["confidence"]["state"] == "value")
check("outcome determinista DEL GATE DEL PROPIO RUN (ID_TYPES + admisible -> positive, store-grounded)",
      rec["observed_outcome"] == "positive"
      and rec["scoring"]["primary_signal"] == "store-grounded-deterministic"
      and "propio run" in rec["scoring"]["deterministic"]["source"])
check("EVAL_DESIGN en el récord: sources_mode + model_cutoff ATESTIGUADO + harness_version",
      rec["eval"]["sources_mode"] == "di+structured"
      and rec["eval"]["model_cutoff"] == "atestiguado-en-smoke"
      and "run-model" in rec["eval"]["harness_version"])
check("gasto MEDIDO por pregunta en el récord (token_usage del run)",
      rec["token_usage"]["by_model"]["stub-synth"]["in"] >= 100)

# ---- 2. pregunta abierta: el juez ADVISORY decide, con sus literales -----------------------------------
rec2, _, _, panel2 = v2.run_question(v1, db, runs_mod, Q_OPEN, "smoke_set", "di+structured",
                                     synthesizer=_mk_synth(0.6, "RA positions the field."),
                                     panel_caller=_caller_ok, judge_fn=_judge_pos)
check("pregunta abierta: deterministic=None -> outcome del juez, marcado ADVISORY jamás ground truth",
      rec2["scoring"]["deterministic"] is None and rec2["observed_outcome"] == "positive"
      and "NOT ground truth" in rec2["scoring"]["primary_signal"]
      and panel2["verdicts"][0]["model"] == "stub-judge")

# ---- 3. di-only A PRUEBA DE FUGAS: las búsquedas externas revientan si alguien las llama ---------------
def _boom(*a, **kw):
    raise AssertionError("FUGA: una búsqueda externa corrió en modo di-only")


ap._search_pubmed, ap._search_zfin, ap._search_tooluniverse = _boom, _boom, _boom
ap._search_europepmc = _boom if hasattr(ap, "_search_europepmc") else None
rag_backend.query = lambda text, k=6: HitList([], degraded=None)   # 0 hits -> dispara estructural
orig_pb = v2._patch_sources(ap, "di-only")
try:
    rec3, frozen3, _, _ = v2.run_question(v1, db, runs_mod, Q_OPEN, "smoke_set", "di-only",
                                          synthesizer=_mk_synth(0.3, "thin evidence."),
                                          panel_caller=_caller_ok, judge_fn=_judge_pos)
    fuga = False
except AssertionError:
    fuga, rec3, frozen3 = True, None, None
finally:
    if orig_pb is not None:
        ap.path_b_bundle = orig_pb
    rag_backend.query = lambda text, k=6: HitList([_chunk], degraded=None)
check("di-only: la Ruta B disparó (estructural + confianza 0.3<tau) y NINGUNA búsqueda externa corrió",
      fuga is False and rec3 is not None
      and frozen3["fallback"]["trigger"] is not None
      and frozen3["decision_state"]["state"] in ("AUDIT_APPROVED", "AUDIT_REJECTED")
      and rec3["eval"]["sources_mode"] == "di-only")

# ---- 4. corrida muerta -> récord honesto (excluida, contada) -------------------------------------------
def _synth_boom(question, evidence, pass_label):
    raise ValueError("synth exploded (smoke)")


rec4, frozen4, run4, _ = v2.run_question(v1, db, runs_mod, Q_OPEN, "smoke_set", "di+structured",
                                         synthesizer=_synth_boom, panel_caller=_caller_ok,
                                         judge_fn=_judge_pos)
check("corrida failed -> récord honesto sin outcome fabricado (excluida de calibración, contada)",
      frozen4 is None and rec4["run_state"] == "failed" and rec4["observed_outcome"] is None
      and "excluida" in rec4["note"])

# ---- 5. compute_ece consume el set del v2 --------------------------------------------------------------
SET_DIR = TMP / "set"
SET_DIR.mkdir()
(SET_DIR / "QS1.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
(SET_DIR / "QS2.json").write_text(json.dumps(rec2, ensure_ascii=False), encoding="utf-8")
sys.path.insert(0, str(v2.ROOT / "substrate_calibration" / "tools"))
import compute_ece  # noqa: E402

records = compute_ece.load_records(str(SET_DIR))
observable = compute_ece.filter_observable(records)
labeled = [compute_ece.outcome_to_label(r.get("observed_outcome")) for r in observable]
check("compute_ece consume los récords v2 (stated_confidence + observed_outcome mapeables)",
      len(records) == 2 and len(observable) == 2 and labeled == [1.0, 1.0]
      and all(isinstance(r.get("stated_confidence"), float) for r in observable))

# ---- 6. builder de pares EPS ----------------------------------------------------------------------------
raw_dir = v2.RUNS_DIR / "smoke_eps_tmp" / "_raw"
raw_dir.mkdir(parents=True, exist_ok=True)
for r_i in (1, 2):
    (raw_dir / f"run{r_i}_QS1.json").write_text(json.dumps(
        {"run_id": f"r{r_i}", "frozen": frozen,
         "path_a_doc_ids": ["CORPUS-2026-0003#c000"]}, ensure_ascii=False), encoding="utf-8")
import argparse as _ap  # noqa: E402

try:
    v2.cmd_eps(_ap.Namespace(set="smoke_eps_tmp", axis_c="lexical"))
    eps_out = json.loads((v2.RUNS_DIR / "smoke_eps_tmp" / "eps_v2.json").read_text(encoding="utf-8"))
    eps_ok = eps_out["n_pairs"] == 1 and "axes" in eps_out
except Exception as e:
    eps_ok = False
    print("   eps error:", e)
finally:
    import shutil
    shutil.rmtree(v2.RUNS_DIR / "smoke_eps_tmp", ignore_errors=True)
check("EPS v2: los pares se construyen desde los raws del run model y noise_probe los consume", eps_ok)

npass = sum(CHECKS)
print("\n== %d/%d PASS ==" % (npass, len(CHECKS)))
sys.exit(0 if npass == len(CHECKS) else 1)

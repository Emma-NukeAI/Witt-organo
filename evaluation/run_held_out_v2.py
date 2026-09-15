"""
run_held_out_v2.py — el harness held-out MIGRADO AL RUN MODEL (ADR-0072).

El v1 (run_held_out.py) "saltaba la máquina de estados" (faltantes §5.6): llamaba path_a /
check_entities / assess_sufficiency por separado y armaba su propio bundle SIN decision_state — por
eso los ~30 registros históricos de evaluation/runs/ salen `instrumented: false` en la webapp. El v2
ejecuta cada pregunta por `runs.execute_run` — LA máquina de estados real de producción completa:

    retrieve (Path A → suficiencia → Ruta B multi-fuente) → pass1 DI-only → decisor por confianza →
    pass2 → elicitación dedicada del escalar (ADR-0065) → gate determinista → panel de 4 jueces
    (ADR-0049) → ciclo de revisión acotado (ADR-0067) → registro congelado (contrato 1.6)

Con eso, Tapón 5 (evals periódicas como gate del código de producción) tiene su instrumento: lo que
se evalúa ES el pipeline que corre en producción, no una réplica.

Qué se conserva del v1 (REUSADO por import, jamás re-implementado): la carga del set congelado, la
extracción de entidades sin fuga (solo símbolos de la pregunta que resuelven en el store), el juez
multi-proveedor ADVISORY (ADR-0031/0038: Opus+Sonnet+Haiku+gpt-4o, chequeo determinista entregado a  # models-literal-doc
los jueces, outcome con guardas de desacuerdo/abstención) y el esquema de claim-record que
compute_ece.py consume. Qué cambia: la síntesis/confianza/gate/panel vienen DEL RUN (el registro
congelado, con procedencia ADR-0065), no de un camino paralelo.

Disciplina EVAL_DESIGN (F5, ADR-0068):
  - `--sources di-only | di+structured` DECLARADO por corrida: di-only parchea
    `answer_pipeline.path_b_bundle` con `sources=()` (la Ruta B dispara pero no busca NADA externo —
    cero fuga); di+structured = el pipeline real (EPMC/PubMed/ZFIN: APIs estructuradas, no web
    abierta — el pipeline no tiene herramienta de web abierta).
  - `--model-cutoff` se REGISTRA en cada récord (atestiguado por el operador; default
    "not-declared" honesto).
  - El juez sigue siendo llm-judge-advisory, JAMÁS ground truth (ADR-0037).

Seguridad de BD (estructural): la BD del harness se FUERZA a `evaluation/eval_runs.db` (local,
gitignored) — un `WITT_BACKEND_DB_URL` de producción presente en el shell NUNCA puede filtrarse;
override explícito solo vía `WITT_EVAL_DB_URL`. Las corridas de eval no entran al corpus de
precedente de producción por construcción (viven en otra BD y no se cierran).

CLI:
    # smoke NO-SPEND (sin API key): ver smoke_run_held_out_v2.py (sintetizador/panel/juez inyectados)
    # piloto vivo (gasto autorizado ~$0.25-0.5/pregunta con panel; el usage MEDIDO queda en el récord):
    python evaluation/run_held_out_v2.py run --set month_p1 --questions Q01,Q26 --backend neo4j \
        --sources di+structured --model-cutoff "<cutoff del modelo, atestiguado>"
    # baseline completo (30 Q) + EPS con corridas pareadas:
    python evaluation/run_held_out_v2.py run --set month_N --backend neo4j --runs 2
    python evaluation/run_held_out_v2.py eps --set month_N
    # ECE (mismo consumidor de siempre):
    python substrate_calibration/tools/compute_ece.py --records-dir evaluation/runs/<set> --output ...
"""
import argparse
import functools
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "evaluation" / "runs"
HARNESS_VERSION = "run_held_out-2.0 (run-model, ADR-0072)"

# La BD del harness se FUERZA (no setdefault): un WITT_BACKEND_DB_URL de producción en el shell
# jamás puede capturar las corridas de eval. Override explícito SOLO vía WITT_EVAL_DB_URL.
os.environ["WITT_BACKEND_DB_URL"] = os.environ.get(
    "WITT_EVAL_DB_URL", f"sqlite:///{ROOT / 'evaluation' / 'eval_runs.db'}")
# ADR-0079: toda corrida del harness nace con origin 'replay' — el precedente, /calibration y el consejo
# la EXCLUYEN por default y lo declaran; una corrida de eval jamás se confunde con una de producción.
# Se fuerza (no setdefault) por la misma razón que la BD: el shell no decide la procedencia.
os.environ["WITT_RUN_ORIGIN"] = "replay"

sys.path.insert(0, str(ROOT / "rag_index" / "query_service"))
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
sys.path.insert(0, str(ROOT / "evaluation"))

ID_TYPES = {"marker_identification", "ortholog_mapping", "specificity_ratio"}


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _boot(backend):
    """Env del backend ANTES de importar la cadena (mismo orden que los smokes): sparse = NO-SPEND
    offline; neo4j = store hosteado con embeddings OpenAI (el pin ADR-0039)."""
    import run_held_out as v1
    v1._load_secrets()
    os.environ["RAG_BACKEND"] = backend
    if backend == "neo4j":
        os.environ["EMBED_MODEL"] = "openai"
    else:
        os.environ.pop("NEO4J_URI", None)
    import db
    import runs as runs_mod
    from lib import answer_pipeline
    db.init_db()
    if "eval-harness" not in {u["user_id"] for u in db.list_users()}:
        import secrets as _s
        db.upsert_user("eval-harness", "Eval Harness", "dev", _s.token_urlsafe(16))
    return v1, db, runs_mod, answer_pipeline


def _patch_sources(answer_pipeline, sources_mode):
    """di-only (EVAL_DESIGN §1): la Ruta B puede DISPARAR pero no busca nada externo — cero fuga.
    Parchea AMBOS sitios de disparo de una vez (path_b_bundle es el constructor único, LOTE-03·1)."""
    if sources_mode != "di-only":
        return None
    orig = answer_pipeline.path_b_bundle
    answer_pipeline.path_b_bundle = functools.partial(orig, sources=())
    return orig


def _deterministic_outcome(q, frozen):
    """El outcome store-grounded para preguntas de identificadores — DEL GATE DEL PROPIO RUN
    (deterministic_checks ya corrió verify_output sobre la respuesta final): el run es el
    instrumento, no se re-corre un gate paralelo (diferencia declarada vs v1, que recomputaba
    con identifier_bindings)."""
    checks = frozen.get("deterministic_checks") or {}
    rep = checks.get("identifier_report") or {}
    has_ids = any(rep.get(k) for k in ("verified_raw", "verified_derived", "unresolved",
                                       "reingest_candidates", "misbound"))
    if q["type"] not in ID_TYPES or not has_ids:
        return None
    adm = bool(checks.get("admissible"))
    return {"admissible": adm, "outcome": "positive" if adm else "negative",
            "source": "run.deterministic_checks (el gate del propio run, ADR-0072)",
            "report": rep, "reasons": checks.get("reasons", [])}


def _contract_view(frozen):
    """La vista que el juez v1 espera, derivada del registro congelado."""
    ans = frozen.get("answer") or {}
    conf = (frozen.get("confidence") or {}).get("final")
    cits = [f"{c.get('kind')}:{c.get('id')}" for c in (frozen.get("citations") or [])]
    return {"direct_answer": ans.get("direct_answer", ""), "confidence": conf,
            "evidence_cited": cits, "gap_flags": ans.get("gap_flags", [])}


def make_record(q, set_name, frozen, run_id, deterministic, panel, sources_mode, model_cutoff):
    """Claim-record compatible con compute_ece + los campos del run model (INSTRUMENTADO: lleva
    decision_state — los históricos v1 no lo tienen y la webapp los marca instrumented:false)."""
    conf_block = frozen.get("confidence") or {}
    primary = deterministic["outcome"] if deterministic else (panel["outcome"] if panel else None)
    primary_signal = ("store-grounded-deterministic" if deterministic
                      else "llm-judge-advisory (NOT ground truth)" if panel else "unscored")
    niche = q.get("niche", ["unspecified"])
    return {
        "claim_id": f"held_out_{set_name}_{q['id']}",
        "claim_timestamp": _now_iso(),
        "session_id": f"evaluation/runs/{set_name} ({HARNESS_VERSION})",
        "skill_origin": "held-out-runner-v2",
        "skill_version": HARNESS_VERSION,
        "stream": "biomedical",
        "sub_domain": niche[0] if isinstance(niche, list) and niche else "unspecified",
        "claim_category": q["type"],
        "question_id": q["id"],
        "question": q["q"],
        # --- del RUN MODEL (lo que el v1 no podía dar) --------------------------------------------
        "run_id": run_id,
        "decision_state": frozen.get("decision_state"),
        "render_contract_version": frozen.get("render_contract_version"),
        "confidence": conf_block,                      # procedencia completa (ADR-0057/0065/0067)
        "fallback": frozen.get("fallback"),
        "audit": {k: (frozen.get("audit") or {}).get(k)
                  for k in ("verdict", "n_valid", "tally", "source_vocabulary")},
        "revision": frozen.get("revision"),
        "retrieval_summary": frozen.get("retrieval_summary"),
        "token_usage": frozen.get("token_usage"),      # gasto MEDIDO por pregunta (M8-grade)
        # --- lo que compute_ece consume ------------------------------------------------------------
        "direct_answer": (frozen.get("answer") or {}).get("direct_answer"),
        "stated_confidence": conf_block.get("final"),
        "prior": conf_block.get("final"),
        "gap_flags": (frozen.get("answer") or {}).get("gap_flags", []),
        "alternatives_considered": frozen.get("alternatives_considered"),
        "observed_outcome": primary,
        "observed_at": _now_iso() if primary else None,
        "scoring": {"method": ("both (deterministic primary + judge advisory)" if deterministic and panel
                               else "deterministic-store" if deterministic
                               else "judge-panel (advisory)" if panel else "unscored"),
                    "primary_signal": primary_signal,
                    "deterministic": deterministic, "panel_outcome": (panel or {}).get("outcome")},
        "test_mapping": ["test_1", "test_3", "test_4"],
        # --- EVAL_DESIGN (F5): las condiciones de la eval viajan EN el récord ----------------------
        "eval": {"harness_version": HARNESS_VERSION, "sources_mode": sources_mode,
                 "model_cutoff": model_cutoff, "set": set_name,
                 "leakage_note": ("di-only: cero búsqueda externa (fuentes parcheadas a ()); "
                                  "di+structured: EPMC/PubMed/ZFIN (APIs estructuradas — el pipeline "
                                  "no tiene web abierta)")},
        "agents_invoked": [
            {"agent": "answer_pipeline + runs.execute_run (la máquina de estados de producción)",
             "status": "invoked", "invocation_id": run_id,
             "evidence_generated": ["test_1", "test_3"]},
            {"agent": "composite-auditor (panel del run, ADR-0049)", "status": "invoked",
             "invocation_id": f"run:{run_id}",
             "evidence_generated": [f"verdict:{(frozen.get('audit') or {}).get('verdict')}"]},
            {"agent": "judge-panel v1 (advisory, ADR-0031/0038)",
             "status": "invoked" if panel else "skipped-ad-hoc",
             "reason": "outcome advisory para calibración" if panel else "sin juez (--no-judge)"},
        ],
    }


def run_question(v1, db, runs_mod, q, set_name, sources_mode, model_cutoff="not-declared",
                 synthesizer=None, panel_caller=None, judge_fn=None, no_judge=False):
    """UNA pregunta por el run model. synthesizer/panel_caller/judge_fn inyectables (el smoke los
    stubbea; None = vivo). Devuelve (record, frozen|None, run_row)."""
    ents = v1.extract_entities(q["q"])
    rid = runs_mod.new_run("eval-harness", q["q"], entities=ents)
    claimed = db.claim_next_queued()
    assert claimed and claimed["run_id"] == rid, f"claim falló para {q['id']}"
    runs_mod.execute_run(claimed, synthesizer=synthesizer, panel_caller=panel_caller)
    run = db.get_run(rid)
    if run["state"] != "awaiting_closure" or not run.get("frozen_record_json"):
        # honesto: la corrida murió — el récord lo dice, jamás se fabrica un resultado
        rec = {"claim_id": f"held_out_{set_name}_ERR_{q['id']}", "question_id": q["id"],
               "question": q["q"], "run_id": rid, "run_state": run["state"],
               "error": run.get("error"), "stated_confidence": None, "observed_outcome": None,
               "eval": {"harness_version": HARNESS_VERSION, "sources_mode": sources_mode,
                        "model_cutoff": model_cutoff, "set": set_name},
               "note": "corrida failed/cancelled — excluida de calibración, contada en el resumen"}
        return rec, None, run, None
    frozen = json.loads(run["frozen_record_json"])
    deterministic = _deterministic_outcome(q, frozen)
    panel = None
    if not no_judge:
        judge = judge_fn or v1.judge_answer
        panel = judge(q, _contract_view(frozen))
    rec = make_record(q, set_name, frozen, rid, deterministic, panel, sources_mode, model_cutoff)
    return rec, frozen, run, panel


def cmd_run(args):
    v1, db, runs_mod, answer_pipeline = _boot(args.backend)
    orig_pb = _patch_sources(answer_pipeline, args.sources)
    set_dir = RUNS_DIR / args.set
    raw_dir, panel_dir = set_dir / "_raw", set_dir / "_panel"
    for d in (set_dir, raw_dir, panel_dir):
        d.mkdir(parents=True, exist_ok=True)
    questions = v1.load_questions(args.questions or None)
    print(f"[held-out v2] {len(questions)} Q · backend={args.backend} · sources={args.sources} · "
          f"runs={args.runs} · juez={'off' if args.no_judge else 'on'} · BD={os.environ['WITT_BACKEND_DB_URL']}")
    try:
        resumen = {"positive": 0, "negative": 0, "unfalsifiable_in_phase_I": 0, "unscored": 0,
                   "failed": 0}
        gasto = 0.0
        for q in questions:
            for r in range(1, args.runs + 1):
                rec, frozen, run, panel = run_question(v1, db, runs_mod, q, args.set, args.sources,
                                                       model_cutoff=args.model_cutoff,
                                                       no_judge=args.no_judge)
                if frozen is not None:
                    gasto += ((frozen.get("token_usage") or {}).get("estimated_cost_usd") or 0.0)
                outcome = rec.get("observed_outcome") or ("failed" if frozen is None else "unscored")
                resumen[outcome] = resumen.get(outcome, 0) + 1
                raw = {"run_id": rec.get("run_id"), "frozen": frozen,
                       "path_a_doc_ids": ([h["doc_id"] for h in
                                           json.loads(run["bundle_json"])["path_a"]["hits"]]
                                          if run.get("bundle_json") else [])}
                (raw_dir / f"run{r}_{q['id']}.json").write_text(
                    json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
                if r == 1:
                    (set_dir / f"{q['id']}.json").write_text(
                        json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
                    if panel is not None:   # el detalle por juez (verdicts crudos) — patrón v1
                        (panel_dir / f"{q['id']}.json").write_text(
                            json.dumps(panel, ensure_ascii=False, indent=1), encoding="utf-8")
                conf = rec.get("stated_confidence")
                print(f"  {q['id']} run{r}: {rec.get('observed_outcome') or rec.get('run_state')} · "
                      f"conf={conf} ({(rec.get('confidence') or {}).get('source')}) · "
                      f"verdict={(rec.get('audit') or {}).get('verdict')}")
        resumen_obj = {"set": args.set, "generated_at": _now_iso(), "harness": HARNESS_VERSION,
                       "backend": args.backend, "sources_mode": args.sources,
                       "model_cutoff": args.model_cutoff, "n_questions": len(questions),
                       "runs_per_q": args.runs, "outcomes": resumen,
                       "spend_usd_projection": round(gasto, 4),
                       "note": ("outcomes: deterministic=ground truth store; judge=ADVISORY jamás "
                                "ground truth (ADR-0037); ECE via compute_ece.py sobre este dir")}
        (set_dir / "_summary.json").write_text(json.dumps(resumen_obj, ensure_ascii=False, indent=1),
                                               encoding="utf-8")
        print(f"[held-out v2] {resumen} · gasto proyección USD {round(gasto, 4)} -> {set_dir}")
    finally:
        if orig_pb is not None:
            answer_pipeline.path_b_bundle = orig_pb


def cmd_eps(args):
    """EPS (Test 3) sobre corridas pareadas del v2: mismos ejes que el v1 (noise_probe reusado)."""
    sys.path.insert(0, str(ROOT / "substrate_calibration" / "tools"))
    import noise_probe
    import run_held_out as v1
    embedder = v1._load_bge_embedder() if args.axis_c == "bge" else None
    raw_dir = RUNS_DIR / args.set / "_raw"
    pairs = []
    for f1 in sorted(raw_dir.glob("run1_*.json")):
        qid = f1.stem.split("_")[-1]
        f2 = raw_dir / f"run2_{qid}.json"
        if not f2.exists():
            continue
        a, b = json.loads(f1.read_text(encoding="utf-8")), json.loads(f2.read_text(encoding="utf-8"))
        fa, fb = a.get("frozen") or {}, b.get("frozen") or {}
        pairs.append({
            "retrieval_a": a.get("path_a_doc_ids", []), "retrieval_b": b.get("path_a_doc_ids", []),
            "citations_a": [c.get("id") for c in fa.get("citations", [])],
            "citations_b": [c.get("id") for c in fb.get("citations", [])],
            "hyp_a": (fa.get("answer") or {}).get("direct_answer", "") or "",
            "hyp_b": (fb.get("answer") or {}).get("direct_answer", "") or "",
        })
    if not pairs:
        print(f"[eps] no hay corridas pareadas en {raw_dir} (corre con --runs 2)")
        return
    res = noise_probe.probe(pairs, month_tag=args.set, config_hash="held-out-v2", embedder=embedder)
    out = RUNS_DIR / args.set / "eps_v2.json"
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(res["axes"], indent=2))
    print(f"[eps] {out} (n_pairs={res['n_pairs']})")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Held-out harness v2 — sobre el run model (ADR-0072)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--set", default="month_p1", help="nombre del set de salida (evaluation/runs/<set>)")
    r.add_argument("--backend", default="sparse", choices=["sparse", "neo4j"])
    r.add_argument("--sources", default="di+structured", choices=["di-only", "di+structured"],
                   help="EVAL_DESIGN §1: fuentes DECLARADAS de la eval")
    r.add_argument("--runs", type=int, default=1, help="corridas pareadas (2 para EPS)")
    r.add_argument("--questions", default="", help="subset Q01,Q22 (default: las 30)")
    r.add_argument("--no-judge", action="store_true", help="sin panel advisory (solo determinista)")
    r.add_argument("--model-cutoff", default="not-declared",
                   help="cutoff del modelo sintetizador, ATESTIGUADO por el operador (EVAL_DESIGN §1)")
    r.set_defaults(func=cmd_run)
    e = sub.add_parser("eps")
    e.add_argument("--set", default="month_p1")
    e.add_argument("--axis-c", default="bge", choices=["bge", "lexical"])
    e.set_defaults(func=cmd_eps)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

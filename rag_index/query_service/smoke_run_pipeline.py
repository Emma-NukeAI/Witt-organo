"""smoke_run_pipeline.py — gate determinista del bloque 3 (ADR-0049/0050).

Cubre: la reforma de la maquina de estados (DI_SUFFICIENT ya NO autoriza responder — auditoria en el
100% de las corridas), el composite_auditor invocable (agregacion worst-of, vocabulario homologado,
panel delgado NUNCA aprueba, jueces errados excluidos y registrados), record_audit con su PRIMER
llamador real, el modelo de corrida end-to-end (queued -> running -> awaiting_closure -> closed),
cancelacion como estado de primera clase, latido, y la bitacora UNICA (replay == traza viva).
ADR-0079 (seccion final): la INVESTIGACION integrada de punta a punta — raiz/refine/rerun/branch por la
puerta, snapshot del turno anterior como llave hermana al sintetizador (camino REAL capturado) y jamas al
panel, precedente en LETRAS != evidencia, fuga de identificadores del padre -> inadmisible, origen, ejes del
episodio por tabla, GET /threads y GET /runs?thread=, include_origins en precedente/calibracion, PDF.

100% offline: SQLite tmp, rag_backend/path_b/sintetizador/panel monkeypatcheados — cero red, cero
OpenAI/Anthropic, cero mutacion de la DATA INAMOVIBLE. Exit 0 = todo PASS.

Corre:  python rag_index/query_service/smoke_run_pipeline.py
(necesita fastapi + sqlalchemy; venv desechable — NO el .venv del MCP, ADR-0039.)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TMP = Path(tempfile.mkdtemp(prefix="smoke_run_pipeline_"))
os.environ["WITT_BACKEND_DB_URL"] = f"sqlite:///{TMP / 'backend.db'}"
os.environ.pop("NEO4J_URI", None)
os.environ["WITT_ALLOW_RUNS_OFFLINE"] = "1"   # dev sparse siempre esta OFFLINE (LOTE-01·A5 override)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402
import db  # noqa: E402
import runs as runs_mod  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from lib import answer_pipeline, composite_auditor, models, rag_backend  # noqa: E402
from lib.rag_backend import Hit, HitList  # noqa: E402

os.environ.pop("NEO4J_URI", None)

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


def _http_error(fn, *a, **kw):
    try:
        fn(*a, **kw)
        return None
    except HTTPException as e:
        return e.status_code


def _cits_base(citations):
    """La forma BASE de las citas (n, kind, id, note). ADR-0080 (G) añade por cita la escalera de soporte
    (resolved, passage_delivered, pertinent, supported, support_state) como llaves ADITIVAS: los checks
    anteriores comparan la base, y la escalera se prueba en su sección."""
    return [{k: c.get(k) for k in ("n", "kind", "id", "note")} for c in (citations or [])]


# ---- stubs deterministas ----------------------------------------------------------------------------
def _raises(fn, exc):
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


def _stub_caller_factory(verdicts):
    """caller inyectado: devuelve verdicts[lens] o lanza si el valor es una excepcion."""
    def _caller(member, system, user_text):
        v = verdicts[member["lens"]]
        if isinstance(v, Exception):
            raise v
        return ({"verdict": v, "caught": f"({member['lens']})", "correction_applied": "",
                 "confidence": 0.9, "reasons": []}, {"input_tokens": 10, "output_tokens": 5})
    return _caller


def _mk_synth(conf_by_pass, extra=None):
    """Sintetizador stub de dos pasadas: conf_by_pass = {'pass1': x, 'pass2': y} (+campos extra)."""
    def _synth(question, evidence, pass_label):
        out = {"direct_answer": "wt1a (ENSDARG00000031420) marks the zebrafish pronephros.",
               "stated_confidence": conf_by_pass.get(pass_label, 0.8),
               "confidence_by_subclaim": {"marker-expression": 0.9, "functional-requirement": 0.3},
               "absence_kind": "not-applicable",
               "gap_flags": [], "evidence_cited": [{"kind": "di-record", "id": "CORPUS-2026-0001"}],
               # contrato §5 (ADR-0060): el stub cita el criterio REAL del catalogo
               "alternatives_considered": ["wt1b como paralogo redundante: descartado, sin evidencia"],
               "framework_applied": "Logic-LM",
               "framework_criterion": "for any task whose criteria are formalizable",
               "framework_reason": "la admisibilidad del identificador es formalizable",
               "model": "stub-synth", "usage": {"input_tokens": 100, "output_tokens": 50}}
        out.update(extra or {})
        return out
    return _synth


_stub_synth = _mk_synth({"pass1": 0.8, "pass2": 0.85})


_chunk = Hit(doc_id="CORPUS-2026-0003#c000", type="chunk", score=0.9, text="pronephros evidence",
             metadata={})
_path_b_real = answer_pipeline.path_b          # ADR-0078: la seccion de Ruta B lo restaura con stubs de red
_path_b_stub = lambda q, n=2, **kw: []
answer_pipeline.path_b = _path_b_stub
rag_backend.query = lambda text, k=6: HitList([_chunk], degraded=None)

# ---- 1. reforma ADR-0049: DI_SUFFICIENT ya NO autoriza responder ------------------------------------
b = answer_pipeline.retrieve("well covered question")
check("DI_SUFFICIENT es intermedio: may_answer_now=False + required_next=AUDIT (ADR-0049)",
      b["decision_state"]["state"] == "DI_SUFFICIENT"
      and b["decision_state"]["may_answer_now"] is False
      and "AUDIT" in b["decision_state"]["required_next_action"])

# ---- 2. composite_auditor: agregacion worst-of + vocabulario ----------------------------------------
ALL_A = {"correctness": "APPROVE", "overclaim": "APPROVE", "evidence-grounding": "APPROVE",
         "reproducibility": "APPROVE"}
r = composite_auditor.audit({"c": 1}, {"e": 1}, caller=_stub_caller_factory(ALL_A))
check("panel 4/4 APPROVE -> APPROVE, tally correcto, source_vocabulary presente",
      r["verdict"] == "APPROVE" and r["tally"]["APPROVE"] == 4
      and r["source_vocabulary"] == "APPROVE|APPROVE_DECLINE|APPROVE_MINOR|REVISE" and r["n_valid"] == 4)
# ADR-0058: la declinacion correcta es su propio veredicto y APRUEBA
r = composite_auditor.audit({"c": 1}, {"e": 1}, caller=_stub_caller_factory(
    {**ALL_A, "reproducibility": "APPROVE_DECLINE"}))
check("ADR-0058: APPROVE_DECLINE domina al APPROVE generico (caracterizacion especifica)",
      r["verdict"] == "APPROVE_DECLINE")
r = composite_auditor.audit({"c": 1}, {"e": 1}, caller=_stub_caller_factory(
    {**ALL_A, "reproducibility": "APPROVE_DECLINE", "overclaim": "APPROVE_MINOR"}))
check("ADR-0058: un issue real (APPROVE_MINOR) domina a la declinacion", r["verdict"] == "APPROVE_MINOR")
b_dec = answer_pipeline.retrieve("honest decline run")
r_dec = composite_auditor.audit({"c": 1}, {"e": 1}, caller=_stub_caller_factory(
    {"correctness": "APPROVE_DECLINE", "overclaim": "APPROVE_DECLINE",
     "evidence-grounding": "APPROVE_DECLINE", "reproducibility": "APPROVE_DECLINE"}))
b_dec = composite_auditor.apply_to_bundle(b_dec, r_dec, ["x"])
check("ADR-0058: la declinacion honesta correcta termina AUDIT_APPROVED (hallazgo de primera clase)",
      b_dec["decision_state"]["state"] == "AUDIT_APPROVED"
      and b_dec["audit"]["verdict"] == "APPROVE_DECLINE")
r = composite_auditor.audit({"c": 1}, {"e": 1}, caller=_stub_caller_factory(
    {**ALL_A, "overclaim": "APPROVE_MINOR"}))
check("worst-of: un APPROVE_MINOR degrada el verdict global", r["verdict"] == "APPROVE_MINOR")
r = composite_auditor.audit({"c": 1}, {"e": 1}, caller=_stub_caller_factory(
    {**ALL_A, "evidence-grounding": "REVISE"}))
check("worst-of: un REVISE manda (nunca se promedia el catch)", r["verdict"] == "REVISE")

# ---- 3. panel delgado NUNCA aprueba (Mode 1 minimo >=3) ---------------------------------------------
r = composite_auditor.audit({"c": 1}, {"e": 1}, caller=_stub_caller_factory(
    {"correctness": "APPROVE", "overclaim": RuntimeError("judge down"),
     "evidence-grounding": RuntimeError("judge down"), "reproducibility": "APPROVE"}))
errored = [p for p in r["panel"] if p.get("status") == "errored"]
check("2 jueces caidos (<3 validos) -> REVISE + panel_incomplete (conservador)",
      r["verdict"] == "REVISE" and r.get("panel_incomplete") is True and r["n_valid"] == 2)
check("jueces errados quedan REGISTRADOS como errored (excluidos, jamas fabricados)",
      len(errored) == 2 and all("error" in p for p in errored))

# ---- 4. apply_to_bundle: el PRIMER llamador real de record_audit ------------------------------------
b = answer_pipeline.retrieve("q for audit")
r_ok = composite_auditor.audit({"c": 1}, {"e": 1}, caller=_stub_caller_factory(ALL_A))
b = composite_auditor.apply_to_bundle(b, r_ok, ["CORPUS-2026-0003#c000"])
import hashlib
payload = {k: v for k, v in b.items() if k != "bundle_identity"}
sha = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
check("APPROVE -> record_audit -> AUDIT_APPROVED + panel visible en bundle.audit + identidad re-estampada",
      b["decision_state"]["state"] == "AUDIT_APPROVED" and len(b["audit"]["panel"]) == 4
      and b["audit"]["verdict"] == "APPROVE" and b["bundle_identity"]["sha256"] == sha)
b2 = answer_pipeline.retrieve("q for reject")
r_rev = composite_auditor.audit({"c": 1}, {"e": 1}, caller=_stub_caller_factory(
    {**ALL_A, "correctness": "REVISE"}))
b2 = composite_auditor.apply_to_bundle(b2, r_rev, ["x"])
check("REVISE -> AUDIT_REJECTED (evidencia rechazada, gap explicito)",
      b2["decision_state"]["state"] == "AUDIT_REJECTED")

# ---- 5. corrida end-to-end (worker sincrono, panel/sintesis stubbeados) ------------------------------
db.init_db()
db.upsert_user("natalia", "Natalia", "medico", "pw-natalia-123")
AUTH = "Bearer " + app.login(app.LoginBody(username="natalia", password="pw-natalia-123"))["token"]
rv = app.create_run(app.RunBody(question="does wt1a mark the pronephros?", entities=[]),
                    authorization=AUTH)
RID = rv["run_id"]
check("POST /runs -> queued con run_id + evento inicial", rv["state"] == "queued" and len(RID) == 32)
check("ADR-0076: la corrida NACE con número de corrida y viaja en la vista (1 en BD nueva)",
      rv.get("run_no") == 1)
claimed = db.claim_next_queued()
check("claim atomico: queued -> running (FIFO)", claimed["run_id"] == RID
      and db.get_run(RID)["state"] == "running")
runs_mod.execute_run(claimed, synthesizer=_stub_synth,
                     panel_caller=_stub_caller_factory(ALL_A))
run = db.get_run(RID)
check("corrida termina awaiting_closure (terminal SIEMPRE post-audit, ADR-0049)",
      run["state"] == "awaiting_closure" and run["finished_at"] is not None)
ev = app.get_events(RID, after=0, authorization=AUTH)["events"]
types = [e["type"] for e in ev]
check("bitacora: eventos por etapa con seq monotonico (replay == traza viva)",
      [e["seq"] for e in ev] == list(range(1, len(ev) + 1))
      and "stage.path_a" in types and "stage.assess_sufficiency" in types
      and "stage.synthesize.pass1" in types and "stage.deterministic_gate" in types
      and "stage.audit.verdict" in types, f"n={len(ev)}")
check("corrector ADR-0078: latido POR JUEZ — 4 eventos stage.audit.judge antes del veredicto (el hueco sin evento "
      "queda acotado a UN juez, nunca al panel entero)",
      types.count("stage.audit.judge") == 4
      and types.index("stage.audit.judge") < types.index("stage.audit.verdict")
      and all(e["payload"].get("heartbeat") is True for e in ev if e["type"] == "stage.audit.judge"),
      f"judge_events={types.count('stage.audit.judge')}")
check("corrector ADR-0078: la vista tipa failure_reason (null cuando no falló) y claimed_by sin worker_id es null",
      app.get_run(RID, authorization=AUTH)["failure_reason"] is None
      and app.get_run(RID, authorization=AUTH)["claimed_by"] is None)
rec = app.get_frozen_record(RID, authorization=AUTH)
check("registro congelado persistido en backend: contrato = runs.RENDER_CONTRACT_VERSION (la versión vigente la fija "
      "runs.py — 1.7 ADR-0078, 1.8 ADR-0079; el literal se asserta UNA vez, en la sección ADR-0079) + audit + "
      "store_at_retrieval + identidad",
      rec["render_contract_version"] == runs_mod.RENDER_CONTRACT_VERSION and rec["audit"]["verdict"] == "APPROVE"
      and rec["question_matches_run"] is True and rec["decision_state"]["state"] == "AUDIT_APPROVED"
      and "store_version" in rec["store_at_retrieval"] and rec["bundle_identity"]["run_id"] == RID)
# --- bloque 4 (ADR-0051): confianza alta + DI suficiente -> SIN fallback, una sola pasada -----------
# ADR-0080: POST /runs SIN plan -> la compuerta de competencia NO puede declarar competente (route/niches
# ausentes, reason 'no-plan') -> trigger 'competence' + pass2, aunque conf 0.8 >= tau (trigger_legacy null:
# la regla vieja NO habría disparado — el literal 'confidence' vive SOLO en fb_meta.trigger_legacy). El camino
# competente (con plan: sin ronda, trigger null) se prueba en la sección ADR-0080.
check("ADR-0080 sin plan: trigger='competence' (reasons route_evidence_run + niches_nonempty por 'no-plan'), "
      "trigger_legacy null (0.8 >= tau), pass2 corre y ambas confianzas persisten (0.8 -> 0.85, delta 0.05)",
      rec["fallback"]["trigger"] == "competence" and rec["fallback"]["fb_meta"]["trigger_legacy"] is None
      and rec["confidence"]["pass1"] == 0.8 and rec["confidence"]["pass2"] == 0.85
      and rec["confidence"]["delta"] == 0.05 and rec["confidence"]["state"] == "value"
      and "stage.synthesize.pass2" in types
      and rec["competence"]["competent"] is False
      and set(rec["competence"]["reasons"]) == {"route_evidence_run", "niches_nonempty"}
      and rec["competence"]["components"]["route_evidence_run"]["reason"] == "no-plan"
      and rec["competence"]["components"]["niches_nonempty"]["reason"] == "no-plan",
      f"reasons={rec['competence']['reasons']}")
check("confidence_by_subclaim viaja al registro (asimetria declarada, no promediada)",
      rec["confidence"]["by_subclaim"] == {"marker-expression": 0.9, "functional-requirement": 0.3})
check("citas tipadas con serie numerica (letras reservadas a precedente); ADR-0080: la escalera de soporte es "
      "ADITIVA dentro de la cita (support_state presente, forma base intacta)",
      _cits_base(rec["citations"]) == [{"n": 1, "kind": "di-record", "id": "CORPUS-2026-0001", "note": ""}]
      and "support_state" in rec["citations"][0]
      and rec["answer"]["absence_kind"] == "not-applicable")
tu = rec["token_usage"]
# ADR-0081: el juez de la lente correctness se LEE del registro (models.panel() en la llamada), no se pinea un literal
_corr_reviewer = next(r["reviewer"] for r in rec["audit"]["panel"] if r["lens"] == "correctness")
check("TokenUsage: by_model medido + costo etiquetado PROJECTION + embeddings declarados (ADR-0080: sin plan hay "
      "pass1 + pass2 -> stub-synth 200/100; total 240/120; ADR-0081: el juez correctness es el que el registro dice)",
      tu["by_model"].get("stub-synth") == {"in": 200, "out": 100}
      and tu["by_model"].get(_corr_reviewer) == {"in": 10, "out": 5}
      and tu["input_tokens"] == 240 and tu["output_tokens"] == 120
      and "PROJECTION" in tu["cost_class"] and tu["estimated_cost_usd"] > 0
      and tu["embedding"]["total_tokens"] == 0,
      f"cost={tu['estimated_cost_usd']}")
view = app.get_run(RID, authorization=AUTH)
check("latido expuesto (heartbeat_age_s) y no-stale tras actividad",
      view["heartbeat_age_s"] is not None and view["heartbeat_stale"] is False)
es = view["epistemic_summary"]
# se comprueban los campos POR NOMBRE, no el dict por igualdad: la igualdad exacta convertía
# cualquier campo aditivo en una regresión falsa (2026-09-05, al entrar el eje de nichos).
check("LOTE-02·3: epistemic_summary derivado AL CONGELAR, visible en la vista (renglon rico de M6)",
      es["retrieval_mode"] == "semantic" and es["verdict"] == "APPROVE"
      and es["confidence_state"] == "value" and es["panel_n_valid"] == 4,
      f"summary={ {k: v for k, v in es.items() if k != 'niches'} }")

# 2026-09-05 — LOS DOS EJES DE NICHO, en fuentes separadas: el juicio jamás tapa a la medición
nic = es.get("niches") or {}
check("nichos: el eje del CATALOGO viaja con su cobertura y se declara MEDICION",
      (nic.get("catalogo") or {}).get("class") == "medicion"
      and "coverage" in (nic.get("catalogo") or {}),
      f"catalogo={ {k: v for k, v in (nic.get('catalogo') or {}).items() if k in ('class', 'coverage')} }")
# el CABLEADO, no solo la forma: el registro llama `citations` a la evidencia y leer `evidence`
# devolvia "0 de 0" — un cable roto disfrazado de corrida sin evidencia catalogada (2026-09-05).
# El denominador tiene que ser el numero REAL de citas del registro.
check("nichos: el catalogo lee las CITAS del registro (denominador real, no un 0 de 0 mudo)",
      (nic.get("catalogo") or {}).get("n_evidence") == len(rec.get("citations") or []),
      f"n_evidence={(nic.get('catalogo') or {}).get('n_evidence')} citas={len(rec.get('citations') or [])}")
check("nichos: el eje del PANEL viaja aparte y se declara JUICIO (conteos, jamas un ganador)",
      (nic.get("panel") or {}).get("class") == "juicio"
      and isinstance((nic.get("panel") or {}).get("counts"), dict)
      and "n_classified" in (nic.get("panel") or {}),
      f"panel={nic.get('panel')}")

# ---- LOTE-01·A1/A2: la LISTA trae el latido + el umbral viaja con la derivacion ----------------------
lst = app.list_runs(authorization=AUTH)["runs"]
check("GET /runs (lista) via _run_view: latido + umbral + token_usage + fechas como el detalle",
      lst and all(("heartbeat_age_s" in r and "heartbeat_stale" in r
                   and r["heartbeat_stale_after_s"] == app.HEARTBEAT_STALE_S
                   and "token_usage" in r) for r in lst)
      and view["heartbeat_stale_after_s"] == app.HEARTBEAT_STALE_S)

# ---- LOTE-01·A5: POST /runs bloquea con el indice OFFLINE (server-side, no disciplina de UI) ---------
os.environ.pop("WITT_ALLOW_RUNS_OFFLINE", None)
err = _http_error(app.create_run, app.RunBody(question="should be blocked", entities=[]),
                  authorization=AUTH)
os.environ["WITT_ALLOW_RUNS_OFFLINE"] = "1"
check("indice OFFLINE sin override -> POST /runs = 409 index_offline (bloquea, no degrada)",
      err == 409)

# ---- 5b. fallback por CONFIANZA (el fix que pidio la corrida #1: tau=0.5) ----------------------------
rv = app.create_run(app.RunBody(question="thin evidence question", entities=[]), authorization=AUTH)
claimed = db.claim_next_queued()
runs_mod.execute_run(claimed, synthesizer=_mk_synth({"pass1": 0.3, "pass2": 0.75}),
                     panel_caller=_stub_caller_factory(ALL_A))
rec = app.get_frozen_record(rv["run_id"], authorization=AUTH)
ev_types = [e["type"] for e in app.get_events(rv["run_id"], after=0, authorization=AUTH)["events"]]
check("pass1 0.3 < tau 0.5 -> Ruta B aunque lo estructural dijera suficiente; ADR-0080: trigger='competence' y el "
      "literal viejo vive en fb_meta.trigger_legacy='confidence' (la regla `pass1 < tau` habría disparado)",
      rec["fallback"]["trigger"] == "competence"
      and rec["fallback"]["fb_meta"]["trigger_legacy"] == "confidence"
      and rec["fallback"]["fb_meta"]["pass1_confidence"] == 0.3
      and rec["fallback"]["fb_meta"]["tau"] == 0.5
      and rec["audit"]["required_because"] == "FALLBACK_FETCHED"
      and "stage.path_b" in ev_types)
check("dos pasadas persistidas: pass1=0.3, pass2=0.75, delta=+0.45 (el dato mas informativo)",
      rec["confidence"]["pass1"] == 0.3 and rec["confidence"]["pass2"] == 0.75
      and rec["confidence"]["delta"] == 0.45 and rec["confidence"]["final"] == 0.75
      and "stage.synthesize.pass2" in ev_types)

# ---- 5c. fallback ESTRUCTURAL (la via original) -----------------------------------------------------
rag_backend.query = lambda text, k=6: HitList([], degraded=None)   # DI sin chunks -> insuficiente
rv = app.create_run(app.RunBody(question="no coverage question", entities=[]), authorization=AUTH)
claimed = db.claim_next_queued()
runs_mod.execute_run(claimed, synthesizer=_mk_synth({"pass1": 0.9, "pass2": 0.9}),
                     panel_caller=_stub_caller_factory(ALL_A))
rec = app.get_frozen_record(rv["run_id"], authorization=AUTH)
check("insuficiencia estructural -> trigger=structural y dos pasadas aunque pass1 fuera confiada",
      rec["fallback"]["trigger"] == "structural" and rec["confidence"]["pass2"] == 0.9)
rag_backend.query = lambda text, k=6: HitList([_chunk], degraded=None)

# ---- 5d. confianza AUSENTE -> dispara fallback + estado declarado (jamas null silencioso) ------------
rv = app.create_run(app.RunBody(question="model omits confidence", entities=[]), authorization=AUTH)
claimed = db.claim_next_queued()
runs_mod.execute_run(claimed, synthesizer=_mk_synth({"pass1": None, "pass2": None},
                                                    extra={"confidence_by_subclaim": None}),
                     panel_caller=_stub_caller_factory(ALL_A))
rec = app.get_frozen_record(rv["run_id"], authorization=AUTH)
check("confianza ausente (ni escalar ni subclaims): gate + 'absent-not-calibratable' declarado; ADR-0080: trigger "
      "'competence' + trigger_legacy 'confidence' + componente conf1_ge_tau con reason 'conf1-absent'",
      rec["fallback"]["trigger"] == "competence"
      and rec["fallback"]["fb_meta"]["trigger_legacy"] == "confidence"
      and rec["competence"]["components"]["conf1_ge_tau"]["reason"] == "conf1-absent"
      and rec["fallback"]["fb_meta"]["pass1_confidence"] is None
      and rec["confidence"]["state"] == "absent-not-calibratable"
      and rec["confidence"]["delta"] is None)

# ---- LOTE-03·2: la confianza atrapada como texto se RECUPERA, con procedencia declarada --------------
prod_artifact = {"direct_answer": "…no hay evidencia funcional (marcadores pronéfricos).</parameter>\n"
                                  '<parameter name="confidence">0.15',
                 "confidence": None, "absence_kind": "no-evidence-retrieved"}
out = composite_auditor.recover_trapped_params(dict(prod_artifact))
check("recover_trapped_params: el artefacto EXACTO de produccion (2/2 corridas) se recupera",
      out["confidence"] == 0.15 and out["_recovered_fields"] == ["confidence"]
      and "<parameter" not in out["direct_answer"] and "</parameter" not in out["direct_answer"]
      and out["direct_answer"].endswith("(marcadores pronéfricos)."))
clean = composite_auditor.recover_trapped_params({"direct_answer": "texto limpio.", "confidence": 0.8})
check("recover_trapped_params: una salida limpia pasa intacta (sin _recovered_fields)",
      clean["confidence"] == 0.8 and "_recovered_fields" not in clean)

# ---- ADR-0065: la elicitación dedicada es la medición AUTORITATIVA del escalar ------------------------
# (medido en evaluation/scripts/ab_trapped_scalar.py: in-line atrapado ~50-60% e insensible a prompts;
# la elicitación sin campos largos = 24/24 limpia con |delta| mediana 0.09 tras clavar la semántica)
_orig_tool_call = composite_auditor._anthropic_tool_call


def _mk_fake_api(synth_out, elicit_out=None, elicit_raises=False):
    def fake(model, system, user_text, tool=None, timeout=120, retries=1, max_tokens=1200):
        if tool and tool["name"] == "emit_confidence":
            if elicit_raises:
                raise RuntimeError("elicitation down (smoke)")
            return dict(elicit_out), {"input_tokens": 30, "output_tokens": 3}
        return dict(synth_out), {"input_tokens": 100, "output_tokens": 50}
    return fake


_BASE_SYNTH = {"direct_answer": "respuesta.", "confidence": None, "absence_kind": "not-applicable",
               "alternatives_considered": ["x"], "framework_applied": "NONE-MATCHED",
               "gap_flags": [], "evidence_cited": []}

composite_auditor._anthropic_tool_call = _mk_fake_api(dict(_BASE_SYNTH), elicit_out={"confidence": 0.4})
ans = runs_mod._default_synthesizer("q", {"e": 1}, "pass1")
check("ADR-0065a: la elicitada gobierna (source=stated-second-elicitation) + usage FUSIONADO (M8 cuadra)",
      ans["stated_confidence"] == 0.4 and ans["confidence_source"] == "stated-second-elicitation"
      and ans["stated_confidence_inline"] is None
      and ans["usage"] == {"input_tokens": 130, "output_tokens": 53})

composite_auditor._anthropic_tool_call = _mk_fake_api({**_BASE_SYNTH, "confidence": 0.9},
                                                      elicit_out={"confidence": 0.2})
ans = runs_mod._default_synthesizer("q", {"e": 1}, "pass1")
check("ADR-0065b: divergencia >0.15 DECLARADA en gap_flags; la elicitada gobierna, la in-line persiste",
      ans["stated_confidence"] == 0.2 and ans["stated_confidence_inline"] == 0.9
      and any("cross-check divergence" in f for f in ans["gap_flags"]))

composite_auditor._anthropic_tool_call = _mk_fake_api(
    {**_BASE_SYNTH, "confidence": 0.15, "_recovered_fields": ["confidence"]},
    elicit_out={"confidence": 0.1, "confidence_by_subclaim": {"s1": 0.2, "s2": 0.05}})
ans = runs_mod._default_synthesizer("q", {"e": 1}, "pass1")
check("ADR-0065c: in-line RECOVERED queda como cross-check declarado; subclaims elicitados ganan",
      ans["stated_confidence"] == 0.1 and ans["confidence_source"] == "stated-second-elicitation"
      and ans["stated_confidence_inline"] == 0.15
      and ans["confidence_by_subclaim"] == {"s1": 0.2, "s2": 0.05}
      and any("kept as cross-check" in f for f in ans["gap_flags"]))

composite_auditor._anthropic_tool_call = _mk_fake_api({**_BASE_SYNTH, "confidence": 0.7},
                                                      elicit_raises=True)
ans = runs_mod._default_synthesizer("q", {"e": 1}, "pass1")
check("ADR-0065d: elicitación caída JAMÁS bloquea (§6) — cae al in-line source=stated + flag declarado",
      ans["stated_confidence"] == 0.7 and ans["confidence_source"] == "stated"
      and any("elicitation FAILED" in f for f in ans["gap_flags"]))

composite_auditor._anthropic_tool_call = _mk_fake_api(dict(_BASE_SYNTH), elicit_raises=True)
ans = runs_mod._default_synthesizer("q", {"e": 1}, "pass1")
check("ADR-0065e: sin escalar por NINGÚN camino -> ausencia DECLARADA (jamás null silencioso)",
      ans["stated_confidence"] is None and any("ABSENT" in f for f in ans["gap_flags"]))

# ---- ADR-0074: campos-lista serializados como string — se parsean con procedencia o se conservan
# crudos DECLARADOS (la corrida real 9b3140ab congeló alternatives como string JSON y gap_flags
# explotado en caracteres; la hoja de la webapp no dibujaba) ------------------------------------------
trap_lista = composite_auditor.recover_trapped_params(
    {"direct_answer": 'texto.</parameter>\n<parameter name="alternatives_considered">["a", "b"]',
     "confidence": 0.5, "alternatives_considered": None})
check("ADR-0074a: recover_trapped_params parsea el contenedor JSON atrapado (lista, no string)",
      trap_lista["alternatives_considered"] == ["a", "b"]
      and "alternatives_considered" in trap_lista["_recovered_fields"])
composite_auditor._anthropic_tool_call = _mk_fake_api(
    {**_BASE_SYNTH, "alternatives_considered": '["alt uno", "alt dos"]', "gap_flags": '["g1"]'},
    elicit_out={"confidence": 0.4})
ans = runs_mod._default_synthesizer("q", {"e": 1}, "pass1")
check("ADR-0074b: alternatives/gap_flags serializados se parsean, con procedencia; JAMÁS chars sueltos",
      ans["alternatives_considered"] == ["alt uno", "alt dos"]
      and "g1" in ans["gap_flags"]
      and not any(len(f) == 1 for f in ans["gap_flags"])
      and sum("SERIALIZAD" in f for f in ans["gap_flags"]) == 2)
composite_auditor._anthropic_tool_call = _mk_fake_api(
    {**_BASE_SYNTH, "alternatives_considered": "prosa suelta, no JSON"},
    elicit_out={"confidence": 0.4})
ans = runs_mod._default_synthesizer("q", {"e": 1}, "pass1")
check("ADR-0074c: string NO parseable -> se conserva crudo como UN elemento, declarado (jamás [])",
      ans["alternatives_considered"] == ["prosa suelta, no JSON"]
      and any("NO parseable" in f for f in ans["gap_flags"]))
composite_auditor._anthropic_tool_call = _orig_tool_call
rv = app.create_run(app.RunBody(question="recovered conf run", entities=[]), authorization=AUTH)
claimed = db.claim_next_queued()
runs_mod.execute_run(claimed, synthesizer=_mk_synth(
    {"pass1": 0.15, "pass2": 0.75},
    extra={"confidence_source": "recovered-from-malformed-tool-call"}),
    panel_caller=_stub_caller_factory(ALL_A))
rec = app.get_frozen_record(rv["run_id"], authorization=AUTH)
check("procedencia en el registro: fb_meta.pass1_confidence_source='recovered-…' + gate disparado (0.15<tau; ADR-0080: "
      "trigger 'competence', trigger_legacy 'confidence')",
      rec["fallback"]["trigger"] == "competence"
      and rec["fallback"]["fb_meta"]["trigger_legacy"] == "confidence"
      and rec["fallback"]["fb_meta"]["pass1_confidence_source"] == "recovered-from-malformed-tool-call"
      and rec["confidence"]["pass1_source"] == "recovered-from-malformed-tool-call")

# ---- LOTE-03·2b: §5 permite el OR — by_subclaim sin escalar deriva min (worst-of, declarado) ----------
rv = app.create_run(app.RunBody(question="subclaims only run", entities=[]), authorization=AUTH)
claimed = db.claim_next_queued()
runs_mod.execute_run(claimed, synthesizer=_mk_synth(
    {"pass1": None, "pass2": 0.75},
    extra={"confidence_by_subclaim": {"a": 0.60, "b": 0.10, "c": 0.05}}),
    panel_caller=_stub_caller_factory(ALL_A))
rec = app.get_frozen_record(rv["run_id"], authorization=AUTH)
check("by_subclaim sin escalar: gate usa min (0.05) DECLARADO como derived-min-of-subclaims",
      rec["fallback"]["fb_meta"]["pass1_confidence"] == 0.05
      and rec["fallback"]["fb_meta"]["pass1_confidence_source"] == "derived-min-of-subclaims"
      and rec["confidence"]["pass1_source"] == "derived-min-of-subclaims"
      and rec["confidence"]["source"] == "stated" and rec["confidence"]["final"] == 0.75)

# ---- LOTE-03·1: la query externa se construye y se REGISTRA (jamas la pregunta ES verbatim a ciegas) --
q_sent, q_src = answer_pipeline.build_external_query("¿Qué señal induce el pronefros?", ["osr1", "pax2a"])
check("build_external_query (ADR-0078): sintaxis NATIVA de Europe PMC desde los símbolos + organismo + "
      "anatomía detectada en ES; la fuente declara constructor y modo (ya no 'osr1 pax2a' como texto libre)",
      "TITLE:osr1 OR ABSTRACT:osr1" in q_sent and "TITLE:pax2a" in q_sent
      and 'MESH:"Zebrafish"' in q_sent and "pronephros" in q_sent and "ORGANISM:" not in q_sent
      and q_src == "query-builder-v1:symbols"
      # corrector: la pregunta ORIGINAL (sin formulación EN) jamás se tokeniza como texto libre -> 'empty'
      and answer_pipeline.build_external_query("solo pregunta", []) == (None, "query-builder-v1:empty")
      and answer_pipeline.build_external_query("solo pregunta", [], question_en="only question")[1]
      == "query-builder-v1:question-only",
      f"q={q_sent!r}")
rv = app.create_run(app.RunBody(question="pregunta en español sin cobertura",
                                entities=["osr1", "pax2a"]), authorization=AUTH)
claimed = db.claim_next_queued()
runs_mod.execute_run(claimed, synthesizer=_mk_synth(
    {"pass1": 0.2, "pass2": 0.7},
    extra={"search_query_en": "osr1 pax2a zebrafish pronephros induction"}),
    panel_caller=_stub_caller_factory(ALL_A))
ev_types = app.get_events(rv["run_id"], after=0, authorization=AUTH)["events"]
pb = next(e for e in ev_types if e["type"] == "stage.path_b")
check("conf-gated: la formulación EN del sintetizador ALIMENTA al constructor (anatomía detectada en ella) "
      "y queda AUDITABLE en el evento: query por fuente + question_en_source='synthesizer' (ADR-0078)",
      "TITLE:osr1" in pb["payload"]["query_sent"] and "pronephros" in pb["payload"]["query_sent"]
      and pb["payload"]["query_source"] == "query-builder-v1:symbols"
      and pb["payload"]["question_en_source"] == "synthesizer"
      and pb["payload"]["query_sent_scope"] == "europepmc"
      and "[tiab]" in pb["payload"]["pubmed_query"]
      # corrector ADR-0078: UNA política de anatomía para los tres índices — la pregunta ES no la trae,
      # el EN del sintetizador sí ('pronephros') -> zfin_filter 'pronephr', procedencia 'from-question-en'
      and pb["payload"]["zfin_filter"] == "pronephr"
      and pb["payload"]["epmc_query"] == pb["payload"]["query_sent"]
      and pb["payload"]["ledger_version"] == "2"
      and "n_results_by_source" in pb["payload"],
      f"payload_query={pb['payload']['query_sent']!r} zfin={pb['payload']['zfin_filter']!r}")

# ---- LOTE-04 / tapon 1A: ZFIN como fuente de Ruta B (nativo pez cebra) -------------------------------
# Todo offline: la tool se inyecta en el cache de carga por path, y CACHE se desvia al tmp del gate
# (el header promete cero mutacion, y eso incluye mcp_cache).
_CACHE_REAL = answer_pipeline.CACHE
answer_pipeline.CACHE = TMP / "mcp_cache"

check("filtro anatomico determinista: ES y EN caen al MISMO termino de ZFIN (leccion LOTE-03: un "
      "indice en otro idioma devuelve cero y se ve igual que 'no existe')",
      answer_pipeline.zfin_anatomy_filter("¿Qué señal induce el pronefros?") == ("pronephr", "question-keyword-table")
      and answer_pipeline.zfin_anatomy_filter("is wt1a required for pronephros") == ("pronephr", "question-keyword-table")
      and answer_pipeline.zfin_anatomy_filter("pregunta sin anatomia") == (None, "no-anatomy-term-in-question"))

def _fake_zfin(symbol, anatomy=None, limit=50, **kw):
    # envelope VIEJO (sin los campos ADR-0078): el pipeline debe seguir funcionando y dejar AUSENTES
    # (no null) las llaves que el tool no declaró
    if symbol == "boom":
        return {"status": "error", "error": "HTTPError: 500"}
    if symbol == "vacio":
        return {"status": "success", "data": {"symbol": symbol, "zfin_curie": "ZFIN:ZDB-GENE-VACIO",
                                             "taxon": "NCBITaxon:7955", "n_phenotypes_total": 143,
                                             "n_matched": 0, "anatomy_filter": anatomy, "phenotypes": []}}
    return {"status": "success", "data": {
        "symbol": symbol, "zfin_curie": f"ZFIN:ZDB-GENE-{symbol.upper()}", "taxon": "NCBITaxon:7955",
        "n_phenotypes_total": 143, "n_matched": 30, "anatomy_filter": anatomy,
        "phenotypes": [{"statement": f"{symbol}: pronephric duct absent, abnormal",
                        "references": ["12345678"]}] * 30}}

answer_pipeline._WS_CACHE[("zfin_zebrafish.py", "query_zfin")] = _fake_zfin
items, ledger = answer_pipeline._search_zfin(
    ["pax2a", "vacio", "boom", "a", "b", "c", "d"], "pronefros: ¿qué induce el pronefros?")
by = {r["symbol"]: r["status"] for r in ledger}
check("ZFIN distingue los CUATRO destinos de un simbolo: success / no-match / error / skipped-cap "
      "(buscar y no hallar JAMAS se ve como que la busqueda fallo)",
      by["pax2a"] == "success" and by["vacio"] == "no-match" and by["boom"] == "error"
      and by["d"] == "skipped-cap" and len(ledger) == 7,
      f"ledger={by}")
check("ZFIN emite item SOLO cuando hubo match, con evidence_id = curie resuelto en vivo (nunca acuñado)",
      len(items) == 4 and all(i["source"] == "zfin" for i in items)
      and items[0]["evidence_id"] == "ZFIN:ZDB-GENE-PAX2A"
      and all(i["evidence_id"] != "paper" for i in items),
      f"n_items={len(items)}")
z = items[0]["zfin"]
check("el truncado de statements se DECLARA (n_matched 30 > n_returned 12) — un corte silencioso se "
      "leeria como 'eso es todo lo que ZFIN sabe'",
      z["n_matched"] == 30 and z["n_returned"] == 12 and z["truncated"] is True
      and z["anatomy_filter"] == "pronephr" and z["taxon"] == "NCBITaxon:7955"
      and z["identifier_provenance"] == "alliance-genome-api-live")
check("presupuesto de reloj: agotado -> los simbolos restantes quedan skipped-budget, no invisibles",
      [r["status"] for r in answer_pipeline._search_zfin(["x", "y"], "pronefros", budget_s=-1)[1]]
      == ["skipped-budget", "skipped-budget"])
answer_pipeline._WS_CACHE[("zfin_zebrafish.py", "query_zfin")] = None
check("tool ausente -> la fuente DEGRADA declarada (tool-unavailable), la corrida no truena (§6 no-hang)",
      answer_pipeline._search_zfin(["pax2a"], "pronefros")[1][0]["status"] == "tool-unavailable")
answer_pipeline._WS_CACHE.pop(("zfin_zebrafish.py", "query_zfin"), None)
answer_pipeline.CACHE = _CACHE_REAL

check("n_results_by_source: por fuente, y AMBAS fuentes de literatura presentes por default "
      "(0 explicito != fuente ausente)",
      answer_pipeline.n_results_by_source([{"source": "zfin"}, {"source": "zfin"}])
      == {"zfin": 2, "europepmc": 0, "pubmed": 0})
check("corrector ADR-0078: el 0 explícito se estampa SOLO para las fuentes PEDIDAS — sources=('zfin',) deja "
      "europepmc/pubmed AUSENTES ('no se pidió' != '0 medido')",
      answer_pipeline.n_results_by_source([{"source": "zfin"}], sources=("zfin",)) == {"zfin": 1}
      and answer_pipeline.n_results_by_source([], sources=("europepmc", "zfin")) == {"europepmc": 0})

# ---- ADR-0062 / tapon 1B: PubMed en Layer 0 con dedup por PMID -----------------------------------------
_pubmed_calls = []


def _fake_pubmed(query, limit=None, retmax=None):
    # forma del tool ADR-0078 (identidad, throttle, retmax_sent declarados) — sin red
    _pubmed_calls.append({"query": query, "limit": limit, "retmax": retmax})
    return {"status": "success", "ncbi_identity": "missing",
            "throttle": {"host": "eutils.ncbi.nlm.nih.gov", "min_interval_s": 0.34,
                         "min_interval_source": "derived", "api_key_present": False, "waited_s": 0.0},
            "retries_429": 0, "rate_limit_headers": None,
            "data": {"query": query, "query_sent": query, "retmax_sent": retmax, "n_found_total": 9,
                     "records": [
                         {"pmid": "19666820", "title": "RA responsive element controls wt1a",
                          "year": "2009", "journal": "Development"},
                         {"pmid": "42153456", "title": "ya vino por europepmc", "year": "2025",
                          "journal": "X"},
                     ]}}


answer_pipeline._WS_CACHE[("pubmed_literature.py", "query_pubmed")] = _fake_pubmed
cands, row = answer_pipeline._search_pubmed("wt1a zebrafish", 20, {"PMID:42153456": "PMID:42153456"})
check("pubmed: dedup por PMID contra europepmc DECLARADO — el duplicado ni entra dos veces ni se "
      "tira callado (EPMC indexa PubMed: sin esto el sintetizador cuenta doble)",
      len(cands) == 1 and cands[0]["evidence_id"] == "PMID:19666820"
      and cands[0]["source"] == "pubmed" and "fetched" not in cands[0]   # candidato: aún no se baja
      and row["status"] == "success" and row["n_new"] == 1
      and row["duplicates_of_europepmc"] == ["PMID:42153456"])
check("ADR-0078 pubmed: se pide retmax (no n) y el ledger copia lo que el tool DECLARA — "
      "retmax_sent, query_sent, ncbi_identity 'missing', throttle, retries_429, rate_limit_headers",
      _pubmed_calls[-1]["retmax"] == 20 and _pubmed_calls[-1]["limit"] is None
      and row["retmax_sent"] == 20 and row["query_sent"] == "wt1a zebrafish"
      and row["ncbi_identity"] == "missing" and row["throttle"]["host"] == "eutils.ncbi.nlm.nih.gov"
      and row["retries_429"] == 0 and row["rate_limit_headers"] is None)
answer_pipeline._WS_CACHE[("pubmed_literature.py", "query_pubmed")] = (
    lambda query, limit=None, retmax=None: {"status": "error", "error": "HTTPError: 500 Server Error",
                                            "http_status": 500, "ncbi_identity": "missing"})
cands_e, row_e = answer_pipeline._search_pubmed("q", 20, {})
check("pubmed: la busqueda FALLIDA se declara error (+ http_status del tool) — jamas se ve igual que "
      "'no hay resultados'",
      cands_e == [] and row_e["status"] == "error" and "500" in row_e["detail"]
      and row_e["http_status"] == 500)
answer_pipeline._WS_CACHE[("pubmed_literature.py", "query_pubmed")] = None
check("pubmed: tool ausente -> tool-unavailable declarado, la corrida no truena (§6 no-hang)",
      answer_pipeline._search_pubmed("q", 20, {})[1]["status"] == "tool-unavailable")
answer_pipeline._WS_CACHE.pop(("pubmed_literature.py", "query_pubmed"), None)
_row_ns = answer_pipeline._search_pubmed(None, 20, {})[1]
check("ADR-0078 pubmed: sin query (constructor vacío) -> 'not-searched' declarado, jamás una query vacía; "
      "contadores None (no midió), no 0 (corrector)",
      _row_ns["status"] == "not-searched" and _row_ns["n_returned"] is None and _row_ns["n_new"] is None
      and _row_ns["duplicates_of_europepmc"] is None)
check("corrector: pubmed en 'error' tampoco reporta 0: n_returned/n_new None",
      row_e["n_returned"] is None and row_e["n_new"] is None)
pl_ev = answer_pipeline.path_b_event_payload(
    {"papers": [], "query_sent": "q", "query_source": "entities",
     "n_results_by_source": {"europepmc": 2, "pubmed": 1, "zfin": 0},
     "pubmed_searched": {"status": "success", "n_found_total": 9, "n_new": 1,
                         "duplicates_of_europepmc": ["PMID:1"], "ranking": "x"}})


def _boom_fetch(ident, want_full_text=True):
    raise TimeoutError("read timed out")


_fetch_real2 = answer_pipeline.fetch_paper.fetch_external
_epmc_ledger_real = answer_pipeline.fetch_paper.search_europepmc_ledger
answer_pipeline.fetch_paper.fetch_external = _boom_fetch
answer_pipeline.fetch_paper.search_europepmc_ledger = (
    lambda query, n=5, sort=None, synonym=True: ([], {"source": "europepmc", "status": "no-match",
                                                       "query_sent": query, "n_found": 0, "n_returned": 0}))
answer_pipeline._WS_CACHE[("pubmed_literature.py", "query_pubmed")] = _fake_pubmed
answer_pipeline.path_b = _path_b_real
_led_t = {}
items_t = answer_pipeline.path_b("q", n=5, entities=["wt1a"], sources=("europepmc", "pubmed"),
                                 ledger_out=_led_t)
answer_pipeline.path_b = _path_b_stub
answer_pipeline.fetch_paper.fetch_external = _fetch_real2
answer_pipeline.fetch_paper.search_europepmc_ledger = _epmc_ledger_real
answer_pipeline._WS_CACHE.pop(("pubmed_literature.py", "query_pubmed"), None)
check("un timeout bajando UN paper degrada ESE item (found=false + fetch_error declarado) — "
      "jamas tumba path_b (§6 no-hang; lo destapo la verificacion en vivo)",
      len(items_t) == 2 and all(i["fetched"]["found"] is False for i in items_t)
      and "TimeoutError" in items_t[0]["fetched"]["fetch_error"]
      and all(i["text_provenance"] == "none" and i["abstract"] is None for i in items_t)
      and _led_t["europepmc_searched"]["status"] == "no-match"
      and _led_t["selection"]["n_selected"] == 2,
      f"n={len(items_t)} sel={_led_t.get('selection', {}).get('n_selected')}")

check("el evento stage.path_b lleva el resumen de pubmed (dedup incluido) — un solo log",
      pl_ev["pubmed_searched"]["n_new"] == 1
      and pl_ev["pubmed_searched"]["duplicates_of_europepmc"] == ["PMID:1"])

# path_b sigue stubbeado ([]) -> path_b_bundle es offline y el bloque queda completo y declarado
blk = answer_pipeline.path_b_bundle("pregunta", entities=["osr1"], triggered_by=["motivo"])
check("path_b_bundle: UN constructor del bloque, con fuentes pedidas + contadores + query declarada "
      "(ADR-0078: query_sent = la de EPMC, scope declarado; ledger_version '2'; llaves previas intactas)",
      blk["triggered"] is True and blk["query_sent"] == blk["epmc_query"]
      and blk["query_sent"].startswith("(TITLE:osr1 OR ABSTRACT:osr1)")
      and blk["query_sent_scope"] == "europepmc" and blk["query_source"] == "query-builder-v1:symbols"
      and blk["ledger_version"] == "2" and blk["pubmed_query"].startswith("(osr1[tiab])")
      and blk["zfin_filter"] is None            # 'pregunta' no menciona anatomía: sin filtro, declarado
      and blk["query_builder"]["zfin"]["notes"]["mode"] == "no-filter"
      and blk["n_papers_requested"] == 5 and blk["retmax_requested"] == 20
      and blk["sources_requested"] == list(answer_pipeline.PATH_B_SOURCES)
      and blk["n_results_by_source"] == {"europepmc": 0, "pubmed": 0} and blk["triggered_by"] == ["motivo"]
      and all(k in blk for k in ("papers", "query_source", "tool_universe_directive")))
os.environ["WITT_PATH_B_N_PAPERS"], os.environ["WITT_PATH_B_RETMAX"] = "3", "7"
blk_env = answer_pipeline.path_b_bundle("pregunta", entities=["osr1"])
del os.environ["WITT_PATH_B_N_PAPERS"], os.environ["WITT_PATH_B_RETMAX"]
check("ADR-0078: WITT_PATH_B_N_PAPERS / WITT_PATH_B_RETMAX se leen en tiempo de llamada y el valor "
      "EFECTIVO viaja en el bloque (defaults 5/20 declarados en código)",
      blk_env["n_papers_requested"] == 3 and blk_env["retmax_requested"] == 7
      and answer_pipeline.PATH_B_N_PAPERS_DEFAULT == 5 and answer_pipeline.PATH_B_RETMAX_DEFAULT == 20)
pl = answer_pipeline.path_b_event_payload(
    {"papers": [], "query_sent": "q", "query_source": "entities",
     "n_results_by_source": {"europepmc": 0, "zfin": 1},
     "zfin_searched": [{"symbol": "a", "status": "success"}, {"symbol": "b", "status": "no-match"}]},
    trigger="competence")   # ADR-0080: vocabulario structural|competence (el literal 'confidence' es alias legado)
check("el evento stage.path_b lleva el desglose por fuente + el tally de ZFIN (la traza viva y el "
      "replay leen el MISMO resumen)",
      pl["n_results_by_source"]["zfin"] == 1 and pl["trigger"] == "competence"
      and pl["zfin_status_tally"] == {"no-match": 1, "success": 1})

check("_evidence_ids prefiere evidence_id: dos items sin PMID ya no colapsan en la llave 'paper'",
      runs_mod._evidence_ids({"path_a": {"hits": []},
                              "path_b": {"papers": [{"evidence_id": "ZFIN:A"}, {"evidence_id": "ZFIN:B"},
                                                    {"search_rec": {"pmid": "999"}}]}})
      == ["ZFIN:A", "ZFIN:B", "PMID:999"])

# ---- ADR-0060 / tapon 2: los tres campos §5 que faltaban en el 100% de las corridas ------------------
from lib import reasoning_catalog  # noqa: E402

fa = rec["reasoning"]["framework_applied"]
check("framework_applied: el modelo elige el NOMBRE; la SECCION y el TIER los resuelve la TABLA "
      "(§4: citar el header del tier en vez de la seccion es falla de auditoria, paso 2 veces)",
      fa["name"] == "Logic-LM" and fa["catalog_section"] == "§5" and fa["tier"] == 1,
      f"seccion={fa['catalog_section']} tier={fa['tier']}")
check("framework_applied viaja marcado como SELF-REPORT (§5 nota critica) — jamas como medicion",
      fa["class"] == "self-report" and "introspección" in fa["class_note"])
check("la cita se VERIFICA contra el catalogo: un criterio real hace match",
      fa["criterion_matches_catalog"] is True and fa["criterion_overlap"] >= 0.5,
      f"overlap={fa['criterion_overlap']}")
inventado = reasoning_catalog.resolve("Logic-LM", "porque el modelo lo considero apropiado hoy")
check("un criterio INVENTADO se registra como no-coincidente — se declara, no se rechaza",
      inventado["criterion_matches_catalog"] is False and inventado["catalog_section"] == "§5")
nm = reasoning_catalog.resolve(reasoning_catalog.NONE_MATCHED, "", "pregunta abierta, ninguno aplica")
check("NONE-MATCHED es un destino legitimo: seccion y tier NULOS + la declaracion explicita que pide §4",
      nm["catalog_section"] is None and nm["tier"] is None
      and nm["declared_no_rigorous_framework"] is True)
raro = reasoning_catalog.resolve("Razonamiento Cosmico", "algo")
check("un nombre fuera del vocabulario se registra CRUDO y marcado off_catalog — no se corrige ni se tira",
      raro["name"] == "Razonamiento Cosmico" and raro["off_catalog"] is True
      and raro["catalog_section"] is None)

sf = rec["reasoning"]["structural_frameworks"]
check("structural_frameworks: lo que el PIPELINE aplica, derivado del codigo (contrapeso al self-report)",
      all(x["class"] == "derived-from-code" for x in sf)
      and any(x["catalog_section"] == "§5" and "verify_output" in x["component"] for x in sf))
check("el panel NO se disfraza de Self-Consistency: worst-of-N no es voto por mayoria, y se dice",
      any("NO es Self-Consistency" in x["note"] for x in sf))

ai = {a["agent"]: a for a in rec["agents_invoked"]}
check("agents_invoked DERIVADO de lo que corrio (§11), nunca auto-reportado por el modelo",
      ai["composite-auditor"]["status"] == "invoked"
      and ai["composite-auditor"]["invocation_id"].startswith("panel:")
      and any("verdict:" in e for e in ai["composite-auditor"]["evidence_generated"]))
pre = ai["(preflight §11 sobre el catálogo de agentes)"]
check("el hueco del planner queda DECLARADO en cada corrida: not-assessed != skipped-ad-hoc "
      "(saltarse con justificacion afirmaria un juicio que nadie hizo)",
      pre["status"] == "not-assessed" and "planner" in pre["reason"])

check("alternatives_considered viaja en el registro (§5: la asimetria entre formatos es violacion)",
      rec["alternatives_considered"] == ["wt1b como paralogo redundante: descartado, sin evidencia"])

# ausencia: null, NO lista vacia — y declarada en gap_flags
rv_sin = app.create_run(app.RunBody(question="sin campos §5", entities=[]), authorization=AUTH)
runs_mod.execute_run(db.claim_next_queued(),
                     synthesizer=lambda q, e, pl: {"direct_answer": "x", "stated_confidence": 0.9,
                                                   "absence_kind": "not-applicable", "gap_flags": [],
                                                   "evidence_cited": [], "model": "stub-pelon",
                                                   "usage": {}},
                     panel_caller=_stub_caller_factory(ALL_A))
rsin = app.get_frozen_record(rv_sin["run_id"], authorization=AUTH)
check("§5 ausente -> null (NO [] que se leeria como 'no habia alternativas') + seccion/tier nulos",
      rsin["alternatives_considered"] is None
      and rsin["reasoning"]["framework_applied"]["name"] is None
      and rsin["reasoning"]["framework_applied"]["catalog_section"] is None
      and rsin["reasoning"]["framework_applied"]["class"] == "self-report")
check("el digest del catalogo va en el prompt: sin el, pedir la cita FABRICA numeros de seccion",
      "Logic-LM (Tier 1)" in reasoning_catalog.digest()
      and "NONE-MATCHED" in reasoning_catalog.digest()
      and all(f in reasoning_catalog.ENUM for f in ("Logic-LM", "Self-Consistency")))

# ---- ADR-0061 / tapon 3: el plan declarado ------------------------------------------------------------
from lib import agent_matrix  # noqa: E402

def _fake_planner_ok(question, entities):
    return ({"work_type": "evidence-grounded QA con hipotesis de suficiencia",
             "route": "evidence-run",
             "niches": ["N3", "N4"],
             "agents_applicable": [
                 {"agent": "causal-pruner", "reason": "la pregunta pide set minimo + suficiencia"},
                 {"agent": "hypothesis-generator", "reason": "hipotesis fundada en literatura"},
                 {"agent": "composite-auditor", "reason": "auditoria de la respuesta"}]},
            {"input_tokens": 400, "output_tokens": 120})

HIST_OK = ([{"cost_usd": 0.18, "duration_s": 60, "trigger": None}] * 3
           + [{"cost_usd": 0.21, "duration_s": 95, "trigger": "confidence"}] * 3)

# ADR-0066: query_sparse stubbeado para que el preview del paisaje sea determinista en el gate
_orig_sparse = rag_backend.query_sparse
rag_backend.query_sparse = lambda text, k=5: HitList([_chunk, _chunk], degraded="sparse-by-config")

pl = runs_mod.build_plan("¿osr1 es suficiente para inducir el pronefros ectopicamente?",
                         ["osr1"], planner=_fake_planner_ok, history_rows=HIST_OK)
check("ADR-0066 (plan v3): data_landscape ESTRUCTURAL — preview DI sparse NO-SPEND + fuentes B por hechos "
      "(zfin aplica con entities; tooluniverse declarado hook)",
      pl["plan_version"] == runs_mod.PLAN_VERSION == "4" and pl["data_landscape"]["class"] == "structural"
      and pl["data_landscape"]["di_preview"]["n_hits"] == 2
      and pl["data_landscape"]["di_preview"]["mode"] == "sparse-preview-no-spend"
      and "aplica: 1 símbolo" in pl["data_landscape"]["path_b_sources"]["zfin"]
      and "hook" in pl["data_landscape"]["path_b_sources"]["tooluniverse"])
check("ADR-0066: planner sin clarifying_questions -> [] (pregunta clara — jamás se inventan)",
      pl["judgment"]["clarifying_questions"] == [])


def _planner_ambiguo(question, entities):
    return ({"work_type": "QA con alcance ambiguo", "route": "evidence-run", "niches": ["N3"],
             "agents_applicable": [],
             "clarifying_questions": [
                 {"question": "¿inducción ectópica (GOF) o requerimiento (LOF)?",
                  "why": "cambia qué evidencia busca la Ruta B y qué agentes aplican"}]}, {})


pl_amb = runs_mod.build_plan("¿osr1 induce?", [], planner=_planner_ambiguo, history_rows=HIST_OK)
check("ADR-0066: 1-3 preguntas de clarificación DECLARADAS en el juicio + n_clarifying en stage.plan; "
      "zfin declara NO-aplica sin entities (never-stopper: nada bloquea)",
      len(pl_amb["judgment"]["clarifying_questions"]) == 1
      and pl_amb["judgment"]["clarifying_questions"][0]["why"].startswith("cambia")
      and runs_mod.plan_event_payload(pl_amb)["n_clarifying"] == 1
      and runs_mod.plan_event_payload(pl_amb)["di_preview_hits"] == 2
      and "NO aplica" in pl_amb["data_landscape"]["path_b_sources"]["zfin"])


def _sparse_boom(text, k=5):
    raise RuntimeError("sparse index down")


rag_backend.query_sparse = _sparse_boom
pl_noidx = runs_mod.build_plan("q", [], planner=_fake_planner_ok, history_rows=HIST_OK)
check("ADR-0066: el preview caído se DECLARA unavailable y el plan sigue entero (§6 no-hang)",
      pl_noidx["data_landscape"]["di_preview"]["state"] == "unavailable"
      and pl_noidx["judgment"]["state"] == "declared")
rag_backend.query_sparse = lambda text, k=5: HitList([_chunk, _chunk], degraded="sparse-by-config")
check("plan: lo estructural viene del CODIGO (Ruta A siempre, B condicional con sus 2 decisores, "
      "panel obligatorio con sus 4 lentes)",
      pl["route"]["class"] == "structural" and pl["route"]["path_b"]["conditional"] is True
      and len(pl["route"]["path_b"]["deciders"]) == 2
      and pl["audit"]["required"] is True and len(pl["audit"]["panel"]) == 4)
ags = {a["agent"]: a for a in pl["judgment"]["agents_applicable"]}
check("plan: el modelo elige NOMBRES; el gate y la componentizacion los resuelve la TABLA — ADR-0082 (B/G.7, plan v4): "
      "causal-pruner es hard-rule Y miembro del consejo (componentized True, component 'lib/council.py', will_run "
      "'council-member' — ya no 'skipped-ad-hoc'); hypothesis-generator idem; composite-auditor=componentizado de siempre",
      ags["causal-pruner"]["gate"] == "hard-rule" and ags["causal-pruner"]["componentized"] is True
      and ags["causal-pruner"]["component"] == agent_matrix.COUNCIL_COMPONENT[0] == "lib/council.py"
      and ags["causal-pruner"]["will_run"] == "council-member"
      and ags["hypothesis-generator"]["will_run"] == "council-member"
      and ags["composite-auditor"]["componentized"] is True
      and ags["composite-auditor"]["will_run"] == "runs-always-componentized")
check("plan: nichos resueltos con nombre y fase (§3) + in_scope",
      pl["judgment"]["scope"]["in_scope"] is True
      and any(n["code"] == "N3" and "Embriología" in n["name"] for n in pl["judgment"]["niches"]))
check("plan: estimaciones DETERMINISTAS por escenario (mediana de historia real, clase PROJECTION)",
      pl["estimates"]["di_only"]["state"] == "projected"
      and pl["estimates"]["di_only"]["cost_usd"]["median"] == 0.18
      and pl["estimates"]["with_fallback"]["duration_s"]["median"] == 95
      and "PROJECTION" in pl["estimates"]["class"])
# el defecto que destapo la PRIMERA corrida real del planner: escenario 'projected' con la mediana
# de costo en null porque esas corridas no tenian gasto medido.
HIST_SIN_COSTO = [{"cost_usd": None, "duration_s": 0.05, "trigger": None}] * 3
pl_parcial = runs_mod.build_plan("q", [], planner=_fake_planner_ok, history_rows=HIST_SIN_COSTO)
check("plan: metrica sin medir NO se cubre con la que si existe -> escenario PARCIAL, costo "
      "insufficient-history, duracion projected (una proyeccion sin numero no es proyeccion)",
      pl_parcial["estimates"]["di_only"]["state"] == "partial"
      and pl_parcial["estimates"]["di_only"]["cost_usd"]["state"] == "insufficient-history"
      and pl_parcial["estimates"]["di_only"]["cost_usd"]["n_measured"] == 0
      and pl_parcial["estimates"]["di_only"]["duration_s"]["state"] == "projected")
pl_thin = runs_mod.build_plan("q", [], planner=_fake_planner_ok, history_rows=HIST_OK[:2])
check("plan: historia insuficiente -> '[?] sin historia suficiente' declarado, JAMAS un numero "
      "inventado (LOTE-01)",
      pl_thin["estimates"]["di_only"]["state"] == "insufficient-history"
      and "median" not in pl_thin["estimates"]["di_only"]["cost_usd"])
def _planner_out_of_scope(question, entities):
    return ({"work_type": "pregunta fuera de dominio", "route": "evidence-run", "niches": [],
             "out_of_scope_reason": "no toca ninguno de los seis nichos",
             "agents_applicable": []}, {})
pl_oos = runs_mod.build_plan("¿cual es la capital de Francia?", [], planner=_planner_out_of_scope,
                             history_rows=HIST_OK)
check("plan: cero nichos -> FUERA DE ALCANCE marcado (§3: se marca, el humano decide — no se bloquea)",
      pl_oos["judgment"]["scope"]["in_scope"] is False
      and "humano decide" in pl_oos["judgment"]["scope"]["note"])
def _planner_inventario(question, entities):
    return ({"work_type": "consulta de inventario del sistema", "route": "store-consultation",
             "niches": [], "agents_applicable": []}, {})
pl_inv = runs_mod.build_plan("dime que tenemos en data inamovible", [],
                             planner=_planner_inventario, history_rows=HIST_OK)
check("ADR-0063: consulta META -> route=store-consultation con la GUIA resuelta por tabla "
      "(donde vive la respuesta es un hecho del sistema, no un juicio)",
      pl_inv["judgment"]["route"] == "store-consultation"
      and any("/rack" in d for d in pl_inv["judgment"]["route_guidance"]["doors"])
      and "panel de 4 jueces" in pl_inv["judgment"]["route_guidance"]["note"])
check("ADR-0063: en consulta META el filtro §3 NO APLICA (in_scope=None declarado) — "
      "no-aplica != fuera-de-alcance: la pregunta de Emmanuel no debe salir marcada FUERA DE ALCANCE",
      pl_inv["judgment"]["scope"]["in_scope"] is None
      and "no-aplica" in pl_inv["judgment"]["scope"]["note"])
check("ADR-0063: la ruta viaja en el evento stage.plan",
      runs_mod.plan_event_payload(pl_inv)["route"] == "store-consultation"
      and runs_mod.plan_event_payload(pl)["route"] == "evidence-run")


def _planner_boom(question, entities):
    raise RuntimeError("planner caido")
pl_err = runs_mod.build_plan("q", [], planner=_planner_boom, history_rows=HIST_OK)
check("plan: el juicio FALLA sin tumbar el plan (no-hang §6) — errored declarado, estructura intacta",
      pl_err["judgment"]["state"] == "errored" and "planner caido" in pl_err["judgment"]["error"]
      and pl_err["route"]["class"] == "structural" and pl_err["estimates"]["di_only"]["state"] == "projected")
check("ADR-0066: el paisaje es ESTRUCTURAL — presente aunque el juicio del planner falle",
      pl_err["data_landscape"]["di_preview"]["n_hits"] == 2)

# --- el plan viaja: POST /runs/plan -> POST /runs {plan_id} -> stage.plan -> registro congelado --------
# ADR-0082: este flujo LEGADO corre con WITT_COUNCIL=0 (kill-switch declarado, camino 9d90c01 — L.2). Con el consejo
# encendido, app._council_state_for_new_plan (C6) emite 'not-requested (origin smoke not in WITT_COUNCIL_ORIGINS)' (56 chars)
# y db.create_plan (C4) lo rechaza (VARCHAR(40)) — costura C6<->C4 que C9 debe cerrar (open question de C5); y con
# WITT_COUNCIL_ORIGINS=smoke el plan nace 'queued' y POST /runs responde 409 hasta que el JOB r1 (council_jobs) termine —
# eso lo mide smoke_council_http. La sección ADR-0082 (C5) de abajo mide el consejo ENCENDIDO con la copia F.4 directa.
os.environ["WITT_COUNCIL"] = "0"
runs_mod._default_planner_real = runs_mod._default_planner
runs_mod._default_planner = _fake_planner_ok
prv = app.create_plan(app.PlanBody(question="¿osr1 es suficiente para inducir el pronefros?",
                                   entities=["osr1"]), authorization=AUTH)
runs_mod._default_planner = runs_mod._default_planner_real
check("ADR-0082 (E.3/L.2): con WITT_COUNCIL=0 POST /runs/plan NO encola la ronda 1 — council.state 'disabled (kill-switch "
      "WITT_COUNCIL=0)' y POST /runs no exige ledger",
      prv.get("council", {}).get("state") == "disabled (kill-switch WITT_COUNCIL=0)", json.dumps(prv.get("council", {}).get("state")))
check("POST /runs/plan: devuelve plan_id + plan con juicio declarado",
      bool(prv["plan_id"]) and prv["plan"]["judgment"]["state"] == "declared")
rv_p = app.create_run(app.RunBody(question="¿osr1 es suficiente para inducir el pronefros?",
                                  entities=["osr1"], plan_id=prv["plan_id"]), authorization=AUTH)
check("POST /runs con plan_id: la vista declara plan_declared=true",
      rv_p["plan_declared"] is True)
err409 = _http_error(app.create_run, app.RunBody(question="otra", plan_id=prv["plan_id"]),
                     authorization=AUTH)
check("un plan se consume UNA vez: re-usarlo -> 409 plan_already_used (un juicio viejo no pasa por fresco)",
      err409 == 409)
check("plan_id inexistente -> 404 (no se inventa un plan)",
      _http_error(app.create_run, app.RunBody(question="q", plan_id="nope"), authorization=AUTH) == 404)
claimed_p = db.claim_next_queued()
runs_mod.execute_run(claimed_p, synthesizer=_stub_synth, panel_caller=_stub_caller_factory(ALL_A))
ev_p = app.get_events(rv_p["run_id"], after=0, authorization=AUTH)["events"]
tipos_p = [e["type"] for e in ev_p]
stages_p = [t for t in tipos_p if t.startswith("stage.")]
check("ADR-0081 (B): stage.models es el PRIMER evento de etapa (qué va a correr ANTES de gastar) y stage.plan el segundo "
      "(el boceto M3 lo pinta como primera línea del plan)",
      stages_p[:2] == ["stage.models", "stage.plan"]
      and next(e for e in ev_p if e["type"] == "stage.plan")["payload"]["agents"]
          == ["causal-pruner", "hypothesis-generator", "composite-auditor"], f"stages={stages_p[:3]}")
rec_p = app.get_frozen_record(rv_p["run_id"], authorization=AUTH)
check("el planner GASTA y su gasto entra al total (M8 cuadra) + aparte en plan_judgment: "
      "dejarlo fuera haria irreconciliable el consumo (misma disciplina que LOTE-01·A4)",
      rec_p["token_usage"]["plan_judgment"] is not None
      and rec_p["token_usage"]["plan_judgment"]["in"] == 400
      # el planner y el juez de la lente correctness son el MISMO modelo en ambas generaciones de la tabla (ADR-0081:
      # ambos se LEEN del registro — plan.judgment.planner.model y la fila correctness del panel — no de un literal):
      # agregar por modelo es lo correcto (410 = 400 del plan + 10 del juez), y plan_judgment lo desglosa aparte
      and rec_p["plan"]["judgment"]["planner"]["model"]
          == next(r["reviewer"] for r in rec_p["audit"]["panel"] if r["lens"] == "correctness")
      and rec_p["token_usage"]["by_model"][rec_p["plan"]["judgment"]["planner"]["model"]]["in"] == 410
      and rec_p["token_usage"]["input_tokens"] >= 400,
      f"plan_judgment={rec_p['token_usage']['plan_judgment']} by_model={rec_p['token_usage']['by_model']}")
check("una corrida SIN plan no inventa plan_judgment: null declarado",
      rec["token_usage"]["plan_judgment"] is None)
check("registro 1.4: el plan viaja CONGELADO + plan_question_matches_run=true",
      rec_p["plan_declared"] is True and rec_p["plan"]["judgment"]["state"] == "declared"
      and rec_p["plan_question_matches_run"] is True)
ai_p = {a["agent"]: a for a in rec_p["agents_invoked"]}
check("agents_invoked CON plan bajo kill-switch WITT_COUNCIL=0 (ADR-0082 L.2 iii): los miembros del consejo que el planner "
      "juzgó aplicables (causal-pruner, hypothesis-generator) NO aparecen (matriz v1.3: componentizados → el camino de 9d90c01 "
      "los omite) y la fila agregada '(consejo de criterio — cm-1)' es not-applicable 'kill-switch WITT_COUNCIL=0'; sigue la fila "
      "agregada 'resto del catálogo' — y NO hay not-assessed ni skipped-ad-hoc (los tres aplicables son componentizados)",
      "causal-pruner" not in ai_p and "hypothesis-generator" not in ai_p
      and ai_p[runs_mod.COUNCIL_AGENT_ROW]["status"] == "not-applicable"
      and ai_p[runs_mod.COUNCIL_AGENT_ROW]["reason"] == "kill-switch WITT_COUNCIL=0"
      and any(a["status"] == "not-applicable" and "resto del catálogo" in a["agent"]
              for a in rec_p["agents_invoked"])
      and not any(a["status"] in ("not-assessed", "skipped-ad-hoc") for a in rec_p["agents_invoked"])
      and rec_p["council"]["state"] == "disabled (kill-switch WITT_COUNCIL=0)"
      and rec_p["plan"]["judgment"]["agents_applicable"][0]["will_run"] == "council-member",
      json.dumps([(a["agent"], a["status"]) for a in rec_p["agents_invoked"]]))
check("agents_invoked SIN plan (corridas previas de este gate): el hueco sigue not-assessed",
      any(a["status"] == "not-assessed" for a in rec["agents_invoked"])
      and rec["plan_declared"] is False and rec["plan"] is None)
check("matriz: derogaciones y suspensiones viajan en la tabla (html-report ADR-0046 · "
      "investor-relations ADR-0008)",
      "ADR-0046" in agent_matrix.AGENTS["html-report-emitter"]["note"]
      and "SUSPENDIDO" in agent_matrix.AGENTS["investor-relations-drafter"]["note"])
os.environ.pop("WITT_COUNCIL", None)      # fin del flujo legado bajo kill-switch (ADR-0082)
rag_backend.query_sparse = _orig_sparse   # fin de la seccion del planner (ADR-0066)

# ---- 6. cierre explicito ------------------------------------------------------------------------------
res = app.close_run(RID, authorization=AUTH)
rec2 = app.get_frozen_record(RID, authorization=AUTH)
check("close: awaiting_closure -> closed + frozen_at + closed_by en el registro",
      res["closed"] and db.get_run(RID)["state"] == "closed"
      and rec2.get("frozen_at") and rec2.get("closed_by") == "natalia")
check("close doble -> 409 (el cierre es unico)", _http_error(app.close_run, RID, authorization=AUTH) == 409)

# ---- 7. cancelacion como estado de primera clase -----------------------------------------------------
rv = app.create_run(app.RunBody(question="cancel me", entities=[]), authorization=AUTH)
RID2 = rv["run_id"]
app.cancel_run(RID2, body=app.CancelBody(reason="cambie de opinion"), authorization=AUTH)
check("cancel de un run queued -> cancelled inmediato (no failed, no muerto)",
      db.get_run(RID2)["state"] == "cancelled")
v2 = app.get_run(RID2, authorization=AUTH)
check("LOTE-01·A3: la cancelacion registra autor (sesion) y razon, visibles en la vista",
      v2["cancelled_by"] == "natalia" and v2["cancel_reason"] == "cambie de opinion")
rv = app.create_run(app.RunBody(question="cancel mid-flight", entities=[]), authorization=AUTH)
RID3 = rv["run_id"]
claimed = db.claim_next_queued()


def _synth_then_cancel(question, evidence, pass_label):
    db.request_cancel(RID3)   # la cancelacion llega mientras la corrida trabaja
    return _stub_synth(question, evidence, pass_label)


runs_mod.execute_run(claimed, synthesizer=_synth_then_cancel,
                     panel_caller=_stub_caller_factory(ALL_A))
check("cancel en vuelo: se detecta en la frontera de etapa -> cancelled (jamas disfrazado de failed)",
      db.get_run(RID3)["state"] == "cancelled" and db.get_run(RID3)["error"] is None)
v3 = app.get_run(RID3, authorization=AUTH)
check("LOTE-01·A4: lo gastado ANTES de la cancelacion queda visible (pass1 = 100 in / 50 out)",
      v3["token_usage"] is not None and v3["token_usage"]["input_tokens"] == 100
      and v3["token_usage"]["output_tokens"] == 50 and "cost_class" in v3["token_usage"])

# ---- 8. fallo honesto ---------------------------------------------------------------------------------
rv = app.create_run(app.RunBody(question="explode", entities=[]), authorization=AUTH)
claimed = db.claim_next_queued()


def _synth_boom(question, evidence, pass_label):
    raise ValueError("synth exploded (smoke)")


runs_mod.execute_run(claimed, synthesizer=_synth_boom, panel_caller=_stub_caller_factory(ALL_A))
run = db.get_run(rv["run_id"])
check("fallo -> failed con error registrado + evento level=error",
      run["state"] == "failed" and "synth exploded" in (run["error"] or ""))
vf = app.get_run(rv["run_id"], authorization=AUTH)
check("LOTE-01·A4: una corrida failed tambien expone su token_usage (aqui 0, medido no ausente)",
      vf["token_usage"] is not None and vf["token_usage"]["input_tokens"] == 0
      and "cost_class" in vf["token_usage"])

# ---- ADR-0067: ciclo de revisión acotado (adopción del loop reviewer->re-delegate de VB) --------------
def _stub_caller_rounds(rounds):
    """caller por RONDAS de panel: cada 4 llamadas (un panel completo) avanza a la siguiente ronda."""
    n = {"i": 0}

    def _caller(member, system, user_text):
        idx = min(n["i"] // 4, len(rounds) - 1)
        n["i"] += 1
        return ({"verdict": rounds[idx][member["lens"]], "caught": f"catch-{member['lens']}",
                 "correction_applied": "cita el chunk exacto", "confidence": 0.9,
                 "reasons": ["falta grounding"]},
                {"input_tokens": 10, "output_tokens": 5})
    return _caller


ALL_R = {k: "REVISE" for k in ALL_A}
_rev_seen = {"labels": [], "findings": False}


def _synth_with_revision(question, evidence, pass_label):
    _rev_seen["labels"].append(pass_label)
    if pass_label == "revision":
        _rev_seen["findings"] = bool(evidence.get("revision_input", {}).get("panel_findings"))
        base = _mk_synth({})(question, evidence, pass_label)
        return {**base, "direct_answer": "REVISED: wt1a marks the pronephros (chunk c000).",
                "stated_confidence": 0.85}
    return _mk_synth({"pass1": 0.8})(question, evidence, pass_label)


rv = app.create_run(app.RunBody(question="revision cycle run", entities=[]), authorization=AUTH)
claimed = db.claim_next_queued()
runs_mod.execute_run(claimed, synthesizer=_synth_with_revision,
                     panel_caller=_stub_caller_rounds([ALL_R, ALL_A]))
rec_r = app.get_frozen_record(rv["run_id"], authorization=AUTH)
ev_r = [e["type"] for e in app.get_events(rv["run_id"], after=0, authorization=AUTH)["events"]]
check("ADR-0067a: REVISE -> UNA revisión (hallazgos del panel como insumo tipado) -> re-auditoría -> "
      "APPROVE terminal",
      rec_r["revision"]["performed"] is True and rec_r["revision"]["initial_verdict"] == "REVISE"
      and rec_r["revision"]["final_verdict"] == "APPROVE"
      and rec_r["decision_state"]["state"] == "AUDIT_APPROVED"
      and _rev_seen["findings"] is True and "revision" in _rev_seen["labels"]
      and len(rec_r["revision"]["findings_used"]) == 4)
check("ADR-0067b: NADA se borra — answer_initial + audit_initial persisten junto a la versión final",
      rec_r["answer_initial"]["direct_answer"].startswith("wt1a (ENSDARG")
      and rec_r["audit_initial"]["verdict"] == "REVISE"
      and rec_r["answer"]["direct_answer"].startswith("REVISED:")
      and rec_r["audit"]["verdict"] == "APPROVE"
      and rec_r["confidence"]["revision"] == 0.85 and rec_r["confidence"]["final"] == 0.85
      and rec_r["render_contract_version"] == runs_mod.RENDER_CONTRACT_VERSION)
check("ADR-0067c: la traza lleva las DOS rondas (revision_round 0/1) + stage.revision.start + "
      "stage.synthesize.revision (cap duro = 1)",
      ev_r.count("stage.audit.verdict") == 2 and "stage.revision.start" in ev_r
      and "stage.synthesize.revision" in ev_r and rec_r["revision"]["cap"] == 1)
check("ADR-0067d: el usage cuenta AMBOS paneles (8 jueces) y la pasada de revisión (M8 cuadra); ADR-0080: sin plan "
      "también pass2 -> stub-synth 300 (pass1 + pass2 + revisión)",
      rec_r["usage_raw"]["panel_total"] == {"input_tokens": 80, "output_tokens": 40}
      and rec_r["token_usage"]["by_model"].get("stub-synth", {}).get("in") == 300)

rv = app.create_run(app.RunBody(question="revision fails again", entities=[]), authorization=AUTH)
claimed = db.claim_next_queued()
runs_mod.execute_run(claimed, synthesizer=_synth_with_revision,
                     panel_caller=_stub_caller_rounds([ALL_R, ALL_R]))
rec_rr = app.get_frozen_record(rv["run_id"], authorization=AUTH)
ev_rr = [e["type"] for e in app.get_events(rv["run_id"], after=0, authorization=AUTH)["events"]]
check("ADR-0067e: REVISE tras la revisión -> AUDIT_REJECTED terminal honesto (jamás una 2ª iteración)",
      rec_rr["revision"]["performed"] is True and rec_rr["revision"]["final_verdict"] == "REVISE"
      and rec_rr["decision_state"]["state"] == "AUDIT_REJECTED"
      and ev_rr.count("stage.audit.verdict") == 2)

os.environ["WITT_REVISION_CYCLE"] = "0"
rv = app.create_run(app.RunBody(question="kill switch run", entities=[]), authorization=AUTH)
claimed = db.claim_next_queued()
runs_mod.execute_run(claimed, synthesizer=_mk_synth({"pass1": 0.8}),
                     panel_caller=_stub_caller_factory({**ALL_A, "correctness": "REVISE"}))
rec_ks = app.get_frozen_record(rv["run_id"], authorization=AUTH)
ev_ks = [e["type"] for e in app.get_events(rv["run_id"], after=0, authorization=AUTH)["events"]]
os.environ["WITT_REVISION_CYCLE"] = "1"
check("ADR-0067f: kill-switch WITT_REVISION_CYCLE=0 -> comportamiento pre-ADR (REVISE terminal, "
      "skipped_reason declarado, un solo panel)",
      rec_ks["revision"]["enabled"] is False and rec_ks["revision"]["performed"] is False
      and "kill-switch" in rec_ks["revision"]["skipped_reason"]
      and rec_ks["decision_state"]["state"] == "AUDIT_REJECTED"
      and ev_ks.count("stage.audit.verdict") == 1)

rv = app.create_run(app.RunBody(question="thin panel run", entities=[]), authorization=AUTH)
claimed = db.claim_next_queued()
runs_mod.execute_run(claimed, synthesizer=_mk_synth({"pass1": 0.8}),
                     panel_caller=_stub_caller_factory(
                         {"correctness": "APPROVE", "overclaim": RuntimeError("judge down"),
                          "evidence-grounding": RuntimeError("judge down"), "reproducibility": "APPROVE"}))
rec_tp = app.get_frozen_record(rv["run_id"], authorization=AUTH)
check("ADR-0067g: REVISE por panel_incomplete NO dispara revisión (el problema son los jueces, no la "
      "respuesta) — skipped_reason lo declara",
      rec_tp["revision"]["performed"] is False
      and "panel_incomplete" in rec_tp["revision"]["skipped_reason"]
      and rec_tp["decision_state"]["state"] == "AUDIT_REJECTED")

check("ADR-0067h: una corrida SIN revisión declara el bloque en 3 estados (null-declarado, no ausencia)",
      rec["revision"]["performed"] is False and rec["audit_initial"] is None
      and rec["answer_initial"] is None and rec["confidence"]["revision"] is None)

# ---- ADR-0073: el PDF de servidor — del JSON congelado, jamás de la página ----------------------------
import record_pdf  # noqa: E402

pdf_ok = record_pdf.build_pdf(rec, compress=False)
check("ADR-0073a: PDF generado del registro congelado — %PDF + banda de modo con PALABRAS completas",
      pdf_ok[:5] == b"%PDF-" and b"SELLADA" in pdf_ok and b"CONGELADO" in pdf_ok
      and b"APROBADA" in pdf_ok and b"PREGUNTA" in pdf_ok)
pdf_rev = record_pdf.build_pdf(rec_r, compress=False)
check("ADR-0073b: el ciclo de revisión viaja al PDF — ronda 0 completa y marcada SUPERADA (nada se borra)",
      b"RONDA 0" in pdf_rev and b"SUPERADA" in pdf_rev and b"REVISION" in pdf_rev)
try:
    record_pdf.build_pdf({**rec, "question_matches_run": False})
    ident_ok = False
except ValueError:
    ident_ok = True
check("ADR-0073c: identidad rota -> el PDF NO se genera (la misma regla que la hoja, ADR-0044)",
      ident_ok)
pdf_ni = record_pdf.build_pdf({k: v for k, v in rec.items() if k != "retrieval_summary"},
                              compress=False)
check("ADR-0073d: sin retrieval_summary la banda dice NO INSTRUMENTADO con palabras completas "
      "(jamás se apoya en punteados)",
      b"NO INSTRUMENTADO" in pdf_ni)
resp_pdf = app.get_record_pdf(RID, authorization=AUTH)
check("ADR-0073e: GET /runs/{id}/record.pdf sirve application/pdf con Content-Disposition de descarga",
      resp_pdf.media_type == "application/pdf" and bytes(resp_pdf.body)[:5] == b"%PDF-"
      and "registro_" in resp_pdf.headers.get("content-disposition", ""))
check("ADR-0073f: el pie declara el canal único + el saneo latin-1 (disciplina de exportación)",
      b"latin-1" in pdf_ok and b"UNICO" in pdf_ok)

# ---- LOTE-02·2: /usage — la suma vive en el SERVIDOR (M8) --------------------------------------------
us = app.usage(authorization=AUTH)
check("/usage: totales + by_user + by_model + most_expensive + costo PROJECTION",
      us["n_runs"] >= 6 and us["n_runs_with_usage"] >= 5
      and us["by_user"]["natalia"]["n_runs"] == us["n_runs_with_usage"]
      and us["by_model"]["stub-synth"]["in"] >= 700
      and us["most_expensive"] is not None and "PROJECTION" in us["cost_class"]
      and "attribution" in us["rack_embeddings"],
      f"n={us['n_runs']} con_usage={us['n_runs_with_usage']} stub_in={us['by_model']['stub-synth']['in']}")
us2 = app.usage(from_="2099-01-01", authorization=AUTH)
check("/usage con ventana vacia -> denominador honesto (0 corridas, 0 con usage)",
      us2["n_runs"] == 0 and us2["n_runs_with_usage"] == 0)

# =====================================================================================================
# ---- ADR-0078: higiene de Ruta A y B (integración de las rebanadas I1–I5) -----------------------------
# Todo offline: red de EPMC/PubMed/Alliance stubbeada o servida desde el fixture REAL del repo; fetch
# stubbeado con archivos en el tmp del gate; cero modelo, cero mutación de mcp_cache.
# =====================================================================================================
import datetime as _dt  # noqa: E402
import urllib.parse  # noqa: E402

# --- A. Ruta A: el fragmento que viaja al sintetizador ya no es [:140] ----------------------------------
_long = Hit(doc_id="CORPUS-2026-0009#c001", type="chunk", score=0.8,
            text=("x" * 3000) + " pronephros", metadata={})
rag_backend.query = lambda text, k=6: HitList([_long, _chunk], degraded=None)
pa = answer_pipeline.path_a("q")
h0, h1 = pa["hits"][0], pa["hits"][1]
check("ADR-0078 Ruta A: el hit viaja con WITT_PATH_A_CHARS (2400, no 140) y DECLARA el corte — "
      "text_offsets [0,2400], text_sha256 del fragmento, text_omitted=True, text_hit_chars, text_source",
      len(h0["text"]) == 2400 and h0["text_offsets"] == [0, 2400] and h0["text_omitted"] is True
      and h0["text_hit_chars"] == 3011
      and h0["text_sha256"] == hashlib.sha256(h0["text"].encode("utf-8")).hexdigest()
      and h0["text_source"] == "index-hit" and pa["text_cap_chars"] == 2400
      # corrector: la PROCEDENCIA del tope dice de verdad de dónde vino (default por env ausente, no 'env')
      and pa["text_cap_source"] == "default-unset:WITT_PATH_A_CHARS" and answer_pipeline.PATH_A_CHARS_DEFAULT == 2400,
      f"len={len(h0['text'])} omitted={h0['text_omitted']} src={pa['text_cap_source']}")
check("Ruta A: un hit corto va ÍNTEGRO (text_omitted=False, offsets = su largo) — tres estados, no un "
      "recorte silencioso",
      h1["text"] == "pronephros evidence" and h1["text_omitted"] is False
      and h1["text_offsets"] == [0, 19] and h1["text_hit_chars"] == 19)
os.environ["WITT_PATH_A_CHARS"] = "100"
pa100 = answer_pipeline.path_a("q")
del os.environ["WITT_PATH_A_CHARS"]
check("Ruta A: WITT_PATH_A_CHARS se lee en tiempo de llamada (100 -> fragmento de 100, cap declarado, fuente 'env:…')",
      len(pa100["hits"][0]["text"]) == 100 and pa100["text_cap_chars"] == 100
      and pa100["hits"][0]["text_offsets"] == [0, 100] and pa100["hits"][0]["text_omitted"] is True
      and pa100["text_cap_source"] == "env:WITT_PATH_A_CHARS")
os.environ["WITT_PATH_A_CHARS"] = "abc"
pa_bad = answer_pipeline.path_a("q")
del os.environ["WITT_PATH_A_CHARS"]
check("corrector: env inválida ('abc') -> default 2400 con fuente 'default-invalid-env:WITT_PATH_A_CHARS' "
      "(antes el bundle decía que vino de la env)",
      pa_bad["text_cap_chars"] == 2400 and pa_bad["text_cap_source"] == "default-invalid-env:WITT_PATH_A_CHARS"
      and answer_pipeline.path_a("q", max_chars=50)["text_cap_source"] == "caller")
rag_backend.query = lambda text, k=6: HitList([_chunk], degraded=None)

# --- B. el constructor de queries POR FUENTE (lib/search_queries cableado) -----------------------------
qb_syn = answer_pipeline.build_source_queries("¿Qué induce el pronefros?", ["osr1"],
                                              query="osr1 zebrafish glomerulus induction",
                                              query_source="synthesizer")
check("ADR-0078 queries: la formulación EN del sintetizador alimenta al constructor (anatomía detectada "
      "en ELLA) y se declara en inputs; tres sintaxis distintas para tres índices",
      qb_syn["inputs"]["question_en_source"] == "synthesizer"
      and qb_syn["inputs"]["question_en"] == "osr1 zebrafish glomerulus induction"
      and "glomerulus" in qb_syn["europepmc"]["query"] and "glomerulus[tiab]" in qb_syn["pubmed"]["query"]
      # corrector: UNA política — ES aporta 'pronephr', EN aporta 'glomer'; los tres índices lo declaran 'from-both'
      and qb_syn["zfin"]["query"] == "pronephr|glomer"
      and all(qb_syn[i]["notes"]["anatomy"] == "from-both" for i in ("pubmed", "europepmc", "zfin"))
      and "pronephros[tiab]" in qb_syn["pubmed"]["query"]
      and qb_syn["query_source"] == "query-builder-v1:symbols"
      and qb_syn["pubmed"]["query"] != qb_syn["europepmc"]["query"])
qb_rt = answer_pipeline.build_source_queries("¿Qué induce el pronefros?", ["osr1"],
                                             query=qb_syn["europepmc"]["query"],
                                             query_source="query-builder-v1:symbols")
check("queries: una query que ya salió del constructor (runs.py la devuelve) se RECONSTRUYE de la "
      "pregunta+símbolos, no se usa como question_en (evitaría meter 'TITLE:' como término)",
      qb_rt["inputs"]["question_en"] is None and qb_rt["inputs"]["question_en_source"] is None
      and "TITLE:osr1" in qb_rt["europepmc"]["query"])
qb_empty = answer_pipeline.build_source_queries("", [])
check("queries: sin símbolos NI pregunta -> query None DECLARADA en las dos fuentes de literatura "
      "(modo 'empty'), jamás una cadena vacía",
      qb_empty["europepmc"]["query"] is None and qb_empty["pubmed"]["query"] is None
      and qb_empty["query_source"] == "query-builder-v1:empty")

# --- C. Ruta B de punta a punta con la red stubbeada: pool, dedup, selección, contenido, ledger v2 ------
_FT_PATH = TMP / "mcp_cache" / "raw_paper_PMC111_20260914.txt"
_P1 = ("Introduction. " + "Zebrafish embryos develop rapidly and are transparent, which makes them a "
       "convenient model for wt1a studies. " * 5)
_P2 = ("Methods. " + "Embryos were raised at 28.5 C and staged by hours post fertilization according "
       "to standard tables. " * 6)
_P3 = ("Results. wt1a morphants lacked pronephros glomerulus formation; the pronephric duct was present "
       "but the glomerulus failed to form. Podocyte markers were absent in wt1a morphants.")
_P4 = ("Discussion. " + "These observations suggest a conserved role in organ development that merits "
       "further study in other vertebrates. " * 6)
_FULLTEXT = "\n\n".join([_P1, _P2, _P3, _P4])
assert len(_FULLTEXT) > 1500, "el texto de prueba debe exceder el tope para que el recorte aplique"

_EPMC_RECS = [
    {"epmc_id": "1", "source": "MED", "pmid": "11111111", "pmcid": "PMC111", "doi": "10.1000/AAA",
     "title": "wt1a in pronephros", "year": "2020", "journal": "Development", "is_oa": True,
     "abstract": "wt1a is required for pronephros formation in zebrafish.", "cited_by": 10},
    {"epmc_id": "2", "source": "MED", "pmid": "22222222", "pmcid": None, "doi": "https://doi.org/10.1000/bbb",
     "title": "closed access paper", "year": "2019", "journal": "X", "is_oa": False,
     "abstract": None, "cited_by": 3},
    {"epmc_id": "3", "source": "PPR", "pmid": None, "pmcid": None, "doi": "10.1000/BBB",
     "title": "preprint duplicado por DOI", "year": "2019", "journal": None, "is_oa": True,
     "abstract": "dup", "cited_by": 0},
    {"epmc_id": "4", "source": "MED", "pmid": "44444444", "pmcid": "PMC444", "doi": None,
     "title": "second OA", "year": "2021", "journal": "Dev Biol", "is_oa": True,
     "abstract": "A glomerulus paper about podocytes.", "cited_by": 1},
    {"epmc_id": "5", "source": "MED", "pmid": "55555555", "pmcid": None, "doi": None,
     "title": "fifth", "year": "2018", "journal": "Y", "is_oa": False, "abstract": None, "cited_by": 0},
    {"epmc_id": "6", "source": "MED", "pmid": "66666666", "pmcid": None, "doi": None,
     "title": "sixth", "year": "2017", "journal": "Z", "is_oa": False, "abstract": None, "cited_by": 0},
]
_epmc_calls = []


def _fake_epmc_ledger(query, n=5, sort=None, synonym=True):
    _epmc_calls.append({"query": query, "n": n, "sort": sort, "synonym": synonym})
    return list(_EPMC_RECS), {"source": "europepmc", "status": "success", "query_sent": query,
                              "n_found": 6, "n_returned": 6, "elapsed_s": 0.01, "sort": "RELEVANCE",
                              "synonym": True, "throttle": "net_throttle", "throttle_slept_s": 0.0,
                              "contact": "unset"}


def _fake_pubmed_pool(query, limit=None, retmax=None):
    out = _fake_pubmed(query, limit, retmax)
    out["data"]["records"] = [
        {"pmid": "22222222", "title": "closed access paper", "year": "2019", "journal": "X"},
        {"pmid": "77777777", "title": "solo en pubmed", "year": "2022", "journal": "W"},
        {"pmid": "11111111", "title": "wt1a in pronephros", "year": "2020", "journal": "Development"},
    ]
    return out


def _fake_fetch_content(ident, want_full_text=True):
    if ident == "PMID:11111111":
        _FT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _FT_PATH.write_text(_FULLTEXT, encoding="utf-8")
        return {"found": True, "full_text": True, "n_chunks": 4, "raw_cached": [str(_FT_PATH)],
                "raw_ref": {"filename": _FT_PATH.name},
                "record": {"abstract": "wt1a is required for pronephros formation in zebrafish."},
                "cache_hit": False, "cached_at": None, "fetched_at": "2026-09-14T00:00:00Z",
                "cache_ttl_days": 7.0,
                "search_ledger": {"source": "europepmc", "status": "success", "contact": "unset"}}
    if ident == "PMID:44444444":
        return {"found": True, "full_text": False, "n_chunks": 1, "raw_cached": [], "raw_ref": None,
                "record": {"abstract": "A glomerulus paper about podocytes."},
                "cache_hit": True, "cached_at": "2026-09-10T00:00:00Z", "cached_at_source": "fetched_at",
                "cache_age_days": 4.0}
    return {"found": False, "fetch_error": "TimeoutError: read timed out"}


answer_pipeline.fetch_paper.search_europepmc_ledger = _fake_epmc_ledger
answer_pipeline.fetch_paper.fetch_external = _fake_fetch_content
answer_pipeline._WS_CACHE[("pubmed_literature.py", "query_pubmed")] = _fake_pubmed_pool
answer_pipeline.path_b = _path_b_real
blk_b = answer_pipeline.path_b_bundle("is wt1a required for pronephros glomerulus formation?",
                                      entities=["wt1a"], n=3, sources=("europepmc", "pubmed"),
                                      triggered_by=["smoke"])
answer_pipeline.path_b = _path_b_stub

ep = blk_b["europepmc_searched"]
check("ADR-0078 EPMC: la búsqueda corre por search_europepmc_ledger -> `europepmc_searched` EXISTE en el "
      "bloque con status + query_sent + n_found + n_candidates (antes no había ledger de EPMC)",
      ep["status"] == "success" and ep["query_sent"] == blk_b["epmc_query"] and ep["n_found"] == 6
      and ep["n_returned"] == 6 and ep["n_candidates"] == 5 and ep["retmax_sent"] == 20
      and _epmc_calls[-1]["n"] == 20,
      f"epmc={ {k: ep.get(k) for k in ('status', 'n_found', 'n_candidates')} }")
sel = blk_b["selection"]
check("ADR-0078 dedup: por PMID (pubmed vs EPMC) Y por DOI normalizado (https://doi.org/10.1000/bbb == "
      "10.1000/BBB) — n_candidates 6, n_duplicates 3, cada duplicado dice DE QUIÉN y POR QUÉ llave",
      sel["n_candidates"] == 6 and sel["n_duplicates"] == 3
      and any(d["matched_key"] == "DOI:10.1000/bbb" and d["of"] == "PMID:22222222" for d in sel["duplicates"])
      and blk_b["pubmed_searched"]["duplicates_of_europepmc"] == ["PMID:22222222", "PMID:11111111"]
      and blk_b["pubmed_searched"]["n_new"] == 1 and blk_b["pubmed_searched"]["n_candidates"] == 1,
      f"dups={[(d['duplicate'], d['matched_key']) for d in sel['duplicates']]}")
ids_sel = [p["evidence_id"] for p in blk_b["papers"]]
check("ADR-0078 selección: regla DECLARADA 'oa-with-pmcid-first, then source order' — n_selected 3 <= n, "
      "OA+PMCID primero (rank 1-2), luego orden de fuente; los NO elegidos quedan listados",
      sel["rule"] == "oa-with-pmcid-first, then source order" and sel["n_requested"] == 3
      and sel["n_selected"] == 3 and len(blk_b["papers"]) == 3
      and ids_sel == ["PMID:11111111", "PMID:44444444", "PMID:22222222"]
      and [p["selection_rank"] for p in blk_b["papers"]] == [1, 2, 3]
      and sel["not_selected"] == ["PMID:55555555", "PMID:66666666", "PMID:77777777"]
      and blk_b["n_results_by_source"] == {"europepmc": 3, "pubmed": 0},
      f"sel={ids_sel} not={sel['not_selected']}")
p_ft, p_ab, p_none = blk_b["papers"]
check("ADR-0078 contenido: con texto completo cacheado el item lleva `text_excerpt` por solapamiento "
      "léxico (párrafos con términos de la query, en orden del documento, <= 1500), provenance "
      "'fulltext-excerpt', regla y omisión declaradas",
      p_ft["text_provenance"] == "fulltext-excerpt"
      and p_ft["text_excerpt_rule"] == "top-paragraphs-by-lexical-overlap"
      and p_ft["text_excerpt"].startswith("Introduction.") and "Results. wt1a morphants" in p_ft["text_excerpt"]
      and "Methods." not in p_ft["text_excerpt"] and "Discussion." not in p_ft["text_excerpt"]
      and len(p_ft["text_excerpt"]) <= 1500 and p_ft["text_excerpt_chars"] == len(p_ft["text_excerpt"])
      and p_ft["text_excerpt_omitted"] is True and p_ft["text_source_chars"] == len(_FULLTEXT)
      and p_ft["text_excerpt_cap_chars"] == 1500,
      f"rule={p_ft['text_excerpt_rule']} chars={p_ft['text_excerpt_chars']}")
check("ADR-0078 contenido: `abstract` viaja en el item (del search_rec de EPMC) — antes se descargaba y "
      "se tiraba; el search_rec conserva sus 8 llaves de metadatos",
      p_ft["abstract"] == "wt1a is required for pronephros formation in zebrafish."
      and set(p_ft["search_rec"]) == {"pmid", "pmcid", "doi", "title", "year", "journal", "is_oa", "cited_by"})
check("ADR-0078 contenido: sin texto completo el excerpt es el abstract entero (rule 'full', provenance "
      "'abstract'); sin nada -> provenance 'none' con abstract null DECLARADO (tres estados)",
      p_ab["text_provenance"] == "abstract" and p_ab["text_excerpt_rule"] == "full"
      and p_ab["text_excerpt"] == "A glomerulus paper about podocytes." and p_ab["text_excerpt_omitted"] is False
      and p_none["text_provenance"] == "none" and p_none["text_excerpt"] is None
      and p_none["abstract"] is None and p_none["text_excerpt_rule"] == "none")
check("ADR-0078 fetched: la caché de LECTURA se declara (cache_hit/cached_at/fetched_at) SOLO cuando el "
      "fetch la midió — el item no bajado lleva fetch_error y NINGUNA llave de caché (ausente != false)",
      p_ft["fetched"]["cache_hit"] is False and p_ft["fetched"]["fetched_at"] == "2026-09-14T00:00:00Z"
      and p_ft["fetched"]["search_ledger"]["status"] == "success"
      and p_ab["fetched"]["cache_hit"] is True and p_ab["fetched"]["cached_at"] == "2026-09-10T00:00:00Z"
      and p_none["fetched"]["found"] is False and "TimeoutError" in p_none["fetched"]["fetch_error"]
      and "cache_hit" not in p_none["fetched"])
check("ADR-0078 ledger v2: llaves NUEVAS + TODAS las previas que la Traza lee (pubmed_searched, "
      "zfin_searched si corrió, n_results_by_source, query_sent, query_source, sources_requested)",
      blk_b["ledger_version"] == "2" and blk_b["query_sent_scope"] == "europepmc"
      and blk_b["query_sent"] == blk_b["epmc_query"] and "[tiab]" in blk_b["pubmed_query"]
      and blk_b["zfin_filter"] == "pronephr|glomer"
      and blk_b["query_builder"]["builder_version"] == "1"
      and all(k in blk_b for k in ("pubmed_searched", "n_results_by_source", "query_sent", "query_source",
                                    "sources_requested", "papers", "triggered", "triggered_by",
                                    "tool_universe_directive", "europepmc_searched", "selection")),
      f"zfin_filter={blk_b['zfin_filter']!r}")
pl_b = answer_pipeline.path_b_event_payload(blk_b, trigger="structural")
check("el evento stage.path_b lleva el resumen NUEVO (europepmc_searched, selection, ledger_version) "
      "junto al de siempre — un solo log para la traza viva y el replay",
      pl_b["europepmc_searched"]["status"] == "success" and pl_b["europepmc_searched"]["n_candidates"] == 5
      and pl_b["selection"]["n_selected"] == 3 and pl_b["selection"]["n_candidates"] == 6
      and pl_b["ledger_version"] == "2" and pl_b["pubmed_searched"]["ncbi_identity"] == "missing"
      and pl_b["pubmed_searched"]["n_new"] == 1 and pl_b["n_papers"] == 3)
check("corrector ADR-0078 evento: resumen POR PAPER para la Traza (evidence_id, source, text_provenance, cache_hit/"
      "cached_at, selection_rank — sin texto) + epmc_query + selection.not_selected (el bloque path_b no viaja congelado)",
      [p["evidence_id"] for p in pl_b["papers"]] == ["PMID:11111111", "PMID:44444444", "PMID:22222222"]
      and pl_b["papers"][0]["text_provenance"] == "fulltext-excerpt" and pl_b["papers"][0]["fetched"]["cache_hit"] is False
      and pl_b["papers"][1]["fetched"]["cache_hit"] is True and pl_b["papers"][1]["fetched"]["cached_at"] == "2026-09-10T00:00:00Z"
      and "cache_hit" not in pl_b["papers"][2]["fetched"] and "TimeoutError" in pl_b["papers"][2]["fetched"]["fetch_error"]
      and all("text_excerpt" not in p and "abstract" not in p for p in pl_b["papers"])
      and pl_b["epmc_query"] == blk_b["epmc_query"] and pl_b["selection"]["not_selected"] == blk_b["selection"]["not_selected"],
      f"papers={pl_b['papers']}")
# --- FORMA por bloque (reviewer: los checks por llave suelta dejaban pasar llaves nuevas/ausentes en silencio) ----
check("corrector ADR-0078 FORMA europepmc_searched: exactamente el conjunto de llaves del contrato",
      set(ep) == {"source", "status", "query_sent", "retmax_sent", "n_found", "n_returned", "n_candidates",
                  "elapsed_s", "sort", "synonym", "throttle", "throttle_slept_s", "contact"},
      repr(sorted(ep)))
check("corrector ADR-0078 FORMA selection: exactamente el conjunto de llaves del contrato",
      set(sel) == {"rule", "n_requested", "retmax", "n_candidates", "n_selected", "n_duplicates", "duplicates",
                   "not_selected", "dedup_keys"}, repr(sorted(sel)))
_PAPER_KEYS = {"source", "evidence_id", "search_rec", "fetched", "selection_rank", "dedup_keys", "abstract",
               "text_excerpt", "text_provenance", "text_excerpt_rule", "text_excerpt_chars", "text_excerpt_omitted",
               "text_source_chars", "text_excerpt_cap_chars"}
check("corrector ADR-0078 FORMA papers[]: cada paper de literatura lleva exactamente las 14 llaves; dedup_keys con "
      "valores (PMID/PMCID/DOI normalizado); fetched.cache_ttl_days propagado cuando el fetch lo midió",
      all(set(p) == _PAPER_KEYS for p in blk_b["papers"])
      and p_ft["dedup_keys"] == ["PMID:11111111", "PMCID:PMC111", "DOI:10.1000/aaa"]
      and p_ab["dedup_keys"] == ["PMID:44444444", "PMCID:PMC444"]
      and p_ft["fetched"]["cache_ttl_days"] == 7.0 and "cache_ttl_days" not in p_none["fetched"]
      and set(p_none["fetched"]) == {"found", "full_text", "n_chunks", "raw_cached", "raw_ref", "fetch_error"},
      repr([sorted(p) for p in blk_b["papers"]][:1]))
check("corrector ADR-0078 FORMA bloque: llaves de nivel superior del path_b v2 (n_papers_source / retmax_source "
      "declaran la procedencia de n y retmax: 'caller' aquí)",
      set(blk_b) == {"triggered", "triggered_by", "ledger_version", "papers", "query_sent", "query_sent_scope",
                     "query_source", "epmc_query", "pubmed_query", "zfin_filter", "query_builder",
                     "n_papers_requested", "n_papers_source", "retmax_requested", "retmax_source",
                     "n_results_by_source", "sources_requested", "tool_universe_directive",
                     "europepmc_searched", "pubmed_searched", "selection"}
      and blk_b["n_papers_source"] == "caller" and blk_b["retmax_source"] == "default-unset:WITT_PATH_B_RETMAX",
      repr(sorted(blk_b)))
# --- la vista de PROMPT del bloque: evidencia, no bitácora --------------------------------------------------------
_ev_prompt = runs_mod._compact_evidence({"path_a": {"hits": [], "retrieval": {}}, "entities_checked": {},
                                         "sufficiency": {}, "path_b": blk_b})["path_b"]
check("corrector ADR-0078 prompt: el sintetizador/panel reciben path_b PROYECTADO — sin query_builder, throttle, "
      "search_ledger anidado, dedup_keys ni duplicates; con estados por fuente, selección y UN texto por paper",
      "query_builder" not in _ev_prompt and "tool_universe_directive" not in _ev_prompt
      and set(_ev_prompt["europepmc_searched"]) <= {"status", "n_found", "n_returned", "n_candidates", "detail", "error"}
      and "throttle" not in _ev_prompt["pubmed_searched"] and "duplicates" not in _ev_prompt["selection"]
      and all("dedup_keys" not in p and "search_ledger" not in p["fetched"] for p in _ev_prompt["papers"])
      and _ev_prompt["papers"][0]["text_excerpt"] == p_ft["text_excerpt"] and "abstract" in _ev_prompt["papers"][0]
      and "abstract" not in _ev_prompt["papers"][1]      # provenance 'abstract': el excerpt YA es el abstract
      and _ev_prompt["papers"][1]["text_excerpt"] == p_ab["abstract"]
      and _ev_prompt["selection"]["not_selected"] == sel["not_selected"],
      f"keys={sorted(_ev_prompt)}")

# --- D. EPMC caída: status 'error' en el ledger y la corrida SIGUE con PubMed (§6 no-hang) --------------
answer_pipeline.fetch_paper.search_europepmc_ledger = (
    lambda query, n=5, sort=None, synonym=True: ([], {"source": "europepmc", "status": "error",
                                                       "query_sent": query, "n_found": None, "n_returned": 0,
                                                       "elapsed_s": 30.0, "sort": "RELEVANCE", "synonym": True,
                                                       "throttle": "net_throttle", "throttle_slept_s": 0.0,
                                                       "contact": "unset", "error": "URLError: timed out"}))
answer_pipeline.path_b = _path_b_real
blk_err = answer_pipeline.path_b_bundle("is wt1a required for pronephros?", entities=["wt1a"], n=3,
                                        sources=("europepmc", "pubmed"))
answer_pipeline.path_b = _path_b_stub
check("ADR-0078 §6: Europe PMC caída -> europepmc_searched.status='error' con el mensaje, CERO candidatos "
      "de EPMC, y PubMed sigue aportando (antes la excepción mataba path_b entero)",
      blk_err["europepmc_searched"]["status"] == "error"
      and "URLError" in blk_err["europepmc_searched"]["error"]
      # corrector: una fuente que FALLÓ no midió 0 candidatos — None (ADR-0043); PubMed sí midió (3)
      and blk_err["europepmc_searched"]["n_candidates"] is None
      and blk_err["europepmc_searched"]["n_returned"] is None
      and blk_err["pubmed_searched"]["n_candidates"] == 3
      and blk_err["pubmed_searched"]["duplicates_of_europepmc"] == []
      and [p["evidence_id"] for p in blk_err["papers"]] == ["PMID:22222222", "PMID:77777777", "PMID:11111111"]
      and blk_err["n_results_by_source"] == {"europepmc": 0, "pubmed": 3},
      f"papers={[p['evidence_id'] for p in blk_err['papers']]}")
answer_pipeline.path_b = _path_b_real
blk_ns = answer_pipeline.path_b_bundle("", entities=[], sources=("europepmc", "pubmed"))
answer_pipeline.path_b = _path_b_stub
check("ADR-0078: sin nada que buscar -> query_sent None DECLARADO + ambas fuentes 'not-searched' + "
      "selection 0/0 (jamás se manda una query vacía al índice)",
      blk_ns["query_sent"] is None and blk_ns["europepmc_searched"]["status"] == "not-searched"
      and blk_ns["pubmed_searched"]["status"] == "not-searched"
      and blk_ns["europepmc_searched"]["n_candidates"] is None and blk_ns["europepmc_searched"]["n_returned"] is None
      and blk_ns["selection"]["n_candidates"] == 0 and blk_ns["papers"] == []
      and blk_ns["query_source"] == "query-builder-v1:empty")


def _boom_epmc(query, n=5, sort=None, synonym=True):
    raise AssertionError("con n<=0 NO debe dispararse ninguna búsqueda de literatura")


answer_pipeline.fetch_paper.search_europepmc_ledger = _boom_epmc
answer_pipeline._WS_CACHE[("pubmed_literature.py", "query_pubmed")] = (
    lambda *a, **k: (_ for _ in ()).throw(AssertionError("pubmed no debe llamarse con n<=0")))
answer_pipeline.path_b = _path_b_real
blk_n0 = answer_pipeline.path_b_bundle("is wt1a required for pronephros?", entities=["wt1a"], n=0,
                                       sources=("europepmc", "pubmed"))
answer_pipeline.path_b = _path_b_stub
check("corrector ADR-0078: n_papers=0 -> CERO red de literatura; ambas fuentes 'not-requested' (detail n_papers=0), "
      "contadores None, selection 0/0, papers [] (antes disparaba EPMC+esearch+esummary con retmax 20 para no elegir nada)",
      blk_n0["europepmc_searched"]["status"] == "not-requested" and blk_n0["pubmed_searched"]["status"] == "not-requested"
      and blk_n0["europepmc_searched"]["detail"] == "n_papers=0 <= 0" and blk_n0["europepmc_searched"]["n_candidates"] is None
      and blk_n0["pubmed_searched"]["n_new"] is None and blk_n0["pubmed_searched"]["duplicates_of_europepmc"] is None
      and blk_n0["selection"]["n_requested"] == 0 and blk_n0["selection"]["n_candidates"] == 0 and blk_n0["papers"] == []
      and blk_n0["n_results_by_source"] == {"europepmc": 0, "pubmed": 0},
      f"epmc={blk_n0['europepmc_searched']} pubmed={blk_n0['pubmed_searched']['status']}")
answer_pipeline.fetch_paper.search_europepmc_ledger = _epmc_ledger_real
answer_pipeline.fetch_paper.fetch_external = _fetch_real2
answer_pipeline._WS_CACHE.pop(("pubmed_literature.py", "query_pubmed"), None)

# --- E. ZFIN con el TOOL REAL (cargado por ruta) servido desde el fixture REAL 2026-09-13 --------------
_FIX_PATH = Path(__file__).resolve().parent / "fixtures" / "alliance_phenotypes_wt1a_20260913.json"
_FIX = json.loads(_FIX_PATH.read_text(encoding="utf-8"))
_FIX_NOREF = {"results": [{"phenotypeStatement": "pronephric duct absent, abnormal",
                           "pubmedPublications": [], "references": []}],
              "total": 1, "returnedRecords": 1}
_zfin_mode = {"noref": False}
_zfin_calls = []


def _fake_alliance_get(url, timeout=30):
    _zfin_calls.append({"url": url, "timeout": timeout})
    if "search_autocomplete" in url:
        return {"results": [{"category": "gene_search_result", "name": "wt1a",
                             "curie": "ZFIN:ZDB-GENE-980526-558"}]}
    if _zfin_mode["noref"]:
        return _FIX_NOREF
    if "filter.termName=" in url:   # el servidor filtra como Alliance: OR por subcadena
        terms = urllib.parse.unquote(url.split("filter.termName=")[1]).split("|")
        res = [r for r in _FIX["results"] if any(t in r["phenotypeStatement"].lower() for t in terms)]
        return {"results": res, "total": len(res), "returnedRecords": len(res)}
    return _FIX


answer_pipeline._WS_CACHE.pop(("zfin_zebrafish.py", "query_zfin"), None)
_zfin_real = answer_pipeline._workspace_tool("zfin_zebrafish.py", "query_zfin")
_zfin_get_real = _zfin_real.__globals__["_get"]
_zfin_real.__globals__["_get"] = _fake_alliance_get
answer_pipeline.CACHE = TMP / "mcp_cache"
items_z, ledger_z = answer_pipeline._search_zfin(["wt1a"], "is wt1a required for pronephros development?")
row_z = ledger_z[0]
check("ADR-0078 ZFIN: con el esquema NUEVO (pubmedPublications, fixture real 53/53) las referencias YA NO "
      "son [] — PMIDs reales por statement, references_schema declarado en ledger e item",
      row_z["status"] == "success" and row_z["references_schema"] == "pubmedPublications"
      and len(items_z) == 1 and items_z[0]["zfin"]["has_references"] is True
      and all(p["references"] and all(r.startswith("PMID:") for r in p["references"])
              for p in items_z[0]["zfin"]["phenotypes"])
      and items_z[0]["zfin"]["references_schema"] == "pubmedPublications"
      and items_z[0]["evidence_id"] == "ZFIN:ZDB-GENE-980526-558",
      f"status={row_z['status']} schema={row_z.get('references_schema')} "
      f"refs0={items_z[0]['zfin']['phenotypes'][0]['references'] if items_z else None}")
check("corrector ADR-0078 ZFIN: por DEFAULT el filtro anatómico de build_zfin_filter va en el CLIENTE (prefijo de "
      "palabra) — la URL NO lleva filter.termName ('a|b' midió HTTP 400 en vivo; la forma de una raíz no está medida); "
      "el timeout de cada GET es min(10, presupuesto restante / 2) y se declara con su alcance",
      not any("filter.termName" in c["url"] for c in _zfin_calls)
      and all(0 < c["timeout"] <= 10 for c in _zfin_calls) and len(_zfin_calls) == 2
      and row_z["timeout_s"] <= 10 and row_z["timeout_s_scope"] == "per-http-get"
      and row_z["anatomy_filter"] == "pronephr"
      and row_z["anatomy_terms"] == ["pronephr"] and row_z["anatomy_filter_mode"] == "client"
      and row_z["anatomy_filter_semantics"].startswith("word-prefix")
      and row_z["n_phenotypes_total"] == 53 and row_z["n_phenotypes_total_scope"] == "gene",
      f"calls={[(c['url'][-60:], c['timeout']) for c in _zfin_calls]}")
check("ADR-0078 ZFIN: los cortes del tool se PROPAGAN — n_returned_by_api 53 (payload completo, filtro cliente), "
      "phenotypes_capped_at_300 False, n_matched 16 > n_returned 12 truncado declarado, references_truncated",
      row_z["n_returned_by_api"] == 53 and row_z["phenotypes_capped_at_300"] is False
      and row_z["n_matched"] == 16 and items_z[0]["zfin"]["n_returned"] == 12
      and items_z[0]["zfin"]["truncated"] is True and "references_truncated" in row_z
      and row_z["n_statements_with_references"] == 16
      and items_z[0]["zfin"]["anatomy_filter_source"] == "search_queries.build_zfin_filter:v1"
      and items_z[0]["zfin"]["n_phenotypes_total_scope"] == "gene",
      f"api={row_z.get('n_returned_by_api')} matched={row_z.get('n_matched')}")
os.environ["WITT_ZFIN_SERVER_FILTER"] = "1"
_zfin_calls.clear()
items_sv, ledger_sv = answer_pipeline._search_zfin(["wt1a"], "is wt1a required for pronephros and glomerulus development?")
del os.environ["WITT_ZFIN_SERVER_FILTER"]
_urls_sv = [c["url"] for c in _zfin_calls if "/phenotypes" in c["url"]]
check("corrector ADR-0078 ZFIN: con WITT_ZFIN_SERVER_FILTER=1 el filtro va al servidor UNA GET POR RAÍZ "
      "(filter.termName=pronephr, =glomer; jamás 'a|b'), modo 'server+client', total del gen NO medido "
      "(None, scope 'server-filtered', server_filter_totals por raíz), n_http_gets 3",
      len(_urls_sv) == 2 and any(u.endswith("filter.termName=pronephr") for u in _urls_sv)
      and any(u.endswith("filter.termName=glomer") for u in _urls_sv) and not any("|" in u for u in _urls_sv)
      and ledger_sv[0]["anatomy_filter_mode"] == "server+client" and ledger_sv[0]["n_phenotypes_total"] is None
      and ledger_sv[0]["n_phenotypes_total_scope"] == "server-filtered"
      and set(ledger_sv[0]["server_filter_totals"]) == {"pronephr", "glomer"} and ledger_sv[0]["n_http_gets"] == 3
      and ledger_sv[0]["n_matched"] >= 16 and ledger_sv[0]["anatomy_filter"] == "pronephr|glomer",
      f"urls={[u[-45:] for u in _urls_sv]} row={ {k: ledger_sv[0].get(k) for k in ('n_matched', 'n_phenotypes_total_scope')} }")
_zfin_mode["noref"] = True
items_nr, ledger_nr = answer_pipeline._search_zfin(["wt1a"], "pronefros")
_zfin_mode["noref"] = False
check("ADR-0078 ZFIN: statements SIN PMIDs -> 'success-no-references' LITERAL en el ledger (no 'success', "
      "no 'error') + item con has_references=false y references_schema 'none'",
      ledger_nr[0]["status"] == "success-no-references" and ledger_nr[0]["references_schema"] == "none"
      and len(items_nr) == 1 and items_nr[0]["zfin"]["has_references"] is False
      and items_nr[0]["zfin"]["status"] == "success-no-references"
      and items_nr[0]["zfin"]["phenotypes"][0]["references"] == [],
      f"status={ledger_nr[0]['status']}")
_zfin_real.__globals__["_get"] = _zfin_get_real
answer_pipeline._WS_CACHE.pop(("zfin_zebrafish.py", "query_zfin"), None)
answer_pipeline.CACHE = _CACHE_REAL
check("mcp_cache del repo INTACTO tras la sección ZFIN (los envelopes fueron al tmp del gate)",
      not list(_CACHE_REAL.glob(f"zfin_wt1a_{_dt.datetime.now(_dt.timezone.utc).strftime('%Y%m%d')}.json"))
      and list((TMP / "mcp_cache").glob("zfin_wt1a_*.json")))

# --- F. modelo de corrida (rebanada I5): citas, precios, claimed_by, reaper ------------------------------
_CITAS_STR = '[{"kind": "di-record", "id": "CORPUS-2026-0001"}]'
composite_auditor._anthropic_tool_call = _mk_fake_api({**_BASE_SYNTH, "evidence_cited": _CITAS_STR},
                                                      elicit_out={"confidence": 0.4})
ans_c = runs_mod._default_synthesizer("q", {"e": 1}, "pass1")
composite_auditor._anthropic_tool_call = _orig_tool_call
check("ADR-0078 citas (sintetizador real): evidence_cited como STRING JSON se re-parsea con dicts INTACTOS "
      "(kind/id tipados, no kind='other'), el crudo queda en evidence_cited_raw y gap_flags lo declara",
      ans_c["evidence_cited"] == [{"kind": "di-record", "id": "CORPUS-2026-0001"}]
      and ans_c["evidence_cited_raw"] == _CITAS_STR
      and any("SERIALIZADO" in f and "evidence_cited" in f for f in ans_c["gap_flags"]))
rv_c = app.create_run(app.RunBody(question="citas serializadas", entities=[]), authorization=AUTH)
claimed_c = db.claim_next_queued(worker_id="run-worker-smoke")
runs_mod.execute_run(claimed_c, synthesizer=_mk_synth(
    {"pass1": 0.8}, extra={"evidence_cited": _CITAS_STR, "evidence_cited_raw": _CITAS_STR}),
    panel_caller=_stub_caller_factory(ALL_A))
rec_c = app.get_frozen_record(rv_c["run_id"], authorization=AUTH)
check("ADR-0078 citas (congelado): un string que llega hasta el freeze se re-parsea -> 1 cita tipada "
      "(jamás N de un carácter) + citations_schema 'string-reparsed' + evidence_cited_raw en el registro",
      rec_c["citations_schema"]["source"] == "string-reparsed" and rec_c["citations_schema"]["n_valid"] == 1
      and _cits_base(rec_c["citations"]) == [{"n": 1, "kind": "di-record", "id": "CORPUS-2026-0001", "note": ""}]
      and rec_c["evidence_cited_raw"] == _CITAS_STR,
      f"schema={rec_c['citations_schema']}")
view_c = app.get_run(rv_c["run_id"], authorization=AUTH)
check("ADR-0078 reclamo: claimed_by/claimed_at viajan en la vista (worker_id del hilo; sin él = null declarado)",
      view_c["claimed_by"] == "run-worker-smoke" and view_c["claimed_at"] is not None
      and claimed_c["claimed_by"] == "run-worker-smoke")
# --- corrector: el CAMINO REAL de producción (wrapper _default_synthesizer -> execute_run -> congelado) ---------------
composite_auditor._anthropic_tool_call = _mk_fake_api({**_BASE_SYNTH, "evidence_cited": _CITAS_STR},
                                                      elicit_out={"confidence": 0.9})
rv_real = app.create_run(app.RunBody(question="citas string por el wrapper real", entities=[]), authorization=AUTH)
runs_mod.execute_run(db.claim_next_queued(worker_id="run-worker-smoke"), synthesizer=None,
                     panel_caller=_stub_caller_factory(ALL_A))
composite_auditor._anthropic_tool_call = _orig_tool_call
rec_real = app.get_frozen_record(rv_real["run_id"], authorization=AUTH)
check("corrector ADR-0078 citas (CAMINO REAL: _default_synthesizer re-parsea y execute_run congela): el registro dice "
      "'string-reparsed' con el crudo — ya no 'list' junto a un evidence_cited_raw string",
      db.get_run(rv_real["run_id"])["state"] == "awaiting_closure"
      and rec_real["citations_schema"]["source"] == "string-reparsed" and rec_real["citations_schema"]["n_valid"] == 1
      and rec_real["evidence_cited_raw"] == _CITAS_STR
      and _cits_base(rec_real["citations"]) == [{"n": 1, "kind": "di-record", "id": "CORPUS-2026-0001", "note": ""}],
      f"schema={rec_real.get('citations_schema')} state={db.get_run(rv_real['run_id'])['state']}")
composite_auditor._anthropic_tool_call = _mk_fake_api({k: v for k, v in _BASE_SYNTH.items() if k != "evidence_cited"},
                                                      elicit_out={"confidence": 0.9})
rv_abs = app.create_run(app.RunBody(question="modelo que omite evidence_cited", entities=[]), authorization=AUTH)
runs_mod.execute_run(db.claim_next_queued(worker_id="run-worker-smoke"), synthesizer=None,
                     panel_caller=_stub_caller_factory(ALL_A))
composite_auditor._anthropic_tool_call = _orig_tool_call
rec_abs = app.get_frozen_record(rv_abs["run_id"], authorization=AUTH)
check("corrector ADR-0078 citas: el modelo NO emite evidence_cited -> citations_schema 'absent' (0/0) + gap_flag "
      "'AUSENTE' — declarado, no rellenado con [] (que se leería 'citó 0'); la corrida termina",
      db.get_run(rv_abs["run_id"])["state"] == "awaiting_closure"
      and rec_abs["citations_schema"] == {"source": "absent", "n_raw": 0, "n_valid": 0}
      and rec_abs["citations"] == [] and rec_abs["evidence_cited_raw"] is None
      and any("evidence_cited AUSENTE" in f for f in rec_abs["answer"]["gap_flags"]),
      f"schema={rec_abs.get('citations_schema')} gaps={rec_abs['answer']['gap_flags'][-1:]}")
tu_c = rec_c["token_usage"]
check("ADR-0078 precios: un modelo SIN precio (stub-synth) NO se cotiza a 0 — missing_price_models + "
      "cost_projection_complete=False + cost_class INCOMPLETE; sonnet-5 corregido a (2.0, 10.0)",
      tu_c["missing_price_models"] == ["stub-synth"] and tu_c["cost_projection_complete"] is False
      and "INCOMPLETE" in tu_c["cost_class"] and tu_c["estimated_cost_usd"] > 0
      # ADR-0081: el id se lee de la tabla (asiento overclaim de g1 = sonnet-5), no de un literal; los precios son alias
      and runs_mod.PRICES_PER_MTOK_USD[models.GENERATIONS["g1-2026-08"]["defaults"]["judge.overclaim"]] == (2.0, 10.0)
      and runs_mod.PRICES_PER_MTOK_USD == models.prices() and runs_mod.PRICES_AS_OF == models.PRICES_AS_OF == "2026-09",
      f"missing={tu_c['missing_price_models']} cost={tu_c['estimated_cost_usd']}")
rv_u = app.create_run(app.RunBody(question="citas en prosa", entities=[]), authorization=AUTH)
runs_mod.execute_run(db.claim_next_queued(), synthesizer=_mk_synth(
    {"pass1": 0.8}, extra={"evidence_cited": "cito el registro CORPUS-2026-0001 y nada mas, en prosa"}),
    panel_caller=_stub_caller_factory(ALL_A))
rec_u = app.get_frozen_record(rv_u["run_id"], authorization=AUTH)
check("ADR-0078 citas: string NO parseable -> citations=[] + 'string-unparseable' con raw_len_chars, la "
      "corrida termina (awaiting_closure) y NINGUNA cita es de un carácter",
      rec_u["citations"] == [] and rec_u["citations_schema"]["source"] == "string-unparseable"
      and rec_u["citations_schema"]["n_valid"] == 0 and rec_u["citations_schema"]["raw_len_chars"] > 10
      and db.get_run(rv_u["run_id"])["state"] == "awaiting_closure"
      and not any(len(c["id"]) == 1 for c in rec_u["citations"]),
      f"schema={rec_u['citations_schema']}")
us3 = app.usage(authorization=AUTH)
check("ADR-0078 /usage: missing_price_models agregado, cost_projection_complete=False, "
      "by_model[stub-synth].estimated_cost_usd=null con price_state 'missing' (jamás 0.0)",
      "stub-synth" in us3["missing_price_models"] and us3["cost_projection_complete"] is False
      and us3["by_model"]["stub-synth"]["estimated_cost_usd"] is None
      and us3["by_model"]["stub-synth"]["price_state"] == "missing"
      and us3["n_runs_cost_incomplete"] >= 2,
      f"missing={us3['missing_price_models']} incomplete={us3['n_runs_cost_incomplete']}")
rv_w = app.create_run(app.RunBody(question="worker lost", entities=[]), authorization=AUTH)
claimed_w = db.claim_next_queued(worker_id="run-worker-0")     # running, y el worker 'muere' sin latir
_future = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(seconds=2000)
segadas = db.reap_stale_running(900, now=_future)
run_w = db.get_run(rv_w["run_id"])
ev_w = app.get_events(rv_w["run_id"], after=0, authorization=AUTH)["events"]
check("ADR-0078 reaper: running sin latido > 900 s -> failed 'worker-lost' + evento run.state "
      "{reason: worker-lost} del agente run-reaper; NUNCA re-encolada (nada se re-ejecuta solo)",
      segadas == [rv_w["run_id"]] and run_w["state"] == "failed" and "worker-lost" in run_w["error"]
      and any(e["type"] == "run.state" and (e.get("payload") or {}).get("reason") == "worker-lost"
              and e.get("agent") == "run-reaper" for e in ev_w)
      and runs_mod.REAP_STALE_S == 900,
      f"segadas={segadas} state={run_w['state']}")
check("reaper: segunda pasada no toca nada (idempotente); una running FRESCA queda intacta",
      db.reap_stale_running(900, now=_future) == []
      and db.reap_stale_running(900) == [])
check("ADR-0078: la vista distingue la corrida segada (error 'worker-lost: …', failure_reason 'worker-lost') de un "
      "fallo del pipeline; la segada queda con cancel_requested para que un hilo vivo aborte en la siguiente frontera",
      app.get_run(rv_w["run_id"], authorization=AUTH)["error"].startswith("worker-lost:")
      and app.get_run(rv_w["run_id"], authorization=AUTH)["failure_reason"] == "worker-lost"
      and app.get_run(rv_w["run_id"], authorization=AUTH)["claimed_by"] == "run-worker-0"
      and db.cancel_requested(rv_w["run_id"]) is True
      and db.get_run(rv_w["run_id"])["cancelled_by"] == "run-reaper")
# --- corrector: la carrera reaper <-> worker vivo, dirección peligrosa: el worker NO pisa a la segada -------------------
_ok_fin = runs_mod._finish(rv_w["run_id"], "awaiting_closure", {"verdict": "APPROVE"},
                           frozen_record_json="{}", bundle_json="{}")
_row_w = db.get_run(rv_w["run_id"])
_ev_w2 = app.get_events(rv_w["run_id"], after=0, authorization=AUTH)["events"]
check("corrector ADR-0078: el cierre del worker es CONDICIONAL (finish_run WHERE state='running') — tras la siega "
      "devuelve False, la fila sigue failed/worker-lost sin frozen_record, y queda UN evento run.state.conflict "
      "{attempted awaiting_closure, found failed, ignored true}",
      _ok_fin is False and _row_w["state"] == "failed" and _row_w["error"].startswith("worker-lost")
      and _row_w["frozen_record_json"] is None
      and _ev_w2[-1]["type"] == "run.state.conflict" and _ev_w2[-1]["payload"]["attempted"] == "awaiting_closure"
      and _ev_w2[-1]["payload"]["found"] == "failed" and _ev_w2[-1]["payload"]["ignored"] is True,
      f"ok={_ok_fin} state={_row_w['state']} last={_ev_w2[-1]['type']}")
_run_fail = db.get_run(rv_abs["run_id"])
check("corrector ADR-0078: failure_reason 'pipeline' para un failed por excepción (no reaper)",
      (lambda rid: (db.update_run(rid, state="failed", error="RuntimeError: boom"),
                    app.get_run(rid, authorization=AUTH)["failure_reason"])[1] == "pipeline"
       and (db.update_run(rid, state="awaiting_closure", error=None), True)[1])(rv_abs["run_id"]))
check("corrector ADR-0078: worker_id lleva identidad de PROCESO (boot_id:pid:hilo, <= 64 chars) — dos generaciones "
      "del proceso ya no comparten 'run-worker-0'",
      runs_mod.worker_id_for("run-worker-0").endswith(":run-worker-0")
      and runs_mod.worker_id_for("run-worker-0").split(":")[0] == runs_mod.WORKER_BOOT_ID
      and runs_mod.worker_id_for("run-worker-0").split(":")[1] == str(os.getpid())
      and len(runs_mod.worker_id_for("run-worker-0")) <= 64)
os.environ["WITT_REAP_STALE_S"] = ""
_tol_empty = runs_mod._env_int_tolerante("WITT_REAP_STALE_S", 900)
os.environ["WITT_REAP_STALE_S"] = "abc"
_tol_bad = runs_mod._env_int_tolerante("WITT_REAP_STALE_S", 900)
os.environ["WITT_REAP_STALE_S"] = "120"
_tol_ok = runs_mod._env_int_tolerante("WITT_REAP_STALE_S", 900)
os.environ.pop("WITT_REAP_STALE_S", None)
check("corrector ADR-0078: WITT_REAP_STALE_S vacía / basura -> 900 declarado (default-unset / default-invalid-env), "
      "nunca una excepción al importar; '120' -> (120, 'env:…')",
      _tol_empty == (900, "default-unset:WITT_REAP_STALE_S") and _tol_bad == (900, "default-invalid-env:WITT_REAP_STALE_S")
      and _tol_ok == (120, "env:WITT_REAP_STALE_S") and runs_mod.REAP_STALE_S == 900
      and runs_mod.REAP_STALE_S_SOURCE.endswith(":WITT_REAP_STALE_S"))
us4 = app.usage(authorization=AUTH)
check("corrector ADR-0078 /usage: cost_projection_complete es False mientras haya corridas congeladas incompletas "
      "(aunque hoy todos los modelos tuvieran precio) y n_runs_cost_unknown declara las anteriores a la llave",
      us4["cost_projection_complete"] is False and us4["n_runs_cost_incomplete"] >= 2
      and "corrida(s) congeladas sin precio" in us4["cost_class"] and us4["n_runs_cost_unknown"] == 0
      and "price_state" in us4["by_model"]["stub-synth"],
      f"incomplete={us4['n_runs_cost_incomplete']} unknown={us4['n_runs_cost_unknown']}")
os.environ["WITT_NCBI_EMAIL"] = "smoke-leak@example.invalid"
_fp = answer_pipeline.fetch_paper
_fp_get_real = _fp._get
_fp._get = lambda url, parse_json=False, meta=None: {"hitCount": 1, "resultList": {"result": [
    {"id": "1", "source": "MED", "pmid": "11111111", "title": "t", "pubYear": "2020", "isOpenAccess": "N"}]}}
_items_leak, _led_leak = _fp.search_europepmc_ledger("leak test", n=1)
_fp._get = _fp_get_real
_ua_leak = _fp._ua()["User-Agent"]
os.environ.pop("WITT_NCBI_EMAIL", None)
_bundle_leak = {"path_a": {"hits": [], "retrieval": {}}, "entities_checked": {}, "sufficiency": {},
                "path_b": {"triggered": True, "papers": [], "europepmc_searched": _led_leak}}
check("corrector ADR-0078 FUGA: con WITT_NCBI_EMAIL fijada el correo vive SOLO en el User-Agent; el ledger declara "
      "contact 'declared' y ni el ledger ni la vista de prompt llevan '@'",
      "smoke-leak@example.invalid" in _ua_leak and _led_leak["contact"] == "declared"
      and "@" not in json.dumps(_led_leak, ensure_ascii=False)
      and "@" not in json.dumps(runs_mod._compact_evidence(_bundle_leak), ensure_ascii=False, default=str),
      f"contact={_led_leak['contact']}")

# =====================================================================================================
# ---- ADR-0079: la INVESTIGACIÓN (turnos encadenados sobre una raíz) — integración T1..T4 -------------
# db (columnas) <-> runs (derivación al encolar, snapshot, inyección, precedente != evidencia, origen, ejes)
# <-> app (404/409, vista, GET /threads, GET /runs?thread=, include_origins) <-> consumidores (precedent,
# calibration, record_pdf). Todo offline: sintetizador/panel inyectados, o el camino REAL de
# _default_synthesizer con composite_auditor._anthropic_tool_call CAPTURADO; cero red, cero modelo.
# El ORIGEN de estas corridas lo deriva runs.run_origin() del entorno: 'smoke' bajo la máscara de los gates
# (WITT_RUN_ORIGIN=smoke) o 'dev-offline' (WITT_ALLOW_RUNS_OFFLINE=1) sin ella. Los checks comparan contra
# esa derivación — en ambos casos el origen es ∉ 'production', que es lo que precedente/calibración
# excluyen por default (y cuentan). Vocabulario: en código thread_id/turn_no/turn_kind; al humano
# "investigación" T-<run_no raíz> ("hilo" ya nombra los comentarios de ADR-0077).
# =====================================================================================================
import precedent  # noqa: E402

_ORIGIN = runs_mod.run_origin()
assert _ORIGIN["value"] in db.RUN_ORIGINS, _ORIGIN
_SYNTH_CTX = []     # (pass_label, thread_context) que recibió el sintetizador stub con la firma NUEVA
_PANEL_TXT = []     # user_text de cada juez: el panel NUNCA debe recibir el texto del turno anterior
_REAL_API = []      # (system, user_text, tool_name) capturados del camino REAL (_default_synthesizer)
_THREAD_COLS = ("parent_run_id", "thread_id", "turn_no", "turn_kind", "origin", "root_question_id")


def _panel_capture(verdicts):
    inner = _stub_caller_factory(verdicts)

    def _caller(member, system, user_text):
        _PANEL_TXT.append(user_text)
        return inner(member, system, user_text)
    return _caller


def _synth_ctx(answer_text, gap_flags=("thin coverage of late stages",), **extra):
    """Sintetizador stub con la firma NUEVA (acepta thread_context): registra qué recibió."""
    def _s(question, evidence, pass_label, thread_context=None):
        _SYNTH_CTX.append((pass_label, thread_context))
        assert "thread_context" not in (evidence or {}), "thread_context jamás DENTRO de evidence"
        out = _mk_synth({"pass1": 0.8, "pass2": 0.85})(question, evidence, pass_label)
        out.update({"direct_answer": answer_text, "gap_flags": list(gap_flags)})
        out.update(extra)
        return out
    return _s


def _mk_capture_api(synth_out, elicit_out, sink):
    """La API de Anthropic FALSA que además graba lo que el sintetizador REAL le mandó (system, user_text)."""
    def fake(model, system, user_text, tool=None, timeout=120, retries=1, max_tokens=1200):
        sink.append((system, user_text, (tool or {}).get("name")))
        if tool and tool["name"] == "emit_confidence":
            return dict(elicit_out), {"input_tokens": 30, "output_tokens": 3}
        return dict(synth_out), {"input_tokens": 100, "output_tokens": 50}
    return fake


def _ejecuta(run_id, synth=None, panel=None):
    claimed = db.claim_next_queued(worker_id="run-worker-adr0079")
    assert claimed and claimed["run_id"] == run_id, \
        f"FIFO: se esperaba {run_id}, se reclamó {claimed and claimed['run_id']}"
    runs_mod.execute_run(claimed, synthesizer=synth, panel_caller=panel or _panel_capture(ALL_A))
    return db.get_run(run_id), app.get_frozen_record(run_id, authorization=AUTH)


def _cols(view):
    return {k: view.get(k) for k in _THREAD_COLS}


check("ADR-0079/0080/0081 contrato: runs.RENDER_CONTRACT_VERSION == '1.10' — 1.8 (ADR-0079) acompañó thread, thread_context, "
      "thread_parent_matches_run, precedent_citations, origin, episode_axes; 1.9 (ADR-0080) sumó competence, search_ledger, "
      "citations[].support_state, citations_support_summary, deterministic_checks.{pass1_admissible, "
      "positive_claim_requires_citations, competence_gate}, token_usage.by_stage, epistemic_summary.{competent, "
      "n_search_rounds}; 1.10 (ADR-0081) suma frozen.models, answer.{model_source, model_reported, relation}, audit.{families_valid…, "
      "quorum}, by_stage.panel.by_model, plan.judgment.planner.model_source, epistemic_summary.{model_generation, "
      "panel_n_families_valid} + eventos stage.models / run.state{queued}.root_run_no; la webapp los tipa `?` — eso ES la paridad",
      runs_mod.RENDER_CONTRACT_VERSION == "1.13")   # el ÚNICO literal del contrato en todos los gates (los demás comparan contra runs_mod)
                                                    # 1.13 = ADR-0084 (la web LOCALIZA, jamás es fuente): +web_locator, deterministic_checks.web_locator,
                                                    # citations[].located_via, token_usage.web_locator/total, epistemic web_*, stage.web.locate
                                                    # 1.11 = ADR-0082 (consejo de criterio): +council, deterministic_checks.council/
                                                    # attestation_identifier_leak, token_usage.cache/council_r*, citations[].pertinent con razón
                                                    # 1.12 = ADR-0083 (figuras como evidencia observada): +figures, citations[].kind 'figure' +
                                                    # figure_verification, citations_support_summary.figure_citations, deterministic_checks.figures,
                                                    # audit.panel[].saw_figures/audit.vision (F3), by_model[*].vision, agents_invoked fila figures
check("ADR-0079 (D) synth_system SIN turno anterior es byte-idéntico al de antes (la medición de ab_trapped_scalar no "
      "cambia); CON turno gana THREAD_ANTI_LEAK_CLAUSE; SYNTH_TOOL.description lleva la frase anti-fuga SIEMPRE",
      runs_mod.synth_system("pass1") == runs_mod.synth_system("pass1", thread_context=False)
      and runs_mod.THREAD_ANTI_LEAK_CLAUSE not in runs_mod.synth_system("pass1")
      and runs_mod.THREAD_ANTI_LEAK_CLAUSE in runs_mod.synth_system("pass1", thread_context=True)
      and "PRIOR ART" in runs_mod.SYNTH_TOOL["description"])

# --- la RAÍZ por la PUERTA (app.create_run -> runs.new_run -> db.create_run): la derivación es del servidor -----
rv_root = app.create_run(app.RunBody(question="ADR-0079 raiz: does wt1a mark the pronephros?", entities=["wt1a"]),
                         authorization=AUTH)
T_ROOT = rv_root["run_id"]
check("ADR-0079 (A/B) la RAÍZ nace en la vista con thread_id=run_id, turn_no 1, turn_kind 'root', parent_run_id null, "
      f"origin derivado por el SERVIDOR ({_ORIGIN['value']!r} via {_ORIGIN['source']}), root_question_id null declarado; "
      "el blob thread_context_json NO viaja por renglón",
      rv_root["thread_id"] == T_ROOT and rv_root["turn_no"] == 1 and rv_root["turn_kind"] == "root"
      and rv_root["parent_run_id"] is None and rv_root["origin"] == _ORIGIN["value"]
      and rv_root["root_question_id"] is None and "thread_context_json" not in rv_root,
      json.dumps(_cols(rv_root)))
check("ADR-0079 (B) por la puerta: parent_run_id inexistente -> 404 parent_not_found; padre 'queued' (la raíz aún no "
      "corrió) -> 409 parent_not_terminal — validado UNA vez en runs.py (ThreadError) y traducido en app.py",
      _http_error(app.create_run, app.RunBody(question="x", parent_run_id="no-such-parent"), authorization=AUTH) == 404
      and _http_error(app.create_run, app.RunBody(question="x", parent_run_id=T_ROOT), authorization=AUTH) == 409)
_SYNTH_CTX.clear(); _PANEL_TXT.clear()
root_row, rec_root = _ejecuta(T_ROOT, synth=_synth_ctx(
    "wt1a (ENSDARG00000031420) marks the zebrafish pronephros (PMID:31415926)."))
check("ADR-0079 (I) raíz congelada: thread {root, turno 1, parent null, root_run_no = su propio run_no}, thread_context "
      "null + skipped 'root-turn', thread_parent_matches_run null/'no-parent', precedent_citations [] + disjoint_series "
      "True 'no-parent', leak 'no-parent'; el sintetizador recibió thread_context=None (sin turno anterior no viaja nada) "
      "en AMBAS pasadas (ADR-0080: sin plan hay pass2)",
      rec_root["thread"]["turn_kind"] == "root" and rec_root["thread"]["turn_no"] == 1
      and rec_root["thread"]["parent_run_id"] is None and rec_root["thread"]["root_run_no"] == rv_root["run_no"]
      and rec_root["thread_context"] is None and rec_root["thread_context_skipped_reason"] == "root-turn"
      and rec_root["thread_parent_matches_run"] is None and rec_root["thread_parent_matches_run_state"] == "no-parent"
      and rec_root["precedent_citations"] == [] and rec_root["deterministic_checks"]["disjoint_series"] is True
      and rec_root["deterministic_checks"]["disjoint_series_state"] == "no-parent"
      and rec_root["deterministic_checks"]["parent_identifier_leak_state"] == "no-parent"
      and [p for p, _tc in _SYNTH_CTX] == ["pass1", "pass2"] and all(tc is None for _p, tc in _SYNTH_CTX),
      json.dumps(rec_root["thread"]))
_v_root = app.get_run(T_ROOT, authorization=AUTH)
check("ADR-0079 (F) origin en el REGISTRO {value, source, note null} = la derivación del servidor al encolar; la vista, el "
      "epistemic_summary (derivado al congelar) y episode_axes.provenance.origin dicen lo MISMO",
      rec_root["origin"]["value"] == _ORIGIN["value"] and rec_root["origin"]["source"] == _ORIGIN["source"]
      and rec_root["origin"]["note"] is None
      # corrector: la re-derivación al ejecutar viaja APARTE (mismo entorno aquí → mismo valor y fuente)
      and rec_root["origin"]["source_at_execution"] == {**_ORIGIN, "same_value_as_column": True}
      and _v_root["origin"] == _ORIGIN["value"] and _v_root["epistemic_summary"]["origin"] == _ORIGIN["value"]
      and _v_root["epistemic_summary"]["thread_id"] == T_ROOT and _v_root["epistemic_summary"]["turn_no"] == 1
      and rec_root["episode_axes"]["provenance"]["origin"] == _ORIGIN["value"],
      json.dumps(rec_root["origin"]))

# el padre gana conversación (ADR-0077) y una calificación (M5): la conversación SÍ entra al snapshot (clase
# atestiguada); la calificación JAMÁS (enmascarada por solicitante, nunca promediada)
app.create_run_comment(T_ROOT, app.RunCommentBody(body="COMENTARIO-0079-A: falta el estadio tardío (48 hpf)"),
                       authorization=AUTH)
app.create_run_comment(T_ROOT, app.RunCommentBody(body="COMENTARIO-0079-B: revisar wt1b como parálogo"),
                       authorization=AUTH)
db.add_rating(db.get_run(T_ROOT), {"user_id": "natalia", "role": "medico"}, 4, "value", 5, "value",
              note="NOTA-DE-CALIFICACION-SECRETA-0079", note_question="")

# --- hijo 'refine' por el CAMINO REAL: _default_synthesizer (API capturada) + panel capturado ------------------
rv_child = app.create_run(app.RunBody(question="ADR-0079 refine: does wt1a mark the pronephros at 48 hpf?",
                                      entities=["wt1a"], parent_run_id=T_ROOT), authorization=AUTH)
T_CHILD = rv_child["run_id"]
_lista = {r["run_id"]: r for r in app.list_runs(authorization=AUTH)["runs"]}
check("ADR-0079 (B) hijo con pregunta distinta por la puerta: turn_no 2, 'refine', thread_id = raíz, parent = raíz, "
      "mismo origin; LISTA y DETALLE traen las MISMAS 6 columnas para raíz e hijo (ADR-0055/0076: sin setdefault)",
      rv_child["turn_no"] == 2 and rv_child["turn_kind"] == "refine" and rv_child["thread_id"] == T_ROOT
      and rv_child["parent_run_id"] == T_ROOT and rv_child["origin"] == _ORIGIN["value"]
      and all(_cols(_lista[rid]) == _cols(app.get_run(rid, authorization=AUTH)) for rid in (T_ROOT, T_CHILD))
      and _cols(_lista[T_CHILD])["turn_no"] == 2,
      json.dumps(_cols(rv_child)))
# corrector ADR-0079: la raíz se CIERRA entre el encolado del hijo (snapshot + sha tomados sobre el blob
# pre-clausura) y su ejecución — THREAD_SHA_RULE debe casar igual, y sólo un padre 'closed' es precedente (letra)
app.close_run(T_ROOT, authorization=AUTH)
_REAL_API.clear(); _PANEL_TXT.clear()
composite_auditor._anthropic_tool_call = _mk_capture_api(
    {**_BASE_SYNTH, "direct_answer": "wt1a marks the pronephros at 48 hpf as well.", "confidence": 0.8,
     "gap_flags": ["thin coverage of late stages"],
     "evidence_cited": [{"kind": "di-record", "id": "CORPUS-2026-0001"}]},
    {"confidence": 0.8}, _REAL_API)
try:
    child_row, rec_child = _ejecuta(T_CHILD, synth=None)     # synthesizer=None = _default_synthesizer REAL
finally:
    composite_auditor._anthropic_tool_call = _orig_tool_call
_synth_calls = [(s, json.loads(u)) for s, u, name in _REAL_API if name == "emit_answer"]
snap = rec_child["thread_context"]
check("ADR-0079 (D) CAMINO REAL: el user_text del sintetizador tiene EXACTAMENTE {question, evidence, thread_context} — "
      "llave HERMANA (no dentro de evidence), el system lleva THREAD_ANTI_LEAK_CLAUSE; el registro declara "
      "context_delivery.synthesizer True / panel False y los 3 prompt_components (ADR-0080: sin plan hay pass2 — las DOS "
      "llamadas emit_answer llevan la llave)",
      len(_synth_calls) == 2 and all(set(u) == {"question", "evidence", "thread_context"} for _s, u in _synth_calls)
      and "thread_context" not in _synth_calls[0][1]["evidence"]
      and _synth_calls[0][1]["thread_context"]["parent"]["run_id"] == T_ROOT
      and runs_mod.THREAD_ANTI_LEAK_CLAUSE in _synth_calls[0][0]
      and rec_child["thread"]["context_delivery"]["synthesizer"] is True
      and rec_child["thread"]["context_delivery"]["panel"] is False
      and len(rec_child["thread"]["context_delivery"]["prompt_components"]) == 3,
      f"keys={sorted(_synth_calls[0][1]) if _synth_calls else None}")
_panel_thread = [json.loads(t)["deterministic_checks"]["thread"] for t in _PANEL_TXT]
check("ADR-0079 (D) el PANEL (4 jueces) recibe evidencia LIMPIA: sin llave 'thread_context', sin los comentarios ni la nota "
      "de calificación del padre; SÍ deterministic_checks.thread {turn_no 2, parent_run_no raíz, parent_verdict APPROVE, "
      "context_available} — sabe que hubo turno previo, no lee su texto",
      len(_PANEL_TXT) == 4 and all('"thread_context"' not in t for t in _PANEL_TXT)
      and all("COMENTARIO-0079" not in t and "SECRETA-0079" not in t for t in _PANEL_TXT)
      and all(pt["turn_no"] == 2 and pt["parent_run_no"] == rv_root["run_no"] and pt["parent_verdict"] == "APPROVE"
              and pt["context_available"] is True and pt["thread_id"] == T_ROOT for pt in _panel_thread),
      json.dumps(_panel_thread[:1]))
_snapc = {
    "parent_identity": snap["parent"]["run_id"] == T_ROOT and snap["parent"]["run_no"] == rv_root["run_no"],
    "parent_verdict": snap["parent"]["verdict"] == "APPROVE" and snap["parent"]["decision_state"] == "AUDIT_APPROVED",
    "previous_answer": snap["previous_answer"]["direct_answer"].startswith("wt1a (ENSDARG00000031420)")
    and snap["previous_answer"]["gap_flags"] == ["thin coverage of late stages"],
    "previous_audit": snap["previous_audit"]["verdict"] == "APPROVE" and snap["previous_audit"]["n_valid"] == 4,
    "comments_2_of_2": snap["human_comments"]["n_included"] == 2 and snap["human_comments"]["n_total"] == 2
    and snap["human_comments"]["truncated"] is False and snap["human_comments"]["class"] == "atestiguada",
    "comments_order": [c["body"][:18] for c in snap["human_comments"]["items"]] == ["COMENTARIO-0079-A:", "COMENTARIO-0079-B:"],
    "comments_author": snap["human_comments"]["items"][0]["author_name"] == "Natalia",
    # corrector: las unidades viajan declaradas (chars del tope vs bytes del snapshot)
    "units_declared": snap["human_comments"]["limits"]["unit"] == "chars (code points)" and snap["bytes_unit"] == "utf-8 bytes",
    "hints_excluded": snap["evidence_hints"]["entities"] == ["wt1a"] and snap["excluded"] == runs_mod.THREAD_CONTEXT_EXCLUDED,
    "no_rating_note": "SECRETA-0079" not in json.dumps(snap),
    "sha": len(snap["parent_frozen_sha256"]) == 64,
}
check("ADR-0079 (C) snapshot armado en el SERVIDOR desde frozen + comentarios del padre: parent {run_no raíz, verdict, "
      "decision_state}, previous_answer (gap_flags íntegros), previous_audit {verdict, n_valid}, human_comments {2 de 2, "
      "orden determinista, class 'atestiguada', truncated False}, evidence_hints (pistas para RE-RECUPERAR), excluded "
      "declara ratings — y la NOTA de calificación NO está en el snapshot",
      all(_snapc.values()), json.dumps({k: v for k, v in _snapc.items() if not v}) + " " + json.dumps(snap["parent"]))
pcs = rec_child["precedent_citations"]
check("ADR-0079 (E) precedent_citations del hijo = [{l:'A', run_id raíz, run_no raíz, turn_no 1, kind 'turn', "
      "admissible_as_evidence False, why_not_admissible}] vía precedent.serialize_disjoint; validate_disjoint True sobre "
      "{citations (n enteros), precedent}; deterministic_checks.disjoint_series True 'checked'; `citations` conserva su forma "
      "BASE (ADR-0080 añade la escalera de soporte, aditiva)",
      len(pcs) == 1 and pcs[0]["l"] == "A" and pcs[0]["run_id"] == T_ROOT and pcs[0]["run_no"] == rv_root["run_no"]
      and pcs[0]["turn_no"] == 1 and pcs[0]["kind"] == "turn" and pcs[0]["admissible_as_evidence"] is False
      and pcs[0]["why_not_admissible"] == precedent.WHY_NOT_ADMISSIBLE
      and precedent.validate_disjoint({"evidence": rec_child["citations"], "precedent": pcs}) is True
      and rec_child["deterministic_checks"]["disjoint_series"] is True
      and rec_child["deterministic_checks"]["disjoint_series_state"] == "checked"
      and rec_child["precedent_citations_state"] == "checked"
      and _cits_base(rec_child["citations"]) == [{"n": 1, "kind": "di-record", "id": "CORPUS-2026-0001", "note": ""}],
      json.dumps(pcs))
check("ADR-0079 (E) una cita de precedente hecha a mano con 'label':'A' (sin 'l') DEBE fallar validate_disjoint; una letra "
      "dentro de la serie numérica también; una 'l' que además trae 'n' también (ninguna serie produce la etiqueta de la otra)",
      precedent.validate_disjoint({"evidence": [], "precedent": [{"label": "A", "run_id": T_ROOT,
                                                                 "admissible_as_evidence": False}]}) is False
      and precedent.validate_disjoint({"evidence": [{"n": 1, "l": "A", "id": "x"}], "precedent": []}) is False
      and precedent.validate_disjoint({"evidence": [], "precedent": [{"l": "A", "n": 1, "run_id": T_ROOT,
                                                                     "admissible_as_evidence": False}]}) is False)
check("ADR-0079 (I) thread_parent_matches_run True ('checked', regla THREAD_SHA_RULE en el registro): el sha que el snapshot "
      "tomó al ENCOLAR (pre-clausura) == sha del frozen del padre al CONGELAR al hijo (cerrado entre ambos: la clausura "
      "sólo añade frozen_at/closed_by — padre inmutable, ADR-0074); thread.root_run_no = "
      "run_no de la raíz (T5: insumo de 'T-<run_no raíz>' en el PDF); parent_run_no/parent_state declarados",
      rec_child["thread_parent_matches_run"] is True and rec_child["thread_parent_matches_run_state"] == "checked"
      and rec_child["thread_parent_matches_run_rule"] == runs_mod.THREAD_SHA_RULE
      and rec_child["thread_context"]["parent_frozen_sha256"]
      == runs_mod.frozen_sha256(db.get_run(T_ROOT)["frozen_record_json"])
      and rec_child["thread"]["root_run_no"] == rv_root["run_no"]
      and rec_child["thread"]["parent_run_no"] == rv_root["run_no"]
      and rec_child["thread"]["parent_state"] == "closed"
      and rec_child["plan_parent_matches_run"] is None and rec_child["plan_parent_matches_run_state"] == "no-plan",
      json.dumps({k: rec_child.get(k) for k in ("thread_parent_matches_run", "thread_parent_matches_run_state")}))
# --- el PDF del hijo (ADR-0073): INVESTIGACION + EJES en palabras, leídos del JSON congelado -------------------------
_pdf_lines = []
_orig_pdf_p = record_pdf._p


def _p_capture(pdf, text, style="", size=9):
    _pdf_lines.append(text)
    return _orig_pdf_p(pdf, text, style=style, size=size)


record_pdf._p = _p_capture
try:
    pdf_child = record_pdf.build_pdf(rec_child, compress=False)
finally:
    record_pdf._p = _orig_pdf_p
_pdf_txt = "\n".join(_pdf_lines)
check("ADR-0079 (PDF) el registro del hijo imprime INVESTIGACION con la etiqueta 'T-<run_no raíz>' (de thread.root_run_no), "
      "'turno 2 - refinamiento', precedente '[A] turn: turno 1' NO ADMISIBLE COMO EVIDENCIA, 'identidad del padre: COINCIDE', "
      "comentarios humanos '2 de 2' (T5: el sobre dict de runs.py), el origen con su glosa; y EJES DEL EPISODIO en palabras",
      pdf_child[:5] == b"%PDF-" and f"investigacion T-{rv_root['run_no']}" in _pdf_txt
      and "turno 2 - refinamiento" in _pdf_txt and "[A] turn: turno 1" in _pdf_txt
      and "NO ADMISIBLE COMO EVIDENCIA" in _pdf_txt and "identidad del padre: COINCIDE" in _pdf_txt
      and "comentarios humanos: 2 de 2" in _pdf_txt and f"origen: {_ORIGIN['value']}" in _pdf_txt
      and "MUNDO: se afirma un efecto" in _pdf_txt and "INFERENCIA: sostenida (APPROVE)" in _pdf_txt
      and "TECNICO: completada" in _pdf_txt,
      " | ".join(l for l in _pdf_lines if "investigacion T-" in l or "comentarios humanos" in l or "[A]" in l)[:300])

# --- rerun: MISMA pregunta + entities que su padre (el refine) ---------------------------------------------------------
rv_rerun = app.create_run(app.RunBody(question="ADR-0079 refine: does wt1a mark the pronephros at 48 hpf?",
                                      entities=["wt1a"], parent_run_id=T_CHILD), authorization=AUTH)
T_RERUN = rv_rerun["run_id"]
_SYNTH_CTX.clear(); _PANEL_TXT.clear()
rerun_row, rec_rerun = _ejecuta(T_RERUN, synth=_synth_ctx("wt1a marks the pronephros at 48 hpf (re-run)."))
check("ADR-0079 (B) misma pregunta + entities que el padre -> turn_kind 'rerun', turn_no 3 (max del hilo + 1), thread_id = "
      "raíz (heredado, no el padre); el snapshot trae los gap_flags del padre. Corrector (E): el padre (refine) está "
      "awaiting_closure -> NO es precedente: precedent_citations [] + precedent_citations_state 'parent-not-closed', "
      "disjoint_series True con estado 'parent-not-precedent' (tres estados; la letra sólo con padre 'closed')",
      rv_rerun["turn_kind"] == "rerun" and rv_rerun["turn_no"] == 3 and rv_rerun["thread_id"] == T_ROOT
      and rv_rerun["parent_run_id"] == T_CHILD
      and rec_rerun["precedent_citations"] == [] and rec_rerun["precedent_citations_state"] == "parent-not-closed"
      and rec_rerun["thread"]["parent_state"] == "awaiting_closure"
      and rec_rerun["deterministic_checks"]["disjoint_series"] is True
      and rec_rerun["deterministic_checks"]["disjoint_series_state"] == "parent-not-precedent"
      and rec_rerun["thread_context"]["previous_answer"]["gap_flags"] == ["thin coverage of late stages"]
      and rec_rerun["thread"]["root_run_no"] == rv_root["run_no"]
      and _SYNTH_CTX[0][1]["parent"]["run_id"] == T_CHILD,
      json.dumps(_cols(rv_rerun)))

# --- kill-switch WITT_THREAD_CONTEXT=0 (al encolar Y al ejecutar), camino REAL ----------------------------------------
_prev_tc = os.environ.get("WITT_THREAD_CONTEXT")
os.environ["WITT_THREAD_CONTEXT"] = "0"
_REAL_API.clear()
try:
    rv_ksw = app.create_run(app.RunBody(question="ADR-0079 kill-switch: is wt1a required for glomerulus formation?",
                                        entities=["wt1a"], parent_run_id=T_ROOT), authorization=AUTH)
    T_KSW = rv_ksw["run_id"]
    composite_auditor._anthropic_tool_call = _mk_capture_api(
        {**_BASE_SYNTH, "direct_answer": "wt1a is required for glomerulus formation.", "confidence": 0.7,
         "gap_flags": ["thin coverage of late stages"],
         "evidence_cited": [{"kind": "di-record", "id": "CORPUS-2026-0001"}]},
        {"confidence": 0.7}, _REAL_API)
    ksw_row, rec_ksw = _ejecuta(T_KSW, synth=None)
finally:
    composite_auditor._anthropic_tool_call = _orig_tool_call
    if _prev_tc is None:
        os.environ.pop("WITT_THREAD_CONTEXT", None)
    else:
        os.environ["WITT_THREAD_CONTEXT"] = _prev_tc
_ksw_synth = [(s, json.loads(u)) for s, u, name in _REAL_API if name == "emit_answer"]
_ksw_env = json.loads(db.get_run(T_KSW)["thread_context_json"])
check("ADR-0079 kill-switch WITT_THREAD_CONTEXT=0: las COLUMNAS sí se llenan (turno 4, 'branch' — la raíz ya tenía hijo —, "
      "thread raíz), el sobre persistido declara snapshot null + skipped 'kill-switch WITT_THREAD_CONTEXT=0'; en el CAMINO "
      "REAL el user_text es EXACTAMENTE {question, evidence} (SIN la llave) y el system sin cláusula; frozen.thread_context "
      "null + skipped_reason, context_delivery.synthesizer null + prompt_components [], thread_parent_matches_run "
      "null/'no-snapshot' y parent_identifier_leak_state 'no-snapshot' (corrector: hay padre, no se midió — no es 'no-parent'); "
      "precedent_citations sigue con 'A' (el padre está CERRADO aunque el contexto no viaje)",
      rv_ksw["turn_no"] == 4 and rv_ksw["turn_kind"] == "branch" and rv_ksw["thread_id"] == T_ROOT
      and _ksw_env["snapshot"] is None and _ksw_env["skipped_reason"] == "kill-switch WITT_THREAD_CONTEXT=0"
      and _ksw_env["kill_switch"]["WITT_THREAD_CONTEXT"] == "0"
      and len(_ksw_synth) == 2 and all(set(u) == {"question", "evidence"} for _s, u in _ksw_synth)
      and runs_mod.THREAD_ANTI_LEAK_CLAUSE not in _ksw_synth[0][0]
      and rec_ksw["thread_context"] is None
      and rec_ksw["thread_context_skipped_reason"] == "kill-switch WITT_THREAD_CONTEXT=0"
      and rec_ksw["thread"]["context_delivery"]["synthesizer"] is None
      and rec_ksw["thread"]["context_delivery"]["prompt_components"] == []
      and rec_ksw["thread_parent_matches_run"] is None and rec_ksw["thread_parent_matches_run_state"] == "no-snapshot"
      and rec_ksw["deterministic_checks"]["parent_identifier_leak_state"] == "no-snapshot"
      and rec_ksw["precedent_citations"][0]["l"] == "A" and rec_ksw["precedent_citations"][0]["run_id"] == T_ROOT,
      json.dumps({"env": _ksw_env.get("skipped_reason"), "frozen": rec_ksw.get("thread_context_skipped_reason"),
                  "keys": sorted(_ksw_synth[0][1]) if _ksw_synth else None}))

# --- (E) FUGA: un identificador que SOLO vive en el turno anterior y reaparece en la respuesta -> inadmisible -------
# PMID:31415926 lo citó la RAÍZ (está en previous_answer del snapshot); NO está en la evidencia de este hijo. El
# ENSDARG de wt1a también viene del padre pero SÍ está en la evidencia del hijo (entities_checked lo resuelve) -> no es
# fuga: la regla mira la evidencia que el modelo VIO, no sólo los evidence_ids (declarada en parent_identifier_leak_rule).
rv_leak = app.create_run(app.RunBody(question="ADR-0079 branch: is wt1a marking conserved at 72 hpf?",
                                     entities=["wt1a"], parent_run_id=T_ROOT), authorization=AUTH)
T_LEAK = rv_leak["run_id"]
_SYNTH_CTX.clear(); _PANEL_TXT.clear()
leak_row, rec_leak = _ejecuta(T_LEAK, synth=_synth_ctx(
    "wt1a (ENSDARG00000031420) marking is conserved at 72 hpf (PMID:31415926)."))
dc_l = rec_leak["deterministic_checks"]
check("ADR-0079 (B) segundo hijo de la raíz con pregunta nueva -> 'branch', turno 5, thread raíz (la raíz ya tenía a refine "
      "y kill-switch)",
      rv_leak["turn_kind"] == "branch" and rv_leak["turn_no"] == 5 and rv_leak["thread_id"] == T_ROOT
      and rv_leak["parent_run_id"] == T_ROOT)
check("ADR-0079 (E) PMID:31415926 en el thread_context Y en direct_answer Y AUSENTE de la evidencia del hijo -> "
      "parent_identifier_leak ['PMID:31415926'] -> predicado DURO -> admissible False con la razón declarada; el ENSDARG "
      "resuelto por el store NO figura (está en la evidencia del hijo); la corrida TERMINA (inadmisible se declara, no "
      "tumba) y el PANEL vio el hallazgo en deterministic_checks",
      dc_l["parent_identifier_leak"] == ["PMID:31415926"] and dc_l["parent_identifier_leak_state"] == "checked"
      and dc_l["admissible"] is False and any("parent_identifier_leak" in r for r in dc_l["reasons"])
      and "PMID" in dc_l["parent_identifier_leak_rule"] and "evidence text" in dc_l["parent_identifier_leak_rule"]
      and leak_row["state"] == "awaiting_closure"
      and "PMID:31415926" in rec_leak["thread_context"]["previous_answer"]["direct_answer"]
      and all(json.loads(t)["deterministic_checks"]["parent_identifier_leak"] == ["PMID:31415926"]
              for t in _PANEL_TXT[:4]),
      json.dumps({"leak": dc_l["parent_identifier_leak"], "reasons": dc_l["reasons"]}))

# --- (H) GET /threads/{raíz}: la investigación como UNA unidad, todo calculado en código -------------------------------
th = app.get_thread(T_ROOT, authorization=AUTH)
_turnos = {t["turn_no"]: t for t in th["turns"]}
_suma = round(sum(float(t["estimated_cost_usd"] or 0.0) for t in th["turns"]), 4)
check("ADR-0079 (H) GET /threads/{raíz}: label 'T-<run_no raíz>', 5 turnos en orden [root, refine, rerun, branch, branch] "
      "con veredicto/decision_state del registro congelado, origins {origen: 5}, authors ['natalia'], todos con registro, "
      "n_closed 1 (la raíz se cerró antes de ejecutar a su hijo)",
      th["label"] == f"T-{rv_root['run_no']}" and th["root_run_id"] == T_ROOT and th["root_run_no"] == rv_root["run_no"]
      and th["n_turns"] == 5 and [t["turn_no"] for t in th["turns"]] == [1, 2, 3, 4, 5]
      and [t["turn_kind"] for t in th["turns"]] == ["root", "refine", "rerun", "branch", "branch"]
      and _turnos[1]["verdict"] == "APPROVE" and _turnos[2]["verdict"] == "APPROVE" and _turnos[4]["verdict"] == "APPROVE"
      and _turnos[5]["decision_state"] in ("AUDIT_APPROVED", "AUDIT_REJECTED")
      and th["origins"] == {_ORIGIN["value"]: 5} and th["authors"] == ["natalia"]
      and th["n_turns_without_record"] == 0 and th["root_pre_adr_0079"] is False and th["n_closed"] == 1,
      json.dumps({"label": th["label"], "kinds": [t["turn_kind"] for t in th["turns"]], "origins": th["origins"]}))
_gu = th["gap_flags_union"]
check("ADR-0079 (H) gap_flags_union agrega SIN duplicar (igualdad lower/strip; conteo POR TURNO; texto de la PRIMERA "
      "aparición): 'thin coverage of late stages' count 5, first_turn 1, last_turn 5; textos normalizados únicos",
      any(g["text"] == "thin coverage of late stages" and g["count"] == 5 and g["first_turn"] == 1 and g["last_turn"] == 5
          for g in _gu)
      and len({g["text"].strip().lower() for g in _gu}) == len(_gu),
      json.dumps(_gu))
check("ADR-0079 (H) total_cost_usd = SUMA de los estimated_cost_usd CONGELADOS por turno, etiquetada PROJECTION y declarada "
      "INCOMPLETA: 3 turnos con stub-synth (sin precio) -> n_turns_cost_incomplete 3, complete False, 0 sin usage",
      th["total_cost_usd"]["value"] == _suma and th["total_cost_usd"]["complete"] is False
      and th["total_cost_usd"]["n_turns_cost_incomplete"] == 3 and th["total_cost_usd"]["n_turns_without_usage"] == 0
      and "PROJECTION" in th["total_cost_usd"]["cost_class"]
      and all(t["cost_projection_complete"] in (True, False) for t in th["turns"]),
      json.dumps(th["total_cost_usd"]))
check("ADR-0079 (H) pivot_suggested True con 3 turnos PLANOS consecutivos (turnos 3-4-5: el mismo conjunto de gap_flags, "
      "nada se cerró) — regla WITT_PIVOT_TURNS declarada, threshold 3, turns_considered [3,4,5]; es sugerencia calculada",
      th["pivot_suggested"]["value"] is True and th["pivot_suggested"]["threshold"] == app.PIVOT_TURNS == 3
      and th["pivot_suggested"]["turns_considered"] == [3, 4, 5] and th["pivot_suggested"]["rule"] == app.PIVOT_RULE
      and th["pivot_suggested"]["reason"] is None,
      json.dumps(th["pivot_suggested"]))
check("ADR-0079 (H) investigación inexistente -> 404 thread_not_found",
      _http_error(app.get_thread, "no-such-thread", authorization=AUTH) == 404)
p1 = app.list_runs(thread=T_ROOT, limit=2, authorization=AUTH)
p2 = app.list_runs(thread=T_ROOT, limit=2, after=p1["next_after"], authorization=AUTH)
p3 = app.list_runs(thread=T_ROOT, limit=2, after=p2["next_after"], authorization=AUTH)
check("ADR-0079 (H) GET /runs?thread=&limit=2 pagina por turn_no (cursor EXCLUSIVO, has_more MEDIDO con limit+1): "
      "[1,2] next_after 2 -> [3,4] next_after 4 -> [5] has_more False; sin limit = la investigación entera (5, sin tope 50); "
      "`after` sin thread = 400; los renglones son la MISMA vista que el detalle",
      [r["turn_no"] for r in p1["runs"]] == [1, 2] and p1["has_more"] is True and p1["next_after"] == 2
      and [r["turn_no"] for r in p2["runs"]] == [3, 4] and p2["has_more"] is True and p2["next_after"] == 4
      and [r["turn_no"] for r in p3["runs"]] == [5] and p3["has_more"] is False and p3["next_after"] is None
      and app.list_runs(thread=T_ROOT, authorization=AUTH)["n"] == 5
      and _http_error(app.list_runs, after=1, authorization=AUTH) == 400
      and _cols(p1["runs"][1]) == _cols(app.get_run(T_CHILD, authorization=AUTH)),
      json.dumps({"p1": [r["turn_no"] for r in p1["runs"]], "next": p1["next_after"]}))
check("ADR-0079 corrector (H) la lista general valida el signo ANTES de consultar: limit=-1 -> 400 (antes llegaba a LIMIT -1 = "
      "sin tope en SQLite / 500 en Postgres); limit=500 -> limit 50 declarado con limit_cap 50; db.list_runs(limit=0) -> ValueError",
      _http_error(app.list_runs, limit=-1, authorization=AUTH) == 400
      and _http_error(app.list_runs, thread=T_ROOT, limit=0, authorization=AUTH) == 400
      and app.list_runs(limit=500, authorization=AUTH)["limit"] == 50
      and _raises(lambda: db.list_runs(limit=0), ValueError))

check("ADR-0079 corrector (E) un DOI con punto final de prosa en el snapshot y en la respuesta, PRESENTE en la evidencia del "
      "hijo -> NO es fuga (extract_identifiers recorta './,' finales; antes el token '…456.' no casaba y el predicado DURO "
      "vetaba una respuesta legítima); el mismo DOI AUSENTE de la evidencia sí es fuga",
      runs_mod.parent_identifier_leak({"previous_answer": "see doi 10.1242/dev.123456."}, "as shown in 10.1242/dev.123456.",
                                      [], '{"doi": "10.1242/dev.123456"}') == []
      and runs_mod.parent_identifier_leak({"previous_answer": "see doi 10.1242/dev.123456."}, "as shown in 10.1242/dev.123456.",
                                          [], "") == ["10.1242/DEV.123456"]
      and runs_mod.extract_identifiers("cited PMID: 123, doi 10.1000/abc.1,") == {"PMID:123", "10.1000/ABC.1"})

# --- (F) consumidores del ORIGEN: precedente y calibración excluyen este gate por default y lo CUENTAN ---------------
# (la raíz T_ROOT ya se cerró antes de ejecutar a su hijo; las cerradas de este gate son RID y T_ROOT = 2)
precedent._IDX["key"] = None
ps_def = app.precedent_search(q="ADR-0079 raiz wt1a pronephros", k=10, authorization=AUTH)
ps_inc = app.precedent_search(q="ADR-0079 raiz wt1a pronephros", k=10, include_origins=_ORIGIN["value"],
                              authorization=AUTH)
_item = next((i for i in ps_inc["items"] if i["run_id"] == T_ROOT), None)
check("ADR-0079 (F) /precedent/search por DEFAULT excluye y CUENTA las corridas cerradas de este gate (origin ∉ production): "
      "origins_included ['production'], excluded_by_origin {origen: 2}, items [] (n_closed_runs 0), origin_unknown_included 0; "
      "con include_origins=<origen> entra la raíz cerrada con run_no/thread_id/turn_no 1/turn_kind 'root' (T5: db.closed_runs "
      "SELECTea turn_kind) y origin — admissible_as_evidence False",
      ps_def["origins_included"] == ["production"] and ps_def["excluded_by_origin"].get(_ORIGIN["value"]) == 2
      and ps_def["items"] == [] and ps_def["n_closed_runs"] == 0 and ps_def["origin_unknown_included"] == 0
      and ps_inc["origins_included"] == [_ORIGIN["value"]] and ps_inc["n_closed_runs"] == 2
      and _item is not None and _item["turn_kind"] == "root" and _item["turn_no"] == 1 and _item["thread_id"] == T_ROOT
      and _item["origin"] == _ORIGIN["value"] and _item["run_no"] == rv_root["run_no"]
      and _item["admissible_as_evidence"] is False,
      json.dumps({"def": {k: ps_def.get(k) for k in ("origins_included", "excluded_by_origin", "n_closed_runs")},
                  "item": {k: (_item or {}).get(k) for k in ("turn_kind", "turn_no", "origin", "run_no")}}))
cal_def = app.calibration_report(authorization=AUTH)
cal_inc = app.calibration_report(include_origins=_ORIGIN["value"], authorization=AUTH)
check("ADR-0079 (F) /calibration declara su alcance por origen: default origins_included ['production'] con este gate excluido "
      "y contado (n_closed 0); include_origins=<origen> lo incluye (n_closed 2); origen fuera del enum -> 400 invalid-origin",
      cal_def["origins_included"] == ["production"] and cal_def["excluded_by_origin"].get(_ORIGIN["value"]) == 2
      and cal_def["n_closed"] == 0 and cal_inc["origins_included"] == [_ORIGIN["value"]] and cal_inc["n_closed"] == 2
      and _http_error(app.calibration_report, include_origins="marte", authorization=AUTH) == 400,
      json.dumps({k: cal_def.get(k) for k in ("origins_included", "excluded_by_origin", "n_closed")}))

# --- (F) corrector: la FUENTE del origen es la de ENCOLAR, persistida en el sobre; la re-derivación viaja aparte -------
_prev_ro = os.environ.get("WITT_RUN_ORIGIN")
os.environ["WITT_RUN_ORIGIN"] = "dev-offline"          # encolada con la env (source env:WITT_RUN_ORIGIN)
try:
    rv_src = app.create_run(app.RunBody(question="ADR-0079 corrector: fuente del origen al encolar", entities=[]),
                            authorization=AUTH)
    os.environ.pop("WITT_RUN_ORIGIN", None)            # ejecutada SIN la env: la máscara deriva el MISMO valor…
    assert runs_mod.run_origin() == {"value": "dev-offline", "source": "derived:offline-mask"}
    _SYNTH_CTX.clear(); _PANEL_TXT.clear()
    src_row, rec_src = _ejecuta(rv_src["run_id"], synth=_synth_ctx("origin source probe."))
finally:
    if _prev_ro is None:
        os.environ.pop("WITT_RUN_ORIGIN", None)
    else:
        os.environ["WITT_RUN_ORIGIN"] = _prev_ro
_env_src = json.loads(db.get_run(rv_src["run_id"])["thread_context_json"])
check("ADR-0079 corrector (F) mismo VALOR, distinta FUENTE entre encolar y ejecutar: frozen.origin.source = 'env:WITT_RUN_ORIGIN' "
      "(copiada del sobre thread_context_json.origin persistido al encolar), source_at_execution declara "
      "'derived:offline-mask' con same_value_as_column True — la procedencia registrada no se re-deriva",
      _env_src["origin"] == {"value": "dev-offline", "source": "env:WITT_RUN_ORIGIN"}
      and rec_src["origin"]["value"] == "dev-offline" and rec_src["origin"]["source"] == "env:WITT_RUN_ORIGIN"
      and rec_src["origin"]["source_at_execution"] == {"value": "dev-offline", "source": "derived:offline-mask",
                                                       "same_value_as_column": True}
      and rec_src["origin"]["note"] is None,
      json.dumps(rec_src["origin"]))

# --- corrector: procedencia plan<->padre — el plan declara QUÉ padre/sha vio; el registro lo casa con la corrida ------
_pl_ok = app.create_plan(app.PlanBody(question="ADR-0079 plan con padre: wt1a at 96 hpf?", entities=["wt1a"],
                                      parent_run_id=T_ROOT), authorization=AUTH)
rv_plan_ok = app.create_run(app.RunBody(question="ADR-0079 plan con padre: wt1a at 96 hpf?", entities=["wt1a"],
                                        parent_run_id=T_ROOT, plan_id=_pl_ok["plan_id"]), authorization=AUTH)
_SYNTH_CTX.clear(); _PANEL_TXT.clear()
_, rec_plan_ok = _ejecuta(rv_plan_ok["run_id"], synth=_synth_ctx("wt1a at 96 hpf: sustained."))
_pl_x = app.create_plan(app.PlanBody(question="ADR-0079 plan con OTRO padre", entities=["wt1a"], parent_run_id=T_ROOT),
                        authorization=AUTH)
rv_plan_x = app.create_run(app.RunBody(question="ADR-0079 plan con OTRO padre", entities=["wt1a"],
                                       parent_run_id=T_CHILD, plan_id=_pl_x["plan_id"]), authorization=AUTH)
_SYNTH_CTX.clear(); _PANEL_TXT.clear()
_, rec_plan_x = _ejecuta(rv_plan_x["run_id"], synth=_synth_ctx("mismatch probe."))
check("ADR-0079 corrector (B/I) plan<->padre: el plan guarda thread_parent_run_id + thread_parent_frozen_sha256 (lo que el "
      "planner VIO); al congelar, plan_parent_matches_run True/'checked' y plan_snapshot_matches_run True/'checked' cuando "
      "plan y corrida declaran el MISMO padre; un plan hecho con el padre X respaldando una corrida con padre Y -> "
      "plan_parent_matches_run False y plan_snapshot_matches_run False (declarado, jamás silencioso); la raíz sin plan -> "
      "None/'no-plan'",
      _pl_ok["plan"]["thread_parent_run_id"] == T_ROOT and len(_pl_ok["plan"]["thread_parent_frozen_sha256"]) == 64
      and rec_plan_ok["plan_parent_matches_run"] is True and rec_plan_ok["plan_parent_matches_run_state"] == "checked"
      and rec_plan_ok["plan_snapshot_matches_run"] is True and rec_plan_ok["plan_snapshot_matches_run_state"] == "checked"
      and rec_plan_ok["plan_declared"] is True and rec_plan_ok["plan_question_matches_run"] is True
      and rec_plan_x["plan_parent_matches_run"] is False and rec_plan_x["plan_parent_matches_run_state"] == "checked"
      and rec_plan_x["plan_snapshot_matches_run"] is False and rec_plan_x["plan_snapshot_matches_run_state"] == "checked"
      and rec_root["plan_parent_matches_run"] is None and rec_root["plan_parent_matches_run_state"] == "no-plan"
      and rec_root["plan_snapshot_matches_run_state"] == "no-plan",
      json.dumps({k: rec_plan_x.get(k) for k in ("plan_parent_matches_run", "plan_snapshot_matches_run")}))

# --- corrector: la CARRERA de turn_no la cierra el índice único (thread_id, turn_no) + re-derivación en new_run --------
_orig_max_turn = db.max_turn_no
_stale_calls = []


def _max_turn_stale(thread_id):
    """La primera lectura devuelve un máximo VIEJO (como si otro hijo hubiera entrado entre leer e insertar)."""
    real = _orig_max_turn(thread_id)
    _stale_calls.append(real)
    return (real - 1) if len(_stale_calls) == 1 else real


_max_before = db.max_turn_no(T_ROOT)
db.max_turn_no = _max_turn_stale
try:
    rv_race = app.create_run(app.RunBody(question="ADR-0079 corrector: carrera de turn_no", entities=["wt1a"],
                                         parent_run_id=T_ROOT), authorization=AUTH)
finally:
    db.max_turn_no = _orig_max_turn
check("ADR-0079 corrector (A/B) carrera de turn_no RESUELTA: con un máximo viejo el INSERT choca contra ux_runs_thread_turn "
      "(índice único thread_id, turn_no), new_run RE-DERIVA (2 lecturas) y la corrida nace con el turn_no siguiente; el "
      "índice rechaza un duplicado directo (IntegrityError); GET /runs?thread= sigue sin huecos",
      len(_stale_calls) == 2 and rv_race["turn_no"] == _max_before + 1 and rv_race["turn_kind"] == "branch"
      and _raises(lambda: db.create_run("dup" + "c" * 29, "natalia", "dup turn", [], thread_id=T_ROOT,
                                        turn_no=rv_race["turn_no"], turn_kind="branch", parent_run_id=T_ROOT),
                  __import__("sqlalchemy.exc", fromlist=["IntegrityError"]).IntegrityError)
      and [r["turn_no"] for r in app.list_runs(thread=T_ROOT, authorization=AUTH)["runs"]]
      == list(range(1, rv_race["turn_no"] + 1)),
      json.dumps({"stale_calls": _stale_calls, "turn_no": rv_race["turn_no"]}))
db.update_run(rv_race["run_id"], state="cancelled")   # que el FIFO de abajo no la reclame

# --- (A) una fila ANTERIOR al contrato: NULL en todo, sin backfill; raíz VIRTUAL al servir ---------------------------
PRE_0079 = "pre0079" + "b" * 25
db.create_run(PRE_0079, "natalia", "pre-ADR question (fila anterior al contrato)", ["wt1a"])
db.update_run(PRE_0079, state="awaiting_closure")   # terminal SIN registro (como una corrida vieja): que el FIFO
                                                      # de las _ejecuta de abajo no la reclame
v_pre = app.get_run(PRE_0079, authorization=AUTH)
th_pre = app.get_thread(PRE_0079, authorization=AUTH)
check("ADR-0079 (A) una fila anterior al contrato queda NULL en las 6 columnas de la vista (ausencia declarada: 'sin "
      "investigación' / origin unknown-pre-adr-0079; sin backfill), idéntica en lista y detalle; GET /threads la LEE como raíz "
      "VIRTUAL (root_pre_adr_0079 True, turn_no null — derivación al servir, cero escritura)",
      all(v_pre[k] is None for k in _THREAD_COLS)
      and _cols(next(r for r in app.list_runs(authorization=AUTH)["runs"] if r["run_id"] == PRE_0079)) == _cols(v_pre)
      and th_pre["root_pre_adr_0079"] is True and th_pre["turns"][0]["turn_no"] is None
      and th_pre["turns"][0]["root_pre_adr_0079"] is True and th_pre["origins"] == {app.ORIGIN_UNKNOWN: 1}
      and db.get_run(PRE_0079)["thread_id"] is None,
      json.dumps(_cols(v_pre)))

# --- (G) los EJES del episodio por TABLA (EPISODE_AXES_MAP) sobre registros REALES del gate + fixtures nuevos ----------
rv_nb = app.create_run(app.RunBody(question="ADR-0079 ejes: null-bounded", entities=[]), authorization=AUTH)
_, rec_nb = _ejecuta(rv_nb["run_id"], synth=_mk_synth({"pass1": 0.8}, extra={"absence_kind": "evidence-of-no-effect"}))
rv_ind = app.create_run(app.RunBody(question="ADR-0079 ejes: indeterminate + honest decline", entities=[]),
                        authorization=AUTH)
_, rec_ind = _ejecuta(rv_ind["run_id"], synth=_mk_synth({"pass1": 0.8}, extra={"absence_kind": "no-evidence-retrieved"}),
                      panel=_panel_capture({k: "APPROVE_DECLINE" for k in ALL_A}))
rag_backend.query = lambda text, k=6: HitList([_chunk], degraded="sparse-by-config")
rv_deg = app.create_run(app.RunBody(question="ADR-0079 ejes: degraded retrieval", entities=[]), authorization=AUTH)
_, rec_deg = _ejecuta(rv_deg["run_id"], synth=_mk_synth({"pass1": 0.8}))
rag_backend.query = lambda text, k=6: HitList([_chunk], degraded=None)


def _axes(r):
    return (r["episode_axes"]["world"], r["episode_axes"]["inference"], r["episode_axes"]["technical"])


check("ADR-0079 (G) episode_axes por TABLA sobre 6 registros del gate: APPROVED×not-applicable×APPROVE -> effect-claimed/"
      "supported/completed · evidence-of-no-effect -> null-bounded · no-evidence-retrieved×APPROVE_DECLINE -> indeterminate/"
      "honest-decline · REJECTED (REVISE tras revisión) -> not-established/insufficient · REVISE por panel delgado -> "
      "not-established · retrieval no semántica -> technical degraded con nota; todos class 'derived-at-freeze' + map",
      _axes(rec_root) == ("effect-claimed", "supported", "completed")
      and _axes(rec_nb) == ("null-bounded", "supported", "completed")
      and _axes(rec_ind) == ("indeterminate", "honest-decline", "completed")
      and _axes(rec_rr) == ("not-established", "insufficient", "completed")
      and _axes(rec_tp) == ("not-established", "insufficient", "completed")
      and _axes(rec_deg) == ("effect-claimed", "supported", "degraded") and rec_deg["retrieval_summary"]["mode"] != "semantic"
      and any("degraded" in n for n in rec_deg["episode_axes"]["notes"])
      and all(r["episode_axes"]["class"] == "derived-at-freeze"
              and r["episode_axes"]["map"] == "runs.EPISODE_AXES_MAP (ADR-0079)"
              for r in (rec_root, rec_nb, rec_ind, rec_rr, rec_tp, rec_deg)),
      json.dumps({"root": _axes(rec_root), "nb": _axes(rec_nb), "ind": _axes(rec_ind), "rr": _axes(rec_rr),
                  "tp": _axes(rec_tp), "deg": _axes(rec_deg)}))
_na = runs_mod.episode_axes("DI_SUFFICIENT", None, None, "failed", None, _ORIGIN["value"], False, False, None)
_cn = runs_mod.episode_axes("AUDIT_APPROVED", "not-applicable", "APPROVE_MINOR", "cancelled", "semantic", "production",
                            True, False, {"thread_id": "t", "turn_no": 2, "turn_kind": "refine"})
_ab = runs_mod.episode_axes("AUDIT_APPROVED", None, "APPROVE", "closed", "semantic", None, False, True, None)
check("ADR-0079 (G) la función pura cubre lo que un registro congelado no produce: sin veredicto -> not-assessed/not-evaluated "
      "+ technical failed · cancelled × APPROVE_MINOR -> minor-issues/cancelled con provenance {origin, human_gates, turn} · "
      "APPROVED sin absence_kind -> indeterminate DECLARADO en notes · human_gates.closed True cuando se pide; y la TABLA "
      "EPISODE_AXES_MAP dice lo mismo (es la que copia el ADR)",
      (_na["world"], _na["inference"], _na["technical"]) == ("not-assessed", "not-evaluated", "failed")
      and (_cn["world"], _cn["inference"], _cn["technical"]) == ("effect-claimed", "minor-issues", "cancelled")
      and _cn["provenance"] == {"origin": "production",
                                "human_gates": {"plan_declared": True, "closed": False,
                                                "closed_note": _cn["provenance"]["human_gates"]["closed_note"]},
                                "turn": {"thread_id": "t", "turn_no": 2, "turn_kind": "refine"}}
      and _ab["world"] == "indeterminate" and any("absence_kind" in n for n in _ab["notes"])
      and _ab["provenance"]["human_gates"]["closed"] is True and _ab["provenance"]["origin"] is None
      and runs_mod.EPISODE_AXES_MAP["class"] == "derived-at-freeze"
      and runs_mod.EPISODE_AXES_MAP["world"]["AUDIT_REJECTED"] == "not-established"
      and runs_mod.EPISODE_AXES_MAP["world"]["AUDIT_APPROVED × evidence-of-no-effect"] == "null-bounded"
      and runs_mod.EPISODE_AXES_MAP["inference"]["APPROVE_DECLINE"] == "honest-decline"
      and runs_mod.EPISODE_AXES_MAP["technical"]["failed"] == "failed",
      json.dumps({"na": (_na["world"], _na["technical"]), "ab_notes": _ab["notes"]}))
_ax_rej = runs_mod.episode_axes("AUDIT_REJECTED", None, None, "awaiting_closure", "semantic", None, False, False, None)
_ax_nt = runs_mod.episode_axes("FALLBACK_FETCHED", "not-applicable", "APPROVE", "awaiting_closure", "semantic", None,
                               False, False, None)
check("ADR-0079 corrector (G) la TABLA dice lo que la función hace en los dos caminos de precedencia: AUDIT_REJECTED SIN "
      "veredicto -> world not-assessed (el 'sin veredicto' precede a decision_state); veredicto presente con decision_state "
      "no terminal de auditoría -> not-assessed con nota; ambas filas figuran en EPISODE_AXES_MAP.world",
      _ax_rej["world"] == "not-assessed" and _ax_rej["inference"] == "not-evaluated"
      and _ax_nt["world"] == "not-assessed" and _ax_nt["inference"] == "supported" and any("not-assessed" in n for n in _ax_nt["notes"])
      and runs_mod.EPISODE_AXES_MAP["world"]["<no audit verdict> (precede a decision_state)"] == "not-assessed"
      and "<verdict present> × decision_state ∉ {AUDIT_APPROVED, AUDIT_REJECTED}" in runs_mod.EPISODE_AXES_MAP["world"])
check("ADR-0079 (G) epistemic_summary de cada turno (derivado al congelar, regla frozen-counter) lleva thread_id/turn_no/origin "
      "y la lista los sirve tal cual (turnos 1..5 de la investigación)",
      all(app.get_run(rid, authorization=AUTH)["epistemic_summary"]["thread_id"] == T_ROOT
          and app.get_run(rid, authorization=AUTH)["epistemic_summary"]["turn_no"] == n
          and app.get_run(rid, authorization=AUTH)["epistemic_summary"]["origin"] == _ORIGIN["value"]
          for rid, n in ((T_ROOT, 1), (T_CHILD, 2), (T_RERUN, 3), (T_KSW, 4), (T_LEAK, 5))))

# ---- ADR-0080: la COMPUERTA DE COMPETENCIA y el HARNESS de búsqueda — integración C1..C6 (C7) ---------
# competence.evaluate (decidido por CÓDIGO) <-> runs.execute_run (elicit{pass} · gate{pass:1} ADELANTADO ·
# stage.competence · plan · rondas · pass2) <-> lib/search_harness (SEARCH_DISPATCH sobre los archivos REALES de
# .tooluniverse/tools, rondas con presupuesto, ledger) <-> answer_pipeline.path_b_bundle(search_plan=) <->
# verify_output (positive_claim_requires_citations, escalera support_state) <-> composite_auditor (reintento por
# juez, citation_support). 100% offline: las tools Layer 0 se INYECTAN en search_harness._TOOL_CACHE (tras
# verificar que las reales resuelven), las tres fuentes legadas por sus costuras de hoy, el reloj del harness es
# falso (_sh._monotonic) y urllib.request.urlopen queda BLOQUEADO Y CONTADO durante la sección: "cero red" es
# MEDICIÓN, no promesa. Cero modelo, cero mutación de mcp_cache (snapshot antes/después).
# =====================================================================================================
import time as _time  # noqa: E402
import urllib.request as _urlreq  # noqa: E402
from lib import search_harness as _sh, verify_output as _vo  # noqa: E402
import competence as _cg  # noqa: E402

_NET_CALLS = []
_urlopen_real = _urlreq.urlopen


def _urlopen_blocked(*a, **kw):
    _NET_CALLS.append(str(a[0] if a else kw.get("url")))
    raise RuntimeError("network blocked by smoke_run_pipeline (ADR-0080 offline gate)")


_urlreq.urlopen = _urlopen_blocked
_MCP_CACHE_DIR = answer_pipeline.CACHE


def _mcp_snapshot():
    if not _MCP_CACHE_DIR.exists():
        return []
    return sorted((p.name, p.stat().st_size) for p in _MCP_CACHE_DIR.iterdir()
                  if p.is_file() and not p.name.endswith(".log"))


_mcp_before = _mcp_snapshot()
_cache_zfin_real = answer_pipeline._cache_zfin
answer_pipeline._cache_zfin = lambda symbol, res: []   # la caché por día de ZFIN no se toca desde el gate

# --- (C/D) cableado ESTÁTICO: la tabla apunta a los archivos REALES de C3–C5 --------------------------------
_L0_FAMILIES = ("alliance_orthologs", "zfin_expression", "ensembl_homology", "uniprot", "monarch", "reactome",
                "string", "geo", "unpaywall_crossref", "openalex")
_sh._TOOL_CACHE.clear()
_wiring = {}
for _fam in _L0_FAMILIES + ("pubmed", "zfin"):
    _spec = _sh.SEARCH_DISPATCH[_fam]
    _fn, _resolved, _detail = _sh._load_tool(_fam)
    _wiring[_fam] = {"file_exists": (_sh._TU_WORKSPACE / _spec["tool_module"]).exists(),
                     "fn_declared": _spec["fn"], "fn_resolved": _resolved, "detail": _detail, "callable": callable(_fn)}
_web_load = _sh._load_tool("web")
check("ADR-0080 (C/D) SEARCH_DISPATCH apunta a los archivos REALES de C3–C5 (+pubmed/zfin de hoy): los 12 módulos existen "
      "bajo .tooluniverse/tools y _load_tool resuelve EXACTAMENTE la función declarada (fn_resolved == fn, sin nota); "
      "ADR-0084 (C.1): 'web' resuelve el tool REAL brave_web_search.locate (13.º módulo, cargado por ruta; la disponibilidad la decide "
      "web_locator.provider_state EN LA LLAMADA, no la tabla); 'tooluniverse' queda tool-unavailable DECLARADO (ADR-0085); las 15 "
      "familias tienen gate/evidence_kind/label en vocabulario",
      all(w["file_exists"] and w["callable"] and w["fn_resolved"] == w["fn_declared"] and w["detail"] is None
          for w in _wiring.values())
      and callable(_web_load[0]) and _web_load[1:] == ("locate", None)
      and _sh.SEARCH_DISPATCH["web"]["tool_module"] == "brave_web_search.py" and _sh.SEARCH_DISPATCH["web"]["adapter"] == "web"
      and _sh.SEARCH_DISPATCH["web"]["unavailable_reason"] == "tool-unavailable (ADR-0084)"
      and _sh._load_tool("tooluniverse") == (None, None, "tool-unavailable (ADR-0085)")
      and len(_sh.SEARCH_DISPATCH) == 15
      and all(s["gate"] in _sh.GATES and s["label_provenance"] in _sh.LABELS and s.get("evidence_kind")
              for s in _sh.SEARCH_DISPATCH.values())
      and [f for f, s in _sh.SEARCH_DISPATCH.items() if s["gate"] == "auto"] == list(_sh.DEFAULT_FAMILIES),
      json.dumps({k: (v["fn_resolved"], v["detail"]) for k, v in _wiring.items()
                  if not (v["fn_resolved"] == v["fn_declared"] and v["detail"] is None)}))

# --- (C7 costura C2<->C5) la tabla casa con la forma REAL de las tools ---------------------------------------
_doi_res = {"status": "success", "query_sent": "GET api.crossref.org/works/10.1242/dev.02071", "elapsed_s": 0.1,
            "data": {"doi": "10.1242/dev.02071",
                     "crossref": {"source": "crossref", "status": "success", "evidence_kind": "paper-metadata",
                                  "identifier_provenance": "crossref-works",
                                  "data": {"doi": "10.1242/dev.02071", "year": 2005,
                                           "title": "Fgf signals from a novel signaling center determine axial patterning",
                                           "url": "https://doi.org/10.1242/dev.02071", "abstract": "abs"}},
                     "unpaywall": {"source": "unpaywall", "status": "tool-unavailable",
                                   "reason": "WITT_UNPAYWALL_EMAIL unset", "contact": "unset"}}}
_els, _lk = _sh._result_list(_doi_res, _sh.SEARCH_DISPATCH["unpaywall_crossref"])
_it = _sh.normalize_item("unpaywall_crossref", _els[0], _sh.SEARCH_DISPATCH["unpaywall_crossref"], _doi_res,
                         input_value="10.1242/dev.02071") if _els else {}
_plan_doi = {"families": ["unpaywall_crossref"], "queries": {"unpaywall_crossref": {"inputs": "dois"}}, "symbols": []}
_rd_tu = _sh.run_round(_plan_doi, 1, 30.0, ctx={"dois": ["10.1242/dev.02071"]},
                       tools={"unpaywall_crossref": lambda doi, timeout=None, **kw: {
                           "status": "tool-unavailable", "error": "WITT_UNPAYWALL_EMAIL unset", "query_sent": None}})
_rd_sb = _sh.run_round(_plan_doi, 1, 30.0, ctx={"dois": ["10.1242/dev.02071"]},
                       tools={"unpaywall_crossref": lambda doi, timeout=None, **kw: {
                           "status": "skipped-budget", "error": "BudgetExhausted", "query_sent": None}})
check("ADR-0080 (C7 costura C2<->C3/C5) la tabla casa con la forma REAL de las tools: geo/openalex dejan la lista en "
      "data.records; unpaywall_crossref deja UNA fila por fuente (source_rows) -> _result_list produce un elemento por fila "
      "'success' con evidence_id '<fuente>:<doi>' (la fila tool-unavailable NO produce nada) y el ítem normalizado conserva "
      "kind/identifier_provenance de la fila; una familia cuyas llamadas dijeron TODAS 'tool-unavailable' | 'skipped-budget' "
      "hereda ese literal (no se degrada a 'error') con la razón del tool en detail",
      _sh.SEARCH_DISPATCH["geo"]["list_keys"] == ("records",) and _sh.SEARCH_DISPATCH["openalex"]["list_keys"] == ("records",)
      and _lk == "source-rows" and len(_els) == 1 and _els[0]["evidence_id"] == "crossref:10.1242/dev.02071"
      and _it.get("kind") == "paper-metadata" and _it.get("identifier_provenance") == "crossref-works"
      and _it.get("url") == "https://doi.org/10.1242/dev.02071" and _it.get("source_family") == "unpaywall_crossref"
      and _rd_tu["sources"][0]["status"] == "tool-unavailable" and _rd_tu["sources"][0]["n_found"] is None
      and _rd_tu["sources"][0]["detail"] == "WITT_UNPAYWALL_EMAIL unset" and _rd_tu["n_new_total"] == 0
      and _rd_sb["sources"][0]["status"] == "skipped-budget",
      f"list_key={_lk} n={len(_els)} tu={_rd_tu['sources'][0]['status']} sb={_rd_sb['sources'][0]['status']}")

# --- fakes Layer 0 inyectadas en _TOOL_CACHE + reloj falso del harness --------------------------------------
_CLOCK = {"t": 0.0}
_sh._monotonic = lambda: _CLOCK["t"]
_TOOL_CALLS = []
_ALLIANCE_EL = {"species": "Homo sapiens", "taxon_id": "NCBITaxon:9606", "symbol": "WT1", "id": "HGNC:12796",
                "stringency": "stringent", "best": "Yes", "confidence": "high",
                "evidence_id": "alliance-ortholog:ZFIN:ZDB-GENE-980526-558->HGNC:12796",
                "url": "https://www.alliancegenome.org/gene/HGNC:12796", "identifier_provenance": "alliance-api-payload"}


def _fake_l0(family, status="no-match", elements=None, list_key="items", bump_clock_s=0.0, cache_hit=False):
    def _fn(x, timeout=None, **kw):
        _TOOL_CALLS.append({"family": family, "input": x, "timeout": timeout})
        if bump_clock_s:
            _CLOCK["t"] += bump_clock_s
        out = {"status": status, "query_sent": f"{family}?q={x}", "elapsed_s": bump_clock_s, "cache_hit": cache_hit,
               "data": {list_key: list(elements or [])}}
        if status == "error":
            out["error"] = "HTTPError: 503 (simulated)"
        return out
    return _fn


def _inject_l0(alliance_status="success", alliance_bump=0.0, expr_status="no-match"):
    _sh._TOOL_CACHE.clear()
    _sh._TOOL_CACHE["alliance_orthologs"] = (
        _fake_l0("alliance_orthologs", alliance_status, [_ALLIANCE_EL] if alliance_status == "success" else [],
                 list_key="orthologs", bump_clock_s=alliance_bump, cache_hit=True), "injected", None)
    _sh._TOOL_CACHE["zfin_expression"] = (_fake_l0("zfin_expression", expr_status, [], list_key="rows"), "injected", None)
    for fam in _L0_FAMILIES:
        _sh._TOOL_CACHE.setdefault(fam, (_fake_l0(fam, "no-match"), "injected", None))


def _fake_zfin_empty(symbol, anatomy=None, limit=50, **kw):
    return {"status": "success", "data": {"symbol": symbol, "zfin_curie": f"ZFIN:ZDB-GENE-{symbol.upper()}",
                                          "taxon": "NCBITaxon:7955", "n_phenotypes_total": 143, "n_matched": 0,
                                          "anatomy_filter": anatomy, "phenotypes": []}}


def _fake_pubmed_empty(query, limit=None, retmax=None):
    out = _fake_pubmed(query, limit, retmax)
    out["data"]["records"] = []
    out["data"]["n_found_total"] = 0
    return out


def _sources_found():
    """EPMC 6 recs (2 duplicadas por PubMed) + PubMed 3 + ZFIN wt1a 30 fenotipos + Alliance 1 ortólogo."""
    answer_pipeline.fetch_paper.search_europepmc_ledger = _fake_epmc_ledger
    answer_pipeline.fetch_paper.fetch_external = _fake_fetch_content
    answer_pipeline._WS_CACHE[("pubmed_literature.py", "query_pubmed")] = _fake_pubmed_pool
    answer_pipeline._WS_CACHE[("zfin_zebrafish.py", "query_zfin")] = _fake_zfin
    _inject_l0("success")


def _sources_empty():
    """Todas las fuentes MIDEN 0 (no-match): la ronda no trae nada nuevo."""
    answer_pipeline.fetch_paper.search_europepmc_ledger = (
        lambda query, n=5, sort=None, synonym=True: ([], {"source": "europepmc", "status": "no-match", "query_sent": query,
                                                          "n_found": 0, "n_returned": 0, "elapsed_s": 0.01}))
    answer_pipeline.fetch_paper.fetch_external = _fake_fetch_content
    answer_pipeline._WS_CACHE[("pubmed_literature.py", "query_pubmed")] = _fake_pubmed_empty
    answer_pipeline._WS_CACHE[("zfin_zebrafish.py", "query_zfin")] = _fake_zfin_empty
    _inject_l0("no-match")


def _run80(question, entities=(), synth=None, panel=None, plan=False, env=None, worker="run-worker-adr0080"):
    """Una corrida por la PUERTA (app.create_run [+ app.create_plan con el planner stub]) ejecutada con el
    sintetizador/panel inyectados bajo `env` (vars fijadas SOLO durante la corrida). Devuelve (run_id, frozen, events).
    ADR-0082: con plan=True el flujo corre bajo WITT_COUNCIL=0 salvo que `env` lo fije — el camino de 9d90c01 (L.2): con
    el consejo encendido y origen smoke, app (C6) emite un literal de 56 chars que db.create_plan (C4) rechaza, o encola un
    JOB r1 que nadie corre aquí (409 en POST /runs). El consejo ENCENDIDO se mide en la sección ADR-0082 (C5) con la copia
    F.4 directa (runs.new_run(council_json=))."""
    env = dict(env or {})
    if plan:
        env.setdefault("WITT_COUNCIL", "0")
    saved = {k: os.environ.get(k) for k in (env or {})}
    for k, v in (env or {}).items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        body = {"question": question, "entities": list(entities)}
        if plan:
            planner_real = runs_mod._default_planner
            runs_mod._default_planner = _fake_planner_ok
            try:
                prv = app.create_plan(app.PlanBody(question=question, entities=list(entities)), authorization=AUTH)
            finally:
                runs_mod._default_planner = planner_real
            body["plan_id"] = prv["plan_id"]
        rv = app.create_run(app.RunBody(**body), authorization=AUTH)
        claimed = db.claim_next_queued(worker_id=worker)
        assert claimed and claimed["run_id"] == rv["run_id"], "FIFO: la corrida reclamada debe ser la esperada"
        runs_mod.execute_run(claimed, synthesizer=synth or _mk_synth({"pass1": 0.8, "pass2": 0.85}),
                             panel_caller=panel or _stub_caller_factory(ALL_A))
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    rid = rv["run_id"]
    return rid, app.get_frozen_record(rid, authorization=AUTH), app.get_events(rid, after=0, authorization=AUTH)["events"]


def _ev_types(ev):
    return [e["type"] for e in ev]


def _ev_payloads(ev, t):
    return [e["payload"] for e in ev if e["type"] == t]


answer_pipeline.path_b = _path_b_real   # la Ruta B REAL: path_b_bundle(search_plan=) -> _path_b_harness -> harness
_sources_found()

# --- (A/B) COMPETENTE con plan: pass1 es la candidata, SIN ronda, trigger null ------------------------------
_rid_c, _rec_c, _ev_c = _run80("ADR-0080 competente: does wt1a mark the pronephros?", ["wt1a"], plan=True)
_t_c = _ev_types(_ev_c)
_gate_c = _ev_payloads(_ev_c, "stage.deterministic_gate")
check("ADR-0080 (A/B) COMPETENTE (plan evidence-run + nichos, conf 0.8 >= tau, pass1 admisible, sin estructural): "
      "competent True, reasons [], fallback.trigger null y trigger_legacy null, NINGUNA ronda (sin stage.search.* ni "
      "stage.path_b ni pass2), search_ledger.state 'not-requested…' con rounds [] y n_rounds 0 (CERO medido: la compuerta "
      "decidió no buscar — corrector ADR-0080/ADR-0043; null se reserva a 'el harness no midió'), epistemic_summary "
      "{competent True, n_search_rounds 0}; orden de la traza: synthesize.pass1 < confidence.elicit{pass1} < "
      "deterministic_gate{pass:1} (ADELANTADO) < competence < audit.start",
      _rec_c["competence"]["competent"] is True and _rec_c["competence"]["reasons"] == []
      and _rec_c["competence"]["not_applicable"] is False
      and _rec_c["fallback"]["trigger"] is None and _rec_c["fallback"]["fb_meta"]["trigger_legacy"] is None
      and _rec_c["confidence"]["pass2"] is None and "stage.synthesize.pass2" not in _t_c
      and not any(t.startswith("stage.search.") for t in _t_c) and "stage.path_b" not in _t_c
      and _rec_c["search_ledger"]["state"].startswith("not-requested") and _rec_c["search_ledger"]["rounds"] == []
      and _rec_c["search_ledger"]["n_rounds"] == 0 and _rec_c["search_ledger"]["plan_state"] == "not-requested"
      and app.get_run(_rid_c, authorization=AUTH)["epistemic_summary"]["competent"] is True
      and app.get_run(_rid_c, authorization=AUTH)["epistemic_summary"]["n_search_rounds"] == 0
      and _t_c.index("stage.synthesize.pass1") < _t_c.index("stage.confidence.elicit") < _t_c.index("stage.deterministic_gate")
      < _t_c.index("stage.competence") < _t_c.index("stage.audit.start")
      and len(_gate_c) == 1 and _gate_c[0]["pass"] == "pass1" and _gate_c[0]["admissible"] is True
      and _rec_c["deterministic_checks"]["pass1_admissible"] is True
      and _rec_c["deterministic_checks"]["competence_gate"]["competent"] is True,
      f"reasons={_rec_c['competence']['reasons']} ledger_state={_rec_c['search_ledger']['state']}")
_comp_ev = _ev_payloads(_ev_c, "stage.competence")
check("ADR-0080 (A) el BLOQUE de la compuerta: stage.competence == frozen.competence (íntegro, con decision), decided_by "
      "'code', module_version 'cg-3', self_report {stated_confidence 0.8, class 'model-judgment', nota que dice la VERDAD: "
      "'participa como componente conf1_ge_tau medido por CONF_TOOL (ADR-0065; …); la conjunción la decide código'}, componentes "
      "en orden canónico con value/reason, conjunction CON conf1_ge_tau primero (cg-3: el escalar elicitado gatea por default, "
      "ADR-0051/0065) y SIN calibration_coverage (gating False por default); council_uncovered_must (cg-4, ADR-0082 G.2) bajo "
      "kill-switch WITT_COUNCIL=0 (este flujo legado): state 'kill-switch WITT_COUNCIL=0', value null, gating False, fuera de "
      "conjunction; fb_meta.competence + trigger_vocabulary (runs.TRIGGER_VOCABULARY) + trigger_decided_by 'code (competence-gate)'; "
      "config con tau 0.5 (source 'caller' = runs.FALLBACK_CONF_TAU) y fb_meta.tau_source declarado",
      len(_comp_ev) == 1 and _comp_ev[0] == _rec_c["competence"]
      and _rec_c["competence"]["decided_by"] == "code" and _rec_c["competence"]["module_version"] == "cg-4" == _cg.MODULE_VERSION
      and _rec_c["competence"]["self_report"] == {"stated_confidence": 0.8, "class": "model-judgment",
                                                 "note": "participa como componente conf1_ge_tau medido por CONF_TOOL (ADR-0065; "
                                                         "gating true, WITT_CG_CONF_COMPONENT default 1, cg-3); la conjunción la "
                                                         "decide código"}
      and list(_rec_c["competence"]["components"]) == list(_cg.COMPONENT_ORDER)
      and _rec_c["competence"]["conjunction"] == ["conf1_ge_tau", "admissible", "route_evidence_run", "niches_nonempty",
                                                  "structural_not_fired"]
      and _rec_c["competence"]["components"]["conf1_ge_tau"]["gating"] is True
      and _rec_c["competence"]["components"]["conf1_ge_tau"]["value"] is True
      and _rec_c["competence"]["config"]["conf_component_gating"] is True
      and _rec_c["fallback"]["fb_meta"]["trigger_decided_by"] == "code (competence-gate)"
      and _rec_c["fallback"]["fb_meta"]["tau_source"] == runs_mod.FALLBACK_CONF_TAU_SOURCE
      and _rec_c["competence"]["components"]["calibration_coverage"]["gating"] is False
      and _rec_c["competence"]["components"]["council_uncovered_must"]["state"] == "kill-switch WITT_COUNCIL=0"
      and _rec_c["competence"]["components"]["council_uncovered_must"]["value"] is None
      and _rec_c["competence"]["components"]["council_uncovered_must"]["gating"] is False
      and "council_uncovered_must" not in _rec_c["competence"]["conjunction"]
      and _rec_c["competence"]["config"]["council_component_gating"] is True
      and _rec_c["competence"]["config"]["council_enabled"] is False
      and _rec_c["competence"]["components"]["niches_nonempty"]["niches"] == ["N3", "N4"]
      and _rec_c["competence"]["config"]["tau"] == 0.5 and _rec_c["competence"]["config"]["tau_source"] == "caller"
      and _rec_c["competence"]["decision"]["decision_source"].startswith("competence-gate: competent")
      and _rec_c["fallback"]["fb_meta"]["trigger_vocabulary"] == runs_mod.TRIGGER_VOCABULARY
      and "confidence(only when competence.competent is null)" in runs_mod.TRIGGER_VOCABULARY
      and _rec_c["fallback"]["fb_meta"]["competence"]["competent"] is True
      and _rec_c["fallback"]["fb_meta"]["competence"]["decided_by"] == "code",
      json.dumps({k: v.get("value") for k, v in _rec_c["competence"]["components"].items()}))
_bs_c = _rec_c["token_usage"]["by_stage"]
check("ADR-0080 (F) by_stage del competente: plan 400 (el planner gastó), synthesize_pass1 100, elicit_pass1 'not-separable…' "
      "(stub sin usage_elicitation: in/out null, jamás un 0 inventado), search 0 con nota Layer 0, synthesize_pass2 0, panel 40, "
      "revision 0, embed aparte; _sum == by_model total y by_stage_sum_matches_by_model True",
      _bs_c["plan"]["in"] == 400 and _bs_c["synthesize_pass1"]["in"] == 100 and _bs_c["synthesize_pass1"]["out"] == 50
      and _bs_c["elicit_pass1"]["in"] is None and _bs_c["elicit_pass1"]["state"].startswith("not-separable")
      and _bs_c["search"]["in"] == 0 and "Layer 0" in _bs_c["search"]["note"]
      and _bs_c["synthesize_pass2"]["in"] == 0 and _bs_c["elicit_pass2"]["state"] == "not-run"
      and _bs_c["panel"]["in"] == 40 and _bs_c["revision"]["in"] == 0 and "tokens" in _bs_c["embed"]
      and _bs_c["_sum"]["in"] == _rec_c["token_usage"]["input_tokens"] == 540
      and _bs_c["_sum"]["out"] == _rec_c["token_usage"]["output_tokens"]
      and _rec_c["token_usage"]["by_stage_sum_matches_by_model"] is True,
      json.dumps({k: (v.get("in"), v.get("state")) for k, v in _bs_c.items() if k != "embed"}))

# --- (B/C) NO competente (sin plan) -> plan de búsqueda REAL + UNA ronda por el harness REAL -> pass2 ------------
_TOOL_CALLS.clear()
_rid_h, _rec_h, _ev_h = _run80("ADR-0080 harness: is wt1a required for pronephros glomerulus formation?", ["wt1a"],
                               synth=_mk_synth({"pass1": 0.8, "pass2": 0.85},
                                               extra={"search_query_en": "wt1a zebrafish pronephros glomerulus"}))
_t_h = _ev_types(_ev_h)
_sl_h = _rec_h["search_ledger"]
_plan_ev = _ev_payloads(_ev_h, "stage.search.plan")
_src_ev = _ev_payloads(_ev_h, "stage.search.source")
_rnd_ev = _ev_payloads(_ev_h, "stage.search.round")
_pb_ev = _ev_payloads(_ev_h, "stage.path_b")
_row_h = {s["family"]: s for s in _sl_h["rounds"][0]["sources"]} if _sl_h.get("rounds") else {}
check("ADR-0080 (B/C) NO COMPETENTE (sin plan, 'no-plan') -> stage.search.plan UNA vez (plan_version '1', familias DEFAULT "
      "europepmc,pubmed,zfin,alliance_orthologs,zfin_expression, families_source 'default-families', n_directives 0, "
      "question_en_source 'pass1_query_en' — la formulación EN de pass1 alimenta al plan; el constructor del bloque la "
      "declara 'synthesizer'), 5 stage.search.source, "
      "1 stage.search.round; frozen.search_ledger.state 'harness', n_rounds 1 <= cap 2, stop_reason 'found-new', "
      "config_source declarada; stage.path_b trigger 'competence' + harness_used True + trigger_legacy null; pass2 corre; "
      "epistemic_summary.n_search_rounds 1",
      _rec_h["competence"]["competent"] is False and _rec_h["fallback"]["trigger"] == "competence"
      and _rec_h["fallback"]["fb_meta"]["trigger_legacy"] is None
      and len(_plan_ev) == 1 and _plan_ev[0]["plan_version"] == "1"
      and _plan_ev[0]["families"] == ["europepmc", "pubmed", "zfin", "alliance_orthologs", "zfin_expression"]
      and _plan_ev[0]["families_source"] == "default-families" and _plan_ev[0]["n_directives"] == 0
      and _plan_ev[0]["question_en_source"] == "pass1_query_en"
      and _rec_h["search_ledger"]["plan"]["question_en"] == "wt1a zebrafish pronephros glomerulus"
      and json.loads(db.get_run(_rid_h)["bundle_json"])["path_b"]["query_builder"]["inputs"]["question_en_source"] == "synthesizer"
      and len(_src_ev) == 5 and len(_rnd_ev) == 1 and _rnd_ev[0]["round"] == 1 and _rnd_ev[0]["trigger"] == "initial"
      and _sl_h["state"] == "harness" and _sl_h["n_rounds"] == 1 and _sl_h["cap"] == 2 and _sl_h["n_rounds"] <= _sl_h["cap"]
      and _sl_h["stop_reason"] == "found-new" and _sl_h["harness_version"] == "sh-1"
      and _sl_h["families_default"] == ["europepmc", "pubmed", "zfin", "alliance_orthologs", "zfin_expression"]
      and _sl_h["config_source"] == {"families": "default-unset:WITT_SEARCH_DEFAULT_FAMILIES",
                                     "cap": "default-unset:WITT_SEARCH_ROUNDS_CAP",
                                     "round_budget_s": "default-unset:WITT_SEARCH_ROUND_BUDGET_S"}
      and len(_pb_ev) == 1 and _pb_ev[0]["trigger"] == "competence" and _pb_ev[0]["harness_used"] is True
      and _pb_ev[0]["trigger_legacy"] is None and _pb_ev[0]["search_ledger"]["n_rounds"] == 1
      and "stage.synthesize.pass2" in _t_h and _rec_h["confidence"]["pass2"] == 0.85
      and app.get_run(_rid_h, authorization=AUTH)["epistemic_summary"]["n_search_rounds"] == 1
      and app.get_run(_rid_h, authorization=AUTH)["epistemic_summary"]["competent"] is False,
      json.dumps({"ledger_state": _sl_h.get("state"), "n_rounds": _sl_h.get("n_rounds"), "stop": _sl_h.get("stop_reason"),
                  "plan_ev": len(_plan_ev), "src_ev": len(_src_ev), "rnd_ev": len(_rnd_ev),
                  "plan": {k: _plan_ev[0].get(k) for k in ("plan_version", "families", "families_source", "n_directives",
                                                          "question_en_source")} if _plan_ev else None,
                  "pb": {k: _pb_ev[0].get(k) for k in ("trigger", "harness_used", "trigger_legacy")} if _pb_ev else None,
                  "config_source": _sl_h.get("config_source"), "trigger": _rec_h["fallback"]["trigger"],
                  "legacy": _rec_h["fallback"]["fb_meta"]["trigger_legacy"], "pass2": _rec_h["confidence"]["pass2"],
                  "es": {k: app.get_run(_rid_h, authorization=AUTH)["epistemic_summary"].get(k)
                         for k in ("competent", "n_search_rounds")}}))
_papers_h = json.loads(db.get_run(_rid_h)["bundle_json"])["path_b"]["papers"]
_kinds_h = {p.get("evidence_id"): p.get("kind") for p in _papers_h}
check("ADR-0080 (C/D) la RONDA por fuente: europepmc success (6 -> pool), pubmed success con duplicates_of_europepmc "
      "DECLARADOS (PMID:11111111/22222222 ya vinieron por EPMC), zfin success (fenotipos nativos), alliance_orthologs success "
      "1 ítem kind 'ortholog' con evidence_id/identifier_provenance DEL TOOL ('alliance-api-payload', cache_hit True), "
      "zfin_expression no-match (n_found 0 ENTERO: midió); cada fake recibió `timeout` (el presupuesto viaja al tool); "
      "los ítems Layer 0 entran a path_b.papers junto a la literatura seleccionada; n_new/n_found enteros SOLO en success|no-match",
      set(_row_h) == {"europepmc", "pubmed", "zfin", "alliance_orthologs", "zfin_expression"}
      and _row_h["europepmc"]["status"] == "success" and _row_h["europepmc"]["n_found"] == 6
      and _row_h["pubmed"]["status"] == "success"
      and set(_row_h["pubmed"]["ledger"].get("duplicates_of_europepmc") or []) >= {"PMID:11111111", "PMID:22222222"}
      and _row_h["zfin"]["status"] == "success" and _row_h["zfin"]["n_found"] == 1
      and _row_h["alliance_orthologs"]["status"] == "success" and _row_h["alliance_orthologs"]["n_found"] == 1
      and _row_h["alliance_orthologs"]["n_new"] == 1 and _row_h["alliance_orthologs"]["cache_hit"] is True
      and _row_h["alliance_orthologs"]["fn_resolved"] == "injected"
      and _row_h["zfin_expression"]["status"] == "no-match" and _row_h["zfin_expression"]["n_found"] == 0
      and _kinds_h.get("alliance-ortholog:ZFIN:ZDB-GENE-980526-558->HGNC:12796") == "ortholog"
      and next(p for p in _papers_h if p.get("kind") == "ortholog")["identifier_provenance"] == "alliance-api-payload"
      and next(p for p in _papers_h if p.get("kind") == "ortholog")["label"] is None
      and any(p.get("kind") == "phenotype" for p in _papers_h)
      and any(p.get("evidence_id") == "PMID:11111111" for p in _papers_h)
      and all(isinstance(c["timeout"], (int, float)) and c["timeout"] > 0 for c in _TOOL_CALLS)
      and {c["family"] for c in _TOOL_CALLS} == {"alliance_orthologs", "zfin_expression"}
      and all((s["n_found"] is None) == (s["status"] not in ("success", "no-match")) for s in _row_h.values()),
      json.dumps({f: (s["status"], s["n_found"], s["n_new"]) for f, s in _row_h.items()}))
# --- corrector ADR-0080 (paridad webapp 2026-09-15): papers[] del EVENTO stage.path_b lleva las llaves del harness ---
_pb_papers_h = _pb_ev[0]["papers"]
_pb_orth = next((p for p in _pb_papers_h if p.get("kind") == "ortholog"), None)
_pb_lit = next((p for p in _pb_papers_h if p.get("evidence_id") == "PMID:11111111"), None)
check("ADR-0080 (G/Consequences 9, corrector paridad webapp) el resumen papers[] del EVENTO stage.path_b (lo único del ítem que la "
      "webapp puede pintar: el bloque vive en bundle_json, no en el frozen) lleva las llaves del harness SOLO cuando el ítem las "
      "trae: el ítem de ortología llega con kind 'ortholog', source_family 'alliance_orthologs', label PRESENTE y null (ni "
      "predictivo ni inferido), identifier_provenance 'alliance-api-payload', url del tool, zfin_curie presente, round 1, sin "
      "gap_flags (tiene id externo: ausente sigue ausente) y SIN texto; el paper de literatura seleccionado lleva kind "
      "'literature-candidate', source_family 'europepmc', identifier_provenance 'europepmc-api-live', round 1; un paper LEGADO "
      "(bloque ADR-0078 sin harness, pl_b) NO gana ninguna de esas llaves",
      _pb_orth is not None and _pb_orth["source_family"] == "alliance_orthologs" and "label" in _pb_orth and _pb_orth["label"] is None
      and _pb_orth["identifier_provenance"] == "alliance-api-payload"
      and _pb_orth["url"] == "https://www.alliancegenome.org/gene/HGNC:12796"
      and "zfin_curie" in _pb_orth and _pb_orth["round"] == 1 and _pb_orth["source"] == "alliance_orthologs"
      and "gap_flags" not in _pb_orth
      and not any(k in _pb_orth for k in ("statement", "text", "abstract", "text_excerpt", "title"))
      and _pb_lit is not None and _pb_lit["kind"] == "literature-candidate" and _pb_lit["source_family"] == "europepmc"
      and _pb_lit["identifier_provenance"] == "europepmc-api-live" and _pb_lit["round"] == 1
      and _pb_lit["url"] == "https://europepmc.org/abstract/MED/11111111"
      and all(k not in p for p in pl_b["papers"] for k in ("kind", "source_family", "label", "identifier_provenance", "round")),
      json.dumps({"orth": _pb_orth, "lit": {k: _pb_lit.get(k) for k in ("kind", "source_family", "round", "url")} if _pb_lit else None}))
_bs_h = _rec_h["token_usage"]["by_stage"]
check("ADR-0080 (F) by_stage del NO competente: plan {0, 'no-plan'}, synthesize_pass1 100, synthesize_pass2 100, search 0 "
      "(Layer 0 no gasta modelo), panel 40; _sum 240 == by_model total (stub-synth 200 + jueces 40) == token_usage.input_tokens; "
      "y en la corrida con REVISIÓN (ADR-0067) revision 100 + panel 80 y la suma también cuadra",
      _bs_h["plan"] == {"in": 0, "out": 0, "state": "no-plan"} and _bs_h["synthesize_pass1"]["in"] == 100
      and _bs_h["synthesize_pass2"]["in"] == 100 and _bs_h["search"]["in"] == 0 and _bs_h["panel"]["in"] == 40
      and _bs_h["_sum"]["in"] == 240 == _rec_h["token_usage"]["input_tokens"]
      and _rec_h["token_usage"]["by_stage_sum_matches_by_model"] is True
      and rec_r["token_usage"]["by_stage"]["revision"]["in"] == 100 and rec_r["token_usage"]["by_stage"]["panel"]["in"] == 80
      and rec_r["token_usage"]["by_stage"]["_sum"]["in"] == rec_r["token_usage"]["input_tokens"]
      and rec_r["token_usage"]["by_stage_sum_matches_by_model"] is True,
      json.dumps({k: v.get("in") for k, v in _bs_h.items() if k != "embed"}))
_bs_real = rec_real["token_usage"]["by_stage"]
_el_real = [p for p in _ev_payloads(app.get_events(rv_real["run_id"], after=0, authorization=AUTH)["events"],
                                    "stage.confidence.elicit")]
check("ADR-0080 (B/F) CAMINO REAL (_default_synthesizer con la API falsa): la elicitación dedicada (ADR-0065) gana su evento "
      "stage.confidence.elicit{pass 1|2} con usage {in 30, out 3, model} y elicitation_state 'elicited'; by_stage SEPARA "
      "elicit_pass1 {30, 3, 'measured'} de synthesize_pass1 {100, 50} (la parte se resta de la suma fusionada, M8 sigue "
      "cuadrando: _sum == by_model total)",
      len(_el_real) == 2 and [p["pass"] for p in _el_real] == ["pass1", "pass2"]
      and _el_real[0]["usage"]["in"] == 30 and _el_real[0]["usage"]["out"] == 3 and _el_real[0]["usage"].get("model")
      and _el_real[0]["elicitation_state"] == "elicited" and _el_real[0]["confidence_source"] == "stated-second-elicitation"
      and _bs_real["elicit_pass1"]["in"] == 30 and _bs_real["elicit_pass1"]["out"] == 3
      and _bs_real["elicit_pass1"]["state"] == "measured"
      and _bs_real["synthesize_pass1"]["in"] == 100 and _bs_real["synthesize_pass1"]["out"] == 50
      and _bs_real["_sum"]["in"] == rec_real["token_usage"]["input_tokens"]
      and rec_real["token_usage"]["by_stage_sum_matches_by_model"] is True,
      json.dumps({"elicit": [(p["pass"], p["usage"]) for p in _el_real],
                  "by_stage": {k: v.get("in") for k, v in _bs_real.items() if k != "embed"}}))
_gate_h = _ev_payloads(_ev_h, "stage.deterministic_gate")
_syn1_h = _ev_payloads(_ev_h, "stage.synthesize.pass1")
check("ADR-0080 (G) eventos nuevos y ampliados en la traza del NO competente: stage.deterministic_gate x2 con `pass` 1 y 2 "
      "(el de pass1 ANTES de stage.competence), stage.synthesize.pass1 lleva usage {in, out, model}, stage.confidence.elicit "
      "x2 (pass 'pass1' y 'pass2' — ETIQUETAS, el vocabulario de usage_raw.passes; corrector ADR-0080: la llave ya no mezcla "
      "int y str) con elicitation_state 'not-reported-by-synthesizer' (stub) y usage null declarado; deterministic_checks "
      "congelado lleva pass 'pass2', pass1_admissible True, competence_gate compacto con reasons ['route_evidence_run','niches_nonempty']",
      [g["pass"] for g in _gate_h] == ["pass1", "pass2"]
      and _t_h.index("stage.deterministic_gate") < _t_h.index("stage.competence") < _t_h.index("stage.search.plan")
      and _syn1_h[0]["usage"] == {"in": 100, "out": 50, "model": "stub-synth"}
      and [p["pass"] for p in _ev_payloads(_ev_h, "stage.confidence.elicit")] == ["pass1", "pass2"]
      and all(p["elicitation_state"] == "not-reported-by-synthesizer" and p["usage"] is None
              for p in _ev_payloads(_ev_h, "stage.confidence.elicit"))
      and _rec_h["deterministic_checks"]["pass"] == "pass2" and _rec_h["deterministic_checks"]["pass1_admissible"] is True
      and _rec_h["deterministic_checks"]["competence_gate"]["competent"] is False
      and _rec_h["deterministic_checks"]["competence_gate"]["reasons"] == ["route_evidence_run", "niches_nonempty"]
      and _rec_h["deterministic_checks"]["competence_gate"]["decided_by"] == "code",
      json.dumps({"gate_passes": [g["pass"] for g in _gate_h], "syn1_usage": _syn1_h[0].get("usage")}))

# --- (C) rondas <= cap: nada nuevo en la ronda 1 -> ronda 2 -> 'rounds-cap'; cap por env respetado -------------
_sources_empty()
_rid_2, _rec_2, _ev_2 = _run80("ADR-0080 dos rondas: does wt1a mark the pronephros?", ["wt1a"])
_sl_2 = _rec_2["search_ledger"]
_rid_1, _rec_1, _ev_1 = _run80("ADR-0080 cap 1: does wt1a mark the pronephros?", ["wt1a"],
                               env={"WITT_SEARCH_ROUNDS_CAP": "1"})
_sl_1 = _rec_1["search_ledger"]
check("ADR-0080 (C, corrector) NADA SE RE-EJECUTA: n_admitted == 0 en la ronda 1 y NINGÚN insumo de familia cambió "
      "(inputs_signature idéntica antes/después) -> NO hay ronda 2 aunque k < cap: stop_reason 'no-new-inputs' (literal "
      "declarado en SEARCH_STOP_REASONS), n_rounds 1 < cap 2, 1 evento stage.search.round, 5 stage.search.source (no 10: "
      "cero GETs repetidos), todas las fuentes no-match con n_found 0 ENTERO, rounds[0].inputs_changed False y n_admitted 0; "
      "pass2 corre igual (la ronda vacía se declara, no se esconde); epistemic_summary.n_search_rounds 1; second_round_rule "
      "congelada nombra el predicado completo",
      _sl_2["n_rounds"] == 1 and _sl_2["cap"] == 2 and _sl_2["stop_reason"] == "no-new-inputs" and _sl_2["n_new_total"] == 0
      and "no-new-inputs" in answer_pipeline.SEARCH_STOP_REASONS and _sl_2["stop_reasons_vocabulary"] == list(answer_pipeline.SEARCH_STOP_REASONS)
      and [r["trigger"] for r in _sl_2["rounds"]] == ["initial"]
      and _sl_2["rounds"][0]["inputs_changed"] is False and _sl_2["rounds"][0]["n_admitted"] == 0 and _sl_2["n_admitted_total"] == 0
      and len(_ev_payloads(_ev_2, "stage.search.round")) == 1 and len(_ev_payloads(_ev_2, "stage.search.source")) == 5
      and _ev_payloads(_ev_2, "stage.search.round")[0]["n_admitted"] == 0
      and all(s["status"] == "no-match" and s["n_found"] == 0 for r in _sl_2["rounds"] for s in r["sources"])
      and "stage.synthesize.pass2" in _ev_types(_ev_2)
      and app.get_run(_rid_2, authorization=AUTH)["epistemic_summary"]["n_search_rounds"] == 1
      and _sl_2["second_round_rule"].startswith("only if n_admitted == 0 in round k AND k < cap AND the inputs"),
      json.dumps({"n_rounds": _sl_2["n_rounds"], "stop": _sl_2["stop_reason"],
                  "statuses": [[s["status"] for s in r["sources"]] for r in _sl_2["rounds"]]}))
_sh_pred = (_sh.should_run_next_round(1, 0, 2, True) is True and _sh.should_run_next_round(1, 0, 2, False) is False
            and _sh.should_run_next_round(1, 0, 2) is True and _sh.should_run_next_round(2, 0, 2, True) is False)
check("ADR-0080 (C, corrector) should_run_next_round(k, n_new, cap, inputs_changed): (1,0,2,True) True · (1,0,2,False) False · "
      "firma vieja (1,0,2) True (compat) · (2,0,2,True) False (cap); inputs_signature es determinista y por familia",
      _sh_pred and set(_sh.inputs_signature(_sl_2["plan"], {"dois": [], "curies": []})) == set(_sl_2["plan"]["families"]),
      json.dumps(_sh.inputs_signature(_sl_2["plan"], {"dois": ["10.1/x"], "curies": []}), default=str)[:200])
check("ADR-0080 (C) WITT_SEARCH_ROUNDS_CAP=1 (leída en tiempo de corrida): una sola ronda aunque no haya nada nuevo, "
      "stop_reason 'rounds-cap' (k >= cap manda sobre 'no-new-inputs'), search_ledger.cap 1 con config_source.cap "
      "'env:WITT_SEARCH_ROUNDS_CAP' y el plan declara rounds_cap_source 'env:…'",
      _sl_1["n_rounds"] == 1 and _sl_1["cap"] == 1 and _sl_1["stop_reason"] == "rounds-cap"
      and _sl_1["config_source"]["cap"] == "env:WITT_SEARCH_ROUNDS_CAP"
      and _sl_1["plan"]["rounds_cap"] == 1 and _sl_1["plan"]["rounds_cap_source"] == "env:WITT_SEARCH_ROUNDS_CAP"
      and len(_ev_payloads(_ev_1, "stage.search.round")) == 1,
      json.dumps({"n_rounds": _sl_1["n_rounds"], "cap": _sl_1["cap"], "cap_src": _sl_1["config_source"]["cap"]}))

# --- (C, corrector paridad webapp 2026-09-15) SIN entidades y SIN pass1.search_query_en: nada que buscar, declarado ----
# Hallazgo medido en los fixtures objetada-confianza-ausente / citas-no-parseables de la webapp: query None -> el ledger legado
# decía 'not-searched', el harness lo degradaba a 'error' ("query builder produced no … query") con inputs_used [None] != []
# -> ronda 2 IDÉNTICA (skipped-cap 'same inputs as round 1') -> stop 'rounds-cap', n_rounds 2, contra "nada se re-ejecuta".
_sources_found()
_NS_CALLS = []
_ns_epmc, _ns_pm, _ns_zf = (answer_pipeline.fetch_paper.search_europepmc_ledger,
                            answer_pipeline._WS_CACHE[("pubmed_literature.py", "query_pubmed")],
                            answer_pipeline._WS_CACHE[("zfin_zebrafish.py", "query_zfin")])
answer_pipeline.fetch_paper.search_europepmc_ledger = lambda *a, **kw: (_NS_CALLS.append("europepmc"), _ns_epmc(*a, **kw))[1]
answer_pipeline._WS_CACHE[("pubmed_literature.py", "query_pubmed")] = lambda *a, **kw: (_NS_CALLS.append("pubmed"), _ns_pm(*a, **kw))[1]
answer_pipeline._WS_CACHE[("zfin_zebrafish.py", "query_zfin")] = lambda *a, **kw: (_NS_CALLS.append("zfin"), _ns_zf(*a, **kw))[1]
_TOOL_CALLS.clear()
_rid_ns, _rec_ns, _ev_ns = _run80("ADR-0080 sin entidades ni EN: que marca el pronefros?", [])
_sources_found()   # restaura las fakes de siempre (sin los espías)
_sl_ns = _rec_ns["search_ledger"]
_rows_ns = {s["family"]: s for s in _sl_ns["rounds"][0]["sources"]} if _sl_ns.get("rounds") else {}
check("ADR-0080 (C, corrector paridad webapp) corrida SIN entidades y SIN search_query_en: el constructor no produce query "
      "(stage.path_b.query_sent None) -> las cinco familias dejan 'not-requested' (europepmc/pubmed con el detail '… (nothing to "
      "search)' del ledger legado, que conserva SU literal 'not-searched'; zfin/alliance/expresión 'no symbols'), NINGUNA fila "
      "'error', inputs_used [] en todas (== la firma de _inputs_for) -> should_run_next_round False -> n_rounds 1, stop "
      "'no-new-inputs' (antes: [None] != [] -> ronda 2 idéntica -> 'rounds-cap', n_rounds 2), rounds[0].inputs_changed False, un "
      "solo stage.search.round con las 5 filas 'not-requested', CERO llamadas a las tres fuentes legadas y a las fakes Layer 0; "
      "pass2 corre igual; epistemic_summary.n_search_rounds 1",
      _sl_ns["state"] == "harness" and _sl_ns["n_rounds"] == 1 and _sl_ns["cap"] == 2 and _sl_ns["stop_reason"] == "no-new-inputs"
      and set(_rows_ns) == {"europepmc", "pubmed", "zfin", "alliance_orthologs", "zfin_expression"}
      and all(s["status"] == "not-requested" and "error" not in s and s["inputs_used"] == [] for s in _rows_ns.values())
      and "nothing to search" in _rows_ns["europepmc"]["detail"] and "nothing to search" in _rows_ns["pubmed"]["detail"]
      and _rows_ns["europepmc"]["ledger"]["status"] == "not-searched" and _rows_ns["pubmed"]["ledger"]["status"] == "not-searched"
      and _rows_ns["zfin"]["detail"] == "no symbols" and _rows_ns["alliance_orthologs"]["detail"] == "no symbols"
      and _sl_ns["rounds"][0]["inputs_changed"] is False and _sl_ns["rounds"][0]["families_with_new_inputs"] == []
      and _sl_ns["rounds"][0]["n_admitted"] == 0 and _sl_ns["n_new_total"] == 0
      and len(_ev_payloads(_ev_ns, "stage.search.round")) == 1
      and all(s["status"] == "not-requested" for s in _ev_payloads(_ev_ns, "stage.search.round")[0]["sources"])
      and _ev_payloads(_ev_ns, "stage.path_b")[0]["query_sent"] is None
      and _ev_payloads(_ev_ns, "stage.path_b")[0]["europepmc_searched"]["status"] == "not-searched"
      and _NS_CALLS == [] and _TOOL_CALLS == []
      and "stage.synthesize.pass2" in _ev_types(_ev_ns)
      and app.get_run(_rid_ns, authorization=AUTH)["epistemic_summary"]["n_search_rounds"] == 1,
      json.dumps({"n_rounds": _sl_ns.get("n_rounds"), "stop": _sl_ns.get("stop_reason"),
                  "rows": {f: (s["status"], s.get("detail"), s.get("inputs_used"), s.get("error")) for f, s in _rows_ns.items()},
                  "legacy_calls": _NS_CALLS, "l0_calls": len(_TOOL_CALLS)}))

# --- (C) presupuesto de RONDA: una fuente lenta consume el reloj -> la siguiente queda skipped-budget SIN red ------
_sources_empty()
_inject_l0("success", alliance_bump=500.0)
_TOOL_CALLS.clear()
_rid_b, _rec_b, _ev_b = _run80("ADR-0080 presupuesto: does wt1a mark the pronephros?", ["wt1a"],
                               env={"WITT_SEARCH_ROUND_BUDGET_S": "10"})
_sl_b = _rec_b["search_ledger"]
_row_b = {s["family"]: s for s in _sl_b["rounds"][0]["sources"]}
_src_b = {s["family"]: s for s in _ev_payloads(_ev_b, "stage.search.source")}
check("ADR-0080 (C) presupuesto por RONDA (WITT_SEARCH_ROUND_BUDGET_S=10): alliance_orthologs tarda 500 s (reloj simulado) -> "
      "over_budget True declarado en SU fila; zfin_expression queda 'skipped-budget' SIN llamar al tool (n_found/n_new null: "
      "no midió; detail 'round budget 10.0s exhausted…'; budget_s 0.0) y el evento stage.search.source lo dice igual; la ronda "
      "termina (§6 no-hang), search_ledger.round_budget_s 10 con config_source 'env:…' y la corrida llega a awaiting_closure",
      _row_b["alliance_orthologs"]["status"] == "success" and _row_b["alliance_orthologs"]["over_budget"] is True
      and _row_b["zfin_expression"]["status"] == "skipped-budget" and _row_b["zfin_expression"]["n_found"] is None
      and _row_b["zfin_expression"]["n_new"] is None and _row_b["zfin_expression"]["budget_s"] == 0.0
      and _row_b["zfin_expression"]["detail"].startswith("round budget 10.0s exhausted")
      and _src_b["zfin_expression"]["status"] == "skipped-budget" and _src_b["alliance_orthologs"]["over_budget"] is True
      and {c["family"] for c in _TOOL_CALLS} == {"alliance_orthologs"}
      and _sl_b["round_budget_s"] == 10 and _sl_b["config_source"]["round_budget_s"] == "env:WITT_SEARCH_ROUND_BUDGET_S"
      and _sl_b["rounds"][0]["budget_s"] == 10.0 and _sl_b["n_rounds"] == 1 and _sl_b["stop_reason"] == "found-new"
      and db.get_run(_rid_b)["state"] == "awaiting_closure",
      json.dumps({f: (s["status"], s.get("over_budget"), s.get("budget_s")) for f, s in _row_b.items()}))
_CLOCK["t"] = 0.0
_sources_found()

# --- kill-switch WITT_COMPETENCE_GATE=0: competent null + skipped_reason; la regla por confianza de hoy decide ---------
_rid_k, _rec_k, _ev_k = _run80("ADR-0080 kill-switch alto: does wt1a mark the pronephros?", ["wt1a"],
                               env={"WITT_COMPETENCE_GATE": "0"})
_rid_kl, _rec_kl, _ev_kl = _run80("ADR-0080 kill-switch bajo: does wt1a mark the pronephros?", ["wt1a"],
                                  synth=_mk_synth({"pass1": 0.3, "pass2": 0.7}), env={"WITT_COMPETENCE_GATE": "0"})
_pb_kl = _ev_payloads(_ev_kl, "stage.path_b")
_sp_kl = _ev_payloads(_ev_kl, "stage.search.plan")
check("ADR-0080 (A, corrector) kill-switch WITT_COMPETENCE_GATE=0 RESTAURA ADR-0078 byte a byte: competent null + skipped_reason "
      "'kill-switch…' (los componentes se calculan y viajan igual), config.gate_enabled False; decide la regla legada y el "
      "trigger lo dice con SU nombre: conf 0.8 >= tau -> trigger null, sin ronda ni pass2 (search_ledger 'not-requested', "
      "n_rounds 0); conf 0.3 < tau -> trigger 'confidence' (literal válido SÓLO con competent null) + trigger_legacy "
      "'confidence' + trigger_decided_by 'model-confidence (legacy…)' + decision_source 'legacy-confidence (…)' + Ruta B por "
      "path_b_bundle SIN plan: harness_used False, NINGÚN stage.search.round/source, stage.search.plan con state "
      "'kill-switch WITT_COMPETENCE_GATE=0', search_ledger.state 'legacy-path-b (kill-switch WITT_COMPETENCE_GATE=0)' con "
      "n_rounds null (no midió), triggered_by con el literal de ADR-0051; pass2 corre; epistemic_summary.competent null en ambas",
      _rec_k["competence"]["competent"] is None and _rec_k["competence"]["skipped_reason"].startswith("kill-switch")
      and _rec_k["competence"]["config"]["gate_enabled"] is False
      and _rec_k["competence"]["components"]["route_evidence_run"]["value"] is False
      and _rec_k["fallback"]["trigger"] is None and _rec_k["fallback"]["fb_meta"]["trigger_legacy"] is None
      and _rec_k["confidence"]["pass2"] is None and _rec_k["search_ledger"]["state"].startswith("not-requested")
      and _rec_k["search_ledger"]["n_rounds"] == 0
      and _rec_k["fallback"]["fb_meta"]["competence"]["skipped_reason"].startswith("kill-switch")
      and app.get_run(_rid_k, authorization=AUTH)["epistemic_summary"]["competent"] is None
      and _rec_kl["competence"]["competent"] is None and _rec_kl["fallback"]["trigger"] == "confidence"
      and "confidence" in runs_mod.FALLBACK_TRIGGERS
      and _rec_kl["fallback"]["fb_meta"]["trigger_legacy"] == "confidence"
      and _rec_kl["fallback"]["fb_meta"]["trigger_decided_by"].startswith("model-confidence (legacy")
      and _rec_kl["competence"]["decision"]["decision_source"].startswith("legacy-confidence")
      and _rec_kl["competence"]["decision"]["legacy_confidence_fired"] is True
      and _rec_kl["search_ledger"]["state"] == "legacy-path-b (kill-switch WITT_COMPETENCE_GATE=0)"
      and _rec_kl["search_ledger"]["n_rounds"] is None and _rec_kl["search_ledger"]["rounds"] == []
      and len(_pb_kl) == 1 and _pb_kl[0]["harness_used"] is False and _pb_kl[0]["trigger"] == "confidence"
      and "stage.search.round" not in _ev_types(_ev_kl) and "stage.search.source" not in _ev_types(_ev_kl)
      and len(_sp_kl) == 1 and _sp_kl[0]["state"] == "kill-switch WITT_COMPETENCE_GATE=0"
      and _rec_kl["bundle_identity"] and _rec_kl["confidence"]["pass2"] == 0.7
      and app.get_run(_rid_kl, authorization=AUTH)["epistemic_summary"]["n_search_rounds"] is None,
      json.dumps({"alto": (_rec_k["fallback"]["trigger"], _rec_k["competence"]["skipped_reason"]),
                  "bajo": (_rec_kl["fallback"]["trigger"], _rec_kl["fallback"]["fb_meta"]["trigger_legacy"],
                           _rec_kl["search_ledger"]["state"], _rec_kl["fallback"]["fb_meta"]["trigger_decided_by"])}))
_bd_kl = json.loads(db.get_run(_rid_kl)["bundle_json"])
check("ADR-0080 (A, corrector) bajo kill-switch la Ruta B es el bloque LEGADO: bundle.path_b sin search_ledger ni "
      "search_plan_version, sources_requested == answer_pipeline.PATH_B_SOURCES y triggered_by[0] empieza con "
      "'confidence-gate: pass1_confidence=0.3 < tau=0.5' (el literal de ADR-0051)",
      "search_ledger" not in _bd_kl["path_b"] and "search_plan_version" not in _bd_kl["path_b"]
      and _bd_kl["path_b"]["sources_requested"] == list(answer_pipeline.PATH_B_SOURCES)
      and _bd_kl["path_b"]["triggered_by"][0].startswith("confidence-gate: pass1_confidence=0.3 < tau=0.5"),
      json.dumps(_bd_kl["path_b"]["triggered_by"]))
# --- WITT_SEARCH_HARNESS=0: la compuerta decide, el harness no corre (corrector ADR-0080) ---------------------------
_TOOL_CALLS.clear()
_rid_nh, _rec_nh, _ev_nh = _run80("ADR-0080 sin harness: does wt1a mark the pronephros?", ["wt1a"],
                                  env={"WITT_SEARCH_HARNESS": "0"})
check("ADR-0080 (corrector) WITT_SEARCH_HARNESS=0 apaga SÓLO el harness: la compuerta sigue decidiendo (no-plan -> competent "
      "False, trigger 'competence', decided_by code) pero la Ruta B corre por path_b_bundle SIN plan (harness_used False, "
      "cero fakes Layer 0 llamadas, sin stage.search.round/source), stage.search.plan state 'kill-switch WITT_SEARCH_HARNESS=0', "
      "search_ledger.state 'legacy-path-b (kill-switch WITT_SEARCH_HARNESS=0)', fb_meta.search_harness_enabled False con "
      "fuente 'env:WITT_SEARCH_HARNESS'; pass2 corre",
      _rec_nh["competence"]["competent"] is False and _rec_nh["fallback"]["trigger"] == "competence"
      and _ev_payloads(_ev_nh, "stage.path_b")[0]["harness_used"] is False
      and _TOOL_CALLS == [] and "stage.search.round" not in _ev_types(_ev_nh)
      and _ev_payloads(_ev_nh, "stage.search.plan")[0]["state"] == "kill-switch WITT_SEARCH_HARNESS=0"
      and _rec_nh["search_ledger"]["state"] == "legacy-path-b (kill-switch WITT_SEARCH_HARNESS=0)"
      and _rec_nh["fallback"]["fb_meta"]["search_harness_enabled"] is False
      and _rec_nh["fallback"]["fb_meta"]["search_harness_enabled_source"] == "env:WITT_SEARCH_HARNESS"
      and _rec_nh["confidence"]["pass2"] == 0.85,
      json.dumps({"state": _rec_nh["search_ledger"]["state"], "tool_calls": len(_TOOL_CALLS)}))
# --- cg-3 (orquestador 2026-09-15): el escalar ELICITADO gatea POR DEFAULT; WITT_CG_CONF_COMPONENT=0 declarado lo apaga -----
_rid_cc, _rec_cc, _ev_cc = _run80("ADR-0080 conf gatea por default (cg-3): does wt1a mark the pronephros?", ["wt1a"], plan=True,
                                  synth=_mk_synth({"pass1": 0.3, "pass2": 0.7}))
_rid_cd, _rec_cd, _ev_cd = _run80("ADR-0080 conf apagado por env=0: does wt1a mark the pronephros?", ["wt1a"], plan=True,
                                  synth=_mk_synth({"pass1": 0.3, "pass2": 0.7}), env={"WITT_CG_CONF_COMPONENT": "0"})
check("ADR-0080 (A, cg-3) el escalar ELICITADO (CONF_TOOL, ADR-0065) gatea POR DEFAULT como decidió ADR-0051: con plan + pass1 "
      "admisible + conf 0.3 < tau la corrida NO es competente (reasons ['conf1_ge_tau'], gating True, conf1_ge_tau primero en "
      "conjunction, config.conf_component_gating True SIN env), trigger 'competence' + ronda + pass2 0.7 — el caso a361f566 "
      "(0.15 → Ruta B) NO regresa; self_report.note dice 'participa como componente conf1_ge_tau medido por CONF_TOOL…; la "
      "conjunción la decide código' y module_version 'cg-3'",
      _rec_cc["competence"]["competent"] is False and _rec_cc["competence"]["reasons"] == ["conf1_ge_tau"]
      and _rec_cc["competence"]["components"]["conf1_ge_tau"]["value"] is False
      and _rec_cc["competence"]["components"]["conf1_ge_tau"]["gating"] is True
      and _rec_cc["competence"]["conjunction"][0] == "conf1_ge_tau"
      and _rec_cc["competence"]["config"]["conf_component_gating"] is True
      and _rec_cc["competence"]["module_version"] == _cg.MODULE_VERSION == "cg-4"
      and _rec_cc["fallback"]["trigger"] == "competence" and _rec_cc["confidence"]["pass2"] == 0.7
      and _rec_cc["fallback"]["fb_meta"]["trigger_legacy"] == "confidence"
      and _rec_cc["competence"]["self_report"]["note"].startswith("participa como componente conf1_ge_tau medido por CONF_TOOL")
      and _rec_cc["competence"]["self_report"]["note"].endswith("la conjunción la decide código"),
      json.dumps({"default": (_rec_cc["competence"]["competent"], _rec_cc["competence"]["reasons"])}))
check("ADR-0080 (A, cg-3) APAGADO EXPLÍCITO WITT_CG_CONF_COMPONENT=0: la MISMA corrida (conf 0.3) es competente (trigger null), "
      "conf1_ge_tau viaja informativo (value False, gating False, FUERA de conjunction, config.conf_component_gating False), "
      "trigger_legacy 'confidence' declara que la regla vieja habría disparado, y self_report.note dice la verdad: "
      "'no participa en la decisión (conf1_ge_tau informativo, WITT_CG_CONF_COMPONENT=0 declarado)' — la nota coincide con gating",
      _rec_cd["competence"]["competent"] is True and _rec_cd["fallback"]["trigger"] is None
      and _rec_cd["competence"]["components"]["conf1_ge_tau"]["value"] is False
      and _rec_cd["competence"]["components"]["conf1_ge_tau"]["gating"] is False
      and "conf1_ge_tau" not in _rec_cd["competence"]["conjunction"]
      and _rec_cd["competence"]["config"]["conf_component_gating"] is False
      and _rec_cd["fallback"]["fb_meta"]["trigger_legacy"] == "confidence"
      and _rec_cd["competence"]["self_report"]["note"]
      == "no participa en la decisión (conf1_ge_tau informativo, WITT_CG_CONF_COMPONENT=0 declarado)"
      and _rec_cd["confidence"]["pass2"] is None,
      json.dumps({"env0": (_rec_cd["competence"]["competent"], _rec_cd["fallback"]["trigger"])}))

# --- calibration_coverage: medición de la BD; gatea SOLO con WITT_CG_REQUIRE_CALIBRATION=1 -------------------------
_rid_g, _rec_g, _ev_g = _run80("ADR-0080 calibración gatea: does wt1a mark the pronephros?", ["wt1a"], plan=True,
                               env={"WITT_CG_REQUIRE_CALIBRATION": "1"})
_cal_g = _rec_g["competence"]["components"]["calibration_coverage"]
check("ADR-0080 (A) WITT_CG_REQUIRE_CALIBRATION=1: calibration_coverage entra a la conjunción (gating True) y con < 10 corridas "
      "CLOSED calificadas que intersequen N3/N4 la MISMA corrida que era competente deja de serlo — reasons == "
      "['calibration_coverage'], n_closed_rated ENTERO medido (class 'medicion'), min_required 10 (source default-unset), "
      "sufficient False -> trigger 'competence' + ronda; por default (gating False) el componente viaja informativo y no gatea",
      _rec_g["competence"]["competent"] is False and _rec_g["competence"]["reasons"] == ["calibration_coverage"]
      and _cal_g["gating"] is True and isinstance(_cal_g["n_closed_rated"], int) and _cal_g["n_closed_rated"] < 10
      # corrector ADR-0080: la cobertura cuenta SÓLO producción por default (las corridas smoke de este gate NO son historia)
      and _rec_g["competence"]["components"]["calibration_coverage"]["n_closed_rated"] == 0
      and _cal_g["min_required"] == 10 and _cal_g["sufficient"] is False and _cal_g["class"].startswith("medicion")
      and "calibration_coverage" in _rec_g["competence"]["conjunction"]
      and _rec_g["competence"]["config"]["require_calibration"] is True
      and _rec_g["fallback"]["trigger"] == "competence" and _rec_g["search_ledger"]["state"] == "harness"
      and _rec_c["competence"]["components"]["calibration_coverage"]["gating"] is False
      and "calibration_coverage" not in _rec_c["competence"]["conjunction"],
      json.dumps(_cal_g))
_cal_ev_g = _ev_payloads(_ev_g, "stage.competence")[0]["components"]["calibration_coverage"]
_cov_prod = db.calibration_coverage(["N3", "N4"], 10, include_origins=["production"])
_cov_all = db.calibration_coverage(["N3", "N4"], 10, include_origins=None)
# corrector paridad webapp 2026-09-15: con WITT_CG_CALIBRATION_ORIGINS=all el componente declara include_origins 'all' (jamás null)
_rid_ga, _rec_ga, _ev_ga = _run80("ADR-0080 calibración all: does wt1a mark the pronephros?", ["wt1a"], plan=True,
                                  env={"WITT_CG_REQUIRE_CALIBRATION": "1", "WITT_CG_CALIBRATION_ORIGINS": "all"})
_cal_ga = _rec_ga["competence"]["components"]["calibration_coverage"]
check("ADR-0080 (A, corrector) WITT_CG_CALIBRATION_ORIGINS default 'production': db.calibration_coverage se llama con "
      "include_origins ['production'] (fuente 'default-unset:WITT_CG_CALIBRATION_ORIGINS' en el bloque) — las corridas de "
      "origen smoke cerradas de esta BD quedan CONTADAS FUERA (n 0 con filtro, n_closed_rated_total con filtro <= sin filtro); "
      "el lector CSV tolerante acepta 'all' como sin filtro declarado. Corrector paridad webapp: components.calibration_coverage "
      "LLEVA include_origins ['production'] + include_origins_source (aserción DURA en frozen y evento; antes condicional a la "
      "llave, que no existía); con WITT_CG_CALIBRATION_ORIGINS=all -> include_origins 'all' (literal, no null) + source "
      "'env:WITT_CG_CALIBRATION_ORIGINS (all origins, no filter)' y n_closed_rated ENTERO (cuenta también smoke)",
      _cal_g["include_origins"] == ["production"] and _cal_g["include_origins_source"] == "default-unset:WITT_CG_CALIBRATION_ORIGINS"
      and _cal_ev_g["include_origins"] == ["production"] and _cal_ev_g["include_origins_source"] == _cal_g["include_origins_source"]
      and _cal_ga["include_origins"] == "all" and _cal_ga["include_origins_source"] == "env:WITT_CG_CALIBRATION_ORIGINS (all origins, no filter)"
      and isinstance(_cal_ga["n_closed_rated"], int) and _cal_ga["n_closed_rated"] >= _cal_g["n_closed_rated"]
      and _cal_ga["gating"] is True
      and _cov_prod["include_origins"] == ["production"] and _cov_prod["n"] == 0
      and _cov_prod["n_closed_rated_total"] <= _cov_all["n_closed_rated_total"]
      and runs_mod._calibration_origins() == (["production"], "default-unset:WITT_CG_CALIBRATION_ORIGINS")
      and (lambda saved: (os.environ.__setitem__("WITT_CG_CALIBRATION_ORIGINS", "all"),
                          runs_mod._calibration_origins(),
                          os.environ.pop("WITT_CG_CALIBRATION_ORIGINS"))[1])(None)[0] is None
      and (lambda: (os.environ.__setitem__("WITT_CG_CALIBRATION_ORIGINS", "Production, smoke,smoke"),
                    runs_mod._calibration_origins(),
                    os.environ.pop("WITT_CG_CALIBRATION_ORIGINS"))[1])() == (["production", "smoke"], "env:WITT_CG_CALIBRATION_ORIGINS"),
      json.dumps({"prod": _cov_prod, "all_total": _cov_all["n_closed_rated_total"]}, default=str)[:300])

# --- (E/G) la ESCALERA de soporte por cita: nunca se funden los peldaños ---------------------------------------------
def _panel_cs(verdicts, citation_support):
    inner = _stub_caller_factory(verdicts)

    def _caller(member, system, user_text):
        out, usage = inner(member, system, user_text)
        if member["lens"] == "evidence-grounding":
            out["citation_support"] = list(citation_support)
        return out, usage
    return _caller


_rid_s, _rec_s, _ev_s = _run80("ADR-0080 escalera: does wt1a mark the pronephros?", ["wt1a"], plan=True,
                               synth=_mk_synth({"pass1": 0.8}, extra={"evidence_cited": [
                                   {"kind": "di-chunk", "id": "CORPUS-2026-0003#c000"},
                                   {"kind": "paper", "id": "PMID:99999999"}]}),
                               panel=_panel_cs(ALL_A, [{"n": 1, "verdict": "supported"}, {"n": 2, "verdict": "supported"}]))
_c1, _c2 = _rec_s["citations"][0], _rec_s["citations"][1]
_css = _rec_s["citations_support_summary"]
check("ADR-0080 (E/G) support_state por cita, ADITIVO y sin saltar peldaños: la cita [1] al chunk de Ruta A resuelve "
      "(resolved True), tiene pasaje (passage_delivered True) y el juez evidence-grounding la marcó 'supported' -> "
      "support_state 'supported'; la cita [2] PMID:99999999 NO está en el bundle -> 'unresolved' AUNQUE el juez dijera "
      "'supported' (su palabra se conserva en `supported`, no eleva); pertinent 'not-available (council disabled (kill-switch "
      "WITT_COUNCIL=0))' en ambas (ADR-0082 L.2 iv: el literal lleva la razón; el viejo sigue en summary.pertinent.literal); "
      "citations_support_summary {n 2, by_state con los 5 peldaños, state 'checked', grounding_rows 2, ladder_rule}; forma BASE intacta",
      _cits_base(_rec_s["citations"]) == [{"n": 1, "kind": "di-chunk", "id": "CORPUS-2026-0003#c000", "note": ""},
                                          {"n": 2, "kind": "paper", "id": "PMID:99999999", "note": ""}]
      and _c1["resolved"] is True and _c1["passage_delivered"] is True and _c1["supported"] == "supported"
      and _c1["support_state"] == "supported"
      and _c1["pertinent"] == _c2["pertinent"] == "not-available (council disabled (kill-switch WITT_COUNCIL=0))"
      and _css["pertinent"]["literal"] == _vo.PERTINENT_NOT_AVAILABLE == "not-available (ADR-0082)"
      and _css["pertinent"]["n_not_available"] == 2
      and _c2["resolved"] is False and _c2["passage_delivered"] is False and _c2["supported"] == "supported"
      and _c2["support_state"] == "unresolved"
      and _css["n"] == 2 and set(_css["by_state"]) == set(_vo.SUPPORT_LADDER)
      and _css["by_state"]["supported"] == 1 and _css["by_state"]["unresolved"] == 1
      and _css["state"] == "checked" and _css["grounding_rows"] == 2 and _css["ladder_rule"] == _vo.SUPPORT_LADDER_RULE
      and _rec_s["audit"]["panel"][2]["lens"] == "evidence-grounding"
      and _rec_s["audit"]["panel"][2]["citation_support"] == [{"n": 1, "verdict": "supported"}, {"n": 2, "verdict": "supported"}],
      json.dumps({"c1": {k: _c1.get(k) for k in ("resolved", "passage_delivered", "supported", "support_state")},
                  "c2": {k: _c2.get(k) for k in ("resolved", "passage_delivered", "supported", "support_state")},
                  "summary": _css.get("by_state")}))
_no_cs_ids = [c["support_state"] for c in _rec_c["citations"]]
check("ADR-0080 (E/G) sin citation_support del panel (los otros jueces lo IGNORAN, la lente no lo emitió): supported "
      "'not-evaluated' y el peldaño más alto es el DETERMINISTA; una cita a un id ausente del bundle queda 'unresolved' "
      "(el stub cita CORPUS-2026-0001, que no está en la evidencia) — declarado, no rellenado",
      _rec_c["citations"][0]["supported"] == "not-evaluated" and _no_cs_ids == ["unresolved"]
      and _rec_c["citations_support_summary"]["grounding_rows"] == 0
      and _rec_c["citations_support_summary"]["by_state"]["unresolved"] == 1
      and "citation_support" not in _rec_c["audit"]["panel"][2],
      json.dumps(_rec_c["citations_support_summary"]["by_state"]))

# --- (E) positive_claim_requires_citations: afirmación positiva sin citas = inadmisible; la declinación puede no citar ---
_rid_p, _rec_p, _ev_p = _run80("ADR-0080 positiva sin citas: does wt1a mark the pronephros?", ["wt1a"], plan=True,
                               synth=_mk_synth({"pass1": 0.8, "pass2": 0.85}, extra={"evidence_cited": []}))
_rid_d, _rec_d, _ev_d = _run80("ADR-0080 declinación sin citas: does wt1a mark the pronephros?", ["wt1a"], plan=True,
                               synth=_mk_synth({"pass1": 0.8}, extra={"evidence_cited": [],
                                                                    "absence_kind": "no-evidence-retrieved",
                                                                    "direct_answer": "No evidence retrieved on wt1a and the pronephros; cannot answer."}))
_rid_di, _rec_di, _ev_di = _run80("ADR-0080 declinación con ids resueltos: does wt1a mark the pronephros?", ["wt1a"], plan=True,
                                  synth=_mk_synth({"pass1": 0.8, "pass2": 0.85}, extra={"evidence_cited": [],
                                                                                    "absence_kind": "no-evidence-retrieved"}))
_rid_ab, _rec_ab, _ev_ab = _run80("ADR-0080 absence_kind ausente sin citas: does wt1a mark the pronephros?", ["wt1a"], plan=True,
                                  synth=_mk_synth({"pass1": 0.8, "pass2": 0.85}, extra={"evidence_cited": [], "absence_kind": None}))
_pc_p = _rec_p["deterministic_checks"]["positive_claim_requires_citations_evaluation"]
_pc_di = _rec_di["deterministic_checks"]["positive_claim_requires_citations_evaluation"]
_pc_ab = _rec_ab["deterministic_checks"]["positive_claim_requires_citations_evaluation"]
check("ADR-0080 (E, corrector) lectura CONSERVADORA por código: absence_kind AUSENTE se trata como afirmación positiva "
      "(absence_kind_state 'absent -> treated-as-positive…') -> sin citas inadmisible -> no competente por 'admissible'; una "
      "'declinación' (no-evidence-retrieved) cuyo texto nombra un identificador RESUELTO (ENSDARG00000031420, verified por "
      "verify_identifiers del MISMO gate) sin citar también dispara (reason 'declination with resolved identifiers […] and 0 "
      "citations', resolved_identifiers_state 'checked') -> ronda + pass2; el registro conserva la regla completa",
      _pc_ab["positive_claim"] is True and _pc_ab["absence_kind"] is None
      and _pc_ab["absence_kind_state"].startswith("absent -> treated-as-positive")
      and _pc_ab["ok"] is False and _rec_ab["competence"]["reasons"] == ["admissible"] and _rec_ab["fallback"]["trigger"] == "competence"
      and _pc_di["positive_claim"] is False and _pc_di["ok"] is False
      and _pc_di["resolved_identifiers"] == ["ENSDARG00000031420"] and _pc_di["resolved_identifiers_state"] == "checked"
      and _pc_di["reason"].startswith("declination with resolved identifiers")
      and _rec_di["competence"]["reasons"] == ["admissible"] and _rec_di["fallback"]["trigger"] == "competence"
      and "conservative" in _pc_di["rule"],
      json.dumps({"ausente": _pc_ab["reason"], "declinacion_ids": _pc_di["reason"]}))
check("ADR-0080 (E) positive_claim_requires_citations en el gate ADELANTADO: afirmación positiva (absence_kind not-applicable) "
      "con 0 citas válidas -> inadmisible (predicado False, _state 'checked', evaluación congelada con n_citations_valid 0 y "
      "decided_by 'code') -> pass1_admissible False -> la compuerta NO es competente (reasons ['admissible'], aunque conf 0.8 y "
      "plan) -> ronda + pass2 (también sin citas -> el gate final sigue inadmisible); una DECLINACIÓN (no-evidence-retrieved) sin "
      "citas y SIN identificadores resueltos en el texto es admisible -> competente, trigger null",
      _rec_p["deterministic_checks"]["positive_claim_requires_citations"] is False
      and _rec_p["deterministic_checks"]["positive_claim_requires_citations_state"] == "checked"
      and _pc_p["ok"] is False and _pc_p["n_citations_valid"] == 0 and _pc_p["positive_claim"] is True
      and _pc_p["decided_by"] == "code"
      and _rec_p["deterministic_checks"]["pass1_admissible"] is False and _rec_p["deterministic_checks"]["admissible"] is False
      and _rec_p["competence"]["competent"] is False and _rec_p["competence"]["reasons"] == ["admissible"]
      and _rec_p["competence"]["components"]["admissible"]["reason"] == "pass1 inadmissible (verify_output)"
      and _rec_p["fallback"]["trigger"] == "competence" and _rec_p["confidence"]["pass2"] == 0.85
      and _rec_d["deterministic_checks"]["positive_claim_requires_citations"] is True
      and _rec_d["deterministic_checks"]["admissible"] is True and _rec_d["competence"]["competent"] is True
      and _rec_d["fallback"]["trigger"] is None,
      json.dumps({"positiva": (_rec_p["deterministic_checks"]["admissible"], _rec_p["competence"]["reasons"]),
                  "declinacion": (_rec_d["deterministic_checks"]["admissible"], _rec_d["fallback"]["trigger"])}))

# --- (E) reintento por juez (WITT_JUDGE_RETRIES default 1): declarado en la fila, medido en la traza -------------------
def _panel_fail_once(verdicts, lens_fail):
    inner = _stub_caller_factory(verdicts)
    seen = {"n": 0}

    def _caller(member, system, user_text):
        if member["lens"] == lens_fail:
            seen["n"] += 1
            if seen["n"] == 1:
                raise RuntimeError("judge transport failure (simulated once)")
        return inner(member, system, user_text)
    return _caller


_rid_j, _rec_j, _ev_j = _run80("ADR-0080 reintento por juez: does wt1a mark the pronephros?", ["wt1a"], plan=True,
                               panel=_panel_fail_once(ALL_A, "overclaim"))
_judge_ev = _ev_payloads(_ev_j, "stage.audit.judge")
_row_j = next(r for r in _rec_j["audit"]["panel"] if r["lens"] == "overclaim")
check("ADR-0080 (E) reintento por juez: el juez 'overclaim' cae en su primer intento y composite_auditor lo REINTENTA una vez "
      "(WITT_JUDGE_RETRIES default 1, declarado en audit.judge_retries {value 1, source 'default-unset:…'}) -> 5 eventos "
      "stage.audit.judge (uno con attempt 2 / retries_judge 1), la fila del juez lleva verdict APPROVE + retries_judge 1 + "
      "attempts [errored, ok] (jamás fabricado), n_valid 4, y su usage cuenta UNA vez (panel 40). Corrector paridad webapp: "
      "cada evento dice 'intento N de M' — max_attempts 2 == 1 + audit.judge_retries.value, misma fuente "
      "('default-unset:WITT_JUDGE_RETRIES' en max_attempts_source): overclaim [(1 de 2), (2 de 2)]",
      len(_judge_ev) == 5
      and [(p["reviewer"] is not None, p["lens"], p["attempt"], p["retries_judge"]) for p in _judge_ev if p["lens"] == "overclaim"]
      == [(True, "overclaim", 1, 0), (True, "overclaim", 2, 1)]
      and [(p["attempt"], p["max_attempts"]) for p in _judge_ev if p["lens"] == "overclaim"] == [(1, 2), (2, 2)]
      and all(p["max_attempts"] == 2 == 1 + _rec_j["audit"]["judge_retries"]["value"]
              and p["max_attempts_source"] == _rec_j["audit"]["judge_retries"]["source"] for p in _judge_ev)
      and _row_j["verdict"] == "APPROVE" and _row_j["retries_judge"] == 1
      and [a["status"] for a in _row_j["attempts"]] == ["errored", "ok"] and "error" in _row_j["attempts"][0]
      and _rec_j["audit"]["n_valid"] == 4 and _rec_j["audit"]["verdict"] == "APPROVE"
      and {k: _rec_j["audit"]["judge_retries"].get(k) for k in ("value", "source")}
      == {"value": 1, "source": "default-unset:WITT_JUDGE_RETRIES"}
      and _rec_j["token_usage"]["by_stage"]["panel"]["in"] == 40 and _rec_j["usage_raw"]["panel_total"]["input_tokens"] == 40,
      json.dumps({"judge_events": [(p["lens"], p["attempt"]) for p in _judge_ev],
                  "row": {k: _row_j.get(k) for k in ("verdict", "retries_judge")},
                  "judge_retries": _rec_j["audit"].get("judge_retries"), "n_valid": _rec_j["audit"]["n_valid"],
                  "panel_in": _rec_j["token_usage"]["by_stage"]["panel"]["in"]}))


def _panel_billed_errored(verdicts, lens_fail):
    """Juez que devuelve SIEMPRE un veredicto ilegible pero COBRA tokens (la API respondió) — agota sus intentos."""
    inner = _stub_caller_factory(verdicts)

    def _caller(member, system, user_text):
        if member["lens"] == lens_fail:
            return ({"verdict": "MAYBE", "caught": "", "correction_applied": "", "confidence": 0.5, "reasons": []},
                    {"input_tokens": 7, "output_tokens": 2})
        return inner(member, system, user_text)
    return _caller


_rid_je, _rec_je, _ev_je = _run80("ADR-0080 juez agotado que cobró: does wt1a mark the pronephros?", ["wt1a"], plan=True,
                                  panel=_panel_billed_errored(ALL_A, "overclaim"))
_row_je = next(r for r in _rec_je["audit"]["panel"] if r["lens"] == "overclaim")
_tu_je = _rec_je["token_usage"]
_passes_in = sum(int((p or {}).get("input_tokens") or 0) for p in _rec_je["usage_raw"]["passes"].values())
_plan_in = (_tu_je.get("plan_judgment") or {}).get("in") or 0
check("ADR-0080 (E/F, corrector) M8 cuadra con un juez AGOTADO que cobró: 'overclaim' devuelve un veredicto ilegible dos veces "
      "(attempts [errored, errored], usage 7+7 medido) -> fila status 'errored' CON usage 14; audit.usage lo suma y token_usage "
      "también: by_model incluye al reviewer errado, by_stage.panel == 30 + 14 = 44, usage_raw.panel_total 44, "
      "token_usage.input_tokens == pasadas + plan + audit.usage.input_tokens (antes el gasto entraba a audit.usage y NO a M8)",
      _row_je.get("status") == "errored" and [a["status"] for a in _row_je["attempts"]] == ["errored", "errored"]
      and _row_je["usage"]["input_tokens"] == 14
      and _rec_je["audit"]["usage"]["input_tokens"] == 44
      and _tu_je["by_stage"]["panel"]["in"] == 44 and _rec_je["usage_raw"]["panel_total"]["input_tokens"] == 44
      and _row_je["reviewer"] in _tu_je["by_model"] and _tu_je["by_model"][_row_je["reviewer"]]["in"] == 14
      and _tu_je["input_tokens"] == _passes_in + _plan_in + _rec_je["audit"]["usage"]["input_tokens"]
      and _tu_je["by_stage_sum_matches_by_model"] is True,
      json.dumps({"row_usage": _row_je.get("usage"), "audit_usage": _rec_je["audit"]["usage"],
                  "panel_stage": _tu_je["by_stage"]["panel"], "total": _tu_je["input_tokens"],
                  "passes": _passes_in, "plan": _plan_in}))
# --- by_stage.plan: tres estados (corrector ADR-0080) ---
_bs3 = runs_mod._usage_by_stage([("pass1", {"usage": {"input_tokens": 10, "output_tokens": 1}})],
                                {"model": "planner-x"}, {"panel": []}, 0, plan_declared=True)
_bs3n = runs_mod._usage_by_stage([], None, {"panel": []}, 0, plan_declared=False)
check("ADR-0080 (F, corrector) by_stage.plan distingue TRES estados: plan declarado SIN usage del planner -> {in null, out null, "
      "state 'plan-without-usage (planner reported no usage)', model} (no un 0 ni 'no-plan'); sin plan -> {0, 0, 'no-plan'}; "
      "con usage -> medido (plan 400 en la corrida competente)",
      _bs3["plan"] == {"in": None, "out": None, "state": "plan-without-usage (planner reported no usage)", "model": "planner-x"}
      and _bs3n["plan"] == {"in": 0, "out": 0, "state": "no-plan"} and _bs_c["plan"]["in"] == 400
      and _bs3["_sum"]["in"] == 10,
      json.dumps({"declared_no_usage": _bs3["plan"], "no_plan": _bs3n["plan"]}))
# --- una env, una verdad: familias en mayúsculas/duplicadas (corrector ADR-0080) ---
_rid_f, _rec_f, _ev_f = _run80("ADR-0080 familias env: does wt1a mark the pronephros?", ["wt1a"],
                               env={"WITT_SEARCH_DEFAULT_FAMILIES": "EuropePMC,pubmed,pubmed,Zfin"})
check("ADR-0080 (C, corrector) UN lector de WITT_SEARCH_DEFAULT_FAMILIES: 'EuropePMC,pubmed,pubmed,Zfin' -> "
      "search_ledger.families_default == plan.families_default == ['europepmc','pubmed','zfin'] (minúsculas, sin duplicados) "
      "con config_source.families 'env:…' y config_reader 'search_harness'; round_budget_s es FLOTANTE del mismo parser",
      _rec_f["search_ledger"]["families_default"] == ["europepmc", "pubmed", "zfin"]
      and _rec_f["search_ledger"]["plan"]["families_default"] == ["europepmc", "pubmed", "zfin"]
      and _rec_f["search_ledger"]["config_source"]["families"] == "env:WITT_SEARCH_DEFAULT_FAMILIES"
      and _rec_f["search_ledger"]["config_reader"] == "search_harness"
      and isinstance(_rec_f["search_ledger"]["round_budget_s"], float),
      json.dumps({"ledger": _rec_f["search_ledger"]["families_default"], "plan": _rec_f["search_ledger"]["plan"]["families_default"]}))

# --- (G) contrato 1.9: los campos ADITIVOS presentes en el registro (paridad front<->back: la webapp los tipa `?`) ------
_REQ_19 = {"competence", "search_ledger", "citations_support_summary", "citations", "deterministic_checks", "token_usage",
           "fallback", "render_contract_version"}
check("ADR-0080 (G) contrato 1.9 en el registro: render_contract_version '1.9'; frozen.competence, frozen.search_ledger {plan, "
      "rounds[], families_default, n_rounds, cap, state, plan_state, config_source}, citations[].support_state, "
      "citations_support_summary, deterministic_checks.{pass, pass1_admissible, positive_claim_requires_citations(+_state), "
      "competence_gate}, fallback.trigger en {structural, competence, null} + fb_meta.{trigger_legacy, trigger_vocabulary, "
      "competence}, token_usage.by_stage con las 9 etapas + _sum, epistemic_summary.{competent, n_search_rounds} — en TODAS "
      "las corridas de esta sección",
      all(r["render_contract_version"] == runs_mod.RENDER_CONTRACT_VERSION and _REQ_19 <= set(r)
          and {"plan", "rounds", "families_default", "n_rounds", "cap", "state", "plan_state", "config_source"} <= set(r["search_ledger"])
          and all("support_state" in c for c in r["citations"])
          and {"pass", "pass1_admissible", "positive_claim_requires_citations", "positive_claim_requires_citations_state",
               "competence_gate"} <= set(r["deterministic_checks"])
          and r["fallback"]["trigger"] in runs_mod.FALLBACK_TRIGGERS
          and {"trigger_legacy", "trigger_vocabulary", "competence"} <= set(r["fallback"]["fb_meta"])
          and set(runs_mod.TOKEN_STAGES) | {"_sum"} <= set(r["token_usage"]["by_stage"])
          and "by_stage_sum_matches_by_model" in r["token_usage"]
          for r in (_rec_c, _rec_h, _rec_2, _rec_1, _rec_b, _rec_k, _rec_kl, _rec_g, _rec_s, _rec_p, _rec_d, _rec_j,
                    _rec_nh, _rec_cc, _rec_cd, _rec_di, _rec_ab, _rec_je, _rec_f, _rec_ns, _rec_ga))
      and all({"competent", "n_search_rounds"} <= set(app.get_run(rid, authorization=AUTH)["epistemic_summary"])
              for rid in (_rid_c, _rid_h, _rid_2, _rid_k))
      and all(r["deterministic_checks"]["pass"] in ("pass1", "pass2", "revision")
              for r in (_rec_c, _rec_h, _rec_2, _rec_1, _rec_b, _rec_k, _rec_kl, _rec_g, _rec_s, _rec_p, _rec_d, _rec_j))
      # corrector: 'confidence' vuelve al vocabulario SÓLO para competent null (kill-switch / not-applicable)
      and runs_mod.FALLBACK_TRIGGERS == ("structural", "competence", "confidence", None)
      and runs_mod.TRIGGER_LEGACY_CONFIDENCE == "confidence"
      and all(r["fallback"]["trigger"] != "confidence" or r["competence"]["competent"] is None
              for r in (_rec_c, _rec_h, _rec_2, _rec_1, _rec_b, _rec_k, _rec_kl, _rec_g, _rec_s, _rec_p, _rec_d, _rec_j,
                        _rec_nh, _rec_cc, _rec_cd, _rec_di, _rec_ab, _rec_je, _rec_f, _rec_ns, _rec_ga)))

# --- (G, corrector paridad webapp 2026-09-15) vocabulario REAL de plan_state: exactos + prefijos, declarado y MEDIDO -------
_PS_RUNS = ((_rec_c, _ev_c), (_rec_h, _ev_h), (_rec_2, _ev_2), (_rec_1, _ev_1), (_rec_b, _ev_b), (_rec_k, _ev_k),
            (_rec_kl, _ev_kl), (_rec_g, _ev_g), (_rec_s, _ev_s), (_rec_p, _ev_p), (_rec_d, _ev_d), (_rec_j, _ev_j),
            (_rec_nh, _ev_nh), (_rec_cc, _ev_cc), (_rec_cd, _ev_cd), (_rec_di, _ev_di), (_rec_ab, _ev_ab), (_rec_je, _ev_je),
            (_rec_f, _ev_f), (_rec_ns, _ev_ns), (_rec_ga, _ev_ga))
_sh_saved = runs_mod.search_harness


class _HarnessBoom:
    @staticmethod
    def build_search_plan(*a, **kw):
        raise RuntimeError("plan exploded (simulated)")


runs_mod.search_harness = _HarnessBoom
_plan_err, _state_err = runs_mod._build_search_plan("q", ["wt1a"], None, runs_mod._search_config())
runs_mod.search_harness = None
_plan_un, _state_un = runs_mod._build_search_plan("q", ["wt1a"], None, runs_mod._search_config())
runs_mod.search_harness = _sh_saved
_ps_seen = sorted({r["search_ledger"]["plan_state"] for r, _ in _PS_RUNS}
                  | {p["state"] for _, ev in _PS_RUNS for p in _ev_payloads(ev, "stage.search.plan")}
                  | {(r["search_ledger"].get("plan") or {}).get("state") for r, _ in _PS_RUNS
                     if (r["search_ledger"].get("plan") or {}).get("state") is not None}
                  | {_state_err, _plan_err["state"], _state_un, _plan_un["state"]})
check("ADR-0080 (G, corrector paridad webapp) vocabulario REAL de plan_state: ADR-0080 declaraba 4 literales exactos y el código "
      "emite además 'kill-switch <ENV>=0', 'not-applicable (<skipped_reason>)' y, en el plan-sobre de _build_search_plan, "
      "'error: <tipo>: <msg>' / 'harness-unavailable (<qué faltó>)' junto a los exactos 'error' / 'harness-unavailable'; runs lo "
      "declara (SEARCH_PLAN_STATES_EXACT + SEARCH_PLAN_STATE_PREFIXES), lo congela en search_ledger.plan_state_vocabulary en las "
      "21 corridas y plan_state_in_vocabulary lo valida: TODOS los search_ledger.plan_state, plan.state y stage.search.plan.state "
      "de la sección pasan (medidos aquí: 'built', 'not-requested', 'kill-switch WITT_COMPETENCE_GATE=0', 'kill-switch "
      "WITT_SEARCH_HARNESS=0'; sobre _build_search_plan: 'error' + 'error: RuntimeError: …', 'harness-unavailable' + "
      "'harness-unavailable (…)'); 'legacy-path-b (built)' y None NO pasan",
      all(runs_mod.plan_state_in_vocabulary(s) for s in _ps_seen)
      and {"built", "not-requested", "kill-switch WITT_COMPETENCE_GATE=0", "kill-switch WITT_SEARCH_HARNESS=0",
           "error", "harness-unavailable"} <= set(_ps_seen)
      and _state_err == "error" and _plan_err["state"].startswith("error: RuntimeError: plan exploded")
      and _state_un == "harness-unavailable" and _plan_un["state"].startswith("harness-unavailable (")
      and all(r["search_ledger"]["plan_state_vocabulary"] == runs_mod.SEARCH_PLAN_STATE_VOCABULARY for r, _ in _PS_RUNS)
      and runs_mod.SEARCH_PLAN_STATE_VOCABULARY["exact"] == list(runs_mod.SEARCH_PLAN_STATES_EXACT)
      == ["built", "not-requested", "harness-unavailable", "error"]
      and runs_mod.SEARCH_PLAN_STATE_VOCABULARY["prefixes"] == list(runs_mod.SEARCH_PLAN_STATE_PREFIXES)
      == ["error: ", "kill-switch ", "not-applicable (", "harness-unavailable ("]
      and not runs_mod.plan_state_in_vocabulary("legacy-path-b (built)") and not runs_mod.plan_state_in_vocabulary(None),
      json.dumps(_ps_seen))

# =====================================================================================================
# ADR-0081 — política best-tier v2 / generación g2-2026-09: contrato 1.10, frozen.models MEDIDO (requested vs reported),
# stage.models, cuórum por familias en el veredicto + REVISE estructural, topes/effort por generación, run.state{queued}.
# {run_no, thread.root_run_no}, by_stage.panel.by_model, kill-switch g1 byte a byte contra un golden 1.9 MEDIDO. Sigue
# DENTRO del bloque offline (urlopen bloqueado y contado; mcp_cache intacto). Los ids de modelo se LEEN de la tabla
# (models.resolve_role / GENERATIONS), jamás se pinean literales (gate estático M.4 de smoke_models.py).
# =====================================================================================================
_G2, _G1 = "g2-2026-09", "g1-2026-08"
_ROLE_SYNTH, _ROLE_ELICIT, _ROLE_PLANNER = (models.resolve_role("synthesizer"), models.resolve_role("elicitation"),
                                            models.resolve_role("planner"))
_ROLE_QA = models.resolve_role("question_agent")
_TOPES = {g: models.GENERATIONS[g]["max_tokens"] for g in (_G1, _G2)}
_API_81 = []                     # lo que el wrapper REAL pidió a la API falsa: {tool, model, max_tokens, effort, return_meta}
_api_saved_81 = composite_auditor._anthropic_tool_call
_SYNTH_OUT_81 = {"direct_answer": "wt1a (ENSDARG00000031420) marks the zebrafish pronephros.", "confidence": 0.8,
                 "absence_kind": "not-applicable", "alternatives_considered": ["wt1b paralogo redundante: descartado"],
                 "framework_applied": "Logic-LM", "framework_criterion": "for any task whose criteria are formalizable",
                 "framework_reason": "formalizable", "gap_flags": [],
                 "evidence_cited": [{"kind": "di-record", "id": "CORPUS-2026-0001"}], "search_query_en": "wt1a pronephros"}

# El keyset de un registro 1.9 — MEDIDO el 2026-09-15 sobre el árbol f57a3d3 + S1 (runs.py SIN tocar) con el mismo camino
# que la corrida kill-switch de abajo (plan con planner stub, sintetizador REAL con API falsa, panel 4/4 APPROVE,
# competente). Es el golden de (M.2): el frozen 1.10 menos las llaves aditivas debe tener EXACTAMENTE estas llaves.
_GOLDEN_19 = {
    "top": ["agents_invoked", "alternatives_considered", "answer", "answer_initial", "audit", "audit_initial",
            "bundle_identity", "citations", "citations_schema", "citations_support_summary", "competence", "confidence",
            "decision_state", "deterministic_checks", "episode_axes", "evidence_cited_raw", "fallback", "measured_at",
            "niches", "origin", "plan", "plan_declared", "plan_parent_matches_run", "plan_parent_matches_run_state",
            "plan_question_matches_run", "plan_snapshot_matches_run", "plan_snapshot_matches_run_state",
            "precedent_citations", "precedent_citations_state", "question", "question_matches_run", "reasoning",
            "render_contract_version", "retrieval_summary", "revision", "run_id", "search_ledger", "store_at_retrieval",
            "thread", "thread_context", "thread_context_skipped_reason", "thread_parent_matches_run",
            "thread_parent_matches_run_rule", "thread_parent_matches_run_state", "token_usage", "usage_raw", "user_id"],
    "answer": ["absence_kind", "direct_answer", "gap_flags", "model", "stated_confidence"],
    "audit": ["approved", "judge_retries", "n_valid", "note", "panel", "rejected", "required", "required_because",
              "source_vocabulary", "tally", "usage", "verdict"],
    "audit_row": ["attempts", "caught", "confidence", "correction_applied", "family", "lens", "reasons", "retries_judge",
                  "reviewer", "usage", "verdict"],
    "by_stage_panel": ["in", "out"], "by_stage_synth": ["in", "model", "out"],
    "by_stage_elicit": ["in", "model", "out", "state"], "by_stage_plan": ["in", "model", "out"],
    "revision": ["cap", "enabled", "performed"],
    "planner": ["class", "model", "note", "thread_context_delivered", "usage"],
    "plan_audit": ["class", "note", "panel", "required"],
    "epistemic": ["competent", "confidence_state", "n_search_rounds", "niches", "origin", "panel_n_valid",
                  "retrieval_mode", "thread_id", "turn_no", "verdict"],
    "queued_payload": ["origin", "state", "thread"],
    "queued_thread": ["context", "context_bytes", "context_skipped_reason", "n_comments_included", "parent_run_id",
                      "thread_id", "turn_kind", "turn_no"],
    "verdict_payload": ["n_valid", "revision_round", "source_vocabulary", "tally", "verdict"],
    "judge_payload": ["attempt", "heartbeat", "lens", "max_attempts", "max_attempts_source", "phase", "retries_judge",
                      "reviewer"],
    "event_types": ["run.state", "run.state", "stage.plan", "stage.path_a", "stage.check_entities", "stage.assess_sufficiency",
                    "stage.decision_state", "stage.synthesize.start", "stage.synthesize.pass1", "stage.confidence.elicit",
                    "stage.deterministic_gate", "stage.competence", "stage.audit.start", "stage.audit.judge",
                    "stage.audit.judge", "stage.audit.judge", "stage.audit.judge", "stage.audit.verdict", "run.state"],
}
# Llaves ADITIVAS 1.10 por bloque. Las de audit/panel las declara composite_auditor (S2): se leen de su constante.
_ADD_110 = {
    "top": {"models"}, "answer": {"model_source", "model_reported", "relation"},
    "audit": set(getattr(composite_auditor, "_BUNDLE_AUDIT_KEYS_1_10", ())),
    "audit_row": {"family_source", "api", "api_source", "reviewer_source", "max_tokens"},
    "by_stage_panel": {"by_model"}, "by_stage_synth": {"model_source"}, "by_stage_elicit": {"model_source"},
    "by_stage_plan": {"model_source"}, "revision": set(), "planner": {"model_source", "model_reported", "relation"},
    "plan_audit": {"panel_resolved"}, "epistemic": {"model_generation", "panel_n_families_valid"},
    "queued_payload": {"run_no"}, "queued_thread": {"root_run_no"},
    "verdict_payload": {"families_valid", "n_families_valid", "lenses_valid", "n_lenses_valid", "panel_incomplete",
                        "panel_incomplete_reasons"},
    "judge_payload": {"family", "api", "api_source", "reviewer_source"},
}
# ADR-0082 (1.11, L.2 i–iii): llaves ADITIVAS declaradas del consejo — se restan junto a las de 1.10 para comparar contra el
# golden 1.9: frozen.council (top), epistemic_summary.council_* (G.8) y run.state{queued}.council (J)
_ADD_110["top"] |= {"council"}
_ADD_110["epistemic"] |= {"council_state", "council_n_valid", "council_n_members", "council_must_uncovered"}
_ADD_110["queued_payload"] |= {"council"}
# ADR-0083 (1.12, L): llaves ADITIVAS declaradas de las figuras — frozen.figures (top, SIEMPRE presente en >= 1.12),
# epistemic_summary.figures_* y stage.audit.judge.{figures_sent, figures_sha256} (medidos: 0 y [] cuando no viajó ninguna)
_ADD_110["top"] |= {"figures"}
_ADD_110["epistemic"] |= {"figures_state", "figures_n_verified", "figures_n_cited"}
_ADD_110["judge_payload"] |= {"figures_sent", "figures_sha256"}
# ADR-0084 (1.13, G.2/G.8): frozen.web_locator (top, SIEMPRE presente en >= 1.13) y epistemic_summary.web_* (null = no midió)
_ADD_110["top"] |= {"web_locator"}
_ADD_110["epistemic"] |= {"web_locator_state", "web_n_located", "web_n_unresolved"}
# ADR-0083 (G.6, F3): con WITT_FIGURES=1 CADA fila del panel gana saw_figures (MEDIDO: n 0 + detail cuando no hubo figuras) y
# audit gana vision — llaves aditivas declaradas; bajo WITT_FIGURES=0 no se emiten (M.1, medido en la sección ADR-0083)
_ADD_110["audit"] |= {"vision"}
_ADD_110["audit_row"] |= {"saw_figures"}


def _mk_api_81(reported_suffix=None, reported_literal=None):
    """API Anthropic FALSA con la firma NUEVA de composite_auditor._anthropic_tool_call (effort=, return_meta=): graba lo que
    el wrapper REAL pidió (model, max_tokens, effort) y devuelve la 3-tupla con meta.model_reported = <pedido>+suffix
    (alias fechado -> 'prefix') | literal ('different') | None (la API no lo dijo -> 'not-reported')."""
    def fake(model, system, user_text, tool=None, timeout=120, retries=1, max_tokens=1200, effort=None, return_meta=False):
        name = (tool or {}).get("name")
        _API_81.append({"tool": name, "model": model, "max_tokens": max_tokens, "effort": effort, "return_meta": return_meta})
        if name == "emit_confidence":
            out, usage = {"confidence": 0.8}, {"input_tokens": 30, "output_tokens": 3}
        elif name == "emit_plan_judgment":
            out, usage = _fake_planner_ok("q", [])[0], {"input_tokens": 400, "output_tokens": 120}
        else:
            out, usage = dict(_SYNTH_OUT_81), {"input_tokens": 100, "output_tokens": 50}
        if not return_meta:
            return out, usage
        reported = (model + reported_suffix) if reported_suffix else reported_literal
        return out, usage, {"model_reported": reported, "api": "anthropic-messages", "stop_reason": "tool_use"}
    return fake


def _with_env(env, fn):
    saved = {k: os.environ.get(k) for k in env}
    for k, v in env.items():
        os.environ[k] = v
    try:
        return fn()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _keys_minus(d, add):
    return sorted(set(d) - set(add))


def _corr(rec):
    return next(r for r in rec["audit"]["panel"] if r["lens"] == "correctness")


# --- (A) corrida con sintetizador STUB + plan: stage.models, frozen.models con 'not-reported', planner COPIADO ------------
_rid_a81, _rec_a81, _ev_a81 = _run80("ADR-0081 A: does wt1a mark the pronephros?", ["wt1a"], plan=True)
_t_a81 = _ev_types(_ev_a81)
_sm_a81 = _ev_payloads(_ev_a81, "stage.models")
check("ADR-0081 (B) stage.models es el PRIMER evento tras run.state{running} y antes de stage.plan, agent 'runs', payload = "
      "snapshot REDUCIDO {generation, generation_source, table_version, panel_signature, roles (8, forma RoleResolved), "
      "panel (4, orden LENSES), warnings[], unknown_models[]}; generación g2 por default-unset; todo warning en vocabulario",
      _t_a81[:4] == ["run.state", "run.state", "stage.models", "stage.plan"] and len(_sm_a81) == 1
      and next(e for e in _ev_a81 if e["type"] == "stage.models")["agent"] == "runs"
      and set(_sm_a81[0]) == set(runs_mod.STAGE_MODELS_PAYLOAD_KEYS)
      and _sm_a81[0]["generation"] == _G2 and _sm_a81[0]["generation_source"].startswith("default-unset:")
      and _sm_a81[0]["table_version"] == models.MODELS_TABLE_VERSION
      and set(_sm_a81[0]["roles"]) == set(models.ROLES)
      and all(tuple(r) == models.ROLE_RESOLVED_FIELDS for r in _sm_a81[0]["roles"].values())
      and [m["lens"] for m in _sm_a81[0]["panel"]] == list(models.LENSES)
      and isinstance(_sm_a81[0]["warnings"], list)
      and all(w.startswith(models.WARNING_PREFIXES) for w in _sm_a81[0]["warnings"])
      and _sm_a81[0]["unknown_models"] == [],
      json.dumps({"first": _t_a81[:4], "warnings": _sm_a81[0]["warnings"][:3]}))
_M_a = _rec_a81["models"]
check("ADR-0082 (M, C9): frozen.models.roles.council == stage.models.roles.council (el MISMO RoleResolved del snapshot: modelo del rol "
      "`council` de la tabla g2 con su fuente; viaja aunque el consejo no haya corrido en esta corrida — el rol está en la tabla)",
      _M_a["roles"].get("council") == _sm_a81[0]["roles"]["council"] and _M_a["roles"]["council"]["model"] == models.GENERATIONS[_G2]["defaults"]["council"]
      and _M_a["roles"]["council"]["source"].startswith("default:"),
      json.dumps({"frozen": _M_a["roles"].get("council"), "stage": _sm_a81[0]["roles"].get("council")})[:300])
check("ADR-0081 (B) frozen.models con sintetizador STUB: forma PROVENANCE_FIELDS; roles.synthesizer/elicitation == los resueltos "
      "en la llamada; question_agent null (no corrió); roles.planner COPIADO de plan_json.judgment.planner (provenance "
      "'plan_json'); ran.synthesize_pass1 {requested 'stub-synth', reported null, relation 'not-reported', thinking_state "
      "'unknown-to-table'}; pass2/revision/elicit_* null (competente; stub sin usage_elicitation); ran.plan not-reported; "
      "ran.panel 4 filas {lens, reviewer, reported null, relation 'not-reported', api_used == audit.panel[].api, attempts 1}",
      tuple(_M_a) == models.PROVENANCE_FIELDS and _M_a["generation"] == _G2
      and _M_a["table_version"] == models.MODELS_TABLE_VERSION and _M_a["table_as_of"] == models.MODEL_TABLE_AS_OF
      and _M_a["roles"]["synthesizer"] == _ROLE_SYNTH and _M_a["roles"]["elicitation"] == _ROLE_ELICIT
      and _M_a["roles"]["question_agent"] is None
      and _M_a["roles"]["planner"] == {"model": _rec_a81["plan"]["judgment"]["planner"]["model"],
                                       "model_source": _rec_a81["plan"]["judgment"]["planner"]["model_source"],
                                       "provenance": "plan_json"}
      and _M_a["ran"]["synthesize_pass1"] == {"requested": "stub-synth", "reported": None, "relation": "not-reported",
                                              "thinking_state": models.THINKING_STATES[None]}
      and _M_a["ran"]["synthesize_pass2"] is None and _M_a["ran"]["revision"] is None
      and _M_a["ran"]["elicit_pass1"] is None and _M_a["ran"]["elicit_pass2"] is None and _M_a["ran"]["question"] is None
      and _M_a["ran"]["plan"]["requested"] == _ROLE_PLANNER["model"] and _M_a["ran"]["plan"]["relation"] == "not-reported"
      and [p["lens"] for p in _M_a["ran"]["panel"]] == list(models.LENSES)
      and all(p["reported"] is None and p["relation"] == "not-reported" and p["attempts"] == 1
              and p["api_used"] == next(r["api"] for r in _rec_a81["audit"]["panel"] if r["lens"] == p["lens"])
              for p in _M_a["ran"]["panel"])
      and _M_a["rule"] == models.PROVENANCE_RULE,
      json.dumps({"planner": _M_a["roles"]["planner"], "pass1": _M_a["ran"]["synthesize_pass1"]}))
_pj_a = _rec_a81["plan"]["judgment"]["planner"]
check("ADR-0081 (B/J) plan.judgment.planner con planner STUB (2-tupla): model = rol planner RESUELTO (lo que el código pediría, "
      "con model_source 'default:g2…'), model_reported null, relation 'not-reported'; plan.audit.panel == models.panel() en la "
      "llamada + panel_resolved[] {reviewer, family, lens, reviewer_source}; answer += model_source null (stub), model_reported "
      "null, relation 'not-reported'",
      _pj_a["model"] == _ROLE_PLANNER["model"] and _pj_a["model_source"] == _ROLE_PLANNER["source"]
      and _pj_a["model_reported"] is None and _pj_a["relation"] == "not-reported"
      and _rec_a81["plan"]["audit"]["panel"] == [f"{m['reviewer']} ({m['lens']})" for m in models.panel()]
      and [p["reviewer"] for p in _rec_a81["plan"]["audit"]["panel_resolved"]] == [m["reviewer"] for m in models.panel()]
      and all(set(p) == {"reviewer", "family", "lens", "reviewer_source"} for p in _rec_a81["plan"]["audit"]["panel_resolved"])
      and _rec_a81["answer"]["model"] == "stub-synth" and _rec_a81["answer"]["model_source"] is None
      and _rec_a81["answer"]["model_reported"] is None and _rec_a81["answer"]["relation"] == "not-reported",
      json.dumps(_pj_a))
_vd_a = _ev_payloads(_ev_a81, "stage.audit.verdict")
_jd_a = _ev_payloads(_ev_a81, "stage.audit.judge")
check("ADR-0081 (D) stage.audit.verdict += families_valid ['anthropic','openai'], n_families_valid 2, lenses_valid (4), "
      "n_lenses_valid 4, panel_incomplete False, panel_incomplete_reasons []; stage.audit.judge += family, api (== audit.panel[].api "
      "de la misma lente), api_source, reviewer_source 'default:g2…'; stage.synthesize.start payload {model, model_source, "
      "generation} del rol RESUELTO; epistemic_summary += model_generation g2 + panel_n_families_valid 2; agents_invoked."
      "composite-auditor.evidence_generated += 'families_valid:2'",
      len(_vd_a) == 1 and _vd_a[0]["families_valid"] == ["anthropic", "openai"] and _vd_a[0]["n_families_valid"] == 2
      and _vd_a[0]["lenses_valid"] == list(models.LENSES) and _vd_a[0]["n_lenses_valid"] == 4
      and _vd_a[0]["panel_incomplete"] is False and _vd_a[0]["panel_incomplete_reasons"] == []
      and len(_jd_a) == 4
      and all({"family", "api", "api_source", "reviewer_source"} <= set(j) for j in _jd_a)
      and all(j["api"] == next(r["api"] for r in _rec_a81["audit"]["panel"] if r["lens"] == j["lens"]) for j in _jd_a)
      and all(j["reviewer_source"] == f"default:{_G2}" for j in _jd_a)
      and _ev_payloads(_ev_a81, "stage.synthesize.start") == [{"model": _ROLE_SYNTH["model"],
                                                               "model_source": _ROLE_SYNTH["source"], "generation": _G2}]
      and app.get_run(_rid_a81, authorization=AUTH)["epistemic_summary"]["model_generation"] == _G2
      and app.get_run(_rid_a81, authorization=AUTH)["epistemic_summary"]["panel_n_families_valid"] == 2
      and "families_valid:2" in next(a for a in _rec_a81["agents_invoked"]
                                     if a["agent"] == "composite-auditor")["evidence_generated"],
      json.dumps({"verdict": {k: _vd_a[0][k] for k in ("families_valid", "n_lenses_valid", "panel_incomplete_reasons")},
                  "judge0": {k: _jd_a[0][k] for k in ("family", "api", "api_source", "reviewer_source")}}))
_bp_a = _rec_a81["token_usage"]["by_stage"]["panel"]
check("ADR-0081 (H) by_stage.panel.by_model {reviewer: {in, out}}: llaves == los 4 reviewers del panel, cada uno 10/5, "
      "Σ == panel.in/out (40/20); by_stage_sum_matches_by_model sigue True; by_model sin 'unknown-model'",
      set(_bp_a["by_model"]) == {r["reviewer"] for r in _rec_a81["audit"]["panel"]}
      and all(v == {"in": 10, "out": 5} for v in _bp_a["by_model"].values())
      and sum(v["in"] for v in _bp_a["by_model"].values()) == _bp_a["in"] == 40
      and sum(v["out"] for v in _bp_a["by_model"].values()) == _bp_a["out"] == 20
      and _rec_a81["token_usage"]["by_stage_sum_matches_by_model"] is True
      and "unknown-model" not in _rec_a81["token_usage"]["by_model"],
      json.dumps(_bp_a))

# --- (B) CAMINO REAL (_default_synthesizer + API falsa con meta): 'prefix', topes g2, sin effort, no-plan -----------------
composite_auditor._anthropic_tool_call = _mk_api_81(reported_suffix="-20260915")
_API_81.clear()
_rid_b81, _rec_b81, _ev_b81 = _run80("ADR-0081 B: prefix (alias fechado)", ["wt1a"], synth=runs_mod._default_synthesizer, plan=False)
_M_b = _rec_b81["models"]
_TS_ADAPT = models.THINKING_STATES[models.MODELS[_ROLE_SYNTH["model"]]["thinking_default"]]
check("ADR-0081 (B) CAMINO REAL con API falsa que reporta '<pedido>-20260915': ran.synthesize_pass1/pass2 {requested == rol "
      "synthesizer, reported con sufijo, relation 'prefix' (NEUTRO), thinking_state por tabla}; elicit_pass1/pass2 'prefix' con "
      "requested == rol elicitation; sin plan -> ran.plan null y roles.planner {model null, provenance 'no-plan'}; answer "
      "{model == rol, model_source 'default:g2…', model_reported con sufijo, relation 'prefix'}",
      _M_b["ran"]["synthesize_pass1"] == {"requested": _ROLE_SYNTH["model"], "reported": _ROLE_SYNTH["model"] + "-20260915",
                                          "relation": "prefix", "thinking_state": _TS_ADAPT}
      and _M_b["ran"]["synthesize_pass2"]["relation"] == "prefix"
      and _M_b["ran"]["elicit_pass1"] == {"requested": _ROLE_ELICIT["model"], "reported": _ROLE_ELICIT["model"] + "-20260915",
                                          "relation": "prefix", "thinking_state": _TS_ADAPT}
      and _M_b["ran"]["elicit_pass2"]["relation"] == "prefix"
      and _M_b["ran"]["plan"] is None and _M_b["ran"]["revision"] is None
      and _M_b["roles"]["planner"] == {"model": None, "model_source": None, "provenance": "no-plan"}
      and _rec_b81["answer"]["model"] == _ROLE_SYNTH["model"] and _rec_b81["answer"]["model_source"] == _ROLE_SYNTH["source"]
      and _rec_b81["answer"]["model_reported"] == _ROLE_SYNTH["model"] + "-20260915"
      and _rec_b81["answer"]["relation"] == "prefix",
      json.dumps({"pass1": _M_b["ran"]["synthesize_pass1"], "elicit": _M_b["ran"]["elicit_pass1"]}))
_calls_b = _API_81[:]
check("ADR-0081 (C.4) topes por GENERACIÓN recibidos por la API falsa (g2): emit_answer max_tokens == 8000 (tope synthesizer), "
      "emit_confidence == 2000 (tope elicitation); effort None en TODAS (WITT_ANTHROPIC_EFFORT vacío = no se envía); "
      "return_meta True en todas (el wrapper pide lo que la API dijo); model pedido == el del rol",
      len(_calls_b) == 4
      and all(c["max_tokens"] == _TOPES[_G2]["synthesizer"] == 8000 and c["model"] == _ROLE_SYNTH["model"]
              for c in _calls_b if c["tool"] == "emit_answer")
      and all(c["max_tokens"] == _TOPES[_G2]["elicitation"] == 2000 and c["model"] == _ROLE_ELICIT["model"]
              for c in _calls_b if c["tool"] == "emit_confidence")
      and all(c["effort"] is None and c["return_meta"] is True for c in _calls_b),
      json.dumps(_calls_b))
_bs_b = _rec_b81["token_usage"]["by_stage"]
check("ADR-0081 (H/J) by_stage con el wrapper REAL: synthesize_pass1/pass2.{model == rol, model_source 'default:g2…'}, "
      "elicit_pass1/pass2 measured con model == rol elicitation + model_source; plan 'no-plan' sin model_source; by_model bajo "
      "el modelo del rol = 2×(100+30) síntesis+elicitación + 10 del juez correctness (mismo modelo en g2) = 270",
      _bs_b["synthesize_pass1"]["model"] == _ROLE_SYNTH["model"] and _bs_b["synthesize_pass1"]["model_source"] == _ROLE_SYNTH["source"]
      and _bs_b["synthesize_pass2"]["model_source"] == _ROLE_SYNTH["source"]
      and _bs_b["elicit_pass1"]["state"] == "measured" and _bs_b["elicit_pass1"]["model"] == _ROLE_ELICIT["model"]
      and _bs_b["elicit_pass1"]["model_source"] == _ROLE_ELICIT["source"]
      and _bs_b["plan"]["state"] == "no-plan" and "model_source" not in _bs_b["plan"]
      and _corr(_rec_b81)["reviewer"] == _ROLE_SYNTH["model"]
      and _rec_b81["token_usage"]["by_model"][_ROLE_SYNTH["model"]] == {"in": 270, "out": 111},
      json.dumps({"synth": _bs_b["synthesize_pass1"], "elicit": _bs_b["elicit_pass1"],
                  "by_model": _rec_b81["token_usage"]["by_model"]}))

# --- (C) 'different' + effort por env (sólo a modelos adaptativos) -----------------------------------------------------
composite_auditor._anthropic_tool_call = _mk_api_81(reported_literal="otro-modelo-x")
_API_81.clear()
_rid_c81, _rec_c81, _ev_c81 = _run80("ADR-0081 C: different + effort", ["wt1a"], synth=runs_mod._default_synthesizer, plan=True,
                                     env={"WITT_ANTHROPIC_EFFORT": "low", "WITT_ANTHROPIC_EFFORT_ELICIT": "medium"})
_calls_c = _API_81[:]
check("ADR-0081 (B/C.4) la API reporta OTRO modelo -> relation 'different' (objeción) en ran.synthesize_pass1 y answer; con "
      "WITT_ANTHROPIC_EFFORT=low + _ELICIT=medium el wrapper pasa effort 'low' a emit_answer y 'medium' a emit_confidence (g2: "
      "el rol es adaptativo); answer.model sigue siendo lo PEDIDO",
      _rec_c81["models"]["ran"]["synthesize_pass1"]["relation"] == "different"
      and _rec_c81["models"]["ran"]["synthesize_pass1"]["reported"] == "otro-modelo-x"
      and _rec_c81["answer"]["relation"] == "different" and _rec_c81["answer"]["model"] == _ROLE_SYNTH["model"]
      and [c["effort"] for c in _calls_c if c["tool"] == "emit_answer"] == ["low"]
      and [c["effort"] for c in _calls_c if c["tool"] == "emit_confidence"] == ["medium"],
      json.dumps([(c["tool"], c["effort"]) for c in _calls_c]))

# --- (M.2) KILL-SWITCH g1 + chat-completions + MIN 0/0 + LEDGER 0: keyset 1.9 EXACTO (golden medido) y valores f57a3d3 -----
composite_auditor._anthropic_tool_call = _mk_api_81(reported_suffix="-20260915")
_API_81.clear()
_KS_ENV = {"WITT_MODEL_GENERATION": _G1, "WITT_OPENAI_API": "chat-completions", "WITT_PANEL_MIN_FAMILIES": "0",
           "WITT_PANEL_MIN_LENSES": "0", "WITT_CONFIG_LEDGER": "0", "WITT_ANTHROPIC_EFFORT": "low"}
_rid_k81, _rec_k81, _ev_k81 = _run80("ADR-0081 kill-switch g1: does wt1a mark the pronephros?", ["wt1a"],
                                     synth=runs_mod._default_synthesizer, plan=True, env=_KS_ENV)
_calls_k = _API_81[:]
_g1d = models.GENERATIONS[_G1]["defaults"]
_view_k = app.get_run(_rid_k81, authorization=AUTH)
_ev_k_types = _ev_types(_ev_k81)
_queued_k = next(e for e in _ev_k81 if e["type"] == "run.state" and e["payload"].get("state") == "queued")["payload"]
_bs_k = _rec_k81["token_usage"]["by_stage"]
# el golden se midió sobre el blob CRUDO (runs.frozen_record_json); la vista GET /runs/{id}/record lo decora con
# consensus/ratings/ratings_masked (ADR-0047/0055) — se compara crudo contra crudo
_raw_k81 = json.loads(db.get_run(_rid_k81)["frozen_record_json"])
_ks_keysets = {
    "top": _keys_minus(_raw_k81, _ADD_110["top"]),
    "answer": _keys_minus(_rec_k81["answer"], _ADD_110["answer"]),
    "audit": _keys_minus(_rec_k81["audit"], _ADD_110["audit"]),
    "audit_row": _keys_minus(_corr(_rec_k81), _ADD_110["audit_row"]),
    "by_stage_panel": _keys_minus(_bs_k["panel"], _ADD_110["by_stage_panel"]),
    "by_stage_synth": _keys_minus(_bs_k["synthesize_pass1"], _ADD_110["by_stage_synth"]),
    "by_stage_elicit": _keys_minus(_bs_k["elicit_pass1"], _ADD_110["by_stage_elicit"]),
    "by_stage_plan": _keys_minus(_bs_k["plan"], _ADD_110["by_stage_plan"]),
    "revision": _keys_minus(_rec_k81["revision"], _ADD_110["revision"]),
    "planner": _keys_minus(_rec_k81["plan"]["judgment"]["planner"], _ADD_110["planner"]),
    "plan_audit": _keys_minus(_rec_k81["plan"]["audit"], _ADD_110["plan_audit"]),
    "epistemic": _keys_minus(_view_k["epistemic_summary"], _ADD_110["epistemic"]),
    "queued_payload": _keys_minus(_queued_k, _ADD_110["queued_payload"]),
    "queued_thread": _keys_minus(_queued_k["thread"], _ADD_110["queued_thread"]),
    "verdict_payload": _keys_minus(_ev_payloads(_ev_k81, "stage.audit.verdict")[0], _ADD_110["verdict_payload"]),
    "judge_payload": _keys_minus(_ev_payloads(_ev_k81, "stage.audit.judge")[0], _ADD_110["judge_payload"]),
    "event_types": [t for t in _ev_k_types if t != "stage.models"],
}
_ks_diff = {k: {"extra": sorted(set(_ks_keysets[k]) - set(_GOLDEN_19[k])), "missing": sorted(set(_GOLDEN_19[k]) - set(_ks_keysets[k]))}
            for k in _GOLDEN_19 if _ks_keysets[k] != _GOLDEN_19[k]}
check("ADR-0081 (M.2) KILL-SWITCH (WITT_MODEL_GENERATION=g1-2026-08 + WITT_OPENAI_API=chat-completions + MIN_FAMILIES/LENSES 0 + "
      "LEDGER 0): el registro 1.10 MENOS las llaves aditivas declaradas tiene EXACTAMENTE el keyset del golden 1.9 medido en "
      "f57a3d3 — top-level (47), answer, audit, fila del panel, by_stage.{panel, synthesize_pass1, elicit_pass1, plan}, revision, "
      "plan.judgment.planner, plan.audit, epistemic_summary, run.state{queued} (+thread), stage.audit.verdict/judge y la secuencia "
      "de eventos sin stage.models",
      _ks_diff == {}, json.dumps(_ks_diff)[:700])
check("ADR-0081 (M.2) KILL-SWITCH valores f57a3d3: frozen.models.generation g1 (source 'env:WITT_MODEL_GENERATION'); answer.model y "
      "roles == defaults g1 (opus-4-8 en synth/planner/elicit/correctness); panel == los 4 asientos g1 en orden; topes g1 recibidos "
      "por la API falsa (2500 / 300 / 1200 plan); effort NO se envía a un modelo 'off' aunque WITT_ANTHROPIC_EFFORT=low (declarado); "
      "juez reproducibility por 'openai-chat-completions'; quorum.families_gating/lenses_gating False (kill-switch) y APPROVE; "
      "by_model[synth g1].in == 540 (400 plan + 130 síntesis+elicit + 10 juez correctness) == el golden",
      _rec_k81["models"]["generation"] == _G1 and _rec_k81["models"]["generation_source"] == "env:WITT_MODEL_GENERATION"
      and _rec_k81["answer"]["model"] == _g1d["synthesizer"]
      and _rec_k81["models"]["roles"]["synthesizer"]["model"] == _g1d["synthesizer"]
      and _rec_k81["models"]["roles"]["elicitation"]["model"] == _g1d["elicitation"]
      and _rec_k81["plan"]["judgment"]["planner"]["model"] == _g1d["planner"]
      and [r["reviewer"] for r in _rec_k81["audit"]["panel"]] == [_g1d["judge." + l] for l in models.LENSES]
      and [c["max_tokens"] for c in _calls_k if c["tool"] == "emit_answer"] == [_TOPES[_G1]["synthesizer"]] == [2500]
      and [c["max_tokens"] for c in _calls_k if c["tool"] == "emit_confidence"] == [_TOPES[_G1]["elicitation"]] == [300]
      and all(c["effort"] is None for c in _calls_k)
      and next(r for r in _rec_k81["audit"]["panel"] if r["lens"] == "reproducibility")["api"] == "openai-chat-completions"
      and _rec_k81["audit"]["quorum"]["families_gating"] is False and _rec_k81["audit"]["quorum"]["lenses_gating"] is False
      and _rec_k81["audit"]["verdict"] == "APPROVE"
      and _rec_k81["token_usage"]["by_model"][_g1d["synthesizer"]]["in"] == 540,
      json.dumps({"gen": _rec_k81["models"]["generation"], "panel": [r["reviewer"] for r in _rec_k81["audit"]["panel"]],
                  "calls": [(c["tool"], c["max_tokens"], c["effort"]) for c in _calls_k],
                  "by_model": _rec_k81["token_usage"]["by_model"]}))
check("ADR-0081 (C.4/B) el wrapper DECLARA lo que pidió y lo que pudo entregar: pass1 real lleva effort None + effort_source "
      "'not-sent (thinking_default off; env:WITT_ANTHROPIC_EFFORT=low)' bajo g1, y con la env vacía 'default-unset:…'; "
      "un caller/fake con la firma VIEJA (sin return_meta/effort) sigue válido: 2-tupla tolerada -> model_reported None, "
      "relation 'not-reported', effort_delivered False cuando se pidió effort y el caller no lo acepta",
      (lambda p_old, p_g1: (
          p_g1["effort"] is None and p_g1["effort_source"] == "not-sent (thinking_default off; env:WITT_ANTHROPIC_EFFORT=low)"
          and p_old["model_reported"] is None and p_old["relation"] == "not-reported"
          and p_old["model"] == _ROLE_SYNTH["model"] and p_old["model_source"] == _ROLE_SYNTH["source"]
          and p_old["effort"] == "low" and p_old["effort_delivered"] is False
          and p_old["elicitation_model"] == _ROLE_ELICIT["model"] and p_old["elicitation_relation"] == "not-reported"))(
          _with_env({"WITT_ANTHROPIC_EFFORT": "low"},
                    lambda: (setattr(composite_auditor, "_anthropic_tool_call",
                                     _mk_capture_api(_SYNTH_OUT_81, {"confidence": 0.8}, [])),
                             runs_mod._default_synthesizer("q", {"e": 1}, "pass1"))[1]),
          _with_env(_KS_ENV, lambda: (setattr(composite_auditor, "_anthropic_tool_call", _mk_api_81(reported_suffix="-x")),
                                      runs_mod._default_synthesizer("q", {"e": 1}, "pass1"))[1])))

# --- (A, corrector) id de familia DESCONOCIDA en un rol del PIPELINE: fail-loud SIN llamar (la regla del panel) -----------
_API_81.clear()
composite_auditor._anthropic_tool_call = _mk_api_81(reported_suffix="-x")


def _synth_unknown_family():
    try:
        runs_mod._default_synthesizer("q", {"e": 1}, "pass1")
        return None
    except Exception as e:   # se espera CallerError('unknown-family') — el fake no debe recibir ninguna llamada
        return e


_e_unk = _with_env({"WITT_MODEL_SYNTH": "llama-9"}, _synth_unknown_family)
check("ADR-0081 (A, corrector) WITT_MODEL_SYNTH=<id sin prefijo que case> en un rol del pipeline: runs._anthropic_call erra en voz "
      "alta con CallerError kind 'unknown-family' ANTES de construir la petición (0 llamadas a la API falsa) — la misma regla que "
      "_default_caller aplica a los asientos del panel, no el `else: anthropic` de f57a3d3",
      isinstance(_e_unk, composite_auditor.CallerError) and _e_unk.kind == "unknown-family" and _API_81 == []
      and "llama-9" in str(_e_unk), f"{type(_e_unk).__name__}: {_e_unk} calls={_API_81}")

# --- (D) juez OpenAI caído -> REVISE ESTRUCTURAL por familias, sin revisión, skipped_reason con el código -----------------
composite_auditor._anthropic_tool_call = _api_saved_81
_rid_e81, _rec_e81, _ev_e81 = _run80("ADR-0081 D: openai down", ["wt1a"], plan=True,
                                     panel=_stub_caller_factory({**ALL_A, "reproducibility": RuntimeError("openai down (smoke)")}))
_t_e81 = _ev_types(_ev_e81)
_vd_e = _ev_payloads(_ev_e81, "stage.audit.verdict")
_row_oai = next(r for r in _rec_e81["audit"]["panel"] if r["lens"] == "reproducibility")
check("ADR-0081 (D) juez OpenAI errored + 3 APPROVE Anthropic -> REVISE ESTRUCTURAL: n_valid 3 pero families_valid ['anthropic'] "
      "(1 < MIN_FAMILIES 2) -> panel_incomplete True, panel_incomplete_reasons ['families'], AUDIT_REJECTED; revision.performed False "
      "con skipped_reason 'panel_incomplete (families) — el REVISE es estructural (jueces caídos o sin diversidad), …' y SIN "
      "stage.revision.start; stage.audit.verdict lo dice; epistemic panel_n_families_valid 1; la fila errored lleva 2 intentos con "
      "error_kind (S2) y ran.panel[reproducibility] {reported null, not-reported, attempts 2}",
      _rec_e81["audit"]["verdict"] == "REVISE" and _rec_e81["audit"]["n_valid"] == 3
      and _rec_e81["audit"]["families_valid"] == ["anthropic"] and _rec_e81["audit"]["panel_incomplete"] is True
      and _rec_e81["audit"]["panel_incomplete_reasons"] == ["families"]
      and _rec_e81["decision_state"]["state"] == "AUDIT_REJECTED"
      and _rec_e81["revision"]["performed"] is False
      and _rec_e81["revision"]["skipped_reason"] == ("panel_incomplete (families) — el REVISE es estructural (jueces caídos o sin "
                                                     "diversidad), no un hallazgo sobre la respuesta; la revisión no aplica")
      and "stage.revision.start" not in _t_e81 and _t_e81.count("stage.audit.verdict") == 1
      and _vd_e[0]["panel_incomplete"] is True and _vd_e[0]["panel_incomplete_reasons"] == ["families"]
      and _vd_e[0]["n_families_valid"] == 1
      and app.get_run(_rid_e81, authorization=AUTH)["epistemic_summary"]["panel_n_families_valid"] == 1
      and _row_oai["status"] == "errored" and len(_row_oai["attempts"]) == 2
      and all("error_kind" in a for a in _row_oai["attempts"])
      and next(p for p in _rec_e81["models"]["ran"]["panel"] if p["lens"] == "reproducibility")
          == {"lens": "reproducibility", "reviewer": _row_oai["reviewer"], "reported": None, "relation": "not-reported",
              "api_used": _row_oai["api"], "attempts": 2}
      and "families_valid:1" in next(a for a in _rec_e81["agents_invoked"]
                                     if a["agent"] == "composite-auditor")["evidence_generated"],
      json.dumps({"reasons": _rec_e81["audit"].get("panel_incomplete_reasons"), "skipped": _rec_e81["revision"].get("skipped_reason"),
                  "kinds": [a.get("error_kind") for a in _row_oai["attempts"]]}))

# --- (D) revisión: audit_initial copia el cuórum; by_model del panel sobre DOS paneles ----------------------------------------
_rid_f81, _rec_f81, _ev_f81 = _run80("ADR-0081 F: revision cycle", ["wt1a"], synth=_synth_with_revision, plan=True,
                                     panel=_stub_caller_rounds([ALL_R, ALL_A]))
_ai_f = _rec_f81["audit_initial"]
_bp_f = _rec_f81["token_usage"]["by_stage"]["panel"]
check("ADR-0081 (D) con revisión: audit_initial copia ADEMÁS families_valid, n_families_valid, lenses_valid, n_lenses_valid, quorum "
      "(verdict inicial REVISE con quorum.ok True: fue hallazgo, no estructural); ambos stage.audit.verdict traen familias; "
      "by_stage.panel.by_model suma los DOS paneles (8 jueces: cada reviewer 20/10, Σ == 80/40 == panel); ran.panel refleja el "
      "panel FINAL (audit.panel)",
      _ai_f["verdict"] == "REVISE" and {"families_valid", "n_families_valid", "lenses_valid", "n_lenses_valid", "quorum"} <= set(_ai_f)
      and _ai_f["quorum"]["ok"] is True and _ai_f["n_families_valid"] == 2 and "panel_incomplete" not in _ai_f
      and _rec_f81["audit"]["verdict"] == "APPROVE"
      and all(v["n_families_valid"] == 2 for v in _ev_payloads(_ev_f81, "stage.audit.verdict"))
      and all(v == {"in": 20, "out": 10} for v in _bp_f["by_model"].values()) and len(_bp_f["by_model"]) == 4
      and sum(v["in"] for v in _bp_f["by_model"].values()) == _bp_f["in"] == 80
      and _rec_f81["usage_raw"]["panel_total"]["input_tokens"] == 80
      and len(_rec_f81["models"]["ran"]["panel"]) == 4,
      json.dumps({"audit_initial_keys": sorted(_ai_f), "by_model": _bp_f["by_model"]}))

# --- (F) run.state{queued} += run_no y thread.root_run_no — raíz / hijo / raíz VIRTUAL (padre pre-ADR-0079) ------------------
_q_root = next(e for e in _ev_a81 if e["type"] == "run.state" and e["payload"].get("state") == "queued")["payload"]
_view_root = app.get_run(_rid_a81, authorization=AUTH)
_rv_ch81 = app.create_run(app.RunBody(question="ADR-0081 F hijo", entities=["wt1a"], parent_run_id=_rid_a81), authorization=AUTH)
_q_ch = next(e for e in app.get_events(_rv_ch81["run_id"], after=0, authorization=AUTH)["events"]
             if e["type"] == "run.state" and e["payload"].get("state") == "queued")["payload"]
db.update_run(_rv_ch81["run_id"], state="cancelled")   # que el FIFO no la reclame
PRE_0081 = "pre0081" + "d" * 25
db.create_run(PRE_0081, "natalia", "pre-ADR parent (fila anterior al contrato)", ["wt1a"])
db.update_run(PRE_0081, state="awaiting_closure")
_rv_vch = app.create_run(app.RunBody(question="ADR-0081 F hijo de raíz virtual", entities=["wt1a"], parent_run_id=PRE_0081),
                         authorization=AUTH)
_q_vch = next(e for e in app.get_events(_rv_vch["run_id"], after=0, authorization=AUTH)["events"]
              if e["type"] == "run.state" and e["payload"].get("state") == "queued")["payload"]
db.update_run(_rv_vch["run_id"], state="cancelled")
_pre_no = db.get_run(PRE_0081)["run_no"]
check("ADR-0081 (F) run.state{queued} lleva run_no y thread.root_run_no desde la BD: raíz -> root_run_no == su run_no; hijo -> el "
      "run_no de la raíz; hijo de raíz VIRTUAL (padre pre-ADR-0079, thread_id NULL) -> el run_no del padre; == frozen.thread."
      "root_run_no y == RunView.root_run_no (S4 JOIN) — la MISMA verdad por tres puertas",
      _q_root["run_no"] == _view_root["run_no"] and _q_root["thread"]["root_run_no"] == _view_root["run_no"]
      and _rec_a81["thread"]["root_run_no"] == _view_root["run_no"]
      and _q_ch["run_no"] == _rv_ch81["run_no"] and _q_ch["thread"]["root_run_no"] == _view_root["run_no"]
      and _q_ch["thread"]["thread_id"] == _rid_a81
      and _q_vch["thread"]["root_run_no"] == _pre_no and _q_vch["thread"]["thread_id"] == PRE_0081
      and _view_root.get("root_run_no") == _view_root["run_no"]
      and app.get_run(_rv_vch["run_id"], authorization=AUTH).get("root_run_no") == _pre_no,
      json.dumps({"root": (_q_root["run_no"], _q_root["thread"]["root_run_no"]),
                  "child": (_q_ch["run_no"], _q_ch["thread"]["root_run_no"]),
                  "virtual": (_q_vch["run_no"], _q_vch["thread"]["root_run_no"], _pre_no)}))

# --- unidades: planner REAL (3-tupla) y stub (2-tupla) en build_plan; _usage_by_stage/_token_usage sin constante -------------
composite_auditor._anthropic_tool_call = _mk_api_81(reported_suffix="-20260915")
_API_81.clear()
_p_out, _p_usage, _p_meta = runs_mod._default_planner("q", ["wt1a"])
_plan_real = runs_mod.build_plan("q", ["wt1a"], planner=runs_mod._default_planner, history_rows=HIST_OK)
_plan_stub = runs_mod.build_plan("q", ["wt1a"], planner=_fake_planner_ok, history_rows=HIST_OK)
composite_auditor._anthropic_tool_call = _api_saved_81
check("ADR-0081 (B) _default_planner REAL devuelve (out, usage, meta) con model == rol planner, model_source 'default:g2…', "
      "model_reported '<pedido>-20260915', relation 'prefix', generation g2, tope 4000 pedido; build_plan con el planner real "
      "congela ese meta en judgment.planner; con planner stub (2-tupla) -> model = rol resuelto, model_reported null, "
      "relation 'not-reported' (nada se copia de una constante)",
      _p_meta["model"] == _ROLE_PLANNER["model"] and _p_meta["model_source"] == _ROLE_PLANNER["source"]
      and _p_meta["model_reported"] == _ROLE_PLANNER["model"] + "-20260915" and _p_meta["relation"] == "prefix"
      and _p_meta["generation"] == _G2 and _API_81 and _API_81[0]["tool"] == "emit_plan_judgment"
      and _API_81[0]["max_tokens"] == _TOPES[_G2]["planner"] == 4000
      and _plan_real["judgment"]["planner"]["model_reported"] == _ROLE_PLANNER["model"] + "-20260915"
      and _plan_real["judgment"]["planner"]["relation"] == "prefix"
      and _plan_stub["judgment"]["planner"]["model"] == _ROLE_PLANNER["model"]
      and _plan_stub["judgment"]["planner"]["model_reported"] is None
      and _plan_stub["judgment"]["planner"]["relation"] == "not-reported"
      and _plan_stub["judgment"]["planner"]["usage"] == {"input_tokens": 400, "output_tokens": 120},
      json.dumps({k: _p_meta[k] for k in ("model", "model_source", "model_reported", "relation")}))
_bs_u = runs_mod._usage_by_stage([("pass1", {"usage": {"input_tokens": 10, "output_tokens": 1}})], None,
                                 {"panel": [{"reviewer": "j1", "usage": {"input_tokens": 3, "output_tokens": 2}},
                                            {"reviewer": "j1", "usage": {"input_tokens": 4, "output_tokens": 1}},
                                            {"reviewer": "j2", "status": "errored"}]}, 0)
_tu_u = runs_mod._token_usage([("pass1", {"usage": {"input_tokens": 10, "output_tokens": 1}})], {"panel": []}, 0)
check("ADR-0081 (H) _usage_by_stage / _token_usage SIN constante: una pasada sin `model` deja by_stage.synthesize_pass1.model "
      "null DECLARADO (no una constante copiada) y sin model_source; by_model la atribuye a 'unknown-model' (sin precio -> "
      "missing_price_models); panel.by_model agrega por reviewer (j1 7/3) y un juez errored sin usage no aparece; Σ == panel",
      _bs_u["synthesize_pass1"] == {"in": 10, "out": 1, "model": None}
      and _bs_u["panel"] == {"in": 7, "out": 3, "by_model": {"j1": {"in": 7, "out": 3}}}
      and _tu_u["by_model"] == {"unknown-model": {"in": 10, "out": 1}} and _tu_u["missing_price_models"] == ["unknown-model"],
      json.dumps({"bs": _bs_u["synthesize_pass1"], "panel": _bs_u["panel"], "by_model": _tu_u["by_model"]}))
_extra = runs_mod.snapshot_extra()
_snap = models.snapshot(extra=_extra)
check("ADR-0081 (I/E) runs.snapshot_extra() cubre EXACTAMENTE models.EXTRA_FIELDS ({value, source}: contrato 1.10 desde "
      "runs.RENDER_CONTRACT_VERSION, competence.gate/search.harness/revision.cycle con fuente default-unset/env) -> el snapshot "
      "no deja ninguno en 'not-provided-by-caller'; _config_ledger_observe devuelve un dict con `state` y JAMÁS lanza (módulo de S5 "
      "presente o no); SYNTH_MODEL es alias derivado == resolve_role('synthesizer').model y PRICES_PER_MTOK_USD == models.prices()",
      set(_extra) == set(models.EXTRA_FIELDS)
      and all(set(v) == {"value", "source"} for v in _extra.values())
      and _extra["contract.render_contract_version"] == {"value": runs_mod.RENDER_CONTRACT_VERSION, "source": "runs.RENDER_CONTRACT_VERSION"}
      and all(_snap["fields"][f]["source"] != models.NOT_PROVIDED for f in models.EXTRA_FIELDS)
      and _snap["fields"]["contract.render_contract_version"]["value"] == runs_mod.RENDER_CONTRACT_VERSION
      and isinstance(runs_mod._config_ledger_observe(_snap), dict) and "state" in runs_mod._config_ledger_observe(_snap)
      and runs_mod.SYNTH_MODEL == models.resolve_role("synthesizer")["model"]
      and runs_mod.PRICES_PER_MTOK_USD == models.prices() and runs_mod.PRICES_AS_OF == models.PRICES_AS_OF,
      json.dumps({k: v for k, v in _extra.items()}))
composite_auditor._anthropic_tool_call = _api_saved_81

# --- S7 costuras (N) MEDIDAS: UNA identidad de configuración por corrida · UNA verdad para root_run_no -------------------
_sig_frozen = _rec_a81["models"]["panel_signature"]
_sig_stage = _sm_a81[0]["panel_signature"]
_sig_audit = _rec_a81["audit"]["panel_source"]["panel_signature"]
check("ADR-0081 (N) frozen.models.panel_signature == stage.models.panel_signature == audit.panel_source.panel_signature (la firma se "
      "calcula con los MISMOS 8 roles del snapshot — provenance_block(signature_roles=)); asientos iguales por tres puertas "
      "(frozen.models.ran.panel[].reviewer == audit.panel[].reviewer == stage.models.panel[].reviewer); audit.panel_origin "
      "'models.panel(directives)' (el panel salió de la tabla, no del llamador)",
      _sig_frozen == _sig_stage == _sig_audit
      and [p["reviewer"] for p in _rec_a81["models"]["ran"]["panel"]] == [r["reviewer"] for r in _rec_a81["audit"]["panel"]]
      == [m["reviewer"] for m in _sm_a81[0]["panel"]]
      and _rec_a81["audit"]["panel_origin"] == "models.panel(directives)",
      json.dumps({"frozen": _sig_frozen, "stage": _sig_stage, "audit": _sig_audit}))
_rows_all = db.list_runs(limit=1000)
_mism = [(r["run_id"][:8], r.get("root_run_no"), runs_mod._root_run_no(r)) for r in _rows_all
         if r.get("root_run_no") != runs_mod._root_run_no(r)]
check(f"ADR-0081 (N) db._list_select.root_run_no (JOIN a la raíz, S4) == runs._root_run_no (la regla de frozen.thread.root_run_no) "
      f"en TODAS las corridas del gate ({len(_rows_all)}: raíces, hijos, hijos de raíz VIRTUAL y pre-ADR null == null); la llave "
      f"viaja en cada renglón de la lista",
      bool(_rows_all) and not _mism and all("root_run_no" in r for r in _rows_all), json.dumps(_mism[:5]))

# =====================================================================================================
# ADR-0082 (C5) — EL CONSEJO DE CRITERIO EN LA CORRIDA: 17 miembros FAKEADOS (válidos, duplicados, caídos, con ids
# alucinados, fuera de vocabulario, con campos prohibidos, tool equivocado, not-applicable), ronda 1 + agregación por
# código (council.run_round/aggregate_r1) → ledger humano (council.apply_ledger_decisions y la forma HTTP de app con
# decisions[]) → copia F.4 (runs.new_run(council_json=)) → execute_run(council_caller=fake): r2 ANTES de la compuerta,
# componente cg-4, directivas → familia directive-only ENTRA → r3 sobre dueños → cobertura post; kill-switch = forma 1.10 +
# excepciones (L.2); aporto → covered-by-attestation y fuga → inadmisible; by_stage suma; agents_invoked council:17/17;
# cancelación a media ronda. TODO dentro del bloque offline (urlopen bloqueado y contado; mcp_cache intacto).
# =====================================================================================================
import threading as _threading  # noqa: E402
from lib import agent_matrix as _am, catalog_cards as _cc, council as _council  # noqa: E402
import competence as _cg82  # noqa: E402

_C_MEMBERS = _am.council_members({})
_C_CALLS = []
_C_R1_OUT = {
    "cross-modality-integrator": {"applicable": True, "requirements": [
        {"gap": "protein interaction partners of wt1a in the pronephros", "evidence_kind": "interaction",
         "source_family": "string", "query_en": "wt1a protein interaction partners", "entities": ["wt1a"],
         "acceptance_test": ">=1 STRING partner with score", "priority": "must"}]},
    "literature-monitor": {"applicable": True, "requirements": [
        {"gap": "podocyte-glomerulus expression of wt1a", "evidence_kind": "paper", "source_family": "pubmed",
         "query_en": "wt1a podocyte glomerulus zebrafish", "entities": ["wt1a"],
         "acceptance_test": ">=1 paper with in situ", "priority": "must"}]},
    "causal-pruner": {"applicable": True, "requirements": [
        {"gap": "loss-of-function pronephros phenotype of wt1a", "evidence_kind": "phenotype", "source_family": "zfin",
         "query_en": "wt1a knockdown pronephros phenotype", "entities": ["wt1a"],
         "acceptance_test": ">=1 ZFIN phenotype statement", "priority": "must"}]},
    "cross-field-bridge-agent": {"applicable": True, "requirements": [
        {"gap": "public datasets with wt1a expression", "evidence_kind": "dataset", "source_family": "geo",
         "query_en": "wt1a zebrafish pronephros dataset", "entities": ["wt1a"],
         "acceptance_test": ">=1 GEO series", "priority": "must"}]},      # exploratorio → must se degrada a should
    "hypothesis-generator": {"applicable": True, "requirements": [
        {"gap": "web grey literature", "evidence_kind": "web", "source_family": "web",
         "query_en": "wt1a pronephros web", "entities": ["wt1a"], "acceptance_test": "any", "priority": "must"}]},  # unsatisfiable (E1)
    "regulatory-ethics-advisor": {"applicable": True, "flags": [
        {"kind": "animal-work", "statement": "zebrafish morpholino work needs the animal-work protocol on file"}]},
    "scrna-seq-analyst": {"applicable": False, "not_applicable_reason": "no single-cell question here"},
    # fuera de vocabulario / campos prohibidos / duplicado: la validación por CÓDIGO los descarta y cuenta
    "spatial-omics-analyst": {"applicable": True, "direct_answer": "wt1a marks it", "confidence": 0.9, "requirements": [
        {"gap": "off-vocabulary family", "evidence_kind": "paper", "source_family": "pubmed-central",
         "query_en": "wt1a", "entities": ["wt1a"], "acceptance_test": "x", "priority": "must"},
        {"gap": "literature on wt1a pronephros (dup)", "evidence_kind": "paper", "source_family": "europepmc",
         "query_en": "wt1a pronephros zebrafish", "entities": ["wt1a"], "acceptance_test": ">=1 paper", "priority": "should"}]},
}
_C_R1_DEFAULT = {"applicable": True, "requirements": [
    {"gap": "literature on wt1a pronephros", "evidence_kind": "paper", "source_family": "europepmc",
     "query_en": "wt1a pronephros zebrafish", "entities": ["wt1a"], "acceptance_test": ">=1 paper", "priority": "should"}],
    "notes_for_human": "shared literature requirement"}


def _c_body(user_text):
    head = user_text.split("\n\nEVIDENCE (", 1)[0]
    return json.loads(head.split("\n\n", 1)[1])


def _mk_council_caller(fail_r2=(), halluc_r2=(), uncovered_fams=(), cancel_after=None, run_box=None, wrong_tool_r1=()):
    """caller(request) -> (tool_input, usage, meta) — 17 fakes deterministas, cero red. r1: la salida de _C_R1_OUT (o la
    compartida); r2/r3: un juicio por requisito PROPIO (parseado del user_text) citando el primer evidence_id disponible;
    `uncovered_fams` → 'uncovered' + search_directive en r2 (en r3 vuelve 'covered' citando el ítem nuevo); `halluc_r2` →
    evidence_ids ['PMID:999'] (∉ bundle → voto ANULADO); `fail_r2` → CallerError http-529; `cancel_after` → request_cancel
    en la k-ésima llamada. Caché: el primer despacho de cada ronda ESCRIBE 2400, los demás LEEN 2400 (usage medido)."""
    seen_round = {}

    def caller(request):
        agent, rnd = request["agent"], request["round"]
        _C_CALLS.append({"agent": agent, "round": rnd, "tool": request["tool"], "thread": _threading.get_ident(),
                         "tools_sha": request["tools_sha"], "tool_choice": request["tool_choice"]["name"],
                         "system_kind": type(request["system"]).__name__, "model": request["model"]})
        if cancel_after is not None and run_box and len(_C_CALLS) >= cancel_after and not run_box.get("cancelled"):
            run_box["cancelled"] = True          # one-shot: los fakes corren en hilos y len() no es atómico entre ellos
            db.request_cancel(run_box["run_id"])
        first = seen_round.setdefault(rnd, agent) == agent
        usage = {"input_tokens": 1000, "output_tokens": 200,
                 "cache_creation_input_tokens": 2400 if first else 0, "cache_read_input_tokens": 0 if first else 2400}
        meta = {"model_reported": (request["model"] or "m") + "-20260915", "attempts": 1, "stop_reason": "tool_use", "api": "fake"}
        if rnd == "r2" and agent in fail_r2:
            raise composite_auditor.CallerError("http-529", "overloaded (simulated)", usage={"input_tokens": 1000, "output_tokens": 0})
        if rnd == "r1":
            if agent in wrong_tool_r1:
                return {"judgments": []}, usage, meta        # tool equivocado para la ronda → fila errored wrong-tool
            return json.loads(json.dumps(_C_R1_OUT.get(agent, _C_R1_DEFAULT))), usage, meta
        body = _c_body(request["user_text"])
        ids = list(body.get("evidence_ids_available") or [])
        judg = []
        for r in body.get("your_requirements") or []:
            rid = r["requirement_id"]
            if agent in halluc_r2:
                judg.append({"requirement_id": rid, "coverage": "covered", "evidence_ids": ["PMID:999"], "rationale": "fake id"})
            elif rnd == "r2" and r.get("source_family") in uncovered_fams:
                judg.append({"requirement_id": rid, "coverage": "uncovered", "evidence_ids": [],
                             "rationale": "no interaction evidence in the bundle",
                             "search_directive": {"query_en": "wt1a STRING partners zebrafish", "entities": ["wt1a"]}})
            elif rnd == "r3":
                new = [i for i in ids if str(i).startswith("STRING") or "string" in str(i).lower()] or ids[-1:]
                judg.append({"requirement_id": rid, "coverage": "covered", "evidence_ids": new[:1], "rationale": "directed search brought it"})
            else:
                judg.append({"requirement_id": rid, "coverage": "covered", "evidence_ids": ids[:1], "rationale": "DI chunk covers it"})
        return {"judgments": judg}, usage, meta
    return caller


_C_CFG = _council.config()
_c_ctx1 = {"question": "does wt1a mark the pronephros?", "entities": ["wt1a"],
           "judgment": {"work_type": "QA", "route": "evidence-run", "niches": ["N3"], "state": "declared"}}
_C_R1 = _council.run_round(_C_MEMBERS, "r1", _c_ctx1, caller=_mk_council_caller(wrong_tool_r1=("histology-reviewer",)),
                           cfg=_C_CFG, phase="plan")
_C_R1["prior_observations"] = {"n": 0, "kinds": [], "state": "empty-corpus"}
_C_AGG = _council.aggregate_r1(_C_R1, members=_C_MEMBERS, cfg=_C_CFG)
_c_by_fam = {}
for _r in _C_AGG["requirements"]:
    _c_by_fam.setdefault(_r["source_family"], _r)
_c_rid = {f: _c_by_fam[f]["requirement_id"] for f in _c_by_fam}
_c_hist = next(m for m in _C_R1["members"] if m["agent"] == "histology-reviewer")
_c_spat = next(m for m in _C_R1["members"] if m["agent"] == "spatial-omics-analyst")
check("ADR-0082 (C.3/C.4) ronda 1 FAKEADA (17, cero red): applicable con 16/17 válidos (histology-reviewer 'wrong-tool' → errored, "
      "la ronda sigue); scrna-seq-analyst not-applicable CUENTA como válido; spatial-omics: 'pubmed-central' fuera de vocabulario "
      "→ ítem descartado y crudo en off_vocabulary, direct_answer/confidence → dropped_fields (no viajan); agregación: la "
      "literatura pedida por 9 miembros es UN requisito (n_requested_by 9, variants [] — misma query), string/pubmed/zfin must, "
      "zfin hard_rule_gate (causal-pruner), geo exploratorio must→should con priority_downgraded_from, web unsatisfiable "
      "(n_unsatisfiable 1), 1 bandera animal-work con gate humano; membros barajados → aggregation_sha idéntico",
      _C_R1["state"] == "applicable" and _C_R1["n_valid"] == 16 and _C_R1["n_errored"] == 1
      and _c_hist["status"] == "errored" and _c_hist["error_kind"] == "wrong-tool"
      and _c_spat["status"] == "ok" and _c_spat["validation"]["off_vocabulary"][0]["value"] == "pubmed-central"
      and set(_c_spat["validation"]["dropped_fields"]) >= {"direct_answer", "confidence"}
      and set(_c_rid) == {"europepmc", "string", "pubmed", "zfin", "geo", "web"}
      and _c_by_fam["europepmc"]["n_requested_by"] == 9 and _c_by_fam["europepmc"]["n_members"] == 17
      and _c_by_fam["string"]["priority"] == "must" and _c_by_fam["zfin"]["hard_rule_gate"] is True
      and _c_by_fam["geo"]["priority"] == "should" and _c_by_fam["geo"]["priority_downgraded_from"] == "must"
      and _c_by_fam["web"]["harness_state"].startswith("unsatisfiable-by-harness") and _C_AGG["n_unsatisfiable"] == 1
      and _C_AGG["n_hard_rule"] == 1 and _C_AGG["flags"][0]["kind"] == "animal-work" and _C_AGG["flags"][0]["gate"] == "human"
      and _council.aggregate_r1({**_C_R1, "members": list(reversed(_C_R1["members"]))}, members=_C_MEMBERS,
                                cfg=_C_CFG)["aggregation_sha"] == _C_AGG["aggregation_sha"]
      and all(c["tools_sha"] == _council.TOOLS_SHA and c["system_kind"] == "list" for c in _C_CALLS),
      json.dumps({"rids": _c_rid, "n_req": _C_AGG["n_requirements"], "hist": _c_hist["error_kind"],
                  "spat": _c_spat["validation"]["dropped_fields"]}))

_C_AT = "2026-09-15T20:00:00+00:00"
_C_DECISIONS = [{"requirement_id": _c_rid["zfin"], "decision": "keep"},                      # hard-rule: decisión EXPLÍCITA
                {"requirement_id": _c_rid["geo"], "decision": "discard", "reason": "datasets fuera del alcance del turno"},
                {"requirement_id": _c_rid["pubmed"], "decision": "aporto",
                 "attested_text": "Our lab confirmed podocyte wt1a expression in situ (notebook 2026-08, see PMID:31415926)."}]
_C_LEDGER = _council.apply_ledger_decisions(_C_AGG, decisions=_C_DECISIONS, approve=True, decided_by="natalia",
                                            decided_at=_C_AT, knowledge_now="We already know wt1a marks the pronephros.")
_c_undecided = _council.apply_ledger_decisions(_C_AGG, decisions=[], approve=True, decided_by="natalia", decided_at=_C_AT)
check("ADR-0082 (F.1/§7.1) ledger por CÓDIGO: approve con el must de causal-pruner (hard_rule) SIN decidir → state 'draft' + "
      "errors.hard_rule_requirements_undecided [zfin] (ningún default lo toma); con keep explícito + 1 discard con razón + 1 "
      "aporto atestiguado → 'approved', los pending restantes 'default-keep' (europepmc, string, web), n_kept 4 / n_discarded 1 / "
      "n_attested 1, knowledge_now clase 'attested'",
      _c_undecided["state"] == "draft" and _c_undecided["errors"]["hard_rule_requirements_undecided"] == [_c_rid["zfin"]]
      and _C_LEDGER["state"] == "approved" and _C_LEDGER["n_kept"] == 4 and _C_LEDGER["n_discarded"] == 1
      and _C_LEDGER["n_attested"] == 1 and _C_LEDGER["n_pending"] == 0
      and next(r for r in _C_LEDGER["requirements"] if r["requirement_id"] == _c_rid["europepmc"])["decided_by"] == "default-keep"
      and _C_LEDGER["knowledge_now"]["class"] == "attested",
      json.dumps({k: _C_LEDGER[k] for k in ("state", "n_kept", "n_discarded", "n_attested", "n_pending")}))


def _c_app_ledger(ledger):
    """La forma HTTP del ledger que app (C6) persiste: decisions[] por requirement_id + knowledge_now + approved_by…"""
    decs = []
    for r in ledger["requirements"]:
        d = {"requirement_id": r["requirement_id"], "decision": r["decision"], "decided_by": r["decided_by"],
             "decided_at": r["decided_at"], "hard_rule_gate": bool(r.get("hard_rule_gate")), "priority": r.get("priority")}
        if r.get("decision_reason"):
            d["reason"] = r["decision_reason"]
        if r.get("attested_text"):
            d.update(attested_text=r["attested_text"], attested_chars=len(r["attested_text"]), attested_class="attested")
        decs.append(d)
    return {"state": ledger["state"], "plan_id": "plan-c5", "council_state": "applicable", "decisions": decs,
            "n_requirements": len(decs), "knowledge_now": ledger["knowledge_now"], "approved_by": "natalia",
            "approved_at": _C_AT, "approved_by_is_author": True, "source": "POST /plans/{plan_id}/council/ledger (fake)"}


def _c_json(ledger, plan_id="plan-c5"):
    r1 = {**_C_AGG, "rounds": [_C_R1], "members": list(_C_MEMBERS), "full_council": False, "catalog_sha": _cc.CATALOG_SHA,
          "n_members": 17, "membership_version": _am.MEMBERSHIP_VERSION, "model": _C_R1["model"]}
    return {"plan_id": plan_id, "r1_state": "applicable", "r1": r1, "ledger": ledger,
            "membership_version": _am.MEMBERSHIP_VERSION, "n_members": 17, "members": list(_C_MEMBERS), "full_council": False,
            "catalog_sha": _cc.CATALOG_SHA, "membership_source": "plan.council (frozen at r1)", "composed_at": _C_AT,
            "source": "plans.council_json + plans.council_ledger_json (copied at enqueue)"}


_C_SYNTH_SEEN = []


def _mk_synth82(answer_text, conf_by_pass, cited):
    """Sintetizador stub con la firma NUEVA (thread_context=, human_attestations=): registra qué llaves hermanas recibió."""
    def _s(question, evidence, pass_label, thread_context=None, human_attestations=None):
        _C_SYNTH_SEEN.append({"pass": pass_label, "human_attestations": human_attestations, "thread_context": thread_context,
                              "evidence_has_attestations": "human_attestations" in (evidence or {})})
        return _mk_synth(conf_by_pass, extra={"direct_answer": answer_text, "evidence_cited": cited})(question, evidence, pass_label)
    return _s


_C_CITED_OK = [{"kind": "di-chunk", "id": "CORPUS-2026-0003#c000"}, {"kind": "di-record", "id": "CORPUS-2026-0001"}]
_C_ANSWER = "wt1a (ENSDARG00000031420) marks the zebrafish pronephros."
_C_STRING_EL = {"partner": "wt1b", "score": 0.91, "evidence_id": "STRING:7955.wt1a-wt1b", "statement": "wt1a interacts with wt1b (STRING 0.91)",
                "url": "https://string-db.org/", "identifier_provenance": "string-api"}


def _run82(question, cj, synth=None, council_caller=None, env=None, plan=True, entities=("wt1a",), string_found=False,
           cancel_after=None):
    saved = {k: os.environ.get(k) for k in (env or {})}
    for k, v in (env or {}).items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    try:
        _sources_found()
        if string_found:
            _sh._TOOL_CACHE["string"] = (_fake_l0("string", "success", [_C_STRING_EL], list_key="partners"), "injected", None)
        plan_obj = (runs_mod.build_plan(question, list(entities), planner=_fake_planner_ok, history_rows=HIST_OK) if plan else None)
        box = {}
        rid = runs_mod.new_run("natalia", question, list(entities),
                               plan_json=json.dumps(plan_obj, default=str) if plan_obj else None,
                               council_json=json.dumps(cj, ensure_ascii=False, default=str) if cj else None)
        box["run_id"] = rid
        caller = council_caller if council_caller is not None else _mk_council_caller()
        if cancel_after is not None:
            caller = _mk_council_caller(cancel_after=cancel_after, run_box=box)
        claimed = db.claim_next_queued(worker_id="run-worker-adr0082")
        assert claimed and claimed["run_id"] == rid, "FIFO: la corrida reclamada debe ser la esperada"
        runs_mod.execute_run(claimed, synthesizer=synth or _mk_synth82(_C_ANSWER, {"pass1": 0.8, "pass2": 0.85}, _C_CITED_OK),
                             panel_caller=_stub_caller_factory(ALL_A), council_caller=caller)
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    row = db.get_run(rid)
    frozen = json.loads(row["frozen_record_json"]) if row.get("frozen_record_json") else None
    return rid, frozen, app.get_events(rid, after=0, authorization=AUTH)["events"], row


# --- (a) consejo COMPLETO: 17 ok en r2, 0 must sin cubrir → competente, SIN ronda de búsqueda; ledger en forma HTTP (app) --
_C_CALLS.clear(); _C_SYNTH_SEEN.clear()
_rid_ca, _rec_ca, _ev_ca, _row_ca = _run82("ADR-0082 a: does wt1a mark the pronephros?", _c_json(_c_app_ledger(_C_LEDGER)))
_t_ca = _ev_types(_ev_ca)
_cn_a = _rec_ca["council"]
_r2_a = next(r for r in _cn_a["rounds"] if r["round"] == "r2")
_stages_ca = [t for t in _t_ca if t.startswith("stage.")]
check("ADR-0082 (F.4) runs.new_run(council_json=) PERSISTE la copia (db.create_run council_json, C4) y run.state{queued}.council "
      "{ledger_present True, n_kept 4, n_hard_rule 1, r1_state 'applicable', persisted True}; el ledger HTTP (decisions[]) se FUSIONA "
      "con r1.requirements por requirement_id (council_ledger_from) → frozen.council.ledger con decisiones, decided_by y "
      "attested_text (≤600), knowledge_now {present True}",
      _row_ca.get("council_json") and json.loads(_row_ca["council_json"])["plan_id"] == "plan-c5"
      and next(e for e in _ev_ca if e["type"] == "run.state" and e["payload"]["state"] == "queued")["payload"]["council"]
          == {"ledger_present": True, "ledger_state": "approved", "n_kept": 4, "n_hard_rule": 1, "r1_state": "applicable",
              "plan_id": "plan-c5", "n_members": 17, "persisted": True}
      and _cn_a["ledger"]["state"] == "approved" and _cn_a["ledger"]["n_kept"] == 4 and _cn_a["ledger"]["n_attested"] == 1
      and _cn_a["ledger"]["requirements_source"].startswith("r1.requirements ⨝ ledger.decisions")
      and next(r for r in _cn_a["ledger"]["requirements"] if r["requirement_id"] == _c_rid["pubmed"])["attested_text"].startswith("Our lab")
      and _cn_a["ledger"]["knowledge_now"]["present"] is True and _cn_a["ledger"]["approved_by_is_author"] is True,
      json.dumps(next(e for e in _ev_ca if e["type"] == "run.state")["payload"].get("council")))
check("ADR-0082 (G.1) orden de la traza: stage.models → stage.plan{council_state 'applicable'} → stage.council.ledger → … → "
      "gate{pass1} → stage.council.round{r2, coverage, run} con 12 stage.council.member 'start' + 12 'done' (== n_invoked; "
      "emitidos desde el hilo orquestador) → stage.council.coverage{pre-search} → stage.competence → NI search.plan NI pass2 "
      "(competente); 12 llamadas al fake en r2 — SÓLO los miembros con ≥1 requisito kept propio (literature-monitor → aporto, "
      "cross-field → discard, regulatory/scrna/histology sin requisitos → not-invoked, cero llamadas) — 0 en r1 (copiada del plan); "
      "pass1 gate ANTES de r2",
      _stages_ca[:3] == ["stage.models", "stage.plan", "stage.council.ledger"]
      and _ev_payloads(_ev_ca, "stage.plan")[0]["council_state"] == "applicable"
      and _t_ca.index("stage.deterministic_gate") < _t_ca.index("stage.council.round") < _t_ca.index("stage.council.coverage")
      < _t_ca.index("stage.competence")
      and sum(1 for e in _ev_ca if e["type"] == "stage.council.member" and e["payload"]["phase"] == "start") == _r2_a["n_invoked"]
      and sum(1 for e in _ev_ca if e["type"] == "stage.council.member" and e["payload"]["phase"] == "done") == _r2_a["n_invoked"]
      and all(e["agent"] == "council" for e in _ev_ca if e["type"].startswith("stage.council."))
      and _r2_a["events"]["emitted_from"] == "orchestrator-thread"
      and "stage.search.plan" not in _t_ca and "stage.synthesize.pass2" not in _t_ca
      and [c["round"] for c in _C_CALLS] == ["r2"] * len(_C_CALLS) and len(_C_CALLS) == _r2_a["n_invoked"]
      and all(c["tool_choice"] == "emit_coverage_judgment" for c in _C_CALLS),
      json.dumps({"stages": _stages_ca[:8], "n_calls": len(_C_CALLS), "n_invoked": _r2_a["n_invoked"]}))
_cov_a = _cn_a["coverage"]["pre_search"]
_comp_a = _rec_ca["competence"]["components"]["council_uncovered_must"]
check("ADR-0082 (C.5/G.2) cobertura pre-búsqueda JUZGADA: must_total 4 (string, pubmed, zfin, web) → must_attested 1 (pubmed "
      "aporto → 'covered-by-attestation'), must_unsatisfiable 1 (web, NO gatea — E1), must_gateable 2 ambos 'covered' → "
      "must_uncovered 0; geo discard → 'discarded'; componente cg-4 {state 'checked', value True, gating True} DENTRO de conjunction "
      "→ competent True; frozen.council.state 'applicable', must_uncovered 0 (0 medido ≠ null); directives_state 'none (all must "
      "covered)'; post_search 'not-run (search not triggered)'",
      _cov_a["state"] == "judged" and _cov_a["must_total"] == 4 and _cov_a["must_attested"] == 1
      and _cov_a["must_unsatisfiable"] == 1 and _cov_a["must_gateable"] == 2 and _cov_a["must_uncovered"] == 0
      and {b["requirement_id"]: b["coverage_final"] for b in _cov_a["by_requirement"]}[_c_rid["pubmed"]] == "covered-by-attestation"
      and {b["requirement_id"]: b["coverage_final"] for b in _cov_a["by_requirement"]}[_c_rid["geo"]] == "discarded"
      and _comp_a["state"] == "checked" and _comp_a["value"] is True and _comp_a["gating"] is True
      and _comp_a["must_uncovered"] == 0 and _comp_a["must_unsatisfiable"] == 1
      and "council_uncovered_must" in _rec_ca["competence"]["conjunction"] and _rec_ca["competence"]["competent"] is True
      and _rec_ca["competence"]["module_version"] == "cg-4"
      and _cn_a["state"] == "applicable" and _cn_a["must_uncovered"] == 0
      and _cn_a["directives_state"] == "none (all must covered)"
      and _cn_a["coverage"]["post_search"]["state"] == "not-run (search not triggered)"
      and _cn_a["coverage"]["after_search"]["state"] == "not-run (no search ledger)",
      json.dumps({k: _cov_a[k] for k in ("must_total", "must_attested", "must_unsatisfiable", "must_gateable", "must_uncovered")}))
check("ADR-0082 (J) frozen.council íntegro: module 'council-1', membership cm-1 CONGELADA del plan (n_members 17, members 17, "
      "membership_source 'plan.council (frozen at r1)'), catalog_sha == catalog_cards.CATALOG_SHA == r1 → plan_catalog_matches_run "
      "True, rules_sha/tools_sha, model {requested opus por tabla, effort 'medium' pinneado y ENVIADO (adaptive)}, rounds [r1 "
      "COPIADA (copied_from_plan_id, phase plan, usage con caché) + r2 medida (17 miembros con usage/status/system_sha/card_sha)], "
      "cache {enabled, ttl 5m, r2 creation 2400 read 26400 (1 escritura + 11 lecturas), hit_ratio_r2 medido}, vocabulary == council.council_vocabulary(), "
      "decided_by 'code (council.aggregate_*)', kill_switch enabled True, index state declarado",
      _cn_a["module_version"] == "council-1" and _cn_a["membership_version"] == "cm-1" and _cn_a["n_members"] == 17
      and _cn_a["members"] == _C_MEMBERS and _cn_a["membership_source"] == "plan.council (frozen at r1)"
      and _cn_a["catalog_sha"] == _cc.CATALOG_SHA == _cn_a["plan_catalog_sha"] and _cn_a["plan_catalog_matches_run"] is True
      and _cn_a["rules_sha"] == _council.RULES_SHA and _cn_a["tools_sha"] == _council.TOOLS_SHA
      and _cn_a["model"]["requested"] == models.resolve_role("council")["model"] and _cn_a["model"]["effort_pinned"] == "medium"
      and _cn_a["model"]["effort"] == "medium"
      and [r["round"] for r in _cn_a["rounds"]] == ["r1", "r2"] and _cn_a["rounds"][0]["copied_from_plan_id"] == "plan-c5"
      and _cn_a["rounds"][0]["phase"] == "plan" and _r2_a["phase"] == "run" and len(_r2_a["members"]) == 17
      and all(m["card_sha"] and m["system_sha"] for m in _r2_a["members"] if m["status"] == "ok")
      and _cn_a["cache"]["enabled"] is True and _cn_a["cache"]["ttl"] == "5m"
      and _cn_a["cache"]["r2"] == {"creation": 2400, "read": 2400 * 11} and _cn_a["cache"]["hit_ratio_r2"] == round(11 / 12, 4)
      and _cn_a["vocabulary"] == runs_mod.council_vocabulary_full() and "competence_component_states" in _cn_a["vocabulary"]
      and _cn_a["vocabulary"]["usage_stage_states"]["exact"] == list(runs_mod.COUNCIL_USAGE_STAGE_STATES_EXACT)
      and _cn_a["decided_by"] == "code (council.aggregate_*)"
      and _cn_a["kill_switch"]["enabled"] is True and "state" in _cn_a["index"]
      and _rec_ca["render_contract_version"] == runs_mod.RENDER_CONTRACT_VERSION == "1.13",   # ADR-0084: 1.13 apila sobre 1.12
      json.dumps({"cache": _cn_a["cache"], "model": _cn_a["model"]}, default=str)[:400])
_tu_a = _rec_ca["token_usage"]
_cm_a = _cn_a["model"]["requested"]
_r1_usage = _C_R1["usage"]
check("ADR-0082 (H) token_usage: by_stage.council_r1 COPIADA del plan (state 'copied-from-plan_json', in/out/cache == "
      "runs.council_json.r1.rounds[0].usage, source 'plan_json (spent BEFORE enqueue; plan_id plan-c5)'), council_r2 'measured' "
      "(12×1000 in, 12×200 out, cache creation 2400 / read 26400, n_invoked 12 de 17, n_calls 12), council_r3 'not-run (…)' in/out null; by_model[opus] "
      "gana cache_creation/cache_read; _sum == by_model (by_stage_sum_matches_by_model) y cache_sum_matches_by_model True; "
      "input_tokens_total = input + creation + read; USD > el mismo gasto sin caché (multiplicadores publicados aplicados, cache."
      "priced True); council_judgment aparte con usd_projected",
      _tu_a["by_stage"]["council_r1"]["state"] == "copied-from-plan_json"
      and _tu_a["by_stage"]["council_r1"]["in"] == _r1_usage["in"] and _tu_a["by_stage"]["council_r1"]["cache_read"] == _r1_usage["cache_read"]
      and _tu_a["by_stage"]["council_r1"]["source"] == "plan_json (spent BEFORE enqueue; plan_id plan-c5)"
      and _tu_a["by_stage"]["council_r2"] == {"in": 12000, "out": 2400, "cache_creation": 2400, "cache_read": 26400,
                                               "n_members": 17, "n_invoked": 12, "n_calls": 12, "model": _cm_a,
                                               "model_source": _cn_a["model"]["source"], "state": "measured"}
      and _tu_a["by_stage"]["council_r3"]["in"] is None and _tu_a["by_stage"]["council_r3"]["state"].startswith("not-run (")
      and _tu_a["by_model"][_cm_a]["cache_creation"] == 2400 + _r1_usage["cache_creation"]
      and _tu_a["by_model"][_cm_a]["cache_read"] == 26400 + _r1_usage["cache_read"]
      and _tu_a["by_stage_sum_matches_by_model"] is True and _tu_a["cache_sum_matches_by_model"] is True
      and _tu_a["input_tokens_total"] == _tu_a["input_tokens"] + _tu_a["cache"]["creation_input_tokens"] + _tu_a["cache"]["read_input_tokens"]
      and _tu_a["cache"]["priced"] is True and _tu_a["cache"]["usd_projected"] > 0
      and _tu_a["cache"]["multipliers"] == models.CACHE_MULTIPLIERS and _tu_a["cache"]["write_multiplier_key"] == "write_5m"
      and _tu_a["estimated_cost_usd"] > sum((m["in"] * models.prices()[k][0] + m["out"] * models.prices()[k][1]) / 1e6
                                            for k, m in _tu_a["by_model"].items() if k in models.prices())
      and _tu_a["council_judgment"]["model"] == _cm_a and _tu_a["council_judgment"]["usd_projected"] > 0
      and _tu_a["council_judgment"]["rounds"] == ["council_r1", "council_r2"] and "prompt-cache" in _tu_a["cost_class"],
      json.dumps({"r1": _tu_a["by_stage"]["council_r1"], "r2": _tu_a["by_stage"]["council_r2"], "cache": _tu_a["cache"]}, default=str)[:600])
_ai_a = {a["agent"]: a for a in _rec_ca["agents_invoked"]}
_ops_row = _ai_a[runs_mod.COUNCIL_OPERATIVES_ROW]
check("ADR-0082 (G.7) agents_invoked: fila agregada '(consejo de criterio — cm-1)' invoked 'council:12/17' con evidence r1:15/17 "
      "(n_ok de r1: 15 ok + 1 not-applicable + 1 errored), r2:12/17, requirements:4, must_uncovered:0, catalog_sha:<16>; 17 filas por "
      "miembro 'invoked' (los 17 fueron despachados en r1 — el JOB del plan; histology-reviewer TAMBIÉN: "
      "'errored:wrong-tool (r1)' en su evidence; causal-pruner 'requirements:1'); los 8 operativos en UNA fila not-applicable por "
      "categoría; sustrato en UNA fila con su estado real; ningún miembro 'skipped-ad-hoc'; hypothesis-generator/causal-pruner "
      "(aplicables según el planner) son filas del consejo, no ad-hoc",
      _ai_a[runs_mod.COUNCIL_AGENT_ROW]["status"] == "invoked" and _ai_a[runs_mod.COUNCIL_AGENT_ROW]["invocation_id"] == "council:12/17"
      and {"r1:15/17", "r2:12/17", "requirements:4", "must_uncovered:0"} <= set(_ai_a[runs_mod.COUNCIL_AGENT_ROW]["evidence_generated"])
      and _ai_a["literature-monitor"]["invocation_id"] == "council:literature-monitor:r1"
      and any(e.startswith("not-invoked (r2)") for e in _ai_a["literature-monitor"]["evidence_generated"])
      and all(_ai_a[m]["status"] == "invoked" for m in _C_MEMBERS)
      and any(e.startswith("errored:wrong-tool") for e in _ai_a["histology-reviewer"]["evidence_generated"])
      and "requirements:1" in _ai_a["causal-pruner"]["evidence_generated"]
      and _ai_a["causal-pruner"]["invocation_id"] == "council:causal-pruner:r1+r2"
      and _ops_row["status"] == "not-applicable" and len(_ops_row["evidence_generated"]) == 8
      and _ai_a[runs_mod.COUNCIL_SUBSTRATE_ROW]["status"] == "not-applicable"
      and not any(a["status"] == "skipped-ad-hoc" for a in _rec_ca["agents_invoked"]),
      json.dumps([(a["agent"], a["status"]) for a in _rec_ca["agents_invoked"]][:6]))
_cits_a = {c["id"]: c for c in _rec_ca["citations"]}
check("ADR-0082 (G.4) citations[].pertinent deja de ser gris: la cita al chunk de Ruta A que los votos VÁLIDOS covered citaron → "
      "pertinent true + pertinent_to (requirement_ids) + pertinent_source 'council.r2 (…)'; la cita a CORPUS-2026-0001 (∉ bundle, "
      "nadie la nombró) → 'not-named-by-council (valid round; no vote cites this id)' (jamás false); summary.pertinent {state "
      "'checked', n_true 1, n_not_named 1, literal viejo dentro}; deterministic_checks.council {state applicable, must_uncovered_pre 0, "
      "post null, n_hallucinated_votes 0, n_directives 0, n_requirements_kept 4} y attestation_identifier_leak [] 'checked' (hubo "
      "atestiguaciones sin fuga); epistemic_summary.{council_state, council_n_valid 12 (r2), council_n_members 17, council_must_uncovered 0}",
      _cits_a["CORPUS-2026-0003#c000"]["pertinent"] is True and _c_rid["europepmc"] in _cits_a["CORPUS-2026-0003#c000"]["pertinent_to"]
      and _cits_a["CORPUS-2026-0003#c000"]["pertinent_source"].startswith("council.r2")
      and _cits_a["CORPUS-2026-0001"]["pertinent"] == _vo.PERTINENT_NOT_NAMED
      and _rec_ca["citations_support_summary"]["pertinent"]["state"] == "checked"
      and _rec_ca["citations_support_summary"]["pertinent"]["n_true"] == 1 and _rec_ca["citations_support_summary"]["pertinent"]["n_not_named"] == 1
      and _rec_ca["citations_support_summary"]["pertinent"]["literal"] == "not-available (ADR-0082)"
      and _rec_ca["deterministic_checks"]["council"] == {**_rec_ca["deterministic_checks"]["council"], "state": "applicable",
                                                          "must_uncovered_pre": 0, "must_uncovered_post": None,
                                                          "n_hallucinated_votes": 0, "n_directives": 0, "n_requirements_kept": 4}
      and _rec_ca["deterministic_checks"]["attestation_identifier_leak"] == []
      and _rec_ca["deterministic_checks"]["attestation_identifier_leak_state"] == "checked"
      and json.loads(_row_ca["epistemic_summary_json"])["council_state"] == "applicable"
      and json.loads(_row_ca["epistemic_summary_json"])["council_n_valid"] == 12
      and json.loads(_row_ca["epistemic_summary_json"])["council_n_members"] == 17
      and json.loads(_row_ca["epistemic_summary_json"])["council_must_uncovered"] == 0,
      json.dumps({"cits": {k: (v.get("pertinent"), v.get("pertinent_to")) for k, v in _cits_a.items()},
                  "dc": _rec_ca["deterministic_checks"]["council"]}, default=str))
check("ADR-0082 (F.5/E5) el sintetizador recibió human_attestations como llave HERMANA (knowledge_now + 1 aporto) en pass1 y NO "
      "dentro de evidence; NUNCA recibe criterios ni cobertura del consejo (ciego, E5); frozen.council.human_attestations {present, "
      "n_attestations 1, knowledge_now_present True, delivery.synthesizer True}; el panel recibió deterministic_checks.council "
      "(conteos) — la prosa atestiguada no viaja al panel: los jueces NO ven 'Our lab confirmed'",
      len(_C_SYNTH_SEEN) == 1 and _C_SYNTH_SEEN[0]["human_attestations"]["n_attestations"] == 1
      and _C_SYNTH_SEEN[0]["human_attestations"]["knowledge_now"]["text"].startswith("We already know")
      and _C_SYNTH_SEEN[0]["evidence_has_attestations"] is False
      and _cn_a["human_attestations"] == {**_cn_a["human_attestations"], "present": True, "n_attestations": 1,
                                          "knowledge_now_present": True}
      and _cn_a["human_attestations"]["delivery"]["synthesizer"] is True and _cn_a["human_attestations"]["delivery"]["panel"] is False,
      json.dumps(_cn_a["human_attestations"]))

# --- (b) must SIN cubrir → no competente → directivas → familia directive-only (string) ENTRA → r3 sobre el dueño → post ------
_C_CALLS.clear()
_rid_cb, _rec_cb, _ev_cb, _row_cb = _run82("ADR-0082 b: wt1a interaction partners?", _c_json(_C_LEDGER, "plan-c5-b"),
                                            council_caller=_mk_council_caller(uncovered_fams=("string",)), string_found=True)
_t_cb = _ev_types(_ev_cb)
_cn_b = _rec_cb["council"]
_sp_b = _ev_payloads(_ev_cb, "stage.search.plan")[0]
_dir_ev = _ev_payloads(_ev_cb, "stage.council.directives")
_cov_pre_b, _cov_post_b, _after_b = _cn_b["coverage"]["pre_search"], _cn_b["coverage"]["post_search"], _cn_b["coverage"]["after_search"]
_r3_b = next(r for r in _cn_b["rounds"] if r["round"] == "r3")
check("ADR-0082 (G.1/G.3) 1 must sin cubrir (string, uncovered por cross-modality-integrator): componente 'checked' value False → "
      "competent False reasons ['council_uncovered_must'] → stage.council.directives {n 1, families ['string']} → stage.search.plan "
      "families_source 'directives+default', n_directives 1, la familia directive-only 'string' ENTRA y las 5 auto SIGUEN → "
      "path_b → r3 SÓLO sobre el dueño (n_invoked 1 < 17, kind recoverage) → coverage post-search must_uncovered 0 → pass2; "
      "orden competence < directives < search.plan < path_b < council.round{r3} < coverage{post} < pass2",
      _rec_cb["competence"]["competent"] is False and _rec_cb["competence"]["reasons"] == ["council_uncovered_must"]
      and _rec_cb["competence"]["components"]["council_uncovered_must"]["value"] is False
      and _rec_cb["competence"]["components"]["council_uncovered_must"]["must_uncovered"] == 1
      and len(_dir_ev) == 1 and _dir_ev[0]["n"] == 1 and _dir_ev[0]["families"] == ["string"]
      and _sp_b["families_source"] == "directives+default" and _sp_b["n_directives"] == 1
      and "string" in _sp_b["families"] and set(_sh.DEFAULT_FAMILIES) <= set(_sp_b["families"])
      and _r3_b["kind"] == "recoverage" and _r3_b["n_invoked"] == 1 and _r3_b["members_order"] == ["cross-modality-integrator"]
      and _cov_pre_b["must_uncovered"] == 1 and _cov_post_b["state"] == "judged" and _cov_post_b["must_uncovered"] == 0
      and _cov_post_b["rejudged_members"] == ["cross-modality-integrator"]
      and _t_cb.index("stage.competence") < _t_cb.index("stage.council.directives") < _t_cb.index("stage.search.plan")
      < _t_cb.index("stage.path_b") < [i for i, t in enumerate(_t_cb) if t == "stage.council.round"][1]
      < [i for i, t in enumerate(_t_cb) if t == "stage.council.coverage"][1] < _t_cb.index("stage.synthesize.pass2")
      and [c["round"] for c in _C_CALLS].count("r3") == 1 and _rec_cb["fallback"]["trigger"] == "competence",
      json.dumps({"reasons": _rec_cb["competence"]["reasons"], "families": _sp_b["families"], "r3": _r3_b["members_order"],
                  "post": _cov_post_b["must_uncovered"]}))
_sl_b = _rec_cb["search_ledger"]
_string_row = next((s for rd in _sl_b["rounds"] for s in rd["sources"] if s["family"] == "string"), None)
_string_paper = next((p for p in json.loads(_row_cb["bundle_json"])["path_b"]["papers"] if p.get("source_family") == "string"), None)
check("ADR-0082 (C.6/C.7) la directiva se compiló desde el REQUISITO (family string, symbols ['wt1a'] resueltos por resolve_id, "
      "refined_by_members ['cross-modality-integrator'] por su search_directive) y viaja verbatim en search_ledger.plan.directives "
      "(directives_state 'provided'); la fila de string lleva directive_requirement_ids [req string] y el ítem admitido también → "
      "after_search: string 'retrieved-for' (1 ítem, medición estructural), europepmc 'covered-pre'; search_ledger.n_items_for_"
      "directives {req: 1}; frozen.council.directives_state 'provided'; fb_meta.council.families_from_directives ['string']",
      _cn_b["directives"][0]["family"] == "string" and _cn_b["directives"][0]["symbols"] == ["wt1a"]
      and _cn_b["directives"][0]["refined_by_members"] == ["cross-modality-integrator"]
      and _cn_b["directives"][0]["query_en"] == "wt1a STRING partners zebrafish" and "query_en_original" in _cn_b["directives"][0]
      and _sl_b["plan"]["directives_state"] == "provided" and _sl_b["plan"]["directives"][0]["requirement_id"] == _c_rid["string"]
      and _string_row is not None and _string_row["directive_requirement_ids"] == [_c_rid["string"]] and _string_row["status"] == "success"
      and _string_paper is not None and _string_paper.get("directive_requirement_ids") == [_c_rid["string"]]
      and {b["requirement_id"]: b["state"] for b in _after_b["by_requirement"]}[_c_rid["string"]] == "retrieved-for"
      and {b["requirement_id"]: b["state"] for b in _after_b["by_requirement"]}[_c_rid["europepmc"]] == "covered-pre"
      and _after_b["n_items_for_directives"] == {_c_rid["string"]: 1} and _sl_b["n_items_for_directives"] == {_c_rid["string"]: 1}
      and _cn_b["directives_state"] == "provided"
      and _rec_cb["fallback"]["fb_meta"]["council"]["families_from_directives"] == ["string"]
      and _rec_cb["fallback"]["fb_meta"]["council"]["must_uncovered_pre"] == 1,
      json.dumps({"dir": _cn_b["directives"][0], "after": _after_b["n_items_for_directives"],
                  "row": (_string_row or {}).get("directive_requirement_ids")}, default=str)[:500])
_tu_b = _rec_cb["token_usage"]
_ai_b = {a["agent"]: a for a in _rec_cb["agents_invoked"]}
check("ADR-0082 (H/G.7/G.8) con r3: by_stage.council_r3 'measured' (1 miembro, 1000/200), _sum == by_model, cache cuadra; "
      "deterministic_checks.council {must_uncovered_pre 1, must_uncovered_post 0, n_directives 1}; epistemic council_must_uncovered 1 "
      "(pre, frozen-counter); agents_invoked cross-modality-integrator 'council:cross-modality-integrator:r1+r2+r3' con "
      "'coverage:1/0/0' (el voto r3 REEMPLAZA al r2 en la cobertura post); el sintetizador de pass2 sigue CIEGO al consejo",
      _tu_b["by_stage"]["council_r3"]["state"] == "measured" and _tu_b["by_stage"]["council_r3"]["in"] == 1000
      and _tu_b["by_stage"]["council_r3"]["n_invoked"] == 1
      and _tu_b["by_stage_sum_matches_by_model"] is True and _tu_b["cache_sum_matches_by_model"] is True
      and _rec_cb["deterministic_checks"]["council"]["must_uncovered_pre"] == 1
      and _rec_cb["deterministic_checks"]["council"]["must_uncovered_post"] == 0
      and _rec_cb["deterministic_checks"]["council"]["n_directives"] == 1
      and json.loads(_row_cb["epistemic_summary_json"])["council_must_uncovered"] == 1
      and _ai_b["cross-modality-integrator"]["invocation_id"] == "council:cross-modality-integrator:r1+r2+r3"
      and "coverage:1/0/0" in _ai_b["cross-modality-integrator"]["evidence_generated"]
      and _cn_b["r3"]["state"] == "judged" and _cn_b["r3"]["members"] == ["cross-modality-integrator"],
      json.dumps({"r3": _tu_b["by_stage"]["council_r3"], "dc": _rec_cb["deterministic_checks"]["council"]}, default=str))

# --- (c) ronda INCOMPLETA (8/17 caídos http-529) → False 'council-incomplete' — no competente, revisión NO disparada por eso ----
_C_CALLS.clear()
_fail8 = tuple(_C_MEMBERS[i] for i in range(0, 16, 2))
_rid_cc2, _rec_cc2, _ev_cc2, _row_cc2 = _run82("ADR-0082 c: incomplete round", _c_json(_C_LEDGER, "plan-c5-c"),
                                                council_caller=_mk_council_caller(fail_r2=_fail8))
_cn_c = _rec_cc2["council"]
_comp_c = _rec_cc2["competence"]["components"]["council_uncovered_must"]
_r2_c = next(r for r in _cn_c["rounds"] if r["round"] == "r2")
check("ADR-0082 (C.3/G.2) 8 miembros marcados para caer (CallerError http-529 con usage de intento cobrado), 5 de ellos con requisito "
      "kept → r2 n_valid 7 (12 invocados − 5 caídos) < cuórum 8 = ceil(0.6·12 ELEGIBLES) (corrector: los 5 not-invoked no cuentan en el "
      "denominador; required_full_membership 11) → round state 'incomplete' → frozen.council.state 'incomplete'; "
      "componente {state 'incomplete (7/12 < quorum 8)', value False, gating True, reason 'council-incomplete (k/N < quorum)'} → "
      "competent False reasons ['council_uncovered_must']; los 5 errored "
      "llevan error_kind 'http-529' y usage MEDIDO (1000 in, cobrado); revision.performed False (el panel aprobó: la ronda "
      "incompleta jamás dispara revisión); epistemic council_n_valid 9",
      _r2_c["state"] == "incomplete" and _r2_c["n_valid"] == 7 and _r2_c["n_errored"] == 5
      and _cn_c["state"] == "incomplete"
      and _comp_c["state"] == "incomplete (7/12 < quorum 8)" and _comp_c["value"] is False and _comp_c["gating"] is True
      and _r2_c["quorum"]["n_eligible"] == 12 and _r2_c["quorum"]["required"] == 8 and _r2_c["quorum"]["required_full_membership"] == 11
      and _comp_c["round"]["n_eligible"] == 12 and _cn_c["coverage"]["pre_search"]["round_summary"]["quorum_required"] == 8
      and _comp_c["reason"] == "council-incomplete (k/N < quorum)"
      and _rec_cc2["competence"]["competent"] is False and _rec_cc2["competence"]["reasons"] == ["council_uncovered_must"]
      and all(m["error_kind"] == "http-529" and m["usage"]["input_tokens"] == 1000 for m in _r2_c["members"] if m["status"] == "errored")
      and _rec_cc2["revision"]["performed"] is False and _rec_cc2["audit"]["verdict"] == "APPROVE"
      and json.loads(_row_cc2["epistemic_summary_json"])["council_n_valid"] == 7,
      json.dumps({"comp": {k: _comp_c[k] for k in ("state", "value", "gating", "reason")}, "n_valid": _r2_c["n_valid"]}))

# --- (l) corrector C.3/C.5: SÓLO 3 dueños de requisitos kept (europepmc — el requisito de 9 miembros — descartado con razón) --------
_C_CALLS.clear()
_L3_DECISIONS = _C_DECISIONS + [{"requirement_id": _c_rid["europepmc"], "decision": "discard",
                                 "reason": "la literatura general ya está en la DI (turno acotado)"}]
_C_LEDGER3 = _council.apply_ledger_decisions(_C_AGG, decisions=_L3_DECISIONS, approve=True, decided_by="natalia", decided_at=_C_AT)
_rid_cl, _rec_cl, _ev_cl, _row_cl = _run82("ADR-0082 l: three owners", _c_json(_c_app_ledger(_C_LEDGER3), "plan-c5-l"))
_cn_l = _rec_cl["council"]
_r2_l = next(r for r in _cn_l["rounds"] if r["round"] == "r2")
_comp_l = _rec_cl["competence"]["components"]["council_uncovered_must"]
check("ADR-0082 (C.3/C.5) corrector: ledger con 3 kept (string, zfin, web) cuyos dueños son 3 miembros (14 not-invoked, 3 llamadas) que "
      "votan covered con id válido → r2 'applicable' con quorum {n_eligible 3, required 2 = ceil(0.6·3), n_valid 3, met True, "
      "required_full_membership 11} → componente 'checked' value True → competent True SIN ronda de búsqueda — ANTES: 3/17 < 11 → "
      "'incomplete' por construcción → no competente → búsqueda + pass2 forzadas sin haber medido nada",
      _r2_l["state"] == "applicable" and _r2_l["n_invoked"] == 3 and _r2_l["n_not_invoked"] == 14 and len(_C_CALLS) == 3
      and _r2_l["quorum"] == {**_r2_l["quorum"], "n_eligible": 3, "required": 2, "n_valid": 3, "met": True, "n_members": 17,
                              "required_full_membership": 11, "state": "met"}
      and _cn_l["state"] == "applicable" and _cn_l["ledger"]["n_kept"] == 3 and _cn_l["ledger"]["n_discarded"] == 2
      and _comp_l["state"] == "checked" and _comp_l["value"] is True and _comp_l["gating"] is True
      and _comp_l["round"]["n_eligible"] == 3 and _comp_l["round"]["quorum_required"] == 2
      and _rec_cl["competence"]["competent"] is True and "stage.search.plan" not in _ev_types(_ev_cl)
      and _ev_payloads(_ev_cl, "stage.council.round")[0]["quorum"]["n_eligible"] == 3,
      json.dumps({"quorum": _r2_l["quorum"], "comp": {k: _comp_l[k] for k in ("state", "value", "gating")},
                  "competent": _rec_cl["competence"]["competent"]}))

# --- (d) voto con evidence_id ALUCINADO → anulado → not-judged → must sin cubrir --------------------------------------------
_C_CALLS.clear()
_rid_cd, _rec_cd, _ev_cd, _row_cd = _run82("ADR-0082 d: hallucinated vote", _c_json(_C_LEDGER, "plan-c5-d"),
                                            council_caller=_mk_council_caller(halluc_r2=("causal-pruner",)))
_cov_d = _rec_cd["council"]["coverage"]["pre_search"]
_zfin_d = next(b for b in _cov_d["by_requirement"] if b["requirement_id"] == _c_rid["zfin"])
check("ADR-0082 (C.5) causal-pruner cita 'PMID:999' (∉ bundle) → voto ANULADO (annulled True, hallucinated_evidence_ids ['PMID:999']) "
      "→ su must zfin sin votos válidos → 'not-judged' → cuenta como must SIN cubrir (must_not_judged 1, must_uncovered 1) → "
      "not competent; coverage.hallucinated_evidence_ids lo lista, n_hallucinated_votes 1 en el frozen, en stage.council.coverage y "
      "en deterministic_checks.council (el panel lo recibe como CONTEO)",
      _zfin_d["coverage_final"] == "not-judged" and _zfin_d["votes"][0]["annulled"] is True
      and _zfin_d["votes"][0]["hallucinated_evidence_ids"] == ["PMID:999"] and _zfin_d["n_valid_votes"] == 0
      and _cov_d["must_not_judged"] == 1 and _cov_d["must_uncovered"] == 1 and _cov_d["n_hallucinated_votes"] == 1
      and _cov_d["hallucinated_evidence_ids"] == [{"agent": "causal-pruner", "requirement_id": _c_rid["zfin"], "evidence_ids": ["PMID:999"]}]
      and _ev_payloads(_ev_cd, "stage.council.coverage")[0]["n_hallucinated_votes"] == 1
      and _rec_cd["deterministic_checks"]["council"]["n_hallucinated_votes"] >= 1
      and _rec_cd["competence"]["competent"] is False,
      json.dumps({"zfin": {k: _zfin_d[k] for k in ("coverage_final", "n_valid_votes")}, "halluc": _cov_d["hallucinated_evidence_ids"]}))

# --- (e) KILL-SWITCH WITT_COUNCIL=0 con la MISMA copia: 0 llamadas, 0 stage.council.*, forma 1.10 + excepciones DECLARADAS (L.2) ----
_C_CALLS.clear()
_rid_ce, _rec_ce, _ev_ce, _row_ce = _run82("ADR-0082 e: kill-switch", _c_json(_c_app_ledger(_C_LEDGER), "plan-c5-e"),
                                            env={"WITT_COUNCIL": "0"})
_FROZEN_1_10_KEYS = {
    "render_contract_version", "run_id", "user_id", "question", "measured_at", "store_at_retrieval", "retrieval_summary",
    "decision_state", "fallback", "confidence", "audit", "audit_initial", "answer_initial", "revision", "answer", "models",
    "alternatives_considered", "reasoning", "agents_invoked", "plan", "plan_declared", "plan_question_matches_run", "citations",
    "citations_schema", "citations_support_summary", "evidence_cited_raw", "competence", "search_ledger", "deterministic_checks",
    "token_usage", "usage_raw", "bundle_identity", "question_matches_run", "thread", "thread_context",
    "thread_context_skipped_reason", "thread_parent_matches_run", "thread_parent_matches_run_state",
    "thread_parent_matches_run_rule", "precedent_citations", "precedent_citations_state", "origin", "plan_parent_matches_run",
    "plan_parent_matches_run_state", "plan_snapshot_matches_run", "plan_snapshot_matches_run_state", "episode_axes", "niches"}
_TU_1_10_KEYS = {"input_tokens", "output_tokens", "by_model", "by_stage", "by_stage_sum_matches_by_model", "plan_judgment",
                 "embedding", "estimated_cost_usd", "missing_price_models", "cost_projection_complete", "cost_class"}
_dc_extra = set(_rec_ce["deterministic_checks"]) - set(_rec_ca["deterministic_checks"])
check("ADR-0082 (L.2) kill-switch WITT_COUNCIL=0 con la misma copia F.4: CERO llamadas al fake, CERO eventos stage.council.*, ninguna "
      "de las etapas del consejo; el frozen tiene EXACTAMENTE las 47 llaves de 1.10 + {council}; token_usage = llaves 1.10 + {cache, "
      "input_tokens_total, council_judgment, cache_sum_matches_by_model}; by_stage.council_r2/r3 'kill-switch WITT_COUNCIL=0' in/out "
      "null PERO council_r1 se COPIA igual del plan (el gasto ocurrió ANTES de encolar: apagar el consejo detiene llamadas, no "
      "contabilidad — declarado) → cache = la de r1, input_tokens_total = input + caché de r1, council_judgment rounds ['council_r1']; "
      "frozen.council.rounds == [r1 copiada] (sin r2/r3), ledger null; deterministic_checks gana SÓLO council{state disabled} + "
      "attestation_identifier_leak 'no-attestations'; frozen.council {state 'disabled (kill-switch WITT_COUNCIL=0)', kill_switch.enabled False}; competencia "
      "component 'kill-switch WITT_COUNCIL=0' fuera de conjunction (== cg-3); agents_invoked gana SÓLO la fila agregada "
      "not-applicable 'kill-switch WITT_COUNCIL=0' (sin filas por miembro); citations[].pertinent 'not-available (council disabled (…))'; "
      "panel_signature byte-igual a la corrida (a) con consejo; el sintetizador NO recibió human_attestations (ledger apagado)",
      _C_CALLS == [] and not any(t.startswith("stage.council.") for t in _ev_types(_ev_ce))
      and set(_rec_ce) == _FROZEN_1_10_KEYS | {"council", "figures", "web_locator"}   # ADR-0083/0084: figures y web_locator SIEMPRE presentes
      and set(_rec_ce["token_usage"]) == _TU_1_10_KEYS | {"cache", "input_tokens_total", "council_judgment", "cache_sum_matches_by_model",
                                                            "figures"}   # F8 ADR-0083 (H): usage_json.figures espejo (WITT_FIGURES=1 default)
      and _rec_ce["token_usage"]["cache"]["creation_input_tokens"] == _r1_usage["cache_creation"]
      and _rec_ce["token_usage"]["cache"]["read_input_tokens"] == _r1_usage["cache_read"]
      and _rec_ce["token_usage"]["council_judgment"]["rounds"] == ["council_r1"]
      and "kill-switch" in _rec_ce["token_usage"]["cache"]["state"]
      and _rec_ce["token_usage"]["by_stage"]["council_r1"]["state"] == "copied-from-plan_json"
      and "council disabled at execution" in _rec_ce["token_usage"]["by_stage"]["council_r1"]["source"]
      and all(_rec_ce["token_usage"]["by_stage"][s] == {"in": None, "out": None, "state": "kill-switch WITT_COUNCIL=0"}
              for s in ("council_r2", "council_r3"))
      and _rec_ce["token_usage"]["input_tokens_total"] == (_rec_ce["token_usage"]["input_tokens"] + _r1_usage["cache_creation"]
                                                          + _r1_usage["cache_read"])
      and _rec_ce["token_usage"]["by_stage_sum_matches_by_model"] is True and _rec_ce["token_usage"]["cache_sum_matches_by_model"] is True
      and set(_rec_ce["deterministic_checks"]) - set(_rec_ca["deterministic_checks"]) == set()
      and _rec_ce["deterministic_checks"]["council"]["state"] == "disabled (kill-switch WITT_COUNCIL=0)"
      and _rec_ce["deterministic_checks"]["attestation_identifier_leak_state"] == "no-attestations"
      and _rec_ce["council"]["state"] == "disabled (kill-switch WITT_COUNCIL=0)" and _rec_ce["council"]["kill_switch"]["enabled"] is False
      and [r["round"] for r in _rec_ce["council"]["rounds"]] == ["r1"] and _rec_ce["council"]["rounds"][0]["copied_from_plan_id"] == "plan-c5-e"
      and _rec_ce["council"]["ledger"] is None
      and _rec_ce["competence"]["components"]["council_uncovered_must"]["state"] == "kill-switch WITT_COUNCIL=0"
      and "council_uncovered_must" not in _rec_ce["competence"]["conjunction"]
      and _rec_ce["competence"]["conjunction"] == _rec_c["competence"]["conjunction"]
      and [a["agent"] for a in _rec_ce["agents_invoked"] if a["agent"] in _C_MEMBERS] == []
      and next(a for a in _rec_ce["agents_invoked"] if a["agent"] == runs_mod.COUNCIL_AGENT_ROW)["reason"] == "kill-switch WITT_COUNCIL=0"
      and runs_mod.COUNCIL_OPERATIVES_ROW not in {a["agent"] for a in _rec_ce["agents_invoked"]}
      and all(c["pertinent"] == "not-available (council disabled (kill-switch WITT_COUNCIL=0))" for c in _rec_ce["citations"])
      and _rec_ce["models"]["panel_signature"] == _rec_ca["models"]["panel_signature"]
      and _C_SYNTH_SEEN[-1]["human_attestations"] is None,
      json.dumps({"extra_frozen": sorted(set(_rec_ce) - _FROZEN_1_10_KEYS), "dc_extra": sorted(_dc_extra),
                  "tu_extra": sorted(set(_rec_ce["token_usage"]) - _TU_1_10_KEYS)}))

_DC_ADD_111 = {"council", "attestation_identifier_leak", "attestation_identifier_leak_state", "attestation_identifier_leak_rule"}
_DC_1_10_BASE = {"pass", "admissible", "reasons", "identifier_report", "parent_identifier_leak", "parent_identifier_leak_state", "thread",
                 "positive_claim_requires_citations", "positive_claim_requires_citations_state",   # runs._gate @ 9d90c01 (sin padre)
                 "pass1_admissible", "competence_gate", "disjoint_series", "disjoint_series_state"}   # + lo que execute_run añade al congelar @ 9d90c01
check("ADR-0082 (L.2 i) corrector: bajo kill-switch deterministic_checks = keyset 1.10 congelado @ 9d90c01 (runs._gate + pass1_admissible/competence_gate/disjoint_series*) + EXACTAMENTE las 4 llaves "
      "aditivas DECLARADAS {council {state}, attestation_identifier_leak [], _state 'no-attestations', _rule} — el fragmento viaja al panel "
      "con estado declarado (tres estados: el predicado corrió y no había atestiguaciones) y la excepción queda escrita en el ADR",
      (set(_rec_ce["deterministic_checks"]) - _DC_ADD_111 - {"figures", "web_locator"}) - {"positive_claim_requires_citations_inputs",
                                                                          "positive_claim_requires_citations_evaluation"} == _DC_1_10_BASE
      # ADR-0083 (F/L): deterministic_checks.figures NACE en 1.12 (SIEMPRE presente; su keyset se mide en la sección ADR-0083)
      # ADR-0084 (E/G.3): deterministic_checks.web_locator NACE en 1.13 (SIEMPRE presente; su keyset se mide en la sección ADR-0084)
      and _DC_ADD_111 <= set(_rec_ce["deterministic_checks"])
      and _rec_ce["deterministic_checks"]["attestation_identifier_leak"] == []
      and _rec_ce["deterministic_checks"]["attestation_identifier_leak_state"] == "no-attestations"
      and _rec_ce["deterministic_checks"]["attestation_identifier_leak_rule"] == runs_mod.ATTESTATION_LEAK_RULE,
      json.dumps(sorted(set(_rec_ce["deterministic_checks"]) - _DC_1_10_BASE)))

# --- (f) aporto ATESTIGUADO con un PMID que la respuesta cita sin evidencia → attestation_identifier_leak → INADMISIBLE ------------
_C_CALLS.clear(); _C_SYNTH_SEEN.clear()
_rid_cf, _rec_cf, _ev_cf, _row_cf = _run82("ADR-0082 f: attestation leak", _c_json(_C_LEDGER, "plan-c5-f"),
                                            synth=_mk_synth82("wt1a marks the pronephros (PMID:31415926).",
                                                              {"pass1": 0.9, "pass2": 0.9}, _C_CITED_OK))
_g1_f = _ev_payloads(_ev_cf, "stage.deterministic_gate")[0]
check("ADR-0082 (F.5/R9) el humano aportó un texto con PMID:31415926; la respuesta lo cita y NO está en la evidencia → predicado DURO "
      "attestation_identifier_leak ['PMID:31415926'] state 'checked' → pass1 INADMISIBLE ('hard predicate failed: "
      "attestation_identifier_leak') → competent False ['admissible'] → ronda + pass2 (misma respuesta → inadmisible de nuevo); "
      "parent_identifier_leak intacto ('no-parent'); el requisito aportado queda 'covered-by-attestation' (fuera del gating); el "
      "sintetizador recibió human_attestations en pass1 Y pass2 y el system lleva ATTESTATION_ANTI_LEAK_CLAUSE sólo con ellas",
      _g1_f["attestation_identifier_leak"] == ["PMID:31415926"] and _g1_f["attestation_identifier_leak_state"] == "checked"
      and _g1_f["admissible"] is False and "hard predicate failed: attestation_identifier_leak" in _g1_f["reasons"]
      and _g1_f["parent_identifier_leak_state"] == "no-parent"
      and _rec_cf["competence"]["competent"] is False and "admissible" in _rec_cf["competence"]["reasons"]
      and _rec_cf["deterministic_checks"]["attestation_identifier_leak"] == ["PMID:31415926"]
      and _rec_cf["deterministic_checks"]["admissible"] is False and _rec_cf["deterministic_checks"]["pass"] == "pass2"
      and {b["requirement_id"]: b["coverage_final"] for b in _rec_cf["council"]["coverage"]["pre_search"]["by_requirement"]}[_c_rid["pubmed"]]
          == "covered-by-attestation"
      and [s["pass"] for s in _C_SYNTH_SEEN] == ["pass1", "pass2"] and all(s["human_attestations"] for s in _C_SYNTH_SEEN)
      and runs_mod.ATTESTATION_ANTI_LEAK_CLAUSE in runs_mod.synth_system("pass1", human_attestations=True)
      and runs_mod.ATTESTATION_ANTI_LEAK_CLAUSE not in runs_mod.synth_system("pass1")
      and runs_mod.synth_system("pass1") == runs_mod.synth_system("pass1", thread_context=False, human_attestations=False)
      and "PRIOR ART attested by humans" in runs_mod.SYNTH_TOOL["description"],
      json.dumps({"leak": _g1_f["attestation_identifier_leak"], "reasons": _g1_f["reasons"]}))

# --- (g) WITT_COUNCIL_RECOVERAGE=0 con el fixture (b): sin r3, post_search 'not-run (kill-switch …)' --------------------------------
_C_CALLS.clear()
_rid_cg, _rec_cg, _ev_cg, _row_cg = _run82("ADR-0082 g: recoverage off", _c_json(_C_LEDGER, "plan-c5-g"),
                                            council_caller=_mk_council_caller(uncovered_fams=("string",)), string_found=True,
                                            env={"WITT_COUNCIL_RECOVERAGE": "0"})
check("ADR-0082 (C.7/L) WITT_COUNCIL_RECOVERAGE=0: la búsqueda dirigida corre (string entra, after_search 'retrieved-for') pero NO hay "
      "r3 — post_search.state 'not-run (kill-switch WITT_COUNCIL_RECOVERAGE=0)', rounds [r1, r2], by_stage.council_r3 not-run con la "
      "razón, 0 llamadas r3; deterministic_checks.council.must_uncovered_post null",
      _rec_cg["council"]["coverage"]["post_search"]["state"] == "not-run (kill-switch WITT_COUNCIL_RECOVERAGE=0)"
      and [r["round"] for r in _rec_cg["council"]["rounds"]] == ["r1", "r2"]
      and _rec_cg["token_usage"]["by_stage"]["council_r3"]["state"] == "not-run (kill-switch WITT_COUNCIL_RECOVERAGE=0)"
      and not any(c["round"] == "r3" for c in _C_CALLS)
      and {b["requirement_id"]: b["state"] for b in _rec_cg["council"]["coverage"]["after_search"]["by_requirement"]}[_c_rid["string"]] == "retrieved-for"
      and _rec_cg["deterministic_checks"]["council"]["must_uncovered_post"] is None
      and _rec_cg["council"]["config"]["recoverage"] is False,
      _rec_cg["council"]["coverage"]["post_search"]["state"])

# --- (h) membresía CONGELADA: WITT_COUNCIL_FULL=1 al ejecutar con un plan de 17 → N sigue 17 ------------------------------------
_C_CALLS.clear()
_rid_ch, _rec_ch, _ev_ch, _row_ch = _run82("ADR-0082 h: frozen membership", _c_json(_C_LEDGER, "plan-c5-h"), env={"WITT_COUNCIL_FULL": "1"})
check("ADR-0082 (F.4) WITT_COUNCIL_FULL=1 en la CORRIDA con un plan congelado de 17: N sigue 17 (members del plan, membership_source "
      "'plan.council (frozen at r1)', full_council False, quorum_required 11), 12 llamadas (los 12 con requisito kept) — el cuórum no se mueve en silencio",
      _rec_ch["council"]["n_members"] == 17 and _rec_ch["council"]["full_council"] is False
      and _rec_ch["council"]["membership_source"] == "plan.council (frozen at r1)" and _rec_ch["council"]["quorum_required"] == 11
      and len(_C_CALLS) == 12 and next(r for r in _rec_ch["council"]["rounds"] if r["round"] == "r2")["n_members"] == 17,
      json.dumps({"n": _rec_ch["council"]["n_members"], "calls": len(_C_CALLS)}))

# --- (i) SIN plan → 'not-applicable (no-ledger)'; (k) ledger SALTADO por el humano → 'skipped-by-human' — cero llamadas ------------
_C_CALLS.clear()
_rid_ci, _rec_ci, _ev_ci, _row_ci = _run82("ADR-0082 i: no plan", None, plan=False)
_skip_ledger = {"state": "skipped-by-human", "plan_id": "plan-c5-k", "council_state_before": "applicable", "decisions": [],
                "n_requirements": _C_AGG["n_requirements"], "knowledge_now": None, "skipped_by": "natalia", "skipped_at": _C_AT,
                "reason": "hoy no quiero consejo"}
_rid_ck, _rec_ck, _ev_ck, _row_ck = _run82("ADR-0082 k: skipped ledger", _c_json(_skip_ledger, "plan-c5-k"))
check("ADR-0082 (F.2/F.4) sin plan → frozen.council.state 'not-applicable (no-ledger)', componente 'not-applicable (no-ledger)' value "
      "null gating False FUERA de conjunction, by_stage.council_r1 'plan-without-council', sin stage.council.*; ledger SALTADO por el "
      "humano → state 'skipped-by-human' con skip_reason, ledger con 0 kept (los requisitos quedan pending), componente 'not-applicable "
      "(skipped-by-human)', stage.council.ledger emitido con ledger_state 'skipped-by-human'; CERO llamadas al fake en ambas",
      _C_CALLS == []
      and _rec_ci["council"]["state"] == "not-applicable (no-ledger)"
      and _rec_ci["competence"]["components"]["council_uncovered_must"]["state"] == "not-applicable (no-ledger)"
      and _rec_ci["competence"]["components"]["council_uncovered_must"]["gating"] is False
      and "council_uncovered_must" not in _rec_ci["competence"]["conjunction"]
      and _rec_ci["token_usage"]["by_stage"]["council_r1"]["state"] == "plan-without-council"
      and not any(t.startswith("stage.council.") for t in _ev_types(_ev_ci))
      and _rec_ck["council"]["state"] == "skipped-by-human" and _rec_ck["council"]["state_reason"] == "hoy no quiero consejo"
      and _rec_ck["council"]["ledger"]["state"] == "skipped-by-human" and _rec_ck["council"]["ledger"]["n_kept"] == 0
      and _rec_ck["competence"]["components"]["council_uncovered_must"]["state"] == "not-applicable (skipped-by-human)"
      and _ev_payloads(_ev_ck, "stage.council.ledger")[0]["ledger_state"] == "skipped-by-human"
      and _rec_ck["council"]["rounds"][0]["round"] == "r1" and len(_rec_ck["council"]["rounds"]) == 1,
      json.dumps({"i": _rec_ci["council"]["state"], "k": _rec_ck["council"]["state"]}))

check("ADR-0082 (J/G.8) corrector: UNA verdad para N — sin copia del consejo (i) frozen.council {n_members null, members [], full_council "
      "null, quorum_required null, membership_source 'not-available (no council copy: …)'} y epistemic council_n_members null; con copia "
      "(a) ambos 17; bajo kill-switch CON copia (e) frozen 17 (hecho de la ronda 1 del plan) y epistemic copia ese 17 (antes null: dos "
      "valores para un hecho)",
      _rec_ci["council"]["n_members"] is None and _rec_ci["council"]["members"] == [] and _rec_ci["council"]["full_council"] is None
      and _rec_ci["council"]["quorum_required"] is None
      and _rec_ci["council"]["membership_source"].startswith("not-available (no council copy")
      and json.loads(_row_ci["epistemic_summary_json"])["council_n_members"] is None
      and _rec_ca["council"]["n_members"] == 17 == json.loads(_row_ca["epistemic_summary_json"])["council_n_members"]
      and _rec_ce["council"]["n_members"] == 17 == json.loads(_row_ce["epistemic_summary_json"])["council_n_members"]
      and _rec_ce["council"]["membership_source"] == "plan.council (frozen at r1)",
      json.dumps({"i": {k: _rec_ci["council"][k] for k in ("n_members", "members", "membership_source")},
                  "e_epistemic": json.loads(_row_ce["epistemic_summary_json"])["council_n_members"]}))

# --- (j) CANCELACIÓN a media ronda 2: pendientes skipped-cancelled, usage parcial persiste, corrida cancelled ------------------------
# El cancel lo pide el fake en su PRIMERA llamada (el miembro #1 va SOLO, C.3): así el orquestador está ocioso en wait() cuando el
# hilo del fake escribe runs.cancel_requested. Con SQLite en el gate, un escritor en hilo de pool SE MUERE DE HAMBRE detrás de los
# db.add_event continuos del orquestador (stage.council.member) y su UPDATE sólo entra cuando la ronda queda ociosa — R16 del ADR
# (Postgres en prod no tiene el límite); medido aquí con cancel_after=3: los 12 despachados terminaron antes de verse el flag.
_C_CALLS.clear()
_rid_cj, _rec_cj, _ev_cj, _row_cj = _run82("ADR-0082 j: cancel mid r2", _c_json(_C_LEDGER, "plan-c5-j"), cancel_after=1)
_v_cj = app.get_run(_rid_cj, authorization=AUTH)
_rnd_cj = _ev_payloads(_ev_cj, "stage.council.round")[-1]
check("ADR-0082 (C.3/LOTE-01·A4) cancel a media r2 (request_cancel durante la llamada del miembro #1): _check_cancel LANZA en la "
      "compuerta previa al primer despacho de la oleada → los 11 pendientes quedan skipped-cancelled con CERO llamadas (1 llamada en "
      "total), RunCancelled se relanza con el RoundResult PARCIAL adjunto → la corrida termina 'cancelled' (jamás failed), sin registro "
      "congelado; usage_json.by_stage.council_r2 'measured (partial: round cancelled)' con el gasto del que SÍ terminó (in 1000, cache "
      "creation 2400) — LOTE-01·A4 aplicado a la ronda; stage.council.round emitido con cancelled True, n_invoked 1, n_skipped_cancelled 11",
      _row_cj["state"] == "cancelled" and _rec_cj is None
      and _v_cj["token_usage"]["by_stage"]["council_r2"]["state"] == "measured (partial: round cancelled)"
      and _v_cj["token_usage"]["by_stage"]["council_r2"]["in"] == 1000
      and _v_cj["token_usage"]["by_stage"]["council_r2"]["cache_creation"] == 2400
      and len(_C_CALLS) == 1
      and _rnd_cj["cancelled"] is True and _rnd_cj["n_invoked"] == 1 and _rnd_cj["n_skipped_cancelled"] == 11
      and "stage.competence" not in _ev_types(_ev_cj),
      json.dumps({"state": _row_cj["state"], "calls": len(_C_CALLS), "round": {k: _rnd_cj.get(k) for k in ("n_invoked", "n_skipped_cancelled", "cancelled")},
                  "r2": _v_cj["token_usage"]["by_stage"]["council_r2"]}, default=str))

# --- (m) corrector E5/G.9/K.i: turno N+1 — el hijo de (a): el SINTETIZADOR no recibe council_summary; el planner y r1 SÍ ------------
import council_jobs as _cj82  # noqa: E402
_C_CALLS.clear(); _C_SYNTH_SEEN.clear()
_sources_found()
_rid_cm = runs_mod.new_run("natalia", "ADR-0082 m: and its partners?", ["wt1a"], parent_run_id=_rid_ca)
_cl_cm = db.claim_next_queued(worker_id="run-worker-adr0082")
assert _cl_cm and _cl_cm["run_id"] == _rid_cm
runs_mod.execute_run(_cl_cm, synthesizer=_mk_synth82(_C_ANSWER, {"pass1": 0.8, "pass2": 0.85}, _C_CITED_OK),
                     panel_caller=_stub_caller_factory(ALL_A), council_caller=_mk_council_caller())
_row_cm = db.get_run(_rid_cm)
_rec_cm = json.loads(_row_cm["frozen_record_json"])
_env_cm = json.loads(_row_cm["thread_context_json"])["snapshot"]
_plan_cm = runs_mod.plan_thread_context(_rid_ca)["snapshot"]
_inh_cm, _inh_state = _cj82._inherited_criteria({"thread_parent_run_id": _rid_ca})
_gap_a = next(r["gap"] for r in _rec_ca["council"]["ledger"]["requirements"] if r["requirement_id"] == _c_rid["string"])
_synth_tc = [s["thread_context"] for s in _C_SYNTH_SEEN]
check("ADR-0082 (E5/G.9/K.i) corrector: turno N+1 sobre el padre (a) CON consejo — el snapshot persistido al encolar y el que recibe el "
      "PLANNER (runs.plan_thread_context) traen council_summary con requisitos (gap ≤200, coverage_final, decision) y la ronda 1 del hijo "
      "lo heredaría (council_jobs._inherited_criteria 'delivered'); el SINTETIZADOR recibió thread_context (parent, previous_answer…) "
      "SIN la llave council_summary en pass1 (ni el texto del gap del consejo en su user_text); frozen.thread_context conserva el snapshot "
      "íntegro y frozen.thread.context_delivery.council_summary {present_in_snapshot True, delivered_to_synthesizer False, delivered_to "
      "[planner, r1], rule} + prompt_components lo declaran",
      _env_cm["council_summary"] is not None and len(_env_cm["council_summary"]["requirements"]) >= 3
      and _plan_cm["council_summary"] is not None and len(_plan_cm["council_summary"]["requirements"]) >= 3
      and _inh_state == "delivered" and len(_inh_cm["requirements"]) >= 3
      and len(_synth_tc) >= 1 and all(tc is not None and "council_summary" not in tc for tc in _synth_tc)
      and all("parent" in tc for tc in _synth_tc)
      and _gap_a not in json.dumps(_synth_tc, ensure_ascii=False) and _gap_a in json.dumps(_env_cm, ensure_ascii=False)
      and _rec_cm["thread_context"]["council_summary"] is not None
      and _rec_cm["thread"]["context_delivery"]["council_summary"]["present_in_snapshot"] is True
      and _rec_cm["thread"]["context_delivery"]["council_summary"]["delivered_to_synthesizer"] is False
      and len(_rec_cm["thread"]["context_delivery"]["council_summary"]["delivered_to"]) == 2
      and _rec_cm["thread"]["context_delivery"]["council_summary"]["rule"] == runs_mod.COUNCIL_SUMMARY_SYNTH_RULE
      and "WITHOUT council_summary" in _rec_cm["thread"]["context_delivery"]["prompt_components"][0]
      and _rec_cm["council"]["state"] == "not-applicable (no-ledger)" and _C_CALLS == [],
      json.dumps({"synth_keys": sorted(_synth_tc[0]) if _synth_tc else None, "inherited": _inh_state,
                  "n_req_env": len((_env_cm.get("council_summary") or {}).get("requirements") or [])}))

# --- censo (gate F, corrector): TODO evento stage.council.* con llave `state` lleva un literal del vocabulario congelado -----------
_c_evs = [e for _evl in (_ev_ca, _ev_cb, _ev_cc2, _ev_cd, _ev_cf, _ev_cg, _ev_ch, _ev_ck, _ev_cl) for e in _evl
          if e["type"].startswith("stage.council.")]


def _ev_state_ok(e):
    p, t = e["payload"], e["type"]
    if "state" not in p:
        return True
    if t == "stage.council.ledger":
        return _council.council_state_in_vocabulary(p["state"])
    if t == "stage.council.round":
        return _council.aggregate_state_in_vocabulary(p["state"])
    if t == "stage.council.directives":
        return p["state"] in _council.DIRECTIVES_STATES
    return False


check("ADR-0082 (J / gate F) corrector: en las 9 corridas con consejo TODOS los eventos stage.council.* con llave `state` llevan un literal "
      "del vocabulario congelado — ledger.state ∈ council_states (jamás el centinela interno 'pending-r2'/'r2-pending': mientras r2 decide "
      "viaja el estado de r1 + r2_pending True), round.state ∈ aggregate_states, directives.state ∈ DIRECTIVES_STATES; ledger de (k) "
      "'skipped-by-human' con r2_pending False",
      len(_c_evs) > 40 and all(_ev_state_ok(e) for e in _c_evs)
      and not any(e["payload"].get("state") in ("r2-pending", "pending-r2") for e in _c_evs)
      and _ev_payloads(_ev_ca, "stage.council.ledger")[0]["state"] == "applicable"
      and _ev_payloads(_ev_ca, "stage.council.ledger")[0]["r2_pending"] is True
      and _ev_payloads(_ev_ck, "stage.council.ledger")[0]["state"] == "skipped-by-human"
      and _ev_payloads(_ev_ck, "stage.council.ledger")[0]["r2_pending"] is False
      and all("attempt" in e["payload"] for e in _c_evs if e["type"] == "stage.council.member"),
      json.dumps({"n_events": len(_c_evs), "bad": [(e["type"], e["payload"].get("state")) for e in _c_evs if not _ev_state_ok(e)][:5]}))

# --- vocabularios: todo literal de estado medido en esta sección está en el vocabulario congelado ---------------------------------
_c_states = {r["council"]["state"] for r in (_rec_ca, _rec_cb, _rec_cc2, _rec_cd, _rec_ce, _rec_cf, _rec_cg, _rec_ch, _rec_ci, _rec_ck)}
_c_comp_states = {r["competence"]["components"]["council_uncovered_must"]["state"]
                  for r in (_rec_ca, _rec_cb, _rec_cc2, _rec_cd, _rec_ce, _rec_cf, _rec_cg, _rec_ch, _rec_ci, _rec_ck)}
_c_member_states = {m["status"] for r in (_rec_ca, _rec_cb, _rec_cc2, _rec_cd) for rr in r["council"]["rounds"] for m in rr.get("members") or []}
_c_cov_states = {b["coverage_final"] for r in (_rec_ca, _rec_cb, _rec_cd) for b in r["council"]["coverage"]["pre_search"]["by_requirement"]}
check("ADR-0082 (C.8/F paridad) TODOS los literales medidos en esta sección están en los vocabularios congelados: council.state "
      "(council_state_in_vocabulary), componente (competence.council_component_state_in_vocabulary), members[].status ⊆ MEMBER_STATES, "
      "coverage_final ⊆ COVERAGE_STATES, post_search ∈ POST_SEARCH exact|prefix, directives_state ∈ DIRECTIVES_STATES, by_stage.council_* "
      "state ∈ exact|prefix; stage.plan.council_state y stage.council.round.state también",
      all(_council.council_state_in_vocabulary(s) for s in _c_states)
      and all(_cg82.council_component_state_in_vocabulary(s) for s in _c_comp_states)
      and _c_member_states <= set(_council.MEMBER_STATES) and _c_cov_states <= set(_council.COVERAGE_STATES)
      and all(r["council"]["coverage"]["post_search"]["state"] in _council.POST_SEARCH_STATES_EXACT
              or r["council"]["coverage"]["post_search"]["state"].startswith("not-run (")
              for r in (_rec_ca, _rec_cb, _rec_cc2, _rec_cd, _rec_cf, _rec_cg, _rec_ch))
      and all(r["council"]["directives_state"] in _council.DIRECTIVES_STATES for r in (_rec_ca, _rec_cb, _rec_cc2, _rec_ce, _rec_ci))
      and all(v["state"] in runs_mod.COUNCIL_USAGE_STAGE_STATES_EXACT or v["state"].startswith(runs_mod.COUNCIL_USAGE_STAGE_STATE_PREFIXES)
              for r in (_rec_ca, _rec_cb, _rec_ce, _rec_ci) for s, v in r["token_usage"]["by_stage"].items() if s in runs_mod.COUNCIL_STAGES)
      and _council.council_state_in_vocabulary(_ev_payloads(_ev_ca, "stage.plan")[0]["council_state"]),
      json.dumps({"council": sorted(_c_states), "component": sorted(_c_comp_states), "members": sorted(_c_member_states)}))

# --- PDF: la sección CONSEJO DE CRITERIO nace con el bloque (tres estados) -----------------------------------------------------------
import record_pdf as _pdf82  # noqa: E402
_pdf_a = _pdf82.build_pdf(_rec_ca, compress=False)
_pdf_e = _pdf82.build_pdf(_rec_ce, compress=False)
_pdf_old = _pdf82.build_pdf({k: v for k, v in _rec_ca.items() if k != "council"}, compress=False)
check("ADR-0082 (K.m) record_pdf: la sección 'CONSEJO DE CRITERIO' NACE con el bloque — con consejo imprime membresía cm-1, ledger con "
      "decisiones y ATESTIGUADO, cobertura y rondas n/N; bajo kill-switch imprime el estado declarado; sin la llave (registro < 1.11) "
      "imprime 'NO INSTRUMENTADO (contrato < 1.11)' — jamás rellena",
      # fpdf escapa los paréntesis dentro del content stream ("\\(") — se buscan los fragmentos sin paréntesis
      b"CONSEJO DE CRITERIO" in _pdf_a and b"LEDGER approved" in _pdf_a and b"ATESTIGUADO" in _pdf_a
      and b"ronda r2" in _pdf_a and b"coverage, fase run" in _pdf_a and b"kill-switch" in _pdf_e
      and b"NO INSTRUMENTADO" in _pdf_old and b"contrato < 1.11" in _pdf_old and b"CONSEJO DE CRITERIO" in _pdf_old,
      f"len(a)={len(_pdf_a)} len(e)={len(_pdf_e)}")
_sh._TOOL_CACHE.pop("string", None)

# =====================================================================================================================
# ADR-0083 (F4) — FIGURAS como evidencia OBSERVADA en la corrida (contrato 1.12): etapa PROPIA stage.figures tras la Ruta B,
# proyección caption+meta al sintetizador (JAMÁS bytes), citas kind 'figure' con figure_verification, panel con visión (F3:
# imágenes SÓLO en dos lentes), predicados deterministas (F2), frozen.figures, kill-switches byte a byte. 100% offline con los
# fixtures de F1 (2 XML golden + zip CC BY real reducido + zip NC SINTÉTICO), _get_bytes FALSO (0 red), caché de figuras en TMP.
# Los checks marcados [F2] / [F3] miden contratos DECLARADOS de rebanadas paralelas: rojos LITERALES hasta que aterricen.
# =====================================================================================================================
print("\n== ADR-0083 (F4) figuras en la corrida ==")
import base64 as _b64  # noqa: E402
import io as _io  # noqa: E402
import zipfile as _zipfile  # noqa: E402
from lib import figures as _fig  # noqa: E402

_FX83 = Path(__file__).resolve().parent / "fixtures" / "figures"
_MAN83 = json.loads((_FX83 / "MANIFEST.json").read_text(encoding="utf-8"))
_XML_BY83 = _FX83 / "epmc_fulltext_PMC11379296_20260613.xml"
_XML_NC83 = _FX83 / "epmc_fulltext_PMC11647118_20260613.xml"
_ZIP_BY83 = (_FX83 / "PMC11379296-figures.zip").read_bytes()
_ZIP_NC83 = (_FX83 / "PMC11647118-figures-SYNTHETIC.zip").read_bytes()
_MAN_BY83 = {e["href"]: e for e in _MAN83["zips"]["PMC11379296"]["entries"]}
_ZF_BY83 = _zipfile.ZipFile(_io.BytesIO(_ZIP_BY83))
_B64_BY83 = {n: _b64.b64encode(_ZF_BY83.read(n)).decode("ascii") for n in _ZF_BY83.namelist()}
_G001_HREF = "pone.0307390.g001.jpg"
_G001_B64 = _B64_BY83[_G001_HREF]
_G001_ID = "PMC11379296#pone.0307390.g001"
_FIG_IDS83 = [f"PMC11379296#pone.0307390.g00{i}" for i in range(1, 10)]
_LENSES_V83 = ["evidence-grounding", "reproducibility"]
# la caché de figuras del gate vive en un TMP propio (WITT_MCP_CACHE_DIR): mcp_cache del repo byte-idéntico (snapshot final)
_FIG_CACHE83 = TMP / "mcp_cache_figs"
_MCP_ENV_SAVED83 = os.environ.get("WITT_MCP_CACHE_DIR")
os.environ["WITT_MCP_CACHE_DIR"] = str(_FIG_CACHE83)
_CR83 = _FIG_CACHE83 / "figures"
# la costura de red de figures quedó ligada al urlopen REAL al importar (antes del bloqueador): se bloquea y cuenta aquí también
_FIG_URLOPEN_SAVED83 = _fig._urlopen
_fig._urlopen = _urlopen_blocked
_net_before83 = len(_NET_CALLS)

# XML SINTÉTICO sin <permissions> → licencia 'unknown' (declarado: el gate mide licencia y sha, no contenido); su zip lleva el PNG
# 1×1 del fixture NC bajo el href u1.jpg (media_type por magic ≠ mime por extensión)
_XML_UNK83 = TMP / "epmc_fulltext_PMC90000001_synthetic_fulltext.xml"
_XML_UNK83.write_text(
    '<article xml:lang="en" xmlns:xlink="http://www.w3.org/1999/xlink"><front><article-meta>'
    '<article-id pub-id-type="pmcid">PMC90000001</article-id></article-meta></front><body>'
    '<fig id="u1"><label>Fig 1</label><caption><p>Synthetic figure whose article carries no permissions block.</p></caption>'
    '<graphic xlink:href="u1.jpg"/></fig></body></article>', encoding="utf-8")
_PNG1x1 = _zipfile.ZipFile(_io.BytesIO(_ZIP_NC83)).read("gr1.jpg")
_bufu = _io.BytesIO()
with _zipfile.ZipFile(_bufu, "w") as _zu:
    _zu.writestr("u1.jpg", _PNG1x1)
_ZIP_UNK83 = _bufu.getvalue()
_ZIPS83 = {"PMC11379296": _ZIP_BY83, "PMC11647118": _ZIP_NC83, "PMC90000001": _ZIP_UNK83}
_XMLS83 = {"PMC11379296": _XML_BY83, "PMC11647118": _XML_NC83, "PMC90000001": _XML_UNK83}
_RECS83 = {
    "PMC11379296": {"epmc_id": "83a", "source": "MED", "pmid": "39230001", "pmcid": "PMC11379296",
                    "doi": "10.1371/journal.pone.0307390", "title": _MAN83["attribution"]["PMC11379296"]["title"],
                    "year": "2024", "journal": "PLoS One", "is_oa": True, "abstract": "wt1a pronephros abstract (CC BY fixture).",
                    "cited_by": 1, "license": "cc by"},
    "PMC11647118": {"epmc_id": "83b", "source": "MED", "pmid": "39230002", "pmcid": "PMC11647118", "doi": None,
                    "title": _MAN83["attribution"]["PMC11647118"]["title"], "year": "2024", "journal": "J", "is_oa": True,
                    "abstract": "wt1a pronephros abstract (CC BY-NC fixture).", "cited_by": 0, "license": "cc by-nc"},
    "PMC90000001": {"epmc_id": "83c", "source": "MED", "pmid": "39230003", "pmcid": "PMC90000001", "doi": None,
                    "title": "synthetic unknown-license paper", "year": "2024", "journal": "J", "is_oa": True,
                    "abstract": "wt1a pronephros abstract (unknown license, synthetic).", "cited_by": 0, "license": None},
}
_PMID2PMC83 = {r["pmid"]: pm for pm, r in _RECS83.items()}
_GET83 = []
_REAL_GET83 = _fig._get_bytes


def _mk_get83(zips=None, raise_exc=None, hook=None):
    """_get_bytes FALSO con la MISMA firma (url, timeout, max_bytes, dest=None): escribe el zip fixture en `dest` (0 red)."""
    zips = _ZIPS83 if zips is None else zips

    def _fake(url, timeout, max_bytes, dest=None):
        _GET83.append({"url": url, "timeout": timeout, "max_bytes": max_bytes, "dest": str(dest)})
        if hook is not None:
            hook(url)
        if raise_exc is not None:
            raise raise_exc
        zb = zips[url.rsplit("/", 2)[-2]]
        Path(dest).write_bytes(zb)
        return {"status": "ok", "http_status": 200, "content_length": len(zb), "content_type": "application/zip",
                "bytes": len(zb), "elapsed_s": 0.02, "url": url, "path": str(dest)}
    return _fake


def _sources83(pmcids, with_xml=True):
    """Fuentes fake de la Ruta B: EPMC devuelve los recs pedidos; fetch_external deja .txt (excerpt) + el XML fixture en raw_cached
    (rutas ABSOLUTAS → figures.locate_xml); PubMed vacío, ZFIN de siempre, Layer 0 no-match."""
    recs = [_RECS83[p] for p in pmcids]

    def _epmc(query, n=5, sort=None, synonym=True):
        return list(recs), {"source": "europepmc", "status": "success", "query_sent": query, "n_found": len(recs),
                            "n_returned": len(recs), "elapsed_s": 0.01, "sort": "RELEVANCE", "synonym": True,
                            "throttle": "net_throttle", "throttle_slept_s": 0.0, "contact": "unset"}

    def _fetch(ident, want_full_text=True):
        pmcid = _PMID2PMC83.get(str(ident).replace("PMID:", ""))
        if pmcid is None:
            return {"found": False, "fetch_error": "not in ADR-0083 fixture"}
        txt = TMP / f"raw_paper_{pmcid}_20260613.txt"
        txt.write_text(_FULLTEXT, encoding="utf-8")
        cached = [str(txt)] + ([str(_XMLS83[pmcid])] if with_xml else [])
        return {"found": True, "full_text": True, "n_chunks": 4, "raw_cached": cached, "raw_ref": None,
                "record": {"abstract": _RECS83[pmcid]["abstract"]}, "cache_hit": True, "cached_at": "2026-06-13T00:00:00Z",
                "cached_at_source": "fetched_at", "cache_age_days": 95.0}
    answer_pipeline.fetch_paper.search_europepmc_ledger = _epmc
    answer_pipeline.fetch_paper.fetch_external = _fetch
    answer_pipeline._WS_CACHE[("pubmed_literature.py", "query_pubmed")] = _fake_pubmed_empty
    answer_pipeline._WS_CACHE[("zfin_zebrafish.py", "query_zfin")] = _fake_zfin
    _inject_l0("no-match")


_PANEL83 = []     # lo que recibió CADA llamada al caller del panel: lente, figuras en el member, regla en el system, b64 en el texto
_SYNTH83 = []     # lo que recibió CADA pasada del sintetizador: la evidencia (dict + json) — el sintetizador JAMÁS ve bytes


def _panel83(verdicts, readings=False, cs=None, rounds=None):
    """Caller del panel que REGISTRA member['figures'] (F3 las pone SÓLO en las lentes con visión), si el system lleva
    FIGURE_READING_RULE y si la b64 del fixture se coló en user_text. `readings=True` → las lentes con figuras emiten
    figure_readings (juicio); `rounds` = [verdicts_panel1, verdicts_panel2] para forzar REVISE y luego APPROVE.
    `evidence_has_figures_key` mira SÓLO la evidencia del user_text (el panel SÍ recibe deterministic_checks.figures {state}:
    una de las 3 excepciones declaradas bajo kill-switch)."""
    calls = {}

    def _caller(member, system, user_text):
        figs = [f for f in member.get("figures") or []] if isinstance(member.get("figures"), list) else []
        rule = getattr(composite_auditor, "FIGURE_READING_RULE", None)
        try:
            ev_json = json.dumps(json.loads(user_text).get("evidence"), ensure_ascii=False)
        except Exception:
            ev_json = user_text
        _PANEL83.append({"lens": member["lens"], "reviewer": member["reviewer"], "n_figures": len(figs),
                         "shas": [f.get("sha256") for f in figs], "b64_in_user_text": _G001_B64 in user_text,
                         "rule_in_system": bool(rule) and rule in system, "attempt": member.get("attempt"),
                         "evidence_has_figures_key": '"figures"' in ev_json})
        calls[member["lens"]] = calls.get(member["lens"], 0) + 1
        vtab = rounds[min(calls[member["lens"]], len(rounds)) - 1] if rounds else verdicts
        v = vtab[member["lens"]]
        if isinstance(v, Exception):
            raise v
        out = {"verdict": v, "caught": f"({member['lens']}) finding" if v != "APPROVE" else "", "correction_applied": "",
               "confidence": 0.9, "reasons": [f"{member['lens']} reason"] if v != "APPROVE" else []}
        if member["lens"] == "evidence-grounding" and cs is not None:
            out["citation_support"] = list(cs)
        if readings and figs:
            out["figure_readings"] = [{"fig_id": f["fig_id"], "reading": "panel judgment: image consistent with its caption",
                                       "consistent_with_caption": True} for f in figs[:2]]
        return out, {"input_tokens": 10, "output_tokens": 5}
    return _caller


_CIT_PASS1_83 = [{"kind": "di-record", "id": "CORPUS-2026-0001"}]   # pass1 es DI-only: una figura citada ahí sería alucinada (F.1)


def _synth83(answer_text, cited, conf=None, absence_kind="not-applicable", rev_text=None):
    """Sintetizador stub con la firma NUEVA: pass1 cita SÓLO la DI (no ha visto figuras — citar una en pass1 es un id no resuelto y
    F2 lo hace inadmisible, con razón); pass2/revisión citan `cited` (papers + figuras de la Ruta B)."""
    conf = conf or {"pass1": 0.8, "pass2": 0.85, "revision": 0.85}

    def _s(question, evidence, pass_label, thread_context=None, human_attestations=None):
        _SYNTH83.append({"pass": pass_label, "evidence": evidence, "json": json.dumps(evidence, ensure_ascii=False, default=str)})
        out = _mk_synth(conf)(question, evidence, pass_label)
        out["direct_answer"] = (rev_text or answer_text) if pass_label == "revision" else answer_text
        out["evidence_cited"] = json.loads(json.dumps(_CIT_PASS1_83 if pass_label == "pass1" else cited))
        out["absence_kind"] = absence_kind
        return out
    return _s


def _run83(question, synth, panel=None, env=None, pmcids=("PMC11379296",), with_xml=True, get=None, before=None):
    """Corrida por la PUERTA sin plan (no competente por ruta → harness → Ruta B) con las fuentes fake de figuras y _get_bytes
    falso; `env` sólo durante la corrida. Devuelve (run_id, frozen|None, events, row)."""
    env = dict(env or {})
    saved = {k: os.environ.get(k) for k in env}
    for k, v in env.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    _fig._get_bytes = get or _mk_get83()
    _GET83.clear(); _PANEL83.clear(); _SYNTH83.clear()
    try:
        _sources83(pmcids, with_xml=with_xml)
        rv = app.create_run(app.RunBody(question=question, entities=["wt1a"]), authorization=AUTH)
        rid = rv["run_id"]
        if before is not None:
            before(rid)
        claimed = db.claim_next_queued(worker_id="run-worker-adr0083")
        assert claimed and claimed["run_id"] == rid, "FIFO: la corrida reclamada debe ser la esperada"
        runs_mod.execute_run(claimed, synthesizer=synth, panel_caller=panel or _panel83(ALL_A))
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        _fig._get_bytes = _REAL_GET83
    row = db.get_run(rid)
    frozen = json.loads(row["frozen_record_json"]) if row.get("frozen_record_json") else None
    return rid, frozen, app.get_events(rid, after=0, authorization=AUTH)["events"], row


def _walk_keys83(obj, acc=None):
    acc = set() if acc is None else acc
    if isinstance(obj, dict):
        for k, v in obj.items():
            acc.add(k)
            _walk_keys83(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _walk_keys83(v, acc)
    return acc


def _walk_types83(obj, key, acc=None):
    """Tipos (nombre) de TODOS los valores bajo la llave `key`, a cualquier profundidad."""
    acc = [] if acc is None else acc
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                acc.append(type(v).__name__)
            _walk_types83(v, key, acc)
    elif isinstance(obj, list):
        for v in obj:
            _walk_types83(v, key, acc)
    return acc


def _diff83(a, b, prefix=""):
    """Rutas (dotted) donde dos registros difieren — llaves ausentes de un lado incluidas."""
    out = set()
    if isinstance(a, dict) and isinstance(b, dict):
        for k in set(a) | set(b):
            if k not in a or k not in b:
                out.add(f"{prefix}{k}")
            else:
                out |= _diff83(a[k], b[k], f"{prefix}{k}.")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.add(prefix.rstrip(".") + "[len]")
        for i, (x, y) in enumerate(zip(a, b)):
            out |= _diff83(x, y, f"{prefix.rstrip('.')}[{i}].")
    elif a != b:
        out.add(prefix.rstrip("."))
    return out


_ADDITIVE_112_KEYS = {"saw_figures", "figure_readings", "figure_readings_class", "figure_readings_dropped", "vision",
                      "figure_verification", "figure_citations", "from_vision_lens",
                      "citation_support_vision_informed"}     # corrector: la fila con citation_support declara si vio imágenes (M.1: ausente bajo kill-switch)
_IDENTITY_KEYS83 = ("run_id", "measured_at", "bundle_identity", "thread")   # difieren entre DOS corridas del mismo fixture


def _drop_key83(obj, key):
    """Quita `key` en CUALQUIER profundidad (thread_id = run_id de la raíz: identidad de corrida, viaja anidado en
    deterministic_checks.thread y episode_axes.provenance.turn)."""
    if isinstance(obj, dict):
        obj.pop(key, None)
        for v in obj.values():
            _drop_key83(v, key)
    elif isinstance(obj, list):
        for v in obj:
            _drop_key83(v, key)
    return obj


def _strip83(rec):
    """El registro SIN las llaves aditivas 1.12 ni las de identidad de corrida — para medir que el kill-switch no cambia NADA más."""
    r = json.loads(json.dumps(rec))
    for k in _IDENTITY_KEYS83 + ("figures",):
        r.pop(k, None)
    _drop_key83(r, "thread_id")
    r["deterministic_checks"].pop("figures", None)
    r["agents_invoked"] = [a for a in r["agents_invoked"] if a["agent"] != runs_mod.FIGURES_AGENT_ROW]
    for k in ("approved", "rejected"):
        r["audit"][k] = [x for x in r["audit"][k] if "#" not in str(x)]   # D.3: los ids de figura entran a evidence_ids
    # D.3 (misma consecuencia): record_audit escribe los ids aprobados en la PROSA de decision_state.required_next_action
    import re as _re83
    r["decision_state"]["required_next_action"] = _re83.sub(r"'PMC\d+#[^']*', ?", "", r["decision_state"]["required_next_action"])
    r["audit"].pop("vision", None)
    for row in r["audit"]["panel"]:
        for k in ("saw_figures", "figure_readings", "figure_readings_class", "figure_readings_dropped",
                  "citation_support_vision_informed"):      # corrector: declara si la fila con citation_support vio imágenes (ausente bajo kill-switch)
            row.pop(k, None)
    for c in r["citations"]:
        for k in ("figure_verification", "resolved", "resolved_to", "passage_delivered", "supported", "support_state"):
            c.pop(k, None)   # la escalera de la cita kind figure cambia de peldaño con figuras (F2 la indexa): consecuencia, no fuga
    r["citations_support_summary"].pop("figure_citations", None)
    r["citations_support_summary"].pop("by_state", None)
    for m in r["token_usage"]["by_stage"]["panel"]["by_model"].values():
        m.pop("vision", None)
    r["token_usage"].pop("figures", None)   # F8 (H): usage_json.figures = espejo de frozen.figures (aditiva 1.12; ausente bajo kill-switch)
    return r


_ANS_A83 = "wt1a marks the zebrafish pronephros [1]; Fig 1 illustrates the expression domain described in its caption [2]."
_CIT_A83 = [{"kind": "paper", "id": "PMID:39230001"}, {"kind": "figure", "id": _G001_ID}]
_CS_A83 = [{"n": 1, "verdict": "supported"}, {"n": 2, "verdict": "supported"}]
_Q_A83 = "ADR-0083 a: does wt1a mark the pronephros (figures CC BY)?"

# --- estático: contrato, tool del sintetizador, gate de llaves de prompt, snapshot ------------------------------------------------
check("ADR-0083 (L) RENDER_CONTRACT_VERSION apilado sobre 1.12 (hoy '1.13', ADR-0084); FIGURES_DECLARED_EXCEPTIONS son EXACTAMENTE 3 (M.1)",
      runs_mod.RENDER_CONTRACT_VERSION == "1.13"
      and runs_mod.FIGURES_DECLARED_EXCEPTIONS == ("render_contract_version", "figures", "deterministic_checks.figures"))
check("ADR-0083 (D.2) SYNTH_TOOL: evidence_cited.items.kind.enum gana 'figure' y la description exige marcadores [n] y prohíbe afirmar "
      "lo que sólo existe en la imagen (literal); synth_system NO cambia (la serie ab_trapped_scalar sigue comparable)",
      "figure" in runs_mod.SYNTH_TOOL["input_schema"]["properties"]["evidence_cited"]["items"]["properties"]["kind"]["enum"]
      and "kind 'figure' = '<PMCID>#<fig_id>'" in runs_mod.SYNTH_TOOL["description"]
      and "never state a number or observation that exists only in an image" in runs_mod.SYNTH_TOOL["description"]
      and "Cite inline as [n] in direct_answer" in runs_mod.SYNTH_TOOL["description"]
      and "figure" not in runs_mod.synth_system("pass2"))
check("ADR-0083 (D.1) gate ESTÁTICO independiente de fixtures: _PROMPT_FIGURE_KEYS == figures.PROMPT_FIGURE_KEYS (11) y ∩ "
      "{cache_path, cache_path_rel, raw_ref, b64, data, bytes_b64} == ∅",
      runs_mod._PROMPT_FIGURE_KEYS == _fig.PROMPT_FIGURE_KEYS and len(runs_mod._PROMPT_FIGURE_KEYS) == 11
      and not set(runs_mod._PROMPT_FIGURE_KEYS) & {"cache_path", "cache_path_rel", "raw_ref", "b64", "data", "bytes_b64"}
      and runs_mod._FORBIDDEN_PROMPT_FIGURE_KEYS == _fig.FORBIDDEN_PROMPT_KEYS)
_snap83 = models.snapshot(extra=runs_mod.snapshot_extra())
check("ADR-0083 (O.5) el snapshot de configuración trae figures.enabled / figures.vision {value True, source default-unset:WITT_FIGURES[_VISION]} "
      "DERIVADOS por models (F3: SNAPSHOT_FIELDS += figures.*); runs.snapshot_extra() sigue cubriendo EXACTAMENTE models.EXTRA_FIELDS "
      "(no duplica campos que models deriva: extra_ignored [])",
      _snap83["fields"]["figures.enabled"] == {"value": True, "source": "default-unset:WITT_FIGURES"}
      and _snap83["fields"]["figures.vision"] == {"value": True, "source": "default-unset:WITT_FIGURES_VISION"}
      and set(runs_mod.snapshot_extra()) == set(models.EXTRA_FIELDS) and _snap83.get("extra_ignored") == [],
      json.dumps({k: _snap83["fields"].get(k) for k in ("figures.enabled", "figures.vision")}))

# --- (a) corrida con figuras CC BY: 9 parseadas, 9 verificadas, 9 embebibles; cita kind figure + cita paper -------------------------
_rid_fa, _rec_fa, _ev_fa, _row_fa = _run83(_Q_A83, _synth83(_ANS_A83, _CIT_A83), panel=_panel83(ALL_A, readings=True, cs=_CS_A83))
_fg_a = _rec_fa["figures"]
_t_fa = _ev_types(_ev_fa)
_fig_ev_a = [e for e in _ev_fa if e["type"].startswith("stage.figures.")]
_plan_ev_a = _ev_payloads(_ev_fa, "stage.figures.plan")
_paper_ev_a = _ev_payloads(_ev_fa, "stage.figures.paper")
_figure_ev_a = _ev_payloads(_ev_fa, "stage.figures.figure")
_sum_ev_a = _ev_payloads(_ev_fa, "stage.figures.summary")
_items_a = _fg_a["items"]
check("ADR-0083 (L) contrato en el registro (hoy '1.13'); keyset top-level == 1.11 (47 + council) + {figures} + {web_locator} (ADR-0084); "
      "deterministic_checks gana `figures`; la corrida cerró awaiting_closure con Ruta B por la compuerta (no competente sin plan)",
      _rec_fa["render_contract_version"] == "1.13" and set(_rec_fa) == _FROZEN_1_10_KEYS | {"council", "figures", "web_locator"}
      and "figures" in _rec_fa["deterministic_checks"] and _row_fa["state"] == "awaiting_closure"
      and _rec_fa["fallback"]["trigger"] == "competence",
      json.dumps({"extra": sorted(set(_rec_fa) - _FROZEN_1_10_KEYS - {"council", "figures", "web_locator"}), "state": _row_fa["state"]}))
check("ADR-0083 (C) ORDEN de la Traza: stage.path_b < stage.figures.plan < paper{start} < paper{done} < figure×9 < stage.figures.summary "
      "< stage.synthesize.pass2; todos los stage.figures.* con agent 'figures'; 1 plan · 2 paper · 9 figure · 1 summary",
      _t_fa.index("stage.path_b") < _t_fa.index("stage.figures.plan") < _t_fa.index("stage.figures.paper")
      < max(i for i, t in enumerate(_t_fa) if t == "stage.figures.paper") < _t_fa.index("stage.figures.summary")
      < _t_fa.index("stage.synthesize.pass2")
      and all(_t_fa.index("stage.figures.paper") < i < _t_fa.index("stage.figures.summary")
              for i, t in enumerate(_t_fa) if t == "stage.figures.figure")
      and all(e["agent"] == "figures" for e in _fig_ev_a)
      and [len(_plan_ev_a), len(_paper_ev_a), len(_figure_ev_a), len(_sum_ev_a)] == [1, 2, 9, 1],
      json.dumps([t for t in _t_fa if t.startswith(("stage.path_b", "stage.figures", "stage.synthesize.pass2"))]))
check("ADR-0083 (C) stage.figures.plan ANTES de bajar: n_papers_eligible 1 / n_papers_selected 1, caps (8 con {value, source}), "
      "budget_s 90, cache_dir_state 'writable' + cache_dir_source 'env', vision {enabled, lenses [grounding, reproducibility], "
      "lenses_source default-unset, max_per_lens 12, detail 'high'}, versiones y mecanismo declarados",
      _plan_ev_a[0]["n_papers_eligible"] == 1 and _plan_ev_a[0]["n_papers_selected"] == 1
      and set(_plan_ev_a[0]["caps"]) == {"max_papers", "max_per_paper", "max_per_run", "max_per_lens", "max_image_mb",
                                          "request_b64_mb", "zip_max_mb", "caption_chars"}
      and all(set(v) == {"value", "source"} for v in _plan_ev_a[0]["caps"].values())
      and _plan_ev_a[0]["budget_s"] == 90.0 and _plan_ev_a[0]["cache_dir_state"] == "writable"
      and _plan_ev_a[0]["cache_dir_source"] == "env"
      and _plan_ev_a[0]["vision"] == {"enabled": True, "lenses": _LENSES_V83, "lenses_source": "default-unset:WITT_FIGURES_VISION_LENSES",
                                       "max_per_lens": 12, "detail": "high"}
      and _plan_ev_a[0]["module_version"] == "fig-1" and _plan_ev_a[0]["parser_version"] == "jats-fig-1"
      and _plan_ev_a[0]["license_table_version"] == "lt-1" and _plan_ev_a[0]["mechanism"] == "supplementaryFiles-zip",
      json.dumps({k: _plan_ev_a[0][k] for k in ("n_papers_eligible", "n_papers_selected", "cache_dir_state", "vision")}))
check("ADR-0083 (C) stage.figures.paper: {phase 'start', heartbeat True, pmcid, evidence_id 'PMID:39230001', n_figs_in_xml 9, n_selected 9} "
      "ANTES de la descarga y {phase 'done', license {cc-by, ext-link}, mechanism, http_status 200, zip_bytes == len(zip), n_extracted 9, "
      "n_missing 0, status 'success', cache_hit False, elapsed_s} después; UNA GET a figures._zip_url(PMC11379296)",
      _paper_ev_a[0]["phase"] == "start" and _paper_ev_a[0]["heartbeat"] is True and _paper_ev_a[0]["pmcid"] == "PMC11379296"
      and _paper_ev_a[0]["evidence_id"] == "PMID:39230001" and _paper_ev_a[0]["n_figs_in_xml"] == 9 and _paper_ev_a[0]["n_selected"] == 9
      and _paper_ev_a[1]["phase"] == "done" and _paper_ev_a[1]["license"] == {"id": "cc-by", "source": "ext-link"}
      and _paper_ev_a[1]["mechanism"] == "supplementaryFiles-zip" and _paper_ev_a[1]["http_status"] == 200
      and _paper_ev_a[1]["zip_bytes"] == len(_ZIP_BY83) and _paper_ev_a[1]["n_extracted"] == 9 and _paper_ev_a[1]["n_missing"] == 0
      and _paper_ev_a[1]["status"] == "success" and _paper_ev_a[1]["cache_hit"] is False and "elapsed_s" in _paper_ev_a[1]
      and len(_GET83) == 1 and _GET83[0]["url"] == _fig._zip_url("PMC11379296"),
      json.dumps({"start": _paper_ev_a[0], "get": _GET83}, default=str)[:400])
check("ADR-0083 (C) 9 eventos stage.figures.figure {id, sha256 == MANIFEST, media_type image/jpeg, bytes, dims_measured == scaled "
      "(dims_match True), bytes_state 'verified', embeddable True, panel_view True, heartbeat True} y stage.figures.summary "
      "{state 'attached', n_figures 9, n_verified 9, n_embeddable 9, n_not_fetched 0, n_unknown_license 0, budget, evicted_n 0}",
      [e["id"] for e in _figure_ev_a] == _FIG_IDS83
      and all(e["sha256"] == _MAN_BY83[e["id"].split("#")[1] + ".jpg"]["sha256"] for e in _figure_ev_a)
      and all(e["media_type"] == "image/jpeg" and e["dims_match"] is True and e["bytes_state"] == "verified"
              and e["embeddable"] is True and e["panel_view"] is True and e["heartbeat"] is True for e in _figure_ev_a)
      and all(e["dims_measured"] == _MAN_BY83[e["id"].split("#")[1] + ".jpg"]["dims"] for e in _figure_ev_a)
      and _sum_ev_a[0]["state"] == "attached" and _sum_ev_a[0]["n_figures"] == 9 and _sum_ev_a[0]["n_verified"] == 9
      and _sum_ev_a[0]["n_embeddable"] == 9 and _sum_ev_a[0]["n_not_fetched"] == 0 and _sum_ev_a[0]["n_unknown_license"] == 0
      and _sum_ev_a[0]["evicted_n"] == 0 and _sum_ev_a[0]["over_budget"] is False and "budget" in _sum_ev_a[0],
      json.dumps(_sum_ev_a[0], default=str)[:300])
check("ADR-0083 (L) frozen.figures cabecera: state 'attached', fig-1 / jats-fig-1 / lt-1, mechanism, cache {dir_source 'env', dir_state "
      "'writable', ttl_days 30, cache_max_mb 512, evicted_n 0}, budget {total_s 90, used_s >= 0, over_budget False}, caps == los del plan, "
      "1/1/1 papers, n_figures 9, n_with_caption 9, n_fetched 9, n_verified 9, n_not_fetched 0, n_mismatch 0, n_embeddable 9, "
      "n_panel_view 9, n_unknown_license 0, n_cited 1, zfin_figures_state literal, selection.rule literal, SIN `papers`",
      _fg_a["state"] == "attached" and _fg_a["module_version"] == "fig-1" and _fg_a["parser_version"] == "jats-fig-1"
      and _fg_a["license_table_version"] == "lt-1" and _fg_a["mechanism"] == "supplementaryFiles-zip"
      and _fg_a["cache"] == {"dir_source": "env", "dir_state": "writable", "ttl_days": 30.0, "cache_max_mb": 512.0, "evicted_n": 0}
      and _fg_a["budget"]["total_s"] == 90.0 and _fg_a["budget"]["used_s"] >= 0 and _fg_a["budget"]["over_budget"] is False
      and _fg_a["caps"] == _plan_ev_a[0]["caps"]
      and (_fg_a["n_papers_eligible"], _fg_a["n_papers_selected"], _fg_a["n_papers_with_xml"]) == (1, 1, 1)
      and (_fg_a["n_figures"], _fg_a["n_with_caption"], _fg_a["n_fetched"], _fg_a["n_verified"]) == (9, 9, 9, 9)
      and (_fg_a["n_not_fetched"], _fg_a["n_mismatch"], _fg_a["n_embeddable"], _fg_a["n_panel_view"]) == (0, 0, 9, 9)
      and _fg_a["n_unknown_license"] == 0 and _fg_a["n_cited"] == 1
      and _fg_a["zfin_figures_state"] == _fig.ZFIN_FIGURES_STATE == "not-available (zfin_zebrafish payload carries no ZDB-FIG ids at 9d90c01)"
      and _fg_a["selection"]["rule"] == _fig.SELECTION_RULE and "papers" not in _fg_a
      and _fig.figures_state_in_vocabulary(_fg_a["state"]),
      json.dumps({k: _fg_a[k] for k in ("state", "n_figures", "n_verified", "n_embeddable", "n_panel_view", "n_cited", "cache")}))
check("ADR-0083 (L/A.3) frozen.figures.license_table EFECTIVA (cc-by embed True; cc-by-nc embed False panel_view True; unknown embed False "
      "panel_view False fetch_bytes True; zfin todo False), license_table_rule literal, env_ignored [], vocabulary == figures.VOCABULARY (17)",
      _fg_a["license_table"]["cc-by"]["embed"] is True and _fg_a["license_table"]["cc-by-nc"] ["embed"] is False
      and _fg_a["license_table"]["cc-by-nc"]["panel_view"] is True and _fg_a["license_table"]["unknown"]["embed"] is False
      and _fg_a["license_table"]["unknown"]["panel_view"] is False and _fg_a["license_table"]["unknown"]["fetch_bytes"] is True
      and _fg_a["license_table"]["zfin-display-only"]["fetch_bytes"] is False
      and _fg_a["license_table_rule"] == _fig.LICENSE_TABLE_RULE and _fg_a["license_table_env_ignored"] == []
      and _fg_a["vocabulary"] == json.loads(json.dumps(_fig.VOCABULARY)) and len(_fg_a["vocabulary"]) == 17)
check("ADR-0083 (L) items[]: 9 FigureItem con las 33 llaves en el ORDEN exacto de figures.FIGURE_ITEM_KEYS; ids g001..g009; sha256 == MANIFEST; "
      "media_type image/jpeg == mime_from_extension; dims_match True; license {cc-by, ext-link, rule_no 2, article-level}; embeddable y "
      "panel_view True; bytes_state 'verified' (vocabulario); raw_ref = source-pointer con source_url; cache_path_rel 'PMC11379296/<href>'; "
      "cache_hit False; delivered_to_synthesizer True; caption_in_excerpt bool; class literal; cited_by_answer g001 == [2], resto []",
      len(_items_a) == 9 and all(tuple(it) == _fig.FIGURE_ITEM_KEYS for it in _items_a)
      and [it["id"] for it in _items_a] == _FIG_IDS83
      and all(it["sha256"] == _MAN_BY83[it["graphic_href"]]["sha256"] and it["sha256_short"] == it["sha256"][:12] for it in _items_a)
      and all(it["media_type"] == "image/jpeg" == it["mime_from_extension"] and it["dims_match"] is True for it in _items_a)
      and all(it["license"]["id"] == "cc-by" and it["license"]["source"] == "ext-link" and it["license"]["rule_no"] == 2
              and it["license"]["scope"] == "article-level" for it in _items_a)
      and all(it["embeddable"] is True and it["panel_view"] is True and it["bytes_state"] == "verified" for it in _items_a)
      and all(_fig.bytes_state_in_vocabulary(it["bytes_state"]) for it in _items_a)
      and all(isinstance(it["raw_ref"], dict) and it["raw_ref"].get("source_url") == it["source_url"] for it in _items_a)
      and all(it["cache_path_rel"] == f"PMC11379296/{it['graphic_href']}" and it["cache_hit"] is False for it in _items_a)
      and all(it["delivered_to_synthesizer"] is True and isinstance(it["caption_in_excerpt"], bool) for it in _items_a)
      and all(it["class"] == _fig.FIGURE_CLASS for it in _items_a)
      and _items_a[0]["cited_by_answer"] == [2] and all(it["cited_by_answer"] == [] for it in _items_a[1:]),
      json.dumps({"keys_ok": all(tuple(it) == _fig.FIGURE_ITEM_KEYS for it in _items_a), "cited": [it["cited_by_answer"] for it in _items_a]}))
_frozen_json_a = json.dumps(_rec_fa, ensure_ascii=False)
_bundle_json_a = _row_fa["bundle_json"]
_bin83 = {"frozen_b64": any(b in _frozen_json_a for b in _B64_BY83.values()),
          "bundle_b64": any(b in _bundle_json_a for b in _B64_BY83.values()),
          "data_image": ("data:image" in _frozen_json_a) or ("data:image" in _bundle_json_a),
          "synth_b64": any(any(b in s["json"] for b in _B64_BY83.values()) or "data:image" in s["json"] for s in _SYNTH83),
          "forbidden_keys": sorted(_walk_keys83(_rec_fa) & {"b64", "cache_path"}),
          # `bytes_b64` es el CONTADOR entero de (H) (by_model[*].vision.bytes_b64), jamás contenido: se mide que sea int
          "bytes_b64_non_int": [t for t in _walk_types83(_rec_fa, "bytes_b64") if t != "int"],
          "panel_b64": any(p["b64_in_user_text"] for p in _PANEL83)}
check("ADR-0083 (D.1/M.6) NADA BINARIO: ninguna b64 de las 9 figuras ni 'data:image' en frozen_record_json, en bundle_json ni en el user_text "
      "de NINGUNA pasada del sintetizador; ninguna llave b64/cache_path en el frozen (cache_path_rel SÍ viaja: es ruta, no bytes; bytes_b64 es "
      "el contador int de (H)); panel: la b64 jamás en user_text (F3 la manda en bloques, no en el texto)",
      not _bin83["frozen_b64"] and not _bin83["bundle_b64"] and not _bin83["data_image"] and not _bin83["synth_b64"]
      and _bin83["forbidden_keys"] == [] and _bin83["bytes_b64_non_int"] == [] and not _bin83["panel_b64"],
      json.dumps(_bin83))
_ev_p1 = next(s for s in _SYNTH83 if s["pass"] == "pass1")["evidence"]
_ev_p2 = next(s for s in _SYNTH83 if s["pass"] == "pass2")["evidence"]
_p2_paper = next(p for p in _ev_p2["path_b"]["papers"] if p.get("source") == "europepmc")
check("ADR-0083 (D.1) pass1 es DI-only (path_b.included False, sin figuras); pass2 recibe papers[].figures {state 'attached', n 9, "
      "n_delivered 9, items 9 × EXACTAMENTE PROMPT_FIGURE_KEYS} con license {id, source} y caption íntegro — sin cache_path_rel/raw_ref/b64; "
      "el paper ZFIN no gana `figures`",
      _ev_p1["path_b"].get("included") is False and '"figures"' not in json.dumps(_ev_p1)
      and _p2_paper["figures"]["state"] == "attached" and _p2_paper["figures"]["n"] == 9 and _p2_paper["figures"]["n_delivered"] == 9
      and len(_p2_paper["figures"]["items"]) == 9
      and all(set(it) == set(_fig.PROMPT_FIGURE_KEYS) for it in _p2_paper["figures"]["items"])
      and all(set(it["license"]) == {"id", "source"} and it["license"]["id"] == "cc-by" for it in _p2_paper["figures"]["items"])
      and _p2_paper["figures"]["items"][0]["caption"] == _items_a[0]["caption"]
      and not any(p.get("source") == "zfin" and "figures" in p for p in _ev_p2["path_b"]["papers"]),
      json.dumps(sorted(_p2_paper["figures"]["items"][0])))
_cit_a = _rec_fa["citations"]
_fc_a = _rec_fa["citations_support_summary"].get("figure_citations")
check("ADR-0083 (E) la cita [2] kind 'figure' gana figure_verification {bytes 'verified', content ∈ vocabulario, figure_id '<PMCID>#<fig_id>'}; "
      "la cita paper NO la gana; citations_support_summary.figure_citations {n 1, n_verified_bytes 1, n_not_fetched 0, n_mismatch 0, n_unresolved 0}",
      _cit_a[1]["kind"] == "figure" and _cit_a[1]["id"] == _G001_ID
      and _cit_a[1]["figure_verification"]["bytes"] == "verified" and _cit_a[1]["figure_verification"]["figure_id"] == _G001_ID
      and _cit_a[1]["figure_verification"]["content"] in runs_mod.FIGURE_CONTENT_STATES
      and "figure_verification" not in _cit_a[0]
      and _cit_a[1]["figure_verification"]["kind_reported"] == "figure"
      and _fc_a == {"n": 1, "n_verified_bytes": 1, "n_not_fetched": 0, "n_error": 0, "n_mismatch": 0, "n_unresolved": 0, "n_other": 0,
                    "n_figure_shaped_other_kind": 0},
      json.dumps({"fv": _cit_a[1].get("figure_verification"), "fc": _fc_a}))
check("[F3] ADR-0083 (E) content 'panel-judgment' ⇔ una lente con visión emitió figure_readings para g001 (el fake las emite cuando recibe "
      "figuras) — hasta que F3 aterrice el fake no recibe figuras y el contenido queda 'not-evaluated'",
      _cit_a[1]["figure_verification"]["content"] == "panel-judgment",
      _cit_a[1]["figure_verification"]["content"])
check("[F2] ADR-0083 (E) la cita kind figure sube la escalera de ADR-0080 sin peldaños nuevos: resolved True (verify_output indexa cada "
      "papers[].figures.items[] como ítem propio) y support_state ∈ {passage_delivered, supported} (caption entregado; grounding 'supported')",
      _cit_a[1].get("resolved") is True and _cit_a[1].get("support_state") in ("passage_delivered", "supported"),
      json.dumps({k: _cit_a[1].get(k) for k in ("resolved", "passage_delivered", "support_state")}))
_dcf_a = _rec_fa["deterministic_checks"]["figures"]
check("[F2] ADR-0083 (F) deterministic_checks.figures: state 'checked' con los 5 predicados {figure_id_resolves, figure_sha_matches, "
      "figure_only_not_asserted, figure_numerals_grounded, figure_license_known}, rules (5) y decided_by 'code'; la corrida (a) es admisible "
      "(figura + paper del mismo artículo, sha cuadra) — hasta F2 el fragmento dice 'tool-unavailable (verify_output.figure_predicates …)'",
      _dcf_a.get("state") == "checked" and _dcf_a.get("decided_by") == "code"
      and {"figure_id_resolves", "figure_sha_matches", "figure_only_not_asserted", "figure_numerals_grounded",
           "figure_license_known", "rules"} <= set(_dcf_a) and _rec_fa["deterministic_checks"]["admissible"] is True,
      json.dumps(_dcf_a)[:300])
check("ADR-0083 (F, cableado tolerante) deterministic_checks.figures SIEMPRE trae `state` (string, vocabulario declarado: 'checked' | "
      "'no-figure-citations' | 'kill-switch WITT_FIGURES=0' | 'tool-unavailable (…)' | 'error: …'); el evento stage.deterministic_gate "
      "gana figures_state == state; la conjunción de hoy sigue admisible (ningún predicado inventado)",
      isinstance(_dcf_a.get("state"), str)
      and (_dcf_a["state"] in ("checked", "no-figure-citations", "kill-switch WITT_FIGURES=0")
           or _dcf_a["state"].startswith(("tool-unavailable (", "error: ")))
      and all(p.get("figures_state") == p["figures"]["state"] for p in _ev_payloads(_ev_fa, "stage.deterministic_gate"))
      and _rec_fa["deterministic_checks"]["admissible"] is True,
      _dcf_a["state"])
_ag_a = _rec_fa["agents_invoked"]
_ag_fig_a = next((a for a in _ag_a if a["agent"] == runs_mod.FIGURES_AGENT_ROW), None)
check("ADR-0083 (L) agents_invoked fila 'figures (lib/figures.py — JATS parser + fetch by sha + license gate)' DERIVADA por código: status "
      "'invoked', invocation_id 'figures:9/9', evidence_generated [parsed:9, verified:9, embeddable:9, lenses:evidence-grounding,"
      "reproducibility, synthesizer:captions-only]; tercera fila (tras composite-auditor y verify_output)",
      _ag_fig_a is not None and _ag_fig_a["status"] == "invoked" and _ag_fig_a["invocation_id"] == "figures:9/9"
      and _ag_fig_a["evidence_generated"] == ["parsed:9", "verified:9", "embeddable:9", "lenses:evidence-grounding,reproducibility",
                                              "synthesizer:captions-only"]
      and _ag_a[2] is _ag_fig_a and "reason" not in _ag_fig_a,
      json.dumps(_ag_fig_a))
_view_fa = app.get_run(_rid_fa, authorization=AUTH)
check("ADR-0083 (L, vista) epistemic_summary += figures_state 'attached', figures_n_verified 9, figures_n_cited 1 (derivados AL CONGELAR; "
      "la lista no re-deriva) == frozen.figures.{state, n_verified, n_cited}",
      _view_fa["epistemic_summary"]["figures_state"] == "attached" == _fg_a["state"]
      and _view_fa["epistemic_summary"]["figures_n_verified"] == 9 == _fg_a["n_verified"]
      and _view_fa["epistemic_summary"]["figures_n_cited"] == 1 == _fg_a["n_cited"],
      json.dumps({k: _view_fa["epistemic_summary"].get(k) for k in ("figures_state", "figures_n_verified", "figures_n_cited")}))
_judge_a = _ev_payloads(_ev_fa, "stage.audit.judge")
check("ADR-0083 (L) stage.audit.judge += figures_sent (int) y figures_sha256 (lista) en las 4 filas, MEDIDOS del member entregado al caller",
      len(_judge_a) == 4 and all(isinstance(p["figures_sent"], int) and isinstance(p["figures_sha256"], list) for p in _judge_a)
      and all(len(p["figures_sha256"]) == p["figures_sent"] for p in _judge_a),
      json.dumps([(p["lens"], p["figures_sent"]) for p in _judge_a]))
_by_lens_a = {p["lens"]: p for p in _PANEL83}
check("[F3] ADR-0083 (G.2) caller espía: SOLO evidence-grounding y reproducibility reciben member['figures'] (9, sha == frozen), correctness "
      "y overclaim 0; su system lleva FIGURE_READING_RULE y los otros dos NO; stage.audit.judge.figures_sent coincide 9/9/0/0",
      {l: p["n_figures"] for l, p in _by_lens_a.items()} == {"correctness": 0, "overclaim": 0, "evidence-grounding": 9, "reproducibility": 9}
      and all(set(_by_lens_a[l]["shas"]) == {it["sha256"] for it in _items_a} for l in _LENSES_V83)
      and {l: p["rule_in_system"] for l, p in _by_lens_a.items()} == {"correctness": False, "overclaim": False,
                                                                       "evidence-grounding": True, "reproducibility": True}
      and {p["lens"]: p["figures_sent"] for p in _judge_a} == {"correctness": 0, "overclaim": 0, "evidence-grounding": 9, "reproducibility": 9},
      json.dumps({l: (p["n_figures"], p["rule_in_system"]) for l, p in _by_lens_a.items()}))
_rows_a = {r["lens"]: r for r in _rec_fa["audit"]["panel"]}
check("[F3] ADR-0083 (G.6/L) audit.panel[].saw_figures {n 9 en grounding y reproducibility, 0 en las otras, detail vocabulario}; audit.vision "
      "{enabled, lenses, …}; items[].seen_by_lenses == [grounding, reproducibility] para las 9; selection.n_sent_to_panel_by_lens {9, 9}; "
      "figure_readings en las dos lentes con figure_readings_class 'model-judgment'",
      {l: (r.get("saw_figures") or {}).get("n") for l, r in _rows_a.items()} == {"correctness": 0, "overclaim": 0,
                                                                                 "evidence-grounding": 9, "reproducibility": 9}
      and isinstance(_rec_fa["audit"].get("vision"), dict)
      and all(it["seen_by_lenses"] == _LENSES_V83 for it in _items_a)
      and _fg_a["selection"]["n_sent_to_panel_by_lens"] == {"evidence-grounding": 9, "reproducibility": 9}
      and all(isinstance(_rows_a[l].get("figure_readings"), list) and _rows_a[l].get("figure_readings_class") == "model-judgment"
              for l in _LENSES_V83),
      json.dumps({l: r.get("saw_figures") for l, r in _rows_a.items()}, default=str)[:400])
_vis_a = _fg_a["vision"]
check("ADR-0083 (L/H) frozen.figures.vision: forma {state, enabled, lenses, lenses_source, rule, rule_state, openai_detail 'high', "
      "openai_chat_form_state literal, max_per_lens 12, max_image_mb 5, request_b64_mb 8, sent {n_panels, n_attempts_with_images, "
      "bytes_b64_sent_total, visual_tokens_projected_total, tokens_state, rule}, cost_projection {per_lens, total_usd_projected, "
      "prices_source, class 'proyección', complete}, panels [1 con selection {n_eligible 9, n_selected 9, n_dropped 0, n_excluded, rule}], "
      "delivery {audit_accepts_*}, vocabulary, class}; state ∈ vocabulario; lenses == default con fuente",
      {"state", "enabled", "lenses", "lenses_source", "rule", "rule_state", "openai_detail", "openai_chat_form_state", "max_per_lens",
       "max_image_mb", "request_b64_mb", "sent", "cost_projection", "panels", "delivery", "vocabulary", "class"} <= set(_vis_a)
      and _vis_a["enabled"] is True and _vis_a["lenses"] == _LENSES_V83
      and _vis_a["lenses_source"] == "default-unset:WITT_FIGURES_VISION_LENSES" and _vis_a["openai_detail"] == "high"
      and _vis_a["openai_chat_form_state"] == _fig.OPENAI_CHAT_FORM_STATE and _vis_a["request_b64_mb"] == 8
      and set(_vis_a["sent"]) == {"n_panels", "n_attempts_with_images", "bytes_b64_sent_total", "visual_tokens_projected_total",
                                  "tokens_state", "rule"}
      and _vis_a["cost_projection"]["class"] == "proyección" and _vis_a["cost_projection"]["prices_source"] == "models.prices() (ADR-0081)"
      and len(_vis_a["panels"]) == 1 and _vis_a["panels"][0]["selection"]["n_eligible"] == 9
      and _vis_a["panels"][0]["selection"]["n_selected"] == 9 and _vis_a["panels"][0]["selection"]["n_dropped_by_request_cap"] == 0
      and _vis_a["panels"][0]["selection"]["rule"] == _fig.SELECTION_RULE
      and (_vis_a["state"] in runs_mod.VISION_STATES_EXACT or _vis_a["state"].startswith(runs_mod.VISION_STATES_PREFIXES))
      and isinstance(_vis_a["delivery"]["audit_accepts_figures"], bool),
      json.dumps({k: _vis_a[k] for k in ("state", "lenses", "sent", "delivery")}, default=str)[:400])
check("[F3] ADR-0083 (G.3/H) vision.state 'sent', rule == composite_auditor.FIGURE_READING_RULE (verbatim, con 'never derive'), sent "
      "{n_panels 1, n_attempts_with_images 2, bytes_b64_sent_total == 2 × Σ b64 de las 9}; by_stage.panel.by_model[haiku].vision "
      "{n_images 9, visual_tokens_projected 5037 (Σ ⌈w/28⌉×⌈h/28⌉), class 'proyección'}, [gpt-4o].vision {…5525 (tiles)…}; "  # models-literal-doc
      "_sum == by_model (la visión NO se suma dos veces); cost_projection.per_lens 2 con usd_projected",
      _vis_a["state"] == "sent" and isinstance(_vis_a["rule"], str) and "never" in _vis_a["rule"].lower()
      and _vis_a["sent"]["n_panels"] == 1 and _vis_a["sent"]["n_attempts_with_images"] == 2
      and _vis_a["sent"]["bytes_b64_sent_total"] == 2 * sum(len(b) for b in _B64_BY83.values())
      and _rec_fa["token_usage"]["by_stage"]["panel"]["by_model"][_rows_a["evidence-grounding"]["reviewer"]]["vision"]["n_images"] == 9
      and _rec_fa["token_usage"]["by_stage"]["panel"]["by_model"][_rows_a["evidence-grounding"]["reviewer"]]["vision"]["visual_tokens_projected"] == 5037
      and _rec_fa["token_usage"]["by_stage"]["panel"]["by_model"][_rows_a["reproducibility"]["reviewer"]]["vision"]["visual_tokens_projected"] == 5525
      and _rec_fa["token_usage"]["by_stage_sum_matches_by_model"] is True
      and len(_vis_a["cost_projection"]["per_lens"]) == 2 and _vis_a["cost_projection"]["complete"] is True,
      json.dumps({"state": _vis_a["state"], "sent": _vis_a["sent"],
                  "by_model": {k: v.get("vision") for k, v in _rec_fa["token_usage"]["by_stage"]["panel"]["by_model"].items()}}, default=str)[:500])
check("ADR-0083 (H) sin filas con imágenes NADA gana `vision` en by_model y _sum == by_model total; con figuras encendidas y kill-switch de visión "
      "idem — la proyección jamás altera el gasto MEDIDO",
      _rec_fa["token_usage"]["by_stage_sum_matches_by_model"] is True
      and _rec_fa["token_usage"]["by_stage"]["_sum"]["in"] == _rec_fa["token_usage"]["input_tokens"]
      and all("vision" not in m or m["vision"]["n_images"] > 0 for m in _rec_fa["token_usage"]["by_stage"]["panel"]["by_model"].values()))
_bundle_a = json.loads(_bundle_json_a)
_bpaper_a = next(p for p in _bundle_a["path_b"]["papers"] if p.get("source") == "europepmc")
_ident_a = answer_pipeline._identity({k: v for k, v in _bundle_a.items() if k != "bundle_identity"})
check("ADR-0083 (L/ADR-0044) bundle.path_b.papers[].figures {state, n, items, ledger {mechanism, status, http_status, zip_bytes, elapsed_s, "
      "n_entries, n_extracted, n_missing, …}}; bundle.figures_ledger.items[].sha256 == frozen.figures.items[].sha256 (MISMO objeto); "
      "cited_by_answer/seen_by_lenses se llenaron ANTES del re-sellado: bundle_identity.sha256 == sha256(bundle_json sin identidad)",
      _bpaper_a["figures"]["state"] == "attached" and _bpaper_a["figures"]["n"] == 9
      and {"mechanism", "status", "http_status", "zip_bytes", "elapsed_s", "n_entries", "n_extracted", "n_missing"} <= set(_bpaper_a["figures"]["ledger"])
      and [it["sha256"] for it in _bundle_a["figures_ledger"]["items"]] == [it["sha256"] for it in _items_a]
      and [it["cited_by_answer"] for it in _bundle_a["figures_ledger"]["items"]] == [it["cited_by_answer"] for it in _items_a]
      and _rec_fa["bundle_identity"]["sha256"] == _ident_a["sha256"],
      json.dumps({"ledger": _bpaper_a["figures"]["ledger"], "identity_ok": _rec_fa["bundle_identity"]["sha256"] == _ident_a["sha256"]}, default=str)[:300])
check("ADR-0083 (D.3) _evidence_ids(bundle) += los 9 ids '<PMCID>#<fig_id>' → audit.approved los trae (APPROVE) junto al paper y el chunk",
      set(_FIG_IDS83) <= set(_rec_fa["audit"]["approved"]) and "PMID:39230001" in _rec_fa["audit"]["approved"]
      and set(_FIG_IDS83) <= set(runs_mod._evidence_ids(_bundle_a)),
      json.dumps(sorted(_rec_fa["audit"]["approved"]))[:300])
check("ADR-0083 (B.3) caché de figuras en el TMP de WITT_MCP_CACHE_DIR: figures/PMC11379296/<9 jpg> + _figures_<YYYYMMDD>.json, el zip NO se conserva",
      sorted(p.name for p in (_CR83 / "PMC11379296").glob("*.jpg")) == sorted(_MAN_BY83)
      and len(list((_CR83 / "PMC11379296").glob("_figures_*.json"))) == 1
      and not list((_CR83 / "PMC11379296").glob("*.zip")) and not list((_CR83 / "PMC11379296").glob("*.part")))

# --- (b) CC BY-NC: panel_view True, embeddable False; undfig1 sin caption no se baja ni se entrega -----------------------------------
_rid_fb, _rec_fb, _ev_fb, _row_fb = _run83("ADR-0083 b: figures CC BY-NC", _synth83("wt1a marks the pronephros [1].",
                                                                                     [{"kind": "paper", "id": "PMID:39230002"}]),
                                           pmcids=("PMC11647118",))
_fg_b = _rec_fb["figures"]
_items_b = _fg_b["items"]
_p2_b = next(p for p in next(s for s in _SYNTH83 if s["pass"] == "pass2")["evidence"]["path_b"]["papers"] if p.get("source") == "europepmc")
check("ADR-0083 (A.3/E2) NC: n_figures 6, n_with_caption 5, n_verified 5, n_not_fetched 1, n_embeddable 0, n_panel_view 5, n_unknown_license 0; "
      "undfig1 {label None, caption_state 'absent', bytes_state 'not-fetched (no-caption)', delivered_to_synthesizer False}; fig1 {license "
      "cc-by-nc / license-p-url / rule_no 3, embeddable False, panel_view True, bytes_state 'verified', media_type image/png ≠ mime_from_extension "
      "image/jpeg (SINTÉTICO por magic), dims_match False}; pass2 entrega 5 (undfig1 fuera); agents 'figures:5/6'; epistemic 5/0",
      (_fg_b["n_figures"], _fg_b["n_with_caption"], _fg_b["n_verified"], _fg_b["n_not_fetched"]) == (6, 5, 5, 1)
      and (_fg_b["n_embeddable"], _fg_b["n_panel_view"], _fg_b["n_unknown_license"]) == (0, 5, 0)
      and _items_b[0]["fig_id"] == "undfig1" and _items_b[0]["label"] is None and _items_b[0]["caption_state"] == "absent"
      and _items_b[0]["bytes_state"] == "not-fetched (no-caption)" and _items_b[0]["delivered_to_synthesizer"] is False
      and _items_b[1]["license"]["id"] == "cc-by-nc" and _items_b[1]["license"]["source"] == "license-p-url"
      and _items_b[1]["license"]["rule_no"] == 3 and _items_b[1]["embeddable"] is False and _items_b[1]["panel_view"] is True
      and _items_b[1]["bytes_state"] == "verified" and _items_b[1]["media_type"] == "image/png"
      and _items_b[1]["mime_from_extension"] == "image/jpeg" and _items_b[1]["dims_match"] is False
      and _p2_b["figures"]["n"] == 6 and _p2_b["figures"]["n_delivered"] == 5 and len(_p2_b["figures"]["items"]) == 5
      and next(a for a in _rec_fb["agents_invoked"] if a["agent"] == runs_mod.FIGURES_AGENT_ROW)["invocation_id"] == "figures:5/6"
      and app.get_run(_rid_fb, authorization=AUTH)["epistemic_summary"]["figures_n_verified"] == 5
      and app.get_run(_rid_fb, authorization=AUTH)["epistemic_summary"]["figures_n_cited"] == 0,
      json.dumps({k: _fg_b[k] for k in ("n_figures", "n_with_caption", "n_verified", "n_embeddable", "n_panel_view")}))
check("ADR-0083 (G.2/E2) NC: la selección para el panel toma las 5 con caption (panel_view True aunque NO embebibles: leer para juzgar no es "
      "redistribuir; embeber sigue prohibido) — vision.panels[0].selection {n_eligible 5, n_selected 5}; figure_citations {n 0} sin citas figure",
      _fg_b["vision"]["panels"][0]["selection"]["n_eligible"] == 5 and _fg_b["vision"]["panels"][0]["selection"]["n_selected"] == 5
      and _rec_fb["citations_support_summary"]["figure_citations"]["n"] == 0,
      json.dumps(_fg_b["vision"]["panels"][0]["selection"]))
check("[F3] ADR-0083 (E2) NC: las dos lentes con visión reciben las 5 figuras NC (bytes al panel, jamás al PDF/GET)",
      {p["lens"]: p["n_figures"] for p in _PANEL83} == {"correctness": 0, "overclaim": 0, "evidence-grounding": 5, "reproducibility": 5},
      json.dumps({p["lens"]: p["n_figures"] for p in _PANEL83}))

# --- (c) licencia DESCONOCIDA (XML sintético sin <permissions>): se baja y verifica por sha, pero NO viaja a nadie -----------------------
_rid_fc, _rec_fc, _ev_fc, _row_fc = _run83("ADR-0083 c: unknown license", _synth83("wt1a marks the pronephros [1] [2].",
                                                                                   [{"kind": "paper", "id": "PMID:39230003"},
                                                                                    {"kind": "figure", "id": "PMC90000001#u1"}]),
                                           pmcids=("PMC90000001",))
_fg_c = _rec_fc["figures"]
check("ADR-0083 (A.3) unknown: license {id 'unknown', source 'none', rule_no 7}, embeddable False, panel_view False, bytes_state 'verified' "
      "(fetch_bytes True: se baja y verifica; lo que no viaja son sus bytes a terceros), n_unknown_license 1, n_panel_view 0, n_embeddable 0; "
      "vision.state 'no-eligible-figures' (0 elegibles); caller sin figuras en ninguna lente; el caption SÍ viaja al sintetizador",
      _fg_c["n_figures"] == 1 and _fg_c["items"][0]["license"]["id"] == "unknown" and _fg_c["items"][0]["license"]["source"] == "none"
      and _fg_c["items"][0]["license"]["rule_no"] == 7 and _fg_c["items"][0]["embeddable"] is False
      and _fg_c["items"][0]["panel_view"] is False and _fg_c["items"][0]["bytes_state"] == "verified"
      and (_fg_c["n_unknown_license"], _fg_c["n_panel_view"], _fg_c["n_embeddable"], _fg_c["n_verified"]) == (1, 0, 0, 1)
      and _fg_c["vision"]["state"] == "no-eligible-figures" and _fg_c["vision"]["panels"][0]["selection"]["n_eligible"] == 0
      and all(p["n_figures"] == 0 for p in _PANEL83)
      and next(p for p in next(s for s in _SYNTH83 if s["pass"] == "pass2")["evidence"]["path_b"]["papers"]
               if p.get("source") == "europepmc")["figures"]["n_delivered"] == 1
      and _rec_fc["citations"][1]["figure_verification"] == {"bytes": "verified", "content": "not-evaluated", "figure_id": "PMC90000001#u1",
                                                              "kind_reported": "figure"},
      json.dumps({"license": _fg_c["items"][0]["license"], "vision": _fg_c["vision"]["state"]}))
check("[F2] ADR-0083 (F.5) figure_license_known INFORMATIVO: unknown ['PMC90000001#u1'] → ok False con gating False; admissible sigue True",
      _rec_fc["deterministic_checks"]["figures"].get("figure_license_known", {}).get("ok") is False
      and _rec_fc["deterministic_checks"]["figures"]["figure_license_known"].get("gating") is False
      and _rec_fc["deterministic_checks"]["admissible"] is True,
      json.dumps(_rec_fc["deterministic_checks"]["figures"].get("figure_license_known")))

# --- (d) sha ALTERADO entre attach y gate: inadmisible (F2) y excluida del panel por sha recalculado (select_for_panel) -----------------
_real_stage83 = runs_mod._figures_stage


def _stage_then_tamper83(*a, **kw):
    s = _real_stage83(*a, **kw)
    p = _CR83 / "PMC11379296" / _G001_HREF
    p.write_bytes(p.read_bytes()[:-1] + b"\x00")
    return s


runs_mod._figures_stage = _stage_then_tamper83
try:
    _rid_fd, _rec_fd, _ev_fd, _row_fd = _run83("ADR-0083 d: tampered bytes", _synth83(_ANS_A83, _CIT_A83),
                                               panel=_panel83(ALL_A, readings=True, cs=_CS_A83))
finally:
    runs_mod._figures_stage = _real_stage83
_fg_d = _rec_fd["figures"]
check("ADR-0083 (B.3) segunda corrida BY: la caché de figuras cumple TTL (ledger fresco + archivos + sha recalculado igual) → cache_hit True en "
      "las 9, ledger.status 'cache-hit', CERO GET; el frozen sigue 9 verified (la alteración ocurrió DESPUÉS del attach)",
      _GET83 == [] and all(it["cache_hit"] is True for it in _fg_d["items"]) and _fg_d["n_verified"] == 9
      and next(p for p in json.loads(_row_fd["bundle_json"])["path_b"]["papers"] if p.get("source") == "europepmc")["figures"]["ledger"]["status"] == "cache-hit",
      json.dumps({"gets": len(_GET83), "status": _fg_d["state"]}))
check("ADR-0083 (G.2/ADR-0077) sha ALTERADO en caché → select_for_panel RECALCULA y EXCLUYE g001 ('mismatch' declarado): panels[0].selection "
      "{n_eligible 9, n_selected 8, n_excluded.mismatch 1} — jamás se envía un byte que no cuadre",
      _fg_d["vision"]["panels"][0]["selection"]["n_eligible"] == 9 and _fg_d["vision"]["panels"][0]["selection"]["n_selected"] == 8
      and _fg_d["vision"]["panels"][0]["selection"]["n_excluded"]["mismatch"] == 1,
      json.dumps(_fg_d["vision"]["panels"][0]["selection"]))
check("[F2] ADR-0083 (F.2) figure_sha_matches DURO en MISMATCH: pass2 INADMISIBLE con 'hard predicate failed: figure_sha_matches', "
      "mismatches [{id g001, expected, actual}] congelado",
      _rec_fd["deterministic_checks"]["admissible"] is False
      and "hard predicate failed: figure_sha_matches" in _rec_fd["deterministic_checks"]["reasons"]
      and [m.get("id") for m in _rec_fd["deterministic_checks"]["figures"].get("figure_sha_matches", {}).get("mismatches", [])] == [_G001_ID],
      json.dumps({"adm": _rec_fd["deterministic_checks"]["admissible"], "reasons": _rec_fd["deterministic_checks"]["reasons"]}))
check("[F3] ADR-0083 (G.2) con el sha alterado las dos lentes reciben 8 (g001 excluida) y saw_figures.n 8",
      {p["lens"]: p["n_figures"] for p in _PANEL83}.get("evidence-grounding") == 8
      and (next(r for r in _rec_fd["audit"]["panel"] if r["lens"] == "reproducibility").get("saw_figures") or {}).get("n") == 8,
      json.dumps({p["lens"]: p["n_figures"] for p in _PANEL83}))
import shutil as _shutil  # noqa: E402
_shutil.rmtree(_CR83 / "PMC11379296", ignore_errors=True)   # la caché alterada no contamina las corridas siguientes (re-descarga medida abajo)

# --- (e) afirmación positiva con SOLO citas figure → inadmisible (F2, §7 figure-only NOT asserted) ---------------------------------------
_rid_fe, _rec_fe, _ev_fe, _row_fe = _run83("ADR-0083 e: figure-only claim", _synth83("Fig 1 shows wt1a in the pronephros [1].",
                                                                                     [{"kind": "figure", "id": _G001_ID}]))
check("[F2] ADR-0083 (F.3) figure_only_not_asserted DURO: afirmación positiva cuyas citas válidas son TODAS kind figure → INADMISIBLE "
      "('hard predicate failed: figure_only_not_asserted'; n_figure_citations 1, n_non_figure_citations 0)",
      _rec_fe["deterministic_checks"]["admissible"] is False
      and "hard predicate failed: figure_only_not_asserted" in _rec_fe["deterministic_checks"]["reasons"]
      and _rec_fe["deterministic_checks"]["figures"].get("figure_only_not_asserted", {}).get("n_figure_citations") == 1,
      json.dumps({"adm": _rec_fe["deterministic_checks"]["admissible"], "reasons": _rec_fe["deterministic_checks"]["reasons"]}))
check("ADR-0083 (B.3) tras borrar la caché la corrida (e) RE-DESCARGA: UNA GET, cache_hit False, 9 verified — la ausencia de bytes no es un error",
      len(_GET83) == 1 and _rec_fe["figures"]["n_verified"] == 9 and all(it["cache_hit"] is False for it in _rec_fe["figures"]["items"]))

# --- (f) id de figura INVENTADO → inadmisible (F2) y figure_verification 'not-a-figure' (F4) -------------------------------------------
_rid_ff, _rec_ff, _ev_ff, _row_ff = _run83("ADR-0083 f: invented figure id", _synth83(_ANS_A83, [
    {"kind": "paper", "id": "PMID:39230001"}, {"kind": "figure", "id": "PMC11379296#pone.0307390.g099"}]))
check("ADR-0083 (E) id de figura que NO nombra un ítem del bundle → figure_verification {bytes 'not-a-figure', content 'not-evaluated', "
      "figure_id null} y figure_citations {n 1, n_unresolved 1}; los 9 ítems siguen verified (la cita inventada no toca la medición)",
      _rec_ff["citations"][1]["figure_verification"] == {"bytes": "not-a-figure", "content": "not-evaluated", "figure_id": None, "kind_reported": "figure"}
      and _rec_ff["citations_support_summary"]["figure_citations"] == {"n": 1, "n_verified_bytes": 0, "n_not_fetched": 0, "n_error": 0, "n_mismatch": 0,
                                                                         "n_unresolved": 1, "n_other": 0, "n_figure_shaped_other_kind": 0}
      and _rec_ff["figures"]["n_verified"] == 9 and _rec_ff["figures"]["n_cited"] == 0,
      json.dumps(_rec_ff["citations"][1].get("figure_verification")))
check("[F2] ADR-0083 (F.1) figure_id_resolves DURO: id inventado → INADMISIBLE ('hard predicate failed: figure_id_resolves'), unresolved_ids [id]",
      _rec_ff["deterministic_checks"]["admissible"] is False
      and "hard predicate failed: figure_id_resolves" in _rec_ff["deterministic_checks"]["reasons"]
      and _rec_ff["deterministic_checks"]["figures"].get("figure_id_resolves", {}).get("unresolved_ids") == ["PMC11379296#pone.0307390.g099"],
      json.dumps(_rec_ff["deterministic_checks"]["reasons"]))

# --- (g) SIN XML de texto completo en raw_cached → 'no-papers-with-xml' declarado ----------------------------------------------------
_rid_fg, _rec_fg, _ev_fg, _row_fg = _run83("ADR-0083 g: no fulltext xml", _synth83("wt1a [1].", [{"kind": "paper", "id": "PMID:39230001"}]),
                                           with_xml=False)
_fg_g = _rec_fg["figures"]
_p2_g = next(p for p in next(s for s in _SYNTH83 if s["pass"] == "pass2")["evidence"]["path_b"]["papers"] if p.get("source") == "europepmc")
check("ADR-0083 (C/L) sin *fulltext*.xml en raw_cached: frozen.figures.state 'no-papers-with-xml', n_papers_eligible 0, items []; papers[0].figures "
      "{state 'no-fulltext-xml', n 0, items [], ledger null} (también en el prompt de pass2 con n_delivered 0); eventos: plan {n_papers_eligible 0} + "
      "summary, SIN paper/figure; CERO GET; agents fila 'not-applicable' reason 'no full-text XML among selected papers' 'figures:0/0'; "
      "epistemic {figures_state 'no-papers-with-xml', figures_n_verified 0 (MEDIDO), figures_n_cited 0}; figure_citations n 0; vision 'no-eligible-figures'",
      _fg_g["state"] == "no-papers-with-xml" and _fg_g["n_papers_eligible"] == 0 and _fg_g["items"] == []
      and next(p for p in json.loads(_row_fg["bundle_json"])["path_b"]["papers"] if p.get("source") == "europepmc")["figures"]
          == {"state": "no-fulltext-xml", "n": 0, "items": [], "ledger": None}
      and _p2_g["figures"] == {"state": "no-fulltext-xml", "n": 0, "items": [], "n_delivered": 0}
      and [e["type"] for e in _ev_fg if e["type"].startswith("stage.figures.")] == ["stage.figures.plan", "stage.figures.summary"]
      and _ev_payloads(_ev_fg, "stage.figures.plan")[0]["n_papers_eligible"] == 0 and _GET83 == []
      and next(a for a in _rec_fg["agents_invoked"] if a["agent"] == runs_mod.FIGURES_AGENT_ROW)
          == {"agent": runs_mod.FIGURES_AGENT_ROW, "status": "not-applicable", "invocation_id": "figures:0/0",
              "evidence_generated": ["parsed:0", "verified:0", "embeddable:0", "lenses:evidence-grounding,reproducibility", "synthesizer:captions-only"],
              "reason": "no full-text XML among selected papers"}
      and app.get_run(_rid_fg, authorization=AUTH)["epistemic_summary"]["figures_state"] == "no-papers-with-xml"
      and app.get_run(_rid_fg, authorization=AUTH)["epistemic_summary"]["figures_n_verified"] == 0
      and _rec_fg["citations_support_summary"]["figure_citations"]["n"] == 0 and _fg_g["vision"]["state"] == "no-eligible-figures",
      json.dumps({"state": _fg_g["state"], "events": [e["type"] for e in _ev_fg if e["type"].startswith("stage.figures.")]}))

# --- (h) PRESUPUESTO agotado (WITT_FIGURES_BUDGET_S=0.5 < 5 s mínimos): filas declaradas sin red, la corrida cierra ---------------------
_shutil.rmtree(_CR83 / "PMC11379296", ignore_errors=True)   # sin caché: la única vía a los bytes es la red, y el presupuesto la veta
_rid_fh, _rec_fh, _ev_fh, _row_fh = _run83("ADR-0083 h: budget exhausted", _synth83(_ANS_A83, _CIT_A83), env={"WITT_FIGURES_BUDGET_S": "0.5"})
_fg_h = _rec_fh["figures"]
_bledger_h = next(p for p in json.loads(_row_fh["bundle_json"])["path_b"]["papers"] if p.get("source") == "europepmc")["figures"]["ledger"]
check("ADR-0083 (B.4/§6) WITT_FIGURES_BUDGET_S=0.5: restante < 5 s → las 9 filas 'not-fetched (budget-exhausted)' SIN red (0 GET), n_verified 0, "
      "n_not_fetched 9, caption intacto, budget.total_s 0.5 (source 'env:WITT_FIGURES_BUDGET_S' en caps? no: budget), ledger {status 'skipped-budget', "
      "error_kind 'budget-exhausted'}, paper{done} con error; la corrida CIERRA awaiting_closure; figure_verification.bytes = la fila declarada",
      _GET83 == [] and all(it["bytes_state"] == "not-fetched (budget-exhausted)" for it in _fg_h["items"])
      and (_fg_h["n_verified"], _fg_h["n_not_fetched"], _fg_h["n_figures"]) == (0, 9, 9)
      and all(it["caption_state"] == "present" and it["caption"] for it in _fg_h["items"])
      and _fg_h["budget"]["total_s"] == 0.5 and _bledger_h["status"] == "skipped-budget" and _bledger_h["error_kind"] == "budget-exhausted"
      and "error" in _ev_payloads(_ev_fh, "stage.figures.paper")[1] and _row_fh["state"] == "awaiting_closure"
      and _rec_fh["citations"][1]["figure_verification"]["bytes"] == "not-fetched (budget-exhausted)"
      and _rec_fh["citations_support_summary"]["figure_citations"]["n_not_fetched"] == 1
      and _fg_h["vision"]["state"] == "no-eligible-figures",
      json.dumps({"budget": _fg_h["budget"], "ledger": _bledger_h}, default=str)[:300])
check("[F2] ADR-0083 (F.2) figura NO bajada ≠ alterada: figure_sha_matches n_not_verifiable 1 y ok (la cita sostiene sólo su caption); admisible",
      _rec_fh["deterministic_checks"]["figures"].get("figure_sha_matches", {}).get("n_not_verifiable") == 1
      and _rec_fh["deterministic_checks"]["admissible"] is True,
      json.dumps(_rec_fh["deterministic_checks"]["figures"].get("figure_sha_matches")))

# --- (i) _get_bytes que LANZA → filas 'error: RuntimeError: …', la corrida sigue -------------------------------------------------------
_shutil.rmtree(_CR83 / "PMC11379296", ignore_errors=True)   # (h) no escribió nada; se garantiza igual: la GET DEBE ocurrir
_rid_fi, _rec_fi, _ev_fi, _row_fi = _run83("ADR-0083 i: get_bytes raises", _synth83(_ANS_A83, _CIT_A83),
                                           get=_mk_get83(raise_exc=RuntimeError("caller exploded")))
check("ADR-0083 (§6) un _get_bytes que LANZA → 9 filas 'error: RuntimeError: caller exploded' (vocabulario prefijo 'error: '), n_error 9 y "
      "n_not_fetched 0 (corrector: cubetas separadas — frozen.figures y stage.figures.summary llevan n_error; la cita figure gana figure_verification.bytes "
      "'error: …' y figure_citations.n_error 1), ledger.error_kind 'error: RuntimeError', paper{done} level warning con error; la corrida SIGUE y cierra awaiting_closure",
      all(it["bytes_state"] == "error: RuntimeError: caller exploded" for it in _rec_fi["figures"]["items"])
      and all(_fig.bytes_state_in_vocabulary(it["bytes_state"]) for it in _rec_fi["figures"]["items"])
      and _rec_fi["figures"]["n_error"] == 9 and _rec_fi["figures"]["n_not_fetched"] == 0 and _rec_fi["figures"]["n_verified"] == 0
      and _ev_payloads(_ev_fi, "stage.figures.summary")[0]["n_error"] == 9
      and _rec_fi["citations"][1]["figure_verification"]["bytes"] == "error: RuntimeError: caller exploded"
      and _rec_fi["citations_support_summary"]["figure_citations"]["n_error"] == 1
      and _rec_fi["citations_support_summary"]["figure_citations"]["n_not_fetched"] == 0
      and next(p for p in json.loads(_row_fi["bundle_json"])["path_b"]["papers"] if p.get("source") == "europepmc")["figures"]["ledger"]["error_kind"]
          == "error: RuntimeError"
      and next(e for e in _ev_fi if e["type"] == "stage.figures.paper" and e["payload"]["phase"] == "done")["level"] == "warning"
      and _row_fi["state"] == "awaiting_closure",
      json.dumps({"state": _row_fi["state"], "bytes_state": _rec_fi["figures"]["items"][0]["bytes_state"]}))

# --- (j) KILL-SWITCH WITT_FIGURES=0: el frozen de 1.11 salvo EXACTAMENTE 3 excepciones ----------------------------------------------------
_rid_fj, _rec_fj, _ev_fj, _row_fj = _run83(_Q_A83, _synth83(_ANS_A83, _CIT_A83), panel=_panel83(ALL_A, readings=True, cs=_CS_A83),
                                           env={"WITT_FIGURES": "0"})
_fg_j = _rec_fj["figures"]
_fig_ev_j = [e for e in _ev_fj if e["type"].startswith("stage.figures.")]
_diff_j = _diff83(_strip83(_rec_fa), _strip83(_rec_fj))
check("ADR-0083 (M.1) KILL-SWITCH WITT_FIGURES=0: frozen keyset == 1.11 (47 + council) + {figures}; figures {state 'kill-switch WITT_FIGURES=0', "
      "kill_switch {WITT_FIGURES '0', declared_exceptions [render_contract_version, figures, deterministic_checks.figures]}, items [], n_figures 0, "
      "SIN vision}; deterministic_checks.figures == {state 'kill-switch WITT_FIGURES=0'} y su keyset == el de la corrida (a); render_contract_version "
      "'1.12' — las TRES excepciones declaradas y ninguna más",
      set(_rec_fj) == _FROZEN_1_10_KEYS | {"council", "figures", "web_locator"}   # ADR-0084: web_locator SIEMPRE presente en >= 1.13
      and _fg_j["state"] == "kill-switch WITT_FIGURES=0"
      and _fg_j["kill_switch"] == {"WITT_FIGURES": "0", "declared_exceptions": ["render_contract_version", "figures", "deterministic_checks.figures"]}
      and _fg_j["items"] == [] and _fg_j["n_figures"] == 0 and "vision" not in _fg_j
      and _rec_fj["deterministic_checks"]["figures"] == {"state": "kill-switch WITT_FIGURES=0"}
      and set(_rec_fj["deterministic_checks"]) == set(_rec_fa["deterministic_checks"])
      and _rec_fj["render_contract_version"] == "1.13",   # ADR-0084 apila sobre 1.12
      json.dumps({"figures": {k: _fg_j[k] for k in ("state", "kill_switch")}, "dc": _rec_fj["deterministic_checks"]["figures"]}))
check("ADR-0083 (M.1) KILL-SWITCH: los papers NO ganan `figures` ni el bundle `figures_ledger`; el user_text del sintetizador (pass1 Y pass2) no "
      "trae la llave 'figures' (byte a byte el de 1.11); el panel no recibe imágenes ni la llave; ninguna llave aditiva 1.12 en el frozen "
      "(saw_figures, vision, figure_readings*, figure_verification, figure_citations, from_vision_lens); agents_invoked SIN fila figures; "
      "by_model[*] sin vision; CERO GET; UN solo evento stage.figures.* == summary {state kill-switch}; judge.figures_sent 0 en las 4",
      not any("figures" in p for p in json.loads(_row_fj["bundle_json"])["path_b"]["papers"])
      and "figures_ledger" not in json.loads(_row_fj["bundle_json"])
      and not any('"figures"' in s["json"] for s in _SYNTH83) and not any(p["evidence_has_figures_key"] for p in _PANEL83)
      and all(p["n_figures"] == 0 for p in _PANEL83)
      and not _walk_keys83({k: v for k, v in _rec_fj.items() if k != "figures"}) & _ADDITIVE_112_KEYS
      and not any(a["agent"] == runs_mod.FIGURES_AGENT_ROW for a in _rec_fj["agents_invoked"])
      and not any("vision" in m for m in _rec_fj["token_usage"]["by_stage"]["panel"]["by_model"].values())
      and _GET83 == [] and [e["type"] for e in _fig_ev_j] == ["stage.figures.summary"]
      and _fig_ev_j[0]["payload"]["state"] == "kill-switch WITT_FIGURES=0"
      and all(p["figures_sent"] == 0 and p["figures_sha256"] == [] for p in _ev_payloads(_ev_fj, "stage.audit.judge")),
      json.dumps({"fig_events": [e["type"] for e in _fig_ev_j], "additive_leak": sorted(_walk_keys83({k: v for k, v in _rec_fj.items() if k != "figures"}) & _ADDITIVE_112_KEYS)}))
check("ADR-0083 (M.1) KILL-SWITCH byte a byte contra la corrida (a) del MISMO fixture y la MISMA pregunta: quitadas las llaves ADITIVAS 1.12 "
      "(figures, deterministic_checks.figures, fila figures de agents, ids de figura en audit.approved (D.3), saw_figures/vision/figure_readings, "
      "figure_verification/escalera de la cita figure, by_model.vision) y las de identidad de corrida (run_id, measured_at, bundle_identity, thread), "
      "los dos registros son IDÉNTICOS (json sort_keys, keyset Y valores) — cualquier otra diferencia falla listando el path",
      _diff_j == set(), json.dumps(sorted(_diff_j))[:600])
check("ADR-0083 (M.1, vista) KILL-SWITCH epistemic_summary: figures_state 'kill-switch WITT_FIGURES=0', figures_n_verified null y figures_n_cited null "
      "(nada se contó: null ≠ 0 medido)",
      app.get_run(_rid_fj, authorization=AUTH)["epistemic_summary"]["figures_state"] == "kill-switch WITT_FIGURES=0"
      and app.get_run(_rid_fj, authorization=AUTH)["epistemic_summary"]["figures_n_verified"] is None
      and app.get_run(_rid_fj, authorization=AUTH)["epistemic_summary"]["figures_n_cited"] is None)

# --- (k) WITT_FIGURES_VISION=0: figuras OBSERVADAS (captions, sha, licencia) pero NINGUNA lente recibe imágenes ---------------------------
_rid_fk, _rec_fk, _ev_fk, _row_fk = _run83("ADR-0083 k: vision off", _synth83(_ANS_A83, _CIT_A83), panel=_panel83(ALL_A, readings=True, cs=_CS_A83),
                                           env={"WITT_FIGURES_VISION": "0"})
_fg_k = _rec_fk["figures"]
check("ADR-0083 (M.2) WITT_FIGURES_VISION=0: n_verified 9, captions al sintetizador (pass2 n_delivered 9), figure_verification.bytes 'verified', "
      "GET/predicados iguales; vision {state 'kill-switch WITT_FIGURES_VISION=0', enabled False, sent {n_panels 0, n_attempts_with_images 0, "
      "bytes 0}, panels[0].selection null (no se leyó un byte)}; caller sin figuras en las 4 lentes; judge.figures_sent 0; by_model sin vision; "
      "plan.vision.enabled False",
      _fg_k["n_verified"] == 9
      and next(p for p in next(s for s in _SYNTH83 if s["pass"] == "pass2")["evidence"]["path_b"]["papers"] if p.get("source") == "europepmc")["figures"]["n_delivered"] == 9
      and _rec_fk["citations"][1]["figure_verification"]["bytes"] == "verified"
      and _fg_k["vision"]["state"] == "kill-switch WITT_FIGURES_VISION=0" and _fg_k["vision"]["enabled"] is False
      and _fg_k["vision"]["sent"]["n_panels"] == 0 and _fg_k["vision"]["sent"]["n_attempts_with_images"] == 0
      and _fg_k["vision"]["sent"]["bytes_b64_sent_total"] == 0 and _fg_k["vision"]["panels"][0]["selection"] is None
      and all(p["n_figures"] == 0 for p in _PANEL83)
      and all(p["figures_sent"] == 0 for p in _ev_payloads(_ev_fk, "stage.audit.judge"))
      and not any("vision" in m for m in _rec_fk["token_usage"]["by_stage"]["panel"]["by_model"].values())
      and _ev_payloads(_ev_fk, "stage.figures.plan")[0]["vision"]["enabled"] is False,
      json.dumps(_fg_k["vision"]["sent"]))
check("[F3] ADR-0083 (M.2) con visión apagada cada fila del panel declara saw_figures {n 0, detail 'kill-switch WITT_FIGURES_VISION=0'} y "
      "items[].seen_by_lenses == []",
      all((r.get("saw_figures") or {}).get("detail") == "kill-switch WITT_FIGURES_VISION=0" for r in _rec_fk["audit"]["panel"])
      and all(it["seen_by_lenses"] == [] for it in _fg_k["items"]),
      json.dumps([r.get("saw_figures") for r in _rec_fk["audit"]["panel"]], default=str)[:300])

# --- (l) REVISE forzado: dos paneles → reenvío MEDIDO; el lazo D.4 (from_vision_lens + la frase) -------------------------------------------
_ROUND1_83 = {"correctness": "REVISE", "overclaim": "APPROVE", "evidence-grounding": "REVISE", "reproducibility": "APPROVE"}
_rid_fl, _rec_fl, _ev_fl, _row_fl = _run83("ADR-0083 l: forced revise", _synth83(_ANS_A83, _CIT_A83, rev_text=_ANS_A83 + " (revised)"),
                                           panel=_panel83(ALL_A, readings=True, cs=_CS_A83, rounds=[_ROUND1_83, ALL_A]))
_fg_l = _rec_fl["figures"]
_rev_ev_l = next(s for s in _SYNTH83 if s["pass"] == "revision")["evidence"]
_findings_l = _rec_fl["revision"]["findings_used"]
check("ADR-0083 (D.4, el lazo) revisión: findings_used[] gana `from_vision_lens` (bool) y NADA más (lens, reviewer, verdict, caught, "
      "correction_applied, reasons — figure_readings JAMÁS entra); la instruction de la revisión lleva la frase VISION_LENS_FINDINGS_CLAUSE "
      "('never adopt a number or observation from them unless it appears in a delivered TEXT passage'); stage.revision.start += n_from_vision_lens; "
      "vision.panels 2 (la revisión re-selecciona); revision.performed True",
      _rec_fl["revision"]["performed"] is True and len(_findings_l) == 2
      and all(set(f) == {"lens", "reviewer", "verdict", "caught", "correction_applied", "reasons", "from_vision_lens"} for f in _findings_l)
      and all(isinstance(f["from_vision_lens"], bool) for f in _findings_l)
      and runs_mod.VISION_LENS_FINDINGS_CLAUSE in _rev_ev_l["revision_input"]["instruction"]
      and "never adopt a number or observation from them unless it appears in a delivered TEXT passage" in _rev_ev_l["revision_input"]["instruction"]
      and _rev_ev_l["revision_input"]["panel_findings"] == _findings_l
      and "n_from_vision_lens" in _ev_payloads(_ev_fl, "stage.revision.start")[0]
      and len(_fg_l["vision"]["panels"]) == 2,
      json.dumps(_findings_l))
check("[F3] ADR-0083 (D.4/H) from_vision_lens True SÓLO en el hallazgo de evidence-grounding (vio 9), False en correctness; sent {n_panels 2, "
      "n_attempts_with_images 4, bytes ×2 del panel único} — cada panel reenvía las imágenes y la API las factura",
      {f["lens"]: f["from_vision_lens"] for f in _findings_l} == {"correctness": False, "evidence-grounding": True}
      and _fg_l["vision"]["sent"]["n_panels"] == 2 and _fg_l["vision"]["sent"]["n_attempts_with_images"] == 4
      and _fg_l["vision"]["sent"]["bytes_b64_sent_total"] == 2 * _fg_a["vision"]["sent"]["bytes_b64_sent_total"]
      and _ev_payloads(_ev_fl, "stage.revision.start")[0]["n_from_vision_lens"] == 1,
      json.dumps({"findings": {f["lens"]: f["from_vision_lens"] for f in _findings_l}, "sent": _fg_l["vision"]["sent"]}))

check("ADR-0083 (L/G.6, corrector) con revisión `audit += vision` TAMBIÉN en audit_initial: audit_initial.vision presente, state 'sent', mismo keyset que "
      "audit.vision (el ADR (L) lo prometía; AUDIT_INITIAL_QUORUM_KEYS lo copia sólo si audit() la trae → bajo kill-switch (j) audit_initial no existe "
      "o no la lleva)",
      isinstance(_rec_fl.get("audit_initial"), dict) and isinstance(_rec_fl["audit_initial"].get("vision"), dict)
      and _rec_fl["audit_initial"]["vision"]["state"] == "sent" and set(_rec_fl["audit_initial"]["vision"]) == set(_rec_fl["audit"]["vision"])
      and "vision" in runs_mod.AUDIT_INITIAL_QUORUM_KEYS
      and not (isinstance(_rec_fj.get("audit_initial"), dict) and "vision" in _rec_fj["audit_initial"]),
      json.dumps(sorted(_rec_fl["audit_initial"].get("vision") or {})))
# --- (corrector) unidades: _figure_readings_ids sin colisión de fig_id; clasificador SUPERSET; proyección con detail -------------------
_blk_two = {"items": [{"id": "PMC1#F1", "pmcid": "PMC1", "fig_id": "F1", "bytes_state": "verified", "sha256": "1" * 64},
                      {"id": "PMC2#F1", "pmcid": "PMC2", "fig_id": "F1", "bytes_state": "verified", "sha256": "2" * 64}]}
_aud_two = {"panel": [{"lens": "evidence-grounding", "saw_figures": {"n": 1}, "figure_readings": [{"fig_id": "F1", "id": "PMC1#F1", "reading": "x"}]}]}
_cits_two = [{"n": 1, "kind": "figure", "id": "PMC1#F1"}, {"n": 2, "kind": "figure", "id": "PMC2#F1"}]
_fc_two = runs_mod._figure_verification(_cits_two, _blk_two, _aud_two)
check("ADR-0083 (E, corrector) dos papers con el MISMO fig_id ('F1'): sólo la figura LEÍDA (PMC1#F1) gana content 'panel-judgment'; PMC2#F1 queda "
      "'not-evaluated' (antes el fig_id desnudo colisionaba y atribuía juicio a una imagen que ninguna lente leyó); _figure_readings_ids sólo ids compuestos",
      _cits_two[0]["figure_verification"]["content"] == "panel-judgment" and _cits_two[1]["figure_verification"]["content"] == "not-evaluated"
      and runs_mod._figure_readings_ids(_aud_two) == {"PMC1#F1"} and _fc_two["n"] == 2 and _fc_two["n_verified_bytes"] == 2,
      json.dumps([c["figure_verification"] for c in _cits_two]))
_cits_kind = [{"n": 1, "kind": "paper", "id": "PMC11379296#pone.0307390.g001"}, {"n": 2, "kind": "paper", "id": "PMID:39230001"}]
_fc_kind = runs_mod._figure_verification(_cits_kind, _fg_a, _rec_fa["audit"])
_ns_kind = runs_mod._figure_citation_ns(_cits_kind, _fg_a)
check("ADR-0083 (E/F, corrector) UN clasificador de cita-figura en runs == el SUPERSET de verify_output: una cita con id de figura pero kind 'paper' gana "
      "figure_verification {bytes 'verified', kind_reported 'paper'}, cuenta en figure_citations.n 1 y n_figure_shaped_other_kind 1, y entra a "
      "cited_ns (citadas primero / n_cited); la cita PMID no; runs._is_figure_citation acepta kind 'figure', forma 'PMC…#…' o id que resuelve",
      "figure_verification" in _cits_kind[0] and _cits_kind[0]["figure_verification"]["bytes"] == "verified"
      and _cits_kind[0]["figure_verification"]["kind_reported"] == "paper" and "figure_verification" not in _cits_kind[1]
      and _fc_kind["n"] == 1 and _fc_kind["n_figure_shaped_other_kind"] == 1 and _ns_kind == {_G001_ID: [1]}
      and runs_mod._is_figure_citation({"kind": "figure", "id": "x"}, {}) and runs_mod._is_figure_citation({"kind": "other", "id": "PMC9#f1"}, {})
      and not runs_mod._is_figure_citation({"kind": "paper", "id": "PMID:1"}, {}),
      json.dumps({"fv": _cits_kind[0].get("figure_verification"), "fc": _fc_kind, "ns": _ns_kind}))
_g4o83 = next(r["reviewer"] for r in _rec_fa["audit"]["panel"] if r["lens"] == "reproducibility")   # el reviewer OpenAI del registro (tile-512)
_t_hi = runs_mod._vision_tokens(_g4o83, {"w": 750, "h": 417})
_t_lo = runs_mod._vision_tokens(_g4o83, {"w": 750, "h": 417}, "low")
_hk83 = next(r["reviewer"] for r in _rec_fa["audit"]["panel"] if r["lens"] == "evidence-grounding")
_t_an = runs_mod._vision_tokens(_hk83, {"w": 750, "h": 417}, "low")
_rows_lo = [{"reviewer": _g4o83, "lens": "reproducibility", "saw_figures": {"n": 2, "sha256s": ["s1", "s2"], "bytes_b64_total": 10}, "attempts": [{}]}]
_items_lo = [{"sha256": "s1", "dims_measured": {"w": 750, "h": 417}}, {"sha256": "s2", "dims_measured": {"w": 738, "h": 840}}]
_bv_lo = runs_mod._vision_by_reviewer(_rows_lo, _items_lo, "low")
_bv_hi = runs_mod._vision_by_reviewer(_rows_lo, _items_lo, "high")
check("ADR-0083 (H, corrector) la proyección de runs honra WITT_FIGURES_OPENAI_DETAIL como composite_auditor: reviewer OpenAI tile-512 750×417 'high' 425 vs 'low' 85; "
      "_vision_by_reviewer(…, 'low') → 2×85 = 170 con detail 'low' (antes runs proyectaba SIEMPRE la fórmula 'high' y el frozen congelaba dos cifras "
      "distintas para el mismo envío); 'high' → 425 + 765 = 1190; Anthropic ignora el detail (_openai_detail_for → None); el id OpenAI se LEE del registro (a)",
      _t_hi["tokens"] == 425 and _t_lo["tokens"] == 85 and _bv_lo[_g4o83]["visual_tokens_projected"] == 170 and _bv_lo[_g4o83]["detail"] == "low"
      and _bv_hi[_g4o83]["visual_tokens_projected"] == 1190 and runs_mod._openai_detail_for(_hk83, "low") is None
      and runs_mod._openai_detail_for(_g4o83, "low") == "low" and _t_an["tokens"] == 405 and models.vision_tier_of(_g4o83)[0] == "tile-512",
      json.dumps({"hi": _t_hi["tokens"], "lo": _t_lo["tokens"], "bv_lo": _bv_lo[_g4o83]["visual_tokens_projected"]}))

# --- (m) CANCELACIÓN durante stage.figures → cancelled con lo declarado hasta ahí ----------------------------------------------------------
_shutil.rmtree(_CR83 / "PMC11379296", ignore_errors=True)   # sin caché → la descarga ocurre y el hook cancela DURANTE la etapa
_box83 = {}
_rid_fm, _rec_fm, _ev_fm, _row_fm = _run83("ADR-0083 m: cancel during figures", _synth83(_ANS_A83, _CIT_A83),
                                           before=lambda rid: _box83.__setitem__("rid", rid),
                                           get=_mk_get83(hook=lambda url: db.request_cancel(_box83["rid"], by="natalia",
                                                                                              reason="smoke: cancel during stage.figures")))
check("ADR-0083 (C/LOTE-01·A3) cancelación pedida DURANTE la descarga: la etapa la ve tras el evento del paper → la corrida queda `cancelled` "
      "(no failed, no disfrazada), sin frozen, con usage_json (gasto previo persistido); la Traza trae stage.figures.plan + paper{start} y "
      "run.state cancelled; la GET ocurrió (1) y ningún stage.synthesize.pass2",
      _row_fm["state"] == "cancelled" and _rec_fm is None and _row_fm.get("usage_json")
      and "stage.figures.plan" in _ev_types(_ev_fm) and "stage.figures.paper" in _ev_types(_ev_fm)
      and "stage.synthesize.pass2" not in _ev_types(_ev_fm) and len(_GET83) == 1
      and _ev_types(_ev_fm)[-1] == "run.state" and _ev_fm[-1]["payload"]["state"] == "cancelled",
      json.dumps({"state": _row_fm["state"], "tail": _ev_types(_ev_fm)[-4:]}))

# --- F8 (integrador) — COSTURAS (O) medidas sobre la corrida (a) y la kill-switch (j); assert GLOBAL anti-binario sobre la BD -------------
_fa_sha_items = {i["sha256"] for i in _items_a if i["bytes_state"] == "verified"}
_fa_bundle = json.loads(_row_fa["bundle_json"])
_fa_sha_bundle = {i["sha256"] for p in _fa_bundle["path_b"]["papers"] for i in ((p.get("figures") or {}).get("items") or [])
                  if i.get("bytes_state") == "verified"}
_fa_sha_ledger = {i["sha256"] for i in (_fa_bundle.get("figures_ledger") or {}).get("items") or [] if i.get("bytes_state") == "verified"}
_fa_panels = _fg_a["vision"]["panels"]
_fa_sha_panels = {s for pnl in _fa_panels for s in (pnl.get("sha256s") or [])}
_fa_rows = list(_rec_fa["audit"]["panel"]) + list((_rec_fa.get("audit_initial") or {}).get("panel") or [])
_fa_saw = {(r["reviewer"], r["lens"]): r["saw_figures"] for r in _fa_rows if isinstance(r.get("saw_figures"), dict)}
_fa_sha_saw = {s for sf in _fa_saw.values() for s in (sf.get("sha256s") or [])}
check("F8 (O) costura sha: frozen.figures.items[verified].sha256 == bundle.path_b.papers[].figures.items == bundle.figures_ledger.items == "
      "vision.panels[].sha256s (lo que _figures_for_panel seleccionó, sha RECALCULADO) == ⋃ audit.panel[].saw_figures.sha256s — las 9 del "
      "MANIFEST, un solo sha por figura (el del original); audit.panel[].saw_figures.sha256s ⊆ frozen.figures.items[].sha256",
      len(_fa_sha_items) == 9 and _fa_sha_items == _fa_sha_bundle == _fa_sha_ledger == _fa_sha_panels == _fa_sha_saw
      == {e["sha256"] for e in _MAN_BY83.values()}
      and all(set(sf.get("sha256s") or []) <= _fa_sha_items for sf in _fa_saw.values()),
      json.dumps({"items": len(_fa_sha_items), "bundle": len(_fa_sha_bundle), "ledger": len(_fa_sha_ledger), "panels": len(_fa_sha_panels),
                  "saw": len(_fa_sha_saw)}))
_fa_judge = _ev_payloads(_ev_fa, "stage.audit.judge")
check("F8 (O) costura judge: stage.audit.judge.figures_sent == audit.panel[].saw_figures.n por (reviewer, lens) en TODOS los intentos, y "
      "figures_sha256 del evento == saw_figures.sha256s (mismo orden); 9 en grounding y reproducibility, 0 en correctness y overclaim",
      len(_fa_judge) >= 4 and all(_fa_saw.get((p["reviewer"], p["lens"]), {}).get("n") == p["figures_sent"]
                                  and (_fa_saw.get((p["reviewer"], p["lens"]), {}).get("sha256s") or []) == p["figures_sha256"]
                                  for p in _fa_judge)
      and sorted(p["figures_sent"] for p in _fa_judge) == [0, 0, 9, 9],
      json.dumps([(p["lens"], p["figures_sent"]) for p in _fa_judge]))
_fa_epi = json.loads(_row_fa["epistemic_summary_json"])
_fa_view = app.get_run(_rid_fa, authorization=AUTH)["epistemic_summary"]
check("F8 (O) costura vista: epistemic_summary.figures_n_verified == frozen.figures.n_verified (9), figures_n_cited == n_cited (1), figures_state "
      "== state ('attached') — en el blob persistido Y en la vista GET /runs/{id} (sin re-derivar)",
      _fa_epi["figures_n_verified"] == _fg_a["n_verified"] == 9 and _fa_epi["figures_n_cited"] == _fg_a["n_cited"] == 1
      and _fa_epi["figures_state"] == _fg_a["state"] == "attached"
      and {k: _fa_view[k] for k in ("figures_state", "figures_n_verified", "figures_n_cited")}
      == {k: _fa_epi[k] for k in ("figures_state", "figures_n_verified", "figures_n_cited")},
      json.dumps({k: _fa_epi.get(k) for k in ("figures_state", "figures_n_verified", "figures_n_cited")}))
_cov_a = _pdf82.pdf_sections_cover(set(_rec_fa))
check("F8 (O/K) costura PDF: record_pdf.pdf_sections_cover(frozen REAL de la corrida (a), 1.12, awaiting_closure) == {missing [], extra "
      "[closed_by, frozen_at]} (las dos nacen al CERRAR: ADR-0073); ninguna llave de servicio (consensus/ratings*) viaja en el frozen; "
      "build_pdf del registro con figuras → 200 bytes %PDF- y 0 red",
      _cov_a["missing"] == [] and sorted(_cov_a["extra"]) == ["closed_by", "frozen_at"]
      and not (set(_rec_fa) & set(_pdf82.SERVICE_KEYS))
      and _pdf82.build_pdf(_rec_fa, compress=False, cache_dir=str(_CR83), thumbs=False)[:5] == b"%PDF-",
      json.dumps(_cov_a))
_fa_tu = _rec_fa["token_usage"].get("figures")
_fa_usage = json.loads(_row_fa["usage_json"])
check("F8 (H) usage_json.figures (contrato F5→F4 cosido): token_usage.figures == espejo de frozen.figures {state, n_figures, n_verified, n_cited} "
      "+ bytes_downloaded == Σ bytes MANIFEST de las 9 verified + class MEASUREMENT; usage_json persistido == frozen.token_usage; bajo "
      "kill-switch (j) la llave NO existe (M.1)",
      isinstance(_fa_tu, dict)
      and {k: _fa_tu[k] for k in ("state", "n_figures", "n_verified", "n_cited")}
      == {k: _fg_a[k] for k in ("state", "n_figures", "n_verified", "n_cited")}
      and _fa_tu["bytes_downloaded"] == sum(e["bytes"] for e in _MAN_BY83.values())
      == sum(i["bytes"] for i in _items_a if i["bytes_state"] == "verified") == _fa_tu["bytes_verified"]
      and _fa_tu["n_cache_hit"] == 0 and all(i["cache_hit"] is False for i in _items_a if i["bytes_state"] == "verified")
      and _fa_tu["class"].startswith("MEASUREMENT") and _fa_usage.get("figures") == _fa_tu
      and "figures" not in _rec_fj["token_usage"] and "figures" not in json.loads(_row_fj["usage_json"]),
      json.dumps(_fa_tu))
_tu_k, _it_k = _rec_fk["token_usage"]["figures"], _rec_fk["figures"]["items"]
_hits_k = [i for i in _it_k if i["bytes_state"] == "verified" and i["cache_hit"] is True]
check("ADR-0083 (H, corrector) token_usage.figures distingue bytes_verified (Σ verified, caché incluida) de bytes_downloaded (SOLO verified con cache_hit "
      "False = red REAL de la corrida) y declara n_cache_hit — invariante medido sobre la corrida (k) (misma caché que (a): "
      f"{len(_hits_k)} cache hits): bytes_downloaded == Σ verified¬hit, bytes_verified == Σ verified, n_cache_hit == hits; class lo dice",
      _tu_k["bytes_verified"] == sum(i["bytes"] for i in _it_k if i["bytes_state"] == "verified")
      and _tu_k["bytes_downloaded"] == sum(i["bytes"] for i in _it_k if i["bytes_state"] == "verified" and i["cache_hit"] is not True)
      and _tu_k["n_cache_hit"] == len(_hits_k) and (_tu_k["bytes_downloaded"] == 0) == (len(_hits_k) == 9)
      and "cache_hit false" in _tu_k["class"],
      json.dumps({k: _tu_k[k] for k in ("bytes_verified", "bytes_downloaded", "n_cache_hit")}))
_fa_dcf = _rec_fa["deterministic_checks"]["figures"]
check("F8 (F.3) costura gate: runs._figure_checks pasa el DICT del sintetizador → figure_only_not_asserted.absence_kind_state 'declared' "
      "(absence_kind 'not-applicable' del stub llegó; NO 'not-provided by caller'), positive_claim True, ok True (1 paper + 1 figure)",
      _fa_dcf["state"] == "checked" and _fa_dcf["figure_only_not_asserted"]["absence_kind_state"] == "declared"
      and _fa_dcf["figure_only_not_asserted"]["absence_kind"] == "not-applicable"
      and _fa_dcf["figure_only_not_asserted"]["positive_claim"] is True and _fa_dcf["figure_only_not_asserted"]["ok"] is True,
      json.dumps({k: _fa_dcf["figure_only_not_asserted"].get(k) for k in ("absence_kind_state", "absence_kind", "ok")}))
_never = TMP / "figcache_never_created"
_b_nox = {"path_b": {"papers": [{"source": "europepmc", "evidence_id": "e1", "search_rec": {"pmcid": "PMC11379296"},
                                 "selection_rank": 1, "fetched": {"found": True, "full_text": True, "raw_cached": []}}]}}
_s_nox = _fig.attach(_b_nox, cfg=_fig.env_config(), cache_root=_never)
check("F8 (B.3) caché perezosa: attach con papers SIN XML de texto completo → 'no-papers-with-xml' con cache.dir_state 'missing' MEDIDO y el "
      "directorio NO se crea (un gate sin WITT_MCP_CACHE_DIR ya no deja <repo>/mcp_cache/figures vacío); con papers seleccionados el dir sí "
      "se crea (la corrida (a) lo midió 'writable')",
      _s_nox["state"] == "no-papers-with-xml" and _s_nox["cache"]["dir_state"] == "missing" and not _never.exists()
      and _plan_ev_a[0]["cache_dir_state"] == "writable" and _fg_a["cache"]["dir_state"] == "writable",
      json.dumps(_s_nox["cache"]))
import re as _re_f8  # noqa: E402
import sqlalchemy as _sa_f8  # noqa: E402
_B64_RE_F8 = _re_f8.compile(r"[A-Za-z0-9+/]{300,}={0,2}")
_B64_PREFIXES_F8 = [b[:80] for b in _B64_BY83.values()]
with db.engine().begin() as _cx:
    _all_rows = _cx.execute(_sa_f8.select(db.runs.c.run_id, db.runs.c.frozen_record_json, db.runs.c.bundle_json,
                                          db.runs.c.usage_json, db.runs.c.epistemic_summary_json)).all()
_bin_hits = []
for _r in _all_rows:
    for _col in ("frozen_record_json", "bundle_json", "usage_json", "epistemic_summary_json"):
        _blob = _r._mapping[_col] or ""
        if "data:image" in _blob or any(pfx in _blob for pfx in _B64_PREFIXES_F8) or _B64_RE_F8.search(_blob):
            _bin_hits.append(f"{_r._mapping['run_id']}:{_col}")
check("F8 (D.1/M.6) assert GLOBAL anti-binario sobre TODA la BD del gate: ningún frozen_record_json / bundle_json / usage_json / "
      f"epistemic_summary_json de las {len(_all_rows)} corridas contiene 'data:image', la b64 de las 9 figuras del fixture (prefijos de 80) "
      "ni una cadena base64 ≥ 300 chars — nada binario en el blob (ADR-0074)",
      len(_all_rows) >= 60 and _bin_hits == [], json.dumps({"runs": len(_all_rows), "hits": _bin_hits[:10]}))

# --- cero red en la sección + restauración --------------------------------------------------------------------------------------------
check("ADR-0083 (M.5) la sección corrió 100% OFFLINE: figures._urlopen fue el bloqueador contado durante toda la sección y el contador global "
      "NO se movió (0 llamadas); la caché de figuras vivió en TMP (WITT_MCP_CACHE_DIR), jamás en mcp_cache del repo",
      _fig._urlopen is _urlopen_blocked and len(_NET_CALLS) == _net_before83
      and _CR83.exists() and not (answer_pipeline.CACHE / "figures" / "PMC11379296").exists(),
      json.dumps({"net_calls_delta": len(_NET_CALLS) - _net_before83}))
_fig._urlopen = _FIG_URLOPEN_SAVED83
_fig._get_bytes = _REAL_GET83
if _MCP_ENV_SAVED83 is None:
    os.environ.pop("WITT_MCP_CACHE_DIR", None)
else:
    os.environ["WITT_MCP_CACHE_DIR"] = _MCP_ENV_SAVED83
_sources_found()

# =====================================================================================================================
# ADR-0084 (W7, integrador) — la WEB como LOCALIZADOR, jamás fuente: contrato 1.13. Corridas por la puerta con el consejo FAKE
# (copia F.4 con un `must` de familia web), el tool Brave REAL cargado por ruta con su ÚNICA costura de red `_get` parcheada
# (llave fake SÓLO en la cabecera), el resolutor REAL (W2), el harness REAL (W3), la admisión native-first REAL (W4), los
# predicados REALES (W5), el consejo dinámico REAL (W6) y la cuota REAL en la BD (H). Europe PMC y fetch_external FALSOS.
# Doctrina medida: 0 ítems con source 'web'; ninguna URL hallada fuera de frozen.web_locator (ni en eventos, ni en el prompt,
# ni en answer.gap_flags, ni en el snapshot del hijo); kill-switch M.1 byte a byte salvo EXACTAMENTE 3 excepciones.
# =====================================================================================================================
from lib import web_locator as _wl84  # noqa: E402
from lib import fetch_paper as _fp84  # noqa: E402

FAKE_KEY84 = "fake-brave-key-adr84-never-in-output-0084"
WEB_TEXT84 = "DESCRIPTION-WEB-TEXT-NEVER-EVIDENCE-84"
_URLS84 = {
    "pm333": "https://pubmed.ncbi.nlm.nih.gov/33333333/?dopt=Abstract",   # PMID nuevo → materializado (EPMC lo tiene)
    "doi666": "https://doi.org/10.1000/web666",                            # DOI nuevo → materializado (EPMC lo tiene)
    "pm111": "https://pubmed.ncbi.nlm.nih.gov/11111111/",                  # PMID que EPMC nativo YA trae → dup del pool (native-first)
    "doi_nf": "https://doi.org/10.1000/notfound84",                        # DOI que EPMC NO tiene → not-found-in-europepmc (gap k)
    "rg": "https://www.researchgate.net/publication/777_wt1a_pronephros",   # sin patrón → unresolved (gap n)
    "zfin": "https://zfin.org/ZDB-GENE-980526-558",                        # curie → ctx:curies (fed-same-round)
}
_ANTH_FX84 = json.loads((Path(__file__).resolve().parent / "fixtures" / "anthropic_web_search_SYNTHETIC_wt1a_20260916.json")
                        .read_text(encoding="utf-8"))
_ANTH_URLS84 = [x.get("url") for c in _ANTH_FX84["response"]["content"] if c.get("type") == "web_search_tool_result"
                for x in (c.get("content") or []) if isinstance(x, dict) and x.get("url")]
_ALL_WEB_URLS84 = list(_URLS84.values()) + _ANTH_URLS84
# URLs HALLADAS que JAMÁS son la canónica de un identificador (la canónica de un DOI es https://doi.org/<doi> — idéntica a la hallada — y
# ES identificador, viaja legítimamente en papers[].url): pubmed con '?dopt', el DOI no materializado y la de researchgate sin patrón
_LEAK_URLS84 = [_URLS84["pm333"], _URLS84["doi_nf"], _URLS84["rg"]]


def _res84(url, title):
    return {"title": title, "url": url, "description": WEB_TEXT84 + " " + title, "extra_snippets": [WEB_TEXT84], "age": None,
            "page_age": None, "language": "en", "family_friendly": True, "meta_url": {"hostname": urllib.parse.urlparse(url).hostname}}


_WEB84 = [_res84(_URLS84["pm333"], "WEB TITLE pubmed 333 (never evidence)"), _res84(_URLS84["doi666"], "WEB TITLE doi 666"),
          _res84(_URLS84["pm111"], "WEB TITLE pubmed 111 already native"), _res84(_URLS84["doi_nf"], "WEB TITLE doi not in EPMC"),
          _res84(_URLS84["rg"], "WEB TITLE researchgate " + "R" * 180), _res84(_URLS84["zfin"], "WEB TITLE zfin wt1a")]


def _rec84(pmid, pmcid=None, doi=None, is_oa=False, title=None):
    return {"epmc_id": pmid, "source": "MED", "pmid": pmid, "pmcid": pmcid, "doi": doi, "title": title or f"EPMC record {pmid}",
            "year": "2021", "journal": "Dev Biol", "is_oa": is_oa, "abstract": f"wt1a pronephros podocyte abstract (Europe PMC) {pmid}",
            "cited_by": 3}


_REC333 = _rec84("33333333", title="EPMC record for web-located 333")
_REC888 = _rec84("88888888", pmcid="PMC888", doi="10.1000/web666", is_oa=True, title="EPMC record for web-located DOI 666")
_EPMC84 = {"PMID:33333333": _REC333, "DOI:10.1000/web666": _REC888, "PMID:11111111": _EPMC_RECS[0]}


class _FakeBraveNet84:
    """La ÚNICA costura de red del tool Brave (W1 `_get`): misma firma, respuesta con la forma documentada; cuenta GETs y si la
    llave viajó SÓLO en la cabecera (jamás en la URL)."""

    def __init__(self, results):
        self.calls, self.results = [], results

    def __call__(self, url, timeout=None, with_headers=True, api_key=None):
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        q = (qs.get("q") or [""])[0]
        self.calls.append({"q": q, "key_in_header": api_key == FAKE_KEY84, "key_in_url": FAKE_KEY84 in url, "url": url})
        js = {"type": "search", "query": {"original": q, "altered": None, "more_results_available": False},
              "web": {"type": "search", "results": [dict(r) for r in self.results]}}
        return (js, {"X-RateLimit-Limit": "1, 2000", "X-RateLimit-Remaining": "0, 1999"}) if with_headers else js


class _EpmcSpy84:
    """corrector ADR-0084: la ronda materializa por fetch_paper.search_europepmc_ledger(<consulta por ident>, n=1, timeout=<presupuesto>)
    — el spy sirve por ident (search_harness.epmc_ident_of_query), registra `calls` (idents) y `timeouts`, y delega las búsquedas LIBRES
    (la familia europepmc nativa) al fake que estaba activo (`native`)."""

    def __init__(self, recs, native=None):
        self.calls, self.timeouts, self.recs, self.native = [], [], dict(recs), native

    def __call__(self, query, n=5, sort=None, synonym=True, timeout=None):
        ident = _sh.epmc_ident_of_query(query)
        if ident is None:
            return self.native(query, n=n, sort=sort, synonym=synonym)
        self.calls.append(ident)
        self.timeouts.append(timeout)
        rec = self.recs.get(ident)
        return ([dict(rec)] if rec else []), {"source": "europepmc", "status": "success" if rec else "no-match", "query_sent": query,
                                              "n_found": 1 if rec else 0, "n_returned": 1 if rec else 0, "elapsed_s": 0.01}


def _fake_fetch84(ident, want_full_text=True):
    """fetch_external FALSO: los web-localizados 333/666 se bajan (found True: el candidato ES citable); los nativos como en ADR-0080."""
    if ident in ("PMID:33333333", "PMID:88888888"):
        return {"found": True, "full_text": False, "n_chunks": 1, "raw_cached": [], "raw_ref": None,
                "record": {"abstract": _EPMC84["PMID:33333333" if ident == "PMID:33333333" else "DOI:10.1000/web666"]["abstract"]},
                "cache_hit": False, "cached_at": None, "fetched_at": "2026-09-16T00:00:00Z"}
    return _fake_fetch_content(ident, want_full_text=want_full_text)


_SYNTH84, _PANEL84, _COUNCIL84 = [], [], []


def _mk_synth84(answer_text, cited, conf=None):
    conf = conf or {"pass1": 0.8, "pass2": 0.85, "revision": 0.85}

    def _s(question, evidence, pass_label, thread_context=None, human_attestations=None):
        _SYNTH84.append({"pass": pass_label, "json": json.dumps(evidence, ensure_ascii=False, default=str)})
        out = _mk_synth(conf)(question, evidence, pass_label)
        out["direct_answer"] = answer_text
        out["evidence_cited"] = json.loads(json.dumps(_C_CITED_OK if pass_label == "pass1" else cited))
        return out
    return _s


def _panel84():
    def _caller(member, system, user_text):
        _PANEL84.append({"lens": member["lens"], "user_text": user_text})
        return ({"verdict": "APPROVE", "caught": "", "correction_applied": "", "confidence": 0.9, "reasons": []},
                {"input_tokens": 10, "output_tokens": 5})
    return _caller


def _council84(uncovered=("web",)):
    inner = _mk_council_caller(uncovered_fams=uncovered)

    def _caller(request):
        _COUNCIL84.append({"round": request["round"], "agent": request["agent"], "user_text": request["user_text"]})
        return inner(request)
    return _caller


# r1 AGREGADA con la llave presente: el requisito web nace 'satisfiable' (gateable) — así la ronda 2 puede dejarlo uncovered y el
# consejo COMPILA la directiva web (F.1/F.2); bajo off la compilación lo recomputa y lo EXCLUYE con el literal de 7d9ce15
_C_AGG84 = _with_env({"BRAVE_API_KEY": FAKE_KEY84, "WITT_WEB_LOCATOR": "brave"},
                     lambda: _council.aggregate_r1(_C_R1, members=_C_MEMBERS, cfg=_C_CFG))
_c_by_fam84 = {}
for _r in _C_AGG84["requirements"]:
    _c_by_fam84.setdefault(_r["source_family"], _r)
_c_rid84 = {f: _c_by_fam84[f]["requirement_id"] for f in _c_by_fam84}
_C_LEDGER84 = _council.apply_ledger_decisions(
    _C_AGG84, decisions=[{"requirement_id": _c_rid84["zfin"], "decision": "keep"},
                         {"requirement_id": _c_rid84["geo"], "decision": "discard", "reason": "fuera del alcance"},
                         {"requirement_id": _c_rid84["pubmed"], "decision": "aporto",
                          "attested_text": "Our lab confirmed podocyte wt1a expression in situ (notebook 2026-08)."}],
    approve=True, decided_by="natalia", decided_at=_C_AT, knowledge_now="We already know wt1a marks the pronephros.")


def _c_json84(ledger, plan_id):
    r1 = {**_C_AGG84, "rounds": [_C_R1], "members": list(_C_MEMBERS), "full_council": False, "catalog_sha": _cc.CATALOG_SHA,
          "n_members": 17, "membership_version": _am.MEMBERSHIP_VERSION, "model": _C_R1["model"]}
    return {"plan_id": plan_id, "r1_state": "applicable", "r1": r1, "ledger": ledger,
            "membership_version": _am.MEMBERSHIP_VERSION, "n_members": 17, "members": list(_C_MEMBERS), "full_council": False,
            "catalog_sha": _cc.CATALOG_SHA, "membership_source": "plan.council (frozen at r1)", "composed_at": _C_AT,
            "source": "plans.council_json + plans.council_ledger_json (copied at enqueue)"}


_ANS84 = "wt1a marks the zebrafish pronephros podocyte [1][2]."
_CIT84 = [{"kind": "paper", "id": "PMID:33333333"}, {"kind": "di-record", "id": "CORPUS-2026-0001"}]
_BRAVE_MOD84 = _wl84._load_brave_tool()[0]
_REAL_GET84 = _BRAVE_MOD84._get
_REAL_RESOLVE84 = _fp84.search_europepmc_ledger
_REAL_POST84 = _wl84._post_json
_RUNS84 = []   # (run_id, kind) para el assert GLOBAL sobre la BD


def _run84(question, plan_id, env=None, uncovered=("web",), synth=None, web_results=None, epmc=None, cj=None, anthropic_fx=None):
    """Una corrida por la puerta (plan + copia F.4 del consejo) con los fakes de red del localizador; `env` sólo durante la corrida.
    Devuelve (run_id, frozen|None, events, row, net, espy)."""
    tmp_cache = TMP / f"mcp84-{plan_id}"
    tmp_cache.mkdir(parents=True, exist_ok=True)
    env = {"WITT_WEB_LOCATOR": "brave", "BRAVE_API_KEY": FAKE_KEY84, "WITT_WEB_MIN_INTERVAL_S": "0",
           "WITT_MCP_CACHE_DIR": str(tmp_cache), "WITT_PATH_B_N_PAPERS": "10", **(env or {})}   # top-n 10: los web-localizados caben
    saved = {k: os.environ.get(k) for k in env}
    for k, v in env.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    _SYNTH84.clear(); _PANEL84.clear(); _COUNCIL84.clear()
    net = _FakeBraveNet84(web_results if web_results is not None else _WEB84)
    espy = _EpmcSpy84(epmc if epmc is not None else _EPMC84, native=_fp84.search_europepmc_ledger)
    _sources_found()
    _BRAVE_MOD84._get = net
    _fp84.search_europepmc_ledger = espy
    answer_pipeline.fetch_paper.fetch_external = _fake_fetch84
    if anthropic_fx is not None:
        _wl84._post_json = lambda url, body, headers, timeout, inflight=None, urlopen=None: (200, anthropic_fx, json.dumps(anthropic_fx))
    try:
        plan_obj = runs_mod.build_plan(question, ["wt1a"], planner=_fake_planner_ok, history_rows=HIST_OK)
        rid = runs_mod.new_run("natalia", question, ["wt1a"], plan_json=json.dumps(plan_obj, default=str),
                               council_json=json.dumps(cj if cj is not None else _c_json84(_C_LEDGER84, plan_id),
                                                       ensure_ascii=False, default=str))
        claimed = db.claim_next_queued(worker_id="run-worker-adr0084")
        assert claimed and claimed["run_id"] == rid, "FIFO: la corrida reclamada debe ser la esperada"
        runs_mod.execute_run(claimed, synthesizer=synth or _mk_synth84(_ANS84, _CIT84), panel_caller=_panel84(),
                             council_caller=_council84(uncovered))
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        _BRAVE_MOD84._get = _REAL_GET84
        _fp84.search_europepmc_ledger = _REAL_RESOLVE84
        _wl84._post_json = _REAL_POST84
        answer_pipeline.fetch_paper.fetch_external = _fake_fetch_content
    row = db.get_run(rid)
    frozen = json.loads(row["frozen_record_json"]) if row.get("frozen_record_json") else None
    _RUNS84.append(rid)
    return rid, frozen, app.get_events(rid, after=0, authorization=AUTH)["events"], row, net, espy


def _urls_in84(text):
    return [u for u in _LEAK_URLS84 if u in text]


def _no_web_text84(text):
    return not _urls_in84(text) and "WEB TITLE" not in text and WEB_TEXT84 not in text and FAKE_KEY84 not in text


# --- estático: contrato 1.13, 3 excepciones, cableado del tool, constantes aliasadas (una verdad) --------------------------------
check("ADR-0084 (G.1/G.11) RENDER_CONTRACT_VERSION == '1.13' apilado sobre 1.12; WEB_DECLARED_EXCEPTIONS son EXACTAMENTE 3 (M.1); "
      "WEB_KILL_SWITCH_STATE aliasa web_locator.WEB_KILL_SWITCH_STATE (una verdad); FIGURES_DECLARED_EXCEPTIONS intactas",
      runs_mod.RENDER_CONTRACT_VERSION == "1.13"
      and runs_mod.WEB_DECLARED_EXCEPTIONS == ("render_contract_version", "web_locator", "deterministic_checks.web_locator")
      and runs_mod.WEB_KILL_SWITCH_STATE == _wl84.WEB_KILL_SWITCH_STATE == "kill-switch WITT_WEB_LOCATOR=off"
      and runs_mod.FIGURES_DECLARED_EXCEPTIONS == ("render_contract_version", "figures", "deterministic_checks.figures"))
_sh._TOOL_CACHE.pop("web", None)
_web_fn, _web_resolved, _web_detail = _sh._load_tool("web")
check("ADR-0084 (C.1) cableado ESTÁTICO: SEARCH_DISPATCH['web'] apunta al archivo REAL .tooluniverse/tools/brave_web_search.py y "
      "_load_tool('web') resuelve EXACTAMENTE 'locate' (sin nota); 13 módulos reales (12 + brave) bajo .tooluniverse/tools; "
      "len(SEARCH_DISPATCH) == 15; _path_b_bundle_accepts() ⊇ {search_plan, on_stage, existing_ids, web_quota}; _web_quota_fn() es "
      "db.web_locator_reserve",
      callable(_web_fn) and _web_resolved == "locate" and _web_detail is None
      and (_sh._TU_WORKSPACE / "brave_web_search.py").exists()
      and len([p for p in _sh._TU_WORKSPACE.glob("*.py")]) >= 13 and len(_sh.SEARCH_DISPATCH) == 15
      and {"search_plan", "on_stage", "existing_ids", "web_quota"} <= runs_mod._path_b_bundle_accepts()
      and runs_mod._web_quota_fn() is db.web_locator_reserve,
      json.dumps({"resolved": _web_resolved, "detail": _web_detail, "accepts": sorted(runs_mod._path_b_bundle_accepts())}))
_sh._TOOL_CACHE.pop("web", None)
check("ADR-0084 (D.1) gate ESTÁTICO del prompt: _PROMPT_PATH_B_TOP y _PROMPT_PAPER_KEYS NO incluyen web_locator/url/located_from/"
      "title_web/description (el sintetizador es CIEGO al ledger por lista blanca)",
      not ({"web_locator", "url", "located_from", "title_web", "description", "search_ledger"} & set(runs_mod._PROMPT_PATH_B_TOP))
      and not ({"web_locator", "url", "located_from", "title_web", "description"} & set(runs_mod._PROMPT_PAPER_KEYS)))
_snap84 = models.snapshot(extra=runs_mod.snapshot_extra())
check("ADR-0084 (tabla de env) el snapshot de configuración trae web.locator {'' , default-unset:WITT_WEB_LOCATOR} y web.provider "
      "{'off', 'default-derived:BRAVE_API_KEY absent'} DERIVADOS por models (SNAPSHOT_FIELDS += 2, FUERA de panel_signature); "
      "snapshot_extra() sigue cubriendo EXACTAMENTE models.EXTRA_FIELDS",
      _snap84["fields"]["web.locator"] == {"value": "", "source": "default-unset:WITT_WEB_LOCATOR"}
      and _snap84["fields"]["web.provider"] == {"value": "off", "source": "default-derived:BRAVE_API_KEY absent"}
      and set(runs_mod.snapshot_extra()) == set(models.EXTRA_FIELDS) and _snap84.get("extra_ignored") == []
      and models.SNAPSHOT_FIELDS[-6:-4] == models.WEB_SNAPSHOT_FIELDS == ("web.locator", "web.provider")
      # ADR-0086 (F3a): los 4 interruptores de lo atestiguado cierran la lista, FUERA de panel_signature
      and models.SNAPSHOT_FIELDS[-4:] == models.ATTESTED_SNAPSHOT_FIELDS,
      json.dumps({k: _snap84["fields"].get(k) for k in ("web.locator", "web.provider")}))

# --- (q) CUOTA primero (tabla limpia): WITT_WEB_MONTHLY_CAP=1 → 1ª corrida granted, 2ª skipped-cap con detail, CERO GETs -----------
with db.engine().begin() as _cx84:
    _cx84.execute(_sa_f8.text("DELETE FROM web_locator_usage"))
_rid_q1, _rec_q1, _ev_q1, _row_q1, _net_q1, _esp_q1 = _run84("ADR-0084 q1: web quota granted", "plan-84-q1", env={"WITT_WEB_MONTHLY_CAP": "1"})
_rid_q2, _rec_q2, _ev_q2, _row_q2, _net_q2, _esp_q2 = _run84("ADR-0084 q2: web quota reached", "plan-84-q2", env={"WITT_WEB_MONTHLY_CAP": "1"})
_wl_q1, _wl_q2 = _rec_q1["web_locator"], _rec_q2["web_locator"]
_month84 = _wl84.month_utc()
_mtd84 = db.web_locator_month_to_date("brave", _month84)
check("ADR-0084 (H/G.10) CUOTA inyectada por firma (db.web_locator_reserve): WITT_WEB_MONTHLY_CAP=1 → corrida q1 'located' con quota "
      "{state 'under-cap', n_before 0, n_after 1, cap 1, hook 'ctx.web_quota'} y 1 GET; corrida q2 (mismo mes UTC) → frozen.web_locator.state "
      "'skipped-cap (monthly cap WITT_WEB_MONTHLY_CAP=1 reached (n_queries=1, month <m>))', quota.state 'cap-reached', CERO GETs al proveedor, "
      "0 stage.web.locate… NO: UN latido declarado (consulta skipped-cap) sin URLs; la fila del mes queda en n_queries 1 con n_results 6",
      _wl_q1["state"] == "located" and _wl_q1["quota"]["state"] == "under-cap" and _wl_q1["quota"]["n_before"] == 0
      and _wl_q1["quota"]["n_after"] == 1 and _wl_q1["quota"]["cap"] == 1 and _wl_q1["quota"]["hook"] == "ctx.web_quota"
      and len(_net_q1.calls) == 1
      and _wl_q2["state"] == f"skipped-cap (monthly cap WITT_WEB_MONTHLY_CAP=1 reached (n_queries=1, month {_month84}))"
      and _wl_q2["quota"]["state"] == "cap-reached" and len(_net_q2.calls) == 0
      and _mtd84["n_queries"] == 1 and _mtd84["n_results"] == 6 and abs(_mtd84["cost_usd_projected"] - 0.005) < 1e-9
      and len(_ev_payloads(_ev_q2, "stage.web.locate")) == 1
      and _ev_payloads(_ev_q2, "stage.web.locate")[0]["provider_status"] == "skipped-cap",
      json.dumps({"q1": _wl_q1["quota"], "q2": {"state": _wl_q2["state"], "quota": _wl_q2["quota"]}, "mtd": _mtd84}, default=str)[:600])
_ai_q2 = next(a for a in _rec_q2["agents_invoked"] if a["agent"] == runs_mod.WEB_LOCATOR_AGENT_ROW)
check("ADR-0084 (G.9, corrector) bajo skipped-cap la fila web de agents_invoked NO es 'invoked' (corrió pero NO envió): status "
      "'not-applicable (skipped-cap (monthly cap …))', invocation_id 'web_locator:-/-' y evidence_generated con '-' (jamás el literal 'None')",
      _ai_q2["status"].startswith("not-applicable (skipped-cap (monthly cap WITT_WEB_MONTHLY_CAP=1 reached")
      and _ai_q2["invocation_id"] == "web_locator:-/-" and "located:-" in _ai_q2["evidence_generated"]
      and not any("None" in e for e in _ai_q2["evidence_generated"]) and _ai_q2.get("reason"),
      json.dumps(_ai_q2))
check("ADR-0084 (G.7) bajo skipped-cap la familia CORRIÓ (declarada): token_usage.web_locator {n_queries 1, n_queries_billable 0, "
      "usd_projected 0.0, quota_state 'cap-reached'} presente y estimated_cost_usd_total_projected == estimated_cost_usd (nada facturable)",
      _rec_q2["token_usage"]["web_locator"]["n_queries"] == 1 and _rec_q2["token_usage"]["web_locator"]["n_queries_billable"] == 0
      and _rec_q2["token_usage"]["web_locator"]["usd_projected"] == 0.0
      and _rec_q2["token_usage"]["web_locator"]["quota_state"] == "cap-reached"
      and _rec_q2["token_usage"]["estimated_cost_usd_total_projected"] == _rec_q2["token_usage"]["estimated_cost_usd"],
      json.dumps(_rec_q2["token_usage"]["web_locator"], default=str)[:300])

# --- (a) la corrida 'located' de punta a punta (cap default 900) ----------------------------------------------------------------------
_rid_wa, _rec_wa, _ev_wa, _row_wa, _net_wa, _esp_wa = _run84("ADR-0084 a: web located end to end", "plan-84-a")
_t_wa = _ev_types(_ev_wa)
_wl_a = _rec_wa["web_locator"]
_sl_a = _rec_wa["search_ledger"]
_papers_a = json.loads(_row_wa["bundle_json"])["path_b"]["papers"]
_web_papers_a = [p for p in _papers_a if p.get("source_family") == "web"]
_src_ev_a = _ev_payloads(_ev_wa, "stage.search.source")
_web_src_ev_a = [p for p in _src_ev_a if p.get("family") == "web"]
_loc_ev_a = _ev_payloads(_ev_wa, "stage.web.locate")
_i_web_src = next(i for i, e in enumerate(_ev_wa) if e["type"] == "stage.search.source" and e["payload"].get("family") == "web")
check("ADR-0084 (C.4/G.6) TRAZA: no competente (must web sin cubrir) → stage.council.directives {families ['web']} → stage.search.plan "
      "(families[0] == 'web', families_order_rule) → stage.web.locate ×1 (agent 'web_locator', UNO por consulta) → stage.search.source(web) "
      "PRIMERA de la ronda → stage.search.round → stage.path_b → pass2; el proveedor Brave REAL recibió UNA GET con la llave SÓLO en la "
      "cabecera (no en la URL)",
      _rec_wa["competence"]["competent"] is False and _ev_payloads(_ev_wa, "stage.council.directives")[0]["families"] == ["web"]
      and _sl_a["plan"]["families"][0] == "web" and _sl_a["plan"]["families_order_rule"] == _sh.FAMILIES_ORDER_RULE_WEB_FIRST
      and len(_loc_ev_a) == 1 and all(e["agent"] == "web_locator" for e in _ev_wa if e["type"] == "stage.web.locate")
      and _t_wa.index("stage.search.plan") < _t_wa.index("stage.web.locate") < _i_web_src < _t_wa.index("stage.search.round")
      < _t_wa.index("stage.path_b") < _t_wa.index("stage.synthesize.pass2")
      and _src_ev_a[0].get("family") == "web"
      and len(_net_wa.calls) == 1 and _net_wa.calls[0]["key_in_header"] is True and _net_wa.calls[0]["key_in_url"] is False,
      json.dumps({"families": _sl_a["plan"]["families"], "stages": [t for t in _t_wa if t.startswith("stage.")][:16],
                  "net": [{k: v for k, v in c.items() if k != "url"} for c in _net_wa.calls]}))
check("ADR-0084 (G.2) frozen.web_locator 'located': provider 'brave' (env:WITT_WEB_LOCATOR), entered_by 'directive', directive_requirement_ids "
      "[req web], gate 'directive-only', versiones wl-1/wlr-2/bws-1, measured True, n_queries 1, n_results 6, n_located 5, n_unresolved 1, "
      "n_materialized 3 (333, el DOI 666 → PMID 888 y el 111 que el pool declaró dup), n_not_found_in_europepmc 1, n_already_present_pool 1, n_admitted 2, "
      "n_papers_web_located 2, gap_flags_typed 2 (unresolved + unmaterialized), cost {n_queries_billable 1, usd_projected 0.005, class "
      "'proyección'}, quota under-cap, resolver_rules 12, state_vocabulary, text_policy, rule; kill_switch AUSENTE",
      _wl_a["state"] == "located" and _wl_a["provider"] == "brave" and _wl_a["provider_source"] == "env:WITT_WEB_LOCATOR"
      and _wl_a["entered_by"] == "directive" and _wl_a["directive_requirement_ids"] == [_c_rid84["web"]] and _wl_a["gate"] == "directive-only"
      and (_wl_a["module_version"], _wl_a["resolver_version"], _wl_a["tool_version"]) == ("wl-1", "wlr-2", "bws-1")
      and _wl_a["measured"] is True and _wl_a["n_queries"] == 1 and _wl_a["n_results"] == 6 and _wl_a["n_located"] == 5
      and _wl_a["n_unresolved"] == 1 and _wl_a["n_materialized"] == 3 and _wl_a["n_not_found_in_europepmc"] == 1
      and _wl_a["n_already_present_pool"] == 1 and _wl_a["n_admitted"] == 2 and _wl_a["n_papers_web_located"] == 2
      and len(_wl_a["gap_flags_typed"]) == 2 and _wl_a["n_gap_flags"] == {"web-located-unresolved": 1, "web-located-unmaterialized": 1}
      and _wl_a["cost"]["n_queries_billable"] == 1 and _wl_a["cost"]["usd_projected"] == 0.005 and _wl_a["cost"]["class"] == "proyección"
      and _wl_a["quota"]["state"] == "under-cap" and len(_wl_a["resolver_rules"]) == 12
      and _wl_a["state_vocabulary"]["exact"] == list(_wl84.WEB_STATES_EXACT) and _wl_a["text_policy"] == _wl84.TEXT_POLICY
      and _wl_a["rule"] == _wl84.WEB_LOCATOR_RULE and "kill_switch" not in _wl_a and _wl_a["source"] == runs_mod.WEB_FROZEN_SOURCE,
      json.dumps({k: _wl_a.get(k) for k in ("state", "n_queries", "n_results", "n_located", "n_unresolved", "n_materialized",
                                              "n_not_found_in_europepmc", "n_already_present_pool", "n_admitted", "n_papers_web_located",
                                              "n_gap_flags")}, default=str))
_loc_a = {l["id"]: l for l in _wl_a["located"]}
check("ADR-0084 (G.2) located[]/unresolved[] del frozen: 5 localizados con url HALLADA (SÓLO aquí), kind/resolver_rule/confidence/canonical_url, "
      "fed_to y feed_state del vocabulario; PMID:33333333 y el DOI 10.1000/web666 (evidence_id PMID:88888888) 'materialized-same-round' admitted True selected True fetched_found True; "
      "PMID:11111111 'already-present (dup of PMID:11111111)' con pool_dedup; 10.1000/notfound84 'not-found-in-europepmc'; ZFIN 'fed-same-round' "
      "ctx:curies; unresolved[0] {url researchgate, title_web ≤ 120 rotulado, reason 'no-identifier-pattern'}",
      set(_loc_a) == {"PMID:33333333", "10.1000/web666", "PMID:11111111", "10.1000/notfound84", "ZFIN:ZDB-GENE-980526-558"}
      and _loc_a["PMID:33333333"]["url"] == _URLS84["pm333"] and _loc_a["PMID:33333333"]["resolver_rule"] == "pubmed-path"
      and _loc_a["PMID:33333333"]["feed_state"] == "materialized-same-round" and _loc_a["PMID:33333333"]["admitted"] is True
      and _loc_a["PMID:33333333"]["selected"] is True and _loc_a["PMID:33333333"]["fetched_found"] is True
      and _loc_a["10.1000/web666"]["resolver_rule"] == "doi-org-path" and _loc_a["10.1000/web666"]["kind"] == "doi"
      and _loc_a["10.1000/web666"]["feed_state"] == "materialized-same-round" and _loc_a["10.1000/web666"]["admitted"] is True
      and _loc_a["10.1000/web666"]["evidence_id"] == "PMID:88888888" and _loc_a["10.1000/web666"]["selected"] is True
      and _loc_a["10.1000/web666"]["fetched_found"] is True and _loc_a["10.1000/web666"]["url"] == _URLS84["doi666"]
      and _loc_a["PMID:11111111"]["feed_state"] == "already-present (dup of PMID:11111111)" and _loc_a["PMID:11111111"]["admitted"] is False
      and _loc_a["PMID:11111111"]["duplicate_of"] == "PMID:11111111" and _loc_a["PMID:11111111"]["pool_dedup"]["layer"] == "pool"
      and _loc_a["10.1000/notfound84"]["feed_state"] == "not-found-in-europepmc"
      and _loc_a["ZFIN:ZDB-GENE-980526-558"]["feed_state"] == "fed-same-round" and _loc_a["ZFIN:ZDB-GENE-980526-558"]["fed_to"] == "ctx:curies"
      and all(_wl84.feed_state_in_vocabulary(l["feed_state"]) and l["fed_to"] in _wl84.FED_TO and l["kind"] in _wl84.LOCATED_KINDS
              for l in _wl_a["located"])
      and len(_wl_a["unresolved"]) == 1 and _wl_a["unresolved"][0]["url"] == _URLS84["rg"]
      and _wl_a["unresolved"][0]["reason"] == "no-identifier-pattern" and len(_wl_a["unresolved"][0]["title_web"]) <= 120,
      json.dumps({k: (v["feed_state"], v.get("admitted"), v.get("selected"), v.get("fetched_found")) for k, v in _loc_a.items()}))
check("ADR-0084 (C.5/D.3) papers del bundle: 0 con source 'web' o kind 'web'; EXACTAMENTE 2 web-localizados (PMID:33333333, PMID:66666666) con "
      "source 'europepmc', source_family 'web', kind 'literature-candidate', identifier_provenance 'web-located:<regla>', url CANÓNICA (la hallada "
      "con '?dopt' AUSENTE), search_rec/título de EPMC ('WEB TITLE' y description AUSENTES en TODO el bundle_json), located_via 'web', located_from "
      "SIN url; el nativo PMID:11111111 conserva su identidad (identifier_provenance 'europepmc-api-live', sin located_via); "
      "n_results_by_source.web == 0 (PMID:33333333 y PMID:88888888 — el DOI 666 materializado por EPMC)",
      not any(p.get("source") == "web" or p.get("kind") == "web" for p in _papers_a)
      and sorted(p["evidence_id"] for p in _web_papers_a) == ["PMID:33333333", "PMID:88888888"]
      and all(p["source"] == "europepmc" and p["kind"] == "literature-candidate" and p["located_via"] == "web"
              and p["identifier_provenance"].startswith("web-located:") and "url" not in p["located_from"] for p in _web_papers_a)
      and next(p for p in _web_papers_a if p["evidence_id"] == "PMID:33333333")["url"] == "https://pubmed.ncbi.nlm.nih.gov/33333333/"
      and next(p for p in _web_papers_a if p["evidence_id"] == "PMID:33333333")["search_rec"]["title"] == "EPMC record for web-located 333"
      and next(p for p in _web_papers_a if p["evidence_id"] == "PMID:88888888")["url"] == "https://doi.org/10.1000/web666"
      and next(p for p in _web_papers_a if p["evidence_id"] == "PMID:88888888")["identifier_provenance"] == "web-located:doi-org-path"
      and "WEB TITLE" not in json.dumps(_papers_a) and WEB_TEXT84 not in _row_wa["bundle_json"] and "?dopt" not in json.dumps(_papers_a)
      and next(p for p in _papers_a if p["evidence_id"] == "PMID:11111111")["identifier_provenance"] == "europepmc-api-live"
      and "located_via" not in next(p for p in _papers_a if p["evidence_id"] == "PMID:11111111")
      and json.loads(_row_wa["bundle_json"])["path_b"]["n_results_by_source"].get("web") == 0,
      json.dumps([(p["evidence_id"], p.get("identifier_provenance"), p.get("url")) for p in _papers_a]))
check("ADR-0084 (E/G.3) deterministic_checks.web_locator 'checked': web_text_not_cited / web_located_cited_requires_fetch / web_items_native_only "
      "ok True gating True, web_urls_not_in_answer ok True gating False, conjunction == los 3 DUROS, rules == verify_output.WEB_RULES, "
      "predicates_version 'wlpred-1'; pass2 ADMISIBLE; stage.deterministic_gate{pass2}.web_locator_state 'checked'",
      _rec_wa["deterministic_checks"]["web_locator"]["state"] == "checked"
      and all(_rec_wa["deterministic_checks"]["web_locator"][p]["ok"] is True for p in _vo.WEB_PREDICATES)
      and all(_rec_wa["deterministic_checks"]["web_locator"][p]["gating"] is _vo.WEB_GATING[p] for p in _vo.WEB_PREDICATES)
      and _rec_wa["deterministic_checks"]["web_locator"]["conjunction"] == ["web_text_not_cited", "web_located_cited_requires_fetch", "web_items_native_only"]
      and _rec_wa["deterministic_checks"]["web_locator"]["rules"] == _vo.WEB_RULES
      and _rec_wa["deterministic_checks"]["web_locator"]["predicates_version"] == "wlpred-1"
      and _rec_wa["deterministic_checks"]["admissible"] is True
      and [p for p in _ev_payloads(_ev_wa, "stage.deterministic_gate") if p.get("pass") == "pass2"][0]["web_locator_state"] == "checked",
      json.dumps({p: _rec_wa["deterministic_checks"]["web_locator"][p]["ok"] for p in _vo.WEB_PREDICATES}))
_gf_a = _rec_wa["answer"]["gap_flags"]
_gf_web_a = [g for g in _gf_a if g.startswith(runs_mod.WEB_GAP_FLAG_PREFIXES)]
check("ADR-0084 (G.4) answer.gap_flags gana EXACTAMENTE los 2 strings de CONTEO por clase ('web-located-unresolved: 1 URL(s) …', "
      "'web-located-unmaterialized: 1 identifier(s) …') apilados por CÓDIGO tras pass2 — SIN ninguna URL, título ni description; el resto de "
      "gap_flags intacto",
      _gf_web_a == [runs_mod.WEB_GAP_FLAG_UNRESOLVED.format(n=1), runs_mod.WEB_GAP_FLAG_UNMATERIALIZED.format(k=1)]
      and _no_web_text84(json.dumps(_gf_a)) and "http" not in json.dumps(_gf_web_a),
      json.dumps(_gf_web_a))
check("ADR-0084 (G.5) citations[]: la cita PMID:33333333 (web-localizada, fetched.found True) gana located_via 'web' y la DI located_via null; "
      "citations_support_summary.n_located_via_web == 1; la cita web-localizada resuelve (support_state ≠ unresolved)",
      [c["located_via"] for c in _rec_wa["citations"]] == ["web", None]
      and _rec_wa["citations_support_summary"]["n_located_via_web"] == 1
      and _rec_wa["citations"][0].get("resolved") is True,
      json.dumps([(c["id"], c.get("located_via"), c.get("support_state")) for c in _rec_wa["citations"]]))
check("ADR-0084 (G.7) token_usage: web_locator {provider 'brave', n_queries 1, n_queries_billable 1, usd_projected 0.005, class 'proyección', "
      "n_results 6, n_located 5, quota_state 'under-cap'} APARTE; estimated_cost_usd INTACTO (cost_class de tokens) y "
      "estimated_cost_usd_total_projected == estimated_cost_usd + 0.005 con total_class; by_stage.search {in 0, out 0, note '… web locator cost "
      "travels apart (ADR-0084)', web_locator_usd_projected 0.005}; by_stage_sum_matches_by_model True",
      _rec_wa["token_usage"]["web_locator"]["provider"] == "brave" and _rec_wa["token_usage"]["web_locator"]["n_queries"] == 1
      and _rec_wa["token_usage"]["web_locator"]["n_queries_billable"] == 1 and _rec_wa["token_usage"]["web_locator"]["usd_projected"] == 0.005
      and _rec_wa["token_usage"]["web_locator"]["class"] == "proyección" and _rec_wa["token_usage"]["web_locator"]["n_results"] == 6
      and _rec_wa["token_usage"]["web_locator"]["n_located"] == 5 and _rec_wa["token_usage"]["web_locator"]["quota_state"] == "under-cap"
      and _rec_wa["token_usage"]["cost_class"].startswith("PROJECTION (calculated from measured tokens x per-Mtok prices")
      and _rec_wa["token_usage"]["estimated_cost_usd_total_projected"] == round(_rec_wa["token_usage"]["estimated_cost_usd"] + 0.005, 4)
      and _rec_wa["token_usage"]["total_class"] == runs_mod.WEB_TOTAL_CLASS
      and _rec_wa["token_usage"]["by_stage"]["search"]["in"] == 0 and _rec_wa["token_usage"]["by_stage"]["search"]["out"] == 0
      and _rec_wa["token_usage"]["by_stage"]["search"]["note"] == runs_mod.WEB_SEARCH_STAGE_NOTE
      and _rec_wa["token_usage"]["by_stage"]["search"]["web_locator_usd_projected"] == 0.005
      and _rec_wa["token_usage"]["by_stage_sum_matches_by_model"] is True,
      json.dumps({"wl": _rec_wa["token_usage"]["web_locator"], "total": _rec_wa["token_usage"].get("estimated_cost_usd_total_projected"),
                  "search": _rec_wa["token_usage"]["by_stage"]["search"]}, default=str)[:500])
_epi_a = app.get_run(_rid_wa, authorization=AUTH)["epistemic_summary"]
_ai_a = {a["agent"]: a for a in _rec_wa["agents_invoked"]}
check("ADR-0084 (G.8/G.9) epistemic_summary {web_locator_state 'located', web_n_located 5, web_n_unresolved 1}; agents_invoked fila "
      "'web_locator (lib/web_locator.py — …)' status 'invoked', provider 'brave', invocation_id 'web_locator:5/6'",
      _epi_a["web_locator_state"] == "located" and _epi_a["web_n_located"] == 5 and _epi_a["web_n_unresolved"] == 1
      and _ai_a[runs_mod.WEB_LOCATOR_AGENT_ROW]["status"] == "invoked" and _ai_a[runs_mod.WEB_LOCATOR_AGENT_ROW]["provider"] == "brave"
      and _ai_a[runs_mod.WEB_LOCATOR_AGENT_ROW]["invocation_id"] == "web_locator:5/6",
      json.dumps({"epi": {k: _epi_a[k] for k in ("web_locator_state", "web_n_located", "web_n_unresolved")},
                  "row": _ai_a.get(runs_mod.WEB_LOCATOR_AGENT_ROW)}))
_pass2_json_a = next(s["json"] for s in _SYNTH84 if s["pass"] == "pass2")
_r3_texts_a = [c["user_text"] for c in _COUNCIL84 if c["round"] == "r3"]
check("ADR-0084 (doctrina, Context 3) NINGÚN texto web llega al modelo: el user_text de pass2 (evidencia), de las 4 lentes del panel y de la "
      "ronda 3 del consejo NO contienen ninguna URL hallada, 'WEB TITLE', la description ni la llave fake; el evidence de pass2 no trae la llave "
      "'web_locator'; r3 SÍ corrió (n_admitted > 0)",
      _no_web_text84(_pass2_json_a) and '"web_locator"' not in _pass2_json_a
      and all(_no_web_text84(p["user_text"]) for p in _PANEL84) and len(_PANEL84) >= 4
      and _r3_texts_a and all(_no_web_text84(t) for t in _r3_texts_a),
      json.dumps({"n_panel": len(_PANEL84), "n_r3": len(_r3_texts_a), "urls_pass2": _urls_in84(_pass2_json_a)}))
_ev_json_a = json.dumps([e["payload"] for e in _ev_wa], ensure_ascii=False, default=str)
check("ADR-0084 (G.6) NINGUNA URL hallada en NINGÚN evento de la corrida (payloads de stage.web.locate, stage.search.source(web), stage.path_b, "
      "stage.search.round…); stage.web.locate {round 1, provider 'brave', query_en, requirement_ids [req web], provider_status 'success', n_results 6, "
      "n_located 5, n_materialized 3, n_unresolved 1, located_ids (ids nativos), hosts_unresolved ['www.researchgate.net'], cost_usd_projected 0.005, "
      "quota {state, n_after, cap}}; stage.search.source(web) += provider/n_queries/n_located/n_materialized/cost_usd_projected/quota_state; "
      "stage.path_b += n_web_located 5 / n_web_unresolved 1",
      not _urls_in84(_ev_json_a) and "WEB TITLE" not in _ev_json_a and WEB_TEXT84 not in _ev_json_a and FAKE_KEY84 not in _ev_json_a
      and _loc_ev_a[0]["round"] == 1 and _loc_ev_a[0]["provider"] == "brave" and _loc_ev_a[0]["requirement_ids"] == [_c_rid84["web"]]
      and _loc_ev_a[0]["provider_status"] == "success" and _loc_ev_a[0]["n_results"] == 6 and _loc_ev_a[0]["n_located"] == 5
      and _loc_ev_a[0]["n_materialized"] == 3 and _loc_ev_a[0]["n_unresolved"] == 1
      and set(_loc_ev_a[0]["located_ids"]) == set(_loc_a) and _loc_ev_a[0]["hosts_unresolved"] == ["www.researchgate.net"]
      and _loc_ev_a[0]["cost_usd_projected"] == 0.005 and set(_loc_ev_a[0]["quota"]) == {"state", "n_after", "cap"}
      and _web_src_ev_a[0]["provider"] == "brave" and _web_src_ev_a[0]["n_queries"] == 1 and _web_src_ev_a[0]["n_located"] == 5
      and _web_src_ev_a[0]["n_materialized"] == 3 and _web_src_ev_a[0]["cost_usd_projected"] == 0.005 and _web_src_ev_a[0]["quota_state"] == "under-cap"
      and _ev_payloads(_ev_wa, "stage.path_b")[0]["n_web_located"] == 5 and _ev_payloads(_ev_wa, "stage.path_b")[0]["n_web_unresolved"] == 1,
      json.dumps({"locate": {k: _loc_ev_a[0].get(k) for k in ("provider_status", "n_results", "n_located", "located_ids", "hosts_unresolved")},
                  "src": {k: _web_src_ev_a[0].get(k) for k in ("provider", "n_queries", "n_located", "quota_state")}}))
check("ADR-0084 (corrector: C.4/D.1/D.2 en los EVENTOS) stage.search.plan.payload lleva families_order_rule (WEB_FIRST) y "
      "stage.path_b.selection lleva pool_admission_rule / tie_break_web_located — la Traza/Hoja los pintan desde el evento; la materialización "
      "por Europe PMC corrió por search_europepmc_ledger con timeout ACOTADO (0.5 <= t <= WITT_WEB_BUDGET_S 30) en las 4 GETs de la ronda",
      _ev_payloads(_ev_wa, "stage.search.plan")[0].get("families_order_rule") == _sh.FAMILIES_ORDER_RULE_WEB_FIRST
      and _ev_payloads(_ev_wa, "stage.path_b")[0]["selection"]["pool_admission_rule"] == answer_pipeline.WEB_POOL_ADMISSION_RULE
      and _ev_payloads(_ev_wa, "stage.path_b")[0]["selection"]["tie_break_web_located"] == answer_pipeline.WEB_TIE_BREAK_RULE
      and len(_esp_wa.timeouts) >= 4 and all(t is not None and 0.5 <= t <= 30.0 for t in _esp_wa.timeouts[:4]),
      json.dumps({"plan_rule": _ev_payloads(_ev_wa, "stage.search.plan")[0].get("families_order_rule"),
                  "sel": _ev_payloads(_ev_wa, "stage.path_b")[0]["selection"], "timeouts": _esp_wa.timeouts[:4]}))
_web_row_sl = next(s for rd in _sl_a["rounds"] for s in rd["sources"] if s["family"] == "web")
_frozen_wo_wl = json.dumps({k: v for k, v in _rec_wa.items() if k != "web_locator"}, ensure_ascii=False, default=str)
check("ADR-0084 (G.2, lectura estricta) las URLs viven SÓLO en frozen.web_locator: la fila web de frozen.search_ledger.rounds[].sources[] NO lleva el "
      "ledger anidado `web_locator` (podado al congelar; web_locator_frozen_at lo declara; el bundle_json conserva el bloque íntegro) y el frozen "
      "SIN la llave web_locator no contiene NINGUNA URL hallada ni title_web; la fila web SÍ lleva provider/n_queries/n_located/n_materialized/"
      "n_unresolved/cost_usd_projected/quota_state (C.7)",
      "web_locator" not in _web_row_sl and _web_row_sl.get("web_locator_frozen_at") == "frozen.web_locator"
      and not _urls_in84(_frozen_wo_wl) and "WEB TITLE" not in _frozen_wo_wl
      and _web_row_sl["provider"] == "brave" and _web_row_sl["n_queries"] == 1 and _web_row_sl["n_located"] == 5
      and _web_row_sl["n_materialized"] == 3 and _web_row_sl["n_unresolved"] == 1 and _web_row_sl["quota_state"] == "under-cap"
      and "web_locator" in next(s for rd in json.loads(_row_wa["bundle_json"])["path_b"]["search_ledger"]["rounds"] for s in rd["sources"]
                                if s["family"] == "web"),
      json.dumps({"urls_outside": _urls_in84(_frozen_wo_wl), "row_keys": sorted(_web_row_sl)[:40]}))
_after_a = _rec_wa["council"]["coverage"]["after_search"]
_by_req_a = {b["requirement_id"]: b for b in _after_a["by_requirement"]}
check("ADR-0084 (F.4) coverage_after_search recibió el ledger web (web_locator=): by_requirement[req web].web_locator {n_queries 1, n_results 6, "
      "n_located 5, n_materialized 2 (materialized-same-round admitidos… W6: feed_state), n_unresolved 1}, ausente en los demás requisitos; "
      "web_locator_source 'caller (web_locator=)'; el requisito web queda 'retrieved-for' (≥ 1 candidato admitido con su requirement_id)",
      _by_req_a[_c_rid84["web"]].get("web_locator", {}).get("n_queries") == 1 and _by_req_a[_c_rid84["web"]]["web_locator"]["n_results"] == 6
      and _by_req_a[_c_rid84["web"]]["web_locator"]["n_located"] == 5 and _by_req_a[_c_rid84["web"]]["web_locator"]["n_unresolved"] == 1
      and _by_req_a[_c_rid84["web"]]["web_locator"]["n_materialized"] in (2, 3)
      and all("web_locator" not in b for rid_, b in _by_req_a.items() if rid_ != _c_rid84["web"])
      and _after_a.get("web_locator_source") == "caller (web_locator=)"
      and _by_req_a[_c_rid84["web"]]["state"] == "retrieved-for",
      json.dumps({"web": _by_req_a[_c_rid84["web"]].get("web_locator"), "state": _by_req_a[_c_rid84["web"]]["state"],
                  "source": _after_a.get("web_locator_source")}))
_tc_a = runs_mod.build_thread_context(db.get_run(_rid_wa), [], _dt.datetime(2026, 9, 16, tzinfo=_dt.timezone.utc))
_tc_json_a = json.dumps(_tc_a, ensure_ascii=False, default=str)
check("ADR-0084 (Context 3) el snapshot thread_context de un HIJO de esta corrida (build_thread_context sobre su fila) transporta los 2 strings de "
      "CONTEO en previous_answer.gap_flags y NINGUNA URL hallada, 'WEB TITLE', title_web ni canonical_url (el ledger no viaja al hijo)",
      _tc_a["snapshot"] is not None and _gf_web_a[0] in _tc_a["snapshot"]["previous_answer"]["gap_flags"]
      and _no_web_text84(_tc_json_a) and "title_web" not in _tc_json_a and "canonical_url" not in _tc_json_a,
      json.dumps({"urls": _urls_in84(_tc_json_a), "n_gap": len(_tc_a["snapshot"]["previous_answer"]["gap_flags"])}))
check("ADR-0084 (C.5 ii/iii, encadenado en la MISMA ronda) el DOI 10.1000/web666 y el curie ZFIN:ZDB-GENE-980526-558 localizados por la web llegaron a "
      "ctx (fed_ctx ['ctx:dois'] / fed_to 'ctx:curies') — la web corrió PRIMERA; el spy de Europe PMC recibió idents SÓLO en forma EPMC "
      "(PMID:<n> | DOI:<doi>) y 4 en la ronda (333, 666, 111 y el notfound)",
      _loc_a["10.1000/web666"].get("fed_ctx") == ["ctx:dois"] and _loc_a["ZFIN:ZDB-GENE-980526-558"]["fed_to"] == "ctx:curies"
      and all(_wl84.EPMC_IDENT_RE.match(i) for i in _esp_wa.calls[:4])
      and set(_esp_wa.calls[:4]) == {"PMID:33333333", "DOI:10.1000/web666", "PMID:11111111", "DOI:10.1000/notfound84"},
      json.dumps(_esp_wa.calls[:6]))

# --- (b) cita FABRICADA a una URL → pass2 INADMISIBLE por web_text_not_cited (id-is-url) -----------------------------------------------
_CIT_URL84 = [{"kind": "other", "id": "https://example.org/wt1a-blog"}, {"kind": "di-record", "id": "CORPUS-2026-0001"}]
_rid_wb, _rec_wb, _ev_wb, _row_wb, _net_wb, _esp_wb = _run84("ADR-0084 b: fabricated URL citation", "plan-84-b",
                                                              synth=_mk_synth84(_ANS84, _CIT_URL84))
_dc_wb = _rec_wb["deterministic_checks"]["web_locator"]
check("ADR-0084 (E.1) una cita fabricada con id URL ('https://example.org/wt1a-blog', kind other) → web_text_not_cited ok False (why 'id-is-url') → "
      "pass2 INADMISIBLE con reason 'hard predicate failed: web_text_not_cited'; la URL fabricada NO está en el ledger (ledger_index None); "
      "deterministic_checks.web_locator.state 'checked'",
      _dc_wb["state"] == "checked" and _dc_wb["web_text_not_cited"]["ok"] is False
      and _dc_wb["web_text_not_cited"]["offenders"][0]["why"] == "id-is-url"
      and _rec_wb["deterministic_checks"]["admissible"] is False
      and "hard predicate failed: web_text_not_cited" in _rec_wb["deterministic_checks"]["reasons"],
      json.dumps({"ok": _dc_wb["web_text_not_cited"]["ok"], "off": _dc_wb["web_text_not_cited"]["offenders"][:1],
                  "reasons": _rec_wb["deterministic_checks"]["reasons"]}, default=str)[:400])

# --- (c) KILL-SWITCH explícito CON directiva web y llave presente: excluida con el literal de 7d9ce15, 0 stage.web.*, 3 excepciones ---------
_rid_wc, _rec_wc, _ev_wc, _row_wc, _net_wc, _esp_wc = _run84("ADR-0084 c: kill-switch with web directive", "plan-84-c",
                                                              env={"WITT_WEB_LOCATOR": "off"})
_wl_c = _rec_wc["web_locator"]
_excl_c = _rec_wc["council"]["directives_excluded"]
check("ADR-0084 (L) KILL-SWITCH WITT_WEB_LOCATOR=off CON llave y must web sin cubrir: la directiva web se EXCLUYE al compilar con el literal EXACTO "
      "de 7d9ce15 'unsatisfiable-by-harness (tool-unavailable (ADR-0084))' (harness_state_recomputed True: el plan la vio satisfiable), el plan "
      "NO trae web, CERO stage.web.* y CERO GETs; frozen.web_locator == EXACTAMENTE {state 'kill-switch WITT_WEB_LOCATOR=off', provider 'off', "
      "provider_source 'env:WITT_WEB_LOCATOR', kill_switch {WITT_WEB_LOCATOR 'off', enabled False, source, declared_exceptions [3]}, "
      "state_vocabulary, rule}; deterministic_checks.web_locator == {state}; agents_invoked SIN fila web; token_usage SIN web_locator; "
      "citations SIN located_via; epistemic web_n_located null",
      len(_excl_c) == 1 and _excl_c[0]["family"] == "web" and _excl_c[0]["reason"] == _sh.WEB_UNSATISFIABLE_LITERAL
      == "unsatisfiable-by-harness (tool-unavailable (ADR-0084))" and _excl_c[0].get("harness_state_recomputed") is True
      and "web" not in _rec_wc["search_ledger"]["plan"]["families"]
      and not any(t.startswith("stage.web.") for t in _ev_types(_ev_wc)) and len(_net_wc.calls) == 0
      and set(_wl_c) == set(runs_mod.WEB_FROZEN_KILL_SWITCH_KEYS)
      and _wl_c["state"] == "kill-switch WITT_WEB_LOCATOR=off" and _wl_c["provider"] == "off"
      and _wl_c["provider_source"] == "env:WITT_WEB_LOCATOR"
      and _wl_c["kill_switch"] == {"WITT_WEB_LOCATOR": "off", "enabled": False, "source": "env:WITT_WEB_LOCATOR",
                                   "declared_exceptions": ["render_contract_version", "web_locator", "deterministic_checks.web_locator"]}
      and _rec_wc["deterministic_checks"]["web_locator"] == {"state": "kill-switch WITT_WEB_LOCATOR=off"}
      and not any(a["agent"] == runs_mod.WEB_LOCATOR_AGENT_ROW for a in _rec_wc["agents_invoked"])
      and "web_locator" not in _rec_wc["token_usage"] and "estimated_cost_usd_total_projected" not in _rec_wc["token_usage"]
      and all("located_via" not in c for c in _rec_wc["citations"]) and "n_located_via_web" not in _rec_wc["citations_support_summary"]
      and app.get_run(_rid_wc, authorization=AUTH)["epistemic_summary"]["web_n_located"] is None
      and app.get_run(_rid_wc, authorization=AUTH)["epistemic_summary"]["web_locator_state"] == "kill-switch WITT_WEB_LOCATOR=off",
      json.dumps({"wl": _wl_c, "excl": _excl_c}, default=str)[:600])

# --- (d/e) M.1 byte a byte: el MISMO fixture SIN directiva web (string sin cubrir), ON vs OFF ------------------------------------------------
_ADDITIVE_113_KEYS = {"located_via", "n_located_via_web", "families_order_rule", "pool_admission_rule", "tie_break_web_located",
                      "web_locator_usd_projected", "estimated_cost_usd_total_projected", "total_class",
                      "web_locator_state", "web_n_located", "web_n_unresolved", "harness_state_at_plan", "harness_state_at_compile",
                      "harness_state_recomputed"}


def _strip84(rec):
    """El registro SIN las llaves aditivas 1.13 ni las de identidad — para medir que el kill-switch no cambia NADA más."""
    r = json.loads(json.dumps(rec))
    for k in _IDENTITY_KEYS83 + ("web_locator",):
        r.pop(k, None)
    _drop_key83(r, "thread_id")
    r["deterministic_checks"].pop("web_locator", None)
    r["agents_invoked"] = [a for a in r["agents_invoked"] if a["agent"] != runs_mod.WEB_LOCATOR_AGENT_ROW]
    for k in _ADDITIVE_113_KEYS:
        _drop_key83(r, k)
    for k in ("queue_wait_s", "stagger_wait_s", "elapsed_s", "cache_dir"):   # reloj (consejo fake, rondas) y caché por corrida: identidad, no fuga
        _drop_key83(r, k)
    return r


_rid_wd, _rec_wd, _ev_wd, _row_wd, _net_wd, _esp_wd = _run84("ADR-0084 d: no web directive ON", "plan-84-de", uncovered=("string",),
                                                              cj=_c_json84(_C_LEDGER84, "plan-84-de"))
_rid_we, _rec_we, _ev_we, _row_we, _net_we, _esp_we = _run84("ADR-0084 d: no web directive ON", "plan-84-de", uncovered=("string",),
                                                              cj=_c_json84(_C_LEDGER84, "plan-84-de"), env={"WITT_WEB_LOCATOR": "off"})
_diff_de = _diff83(_strip84(_rec_wd), _strip84(_rec_we))
check("ADR-0084 (L, M.1) KILL-SWITCH byte a byte contra la corrida ENCENDIDA del MISMO fixture SIN directiva web (string sin cubrir, misma "
      "pregunta): quitadas las llaves ADITIVAS 1.13 (web_locator, deterministic_checks.web_locator, fila web de agents, citations[].located_via, "
      "n_located_via_web, token_usage.web_locator/total, epistemic web_*, families_order_rule, pool_admission_rule/tie_break, recomputo del "
      "consejo) y las de identidad de corrida, los dos registros son IDÉNTICOS (json sort_keys, keyset Y valores) — cualquier otra diferencia "
      "falla listando el path; ON: web_locator.state 'not-requested (no web directive)' y deterministic_checks.web_locator 'no-web-items' con 4 "
      "bloques; OFF: las 3 excepciones",
      _diff_de == set() and _rec_wd["web_locator"]["state"] == "not-requested (no web directive)"
      and _rec_wd["deterministic_checks"]["web_locator"]["state"] == "no-web-items"
      and set(_vo.WEB_PREDICATES) <= set(_rec_wd["deterministic_checks"]["web_locator"])
      and _rec_wd["deterministic_checks"]["web_locator"]["conjunction"] == []
      and _rec_we["web_locator"]["state"] == "kill-switch WITT_WEB_LOCATOR=off"
      and _rec_we["deterministic_checks"]["web_locator"] == {"state": "kill-switch WITT_WEB_LOCATOR=off"}
      and _rec_wd["render_contract_version"] == _rec_we["render_contract_version"] == "1.13"
      and len(_net_wd.calls) == 0 and len(_net_we.calls) == 0,
      json.dumps(sorted(_diff_de))[:600])
_RULE_DIRECTIVES_112 = ("one directive per KEPT requirement with coverage_final ∈ {uncovered, partial, not-judged} and harness_state "
                        "satisfiable; family/query/entities come from the REQUIREMENT (never from optional prose); a valid vote's "
                        "search_directive only refines query_en/entities (refined_by_members); dedup by (family, requirement_id); order must > "
                        "should, requirement_id asc")
_RULE_AFTER_112 = ("retrieved-for = at least one item ADMITTED by the harness carries this requirement_id in directive_requirement_ids "
                   "(structural MEASUREMENT, not a judgment); still-uncovered = a directive was compiled but nothing admitted for it; "
                   "not-searched = no directive (unsatisfiable, discarded or no search); covered-pre = coverage_final ∈ {covered, "
                   "covered-by-attestation} before the search")
check("ADR-0084 (L, corrector) los literales COMPARTIDOS del consejo que viajan al frozen son los de 1.12 @ 7d9ce15 BYTE A BYTE en ON y en OFF "
      "(council.directives_rule, council.coverage.after_search.rule): la ampliación web vive en llaves propias (availability_rule SÓLO con "
      "recomputo — presente en la corrida c bajo off con directiva web y AUSENTE en d/e —, web_locator_rule SÓLO con ledger web)",
      _rec_wd["council"]["directives_rule"] == _rec_we["council"]["directives_rule"] == _RULE_DIRECTIVES_112
      and _rec_wd["council"]["coverage"]["after_search"]["rule"] == _rec_we["council"]["coverage"]["after_search"]["rule"] == _RULE_AFTER_112
      and "directives_availability_rule" not in _rec_wd["council"] and "directives_availability_rule" not in _rec_we["council"]
      and _rec_wc["council"].get("directives_availability_rule") == _council.DIRECTIVES_AVAILABILITY_RULE
      and "web_locator_rule" not in _rec_wd["council"]["coverage"]["after_search"]
      and _rec_wa["council"]["coverage"]["after_search"].get("web_locator_rule") == _council.WEB_LOCATOR_COVERAGE_RULE,
      json.dumps({"d": _rec_wd["council"]["directives_rule"][:60], "c_avail": _rec_wc["council"].get("directives_availability_rule", "")[:60]}))
_ai_d = {a["agent"]: a for a in _rec_wd["agents_invoked"]}
check("ADR-0084 (G.9/G.8) ON sin directiva web: agents_invoked fila web 'not-applicable (not-requested (no web directive))'; epistemic "
      "web_locator_state 'not-requested (no web directive)', web_n_located null (no midió); token_usage SIN web_locator (la familia no corrió); "
      "citations[].located_via null en todas (localizador disponible, nada web)",
      _ai_d[runs_mod.WEB_LOCATOR_AGENT_ROW]["status"] == "not-applicable (not-requested (no web directive))"
      and app.get_run(_rid_wd, authorization=AUTH)["epistemic_summary"]["web_locator_state"] == "not-requested (no web directive)"
      and app.get_run(_rid_wd, authorization=AUTH)["epistemic_summary"]["web_n_located"] is None
      and "web_locator" not in _rec_wd["token_usage"]
      and all(c.get("located_via") is None and "located_via" in c for c in _rec_wd["citations"])
      and _rec_wd["citations_support_summary"]["n_located_via_web"] == 0,
      json.dumps(_ai_d.get(runs_mod.WEB_LOCATOR_AGENT_ROW)))

# --- (f) brave EXPLÍCITO sin llave → literal con causa; (g) competente → 'not-requested (no search round)' ----------------------------------
_rid_wf, _rec_wf, _ev_wf, _row_wf, _net_wf, _esp_wf = _run84("ADR-0084 f: brave without key", "plan-84-f", env={"BRAVE_API_KEY": ""})
_wl_f = _rec_wf["web_locator"]
check("ADR-0084 (B.3/G.2) WITT_WEB_LOCATOR=brave SIN llave: la directiva web se excluye con 'unsatisfiable-by-harness (tool-unavailable (ADR-0084: "
      "BRAVE_API_KEY unset))' (prefijo ya glosado, literal con CAUSA), frozen.web_locator.state 'tool-unavailable (ADR-0084: BRAVE_API_KEY unset)' "
      "(la causa viaja aquí), provider 'brave' env:WITT_WEB_LOCATOR, provider_available False, SIN contadores (no midió: nada de n_results/n_located), "
      "deterministic_checks.web_locator == {state 'tool-unavailable (ADR-0084: BRAVE_API_KEY unset)'}, agents_invoked fila 'tool-unavailable', "
      "CERO GETs",
      _rec_wf["council"]["directives_excluded"][0]["reason"] == "unsatisfiable-by-harness (tool-unavailable (ADR-0084: BRAVE_API_KEY unset))"
      and _wl_f["state"] == "tool-unavailable (ADR-0084: BRAVE_API_KEY unset)" and _wl_f["provider"] == "brave"
      and _wl_f["provider_source"] == "env:WITT_WEB_LOCATOR" and _wl_f["provider_available"] is False
      and "n_results" not in _wl_f and "n_located" not in _wl_f and "n_materialized" not in _wl_f
      and _rec_wf["deterministic_checks"]["web_locator"] == {"state": "tool-unavailable (ADR-0084: BRAVE_API_KEY unset)"}
      and next(a for a in _rec_wf["agents_invoked"] if a["agent"] == runs_mod.WEB_LOCATOR_AGENT_ROW)["status"] == "tool-unavailable"
      and len(_net_wf.calls) == 0 and _wl84.web_state_in_vocabulary(_wl_f["state"]),
      json.dumps({k: _wl_f.get(k) for k in ("state", "state_detail", "provider", "provider_available")}))
_rid_wg, _rec_wg, _ev_wg, _row_wg, _net_wg, _esp_wg = _run84("ADR-0084 g: competent run", "plan-84-g", uncovered=())
_wl_g = _rec_wg["web_locator"]
check("ADR-0084 (G.2) corrida COMPETENTE (0 must sin cubrir, sin Ruta B): frozen.web_locator.state 'not-requested (no search round)', measured False, "
      "queries/located/unresolved [], SIN contadores, provider 'brave' disponible, encabezado (versiones, resolver_rules 12, text_policy); "
      "deterministic_checks.web_locator 'no-web-items'; agents fila 'not-applicable (not-requested (no search round))'; token_usage SIN web_locator; "
      "epistemic web_n_located null",
      _rec_wg["competence"]["competent"] is True and _wl_g["state"] == "not-requested (no search round)" and _wl_g["measured"] is False
      and _wl_g["queries"] == [] and _wl_g["located"] == [] and _wl_g["unresolved"] == [] and "n_results" not in _wl_g
      and _wl_g["provider"] == "brave" and _wl_g["provider_available"] is True and len(_wl_g["resolver_rules"]) == 12
      and _wl_g["module_version"] == "wl-1" and _wl_g["text_policy"] == _wl84.TEXT_POLICY
      and _rec_wg["deterministic_checks"]["web_locator"]["state"] == "no-web-items"
      and next(a for a in _rec_wg["agents_invoked"] if a["agent"] == runs_mod.WEB_LOCATOR_AGENT_ROW)["status"]
      == "not-applicable (not-requested (no search round))"
      and "web_locator" not in _rec_wg["token_usage"]
      and app.get_run(_rid_wg, authorization=AUTH)["epistemic_summary"]["web_n_located"] is None,
      json.dumps({k: _wl_g.get(k) for k in ("state", "state_detail", "measured", "provider")}))

# --- (h) alterno Anthropic web_search con _post_json FALSO (fixture SINTÉTICO): tokens MEDIDOS del despachador + USD 10/1k -------------------
_rid_wh, _rec_wh, _ev_wh, _row_wh, _net_wh, _esp_wh = _run84("ADR-0084 h: anthropic alternate", "plan-84-h",
                                                              env={"WITT_WEB_LOCATOR": "anthropic", "ANTHROPIC_API_KEY": "fake-anthropic-key-adr84",
                                                                   "BRAVE_API_KEY": None},
                                                              anthropic_fx=_ANTH_FX84["response"],
                                                              epmc={"PMID:15982647": _rec84("15982647", title="EPMC 15982647")})
_wl_h = _rec_wh["web_locator"]
_tu_h = _rec_wh["token_usage"]
_disp_model = _ANTH_FX84["response"]["model"]
check("ADR-0084 (I/G.7) alterno Anthropic (WITT_WEB_LOCATOR=anthropic, _post_json falso con el fixture SINTÉTICO): frozen.web_locator provider "
      "'anthropic', 1 consulta, n_results 5 (4 URLs de web_search_tool_result + 1 de citations[], dedup), cost {price_usd_per_1k 10.0, n_queries_billable 1 (web_search_requests), "
      "usd_projected 0.01, tokens {in 1480, out 92, class 'medición'}}; token_usage.web_locator.tokens medidos; by_stage.search {in 1480, out 92, model "
      "<despachador>, state 'measured (anthropic web_search dispatcher)'}; by_model[<despachador>] los suma; by_stage_sum_matches_by_model True; "
      "CERO GETs a Brave; la PROSA del despachador (sentinela del fixture) NO persiste ni en frozen, ni en bundle_json, ni en eventos",
      _wl_h["provider"] == "anthropic" and _wl_h["n_queries"] == 1 and _wl_h["n_results"] == 5
      and _wl_h["cost"]["price_usd_per_1k"] == 10.0 and _wl_h["cost"]["n_queries_billable"] == 1 and _wl_h["cost"]["usd_projected"] == 0.01
      and _wl_h["cost"]["tokens"] == {"in": 1480, "out": 92, "class": "medición", "model": _disp_model}
      and _tu_h["web_locator"]["tokens"]["in"] == 1480 and _tu_h["by_stage"]["search"]["in"] == 1480 and _tu_h["by_stage"]["search"]["out"] == 92
      and _tu_h["by_stage"]["search"]["model"] == _disp_model and _tu_h["by_stage"]["search"]["state"] == runs_mod.WEB_ANTHROPIC_SEARCH_STATE
      and _tu_h["by_model"].get(_disp_model, {}).get("in", 0) >= 1480 and _tu_h["by_stage_sum_matches_by_model"] is True
      and len(_net_wh.calls) == 0
      and "SYNTHETIC_MODEL_PROSE_MUST_NEVER_PERSIST" not in json.dumps(_rec_wh)
      and "SYNTHETIC_MODEL_PROSE_MUST_NEVER_PERSIST" not in _row_wh["bundle_json"]
      and "SYNTHETIC_MODEL_PROSE_MUST_NEVER_PERSIST" not in json.dumps([e["payload"] for e in _ev_wh], default=str),
      json.dumps({"cost": _wl_h["cost"], "search": _tu_h["by_stage"]["search"], "state": _wl_h["state"]}, default=str)[:500])
_papers_wh = json.loads(_row_wh["bundle_json"])["path_b"]["papers"]
_p_wh = next(p for p in _papers_wh if p.get("source_family") == "web")
_dc_wh = _rec_wh["deterministic_checks"]
check("ADR-0084 (D.3 <-> E.3, corrector) el paper web-localizado SELECCIONADO cuyo fetch_external NO lo entregó (fetched.found False: timeout "
      "transitorio) queda SIN PASAJE — abstract None, text_excerpt None, text_provenance 'none', text_withheld_reason 'web-located-not-fetched "
      "(ADR-0084 D.3)' — y la respuesta (que no lo cita) es ADMISIBLE: web_items_native_only ok True (0 offenders) — antes E.3 disparaba "
      "'text-without-fetch' sobre el abstract del registro EPMC y volvía inadmisible TODA la pass2 por un fallo de red",
      _p_wh["fetched"]["found"] is False and _p_wh["abstract"] is None and _p_wh["text_excerpt"] is None
      and _p_wh["text_provenance"] == "none" and _p_wh["text_withheld_reason"] == answer_pipeline.WEB_TEXT_WITHHELD_REASON
      and _dc_wh["admissible"] is True and _dc_wh["web_locator"]["web_items_native_only"]["ok"] is True
      and _dc_wh["web_locator"]["web_items_native_only"]["n_offenders"] == 0 and _dc_wh["web_locator"]["state"] == "checked",
      json.dumps({"fetched": _p_wh["fetched"], "prov": _p_wh["text_provenance"], "adm": _dc_wh["admissible"], "reasons": _dc_wh["reasons"]}, default=str)[:400])
_q_wh = _wl_h["queries"][0]
check("ADR-0084 (I, corrector) el alterno DECLARA en el frozen lo que hace: queries[0] {tool_type 'web_search_20250305' (vocabulario CERRADO "
      "web_locator.ANTHROPIC_TOOL_TYPES), provider_property == ANTHROPIC_READS_WEB_TEXT (el modelo LEE texto web), n_text_blocks_discarded 1, "
      "request_shape {has_tool_choice False, has_allowed_callers False, has_blocked_domains False}, query_sent_matches_directive False, stop_reason}; "
      "cost.provider_detail {tool_type, tool_type_source 'default', tool_types_allowed ['web_search_20250305'], reads_web_text True, property} "
      "también en token_usage.web_locator",
      _q_wh["tool_type"] == "web_search_20250305" and _wl84.ANTHROPIC_TOOL_TYPES == ("web_search_20250305",)
      and _q_wh["provider_property"] == _wl84.ANTHROPIC_READS_WEB_TEXT and _q_wh["n_text_blocks_discarded"] == 1
      and _q_wh["request_shape"]["has_tool_choice"] is False and _q_wh["request_shape"]["has_allowed_callers"] is False
      and _q_wh["request_shape"]["has_blocked_domains"] is False and _q_wh["query_sent_matches_directive"] is False
      and "stop_reason" in _q_wh
      and _wl_h["cost"]["provider_detail"] == {"tool_type": "web_search_20250305", "tool_type_source": "default",
                                              "tool_types_allowed": ["web_search_20250305"], "reads_web_text": True,
                                              "property": _wl84.ANTHROPIC_READS_WEB_TEXT}
      and _tu_h["web_locator"]["provider_detail"]["reads_web_text"] is True,
      json.dumps({k: _q_wh.get(k) for k in ("tool_type", "n_text_blocks_discarded", "request_shape", "stop_reason")}, default=str)
      + " " + json.dumps(_wl_h["cost"].get("provider_detail"), default=str)[:200])

# --- assert GLOBAL sobre la BD del gate: ninguna URL de fixture web fuera de frozen.web_locator ni en run_events --------------------------------
_leaks84 = []
with db.engine().begin() as _cx84:
    for _rid84, _fr84 in _cx84.execute(_sa_f8.text("SELECT run_id, frozen_record_json FROM runs WHERE frozen_record_json IS NOT NULL")).all():
        _d = json.loads(_fr84)
        _d.pop("web_locator", None)
        _s = json.dumps(_d, ensure_ascii=False)
        if _urls_in84(_s) or "WEB TITLE" in _s or WEB_TEXT84 in _s or FAKE_KEY84 in _s:
            _leaks84.append(("frozen", _rid84, _urls_in84(_s)[:2]))
    for _rid84, _seq84, _pl84 in _cx84.execute(_sa_f8.text("SELECT run_id, seq, payload_json FROM run_events WHERE payload_json IS NOT NULL")).all():
        if _urls_in84(_pl84 or "") or "WEB TITLE" in (_pl84 or "") or WEB_TEXT84 in (_pl84 or "") or FAKE_KEY84 in (_pl84 or ""):
            _leaks84.append(("event", _rid84, _seq84))
check("ADR-0084 assert GLOBAL sobre la BD del gate: NINGUNA URL de fixture web (Brave ni Anthropic), 'WEB TITLE', description ni la llave fake en "
      "ningún frozen_record_json fuera de la llave web_locator, ni en ningún payload de run_events (todas las corridas de todos los ADR)",
      _leaks84 == [], json.dumps(_leaks84[:5], default=str))
check("ADR-0084 los estados congelados están en los vocabularios CERRADOS: web_locator.state ∈ WEB_STATES (exactos | prefijos) en las 9 corridas; "
      "deterministic_checks.web_locator.state ∈ WEB_CHECK_STATES; quota.state ∈ QUOTA_STATES cuando existe",
      all(_wl84.web_state_in_vocabulary(r["web_locator"]["state"]) for r in (_rec_q1, _rec_q2, _rec_wa, _rec_wb, _rec_wc, _rec_wd, _rec_we, _rec_wf, _rec_wg, _rec_wh))
      and all(_vo.web_check_state_in_vocabulary(r["deterministic_checks"]["web_locator"]["state"])
              for r in (_rec_q1, _rec_q2, _rec_wa, _rec_wb, _rec_wc, _rec_wd, _rec_we, _rec_wf, _rec_wg, _rec_wh))
      and all(_wl84.quota_state_in_vocabulary(r["web_locator"]["quota"]["state"]) for r in (_rec_q1, _rec_q2, _rec_wa, _rec_wb, _rec_wh)),
      json.dumps([r["web_locator"]["state"] for r in (_rec_q1, _rec_q2, _rec_wa, _rec_wb, _rec_wc, _rec_wd, _rec_we, _rec_wf, _rec_wg, _rec_wh)]))
_sh._TOOL_CACHE.pop("web", None)


# --- cero red MEDIDO + mcp_cache intacto + restauración de costuras --------------------------------------------------
_mcp_after = _mcp_snapshot()
check("ADR-0080 (H) / ADR-0081 / ADR-0083 / ADR-0084 la sección corrió 100% OFFLINE — MEDIDO, no prometido: urllib.request.urlopen bloqueado y "
      "contado durante las 21 corridas de _run80 de ADR-0080 + las 6 de ADR-0081 + las de ADR-0082, ADR-0083 y ADR-0084 (0 llamadas), mcp_cache "
      "byte-idéntico antes/después (la caché por día de ZFIN neutralizada desde el gate; la caché de figuras vive en un TMP propio), "
      "las fakes Layer 0 se inyectaron en _TOOL_CACHE tras verificar que las tools reales resuelven",
      _NET_CALLS == [] and _mcp_before == _mcp_after,
      json.dumps({"net_calls": _NET_CALLS[:3], "mcp_changed": [x for x in _mcp_after if x not in _mcp_before][:3]}))
_urlreq.urlopen = _urlopen_real
_sh._monotonic = _time.monotonic
_sh._TOOL_CACHE.clear()
answer_pipeline._cache_zfin = _cache_zfin_real
answer_pipeline.fetch_paper.search_europepmc_ledger = _epmc_ledger_real
answer_pipeline.fetch_paper.fetch_external = _fetch_real2
answer_pipeline._WS_CACHE.pop(("pubmed_literature.py", "query_pubmed"), None)
answer_pipeline._WS_CACHE.pop(("zfin_zebrafish.py", "query_zfin"), None)
answer_pipeline.path_b = _path_b_stub

# ---- ADR-0076: al final de todo el gate, los números son únicos y consecutivos en la creación ---------
_lista = db.list_runs(limit=1000)
_nums = [r["run_no"] for r in _lista]
check("ADR-0076: todas las corridas del gate tienen número, sin repetidos, y la lista (created_at desc) los trae descendentes",
      all(isinstance(n, int) for n in _nums) and len(set(_nums)) == len(_nums)
      and _nums == sorted(_nums, reverse=True), f"run_no={_nums}")

npass = sum(CHECKS)
print("\n== %d/%d PASS ==" % (npass, len(CHECKS)))
sys.exit(0 if npass == len(CHECKS) else 1)

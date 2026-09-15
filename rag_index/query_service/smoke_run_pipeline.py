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
from lib import answer_pipeline, composite_auditor, rag_backend  # noqa: E402
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
check("TokenUsage: by_model medido + costo etiquetado PROJECTION + embeddings declarados (ADR-0080: sin plan hay "
      "pass1 + pass2 -> stub-synth 200/100; total 240/120)",
      tu["by_model"].get("stub-synth") == {"in": 200, "out": 100}
      and tu["by_model"].get("claude-opus-4-8") == {"in": 10, "out": 5}
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
      pl["plan_version"] == "3" and pl["data_landscape"]["class"] == "structural"
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
check("plan: el modelo elige NOMBRES; el gate y la componentizacion los resuelve la TABLA "
      "(causal-pruner=hard-rule sin componente; composite-auditor=componentizado)",
      ags["causal-pruner"]["gate"] == "hard-rule" and ags["causal-pruner"]["componentized"] is False
      and ags["causal-pruner"]["will_run"] == "skipped-ad-hoc"
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
runs_mod._default_planner_real = runs_mod._default_planner
runs_mod._default_planner = _fake_planner_ok
prv = app.create_plan(app.PlanBody(question="¿osr1 es suficiente para inducir el pronefros?",
                                   entities=["osr1"]), authorization=AUTH)
runs_mod._default_planner = runs_mod._default_planner_real
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
first_stage = next(t for t in tipos_p if t.startswith("stage."))
check("stage.plan es el PRIMER evento de etapa de la traza (el boceto M3 lo pinta primero)",
      first_stage == "stage.plan"
      and next(e for e in ev_p if e["type"] == "stage.plan")["payload"]["agents"]
          == ["causal-pruner", "hypothesis-generator", "composite-auditor"])
rec_p = app.get_frozen_record(rv_p["run_id"], authorization=AUTH)
check("el planner GASTA y su gasto entra al total (M8 cuadra) + aparte en plan_judgment: "
      "dejarlo fuera haria irreconciliable el consumo (misma disciplina que LOTE-01·A4)",
      rec_p["token_usage"]["plan_judgment"] is not None
      and rec_p["token_usage"]["plan_judgment"]["in"] == 400
      # el planner y el juez de la lente correctness son el MISMO modelo: agregar por modelo es
      # lo correcto (410 = 400 del plan + 10 del juez), y plan_judgment lo desglosa aparte
      and rec_p["token_usage"]["by_model"]["claude-opus-4-8"]["in"] == 410
      and rec_p["token_usage"]["input_tokens"] >= 400,
      f"plan_judgment={rec_p['token_usage']['plan_judgment']} by_model={rec_p['token_usage']['by_model']}")
check("una corrida SIN plan no inventa plan_judgment: null declarado",
      rec["token_usage"]["plan_judgment"] is None)
check("registro 1.4: el plan viaja CONGELADO + plan_question_matches_run=true",
      rec_p["plan_declared"] is True and rec_p["plan"]["judgment"]["state"] == "declared"
      and rec_p["plan_question_matches_run"] is True)
ai_p = {a["agent"]: a for a in rec_p["agents_invoked"]}
check("agents_invoked CON plan: los aplicables no-componentizados entran skipped-ad-hoc (literal §5 "
      "de la matriz) con la razon del planner + fila agregada not-applicable — y NO hay not-assessed",
      ai_p["causal-pruner"]["status"] == "skipped-ad-hoc"
      and "planner (§11)" in ai_p["causal-pruner"]["reason"]
      and any(a["status"] == "not-applicable" and "resto del catálogo" in a["agent"]
              for a in rec_p["agents_invoked"])
      and not any(a["status"] == "not-assessed" for a in rec_p["agents_invoked"]))
check("agents_invoked SIN plan (corridas previas de este gate): el hueco sigue not-assessed",
      any(a["status"] == "not-assessed" for a in rec["agents_invoked"])
      and rec["plan_declared"] is False and rec["plan"] is None)
check("matriz: derogaciones y suspensiones viajan en la tabla (html-report ADR-0046 · "
      "investor-relations ADR-0008)",
      "ADR-0046" in agent_matrix.AGENTS["html-report-emitter"]["note"]
      and "SUSPENDIDO" in agent_matrix.AGENTS["investor-relations-drafter"]["note"])
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
      and runs_mod.PRICES_PER_MTOK_USD["claude-sonnet-5"] == (2.0, 10.0)
      and runs_mod.PRICES_AS_OF == "2026-09",
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


check("ADR-0079/0080 contrato: runs.RENDER_CONTRACT_VERSION == '1.9' — 1.8 (ADR-0079) acompañó thread, thread_context, "
      "thread_parent_matches_run, precedent_citations, origin, episode_axes; 1.9 (ADR-0080) suma competence, search_ledger, "
      "citations[].support_state, citations_support_summary, deterministic_checks.{pass1_admissible, "
      "positive_claim_requires_citations, competence_gate}, token_usage.by_stage, epistemic_summary.{competent, "
      "n_search_rounds}; la webapp los tipa `?` — eso ES la paridad front<->back",
      runs_mod.RENDER_CONTRACT_VERSION == "1.9")   # el ÚNICO literal del contrato en todos los gates (los demás comparan contra runs_mod)
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
check("ADR-0080 (C/D) SEARCH_DISPATCH apunta a los archivos REALES de C3–C5 (+pubmed/zfin de hoy): los 12 módulos existen "
      "bajo .tooluniverse/tools y _load_tool resuelve EXACTAMENTE la función declarada (fn_resolved == fn, sin nota); "
      "'web' y 'tooluniverse' quedan tool-unavailable DECLARADOS (ADR-0084/0085); las 15 familias tienen gate/evidence_kind/"
      "label en vocabulario",
      all(w["file_exists"] and w["callable"] and w["fn_resolved"] == w["fn_declared"] and w["detail"] is None
          for w in _wiring.values())
      and _sh._load_tool("web") == (None, None, "tool-unavailable (ADR-0084)")
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
    sintetizador/panel inyectados bajo `env` (vars fijadas SOLO durante la corrida). Devuelve (run_id, frozen, events)."""
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
      "ADR-0051/0065) y SIN calibration_coverage (gating False por default); council_uncovered_must 'not-available (ADR-0082)' "
      "gating False; "
      "fb_meta.competence + trigger_vocabulary (runs.TRIGGER_VOCABULARY) + trigger_decided_by 'code (competence-gate)'; "
      "config con tau 0.5 (source 'caller' = runs.FALLBACK_CONF_TAU) y fb_meta.tau_source declarado",
      len(_comp_ev) == 1 and _comp_ev[0] == _rec_c["competence"]
      and _rec_c["competence"]["decided_by"] == "code" and _rec_c["competence"]["module_version"] == "cg-3" == _cg.MODULE_VERSION
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
      and _rec_c["competence"]["components"]["council_uncovered_must"] == {"value": None, "state": "not-available (ADR-0082)",
                                                                          "gating": False}
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
      and _rec_cc["competence"]["module_version"] == "cg-3"
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
check("ADR-0080 (A, corrector) WITT_CG_CALIBRATION_ORIGINS default 'production': db.calibration_coverage se llama con "
      "include_origins ['production'] (fuente 'default-unset:WITT_CG_CALIBRATION_ORIGINS' en el bloque) — las corridas de "
      "origen smoke cerradas de esta BD quedan CONTADAS FUERA (n 0 con filtro, n_closed_rated_total con filtro <= sin filtro); "
      "el lector CSV tolerante acepta 'all' como sin filtro declarado",
      _cal_ev_g.get("include_origins") == ["production"] if "include_origins" in _cal_ev_g else True
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
      "'supported' (su palabra se conserva en `supported`, no eleva); pertinent 'not-available (ADR-0082)' en ambas; "
      "citations_support_summary {n 2, by_state con los 5 peldaños, state 'checked', grounding_rows 2, ladder_rule}; forma BASE intacta",
      _cits_base(_rec_s["citations"]) == [{"n": 1, "kind": "di-chunk", "id": "CORPUS-2026-0003#c000", "note": ""},
                                          {"n": 2, "kind": "paper", "id": "PMID:99999999", "note": ""}]
      and _c1["resolved"] is True and _c1["passage_delivered"] is True and _c1["supported"] == "supported"
      and _c1["support_state"] == "supported" and _c1["pertinent"] == "not-available (ADR-0082)"
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
      "attempts [errored, ok] (jamás fabricado), n_valid 4, y su usage cuenta UNA vez (panel 40)",
      len(_judge_ev) == 5
      and [(p["reviewer"] is not None, p["lens"], p["attempt"], p["retries_judge"]) for p in _judge_ev if p["lens"] == "overclaim"]
      == [(True, "overclaim", 1, 0), (True, "overclaim", 2, 1)]
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
                    _rec_nh, _rec_cc, _rec_cd, _rec_di, _rec_ab, _rec_je, _rec_f))
      and all({"competent", "n_search_rounds"} <= set(app.get_run(rid, authorization=AUTH)["epistemic_summary"])
              for rid in (_rid_c, _rid_h, _rid_2, _rid_k))
      and all(r["deterministic_checks"]["pass"] in ("pass1", "pass2", "revision")
              for r in (_rec_c, _rec_h, _rec_2, _rec_1, _rec_b, _rec_k, _rec_kl, _rec_g, _rec_s, _rec_p, _rec_d, _rec_j))
      # corrector: 'confidence' vuelve al vocabulario SÓLO para competent null (kill-switch / not-applicable)
      and runs_mod.FALLBACK_TRIGGERS == ("structural", "competence", "confidence", None)
      and runs_mod.TRIGGER_LEGACY_CONFIDENCE == "confidence"
      and all(r["fallback"]["trigger"] != "confidence" or r["competence"]["competent"] is None
              for r in (_rec_c, _rec_h, _rec_2, _rec_1, _rec_b, _rec_k, _rec_kl, _rec_g, _rec_s, _rec_p, _rec_d, _rec_j,
                        _rec_nh, _rec_cc, _rec_cd, _rec_di, _rec_ab, _rec_je, _rec_f)))

# --- cero red MEDIDO + mcp_cache intacto + restauración de costuras --------------------------------------------------
_mcp_after = _mcp_snapshot()
check("ADR-0080 (H) la sección corrió 100% OFFLINE — MEDIDO, no prometido: urllib.request.urlopen bloqueado y contado durante "
      "20 corridas (0 llamadas), mcp_cache byte-idéntico antes/después (la caché por día de ZFIN neutralizada desde el gate), "
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

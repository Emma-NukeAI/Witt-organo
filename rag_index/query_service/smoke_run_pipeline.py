"""smoke_run_pipeline.py — gate determinista del bloque 3 (ADR-0049/0050).

Cubre: la reforma de la maquina de estados (DI_SUFFICIENT ya NO autoriza responder — auditoria en el
100% de las corridas), el composite_auditor invocable (agregacion worst-of, vocabulario homologado,
panel delgado NUNCA aprueba, jueces errados excluidos y registrados), record_audit con su PRIMER
llamador real, el modelo de corrida end-to-end (queued -> running -> awaiting_closure -> closed),
cancelacion como estado de primera clase, latido, y la bitacora UNICA (replay == traza viva).

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


# ---- stubs deterministas ----------------------------------------------------------------------------
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
answer_pipeline.path_b = lambda q, n=2, **kw: []
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
rec = app.get_frozen_record(RID, authorization=AUTH)
check("registro congelado persistido en backend: contrato + audit + store_at_retrieval + identidad",
      rec["render_contract_version"] == "1.5" and rec["audit"]["verdict"] == "APPROVE"
      and rec["question_matches_run"] is True and rec["decision_state"]["state"] == "AUDIT_APPROVED"
      and "store_version" in rec["store_at_retrieval"] and rec["bundle_identity"]["run_id"] == RID)
# --- bloque 4 (ADR-0051): confianza alta + DI suficiente -> SIN fallback, una sola pasada -----------
check("sin fallback: trigger=None, pass2=None, answer=pass1 (conf 0.8 >= tau 0.5)",
      rec["fallback"]["trigger"] is None and rec["confidence"]["pass1"] == 0.8
      and rec["confidence"]["pass2"] is None and rec["confidence"]["delta"] is None
      and rec["confidence"]["state"] == "value"
      and "stage.synthesize.pass2" not in types)
check("confidence_by_subclaim viaja al registro (asimetria declarada, no promediada)",
      rec["confidence"]["by_subclaim"] == {"marker-expression": 0.9, "functional-requirement": 0.3})
check("citas tipadas con serie numerica (letras reservadas a precedente)",
      rec["citations"] == [{"n": 1, "kind": "di-record", "id": "CORPUS-2026-0001", "note": ""}]
      and rec["answer"]["absence_kind"] == "not-applicable")
tu = rec["token_usage"]
check("TokenUsage: by_model medido + costo etiquetado PROJECTION + embeddings declarados",
      tu["by_model"].get("stub-synth") == {"in": 100, "out": 50}
      and tu["by_model"].get("claude-opus-4-8") == {"in": 10, "out": 5}
      and tu["input_tokens"] == 140 and tu["output_tokens"] == 70
      and "PROJECTION" in tu["cost_class"] and tu["estimated_cost_usd"] > 0
      and tu["embedding"]["total_tokens"] == 0,
      f"cost={tu['estimated_cost_usd']}")
view = app.get_run(RID, authorization=AUTH)
check("latido expuesto (heartbeat_age_s) y no-stale tras actividad",
      view["heartbeat_age_s"] is not None and view["heartbeat_stale"] is False)
check("LOTE-02·3: epistemic_summary derivado AL CONGELAR, visible en la vista (renglon rico de M6)",
      view["epistemic_summary"] == {"retrieval_mode": "semantic", "verdict": "APPROVE",
                                    "confidence_state": "value", "panel_n_valid": 4})

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
check("pass1 0.3 < tau 0.5 -> dispara Ruta B por CONFIANZA aunque lo estructural dijera suficiente",
      rec["fallback"]["trigger"] == "confidence"
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
check("confianza ausente (ni escalar ni subclaims): gate + 'absent-not-calibratable' declarado",
      rec["fallback"]["trigger"] == "confidence"
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
composite_auditor._anthropic_tool_call = _orig_tool_call
rv = app.create_run(app.RunBody(question="recovered conf run", entities=[]), authorization=AUTH)
claimed = db.claim_next_queued()
runs_mod.execute_run(claimed, synthesizer=_mk_synth(
    {"pass1": 0.15, "pass2": 0.75},
    extra={"confidence_source": "recovered-from-malformed-tool-call"}),
    panel_caller=_stub_caller_factory(ALL_A))
rec = app.get_frozen_record(rv["run_id"], authorization=AUTH)
check("procedencia en el registro: fb_meta.pass1_confidence_source='recovered-…' + gate disparado (0.15<tau)",
      rec["fallback"]["trigger"] == "confidence"
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
check("build_external_query: entidades (EN) primero; la fuente se declara",
      q_sent == "osr1 pax2a" and q_src == "entities"
      and answer_pipeline.build_external_query("solo pregunta", [])[1] == "question-verbatim")
rv = app.create_run(app.RunBody(question="pregunta en español sin cobertura",
                                entities=["osr1", "pax2a"]), authorization=AUTH)
claimed = db.claim_next_queued()
runs_mod.execute_run(claimed, synthesizer=_mk_synth(
    {"pass1": 0.2, "pass2": 0.7},
    extra={"search_query_en": "osr1 pax2a zebrafish pronephros induction"}),
    panel_caller=_stub_caller_factory(ALL_A))
ev_types = app.get_events(rv["run_id"], after=0, authorization=AUTH)["events"]
pb = next(e for e in ev_types if e["type"] == "stage.path_b")
check("conf-gated: la query del sintetizador (EN) se usa y queda AUDITABLE en el evento",
      pb["payload"]["query_sent"] == "osr1 pax2a zebrafish pronephros induction"
      and pb["payload"]["query_source"] == "synthesizer"
      and "n_results_by_source" in pb["payload"])

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

def _fake_zfin(symbol, anatomy=None, limit=50):
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

check("n_results_by_source: por fuente, y AMBAS fuentes de literatura SIEMPRE presentes "
      "(0 explicito != fuente ausente)",
      answer_pipeline.n_results_by_source([{"source": "zfin"}, {"source": "zfin"}])
      == {"zfin": 2, "europepmc": 0, "pubmed": 0})

# ---- ADR-0062 / tapon 1B: PubMed en Layer 0 con dedup por PMID -----------------------------------------
def _fake_pubmed(query, limit=8):
    return {"status": "success", "data": {"query": query, "n_found_total": 9, "records": [
        {"pmid": "19666820", "title": "RA responsive element controls wt1a", "year": "2009",
         "journal": "Development"},
        {"pmid": "42153456", "title": "ya vino por europepmc", "year": "2025", "journal": "X"},
    ]}}
answer_pipeline._WS_CACHE[("pubmed_literature.py", "query_pubmed")] = _fake_pubmed
_fetch_real = answer_pipeline.fetch_paper.fetch_external
answer_pipeline.fetch_paper.fetch_external = lambda ident, want_full_text=True: {"found": True}
items, row = answer_pipeline._search_pubmed("wt1a zebrafish", 5, {"PMID:42153456"})
answer_pipeline.fetch_paper.fetch_external = _fetch_real
check("pubmed: dedup por PMID contra europepmc DECLARADO — el duplicado ni entra dos veces ni se "
      "tira callado (EPMC indexa PubMed: sin esto el sintetizador cuenta doble)",
      len(items) == 1 and items[0]["evidence_id"] == "PMID:19666820"
      and items[0]["source"] == "pubmed"
      and row["status"] == "success" and row["n_new"] == 1
      and row["duplicates_of_europepmc"] == ["PMID:42153456"])
answer_pipeline._WS_CACHE[("pubmed_literature.py", "query_pubmed")] =     lambda query, limit=8: {"status": "error", "error": "HTTPError: 500"}
items_e, row_e = answer_pipeline._search_pubmed("q", 5, set())
check("pubmed: la busqueda FALLIDA se declara error — jamas se ve igual que 'no hay resultados'",
      items_e == [] and row_e["status"] == "error" and "500" in row_e["detail"])
answer_pipeline._WS_CACHE[("pubmed_literature.py", "query_pubmed")] = None
check("pubmed: tool ausente -> tool-unavailable declarado, la corrida no truena (§6 no-hang)",
      answer_pipeline._search_pubmed("q", 5, set())[1]["status"] == "tool-unavailable")
answer_pipeline._WS_CACHE.pop(("pubmed_literature.py", "query_pubmed"), None)
pl_ev = answer_pipeline.path_b_event_payload(
    {"papers": [], "query_sent": "q", "query_source": "entities",
     "n_results_by_source": {"europepmc": 2, "pubmed": 1, "zfin": 0},
     "pubmed_searched": {"status": "success", "n_found_total": 9, "n_new": 1,
                         "duplicates_of_europepmc": ["PMID:1"], "ranking": "x"}})
def _boom_fetch(ident, want_full_text=True):
    raise TimeoutError("read timed out")
_fetch_real2 = answer_pipeline.fetch_paper.fetch_external
answer_pipeline.fetch_paper.fetch_external = _boom_fetch
answer_pipeline._WS_CACHE[("pubmed_literature.py", "query_pubmed")] = _fake_pubmed
items_t, row_t = answer_pipeline._search_pubmed("q", 5, set())
answer_pipeline.fetch_paper.fetch_external = _fetch_real2
answer_pipeline._WS_CACHE.pop(("pubmed_literature.py", "query_pubmed"), None)
check("un timeout bajando UN paper degrada ESE item (found=false + fetch_error declarado) — "
      "jamas tumba path_b (§6 no-hang; lo destapo la verificacion en vivo)",
      len(items_t) == 2 and all(i["fetched"]["found"] is False for i in items_t)
      and "TimeoutError" in items_t[0]["fetched"]["fetch_error"])

check("el evento stage.path_b lleva el resumen de pubmed (dedup incluido) — un solo log",
      pl_ev["pubmed_searched"]["n_new"] == 1
      and pl_ev["pubmed_searched"]["duplicates_of_europepmc"] == ["PMID:1"])

# path_b sigue stubbeado ([]) -> path_b_bundle es offline y el bloque queda completo y declarado
blk = answer_pipeline.path_b_bundle("pregunta", entities=["osr1"], triggered_by=["motivo"])
check("path_b_bundle: UN constructor del bloque, con fuentes pedidas + contadores + query declarada",
      blk["triggered"] is True and blk["query_sent"] == "osr1" and blk["query_source"] == "entities"
      and blk["sources_requested"] == list(answer_pipeline.PATH_B_SOURCES)
      and blk["n_results_by_source"] == {"europepmc": 0, "pubmed": 0} and blk["triggered_by"] == ["motivo"])
pl = answer_pipeline.path_b_event_payload(
    {"papers": [], "query_sent": "q", "query_source": "entities",
     "n_results_by_source": {"europepmc": 0, "zfin": 1},
     "zfin_searched": [{"symbol": "a", "status": "success"}, {"symbol": "b", "status": "no-match"}]},
    trigger="confidence")
check("el evento stage.path_b lleva el desglose por fuente + el tally de ZFIN (la traza viva y el "
      "replay leen el MISMO resumen)",
      pl["n_results_by_source"]["zfin"] == 1 and pl["trigger"] == "confidence"
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

pl = runs_mod.build_plan("¿osr1 es suficiente para inducir el pronefros ectopicamente?",
                         ["osr1"], planner=_fake_planner_ok, history_rows=HIST_OK)
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

npass = sum(CHECKS)
print("\n== %d/%d PASS ==" % (npass, len(CHECKS)))
sys.exit(0 if npass == len(CHECKS) else 1)

"""smoke_run_recovery.py — gate determinista de la rebanada I5 (ADR-0078): modelo de corrida —
recuperación, citas, precios.

Cubre: (a) el segador de corridas huérfanas (reap_stale_running): una 'running' sin latido por más de
stale_s pasa a failed/worker-lost CON evento, una fresca queda intacta, NADA se re-encola; (b) el
reclamo declara su procedencia (claimed_by/claimed_at) y la vista de /runs la sirve; (c) _token_usage
no cotiza a 0 un modelo sin precio: lo declara en missing_price_models y cost_projection_complete=False;
(d) _normalize_citations jamás itera un string por caracteres (469 pseudocitas medidas): re-parsea con
procedencia o declara 'string-unparseable'; (e) precios: sonnet-5 = (2.0, 10.0) y los modelos del
consejo están en la tabla; (f) start_workers corre el reaper al arrancar y lanza el hilo 'run-reaper'.

100% offline: SQLite en %LOCALAPPDATA%/Temp/claude/witt-smokes, sintetizador/panel/rag stubbeados —
cero red, cero OpenAI/Anthropic, cero mutación de la DATA INAMOVIBLE. Exit 0 = todo PASS.

Corre (con la máscara offline):
  WITT_BACKEND_DB_URL="sqlite:///C:/Users/Emmanuel/AppData/Local/Temp/claude/witt-smokes/smoke-i5.db"
  NEO4J_URI="" RAG_BACKEND=sparse OPENAI_API_KEY="" ANTHROPIC_API_KEY=""
  python rag_index/query_service/smoke_run_recovery.py
(si WITT_BACKEND_DB_URL no viene, se fija a ese archivo; el archivo previo se borra al arrancar.)
"""
import datetime
import os
import sys
import threading
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SMOKES_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Temp" / "claude" / "witt-smokes"
SMOKES_DIR.mkdir(parents=True, exist_ok=True)
_default_db = SMOKES_DIR / "smoke-i5.db"
_url = os.environ.get("WITT_BACKEND_DB_URL") or f"sqlite:///{_default_db.as_posix()}"
os.environ["WITT_BACKEND_DB_URL"] = _url
if _url.startswith("sqlite:///"):
    _f = Path(_url[len("sqlite:///"):])
    if _f.exists():
        _f.unlink()   # BD fresca por corrida del smoke: el gate no hereda estado
os.environ.pop("NEO4J_URI", None)
os.environ["WITT_ALLOW_RUNS_OFFLINE"] = "1"
os.environ.setdefault("RAG_BACKEND", "sparse")
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402
import db  # noqa: E402
import runs as runs_mod  # noqa: E402
from lib import answer_pipeline, rag_backend  # noqa: E402
from lib.rag_backend import Hit, HitList  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


# ---- stubs deterministas (mismo patrón que smoke_run_pipeline) --------------------------------------
_chunk = Hit(doc_id="CORPUS-2026-0003#c000", type="chunk", score=0.9, text="pronephros evidence",
             metadata={})
answer_pipeline.path_b = lambda q, n=2, **kw: []
rag_backend.query = lambda text, k=6: HitList([_chunk], degraded=None)
ALL_A = {"correctness": "APPROVE", "overclaim": "APPROVE", "evidence-grounding": "APPROVE",
         "reproducibility": "APPROVE"}


def _stub_caller(member, system, user_text):
    return ({"verdict": ALL_A[member["lens"]], "caught": f"({member['lens']})", "correction_applied": "",
             "confidence": 0.9, "reasons": []}, {"input_tokens": 10, "output_tokens": 5})


def _mk_synth(evidence_cited, model="stub-synth"):
    def _synth(question, evidence, pass_label):
        return {"direct_answer": "wt1a (ENSDARG00000031420) marks the zebrafish pronephros.",
                "stated_confidence": 0.8, "absence_kind": "not-applicable", "gap_flags": [],
                "evidence_cited": evidence_cited,
                "alternatives_considered": ["wt1b como paralogo redundante: descartado"],
                "framework_applied": "Logic-LM",
                "framework_criterion": "for any task whose criteria are formalizable",
                "framework_reason": "formalizable", "model": model,
                "usage": {"input_tokens": 100, "output_tokens": 50}}
    return _synth


db.init_db()
db.upsert_user("natalia", "Natalia", "medico", "pw-natalia-123")
AUTH = "Bearer " + app.login(app.LoginBody(username="natalia", password="pw-natalia-123"))["token"]

# ---- 0. migración: las columnas nuevas existen y el tipo fecha se compiló por dialecto -------------
cols = {c["name"] for c in __import__("sqlalchemy").inspect(db.engine()).get_columns("runs")}
check("ADR-0078: runs.claimed_by y runs.claimed_at existen tras init_db (create_all + _migrate idempotente)",
      {"claimed_by", "claimed_at"} <= cols)
db.init_db()   # segunda vez: el ALTER duplicado se traga en silencio, nada truena
check("_migrate idempotente: init_db dos veces no truena", True)

# ---- 1. el reclamo declara su procedencia -------------------------------------------------------------
r_a = runs_mod.new_run("natalia", "corrida que reclama un worker con nombre")
claimed = db.claim_next_queued("run-worker-7")
check("claim llena claimed_by (worker_id) y claimed_at (misma marca que started_at)",
      claimed is not None and claimed["run_id"] == r_a and claimed["claimed_by"] == "run-worker-7"
      and claimed["claimed_at"] is not None and claimed["claimed_at"] == claimed["started_at"]
      and claimed["state"] == "running")
row_a = db.get_run(r_a)
check("get_run sirve claimed_by/claimed_at con tz UTC normalizada (SQLite pierde tzinfo)",
      row_a["claimed_by"] == "run-worker-7" and row_a["claimed_at"].tzinfo is not None)
view_a = app.get_run(r_a, authorization=AUTH)
check("GET /runs/{id}: la vista incluye claimed_by y claimed_at (ISO) — la exclusión de _run_view no los tapa",
      view_a["claimed_by"] == "run-worker-7" and isinstance(view_a["claimed_at"], str)
      and view_a["claimed_at"].endswith("+00:00"), f"claimed_at={view_a['claimed_at']}")
lista = app.list_runs(authorization=AUTH)
fila_a = next(r for r in lista["runs"] if r["run_id"] == r_a) if isinstance(lista, dict) else \
    next(r for r in lista if r["run_id"] == r_a)
check("GET /runs (lista): la misma vista trae claimed_by/claimed_at (misma-vista LOTE-01·A1)",
      fila_a["claimed_by"] == "run-worker-7" and fila_a["claimed_at"] == view_a["claimed_at"])
r_b = runs_mod.new_run("natalia", "corrida reclamada por un llamador viejo sin worker_id")
claimed_b = db.claim_next_queued()
check("claim sin worker_id (smokes/harness viejos): claimed_by=None = 'nadie declaró', claimed_at sí",
      claimed_b["run_id"] == r_b and claimed_b["claimed_by"] is None and claimed_b["claimed_at"] is not None)
check("claim con cola vacía sigue devolviendo None", db.claim_next_queued("run-worker-0") is None)

# ---- 2. el segador: vieja -> failed worker-lost CON evento; fresca -> intacta; NUNCA re-encola -------
ahora = db._now()
vieja = ahora - datetime.timedelta(seconds=2000)
# r_a: running con last_event_at viejo (el worker murió); r_b: running fresca (late)
db.update_run(r_a, last_event_at=vieja, started_at=vieja)
db.update_run(r_b, last_event_at=ahora)
# r_c: running SIN last_event_at (murió antes del primer evento) — la referencia cae a started_at
r_c = runs_mod.new_run("natalia", "corrida huérfana sin ningún evento de etapa")
db.claim_next_queued("run-worker-1")
db.update_run(r_c, last_event_at=None, started_at=vieja)
# r_d: queued (no es running) con created_at viejo — el reaper NO la toca: la cola no es orfandad
r_d = runs_mod.new_run("natalia", "corrida encolada vieja, sin worker aún")
db.update_run(r_d, created_at=vieja)
n_ev_a_antes = len(db.events_after(r_a))
segadas = db.reap_stale_running(900, now=ahora)
check("reap_stale_running(900): sega la vieja con latido viejo y la vieja sin latido; no la fresca ni la queued",
      sorted(segadas) == sorted([r_a, r_c]), f"segadas={segadas}")
fa = db.get_run(r_a)
check("segada: state=failed, finished_at puesto, error 'worker-lost: sin latido por >900 s (ADR-0078)'",
      fa["state"] == "failed" and fa["finished_at"] is not None
      and fa["error"] == "worker-lost: sin latido por >900 s (ADR-0078)", f"error={fa['error']}")
ev_a = db.events_after(r_a)
ult = ev_a[-1] if ev_a else {}
check("segada: UN evento run.state {state:'failed', reason:'worker-lost', stale_s:900} en la bitácora, level=error",
      len(ev_a) == n_ev_a_antes + 1 and ult.get("type") == "run.state" and ult.get("level") == "error"
      and (ult.get("payload") or {}).get("state") == "failed"
      and (ult.get("payload") or {}).get("reason") == "worker-lost"
      and (ult.get("payload") or {}).get("stale_s") == 900.0
      and (ult.get("payload") or {}).get("ref_field") == "last_event_at", f"payload={ult.get('payload')}")
fc = db.get_run(r_c)
ev_c = db.events_after(r_c)
check("segada sin last_event_at: la referencia fue started_at y el evento lo DECLARA (ref_field)",
      fc["state"] == "failed" and (ev_c[-1].get("payload") or {}).get("ref_field") == "started_at")
fb = db.get_run(r_b)
check("fresca: sigue running, sin error, sin finished_at — intacta",
      fb["state"] == "running" and fb["error"] is None and fb["finished_at"] is None)
fd = db.get_run(r_d)
check("queued vieja: sigue queued — el reaper sólo mira 'running'", fd["state"] == "queued")
check("NUNCA re-encola: ninguna segada volvió a 'queued'; tally cuenta 2 failed",
      db.run_state_tally().get("failed") == 2 and db.run_state_tally().get("queued") == 1,
      f"tally={db.run_state_tally()}")
check("segunda pasada: nada que segar (idempotente)", db.reap_stale_running(900, now=ahora) == [])
check("la vista de la segada: state failed + error worker-lost + heartbeat NO stale (ya no es running)",
      (lambda v: v["state"] == "failed" and v["error"].startswith("worker-lost")
       and v["heartbeat_stale"] is False)(app.get_run(r_a, authorization=AUTH)))
check("usage de la segada: ausente-declarado (token_usage=None), jamás inventado",
      app.get_run(r_a, authorization=AUTH)["token_usage"] is None)

# ---- 3. start_workers: reap al arranque + hilo 'run-reaper' ------------------------------------------
# la cola es FIFO: la queued vieja (r_d) es la que sale al reclamar — se usa lo que el claim DEVUELVE
r_e = db.claim_next_queued("run-worker-viejo")["run_id"]
check("FIFO: el reclamo tomó la queued más vieja (r_d), la cola queda vacía",
      r_e == r_d and db.run_state_tally().get("queued") is None)
db.update_run(r_e, last_event_at=db._now() - datetime.timedelta(seconds=120))
runs_mod._STOP.clear()
runs_mod.start_workers(n=0, reap_stale_s=60)
nombres = [t.name for t in threading.enumerate()]
check("start_workers: reap UNA vez al arrancar (la huérfana de 120 s cae con umbral 60) + hilo 'run-reaper' vivo",
      db.get_run(r_e)["state"] == "failed" and "run-reaper" in nombres, f"threads={nombres}")
check("REAP_STALE_S default 900 (env WITT_REAP_STALE_S) y REAP >= 3 × HEARTBEAT_STALE_S (la vista avisa, el reaper mata)",
      runs_mod.REAP_STALE_S == int(os.environ.get("WITT_REAP_STALE_S", "900"))
      and runs_mod.REAP_STALE_S >= 3 * app.HEARTBEAT_STALE_S,
      f"REAP={runs_mod.REAP_STALE_S} HEARTBEAT={app.HEARTBEAT_STALE_S}")
runs_mod.stop_workers()
check("_reap_once tolera una BD rota (§6 no-hang): devuelve [] sin propagar",
      (lambda orig: (setattr(db, "reap_stale_running", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bd"))),
                     runs_mod._reap_once(60, "prueba"), setattr(db, "reap_stale_running", orig))[1] == [])
      (db.reap_stale_running))

# ---- 4. precios: sonnet-5 corregido, consejo en tabla, modelos sin precio DECLARADOS ------------------
P = runs_mod.PRICES_PER_MTOK_USD
check("precio de claude-sonnet-5 = (2.0, 10.0) (era (3.0, 15.0))", P["claude-sonnet-5"] == (2.0, 10.0))
check("modelos del consejo en la tabla: opus-5, fable-5-1, gpt-6-astra, gpt-5.6-sol",
      P.get("claude-opus-5") == (5.0, 25.0) and P.get("claude-fable-5-1") == (10.0, 50.0)
      and P.get("gpt-6-astra") == (10.0, 50.0) and P.get("gpt-5.6-sol") == (4.0, 20.0))
check("PRICES_AS_OF = '2026-09'", runs_mod.PRICES_AS_OF == "2026-09")
pases_ok = [("pass1", {"model": "claude-opus-4-8", "usage": {"input_tokens": 1000, "output_tokens": 100}})]
tu_ok = runs_mod._token_usage(pases_ok, {"panel": []}, 0)
check("_token_usage con modelo conocido: cost_projection_complete=True, missing_price_models=[] y costo calculado",
      tu_ok["cost_projection_complete"] is True and tu_ok["missing_price_models"] == []
      and tu_ok["estimated_cost_usd"] == round((1000 * 5.0 + 100 * 25.0) / 1e6, 4))
pases_x = pases_ok + [("pass2", {"model": "modelo-desconocido-x", "usage": {"input_tokens": 999999,
                                                                            "output_tokens": 999999}})]
tu_x = runs_mod._token_usage(pases_x, {"panel": []}, 0)
check("_token_usage con modelo desconocido: NO cotiza a 0 — missing_price_models lo nombra, complete=False, "
      "y el costo excluye ese modelo (igual al del caso conocido)",
      tu_x["cost_projection_complete"] is False and tu_x["missing_price_models"] == ["modelo-desconocido-x"]
      and tu_x["estimated_cost_usd"] == tu_ok["estimated_cost_usd"]
      and "INCOMPLETE" in tu_x["cost_class"] and tu_x["by_model"]["modelo-desconocido-x"]["in"] == 999999,
      f"cost={tu_x['estimated_cost_usd']} missing={tu_x['missing_price_models']}")
os.environ["OPENAI_EMBED_MODEL"] = "embed-sin-precio"
tu_e = runs_mod._token_usage(pases_ok, {"panel": []}, 500)
os.environ.pop("OPENAI_EMBED_MODEL", None)
check("embedding con modelo sin precio y tokens > 0: también se declara en missing_price_models",
      tu_e["missing_price_models"] == ["embed-sin-precio"] and tu_e["cost_projection_complete"] is False)

# ---- 5. citas: un string jamás se itera por caracteres --------------------------------------------------
c1, s1 = runs_mod._normalize_citations('["a","b"]', with_schema=True)
check("_normalize_citations('[\"a\",\"b\"]' string) -> 2 citas vía _lista_serializada, schema string-reparsed",
      len(c1) == 2 and [c["id"] for c in c1] == ["a", "b"] and s1["source"] == "string-reparsed"
      and s1["n_raw"] == 2 and s1["n_valid"] == 2, f"schema={s1}")
suelto = "texto suelto sin json " * 22   # 469 chars, el tamaño del incidente real
c2, s2 = runs_mod._normalize_citations(suelto, with_schema=True)
check("_normalize_citations('texto suelto sin json') -> [] y 'string-unparseable' (NUNCA 469 pseudocitas)",
      c2 == [] and s2["source"] == "string-unparseable" and s2["n_valid"] == 0 and s2["n_raw"] == 1
      and s2["raw_len_chars"] == len(suelto), f"schema={s2}")
c3, s3 = runs_mod._normalize_citations('[{"kind":"paper","id":"PMID:12668625","note":"n"}]', with_schema=True)
check("string JSON de citas TIPADAS conserva kind/id (keep_dicts — no se degrada a kind=other)",
      c3 == [{"n": 1, "kind": "paper", "id": "PMID:12668625", "note": "n"}] and s3["source"] == "string-reparsed")
c4, s4 = runs_mod._normalize_citations(None, with_schema=True)
c5, s5 = runs_mod._normalize_citations([], with_schema=True)
c6, s6 = runs_mod._normalize_citations([{"kind": "di-record", "id": "CORPUS-2026-0001"}, {"kind": "x"}],
                                       with_schema=True)
check("tres estados: None -> 'absent' (0/0) ≠ [] -> 'list' (0/0) ≠ lista -> 'list' n_raw=2 n_valid=1 (id vacío no vale)",
      s4 == {"source": "absent", "n_raw": 0, "n_valid": 0} and c4 == []
      and s5 == {"source": "list", "n_raw": 0, "n_valid": 0}
      and s6["source"] == "list" and s6["n_raw"] == 2 and s6["n_valid"] == 1 and len(c6) == 2)
check("compatibilidad: sin with_schema devuelve la lista tal cual (llamadores viejos)",
      runs_mod._normalize_citations([{"kind": "paper", "id": "PMID:1"}]) ==
      [{"n": 1, "kind": "paper", "id": "PMID:1", "note": ""}])
check("_lista_serializada por default (gap_flags/alternatives) sigue re-serializando dicts a string (ADR-0074)",
      runs_mod._lista_serializada('[{"a":1},"b"]') == ['{"a": 1}', "b"]
      and runs_mod._lista_serializada('[{"a":1}]', keep_dicts=True) == [{"a": 1}]
      and runs_mod._lista_serializada(123) is None)

# ---- 6. end-to-end: evidence_cited serializado llega al registro con schema y crudo -------------------
runs_mod._STOP.clear()
def _corre(question, synth):
    """new_run + claim (FIFO: la cola está vacía, así que el claim devuelve ESTA corrida) + execute_run."""
    rid = runs_mod.new_run("natalia", question)
    claimed = db.claim_next_queued("run-worker-smoke")
    assert claimed and claimed["run_id"] == rid, f"claim tomó otra corrida: {claimed and claimed['run_id']}"
    runs_mod.execute_run(claimed, synthesizer=synth, panel_caller=_stub_caller)
    return rid


r_f = _corre("corrida cuyo sintetizador devuelve evidence_cited como string",
             _mk_synth('[{"kind":"di-record","id":"CORPUS-2026-0001"}]'))
rec_f = app.get_frozen_record(r_f, authorization=AUTH)
check("registro congelado: citations re-parseadas (1 válida) + citations_schema string-reparsed + evidence_cited_raw declarado",
      rec_f["citations"] == [{"n": 1, "kind": "di-record", "id": "CORPUS-2026-0001", "note": ""}]
      and rec_f["citations_schema"] == {"source": "string-reparsed", "n_raw": 1, "n_valid": 1}
      and "evidence_cited_raw" in rec_f,
      f"schema={rec_f.get('citations_schema')} state={db.get_run(r_f)['state']}")
r_g = _corre("corrida cuyo sintetizador devuelve evidence_cited como prosa",
             _mk_synth("see the papers cited above, PMID:1 and PMID:2"))
rec_g = app.get_frozen_record(r_g, authorization=AUTH)
check("registro congelado con string no parseable: citations=[] y schema string-unparseable (0 pseudocitas)",
      rec_g["citations"] == [] and rec_g["citations_schema"]["source"] == "string-unparseable"
      and rec_g["citations_schema"]["n_valid"] == 0 and db.get_run(r_g)["state"] == "awaiting_closure",
      f"schema={rec_g.get('citations_schema')}")
r_h = _corre("corrida con lista normal de citas",
             _mk_synth([{"kind": "di-record", "id": "CORPUS-2026-0001"}]))
rec_h = app.get_frozen_record(r_h, authorization=AUTH)
check("registro congelado con lista: schema 'list' 1/1 y evidence_cited_raw=None (llegó como lista)",
      rec_h["citations_schema"] == {"source": "list", "n_raw": 1, "n_valid": 1}
      and rec_h["evidence_cited_raw"] is None)
check("token_usage del registro: stub-synth sin precio -> missing_price_models + complete=False; opus del panel cotizado",
      rec_h["token_usage"]["missing_price_models"] == ["stub-synth"]
      and rec_h["token_usage"]["cost_projection_complete"] is False
      and rec_h["token_usage"]["estimated_cost_usd"] > 0)
check("claimed_by del worker de smoke viaja en la vista de la corrida terminada",
      app.get_run(r_h, authorization=AUTH)["claimed_by"] == "run-worker-smoke")

# ---- 7. /usage: la suma declara los modelos sin precio ---------------------------------------------------
us = app.usage(authorization=AUTH)
check("/usage: missing_price_models nombra a stub-synth, cost_projection_complete=False, by_model[stub].estimated_cost_usd=None",
      "stub-synth" in us["missing_price_models"] and us["cost_projection_complete"] is False
      and us["by_model"]["stub-synth"]["estimated_cost_usd"] is None
      and us["by_model"]["stub-synth"]["price_state"] == "missing"
      and us["by_model"]["claude-opus-4-8"]["estimated_cost_usd"] > 0
      and us["n_runs_cost_incomplete"] == 3 and "INCOMPLETE" in us["cost_class"],
      f"missing={us['missing_price_models']} incompletas={us['n_runs_cost_incomplete']}")

n_ok = sum(CHECKS)
print(f"\n== {n_ok}/{len(CHECKS)} PASS ==")
sys.exit(0 if n_ok == len(CHECKS) else 1)

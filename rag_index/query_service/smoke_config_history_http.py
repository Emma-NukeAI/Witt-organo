"""
smoke_config_history_http.py — gate HTTP de la BITÁCORA DE CONFIGURACIÓN (ADR-0081 (I) y (E), rebanada S5).

Fija, vía ASGI TestClient SIN lifespan (por eso `config_ledger.boot()` es llamable DIRECTA) y con la comparación
PURA `config_ledger.diff_rows` (medible sin BD):
  · primer arranque: UNA fila por campo de models.SNAPSHOT_FIELDS (28), previous_value null, note
    'first-boot-snapshot', changed_by 'system:boot-diff', boot_id/generation en cada fila
  · segundo arranque sin cambios → 0 filas (idempotente)
  · env cambiada (WITT_MODEL_SYNTH, WITT_PANEL_MIN_FAMILIES) → EXACTAMENTE los campos que cambiaron (+ la
    firma del panel), con previous_value y source 'env:<VAR>'
  · runtime-diff con `today` inyectado y WITT_PANEL_AUTO_RETIRE=1: al llegar retire_not_before el asiento
    evidence-grounding cambia (haiku → sonnet-5, source 'auto-retire:…') y la firma; changed_by 'system:runtime-diff'
  · kill-switch WITT_CONFIG_LEDGER=0: cero escrituras, ledger_state literal
  · un fallo del ledger (snapshot que lanza / append que lanza) → boot() y observe() NO lanzan; ledger_state 'error: <tipo>'
  · ningún `value` de fila ni de `current` contiene un valor con forma de llave (env de modelo con 'sk-…' se
    rechaza y se REDACTA)
  · GET /config-history: entries del ARCHIVO byte-compatibles + entries_class · ledger[] + ledger_state ·
    current {recorded_at, boot_id, generation, panel_signature, fields, warnings, unknown_models} ·
    provenance.db · model_generation; /status BYTE-IGUAL (keyset de f57a3d3, embed_model_changed_at del archivo)
  · consulta_sistema.config.models_effective == /config-history.current (misma verdad por dos puertas) y
    ledger {n_rows, last_recorded_at, state}

Las comprobaciones marcadas [S4] pasan por db.config_ledger_* (rebanada S4, ADR-0081) — dependencia DURA desde S7
(la rama "[S4 pendiente]" de la obra se retiró): un build sin esas funciones queda ROJO y lo dice, jamás se simula con un stub.

NO-SPEND: sin red (urlopen bloqueado y contado), sin modelo. BD sqlite temporal fuera del repo.
Uso (máscara offline):
  WITT_BACKEND_DB_URL="sqlite:///C:/Users/Emmanuel/AppData/Local/Temp/claude/witt-smokes/adr81-config-history-http.db"
  NEO4J_URI="" RAG_BACKEND=sparse OPENAI_API_KEY="" ANTHROPIC_API_KEY="" WITT_RUN_ORIGIN=smoke
  python rag_index/query_service/smoke_config_history_http.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# --- máscara offline ANTES de importar la app (misma disciplina que los otros gates) ----------------
SMOKES_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Temp" / "claude" / "witt-smokes"
SMOKES_DIR.mkdir(parents=True, exist_ok=True)
_url = os.environ.get("WITT_BACKEND_DB_URL") or f"sqlite:///{(SMOKES_DIR / 'adr81-config-history-http.db').as_posix()}"
os.environ["WITT_BACKEND_DB_URL"] = _url
if _url.startswith("sqlite:///"):
    _f = Path(_url[len("sqlite:///"):])
    if _f.exists():
        _f.unlink()
os.environ["NEO4J_URI"] = ""
os.environ["RAG_BACKEND"] = "sparse"
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["WITT_RUN_ORIGIN"] = "smoke"
# el proceso arranca SIN ninguna env del ADR: el snapshot base es el de los defaults declarados
for _var in ("WITT_MODEL_GENERATION", "WITT_MODEL_SYNTH", "WITT_MODEL_PLANNER", "WITT_MODEL_ELICIT",
             "WITT_MODEL_QUESTION", "WITT_JUDGE_CORRECTNESS", "WITT_JUDGE_OVERCLAIM", "WITT_JUDGE_GROUNDING",
             "OPENAI_JUDGE_MODEL", "WITT_PANEL_AUTO_RETIRE", "WITT_PANEL_MIN_FAMILIES", "WITT_PANEL_MIN_LENSES",
             "WITT_OPENAI_API", "WITT_OPENAI_STORE", "WITT_OPENAI_MAX_OUTPUT_TOKENS", "WITT_OPENAI_REASONING_EFFORT",
             "WITT_OPENAI_TIMEOUT_S", "WITT_ANTHROPIC_EFFORT", "WITT_ANTHROPIC_EFFORT_ELICIT", "WITT_CONFIG_LEDGER",
             "WITT_JUDGE_RETRIES", "OPENAI_EMBED_MODEL", "WITT_COMPETENCE_GATE", "WITT_SEARCH_HARNESS",
             "WITT_REVISION_CYCLE"):
    os.environ.pop(_var, None)

# ---- cero red: urlopen bloqueado y CONTADO durante TODO el smoke ---------------------------------------
import urllib.request as _urlreq  # noqa: E402

_URLOPEN_CALLS = []


def _urlopen_blocked(*a, **kw):
    _URLOPEN_CALLS.append(a[0] if a else kw.get("url"))
    raise RuntimeError("smoke_config_history_http: red bloqueada")


_urlreq.urlopen = _urlopen_blocked

import db  # noqa: E402
import app as app_mod  # noqa: E402
import config_ledger  # noqa: E402
import runs as runs_mod  # noqa: E402
from lib import models  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  -> {detail}" if detail else ""))


def _fin():
    n_pass = sum(CHECKS)
    print(f"\n{n_pass}/{len(CHECKS)} PASS")
    sys.exit(0 if n_pass == len(CHECKS) else 1)


# S7 (N): S4 aterrizó — db.config_ledger_* es dependencia DURA de config_ledger (se retiró la rama "[S4 pendiente]"):
# se MIDE aquí y todo lo que sigue la da por hecha.
check("[S4] db.config_ledger_last_by_field / config_ledger_append / config_ledger_list presentes (dependencia dura de config_ledger)",
      all(callable(getattr(db, n, None)) for n in ("config_ledger_last_by_field", "config_ledger_append", "config_ledger_list")))
HOY, RETIRO = "2026-09-15", "2026-10-15"
# ADR-0081 (M.4, S7): ids de modelo LEÍDOS de la tabla (defaults g2), jamás literales en el smoke
_G2 = models.GENERATIONS["g2-2026-09"]["defaults"]
OPUS5, SON, HAI, G4O = _G2["synthesizer"], _G2["judge.overclaim"], _G2["judge.evidence-grounding"], _G2["judge.reproducibility"]
FAKE_KEY = "sk-FAKEKEYSMOKE0123456789abcdefghijklmnop"    # jamás debe salir en ninguna fila ni snapshot
N_FIELDS = len(models.SNAPSHOT_FIELDS)

db.init_db()
db.upsert_user("natalia", "Natalia", "medico", "pw-natalia")
client = TestClient(app_mod.app)   # SIN lifespan: boot() no ha corrido → ledger_state 'not-booted (…)'
r = client.post("/login", json={"username": "natalia", "password": "pw-natalia"})
assert r.status_code == 200, r.text
AUTH = {"Authorization": "Bearer " + r.json()["token"]}

# ---- 0. /status ANTES de todo (golden del keyset de f57a3d3) ----------------------------------------
STATUS_KEYS_F57A3D3 = {"store_version", "record_count", "sha", "doc_count", "entity_count", "embed_model",
                       "embed_dim", "index_state", "index_version", "integrity", "embed_model_changed_at",
                       "refreshed_at"}
st0 = client.get("/status", headers=AUTH).json()

# ---- 1. la comparación PURA (sin BD): diff_rows ------------------------------------------------------
snap0 = config_ledger.take_snapshot(env={}, today=HOY)
filas0 = config_ledger.diff_rows(snap0, {}, config_ledger.CHANGED_BY_BOOT, boot_id="boot-smoke")
check(f"diff_rows primer arranque: {N_FIELDS} filas (una por campo de SNAPSHOT_FIELDS, en orden), previous_value null, "
      "note 'first-boot-snapshot', changed_by 'system:boot-diff', boot_id y generation en cada fila",
      [f["field"] for f in filas0] == list(models.SNAPSHOT_FIELDS)
      and all(f["previous_value"] is None and f["note"] == "first-boot-snapshot"
              and f["changed_by"] == "system:boot-diff" and f["boot_id"] == "boot-smoke"
              and f["generation"] == "g2-2026-09" for f in filas0),
      f"n={len(filas0)} primera={filas0[0] if filas0 else None}")
check("fila: forma cerrada {recorded_at, field, value, previous_value, source, changed_by, scope, generation, boot_id, note}; "
      "value codificado como texto (bool → 'true'|'false', None → 'null', str tal cual)",
      all(set(f) == {"recorded_at", "field", "value", "previous_value", "source", "changed_by", "scope", "generation",
                     "boot_id", "note"} for f in filas0)
      and {f["field"]: f["value"] for f in filas0}["panel.auto_retire"] == "false"
      and {f["field"]: f["value"] for f in filas0}["openai.reasoning_effort"] == "null"
      and {f["field"]: f["value"] for f in filas0}["role.synthesizer"] == OPUS5
      and {f["field"]: f["value"] for f in filas0}["panel.min_families"] == "2",
      f"{ {f['field']: f['value'] for f in filas0} }")
ultimas = {f["field"]: {"value": f["value"]} for f in filas0}
check("diff_rows segundo arranque sin cambios → 0 filas (idempotente)",
      config_ledger.diff_rows(config_ledger.take_snapshot(env={}, today=HOY), ultimas, config_ledger.CHANGED_BY_BOOT) == [])

ENV_CAMBIO = {"WITT_MODEL_SYNTH": SON, "WITT_PANEL_MIN_FAMILIES": "0"}
filas1 = config_ledger.diff_rows(config_ledger.take_snapshot(env=ENV_CAMBIO, today=HOY), ultimas,
                                 config_ledger.CHANGED_BY_BOOT)
por_campo = {f["field"]: f for f in filas1}
check("env cambiada → EXACTAMENTE {role.synthesizer, panel.min_families, panel_signature}: sonnet-5 (prev opus-5, source "
      "env:WITT_MODEL_SYNTH) · '0' (prev '2', kill-switch válido) · firma nueva; note null (no es primer arranque)",
      set(por_campo) == {"role.synthesizer", "panel.min_families", "panel_signature"}
      and por_campo["role.synthesizer"]["value"] == SON
      and por_campo["role.synthesizer"]["previous_value"] == OPUS5
      and por_campo["role.synthesizer"]["source"] == "env:WITT_MODEL_SYNTH"
      and por_campo["panel.min_families"]["value"] == "0" and por_campo["panel.min_families"]["previous_value"] == "2"
      and por_campo["panel_signature"]["previous_value"] == snap0["panel_signature"]
      and all(f["note"] is None for f in filas1),
      f"{sorted(por_campo)} {por_campo.get('role.synthesizer')}")

base_ar = config_ledger.take_snapshot(env={"WITT_PANEL_AUTO_RETIRE": "1"}, today=HOY)
ult_ar = {f["field"]: {"value": f["value"]} for f in config_ledger.diff_rows(base_ar, {}, config_ledger.CHANGED_BY_BOOT)}
snap_ret = config_ledger.take_snapshot(env={"WITT_PANEL_AUTO_RETIRE": "1"}, today=RETIRO)
filas_rt = config_ledger.diff_rows(snap_ret, ult_ar, config_ledger.CHANGED_BY_RUNTIME)
por_rt = {f["field"]: f for f in filas_rt}
check("runtime-diff (today inyectado 2026-10-15, AUTO_RETIRE=1): EXACTAMENTE {panel.evidence-grounding, panel_signature} — "
      f"haiku → {SON} con source 'auto-retire:{HAI}->{SON}', changed_by 'system:runtime-diff'; "
      "el 2026-09-15 NO sustituye (retire_not_before es frontera, faltan 30 días)",
      set(por_rt) == {"panel.evidence-grounding", "panel_signature"}
      and por_rt["panel.evidence-grounding"]["value"] == SON
      and por_rt["panel.evidence-grounding"]["previous_value"] == HAI
      and por_rt["panel.evidence-grounding"]["source"] == f"auto-retire:{HAI}->{SON}"
      and all(f["changed_by"] == "system:runtime-diff" for f in filas_rt)
      and base_ar["fields"]["panel.evidence-grounding"]["value"] == HAI
      and any(w.startswith(f"retirement-due: {HAI} en judge.evidence-grounding") for w in base_ar["warnings"]),
      f"{sorted(por_rt)} {por_rt.get('panel.evidence-grounding')} warnings={base_ar['warnings']}")

# ---- 2. cinturón de llaves: una env de modelo con forma de llave se rechaza y se REDACTA --------------
snap_sk = config_ledger.take_snapshot(env={"OPENAI_JUDGE_MODEL": FAKE_KEY}, today=HOY)
filas_sk = config_ledger.diff_rows(snap_sk, {}, config_ledger.CHANGED_BY_BOOT)
blob_sk = json.dumps({"snapshot": snap_sk, "rows": filas_sk}, ensure_ascii=False, default=str)
check(f"ningún valor contiene la llave falsa: OPENAI_JUDGE_MODEL='sk-…' → asiento default {G4O} con source "
      "'default-invalid-env:OPENAI_JUDGE_MODEL (secret-like-value)', rejected_env con value REDACTADO, y 'sk-' ausente de "
      "todo value de fila",
      FAKE_KEY not in blob_sk and "sk-" not in " ".join(str(f["value"]) for f in filas_sk)
      and snap_sk["fields"]["panel.reproducibility"]["value"] == G4O
      and snap_sk["fields"]["panel.reproducibility"]["source"] == "default-invalid-env:OPENAI_JUDGE_MODEL (secret-like-value)"
      and snap_sk["rejected_env"] and snap_sk["rejected_env"][0]["value"] == "<redactado: parece llave>",
      f"repro={snap_sk['fields']['panel.reproducibility']} rejected={snap_sk['rejected_env']}")

# ---- 3. boot() nunca lanza; kill-switch; fallo del snapshot ------------------------------------------
res_kill = config_ledger.boot(env={"WITT_CONFIG_LEDGER": "0"}, today=HOY)
check("kill-switch WITT_CONFIG_LEDGER=0: boot() → state 'kill-switch WITT_CONFIG_LEDGER=0', 0 filas escritas, snapshot tomado "
      "(la baseline de observe existe aunque no se escriba)",
      res_kill["state"] == "kill-switch WITT_CONFIG_LEDGER=0" and res_kill["n_rows_written"] == 0
      and isinstance(res_kill["snapshot"], dict) and config_ledger._LEDGER_STATE["last"] is not None,
      f"{res_kill['state']} n={res_kill['n_rows_written']}")
_snap_real = config_ledger.take_snapshot


def _snap_boom(*a, **kw):
    raise RuntimeError("snapshot roto (smoke)")


config_ledger.take_snapshot = _snap_boom
res_err = config_ledger.boot(env={}, today=HOY)
res_obs_err = config_ledger.observe(None)
config_ledger.take_snapshot = _snap_real
check("un fallo interno del ledger JAMÁS lanza: boot() → state 'error: RuntimeError' con la causa; observe(None) tampoco lanza",
      res_err["state"] == "error: RuntimeError" and "snapshot roto" in (res_err["error"] or "")
      and res_obs_err["state"] == "error: RuntimeError" and res_obs_err["n_written"] == 0,
      f"{res_err['state']} | {res_obs_err}")

# ---- 4. [S4] el ledger REAL en BD: first-boot, 2º boot, env cambiada, runtime-diff, append que lanza ----
res_b1 = config_ledger.boot(env={}, today=HOY)
check(f"[S4] boot() primer arranque real: state 'ok', first_boot true, {N_FIELDS} filas escritas (una por campo), rejected []",
      res_b1["state"] == "ok" and res_b1["first_boot"] is True and res_b1["n_rows_written"] == N_FIELDS
      and res_b1["rejected"] == [], f"{ {k: v for k, v in res_b1.items() if k != 'snapshot'} }")
res_b2 = config_ledger.boot(env={}, today=HOY)
check("[S4] segundo boot() sin cambios: 0 filas, changed_fields [], state 'ok'",
      res_b2["state"] == "ok" and res_b2["n_rows_written"] == 0 and res_b2["changed_fields"] == [],
      f"{ {k: v for k, v in res_b2.items() if k != 'snapshot'} }")
res_b3 = config_ledger.boot(env=ENV_CAMBIO, today=HOY)
check("[S4] boot() con env cambiada: EXACTAMENTE 3 filas (role.synthesizer, panel.min_families, panel_signature) — la tabla "
      "guarda previous_value",
      res_b3["state"] == "ok" and sorted(res_b3["changed_fields"]) == ["panel.min_families", "panel_signature", "role.synthesizer"]
      and res_b3["n_rows_written"] == 3, f"{res_b3['changed_fields']} n={res_b3['n_rows_written']}")
ultimas_db = {}
try:
    ultimas_db = db.config_ledger_last_by_field() or {}
except Exception as e:
    ultimas_db = {"__error__": f"{type(e).__name__}"}
check(f"[S4] db.config_ledger_last_by_field: la última fila de role.synthesizer vale '{SON}' con previous_value '{OPUS5}'",
      isinstance(ultimas_db.get("role.synthesizer"), dict)
      and ultimas_db["role.synthesizer"].get("value") == SON
      and ultimas_db["role.synthesizer"].get("previous_value") == OPUS5,
      f"{ultimas_db.get('role.synthesizer') or ultimas_db.get('__error__')}")
# runtime-diff real: baseline (boot) con AUTO_RETIRE=1 hoy; la corrida del 2026-10-15 observa el retiro
config_ledger.boot(env={"WITT_PANEL_AUTO_RETIRE": "1"}, today=HOY)
res_obs = config_ledger.observe(config_ledger.take_snapshot(env={"WITT_PANEL_AUTO_RETIRE": "1"}, today=RETIRO),
                                env={"WITT_PANEL_AUTO_RETIRE": "1"})
check("[S4] observe(snapshot) en corrida: el retiro de haiku (today 2026-10-15) escribe EXACTAMENTE 2 filas runtime-diff "
      "(panel.evidence-grounding, panel_signature); una segunda observación igual → 0",
      res_obs["state"] == "ok" and sorted(res_obs["changed_fields"]) == ["panel.evidence-grounding", "panel_signature"]
      and config_ledger.observe(config_ledger.take_snapshot(env={"WITT_PANEL_AUTO_RETIRE": "1"}, today=RETIRO),
                                env={"WITT_PANEL_AUTO_RETIRE": "1"})["n_written"] == 0,
      f"{res_obs}")
# corrector ADR-0081 (I): el servicio corre WITT_RUN_WORKERS hilos (default 2); dos execute_run que observan el MISMO cambio a
# la vez (auto-retire al cruzar retire_not_before) NO deben duplicar la fila runtime-diff en una tabla append-only →
# observe() está serializado por config_ledger._LOCK. Medido: baseline con haiku (boot HOY), dos hilos observan el retiro.
import threading as _th  # noqa: E402

config_ledger.boot(env={"WITT_PANEL_AUTO_RETIRE": "1"}, today=HOY)      # baseline: haiku de vuelta (2 filas boot-diff)
_snap_rt = config_ledger.take_snapshot(env={"WITT_PANEL_AUTO_RETIRE": "1"}, today=RETIRO)
_barrier, _res_th = _th.Barrier(2), []


def _obs_worker():
    _barrier.wait()
    _res_th.append(config_ledger.observe(_snap_rt, env={"WITT_PANEL_AUTO_RETIRE": "1"}))


_ths = [_th.Thread(target=_obs_worker, name=f"run-worker-{i}") for i in range(2)]
for _t in _ths:
    _t.start()
for _t in _ths:
    _t.join()
check("[S4, corrector] observe() CONCURRENTE desde 2 hilos con el MISMO cambio (retiro de haiku): serializado por _LOCK → en total "
      "EXACTAMENTE 2 filas runtime-diff (panel.evidence-grounding, panel_signature) — una observación escribe 2 y la otra 0, "
      "ninguna duplica; ambas state 'ok'",
      hasattr(config_ledger, "_LOCK") and len(_res_th) == 2 and sorted(r["n_written"] for r in _res_th) == [0, 2]
      and sorted(f for r in _res_th for f in r["changed_fields"]) == ["panel.evidence-grounding", "panel_signature"]
      and all(r["state"] == "ok" for r in _res_th), f"{_res_th}")
_append_real = db.config_ledger_append


def _append_boom(rows):
    raise RuntimeError("append roto (smoke)")


db.config_ledger_append = _append_boom
res_b4 = config_ledger.boot(env={"WITT_MODEL_PLANNER": SON}, today=HOY)
db.config_ledger_append = _append_real
check("[S4] append que lanza → boot() devuelve state 'error: RuntimeError' (arranque OK, la causa declarada), sin propagar",
      res_b4["state"] == "error: RuntimeError" and "append roto" in (res_b4.get("error") or ""),
      f"{res_b4['state']} {res_b4.get('error')}")
config_ledger.boot(env={}, today=HOY)   # baseline final = defaults (deja la BD con la vuelta registrada)

# ---- 5. GET /config-history ---------------------------------------------------------------------------
check("GET /config-history sin token -> 401", client.get("/config-history").status_code == 401)
resp = client.get("/config-history", headers=AUTH)
check("GET /config-history -> 200", resp.status_code == 200, resp.text[:200])
CH = resp.json()
archivo = json.loads(app_mod._CONFIG_HISTORY.read_text(encoding="utf-8")).get("entries", [])
check("entries == el ARCHIVO byte-compatible (rag_index/config_history.json) · entries_class 'atestiguada (archivo human-maintained; "
      "fechas de ADRs)' · provenance.path/mtime siguen · user_history/store_version_history/refreshed_at siguen",
      CH.get("entries") == archivo and CH.get("entries_class") == "atestiguada (archivo human-maintained; fechas de ADRs)"
      and CH.get("provenance", {}).get("path") == "rag_index/config_history.json" and "mtime" in CH.get("provenance", {})
      and all(k in CH for k in ("user_history", "store_version_history", "refreshed_at")),
      f"keys={sorted(CH)}")
cur = CH.get("current") or {}
check(f"current: {{recorded_at, boot_id, generation, panel_signature, fields, warnings, unknown_models, actor_state}} — fields con los "
      f"{N_FIELDS} campos en el orden de SNAPSHOT_FIELDS, cada uno {{value, source}}; generation 'g2-2026-09'; model_generation == current.generation",
      {"recorded_at", "boot_id", "generation", "panel_signature", "fields", "warnings", "unknown_models", "actor_state"} <= set(cur)
      and list(cur.get("fields") or {}) == list(models.SNAPSHOT_FIELDS)
      and all(set(v) == {"value", "source"} for v in cur["fields"].values())
      and cur["generation"] == "g2-2026-09" and CH.get("model_generation") == cur["generation"]
      and cur["actor_state"] == "not-observable (env set outside the service)",
      f"gen={cur.get('generation')} n_fields={len(cur.get('fields') or {})} actor={cur.get('actor_state')}")
check(f"current.fields: panel.reproducibility {G4O} (default:g2-2026-09) · openai.api 'table' (default-unset) · "
      "contract.render_contract_version == runs.RENDER_CONTRACT_VERSION (source runs.RENDER_CONTRACT_VERSION) · competence.gate true · "
      "search.harness true · revision.cycle true (los 4 extras vienen del llamador, no 'not-provided-by-caller')",
      cur["fields"]["panel.reproducibility"] == {"value": G4O, "source": "default:g2-2026-09"}
      and cur["fields"]["openai.api"] == {"value": "table", "source": "default-unset:WITT_OPENAI_API"}
      and cur["fields"]["contract.render_contract_version"] == {"value": runs_mod.RENDER_CONTRACT_VERSION,
                                                                "source": "runs.RENDER_CONTRACT_VERSION"}
      and cur["fields"]["competence.gate"]["value"] is True and cur["fields"]["search.harness"]["value"] is True
      and cur["fields"]["revision.cycle"]["value"] is True
      and all("not-provided-by-caller" not in cur["fields"][k]["source"] for k in models.EXTRA_FIELDS),
      f"{ {k: cur['fields'][k] for k in ('panel.reproducibility', 'openai.api') + tuple(models.EXTRA_FIELDS)} }")
check("ledger_limit 500 · ledger_encoding y ledger_scope_rule declarados · ledger_writer {state, boot_id, booted_at, n_written_boot, …}",
      CH.get("ledger_limit") == 500 and CH.get("ledger_encoding") == config_ledger.VALUE_ENCODING
      and CH.get("ledger_scope_rule") == config_ledger.SCOPE_RULE
      and {"state", "boot_id", "booted_at", "n_written_boot", "n_written_runtime", "rejected", "last_error"} <= set(CH.get("ledger_writer") or {}),
      f"{CH.get('ledger_limit')} writer_keys={sorted(CH.get('ledger_writer') or {})}")
ledger = CH.get("ledger") or []
check(f"[S4] ledger_state 'ok' · ledger[] con ≥ {N_FIELDS} filas (first-boot + cambios + vueltas), recorded_at DESC, la primera es la "
      "más reciente · provenance.db {table 'config_history', n_rows == COUNT real, last_recorded_at == ledger[0].recorded_at}",
      CH.get("ledger_state") == "ok" and len(ledger) >= N_FIELDS
      and all(ledger[i]["recorded_at"] >= ledger[i + 1]["recorded_at"] for i in range(len(ledger) - 1))
      and (CH.get("provenance", {}).get("db") or {}).get("table") == "config_history"
      and isinstance(CH["provenance"]["db"].get("n_rows"), int) and CH["provenance"]["db"]["n_rows"] >= len(ledger)
      and CH["provenance"]["db"].get("last_recorded_at") == ledger[0]["recorded_at"],
      f"state={CH.get('ledger_state')} n={len(ledger)} db={CH.get('provenance', {}).get('db')}")
check("[S4] cada fila del ledger trae {recorded_at, field, value, previous_value, source, changed_by, scope, generation, boot_id, note} "
      "y hay filas 'system:boot-diff' Y 'system:runtime-diff' (el retiro observado en corrida)",
      bool(ledger) and all({"recorded_at", "field", "value", "previous_value", "source", "changed_by", "scope", "generation",
                            "boot_id", "note"} <= set(f) for f in ledger)
      and {"system:boot-diff", "system:runtime-diff"} <= {f["changed_by"] for f in ledger},
      f"changed_by={sorted({f.get('changed_by') for f in ledger})}")
blob_ch = json.dumps(CH, ensure_ascii=False)
check("ningún value de ledger[] ni de current contiene la llave falsa ni 'sk-' (cinturón de dos capas: models.snapshot + S4)",
      FAKE_KEY not in blob_ch
      and not any("sk-" in str(f.get("value") or "") or "sk-" in str(f.get("previous_value") or "") for f in ledger)
      and not any("sk-" in str(c.get("value") or "") for c in cur["fields"].values()))

# ---- 6. /status BYTE-IGUAL y _embed_model_changed_at intacto ------------------------------------------
st1 = client.get("/status", headers=AUTH).json()
check("/status BYTE-IGUAL: mismo keyset que f57a3d3 (12 llaves, sin NEO4J), idéntico antes y después del ledger, "
      "embed_model_changed_at '2026-06-12' del ARCHIVO (la puerta nueva no toca _embed_model_changed_at)",
      set(st0) == STATUS_KEYS_F57A3D3 and st0 == st1 and st1.get("embed_model_changed_at") == "2026-06-12",
      f"keys={sorted(st1)} changed_at={st1.get('embed_model_changed_at')}")

# ---- 7. consulta_sistema: misma verdad por dos puertas ------------------------------------------------
cs = client.get("/consulta-sistema?q=configuracion+de+modelos", headers=AUTH).json()
sec = ((cs.get("snapshot") or {}).get("secciones") or {}).get("config") or {}
CH2 = client.get("/config-history", headers=AUTH).json()
check("consulta_sistema: q con 'modelo' rutea a la sección config; config.models_effective == /config-history.current "
      "(la MISMA función) y ledger {n_rows, last_recorded_at, state} == provenance.db + ledger_state",
      cs.get("q_matched_sections") == ["config"] and sec.get("models_effective") == CH2.get("current")
      and set(sec.get("ledger") or {}) == {"n_rows", "last_recorded_at", "state"}
      and sec["ledger"]["n_rows"] == CH2["provenance"]["db"]["n_rows"]
      and sec["ledger"]["last_recorded_at"] == CH2["provenance"]["db"]["last_recorded_at"]
      and sec["ledger"]["state"] == CH2["ledger_state"]
      and sec.get("n_cambios") == len(archivo),
      f"matched={cs.get('q_matched_sections')} ledger={sec.get('ledger')} igual={sec.get('models_effective') == CH2.get('current')}")
check("consulta_sistema.resumen menciona la generación efectiva y el estado de la bitácora (cifras del snapshot, no constantes)",
      "generación g2-2026-09" in (cs.get("resumen") or "") and "Bitácora de configuración:" in (cs.get("resumen") or ""),
      (cs.get("resumen") or "")[-220:])

# ---- 8. cero red ------------------------------------------------------------------------------------
check("cero red: urllib.request.urlopen bloqueado y contado == 0", len(_URLOPEN_CALLS) == 0, f"{_URLOPEN_CALLS}")

_fin()

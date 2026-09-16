"""smoke_panel_quorum.py — gate determinista de la rebanada S2 de ADR-0081 (D) + (K) + (A) en composite_auditor.audit():
cuórum por FAMILIAS y LENTES, kill-switches WITT_PANEL_MIN_FAMILIES / WITT_PANEL_MIN_LENSES ∈ {0,1}, GOLDEN byte a byte del
subconjunto 1.9 de audit() @ f57a3d3, panel resuelto EN LA LLAMADA (models.panel), panel_source (K), apply_to_bundle.

Qué MIDE (todo offline, caller inyectado por lente):
  - 4 válidos (2 familias, 4 lentes) → APPROVE; `quorum` completo y exacto; sin llaves panel_incomplete/_reasons cuando ok.
  - juez OpenAI caído + 3 APPROVE Anthropic → REVISE ESTRUCTURAL: panel_incomplete True, panel_incomplete_reasons ['families'],
    panel_single_family True, tally intacto (hallazgo F3 del brief: tres APPROVE de una sola familia ya no aprueban en silencio).
  - MIN_FAMILIES=0|1 → kill-switch declarado (families_gating False, families_ok None) → APPROVE con panel_single_family True.
  - lentes repetidas (4 válidos, 2 lentes) → ['lenses']; 2 válidos/1 familia → ['min_valid','families'] (+'lenses' con el default)
    en ORDEN FIJO; 'unknown' no cuenta como familia pero se VE en families_present; min_* del llamador → source 'caller';
    env basura/negativa → default DECLARADO.
  - GOLDEN: el subconjunto 1.9 de audit() (las llaves de f57a3d3, incluido `attempts[].error`) es BYTE A BYTE el medido con la
    versión f57a3d3 (misma fake) en 4 escenarios (ALL_A · 1 caído · 2 caídos · ilegible) × MIN_FAMILIES∈{0,1} × MIN_LENSES∈{0,1},
    con el panel legado explícito y con panel=None + WITT_MODEL_GENERATION=g1-2026-08 (kill-switch M.2).
  - filas += family_source/api/api_source/reviewer_source/max_tokens (tabla vs legado); attempts += error_kind / model_reported /
    api (tres estados); panel_duplicate_models; panel_origin; panel_source (K) exacto; `directives` aceptado e ignorado;
    panel=None resuelve models.panel() EN LA LLAMADA (env del proceso, sin reimportar); DEFAULT_PANEL = snapshot documental.
  - apply_to_bundle copia las llaves 1.10 al bundle['audit'] y re-sella bundle_identity (answer_pipeline REAL).
  - firmas del contrato S2 (audit, _default_caller) y docstring corregido (L41 de f57a3d3).

100% offline: cero red (urlopen bloqueado y contado = 0), cero gasto de modelo, cero BD, cero mutación de la DATA INAMOVIBLE.
Exit 0 = todo PASS. Ningún id de modelo se escribe aquí como literal: el GOLDEN lleva tokens @@judge.<lente>@@ que se rellenan
con models.GENERATIONS['g1-2026-08'] (= f57a3d3) — gate estático M.4.

Cómo se obtuvo el GOLDEN (2026-09-15): se cargó por importlib la copia byte-idéntica (sha256 9e288b7c…) de
analysis/scripts/lib/composite_auditor.py @ f57a3d3, se corrió audit(CLAIM, EVID, deterministic_checks=DET,
required_because='DI_SUFFICIENT', panel=DEFAULT_PANEL, caller=caller_factory(plan)) con la MISMA fake de este archivo
(WITT_JUDGE_RETRIES sin fijar → 1) y se serializó json.dumps(sort_keys=True, ensure_ascii=True, separators=(',', ':')).

Corre (máscara offline):
  WITT_BACKEND_DB_URL="sqlite:///C:/Users/Emmanuel/AppData/Local/Temp/claude/witt-smokes/adr81-panel-quorum.db"
  NEO4J_URI="" RAG_BACKEND=sparse OPENAI_API_KEY="" ANTHROPIC_API_KEY="" WITT_RUN_ORIGIN=smoke
  python rag_index/query_service/smoke_panel_quorum.py
"""
import hashlib
import inspect
import json
import os
import sys
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
_ADR81_ENVS = ("WITT_MODEL_GENERATION", "WITT_MODEL_SYNTH", "WITT_MODEL_PLANNER", "WITT_MODEL_ELICIT",
               "WITT_MODEL_QUESTION", "WITT_JUDGE_CORRECTNESS", "WITT_JUDGE_OVERCLAIM", "WITT_JUDGE_GROUNDING",
               "OPENAI_JUDGE_MODEL", "WITT_PANEL_AUTO_RETIRE", "WITT_PANEL_MIN_FAMILIES", "WITT_PANEL_MIN_LENSES",
               "WITT_OPENAI_API", "WITT_OPENAI_STORE", "WITT_OPENAI_MAX_OUTPUT_TOKENS", "WITT_OPENAI_REASONING_EFFORT",
               "WITT_OPENAI_TIMEOUT_S", "WITT_ANTHROPIC_EFFORT", "WITT_ANTHROPIC_EFFORT_ELICIT", "WITT_CONFIG_LEDGER",
               "WITT_JUDGE_RETRIES")
for _k in _ADR81_ENVS:
    os.environ.pop(_k, None)
# ADR-0082 (D.1): las env del caller y del consejo tampoco entran al gate (defaults declarados medibles)
for _k in list(os.environ):
    if _k.startswith('WITT_COUNCIL') or _k in ('WITT_ANTHROPIC_MAX_INFLIGHT', 'WITT_ANTHROPIC_RETRY_AFTER_CAP_S', 'WITT_MODEL_COUNCIL',
                                                'WITT_CG_COUNCIL_COMPONENT'):
        os.environ.pop(_k, None)

_NET_CALLS = []


def _blocked_urlopen(*a, **k):
    _NET_CALLS.append(getattr(a[0], "full_url", repr(a[0])) if a else repr(k))
    raise AssertionError("smoke: urllib.request.urlopen bloqueado (cero red)")


urllib.request.urlopen = _blocked_urlopen

from lib import composite_auditor as ca  # noqa: E402
from lib import models  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


def _pop_mins():
    os.environ.pop("WITT_PANEL_MIN_FAMILIES", None)
    os.environ.pop("WITT_PANEL_MIN_LENSES", None)


# --- fake determinista (la MISMA con la que se midió el GOLDEN) --------------------------------------------------------
def caller_factory(plan):
    """plan[lens] = veredicto | Exception | 'ILLEGIBLE' (verdict fuera del vocabulario, con usage: la API cobró)."""
    def _caller(member, system, user_text):
        v = plan[member["lens"]]
        if isinstance(v, Exception):
            raise v
        if v == "ILLEGIBLE":
            return {"verdict": "MAYBE", "confidence": 0.5}, {"input_tokens": 10, "output_tokens": 5}
        out = {"verdict": v, "caught": f"({member['lens']})", "correction_applied": "", "confidence": 0.9, "reasons": []}
        if member["lens"] == "correctness":
            out["domain_niches"] = ["N3"]
        return out, {"input_tokens": 10, "output_tokens": 5}
    return _caller


def caller_3tuple(plan, reported_suffix="-20260901", api="anthropic-messages"):
    """La 3-tupla de ADR-0081 (B): meta con model_reported/api por miembro."""
    inner = caller_factory(plan)

    def _caller(member, system, user_text):
        out, usage = inner(member, system, user_text)
        return out, usage, {"model_reported": member["reviewer"] + reported_suffix, "api": member.get("api") or api}
    return _caller


ALL_A = {"correctness": "APPROVE", "overclaim": "APPROVE", "evidence-grounding": "APPROVE", "reproducibility": "APPROVE"}
DOWN = RuntimeError("judge down")
SCEN = {
    "all_a": ALL_A,
    "one_down": {**ALL_A, "overclaim": DOWN},
    "two_down": {**ALL_A, "overclaim": DOWN, "evidence-grounding": DOWN},
    "illegible": {**ALL_A, "reproducibility": "ILLEGIBLE"},
}
OPENAI_DOWN = {**ALL_A, "reproducibility": RuntimeError("openai judge down")}
CLAIM = {"direct_answer": "wt1a marks the pronephros [1].", "stated_confidence": 0.7}
EVID = {"path_a": [{"id": "CORPUS-2026-0001", "text": "wt1a"}]}
DET = {"admissible": True}

G1 = models.GENERATIONS["g1-2026-08"]["defaults"]
G2 = models.GENERATIONS["g2-2026-09"]["defaults"]
LEGACY_PANEL = [{"reviewer": G1["judge." + lens], "family": models.LENS_FAMILY[lens], "lens": lens} for lens in models.LENSES]

# --- GOLDEN 1.9 @ f57a3d3 (plantillas: @@judge.<lente>@@ → GENERATIONS['g1-2026-08'], que ES f57a3d3) -----------------
_GOLDEN_TEMPLATES = {
    "all_a": r'''{"domain_niches":{"class":"juicio","counts":{"N3":1},"n_classified":1,"n_valid":4,"note":"conteos de jueces por c\u00f3digo, jam\u00e1s un ganador: cuatro opiniones no hacen un hecho. n_classified < n_valid = jueces que no clasificaron; su silencio no se reparte entre los dem\u00e1s."},"judge_retries":{"scope":"judge-call (additional attempts before exclusion)","source":"default-unset:WITT_JUDGE_RETRIES","value":1},"n_valid":4,"panel":[{"attempts":[{"attempt":1,"status":"ok","usage":{"input_tokens":10,"output_tokens":5}}],"caught":"(correctness)","confidence":0.9,"correction_applied":"","domain_niches":["N3"],"family":"anthropic","lens":"correctness","reasons":[],"retries_judge":0,"reviewer":"@@judge.correctness@@","usage":{"input_tokens":10,"output_tokens":5},"verdict":"APPROVE"},{"attempts":[{"attempt":1,"status":"ok","usage":{"input_tokens":10,"output_tokens":5}}],"caught":"(overclaim)","confidence":0.9,"correction_applied":"","family":"anthropic","lens":"overclaim","reasons":[],"retries_judge":0,"reviewer":"@@judge.overclaim@@","usage":{"input_tokens":10,"output_tokens":5},"verdict":"APPROVE"},{"attempts":[{"attempt":1,"status":"ok","usage":{"input_tokens":10,"output_tokens":5}}],"caught":"(evidence-grounding)","confidence":0.9,"correction_applied":"","family":"anthropic","lens":"evidence-grounding","reasons":[],"retries_judge":0,"reviewer":"@@judge.evidence-grounding@@","usage":{"input_tokens":10,"output_tokens":5},"verdict":"APPROVE"},{"attempts":[{"attempt":1,"status":"ok","usage":{"input_tokens":10,"output_tokens":5}}],"caught":"(reproducibility)","confidence":0.9,"correction_applied":"","family":"openai","lens":"reproducibility","reasons":[],"retries_judge":0,"reviewer":"@@judge.reproducibility@@","usage":{"input_tokens":10,"output_tokens":5},"verdict":"APPROVE"}],"required":true,"required_because":"DI_SUFFICIENT","source_vocabulary":"APPROVE|APPROVE_DECLINE|APPROVE_MINOR|REVISE","tally":{"APPROVE":4,"APPROVE_DECLINE":0,"APPROVE_MINOR":0,"REVISE":0},"usage":{"input_tokens":40,"output_tokens":20},"verdict":"APPROVE"}''',
    "one_down": r'''{"domain_niches":{"class":"juicio","counts":{"N3":1},"n_classified":1,"n_valid":3,"note":"conteos de jueces por c\u00f3digo, jam\u00e1s un ganador: cuatro opiniones no hacen un hecho. n_classified < n_valid = jueces que no clasificaron; su silencio no se reparte entre los dem\u00e1s."},"judge_retries":{"scope":"judge-call (additional attempts before exclusion)","source":"default-unset:WITT_JUDGE_RETRIES","value":1},"n_valid":3,"panel":[{"attempts":[{"attempt":1,"status":"ok","usage":{"input_tokens":10,"output_tokens":5}}],"caught":"(correctness)","confidence":0.9,"correction_applied":"","domain_niches":["N3"],"family":"anthropic","lens":"correctness","reasons":[],"retries_judge":0,"reviewer":"@@judge.correctness@@","usage":{"input_tokens":10,"output_tokens":5},"verdict":"APPROVE"},{"attempts":[{"attempt":1,"error":"RuntimeError: judge down","status":"errored"},{"attempt":2,"error":"RuntimeError: judge down","status":"errored"}],"error":"RuntimeError: judge down","family":"anthropic","lens":"overclaim","retries_judge":1,"reviewer":"@@judge.overclaim@@","status":"errored"},{"attempts":[{"attempt":1,"status":"ok","usage":{"input_tokens":10,"output_tokens":5}}],"caught":"(evidence-grounding)","confidence":0.9,"correction_applied":"","family":"anthropic","lens":"evidence-grounding","reasons":[],"retries_judge":0,"reviewer":"@@judge.evidence-grounding@@","usage":{"input_tokens":10,"output_tokens":5},"verdict":"APPROVE"},{"attempts":[{"attempt":1,"status":"ok","usage":{"input_tokens":10,"output_tokens":5}}],"caught":"(reproducibility)","confidence":0.9,"correction_applied":"","family":"openai","lens":"reproducibility","reasons":[],"retries_judge":0,"reviewer":"@@judge.reproducibility@@","usage":{"input_tokens":10,"output_tokens":5},"verdict":"APPROVE"}],"required":true,"required_because":"DI_SUFFICIENT","source_vocabulary":"APPROVE|APPROVE_DECLINE|APPROVE_MINOR|REVISE","tally":{"APPROVE":3,"APPROVE_DECLINE":0,"APPROVE_MINOR":0,"REVISE":0},"usage":{"input_tokens":30,"output_tokens":15},"verdict":"APPROVE"}''',
    "two_down": r'''{"domain_niches":{"class":"juicio","counts":{"N3":1},"n_classified":1,"n_valid":2,"note":"conteos de jueces por c\u00f3digo, jam\u00e1s un ganador: cuatro opiniones no hacen un hecho. n_classified < n_valid = jueces que no clasificaron; su silencio no se reparte entre los dem\u00e1s."},"judge_retries":{"scope":"judge-call (additional attempts before exclusion)","source":"default-unset:WITT_JUDGE_RETRIES","value":1},"n_valid":2,"panel":[{"attempts":[{"attempt":1,"status":"ok","usage":{"input_tokens":10,"output_tokens":5}}],"caught":"(correctness)","confidence":0.9,"correction_applied":"","domain_niches":["N3"],"family":"anthropic","lens":"correctness","reasons":[],"retries_judge":0,"reviewer":"@@judge.correctness@@","usage":{"input_tokens":10,"output_tokens":5},"verdict":"APPROVE"},{"attempts":[{"attempt":1,"error":"RuntimeError: judge down","status":"errored"},{"attempt":2,"error":"RuntimeError: judge down","status":"errored"}],"error":"RuntimeError: judge down","family":"anthropic","lens":"overclaim","retries_judge":1,"reviewer":"@@judge.overclaim@@","status":"errored"},{"attempts":[{"attempt":1,"error":"RuntimeError: judge down","status":"errored"},{"attempt":2,"error":"RuntimeError: judge down","status":"errored"}],"error":"RuntimeError: judge down","family":"anthropic","lens":"evidence-grounding","retries_judge":1,"reviewer":"@@judge.evidence-grounding@@","status":"errored"},{"attempts":[{"attempt":1,"status":"ok","usage":{"input_tokens":10,"output_tokens":5}}],"caught":"(reproducibility)","confidence":0.9,"correction_applied":"","family":"openai","lens":"reproducibility","reasons":[],"retries_judge":0,"reviewer":"@@judge.reproducibility@@","usage":{"input_tokens":10,"output_tokens":5},"verdict":"APPROVE"}],"panel_incomplete":true,"required":true,"required_because":"DI_SUFFICIENT","source_vocabulary":"APPROVE|APPROVE_DECLINE|APPROVE_MINOR|REVISE","tally":{"APPROVE":2,"APPROVE_DECLINE":0,"APPROVE_MINOR":0,"REVISE":0},"usage":{"input_tokens":20,"output_tokens":10},"verdict":"REVISE"}''',
    "illegible": r'''{"domain_niches":{"class":"juicio","counts":{"N3":1},"n_classified":1,"n_valid":3,"note":"conteos de jueces por c\u00f3digo, jam\u00e1s un ganador: cuatro opiniones no hacen un hecho. n_classified < n_valid = jueces que no clasificaron; su silencio no se reparte entre los dem\u00e1s."},"judge_retries":{"scope":"judge-call (additional attempts before exclusion)","source":"default-unset:WITT_JUDGE_RETRIES","value":1},"n_valid":3,"panel":[{"attempts":[{"attempt":1,"status":"ok","usage":{"input_tokens":10,"output_tokens":5}}],"caught":"(correctness)","confidence":0.9,"correction_applied":"","domain_niches":["N3"],"family":"anthropic","lens":"correctness","reasons":[],"retries_judge":0,"reviewer":"@@judge.correctness@@","usage":{"input_tokens":10,"output_tokens":5},"verdict":"APPROVE"},{"attempts":[{"attempt":1,"status":"ok","usage":{"input_tokens":10,"output_tokens":5}}],"caught":"(overclaim)","confidence":0.9,"correction_applied":"","family":"anthropic","lens":"overclaim","reasons":[],"retries_judge":0,"reviewer":"@@judge.overclaim@@","usage":{"input_tokens":10,"output_tokens":5},"verdict":"APPROVE"},{"attempts":[{"attempt":1,"status":"ok","usage":{"input_tokens":10,"output_tokens":5}}],"caught":"(evidence-grounding)","confidence":0.9,"correction_applied":"","family":"anthropic","lens":"evidence-grounding","reasons":[],"retries_judge":0,"reviewer":"@@judge.evidence-grounding@@","usage":{"input_tokens":10,"output_tokens":5},"verdict":"APPROVE"},{"attempts":[{"attempt":1,"error":"RuntimeError: unparseable judge output: verdict='MAYBE'","status":"errored","usage":{"input_tokens":10,"output_tokens":5}},{"attempt":2,"error":"RuntimeError: unparseable judge output: verdict='MAYBE'","status":"errored","usage":{"input_tokens":10,"output_tokens":5}}],"error":"RuntimeError: unparseable judge output: verdict='MAYBE'","family":"openai","lens":"reproducibility","retries_judge":1,"reviewer":"@@judge.reproducibility@@","status":"errored","usage":{"input_tokens":20,"output_tokens":10}}],"required":true,"required_because":"DI_SUFFICIENT","source_vocabulary":"APPROVE|APPROVE_DECLINE|APPROVE_MINOR|REVISE","tally":{"APPROVE":3,"APPROVE_DECLINE":0,"APPROVE_MINOR":0,"REVISE":0},"usage":{"input_tokens":50,"output_tokens":25},"verdict":"APPROVE"}''',
}


def _fill(tpl):
    for lens in models.LENSES:
        tpl = tpl.replace(f"@@judge.{lens}@@", G1["judge." + lens])
    return tpl


GOLDEN_1_9 = {name: _fill(tpl) for name, tpl in _GOLDEN_TEMPLATES.items()}
NEW_TOP = ("families_valid", "n_families_valid", "lenses_valid", "n_lenses_valid", "panel_single_family", "quorum",
           "panel_incomplete_reasons", "panel_duplicate_models", "panel_origin", "panel_source", "failure_kinds_vocabulary")
NEW_ROW = ("family_source", "api", "api_source", "reviewer_source", "max_tokens")
NEW_ATTEMPT = ("error_kind", "model_reported", "api")


def strip_1_10(r):
    """El subconjunto 1.9: quita SÓLO las llaves aditivas de ADR-0081 (top, fila, intento)."""
    r = json.loads(json.dumps(r))
    for k in NEW_TOP:
        r.pop(k, None)
    for row in r["panel"]:
        for k in NEW_ROW:
            row.pop(k, None)
        for a in row.get("attempts", []):
            for k in NEW_ATTEMPT:
                a.pop(k, None)
    return r


def dumps(r):
    return json.dumps(r, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _audit(plan, **kw):
    kw.setdefault("deterministic_checks", DET)
    kw.setdefault("required_because", "DI_SUFFICIENT")
    return ca.audit(CLAIM, EVID, caller=caller_factory(plan), **kw)


# =====================================================================================================================
# 1. GOLDEN byte a byte del subconjunto 1.9 con AMBOS kill-switches (M.2): panel legado explícito y panel=None + g1
# =====================================================================================================================
_full_all_a = None
for mf, ml in (("0", "0"), ("1", "1"), ("0", "1"), ("1", "0")):
    os.environ["WITT_PANEL_MIN_FAMILIES"], os.environ["WITT_PANEL_MIN_LENSES"] = mf, ml
    got = {name: _audit(plan, panel=LEGACY_PANEL) for name, plan in SCEN.items()}
    if _full_all_a is None:
        _full_all_a, _full_two_down = got["all_a"], got["two_down"]
    same = {name: dumps(strip_1_10(r)) == GOLDEN_1_9[name] for name, r in got.items()}
    check(f"GOLDEN 1.9 @ f57a3d3 con MIN_FAMILIES={mf} MIN_LENSES={ml} (kill-switch): los 4 escenarios (ALL_A · 1 caído · 2 caídos · "
          f"ilegible) son BYTE A BYTE el subconjunto 1.9 (verdict, panel_incomplete, tally, usage, attempts[].error, judge_retries…)",
          all(same.values()), json.dumps(same))
os.environ["WITT_PANEL_MIN_FAMILIES"], os.environ["WITT_PANEL_MIN_LENSES"] = "0", "0"
os.environ["WITT_MODEL_GENERATION"] = "g1-2026-08"
got_g1 = {name: _audit(plan) for name, plan in SCEN.items()}          # panel=None → models.panel() EN LA LLAMADA (g1)
same_g1 = {name: dumps(strip_1_10(r)) == GOLDEN_1_9[name] for name, r in got_g1.items()}
os.environ.pop("WITT_MODEL_GENERATION", None)
_pop_mins()
check("GOLDEN con panel=None + WITT_MODEL_GENERATION=g1-2026-08 + MIN 0/0 (los tres kill-switches de M.2): models.panel() resuelto "
      "EN LA LLAMADA == el DEFAULT_PANEL de f57a3d3 → los 4 escenarios byte a byte (reviewers, familias, lentes, orden)",
      all(same_g1.values()) and [r["reviewer"] for r in got_g1["all_a"]["panel"]] == [m["reviewer"] for m in LEGACY_PANEL],
      json.dumps(same_g1))
check("el GOLDEN no es vacuo: el resultado 1.10 SÍ trae las llaves aditivas que strip_1_10 quita (top-level, por fila, por "
      "intento errado) — y la fila errada de f57a3d3 sigue sin `usage` cuando el caller lanzó sin medir",
      set(NEW_TOP) - {"panel_incomplete_reasons"} <= set(_full_all_a)
      and all(set(NEW_ROW) <= set(row) for row in _full_all_a["panel"])
      and all("error_kind" in a for row in _full_two_down["panel"] if row.get("status") == "errored" for a in row["attempts"])
      and "usage" not in [row for row in _full_two_down["panel"] if row.get("status") == "errored"][0])

# =====================================================================================================================
# 2. Cuórum (D) con los defaults (MIN_FAMILIES 2, MIN_LENSES 3) sobre el panel de la tabla (g2, panel=None)
# =====================================================================================================================
r = _audit(ALL_A)
check("(D) 4 válidos → APPROVE; families_valid ['anthropic','openai'] (2), lenses_valid = las 4 lentes en orden del panel, "
      "panel_single_family False; SIN llaves panel_incomplete / panel_incomplete_reasons (ausente = no aplica, tres estados)",
      r["verdict"] == "APPROVE" and r["families_valid"] == ["anthropic", "openai"] and r["n_families_valid"] == 2
      and r["lenses_valid"] == list(models.LENSES) and r["n_lenses_valid"] == 4 and r["panel_single_family"] is False
      and "panel_incomplete" not in r and "panel_incomplete_reasons" not in r)
check("(D) quorum EXACTO: {n_valid 4, min_valid 3, min_families {2, default-unset}, min_lenses {3, default-unset}, families_present "
      "{anthropic 3, openai 1}, lenses_present[4], n_valid_ok/families_ok/lenses_ok True, *_gating True, ok True, failed [], rule, "
      "decided_by 'code'}",
      r["quorum"] == {"n_valid": 4, "min_valid": 3,
                      "min_families": {"value": 2, "source": "default-unset:WITT_PANEL_MIN_FAMILIES"},
                      "min_lenses": {"value": 3, "source": "default-unset:WITT_PANEL_MIN_LENSES"},
                      "families_present": {"anthropic": 3, "openai": 1}, "lenses_present": list(models.LENSES),
                      "n_valid_ok": True, "families_ok": True, "lenses_ok": True,
                      "families_gating": True, "lenses_gating": True, "ok": True, "failed": [],
                      "rule": ca.QUORUM_RULE, "decided_by": "code"}, json.dumps(r["quorum"])[:400])
r = _audit(OPENAI_DOWN)
check("(D) juez OpenAI caído + 3 APPROVE Anthropic → REVISE ESTRUCTURAL: panel_incomplete True, panel_incomplete_reasons "
      "['families'] (código cerrado; los números viven en quorum), n_valid 3 (n_valid_ok True), families_ok False, lenses_ok True, "
      "panel_single_family True, families_valid ['anthropic']; el tally sigue 3 APPROVE (no se fabrica un REVISE de juez)",
      r["verdict"] == "REVISE" and r["panel_incomplete"] is True and r["panel_incomplete_reasons"] == ["families"]
      and r["n_valid"] == 3 and r["quorum"]["n_valid_ok"] is True and r["quorum"]["families_ok"] is False
      and r["quorum"]["lenses_ok"] is True and r["quorum"]["failed"] == ["families"] and r["panel_single_family"] is True
      and r["families_valid"] == ["anthropic"] and r["tally"]["APPROVE"] == 3 and r["tally"]["REVISE"] == 0
      and r["quorum"]["families_present"] == {"anthropic": 3}, json.dumps(r["quorum"])[:300])
for v in ("0", "1"):
    os.environ["WITT_PANEL_MIN_FAMILIES"] = v
    rk = _audit(OPENAI_DOWN)
    _pop_mins()
    check(f"(D) kill-switch WITT_PANEL_MIN_FAMILIES={v}: mismo insumo → APPROVE (regla de f57a3d3), families_gating False, families_ok "
          f"None (null = gating apagado), panel_single_family True DECLARADO, min_families {{value {v}, source env}}, sin panel_incomplete",
          rk["verdict"] == "APPROVE" and rk["quorum"]["families_gating"] is False and rk["quorum"]["families_ok"] is None
          and rk["panel_single_family"] is True and rk["quorum"]["min_families"] == {"value": int(v), "source": "env:WITT_PANEL_MIN_FAMILIES"}
          and "panel_incomplete" not in rk and rk["quorum"]["failed"] == [])
REPEATED = [{"reviewer": "j-c1", "family": "anthropic", "lens": "correctness"},
            {"reviewer": "j-c2", "family": "anthropic", "lens": "correctness"},
            {"reviewer": "j-o1", "family": "openai", "lens": "overclaim"},
            {"reviewer": "j-o2", "family": "openai", "lens": "overclaim"}]
r = _audit(ALL_A, panel=REPEATED)
check("(D) lentes repetidas: 4 válidos, 2 familias pero sólo 2 lentes distintas (< MIN_LENSES 3) → REVISE con failed ['lenses']; "
      "lenses_present con repetición, lenses_valid distintas; n_valid_ok y families_ok True",
      r["verdict"] == "REVISE" and r["panel_incomplete_reasons"] == ["lenses"] and r["quorum"]["lenses_ok"] is False
      and r["lenses_valid"] == ["correctness", "overclaim"] and r["quorum"]["lenses_present"] == ["correctness", "correctness", "overclaim", "overclaim"]
      and r["quorum"]["n_valid_ok"] is True and r["quorum"]["families_ok"] is True)
TWO_ONE = {**ALL_A, "overclaim": DOWN, "reproducibility": DOWN}
r_a = _audit(TWO_ONE, min_lenses=0)
r_b = _audit(TWO_ONE)
check("(D) 2 válidos / 1 familia: con min_lenses=0 del llamador → failed ['min_valid','families'] en ORDEN FIJO (min_lenses {0, "
      "'caller'}, lenses_gating False); con el default → ['min_valid','families','lenses']",
      r_a["panel_incomplete_reasons"] == ["min_valid", "families"] and r_a["quorum"]["min_lenses"] == {"value": 0, "source": "caller"}
      and r_a["quorum"]["lenses_gating"] is False and r_a["quorum"]["lenses_ok"] is None
      and r_b["panel_incomplete_reasons"] == ["min_valid", "families", "lenses"] and r_b["verdict"] == r_a["verdict"] == "REVISE")
UNKNOWN_SEAT = LEGACY_PANEL[:3] + [{"reviewer": "llama-9", "family": "unknown", "lens": "reproducibility"}]
r = _audit(ALL_A, panel=UNKNOWN_SEAT)
check("(D) familia 'unknown' NO cuenta como familia válida (families_valid ['anthropic'] → failed ['families']) pero se VE en "
      "families_present {anthropic 3, unknown 1}: nada se esconde, nada se acredita",
      r["families_valid"] == ["anthropic"] and r["quorum"]["families_present"] == {"anthropic": 3, "unknown": 1}
      and r["panel_incomplete_reasons"] == ["families"] and r["n_valid"] == 4)
r_c1 = _audit(OPENAI_DOWN, min_families=1)
r_c3 = _audit(ALL_A, min_families=3)
check("(D) min_families del llamador: =1 → source 'caller', gating False → APPROVE con OpenAI caído; =3 → families_ok False → "
      "['families'] aunque las 4 lentes votaron",
      r_c1["quorum"]["min_families"] == {"value": 1, "source": "caller"} and r_c1["verdict"] == "APPROVE"
      and r_c3["quorum"]["min_families"] == {"value": 3, "source": "caller"} and r_c3["panel_incomplete_reasons"] == ["families"])
os.environ["WITT_PANEL_MIN_FAMILIES"], os.environ["WITT_PANEL_MIN_LENSES"] = "abc", "-3"
r_bad = _audit(ALL_A)
os.environ["WITT_PANEL_MIN_LENSES"] = ""
r_empty = _audit(ALL_A)
_pop_mins()
check("(D) env basura/negativa → default DECLARADO: MIN_FAMILIES='abc' → {2, default-invalid-env}, MIN_LENSES='-3' → {3, "
      "default-invalid-env}; MIN_LENSES='' → {3, default-unset}",
      r_bad["quorum"]["min_families"] == {"value": 2, "source": "default-invalid-env:WITT_PANEL_MIN_FAMILIES"}
      and r_bad["quorum"]["min_lenses"] == {"value": 3, "source": "default-invalid-env:WITT_PANEL_MIN_LENSES"}
      and r_empty["quorum"]["min_lenses"] == {"value": 3, "source": "default-unset:WITT_PANEL_MIN_LENSES"})

# =====================================================================================================================
# 3. Filas 1.10, attempts (tres estados), panel_source (K), panel_origin, duplicados, resolución EN LA LLAMADA
# =====================================================================================================================
r = ca.audit(CLAIM, EVID, caller=caller_3tuple(ALL_A))
c_row, p_row = r["panel"][0], r["panel"][3]
check("(D/A) filas del panel de la TABLA (g2): correctness {reviewer = default g2, family_source 'table', api 'anthropic-messages', "
      "api_source 'table', reviewer_source 'default:g2-2026-09', max_tokens 4000}; reproducibility {api 'openai-chat-completions', "
      "max_tokens None (tope del transporte)}",
      c_row["reviewer"] == G2["judge.correctness"] and c_row["family_source"] == "table" and c_row["api"] == "anthropic-messages"
      and c_row["api_source"] == "table" and c_row["reviewer_source"] == "default:g2-2026-09" and c_row["max_tokens"] == 4000
      and p_row["reviewer"] == G2["judge.reproducibility"] and p_row["api"] == "openai-chat-completions" and p_row["max_tokens"] is None,
      json.dumps({k: c_row[k] for k in ("reviewer",) + NEW_ROW}))
check("(B) caller 3-tupla → attempts[0] lleva model_reported (lo que la API dijo) y api; caller 2-tupla (f57a3d3) → esas llaves "
      "AUSENTES (ausente ≠ null); intento errado con RuntimeError pelón → error_kind 'unclassified'",
      c_row["attempts"][0]["model_reported"] == G2["judge.correctness"] + "-20260901"
      and c_row["attempts"][0]["api"] == "anthropic-messages"
      and all("model_reported" not in a and "api" not in a for row in _full_all_a["panel"] for a in row["attempts"])
      and _full_two_down["panel"][1]["attempts"][0]["error_kind"] == "unclassified")
r_leg = _audit(ALL_A, panel=LEGACY_PANEL)
lrow = r_leg["panel"][0]
check("(D) panel LEGADO (reviewer/family/lens): family_source 'caller', api inferido ('anthropic-messages'), api_source "
      "'inferred-from-family', reviewer_source 'caller', max_tokens None; panel_origin 'caller'",
      lrow["family_source"] == "caller" and lrow["api"] == "anthropic-messages" and lrow["api_source"] == "inferred-from-family"
      and lrow["reviewer_source"] == "caller" and lrow["max_tokens"] is None and r_leg["panel_origin"] == "caller")
ps = ca.audit(CLAIM, EVID, caller=caller_factory(ALL_A), directives=[{"niche": "N3", "lens": "extra"}])
check("(K) audit.panel_source EXACTO == models.panel_source(): {generation 'g2-2026-09', table_version, panel_signature (16 hex), "
      "directives_state 'empty-until-ADR-0082', council_hook {state 'not-available (ADR-0082)', accepts, lens_scope 'global'}, "
      "lens_charges_source 'composite_auditor._LENS_CHARGES'}; `directives` se acepta y se IGNORA; panel_origin 'models.panel(directives)'",
      ps["panel_source"] == models.panel_source() and ps["panel_source"] == {
          "generation": "g2-2026-09", "table_version": models.MODELS_TABLE_VERSION,
          "panel_signature": ps["panel_source"]["panel_signature"], "directives_state": "empty-until-ADR-0082",
          "council_hook": {"state": "not-available (ADR-0082)", "accepts": "directives[] → asientos/lentes por nicho",
                           "lens_scope": "global"},
          "lens_charges_source": "composite_auditor._LENS_CHARGES"}
      and len(ps["panel_source"]["panel_signature"]) == 16 and int(ps["panel_source"]["panel_signature"], 16) >= 0
      and ps["panel_origin"] == "models.panel(directives)" and ps["verdict"] == r["verdict"] == "APPROVE"
      and all(l in ca._LENS_CHARGES for l in models.LENSES))
os.environ["WITT_JUDGE_GROUNDING"] = G2["judge.overclaim"]
r_dup = _audit(ALL_A)
os.environ.pop("WITT_JUDGE_GROUNDING", None)
check("(D/E) frontera declarada: el sucesor de haiku en evidence-grounding (mismo modelo que overclaim) → panel_duplicate_models "
      "[<modelo>], lenses_valid 4, families_valid 2 → APPROVE; la fila trae reviewer_source 'env:WITT_JUDGE_GROUNDING'",
      r_dup["panel_duplicate_models"] == [G2["judge.overclaim"]] and r_dup["n_lenses_valid"] == 4 and r_dup["n_families_valid"] == 2
      and r_dup["verdict"] == "APPROVE" and r_dup["panel"][2]["reviewer_source"] == "env:WITT_JUDGE_GROUNDING"
      and r["panel_duplicate_models"] == [])
os.environ["WITT_MODEL_GENERATION"] = "g1-2026-08"
r_g1 = _audit(ALL_A)
os.environ.pop("WITT_MODEL_GENERATION", None)
r_g2 = _audit(ALL_A)
check("(A) panel=None se resuelve EN LA LLAMADA, sin reimportar: con WITT_MODEL_GENERATION=g1 los reviewers son los de f57a3d3, "
      "max_tokens 1200 (tope g1) y reviewer_source 'default:g1-2026-08'; al quitar la env, la siguiente llamada vuelve a g2 (4000)",
      [x["reviewer"] for x in r_g1["panel"]] == [m["reviewer"] for m in LEGACY_PANEL] and r_g1["panel"][0]["max_tokens"] == 1200
      and r_g1["panel"][0]["reviewer_source"] == "default:g1-2026-08" and r_g1["panel_source"]["generation"] == "g1-2026-08"
      and r_g2["panel"][0]["reviewer"] == G2["judge.correctness"] and r_g2["panel"][0]["max_tokens"] == 4000)
check("(A) DEFAULT_PANEL = snapshot DOCUMENTAL models.panel(env={}, today=MODEL_TABLE_AS_OF): misma forma PanelMember, sin leer "
      "env en import (reproducibility = default g2 aunque la env cambie después); audit() no lo usa",
      ca.DEFAULT_PANEL == models.panel(env={}, today=models.MODEL_TABLE_AS_OF)
      and ca.DEFAULT_PANEL[3]["reviewer"] == G2["judge.reproducibility"]
      and set(models.PANEL_MEMBER_FIELDS) == set(ca.DEFAULT_PANEL[0]))

# =====================================================================================================================
# 4. apply_to_bundle copia las llaves 1.10 y re-sella (answer_pipeline REAL)
# =====================================================================================================================
try:
    from lib import answer_pipeline as _ap  # noqa: E402
    _ap_kind = "lib.answer_pipeline REAL"
except Exception as e:  # pragma: no cover — declarado, no disimulado
    _ap = None
    _ap_kind = f"NO importable ({type(e).__name__}: {str(e)[:80]})"
if _ap is not None:
    r_ok = _audit(ALL_A)
    r_st = _audit(OPENAI_DOWN)
    b_ok = ca.apply_to_bundle({"run_id": "smoke-ok", "question": "q"}, r_ok, ["CORPUS-2026-0001"], answer_pipeline_module=_ap)
    b_st = ca.apply_to_bundle({"run_id": "smoke-st", "question": "q"}, r_st, ["CORPUS-2026-0001"], answer_pipeline_module=_ap)

    def _sha(b):
        return hashlib.sha256(json.dumps({k: v for k, v in b.items() if k != "bundle_identity"}, sort_keys=True,
                                         ensure_ascii=False).encode("utf-8")).hexdigest()
    check(f"apply_to_bundle ({_ap_kind}): bundle['audit'] gana families_valid/n_families_valid/lenses_valid/n_lenses_valid/"
          "panel_single_family/quorum/panel_duplicate_models/panel_origin/panel_source/failure_kinds_vocabulary; APPROVE → "
          "AUDIT_APPROVED y SIN panel_incomplete_reasons; identidad re-sellada (sha256 del payload sin bundle_identity)",
          all(k in b_ok["audit"] for k in ("families_valid", "n_families_valid", "lenses_valid", "n_lenses_valid", "panel_single_family",
                                          "quorum", "panel_duplicate_models", "panel_origin", "panel_source", "failure_kinds_vocabulary"))
          and b_ok["audit"]["quorum"] == r_ok["quorum"] and b_ok["decision_state"]["state"] == "AUDIT_APPROVED"
          and "panel_incomplete_reasons" not in b_ok["audit"] and "panel_incomplete" not in b_ok["audit"]
          and b_ok["bundle_identity"]["sha256"] == _sha(b_ok))
    check("apply_to_bundle: REVISE estructural → AUDIT_REJECTED con panel_incomplete True + panel_incomplete_reasons ['families'] "
          "en bundle['audit']; note 'composite-auditor Mode 1: REVISE (valid 3/4, …)' como hoy; identidad re-sellada",
          b_st["decision_state"]["state"] == "AUDIT_REJECTED" and b_st["audit"]["panel_incomplete"] is True
          and b_st["audit"]["panel_incomplete_reasons"] == ["families"]
          and b_st["audit"]["note"].startswith("composite-auditor Mode 1: REVISE (valid 3/4, ")
          and b_st["bundle_identity"]["sha256"] == _sha(b_st))
else:
    check(f"apply_to_bundle: answer_pipeline {_ap_kind}", False)
    check("apply_to_bundle: (no medido)", False)

# =====================================================================================================================
# 5. Contrato S2 (firmas) y docstring corregido
# =====================================================================================================================
check("contrato S2: audit(claim, evidence, deterministic_checks=None, required_because='', panel=None, caller=None, min_valid=3, "
      "judge_retries=None, min_families=None, min_lenses=None, directives=None); _default_caller(member, system, user_text, tool=None); "
      "_anthropic_tool_call(..., max_tokens=1200, effort=None, return_meta=False, tools=None) (ADR-0082 D.1: `tools=` aditivo al final)",
      list(inspect.signature(ca.audit).parameters) == ["claim", "evidence", "deterministic_checks", "required_because", "panel",
                                                        "caller", "min_valid", "judge_retries", "min_families", "min_lenses",
                                                        "directives"]
      and list(inspect.signature(ca._default_caller).parameters) == ["member", "system", "user_text", "tool"]
      and list(inspect.signature(ca._anthropic_tool_call).parameters) == ["model", "system", "user_text", "tool", "timeout", "retries",
                                                                           "max_tokens", "effort", "return_meta", "tools"]
      and inspect.signature(ca._anthropic_tool_call).parameters["tools"].default is None
      and inspect.signature(ca._anthropic_tool_call).parameters["return_meta"].default is False
      and inspect.signature(ca._openai_responses_call).parameters["retries"].default == 1)
check("docstring corregido: la promesa de ADR-0080 L41 ('families_valid / lenses_valid are NOT here') ya no está; el módulo declara "
      "ADR-0081 (C, D, K) y que el panel sale de la tabla EN LA LLAMADA",
      "are NOT here" not in ca.__doc__ and "ADR-0081" in ca.__doc__ and "models.panel()" in ca.__doc__
      and "Fable" in ca.__doc__ and "EXCLUDED" in ca.__doc__)
check("(M.3) urllib.request.urlopen REAL bloqueado: 0 llamadas en todo el gate; 'openai' jamás importado aquí",
      _NET_CALLS == [] and "openai" not in sys.modules)

# =====================================================================================================================
# 6. ADR-0082 (D.1) — el caller: tools=, system lista, semáforo de PROCESO, Retry-After con tope, attempts/usage_prior_attempts
#    (urlopen FAKE = transporte simulado, cero red; _backoff GRABADO, no se espera)
# =====================================================================================================================
import io as _io  # noqa: E402
import threading as _threading  # noqa: E402
import time as _time  # noqa: E402
import urllib.error as _uerr  # noqa: E402

_D1_CALLS = []
_D1_WAITS = []
_orig_backoff, _orig_inflight = ca._backoff, ca._INFLIGHT
ca._backoff = lambda seconds: _D1_WAITS.append(seconds)


class _D1Resp:
    def __init__(self, payload):
        self._p = payload

    def read(self):
        return json.dumps(self._p).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _d1_payload(tool_name, tool_input, usage=None):
    return {"id": "msg_d1", "model": _MODEL_D1 + "-20260901", "stop_reason": "tool_use",
            "content": [{"type": "tool_use", "id": "tu", "name": tool_name, "input": tool_input}],
            "usage": usage or {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 700, "cache_read_input_tokens": 0}}


def _d1_urlopen(script):
    script = list(script)

    def _fake(req, timeout=None):
        _D1_CALLS.append({"body": json.loads(req.data.decode("utf-8")), "timeout": timeout})
        nxt = script.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return _D1Resp(nxt)
    return _fake


def _d1_http(code, headers=None, body=b"err"):
    return _uerr.HTTPError(ca.ANTHROPIC_URL, code, "x", headers if headers is not None else {}, _io.BytesIO(body))


def _d1_raises(fn):
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        return e
    return None


_VOK = {"verdict": "APPROVE", "confidence": 0.9, "issues": [], "rationale": "ok"}
_TOOL_B = {"name": "other_tool", "description": "b", "input_schema": {"type": "object", "properties": {"x": {"type": "string"}},
                                                                     "required": ["x"]}}
_MODEL_D1 = models.GENERATIONS["g2-2026-09"]["defaults"]["judge.correctness"]
os.environ["ANTHROPIC_API_KEY"] = "smoke-fake-anthropic-key-not-a-secret"
try:
    urllib.request.urlopen = _d1_urlopen([_d1_payload(ca.VERDICT_TOOL["name"], _VOK)])
    out, usage = ca._anthropic_tool_call(_MODEL_D1, "S", "U")
    body_str = _D1_CALLS[-1]["body"]
    check("(D.1) system str, sin tools= -> cuerpo BYTE A BYTE el de f57a3d3: {model, max_tokens 1200, system 'S', messages[1], tools [VERDICT_TOOL], "
          "tool_choice forzado}, sin output_config; 2-tupla intacta con usage crudo (cache_* incluidos)",
          body_str == {"model": _MODEL_D1, "max_tokens": 1200, "system": "S", "messages": [{"role": "user", "content": "U"}],
                       "tools": [ca.VERDICT_TOOL], "tool_choice": {"type": "tool", "name": ca.VERDICT_TOOL["name"]}}
          and out == _VOK and usage["cache_creation_input_tokens"] == 700, json.dumps(list(body_str)))
    blocks = [{"type": "text", "text": "A", "cache_control": {"type": "ephemeral"}},
              {"type": "text", "text": "B", "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
    urllib.request.urlopen = _d1_urlopen([_d1_payload(_TOOL_B["name"], {"x": "1"})])
    out, usage, meta = ca._anthropic_tool_call(_MODEL_D1, blocks, "U", tool=_TOOL_B, tools=[ca.VERDICT_TOOL, _TOOL_B], max_tokens=4000,
                                              effort="medium", return_meta=True, timeout=77)
    body_l = _D1_CALLS[-1]["body"]
    check("(D.1) system LISTA de bloques -> viaja tal cual (cache_control x2, ttl 1h en el 2o); tools= lista completa [VERDICT_TOOL, other_tool] "
          "+ tool_choice forzado al `tool`; max_tokens 4000; output_config.effort medium; timeout al socket; meta {attempts 1, queue_wait_s, "
          "model_reported}; usage numerico conserva cache_creation",
          body_l["system"] == blocks and body_l["tools"] == [ca.VERDICT_TOOL, _TOOL_B] and body_l["tool_choice"] == {"type": "tool", "name": "other_tool"}
          and body_l["max_tokens"] == 4000 and body_l["output_config"] == {"effort": "medium"} and _D1_CALLS[-1]["timeout"] == 77
          and out == {"x": "1"} and meta["attempts"] == 1 and isinstance(meta["queue_wait_s"], float) and "usage_prior_attempts" not in meta
          and usage["cache_creation_input_tokens"] == 700 and meta["model_reported"].startswith(_MODEL_D1))
    e = _d1_raises(lambda: ca._anthropic_tool_call(_MODEL_D1, "S", "U", tool=_TOOL_B, tools=[ca.VERDICT_TOOL]))
    check("(D.1) `tool` forzado que NO esta en tools= -> ValueError ANTES de cualquier llamada (cero red)",
          isinstance(e, ValueError) and "not in tools" in str(e))
    # Retry-After
    n0, w0 = len(_D1_CALLS), len(_D1_WAITS)
    urllib.request.urlopen = _d1_urlopen([_d1_http(429, {"Retry-After": "7"}), _d1_payload(ca.VERDICT_TOOL["name"], _VOK)])
    out, usage, meta = ca._anthropic_tool_call(_MODEL_D1, "S", "U", return_meta=True)
    check("(D.1) http-429 con Retry-After: 7 -> se espera 7 s (reloj grabado, no real), reintento OK: meta.retry_after_honored_s 7.0, attempts 2, "
          "2 llamadas",
          _D1_WAITS[w0:] == [7.0] and len(_D1_CALLS) - n0 == 2 and meta["retry_after_honored_s"] == 7.0 and meta["attempts"] == 2 and out == _VOK,
          f"waits={_D1_WAITS[w0:]}")
    n0, w0 = len(_D1_CALLS), len(_D1_WAITS)
    urllib.request.urlopen = _d1_urlopen([_d1_http(529, {"Retry-After": "900"}), _d1_http(529, {"Retry-After": "900"})])
    e = _d1_raises(lambda: ca._anthropic_tool_call(_MODEL_D1, "S", "U"))
    check("(D.1) http-529 con Retry-After: 900 -> tope WITT_ANTHROPIC_RETRY_AFTER_CAP_S=30 (espera 30); 2o 529 -> CallerError kind http-529 con "
          ".retry_after 900.0 (crudo) y meta.attempts 2",
          _D1_WAITS[w0:] == [30.0] and isinstance(e, ca.CallerError) and e.kind == "http-529" and e.retry_after == 900.0
          and e.meta["attempts"] == 2 and len(_D1_CALLS) - n0 == 2, f"waits={_D1_WAITS[w0:]}")
    n0, w0 = len(_D1_CALLS), len(_D1_WAITS)
    urllib.request.urlopen = _d1_urlopen([_d1_http(429), _d1_http(500, {"Retry-After": "5"})])
    e = _d1_raises(lambda: ca._anthropic_tool_call(_MODEL_D1, "S", "U"))
    check("(D.1) 429 SIN cabecera -> backoff de hoy 2*(0+1) = 2; el 500 final NO lee Retry-After (kind http-500, retry_after None); "
          "retries=1 -> 2 llamadas",
          _D1_WAITS[w0:] == [2] and isinstance(e, ca.CallerError) and e.kind == "http-500" and e.retry_after is None and len(_D1_CALLS) - n0 == 2)
    n0, w0 = len(_D1_CALLS), len(_D1_WAITS)
    urllib.request.urlopen = _d1_urlopen([_d1_http(429, {"Retry-After": "Thu, 01 Jan 2009 00:00:00 GMT"}), _d1_payload(ca.VERDICT_TOOL["name"], _VOK)])
    ca._anthropic_tool_call(_MODEL_D1, "S", "U")
    check("(D.1) Retry-After como HTTP-date en el pasado -> 0 s (nunca negativo); fecha ilegible -> None -> backoff de hoy; cabecera en minusculas tambien se lee",
          _D1_WAITS[w0:] == [0.0] and ca._retry_after_seconds({"Retry-After": "not a date"}) is None
          and ca._retry_after_seconds({}) is None and ca._retry_after_seconds({"retry-after": "3"}) == 3.0)
    # attempts / usage_prior_attempts (contenido)
    n0 = len(_D1_CALLS)
    urllib.request.urlopen = _d1_urlopen([
        {"id": "m", "model": _MODEL_D1, "stop_reason": "end_turn", "content": [{"type": "text", "text": "hola"}],
         "usage": {"input_tokens": 100, "output_tokens": 20}},
        _d1_payload(ca.VERDICT_TOOL["name"], _VOK, usage={"input_tokens": 100, "output_tokens": 30})])
    out, usage, meta = ca._anthropic_tool_call(_MODEL_D1, "S", "U", return_meta=True)
    check("(D.1) reintento de CONTENIDO (no-function-call -> ok): meta.attempts 2 y meta.usage_prior_attempts [{100, 20}] - lo que la API cobro "
          "en el intento fallido viaja (el consejo lo suma); usage final 100/30",
          meta["attempts"] == 2 and meta["usage_prior_attempts"] == [{"input_tokens": 100, "output_tokens": 20}]
          and usage == {"input_tokens": 100, "output_tokens": 30} and len(_D1_CALLS) - n0 == 2)
    # semaforo de proceso
    _sem_state = {"cur": 0, "max": 0}
    _sem_lock = _threading.Lock()

    def _slow_urlopen(req, timeout=None):
        with _sem_lock:
            _sem_state["cur"] += 1
            _sem_state["max"] = max(_sem_state["max"], _sem_state["cur"])
        _time.sleep(0.05)
        with _sem_lock:
            _sem_state["cur"] -= 1
        return _D1Resp(_d1_payload(ca.VERDICT_TOOL["name"], _VOK))
    urllib.request.urlopen = _slow_urlopen
    ca._INFLIGHT = _threading.BoundedSemaphore(2)
    _metas = []
    _ts = [_threading.Thread(target=lambda: _metas.append(ca._anthropic_tool_call(_MODEL_D1, "S", "U", return_meta=True)[2])) for _ in range(5)]
    for t in _ts:
        t.start()
    for t in _ts:
        t.join(10)
    check("(D.1) semaforo de PROCESO: con _INFLIGHT=2 y 5 hilos, maximo 2 dentro de urlopen a la vez (contador medido); 5 respuestas; algun "
          "meta.queue_wait_s > 0 (alguien espero)",
          _sem_state["max"] == 2 and len(_metas) == 5 and any(m["queue_wait_s"] > 0 for m in _metas), str(_sem_state))
    check("(D.1) _INFLIGHT por default: BoundedSemaphore(8) con fuente '...WITT_ANTHROPIC_MAX_INFLIGHT' y regla declarada; retry_after_cap() "
          "default 30; inflight_limit tolerante a basura ('zz' -> 8) y a valor valido ('3' -> 3)",
          ca._INFLIGHT_LIMIT == 8 and ca._INFLIGHT_SOURCE.endswith("WITT_ANTHROPIC_MAX_INFLIGHT") and "urlopen" in ca._INFLIGHT_RULE
          and ca.retry_after_cap()[0] == 30 and ca.inflight_limit({"WITT_ANTHROPIC_MAX_INFLIGHT": "zz"})[0] == 8
          and ca.inflight_limit({"WITT_ANTHROPIC_MAX_INFLIGHT": "3"})[0] == 3)
finally:
    os.environ["ANTHROPIC_API_KEY"] = ""
    urllib.request.urlopen = _blocked_urlopen
    ca._backoff, ca._INFLIGHT = _orig_backoff, _orig_inflight
r_dir = _audit(ALL_A, directives=[{"family": "zfin", "requirement_id": "req-x"}])
check("(K) audit(directives=[...]) sigue IGNORANDOLAS: panel_source.council_hook.state 'not-available (ADR-0082)' y directives_state "
      "'empty-until-ADR-0082' (las lentes por nicho NO entran en ADR-0082; ADR propio)",
      r_dir["panel_source"]["council_hook"]["state"] == "not-available (ADR-0082)"
      and r_dir["panel_source"]["directives_state"] == "empty-until-ADR-0082" and r_dir["verdict"] == "APPROVE")
check("(M.3 bis) tras la seccion D.1: urlopen REAL sigue bloqueado y con 0 llamadas", _NET_CALLS == [])

npass = sum(CHECKS)
print("\n== %d/%d PASS ==" % (npass, len(CHECKS)))
sys.exit(0 if npass == len(CHECKS) else 1)

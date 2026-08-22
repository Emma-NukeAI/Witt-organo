"""
ab_trapped_scalar.py — A/B en vivo del "escalar atrapado" (PENDIENTES DE BACK item 2; ADR-0065).

El fenómeno (ADR-0057, 6/6 corridas de producción + 7/8 pasadas locales con usage vivo): Opus 4.8,
bajo tool_choice forzado con SYNTH_TOOL, emite la transición al siguiente parámetro en sintaxis XML
legada DENTRO del string de `direct_answer` (`…</parameter><parameter name="confidence">0.86`), y
`confidence` llega None; `recover_trapped_params` lo rescata con procedencia declarada en cada corrida.

Este script mide la CAUSA con dos brazos, misma pregunta y misma evidencia REALES (una corrida del
loop local), n llamadas por brazo, intercaladas:

  A (baseline)  = runs.SYNTH_TOOL verbatim + runs.synth_system("pass1") — lo que corre producción.
  B (candidato) = mismos campos y mismos required, con el campo largo (`direct_answer`) EMITIDO AL
                  FINAL (los escalares/enums salen antes de la prosa: el descarrilamiento ocurre al
                  salir del string largo — si es el último campo, no queda nada que tragarse) +
                  descripción anti-artefacto en el tool y en direct_answer.

Métrica primaria por llamada (PRE-recuperación, sobre el raw): ¿algún string trae `</parameter>` /
`<parameter name=`? ¿`confidence` llegó como campo numérico limpio? Secundaria: valor de confianza
post-recuperación por brazo (vigilar drift de régimen), stop_reason, tokens.

Disciplina §6/§7.9: CADA respuesta cruda se guarda en mcp_cache/ab_trapped_scalar/<ts>/ ANTES de
procesarla. Gasto: ~USD 0.04–0.08 por llamada de Opus (autorizado 2026-06-13; se reporta el total).
Con tasa base ≈7/8 atrapadas, 8/8 limpias en B tiene p≈1e-7 bajo la hipótesis nula — decisivo.

Uso (venv del servicio, NO el del MCP):
  python evaluation/scripts/ab_trapped_scalar.py --n 8
"""
import argparse
import concurrent.futures
import copy
import datetime
import json
import os
import sqlite3
import statistics
import subprocess
import sys
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rag_index" / "query_service"))
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))

DEFAULT_DB = "C:/Users/Emmanuel/dev/.venvs/witt-query-service/backend.db"
DEFAULT_RUN_PREFIX = "ea96d70e"   # la corrida wt1a del A/B de ADR-0059 — reprodujo el trap 2/2 pasadas


def _load_deploy_env():
    """Solo ANTHROPIC_API_KEY hace falta; mismo patrón no-override que server._load_local_secrets."""
    envf = ROOT / ".secrets" / "deploy.env"
    if not envf.exists():
        return
    for line in envf.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_deploy_env()
import runs as runs_mod  # noqa: E402  (importa lib/* del repo; sin red al importar)
from lib import composite_auditor  # noqa: E402

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
TRAP_MARKERS = ("</parameter>", "<parameter name=")


def candidate_tool(base):
    """Brazo B: MISMOS campos, MISMO required — cambia solo el ORDEN de emisión (el campo largo al
    final) y las descripciones anti-artefacto. Si gana, esta transformación se aplica tal cual a
    runs.SYNTH_TOOL (cero impacto de contrato: nombres y required intactos)."""
    t = copy.deepcopy(base)
    props = t["input_schema"]["properties"]
    order = ["confidence", "confidence_by_subclaim", "absence_kind", "framework_applied",
             "framework_criterion", "framework_reason", "search_query_en", "gap_flags",
             "alternatives_considered", "evidence_cited", "direct_answer"]
    assert set(order) == set(props), f"drift de schema: {sorted(set(props) ^ set(order))}"
    t["input_schema"]["properties"] = {k: props[k] for k in order}
    t["description"] += (" Emit EVERY field as its own tool parameter. A string value carries ONLY "
                         "its own content — never another field's name or value, never any markup.")
    t["input_schema"]["properties"]["direct_answer"] = {
        "type": "string",
        "description": ("The answer prose for the medical team, and NOTHING else. Every other field "
                        "(confidence, citations, flags, frameworks) already has its own parameter "
                        "above — none of them, and no serialization syntax, may appear inside this "
                        "text. End the answer with a period.")}
    return t


def load_case(db_path, run_prefix):
    cx = sqlite3.connect(db_path)
    cx.row_factory = sqlite3.Row
    row = cx.execute("select run_id, question, bundle_json from runs where run_id like ? "
                     "and bundle_json is not null", (run_prefix + "%",)).fetchone()
    if row is None:
        sys.exit(f"[ab] no hay corrida con bundle que empiece con {run_prefix!r} en {db_path}")
    bundle = json.loads(row["bundle_json"])
    evidence = runs_mod._compact_evidence(bundle, include_path_b=False)   # la vista pass1 (DI-only)
    return row["run_id"], row["question"], evidence


SYSTEM_FORMAT_ANCHOR = (
    "\n\nTOOL-CALL FORMAT (hard rule): the tool input is ONE JSON object; every schema field is its "
    "own JSON key with a JSON value. NEVER write XML-style parameter tags — no '</parameter>', no "
    "'<parameter name=...>' — anywhere in the output, and especially never inside a string value. "
    "When a string field's content is finished, close the JSON string and emit the next field as a "
    "JSON key.")

# --- brazo D: elicitación dedicada del escalar (estructural, no prompting) ---------------------------
# Un tool SIN campos de texto largo: no hay string que contaminar. La confianza se emite DESPUÉS de
# ver la respuesta completa (answer-then-confidence — además el mejor diseño de calibración). Se mide
# sobre respuestas YA cacheadas de rounds previos (cero gasto de síntesis nueva).
# ADOPTADO en producción (ADR-0065): se referencian las definiciones REALES de runs.py — este script
# mide siempre lo que producción corre, jamás una réplica. La lección del round D-1 vive allá: sin la
# cláusula de semántica, |delta| fue 0.75 (el elicitor calificaba la declinación, no la suficiencia).
CONF_TOOL = runs_mod.CONF_TOOL
ELICIT_SYSTEM = runs_mod.ELICIT_SYSTEM


def _post(body, timeout=120):
    headers = {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": ANTHROPIC_VERSION,
               "content-type": "application/json"}
    req = urllib.request.Request(ANTHROPIC_URL, data=json.dumps(body).encode("utf-8"),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _tool_input(payload):
    return next((b["input"] for b in payload.get("content", [])
                 if b.get("type") == "tool_use"), None) or {}


def elicit_one(idx, src_path, question, evidence, out_dir, timeout=120):
    """Una elicitación sobre una respuesta cacheada: reconstruye lo que vio el sintetizador + su
    respuesta (recuperada), llama CONF_TOOL y clasifica trap/valor/delta vs el escalar in-line."""
    payload = json.loads(src_path.read_text(encoding="utf-8"))
    rec = composite_auditor.recover_trapped_params(dict(_tool_input(payload)))
    inline_conf = rec.get("confidence")
    user_text = json.dumps({"question": question, "evidence": evidence,
                            "produced_answer": {"direct_answer": rec.get("direct_answer"),
                                                "gap_flags": rec.get("gap_flags", [])}},
                           ensure_ascii=False, default=str)
    p2 = _post({"model": runs_mod.SYNTH_MODEL, "max_tokens": 300, "system": ELICIT_SYSTEM,
                "messages": [{"role": "user", "content": user_text}],
                "tools": [CONF_TOOL], "tool_choice": {"type": "tool", "name": CONF_TOOL["name"]}},
               timeout=timeout)
    (out_dir / f"raw_elicit_{idx:02d}.json").write_text(
        json.dumps(p2, ensure_ascii=False, indent=1), encoding="utf-8")
    einp = _tool_input(p2)
    trapped = sorted(k for k, v in einp.items()
                     if isinstance(v, str) and any(m in v for m in TRAP_MARKERS))
    conf = einp.get("confidence")
    delta = (round(conf - inline_conf, 3)
             if isinstance(conf, (int, float)) and isinstance(inline_conf, (int, float)) else None)
    return {"src": src_path.name, "idx": idx, "trapped": bool(trapped),
            "clean": isinstance(conf, (int, float)),
            "conf_elicited": conf, "conf_inline": inline_conf, "delta": delta,
            "by_subclaim": bool(einp.get("confidence_by_subclaim")),
            "out_tokens": p2.get("usage", {}).get("output_tokens"),
            "in_tokens": p2.get("usage", {}).get("input_tokens")}


def run_elicitation(src_dirname, question, evidence, workers):
    """Modo D: elicitación dedicada sobre TODOS los raws de un round previo (cero síntesis nueva)."""
    src_dir = ROOT / "mcp_cache" / "ab_trapped_scalar" / src_dirname
    srcs = sorted(src_dir.glob("raw_[ABC]_*.json"))
    if not srcs:
        sys.exit(f"[ab] no hay raws en {src_dir}")
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "mcp_cache" / "ab_trapped_scalar" / f"{ts}_elicit"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(elicit_one, i, p, question, evidence, out_dir): p for i, p in enumerate(srcs)}
        for fut in concurrent.futures.as_completed(futs):
            try:
                r = fut.result()
            except Exception as e:
                r = {"src": futs[fut].name, "error": f"{type(e).__name__}: {str(e)[:160]}"}
            results.append(r)
            tag = ("ERROR " + r["error"]) if "error" in r else \
                  (f"trapped={r['trapped']} clean={r['clean']} conf={r['conf_elicited']} "
                   f"inline={r['conf_inline']} delta={r['delta']}")
            print(f"[D:{r['src']}] {tag}")
    ok = [r for r in results if "error" not in r]
    deltas = [abs(r["delta"]) for r in ok if r["delta"] is not None]
    summary = {"ts": ts, "mode": "elicitation-D", "src_dir": src_dirname, "n": len(srcs),
               "model": runs_mod.SYNTH_MODEL, "git_head": _git_head(),
               "n_ok": len(ok), "n_error": len(results) - len(ok),
               "n_trapped": sum(r["trapped"] for r in ok),
               "n_clean": sum(r["clean"] for r in ok),
               "abs_delta_median": round(statistics.median(deltas), 3) if deltas else None,
               "abs_delta_max": round(max(deltas), 3) if deltas else None,
               "results": ok}
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    print(f"\n== D: ok={summary['n_ok']} err={summary['n_error']} atrapadas={summary['n_trapped']} "
          f"limpias={summary['n_clean']} |delta| mediana={summary['abs_delta_median']} "
          f"max={summary['abs_delta_max']} ==")
    print(f"raws + summary -> {out_dir}")


def one_call(arm, idx, tool, system, user_text, out_dir, timeout=120, temperature=None):
    """UNA llamada forzada (sin retry — medimos la tasa POR LLAMADA). Guarda el raw ANTES de procesar."""
    body = {"model": runs_mod.SYNTH_MODEL, "max_tokens": 2500, "system": system,
            "messages": [{"role": "user", "content": user_text}],
            "tools": [tool], "tool_choice": {"type": "tool", "name": tool["name"]}}
    if temperature is not None:
        body["temperature"] = temperature
    headers = {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": ANTHROPIC_VERSION,
               "content-type": "application/json"}
    req = urllib.request.Request(ANTHROPIC_URL, data=json.dumps(body).encode("utf-8"),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    raw_path = out_dir / f"raw_{arm}_{idx:02d}.json"
    raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    tool_input = next((b["input"] for b in payload.get("content", [])
                       if b.get("type") == "tool_use"), None) or {}
    trapped_fields = sorted(k for k, v in tool_input.items()
                            if isinstance(v, str) and any(m in v for m in TRAP_MARKERS))
    conf_clean = isinstance(tool_input.get("confidence"), (int, float))
    recovered = composite_auditor.recover_trapped_params(dict(tool_input))
    usage = payload.get("usage", {})
    return {"arm": arm, "idx": idx,
            "trapped": bool(trapped_fields), "trapped_fields": trapped_fields,
            "confidence_clean": conf_clean,
            "confidence_final": recovered.get("confidence"),
            "recovered_fields": recovered.get("_recovered_fields", []),
            "stop_reason": payload.get("stop_reason"),
            "out_tokens": usage.get("output_tokens"), "in_tokens": usage.get("input_tokens"),
            "raw": raw_path.name}


def main():
    ap = argparse.ArgumentParser(description="A/B del escalar atrapado (ADR-0065)")
    ap.add_argument("--n", type=int, default=8, help="llamadas por brazo")
    ap.add_argument("--arms", default="A,B", help="brazos a correr, p.ej. 'C' o 'A,B,C'")
    ap.add_argument("--elicit-from", default=None,
                    help="modo D: nombre del dir de un round previo (bajo mcp_cache/ab_trapped_scalar/) "
                         "cuyos raws se re-usan como respuestas — mide la elicitación dedicada")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--run-prefix", default=DEFAULT_RUN_PREFIX)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("[ab] ANTHROPIC_API_KEY ausente (ni en env ni en .secrets/deploy.env)")

    run_id, question, evidence = load_case(args.db, args.run_prefix)
    if args.elicit_from:
        run_elicitation(args.elicit_from, question, evidence, args.workers)
        return
    base_system = runs_mod.synth_system("pass1")       # el string de PRODUCCIÓN, no una réplica
    user_text = json.dumps({"question": question, "evidence": evidence},
                           ensure_ascii=False, default=str)
    # brazo: (tool, system, temperature). A = producción verbatim. B = reorden+descripciones.
    # C = B + ancla de formato a nivel SYSTEM. Hallazgos del round 1: el orden del schema NO controla
    # la emisión (direct_answer salió primero en 16/16) y `temperature` está DEPRECADO para Opus 4.8
    # (400 medido: "`temperature` is deprecated for this model") — esa palanca no existe; queda la
    # autoridad del system prompt sobre el formato.
    arms = {"A": (runs_mod.SYNTH_TOOL, base_system, None),
            "B": (candidate_tool(runs_mod.SYNTH_TOOL), base_system, None),
            "C": (candidate_tool(runs_mod.SYNTH_TOOL), base_system + SYSTEM_FORMAT_ANCHOR, None)}
    run_arms = [a.strip().upper() for a in args.arms.split(",") if a.strip()]

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "mcp_cache" / "ab_trapped_scalar" / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    jobs = [(arm, i) for i in range(args.n) for arm in run_arms]     # intercalado
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {}
        for arm, i in jobs:
            tool, system, temp = arms[arm]
            futs[ex.submit(one_call, arm, i, tool, system, user_text, out_dir,
                           temperature=temp)] = (arm, i)
        for fut in concurrent.futures.as_completed(futs):
            arm, i = futs[fut]
            try:
                r = fut.result()
            except Exception as e:
                r = {"arm": arm, "idx": i, "error": f"{type(e).__name__}: {str(e)[:160]}"}
            results.append(r)
            tag = ("ERROR " + r["error"]) if "error" in r else \
                  (f"trapped={r['trapped']} conf_clean={r['confidence_clean']} "
                   f"conf={r['confidence_final']} stop={r['stop_reason']} out={r['out_tokens']}")
            print(f"[{r['arm']}#{r['idx']:02d}] {tag}")

    summary = {"ts": ts, "question_run": run_id, "model": runs_mod.SYNTH_MODEL,
               "n_per_arm": args.n, "git_head": _git_head(), "arms": {}}
    for arm in run_arms:
        rows = [r for r in results if r["arm"] == arm and "error" not in r]
        errs = [r for r in results if r["arm"] == arm and "error" in r]
        confs = [r["confidence_final"] for r in rows if isinstance(r["confidence_final"], (int, float))]
        summary["arms"][arm] = {
            "n_ok": len(rows), "n_error": len(errs),
            "n_trapped": sum(r["trapped"] for r in rows),
            "n_confidence_clean": sum(r["confidence_clean"] for r in rows),
            "confidence_median": round(statistics.median(confs), 3) if confs else None,
            "confidence_values": confs,
            "out_tokens": [r["out_tokens"] for r in rows],
            "stop_reasons": sorted({str(r["stop_reason"]) for r in rows}),
        }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    print("\n== RESUMEN ==")
    for arm, s in summary["arms"].items():
        print(f"  {arm}: ok={s['n_ok']} err={s['n_error']} atrapadas={s['n_trapped']} "
              f"conf_limpia={s['n_confidence_clean']} mediana_conf={s['confidence_median']}")
    print(f"raws + summary -> {out_dir}")


def _git_head():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True).stdout.strip()
    except Exception:
        return None


if __name__ == "__main__":
    main()

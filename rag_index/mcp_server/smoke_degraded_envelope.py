"""smoke_degraded_envelope.py — regresion determinista del sobre {degraded, n_hits, hits} (ADR-0043/0044).

LA regresion que cubre: forzar el fallo del denso, consultar algo que da 0 hits, y afirmar que el sobre
reporta degradado. Antes de ADR-0043 el marcador se estampaba iterando los hits — con lista vacia el for
no entraba y "degradado y vacio" era byte-identico a "sano y vacio" (dos conclusiones OPUESTAS: hueco real
de la DI vs. buscador roto). Es el trap del 2026-07-18/19 reintroducido en el borde del resultado vacio.

100% offline y deterministico: el backend se monkeypatchea (rag_backend.query / query_sparse), asi que no
hay red, no hay Neo4j, no hay spend de OpenAI. Exit 0 = todo PASS.

Corre:  python rag_index/mcp_server/smoke_degraded_envelope.py
"""
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import server  # noqa: E402
from lib import rag_backend, answer_pipeline  # noqa: E402
from lib.rag_backend import Hit, HitList  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


def _hit(doc_id="DOC-1", score=0.9):
    return Hit(doc_id=doc_id, type="dataset", score=score, text="synthetic", metadata={})


_orig_query, _orig_sparse = rag_backend.query, rag_backend.query_sparse
_orig_path_b = answer_pipeline.path_b

try:
    # ---- 1. LA regresion: denso caido + 0 hits -> el sobre AUN reporta degradado -------------------
    def _dense_down(text, k=5):
        raise RuntimeError("forced dense failure (smoke)")
    rag_backend.query = _dense_down
    rag_backend.query_sparse = lambda text, k=5: HitList([], degraded="sparse-by-config")
    r = server._query("query with zero hits", 3)
    check("0-hits degradado: el sobre reporta degradado (no se pierde)",
          isinstance(r, dict) and r.get("degraded") == "sparse" and r.get("n_hits") == 0 and r.get("hits") == [],
          f"degraded={r.get('degraded')!r} n_hits={r.get('n_hits')}")

    # ---- 2. sobre con hits + estampado por-hit conservado (compat) --------------------------------
    rag_backend.query_sparse = lambda text, k=5: HitList([_hit()], degraded="sparse-by-config")
    r = server._query("query with one hit", 3)
    check("sobre con hits: marcador en sobre Y en metadata por-hit (compat)",
          r.get("degraded") == "sparse" and r.get("n_hits") == 1
          and r["hits"][0]["metadata"].get("degraded") == "sparse")

    # ---- 3. camino semantico sano: degraded None en el sobre --------------------------------------
    rag_backend.query = lambda text, k=5: HitList([_hit()], degraded=None)
    r = server._query("healthy semantic", 3)
    check("semantico sano: sobre con degraded=None y hits",
          r.get("degraded") is None and r.get("n_hits") == 1 and "error" not in r)

    # ---- 4. enum de 4 literales, nunca nullable (ADR-0043) ----------------------------------------
    m = answer_pipeline._mode_of
    _MISSING = answer_pipeline._MARKER_MISSING
    check("_mode_of: 4 literales + unknown->degraded + missing->not-measured",
          m(None) == "semantic"
          and m("dense-failed:sparse-only") == "degraded-dense-failed"
          and m("sparse-by-config") == "reduced-by-config"
          and m("sparse") == "degraded-dense-failed"
          and m("some-future-marker") == "degraded-dense-failed"
          and m(_MISSING) == "not-measured"
          and set(answer_pipeline._MODE_SEVERITY) == set(answer_pipeline.RETRIEVAL_MODES))

    # ---- 5. path_a con 0 hits degradados: el bundle carga el estado epistemico --------------------
    rag_backend.query = lambda text, k=6: HitList([], degraded="dense-failed:sparse-only")
    a = answer_pipeline.path_a("zero-hit degraded question")
    ret = a.get("retrieval", {})
    check("path_a 0-hits: retrieval.mode enum + raw_marker literal en el bundle",
          ret.get("mode") == "degraded-dense-failed"
          and ret.get("raw_marker") == "dense-failed:sparse-only"
          and ret.get("n_hits") == 0 and a["n_hits"] == 0)
    src = Path(answer_pipeline.__file__).read_text(encoding="utf-8")
    check("grep degraded answer_pipeline.py > 0 (criterio de aceptacion tapon 1)", "degraded" in src)

    # ---- 6. retrieve() e2e offline: run_id + stamp real + retrieval_summary + identity ------------
    answer_pipeline.path_b = lambda q, n=2, **kw: []
    b1 = answer_pipeline.retrieve("does gene X pattern the pronephros?")
    b2 = answer_pipeline.retrieve("does gene X pattern the pronephros?")
    check("run_id unico por corrida (misma pregunta -> bundles distintos, ADR-0044)",
          b1["run_id"] != b2["run_id"] and len(b1["run_id"]) == 32)
    check("stamp es timestamp real de la corrida, no la constante '20260613'",
          b1["stamp"] != "20260613" and b1["stamp"][:4].isdigit() and "T" in b1["stamp"])
    check("retrieval_summary worst-of-n declarado",
          b1["retrieval_summary"] == {"mode": "degraded-dense-failed", "retrievals": 1,
                                      "aggregation": "worst-of-n"})
    ident = b1["bundle_identity"]
    payload = {k: v for k, v in b1.items() if k != "bundle_identity"}
    import hashlib
    sha = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    check("bundle_identity.sha256 verifica contra el payload canonico",
          ident["sha256"] == sha and ident["run_id"] == b1["run_id"])

    # ---- 7. record_audit re-estampa la identidad (el bundle muto) ---------------------------------
    pre_sha = b1["bundle_identity"]["sha256"]
    b1 = answer_pipeline.record_audit(b1, approved=["PMID:1"], rejected=[])
    payload = {k: v for k, v in b1.items() if k != "bundle_identity"}
    sha = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    check("record_audit: AUDIT_APPROVED + identidad re-estampada y verificable",
          b1["decision_state"]["state"] == "AUDIT_APPROVED"
          and b1["bundle_identity"]["sha256"] == sha and sha != pre_sha)

    # ---- 8. contrato de exit-codes del CLI sobre el sobre ------------------------------------------
    import cli
    args = types.SimpleNamespace(text=["x"], k=3, json=True)
    _orig_srv_query = server._query
    server._query = lambda q, k=5: {"degraded": "sparse", "n_hits": 0, "hits": []}
    rc_degraded_empty = cli._cmd_query(args)
    server._query = lambda q, k=5: {"degraded": None, "n_hits": 0, "hits": []}
    rc_healthy_empty = cli._cmd_query(args)
    server._query = lambda q, k=5: {"error": "query_unavailable", "degraded": "unavailable",
                                    "n_hits": 0, "hits": [], "note": "n/a", "query": q}
    rc_error = cli._cmd_query(args)
    server._query = _orig_srv_query
    check("CLI: degradado+vacio -> exit 3 (NO se confunde con sano+vacio=4 ni error=4)",
          rc_degraded_empty == 3 and rc_healthy_empty == 4 and rc_error == 4,
          f"degraded+empty={rc_degraded_empty} healthy+empty={rc_healthy_empty} error={rc_error}")
finally:
    rag_backend.query, rag_backend.query_sparse = _orig_query, _orig_sparse
    answer_pipeline.path_b = _orig_path_b

npass = sum(CHECKS)
print("\n== %d/%d PASS ==" % (npass, len(CHECKS)))
sys.exit(0 if npass == len(CHECKS) else 1)

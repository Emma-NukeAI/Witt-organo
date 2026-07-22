"""
cli.py — `witt-di`: the robust, always-available CLI front door to the DATA INAMOVIBLE RAG.

WHY THIS EXISTS (ADR-0039, 2026-07-19). The MCP server (server.py) is the agent-native front door, but it
has two operational failure modes a plain CLI structurally does NOT: (1) per-session MCP registration can
fail SILENTLY (a Claude session ends up with zero data-inamovible tools while other MCPs load fine), and
(2) the stdio pipe to the subprocess can go stale. This CLI is the same query against the SAME hosted RAG,
reachable from any shell or agent that can run a command — no registration, no pipe.

It reuses server.py's backend verbatim, so it inherits everything that matters:
  - the same .secrets/deploy.env loading (NO secrets on the command line / in config),
  - the same §6 no-hang guarantee (bounded dense timeout -> local sparse fallback, never hangs, never empty),
  - the same degradation marker (ADR-0039): a sparse-only result is announced LOUDLY, never passed off as
    semantic. `resolve` uses the deterministic verified store (resolve_id) — the anti-fabrication source of
    truth — so it works even with zero network.

Transport is orthogonal to which RAG is hit: this CLI and the MCP both call rag_backend.query() against the
same hosted Neo4j, so semantic quality is identical (top hit ~0.80). The CLI is the robust PRIMARY; the MCP
is an optional enhancement.

Usage (from the repo root; runs on the pinned interpreter):
  uv run --locked python rag_index/mcp_server/cli.py query "transcription factors pronephric mesoderm" -k 3
  uv run --locked python rag_index/mcp_server/cli.py resolve pax2a
  uv run --locked python rag_index/mcp_server/cli.py fetch GSE218068
  uv run --locked python rag_index/mcp_server/cli.py health
Add --json to any subcommand for machine-readable output.

Exit codes: 0 = ok (true semantic / resolved / found) · 2 = usage error · 3 = DEGRADED (sparse-only, not
semantic — Neo4j unreachable or semantic disabled by config) · 4 = not found / unavailable.
"""
import sys
import json
import argparse
import pathlib

# cp1252 hardening (extends ADR-0026's cp1252 sweep to the CLI, 2026-07-21). On a Windows console whose
# default codec is cp1252, printing the status glyphs this CLI emits (e.g. the semantic-OK "✓") raised
# UnicodeEncodeError and crashed AFTER a successful retrieval — the query worked, only the print failed.
# Force UTF-8 on stdout/stderr at the root so every downstream print is safe, regardless of console locale.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # py3.7+; TextIOWrapper only
    except (AttributeError, ValueError):
        pass  # already UTF-8, or a non-reconfigurable stream (pipe/redirect) — nothing to do

# Import the server module (same directory). Importing it loads .secrets/deploy.env and wires the backend
# EXACTLY as the MCP server does, but does NOT start mcp.run() (that is under server.py's __main__ guard).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402  (side effect: _load_local_secrets() + backend import)


_DEGRADED_HELP = {
    "sparse-by-config": "semantic disabled by configuration (RAG_BACKEND != neo4j / no .secrets/deploy.env)",
    "dense-failed:sparse-only": "the dense GraphRAG half FAILED (Neo4j unreachable / dim mismatch / MAX_PATH) "
                                "— retry, or run `health` to diagnose",
    "sparse": "hosted semantic path timed out — fell back to the local sparse index (§6 no-hang)",
}


def _degraded_of(hits):
    """Return the degradation marker carried by the query result (None if true semantic)."""
    if isinstance(hits, list):
        for h in hits:
            d = (h.get("metadata") or {}).get("degraded")
            if d:
                return d
    return None


def _cmd_query(args):
    res = server._query(" ".join(args.text), args.k)
    if isinstance(res, dict):  # {"error": "query_unavailable", ...}
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(f"UNAVAILABLE: {res.get('note', res.get('error'))}")
        return 4
    degraded = _degraded_of(res)
    if args.json:
        print(json.dumps({"degraded": degraded, "hits": res}, ensure_ascii=False, indent=2))
    else:
        if degraded:
            print(f"⚠ DEGRADED [{degraded}] — {_DEGRADED_HELP.get(degraded, 'sparse-only, NOT semantic')}")
            print("  These are sparse/keyword hits, NOT semantic GraphRAG results. Do not treat as high-recall.\n")
        else:
            print("semantic (dense GraphRAG) ✓\n")
        for h in res:
            print(f"  [{h['score']:.3f}] {h['type']:9s} {h['doc_id'][:26]:26s} {h['text'][:80]}")
        if not res:
            print("  (no hits)")
    return 3 if degraded else (0 if res else 4)


def _cmd_resolve(args):
    res = server._resolve(args.key)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        if res.get("resolved"):
            print(f"{res['symbol']} -> {res['ensdarg']}  (tier={res['tier']}, verified={res.get('verified_on')})")
        else:
            print(f"NOT_FOUND: {res.get('note')}")
    return 0 if res.get("resolved") else 4


def _cmd_fetch(args):
    res = server._fetch_raw(args.key, args.filename)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        if res.get("found"):
            print(f"{res['corpus_record_id']}  (accession={res.get('accession')}, policy={res.get('policy')}, "
                  f"{res.get('n_files')} file(s))")
            for f in res.get("files", []):
                print(f"  - {f.get('filename')}  {f.get('url') or f.get('source_url') or ''}")
        else:
            print(f"NOT FOUND: {res.get('note')}")
    return 0 if res.get("found") else 4


def _cmd_health(args):
    """One-shot liveness + degradation probe — the pre-flight a teammate runs before trusting results."""
    import os
    res = server._query("pronephros zebrafish", 1)
    degraded = _degraded_of(res) if isinstance(res, list) else "unavailable"
    info = {
        "backend": os.environ.get("RAG_BACKEND") or "sparse(dev)",
        "embed_model": os.environ.get("EMBED_MODEL"),
        "neo4j_uri_set": bool(os.environ.get("NEO4J_URI")),
        "degraded": degraded,
        "semantic_ok": degraded is None and isinstance(res, list) and bool(res),
        "top": (f"{res[0]['doc_id']}:{res[0]['score']}" if isinstance(res, list) and res else None),
    }
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        status = "OK (semantic)" if info["semantic_ok"] else f"DEGRADED ({degraded})"
        print(f"data-inamovible: {status}")
        for k in ("backend", "embed_model", "neo4j_uri_set", "top"):
            print(f"  {k}: {info[k]}")
        if not info["semantic_ok"]:
            print(f"  hint: {_DEGRADED_HELP.get(degraded, 'check .secrets/deploy.env + run smoke_rag.py')}")
    return 0 if info["semantic_ok"] else 3


def main(argv=None):
    ap = argparse.ArgumentParser(prog="witt-di", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("query", help="semantic GraphRAG search over the DATA INAMOVIBLE")
    q.add_argument("text", nargs="+", help="the query text")
    q.add_argument("-k", type=int, default=5, help="number of hits (default 5)")
    q.set_defaults(fn=_cmd_query)

    r = sub.add_parser("resolve", help="deterministic verified-identifier resolve (symbol/ENSDARG/RefSeq/UniProt)")
    r.add_argument("key")
    r.set_defaults(fn=_cmd_resolve)

    f = sub.add_parser("fetch", help="drill a corpus record / accession to its RAW data URLs")
    f.add_argument("key")
    f.add_argument("--filename", default=None, help="restrict to one filename")
    f.set_defaults(fn=_cmd_fetch)

    h = sub.add_parser("health", help="liveness + degradation pre-flight")
    h.set_defaults(fn=_cmd_health)

    for p in (q, r, f, h):
        p.add_argument("--json", action="store_true", help="machine-readable JSON output")

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

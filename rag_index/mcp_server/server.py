"""
server.py — MCP server fronting the DATA INAMOVIBLE (hosted GraphRAG), per ADR-0020.

This is the single front door the project's agents (and anyone with the project) use to query the
shared DATA INAMOVIBLE. It exposes the TWO halves of the source-of-truth interface as MCP tools:
  - query_data_inamovible(query, k)  -> SEMANTIC GraphRAG retrieval (rag_backend; sparse v1 in dev,
                                        Neo4j GraphRAG on the rack via RAG_BACKEND=neo4j)
  - resolve_identifier(key)          -> DETERMINISTIC identifier resolve (resolve_id: symbol/ENSDARG/
                                        RefSeq/UniProt) against the verified store

Deploy: run this on the rack alongside Neo4j + the embedding service; point Claude/MCP clients here
(see rag_index/mcp_server/README.md + rag_index/deploy/README.md). Requires the MCP Python SDK
(`pip install mcp`). In dev it runs against the local sparse v1 (no Neo4j needed).

Run:  python rag_index/mcp_server/server.py
"""
import os
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))


def _load_local_secrets():
    """Single-host convenience: load the deploy vars from the gitignored .secrets/deploy.env so the MCP
    client config carries NO secrets. Uses setdefault, so a hosted/production deploy's real env vars always
    win.

    2026-07-18 fix: we do NOT early-return when NEO4J_URI alone is already in the env. That early-return was
    the trigger for the 1800s query_data_inamovible hang — a half-populated spawn env (NEO4J_URI present but
    EMBED_MODEL / OPENAI_API_KEY unset) skipped loading the rest, so get_embedder() fell to its bge default,
    which downloads a model on first call (hang) and mismatches the 1536-dim index. We always load every var
    the neo4j path needs, then pin RAG_BACKEND=neo4j + EMBED_MODEL=openai whenever a hosted Neo4j is reachable."""
    env_path = ROOT / ".secrets" / "deploy.env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    if os.environ.get("NEO4J_URI"):
        os.environ.setdefault("RAG_BACKEND", "neo4j")   # hosted Neo4j reachable -> use the GraphRAG backend
        os.environ["EMBED_MODEL"] = "openai"            # HARD pin: the 1536-dim index; never fall to bge


_load_local_secrets()
import json  # noqa: E402
from lib import rag_backend, resolve_id, raw_store, verify_output  # noqa: E402

MANIFEST = ROOT / "rag_index" / "corpus_manifest.json"

# --- lightweight file logging (2026-07-19): the subprocess talks stdio to the MCP client, so stdout is
# unavailable for diagnostics. Append timestamped lines to a gitignored log so a hang is diagnosable
# after the fact (which tool, backend, embed model, latency, timeout/error). Never raises.
import datetime as _dt  # noqa: E402
_LOG_PATH = ROOT / "mcp_cache" / "mcp_server.log"


def _log(msg: str):
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"{_dt.datetime.now().isoformat(timespec='milliseconds')} pid={os.getpid()} {msg}\n")
    except Exception:
        pass


_log("server import: RAG_BACKEND={} EMBED_MODEL={} NEO4J_URI_set={} "
     "HTTP_PROXY={!r} HTTPS_PROXY={!r} NO_PROXY={!r}".format(
         os.environ.get("RAG_BACKEND"), os.environ.get("EMBED_MODEL"), bool(os.environ.get("NEO4J_URI")),
         os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"),
         os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"),
         os.environ.get("NO_PROXY") or os.environ.get("no_proxy")))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # SDK not installed in dev — the tools below still importable/testable directly
    FastMCP = None


import concurrent.futures as _futures  # noqa: E402

import time as _time  # noqa: E402

_QUERY_POOL = _futures.ThreadPoolExecutor(max_workers=4)
# Per-attempt budget for the hosted semantic path (Neo4j vector+graph + OpenAI embed). If it exceeds this
# we DO NOT return empty — we fall back to the local sparse index (§6 no-hang). The hosted Neo4j on Dokploy
# intermittently spikes >30s; a healthy warm query is ~0.6s and a cold one ~4s, so 12s cleanly separates
# "warming up" from "spiking". Override via DI_QUERY_TIMEOUT_S.
_DENSE_TIMEOUT_S = int(os.environ.get("DI_QUERY_TIMEOUT_S", "12"))


# --- block-1.4 exposure (webapp handoff §3): manifest/record binding + index version --------------
# Both caches refresh on file mtime change: reads are free (CLAUDE.md §7 — mutations are gated, reads
# auto-reload), so a human-gated ingest becomes visible without restarting the server.
_REC_IDX = {"mtime": None, "idx": {}}
_IDX_VER = {"mtime": None, "version": None}


def _record_index():
    """doc_id/accession -> corpus-record summary {corpus_record_id, verification_tier, approval_status,
    approved_by, data_niche}. `verification_tier` and `approval_status` use the explicit literal
    'not-declared' when absent — never a silent null (a missing tier is 'not measured', not 'clean')."""
    try:
        mtime = MANIFEST.stat().st_mtime
    except OSError:
        return {}
    if _REC_IDX["mtime"] != mtime:
        idx = {}
        try:
            man = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            man = {"records": []}
        for r in man.get("records", []):
            chain = r.get("approval_chain") or [{}]
            info = {"corpus_record_id": r.get("corpus_record_id"),
                    "verification_tier": r.get("verification_tier") or "not-declared",
                    "approval_status": chain[-1].get("status") or "not-declared",
                    "approved_by": chain[-1].get("approved_by"),
                    "data_niche": (r.get("axis_data_niche") or {}).get("primary")}
            cid = str(r.get("corpus_record_id") or "").lower()
            if cid:
                idx[cid] = info
            acc = str((r.get("source_document") or {}).get("accession") or "").lower()
            for part in (p.strip() for p in acc.split("/")):
                if part:
                    idx.setdefault(part, info)
        _REC_IDX.update(mtime=mtime, idx=idx)
    return _REC_IDX["idx"]


def _index_version():
    p = ROOT / "rag_index" / "index" / "manifest.json"
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return None
    if _IDX_VER["mtime"] != mtime:
        try:
            _IDX_VER["version"] = json.loads(p.read_text(encoding="utf-8")).get("index_version")
        except Exception:
            _IDX_VER["version"] = None
        _IDX_VER["mtime"] = mtime
    return _IDX_VER["version"]


def _bind_record(doc_id, meta):
    """Bind a hit to its corpus record: dataset doc_id 'CORPUS-YYYY-NNNN', chunk 'CORPUS-YYYY-NNNN#cNNN'
    (or its metadata.parent), or a metadata accession. Returns the record summary or None (db:/niche:
    docs are taxonomy, not corpus records)."""
    idx = _record_index()
    for key in (str(doc_id).split("#")[0], str(meta.get("parent") or "").split("#")[0],
                str(meta.get("accession") or "")):
        info = idx.get(key.strip().lower())
        if info:
            return info
    return None


def _hit_dicts(hits, degraded=None):
    out = []
    for h in hits:
        meta = dict(h.metadata) if isinstance(h.metadata, dict) else {"meta": h.metadata}
        if degraded:
            meta["degraded"] = degraded
        d = {"doc_id": h.doc_id, "score": round(h.score, 4), "type": h.type,
             "text": h.text, "metadata": meta}
        rec = _bind_record(h.doc_id, meta)
        if rec:  # block 1.4: a search result KNOWS its evidence level without a second call
            d["record"] = rec
        out.append(d)
    return out


def _envelope(hit_dicts, degraded, last_error=None):
    """The uniform query ENVELOPE (ADR-0043): the degradation marker lives ON the envelope, sourced from
    `HitList.degraded` — never derived from per-hit metadata. Stamping only per-hit loses the marker the
    moment the hit list is empty (the for-loop never runs), which made "degraded and empty" byte-identical
    to "healthy and empty" — opposite conclusions (a real DI gap vs. a broken retriever), and the
    2026-07-18/19 silent-degradation trap reintroduced at the empty-result edge. Per-hit stamps are KEPT
    for backward compatibility, but the envelope is the source of truth for consumers (CLI, MCP, HTTP).

    Block 1.4 (ADR-0047): `last_error` turns "degraded" into a diagnosis ("Neo4j unreachable" vs a generic
    marker); `index_version` + `store_version` make scores/resolutions comparable across time."""
    env = {"degraded": degraded, "n_hits": len(hit_dicts), "hits": hit_dicts,
           "last_error": last_error, "index_version": _index_version()}
    try:
        env["store_version"] = resolve_id.store_version()
    except Exception:
        env["store_version"] = None
    return env


def _query(query: str, k: int = 5):
    """Semantic GraphRAG search over the DATA INAMOVIBLE, with a hard no-hang guarantee (CLAUDE.md §6).

    Layered defense (2026-07-18/19) so the tool NEVER hangs the MCP client (the observed 1800s stall) and
    NEVER returns empty when a local answer exists:
      1. Try the hosted semantic path (Neo4j vector + 1-hop graph; OpenAI embed) in a worker thread, bounded
         by _DENSE_TIMEOUT_S. The OpenAI client is itself capped (embeddings.py: 10s, 0 retries — the SDK
         default 600s x2 retries was the 1800s hang) and Neo4j has bounded connect timeouts.
      2. On timeout/error, fall back to the LOCAL SPARSE index (TF-IDF over documents.jsonl, instant, no
         network) and return those hits marked degraded=sparse. The hosted Neo4j on Dokploy intermittently
         spikes >30s; this keeps the tool useful (lower-precision hits) instead of empty.
    Every call is logged (start/latency/outcome) to mcp_cache/mcp_server.log for post-hoc diagnosis.

    RETURN SHAPE (ADR-0043): always a dict envelope {degraded, n_hits, hits} — degraded is
    None | 'dense-failed:sparse-only' | 'sparse-by-config' | 'sparse' | 'unavailable' (error path, which
    additionally carries an 'error' key). The marker survives n_hits == 0 by construction."""
    _log(f"_query START dense_timeout={_DENSE_TIMEOUT_S}s backend={os.environ.get('RAG_BACKEND')} "
         f"embed={os.environ.get('EMBED_MODEL')} k={k} q={query[:80]!r}")
    _t0 = _time.perf_counter()
    try:
        hits = _QUERY_POOL.submit(lambda: rag_backend.query(query, k)).result(timeout=_DENSE_TIMEOUT_S)
        # A successful RETURN can still be sparse-only: HybridRetriever swallows a dense-half failure
        # (Neo4j down / dim mismatch / MAX_PATH) and returns sparse hits. Read the marker it travels on the
        # result and surface it — never label a sparse-only result 'semantic' (ADR-0039, the 07-18/19 trap).
        degraded = getattr(hits, "degraded", None)
        last_error = getattr(rag_backend.get_backend(), "last_error", None) if degraded else None
        r = _hit_dicts(hits, degraded=degraded)
        _log(f"_query OK({'semantic' if not degraded else 'DEGRADED:' + degraded}) "
             f"{(_time.perf_counter() - _t0):.2f}s hits={len(r)}"
             + (f" top={r[0]['doc_id']}:{r[0]['score']}" if r else "")
             + (f" err={last_error}" if last_error else ""))
        return _envelope(r, degraded, last_error=last_error)
    except _futures.TimeoutError:
        dense_cause = f"dense-timeout:{_DENSE_TIMEOUT_S}s (hosted semantic path exceeded budget)"
        _log(f"_query dense TIMEOUT {_DENSE_TIMEOUT_S}s -> sparse fallback (hosted Neo4j slow)")
    except Exception as e:
        dense_cause = f"dense:{type(e).__name__}:{str(e)[:160]}"
        _log(f"_query dense ERROR {(_time.perf_counter() - _t0):.2f}s {type(e).__name__}: "
             f"{str(e)[:160]} -> sparse fallback")
    # ---- §6 fallback: local sparse, run DIRECTLY (not via the pool) so a pool saturated with hung dense
    # workers can never block it. No network, instant. Never empty when the corpus can answer. ----
    try:
        hits = rag_backend.query_sparse(query, k)
        r = _hit_dicts(hits, degraded="sparse")
        _log(f"_query OK(sparse-fallback) {(_time.perf_counter() - _t0):.2f}s hits={len(r)}")
        return _envelope(r, "sparse", last_error=dense_cause)
    except Exception as e:
        _log(f"_query sparse FAILED {(_time.perf_counter() - _t0):.2f}s {type(e).__name__}: {str(e)[:160]}")
        return {"error": "query_unavailable", "degraded": "unavailable", "n_hits": 0, "hits": [],
                "last_error": f"{dense_cause}; sparse:{type(e).__name__}:{str(e)[:160]}",
                "note": ("hosted semantic backend slow AND local sparse fallback failed; "
                         "use resolve_identifier or retry (CLAUDE.md §6)."),
                "query": query}


def _resolve(key: str):
    """Deterministic verified-identifier resolve (symbol | ENSDARG | RefSeq NM_* | UniProt).

    Block 1.4 (ADR-0047): returns the FULL VerifiedRecord — the prior shape returned 6 fields and
    discarded 12 (confidence, provenance, resolver, notes, …), leaving per-entity provenance unreachable
    from any client. `tier_weight` is a CALIBRATION label-weight (Bayes-purity/ECE, ADR-0024), NOT a
    ranking or probative-strength score — it always travels WITH its tier literal (a 0.0 weight does not
    prove NOT_FOUND: unknown literals also map to 0.0)."""
    r = resolve_id.resolve(key)
    if r is resolve_id.NOT_FOUND:
        return {"resolved": False, "key": key,
                "note": "NOT_FOUND — verify against Ensembl + raw-cache (CLAUDE.md §7.9) before use; never mint."}
    tier = "RAW" if r.is_raw_verified else "DERIVED"
    out = {"resolved": True, "symbol": r.symbol, "ensdarg": r.ensdarg,
           "tier": tier, "raw_cache_ref": r.raw_cache_ref, "verified_on": r.verified_on,
           # block 1.4 — the 12 previously-discarded fields:
           "confidence": r.confidence, "provenance": r.provenance, "resolver": r.resolver,
           "source_db": r.source_db, "taxon": r.taxon, "anchor_match": r.anchor_match,
           "ensdarp": r.ensdarp, "ensdart": r.ensdart, "uniprot_acc": r.uniprot_acc,
           "assembly": r.assembly, "ensembl_release": r.ensembl_release, "notes": r.notes,
           "tier_weight": verify_output.tier_weight(tier),
           "tier_weight_kind": "calibration label-weight (Bayes-purity/ECE, ADR-0024) — NOT ranking "
                               "nor probative strength; DERIVED=0.7 is a provisional placeholder"}
    try:
        out["store_version"] = resolve_id.store_version()
    except Exception:
        out["store_version"] = None
    return out


def _fetch_raw(key: str, filename: str = None, expires_seconds: int = 3600):
    """Resolve a corpus record / accession to its RAW data location(s) — the drill-down path for when a
    chunk/embedding is NOT enough and the agent needs the raw data that composes the truth. Returns
    retrievable URLs: a presigned MinIO URL (mirrored private/derived) or the canonical source_url +
    sha256 (public source-pointer, hybrid policy)."""
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    k = str(key).strip().lower()

    def _match(r):
        if r.get("corpus_record_id", "").lower() == k:
            return True
        acc = str(r.get("source_document", {}).get("accession", "")).lower()
        return bool(acc) and k in acc

    rec = next((r for r in man.get("records", []) if _match(r)), None)
    if rec is None:
        return {"found": False, "key": key,
                "note": "no corpus record matches; pass a corpus_record_id (CORPUS-YYYY-NNNN) or an "
                        "accession (GSE.../STDS.../CNP...)"}
    prov = rec.get("raw_provenance", {})
    files = prov.get("files", [])
    if filename:
        files = [f for f in files if f.get("filename") == filename]
    out = [{"filename": f.get("filename"), **raw_store.fetch_url(f, expires_seconds)} for f in files]
    return {"found": True, "corpus_record_id": rec["corpus_record_id"],
            "accession": rec.get("source_document", {}).get("accession"),
            "policy": prov.get("policy"), "n_files": len(out), "files": out}


if FastMCP is not None:
    mcp = FastMCP("data-inamovible")

    @mcp.tool()
    def query_data_inamovible(query: str, k: int = 5):
        """Semantic GraphRAG search over the shared DATA INAMOVIBLE. Use to retrieve the best related
        information (niches, databases, datasets, curated knowledge) for a research question.
        Returns an envelope {degraded, n_hits, hits} (ADR-0043): `degraded` is None for a true semantic
        result and a string marker when the result is sparse-only/unavailable — surface it ALWAYS,
        including (especially) when hits is empty."""
        return _query(query, k)

    @mcp.tool()
    def resolve_identifier(key: str):
        """Resolve a gene symbol / ENSDARG / RefSeq NM_* / UniProt accession to the verified identifier
        (DATA INAMOVIBLE). Deterministic; never invents IDs."""
        return _resolve(key)

    @mcp.tool()
    def fetch_raw(key: str, filename: str = None):
        """Drill from the graph (the guide) to the RAW data that composes the truth, when a chunk or
        embedding is not enough. Pass a corpus_record_id (CORPUS-YYYY-NNNN) or an accession
        (GSE218068 / STDS0000057 / CNP0002220); optionally a filename. Returns retrievable URLs +
        sha256 (presigned MinIO for mirrored data; canonical source_url for public source-pointers)."""
        return _fetch_raw(key, filename)


def _net_probe():
    """Raw TCP reachability probe (2026-07-19) — distinguishes 'network hangs from this subprocess' from
    'backend slow'. Logs connect latency to OpenAI:443 and the Neo4j host:port. If these hang here but are
    fast from a plain shell, the subprocess env (e.g. an injected proxy) is the culprit, not the backends."""
    import socket
    import urllib.parse as _up
    targets = [("api.openai.com", 443)]
    try:
        p = _up.urlparse(os.environ.get("NEO4J_URI", ""))
        if p.hostname:
            targets.append((p.hostname, p.port or 7687))
    except Exception:
        pass
    for host, port in targets:
        t0 = _time.perf_counter()
        try:
            socket.create_connection((host, port), timeout=6).close()
            _log(f"net_probe {host}:{port} OK {(_time.perf_counter() - t0):.2f}s")
        except Exception as e:
            _log(f"net_probe {host}:{port} FAIL {(_time.perf_counter() - t0):.2f}s {type(e).__name__}: {str(e)[:100]}")


def _warmup():
    """Pay the cold-start (Neo4j connect + first OpenAI embed) at server startup, in the background, so the
    user's FIRST query is already warm (~0.5s) instead of paying ~4-6s — or, if the embedder/Neo4j are
    unreachable, so the failure surfaces here (and queries fall back to sparse) rather than hanging the
    first live query. Bounded by _query's own timeout; never blocks mcp.run()."""
    t0 = _time.perf_counter()
    _log("warmup START")
    _net_probe()
    try:
        r = _query("warmup pronephros zebrafish", 1)
        ok = isinstance(r, dict) and "error" not in r
        _log(f"warmup DONE {(_time.perf_counter() - t0):.2f}s ok={ok} "
             + (f"hits={r.get('n_hits')} degraded={r.get('degraded')}" if ok else f"marker={r.get('error')}"))
    except Exception as e:
        _log(f"warmup ERROR {(_time.perf_counter() - t0):.2f}s {type(e).__name__}: {str(e)[:200]}")


if __name__ == "__main__":
    if FastMCP is None:
        # Dev smoke test without the SDK.
        import json
        print("MCP SDK not installed; dev smoke test of the tool backends:")
        print(json.dumps(_query("ocular cornea markers", 2), ensure_ascii=False)[:400])
        print(json.dumps(_resolve("foxc1b")))
        print(json.dumps(_resolve("NM_131729")))
        print(json.dumps(_fetch_raw("GSE218068"), ensure_ascii=False)[:500])
    else:
        # CRITICAL (2026-07-19): pre-import sklearn + build the sparse index in the MAIN thread BEFORE
        # mcp.run(). A first-time import of sklearn/numpy/joblib from a NON-main worker thread deadlocks in
        # this MCP subprocess (VS Code-launched, no console) on the import lock — the true cause of the
        # 1800s stall: EVERY query path (dense via pool -> get_backend builds TfidfRetriever; sparse
        # fallback -> TfidfRetriever) triggered that import off the main thread and hung, even though the
        # network was healthy (net_probe OK). resolve_identifier never touches sklearn, so it worked.
        # Importing here on the main thread makes the module safe; worker threads then reuse sys.modules.
        try:
            _tpre = _time.perf_counter()
            n = len(rag_backend.query_sparse("startup preload pronephros", 1))
            _log(f"preload sparse (main thread) OK {(_time.perf_counter() - _tpre):.2f}s hits={n}")
        except Exception as e:
            _log(f"preload sparse (main thread) ERROR {type(e).__name__}: {str(e)[:200]}")
        try:
            # Also warm the DENSE backend (Neo4j connect + OpenAI embedder) on the MAIN thread and cache it
            # in get_backend()'s singleton, so worker threads reuse the connected driver/embedder instead of
            # doing a first-time init off the main thread (which yields empty/degraded semantic results).
            _tpre = _time.perf_counter()
            h = rag_backend.query("startup preload pronephros zebrafish", 1)
            top = f"{h[0].doc_id}:{round(h[0].score, 3)}" if h else "none"
            _log(f"preload dense (main thread) OK {(_time.perf_counter() - _tpre):.2f}s hits={len(h)} top={top}")
            # HybridRetriever swallows dense errors (rag_backend.py: except Exception: pass), so probe the
            # dense half DIRECTLY here to surface WHY semantic returns empty (Neo4j / embed / dim mismatch).
            be = rag_backend.get_backend()
            dense = getattr(be, "dense", None)
            if dense is not None:
                _td = _time.perf_counter()
                try:
                    dh = dense.query("startup preload pronephros zebrafish", 1)
                    dtop = f"{dh[0].doc_id}:{round(dh[0].score, 3)}" if dh else "none"
                    _log(f"preload dense-DIRECT OK {(_time.perf_counter() - _td):.2f}s hits={len(dh)} top={dtop}")
                except Exception as de:
                    _log(f"preload dense-DIRECT ERROR {(_time.perf_counter() - _td):.2f}s "
                         f"{type(de).__name__}: {str(de)[:250]}")
        except Exception as e:
            _log(f"preload dense (main thread) ERROR {type(e).__name__}: {str(e)[:200]}")
        import threading as _threading
        _threading.Thread(target=_warmup, daemon=True).start()  # warm dense in background; never blocks
        _log("mcp.run() starting")
        mcp.run()

"""
raw_store.py — the durable RAW layer behind the DATA INAMOVIBLE graph (GWT v1.1, ADR-0021).

The graph (Neo4j) holds documents/chunks + embeddings as the GUIDE/index; this is the backing store an
agent drills into when a chunk/embedding is not enough and it needs the raw data that composes the truth.

HYBRID policy (Emmanuel 2026-06-12):
  - PUBLIC / reproducible sources  -> kept as a SOURCE-POINTER (canonical URL + sha256). Re-fetched
    on demand; nothing of ours stored. (ZESTA at CNGB, GSE* at GEO, Ensembl, etc.)
  - PRIVATE / derived / non-reproducible bytes -> MIRRORED into self-hosted MinIO (S3-compatible, a
    Docker-Compose stack on Dokploy next to Neo4j).

Every graph node carries a `raw_ref` produced here, so provenance-to-raw is first-class.

raw_ref schema:
{
  "mode": "mirror" | "source-pointer",
  "store": "minio" | null,            # set when mode=mirror
  "bucket": "...", "key": "...",       # set when mode=mirror
  "source_url": "https://...",         # canonical public source (recorded in BOTH modes when known)
  "sha256": "<hex>", "bytes": <int>,
  "content_type": "...", "recorded_on": "YYYY-MM-DD"
}

fetch_url(raw_ref) resolves a ref to a retrievable URL:
  mirror         -> a time-limited PRESIGNED MinIO GET URL
  source-pointer -> the source_url (+ sha256 to verify integrity after download)

Env (only for the mirror path / MinIO): MINIO_ENDPOINT (host:port), MINIO_ACCESS_KEY, MINIO_SECRET_KEY,
MINIO_BUCKET (default 'data-inamovible-raw'), MINIO_SECURE ('true'|'false').
NO-SPEND: source-pointer mode needs nothing installed. MinIO is self-hosted (free).
"""
import os
import hashlib
from pathlib import Path

DEFAULT_BUCKET = os.environ.get("MINIO_BUCKET", "data-inamovible-raw")


def sha256_file(path, _bufsize=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(_bufsize), b""):
            h.update(blk)
    return h.hexdigest()


def _today():
    # scripts pass dates explicitly elsewhere; here we read the OS date once at call time.
    import datetime
    return datetime.date.today().isoformat()


def source_pointer(source_url, path=None, sha256=None, bytes_=None, content_type=None):
    """Build a source-pointer raw_ref (PUBLIC/reproducible). If `path` is given, sha256 + bytes are
    computed from the local cached copy (so re-downloads can be integrity-checked)."""
    if path is not None:
        p = Path(path)
        sha256 = sha256 or sha256_file(p)
        bytes_ = bytes_ if bytes_ is not None else p.stat().st_size
    return {"mode": "source-pointer", "store": None, "source_url": source_url,
            "sha256": sha256, "bytes": bytes_, "content_type": content_type, "recorded_on": _today()}


# ---------------- MinIO (mirror path) — lazy so source-pointer works without the SDK ----------------
def _client():
    from minio import Minio  # lazy import; only needed for the mirror path
    endpoint = os.environ["MINIO_ENDPOINT"]            # e.g. minio.example.com:9000  (no scheme)
    secure = os.environ.get("MINIO_SECURE", "true").lower() == "true"
    return Minio(endpoint, access_key=os.environ["MINIO_ACCESS_KEY"],
                 secret_key=os.environ["MINIO_SECRET_KEY"], secure=secure)


def ensure_bucket(bucket=DEFAULT_BUCKET):
    c = _client()
    if not c.bucket_exists(bucket):
        c.make_bucket(bucket)
    return bucket


def put(path, key=None, bucket=DEFAULT_BUCKET, source_url=None, content_type="application/octet-stream"):
    """Mirror a PRIVATE/derived file into MinIO; returns a mirror raw_ref. Idempotent by key."""
    p = Path(path)
    key = key or p.name
    sha = sha256_file(p)
    size = p.stat().st_size
    c = _client()
    ensure_bucket(bucket)
    c.fput_object(bucket, key, str(p), content_type=content_type,
                  metadata={"sha256": sha})
    return {"mode": "mirror", "store": "minio", "bucket": bucket, "key": key,
            "source_url": source_url, "sha256": sha, "bytes": size,
            "content_type": content_type, "recorded_on": _today()}


def presign(raw_ref, expires_seconds=3600):
    """Presigned GET URL for a mirror raw_ref (time-limited)."""
    from datetime import timedelta
    c = _client()
    return c.presigned_get_object(raw_ref["bucket"], raw_ref["key"],
                                  expires=timedelta(seconds=expires_seconds))


def fetch_url(raw_ref, expires_seconds=3600):
    """Resolve a raw_ref to something an agent can GET. The single entry point the MCP fetch_raw uses."""
    if not raw_ref:
        return {"available": False, "note": "no raw_ref recorded for this node"}
    mode = raw_ref.get("mode")
    if mode == "mirror":
        try:
            url = presign(raw_ref, expires_seconds)
            return {"available": True, "mode": "mirror", "url": url, "sha256": raw_ref.get("sha256"),
                    "bytes": raw_ref.get("bytes"), "expires_seconds": expires_seconds,
                    "note": "presigned MinIO URL (time-limited); verify sha256 after download"}
        except Exception as e:
            return {"available": False, "mode": "mirror", "error": f"{type(e).__name__}: {e}",
                    "source_url": raw_ref.get("source_url"),
                    "note": "MinIO unreachable; fall back to source_url if present"}
    # source-pointer
    return {"available": True, "mode": "source-pointer", "url": raw_ref.get("source_url"),
            "sha256": raw_ref.get("sha256"), "bytes": raw_ref.get("bytes"),
            "note": "canonical public source; re-download and verify sha256 (hybrid policy: not mirrored)"}


if __name__ == "__main__":
    import json
    rp = source_pointer("https://example.org/file.h5ad", sha256="deadbeef", bytes_=123)
    print("source_pointer:", json.dumps(rp))
    print("fetch_url:", json.dumps(fetch_url(rp)))

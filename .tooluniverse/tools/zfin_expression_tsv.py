"""
ZFIN_expression_tsv — a custom ToolUniverse workspace tool (added 2026-09-15, ADR-0080 rebanada C3).

WHY THIS TOOL EXISTS (ADR-0080, harness Layer 0 lote A):
ZFIN's wild-type EXPRESSION annotations (where/when a gene is expressed, by which assay, from which
publication) are the evidence tier that answers "is <gene> expressed in the pronephros?" — a question
the phenotype tool (zfin_zebrafish) cannot answer and the literature tools answer only indirectly.
ZFIN exposes the whole table as one tab-separated download; there is no per-gene REST endpoint for it,
so the tool DOWNLOADS THE FILE ONCE PER DAY and filters locally (CLI-side, deterministic).

WHAT IT DOES:
  1. download_expression_tsv(): GET https://zfin.org/downloads/wildtype-expression_fish.txt ONCE per UTC
     day -> <cache_dir>/zfin_wildtype_expression_<YYYYMMDD>.txt (written to a .part file and renamed only
     when complete — a partial download is never left where a reader would take it for the whole table).
     cache_dir = WITT_MCP_CACHE_DIR or <repo>/mcp_cache (git-ignored). Bounded by a wall-clock budget
     (WITT_ZFIN_EXPR_DOWNLOAD_BUDGET_S, default 180) and a byte cap (WITT_ZFIN_EXPR_MAX_MB, default 500);
     exceeding either aborts the download, deletes the .part and returns status 'error' BudgetExhausted.
  2. detect_columns(head_lines): reads the FIRST 3 LINES and declares `column_mode`:
       'header'     — line 1 is a header row (no ZDB- identifier in it, alphabetic labels) -> columns are
                      mapped BY NAME (normalized header text);
       'positional' — line 1 is already data -> columns are mapped by POSITION using POSITIONAL_SCHEMA
                      (the order OBSERVED on 2026-09-15 and frozen below; the observed head travels in the
                      output as `head_observed` so any drift is visible).
     The header is NEVER assumed: it is detected from the file in hand and the result is declared.
  3. query_expression(symbol, anatomy=..., ...): streams the cached file, keeps rows whose gene symbol equals
     `symbol` (case-insensitive exact) and — optionally — whose anatomy (super OR sub structure name) matches
     any term at a WORD START (same semantics as zfin_zebrafish.ANATOMY_FILTER_SEMANTICS). Rows come back as
     {gene, gene_id, fish, anatomy, anatomy_id, anatomy_sub, anatomy_sub_id, stage_start, stage_end, assay,
      assay_id, pub_id, probe_id, antibody_id, fish_id, line_no, evidence_id, url}.

DOCTRINE (ADR-0078/0079/0080):
  * THREE states: 'success' (>=1 row), 'no-match' (file scanned to the end, zero rows for this gene /
    anatomy — a MEASUREMENT of the table), 'error' (download or scan failed; a scan cut by budget is 'error'
    with `scan_complete: False` and the rows gathered so far — never 'success' on a partial scan).
    'skipped-budget' when timeout <= 0 BEFORE any network or disk work.
  * Every cut declared: `rows_truncated` (caller's `limit`), `n_rows_scanned`, `n_matched_gene` (before the
    anatomy filter), `n_matched`, `scan_complete`, the download's `bytes`/`n_lines`, and the per-day cache
    (`cache_hit`, `cached_at`, `cache_path`).
  * evidence_id is built from the row's EXTERNAL identifiers (ADR-0080 corrector):
      'zfin-expression:<gene_id>:<super_structure_id>:<publication_id>:<assay_mmo_id>[:<sub_structure_id>][:<fish_id>][:<stage-token>]'
    — every key resolves outside (ZDB-GENE, ZFA, ZDB-PUB, MMO, ZDB-FISH; the stage token is the sanitized
    'start~end' label) and the id is STABLE across daily downloads, unlike a line number of a file ZFIN
    regenerates. The rule travels in data.evidence_id_rule; each row also carries `resolves_to` (the keys) and
    `raw_ref {file_date, line_no}` (where the row sat in the dated cached file — a locator, not an identifier).
    `url` points at the ZFIN publication (https://zfin.org/<ZDB-PUB-...>) when the row carries one.
    `identifier_provenance: 'zfin-tsv-row-keys'`.
  * The TSV is split on TAB ONLY (no csv quoting: a stray '"' in an anatomy name must not swallow columns);
    a line whose cell count differs from n_columns is counted in `n_rows_malformed` (declared drift, never
    silently mapped to the wrong roles). The daily download is serialized with a process lock and written to a
    per-thread .part file, then validated (n_lines > 0, trailing newline) before it is published.

REAL SCHEMA OBSERVED 2026-09-15 (fixture rag_index/query_service/fixtures/zfin_wildtype_expression_head200_20260915.json,
first 200 of 243,119 lines / 43,700,153 bytes downloaded in 27.4 s; the cut is declared in the fixture's `cut`):
  NO header row -> column_mode 'positional', 15 tab-separated columns on every line observed, e.g.
  ZDB-GENE-060824-3 | a1cf | WT | ZFA:0000123 | liver | <sub id ''> | <sub name ''> | Adult | Adult |
  Reverse transcription PCR | MMO:0000655 | ZDB-PUB-060501-4 | <probe ''> | <antibody ''> | ZDB-FISH-150901-29105
  i.e. POSITIONAL_SCHEMA below (gene_id, gene_symbol, fish_name, super_structure_id, super_structure_name,
  sub_structure_id, sub_structure_name, start_stage, end_stage, assay, assay_mmo_id, publication_id, probe_id,
  antibody_id, fish_id). Stages are 'Period:Stage' labels (e.g. 'Pharyngula:Prim-5'); assays carry MMO ids.
  Sanity run over the cached table (offline): wt1a -> 158 rows, 92 with anatomy matching 'pronephr'
  (pronephric glomerulus ZFA:0001557, pronephric podocyte ZFA:0001673, ...), scan 0.5 s.
Offline gate: rag_index/query_service/smoke_tools_a.py
"""
import io
import json
import os
import re
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
TSV_URL = "https://zfin.org/downloads/wildtype-expression_fish.txt"
_UA = {"User-Agent": "witt-organo/1.0 (zfin-expression-tool)", "Accept": "text/plain"}

DEFAULT_TIMEOUT_S = 60                       # socket timeout of the download / per read
DEFAULT_DOWNLOAD_BUDGET_S = 180              # WITT_ZFIN_EXPR_DOWNLOAD_BUDGET_S
DEFAULT_MAX_MB = 500                         # WITT_ZFIN_EXPR_MAX_MB
DEFAULT_SCAN_BUDGET_S = 60                   # WITT_ZFIN_EXPR_SCAN_BUDGET_S (local scan of the cached file)
CHUNK_BYTES = 1 << 16
TOOL_NAME = "zfin_expression_tsv"
IDENTIFIER_PROVENANCE = "zfin-tsv-row-keys"     # ADR-0080 corrector (was 'zfin-download-tsv': line-of-day ids)
EVIDENCE_ID_RULE = ("zfin-expression:<gene_id>:<super_structure_id>:<publication_id>:<assay_mmo_id>"
                    "[:<sub_structure_id>][:<fish_id>][:<start_stage~end_stage sanitized>] — external row keys "
                    "(missing key -> 'na'); stable across daily downloads (ADR-0080 corrector)")
_DOWNLOAD_LOCK = threading.Lock()              # one download per process at a time (WITT_RUN_WORKERS > 1 shares the file)
ANATOMY_FILTER_SEMANTICS = "word-prefix (\\b<term>) over super-structure OR sub-structure name (client-side)"

# Roles the tool understands, in the POSITIONAL order OBSERVED on 2026-09-15 (ZFIN "Wildtype Expression"
# download; the file carries NO header row). Frozen here and declared in every output (`columns`).
POSITIONAL_SCHEMA = (
    "gene_id", "gene_symbol", "fish_name", "super_structure_id", "super_structure_name",
    "sub_structure_id", "sub_structure_name", "start_stage", "end_stage", "assay", "assay_mmo_id",
    "publication_id", "probe_id", "antibody_id", "fish_id",
)
# Header-name normalization (only used when column_mode == 'header'): normalized header text -> role.
HEADER_ALIASES = {
    "geneid": "gene_id", "genesymbol": "gene_symbol", "fishname": "fish_name",
    "superstructureid": "super_structure_id", "superstructurename": "super_structure_name",
    "substructureid": "sub_structure_id", "substructurename": "sub_structure_name",
    "startstage": "start_stage", "endstage": "end_stage", "assay": "assay", "assaymmoid": "assay_mmo_id",
    "publicationid": "publication_id", "pubid": "publication_id", "probeid": "probe_id",
    "antibodyid": "antibody_id", "fishid": "fish_id",
}
_ZDB_RE = re.compile(r"ZDB-[A-Z]+-\d{6}-\d+")


def _get_stream(url, timeout=DEFAULT_TIMEOUT_S):
    """The ONLY network seam of this module: returns an open binary response (file-like, .read(n)).
    The offline smoke monkeypatches it to serve io.BytesIO(fixture)."""
    req = urllib.request.Request(url, headers=_UA)
    return urllib.request.urlopen(req, timeout=timeout)


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today():
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def resolve_cache_dir(cache_dir=None):
    """ADR-0080: WITT_MCP_CACHE_DIR (env, default declared) > <repo>/mcp_cache; `cache_dir` wins for tests."""
    if cache_dir is not None:
        return Path(cache_dir)
    raw = os.environ.get("WITT_MCP_CACHE_DIR", "").strip()
    return Path(raw) if raw else _ROOT / "mcp_cache"


def _env_float(name, default):
    raw = os.environ.get(name, "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return float(default)


def cache_file_path(cache_dir=None, day=None):
    return resolve_cache_dir(cache_dir) / f"zfin_wildtype_expression_{day or _today()}.txt"


def download_expression_tsv(cache_dir=None, timeout=DEFAULT_TIMEOUT_S, budget_s=None, max_bytes=None, force=False):
    """Download the table ONCE per UTC day into the cache dir (ADR-0080). Returns
    {status: 'success'|'error'|'skipped-budget', path, cache_hit, cached_at, bytes, n_lines, elapsed_s, url,
     budget_s, max_bytes, error?}. `n_lines` is counted only on a fresh download (None on a cache hit —
     declared, not recounted)."""
    t0 = time.monotonic()
    budget = float(budget_s) if budget_s is not None else _env_float("WITT_ZFIN_EXPR_DOWNLOAD_BUDGET_S", DEFAULT_DOWNLOAD_BUDGET_S)
    cap = int(max_bytes) if max_bytes is not None else int(_env_float("WITT_ZFIN_EXPR_MAX_MB", DEFAULT_MAX_MB) * 1024 * 1024)
    path = cache_file_path(cache_dir)
    out = {"url": TSV_URL, "path": str(path), "cache_hit": None, "cached_at": None, "bytes": None, "n_lines": None,
           "budget_s": budget, "max_bytes": cap}

    def _finish(status, **extra):
        out["elapsed_s"] = round(time.monotonic() - t0, 3)
        out["status"] = status
        out.update(extra)
        return out

    if timeout is not None and timeout <= 0:
        return _finish("skipped-budget", error=f"BudgetExhausted: timeout={timeout!r} <= 0 before the call (no request sent)")

    def _hit():
        st = path.stat()
        return _finish("success", cache_hit=True, bytes=st.st_size,
                       cached_at=datetime.fromtimestamp(st.st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    if path.exists() and not force:
        return _hit()
    # ADR-0080 corrector: UNA descarga por proceso a la vez — dos workers que arrancan la ronda juntos abrían el
    # MISMO .part (truncado + chunks intercalados) y el primero en terminar publicaba un archivo corrupto. Bajo el
    # lock se re-chequea la caché (el segundo hilo espera y LEE), y el .part es único por hilo.
    with _DOWNLOAD_LOCK:
        if path.exists() and not force:
            out["waited_for_lock"] = True
            return _hit()
        part = path.with_suffix(path.suffix + f".part.{os.getpid()}.{threading.get_ident()}")
        n_bytes = n_lines = 0
        last_byte = b""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            resp = _get_stream(TSV_URL, timeout=timeout)
            try:
                with open(part, "wb") as f:
                    while True:
                        if time.monotonic() - t0 > budget:
                            raise TimeoutError(f"BudgetExhausted: download budget {budget}s exceeded after {n_bytes} bytes")
                        chunk = resp.read(CHUNK_BYTES)
                        if not chunk:
                            break
                        n_bytes += len(chunk)
                        if n_bytes > cap:
                            raise OverflowError(f"BudgetExhausted: byte cap {cap} exceeded")
                        n_lines += chunk.count(b"\n")
                        last_byte = chunk[-1:]
                        f.write(chunk)
            finally:
                try:
                    resp.close()
                except Exception:
                    pass
            # validación ANTES de publicar: una tabla vacía o cortada a media línea no se vuelve "la tabla del día"
            if n_lines <= 0:
                raise ValueError(f"ValidationError: download has {n_bytes} bytes and no newline (empty table)")
            if last_byte != b"\n":
                raise ValueError(f"ValidationError: download does not end with a newline ({n_bytes} bytes, {n_lines} lines) — truncated")
            os.replace(part, path)
            return _finish("success", cache_hit=False, cached_at=_now_iso(), bytes=n_bytes, n_lines=n_lines,
                           validated={"n_lines_gt_0": True, "trailing_newline": True})
        except Exception as e:
            try:
                if part.exists():
                    part.unlink()
            except Exception:
                pass
            return _finish("error", error=f"{type(e).__name__}: {e}", bytes=n_bytes)


def _norm_header(cell):
    return re.sub(r"[^a-z0-9]", "", (cell or "").lower())


def detect_columns(head_lines):
    """ADR-0080: decide 'header' vs 'positional' from the first (<=3) lines, NEVER from an assumption.
    Returns {column_mode, columns: [role|None per position], n_columns, header_raw?, head_observed}.
    A line is a header when it contains NO ZDB- identifier and at least half its cells are alphabetic labels."""
    head = [ln.rstrip("\r\n") for ln in head_lines[:3]]
    rows = [ln.split("\t") if ln else [] for ln in head]   # TAB only, no csv quoting (ADR-0080 corrector)
    first = rows[0] if rows else []
    n_cols = max((len(r) for r in rows), default=0)
    is_header = bool(first) and not any(_ZDB_RE.search(c or "") for c in first) \
        and sum(1 for c in first if re.search(r"[A-Za-z]", c or "")) >= max(1, len(first) // 2) \
        and not any(_norm_header(c) in ("", ) for c in first)
    if is_header:
        columns = [HEADER_ALIASES.get(_norm_header(c)) for c in first]
        return {"column_mode": "header", "columns": columns, "n_columns": len(first), "header_raw": first,
                "head_observed": head, "unmapped_headers": [c for c in first if HEADER_ALIASES.get(_norm_header(c)) is None]}
    columns = list(POSITIONAL_SCHEMA[:n_cols]) + [None] * max(0, n_cols - len(POSITIONAL_SCHEMA))
    return {"column_mode": "positional", "columns": columns, "n_columns": n_cols, "header_raw": None,
            "head_observed": head, "schema_source": "POSITIONAL_SCHEMA (observed 2026-09-15)",
            "n_columns_expected": len(POSITIONAL_SCHEMA)}


def _anatomy_terms(anatomy, anatomy_terms):
    out = []
    for t in [anatomy] + list(anatomy_terms or []):
        t = (t or "").strip().lower()
        if t and t not in out:
            out.append(t)
    return out


def _matches_anatomy(text, terms):
    low = (text or "").lower()
    return any(re.search(r"\b" + re.escape(t), low) for t in terms)


def _row_dict(cells, columns):
    d = {}
    for i, role in enumerate(columns):
        if role and i < len(cells):
            d[role] = cells[i]
    return d


def query_expression(symbol, anatomy=None, anatomy_terms=None, limit=50, timeout=DEFAULT_TIMEOUT_S, budget_s=None,
                     scan_budget_s=None, cache_dir=None, download_kwargs=None):
    """Core logic (stdlib-only, importable for standalone testing) — ADR-0080.

    Args:
      symbol         — zebrafish gene symbol (exact, case-insensitive match on the gene-symbol column).
      anatomy        — optional anatomy keyword; anatomy_terms — extra keywords OR-ed with it (word-prefix).
      limit          — max rows returned (default 50); the cut is DECLARED in rows_truncated.
      timeout        — socket timeout of the download; <= 0 -> 'skipped-budget' with zero work.
      budget_s       — wall-clock budget of the DOWNLOAD (default env WITT_ZFIN_EXPR_DOWNLOAD_BUDGET_S=180).
      scan_budget_s  — wall-clock budget of the local SCAN (default env WITT_ZFIN_EXPR_SCAN_BUDGET_S=60).
      cache_dir      — override of WITT_MCP_CACHE_DIR / <repo>/mcp_cache (tests).

    Returns {status, query_sent, elapsed_s, n_http_gets, cache_hit, cached_at, cache_path, download,
             column_mode, columns, head_observed, n_rows_scanned, scan_complete, data|error}
      status ∈ 'success' | 'no-match' | 'error' | 'skipped-budget'
      data = {symbol, taxon, anatomy_filter, anatomy_terms, anatomy_filter_semantics, n_matched_gene, n_matched,
              rows_truncated, identifier_provenance, source_file_date, rows: [...]}.
    """
    t0 = time.monotonic()
    scan_budget = float(scan_budget_s) if scan_budget_s is not None else _env_float("WITT_ZFIN_EXPR_SCAN_BUDGET_S", DEFAULT_SCAN_BUDGET_S)
    terms = _anatomy_terms(anatomy, anatomy_terms)
    out = {"query_sent": f"{TSV_URL} | gene_symbol=={symbol!r} | anatomy_terms={terms}", "n_http_gets": 0,
           "cache_hit": None, "cached_at": None, "cache_path": None, "download": None,
           "column_mode": None, "columns": None, "head_observed": None, "n_rows_scanned": 0, "scan_complete": None}

    def _finish(status, **extra):
        out["elapsed_s"] = round(time.monotonic() - t0, 3)
        out["status"] = status
        out.update(extra)
        return out

    if timeout is not None and timeout <= 0:
        return _finish("skipped-budget", error=f"BudgetExhausted: timeout={timeout!r} <= 0 before the call (no request sent)")
    sym = (symbol or "").strip()
    if not sym:
        return _finish("error", error="ValueError: empty symbol")

    dl = download_expression_tsv(cache_dir=cache_dir, timeout=timeout, budget_s=budget_s, **(download_kwargs or {}))
    out["download"] = dl
    out["cache_hit"], out["cached_at"], out["cache_path"] = dl.get("cache_hit"), dl.get("cached_at"), dl.get("path")
    out["n_http_gets"] = 0 if dl.get("cache_hit") else (1 if dl.get("status") != "skipped-budget" else 0)
    if dl.get("status") != "success":
        return _finish(dl.get("status") if dl.get("status") == "skipped-budget" else "error",
                       error=dl.get("error", "download failed"))
    path = Path(dl["path"])
    file_date = re.search(r"_(\d{8})\.txt$", path.name)
    file_date = file_date.group(1) if file_date else _today()

    rows, n_gene = [], 0
    n_scanned = 0
    n_malformed = 0
    complete = False
    try:
        with open(path, encoding="utf-8", errors="replace", newline="") as f:
            head = []
            for _ in range(3):
                ln = f.readline()
                if not ln:
                    break
                head.append(ln)
            det = detect_columns(head)
            out["column_mode"], out["columns"], out["head_observed"] = det["column_mode"], det["columns"], det["head_observed"]
            out["column_detection"] = det
            columns = det["columns"]
            sym_idx = columns.index("gene_symbol") if "gene_symbol" in columns else None
            if sym_idx is None:
                return _finish("error", error="SchemaError: no gene_symbol column detected", n_rows_scanned=0, scan_complete=False)
            data_lines = head[1:] if det["column_mode"] == "header" else head
            first_line_no = 2 if det["column_mode"] == "header" else 1
            sym_low = sym.lower()

            n_columns = det.get("n_columns") or len(columns)

            def _consume(ln, line_no):
                nonlocal n_gene, n_malformed
                cells = ln.rstrip("\r\n").split("\t")   # TAB only: a stray quote never swallows columns
                if len(cells) != n_columns:
                    n_malformed += 1   # drift DECLARADO (ADR-0080 corrector); la fila no se mapea a roles equivocados
                    return
                if len(cells) <= sym_idx or (cells[sym_idx] or "").strip().lower() != sym_low:
                    return
                n_gene += 1
                d = _row_dict(cells, columns)
                anat_text = " | ".join(x for x in (d.get("super_structure_name"), d.get("sub_structure_name")) if x)
                if terms and not _matches_anatomy(anat_text, terms):
                    return
                pub = d.get("publication_id") or None
                keys = {"gene_id": d.get("gene_id") or None, "anatomy_id": d.get("super_structure_id") or None,
                        "publication_id": pub, "assay_id": d.get("assay_mmo_id") or None,
                        "anatomy_sub_id": d.get("sub_structure_id") or None, "fish_id": d.get("fish_id") or None}
                rows.append({
                    "gene": d.get("gene_symbol"), "gene_id": d.get("gene_id"), "fish": d.get("fish_name"),
                    "anatomy": d.get("super_structure_name"), "anatomy_id": d.get("super_structure_id"),
                    "anatomy_sub": d.get("sub_structure_name") or None, "anatomy_sub_id": d.get("sub_structure_id") or None,
                    "stage_start": d.get("start_stage"), "stage_end": d.get("end_stage"),
                    "assay": d.get("assay"), "assay_id": d.get("assay_mmo_id") or None,
                    "pub_id": pub, "probe_id": d.get("probe_id") or None, "antibody_id": d.get("antibody_id") or None,
                    "fish_id": d.get("fish_id") or None, "line_no": line_no,
                    "evidence_id": build_evidence_id(keys, d.get("start_stage"), d.get("end_stage")),
                    "resolves_to": keys,
                    "raw_ref": {"file_date": file_date, "line_no": line_no, "cache_path": str(path)},
                    "url": f"https://zfin.org/{pub}" if pub else None,
                    "identifier_provenance": IDENTIFIER_PROVENANCE,
                })

            line_no = first_line_no
            for ln in data_lines:
                _consume(ln, line_no)
                n_scanned += 1
                line_no += 1
            for ln in f:
                if (n_scanned & 1023) == 0 and time.monotonic() - t0 > scan_budget:
                    raise TimeoutError(f"BudgetExhausted: scan budget {scan_budget}s exceeded after {n_scanned} rows")
                _consume(ln, line_no)
                n_scanned += 1
                line_no += 1
            complete = True
    except Exception as e:
        out.update(n_rows_scanned=n_scanned, scan_complete=False, n_rows_malformed=n_malformed)
        return _finish("error", error=f"{type(e).__name__}: {e}",
                       data={"symbol": sym, "n_matched_gene": n_gene, "n_matched": len(rows), "rows": rows[:limit] if limit else rows})

    out.update(n_rows_scanned=n_scanned, scan_complete=complete, n_rows_malformed=n_malformed)
    data = {"symbol": sym, "taxon": "NCBITaxon:7955", "anatomy_filter": anatomy, "anatomy_terms": terms,
            "anatomy_filter_semantics": ANATOMY_FILTER_SEMANTICS if terms else None,
            "n_matched_gene": n_gene, "n_matched": len(rows),
            "rows_truncated": (len(rows) > limit) if limit is not None else False,
            "identifier_provenance": IDENTIFIER_PROVENANCE, "evidence_id_rule": EVIDENCE_ID_RULE,
            "source_file_date": file_date, "n_rows_malformed": n_malformed,
            "rows": rows[:limit] if limit is not None else rows}
    return _finish("success" if rows else "no-match", data=data)


def _stage_token(start, end):
    s = re.sub(r"[^A-Za-z0-9]+", "-", f"{start or ''}~{end or ''}".strip("~")).strip("-")
    return s or None


def build_evidence_id(keys, start_stage=None, end_stage=None):
    """EVIDENCE_ID_RULE aplicada a las llaves externas de UNA fila (ADR-0080 corrector). Determinista; una llave
    ausente se escribe 'na' (declarado por posición), los sufijos opcionales sólo cuando existen."""
    parts = ["zfin-expression"] + [str(keys.get(k) or "na") for k in ("gene_id", "anatomy_id", "publication_id", "assay_id")]
    if keys.get("anatomy_sub_id"):
        parts.append(str(keys["anatomy_sub_id"]))
    if keys.get("fish_id"):
        parts.append(str(keys["fish_id"]))
    tok = _stage_token(start_stage, end_stage)
    if tok:
        parts.append(tok)
    return ":".join(parts)


# --- ToolUniverse registration (no-op if the package isn't importable, so the file stays testable) ---
try:
    from tooluniverse.tool_registry import register_tool
except Exception:  # pragma: no cover
    def register_tool(x):
        return x


@register_tool
class ZFIN_expression_tsv:
    name = "ZFIN_expression_tsv"
    description = (
        "Wild-type expression annotations of a zebrafish gene from ZFIN's daily 'wildtype-expression_fish.txt' "
        "download (cached once per day): anatomy (super/sub structure), stage range, assay and ZFIN publication "
        "per row, optionally filtered by an anatomy keyword (word-prefix, e.g. 'pronephr'). Deterministic local "
        "filter over the downloaded table; header/positional layout detected from the file, never assumed (ADR-0080)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Zebrafish gene symbol, e.g. 'wt1a'."},
            "anatomy": {"type": ["string", "null"], "description": "Optional anatomy keyword (word-prefix), e.g. 'pronephr'."},
            "anatomy_terms": {"type": ["array", "null"], "items": {"type": "string"}, "description": "Extra anatomy keywords OR-ed with `anatomy`."},
            "limit": {"type": ["integer", "null"], "description": "Max rows returned (default 50; cut declared in rows_truncated)."},
            "timeout": {"type": ["number", "null"], "description": "Socket timeout of the download in seconds (default 60)."},
        },
        "required": ["symbol"],
    }

    def run(self, symbol, anatomy=None, anatomy_terms=None, limit=None, timeout=None):
        return query_expression(symbol, anatomy, anatomy_terms, 50 if limit is None else limit,
                                DEFAULT_TIMEOUT_S if timeout is None else timeout)


def _record_fixture(out_path, n_lines_keep=200, cache_dir=None):
    """ONE real GET (ADR-0080 rule): the tool's own daily download into mcp_cache, then ONLY the first
    `n_lines_keep` lines are frozen as the fixture — the cut is DECLARED (`cut`), the full file stays in the
    (git-ignored) cache. The column detection over the real head is recorded too."""
    dl = download_expression_tsv(cache_dir=cache_dir, timeout=120)
    if dl.get("status") != "success":
        raise SystemExit(f"download failed: {dl}")
    lines = []
    total_lines = 0
    with open(dl["path"], encoding="utf-8", errors="replace", newline="") as f:
        for ln in f:
            total_lines += 1
            if len(lines) < n_lines_keep:
                lines.append(ln.rstrip("\r\n"))
    det = detect_columns(lines[:3])
    env = {"tool": TOOL_NAME, "recorded_at": _now_iso(), "url": TSV_URL, "download": dl,
           "cut": {"lines_kept": len(lines), "total_lines_in_download": total_lines, "total_bytes": dl.get("bytes"),
                   "note": "fixture = first N lines only (ADR-0080 rebanada C3); the full table lives in mcp_cache"},
           "column_detection": det, "lines": lines}
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(env, f, ensure_ascii=False, indent=1)
    return env


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if len(sys.argv) >= 3 and sys.argv[1] == "--record-fixture":
        env = _record_fixture(sys.argv[2])
        print(f"recorded {sys.argv[2]}: kept={env['cut']['lines_kept']} total_lines={env['cut']['total_lines_in_download']} "
              f"bytes={env['cut']['total_bytes']} download_status={env['download']['status']} "
              f"cache_hit={env['download']['cache_hit']} elapsed={env['download']['elapsed_s']}")
        det = env["column_detection"]
        print("column_mode:", det["column_mode"], "n_columns:", det["n_columns"])
        for i, ln in enumerate(det["head_observed"]):
            print(f"HEAD{i+1}: {ln}")
    else:
        r = query_expression("wt1a", anatomy="pronephr", limit=8)
        print(json.dumps({k: v for k, v in r.items() if k != "data"}, indent=1, default=str))
        for row in (r.get("data") or {}).get("rows", []):
            print(f"  {row['gene']} {row['anatomy']} / {row['anatomy_sub']} {row['stage_start']}-{row['stage_end']} {row['assay']} {row['pub_id']}")

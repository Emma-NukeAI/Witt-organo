"""
chunk_document.py — section-aware chunking for text documents (papers/PDFs) in the DATA INAMOVIBLE
(GWT v1.1, ADR-0021; guide research-hypothesis §3 "chunk by section, not blind fixed-size").

Splits a PDF/text/markdown doc into SECTION chunks (Abstract/Introduction/Methods/Results/Discussion/...),
sub-splitting overly long sections on paragraph boundaries. Each chunk becomes a retrievable graph node
(type='chunk') that carries a raw_ref back to the full source document — so an agent reads the chunk as a
guide and drills to the raw PDF via fetch_raw when it needs more.

PDF needs PyMuPDF (pip install pymupdf); .txt/.md need nothing. Attach to a corpus record with --attach.

Usage:
  python analysis/scripts/lib/chunk_document.py paper.pdf                      # preview chunks
  python analysis/scripts/lib/chunk_document.py paper.pdf --attach CORPUS-2026-0004 --source-url https://doi/...
"""
import argparse
import re
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2].parent
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
from lib import raw_store  # noqa: E402

MANIFEST = ROOT / "rag_index" / "corpus_manifest.json"
SECTION_RE = re.compile(
    r"^\s*(?:#{1,3}\s+)?("
    r"abstract|summary|introduction|background|results|discussion|conclusions?|"
    r"materials and methods|methods|experimental procedures|references|"
    r"acknowledge?ments|supplementary|figure legends?)\b",
    re.IGNORECASE)
MAX_CHARS = 1800


def _read_text(path):
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        import fitz  # PyMuPDF
        doc = fitz.open(p)
        return "\n".join(page.get_text() for page in doc)
    return p.read_text(encoding="utf-8", errors="replace")


def _split_sections(text):
    """Yield (section_label, body) by detected headers; everything before the first header = 'Header'."""
    lines = text.splitlines()
    sections, cur_label, cur = [], "Header", []
    for ln in lines:
        m = SECTION_RE.match(ln)
        if m:
            if cur:
                sections.append((cur_label, "\n".join(cur).strip()))
            cur_label, cur = m.group(1).title(), []
        else:
            cur.append(ln)
    if cur:
        sections.append((cur_label, "\n".join(cur).strip()))
    return [(lbl, body) for lbl, body in sections if body]


def _subsplit(body, max_chars=MAX_CHARS):
    if len(body) <= max_chars:
        return [body]
    parts, buf = [], ""
    for para in re.split(r"\n\s*\n", body):
        if len(buf) + len(para) + 2 > max_chars and buf:
            parts.append(buf.strip()); buf = ""
        buf += para + "\n\n"
    if buf.strip():
        parts.append(buf.strip())
    return parts


def chunk(path):
    chunks, order = [], 0
    for label, body in _split_sections(_read_text(path)):
        for piece in _subsplit(body):
            chunks.append({"section": label, "order": order, "text": piece, "chars": len(piece)})
            order += 1
    return chunks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--attach", default=None, help="corpus_record_id to attach chunks to")
    ap.add_argument("--source-url", default=None, help="canonical URL of the doc (for the raw_ref pointer)")
    ap.add_argument("--private", action="store_true", help="mirror the doc into MinIO (else source-pointer)")
    a = ap.parse_args()

    chunks = chunk(a.path)
    print(f"[chunk] {Path(a.path).name}: {len(chunks)} chunks across "
          f"{len(set(c['section'] for c in chunks))} sections")
    for c in chunks[:8]:
        print(f"   c{c['order']:02d} [{c['section']:14s}] {c['chars']:5d} chars  {c['text'][:60]!r}")

    if not a.attach:
        print("  (preview only; pass --attach CORPUS-... to write into the manifest)")
        return

    if a.private:
        raw_ref = raw_store.put(a.path, source_url=a.source_url, content_type="application/pdf")
    else:
        raw_ref = raw_store.source_pointer(a.source_url or f"file://{Path(a.path).resolve()}", path=a.path)
    raw_ref["filename"] = Path(a.path).name

    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rec = next((r for r in man["records"] if r["corpus_record_id"] == a.attach), None)
    if rec is None:
        sys.exit(f"no record {a.attach}")
    rec["chunks"] = [{"chunk_id": f"{a.attach}#c{c['order']:03d}", "section": c["section"],
                      "order": c["order"], "text": c["text"], "raw_ref": raw_ref} for c in chunks]
    rec.setdefault("raw_provenance", {"policy": "hybrid", "files": []})
    rec["raw_provenance"]["files"].append(raw_ref)
    man["status"] = f"{a.attach}: {len(chunks)} chunks attached (chunk_document.py). Human-gated; re-ingest to load."
    MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  attached {len(chunks)} chunks to {a.attach} (each with raw_ref). Re-ingest to load into the graph.")


if __name__ == "__main__":
    main()

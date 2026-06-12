"""
approve_dataset.py — the HUMAN GATE for the DATA INAMOVIBLE (GWT v1.1, §7). Flip a PROPOSED corpus
record (from add_dataset.py) to approved and ingest it into the graph. This is the single write gate:
only a human runs it, and only after reviewing the proposal. Idempotent ingest (MERGE).

Run with the venv python + sourced secrets (so ingest can reach Neo4j + embed):
  set -a; . .secrets/deploy.env; set +a
  ./.venv/Scripts/python.exe analysis/scripts/lib/approve_dataset.py CORPUS-2026-0003 --by Emmanuel
"""
import argparse
import json
import subprocess
import sys
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2].parent
MANIFEST = ROOT / "rag_index" / "corpus_manifest.json"
INGEST = ROOT / "rag_index" / "graphrag" / "ingest.py"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus_record_id")
    ap.add_argument("--by", required=True, help="approver name (the human gate)")
    ap.add_argument("--no-ingest", action="store_true", help="approve only; don't run ingest")
    a = ap.parse_args()

    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rec = next((r for r in man["records"] if r["corpus_record_id"] == a.corpus_record_id), None)
    if rec is None:
        sys.exit(f"no record {a.corpus_record_id} in manifest")

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    chain = rec.setdefault("approval_chain", [])
    gate = next((g for g in chain if g.get("gate") == "categorization"), None)
    if gate is None:
        gate = {"gate": "categorization"}
        chain.append(gate)
    gate.update(status="approved", approved_by=a.by, approved_at=now)
    man["status"] = f"{a.corpus_record_id} APPROVED by {a.by}. Ingesting." if not a.no_ingest else \
                    f"{a.corpus_record_id} APPROVED by {a.by} (ingest pending)."
    MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[approve] {a.corpus_record_id} -> approved by {a.by} at {now}")

    if a.no_ingest:
        print("  --no-ingest: skipping graph load. Run ingest.py when ready.")
        return
    print("  ingesting into Neo4j (idempotent MERGE)...")
    r = subprocess.run([sys.executable, str(INGEST)])
    if r.returncode == 0:
        print(f"  [approve] {a.corpus_record_id} ingested.")
    else:
        print(f"  [approve] ingest FAILED (exit {r.returncode}). Check NEO4J_*/OPENAI_API_KEY env + venv deps, "
              f"then re-run: {sys.executable} {INGEST}")


if __name__ == "__main__":
    main()

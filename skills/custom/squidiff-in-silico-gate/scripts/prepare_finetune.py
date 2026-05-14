#!/usr/bin/env python
"""
prepare_finetune.py — Mode 2 helper. Produces a configured train_squidiff.py
invocation and a Runpod recipe for the user to run training on GPU.

This script does NOT run training. Training needs GPU and is expensive.
This script prepares the inputs and produces a runbook.

Usage:
  python prepare_finetune.py \
    --data /path/to/POC_data.h5ad \
    --base-checkpoint ipsc \
    --output-dir /tmp/finetune_config/

Outputs:
  - <output-dir>/train_command.sh    Bash script with the full training command
  - <output-dir>/runpod_recipe.md    Step-by-step Runpod runbook (pod, cost, time)
  - <output-dir>/validation.sh       Post-training validation harness
  - <output-dir>/README.md           Overview
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import textwrap


RUNPOD_RECIPE_TEMPLATE = """\
# Runpod Recipe — Fine-tuning Squidiff on POC Data

## Pod selection

Recommended: **RTX 4090** (24GB VRAM) or **A6000** (48GB).
- RTX 4090: ~$0.34/hr on Runpod community cloud, sufficient for gene_size ≤ 1000
- A6000: ~$0.69/hr, use if gene_size > 1500 or batch_size > 64

Estimated cost: **$200–500** for a single full fine-tune from {base_checkpoint} base.
Estimated time: **4–12 hours** depending on dataset size and convergence.

## Setup steps on the pod

```bash
# 1. SSH into the pod
ssh root@<pod-ip>

# 2. Clone the Squidiff reproducibility repo (has the base checkpoints)
git clone https://github.com/siyuh/Squidiff_reproducibility.git
git clone https://github.com/siyuh/Squidiff.git

# 3. Install
cd Squidiff
pip install -e .
pip install scanpy anndata h5py

# 4. Upload your POC data
# Either scp from local, or use Runpod's file upload:
#   /workspace/poc_data.h5ad

# 5. Run training
bash /workspace/train_command.sh

# 6. The output checkpoint will be in:
#   /workspace/logger_files/{logger_path}/model.pt

# 7. Download it before terminating the pod:
#   scp root@<pod-ip>:/workspace/logger_files/{logger_path}/model.pt ./local_path/
```

## Cost-safety checklist

- [ ] Confirm POC data uploaded and readable before starting training
- [ ] Set a wall-clock budget — terminate the pod if training exceeds 12h
- [ ] Snapshot the pod or download checkpoints every 2h during long runs
- [ ] Verify final checkpoint loads with sample_squidiff before terminating
- [ ] Stop the pod immediately after downloading (Runpod bills per second)

## Bringing the checkpoint home

Once you have `model.pt` locally, place it at:

```
~/.squidiff-gate-weights/custom/{logger_path}.pt
```

Then run inference via:

```
python scripts/run_inference.py \\
    --data new_data.h5ad \\
    --operation addition \\
    --checkpoint ~/.squidiff-gate-weights/custom/{logger_path}.pt \\
    --system pronephros \\
    --hypothesis "..." \\
    --out /tmp/metrics.json
```
"""


TRAIN_CMD_TEMPLATE = """\
#!/usr/bin/env bash
# train_command.sh — fine-tune Squidiff on POC data

set -e

DATA_PATH=/workspace/{data_filename}
LOGGER_PATH=logger_files/{logger_path}
BASE_CHECKPOINT=/workspace/Squidiff_reproducibility/checkpoints/{base_checkpoint}.pt
GENE_SIZE={gene_size}

mkdir -p $LOGGER_PATH

# Training invocation — see train_squidiff.py for full arg list
python /workspace/Squidiff/train_squidiff.py \\
    --logger_path $LOGGER_PATH \\
    --data_path $DATA_PATH \\
    --resume_checkpoint $BASE_CHECKPOINT \\
    --gene_size $GENE_SIZE \\
    --output_dim $GENE_SIZE \\
    {extra_args}

echo "Done. Checkpoint should be at $LOGGER_PATH/model.pt"
"""


VALIDATION_TEMPLATE = """\
#!/usr/bin/env bash
# validation.sh — sanity-check the fine-tuned checkpoint

CHECKPOINT_PATH=$1
DATA_PATH=$2

if [ -z "$CHECKPOINT_PATH" ] || [ -z "$DATA_PATH" ]; then
  echo "Usage: bash validation.sh <checkpoint.pt> <held_out_h5ad>"
  exit 1
fi

python scripts/run_inference.py \\
    --data "$DATA_PATH" \\
    --operation addition \\
    --checkpoint "$CHECKPOINT_PATH" \\
    --system pronephros \\
    --source-label control \\
    --target-label perturbed \\
    --label-col condition \\
    --hypothesis "Validation of fine-tuned checkpoint on held-out POC data" \\
    --out /tmp/finetune_validation.json

python scripts/render_figure.py \\
    --metrics /tmp/finetune_validation.json \\
    --out /mnt/user-data/outputs/finetune_validation.html

echo "Inspect /mnt/user-data/outputs/finetune_validation.html"
echo "Sanity criteria:"
echo "  - Pearson r >= 0.75 on the held-out condition"
echo "  - Directional accuracy >= 70% on top-20 DE genes"
echo "  - Latent space shows clear separation between conditions"
"""


def detect_gene_size(data_path: Path) -> int:
    """Try to detect gene count from the h5ad."""
    try:
        import anndata as ad
        adata = ad.read_h5ad(str(data_path), backed='r')
        n = adata.n_vars
        adata.file.close()
        # Round up to standard sizes the paper uses
        if n <= 200: return 200
        if n <= 500: return 500
        if n <= 1000: return 1000
        return n
    except Exception:
        return 500  # default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--base-checkpoint", default="ipsc",
                    choices=["ipsc", "bvo", "k562", "glioblastoma", "sciplex"])
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--logger-name", default="poc_finetune")
    ap.add_argument("--use-drug-structure", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    data_path = Path(args.data)
    gene_size = detect_gene_size(data_path)
    extra = ""
    if args.use_drug_structure:
        extra = "--use_drug_structure True"

    train_cmd = TRAIN_CMD_TEMPLATE.format(
        data_filename=data_path.name,
        logger_path=args.logger_name,
        base_checkpoint=args.base_checkpoint,
        gene_size=gene_size,
        extra_args=extra,
    )
    (out_dir / "train_command.sh").write_text(train_cmd)
    (out_dir / "train_command.sh").chmod(0o755)

    runpod = RUNPOD_RECIPE_TEMPLATE.format(
        base_checkpoint=args.base_checkpoint,
        logger_path=args.logger_name,
    )
    (out_dir / "runpod_recipe.md").write_text(runpod)

    (out_dir / "validation.sh").write_text(VALIDATION_TEMPLATE)
    (out_dir / "validation.sh").chmod(0o755)

    readme = textwrap.dedent(f"""\
        # Fine-tune Squidiff on POC Data — Generated Config

        Generated for: {data_path.name}
        Detected gene size: {gene_size}
        Base checkpoint: {args.base_checkpoint}

        Files in this directory:
          - train_command.sh    The training invocation. Run on a GPU pod.
          - runpod_recipe.md    Step-by-step Runpod runbook with cost estimate.
          - validation.sh       Post-training validation harness.

        Next step: read runpod_recipe.md and provision a pod.

        Estimated cost: $200–500. Estimated time: 4–12 hours.

        After training, place the checkpoint at:
          ~/.squidiff-gate-weights/custom/{args.logger_name}.pt

        Then validate with:
          bash validation.sh ~/.squidiff-gate-weights/custom/{args.logger_name}.pt <held_out_h5ad>
        """)
    (out_dir / "README.md").write_text(readme)

    print(f"[prepare_finetune] Generated fine-tune config in {out_dir}")
    print(f"[prepare_finetune] Read {out_dir}/runpod_recipe.md to start the GPU pod.")


if __name__ == "__main__":
    main()

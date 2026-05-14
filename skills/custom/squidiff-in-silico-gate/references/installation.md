# Installation Reference

How to get Mode 1 (real Squidiff inference) working in your environment. Read this before invoking the skill for the first time on a new machine or fresh workspace.

## Quick Path

```bash
bash scripts/setup_environment.sh
```

That command installs the Python stack (`numpy`, `scipy`, `pandas`, `anndata`, `scanpy`, `torch`-CPU, `Squidiff`), downloads the reproducibility repo (which contains the checkpoint demos), and writes a marker file at `~/.squidiff-gate-setup-done` so subsequent invocations don't redo the install.

First run: **2–4 minutes** of install + download time. Subsequent runs: instant.

If you have GPU access locally and want to use it:

```bash
bash scripts/setup_environment.sh --gpu
```

To force reinstall:

```bash
bash scripts/setup_environment.sh --force
```

## What Gets Installed

The setup script installs into the system Python via `pip --break-system-packages`:

| Package | Purpose |
|---|---|
| numpy, scipy, pandas, scikit-learn | Core scientific stack |
| matplotlib | Plotting (used by some Squidiff internal helpers) |
| anndata, scanpy, h5py | Single-cell data handling |
| torch | PyTorch (CPU build by default) |
| **Squidiff** | The actual model package |
| rdkit (optional) | Required only for Operation 5 (drug adapter) |

Total disk: ~2–3 GB.

## Pretrained Weights

The skill expects pretrained checkpoints at `~/.squidiff-gate-weights/Squidiff_reproducibility/checkpoints/`. The setup script clones the demo repo, but if upstream changes file locations, you may need to download checkpoints manually.

Sources for pretrained weights (in priority order):

1. **The reproducibility repo:** https://github.com/siyuh/Squidiff_reproducibility
2. **Zenodo archive:** https://doi.org/10.5281/zenodo.15061773
3. **Direct contact** with the corresponding authors (kam.leong@columbia.edu, ea2690@columbia.edu, jamesz@stanford.edu) if neither of the above is accessible

Expected checkpoint files in `~/.squidiff-gate-weights/Squidiff_reproducibility/checkpoints/`:

```
bvo.pt          # Blood vessel organoid model (irradiation + G-CSF dataset)
ipsc.pt         # iPSC differentiation model (Cuomo et al. dataset)
k562.pt         # K562 gene perturbation model (Norman et al. dataset)
glioma.pt       # Glioblastoma drug response model (Zhao et al. dataset)
sciplex.pt      # sci-plex3 drug adapter model (Srivatsan et al. dataset)
```

**If a checkpoint file is missing**, the skill will:
1. Try to use the next-closest checkpoint with a warning
2. If no checkpoints are available at all, fall back to Mode 0 (synthetic proxy) with a clear flag in the figure

## Troubleshooting

### `pip install Squidiff` fails

Squidiff is a new package on PyPI. If it's not found:

```bash
pip install --break-system-packages git+https://github.com/siyuh/Squidiff.git
```

### Torch installation hangs or fails

CPU torch from the pytorch.org index is the most reliable:

```bash
pip install --break-system-packages --index-url https://download.pytorch.org/whl/cpu torch
```

If that also fails, try the generic pip torch (will be a CPU build by default on systems without CUDA):

```bash
pip install --break-system-packages torch
```

### Checkpoint files not found at `~/.squidiff-gate-weights/`

Either the reproducibility repo clone failed (check network), or the upstream repo restructured. Manually:

```bash
mkdir -p ~/.squidiff-gate-weights
cd ~/.squidiff-gate-weights
git clone https://github.com/siyuh/Squidiff_reproducibility.git
# If the checkpoint files are in a different subdirectory, set the env var:
export SQUIDIFF_GATE_WEIGHTS=/path/to/your/checkpoints/parent
```

The `run_inference.py` script honors the `SQUIDIFF_GATE_WEIGHTS` env var to override the default path.

### Mode 1 keeps falling back to Mode 0

Symptoms: every figure says "Mode 0 synthetic proxy" with the watermark.

Causes (in order of likelihood):
1. `Squidiff` package not importable → `python -c "import Squidiff"` should succeed silently
2. PyTorch missing → `python -c "import torch"` should succeed
3. Checkpoint paths invalid → `ls ~/.squidiff-gate-weights/Squidiff_reproducibility/checkpoints/*.pt`
4. Permissions on `/home/claude/.squidiff-gate-*` → make sure writable

Fix usually: `bash scripts/setup_environment.sh --force` and check the script output carefully.

### Inference is slow

CPU inference on the Squidiff DDIM is **~30s to 2 min per prediction** depending on cell count and gene size. This is normal.

To speed up:
- Reduce gene set: subset the h5ad to the top 200–500 most-variable genes before running
- Subsample cells: 500 cells per condition is usually enough for stable Pearson r estimates
- Use GPU: rerun setup with `--gpu` flag and ensure `torch.cuda.is_available()` returns `True`

### Memory errors during inference

The model itself is small (a few hundred MB of weights), but high gene counts × high cell counts make activations large. Symptoms: `OOMError`, kernel killed by OS.

Mitigations:
- Subset to top-500 variable genes
- Batch the inference: process source cells in chunks of 200
- For very large datasets, use a Runpod CPU pod with 32–64 GB RAM (~$0.10–0.20/hr)

## Environment Sanity Check

After setup, this should run clean:

```bash
python -c "
import torch
import anndata
import scanpy
import Squidiff
print('Squidiff version:', Squidiff.__version__ if hasattr(Squidiff,'__version__') else 'unknown')
print('Torch:', torch.__version__, 'CUDA:', torch.cuda.is_available())
print('Setup OK.')
"
```

If anything errors, run `bash scripts/setup_environment.sh --force` and re-check.

## Offline / Air-Gapped Environments

If your environment has no internet access:

1. On a connected machine, run the setup script to populate `~/.squidiff-gate-weights/` and a pip wheel cache.
2. `pip wheel --break-system-packages Squidiff anndata scanpy torch -d ./wheels/`
3. Tar up `wheels/` and `~/.squidiff-gate-weights/`, transfer to the air-gapped machine.
4. On the target: `pip install --break-system-packages ./wheels/*.whl` and unpack the weights directory.
5. Set `SQUIDIFF_GATE_WEIGHTS=/path/to/transferred/weights`.

Mode 0 (synthetic proxy) requires no external dependencies beyond `numpy` and works offline by default.

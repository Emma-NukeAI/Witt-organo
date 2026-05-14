#!/usr/bin/env bash
# setup_environment.sh — one-time setup for Squidiff inference
#
# What this does:
#   1. Installs Squidiff package from pip
#   2. Installs supporting dependencies (scanpy, anndata, torch CPU build, etc.)
#   3. Downloads pretrained weights from Squidiff_reproducibility demo repo
#   4. Creates a marker file (~/.squidiff-gate-setup-done) so we don't redo
#
# Usage:
#   bash scripts/setup_environment.sh
#   bash scripts/setup_environment.sh --force   # force reinstall
#   bash scripts/setup_environment.sh --gpu     # install GPU torch instead of CPU
#
# Notes for the skill orchestrator:
#   - This is idempotent. Safe to call every invocation; it's fast on subsequent runs.
#   - Approximate first-run time: 2–4 min for installs, additional download time for weights.
#   - Network access required for both pip and weight downloads.
#   - If pip fails, the skill should fall back to Mode 0 (conceptual) and warn the user.

set -e

MARKER_FILE="$HOME/.squidiff-gate-setup-done"
WEIGHTS_DIR="$HOME/.squidiff-gate-weights"
FORCE=0
GPU=0

for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --gpu) GPU=1 ;;
  esac
done

if [ -f "$MARKER_FILE" ] && [ "$FORCE" -eq 0 ]; then
  echo "[setup] Already configured. Use --force to reinstall."
  echo "[setup] Marker: $MARKER_FILE"
  echo "[setup] Weights: $WEIGHTS_DIR"
  exit 0
fi

echo "[setup] Installing Squidiff package and dependencies..."
echo "[setup] First run takes 2–4 minutes."

# Core scientific stack
pip install --break-system-packages --quiet \
  numpy \
  scipy \
  pandas \
  scikit-learn \
  matplotlib

# Single-cell stack
pip install --break-system-packages --quiet \
  anndata \
  scanpy \
  h5py

# PyTorch — CPU by default
if [ "$GPU" -eq 1 ]; then
  echo "[setup] Installing GPU build of PyTorch..."
  pip install --break-system-packages --quiet torch
else
  echo "[setup] Installing CPU build of PyTorch..."
  pip install --break-system-packages --quiet --index-url https://download.pytorch.org/whl/cpu torch || \
    pip install --break-system-packages --quiet torch
fi

# Squidiff itself
echo "[setup] Installing Squidiff..."
pip install --break-system-packages --quiet Squidiff || {
  echo "[setup] WARNING: pip install Squidiff failed."
  echo "[setup] Attempting install from GitHub..."
  pip install --break-system-packages --quiet git+https://github.com/siyuh/Squidiff.git || {
    echo "[setup] ERROR: Could not install Squidiff. Fall back to Mode 0."
    exit 1
  }
}

# Optional: RDKit for drug-adapter operation (Operation 5)
# Only needed if user invokes Operation 5. Don't fail setup if missing.
pip install --break-system-packages --quiet rdkit 2>/dev/null || \
  echo "[setup] NOTE: rdkit not installed. Operation 5 (drug adapter) will be unavailable."

# Weight downloads
mkdir -p "$WEIGHTS_DIR"
cd "$WEIGHTS_DIR"

# These URLs point at the Squidiff_reproducibility demo repo's checkpoint locations.
# If they change upstream, the skill should fall back gracefully and instruct the user
# to clone the demo repo manually.
echo "[setup] Downloading pretrained checkpoints..."
echo "[setup] Note: these are placeholder URLs. Update once the demo repo publishes stable URLs."
echo "[setup] If downloads fail, clone https://github.com/siyuh/Squidiff_reproducibility manually"
echo "[setup] and point --checkpoint at the local path."

# Attempt download of demo repo (lightweight clone, no LFS unless required)
if [ ! -d "Squidiff_reproducibility" ]; then
  git clone --depth 1 https://github.com/siyuh/Squidiff_reproducibility.git 2>/dev/null || {
    echo "[setup] WARNING: Could not clone reproducibility repo."
    echo "[setup] You will need to provide --checkpoint <path> explicitly to run_inference.py."
  }
fi

# Sanity check
python -c "import torch; import anndata; import scanpy; print('[setup] Core stack OK.')" || exit 1
python -c "import Squidiff; print('[setup] Squidiff package importable.')" 2>/dev/null || \
  echo "[setup] WARNING: Squidiff import failed. Mode 1 will not work; the skill should fall back to Mode 0."

# Marker
touch "$MARKER_FILE"
echo "[setup] Done. Marker written to $MARKER_FILE"
echo "[setup] Weights directory: $WEIGHTS_DIR"

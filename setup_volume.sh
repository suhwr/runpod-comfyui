#!/usr/bin/env bash
# ==============================================================================
# setup_volume.sh — One-time model population script for Network Volume
#
# HOW TO USE:
#   1. Create a Network Volume (>=20GB) from dashboard
#   2. Spin up a temporary GPU pod with the volume attached
#      (any Ubuntu/Python image works, e.g. nvidia/cuda:12.4.1-runtime-ubuntu22.04)
#   3. Open terminal in that pod and run:
#         bash <(curl -fsSL https://raw.githubusercontent.com/suhwr/runpod-comfyui/main/setup_volume.sh)
#      or upload this file and run:  bash setup_volume.sh
#   4. Terminate the temporary pod (volume data persists)
#   5. Attach the volume to your serverless endpoint
#   6. The worker will auto-detect and symlink — no download needed!
# ==============================================================================
set -e

VOLUME_ROOT="/runpod-volume"
MODELS_DIR="$VOLUME_ROOT/models"
CHECKPOINTS_DIR="$MODELS_DIR/checkpoints"
LORAS_DIR="$MODELS_DIR/loras"

echo "================================================================"
echo "  Network Volume Model Setup Script"
echo "  Target: $VOLUME_ROOT"
echo "================================================================"

# Detect volume
if [ ! -d "$VOLUME_ROOT" ]; then
    echo "❌ Network Volume not found at $VOLUME_ROOT"
    echo "   Make sure the volume is attached to this pod."
    exit 1
fi

FREE_GB=$(df -BG "$VOLUME_ROOT" | tail -1 | awk '{print $4}' | tr -d 'G')
echo "✅ Volume found. Free space: ${FREE_GB}GB"

if [ "$FREE_GB" -lt 10 ]; then
    echo "⚠️  Warning: Less than 10GB free. NoobAI-XL needs ~7.2GB."
fi

mkdir -p "$CHECKPOINTS_DIR" "$LORAS_DIR"

# Install aria2 for fast multi-stream download
if ! command -v aria2c >/dev/null 2>&1; then
    echo "📦 Installing aria2..."
    apt-get update -qq && apt-get install -y -qq aria2
fi

# ─── Download NoobAI-XL v1.1 Checkpoint (~7.1GB) ───────────────────────────
CHECKPOINT_NAME="NoobAI-XL-v1.1.safetensors"
CHECKPOINT_PATH="$CHECKPOINTS_DIR/$CHECKPOINT_NAME"
CHECKPOINT_URL="https://huggingface.co/Laxhar/noobai-XL-1.1/resolve/main/NoobAI-XL-v1.1.safetensors"

if [ -f "$CHECKPOINT_PATH" ]; then
    SIZE=$(du -sh "$CHECKPOINT_PATH" | cut -f1)
    echo "✅ Checkpoint already exists ($SIZE) — skipping download."
else
    echo ""
    echo "⬇️  Downloading NoobAI-XL v1.1 (~7.1GB)..."
    echo "    Destination: $CHECKPOINT_PATH"
    echo "    Using 16-stream accelerated download..."
    aria2c \
        -c \
        -x 16 \
        -s 16 \
        -k 1M \
        --file-allocation=none \
        --console-log-level=notice \
        --dir="$CHECKPOINTS_DIR" \
        --out="$CHECKPOINT_NAME" \
        "$CHECKPOINT_URL"
    echo "✅ Checkpoint downloaded!"
fi

# ─── Download Hyper-SD 8-Step CFG LoRA (~400MB) ────────────────────────────
LORA_NAME="Hyper-SDXL-8steps-CFG-lora.safetensors"
LORA_PATH="$LORAS_DIR/$LORA_NAME"
LORA_URL="https://huggingface.co/ByteDance/Hyper-SD/resolve/main/Hyper-SDXL-8steps-CFG-lora.safetensors"

if [ -f "$LORA_PATH" ]; then
    SIZE=$(du -sh "$LORA_PATH" | cut -f1)
    echo "✅ LoRA already exists ($SIZE) — skipping download."
else
    echo ""
    echo "⬇️  Downloading Hyper-SD 8-Step LoRA (~400MB)..."
    aria2c \
        -c \
        -x 8 \
        -s 8 \
        -k 1M \
        --file-allocation=none \
        --console-log-level=notice \
        --dir="$LORAS_DIR" \
        --out="$LORA_NAME" \
        "$LORA_URL"
    echo "✅ LoRA downloaded!"
fi

# ─── Final summary ────────────────────────────────────────────────────────────
echo ""
echo "================================================================"
echo "  ✅ All models ready in Network Volume!"
echo ""
echo "  Volume structure:"
find "$MODELS_DIR" -name "*.safetensors" -printf "    %s bytes  %f\n" 2>/dev/null \
    || ls -lh "$CHECKPOINTS_DIR" "$LORAS_DIR" 2>/dev/null || true
echo ""
echo "  Next steps:"
echo "  1. Terminate this temporary pod"
echo "  2. Attach this volume to your serverless endpoint"
echo "  3. Cold start will now be ~25 seconds (no download needed!)"
echo "================================================================"

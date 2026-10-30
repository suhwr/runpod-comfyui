#!/usr/bin/env bash
# ==============================================================================
# setup_volume.sh — Dual-Model Population Script for Network Volume
#
# Models downloaded:
#   1. Nova Anime AM (2.9B) [Anima DiT + Qwen Text Encoder + Qwen VAE]
#   2. NoobAI-XL v1.1 [SDXL Native]
# ==============================================================================
set -e

VOLUME_ROOT="/runpod-volume"
MODELS_DIR="$VOLUME_ROOT/models"
DIFFUSION_DIR="$MODELS_DIR/diffusion_models"
TEXT_ENCODER_DIR="$MODELS_DIR/text_encoders"
VAE_DIR="$MODELS_DIR/vae"
CHECKPOINTS_DIR="$MODELS_DIR/checkpoints"

echo "================================================================"
echo "  Dual-Model Network Volume Setup Script"
echo "  Target: $VOLUME_ROOT"
echo "================================================================"

if [ ! -d "$VOLUME_ROOT" ]; then
    echo "❌ Network Volume not found at $VOLUME_ROOT"
    exit 1
fi

mkdir -p "$DIFFUSION_DIR" "$TEXT_ENCODER_DIR" "$VAE_DIR" "$CHECKPOINTS_DIR"

if ! command -v aria2c >/dev/null 2>&1; then
    echo "📦 Installing aria2..."
    apt-get update -qq && apt-get install -y -qq aria2
fi

# ─── 1. Nova Anime AM (2.9B) UNet (~5.5GB) ──────────────────────────────────
NOVA_UNET_NAME="novaAnimeAM_v5029B.safetensors"
NOVA_UNET_URL="https://huggingface.co/Kutches/Anim4/resolve/main/novaAnimeAM_v5029B.safetensors"

if [ -f "$DIFFUSION_DIR/$NOVA_UNET_NAME" ]; then
    echo "✅ Nova UNet already exists — skipping download."
else
    echo "⬇️ Downloading Nova Anime AM UNet (~5.5GB)..."
    aria2c -c -x 16 -s 16 -k 1M --file-allocation=none --dir="$DIFFUSION_DIR" --out="$NOVA_UNET_NAME" "$NOVA_UNET_URL"
    echo "✅ Nova UNet downloaded!"
fi

# ─── 2. Qwen Text Encoder (~1.1GB) ──────────────────────────────────────────
NOVA_CLIP_NAME="qwen_3_06b_base.safetensors"
NOVA_CLIP_URL="https://huggingface.co/circlestone-labs/Anima/resolve/main/split_files/text_encoders/qwen_3_06b_base.safetensors"

if [ -f "$TEXT_ENCODER_DIR/$NOVA_CLIP_NAME" ]; then
    echo "✅ Qwen Text Encoder already exists — skipping download."
else
    echo "⬇️ Downloading Qwen Text Encoder (~1.1GB)..."
    aria2c -c -x 8 -s 8 -k 1M --file-allocation=none --dir="$TEXT_ENCODER_DIR" --out="$NOVA_CLIP_NAME" "$NOVA_CLIP_URL"
    echo "✅ Qwen Text Encoder downloaded!"
fi

# ─── 3. Qwen VAE (~240MB) ───────────────────────────────────────────────────
NOVA_VAE_NAME="qwen_image_vae.safetensors"
NOVA_VAE_URL="https://huggingface.co/circlestone-labs/Anima/resolve/main/split_files/vae/qwen_image_vae.safetensors"

if [ -f "$VAE_DIR/$NOVA_VAE_NAME" ]; then
    echo "✅ Qwen VAE already exists — skipping download."
else
    echo "⬇️ Downloading Qwen VAE (~240MB)..."
    aria2c -c -x 8 -s 8 -k 1M --file-allocation=none --dir="$VAE_DIR" --out="$NOVA_VAE_NAME" "$NOVA_VAE_URL"
    echo "✅ Qwen VAE downloaded!"
fi

# ─── 4. NoobAI-XL v1.1 Checkpoint (~7.1GB) ─────────────────────────────────
NOOBAI_CKPT_NAME="NoobAI-XL-v1.1.safetensors"
NOOBAI_CKPT_URL="https://huggingface.co/Laxhar/noobai-XL-1.1/resolve/main/NoobAI-XL-v1.1.safetensors"

if [ -f "$CHECKPOINTS_DIR/$NOOBAI_CKPT_NAME" ]; then
    echo "✅ NoobAI-XL checkpoint already exists — skipping download."
else
    echo "⬇️ Downloading NoobAI-XL v1.1 Checkpoint (~7.1GB)..."
    aria2c -c -x 16 -s 16 -k 1M --file-allocation=none --dir="$CHECKPOINTS_DIR" --out="$NOOBAI_CKPT_NAME" "$NOOBAI_CKPT_URL"
    echo "✅ NoobAI-XL downloaded!"
fi

echo ""
echo "================================================================"
echo "  ✅ All Dual-Model components populated in Network Volume!"
echo "================================================================"

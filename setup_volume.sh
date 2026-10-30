#!/usr/bin/env bash
# ==============================================================================
# setup_volume.sh — Pure-DiT Trio Model Population Script for Network Volume
#
# Models downloaded:
#   1. Nova Anime AM v6.0 (2.9B) [Anima DiT 2D Flagship]
#   2. Nova Orange AM (2.9B) [Anima DiT 2.5D Semi-Realistic]
#   3. SilvermoonMix Anima Evolved (2.9B) [Anima DiT Stable Hands & Soft Shading]
#   4. Shared Qwen 2.5 (3B) Text Encoder & Qwen Image VAE
# ==============================================================================
set -e

VOLUME_ROOT="/runpod-volume"
MODELS_DIR="$VOLUME_ROOT/models"
DIFFUSION_DIR="$MODELS_DIR/diffusion_models"
TEXT_ENCODER_DIR="$MODELS_DIR/text_encoders"
VAE_DIR="$MODELS_DIR/vae"

echo "================================================================"
echo "  Pure-DiT Trio Model Network Volume Setup Script"
echo "  Target: $VOLUME_ROOT"
echo "================================================================"

if [ ! -d "$VOLUME_ROOT" ]; then
    echo "❌ Network Volume not found at $VOLUME_ROOT"
    exit 1
fi

mkdir -p "$DIFFUSION_DIR" "$TEXT_ENCODER_DIR" "$VAE_DIR"

if ! command -v aria2c >/dev/null 2>&1; then
    echo "📦 Installing aria2..."
    apt-get update -qq && apt-get install -y -qq aria2
fi

# ─── 1. Nova Anime AM v6.0 (2.9B) UNet (~5.8GB) ─────────────────────────────
NOVA_UNET_NAME="novaAnimeAM_v6029B.safetensors"
NOVA_UNET_URL="https://huggingface.co/mogaru99/novaAnimeAM_v6029B/resolve/main/novaAnimeAM_v6029B.safetensors"

if [ -f "$DIFFUSION_DIR/$NOVA_UNET_NAME" ]; then
    echo "✅ Nova Anime AM v6.0 UNet already exists — skipping download."
else
    echo "⬇️ Downloading Nova Anime AM v6.0 UNet (~5.8GB)..."
    aria2c -c -x 16 -s 16 -k 1M --file-allocation=none --dir="$DIFFUSION_DIR" --out="$NOVA_UNET_NAME" "$NOVA_UNET_URL"
    echo "✅ Nova Anime AM v6.0 UNet downloaded!"
fi

# ─── 2. Nova Orange AM (2.9B) UNet (~5.5GB) ─────────────────────────────────
ORANGE_UNET_NAME="novaOrangeAM_v4029B.safetensors"
ORANGE_UNET_URL="https://huggingface.co/Kutches/Anim4/resolve/main/novaOrangeAM_v4029B.safetensors"

if [ -f "$DIFFUSION_DIR/$ORANGE_UNET_NAME" ]; then
    echo "✅ Nova Orange AM UNet already exists — skipping download."
else
    echo "⬇️ Downloading Nova Orange AM UNet (~5.5GB)..."
    aria2c -c -x 16 -s 16 -k 1M --file-allocation=none --dir="$DIFFUSION_DIR" --out="$ORANGE_UNET_NAME" "$ORANGE_UNET_URL"
    echo "✅ Nova Orange AM UNet downloaded!"
fi

# ─── 3. SilvermoonMix Anima Evolved (2.9B) UNet (~5.8GB) ─────────────────────
SILVERMOON_UNET_NAME="SilvermoonMix-Anima29B-Evolved-V2.3.safetensors"
SILVERMOON_UNET_URL="https://huggingface.co/silvermoong/SilvermoonMix-Anima-Evolved/resolve/main/SilvermoonMix-Anima29B-Evolved-V2.3.safetensors"

if [ -f "$DIFFUSION_DIR/$SILVERMOON_UNET_NAME" ]; then
    echo "✅ SilvermoonMix UNet already exists — skipping download."
else
    echo "⬇️ Downloading SilvermoonMix UNet (~5.8GB)..."
    aria2c -c -x 16 -s 16 -k 1M --file-allocation=none --dir="$DIFFUSION_DIR" --out="$SILVERMOON_UNET_NAME" "$SILVERMOON_UNET_URL"
    echo "✅ SilvermoonMix UNet downloaded!"
fi

# ─── 4. Shared Qwen Text Encoder (~1.1GB) ───────────────────────────────────
NOVA_CLIP_NAME="qwen_3_06b_base.safetensors"
NOVA_CLIP_URL="https://huggingface.co/circlestone-labs/Anima/resolve/main/split_files/text_encoders/qwen_3_06b_base.safetensors"

if [ -f "$TEXT_ENCODER_DIR/$NOVA_CLIP_NAME" ]; then
    echo "✅ Qwen Text Encoder already exists — skipping download."
else
    echo "⬇️ Downloading Qwen Text Encoder (~1.1GB)..."
    aria2c -c -x 8 -s 8 -k 1M --file-allocation=none --dir="$TEXT_ENCODER_DIR" --out="$NOVA_CLIP_NAME" "$NOVA_CLIP_URL"
    echo "✅ Qwen Text Encoder downloaded!"
fi

# ─── 5. Shared Qwen VAE (~240MB) ────────────────────────────────────────────
NOVA_VAE_NAME="qwen_image_vae.safetensors"
NOVA_VAE_URL="https://huggingface.co/circlestone-labs/Anima/resolve/main/split_files/vae/qwen_image_vae.safetensors"

if [ -f "$VAE_DIR/$NOVA_VAE_NAME" ]; then
    echo "✅ Qwen VAE already exists — skipping download."
else
    echo "⬇️ Downloading Qwen VAE (~240MB)..."
    aria2c -c -x 8 -s 8 -k 1M --file-allocation=none --dir="$VAE_DIR" --out="$NOVA_VAE_NAME" "$NOVA_VAE_URL"
    echo "✅ Qwen VAE downloaded!"
fi

echo ""
echo "================================================================"
echo "  ✅ All Pure-DiT Trio Model components populated in Network Volume!"
echo "================================================================"

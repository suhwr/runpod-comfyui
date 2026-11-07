#!/usr/bin/env bash
# ==============================================================================
# setup_volume.sh — Pure-DiT Anima Model Population Script for Network Volume
#
# Models downloaded:
#   1. Nova Anime AM v6.0 (2.9B) [Anima DiT 2D Flagship & Default Model]
#   2. Anima-3.8B v1.1 DiT (~8.8GB) [Flagship 3.8B DiT with 52 layers]
#   3. SilvermoonMix Anima Evolved (2.9B) [Anima DiT Aesthetic Art & Soft Shading]
#   4. CircleStone Anima Base v1.0 (2.9B) [Official Pure 2D DiT Base]
#   5. Dual Text Encoders:
#      - Qwen 2.5 3B (0.6B base) text encoder (shared)
#      - Qwen 3.5 4B text encoder (for Anima 3.8B)
#      - Anima 3.8B Expanded Adapter / Semantic Connector v2
#   6. Shared Qwen Image VAE
#   7. Curated high-popularity SOTA LoRA Collection
# ==============================================================================
set -e

VOLUME_ROOT="/runpod-volume"
MODELS_DIR="$VOLUME_ROOT/models"
DIFFUSION_DIR="$MODELS_DIR/diffusion_models"
TEXT_ENCODER_DIR="$MODELS_DIR/text_encoders"
VAE_DIR="$MODELS_DIR/vae"
LORA_DIR="$MODELS_DIR/loras"

echo "================================================================"
echo "  Pure-DiT Anima Model Network Volume Setup Script"
echo "  Target: $VOLUME_ROOT"
echo "================================================================"

if [ ! -d "$VOLUME_ROOT" ]; then
    echo "❌ Network Volume not found at $VOLUME_ROOT"
    exit 1
fi

mkdir -p "$DIFFUSION_DIR" "$TEXT_ENCODER_DIR" "$VAE_DIR" "$LORA_DIR"

if ! command -v aria2c >/dev/null 2>&1; then
    echo "📦 Installing aria2..."
    apt-get update -qq && apt-get install -y -qq aria2
fi

# ─── 1. Nova Anime AM v6.0 (2.9B) UNet (~5.8GB) [DEFAULT MODEL] ───────────────
NOVA_UNET_NAME="novaAnimeAM_v6029B.safetensors"
NOVA_UNET_URL="https://huggingface.co/mogaru99/novaAnimeAM_v6029B/resolve/main/novaAnimeAM_v6029B.safetensors"

if [ -f "$DIFFUSION_DIR/$NOVA_UNET_NAME" ]; then
    echo "✅ Nova Anime AM v6.0 UNet already exists — skipping download."
else
    echo "⬇️ Downloading Nova Anime AM v6.0 UNet (~5.8GB)..."
    aria2c -c -x 16 -s 16 -k 1M --file-allocation=none --dir="$DIFFUSION_DIR" --out="$NOVA_UNET_NAME" "$NOVA_UNET_URL"
    echo "✅ Nova Anime AM v6.0 UNet downloaded!"
fi

# ─── 2. Anima-3.8B v1.1 UNet (~8.8GB) [52 DiT Blocks Flagship] ─────────────────
ANIMA_38B_UNET_NAME="Anima-3.8B-v1.1.safetensors"
ANIMA_38B_UNET_URL="https://huggingface.co/lylogummy/Anima-3.8B/resolve/main/difussion_models/Anima-3.8B-v1.1.safetensors"

if [ -f "$DIFFUSION_DIR/$ANIMA_38B_UNET_NAME" ]; then
    echo "✅ Anima-3.8B v1.1 UNet already exists — skipping download."
else
    echo "⬇️ Downloading Anima-3.8B v1.1 UNet (~8.8GB)..."
    aria2c -c -x 16 -s 16 -k 1M --file-allocation=none --dir="$DIFFUSION_DIR" --out="$ANIMA_38B_UNET_NAME" "$ANIMA_38B_UNET_URL"
    echo "✅ Anima-3.8B v1.1 UNet downloaded!"
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

# ─── 4. CircleStone Anima Base v1.0 (2.9B) UNet (~4.18GB) [Official Pure Base] ─
ANIMA_BASE_UNET_NAME="anima-base-v1.0.safetensors"
ANIMA_BASE_UNET_URL="https://huggingface.co/circlestone-labs/Anima/resolve/main/split_files/diffusion_models/anima-base-v1.0.safetensors"

if [ -f "$DIFFUSION_DIR/$ANIMA_BASE_UNET_NAME" ]; then
    echo "✅ CircleStone Anima Base v1.0 UNet already exists — skipping download."
else
    echo "⬇️ Downloading CircleStone Anima Base v1.0 UNet (~4.18GB)..."
    aria2c -c -x 16 -s 16 -k 1M --file-allocation=none --dir="$DIFFUSION_DIR" --out="$ANIMA_BASE_UNET_NAME" "$ANIMA_BASE_UNET_URL"
    echo "✅ CircleStone Anima Base v1.0 UNet downloaded!"
fi

# ─── 5. Shared Qwen Native Text Encoder (~1.1GB) ──────────────────────────────
NOVA_CLIP_NAME="qwen_3_06b_base.safetensors"
NOVA_CLIP_URL="https://huggingface.co/circlestone-labs/Anima/resolve/main/split_files/text_encoders/qwen_3_06b_base.safetensors"

if [ -f "$TEXT_ENCODER_DIR/$NOVA_CLIP_NAME" ]; then
    echo "✅ Shared Qwen Text Encoder already exists — skipping download."
else
    echo "⬇️ Downloading Shared Qwen Text Encoder (~1.1GB)..."
    aria2c -c -x 8 -s 8 -k 1M --file-allocation=none --dir="$TEXT_ENCODER_DIR" --out="$NOVA_CLIP_NAME" "$NOVA_CLIP_URL"
    echo "✅ Shared Qwen Text Encoder downloaded!"
fi

# ─── 6. Qwen3.5 4B Text Encoder (~4.78GB) [For Anima 3.8B] ───────────────────
QWEN35_CLIP_NAME="qwen35_4b.safetensors"
QWEN35_CLIP_URL="https://huggingface.co/lylogummy/Anima-3.8B/resolve/main/text_encoders/qwen35_4b.safetensors"

if [ -f "$TEXT_ENCODER_DIR/$QWEN35_CLIP_NAME" ]; then
    echo "✅ Qwen3.5 4B Text Encoder already exists — skipping download."
else
    echo "⬇️ Downloading Qwen3.5 4B Text Encoder (~4.78GB)..."
    aria2c -c -x 16 -s 16 -k 1M --file-allocation=none --dir="$TEXT_ENCODER_DIR" --out="$QWEN35_CLIP_NAME" "$QWEN35_CLIP_URL"
    echo "✅ Qwen3.5 4B Text Encoder downloaded!"
fi

# ─── 7. Anima 3.8B Expanded Adapter / Semantic Connector v2 (~88MB) ───────────
ANIMA_ADAPTER_NAME="Anima-3.8B-expanded_adapter.safetensors"
ANIMA_ADAPTER_URL="https://huggingface.co/lylogummy/Anima-3.8B/resolve/main/text_encoders/Anima-3.8B-expanded_adapter.safetensors"

if [ -f "$TEXT_ENCODER_DIR/$ANIMA_ADAPTER_NAME" ]; then
    echo "✅ Anima 3.8B Expanded Adapter already exists — skipping download."
else
    echo "⬇️ Downloading Anima 3.8B Expanded Adapter (~88MB)..."
    aria2c -c -x 8 -s 8 -k 1M --file-allocation=none --dir="$TEXT_ENCODER_DIR" --out="$ANIMA_ADAPTER_NAME" "$ANIMA_ADAPTER_URL"
    echo "✅ Anima 3.8B Expanded Adapter downloaded!"
fi

# ─── 8. Shared Qwen VAE (~240MB) ──────────────────────────────────────────────
NOVA_VAE_NAME="qwen_image_vae.safetensors"
NOVA_VAE_URL="https://huggingface.co/circlestone-labs/Anima/resolve/main/split_files/vae/qwen_image_vae.safetensors"

if [ -f "$VAE_DIR/$NOVA_VAE_NAME" ]; then
    echo "✅ Qwen VAE already exists — skipping download."
else
    echo "⬇️ Downloading Qwen VAE (~240MB)..."
    aria2c -c -x 8 -s 8 -k 1M --file-allocation=none --dir="$VAE_DIR" --out="$NOVA_VAE_NAME" "$NOVA_VAE_URL"
    echo "✅ Qwen VAE downloaded!"
fi

# ─── 9. Curated SOTA LoRA Collection ──────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/download_loras.sh" ]; then
    bash "$SCRIPT_DIR/download_loras.sh" "$LORA_DIR"
elif [ -f "/app/download_loras.sh" ]; then
    bash "/app/download_loras.sh" "$LORA_DIR"
fi

echo ""
echo "================================================================"
echo "  ✅ All Models (Nova Default, Anima 3.8B, Silvermoon, Base) & Curated LoRAs Populated!"
echo "================================================================"

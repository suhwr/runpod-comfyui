#!/usr/bin/env bash
set -e

CHECKPOINT_DIR="/app/ComfyUI/models/checkpoints"
LORA_DIR="/app/ComfyUI/models/loras"
mkdir -p "$CHECKPOINT_DIR" "$LORA_DIR"

MODEL_NAME="${CHECKPOINT_NAME:-NoobAI-XL-v1.1.safetensors}"
MODEL_PATH="$CHECKPOINT_DIR/$MODEL_NAME"

LORA_NAME="${LORA_NAME:-Hyper-SDXL-8steps-CFG-lora.safetensors}"
LORA_PATH="$LORA_DIR/$LORA_NAME"

# Check if model exists or download if CHECKPOINT_URL is provided
if [ ! -f "$MODEL_PATH" ] && [ -n "$CHECKPOINT_URL" ]; then
    echo "⬇️ Downloading model $MODEL_NAME from $CHECKPOINT_URL..."
    curl -L --retry 3 --connect-timeout 30 -o "$MODEL_PATH" "$CHECKPOINT_URL"
    echo "✅ Model $MODEL_NAME downloaded successfully!"
fi

# Check if LoRA exists or download if LORA_URL is provided
if [ ! -f "$LORA_PATH" ] && [ -n "$LORA_URL" ]; then
    echo "⬇️ Downloading LoRA $LORA_NAME from $LORA_URL..."
    curl -L --retry 3 --connect-timeout 30 -o "$LORA_PATH" "$LORA_URL"
    echo "✅ LoRA $LORA_NAME downloaded successfully!"
fi

echo "🚀 Starting ComfyUI Serverless Worker..."
exec python3 -u /app/handler.py

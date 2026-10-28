#!/usr/bin/env bash
set -e

CHECKPOINT_DIR="/app/ComfyUI/models/checkpoints"
mkdir -p "$CHECKPOINT_DIR"

MODEL_NAME="${CHECKPOINT_NAME:-animagine-xl-3.1.safetensors}"
MODEL_PATH="$CHECKPOINT_DIR/$MODEL_NAME"

# Check if model exists or download if CHECKPOINT_URL is provided
if [ ! -f "$MODEL_PATH" ] && [ -n "$CHECKPOINT_URL" ]; then
    echo "⬇️ Downloading model $MODEL_NAME from $CHECKPOINT_URL..."
    curl -L --retry 3 --connect-timeout 30 -o "$MODEL_PATH" "$CHECKPOINT_URL"
    echo "✅ Model $MODEL_NAME downloaded successfully!"
fi

echo "🚀 Starting ComfyUI Serverless Worker..."
exec python3 -u /app/handler.py

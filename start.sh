#!/usr/bin/env bash
set -e

CHECKPOINT_DIR="/app/ComfyUI/models/checkpoints"
LORA_DIR="/app/ComfyUI/models/loras"
mkdir -p "$CHECKPOINT_DIR" "$LORA_DIR"

MODEL_NAME="${CHECKPOINT_NAME:-NoobAI-XL-v1.1.safetensors}"
MODEL_PATH="$CHECKPOINT_DIR/$MODEL_NAME"

LORA_NAME="${LORA_NAME:-Hyper-SDXL-8steps-CFG-lora.safetensors}"
LORA_PATH="$LORA_DIR/$LORA_NAME"

# 1. Check & Download LoRA if not present (~400MB)
if [ ! -f "$LORA_PATH" ] && [ -n "$LORA_URL" ]; then
    echo "⬇️ Downloading LoRA $LORA_NAME from $LORA_URL..."
    curl -L --retry 3 --connect-timeout 30 -o "$LORA_PATH" "$LORA_URL"
    echo "✅ LoRA $LORA_NAME downloaded successfully!"
fi

# 2. Check & Download Checkpoint if not present (~7.1GB)
if [ ! -f "$MODEL_PATH" ] && [ -n "$CHECKPOINT_URL" ]; then
    echo "⬇️ Downloading Checkpoint $MODEL_NAME from $CHECKPOINT_URL..."
    echo "⏳ Note: Model is ~7.1GB. Download is in progress, please check progress below..."
    curl -L -# --retry 3 --connect-timeout 30 -o "$MODEL_PATH" "$CHECKPOINT_URL"
    echo "✅ Checkpoint $MODEL_NAME downloaded successfully!"
fi

# 3. Launch headless ComfyUI in the background
echo "🚀 Launching headless ComfyUI server on 127.0.0.1:8188..."
cd /app/ComfyUI
python3 main.py \
    --listen 127.0.0.1 \
    --port 8188 \
    --highvram \
    --dont-upcast-attention \
    --disable-auto-launch &

COMFY_PID=$!
echo "ComfyUI daemon started with PID: $COMFY_PID"

# 4. Wait until ComfyUI responds 200 OK
echo "⏳ Waiting for ComfyUI to become ready..."
MAX_WAIT=120
WAITED=0
while ! curl -s -f http://127.0.0.1:8188/ > /dev/null 2>&1; do
    if ! kill -0 $COMFY_PID 2>/dev/null; then
        echo "❌ ComfyUI process crashed on boot! Check logs above."
        wait $COMFY_PID
        exit 1
    fi
    sleep 2
    WAITED=$((WAITED + 2))
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "❌ ComfyUI timed out after $MAX_WAIT seconds."
        exit 1
    fi
done

echo "✅ ComfyUI is up and running healthy!"

# 5. Start the serverless handler event loop
echo "🚀 Starting serverless worker listener..."
cd /app
exec python3 -u /app/handler.py

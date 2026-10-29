#!/usr/bin/env bash
set -e

# ==============================================================================
# COMPILER CHECK: Triton requires a C compiler (gcc) for JIT kernel compilation
# ==============================================================================
if ! command -v gcc >/dev/null 2>&1; then
    echo "🔧 C compiler (gcc) not found! Installing build-essential for Triton..."
    apt-get update -qq && apt-get install -y -qq --no-install-recommends build-essential gcc || true
fi
export CC="$(command -v gcc || echo '/usr/bin/gcc')"

CHECKPOINT_DIR="/app/ComfyUI/models/checkpoints"
LORA_DIR="/app/ComfyUI/models/loras"
mkdir -p "$CHECKPOINT_DIR" "$LORA_DIR"

MODEL_NAME="${CHECKPOINT_NAME:-NoobAI-XL-v1.1.safetensors}"
MODEL_PATH="$CHECKPOINT_DIR/$MODEL_NAME"

LORA_NAME="${LORA_NAME:-Hyper-SDXL-8steps-CFG-lora.safetensors}"
LORA_PATH="$LORA_DIR/$LORA_NAME"

# ==============================================================================
# PATCH: Safety net for comfy_kitchen list[int] incompatibility with PyTorch < 2.7
# comfy_kitchen uses PEP-585 built-in generics (list[int]) which are only
# supported by torch.library.infer_schema in PyTorch >= 2.7.
# Dockerfile now uses PyTorch 2.7.0 so this normally won't be needed,
# but we keep it as a safety net in case the running image is older.
# ==============================================================================
CKITCHEN_SITE="$(python3 -c 'import site; print(site.getsitepackages()[0])')/comfy_kitchen"

# Check PyTorch version — only patch if < 2.7
TORCH_VER=$(python3 -c "import torch; v=torch.__version__; parts=v.split('.')[:2]; print(int(parts[0])*100+int(parts[1]))" 2>/dev/null || echo "0")
if [ "$TORCH_VER" -lt 207 ] && [ -d "$CKITCHEN_SITE" ]; then
    echo "⚠️  PyTorch < 2.7 detected — patching comfy_kitchen for list[int] compatibility..."

    find "$CKITCHEN_SITE" -name "*.py" | while read -r f; do
        if grep -qE ": list\[|: dict\[|: tuple\[|: set\[" "$f" 2>/dev/null; then
            # Inject typing import at top if not present
            if ! grep -q "^import typing" "$f"; then
                sed -i '1s/^/import typing\n/' "$f"
            fi
            # Replace bare PEP-585 builtin generics with typing equivalents
            sed -i \
                -e 's/: list\[int\]/: typing.List[int]/g' \
                -e 's/: list\[float\]/: typing.List[float]/g' \
                -e 's/: list\[bool\]/: typing.List[bool]/g' \
                -e 's/: list\[str\]/: typing.List[str]/g' \
                -e 's/: list\[torch\.Tensor\]/: typing.List[torch.Tensor]/g' \
                -e 's/: list\[typing/: typing.List[typing/g' \
                -e 's/: dict\[/: typing.Dict[/g' \
                -e 's/: tuple\[/: typing.Tuple[/g' \
                -e 's/: set\[/: typing.Set[/g' \
                "$f"
        fi
    done

    echo "✅ comfy_kitchen patch applied!"
elif [ "$TORCH_VER" -ge 207 ]; then
    echo "✅ PyTorch >= 2.7 detected — comfy_kitchen patch not needed."
fi

# ==============================================================================

# 1. Volume Auto-Detection (Zero Cold-Start if using persistent Network Volume)
#    Checks both flat and nested /models/checkpoints + /models/loras layout
for VOL in "/runpod-volume" "/workspace" "/volume"; do
    [ -d "$VOL" ] || continue

    # Checkpoint auto-symlink
    for CKPT_PATH in "$VOL/models/checkpoints/$MODEL_NAME" "$VOL/models/$MODEL_NAME" "$VOL/$MODEL_NAME"; do
        if [ -f "$CKPT_PATH" ]; then
            echo "⚡ Network Volume checkpoint found! Symlinking $CKPT_PATH -> $MODEL_PATH"
            ln -sf "$CKPT_PATH" "$MODEL_PATH"
            break
        fi
    done

    # LoRA auto-symlink
    for LORA_VOL_PATH in "$VOL/models/loras/$LORA_NAME" "$VOL/models/$LORA_NAME" "$VOL/$LORA_NAME"; do
        if [ -f "$LORA_VOL_PATH" ]; then
            echo "⚡ Network Volume LoRA found! Symlinking $LORA_VOL_PATH -> $LORA_PATH"
            ln -sf "$LORA_VOL_PATH" "$LORA_PATH"
            break
        fi
    done

    # If checkpoint is now resolved, no need to check other volumes
    [ -f "$MODEL_PATH" ] && break
done

# 2. Check & Download LoRA if not present (~400MB)
if [ ! -f "$LORA_PATH" ] && [ -n "$LORA_URL" ]; then
    echo "⬇️ Downloading LoRA $LORA_NAME from $LORA_URL..."
    if command -v aria2c >/dev/null 2>&1; then
        aria2c -c -x 8 -s 8 -k 1M --dir="$LORA_DIR" --out="$LORA_NAME" "$LORA_URL"
    else
        curl -L --retry 3 --connect-timeout 30 -o "$LORA_PATH" "$LORA_URL"
    fi
    echo "✅ LoRA $LORA_NAME downloaded successfully!"
fi

# 3. Check & Download Checkpoint if not present (~7.1GB)
if [ ! -f "$MODEL_PATH" ] && [ -n "$CHECKPOINT_URL" ]; then
    echo "⬇️ Downloading Checkpoint $MODEL_NAME from $CHECKPOINT_URL..."
    echo "⚡ Using multi-stream accelerator for maximum download throughput..."
    if command -v aria2c >/dev/null 2>&1; then
        aria2c -c -x 16 -s 16 -k 1M --dir="$CHECKPOINT_DIR" --out="$MODEL_NAME" "$CHECKPOINT_URL"
    else
        curl -L -# --retry 3 --connect-timeout 30 -o "$MODEL_PATH" "$CHECKPOINT_URL"
    fi
    echo "✅ Checkpoint $MODEL_NAME downloaded successfully!"
fi

# 4. Launch headless ComfyUI in the background with speed optimizations
echo "🚀 Launching headless ComfyUI daemon on 127.0.0.1:8188 (--fast --highvram)..."
cd /app/ComfyUI
python3 main.py \
    --listen 127.0.0.1 \
    --port 8188 \
    --fast \
    --highvram \
    --disable-auto-launch &

COMFY_PID=$!
echo "ComfyUI daemon started with PID: $COMFY_PID"

# 5. Wait until ComfyUI responds 200 OK
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

# 6. Start the serverless handler event loop
echo "🚀 Starting serverless worker listener..."
cd /app
exec python3 -u /app/handler.py

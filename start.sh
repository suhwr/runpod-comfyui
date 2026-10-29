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

DIFFUSION_DIR="/app/ComfyUI/models/diffusion_models"
TEXT_ENCODER_DIR="/app/ComfyUI/models/text_encoders"
VAE_DIR="/app/ComfyUI/models/vae"
CHECKPOINT_DIR="/app/ComfyUI/models/checkpoints"
mkdir -p "$DIFFUSION_DIR" "$TEXT_ENCODER_DIR" "$VAE_DIR" "$CHECKPOINT_DIR"

# ─── Dual Model Config ────────────────────────────────────────────────────────
# Model 1: Nova Anime AM v6.0 (2.9B) [Default]
NOVA_UNET_NAME="${NOVA_UNET_NAME:-novaAnimeAM_v6029B.safetensors}"
NOVA_UNET_URL="${NOVA_UNET_URL:-https://huggingface.co/mogaru99/novaAnimeAM_v6029B/resolve/main/novaAnimeAM_v6029B.safetensors}"

NOVA_CLIP_NAME="${NOVA_CLIP_NAME:-qwen_3_06b_base.safetensors}"
NOVA_CLIP_URL="${NOVA_CLIP_URL:-https://huggingface.co/circlestone-labs/Anima/resolve/main/split_files/text_encoders/qwen_3_06b_base.safetensors}"

NOVA_VAE_NAME="${NOVA_VAE_NAME:-qwen_image_vae.safetensors}"
NOVA_VAE_URL="${NOVA_VAE_URL:-https://huggingface.co/circlestone-labs/Anima/resolve/main/split_files/vae/qwen_image_vae.safetensors}"

# Model 2: NoobAI-XL v1.1 [SDXL Native]
NOOBAI_CKPT_NAME="${NOOBAI_CKPT_NAME:-NoobAI-XL-v1.1.safetensors}"
NOOBAI_CKPT_URL="${NOOBAI_CKPT_URL:-https://huggingface.co/Laxhar/noobai-XL-1.1/resolve/main/NoobAI-XL-v1.1.safetensors}"

# ==============================================================================
# 1. Volume Auto-Detection (Zero Cold-Start if using persistent Network Volume)
# ==============================================================================
for VOL in "/runpod-volume" "/workspace" "/volume"; do
    [ -d "$VOL" ] || continue

    # Auto-symlink Nova components from volume
    for FPATH in "$VOL/models/diffusion_models/$NOVA_UNET_NAME" "$VOL/models/$NOVA_UNET_NAME" "$VOL/$NOVA_UNET_NAME"; do
        if [ -f "$FPATH" ]; then
            echo "⚡ Found Nova UNet in volume! Symlinking $FPATH -> $DIFFUSION_DIR/$NOVA_UNET_NAME"
            ln -sf "$FPATH" "$DIFFUSION_DIR/$NOVA_UNET_NAME"
            break
        fi
    done

    for FPATH in "$VOL/models/text_encoders/$NOVA_CLIP_NAME" "$VOL/models/$NOVA_CLIP_NAME" "$VOL/$NOVA_CLIP_NAME"; do
        if [ -f "$FPATH" ]; then
            echo "⚡ Found Qwen CLIP in volume! Symlinking $FPATH -> $TEXT_ENCODER_DIR/$NOVA_CLIP_NAME"
            ln -sf "$FPATH" "$TEXT_ENCODER_DIR/$NOVA_CLIP_NAME"
            break
        fi
    done

    for FPATH in "$VOL/models/vae/$NOVA_VAE_NAME" "$VOL/models/$NOVA_VAE_NAME" "$VOL/$NOVA_VAE_NAME"; do
        if [ -f "$FPATH" ]; then
            echo "⚡ Found Qwen VAE in volume! Symlinking $FPATH -> $VAE_DIR/$NOVA_VAE_NAME"
            ln -sf "$FPATH" "$VAE_DIR/$NOVA_VAE_NAME"
            break
        fi
    done

    # Auto-symlink NoobAI-XL if in volume
    for FPATH in "$VOL/models/checkpoints/$NOOBAI_CKPT_NAME" "$VOL/models/$NOOBAI_CKPT_NAME" "$VOL/$NOOBAI_CKPT_NAME"; do
        if [ -f "$FPATH" ]; then
            echo "⚡ Found NoobAI-XL in volume! Symlinking $FPATH -> $CHECKPOINT_DIR/$NOOBAI_CKPT_NAME"
            ln -sf "$FPATH" "$CHECKPOINT_DIR/$NOOBAI_CKPT_NAME"
            break
        fi
    done
done

# ==============================================================================
# 2. Check & Download Nova Anime AM Components (Default Model)
# ==============================================================================
if [ -f "$DIFFUSION_DIR/$NOVA_UNET_NAME" ]; then
    echo "⚡ Nova UNet is already available: $DIFFUSION_DIR/$NOVA_UNET_NAME"
else
    echo "⬇️ Downloading Nova Anime AM UNet ($NOVA_UNET_NAME)..."
    if command -v aria2c >/dev/null 2>&1; then
        aria2c -c -x 16 -s 16 -k 1M --file-allocation=none --dir="$DIFFUSION_DIR" --out="$NOVA_UNET_NAME" "$NOVA_UNET_URL"
    else
        curl -L -# --retry 3 --connect-timeout 30 -o "$DIFFUSION_DIR/$NOVA_UNET_NAME" "$NOVA_UNET_URL"
    fi
    echo "✅ Nova UNet downloaded successfully!"
fi

if [ -f "$TEXT_ENCODER_DIR/$NOVA_CLIP_NAME" ]; then
    echo "⚡ Qwen Text Encoder is already available: $TEXT_ENCODER_DIR/$NOVA_CLIP_NAME"
else
    echo "⬇️ Downloading Qwen Text Encoder ($NOVA_CLIP_NAME)..."
    if command -v aria2c >/dev/null 2>&1; then
        aria2c -c -x 8 -s 8 -k 1M --file-allocation=none --dir="$TEXT_ENCODER_DIR" --out="$NOVA_CLIP_NAME" "$NOVA_CLIP_URL"
    else
        curl -L -# --retry 3 --connect-timeout 30 -o "$TEXT_ENCODER_DIR/$NOVA_CLIP_NAME" "$NOVA_CLIP_URL"
    fi
    echo "✅ Qwen Text Encoder downloaded successfully!"
fi

if [ -f "$VAE_DIR/$NOVA_VAE_NAME" ]; then
    echo "⚡ Qwen VAE is already available: $VAE_DIR/$NOVA_VAE_NAME"
else
    echo "⬇️ Downloading Qwen VAE ($NOVA_VAE_NAME)..."
    if command -v aria2c >/dev/null 2>&1; then
        aria2c -c -x 8 -s 8 -k 1M --file-allocation=none --dir="$VAE_DIR" --out="$NOVA_VAE_NAME" "$NOVA_VAE_URL"
    else
        curl -L -# --retry 3 --connect-timeout 30 -o "$VAE_DIR/$NOVA_VAE_NAME" "$NOVA_VAE_URL"
    fi
    echo "✅ Qwen VAE downloaded successfully!"
fi

# ==============================================================================
# 3. Check & Download NoobAI-XL v1.1 Checkpoint (Optional / Secondary Model)
#    If not already baked into the image, downloads in background without
#    blocking worker startup so Nova requests can begin immediately!
# ==============================================================================
if [ -f "$CHECKPOINT_DIR/$NOOBAI_CKPT_NAME" ]; then
    echo "⚡ NoobAI-XL v1.1 is already available: $CHECKPOINT_DIR/$NOOBAI_CKPT_NAME"
elif [ "${DOWNLOAD_NOOBAI:-true}" = "true" ]; then
    echo "⬇️ Downloading NoobAI-XL v1.1 in background (non-blocking)..."
    (
        if command -v aria2c >/dev/null 2>&1; then
            aria2c -c -x 16 -s 16 -k 1M --file-allocation=none --dir="$CHECKPOINT_DIR" --out="$NOOBAI_CKPT_NAME" "$NOOBAI_CKPT_URL"
        else
            curl -L -# --retry 3 --connect-timeout 30 -o "$CHECKPOINT_DIR/$NOOBAI_CKPT_NAME" "$NOOBAI_CKPT_URL"
        fi
        echo "✅ NoobAI-XL v1.1 background download complete!"
    ) &
fi

# ==============================================================================
# 4. Launch headless ComfyUI daemon in the background
# ==============================================================================
echo "🚀 Launching headless ComfyUI daemon on 127.0.0.1:8188 (--fast --highvram --disable-metadata)..."
cd /app/ComfyUI
python3 main.py \
    --listen 127.0.0.1 \
    --port 8188 \
    --fast \
    --highvram \
    --disable-auto-launch \
    --disable-metadata &

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
    sleep 1
    WAITED=$((WAITED + 1))
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "❌ ComfyUI timed out after $MAX_WAIT seconds."
        exit 1
    fi
done

echo "✅ ComfyUI is up and running healthy with Dual-Model support!"

# 6. Pre-warm default model into GPU VRAM
#    In Scale-to-Zero serverless mode, disabled by default to save 15s cold-start latency!
#    The real user job loads the model directly on first inference.
if [ "${PREWARM_MODEL:-false}" = "true" ]; then
    echo "🔥 Running VRAM Pre-warming..."
    python3 /app/warmup.py || true
fi

# 7. Start the serverless worker listener
echo "🚀 Starting serverless worker listener..."
cd /app
exec python3 -u /app/handler.py

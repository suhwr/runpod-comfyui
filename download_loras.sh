#!/usr/bin/env bash
# ==============================================================================
# download_loras.sh — Curated SOTA LoRA Collection for Pure-DiT Anima Architecture
#
# Curated based on top Civitai/HF download statistics & visual quality:
#   1. Anima Turbo v1.1 (Anti-Slop 8-10 steps step distillation) [80k+ DL]
#   2. Anima Turbo 4-Step (Extreme speed preview)
#   3. Highres Aesthetic Booster (Micro-details, lineart & eye clarity) [47k+ DL]
#   4. RL Anatomy & Hand Fix (Reinforcement learning anatomy & hands) [14k+ DL]
#   5. Context Detailer (Hair strands, fabric folds & clothing drapery) [38k+ DL]
#   6. Rendering Detailer (Sharp brush strokes & crisp textures)
#   7. NoobAI Modern Anime Style (Vibrant 2D Danbooru / flat cel shading) [10k+ DL]
#   8. Hand-Drawn Sketch (Yamimatsu7 - pencil sketch & thin lineart)
#   9. Classic Watercolor (Ken Sugimori vintage watercolor illustration)
#
# Obsolete/low-download/broken LoRAs purged:
#   - Greg Rutkowski (causes muddy 2.5D oil paint leak)
#   - Helltaker, SailorMoon, DragonBall, Gunsmith (outdated 28-block preview LoRAs)
# ==============================================================================
set -e

TARGET_DIR="${1:-/app/ComfyUI/models/loras}"
mkdir -p "$TARGET_DIR"

download_lora() {
    local filename="$1"
    local url="$2"
    local desc="$3"

    if [ -f "$TARGET_DIR/$filename" ]; then
        echo "⚡ [LoRA Available] $filename ($desc)"
        return 0
    fi

    echo "⬇️ Downloading LoRA: $filename ($desc)..."
    if command -v aria2c >/dev/null 2>&1; then
        aria2c -c -x 8 -s 8 -k 1M --file-allocation=none --dir="$TARGET_DIR" --out="$filename" "$url" || true
    else
        curl -L -s --retry 3 --connect-timeout 30 -o "$TARGET_DIR/$filename" "$url" || true
    fi

    if [ -f "$TARGET_DIR/$filename" ]; then
        echo "✅ Downloaded: $filename"
    else
        echo "⚠️ Failed to download: $filename"
    fi
}

echo "================================================================"
echo "  Baking / Syncing Curated LoRA Collection into: $TARGET_DIR"
echo "================================================================"

# 1. Flagship Anima Turbo v1.1 (Anti-Slop 8-10 steps)
download_lora "Anima_Turbo_v1.1.safetensors" \
    "https://huggingface.co/watanbe4112/Anima_Turbo_LoRA/resolve/main/anima-turbo-lora-v0.2.safetensors" \
    "Anima Turbo v1.1 - 8-10 steps anti-slop distillation"

# 2. Ultra Fast 4-step Turbo
download_lora "anima_turbo_4step_v3.safetensors" \
    "https://huggingface.co/sorryhyun/anima-turbo-4step/resolve/main/anima_turbo_4step_v3.safetensors" \
    "4-step extreme fast generation"

# 3. Highres Aesthetic Booster
download_lora "anima-highres-aesthetic-boost.safetensors" \
    "https://huggingface.co/circlestone-labs/Anima-Official-LoRAs/resolve/main/anima-highres-aesthetic-boost.safetensors" \
    "Official micro-details and clean lineart booster"

# 4. RL Anatomy & Hand Fix
download_lora "anima-rl-v0.1.safetensors" \
    "https://huggingface.co/circlestone-labs/Anima-Official-LoRAs/resolve/main/anima-rl-v0.1.safetensors" \
    "Official RL prompt alignment & anatomy enhancement"

# 5. Context Detailer (Hair strands, fabric drapery, clothing folds)
download_lora "anima_context_detailer_base10.safetensors" \
    "https://huggingface.co/Sybamboo/anima-detail-tweaker-backup/resolve/main/loras/anima_context_detailer_base10.safetensors" \
    "Hair strands, clothing folds and fabric drapery detailer"

# 6. Rendering Detailer (Stroke crispness and texture sharpness)
download_lora "rendering_detailer_base10-000400.safetensors" \
    "https://huggingface.co/Sybamboo/anima-detail-tweaker-backup/resolve/main/loras/rendering_detailer_base10-000400.safetensors" \
    "Rendering stroke sharpness and texture enhancer"

# 7. NoobAI Modern Anime Style & 2D Cel Shading (Danbooru vibrant flat illustration)
download_lora "noobai-style-anima-lora-final.safetensors" \
    "https://huggingface.co/mikeyoubeach/noobai-style-anima-lora/resolve/main/noobai-style-anima-lora-final.safetensors" \
    "Modern vibrant Danbooru illustration & pure flat 2D anime cel-shading"

# 8. Hand-Drawn Sketch & Thin Lineart (Yamimatsu7)
download_lora "yamimatsu7_A3P_v1.safetensors" \
    "https://huggingface.co/GAi92/anima-preview-3-loras/resolve/main/styles/yamimatsu7_A3P_v1/yamimatsu7_A3P_v1.safetensors" \
    "Authentic hand-drawn pencil/ink sketch and thin lineart"

# 9. Classic Watercolor & Hand-drawn Lines (Ken Sugimori Style)
download_lora "sugimori_ken_A3P_v1.safetensors" \
    "https://huggingface.co/GAi92/anima-preview-3-loras/resolve/main/styles/sugimori_ken_A3P_v1/sugimori_ken_A3P_v1.safetensors" \
    "Classic 90s hand-drawn watercolor illustration aesthetic"

# ─── Aliases & Intuitive Shorthand Symlinks ────────────────────────────────────
cd "$TARGET_DIR"

create_link() {
    local target="$1"
    local link="$2"
    if [ -f "$target" ]; then
        ln -sf "$target" "$link" 2>/dev/null || true
    fi
}

# Turbo & Speed
create_link "Anima_Turbo_v1.1.safetensors" "anima-turbo-lora-v0.2.safetensors"
create_link "Anima_Turbo_v1.1.safetensors" "anima_turbo.safetensors"
create_link "Anima_Turbo_v1.1.safetensors" "turbo.safetensors"
create_link "anima_turbo_4step_v3.safetensors" "turbo_4step.safetensors"
create_link "anima_turbo_4step_v3.safetensors" "anima_turbo_4step.safetensors"

# Quality, Anatomy & Details
create_link "anima-highres-aesthetic-boost.safetensors" "aesthetic_boost.safetensors"
create_link "anima-highres-aesthetic-boost.safetensors" "highres_boost.safetensors"

create_link "anima-rl-v0.1.safetensors" "anatomy_fix.safetensors"
create_link "anima-rl-v0.1.safetensors" "anima_rl.safetensors"
create_link "anima-rl-v0.1.safetensors" "prompt_align.safetensors"

create_link "anima_context_detailer_base10.safetensors" "cloth_and_hair_detailer.safetensors"
create_link "anima_context_detailer_base10.safetensors" "detail_tweaker.safetensors"
create_link "anima_context_detailer_base10.safetensors" "fabric_detailer.safetensors"

create_link "rendering_detailer_base10-000400.safetensors" "rendering_detailer.safetensors"
create_link "rendering_detailer_base10-000400.safetensors" "texture_detailer.safetensors"

# 2D Anime & Cel Shading Style (Key to Pure 2D Flat Art)
create_link "noobai-style-anima-lora-final.safetensors" "noobai_style.safetensors"
create_link "noobai-style-anima-lora-final.safetensors" "noobai.safetensors"
create_link "noobai-style-anima-lora-final.safetensors" "pure_2d.safetensors"
create_link "noobai-style-anima-lora-final.safetensors" "flat_anime.safetensors"
create_link "noobai-style-anima-lora-final.safetensors" "cel_shading.safetensors"

# Sketch & Hand-Drawn Styles
create_link "yamimatsu7_A3P_v1.safetensors" "sketch_style.safetensors"
create_link "yamimatsu7_A3P_v1.safetensors" "hand_drawn_sketch.safetensors"
create_link "yamimatsu7_A3P_v1.safetensors" "pencil_sketch.safetensors"

create_link "sugimori_ken_A3P_v1.safetensors" "watercolor_artist.safetensors"
create_link "sugimori_ken_A3P_v1.safetensors" "sugimori_style.safetensors"
create_link "sugimori_ken_A3P_v1.safetensors" "classic_watercolor.safetensors"

echo "✨ Curated high-popularity LoRAs and aliases successfully initialized in $TARGET_DIR!"

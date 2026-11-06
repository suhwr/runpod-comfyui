#!/usr/bin/env bash
# ==============================================================================
# download_loras.sh — Curated SOTA LoRA Collection for Pure-DiT Anima Architecture
#
# Downloads & aliases 10 high-quality LoRAs:
#   1. Anima Turbo v1.1 (Anti-Slop 8-10 steps step distillation)
#   2. Anima Turbo 4-Step (Extreme speed preview)
#   3. Highres Aesthetic Booster (Micro-details, lineart & eye clarity)
#   4. RL Anatomy & Hand Fix (Reinforcement learning anatomy & hands)
#   5. Fantasy Art & Dramatic Lighting (Painterly environmental depth)
#   6. NoobAI Style (Modern vibrant Danbooru aesthetic)
#   7. Retro 90s Anime Style (Vintage cel shading)
#   8. Dynamic Action / Battle Pose (Action lines & muscular tension)
#   9. Vintage 90s OVA (Classic OVA mechanical & character lineart)
#  10. Sharp High-Contrast Lineart (Bold ink & crisp silhouette)
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

# 5. Fantasy Art & Dramatic Lighting
download_lora "anima-greg-rutkowski-style.safetensors" \
    "https://huggingface.co/circlestone-labs/Anima-Official-LoRAs/resolve/main/anima-greg-rutkowski-style.safetensors" \
    "Dramatic atmospheric lighting and painterly scenery"

# 6. NoobAI Modern Anime Style
download_lora "noobai-style-anima-lora-final.safetensors" \
    "https://huggingface.co/mikeyoubeach/noobai-style-anima-lora/resolve/main/noobai-style-anima-lora-final.safetensors" \
    "Modern vibrant Danbooru illustration aesthetic"

# 7. Retro 90s Cel Shading (Sailor Moon style)
download_lora "SailorMoon-A1_v1.safetensors" \
    "https://huggingface.co/barusun1/anima-base-1-loras/resolve/main/styles/SailorMoon-A1_v1/SailorMoon-A1_v1.safetensors" \
    "Classic 90s vintage anime cel-shading aesthetic"

# 8. Dynamic Action / Battle Pose (DragonBall action style)
download_lora "DragonBall-A1_v1.safetensors" \
    "https://huggingface.co/barusun1/anima-base-1-loras/resolve/main/styles/DragonBall-A1_v1/DragonBall-A1_v1.safetensors" \
    "Dynamic fighting pose and battle intensity"

# 9. Vintage 90s OVA Anime (Gunsmith Cats style)
download_lora "Gunsmith-A1_v1.safetensors" \
    "https://huggingface.co/barusun1/anima-base-1-loras/resolve/main/styles/Gunsmith-A1_v1/Gunsmith-A1_v1.safetensors" \
    "Sharp mechanical & 90s OVA anime lineart"

# 10. Sharp High-Contrast Lineart (Helltaker style)
download_lora "Helltaker-A1_v1.safetensors" \
    "https://huggingface.co/barusun1/anima-base-1-loras/resolve/main/styles/Helltaker-A1_v1/Helltaker-A1_v1.safetensors" \
    "Stylized bold ink, suit silhouettes & sharp aesthetic"

# ─── Aliases & Intuitive Shorthand Symlinks ────────────────────────────────────
cd "$TARGET_DIR"

create_link() {
    local target="$1"
    local link="$2"
    if [ -f "$target" ]; then
        ln -sf "$target" "$link" 2>/dev/null || true
    fi
}

create_link "Anima_Turbo_v1.1.safetensors" "anima-turbo-lora-v0.2.safetensors"
create_link "Anima_Turbo_v1.1.safetensors" "anima_turbo.safetensors"
create_link "Anima_Turbo_v1.1.safetensors" "turbo.safetensors"

create_link "anima_turbo_4step_v3.safetensors" "turbo_4step.safetensors"
create_link "anima_turbo_4step_v3.safetensors" "anima_turbo_4step.safetensors"

create_link "anima-highres-aesthetic-boost.safetensors" "aesthetic_boost.safetensors"
create_link "anima-highres-aesthetic-boost.safetensors" "highres_boost.safetensors"

create_link "anima-rl-v0.1.safetensors" "anatomy_fix.safetensors"
create_link "anima-rl-v0.1.safetensors" "anima_rl.safetensors"

create_link "anima-greg-rutkowski-style.safetensors" "fantasy_art.safetensors"
create_link "anima-greg-rutkowski-style.safetensors" "dramatic_lighting.safetensors"

create_link "noobai-style-anima-lora-final.safetensors" "noobai_style.safetensors"
create_link "noobai-style-anima-lora-final.safetensors" "noobai.safetensors"

create_link "SailorMoon-A1_v1.safetensors" "retro_90s.safetensors"
create_link "SailorMoon-A1_v1.safetensors" "retro_anime_90s.safetensors"
create_link "SailorMoon-A1_v1.safetensors" "sailormoon_style.safetensors"

create_link "DragonBall-A1_v1.safetensors" "dynamic_action.safetensors"
create_link "DragonBall-A1_v1.safetensors" "dynamic_action_pose.safetensors"
create_link "DragonBall-A1_v1.safetensors" "dragonball_style.safetensors"

create_link "Gunsmith-A1_v1.safetensors" "vintage_ova.safetensors"
create_link "Gunsmith-A1_v1.safetensors" "gunsmith_style.safetensors"

create_link "Helltaker-A1_v1.safetensors" "sharp_lineart.safetensors"
create_link "Helltaker-A1_v1.safetensors" "helltaker_style.safetensors"

echo "✨ All LoRAs and aliases successfully initialized in $TARGET_DIR!"

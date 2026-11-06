# ComfyUI Anime Serverless Worker

Production-grade, ultra-fast serverless worker powering SOTA anime generation with **ComfyUI**, **Pure-DiT Anima Architecture** (CircleStone Labs & Comfy Org), **Nova Anime AM v6.0** (2.9B Flagship Danbooru Master), and **SilvermoonMix-Anima-Evolved v2.3**.

Features **Pre-baked 14 SOTA LoRAs**, **Multi-LoRA Chaining Presets**, **Qwen 2.5 LLM Prompt Adherence**, and **Zero-AI-Slop Tuning**.

---

## ⚡ Key Highlights

1. **State-of-the-Art Pure DiT Architecture (~2.9B Parameters):**
   Powered by Flow-Matching Diffusion Transformers paired with the **Qwen 2.5 3B** text encoder and Qwen image VAE for superior prompt comprehension and visual aesthetic.
2. **Flagship 2D Anime Quality (Nova Anime AM v6.0):**
   Trained on millions of modern Danbooru tags up to 2025/2026 for immaculate character fidelity (Genshin Impact, Honkai: Star Rail, Zenless Zone Zero, Blue Archive, VTubers, seasonal anime).
3. **Multi-LoRA Presets (0ms Setup Latency):**
   Ready-to-use harmonized multi-LoRA stacks for Digital Artist illustration, hand-drawn pencil/ink sketches, extreme character fidelity, vintage 90s anime, and classic watercolors.
4. **Anti-AI-Slop Core Tuning:**
   Locked low CFG ($1.2 - 1.4$) with step distillation and clean cel-shading boosters to banish oily/greasy skin, glossy plastic textures, and lifeless doll faces.
5. **Multi-tier Output Fallback Chain:**
   Artwork uploads through an automatic fallback chain:
   $$\text{Backblaze B2 (Primary)} \longrightarrow \text{Uguu} \longrightarrow \text{Catbox} \longrightarrow \text{Uploadcare} \longrightarrow \text{Direct Base64}$$

---

## 🎨 1. Multi-LoRA Tuning Presets (`"preset"`)

Instead of configuring multiple LoRA weights manually, you can pass `"preset"` to automatically activate a tailored multi-LoRA stack with tuned CFG, steps, and dedicated 2D quality boosters:

| Preset Name | LoRA Stack Combinations | CFG / Steps | Visual Characteristics & Output Style |
| :--- | :--- | :---: | :--- |
| **`"pure_2d"`**<br>*(or `"flat_anime"` / `"cel_shading"`)* | `Anima Turbo` (0.90)<br>+ `Sharp Lineart` (0.50) | `1.15`<br>10 steps | **Pure 2D Anime Screencap:** 100% flat cel-shading, zero 3D spherical gradients, bold crisp lineart, completely free of AI-slop textures. |
| **`"master_illustrator"`**<br>*(or `"digital_art"`)* | `Anima Turbo` (0.90)<br>+ `Aesthetic Boost` (0.45) | `1.25`<br>10 steps | **The SOTA Digital Artist Recipe:** Clean 2D Japanese digital artist illustration (Pixiv/Twitter). Harmonious flat colors, clear expressive eyes, clean lines. |
| **`"hand_drawn_sketch"`**<br>*(or `"sketch"`)* | `Anima Turbo` (0.85)<br>+ `Sketch Style (Yamimatsu7)` (0.85) | `1.20`<br>10 steps | **Authentic Hand-Drawn Sketch:** Draft lines, delicate pencil hatching, thin ink lineart, and artist sketchbook drawing board aesthetic. |
| **`"character_focus"`**<br>*(or `"strong_character"`)* | `Anima Turbo` (0.90)<br>+ `Anatomy Fix` (0.65; RL tuned) | `1.25`<br>10 steps | **Maximum Character Recognition (98%+):** Boosted CLIP text weights ensure complex character outfits, hair accessories, and canonical features adhere strictly to the prompt without concept bleed. |
| **`"watercolor_classic"`**<br>*(or `"sugimori"`)* | `Anima Turbo` (0.85)<br>+ `Watercolor Artist (Sugimori)` (0.85) | `1.20`<br>10 steps | **Classic 90s Hand-Drawn Watercolor:** Soft watercolor washes, paper grain texture, and delicate outline art (legendary Ken Sugimori aesthetic). |
| **`"modern_anime"`**<br>*(or `"pixiv"` / `"noobai"`)* | `Anima Turbo` (0.90)<br>+ `NoobAI Modern Style` (0.75) | `1.25`<br>10 steps | **Modern Danbooru Vibrant Art:** Vibrant pop colors, high contrast, clean modern cel shading illustration. |
| **`"retro_90s"`**<br>*(or `"vintage"`)* | `Anima Turbo` (0.85)<br>+ `Retro 90s Cel (Sailor Moon)` (0.80) | `1.20`<br>10 steps | **Classic 90s Cel Animation:** Nostalgic hand-painted anime cel shading, film grain, and 90s TV anime palette. |
| **`"dynamic_action"`**<br>*(or `"battle_pose"`)* | `Anima Turbo` (0.90)<br>+ `Dynamic Action (DragonBall)` (0.75) | `1.25`<br>10 steps | **Dynamic Combat & Action:** Martial arts fighting stances, dynamic motion lines, and intense perspective lineart. |
| **`"painterly"`**<br>*(or `"fantasy"`)* | `Anima Turbo` (0.90)<br>+ `Fantasy Art (Rutkowski)` (0.60) | `1.30`<br>12 steps | **Painterly Fantasy Concept Art:** Expressive digital brushwork, traditional art media texture, and rich artistic composition. |

---

## 📦 2. Pre-baked 14 SOTA LoRAs Collection (0ms Cold Start)

All 14 LoRAs are downloaded during `docker build` into `/app/ComfyUI/models/loras/`. They can be used directly via their filename or intuitive shorthand aliases:

| Category | LoRA File Name | Shorthand Aliases | Rec. Strength | Description & Target Role |
| :--- | :--- | :--- | :---: | :--- |
| **Speed Foundation** | `Anima_Turbo_v1.1.safetensors` | `turbo`, `anima_turbo` | `0.95` | Step distillation base. Finishes generation in 8–10 steps and eliminates the over-sampled greasy plastic skin. |
| **Instant Speed** | `anima_turbo_4step_v3.safetensors` | `turbo_4step` | `1.00` | Extreme 4-step generation for sub-1s rapid draft previews. |
| **Fabric & Hair Detail**| `anima_context_detailer_base10.safetensors` | `cloth_and_hair_detailer`, `detail_tweaker` | `0.60 – 0.70` | Micro-detail booster for fine hair strands, fabric drapery, and realistic clothing folds. |
| **Render Crispness** | `rendering_detailer_base10-000400.safetensors` | `rendering_detailer`, `texture_detailer` | `0.50 – 0.65` | Sharpens brush strokes, edge crispness, and surface textures. |
| **Aesthetic Polish** | `anima-highres-aesthetic-boost.safetensors` | `aesthetic_boost`, `highres_boost` | `0.60 – 0.75` | Official CircleStone booster for clear pupil catchlights, fine outlines, and eye clarity. |
| **Anatomy & Alignment**| `anima-rl-v0.1.safetensors` | `anatomy_fix`, `prompt_align` | `0.70 – 0.85` | RL fine-tuned for anatomically accurate fingers, hands, and complex prompt compliance. |
| **Hand-Drawn Sketch** | `yamimatsu7_A3P_v1.safetensors` | `sketch_style`, `hand_drawn_sketch` | `0.75 – 0.85` | Authentic hand-drawn draft lines, thin pencil hatching, and artist sketchbook aesthetic. |
| **Watercolor Art** | `sugimori_ken_A3P_v1.safetensors` | `watercolor_artist`, `sugimori_style` | `0.70 – 0.80` | Classic 90s hand-drawn watercolor illustration with gentle wash gradients. |
| **Modern Anime** | `noobai-style-anima-lora-final.safetensors` | `noobai_style`, `noobai` | `0.65 – 0.75` | Modern vibrant Danbooru anime aesthetic with sharp digital lines. |
| **Fantasy Lighting** | `anima-greg-rutkowski-style.safetensors` | `fantasy_art`, `dramatic_lighting` | `0.55 – 0.70` | Cinematic lighting, volumetric god rays, and painterly fantasy environments. |
| **Retro 90s Cel** | `SailorMoon-A1_v1.safetensors` | `retro_90s`, `retro_anime_90s` | `0.70 – 0.80` | Vintage 90s TV anime cel shading with nostalgic color grading. |
| **Dynamic Battle** | `DragonBall-A1_v1.safetensors` | `dynamic_action`, `dynamic_action_pose` | `0.75 – 0.85` | Dynamic action lines, battle tension, and muscular definition. |
| **90s OVA Anime** | `Gunsmith-A1_v1.safetensors` | `vintage_ova`, `gunsmith_style` | `0.70 – 0.80` | Vintage 90s OVA mechanical props, detailed jackets, and sharp hand-drawn ink. |
| **Bold Stylized Ink** | `Helltaker-A1_v1.safetensors` | `sharp_lineart`, `helltaker_style` | `0.70 – 0.80` | High-contrast black ink lineart, crisp silhouettes, and stylized suits. |

---

## 📥 API Input Specification

| Parameter | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `prompt` | `string` | *(Required)* | Positive anime prompt tags. |
| `preset` | `string` | `""` | Quick multi-LoRA preset (`master_illustrator`, `hand_drawn_sketch`, `character_focus`, `watercolor_classic`, `modern_anime`, `painterly`, `retro_90s`). |
| `model` | `string` | `"nova"` | Base model: `"nova"` (Default - Nova Anime AM v6.0 with anti-slop cel-shading), `"anima_base"` (CircleStone Anima Base v1.0 DiT with auto-download if missing), `"silvermoon"` (SilvermoonMix Anima Evolved), `"orange"` (Nova Orange AM 2.5D). |
| `turbo` | `boolean` | `false` | Enable Anima Turbo v1.1 standalone (10 steps, CFG 1.4, euler). |
| `turbo_strength` | `float` | `1.0` | Turbo strength override (0.0 to 1.0). |
| `loras` | `array` | `[]` | Dynamic multiple LoRA chaining (`[{"name": "...", "strength": 0.8}]`). Can be stacked on top of any `preset`. |
| `negative_prompt` | `string` | `""` | Optional negative prompt overrides. |
| `width` | `integer` | `768` | Width in pixels (`768`, `832`, `1024`). |
| `height` | `integer` | `1024` | Height in pixels (`1024`, `1216`). |
| `steps` | `integer` | *(Auto)* | Steps (`10` for Turbo/presets, `4` for 4step, `16` for normal). |
| `cfg` | `float` | *(Auto)* | Guidance scale (`1.25 – 1.4` for presets, `2.1` for normal). |
| `sampler` | `string` | *(Auto)* | Sampler name (`euler` for Turbo/presets, `er_sde` for normal). |
| `scheduler` | `string` | `"simple"` | Scheduler name (`simple`, `normal`, `karras`). |
| `seed` | `integer` | `-1` | Random seed (`-1` for randomized generation). |

---

## 🚀 Example Requests

### Example 1: Master Illustrator (The Golden Anti-Slop Recipe)
```json
{
  "input": {
    "prompt": "1girl, silver hair, glowing blue eyes, white hoodie, headphone, standing in cyberpunk tokyo street, neon reflection",
    "preset": "master_illustrator",
    "width": 768,
    "height": 1024
  }
}
```

### Example 2: Strong Character Recognition
```json
{
  "input": {
    "prompt": "furina (genshin impact), ascot, top hat, blue coat, heterochromia, ahoge, standing in fountain plaza, water ripples, delicate reflection",
    "preset": "character_focus",
    "width": 768,
    "height": 1024
  }
}
```

### Example 3: Authentic Hand-Drawn Sketch
```json
{
  "input": {
    "prompt": "1girl, silver hair, school uniform, wind blowing hair, looking at viewer",
    "preset": "hand_drawn_sketch",
    "width": 768,
    "height": 1024
  }
}
```

### Example 4: Classic 90s Watercolor (Ken Sugimori Style)
```json
{
  "input": {
    "prompt": "1girl, cute trainer outfit, red cap, backpack, holding pokeball, lush green meadow background",
    "preset": "watercolor_classic",
    "width": 768,
    "height": 1024
  }
}
```

---

## 📤 API Output Specification

```json
{
  "status": "COMPLETED",
  "execution_time_seconds": 2.15,
  "model_used": "Nova Anime AM v6.0 (2.9B)",
  "seed": 420691337,
  "loras_applied": [
    "Anima_Turbo_v1.1.safetensors",
    "anima_context_detailer_base10.safetensors",
    "anima-highres-aesthetic-boost.safetensors",
    "anima-rl-v0.1.safetensors"
  ],
  "images": [
    {
      "url": "https://f005.backblazeb2.com/file/my-bucket/tmp/comfyui/1730799999_a1b2c3d4_ComfyUI_00001_.png",
      "file_name": "ComfyUI_00001_.png",
      "size_bytes": 1845120,
      "storage": "backblaze_b2"
    }
  ]
}
```

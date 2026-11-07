# ComfyUI Anime Serverless Worker

Production-grade, ultra-fast serverless worker powering SOTA anime generation with **ComfyUI**, **Pure-DiT Anima Architecture** (CircleStone Labs & Comfy Org), **Nova Anime AM v6.0** (2.9B Flagship Danbooru Master & Default Model), and **Anima 3.8B v1.1** (52 DiT Blocks with Dual Qwen 3.5 4B Text Encoders & Semantic Connector v2).

Features **Curated SOTA LoRAs based on Civitai/HF download metrics**, **Multi-LoRA Chaining Presets**, **Qwen LLM Prompt Adherence**, **Genuine Flat 2D Cel-Shading Anti-2.5D Tuning**, and **Zero-AI-Slop Tuning**.

---

## ⚡ Key Highlights

1. **State-of-the-Art Pure DiT Architecture (Nova 2.9B Default & Anima 3.8B Flagship):**
   - **Nova Anime AM v6.0 (2.9B) [DEFAULT]:** Flow-Matching Diffusion Transformer with high Danbooru tag compliance up to 2025/2026.
   - **Anima 3.8B v1.1 (3.8B):** 52 DiT blocks paired with Qwen 3.5 4B text encoder and progressive-cross Semantic Connector v2 (`lylogummy/Anima-3.8B` via `GumGum10/comfyui-anima-3-8B`).
2. **Genuine Flat 2D Cel Shading (Fixed 2.5D/Plastic Look):**
   - Eliminated `"flat colors"` penalty from negative prompt.
   - `pure_2d` preset couples `noobai-style-anima-lora-final` (0.85) + `Anima Turbo v1.1` (0.85) + `anatomy_fix` (0.45) with CFG 1.65 and dedicated anti-2.5D/3D negative tokens.
3. **Curated High-Popularity SOTA LoRA Collection:**
   Purged obscure, broken preview-1 LoRAs (Greg Rutkowski, Helltaker, SailorMoon, DragonBall, Gunsmith). Retained only verified top-downloaded LoRAs (Anima Turbo, Aesthetic Boost, RL Anatomy, Context & Rendering Detailers, NoobAI 2D Cel-Shading, Yamimatsu7 Sketch, Sugimori Ken Watercolor).
4. **Multi-LoRA Presets (0ms Setup Latency):**
   Ready-to-use harmonized multi-LoRA stacks for Pure 2D Flat Anime, Digital Artist illustration, hand-drawn pencil/ink sketches, extreme character fidelity, and vintage watercolors.
5. **Multi-tier Output Fallback Chain:**
   Artwork uploads through an automatic fallback chain:
   $$\text{Direct Base64 (sub-7MB, 0ms latency)} \longrightarrow \text{Backblaze B2} \longrightarrow \text{Uguu} \longrightarrow \text{Catbox} \longrightarrow \text{Uploadcare}$$

---

## 🎨 1. Multi-LoRA Tuning Presets (`"preset"`)

Instead of configuring multiple LoRA weights manually, you can pass `"preset"` to automatically activate a tailored multi-LoRA stack with tuned CFG, steps, and dedicated 2D quality boosters:

| Preset Name | LoRA Stack Combinations | CFG / Steps / Sampler | Visual Characteristics & Output Style |
| :--- | :--- | :---: | :--- |
| **`"pure_2d"`**<br>*(or `"flat_anime"` / `"cel_shading"`)* | `Anima Turbo` (0.85)<br>+ `NoobAI 2D Flat Style` (0.85)<br>+ `Anatomy Fix` (0.45) | `1.65`<br>10 steps<br>`er_sde` + `simple` | **Pure 2D Anime Screencap:** Genuine flat cel-shading, zero 2.5D spherical shading, zero plastic skin, bold ink lineart, natural anatomy, and scenic background. |
| **`"master_illustrator"`**<br>*(or `"digital_art"`)* | `Anima Turbo` (0.90)<br>+ `Aesthetic Boost` (0.45)<br>+ `Anatomy Fix` (0.55)<br>+ `Cloth & Hair Detailer` (0.40) | `1.25`<br>10 steps<br>`er_sde` + `simple` | **The SOTA Digital Artist Recipe:** Clean 2D Japanese digital artist illustration (Pixiv/Twitter). Harmonious flat colors, natural body curves, clear expressive eyes, rich scenic environment. |
| **`"hand_drawn_sketch"`**<br>*(or `"sketch"`)* | `Anima Turbo` (0.85)<br>+ `Sketch Style (Yamimatsu7)` (0.85)<br>+ `Anatomy Fix` (0.45) | `1.20`<br>10 steps<br>`er_sde` + `simple` | **Authentic Hand-Drawn Sketch:** Draft lines, delicate pencil hatching, thin ink lineart, and artist sketchbook drawing board aesthetic. |
| **`"character_focus"`**<br>*(or `"strong_character"`)* | `Anima Turbo` (0.90)<br>+ `Anatomy Fix` (0.70; RL tuned)<br>+ `Cloth & Hair Detailer` (0.40) | `1.25`<br>10 steps<br>`er_sde` + `simple` | **Maximum Character Recognition (98%+):** Boosted CLIP text weights ensure complex character outfits, hair accessories, and canonical features adhere strictly to prompt without blanking the background. |
| **`"watercolor_classic"`**<br>*(or `"sugimori"`)* | `Anima Turbo` (0.85)<br>+ `Watercolor Artist (Sugimori)` (0.85)<br>+ `Anatomy Fix` (0.45) | `1.20`<br>10 steps<br>`er_sde` + `simple` | **Classic 90s Hand-Drawn Watercolor:** Soft watercolor washes, paper grain texture, and delicate outline art (legendary Ken Sugimori aesthetic). |
| **`"modern_anime"`**<br>*(or `"pixiv"` / `"noobai"`)* | `Anima Turbo` (0.90)<br>+ `NoobAI Modern Style` (0.75)<br>+ `Anatomy Fix` (0.50) | `1.25`<br>10 steps<br>`er_sde` + `simple` | **Modern Danbooru Vibrant Art:** Vibrant pop colors, high contrast, clean modern cel shading illustration, beautiful background scenery. |
| **`"retro_90s"`**<br>*(or `"vintage"`)* | `Anima Turbo` (0.85)<br>+ `NoobAI Cel Style` (0.65)<br>+ `Anatomy Fix` (0.45) | `1.25`<br>10 steps<br>`er_sde` + `simple` | **Classic 90s Cel Animation:** Nostalgic hand-painted anime cel shading, film grain, vintage anime scenery, and 90s TV anime palette. |
| **`"dynamic_action"`**<br>*(or `"battle_pose"`)* | `Anima Turbo` (0.90)<br>+ `Anatomy Fix` (0.65)<br>+ `Rendering Detailer` (0.40) | `1.25`<br>10 steps<br>`er_sde` + `simple` | **Dynamic Combat & Action:** Martial arts fighting stances, dynamic motion lines, powerful natural muscle tension, and cinematic battlefield background. |
| **`"painterly"`**<br>*(or `"fantasy"`)* | `Anima Turbo` (0.90)<br>+ `Aesthetic Boost` (0.55)<br>+ `Rendering Detailer` (0.45) | `1.25`<br>12 steps<br>`er_sde` + `simple` | **Painterly Fantasy Concept Art:** Expressive digital brushwork, traditional art media texture, and rich atmospheric scenery. |

---

## 📦 2. Curated SOTA LoRAs Collection (0ms Cold Start)

| Category | LoRA File Name | Shorthand Aliases | Rec. Strength | Description & Target Role |
| :--- | :--- | :--- | :---: | :--- |
| **Speed Foundation** | `Anima_Turbo_v1.1.safetensors` | `turbo`, `anima_turbo` | `0.90` | Top Civitai LoRA (80k+ DL). Finishes generation in 8–10 steps and eliminates over-sampled plastic slop. |
| **Instant Speed** | `anima_turbo_4step_v3.safetensors` | `turbo_4step` | `1.00` | Extreme 4-step generation for sub-1s rapid draft previews. |
| **Aesthetic Polish** | `anima-highres-aesthetic-boost.safetensors` | `aesthetic_boost`, `highres_boost` | `0.50` | Official CircleStone booster (47k+ DL) for pupil catchlights, fine outlines, and eye clarity. |
| **Anatomy & Alignment**| `anima-rl-v0.1.safetensors` | `anatomy_fix`, `prompt_align` | `0.50` | RL tuned (14k+ DL) for anatomically accurate fingers, hands, and complex prompt compliance. |
| **Fabric & Hair Detail**| `anima_context_detailer_base10.safetensors` | `cloth_and_hair_detailer`, `detail_tweaker` | `0.40` | Micro-detail booster (38k+ DL) for fine hair strands, fabric drapery, and clothing folds. |
| **Render Crispness** | `rendering_detailer_base10-000400.safetensors` | `rendering_detailer`, `texture_detailer` | `0.45` | Sharpens brush strokes, edge crispness, and surface textures. |
| **Pure 2D Cel-Shading**| `noobai-style-anima-lora-final.safetensors` | `noobai_style`, `pure_2d`, `cel_shading` | `0.85` | Key to pure flat 2D anime illustration. Danbooru cel-shading without oily or 2.5D gradients. |
| **Hand-Drawn Sketch** | `yamimatsu7_A3P_v1.safetensors` | `sketch_style`, `hand_drawn_sketch` | `0.85` | Authentic hand-drawn draft lines, thin pencil hatching, and artist sketchbook aesthetic. |
| **Watercolor Art** | `sugimori_ken_A3P_v1.safetensors` | `watercolor_artist`, `sugimori_style` | `0.85` | Classic 90s hand-drawn watercolor illustration with gentle wash gradients. |

---

## 📥 API Input Specification

| Parameter | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `prompt` | `string` | *(Required)* | Positive anime prompt tags. |
| `model` | `string` | `"nova"` | Base model: `"nova"` (DEFAULT - Nova Anime AM v6.0), `"3.8b"` / `"anima-3.8b"` (Anima 3.8B v1.1 DiT 52 blocks), `"silvermoon"` (SilvermoonMix), `"anima_base"` (CircleStone Anima Base v1.0). |
| `image` | `string` | `""` | Optional reference image (Public URL, base64 data string, or path) for Img2Img redraw / style transfer. |
| `denoise` | `float` | `0.65` (img2img) / `1.0` (txt2img) | Denoising strength for Img2Img (`0.4` minor tweak, `0.65` anime redraw, `0.85` creative remake). |
| `preset` | `string` | `""` | Quick multi-LoRA preset (`pure_2d`, `master_illustrator`, `hand_drawn_sketch`, `character_focus`, `watercolor_classic`, `modern_anime`, `painterly`, `retro_90s`). |
| `turbo` | `boolean` | `false` | Enable Anima Turbo v1.1 standalone (10 steps, CFG 1.25, er_sde). |
| `loras` | `array` | `[]` | Dynamic multiple LoRA chaining (`[{"name": "...", "strength": 0.8}]`). Can be stacked on top of any `preset`. |
| `negative_prompt` | `string` | `""` | Optional negative prompt overrides. |
| `width` | `integer` | `768` | Width in pixels (`768`, `832`, `1024`). |
| `height` | `integer` | `1024` | Height in pixels (`1024`, `1216`). |
| `steps` | `integer` | *(Auto)* | Steps (`15` default across all models, `10` for Turbo/presets, `4` for 4step). |
| `cfg` | `float` | *(Auto)* | Guidance scale (`2.1` default, `1.65` for pure_2d, `1.25` for presets). |
| `sampler` | `string` | *(Auto)* | Native sampler (`er_sde` default for Anima ecosystem, `euler` for 4-step). |
| `scheduler` | `string` | *(Auto)* | Scheduler (`simple` default for Anima ecosystem). |
| `seed` | `integer` | `-1` | Random seed (`-1` for randomized generation). |

---

## 🚀 Example Requests

### Example 1: Pure 2D Anime (Cel Shading without 2.5D Leaks)
```json
{
  "input": {
    "prompt": "1girl, silver hair, cat ears, school uniform, smiling, vibrant anime colors, clean lineart, anime screencap",
    "preset": "pure_2d",
    "width": 768,
    "height": 1024
  }
}
```

### Example 2: Flagship Anima 3.8B v1.1
```json
{
  "input": {
    "model": "3.8b",
    "prompt": "1girl, futuristic explorer, glowing tech staff, mountain temple, cherry blossoms in snow, cinematic sunset",
    "width": 1024,
    "height": 1024,
    "steps": 15,
    "cfg": 2.1
  }
}
```

### Example 3: Master Illustrator (The Golden Anti-Slop Recipe on Nova Default)
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
    "noobai-style-anima-lora-final.safetensors",
    "anatomy_fix"
  ],
  "images": [
    {
      "url": "https://f005.backblazeb2.com/file/my-bucket/tmp/comfyui/1730799999_a1b2c3d4_ComfyUI_00001_.png",
      "base64": "",
      "file_name": "ComfyUI_00001_.png",
      "size_bytes": 1845120,
      "storage": "backblaze_b2"
    }
  ]
}
```

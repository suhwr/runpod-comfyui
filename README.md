# ComfyUI Anime Serverless Worker

Production-grade, ultra-fast serverless worker powering SOTA anime generation with **ComfyUI**, **Pure-DiT Anima Architecture** (CircleStone Labs & Comfy Org), **Nova Anime AM v6.0** (2.9B Flagship), and **SilvermoonMix-Anima-Evolved v2.3**.

---

## ⚡ Key Highlights

1. **State-of-the-Art Pure DiT Architecture (~2.9B Parameters):**
   Powered by Flow-Matching Diffusion Transformers paired with the **Qwen 2.5 3B** text encoder and Qwen image VAE for superior prompt comprehension and visual aesthetic.
2. **Flagship 2D Anime Quality (Nova Anime AM v6.0):**
   Trained on millions of modern Danbooru tags for immaculate character fidelity (Genshin Impact, Honkai: Star Rail, Blue Archive, VTubers, seasonal anime).
3. **Aesthetic Alternative (SilvermoonMix Anima Evolved v2.3):**
   Fine-tuned for painterly digital illustrations, ambient lighting, and refined soft shading.
4. **Sub-3s Inference Speed:**
   Flow Matching sampler requires only 12–16 steps to render sharp 768×1024 / 832×1216 images in ~2.5 seconds on serverless GPUs.
5. **Headless ComfyUI Core (`127.0.0.1:8188`):**
   Runs a lightweight daemon stripped of GUI overhead with pre-warmed CUDA kernels.
6. **Multi-tier Output Fallback Chain:**
   Generated artworks are uploaded through an automatic fallback chain:
   $$\text{Backblaze B2 (Primary)} \longrightarrow \text{Uguu} \longrightarrow \text{Catbox} \longrightarrow \text{Uploadcare} \longrightarrow \text{Direct Base64}$$

---

## 📥 API Input Specification

| Parameter | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `prompt` | `string` | *(Required)* | Positive anime prompt tags |
| `model` | `string` | `"nova"` | Model selector: `"nova"` (Default 2D Anime), `"silvermoon"` (Painterly), `"orange"` (2.5D) |
| `turbo` | `boolean` | `false` | Enable Anima Turbo v1.1 (~2x faster, 10 steps, CFG 1.4, anti-slop tuning) |
| `turbo_strength` | `float` | `1.0` | Turbo LoRA strength (0.0 to 1.0) |
| `loras` | `array` | `[]` | Dynamic multiple LoRA chaining (`[{"name": "...", "strength": 0.8}]` or `["..."]`) |
| `negative_prompt` | `string` | `""` | Optional negative prompt overrides |
| `width` | `integer` | `768` | Width in pixels (recommended: `768`, `832`, `1024`) |
| `height` | `integer` | `1024` | Height in pixels (recommended: `1024`, `1216`) |
| `steps` | `integer` | `10` (Turbo) / `16` | Sampling steps (Flow Matching: 10–16 optimal) |
| `cfg` | `float` | `1.4` (Turbo) / `2.1` | Guidance scale (optimal for Anima DiT: 1.2–2.3; keep $\le 2.4$ to prevent AI slop) |
| `sampler` | `string` | `"euler"` (Turbo) / `"er_sde"` | Sampler name (`euler`, `er_sde`, `euler_ancestral`, `dpmpp_2m`) |
| `scheduler` | `string` | `"simple"` | Scheduler name (`simple`, `normal`, `karras`, `sgm_uniform`) |
| `seed` | `integer` | `-1` | Random seed (`-1` for randomized generation) |
| `workflow` | `object` | `null` | Optional raw ComfyUI API workflow JSON dict |

### Example Request with Multiple LoRAs:

```json
{
  "input": {
    "prompt": "1girl, silver hair, fighting pose, dynamic action, retro 90s aesthetic",
    "turbo": true,
    "loras": [
      {
        "name": "dynamic_action_pose.safetensors",
        "strength": 0.8
      },
      {
        "name": "retro_anime_90s.safetensors",
        "strength_model": 0.65,
        "strength_clip": 0.5
      }
    ],
    "width": 768,
    "height": 1024
  }
}
```

---

## 🎨 Pre-baked Curated LoRA Collection (0ms Cold-Start)

The worker container comes pre-baked with 10 high-quality SOTA LoRAs for the Pure-DiT Anima ecosystem. They can be invoked by their exact filename or convenient shorthand aliases:

| Category | LoRA File | Shorthand Aliases | Description |
| :--- | :--- | :--- | :--- |
| **Speed & Anti-Slop** | `Anima_Turbo_v1.1.safetensors` | `turbo`, `anima_turbo` | 8–10 steps step distillation, removes AI slop & greasy skin textures. |
| **Instant Speed** | `anima_turbo_4step_v3.safetensors` | `turbo_4step` | Ultra-fast 4-step generation (~1s inference). |
| **Detail & Polish** | `anima-highres-aesthetic-boost.safetensors` | `aesthetic_boost`, `highres_boost` | Enhances micro-details, eye clarity, and clean lineart. |
| **Anatomy** | `anima-rl-v0.1.safetensors` | `anatomy_fix`, `anima_rl` | RL-tuned for accurate hand geometry, fingers, and anatomy. |
| **Lighting** | `anima-greg-rutkowski-style.safetensors` | `fantasy_art`, `dramatic_lighting` | Dramatic fantasy lighting, cinematic depth, and painterly backgrounds. |
| **Modern Anime** | `noobai-style-anima-lora-final.safetensors` | `noobai_style`, `noobai` | Vibrant modern Danbooru anime aesthetic. |
| **Retro 90s** | `SailorMoon-A1_v1.safetensors` | `retro_90s`, `retro_anime_90s` | Classic 90s vintage anime cel shading. |
| **Action & Battle** | `DragonBall-A1_v1.safetensors` | `dynamic_action`, `dynamic_action_pose` | Intense battle pose, dynamic lines, and muscular tension. |
| **90s OVA** | `Gunsmith-A1_v1.safetensors` | `vintage_ova`, `gunsmith_style` | Sharp mechanical details & 90s OVA lineart. |
| **Bold Lineart** | `Helltaker-A1_v1.safetensors` | `sharp_lineart`, `helltaker_style` | High-contrast ink, crisp silhouettes, and sharp suits. |

---

## 📤 API Output Specification

```json
{
  "status": "COMPLETED",
  "execution_time_seconds": 2.45,
  "model_used": "Nova Anime AM v6.0 (2.9B)",
  "seed": 1234567,
  "images": [
    {
      "url": "https://f005.backblazeb2.com/file/my-bucket/tmp/comfyui/image.png",
      "file_name": "ComfyUI_00001_.png",
      "size_bytes": 1642890,
      "storage": "backblaze_b2"
    }
  ]
}
```

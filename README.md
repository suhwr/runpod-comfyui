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
| `model` | `string` | `"nova"` | Model selector: `"nova"` (Default) or `"silvermoon"` |
| `negative_prompt` | `string` | `""` | Optional negative prompt overrides |
| `width` | `integer` | `768` | Width in pixels (recommended: `768`, `832`, `1024`) |
| `height` | `integer` | `1024` | Height in pixels (recommended: `1024`, `1216`) |
| `steps` | `integer` | `16` | Sampling steps (Flow Matching: 16 optimal) |
| `cfg` | `float` | `2.1` | Guidance scale (optimal for Anima DiT: 2.0–2.4) |
| `sampler` | `string` | `"er_sde"` | Sampler name (`er_sde`, `euler`, `dpmpp_2m`) |
| `scheduler` | `string` | `"simple"` | Scheduler name (`simple`, `sgm_uniform`) |
| `seed` | `integer` | `-1` | Random seed (`-1` for randomized generation) |
| `workflow` | `object` | `null` | Optional raw ComfyUI API workflow JSON dict |

### Example Request:

```json
{
  "input": {
    "prompt": "1girl, silver hair, cat ears, school uniform, cherry blossoms",
    "model": "nova",
    "width": 768,
    "height": 1024,
    "seed": 1234567
  }
}
```

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

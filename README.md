# ComfyUI Anime Serverless Worker

Production-grade, ultra-fast serverless worker powering SOTA anime generation with **ComfyUI**, **NoobAI-XL v1.1** (SDXL), and **Hyper-SD 8-Step LoRA**.

---

## ⚡ Key Highlights

1. **Top-Tier Anime Visuals (NoobAI-XL v1.1):**
   State-of-the-art Danbooru tag comprehension, clean lineart, and precise anatomy.
2. **Lightning-Fast Generation (~4s via Hyper-SD 8-Step LoRA):**
   Accelerated 8-step sampling delivering crisp 1024px+ outputs in just ~4 seconds, slashing serverless GPU billing by up to 70%.
3. **Headless ComfyUI Core:**
   Executes directly on a lightweight headless ComfyUI daemon (`127.0.0.1:8188`) without frontend bloat.
4. **Built-in SOTA Anime Workflow:**
   Clients do not need to construct raw JSON graph payloads. Simply supply prompt parameters, and the worker parameterizes an optimized SDXL anime pipeline.
5. **Auto Quality Enhancer:**
   Automatically incorporates Danbooru quality tags (`masterpiece, best quality, very aesthetic`) and comprehensive negative filtering (`bad anatomy, bad hands, lowres`).
6. **Multi-tier Output Fallback:**
   Generated artworks are uploaded through an automatic fallback chain:
   $$\text{Uguu} \longrightarrow \text{Catbox} \longrightarrow \text{Uploadcare (Ucarecdn)} \longrightarrow \text{Base64}$$

---

## 📥 API Input Specification

| Parameter | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `prompt` | `string` | *(Required)* | Positive anime prompt tags |
| `negative_prompt` | `string` | `""` | Optional negative prompt overrides |
| `width` | `integer` | `832` | Width in pixels (recommended: `832`, `1024`, `1216`) |
| `height` | `integer` | `1216` | Height in pixels (recommended: `1216`, `1024`, `832`) |
| `steps` | `integer` | `8` | Sampling steps (capped to 12 max for high throughput) |
| `cfg` | `float` | `5.0` | CFG scale |
| `seed` | `integer` | `-1` | Random seed (`-1` for randomized generation) |
| `model` | `string` | `null` | Optional checkpoint filename override |
| `lora` | `string` | `null` | Optional LoRA filename override |
| `workflow` | `object` | `null` | Optional raw ComfyUI API workflow JSON dict |
| `catbox_key` | `string` | `null` | Optional Catbox userhash |

### Example Request:

```json
{
  "input": {
    "prompt": "1girl, silver hair, cat ears, school uniform, cherry blossoms",
    "negative_prompt": "blurry, low quality",
    "width": 832,
    "height": 1216,
    "seed": 1234567
  }
}
```

---

## 📤 API Output Specification

```json
{
  "status": "COMPLETED",
  "execution_time_seconds": 3.84,
  "seed": 1234567,
  "images": [
    {
      "url": "https://a.uguu.se/xyz.png",
      "file_name": "ComfyUI_Anime_00001_.png",
      "size_bytes": 1642890,
      "storage": "uguu"
    }
  ]
}
```

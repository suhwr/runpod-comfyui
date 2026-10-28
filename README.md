# ComfyUI Anime Serverless Worker

Production-grade, high-throughput serverless worker powering SOTA anime generation with **ComfyUI** and SDXL checkpoints.

---

## ⚡ Key Highlights

1. **Headless ComfyUI Core:**
   Executes directly on a lightweight headless ComfyUI daemon (`127.0.0.1:8188`) without browser/frontend bloat.
2. **Built-in SOTA Anime Workflow:**
   Clients do not need to construct raw JSON graph payloads. Simply supply prompt parameters, and the worker parameterizes an optimized SDXL anime pipeline.
3. **Auto Quality Enhancer:**
   Automatically incorporates Danbooru quality tags (`masterpiece, best quality, very aesthetic`) and comprehensive negative filtering (`bad anatomy, bad hands, lowres`).
4. **Multi-tier Output Fallback:**
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
| `steps` | `integer` | `25` | Sampling steps |
| `cfg` | `float` | `7.0` | CFG scale |
| `seed` | `integer` | `-1` | Random seed (`-1` for randomized generation) |
| `model` | `string` | `null` | Optional checkpoint filename override |
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
    "steps": 25,
    "cfg": 7.0,
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
      "url": "https://h.uguu.se/anime_art.png",
      "file_name": "ComfyUI_Anime_00001_.png",
      "size_bytes": 2145320,
      "storage": "uguu"
    }
  ]
}
```

---

## 🛠️ Environment Variables

- `CHECKPOINT_NAME`: Default anime checkpoint filename (defaults to `animagine-xl-3.1.safetensors`).
- `CHECKPOINT_URL`: Optional direct URL to download checkpoint if missing.
- `MAX_CONCURRENCY`: Worker job queue concurrency (defaults to `1` for collision-free execution).
- `CATBOX_KEY`: Default Catbox userhash (optional).
- `COMFY_DIR`: ComfyUI installation path (defaults to `/app/ComfyUI`).

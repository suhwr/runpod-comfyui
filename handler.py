import base64
import copy
import io
import json
import logging
import os
import pathlib
import random
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import requests
import runpod
import websocket

# ============================================================================ #
# Configuration & Hardware Diagnostics                                         #
# ============================================================================ #

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("comfyui-worker")

COMFY_DIR = os.environ.get("COMFY_DIR", "/app/ComfyUI")
COMFY_HOST = os.environ.get("COMFY_HOST", "127.0.0.1:8188")
CHECKPOINT_NAME = os.environ.get("CHECKPOINT_NAME", "novaAnimeXL_ilV100.safetensors")
LORA_NAME = os.environ.get("LORA_NAME", "Hyper-SDXL-8steps-CFG-lora.safetensors")
DEFAULT_CATBOX_USER_HASH = os.environ.get("CATBOX_KEY", "")
MAX_CONCURRENCY = max(1, int(os.environ.get("MAX_CONCURRENCY", "1")))

WORKFLOW_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "workflow_anime.json")

# Default quality tags for NoobAI-XL / Illustrious anime generation
ANIME_QUALITY_BOOSTER = "masterpiece, best quality, newest, absurdres, highres, safe"
ANIME_NEGATIVE_DEFAULT = (
    "worst quality, old, early, low quality, lowres, sketch, rough sketch, crayon, "
    "child drawing, lineart, monochrome, greyscale, signature, watermark, username, "
    "bad anatomy, bad hands, missing fingers, extra digits, fewer digits, blurry"
)

# ============================================================================ #
# Storage Uploaders with Automatic Fallback Chain                              #
# ============================================================================ #

def _upload_uguu(file_path: pathlib.Path) -> str:
    """Upload to Uguu.se (up to 100MB)."""
    with open(file_path, "rb") as f:
        resp = requests.post(
            "https://uguu.se/upload",
            params={"output": "json"},
            files={"files[]": (file_path.name, f)},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        files = data.get("files")
        if files and len(files) > 0 and files[0].get("url"):
            return files[0]["url"]
        raise ValueError(f"Uguu response invalid: {data}")


def _upload_catbox(file_path: pathlib.Path, user_hash: Optional[str] = None) -> str:
    """Upload to Catbox.moe (up to 200MB)."""
    data = {"reqtype": "fileupload"}
    hash_to_use = user_hash or DEFAULT_CATBOX_USER_HASH
    if hash_to_use:
        data["userhash"] = hash_to_use

    with open(file_path, "rb") as f:
        resp = requests.post(
            "https://catbox.moe/user/api.php",
            data=data,
            files={"fileToUpload": (file_path.name, f)},
            timeout=90,
        )
        resp.raise_for_status()
        url = resp.text.strip()
        if url.startswith("https://") or url.startswith("http://"):
            return url
        raise ValueError(f"Catbox failed with response: {url}")


def _upload_ucarecdn(file_path: pathlib.Path, pub_key: str = "demopublickey") -> str:
    """Upload to Uploadcare (ucarecdn.com)."""
    with open(file_path, "rb") as f:
        resp = requests.post(
            "https://upload.uploadcare.com/base/",
            data={
                "UPLOADCARE_PUB_KEY": pub_key,
                "UPLOADCARE_STORE": "1",
            },
            files={"file": (file_path.name, f)},
            timeout=60,
        )
        resp.raise_for_status()
        file_id = resp.json().get("file")
        if file_id:
            return f"https://ucarecdn.com/{file_id}/{file_path.name}"
        raise ValueError(f"Uploadcare failed: {resp.text}")


def upload_with_fallback(file_path: pathlib.Path, catbox_hash: Optional[str] = None) -> Tuple[str, str]:
    """Fallback chain: uguu -> catbox -> ucarecdn."""
    errors: List[str] = []

    try:
        url = _upload_uguu(file_path)
        return url, "uguu"
    except Exception as exc:
        errors.append(f"uguu: {exc}")

    try:
        url = _upload_catbox(file_path, user_hash=catbox_hash)
        return url, "catbox"
    except Exception as exc:
        errors.append(f"catbox: {exc}")

    try:
        url = _upload_ucarecdn(file_path)
        return url, "ucarecdn"
    except Exception as exc:
        errors.append(f"ucarecdn: {exc}")

    raise RuntimeError("All uploaders failed: " + " | ".join(errors))


# ============================================================================ #
# ComfyUI Process & Health Lifecycle                                           #
# ============================================================================ #

def check_comfy_health() -> bool:
    try:
        r = requests.get(f"http://{COMFY_HOST}/", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def ensure_comfyui_ready(timeout_seconds: int = 30) -> bool:
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        if check_comfy_health():
            return True
        time.sleep(1)
    return False


def load_default_workflow() -> Dict[str, Any]:
    with open(WORKFLOW_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def build_workflow_from_inputs(inputs: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    raw_prompt = inputs.get("prompt", "").strip()
    if not raw_prompt:
        raise ValueError("prompt is required")

    # Positive prompt with auto quality booster
    if ANIME_QUALITY_BOOSTER not in raw_prompt:
        positive_text = f"{raw_prompt}, {ANIME_QUALITY_BOOSTER}"
    else:
        positive_text = raw_prompt

    # Negative prompt
    custom_negative = inputs.get("negative_prompt", "").strip()
    if custom_negative:
        negative_text = f"{custom_negative}, {ANIME_NEGATIVE_DEFAULT}"
    else:
        negative_text = ANIME_NEGATIVE_DEFAULT

    width = int(inputs.get("width", 832))
    height = int(inputs.get("height", 1216))
    steps = int(inputs.get("steps", 12))
    # Cap steps to 20 maximum to guarantee fast execution and prevent abuse
    steps = min(20, max(6, steps))
    cfg = float(inputs.get("cfg", 3.0))

    seed = int(inputs.get("seed", -1))
    if seed < 0:
        seed = random.randint(1, 2**32 - 1)

    ckpt_override = inputs.get("model") or inputs.get("checkpoint") or CHECKPOINT_NAME
    lora_override = inputs.get("lora") or LORA_NAME

    workflow = load_default_workflow()
    workflow["1"]["inputs"]["ckpt_name"] = ckpt_override
    if "10" in workflow and "inputs" in workflow["10"]:
        workflow["10"]["inputs"]["lora_name"] = lora_override
        workflow["10"]["inputs"]["strength_model"] = float(inputs.get("lora_strength", 0.8))
        workflow["10"]["inputs"]["strength_clip"] = float(inputs.get("lora_clip", 0.8))
    workflow["2"]["inputs"]["text"] = positive_text
    workflow["3"]["inputs"]["text"] = negative_text
    workflow["4"]["inputs"]["width"] = width
    workflow["4"]["inputs"]["height"] = height
    workflow["5"]["inputs"]["seed"] = seed
    workflow["5"]["inputs"]["steps"] = steps
    workflow["5"]["inputs"]["cfg"] = cfg
    workflow["5"]["inputs"]["sampler_name"] = inputs.get("sampler", "euler")
    workflow["5"]["inputs"]["scheduler"] = inputs.get("scheduler", "sgm_uniform")

    return workflow, seed


# ============================================================================ #
# Serverless Execution Handler                                                 #
# ============================================================================ #

def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    start_time = time.time()
    job_id = event.get("id", f"job_{int(start_time * 1000)}")
    job_input = event.get("input", {})

    if not check_comfy_health():
        if not ensure_comfyui_ready(timeout_seconds=20):
            return {"status": "FAILED", "error": f"ComfyUI server at {COMFY_HOST} is not healthy"}

    # Determine workflow: custom raw workflow or generated from parameters
    if "workflow" in job_input and isinstance(job_input["workflow"], dict):
        workflow = job_input["workflow"]
        seed = int(job_input.get("seed", -1))
    else:
        try:
            workflow, seed = build_workflow_from_inputs(job_input)
        except Exception as err:
            return {"status": "FAILED", "error": str(err)}

    client_id = f"client_{job_id}"
    ws_url = f"ws://{COMFY_HOST}/ws?clientId={client_id}"

    try:
        ws = websocket.create_connection(ws_url, timeout=30)
    except Exception as ws_err:
        return {"status": "FAILED", "error": f"Failed to connect to ComfyUI websocket: {ws_err}"}

    try:
        # Submit prompt to ComfyUI
        logger.info(f"[{job_id}] 📤 Submitting workflow to ComfyUI /prompt...")
        queue_payload = {"prompt": workflow, "client_id": client_id}
        res = requests.post(f"http://{COMFY_HOST}/prompt", json=queue_payload, timeout=20)
        if res.status_code != 200:
            return {"status": "FAILED", "error": f"ComfyUI prompt rejection ({res.status_code}): {res.text}"}

        prompt_id = res.json().get("prompt_id")
        if not prompt_id:
            return {"status": "FAILED", "error": "No prompt_id returned from ComfyUI"}

        logger.info(f"[{job_id}] ⏳ Waiting for execution completion (prompt_id: {prompt_id})...")

        # Wait for WebSocket events
        execution_done = False
        while True:
            raw_msg = ws.recv()
            if not isinstance(raw_msg, str):
                continue
            msg = json.loads(raw_msg)
            msg_type = msg.get("type")

            if msg_type == "executing":
                data = msg.get("data", {})
                if data.get("node") is None and data.get("prompt_id") == prompt_id:
                    execution_done = True
                    break
            elif msg_type == "execution_error":
                data = msg.get("data", {})
                if data.get("prompt_id") == prompt_id:
                    return {
                        "status": "FAILED",
                        "error": f"ComfyUI execution error in node {data.get('node_id')} ({data.get('node_type')}): {data.get('exception_message')}",
                    }

        if not execution_done:
            return {"status": "FAILED", "error": "Workflow did not finish execution properly"}

        # Fetch output image filenames from history
        history_res = requests.get(f"http://{COMFY_HOST}/history/{prompt_id}", timeout=20)
        history_data = history_res.json().get(prompt_id, {})
        outputs = history_data.get("outputs", {})

        output_images: List[pathlib.Path] = []
        output_dir = pathlib.Path(COMFY_DIR) / "output"

        for node_id, node_out in outputs.items():
            if "images" in node_out:
                for img_info in node_out["images"]:
                    fname = img_info.get("filename")
                    subf = img_info.get("subfolder", "")
                    img_path = output_dir / subf / fname
                    if img_path.exists() and img_path.is_file():
                        output_images.append(img_path)

        if not output_images:
            return {"status": "FAILED", "error": "No output images found in ComfyUI history"}

        # Upload generated images via fallback chain (uguu -> catbox -> ucarecdn -> base64)
        uploaded_results: List[Dict[str, Any]] = []
        catbox_key = job_input.get("catbox_key", DEFAULT_CATBOX_USER_HASH)

        for img_path in output_images:
            file_size = img_path.stat().st_size
            try:
                url, storage = upload_with_fallback(img_path, catbox_key)
                uploaded_results.append({
                    "url": url,
                    "file_name": img_path.name,
                    "size_bytes": file_size,
                    "storage": storage,
                })
                logger.info(f"[{job_id}] ✨ Image uploaded to {storage}: {url}")
            except Exception as up_err:
                logger.warning(f"[{job_id}] ⚠️ Upload failed ({up_err}), falling back to Base64...")
                if file_size < 15 * 1024 * 1024:
                    with open(img_path, "rb") as bf:
                        b64 = base64.b64encode(bf.read()).decode("utf-8")
                    uploaded_results.append({
                        "url": "",
                        "base64": b64,
                        "file_name": img_path.name,
                        "size_bytes": file_size,
                        "storage": "base64",
                    })

        total_elapsed = time.time() - start_time
        return {
            "status": "COMPLETED",
            "execution_time_seconds": round(total_elapsed, 2),
            "seed": seed,
            "images": uploaded_results,
        }

    except Exception as exc:
        logger.error(f"[{job_id}] ❌ Error: {exc}")
        return {"status": "FAILED", "error": f"Inference error: {str(exc)}"}
    finally:
        try:
            ws.close()
        except Exception:
            pass


def concurrency_controller(current_concurrency):
    return MAX_CONCURRENCY


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info(f"🚀 Initializing ComfyUI Anime Serverless Worker (Concurrency: {MAX_CONCURRENCY})")
    logger.info(f"📂 ComfyUI Path      : {COMFY_DIR}")
    logger.info(f"🎨 Default Checkpoint: {CHECKPOINT_NAME}")
    logger.info("=" * 60)

    if not ensure_comfyui_ready(timeout_seconds=30):
        logger.error(f"❌ ComfyUI failed to respond on {COMFY_HOST}")
        sys.exit(1)

    start_params = {
        "handler": handler,
    }
    if MAX_CONCURRENCY > 1:
        start_params["concurrency_modifier"] = concurrency_controller

    runpod.serverless.start(start_params)

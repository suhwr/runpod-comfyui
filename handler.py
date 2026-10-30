import base64
import copy
import hashlib
import io
import json
import logging
import mimetypes
import os
import pathlib
import random
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
from typing import Any, Dict, List, Optional, Tuple

import requests
import runpod
import torch
import websocket

# ============================================================================ #
# Configuration & Hardware Diagnostics                                         #
# ============================================================================ #

os.environ.setdefault("PYTHONUNBUFFERED", "1")

if torch.cuda.is_available():
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    torch.backends.cudnn.benchmark = True

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("comfyui-worker")

COMFY_DIR = os.environ.get("COMFY_DIR", "/app/ComfyUI")
COMFY_HOST = os.environ.get("COMFY_HOST", "127.0.0.1:8188")
DEFAULT_CATBOX_USER_HASH = os.environ.get("CATBOX_KEY", "")
MAX_CONCURRENCY = max(1, int(os.environ.get("MAX_CONCURRENCY", "1")))

# File paths
TEMPLATE_DIR = os.path.dirname(__file__)
WORKFLOW_NOVA_PATH = os.path.join(TEMPLATE_DIR, "workflow_nova.json")

# Model Filenames (All 3 are pure 2.9B DiT sharing the same Qwen Text Encoder & VAE)
NOVA_UNET_NAME = os.environ.get("NOVA_UNET_NAME", "novaAnimeAM_v6029B.safetensors")
ORANGE_UNET_NAME = os.environ.get("ORANGE_UNET_NAME", "novaOrangeAM_v4029B.safetensors")
SILVERMOON_UNET_NAME = os.environ.get("SILVERMOON_UNET_NAME", "SilvermoonMix-Anima29B-Evolved-V2.3.safetensors")

NOVA_CLIP_NAME = os.environ.get("NOVA_CLIP_NAME", "qwen_3_06b_base.safetensors")
NOVA_VAE_NAME = os.environ.get("NOVA_VAE_NAME", "qwen_image_vae.safetensors")

# Default quality tags
NOVA_QUALITY_BOOSTER = (
    "masterpiece, best quality, score_9, score_8, score_7, very aesthetic, newest, absurdres, highres, highly detailed, "
    "delicate facial features, beautiful detailed eyes, detailed hair strands, "
    "cinematic lighting, soft volumetric illumination, vibrant colors, detailed scenery background, "
    "atmospheric depth"
)

ORANGE_QUALITY_BOOSTER = (
    "masterpiece, best quality, score_9, score_8, very aesthetic, newest, absurdres, highres, highly detailed, "
    "semi-realistic anime, expressive facial features, beautiful realistic eyes, soft skin texture, "
    "volumetric warm lighting, rich shadows, cinematic composition, depth of field"
)

SILVERMOON_QUALITY_BOOSTER = (
    "masterpiece, best quality, score_9, score_8, very aesthetic, newest, absurdres, highres, highly detailed, "
    "perfect anatomy, stable hands, beautiful expressive face, intricate eyes, delicate lineart, "
    "soft ambient lighting, harmonious colors, detailed illustration"
)

NEGATIVE_DEFAULT = (
    "worst quality, low quality, early, old, score_1, score_2, score_3, monochrome, jpeg artifacts, "
    "lowres, blurry, watermark, signature, bad anatomy, bad hands, missing fingers, extra digits, deformed, "
    "flat colors, washed out, dull lighting, oversaturated, amateur"
)

# ============================================================================ #
# Storage Uploaders with Automatic Fallback Chain                              #
# Backblaze B2 (Primary) -> Uguu -> Catbox -> Uploadcare -> Base64             #
# ============================================================================ #

def _upload_b2(file_path: pathlib.Path, folder: str = "tmp/comfyui") -> str:
    """
    Upload to Backblaze B2 (S3-compatible or native REST).
    Uses 'tmp/' prefix for automatic lifecycle expiration cleanup.
    """
    key_id = os.environ.get("B2_KEY_ID") or os.environ.get("AWS_ACCESS_KEY_ID")
    app_key = os.environ.get("B2_APPLICATION_KEY") or os.environ.get("AWS_SECRET_ACCESS_KEY")
    bucket = os.environ.get("B2_BUCKET_NAME")
    endpoint = os.environ.get("B2_ENDPOINT_URL") or os.environ.get("AWS_ENDPOINT_URL")

    if not (key_id and app_key and bucket):
        raise ValueError("Backblaze B2 credentials (B2_KEY_ID, B2_APPLICATION_KEY, B2_BUCKET_NAME) not set")

    clean_folder = folder.strip("/")
    target_key = f"{clean_folder}/{int(time.time())}_{uuid.uuid4().hex[:8]}_{file_path.name}"
    content_type, _ = mimetypes.guess_type(str(file_path))
    if not content_type:
        content_type = "image/png"

    # Attempt 1: boto3 S3 API if endpoint is provided
    if endpoint:
        try:
            import boto3
            from botocore.config import Config

            s3 = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=key_id,
                aws_secret_access_key=app_key,
                config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
            )
            with open(file_path, "rb") as f:
                s3.upload_fileobj(f, bucket, target_key, ExtraArgs={"ContentType": content_type})

            public_prefix = os.environ.get("B2_PUBLIC_URL_PREFIX", "").rstrip("/")
            if public_prefix:
                return f"{public_prefix}/{target_key}"

            try:
                return s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": target_key}, ExpiresIn=86400)
            except Exception:
                parsed = urllib.parse.urlsplit(endpoint)
                return f"{parsed.scheme}://{bucket}.{parsed.netloc}/{target_key}"
        except ImportError:
            pass

    # Attempt 2: B2 Native REST API (No external packages required)
    auth_resp = requests.get(
        "https://api.backblazeb2.com/b2api/v3/b2_authorize_account",
        auth=(key_id, app_key),
        timeout=30,
    )
    auth_resp.raise_for_status()
    auth_data = auth_resp.json()
    api_url = auth_data["apiUrl"]
    auth_token = auth_data["authorizationToken"]
    download_url = auth_data["downloadUrl"]

    bucket_id = os.environ.get("B2_BUCKET_ID")
    if not bucket_id:
        bucket_id = auth_data.get("allowed", {}).get("bucketId")
    if not bucket_id:
        lb_resp = requests.post(
            f"{api_url}/b2api/v3/b2_list_buckets",
            headers={"Authorization": auth_token},
            json={"accountId": auth_data["accountId"], "bucketName": bucket},
            timeout=30,
        )
        lb_resp.raise_for_status()
        buckets = lb_resp.json().get("buckets", [])
        if buckets:
            bucket_id = buckets[0]["bucketId"]
        else:
            raise ValueError(f"B2 bucket '{bucket}' not found")

    up_resp = requests.post(
        f"{api_url}/b2api/v3/b2_get_upload_url",
        headers={"Authorization": auth_token},
        json={"bucketId": bucket_id},
        timeout=30,
    )
    up_resp.raise_for_status()
    up_data = up_resp.json()
    upload_url = up_data["uploadUrl"]
    upload_token = up_data["authorizationToken"]

    sha1 = hashlib.sha1()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha1.update(chunk)
    digest = sha1.hexdigest()

    file_size = file_path.stat().st_size
    with open(file_path, "rb") as f:
        res = requests.post(
            upload_url,
            headers={
                "Authorization": upload_token,
                "X-Bz-File-Name": urllib.parse.quote(target_key),
                "Content-Type": content_type,
                "Content-Length": str(file_size),
                "X-Bz-Content-Sha1": digest,
            },
            data=f,
            timeout=120,
        )
        res.raise_for_status()

    public_prefix = os.environ.get("B2_PUBLIC_URL_PREFIX", "").rstrip("/")
    if public_prefix:
        return f"{public_prefix}/{target_key}"

    return f"{download_url}/file/{bucket}/{target_key}"


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
    """Fallback chain: Backblaze B2 (if configured) -> uguu -> catbox -> ucarecdn."""
    errors: List[str] = []

    # 1. Backblaze B2 Object Storage (tmp/ auto-expire lifecycle)
    if os.environ.get("B2_APPLICATION_KEY") or os.environ.get("AWS_SECRET_ACCESS_KEY"):
        try:
            url = _upload_b2(file_path, folder="tmp/comfyui")
            return url, "backblaze_b2"
        except Exception as exc:
            logger.warning(f"Backblaze B2 upload failed ({exc}), trying fallback uploaders...")
            errors.append(f"b2: {exc}")

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
# Fast ComfyUI Readiness Checks (100ms polling interval)                        #
# ============================================================================ #

def check_comfy_health() -> bool:
    try:
        r = requests.get(f"http://{COMFY_HOST}/", timeout=0.5)
        return r.status_code == 200
    except Exception:
        return False


def ensure_comfyui_ready(timeout_seconds: int = 30) -> bool:
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        if check_comfy_health():
            return True
        time.sleep(0.1)
    return False


def build_workflow_from_inputs(inputs: Dict[str, Any]) -> Tuple[Dict[str, Any], int, str]:
    """Builds workflow based on chosen model ('silvermoon' [default], 'nova', or 'orange')."""
    raw_prompt = inputs.get("prompt", "").strip()
    if not raw_prompt:
        raise ValueError("prompt is required")

    model_choice = str(inputs.get("model", "silvermoon")).strip().lower()

    # Determine UNet, display name, and quality booster
    if "orange" in model_choice or "2.5d" in model_choice:
        selected_unet = inputs.get("unet_name", ORANGE_UNET_NAME)
        active_model_name = "Nova Orange AM (2.9B)"
        quality_booster = ORANGE_QUALITY_BOOSTER
    elif "nova" in model_choice or "anime" in model_choice or "v6" in model_choice:
        selected_unet = inputs.get("unet_name", NOVA_UNET_NAME)
        active_model_name = "Nova Anime AM v6.0 (2.9B)"
        quality_booster = NOVA_QUALITY_BOOSTER
    else:
        selected_unet = inputs.get("unet_name", SILVERMOON_UNET_NAME)
        active_model_name = "SilvermoonMix Anima Evolved (2.9B)"
        quality_booster = SILVERMOON_QUALITY_BOOSTER

    seed = int(inputs.get("seed", -1))
    if seed <= 0:
        seed = random.randint(1, 2**32 - 1)

    custom_negative = inputs.get("negative_prompt", "").strip()

    with open(WORKFLOW_NOVA_PATH, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    if quality_booster not in raw_prompt:
        positive_text = f"{raw_prompt}, {quality_booster}"
    else:
        positive_text = raw_prompt

    if custom_negative:
        negative_text = f"{custom_negative}, {NEGATIVE_DEFAULT}"
    else:
        negative_text = NEGATIVE_DEFAULT

    width = int(inputs.get("width", 768))
    height = int(inputs.get("height", 1024))
    steps = int(inputs.get("steps", 12))
    steps = min(35, max(8, steps))
    cfg = float(inputs.get("cfg", 2.6))

    sampler = inputs.get("sampler", "er_sde")
    scheduler = inputs.get("scheduler", "simple")

    workflow["1"]["inputs"]["unet_name"] = selected_unet
    workflow["2"]["inputs"]["clip_name"] = inputs.get("clip_name", NOVA_CLIP_NAME)
    workflow["3"]["inputs"]["vae_name"] = inputs.get("vae_name", NOVA_VAE_NAME)
    workflow["4"]["inputs"]["text"] = positive_text
    workflow["5"]["inputs"]["text"] = negative_text
    workflow["6"]["inputs"]["width"] = width
    workflow["6"]["inputs"]["height"] = height
    workflow["7"]["inputs"]["seed"] = seed
    workflow["7"]["inputs"]["steps"] = steps
    workflow["7"]["inputs"]["cfg"] = cfg
    workflow["7"]["inputs"]["sampler_name"] = sampler
    workflow["7"]["inputs"]["scheduler"] = scheduler

    return workflow, seed, active_model_name


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

    # Determine workflow: custom raw workflow or built from inputs
    if "workflow" in job_input and isinstance(job_input["workflow"], dict):
        workflow = job_input["workflow"]
        seed = int(job_input.get("seed", -1))
        active_model = "custom_workflow"
    else:
        try:
            workflow, seed, active_model = build_workflow_from_inputs(job_input)
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
        logger.info(f"[{job_id}] 📤 Submitting {active_model} workflow to ComfyUI...")
        queue_payload = {"prompt": workflow, "client_id": client_id}
        res = requests.post(f"http://{COMFY_HOST}/prompt", json=queue_payload, timeout=20)
        if res.status_code != 200:
            return {"status": "FAILED", "error": f"ComfyUI prompt rejection ({res.status_code}): {res.text}"}

        prompt_id = res.json().get("prompt_id")
        if not prompt_id:
            return {"status": "FAILED", "error": "No prompt_id returned from ComfyUI"}

        logger.info(f"[{job_id}] ⏳ Waiting for completion (prompt_id: {prompt_id})...")

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
                        "error": f"ComfyUI error in node {data.get('node_id')} ({data.get('node_type')}): {data.get('exception_message')}",
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

        # Dual-mode return:
        # If output <= 7MB (and cumulative <= 7MB), directly return Base64 (zero upload & download latency)
        # If output > 7MB, upload to Backblaze B2 / external storage
        MAX_DIRECT_B64_BYTES = 7 * 1024 * 1024  # 7MB threshold
        uploaded_results: List[Dict[str, Any]] = []
        catbox_key = job_input.get("catbox_key", DEFAULT_CATBOX_USER_HASH)
        cumulative_b64 = 0

        for img_path in output_images:
            file_size = img_path.stat().st_size
            if file_size <= MAX_DIRECT_B64_BYTES and (cumulative_b64 + file_size) <= MAX_DIRECT_B64_BYTES:
                with open(img_path, "rb") as bf:
                    b64 = base64.b64encode(bf.read()).decode("utf-8")
                cumulative_b64 += file_size
                uploaded_results.append({
                    "url": "",
                    "base64": b64,
                    "file_name": img_path.name,
                    "size_bytes": file_size,
                    "storage": "base64",
                })
                logger.info(f"[{job_id}] ⚡ Image {img_path.name} ({file_size} bytes) returned directly via Base64")
            else:
                try:
                    url, storage = upload_with_fallback(img_path, catbox_key)
                    uploaded_results.append({
                        "url": url,
                        "base64": "",
                        "file_name": img_path.name,
                        "size_bytes": file_size,
                        "storage": storage,
                    })
                    logger.info(f"[{job_id}] ✨ Image uploaded to {storage}: {url}")
                except Exception as up_err:
                    logger.warning(f"[{job_id}] ⚠️ Upload failed ({up_err}), falling back to Base64...")
                    if file_size < 10 * 1024 * 1024:
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
            "model_used": active_model,
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
    logger.info(f"🚀 Initializing Dual-Model ComfyUI Serverless Worker")
    logger.info(f"📂 ComfyUI Path : {COMFY_DIR}")
    logger.info(f"🎨 Model 1 (Default): Nova Anime AM (2.9B) [Anima DiT + Qwen]")
    logger.info(f"🎨 Model 2          : NoobAI-XL v1.1 [SDXL Native]")
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

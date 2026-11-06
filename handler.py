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
import socket
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
    try:
        _gpu_name = torch.cuda.get_device_name(0)
        _gpu_cap = torch.cuda.get_device_capability(0)
        _vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        logging.info(f"🚀 Active GPU: {_gpu_name} (sm_{_gpu_cap[0]}{_gpu_cap[1]}, {_vram_gb:.2f} GB VRAM) — PyTorch {torch.__version__}")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("comfyui-worker")

COMFY_DIR = os.environ.get("COMFY_DIR", "/app/ComfyUI")
COMFY_HOST = os.environ.get("COMFY_HOST", "127.0.0.1:8188")
DEFAULT_CATBOX_USER_HASH = os.environ.get("CATBOX_KEY", "")
MAX_CONCURRENCY = max(1, int(os.environ.get("MAX_CONCURRENCY", "1")))

# File paths
TEMPLATE_DIR = os.path.dirname(__file__)
WORKFLOW_ANIMA_PATH = os.path.join(TEMPLATE_DIR, "workflow_anima.json")

# Model Filenames (Pure 2.9B DiT sharing the same Qwen Text Encoder & VAE)
NOVA_UNET_NAME = os.environ.get("NOVA_UNET_NAME", "novaAnimeAM_v6029B.safetensors")
SILVERMOON_UNET_NAME = os.environ.get("SILVERMOON_UNET_NAME", "SilvermoonMix-Anima29B-Evolved-V2.3.safetensors")
ORANGE_UNET_NAME = os.environ.get("ORANGE_UNET_NAME", "novaOrangeAM_v4029B.safetensors")
ANIMA_BASE_UNET_NAME = os.environ.get("ANIMA_BASE_UNET_NAME", "anima-base-v1.0.safetensors")
ANIMA_TURBO_UNET_NAME = os.environ.get("ANIMA_TURBO_UNET_NAME", "anima-turbo-v1.1.safetensors")

NOVA_CLIP_NAME = os.environ.get("NOVA_CLIP_NAME", "qwen_3_06b_base.safetensors")
NOVA_VAE_NAME = os.environ.get("NOVA_VAE_NAME", "qwen_image_vae.safetensors")
TURBO_LORA_NAME = os.environ.get("TURBO_LORA_NAME", "Anima_Turbo_v1.1.safetensors")


def get_comfy_available_loras() -> List[str]:
    """Fetch exact list of LoRAs recognized by ComfyUI's LoraLoader."""
    try:
        r = requests.get(f"http://{COMFY_HOST}/object_info/LoraLoader", timeout=2)
        if r.status_code == 200:
            lora_input = r.json().get("LoraLoader", {}).get("input", {}).get("required", {}).get("lora_name", [])
            if lora_input and isinstance(lora_input[0], list) and lora_input[0]:
                return lora_input[0]
    except Exception as exc:
        logger.debug(f"Could not query /object_info/LoraLoader ({exc}), falling back to disk...")

    lora_dir = os.path.join(COMFY_DIR, "models", "loras")
    if os.path.isdir(lora_dir):
        try:
            return os.listdir(lora_dir)
        except Exception:
            pass
    return []


def resolve_lora_name(requested_name: str, available_loras: Optional[List[str]] = None) -> Optional[str]:
    """
    Resolve user-requested LoRA name to exact filename recognized by ComfyUI.
    Returns None if the requested LoRA is not present in ComfyUI or on disk.
    """
    req_clean = str(requested_name).strip()
    if not req_clean:
        return None

    if available_loras is None:
        available_loras = get_comfy_available_loras()

    if not available_loras:
        return req_clean

    candidates = [req_clean]
    if not req_clean.endswith(".safetensors") and not req_clean.endswith(".pt"):
        candidates.append(f"{req_clean}.safetensors")
        candidates.append(f"{req_clean}.pt")

    # 1. Exact match
    for cand in candidates:
        if cand in available_loras:
            return cand

    # 2. Case-insensitive exact match
    for f in available_loras:
        for cand in candidates:
            if f.lower() == cand.lower():
                return f

    # 3. Substring match
    for cand in candidates:
        cand_stem = cand.replace(".safetensors", "").replace(".pt", "").lower()
        if not cand_stem:
            continue
        for f in available_loras:
            f_stem = f.replace(".safetensors", "").replace(".pt", "").lower()
            if cand_stem in f_stem or f_stem in cand_stem:
                return f

    return None

# Default quality tags (Tuned specifically for Pure 2D Anime & Anti-Slop Digital Art)
NOVA_QUALITY_BOOSTER = (
    "score_9, score_8, score_7, very aesthetic, newest, absurdres, highres, "
    "2d, flat color, flat shading, cel shading, clean lineart, digital illustration, "
    "drawing (medium), anime screencap, expressive eyes, delicate facial features, "
    "detailed hair strands, vibrant anime coloring"
)

ORANGE_QUALITY_BOOSTER = (
    "score_9, score_8, very aesthetic, newest, absurdres, highres, "
    "2d, digital illustration, clean lineart, expressive facial features, beautiful eyes, "
    "vibrant colors, harmonious composition"
)

SILVERMOON_QUALITY_BOOSTER = (
    "score_9, score_8, very aesthetic, newest, absurdres, highres, "
    "2d, flat color, clean lineart, delicate brushwork, accurate hands, finely detailed fingers, "
    "expressive eyes, delicate facial features, harmonious colors, detailed digital illustration"
)

NEGATIVE_DEFAULT = (
    "worst quality, low quality, early, old, score_1, score_2, score_3, score_4, score_5, score_6, monochrome, jpeg artifacts, "
    "lowres, blurry, watermark, signature, username, error, "
    "bad anatomy, bad hands, missing fingers, extra digits, extra fingers, fewer digits, fused fingers, "
    "elongated fingers, long fingers, malformed fingers, mutated hands, poorly drawn hands, disfigured, "
    "bad proportions, gross proportions, malformed limbs, extra limbs, missing limbs, floating limbs, "
    "washed out, dull lighting, oversaturated, amateur, overexposed, blown out highlights, glaring light, glowing glare, "
    "2.5d, 3d, realistic, photorealistic, semi-realistic, cg, cgi, 3d render, unreal engine, octane render, "
    "airbrushed, plastic, fake depth, ambient occlusion, raytracing, volumetric lighting, gradient shading, "
    "realistic skin, shiny skin, oily skin, doll-like face, mannequin, glossy plastic, 3d model"
)

NEGATIVE_BG_BLOCK = (
    "bad background, poorly drawn background, simple background, white background, "
    "plain background, blank background, solid background, empty background, "
    "grey background, gray background, monochrome background, "
    "minimalist background, void background, lacking background, unfinished background"
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
    """Builds workflow based on chosen model ('nova' [default], 'silvermoon', or 'orange')."""
    raw_prompt = inputs.get("prompt", "").strip()
    if not raw_prompt:
        raise ValueError("prompt is required")

    model_choice = str(inputs.get("model", "nova")).strip().lower()

    # Determine UNet, display name, and quality booster
    if "silvermoon" in model_choice or "silver" in model_choice or "moon" in model_choice:
        selected_unet = inputs.get("unet_name", SILVERMOON_UNET_NAME)
        active_model_name = "SilvermoonMix Anima Evolved (2.9B)"
        quality_booster = SILVERMOON_QUALITY_BOOSTER
    elif "base" in model_choice or "circlestone" in model_choice:
        selected_unet = inputs.get("unet_name", ANIMA_BASE_UNET_NAME)
        active_model_name = "CircleStone Anima Base v1.0 (2.9B DiT)"
        quality_booster = NOVA_QUALITY_BOOSTER
    elif "anima_turbo" in model_choice:
        selected_unet = inputs.get("unet_name", ANIMA_TURBO_UNET_NAME)
        active_model_name = "CircleStone Anima Turbo v1.1 (2.9B DiT)"
        quality_booster = NOVA_QUALITY_BOOSTER
    elif "orange" in model_choice or "2.5d" in model_choice:
        orange_path = os.path.join(COMFY_DIR, "models", "diffusion_models", ORANGE_UNET_NAME)
        if os.path.exists(orange_path):
            selected_unet = inputs.get("unet_name", ORANGE_UNET_NAME)
            active_model_name = "Nova Orange AM (2.9B)"
            quality_booster = ORANGE_QUALITY_BOOSTER
        else:
            logger.info("Nova Orange AM UNet not found on disk, gracefully falling back to Nova Anime AM v6.0")
            selected_unet = inputs.get("unet_name", NOVA_UNET_NAME)
            active_model_name = "Nova Anime AM v6.0 (2.9B)"
            quality_booster = NOVA_QUALITY_BOOSTER
    else:
        # Default: Nova Anime AM v6.0 (2D Anime Flagship & Danbooru Master)
        selected_unet = inputs.get("unet_name", NOVA_UNET_NAME)
        active_model_name = "Nova Anime AM v6.0 (2.9B)"
        quality_booster = NOVA_QUALITY_BOOSTER

    seed = int(inputs.get("seed", -1))
    if seed <= 0:
        seed = random.randint(1_000_000_000_000_000, 9_999_999_999_999_999)

    custom_negative = inputs.get("negative_prompt", "").strip()

    with open(WORKFLOW_ANIMA_PATH, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    # ─── Curated Presets with Dedicated 2D Boosters & Clean LoRA Stacks ────────
    preset = str(inputs.get("preset", "")).strip().lower()
    lora_list = []
    preset_cfg = None

    if preset in ("pure_2d", "flat_anime", "cel_shading", "flat_2d"):
        quality_booster = (
            "score_9, score_8, 2d, pure 2d, flat color, flat shading, cel shading, "
            "anime screencap, clean lineart, bold outline, traditional anime drawing, vibrant colors"
        )
        lora_list.append({"name": "Anima_Turbo_v1.1.safetensors", "strength": 0.90})
        lora_list.append({"name": "sharp_lineart", "strength": 0.50, "strength_model": 0.50, "strength_clip": 0.60})
        preset_cfg = 1.15
    elif preset in ("digital_art", "master_illustrator", "artist", "illustrator", "clean_anime"):
        # The SOTA Digital Artist recipe: Turbo + Mild Aesthetic Boost (clean 2D lines, NO heavy micro-detailers)
        quality_booster = (
            "score_9, score_8, very aesthetic, newest, 2d, digital illustration, "
            "clean lineart, cel shading, flat color, crisp outline, vibrant anime coloring, "
            "expressive eyes, delicate facial features, high quality drawing"
        )
        lora_list.append({"name": "Anima_Turbo_v1.1.safetensors", "strength": 0.90})
        lora_list.append({"name": "aesthetic_boost", "strength": 0.45, "strength_model": 0.40, "strength_clip": 0.50})
        preset_cfg = 1.25
    elif preset in ("sketch", "hand_drawn_sketch", "rough_sketch", "pencil_sketch"):
        # Authentic Hand-Drawn Sketch / Pro Draft (Yamimatsu7)
        quality_booster = (
            "score_9, score_8, very aesthetic, sketch, graphite sketch, pencil drawing, "
            "clean thin lineart, traditional media, paper texture, hatching, monochrome, "
            "artist rough draft, expressive eyes"
        )
        lora_list.append({"name": "Anima_Turbo_v1.1.safetensors", "strength": 0.85})
        lora_list.append({"name": "sketch_style", "strength": 0.85, "strength_model": 0.85, "strength_clip": 0.80})
        preset_cfg = 1.20
    elif preset in ("character_focus", "strong_character", "character"):
        # Maximum Character Recognition & Costume Fidelity (RL Prompt Alignment)
        quality_booster = (
            "score_9, score_8, very aesthetic, newest, 2d, character sheet, sharp focus, "
            "clean lineart, flat color, vibrant anime coloring, accurate character features, expressive face"
        )
        lora_list.append({"name": "Anima_Turbo_v1.1.safetensors", "strength": 0.90})
        lora_list.append({"name": "anatomy_fix", "strength": 0.65, "strength_model": 0.60, "strength_clip": 0.70})
        preset_cfg = 1.25
    elif preset in ("watercolor_classic", "sugimori", "classic_art", "watercolor"):
        # Classic 90s Hand-Drawn Watercolor (Sugimori Style)
        quality_booster = (
            "score_9, score_8, very aesthetic, ken sugimori (style), watercolor (medium), "
            "hand-drawn illustration, soft watercolor wash, delicate ink lines, paper texture, "
            "traditional media, 1990s official art"
        )
        lora_list.append({"name": "Anima_Turbo_v1.1.safetensors", "strength": 0.85})
        lora_list.append({"name": "watercolor_artist", "strength": 0.85, "strength_model": 0.80, "strength_clip": 0.85})
        preset_cfg = 1.20
    elif preset in ("modern_anime", "pixiv", "noobai"):
        # Modern Danbooru Vibrant Art (Pixiv / Twitter Style)
        quality_booster = (
            "score_9, score_8, very aesthetic, newest, 2d, pixiv, digital illustration, "
            "vivid colors, cel shading, crisp lineart, trending on pixiv, flat color, anime artwork"
        )
        lora_list.append({"name": "Anima_Turbo_v1.1.safetensors", "strength": 0.90})
        lora_list.append({"name": "noobai_style", "strength": 0.75, "strength_model": 0.70, "strength_clip": 0.80})
        preset_cfg = 1.25
    elif preset in ("dynamic_action", "battle_pose", "action"):
        # Dynamic Combat & Martial Arts Fighting Poses
        quality_booster = (
            "score_9, score_8, very aesthetic, 2d, dynamic action pose, fighting stance, "
            "motion lines, intense perspective, crisp lineart, cel shading, energetic composition"
        )
        lora_list.append({"name": "Anima_Turbo_v1.1.safetensors", "strength": 0.90})
        lora_list.append({"name": "dynamic_action", "strength": 0.75, "strength_model": 0.70, "strength_clip": 0.80})
        preset_cfg = 1.25
    elif preset in ("retro_90s", "retro", "vintage"):
        # Retro 90s Vintage Cel Animation (Sailor Moon style)
        quality_booster = (
            "score_9, score_8, 1990s (style), retro anime, vintage anime cel, "
            "flat color, clean lineart, anime screencap, traditional cel animation, "
            "scanlines, nostalgic anime aesthetic, vibrant classic palette"
        )
        lora_list.append({"name": "Anima_Turbo_v1.1.safetensors", "strength": 0.85})
        lora_list.append({"name": "retro_90s", "strength": 0.80, "strength_model": 0.75, "strength_clip": 0.85})
        preset_cfg = 1.20
    elif preset in ("painterly", "fantasy", "cinematic"):
        # Painterly Concept Art & Brushwork
        quality_booster = (
            "score_9, score_8, very aesthetic, painterly illustration, visible brush strokes, "
            "traditional art media, expressive colors, artistic composition"
        )
        lora_list.append({"name": "Anima_Turbo_v1.1.safetensors", "strength": 0.90})
        lora_list.append({"name": "fantasy_art", "strength": 0.60, "strength_model": 0.55, "strength_clip": 0.65})
        preset_cfg = 1.30
    elif use_turbo:
        lora_list.append({
            "name": TURBO_LORA_NAME,
            "strength": float(inputs.get("turbo_strength", 1.0)),
        })

    if quality_booster not in raw_prompt:
        positive_text = f"{raw_prompt}, {quality_booster}"
    else:
        positive_text = raw_prompt

    # Detect if user intentionally requested a plain, solid, or white background
    user_wants_plain_bg = any(
        kw in raw_prompt.lower()
        for kw in (
            "white background",
            "simple background",
            "plain background",
            "blank background",
            "solid background",
            "empty background",
            "transparent background",
            "monochrome background",
        )
    )

    base_negative = NEGATIVE_DEFAULT
    if not user_wants_plain_bg:
        base_negative = f"{NEGATIVE_DEFAULT}, {NEGATIVE_BG_BLOCK}"

    if custom_negative:
        negative_text = f"{custom_negative}, {base_negative}"
    else:
        negative_text = base_negative

    # ─── Custom Multiple LoRAs from Request ────────────────────────────────────
    raw_loras = inputs.get("loras") or inputs.get("lora")
    if raw_loras:
        if isinstance(raw_loras, (str, dict)):
            raw_loras = [raw_loras]
        if isinstance(raw_loras, list):
            for item in raw_loras:
                if isinstance(item, str) and item.strip():
                    lora_list.append({"name": item.strip(), "strength": 1.0})
                elif isinstance(item, dict) and (item.get("name") or item.get("lora") or item.get("file")):
                    lora_list.append(item)

    available_comfy_loras = get_comfy_available_loras()
    logger.info(f"🔎 Available LoRAs recognized by ComfyUI: {available_comfy_loras}")

    current_model = ["1", 0]
    current_clip = ["2", 0]
    applied_loras = []
    missing_loras = []
    has_turbo_active = False
    has_4step_active = False

    node_id_counter = 100
    for lora_entry in lora_list:
        l_name = lora_entry.get("name") or lora_entry.get("lora") or lora_entry.get("file") or ""
        if not l_name:
            continue

        resolved_name = resolve_lora_name(l_name, available_comfy_loras)

        # Failsafe: if not recognized or not available in ComfyUI, skip to prevent 400 prompt rejection
        if not resolved_name or (available_comfy_loras and resolved_name not in available_comfy_loras):
            logger.warning(f"⚠️ LoRA '{l_name}' not available in ComfyUI (Available: {available_comfy_loras}). Skipped to prevent render crash.")
            missing_loras.append(l_name)
            continue

        base_strength = float(lora_entry.get("strength", 1.0))
        strength_model = float(lora_entry.get("strength_model", base_strength))
        strength_clip = float(lora_entry.get("strength_clip", base_strength))

        if "4step" in resolved_name.lower():
            has_4step_active = True
            has_turbo_active = True
        elif "turbo" in resolved_name.lower():
            has_turbo_active = True

        node_id_counter += 1
        node_id = str(node_id_counter)

        workflow[node_id] = {
            "inputs": {
                "lora_name": resolved_name,
                "strength_model": strength_model,
                "strength_clip": strength_clip,
                "model": current_model,
                "clip": current_clip,
            },
            "class_type": "LoraLoader",
            "_meta": {
                "title": f"Load LoRA ({resolved_name})"
            }
        }
        current_model = [node_id, 0]
        current_clip = [node_id, 1]
        applied_loras.append({
            "node_id": node_id,
            "lora_name": resolved_name,
            "strength_model": strength_model,
            "strength_clip": strength_clip,
        })

    if has_4step_active:
        default_steps = 4
        default_cfg = 1.15
        default_sampler = "euler"
    elif has_turbo_active:
        default_steps = 10
        if preset_cfg is not None:
            default_cfg = preset_cfg
        else:
            default_cfg = 1.25
        default_sampler = "euler"
    else:
        default_steps = 16
        default_cfg = 1.8
        default_sampler = "euler"

    width = int(inputs.get("width", 768))
    height = int(inputs.get("height", 1024))
    steps = int(inputs.get("steps", default_steps))
    steps = min(35, max(4, steps))
    cfg = float(inputs.get("cfg", default_cfg))

    sampler = inputs.get("sampler", default_sampler)
    scheduler = inputs.get("scheduler", "simple")

    workflow["1"]["inputs"]["unet_name"] = selected_unet
    workflow["2"]["inputs"]["clip_name"] = inputs.get("clip_name", NOVA_CLIP_NAME)
    workflow["3"]["inputs"]["vae_name"] = inputs.get("vae_name", NOVA_VAE_NAME)
    workflow["4"]["inputs"]["text"] = positive_text
    workflow["4"]["inputs"]["clip"] = current_clip
    workflow["5"]["inputs"]["text"] = negative_text
    workflow["5"]["inputs"]["clip"] = current_clip
    workflow["6"]["inputs"]["width"] = width
    workflow["6"]["inputs"]["height"] = height
    workflow["7"]["inputs"]["seed"] = seed
    workflow["7"]["inputs"]["steps"] = steps
    workflow["7"]["inputs"]["cfg"] = cfg
    workflow["7"]["inputs"]["sampler_name"] = sampler
    workflow["7"]["inputs"]["scheduler"] = scheduler
    workflow["7"]["inputs"]["model"] = current_model

    return workflow, seed, active_model_name, applied_loras, missing_loras


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

    applied_loras = []
    missing_loras = []
    # Determine workflow: custom raw workflow or built from inputs
    if "workflow" in job_input and isinstance(job_input["workflow"], dict):
        workflow = job_input["workflow"]
        seed = int(job_input.get("seed", -1))
        active_model = "custom_workflow"
    else:
        try:
            workflow, seed, active_model, applied_loras, missing_loras = build_workflow_from_inputs(job_input)
        except Exception as err:
            return {"status": "FAILED", "error": str(err)}

    client_id = f"client_{job_id}"
    ws_url = f"ws://{COMFY_HOST}/ws?clientId={client_id}"

    execution_done = False
    try:
        ws = websocket.create_connection(ws_url, timeout=5)
    except Exception as ws_err:
        return {"status": "FAILED", "error": f"Failed to connect to ComfyUI websocket: {ws_err}"}

    try:
        # Submit prompt to ComfyUI
        if applied_loras:
            lora_summary = ", ".join([f"{l['lora_name']} (s={l['strength_model']:.2f})" for l in applied_loras])
            logger.info(f"[{job_id}] 🎨 Chained {len(applied_loras)} LoRA(s): {lora_summary}")
        logger.info(f"[{job_id}] 📤 Submitting {active_model} workflow to ComfyUI...")
        queue_payload = {"prompt": workflow, "client_id": client_id}
        res = requests.post(f"http://{COMFY_HOST}/prompt", json=queue_payload, timeout=30)
        if res.status_code != 200:
            return {"status": "FAILED", "error": f"ComfyUI prompt rejection ({res.status_code}): {res.text}"}

        prompt_id = res.json().get("prompt_id")
        if not prompt_id:
            return {"status": "FAILED", "error": "No prompt_id returned from ComfyUI"}

        logger.info(f"[{job_id}] ⏳ Waiting for completion (prompt_id: {prompt_id})...")

        # Wait for WebSocket events with resilient heartbeat loop
        max_job_timeout = int(job_input.get("timeout", 600))  # Allow up to 10 minutes (for heavy cold-start model loads)
        start_wait = time.time()
        last_heartbeat = time.time()

        while (time.time() - start_wait) < max_job_timeout:
            try:
                # 5s socket timeout prevents hanging while letting us check ComfyUI health
                raw_msg = ws.recv()
            except (websocket.WebSocketTimeoutException, socket.timeout):
                if not check_comfy_health():
                    return {"status": "FAILED", "error": "ComfyUI process crashed during execution"}
                if time.time() - last_heartbeat >= 10:
                    elapsed = int(time.time() - start_wait)
                    logger.info(f"[{job_id}] ⏳ ComfyUI active ({elapsed}s elapsed, weights loading/sampling)...")
                    last_heartbeat = time.time()
                continue
            except Exception as ws_read_err:
                logger.error(f"[{job_id}] WebSocket read error: {ws_read_err}")
                break

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
            return {"status": "FAILED", "error": f"Workflow did not complete within {max_job_timeout}s timeout"}

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
        res_payload = {
            "status": "COMPLETED",
            "model_used": active_model,
            "execution_time_seconds": round(total_elapsed, 2),
            "seed": seed,
            "loras_applied": [l["lora_name"] for l in applied_loras],
            "images": uploaded_results,
        }
        if missing_loras:
            res_payload["loras_missing"] = missing_loras
        return res_payload

    except Exception as exc:
        logger.error(f"[{job_id}] ❌ Error: {exc}")
        return {"status": "FAILED", "error": f"Inference error: {str(exc)}"}
    finally:
        if not execution_done:
            try:
                requests.post(f"http://{COMFY_HOST}/interrupt", timeout=5)
                logger.info(f"[{job_id}] 🛑 Interrupted pending ComfyUI execution queue")
            except Exception:
                pass
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

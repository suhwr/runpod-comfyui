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

# Model Filenames & URLs (Pure 2.9B DiT sharing the same Qwen Text Encoder & VAE)
NOVA_UNET_NAME = os.environ.get("NOVA_UNET_NAME", "novaAnimeAM_v6029B.safetensors")
NOVA_UNET_URL = os.environ.get(
    "NOVA_UNET_URL",
    "https://huggingface.co/mogaru99/novaAnimeAM_v6029B/resolve/main/novaAnimeAM_v6029B.safetensors"
)

SILVERMOON_UNET_NAME = os.environ.get("SILVERMOON_UNET_NAME", "SilvermoonMix-Anima29B-Evolved-V2.3.safetensors")
SILVERMOON_UNET_URL = os.environ.get(
    "SILVERMOON_UNET_URL",
    "https://huggingface.co/silvermoong/SilvermoonMix-Anima-Evolved/resolve/main/SilvermoonMix-Anima29B-Evolved-V2.3.safetensors"
)

ORANGE_UNET_NAME = os.environ.get("ORANGE_UNET_NAME", "novaOrangeAM_v4029B.safetensors")
ORANGE_UNET_URL = os.environ.get(
    "ORANGE_UNET_URL",
    "https://huggingface.co/mogaru99/novaOrangeAM_v4029B/resolve/main/novaOrangeAM_v4029B.safetensors"
)

ANIMA_BASE_UNET_NAME = os.environ.get("ANIMA_BASE_UNET_NAME", "anima-base-v1.0.safetensors")
ANIMA_BASE_UNET_URL = os.environ.get(
    "ANIMA_BASE_UNET_URL",
    "https://huggingface.co/circlestone-labs/Anima/resolve/main/split_files/diffusion_models/anima-base-v1.0.safetensors"
)

ANIMA_TURBO_UNET_NAME = os.environ.get("ANIMA_TURBO_UNET_NAME", "anima-turbo-v1.1.safetensors")
ANIMA_TURBO_UNET_URL = os.environ.get(
    "ANIMA_TURBO_UNET_URL",
    "https://huggingface.co/circlestone-labs/Anima/resolve/main/split_files/diffusion_models/anima-turbo-v1.1.safetensors"
)

DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "nova")

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


def get_comfy_available_unets() -> List[str]:
    """Fetch exact list of UNets recognized by ComfyUI's UNETLoader or present on disk."""
    try:
        r = requests.get(f"http://{COMFY_HOST}/object_info/UNETLoader", timeout=2)
        if r.status_code == 200:
            unet_input = r.json().get("UNETLoader", {}).get("input", {}).get("required", {}).get("unet_name", [])
            if unet_input and isinstance(unet_input[0], list) and unet_input[0]:
                return unet_input[0]
    except Exception as exc:
        logger.debug(f"Could not query /object_info/UNETLoader ({exc}), falling back to disk...")

    unet_dir = os.path.join(COMFY_DIR, "models", "diffusion_models")
    if os.path.isdir(unet_dir):
        try:
            files = [f for f in os.listdir(unet_dir) if f.endswith((".safetensors", ".pt", ".bin"))]
            if files:
                return files
        except Exception:
            pass
    return [NOVA_UNET_NAME, SILVERMOON_UNET_NAME]


def resolve_unet_name(requested_name: str, available_unets: Optional[List[str]] = None) -> Tuple[str, bool]:
    """
    Resolve requested UNet name against available UNets in ComfyUI.
    Returns (resolved_unet_filename, is_available).
    If requested_name is not available, falls back safely to an existing UNet
    so ComfyUI NEVER crashes with 'Value not in list' (400 rejection).
    """
    req_clean = str(requested_name).strip()
    if available_unets is None:
        available_unets = get_comfy_available_unets()

    if not available_unets:
        return req_clean or NOVA_UNET_NAME, True

    candidates = [req_clean]
    if not req_clean.endswith(".safetensors") and not req_clean.endswith(".pt"):
        candidates.append(f"{req_clean}.safetensors")
        candidates.append(f"{req_clean}.pt")

    # 1. Exact match
    for cand in candidates:
        if cand in available_unets:
            return cand, True

    # 2. Case-insensitive exact match
    for f in available_unets:
        for cand in candidates:
            if f.lower() == cand.lower():
                return f, True

    # 3. Substring / Stem match
    for cand in candidates:
        cand_stem = cand.replace(".safetensors", "").replace(".pt", "").lower()
        if not cand_stem:
            continue
        for f in available_unets:
            f_stem = f.replace(".safetensors", "").replace(".pt", "").lower()
            if cand_stem in f_stem or f_stem in cand_stem:
                return f, True

    # 4. Keyword matching based on known models
    cand_lower = req_clean.lower()
    if "silver" in cand_lower or "moon" in cand_lower:
        for f in available_unets:
            if "silver" in f.lower():
                return f, True
    if "orange" in cand_lower:
        for f in available_unets:
            if "orange" in f.lower():
                return f, True
    if "nova" in cand_lower or "anime" in cand_lower:
        for f in available_unets:
            if "nova" in f.lower():
                return f, True

    # 5. Safe Fallback: Requested UNet is NOT available!
    fallback = None
    if NOVA_UNET_NAME in available_unets:
        fallback = NOVA_UNET_NAME
    elif SILVERMOON_UNET_NAME in available_unets:
        fallback = SILVERMOON_UNET_NAME
    else:
        fallback = available_unets[0]

    logger.warning(
        f"⚠️ Requested UNet '{requested_name}' is NOT in ComfyUI available models {available_unets}. "
        f"Gracefully falling back to '{fallback}' to prevent 400 prompt rejection."
    )
    return fallback, False


def resolve_clip_name(requested_name: str) -> str:
    """Ensure CLIP name exists in ComfyUI, else fall back safely to default."""
    req_clean = str(requested_name).strip()
    clip_dir = os.path.join(COMFY_DIR, "models", "text_encoders")
    if os.path.isdir(clip_dir):
        available = os.listdir(clip_dir)
        if req_clean in available:
            return req_clean
        for f in available:
            if req_clean.lower() in f.lower() or f.lower() in req_clean.lower():
                return f
        if NOVA_CLIP_NAME in available:
            return NOVA_CLIP_NAME
        if available:
            return available[0]
    return NOVA_CLIP_NAME


def resolve_vae_name(requested_name: str) -> str:
    """Ensure VAE name exists in ComfyUI, else fall back safely to default."""
    req_clean = str(requested_name).strip()
    vae_dir = os.path.join(COMFY_DIR, "models", "vae")
    if os.path.isdir(vae_dir):
        available = os.listdir(vae_dir)
        if req_clean in available:
            return req_clean
        for f in available:
            if req_clean.lower() in f.lower() or f.lower() in req_clean.lower():
                return f
        if NOVA_VAE_NAME in available:
            return NOVA_VAE_NAME
        if available:
            return available[0]
    return NOVA_VAE_NAME


def ensure_model_on_disk(filename: str, url: str) -> bool:
    """
    Ensure the requested UNet model exists on disk.
    If missing, download it on demand via aria2c/curl so user requests NEVER get falsely downgraded.
    """
    try:
        dest_path = os.path.join(COMFY_DIR, "models", "diffusion_models", filename)
        if os.path.isfile(dest_path) and os.path.getsize(dest_path) > 1_000_000_000:
            return True

        logger.info(f"⬇️ Model '{filename}' requested but not found locally. Initiating high-speed on-demand download from {url}...")
        tmp_path = dest_path + ".tmp"
        models_dir = os.path.join(COMFY_DIR, "models", "diffusion_models")
        os.makedirs(models_dir, exist_ok=True)
    except Exception as exc:
        logger.warning(f"Could not prepare destination directory for '{filename}': {exc}")
        return False

    # 1. High-speed multi-connection aria2c download
    try:
        cmd = [
            "aria2c", "-c", "-x", "16", "-s", "16", "-k", "1M",
            "--file-allocation=none",
            f"--dir={models_dir}",
            f"--out={filename}.tmp",
            url
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        if res.returncode == 0 and os.path.isfile(tmp_path):
            os.replace(tmp_path, dest_path)
            logger.info(f"✅ Successfully downloaded '{filename}' ({os.path.getsize(dest_path)} bytes) via aria2c!")
            return True
        else:
            logger.warning(f"aria2c download failed (code {res.returncode}): {res.stderr.decode('utf-8', errors='ignore')[:300]}")
    except Exception as exc:
        logger.warning(f"aria2c execution error: {exc}, attempting curl fallback...")

    # 2. Curl fallback
    try:
        cmd = ["curl", "-L", "-s", "--retry", "3", "--connect-timeout", "30", "-o", tmp_path, url]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        if res.returncode == 0 and os.path.isfile(tmp_path):
            os.replace(tmp_path, dest_path)
            logger.info(f"✅ Successfully downloaded '{filename}' via curl ({os.path.getsize(dest_path)} bytes)!")
            return True
    except Exception as exc:
        logger.error(f"❌ Failed to download '{filename}': {exc}")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    return False


def save_reference_image(raw_image_input: str, target_width: int = 768, target_height: int = 1024) -> Tuple[Optional[str], int, int]:
    """
    Accepts image as URL, base64 data string, or existing filepath.
    Resizes it cleanly to multiples of 16 to avoid VAE/UNet shape mismatch,
    saves into ComfyUI's input directory, and returns (filename, width, height).
    """
    if not raw_image_input or not isinstance(raw_image_input, str):
        return None, target_width, target_height

    raw_clean = raw_image_input.strip()
    image_bytes = None

    try:
        if raw_clean.startswith("http://") or raw_clean.startswith("https://"):
            logger.info(f"⬇️ Downloading reference image from URL: {raw_clean[:60]}...")
            resp = requests.get(raw_clean, timeout=20)
            if resp.status_code == 200:
                image_bytes = resp.content
            else:
                logger.warning(f"Failed to download image from URL (HTTP {resp.status_code})")
                return None, target_width, target_height
        elif raw_clean.startswith("data:image") or len(raw_clean) > 200:
            if "base64," in raw_clean:
                raw_clean = raw_clean.split("base64,")[1]
            image_bytes = base64.b64decode(raw_clean)
        elif os.path.isfile(raw_clean):
            with open(raw_clean, "rb") as f:
                image_bytes = f.read()
    except Exception as exc:
        logger.error(f"❌ Failed to parse reference image: {exc}")
        return None, target_width, target_height

    if not image_bytes:
        return None, target_width, target_height

    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")

        w, h = img.size
        # Maintain aspect ratio, cap largest dimension at 1024, ensure divisible by 16
        scale = min(1024 / max(w, h), 1.0)
        new_w = max(256, int(round((w * scale) / 16.0)) * 16)
        new_h = max(256, int(round((h * scale) / 16.0)) * 16)

        if (new_w, new_h) != (w, h):
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        filename = f"ref_{int(time.time())}_{uuid.uuid4().hex[:8]}.png"
        input_dir = os.path.join(COMFY_DIR, "input")
        try:
            os.makedirs(input_dir, exist_ok=True)
        except Exception:
            input_dir = "/tmp"

        dest_path = os.path.join(input_dir, filename)
        img.save(dest_path, format="PNG")
        logger.info(f"✅ Reference image saved: {dest_path} ({new_w}x{new_h})")
        return filename, new_w, new_h
    except Exception as exc:
        logger.error(f"❌ Failed to process and save reference image: {exc}")
        return None, target_width, target_height


# Allowed samplers & schedulers in ComfyUI KSampler (Guards against invalid inputs)
VALID_SAMPLERS = {
    "euler", "euler_ancestral", "heun", "heunpp2", "dpm_2", "dpm_2_ancestral",
    "lms", "dpm_fast", "dpm_adaptive", "dpmpp_2s_ancestral", "dpmpp_sde",
    "dpmpp_sde_gpu", "dpmpp_2m", "dpmpp_2m_sde", "dpmpp_2m_sde_gpu",
    "dpmpp_3m_sde", "dpmpp_3m_sde_gpu", "ddpm", "lcm", "ddim", "uni_pc",
    "uni_pc_bh2", "er_sde"
}

VALID_SCHEDULERS = {
    "normal", "karras", "exponential", "sgm_uniform", "simple", "ddim_uniform", "beta"
}

# Default quality tags (Tuned specifically for Pure 2D Anime, Anti-Slop, Natural Anatomy & Rich Scenery)
NOVA_QUALITY_BOOSTER = (
    "masterpiece, best quality, score_9, score_8, score_7, year 2025, newest, absurdres, highres, "
    "2d, clean lineart, sharp defined outlines, cel shading, flat color, "
    "accurate anatomy, natural body curves, well-proportioned limbs, "
    "distinct hair clumps, expressive anime eyes, lively expression, delicate facial features, "
    "vibrant anime coloring, detailed scenery, beautiful background, scenic environment, "
    "atmospheric lighting, digital illustration"
)

ORANGE_QUALITY_BOOSTER = (
    "masterpiece, best quality, score_9, score_8, year 2025, very aesthetic, newest, absurdres, highres, "
    "2d, digital illustration, clean lineart, accurate anatomy, natural body curves, well-proportioned limbs, "
    "expressive facial features, beautiful eyes, vibrant colors, detailed scenery, scenic background, harmonious composition"
)

SILVERMOON_QUALITY_BOOSTER = (
    "masterpiece, best quality, score_9, score_8, year 2025, very aesthetic, newest, absurdres, highres, "
    "2d, flat color, clean lineart, delicate brushwork, accurate hands, finely detailed fingers, "
    "accurate anatomy, natural body curves, well-proportioned limbs, "
    "expressive eyes, delicate facial features, harmonious colors, detailed scenery, beautiful atmospheric background, detailed digital illustration"
)

NEGATIVE_DEFAULT = (
    # 1. Quality & Artifacts
    "worst quality, low quality, early, old, score_1, score_2, score_3, score_4, score_5, score_6, "
    "monochrome, jpeg artifacts, lowres, blurry, watermark, signature, username, error, text, logo, "
    # 2. Anti-3D / Anti-2.5D / Anti-Airbrush / Anti-Slop Shading (Grease & Plastic Vinyl Skin)
    "2.5d, 3d, realistic, photorealistic, semi-realistic, cg, cgi, 3d render, unreal engine, octane render, "
    "airbrush, smooth shading, soft gradients, volumetric lighting, raytracing, ambient occlusion, flat 3d shading, muddy colors, "
    "plastic skin, shiny skin, oily skin, greasy skin, porcelain skin, doll face, mannequin, glossy plastic, 3d model, "
    # 3. Anti-Anatomical Slop, Unnatural Curves & Mutations
    "bad anatomy, bad proportions, gross proportions, deformed, disfigured, unnatural spine, awkward pose, rubber limbs, stiff pose, "
    "bad hands, poorly drawn hands, mutated hands, missing fingers, extra digits, extra fingers, fewer digits, "
    "fused fingers, elongated fingers, long fingers, malformed fingers, crooked fingers, jointless limbs, "
    "malformed limbs, extra limbs, missing limbs, floating limbs, "
    # 4. Anti-Hair & Eye Slop (Dead Glass Eyes & Spaghetti Hair)
    "glassy eyes, dead eyes, over-detailed eyes, chaotic pupil, pupil deformity, "
    "floating hair strands, hair spaghetti, messy hair, melted hair, hair melting into clothing, "
    # 5. Anti-Greeble & Compositional Noise (NO background-bleeding penalty so scenery renders freely)
    "floating straps, disconnected belts, random greebles, melting clothes, clothing merging with skin, "
    "excessive bokeh, floating particles, visual noise, "
    # 6. Lighting Slop
    "washed out, dull lighting, oversaturated, amateur, overexposed, blown out highlights, glaring light, glowing glare"
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

    model_choice = str(inputs.get("model", DEFAULT_MODEL)).strip().lower()
    raw_unet_req = inputs.get("unet_name", "")
    target_url = ""

    # Determine desired UNet target, download URL, and display name
    if "silvermoon" in model_choice or "silver" in model_choice or "moon" in model_choice:
        target_unet = raw_unet_req or SILVERMOON_UNET_NAME
        target_url = SILVERMOON_UNET_URL
        active_model_name = "SilvermoonMix Anima Evolved (2.9B)"
        quality_booster = SILVERMOON_QUALITY_BOOSTER
    elif "base" in model_choice or "circlestone" in model_choice or "anima_base" in model_choice:
        target_unet = raw_unet_req or ANIMA_BASE_UNET_NAME
        target_url = ANIMA_BASE_UNET_URL
        active_model_name = "CircleStone Anima Base v1.0 (2.9B DiT)"
        quality_booster = NOVA_QUALITY_BOOSTER
    elif "anima_turbo" in model_choice:
        target_unet = raw_unet_req or ANIMA_TURBO_UNET_NAME
        target_url = ANIMA_TURBO_UNET_URL
        active_model_name = "CircleStone Anima Turbo v1.1 (2.9B DiT)"
        quality_booster = NOVA_QUALITY_BOOSTER
    elif "orange" in model_choice or "2.5d" in model_choice:
        target_unet = raw_unet_req or ORANGE_UNET_NAME
        target_url = ORANGE_UNET_URL
        active_model_name = "Nova Orange AM (2.9B)"
        quality_booster = ORANGE_QUALITY_BOOSTER
    elif "nova" in model_choice or "anime" in model_choice:
        target_unet = raw_unet_req or NOVA_UNET_NAME
        target_url = NOVA_UNET_URL
        active_model_name = "Nova Anime AM v6.0 (2.9B)"
        quality_booster = NOVA_QUALITY_BOOSTER
    else:
        # Default fallback to NOVA_UNET_NAME (Nova Anime AM v6.0 Flagship)
        target_unet = raw_unet_req or NOVA_UNET_NAME
        target_url = NOVA_UNET_URL
        active_model_name = "Nova Anime AM v6.0 (2.9B)"
        quality_booster = NOVA_QUALITY_BOOSTER

    # Resolve against actual models available in ComfyUI
    available_unets = get_comfy_available_unets()
    logger.info(f"🔎 Available UNets recognized by ComfyUI: {available_unets}")

    # Check if target model is already available in ComfyUI
    target_in_available = any(
        target_unet.lower() == f.lower() or target_unet.replace(".safetensors", "").lower() in f.lower()
        for f in available_unets
    )

    # Only trigger on-demand download if model is truly missing
    if not target_in_available and target_url:
        logger.info(f"⚡ Target model '{target_unet}' missing locally. Triggering on-demand download...")
        downloaded = ensure_model_on_disk(target_unet, target_url)
        if downloaded:
            # Refresh ComfyUI model cache
            try:
                requests.post(f"http://{COMFY_HOST}/free", json={"unload_models": False, "free_memory": False}, timeout=2)
            except Exception:
                pass
            available_unets = get_comfy_available_unets()

    selected_unet, is_available = resolve_unet_name(target_unet, available_unets)

    if not is_available:
        # Only in the worst-case scenario where download failed completely
        if "silver" in selected_unet.lower():
            active_model_name = f"SilvermoonMix Anima Evolved (2.9B) [Auto-fallback from {target_unet}]"
            quality_booster = SILVERMOON_QUALITY_BOOSTER
        else:
            active_model_name = f"Nova Anime AM v6.0 (2.9B) [Auto-fallback from {target_unet}]"
            quality_booster = NOVA_QUALITY_BOOSTER

    seed = int(inputs.get("seed", -1))
    if seed <= 0:
        seed = random.randint(1_000_000_000_000_000, 9_999_999_999_999_999)

    custom_negative = inputs.get("negative_prompt", "").strip()

    with open(WORKFLOW_ANIMA_PATH, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    # ─── Curated Presets with Dedicated 2D Boosters & Clean LoRA Stacks ────────
    preset = str(inputs.get("preset", "")).strip().lower()
    use_turbo = bool(inputs.get("turbo", False) or inputs.get("anima_turbo", False))
    lora_list = []
    preset_cfg = None

    if preset in ("pure_2d", "flat_anime", "cel_shading", "flat_2d"):
        quality_booster = (
            "masterpiece, best quality, score_9, score_8, year 2025, 2d, pure 2d, flat color, flat shading, cel shading, "
            "anime screencap, sharp clean lineart, bold ink outlines, traditional anime drawing, zero gradients, vibrant colors, clean edges, "
            "accurate anatomy, natural body curves, detailed scenery, beautiful scenic background"
        )
        lora_list.append({"name": "Anima_Turbo_v1.1.safetensors", "strength": 0.90})
        lora_list.append({"name": "sharp_lineart", "strength": 0.50, "strength_model": 0.50, "strength_clip": 0.60})
        lora_list.append({"name": "anatomy_fix", "strength": 0.50, "strength_model": 0.45, "strength_clip": 0.55})
        preset_cfg = 1.20
    elif preset in ("digital_art", "master_illustrator", "artist", "illustrator", "clean_anime"):
        # The SOTA Digital Artist recipe: Turbo + Mild Aesthetic Boost + Anatomy Fix + Cloth/Hair Detailer
        quality_booster = (
            "masterpiece, best quality, score_9, score_8, very aesthetic, year 2025, newest, 2d, digital illustration, "
            "Japanese artist style, clean lineart, cel shading, crisp outlines, vibrant anime coloring, "
            "accurate anatomy, natural body curves, well-proportioned limbs, expressive eyes, defined hair clumps, delicate facial features, "
            "professional artwork, detailed scenery, beautiful background, atmospheric lighting"
        )
        lora_list.append({"name": "Anima_Turbo_v1.1.safetensors", "strength": 0.90})
        lora_list.append({"name": "aesthetic_boost", "strength": 0.45, "strength_model": 0.40, "strength_clip": 0.50})
        lora_list.append({"name": "anatomy_fix", "strength": 0.55, "strength_model": 0.50, "strength_clip": 0.60})
        lora_list.append({"name": "cloth_and_hair_detailer", "strength": 0.40, "strength_model": 0.35, "strength_clip": 0.45})
        preset_cfg = 1.25
    elif preset in ("sketch", "hand_drawn_sketch", "rough_sketch", "pencil_sketch"):
        # Authentic Hand-Drawn Sketch / Pro Draft (Yamimatsu7)
        quality_booster = (
            "masterpiece, score_9, score_8, sketch, graphite sketch, pencil drawing, ink draft, "
            "clean thin lineart, traditional media, paper texture, cross-hatching, monochrome, "
            "illustrator rough draft, dynamic lines, accurate anatomy, natural body curves"
        )
        lora_list.append({"name": "Anima_Turbo_v1.1.safetensors", "strength": 0.85})
        lora_list.append({"name": "sketch_style", "strength": 0.85, "strength_model": 0.85, "strength_clip": 0.80})
        lora_list.append({"name": "anatomy_fix", "strength": 0.45, "strength_model": 0.40, "strength_clip": 0.50})
        preset_cfg = 1.20
    elif preset in ("character_focus", "strong_character", "character"):
        # Maximum Character Recognition & Costume Fidelity (RL Prompt Alignment)
        quality_booster = (
            "masterpiece, best quality, score_9, score_8, very aesthetic, year 2025, newest, 2d, character focus, "
            "official character art, accurate costume details, crisp lineart, cel shading, vibrant anime coloring, "
            "accurate anatomy, natural body curves, well-proportioned limbs, expressive face, sharp focal clarity, "
            "detailed scenery, scenic background"
        )
        lora_list.append({"name": "Anima_Turbo_v1.1.safetensors", "strength": 0.90})
        lora_list.append({"name": "anatomy_fix", "strength": 0.70, "strength_model": 0.65, "strength_clip": 0.75})
        lora_list.append({"name": "cloth_and_hair_detailer", "strength": 0.40, "strength_model": 0.35, "strength_clip": 0.45})
        preset_cfg = 1.25
    elif preset in ("watercolor_classic", "sugimori", "classic_art", "watercolor"):
        # Classic 90s Hand-Drawn Watercolor (Sugimori Style)
        quality_booster = (
            "masterpiece, score_9, score_8, ken sugimori (style), watercolor (medium), "
            "hand-drawn illustration, soft watercolor wash, delicate ink lines, paper texture, "
            "traditional media, vintage official art, accurate anatomy, natural body curves, detailed scenery, scenic background"
        )
        lora_list.append({"name": "Anima_Turbo_v1.1.safetensors", "strength": 0.85})
        lora_list.append({"name": "watercolor_artist", "strength": 0.85, "strength_model": 0.80, "strength_clip": 0.85})
        lora_list.append({"name": "anatomy_fix", "strength": 0.45, "strength_model": 0.40, "strength_clip": 0.50})
        preset_cfg = 1.20
    elif preset in ("modern_anime", "pixiv", "noobai"):
        # Modern Danbooru Vibrant Art (Pixiv / Twitter Style)
        quality_booster = (
            "masterpiece, best quality, score_9, score_8, year 2025, newest, 2d, pixiv, digital illustration, "
            "cel shading, vibrant pop colors, crisp lineart, trending on pixiv, flat anime color, "
            "accurate anatomy, natural body curves, detailed scenery, beautiful background, atmospheric lighting, modern anime artwork"
        )
        lora_list.append({"name": "Anima_Turbo_v1.1.safetensors", "strength": 0.90})
        lora_list.append({"name": "noobai_style", "strength": 0.75, "strength_model": 0.70, "strength_clip": 0.80})
        lora_list.append({"name": "anatomy_fix", "strength": 0.50, "strength_model": 0.45, "strength_clip": 0.55})
        preset_cfg = 1.25
    elif preset in ("dynamic_action", "battle_pose", "action"):
        # Dynamic Combat & Martial Arts Fighting Poses
        quality_booster = (
            "masterpiece, best quality, score_9, score_8, 2d, dynamic action pose, fighting stance, "
            "motion lines, perspective foreshortening, crisp ink lineart, cel shading, intense energetic composition, "
            "accurate anatomy, natural body curves, dynamic anatomy, dynamic background, cinematic battlefield, scenic environment"
        )
        lora_list.append({"name": "Anima_Turbo_v1.1.safetensors", "strength": 0.90})
        lora_list.append({"name": "dynamic_action", "strength": 0.75, "strength_model": 0.70, "strength_clip": 0.80})
        lora_list.append({"name": "anatomy_fix", "strength": 0.60, "strength_model": 0.55, "strength_clip": 0.65})
        preset_cfg = 1.25
    elif preset in ("retro_90s", "retro", "vintage"):
        # Retro 90s Vintage Cel Animation (Sailor Moon style)
        quality_booster = (
            "masterpiece, score_9, score_8, 1990s (style), vintage anime, retro anime cel, "
            "anime screencap, flat color, clean lineart, traditional cel animation, "
            "nostalgic 90s TV anime palette, scanlines, accurate anatomy, natural body curves, vintage anime scenery, scenic background"
        )
        lora_list.append({"name": "Anima_Turbo_v1.1.safetensors", "strength": 0.85})
        lora_list.append({"name": "retro_90s", "strength": 0.80, "strength_model": 0.75, "strength_clip": 0.85})
        lora_list.append({"name": "anatomy_fix", "strength": 0.45, "strength_model": 0.40, "strength_clip": 0.50})
        preset_cfg = 1.20
    elif preset in ("painterly", "fantasy", "cinematic"):
        # Painterly Concept Art & Brushwork
        quality_booster = (
            "masterpiece, score_9, score_8, very aesthetic, painterly illustration, visible brush strokes, "
            "traditional art media, expressive colors, artistic composition, "
            "accurate anatomy, natural body curves, detailed scenery, beautiful atmospheric landscape, scenic environment"
        )
        lora_list.append({"name": "Anima_Turbo_v1.1.safetensors", "strength": 0.90})
        lora_list.append({"name": "fantasy_art", "strength": 0.60, "strength_model": 0.55, "strength_clip": 0.65})
        lora_list.append({"name": "anatomy_fix", "strength": 0.50, "strength_model": 0.45, "strength_clip": 0.55})
        preset_cfg = 1.30
    elif use_turbo:
        lora_list.append({
            "name": TURBO_LORA_NAME,
            "strength": float(inputs.get("turbo_strength", 1.0)),
        })

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

    if user_wants_plain_bg:
        for bg_tag in (
            "detailed scenery", "beautiful background", "scenic environment",
            "atmospheric lighting", "scenic background", "dynamic background",
            "cinematic battlefield", "vintage anime scenery", "beautiful atmospheric landscape"
        ):
            quality_booster = quality_booster.replace(f", {bg_tag}", "").replace(f"{bg_tag}, ", "").replace(bg_tag, "")

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
        default_scheduler = "simple"
    elif has_turbo_active:
        default_steps = 10
        if preset_cfg is not None:
            default_cfg = preset_cfg
        else:
            default_cfg = 1.25
        default_sampler = "er_sde"
        default_scheduler = "simple"
    else:
        default_steps = 20
        default_cfg = 3.5
        default_sampler = "er_sde"
        default_scheduler = "simple"

    width = int(inputs.get("width", 768))
    height = int(inputs.get("height", 1024))
    width = max(256, min(2048, (width // 16) * 16))
    height = max(256, min(2048, (height // 16) * 16))

    steps = int(inputs.get("steps", default_steps))
    steps = min(35, max(4, steps))
    cfg = float(inputs.get("cfg", default_cfg))

    sampler = str(inputs.get("sampler", default_sampler)).strip().lower()
    if sampler not in VALID_SAMPLERS:
        logger.warning(f"⚠️ Sampler '{sampler}' not recognized. Falling back to '{default_sampler}'.")
        sampler = default_sampler

    scheduler = str(inputs.get("scheduler", default_scheduler)).strip().lower()
    if scheduler not in VALID_SCHEDULERS:
        logger.warning(f"⚠️ Scheduler '{scheduler}' not recognized. Falling back to '{default_scheduler}'.")
        scheduler = default_scheduler

    resolved_clip = resolve_clip_name(inputs.get("clip_name", NOVA_CLIP_NAME))
    resolved_vae = resolve_vae_name(inputs.get("vae_name", NOVA_VAE_NAME))

    ref_image = inputs.get("image") or inputs.get("image_url") or inputs.get("input_image")
    denoise = float(inputs.get("denoise", 0.65 if ref_image else 1.0))
    denoise = max(0.05, min(1.0, denoise))

    saved_ref_filename = None
    if ref_image:
        saved_ref_filename, img_w, img_h = save_reference_image(ref_image, width, height)
        if saved_ref_filename:
            width, height = img_w, img_h

    workflow["1"]["inputs"]["unet_name"] = selected_unet
    workflow["2"]["inputs"]["clip_name"] = resolved_clip
    workflow["3"]["inputs"]["vae_name"] = resolved_vae
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

    if saved_ref_filename:
        # Img2Img path: LoadImage -> VAEEncode -> KSampler (Node 7)
        workflow["10"] = {
            "inputs": {
                "image": saved_ref_filename
            },
            "class_type": "LoadImage",
            "_meta": {
                "title": f"Load Reference Image ({saved_ref_filename})"
            }
        }
        workflow["11"] = {
            "inputs": {
                "pixels": ["10", 0],
                "vae": ["3", 0]
            },
            "class_type": "VAEEncode",
            "_meta": {
                "title": "VAE Encode (Reference Image)"
            }
        }
        workflow["7"]["inputs"]["latent_image"] = ["11", 0]
        workflow["7"]["inputs"]["denoise"] = denoise
    else:
        # Txt2Img path: EmptyLatentImage (Node 6) -> KSampler (Node 7)
        workflow["7"]["inputs"]["latent_image"] = ["6", 0]
        workflow["7"]["inputs"]["denoise"] = 1.0

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

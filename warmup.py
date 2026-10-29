#!/usr/bin/env python3
"""
warmup.py — VRAM Pre-warming script for ComfyUI Serverless Worker

Executes a 1-step minimal latent inference during container boot so that:
  1. The diffusion model (Nova Anime AM), Qwen text encoder, and VAE
     are fully loaded into GPU VRAM before the worker begins accepting user jobs.
  2. The first user request experiences ZERO seconds model-loading latency!
"""

import json
import logging
import os
import pathlib
import sys
import time
import requests
import websocket

logging.basicConfig(level=logging.INFO, format="%(asctime)s [warmup] %(message)s")
logger = logging.getLogger("warmup")

COMFY_HOST = os.environ.get("COMFY_HOST", "127.0.0.1:8188")
COMFY_DIR = os.environ.get("COMFY_DIR", "/app/ComfyUI")
WORKFLOW_NOVA_PATH = "/app/workflow_nova.json"


def prewarm_comfyui() -> bool:
    if not os.path.exists(WORKFLOW_NOVA_PATH):
        logger.warning(f"Workflow template {WORKFLOW_NOVA_PATH} not found. Skipping warmup.")
        return False

    try:
        with open(WORKFLOW_NOVA_PATH, "r", encoding="utf-8") as f:
            workflow = json.load(f)

        # Make the warmup ultra-fast: 1 step, tiny 256x256 resolution
        # This loads all model layers into VRAM without wasting computation
        if "6" in workflow and "inputs" in workflow["6"]:
            workflow["6"]["inputs"]["width"] = 256
            workflow["6"]["inputs"]["height"] = 256
        if "7" in workflow and "inputs" in workflow["7"]:
            workflow["7"]["inputs"]["steps"] = 1
            workflow["7"]["inputs"]["cfg"] = 1.0

        client_id = "warmup_client"
        ws_url = f"ws://{COMFY_HOST}/ws?clientId={client_id}"

        logger.info("🔥 Pre-warming models into GPU VRAM (1-step warmup)...")
        ws = websocket.create_connection(ws_url, timeout=45)

        res = requests.post(
            f"http://{COMFY_HOST}/prompt",
            json={"prompt": workflow, "client_id": client_id},
            timeout=20,
        )
        if res.status_code != 200:
            logger.warning(f"Warmup prompt submission failed ({res.status_code}): {res.text}")
            ws.close()
            return False

        prompt_id = res.json().get("prompt_id")

        while True:
            raw_msg = ws.recv()
            if not isinstance(raw_msg, str):
                continue
            msg = json.loads(raw_msg)
            msg_type = msg.get("type")

            if msg_type == "executing":
                data = msg.get("data", {})
                if data.get("node") is None and data.get("prompt_id") == prompt_id:
                    break
            elif msg_type == "execution_error":
                logger.warning(f"Warmup execution encountered an issue: {msg}")
                break

        ws.close()

        # Clean up any warmup output file
        output_dir = pathlib.Path(COMFY_DIR) / "output"
        for p in output_dir.glob("ComfyUI_NovaAnime*"):
            try:
                p.unlink()
            except Exception:
                pass

        logger.info("✨ GPU VRAM Pre-warming complete! Model is hot and ready for sub-second start!")
        return True

    except Exception as exc:
        logger.warning(f"Warmup error (non-fatal, worker will still function): {exc}")
        return False


if __name__ == "__main__":
    prewarm_comfyui()

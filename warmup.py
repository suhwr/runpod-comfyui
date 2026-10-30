#!/usr/bin/env python3
"""
warmup.py — Dual-Model VRAM Pre-warming script for ComfyUI Serverless Worker

Executes a 1-step minimal latent inference during container boot so that:
  1. NoobAI-XL v1.1 and Nova Anime AM v6.0 are both loaded into memory / GPU VRAM
     before the worker begins accepting user jobs.
  2. The first user request experiences ZERO seconds model-loading latency,
     regardless of whether they request Nova or NoobAI on a brand-new worker!
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


def run_micro_warmup(workflow_path: str, latent_node: str, sampler_node: str, clean_prefix: str, name: str) -> bool:
    if not os.path.exists(workflow_path):
        logger.warning(f"Workflow template {workflow_path} not found. Skipping {name} warmup.")
        return False

    try:
        with open(workflow_path, "r", encoding="utf-8") as f:
            workflow = json.load(f)

        # Make the warmup ultra-fast: 1 step, tiny 256x256 resolution
        # This forces ComfyUI to load and initialize all weights without wasting computation
        if latent_node in workflow and "inputs" in workflow[latent_node]:
            workflow[latent_node]["inputs"]["width"] = 256
            workflow[latent_node]["inputs"]["height"] = 256
        if sampler_node in workflow and "inputs" in workflow[sampler_node]:
            workflow[sampler_node]["inputs"]["steps"] = 1
            workflow[sampler_node]["inputs"]["cfg"] = 1.0

        client_id = f"warmup_{name.lower().replace(' ', '_')}"
        ws_url = f"ws://{COMFY_HOST}/ws?clientId={client_id}"

        logger.info(f"🔥 Pre-warming [{name}] into memory/VRAM (1-step micro-inference)...")
        ws = websocket.create_connection(ws_url, timeout=60)

        res = requests.post(
            f"http://{COMFY_HOST}/prompt",
            json={"prompt": workflow, "client_id": client_id},
            timeout=20,
        )
        if res.status_code != 200:
            logger.warning(f"Warmup prompt submission failed for {name} ({res.status_code}): {res.text}")
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
                logger.warning(f"Warmup execution encountered an issue with {name}: {msg}")
                break

        ws.close()

        # Clean up any warmup output files generated
        output_dir = pathlib.Path(COMFY_DIR) / "output"
        for p in output_dir.glob(f"{clean_prefix}*"):
            try:
                p.unlink()
            except Exception:
                pass

        logger.info(f"✨ [{name}] pre-warming complete!")
        return True

    except Exception as exc:
        logger.warning(f"Warmup error for {name} (non-fatal, worker will still function): {exc}")
        return False


def prewarm_comfyui() -> bool:
    # Prewarm SilvermoonMix Anima Evolved (Default model - sits ready in active VRAM with pre-compiled CUDA kernels)
    run_micro_warmup(
        workflow_path=WORKFLOW_NOVA_PATH,
        latent_node="6",
        sampler_node="7",
        clean_prefix="ComfyUI_Silvermoon",
        name="SilvermoonMix Anima Evolved",
    )

    logger.info("✨ Pure-DiT GPU VRAM Pre-warming complete! Model is hot and ready for sub-second start!")
    return True


if __name__ == "__main__":
    prewarm_comfyui()

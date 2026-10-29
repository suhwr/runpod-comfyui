# ==============================================================================
# Ultra-Optimized ComfyUI Anime Serverless Worker
# Architecture: ComfyUI Headless Engine + SDXL (NoobAI-XL) + Hyper-SD 8-Step LoRA
# ==============================================================================
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_PREFER_BINARY=1 \
    CC=/usr/bin/gcc \
    COMFY_DIR=/app/ComfyUI \
    COMFY_HOST=127.0.0.1:8188 \
    NOVA_UNET_NAME=novaAnimeAM_v6029B.safetensors \
    NOVA_UNET_URL=https://huggingface.co/mogaru99/novaAnimeAM_v6029B/resolve/main/novaAnimeAM_v6029B.safetensors \
    NOVA_CLIP_NAME=qwen_3_06b_base.safetensors \
    NOVA_CLIP_URL=https://huggingface.co/circlestone-labs/Anima/resolve/main/split_files/text_encoders/qwen_3_06b_base.safetensors \
    NOVA_VAE_NAME=qwen_image_vae.safetensors \
    NOVA_VAE_URL=https://huggingface.co/circlestone-labs/Anima/resolve/main/split_files/vae/qwen_image_vae.safetensors \
    NOOBAI_CKPT_NAME=NoobAI-XL-v1.1.safetensors \
    NOOBAI_CKPT_URL=https://huggingface.co/Laxhar/noobai-XL-1.1/resolve/main/NoobAI-XL-v1.1.safetensors

# 1. System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    build-essential \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    aria2 \
    curl \
    git \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set Python 3.11 as default python
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11 \
    && python3 -m pip install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /app

# 2. Install PyTorch 2.7.0 with CUDA 12.4
# comfy-kitchen (required by ComfyUI) officially requires PyTorch >= 2.7.0
# for torch.library.infer_schema support of built-in generic types (list[int], etc.)
RUN python3 -m pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cu124 \
    --extra-index-url https://pypi.org/simple \
    torch==2.7.0 torchvision==0.22.0 torchaudio==2.7.0

# 3. Clone ComfyUI repository & install dependencies
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI \
    && python3 -m pip install --no-cache-dir -r /app/ComfyUI/requirements.txt

# 4. Install worker-specific requirements
COPY requirements.txt /app/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /app/requirements.txt

# 5. Prepare folders
RUN mkdir -p /app/ComfyUI/models/checkpoints \
             /app/ComfyUI/models/diffusion_models \
             /app/ComfyUI/models/text_encoders \
             /app/ComfyUI/models/vae \
             /app/ComfyUI/output

# 6. Copy handler, workflows, and startup script
COPY workflow_nova.json /app/workflow_nova.json
COPY workflow_noobai.json /app/workflow_noobai.json
COPY handler.py /app/handler.py
COPY warmup.py /app/warmup.py
COPY start.sh /app/start.sh
COPY setup_volume.sh /app/setup_volume.sh
COPY README.md /app/README.md

RUN chmod +x /app/start.sh /app/setup_volume.sh /app/warmup.py

CMD ["/app/start.sh"]

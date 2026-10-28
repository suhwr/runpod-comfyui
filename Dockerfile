# ==============================================================================
# Ultra-Optimized ComfyUI Anime Serverless Worker
# Architecture: ComfyUI Headless Engine + SDXL (NoobAI-XL) + Hyper-SD 8-Step LoRA
# ==============================================================================
FROM nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_PREFER_BINARY=1 \
    COMFY_DIR=/app/ComfyUI \
    COMFY_HOST=127.0.0.1:8188 \
    CHECKPOINT_NAME=NoobAI-XL-v1.1.safetensors \
    CHECKPOINT_URL=https://huggingface.co/Laxhar/noobai-XL-1.1/resolve/main/NoobAI-XL-v1.1.safetensors \
    LORA_NAME=Hyper-SDXL-8steps-CFG-lora.safetensors \
    LORA_URL=https://huggingface.co/ByteDance/Hyper-SD/resolve/main/Hyper-SDXL-8steps-CFG-lora.safetensors

# 1. System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    build-essential \
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

# 2. Install PyTorch with CUDA 12.4
RUN python3 -m pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cu124 \
    --extra-index-url https://pypi.org/simple \
    torch==2.4.1 torchvision==0.19.1 torchaudio==2.4.1

# 3. Clone ComfyUI repository & install dependencies
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI \
    && python3 -m pip install --no-cache-dir -r /app/ComfyUI/requirements.txt

# 4. Install worker-specific requirements
COPY requirements.txt /app/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /app/requirements.txt

# 5. Prepare folders & pre-download Hyper-SD 8-step LoRA (~400MB)
RUN mkdir -p /app/ComfyUI/models/checkpoints \
             /app/ComfyUI/models/loras \
             /app/ComfyUI/models/vae \
             /app/ComfyUI/output \
    && curl -L --retry 3 --connect-timeout 30 -o /app/ComfyUI/models/loras/Hyper-SDXL-8steps-CFG-lora.safetensors \
       https://huggingface.co/ByteDance/Hyper-SD/resolve/main/Hyper-SDXL-8steps-CFG-lora.safetensors

# 6. Copy handler, default anime workflow, and startup script
COPY workflow_anime.json /app/workflow_anime.json
COPY handler.py /app/handler.py
COPY start.sh /app/start.sh
COPY README.md /app/README.md

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]

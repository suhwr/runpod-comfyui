# ==============================================================================
# Ultra-Optimized ComfyUI Anime Serverless Worker
# Architecture: ComfyUI Headless Engine + Dual-Model (Nova Anime AM + NoobAI-XL)
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

# 5. Prepare model folders
RUN mkdir -p /app/ComfyUI/models/checkpoints \
             /app/ComfyUI/models/diffusion_models \
             /app/ComfyUI/models/text_encoders \
             /app/ComfyUI/models/vae \
             /app/ComfyUI/output

# 6. Bake models directly into the Docker image during build
#    Eliminates runtime download latency completely across all GPU server rollings!
# 6a. Nova Anime AM v6.0 UNet (~5.5 GB)
RUN aria2c -c -x 16 -s 16 -k 1M --file-allocation=none \
    --dir=/app/ComfyUI/models/diffusion_models --out=novaAnimeAM_v6029B.safetensors \
    https://huggingface.co/mogaru99/novaAnimeAM_v6029B/resolve/main/novaAnimeAM_v6029B.safetensors

# 6b. Qwen Text Encoder (~1.1 GB) & Qwen VAE (~240 MB)
RUN aria2c -c -x 8 -s 8 -k 1M --file-allocation=none \
    --dir=/app/ComfyUI/models/text_encoders --out=qwen_3_06b_base.safetensors \
    https://huggingface.co/circlestone-labs/Anima/resolve/main/split_files/text_encoders/qwen_3_06b_base.safetensors \
 && aria2c -c -x 8 -s 8 -k 1M --file-allocation=none \
    --dir=/app/ComfyUI/models/vae --out=qwen_image_vae.safetensors \
    https://huggingface.co/circlestone-labs/Anima/resolve/main/split_files/vae/qwen_image_vae.safetensors

# 6c. NoobAI-XL v1.1 Checkpoint (~7.1 GB)
RUN aria2c -c -x 16 -s 16 -k 1M --file-allocation=none \
    --dir=/app/ComfyUI/models/checkpoints --out=NoobAI-XL-v1.1.safetensors \
    https://huggingface.co/Laxhar/noobai-XL-1.1/resolve/main/NoobAI-XL-v1.1.safetensors

# 7. Copy handler, workflows, and startup script
COPY workflow_nova.json /app/workflow_nova.json
COPY workflow_noobai.json /app/workflow_noobai.json
COPY handler.py /app/handler.py
COPY warmup.py /app/warmup.py
COPY start.sh /app/start.sh
COPY setup_volume.sh /app/setup_volume.sh
COPY README.md /app/README.md

RUN chmod +x /app/start.sh /app/setup_volume.sh /app/warmup.py

CMD ["/app/start.sh"]

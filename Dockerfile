# ==============================================================================
# Ultra-Optimized ComfyUI Anime Serverless Worker
# Architecture: ComfyUI Headless Engine + Pure-DiT Anima (Nova Anime v6.0 + SilvermoonMix)
# Universal GPU Support: Turing (7.5) -> Ampere (8.0/8.6) -> Ada (8.9) -> Hopper (9.0) -> Blackwell (10.0/12.0)
# ==============================================================================
FROM nvidia/cuda:12.8.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_PREFER_BINARY=1 \
    CUDA_MODULE_LOADING=LAZY \
    TORCH_CUDA_ARCH_LIST="7.5;8.0;8.6;8.9;9.0;10.0;12.0+PTX" \
    PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True" \
    PREWARM_MODEL=false \
    LD_LIBRARY_PATH=/usr/local/cuda/lib64:${LD_LIBRARY_PATH} \
    CC=/usr/bin/gcc \
    COMFY_DIR=/app/ComfyUI \
    COMFY_HOST=127.0.0.1:8188 \
    NOVA_UNET_NAME=novaAnimeAM_v6029B.safetensors \
    NOVA_UNET_URL=https://huggingface.co/mogaru99/novaAnimeAM_v6029B/resolve/main/novaAnimeAM_v6029B.safetensors \
    SILVERMOON_UNET_NAME=SilvermoonMix-Anima29B-Evolved-V2.3.safetensors \
    SILVERMOON_UNET_URL=https://huggingface.co/silvermoong/SilvermoonMix-Anima-Evolved/resolve/main/SilvermoonMix-Anima29B-Evolved-V2.3.safetensors \
    ANIMA_BASE_UNET_NAME=anima-base-v1.0.safetensors \
    ANIMA_BASE_UNET_URL=https://huggingface.co/circlestone-labs/Anima/resolve/main/split_files/diffusion_models/anima-base-v1.0.safetensors \
    DEFAULT_MODEL=nova \
    NOVA_CLIP_NAME=qwen_3_06b_base.safetensors \
    NOVA_CLIP_URL=https://huggingface.co/circlestone-labs/Anima/resolve/main/split_files/text_encoders/qwen_3_06b_base.safetensors \
    NOVA_VAE_NAME=qwen_image_vae.safetensors \
    NOVA_VAE_URL=https://huggingface.co/circlestone-labs/Anima/resolve/main/split_files/vae/qwen_image_vae.safetensors

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

# 2. Install PyTorch with CUDA 12.8 (Universal architecture support including Blackwell sm_120)
RUN python3 -m pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cu128 \
    --extra-index-url https://pypi.org/simple \
    torch torchvision torchaudio

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
             /app/ComfyUI/models/loras \
             /app/ComfyUI/output

# 6. Bake Pure-DiT Anima models + Qwen Text Encoder & VAE directly into the Docker image
#    Eliminates runtime download latency completely across all GPU server rollings!
# 6a. Nova Anime AM v6.0 UNet (~5.8 GB) [2D Anime Flagship & Default Model]
RUN aria2c -c -x 16 -s 16 -k 1M --file-allocation=none \
    --dir=/app/ComfyUI/models/diffusion_models --out=novaAnimeAM_v6029B.safetensors \
    https://huggingface.co/mogaru99/novaAnimeAM_v6029B/resolve/main/novaAnimeAM_v6029B.safetensors

# 6b. SilvermoonMix Anima Evolved UNet (~5.8 GB) [Aesthetic Digital Art & Soft Lighting]
RUN aria2c -c -x 16 -s 16 -k 1M --file-allocation=none \
    --dir=/app/ComfyUI/models/diffusion_models --out=SilvermoonMix-Anima29B-Evolved-V2.3.safetensors \
    https://huggingface.co/silvermoong/SilvermoonMix-Anima-Evolved/resolve/main/SilvermoonMix-Anima29B-Evolved-V2.3.safetensors

# 6c. CircleStone Anima Base v1.0 UNet (~4.18 GB) [Official Pure 2D DiT Base Model]
RUN aria2c -c -x 16 -s 16 -k 1M --file-allocation=none \
    --dir=/app/ComfyUI/models/diffusion_models --out=anima-base-v1.0.safetensors \
    https://huggingface.co/circlestone-labs/Anima/resolve/main/split_files/diffusion_models/anima-base-v1.0.safetensors

# 6d. Qwen Text Encoder (~1.1 GB) & Qwen VAE (~240 MB)
RUN aria2c -c -x 8 -s 8 -k 1M --file-allocation=none \
    --dir=/app/ComfyUI/models/text_encoders --out=qwen_3_06b_base.safetensors \
    https://huggingface.co/circlestone-labs/Anima/resolve/main/split_files/text_encoders/qwen_3_06b_base.safetensors \
 && aria2c -c -x 8 -s 8 -k 1M --file-allocation=none \
    --dir=/app/ComfyUI/models/vae --out=qwen_image_vae.safetensors \
    https://huggingface.co/circlestone-labs/Anima/resolve/main/split_files/vae/qwen_image_vae.safetensors

# 6e. Bake Curated SOTA LoRA Collection directly into the image (~1.2 GB, 0ms cold start)
COPY download_loras.sh /app/download_loras.sh
RUN chmod +x /app/download_loras.sh && /app/download_loras.sh /app/ComfyUI/models/loras

# 7. Copy handler, workflows, and startup script
COPY workflow_anima.json /app/workflow_anima.json
COPY handler.py /app/handler.py
COPY warmup.py /app/warmup.py
COPY start.sh /app/start.sh
COPY setup_volume.sh /app/setup_volume.sh
COPY README.md /app/README.md

RUN chmod +x /app/start.sh /app/setup_volume.sh /app/download_loras.sh /app/warmup.py \
    && python3 -m compileall -q /app/ComfyUI \
    && python3 -m compileall -q /app \
    && python3 -m compileall -q /usr/local/lib/python3.11/dist-packages || true

CMD ["/app/start.sh"]

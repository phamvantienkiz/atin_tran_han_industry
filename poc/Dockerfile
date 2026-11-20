# =============================================================================
# Stage 1: Build Next.js Static Export (poc/frontend/out)
# =============================================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY frontend/ ./
ENV NODE_ENV=production
RUN npm run build

# =============================================================================
# Stage 2: GPU Runtime (NVIDIA CUDA 12.4 + cuDNN 9 + FastAPI + ONNX Runtime GPU)
# =============================================================================
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    libglib2.0-0 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

COPY backend/pyproject.toml ./pyproject.toml
COPY backend/app ./app

# Install backend dependencies + CUDA 12 ONNX Runtime GPU (uses container's native CUDA 12.4 + cuDNN 9)
RUN python3 -m pip install --upgrade pip \
    && python3 -m pip install . \
    && (python3 -m pip uninstall -y opencv-python onnxruntime || true) \
    && python3 -m pip install --force-reinstall opencv-python-headless "onnxruntime-gpu==1.23.2" \
    && python3 -c "import uvicorn, fastapi, cv2, onnxruntime, supervision, app.main; print('Verified app.main & runtime imports OK:', onnxruntime.get_available_providers())"

# Copy compiled Next.js static export from Stage 1
COPY --from=frontend-builder /build/frontend/out /app/frontend/out

RUN mkdir -p /app/data /app/models /app/storages /app/backend/logs

EXPOSE 28080

CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "28080", "--timeout-graceful-shutdown", "2"]

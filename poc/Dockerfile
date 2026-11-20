# syntax=docker/dockerfile:1.7

# =============================================================================
# Stage 1: Build Next.js Static Export (poc/frontend/out)
# =============================================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund

COPY frontend/ ./
ENV NODE_ENV=production
RUN --mount=type=cache,target=/build/frontend/.next/cache \
    npm run build

# =============================================================================
# Stage 2: GPU Runtime (NVIDIA CUDA 12.4 + cuDNN 9 + FastAPI + ONNX Runtime GPU)
# =============================================================================
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    libglib2.0-0 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

# Install Python dependencies BEFORE copying app source so backend code edits hit Docker layer cache.
# Note: supervision==0.27.0.post2 declares opencv-python (GUI) in metadata; we intentionally uninstall
# opencv-python and restore pinned opencv-python-headless==5.1.0.95 (--no-deps) for headless runtime.
# `pip check` reporting missing opencv-python for supervision is an expected, intentional substitution.
COPY backend/requirements/docker.txt /tmp/docker.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m pip install --upgrade pip \
    && python3 -m pip install -r /tmp/docker.txt \
    && python3 -m pip uninstall -y opencv-python \
    && python3 -m pip install --no-deps --force-reinstall "opencv-python-headless==5.1.0.95" \
    && (! python3 -m pip show opencv-python >/dev/null 2>&1) \
    && (! python3 -m pip show onnxruntime >/dev/null 2>&1) \
    && python3 -c "import uvicorn, fastapi, cv2, numpy as np, onnxruntime as ort, supervision as sv; ok, enc = cv2.imencode('.jpg', np.zeros((100, 100, 3), dtype=np.uint8)); assert ok and len(enc) > 0; _ = sv.Detections.empty(); print('Verified deps OK | cv2:', cv2.__version__, '| sv:', sv.__version__, '| ort:', ort.__version__, '| providers:', ort.get_available_providers())" \
    && rm -f /tmp/docker.txt

RUN mkdir -p /app/data /app/models /app/storages /app/backend/logs

# Copy application source last (frequently changed)
COPY backend/app ./app
COPY backend/scripts ./scripts
RUN python3 -m compileall -q app

# Copy compiled Next.js static export from Stage 1
COPY --from=frontend-builder /build/frontend/out /app/frontend/out

EXPOSE 28080

CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "28080", "--timeout-graceful-shutdown", "2"]

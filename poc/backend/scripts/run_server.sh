#!/usr/bin/env bash
set -euo pipefail

# Chuyển về thư mục poc/backend bất kể gọi script từ đâu
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
FRONTEND_DIR="$(cd "${BACKEND_DIR}/../frontend" && pwd)"

# 1. Thoát Conda (base) nếu shell tự kích hoạt để bảo vệ cô lập môi trường
conda deactivate 2>/dev/null || true

# 2. Nạp biến môi trường từ poc/backend/.env (nếu có)
if [ -f "${BACKEND_DIR}/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "${BACKEND_DIR}/.env"
    set +a
fi

PORT="${PORT:-28080}"

# 3. Nếu chưa có poc/frontend/out/index.html hoặc có truyền cờ --build thì tự động build Next.js
if [ "${1:-}" = "--build" ] || [ ! -f "${FRONTEND_DIR}/out/index.html" ]; then
    echo "[1/2] Đang build giao diện Next.js Static Export (poc/frontend/out)..."
    cd "${FRONTEND_DIR}"
    if [ ! -d "node_modules" ]; then
        npm install --no-audit --no-fund
    fi
    npm run build
fi

# 4. Khởi chạy FastAPI + AI Core + Next.js UI trên duy nhất 1 cổng PORT
# Dùng exec để tín hiệu Ctrl+C (SIGINT) truyền trực tiếp vào uvicorn và dọn sạch 100% VRAM
cd "${BACKEND_DIR}"
echo "[2/2] Đang khởi động ATIN Trần Hân PoC (FastAPI + Next.js + GPU AI) tại http://0.0.0.0:${PORT} ..."
exec uv run --no-sync uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --timeout-graceful-shutdown 2

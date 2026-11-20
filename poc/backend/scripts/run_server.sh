#!/usr/bin/env bash
set -euo pipefail

# Chuyển về thư mục poc/backend bất kể gọi script từ đâu
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
FRONTEND_SRC_DIR="$(cd "${BACKEND_DIR}/../frontend" && pwd)"
LOG_DIR="${BACKEND_DIR}/logs"
PID_FILE="${LOG_DIR}/server.pid"
LOG_FILE="${LOG_DIR}/server.log"

mkdir -p "${LOG_DIR}"

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

# 3. Nạp thư viện CUDA 12 / cuDNN 9 cô lập bên trong .venv (nếu chạy trực tiếp không qua Docker)
NVIDIA_LIB_DIRS="$(find "${BACKEND_DIR}/.venv/lib" -type d -path "*/nvidia/*/lib" 2>/dev/null | paste -sd ':' - || true)"
if [ -n "${NVIDIA_LIB_DIRS}" ]; then
    export LD_LIBRARY_PATH="${NVIDIA_LIB_DIRS}:${LD_LIBRARY_PATH:-}"
fi

build_frontend_if_needed() {
    local force_build="${1:-false}"
    if [ "${force_build}" = "true" ] || [ ! -f "${FRONTEND_SRC_DIR}/out/index.html" ]; then
        echo "[1/2] Đang build giao diện Next.js Static Export (poc/frontend/out)..."
        cd "${FRONTEND_SRC_DIR}"
        if [ ! -d "node_modules" ]; then
            npm install --no-audit --no-fund
        fi
        npm run build
    fi
}

is_running() {
    if [ -f "${PID_FILE}" ]; then
        local pid
        pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
        if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

stop_native_server() {
    if is_running; then
        local pid
        pid="$(cat "${PID_FILE}")"
        echo "[STOP] Đang dừng tiến trình chạy nền non-Docker (PID ${pid})..."
        kill -INT -- "-${pid}" 2>/dev/null || kill -INT "${pid}" 2>/dev/null || true

        for _ in $(seq 1 10); do
            if ! kill -0 "${pid}" 2>/dev/null; then
                rm -f "${PID_FILE}"
                echo "[OK] Đã dừng tiến trình non-Docker (PID ${pid})."
                return 0
            fi
            sleep 0.5
        done

        echo "[WARN] Tiến trình ${pid} chưa thoát sau 5s, ép dừng (SIGKILL)..."
        kill -KILL -- "-${pid}" 2>/dev/null || kill -KILL "${pid}" 2>/dev/null || true
        rm -f "${PID_FILE}"
    else
        rm -f "${PID_FILE}"
    fi
}

stop_docker_server() {
    if command -v docker >/dev/null 2>&1; then
        cd "${BACKEND_DIR}"
        if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q '^tranhan_ai_poc$'; then
            echo "[STOP] Đang dừng và gỡ container Docker tranhan_ai_poc..."
            docker compose down --remove-orphans
            echo "[OK] Đã dừng sạch Docker container tranhan_ai_poc."
        fi
    fi
}

stop_server() {
    stop_native_server
    stop_docker_server
    echo "[OK] Đã giải phóng hoàn toàn port ${PORT} và VRAM của PoC."
}

start_docker() {
    stop_native_server
    cd "${BACKEND_DIR}"
    echo "[DOCKER] Đang build & khởi chạy container tranhan_ai_poc trên cổng ${PORT}..."
    docker compose up -d --build
    echo "[OK] Container tranhan_ai_poc đã chạy nền 24/7 trên port ${PORT}!"
    echo "     Xem log   : docker compose logs -f"
    echo "     Trạng thái: ./scripts/run_server.sh status"
    echo "     Dừng hẳn  : ./scripts/run_server.sh stop  (hoặc: docker compose down)"
}

start_background() {
    local force_build="${1:-false}"
    stop_docker_server
    if is_running; then
        echo "[INFO] Server đang chạy rồi (PID $(cat "${PID_FILE}"), port ${PORT}). Dùng './scripts/run_server.sh restart' để khởi động lại."
        return 0
    fi
    build_frontend_if_needed "${force_build}"
    cd "${BACKEND_DIR}"
    echo "[2/2] Đang chạy nền ATIN Trần Hân PoC tại http://0.0.0.0:${PORT} (tắt Termius server vẫn chạy)..."
    setsid nohup uv run --no-sync uvicorn app.main:app \
        --host 0.0.0.0 \
        --port "${PORT}" \
        --timeout-graceful-shutdown 2 \
        >> "${LOG_FILE}" 2>&1 < /dev/null &
    local bg_pid=$!
    echo "${bg_pid}" > "${PID_FILE}"
    sleep 1
    if kill -0 "${bg_pid}" 2>/dev/null; then
        echo "[OK] Server đã chạy nền thành công (PID ${bg_pid})."
        echo "     Xem log : ./scripts/run_server.sh logs"
        echo "     Kiểm tra: ./scripts/run_server.sh status"
        echo "     Dừng hẳn: ./scripts/run_server.sh stop"
    else
        rm -f "${PID_FILE}"
        echo "[ERROR] Server thoát sớm khi khởi động. Kiểm tra log:" >&2
        tail -n 30 "${LOG_FILE}" >&2 || true
        return 1
    fi
}

show_status() {
    if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^tranhan_ai_poc$'; then
        echo "[RUNNING - DOCKER] Container tranhan_ai_poc đang chạy trên port ${PORT}:"
        docker ps --filter "name=tranhan_ai_poc"
        nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv 2>/dev/null || true
        return 0
    fi
    if is_running; then
        local pid
        pid="$(cat "${PID_FILE}")"
        echo "[RUNNING - NATIVE] ATIN Trần Hân PoC đang chạy (PID ${pid}, port ${PORT})."
        ss -tulpn 2>/dev/null | grep ":${PORT} " || true
        nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv 2>/dev/null | grep -E "pid|${pid}" || true
    else
        echo "[STOPPED] ATIN Trần Hân PoC hiện đang dừng (cả Docker lẫn Native)."
    fi
}

ACTION="${1:-fg}"
FLAG="${2:-}"
FORCE_BUILD="false"
if [ "${ACTION}" = "--build" ] || [ "${FLAG}" = "--build" ]; then
    FORCE_BUILD="true"
fi

case "${ACTION}" in
    docker|docker-start)
        start_docker
        ;;
    docker-stop)
        stop_docker_server
        ;;
    start)
        start_background "${FORCE_BUILD}"
        ;;
    stop)
        stop_server
        ;;
    restart)
        stop_server
        start_background "${FORCE_BUILD}"
        ;;
    status)
        show_status
        ;;
    logs)
        if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^tranhan_ai_poc$'; then
            cd "${BACKEND_DIR}"
            docker compose logs -f --tail=50
        else
            touch "${LOG_FILE}"
            echo "[INFO] Đang xem log (${LOG_FILE}) — bấm Ctrl+C để thoát xem log (server vẫn tiếp tục chạy nền)..."
            tail -n 50 -f "${LOG_FILE}"
        fi
        ;;
    fg|--build)
        stop_server
        build_frontend_if_needed "${FORCE_BUILD}"
        cd "${BACKEND_DIR}"
        echo "[2/2] Đang khởi động ATIN Trần Hân PoC (foreground) tại http://0.0.0.0:${PORT} ..."
        exec uv run --no-sync uvicorn app.main:app \
            --host 0.0.0.0 \
            --port "${PORT}" \
            --timeout-graceful-shutdown 2
        ;;
    *)
        echo "Cách dùng: $0 [docker|start|stop|restart|status|logs|--build] [--build]"
        exit 1
        ;;
esac

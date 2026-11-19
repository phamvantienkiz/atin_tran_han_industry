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

# 3. Nạp thư viện CUDA 12 / cuDNN 9 cô lập bên trong .venv (nếu đã cài nhóm [gpu])
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

stop_server() {
    if ! is_running; then
        rm -f "${PID_FILE}"
        echo "[INFO] Server hiện không chạy."
        return 0
    fi
    local pid
    pid="$(cat "${PID_FILE}")"
    echo "[STOP] Đang gửi tín hiệu dừng (SIGINT) tới tiến trình PID ${pid}..."
    kill -INT -- "-${pid}" 2>/dev/null || kill -INT "${pid}" 2>/dev/null || true

    for _ in $(seq 1 10); do
        if ! kill -0 "${pid}" 2>/dev/null; then
            rm -f "${PID_FILE}"
            echo "[OK] Đã dừng server và giải phóng port ${PORT} + VRAM."
            return 0
        fi
        sleep 0.5
    done

    echo "[WARN] Tiến trình ${pid} chưa thoát sau 5s, ép dừng cả nhóm tiến trình (SIGKILL)..."
    kill -KILL -- "-${pid}" 2>/dev/null || kill -KILL "${pid}" 2>/dev/null || true
    rm -f "${PID_FILE}"
    echo "[OK] Đã buộc dừng PID ${pid}."
}

start_background() {
    local force_build="${1:-false}"
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
    if is_running; then
        local pid
        pid="$(cat "${PID_FILE}")"
        echo "[RUNNING] ATIN Trần Hân PoC đang chạy (PID ${pid}, port ${PORT})."
        ss -tulpn 2>/dev/null | grep ":${PORT} " || true
        nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv 2>/dev/null | grep -E "pid|${pid}" || true
    else
        echo "[STOPPED] ATIN Trần Hân PoC đang dừng."
    fi
}

ACTION="${1:-fg}"
FLAG="${2:-}"
FORCE_BUILD="false"
if [ "${ACTION}" = "--build" ] || [ "${FLAG}" = "--build" ]; then
    FORCE_BUILD="true"
fi

case "${ACTION}" in
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
        touch "${LOG_FILE}"
        echo "[INFO] Đang xem log (${LOG_FILE}) — bấm Ctrl+C để thoát xem log (server vẫn tiếp tục chạy nền)..."
        tail -n 50 -f "${LOG_FILE}"
        ;;
    fg|--build)
        if is_running; then
            echo "[WARN] Đang có bản chạy nền (PID $(cat "${PID_FILE}")). Hãy chạy './scripts/run_server.sh stop' trước khi chạy foreground." >&2
            exit 1
        fi
        build_frontend_if_needed "${FORCE_BUILD}"
        cd "${BACKEND_DIR}"
        echo "[2/2] Đang khởi động ATIN Trần Hân PoC (foreground) tại http://0.0.0.0:${PORT} ..."
        exec uv run --no-sync uvicorn app.main:app \
            --host 0.0.0.0 \
            --port "${PORT}" \
            --timeout-graceful-shutdown 2
        ;;
    *)
        echo "Cách dùng: $0 [start|stop|restart|status|logs|--build] [--build]"
        exit 1
        ;;
esac

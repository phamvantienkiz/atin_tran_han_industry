# PoC v001 — Hướng Dẫn Triển Khai Step-by-Step Lên Server `aiot`, Xem Qua Termius & Bàn Giao Port Public Cho Công Ty

> [!IMPORTANT]
> **Cập Nhật Quy Trình Triển Khai Chính Thức (Docker Compose Tại `poc/` — `https://tranhan.atin.vn/`)**:
> - Toàn bộ hệ thống **ATIN Smart Fishing PoC v001** hiện đã được đóng gói hoàn chỉnh bằng **Multi-Stage Docker Compose ngay tại thư mục gốc `poc/`** ([poc/Dockerfile](file:///e:/ATIN/atin_tran_han_industry/poc/Dockerfile) + [poc/docker-compose.yml](file:///e:/ATIN/atin_tran_han_industry/poc/docker-compose.yml)) chạy trên cổng **`28080`** (đã được công ty mở Public ra **`https://tranhan.atin.vn/`**).
> - Xem hướng dẫn vận hành Docker Compose ngắn gọn nhất tại: **[poc/docs/deploy.md](file:///e:/ATIN/atin_tran_han_industry/poc/docs/deploy.md)**.
> - Tài liệu bên dưới ghi nhận cả quy trình chạy qua Docker Compose tại `poc/` lẫn quy trình chạy Native `.venv` dự phòng trên server `aiot`.

> **Mục đích tài liệu**:
> 1. Là cẩm nang **Step-by-Step thực chiến** để triển khai PoC v001 (FastAPI + Next.js Static Export 1-Port) lên server GPU **`aiot` (`192.168.1.170`, NVIDIA RTX A400 4GB VRAM)** ngay tại thư mục riêng **`tts@aiot:~/projects/tien$`**.
> 2. **Yêu cầu bắt buộc đối với Hydrogen / Neon**: Sau khi viết xong code Backend + Frontend Next.js và vượt qua toàn bộ bài test ở local, **Hydrogen / Neon phải tạo sẵn script `poc/backend/scripts/run_server.sh` đúng chuẩn trong tài liệu này**, đồng thời kiểm tra lại toàn bộ các bước dưới đây để đảm bảo kỹ thuật viên chỉ cần copy-paste từng khối lệnh trên `tts@aiot:~/projects/tien$` là hệ thống chạy ngay 100%.

---

## 1. Thông Số Hạ Tầng Thực Tế Trên Server `aiot`

| Hạng mục | Giá trị trên Server `aiot` |
| :--- | :--- |
| **SSH Host & User** | `tts@192.168.1.170` (Hostname: `aiot`, Ubuntu 22.04.5 LTS) |
| **Thư mục đứng chân của Tiến** | `tts@aiot:~/projects/tien$` (`/home/tts/projects/tien`) |
| **Thư mục dự án sau khi clone** | `/home/tts/projects/tien/atin_tran_han_industry` |
| **GPU & Giới hạn VRAM PoC** | NVIDIA RTX A400 (**4 GB VRAM**) — Giới hạn PoC `AI_VRAM_LIMIT_MB=1536` |
| **Port chạy PoC (1 Port duy nhất)** | Mặc định **`28080`** (đổi linh hoạt qua biến `PORT` trong `poc/backend/.env`) |
| **Nguồn Camera Trần Hân** | `nmts2025.smartddns.tv:80` · User: `user` · Pass: `testcam@123` (Kênh 16, 17, 18, 21) |

---

## 1.1. Quy Trình Triển Khai Chính Thức Bằng Docker Compose (BuildKit)

Tại thư mục `poc/` trên server `aiot` (`~/projects/tien/atin_tran_han_industry/poc`):

```bash
git pull origin feat/pocv001
DOCKER_BUILDKIT=1 docker compose --progress plain build
docker compose up -d
```

Kiểm tra nhanh GPU & logs sau khi container `tranhan_ai_poc` khởi động:

```bash
docker compose exec -T tranhan-poc nvidia-smi
docker compose logs --tail=50 | grep -E "active_provider|METRICS"
curl -s http://127.0.0.1:28080/api/v1/health
```

> Lưu ý: `poc/Dockerfile` sử dụng `poc/backend/requirements/docker.txt` với BuildKit cache mount (`/root/.npm`, `/build/frontend/.next/cache`, `/root/.cache/pip`) giúp các lần rebuild chỉ sửa code `backend/app/` hoặc `frontend/` diễn ra nhanh chóng mà không phải tải lại thư viện CUDA/ONNX.

---

## 2. Bản Thiết Kế Script `poc/backend/scripts/run_server.sh` (Hydrogen / Neon Tạo Sẵn Trong Repo)

**Hydrogen / Neon** bắt buộc phải tạo file `poc/backend/scripts/run_server.sh` (với dòng kết thúc LF chuẩn Linux) có nội dung dưới đây để tự động kiểm tra bản build Next.js và khởi chạy Uvicorn trên 1 port duy nhất, đảm bảo bấm **`Ctrl + C` dừng sạch 100% tiến trình và giải phóng VRAM**:

```bash
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
```

---

## 3. Hướng Dẫn Step-by-Step Đưa Lên Server `aiot` (Từ Bước Clone GitHub Đến Khi Chạy)

Thực hiện tuần tự từng bước dưới đây trên cửa sổ SSH **Termius** kết nối vào `tts@192.168.1.170`:

### Bước 1: Kiểm tra môi trường tại `tts@aiot:~/projects/tien$` & Dọn tiến trình cũ (nếu có)

```bash
# 1. Đảm bảo đang đứng ở thư mục riêng của Tiến và thoát Conda (base)
cd ~/projects/tien
conda deactivate 2>/dev/null || true

# 2. Kiểm tra VRAM GPU và cổng 28080 (nếu dự án cũ đang giữ cổng 28080 trong tmux thì tắt trước)
nvidia-smi
ss -tulpn | grep 28080 || true
```
*(Nếu thấy cổng `28080` đang bị phiên `tmux` của dự án cũ chiếm, gõ `tmux ls` rồi `tmux kill-session -t poc` để giải phóng cổng và VRAM).*

---

### Bước 2: Cài đặt Node.js Runtime trên Server `aiot` (Chỉ làm 1 lần đầu tiên)

Vì server `aiot` chưa có Node.js runtime để build Next.js (`next build` yêu cầu **Node.js >= 18.18 / 20 LTS**; lưu ý gói `apt install nodejs` mặc định của Ubuntu 22.04 chỉ là Node 12 đã quá cũ không build được Next.js 15), hãy chạy 1 trong 2 cách sau:

#### Cách 2A (Nếu user `tts` có quyền `sudo` — Cài Node.js 20 LTS chuẩn qua `apt`):
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
node -v   # Xác nhận >= v20.x.x
npm -v
```

#### Cách 2B (Nếu không dùng `sudo` — Tải bản Node.js 20 LTS cục bộ ngay trong `~/projects/tien/.local`):
```bash
mkdir -p ~/projects/tien/.local
cd ~/projects/tien/.local
curl -fsSL https://nodejs.org/dist/v20.18.1/node-v20.18.1-linux-x64.tar.xz -o node20.tar.xz
tar -xJf node20.tar.xz
rm -f node20.tar.xz
export PATH="$HOME/projects/tien/.local/node-v20.18.1-linux-x64/bin:$PATH"
grep -q "node-v20.18.1-linux-x64/bin" ~/.bashrc || echo 'export PATH="$HOME/projects/tien/.local/node-v20.18.1-linux-x64/bin:$PATH"' >> ~/.bashrc
node -v   # Xác nhận v20.18.1
npm -v
```

---

### Bước 3: Clone Repo từ GitHub vào `tts@aiot:~/projects/tien$`

```bash
cd ~/projects/tien

# Clone repo từ GitHub (thay <GITHUB_REPO_URL> bằng link repo thực tế của dự án)
git clone <GITHUB_REPO_URL> atin_tran_han_industry
cd ~/projects/tien/atin_tran_han_industry

# Nếu đã clone trước đó thì chỉ cần pull nhánh mới nhất:
# cd ~/projects/tien/atin_tran_han_industry && git pull
```

---

### Bước 4: Thiết lập Môi trường Python Cô lập (`.venv`) + Cài `onnxruntime-gpu` & Chuyển đổi Model FP16

```bash
cd ~/projects/tien/atin_tran_han_industry/poc/backend
conda deactivate 2>/dev/null || true

# 1. Tạo môi trường ảo cục bộ .venv bằng uv (Python 3.12 hoặc 3.11)
uv venv .venv

# 2. Cài đặt dependencies kèm nhóm [gpu] vào đúng poc/backend/.venv
uv pip install --python .venv/bin/python -e ".[dev,gpu]"

# 3. Đảm bảo binary CUDA của onnxruntime-gpu không bị gói onnxruntime CPU ghi đè
uv pip install --python .venv/bin/python --force-reinstall --no-deps onnxruntime-gpu

# 4. Kiểm tra nhanh CUDAExecutionProvider (RTX A400), ByteTrack và OpenCV
.venv/bin/python -c "import cv2, onnxruntime as ort, supervision as sv; print('Providers:', ort.get_available_providers()); print('ByteTrack:', sv.ByteTrack, 'cv2:', cv2.__version__)"

# 5. Chuyển đổi model yolo26s_best.onnx sang FP16 (yolo26s_fp16.onnx) để tối ưu Tensor Cores
.venv/bin/python scripts/convert_onnx_fp16.py
```

---

### Bước 5: Tạo File Cấu Hình `poc/backend/.env` Kết Nối Trực Tiếp DDNS Trần Hân

```bash
cd ~/projects/tien/atin_tran_han_industry/poc/backend
cat > .env << 'EOF'
APP_NAME="ATIN Tran Han AI Backend"
ENVIRONMENT=poc
DEBUG=true
PORT=28080
SERVE_FRONTEND=true
FRONTEND_DIR=../frontend/out
FRONTEND_LEGACY_DIR=../frontend

# Thông tin NVR Trần Hân (DDNS Direct Mode)
NVR_HOST=nmts2025.smartddns.tv
NVR_PORT=80
NVR_USER=user
NVR_PASS=testcam@123
NVR_STREAM_FPS_LIMIT=12.0

# Cấu hình AI GPU RTX A400 (4GB VRAM -> Cap 1024MB)
AI_ENABLED=true
MODEL_PATH=../models/yolo26s_fp16.onnx
AI_RUNTIME=auto
AI_VRAM_LIMIT_MB=1024
AI_CONF_THRESHOLD=0.40
AI_IMGSZ=640
AI_TARGET_FPS=12.0
AI_ANCHOR_MODE=bottom_center
AI_PRESENCE_GRACE_SECONDS=2.0
AI_PRESENCE_WARNING_SECONDS=10.0
AI_TIMELINE_WINDOW_SECONDS=1800
WS_PUSH_MAX_HZ=15.0
EOF
```

---

### Bước 6: Build Next.js Static Export (`poc/frontend/out/`) & Khởi Chạy Hệ Thống

```bash
# 1. Cài đặt thư viện local trong poc/frontend/node_modules và build ra poc/frontend/out/
cd ~/projects/tien/atin_tran_han_industry/poc/frontend
npm install --no-audit --no-fund
npm run build
ls -la out/   # Xác nhận đã có index.html và thư mục _next/

# 2. Cấp quyền thực thi và chạy server trên cổng 28080
cd ~/projects/tien/atin_tran_han_industry/poc/backend
chmod +x scripts/run_server.sh
./scripts/run_server.sh
```

> **Cách dừng server an toàn**:
> - Khi đang chạy `./scripts/run_server.sh` trên cửa sổ Termius, chỉ cần bấm **`Ctrl + C`** 1 lần.
> - Toàn bộ tiến trình Uvicorn, các luồng đọc NVR (`NvrStreamManager`), WebSocket và bộ nhớ VRAM trên RTX A400 sẽ được giải phóng sạch 100% trong vòng `<= 2 giây`.

---

## 4. Hai Chế Độ Truy Cập & Kiểm Thử (Termius Local vs Công Ty Mở Port Public)

### 4.1. Chế độ 1: Khi Công Ty Chưa Mở Port Public — Xem Ngay Qua Termius Port Forwarding

Bạn **không cần tạo rule mới trên Termius** nếu đã có sẵn bộ rule của dự án trước:
1. Bật **OpenVPN Connect** trên laptop.
2. Mở **Termius** $\rightarrow$ kết nối vào `aiot` (`tts@192.168.1.170`) với rule **Local Port Forwarding** sẵn có:
   - **Type**: `Local`
   - **Local Port**: `28080`
   - **Destination Host**: `127.0.0.1`
   - **Destination Port**: `28080`
   *(Hai rule `28889` và `28189` cũ cứ giữ nguyên trên Termius cũng không sao, hoàn toàn không ảnh hưởng).*
3. Mở trình duyệt trên laptop truy cập:
   - Giao diện Next.js Live View: **`http://localhost:28080`**
   - Tài liệu Swagger API: **`http://localhost:28080/docs`**
   - Healthcheck: **`http://localhost:28080/api/v1/health`**

---

### 4.2. Chế độ 2: Khi Bàn Giao Cho Công Ty Mở Port Public / Gắn Domain Cho Khách Hàng Xem (Không Cần OpenVPN)

Khi bạn đã test ổn định qua Termius và chốt số Port (mặc định là **`28080`**, hoặc nếu công ty yêu cầu đổi sang port khác ví dụ `28090` thì chỉ cần sửa `PORT=28090` trong `poc/backend/.env` rồi chạy lại `./scripts/run_server.sh`):

#### Thông tin gửi cho bộ phận IT / Hạ tầng công ty:
- **IP nội bộ server `aiot`**: `192.168.1.170`
- **Port dịch vụ PoC (TCP)**: **`28080`** (hoặc port được chỉ định)
- **Đặc điểm kỹ thuật**: Chỉ cần mở/forward **đúng 1 cổng TCP duy nhất** này. Toàn bộ Giao diện Web Next.js, REST API, WebSocket BBox và Luồng Video MJPEG đều đi chung qua cổng `28080`.
- **Nếu IT công ty bọc qua Nginx Reverse Proxy để gắn Domain HTTPS (ví dụ `https://tranhan-poc.atin.vn`)**, gửi kèm cho IT đoạn cấu hình location chuẩn sau để WebSocket và luồng MJPEG không bị nghẽn buffer:
  ```nginx
  location / {
      proxy_pass http://192.168.1.170:28080;
      proxy_http_version 1.1;
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto $scheme;

      # Bắt buộc cho WebSocket BBox (/api/v1/ws/detections)
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";

      # Bắt buộc cho luồng video MJPEG (/api/v1/cameras/*/mjpeg) mượt, không trễ
      proxy_buffering off;
      proxy_cache off;
      proxy_read_timeout 3600s;
  }
  ```

> **Lưu ý khi mở cho khách hàng tự vào xem bất kỳ lúc nào trong ngày**:
> - Khi bạn đang code/debug: chạy trực tiếp `./scripts/run_server.sh` ở cửa sổ Termius để dễ `Ctrl + C`.
> - Khi đã gửi link Public cho khách hàng Trần Hân vào xem tự do (kể cả khi bạn tắt laptop), bọc lệnh `./scripts/run_server.sh` trong 1 phiên `tmux` được đặt tên rõ ràng:
>   ```bash
>   tmux new -s tranhan_poc
>   cd ~/projects/tien/atin_tran_han_industry/poc/backend
>   ./scripts/run_server.sh
>   # Bấm Ctrl+B rồi bấm D để giữ server chạy 24/7 cho khách xem.
>   # Khi muốn dừng hẳn: tmux attach -t tranhan_poc -> bấm Ctrl+C -> exit
>   ```

---

## 5. Quy Trình Cập Nhật Nhanh (Continuous Update) Chỉ Mất 10 Giây

Mỗi khi Hydrogen / Neon sửa code xong và push lên GitHub, trên server `aiot` chỉ cần chạy đúng 2 dòng lệnh:

```bash
cd ~/projects/tien/atin_tran_han_industry && git pull
cd poc/backend && ./scripts/run_server.sh --build
```
*(Cờ `--build` sẽ tự động build lại `poc/frontend/out/` trong ~5–10 giây rồi khởi chạy ngay FastAPI + AI Core mới nhất trên cùng cổng `28080`).*

---

## 6. Checklist Nghiệm Thu Bắt Buộc Cho Hydrogen / Neon Trước Khi Kết Thúc Task

Hydrogen / Neon phải đánh dấu hoàn thành đủ 6 mục sau trước khi bàn giao cho người dùng:
- [x] **1. Backend Tests & Linter**: Chạy `pytest -v` (18/18 tests pass: State Machine 4 trạng thái `present/leaving/empty/alert`, ByteTrack IoU Snap, NvrStreamManager, real ONNX pipeline smoke, REST API, WebSocket) và `ruff check app tests scripts` trong `poc/backend/` đạt **100% Pass, 0 Warning/Error**.
- [x] **2. Frontend Static Export Build**: Chạy `npm run typecheck` và `npm run build` trong `poc/frontend/` tạo ra thư mục `poc/frontend/out/` sạch lỗi (0 TypeScript error, 0 build error).
- [x] **3. Single-Port Integration Verify**: Khởi chạy Uvicorn ở local cổng `28080`, truy cập `http://localhost:28080/` xác nhận tải được giao diện Next.js Static Export, gọi `/api/v1/health`, `/api/v1/config`, `/api/v1/cameras`, kết nối `/api/v1/ws/detections` nhận đủ dữ liệu 4 camera thực (`ch16`, `ch17`, `ch18`, `ch21`).
- [x] **4. Relative URL Check**: Rà soát toàn bộ `poc/frontend/src/` đảm bảo **0 chuỗi hardcode `localhost`, `127.0.0.1` hay `192.168.1.170`** trong các lệnh gọi API/WebSocket/Image.
- [x] **5. Script `run_server.sh` & `convert_onnx_fp16.py`**: Đã tạo sẵn với dòng kết thúc LF chuẩn Linux, kiểm tra cú pháp chuẩn và sẵn sàng chạy trên Ubuntu `aiot`.
- [x] **6. Báo cáo hướng dẫn Step-by-Step cho User**: Đã đồng bộ các lệnh triển khai thực tế từ `tts@aiot:~/projects/tien$` trong tài liệu này.

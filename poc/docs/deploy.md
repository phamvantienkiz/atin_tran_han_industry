# Hướng Dẫn Triển Khai Chi Tiết PoC v001 Trên Server GPU `aiot` (`tts@aiot:~/projects/tien$`)

> **Mục tiêu**: Đưa trọn bộ **ATIN Trần Hân AI PoC v001** (Backend FastAPI + AI GPU `onnxruntime-gpu` FP16 + ByteTrack + Next.js Static Export) lên server **`aiot` (`192.168.1.170`)**, chạy gọn trên **1 Port duy nhất (`28080`)** để:
> 1. Kiểm thử trực tiếp từ laptop cá nhân qua **OpenVPN + Termius Port Forwarding (`28080 -> 127.0.0.1:28080`)**.
> 2. Sau khi test ổn định, báo bộ phận IT công ty mở **Public Port `28080`** (hoặc gắn Domain HTTPS) cho khách hàng Nhà máy Thủy sản Trần Hân truy cập trực tiếp.

---

## 1. Thông Số Hạ Tầng & Quy Ước Bắt Buộc

| Hạng mục | Giá trị thực tế |
| :--- | :--- |
| **SSH Server** | `tts@192.168.1.170` (Hostname: `aiot`, Ubuntu 22.04.5 LTS) |
| **Thư mục làm việc** | `~/projects/tien` (`/home/tts/projects/tien`) |
| **Thư mục dự án** | `~/projects/tien/atin_tran_han_industry` |
| **GitHub Repository** | `https://github.com/phamvantienkiz/atin_tran_han_industry.git` (nhánh `jin`) |
| **GPU & Giới hạn VRAM** | NVIDIA RTX A400 (**4 GB VRAM dùng chung**) — PoC giới hạn **`AI_VRAM_LIMIT_MB=1024`** |
| **Port dịch vụ duy nhất** | **`28080`** (gộp chung Next.js UI + REST API + WebSocket BBox + MJPEG Stream) |
| **NVR Trần Hân (DDNS)** | `nmts2025.smartddns.tv:80` · User: `user` · Pass: `testcam@123` (Kênh `16, 17, 18, 21`) |
| **Quy tắc vận hành** | Cô lập 100% trong `poc/backend/.venv` (chạy bằng `uv`) và `poc/frontend/node_modules`. **Không dùng `tmux`** khi dev/test; bấm **`Ctrl + C`** phải dừng sạch tiến trình & giải phóng VRAM ngay lập tức. |

---

## 2. Giai Đoạn 0 — Chuẩn Bị Trên Laptop Windows (Push Code Lên GitHub)

Trước khi SSH sang `aiot`, đảm bảo toàn bộ mã nguồn PoC v001 trên laptop đã được push lên GitHub (nhánh `jin`):

```powershell
cd E:\ATIN\atin_tran_han_industry
git status
git add poc/
git commit -m "feat(poc): implement PoC v001 single-port FastAPI + GPU AI Core + Next.js"
git push origin jin
```

> [!IMPORTANT]
> Trong `.gitignore` của dự án có quy tắc bỏ qua **`*.onnx`**, **`*.pt`** và **`.env`**. Do đó:
> - File model **`poc/models/yolo26s_best.onnx`** sẽ **không** đi theo `git push` — ta sẽ copy riêng bằng `scp` (hoặc Termius SFTP) ở **Bước 3.2**.
> - File cấu hình **`poc/backend/.env`** sẽ được tạo trực tiếp trên `aiot` ở **Bước 5**.

---

## 3. Giai Đoạn 1 — SSH Vào Server `aiot` & Kiểm Tra Môi Trường

Bật **OpenVPN Connect** trên laptop, mở **Termius** kết nối tới `tts@192.168.1.170` và chạy:

```bash
# 1. Di chuyển vào thư mục riêng và thoát Conda (base) để tránh xung đột Python
cd ~/projects/tien
conda deactivate 2>/dev/null || true

# 2. Kiểm tra GPU, VRAM đang sử dụng và tiến trình đang giữ cổng 28080 (nếu có)
nvidia-smi
ss -tulpn | grep 28080 || true

# 3. Kiểm tra uv đã có sẵn chưa
which uv && uv --version
```

### Dọn phiên `tmux` của dự án cũ (nếu cổng `28080` hoặc GPU đang bị chiếm)
```bash
tmux ls 2>/dev/null || true
# Nếu thấy session cũ (ví dụ: poc) đang chạy dự án traffic_congestion_evaluation thì tắt:
# tmux kill-session -t poc
```

*(Nếu `uv` chưa có trong `PATH`, cài cục bộ không cần `sudo` bằng: `curl -LsSf https://astral.sh/uv/install.sh | sh && source ~/.local/bin/env`)*

---

## 4. Giai Đoạn 2 — Cài Đặt Node.js 20 LTS Trên `aiot` (Chỉ Làm 1 Lần Đầu)

Next.js 15 yêu cầu **Node.js `>= 18.18`** (khuyến nghị **Node 20 LTS**). Kiểm tra trước:

```bash
node -v 2>/dev/null || echo "Chưa có Node.js"
```

Nếu chưa có Node.js hoặc phiên bản `< 18.18`, chọn **Cách B** (ưu tiên trên server dùng chung vì **không cần `sudo`**, không động tới hệ thống của dev khác):

### Cách B (Khuyến nghị — Cài cục bộ trong `~/projects/tien/.local`, không cần `sudo`):
```bash
mkdir -p ~/projects/tien/.local
cd ~/projects/tien/.local
curl -fsSL https://nodejs.org/dist/v20.18.1/node-v20.18.1-linux-x64.tar.xz -o node20.tar.xz
tar -xJf node20.tar.xz
rm -f node20.tar.xz

# Thêm vào PATH phiên hiện tại và lưu vào ~/.bashrc
export PATH="$HOME/projects/tien/.local/node-v20.18.1-linux-x64/bin:$PATH"
grep -q "node-v20.18.1-linux-x64/bin" ~/.bashrc || echo 'export PATH="$HOME/projects/tien/.local/node-v20.18.1-linux-x64/bin:$PATH"' >> ~/.bashrc

node -v   # Kỳ vọng: v20.18.1
npm -v    # Kỳ vọng: 10.x.x
```

### Cách A (Thay thế nếu muốn cài system-wide bằng `sudo`):
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
node -v && npm -v
```

---

## 5. Giai Đoạn 3 — Clone Repo Từ GitHub & Upload File Model ONNX

### Bước 3.1: Clone (hoặc Pull) mã nguồn vào `~/projects/tien`
```bash
cd ~/projects/tien

# Lần đầu tiên: clone trực tiếp nhánh jin
git clone -b jin https://github.com/phamvantienkiz/atin_tran_han_industry.git
cd ~/projects/tien/atin_tran_han_industry

# Tạo thư mục models nếu chưa tồn tại
mkdir -p poc/models
```

*(Nếu đã clone trước đó rồi thì chỉ cần: `cd ~/projects/tien/atin_tran_han_industry && git fetch origin && git checkout jin && git pull origin jin`)*

### Bước 3.2: Upload file `yolo26s_best.onnx` từ Laptop Windows lên `aiot`
Vì `*.onnx` không được push lên GitHub, mở một cửa sổ **PowerShell trên Laptop Windows** và chạy `scp`:

```powershell
scp E:\ATIN\atin_tran_han_industry\poc\models\yolo26s_best.onnx tts@192.168.1.170:/home/tts/projects/tien/atin_tran_han_industry/poc/models/
```

*(Hoặc mở tab **SFTP** trong Termius, kéo thả file `E:\ATIN\atin_tran_han_industry\poc\models\yolo26s_best.onnx` vào `/home/tts/projects/tien/atin_tran_han_industry/poc/models/`).*

Quay lại cửa sổ SSH `aiot` xác nhận file đã lên đủ dung lượng:
```bash
ls -lh ~/projects/tien/atin_tran_han_industry/poc/models/
```

---

## 6. Giai Đoạn 4 — Tạo Môi Trường Python `.venv` GPU & Chuyển Đổi Model FP16

```bash
cd ~/projects/tien/atin_tran_han_industry/poc/backend
conda deactivate 2>/dev/null || true

# 1. Tạo môi trường ảo cô lập .venv bằng uv (Python 3.11 hoặc 3.12)
uv venv .venv

# 2. Cài đặt toàn bộ dependencies kèm nhóm [gpu] (onnxruntime-gpu, onnx, onnxconverter-common)
uv pip install --python .venv/bin/python -e ".[dev,gpu]"

# 3. BẮT BUỘC: Force reinstall onnxruntime-gpu để đảm bảo binary CUDA không bị bản CPU ghi đè
uv pip install --python .venv/bin/python --force-reinstall --no-deps onnxruntime-gpu

# 4. Kiểm tra CUDAExecutionProvider (RTX A400), ByteTrack và OpenCV
.venv/bin/python -c "import cv2, onnxruntime as ort, supervision as sv; print('Providers:', ort.get_available_providers()); print('ByteTrack:', sv.ByteTrack, 'cv2:', cv2.__version__)"
```

> [!TIP]
> - Kết quả `Providers:` **bắt buộc** phải có `'CUDAExecutionProvider'` (ví dụ: `['TensorrtExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']`).
> - Nếu bước 4 báo lỗi `ImportError: libGL.so.1` (do `supervision` kéo theo `opencv-python` bản GUI trên Ubuntu headless), xử lý sạch ngay trong `.venv` bằng 2 dòng sau:
>   ```bash
>   uv pip uninstall --python .venv/bin/python opencv-python
>   uv pip install --python .venv/bin/python --force-reinstall opencv-python-headless
>   ```

### Bước 4.2: Chuyển đổi `yolo26s_best.onnx` (FP32) → `yolo26s_fp16.onnx` (FP16)
Chạy 1 lần duy nhất để tối ưu Tensor Cores và tiết kiệm ~50% VRAM trên RTX A400 (giữ nguyên input/output FP32 để không vỡ NMS):

```bash
cd ~/projects/tien/atin_tran_han_industry/poc/backend
.venv/bin/python scripts/convert_onnx_fp16.py
ls -lh ../models/
```
*(Kỳ vọng thấy `[OK] Đã lưu model FP16: .../poc/models/yolo26s_fp16.onnx`).*

### Bước 4.3: Chạy nhanh bộ unit test xác nhận môi trường Backend trên `aiot`
```bash
cd ~/projects/tien/atin_tran_han_industry/poc/backend
.venv/bin/pytest -v
```
*(Kỳ vọng: `18 passed`).*

---

## 7. Giai Đoạn 5 — Tạo File Cấu Hình `poc/backend/.env`

```bash
cd ~/projects/tien/atin_tran_han_industry/poc/backend
cat > .env << 'EOF'
# --- Server & Single-Port (Next.js UI + FastAPI + WS + MJPEG chung 1 cổng) ---
APP_NAME="ATIN Tran Han AI Backend"
ENVIRONMENT=poc
DEBUG=false
PORT=28080
API_V1_PREFIX=/api/v1
PROJECT_DISPLAY_NAME="Nhà máy Thủy sản Trần Hân"
SERVE_FRONTEND=true
FRONTEND_DIR=../frontend/out
FRONTEND_LEGACY_DIR=../frontend

# --- NVR Nhà máy Thủy sản Trần Hân (DDNS Direct Mode) ---
NVR_HOST=nmts2025.smartddns.tv
NVR_PORT=80
NVR_USER=user
NVR_PASS=testcam@123
NVR_STREAM_FPS_LIMIT=12.0

# --- AI Core trên GPU RTX A400 (4GB VRAM -> Cap 1024 MB) ---
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
AI_CONFIRM_SECONDS=2.0
AI_EVENT_COOLDOWN_SECONDS=60.0
WS_PUSH_MAX_HZ=15.0
EOF
```

---

## 8. Giai Đoạn 6 — Build Next.js Static Export & Khởi Chạy Bằng 1 Lệnh Duy Nhất

```bash
cd ~/projects/tien/atin_tran_han_industry/poc/backend
chmod +x scripts/run_server.sh

# Chạy lần đầu kèm cờ --build: tự cài node_modules (nếu thiếu), build poc/frontend/out/ và chạy Uvicorn trên :28080
./scripts/run_server.sh --build
```

### Dấu hiệu khởi động thành công trên màn hình Termius
1. `[1/2] Đang build giao diện Next.js Static Export (poc/frontend/out)...` → kết thúc với `✓ Exporting (2/2)`.
2. `[2/2] Đang khởi động ATIN Trần Hân PoC (FastAPI + Next.js + GPU AI) tại http://0.0.0.0:28080 ...`
3. Log AI Core hiển thị:
   `Loaded YOLO ONNX model=yolo26s_fp16.onnx active_provider=CUDAExecutionProvider ...`
4. `Uvicorn running on http://0.0.0.0:28080 (Press CTRL+C to quit)`

### Cách dừng an toàn (Bắt buộc trên server dùng chung)
- Nhấn **`Ctrl + C`** 1 lần trực tiếp trên cửa sổ Termius đang chạy `./scripts/run_server.sh`.
- Nhờ `exec uv run --no-sync uvicorn ... --timeout-graceful-shutdown 2` và cơ chế shutdown trong `lifespan`, toàn bộ WebSocket, luồng AI, kết nối NVR và VRAM GPU được giải phóng sạch trong `<= 2 giây`.
- Có thể kiểm tra lại bằng `nvidia-smi` và `ss -tulpn | grep 28080`.

*(Nếu muốn kiểm tra nhanh bằng `curl` ở một tab SSH thứ hai trong khi server đang chạy)*:
```bash
curl -s http://127.0.0.1:28080/api/v1/health
curl -s http://127.0.0.1:28080/api/v1/config | python3 -m json.tool
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
```

---

## 9. Giai Đoạn 7 — Test Từ Laptop Qua Termius Port Forwarding (`28080`)

### Bước 7.1: Cấu hình Local Port Forwarding trên Termius
Trong mục **Port Forwarding** của Termius (có thể dùng lại rule `28080` của dự án trước):

| Trường | Giá trị |
| :--- | :--- |
| **Type** | `Local` |
| **Host** | `aiot` (`tts@192.168.1.170`) |
| **Local Port** | `28080` |
| **Bind Address** | `127.0.0.1` |
| **Destination Host** | `127.0.0.1` |
| **Destination Port** | `28080` |

### Bước 7.2: Mở trình duyệt trên Laptop & Checklist kiểm thử trước khi báo IT
Truy cập các URL sau trên trình duyệt laptop:
- **Giao diện chính (Next.js Live View)**: `http://localhost:28080`
- **Swagger API Docs**: `http://localhost:28080/docs`
- **Healthcheck**: `http://localhost:28080/api/v1/health`

**Checklist xác nhận đạt chuẩn trước khi xin Public Port `28080`**:
- [ ] Cả 4 camera (`Tăng trọng 1`, `Tăng trọng 2`, `Tăng trọng 3`, `Định hình 2`) hiển thị mượt, badge góc trên-phải báo `Trực tiếp`.
- [ ] `GET http://localhost:28080/api/v1/config` trả về `"active_provider": "CUDAExecutionProvider"`.
- [ ] `nvidia-smi` trên `aiot` cho thấy tiến trình Python tiêu thụ **`<= 1024 MiB` VRAM**.
- [ ] BBox nhân viên di chuyển bám sát khung hình (không bị trễ pha Kalman, không bị treo bóng ma). Nhân viên trong vùng vẽ viền xanh lá `Nhân viên #ID` + chấm chân; nhân viên ngoài vùng làm mờ `#ID`.
- [ ] Kiểm tra đủ 3 màu HUD:
  - 🟢 **Xanh lá**: `CÓ NHÂN VIÊN` (`{N} người trong vùng`) và chuyển nhanh sang `Vừa rời khỏi vùng` trong `2s` khi vừa rời vùng.
  - 🟡 **Vàng**: `VÙNG TRỐNG` (`không có người 00:02` → `00:11`).
  - 🔴 **Đỏ**: `KHÔNG CÓ NHÂN VIÊN` (`Cảnh báo · vùng trống 00:12`), viền đỏ `3px` quanh toàn khung camera, tăng `Số lần cảnh báo`, cộng dồn `Tổng thời gian cảnh báo`, và vẽ đúng dải màu trên `Dòng thời gian (30p gần nhất)`.
- [ ] Kiểm tra nút **Phóng to (Focus Modal)** → chuyển `Luồng chính / Luồng phụ`, bấm **Reset thống kê**, thử **Vẽ vùng**, và mở tab **Video & Tách frame**.
- [ ] Mở DevTools (`F12` → tab **Network** & **Console**): xác nhận WebSocket `ws://localhost:28080/api/v1/ws/detections` kết nối trạng thái `101 Switching Protocols`, không có lỗi đỏ 404/500.

---

## 10. Giai Đoạn 8 — Bàn Giao Cho IT Công Ty Mở Port Public `28080`

Sau khi test qua Termius đạt 100% checklist ở trên, gửi yêu cầu cho bộ phận IT / Hạ tầng công ty với thông tin sau:

- **Server đích (LAN)**: `192.168.1.170` (`aiot`)
- **Port cần mở / NAT / Reverse Proxy**: **Duy nhất 1 cổng TCP `28080`**
- **Giao thức đi qua cổng `28080`**: HTTP/1.1 (Next.js UI + REST API + MJPEG stream) và WebSocket (`Upgrade: websocket` tại `/api/v1/ws/detections`).
- **Không cần sửa bất kỳ dòng code nào**: Frontend dùng 100% Relative URL (`/api/v1/...`) và tự nhận diện `ws://` (HTTP) hoặc `wss://` (HTTPS) theo `window.location.host`.

### Nếu IT công ty cấu hình Nginx Reverse Proxy gắn Domain HTTPS (ví dụ `https://tranhan-poc.atin.vn`)
Gửi kèm block cấu hình Nginx chuẩn sau để WebSocket và luồng MJPEG không bị nghẽn buffer:

```nginx
location / {
    proxy_pass http://192.168.1.170:28080;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # Bắt buộc cho WebSocket BBox realtime (/api/v1/ws/detections)
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";

    # Bắt buộc cho luồng video MJPEG mượt, không bị buffer trễ
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600s;
}
```

### Nếu IT yêu cầu đổi sang một port khác (ví dụ `28090`)
Chỉ cần sửa đúng 1 dòng `PORT=28090` trong `poc/backend/.env` rồi chạy lại `./scripts/run_server.sh`.

---

## 11. Quy Trình Cập Nhật Code Nhanh Hằng Ngày (Chỉ ~10 Giây)

Mỗi khi cập nhật code mới và `git push origin jin` từ laptop, trên `aiot` chỉ cần chạy:

```bash
cd ~/projects/tien/atin_tran_han_industry && git pull origin jin
cd poc/backend && ./scripts/run_server.sh --build
```
*(Nếu chỉ sửa Backend Python mà không sửa Frontend Next.js, bỏ cờ `--build` để khởi chạy trong ~2 giây: `./scripts/run_server.sh`).*

---

## 12. Xử Lý Sự Cố Thường Gặp (Troubleshooting)

| Triệu chứng | Nguyên nhân | Cách xử lý chuẩn |
| :--- | :--- | :--- |
| `Providers: ['CPUExecutionProvider']` (không có CUDA) | Gói `onnxruntime` CPU ghi đè binary của `onnxruntime-gpu`, hoặc thiếu thư viện CUDA runtime trong `.venv` | Chạy `uv pip install --python .venv/bin/python --force-reinstall --no-deps onnxruntime-gpu`. Kiểm tra `nvidia-smi` và biến `LD_LIBRARY_PATH` (nếu cần dùng `cudnn` từ pip: `uv pip install --python .venv/bin/python nvidia-cudnn-cu12 nvidia-cublas-cu12`). |
| `ImportError: libGL.so.1: cannot open shared object file` | `supervision` kéo theo `opencv-python` (bản GUI) trên server Ubuntu không có X11/OpenGL | Chạy trong `poc/backend`: `uv pip uninstall --python .venv/bin/python opencv-python && uv pip install --python .venv/bin/python --force-reinstall opencv-python-headless`. |
| `ERROR: [Errno 98] Address already in use` trên cổng `28080` | Một tiến trình khác (hoặc `tmux` cũ) đang chiếm cổng `28080` | Chạy `ss -tulpn \| grep 28080` hoặc `tmux ls` để xác định PID/session, dừng tiến trình cũ trước khi chạy lại. |
| `./scripts/run_server.sh: /usr/bin/env: 'bash\r': No such file or directory` | Git trên Windows tự đổi LF thành CRLF khi checkout | Chạy 1 lần trên `aiot`: `sed -i 's/\r$//' poc/backend/scripts/run_server.sh`. |
| `npm run build` lỗi cú pháp hoặc báo `Node version` | Đang dùng `node` mặc định của Ubuntu 22.04 (v12) thay vì Node 20 | Chạy `source ~/.bashrc && node -v` xác nhận `>= v20.x.x` (xem **Giai đoạn 2**). |
| Trình duyệt tải được UI nhưng video báo `Mất tín hiệu` | Server `aiot` không ra được Internet tới `nmts2025.smartddns.tv:80` hoặc NVR Trần Hân đang quá tải | Test trực tiếp từ `aiot`: `curl -I --digest -u 'user:testcam@123' 'http://nmts2025.smartddns.tv:80/cgi-bin/snapshot.cgi?channel=16'`. Nếu trả `200 OK` là mạng thông. |
| `YOLO model not found` trong log | Chưa upload file `yolo26s_best.onnx` (do `.gitignore` chặn `*.onnx`) | Thực hiện lại **Bước 3.2** (`scp`) và **Bước 4.2** (`convert_onnx_fp16.py`). |

# Hướng Dẫn Triển Khai PoC v001 Bằng Docker Compose Trên Server GPU `aiot` (`tts@aiot:~/projects/tien$`)

> **Mục tiêu**: Đóng gói trọn bộ **ATIN Trần Hân AI PoC v001** (Next.js Static Export + FastAPI + AI GPU `onnxruntime-gpu` CUDA 12 + ByteTrack) vào **1 container Docker duy nhất (`tranhan_ai_poc`)** đặt ngay tại thư mục gốc **`poc/`**, chạy trên cổng **`28080` (`https://tranhan.atin.vn/`)**:
> 1. **Cô lập 100% môi trường** bằng Docker Compose (`poc/Dockerfile` + `poc/docker-compose.yml`), không dùng bất kỳ file `.sh` nào để chạy, xem log hay dừng server.
> 2. **Tương thích 100% với port `28080` đã được công ty mở ra `https://tranhan.atin.vn/`** — không cần báo IT sửa cấu hình mạng/domain.
> 3. Toàn bộ vận hành thực hiện ngay tại thư mục **`~/projects/tien/atin_tran_han_industry/poc`** bằng 4 lệnh Docker chuẩn:
>    - Khởi chạy / Build lại: **`docker compose up -d --build`**
>    - Xem log realtime: **`docker compose logs -f --tail=50`**
>    - Xem trạng thái: **`docker compose ps`**
>    - Dừng sạch toàn bộ (1 lệnh duy nhất): **`docker compose down`**

---

## 1. Thông Số Hạ Tầng & Cấu Trúc Docker Tại `poc/`

| Hạng mục | Giá trị thực tế |
| :--- | :--- |
| **SSH Server** | `tts@192.168.1.170` (Hostname: `aiot`, Ubuntu 22.04.5 LTS) |
| **Thư mục đứng chạy Docker** | **`~/projects/tien/atin_tran_han_industry/poc`** |
| **File cấu hình Docker** | `poc/Dockerfile`, `poc/docker-compose.yml`, `poc/.dockerignore` |
| **Tên Container** | `tranhan_ai_poc` |
| **GPU & Giới hạn VRAM** | NVIDIA RTX A400 (**4 GB VRAM**) — Container giới hạn **`AI_VRAM_LIMIT_MB=1024`** (~400 MB thực tế) |
| **Port dịch vụ duy nhất** | **`28080:28080`** (Ăn khớp trực tiếp với **`https://tranhan.atin.vn/`**) |
| **Model AI sử dụng** | `poc/models/yolo26s.onnx` (Fine-tune `factory_person_dataset`, `names = {0: 'person'}`) |
| **NVR Trần Hân (DDNS)** | `nmts2025.smartddns.tv:80` · User: `user` · Pass: `testcam@123` (Kênh `16, 17, 18, 21`) |

```text
poc/
├── Dockerfile                # Multi-stage: Stage 1 (node:20-alpine build Next.js) -> Stage 2 (nvidia/cuda:12.4.1-cudnn-runtime)
├── docker-compose.yml        # Cấu hình container tranhan_ai_poc (port 28080:28080, gpus: all, volumes)
├── .dockerignore             # Loại bỏ .venv, node_modules, caches khỏi Docker build context
├── backend/                  # Mã nguồn FastAPI + AI Core + file .env
├── frontend/                 # Mã nguồn Next.js App Router + TypeScript + Tailwind CSS
├── models/                   # Chứa yolo26s.onnx & yolo26s.pt (mount read-only vào /app/models)
├── data/                     # Chứa cameras.json (mount read-write vào /app/data để lưu tọa độ đa giác)
└── storages/                 # Chứa videos/ & frames/ (mount read-write vào /app/storages)
```

---

## 2. Bước 1 — Trên Laptop Windows: Push Code Lên GitHub & Kéo Model Mới Lên `aiot` Qua SFTP

1. Mở PowerShell trên Laptop Windows push code mới lên nhánh `jin`:
   ```powershell
   cd E:\ATIN\atin_tran_han_industry
   git add poc/
   git commit -m "feat(poc): dockerize full PoC at poc/ root, use factory person yolo26s.onnx and transparent HUD"
   git push origin jin
   ```

2. Mở tab **SFTP trên Termius**, kéo 2 file model mới trong `E:\ATIN\atin_tran_han_industry\poc\models\` (**`yolo26s.onnx`** và **`yolo26s.pt`**) thả vào thư mục trên server `aiot`:
   ```text
   /home/tts/projects/tien/atin_tran_han_industry/poc/models/
   ```
   *(Hoặc dùng lệnh `scp` từ PowerShell Laptop Windows)*:
   ```powershell
   scp E:\ATIN\atin_tran_han_industry\poc\models\yolo26s.onnx E:\ATIN\atin_tran_han_industry\poc\models\yolo26s.pt tts@192.168.1.170:/home/tts/projects/tien/atin_tran_han_industry/poc/models/
   ```

---

## 3. Bước 2 — Trên Server `aiot`: Pull Code, Giải Phóng Cổng `28080` & Kiểm Tra GPU Docker

SSH vào `tts@192.168.1.170` trên Termius:

### 3.1. Pull code mới & Dừng tiến trình non-Docker cũ đang giữ cổng `28080` (Chỉ làm 1 lần khi chuyển sang Docker)

```bash
cd ~/projects/tien/atin_tran_han_industry && git pull origin jin
```
```bash
# Giải phóng cổng 28080 từ tiến trình chạy nền cũ (nếu đang chạy)
fuser -k 28080/tcp 2>/dev/null || true
rm -f ~/projects/tien/atin_tran_han_industry/poc/backend/logs/server.pid
```
```bash
# Xóa 2 file model PPE cũ (yolo26s_best.onnx / yolo26s_fp16.onnx) để chỉ dùng yolo26s.onnx mới
rm -f ~/projects/tien/atin_tran_han_industry/poc/models/yolo26s_best.onnx ~/projects/tien/atin_tran_han_industry/poc/models/yolo26s_fp16.onnx
ls -lh ~/projects/tien/atin_tran_han_industry/poc/models/
```
*(Xác nhận trong `poc/models/` có file `yolo26s.onnx` ~36.4 MB).*

### 3.2. Về file `poc/backend/.env` hiện tại trên server `aiot` (KHÔNG BẮT BUỘC PHẢI SỬA)
File `poc/backend/.env` hiện tại trên server của bạn **có thể giữ nguyên 100% mà không cần sửa** vì trong `poc/docker-compose.yml` mục `environment:` (vốn có độ ưu tiên cao hơn `env_file:` trong Docker Compose) đã tự động ghi đè các biến quan trọng cho container:
- `APP_NAME: "ATIN Smart Fishing"`
- `PROJECT_DISPLAY_NAME: "ATIN Smart Fishing"`
- `MODEL_PATH: /app/models/yolo26s.onnx`
- `FRONTEND_DIR: /app/frontend/out`
- `CAMERAS_FILE: /app/data/cameras.json`
- `STORAGES_DIR: /app/storages`

*(Tùy chọn: Nếu muốn cập nhật luôn file `poc/backend/.env` trên server cho đồng bộ hoặc khi cài trên máy mới chưa có `.env`, bạn có thể chạy lệnh sau)*:

```bash
cat > ~/projects/tien/atin_tran_han_industry/poc/backend/.env << 'EOF'
APP_NAME="ATIN Smart Fishing"
ENVIRONMENT=poc
DEBUG=false
PORT=28080
API_V1_PREFIX=/api/v1
PROJECT_DISPLAY_NAME="ATIN Smart Fishing"
SERVE_FRONTEND=true
FRONTEND_DIR=../frontend/out
FRONTEND_LEGACY_DIR=../frontend
RATE_LIMIT_PER_MINUTE=1800

NVR_HOST=nmts2025.smartddns.tv
NVR_PORT=80
NVR_USER=user
NVR_PASS=testcam@123
NVR_STREAM_FPS_LIMIT=12.0

AI_ENABLED=true
MODEL_PATH=../models/yolo26s.onnx
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

### 3.3. Kiểm tra `nvidia-container-toolkit` trên `aiot`
Kiểm tra xem Docker trên `aiot` đã kích hoạt runtime NVIDIA chưa:
```bash
docker info | grep -i nvidia || true
```
- **Nếu có hiện chữ `nvidia`**: Server `aiot` đã có sẵn `nvidia-container-toolkit`, chuyển thẳng sang **Bước 3**.
- **Nếu chưa hiện gì**: Cài plugin `nvidia-container-toolkit` (~10 MB) trong 15 giây:
  ```bash
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
  sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
  sudo nvidia-ctk runtime configure --runtime=docker
  sudo systemctl restart docker
  ```

---

## 4. Bước 3 — Build & Khởi Chạy Bằng Docker Compose Ngay Tại `poc/`

Đứng trực tiếp tại thư mục **`~/projects/tien/atin_tran_han_industry/poc`**:

```bash
cd ~/projects/tien/atin_tran_han_industry/poc
docker compose up -d --build
```

- Container `tranhan_ai_poc` sẽ tự động:
  1. Build Next.js Static Export (`poc/frontend/out`) bằng Node 20 trong Stage 1.
  2. Chạy FastAPI + `onnxruntime-gpu` trên image `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04` trong Stage 2.
  3. Mở đúng cổng **`0.0.0.0:28080`**, kết nối ngay lập tức với domain **`https://tranhan.atin.vn/`**.
- Sau khi `docker compose up -d --build` báo `Started`, bạn có thể **tắt cửa sổ Termius thoải mái**, hệ thống tự chạy 24/7.

---

## 5. Bốn Lệnh Quản Lý Hằng Ngày Bằng Docker Compose (Tại `~/projects/tien/atin_tran_han_industry/poc`)

Không sử dụng bất kỳ file `.sh` nào — đứng tại `~/projects/tien/atin_tran_han_industry/poc`:

### 1. Xem log trực tiếp (Real-time Logs)
```bash
cd ~/projects/tien/atin_tran_han_industry/poc
docker compose logs -f --tail=50
```
*(Kỳ vọng thấy dòng `Loaded YOLO ONNX model=yolo26s.onnx classes={0: 'person'} active_provider=CUDAExecutionProvider` · Bấm `Ctrl + C` để thoát xem log, container vẫn chạy nền).*

### 2. Kiểm tra trạng thái Container & Mức dùng VRAM GPU
```bash
cd ~/projects/tien/atin_tran_han_industry/poc
docker compose ps
nvidia-smi
```

### 3. Cập nhật code mới từ GitHub (Continuous Update)
```bash
cd ~/projects/tien/atin_tran_han_industry && git pull origin jin
cd ~/projects/tien/atin_tran_han_industry/poc && docker compose up -d --build
```

### 4. Dừng sạch toàn bộ hệ thống khi kết thúc PoC (1 Lệnh Duy Nhất)
```bash
cd ~/projects/tien/atin_tran_han_industry/poc
docker compose down
```
*(Lệnh `docker compose down` sẽ dừng và gỡ sạch container `tranhan_ai_poc`, giải phóng 100% cổng `28080` và toàn bộ VRAM trên RTX A400 mà không ảnh hưởng tới container của bất kỳ dev nào khác trên `aiot`).*

---

## 6. Kiểm Thử Nghiệm Thu Trực Tiếp Trên `https://tranhan.atin.vn/`

1. Mở **`https://tranhan.atin.vn/`** trên trình duyệt (không cần bật OpenVPN).
2. Kiểm tra `https://tranhan.atin.vn/api/v1/config` xác nhận `"active_provider": "CUDAExecutionProvider"`.
3. Quan sát trên 4 khung hình camera:
   - Khung **HUD góc trên-trái đã nhỏ gọn và trong suốt (`alpha 0.44`)**, nhìn xuyên thấu thấy rõ đường đa giác Poly Zone và công nhân đi lại phía sau.
   - Nhãn Pill của Polygon tự động đặt ở đỉnh ngoài vùng HUD, không bị HUD đè chữ.
   - Khi có công nhân trong vùng: BBox xanh lá `#22C55E` (`Nhân viên #ID` + chấm chân) bám sát người thật, HUD chuyển 🟢 **`CÓ NHÂN VIÊN`** (`{N} người trong vùng`).
   - Khi công nhân rời vùng: chuyển `Vừa rời khỏi vùng` (`2s`) → 🟡 **`VÙNG TRỐNG`** (`10s`) → 🔴 **`KHÔNG CÓ NHÂN VIÊN`** + viền đỏ `3px`.

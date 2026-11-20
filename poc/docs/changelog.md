# Changelog — ATIN Trần Hân Industry PoC (`poc/`)

Tài liệu ghi nhận toàn bộ lịch sử thay đổi, nâng cấp kiến trúc và sửa lỗi của hệ thống PoC (`poc/backend` + `poc/frontend` + `poc/Dockerfile` + `poc/docker-compose.yml`).

---

## [0.2.2] - 2026-11-20 — Optimization v4 (Zero-Wait MJPEG), GridFrameCache, SQLite WAL & Docker BuildKit

### Added
- **Tối ưu hiệu năng & Streaming (`GridFrameCache`, `Auto-FP16`, `JIT Overlap Prefetch`)**:
  - `poc/backend/app/ai/grid_cache.py`: Cache JPEG theo nhu cầu (demand-driven) dành riêng cho Grid View (`854px`, `Q=68`, `X-Stream-Source: ram-grid-cache`), giải phóng băng thông và CPU khỏi asyncio event loop; Focus View giữ passthrough trực tiếp `ram-direct`.
  - `PersonZoneDetector` (`worker.py`): JIT fetch + 1-cam overlap prefetch (`ThreadPoolExecutor(max_workers=1)`), skip AI với camera chưa vẽ zone.
  - `YoloPersonDetector` (`detector.py`): Tự động nhận diện input dtype FP16/FP32 từ ONNX và warmup pass; `AI_VRAM_LIMIT_MB=1536`.
  - Endpoint `GET /api/v1/metrics` và script `scripts/export_app_logs.py`, `scripts/probe_nvr.py`, `scripts/bench_decode.py`, `scripts/bench_infer.py`.
- **Lưu trữ SQLite WAL (`poc/backend/app/db/sqlite_store.py`, `sqlite_camera_repository.py`)**:
  - Chuyển cấu hình camera, lịch sử cảnh báo (`alert_events`, retention 90 ngày) và `runtime_snapshots` sang SQLite WAL (`tranhan_poc.db`) với async writer thread, tự migrate từ `cameras.json`.
- **Docker BuildKit Layer Caching (`poc/Dockerfile`, `poc/backend/requirements/docker.txt`, `poc/.dockerignore`)**:
  - Tách manifest `requirements/docker.txt` (`onnxruntime-gpu==1.23.2`, `opencv-python-headless==5.1.0.95`, `supervision==0.27.0.post2`) và cài đặt trước khi copy `app/`/`scripts/`, dùng cache mount BuildKit cho `npm`, `.next/cache` và `pip`.

### Changed & Fixed
- **Zero-Wait MJPEG & Tách WebSocket (`ws_hub.py`, `ws-client.ts`, `detection-store.ts`)**: Tách message `bbox` (tức thì) và `hud`/`timeline` (`1s`/`2s`), coalescing latest-wins ở server; nâng `BBOX_STALE_SECONDS=1.8`.
- **Tinh chỉnh AI & Giao diện Live View (`config.py`, `CameraOverlayCanvas.tsx`, `CameraCard.tsx`, `FocusModal.tsx`)**:
  - Đặt mặc định `AI_CONF_THRESHOLD=0.55`, `AI_ANCHOR_MODE=center`.
  - BBox trong vùng xanh lá (`#22C55E`), ngoài vùng xám (`#94A3B8`, `globalAlpha=0.42`, `1.25px`) kèm nhãn `%` độ tin cậy, ẩn chấm tròn anchor.
  - Ẩn badge `"Trực tiếp"` trên `CameraCard` khi đang live bình thường; bỏ xóa `img.src` khi unmount tránh lỗi stream giả; ngắt MJPEG khi mở Zone Editor; nâng cấp `FocusModal` sang Fullscreen API (`requestFullscreen()`).

---

## [0.2.1] - 2026-11-20 — Model Công Nhân Nhà Máy Mới, Sửa Lỗi Ẩn BBox, HUD Trong Suốt & Đóng Gói Docker Tại `poc/`

### Added
- **Docker hóa toàn diện tại thư mục gốc `poc/` ([poc/Dockerfile](file:///e:/ATIN/atin_tran_han_industry/poc/Dockerfile), [poc/docker-compose.yml](file:///e:/ATIN/atin_tran_han_industry/poc/docker-compose.yml), [poc/.dockerignore](file:///e:/ATIN/atin_tran_han_industry/poc/.dockerignore))**:
  - **Multi-stage build**:
    - Stage 1 (`node:20-alpine`): Tự động cài dependencies và build Next.js Static Export ra `/build/frontend/out`.
    - Stage 2 (`nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04`): Tích hợp sẵn CUDA 12.4 + cuDNN 9 chính hãng NVIDIA, cài FastAPI + `onnxruntime-gpu==1.23.2` + `opencv-python-headless`.
  - Chạy gọn trong 1 container duy nhất `tranhan_ai_poc`, map cổng **`28080:28080`** khớp 100% với cấu hình cứng `https://tranhan.atin.vn/` của IT công ty.
  - Vận hành thuần bằng lệnh chuẩn `docker compose up -d --build`, `docker compose logs -f`, và dừng sạch 100% bằng 1 lệnh `docker compose down` ngay tại `poc/` (loại bỏ sự phụ thuộc vào script `.sh`).
- **Tích hợp bộ Model nhận diện công nhân nhà máy mới ([poc/models/yolo26s.onnx](file:///e:/ATIN/atin_tran_han_industry/poc/models/yolo26s.onnx) & `yolo26s.pt`)**:
  - Model fine-tune riêng trên `factory_person_dataset/data.yaml` với output `[1, 5, 8400]`, 1 class duy nhất `{0: 'person'}` (thay thế file `yolo26s_best.onnx` cũ vốn là model PPE 7 class `glove/hairnet/mask` không có class `person`).
  - Bổ sung ghi log metadata `classes={0: 'person'}` trong [detector.py](file:///e:/ATIN/atin_tran_han_industry/poc/backend/app/ai/detector.py) khi nạp ONNX session.

### Changed
- **Đổi toàn bộ Brand Name thành `ATIN Smart Fishing` ([Topbar.tsx](file:///e:/ATIN/atin_tran_han_industry/poc/frontend/src/components/Topbar.tsx), [layout.tsx](file:///e:/ATIN/atin_tran_han_industry/poc/frontend/src/app/layout.tsx), [AiBriefModal.tsx](file:///e:/ATIN/atin_tran_han_industry/poc/frontend/src/components/AiBriefModal.tsx), [config.py](file:///e:/ATIN/atin_tran_han_industry/poc/backend/app/core/config.py), [docker-compose.yml](file:///e:/ATIN/atin_tran_han_industry/poc/docker-compose.yml))**:
  - Cập nhật tiêu đề thương hiệu trên Topbar, tiêu đề tab trình duyệt (`ATIN Smart Fishing — Giám sát AI`), modal Bài toán AI và cấu hình Backend (`APP_NAME`, `PROJECT_DISPLAY_NAME`).
- **Thu nhỏ & Tăng độ trong suốt khung HUD ([ZoneHudOverlay.tsx](file:///e:/ATIN/atin_tran_han_industry/poc/frontend/src/components/ZoneHudOverlay.tsx), [globals.css](file:///e:/ATIN/atin_tran_han_industry/poc/frontend/src/app/globals.css))**:
  - Giảm độ đặc nền `--surface-hud` từ `rgba(15, 23, 42, 0.82)` xuống **`rgba(15, 23, 42, 0.44)`** kết hợp `backdrop-blur-[3px]` và bóng chữ `[text-shadow:0_1px_2px_rgba(0,0,0,0.85)]` để nhìn xuyên thấu rõ ràng vùng đa giác Poly Zone và công nhân phía sau HUD.
  - Thu gọn kích thước khung HUD (`max-w-[214px]` ở chế độ lưới 4/6 camera, `max-w-[262px]` ở chế độ phóng to 1 camera).
- **Tránh chồng lấp nhãn Polygon với khung HUD ([CameraOverlayCanvas.tsx](file:///e:/ATIN/atin_tran_han_industry/poc/frontend/src/components/CameraOverlayCanvas.tsx))**:
  - Tự động chọn đỉnh cao nhất nằm ngoài vùng góc trên-trái của HUD để vẽ nhãn Pill trạng thái Polygon (`TĂNG TRỌNG 2 · ...`), tránh hiện tượng HUD đè lên một nửa nhãn Polygon.
- **Cập nhật hướng dẫn triển khai ([poc/docs/deploy.md](file:///e:/ATIN/atin_tran_han_industry/poc/docs/deploy.md))**:
  - Chuyển toàn bộ quy trình vận hành trên `tts@aiot:~/projects/tien$` sang Docker Compose đặt tại `poc/`.

### Fixed
- **Sửa lỗi mất BBox trên trình duyệt do lệch đồng hồ Server vs Client (`Clock Skew`) ([detection-store.ts](file:///e:/ATIN/atin_tran_han_industry/poc/frontend/src/lib/detection-store.ts), [CameraOverlayCanvas.tsx](file:///e:/ATIN/atin_tran_han_industry/poc/frontend/src/components/CameraOverlayCanvas.tsx))**:
  - Đóng dấu thời gian nhận thực tế tại trình duyệt (`_client_ts = Date.now() / 1000`) khi nhận bản tin WebSocket `/api/v1/ws/detections`, thay vì lấy `Date.now()` của máy khách trừ `updated_at` (`time.time()`) của server `aiot` (tránh việc đồng hồ server chậm hơn máy khách `> 1.5s` làm Canvas xóa nhầm toàn bộ BBox).
- **Sửa lỗi tăng `seq` trùng lặp khi chưa decode frame BGR mới ([nvr_stream.py](file:///e:/ATIN/atin_tran_han_industry/poc/backend/app/ai/nvr_stream.py))**:
  - Chỉ tăng `self._seq` khi thực sự giải mã frame BGR mới cho AI Worker, tránh việc AI chạy suy luận lặp lại trên frame cũ.
- **Tương thích Python 3.10 mặc định của Ubuntu 22.04 trong container CUDA ([pyproject.toml](file:///e:/ATIN/atin_tran_han_industry/poc/backend/pyproject.toml), [common.py](file:///e:/ATIN/atin_tran_han_industry/poc/backend/app/schemas/common.py), [poc/Dockerfile](file:///e:/ATIN/atin_tran_han_industry/poc/Dockerfile))**:
  - Hạ `requires-python = ">=3.10"` và dùng `timezone.utc` thay cho `datetime.UTC` để tương thích với `/usr/bin/python3` (`3.10.12`) trong base image `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04`.
  - Bổ sung bước kiểm tra `python3 -c "import uvicorn, fastapi, cv2, onnxruntime, supervision, app.main"` ngay trong quá trình `docker build`.

---

## [0.2.0] - 2026-11-19 — Kiến Trúc PoC v001 Single-Port (FastAPI + Next.js Static Export + GPU AI Core)

### Added
- **Frontend Next.js App Router + TypeScript + Tailwind CSS ([poc/frontend/](file:///e:/ATIN/atin_tran_han_industry/poc/frontend))**:
  - Cấu hình `output: 'export'` xuất tĩnh ra `poc/frontend/out/` để FastAPI phục vụ trực tiếp trên cùng cổng `28080`.
  - Áp dụng hệ thống thiết kế hợp nhất **ATIN IOC Platform × Soft Clean Cards** ([04_DESIGN_SYSTEM.md](file:///e:/ATIN/atin_tran_han_industry/poc/docs/pocv001/04_DESIGN_SYSTEM.md)).
  - Kiến trúc **Dual-Speed Rendering**: External Store (`detection-store.ts`) tách luồng vẽ `<CameraOverlayCanvas />` 15 FPS bằng `requestAnimationFrame` (**0 React re-render**) khỏi luồng cập nhật `<ZoneHudOverlay />` ở nhịp 1 Hz.
  - Đầy đủ công cụ Vẽ vùng giám sát (`ZoneEditor`), phóng to camera (`FocusModal`), đặt lại thống kê (`Reset thống kê`), ghi hình `.mp4` (5/10/20 phút) và trang quản lý/tách bộ frame Dataset (`DatasetView`).
- **Bộ đọc luồng NVR chia sẻ trong RAM ([nvr_stream.py](file:///e:/ATIN/atin_tran_han_industry/poc/backend/app/ai/nvr_stream.py))**:
  - Duy trì 1 kết nối HTTP Digest Auth duy nhất trên mỗi kênh camera tới `nmts2025.smartddns.tv:80` (ưu tiên luồng MJPEG `/cgi-bin/mjpg/video.cgi`, tự động fallback sang `/cgi-bin/snapshot.cgi`), chia sẻ frame trong RAM cho cả AI Core và endpoint `GET /api/v1/cameras/{cam_id}/mjpeg`.
- **Theo dõi đối tượng & Máy trạng thái 4 trạng thái ([tracker.py](file:///e:/ATIN/atin_tran_han_industry/poc/backend/app/ai/tracker.py), [rule_engine.py](file:///e:/ATIN/atin_tran_han_industry/poc/backend/app/ai/rule_engine.py), [ws_hub.py](file:///e:/ATIN/atin_tran_han_industry/poc/backend/app/services/ws_hub.py))**:
  - `CameraTracker` tích hợp `supervision.ByteTrack` kèm thuật toán `_snap_box_to_raw(min_iou=0.45)` khử trễ pha Kalman Filter.
  - `ZoneRuleEngine` kiểm tra điểm chân `(foot_x, foot_y)` trong đa giác với 4 trạng thái (`present`, `leaving`, `empty`, `alert`) → 3 màu UI (`green`, `yellow`, `red`) và Rolling Timeline 30 phút.
  - `DetectionWsHub` đẩy kết quả realtime qua `WS /api/v1/ws/detections`.

---

## [0.1.0] - 2026-11-19 — Khởi Tạo Khung `poc/backend` Chuẩn Clean Architecture

### Added
- Dựng khung `poc/backend/` theo chuẩn `fastapi-backend-scaffold` (`api/v1`, `middlewares`, `core`, `models`, `schemas`, `db`, `repositories`, `services`, `dependencies`, `exceptions`, `utils`).
- Bổ sung bộ adapter tích hợp ATIN Smart VMS tại `app/integrations/atin_vms/` (`mqtt_orchestrator.py`, `rtsp_reader.py`, `storage_client.py`).

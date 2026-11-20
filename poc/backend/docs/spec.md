# Đặc Tả Kỹ Thuật Backend & AI Core (`poc/backend`)

> Tài liệu đặc tả kiến trúc và hành vi thực tế của `poc/backend` cho **PoC v0.0.1 — ATIN Smart Fishing** (Giám sát nhân sự khu vực chế biến tại Nhà máy Thủy sản Trần Hân).

---

## 1. Kiến trúc phân tầng

Tuân thủ chuẩn `fastapi-backend-scaffold`, tách biệt rõ trách nhiệm giữa HTTP/WS, nghiệp vụ, lưu trữ dữ liệu, luồng video NVR và AI Core:

```text
HTTP / WebSocket Request
  └─► app/middlewares/ (ErrorHandling → CORS → RequestLogging → RateLimit → RequestID)
        └─► app/api/v1/endpoints/ (Controller: validate Pydantic schema, gọi Service)
              ├─► app/services/ws_hub.py (DetectionWsHub: coalescing latest-wins per-client)
              └─► app/services/ (CameraService, DetectionService, MediaService)
                    ├─► app/repositories/ (SqliteCameraRepository [mặc định] | JsonCameraRepository)
                    │     └─► app/db/sqlite_store.py (SQLite WAL + non-blocking writer thread)
                    ├─► app/ai/
                    │     ├─► nvr_stream.py (NvrStreamManager: giữ kết nối MJPEG nền tới NVR)
                    │     ├─► grid_cache.py (GridFrameCache: resize/encode JPEG demand-driven cho Grid View)
                    │     ├─► detector.py (YoloPersonDetector: ONNX Runtime CUDA FP16/FP32 / CPU)
                    │     ├─► tracker.py (CameraTracker: ByteTrack + raw-box IoU snapping)
                    │     ├─► rule_engine.py (ZoneRuleEngine: 4-state zone_presence & zone_intrusion)
                    │     └─► worker.py (PersonZoneDetector: JIT fetch + 1-cam overlap prefetch)
                    └─► app/integrations/atin_vms/ (MQTT Orchestrator, RTSP Reader, Storage API)
```

> **Ghi chú về `app/ai/display_pipeline.py`:** Module `DisplayAndSyncPipeline` được khởi tạo trong `ServiceContainer` (`app/dependencies/container.py`), nhưng hiện `PersonZoneDetector` được cấu hình `display_pipeline=None` để ưu tiên đường truyền zero-wait MJPEG (`GridFrameCache` + `NvrStreamManager`) và đẩy `bbox`/`hud` trực tiếp qua `DetectionWsHub`.

---

## 2. Cấu trúc thư mục thực tế (`poc/backend/`)

| Đường dẫn | Vai trò |
| :--- | :--- |
| `app/main.py` | Khởi tạo FastAPI, lifespan (bind event loop cho `ws_hub`, `nvr_stream_manager`, `grid_cache`, khởi chạy `detection_service`, mount static `frontend/out`) |
| `app/core/config.py` | `Settings` (`pydantic-settings`) đọc `.env`, resolve `model_file_path` (`yolo26s.onnx` -> `yolo26s_best.onnx` -> `yolo26s_fp16.onnx`) và `frontend_path` |
| `app/core/logging.py` | Cấu hình logging chuẩn |
| `app/dependencies/container.py` | `ServiceContainer` singleton (`@lru_cache(maxsize=1)`) gắn kết Repo, Store, Stream, Cache, AI Worker, Services |
| `app/db/sqlite_store.py` | Quản lý SQLite (`WAL`, `synchronous=NORMAL`, `busy_timeout=5000`), writer thread bất đồng bộ (`queue.Queue(maxsize=256)`), bảng `cameras`, `alert_events`, `runtime_snapshots`, `app_settings` |
| `app/repositories/sqlite_camera_repository.py` | CRUD camera/zone trên SQLite, tự động migrate dữ liệu từ `data/cameras.json` khi DB trống |
| `app/repositories/camera_repository.py` | Interface `CameraRepository` và `JsonCameraRepository` (dùng khi `DB_BACKEND=json`) |
| `app/ai/nvr_stream.py` | `NvrStreamManager`: đọc MJPEG dài hạn từ NVR, tách JPEG packet, giữ gói mới nhất trong RAM |
| `app/ai/grid_cache.py` | `GridFrameCache`: chỉ resize & nén JPEG (mặc định `854px`, `Q=68`) khi có viewer Grid kết nối |
| `app/ai/detector.py` | `YoloPersonDetector`: suy luận thuần ONNX Runtime (`class 0 = person`), không phụ thuộc `ultralytics`, tự nhận biết FP16/FP32 từ input tensor |
| `app/ai/tracker.py` | `CameraTracker`: `supervision.ByteTrack` độc lập từng camera trên hệ tọa độ ảo `1280x720`, snap lại BBox gốc nếu `IoU >= AI_SNAP_MIN_IOU` (`0.25`) |
| `app/ai/rule_engine.py` | `ZoneRuleEngine`: state machine 4 trạng thái cho `zone_presence` (`present`, `leaving`, `empty`, `alert`, kèm `idle` khi chưa vẽ vùng) và chế độ `zone_intrusion`; quản lý rolling timeline 30 phút |
| `app/ai/worker.py` | `PersonZoneDetector`: vòng lặp AI ưu tiên camera đang focus hoặc các camera có zone (`len(zone) >= 3`), overlap prefetch 1 camera bằng `ThreadPoolExecutor(max_workers=1)`, phát `bbox` / `hud` qua callback |
| `app/services/ws_hub.py` | `DetectionWsHub`: quản lý WebSocket clients với `_ClientSender` coalescing (latest-wins theo `(msg_type, cam_id)`) |
| `app/services/media_service.py` | Ghi hình `.mp4` (`10 FPS`) từ luồng NVR, quản lý video và tách frame `.jpg` (`skip_frames`: `5` hoặc `10`), nén `.zip` |
| `app/integrations/atin_vms/` | Bộ adapter chuẩn Production cho ATIN Smart VMS (`mqtt_orchestrator.py`, `rtsp_reader.py`, `storage_client.py`) |
| `requirements/docker.txt` | Manifest riêng cho Docker GPU runtime (`onnxruntime-gpu==1.23.2`, `opencv-python-headless==5.1.0.95`, `supervision==0.27.0.post2`) |
| `pyproject.toml` | Khai báo package và dependencies cho phát triển local (`dev`, `gpu`) |

---

## 3. Luồng dữ liệu Video & AI (Zero-Wait Pipeline)

1. **NVR Stream (`NvrStreamManager`)**: Mở kết nối MJPEG (`subtype=0` hoặc `1`) tới NVR (`DigestAuth`), phân tách từng frame JPEG thành `NvrFramePacket` (`seq`, `ts_mono`, `ts_wall`, `jpeg_bytes`).
2. **Grid Cache (`GridFrameCache`)**: Khi `GET /api/v1/cameras/{cam_id}/mjpeg?view=grid` được gọi trên `subtype=0`, cache sẽ resize/encode JPEG (`DISPLAY_GRID_W=854`, `DISPLAY_GRID_Q=68`) trên thread pool riêng và phát chung cho mọi client Grid. Khi xem Focus (`view=focus`), backend passthrough trực tiếp `pkt.jpeg_bytes` gốc từ RAM (`X-Stream-Source: ram-direct`).
3. **AI Inference (`PersonZoneDetector`)**:
   - Bỏ qua camera chưa vẽ zone (`len(zone) < 3`) trừ khi đang được focus.
   - Prefetch 1 camera kế tiếp (`_fetch_and_prepare`: decode JPEG -> letterbox `640x640` -> chuẩn hóa tensor) song song khi GPU đang chạy ONNX cho camera hiện tại.
   - Chạy `YoloPersonDetector` (giới hạn VRAM `AI_VRAM_LIMIT_MB=1536`, `CUDAExecutionProvider` với fallback `CPUExecutionProvider`).
   - Cập nhật `CameraTracker` (ByteTrack) -> đánh giá `ZoneRuleEngine` (mặc định `AI_ANCHOR_MODE=center`, ngưỡng `AI_CONF_THRESHOLD=0.55`).
   - Đẩy `bbox` ngay lập tức qua `DetectionWsHub.publish_bbox_from_thread` và đẩy `hud` (tối đa mỗi `1.0s` hoặc ngay khi đổi trạng thái; kèm `timeline` mỗi `2.0s`) qua `publish_hud_from_thread`.
   - Khi chuyển sang trạng thái `alert` và kết thúc `alert`, ghi bản ghi vào bảng `alert_events` qua `SqliteStore`; định kỳ mỗi `12s` lưu `runtime_snapshots` để khôi phục bộ đếm sau khi khởi động lại.

---

## 4. Danh sách API (`/api/v1`)

| Nhóm | Method | Endpoint | Mô tả |
| :--- | :---: | :--- | :--- |
| **System** | `GET` | `/api/v1/health` | Healthcheck (`{"status": "ok"}`) |
| | `GET` | `/api/v1/config` | Cấu hình runtime, AI provider, ngưỡng presence & WS path |
| | `GET` | `/api/v1/metrics` | Số liệu hiệu năng theo camera (`decode_prep_ms`, `infer_ms`, `track_ms`, `e2e_ms`, grid KB/encode) & `ws_clients` |
| **Cameras** | `GET` | `/api/v1/cameras` | Danh sách camera & zone (hỗ trợ filter `enabled`, `search`) |
| | `POST` | `/api/v1/cameras` | Thêm camera mới (`zone_name`, `feature_type`, `grace_seconds`, `warning_seconds`) |
| | `PUT` | `/api/v1/cameras/{cam_id}` | Cập nhật từng phần thông tin camera |
| | `DELETE` | `/api/v1/cameras/{cam_id}` | Xóa camera |
| | `PUT` | `/api/v1/cameras/{cam_id}/zone` | Lưu tọa độ đa giác (`0..1`) |
| | `GET` | `/api/v1/cameras/{cam_id}/snapshot.jpg` | Proxy ảnh snapshot từ NVR (hỗ trợ `?direct=true`) |
| | `GET` | `/api/v1/cameras/{cam_id}/probe` | Kiểm tra online & độ trễ NVR |
| | `GET` | `/api/v1/cameras/{cam_id}/mjpeg` | Proxy luồng MJPEG (`?subtype=0..2&view=grid\|focus`) |
| **Detections** | `GET` | `/api/v1/detections` | Kết quả nhận diện & trạng thái zone mới nhất theo từng camera |
| | `POST` | `/api/v1/detections/focus` | Đặt camera ưu tiên suy luận (hết hạn sau `15s`) hoặc bỏ (`null`) |
| | `POST` | `/api/v1/detections/{cam_id}/reset-stats` | Reset bộ đếm cảnh báo, timeline và tracker của 1 camera |
| | `GET` | `/api/v1/detections/{cam_id}/events` | Truy vấn lịch sử sự kiện `alert_events` từ SQLite (`from`, `to`, `limit`) |
| | `WS` | `/api/v1/ws/detections`<br>`/api/v1/detections/ws` | Kênh WebSocket realtime nhận `detections`, `bbox`, `hud` và gửi `{"type":"focus"}` |
| **Recording & Dataset** | `POST` | `/api/v1/cameras/{cam_id}/record/start` | Bắt đầu ghi hình `.mp4` (`5`/`10`/`20` phút, `subtype` `0`/`1`) |
| | `POST` | `/api/v1/cameras/{cam_id}/record/stop` | Dừng ghi hình |
| | `GET` | `/api/v1/records/active` | Danh sách phiên ghi hình đang chạy |
| | `GET` | `/api/v1/records/{job_id}` | Tra cứu trạng thái 1 job ghi hình |
| | `GET` | `/api/v1/storages/videos` | Danh sách video đã ghi |
| | `GET` | `/api/v1/storages/videos/{filename}/download` | Tải video `.mp4` |
| | `DELETE` | `/api/v1/storages/videos/{filename}` | Xóa video |
| | `POST` | `/api/v1/storages/videos/{filename}/extract` | Tách frame (`skip_frames`: `5` hoặc `10`) |
| | `GET` | `/api/v1/storages/frames` | Danh sách bộ frame |
| | `GET` | `/api/v1/storages/frames/{folder}/preview/{image_name}` | Xem trước 1 ảnh frame |
| | `GET` | `/api/v1/storages/frames/{folder}/download.zip` | Tải bộ frame dạng `.zip` |
| | `DELETE` | `/api/v1/storages/frames/{folder}` | Xóa bộ frame |

---

## 5. Quản lý Dependencies (`pyproject.toml` vs `requirements/docker.txt`)

- **Phát triển local**: Dùng `poc/backend/pyproject.toml` (kèm `[project.optional-dependencies]` nhóm `dev` và `gpu`).
- **Build Docker GPU (`poc/Dockerfile`)**: Dùng riêng `poc/backend/requirements/docker.txt` để tách layer cài thư viện khỏi mã nguồn `app/` và `scripts/`, đồng thời ghim `onnxruntime-gpu==1.23.2` (không cài `onnxruntime` bản CPU) và thay thế `opencv-python` (do `supervision` kéo theo) bằng `opencv-python-headless==5.1.0.95`.
- **Nguyên tắc đồng bộ**: Khi thêm, nâng cấp hoặc gỡ bỏ thư viện runtime trong `pyproject.toml`, phải cập nhật đồng thời `poc/backend/requirements/docker.txt`.

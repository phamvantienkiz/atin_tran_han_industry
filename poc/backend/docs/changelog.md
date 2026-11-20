# Changelog — `poc/backend`

---

## [0.1.5] - 2026-11-20 (PoC v0.0.1 — Docker BuildKit & Detection Tuning)
### Changed
- Tách manifest `poc/backend/requirements/docker.txt` cho Docker GPU runtime (`onnxruntime-gpu==1.23.2`, `opencv-python-headless==5.1.0.95`, `supervision==0.27.0.post2`), tối ưu layer caching trong `poc/Dockerfile` (copy & cài đặt thư viện trước khi copy `app/` và `scripts/`, dùng BuildKit cache mount `/root/.cache/pip`).
- Cập nhật cấu hình mặc định AI Core (`app/core/config.py`): `AI_CONF_THRESHOLD=0.55`, `AI_ANCHOR_MODE=center`, ưu tiên model `models/yolo26s.onnx`.

---

## [0.1.4] - 2026-11-19 (Streaming Cache & Latency)
### Added
- Thêm `app/ai/grid_cache.py` (`GridFrameCache`): cache JPEG theo nhu cầu (demand-driven) dành riêng cho Grid View (`854px`, `Q=68`), encode trên thread pool riêng để không nghẽn asyncio event loop.
- Thêm endpoint `GET /api/v1/metrics` trả về số liệu decode/infer/track/e2e và thống kê `GridFrameCache` + `ws_clients`.
- Thêm header `X-Stream-Source` (`ram-grid-cache` | `ram-direct` | `nvr-direct`), `X-Accel-Buffering: no`, `Pragma: no-cache` cho luồng MJPEG.
- Thêm script `scripts/export_app_logs.py` hỗ trợ thu thập log container.

---

## [0.1.3] - 2026-11-19 (Auto-FP16 & JIT Overlap Prefetch)
### Added
- `YoloPersonDetector` (`app/ai/detector.py`) tự động nhận diện input dtype (`float16` / `float32`) của model ONNX và thực hiện warmup pass trước khi chạy live stream.
- `PersonZoneDetector` (`app/ai/worker.py`) áp dụng JIT fetch frame mới nhất và `ThreadPoolExecutor(max_workers=1)` prefetch/decode/preprocess camera `i+1` song song khi GPU đang suy luận camera `i`.
- Bộ benchmark Phase 0 read-only tại `scripts/` (`probe_nvr.py`, `bench_decode.py`, `bench_infer.py`).

---

## [0.1.2] - 2026-11-19 (Zero-Wait MJPEG & WebSocket Split Push)
### Changed
- Chuyển từ pipeline đồng bộ đệm (`DisplayAndSyncPipeline`) sang kiến trúc **zero-wait MJPEG passthrough** qua `NvrStreamManager` (`ram-direct`) và đẩy kết quả nhận diện ngay lập tức theo từng camera qua WebSocket.
- Tách luồng đẩy WebSocket (`DetectionWsHub` với `_ClientSender` coalescing latest-wins) thành `bbox` (tần suất cao) và `hud` / `timeline` (tần suất thấp `1s`/`2s` hoặc ngay khi đổi trạng thái).

---

## [0.1.1] - 2026-11-19 (SQLite WAL, ByteTrack & 4-State Zone Presence)
### Added
- `app/db/sqlite_store.py` & `app/repositories/sqlite_camera_repository.py`: Lưu cấu hình camera, lịch sử `alert_events` (retention 90 ngày) và `runtime_snapshots` trên SQLite WAL, tự động migrate từ `data/cameras.json`.
- `app/ai/tracker.py` (`CameraTracker`): `supervision.ByteTrack` cô lập theo từng camera, snap về BBox YOLO gốc khi `IoU >= 0.25`.
- `app/ai/rule_engine.py`: Bổ sung mode `zone_presence` với 4 trạng thái (`present`, `leaving`, `empty`, `alert`) + `idle`, rolling timeline 30 phút, `grace_seconds` và `warning_seconds` cấu hình theo từng camera.
- Endpoints mới: `POST /api/v1/detections/{cam_id}/reset-stats`, `GET /api/v1/detections/{cam_id}/events`, `WS /api/v1/ws/detections` (và alias `/api/v1/detections/ws`).
- Hỗ trợ chuyển đổi model FP16 an toàn (`scripts/convert_onnx_fp16.py`) và giới hạn VRAM CUDA (`AI_VRAM_LIMIT_MB=1536`).

---

## [0.1.0] - 2026-11-19
### Added
- Dựng khung `poc/backend/` theo chuẩn `fastapi-backend-scaffold` (`api/v1`, `middlewares`, `core`, `models`, `schemas`, `db`, `repositories`, `services`, `dependencies`, `exceptions`, `utils`).
- Dựng AI Core ban đầu (`detector.py`, `rule_engine.py`, `worker.py`) và bộ adapter ATIN Smart VMS (`app/integrations/atin_vms/`).
- Khởi tạo Alembic async (`migrations/`), `Dockerfile`, `docker-compose.yml`, `scripts/dev.ps1` và bộ test `pytest`.

# Báo Cáo Kiểm Tra Kỹ Thuật & Bảo Mật (`poc/backend`)

> Cập nhật theo trạng thái codebase **PoC v0.0.1** (commit `932f1e5`, 2026-11-20).

---

## 1. Kết quả kiểm tra tự động & thực tế

### 1.1. Kiểm tra Local (`poc/backend/.venv`)
- **Ruff (`.\.venv\Scripts\ruff.exe check --no-cache app tests scripts`)**: `All checks passed!` (0 lỗi).
- **Pytest (`.\.venv\Scripts\pytest.exe -v -p no:cacheprovider tests/services/`)**: `15 passed in 0.98s`, bao gồm:
  - `test_detector_smoke.py`: Pipeline `YoloPersonDetector` + `CameraTracker` + `ZoneRuleEngine` trên frame thật (`1 passed`).
  - `test_nvr_stream.py`: Tách gói JPEG MJPEG nhiều chunk & chế độ unconfigured (`2 passed`).
  - `test_optimization_phases.py`: Nội suy track, SQLite WAL + migration từ `cameras.json`, `GridFrameCache` demand-driven (`3 passed`).
  - `test_rule_engine.py`: Chế độ `zone_intrusion` dwell-time & cooldown (`1 passed`).
  - `test_rule_engine_presence.py`: Vòng đời 4 trạng thái `zone_presence` (`present`/`leaving`/`empty`/`alert`/`idle`), anchor, rolling timeline & reset (`5 passed`).
  - `test_tracker.py`: IoU snapping & cô lập ByteTrack theo từng camera (`3 passed`).
- **Lưu ý môi trường Windows sandbox**: Nhóm test API dùng FastAPI `TestClient` kích hoạt lifespan nền (`tests/api/v1/test_cameras.py`, `tests/middlewares/test_request_id.py`) cần chạy trong môi trường cho phép socket/thread đầy đủ hoặc container Linux.

### 1.2. Kiểm chứng Runtime trên Server GPU `aiot` (Docker `tranhan_ai_poc`)
- **Base image & Build**: `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04` (Python 3.10), `Docker 29.6.1`, `Compose v5.3.0`, BuildKit `1.7`. Build context chỉ `7.57 kB`.
- **Thư viện AI & OpenCV trong container**:
  - `onnxruntime-gpu==1.23.2` (`['TensorrtExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']`), `ldd libonnxruntime_providers_cuda.so` khớp đủ `libcublasLt.so.12`, `libcublas.so.12`, `libcurand.so.10`, `libcufft.so.11`, `libcudart.so.12`, `libcudnn.so.9` (không thiếu thư viện).
  - `opencv-python-headless==5.1.0.95` (không có `opencv-python` GUI, được assert trực tiếp lúc build).
  - `supervision==0.27.0.post2`.
- **Hiệu năng suy luận thực tế (NVIDIA RTX A400 4GB)**:
  - `active_provider`: `CUDAExecutionProvider` (giới hạn `AI_VRAM_LIMIT_MB=1536`, thực tế PID 1 dùng ~202 MiB VRAM).
  - `infer_ms`: `16–37 ms` / camera; `e2e_ms`: `33–63 ms`.

---

## 2. Các kiểm soát kỹ thuật & bảo mật đã áp dụng

- **Chống Path Traversal**: Mọi thao tác đọc/tải/xóa file video và frame đi qua `validate_safe_name()` (`^[A-Za-z0-9._-]+$`, chặn `..`).
- **Xử lý lỗi tập trung**: `ErrorHandlingMiddleware` chặn toàn bộ ngoại lệ chưa xử lý và trả JSON `500` kèm `requestId` (không rò rỉ stack trace); các lỗi nghiệp vụ dùng `NotFoundError`, `ConflictError`, `ValidationError`, `UpstreamError`.
- **Bảo toàn dữ liệu SQLite**: `SqliteStore` bật `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`, `PRAGMA busy_timeout=5000` và ghi bất đồng bộ qua thread riêng (`queue.Queue(maxsize=256)`), tránh block vòng lặp AI hoặc asyncio.
- **Tối ưu GPU & Streaming**:
  - Giới hạn VRAM CUDA (`gpu_mem_limit = 1536 MB`) với `HEURISTIC` cuDNN search để tránh OOM trên GPU 4GB.
  - Tự động skip AI với camera chưa vẽ zone (`len(zone) < 3`) trừ khi được focus.
  - Header chống buffering (`X-Accel-Buffering: no`, `Cache-Control: no-store`, `Pragma: no-cache`) cho MJPEG.
- **Cô lập bí mật & môi trường**: `.env`, `.venv/`, `data/tranhan_poc.db` loại trừ khỏi git/build context; chỉ commit `.env.example`.

---

## 3. Hạng mục cần nâng cấp khi lên Production

1. **Rate Limit phân tán**: `RateLimitMiddleware` hiện lưu bộ đếm trong RAM (`_hits`); cần chuyển sang Redis (`INCR` + `EXPIRE`) khi chạy nhiều worker/container.
2. **Xác thực & Phân quyền**: Bổ sung xác thực JWT RS256 (Keycloak / IAM) hoặc tích hợp trực tiếp vào `aioc-backend` theo luồng IAM hiện hữu.
3. **Database PostgreSQL & Alembic**: Chuyển `DB_BACKEND` sang PostgreSQL với `AsyncSession` và tạo migration Alembic chuẩn thay cho SQLite cục bộ.
4. **Cấu hình CORS & Secret**: Thay `SECRET_KEY` mặc định và giới hạn `BACKEND_CORS_ORIGINS` theo domain Production thực tế.
5. **Kích hoạt ATIN Smart VMS Integration**: Bật `ATIN_VMS_ENABLED=true`, cấu hình MQTT WSS + RTSP + Storage Upload theo hợp đồng `C01`–`C09`.

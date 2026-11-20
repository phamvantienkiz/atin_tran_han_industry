# PoC v001 — Đặc Tả Chi Tiết Backend FastAPI & Lõi AI GPU (`poc/backend/`)

> **Mục tiêu**: Nâng cấp `poc/backend/` để vừa phục vụ tĩnh ứng dụng Next.js (`poc/frontend/out/`) trên **1 Port duy nhất (`PORT=28080`)**, vừa kéo trực tiếp luồng hình ảnh từ NVR Trần Hân (`nmts2025.smartddns.tv:80`) vào bộ nhớ RAM chia sẻ (`NvrStreamManager`), chạy suy luận GPU (`onnxruntime-gpu` FP16 + ByteTrack + State Machine 4 trạng thái) và đẩy BBox + HUD realtime qua WebSocket `/api/v1/ws/detections`.

---

## 1. Danh Sách File Cần Tạo Mới / Cập Nhật Trong `poc/backend/`

| Trạng thái | Đường dẫn file | Mô tả nhiệm vụ |
| :---: | :--- | :--- |
| **[MODIFY]** | `poc/backend/pyproject.toml` | `requires-python = ">=3.10"`, `supervision>=0.25.0,<0.28.0`, và nhóm optional `[gpu]` (`onnxruntime-gpu>=1.20.0,<1.24.0`, `nvidia-*-cu12`, `onnx`, `onnxconverter-common`). |
| **[NEW]** | `poc/backend/requirements/docker.txt` | Manifest riêng cho Docker GPU runtime (`onnxruntime-gpu==1.23.2`, `opencv-python-headless==5.1.0.95`, `supervision==0.27.0.post2`). |
| **[MODIFY]** | `poc/backend/.env.example` | Chuẩn hóa biến môi trường PoC v001 (`PORT=28080`, thông tin NVR Trần Hân, cấu hình AI GPU & State Machine). |
| **[MODIFY]** | `poc/backend/app/core/config.py` | Bổ sung các trường cấu hình (`DB_BACKEND`, `DISPLAY_GRID_W/Q`, `BBOX_STALE_SECONDS`, `AI_VRAM_LIMIT_MB=1536`, `AI_CONF_THRESHOLD=0.55`, `AI_ANCHOR_MODE=center`), ưu tiên `yolo26s.onnx` và `poc/frontend/out`. |
| **[NEW]** | `poc/backend/scripts/` | `convert_onnx_fp16.py`, `run_server.sh`, `export_app_logs.py`, `probe_nvr.py`, `bench_decode.py`, `bench_infer.py`. |
| **[NEW]** | `poc/backend/app/ai/nvr_stream.py` | **`NvrStreamManager`**: Kéo trực tiếp luồng MJPEG (fallback Snapshot) qua HTTP Digest Auth từ NVR, lưu `NvrFramePacket` mới nhất vào RAM. |
| **[NEW]** | `poc/backend/app/ai/grid_cache.py` | **`GridFrameCache`**: Cache JPEG theo nhu cầu (demand-driven) cho Grid View (`854px`, `Q=68`) trên ThreadPool riêng. |
| **[NEW]** | `poc/backend/app/db/sqlite_store.py` | **`SqliteStore`**: SQLite WAL + async writer thread lưu `cameras`, `alert_events` (retention 90 ngày), `runtime_snapshots`, `app_settings`. |
| **[NEW]** | `poc/backend/app/repositories/sqlite_camera_repository.py` | **`SqliteCameraRepository`**: Lưu trữ camera/zone trên SQLite, tự migrate từ `data/cameras.json`. |
| **[MODIFY]** | `poc/backend/app/ai/detector.py` | **`YoloPersonDetector`**: `CUDAExecutionProvider` (giới hạn VRAM `1536 MB`) với fallback CPU, tự nhận biết FP16/FP32, warmup pass. |
| **[NEW]** | `poc/backend/app/ai/tracker.py` | **`CameraTracker`**: `supervision.ByteTrack` + `_snap_box_to_raw_ex(min_iou=0.25)` khử trễ pha Kalman Filter. |
| **[MODIFY]** | `poc/backend/app/ai/rule_engine.py` | **`ZoneRuleEngine`**: Máy trạng thái 4 trạng thái (`present`, `leaving`, `empty`, `alert`) + `idle` → 3 màu (`green`, `yellow`, `red`), Rolling Timeline 30 phút. |
| **[NEW]** | `poc/backend/app/services/ws_hub.py` | **`DetectionWsHub`**: `_ClientSender` coalescing (latest-wins), tách `publish_bbox_from_thread` và `publish_hud_from_thread`. |
| **[MODIFY]** | `poc/backend/app/ai/worker.py` | **`PersonZoneDetector`**: JIT fetch + 1-cam overlap prefetch (`ThreadPoolExecutor(max_workers=1)`), skip AI camera chưa vẽ zone, lưu SQLite `alert_events` & `runtime_snapshots`. |
| **[MODIFY]** | `poc/backend/app/api/v1/endpoints/` | Thêm `WS /api/v1/ws/detections`, `POST /detections/{id}/reset-stats`, `GET /detections/{id}/events`, `GET /metrics`, `mjpeg?view=grid|focus` (`X-Stream-Source`). |

---

## 2. Chi Tiết Triển Khai Từng Module

### 2.1. Cập nhật `poc/backend/pyproject.toml`

Thêm `supervision>=0.25.0` vào `dependencies` và tạo nhóm optional `gpu` để cài đặt trên server `aiot`:

```toml
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "pydantic-settings>=2.4.0",
    "python-dotenv>=1.0.0",
    "httpx>=0.27.0",
    "numpy>=1.26.0",
    "opencv-python-headless>=4.10.0",
    "onnxruntime>=1.20.0",
    "supervision>=0.25.0",
    "paho-mqtt>=2.1.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.30.0",
    "alembic>=1.13.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "aiosqlite>=0.20.0",
    "ruff>=0.6.0",
    "mypy>=1.11.0",
]
gpu = [
    "onnxruntime-gpu>=1.18.0",
    "onnx>=1.16.0",
    "onnxconverter-common>=1.14.0",
]
```

> **Lưu ý trên server `aiot`**: Khi cài nhóm `[gpu]`, `onnxruntime-gpu` và `onnxruntime` (CPU) cùng ghi vào namespace `onnxruntime`. Trong script cài đặt trên `aiot` (xem File 03), sau khi cài `-e ".[dev,gpu]"`, chạy thêm `uv pip install --python .venv/bin/python --force-reinstall --no-deps onnxruntime-gpu` để đảm bảo binary CUDA của `onnxruntime-gpu` được kích hoạt 100%.

---

### 2.2. Cấu hình `poc/backend/app/core/config.py` & `.env.example`

#### Các biến trong `poc/backend/.env.example`:
```ini
# --- Server & Port (1 Port duy nhất cho cả Next.js UI + FastAPI + WS + MJPEG) ---
APP_NAME="ATIN Smart Fishing"
ENVIRONMENT=poc
DEBUG=true
PORT=28080
PROJECT_DISPLAY_NAME="ATIN Smart Fishing"
SERVE_FRONTEND=true
FRONTEND_DIR=../frontend/out
FRONTEND_LEGACY_DIR=../frontend

# --- NVR Nhà máy Thủy sản Trần Hân (DDNS Direct Mode) ---
NVR_HOST=nmts2025.smartddns.tv
NVR_PORT=80
NVR_USER=user
NVR_PASS=testcam@123
NVR_STREAM_FPS_LIMIT=12.0

# --- AI Core (ONNX Runtime CUDA 12 + ByteTrack + Zone Presence Rule Engine) ---
AI_ENABLED=true
MODEL_PATH=../models/yolo26s.onnx
AI_RUNTIME=auto
AI_EP=auto
AI_VRAM_LIMIT_MB=1536
AI_CONF_THRESHOLD=0.55
AI_IMGSZ=640
AI_DECODE_REDUCE=1
AI_SNAP_MIN_IOU=0.25
AI_TARGET_FPS=0.0
AI_ANCHOR_MODE=center
AI_PRESENCE_GRACE_SECONDS=2.0
AI_PRESENCE_WARNING_SECONDS=10.0
AI_TIMELINE_WINDOW_SECONDS=1800
AI_CONFIRM_SECONDS=2.0
AI_EVENT_COOLDOWN_SECONDS=60.0
WS_PUSH_MAX_HZ=15.0
DISPLAY_GRID_W=854
DISPLAY_GRID_Q=68
BBOX_STALE_SECONDS=1.8
DB_BACKEND=sqlite
DB_PATH=../data/tranhan_poc.db
```

#### Logic resolve đường dẫn thông minh trong `app/core/config.py`:
- **`frontend_path`**:
  - Kiểm tra nếu `_resolve_path(self.FRONTEND_DIR)` (mặc định `../frontend/out` hoặc `/app/frontend/out` trong Docker) tồn tại và có file `index.html` $\rightarrow$ trả về thư mục đó (bản build Next.js Static Export).
  - Nếu chưa build `out/`, fallback về `_resolve_path(self.FRONTEND_LEGACY_DIR)` để server không bao giờ lỗi khởi động.
- **`model_file_path`**:
  - Ưu tiên sử dụng file `poc/models/yolo26s.onnx` (model fine-tune `factory_person_dataset`, `names = {0: 'person'}`) ngay cả khi biến `.env` cũ còn trỏ tới `yolo26s_fp16.onnx` hay `yolo26s_best.onnx`.

---

### 2.3. Script Chuyển Đổi Model Sang FP16 (`poc/backend/scripts/convert_onnx_fp16.py`)

```python
"""Convert YOLO ONNX FP32 model to FP16 (keep_io_types=True) for RTX A400 Tensor Cores."""

from __future__ import annotations

import sys
from pathlib import Path

import onnx
from onnxconverter_common import float16


def main() -> int:
    models_dir = Path(__file__).resolve().parents[2] / "models"
    src_candidates = [
        models_dir / "yolo26s_best.onnx",
        models_dir / "yolo26s.onnx",
    ]
    src_path = next((p for p in src_candidates if p.exists()), None)
    if src_path is None:
        print(f"[ERROR] Không tìm thấy file ONNX gốc trong {models_dir}", file=sys.stderr)
        return 1

    dst_path = models_dir / "yolo26s_fp16.onnx"
    print(f"[INFO] Đang nạp model FP32: {src_path} ({src_path.stat().st_size / 1024 / 1024:.2f} MB)")
    model_fp32 = onnx.load(str(src_path))
    model_fp16 = float16.convert_float_to_float16(model_fp32, keep_io_types=True)
    onnx.save(model_fp16, str(dst_path))
    print(f"[OK] Đã lưu model FP16: {dst_path} ({dst_path.stat().st_size / 1024 / 1024:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

---

### 2.4. Bộ Đọc Luồng NVR Chia Sẻ Trong RAM (`poc/backend/app/ai/nvr_stream.py`) — **[NEW]**

Module này giải quyết triệt để việc lấy luồng trực tiếp từ `nmts2025.smartddns.tv:80` bằng tài khoản `user` / `testcam@123`:

#### Thiết kế chi tiết `app/ai/nvr_stream.py`:
1. **Dataclass `NvrFramePacket`**:
   ```python
   @dataclass(frozen=True)
   class NvrFramePacket:
       cam_id: str
       channel: int
       subtype: int
       frame: np.ndarray        # Ảnh BGR đã decode cho AI Core
       jpeg_bytes: bytes        # Bytes JPEG gốc để phát ra /api/v1/cameras/{id}/mjpeg (0 tốn CPU re-encode!)
       seq: int                 # Số thứ tự tăng dần mỗi khi có frame mới
       ts_mono: float           # time.monotonic()
       ts_wall: float           # time.time()
   ```
2. **Class `NvrChannelReader`**:
   - Chạy 1 daemon thread riêng cho từng camera có `enabled == True`.
   - **Chiến lược kết nối 2 tầng tự động (Dual-Strategy Ingestion)**:
     - **Tầng 1 (Ưu tiên — Luồng MJPEG liên tục)**: Mở kết nối streaming `GET {nvr_base_url}/cgi-bin/mjpg/video.cgi?channel={channel}&subtype={subtype}` với `httpx.DigestAuth(nvr_user, nvr_pass)` và `timeout=httpx.Timeout(10.0, read=15.0)`.
       - Đọc `iter_bytes(chunk_size=16384)` vào `bytearray` buffer.
       - Tìm cặp SOI (`\xff\xd8`) và EOI (`\xff\xd9`) để cắt chính xác từng bức ảnh JPEG từ luồng multipart.
       - Giới hạn tốc độ decode theo `fps_limit` (mặc định `12.0 FPS`, tức ~83ms/frame): luôn cập nhật `jpeg_bytes` mới nhất, và khi đủ nhịp `1 / fps_limit` thì gọi `cv2.imdecode` ra `frame` BGR, tăng `seq += 1` rồi ghi đè vào `self._latest` dưới `threading.Lock`.
     - **Tầng 2 (Fallback tự động — Snapshot Polling tốc độ cao)**:
       - Nếu kênh NVR nào trả mã lỗi cho `/cgi-bin/mjpg/video.cgi` hoặc luồng MJPEG bị đứt/treo quá `4.0 giây` không có SOI/EOI, thread lập tức chuyển sang gọi `GET {nvr_base_url}/cgi-bin/snapshot.cgi?channel={channel}` liên tục ở nhịp `0.25s–0.35s` trong `15 giây`, sau đó thử nối lại MJPEG.
       - Nhờ cơ chế này, **100% các kênh 16, 17, 18, 21 của Trần Hân luôn có hình và BBox liên tục**, không bao giờ bị chết luồng.
3. **Class `NvrStreamManager`**:
   - Quản lý `dict[str, NvrChannelReader]` theo `cam_id`.
   - `sync_cameras(cameras: list[dict])`: khởi tạo reader cho camera mới, cập nhật nếu `channel`/`subtype` đổi, dừng reader của camera bị xóa hoặc `enabled == False`.
   - `latest(cam_id: str) -> NvrFramePacket | None`: trả về gói frame mới nhất trong RAM.
   - `stop_all()`: đặt `stop_event` cho tất cả reader và đóng sạch kết nối khi bấm `Ctrl + C`.

---

### 2.5. Nâng Cấp `YoloPersonDetector` (`poc/backend/app/ai/detector.py`)

Cập nhật [detector.py](file:///e:/ATIN/atin_tran_han_industry/poc/backend/app/ai/detector.py) với các cải tiến bắt buộc sau:

1. **Mở rộng `PersonDetection` có điểm chân (`foot_x`, `foot_y`)**:
   ```python
   @dataclass(frozen=True)
   class PersonDetection:
       x1: float
       y1: float
       x2: float
       y2: float
       cx: float
       cy: float
       foot_x: float
       foot_y: float
       conf: float
   ```
   Khi tạo `PersonDetection`: `cx = round((nx1 + nx2) / 2.0, 4)`, `cy = round((ny1 + ny2) / 2.0, 4)`, `foot_x = cx`, `foot_y = round(ny2, 4)`.

2. **Tự động kích hoạt `CUDAExecutionProvider` với giới hạn VRAM `1024 MB` trên RTX A400**:
   ```python
   available = ort.get_available_providers()
   use_cuda = self.runtime in ("auto", "onnx_cuda") and "CUDAExecutionProvider" in available
   if use_cuda:
       cuda_opts = {
           "device_id": "0",
           "arena_extend_strategy": "kSameAsRequested",
           "gpu_mem_limit": str(int(self.vram_limit_mb * 1024 * 1024)),
           "cudnn_conv_algo_search": "HEURISTIC",
           "do_copy_in_default_stream": "1",
       }
       providers = [("CUDAExecutionProvider", cuda_opts), "CPUExecutionProvider"]
   else:
       providers = ["CPUExecutionProvider"]
   ```
   - Ghi log rõ ràng khi khởi tạo: `Loaded YOLO ONNX model=<path> active_provider=<session.get_providers()[0]>`.
   - Chạy **1 pass warmup** với `np.zeros((1, 3, self.imgsz, self.imgsz), dtype=np.float32)` ngay trong `ensure_session()` để khởi tạo CUDA context ngay lúc bật server.

3. **Hỗ trợ `detect_batch(frames: list[np.ndarray]) -> list[list[PersonDetection]]`**:
   - Nếu `len(frames) == 0` trả về `[]`.
   - Kiểm tra `input_shape[0]` của ONNX session: nếu là dynamic batch (`isinstance(dim0, str)` hoặc `dim0 is None` hoặc `dim0 != 1`), gom batch bằng `np.concatenate(blobs, axis=0)` và chạy 1 lần `session.run()`. Nếu model export cố định batch `1`, chạy vòng lặp qua từng `blob` trên cùng `session`.
   - Giữ nguyên hàm `detect(frame: np.ndarray) -> list[PersonDetection]` gọi `self.detect_batch([frame])[0]` để tương thích 100% với mọi nơi đang gọi `detect()`.

---

### 2.6. Module Theo Dõi Nhân Viên & Khử Trễ Pha Kalman (`poc/backend/app/ai/tracker.py`) — **[NEW]**

Sử dụng `supervision.ByteTrack` kết hợp thuật toán `_snap_box_to_raw` đã được kiểm chứng trên server `aiot` (xem [DEEP_DIVE_AI_CORE.md](file:///e:/ATIN/atin_tran_han_industry/docs/note/DEEP_DIVE_AI_CORE.md#L468-L485)):

```python
"""ByteTrack person tracker with IoU raw-box snapping (zero Kalman lag)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import supervision as sv

from app.ai.detector import PersonDetection

_VIRTUAL_W = 1280.0
_VIRTUAL_H = 720.0


@dataclass(frozen=True)
class TrackedPerson:
    track_id: int
    x1: float
    y1: float
    x2: float
    y2: float
    cx: float
    cy: float
    foot_x: float
    foot_y: float
    conf: float


def _snap_box_to_raw(
    track_box: np.ndarray,
    raw_boxes: np.ndarray,
    raw_confs: np.ndarray,
    min_iou: float = 0.45,
) -> tuple[np.ndarray, float]:
    """Replace Kalman-smoothed box with exact current-frame YOLO box if IoU >= min_iou."""
    if len(raw_boxes) == 0:
        return track_box, 0.5
    x1 = np.maximum(track_box[0], raw_boxes[:, 0])
    y1 = np.maximum(track_box[1], raw_boxes[:, 1])
    x2 = np.minimum(track_box[2], raw_boxes[:, 2])
    y2 = np.minimum(track_box[3], raw_boxes[:, 3])

    inter = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    area_t = max(1e-6, float((track_box[2] - track_box[0]) * (track_box[3] - track_box[1])))
    area_r = np.maximum(1e-6, (raw_boxes[:, 2] - raw_boxes[:, 0]) * (raw_boxes[:, 3] - raw_boxes[:, 1]))
    ious = inter / (area_t + area_r - inter)

    best_idx = int(np.argmax(ious))
    if float(ious[best_idx]) >= min_iou:
        return raw_boxes[best_idx].astype(np.float32), float(raw_confs[best_idx])
    return track_box, float(raw_confs[best_idx])
```

- Class `CameraTracker`:
  - Giữ `self._trackers: dict[str, sv.ByteTrack] = {}`.
  - Mỗi `sv.ByteTrack` cấu hình `track_activation_threshold=0.25, lost_track_buffer=30, minimum_matching_threshold=0.8, frame_rate=12`.
  - Khi gọi `update(cam_id: str, detections: Sequence[PersonDetection]) -> list[TrackedPerson]`:
    - Quy đổi tọa độ chuẩn hóa `[0..1]` của `detections` sang không gian pixel ảo `1280x720` để bộ lọc Kalman của ByteTrack hoạt động chính xác.
    - Gọi `bt.update_with_detections(sv_dets)`.
    - Với từng đối tượng đã gán `tracker_id`, gọi `_snap_box_to_raw()` rồi chia ngược tọa độ về `[0..1]`, trả ra danh sách `TrackedPerson` có `track_id`, `x1, y1, x2, y2`, `cx, cy`, `foot_x, foot_y`, `conf`.

---

### 2.7. Máy Trạng Thái 4 Trạng Thái & Rolling Timeline 30 Phút (`poc/backend/app/ai/rule_engine.py`)

Nâng cấp [rule_engine.py](file:///e:/ATIN/atin_tran_han_industry/poc/backend/app/ai/rule_engine.py) để hỗ trợ đồng thời cả 2 chế độ:
1. **`feature_type == "zone_presence"` (Mặc định cho PoC Trần Hân — Giám sát duy trì nhân viên trong vùng)**
2. **`feature_type == "zone_intrusion"` (Giữ tương thích ngược cho bài toán xâm nhập & unit test cũ)**

#### Cấu trúc dữ liệu trả về của `ZoneEvaluation`:
```python
@dataclass(frozen=True)
class ZoneEvaluation:
    has_zone: bool
    in_zone_count: int
    person_in_zone: bool
    should_emit_event: bool
    dwell_seconds: float
    persons: list[dict[str, Any]]
    # Các trường phục vụ HUD & Timeline chuẩn 3 ảnh mẫu PM:
    status: str = "empty"               # "present" | "leaving" | "empty" | "alert" | "idle"
    ui_color: str = "yellow"            # "green" | "yellow" | "red" | "idle"
    status_label: str = "VÙNG TRỐNG"
    sub_label: str = "không có người 00:00"
    polygon_label: str = "TRỐNG"
    empty_duration: float = 0.0
    alert_count: int = 0
    total_alert_seconds: float = 0.0
    session_duration_seconds: float = 0.0
    timeline: list[dict[str, Any]] = field(default_factory=list)
```

#### Quy tắc chuyển trạng thái chi tiết của `zone_presence`:
1. **Kiểm tra điểm nằm trong vùng**:
   - Với mỗi `det` (có thể là `TrackedPerson` hoặc `PersonDetection`), lấy `anchor_x = getattr(det, "foot_x", det.cx)` và `anchor_y = getattr(det, "foot_y", det.y2)` (khi `anchor_mode == "bottom_center"`), kiểm tra `point_in_polygon(anchor_x, anchor_y, polygon)`.
   - Mỗi phần tử trong `persons` trả về đủ: `track_id` (mặc định `idx + 1` nếu không qua tracker), `x1, y1, x2, y2, cx, cy, foot_x, foot_y, conf, in_zone`.
2. **Nếu chưa vẽ vùng (`not has_zone`)**:
   - `status = "idle"`, `ui_color = "idle"`, `status_label = "CHƯA VẼ VÙNG"`, `sub_label = "Vẽ vùng giám sát để kích hoạt"`, `polygon_label = ""`.
3. **Nếu đã có vùng (`has_zone == True`)**:
   - Tính `dt = max(0.0, ts - state.last_eval_mono)` (nếu `state.last_eval_mono is not None`).
   - Nếu `state.status == "alert"`: cộng dồn `state.total_alert_seconds += dt`.
   - **Trường hợp 1: Có nhân viên trong vùng (`in_zone_count >= 1`)**:
     - `state.status = "present"`
     - `state.empty_since = None`
     - `state.yellow_since = None`
     - Nếu `state.present_since is None`: `state.present_since = ts`
     - `dwell = ts - state.present_since`
     - `ui_color = "green"`
     - `status_label = "CÓ NHÂN VIÊN"`
     - `sub_label = f"{in_zone_count} người trong vùng"`
     - `polygon_label = f"{zone_title} · {in_zone_count} NV"`
   - **Trường hợp 2: Không có nhân viên trong vùng (`in_zone_count == 0`)**:
     - `state.present_since = None`
     - Nếu `state.empty_since is None`: `state.empty_since = ts`
     - `empty_dur = max(0.0, ts - state.empty_since)`
     - **Từ `present` vừa mất người**:
       - Chuyển sang `state.status = "leaving"` (nếu `grace_seconds > 0`).
     - **Đang ở `leaving`**:
       - Nếu `empty_dur < grace_seconds` (`2.0s`):
         - Giữ `state.status = "leaving"`, `ui_color = "green"`, `status_label = "CÓ NHÂN VIÊN"`, `sub_label = "Vừa rời khỏi vùng"`, `polygon_label = f"{zone_title} · VỪA RỜI VÙNG"`.
       - Nếu `empty_dur >= grace_seconds`:
         - Chuyển sang `state.status = "empty"`, đặt `state.yellow_since = ts`.
     - **Đang ở `empty` (hoặc Cold Start khi mới bật server)**:
       - Nếu `state.yellow_since is None`: `state.yellow_since = ts`.
       - `yellow_dur = max(0.0, ts - state.yellow_since)`
       - Nếu `yellow_dur < warning_seconds` (`10.0s`):
         - Giữ `state.status = "empty"`, `ui_color = "yellow"`, `status_label = "VÙNG TRỐNG"`, `sub_label = f"không có người {_fmt_mmss(empty_dur)}"`, `polygon_label = f"{zone_title} · TRỐNG"`.
       - Nếu `yellow_dur >= warning_seconds` (`10.0s`):
         - Chuyển sang `state.status = "alert"`.
         - Tăng `state.alert_count += 1`.
         - Kiểm tra cooldown để bật `should_emit_event = True`.
     - **Đang ở `alert`**:
       - `ui_color = "red"`, `status_label = "KHÔNG CÓ NHÂN VIÊN"`, `sub_label = f"Cảnh báo · vùng trống {_fmt_mmss(empty_dur)}"`, `polygon_label = f"{zone_title} · KHÔNG CÓ NHÂN VIÊN"`.
4. **Cập nhật Rolling Timeline 30 phút (`_update_timeline`)**:
   - Lưu danh sách các đoạn `{"start": float, "end": float, "color": "green" | "yellow" | "red"}` theo `wall_now`.
   - Nếu đoạn cuối cùng có cùng `color == ui_color`: chỉ cập nhật `last["end"] = wall_now`. Ngược lại tạo đoạn mới `{"start": prev_end, "end": wall_now, "color": ui_color}`.
   - Cắt bỏ các đoạn có `end < wall_now - timeline_window_sec` (`1800s`), và kẹp `first["start"] = max(first["start"], wall_now - timeline_window_sec)`.

---

### 2.8. WebSocket Hub (`poc/backend/app/services/ws_hub.py`) — **[NEW]**

Quản lý kết nối WebSocket tại `/api/v1/ws/detections` để đẩy BBox + HUD xuống Next.js ngay khi GPU xử lý xong frame:

```python
"""Thread-safe WebSocket broadcast hub for real-time AI detections & HUD state."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import WebSocket

from app.core.logging import get_logger

logger = get_logger("app.services.ws_hub")


class DetectionWsHub:
    def __init__(self, max_hz: float = 15.0) -> None:
        self.max_hz = max_hz
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_push_mono: float = 0.0

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def close_all(self) -> None:
        clients = list(self._clients)
        self._clients.clear()
        for ws in clients:
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass

    async def broadcast(self, message: dict[str, Any]) -> None:
        if not self._clients:
            return
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    def publish_from_thread(self, detections_map: dict[str, dict[str, Any]]) -> None:
        if not self._clients or self._loop is None or self._loop.is_closed():
            return
        now = time.monotonic()
        min_interval = 1.0 / self.max_hz if self.max_hz > 0 else 0.066
        if (now - self._last_push_mono) < min_interval:
            return
        self._last_push_mono = now
        payload = {
            "type": "detections",
            "ts": time.time(),
            "data": detections_map,
        }
        try:
            self._loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self.broadcast(payload))
            )
        except RuntimeError:
            pass
```

---

### 2.9. Luồng AI Worker (`poc/backend/app/ai/worker.py`) & Endpoints

1. **Trong `PersonZoneDetector._run_loop()`**:
   - Ở mỗi chu kỳ (`1.0 / target_fps`, mặc định `~83ms` cho `12 FPS`):
     - Đồng bộ danh sách camera `enabled` vào `NvrStreamManager.sync_cameras(all_cameras)`.
     - Với các camera có `NvrFramePacket` mới trong RAM (`pkt.seq != self._last_seq.get(cam_id)`):
       - Gom `frames` của tất cả camera có frame mới $\rightarrow$ gọi **`self._detector.detect_batch(frames)`** (1 lần gọi GPU cho cả 4 camera).
       - Với kết quả từng camera:
         - Gọi `tracked = self._tracker.update(cam_id, raw_dets)`
         - Gọi `eval_res = self._rule_engine.evaluate(...)`
         - Lưu vào `self._results[cam_id]`.
     - Với camera chưa có frame mới từ NVR trong chu kỳ đó nhưng đã có kết quả trước đó: vẫn cập nhật nhẹ đồng hồ đếm giây (`empty` / `alert`) của `ZoneRuleEngine` mỗi `0.5s` để bộ đếm `00:01 -> 00:02` trên HUD trôi mượt theo từng giây.
     - Gọi `self._on_update(self.get_all())` để `DetectionWsHub` đẩy ngay xuống các trình duyệt đang kết nối.
   - *(Tương thích ngược)*: Nếu `nvr_stream_manager` không có packet (ví dụ trong môi trường test mock `httpx` snapshot đơn lẻ), fallback về `_detect_camera()` qua `/cgi-bin/snapshot.cgi`.

2. **Trong `poc/backend/app/api/v1/endpoints/cameras.py` (`GET /api/v1/cameras/{cam_id}/mjpeg`)**:
   - Kiểm tra xem `nvr_stream_manager.latest(cam_id)` có đang hoạt động và khớp `subtype` không:
     - **Nếu có**: Phát `StreamingResponse` (`multipart/x-mixed-replace; boundary=frame`) đọc trực tiếp `pkt.jpeg_bytes` từ RAM mỗi khi `pkt.seq != last_seq` (chờ `await asyncio.sleep(0.04)` giữa các lần kiểm tra, thoát ngay khi `await request.is_disconnected()`).
     - **Nếu chưa có frame trong RAM (hoặc user mở Focus Modal xem `subtype=0` khác với `subtype` của stream nền)**: mở proxy `httpx.AsyncClient` tới NVR như hiện tại.
   - Tương tự với `GET /api/v1/cameras/{cam_id}/snapshot.jpg`: nếu `query param` không ép `direct=true` và trong RAM `nvr_stream_manager` đang có `pkt.jpeg_bytes` mới hơn `< 2.0s`, trả về ngay `pkt.jpeg_bytes` trong `0 ms` (không tốn 200ms chờ NVR chụp lại!).

3. **Trong `poc/backend/app/api/v1/endpoints/detections.py`**:
   - Thêm WebSocket endpoint:
     ```python
     @router.websocket("/ws")
     async def detections_websocket(
         websocket: WebSocket,
         service: Annotated[DetectionService, Depends(get_detection_service)],
         ws_hub: Annotated[DetectionWsHub, Depends(get_ws_hub)],
     ) -> None:
         await ws_hub.connect(websocket)
         try:
             # Gửi ngay snapshot trạng thái hiện tại vừa khi kết nối
             await websocket.send_json({
                 "type": "detections",
                 "ts": time.time(),
                 "data": service.get_detections(),
             })
             while True:
                 msg = await websocket.receive_json()
                 if isinstance(msg, dict) and msg.get("type") == "focus":
                     cam_id = msg.get("cam_id")
                     service.set_focus(cam_id if cam_id else None)
         except WebSocketDisconnect:
             pass
         except Exception:  # noqa: BLE001
             pass
         finally:
             ws_hub.disconnect(websocket)
     ```
   - *(Lưu ý đường dẫn WS)*: Đăng ký cả ở `/api/v1/detections/ws` và alias `/api/v1/ws/detections` trên `api_router` để Frontend gọi đường dẫn nào cũng khớp 100%.
   - Thêm endpoint reset thống kê:
     ```python
     @router.post("/{cam_id}/reset-stats")
     def reset_camera_stats(
         cam_id: str,
         service: Annotated[DetectionService, Depends(get_detection_service)],
     ) -> dict[str, Any]:
         return service.reset_stats(cam_id)
     ```

---

### 2.10. Phục Vụ Tĩnh Next.js Static Export Trên Cùng 1 Port (`poc/backend/app/main.py`)

Trong [app/main.py](file:///e:/ATIN/atin_tran_han_industry/poc/backend/app/main.py), sau khi `app.include_router(api_router, prefix=settings.API_V1_PREFIX)`:

```python
    if settings.SERVE_FRONTEND and settings.frontend_path.is_dir():
        frontend_dir = settings.frontend_path
        # Mount toàn bộ thư mục tĩnh Next.js (out/_next, out/index.html, assets...)
        app.mount(
            "/",
            StaticFiles(directory=str(frontend_dir), html=True),
            name="frontend",
        )
```

> **Tại sao dùng `app.mount("/", StaticFiles(directory=str(frontend_dir), html=True))` đặt ở CUỐI `create_app()`?**
> - Trong FastAPI/Starlette, các route đăng ký trước (`/api/v1/*`, `/docs`, `/openapi.json`, WebSocket `/api/v1/ws/detections`) được ưu tiên khớp trước.
> - Mọi request tĩnh của Next.js (`/`, `/_next/static/...`, `/favicon.ico`, v.v.) sẽ được `StaticFiles(..., html=True)` phục vụ trực tiếp từ `poc/frontend/out/` trên đúng cổng `28080`!

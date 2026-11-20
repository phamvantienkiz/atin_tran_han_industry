# PoC v001 — Kế Hoạch Tối Ưu Hiệu Năng (Optimization Plan) — v2

> **Người thực hiện**: Hydrogen / Neon. Tài liệu chỉ mô tả thiết kế + kế hoạch; mã trong tài liệu là mẫu hợp đồng, không phải code đã implement.
> **v2 thay đổi so với v1** (theo kết quả `nc` và phản hồi của PM + Neon):
> 1. Cổng RTSP **554 bị timeout** → **bỏ hướng FFmpeg/NVDEC/H.264**, chốt **HTTP MJPEG luồng chính `subtype=0`** (Nhánh B). Hướng ffmpeg chỉ giữ làm phương án dự phòng nếu IT mở 554 sau này.
> 2. **Bỏ "Fused Binary WebSocket"**, chuyển sang **AI-Paced MJPEG** (giữ `<img>` MJPEG + WS BBox tối giản, đồng bộ nhịp, có van xả). PM chấp nhận lệch 1–2 khung; **không chấp nhận** giật, lệch cả chục khung, hay BBox đứng yên.
> 3. **"GPU Batching" = bộ gom/điều phối nhiều camera trên một luồng GPU (`GpuBatcher`)**, **không** yêu cầu export lại model batch=4.
> 4. Các số đo (băng thông, decode, inference) **do script đo trong repo thực hiện**; PM `git pull` rồi chạy trên `aiot`.
> 5. Giả định FPS 12 được làm rõ là **tham số cấu hình**, không phải giới hạn của NVR.

**Ràng buộc đã chốt**: Python 3.10 (base Ubuntu 22.04); VRAM AI tới **1.5 GB**; chất lượng live view **≥ hiện tại**, **không dùng luồng phụ**; **1 port 28080**; đồng ý thêm **SQLite**.

---

## 1. Chẩn Đoán Nguyên Nhân Gốc (đã đối chiếu code)

| # | Lỗi | Vị trí | Triệu chứng người dùng thấy |
|---|---|---|---|
| **R1** | **Re-stamp BBox cũ**: nhánh `idle_cams` lấy `last_tracked` (BBox cũ), nếu chưa quá `_BBOX_STALE_SEC=1.5` thì gọi `_evaluate_camera(..., updated_at=time.time())` và **bắn lại lên WS với timestamp mới**. Frontend (đã stamp `_client_ts` lúc nhận) coi BBox là mới. | `worker.py` ~L307-333 | **BBox đứng yên tại chỗ cũ tới 1.5 s** trong khi người đã đi xa |
| **R2** | `_store_jpeg()` nhánh `else`: ghép `jpeg_bytes` mới với `frame`/`seq` cũ. Live view nhảy trước, AI không thấy `seq` đổi. | `nvr_stream.py` ~L158-171 | Lệch nhiều khung giữa hình và AI |
| **R3** | `ram_iterator()` polling `asyncio.sleep(0.04)`, lệch pha với nhịp nguồn. | `cameras.py` ~L111-120 | Video giật cục, khoảng cách khung không đều |
| **R4** | Mỗi tin WS ở 12–15 Hz mang cả `timeline` 30 phút × 4 cam. | `worker.py` `_build_result` / `ws_hub.py` | JSON nặng, parse tốn, khựng khi mạng yếu |
| **R5** | `backdrop-blur` đè lên 4 `<img>` MJPEG; Canvas `dpr` tới 2. | `ZoneHudOverlay.tsx`, `CameraCard.tsx`, `CameraOverlayCanvas.tsx` | iGPU nóng, rAF tụt nhịp → BBox khựng |
| **R6** | `_snap_box_to_raw(min_iou=0.45)` trả hộp Kalman khi IoU thấp. | `tracker.py` | BBox chậm pha khi đi nhanh |
| **R7** | Cameras mặc định `subtype=1` (luồng phụ). | `camera_repository.py` | Chất lượng thấp; PM yêu cầu bỏ |
| **R8** | Cấu hình/thống kê chỉ ở `cameras.json` + RAM. | `camera_repository.py`, `rule_engine.py` | Restart mất lịch sử |

**FPS 12**: `NVR_STREAM_FPS_LIMIT` và `AI_TARGET_FPS` trong `config.py` — mặc định do PoC đặt, **không phải** FPS của NVR. Sau khi script đo (§6) cho biết FPS nguồn và năng lực GPU, nâng hai tham số này (xem §3.4).

---

## 2. Quyết Định Thiết Kế

### 2.1. Nguồn video: HTTP MJPEG luồng chính (`subtype=0`)
- RTSP 554 timeout từ `aiot` → không có H.264 → **ffmpeg + `h264_cuvid` không áp dụng**. (Ghi vào `deploy.md`: kết quả `nc` ngày 2026-11-20.)
- Hiển thị: **truyền nguyên byte JPEG gốc của NVR**, không recompress → chất lượng = NVR, CPU server ≈ 0 cho đường hiển thị.
- **Rủi ro cần xác nhận bằng script**: `video.cgi?subtype=0` của đầu ghi có thể không hỗ trợ MJPEG ở luồng chính hoặc FPS thấp. Nếu script đo thất bại ở `subtype=0` → báo PM, **không tự quay về `subtype=1`**.
- Dự phòng tương lai: nếu IT mở 554 → quay lại thiết kế ffmpeg/NVDEC (xem DEEP_DIVE §3).

### 2.2. Giải mã cho AI (CPU, có giảm tỉ lệ)
- Dùng `cv2.imdecode(buf, IMREAD_REDUCED_COLOR_k)` với `k ∈ {1,2,4}` (giải nén giảm tỉ lệ ngay ở bước DCT, libjpeg-turbo, chạy **CPU**). Env `AI_DECODE_REDUCE=auto|1|2|4`; `auto` chọn `k` lớn nhất sao cho chiều rộng sau giảm ≥ `AI_IMGSZ` (640).
- **Lưu ý trung thực**: đây không phải GPU. `nvJPEG → GPU resize → ONNX IOBinding` mới là full-GPU nhưng phức tạp (binding + tensor GPU trong Docker). **Chỉ nâng cấp lên chuỗi đó nếu số đo cho thấy `decode+preprocess p95 > 10–15 ms/khung`** (xem tiêu chí ở §6). Chỉ dùng `nvJPEG` rồi copy về CPU là vô ích (2 lần qua PCIe).
- Việc decode **chỉ làm trong worker, ở nhịp AI**, không decode ở reader (reader chỉ nhận và lưu JPEG).

### 2.3. AI-Paced MJPEG (thay Fused WS)
Hai đường vẫn độc lập nhưng **cùng được "mở van" bởi một sự kiện kết quả AI**:

```
NvrChannelReader (HTTP MJPEG subtype=0)
   └► FramePacket{frame_id, jpeg_bytes, ts_capture} (RAM, chỉ giữ gói mới nhất)

GpuBatcher (1 thread, tick = 1/AI_TARGET_FPS)  ── luôn lấy khung MỚI NHẤT, không xếp hàng
   ├ decode (REDUCED) + preprocess tất cả cam có khung mới
   ├ GPU inference cho cả nhóm cam trong 1 lượt điều phối
   ├ FAST PATH: tracker + IoU snap + point_in_polygon  (vài ms)
   │    └► publish BBOX ngay (WS msg "bbox", chỉ cho cam vừa suy luận) + set Event(frame_id)
   └ SLOW PATH: rule engine 4 trạng thái, timeline, bộ đếm, SQLite  → WS msg "hud"

MJPEG endpoint /cameras/{id}/mjpeg:
   chờ Event(frame_id mới) HOẶC timeout VALVE_MS (~100 ms) → gửi jpeg_bytes MỚI NHẤT
```

Quy tắc bắt buộc:
1. **Van xả (`STREAM_VALVE_MS`, mặc định 100)**: video **không bao giờ đứng hình vì AI chậm**; hết timeout là xả khung mới nhất.
2. **Bỏ `sleep(0.04)`**: dùng `asyncio.Event`/Condition do thread AI đánh thức qua `loop.call_soon_threadsafe`.
3. **BBox chỉ được phát khi có suy luận mới của chính camera đó.** **Cấm** tái phát `last_tracked` (sửa R1). Khung suy luận ra 0 người → vẫn phát `bbox` với `persons: []` để client **xóa ngay**.
4. Đồng hồ HUD (`00:05`) vẫn chạy mỗi giây bằng tin `hud`, **không mang BBox**.
5. `bbox` message tối giản (không timeline, không nhãn dài):
```json
{"type":"bbox","cam_id":"ch17","frame_id":18342,"ts_capture":1.7e9,"inference_ms":21,
 "persons":[{"id":3,"x1":0.1,"y1":0.2,"x2":0.2,"y2":0.6,"foot_x":0.15,"foot_y":0.6,"conf":0.88,"in_zone":true}]}
```
6. `hud` message (≈1 Hz hoặc khi đổi trạng thái): `status, ui_color, status_label, sub_label, polygon_label, alert_count, total_alert_seconds, session_duration_seconds, timeline` (timeline chỉ khi thay đổi hoặc ≤ 1 lần/2 s).
7. WS gửi theo cơ chế **latest-wins**: nếu client chậm (hàng đợi gửi đầy) → bỏ tin `bbox` cũ, chỉ giữ tin mới nhất; không dồn hàng đợi.
8. Giữ tương thích: `/api/v1/ws/detections` vẫn là một kênh, phân loại bằng `type`; client cũ xử lý `detections` còn tồn tại trong thời gian chuyển đổi (cờ `WS_LEGACY_PAYLOAD=true`).

### 2.4. "GPU Batching" = `GpuBatcher` điều phối nhiều camera
Theo ý PM: **tận dụng GPU xử lý đồng thời nhiều camera**, không ép YOLO batch=4. Thiết kế:
- **Một thread GPU duy nhất** (`GpuBatcher`) gom khung mới nhất của mọi camera mỗi tick rồi đưa vào inference trong **một lượt** (không để mỗi camera một thread tranh GPU/GIL).
- Model hiện batch=1: `detect_batch()` đã hỗ trợ cả hai nhánh. **Không đổi model.** Nếu `session.get_inputs()[0].shape[0]` là dynamic thì tự gộp tensor; nếu cố định 1 thì chạy tuần tự trong lượt đó.
- Để đạt song song thật trên GPU khi batch=1, `bench_infer.py` (§6) so sánh **3 cấu hình** và chọn cái thắng, ghi vào `changelog.md`:
  - **S1**: 1 session, chạy tuần tự (baseline).
  - **S2**: 1 session, nhiều luồng gọi `run()` (ORT thread-safe) trên `CUDAExecutionProvider`.
  - **S3**: N session (N = số camera, tối đa 2–3) trong giới hạn VRAM 1.5 GB.
- Tham số ORT mặc định mới: `arena_extend_strategy=kNextPowerOfTwo`, `cudnn_conv_algo_search=EXHAUSTIVE` (warmup chậm hơn 1–3 s), `AI_VRAM_LIMIT_MB=1536`. Cũng benchmark `HEURISTIC` để đảm bảo `EXHAUSTIVE` thực sự nhanh hơn trước khi chốt.
- Model FP16: thử export FP16 trực tiếp từ `.pt` (`half=True`) *trong bench*; chỉ dùng nếu mAP/số người phát hiện tương đương bản FP32 trên `poc/report/ch17-snapshot.jpg` và ảnh mẫu của PM.

### 2.5. Tracker
- Giữ **ByteTrack + IoU snap** (PM yêu cầu). **Bỏ Majority Class Voting** (model chỉ có lớp `person`).
- Hộp gửi ra = **hộp YOLO thô của khung hiện tại** gán `track_id` bằng ghép IoU (Hungarian); chỉ khi không có hộp thô khớp (`IoU < 0.15`) mới dùng hộp Kalman và đánh dấu `predicted:true` (client vẽ nhạt hơn).
- `min_iou` snap mặc định **0.25** (env `AI_SNAP_MIN_IOU`), thay cho 0.45.

### 2.6. Frontend (áp dụng cho mọi thiết bị)
- **Xóa `backdrop-blur`** ở HUD và badge; nền HUD `rgba(15,23,42,0.40–0.48)` (vẫn trong suốt như PM muốn).
- Canvas `dpr` tối đa **1.5**; chỉ vẽ khi có `bbox` mới hoặc khi hết hạn; **không rAF vô hạn**.
- **BBox hết hạn theo thời gian nhận ở client**: `BBOX_STALE_SECONDS` giảm **3.0 → 0.7 s** (cấu hình được), tính từ lúc nhận tin `bbox` (không dùng `updated_at` phía server vì lệch đồng hồ). Quá hạn → xóa BBox ngay, không để đứng.
- Tạm dừng vẽ khi `document.hidden`; ô camera ngoài viewport (`IntersectionObserver`) ngừng nhận/hiển thị luồng (đóng `<img>`).
- Bỏ `probe` mỗi 30 s × 4 cam (số liệu trễ lấy từ `inference_ms`/`ts_capture`).
- `detection-store` tách 2 loại: `bbox` (vào canvas, 0 React render) và `hud` (≤ 1 Hz, vào HTML).

### 2.7. Băng thông (không hạ chất lượng)
- Đường hiển thị = JPEG gốc luồng chính, **mỗi khung đọc 1 lần từ NVR, phát lại cho mọi viewer** (thêm viewer chỉ tăng upload của `aiot`, không tăng tải NVR).
- Tin WS nhỏ (BBox) + `hud` thưa → băng thông WS không đáng kể.
- **Sự thật cần PM biết**: luồng chính có dung lượng/khung **lớn hơn** luồng phụ hiện tại. Mức tăng thật được **đo bằng `probe_nvr.py`** (§6). Nếu upload nhà máy/băng thông người xem không đủ, các lựa chọn giữ nguyên chất lượng nhưng giảm tải: (a) giảm FPS phát ra (không giảm độ phân giải/quality), (b) chỉ phát cam đang hiển thị (đã có ở §2.6). H.264 MSE (cũ Phase 5) **đã loại** vì cần RTSP.

### 2.8. SQLite (giữ nguyên từ v1)
- SQLAlchemy 2.x + **Alembic**; writer thread + queue (AI không chờ đĩa); file `/app/data/tranhan_poc.db`; PRAGMA `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`, `busy_timeout=5000`.
- Bảng: `cameras`, `alert_events(id, cam_id, started_at, ended_at, duration_s, peak_state)`, `runtime_snapshots(cam_id, alert_count, total_alert_seconds, session_started_at, timeline_json, saved_at)`, `app_settings`.
- `SqliteCameraRepository` implement Protocol `CameraRepository` hiện có (`list_all/get_by_id/save_all`), không đổi chữ ký.
- Migrate một lần từ `cameras.json` → đổi tên `.migrated` (không xóa). Snapshot runtime mỗi 10–15 s; nạp lại khi khởi động nếu `saved_at` ≤ 30 phút. Retention `alert_events` 90 ngày. Env `DB_BACKEND=sqlite|json` để rollback.
- Endpoint đọc lịch sử: `GET /api/v1/detections/{cam_id}/events?from=&to=`.

### 2.9. Python
Giữ **3.10**.

---

## 3. Kế Hoạch Thực Hiện Theo Giai Đoạn

| Phase | Nội dung | Nghiệm thu | Rollback |
|---|---|---|---|
| **0 — Script đo** | Viết các script ở §6 (không đổi hành vi hệ thống). PM `git pull`, chạy trên `aiot`, gửi kết quả. | Có số đo FPS/băng thông luồng chính, decode/preprocess ms, inference ms theo S1/S2/S3. | Không đổi code ứng dụng. |
| **1 — Sửa lỗi lõi** | R1, R2, R3, R4, R6, R7 (sửa `worker.py`, `nvr_stream.py`, `cameras.py`, `tracker.py`, cameras mặc định `subtype=0`); tách `bbox`/`hud`; `FramePacket` thống nhất; van xả; Event thay polling. | Hết "BBox đứng yên"; video đều nhịp; lệch ≤ 1–2 khung. | Cờ `WS_LEGACY_PAYLOAD`. |
| **2 — GpuBatcher + ORT** | Theo §2.4 sau khi có kết quả Phase 0 chọn S1/S2/S3; `AI_DECODE_REDUCE`; VRAM 1536; nâng `NVR_STREAM_FPS_LIMIT`/`AI_TARGET_FPS` theo số đo. | `infer_ms` và `e2e_ms` đạt §7. | Env về cấu hình cũ. |
| **3 — Frontend** | §2.6 (bỏ blur, dpr 1.5, stale 0.7 s, pause ẩn, tách store). | iGPU/CPU máy khách giảm rõ; BBox bám người. | Revert component. |
| **4 — SQLite** | §2.8 (song song được với 1–3). | Restart không mất bộ đếm/timeline. | `DB_BACKEND=json`. |
| **5 — (Điều kiện)** | Chỉ khi số đo cho thấy CPU decode quá chậm: `nvJPEG + GPU resize + IOBinding`. Chỉ khi IT mở 554: quay lại ffmpeg/NVDEC. | Báo cáo khả thi riêng. | — |

Thứ tự: **0 → 1 → (4 song song) → 2 → 3**; mỗi phase một commit, test trước khi sang phase sau.

---

## 4. Cấu Hình Dự Kiến

`.env` (thêm/đổi):
```
AI_VRAM_LIMIT_MB=1536
AI_SNAP_MIN_IOU=0.25
AI_DECODE_REDUCE=auto             # auto | 1 | 2 | 4
STREAM_VALVE_MS=100
BBOX_STALE_SECONDS=0.7            # dùng cho frontend qua GET /api/v1/config
WS_LEGACY_PAYLOAD=false
DB_BACKEND=sqlite                 # sqlite | json
DB_PATH=/app/data/tranhan_poc.db
ALERT_EVENT_RETENTION_DAYS=90
```
Mặc định camera: `subtype: 0`. `docker-compose.yml`: giữ `ports: ["28080:28080"]`; **không** cần `NVIDIA_DRIVER_CAPABILITIES=video` (chỉ cần nếu quay lại NVDEC). `Dockerfile` hiện chỉ `COPY backend/app` → phải thêm `COPY backend/scripts` (hoặc mount) để chạy script đo trong container.

Tài liệu cập nhật khi xong: `spec.md`, `deploy.md` (kết quả `nc` 554, cách chạy script đo), `changelog.md`, `pocv001/01_*`, `pocv001/02_*`, `issuse.md` (R1–R8).

---

## 5. Metrics Trong Hệ Thống

`GET /api/v1/metrics` (và log mỗi 10 s) theo từng camera: `fps_in`, `decode_ms`, `preprocess_ms`, `infer_ms`, `track_ms`, `e2e_ms` (capture→phát bbox), `bbox_msgs_per_s`, `mjpeg_valve_timeouts` (số lần van xả), `dropped_frames`, `ws_clients`, VRAM.

---

## 6. Script Đo (Phase 0) — Neon viết, PM chạy trên `aiot`

Vị trí: `poc/backend/scripts/bench/`. Chạy trong container (sau khi `COPY backend/scripts` hoặc mount):
`docker compose exec tranhan-poc python -m scripts.bench.<tên>`; kết quả ghi JSON + bản tóm tắt Markdown vào `poc/data/bench/` để PM dán lại cho chúng ta. Script **chỉ đọc**, không ghi cấu hình hệ thống, dừng gọn khi Ctrl+C, và đọc NVR credential từ `.env`.

| Script | Việc đo | Đầu ra chính |
|---|---|---|
| `probe_nvr.py` | Với mỗi kênh 16/17/18/21 và `subtype` 0 & 1 (để so sánh): mở MJPEG 15–20 s; ghi thời gian tới khung đầu, **FPS thực**, độ phân giải, kích thước JPEG (avg/p95 KB), **Mbps**, số lần stall >1 s; thử lại bằng `snapshot.cgi` 5 lần để lấy độ trễ. Lưu 20 JPEG mẫu/kênh vào `poc/data/bench/samples/`. Đo cả khi đọc **đồng thời 4 kênh** (đúng tải thật). | Bảng `luồng chính vs phụ`, quyết định `subtype=0` có dùng được không. |
| `bench_decode.py` | Trên JPEG mẫu: `imdecode` đầy đủ vs `REDUCED_2` vs `REDUCED_4`; `resize/letterbox/cvtColor`; p50/p95 ms; ước tính với 4 cam × FPS mục tiêu. | Khuyến nghị `AI_DECODE_REDUCE`; có/không cần Phase 5-nvJPEG theo ngưỡng §7. |
| `bench_infer.py` | Nạp `yolo26s.onnx` với CUDA EP; warmup; đo `infer_ms` cho 1–4 camera theo **S1/S2/S3** (§2.4) và `HEURISTIC` vs `EXHAUSTIVE`; số người phát hiện trên ảnh mẫu (so sánh nhất quán); VRAM thực (`nvidia-smi --query-gpu=memory.used`). Tùy chọn: so FP16 export nếu có file. | Chọn S1/S2/S3, xác nhận 1.5 GB đủ, tính **FPS AI tối đa** để nâng `AI_TARGET_FPS`. |
| `bench_ws_load.py` (tùy chọn, sau Phase 1) | Kết nối `N` client WS giả lập, đo `bbox_msgs_per_s`, byte/s, độ trễ phát. | Dung lượng WS và xác nhận không dồn hàng đợi. |

Ngưỡng ra quyết định từ số đo (ghi vào `changelog.md`):
- `decode+preprocess p95 ≤ 10 ms/khung` → giữ CPU `REDUCED` (không làm nvJPEG).
- `fps_in luồng chính ≥ 12` → dùng `subtype=0`; nếu thấp hơn mà vẫn ổn định → vẫn dùng (không về luồng phụ), báo PM.
- Tổng Mbps 4 kênh luồng chính cao hơn băng thông upload/download khả dụng → báo PM để chọn giảm FPS phát.

Đo phía trình duyệt (thủ công, ghi trước/sau): Chrome Task Manager (CPU/GPU Process), `chrome://gpu`, Performance Monitor Windows, và quay màn hình 60 fps khi người đi nhanh để kiểm độ lệch BBox.

---

## 7. Tiêu Chí Nghiệm Thu

| Chỉ số | Mục tiêu |
|---|---|
| BBox đứng yên | **0** trường hợp (R1 sửa; hết hạn client 0.7 s) |
| Lệch hình–BBox | ≤ 1–2 khung (mục tiêu thực tế khi người đi bình thường; không có trường hợp "cả chục khung") |
| FPS hiển thị/camera (4 cam đồng thời) | ≥ FPS nguồn đo được hoặc ≥ 12, đều nhịp, không khựng > 150 ms |
| `decode+preprocess` p95 | ≤ 10 ms/khung (nếu vượt → Phase 5-nvJPEG) |
| `infer_ms` cả nhóm 4 cam | đo trong Phase 0; mục tiêu đủ cho `AI_TARGET_FPS` ≥ FPS hiển thị |
| `e2e_ms` capture→phát bbox | mục tiêu < 250 ms (điều chỉnh theo số đo) |
| Van xả | Video không đứng khi AI khựng; `mjpeg_valve_timeouts` được log |
| VRAM | < 1.5 GB |
| Chất lượng ảnh | JPEG gốc luồng chính, **không recompress, không `subtype=1`** |
| Máy khách | Không còn `backdrop-blur`; CPU/GPU giảm so với trước (ghi số trước–sau) |
| SQLite | Restart giữ bộ đếm/timeline; ghi DB không tăng `e2e_ms` |
| Triển khai | `docker compose up -d --build`; 1 lệnh `docker compose down` dừng hết; port 28080 vẫn qua `https://tranhan.atin.vn/` |

---

## 8. Việc Còn Mở

1. **554**: đã xác nhận không thông (timeout) → Nhánh B. Chỉ xem lại nếu IT mở cổng.
2. **Băng thông WAN luồng chính** và **FPS thực `subtype=0`**: chờ kết quả `probe_nvr.py`.
3. **Model**: không cần export lại batch=4; chỉ cần nếu `bench_infer.py` chứng minh FP16/dynamic-batch đáng giá (khi đó mới nhờ team/Hydrogen/Neon export).
4. **H.264 MSE**: loại khỏi kế hoạch (cần RTSP).

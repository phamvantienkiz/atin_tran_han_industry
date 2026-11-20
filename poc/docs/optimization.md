# PoC v001 — Kế Hoạch Tối Ưu Hiệu Năng (Optimization Plan) — v3 (theo số đo benchmark)

> **Người thực hiện**: Hydrogen / Neon. Tài liệu chỉ mô tả thiết kế + kế hoạch; mã trong tài liệu là mẫu hợp đồng.
> **Trạng thái**: PM đã chốt các quyết định ở §7 (trễ hiển thị 0.45 s OK; cổng chất lượng ≥ hiện tại; VRAM 1.5 GB; 82 Mbps OK; chỉ ONNX/CUDA EP, không TensorRT, không yolo26n).
> **Nguồn số đo**: `poc/data/bench/{probe_nvr,bench_decode,bench_infer}.{md,json}` (chạy 2026-11-20 trên `aiot`).
> **Ràng buộc đã chốt**: Python 3.10; 1 port 28080; **không dùng luồng phụ làm nguồn**; chất lượng hiển thị **≥ hiện tại** (hiện tại = 640×480, ~7–13 KB/khung); VRAM AI tới 1.5 GB; thêm SQLite.

---

## 0. Kết Quả Benchmark Và Hệ Quả (đọc trước)

| # | Số đo | Hệ quả thiết kế |
|---|---|---|
| **B1** | **FPS nguồn ≈ 9.5 fps/kênh** ở **cả** `subtype=0` và `subtype=1`, không stall; TTFF 0.6–0.8 s. | 9.5 fps là **trần do NVR/CGI**, không phải do phần mềm ta. `12 fps` cũ vốn không đạt được. Phần "giật" có một phần **do nguồn**; phần mềm chỉ làm cho **đều nhịp**, không thể vượt 9.5 fps (chỉ cải thiện nếu IT/NVR nâng khung hình của MJPEG). |
| **B2** | Luồng chính 1920×1080: JPEG **228–308 KB/khung**; **4 kênh ≈ 82 Mbps** (luồng phụ 640×480: 3 Mbps). | **Phát nguyên JPEG gốc cho trình duyệt là bất khả thi** (≈ 82 Mbps/người xem). Phải **recompress/resize phía server** cho hiển thị (xem §2.2). Đây **thay đổi** quyết định "không recompress" ở v2. |
| **B3** | Giải mã 1080p đầy đủ: **~9 ms (p95 10.7)** + preprocess ~2.6 ms ⇒ **~12 ms/khung**. `REDUCED_2` **không nhanh hơn** (p95 25 ms, nhiễu). | Bỏ ý tưởng `AI_DECODE_REDUCE`. Vì hiển thị cũng cần ảnh giải mã, **decode full-res đúng 1 lần/khung**, dùng chung cho AI (resize 640) và hiển thị. 38 khung/s × ~12 ms ≈ **0.45 core** — chấp nhận được; **chưa cần nvJPEG**. |
| **B4** | YOLO `yolo26s.onnx` trên RTX A400: **~66 ms/khung (1 cam)**; **4 cam: nhóm ≈ 212–255 ms** ⇒ **chỉ 3.9–4.7 fps AI/cam**. S3 (3 session) chỉ nhanh hơn S1 ~1.2× nhưng VRAM **2.0–2.6 GB** (vượt 1.5 GB). `EXHAUSTIVE` ≈ `HEURISTIC` (trong nhiễu). | **GPU bão hòa (compute-bound), song song hóa nhiều session/luồng không đáng.** Điểm nghẽn thật của "BBox đi sau người" là **độ trễ + tần số suy luận thấp** (200+ ms, ~4–5 fps), không phải CPU. Cần tăng tốc suy luận trong ONNX/CUDA EP (FP16, imgsz, bớt khung) **và** thiết kế căn thời gian BBox theo khung (§2.3). |
| **B5** | `VRAM trước khi chạy = 1421 / 4094 MB`; ORT có cả `TensorrtExecutionProvider` nhưng **PM đã quyết không dùng**. | **Số đo B4 rất có thể bị nhiễu**: benchmark chạy trong container khi worker AI của app (và/hoặc process khác trên GPU dùng chung) đang chiếm GPU. Phải **đo lại sạch** (§5 Phase 0b) trước khi chốt con số. Cần đảm bảo `providers` chỉ gồm CUDA + CPU. |
| **B6** | Người phát hiện trên ảnh mẫu: ch16=15, ch17=15, ch18=6, ch21=3. | Model hoạt động; cảnh đông (15 người) làm NMS/postprocess tốn thêm. |

> Các **ước lượng** ở dưới (KB/khung sau nén, ms encode, tăng tốc FP16) chưa được đo; tài liệu ghi rõ và giao script đo ở §5.

---

## 1. Chẩn Đoán Nguyên Nhân Gốc (đối chiếu code)

| # | Lỗi | Vị trí | Triệu chứng |
|---|---|---|---|
| **R1** | Nhánh `idle_cams` tái phát BBox cũ (`last_tracked`) với `updated_at=time.time()` mới, kéo dài tới `_BBOX_STALE_SEC=1.5 s`; client lại stamp `_client_ts` lúc nhận. | `worker.py` ~L307-333 | **BBox đứng yên khi người đã đi xa** |
| **R2** | `_store_jpeg()` nhánh `else` ghép JPEG mới với `frame`/`seq` cũ. | `nvr_stream.py` ~L158-171 | Hình và AI lệch nhau |
| **R3** | `sleep(0.04)` polling trong `ram_iterator()`. | `cameras.py` ~L111-120 | Nhịp khung không đều |
| **R4** | Mỗi tin WS mang cả `timeline` 30 phút × 4 cam. | `worker.py`, `ws_hub.py` | JSON nặng |
| **R5** | `backdrop-blur` đè 4 `<img>` MJPEG; Canvas `dpr` tới 2. | `ZoneHudOverlay.tsx`, `CameraCard.tsx`, `CameraOverlayCanvas.tsx` | iGPU nóng, rAF tụt nhịp |
| **R6** | `_snap_box_to_raw(min_iou=0.45)` trả hộp Kalman khi IoU thấp. | `tracker.py` | BBox chậm pha khi đi nhanh |
| **R7** | Cameras mặc định `subtype=1`. | `camera_repository.py` | Chất lượng thấp |
| **R8** | Dữ liệu chỉ ở JSON + RAM. | `camera_repository.py`, `rule_engine.py` | Restart mất lịch sử |
| **R9** *(mới, từ B4)* | Mỗi camera ~66 ms/khung; suy luận tuần tự 4 cam ≈ 250 ms ⇒ BBox luôn cũ ≥ 250 ms, cập nhật 4–5 Hz so với video 9.5 Hz. | `detector.py`, `worker.py` | **BBox đi sau người** (kể cả khi R1–R6 đã sửa) |
| **R10** *(mới, từ B2)* | Phát nguyên JPEG luồng chính ≈ 82 Mbps/viewer. | `cameras.py` | Không thể xem qua domain/WAN |

---

## 2. Quyết Định Thiết Kế (đã điều chỉnh theo bench)

### 2.1. Nguồn và giải mã (1 lần, dùng chung)
- Nguồn: HTTP MJPEG **luồng chính `subtype=0`** (554 timeout ⇒ không RTSP/ffmpeg/NVDEC).
- Mỗi khung: **decode full-res 1 lần** (`cv2.imdecode`, IMREAD_COLOR). Từ ảnh giải mã đó tạo: (a) tensor AI (letterbox 640), (b) ảnh hiển thị (§2.2). Dùng `ThreadPoolExecutor` (cv2 nhả GIL) để 4 camera giải mã song song, thread GPU không bị chặn bởi decode.
- Reader chỉ nhận JPEG + gán `frame_id` + `ts_capture`; **không** ghép dữ liệu khác khung (sửa R2).
- `NVR_STREAM_FPS_LIMIT` → **0 (không giới hạn)**, vì nguồn chỉ 9.5 fps và hiển thị cần mọi khung.
- Bỏ `AI_DECODE_REDUCE`. nvJPEG chỉ xem xét lại nếu số đo CPU thực (Phase 0b) vượt ~70% số core.

### 2.2. Ảnh hiển thị: recompress/resize theo ngữ cảnh (thay cho "passthrough")
Passthrough = ~82 Mbps/viewer (B2) nên không khả thi. Thay bằng **hai tầng, cùng một nguồn luồng chính, mỗi khung mã hóa 1 lần rồi phát cho mọi viewer**:

| Ngữ cảnh | Kích thước | JPEG quality | Ước lượng KB/khung* | Ước lượng Mbps (9.5 fps) |
|---|---|---|---|---|
| **Lưới 1/4/6 ô** | **960×540** | **80** | ~35–60 | ~1.3–2.3 Mbps/cam (~5–9 cho 4 cam) |
| **Focus Modal** (1 cam) | **1920×1080** | **85** | ~100–180 | ~8–14 Mbps |

\* Ước lượng; `bench_encode.py` (§5) đo thật trước khi chốt.

- So với hiện tại (640×480, ~12 KB): **độ phân giải tăng ~1.7× ở lưới và 6.75× ở Focus** ⇒ thỏa "chất lượng ≥ hiện tại, không luồng phụ". Băng thông viewer **cao hơn hiện tại** nhưng thấp hơn passthrough 10–15 lần; đây là đánh đổi PM cần biết.
- Tầng được chọn bằng tham số kết nối (`?view=grid|focus`); camera không hiển thị (ẩn/ngoài viewport) không được phát.
- Ngưỡng (kích thước/quality) là **cấu hình**: `DISPLAY_GRID_W/Q`, `DISPLAY_FOCUS_W/Q`; PM duyệt sau khi xem ảnh mẫu do `bench_encode.py` xuất ra.
- Tải CPU thêm: resize + encode ~38 khung/s; ước lượng ≤ ~0.3–0.4 core, đo trong `bench_encode.py`.

### 2.3. Căn thời gian BBox theo khung (giải R9) — "Time-Aligned Delayed Playback"
Số đo cho thấy AI chỉ ~4–5 Hz với trễ 200+ ms; ghép "BBox mới nhất" lên "khung mới nhất" luôn lệch. Thiết kế:

1. Server giữ **ring buffer ngắn** các khung hiển thị (theo `ts_capture`) và **phát video trễ cố định `D`** (`STREAM_SYNC_DELAY_MS`, mặc định đề xuất 400–500 ms; điều chỉnh theo `infer` p95 đo ở Phase 0b: `D ≈ trễ AI p95 + 1 chu kỳ AI`).
2. AI chạy ở nhịp riêng (≈ 4–9 Hz/cam), lưu kết quả `(ts_capture, tracks)` vào lịch sử ngắn mỗi camera.
3. Khi tới lúc phát khung `t` (tức `now ≥ t + D`), server **nội suy** vị trí mỗi `track_id` giữa hai kết quả AI bao quanh `t` (nội suy tuyến tính; nếu thiếu kết quả sau → ngoại suy bằng vận tốc, đánh dấu `predicted:true`), rồi **gửi tin `bbox` (có `frame_id`) ngay trước/cùng lúc gửi khung đó**.
4. Hai đường (MJPEG `<img>` và WS) vẫn độc lập nhưng cùng được **lên lịch bởi một bộ phát duy nhất theo `frame_id`**, nên lệch ≤ ~1 khung (đúng mức PM chấp nhận). Không cần Fused binary WS.
5. **Van xả**: nếu AI ngừng trả kết quả quá `STREAM_VALVE_MS` thì khung vẫn phát (không BBox/BBox cũ biến mất nhờ client expiry), **video không bao giờ đứng**.
6. Đánh đổi (PM cần duyệt): **độ trễ hiển thị tăng ~D (≈0.4–0.5 s)** so với thời gian thực. Với giám sát hiện diện/cảnh báo 10 s thì chấp nhận được; nếu PM không chấp nhận độ trễ, đặt `STREAM_SYNC_DELAY_MS=0` ⇒ quay về chế độ "BBox mới nhất" (sẽ còn lệch ~200 ms, chỉ giảm bằng cách tăng tốc suy luận §2.4).

Tin `bbox` (tối giản, không timeline):
```json
{"type":"bbox","cam_id":"ch17","frame_id":18342,"ts_capture":1.7e9,"delay_ms":450,
 "persons":[{"id":3,"x1":0.1,"y1":0.2,"x2":0.2,"y2":0.6,"foot_x":0.15,"foot_y":0.6,"conf":0.88,"in_zone":true,"predicted":false}]}
```
`hud` (JSON, ≈1 Hz hoặc khi đổi): `status, ui_color, status_label, sub_label, polygon_label, alert_count, total_alert_seconds, session_duration_seconds, timeline`. `in_zone` trong `bbox` tính từ điểm chân đã nội suy (fast path); rule engine/timeline/SQLite chạy slow path.

Quy tắc giữ từ v2: **cấm** tái phát BBox cũ (R1); khung ra 0 người vẫn phát `bbox` rỗng; bỏ `sleep(0.04)`, dùng `asyncio.Event`/Condition; WS "latest-wins" khi client chậm.

### 2.4. Tăng tốc suy luận GPU (giải B4/R9)
Bench cho thấy GPU là điểm nghẽn. Thứ tự thử (mỗi bước đo bằng `bench_infer.py` mở rộng, **trên GPU sạch**):

1. **Đo lại sạch** (app AI dừng; ghi `nvidia-smi` các process dùng GPU). Dự kiến số liệu sẽ tốt hơn; lấy làm baseline mới.
2. ~~TensorRT EP~~ — **loại bỏ theo quyết định PM**: chỉ ONNX Runtime với `CUDAExecutionProvider`; không bật `TensorrtExecutionProvider` (đặt `providers` chỉ gồm CUDA + CPU để ORT không tự chọn TRT).
3. **CUDA EP + model FP16** (export từ `.pt` với `half=True`), so sánh số người phát hiện trên ảnh mẫu (B6: 15/15/6/3) — chấp nhận nếu tương đương.
4. **`imgsz` 512/480** (thử): chỉ dùng nếu số người phát hiện/độ chính xác chấp nhận được với PM (người nhỏ có thể mất).
5. **YOLO batch=2/4** chỉ như **thí nghiệm** (PM không yêu cầu): xuất ONNX batch cố định và đo; chỉ dùng nếu nhanh hơn rõ rệt trên GPU sạch.
6. **Giảm số khung phải suy luận**: chỉ chạy AI cho camera đã **vẽ vùng và bật**; điều phối công bằng (round-robin theo "khung mới nhất", không xếp hàng); tùy chọn *adaptive rate* (camera có người chuyển động nhận nhiều lượt hơn camera trống ổn định).
7. ~~Xin biến thể yolo26n~~ — **không thực hiện** theo quyết định PM.

Kết luận kỹ thuật tạm thời (đến khi có số đo sạch): **S1 (1 session, 1 thread GPU)**; **không** dùng S2/S3 (lợi ≤ 1.2×, VRAM vượt 1.5 GB); `cudnn_conv_algo_search=HEURISTIC` (bench không thấy lợi của `EXHAUSTIVE`); `arena_extend_strategy=kNextPowerOfTwo`; `AI_VRAM_LIMIT_MB=1536` áp cho arena (thêm ngữ cảnh CUDA/cuDNN nên VRAM thực của process cao hơn con số này — đo bằng `nvidia-smi --query-compute-apps`).

### 2.5. Tracker
Giữ **ByteTrack + IoU snap**; **bỏ Majority Class Voting** (1 lớp `person`). Hộp phát ra là **hộp YOLO thô** của khung suy luận đã gán `track_id` (Hungarian trên IoU); chỉ dùng hộp Kalman khi không có hộp thô khớp (IoU < 0.15) ⇒ `predicted:true`. `AI_SNAP_MIN_IOU` mặc định **0.25** (thay 0.45). Tracker lưu thêm vận tốc từng track để phục vụ nội suy/ngoại suy §2.3. `frame_rate` của ByteTrack đặt theo **nhịp AI thực tế/cam**, không đặt cứng 12.

### 2.6. Frontend (mọi thiết bị)
- Bỏ `backdrop-blur` (HUD, badge); HUD giữ nền `rgba(15,23,42,0.40–0.48)`.
- Canvas `dpr` ≤ 1.5; chỉ vẽ khi có `bbox` mới/hết hạn; không rAF vô hạn.
- BBox hết hạn ở client **0.7 s kể từ lúc nhận** (`BBOX_STALE_SECONDS`, lấy từ `GET /api/v1/config`), quá hạn xóa ngay.
- Pause khi `document.hidden`; ô ngoài viewport ngừng nhận luồng; Focus Modal dùng tầng `focus`, lưới dùng `grid`; đóng luồng ô đang bị Focus che.
- Bỏ `probe` 30 s × 4 cam; hiển thị `delay_ms`/`inference_ms` từ tin `bbox`.
- `detection-store` tách `bbox` (canvas, 0 React render) và `hud` (≤1 Hz).

### 2.7. SQLite (giữ nguyên)
SQLAlchemy 2.x + Alembic; writer thread + queue; `/app/data/tranhan_poc.db`; PRAGMA `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`, `busy_timeout=5000`. Bảng: `cameras`, `alert_events`, `runtime_snapshots`, `app_settings`. `SqliteCameraRepository` implement Protocol hiện có; migrate một lần từ `cameras.json` (đổi tên `.migrated`); snapshot runtime 10–15 s, nạp lại nếu ≤ 30 phút; retention 90 ngày; `DB_BACKEND=sqlite|json` để rollback; `GET /api/v1/detections/{cam_id}/events?from=&to=`.

### 2.8. Python
Giữ **3.10**.

---

## 3. Kiến Trúc Mục Tiêu

```
NVR HTTP MJPEG (subtype=0, 1080p, ~9.5 fps/cam, ~82 Mbps tổng)
   └► NvrChannelReader ×4: FramePacket{frame_id, ts_capture, jpeg_raw}
          └► DecodePool (thread, cv2 full-res decode 1 lần/khung)
                ├► ai_tensor (letterbox 640) ─► GpuWorker (1 thread, S1, ONNX CUDA EP)
                │         └► tracker (ByteTrack + IoU snap + vận tốc) ─► lịch sử (ts, tracks)
                │                    └► SLOW: rule engine, timeline, SQLite ─► WS "hud" ~1 Hz
                └► display_jpeg (grid 960x540 q80 / focus 1920x1080 q85, mã hóa 1 lần)
                          └► ring buffer theo ts_capture

Bộ phát duy nhất (theo frame_id), trễ cố định D:
   tới giờ phát khung t: nội suy tracks tại t ─► WS "bbox"(frame_id) + MJPEG part(frame_id)
   van xả: video không đứng nếu AI chậm
Browser: <img> MJPEG + <canvas> bbox/polygon (≤1.5 dpr, không blur) + HUD HTML ≤1 Hz
```

---

## 4. Cấu Hình Dự Kiến

```
NVR_STREAM_FPS_LIMIT=0
AI_TARGET_FPS=0                   # 0 = chạy hết khả năng GPU, luôn lấy khung mới nhất
AI_VRAM_LIMIT_MB=1536
AI_SNAP_MIN_IOU=0.25
AI_EP=auto                        # auto | cuda | cpu   (KHÔNG tensorrt)
DISPLAY_GRID_W=960   DISPLAY_GRID_Q=80
DISPLAY_FOCUS_W=1920 DISPLAY_FOCUS_Q=85
STREAM_SYNC_DELAY_MS=450          # 0 = tắt căn thời gian
STREAM_VALVE_MS=150
BBOX_STALE_SECONDS=0.7
WS_LEGACY_PAYLOAD=false
DB_BACKEND=sqlite
DB_PATH=/app/data/tranhan_poc.db
ALERT_EVENT_RETENTION_DAYS=90
```
Camera mặc định `subtype: 0`. `docker-compose.yml`: giữ `ports: ["28080:28080"]`; `AI_VRAM_LIMIT_MB=1536` (mức trần của nhóm vì GPU dùng chung). `Dockerfile` phải `COPY backend/scripts` để chạy script đo trong container. Cập nhật tài liệu khi xong: `spec.md`, `deploy.md`, `changelog.md`, `pocv001/01_*`, `pocv001/02_*`, `issuse.md` (R1–R10).

---

## 5. Kế Hoạch Theo Giai Đoạn

| Phase | Nội dung | Nghiệm thu | Rollback |
|---|---|---|---|
| **0b — Đo lại sạch & đo bổ sung** *(làm trước)* | Viết/mở rộng script (bảng dưới). PM: `docker compose stop` (giải phóng GPU của app) → chạy script trong container tạm (`docker compose run --rm`) → gửi lại kết quả. Ghi `nvidia-smi` (process dùng GPU, P-state, power limit, clock) trước/sau. | Có baseline sạch + so sánh FP32/FP16/imgsz/batch + số core CPU + kích thước/ms encode. | Không đổi hành vi app. |
| **1 — Sửa lỗi lõi** | R1, R2, R3, R4, R6, R7; `FramePacket`; `asyncio.Event`; tách `bbox`/`hud`; cameras `subtype=0`; bỏ `NVR_STREAM_FPS_LIMIT`. | Hết BBox đứng yên; nhịp khung đều (≈ 9.5 fps). | Cờ `WS_LEGACY_PAYLOAD`. |
| **2 — Pipeline hiển thị** | DecodePool dùng chung, hai tầng ảnh hiển thị (§2.2), ring buffer, `?view=grid|focus`, ngừng phát cam ẩn. | Băng thông viewer đúng bảng §2.2; CPU trong ngân sách. | Env về cấu hình cũ. |
| **3 — GPU & căn thời gian** | Chọn EP/model theo Phase 0b (§2.4); bộ phát duy nhất + nội suy (§2.3); tracker vận tốc; van xả. | BBox bám người; lệch ≤ ~1 khung; video không đứng khi AI khựng. | `STREAM_SYNC_DELAY_MS=0`, `AI_EP=cuda`. |
| **4 — Frontend** | §2.6. | CPU/GPU máy khách giảm; BBox hết hạn 0.7 s. | Revert component. |
| **5 — SQLite** | §2.7 (song song được). | Restart giữ bộ đếm/timeline. | `DB_BACKEND=json`. |
| **6 — (Điều kiện)** | nvJPEG/IOBinding chỉ khi CPU quá tải; ffmpeg/NVDEC chỉ khi IT mở 554. | Báo cáo riêng. | — |

### Script Phase 0b (Neon viết; vị trí `poc/backend/scripts/bench/`)
| Script | Việc đo | Đầu ra |
|---|---|---|
| `bench_encode.py` *(mới)* | Từ JPEG mẫu 1080p: decode → resize 960×540 / 1280×720 / 1920×1080 → encode JPEG q70/80/85/90: ms (p50/p95), **KB/khung thực**, Mbps ở 9.5 fps cho 1 và 4 cam; xuất ảnh mẫu cạnh nhau để PM duyệt chất lượng; đo CPU % tổng 4 cam song song bằng thread pool; ghi **số core CPU**. | Chốt `DISPLAY_*`, xác nhận ngân sách CPU. |
| `bench_infer.py` *(mở rộng)* | Chạy trên GPU sạch; thêm: CUDA EP FP16 (**không** TensorRT), `imgsz` 640/512/480, YOLO batch 1/2/4 (thí nghiệm), mức tải GPU (`nvidia-smi dmon`); đếm người trên ảnh mẫu để so độ nhất quán; VRAM **riêng process** (`--query-compute-apps`). | Chốt EP/model/imgsz; FPS AI/cam đạt được; `D` đề xuất = trễ p95 + 1 chu kỳ. |
| `probe_nvr.py` *(giữ, chạy lại tùy ý)* | Thêm 1 lần đo với `subtype=0` khi **không** có viewer; ghi nhận NVR có giới hạn số phiên MJPEG. | Xác nhận 9.5 fps là trần ổn định. |
| `bench_sync.py` *(sau Phase 3)* | Mô phỏng nguồn 9.5 fps + AI trễ thật; đo lệch `ts` giữa khung phát và BBox nội suy, tỷ lệ van xả. | Xác nhận lệch ≤ 1 khung. |

Đo phía trình duyệt (thủ công, ghi trước/sau): Chrome Task Manager, `chrome://gpu`, Performance Monitor Windows, quay màn hình 60 fps khi người đi nhanh.

---

## 6. Tiêu Chí Nghiệm Thu (điều chỉnh theo thực tế nguồn 9.5 fps)

| Chỉ số | Mục tiêu |
|---|---|
| BBox đứng yên | **0** trường hợp |
| Lệch hình–BBox | ≤ ~1 khung hiển thị (~100 ms) khi `STREAM_SYNC_DELAY_MS>0`; không còn "cả chục khung" |
| FPS hiển thị/cam | ≈ FPS nguồn (≈ 9.5), đều nhịp, không khựng > 200 ms |
| AI FPS/cam | Ghi nhận sau Phase 0b; mục tiêu ≥ 5 fps/cam (≥ 8 nếu FP16/imgsz nhỏ đạt); nội suy che phần còn thiếu |
| Độ trễ hiển thị tổng | ≈ `D` + < 150 ms (đề xuất ≤ ~0.6 s); PM duyệt |
| Băng thông viewer | Lưới 4 cam theo bảng §2.2 (ước ≤ ~9 Mbps); Focus ≤ ~14 Mbps; **không** phát luồng cam ẩn |
| CPU server | < 70% số core ở 4 cam × 9.5 fps (decode + resize + encode) |
| VRAM | Process AI < 1.5 GB (đo riêng process) |
| Chất lượng ảnh | Từ luồng chính 1080p; lưới ≥ 960×540 q80; Focus 1920×1080 q85; **không `subtype=1`** |
| Máy khách | Không `backdrop-blur`; CPU/GPU giảm rõ (ghi số trước–sau) |
| SQLite | Restart giữ bộ đếm/timeline; ghi DB không tăng độ trễ |
| Triển khai | `docker compose up -d --build`; 1 lệnh `docker compose down` dừng hết; 28080 vẫn qua `https://tranhan.atin.vn/` |

---

## 7. Quyết Định Của PM (đã chốt) Và Việc Còn Mở

**Đã chốt:**
1. **Độ trễ hiển thị `D ≈ 0.4–0.5 s`: CHẤP NHẬN.** Dùng `STREAM_SYNC_DELAY_MS=450` làm mặc định, tinh chỉnh theo số đo Phase 0b.
2. **Cổng chất lượng ảnh hiển thị (bắt buộc):** chất lượng thấp hơn hiện tại (640×480, ~7–13 KB) ⇒ **KHÔNG CHẤP NHẬN**; ngang bằng hoặc cao hơn ⇒ **CHẤP NHẬN**. Quy ước kiểm: độ phân giải hiển thị ≥ 640×480 **và** ảnh mẫu `bench_encode.py` không kém hơn ảnh luồng phụ hiện tại khi xem cạnh nhau (PM xem). Tuyệt đối không đặt cấu hình nào làm ảnh kém hơn hiện tại, kể cả khi băng thông cho phép.
3. **VRAM:** GPU dùng chung giữa app của ta và dev khác ⇒ **giới hạn của ta = 1.5 GB** (`AI_VRAM_LIMIT_MB=1536`, không vượt). Không cần truy tìm/phối hợp thêm; vẫn ghi `nvidia-smi` trước/sau khi đo để biết phần của ta (xem lưu ý đo ở Phase 0b).
4. **Băng thông NVR→aiot ≈ 82 Mbps liên tục: CHẤP NHẬN.** Nhóm tự quyết, không cần trao đổi nhà máy. Vẫn chỉ phát cho viewer các camera đang hiển thị.
5. **Chỉ chạy bằng ONNX Runtime (CUDA EP). KHÔNG TensorRT, KHÔNG xin yolo26n** trong đợt này. Mọi tối ưu suy luận nằm trong ONNX/CUDA EP: model FP16 ONNX (thử nghiệm), `imgsz`, giảm số khung suy luận (§2.4 mục 2–5).

**Còn mở:**
- **FPS 9.5** là trần của NVR (cả hai luồng); chỉ cải thiện nếu IT chỉnh cấu hình khung hình MJPEG/CGI của đầu ghi (ngoài phạm vi phần mềm).
- Nếu sau Phase 3, số đo sạch cho thấy AI/cam vẫn < ~5 fps, nội suy §2.3 bù phần thiếu; mọi hướng khác (TensorRT, model nhỏ hơn) cần PM mở lại.

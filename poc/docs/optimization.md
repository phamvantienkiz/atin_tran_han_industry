# PoC v001 — Kế Hoạch Tối Ưu Hiệu Năng (Optimization Plan) — v4 (Ưu Tiên Tuyệt Đối Video Live View Mượt, Sửa Ít Nhất Có Thể)

> **Trạng thái**: **ĐÃ TRIỂN KHAI & HOÀN TẤT** (Commit `e06a6fd`, `143b0cc`, `c7592a7`, `932f1e5`). Ngoài kiến trúc *Video Zero-Wait, AI Best-Effort* bên dưới, hệ thống đã bổ sung thêm `GridFrameCache` (`ram-grid-cache`, `854px`, `Q=68`) cho Grid View và `1-cam overlap prefetch` cho GPU AI.
> **Mục tiêu cốt lõi của v4 (theo yêu cầu mới nhất của PM)**:
> - **Đưa Video Live View trở lại mượt mà, ổn định tuyệt đối**, không bao giờ bị giật khung hình.
> - **Tách rời hoàn toàn (100% Decoupled)** đường phát Video MJPEG ra khỏi đường AI / Pacer / Van xả: Video đến từ NVR là đẩy thẳng tới trình duyệt ngay lập tức.
> - **Chấp nhận BBox chậm hơn hình một chút** (BBox chạy ở nhịp riêng của GPU AI, có kết quả mới tới đâu vẽ tới đó, không giữ chân hay làm trễ luồng video).
> - **Sửa ít nhất có thể (Surgical Minimal Diff)** trên code hiện tại; giữ lại những phần đã làm tốt và hoạt động ổn định (SQLite, tách WS `bbox` / `hud`, xóa lỗi re-stamp BBox cũ `R1`, bỏ `backdrop-blur` trên Frontend).

---

## 1. Chẩn Đoán Chính Xác: Tại Sao Bản Triển Khai v3 Làm Video Bị Giật Liên Tục?

Qua kiểm tra trực tiếp code vừa triển khai trong [display_pipeline.py](file:///e:/ATIN/atin_tran_han_industry/poc/backend/app/ai/display_pipeline.py) và [cameras.py](file:///e:/ATIN/atin_tran_han_industry/poc/backend/app/api/v1/endpoints/cameras.py), có **4 nguyên nhân trực tiếp** đã phá vỡ độ mượt tự nhiên của luồng video MJPEG:

| # | Thủ phạm trong code v3 (`display_pipeline.py` & `cameras.py`) | Cơ chế gây giật video liên tục |
|---|---|---|
| **G1** | **Van xả `STREAM_VALVE_MS = 150ms` xung đột trực diện với `STREAM_SYNC_DELAY_MS = 450ms`** (`cameras.py` L140–151) | `pacer_loop` đang giữ các khung hình trễ **450 ms** (`t - 450ms`), nhưng cứ sau **150 ms** không thấy khung mới, `asyncio.wait_for(ev.wait(), timeout=0.15)` lại kích hoạt **van xả** lấy `latest_decoded` (khung ở thời điểm `t = 0ms`, nhảy cóc qua toàn bộ ring buffer!) và đặt `last_frame_id = latest_df.frame_id`. Sau đó suốt **300 ms tiếp theo**, mọi khung trong ring buffer có `frame_id < last_frame_id` bị bỏ qua hết (`df.frame_id <= last_rel`) → **video nhảy cóc 1 phát rồi đứng hình 300–450 ms, lặp đi lặp lại liên tục!** |
| **G2** | **Chạy `cv2.resize` + `cv2.imencode` đồng bộ ngay bên trong coroutine `async def ram_iterator()`** (`cameras.py` L129, L149) | Hàm `display_pipeline.encode_for_viewer(df, view)` chạy thuật toán nén JPEG bằng CPU ngay trên **main `asyncio` event loop** của FastAPI/Uvicorn. Với 4 luồng MJPEG đang mở cùng lúc, event loop bị khóa cứng hàng chục ms mỗi lần nén ảnh → các chunk HTTP MJPEG và gói WebSocket bị nghẽn và đẩy ra giật cục. |
| **G3** | **Bắt mọi khung hình hiển thị phải xếp hàng chờ `DecodePool` giải mã 1080p (`cv2.imdecode`) trên CPU** (`display_pipeline.py` L264–309) | Thay vì nhận byte JPEG từ NVR và phát ngay, mọi khung hình đều bị đẩy vào `ThreadPoolExecutor(max_workers=4)` giải mã 1920×1080 (`~10–25 ms`) tranh chấp GIL và CPU với luồng AI (`worker.py`), làm thời điểm khung hình sẵn sàng bị jitter nặng. |
| **G4** | **`BBOX_STALE_SECONDS = 0.7s` quá ngắn so với chu kỳ AI thực tế (~250ms/vòng 4 cam)** | Khi AI chạy ~4 FPS/cam, chỉ cần 1 nhịp trễ nhẹ là BBox vượt quá 0.7s và bị xóa chớp tắt trên màn hình. |

---

## 2. Phương Án Điều Chỉnh Tối Giản (Surgical Plan — Sửa Ít Nhất, Video Mượt Ngay)

### Nguyên lý vàng của v4: **"Video Zero-Wait, AI Best-Effort"**
1. **Đường Video Live View (`NvrChannelReader` $\rightarrow$ `GET /api/v1/cameras/{id}/mjpeg`)**:
   - **KHÔNG** đi qua `pacer_loop`, **KHÔNG** giữ trễ `450 ms`, **KHÔNG** dùng van xả `150 ms`, **KHÔNG** chạy `cv2.imencode` trên `asyncio` event loop.
   - Ngay khi `NvrChannelReader` nhận được 1 bức ảnh JPEG hoàn chỉnh (`SOI..EOI`) từ NVR:
     - Lưu thẳng `pkt` (`jpeg_bytes`, `seq`) vào `self._latest`.
     - Đánh thức (`ev.set()`) tất cả các client MJPEG đang xem camera đó **ngay lập tức (0 ms giữ trễ)**.
     - `ram_iterator()` chỉ việc `yield _format_mjpeg_part(pkt.jpeg_bytes)` (hoặc `pkt.display_jpeg` nếu có bật giảm dung lượng ở background thread của reader) và chờ `await ev.wait()`.
2. **Chất lượng & Băng thông luồng Video (Cấu hình linh hoạt, mặc định không chạm CPU)**:
   - Với luồng từ NVR:
     - **Chế độ mặc định (`DISPLAY_REENCODE=false`)**: Phát **trực tiếp 100% `pkt.jpeg_bytes` gốc của NVR** (0 tốn CPU decode/encode trên đường hiển thị, độ mượt ngang bằng 100% xem trực tiếp từ NVR).
     - *(Lưu ý thực tế về `subtype`)*: Nếu xem từ xa qua internet bị nghẽn do đường truyền mạng của người xem không tải nổi 80 Mbps (4 cam 1080p MJPEG gốc), cho phép chỉnh trên giao diện Cài đặt Camera (`subtype=0` Chính hoặc `subtype=1` Phụ) hoặc bật `DISPLAY_REENCODE=true` (nén nhẹ ở chính thread `NvrChannelReader` trước khi gán `pkt`, tuyệt đối không nén trong `asyncio` loop).
3. **Đường AI & BBox (`PersonZoneDetector` $\rightarrow$ WebSocket)**:
   - Chạy **hoàn toàn độc lập** ở background thread.
   - Mỗi vòng lặp: lấy `pkt = stream_manager.latest(cam_id)` mới nhất hiện có $\rightarrow$ tự gọi `cv2.imdecode` cho riêng những khung mà AI thực sự đem đi suy luận (tức là chỉ decode ~15 khung/giây thay vì phải decode toàn bộ 38 khung/giây của cả 4 camera!).
   - Suy luận YOLO ONNX (`CUDAExecutionProvider`, `AI_VRAM_LIMIT_MB=1536`) + `ByteTrack` (`snap_min_iou=0.25`) xong camera nào $\rightarrow$ **bắn ngay tin WS `bbox` của camera đó** (và tin `hud` 1 Hz).
   - **Không giữ lại BBox để chờ hình, cũng không giữ hình để chờ BBox**. BBox đến trễ hơn hình ~150–250 ms theo đúng tốc độ tự nhiên của GPU (PM đã chấp nhận).
   - Tăng `BBOX_STALE_SECONDS` từ `0.7` lên **`1.8` giây** чтобы BBox không bị chớp tắt giữa 2 lượt GPU suy luận, nhưng vẫn tự biến mất sạch khi mất luồng (vì lỗi R1 re-stamp BBox cũ trong `idle_cams` đã được xóa bỏ).

---

## 3. Danh Sách Thay Đổi Tối Thiểu (Chỉ 3 File Backend, Không Đụng Frontend & SQLite)

Để sửa ít nhất và an toàn nhất, **giữ nguyên 100% Frontend và tầng SQLite hiện tại**, chỉ rút gọn đường ống ở **3 file Backend** sau:

### 3.1. [poc/backend/app/core/config.py](file:///e:/ATIN/atin_tran_han_industry/poc/backend/app/core/config.py)
Đổi giá trị mặc định để tắt toàn bộ cơ chế giữ trễ / van xả gây giật:
```python
    STREAM_SYNC_DELAY_MS: int = 0       # 0 = Phát video ngay lập tức (Zero-Wait), không giữ trễ
    BBOX_STALE_SECONDS: float = 1.8     # Đủ giữ BBox mượt giữa các chu kỳ GPU ~250ms mà không chớp tắt
```

### 3.2. [poc/backend/app/api/v1/endpoints/cameras.py](file:///e:/ATIN/atin_tran_han_industry/poc/backend/app/api/v1/endpoints/cameras.py) (`GET /api/v1/cameras/{cam_id}/mjpeg`)
Đưa `ram_iterator()` về cơ chế **Direct Event-Driven Passthrough** siêu nhẹ (0 decode, 0 re-encode trên `asyncio` loop, 0 van xả xung đột):
- Đăng ký `ev = stream_manager.register_waiter(cam_id)` trực tiếp trên `NvrStreamManager`.
- Vòng lặp `ram_iterator()`:
  ```python
  async def ram_iterator() -> AsyncIterator[bytes]:
      ev = stream_manager.register_waiter(cam_id)
      last_seq = -1
      try:
          while not await request.is_disconnected():
              pkt = stream_manager.latest(cam_id)
              if pkt is None or pkt.subtype != requested_sub:
                  break
              if pkt.seq != last_seq:
                  last_seq = pkt.seq
                  yield _format_mjpeg_part(pkt.jpeg_bytes)
              ev.clear()
              try:
                  await asyncio.wait_for(ev.wait(), timeout=1.0)
              except asyncio.TimeoutError:
                  continue
      finally:
          stream_manager.unregister_waiter(cam_id, ev)
  ```
- **Tác dụng**:
  - Ngay mili-giây `NvrChannelReader` cắt xong 1 bức JPEG từ NVR, `ev.set()` đánh thức `ram_iterator()` và đẩy nguyên byte `pkt.jpeg_bytes` xuống trình duyệt.
  - Không còn `encode_for_viewer()` chặn `asyncio` loop, không còn xung đột `150ms valve vs 450ms delay`.

### 3.3. [poc/backend/app/ai/nvr_stream.py](file:///e:/ATIN/atin_tran_han_industry/poc/backend/app/ai/nvr_stream.py) & [poc/backend/app/ai/worker.py](file:///e:/ATIN/atin_tran_han_industry/poc/backend/app/ai/worker.py)
1. **Trong `NvrStreamManager` (`nvr_stream.py`)**:
   - Bổ sung `bind_loop(loop)`, `register_waiter(cam_id) -> asyncio.Event`, `unregister_waiter(cam_id, ev)`.
   - Khi `NvrChannelReader._store_jpeg()` lưu `pkt` mới (`seq += 1`), gọi callback đánh thức các `asyncio.Event` của `cam_id` đó qua `loop.call_soon_threadsafe(ev.set)` và đánh thức luồng AI (`ai_wake_event.set()`).
2. **Trong `PersonZoneDetector._run_stream_cycle()` (`worker.py`)**:
   - Bỏ sự phụ thuộc vào `DisplayAndSyncPipeline` (tắt `display_pipeline.start()` và `submit_raw_packet` để không giải mã 100% mọi frame 1080p một cách lãng phí).
   - Ở mỗi chu kỳ AI:
     - Với từng camera trong `target_cams`, lấy `pkt = self._stream_manager.latest(cam_id)`.
     - Nếu `pkt.seq != self._last_frame_id.get(cam_id)`: chỉ lúc này mới gọi `cv2.imdecode(np.frombuffer(pkt.jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)` cho đúng khung hình mà AI sắp xử lý!
     - Sau khi chạy `detect_batch()` cho từng camera (hoặc bắn ngay sau mỗi camera để giảm độ trễ BBox): gọi `self._tracker.update(...)` $\rightarrow$ `self._evaluate_camera(...)` $\rightarrow$ bắn ngay `self._on_bbox(...)` và `self._emit_hud_if_needed(...)`.

> **Cải tiến nhỏ nhưng hiệu quả lớn trong `worker.py` (Per-Camera Immediate BBox Push)**:
> Vì `yolo26s.onnx` có `batch=1`, thay vì đợi chạy xong cả 4 camera (`~240 ms`) rồi mới lặp qua kết quả để bắn `on_bbox`, trong vòng lặp qua `ready_cams`, **chạy xong YOLO + Tracker của camera nào là gọi `self._on_bbox(...)` cho camera đó ngay lập tức** (chỉ mất `~60 ms` kể từ lúc lấy frame của camera đó).

---

## 4. Những Hạng Mục Giữ Nguyên Từ Đợt Nâng Cấp Trước (Không Cần Sửa Lại)

Các phần sau đây đã được implement sạch và không gây giật video, nên **giữ nguyên 100%**:
1. **Sửa lỗi R1 (BBox đứng yên)**: Nhánh `idle_cams` trong `worker.py` chỉ cập nhật đồng hồ HUD, tuyệt đối không tái phát `last_tracked` cũ.
2. **Tách kênh WebSocket `bbox` (nhẹ, không kèm `timeline`) và `hud` (1 Hz) + Latest-Wins Sender (`ws_hub.py`)**.
3. **Cấu hình ONNX Runtime CUDA EP**: `AI_VRAM_LIMIT_MB=1536`, `arena_extend_strategy=kNextPowerOfTwo`, chỉ dùng `CUDAExecutionProvider` + `CPUExecutionProvider` (không TensorRT).
4. **Tối ưu Frontend (`CameraCard.tsx`, `ZoneHudOverlay.tsx`, `CameraOverlayCanvas.tsx`)**: Đã bỏ `backdrop-blur`, giới hạn `dpr <= 1.5`, tạm dừng khi tab ẩn.
5. **Tầng lưu trữ SQLite (`sqlite_store.py`, `camera_repository.py`)**: Chạy trên writer thread riêng với `WAL mode`, hoàn toàn không chạm vào luồng video.

---

## 5. Tiêu Chí Nghiệm Thu Sau Khi Chỉnh Sửa (v4)

| Chỉ số | Mục tiêu nghiệm thu |
|---|---|
| **Độ mượt Video Live View** | **Mượt tuyệt đối theo đúng nhịp gốc của NVR (~9.5 FPS)**, 0 giật lùi, 0 nhảy cóc, 0 nghẽn event loop |
| **Tải CPU đường hiển thị** | **0% CPU decode/encode trên đường phát MJPEG** (truyền thẳng `pkt.jpeg_bytes` bằng `asyncio.Event`) |
| **Tải CPU đường AI** | Giảm **> 60%** so với v3 (chỉ `cv2.imdecode` các khung mà GPU thực sự lấy đi suy luận, không decode mọi khung hình) |
| **Hành vi BBox** | Bám theo người ở nhịp tự nhiên của GPU, cho phép chậm hơn hình một chút (~100–250 ms), **0 đứng yên bóng ma**, **0 chớp tắt** (`BBOX_STALE_SECONDS = 1.8s`) |
| **Số file cần sửa** | Chỉ **3–4 file Backend** (`config.py`, `cameras.py`, `nvr_stream.py`, `worker.py` / `main.py`), **0 file Frontend** |

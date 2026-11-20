# API Contract (Frontend Consumer) — `poc/frontend`

> Tài liệu mô tả chính xác các API REST, WebSocket và Stream URL mà `poc/frontend` tiêu thụ từ `poc/backend`.

---

## 1. REST Endpoints (`src/lib/api.ts`)

Mọi request sử dụng `fetch` với timeout mặc định `15000 ms` (`AbortController`). Khi backend trả lỗi JSON (`error.message` hoặc `detail`), `request<T>` trích xuất thông báo lỗi hiển thị lên Toast hoặc Form error.

| Nhóm | Hàm trong `api` | Method & Path | Ghi chú |
| :--- | :--- | :--- | :--- |
| **Config** | `api.config()` | `GET /api/v1/config` | Lấy `nvr_host`, `ws_path`, `bbox_stale_seconds` |
| **Cameras** | `api.cameras()` | `GET /api/v1/cameras` | Danh sách camera, frontend sort tăng dần theo `channel` |
| | `api.addCamera(body)` | `POST /api/v1/cameras` | Tạo camera mới (`CameraCreatePayload`) |
| | `api.updateCamera(id, body)` | `PUT /api/v1/cameras/{id}` | Cập nhật thông tin camera (`CameraUpdatePayload`) |
| | `api.deleteCamera(id)` | `DELETE /api/v1/cameras/{id}` | Xóa camera |
| | `api.saveZone(id, points)` | `PUT /api/v1/cameras/{id}/zone` | Lưu mảng `ZonePoint[]` chuẩn hóa `0..1` |
| | `api.probeCamera(id)` | `GET /api/v1/cameras/{id}/probe` | Kiểm tra trạng thái online NVR cho camera đầu tiên |
| **Detections** | `api.detections(focusCamId)` | `GET /api/v1/detections` | Dùng cho fallback polling khi WebSocket ngắt |
| | `api.setDetectionFocus(camId)` | `POST /api/v1/detections/focus` | Đồng bộ focus camera qua REST song song với WS |
| | `api.resetDetectionStats(camId)` | `POST /api/v1/detections/{id}/reset-stats` | Reset bộ đếm cảnh báo và timeline trên HUD |
| **Recording** | `api.startRecord(id, min, sub)` | `POST /api/v1/cameras/{id}/record/start` | Bắt đầu ghi `.mp4` (`5`/`10`/`20` phút) |
| | `api.stopRecord(id)` | `POST /api/v1/cameras/{id}/record/stop` | Dừng ghi hình |
| | `api.activeRecords()` | `GET /api/v1/records/active` | Poll mỗi `1000 ms` ở `HomePage` để cập nhật timer trên Topbar |
| **Dataset** | `api.listVideos()` | `GET /api/v1/storages/videos` | Liệt kê `.mp4` trong `DatasetView` |
| | `api.deleteVideo(filename)` | `DELETE /api/v1/storages/videos/{filename}` | Xóa file `.mp4` |
| | `api.extractFrames(filename, skip)` | `POST /api/v1/storages/videos/{filename}/extract` | Tách frame (`skip_frames`: `5` hoặc `10`) |
| | `api.listFrameSets()` | `GET /api/v1/storages/frames` | Liệt kê bộ ảnh frame |
| | `api.deleteFrameSet(folder)` | `DELETE /api/v1/storages/frames/{folder}` | Xóa bộ ảnh frame |

---

## 2. Media Stream & Direct Download URLs

Các thẻ `<img>` và `<a download>` trỏ trực tiếp tới các URL sau:

- **Grid MJPEG (`CameraCard`)**:
  `/api/v1/cameras/{id}/mjpeg?subtype={cam.subtype}&view=grid&t={streamTick}`
- **Focus MJPEG (`FocusModal`)**:
  `/api/v1/cameras/{id}/mjpeg?subtype=0&view=focus&t={streamTick}`
- **Snapshot Polling (`CameraCard` khi `mode === 'snapshot'`)**:
  `/api/v1/cameras/{id}/snapshot.jpg?t={timestamp}` (chu kỳ `1500 ms`)
- **Snapshot Nền Vẽ Vùng (`CameraCard` khi `editingZone === true`)**:
  `/api/v1/cameras/{id}/snapshot.jpg?direct=true&t={timestamp}`
- **Tải video / xem & tải bộ frame (`DatasetView`)**:
  - `/api/v1/storages/videos/{filename}/download`
  - `/api/v1/storages/frames/{folder}/preview/{image}`
  - `/api/v1/storages/frames/{folder}/download.zip`

---

## 3. WebSocket Protocol (`src/lib/ws-client.ts`)

- **URL kết nối**: Tự động suy ra `ws:` hoặc `wss:` theo `window.location.protocol`, ghép với `cfg.ws_path` (mặc định `/api/v1/ws/detections`).
- **Message gửi lên Server**:
  - `{"type": "focus", "cam_id": "<cam_id>" | null}` khi người dùng mở/đóng `FocusModal`.
- **Message nhận từ Server**:
  - `type === "bbox"` -> `detectionStore.updateBbox(msg)`
  - `type === "hud"` -> `detectionStore.updateHud(msg)`
  - `type === "detections"` -> `detectionStore.updateAll(msg.data)`
- **Cơ chế dự phòng (Fallback)**:
  - Khi WS gặp lỗi hoặc bị đóng (không phải chủ động `stop()`), client lập tức bật polling `GET /api/v1/detections` mỗi `1000 ms` và thử reconnect WS mỗi `2000 ms`. Khi WS mở lại thành công, polling tự động dừng.

# API Contract — ATIN Trần Hân AI Backend (`/api/v1`)

> Tài liệu đặc tả chi tiết toàn bộ REST API + WebSocket của `poc/backend` (PoC v0.0.1) và các hợp đồng tích hợp hệ thống **ATIN Smart VMS** (chuẩn Production).

---

## 1. Quy ước chung & Tiêu chuẩn Thiết kế

### 1.1. Base URL & Versioning
- **Base Prefix:** `/api/v1` (mọi endpoint REST và WebSocket nghiệp vụ đặt sau prefix này).
- **OpenAPI / Swagger UI:** `GET /docs` (khi bật `DEBUG=true`, mặc định `true` trong PoC).

### 1.2. Headers xuyên suốt (Middleware)
Mọi HTTP response đều đi qua chuỗi middleware tại `app/middlewares/__init__.py` (`ErrorHandling` -> `CORS` -> `RequestLogging` -> `RateLimit` -> `RequestID`) và trả về:
- `X-Request-ID`: UUIDv4 tự sinh (hoặc giữ nguyên giá trị client gửi lên qua header `X-Request-ID`).
- `X-Process-Time`: Thời gian xử lý request ở server (VD: `7.35ms`).

### 1.3. Cấu trúc Lỗi Thống nhất (Consistent Error Envelope)
Mọi lỗi nghiệp vụ (`404`, `409`, `422`, `429`, `500`, `502`, `503`) trả về JSON chuẩn hóa (vẫn giữ trường `detail` để tương thích ngược):

```json
{
  "success": false,
  "statusCode": 404,
  "message": "Camera 'ch99' không tồn tại",
  "detail": "Camera 'ch99' không tồn tại",
  "error": {
    "code": "NOT_FOUND",
    "details": null
  },
  "meta": {
    "timestamp": "2026-11-20T09:20:00+00:00",
    "path": "/api/v1/cameras/ch99",
    "requestId": "b025990d-37be-4a66-8789-0dd5fc7123e6"
  }
}
```

| HTTP Code | `error.code` | Ý nghĩa |
| :---: | :--- | :--- |
| `404` | `NOT_FOUND` | Không tìm thấy camera, job ghi hình, video hoặc thư mục frame |
| `409` | `CONFLICT` | Xung đột trạng thái (VD: camera đang ghi hình mà gọi `record/start` lần nữa) |
| `422` | `VALIDATION_ERROR` | Dữ liệu đầu vào sai quy tắc (VD: `duration_minutes` không thuộc `{5, 10, 20}`, tên file có `..`) |
| `429` | `RATE_LIMIT_EXCEEDED` | Vượt quá `RATE_LIMIT_PER_MINUTE` (mặc định `600` req/phút/IP) |
| `500` | `INTERNAL_SERVER_ERROR` | Lỗi không lường trước (không rò rỉ stack trace, tra log theo `requestId`) |
| `502` | `UPSTREAM_ERROR` | Lỗi kết nối hoặc phản hồi bất thường từ NVR |
| `503` | `UPSTREAM_ERROR` | Chưa cấu hình `NVR_HOST` / `NVR_USER` / `NVR_PASS` trong `.env` |

---

## 2. System & Observability Endpoints

### 2.1. `GET /api/v1/health`
Kiểm tra tình trạng sống của dịch vụ.
- **Response `200 OK`:**
  ```json
  { "status": "ok" }
  ```

### 2.2. `GET /api/v1/config`
Lấy thông tin cấu hình hiển thị, WebSocket path, AI runtime và các ngưỡng mặc định cho Frontend.
- **Response `200 OK`:**
  ```json
  {
    "nvr_host": "nmts2025.smartddns.tv",
    "nvr_port": 80,
    "project": "ATIN Smart Fishing",
    "environment": "poc",
    "atin_vms_enabled": false,
    "timeline_window_sec": 1800,
    "ws_path": "/api/v1/ws/detections",
    "ai_runtime": "auto",
    "active_provider": "CUDAExecutionProvider",
    "grace_seconds": 2.0,
    "warning_seconds": 10.0,
    "bbox_stale_seconds": 1.8,
    "stream_sync_delay_ms": 0,
    "ws_legacy_payload": false
  }
  ```

### 2.3. `GET /api/v1/metrics`
Lấy số liệu hiệu năng runtime của AI worker, `GridFrameCache` và số kết nối WebSocket đang hoạt động.
- **Response `200 OK`:**
  ```json
  {
    "active_provider": "CUDAExecutionProvider",
    "ws_clients": 2,
    "cameras": {
      "ch16": {
        "grid_viewers": 1,
        "focus_viewers": 0,
        "raw_kb": 148.2,
        "grid_kb": 42.6,
        "encode_ms": 4.8,
        "dropped": 0,
        "grid_fps": 12.0,
        "decode_prep_ms": 6.1,
        "infer_ms": 21,
        "track_ms": 0.45,
        "e2e_ms": 39
      }
    }
  }
  ```

---

## 3. Cameras & Zone Endpoints

### 3.1. `GET /api/v1/cameras`
Lấy danh sách camera và tọa độ zone đã cấu hình (sắp xếp theo `sort_order`, `channel`).
- **Query Parameters (tùy chọn):**
  - `enabled` (`bool`, optional): Lọc theo trạng thái bật/tắt (`true` / `false`).
  - `search` (`string`, optional, max 120): Tìm kiếm không phân biệt hoa thường theo `id`, `name`, `note`.
- **Response `200 OK`:**
  ```json
  [
    {
      "id": "ch16",
      "channel": 16,
      "name": "Tăng trọng 1",
      "zone_name": "Khu vực máy tăng trọng 1",
      "note": "",
      "subtype": 0,
      "mode": "mjpeg",
      "feature_type": "zone_presence",
      "grace_seconds": 2.0,
      "warning_seconds": 10.0,
      "enabled": true,
      "zone": [
        { "x": 0.0797, "y": 0.1355 },
        { "x": 0.7407, "y": 0.9639 },
        { "x": 0.8373, "y": 0.7108 }
      ]
    }
  ]
  ```

### 3.2. `POST /api/v1/cameras`
Thêm camera mới vào cấu hình PoC.
- **Request Body (`CameraCreate`):**
  ```json
  {
    "channel": 25,
    "name": "Cổng kho lạnh",
    "zone_name": "Khu vực cửa kho",
    "note": "Giám sát cửa ra vào",
    "subtype": 0,
    "mode": "mjpeg",
    "feature_type": "zone_presence",
    "grace_seconds": 2.0,
    "warning_seconds": 10.0,
    "enabled": true
  }
  ```
  - Ràng buộc: `channel` (`1..128`), `name` (`1..120`), `zone_name` (`0..120`), `note` (`0..240`), `subtype` (`0..2`), `mode` (`"mjpeg"` | `"snapshot"`), `feature_type` (`"zone_presence"` | `"zone_intrusion"`), `grace_seconds` (`0.0..60.0`), `warning_seconds` (`1.0..600.0`).
- **Response `201 Created`:** Object camera vừa tạo (kèm `"id": "ch25"` và `"zone": []`). Nếu `ch{channel}` đã tồn tại, hệ thống tự thêm hậu tố timestamp `% 10000`.

### 3.3. `PUT /api/v1/cameras/{cam_id}`
Cập nhật từng phần thông tin camera (`CameraUpdate`, các trường `null` được giữ nguyên).
- **Response `200 OK`:** Object camera sau khi cập nhật.
- **Lỗi:** `404 NOT_FOUND` nếu `cam_id` không tồn tại.

### 3.4. `DELETE /api/v1/cameras/{cam_id}`
Xóa camera khỏi cấu hình và dừng stream nền tương ứng.
- **Response `200 OK`:** `{"status": "deleted", "id": "ch25"}`
- **Lỗi:** `404 NOT_FOUND` nếu `cam_id` không tồn tại.

### 3.5. `PUT /api/v1/cameras/{cam_id}/zone`
Lưu đa giác vùng giám sát (tọa độ chuẩn hóa `0.0 .. 1.0`).
- **Request Body (`ZonePayload`):**
  ```json
  {
    "points": [
      { "x": 0.1, "y": 0.2 },
      { "x": 0.8, "y": 0.2 },
      { "x": 0.8, "y": 0.9 },
      { "x": 0.1, "y": 0.9 }
    ]
  }
  ```
  - Truyền `points: []` để xóa vùng; AI chỉ kích hoạt kiểm tra vùng khi `len(points) >= 3`.
- **Response `200 OK`:** Object camera đã cập nhật trường `zone`.

### 3.6. `GET /api/v1/cameras/{cam_id}/snapshot.jpg`
Lấy ảnh tĩnh JPEG từ `NvrStreamManager` (nếu có packet mới trong RAM) hoặc gọi trực tiếp NVR (`/cgi-bin/snapshot.cgi`).
- **Query Parameters:** `direct` (`bool`, default `false`) — đặt `true` để ép gọi thẳng NVR (dùng khi vẽ vùng hoặc kiểm tra trực tiếp).
- **Response `200 OK`:** Binary `image/jpeg`, kèm header `Cache-Control: no-store, no-cache, must-revalidate` và `X-Latency-Ms`.
- **Lỗi:** `404 NOT_FOUND`, `502 UPSTREAM_ERROR`, `503 UPSTREAM_ERROR`.

### 3.7. `GET /api/v1/cameras/{cam_id}/probe`
Kiểm tra trạng thái online và độ trễ NVR cho 1 camera.
- **Response `200 OK`:**
  ```json
  {
    "id": "ch16",
    "online": true,
    "status_code": 200,
    "latency_ms": 185,
    "bytes": 173648
  }
  ```
  Nếu mất kết nối NVR, vẫn trả `200 OK` với `"online": false`, `"error": "..."`, `"latency_ms": null`.

### 3.8. `GET /api/v1/cameras/{cam_id}/mjpeg`
Stream luồng video MJPEG (`multipart/x-mixed-replace`).
- **Query Parameters:**
  - `subtype` (`0..2`, optional — mặc định lấy theo cấu hình camera).
  - `view` (`"grid"` | `"focus"`, default `"grid"`).
- **Cơ chế phân phối (Response Headers `X-Stream-Source`):**
  - `ram-grid-cache`: Khi `view=grid`, `subtype=0` và đã có frame trong `NvrStreamManager` -> phát ảnh đã resize/nén từ `GridFrameCache`.
  - `ram-direct`: Khi `view=focus` hoặc `subtype != 0` và đã có frame trong `NvrStreamManager` -> passthrough trực tiếp `jpeg_bytes` gốc từ RAM.
  - `nvr-direct`: Fallback proxy trực tiếp từ NVR (cold start hoặc chuyển `subtype` chưa có trong RAM).
- **Headers chuẩn chống buffer:** `Cache-Control: no-store, no-cache, must-revalidate`, `Pragma: no-cache`, `X-Accel-Buffering: no`.

---

## 4. AI Detections & Realtime WebSocket Endpoints

### 4.1. `GET /api/v1/detections`
Lấy snapshot kết quả suy luận YOLO26s + ByteTrack + `ZoneRuleEngine` mới nhất theo từng `cam_id`.
- **Query Parameters:** `focus_cam_id` (`string`, optional, max 64) — nếu truyền vào sẽ cập nhật focus camera ngay trong lần gọi.
- **Response `200 OK`:**
  ```json
  {
    "ch16": {
      "cam_id": "ch16",
      "has_zone": true,
      "person_in_zone": true,
      "in_zone_count": 1,
      "total_persons": 2,
      "persons": [
        {
          "track_id": 4,
          "x1": 0.21, "y1": 0.30, "x2": 0.35, "y2": 0.78,
          "cx": 0.28, "cy": 0.54,
          "foot_x": 0.28, "foot_y": 0.78,
          "conf": 0.872,
          "in_zone": true
        }
      ],
      "dwell_seconds": 3.45,
      "event_triggered": false,
      "status": "present",
      "ui_color": "green",
      "status_label": "CÓ NHÂN VIÊN",
      "sub_label": "1 người trong vùng",
      "polygon_label": "KHU VỰC MÁY TĂNG TRỌNG 1 · 1 NV",
      "empty_duration": 0.0,
      "alert_count": 0,
      "total_alert_seconds": 0.0,
      "session_duration_seconds": 124.5,
      "timeline": [
        { "start": 1795061880.0, "end": 1795062004.5, "color": "green" }
      ],
      "inference_ms": 21,
      "active_provider": "CUDAExecutionProvider",
      "updated_at": 1795062004.5
    }
  }
  ```

### 4.2. `POST /api/v1/detections/focus`
Đặt camera ưu tiên suy luận (tần suất tối đa, tự hết hạn sau `AI_FOCUS_TTL_SEC=15s`) hoặc bỏ focus (`cam_id: null`).
- **Request Body:** `{ "cam_id": "ch16" }` hoặc `{ "cam_id": null }`.
- **Response `200 OK`:** `{ "focus_cam_id": "ch16" }`

### 4.3. `POST /api/v1/detections/{cam_id}/reset-stats`
Reset toàn bộ bộ đếm cảnh báo (`alert_count`, `total_alert_seconds`), rolling timeline và trạng thái `ByteTrack` của 1 camera.
- **Response `200 OK`:** `{ "status": "reset", "cam_id": "ch16" }`
- **Lỗi:** `404 NOT_FOUND` nếu `cam_id` không tồn tại.

### 4.4. `GET /api/v1/detections/{cam_id}/events`
Truy vấn lịch sử sự kiện cảnh báo (`alert_events`) đã lưu trong SQLite.
- **Query Parameters:**
  - `from` (`float`, optional): Unix timestamp bắt đầu.
  - `to` (`float`, optional): Unix timestamp kết thúc.
  - `limit` (`int`, default `200`, `1..1000`): Số bản ghi tối đa.
- **Response `200 OK`:** Mảng các bản ghi `{ id, cam_id, started_at, ended_at, duration_s, peak_state }`.

### 4.5. `WS /api/v1/ws/detections` (và alias `WS /api/v1/detections/ws`)
Kênh WebSocket chính phục vụ Live View (tách message tần suất cao và tần suất thấp, coalescing latest-wins ở server):
- **Client -> Server:**
  - Focus camera: `{"type": "focus", "cam_id": "ch16"}` (hoặc `null`).
- **Server -> Client:**
  1. `type: "detections"` (gửi 1 lần ngay khi kết nối, hoặc định kỳ nếu `WS_LEGACY_PAYLOAD=true`):
     `{"type": "detections", "ts": 1795062004.5, "data": { "<cam_id>": CameraDetection }}`
  2. `type: "bbox"` (đẩy ngay lập tức sau mỗi lần suy luận 1 camera):
     ```json
     {
       "type": "bbox",
       "cam_id": "ch16",
       "frame_id": 1420,
       "ts_capture": 1795062004.5,
       "delay_ms": 38,
       "inference_ms": 21,
       "in_zone_count": 1,
       "persons": [...]
     }
     ```
  3. `type: "hud"` (đẩy tối đa 1 Hz hoặc ngay khi đổi `status`; kèm `timeline` mỗi 2s hoặc khi đổi `status`):
     ```json
     {
       "type": "hud",
       "cam_id": "ch16",
       "has_zone": true,
       "status": "present",
       "ui_color": "green",
       "status_label": "CÓ NHÂN VIÊN",
       "sub_label": "1 người trong vùng",
       "polygon_label": "KHU VỰC MÁY TĂNG TRỌNG 1 · 1 NV",
       "alert_count": 0,
       "total_alert_seconds": 0.0,
       "session_duration_seconds": 124.5,
       "in_zone_count": 1,
       "active_provider": "CUDAExecutionProvider",
       "timeline": [...]
     }
     ```

---

## 5. Recording & Dataset Endpoints

### 5.1. `POST /api/v1/cameras/{cam_id}/record/start`
Khởi chạy job ghi hình nền từ luồng MJPEG ra file `.mp4` (`10 FPS`).
- **Request Body:** `{ "duration_minutes": 5, "subtype": 0 }` (`duration_minutes`: `5 | 10 | 20`, `subtype`: `0 | 1`).
- **Response `202 Accepted`:** Object `RecordJob` (`job_id`, `cam_id`, `channel`, `cam_name`, `subtype`, `duration_minutes`, `filename`, `started_at`, `elapsed_sec`, `remaining_sec`, `frames_written`, `status`, `error`).
- **Lỗi:** `404 NOT_FOUND`, `409 CONFLICT`, `422 VALIDATION_ERROR`.

### 5.2. `POST /api/v1/cameras/{cam_id}/record/stop`
Dừng phiên ghi hình đang chạy của camera.
- **Response `200 OK`:** Object `RecordJob`.

### 5.3. `GET /api/v1/records/active` & `GET /api/v1/records/{job_id}`
Liệt kê các phiên ghi hình đang chạy hoặc tra cứu 1 job cụ thể.

### 5.4. Nhóm Storages Videos & Frames
- `GET /api/v1/storages/videos`: Liệt kê `.mp4` trong `poc/storages/videos/` (kèm `width`, `height`, `fps`, `frame_count`, `duration_sec`, `extracted_folders`).
- `GET /api/v1/storages/videos/{filename}/download`: Tải file `.mp4` (`FileResponse`).
- `DELETE /api/v1/storages/videos/{filename}`: Xóa file `.mp4`.
- `POST /api/v1/storages/videos/{filename}/extract`: Tách ảnh `.jpg` với `{"skip_frames": 5}` hoặc `10` (chạy trên worker thread qua `asyncio.to_thread`).
- `GET /api/v1/storages/frames`: Liệt kê các bộ frame trong `poc/storages/frames/`.
- `GET /api/v1/storages/frames/{folder}/preview/{image_name}`: Xem trước 1 ảnh `.jpg`.
- `GET /api/v1/storages/frames/{folder}/download.zip`: Nén và tải `.zip`.
- `DELETE /api/v1/storages/frames/{folder}`: Xóa bộ frame.

---

## 6. Hợp đồng Tích hợp Hệ thống ATIN Smart VMS (Chuẩn Production)

Phần này giữ nguyên theo tài liệu `docs/onboard/` để sẵn sàng ghép vào VMS ATIN khi chuyển từ PoC sang Production (`ATIN_VMS_ENABLED=true`):

### 6.1. Storage HTTP API
- **Upload ảnh:** `POST https://<DOMAIN>/storage/upload/file` (`multipart/form-data` với `file`, `camera_id`, `category`).
  - Dùng trường `object_key` trả về gán vào `snapshot_url`; không dùng `url` nội bộ hay gửi `snapshot_base64` qua MQTT.
- **Xem ảnh:** `GET https://<DOMAIN>/api/v1/snapshot/image?object_key=<object_key>`.

### 6.2. MQTT Topics & Payload (`wss://<DOMAIN>/mqtt:443`)
| Mục đích | Topic | QoS / Retain | Lưu ý bắt buộc |
| :--- | :--- | :---: | :--- |
| Yêu cầu DS Camera | `smart_vms/cameras/getdevice` | `1` / `false` | Gửi JSON `{"organization_id": ..., "zone_id": ...}` |
| Nhận DS Camera | `smart_vms/cameras/company/{org}`<br>`smart_vms/cameras/zone/{zone}` | `1` / `true` | Chỉ chạy AI cho camera bật module tương ứng trong `ai_modules` |
| Hot-reload Zone | `smart_vms/cameras/+/ai_zones/{MODULE}` | `1` / `true` | Lọc theo `ai_modules`; xử lý an toàn payload rỗng `""` |
| BBox Realtime | `smart_vms/ai/bbox/{camera_code}` | `0` / `false` | Gửi mỗi `0.1s–0.2s`, tọa độ `0..1` |
| Sự kiện AI | `smart_vms/ai_events/{MODULE}` | `1` / `false` | `event_time` ISO-8601 `+07:00` |

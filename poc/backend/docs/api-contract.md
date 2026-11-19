# API Contract — ATIN Trần Hân AI Backend (`/api/v1`)

> Tài liệu đặc tả chi tiết toàn bộ REST API của `poc/backend` (chuẩn hóa theo `api-design-patterns`) và các hợp đồng tích hợp hệ thống **ATIN Smart VMS** (giữ nguyên chuẩn Production).

---

## 1. Quy ước chung & Tiêu chuẩn Thiết kế

### 1.1. Base URL & Versioning
- **Base Prefix:** `/api/v1` (mọi endpoint nghiệp vụ đặt sau prefix này).
- **OpenAPI / Swagger UI:** `GET /docs` (khi bật `DEBUG=true` hoặc mặc định FastAPI).

### 1.2. Headers xuyên suốt (Middleware)
Mọi HTTP response đều đi qua chuỗi middleware tại `app/middlewares/__init__.py` và trả về:
- `X-Request-ID`: UUIDv4 tự sinh (hoặc giữ nguyên giá trị client gửi lên qua header `X-Request-ID`).
- `X-Process-Time`: Thời gian xử lý request ở server (VD: `7.35ms`).

### 1.3. Cấu trúc Lỗi Thống nhất (Consistent Error Envelope)
Mọi lỗi nghiệp vụ (`404`, `409`, `422`, `429`, `500`, `502`, `503`) đều trả về JSON chuẩn hóa (vẫn giữ trường `detail` để tương thích ngược với client FastAPI/PoC):

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
    "timestamp": "2026-11-19T04:20:00+00:00",
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

> **Lưu ý Pydantic 422 mặc định:** Khi sai kiểu dữ liệu JSON body/query (Pydantic validation), FastAPI trả về HTTP `422` với `{"detail": [...]}`.

---

## 2. System Endpoints

### 2.1. `GET /api/v1/health`
Kiểm tra tình trạng sống của dịch vụ.
- **Response `200 OK`:**
  ```json
  { "status": "ok" }
  ```

### 2.2. `GET /api/v1/config`
Lấy thông tin cấu hình hiển thị và chế độ vận hành.
- **Response `200 OK`:**
  ```json
  {
    "nvr_host": "nmts2025.smartddns.tv",
    "nvr_port": 80,
    "project": "Nhà máy Thủy sản Trần Hân",
    "environment": "local",
    "atin_vms_enabled": false
  }
  ```

---

## 3. Cameras & Zone Endpoints

### 3.1. `GET /api/v1/cameras`
Lấy danh sách camera và tọa độ zone đã cấu hình.
- **Query Parameters (tùy chọn — Pattern Filtering):**
  - `enabled` (`bool`, optional): Lọc theo trạng thái bật/tắt (`true` / `false`).
  - `search` (`string`, optional, max 120): Tìm kiếm không phân biệt hoa thường theo `id`, `name`, `note`.
- **Response `200 OK`:**
  ```json
  [
    {
      "id": "ch16",
      "channel": 16,
      "name": "Tăng trọng 1",
      "note": "Khu vực máy tăng trọng 1",
      "subtype": 0,
      "mode": "mjpeg",
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
- **Request Body:**
  ```json
  {
    "channel": 25,
    "name": "Cổng kho lạnh",
    "note": "Giám sát cửa ra vào",
    "subtype": 1,
    "mode": "mjpeg",
    "enabled": true
  }
  ```
  - Ràng buộc: `channel` (`1..128`), `name` (`1..120` ký tự), `note` (`0..240`), `subtype` (`0..2`), `mode` (`"mjpeg"` | `"snapshot"`).
- **Response `201 Created`:** Trả về object camera vừa tạo (kèm `"id": "ch25"` và `"zone": []`). Nếu `ch{channel}` đã tồn tại, hệ thống tự thêm hậu tố timestamp `% 10000`.

### 3.3. `PUT /api/v1/cameras/{cam_id}`
Cập nhật từng phần thông tin camera (các trường `null` được giữ nguyên).
- **Request Body:** Bất kỳ tập con nào của `{ channel, name, note, subtype, mode, enabled }`.
- **Response `200 OK`:** Object camera sau khi cập nhật.
- **Lỗi:** `404 NOT_FOUND` nếu `cam_id` không tồn tại.

### 3.4. `DELETE /api/v1/cameras/{cam_id}`
Xóa camera khỏi cấu hình.
- **Response `200 OK`:** `{"status": "deleted", "id": "ch25"}`
- **Lỗi:** `404 NOT_FOUND` nếu `cam_id` không tồn tại.

### 3.5. `PUT /api/v1/cameras/{cam_id}/zone`
Lưu đa giác vùng giám sát (tọa độ chuẩn hóa `0.0 .. 1.0`).
- **Request Body:**
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
  - Lưu ý: Truyền `points: []` để xóa vùng; AI chỉ kích hoạt kiểm tra vùng khi `len(points) >= 3`.
- **Response `200 OK`:** Object camera đã cập nhật trường `zone`.
- **Lỗi:** `404 NOT_FOUND`, `422` (nếu `x` hoặc `y` ngoài `[0.0, 1.0]`).

### 3.6. `GET /api/v1/cameras/{cam_id}/snapshot.jpg`
Proxy ảnh tĩnh JPEG trực tiếp từ NVR (`/cgi-bin/snapshot.cgi`).
- **Response `200 OK`:** Binary `image/jpeg`, kèm header `Cache-Control: no-store, no-cache, must-revalidate` và `X-Latency-Ms`.
- **Lỗi:** `404 NOT_FOUND`, `502 UPSTREAM_ERROR`, `503 UPSTREAM_ERROR` (chưa cấu hình NVR).

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
- **Lỗi:** `404 NOT_FOUND`, `503 UPSTREAM_ERROR`.

### 3.8. `GET /api/v1/cameras/{cam_id}/mjpeg`
Proxy luồng video MJPEG (`multipart/x-mixed-replace`) từ NVR.
- **Query Parameters:** `subtype` (`0..2`, optional — mặc định lấy theo cấu hình camera).
- **Response `200 OK`:** `StreamingResponse` luồng MJPEG với `Cache-Control: no-store`.
- **Lỗi:** `404 NOT_FOUND`, `502 UPSTREAM_ERROR`, `503 UPSTREAM_ERROR`.
- **Lưu ý vận hành:** Kết nối streaming mở liên tục; khi dừng server bằng `Ctrl+C`, dùng `--timeout-graceful-shutdown 2` để đóng luồng sạch sẽ.

---

## 4. AI Detections Endpoints

### 4.1. `GET /api/v1/detections`
Lấy kết quả suy luận YOLO26s + đánh giá `ZoneRuleEngine` mới nhất theo từng `cam_id`.
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
      "dwell_seconds": 3.45,
      "event_triggered": false,
      "inference_ms": 48,
      "updated_at": 1795062000.12,
      "persons": [
        {
          "x1": 0.21, "y1": 0.30, "x2": 0.35, "y2": 0.78,
          "cx": 0.28, "cy": 0.54,
          "conf": 0.872,
          "in_zone": true
        }
      ]
    }
  }
  ```

### 4.2. `POST /api/v1/detections/focus`
Đặt camera ưu tiên suy luận (tần suất `0.15s`, tự hết hạn sau `15s`) hoặc bỏ focus (`cam_id: null`).
- **Request Body:** `{ "cam_id": "ch16" }` hoặc `{ "cam_id": null }`.
- **Response `200 OK`:** `{ "focus_cam_id": "ch16" }`
- **Lỗi:** `404 NOT_FOUND` nếu `cam_id` khác `null` và không tồn tại.

---

## 5. Recording & Dataset Endpoints (Async Request-Response)

### 5.1. `POST /api/v1/cameras/{cam_id}/record/start`
Khởi chạy job ghi hình nền từ luồng MJPEG ra file `.mp4` (`10 FPS`).
- **Request Body:**
  ```json
  {
    "duration_minutes": 5,
    "subtype": 0
  }
  ```
  - Ràng buộc: `duration_minutes` chỉ nhận `5`, `10`, hoặc `20`; `subtype` (`0` hoặc `1`).
- **Response `202 Accepted`:**
  ```json
  {
    "job_id": "ch16_20261119_112000",
    "cam_id": "ch16",
    "channel": 16,
    "cam_name": "Tăng trọng 1",
    "subtype": 0,
    "duration_minutes": 5,
    "filename": "ch16_20261119_112000_5m.mp4",
    "started_at": 1795062000.0,
    "elapsed_sec": 0.0,
    "remaining_sec": 300.0,
    "frames_written": 0,
    "status": "recording",
    "error": null
  }
  ```
- **Lỗi:** `404 NOT_FOUND`, `409 CONFLICT` (camera đang ghi hình), `422 VALIDATION_ERROR`.

### 5.2. `POST /api/v1/cameras/{cam_id}/record/stop`
Gửi tín hiệu dừng phiên ghi hình đang chạy của camera.
- **Response `200 OK`:** Trả về object `RecordJob` hiện tại.
- **Lỗi:** `404 NOT_FOUND` (camera không tồn tại hoặc không có phiên ghi hình đang chạy).

### 5.3. `GET /api/v1/records/active`
Danh sách các phiên ghi hình có `status == "recording"`.
- **Response `200 OK`:** Mảng `RecordJob[]`.

### 5.4. `GET /api/v1/records/{job_id}`
Tra cứu trạng thái của một job ghi hình cụ thể (Pattern 6 — Async Polling).
- **Response `200 OK`:** Object `RecordJob` (`status`: `recording | completed | stopped | error`).
- **Lỗi:** `404 NOT_FOUND` nếu `job_id` không tồn tại (hoặc server vừa khởi động lại).

### 5.5. `GET /api/v1/storages/videos`
Liệt kê toàn bộ file `.mp4` đã ghi trong `poc/storages/videos/` (sắp xếp mới nhất trước).
- **Response `200 OK`:**
  ```json
  [
    {
      "filename": "ch16_20261119_112000_5m.mp4",
      "size_bytes": 12456789,
      "created_at": 1795062300.0,
      "extracted_folders": ["ch16_20261119_112000_5m_skip5"],
      "width": 1920,
      "height": 1080,
      "fps": 10.0,
      "frame_count": 3000,
      "duration_sec": 300.0
    }
  ]
  ```

### 5.6. `GET /api/v1/storages/videos/{filename}/download`
Tải file video `.mp4`.
- **Response `200 OK`:** `video/mp4` (`FileResponse`).
- **Lỗi:** `422 VALIDATION_ERROR` (tên file không hợp lệ), `404 NOT_FOUND`.

### 5.7. `DELETE /api/v1/storages/videos/{filename}`
Xóa file video `.mp4`.
- **Response `200 OK`:** `{"status": "deleted", "filename": "..."}`
- **Lỗi:** `422 VALIDATION_ERROR`, `404 NOT_FOUND`.

### 5.8. `POST /api/v1/storages/videos/{filename}/extract`
Tách ảnh `.jpg` từ video `.mp4` (chạy trên worker thread qua `asyncio.to_thread`).
- **Request Body:** `{ "skip_frames": 5 }` (chỉ hỗ trợ `5` hoặc `10`).
- **Response `200 OK`:**
  ```json
  {
    "folder": "ch16_20261119_112000_5m_skip5",
    "video_name": "ch16_20261119_112000_5m.mp4",
    "skip_frames": 5,
    "total_video_frames": 3000,
    "saved_frames": 500
  }
  ```
- **Lỗi:** `422 VALIDATION_ERROR`, `404 NOT_FOUND`, `500` (không mở được video).

### 5.9. `GET /api/v1/storages/frames`
Liệt kê các bộ ảnh frame trong `poc/storages/frames/`.
- **Response `200 OK`:** Mảng `{ folder, skip_frames, frame_count, size_bytes, created_at, previews }`.

### 5.10. `GET /api/v1/storages/frames/{folder}/preview/{image_name}`
Xem trước 1 ảnh `.jpg` trong bộ frame.
- **Response `200 OK`:** `image/jpeg`.
- **Lỗi:** `422 VALIDATION_ERROR`, `404 NOT_FOUND`.

### 5.11. `GET /api/v1/storages/frames/{folder}/download.zip`
Nén và tải toàn bộ ảnh `.jpg` trong thư mục `{folder}` dưới dạng `.zip`.
- **Response `200 OK`:** `application/zip` với header `Content-Disposition: attachment; filename="{folder}.zip"`.
- **Lỗi:** `422 VALIDATION_ERROR`, `404 NOT_FOUND`.

### 5.12. `DELETE /api/v1/storages/frames/{folder}`
Xóa toàn bộ thư mục bộ frame.
- **Response `200 OK`:** `{"status": "deleted", "folder": "..."}`
- **Lỗi:** `422 VALIDATION_ERROR`, `404 NOT_FOUND`.

---

## 6. Hợp đồng Tích hợp Hệ thống ATIN Smart VMS (Giữ nguyên chuẩn Production)

Phần này giữ nguyên 100% theo tài liệu `docs/onboard/` để khi tích hợp vào VMS ATIN không cần sửa Backend VMS:

### 6.1. Storage HTTP API (Upload & Xem ảnh sự kiện)
- **Upload ảnh:** `POST https://<DOMAIN>/storage/upload/file` (`multipart/form-data`)
  - Fields: `file` (JPEG < 10MB, nén trực tiếp trong RAM), `camera_id` (UUID), `category` (`face | plate | zone | fire | footfall | anomaly`).
  - Response: `{"object_key": "zone/2026-11-19/...", "url": "http://127.0.0.1:..."}`
  - **Bắt buộc:** Lấy `object_key` gán vào `snapshot_url`; **tuyệt đối không** dùng trường `url` nội bộ hay gửi `snapshot_base64` qua MQTT.
- **Xem ảnh:** `GET https://<DOMAIN>/api/v1/snapshot/image?object_key=<object_key>`

### 6.2. MQTT Topics & Payload (`wss://<DOMAIN>/mqtt:443`)
| Mục đích | Topic | QoS / Retain | Lưu ý bắt buộc |
| :--- | :--- | :---: | :--- |
| Yêu cầu DS Camera | `smart_vms/cameras/getdevice` | `1` / `false` | Gửi JSON `{"organization_id": ..., "zone_id": ...}`, **tránh** `getdevice/zone/{id}` |
| Nhận DS Camera | `smart_vms/cameras/company/{org}`<br>`smart_vms/cameras/zone/{zone}` | `1` / `true` | Chỉ chạy AI cho camera bật module tương ứng trong `ai_modules` |
| Hot-reload Zone | `smart_vms/cameras/+/ai_zones/{MODULE}` | `1` / `true` | Không dùng `#` bừa bãi; lọc theo `ai_modules`; xử lý an toàn payload rỗng `""` |
| BBox Realtime | `smart_vms/ai/bbox/{camera_code}` | `0` / `false` | Gửi mỗi `0.1s–0.2s` (Web VMS xóa khung sau `0.35s`), tọa độ `0..1` |
| Sự kiện AI | `smart_vms/ai_events/{MODULE}` | `1` / `false` | `event_time` ISO-8601 `+07:00`; nhóm `ANOMALY` phải đủ `ai_modules`, `submodule_code`, `payload.type` hợp lệ |

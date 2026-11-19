# Đặc Tả Kỹ Thuật Backend & AI Core (`poc/backend`)

## 1. Kiến trúc phân tầng
Tuân thủ chuẩn `fastapi-backend-scaffold`, tách biệt rõ trách nhiệm giữa HTTP, nghiệp vụ, lưu trữ dữ liệu và AI Core:

```text
HTTP Request
  └─► app/middlewares/ (ErrorHandling → CORS → RequestLogging → RateLimit → RequestID)
        └─► app/api/v1/endpoints/ (Controller: validate schema, gọi Service)
              └─► app/services/ (Nghiệp vụ thuần, không phụ thuộc FastAPI)
                    ├─► app/repositories/ (Truy cập dữ liệu: JsonCameraRepository / SQLAlchemy)
                    ├─► app/ai/ (YoloPersonDetector, ZoneRuleEngine, PersonZoneDetector)
                    └─► app/integrations/atin_vms/ (MQTT Orchestrator, RTSP Reader, Storage API)
```

## 2. Danh sách API (`/api/v1`)

| Nhóm | Method | Endpoint | Mô tả |
| :--- | :---: | :--- | :--- |
| **System** | `GET` | `/api/v1/health` | Healthcheck (`{"status": "ok"}`) |
| | `GET` | `/api/v1/config` | Thông tin cấu hình môi trường & dự án |
| **Cameras** | `GET` | `/api/v1/cameras` | Danh sách camera & zone |
| | `POST` | `/api/v1/cameras` | Thêm camera mới |
| | `PUT` | `/api/v1/cameras/{cam_id}` | Cập nhật thông tin camera |
| | `DELETE` | `/api/v1/cameras/{cam_id}` | Xóa camera |
| | `PUT` | `/api/v1/cameras/{cam_id}/zone` | Lưu tọa độ đa giác (`0..1`) |
| | `GET` | `/api/v1/cameras/{cam_id}/snapshot.jpg` | Proxy ảnh snapshot từ NVR |
| | `GET` | `/api/v1/cameras/{cam_id}/probe` | Kiểm tra online & độ trễ NVR |
| | `GET` | `/api/v1/cameras/{cam_id}/mjpeg` | Proxy luồng MJPEG (`StreamingResponse`) |
| **Detections** | `GET` | `/api/v1/detections` | Kết quả nhận diện mới nhất theo từng camera |
| | `POST` | `/api/v1/detections/focus` | Đặt camera ưu tiên suy luận (hoặc `null`) |
| **Recording & Dataset** | `POST` | `/api/v1/cameras/{cam_id}/record/start` | Bắt đầu ghi hình `.mp4` (`5`/`10`/`20` phút) |
| | `POST` | `/api/v1/cameras/{cam_id}/record/stop` | Dừng ghi hình |
| | `GET` | `/api/v1/records/active` | Danh sách phiên ghi hình đang chạy |
| | `GET` | `/api/v1/storages/videos` | Danh sách video đã ghi |
| | `GET` | `/api/v1/storages/videos/{filename}/download` | Tải video `.mp4` |
| | `DELETE` | `/api/v1/storages/videos/{filename}` | Xóa video |
| | `POST` | `/api/v1/storages/videos/{filename}/extract` | Tách frame (`skip_frames`: `5` hoặc `10`) |
| | `GET` | `/api/v1/storages/frames` | Danh sách bộ frame |
| | `GET` | `/api/v1/storages/frames/{folder}/preview/{image_name}` | Xem trước 1 ảnh frame |
| | `GET` | `/api/v1/storages/frames/{folder}/download.zip` | Tải bộ frame dạng `.zip` |
| | `DELETE` | `/api/v1/storages/frames/{folder}` | Xóa bộ frame |

## 3. Tích hợp ATIN Smart VMS (Production Readiness)
Các adapter tại `app/integrations/atin_vms/` được thiết kế theo hợp đồng kỹ thuật `C01`–`C09` trong `docs/onboard/`:
- **`mqtt_orchestrator.py`**: Kết nối WSS (`443`, TLS), tự re-subscribe trong `on_connect`, gửi `smart_vms/cameras/getdevice` với JSON payload, lọc `ai_zones/{MODULE}` theo `ai_modules`, publish BBox QoS 0 và Event QoS 1 chuẩn ISO-8601 `+07:00`.
- **`rtsp_reader.py`**: Ép `rtsp_transport;tcp`, `CAP_PROP_BUFFERSIZE=1`, tự reconnect khi mất kết nối.
- **`storage_client.py`**: Nén JPEG trực tiếp trên RAM (`cv2.imencode`) và upload `POST /storage/upload/file` để lấy `object_key`.

# QUY TRÌNH TRIỂN KHAI TASK MỚI & MẪU CODE CHUẨN (PRODUCTION BOILERPLATE)
## (ATIN Smart VMS — Step-by-Step Playbook & Reusable Edge Worker Template)

> [!IMPORTANT]
> Khi chuyển sang môi trường Production và được giao bất kỳ nhiệm vụ tích hợp Module AI mới nào (ví dụ: Phát hiện đám đông `CROWD_DETECTION`, Đánh nhau `FIGHT_DETECTION`, Cháy khói `FIRE`, Vùng cấm `ZONE`, Biển số `PLATE`, Khuôn mặt `FACE`...), bạn chỉ cần làm theo **Quy trình 4 bước chuẩn** và tái sử dụng **Bộ khung Code (Boilerplate)** đã được kiểm chứng thực tế dưới đây.

---

## Phần 1: Quy trình 4 Bước Khi Nhận Một Task AI Mới Tại Công Ty

```mermaid
flowchart LR
    S1["Bước 1: PROBE (5 phút)\nChạy script dò MQTT\nlấy UUID Camera, RTSP\n& tọa độ ai_zones"] --> S2["Bước 2: SMOKE TEST (5 phút)\nBắn thử 1 BBox + Upload 1 ảnh\n+ Bắn 1 Event chuẩn lên VMS\nxác nhận thông luồng 100%"]
    S2 --> S3["Bước 3: CORE WORKER\nLắp Model AI vào khung Worker\n(Detector + Polygon/Line\n+ Dwell-time + Cooldown)"]
    S3 --> S4["Bước 4: ĐO KIỂM & DOCKER\nĐo FPS, Latency, Precision/Recall\n& Đóng gói Docker bàn giao"]
```

### Bước 1: Chạy Script Probe khám phá Camera & Zone thực tế trên Broker (5 phút)
- Không bao giờ đoán mò `camera_id` (UUID), `zone_id` hay `organization_id`.
- Chạy script Probe (mẫu ở **Mục 2.2** bên dưới) kết nối vào Broker, lắng nghe `smart_vms/cameras/zone/+`, `smart_vms/cameras/company/+` và `smart_vms/cameras/{camera_code}/ai_zones/#` để:
  1. Lấy chính xác `camera_id` (UUID), `organization_id`, `zone_id` của camera được giao.
  2. Kiểm tra mảng `ai_modules` xem camera đó đã được bật đúng module trên Web VMS chưa.
  3. Lấy `rtsp_url` (MediaMTX port `18554`) và chụp thử 1 frame ảnh vẽ đè các đa giác `ai_zones` lên để xem vùng vẽ trên Web VMS có bị trùng lặp với module khác không.

### Bước 2: Chạy Smoke Test xác nhận thông luồng BBox + Storage + Event (5 phút)
- Trước khi viết logic AI phức tạp, dùng bức ảnh vừa chụp ở Bước 1:
  1. Gửi 50 gói BBox giả lập (5 FPS trong 10s) lên `smart_vms/ai/bbox/{camera_code}` $\longrightarrow$ Mở Web VMS xem khung đã hiện chưa.
  2. Upload bức ảnh lên `POST https://<DOMAIN>/storage/upload/file` lấy `object_key`.
  3. Gửi 1 bản tin Event chuẩn với `"snapshot_url": object_key` lên `smart_vms/ai_events/{MODULE}` $\longrightarrow$ Mở tab **Lịch sử sự kiện** trên Web VMS xác nhận sự kiện và ảnh đã lưu thành công vào PostgreSQL.

### Bước 3: Lắp Model AI vào Bộ Khung Worker Chuẩn (`src/`)
- Giữ nguyên `config.py`, `storage_client.py`, `main.py` (Orchestrator) và `worker.py`.
- Chỉ cần tùy biến file `detector.py` (thay model YOLO / Classifier / OCR của bài toán mới) và cấu hình `payload` trong `_publish_event()` theo đúng bảng schema ở File `02_CAM_NANG_TICH_HOP_VA_LUU_Y_THUC_CHIEN.md`.

### Bước 4: Đánh giá Số liệu & Đóng gói Bàn giao
- Ghi nhận các chỉ số từ log `[STATS]`:
  - **System Metrics:** Inference Latency (`ms/frame`), FPS, Storage Upload Latency (`ms`), Cooldown Suppression Rate (`%`).
  - **Accuracy Metrics:** $TP, FP, FN \implies \text{Precision}, \text{Recall}, F_1\text{-Score}$.
- Đóng gói bằng `Dockerfile` và `.env.example` (không kèm `.env` chứa mật khẩu thật).

---

## Phần 2: Bộ Khung Code Chuẩn Tái Sử Dụng (`Reusable Production Template`)

### 2.1. Cấu trúc Thư mục Chuẩn cho Mọi Dự án AI Edge

```text
<ten_module>_ai/
├── .env                        # Chứa thông tin kết nối thật (Đưa vào .gitignore, KHÔNG commit)
├── .env.example                # File mẫu cấu hình
├── Dockerfile                  # Đóng gói container chạy 24/7 trên Server AI
├── requirements.txt            # paho-mqtt, requests, opencv-python-headless, ultralytics, numpy, python-dotenv
├── scripts/
│   ├── step1_probe_mqtt_rtsp.py    # Script Bước 1: Quét UUID camera, lấy ai_zones & test RTSP
│   └── step2_smoke_test_event.py   # Script Bước 2: Test bắn BBox + Upload ảnh + Bắn Event
└── src/
    ├── __init__.py
    ├── config.py               # Đọc biến môi trường tập trung từ .env
    ├── storage_client.py       # Nén JPEG trên RAM & upload lên /storage/upload/file lấy object_key
    ├── detector.py             # Chạy suy luận AI thật (C09) + kiểm tra Point-in-Polygon (C03)
    ├── worker.py               # Đọc RTSP không trễ, tự phục hồi, gửi BBox 5 FPS (C07), Dwell-time & Cooldown (C08)
    └── main.py                 # MQTT Orchestrator (C01), tự bật/tắt Worker (C02) & Hot-reload Zone (C03)
```

---

### 2.2. Mẫu File `.env.example` (Dễ dàng chuyển đổi Staging $\leftrightarrow$ Production)

```ini
# =====================================================================
# 1. CẤU HÌNH KẾT NỐI MQTT BROKER (C01)
# - Khi Onboard/Staging: MQTT_HOST=aioc-stg.atin.vn
# - Khi sang Production: Đổi sang domain Production (VD: aioc.atin.vn)
# =====================================================================
MQTT_HOST=aioc-stg.atin.vn
MQTT_PORT=443
MQTT_WS_PATH=/mqtt
MQTT_USER=atin
MQTT_PASS=Atin@2026#
# LƯU Ý: Đặt client_id duy nhất cho mỗi service, KHÔNG bắt đầu bằng vms_staging_backend
MQTT_CLIENT_ID=ai_edge_worker_01
MQTT_KEEPALIVE=30

# =====================================================================
# 2. PHẠM VI TỔ CHỨC, KHU VỰC & CAMERA MỤC TIÊU (C02, C03)
# =====================================================================
ORGANIZATION_ID=103
ZONE_ID=51
TARGET_CAMERA_CODE=cam_sidewalk
TARGET_CAMERA_ID=2e994218-ebc9-4e7a-9396-4c3054b0d5ac
# Mã module chuẩn theo bảng mục 2.2 & 5.7 (VD: SIDEWALK_ENCROACHMENT, CROWD_DETECTION, FIGHT_DETECTION, ZONE, PLATE...)
AI_MODULE_CODE=SIDEWALK_ENCROACHMENT
ACTUAL_RTSP_URL=rtsp://admin:prometheus123@192.168.1.250:18554/c112_cam_sidewalk
FALLBACK_RTSP_URL=rtsp://192.168.1.198:28537/dungtest

# =====================================================================
# 3. CẤU HÌNH STORAGE API UPLOAD ẢNH SNAPSHOT (C05)
# - Khi sang Production: Đổi domain tương ứng với MQTT_HOST
# - category hợp lệ: face | plate | zone | fire | footfall | anomaly
# =====================================================================
STORAGE_UPLOAD_URL=https://aioc-stg.atin.vn/storage/upload/file
STORAGE_CATEGORY=anomaly

# =====================================================================
# 4. CẤU HÌNH MODEL AI & LOGIC SỰ KIỆN (C07, C08, C09)
# =====================================================================
YOLO_MODEL_PATH=yolo26n.pt
CONF_THRESHOLD=0.35
# Danh sách class ID của COCO (0: person, 1: bicycle, 2: car, 3: motorcycle, 5: bus, 7: truck...)
TARGET_CLASSES=0,1,2,3,5,7,25,56,60
BBOX_PUBLISH_INTERVAL=0.2
CONFIRM_SECONDS=2.0
EVENT_COOLDOWN_SECONDS=60
MIN_ENCROACHMENT_COUNT=1
```

---

### 2.3. Mẫu Script Bước 1: `scripts/step1_probe_mqtt_rtsp.py` (Dò tìm Camera & Vùng vẽ trên mọi Server)

```python
import os
import json
import ssl
import time
import cv2
import numpy as np
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

MQTT_HOST = os.getenv("MQTT_HOST", "aioc-stg.atin.vn")
MQTT_PORT = int(os.getenv("MQTT_PORT", "443"))
MQTT_WS_PATH = os.getenv("MQTT_WS_PATH", "/mqtt")
MQTT_USER = os.getenv("MQTT_USER", "atin")
MQTT_PASS = os.getenv("MQTT_PASS", "")
TARGET_CAMERA = os.getenv("TARGET_CAMERA_CODE", "cam_sidewalk")
ORG_ID = int(os.getenv("ORGANIZATION_ID", "103"))
ZONE_ID = int(os.getenv("ZONE_ID", "51"))

probe_data = {"camera_matches": [], "ai_zones_by_topic": {}}

def on_connect(client, userdata, flags, rc, props=None):
    print(f"[MQTT] Connected (rc={rc}). Scanning retained camera & zone topics...")
    client.subscribe("smart_vms/cameras/zone/+", qos=1)
    client.subscribe("smart_vms/cameras/company/+", qos=1)
    client.subscribe(f"smart_vms/cameras/{TARGET_CAMERA}/ai_zones", qos=1)
    client.subscribe(f"smart_vms/cameras/{TARGET_CAMERA}/ai_zones/#", qos=1)
    # Gửi request chuẩn (Tránh bug getdevice/zone/{id})
    client.publish("smart_vms/cameras/getdevice", json.dumps({"zone_id": ZONE_ID, "organization_id": ORG_ID}), qos=1)
    client.publish("smart_vms/cameras/getdevice", json.dumps({"organization_id": ORG_ID}), qos=1)

def on_message(client, userdata, msg):
    raw = msg.payload.decode("utf-8", errors="ignore").strip()
    if not raw:
        return
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return

    topic = msg.topic
    if topic.startswith("smart_vms/cameras/zone/") or topic.startswith("smart_vms/cameras/company/"):
        for cam in data.get("cameras", []):
            if cam.get("code", "").lower() == TARGET_CAMERA.lower():
                print(f"\n[FOUND CAMERA] trên topic '{topic}':\n{json.dumps(cam, indent=2, ensure_ascii=False)}")
                probe_data["camera_matches"].append({"topic": topic, "camera": cam})
    elif "/ai_zones" in topic:
        zones = data.get("ai_zones", [])
        probe_data["ai_zones_by_topic"][topic] = zones
        print(f"\n[FOUND ZONES] trên topic '{topic}' ({len(zones)} vùng):\n{json.dumps(zones, indent=2, ensure_ascii=False)}")

if __name__ == "__main__":
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"probe_{int(time.time())}", transport="websockets")
    c.ws_set_options(path=MQTT_WS_PATH)
    c.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    c.username_pw_set(MQTT_USER, MQTT_PASS)
    c.on_connect = on_connect
    c.on_message = on_message
    c.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    c.loop_start()
    time.sleep(6)
    c.loop_stop()
    c.disconnect()
```

---

### 2.4. Mẫu Module Upload Ảnh Chuẩn: `src/storage_client.py` (`C05`)

```python
import logging
from typing import Optional
import cv2
import numpy as np
import requests
from .config import settings

logger = logging.getLogger("storage_client")

def upload_snapshot(frame_bgr: np.ndarray, camera_id: str) -> Optional[str]:
    """
    Nén frame BGR sang JPEG trong RAM và upload lên Storage API.
    Trả về chuỗi `object_key` để gắn vào `snapshot_url` của sự kiện MQTT.
    """
    ok, buf = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        logger.error("Không thể nén frame sang JPEG.")
        return None

    files = {"file": ("snapshot.jpg", buf.tobytes(), "image/jpeg")}
    data = {"camera_id": camera_id, "category": settings.STORAGE_CATEGORY}

    for attempt in range(1, 3):
        try:
            resp = requests.post(settings.STORAGE_UPLOAD_URL, files=files, data=data, timeout=10)
            resp.raise_for_status()
            body = resp.json()
            object_key = body.get("object_key")
            if object_key:
                return object_key
            logger.error("Storage API phản hồi thiếu object_key: %s", body)
        except Exception as exc:
            logger.warning("Lỗi upload ảnh (lần %d/2): %s", attempt, exc)
    return None
```

---

### 2.5. Mẫu Module Suy luận AI & Kiểm tra Đa giác: `src/detector.py` (`C03`, `C09`)

```python
import logging
import cv2
import numpy as np
from ultralytics import YOLO
from .config import settings

logger = logging.getLogger("detector")

class SidewalkDetector:
    def __init__(self):
        model_path = settings.YOLO_MODEL_PATH
        try:
            logger.info("Đang tải model AI: %s ...", model_path)
            self.model = YOLO(model_path)
        except Exception as exc:
            logger.warning("Không tải được %s (%s), chuyển sang yolov8n.pt", model_path, exc)
            self.model = YOLO("yolov8n.pt")
        self.names = self.model.names

    @staticmethod
    def is_point_in_polygon(px: float, py: float, points: list[dict]) -> bool:
        if len(points) < 3:
            return False
        poly = np.array([[float(p["x"]), float(p["y"])] for p in points], dtype=np.float32)
        return cv2.pointPolygonTest(poly, (float(px), float(py)), False) >= 0

    def detect_and_filter(self, frame_bgr: np.ndarray, active_zones: list[dict]) -> tuple[list[dict], list[dict]]:
        """
        C09: Chỉ lấy detection thật từ model.predict() trên frame hiện tại.
        Trả về (all_detections, zone_violations).
        """
        h, w = frame_bgr.shape[:2]
        results = self.model.predict(
            frame_bgr,
            conf=settings.CONF_THRESHOLD,
            classes=settings.TARGET_CLASSES,
            verbose=False
        )

        all_detections = []
        if not results or results[0].boxes is None:
            return all_detections, []

        boxes = results[0].boxes
        xyxy_arr = boxes.xyxy.cpu().numpy()
        conf_arr = boxes.conf.cpu().numpy()
        cls_arr = boxes.cls.cpu().numpy().astype(int)

        for idx, (xyxy, conf, cls_id) in enumerate(zip(xyxy_arr, conf_arr, cls_arr)):
            x1 = float(np.clip(xyxy[0] / w, 0.0, 1.0))
            y1 = float(np.clip(xyxy[1] / h, 0.0, 1.0))
            x2 = float(np.clip(xyxy[2] / w, 0.0, 1.0))
            y2 = float(np.clip(xyxy[3] / h, 0.0, 1.0))

            all_detections.append({
                "id": f"det_{idx + 1}",
                "class": self.names.get(cls_id, str(cls_id)),
                "confidence": round(float(conf), 3),
                "bbox": [round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4)],
                "track_id": idx + 1
            })

        zone_violations = []
        for zone in active_zones:
            if not zone.get("is_active", True):
                continue
            # Lọc đúng module phụ trách (Tránh lẫn zone của module khác trên cùng camera)
            z_mod = zone.get("ai_modules", settings.AI_MODULE_CODE).upper()
            if z_mod not in (settings.AI_MODULE_CODE, "ANOMALY", "ZONE"):
                continue

            pts = zone.get("points", [])
            if len(pts) < 3:
                continue

            matched = []
            for det in all_detections:
                bx1, by1, bx2, by2 = det["bbox"]
                foot_x, foot_y = (bx1 + bx2) / 2.0, by2
                center_x, center_y = (bx1 + bx2) / 2.0, (by1 + by2) / 2.0
                if self.is_point_in_polygon(foot_x, foot_y, pts) or self.is_point_in_polygon(center_x, center_y, pts):
                    matched.append(det)

            if len(matched) >= settings.MIN_ENCROACHMENT_COUNT:
                zone_violations.append({
                    "zone_id": zone.get("id"),
                    "zone_name": zone.get("name", "Zone"),
                    "points": pts,
                    "detections": matched
                })

        return all_detections, zone_violations
```

---

### 2.6. Mẫu Luồng Worker & MQTT Orchestrator (`src/worker.py` & `src/main.py`)

Toàn bộ mã nguồn hoàn chỉnh của `src/worker.py` và `src/main.py` đã được đặt tại thư mục [`sidewalk_ai/src/`](../../sidewalk_ai/src/) của workspace này. Những điểm thiết kế cốt lõi cần giữ nguyên khi mang sang dự án mới:

1. **Trong `worker.py` (`CameraStreamWorker`):**
   - Dùng `threading.Lock()` bảo vệ `self._zones` khi nhận bản tin hot-reload từ MQTT (`update_zones`).
   - Đặt `os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;3000000"` và `cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)` để loại bỏ độ trễ RTSP.
   - Duy trì bộ đếm `self._zone_first_seen[zone_id]` (kiểm tra `dwell_time >= CONFIRM_SECONDS`) và `self._zone_last_event[zone_id]` (kiểm tra `now - last_evt >= EVENT_COOLDOWN_SECONDS`) để triệt tiêu hoàn toàn hiện tượng spam sự kiện (`C08`).
   - Bắn BBox định kỳ theo `BBOX_PUBLISH_INTERVAL = 0.2s` (QoS 0) kèm `hud` để hiển thị trực quan trên màn hình Giám sát trực tiếp (`C07`).

2. **Trong `main.py` (`EdgeOrchestrator`):**
   - Trong `on_connect`: Đăng ký lại tất cả các topic camera và `ai_zones`, đồng thời gửi bản tin `smart_vms/cameras/getdevice` để đồng bộ trạng thái mới nhất ngay khi kết nối hoặc sau khi rớt mạng kết nối lại (`C01`).
   - Trong `_handle_camera_list`: Kiểm tra `settings.AI_MODULE_CODE in modules`. Nếu đang bật mà chưa có worker thì khởi tạo và `.start()`; nếu bị tắt mà đang có worker chạy thì gọi `.stop()` và xóa khỏi dictionary ngay lập tức (`C02`).
   - Trong `_handle_zones_update`: Bỏ qua các topic `/lines` (trừ khi làm bài toán đếm vạch) và bỏ qua các topic của sub-module khác để không bị ghi đè mất vùng giám sát trong RAM (`C03`).

---

### 2.7. Mẫu `Dockerfile` Chuẩn Production

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Cài đặt các thư viện hệ thống cần thiết cho OpenCV & FFmpeg (RTSP)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# Chạy dưới dạng module Python
CMD ["python", "-m", "src.main"]
```

**Lệnh Build & Run trên Server Production:**

```bash
# 1. Build Docker Image
docker build -t atin/ai-edge-worker:latest .

# 2. Chạy Container ngầm 24/7 với cơ chế tự khởi động lại và truyền file .env
docker run -d \
  --name ai_edge_sidewalk \
  --restart unless-stopped \
  --env-file .env \
  atin/ai-edge-worker:latest

# 3. Xem log hoạt động và thống kê [STATS] theo thời gian thực
docker logs -f ai_edge_sidewalk
```

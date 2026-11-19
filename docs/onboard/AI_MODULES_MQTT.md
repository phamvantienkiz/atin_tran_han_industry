# AIOC Staging — AI Modules & MQTT Contract

---

## 0. Kết nối cho AI edge

| Thành phần | Địa chỉ | Ghi chú |
|---|---|---|
| **MQTT broker** | `wss://aioc-stg.atin.vn/mqtt` — MQTT 3.1.1 qua WebSocket, TLS, cổng 443 | User `atin` / pass `Atin@2026#`. Client dùng transport WebSocket, path `/mqtt`, keepalive ≤ 60 s. Mẫu code §0.1 |
| RTSP camera | `rtsp_url` / `restream_urls` trong payload camera (§6.1) | MediaMTX, port `18554` |
| **Storage API** (upload ảnh) | `https://aioc-stg.atin.vn/storage/upload/file` | Upload ảnh snapshot trước khi publish event — xem §4 |
| Web VMS | `https://aioc-stg.atin.vn/` | Xem kết quả, bật module AI cho camera |
| Tài khoản thực tập sinh | `atin_tts` — zone 51 | Đã bật sẵn 5 tính năng AI — xem §9 |
### 0.1 Kết nối broker qua domain (Python paho-mqtt)

```python
import json, ssl
import paho.mqtt.client as mqtt

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="tts_edge_01", transport="websockets")
client.ws_set_options(path="/mqtt")
client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
client.username_pw_set("atin", "Atin@2026#")

def on_connect(c, userdata, flags, rc, props=None):
    print("connected:", rc)
    c.subscribe("smart_vms/cameras/zone/51", qos=1)
    c.publish("smart_vms/cameras/getdevice", json.dumps({"zone_id": 51, "organization_id": 103}), qos=1)

client.on_connect = on_connect
client.on_message = lambda c, u, m: print(m.topic, m.payload[:200])
client.connect("aioc-stg.atin.vn", 443, keepalive=30)
client.loop_forever()
```

paho-mqtt 1.x: bỏ tham số `mqtt.CallbackAPIVersion.VERSION2`. Thư viện khác dùng URL `wss://aioc-stg.atin.vn/mqtt` (Node `mqtt.js`, MQTTX: Host `wss://aioc-stg.atin.vn`, Port `443`, Path `/mqtt`). `mosquitto_pub`/`mosquitto_sub` không hỗ trợ WebSocket.

---

## 1. Tổng quan

```
                      ┌───────────────── Mosquitto staging (wss://aioc-stg.atin.vn/mqtt) ───────────────────┐
                      │                                                                                     │
 AI Edge workers ─pub─►  smart_vms/ai_events/{MODULE}        ──sub─►  Backend (vms_staging_backend-pid{N})   │
                      │  smart_vms/ai/bbox/{camera_code}      ──sub─►   ├─ check module bật + lưu sự kiện     │
                      │  smart_vms/ai/person/{camera_code}    ──sub─►   ├─ notifications + WebSocket → FE     │
                      │  smart_vms/cameras/getdevice[...]     ──sub─►   └─ alert / SOP (Telegram/Zalo/loa…)   │
                      │  smart_vms/thermal/get_*, smart_face/customers/service/get  (request)               │
                      │                                                                                     │
 AI Edge workers ◄sub──  smart_vms/cameras/zone/{zone_id}            ◄─pub─  Backend (retained)              │
                      │  smart_vms/cameras/company/{organization_id}                                        │
                      │  smart_vms/cameras/{code}/ai_zones[/{MODULE}][/lines]                               │
                      │  smart_vms/cameras/{preset}/{code}/ai_zones                                         │
                      │  smart_vms/thermal/{sensors|monitor_points}/company/{org}                           │
                      │                                                                                     │
 Frigate          ◄sub──  frigate[_{node}]/{camera_code}/recordings/set ◄─pub─  recording_scheduler          │
 IoT/Barrier/Loa  ◄sub──  smart_vms/iot|barrier/{device_id}/command, kcn/speaker/...  ◄─pub─  SOP engine     │
                      └─────────────────────────────────────────────────────────────────────────────────────┘
```

| Mục | Giá trị |
|---|---|
| Broker | `wss://aioc-stg.atin.vn/mqtt`, có user/pass (§0.1) |
| Backend client_id | `{MQTT_CLIENT_ID}-pid{PID}` = `vms_staging_backend-pid{N}`. Mỗi worker uvicorn một client; **chỉ worker giữ file lock** `MQTT_LEADER_LOCK` (mặc định `/tmp/smart_vms_mqtt_leader.lock`) mới subscribe, các worker khác chỉ publish. AI edge **không dùng client_id bắt đầu bằng `vms_staging_backend`** |
| Backend subscribe | `smart_vms/ai_events/#`, `smart_vms/bbox/#`, `smart_vms/ai/bbox/#`, `smart_vms/ai/person/#`, `smart_vms/cameras/getdevice[/zone/+]` (+ `get_device`, `get_devices`), `smart_vms/thermal/get_sensors[/+]`, `smart_vms/thermal/get_monitor_points[/+]`, `smart_vms/smart_face/customers/service/get[/+]` (đăng ký lại mỗi `on_connect`) |
| Encoding | JSON UTF-8. Payload không phải JSON → log `JSON decode error`, bỏ qua |
| Thời gian | ISO-8601, khuyến nghị có offset `+07:00`. Chuỗi không có timezone được hiểu là **giờ Việt Nam**. Số epoch: giây hoặc ms (>1e10 coi là ms) |
| Ảnh | Upload lên Storage API rồi gửi `object_key` qua `snapshot_url` (§4) |

### 1.1 MQTT "response"

MQTT là **fire-and-forget**, backend không trả lời các topic sự kiện. "Response" trong tài liệu này = *kết quả xử lý phía backend*: sự kiện được lưu, giá trị trả về nội bộ của `create_event`, WebSocket, notification, và hành vi khi lỗi. Lỗi (camera không tồn tại, module tắt, thiếu field) chỉ được **log** (`docker compose -f docker-compose.staging.yml logs -f backend`), AI edge không biết.

Có 3 nhóm topic **request/response** (backend publish kết quả retained lên topic trả về): xin danh sách camera (§5.10.1), thermal (§5.10.2), khách hàng Smart Face (§5.10.3).

### 1.2 Ghi chú vận hành quan trọng (từ code)

1. **Camera phải bật đúng module — áp cho MỌI sự kiện.** Sự kiện chỉ được lưu khi camera (`camera_id` hoặc `camera_code`, không phân biệt hoa thường) tồn tại và đã bật module tương ứng trên VMS. Chưa bật ⇒ **bỏ qua im lặng**. Vừa bật module trên UI cần chờ tối đa **1 phút** mới có hiệu lực.
2. **Backend subscribe QoS 0 + clean session** ⇒ sự kiện publish lúc backend down/restart/reconnect **bị mất**, không redelivery.
3. **Handler không chặn thread paho**: mỗi message được đẩy sang event loop chính (`run_coroutine_threadsafe`, fire-and-forget); nếu loop chưa chạy thì lưu trong thread riêng. Không retry, không dead-letter.
4. **Publish mặc định QoS 1** (`publish(..., qos=1)`), chờ ack tối đa 0.5 s. Nếu chưa kết nối broker chờ 3 s rồi trả `False`, **không retry**.
5. **Retained rỗng = xoá.** Backend publish `""` retained để xoá topic cũ (`/zones`, `/zones/lines`) và publish payload rỗng (`ai_zones: []`, `lines: []`) lên `ai_zones/{MODULE}` khi module bị tắt. Subscriber phải chịu được payload rỗng.
6. **Broker không ACL** (mọi client dùng chung một user), và `rtsp_url` trong payload camera chứa **user/pass MediaMTX** ⇒ ai kết nối được broker đều đọc được. Payload camera không chứa các cột `username/password/main_stream` của camera.
7. **Topic chứa `camera_code` nguyên văn** — chỉ thay `/`, `#`, `+` bằng `_`. Camera code có dấu cách/Unicode (vd `cổng 03`, `hàng rào 01`) xuất hiện nguyên trong topic. Subscriber nên dùng wildcard `+` thay vì tự ghép chuỗi.
---

## 2. Danh mục AI module

### 2.1 Module tiêu biểu

| Parent | Code | Tên hiển thị | Loại | Áp dụng | Số camera đang bật |
|---|---|---|---|---|---|
| — | `FACE` | Nhận diện khuôn mặt | AI | CAMERA | 7 |
| — | `PLATE` | Giám sát phương tiện | AI | CAMERA | 23 |
| — | `ZONE` | Giám sát vùng cấm | AI | CAMERA | 8 |
| — | `FIRE` | Cảnh báo cháy khói | AI | CAMERA | 2 |

Danh sách module bật trên từng camera được đẩy xuống edge qua `smart_vms/cameras/zone|company/...` (§6.1).

### 2.2 Định tuyến topic → handler

| `ai_modules` / hậu tố topic | Handler | Ghi chú |
|---|---|---|
| `FACE` | `handle_face_event` | §5.2 |
| `PLATE` | `handle_plate_event` | §5.3 |
| `ZONE` | `handle_zone_event` | §5.4 |
| `FIRE` | `handle_fire_smoke_event` | §5.5 |
| `FOOTFALL` | `handle_footfall_event` | §5.6 — camera cần bật `CUSTOMER` / `RETAIL_FOOTFALL` |
| Nhóm anomaly | `handle_anomaly_event` | §5.7 |
| **khác** — kể cả `SMART_FACE`, `FIRE_SMOKE`, `FIRESMOKE`, `COUNTING`, `ENTRY_EXIT`, `DOOR_GUARD`, `UAV`, `VANDALISM`, `CLIMB_DETECTION`, `FIGHT`, `CROWD`, `FALL`, `WEAPON`, `HEATMAP` | `handle_ai_event` | **chỉ log, không lưu** |

> ⚠️ Luôn dùng đúng code ở cột đầu. Ví dụ publish `smart_vms/ai_events/SMART_FACE` hoặc `ai_modules: "FIGHT"` ⇒ rơi vào `handle_ai_event` ⇒ mất.

---

## 3. Bảng tổng hợp topic

### 3.1 Edge → VMS (backend subscribe)

| Topic | Publisher → Subscriber | Retain | QoS khuyến nghị | Ghi chú |
|---|---|---|---|---|
| `smart_vms/ai_events/{MODULE}` | AI edge → Backend | no | 1 | sự kiện AI (§5.1–5.7) |
| `smart_vms/ai_events` | AI edge → Backend | no | 1 | legacy; cần `ai_modules` trong body |
| `smart_vms/ai/bbox/{camera_code}` | AI edge → Backend → WS | no | 0 | overlay realtime + heatmap (§5.8) |
| `smart_vms/bbox/{camera_code}` | như trên | no | 0 | tương đương |
| `smart_vms/ai/person/{camera_code}` | tracker → Backend → WS | no | 0 | §5.9 |
| `smart_vms/cameras/getdevice` · `.../getdevice/zone/{zone_id}` (+ `get_device`, `get_devices`) | hệ thống con → Backend | no | 1 | request danh sách camera (§5.10.1) |
| `smart_vms/thermal/get_sensors[/{org}]`, `smart_vms/thermal/get_monitor_points[/{org}]` | edge → Backend | no | 1 | §5.10.2 |
| `smart_vms/smart_face/customers/service/get[/{org}]` | edge → Backend | no | 1 | §5.10.3 |

### 3.2 VMS → Edge / thiết bị (backend publish)

| Topic | Subscriber | Retain | QoS | Trigger |
|---|---|---|---|---|
| `smart_vms/cameras/zone/{zone_id}` | AI edge | **yes** | 1 | startup, CRUD camera / bật-tắt AI, đổi Zone, request getdevice, kiểm tra kết nối (nếu `AUTO_TELNET_ENABLED`) |
| `smart_vms/cameras/company/{organization_id}` | AI edge | **yes** | 1 | như trên |
| `smart_vms/cameras/{camera_code}/ai_zones` | AI edge | **yes** | 1 | startup + CRUD zone/line + bật/tắt AI |
| `smart_vms/cameras/{camera_code}/ai_zones/{MODULE}` | AI edge (lọc sẵn theo module) | **yes** | 1 | như trên; payload rỗng khi module tắt |
| `smart_vms/cameras/{camera_code}/ai_zones/lines` | worker đếm line | **yes** | 1 | như trên |
| `smart_vms/cameras/{camera_code}/ai_zones/{MODULE}/lines` | worker đếm line theo module | **yes** | 1 | như trên |
| `smart_vms/cameras/{camera_code}/zones`, `.../zones/lines` | — | yes (`""`) | 1 | **chỉ để xoá retained legacy** |
| `smart_vms/cameras/{preset_token}/{camera_code}/ai_zones` | AI edge PTZ | **yes** | 1 | startup + CRUD polygon theo preset |
| `smart_vms/thermal/sensors/company/{org}` | thermal edge | **yes** | 1 | startup + request |
| `smart_vms/thermal/monitor_points/company/{org}` | thermal edge | **yes** | 1 | startup + request |
| `smart_vms/smart_face/customers/service/company/{org}` (hoặc `response_topic`) | edge | **yes** | 1 | request |
| `smart_vms/smart_face/customers/service/error` | edge | no | 1 | request thiếu `organization_id` |
| `frigate/{camera_code}/recordings/set` · `frigate_{node_code}/{camera_code}/recordings/set` | Frigate | no | 1 | mỗi phút khi trạng thái đổi + API toggle |
| `smart_vms/recording_scheduler/state/{camera_code}` | giám sát | **yes** | 1 | cùng lúc với lệnh Frigate |
| `smart_vms/recording_scheduler/events` | giám sát | no | 1 | lưu cấu hình ghi hình / tick sync |
| `smart_vms/iot/{device_id}/command` | thiết bị IoT | no | 1 | SOP node `thiet_bi` (env `SOP_IOT_COMMAND_TOPIC`) |
| `smart_vms/barrier/{device_id}/command` | barrier | no | 1 | SOP node `barrier` (env `SOP_BARRIER_COMMAND_TOPIC`) |
| `kcn/speaker/device/{device_id}` · `kcn/speaker/broadcast/{zone}` | loa IP | no | 1 | SOP phát thanh |

---

## 4. Upload ảnh snapshot

Ảnh **không gửi qua MQTT**. Mỗi event có ảnh đi theo 4 bước:

| Bước | Việc | Kết quả |
|---|---|---|
| 1 | Upload ảnh lên Storage API | Storage API lưu ảnh vào bucket `vms-captures` |
| 2 | Lấy `object_key` trong response | Khoá của ảnh, ví dụ `zone/2026-10-21/camera_<camera_id>/<uuid>.jpg` |
| 3 | Publish event MQTT với `"snapshot_url": "<object_key>"` | Backend lưu event kèm ảnh |
| 4 | Kiểm tra ảnh trên VMS | Ảnh hiển thị qua backend |

### 4.1 Bước 1 — Upload ảnh

```
POST https://aioc-stg.atin.vn/storage/upload/file
Content-Type: multipart/form-data
```

Kích thước file tối đa **10 MB**.

| Field (form-data) | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `file` | file ảnh (`.jpg` / `.png`) | **có** | ảnh snapshot |
| `camera_id` | string | **có** | UUID camera (hoặc mã camera); dùng làm thư mục `camera_<camera_id>` |
| `category` | string | không, mặc định `media` | thư mục gốc theo module: `face`, `plate`, `zone`, `fire`, `footfall`, `anomaly` |

Ví dụ:

```bash
curl -X POST https://aioc-stg.atin.vn/storage/upload/file \
  -F "file=@snapshot.jpg" \
  -F "camera_id=6aee1244-632d-43e3-8ef4-447ad539277a" \
  -F "category=zone"
```

### 4.2 Bước 2 — Lấy `object_key` từ response

Response `200`:

```json
{
  "object_key": "zone/2026-10-21/camera_6aee1244-632d-43e3-8ef4-447ad539277a/a0782800...f256.jpg",
  "url": "http://127.0.0.1:18646/vms-captures/zone/...jpg?AWSAccessKeyId=...&Signature=...&Expires=...",
  "success": true,
  "error": null
}
```

| Field | Ghi chú |
|---|---|
| `object_key` | **giá trị cần dùng** — đặt vào `snapshot_url` của event. Cấu trúc: `{category}/{YYYY-MM-DD}/camera_{camera_id}/{uuid}.{ext}` |
| `url` | link presigned nội bộ (host `127.0.0.1`, hết hạn 24 h) — **không dùng** |
| `success` / `error` | kết quả upload |

| Mã lỗi | Ý nghĩa |
|---|---|
| `422` | thiếu `file` hoặc `camera_id` |
| `413` | file quá 10 MB |
| `403` | sai method (chỉ nhận `POST`) |
| `500` | upload thất bại, body `{"detail": "..."}` ⇒ vẫn có thể publish event không kèm ảnh |

### 4.3 Bước 3 — Publish event kèm ảnh

Đặt `object_key` vào `snapshot_url`. Ví dụ event ZONE trên topic `smart_vms/ai_events/ZONE`:

```json
{
  "ai_modules": "ZONE",
  "camera_id": "6aee1244-632d-43e3-8ef4-447ad539277a",
  "event_time": "2026-10-21T08:30:00+07:00",
  "payload": { "zone_id": "<ai_zone uuid>" },
  "snapshot_url": "zone/2026-10-21/camera_6aee1244-632d-43e3-8ef4-447ad539277a/a0782800...f256.jpg"
}
```

### 4.4 Bước 4 — Kiểm tra ảnh

Mở `https://aioc-stg.atin.vn/api/v1/snapshot/image?object_key=<object_key>` ⇒ trả về ảnh.

### 4.5 Cách gửi ảnh khác (không khuyến nghị)

- `snapshot_url` là URL ảnh public.
- `snapshot_base64`: ảnh base64 nằm trong bản tin MQTT, làm bản tin rất nặng.

---

## 5. Backend SUBSCRIBE — payload edge gửi & response của backend

### 5.1 `smart_vms/ai_events/{MODULE}` — định tuyến chung

**Routing key** (`on_message`):

1. Lấy giá trị đầu tiên không rỗng: `ai_modules` → `module_code` → `ai_module_code` → `event_module` → `submodule_code` → hậu tố topic. List ⇒ phần tử đầu; strip + UPPER.
2. Nếu vẫn rỗng (chỉ xảy ra với topic legacy `smart_vms/ai_events`) và `event_type` / `payload.event_type` / `payload.crowd_event_type` / `payload.crowd_type` / `payload.behavior_type` thuộc tập anomaly event (`CROWD`, `FIGHT`, `FALL`, `INTRUSION`, `SMOKING`, `WATER_LEVEL`, `LITTERING`, `SIDEWALK`, `WEAPON`, …) ⇒ `ANOMALY`.

| Giá trị | Handler |
|---|---|
| `ZONE` | `handle_zone_event` |
| `PLATE` | `handle_plate_event` |
| `FACE` | `handle_face_event` |
| `FIRE` | `handle_fire_smoke_event` |
| `FOOTFALL` | `handle_footfall_event` |
| `ANOMALY`, `BEHAVIOR`, `BEHAVIOUR`, `CROWD_DETECTION`, `FALL_DETECTION`, `DANGER_ZONE_HAND_INTRUSION`, `SMOKING`, `SMOKING_DETECTION`, `FIGHT_DETECTION`, `INTRUSION_DETECTION`, `SUICIDE_ATTEMPT`, `WEAPON_DETECTION`, `LITTERING`, `LITTERING_DETECTION`, `SIDEWALK`, `SIDEWALK_ENCROACHMENT`, `WATER_LEVEL`, `WATER_LEVEL_DETECTION`, `MUC_NUOC`, `FLOOD_DETECTION` | `handle_anomaly_event` |
| khác | `handle_ai_event` — **chỉ log, không lưu** |

**Trường chung** — áp dụng cho FACE, PLATE, ZONE, FIRE, FOOTFALL, ANOMALY (§5.2–5.7).

| Field | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `ai_modules` | string | **có** | code module, trùng với hậu tố topic |
| `camera_id` | UUID | **có** | camera phải tồn tại trên VMS; sai UUID hoặc không tồn tại ⇒ event bị bỏ |
| `camera_code` | string | khuyến nghị | mã camera trên VMS |
| `camera_name` | string | không | tên camera |
| `event_time` | string ISO-8601 có múi giờ (`2026-10-20T08:30:00+07:00`) hoặc số epoch (giây/ms) | khuyến nghị | thời điểm phát hiện. Không gửi ⇒ dùng giờ backend nhận. Sai định dạng ⇒ event bị bỏ |
| `entity_type` | string | không | loại đối tượng, giá trị theo từng module |
| `entity_id` | string | không | id đối tượng / track id |
| `confidence` | float 0..1 | không | độ tin cậy |
| `snapshot_url` | string | khuyến nghị | `object_key` nhận từ Storage API (§4) |
| `snapshot_base64` | string | không | ảnh base64, chỉ dùng khi không có `snapshot_url` |
| `payload` | object | theo module | dữ liệu riêng của module |

Backend tự bổ sung từ thông tin camera: `organization_id`, `site_id`, `area_id`, `zone_id`, `node_id`, `node_path`.

**Response chung khi thành công**: lưu sự kiện; log `[MQTT] <MODULE> event saved ...`; `create_event` trả `{"event": <row>, "module_code": "<CODE>", ...}`; thường kèm thông báo trên VMS.
**Khi camera chưa bật module**: bỏ qua, chỉ log.
**Khi lỗi**: log + traceback; không retry; không phản hồi edge.

---

### 5.2 FACE — nhận diện khuôn mặt

**Topic**: `smart_vms/ai_events/FACE`

**Payload (pub)** — chuẩn mới đặt các field ở **root**:

```json
{
  "ai_modules": "FACE",
  "camera_id": "<camera uuid>",
  "camera_code": "CAM_HS_01",
  "access_time": "2026-10-20T08:30:00+07:00",
  "event_time": "2026-10-20T08:30:00+07:00",
  "user_code": "EMP001",
  "user_name": "Nguyen Van A",
  "department_name": "Phòng Kỹ thuật",
  "direction": "IN",
  "score_match": 0.92,
  "gender": 1,
  "age": 30,
  "person_id": 123,
  "device_name": "Cổng chính",
  "face_feature": "<base64 embedding>",
  "payload": {
    "direction": "IN",
    "person": { "person_identity": "EMP001", "person_name": "Nguyen Van A", "department_name": "Phòng Kỹ thuật" }
  },
  "snapshot_url": "face/2026-10-20/xxx.jpg",
  "snapshot_base64": null
}
```

| Field | Ghi chú xử lý |
|---|---|
| `camera_id` / `camera_code` | gửi một trong hai |
| `access_time` (ưu tiên) / `event_time` | chuỗi không múi giờ = giờ VN (env `SMART_FACE_NAIVE_ACCESS_TIME_IS_UTC=1` để coi là UTC). Sai định dạng ⇒ dùng giờ backend nhận |
| `user_code` / `payload.person.person_identity` | khoá nhận diện. Thiếu `department_*` ⇒ tra `smf_employees` + `smf_departments` theo `user_code` + organization |
| `user_name` / `payload.person.person_name` | |
| `department_name` (ưu tiên) / `dep_name` | |
| `direction` | chỉ `IN`/`OUT`, khác ⇒ `IN` |
| `score_match` (alias `match_score`, `score`, `confidence`) | 0<x≤1 ⇒ ×100 → int; âm ⇒ NULL |
| `face_feature` (alias `face_features`, `embedding`, `feature_vector`, `face_embedding`) | lưu bytea |
| `image` / `snapshot_url` / `snapshot_base64` / `base64` | giá trị đầu tiên không rỗng → cột `image` |
| Root extra được forward | `device_name`, `department_id`, `event_id`, `gender`, `age`, `area_name`, `area_id`, `organization_id`, `device_id`, `server_url`, `event_type_id`, `status`, `person_id`, `person_type`, `person_type_name` |
| `organization_id` | payload, không có ⇒ lấy từ camera; vẫn không có ⇒ 400 `Không xác định được organization_id cho FACE event` |
**Response (sub)**
- **Dedup**: rate-limiter in-memory key (`FACE`, camera, `user_code` → `user_name` → `STRANGER`) cửa sổ 1 s **và** kiểm tra sự kiện đã lưu ±1 s quanh `access_time` ⇒ trả `{"event": <row cũ>, "deduped": true}`, không insert.
- Ngược lại INSERT, trả `{"event": {...}, "module_code": "FACE"}`.
- Notification `kind=face` (LOW nếu có `user_code`, MEDIUM nếu người lạ) → `NEW_NOTIFICATION`.
- Thread nền `dispatch_face_event_alert_background(payload)` → alert service (chạy cả khi camera chưa bật module).

---

### 5.3 PLATE — biển số / vi phạm giao thông

**Topic**: `smart_vms/ai_events/PLATE`

Cùng topic, **hai loại payload**: (1) nhận diện — không có `payload.violation_type_code`; (2) vi phạm — có `payload.violation_type_code` (mã trong `its.violation_type_catalog`).

**Payload nhận diện (pub)**

```json
{
  "ai_modules": "PLATE",
  "camera_id": "<camera uuid>",
  "event_time": "2026-10-20T08:30:00+07:00",
  "entity_type": "VEHICLE",
  "entity_id": "plate_30A12345_20261020083000",
  "payload": {
    "direction": "IN",
    "confidence": 0.95,
    "vehicle": {
      "license_plate": { "text": "30A-12345", "status": "DETECTED", "plate_color": "WHITE" },
      "vehicle_type": "CAR", "car_type": "SEDAN", "manufacturer": "TOYOTA", "color": "BLACK",
      "total_number_of_seats": 5, "chassis_number": "RLHABC12345678901", "owner_name": "Nguyen Van A"
    }
  },
  "snapshot_url": "plate/2026-10-20/xxx.jpg",
  "snapshot_base64": null
}
```

**Payload vi phạm** = payload trên + trong `payload`:

```json
"violation_type_code": "RED_LIGHT",
"violation_evidence": { "lane": "A1", "confidence": 0.97, "rule": "red_light_crossing" }
```

| Field | Ghi chú xử lý |
|---|---|
| `camera_id` | **bắt buộc**, phải tồn tại. `camera_code`, `camera_name`, `organization_id` **luôn lấy từ thông tin camera** |
| `payload.vehicle.license_plate.text` | biển số. **Qua MQTT chỉ field lồng này có hiệu lực** (handler không forward `license_plate`/`plate_number` root). Chuẩn hoá: UPPER, bỏ ký tự ngoài A-Z0-9 |
| `payload.direction` | `IN`/`OUT`, khác ⇒ `IN` |
| `.status`, `.plate_color`, `vehicle_type`, `car_type`, `manufacturer`, `color`, `total_number_of_seats` | lưu cột tương ứng |
| `chassis_number` (alias `chassisNumber`, `vin`), `owner_name` / `vehicle_owner_name` (camelCase cũng nhận) | tìm ở `vehicle`, `payload`, root |
| `violation_type_code` | UPPER; rỗng ⇒ nhận diện thường |
| `violation_evidence` | object (không phải object ⇒ bọc `{"value": ...}`) |
| blacklist / whitelist | **AI không gửi**; backend khớp theo biển chuẩn hoá + organization (`is_active=TRUE`) |

**Response (sub)**
- **Dedup**: rate-limiter in-memory (`PLATE`, camera, biển chuẩn hoá hoặc `UNKNOWN_PLATE`) 1 s **và** kiểm tra sự kiện đã lưu ±1 s theo (organization, camera, biển) — chỉ khi biết biển ⇒ trả `{"event": <row cũ>, "deduped": true}`.
- Ngược lại INSERT `plate_event` (`is_blacklisted`, `blacklist_id`, `is_whitelisted`, `whitelist_id`), trả `{"event": <row>, "module_code": "PLATE"}`.
- Có `violation_type_code`: INSERT `plate_violation_event` → tra catalog (`fine_min/max`, `legal_ref`) → INSERT `plate_violation_case` (`status='PENDING'`) → `is_promoted=TRUE`; trả thêm `violation_event_id`, `violation_case_id`. Không transaction; lỗi chỉ log, `plate_event` vẫn giữ.
- WebSocket **`NEW_PLATE_EVENT`**.
- Notification `PLATE_BLACKLIST` (HIGH) **chỉ** khi biển thuộc blacklist.
- Thread nền `dispatch_plate_event_alert_background(payload)` (chạy cả khi camera chưa bật module).

---

### 5.4 ZONE — vùng cấm / line crossing

**Topic**: `smart_vms/ai_events/ZONE`

```json
{
  "ai_modules": "ZONE",
  "camera_id": "<camera uuid>",
  "camera_code": "zone1",
  "event_time": "2026-10-20T08:30:00+07:00",
  "entity_type": "PERSON",
  "entity_id": "person_001",
  "person_name": "Nguyen Van A",
  "person_identity": "P001",
  "count": 2,
  "payload": { "zone_id": "<ai_zone uuid hoặc zone_code>", "zone_name": "Vùng cấm A", "direction": "IN" },
  "snapshot_url": "zone/2026-10-20/xxx.jpg"
}
```

Phương tiện: `entity_type: "VEHICLE"`, thay `person_*` bằng `license_plate`. Line crossing có thể gửi `trigger: {direction, confidence}`.

| Field | Ghi chú xử lý |
|---|---|
| `payload.zone_id` | **bắt buộc** (hoặc `zone_id` root), thiếu ⇒ 400. UUID → tra `restricted_zones.id`; chuỗi khác → tra `zone_code`; **không có thì tự INSERT** zone mới |
| `payload.zone_name` | thiếu ⇒ lấy từ `restricted_zones` |
| direction | `payload.direction` → `direction` → (`event_type ∈ {EXIT, OUT}` ⇒ `OUT`, còn lại `IN`); UPPER, cắt 10 ký tự |
| `camera_id` / `camera_code` | gửi một trong hai; thiếu `camera_code` ⇒ lấy hậu tố topic. Camera **không bắt buộc tồn tại** (khớp `id` → `code`/`name`/`mediamtx_path`) |
| `organization_id` | có thể gửi trong payload; không gửi ⇒ lấy từ camera |
| `entity_type` | `PERSON`/`VEHICLE`, khác ⇒ `PERSON`; `entity_id` mặc định `"unknown"` |
| số người | `count` / `person_count` / `num_persons` (root hoặc payload) → độ dài `detections` → số bbox gần nhất của camera; lưu vào `payload.count`, `payload.person_count` |

**Response (sub)**
- INSERT `zone_event`; trả `{event, zone, zone_name, camera_code, camera_name, entity_type, entity_id, direction}`.
- WebSocket **`NEW_ZONE_EVENT`** — hiện bị **phát 2 lần** (trong `create_event` và trong handler).
- Business rules (best-effort): IN ⇒ upsert `zone_presence`; `zone_access_policy` `allowed=false` + khung giờ khớp ⇒ `zone_incident` `UNAUTHORIZED_ENTRY`; OUT + `must_stay=true` ⇒ `MUST_STAY_BREACH`. Incident mở trong 600 s được gom.
- Notification `kind=zone` (HIGH); thread nền `dispatch_zone_event_alert_background`.

---

### 5.5 FIRE — cháy / khói

**Topic**: `smart_vms/ai_events/FIRE`

```json
{
  "ai_modules": "FIRE",
  "camera_id": "<camera uuid>",
  "camera_code": "CAM_06",
  "event_time": "2026-10-20T08:30:00+07:00",
  "entity_type": "FIRE",
  "entity_id": "fire_evt_0001",
  "payload": { "alert_level": "HIGH" },
  "snapshot_url": "fire/2026-10-20/xxx.jpg"
}
```

| Field | Ghi chú |
|---|---|
| `camera_id` | bắt buộc; `camera_code`/`camera_name` lấy từ thông tin camera |
| `entity_type` | `FIRE` (mặc định) / `SMOKE` / tuỳ biến; UPPER |
| `payload.alert_level` | `HIGH`/`MEDIUM`/`LOW` (UPPER); khác ⇒ `NULL` |

**Response (sub)**: không dedup; INSERT; trả `{"event": <row>, "module_code": "FIRE"}`; notification `kind=fire`; alert nền `dispatch_fire_event_alert_background`. Không phát `BBOX_UPDATE` từ event — muốn vẽ khung phải publish topic bbox (§5.8).

---

### 5.6 FOOTFALL — đếm lưu lượng theo line/zone

**Topic**: `smart_vms/ai_events/FOOTFALL` — camera cần bật `CUSTOMER` / `RETAIL_FOOTFALL` / `RETAIL`

```json
{
  "ai_modules": "FOOTFALL",
  "camera_id": "<camera uuid>",
  "camera_code": "marou-cam01",
  "event_time": "2026-10-20T08:30:00+07:00",
  "entity_type": "PERSON",
  "entity_id": "track_142",
  "payload": { "zone_id": "zone_236", "zone_name": "Entrance", "direction": "IN", "count": { "in": 128, "out": 95 } },
  "snapshot_url": "footfall/2026-10-20/xxx.jpg"
}
```

| Field | Ghi chú |
|---|---|
| `camera_id` | bắt buộc; `camera_code`/`camera_name` ưu tiên giá trị edge gửi |
| `entity_type` | handler mặc định `PERSON` |
| `payload` | lưu nguyên JSON (backend không tổng hợp `count`) |

**Response (sub)**: không dedup; INSERT; trả `{"event": <row>, "module_code": "FOOTFALL"}`; notification `kind=footfall` (LOW, không kích hoạt SOP).

---

### 5.7 Nhóm ANOMALY — hành vi bất thường

**Topic**: `smart_vms/ai_events/{SUBMODULE}`

**Khuyến nghị gửi**:
- Topic & `ai_modules` = **code đầy đủ** (`CROWD_DETECTION`, `FIGHT_DETECTION`, …) — `FIGHT`/`CROWD`/`FALL`/`WEAPON` sẽ bị drop ở routing.
- `submodule_code` = code đầy đủ. Thiếu `submodule_code` mà `event_type` là giá trị lạ (vd `HIGH_DENSITY`) ⇒ không xác định được module ⇒ skip.
- `payload.type` = **loại chi tiết hợp lệ** theo bảng dưới.

```json
{
  "ai_modules": "CROWD_DETECTION",
  "submodule_code": "CROWD_DETECTION",
  "camera_id": "<camera uuid>",
  "camera_code": "CAM_HN_02",
  "event_time": "2026-10-20T08:30:00+07:00",
  "event_type": "CROWD_DETECTION",
  "confidence": 0.88,
  "severity": "MEDIUM",
  "payload": { "type": "HIGH_DENSITY", "person_count": 18, "threshold": 12, "zone_name": "Sảnh" },
  "snapshot_url": "crowd/2026-10-20/xxx.jpg",
  "video_clip_url": null
}
```

| Sub-module (code `ai_module`) | `payload.type` hợp lệ (nếu thiếu và chỉ có 1 giá trị ⇒ tự điền) | Alias sub-module nhận ở `event_type`/`submodule_code` |
|---|---|---|
| `CROWD_DETECTION` | `CROWD`, `CROWD_DETECTION`, `CROWD_THRESHOLD`, `CROWD_THRESHOLD_EXCEEDED`, `ABNORMAL_DENSITY`, `DENSITY`, `HIGH_DENSITY`, `SUDDEN_GATHERING`, `CROWD_GATHERING`, `GATHERING` | `CROWD`, `PHAT_HIEN_DAM_DONG` |
| `FIGHT_DETECTION` | `FIGHT` | `FIGHT`, `AU_DA` |
| `FALL_DETECTION` | `FALL` | `FALL` |
| `INTRUSION_DETECTION` (leo trèo) | `INTRUSION` | `INTRUSION`, `CLIMBING`, `LEO_TREO` |
| `SMOKING_DETECTION` | `SMOKING` | `SMOKING`, `SMOKE`, `SMOKE_DETECTION`, `HUT_THUOC`, `HUT_THUOC_LA` |
| `WEAPON_DETECTION` | `WEAPON` | `WEAPON` |
| `DANGER_ZONE_HAND_INTRUSION` | `DANGER_ZONE_HAND_INTRUSION` | `DANGER_ZONE_INTRUSION`, `HAND_INTRUSION` |
| `SUICIDE_ATTEMPT` | `SUICIDE_ATTEMPT` | — |
| `WATER_LEVEL_DETECTION` | `WATER_LEVEL`, `WATER_LEVEL_ALERT`, `FLOOD` | `WATER_LEVEL`, `WATER_LEVEL_ALERT`, `FLOOD`, `FLOOD_DETECTION`, `MUC_NUOC` |
| `LITTERING_DETECTION` | tự do | `LITTERING`, `LITTER`, `VUT_RAC`, `TRASH`, `GARBAGE` |
| `SIDEWALK_ENCROACHMENT` | tự do | `SIDEWALK`, `ENCROACHMENT`, `LAN_CHIEM_VIA_HE`, `VIA_HE` |

`payload.type` ngoài danh sách ⇒ 400 `payload.type invalid for X; allowed: ...` (event bị bỏ). Nếu không gửi `payload.type`, backend lấy `event_type` khi khác code sub-module — vì vậy đặt `event_type` = alias Việt (`LEO_TREO`, `HUT_THUOC`, `AU_DA`, `MUC_NUOC`…) sẽ **fail validate**; dùng `payload.type` chuẩn.

| Field | Ghi chú |
|---|---|
| `camera_id` | bắt buộc, phải tồn tại |
| `severity` | handler MQTT mặc định **`HIGH`** (create_event mặc định MEDIUM nhưng không áp qua MQTT); UPPER |
| `entity_type` | handler mặc định `PERSON` |
| `zone_id` | UUID tuỳ chọn (sai ⇒ NULL); `zone_name` chuyển nguyên. **Không** tự điền khu vực từ `admin_area` |
| `water_level`, `unit` (mặc định `cm`), `person_count` / `count` / `crowd_count` | không có cột riêng, nằm trong JSON `payload`; dùng cho nội dung cảnh báo |
| ảnh | `snapshot_url`, `snapshot_base64`; `video_clip_url` |

**Response (sub)**: không dedup; INSERT với `module_code='ANOMALY'`, `event_type` = sub-module chuẩn (vd `FIGHT_DETECTION`), `payload` + `raw_payload` (toàn bộ message, đã bỏ key ảnh). Trả `{event, module_code, camera_code, camera_name}`. Notification: **2 dòng** (`kind=anomaly` trong service + kind theo loại `FIGHT`/`CROWD`/`WATER_LEVEL`… trong handler).

---

### 5.8 BBox realtime — `smart_vms/ai/bbox/{camera_code}` (+ `smart_vms/bbox/{camera_code}`)

QoS 0, không retain. Hai luồng tách biệt: **vẽ overlay** (WS ngay) và **lưu heatmap** (queue riêng, throttle, có thể drop khi quá tải).

```json
{
  "camera_code": "CAM_01",
  "camera_id": "<camera uuid>",
  "organization_id": 110,
  "ai_modules": "ZONE",
  "timestamp": 1729068000.123,
  "detections": [
    { "id": "obj_1", "class": "person", "confidence": 0.92, "bbox": [0.1, 0.2, 0.4, 0.8], "track_id": 1,
      "global_id": "person_1001", "frame_x": 0.25, "frame_y": 0.8, "map_x": 0.41, "map_y": 0.63 }
  ],
  "hud": { "text": "IN: 12 | OUT: 8", "display_ms": 2500, "color": "#22c55e" }
}
```

| Field | Ghi chú |
|---|---|
| `camera_code` | `camera_code` → `cameraCode` → `camera` → `camera_id` → hậu tố topic |
| `detections[]` | phần tử không phải object hoặc thiếu `bbox` bị loại khỏi overlay. `cls`→`class`, `conf`→`confidence`. Overlay bỏ các key heatmap (`map_*`, `pdf_*`, `frame_*`, `floor_*`, `heatmap`) |
| `bbox` | `[x1, y1, x2, y2]` góc trên-trái → góc dưới-phải. Chuẩn hoá 0..1 (khuyến nghị); nếu `x2 > 1` hoặc `y2 > 1` thì hiểu là pixel theo độ phân giải video |
| `class`, `confidence` | hiện thành nhãn trên khung |
| `ai_modules` | alias `module_code`, `ai_module_code`, `ai_module`, `ai_module_id`; string/list → UPPER. Nếu có, WS **chỉ phát khi camera bật module đó** |
| `hud` | object có `text`/`label` hoặc `lines[]`; tuỳ chọn `display_ms`/`duration_ms`/`ttl_ms`, `color`, `line_colors`. Hoặc dạng phẳng `hud_text`/`hud_label` + `hud_display_ms`/`hud_duration_ms` |
| heatmap | detection có `frame_x`,`frame_y` **và** (`map_x`,`map_y` hoặc `pdf_x`,`pdf_y`) + `organization_id` (alias `companyId`, `company-id`) ⇒ lưu `heatmap.heatmap_event` + `heatmap_detection` (nếu `BBOX_HEATMAP_SAVE_ENABLED`) |

**Response (sub)**: WebSocket **`BBOX_UPDATE`** `{camera_code, organization_id, camera_id, ai_modules, detections, timestamp, hud}` — chỉ gửi tới client VMS đang xem camera đó. Cập nhật cache số người/camera (dùng điền `count` cho cảnh báo ZONE).

**Điều kiện để khung hiện trên Web VMS** (Giám sát trực tiếp):

1. Camera đang mở trong một ô và nút **Phát hiện AI** đang bật.
2. `ai_modules` trùng **chức năng AI đang chọn trên ô đó** (nút "AI: …" ở góc ô) và camera đã bật module này. Gửi module khác ⇒ không vẽ.
3. Khung tự xoá sau khoảng 0,35 s không nhận bbox mới ⇒ edge cần gửi liên tục theo frame (khuyến nghị 5–10 lần/giây, ví dụ §9.6 gửi mỗi 0,2 s).

### 5.9 Person tracker — `smart_vms/ai/person/{camera_code}`

```json
{ "camera_code": "CAM_01", "camera_id": "<uuid>", "organization_id": 103, "timestamp": 1729068000.1,
  "persons": [ { "track_id": 7, "bbox": [0.1, 0.2, 0.3, 0.9] } ] }
```

Không lưu; WebSocket **`PERSON_UPDATE`** `{camera_code, organization_id, camera_id, persons, timestamp}` (chỉ client đang xem camera).

### 5.10 Topic request/response

#### 5.10.1 Xin danh sách camera — `smart_vms/cameras/getdevice[...]`

| Request | Response (retained) |
|---|---|
| `smart_vms/cameras/getdevice` payload `{"organization_id": 110}` (hoặc `company_id`) | `smart_vms/cameras/zone/{zone_id}` cho từng zone + `smart_vms/cameras/company/110` |
| `smart_vms/cameras/getdevice` payload `{"zone_id": 274, "organization_id": 110}` | các topic trên, lọc theo zone |
| `smart_vms/cameras/getdevice/zone/{zone_id}` | ⚠️ xem lưu ý |

Alias `get_device`, `get_devices`. Payload xem §6.1.

> ⚠️ **Lỗi đã biết**: với `.../getdevice/zone/{id}` backend lấy số cuối topic làm **cả** `zone_id` **và** `organization_id` ⇒ thường không có camera nào ⇒ không publish gì. `.../getdevice/company/{id}` **không được subscribe**. ⇒ Dùng topic gốc `smart_vms/cameras/getdevice` kèm payload, hoặc chỉ cần subscribe retained `smart_vms/cameras/company/{org}`.

#### 5.10.2 Thermal

| Request | Response (retained) |
|---|---|
| `smart_vms/thermal/get_sensors[/{org}]` | `smart_vms/thermal/sensors/company/{org}` `{sensors[], total, timestamp}` |
| `smart_vms/thermal/get_monitor_points[/{org}]` payload tuỳ chọn `{"sensor_id","camera_id"}` | `smart_vms/thermal/monitor_points/company/{org}` `{monitor_points[], total, timestamp}` |

#### 5.10.3 Khách hàng nhóm Service (Smart Face)

Request `smart_vms/smart_face/customers/service/get/{org}` (hoặc không hậu tố + `{"organization_id": 23}`), tuỳ chọn `{"response_topic": "..."}`. Response retained `smart_vms/smart_face/customers/service/company/{org}` (hoặc `response_topic`): `{organization_id, customers[], total, timestamp}`. Thiếu organization ⇒ `smart_vms/smart_face/customers/service/error` `{ok:false, error, request_topic, timestamp}`.

---

## 6. Backend PUBLISH — payload backend gửi & ai nhận

`publish(topic, payload, retain=False, qos=1)`: dict/list → `json.dumps(default=str)`. Startup (`main.py`): `sync_cameras_to_mqtt`, `sync_zones_to_mqtt`, `sync_preset_zones_to_mqtt`, `sync_thermal_sensors_to_mqtt`, `sync_thermal_monitor_points_to_mqtt`.

### 6.1 `smart_vms/cameras/zone/{zone_id}` và `smart_vms/cameras/company/{organization_id}` — danh sách camera (retained)

- `zone_id` = Zone phân cấp (Site → Area → Zone); camera chưa gán Zone ⇒ `0`. Camera không có organization không vào topic company.
- **Trigger**: startup; thêm/sửa/xoá camera; bật/tắt AI; đổi Zone (`routers/hierarchy.py` publish lại zone cũ + mới); request getdevice; vòng kiểm tra kết nối khi có camera đổi trạng thái (chỉ khi `AUTO_TELNET_ENABLED=true` — staging đang `false`).
- Chỉ gồm module đang bật trên camera và hiển thị cho organization.

**Payload mẫu**:

```json
{
  "cameras": [
    {
      "id": "e4ed835d-d3dc-452b-b9b0-d5f5db8c7b54",
      "code": "CAM_04",
      "status": "ONLINE",
      "ai_modules": ["PLATE", "ZONE"],
      "rtsp_url": "rtsp://<mtx_user>:<mtx_pass>@192.168.1.250:18554/c103_CAM_04_detect",
      "restream_urls": {
        "PLATE": "rtsp://<mtx_user>:<mtx_pass>@192.168.1.250:18554/c103_CAM_04_detect",
        "ZONE":  "rtsp://<mtx_user>:<mtx_pass>@192.168.1.250:18554/c103_CAM_04_detect"
      },
      "zone_id": 24
    }
  ],
  "total": 1,
  "company_id": 103,
  "organization_id": 103
}
```

Topic `zone/{id}` có `zone_id` thay cho `company_id`/`organization_id`.

| Field | Nguồn / ghi chú |
|---|---|
| `id`, `code`, `status`, `zone_id` | bảng `camera` |
| `ai_modules` | list code module đang bật |
| `rtsp_url` | `rtsp://{MEDIAMTX_RTSP_USER}:{PASS}@{MEDIAMTX_RTSP_HOST}:{MEDIAMTX_RTSP_PORT=18554}/{path}`; `path` = `mediamtx_path` hoặc `code`; nếu camera có `sub_stream2` ⇒ `{path}_detect` |
| `restream_urls` | `{MODULE: rtsp_url}` — **cùng một URL cho mọi module** |

Payload không chứa `timestamp`, `name`, `admin_area_*`, `ip_address`, `username/password`, `record_url`.

### 6.2 `smart_vms/cameras/{camera_code}/ai_zones[/{MODULE}]` — polygon (retained, QoS 1)

- **Trigger**: startup (`sync_zones_to_mqtt` từ `ai_zone` của link `enabled`), mọi CRUD zone/line, bật/tắt AI module của camera.
- Topic gộp `ai_zones` chứa mọi zone; topic `ai_zones/{MODULE}` chỉ chứa zone của module đó. Module bị tắt ⇒ publish `{"camera_code", "ai_zones": [], "camera_id"}` (và lines rỗng) lên mọi alias của module (vd tắt `PLATE` ⇒ xoá `PLATE`, `ITS`, `TRAFFIC`, `LPR`, `ANPR`, `PLATE_RECOGNITION`) ⇒ edge **dừng module**.
- Đồng thời publish `""` retained lên `.../zones` và `.../zones/lines` (xoá legacy).

**Payload mẫu**:

```json
{
  "camera_code": "zone1",
  "ai_zones": [
    {
      "id": "1c6243ef-551c-4b7b-8133-23a2207f0519",
      "code": "POLY_675900",
      "name": "POLY_675900",
      "zone_type": "MONITORED",
      "points": [{"x": 0.124186, "y": 0.254963}, {"x": 0.875116, "y": 0.277295}, {"x": 0.879304, "y": 0.833127}, {"x": 0.119998, "y": 0.840571}],
      "color": "#ef4444",
      "is_active": true,
      "ai_modules": "ZONE",
      "created_at": "2026-08-14T10:37:57.867316+07:00",
      "updated_at": "2026-08-14T10:37:57.867316+07:00"
    }
  ],
  "camera_id": "6aee1244-632d-43e3-8ef4-447ad539277a"
}
```

| Field | Ghi chú |
|---|---|
| `ai_zones[]` | polygon + line trong cùng mảng. `points` chuẩn hoá 0..1, đã bỏ điểm cuối nếu trùng điểm đầu |
| `ai_modules` | **string** (một module) |
| line crossing | zone có thêm `shape_type: "line_crossing"`, `line: {points: [p1, p2]}`, `direction_point: {x,y}`, `direction_vector: [dx, dy]` |
| `camera_id` | có khi backend biết |
| không có | `lines[]` tách riêng trong payload zone, `shape`, `timestamp` |

### 6.3 `smart_vms/cameras/{camera_code}/ai_zones[/{MODULE}]/lines` — line cho worker đếm IN/OUT (retained, QoS 1)

Publish cùng lúc với `ai_zones`, **kể cả `lines: []`**. Chỉ gồm zone `line_crossing` có đủ 2 điểm + `direction_point`.

```json
{
  "camera_code": "CAM_01",
  "lines": [
    {
      "id": "c2d0e675-c604-421e-8391-f7e855cae141",
      "code": "OUT",
      "name": "OUT",
      "line": { "points": [{"x": 0.013021, "y": 0.673611}, {"x": 0.945313, "y": 0.239583}] },
      "point": {"x": 0.464844, "y": 0.418981},
      "direction_vector": [-0.355846, -0.934545],
      "ai_modules": "PLATE",
      "updated_at": "2026-09-11T13:48:54.366687+07:00"
    }
  ],
  "total": 1,
  "camera_id": "1829efab-7205-41a5-bf76-93678fd4560e"
}
```

`point` = điểm chỉ hướng `IN` do người dùng đặt; `direction_vector` = vector đơn vị theo hướng đó.

### 6.4 `smart_vms/cameras/{preset_token}/{camera_code}/ai_zones` — polygon theo preset PTZ (retained)

Trigger: startup (`sync_preset_zones_to_mqtt` từ `ptz_preset_polygon`) + CRUD polygon preset. Đồng thời xoá `.../{preset}/{code}/zones`.

```json
{
  "camera_code": "ptz01",
  "preset_token": "1",
  "ai_zones": [
    { "id": "<uuid>", "code": "P1_Z1", "name": "P1_Z1", "preset_token": "1",
      "application_id": "<uuid|null>", "ai_module_id": "<uuid|null>",
      "points": [{"x": 0.1, "y": 0.2}, {"x": 0.5, "y": 0.2}, {"x": 0.5, "y": 0.6}],
      "color": "#ef4444", "config": {}, "is_active": true, "created_at": "…", "updated_at": "…" }
  ],
  "camera_id": "<uuid>"
}
```

### 6.5 Thermal — `smart_vms/thermal/sensors/company/{org}`, `smart_vms/thermal/monitor_points/company/{org}` (retained)

`{ "sensors": [{id, organization_id, admin_area_id, code, name, check_interval_minutes, status, is_on, ip, port, metadata, created_at, updated_at}], "total", "timestamp" }` và `{ "monitor_points": [{id, organization_id, device_id, sensor_id, sensor_code, camera_application_id, camera_id, code, name, phase, monitor_source_type, unit_raw, save_frame, map_position_config, threshold_config, is_active, ...}], "total", "timestamp" }`. Trigger: startup + request (§5.10.2).

### 6.6 Ghi hình — `frigate[_{node_code}]/{camera_code}/recordings/set` (không retain)

Payload **chuỗi thuần** `ON` / `OFF`. Prefix `frigate_{node_code}` khi camera gán Frigate của node (`camera_assignment` ACTIVE, `service_code='frigate'`), ngược lại `frigate`.

| Nguồn | Điều kiện |
|---|---|
| `recording_scheduler` (đầu mỗi phút, camera có `recording_config`) | `OFF` nếu `enabled=false` hoặc mode hiện tại `off`; ngược lại `ON`. **Chỉ publish khi trạng thái đổi** (signature) |
| API `PATCH https://aioc-stg.atin.vn/api/v1/cameras/{camera_code}/recording` body `{"enabled": bool}` | publish ngay, lưu cấu hình, sync Frigate nền; response `{camera_code, enabled, mqtt_published, node_code, topic, payload}` |

Mode theo lưới `schedule[day][hour]` (`0`=CN … `6`=T7): `always` / `motion` / `off`; lưới trống ⇒ `default_mode`; ô `null` khi lưới có lịch ⇒ `off`.

### 6.7 `smart_vms/recording_scheduler/state/{camera_code}` (retained) và `.../events`

```json
{ "camera_code": "auda2", "node_code": "kcnhungphu", "enabled": true, "mode": "motion",
  "source": "default", "runtime_payload": "ON", "timestamp": "2026-09-05T09:49:35.341183+07:00" }
```

`source` = `schedule` | `default`. Events (không retain):

```json
{ "type": "recording_config_saved", "camera_code": "auda2", "mode": "motion", "detection": "both",
  "retention_days": 5, "timestamp": "…", "sync_result": {} }
```
```json
{ "type": "scheduler_tick_sync", "camera_codes": ["auda2"], "timestamp": "…", "sync_result": [] }
```

`detection` ∈ `motion` / `objects` / `both`. Đổi cấu hình tĩnh (enabled, default_mode, retention_days, detection) ⇒ `sync_frigate()`; ON/OFF theo giờ **không** restart Frigate.

### 6.8 Lệnh thiết bị từ SOP

| Topic | Payload |
|---|---|
| `smart_vms/iot/{device_id}/command` · `smart_vms/barrier/{device_id}/command` (override bằng env `SOP_IOT_COMMAND_TOPIC` / `SOP_BARRIER_COMMAND_TOPIC`, có `{device_id}`) | `{"event": "SOP_DEVICE_COMMAND", "incident_key", "device_id", "device_code", "command": "OPEN", "hold_seconds", "trial", "camera_code", "location"}` |
| `kcn/speaker/device/{device_id}` · `kcn/speaker/broadcast/{zone}` | `{"event": "SOP_SPEAKER_ALERT", "incident_key", "zone", "device_id", "tts_text", "volume": 85, "repeat": 3, "siren_before": true, "timestamp"}` |

Kết quả ghi `alert_dispatch_log` (`sent` / `failed` — `mqtt_publish_failed`).

---

## 7. Lỗi / rủi ro đã biết

| # | Phát hiện | Vị trí |
|---|---|---|
| 1 | `getdevice/zone/{id}` dùng số cuối topic làm cả `zone_id` và `organization_id` ⇒ thường trả rỗng; `getdevice/company/+` không được subscribe | `mqtt_service._handle_getdevice_request`, `subscribe_camera_requests` |
| 2 | `NEW_ZONE_EVENT` phát 2 lần; ANOMALY tạo 2 notification/event (có thể kích SOP 2 lần) | virtual_fence + handler; anomaly service + handler |
| 3 | ANOMALY: kiểm tra module ở handler dùng sub-module thô (`INTRUSION` ⇒ nhóm ZONE, `SMOKE` ⇒ nhóm FIRE) trong khi service dùng code chuẩn; MQTT ép `severity=HIGH`, `entity_type=PERSON` | `handle_anomaly_event` |
| 4 | ZONE tự tạo `restricted_zones` với mọi `zone_id` lạ; camera không bắt buộc tồn tại | `virtual_fence/threads/create_event.py` |
| 5 | Backend không upload snapshot; base64 lưu thẳng | các `create_event` |
| 6 | Subscribe QoS 0 + clean session ⇒ mất event khi backend restart | `mqtt_service.py` |
| 7 | Broker không ACL, dùng chung một user; `rtsp_url` chứa user/pass MediaMTX | `mosquitto.conf`, `_build_cameras_payload` |
| 8 | Topic chứa camera code có dấu cách/Unicode | `_mqtt_topic_segment` |
| 9 | Có default MinIO access/secret key hardcode trong code | `config/settings.py`, `main.py` |

---

## 8. Kiểm thử nhanh

Theo quy tắc Docker-first, chạy script **trong container** backend (đã có `paho-mqtt`), broker trong mạng host là `127.0.0.1:18648`:

```bash
# Theo dõi log ingest
docker compose -f docker-compose.staging.yml logs -f backend | grep "\[MQTT\]"

# Xem retained topic camera / polygon
docker exec aioc-vms-staging-mqtt mosquitto_sub -h 127.0.0.1 -p 18648 -t 'smart_vms/cameras/company/+' --retained-only -v -W 3
docker exec aioc-vms-staging-mqtt mosquitto_sub -h 127.0.0.1 -p 18648 -t 'smart_vms/cameras/+/ai_zones/#' --retained-only -v -W 3

# Publish thử 1 sự kiện (tạo sự kiện thật!)
docker exec aioc-vms-staging-mqtt mosquitto_pub -h 127.0.0.1 -p 18648 -i test_ai_edge_01 -q 1 \
  -t 'smart_vms/ai_events/FIRE' \
  -m '{"ai_modules":"FIRE","camera_id":"<camera uuid có bật FIRE>","entity_type":"FIRE","payload":{"alert_level":"HIGH"}}'
```

Script mẫu trong `backend/scripts/` (chạy bằng `docker exec aioc-vms-staging-backend python scripts/<file> --help`): `send_anomaly_detail_events.py`, `send_crowd_detection_event.py`, `test_anomaly_payloads.py`, `test_water_level_event.py`, `mqtt_camera_test.py`, `mqtt_polygon_test.py`; payload mẫu `scripts/payloads/*.json`. Luôn dùng `--dry-run` nếu có, dùng `client_id` riêng (không bắt đầu bằng `vms_staging_backend`), và chọn camera **đã bật module** tương ứng — nếu không event sẽ bị bỏ qua im lặng.

---

## 9. Tài khoản thực tập sinh — `atin_tts` (zone 51)

### 9.1 Thông tin tài khoản

| Mục | Giá trị |
|---|---|
| Web VMS | `https://aioc-stg.atin.vn/` |
| Tài khoản | `atin_tts` |
| Mật khẩu | `tts@2026#` |
| Vai trò | `TTS_AI` — Thực tập sinh AI, phạm vi **chỉ zone 51**. Quyền như Zone Admin nhưng nhóm "Cấu hình & Thiết bị" chỉ có Quản lý camera, cộng thêm quyền xem các trang AI. Tự thêm camera vào zone 51 và tự bật/tắt module AI cho camera được |
| Tổ chức | `103` — KCN Hưng Phú |
| Site | `5` — KCN HƯNG PHÚ - IOC |
| Area | `76` — Khu thực tập AI (`khu-thuc-tap-ai`) |
| Zone | **`51`** — Zone thực tập sinh AI (`tts-ai`) |
| Camera ảo | `TTS_CAM_01` — `camera_id` = `4f0cc528-d215-4b3c-9727-1b68bacadacd`. Không có luồng RTSP, đã bật đủ 5 module ở §9.2 |
| Menu dịch vụ | Chỉ hiện 5 tính năng ở §9.2 |

### 9.2 Năm tính năng AI đã bật

| Tính năng | `ai_modules` = hậu tố topic | Topic publish | Payload chi tiết | Module camera phải bật |
|---|---|---|---|---|
| Biển số phương tiện | `PLATE` | `smart_vms/ai_events/PLATE` | §5.3 | `PLATE` |
| Nhận diện khuôn mặt | `FACE` | `smart_vms/ai_events/FACE` | §5.2 | `FACE` |
| Ẩu đả, đánh nhau | `FIGHT_DETECTION` | `smart_vms/ai_events/FIGHT_DETECTION` | §5.7, §9.4 | `FIGHT_DETECTION` |
| Giám sát mực nước | `WATER_LEVEL_DETECTION` | `smart_vms/ai_events/WATER_LEVEL_DETECTION` | §5.7, §9.4 | `WATER_LEVEL_DETECTION` hoặc `ANOMALY` |
| Lấn chiếm vỉa hè | `SIDEWALK_ENCROACHMENT` | `smart_vms/ai_events/SIDEWALK_ENCROACHMENT` | §5.7, §9.4 | `SIDEWALK_ENCROACHMENT` hoặc `ANOMALY` |

Camera ảo `TTS_CAM_01` đã bật đủ 5 module, dùng được ngay để gửi event. Camera thật thêm vào zone 51 sau này cũng phải bật các module ở cột cuối — tài khoản `atin_tts` tự bật được trong **Quản lý camera**.

Quy tắc bắt buộc:

1. Event chỉ được lưu khi camera trong payload (`camera_id` hoặc `camera_code`) đã được bật đúng module ở cột cuối (§1.2). Chưa bật ⇒ bỏ qua im lặng.
2. Luôn dùng đúng code ở cột `ai_modules`. Gửi `FIGHT`, `WATER_LEVEL`, `SIDEWALK` ở topic hoặc `ai_modules` là sai chuẩn.
3. Ba tính năng ẩu đả, mực nước, lấn chiếm vỉa hè thuộc nhóm ANOMALY: gửi thêm `submodule_code` bằng đúng code đầy đủ. Backend dùng `submodule_code` (thiếu thì dùng `event_type`) để kiểm tra module trên camera, nên thiếu `submodule_code` mà `event_type` là alias (vd `AU_DA`, `MUC_NUOC`) ⇒ event bị bỏ.

### 9.3 Lấy danh sách camera của zone 51

| Bước | Topic | Payload |
|---|---|---|
| 1. Subscribe kết quả (retained) | `smart_vms/cameras/zone/51` | — |
| 2. Publish request | `smart_vms/cameras/getdevice` | `{"zone_id": 51, "organization_id": 103}` |

Backend trả danh sách camera của zone 51 kèm `ai_modules` đang bật và `rtsp_url` / `restream_urls` (định dạng §6.1). Zone không có camera ⇒ không có message nào trên `smart_vms/cameras/zone/51`. Không dùng `smart_vms/cameras/getdevice/zone/51` (lỗi §7 mục 1).
### 9.4 Payload mẫu nhóm ANOMALY

| Tính năng | `submodule_code` | `payload.type` hợp lệ | `entity_type` nên gửi |
|---|---|---|---|
| Ẩu đả, đánh nhau | `FIGHT_DETECTION` | `FIGHT` | `PERSON` |
| Giám sát mực nước | `WATER_LEVEL_DETECTION` | `WATER_LEVEL`, `WATER_LEVEL_ALERT`, `FLOOD` | `WATER_LEVEL` |
| Lấn chiếm vỉa hè | `SIDEWALK_ENCROACHMENT` | tự do | `OBSTACLE` |

Qua MQTT, thiếu `entity_type` ⇒ backend ghi `PERSON`; thiếu `severity` ⇒ `HIGH`. `payload.type` ngoài danh sách ⇒ event bị bỏ.

**Ẩu đả, đánh nhau**

```json
{
  "ai_modules": "FIGHT_DETECTION",
  "submodule_code": "FIGHT_DETECTION",
  "camera_id": "<camera uuid trong zone 51>",
  "camera_code": "<camera code>",
  "event_time": "2026-10-26T10:00:00+07:00",
  "entity_type": "PERSON",
  "confidence": 0.91,
  "severity": "HIGH",
  "payload": { "type": "FIGHT", "person_count": 3, "zone_name": "Cổng chính" },
  "snapshot_url": "anomaly/2026-10-26/camera_<camera_id>/<uuid>.jpg"
}
```

**Giám sát mực nước**

```json
{
  "ai_modules": "WATER_LEVEL_DETECTION",
  "submodule_code": "WATER_LEVEL_DETECTION",
  "camera_id": "<camera uuid trong zone 51>",
  "camera_code": "<camera code>",
  "event_time": "2026-10-26T10:00:00+07:00",
  "entity_type": "WATER_LEVEL",
  "confidence": 0.87,
  "severity": "MEDIUM",
  "payload": { "type": "WATER_LEVEL_ALERT", "water_level": 45, "unit": "cm", "zone_name": "Cống thoát nước" },
  "snapshot_url": "anomaly/2026-10-26/camera_<camera_id>/<uuid>.jpg"
}
```

**Lấn chiếm vỉa hè**

```json
{
  "ai_modules": "SIDEWALK_ENCROACHMENT",
  "submodule_code": "SIDEWALK_ENCROACHMENT",
  "camera_id": "<camera uuid trong zone 51>",
  "camera_code": "<camera code>",
  "event_time": "2026-10-26T10:00:00+07:00",
  "entity_type": "OBSTACLE",
  "confidence": 0.84,
  "severity": "MEDIUM",
  "payload": { "type": "SIDEWALK_ENCROACHMENT", "zone_name": "Vỉa hè đường số 1" },
  "snapshot_url": "anomaly/2026-10-26/camera_<camera_id>/<uuid>.jpg"
}
```

`snapshot_url` là `object_key` nhận được khi upload ảnh lên Storage API (§4), với `category=anomaly`. Payload PLATE và FACE xem §5.3 và §5.2.

### 9.5 Gửi thử bằng camera ảo

Thay `camera_id` trong payload bằng `4f0cc528-d215-4b3c-9727-1b68bacadacd` và `camera_code` bằng `TTS_CAM_01`, ví dụ (kết nối như §0.1):

```python
import json, ssl
import paho.mqtt.client as mqtt

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="tts_test_01", transport="websockets")
client.ws_set_options(path="/mqtt")
client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
client.username_pw_set("atin", "Atin@2026#")
client.connect("aioc-stg.atin.vn", 443, keepalive=30)
client.loop_start()

event = {
    "ai_modules": "FIGHT_DETECTION",
    "submodule_code": "FIGHT_DETECTION",
    "camera_id": "4f0cc528-d215-4b3c-9727-1b68bacadacd",
    "camera_code": "TTS_CAM_01",
    "entity_type": "PERSON",
    "payload": {"type": "FIGHT"},
}
client.publish("smart_vms/ai_events/FIGHT_DETECTION", json.dumps(event), qos=1).wait_for_publish()
client.loop_stop()
client.disconnect()
```

Kết quả xem trên Web VMS bằng tài khoản `atin_tts`, mục tương ứng trong nhóm **Dịch vụ** (vd "Phát hiện đánh nhau" → Lịch sử).

### 9.6 Gửi bbox lên camera ảo

Topic `smart_vms/ai/bbox/TTS_CAM_01`, QoS 0, payload theo §5.8. Ví dụ vẽ khung mực nước (kết nối như §0.1):

```python
import json, ssl, time
import paho.mqtt.client as mqtt

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="tts_bbox_01", transport="websockets")
client.ws_set_options(path="/mqtt")
client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
client.username_pw_set("atin", "Atin@2026#")
client.connect("aioc-stg.atin.vn", 443, keepalive=30)
client.loop_start()

for _ in range(100):
    bbox = {
        "camera_code": "TTS_CAM_01",
        "camera_id": "4f0cc528-d215-4b3c-9727-1b68bacadacd",
        "ai_modules": "WATER_LEVEL_DETECTION",
        "timestamp": time.time(),
        "detections": [
            {"id": "w1", "class": "water", "confidence": 0.88, "bbox": [0.1, 0.45, 0.5, 0.92], "track_id": 1},
        ],
        "hud": {"text": "Muc nuoc: 45 cm", "display_ms": 3000, "color": "#22c55e"},
    }
    client.publish("smart_vms/ai/bbox/TTS_CAM_01", json.dumps(bbox), qos=0)
    time.sleep(0.2)

client.loop_stop()
client.disconnect()
```

Xem trên Web VMS: **Giám sát trực tiếp** → **Chọn Camera** → tick "Camera ảo thực tập sinh AI" → nút "AI: …" ở góc ô chọn đúng chức năng trùng `ai_modules` (ví dụ trên: Giám sát mực nước) → nút **Phát hiện AI** bật.

⚠️ Camera ảo không có luồng video nên ô luôn hiện "Đang kết nối luồng video…" và **che mất khung bbox**, dù dữ liệu bbox vẫn tới trình duyệt. Muốn nhìn thấy khung cần camera thật có luồng RTSP trong zone 51.

Đã kiểm thử trên staging với camera ảo: kết nối `wss://aioc-stg.atin.vn/mqtt` từ Internet (sai/thiếu mật khẩu bị từ chối, giữ kết nối ổn định với keepalive 30 s), `getdevice` zone 51 trả `TTS_CAM_01` kèm đủ 5 module, upload ảnh qua `https://aioc-stg.atin.vn/storage/upload/file`, publish đủ 5 event theo mẫu §5.2, §5.3, §9.4 ⇒ cả 5 được lưu với `zone_id` 51, ảnh xem được qua `/api/v1/snapshot/image`, sự kiện hiện trên Web VMS. Bbox theo §9.6 tới được trang Giám sát trực tiếp và được vẽ đúng vị trí (khi bỏ lớp "Đang kết nối luồng video…"); bbox gửi với module camera chưa bật bị lọc bỏ.

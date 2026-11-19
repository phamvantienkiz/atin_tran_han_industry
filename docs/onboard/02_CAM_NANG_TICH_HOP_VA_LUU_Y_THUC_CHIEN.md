# CẨM NANG TÍCH HỢP & 12 LƯU Ý "SỐNG CÒN" TRÊN PRODUCTION
## (ATIN Smart VMS — Lessons Learned, Gotchas & Troubleshooting)

> [!TIP]
> Tài liệu này tổng hợp toàn bộ những kinh nghiệm "xương máu" đúc kết từ thực tế đọc code Backend VMS và quá trình làm bài tập tích hợp `SIDEWALK_ENCROACHMENT`. Vì MQTT của hệ thống VMS là **fire-and-forget (Backend không trả lỗi về cho AI Edge)**, nếu vi phạm bất kỳ điểm nào trong 12 lưu ý dưới đây, bản tin của bạn sẽ **bị Backend bỏ qua im lặng (silent drop)** mà không báo lỗi.

---

## 1. Mười Hai (12) Lưu Ý "Sống Còn" Khi Tích Hợp AI Edge Vào VMS

### Lưu ý #1: Bẫy `client_id` của MQTT (Xung đột Backend hoặc tự đá văng nhau)
- **Cơ chế Backend:** Backend VMS chạy nhiều uvicorn worker, mỗi worker tạo kết nối MQTT với `client_id` có tiền tố `vms_staging_backend-pid{N}` (hoặc `vms_prod_backend...`).
- **Quy tắc bắt buộc:**
  1. **CẤM** đặt `client_id` bắt đầu bằng `vms_staging_backend` (hoặc prefix của backend).
  2. Mỗi tiến trình (process) AI Edge chạy song song phải có **`client_id` duy nhất** (ví dụ: `ai_edge_plate_cam01`, `ai_edge_sidewalk_node1`). Nếu 2 script hoặc 2 container dùng trùng `client_id`, Mosquitto Broker sẽ đá văng kết nối cũ ngay khi kết nối mới vào, gây ra vòng lặp **connect ➔ disconnect liên tục mỗi giây**.

---

### Lưu ý #2: Bẫy Topic `getdevice/zone/{id}` (Bug đã biết của Backend — Mục §5.10.1 & §7.1)
- **Hiện tượng:** Nếu bạn publish lên `smart_vms/cameras/getdevice/zone/51`, Backend lấy số `51` ở cuối topic gán cho **cả `zone_id = 51` lẫn `organization_id = 51`** $\longrightarrow$ Không khớp tổ chức nào $\longrightarrow$ Không trả về danh sách camera! Tương tự, `smart_vms/cameras/getdevice/company/{id}` **không được Backend subscribe**.
- **Cách làm ĐÚNG chuẩn Production:**
  1. Luôn subscribe trước các topic nhận kết quả (Retained, QoS 1):
     - `smart_vms/cameras/zone/+` (hoặc `smart_vms/cameras/zone/{zone_id}`)
     - `smart_vms/cameras/company/{organization_id}`
  2. Chỉ publish request vào **đúng topic gốc** `smart_vms/cameras/getdevice` kèm JSON body rõ ràng:
     ```json
     {"zone_id": 51, "organization_id": 103}
     ```
     hoặc lấy toàn bộ công ty:
     ```json
     {"organization_id": 103}
     ```

---

### Lưu ý #3: Một Camera có thể thuộc nhiều Zone/Org hoặc bật NHIỀU Module AI cùng lúc (Tránh trộn lẫn Polygon)
- **Bài học thực tế từ `cam_sidewalk`:**
  - Khi chạy Probe trên hệ thống, 1 camera như `cam_sidewalk` có thể đang bật đồng thời 2 module: `CROWD_DETECTION` (vùng `POLY_999076` bao trùm toàn bộ mặt đường lớn) và `SIDEWALK_ENCROACHMENT` (vùng `SIDEWALK` chỉ khoanh đúng phần vỉa hè).
  - Nếu AI Edge Worker đọc topic tổng `smart_vms/cameras/cam_sidewalk/ai_zones` mà **không lọc theo trường `ai_modules` của từng zone**, Worker sẽ lấy nhầm cả vùng lòng đường của `CROWD_DETECTION` để bắt lỗi lấn chiếm vỉa hè $\longrightarrow$ Báo giả (False Positive) liên tục khi xe chạy ngoài đường!
- **Cách xử lý chuẩn trong code:**
  - Luôn lọc mảng `ai_zones` theo đúng module mà Worker đang phụ trách:
    ```python
    filtered_zones = [
        z for z in data.get("ai_zones", [])
        if z.get("ai_modules", "").upper() == TARGET_AI_MODULE
    ]
    ```

---

### Lưu ý #4: Bẫy Wildcard `#` trên `ai_zones/#` làm ghi đè mất vùng vừa nhận
- **Hiện tượng thực tế đã gặp:**
  - Khi subscribe wildcard `smart_vms/cameras/{code}/ai_zones/#`, Mosquitto sẽ đẩy lần lượt tất cả các bản tin retained của mọi nhánh con, bao gồm:
    1. `.../ai_zones/SIDEWALK_ENCROACHMENT` (chứa 1 vùng vỉa hè hợp lệ).
    2. Ngay mili-giây sau: `.../ai_zones/CROWD_DETECTION/lines` hoặc `.../ai_zones/PLATE` (chứa mảng rỗng `[]`).
  - Nếu hàm `_handle_zones_update` không kiểm tra kỹ tên topic, bản tin rỗng của module khác đến sau sẽ **ghi đè xóa sạch vùng vỉa hè vừa lưu trong RAM** (`Hot-reload: Đã cập nhật 0 vùng`)!
- **Cách xử lý chuẩn trong code:**
  1. **Không dùng `#` bừa bãi.** Chỉ subscribe chính xác:
     - `smart_vms/cameras/+/ai_zones/{MY_MODULE}` (nếu xử lý polygon)
     - `smart_vms/cameras/+/ai_zones/{MY_MODULE}/lines` (chỉ khi bài toán cần vạch đếm IN/OUT).
  2. Trong `on_message`, nếu không làm bài toán line-crossing thì chặn ngay `if "/lines" in topic: return`, và kiểm tra hậu tố module trên topic có khớp với `MY_MODULE` hay không trước khi cập nhật cache.

---

### Lưu ý #5: Payload Retained Rỗng (`""` hoặc `ai_zones: []`) khi Xóa vùng / Tắt module
- **Cơ chế Backend (§1.2.5 & §6.2):** Khi người dùng tắt module trên Web VMS hoặc xóa vùng cũ, Backend publish chuỗi rỗng `b""` hoặc `{"ai_zones": []}` có cờ `retain=True` để dọn dẹp.
- **Cách xử lý chuẩn:**
  - Luôn kiểm tra `if not raw_payload_str:` trước khi gọi `json.loads(raw_payload_str)` để không bao giờ bị văng `JSONDecodeError` làm chết luồng MQTT.
  - Khi nhận mảng `ai_zones: []` trên đúng topic của module mình, cập nhật danh sách vùng của camera đó về `[]` một cách êm ái.

---

### Lưu ý #6: Bẫy Đặt tên Mã Module (`ai_modules`, `submodule_code`, `payload.type`) khiến Sự kiện bị Drop
- **Cơ chế Backend (§2.2 & §5.7):**
  - Nếu publish lên `smart_vms/ai_events/FIGHT` hoặc `.../CROWD` hoặc `.../SIDEWALK` (tên viết tắt) $\longrightarrow$ Rơi vào `handle_ai_event` (**chỉ in log, KHÔNG lưu vào Database**).
  - Với toàn bộ nhóm **ANOMALY** (`CROWD_DETECTION`, `FIGHT_DETECTION`, `FALL_DETECTION`, `INTRUSION_DETECTION`, `SMOKING_DETECTION`, `WEAPON_DETECTION`, `DANGER_ZONE_HAND_INTRUSION`, `SUICIDE_ATTEMPT`, `WATER_LEVEL_DETECTION`, `LITTERING_DETECTION`, `SIDEWALK_ENCROACHMENT`):
    1. **Topic publish:** `smart_vms/ai_events/<CODE_ĐẦY_ĐỦ>`
    2. **Root field bắt buộc:** Phải có **cả 2 trường** `"ai_modules": "<CODE_ĐẦY_ĐỦ>"` **VÀ** `"submodule_code": "<CODE_ĐẦY_ĐỦ>"`.
    3. **Trường `payload.type`:** Phải nằm trong danh sách hợp lệ của từng sub-module (xem bảng dưới). Nếu truyền sai hoặc truyền alias tiếng Việt (`AU_DA`, `MUC_NUOC`, `LEO_TREO`) $\longrightarrow$ Backend trả lỗi 400 nội bộ và **bỏ qua sự kiện**.

#### Bảng Tra cứu Nhanh `ai_modules` — `category` — `payload.type` Hợp lệ:

| Bài toán AI | Topic `smart_vms/ai_events/...` & `ai_modules` | `submodule_code` | `category` (Upload ảnh) | `entity_type` chuẩn | `payload.type` / Trường bắt buộc trong `payload` |
| :--- | :--- | :--- | :---: | :---: | :--- |
| **Nhận diện khuôn mặt** | `FACE` | *(không cần)* | `face` | `PERSON` | Đặt `user_code`, `user_name`, `direction` (`IN`/`OUT`), `score_match` ở root + `payload.person` |
| **Biển số xe / Vi phạm GT** | `PLATE` | *(không cần)* | `plate` | `VEHICLE` | **Bắt buộc lồng:** `payload.vehicle.license_plate.text` (gửi ở root sẽ bị phớt lờ!). Nếu vi phạm GT: thêm `payload.violation_type_code` |
| **Vùng cấm / Hàng rào ảo** | `ZONE` | *(không cần)* | `zone` | `PERSON` / `VEHICLE` | **Bắt buộc:** `payload.zone_id` (UUID hoặc code), `payload.direction` (`IN`/`OUT`), `count` |
| **Cảnh báo cháy khói** | `FIRE` | *(không cần)* | `fire` | `FIRE` / `SMOKE` | `payload.alert_level`: `"HIGH"` \| `"MEDIUM"` \| `"LOW"` |
| **Đếm lưu lượng người** | `FOOTFALL` *(Cam bật `CUSTOMER`/`RETAIL_FOOTFALL`)* | *(không cần)* | `footfall` | `PERSON` | `payload: {"zone_id", "zone_name", "direction": "IN", "count": {"in": X, "out": Y}}` |
| **Phát hiện đám đông** | `CROWD_DETECTION` | `CROWD_DETECTION` | `anomaly` | `PERSON` | `payload.type`: `"HIGH_DENSITY"` hoặc `"CROWD_DETECTION"`, kèm `"person_count"`, `"threshold"` |
| **Phát hiện đánh nhau** | `FIGHT_DETECTION` | `FIGHT_DETECTION` | `anomaly` | `PERSON` | `payload.type`: **`"FIGHT"`** (duy nhất) |
| **Phát hiện té ngã** | `FALL_DETECTION` | `FALL_DETECTION` | `anomaly` | `PERSON` | `payload.type`: **`"FALL"`** (duy nhất) |
| **Leo trèo / Xâm nhập** | `INTRUSION_DETECTION` | `INTRUSION_DETECTION` | `anomaly` | `PERSON` | `payload.type`: **`"INTRUSION"`** (duy nhất) |
| **Phát hiện hút thuốc** | `SMOKING_DETECTION` | `SMOKING_DETECTION` | `anomaly` | `PERSON` | `payload.type`: **`"SMOKING"`** (duy nhất) |
| **Phát hiện vũ khí** | `WEAPON_DETECTION` | `WEAPON_DETECTION` | `anomaly` | `PERSON` | `payload.type`: **`"WEAPON"`** (duy nhất) |
| **Tay vào vùng nguy hiểm** | `DANGER_ZONE_HAND_INTRUSION` | `DANGER_ZONE_HAND_INTRUSION` | `anomaly` | `PERSON` | `payload.type`: **`"DANGER_ZONE_HAND_INTRUSION"`** |
| **Giám sát mực nước** | `WATER_LEVEL_DETECTION` | `WATER_LEVEL_DETECTION` | `anomaly` | `WATER_LEVEL` | `payload.type`: `"WATER_LEVEL_ALERT"` \| `"WATER_LEVEL"` \| `"FLOOD"`, kèm `"water_level"`, `"unit": "cm"` |
| **Vứt rác bừa bãi** | `LITTERING_DETECTION` | `LITTERING_DETECTION` | `anomaly` | `PERSON` | `payload.type`: `"LITTERING_DETECTION"` (tự do) |
| **Lấn chiếm vỉa hè** | `SIDEWALK_ENCROACHMENT` | `SIDEWALK_ENCROACHMENT` | `anomaly` | `OBSTACLE` | `payload.type`: `"SIDEWALK_ENCROACHMENT"` (tự do), kèm `"zone_id"`, `"zone_name"`, `"count"` |

---

### Lưu ý #7: Độ trễ Cache 1 Phút khi Bật Module trên Giao diện Web VMS (§1.2.1)
- **Cơ chế Backend:** Khi bạn vừa vào trang **Quản lý camera** trên Web VMS để tích chọn bật một module AI mới cho camera, Backend có thể mất **tối đa 60 giây** để đồng bộ cache phân quyền module.
- **Lưu ý:** Nếu gửi sự kiện ngay lập tức sau khi vừa bấm nút bật (chưa qua 1 phút), sự kiện có thể bị bỏ qua im lặng.

---

### Lưu ý #8: Bẫy Upload Ảnh Snapshot (`object_key` vs `url` `127.0.0.1`)
- **Cơ chế Storage API (§4.2):** Khi gọi `POST https://<DOMAIN>/storage/upload/file`, JSON trả về có 2 trường:
  ```json
  {
    "object_key": "anomaly/2026-11-11/camera_2e994218.../34289b2d....jpg",
    "url": "http://127.0.0.1:18646/vms-captures/anomaly/...?AWSAccessKeyId=..."
  }
  ```
- **Quy tắc bắt buộc:**
  1. **LUÔN LẤY `object_key`** gán vào trường `"snapshot_url"` của bản tin MQTT.
  2. **TUYỆT ĐỐI KHÔNG LẤY trường `"url"`** (vì nó trỏ về `127.0.0.1:18646` nội bộ của container MinIO và tự hết hạn sau 24h, trình duyệt người dùng không thể mở được).
  3. **KHÔNG gửi `snapshot_base64`** qua MQTT vì làm nghẽn cổ chai Mosquitto Broker.
  4. Nén ảnh JPEG trực tiếp trong RAM (`cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])`) thay vì ghi ra ổ cứng rồi đọc lại — giúp giảm latency upload xuống chỉ còn `~180ms`.

---

### Lưu ý #9: Quy tắc "0.35 Giây" và 3 Điều kiện để Hiện Khung BBox Realtime trên Web VMS (§5.8)
- **Tại sao gửi BBox rồi mà trên Web VMS không thấy khung?**
  Để khung chữ nhật hiện lên màn hình **Giám sát trực tiếp (`/monitoring`)**, bắt buộc phải hội tụ đủ **4 yếu tố**:
  1. **Tần số gửi (5–10 FPS):** Giao diện Web VMS tự động xóa (fade-out) khung BBox sau **`0.35 giây`** nếu không nhận được gói tin mới. Vì vậy Edge Worker phải publish đều đặn mỗi **`0.1s – 0.2s`** (QoS 0, Retain = False).
  2. **Bật nút "Phát hiện AI":** Trên thanh điều khiển của ô video camera đang mở, nút **Phát hiện AI** phải đang sáng (BẬT).
  3. **Chọn đúng Module ở góc ô video:** Nút dropdown **"AI: ..."** ở góc ô video phải đang chọn **đúng tên chức năng AI** trùng khớp với trường `"ai_modules"` trong bản tin BBox của bạn.
  4. **Camera phải có luồng Video thật đang phát:** Nếu là camera ảo không có RTSP (như `TTS_CAM_01`), lớp màn hình chờ *"Đang kết nối luồng video..."* sẽ đè lên che khuất canvas vẽ BBox.

---

### Lưu ý #10: Xử lý Luồng RTSP qua MediaMTX (`18554`) & Chống Trễ Hình (Buffer Lag)
- **Kinh nghiệm thực tế:**
  1. Luồng RTSP gốc của camera nội bộ (như `192.168.1.198:28537`) thường không mở trực tiếp cho máy trạm bên ngoài, mà được gom về **MediaMTX Server ở cổng `18554`** (trường `rtsp_url` trong payload camera của MQTT, ví dụ `rtsp://admin:prometheus123@192.168.1.250:18554/c112_cam_sidewalk`). Luôn ưu tiên lấy `rtsp_url` từ MQTT.
  2. Khi dùng OpenCV đọc RTSP, bắt buộc thiết lập:
     ```python
     os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"
     cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
     cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
     ```
     Nếu không ép `tcp` và `BUFFERSIZE = 1`, ảnh sẽ bị vỡ hình (UDP packet loss) hoặc bị trễ 5–10 giây so với thời gian thực.

---

### Lưu ý #11: Chống Spam Sự Kiện (Dwell-Time + Cooldown) & Lưu ý Double Notification của Backend
- **Ở phía Backend (§5.4 & §5.7):** Với sự kiện `ZONE` và `ANOMALY`, Backend **KHÔNG có bộ lọc chống trùng lặp (no dedup)** và mỗi sự kiện `ANOMALY` sẽ sinh ra 2 bản ghi notification để phục vụ chuông báo + SOP.
- **Trách nhiệm của AI Edge Worker (`C08`):**
  Nếu bạn bắn sự kiện ở mỗi frame phát hiện vi phạm (5 lần/giây), trong 1 phút bạn sẽ làm ngập Database với 300 sự kiện trùng nhau và làm treo SOP Engine (bắn hàng trăm tin nhắn Telegram / kêu loa IP liên tục)!
- **Giải pháp bắt buộc trong Worker:**
  - **Dwell-time (`CONFIRM_SECONDS = 2.0s`):** Đối tượng phải nằm trong vùng vi phạm liên tục ít nhất `2.0 giây` mới xác nhận là sự việc thật (loại bỏ nhiễu do người/xe lướt nhanh qua mép vùng).
  - **Cooldown (`EVENT_COOLDOWN_SECONDS = 60s`):** Sau khi đã bắn 1 sự kiện cho vùng `zone_id`, khóa không bắn sự kiện mới cho vùng đó trong `60 giây` tiếp theo.

---

### Lưu ý #12: Ký tự Đặc biệt / Tiếng Việt có dấu trong `camera_code` (§1.2.7)
- **Cơ chế Backend:** Khi Backend tạo topic `smart_vms/cameras/{camera_code}/ai_zones`, Backend giữ nguyên dấu cách và chữ Unicode tiếng Việt (ví dụ: `smart_vms/cameras/cổng 03/ai_zones`), chỉ thay `/`, `#`, `+` bằng `_`.
- **Cách xử lý chuẩn:** Khi subscribe, luôn ưu tiên dùng wildcard `+` ở vị trí `{camera_code}` (ví dụ: `smart_vms/cameras/+/ai_zones/SIDEWALK_ENCROACHMENT`) và đọc trường `data["camera_code"]` bên trong JSON payload.

---

## 2. Bảng Cấp Cứu Nhanh Khi Gặp Lỗi (Quick Troubleshooting Matrix)

| Triệu chứng gặp phải | Nguyên nhân khả dĩ nhất | Cách kiểm tra & Xử lý dứt điểm |
| :--- | :--- | :--- |
| **Log báo `Connected with result code 0` rồi ngay lập tức `Disconnected` lặp đi lặp lại** | Trùng `MQTT_CLIENT_ID` với một tiến trình/container khác đang chạy. | Đổi `MQTT_CLIENT_ID` trong `.env` sang chuỗi mới (thêm hậu tố tên máy hoặc số ngẫu nhiên). |
| **Gửi `getdevice` nhưng không nhận được camera nào** | Dùng nhầm topic `getdevice/zone/{id}` hoặc camera nằm ở `organization_id` / `zone_id` khác. | Subscribe `smart_vms/cameras/company/+` và `smart_vms/cameras/zone/+` để quét toàn bộ bản tin retained trên Broker (xem script Probe ở File `03`). |
| **Publish Event báo `rc=0` nhưng mở Web VMS không thấy sự kiện trong Lịch sử** | 1) Camera chưa bật module AI tương ứng trên Web VMS.<br>2) Sai `camera_id` (phải là UUID, không phải `camera_code`).<br>3) Sai tên `ai_modules` / thiếu `submodule_code` / sai `payload.type`.<br>4) Sai định dạng `event_time`. | 1) Kiểm tra trên Web VMS xem camera đã tích bật module chưa (chờ 60s).<br>2) Đối chiếu bảng ở **Lưu ý #6**.<br>3) Đảm bảo `event_time` là `datetime.now( timezone(timedelta(hours=7)) ).isoformat(timespec="seconds")`. |
| **Sự kiện hiện trên Web VMS nhưng ảnh Snapshot bị lỗi không xem được** | Gán nhầm trường `url` (`http://127.0.0.1...`) hoặc đường dẫn file local vào `snapshot_url`. | Phải gán chính xác chuỗi `object_key` trả về từ API `/storage/upload/file`. Thử mở `https://<DOMAIN>/api/v1/snapshot/image?object_key=<object_key>` trên trình duyệt để kiểm tra. |
| **Chạy trong Thread phụ báo lỗi `ValueError: signal only works in main thread`** | Gọi `signal.signal(SIGINT, ...)` khi khởi chạy Orchestrator từ một thread không phải main thread. | Bọc lệnh đăng ký signal trong điều kiện: `if threading.current_thread() is threading.main_thread():`. |
| **Luồng RTSP trả về lỗi `404 Not Found` hoặc `Connection timed out`** | Máy trạm chưa bật VPN nội bộ công ty, hoặc nguồn phát video gốc vào MediaMTX đang tạm tắt. | 1) Kiểm tra VPN (`ipconfig` / `ping 192.168.1.250`).<br>2) Kiểm tra lại `rtsp_url` mới nhất trong bản tin MQTT `smart_vms/cameras/...`. |

# TỔNG HỢP SỔ TAY KỸ THUẬT AI EDGE TÍCH HỢP HỆ THỐNG VMS ATIN
## (ATIN AIOC / Smart VMS — Production Hand-off & Quick Reference)

> [!IMPORTANT]
> **MỤC ĐÍCH CỦA THƯ MỤC `docs/summary/` NÀY:**
> Đây là **bộ sổ tay tổng hợp thực chiến (Portable Knowledge Base)** đúc kết từ toàn bộ tài liệu hợp đồng kỹ thuật (`AI_MODULES_MQTT.md`), thiết kế kiến trúc pipeline và kinh nghiệm thực tế khi triển khai tích hợp AI Edge Worker tại ATIN.
> Bạn có thể **mang nguyên thư mục `docs/summary/` này sang môi trường làm việc thực tế (Production)** để tra cứu nhanh kiến trúc, mã module, cấu trúc JSON payload, những "cạm bẫy" (gotchas) của Backend VMS và các đoạn code chuẩn (boilerplate) để thực hiện bất kỳ task tích hợp module AI mới nào được giao.

---

## 1. Danh mục Tài liệu trong Thư mục `summary/`

| STT | Tên File | Nội dung & Khi nào cần đọc |
| :-: | :--- | :--- |
| **00** | [`00_README_TONG_QUAN_VA_CHUYEN_DOI_PROD.md`](./00_README_TONG_QUAN_VA_CHUYEN_DOI_PROD.md) | **(File hiện tại)** Bản đồ tra cứu nhanh, kiến trúc hệ thống end-to-end, và **Bảng đối chiếu chuyển đổi từ Staging (Onboard) sang Production**. |
| **01** | [`01_AI_MODULES_MQTT_CONTRACT_REF.md`](./01_AI_MODULES_MQTT_CONTRACT_REF.md) | **Bản gốc đầy đủ `AI_MODULES_MQTT.md`** có đóng khung đánh dấu rõ đâu là **thông số riêng của Server Onboard/Staging** và đâu là **quy chuẩn giữ nguyên 100% trên Production**. |
| **02** | [`02_CAM_NANG_TICH_HOP_VA_LUU_Y_THUC_CHIEN.md`](./02_CAM_NANG_TICH_HOP_VA_LUU_Y_THUC_CHIEN.md) | **Cẩm nang thực chiến & 12 Lưu ý "Sống Còn" (Gotchas):** Cách tránh bị Backend drop bản tin im lặng, lỗi `getdevice`, cách lọc đa vùng khi 1 camera bật nhiều module, quy tắc BBox `0.35s`, Storage API và Anti-spam. |
| **03** | [`03_MAU_CODE_BOILERPLATE_VA_QUY_TRINH_TASK_MOI.md`](./03_MAU_CODE_BOILERPLATE_VA_QUY_TRINH_TASK_MOI.md) | **Quy trình 4 bước khi nhận Task AI mới tại công ty** + Bộ khung code Python chuẩn (`.env`, `config`, `storage_client`, `detector`, `worker`, `main` orchestrator, `Dockerfile`) chỉ cần thay tên Module & logic AI là chạy ngay. |

---

## 2. Kiến trúc Tổng thể Hệ thống AIOC / Smart VMS (Giống nhau 100% giữa Staging & Production)

Khi làm việc tại ATIN, **bạn KHÔNG phải viết lại Backend VMS, Database, WebSocket hay Media Server**. Toàn bộ hạ tầng phía Server đã chạy sẵn theo kiến trúc cố định dưới đây. Nhiệm vụ của kỹ sư AI là xây dựng và vận hành khối **AI Edge Worker** (bên trái sơ đồ) giao tiếp với hệ thống qua **3 kênh chuẩn**: **RTSP (18554)**, **Storage HTTP API (443)** và **MQTT over WebSocket TLS (443)**.

```mermaid
flowchart LR
    subgraph Edge ["1. AI EDGE WORKER (Phần việc của Kỹ sư AI)"]
        direction TB
        ORCH["MQTT Orchestrator\n- Sub danh sách Camera & Zone\n- Hot-reload Polygon (0..1)\n- Tự Bật/Tắt Worker theo Module"]
        RTSP_IN["RTSP Stream Reader\n- Đọc MediaMTX (18554)\n- Bufferless (CAP_PROP_BUFFERSIZE=1)\n- Tự reconnect khi rớt mạng"]
        AI_CORE["AI Inference & Rule Engine\n- Model Detection thật (YOLO/v.v.)\n- Point-in-Polygon / Line Crossing\n- Dwell-time (xác nhận) + Cooldown"]
        SNAP_UP["Storage Uploader\n- Nén JPEG trên RAM\n- POST /storage/upload/file\n- Nhận về object_key"]

        ORCH --> RTSP_IN --> AI_CORE
        AI_CORE --> SNAP_UP
    end

    subgraph VMS ["2. HỆ THỐNG SMART VMS SERVER (Giữ nguyên kiến trúc ở cả STG & PROD)"]
        direction TB
        MTX["MediaMTX Server\nPort 18554\n(Restream từ Camera gốc)"]
        MOSQ["Mosquitto MQTT Broker\nwss://<DOMAIN>/mqtt : 443\n(WebSocket + TLS)"]
        MINIO["Storage API (MinIO)\nhttps://<DOMAIN>/storage/upload/file\n(Bucket: vms-captures)"]
        LEADER["VMS Backend Leader\nGiữ /tmp/smart_vms_mqtt_leader.lock\n(Định tuyến Handler -> Lưu PostgreSQL)"]
        WEB["Web VMS UI & SOP Engine\nhttps://<DOMAIN>/monitoring\n(WebSocket BBox, Cảnh báo, Loa IP, Barrier)"]

        MOSQ <--> LEADER
        LEADER --> WEB
        MINIO -. "GET /api/v1/snapshot/image" .-> WEB
    end

    MTX == "1. Luồng Video RTSP" ==> RTSP_IN
    ORCH <== "2. Đồng bộ Camera & ai_zones\n(QoS 1, Retained)" ==> MOSQ
    AI_CORE == "3. BBox Realtime (5-10 FPS, QoS 0)\nsmart_vms/ai/bbox/{camera_code}" ==> MOSQ
    SNAP_UP == "4a. Upload ảnh (.jpg)\ncategory = face|plate|zone|fire|footfall|anomaly" ==> MINIO
    SNAP_UP == "4b. Publish Event kèm object_key (QoS 1)\nsmart_vms/ai_events/{MODULE}" ==> MOSQ
```

---

## 3. Bảng Chuyển đổi Nhanh: Từ Môi trường Onboard (Staging) ➔ Môi trường Production

Kiến trúc topic MQTT, cấu trúc JSON payload, cơ chế leader lock và cách hoạt động của Backend trên **Production giống hệt 100% với Staging (`aioc-stg.atin.vn`)**. Khi chuyển sang dự án thực tế (Production hoặc các Site/Khu công nghiệp của khách hàng), bạn **chỉ cần thay đổi các biến môi trường trong file `.env`** theo bảng đối chiếu sau:

| Thành phần cấu hình | Giá trị dùng khi Onboard (`STAGING`) | Khi chuyển sang `PRODUCTION` (Thực tế) | Lưu ý quan trọng |
| :--- | :--- | :--- | :--- |
| **Domain Hệ thống (`<DOMAIN>`)** | `aioc-stg.atin.vn` | Domain Production của công ty / dự án (VD: `aioc.atin.vn` hoặc domain riêng của KCN/Đô thị) | Chỉ đổi domain gốc, **giữ nguyên toàn bộ đường dẫn (path) phía sau**. |
| **Web VMS UI** | `https://aioc-stg.atin.vn/` (`.../monitoring`) | `https://<PROD_DOMAIN>/` (`.../monitoring`) | Giao diện bật/tắt module AI, vẽ vùng polygon (`ai_zones`) và xem lịch sử sự kiện giống hệt. |
| **MQTT Broker URL** | `wss://aioc-stg.atin.vn/mqtt` (Port `443`, TLS) | `wss://<PROD_DOMAIN>/mqtt` (Port `443`, TLS) | Nếu chạy container cùng mạng host nội bộ với server VMS có thể dùng TCP nội bộ (VD: `127.0.0.1:18648`), nếu chạy từ máy chủ AI rời qua mạng thì luôn dùng `wss://<PROD_DOMAIN>/mqtt` cổng `443`. |
| **Tài khoản MQTT (`MQTT_USER`/`PASS`)** | `atin` / `Atin@2026#` *(Server Onboard/STG)* | Nhận từ Quản trị hệ thống / DevOps dự án (Cấu hình trong `.env`) | **Tuyệt đối không commit file `.env` chứa mật khẩu lên Git.** |
| **`MQTT_CLIENT_ID`** | `tts_<ten>_01` (VD: `tts_sidewalk_01`) | `<ten_service_module>_<node>_01` (VD: `ai_edge_sidewalk_node01`) | **CẤM** đặt `client_id` bắt đầu bằng `vms_staging_backend` hoặc `vms_prod_backend` / `{MQTT_CLIENT_ID}-pid` của Backend. Mỗi process phải có `client_id` **duy nhất** (trùng sẽ văng kết nối liên tục). |
| **Storage API (Upload ảnh)** | `https://aioc-stg.atin.vn/storage/upload/file` | `https://<PROD_DOMAIN>/storage/upload/file` | Giữ nguyên method `POST multipart/form-data` với 3 trường: `file`, `camera_id`, `category`. Lấy `object_key` gán vào `snapshot_url`. |
| **URL kiểm tra ảnh Snapshot** | `https://aioc-stg.atin.vn/api/v1/snapshot/image?object_key=<key>` | `https://<PROD_DOMAIN>/api/v1/snapshot/image?object_key=<key>` | Dùng để test nhanh trên trình duyệt xem ảnh upload đã đọc được chưa. |
| **Phạm vi Tổ chức & Khu vực (`ORGANIZATION_ID`, `ZONE_ID`)** | Onboard: `organization_id = 103` (hoặc `112`), `zone_id = 51` (hoặc `283`) | Theo `organization_id` (Công ty/KCN) và `zone_id` của dự án được giao | Có thể subscribe `smart_vms/cameras/company/{organization_id}` để tự động lấy toàn bộ camera của tổ chức đó mà không cần biết trước từng `zone_id`. |
| **Luồng RTSP Camera** | `rtsp://admin:prometheus123@192.168.1.250:18554/c112_cam_sidewalk` (hoặc `192.168.1.198:28537/dungtest`) | Tự động đọc từ trường `rtsp_url` hoặc `restream_urls[MODULE]` trong bản tin MQTT `smart_vms/cameras/...` | Trên Production, MediaMTX (cổng `18554`) restream toàn bộ camera. Worker nên ưu tiên lấy động `rtsp_url` từ MQTT thay vì hardcode IP camera. |
| **Camera ảo Test (`TTS_CAM_01`)** | `4f0cc528-d215-4b3c-9727-1b68bacadacd` *(Chỉ có ở Zone 51 Staging)* | Trên Prod: Dùng `camera_id` (UUID) thật lấy từ bản tin MQTT `smart_vms/cameras/company/{org}` | Luôn chạy script Probe (`step1_probe_mqtt_rtsp.py`) trong 5 giây đầu để lấy danh sách UUID camera thật trên môi trường mới. |

---

## 4. Tóm tắt 9 Tiêu chuẩn Kỹ thuật Bắt buộc (`C01` – `C09`) cho Mọi Module AI tại ATIN

Khi triển khai bất kỳ bài toán AI nào (Nhận diện khuôn mặt `FACE`, Biển số `PLATE`, Vùng cấm `ZONE`, Cháy khói `FIRE`, Đếm người `FOOTFALL`, hay các bài toán Hành vi bất thường `ANOMALY` như Đám đông, Đánh nhau, Lấn chiếm vỉa hè, Mực nước, Ngã, Leo trèo...), code của bạn đều phải thỏa mãn 9 tiêu chí cốt lõi sau:

1. **C01 — Kết nối MQTT bền vững:** Dùng WebSocket TLS (`wss://.../mqtt`, port `443`, `keepalive=30`), `client_id` riêng biệt, tự động reconnect (`reconnect_delay_set`) và **đăng ký lại (re-subscribe) toàn bộ topic trong hàm `on_connect`**.
2. **C02 — Quản lý vòng đời Camera động:** Lắng nghe `smart_vms/cameras/zone/{id}` hoặc `company/{org}` (retained) + gửi request `smart_vms/cameras/getdevice` (với JSON `{"organization_id": ...}`). Chỉ khởi chạy Worker cho camera có tên module của mình trong mảng `ai_modules`. **Khi người dùng tắt module trên Web VMS ➔ Phải dừng (stop) luồng đọc RTSP của camera đó ngay lập tức.**
3. **C03 — Hot-reload Vùng/Vạch (`ai_zones`) trong RAM:** Lắng nghe `smart_vms/cameras/{code}/ai_zones/{MODULE}` (và `/lines` nếu đếm qua vạch). Khi người dùng vẽ lại vùng trên Web VMS, cập nhật tọa độ đa giác (`0..1`) trực tiếp vào bộ nhớ Worker (qua `threading.Lock`) mà **không cần khởi động lại service**. Phải xử lý an toàn không crash khi nhận payload rỗng `""` hoặc `{"ai_zones": []}`.
4. **C04 — Đọc RTSP độ trễ thấp & Tự phục hồi:** Đọc luồng RTSP qua TCP (`rtsp_transport;tcp`), tắt bộ đệm (`CAP_PROP_BUFFERSIZE = 1`) để luôn lấy frame mới nhất. Tự động kết nối lại khi luồng RTSP bị gián đoạn.
5. **C05 — Upload ảnh qua Storage API (Không gửi Base64):** Nén ảnh sự kiện sang JPEG (`.jpg` < 10MB) ngay trong RAM, gọi `POST /storage/upload/file` kèm `camera_id` và `category` tương ứng (`face`, `plate`, `zone`, `fire`, `footfall`, `anomaly`). Lấy trường **`object_key`** trong JSON trả về để gán vào `snapshot_url` (tuyệt đối không dùng trường `url` `127.0.0.1` và không nhúng `snapshot_base64` vào MQTT).
6. **C06 — Publish Sự kiện đúng Topic & Schema:** Gửi bản tin QoS 1 (không retain) lên `smart_vms/ai_events/{MODULE}`. Trường `event_time` phải là chuỗi ISO-8601 có múi giờ Việt Nam `+07:00` (VD: `2026-11-11T15:30:00+07:00`). Với nhóm `ANOMALY`, bắt buộc có đủ cả `ai_modules`, `submodule_code` (mã đầy đủ) và `payload.type` hợp lệ.
7. **C07 — Publish BBox Realtime (5–10 FPS):** Gửi bản tin QoS 0 (không retain) lên `smart_vms/ai/bbox/{camera_code}` định kỳ mỗi **`0.1s – 0.2s`** (vì giao diện Web VMS tự xóa khung sau **`0.35s`**). Tọa độ `bbox: [x1, y1, x2, y2]` chuẩn hóa `0..1`, trường `ai_modules` phải khớp với module đang chọn trên ô xem trực tiếp của Web VMS.
8. **C08 — Chống Spam Sự kiện (Dwell-time & Cooldown):** Áp dụng State Machine theo từng vùng/đối tượng: chỉ xác nhận vi phạm khi đối tượng tồn tại liên tục qua ngưỡng thời gian (`CONFIRM_SECONDS`, VD `2.0s`) và khóa không gửi lặp lại sự kiện cho cùng một sự việc trong thời gian chờ (`EVENT_COOLDOWN_SECONDS`, VD `60s`).
9. **C09 — Chỉ dùng Detection thật:** Chỉ sinh sự kiện và vẽ BBox từ kết quả suy luận thực tế của model AI trên frame hiện tại, không dùng hộp dự đoán/nội suy từ bộ lọc Kalman của tracker khi đối tượng đã khuất.

---

## 5. Quy tắc Môi trường Làm việc trên Máy trạm / Server (Từ `AGENTS.md`)

- **Cô lập môi trường Python tuyệt đối (`.venv` / `uv`):** Khi phát triển và kiểm thử trên máy cá nhân hoặc server trực tiếp, luôn tạo và sử dụng môi trường ảo `.venv` nội bộ (`.\.venv\Scripts\python.exe` trên Windows hoặc `./.venv/bin/python` trên Linux). Tuyệt đối không chạy `pip install` toàn cục làm ảnh hưởng hệ thống.
- **Đóng gói Docker khi bàn giao Production:** Sử dụng `Dockerfile` và file `.env` tách biệt (xem mẫu chi tiết trong [`03_MAU_CODE_BOILERPLATE_VA_QUY_TRINH_TASK_MOI.md`](./03_MAU_CODE_BOILERPLATE_VA_QUY_TRINH_TASK_MOI.md)).
- **Ghi Log minh bạch:** Mọi lần publish sự kiện lên MQTT đều phải ghi log chuẩn gồm: `timestamp`, `topic`, `camera_code` (`camera_id`), `object_key`, và mã kết quả `rc`.

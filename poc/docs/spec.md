# Đặc Tả Hệ Thống PoC — ATIN Smart Fishing (Nhà Máy Thủy Sản Trần Hân)

> **Phiên bản hiện hành**: `v0.2.1` (PoC v001 — Single-Port FastAPI + Next.js Static Export + GPU AI Core + Docker Compose)  
> **Domain Public**: `https://tranhan.atin.vn/` (Ánh xạ trực tiếp tới cổng `28080` trên server GPU `aiot` `192.168.1.170`)  
> **Bộ tài liệu chi tiết**: Xem thư mục [poc/docs/pocv001/](file:///e:/ATIN/atin_tran_han_industry/poc/docs/pocv001) và hướng dẫn vận hành [poc/docs/deploy.md](file:///e:/ATIN/atin_tran_han_industry/poc/docs/deploy.md).

---

## 1. Mục Tiêu & Kiến Trúc Tổng Thể PoC

Hệ thống **ATIN Smart Fishing** cung cấp giao diện giám sát trực tiếp và lõi suy luận AI thời gian thực trên luồng camera của Nhà máy Thủy sản Trần Hân, đóng gói trọn vẹn trong **1 container Docker duy nhất (`tranhan_ai_poc`)** lắng nghe trên **1 cổng duy nhất (`28080`)**:

- **Giao diện Web (Next.js 15 App Router + TypeScript + Tailwind CSS)**:
  - Biên dịch tĩnh (`output: 'export'`) ra `/app/frontend/out` và được FastAPI phục vụ trực tiếp tại `/` trên cổng `28080`.
  - Áp dụng hệ thống thiết kế **ATIN IOC Platform × Soft Clean Cards** ([04_DESIGN_SYSTEM.md](file:///e:/ATIN/atin_tran_han_industry/poc/docs/pocv001/04_DESIGN_SYSTEM.md)).
  - Kiến trúc **Dual-Speed Rendering**: Tách riêng luồng vẽ BBox/Polygon tốc độ cao (`12–15 FPS` qua `<CameraOverlayCanvas />` với `requestAnimationFrame`, **0 React re-render**) và luồng cập nhật HUD tốc độ thấp (`~1 Hz` qua `<ZoneHudOverlay />`).
- **Bộ đọc luồng NVR chia sẻ trong RAM (`NvrStreamManager`)**:
  - Duy trì **1 kết nối HTTP Digest Auth duy nhất/camera** tới NVR Trần Hân (`nmts2025.smartddns.tv:80`), lưu gói `NvrFramePacket` (`frame` BGR + `jpeg_bytes` + `seq`) vào RAM (`buffer=1`).
  - Chia sẻ đồng thời cho cả **Lõi AI GPU** và **Endpoint phát video `GET /api/v1/cameras/{id}/mjpeg`**, giúp không làm nghẽn đường truyền DDNS của nhà máy khi nhiều người cùng mở `https://tranhan.atin.vn/` và đảm bảo hình ảnh khớp pha 100% với BBox.
- **Lõi AI GPU (`onnxruntime-gpu` CUDA 12 + ByteTrack + State Machine 4 trạng thái)**:
  - Chạy model **`poc/models/yolo26s.onnx`** (fine-tune riêng trên `factory_person_dataset/data.yaml`, 1 class `{0: 'person'}`) trên GPU NVIDIA RTX A400 với giới hạn cứng VRAM `<= 1024 MB` (~400 MB thực tế).
  - Gán ID theo dõi bằng `supervision.ByteTrack` kết hợp thuật toán `_snap_box_to_raw(min_iou=0.45)` khử trễ pha Kalman Filter.
  - Kiểm tra điểm chân nhân viên `(foot_x, foot_y) = ((x1 + x2) / 2, y2)` nằm trong vùng đa giác giám sát.

---

## 2. Danh Sách Camera Mặc Định (`poc/data/cameras.json`)

| ID | Kênh NVR (`channel`) | Tên hiển thị (`name`) | Ghi chú (`note`) | Bài toán mặc định (`feature_type`) |
| :--- | :---: | :--- | :--- | :--- |
| **`ch16`** | `16` | Tăng trọng 1 | Khu vực máy tăng trọng 1 | `zone_presence` |
| **`ch17`** | `17` | Tăng trọng 2 | Khu vực máy tăng trọng 2 | `zone_presence` |
| **`ch18`** | `18` | Tăng trọng 3 | Khu vực máy tăng trọng 3 | `zone_presence` |
| **`ch21`** | `21` | Định hình 2 | Khu vực định hình 2 | `zone_presence` |

---

## 3. Các Phân Hệ Chức Năng

### 3.1. Giám Sát Duy Trì Nhân Viên Trong Vùng (`zone_presence`)
Máy trạng thái 4 trạng thái nội bộ ánh xạ ra 3 màu giao diện trên HUD trong suốt (`rgba(15, 23, 42, 0.44)`), Polygon và khung viền camera:

| Trạng thái (`status`) | Màu UI (`ui_color`) | Nhãn chính (`status_label`) | Nhãn phụ (`sub_label`) | Điều kiện chuyển đổi |
| :--- | :---: | :--- | :--- | :--- |
| **`present`** | 🟢 `green` (`#22C55E`) | **CÓ NHÂN VIÊN** | `{N} người trong vùng` | `in_zone_count >= 1` |
| **`leaving`** | 🟢 `green` (`#22C55E`) | **CÓ NHÂN VIÊN** | `Vừa rời khỏi vùng` | Vừa chuyển từ `present` sang `in_zone_count == 0` trong thời gian `< grace_seconds` (`2.0s`) |
| **`empty`** | 🟡 `yellow` (`#F59E0B`) | **VÙNG TRỐNG** | `không có người {MM:SS}` | Cold start hoặc đã rời vùng `>= grace_seconds` (`2.0s`), thời gian ở trạng thái vàng `< warning_seconds` (`10.0s`) |
| **`alert`** | 🔴 `red` (`#EF4444`) | **KHÔNG CÓ NHÂN VIÊN** | `Cảnh báo · vùng trống {MM:SS}` | Vùng trống kéo dài `>= warning_seconds` (`10.0s`) → Tăng `alert_count`, cộng dồn `total_alert_seconds`, bật viền đỏ `3px` quanh khung video |

- **Hiển thị BBox**:
  - Nhân viên **trong vùng** (`in_zone: true`): Viền xanh lá `#22C55E` (`2px`), nhãn `Nhân viên #{track_id}`, chấm tròn điểm chân trắng-xanh.
  - Nhân viên **ngoài vùng** (`in_zone: false`): Làm mờ (`globalAlpha = 0.42`), viền xám `#94A3B8` (`1.25px`), nhãn nhỏ `#{track_id}`.
- **Rolling Timeline 30 phút**: Hiển thị dải màu lịch sử `green / yellow / red` trong cửa sổ trượt 30 phút gần nhất ngay trên HUD; hỗ trợ nút **Reset thống kê** (`POST /api/v1/detections/{cam_id}/reset-stats`).

### 3.2. Thiết Lập Vùng Giám Sát (`ZoneEditor`)
- Vẽ đa giác trực tiếp trên ảnh nền tĩnh (`snapshot.jpg`) ngay tại thẻ camera với tọa độ chuẩn hóa `[0.0 .. 1.0]`.
- Hỗ trợ hoàn tác (`Ctrl + Z`), hủy (`Escape`), xóa vùng, lưu trực tiếp vào `poc/data/cameras.json` (`PUT /api/v1/cameras/{cam_id}/zone`) hoặc import chuỗi JSON tọa độ trong hộp thoại cài đặt camera.

### 3.3. Phóng To (`FocusModal`), Ghi Hình & Tách Bộ Frame (`DatasetView`)
- **Phóng to 1 camera (`FocusModal`)**: Ưu tiên tần suất suy luận AI cho camera đang focus, chuyển đổi `Luồng chính (subtype=0)` / `Luồng phụ (subtype=1)`, tải ảnh snapshot, đặt lại thống kê cảnh báo.
- **Ghi hình video `.mp4`**: Ghi luồng MJPEG thành file `.mp4` (`10 FPS`) trong `5`, `10`, hoặc `20` phút tại `poc/storages/videos/`.
- **Tách bộ frame (`.jpg` & `.zip`)**: Tách ảnh từ video đã ghi với bước nhảy `skip_frames` (`5` hoặc `10` frame), xem trước thumbnail và tải trọn bộ dưới dạng `.zip` để gán nhãn huấn luyện model.

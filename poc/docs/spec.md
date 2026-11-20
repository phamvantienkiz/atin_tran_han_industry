# Đặc Tả Hệ Thống PoC — ATIN Smart Fishing (Nhà Máy Thủy Sản Trần Hân)

> **Phiên bản hiện hành**: **PoC v0.0.1 (`v0.2.2`)** — Single-Port FastAPI + Next.js Static Export + GPU AI Core + Docker BuildKit  
> **Domain Public**: `https://tranhan.atin.vn/` (Ánh xạ tới cổng `28080` trên server GPU `aiot` `192.168.1.170`)  
> **Bộ tài liệu liên quan**:
> - Chi tiết PoC v001: [poc/docs/pocv001/](file:///e:/ATIN/atin_tran_han_industry/poc/docs/pocv001/00_MASTER_OVERVIEW_AND_ARCHITECTURE.md)
> - Tài liệu Backend: [poc/backend/docs/spec.md](file:///e:/ATIN/atin_tran_han_industry/poc/backend/docs/spec.md) · [api-contract.md](file:///e:/ATIN/atin_tran_han_industry/poc/backend/docs/api-contract.md)
> - Tài liệu Frontend: [poc/frontend/docs/spec.md](file:///e:/ATIN/atin_tran_han_industry/poc/frontend/docs/spec.md) · [api-contract.md](file:///e:/ATIN/atin_tran_han_industry/poc/frontend/docs/api-contract.md)
> - Vận hành Docker: [poc/docs/deploy.md](file:///e:/ATIN/atin_tran_han_industry/poc/docs/deploy.md)

---

## 1. Mục Tiêu & Kiến Trúc Tổng Thể PoC

Hệ thống **ATIN Smart Fishing** cung cấp giao diện giám sát trực tiếp và lõi suy luận AI thời gian thực trên luồng camera của Nhà máy Thủy sản Trần Hân, đóng gói trọn vẹn trong **1 container Docker duy nhất (`tranhan_ai_poc`)** lắng nghe trên **1 cổng duy nhất (`28080`)**:

- **Giao diện Web (Next.js 15 App Router + React 19 + TypeScript + Tailwind CSS)**:
  - Biên dịch tĩnh (`output: 'export'`) ra `/app/frontend/out` và được FastAPI phục vụ trực tiếp tại `/` trên cổng `28080`.
  - Áp dụng hệ thống thiết kế **ATIN IOC Platform × Soft Clean Cards** ([04_DESIGN_SYSTEM.md](file:///e:/ATIN/atin_tran_han_industry/poc/docs/pocv001/04_DESIGN_SYSTEM.md)).
  - Kiến trúc **Dual-Speed Rendering**: External Store (`DetectionStore`) tách luồng `bbox` (vẽ trực tiếp lên HiDPI `<CameraOverlayCanvas />` bằng `requestAnimationFrame`, **0 React re-render**) và luồng `hud` (`~1 Hz` trên `<ZoneHudOverlay />`).
- **Bộ đọc luồng NVR chia sẻ trong RAM (`NvrStreamManager`) & `GridFrameCache`**:
  - Duy trì **1 kết nối HTTP Digest Auth duy nhất/camera** tới NVR Trần Hân (`nmts2025.smartddns.tv:80`), lưu gói `NvrFramePacket` (`jpeg_bytes` + `seq` + `ts_mono`) mới nhất vào RAM.
  - Khi xem Grid (`view=grid`, `subtype=0`), `GridFrameCache` resize & nén JPEG (`854px`, `Q=68`) theo nhu cầu (demand-driven) trên ThreadPool riêng để tiết kiệm băng thông trình duyệt (`X-Stream-Source: ram-grid-cache`). Khi xem Focus (`view=focus`), passthrough trực tiếp frame gốc (`ram-direct`).
- **Lõi AI GPU (`PersonZoneDetector`: `onnxruntime-gpu==1.23.2` CUDA 12 + ByteTrack + 4-state Rule Engine)**:
  - Chạy model **`poc/models/yolo26s.onnx`** (`{0: 'person'}`) trên GPU NVIDIA RTX A400 với giới hạn cứng VRAM `AI_VRAM_LIMIT_MB=1536` (~202 MiB thực tế), tự động nhận biết FP16/FP32 và overlap prefetch 1 camera kế tiếp.
  - Gán ID theo dõi bằng `supervision.ByteTrack` kết hợp `_snap_box_to_raw_ex(min_iou=0.25)` khử trễ pha Kalman Filter.
  - Đánh giá điểm neo mặc định **`AI_ANCHOR_MODE=center`** và ngưỡng tin cậy **`AI_CONF_THRESHOLD=0.55`**.
- **Lưu trữ SQLite WAL (`poc/data/tranhan_poc.db`)**:
  - Lưu cấu hình camera/zone (`cameras`), lịch sử sự kiện cảnh báo (`alert_events`, retention 90 ngày) và trạng thái bộ đếm (`runtime_snapshots`), tự động migrate dữ liệu ban đầu từ `poc/data/cameras.json`.

---

## 2. Danh Sách Camera Mặc Định

| ID | Kênh NVR (`channel`) | Tên hiển thị (`name`) | Ghi chú (`note`) | Bài toán mặc định (`feature_type`) |
| :--- | :---: | :--- | :--- | :--- |
| **`ch16`** | `16` | Tăng trọng 1 | Khu vực máy tăng trọng 1 | `zone_presence` |
| **`ch17`** | `17` | Tăng trọng 2 | Khu vực máy tăng trọng 2 | `zone_presence` |
| **`ch18`** | `18` | Tăng trọng 3 | Khu vực máy tăng trọng 3 | `zone_presence` |
| **`ch21`** | `21` | Định hình 2 | Khu vực định hình 2 | `zone_presence` |

---

## 3. Các Phân Hệ Chức Năng

### 3.1. Giám Sát Duy Trì Nhân Viên Trong Vùng (`zone_presence`)
Máy trạng thái 4 trạng thái nội bộ (kèm `idle` khi chưa vẽ vùng) ánh xạ ra màu giao diện trên HUD trong suốt (`rgba(15, 23, 42, 0.44)`), Polygon và khung viền camera:

| Trạng thái (`status`) | Màu UI (`ui_color`) | Nhãn chính (`status_label`) | Nhãn phụ (`sub_label`) | Điều kiện chuyển đổi |
| :--- | :---: | :--- | :--- | :--- |
| **`present`** | 🟢 `green` (`#22C55E`) | **CÓ NHÂN VIÊN** | `{N} người trong vùng` | `in_zone_count >= 1` |
| **`leaving`** | 🟢 `green` (`#22C55E`) | **CÓ NHÂN VIÊN** | `Vừa rời khỏi vùng` | Vừa chuyển từ `present` sang `in_zone_count == 0` trong `< grace_seconds` (`2.0s`) |
| **`empty`** | 🟡 `yellow` (`#F59E0B`) | **VÙNG TRỐNG** | `không có người {MM:SS}` | Cold start hoặc đã rời vùng `>= grace_seconds` (`2.0s`), ở trạng thái vàng `< warning_seconds` (`10.0s`) |
| **`alert`** | 🔴 `red` (`#EF4444`) | **KHÔNG CÓ NHÂN VIÊN** | `Cảnh báo · vùng trống {MM:SS}` | Vùng trống kéo dài `>= warning_seconds` (`10.0s`) → Tăng `alert_count`, cộng dồn `total_alert_seconds`, lưu `alert_events`, bật viền đỏ `3px` |
| **`idle`** | 🔵 `idle` (`#0284C7`) | **CHƯA VẼ VÙNG** | `Vẽ vùng giám sát để kích hoạt` | Camera chưa vẽ đa giác (`len(zone) < 3`) |

- **Hiển thị BBox**:
  - Nhân viên **trong vùng** (`in_zone: true`): Viền xanh lá `#22C55E` (`2px`), nhãn `%` độ tin cậy nền `#16A34A`.
  - Nhân viên **ngoài vùng** (`in_zone: false`): Làm mờ (`globalAlpha = 0.42`), viền xám `#94A3B8` (`1.25px`), nhãn `%` nền `#334155`. Không vẽ chấm tròn anchor.
- **Minimal Card & Rolling Timeline 30 phút**: Ẩn badge `"Trực tiếp"` lúc live bình thường; hiển thị dải màu lịch sử `green / yellow / red` trong cửa sổ 30 phút gần nhất kèm nút **Reset thống kê** (`POST /api/v1/detections/{cam_id}/reset-stats`).

### 3.2. Thiết Lập Vùng Giám Sát (`ZoneEditor`)
- Khi bật Zone Editor, frontend ngắt kết nối MJPEG của card để giải phóng socket và tải ảnh nền tĩnh `/snapshot.jpg?direct=true`.
- Hỗ trợ hoàn tác (`Ctrl + Z`), hủy (`Escape`), xóa vùng, lưu vào SQLite (`PUT /api/v1/cameras/{cam_id}/zone`) hoặc import chuỗi JSON tọa độ chuẩn hóa `[0.0 .. 1.0]`.

### 3.3. Phóng To Toàn Màn Hình (`FocusModal`), Ghi Hình & Tách Bộ Frame (`DatasetView`)
- **Phóng to 1 camera (`FocusModal`)**: Mở chế độ toàn màn hình (`requestFullscreen()` với fallback viewport), ưu tiên suy luận AI cho camera đang focus (`WS / REST`), sử dụng luồng `subtype=0&view=focus` (`ram-direct`).
- **Ghi hình video `.mp4`**: Ghi luồng MJPEG thành file `.mp4` (`10 FPS`) trong `5`, `10`, hoặc `20` phút tại `poc/storages/videos/`.
- **Tách bộ frame (`.jpg` & `.zip`)**: Tách ảnh từ video đã ghi với bước nhảy `skip_frames` (`5` hoặc `10` frame), xem trước thumbnail và tải trọn bộ `.zip`.

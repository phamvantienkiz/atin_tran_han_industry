# Changelog — `poc/frontend`

---

## [0.1.3] - 2026-11-20 (PoC v0.0.1 — Minimal HUD, Fullscreen Focus & BBox Refinement)
### Changed
- **CameraCard**: Ẩn badge `"Trực tiếp"` góc trên-phải trong trạng thái Live View bình thường (chỉ hiển thị khi tạm dừng hoặc `connecting`/`error`); loại bỏ logic xóa `img.src` khi ẩn/unmount để tránh báo lỗi stream giả.
- **CameraOverlayCanvas**: Đổi màu BBox người ngoài vùng về xám (`#94A3B8`, `globalAlpha = 0.42`, `lineWidth = 1.25`, nhãn `#334155`), ẩn chấm tròn anchor; người trong vùng giữ khung xanh lá (`#22C55E`) kèm nhãn `%` độ tin cậy.
- **FocusModal**: Chuyển sang chế độ xem toàn màn hình (`requestFullscreen()` với fallback viewport), tối giản giao diện tập trung vào video + canvas + HUD.

---

## [0.1.2] - 2026-11-19 (WebSocket Split Client, Canvas Optimization & Zone Editor Fix)
### Added
- `src/lib/ws-client.ts` & `src/lib/detection-store.ts`: Tách luồng `bbox` và `hud`, hỗ trợ reconnect tự động (`2s`) và fallback REST polling (`1s`).
- `src/components/ZoneHudOverlay.tsx`: Hiển thị trạng thái 4 cấp (`CÓ NHÂN VIÊN` / `VÙNG TRỐNG` / `KHÔNG CÓ NHÂN VIÊN` / `CHƯA VẼ VÙNG`), bộ đếm cảnh báo và thanh rolling timeline 30 phút.
### Fixed
- Ngắt kết nối MJPEG khi mở Zone Editor (`editingZone=true`) để tránh nghẽn giới hạn socket trình duyệt.
- Truyền `view=grid` cho MJPEG ở `CameraCard` và `view=focus` ở `FocusModal`; thêm `LatencyOverlay` đọc độ trễ trực tiếp không gây React re-render.

---

## [0.1.1] - 2026-11-19 (Zone Presence UI, Camera Form & Static Export)
### Added
- Cập nhật `CameraFormModal.tsx` bổ sung `zone_name`, `grace_seconds`, `warning_seconds`, và nhập tọa độ `zone` từ JSON.
- Thêm `DatasetView.tsx` cho phép quản lý video `.mp4`, tách frame (`skip 5`/`10`), xem trước ảnh và tải `.zip`.
- Tích hợp build tĩnh `output: 'export'` -> `poc/frontend/out/` phục vụ trực tiếp qua FastAPI `:28080`.

---

## [0.1.0] - 2026-11-19
### Added
- Khởi tạo ứng dụng **Next.js 15 + React 19 + TypeScript + Tailwind CSS** tại `poc/frontend/`, thay thế giao diện vanilla JS/HTML cũ (`poc/ui/`).
- Dựng bộ component đầu tiên: `Topbar`, `CameraGrid`, `CameraCard`, `CameraOverlayCanvas`, `FocusModal`, `CameraFormModal`, `AiBriefModal`, `Toast`.

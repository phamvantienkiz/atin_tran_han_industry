# Báo Cáo Kiểm Tra Kỹ Thuật & Bảo Mật (`poc/frontend`)

> Cập nhật theo trạng thái codebase **PoC v0.0.1** (commit `932f1e5`, 2026-11-20).

---

## 1. Kết quả kiểm tra tự động & build

- **TypeScript Typecheck (`.\node_modules\.bin\tsc.cmd --noEmit --incremental false`)**: Pass hoàn toàn (`exit code 0`, 0 lỗi kiểu dữ liệu trên toàn bộ `src/`).
- **Docker Static Export (`npm run build` trong stage `frontend-builder` của `poc/Dockerfile`)**: Build thành công với `node:20-alpine`, xuất tĩnh hoàn chỉnh sang `poc/frontend/out/` phục vụ bởi FastAPI.

---

## 2. Các tối ưu & kiểm soát kỹ thuật đã áp dụng

- **Tách luồng cập nhật BBox / HUD (`DetectionStore`)**:
  - Tách riêng `bboxListeners` (vẽ `<canvas>`) và `hudListeners` (trạng thái vùng, timeline), kết hợp `requestAnimationFrame` để tránh React re-render cả cây DOM ở tần suất cao.
  - `ZoneHudOverlay` so sánh chi tiết snapshot trước khi `setState`; `LatencyOverlay` cập nhật trực tiếp DOM `textContent` mỗi 1 giây.
- **Giải phóng kết nối trình duyệt (HTTP/1.1 6-connection limit)**:
  - Dùng `IntersectionObserver` + `visibilitychange` để tạm ngắt stream MJPEG ở các card ngoài viewport hoặc khi tab ẩn.
  - Ngắt MJPEG socket khi mở Zone Editor (`editingZone=true`) để ưu tiên kết nối cho `/snapshot.jpg?direct=true` và lưu zone.
  - Không gán lại `img.src = ''` khi unmount để tránh trình duyệt phát sự kiện `onError` giả (`8bb96c7`).
- **Chống BBox treo (Stale Pruning)**:
  - Canvas tự kiểm tra `nowSec - det._client_ts > bboxStaleSeconds` để xóa khung BBox cũ nếu luồng AI tạm ngưng, không giữ khung giả trên video đang chạy.
- **An toàn đường dẫn & mã hóa URL**:
  - Mọi tham số `cam_id`, `filename`, `folder` đưa vào URL đều được bọc qua `encodeURIComponent(...)`.
  - Hỗ trợ phím `Escape` để đóng các modal (`CameraFormModal`, `FocusModal`) và xử lý an toàn `requestFullscreen` fallback khi trình duyệt chặn auto-fullscreen.

---

## 3. Hạng mục cần nâng cấp khi lên Production

1. **Xác thực người dùng (Auth / RBAC)**: PoC chưa có màn hình đăng nhập hay gắn `Authorization: Bearer <JWT>`; khi ghép vào Production cần tích hợp luồng OIDC/Keycloak hoặc đọc token từ ATIN Smart VMS.
2. **Giám sát đa trang / Phân trang Camera**: Khi số lượng camera vượt quá 6–12 kênh, cần bổ sung phân trang hoặc nhóm theo phân khu/xưởng thay vì tải toàn bộ trên 1 grid.
3. **E2E Test tự động**: Bổ sung Playwright/Cypress test cho các luồng vẽ zone, focus fullscreen, ghi hình và tách frame.
4. **Hỗ trợ WebRTC / HLS / MSE (tùy chọn)**: Nếu cần phát H.264/H.265 độ phân giải cao với nhiều người xem đồng thời mà không giới hạn bởi số socket MJPEG HTTP/1.1.

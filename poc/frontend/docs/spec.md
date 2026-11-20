# Đặc Tả Kỹ Thuật Frontend (`poc/frontend`)

> Tài liệu đặc tả kiến trúc và hành vi thực tế của `poc/frontend` (**Next.js 15 App Router + React 19 + TypeScript + Tailwind CSS**) cho **PoC v0.0.1 — ATIN Smart Fishing**.

---

## 1. Kiến trúc tổng thể & Chế độ Build

`poc/frontend` được thiết kế dạng Single-Page Application (SPA) đóng gói tĩnh, do FastAPI (`poc/backend`) phục vụ trực tiếp trên cùng một origin và một cổng (`:28080`):

- **Production / Docker (`NODE_ENV=production`)**: `next.config.ts` kích hoạt `output: 'export'` và `images: { unoptimized: true }`, xuất toàn bộ HTML/JS/CSS tĩnh ra `poc/frontend/out/`. Backend FastAPI mount thư mục này tại `/` qua `StaticFiles`.
- **Development (`npm run dev` trên `:3000`)**: `next.config.ts` cấu hình `rewrites()` proxy toàn bộ `/api/v1/:path*` về `BACKEND_INTERNAL_URL` (mặc định `http://127.0.0.1:28080`).

---

## 2. Cấu trúc thư mục thực tế (`poc/frontend/src/`)

| Đường dẫn | Vai trò |
| :--- | :--- |
| `src/app/layout.tsx` | Root layout (`lang="vi"`), nạp font Inter, metadata `ATIN Smart Fishing` |
| `src/app/globals.css` | Design tokens CSS, style cho segmented tab, button, `.viewport-alert-ring` |
| `src/app/page.tsx` | Trang chủ điều phối 2 chế độ (`live` / `dataset`), bootstrap config, cameras, WebSocket và record polling |
| `src/lib/api.ts` | HTTP client `request<T>` (`timeout=15s`, AbortController) bọc toàn bộ `/api/v1/*` |
| `src/lib/ws-client.ts` | `DetectionsWsClient`: kết nối `ws/wss` `/api/v1/ws/detections`, tự reconnect sau `2s`, fallback polling `GET /api/v1/detections` mỗi `1s` khi WS mất kết nối |
| `src/lib/detection-store.ts` | Store in-memory tách `bboxListeners` (tần suất cao) và `hudListeners` (tần suất thấp) theo từng `cam_id`, quản lý `bboxStaleSeconds` |
| `src/lib/zone-utils.ts` | Tiện ích format thời gian (`formatMMSS`), dung lượng (`formatBytes`), ngày giờ, chuẩn hóa/parse JSON zone (`parseZoneJson`) |
| `src/types/index.ts` | Định nghĩa TypeScript interfaces (`Camera`, `CameraDetection`, `BboxWsMessage`, `HudWsMessage`, `AppConfig`, `VideoItem`, `FrameSetItem`, `ActiveRecordJob`) |
| `src/components/Topbar.tsx` | Thanh điều hướng sticky: Brand + NVR status pill, Page Switcher (`Live view` / `Video & Tách frame`), pill trạng thái đang ghi hình, Grid Layout Switcher (`1` / `4` / `6`), nút Refresh, AI Brief, Thêm Camera |
| `src/components/CameraGrid.tsx` | Lưới hiển thị camera responsive theo layout `1` (1 cột), `4` (2 cột), `6` (3 cột) |
| `src/components/CameraCard.tsx` | Thẻ camera: luồng MJPEG/snapshot, `CameraOverlayCanvas`, `ZoneHudOverlay`, `LatencyOverlay`, thanh công cụ thao tác, Zone Editor inline |
| `src/components/CameraOverlayCanvas.tsx` | Canvas `<canvas>` vẽ đa giác vùng giám sát, BBox người (xanh lá trong vùng / xám ngoài vùng), nhãn độ tin cậy `conf%` và giao diện click-to-draw khi sửa vùng |
| `src/components/ZoneHudOverlay.tsx` | Overlay HUD góc trên-trái hiển thị trạng thái nhân sự (`CÓ NHÂN VIÊN` / `VÙNG TRỐNG` / `KHÔNG CÓ NHÂN VIÊN` / `CHƯA VẼ VÙNG`), bộ đếm `Cảnh báo: N · MM:SS`, thanh rolling timeline 30 phút và nút reset stats |
| `src/components/FocusModal.tsx` | Chế độ xem toàn màn hình (`requestFullscreen()` + fallback fixed viewport) sử dụng luồng `subtype=0&view=focus` kèm `CameraOverlayCanvas` và `ZoneHudOverlay` |
| `src/components/CameraFormModal.tsx` | Modal Thêm/Sửa/Xóa camera, cấu hình `channel`, `zone_name`, `mode`, `subtype`, `grace_seconds`, `warning_seconds`, và nhập tọa độ `zone` từ JSON |
| `src/components/DatasetView.tsx` | Trang `Video & Tách frame`: danh sách video `.mp4` đã ghi (tải/xóa/tách frame `skip 5` hoặc `10`) và bộ ảnh frame (preview 4 ảnh, tải `.zip`, xóa) |
| `src/components/AiBriefModal.tsx` | Modal hiển thị thông số PoC, quy trình 4 trạng thái `zone_presence` và các thông số vận hành |
| `src/components/Toast.tsx` | Thông báo toast góc dưới màn hình (`3s` auto-dismiss) |

---

## 3. Luồng dữ liệu & Tối ưu Render (Zero-React-Re-render cho AI)

Để hiển thị 4–6 luồng MJPEG đồng thời mà không gây giật UI React:
1. **`DetectionsWsClient` -> `DetectionStore`**:
   - Khi nhận `bbox` message từ WebSocket, `detectionStore.updateBbox()` chỉ thông báo tới `bboxListeners` của đúng `cam_id` đó.
   - Khi nhận `hud` message, `detectionStore.updateHud()` chỉ thông báo tới `hudListeners` của đúng `cam_id` đó.
2. **`CameraOverlayCanvas` (Canvas 2D thuần)**:
   - Subscribe `bboxListeners` và `hudListeners` qua `useEffect` -> ghi vào `latestDetRef`, lập lịch vẽ bằng `requestAnimationFrame` (`scheduleDraw`). **Không lưu mảng `persons` vào React `useState`**.
   - Nếu `nowSec - det._client_ts > bboxStaleSeconds` (mặc định đọc từ `/api/v1/config`), canvas tự xóa BBox cũ (stale pruning) nhưng vẫn giữ đa giác vùng giám sát.
   - Người **trong vùng** (`in_zone === true`): khung xanh lá (`#22C55E`, `lineWidth = 2`), nhãn `%` nền `#16A34A`. Người **ngoài vùng**: khung xám (`#94A3B8`, `globalAlpha = 0.42`, `lineWidth = 1.25`), nhãn nền `#334155`. Không vẽ chấm tròn anchor.
3. **`ZoneHudOverlay` & `LatencyOverlay`**:
   - `ZoneHudOverlay` chỉ gọi `setState` khi `status`, `uiColor`, `subLabel`, `alertCount`, số giây làm tròn, hoặc độ dài/cuối `timeline` thực sự thay đổi.
   - `LatencyOverlay` cập nhật trực tiếp `spanRef.current.textContent` tối đa 1 lần/giây, không kích hoạt React re-render.
4. **Quản lý kết nối MJPEG trên `CameraCard`**:
   - Dùng `IntersectionObserver` (`threshold: 0.05`) và `document.visibilitychange` để tự tạm ngưng gắn `src` MJPEG khi card cuộn ra ngoài màn hình hoặc tab trình duyệt bị ẩn.
   - Khi vào chế độ Zone Editor (`editingZone = true`), luồng MJPEG được ngắt để giải phóng socket trình duyệt (giới hạn 6 kết nối HTTP/1.1 mỗi domain) và tải ảnh nền tĩnh `/snapshot.jpg?direct=true`.
   - Trong chế độ Live View bình thường, badge `"Trực tiếp"` góc trên-phải được ẩn đi để giữ khung hình sạch; badge chỉ hiện khi `streamPaused` hoặc `streamHealth !== 'live'` (`Đang kết nối` / `Mất kết nối`).

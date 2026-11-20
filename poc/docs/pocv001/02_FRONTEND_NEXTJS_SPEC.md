# PoC v001 — Đặc Tả Chi Tiết Frontend Next.js (`poc/frontend/`)

> **Mục tiêu**: Xây dựng ứng dụng **Next.js 15 (App Router + React 19 + TypeScript + Tailwind CSS)** tại `poc/frontend/` tuân thủ **[04_DESIGN_SYSTEM.md](file:///e:/ATIN/atin_tran_han_industry/poc/docs/pocv001/04_DESIGN_SYSTEM.md)** và chuẩn hiển thị **HUD 3 Màu & BBox/Polygon**.  
> **Cơ chế đóng gói**: Sử dụng **`output: 'export'`** xuất tĩnh ra `poc/frontend/out/` để FastAPI phục vụ trực tiếp trên cùng **1 Port duy nhất (`28080`)**, kết hợp kiến trúc **Dual-Speed Rendering** (0 React re-render cho luồng BBox).

---

## 1. Cấu Trúc Thư Mục `poc/frontend/` (Thực tế)

```text
poc/frontend/
├── design-system.md                 # Tài liệu tham khảo Design System
├── requirment/                      # 3 ảnh mẫu UI từ PM (CoNhanVien, VungTrong, KhongCoNhanVien)
├── docs/                            # Tài liệu kỹ thuật Frontend (spec, api-contract, audit, changelog)
├── package.json                     # Next.js 15 / React 19 / Tailwind CSS / Lucide React
├── package-lock.json
├── tsconfig.json
├── next.config.ts                   # output: 'export' (prod) + dev rewrites -> :28080
├── postcss.config.mjs
├── tailwind.config.ts               # Tokens từ design-system.md
├── out/                             # Thư mục build tĩnh (FastAPI mount tại /)
└── src/
    ├── app/
    │   ├── layout.tsx               # Font Inter + Metadata "ATIN Smart Fishing"
    │   ├── globals.css              # CSS Variables + HUD / segmented / viewport-alert-ring
    │   └── page.tsx                 # Trang chính điều phối Topbar + LiveView + DatasetView
    ├── types/
    │   └── index.ts                 # TypeScript interfaces (Camera, CameraDetection, BboxWsMessage, HudWsMessage...)
    ├── lib/
    │   ├── api.ts                   # Fetch wrapper (timeout 15s, Relative URL /api/v1/...)
    │   ├── detection-store.ts       # External Pub-Sub Store (tách bboxListeners & hudListeners)
    │   ├── ws-client.ts             # WebSocket client tự động ws/wss + reconnect 2s + fallback poll 1s
    │   └── zone-utils.ts            # formatMMSS, formatBytes, parseZoneJson, normalize tọa độ [0..1]
    └── components/
        ├── Topbar.tsx               # Brand, NVR pill, Live/Dataset tabs, Active Record pill, Layout 1/4/6, Actions
        ├── CameraGrid.tsx           # Lưới camera responsive 1 / 4 / 6
        ├── CameraCard.tsx           # Thẻ camera: MJPEG/Snapshot, ZoneEditor, CameraOverlayCanvas, ZoneHudOverlay, LatencyOverlay
        ├── ZoneHudOverlay.tsx       # HUD góc trên-trái 3 màu + Rolling Timeline 30 phút + nút Reset
        ├── CameraOverlayCanvas.tsx  # HiDPI Canvas vẽ Polygon + BBox (rAF, 0 React re-render)
        ├── FocusModal.tsx           # Xem toàn màn hình (requestFullscreen + fallback viewport, subtype=0&view=focus)
        ├── CameraFormModal.tsx      # Thêm/Sửa/Xóa camera, zone_name, grace/warning seconds, Import Zone JSON
        ├── AiBriefModal.tsx         # Modal thông số PoC & quy trình 4 trạng thái
        ├── DatasetView.tsx          # Quản lý Video đã ghi (.mp4) & Tách bộ Frame (.zip)
        └── Toast.tsx                # Thông báo góc dưới màn hình
```

---

## 2. Cấu Hình Chuẩn & Quy Tắc Relative-Origin

- **`next.config.ts`**:
  - Khi `NODE_ENV === 'production'`: bật `output: 'export'` và `images: { unoptimized: true }` -> xuất tĩnh vào `poc/frontend/out/`.
  - Khi `npm run dev` (cổng `3000`): cấu hình `rewrites()` chuyển `/api/v1/:path*` sang `BACKEND_INTERNAL_URL` (`http://127.0.0.1:28080`).
- **Relative-Origin**: Mọi URL REST, MJPEG, Snapshot, Download đều dùng đường dẫn tương đối `/api/v1/...`; WebSocket tự suy ra `ws:` hoặc `wss:` từ `window.location.protocol` + `window.location.host` + `cfg.ws_path` (`/api/v1/ws/detections`).

---

## 3. Kiến Trúc Dual-Speed Rendering & Quản Lý Kết Nối

1. **External Store (`src/lib/detection-store.ts`)**:
   - Tách riêng `bboxListeners` (nhận message `type: "bbox"` tần suất cao) và `hudListeners` (nhận message `type: "hud"` tần suất thấp `1s`/`2s`).
   - Đóng dấu `_client_ts = Date.now() / 1000` ngay tại trình duyệt khi nhận dữ liệu để triệt tiêu hoàn toàn lỗi lệch đồng hồ Server–Client (`Clock Skew`).
   - Lưu cấu hình `bboxStaleSeconds` nhận từ `/api/v1/config` (mặc định backend `1.8s`).
2. **HiDPI Canvas (`src/components/CameraOverlayCanvas.tsx`)**:
   - Lắng nghe `detectionStore.subscribeBbox` & `subscribeHud`, lập lịch vẽ bằng `requestAnimationFrame` (**0 React re-render**).
   - Tự động xóa BBox cũ khi `nowSec - det._client_ts > bboxStaleSeconds` nhưng vẫn giữ đa giác vùng giám sát.
   - **BBox trong vùng (`in_zone === true`)**: nét liền `2px` màu xanh lá `#22C55E`, nhãn `%` độ tin cậy nền `#16A34A`.
   - **BBox ngoài vùng (`in_zone === false`)**: nét mảnh `1.25px` màu xám `#94A3B8` (`globalAlpha = 0.42`), nhãn `%` nền `#334155`. Không vẽ chấm tròn anchor.
3. **Minimal HUD & Viewport (`CameraCard.tsx`, `ZoneHudOverlay.tsx`, `FocusModal.tsx`)**:
   - `CameraCard` dùng `IntersectionObserver` (`threshold: 0.05`) + `document.visibilitychange` để tạm ngưng gắn `src` MJPEG khi card nằm ngoài viewport hoặc tab bị ẩn (không gán `img.src = ''` khi unmount để tránh lỗi giả).
   - Ẩn badge `"Trực tiếp"` khi đang stream bình thường (`!editingZone && (streamPaused || streamHealth !== 'live')`).
   - Khi vào Zone Editor (`editingZone=true`), ngắt kết nối MJPEG để giải phóng socket HTTP/1.1 và nạp `/snapshot.jpg?direct=true`.
   - `FocusModal` sử dụng Web Fullscreen API (`requestFullscreen()` với fallback viewport `w-screen h-screen`) và luồng `subtype=0&view=focus`.

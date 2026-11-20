# PoC v001 — Đặc Tả Chi Tiết Frontend Next.js (`poc/frontend/`)

> **Mục tiêu**: Xây dựng ứng dụng **Next.js (App Router + TypeScript + Tailwind CSS)** tại `poc/frontend/` tuân thủ nghiêm ngặt **[04_DESIGN_SYSTEM.md](file:///e:/ATIN/atin_tran_han_industry/poc/docs/pocv001/04_DESIGN_SYSTEM.md)** (Hợp nhất **ATIN IOC Platform `ds-atin1.md` / `ds-atin2.md`** làm chính kết hợp với **Soft Clean Cards `design-system.md`**) và chuẩn hiển thị **HUD 3 Màu & BBox/Polygon** theo 3 ảnh mẫu của PM (`poc/frontend/requirment/{CoNhanVien.jpg, VungTrong.jpg, KhongCoNhanVien.jpg}`).  
> **Cơ chế đóng gói**: Sử dụng **`output: 'export'`** xuất tĩnh ra `poc/frontend/out/` để FastAPI phục vụ trực tiếp trên cùng **1 Port duy nhất (`28080`)**, đồng thời áp dụng kiến trúc **Dual-Speed Rendering** (0 React re-render cho luồng BBox 15 FPS).

---

## 1. Bảo Toàn Tài Liệu Thiết Kế & Dọn Chỗ Cho Next.js

Trước khi khởi tạo dự án Next.js trong `poc/frontend/`:
1. **Giữ lại bắt buộc**:
   - `poc/frontend/design-system.md` (Nguồn sự thật về màu sắc, font chữ, bo góc, đổ bóng).
   - `poc/frontend/requirment/` (`CoNhanVien.jpg`, `VungTrong.jpg`, `KhongCoNhanVien.jpg`).
2. **Backup code HTML/JS thuần cũ** (hoặc chuyển vào `poc/frontend/legacy_vanilla/`):
   - Di chuyển `index.html`, `styles.css`, `js/` vào `poc/frontend/legacy_vanilla/` để tham chiếu logic khi cần và tránh xung đột với cấu trúc Next.js.

---

## 2. Cấu Trúc Thư Mục `poc/frontend/` (Next.js App Router)

```text
poc/frontend/
├── design-system.md                 # Giữ nguyên — Tài liệu chuẩn Design System
├── requirment/                      # Giữ nguyên — 3 ảnh mẫu UI từ PM
├── package.json                     # Next.js 15 / React 19 / Tailwind CSS / Lucide React
├── tsconfig.json
├── next.config.ts                   # Cấu hình output: 'export' + dev rewrites
├── postcss.config.mjs
├── tailwind.config.ts               # Tokens từ design-system.md
├── out/                             # Thư mục build tĩnh (FastAPI mount trực tiếp tại /)
└── src/
    ├── app/
    │   ├── layout.tsx               # Font Inter + Metadata "ATIN Trần Hân — Giám sát AI"
    │   ├── globals.css              # CSS Variables chuẩn design-system.md + HUD styles
    │   └── page.tsx                 # Trang chính điều phối Topbar + LiveView + DatasetView
    ├── types/
    │   └── index.ts                 # TypeScript interfaces (Camera, DetectionResult, RecordJob...)
    ├── lib/
    │   ├── api.ts                   # Fetch wrapper dùng Relative URL (/api/v1/...)
    │   ├── detection-store.ts       # External Pub-Sub Store cho Dual-Speed Rendering
    │   ├── ws-client.ts             # WebSocket client tự động ws:// hoặc wss:// + fallback poll
    │   └── zone-utils.ts            # Hàm parseZoneJson & chuẩn hóa tọa độ [0..1]
    └── components/
        ├── Topbar.tsx               # Header thương hiệu, trạng thái NVR, chuyển trang, chọn layout 1/4/6
        ├── CameraGrid.tsx           # Lưới camera 1 / 4 / 6 + ô trống "Thêm camera"
        ├── CameraCard.tsx           # Thẻ camera: Header, ZoneToolbar, Viewport (MJPEG + HUD + Canvas), MetricRow
        ├── ZoneHudOverlay.tsx       # HUD góc trên-trái 3 màu + Rolling Timeline 30 phút (React 1 Hz)
        ├── CameraOverlayCanvas.tsx  # HiDPI Canvas vẽ Polygon + BBox + Điểm chân (rAF 15 FPS, 0 React render)
        ├── FocusModal.tsx           # Xem phóng to 1 camera, đổi luồng Chính/Phụ, Reset thống kê, Ghi hình MP4
        ├── CameraFormModal.tsx      # Thêm/Sửa/Xóa camera, cấu hình tên vùng, grace/warning seconds, Import Zone
        ├── AiBriefModal.tsx         # Modal đối chiếu 4 bài toán AI nhà máy Trần Hân
        ├── DatasetView.tsx          # Quản lý Video đã ghi (.mp4) & Tách bộ Frame (.zip)
        └── Toast.tsx                # Thông báo góc dưới màn hình
```

---

## 3. Cấu Hình Chuẩn `package.json` & `next.config.ts`

### 3.1. `poc/frontend/package.json`
Giữ bộ dependencies tối giản, gọn nhẹ nhất để cài đặt và build trên server `aiot` chỉ mất vài giây:

```json
{
  "name": "tranhan-ai-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev -p 3000",
    "build": "next build",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "lucide-react": "^0.460.0",
    "next": "^15.1.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@types/node": "^22.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.49",
    "tailwindcss": "^3.4.15",
    "typescript": "^5.6.3"
  }
}
```

### 3.2. `poc/frontend/next.config.ts`
Hỗ trợ đồng thời **Static Export (`output: 'export'`)** khi chạy `npm run build` (để FastAPI mount trên server `aiot`) và **API Proxy (`rewrites`)** khi chạy `npm run dev` trên máy local:

```typescript
import type { NextConfig } from 'next';

const isProdBuild = process.env.NODE_ENV === 'production';

const nextConfig: NextConfig = {
  // Khi build (npm run build), xuất ra thư mục tĩnh poc/frontend/out/
  ...(isProdBuild ? { output: 'export' } : {}),
  images: {
    unoptimized: true,
  },
  // Khi chạy dev (npm run dev ở localhost:3000), tự proxy /api/v1/* về FastAPI :28080
  ...(!isProdBuild
    ? {
        async rewrites() {
          const backendUrl = process.env.BACKEND_INTERNAL_URL || 'http://127.0.0.1:28080';
          return [
            {
              source: '/api/v1/:path*',
              destination: `${backendUrl}/api/v1/:path*`,
            },
          ];
        },
      }
    : {}),
};

export default nextConfig;
```

---

## 4. Quy Tắc Relative-Origin Tuyệt Đối (Chạy Xuyên Suốt Termius, LAN, Public IP & Domain HTTPS)

> [!CRITICAL]
> **CẤM HARDCODE `http://localhost:28080` HAY `http://192.168.1.170:28080` TRONG MÃ NGUỒN FRONTEND!**

Vì ứng dụng sẽ được xem qua **cả 3 đường**:
1. Laptop dev qua Termius Port Forwarding (`http://localhost:28080`)
2. Mạng nội bộ công ty (`http://192.168.1.170:28080`)
3. Khách hàng xem trực tiếp qua Port Public hoặc Domain công ty (`http://<PUBLIC_IP>:<PORT>` hoặc `https://poc-tranhan.atin.vn`)

Nên mọi kết nối mạng trong `src/lib/api.ts` và `src/lib/ws-client.ts` **bắt buộc dùng đường dẫn tương đối theo `window.location`**:

- **REST API & MJPEG / Snapshot**:
  - Luôn gọi bắt đầu bằng `/api/v1/...` (ví dụ: `/api/v1/cameras`, `/api/v1/cameras/${cam.id}/mjpeg?subtype=${sub}&t=${ts}`).
- **WebSocket (`/api/v1/ws/detections`)**:
  ```typescript
  export function getDetectionsWsUrl(): string {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${window.location.host}/api/v1/ws/detections`;
  }
  ```
  - Tự động reconnect sau `2000ms` nếu mất kết nối.
  - Nếu WebSocket đang bị gián đoạn (ví dụ mạng khách hàng chặn WS), tự động bật fallback HTTP polling `GET /api/v1/detections` mỗi `1000ms`, và tự tắt polling ngay khi WebSocket kết nối lại thành công!

---

## 5. Kiến Trúc Dual-Speed Rendering (Chống Giật Lag BBox Trong React)

Đây là phần kỹ thuật quan trọng nhất của Frontend (đã phân tích trong [brainstorm.md](file:///e:/ATIN/atin_tran_han_industry/poc/docs/brainstorm.md#L88-L112)):

### 5.1. External Store (`src/lib/detection-store.ts`)
Không đưa mảng `persons[]` (thay đổi tọa độ 12–15 lần/giây) vào `useState` của component cha! Thay vào đó, tạo một store pub-sub siêu nhẹ ngoài React:

```typescript
import type { CameraDetection } from '@/types';

type Listener = (det: CameraDetection | null) => void;

class DetectionStore {
  private data: Record<string, CameraDetection> = {};
  private camListeners: Map<string, Set<Listener>> = new Map();

  updateAll(nextMap: Record<string, CameraDetection>) {
    this.data = nextMap || {};
    for (const [camId, listeners] of this.camListeners.entries()) {
      const det = this.data[camId] || null;
      listeners.forEach((fn) => fn(det));
    }
  }

  get(camId: string): CameraDetection | null {
    return this.data[camId] || null;
  }

  subscribeCamera(camId: string, fn: Listener): () => void {
    let set = this.camListeners.get(camId);
    if (!set) {
      set = new Set();
      this.camListeners.set(camId, set);
    }
    set.add(fn);
    fn(this.get(camId));
    return () => {
      set?.delete(fn);
    };
  }
}

export const detectionStore = new DetectionStore();
```

### 5.2. Luồng Tốc Độ Cao 15 FPS — `<CameraOverlayCanvas />` (0 React Re-render)
- Component `<CameraOverlayCanvas cam={cam} zoneEditorState={...} />` giữ `canvasRef` và `latestDetectionRef = useRef<CameraDetection | null>(null)`.
- Trong `useEffect`, đăng ký `detectionStore.subscribeCamera(cam.id, (det) => { latestDetectionRef.current = det; scheduleDraw(); })`.
- Hàm `scheduleDraw()` gọi `requestAnimationFrame(draw)` để vẽ trực tiếp lên `<canvas>` mà **không kích hoạt bất kỳ lần React re-render nào**:
  1. **HiDPI Scaling**: Tự động nhân `canvas.width = Math.round(clientWidth * dpr)` và `ctx.setTransform(dpr, 0, 0, dpr, 0, 0)`.
  2. **Bảng màu chuẩn 3 trạng thái**:
     - `green`: `#22c55e` (fill `rgba(34, 197, 94, 0.14)`)
     - `yellow`: `#f59e0b` (fill `rgba(245, 158, 11, 0.14)`)
     - `red`: `#ef4444` (fill `rgba(239, 68, 68, 0.18)`)
     - `idle`: `#1f5fff` (fill `rgba(31, 95, 255, 0.14)`)
  3. **Vẽ Đa giác Vùng Giám Sát (Polygon)**:
     - Vẽ nền bán trong suốt + đường viền `2.5px` theo màu `ui_color`.
     - Vẽ các chấm tròn trắng `r = 3.5px` có viền `2px` màu `ui_color` tại tất cả các đỉnh đa giác.
     - Vẽ **Polygon Tag Pill** tại đỉnh cao nhất nằm ngoài vùng góc trên-trái của HUD (`px >= hudBoxW || py >= hudBoxH`) để không bao giờ bị khối HUD che khuất:
       - Nền màu `ui_color`, chữ trắng in đậm `10.5px`, hiển thị `det.polygon_label` (ví dụ: `TĂNG TRỌNG 2 · 2 NV` / `TĂNG TRỌNG 2 · VỪA RỜI VÙNG` / `TĂNG TRỌNG 2 · TRỐNG` / `TĂNG TRỌNG 2 · KHÔNG CÓ NHÂN VIÊN`).
  4. **Vẽ Bounding Box Nhân Viên & Điểm Chân**:
     - Kiểm tra chống bóng ma (Anti-Ghosting không bị ảnh hưởng bởi lệch đồng hồ Server vs Client): đóng dấu `_client_ts = Date.now() / 1000` ngay khi trình duyệt nhận gói WebSocket và chỉ vẽ BBox khi `Date.now() / 1000 - (det._client_ts || det.updated_at) < 3.0`.
     - **Nếu `p.in_zone === true`**:
       - Viền `#22c55e` dày `2px`.
       - Nhãn pill nền `#22c55e` chữ trắng ở góc trên-trái box: `Nhân viên #${p.track_id ?? idx + 1}`.
       - Điểm chân tại `(p.foot_x * w, p.foot_y * h)`: chấm tròn `r = 4.5px` nền `#22c55e`, viền trắng `2px`.
     - **Nếu `p.in_zone === false`**:
       - Đặt `ctx.save(); ctx.globalAlpha = 0.42;`.
       - Viền `#94a3b8` mảnh `1.25px`.
       - Nhãn nhỏ nền `#475569` chữ trắng: `#${p.track_id ?? idx + 1}`.
       - Điểm chân nhỏ `r = 3px` màu `#94a3b8`, rồi `ctx.restore()`.
  5. **Vẽ Chế độ Đang Chỉnh Sửa Vùng (`ZoneEditor`)**:
     - Khi user đang bật chế độ vẽ vùng trên thẻ camera: hiển thị các đỉnh đang click, đường nối nét đứt khép kín đa giác và vùng tô màu xanh `#1f5fff`.

### 5.3. Luồng Tốc Độ Thấp ~1 Hz — `<ZoneHudOverlay />` & Viền Đỏ Cảnh Báo
- Component `<ZoneHudOverlay cam={cam} compact={layoutCount >= 4} />` cũng subscribe vào `detectionStore.subscribeCamera(cam.id, ...)`, nhưng **chỉ gọi `setHudState(...)` khi chữ hiển thị hoặc màu sắc thực sự thay đổi** (so sánh `prev.status !== next.status || prev.ui_color !== next.ui_color || prev.sub_label !== next.sub_label || prev.alert_count !== next.alert_count || Math.floor(prev.total_alert_seconds) !== Math.floor(next.total_alert_seconds)`).
- Nhờ vậy, React chỉ cập nhật DOM của HUD tối đa **1 lần mỗi giây** (khi đồng hồ `00:01 -> 00:02` nhảy số)!
- **Giao diện `<ZoneHudOverlay />` trong suốt & nhỏ gọn khớp với 3 ảnh mẫu của PM**:
  - Đặt ở góc trên-trái trong `.viewport` (`position: absolute; top: 10px; left: 10px; z-index: 10; pointer-events: none;`).
  - Nền trong suốt `rgba(15, 23, 42, 0.44)` (`--surface-hud`), `backdrop-filter: blur(3px)`, đổ bóng chữ `[text-shadow:0_1px_2px_rgba(0,0,0,0.85)]`, kích thước gọn (`max-w-[214px]` trên lưới 4/6 cam, `max-w-[262px]` khi phóng to), thanh vạch màu `3px` bên trái đổi theo `green` (`#22c55e`), `yellow` (`#f59e0b`), `red` (`#ef4444`) để nhìn xuyên thấu thấy rõ Poly Zone và công nhân phía sau.
  - **5 dòng thông tin chuẩn**:
    1. `GIÁM SÁT NHÂN VIÊN · ${(cam.zone_name || cam.name).toUpperCase()}`
    2. Chấm tròn màu + **`CÓ NHÂN VIÊN` / `VÙNG TRỐNG` / `KHÔNG CÓ NHÂN VIÊN`**
    3. Nhãn phụ: `1 người trong vùng` | `Vừa rời khỏi vùng` | `không có người 00:02` | `Cảnh báo · vùng trống 00:12`
    4. Thống kê: `Tổng cảnh báo: ${formatMMSS(det.total_alert_seconds)} · Số lần: ${det.alert_count}`
    5. Thanh **Timeline (30p)**: hiển thị các đoạn `det.timeline` (`green / yellow / red`) theo tỷ lệ chiều rộng `(seg.end - seg.start) / totalSpan * 100%`.
- **Viền đỏ toàn khung Viewport khi `ui_color === 'red'`**:
  - Khi trạng thái là `alert` (`ui_color === 'red'`), khung `.viewport` của thẻ camera (và `.focus-viewport` trong Focus Modal) bật viền đỏ nổi bật: `box-shadow: inset 0 0 0 3px #ef4444, 0 0 16px rgba(239, 68, 68, 0.35)`.

---

## 6. Bảo Toàn 100% Các Tính Năng Quản Lý & Tách Dataset Hiện Có

Ngoài phần nâng cấp Live View + HUD + Dual-Speed Canvas ở trên, ứng dụng Next.js phải giữ đầy đủ mọi tính năng đang có trong `poc/frontend/`:

1. **Thanh Topbar**:
   - Tên thương hiệu **`ATIN Smart Fishing`** + phụ đề `Giám sát AI nhà máy thủy sản`.
   - Pill trạng thái kết nối NVR (`nmts2025.smartddns.tv` — chấm xanh online / đỏ offline).
   - Segmented control chuyển tab: **`Live view`** ↔ **`Video & Tách frame`**.
   - Pill báo hiệu toàn cục khi có phiên đang ghi hình (`Đang ghi CH 16 · còn 04:12`).
   - Cụm nút điều khiển Live View: chọn bố cục lưới **`1` / `4` / `6`**, nút **`Làm mới`**, nút **`Bài toán AI`**, nút **`Thêm camera`**.
2. **Công cụ Vẽ Vùng Giám Sát (`ZoneEditor`) trên từng `CameraCard`**:
   - Khi bấm icon đa giác trên thẻ camera: nạp ảnh tĩnh `/api/v1/cameras/${cam.id}/snapshot.jpg?t=${Date.now()}` làm nền đứng yên để vẽ chính xác, hiện thanh công cụ (`Hoàn tác`, `Xóa`, `Lưu vùng`, `Hủy`), hỗ trợ phím tắt `Ctrl+Z` và `Escape`.
3. **Focus Modal (Phóng to 1 camera)**:
   - Xem khung hình lớn kèm `<ZoneHudOverlay compact={false} />` và `<CameraOverlayCanvas />`.
   - Chuyển đổi `Luồng chính (subtype=0)` / `Luồng phụ (subtype=1)`.
   - Nút **`Reset thống kê`** (`POST /api/v1/detections/${cam.id}/reset-stats`) để đặt lại bộ đếm cảnh báo & timeline khi bắt đầu phiên demo mới cho khách hàng.
   - Nút **`Record`** (chọn `5 phút`, `10 phút`, `20 phút` hoặc bấm `Dừng` khi đang ghi) và nút **`Tải ảnh`**.
4. **Camera Form Modal (Thêm / Sửa / Xóa Camera)**:
   - Chỉnh sửa: `Kênh NVR (1..128)`, `Tên hiển thị`, `Tên vùng trên HUD (zone_name)`, `Ghi chú`, `Chế độ phát (mjpeg / snapshot)`, `Luồng NVR (0 / 1)`, `Thời gian trễ rời vùng grace_seconds (mặc định 2s)`, `Thời gian cảnh báo trống vùng warning_seconds (mặc định 10s)`, và ô **Import tọa độ Zone JSON**.
5. **Trang `Video & Tách frame` (`DatasetView`)**:
   - Danh sách video `.mp4` đã ghi (`Tách frame` với tùy chọn bỏ qua `5` hoặc `10` frame, `Tải MP4`, `Xóa video`).
   - Danh sách các bộ frame đã tách (hiển thị tổng số frame, dải ảnh xem trước thumbnail, nút `Tải bộ ảnh (.zip)`, `Xóa bộ frame`).

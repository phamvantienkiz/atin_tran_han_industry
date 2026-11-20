# PoC v001 — Hệ Thống Thiết Kế Hợp Nhất: ATIN IOC Platform × Soft Clean Cards (`04_DESIGN_SYSTEM.md`)

> **Tuyên ngôn Thiết kế (Design Intent — 1 Câu)**:  
> Xây dựng giao diện giám sát AI thời gian thực cho **Nhà máy Thủy sản Trần Hân** dựa trên hệ màu chuẩn công nghiệp, cấu trúc token và tiêu chuẩn truy cập **WCAG 2.2 AA của ATIN IOC Platform (`aioc.atin.vn/monitoring` & `aioc.atin.vn/login`)**, kết hợp với bố cục thẻ bo tròn thoáng đãng, phân cấp thị giác tĩnh lặng của **Soft Clean Cards (`design-system.md`)** để làm nổi bật tức thì các tín hiệu cảnh báo AI (`Xanh / Vàng / Đỏ`) trên luồng camera trực tiếp.

---

## 1. Bối Cảnh, Mục Tiêu & Nguyên Tắc Kết Hợp (Context & Goals)

### 1.1. Nguồn Tham Chiếu Gốc
Tài liệu này là **Nguồn Sự Thật Duy Nhất (Single Source of Truth)** về UI/UX cho **Hydrogen / Neon** khi xây dựng `poc/frontend/` (Next.js App Router + TypeScript + Tailwind CSS), được tổng hợp từ:
1. **[Chính — 70%] ATIN IOC Platform (`poc/docs/note/ds-atin1.md` & `poc/docs/note/ds-atin2.md`)**:
   - Bề mặt sản phẩm: Hệ thống điều hành & giám sát camera AI (`https://aioc.atin.vn/monitoring`).
   - Hệ màu Slate-Navy công nghiệp (`#17233C`, `#1E293B`, `#334155`, `#4A5D80`), nền sáng lạnh (`#F1F5F9`, `#F8FAFC`, `#FFFFFF`), viền xanh xám đặc trưng (`#DDE5F1`, `#E2E8F0`), điểm nhấn thương hiệu ATIN (`#0284C7` Sky Blue, `#0044A4` Deep Blue, `#F6931D` Amber Orange) và khung nền video đen tuyệt đối (`#000000`).
   - Kỷ luật kỹ thuật bắt buộc: Token hóa 100%, định nghĩa đủ **7 trạng thái** cho mọi component tương tác, hỗ trợ bàn phím/chuột/cảm ứng và tiêu chuẩn nghiệm thu **WCAG 2.2 AA** có thể kiểm thử Pass/Fail.
2. **[Bổ trợ — 30%] Soft Clean Cards (`poc/docs/note/design-system.md`)**:
   - Triết lý *"Một thẻ = Một nhiệm vụ"* và *"Màu sắc là thông tin, không phải trang trí"*.
   - Thẻ trắng tinh khiết (`#FFFFFF`) đặt trên nền xám xanh dịu (`#F1F5F9` → `#F8FAFC`), bo góc mềm mại đồng tâm, đổ bóng màu xanh navy cực nhẹ (`rgba(20, 40, 80, 0.08)`), cụm `Segmented Control` trượt mượt và hàng chỉ số `Metric Row` 3 cột không vách ngăn nặng nề.

### 1.2. 5 Quy Tắc Thị Giác Cốt Lõi
1. **90% Khung Vỏ Tĩnh Lặng — 10% Màu Sắc Mang Tín Hiệu**: Toàn bộ Topbar, nền trang, khung thẻ Camera và bảng Dataset dùng tông **Slate-Navy & Trắng** của ATIN IOC. Màu rực chỉ được phép xuất hiện ở:
   - Nút hành động chính (`#0284C7` — ATIN Monitoring Blue).
   - 3 trạng thái AI trên HUD, Polygon và Viền cảnh báo: 🟢 `#22C55E` (*Có nhân viên*), 🟡 `#F59E0B` (*Vùng trống*), 🔴 `#EF4444` (*Không có nhân viên*).
2. **Tương Phản Tối Đa Trên Khung Hình Video (`#000000`)**: Khung chứa luồng camera (`.viewport`) luôn có nền `#000000`. Khối HUD đè lên video bắt buộc dùng nền kính mờ tối (`rgba(15, 23, 42, 0.82)` + `backdrop-filter: blur(8px)`) để đọc rõ chữ trắng trên mọi điều kiện ánh sáng của xưởng chế biến thủy sản.
3. **Số Liệu Cố Định Độ Rộng (`tabular-nums`)**: Mọi bộ đếm giây (`00:12`), độ trễ (`145 ms`), số lượng người (`1 NV`), thời lượng ghi hình (`04:58`) bắt buộc bật `font-variant-numeric: tabular-nums` để khung chữ không bị rung lắc khi số nhảy mỗi giây.
4. **Bo Góc Đồng Tâm (Nested Radius Harmony)**: Bo góc phần tử con bằng bo góc phần tử cha trừ đi khoảng cách đệm (`Card: 20px` − `Padding: 16px/20px` → `Viewport / Inner Panel: 12px` → `Button / Input: 8px` → `Timeline Segment / Badge: 4px–6px`, `Pill: 9999px`).
5. **Không Dùng Emoji Làm Icon**: Mọi biểu tượng trên giao diện bắt buộc dùng SVG nét mảnh `1.5px` từ bộ **`lucide-react`** (`16px` / `20px`), kế thừa `currentColor`.

---

## 2. Kiến Trúc Design Tokens 3 Tầng (Foundations & Semantic Tokens)

Mọi component trong `poc/frontend/src/` **phải** sử dụng token ngữ nghĩa (Semantic CSS Variables / Tailwind classes), **không được** viết mã hex rời rạc trong từng file TSX.

### 2.1. Bảng Màu Ngữ Nghĩa Hợp Nhất (ATIN IOC × Soft Cards)

| Nhóm | Semantic Token (CSS Variable) | Tailwind Class | Mã Hex / Giá trị | Nguồn gốc & Mục đích sử dụng |
| :--- | :--- | :--- | :--- | :--- |
| **Bề mặt (Surfaces)** | `--surface-page` | `bg-surface-page` | `#F1F5F9` | Nền trang tổng thể (`ds-atin2: color.surface.raised`) |
| | `--surface-card` | `bg-surface-card` | `#FFFFFF` | Nền thẻ Camera, Data Card, Modal (`ds-atin1: color.surface.muted`) |
| | `--surface-subtle` | `bg-surface-subtle` | `#F8FAFC` | Nền vùng phụ trong thẻ, Segmented track, Input (`ds-atin1: color.surface.raised`) |
| | `--surface-subtle-hover` | `bg-surface-subtle-hover` | `#E2E8F0` | Nền khi hover nút phụ / ghost button |
| | `--surface-video` | `bg-surface-video` | `#000000` | Nền khung video camera 16:9 (`ds-atin1/2: color.surface.base`) |
| | `--surface-hud` | `bg-surface-hud` | `rgba(15, 23, 42, 0.44)` | Nền kính mờ trong suốt của HUD đè lên video (`backdrop-blur-[3px]`, nhìn xuyên thấu thấy rõ Poly Zone phía sau) |
| **Thương hiệu & Hành động (Brand)** | `--brand-primary` | `bg-brand-primary` / `text-brand-primary` | `#0284C7` | Nút chính (Primary CTA), trạng thái đang chọn, Focus ring (`ds-atin2: color.surface.strong`) |
| | `--brand-primary-hover` | `hover:bg-brand-primary-hover` | `#0369A1` | Trạng thái hover của nút chính |
| | `--brand-deep` | `text-brand-deep` | `#0044A4` | Điểm nhấn thương hiệu ATIN đậm, link/active badge (`ds-atin1: color.text.tertiary`) |
| | `--brand-warm` | `text-brand-warm` | `#F6931D` | Điểm nhấn cam ATIN (`ds-atin1: shadow.2/3`), dùng cho chỉ báo phụ |
| | `--brand-ink` | `bg-brand-ink` | `#17233C` | Nút hành động tối màu / Header nhấn (`ds-atin1: color.text.secondary`) |
| **Chữ (Typography)** | `--text-heading` | `text-heading` | `#17233C` | Tiêu đề trang, tên Camera, con số Hero lớn (`ds-atin1: #17233C`, `ds-atin2: #1E293B`) |
| | `--text-primary` | `text-primary` | `#334155` | Văn bản nội dung chính, giá trị chỉ số (`ds-atin2: color.text.primary`) |
| | `--text-secondary` | `text-secondary` | `#4A5D80` | Nhãn phụ, tên kênh, chú thích (`ds-atin1: color.text.primary`) |
| | `--text-muted` | `text-muted` | `#64748B` | Đơn vị đo (`ms`, `frames`), placeholder, timestamp (đạt chuẩn WCAG AA `4.6:1` trên nền trắng) |
| | `--text-on-brand` | `text-on-brand` | `#FFFFFF` | Chữ trên nền `--brand-primary`, `--brand-ink` và trong HUD tối (`ds-atin2: color.text.tertiary`) |
| **Đường viền (Borders)** | `--border-default` | `border-default` | `#DDE5F1` | Viền ngoài Card, Modal, Topbar, Input (`ds-atin1 & ds-atin2: color.border.default`) |
| | `--border-muted` | `border-muted` | `#E2E8F0` | Đường kẻ chia nhỏ (hairline divider) trong thẻ (`ds-atin2: color.border.muted`) |
| | `--border-strong` | `border-strong` | `#CBD5E1` | Viền khi hover card hoặc input border nhấn (`ds-atin2: color.border.strong`) |
| **Trạng thái AI & Hệ thống (Status)** | `--status-present` | `text-status-present` / `bg-status-present` | `#22C55E` | 🟢 **CÓ NHÂN VIÊN** (`present` / `leaving`), BBox người trong vùng, chấm NVR Online |
| | `--status-empty` | `text-status-empty` / `bg-status-empty` | `#F59E0B` | 🟡 **VÙNG TRỐNG** (`empty` — đang đếm ngược `< 10s`) |
| | `--status-alert` | `text-status-alert` / `bg-status-alert` | `#EF4444` | 🔴 **KHÔNG CÓ NHÂN VIÊN** (`alert` `>= 10s`), viền khung báo động, nút Xóa/Dừng ghi hình |
| | `--status-idle` | `text-status-idle` / `bg-status-idle` | `#0284C7` | 🔵 Đang vẽ vùng (`ZoneEditor`), hoặc trạng thái chờ quét |
| | `--status-outside` | `text-status-outside` | `#94A3B8` | ⚪ BBox làm mờ (`alpha 0.42`) của nhân viên đứng ngoài vùng quy định |

---

### 2.2. Hệ Thống Chữ (Typography Scale — ATIN Monitoring × Soft Cards)

Sử dụng font **`Inter`** (`font-family: "Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`) kết hợp thang chữ nén gọn của màn hình giám sát `ds-atin2.md` (`11px / 12px / 14px / 16px`) và thang tiêu đề/con số lớn của `ds-atin1.md` & `design-system.md` (`18px / 24px / 43.2px`):

| Token Vai trò | Cỡ chữ / Line-height | Độ đậm (Weight) | Letter-spacing | Màu mặc định | Ứng dụng cụ thể trong PoC v001 |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `hero-metric` | `43.2px` (`2.7rem`) / `1.05` | `600` (SemiBold) | `-0.02em` | `--text-heading` | Số lượng frame lớn trên thẻ Dataset (`ds-atin1: font.size.lg=43.2px`) |
| `title-lg` | `24px` (`1.5rem`) / `1.2` | `600` (SemiBold) | `-0.015em` | `--text-heading` | Tiêu đề Modal lớn, tiêu đề khu vực (`ds-atin1: font.size.md=24px`) |
| `title-card` | `16px` (`1rem`) / `1.35` | `600` (SemiBold) | `-0.01em` | `--text-heading` | Tên Camera trên `CameraCard` (`Tăng trọng 1`), tên thương hiệu trên Topbar (`ds-atin2: font.size.lg=16px`) |
| `hud-title` | `15px` (`0.9375rem`) / `1.25` | `700` (Bold) | `0.01em` | `#FFFFFF` | Dòng trạng thái chính trên HUD (`CÓ NHÂN VIÊN` / `VÙNG TRỐNG` / `KHÔNG CÓ NHÂN VIÊN`) |
| `body-md` | `14px` (`0.875rem`) / `1.45` | `400` / `500` | `0` | `--text-primary` | Văn bản form, nút bấm chính, giá trị `Metric Row` (`CH 16`, `185 ms`) (`ds-atin2: font.size.md=14px`) |
| `label-sm` | `12px` (`0.75rem`) / `1.35` | `500` (Medium) | `0` | `--text-secondary` | Phụ đề thẻ Camera (`Kênh 16 · Khu vực máy tăng trọng 1`), nút Segmented, dòng phụ HUD (`ds-atin2: font.size.sm=12px`) |
| `caption-xs` | `11px` (`0.6875rem`) / `1.3` | `500` / `600` | `0.02em` | `--text-muted` | Dòng overline HUD (`GIÁM SÁT NHÂN VIÊN`), nhãn BBox Canvas, mốc thời gian Timeline (`ds-atin2: font.size.xs=11px`) |

---

### 2.3. Thang Khoảng Cách, Bo Góc, Đổ Bóng & Chuyển Động

#### Khoảng cách (Spacing Scale — hợp nhất `ds-atin1` & `ds-atin2`)
- **Micro spacing (bên trong HUD, Pill, Badge, Metric Col)**: `2px` (`space-0.5`), `4px` (`space-1`), `6px` (`space-1.5`), `8px` (`space-2`), `10px` (`space-2.5`), `12px` (`space-3`).
- **Layout spacing (bên trong Card, Grid, Modal)**: `16px` (`space-4` — padding thẻ Camera compact), `20px` (`space-5` — padding thẻ Camera tiêu chuẩn & gap lưới), `24px` (`space-6` — padding Modal & trang), `32px` (`space-8` — khoảng cách giữa các phân khu).

#### Bo góc (Border Radius)
- `--radius-xs: 4px`: Đoạn màu trên thanh Timeline 30 phút, nhãn tag BBox trên Canvas.
- `--radius-sm: 6px`: Badge nhỏ trong HUD (`ds-atin2: radius.sm=6px`).
- `--radius-md: 8px`: Input, Select, Textarea, Nút bấm tiêu chuẩn (`ds-atin2: radius.md=8px`).
- `--radius-lg: 12px`: Khung video `.viewport` bên trong thẻ, khung Segmented Control, khối HUD (`design-system.md: --radius-md`).
- `--radius-card: 20px`: Thẻ `CameraCard`, `DataCard` và `ModalCard` (kết hợp độ mềm của Soft Clean Cards với mật độ hiển thị 4–6 camera của ATIN Monitoring).
- `--radius-pill: 9999px`: Status Pill trên Topbar, nút tròn Icon Button `36×36px` (`ds-atin2: radius.xl=9999px`).

#### Đổ bóng (Elevation Shadows)
- `--shadow-card`: `0 1px 2px rgba(20, 40, 80, 0.04), 0 6px 20px rgba(20, 40, 80, 0.07)` *(kế thừa `ds-atin1: shadow.1 = rgba(20, 40, 80, 0.1) 0px 6px 20px 0px` làm dịu theo chuẩn Soft Clean Cards)*.
- `--shadow-card-hover`: `0 4px 12px rgba(20, 40, 80, 0.06), 0 12px 28px rgba(20, 40, 80, 0.10)`.
- `--shadow-control`: `0 1px 2px rgba(15, 23, 42, 0.06), 0 0 0 1px rgba(221, 229, 241, 0.7)` *(dùng cho tab đang chọn trong Segmented Control và Icon Button)*.
- `--shadow-brand`: `0 8px 24px -4px rgba(2, 132, 199, 0.35), 0 0 0 1px rgba(2, 132, 199, 0.20)` *(kế thừa nguyên bản `ds-atin2: shadow.3` cho nút Primary `#0284C7`)*.
- `--shadow-alert-ring`: `inset 0 0 0 3px #EF4444, 0 0 20px rgba(239, 68, 68, 0.35)` *(viền sáng đỏ quanh khung video khi camera ở trạng thái `alert`)*.

#### Chuyển động (Motion Tokens)
- `--duration-instant: 120ms` (`ease-out`): Hover/active của nút bấm, icon button (`ds-atin1`).
- `--duration-fast: 200ms` (`cubic-bezier(0.32, 0.72, 0, 1)`): Chuyển tab Segmented Control, mở menu Record, đổi màu trạng thái HUD (`ds-atin2`).
- `--duration-normal: 300ms` (`cubic-bezier(0.32, 0.72, 0, 1)`): Đóng/mở Modal, Toast notification (`ds-atin2`).
- Bắt buộc hỗ trợ `@media (prefers-reduced-motion: reduce)`: tắt hiệu ứng scale/slide, chỉ giữ đổi màu tức thì.

---

### 2.4. Mã Nguồn Cấu Hình `globals.css` & `tailwind.config.ts` (Copy Dùng Ngay)

#### `poc/frontend/src/app/globals.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  /* Surfaces (ATIN IOC + Soft Clean Cards) */
  --surface-page: #f1f5f9;
  --surface-card: #ffffff;
  --surface-subtle: #f8fafc;
  --surface-subtle-hover: #e2e8f0;
  --surface-video: #000000;
  --surface-hud: rgba(15, 23, 42, 0.44);

  /* Brand & Interactive */
  --brand-primary: #0284c7;
  --brand-primary-hover: #0369a1;
  --brand-deep: #0044a4;
  --brand-warm: #f6931d;
  --brand-ink: #17233c;

  /* Typography */
  --text-heading: #17233c;
  --text-primary: #334155;
  --text-secondary: #4a5d80;
  --text-muted: #64748b;
  --text-on-brand: #ffffff;

  /* Borders */
  --border-default: #dde5f1;
  --border-muted: #e2e8f0;
  --border-strong: #cbd5e1;

  /* AI & System Semantic Status */
  --status-present: #22c55e;
  --status-empty: #f59e0b;
  --status-alert: #ef4444;
  --status-idle: #0284c7;
  --status-outside: #94a3b8;

  /* Radius */
  --radius-xs: 4px;
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-card: 20px;
  --radius-pill: 9999px;

  /* Shadows */
  --shadow-card: 0 1px 2px rgba(20, 40, 80, 0.04), 0 6px 20px rgba(20, 40, 80, 0.07);
  --shadow-card-hover: 0 4px 12px rgba(20, 40, 80, 0.06), 0 12px 28px rgba(20, 40, 80, 0.10);
  --shadow-control: 0 1px 2px rgba(15, 23, 42, 0.06), 0 0 0 1px rgba(221, 229, 241, 0.75);
  --shadow-brand: 0 8px 24px -4px rgba(2, 132, 199, 0.35), 0 0 0 1px rgba(2, 132, 199, 0.20);
}

@layer base {
  body {
    background: linear-gradient(180deg, #f8fafc 0%, var(--surface-page) 100%);
    color: var(--text-primary);
    font-family: "Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 14px;
    line-height: 1.45;
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum" 1, "cv11" 1;
    -webkit-font-smoothing: antialiased;
    min-height: 100vh;
  }

  /* WCAG 2.2 AA Focus Visible Rule */
  *:focus-visible {
    outline: 2px solid var(--brand-primary);
    outline-offset: 2px;
  }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

#### `poc/frontend/tailwind.config.ts`:
```typescript
import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          page: 'var(--surface-page)',
          card: 'var(--surface-card)',
          subtle: 'var(--surface-subtle)',
          'subtle-hover': 'var(--surface-subtle-hover)',
          video: 'var(--surface-video)',
          hud: 'var(--surface-hud)',
        },
        brand: {
          primary: 'var(--brand-primary)',
          'primary-hover': 'var(--brand-primary-hover)',
          deep: 'var(--brand-deep)',
          warm: 'var(--brand-warm)',
          ink: 'var(--brand-ink)',
        },
        content: {
          heading: 'var(--text-heading)',
          primary: 'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          muted: 'var(--text-muted)',
          'on-brand': 'var(--text-on-brand)',
        },
        line: {
          DEFAULT: 'var(--border-default)',
          muted: 'var(--border-muted)',
          strong: 'var(--border-strong)',
        },
        status: {
          present: 'var(--status-present)',
          empty: 'var(--status-empty)',
          alert: 'var(--status-alert)',
          idle: 'var(--status-idle)',
          outside: 'var(--status-outside)',
        },
      },
      borderRadius: {
        xs: 'var(--radius-xs)',
        sm: 'var(--radius-sm)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
        card: 'var(--radius-card)',
        pill: 'var(--radius-pill)',
      },
      boxShadow: {
        card: 'var(--shadow-card)',
        'card-hover': 'var(--shadow-card-hover)',
        control: 'var(--shadow-control)',
        brand: 'var(--shadow-brand)',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
    },
  },
  plugins: [],
};

export default config;
```

---

## 3. Quy Tắc Chi Tiết Cấp Độ Component (Component-Level Rules)

Theo yêu cầu của `ds-atin1.md` & `ds-atin2.md`, mọi component phải định nghĩa rõ **Anatomy (Cấu tạo)**, **Variants (Biến thể)**, **7 States (`default`, `hover`, `focus-visible`, `active`, `disabled`, `loading`, `error`)**, **Tương tác Bàn phím / Chuột / Cảm ứng**, và **Xử lý tràn chữ / Trạng thái rỗng**.

### 3.1. Ma Trận 7 Trạng Thái Chuẩn Cho Mọi Nút Bấm & Điều Khiển (`Button`, `IconButton`, `SegmentedTab`, `Input`)

| Trạng thái (State) | Quy tắc hiển thị bắt buộc (Token-driven) |
| :--- | :--- |
| **1. `default`** | Hiển thị nền, chữ và viền đúng variant: Primary (`bg-brand-primary text-white shadow-brand`), Subtle/Ghost (`bg-surface-subtle text-content-primary border border-line`), Danger (`bg-status-alert/10 text-status-alert border border-status-alert/30`), IconButton (`w-9 h-9 rounded-pill bg-surface-card border border-line shadow-control text-content-secondary`). |
| **2. `hover`** | Chuyển mượt trong `120ms`: Primary → `bg-brand-primary-hover`; Subtle → `bg-surface-subtle-hover border-line-strong text-content-heading`; IconButton → `bg-surface-subtle text-content-heading border-line-strong`. Con trỏ luôn là `cursor-pointer`. |
| **3. `focus-visible`** | Hiển thị vòng focus rõ ràng `outline: 2px solid var(--brand-primary); outline-offset: 2px`. Tuyệt đối không dùng `outline-none` mà không có `focus-visible:ring-2`. |
| **4. `active`** | Thu nhẹ `active:scale-[0.97]` trong `120ms` để tạo phản hồi xúc giác rõ rệt khi click chuột hoặc chạm màn hình cảm ứng. |
| **5. `disabled`** | `opacity-50 cursor-not-allowed pointer-events-none`, bỏ `shadow-brand`. Thuộc tính HTML `disabled={true}` và `aria-disabled="true"`. |
| **6. `loading`** | Khóa click (`disabled={true}`), hiển thị icon `<Loader2 className="w-4 h-4 animate-spin" />` bên trái nhãn chữ đổi sang trạng thái đang thực thi (VD: `"Đang lưu..."`, `"Đang tách..."`, `"Đang kết nối..."`). |
| **7. `error`** | Với Input/Textarea: viền chuyển sang `border-status-alert ring-1 ring-status-alert/30`, hiển thị dòng thông báo lỗi `text-[12px] text-status-alert mt-1` ngay bên dưới trường bị lỗi. Với Button/Action: bật Toast báo lỗi màu đỏ kèm nội dung cụ thể từ API. |

---

### 3.2. Đặc Tả 6 Component Cốt Lõi Của Trang Giám Sát

#### A. Thanh Điều Hướng Đỉnh (`<Topbar />`)
- **Anatomy**:
  - Chiều cao tối thiểu `64px`, nền `bg-surface-card/90 backdrop-blur-md border-b border-line sticky top-0 z-30`.
  - **Cụm Trái**: Tên hệ thống **`ATIN Smart Fishing`** (`text-[16px] font-semibold text-content-heading`) + phụ đề `Giám sát AI nhà máy thủy sản` (`text-[12px] text-content-secondary`) + **NVR Status Pill** (`rounded-pill px-3 py-1 bg-surface-subtle border border-line text-[12px]` với chấm tròn `8px` màu `--status-present` khi online, `--status-alert` khi offline).
  - **Cụm Phải**:
    - `Segmented Control` chuyển trang (`Live view` | `Video & Tách frame`).
    - `Global Recording Pill` (chỉ hiện khi có camera đang ghi hình: nền đỏ nhạt `bg-status-alert/10 text-status-alert border border-status-alert/30 rounded-pill px-3 py-1 text-[12px] font-medium` kèm chấm đỏ nhấp nháy).
    - Cụm công cụ Live View: `Segmented Control` chọn lưới `1 | 4 | 6`, nút `Làm mới`, nút `Bài toán AI`, nút chính `Thêm camera` (`bg-brand-primary text-white shadow-brand`).
- **Keyboard & Touch**:
  - Các nhóm `Segmented Control` bắt buộc có `role="tablist"`, mỗi nút con có `role="tab"` và `aria-selected="true|false"`, hỗ trợ phím `Tab` và `Enter/Space`.
  - Vùng chạm cảm ứng tối thiểu đạt `44×44px` (hoặc chiều cao nút `>= 36px` với khoảng cách giữa các nút `>= 8px`).

#### B. Thẻ Camera Giám Sát (`<CameraCard />`)
- **Anatomy (4 tầng dọc chuẩn Soft Clean Cards × ATIN Monitoring)**:
  ```text
  ┌─────────────────────────────────────────────────────────────────┐
  │ 1. Header: Tên Camera (16px SemiBold) + Phụ đề Kênh/Vị trí (12px)│
  │            [Phóng to] [Vẽ vùng] [Tải snapshot] [Cài đặt]        │
  ├─────────────────────────────────────────────────────────────────┤
  │ 2. ZoneEditor Toolbar (Chỉ hiện khi đang bật chế độ Vẽ vùng)     │
  ├─────────────────────────────────────────────────────────────────┤
  │ 3. Viewport (16:9, nền #000000, radius 12px, overflow-hidden):  │
  │    - Lớp 1: <img class="vid-stream"> (MJPEG RAM-Stream)         │
  │    - Lớp 2: <img class="zone-bg"> (Snapshot tĩnh khi vẽ vùng)   │
  │    - Lớp 3: <ZoneHudOverlay /> (Góc trên-trái, 3 màu + Timeline)│
  │    - Lớp 4: <CameraOverlayCanvas /> (HiDPI Polygon + BBox 15FPS)│
  │    - Lớp 5: Stream Badge góc trên-phải (chỉ hiển thị khi tạm dừng hoặc `connecting`/`error`; ẩn `"Trực tiếp"` lúc live bình thường để giữ khung hình sạch)│
  ├─────────────────────────────────────────────────────────────────┤
  │ 4. Metric Row (3 cột thoáng, không vách ngăn dọc):               │
  │    Kênh: CH 16     | Luồng: MJPEG · Chính | Độ trễ: 142 ms      │
  └─────────────────────────────────────────────────────────────────┘
  ```
- **Styles & States của Card**:
  - Khung ngoài: `bg-surface-card border border-line rounded-card p-4 md:p-5 shadow-card transition-shadow duration-200 hover:shadow-card-hover flex flex-col gap-3.5`.
  - **Khi `detection.status === 'alert'` (`ui_color === 'red'`)**:
    - Khung `.viewport` bật viền cảnh báo đỏ rực: `ring-[3px] ring-status-alert shadow-[0_0_20px_rgba(239,68,68,0.35)]`.
    - Viền ngoài của thẻ `CameraCard` chuyển sang `border-status-alert/60`.
  - **Xử lý tràn chữ (Long-content & Overflow)**:
    - Tên camera và phụ đề bắt buộc dùng `truncate` (`white-space: nowrap; overflow: hidden; text-overflow: ellipsis`) kèm thuộc tính `title={cam.name}` để không làm vỡ chiều cao header trên lưới 4 hoặc 6 camera.
  - **Xử lý mất kết nối video (`error` state của Viewport)**:
    - Hiển thị lớp phủ tối `bg-slate-950/85` chính giữa `.viewport` với icon `<VideoOff className="w-6 h-6 text-slate-400" />`, thông báo `"Không thể kết nối luồng video từ kênh CH {cam.channel}"` và nút `"Thử kết nối lại"`.

#### C. Khối HUD Trạng Thái AI & Dòng Thời Gian 30 Phút (`<ZoneHudOverlay />`)
- **Anatomy (Khớp 100% với 3 ảnh mẫu `CoNhanVien.jpg`, `VungTrong.jpg`, `KhongCoNhanVien.jpg`)**:
  - Đặt tại `top-3 left-3 z-10 max-w-[340px] pointer-events-none select-none`.
  - Khung kính mờ tối: `bg-surface-hud backdrop-blur-md rounded-lg px-3.5 py-2.5 text-white border border-white/10 shadow-lg relative overflow-hidden`.
  - **Thanh vạch màu dọc bên trái (`4px`)**: `absolute left-0 top-0 bottom-0 w-1` đổi màu theo `ui_color`:
    - `green`: `bg-[#22C55E]`
    - `yellow`: `bg-[#F59E0B]`
    - `red`: `bg-[#EF4444]`
    - `idle`: `bg-[#0284C7]`
  - **5 Dòng thông tin bên trong**:
    1. **Dòng 1 (Overline)**: `text-[10px] font-semibold tracking-wider uppercase text-slate-300` → `GIÁM SÁT NHÂN VIÊN · {TÊN VÙNG}`
    2. **Dòng 2 (Status Row)**: Chấm tròn `w-2.5 h-2.5 rounded-full` (cùng màu `ui_color`) + Nhãn chính `text-[15px] font-bold tracking-tight text-white` (`CÓ NHÂN VIÊN` | `VÙNG TRỐNG` | `KHÔNG CÓ NHÂN VIÊN`).
    3. **Dòng 3 (Sub-label)**: `text-[12px] font-medium` (màu `#86EFAC` khi xanh, `#FDE68A` khi vàng, `#FCA5A5` khi đỏ) → `1 người trong vùng` | `Vừa rời khỏi vùng` | `không có người 00:02` | `Cảnh báo · vùng trống 00:12`.
    4. **Dòng 4 (KPI Thống kê)**: `text-[11px] text-slate-300 pt-1 border-t border-white/10` → `Tổng thời gian cảnh báo: {MM:SS} · Số lần cảnh báo: {N}`.
    5. **Dòng 5 (Rolling Timeline 30p)**:
       - Header nhỏ: `Dòng thời gian (30p gần nhất)` bên trái + thời lượng phiên `{MM:SS}` bên phải (`text-[10px] text-slate-400`).
       - Thanh ngang `h-1.5 w-full bg-slate-800 rounded-xs overflow-hidden flex gap-[1px] mt-1`: render các đoạn `segment` với `backgroundColor` tương ứng (`#22C55E`, `#F59E0B`, `#EF4444`) và `width: ${pct}%`.
- **Responsive / Compact Mode**:
  - Khi xem ở lưới **6 camera** trên màn hình nhỏ (`compact={true}`): thu gọn nhẹ padding (`px-2.5 py-2`) và cỡ chữ tiêu đề HUD xuống `13px` để không che khuất vùng làm việc của công nhân.
  - Khi xem ở lưới **1 camera** hoặc trong **Focus Modal** (`compact={false}`): hiển thị đầy đủ cả 5 dòng với kích thước chuẩn.

#### D. Lớp Vẽ Đồ Họa AI Trên Video (`<CameraOverlayCanvas />`)
- **Quy tắc màu và nét vẽ trên Canvas HiDPI (`devicePixelRatio`)**:
  - **Đa giác vùng giám sát (`zone`)**:
    - Đường viền `lineWidth = 2.5`, màu theo `ui_color` (`#22C55E` / `#F59E0B` / `#EF4444` / `#0284C7`).
    - Màu tô bên trong (fill): cùng màu `ui_color` với độ trong suốt `alpha = 0.14` (`0.18` khi `red`).
    - Đỉnh đa giác: chấm tròn bán kính `3.5px`, nền `#FFFFFF`, viền `2px` màu `ui_color`.
    - **Polygon Tag Pill** tại đỉnh cao nhất: khung chữ nhật bo góc `4px`, nền màu `ui_color`, chữ trắng `600 11px Inter`, nội dung `{TÊN VÙNG} · {TRẠNG THÁI NGẮN}`.
  - **Bounding Box Nhân Viên**:
    - **Trong vùng (`in_zone === true`)**: Viền `#22C55E` dày `2px`; nhãn pill nền `#16A34A` chữ `#FFFFFF` (`600 11px Inter`) hiển thị độ tin cậy `{conf}%`.
    - **Ngoài vùng (`in_zone === false`)**: Đặt `ctx.globalAlpha = 0.42`, viền `#94A3B8` dày `1.25px`, nhãn nhỏ nền `#334155` chữ trắng ghi `{conf}%`. Không vẽ chấm tròn anchor.

#### E. Hộp Thoại Phóng To (`<FocusModal />`) & Hộp Thoại Cài Đặt (`<CameraFormModal />`)
- **FocusModal**: Chế độ xem toàn màn hình (`requestFullscreen()` với fallback viewport `w-screen h-screen bg-black`), khung 16:9 tối giản chỉ gồm video (`subtype=0&view=focus`), `CameraOverlayCanvas`, `ZoneHudOverlay`, nút đóng `X` và phím `Esc`.
- **CameraFormModal**:
  - Lớp nền mờ: `fixed inset-0 z-50 bg-slate-900/55 backdrop-blur-xs flex items-center justify-center p-4`.
  - Thẻ Modal: `bg-surface-card border border-line rounded-card shadow-2xl w-full max-w-lg max-h-[92vh] flex flex-col overflow-hidden`.
- **Keyboard & Pointer**:
  - Nhấn phím `Escape` hoặc click vào vùng nền mờ bên ngoài thẻ để đóng Modal.
  - Mọi ô `<input>`, `<select>`, `<textarea>` trong `CameraFormModal` bắt buộc nằm trong thẻ `<label>` rõ ràng với nhãn tiếng Việt phía trên (`text-[12px] font-medium text-content-secondary mb-1.5`), chiều cao ô nhập `h-10 px-3 rounded-md border border-line bg-surface-subtle text-content-heading focus:bg-white focus:border-brand-primary`.

#### F. Trang Quản Lý Video & Tách Bộ Frame (`<DatasetView />`)
- **Áp dụng triệt để Hero Metric của Soft Clean Cards + ATIN Tokens**:
  - Mỗi thẻ bộ frame (`FrameSetCard`) lấy **tổng số lượng frame** làm nhân vật chính: con số `43.2px` (`text-[43px] font-semibold leading-none tracking-tight text-content-heading tabular-nums`) đi kèm đơn vị `frames` (`text-[13px] font-medium text-content-muted ml-1.5`).
  - Dải ảnh thumbnail (`thumb-strip`): lưới 4 ảnh vuông bo góc `8px` (`aspect-video object-cover rounded-md border border-line-muted bg-slate-900`), có `loading="lazy"`.
  - **Empty State**: Khi chưa có video hoặc chưa có bộ frame nào được tách, hiển thị khung `bg-surface-card border border-dashed border-line-strong rounded-card p-8 text-center text-content-secondary` với hướng dẫn cụ thể bằng tiếng Việt.

---

## 4. Yêu Cầu Truy Cập & Tiêu Chí Nghiệm Thu WCAG 2.2 AA (Testable Acceptance Criteria)

Mọi tiêu chí dưới đây đều có thể kiểm tra trực tiếp bằng công cụ DevTools / Keyboard test (Pass / Fail):

| Mã | Hạng mục WCAG 2.2 AA | Tiêu chí kiểm thử thực tế (Pass / Fail Check) |
| :-: | :--- | :--- |
| **A01** | **Độ tương phản chữ (1.4.3 Contrast Minimum)** | **PASS** khi: Chữ chính (`#17233C`, `#334155`) trên nền trắng `#FFFFFF` hoặc `#F8FAFC` đạt tỷ lệ tương phản `>= 9.5:1`; chữ phụ (`#4A5D80`, `#64748B`) trên nền trắng đạt `>= 4.6:1`; chữ trắng `#FFFFFF` trên nền HUD `rgba(15, 23, 42, 0.82)` đạt `>= 12:1`. **FAIL** nếu dùng chữ xám nhạt `< #767676` trên nền trắng cho thông tin nghiệp vụ. |
| **A02** | **Không dùng màu sắc làm kênh duy nhất (1.4.1 Use of Color)** | **PASS** khi: Cả 3 trạng thái AI trên HUD đều đi kèm **nhãn chữ tiếng Việt tường minh** (`CÓ NHÂN VIÊN` / `VÙNG TRỐNG` / `KHÔNG CÓ NHÂN VIÊN`) và bộ đếm thời gian `MM:SS`, đồng thời BBox người ngoài vùng vừa được làm mờ vừa có nhãn khác biệt (`#ID` so với `Nhân viên #ID`). |
| **A03** | **Điều hướng bàn phím & Vòng Focus (2.1.1 & 2.4.7 Focus Visible)** | **PASS** khi: Nhấn phím `Tab` đi qua toàn bộ nút trên Topbar, các nút trên `CameraCard` và các trường trong Modal theo thứ tự logic từ trái sang phải, từ trên xuống dưới; phần tử đang focus luôn hiện viền xanh `#0284C7` dày `2px`. Nhấn `Escape` đóng được Modal hoặc thoát chế độ Vẽ vùng (`ZoneEditor`). |
| **A04** | **Kích thước vùng chạm (2.5.8 Target Size Minimum)** | **PASS** khi: Mọi nút bấm (`Button`, `IconButton`, `SegmentedTab`) có diện tích tương tác tối thiểu `36×36px` (với khoảng cách tới nút kế bên `>= 8px`, hoặc đạt vùng chạm `44×44px`). |
| **A05** | **Nhãn ARIA & Ngữ nghĩa HTML (4.1.2 Name, Role, Value)** | **PASS** khi: Mọi nút chỉ có icon (`Phóng to`, `Vẽ vùng`, `Tải ảnh`, `Cài đặt`, `Xóa`, `Đóng`) đều có thuộc tính `aria-label` và `title` tiếng Việt mô tả chính xác kèm tên camera (VD: `aria-label="Vẽ vùng giám sát Tăng trọng 1"`). Các Modal có `role="dialog"` và `aria-modal="true"`. |

---

## 5. Chuẩn Ngôn Ngữ & Giọng Văn Giao Diện (Content & Tone Standards)

Giao diện dành cho cán bộ vận hành nhà máy thủy sản Trần Hân và kỹ thuật viên ATIN, sử dụng **tiếng Việt ngắn gọn, chính xác, hướng hành động**:

- **Viết hoa chữ cái đầu câu (Sentence case)** cho toàn bộ nút bấm, nhãn form, tiêu đề cột. Chỉ viết HOA toàn bộ cho:
  1. Dòng trạng thái chính trong HUD (`CÓ NHÂN VIÊN`, `VÙNG TRỐNG`, `KHÔNG CÓ NHÂN VIÊN`) để đọc được từ khoảng cách xa trước màn hình giám sát.
  2. Dòng overline nhỏ trong HUD (`GIÁM SÁT NHÂN VIÊN · VÙNG MÁY TRỘN`) và nhãn kênh (`CH 16`).
- **Bảng đối chiếu nhãn chuẩn (Nên dùng vs Cấm dùng)**:

| Tình huống | ✅ Chuẩn sử dụng (Do) | ❌ Cấm sử dụng (Don't) |
| :--- | :--- | :--- |
| Lưu cấu hình camera / vùng | `Lưu thay đổi` / `Lưu vùng` | `Submit` / `OK` / `Gửi đi` |
| Xóa vùng đang vẽ | `Xóa vùng` / `Hoàn tác` | `Clear` / `Reset` (dễ nhầm với Reset thống kê) |
| Đặt lại bộ đếm cảnh báo AI | `Reset thống kê` | `Xóa dữ liệu` |
| Trạng thái luồng camera | `Trực tiếp` / `Đang kết nối` / `Mất tín hiệu` | `Online` / `Connecting...` / `Error 502` |
| Đơn vị số liệu | `185 ms`, `500 frames`, `02:37` | `185ミリ秒`, `500fr`, `157s` |

---

## 6. Các Mẫu Cấm Kỵ (Anti-Patterns & Prohibited Implementations)

Hydrogen / Neon **tuyệt đối không** được mắc các lỗi thiết kế và cài đặt sau:

1. ❌ **Cấm đưa tọa độ `persons[]` 15 FPS vào `useState` của React**: Gây re-render toàn bộ cây DOM 15 lần/giây làm đơ trình duyệt. Bắt buộc vẽ BBox qua `<CameraOverlayCanvas />` với `requestAnimationFrame` + `detectionStore`.
2. ❌ **Cấm dùng nền sáng hoặc chữ tối cho khối HUD đè lên video**: Video nhà máy có nhiều vùng sáng/tối phức tạp; HUD bắt buộc dùng nền kính tối `rgba(15, 23, 42, 0.82)` + chữ trắng.
3. ❌ **Cấm dùng viền đen đậm hoặc bóng đổ đen đặc cho Card**: Luôn dùng viền `--border-default` (`#DDE5F1`) `1px` và bóng `--shadow-card` pha sắc xanh navy nhẹ của ATIN.
4. ❌ **Cấm nhồi thẻ lồng trong thẻ (Card-in-Card)**: Không đặt một `.card` có đổ bóng và viền nổi bên trong một `.card` khác; chỉ dùng vùng nền phụ `--surface-subtle` (`#F8FAFC`) để gom nhóm thông tin bên trong thẻ.
5. ❌ **Cấm dùng Emoji (`🟢`, `🔴`, `📹`, `🗑️`) trong giao diện HTML/TSX**: Bắt buộc dùng chấm tròn CSS (`rounded-full`) hoặc SVG icon từ `lucide-react`.
6. ❌ **Cấm tạo thanh cuộn ngang (`horizontal scrollbar`) ở bất kỳ độ phân giải nào** từ `375px` (Mobile) đến `1920px` (Màn hình giám sát lớn).

---

## 7. Checklist Kiểm Tra Chất Lượng Giao Diện (UI/UX QA Checklist)

Trước khi đóng gói bản build `poc/frontend/out/`, **Hydrogen / Neon** phải kiểm tra và tích chọn toàn bộ danh sách này:

- [ ] **Hệ màu ATIN IOC × Soft Cards**: Nền trang `#F1F5F9` → `#F8FAFC`, thẻ trắng `#FFFFFF`, viền `#DDE5F1`, nút chính `#0284C7` có bóng `--shadow-brand`, tiêu đề `#17233C`, khung video `#000000`.
- [ ] **HUD 3 Màu & Timeline 30 Phút**: Khớp 100% bố cục 5 dòng của 3 ảnh mẫu (`CoNhanVien.jpg`, `VungTrong.jpg`, `KhongCoNhanVien.jpg`); khi sang trạng thái `alert` (`red`), khung `.viewport` bật viền sáng đỏ `3px`.
- [ ] **BBox Trong Vùng vs Ngoài Vùng**: Người trong vùng vẽ xanh lá `#22C55E` (`Nhân viên #ID` + chấm chân trắng-xanh); người ngoài vùng làm mờ `globalAlpha = 0.42` màu `#94A3B8` (`#ID`).
- [ ] **Chống nhảy chữ (`tabular-nums`)**: Bộ đếm giây `00:01 → 00:12`, độ trễ `ms` và đồng hồ ghi hình không bị giật ngang khi đổi số.
- [ ] **Đủ 7 Trạng thái Component**: Các nút bấm, ô nhập liệu và khung video đã xử lý đầy đủ `default`, `hover`, `focus-visible`, `active`, `disabled`, `loading`, `error`.
- [ ] **Đạt chuẩn WCAG 2.2 AA**: Mọi nút icon đều có `aria-label` + `title`; nhấn `Tab` hiện vòng focus `#0284C7`; nhấn `Escape` đóng được Modal và ZoneEditor.

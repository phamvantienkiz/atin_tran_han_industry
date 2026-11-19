# PoC v001 — Nhật Ký Sự Cố, Nguyên Nhân Gốc & Cách Xử Lý (`issuse.md`)

> **Phạm vi**: Ghi nhận đầy đủ toàn bộ các lỗi và vấn đề thực tế phát sinh từ lúc bắt đầu code PoC v001 ở local Windows cho đến khi triển khai chạy thật trên server GPU **`aiot` (`192.168.1.170`, Ubuntu 22.04.5 LTS, RTX A400 4GB VRAM, Public Port `28080`)**.  
> **Mục đích**: Làm tài liệu đối chiếu kỹ thuật (Post-mortem / Lessons Learned) để tránh lặp lại cùng một lỗi khi mở rộng dự án hoặc triển khai sang server mới.

---

## Bảng Tổng Hợp Nhanh

| Mã | Giai đoạn | Tóm tắt sự cố | Commit / File sửa | Trạng thái |
| :-: | :--- | :--- | :--- | :-: |
| **ISS-01** | Code Backend | `supervision==0.32.0` đã gỡ bỏ `sv.ByteTrack` (`AttributeError`) | `c272b35` · `poc/backend/pyproject.toml` | Đã fix |
| **ISS-02** | Test Backend | Trôi mốc `yellow_since` trong `ZoneRuleEngine` khi trễ khung hình | `c272b35` · `poc/backend/app/ai/rule_engine.py` | Đã fix |
| **ISS-03** | Build Frontend | Tailwind v3 lỗi `bg-status-alert/10` khi dùng CSS Variable Hex | `c272b35` · `globals.css`, `tailwind.config.ts` | Đã fix |
| **ISS-04** | Setup `aiot` | `apt install nodejs` cài nhầm Node v12 + màn hình hồng `needrestart` ngắt `setup_20.x` | `b213b7c` · `poc/docs/deploy.md` | Đã fix |
| **ISS-05** | Run trên `aiot` | Biến `FRONTEND_DIR` trong `.env` ghi đè biến `FRONTEND_DIR` của `run_server.sh` | `b213b7c` · `poc/backend/scripts/run_server.sh` | Đã fix |
| **ISS-06** | Git trên `aiot` | `chmod +x run_server.sh` gây conflict khi `git pull` & mất quyền `+x` sau pull | Cấu hình `core.fileMode false` trên `aiot` | Đã fix |
| **ISS-07** | Build trên `aiot` | `.gitignore` gốc có `lib/` làm Git bỏ sót toàn bộ `poc/frontend/src/lib/` | `a3519a2` · `.gitignore`, `poc/frontend/src/lib/*` | Đã fix |
| **ISS-08** | AI Core `aiot` | Convert `yolo26s_best.onnx` → FP16 lỗi kiểu dữ liệu tại node `Resize` | `4490461` · `convert_onnx_fp16.py`, `detector.py` | Đã fix |
| **ISS-09** | GPU CUDA `aiot` | `onnxruntime-gpu==1.32.0` đòi CUDA 13 (`libcublasLt.so.13`), fallback về CPU | `ec17460` · `pyproject.toml`, `run_server.sh` | Đã fix |
| **ISS-10** | Vận hành `aiot` | `*.onnx` bị `.gitignore` chặn khi push & lỗi xuống dòng khi paste lệnh dài | `poc/docs/deploy.md` | Đã ghi nhận |

---

## Chi Tiết Từng Vấn Đề & Giải Pháp Đã Áp Dụng

### ISS-01: `supervision==0.32.0` gỡ bỏ `sv.ByteTrack`
- **Giai đoạn**: Cài đặt dependency Backend trong `poc/backend/.venv`.
- **Log / Hiện tượng**:
  ```text
  AttributeError: module 'supervision' has no attribute 'ByteTrack'
  ```
  Kèm theo nhiều cảnh báo `FutureWarning: template_mgs is deprecated since v0.12`.
- **Nguyên nhân gốc**: `pyproject.toml` khai báo `"supervision>=0.25.0"` không giới hạn phiên bản trần, nên `uv` tự tải bản mới nhất `0.32.0` (từ bản `>=0.28.0`, Roboflow đã gỡ `ByteTrack` khỏi namespace `supervision`).
- **Cách fix**: Ghim phiên bản tương thích `"supervision>=0.25.0,<0.28.0"` trong [pyproject.toml](file:///e:/ATIN/atin_tran_han_industry/poc/backend/pyproject.toml#L15) (cài chuẩn `supervision==0.27.0.post2`, có đủ `sv.ByteTrack` và không có cảnh báo).

---

### ISS-02: Trôi mốc `yellow_since` trong `ZoneRuleEngine` khi trễ khung hình
- **Giai đoạn**: Chạy unit test State Machine 4 trạng thái (`tests/services/test_rule_engine_presence.py`).
- **Hiện tượng**: Khi giả lập camera mất frame hoặc nhảy thời gian lớn (ví dụ từ trạng thái `leaving` ở `t=502.5s` nhảy thẳng sang `t=2500.0s`), `ev_late.timeline[-1]["color"]` vẫn là `'yellow'` thay vì `'red'` (`alert`).
- **Nguyên nhân gốc**: Ở nhánh chuyển `leaving -> empty`, code ban đầu gán `state.yellow_since = ts` (thời điểm hiện tại) thay vì `state.empty_since + grace_seconds`. Do đó toàn bộ thời gian đã trống trước đó bị tính lại từ `0s`, làm trễ mốc báo đỏ `10s`.
- **Cách fix**: Sửa thành `state.yellow_since = state.empty_since + grace_seconds` trong [rule_engine.py](file:///e:/ATIN/atin_tran_han_industry/poc/backend/app/ai/rule_engine.py#L247-L249). Mốc chuyển từ xanh → vàng (`00:02`) → đỏ (`00:12`) trở nên chính xác tuyệt đối bất kể jitter khung hình.

---

### ISS-03: Tailwind CSS v3 lỗi biên dịch khi dùng opacity modifier trên CSS Variable Hex
- **Giai đoạn**: Chạy `npm run build` tại `poc/frontend/`.
- **Log / Hiện tượng**:
  ```text
  Syntax error: ./src/app/globals.css The `bg-status-alert/10` class does not exist.
  ```
- **Nguyên nhân gốc**: `tailwind.config.ts` khai báo màu bằng `'var(--status-alert)'` (giá trị hex `#ef4444`). Tailwind CSS v3 không thể áp dụng opacity modifier (`/10`, `/20`, `/30`, `/60`, `/90`) lên biến CSS dạng hex.
- **Cách fix**:
  - Giữ nguyên toàn bộ biến hex gốc trong [globals.css](file:///e:/ATIN/atin_tran_han_industry/poc/frontend/src/app/globals.css#L5-L56) (đảm bảo 100% chuẩn [04_DESIGN_SYSTEM.md](file:///e:/ATIN/atin_tran_han_industry/poc/docs/pocv001/04_DESIGN_SYSTEM.md)), đồng thời bổ sung cặp biến kênh RGB (`--status-alert-rgb: 239 68 68`, ...).
  - Cấu hình [tailwind.config.ts](file:///e:/ATIN/atin_tran_han_industry/poc/frontend/tailwind.config.ts#L3-L45) dùng `rgb(var(--...-rgb) / <alpha-value>)`.

---

### ISS-04: Cài nhầm Node.js v12 trên Ubuntu 22.04 & màn hình hồng `needrestart`
- **Giai đoạn**: Cài Node.js runtime trên server `aiot`.
- **Log / Hiện tượng**:
  - Chạy `sudo apt-get install -y nodejs` trực tiếp cài bản mặc định của Ubuntu 22.04 là **`v12.22.9`** và không có `npm` (Next.js 15 yêu cầu Node `>= 18.18`).
  - Khi chạy `curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -`, công cụ `needrestart` của Ubuntu hiện màn hình màu hồng yêu cầu chọn dịch vụ restart; bấm `Esc` làm gián đoạn quá trình thiết lập kho NodeSource 20.x nên `node -v` vẫn giữ `v12.22.9`.
- **Cách fix**: Export 2 biến môi trường tắt giao diện tương tác `needrestart` và cài sạch NodeSource 20 LTS:
  ```bash
  export NEEDRESTART_MODE=l
  export DEBIAN_FRONTEND=noninteractive
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo -E apt-get purge -y nodejs libnode72 nodejs-doc
  sudo -E apt-get install -y nodejs
  hash -r
  node -v && npm -v   # Kết quả: v20.20.2 & 10.8.2
  ```
  Đã cập nhật quy trình chuẩn này vào [deploy.md](file:///e:/ATIN/atin_tran_han_industry/poc/docs/deploy.md#L72-L95).

---

### ISS-05: Biến `FRONTEND_DIR` trong `.env` ghi đè biến `FRONTEND_DIR` của `run_server.sh`
- **Giai đoạn**: Chạy `./scripts/run_server.sh --build` lần đầu trên `aiot`.
- **Log / Hiện tượng**:
  ```text
  [1/2] Đang build giao diện Next.js Static Export (poc/frontend/out)...
  ./scripts/run_server.sh: line 25: cd: ../frontend/out: No such file or directory
  ```
- **Nguyên nhân gốc**: Script khai báo `FRONTEND_DIR="$(cd "${BACKEND_DIR}/../frontend" && pwd)"`, nhưng ngay sau đó lệnh `source "${BACKEND_DIR}/.env"` nạp biến `FRONTEND_DIR=../frontend/out` (dành cho FastAPI `Settings`), vô tình ghi đè biến của bash script trước khi chạy `npm run build`.
- **Cách fix**: Đổi tên biến nội bộ trong [run_server.sh](file:///e:/ATIN/atin_tran_han_industry/poc/backend/scripts/run_server.sh#L6-L27) thành `FRONTEND_SRC_DIR` để tách biệt hoàn toàn với biến `FRONTEND_DIR` trong `.env` (Commit `b213b7c`).

---

### ISS-06: Xung đột quyền thực thi (`chmod +x`) của `run_server.sh` khi `git pull`
- **Giai đoạn**: Pull bản sửa lỗi từ GitHub xuống `aiot`.
- **Log / Hiện tượng**:
  ```text
  error: Your local changes to the following files would be overwritten by merge:
          poc/backend/scripts/run_server.sh
  ```
  Và sau khi pull xong, chạy `./scripts/run_server.sh` báo `-bash: ./scripts/run_server.sh: Permission denied`.
- **Nguyên nhân gốc**: File được commit từ Windows nên Git lưu file mode `644`. Trên Linux, chạy `chmod +x` làm đổi mode sang `755`, khiến Git coi là thay đổi cục bộ; khi pull bản mới về, Git đặt lại mode `644`.
- **Cách fix**:
  - Trên `aiot`: chạy `git config core.fileMode false` để Git không báo conflict vì `chmod +x`.
  - Sau khi pull file script mới, chạy `chmod +x scripts/run_server.sh` (hoặc về lâu dài set `git update-index --chmod=+x poc/backend/scripts/run_server.sh` trực tiếp trong Git).

---

### ISS-07: `.gitignore` gốc chứa `lib/` làm Git bỏ sót toàn bộ `poc/frontend/src/lib/`
- **Giai đoạn**: Build Next.js trên `aiot` bằng `./scripts/run_server.sh --build`.
- **Log / Hiện tượng**:
  ```text
  ./src/app/page.tsx
  Module not found: Can't resolve '@/lib/api'
  Module not found: Can't resolve '@/lib/ws-client'
  ./src/components/CameraFormModal.tsx
  Module not found: Can't resolve '@/lib/zone-utils'
  ```
- **Nguyên nhân gốc**: File [.gitignore](file:///e:/ATIN/atin_tran_han_industry/.gitignore#L17-L19) gốc của repo (theo mẫu Python) có dòng **`lib/`**, nên khi chạy `git add -A` ở commit `c272b35`, Git đã âm thầm bỏ qua toàn bộ thư mục `poc/frontend/src/lib/` (`api.ts`, `detection-store.ts`, `ws-client.ts`, `zone-utils.ts`). Trên máy local Windows vẫn build được vì file nằm sẵn trên ổ đĩa, nhưng lên `aiot` clone từ GitHub bị thiếu 4 file này.
- **Cách fix**: Thêm ngoại lệ `!poc/frontend/src/lib/` ngay bên dưới `lib/` trong [.gitignore](file:///e:/ATIN/atin_tran_han_industry/.gitignore#L17-L19), commit & push đầy đủ 4 file (Commit `a3519a2`). Sau khi pull, `next build` trên `aiot` pass trong `4.2s`.

---

### ISS-08: Convert `yolo26s_best.onnx` → FP16 lỗi kiểu dữ liệu tại node `Resize`
- **Giai đoạn**: Chạy `scripts/convert_onnx_fp16.py` và khởi động AI worker trên `aiot`.
- **Log / Hiện tượng**:
  - **Lần 1** (dùng `DEFAULT_OP_BLOCK_LIST` mặc định chặn `Resize`):
    ```text
    FAIL : Load model from .../yolo26s_fp16.onnx failed: Type Error: Type (tensor(float)) of output arg (/model.11/Resize_output_0) of node (/model.11/Resize_output_cast0) does not match expected type (tensor(float16)).
    ```
  - **Lần 2** (gỡ `Resize` khỏi `op_block_list` để đưa `Resize` về FP16):
    ```text
    INVALID_GRAPH : Type 'tensor(float16)' of input parameter (/model.11/Constant_output_0) of operator (Resize) in node (/model.11/Resize) is invalid.
    ```
- **Nguyên nhân gốc**: Hạn chế đã biết của `onnxconverter-common` trên đồ thị YOLO có node `Resize` — theo chuẩn ONNX, input `scales` (`/model.11/Constant_output_0`) của op `Resize` bắt buộc là `float32`, trong khi chặn `Resize` lại sinh node `Cast` lệch kiểu.
- **Cách fix** (Commit `4490461`):
  1. Cập nhật [convert_onnx_fp16.py](file:///e:/ATIN/atin_tran_han_industry/poc/backend/scripts/convert_onnx_fp16.py): kiểm tra nạp thật bằng `onnxruntime.InferenceSession` ngay sau khi convert; nếu đồ thị không hợp lệ sẽ **tự động xóa file FP16 lỗi** để không làm hỏng runtime.
  2. Cập nhật [detector.py](file:///e:/ATIN/atin_tran_han_industry/poc/backend/app/ai/detector.py#L86-L109): bổ sung cơ chế fallback an toàn sang `yolo26s_best.onnx` (FP32, `36.4 MB`, chỉ chiếm ~350–450 MB VRAM trên RTX A400 — thấp hơn nhiều mức trần `1024 MB`, chạy rất mượt và giữ nguyên 100% độ chính xác).

---

### ISS-09: `onnxruntime-gpu==1.32.0` yêu cầu CUDA 13 (`libcublasLt.so.13`), fallback về CPU
- **Giai đoạn**: Khởi động FastAPI + AI worker trên `aiot`.
- **Log / Hiện tượng**:
  ```text
  [E:onnxruntime:Default] Failed to load library .../libonnxruntime_providers_cuda.so with error: libcublasLt.so.13: cannot open shared object file: No such file or directory
  [W:onnxruntime:Default] Failed to create CUDAExecutionProvider. Require cuDNN 9.* and CUDA 13.*.
  ```
- **Nguyên nhân gốc**: `pyproject.toml` khai báo `"onnxruntime-gpu>=1.18.0"` không đặt giới hạn trần, nên `uv` cài bản `1.32.0` (wheel PyPI mặc định chuyển sang build cho **CUDA 13**), trong khi server `aiot` dùng **CUDA 12**.
- **Cách fix** (Commit `ec17460`):
  1. Ghim `"onnxruntime-gpu>=1.20.0,<1.24.0"` (cài bản `1.23.2` — chuẩn CUDA 12) và khai báo kèm bộ thư viện NVIDIA runtime cô lập ngay trong `.venv` (`nvidia-cuda-runtime-cu12`, `nvidia-cublas-cu12`, `nvidia-cudnn-cu12>=9.0.0`, `nvidia-cufft-cu12`, `nvidia-curand-cu12`) tại [pyproject.toml](file:///e:/ATIN/atin_tran_han_industry/poc/backend/pyproject.toml#L29-L38).
  2. Cập nhật [run_server.sh](file:///e:/ATIN/atin_tran_han_industry/poc/backend/scripts/run_server.sh#L32-L36) tự động tìm toàn bộ thư mục `.venv/lib/.../nvidia/*/lib` và ghép vào `LD_LIBRARY_PATH` trước khi chạy `exec uv run uvicorn`, đảm bảo `CUDAExecutionProvider` nhận đủ `libcublasLt.so.12` + `libcudnn.so.9` mà không cần sửa CUDA toàn hệ thống của server dùng chung.

---

### ISS-10: Hai lưu ý vận hành thực tế trên `aiot`
1. **File model `*.onnx` không đi theo `git push`**:
   - Do `.gitignore` chặn `*.onnx` và `*.pt`, sau khi `git clone` trên `aiot` bắt buộc phải `scp` (hoặc SFTP qua Termius) file `poc/models/yolo26s_best.onnx` từ laptop lên `/home/tts/projects/tien/atin_tran_han_industry/poc/models/`.
2. **Dán lệnh nhiều dòng dài trên Termius dễ bị ngắt dòng giữa tham số**:
   - Ví dụ dòng `uv pip install ... --no-deps "onnxruntime-gpu>=1.20.0,<1.24.0"` bị xuống dòng trước tên gói khiến bash tách thành 2 lệnh lỗi (`command not found`).
   - **Quy tắc**: Các lệnh cài đặt hoặc lệnh có tham số dài nên tách rõ từng lệnh ngắn 1 dòng để copy-paste an toàn 100%.

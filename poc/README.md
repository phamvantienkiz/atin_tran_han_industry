# ATIN Trần Hân Industry — PoC Giám Sát & AI Core

Hệ thống PoC (Proof of Concept) phục vụ dev, test và demo cho khách hàng **Nhà máy Thủy sản Trần Hân**, được cấu trúc sẵn sàng chuyển đổi lên **Production** và tích hợp vào nền tảng **ATIN Smart VMS (`aioc-backend`)**.

## Cấu trúc thư mục `poc/`

```text
poc/
├── README.md                 # Tài liệu tổng quan PoC (file này)
├── backend/                  # FastAPI Backend + AI Core (chuẩn fastapi-backend-scaffold)
│   ├── app/                  # Mã nguồn API, middlewares, services, repositories, ai, integrations
│   ├── docs/                 # Tài liệu kỹ thuật backend (spec.md, audit.md, changelog.md)
│   ├── migrations/           # Alembic async migrations (PostgreSQL)
│   ├── scripts/              # Script chạy dev (dev.ps1)
│   ├── tests/                # Pytest suite (api, middlewares, services)
│   ├── Dockerfile            # Đóng gói container Production
│   └── docker-compose.yml    # Chạy local với PostgreSQL
├── frontend/                 # Giao diện Web tĩnh (HTML/CSS/JS) + design-system.md
├── data/                     # Dữ liệu cấu hình PoC (cameras.json)
├── models/                   # Trọng số AI (yolo26s.onnx, yolo26s.pt)
├── storages/                 # Lưu trữ video ghi hình (.mp4) & bộ frame tách từ video
├── report/                   # Ảnh/báo cáo kiểm thử PoC
└── docs/                     # Tài liệu đặc tả PoC (spec.md)
```

## Chạy nhanh (Local Dev)

1. Cấu hình biến môi trường:
   ```powershell
   cd poc\backend
   copy .env.example .env
   # Điền NVR_HOST, NVR_PORT, NVR_USER, NVR_PASS trong .env
   ```
2. Tạo môi trường ảo nội bộ và cài đặt thư viện:
   ```powershell
   uv venv .venv
   uv pip install --python .\.venv\Scripts\python.exe -e ".[dev]"
   ```
3. Khởi động server (kèm giao diện Web tại `http://localhost:8000` và Swagger tại `/docs`):
   ```powershell
   .\scripts\dev.ps1
   # Hoặc: uv run uvicorn app.main:app --reload --timeout-graceful-shutdown 2
   ```

## Kiểm thử & Lint

```powershell
cd poc\backend
.\.venv\Scripts\pytest.exe -v
.\.venv\Scripts\ruff.exe check app tests
```

## Chuyển đổi sang Production (ATIN Smart VMS)

- **Giai đoạn PoC**: Kết nối trực tiếp NVR qua HTTP Digest (`snapshot.cgi`, `mjpg/video.cgi`), lưu cấu hình camera/zone tại `data/cameras.json`.
- **Giai đoạn Production**: Kích hoạt adapter `app/integrations/atin_vms/` (`ATIN_VMS_ENABLED=true`) để nhận luồng RTSP qua MediaMTX (`18554`), đồng bộ camera/zone qua MQTT (`smart_vms/...`), upload snapshot lên Storage API (`/storage/upload/file`) và chuyển repository sang PostgreSQL/Alembic.

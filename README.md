# ATIN — Tran Han Industry

Dự án phát triển hệ thống giám sát nhân sự và quy trình vận hành tại nhà máy chế biến thủy hải sản, thực hiện bởi **ATIN Joint Stock Company**.

---

## Tổng quan & Định hướng triển khai

Hiện tại repository đang ở giai đoạn khởi tạo và chuẩn bị tài liệu/prototype. Theo định hướng tại [Hướng dẫn công việc.txt](docs/requirement-ba-pm/H%C6%B0%E1%BB%9Bng%20d%E1%BA%ABn%20c%C3%B4ng%20vi%E1%BB%87c.txt), dự án áp dụng quy trình mô phỏng trước khi tích hợp camera thực tế:

1. **Mô phỏng mặt bằng 3D**: Xây dựng mô hình nhà máy bằng Three.js dựa trên mặt bằng và các kịch bản nghiệp vụ của khách hàng.
2. **Tạo dữ liệu & Huấn luyện model**: Xuất ảnh và bounding box từ môi trường 3D theo các góc camera mô phỏng để huấn luyện model nhận diện (YOLO).
3. **Giả lập luồng RTSP & Kiểm thử**: Record/export góc camera 3D thành luồng RTSP giả lập để chạy thử nghiệm các bài toán giám sát.
4. **Chuyển đổi sang hạ tầng thật**: Khi có luồng camera thực tế tại nhà máy, cập nhật lại polygon (ROI) và model phù hợp trong khi giữ nguyên phần lớn mã nguồn xử lý.

---

## Cấu trúc thư mục

```text
atin_tran_han_industry/
├── .agents/                  # Cấu hình MCP servers và bộ skills hỗ trợ AI Agent
├── customers/                # Tài liệu, video mẫu từ phía khách hàng
├── docs/
│   ├── ai/                   # Nơi lưu trữ tài liệu, kế hoạch, artifact do AI tạo
│   └── requirement-ba-pm/    # Tài liệu yêu cầu, hướng dẫn nghiệp vụ BA/PM
├── prototype/                # Mã nguồn thử nghiệm / prototype (đang chuẩn bị)
├── AGENTS.md                 # Quy tắc làm việc, quản lý môi trường và checklist cho AI Agent
├── LICENSE                   # Giấy phép bản quyền độc quyền của ATIN
└── README.md                 # Tài liệu tổng quan dự án
```

---

## Bản quyền

**Proprietary and Confidential** — Copyright © 2026 [ATIN Joint Stock Company](https://atin.com.vn/).  
Toàn bộ mã nguồn, tài liệu và tài sản trong repository thuộc quyền sở hữu độc quyền của ATIN. Xem chi tiết tại [LICENSE](LICENSE).

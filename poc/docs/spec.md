# Đặc Tả Chức Năng PoC — Giám Sát Khu Vực Nhà Máy Thủy Sản Trần Hân

## 1. Mục tiêu PoC
Xây dựng ứng dụng web demo + AI Core chạy thực tế trên luồng camera của nhà máy để:
- Trực quan hóa luồng camera trực tiếp (MJPEG / Snapshot).
- Cho phép vẽ, chỉnh sửa và lưu vùng giám sát đa giác (Zone Polygon, tọa độ chuẩn hóa `0..1`) trực tiếp trên từng camera.
- Chạy suy luận AI (`yolo26s.onnx`) phát hiện người trong vùng giám sát theo thời gian thực.
- Ghi hình video `.mp4` từ NVR và tách frame làm dữ liệu huấn luyện/kiểm thử (Dataset).

## 2. Phạm vi Camera mặc định (PoC)
Cấu hình khởi tạo trong `poc/data/cameras.json`:
| ID | Kênh (Channel) | Tên khu vực | Ghi chú |
| :--- | :---: | :--- | :--- |
| `ch16` | 16 | Tăng trọng 1 | Khu vực máy tăng trọng 1 |
| `ch17` | 17 | Tăng trọng 2 | Khu vực máy tăng trọng 2 |
| `ch18` | 18 | Tăng trọng 3 | Khu vực máy tăng trọng 3 |
| `ch21` | 21 | Định hình 2 | Khu vực định hình 2 |

## 3. Các phân hệ chức năng

### 3.1. Giám sát trực tiếp & Trạng thái Camera
- Hiển thị lưới camera (hỗ trợ chế độ `mjpeg` hoặc `snapshot`, `subtype` 0/1/2).
- Hỗ trợ mở rộng 1 camera (Focus mode) để ưu tiên tần suất suy luận AI cao hơn (`AI_FOCUS_INTERVAL_SEC=0.15s`, TTL `15s`).
- Kiểm tra kết nối camera (`probe`) đo độ trễ và trạng thái online.

### 3.2. Thiết lập Vùng Giám Sát (Zone Editor)
- Vẽ đa giác (tối thiểu 3 điểm) với tọa độ chuẩn hóa `[0.0 .. 1.0]` theo khung hình.
- Lưu trực tiếp vào `CameraRepository` (`PUT /api/v1/cameras/{cam_id}/zone`).

### 3.3. Nhận diện Người trong Vùng (AI Core)
- Sử dụng mô hình `yolo26s.onnx` qua ONNX Runtime (`CPUExecutionProvider`), lọc class `0` (person) với ngưỡng tin cậy mặc định `0.45` và NMS IoU `0.45`.
- Kiểm tra điểm tâm BBox `(cx, cy)` nằm trong đa giác bằng thuật toán Ray Casting (`point_in_polygon`).
- Áp dụng máy trạng thái chống spam sự kiện (`ZoneRuleEngine`):
  - **Dwell-time** (`AI_CONFIRM_SECONDS = 2.0s`): xác nhận hiện diện liên tục trước khi kích hoạt sự kiện.
  - **Cooldown** (`AI_EVENT_COOLDOWN_SECONDS = 60.0s`): tránh bắn trùng lặp liên tục.

### 3.4. Ghi hình & Tách Frame (Dataset)
- Ghi luồng MJPEG thành file `.mp4` (FPS cố định `10.0`), hỗ trợ thời lượng `5`, `10`, `20` phút; có thể dừng chủ động.
- Tách ảnh `.jpg` từ video đã ghi với bước nhảy `skip_frames` (`5` hoặc `10` frame liên tiếp), xem trước ảnh và tải toàn bộ dưới dạng `.zip`.

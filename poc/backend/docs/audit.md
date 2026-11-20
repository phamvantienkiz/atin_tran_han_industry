# Báo Cáo Kiểm Tra Kỹ Thuật & Bảo Mật (`poc/backend`)

## 1. Kết quả kiểm tra tự động (Verify)
- **Pytest (`pytest -v`)**: `5 passed` (`test_health`, `test_response_has_request_id_and_timing_headers`, `test_request_id_is_propagated`, `test_camera_crud_and_zone_flow`, `test_zone_rule_engine_dwell_time_and_cooldown`).
- **Ruff (`ruff check app tests`)**: `All checks passed!` (0 lỗi).
- **Live Startup**: `uvicorn app.main:app` khởi động thành công, `/api/v1/health` trả `200 OK` kèm header `X-Request-ID` và `X-Process-Time`.

## 2. Các kiểm soát đã áp dụng
- **Chống Path Traversal**: Mọi thao tác đọc/tải/xóa file video và frame đều đi qua `validate_safe_name()` (`^[A-Za-z0-9._-]+$`, chặn `..`).
- **Xử lý lỗi tập trung**: `ErrorHandlingMiddleware` chặn toàn bộ ngoại lệ chưa xử lý và trả JSON `500` kèm `request_id` (không rò rỉ stack trace); các lỗi nghiệp vụ dùng `NotFoundError`, `ConflictError`, `ValidationError`, `UpstreamError` qua `exceptions/handlers.py`.
- **Cô lập bí mật & môi trường**: `.env` và `.venv/` được loại trừ trong `.gitignore`; chỉ commit `.env.example`.
- **Graceful Shutdown**: Cấu hình `--timeout-graceful-shutdown 2` để tránh kẹt kết nối MJPEG streaming khi dừng server.

## 3. Hạng mục cần nâng cấp khi lên Production
1. **Rate Limit phân tán**: `RateLimitMiddleware` hiện lưu bộ đếm trong RAM (`_hits`); cần chuyển sang Redis (`INCR` + `EXPIRE`) khi chạy nhiều worker/container.
2. **Xác thực & Phân quyền**: Bổ sung xác thực JWT RS256 (Keycloak / IAM) hoặc tích hợp trực tiếp vào `aioc-backend` theo luồng IAM hiện hữu.
3. **Database Migration**: Bật PostgreSQL và tạo revision Alembic đầu tiên (`alembic revision --autogenerate -m "init" && alembic upgrade head`), chuyển `CameraRepository` từ JSON sang `AsyncSession`.
4. **Cấu hình CORS & Secret**: Thay `SECRET_KEY` mặc định và giới hạn `BACKEND_CORS_ORIGINS` theo domain Production thực tế.

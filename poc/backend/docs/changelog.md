# Changelog — `poc/backend`

## [0.1.0] - 2026-11-19
### Added
- Dựng khung `poc/backend/` theo chuẩn `fastapi-backend-scaffold` (`api/v1`, `middlewares`, `core`, `models`, `schemas`, `db`, `repositories`, `services`, `dependencies`, `exceptions`, `utils`).
- Tách AI Core thành `app/ai/detector.py` (`YoloPersonDetector`), `app/ai/rule_engine.py` (`ZoneRuleEngine` với dwell-time & cooldown `C08`) và `app/ai/worker.py`.
- Bổ sung bộ adapter tích hợp ATIN Smart VMS tại `app/integrations/atin_vms/` (`mqtt_orchestrator.py`, `rtsp_reader.py`, `storage_client.py`).
- Khởi tạo Alembic async (`migrations/`), `Dockerfile`, `docker-compose.yml`, `scripts/dev.ps1` và bộ test `pytest` (5 test cases).

### Changed
- Chuẩn hóa toàn bộ API sang prefix `/api/v1/...` và cập nhật `poc/frontend/js/*.js` tương ứng.
- Tách `poc/ui/` thành `poc/frontend/` (gồm cả `design-system.md`) và `poc/cameras.json` thành `poc/data/cameras.json`.
- Thêm `--timeout-graceful-shutdown 2` cho Uvicorn để đóng sạch kết nối MJPEG streaming khi `Ctrl + C`.

### Removed
- Dọn bỏ thư mục `poc/src/`, `poc/pyproject.toml`, `poc/uv.lock` và `poc/.env.example` cũ sau khi đã chuyển sang `poc/backend/`.

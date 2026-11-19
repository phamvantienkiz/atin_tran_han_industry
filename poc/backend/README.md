# ATIN Tran Han Industry — AI Backend

FastAPI backend & AI Core for **Nhà máy Thủy sản Trần Hân** (PoC-to-Production), structured according to `fastapi-backend-scaffold` and aligned with ATIN Smart VMS (`aioc-backend` / AI Edge Worker contracts C01–C09).

## Requirements

- Python >= 3.11
- `uv` or `pip`
- (Optional) Docker + Docker Compose

## Setup (local dev)

All commands run from inside `poc/backend/`. Never install dependencies into system Python.

**Using `uv` (recommended):**

```powershell
cd poc/backend
uv venv .venv
.venv\Scripts\Activate.ps1
uv pip install -e ".[dev]"
copy .env.example .env  # fill in NVR / ATIN VMS credentials
```

**Using `pip`:**

```powershell
cd poc/backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

## Running the dev server

```powershell
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --timeout-graceful-shutdown 2
```

Runs at `http://localhost:8000` (API docs at `/docs`, healthcheck at `/api/v1/health`). Every HTTP response includes `X-Request-ID` and `X-Process-Time` headers.

## Running tests & lint

```powershell
uv run pytest
uv run ruff check app tests
```

## Running with Docker

```bash
docker compose up --build
```

## Architecture

- `app/api/v1/endpoints/`: HTTP controllers (`health`, `config`, `cameras`, `detections`, `records`, `storages`)
- `app/middlewares/`: `ErrorHandlingMiddleware`, `CORSMiddleware`, `RequestLoggingMiddleware`, `RateLimitMiddleware`, `RequestIDMiddleware`
- `app/services/`: Business orchestration (`camera_service`, `detection_service`, `media_service`)
- `app/repositories/`: Data persistence (`camera_repository` with JSON PoC store, swappable for SQLAlchemy/Postgres)
- `app/ai/`: Pure AI inference & zone rule engine (`PersonZoneDetector`, `ZoneRuleEngine` with dwell-time & cooldown)
- `app/integrations/atin_vms/`: Production ATIN Smart VMS adapters (MQTT Orchestrator, RTSP low-latency reader, Storage uploader, BBox/Event publisher)

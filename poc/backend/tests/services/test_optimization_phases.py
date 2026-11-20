import time
from pathlib import Path

from app.ai.display_pipeline import AiTrackSnapshot, _interpolate_tracks
from app.ai.tracker import TrackedPerson
from app.db.sqlite_store import SqliteStore
from app.repositories.sqlite_camera_repository import SqliteCameraRepository


def test_interpolate_tracks_linear_and_extrapolate() -> None:
    t0 = 100.0
    t1 = 100.2
    p0 = TrackedPerson(
        track_id=1,
        x1=0.1,
        y1=0.2,
        x2=0.2,
        y2=0.6,
        cx=0.15,
        cy=0.4,
        foot_x=0.15,
        foot_y=0.6,
        conf=0.9,
        vx=0.5,
        vy=0.0,
    )
    p1 = TrackedPerson(
        track_id=1,
        x1=0.2,
        y1=0.2,
        x2=0.3,
        y2=0.6,
        cx=0.25,
        cy=0.4,
        foot_x=0.25,
        foot_y=0.6,
        conf=0.92,
        vx=0.5,
        vy=0.0,
    )
    history = [
        AiTrackSnapshot(ts_mono=t0, tracks=[p0], inference_ms=60),
        AiTrackSnapshot(ts_mono=t1, tracks=[p1], inference_ms=65),
    ]

    # Midpoint interpolation
    persons_mid, infer_ms, extrap = _interpolate_tracks(history, 100.1)
    assert not extrap
    assert infer_ms == 65
    assert len(persons_mid) == 1
    assert abs(persons_mid[0]["x1"] - 0.15) < 1e-4
    assert persons_mid[0]["predicted"] is False

    # Extrapolation slightly past t1
    persons_ext, _, extrap2 = _interpolate_tracks(history, 100.3)
    assert extrap2
    assert len(persons_ext) == 1
    assert persons_ext[0]["x1"] > 0.2
    assert persons_ext[0]["predicted"] is True


def test_sqlite_store_and_camera_repo_migration(tmp_path: Path) -> None:
    legacy_json = tmp_path / "cameras.json"
    legacy_json.write_text(
        '[{"id": "ch16", "channel": 16, "name": "Cam 16", "subtype": 0, "mode": "mjpeg", "enabled": true, "zone": []}]',
        encoding="utf-8",
    )
    db_path = tmp_path / "test.db"
    store = SqliteStore(db_path=db_path, retention_days=90)
    try:
        repo = SqliteCameraRepository(store=store, legacy_json_file=legacy_json)
        cams = repo.list_all()
        assert len(cams) == 1
        assert cams[0]["id"] == "ch16"
        assert cams[0]["subtype"] == 0
        assert (tmp_path / "cameras.json.migrated").is_file()
        assert not legacy_json.exists()

        now = time.time()
        store.enqueue_runtime_snapshots(
            [
                {
                    "cam_id": "ch16",
                    "alert_count": 3,
                    "total_alert_seconds": 42.5,
                    "session_started_at": now - 100,
                    "timeline": [{"start": now - 100, "end": now, "color": "green"}],
                    "saved_at": now,
                }
            ]
        )
        store.enqueue_alert_event("ch16", started_at=now - 20, ended_at=now - 5, duration_s=15.0)
        store._write_queue.join()

        loaded = store.load_recent_snapshots(max_age_sec=1800)
        assert loaded["ch16"]["alert_count"] == 3
        events = store.query_alert_events("ch16")
        assert len(events) == 1
        assert events[0]["duration_s"] == 15.0
    finally:
        store.close()

import time
from pathlib import Path

import cv2
import numpy as np

from app.ai.display_pipeline import AiTrackSnapshot, _interpolate_tracks
from app.ai.grid_cache import GridFrameCache
from app.ai.nvr_stream import NvrFramePacket
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


def test_grid_frame_cache_demand_driven_and_shared() -> None:
    rng = np.random.default_rng(42)
    img_1080p = rng.integers(0, 255, size=(1080, 1920, 3), dtype=np.uint8)
    ok, enc = cv2.imencode(".jpg", img_1080p, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    assert ok
    raw_bytes = enc.tobytes()

    cache = GridFrameCache(grid_width=960, jpeg_quality=72, max_workers=1)
    try:
        pkt1 = NvrFramePacket(
            cam_id="cam_16",
            channel=16,
            subtype=0,
            frame=None,
            jpeg_bytes=raw_bytes,
            seq=1,
            ts_mono=time.monotonic(),
            ts_wall=time.time(),
        )
        # 0 viewers -> must NOT encode
        cache.on_raw_frame(pkt1)
        time.sleep(0.05)
        assert cache.latest_grid("cam_16") is None

        # Register 2 shared viewers -> encodes once and shares same GridFrame
        ev1 = cache.register_grid_waiter("cam_16", initial_pkt=pkt1)
        ev2 = cache.register_grid_waiter("cam_16", initial_pkt=pkt1)
        deadline = time.monotonic() + 2.0
        while cache.latest_grid("cam_16") is None and time.monotonic() < deadline:
            time.sleep(0.02)

        gf = cache.latest_grid("cam_16")
        assert gf is not None
        assert gf.seq == 1
        assert gf.size_bytes < len(raw_bytes)

        dec = cv2.imdecode(np.frombuffer(gf.jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert dec is not None
        assert dec.shape[1] == 960
        assert dec.shape[0] == 540

        metrics = cache.get_metrics()["cam_16"]
        assert metrics["grid_viewers"] == 2
        assert metrics["grid_jpeg_kb"] < metrics["raw_jpeg_kb"]

        cache.unregister_grid_waiter("cam_16", ev1)
        cache.unregister_grid_waiter("cam_16", ev2)
        assert cache.get_metrics()["cam_16"]["grid_viewers"] == 0
    finally:
        cache.stop()

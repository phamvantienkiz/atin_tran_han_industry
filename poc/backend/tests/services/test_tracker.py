import numpy as np

from app.ai.detector import PersonDetection
from app.ai.tracker import CameraTracker, _snap_box_to_raw


def test_snap_box_to_raw_replaces_when_iou_above_threshold() -> None:
    track_box = np.array([100.0, 100.0, 200.0, 300.0], dtype=np.float32)
    raw_boxes = np.array(
        [
            [105.0, 102.0, 205.0, 302.0],  # High IoU (~0.9)
            [500.0, 500.0, 600.0, 700.0],  # Zero IoU
        ],
        dtype=np.float32,
    )
    raw_confs = np.array([0.88, 0.72], dtype=np.float32)

    snapped, conf = _snap_box_to_raw(track_box, raw_boxes, raw_confs, min_iou=0.45)
    assert np.allclose(snapped, raw_boxes[0])
    assert abs(conf - 0.88) < 1e-5


def test_snap_box_to_raw_keeps_track_box_when_iou_too_low() -> None:
    track_box = np.array([100.0, 100.0, 200.0, 300.0], dtype=np.float32)
    raw_boxes = np.array([[500.0, 500.0, 600.0, 700.0]], dtype=np.float32)
    raw_confs = np.array([0.65], dtype=np.float32)

    snapped, _ = _snap_box_to_raw(track_box, raw_boxes, raw_confs, min_iou=0.45)
    assert np.allclose(snapped, track_box)


def test_camera_tracker_persists_id_and_isolates_cameras() -> None:
    tracker = CameraTracker(frame_rate=12)

    frame1 = [PersonDetection(x1=0.20, y1=0.20, x2=0.35, y2=0.70, cx=0.275, cy=0.45, conf=0.90)]
    frame2 = [PersonDetection(x1=0.21, y1=0.20, x2=0.36, y2=0.70, cx=0.285, cy=0.45, conf=0.91)]

    t1 = tracker.update("cam_a", frame1)
    assert len(t1) == 1
    first_id = t1[0].track_id
    assert t1[0].foot_x == t1[0].cx
    assert abs(t1[0].foot_y - t1[0].y2) < 1e-4

    # Slight motion on next frame should retain exact same track_id and snap to frame2 box
    t2 = tracker.update("cam_a", frame2)
    assert len(t2) == 1
    assert t2[0].track_id == first_id
    assert abs(t2[0].x1 - 0.21) < 1e-3

    # Empty frame handled gracefully
    t_empty = tracker.update("cam_a", [])
    assert t_empty == []

    # Independent camera gets its own ByteTrack instance
    t_other = tracker.update("cam_b", frame1)
    assert len(t_other) == 1

    # Reset clears state without error
    tracker.reset("cam_a")
    t_after_reset = tracker.update("cam_a", frame1)
    assert len(t_after_reset) == 1

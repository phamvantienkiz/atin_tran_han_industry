from pathlib import Path

import cv2
import pytest

from app.ai.detector import YoloPersonDetector
from app.ai.rule_engine import ZoneRuleEngine
from app.ai.tracker import CameraTracker

POC_ROOT = Path(__file__).resolve().parents[3]
MODEL_PATH = POC_ROOT / "models" / "yolo26s.onnx"
SAMPLE_IMG = POC_ROOT / "report" / "ch17-snapshot.jpg"


@pytest.mark.skipif(not MODEL_PATH.is_file() or not SAMPLE_IMG.is_file(), reason="Model or sample image absent")
def test_yolo_detector_tracker_rule_engine_pipeline_on_real_frame() -> None:
    frame = cv2.imread(str(SAMPLE_IMG))
    assert frame is not None

    detector = YoloPersonDetector(model_path=MODEL_PATH, conf=0.35, imgsz=640, runtime="cpu")
    batch = detector.detect_batch([frame, frame])
    assert len(batch) == 2
    assert detector.active_provider == "CPUExecutionProvider"

    tracker = CameraTracker(frame_rate=12)
    tracked_1 = tracker.update("ch17", batch[0])
    tracked_2 = tracker.update("ch17", batch[1])

    zone = [
        {"x": 0.05, "y": 0.1},
        {"x": 0.95, "y": 0.1},
        {"x": 0.95, "y": 0.95},
        {"x": 0.05, "y": 0.95},
    ]
    engine = ZoneRuleEngine(default_feature_type="zone_presence")
    ev1 = engine.evaluate("ch17", tracked_1, zone, now=1.0, wall_time=100.0, zone_name="Tăng trọng 2")
    ev2 = engine.evaluate("ch17", tracked_2, zone, now=1.1, wall_time=100.1, zone_name="Tăng trọng 2")

    assert ev1.has_zone is True
    assert len(batch[0]) >= 3
    assert ev2.in_zone_count >= 1
    assert ev2.ui_color == "green"
    for p in ev2.persons:
        assert 0.0 <= p["foot_x"] <= 1.0
        assert 0.0 <= p["foot_y"] <= 1.0
        assert "track_id" in p

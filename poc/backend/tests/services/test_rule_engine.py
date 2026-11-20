from app.ai.detector import PersonDetection
from app.ai.rule_engine import ZoneRuleEngine


def test_zone_rule_engine_dwell_time_and_cooldown() -> None:
    engine = ZoneRuleEngine(confirm_seconds=2.0, cooldown_seconds=60.0)
    polygon = [
        {"x": 0.0, "y": 0.0},
        {"x": 0.5, "y": 0.0},
        {"x": 0.5, "y": 0.5},
        {"x": 0.0, "y": 0.5},
    ]
    inside_person = [PersonDetection(x1=0.1, y1=0.1, x2=0.3, y2=0.3, cx=0.2, cy=0.2, conf=0.9)]

    # t=10.0: enters zone -> dwell 0.0 < 2.0 -> no event yet
    ev1 = engine.evaluate("cam1", inside_person, polygon, now=10.0)
    assert ev1.person_in_zone is True
    assert ev1.should_emit_event is False

    # t=12.1: still in zone -> dwell 2.1 >= 2.0 -> emit event!
    ev2 = engine.evaluate("cam1", inside_person, polygon, now=12.1)
    assert ev2.should_emit_event is True

    # t=20.0: in cooldown (< 60s) -> suppressed
    ev3 = engine.evaluate("cam1", inside_person, polygon, now=20.0)
    assert ev3.should_emit_event is False

    # t=75.0: cooldown expired -> emit again
    ev4 = engine.evaluate("cam1", inside_person, polygon, now=75.0)
    assert ev4.should_emit_event is True

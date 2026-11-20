from app.ai.detector import PersonDetection
from app.ai.rule_engine import ZoneRuleEngine
from app.ai.tracker import TrackedPerson

BOX_ZONE = [
    {"x": 0.2, "y": 0.3},
    {"x": 0.8, "y": 0.3},
    {"x": 0.8, "y": 0.9},
    {"x": 0.2, "y": 0.9},
]


def _tracked_inside(tid: int = 1) -> TrackedPerson:
    # Center (0.5, 0.5), foot (0.5, 0.7) -> both inside BOX_ZONE
    return TrackedPerson(
        track_id=tid,
        x1=0.4,
        y1=0.3,
        x2=0.6,
        y2=0.7,
        cx=0.5,
        cy=0.5,
        foot_x=0.5,
        foot_y=0.7,
        conf=0.92,
    )


def _tracked_outside(tid: int = 9) -> TrackedPerson:
    return TrackedPerson(
        track_id=tid,
        x1=0.02,
        y1=0.1,
        x2=0.12,
        y2=0.25,
        cx=0.07,
        cy=0.175,
        foot_x=0.07,
        foot_y=0.25,
        conf=0.88,
    )


def test_presence_cold_start_empty_then_alert() -> None:
    engine = ZoneRuleEngine(
        grace_seconds=2.0,
        warning_seconds=10.0,
        default_feature_type="zone_presence",
    )

    # t=0.0: Cold start with nobody -> starts YELLOW (empty), NOT leaving
    ev0 = engine.evaluate("cam1", [], BOX_ZONE, now=100.0, wall_time=1000.0, zone_name="Vùng máy trộn")
    assert ev0.status == "empty"
    assert ev0.ui_color == "yellow"
    assert ev0.status_label == "VÙNG TRỐNG"
    assert ev0.sub_label == "không có người 00:00"
    assert ev0.polygon_label == "VÙNG MÁY TRỘN · TRỐNG"
    assert ev0.alert_count == 0
    assert ev0.should_emit_event is False

    # t=9.9s: still yellow
    ev1 = engine.evaluate("cam1", [], BOX_ZONE, now=109.9, wall_time=1009.9, zone_name="Vùng máy trộn")
    assert ev1.status == "empty"
    assert ev1.ui_color == "yellow"
    assert ev1.sub_label == "không có người 00:09"
    assert ev1.alert_count == 0

    # t=10.0s: transitions to RED alert
    ev2 = engine.evaluate("cam1", [], BOX_ZONE, now=110.0, wall_time=1010.0, zone_name="Vùng máy trộn")
    assert ev2.status == "alert"
    assert ev2.ui_color == "red"
    assert ev2.status_label == "KHÔNG CÓ NHÂN VIÊN"
    assert ev2.sub_label == "Cảnh báo · vùng trống 00:10"
    assert ev2.polygon_label == "VÙNG MÁY TRỘN · KHÔNG CÓ NHÂN VIÊN"
    assert ev2.alert_count == 1
    assert ev2.should_emit_event is True


def test_presence_full_lifecycle_present_leaving_empty_alert_and_return() -> None:
    engine = ZoneRuleEngine(
        grace_seconds=2.0,
        warning_seconds=10.0,
        cooldown_seconds=60.0,
        default_feature_type="zone_presence",
    )

    # t=0: employee present
    ev_present = engine.evaluate(
        "cam1",
        [_tracked_inside(1), _tracked_outside(2)],
        BOX_ZONE,
        now=10.0,
        wall_time=2000.0,
        zone_name="Vùng máy trộn",
    )
    assert ev_present.status == "present"
    assert ev_present.ui_color == "green"
    assert ev_present.in_zone_count == 1
    assert ev_present.status_label == "CÓ NHÂN VIÊN"
    assert ev_present.sub_label == "1 người trong vùng"
    assert ev_present.polygon_label == "VÙNG MÁY TRỘN · 1 NV"
    assert [p["in_zone"] for p in ev_present.persons] == [True, False]

    # t=15.0: employee leaves -> leaving (still green) for grace_seconds=2.0s
    ev_leave1 = engine.evaluate("cam1", [], BOX_ZONE, now=15.0, wall_time=2005.0, zone_name="Vùng máy trộn")
    assert ev_leave1.status == "leaving"
    assert ev_leave1.ui_color == "green"
    assert ev_leave1.status_label == "CÓ NHÂN VIÊN"
    assert ev_leave1.sub_label == "Vừa rời khỏi vùng"
    assert ev_leave1.polygon_label == "VÙNG MÁY TRỘN · VỪA RỜI VÙNG"

    # t=16.5: 1.5s elapsed -> still leaving (green)
    ev_leave2 = engine.evaluate("cam1", [], BOX_ZONE, now=16.5, wall_time=2006.5, zone_name="Vùng máy trộn")
    assert ev_leave2.status == "leaving"
    assert ev_leave2.ui_color == "green"

    # t=17.0: 2.0s elapsed -> transitions to empty (yellow)
    ev_empty = engine.evaluate("cam1", [], BOX_ZONE, now=17.0, wall_time=2007.0, zone_name="Vùng máy trộn")
    assert ev_empty.status == "empty"
    assert ev_empty.ui_color == "yellow"
    assert ev_empty.status_label == "VÙNG TRỐNG"
    assert ev_empty.sub_label == "không có người 00:02"
    assert ev_empty.alert_count == 0

    # t=26.9: 9.9s in yellow (11.9s total empty) -> still yellow
    ev_empty2 = engine.evaluate("cam1", [], BOX_ZONE, now=26.9, wall_time=2016.9, zone_name="Vùng máy trộn")
    assert ev_empty2.status == "empty"
    assert ev_empty2.ui_color == "yellow"
    assert ev_empty2.sub_label == "không có người 00:11"

    # t=27.0: 10.0s in yellow (12.0s total empty) -> RED alert!
    ev_alert = engine.evaluate("cam1", [], BOX_ZONE, now=27.0, wall_time=2017.0, zone_name="Vùng máy trộn")
    assert ev_alert.status == "alert"
    assert ev_alert.ui_color == "red"
    assert ev_alert.status_label == "KHÔNG CÓ NHÂN VIÊN"
    assert ev_alert.sub_label == "Cảnh báo · vùng trống 00:12"
    assert ev_alert.alert_count == 1
    assert ev_alert.should_emit_event is True
    assert ev_alert.total_alert_seconds == 0.0

    # t=31.0: 4.0s elapsed in alert -> total_alert_seconds accumulates
    ev_alert2 = engine.evaluate("cam1", [], BOX_ZONE, now=31.0, wall_time=2021.0, zone_name="Vùng máy trộn")
    assert ev_alert2.status == "alert"
    assert ev_alert2.total_alert_seconds == 4.0
    assert ev_alert2.alert_count == 1

    # t=33.0: employee returns -> adds final 2.0s alert time, back to green present
    ev_back = engine.evaluate(
        "cam1",
        [_tracked_inside(1), _tracked_inside(3)],
        BOX_ZONE,
        now=33.0,
        wall_time=2023.0,
        zone_name="Vùng máy trộn",
    )
    assert ev_back.status == "present"
    assert ev_back.ui_color == "green"
    assert ev_back.in_zone_count == 2
    assert ev_back.sub_label == "2 người trong vùng"
    assert ev_back.polygon_label == "VÙNG MÁY TRỘN · 2 NV"
    assert ev_back.total_alert_seconds == 6.0
    assert ev_back.alert_count == 1


def test_presence_fast_bounce_during_grace_stays_green() -> None:
    engine = ZoneRuleEngine(grace_seconds=2.0, warning_seconds=10.0, default_feature_type="zone_presence")
    engine.evaluate("cam1", [_tracked_inside()], BOX_ZONE, now=1.0, wall_time=100.0)
    ev_leave = engine.evaluate("cam1", [], BOX_ZONE, now=2.0, wall_time=101.0)
    assert ev_leave.status == "leaving"
    assert ev_leave.ui_color == "green"

    # Returns before 2.0s expires
    ev_return = engine.evaluate("cam1", [_tracked_inside()], BOX_ZONE, now=3.5, wall_time=102.5)
    assert ev_return.status == "present"
    assert ev_return.ui_color == "green"
    assert ev_return.alert_count == 0


def test_presence_uses_bottom_center_foot_anchor() -> None:
    engine = ZoneRuleEngine(anchor_mode="bottom_center", default_feature_type="zone_presence")

    # Center (0.5, 0.2) is ABOVE polygon (y >= 0.3), but foot (0.5, 0.35) is INSIDE polygon
    foot_in_center_out = PersonDetection(
        x1=0.4,
        y1=0.05,
        x2=0.6,
        y2=0.35,
        cx=0.5,
        cy=0.2,
        foot_x=0.5,
        foot_y=0.35,
        conf=0.9,
    )
    ev_in = engine.evaluate("cam1", [foot_in_center_out], BOX_ZONE, now=1.0, wall_time=100.0)
    assert ev_in.in_zone_count == 1
    assert ev_in.persons[0]["in_zone"] is True

    # Center (0.5, 0.8) is INSIDE polygon (y <= 0.9), but foot (0.5, 0.95) is BELOW polygon
    foot_out_center_in = PersonDetection(
        x1=0.4,
        y1=0.65,
        x2=0.6,
        y2=0.95,
        cx=0.5,
        cy=0.8,
        foot_x=0.5,
        foot_y=0.95,
        conf=0.9,
    )
    ev_out = engine.evaluate("cam2", [foot_out_center_in], BOX_ZONE, now=1.0, wall_time=100.0)
    assert ev_out.in_zone_count == 0
    assert ev_out.persons[0]["in_zone"] is False


def test_presence_idle_when_no_zone_and_rolling_timeline_trims_and_resets() -> None:
    engine = ZoneRuleEngine(
        grace_seconds=2.0,
        warning_seconds=10.0,
        timeline_window_seconds=1800,
        default_feature_type="zone_presence",
    )

    ev_idle = engine.evaluate("cam_no_zone", [_tracked_inside()], [], now=1.0, wall_time=100.0)
    assert ev_idle.has_zone is False
    assert ev_idle.status == "idle"
    assert ev_idle.ui_color == "idle"
    assert ev_idle.status_label == "CHƯA VẼ VÙNG"

    # Build a timeline across > 1800s to test merging & trimming
    engine.evaluate("cam_tl", [_tracked_inside()], BOX_ZONE, now=0.0, wall_time=1000.0)
    engine.evaluate("cam_tl", [_tracked_inside()], BOX_ZONE, now=500.0, wall_time=1500.0)
    engine.evaluate("cam_tl", [], BOX_ZONE, now=502.5, wall_time=1502.5)  # leaving -> empty (yellow)
    ev_late = engine.evaluate("cam_tl", [], BOX_ZONE, now=2500.0, wall_time=3500.0)  # alert (red)

    # Cutoff is 3500 - 1800 = 1700; segments ending before 1700 must be pruned
    assert all(seg["end"] >= 1700.0 for seg in ev_late.timeline)
    assert ev_late.timeline[0]["start"] >= 1700.0
    assert ev_late.timeline[-1]["color"] == "red"

    # Reset stats wipes counters & timeline
    engine.reset_stats("cam_tl")
    ev_after_reset = engine.evaluate("cam_tl", [_tracked_inside()], BOX_ZONE, now=2505.0, wall_time=3505.0)
    assert ev_after_reset.alert_count == 0
    assert ev_after_reset.total_alert_seconds == 0.0
    assert len(ev_after_reset.timeline) == 1
    assert ev_after_reset.timeline[0]["color"] == "green"

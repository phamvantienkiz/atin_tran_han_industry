"""Zone rule engine supporting 4-state zone presence monitoring & legacy zone intrusion."""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.ai.detector import PersonDetection
from app.ai.tracker import TrackedPerson
from app.utils.geometry import point_in_polygon

DetectionLike = PersonDetection | TrackedPerson


def _fmt_mmss(seconds: float) -> str:
    total = max(0, int(seconds))
    mins, secs = divmod(total, 60)
    return f"{mins:02d}:{secs:02d}"


@dataclass
class ZoneState:
    # Legacy zone_intrusion state
    first_seen_at: float | None = None
    last_event_at: float = 0.0
    # 4-state zone_presence state machine
    status: str = "empty"  # "present" | "leaving" | "empty" | "alert"
    present_since: float | None = None
    empty_since: float | None = None
    yellow_since: float | None = None
    last_eval_mono: float | None = None
    session_started_at: float | None = None
    alert_count: int = 0
    total_alert_seconds: float = 0.0
    timeline: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ZoneEvaluation:
    has_zone: bool
    in_zone_count: int
    person_in_zone: bool
    should_emit_event: bool
    dwell_seconds: float
    persons: list[dict[str, Any]]
    # HUD & Rolling Timeline fields (matching PM's 3-state UI specification)
    status: str = "empty"  # "present" | "leaving" | "empty" | "alert" | "idle"
    ui_color: str = "yellow"  # "green" | "yellow" | "red" | "idle"
    status_label: str = "VÙNG TRỐNG"
    sub_label: str = "không có người 00:00"
    polygon_label: str = "TRỐNG"
    empty_duration: float = 0.0
    alert_count: int = 0
    total_alert_seconds: float = 0.0
    session_duration_seconds: float = 0.0
    timeline: list[dict[str, Any]] = field(default_factory=list)


class ZoneRuleEngine:
    """Evaluates detections against a polygon zone for presence monitoring or intrusion."""

    def __init__(
        self,
        confirm_seconds: float = 2.0,
        cooldown_seconds: float = 60.0,
        grace_seconds: float = 2.0,
        warning_seconds: float = 10.0,
        timeline_window_seconds: int = 1800,
        anchor_mode: str = "bottom_center",
        default_feature_type: str = "zone_intrusion",
    ) -> None:
        self.confirm_seconds = confirm_seconds
        self.cooldown_seconds = cooldown_seconds
        self.grace_seconds = grace_seconds
        self.warning_seconds = warning_seconds
        self.timeline_window_seconds = timeline_window_seconds
        self.anchor_mode = anchor_mode
        self.default_feature_type = default_feature_type
        self._states: dict[str, ZoneState] = {}

    def reset_stats(self, zone_key: str) -> None:
        """Reset counters, timers, and rolling timeline for a camera zone."""
        self._states.pop(zone_key, None)

    def _update_timeline(self, state: ZoneState, wall_now: float, ui_color: str) -> list[dict[str, Any]]:
        window = max(60, int(self.timeline_window_seconds))
        cutoff = wall_now - window

        if not state.timeline:
            state.timeline.append({"start": wall_now, "end": wall_now, "color": ui_color})
        elif state.timeline[-1]["color"] == ui_color:
            state.timeline[-1]["end"] = max(state.timeline[-1]["end"], wall_now)
        else:
            prev_end = state.timeline[-1]["end"]
            state.timeline.append({"start": prev_end, "end": max(prev_end, wall_now), "color": ui_color})

        state.timeline = [seg for seg in state.timeline if seg["end"] >= cutoff]
        if state.timeline and state.timeline[0]["start"] < cutoff:
            state.timeline[0]["start"] = cutoff

        return [
            {
                "start": round(seg["start"], 2),
                "end": round(seg["end"], 2),
                "color": seg["color"],
            }
            for seg in state.timeline
        ]

    def evaluate(
        self,
        zone_key: str,
        detections: Sequence[DetectionLike],
        polygon: Sequence[dict[str, float]],
        now: float | None = None,
        *,
        wall_time: float | None = None,
        feature_type: str | None = None,
        zone_name: str = "",
        grace_seconds: float | None = None,
        warning_seconds: float | None = None,
    ) -> ZoneEvaluation:
        ts = time.monotonic() if now is None else now
        wall_now = time.time() if wall_time is None else wall_time
        mode = (feature_type or self.default_feature_type).strip().lower()
        has_zone = len(polygon) >= 3
        zone_title = zone_name.strip().upper() if zone_name.strip() else "VÙNG GIÁM SÁT"

        persons: list[dict[str, Any]] = []
        in_zone_count = 0

        use_foot_anchor = mode == "zone_presence" and self.anchor_mode == "bottom_center"
        for idx, det in enumerate(detections):
            foot_x = det.foot_x if det.foot_x is not None else det.cx
            foot_y = det.foot_y if det.foot_y is not None else det.y2
            anchor_x = foot_x if use_foot_anchor else det.cx
            anchor_y = foot_y if use_foot_anchor else det.cy
            in_zone = point_in_polygon(anchor_x, anchor_y, polygon) if has_zone else False
            if in_zone:
                in_zone_count += 1
            track_id = getattr(det, "track_id", idx + 1)
            persons.append(
                {
                    "track_id": int(track_id),
                    "x1": det.x1,
                    "y1": det.y1,
                    "x2": det.x2,
                    "y2": det.y2,
                    "cx": det.cx,
                    "cy": det.cy,
                    "foot_x": foot_x,
                    "foot_y": foot_y,
                    "conf": det.conf,
                    "in_zone": in_zone,
                }
            )

        if mode == "zone_intrusion":
            return self._evaluate_intrusion(zone_key, has_zone, in_zone_count, persons, ts, zone_title)
        return self._evaluate_presence(
            zone_key=zone_key,
            has_zone=has_zone,
            in_zone_count=in_zone_count,
            persons=persons,
            ts=ts,
            wall_now=wall_now,
            zone_title=zone_title,
            grace_seconds=self.grace_seconds if grace_seconds is None else max(0.0, grace_seconds),
            warning_seconds=self.warning_seconds if warning_seconds is None else max(0.0, warning_seconds),
        )

    def _evaluate_intrusion(
        self,
        zone_key: str,
        has_zone: bool,
        in_zone_count: int,
        persons: list[dict[str, Any]],
        ts: float,
        zone_title: str,
    ) -> ZoneEvaluation:
        state = self._states.setdefault(zone_key, ZoneState())
        should_emit = False
        dwell = 0.0

        if has_zone and in_zone_count > 0:
            if state.first_seen_at is None:
                state.first_seen_at = ts
            dwell = ts - state.first_seen_at
            in_cooldown = (
                (ts - state.last_event_at) < self.cooldown_seconds if state.last_event_at else False
            )
            if dwell >= self.confirm_seconds and not in_cooldown:
                should_emit = True
                state.last_event_at = ts
                state.alert_count += 1
        else:
            state.first_seen_at = None

        if not has_zone:
            status, ui_color = "idle", "idle"
            status_label = "CHƯA VẼ VÙNG"
            sub_label = "Vẽ vùng giám sát để kích hoạt"
            polygon_label = ""
        elif in_zone_count > 0:
            status, ui_color = "alert", "red"
            status_label = "CẢNH BÁO XÂM NHẬP"
            sub_label = f"{in_zone_count} người trong vùng"
            polygon_label = f"{zone_title} · XÂM NHẬP ({in_zone_count})"
        else:
            status, ui_color = "present", "green"
            status_label = "AN TOÀN"
            sub_label = "Không có xâm nhập"
            polygon_label = f"{zone_title} · AN TOÀN"

        return ZoneEvaluation(
            has_zone=has_zone,
            in_zone_count=in_zone_count,
            person_in_zone=in_zone_count > 0,
            should_emit_event=should_emit,
            dwell_seconds=round(dwell, 2),
            persons=persons,
            status=status,
            ui_color=ui_color,
            status_label=status_label,
            sub_label=sub_label,
            polygon_label=polygon_label,
            alert_count=state.alert_count,
        )

    def _evaluate_presence(
        self,
        zone_key: str,
        has_zone: bool,
        in_zone_count: int,
        persons: list[dict[str, Any]],
        ts: float,
        wall_now: float,
        zone_title: str,
        grace_seconds: float,
        warning_seconds: float,
    ) -> ZoneEvaluation:
        state = self._states.setdefault(zone_key, ZoneState())

        if not has_zone:
            state.present_since = None
            state.empty_since = None
            state.yellow_since = None
            state.last_eval_mono = ts
            return ZoneEvaluation(
                has_zone=False,
                in_zone_count=0,
                person_in_zone=False,
                should_emit_event=False,
                dwell_seconds=0.0,
                persons=persons,
                status="idle",
                ui_color="idle",
                status_label="CHƯA VẼ VÙNG",
                sub_label="Vẽ vùng giám sát để kích hoạt",
                polygon_label="",
                empty_duration=0.0,
                alert_count=state.alert_count,
                total_alert_seconds=round(state.total_alert_seconds, 2),
                session_duration_seconds=0.0,
                timeline=[],
            )

        if state.session_started_at is None:
            state.session_started_at = ts

        dt = max(0.0, ts - state.last_eval_mono) if state.last_eval_mono is not None else 0.0
        if state.status == "alert":
            state.total_alert_seconds += dt
        state.last_eval_mono = ts

        should_emit = False
        dwell = 0.0
        empty_dur = 0.0

        if in_zone_count >= 1:
            state.status = "present"
            state.empty_since = None
            state.yellow_since = None
            if state.present_since is None:
                state.present_since = ts
            dwell = max(0.0, ts - state.present_since)
            ui_color = "green"
            status_label = "CÓ NHÂN VIÊN"
            sub_label = f"{in_zone_count} người trong vùng"
            polygon_label = f"{zone_title} · {in_zone_count} NV"
        else:
            state.present_since = None
            if state.empty_since is None:
                state.empty_since = ts
            empty_dur = max(0.0, ts - state.empty_since)

            if state.status == "present":
                if grace_seconds > 0.0:
                    state.status = "leaving"
                else:
                    state.status = "empty"
                    state.yellow_since = ts

            if state.status == "leaving" and empty_dur >= grace_seconds:
                state.status = "empty"
                state.yellow_since = state.empty_since + grace_seconds

            if state.status == "empty":
                if state.yellow_since is None:
                    state.yellow_since = ts
                yellow_dur = max(0.0, ts - state.yellow_since)
                if yellow_dur >= warning_seconds:
                    state.status = "alert"
                    state.alert_count += 1
                    in_cooldown = (
                        (ts - state.last_event_at) < self.cooldown_seconds
                        if state.last_event_at > 0.0
                        else False
                    )
                    if not in_cooldown:
                        should_emit = True
                        state.last_event_at = ts

            if state.status == "leaving":
                ui_color = "green"
                status_label = "CÓ NHÂN VIÊN"
                sub_label = "Vừa rời khỏi vùng"
                polygon_label = f"{zone_title} · VỪA RỜI VÙNG"
            elif state.status == "empty":
                ui_color = "yellow"
                status_label = "VÙNG TRỐNG"
                sub_label = f"không có người {_fmt_mmss(empty_dur)}"
                polygon_label = f"{zone_title} · TRỐNG"
            else:
                ui_color = "red"
                status_label = "KHÔNG CÓ NHÂN VIÊN"
                sub_label = f"Cảnh báo · vùng trống {_fmt_mmss(empty_dur)}"
                polygon_label = f"{zone_title} · KHÔNG CÓ NHÂN VIÊN"

        timeline = self._update_timeline(state, wall_now, ui_color)
        session_dur = max(0.0, ts - state.session_started_at)

        return ZoneEvaluation(
            has_zone=True,
            in_zone_count=in_zone_count,
            person_in_zone=in_zone_count > 0,
            should_emit_event=should_emit,
            dwell_seconds=round(dwell, 2),
            persons=persons,
            status=state.status,
            ui_color=ui_color,
            status_label=status_label,
            sub_label=sub_label,
            polygon_label=polygon_label,
            empty_duration=round(empty_dur, 2),
            alert_count=state.alert_count,
            total_alert_seconds=round(state.total_alert_seconds, 2),
            session_duration_seconds=round(session_dur, 2),
            timeline=timeline,
        )

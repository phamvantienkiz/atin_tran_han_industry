"""Zone intrusion rule engine with ATIN C08 dwell-time & cooldown state machine."""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass

from app.ai.detector import PersonDetection
from app.utils.geometry import point_in_polygon


@dataclass
class ZoneState:
    first_seen_at: float | None = None
    last_event_at: float = 0.0


@dataclass(frozen=True)
class ZoneEvaluation:
    has_zone: bool
    in_zone_count: int
    person_in_zone: bool
    should_emit_event: bool
    dwell_seconds: float
    persons: list[dict]


class ZoneRuleEngine:
    """Evaluates detections against a polygon zone with anti-spam dwell-time & cooldown."""

    def __init__(self, confirm_seconds: float = 2.0, cooldown_seconds: float = 60.0) -> None:
        self.confirm_seconds = confirm_seconds
        self.cooldown_seconds = cooldown_seconds
        self._states: dict[str, ZoneState] = {}

    def evaluate(
        self,
        zone_key: str,
        detections: Sequence[PersonDetection],
        polygon: Sequence[dict[str, float]],
        now: float | None = None,
    ) -> ZoneEvaluation:
        ts = time.monotonic() if now is None else now
        has_zone = len(polygon) >= 3
        persons: list[dict] = []
        in_zone_count = 0

        for det in detections:
            in_zone = point_in_polygon(det.cx, det.cy, polygon) if has_zone else False
            if in_zone:
                in_zone_count += 1
            persons.append(
                {
                    "x1": det.x1,
                    "y1": det.y1,
                    "x2": det.x2,
                    "y2": det.y2,
                    "cx": det.cx,
                    "cy": det.cy,
                    "conf": det.conf,
                    "in_zone": in_zone,
                }
            )

        state = self._states.setdefault(zone_key, ZoneState())
        should_emit = False
        dwell = 0.0

        if has_zone and in_zone_count > 0:
            if state.first_seen_at is None:
                state.first_seen_at = ts
            dwell = ts - state.first_seen_at
            in_cooldown = (ts - state.last_event_at) < self.cooldown_seconds if state.last_event_at else False
            if dwell >= self.confirm_seconds and not in_cooldown:
                should_emit = True
                state.last_event_at = ts
        else:
            state.first_seen_at = None

        return ZoneEvaluation(
            has_zone=has_zone,
            in_zone_count=in_zone_count,
            person_in_zone=in_zone_count > 0,
            should_emit_event=should_emit,
            dwell_seconds=round(dwell, 2),
            persons=persons,
        )

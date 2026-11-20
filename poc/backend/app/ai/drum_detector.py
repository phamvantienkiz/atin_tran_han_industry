"""Drum rotation detector using masked ROI motion analysis with person-occlusion immunity."""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np


@dataclass
class _DrumState:
    rotating: bool = False
    ema_motion: float = 0.0
    stopped_since: float | None = None
    last_ts: float = 0.0


class DrumRotationMonitor:
    """Tracks per-drum rotation state from consecutive frames and raises alerts after prolonged stops."""

    def __init__(
        self,
        stop_alert_seconds: float = 1800.0,
        diff_threshold: int = 18,
        start_motion_ratio: float = 0.035,
        stop_motion_ratio: float = 0.015,
        ema_alpha: float = 0.35,
        max_occlusion_ratio: float = 0.55,
    ) -> None:
        self.stop_alert_seconds = stop_alert_seconds
        self.diff_threshold = diff_threshold
        self.start_motion_ratio = start_motion_ratio
        self.stop_motion_ratio = stop_motion_ratio
        self.ema_alpha = ema_alpha
        self.max_occlusion_ratio = max_occlusion_ratio

        self._prev_gray: dict[str, np.ndarray] = {}
        self._states: dict[str, dict[str, _DrumState]] = {}

    def reset(self, cam_id: str) -> None:
        """Clear cached previous frame and drum timers for one camera."""
        self._prev_gray.pop(cam_id, None)
        self._states.pop(cam_id, None)

    def evaluate(
        self,
        cam_id: str,
        frame_bgr: np.ndarray,
        drums: Sequence[dict[str, Any]],
        persons: Sequence[dict[str, Any]],
        now: float | None = None,
    ) -> list[dict[str, Any]]:
        """Evaluate rotation state and 30-minute stop alert for each configured drum ROI."""
        if not drums:
            self._states.pop(cam_id, None)
            return []

        ts = time.monotonic() if now is None else now
        h, w = frame_bgr.shape[:2]
        # Downscale to max 640px wide for fast, noise-tolerant motion comparison
        scale = min(1.0, 640.0 / max(1, w))
        sw, sh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
        small = cv2.resize(frame_bgr, (sw, sh), interpolation=cv2.INTER_AREA) if scale < 1.0 else frame_bgr
        gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)

        prev_gray = self._prev_gray.get(cam_id)
        self._prev_gray[cam_id] = gray

        diff_bin: np.ndarray | None = None
        if prev_gray is not None and prev_gray.shape == gray.shape:
            diff = cv2.absdiff(prev_gray, gray)
            diff_bin = (diff > self.diff_threshold).astype(np.uint8)

        # Build person occlusion mask so workers walking in front do not trigger false rotation
        person_mask = np.zeros((sh, sw), dtype=np.uint8)
        for p in persons:
            px1 = max(0, int(p["x1"] * sw))
            py1 = max(0, int(p["y1"] * sh))
            px2 = min(sw, int(p["x2"] * sw))
            py2 = min(sh, int(p["y2"] * sh))
            if px2 > px1 and py2 > py1:
                person_mask[py1:py2, px1:px2] = 1

        cam_states = self._states.setdefault(cam_id, {})
        active_ids: set[str] = set()
        results: list[dict[str, Any]] = []

        for idx, drum in enumerate(drums):
            drum_id = str(drum.get("id") or f"drum_{idx + 1}")
            drum_name = str(drum.get("name") or f"Cối {idx + 1}")
            points = drum.get("points") or []
            if len(points) < 3:
                continue

            active_ids.add(drum_id)
            st = cam_states.get(drum_id)
            if st is None:
                st = _DrumState(rotating=False, ema_motion=0.0, stopped_since=ts, last_ts=ts)
                cam_states[drum_id] = st

            poly = np.array([[int(pt["x"] * sw), int(pt["y"] * sh)] for pt in points], dtype=np.int32)
            roi_mask = np.zeros((sh, sw), dtype=np.uint8)
            cv2.fillPoly(roi_mask, [poly], 1)

            roi_area = int(roi_mask.sum())
            if roi_area <= 0:
                continue

            visible_mask = roi_mask & (1 - person_mask)
            visible_area = int(visible_mask.sum())
            occlusion_ratio = 1.0 - (visible_area / roi_area)
            occluded = occlusion_ratio >= self.max_occlusion_ratio

            if diff_bin is not None and not occluded and visible_area > 0:
                changed_pixels = int((diff_bin & visible_mask).sum())
                raw_motion = changed_pixels / visible_area
                st.ema_motion = self.ema_alpha * raw_motion + (1.0 - self.ema_alpha) * st.ema_motion

                if st.rotating:
                    if st.ema_motion < self.stop_motion_ratio:
                        st.rotating = False
                        st.stopped_since = ts
                else:
                    if st.ema_motion >= self.start_motion_ratio:
                        st.rotating = True
                        st.stopped_since = None

            if st.rotating:
                st.stopped_since = None
                stopped_seconds = 0.0
            else:
                if st.stopped_since is None:
                    st.stopped_since = ts
                stopped_seconds = max(0.0, ts - st.stopped_since)

            st.last_ts = ts
            alert = (not st.rotating) and (stopped_seconds >= self.stop_alert_seconds)
            results.append(
                {
                    "id": drum_id,
                    "name": drum_name,
                    "rotating": st.rotating,
                    "label": "Đang xoay" if st.rotating else "Không xoay",
                    "stopped_seconds": round(stopped_seconds, 1),
                    "alert": alert,
                    "occluded": occluded,
                    "motion_score": round(st.ema_motion, 4),
                }
            )

        for stale_id in list(cam_states.keys()):
            if stale_id not in active_ids:
                cam_states.pop(stale_id, None)

        return results

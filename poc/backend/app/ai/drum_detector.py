"""Drum rotation detector using lagged ROI motion analysis with dual-frame person masking."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np


@dataclass
class _FrameSample:
    ts: float
    gray: np.ndarray
    person_mask: np.ndarray


@dataclass
class _DrumState:
    rotating: bool = False
    ema_motion: float = 0.0
    stopped_since: float | None = None
    rotate_candidate_since: float | None = None
    stop_candidate_since: float | None = None
    last_ts: float = 0.0


class DrumRotationMonitor:
    """Tracks per-drum rotation state using a ~0.6s frame lag and dual-frame person occlusion masking."""

    def __init__(
        self,
        stop_alert_seconds: float = 1800.0,
        frame_lag_seconds: float = 0.6,
        diff_threshold: int = 12,
        start_motion_ratio: float = 0.030,
        stop_motion_ratio: float = 0.014,
        ema_alpha: float = 0.35,
        confirm_rotate_seconds: float = 1.8,
        confirm_stop_seconds: float = 2.0,
        max_occlusion_ratio: float = 0.45,
        person_pad_px: int = 14,
    ) -> None:
        self.stop_alert_seconds = stop_alert_seconds
        self.frame_lag_seconds = frame_lag_seconds
        self.diff_threshold = diff_threshold
        self.start_motion_ratio = start_motion_ratio
        self.stop_motion_ratio = stop_motion_ratio
        self.ema_alpha = ema_alpha
        self.confirm_rotate_seconds = confirm_rotate_seconds
        self.confirm_stop_seconds = confirm_stop_seconds
        self.max_occlusion_ratio = max_occlusion_ratio
        self.person_pad_px = person_pad_px

        self._history: dict[str, deque[_FrameSample]] = {}
        self._states: dict[str, dict[str, _DrumState]] = {}

    def reset(self, cam_id: str) -> None:
        """Clear cached frame history and drum timers for one camera."""
        self._history.pop(cam_id, None)
        self._states.pop(cam_id, None)

    def _pick_lag_sample(self, history: deque[_FrameSample], now: float) -> _FrameSample | None:
        if not history:
            return None
        target_ts = now - self.frame_lag_seconds
        best: _FrameSample | None = None
        for sample in history:
            if sample.ts <= target_ts:
                best = sample
            else:
                break
        if best is not None:
            return best
        # Fall back to oldest sample if history is shorter than frame_lag_seconds (at least 0.25s)
        oldest = history[0]
        return oldest if (now - oldest.ts) >= 0.25 else None

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
            self._history.pop(cam_id, None)
            return []

        ts = time.monotonic() if now is None else now
        h, w = frame_bgr.shape[:2]
        scale = min(1.0, 640.0 / max(1, w))
        sw, sh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
        small = cv2.resize(frame_bgr, (sw, sh), interpolation=cv2.INTER_AREA) if scale < 1.0 else frame_bgr
        gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)

        # Build padded person mask so workers walking near/through ROI do not cause false spikes
        person_mask = np.zeros((sh, sw), dtype=np.uint8)
        pad = self.person_pad_px
        for p in persons:
            px1 = max(0, int(p["x1"] * sw) - pad)
            py1 = max(0, int(p["y1"] * sh) - pad)
            px2 = min(sw, int(p["x2"] * sw) + pad)
            py2 = min(sh, int(p["y2"] * sh) + pad)
            if px2 > px1 and py2 > py1:
                person_mask[py1:py2, px1:px2] = 1

        history = self._history.setdefault(cam_id, deque(maxlen=40))
        if history and history[-1].gray.shape != gray.shape:
            history.clear()
        lag_sample = self._pick_lag_sample(history, ts)
        history.append(_FrameSample(ts=ts, gray=gray, person_mask=person_mask))
        # Prune frames older than 2.5s
        while len(history) > 2 and (ts - history[0].ts) > max(2.5, self.frame_lag_seconds * 3):
            history.popleft()

        diff_bin: np.ndarray | None = None
        combined_person_mask = person_mask
        if lag_sample is not None:
            diff = cv2.absdiff(lag_sample.gray, gray)
            diff_bin = (diff > self.diff_threshold).astype(np.uint8)
            combined_person_mask = person_mask | lag_sample.person_mask

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

            visible_mask = roi_mask & (1 - combined_person_mask)
            visible_area = int(visible_mask.sum())
            occlusion_ratio = 1.0 - (visible_area / roi_area)
            occluded = occlusion_ratio >= self.max_occlusion_ratio

            if occluded:
                # Hold previous state while a worker is passing through the ROI
                st.rotate_candidate_since = None
                st.stop_candidate_since = None
            elif diff_bin is not None and visible_area > 0:
                changed_pixels = int((diff_bin & visible_mask).sum())
                raw_motion = changed_pixels / visible_area
                st.ema_motion = self.ema_alpha * raw_motion + (1.0 - self.ema_alpha) * st.ema_motion

                if st.rotating:
                    st.rotate_candidate_since = None
                    if st.ema_motion < self.stop_motion_ratio:
                        if st.stop_candidate_since is None:
                            st.stop_candidate_since = ts
                        elif (ts - st.stop_candidate_since) >= self.confirm_stop_seconds:
                            st.rotating = False
                            st.stopped_since = ts
                            st.stop_candidate_since = None
                    else:
                        st.stop_candidate_since = None
                else:
                    st.stop_candidate_since = None
                    if st.ema_motion >= self.start_motion_ratio:
                        if st.rotate_candidate_since is None:
                            st.rotate_candidate_since = ts
                        elif (ts - st.rotate_candidate_since) >= self.confirm_rotate_seconds:
                            st.rotating = True
                            st.stopped_since = None
                            st.rotate_candidate_since = None
                    else:
                        st.rotate_candidate_since = None

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

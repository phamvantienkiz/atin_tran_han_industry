"""ByteTrack person tracker with IoU raw-box snapping (zero Kalman lag)."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import supervision as sv

from app.ai.detector import PersonDetection

_VIRTUAL_W = 1280.0
_VIRTUAL_H = 720.0


@dataclass(frozen=True)
class TrackedPerson:
    track_id: int
    x1: float
    y1: float
    x2: float
    y2: float
    cx: float
    cy: float
    foot_x: float
    foot_y: float
    conf: float


def _snap_box_to_raw(
    track_box: np.ndarray,
    raw_boxes: np.ndarray,
    raw_confs: np.ndarray,
    min_iou: float = 0.45,
) -> tuple[np.ndarray, float]:
    """Replace Kalman-smoothed box with exact current-frame YOLO box if IoU >= min_iou."""
    if len(raw_boxes) == 0:
        return track_box, 0.5

    x1 = np.maximum(track_box[0], raw_boxes[:, 0])
    y1 = np.maximum(track_box[1], raw_boxes[:, 1])
    x2 = np.minimum(track_box[2], raw_boxes[:, 2])
    y2 = np.minimum(track_box[3], raw_boxes[:, 3])

    inter = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    area_t = max(1e-6, float((track_box[2] - track_box[0]) * (track_box[3] - track_box[1])))
    area_r = np.maximum(
        1e-6,
        (raw_boxes[:, 2] - raw_boxes[:, 0]) * (raw_boxes[:, 3] - raw_boxes[:, 1]),
    )
    ious = inter / (area_t + area_r - inter)

    best_idx = int(np.argmax(ious))
    if float(ious[best_idx]) >= min_iou:
        return raw_boxes[best_idx].astype(np.float32), float(raw_confs[best_idx])
    return track_box.astype(np.float32), float(raw_confs[best_idx])


class CameraTracker:
    """Maintains an isolated ByteTrack instance per camera with raw-box IoU snapping."""

    def __init__(
        self,
        track_activation_threshold: float = 0.25,
        lost_track_buffer: int = 30,
        minimum_matching_threshold: float = 0.8,
        frame_rate: int = 12,
        snap_min_iou: float = 0.45,
    ) -> None:
        self._track_activation_threshold = track_activation_threshold
        self._lost_track_buffer = lost_track_buffer
        self._minimum_matching_threshold = minimum_matching_threshold
        self._frame_rate = frame_rate
        self._snap_min_iou = snap_min_iou
        self._lock = threading.Lock()
        self._trackers: dict[str, sv.ByteTrack] = {}

    def _get_tracker(self, cam_id: str) -> sv.ByteTrack:
        tracker = self._trackers.get(cam_id)
        if tracker is None:
            tracker = sv.ByteTrack(
                track_activation_threshold=self._track_activation_threshold,
                lost_track_buffer=self._lost_track_buffer,
                minimum_matching_threshold=self._minimum_matching_threshold,
                frame_rate=self._frame_rate,
            )
            self._trackers[cam_id] = tracker
        return tracker

    def reset(self, cam_id: str) -> None:
        """Reset ByteTrack state for a camera (e.g., on stats reset or deletion)."""
        with self._lock:
            self._trackers.pop(cam_id, None)

    def update(self, cam_id: str, detections: Sequence[PersonDetection]) -> list[TrackedPerson]:
        """Update tracker with normalized [0..1] detections and return snapped TrackedPerson list."""
        with self._lock:
            tracker = self._get_tracker(cam_id)

            if not detections:
                tracker.update_with_detections(sv.Detections.empty())
                return []

            raw_boxes = np.array(
                [
                    [
                        d.x1 * _VIRTUAL_W,
                        d.y1 * _VIRTUAL_H,
                        d.x2 * _VIRTUAL_W,
                        d.y2 * _VIRTUAL_H,
                    ]
                    for d in detections
                ],
                dtype=np.float32,
            )
            raw_confs = np.array([d.conf for d in detections], dtype=np.float32)
            raw_classes = np.zeros(len(detections), dtype=int)

            sv_dets = sv.Detections(
                xyxy=raw_boxes,
                confidence=raw_confs,
                class_id=raw_classes,
            )
            tracked = tracker.update_with_detections(sv_dets)

        if len(tracked) == 0 or tracked.tracker_id is None:
            return []

        results: list[TrackedPerson] = []
        for idx in range(len(tracked)):
            tid = tracked.tracker_id[idx]
            if tid is None:
                continue
            snapped_box, snapped_conf = _snap_box_to_raw(
                tracked.xyxy[idx],
                raw_boxes,
                raw_confs,
                min_iou=self._snap_min_iou,
            )
            nx1 = max(0.0, min(1.0, float(snapped_box[0]) / _VIRTUAL_W))
            ny1 = max(0.0, min(1.0, float(snapped_box[1]) / _VIRTUAL_H))
            nx2 = max(0.0, min(1.0, float(snapped_box[2]) / _VIRTUAL_W))
            ny2 = max(0.0, min(1.0, float(snapped_box[3]) / _VIRTUAL_H))
            cx = round((nx1 + nx2) / 2.0, 4)
            cy = round((ny1 + ny2) / 2.0, 4)
            results.append(
                TrackedPerson(
                    track_id=int(tid),
                    x1=round(nx1, 4),
                    y1=round(ny1, 4),
                    x2=round(nx2, 4),
                    y2=round(ny2, 4),
                    cx=cx,
                    cy=cy,
                    foot_x=cx,
                    foot_y=round(ny2, 4),
                    conf=round(snapped_conf, 3),
                )
            )
        return results

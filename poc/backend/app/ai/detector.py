"""Pure ONNX Runtime YOLO person detector (decoupled from transport/HTTP)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort


@dataclass(frozen=True)
class PersonDetection:
    x1: float
    y1: float
    x2: float
    y2: float
    cx: float
    cy: float
    conf: float


class YoloPersonDetector:
    """CPU ONNX Runtime inference engine for class 0 (person)."""

    def __init__(
        self,
        model_path: Path,
        conf: float = 0.45,
        imgsz: int = 640,
        nms_iou: float = 0.45,
    ) -> None:
        self.model_path = model_path
        self.conf = conf
        self.imgsz = imgsz
        self.nms_iou = nms_iou
        self._session: ort.InferenceSession | None = None
        self._input_name: str = "images"

    def ensure_session(self) -> ort.InferenceSession:
        if self._session is None:
            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self._session = ort.InferenceSession(
                str(self.model_path),
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
            self._input_name = self._session.get_inputs()[0].name
        return self._session

    def detect(self, frame: np.ndarray) -> list[PersonDetection]:
        """Run inference on a BGR image and return normalized [0..1] detections."""
        h, w = frame.shape[:2]
        session = self.ensure_session()
        blob, scale, pad_x, pad_y = self._preprocess(frame)
        outputs = session.run(None, {self._input_name: blob})
        raw_boxes = self._postprocess(outputs[0], w, h, scale, pad_x, pad_y)

        detections: list[PersonDetection] = []
        for x1, y1, x2, y2, score in raw_boxes:
            nx1 = max(0.0, min(1.0, x1 / w))
            ny1 = max(0.0, min(1.0, y1 / h))
            nx2 = max(0.0, min(1.0, x2 / w))
            ny2 = max(0.0, min(1.0, y2 / h))
            detections.append(
                PersonDetection(
                    x1=round(nx1, 4),
                    y1=round(ny1, 4),
                    x2=round(nx2, 4),
                    y2=round(ny2, 4),
                    cx=round((nx1 + nx2) / 2.0, 4),
                    cy=round((ny1 + ny2) / 2.0, 4),
                    conf=round(float(score), 3),
                )
            )
        return detections

    def _preprocess(self, frame: np.ndarray) -> tuple[np.ndarray, float, float, float]:
        orig_h, orig_w = frame.shape[:2]
        size = self.imgsz
        scale = min(size / orig_w, size / orig_h)
        new_w, new_h = round(orig_w * scale), round(orig_h * scale)
        pad_x = (size - new_w) / 2.0
        pad_y = (size - new_h) / 2.0

        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((size, size, 3), 114, dtype=np.uint8)
        top = round(pad_y - 0.1)
        left = round(pad_x - 0.1)
        canvas[top : top + new_h, left : left + new_w] = resized

        rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
        blob = np.transpose(rgb.astype(np.float32) / 255.0, (2, 0, 1))[None, ...]
        return np.ascontiguousarray(blob), scale, float(left), float(top)

    def _postprocess(
        self,
        output: np.ndarray,
        orig_w: int,
        orig_h: int,
        scale: float,
        pad_x: float,
        pad_y: float,
    ) -> list[tuple[float, float, float, float, float]]:
        preds = output[0].T
        scores = preds[:, 4]
        mask = scores >= self.conf
        if not np.any(mask):
            return []

        filtered = preds[mask]
        filt_scores = scores[mask]
        cx = filtered[:, 0]
        cy = filtered[:, 1]
        bw = filtered[:, 2]
        bh = filtered[:, 3]
        x1 = cx - bw / 2.0
        y1 = cy - bh / 2.0

        boxes_xywh = np.stack([x1, y1, bw, bh], axis=1).tolist()
        indices = cv2.dnn.NMSBoxes(boxes_xywh, filt_scores.tolist(), self.conf, self.nms_iou)
        if len(indices) == 0:
            return []

        results: list[tuple[float, float, float, float, float]] = []
        for idx in np.asarray(indices).flatten():
            bx1 = (x1[idx] - pad_x) / scale
            by1 = (y1[idx] - pad_y) / scale
            bx2 = (x1[idx] + bw[idx] - pad_x) / scale
            by2 = (y1[idx] + bh[idx] - pad_y) / scale
            results.append(
                (
                    max(0.0, min(float(orig_w), float(bx1))),
                    max(0.0, min(float(orig_h), float(by1))),
                    max(0.0, min(float(orig_w), float(bx2))),
                    max(0.0, min(float(orig_h), float(by2))),
                    float(filt_scores[idx]),
                )
            )
        return results

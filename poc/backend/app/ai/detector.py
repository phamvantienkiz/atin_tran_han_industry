"""Pure ONNX Runtime YOLO person detector (CPU / CUDA FP16, zero ultralytics)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import onnxruntime as ort

from app.core.logging import get_logger

logger = get_logger("app.ai.detector")


@dataclass(frozen=True)
class PersonDetection:
    x1: float
    y1: float
    x2: float
    y2: float
    cx: float
    cy: float
    conf: float
    foot_x: float | None = None
    foot_y: float | None = None

    def __post_init__(self) -> None:
        if self.foot_x is None:
            object.__setattr__(self, "foot_x", self.cx)
        if self.foot_y is None:
            object.__setattr__(self, "foot_y", self.y2)


class YoloPersonDetector:
    """ONNX Runtime inference engine for class 0 (person) with CUDA VRAM cap & CPU fallback."""

    def __init__(
        self,
        model_path: Path,
        conf: float = 0.40,
        imgsz: int = 640,
        nms_iou: float = 0.45,
        runtime: str = "auto",
        vram_limit_mb: int = 1024,
    ) -> None:
        self.model_path = model_path
        self.conf = conf
        self.imgsz = imgsz
        self.nms_iou = nms_iou
        self.runtime = runtime.lower()
        self.vram_limit_mb = vram_limit_mb

        self._session: ort.InferenceSession | None = None
        self._input_name: str = "images"
        self._input_dtype: np.dtype[Any] = np.dtype(np.float32)
        self._dynamic_batch: bool = False
        self.active_provider: str = "uninitialized"

    def ensure_session(self) -> ort.InferenceSession:
        if self._session is None:
            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            available = ort.get_available_providers()
            use_cuda = (
                self.runtime in ("auto", "cuda", "onnx_cuda")
                and "CUDAExecutionProvider" in available
            )

            providers: list[Any]
            if use_cuda:
                cuda_opts = {
                    "device_id": "0",
                    "arena_extend_strategy": "kNextPowerOfTwo",
                    "gpu_mem_limit": str(int(self.vram_limit_mb * 1024 * 1024)),
                    "cudnn_conv_algo_search": "HEURISTIC",
                    "do_copy_in_default_stream": "1",
                }
                providers = [("CUDAExecutionProvider", cuda_opts), "CPUExecutionProvider"]
            else:
                providers = ["CPUExecutionProvider"]

            try:
                session = ort.InferenceSession(
                    str(self.model_path),
                    sess_options=opts,
                    providers=providers,
                )
            except Exception as exc:
                fallback_candidates = [
                    self.model_path.parent / "yolo26s.onnx",
                    self.model_path.parent / "yolo26s_best.onnx",
                ]
                fallback_path = next(
                    (p for p in fallback_candidates if p != self.model_path and p.is_file()),
                    None,
                )
                if fallback_path is not None:
                    logger.warning(
                        "Failed to load model %s (%s); falling back to %s",
                        self.model_path.name,
                        exc,
                        fallback_path.name,
                    )
                    self.model_path = fallback_path
                    session = ort.InferenceSession(
                        str(self.model_path),
                        sess_options=opts,
                        providers=providers,
                    )
                else:
                    raise
            inp = session.get_inputs()[0]
            self._input_name = inp.name
            self._input_dtype = (
                np.dtype(np.float16) if "float16" in str(inp.type).lower() else np.dtype(np.float32)
            )
            dim0 = inp.shape[0] if inp.shape else 1
            self._dynamic_batch = isinstance(dim0, str) or dim0 is None or dim0 != 1
            active_providers = session.get_providers()
            self.active_provider = active_providers[0] if active_providers else "CPUExecutionProvider"

            meta_map = session.get_modelmeta().custom_metadata_map or {}
            model_names = meta_map.get("names", "unknown")

            # Warmup pass to initialize CUDA context & cuDNN kernels before live stream hits
            dummy = np.zeros((1, 3, self.imgsz, self.imgsz), dtype=self._input_dtype)
            session.run(None, {self._input_name: dummy})

            self._session = session
            logger.info(
                "Loaded YOLO ONNX model=%s dtype=%s classes=%s active_provider=%s dynamic_batch=%s vram_limit_mb=%s",
                self.model_path.name,
                self._input_dtype,
                model_names,
                self.active_provider,
                self._dynamic_batch,
                self.vram_limit_mb if "CUDA" in self.active_provider else 0,
            )
        return self._session

    def detect_batch(self, frames: Sequence[np.ndarray]) -> list[list[PersonDetection]]:
        """Run inference on one or more BGR frames and return normalized [0..1] detections."""
        if not frames:
            return []

        session = self.ensure_session()
        prepped = [self._preprocess(frame) for frame in frames]
        shapes = [frame.shape[:2] for frame in frames]

        raw_outputs: list[np.ndarray] = []
        if self._dynamic_batch and len(prepped) > 1:
            batch_blob = np.concatenate([p[0] for p in prepped], axis=0)
            batch_out = session.run(None, {self._input_name: batch_blob})[0]
            for i in range(len(prepped)):
                raw_outputs.append(batch_out[i : i + 1])
        else:
            for blob, _, _, _ in prepped:
                out = session.run(None, {self._input_name: blob})[0]
                raw_outputs.append(out)

        batch_results: list[list[PersonDetection]] = []
        for (h, w), (_, scale, pad_x, pad_y), output in zip(shapes, prepped, raw_outputs):
            raw_boxes = self._postprocess(output, w, h, scale, pad_x, pad_y)
            detections: list[PersonDetection] = []
            for x1, y1, x2, y2, score in raw_boxes:
                nx1 = max(0.0, min(1.0, x1 / w))
                ny1 = max(0.0, min(1.0, y1 / h))
                nx2 = max(0.0, min(1.0, x2 / w))
                ny2 = max(0.0, min(1.0, y2 / h))
                cx = round((nx1 + nx2) / 2.0, 4)
                cy = round((ny1 + ny2) / 2.0, 4)
                detections.append(
                    PersonDetection(
                        x1=round(nx1, 4),
                        y1=round(ny1, 4),
                        x2=round(nx2, 4),
                        y2=round(ny2, 4),
                        cx=cx,
                        cy=cy,
                        foot_x=cx,
                        foot_y=round(ny2, 4),
                        conf=round(float(score), 3),
                    )
                )
            batch_results.append(detections)
        return batch_results

    def detect(self, frame: np.ndarray) -> list[PersonDetection]:
        """Run inference on a single BGR image and return normalized [0..1] detections."""
        return self.detect_batch([frame])[0]

    def preprocess_frame(self, frame: np.ndarray) -> tuple[np.ndarray, int, int, float, float, float]:
        """Letterbox & normalize a BGR frame into model input tensor (thread-safe for prefetch)."""
        orig_h, orig_w = frame.shape[:2]
        blob, scale, pad_x, pad_y = self._preprocess(frame)
        return blob, orig_w, orig_h, scale, pad_x, pad_y

    def infer_preprocessed(
        self,
        blob: np.ndarray,
        orig_w: int,
        orig_h: int,
        scale: float,
        pad_x: float,
        pad_y: float,
    ) -> list[PersonDetection]:
        """Run ONNX inference on a pre-built input tensor and return normalized [0..1] detections."""
        session = self.ensure_session()
        if blob.dtype != self._input_dtype:
            blob = np.ascontiguousarray(blob.astype(self._input_dtype, copy=False))
        output = session.run(None, {self._input_name: blob})[0]
        raw_boxes = self._postprocess(output, orig_w, orig_h, scale, pad_x, pad_y)
        detections: list[PersonDetection] = []
        for x1, y1, x2, y2, score in raw_boxes:
            nx1 = max(0.0, min(1.0, x1 / orig_w))
            ny1 = max(0.0, min(1.0, y1 / orig_h))
            nx2 = max(0.0, min(1.0, x2 / orig_w))
            ny2 = max(0.0, min(1.0, y2 / orig_h))
            cx = round((nx1 + nx2) / 2.0, 4)
            cy = round((ny1 + ny2) / 2.0, 4)
            detections.append(
                PersonDetection(
                    x1=round(nx1, 4),
                    y1=round(ny1, 4),
                    x2=round(nx2, 4),
                    y2=round(ny2, 4),
                    cx=cx,
                    cy=cy,
                    foot_x=cx,
                    foot_y=round(ny2, 4),
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
        if self._input_dtype != np.float32:
            blob = blob.astype(self._input_dtype, copy=False)
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
        preds = np.asarray(output[0], dtype=np.float32).T
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

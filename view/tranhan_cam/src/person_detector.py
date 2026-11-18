"""YOLO26 CPU person-in-zone detector (ONNX Runtime) for ATIN Tran Han Live View."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable

import cv2
import httpx
import numpy as np
import onnxruntime as ort


def point_in_polygon(px: float, py: float, polygon: list[dict[str, float]]) -> bool:
    """Return True if normalized point (px, py) lies inside polygon using ray casting."""
    n = len(polygon)
    if n < 3:
        return False

    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]["x"], polygon[i]["y"]
        xj, yj = polygon[j]["x"], polygon[j]["y"]
        intersects = ((yi > py) != (yj > py)) and (
            px < (xj - xi) * (py - yi) / ((yj - yi) or 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


class PersonZoneDetector:
    """Background CPU worker that runs YOLO26s person detection on camera snapshots."""

    def __init__(
        self,
        model_path: Path,
        nvr_base_url: str,
        nvr_user: str,
        nvr_pass: str,
        load_cameras_fn: Callable[[], list[dict[str, Any]]],
        conf: float = 0.45,
        imgsz: int = 640,
        interval_sec: float = 0.5,
    ) -> None:
        self.model_path = model_path
        self.nvr_base_url = nvr_base_url
        self.nvr_user = nvr_user
        self.nvr_pass = nvr_pass
        self.load_cameras_fn = load_cameras_fn
        self.conf = conf
        self.imgsz = imgsz
        self.interval_sec = interval_sec

        self._session: ort.InferenceSession | None = None
        self._input_name: str = "images"
        self._nms_iou: float = 0.45
        self._lock = threading.Lock()
        self._results: dict[str, dict[str, Any]] = {}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="yolo26-zone-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def get_all(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return dict(self._results)

    def _ensure_session(self) -> ort.InferenceSession:
        """Lazily initialize the CPU ONNX Runtime inference session."""
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

    def _preprocess(self, frame: np.ndarray) -> tuple[np.ndarray, float, float, float]:
        """Letterbox-resize BGR frame to imgsz x imgsz and convert to NCHW float32."""
        orig_h, orig_w = frame.shape[:2]
        size = self.imgsz
        scale = min(size / orig_w, size / orig_h)
        new_w, new_h = int(round(orig_w * scale)), int(round(orig_h * scale))
        pad_x = (size - new_w) / 2.0
        pad_y = (size - new_h) / 2.0

        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((size, size, 3), 114, dtype=np.uint8)
        top = int(round(pad_y - 0.1))
        left = int(round(pad_x - 0.1))
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
        """Decode (1, 84, 8400) YOLO output for class 0 (person) with NMS."""
        preds = output[0].T  # (8400, 84)
        scores = preds[:, 4]  # class 0 = person
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
        indices = cv2.dnn.NMSBoxes(boxes_xywh, filt_scores.tolist(), self.conf, self._nms_iou)
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

    def _detect_camera(
        self, client: httpx.Client, session: ort.InferenceSession, cam: dict[str, Any]
    ) -> dict[str, Any]:
        cam_id = cam["id"]
        zone = cam.get("zone") or []
        has_zone = len(zone) >= 3
        url = f"{self.nvr_base_url}/cgi-bin/snapshot.cgi?channel={cam['channel']}"

        resp = client.get(url)
        if resp.status_code != 200:
            return {
                "cam_id": cam_id,
                "has_zone": has_zone,
                "person_in_zone": False,
                "in_zone_count": 0,
                "total_persons": 0,
                "persons": [],
                "error": f"HTTP {resp.status_code}",
                "updated_at": time.time(),
            }

        buf = np.frombuffer(resp.content, dtype=np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if frame is None:
            return {
                "cam_id": cam_id,
                "has_zone": has_zone,
                "person_in_zone": False,
                "in_zone_count": 0,
                "total_persons": 0,
                "persons": [],
                "error": "Decode failed",
                "updated_at": time.time(),
            }

        h, w = frame.shape[:2]
        t0 = time.perf_counter()
        blob, scale, pad_x, pad_y = self._preprocess(frame)
        outputs = session.run(None, {self._input_name: blob})
        detections = self._postprocess(outputs[0], w, h, scale, pad_x, pad_y)
        inference_ms = round((time.perf_counter() - t0) * 1000)

        persons: list[dict[str, Any]] = []
        in_zone_count = 0

        for x1, y1, x2, y2, score in detections:
            nx1 = max(0.0, min(1.0, x1 / w))
            ny1 = max(0.0, min(1.0, y1 / h))
            nx2 = max(0.0, min(1.0, x2 / w))
            ny2 = max(0.0, min(1.0, y2 / h))
            # Diagonal midpoint of the bounding box
            cx = (nx1 + nx2) / 2.0
            cy = (ny1 + ny2) / 2.0
            in_zone = point_in_polygon(cx, cy, zone) if has_zone else False
            if in_zone:
                in_zone_count += 1
            persons.append(
                {
                    "x1": round(nx1, 4),
                    "y1": round(ny1, 4),
                    "x2": round(nx2, 4),
                    "y2": round(ny2, 4),
                    "cx": round(cx, 4),
                    "cy": round(cy, 4),
                    "conf": round(float(score), 3),
                    "in_zone": in_zone,
                }
            )

        return {
            "cam_id": cam_id,
            "has_zone": has_zone,
            "person_in_zone": in_zone_count > 0,
            "in_zone_count": in_zone_count,
            "total_persons": len(persons),
            "persons": persons,
            "inference_ms": inference_ms,
            "updated_at": time.time(),
        }

    def _run_loop(self) -> None:
        session = self._ensure_session()
        auth = httpx.DigestAuth(self.nvr_user, self.nvr_pass)
        with httpx.Client(auth=auth, timeout=6.0) as client:
            while not self._stop_event.is_set():
                cameras = [
                    c for c in self.load_cameras_fn()
                    if c.get("enabled", True) and len(c.get("zone") or []) >= 3
                ]
                if not cameras:
                    self._stop_event.wait(1.0)
                    continue

                for cam in cameras:
                    if self._stop_event.is_set():
                        break
                    try:
                        result = self._detect_camera(client, session, cam)
                    except Exception as exc:
                        result = {
                            "cam_id": cam["id"],
                            "has_zone": len(cam.get("zone") or []) >= 3,
                            "person_in_zone": False,
                            "in_zone_count": 0,
                            "total_persons": 0,
                            "persons": [],
                            "error": str(exc),
                            "updated_at": time.time(),
                        }
                    with self._lock:
                        self._results[cam["id"]] = result

                self._stop_event.wait(self.interval_sec)

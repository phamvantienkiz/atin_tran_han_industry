"""YOLO26 CPU multi-model detector (Cam1 PPE + Cam2 Person-in-Zone) for ATIN Tran Han Live View."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time
from pathlib import Path
from typing import Any, Callable

import cv2
import httpx
import numpy as np
import torch
from ultralytics import YOLO

PPE_VIOLATION_CLASSES = {"incorrect_mask", "no_glove", "no_hairnet", "no_mask"}


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


def resolve_camera_task(cam: dict[str, Any]) -> str:
    """Resolve which AI task ('cam1_ppe', 'cam2_person', or 'none') applies to a camera."""
    explicit = (cam.get("ai_task") or "auto").strip()
    if explicit in {"none", "cam1_ppe", "cam2_person"}:
        return explicit

    text = f"{cam.get('name', '')} {cam.get('note', '')}".lower()
    if "bảo hộ" in text or "bao ho" in text or "ppe" in text:
        return "cam1_ppe"
    if "tăng trọng" in text or "tang trong" in text or "định hình" in text or "dinh hinh" in text:
        return "cam2_person"
    return "none"


class _CameraStreamReader:
    """Background MJPEG (subtype=1) reader that keeps the latest decoded frame."""

    def __init__(self, nvr_base_url: str, nvr_user: str, nvr_pass: str, channel: int) -> None:
        self.url = f"{nvr_base_url}/cgi-bin/mjpg/video.cgi?channel={channel}&subtype=1"
        self.auth = httpx.DigestAuth(nvr_user, nvr_pass)
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._frame_ts: float = 0.0
        self._error: str | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"mjpeg-ch{channel}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def get_latest(self) -> tuple[np.ndarray | None, float, str | None]:
        with self._lock:
            return self._frame, self._frame_ts, self._error

    def _run(self) -> None:
        timeout = httpx.Timeout(8.0, read=15.0)
        with httpx.Client(auth=self.auth, timeout=timeout) as client:
            while not self._stop.is_set():
                buf = bytearray()
                try:
                    with client.stream("GET", self.url) as resp:
                        if resp.status_code != 200:
                            with self._lock:
                                self._error = f"HTTP {resp.status_code}"
                            self._stop.wait(1.5)
                            continue
                        with self._lock:
                            self._error = None
                        for chunk in resp.iter_bytes(chunk_size=16384):
                            if self._stop.is_set():
                                break
                            buf.extend(chunk)
                            while True:
                                start = buf.find(b"\xff\xd8")
                                if start == -1:
                                    if len(buf) > 65536:
                                        buf.clear()
                                    break
                                end = buf.find(b"\xff\xd9", start + 2)
                                if end == -1:
                                    if start > 0:
                                        del buf[:start]
                                    break
                                jpg = bytes(buf[start : end + 2])
                                del buf[: end + 2]
                                frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                                if frame is not None:
                                    with self._lock:
                                        self._frame = frame
                                        self._frame_ts = time.time()
                                        self._error = None
                except Exception as exc:
                    with self._lock:
                        self._error = str(exc)
                    self._stop.wait(1.0)


class PersonZoneDetector:
    """Background CPU worker that runs YOLO26 ONNX models when enabled."""

    def __init__(
        self,
        model_paths: dict[str, Path],
        nvr_base_url: str,
        nvr_user: str,
        nvr_pass: str,
        load_cameras_fn: Callable[[], list[dict[str, Any]]],
        conf: float = 0.45,
        imgsz: int = 640,
        interval_sec: float = 0.2,
    ) -> None:
        self.model_paths = model_paths
        self.nvr_base_url = nvr_base_url
        self.nvr_user = nvr_user
        self.nvr_pass = nvr_pass
        self.load_cameras_fn = load_cameras_fn
        self.conf = conf
        self.imgsz = imgsz
        self.interval_sec = interval_sec
        self.use_cuda = torch.cuda.is_available()
        self.device: int | str = 0 if self.use_cuda else "cpu"
        self.device_label = "GPU" if self.use_cuda else "CPU"

        self._models: dict[str, YOLO] = {}
        self._readers: dict[str, _CameraStreamReader] = {}
        self._last_frame_ts: dict[str, float] = {}
        self._lock = threading.Lock()
        self._results: dict[str, dict[str, Any]] = {}
        self._stats: dict[str, dict[str, Any]] = {}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="yolo26-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        for reader in self._readers.values():
            reader.stop()
        self._readers.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def get_all(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return dict(self._results)

    def _ensure_model(self, task_key: str) -> YOLO:
        if task_key not in self._models:
            path = self.model_paths[task_key]
            if self.use_cuda:
                pt_path = path.with_suffix(".pt")
                if pt_path.is_file():
                    path = pt_path
            if not path.is_file():
                raise FileNotFoundError(f"Không tìm thấy model: {path}")
            self._models[task_key] = YOLO(str(path), task="detect")
        return self._models[task_key]

    def _fetch_frame(self, client: httpx.Client, cam: dict[str, Any]) -> tuple[np.ndarray | None, str | None]:
        url = f"{self.nvr_base_url}/cgi-bin/snapshot.cgi?channel={cam['channel']}"
        resp = client.get(url)
        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code}"
        buf = np.frombuffer(resp.content, dtype=np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if frame is None:
            return None, "Decode failed"
        return frame, None

    def _detect_frame(
        self,
        cam: dict[str, Any],
        task_key: str,
        frame: np.ndarray | None,
        fetch_error: str | None,
    ) -> dict[str, Any]:
        cam_id = cam["id"]
        zone = cam.get("zone") or []
        has_zone = len(zone) >= 3

        if fetch_error or frame is None:
            return {
                "cam_id": cam_id,
                "ai_task": task_key,
                "has_zone": has_zone,
                "alert": False,
                "person_in_zone": False,
                "in_zone_count": 0,
                "violation_count": 0,
                "total_persons": 0,
                "persons": [],
                "device": self.device_label,
                "error": fetch_error or "Decode failed",
                "updated_at": time.time(),
            }

        model = self._ensure_model(task_key)
        h, w = frame.shape[:2]
        t0 = time.perf_counter()
        predict_kwargs: dict[str, Any] = {
            "conf": self.conf,
            "imgsz": self.imgsz,
            "device": self.device,
            "verbose": False,
        }
        if task_key == "cam2_person":
            predict_kwargs["classes"] = [0]

        preds = model.predict(frame, **predict_kwargs)
        inference_ms = round((time.perf_counter() - t0) * 1000)

        detections: list[dict[str, Any]] = []
        in_zone_count = 0
        violation_count = 0

        if preds and preds[0].boxes is not None:
            boxes = preds[0].boxes
            xyxy_list = boxes.xyxy.cpu().tolist()
            conf_list = boxes.conf.cpu().tolist()
            cls_list = boxes.cls.cpu().tolist()
            names = model.names

            for (x1, y1, x2, y2), score, cls_id in zip(xyxy_list, conf_list, cls_list):
                nx1 = max(0.0, min(1.0, x1 / w))
                ny1 = max(0.0, min(1.0, y1 / h))
                nx2 = max(0.0, min(1.0, x2 / w))
                ny2 = max(0.0, min(1.0, y2 / h))
                # Diagonal midpoint of the bounding box
                cx = (nx1 + nx2) / 2.0
                cy = (ny1 + ny2) / 2.0
                in_zone = point_in_polygon(cx, cy, zone) if has_zone else True
                cls_name = str(names.get(int(cls_id), int(cls_id)))

                if task_key == "cam2_person":
                    # Green when inside zone, orange/muted when outside
                    is_alert = False
                    if in_zone:
                        in_zone_count += 1
                    label = "Trong vùng" if in_zone else "Ngoài vùng"
                else:
                    # Cam1 PPE: check violation classes (and respect zone if drawn)
                    is_violation = cls_name in PPE_VIOLATION_CLASSES
                    is_alert = is_violation and in_zone
                    if is_alert:
                        violation_count += 1
                    label = cls_name

                detections.append(
                    {
                        "x1": round(nx1, 4),
                        "y1": round(ny1, 4),
                        "x2": round(nx2, 4),
                        "y2": round(ny2, 4),
                        "cx": round(cx, 4),
                        "cy": round(cy, 4),
                        "conf": round(float(score), 3),
                        "in_zone": in_zone,
                        "is_alert": is_alert,
                        "label": label,
                    }
                )

        # For Cam2 (machine zone), empty zone (no worker) is the alert state
        alert = (in_zone_count == 0) if task_key == "cam2_person" else (violation_count > 0)
        now = time.time()
        stats = self._update_stats(cam_id, alert, now)
        return {
            "cam_id": cam_id,
            "ai_task": task_key,
            "has_zone": has_zone,
            "alert": alert,
            "person_in_zone": in_zone_count > 0,
            "in_zone_count": in_zone_count,
            "violation_count": violation_count,
            "total_persons": len(detections),
            "persons": detections,
            "device": self.device_label,
            "inference_ms": inference_ms,
            "updated_at": now,
            **stats,
        }

    def _update_stats(self, cam_id: str, alert: bool, now: float) -> dict[str, Any]:
        with self._lock:
            st = self._stats.get(cam_id)
            if st is None:
                st = {
                    "last_alert": alert,
                    "state_since": now,
                    "last_ts": now,
                    "total_alert_sec": 0.0,
                    "alert_count": 1 if alert else 0,
                    "timeline": [],
                }
                self._stats[cam_id] = st
            else:
                dt = max(0.0, now - st["last_ts"])
                if st["last_alert"]:
                    st["total_alert_sec"] += dt
                if alert and not st["last_alert"]:
                    st["alert_count"] += 1
                if alert != st["last_alert"]:
                    st["last_alert"] = alert
                    st["state_since"] = now
                st["last_ts"] = now

            st["timeline"].append(1 if alert else 0)
            if len(st["timeline"]) > 60:
                st["timeline"] = st["timeline"][-60:]

            return {
                "current_duration_sec": round(now - st["state_since"]),
                "total_alert_sec": round(st["total_alert_sec"]),
                "alert_count": st["alert_count"],
                "timeline": list(st["timeline"]),
            }

    def _run_loop(self) -> None:
        auth = httpx.DigestAuth(self.nvr_user, self.nvr_pass)
        with httpx.Client(auth=auth, timeout=6.0) as client:
            while not self._stop_event.is_set():
                targets: list[tuple[dict[str, Any], str]] = []
                for cam in self.load_cameras_fn():
                    if not cam.get("enabled", True):
                        continue
                    task_key = resolve_camera_task(cam)
                    if task_key == "none":
                        continue
                    if task_key == "cam2_person" and len(cam.get("zone") or []) < 3:
                        continue
                    targets.append((cam, task_key))

                if not targets:
                    self._stop_event.wait(0.8)
                    continue

                active_ids = {cam["id"] for cam, _ in targets}
                for stale_id in list(self._readers.keys()):
                    if stale_id not in active_ids:
                        self._readers.pop(stale_id).stop()
                        self._last_frame_ts.pop(stale_id, None)

                for cam, _ in targets:
                    cid = cam["id"]
                    if cid not in self._readers:
                        self._readers[cid] = _CameraStreamReader(
                            self.nvr_base_url, self.nvr_user, self.nvr_pass, cam["channel"]
                        )

                now = time.time()
                need_snapshot: list[tuple[dict[str, Any], str]] = []
                for cam, task_key in targets:
                    if self._stop_event.is_set():
                        break
                    cid = cam["id"]
                    frame, frame_ts, _err = self._readers[cid].get_latest()
                    # Use fresh MJPEG frame if available (< 3s old)
                    if frame is not None and (now - frame_ts) < 3.0:
                        if frame_ts <= self._last_frame_ts.get(cid, 0.0):
                            continue
                        self._last_frame_ts[cid] = frame_ts
                        try:
                            result = self._detect_frame(cam, task_key, frame, None)
                        except Exception as exc:
                            result = {
                                "cam_id": cid,
                                "ai_task": task_key,
                                "has_zone": len(cam.get("zone") or []) >= 3,
                                "alert": False,
                                "person_in_zone": False,
                                "in_zone_count": 0,
                                "violation_count": 0,
                                "total_persons": 0,
                                "persons": [],
                                "device": self.device_label,
                                "error": str(exc),
                                "updated_at": time.time(),
                            }
                        with self._lock:
                            self._results[cid] = result
                    elif (now - self._last_frame_ts.get(cid, 0.0)) >= 2.5:
                        need_snapshot.append((cam, task_key))

                # Fallback to parallel snapshot.cgi only when MJPEG stream has no fresh frame
                if need_snapshot:
                    with ThreadPoolExecutor(max_workers=len(need_snapshot)) as pool:
                        future_map = {
                            pool.submit(self._fetch_frame, client, cam): (cam, task_key)
                            for cam, task_key in need_snapshot
                        }
                        for fut in as_completed(future_map):
                            if self._stop_event.is_set():
                                break
                            cam, task_key = future_map[fut]
                            cid = cam["id"]
                            self._last_frame_ts[cid] = time.time()
                            try:
                                frame, fetch_err = fut.result()
                                result = self._detect_frame(cam, task_key, frame, fetch_err)
                            except Exception as exc:
                                result = {
                                    "cam_id": cid,
                                    "ai_task": task_key,
                                    "has_zone": len(cam.get("zone") or []) >= 3,
                                    "alert": False,
                                    "person_in_zone": False,
                                    "in_zone_count": 0,
                                    "violation_count": 0,
                                    "total_persons": 0,
                                    "persons": [],
                                    "device": self.device_label,
                                    "error": str(exc),
                                    "updated_at": time.time(),
                                }
                            with self._lock:
                                self._results[cid] = result

                self._stop_event.wait(self.interval_sec)

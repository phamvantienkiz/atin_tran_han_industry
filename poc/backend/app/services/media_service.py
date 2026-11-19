"""Background recording (MJPEG -> MP4) and frame extraction service."""

from __future__ import annotations

import io
import re
import shutil
import threading
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import httpx
import numpy as np

from app.exceptions.custom import ConflictError, NotFoundError, UpstreamError, ValidationError
from app.utils.validation import validate_safe_name

ALLOWED_DURATIONS_MIN = {5, 10, 20}
ALLOWED_SKIP_FRAMES = {5, 10}
RECORD_FPS = 10.0


@dataclass
class RecordJob:
    job_id: str
    cam_id: str
    channel: int
    cam_name: str
    subtype: int
    duration_minutes: int
    filename: str
    filepath: Path
    started_at: float = field(default_factory=time.time)
    status: str = "recording"
    frames_written: int = 0
    error: str | None = None
    stop_event: threading.Event = field(default_factory=threading.Event, repr=False)

    def to_dict(self) -> dict[str, Any]:
        now = time.time()
        elapsed = max(0.0, now - self.started_at)
        total_sec = self.duration_minutes * 60
        remaining = max(0.0, total_sec - elapsed) if self.status == "recording" else 0.0
        return {
            "job_id": self.job_id,
            "cam_id": self.cam_id,
            "channel": self.channel,
            "cam_name": self.cam_name,
            "subtype": self.subtype,
            "duration_minutes": self.duration_minutes,
            "filename": self.filename,
            "started_at": self.started_at,
            "elapsed_sec": round(elapsed, 1),
            "remaining_sec": round(remaining, 1),
            "frames_written": self.frames_written,
            "status": self.status,
            "error": self.error,
        }


class MediaService:
    """Manages active NVR recordings and video-to-frame dataset extractions."""

    def __init__(self, storages_dir: Path, nvr_base_url: str, nvr_user: str, nvr_pass: str) -> None:
        self.storages_dir = storages_dir
        self.videos_dir = storages_dir / "videos"
        self.frames_dir = storages_dir / "frames"
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        self.frames_dir.mkdir(parents=True, exist_ok=True)

        self.nvr_base_url = nvr_base_url
        self.nvr_user = nvr_user
        self.nvr_pass = nvr_pass

        self._lock = threading.Lock()
        self._jobs: dict[str, RecordJob] = {}

    def active_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [j.to_dict() for j in self._jobs.values() if j.status == "recording"]

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise NotFoundError(f"Không tìm thấy phiên ghi hình '{job_id}'")
            return job.to_dict()

    def start_record(self, cam: dict[str, Any], duration_minutes: int, subtype: int = 0) -> dict[str, Any]:
        if duration_minutes not in ALLOWED_DURATIONS_MIN:
            raise ValidationError("Thời gian record chỉ hỗ trợ 5, 10 hoặc 20 phút")

        with self._lock:
            for existing in self._jobs.values():
                if existing.cam_id == cam["id"] and existing.status == "recording":
                    raise ConflictError(f"Camera {cam['name']} đang trong quá trình ghi hình")

            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{cam['id']}_{stamp}_{duration_minutes}m.mp4"
            filepath = self.videos_dir / filename
            job = RecordJob(
                job_id=f"{cam['id']}_{stamp}",
                cam_id=cam["id"],
                channel=int(cam["channel"]),
                cam_name=cam["name"],
                subtype=subtype,
                duration_minutes=duration_minutes,
                filename=filename,
                filepath=filepath,
            )
            self._jobs[job.job_id] = job

        thread = threading.Thread(target=self._record_worker, args=(job,), daemon=True)
        thread.start()
        return job.to_dict()

    def stop_record(self, cam_id: str) -> dict[str, Any]:
        with self._lock:
            for job in reversed(list(self._jobs.values())):
                if job.cam_id == cam_id and job.status == "recording":
                    job.stop_event.set()
                    return job.to_dict()
        raise NotFoundError(f"Camera '{cam_id}' hiện không có phiên ghi hình nào")

    def _record_worker(self, job: RecordJob) -> None:
        url = f"{self.nvr_base_url}/cgi-bin/mjpg/video.cgi?channel={job.channel}&subtype={job.subtype}"
        auth = httpx.DigestAuth(self.nvr_user, self.nvr_pass)
        tmp_path = job.filepath.with_suffix(".tmp.mp4")
        writer: cv2.VideoWriter | None = None
        last_frame: np.ndarray | None = None
        deadline = job.started_at + job.duration_minutes * 60.0
        frame_interval = 1.0 / RECORD_FPS
        next_write_at = time.time()

        try:
            with (
                httpx.Client(auth=auth, timeout=httpx.Timeout(10.0, read=15.0)) as client,
                client.stream("GET", url) as resp,
            ):
                if resp.status_code != 200:
                    raise RuntimeError(f"NVR trả về mã lỗi HTTP {resp.status_code}")

                buf = bytearray()
                for chunk in resp.iter_bytes(chunk_size=16384):
                    if job.stop_event.is_set() or time.time() >= deadline:
                        break
                    buf.extend(chunk)

                    while True:
                        start = buf.find(b"\xff\xd8")
                        if start < 0:
                            buf.clear()
                            break
                        end = buf.find(b"\xff\xd9", start + 2)
                        if end < 0:
                            if start > 0:
                                del buf[:start]
                            break

                        jpeg_bytes = bytes(buf[start : end + 2])
                        del buf[: end + 2]

                        decoded = cv2.imdecode(
                            np.frombuffer(jpeg_bytes, dtype=np.uint8),
                            cv2.IMREAD_COLOR,
                        )
                        if decoded is None:
                            continue

                        if writer is None:
                            h, w = decoded.shape[:2]
                            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                            writer = cv2.VideoWriter(str(tmp_path), fourcc, RECORD_FPS, (w, h))
                            if not writer.isOpened():
                                raise RuntimeError("Không thể khởi tạo bộ ghi MP4 (VideoWriter)")
                            next_write_at = time.time()

                        last_frame = decoded
                        now = time.time()
                        while next_write_at <= now and next_write_at < deadline:
                            writer.write(last_frame)
                            job.frames_written += 1
                            next_write_at += frame_interval

                    if job.stop_event.is_set() or time.time() >= deadline:
                        break

            if writer is not None:
                writer.release()
                writer = None

            if job.frames_written > 0 and tmp_path.exists():
                tmp_path.replace(job.filepath)
                job.status = "stopped" if job.stop_event.is_set() else "completed"
            else:
                if tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
                job.status = "error"
                job.error = "Không nhận được frame hình ảnh nào từ NVR"
        except Exception as exc:  # noqa: BLE001 - capture worker failure into job.error
            if writer is not None:
                writer.release()
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            job.status = "error"
            job.error = str(exc)

    def get_video_path(self, filename: str) -> Path:
        safe = validate_safe_name(filename)
        target = self.videos_dir / safe
        if not target.is_file():
            raise NotFoundError("Video không tồn tại")
        return target

    def list_videos(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for path in sorted(self.videos_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True):
            if path.name.endswith(".tmp.mp4"):
                continue
            stat = path.stat()
            meta = self._probe_video(path)
            extracted = [
                f.name
                for f in self.frames_dir.iterdir()
                if f.is_dir() and f.name.startswith(f"{path.stem}_skip")
            ]
            items.append(
                {
                    "filename": path.name,
                    "size_bytes": stat.st_size,
                    "created_at": stat.st_mtime,
                    "extracted_folders": sorted(extracted),
                    **meta,
                }
            )
        return items

    @staticmethod
    def _probe_video(path: Path) -> dict[str, Any]:
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return {"width": 0, "height": 0, "fps": 0.0, "frame_count": 0, "duration_sec": 0.0}
        try:
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            duration_sec = round(frame_count / fps, 1) if fps > 0 else 0.0
            return {
                "width": width,
                "height": height,
                "fps": round(fps, 1),
                "frame_count": frame_count,
                "duration_sec": duration_sec,
            }
        finally:
            cap.release()

    def delete_video(self, filename: str) -> None:
        target = self.get_video_path(filename)
        target.unlink()

    def extract_frames(self, filename: str, skip_frames: int) -> dict[str, Any]:
        if skip_frames not in ALLOWED_SKIP_FRAMES:
            raise ValidationError("Mức bỏ qua chỉ hỗ trợ 5 hoặc 10 frame liên tiếp")

        video_path = self.get_video_path(filename)
        folder_name = f"{video_path.stem}_skip{skip_frames}"
        out_dir = self.frames_dir / folder_name
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise UpstreamError(f"Không thể mở video '{video_path.name}'", status_code=500)

        stride = skip_frames + 1
        frame_idx = 0
        saved_count = 0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                if frame_idx % stride == 0:
                    saved_count += 1
                    out_file = out_dir / f"frame_{saved_count:06d}.jpg"
                    cv2.imwrite(str(out_file), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                frame_idx += 1
        finally:
            cap.release()

        return {
            "folder": folder_name,
            "video_name": video_path.name,
            "skip_frames": skip_frames,
            "total_video_frames": frame_idx,
            "saved_frames": saved_count,
        }

    def list_frame_sets(self) -> list[dict[str, Any]]:
        sets: list[dict[str, Any]] = []
        for folder in sorted(self.frames_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not folder.is_dir():
                continue
            images = sorted(folder.glob("*.jpg"))
            size_bytes = sum(img.stat().st_size for img in images)
            skip_match = re.search(r"_skip(\d+)$", folder.name)
            skip_frames = int(skip_match.group(1)) if skip_match else None
            sets.append(
                {
                    "folder": folder.name,
                    "skip_frames": skip_frames,
                    "frame_count": len(images),
                    "size_bytes": size_bytes,
                    "created_at": folder.stat().st_mtime,
                    "previews": [img.name for img in images[:4]],
                }
            )
        return sets

    def get_frame_preview_path(self, folder: str, image_name: str) -> Path:
        safe_folder = validate_safe_name(folder)
        safe_img = validate_safe_name(image_name)
        target = self.frames_dir / safe_folder / safe_img
        if not target.is_file():
            raise NotFoundError("Ảnh không tồn tại")
        return target

    def build_frames_zip_bytes(self, folder: str) -> tuple[str, bytes]:
        safe = validate_safe_name(folder)
        target_dir = self.frames_dir / safe
        if not target_dir.is_dir():
            raise NotFoundError(f"Thư mục '{safe}' không tồn tại")

        mem = io.BytesIO()
        with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for img in sorted(target_dir.glob("*.jpg")):
                zf.write(img, arcname=f"{safe}/{img.name}")
        return safe, mem.getvalue()

    def delete_frame_set(self, folder: str) -> None:
        safe = validate_safe_name(folder)
        target_dir = self.frames_dir / safe
        if not target_dir.is_dir():
            raise NotFoundError(f"Thư mục '{safe}' không tồn tại")
        shutil.rmtree(target_dir)

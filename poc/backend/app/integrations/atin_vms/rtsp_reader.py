"""Low-latency RTSP stream reader for ATIN MediaMTX (C04)."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterator

import cv2
import numpy as np

from app.core.logging import get_logger

logger = get_logger("app.integrations.atin_vms.rtsp")


def iter_rtsp_frames(
    rtsp_url: str,
    reconnect_delay_sec: float = 3.0,
    stop_check: Callable[[], bool] | None = None,
) -> Iterator[np.ndarray]:
    """Yield latest BGR frames from an RTSP stream with TCP transport & minimal buffering."""
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"

    while not (stop_check and stop_check()):
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            logger.warning("RTSP open failed (%s), retrying in %.1fs", rtsp_url, reconnect_delay_sec)
            cap.release()
            time.sleep(reconnect_delay_sec)
            continue

        try:
            while not (stop_check and stop_check()):
                ok, frame = cap.read()
                if not ok or frame is None:
                    logger.warning("RTSP stream interrupted (%s), reconnecting...", rtsp_url)
                    break
                yield frame
        finally:
            cap.release()
        time.sleep(reconnect_delay_sec)

"""Phase 0 benchmark: probe NVR main (subtype=0) vs sub (subtype=1) MJPEG & snapshot streams."""

from __future__ import annotations

import argparse
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import httpx
import numpy as np

from app.ai.nvr_stream import extract_jpeg_frames
from app.core.config import settings
from scripts.bench.common import percentile, samples_dir, write_bench_outputs


@dataclass
class StreamStats:
    channel: int
    subtype: int
    mode: str
    duration_sec: float
    frames: int
    fps_actual: float
    ttff_ms: float | None
    resolution: str
    avg_kb: float
    p95_kb: float
    mbps: float
    stalls_gt_1s: int
    error: str | None = None


@dataclass
class SnapshotStats:
    channel: int
    ok_count: int
    attempts: int
    p50_ms: float | None
    max_ms: float | None
    avg_kb: float
    resolution: str
    error: str | None = None


def _decode_resolution(jpeg_bytes: bytes) -> str:
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return "unknown"
    h, w = img.shape[:2]
    return f"{w}x{h}"


def _probe_mjpeg_channel(
    channel: int,
    subtype: int,
    duration_sec: float,
    mode: str,
    stop_event: threading.Event,
    save_dir: Path | None = None,
    max_samples: int = 20,
) -> StreamStats:
    url = f"{settings.nvr_base_url}/cgi-bin/mjpg/video.cgi?channel={channel}&subtype={subtype}"
    auth = httpx.DigestAuth(settings.NVR_USER, settings.NVR_PASS)
    timeout = httpx.Timeout(10.0, read=10.0)

    t_start = time.monotonic()
    deadline = t_start + duration_sec
    ttff_ms: float | None = None
    last_frame_mono = t_start
    stalls_gt_1s = 0
    sizes_bytes: list[int] = []
    total_bytes = 0
    resolution = "unknown"
    saved_count = 0
    buffer = bytearray()

    if save_dir is not None:
        save_dir.mkdir(parents=True, exist_ok=True)

    try:
        with (
            httpx.Client(auth=auth, timeout=timeout) as client,
            client.stream("GET", url) as resp,
        ):
                if resp.status_code != 200:
                    return StreamStats(
                        channel=channel,
                        subtype=subtype,
                        mode=mode,
                        duration_sec=0.0,
                        frames=0,
                        fps_actual=0.0,
                        ttff_ms=None,
                        resolution="unknown",
                        avg_kb=0.0,
                        p95_kb=0.0,
                        mbps=0.0,
                        stalls_gt_1s=0,
                        error=f"HTTP {resp.status_code}",
                    )
                for chunk in resp.iter_bytes(chunk_size=16384):
                    if stop_event.is_set() or time.monotonic() >= deadline:
                        break
                    if not chunk:
                        continue
                    buffer.extend(chunk)
                    jpegs = extract_jpeg_frames(buffer)
                    now = time.monotonic()
                    if not jpegs:
                        continue
                    for jpg in jpegs:
                        if ttff_ms is None:
                            ttff_ms = round((now - t_start) * 1000.0, 1)
                            resolution = _decode_resolution(jpg)
                        elif (now - last_frame_mono) > 1.0:
                            stalls_gt_1s += 1
                        last_frame_mono = now
                        sz = len(jpg)
                        sizes_bytes.append(sz)
                        total_bytes += sz
                        if save_dir is not None and saved_count < max_samples:
                            out_file = save_dir / f"ch{channel}_sub{subtype}_{saved_count:02d}.jpg"
                            out_file.write_bytes(jpg)
                            saved_count += 1
                    if now >= deadline:
                        break
    except Exception as exc:  # noqa: BLE001
        elapsed = max(0.001, time.monotonic() - t_start)
        return StreamStats(
            channel=channel,
            subtype=subtype,
            mode=mode,
            duration_sec=round(elapsed, 2),
            frames=len(sizes_bytes),
            fps_actual=round(len(sizes_bytes) / elapsed, 2),
            ttff_ms=ttff_ms,
            resolution=resolution,
            avg_kb=round(sum(sizes_bytes) / max(1, len(sizes_bytes)) / 1024.0, 1),
            p95_kb=round(percentile([float(s) for s in sizes_bytes], 95.0) / 1024.0, 1),
            mbps=round((total_bytes * 8.0) / elapsed / 1_000_000.0, 2),
            stalls_gt_1s=stalls_gt_1s,
            error=str(exc),
        )

    elapsed = max(0.001, time.monotonic() - t_start)
    frames = len(sizes_bytes)
    avg_kb = (sum(sizes_bytes) / frames / 1024.0) if frames else 0.0
    p95_kb = (percentile([float(s) for s in sizes_bytes], 95.0) / 1024.0) if frames else 0.0
    mbps = (total_bytes * 8.0) / elapsed / 1_000_000.0
    return StreamStats(
        channel=channel,
        subtype=subtype,
        mode=mode,
        duration_sec=round(elapsed, 2),
        frames=frames,
        fps_actual=round(frames / elapsed, 2),
        ttff_ms=ttff_ms,
        resolution=resolution,
        avg_kb=round(avg_kb, 1),
        p95_kb=round(p95_kb, 1),
        mbps=round(mbps, 2),
        stalls_gt_1s=stalls_gt_1s,
    )


def _probe_snapshot_channel(
    channel: int,
    attempts: int,
    stop_event: threading.Event,
) -> SnapshotStats:
    url = f"{settings.nvr_base_url}/cgi-bin/snapshot.cgi?channel={channel}"
    auth = httpx.DigestAuth(settings.NVR_USER, settings.NVR_PASS)
    latencies: list[float] = []
    sizes: list[int] = []
    resolution = "unknown"
    last_error: str | None = None

    with httpx.Client(auth=auth, timeout=8.0) as client:
        for _ in range(attempts):
            if stop_event.is_set():
                break
            t0 = time.perf_counter()
            try:
                resp = client.get(url)
                ms = (time.perf_counter() - t0) * 1000.0
                if resp.status_code == 200 and resp.content:
                    latencies.append(ms)
                    sizes.append(len(resp.content))
                    if resolution == "unknown":
                        resolution = _decode_resolution(resp.content)
                else:
                    last_error = f"HTTP {resp.status_code}"
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)

    return SnapshotStats(
        channel=channel,
        ok_count=len(latencies),
        attempts=attempts,
        p50_ms=round(percentile(latencies, 50.0), 1) if latencies else None,
        max_ms=round(max(latencies), 1) if latencies else None,
        avg_kb=round((sum(sizes) / len(sizes)) / 1024.0, 1) if sizes else 0.0,
        resolution=resolution,
        error=last_error if not latencies else None,
    )


def _format_markdown(
    single_stats: list[StreamStats],
    concurrent_stats: list[StreamStats],
    snapshot_stats: list[SnapshotStats],
) -> str:
    lines = [
        "# Phase 0 — NVR Stream Probe (`probe_nvr.py`)",
        "",
        f"- **Thời điểm**: `{datetime.now(timezone.utc).isoformat()}`",
        f"- **NVR**: `{settings.NVR_HOST}:{settings.NVR_PORT}`",
        "",
        "## 1. Đo từng kênh riêng lẻ (Single-Channel MJPEG)",
        "",
        "| Kênh | Subtype | Độ phân giải | FPS thực | TTFF (ms) | JPEG avg / p95 (KB) | Mbps | Stall >1s | Lỗi |",
        "| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |",
    ]
    for s in single_stats:
        lines.append(
            f"| ch{s.channel} | {s.subtype} | {s.resolution} | {s.fps_actual} | "
            f"{s.ttff_ms if s.ttff_ms is not None else '-'} | {s.avg_kb} / {s.p95_kb} | "
            f"{s.mbps} | {s.stalls_gt_1s} | {s.error or '-'} |"
        )

    lines.extend([
        "",
        "## 2. Đo đồng thời 4 kênh (Concurrent MJPEG — tải thật)",
        "",
        "| Kênh | Subtype | Độ phân giải | FPS thực | TTFF (ms) | JPEG avg / p95 (KB) | Mbps | Stall >1s | Lỗi |",
        "| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |",
    ])
    for s in concurrent_stats:
        lines.append(
            f"| ch{s.channel} | {s.subtype} | {s.resolution} | {s.fps_actual} | "
            f"{s.ttff_ms if s.ttff_ms is not None else '-'} | {s.avg_kb} / {s.p95_kb} | "
            f"{s.mbps} | {s.stalls_gt_1s} | {s.error or '-'} |"
        )

    for sub in (0, 1):
        sub_rows = [s for s in concurrent_stats if s.subtype == sub]
        if sub_rows:
            total_mbps = round(sum(s.mbps for s in sub_rows), 2)
            avg_fps = round(sum(s.fps_actual for s in sub_rows) / len(sub_rows), 2)
            lines.append(f"- **Tổng tải 4 kênh `subtype={sub}`**: `{total_mbps} Mbps`, FPS TB/kênh = `{avg_fps}`")

    lines.extend([
        "",
        "## 3. Đo độ trễ `snapshot.cgi` (5 lần/kênh)",
        "",
        "| Kênh | Thành công | Độ phân giải | p50 (ms) | max (ms) | Avg (KB) | Lỗi |",
        "| :---: | :---: | :---: | :---: | :---: | :---: | :--- |",
    ])
    for sn in snapshot_stats:
        lines.append(
            f"| ch{sn.channel} | {sn.ok_count}/{sn.attempts} | {sn.resolution} | "
            f"{sn.p50_ms if sn.p50_ms is not None else '-'} | "
            f"{sn.max_ms if sn.max_ms is not None else '-'} | {sn.avg_kb} | {sn.error or '-'} |"
        )

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe NVR MJPEG subtype=0 vs subtype=1 & snapshot.cgi")
    parser.add_argument("--channels", default="16,17,18,21", help="Comma-separated NVR channels")
    parser.add_argument("--duration", type=float, default=15.0, help="Seconds per MJPEG probe run")
    parser.add_argument("--samples", type=int, default=20, help="Max sample JPEGs per channel (subtype=0)")
    parser.add_argument("--skip-single", action="store_true", help="Skip single-channel sequential probe")
    args = parser.parse_args()

    if not settings.nvr_configured:
        print("[ERROR] NVR credentials (NVR_HOST, NVR_USER, NVR_PASS) are not configured in .env")
        return 1

    channels = [int(c.strip()) for c in args.channels.split(",") if c.strip()]
    stop_event = threading.Event()

    def _handle_sig(_signum: int, _frame: Any) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_sig)

    s_root = samples_dir()
    single_stats: list[StreamStats] = []
    concurrent_stats: list[StreamStats] = []
    snapshot_stats: list[SnapshotStats] = []

    if not args.skip_single:
        print(f"[1/3] Probing single channels sequentially ({args.duration:.0f}s each)...")
        for sub in (0, 1):
            for ch in channels:
                if stop_event.is_set():
                    break
                print(f"  -> ch{ch} subtype={sub} ...")
                st = _probe_mjpeg_channel(
                    channel=ch,
                    subtype=sub,
                    duration_sec=args.duration,
                    mode="single",
                    stop_event=stop_event,
                    save_dir=(s_root / f"ch{ch}") if sub == 0 else None,
                    max_samples=args.samples,
                )
                single_stats.append(st)

    print(f"[2/3] Probing {len(channels)} channels concurrently ({args.duration:.0f}s per subtype)...")
    for sub in (0, 1):
        if stop_event.is_set():
            break
        print(f"  -> concurrent subtype={sub} channels={channels} ...")
        with ThreadPoolExecutor(max_workers=len(channels)) as pool:
            futs = [
                pool.submit(
                    _probe_mjpeg_channel,
                    ch,
                    sub,
                    args.duration,
                    "concurrent",
                    stop_event,
                    (s_root / f"ch{ch}") if (sub == 0 and args.skip_single) else None,
                    args.samples,
                )
                for ch in channels
            ]
            for fut in futs:
                concurrent_stats.append(fut.result())

    print("[3/3] Probing snapshot.cgi (5 requests/channel)...")
    for ch in channels:
        if stop_event.is_set():
            break
        snapshot_stats.append(_probe_snapshot_channel(ch, attempts=5, stop_event=stop_event))

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nvr": f"{settings.NVR_HOST}:{settings.NVR_PORT}",
        "channels": channels,
        "duration_sec": args.duration,
        "single": [asdict(s) for s in single_stats],
        "concurrent": [asdict(s) for s in concurrent_stats],
        "snapshot": [asdict(s) for s in snapshot_stats],
    }
    md = _format_markdown(single_stats, concurrent_stats, snapshot_stats)
    json_path, md_path = write_bench_outputs("probe_nvr", payload, md)
    print("\n" + md)
    print(f"[SAVED] {json_path}")
    print(f"[SAVED] {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

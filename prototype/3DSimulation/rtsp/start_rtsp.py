"""Stream one or all 4 PoC videos (.webm/.mp4) as looping RTSP feeds via MediaMTX + FFmpeg."""

from __future__ import annotations

import argparse
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parent
MEDIAMTX_EXE = ROOT / "bin" / "mediamtx.exe"
MEDIAMTX_YML = ROOT / "bin" / "mediamtx.yml"
RESOURCES_DIR = ROOT.parent / "resources"


def wait_port(host: str, port: int, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.2)
    return False


def discover_poc_streams() -> list[tuple[str, Path]]:
    """Auto-discover recorded CAM_<id>_*.webm files in resources/."""
    streams: list[tuple[str, Path]] = []
    for p in sorted(RESOURCES_DIR.glob("CAM_*.webm")):
        m = re.match(r"CAM_([A-Za-z0-9-]+)_", p.stem)
        cam_id = m.group(1) if m else p.stem
        streams.append((f"cam{cam_id}", p))
    return streams


def build_ffmpeg_cmd(ffmpeg_exe: str, video_path: Path, rtsp_url: str) -> list[str]:
    return [
        ffmpeg_exe,
        "-hide_banner",
        "-loglevel", "warning",
        "-stream_loop", "-1",
        "-i", str(video_path),
        "-vf", "setpts=N/(15*TB),scale=trunc(iw/2)*2:trunc(ih/2)*2,realtime",
        "-r", "15",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-pix_fmt", "yuv420p",
        "-g", "15",
        "-an",
        "-f", "rtsp",
        "-rtsp_transport", "tcp",
        rtsp_url,
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate RTSP streams from recorded PoC videos")
    parser.add_argument("--input", type=Path, default=None, help="Single video file (omit to stream all CAM_*.webm)")
    parser.add_argument("--name", default="cam27", help="RTSP stream path name when --input is used")
    parser.add_argument("--port", type=int, default=8554, help="RTSP port")
    args = parser.parse_args()

    if not MEDIAMTX_EXE.exists():
        raise FileNotFoundError(f"Missing MediaMTX binary: {MEDIAMTX_EXE}")

    if args.input is not None:
        if not args.input.exists():
            raise FileNotFoundError(f"Missing input video: {args.input}")
        targets = [(args.name, args.input)]
    else:
        targets = discover_poc_streams()
        if not targets:
            raise FileNotFoundError(f"No CAM_*.webm files found in {RESOURCES_DIR}")

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    mtx_cmd = [str(MEDIAMTX_EXE)]
    if MEDIAMTX_YML.exists():
        mtx_cmd.append(str(MEDIAMTX_YML))
    mtx_proc = subprocess.Popen(mtx_cmd, cwd=str(MEDIAMTX_EXE.parent))

    if not wait_port("127.0.0.1", args.port, timeout=10.0):
        mtx_proc.terminate()
        raise RuntimeError(f"MediaMTX failed to listen on port {args.port}")

    runners: list[tuple[str, list[str], subprocess.Popen]] = []
    for name, video_path in targets:
        url = f"rtsp://127.0.0.1:{args.port}/{name}"
        cmd = build_ffmpeg_cmd(ffmpeg_exe, video_path, url)
        proc = subprocess.Popen(cmd)
        runners.append((url, cmd, proc))
        print(f"RTSP stream READY: {url} <- {video_path.name}", flush=True)

    print("All RTSP streams running. Press Ctrl+C to stop.", flush=True)
    try:
        while True:
            if mtx_proc.poll() is not None:
                print("MediaMTX exited unexpectedly.", file=sys.stderr)
                break
            for idx, (url, cmd, proc) in enumerate(runners):
                if proc.poll() is not None:
                    print(f"Restarting {url}...", flush=True)
                    runners[idx] = (url, cmd, subprocess.Popen(cmd))
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nStopping RTSP streams...")
    finally:
        for _, _, proc in runners:
            if proc.poll() is None:
                proc.terminate()
        for _, _, proc in runners:
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        if mtx_proc.poll() is None:
            mtx_proc.terminate()
            try:
                mtx_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                mtx_proc.kill()


if __name__ == "__main__":
    main()

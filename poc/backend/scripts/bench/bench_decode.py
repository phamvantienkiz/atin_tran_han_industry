"""Phase 0 benchmark: CPU JPEG imdecode (full vs REDUCED_2 vs REDUCED_4) + letterbox preprocess."""

from __future__ import annotations

import argparse
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import cv2
import numpy as np

from app.ai.detector import YoloPersonDetector
from app.core.config import settings
from scripts.bench.common import load_sample_jpegs, percentile, write_bench_outputs


@dataclass
class DecodeBenchRow:
    reduce_k: int
    label: str
    sample_count: int
    decoded_resolutions: list[str]
    decode_p50_ms: float
    decode_p95_ms: float
    preprocess_p50_ms: float
    preprocess_p95_ms: float
    total_p50_ms: float
    total_p95_ms: float
    fits_imgsz: bool


_FLAGS = [
    (1, "IMREAD_COLOR (k=1)", cv2.IMREAD_COLOR),
    (2, "IMREAD_REDUCED_COLOR_2 (k=2)", cv2.IMREAD_REDUCED_COLOR_2),
    (4, "IMREAD_REDUCED_COLOR_4 (k=4)", cv2.IMREAD_REDUCED_COLOR_4),
]


def _run_bench_for_flag(
    k: int,
    label: str,
    flag: int,
    samples: list[tuple[str, bytes]],
    detector: YoloPersonDetector,
    repeats: int,
) -> DecodeBenchRow:
    decode_times: list[float] = []
    pre_times: list[float] = []
    total_times: list[float] = []
    resolutions: set[str] = set()
    min_w = 10**9

    # Warmup once
    if samples:
        arr0 = np.frombuffer(samples[0][1], dtype=np.uint8)
        img0 = cv2.imdecode(arr0, flag)
        if img0 is not None:
            detector._preprocess(img0)

    for _ in range(repeats):
        for _name, raw in samples:
            arr = np.frombuffer(raw, dtype=np.uint8)
            t0 = time.perf_counter()
            img = cv2.imdecode(arr, flag)
            t1 = time.perf_counter()
            if img is None:
                continue
            h, w = img.shape[:2]
            resolutions.add(f"{w}x{h}")
            min_w = min(min_w, w)
            detector._preprocess(img)
            t2 = time.perf_counter()

            d_ms = (t1 - t0) * 1000.0
            p_ms = (t2 - t1) * 1000.0
            decode_times.append(d_ms)
            pre_times.append(p_ms)
            total_times.append(d_ms + p_ms)

    return DecodeBenchRow(
        reduce_k=k,
        label=label,
        sample_count=len(decode_times),
        decoded_resolutions=sorted(resolutions),
        decode_p50_ms=round(percentile(decode_times, 50.0), 3),
        decode_p95_ms=round(percentile(decode_times, 95.0), 3),
        preprocess_p50_ms=round(percentile(pre_times, 50.0), 3),
        preprocess_p95_ms=round(percentile(pre_times, 95.0), 3),
        total_p50_ms=round(percentile(total_times, 50.0), 3),
        total_p95_ms=round(percentile(total_times, 95.0), 3),
        fits_imgsz=(min_w >= detector.imgsz) if resolutions else False,
    )


def _format_markdown(rows: list[DecodeBenchRow], used_fallback: bool, imgsz: int) -> str:
    lines = [
        "# Phase 0 — Decode & Preprocess Benchmark (`bench_decode.py`)",
        "",
        f"- **Thời điểm**: `{datetime.now(timezone.utc).isoformat()}`",
        f"- **AI_IMGSZ**: `{imgsz}`",
        f"- **Nguồn ảnh mẫu**: `{'fallback report/ch17-snapshot.jpg' if used_fallback else 'poc/data/bench/samples/'}`",
        "",
        "| Chế độ | Độ phân giải sau giải mã | Decode p50 / p95 (ms) | Preprocess p50 / p95 (ms) | Tổng p50 / p95 (ms) | Đạt width ≥ imgsz |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
    ]
    for r in rows:
        res_str = ", ".join(r.decoded_resolutions) or "-"
        lines.append(
            f"| {r.label} | {res_str} | {r.decode_p50_ms} / {r.decode_p95_ms} | "
            f"{r.preprocess_p50_ms} / {r.preprocess_p95_ms} | {r.total_p50_ms} / {r.total_p95_ms} | "
            f"{'✅' if r.fits_imgsz else '❌'} |"
        )

    valid = [r for r in rows if r.fits_imgsz]
    rec = max(valid, key=lambda r: r.reduce_k) if valid else rows[0]
    lines.extend([
        "",
        "## Ước tính tải CPU cho 4 camera (theo phương án khuyến nghị)",
        f"- **Khuyến nghị `AI_DECODE_REDUCE`**: `k={rec.reduce_k}` (`{rec.label}`, tổng p95 = `{rec.total_p95_ms} ms/khung`)",
        f"- **Quyết định Phase 5 (nvJPEG)**: `{'GIỮ CPU REDUCED (<= 10 ms/khung)' if rec.total_p95_ms <= 10.0 else 'CÂN NHẮC nvJPEG (> 10 ms/khung)'}`",
        "",
        "| FPS mục tiêu / cam | Tổng khung / giây (4 cam) | Thời gian CPU ước tính (p50 ms/s) | Thời gian CPU ước tính (p95 ms/s) |",
        "| :---: | :---: | :---: | :---: |",
    ])
    for fps in (12, 15, 20, 25):
        total_fps = 4 * fps
        lines.append(
            f"| {fps} | {total_fps} | {round(total_fps * rec.total_p50_ms, 1)} | {round(total_fps * rec.total_p95_ms, 1)} |"
        )

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark CPU JPEG imdecode + letterbox preprocess")
    parser.add_argument("--repeats", type=int, default=3, help="Repeat passes over sample set")
    parser.add_argument("--imgsz", type=int, default=settings.AI_IMGSZ, help="Model input size")
    args = parser.parse_args()

    samples, used_fallback = load_sample_jpegs(limit_per_dir=20)
    if not samples:
        print("[ERROR] No sample JPEGs found in poc/data/bench/samples/ or poc/report/ch17-snapshot.jpg")
        return 1

    detector = YoloPersonDetector(model_path=settings.model_file_path, imgsz=args.imgsz)
    rows = [
        _run_bench_for_flag(k, label, flag, samples, detector, repeats=args.repeats)
        for k, label, flag in _FLAGS
    ]

    md = _format_markdown(rows, used_fallback=used_fallback, imgsz=args.imgsz)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "imgsz": args.imgsz,
        "used_fallback": used_fallback,
        "sample_files": len(samples),
        "results": [asdict(r) for r in rows],
    }
    json_path, md_path = write_bench_outputs("bench_decode", payload, md)
    print("\n" + md)
    print(f"[SAVED] {json_path}")
    print(f"[SAVED] {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Phase 0 benchmark: ONNX Runtime CUDA inference strategies S1/S2/S3 & cuDNN search."""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import onnxruntime as ort

from app.ai.detector import YoloPersonDetector
from app.core.config import BACKEND_ROOT, settings
from scripts.bench.common import (
    load_sample_jpegs,
    percentile,
    query_vram_mb,
    write_bench_outputs,
)


@dataclass
class InferBenchRow:
    model_name: str
    strategy: str
    algo_search: str
    n_cams: int
    active_provider: str
    group_p50_ms: float
    group_p95_ms: float
    per_cam_p50_ms: float
    max_ai_fps_per_cam: float
    vram_used_mb: int | None
    error: str | None = None


def _create_session(
    model_path: Path,
    vram_limit_mb: int,
    algo_search: str,
    arena_strategy: str = "kNextPowerOfTwo",
) -> ort.InferenceSession:
    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

    available = ort.get_available_providers()
    if "CUDAExecutionProvider" in available:
        cuda_opts = {
            "device_id": "0",
            "arena_extend_strategy": arena_strategy,
            "gpu_mem_limit": str(int(vram_limit_mb * 1024 * 1024)),
            "cudnn_conv_algo_search": algo_search,
            "do_copy_in_default_stream": "1",
        }
        providers: list[Any] = [("CUDAExecutionProvider", cuda_opts), "CPUExecutionProvider"]
    else:
        providers = ["CPUExecutionProvider"]

    return ort.InferenceSession(str(model_path), sess_options=opts, providers=providers)


def _warmup_session(session: ort.InferenceSession, imgsz: int, warmup_runs: int) -> str:
    inp_name = session.get_inputs()[0].name
    dummy = np.zeros((1, 3, imgsz, imgsz), dtype=np.float32)
    for _ in range(warmup_runs):
        session.run(None, {inp_name: dummy})
    providers = session.get_providers()
    return providers[0] if providers else "CPUExecutionProvider"


def _bench_strategy(
    model_path: Path,
    strategy: str,
    algo_search: str,
    n_cams: int,
    blobs: list[np.ndarray],
    imgsz: int,
    vram_limit_mb: int,
    warmup_runs: int,
    iters: int,
) -> InferBenchRow:
    try:
        if strategy == "S3":
            sessions = [
                _create_session(model_path, vram_limit_mb=max(256, vram_limit_mb // n_cams), algo_search=algo_search)
                for _ in range(n_cams)
            ]
        else:
            sessions = [_create_session(model_path, vram_limit_mb=vram_limit_mb, algo_search=algo_search)]

        active_provider = ""
        for sess in sessions:
            active_provider = _warmup_session(sess, imgsz=imgsz, warmup_runs=warmup_runs)

        inp_names = [s.get_inputs()[0].name for s in sessions]
        group_ms_list: list[float] = []

        if strategy == "S1":
            sess = sessions[0]
            inp_name = inp_names[0]
            for i in range(iters):
                t0 = time.perf_counter()
                for c in range(n_cams):
                    sess.run(None, {inp_name: blobs[(i + c) % len(blobs)]})
                group_ms_list.append((time.perf_counter() - t0) * 1000.0)
        else:
            with ThreadPoolExecutor(max_workers=n_cams) as pool:
                for i in range(iters):
                    t0 = time.perf_counter()
                    futs = []
                    for c in range(n_cams):
                        sess = sessions[c] if strategy == "S3" else sessions[0]
                        inp_name = inp_names[c] if strategy == "S3" else inp_names[0]
                        blob = blobs[(i + c) % len(blobs)]
                        futs.append(pool.submit(sess.run, None, {inp_name: blob}))
                    for f in futs:
                        f.result()
                    group_ms_list.append((time.perf_counter() - t0) * 1000.0)

        vram = query_vram_mb()
        p50 = percentile(group_ms_list, 50.0)
        p95 = percentile(group_ms_list, 95.0)
        per_cam_p50 = p50 / n_cams
        max_fps = 1000.0 / max(0.001, p50)

        del sessions
        return InferBenchRow(
            model_name=model_path.name,
            strategy=strategy,
            algo_search=algo_search,
            n_cams=n_cams,
            active_provider=active_provider,
            group_p50_ms=round(p50, 2),
            group_p95_ms=round(p95, 2),
            per_cam_p50_ms=round(per_cam_p50, 2),
            max_ai_fps_per_cam=round(max_fps, 1),
            vram_used_mb=vram["used_mb"] if vram else None,
        )
    except Exception as exc:  # noqa: BLE001
        return InferBenchRow(
            model_name=model_path.name,
            strategy=strategy,
            algo_search=algo_search,
            n_cams=n_cams,
            active_provider="error",
            group_p50_ms=0.0,
            group_p95_ms=0.0,
            per_cam_p50_ms=0.0,
            max_ai_fps_per_cam=0.0,
            vram_used_mb=None,
            error=str(exc),
        )


def _check_person_counts(model_path: Path, vram_limit_mb: int) -> list[dict[str, Any]]:
    det = YoloPersonDetector(model_path=model_path, vram_limit_mb=vram_limit_mb)
    items: list[tuple[str, bytes]] = []
    report_img = BACKEND_ROOT.parent / "report" / "ch17-snapshot.jpg"
    if report_img.is_file():
        items.append(("report/ch17-snapshot.jpg", report_img.read_bytes()))
    samples, used_fallback = load_sample_jpegs(limit_per_dir=1)
    if not used_fallback:
        items.extend(samples[:4])

    out: list[dict[str, Any]] = []
    for name, raw in items:
        img = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            continue
        persons = det.detect(img)
        out.append({"image": name, "persons": len(persons)})
    return out


def _format_markdown(
    rows: list[InferBenchRow],
    counts: list[dict[str, Any]],
    vram_before: dict[str, int] | None,
    vram_limit_mb: int,
) -> str:
    lines = [
        "# Phase 0 — GPU Inference Benchmark (`bench_infer.py`)",
        "",
        f"- **Thời điểm**: `{datetime.now(timezone.utc).isoformat()}`",
        f"- **ORT Providers khả dụng**: `{ort.get_available_providers()}`",
        f"- **VRAM limit**: `{vram_limit_mb} MB`",
        f"- **VRAM trước khi chạy**: `{vram_before['used_mb']} / {vram_before['total_mb']} MB`"
        if vram_before
        else "- **VRAM trước khi chạy**: `nvidia-smi unavailable`",
        "",
        "| Model | Chiến lược | cuDNN Search | Số cam | Provider | Nhóm p50 / p95 (ms) | TB/cam (ms) | FPS AI tối đa/cam | VRAM (MB) | Lỗi |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |",
    ]
    for r in rows:
        lines.append(
            f"| {r.model_name} | {r.strategy} | {r.algo_search} | {r.n_cams} | {r.active_provider} | "
            f"{r.group_p50_ms} / {r.group_p95_ms} | {r.per_cam_p50_ms} | {r.max_ai_fps_per_cam} | "
            f"{r.vram_used_mb if r.vram_used_mb is not None else '-'} | {r.error or '-'} |"
        )

    cam4_ok = [r for r in rows if r.n_cams == 4 and not r.error and r.group_p50_ms > 0]
    if cam4_ok:
        best = min(cam4_ok, key=lambda r: r.group_p50_ms)
        lines.extend([
            "",
            "## Đề xuất cấu hình Phase 2 (cho 4 camera)",
            f"- **Chiến lược thắng**: `{best.strategy}` + `cudnn_conv_algo_search={best.algo_search}` (`{best.model_name}`)",
            f"- **Nhóm 4 cam p50 / p95**: `{best.group_p50_ms} / {best.group_p95_ms} ms` → **FPS AI tối đa/cam**: `{best.max_ai_fps_per_cam}`",
        ])

    if counts:
        lines.extend([
            "",
            "## Kiểm tra nhất quán phát hiện người",
            "",
            "| Ảnh mẫu | Số người phát hiện |",
            "| :--- | :---: |",
        ])
        for c in counts:
            lines.append(f"| {c['image']} | {c['persons']} |")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark ONNX Runtime S1/S2/S3 strategies")
    parser.add_argument("--vram-limit-mb", type=int, default=1536, help="CUDA arena VRAM limit in MB")
    parser.add_argument("--iters", type=int, default=40, help="Benchmark iterations per configuration")
    parser.add_argument("--warmup", type=int, default=5, help="Warmup iterations per session")
    parser.add_argument("--fp16", default="", help="Optional path to FP16 ONNX model to compare")
    args = parser.parse_args()

    model_path = settings.model_file_path
    if not model_path.is_file():
        print(f"[ERROR] Model not found: {model_path}")
        return 1

    samples, _ = load_sample_jpegs(limit_per_dir=4)
    detector = YoloPersonDetector(model_path=model_path, imgsz=settings.AI_IMGSZ)
    blobs: list[np.ndarray] = []
    for _name, raw in samples[:8]:
        img = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is not None:
            blobs.append(detector._preprocess(img)[0])
    if not blobs:
        blobs = [np.zeros((1, 3, settings.AI_IMGSZ, settings.AI_IMGSZ), dtype=np.float32)]

    vram_before = query_vram_mb()
    models_to_test = [model_path]
    if args.fp16 and Path(args.fp16).is_file():
        models_to_test.append(Path(args.fp16))

    rows: list[InferBenchRow] = []
    for m_path in models_to_test:
        for algo in ("HEURISTIC", "EXHAUSTIVE"):
            for strategy in ("S1", "S2", "S3"):
                for n_cams in (1, 4):
                    if strategy in ("S2", "S3") and n_cams == 1:
                        continue
                    print(f"[BENCH] model={m_path.name} strategy={strategy} algo={algo} n_cams={n_cams} ...")
                    rows.append(
                        _bench_strategy(
                            model_path=m_path,
                            strategy=strategy,
                            algo_search=algo,
                            n_cams=n_cams,
                            blobs=blobs,
                            imgsz=settings.AI_IMGSZ,
                            vram_limit_mb=args.vram_limit_mb,
                            warmup_runs=args.warmup,
                            iters=args.iters,
                        )
                    )

    counts = _check_person_counts(model_path, vram_limit_mb=args.vram_limit_mb)
    md = _format_markdown(rows, counts=counts, vram_before=vram_before, vram_limit_mb=args.vram_limit_mb)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "providers": ort.get_available_providers(),
        "vram_limit_mb": args.vram_limit_mb,
        "vram_before": vram_before,
        "results": [asdict(r) for r in rows],
        "person_counts": counts,
    }
    json_path, md_path = write_bench_outputs("bench_infer", payload, md)
    print("\n" + md)
    print(f"[SAVED] {json_path}")
    print(f"[SAVED] {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

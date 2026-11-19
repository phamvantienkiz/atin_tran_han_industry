"""Convert YOLO ONNX FP32 model to FP16 (keep_io_types=True) for RTX A400 Tensor Cores."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import onnx
from onnxconverter_common import float16


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert YOLO ONNX FP32 model to FP16.")
    parser.add_argument("--src", type=Path, default=None, help="Source FP32 ONNX model path.")
    parser.add_argument("--dst", type=Path, default=None, help="Destination FP16 ONNX model path.")
    args = parser.parse_args(argv)

    models_dir = Path(__file__).resolve().parents[2] / "models"
    if args.src is not None:
        src_path = args.src.resolve() if args.src.exists() else None
    else:
        src_candidates = [
            models_dir / "yolo26s_best.onnx",
            models_dir / "yolo26s.onnx",
        ]
        src_path = next((p for p in src_candidates if p.exists()), None)

    if src_path is None:
        print(f"[ERROR] Không tìm thấy file ONNX gốc trong {models_dir}", file=sys.stderr)
        return 1

    dst_path = args.dst.resolve() if args.dst is not None else models_dir / "yolo26s_fp16.onnx"
    print(f"[INFO] Đang nạp model FP32: {src_path} ({src_path.stat().st_size / 1024 / 1024:.2f} MB)")
    model_fp32 = onnx.load(str(src_path))
    model_fp16 = float16.convert_float_to_float16(model_fp32, keep_io_types=True)
    onnx.save(model_fp16, str(dst_path))
    print(f"[OK] Đã lưu model FP16: {dst_path} ({dst_path.stat().st_size / 1024 / 1024:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Convert YOLO ONNX FP32 model to FP16 (keep_io_types=True) for RTX A400 Tensor Cores."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import onnx
import onnxruntime as ort
from onnxconverter_common import float16


def _verify_onnx_loadable(model_path: Path) -> None:
    """Validate that ONNX Runtime can load and type-check the converted graph."""
    opts = ort.SessionOptions()
    opts.log_severity_level = 3
    ort.InferenceSession(str(model_path), sess_options=opts, providers=["CPUExecutionProvider"])


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

    # Remove Resize from op_block_list: ONNX Runtime CUDA natively supports FP16 Resize,
    # and keeping Resize in FP16 avoids onnxconverter-common's Resize_output_cast0 type bug.
    custom_block_list = [op for op in float16.DEFAULT_OP_BLOCK_LIST if op != "Resize"]

    attempts = [
        ("FP16 with native FP16 Resize", {"keep_io_types": True, "op_block_list": custom_block_list}),
        (
            "FP16 with disable_shape_infer",
            {"keep_io_types": True, "op_block_list": custom_block_list, "disable_shape_infer": True},
        ),
    ]

    last_err: Exception | None = None
    for label, kwargs in attempts:
        try:
            model_fp32 = onnx.load(str(src_path))
            model_fp16 = float16.convert_float_to_float16(model_fp32, **kwargs)
            onnx.save(model_fp16, str(dst_path))
            _verify_onnx_loadable(dst_path)
            print(
                f"[OK] Đã lưu & kiểm tra ONNX Runtime thành công ({label}): "
                f"{dst_path} ({dst_path.stat().st_size / 1024 / 1024:.2f} MB)"
            )
            return 0
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f"[WARN] Thử {label} không hợp lệ với ONNX Runtime: {exc}", file=sys.stderr)
            if dst_path.exists():
                dst_path.unlink(missing_ok=True)

    print(
        f"[ERROR] Không thể convert model sang FP16 hợp lệ ({last_err}). "
        "Hệ thống sẽ dùng trực tiếp yolo26s_best.onnx (FP32) trên CUDA.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Shared helpers for Phase 0 read-only benchmark scripts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import BACKEND_ROOT, settings


def bench_output_dir() -> Path:
    """Return poc/data/bench (or /app/data/bench in Docker) and ensure it exists."""
    out_dir = settings.cameras_file_path.parent / "bench"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def samples_dir() -> Path:
    """Return poc/data/bench/samples and ensure it exists."""
    path = bench_output_dir() / "samples"
    path.mkdir(parents=True, exist_ok=True)
    return path


def percentile(values: list[float], p: float) -> float:
    """Compute percentile safely for non-empty float lists."""
    if not values:
        return 0.0
    return float(np.percentile(np.asarray(values, dtype=np.float64), p))


def write_bench_outputs(
    name: str,
    payload: dict[str, Any],
    markdown: str,
) -> tuple[Path, Path]:
    """Write <name>.json and <name>.md to poc/data/bench/."""
    out_dir = bench_output_dir()
    json_path = out_dir / f"{name}.json"
    md_path = out_dir / f"{name}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    return json_path, md_path


def query_vram_mb() -> dict[str, int] | None:
    """Query GPU memory used/total (MB) via nvidia-smi, or None if unavailable."""
    try:
        res = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
        if res.returncode != 0 or not res.stdout.strip():
            return None
        first_line = res.stdout.strip().splitlines()[0]
        used_str, total_str = [part.strip() for part in first_line.split(",")[:2]]
        return {"used_mb": int(used_str), "total_mb": int(total_str)}
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def load_sample_jpegs(limit_per_dir: int = 20) -> tuple[list[tuple[str, bytes]], bool]:
    """Load sample JPEGs from poc/data/bench/samples/, falling back to report snapshot."""
    s_dir = samples_dir()
    items: list[tuple[str, bytes]] = []
    if s_dir.exists():
        subdirs = sorted([p for p in s_dir.iterdir() if p.is_dir()])
        for sub in subdirs:
            files = sorted(sub.glob("*.jpg"))[:limit_per_dir]
            for f in files:
                items.append((f"{sub.name}/{f.name}", f.read_bytes()))
        if not items:
            for f in sorted(s_dir.glob("*.jpg"))[:limit_per_dir]:
                items.append((f.name, f.read_bytes()))

    if items:
        return items, False

    fallback = BACKEND_ROOT.parent / "report" / "ch17-snapshot.jpg"
    if fallback.is_file():
        return [(fallback.name, fallback.read_bytes())], True
    return [], True

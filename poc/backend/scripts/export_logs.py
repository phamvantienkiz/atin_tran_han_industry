"""Export the last N lines of app.log into poc/data/ for quick inspection (no rebuild/restart needed)."""

from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
from pathlib import Path


def _resolve_default_paths() -> tuple[Path, Path]:
    container_log = Path("/app/backend/logs/app.log")
    container_out = Path("/app/data/app_log_tail.txt")
    if container_log.exists() or Path("/app/data").is_dir():
        return container_log, container_out

    # Host fallback (relative to poc/ or poc/backend/)
    cwd = Path.cwd()
    for base in (cwd, cwd.parent):
        if (base / "backend" / "logs").is_dir() or (base / "data").is_dir():
            return base / "backend" / "logs" / "app.log", base / "data" / "app_log_tail.txt"
    return Path("backend/logs/app.log"), Path("data/app_log_tail.txt")


def export_log_tail(log_path: Path, out_path: Path, lines: int) -> dict[str, int | str]:
    if not log_path.is_file():
        raise FileNotFoundError(f"Log file not found: {log_path}")

    tail: deque[str] = deque(maxlen=max(1, lines))
    total_lines = 0
    with log_path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            total_lines += 1
            tail.append(line)

    exported = list(tail)
    metrics_cnt = sum(1 for ln in exported if "METRICS " in ln)
    warn_cnt = sum(1 for ln in exported if " WARNING " in ln)
    err_cnt = sum(1 for ln in exported if " ERROR " in ln or " CRITICAL " in ln)

    now_iso = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    header = (
        f"# Exported at: {now_iso}\n"
        f"# Source: {log_path} (total_lines={total_lines}, exported={len(exported)})\n"
        f"# Summary: metrics={metrics_cnt}, warnings={warn_cnt}, errors={err_cnt}\n"
        f"{'=' * 80}\n"
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(header + "".join(exported), encoding="utf-8")
    return {
        "source": str(log_path),
        "output": str(out_path),
        "total_lines": total_lines,
        "exported_lines": len(exported),
        "metrics": metrics_cnt,
        "warnings": warn_cnt,
        "errors": err_cnt,
    }


def main() -> None:
    default_log, default_out = _resolve_default_paths()
    parser = argparse.ArgumentParser(
        description="Export last N lines (default 300) of app.log to poc/data/app_log_tail.txt.",
    )
    parser.add_argument(
        "--lines",
        "-n",
        type=int,
        default=300,
        help="Number of trailing lines to export (recommended: 200-500, default: 300).",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=default_log,
        help=f"Source log file (default: {default_log}).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=default_out,
        help=f"Destination file inside poc/data (default: {default_out}).",
    )
    args = parser.parse_args()

    info = export_log_tail(args.log, args.out, args.lines)
    print(
        f"Exported {info['exported_lines']}/{info['total_lines']} lines "
        f"(metrics={info['metrics']}, warnings={info['warnings']}, errors={info['errors']}) "
        f"-> {info['output']}"
    )


if __name__ == "__main__":
    main()

"""Person-centric PPE inference, RTSP stream processor, and test evaluator.

4 classes: person, glove, hairnet, apron.
1. Detects persons first.
2. Only evaluates PPE items (glove, hairnet, apron) inside detected person boxes;
   standalone PPE detections outside any person are ignored.
3. Supports images, video files, RTSP streams (with configurable ROI polygon &
   counting line in JSON), and --eval on test/ (4x4 confusion matrix, no background).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

CLASSES = ("person", "glove", "hairnet", "apron")
PPE_ITEMS = ("glove", "hairnet", "apron")
DEFAULT_WEIGHTS = Path("prototype/3DSimulation/YOLO/best.pt")
DEFAULT_CONFIG = Path("prototype/3DSimulation/YOLO/cam_config.json")


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ix1 = max(a[0], b[0])
    iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2])
    iy2 = min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = max(1e-6, (a[2] - a[0]) * (a[3] - a[1]))
    area_b = max(1e-6, (b[2] - b[0]) * (b[3] - b[1]))
    return inter / max(1e-6, area_a + area_b - inter)


def _inside_ratio(inner: tuple[float, float, float, float], outer: tuple[float, float, float, float]) -> float:
    ix1 = max(inner[0], outer[0])
    iy1 = max(inner[1], outer[1])
    ix2 = min(inner[2], outer[2])
    iy2 = min(inner[3], outer[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    area = max(1e-6, (inner[2] - inner[0]) * (inner[3] - inner[1]))
    return inter / area


def _center_in(inner: tuple[float, float, float, float], outer: tuple[float, float, float, float]) -> bool:
    cx = 0.5 * (inner[0] + inner[2])
    cy = 0.5 * (inner[1] + inner[3])
    return outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]


def _associate_ppe(persons: list[dict], ppes: list[dict]) -> None:
    """Attach each PPE item to the best-matching person; discard standalone items."""
    for item in ppes:
        best_idx = -1
        best_score = 0.0
        for idx, p in enumerate(persons):
            ratio = _inside_ratio(item["box"], p["box"])
            if ratio >= 0.4 or _center_in(item["box"], p["box"]):
                if ratio > best_score:
                    best_score = ratio
                    best_idx = idx
        if best_idx >= 0:
            persons[best_idx]["ppe"][item["cls"]].append(item)


def _detect_frame(model: YOLO, img: np.ndarray, conf: float = 0.25, imgsz: int = 640) -> list[dict]:
    """Run YOLO on a BGR numpy frame and return person-centric detections."""
    res = model.predict(img, conf=conf, imgsz=imgsz, verbose=False)[0]
    names = res.names

    persons: list[dict] = []
    ppes: list[dict] = []

    for box in res.boxes:
        cls_name = names[int(box.cls[0])]
        xyxy = tuple(float(v) for v in box.xyxy[0].tolist())
        score = float(box.conf[0])
        if cls_name == "person":
            persons.append({"box": xyxy, "conf": score, "ppe": {k: [] for k in PPE_ITEMS}})
        elif cls_name in PPE_ITEMS:
            ppes.append({"cls": cls_name, "box": xyxy, "conf": score})

    _associate_ppe(persons, ppes)
    for p in persons:
        p["missing"] = [k for k in PPE_ITEMS if not p["ppe"][k]]
    return persons


def _draw_persons(
    img: np.ndarray,
    persons: list[dict],
    ppe_check: bool = True,
    fall_check: bool = False,
) -> np.ndarray:
    for p in persons:
        x1, y1, x2, y2 = (int(round(v)) for v in p["box"])
        bw = max(1, x2 - x1)
        bh = max(1, y2 - y1)
        fallen = fall_check and (bw / bh >= 1.15)
        p["fallen"] = fallen
        if fallen:
            color = (77, 77, 255)
            label = "TE NGA"
        elif ppe_check:
            ok = len(p["missing"]) == 0
            color = (60, 200, 80) if ok else (77, 77, 255)
            label = "PPE OK" if ok else "Thieu: " + ", ".join(p["missing"])
        else:
            color = (230, 175, 60)
            label = "person"
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        cv2.putText(img, label, (x1, max(16, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2, cv2.LINE_AA)
        if ppe_check:
            for items in p["ppe"].values():
                for it in items:
                    bx1, by1, bx2, by2 = (int(round(v)) for v in it["box"])
                    cv2.rectangle(img, (bx1, by1), (bx2, by2), (240, 200, 60), 1)
    return img


def evaluate_frame(model: YOLO, image_path: Path, conf: float = 0.25, imgsz: int = 640) -> tuple:
    """Run YOLO detection on an image file and return annotated image + persons."""
    img = cv2.imread(str(image_path))
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    persons = _detect_frame(model, img, conf=conf, imgsz=imgsz)
    _draw_persons(img, persons)
    return img, persons


def _point_in_poly(pt: tuple[float, float], poly: np.ndarray) -> bool:
    return cv2.pointPolygonTest(poly, pt, False) >= 0


def _side_of_line(pt: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (pt[1] - a[1]) - (b[1] - a[1]) * (pt[0] - a[0])


def run_stream(
    model: YOLO,
    source: str,
    cam_cfg: dict,
    conf: float = 0.25,
    imgsz: int = 640,
    headless: bool = False,
    max_frames: int = 0,
    save_video: Path | None = None,
) -> None:
    """Process an RTSP stream or video file with person-first PPE + ROI/Line analytics."""
    cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open stream/video: {source}")

    writer = None
    roi_norm = cam_cfg.get("roi_norm")
    line_norm = cam_cfg.get("line_norm")
    warn_empty_sec = float(cam_cfg.get("warn_empty_sec", 10.0))
    ppe_check = bool(cam_cfg.get("ppe_check", True))
    fall_check = bool(cam_cfg.get("fall_check", False))
    cam_label = cam_cfg.get("label", "")

    empty_start: float | None = None
    in_cnt = 0
    out_cnt = 0
    prev_tracks: list[tuple[int, float, float]] = []
    next_tid = 1
    frame_idx = 0
    fail_cnt = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                if source.startswith("rtsp://"):
                    fail_cnt += 1
                    if max_frames > 0 and fail_cnt > 40:
                        raise RuntimeError(f"RTSP stream stalled: {source}")
                    if fail_cnt % 15 == 0:
                        cap.release()
                        cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    time.sleep(0.2)
                    continue
                break
            fail_cnt = 0

            frame_idx += 1
            h, w = frame.shape[:2]
            now = time.time()

            persons = _detect_frame(model, frame, conf=conf, imgsz=imgsz)
            _draw_persons(frame, persons, ppe_check=ppe_check, fall_check=fall_check)

            # 1) ROI Polygon presence check
            in_roi = 0
            if roi_norm:
                poly = np.array([[int(x * w), int(y * h)] for x, y in roi_norm], dtype=np.int32)
                for p in persons:
                    x1, y1, x2, y2 = p["box"]
                    foot = (0.5 * (x1 + x2), y2)
                    if _point_in_poly(foot, poly):
                        in_roi += 1
                if in_roi > 0:
                    empty_start = None
                    roi_col = (60, 200, 80)
                    roi_txt = f"ROI: {in_roi} nguoi"
                else:
                    if empty_start is None:
                        empty_start = now
                    elapsed = now - empty_start
                    alert = elapsed >= warn_empty_sec
                    roi_col = (77, 77, 255) if alert else (0, 180, 255)
                    roi_txt = f"ROI TRONG {elapsed:.1f}s" + (" [CANH BAO]" if alert else "")
                cv2.polylines(frame, [poly], True, roi_col, 2)
                cv2.putText(frame, roi_txt, (poly[0][0], max(22, poly[0][1] - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, roi_col, 2, cv2.LINE_AA)

            # 2) Counting Line crossing
            if line_norm and len(line_norm) == 2:
                la = (line_norm[0][0] * w, line_norm[0][1] * h)
                lb = (line_norm[1][0] * w, line_norm[1][1] * h)
                cv2.line(frame, (int(la[0]), int(la[1])), (int(lb[0]), int(lb[1])), (255, 160, 60), 2)
                cur_tracks: list[tuple[int, float, float]] = []
                for p in persons:
                    x1, y1, x2, y2 = p["box"]
                    cx, cy = 0.5 * (x1 + x2), 0.5 * (y1 + y2)
                    best_tid, best_d = -1, 80.0
                    prev_xy = (0.0, 0.0)
                    for tid, px, py in prev_tracks:
                        d = float(np.hypot(cx - px, cy - py))
                        if d < best_d:
                            best_d = d
                            best_tid = tid
                            prev_xy = (px, py)
                    if best_tid < 0:
                        best_tid = next_tid
                        next_tid += 1
                    else:
                        s_prev = _side_of_line(prev_xy, la, lb)
                        s_cur = _side_of_line((cx, cy), la, lb)
                        if s_prev < 0 <= s_cur:
                            in_cnt += 1
                        elif s_prev > 0 >= s_cur:
                            out_cnt += 1
                    cur_tracks.append((best_tid, cx, cy))
                prev_tracks = cur_tracks

            ok_cnt = sum(1 for p in persons if not p["missing"])
            fall_cnt = sum(1 for p in persons if p.get("fallen"))
            hud = f"{cam_label + ' | ' if cam_label else ''}Persons: {len(persons)}"
            if ppe_check:
                hud += f" | PPE OK: {ok_cnt} | Vi pham: {len(persons) - ok_cnt}"
            if fall_check:
                hud += f" | Te nga: {fall_cnt}"
            if line_norm:
                hud += f" | In: {in_cnt} Out: {out_cnt}"
            cv2.rectangle(frame, (10, 10), (min(w - 10, 880), 44), (15, 20, 27), -1)
            cv2.putText(frame, hud, (18, 33), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (235, 240, 245), 2, cv2.LINE_AA)

            if save_video is not None:
                if writer is None:
                    save_video.parent.mkdir(parents=True, exist_ok=True)
                    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
                    writer = cv2.VideoWriter(str(save_video), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
                writer.write(frame)

            if not headless:
                cv2.imshow("PPE & PoC Analytics (q/Esc to quit)", frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break

            if max_frames > 0 and frame_idx >= max_frames:
                break
    finally:
        cap.release()
        if writer is not None:
            writer.release()
        if not headless:
            cv2.destroyAllWindows()
    print(f"Processed {frame_idx} frames from {source}")


def _load_gt(label_path: Path, width: int, height: int) -> tuple[list[dict], list[dict]]:
    persons: list[dict] = []
    ppes: list[dict] = []
    if not label_path.exists():
        return persons, ppes
    for raw in label_path.read_text(encoding="utf-8").splitlines():
        parts = raw.strip().split()
        if len(parts) < 5:
            continue
        cid = int(parts[0])
        if cid < 0 or cid >= len(CLASSES):
            continue
        xc, yc, bw, bh = (float(v) for v in parts[1:5])
        x1 = (xc - bw * 0.5) * width
        y1 = (yc - bh * 0.5) * height
        x2 = (xc + bw * 0.5) * width
        y2 = (yc + bh * 0.5) * height
        cls_name = CLASSES[cid]
        if cls_name == "person":
            persons.append({"box": (x1, y1, x2, y2), "ppe": {k: [] for k in PPE_ITEMS}})
        else:
            ppes.append({"cls": cls_name, "box": (x1, y1, x2, y2)})
    _associate_ppe(persons, ppes)
    return persons, ppes


def eval_test(model: YOLO, test_dir: Path, conf: float = 0.25, imgsz: int = 640) -> None:
    """Person-first evaluation on test set with 4x4 confusion matrix (no background)."""
    img_dir = test_dir / "images"
    lbl_dir = test_dir / "labels"
    cm = [[0 for _ in CLASSES] for _ in CLASSES]
    attr_stats = {k: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for k in PPE_ITEMS}
    gt_person_total = 0
    matched_persons = 0

    for img_path in sorted(img_dir.glob("*.jpg")):
        img = cv2.imread(str(img_path))
        h, w = img.shape[:2]
        gt_persons, _ = _load_gt(lbl_dir / f"{img_path.stem}.txt", w, h)
        _, pred_persons = evaluate_frame(model, img_path, conf=conf, imgsz=imgsz)

        gt_person_total += len(gt_persons)
        used_pred: set[int] = set()

        for gp in gt_persons:
            best_j = -1
            best_iou = 0.45
            for j, pp in enumerate(pred_persons):
                if j in used_pred:
                    continue
                val = _iou(gp["box"], pp["box"])
                if val >= best_iou:
                    best_iou = val
                    best_j = j
            if best_j < 0:
                continue
            used_pred.add(best_j)
            matched_persons += 1
            cm[0][0] += 1

            pp = pred_persons[best_j]
            gt_items = [{"cls": k, "box": it["box"]} for k in PPE_ITEMS for it in gp["ppe"][k]]
            pr_items = [{"cls": k, "box": it["box"]} for k in PPE_ITEMS for it in pp["ppe"][k]]
            used_pr: set[int] = set()
            for gi in gt_items:
                best_k = -1
                best_b_iou = 0.25
                for k_idx, pi in enumerate(pr_items):
                    if k_idx in used_pr:
                        continue
                    b_iou = _iou(gi["box"], pi["box"])
                    if b_iou >= best_b_iou:
                        best_b_iou = b_iou
                        best_k = k_idx
                if best_k >= 0:
                    used_pr.add(best_k)
                    gt_cid = CLASSES.index(gi["cls"])
                    pr_cid = CLASSES.index(pr_items[best_k]["cls"])
                    cm[gt_cid][pr_cid] += 1

            for k in PPE_ITEMS:
                gt_has = len(gp["ppe"][k]) > 0
                pr_has = len(pp["ppe"][k]) > 0
                if gt_has and pr_has:
                    attr_stats[k]["tp"] += 1
                elif not gt_has and pr_has:
                    attr_stats[k]["fp"] += 1
                elif gt_has and not pr_has:
                    attr_stats[k]["fn"] += 1
                else:
                    attr_stats[k]["tn"] += 1

    print(f"\n=== PERSON-FIRST TEST EVALUATION (conf={conf}, imgsz={imgsz}) ===")
    print(f"Matched persons: {matched_persons}/{gt_person_total}")
    print("\nConfusion Matrix (rows=GT, cols=Pred, NO background):")
    header = f"{'':10s} " + " ".join(f"{c:>8s}" for c in CLASSES)
    print(header)
    for i, c in enumerate(CLASSES):
        row = " ".join(f"{cm[i][j]:8d}" for j in range(len(CLASSES)))
        print(f"{c:10s} {row}")

    print("\nPerson-Gated PPE Attribute Check (on matched persons):")
    for k in PPE_ITEMS:
        s = attr_stats[k]
        p = s["tp"] / max(1, s["tp"] + s["fp"])
        r = s["tp"] / max(1, s["tp"] + s["fn"])
        acc = (s["tp"] + s["tn"]) / max(1, matched_persons)
        print(f"  {k:8s}: Acc={acc:.3f}  P={p:.3f}  R={r:.3f}  (TP={s['tp']}, FP={s['fp']}, FN={s['fn']}, TN={s['tn']})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Person-centric PPE inference, RTSP & evaluation")
    parser.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    parser.add_argument("--source", default="prototype/3DSimulation/YOLO/test/images", help="Image/dir, video, or rtsp:// URL")
    parser.add_argument("--out", type=Path, default=Path("prototype/3DSimulation/YOLO/infer_out"))
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--cam", default="cam27", help="Camera key in cam_config.json")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--headless", action="store_true", help="Run stream without GUI window")
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after N frames (0 = unlimited)")
    parser.add_argument("--save-video", type=Path, default=None, help="Optional output .mp4 path")
    parser.add_argument("--eval", action="store_true", help="Run person-first evaluation on test dir")
    parser.add_argument("--test-dir", type=Path, default=Path("prototype/3DSimulation/YOLO/test"))
    args = parser.parse_args()

    model = YOLO(str(args.weights))
    if args.eval:
        eval_test(model, args.test_dir, conf=args.conf, imgsz=args.imgsz)
        return

    src_str = str(args.source)
    is_stream = src_str.startswith(("rtsp://", "http://", "https://")) or Path(src_str).suffix.lower() in {".webm", ".mp4", ".avi", ".mkv"}
    if is_stream:
        cam_cfg = {}
        if args.config.exists():
            cam_cfg = json.loads(args.config.read_text(encoding="utf-8")).get(args.cam, {})
        run_stream(
            model,
            src_str,
            cam_cfg,
            conf=args.conf,
            imgsz=args.imgsz,
            headless=args.headless,
            max_frames=args.max_frames,
            save_video=args.save_video,
        )
        return

    args.out.mkdir(parents=True, exist_ok=True)
    src_path = Path(src_str)
    sources = [src_path] if src_path.is_file() else sorted(src_path.glob("*.jpg"))
    for src in sources:
        vis, persons = evaluate_frame(model, src, conf=args.conf, imgsz=args.imgsz)
        out_path = args.out / src.name
        cv2.imwrite(str(out_path), vis)
        ok_cnt = sum(1 for p in persons if not p["missing"])
        print(f"{src.name}: {len(persons)} persons ({ok_cnt} PPE OK, {len(persons) - ok_cnt} missing) -> {out_path}")


if __name__ == "__main__":
    main()

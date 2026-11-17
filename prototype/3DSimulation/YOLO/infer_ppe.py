"""Person-centric PPE inference and evaluation (4 classes: person, glove, hairnet, apron).

1. Detects persons first.
2. Only evaluates PPE items (glove, hairnet, apron) inside detected person boxes;
   standalone PPE detections outside any person are ignored.
3. Supports --eval on test/ to compute person-gated PPE metrics and a clean
   4x4 confusion matrix without a 'background' class.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
from ultralytics import YOLO

CLASSES = ("person", "glove", "hairnet", "apron")
PPE_ITEMS = ("glove", "hairnet", "apron")
DEFAULT_WEIGHTS = Path(
    "runs/detect/prototype/3DSimulation/YOLO/runs/ppe_yolo11s_4cls/weights/best.pt"
)


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


def evaluate_frame(model: YOLO, image_path: Path, conf: float = 0.25, imgsz: int = 640) -> tuple:
    """Run YOLO detection and associate PPE items only with detected persons."""
    img = cv2.imread(str(image_path))
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")

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
        x1, y1, x2, y2 = (int(round(v)) for v in p["box"])
        ok = len(p["missing"]) == 0
        color = (60, 200, 80) if ok else (77, 77, 255)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        label = "PPE OK" if ok else "Thieu: " + ", ".join(p["missing"])
        cv2.putText(img, label, (x1, max(16, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2, cv2.LINE_AA)
        for items in p["ppe"].values():
            for it in items:
                bx1, by1, bx2, by2 = (int(round(v)) for v in it["box"])
                cv2.rectangle(img, (bx1, by1), (bx2, by2), (240, 200, 60), 1)

    return img, persons


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
    cm = [[0 for _ in CLASSES] for _ in CLASSES]  # [gt][pred], no background
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

        # Step 1: Match predicted person to GT person first (IoU >= 0.45)
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
            cm[0][0] += 1  # person -> person

            pp = pred_persons[best_j]
            # Step 2: Only inside confirmed matched person, evaluate PPE items
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

            # Per-person attribute check (has item vs missing item)
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
    parser = argparse.ArgumentParser(description="Person-centric PPE inference and evaluation")
    parser.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    parser.add_argument("--source", type=Path, default=Path("prototype/3DSimulation/YOLO/test/images"))
    parser.add_argument("--out", type=Path, default=Path("prototype/3DSimulation/YOLO/infer_out"))
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--eval", action="store_true", help="Run person-first evaluation on test dir")
    parser.add_argument("--test-dir", type=Path, default=Path("prototype/3DSimulation/YOLO/test"))
    args = parser.parse_args()

    model = YOLO(str(args.weights))
    if args.eval:
        eval_test(model, args.test_dir, conf=args.conf, imgsz=args.imgsz)
        return

    args.out.mkdir(parents=True, exist_ok=True)
    sources = [args.source] if args.source.is_file() else sorted(args.source.glob("*.jpg"))
    for src in sources:
        vis, persons = evaluate_frame(model, src, conf=args.conf, imgsz=args.imgsz)
        out_path = args.out / src.name
        cv2.imwrite(str(out_path), vis)
        ok_cnt = sum(1 for p in persons if not p["missing"])
        print(f"{src.name}: {len(persons)} persons ({ok_cnt} PPE OK, {len(persons) - ok_cnt} missing) -> {out_path}")


if __name__ == "__main__":
    main()

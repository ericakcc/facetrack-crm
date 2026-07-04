"""Validate & tune the wrinkle metric against FFHQ-Wrinkle human annotations.

The wrinkle score is `scoring.wrinkle_raw` — the fraction of pixels whose Sobel
gradient magnitude exceeds a fixed cutoff (currently 30). Until now that cutoff
and `WRINKLE_RAW_RANGE` were hand-calibrated on 5 reference faces. This script
grades the metric against **1,000 dermatologically hand-drawn wrinkle masks**
(FFHQ-Wrinkle, Kim et al.) so the calibration rests on ground truth.

Crucially it measures the metric **the way production does** — on the forehead
and cheek ROIs, not the whole face. The whole-face number is reported too, as a
contrast, because it is dominated by eyebrow / eye / hairline / nostril edges
that the deployed pipeline never scores.

Two questions, two answers:

1.  Ranking validity — does per-face `wrinkle_raw` (ROI mean) order faces the
    way the human annotations do?  Spearman ρ / Pearson r vs mask coverage
    inside the same ROIs. This is the property the longitudinal chart and
    cross-patient comparison rely on.

2.  Localization + threshold tuning — of the pixels the Sobel cutoff fires on
    *inside skin ROIs*, how many land on a hand-drawn wrinkle?  Sweep the cutoff,
    report precision / recall / F1 vs the (tolerance-dilated) masks, recommend
    the F1-maximizing cutoff. This is the offline knob for `magnitude > T`.

Usage:
    uv run python scripts/validation/validate_wrinkle_ffhq.py
    uv run python scripts/validation/validate_wrinkle_ffhq.py --limit 200 --thresholds 15,20,25,30,40

Reads   data/validation/ffhq_wrinkle/{images/*.webp, manual_wrinkle_masks/*.png}
Writes  data/validation/ffhq_wrinkle/results/{wrinkle_per_image.csv,
        wrinkle_threshold_sweep.csv, wrinkle_scatter.png}
No real-person pixels leave the machine; only aggregate CSV/PNG are produced.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from facetrack.config import (  # noqa: E402
    NORMALIZED_FACE_WIDTH_PX,
    SCALE_FACTOR_MAX,
    SCALE_FACTOR_MIN,
)
from facetrack.cv_pipeline import (  # noqa: E402
    LANDMARK_FACE_LEFT,
    LANDMARK_FACE_RIGHT,
    FacePipeline,
)
from facetrack.db import Region  # noqa: E402
from facetrack.scoring import WRINKLE_RAW_RANGE, wrinkle_raw  # noqa: E402
from facetrack.visualization import polygon_mask  # noqa: E402

DATA = REPO / "data" / "validation" / "ffhq_wrinkle"
IMAGES = DATA / "images"
MASKS = DATA / "manual_wrinkle_masks"
RESULTS = DATA / "results"

# Production scores forehead + both cheeks for skin texture; chin/lips excluded.
SKIN_REGIONS = (Region.FOREHEAD, Region.LEFT_CHEEK, Region.RIGHT_CHEEK)
# Hand-drawn wrinkle lines are 1-2px; allow a firing pixel within this radius to
# count as a hit (annotator stroke-placement noise).
MASK_DILATE_PX = 2


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    """Spearman rank correlation, dependency-free (no scipy)."""
    rx = np.argsort(np.argsort(x)).astype(np.float64)
    ry = np.argsort(np.argsort(y)).astype(np.float64)
    return pearson(rx, ry)


def pearson(x: np.ndarray, y: np.ndarray) -> float:
    x = x - x.mean()
    y = y - y.mean()
    denom = np.sqrt((x * x).sum() * (y * y).sum())
    return float((x * y).sum() / denom) if denom else 0.0


def firing_map(bgr: np.ndarray, threshold: float) -> np.ndarray:
    """Sobel-magnitude firing map — the internals of `wrinkle_raw`, thresholded."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    gx = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    return np.sqrt(gx * gx + gy * gy) > threshold


def normalize_to_face_width(bgr: np.ndarray, mask: np.ndarray, landmarks: np.ndarray):
    """Rescale image+mask+landmarks so the face is NORMALIZED_FACE_WIDTH_PX wide.

    FFHQ faces are already upright and centered, so — unlike the deployed
    pipeline — we only need the scale part of alignment, not the rotation. Scaling
    image, mask, and landmarks by the same factor keeps them pixel-aligned, which
    is what lets us intersect the metric's firing map with the human mask.
    """
    face_w = float(np.linalg.norm(landmarks[LANDMARK_FACE_LEFT] - landmarks[LANDMARK_FACE_RIGHT]))
    if face_w < 1e-3:
        return None
    scale = min(max(NORMALIZED_FACE_WIDTH_PX / face_w, SCALE_FACTOR_MIN), SCALE_FACTOR_MAX)
    new_wh = (max(1, round(bgr.shape[1] * scale)), max(1, round(bgr.shape[0] * scale)))
    img = cv2.resize(bgr, new_wh, interpolation=cv2.INTER_AREA)
    msk = cv2.resize(mask.astype(np.uint8), new_wh, interpolation=cv2.INTER_NEAREST) > 0
    return img, msk, landmarks * scale


def roi_union(pipeline: FacePipeline, landmarks: np.ndarray, shape) -> np.ndarray | None:
    """Boolean union of the production skin-ROI polygons at these landmarks."""
    union = np.zeros(shape[:2], dtype=bool)
    got = False
    for region in SKIN_REGIONS:
        poly = pipeline._region_polygon(landmarks, region)  # noqa: SLF001 (validation reuse)
        if poly is None or len(poly) < 3:
            continue
        union |= polygon_mask(poly, shape) > 0
        got = True
    return union if got else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, help="cap number of images (default all)")
    ap.add_argument(
        "--thresholds",
        type=str,
        default="15,20,25,30,35,40,50,60",
        help="comma-separated Sobel cutoffs to sweep",
    )
    args = ap.parse_args()
    thresholds = [float(t) for t in args.thresholds.split(",")]

    pipeline = FacePipeline()
    mask_ids = sorted(p.stem for p in MASKS.glob("*.png"))
    if not mask_ids:
        sys.exit(f"No masks under {MASKS}. See data/validation/README.md.")

    RESULTS.mkdir(exist_ok=True)
    kernel = np.ones((MASK_DILATE_PX * 2 + 1,) * 2, np.uint8)

    roi_metric, roi_gt, whole_metric, whole_gt = [], [], [], []
    rows = []
    # localization accumulators: tp/fp/fn per threshold, restricted to skin ROIs
    tp = {t: 0 for t in thresholds}
    fp = {t: 0 for t in thresholds}
    fn = {t: 0 for t in thresholds}
    n_detect_fail = 0
    n_done = 0

    for fid in mask_ids:
        img_path = IMAGES / f"{fid}.webp"
        if not img_path.exists():
            continue
        bgr = cv2.imread(str(img_path))
        mask = cv2.imread(str(MASKS / f"{fid}.png"), cv2.IMREAD_GRAYSCALE)
        if bgr is None or mask is None:
            continue

        landmarks, _ = pipeline._detect(bgr)  # noqa: SLF001 (validation reuse)
        if landmarks is None:
            n_detect_fail += 1
            continue
        norm = normalize_to_face_width(bgr, mask > 0, landmarks)
        if norm is None:
            n_detect_fail += 1
            continue
        img, msk, lm = norm
        union = roi_union(pipeline, lm, img.shape)
        if union is None or not union.any():
            n_detect_fail += 1
            continue

        # Production scores the CLAHE-normalized crop, so measure on the same:
        # CLAHE raises local contrast and hence Sobel magnitudes, so the raw
        # values here are directly comparable to WRINKLE_RAW_RANGE / cutoff=30.
        norm_img = pipeline._normalize_lighting(img)  # noqa: SLF001 (validation reuse)

        # Q1: production metric (ROI) and whole-face contrast
        m_roi = float(wrinkle_raw(norm_img, (union.astype(np.uint8) * 255)))
        m_whole = float(wrinkle_raw(norm_img))
        d_roi = float(msk[union].mean())
        d_whole = float(msk.mean())
        roi_metric.append(m_roi)
        roi_gt.append(d_roi)
        whole_metric.append(m_whole)
        whole_gt.append(d_whole)
        rows.append((fid, m_roi, d_roi, m_whole, d_whole))

        # Q2: localization inside ROI union
        gt_dil = cv2.dilate(msk.astype(np.uint8), kernel).astype(bool)
        gt_line = msk
        for t in thresholds:
            fire = firing_map(norm_img, t) & union
            tp[t] += int((fire & gt_dil).sum())
            fp[t] += int((fire & ~gt_dil).sum())
            fn[t] += int((~fire & gt_line & union).sum())

        n_done += 1
        if args.limit and n_done >= args.limit:
            break
        if n_done % 200 == 0:
            print(f"  ...{n_done} faces processed", flush=True)

    if not rows:
        sys.exit("No usable faces (detection failed on all). Check the download.")

    roi_metric = np.array(roi_metric)
    roi_gt = np.array(roi_gt)
    whole_metric = np.array(whole_metric)
    whole_gt = np.array(whole_gt)

    with (RESULTS / "wrinkle_per_image.csv").open("w") as f:
        f.write("ffhq_id,wrinkle_raw_roi,gt_density_roi,wrinkle_raw_whole,gt_density_whole\n")
        for fid, mr, dr, mw, dw in rows:
            f.write(f"{fid},{mr:.6f},{dr:.6f},{mw:.6f},{dw:.6f}\n")

    print(f"\nProcessed {n_done} faces ({n_detect_fail} skipped: no face / no ROI).\n")
    print("Q1  Ranking validity  (per-face wrinkle_raw vs human mask coverage)")
    print(
        f"    skin ROIs   Spearman rho = {spearman(roi_metric, roi_gt):+.3f}   "
        f"Pearson r = {pearson(roi_metric, roi_gt):+.3f}   ← production behavior"
    )
    print(
        f"    whole face  Spearman rho = {spearman(whole_metric, whole_gt):+.3f}   "
        f"Pearson r = {pearson(whole_metric, whole_gt):+.3f}   (contrast: eyes/hair contaminate)"
    )
    lo, hi = np.percentile(roi_metric, [5, 95])
    print(
        f"    wrinkle_raw(ROI) p5-p95 = [{lo:.3f}, {hi:.3f}]   "
        f"current WRINKLE_RAW_RANGE = {WRINKLE_RAW_RANGE}"
    )
    print()

    print("Q2  Localization / cutoff tuning  (firing pixels vs masks, inside skin ROIs)")
    print("    cutoff   precision   recall      F1")
    sweep_rows = []
    best = (None, -1.0)
    for t in thresholds:
        prec = tp[t] / (tp[t] + fp[t]) if tp[t] + fp[t] else 0.0
        rec = tp[t] / (tp[t] + fn[t]) if tp[t] + fn[t] else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        sweep_rows.append((t, prec, rec, f1))
        if f1 > best[1]:
            best = (t, f1)
        print(f"    {t:6.0f}   {prec:8.3f}   {rec:7.3f}   {f1:6.3f}")

    with (RESULTS / "wrinkle_threshold_sweep.csv").open("w") as f:
        f.write("sobel_cutoff,precision,recall,f1\n")
        for t, p, rc, f1 in sweep_rows:
            f.write(f"{t},{p:.6f},{rc:.6f},{f1:.6f}\n")
    print(
        f"\n    → F1-max cutoff = {best[0]:.0f} (F1={best[1]:.3f}); "
        "wrinkle_raw currently hard-codes 30 (scoring.py:196)."
    )

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(6, 5), dpi=120)
        ax.scatter(roi_gt * 100, roi_metric, s=8, alpha=0.4, color="#2b6cb0")
        ax.set_xlabel("Human wrinkle coverage inside skin ROIs (%)")
        ax.set_ylabel("wrinkle_raw (ROI Sobel firing ratio)")
        ax.set_title(f"FFHQ-Wrinkle · n={n_done} · Spearman ρ={spearman(roi_metric, roi_gt):.2f}")
        fig.tight_layout()
        fig.savefig(RESULTS / "wrinkle_scatter.png")
        print(f"\nWrote results to {RESULTS}/")
    except Exception as e:  # noqa: BLE001
        print(f"\n(scatter plot skipped: {e})")


if __name__ == "__main__":
    main()

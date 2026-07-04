"""Render real system outputs on EricZou's actual photos for the pitch deck.

Runs the genuine FacePipeline + visualization stack (the same code the Streamlit
app uses) over patient4's three real intake photos and writes PNGs to
docs/assets/. These are the *real* "face in system state" visuals — heatmaps,
ROI polygons, aligned crops — not mock-ups.

Usage:
    uv run python scripts/render_pitch_assets.py
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from facetrack.cv_pipeline import get_pipeline
from facetrack.visualization import (
    compose_intake_view,
    metric_response_map,
    overlay_heatmap,
    skin_mask_from_landmarks,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets"
OUT.mkdir(parents=True, exist_ok=True)

# visit_id -> (label, photo) from the real DB rows
VISITS = {
    10: ("v1_0118", ROOT / "data/photos/patient4_20260518_085926_front.jpg"),
    11: ("v2_0319", ROOT / "data/photos/patient4_20260518_090138_front.jpg"),
    12: ("v3_0518", ROOT / "data/photos/patient4_20260518_090413_front.jpg"),
}

METRICS = ["pigmentation", "erythema", "wrinkle", "pore", "uniformity"]
METRIC_ZH = {
    "pigmentation": "色素沉澱",
    "erythema": "泛紅",
    "wrinkle": "細紋",
    "pore": "毛孔",
    "uniformity": "膚色均勻度",
}


def save(name: str, bgr: np.ndarray) -> None:
    path = OUT / name
    cv2.imwrite(str(path), bgr)
    print(f"  wrote {path.relative_to(ROOT)}  ({bgr.shape[1]}x{bgr.shape[0]})")


def main() -> None:
    pipe = get_pipeline()
    results = {}

    for vid, (label, photo) in VISITS.items():
        print(f"[visit {vid}] {label} :: {photo.name}")
        img = cv2.imread(str(photo), cv2.IMREAD_COLOR)
        if img is None:
            print(f"  !! could not read {photo}")
            continue
        res = pipe.process(img)
        if not res.face_detected:
            print("  !! no face detected")
            continue
        results[vid] = (label, res)

        aligned = res.aligned_image

        # 1. clean aligned face
        save(f"face_{label}_clean.png", aligned)

        # 2. ROI polygons only (no heatmap) — the measurement geometry
        roi_view = compose_intake_view(
            aligned,
            res.landmarks_px,
            res.roi_polygons,
            roi_bboxes=res.roi_bboxes,
            heatmap_metric=None,
            show_landmarks=False,
            show_roi=True,
        )
        save(f"face_{label}_roi.png", roi_view)

        # 3. per-metric heatmap (skin-masked), the explainability money shot
        for metric in METRICS:
            response = metric_response_map(aligned, metric)
            mask = skin_mask_from_landmarks(res.landmarks_px, aligned.shape)
            heat = overlay_heatmap(aligned, response, face_mask=mask)
            save(f"heat_{label}_{metric}.png", heat)

        # 4. canonical intake composite (pigmentation heatmap + ROI) — what the
        #    app shows on the intake/history view for the pico hero metric.
        composite = compose_intake_view(
            aligned,
            res.landmarks_px,
            res.roi_polygons,
            roi_bboxes=res.roi_bboxes,
            heatmap_metric="pigmentation",
            show_landmarks=False,
            show_roi=True,
        )
        save(f"composite_{label}_pigmentation.png", composite)

    print(f"\nDone. {len(list(OUT.glob('*.png')))} PNGs in {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

"""Scale-normalization contract for the imaging pipeline.

The product's core promise is cross-visit comparability. All five scoring
metrics use fixed pixel-size kernels (15x15 black-hat, sigma=1.4 LoG, 3x3
Sobel), so the SAME skin photographed at a different distance / resolution
previously produced materially different scores (measured drift: up to +5
points on pore/wrinkle when the input was halved). The pipeline therefore
rescales every aligned face to a fixed anatomical width before ROI
extraction, making the metrics (approximately) invariant to camera
resolution and subject distance.

These tests run MediaPipe on a real CC0 test face (vendored model, ~10 ms
per call) — they are integration tests, not unit tests.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from facetrack.config import NORMALIZED_FACE_WIDTH_PX
from facetrack.cv_pipeline import (
    LANDMARK_FACE_LEFT,
    LANDMARK_FACE_RIGHT,
    FacePipeline,
)
from facetrack.scoring import score_region

TEST_IMAGE = Path(__file__).resolve().parents[1] / "data" / "test_images" / "test_1.png"


@pytest.fixture(scope="module")
def pipeline() -> FacePipeline:
    return FacePipeline()


@pytest.mark.skipif(not TEST_IMAGE.exists(), reason="test image not present")
def test_aligned_face_width_is_normalized(pipeline: FacePipeline) -> None:
    """After processing, the anatomical face width must equal the target."""
    result = pipeline.process(cv2.imread(str(TEST_IMAGE)))
    assert result.face_detected
    width = float(
        np.linalg.norm(
            result.landmarks_px[LANDMARK_FACE_LEFT] - result.landmarks_px[LANDMARK_FACE_RIGHT]
        )
    )
    assert abs(width - NORMALIZED_FACE_WIDTH_PX) / NORMALIZED_FACE_WIDTH_PX < 0.02


@pytest.mark.skipif(not TEST_IMAGE.exists(), reason="test image not present")
def test_scale_factor_is_reported(pipeline: FacePipeline) -> None:
    """The applied scale factor is surfaced for the quality report / audit."""
    result = pipeline.process(cv2.imread(str(TEST_IMAGE)))
    assert result.face_detected
    assert result.scale_factor > 0.0


@pytest.mark.skipif(not TEST_IMAGE.exists(), reason="test image not present")
def test_undersampled_face_rejected_by_gate(pipeline: FacePipeline) -> None:
    """A face below MIN_NATIVE_FACE_WIDTH_PX must be rejected outright —
    upscaling cannot fabricate the skin texture the metrics measure, so
    scoring it would silently break cross-visit comparability."""
    from facetrack.consistency_gate import ConsistencyGate

    img = cv2.imread(str(TEST_IMAGE))
    tiny = cv2.resize(img, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    result = pipeline.process(tiny)
    assert result.face_detected
    report, _ = ConsistencyGate().evaluate(tiny, result)
    assert report.sharpness.passed is False
    assert "臉部影像過小" in report.sharpness.reason
    assert report.overall_passed is False


@pytest.mark.skipif(not TEST_IMAGE.exists(), reason="test image not present")
def test_scores_stable_across_input_resolution(pipeline: FacePipeline) -> None:
    """The same photo at full and half input resolution must produce nearly
    identical scores. Before normalization the measured drift reached
    +4.4 points (pore, left cheek, this very image)."""
    img = cv2.imread(str(TEST_IMAGE))
    small = cv2.resize(img, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)

    full_res = pipeline.process(img)
    half_res = pipeline.process(small)
    assert full_res.face_detected and half_res.face_detected

    drifts: list[float] = []
    for region in full_res.rois:
        if region not in half_res.rois:
            continue
        a = score_region(full_res.rois[region], full_res.roi_masks[region])
        b = score_region(half_res.rois[region], half_res.roi_masks[region])
        for metric in ("pigmentation", "erythema", "wrinkle", "pore", "uniformity"):
            drifts.append(abs(getattr(a, metric) - getattr(b, metric)))
    assert drifts, "no comparable regions"
    assert max(drifts) < 1.5, f"max cross-resolution drift {max(drifts):.2f} >= 1.5"

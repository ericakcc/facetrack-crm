"""Quantitative skin scoring engine.

The core IP. Five reproducible, deterministic CV metrics — never an LLM:

    pigmentation   black-hat morphology density (dark-spot pixel ratio)
    erythema       mean a* in CIE Lab (redness)
    wrinkle        Sobel-gradient-magnitude edge density (isotropic)
    pore           Laplacian-of-Gaussian blob density at small scale
    uniformity     inverse-normalized L* standard deviation

Each metric maps to a 0–10 score via linear clamping against an empirical
range observed on healthy adult faces. The ranges are intentionally
documented as constants so they can be re-calibrated when a clinic
provides its own training distribution.

v2 (SCORING_VERSION = 2): every metric is computed on an *effective* mask
that excludes specular-glare (L* > SPECULAR_L_MAX) and deep-shadow
(L* < SHADOW_L_MIN) pixels, and the upstream pipeline rescales each face to
a fixed anatomical width — see cv_pipeline._align_face. Formula changes
bump SCORING_VERSION; the value is persisted per visit.

Score convention:
    * pigmentation / erythema / wrinkle / pore — HIGHER = more concern
    * uniformity                                — HIGHER = more uniform (better)

All functions return floats; no I/O, no LLM, no randomness.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from facetrack.config import SCORING_VERSION
from facetrack.db import Region

__all__ = [
    "SCORING_VERSION",
    "RawMetrics",
    "RegionScores",
    "aggregate_face_scores",
    "erythema_raw",
    "pigmentation_raw",
    "pore_raw",
    "score_region",
    "score_visit",
    "uniformity_raw",
    "wrinkle_raw",
]

# Pixels outside this L* band (OpenCV LAB, 0-255) are excluded from every
# metric: above the ceiling is specular glare (clinic downlights, oily
# T-zone shine — lighting artifact, not skin), below the floor is deep
# shadow / hair / occluder. Glare previously counted as "non-uniform tone"
# and its rim as "edges"; near-black blobs counted as melanin spots.
SPECULAR_L_MAX = 235
SHADOW_L_MIN = 20
# If exclusion would remove more than this fraction of the ROI, fall back to
# the unrefined mask — scoring a near-empty region is worse than scoring a
# glary one (the gate's exposure check owns that failure mode).
EXCLUSION_MIN_KEEP_RATIO = 0.3

# Empirical raw-metric ranges, calibrated on the 5 evenly-lit reference
# faces in data/test_images at the v2 normalization scale (every face
# rescaled to NORMALIZED_FACE_WIDTH_PX = 512 before ROI extraction, so the
# ranges are stable across camera resolution and subject distance).
# Wrinkle/pore shifted upward vs v1 because texture-density ratios grow at
# the smaller sampling scale (fixed 3x3/5x5 kernels cover relatively larger
# anatomy); pigmentation/erythema/uniformity distributions were unchanged.
# Wrinkle was then re-fitted against FFHQ-Wrinkle ground truth (n=1000,
# ROI-restricted, CLAHE-matched): real-face p5-p95 = [0.197, 0.619], so the
# reference-face (0.25, 0.75) ceiling was never reached and the top of the
# 0-10 scale was dead range. Guarded by tests/test_validation_benchmarks.py.
# Re-calibrate when a clinic provides its own training distribution.
PIGMENTATION_RAW_RANGE = (0.02, 0.30)
ERYTHEMA_RAW_RANGE = (134.0, 148.0)
WRINKLE_RAW_RANGE = (0.20, 0.62)
PORE_RAW_RANGE = (0.03, 0.22)
UNIFORMITY_RAW_RANGE = (12.0, 50.0)


@dataclass
class RawMetrics:
    """Raw scalar measurements (before 0-10 normalization). Useful for TDD."""

    pigmentation_raw: float
    erythema_raw: float
    wrinkle_raw: float
    pore_raw: float
    uniformity_raw: float


@dataclass
class RegionScores:
    """0-10 normalized scores for a single ROI."""

    pigmentation: float
    erythema: float
    wrinkle: float
    pore: float
    uniformity: float
    raw: RawMetrics


def _clamp_score(value: float, lo: float, hi: float, *, invert: bool = False) -> float:
    """Linearly map `value` from [lo, hi] to [0, 10], clamped at the endpoints.

    Args:
        value: Raw metric value.
        lo: Value that maps to 0.
        hi: Value that maps to 10.
        invert: If True, swap so high raw -> low score.
    """
    if hi == lo:
        return 0.0
    normalized = (value - lo) / (hi - lo)
    if invert:
        normalized = 1.0 - normalized
    normalized = max(0.0, min(1.0, normalized))
    return round(normalized * 10.0, 2)


def _effective_mask(bgr: np.ndarray, roi_mask: np.ndarray | None) -> np.ndarray | None:
    """Refine `roi_mask` by excluding specular-glare and deep-shadow pixels.

    Returns the refined mask, or the original mask unchanged when exclusion
    would remove more than (1 - EXCLUSION_MIN_KEEP_RATIO) of the region.
    """
    lightness = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)[..., 0]
    valid = ((lightness >= SHADOW_L_MIN) & (lightness <= SPECULAR_L_MAX)).astype(np.uint8)
    # Erode by 1px: the transition ring around a glare/shadow blob is a mix
    # of artifact and skin, and its steep gradient is exactly what the edge/
    # morphology metrics mistake for texture.
    valid = cv2.erode(valid, np.ones((3, 3), dtype=np.uint8))
    base = np.ones(bgr.shape[:2], dtype=bool) if roi_mask is None else roi_mask.astype(bool)
    refined = base & valid.astype(bool)
    base_count = int(base.sum())
    if base_count == 0 or int(refined.sum()) < EXCLUSION_MIN_KEEP_RATIO * base_count:
        return roi_mask
    return refined.astype(np.uint8) * 255


def _ratio_inside(fire: np.ndarray, roi_mask: np.ndarray | None) -> float:
    """Pixel ratio of `fire` restricted to `roi_mask` (or whole crop if None)."""
    if roi_mask is None:
        return float(fire.sum() / fire.size)
    inside = roi_mask.astype(bool)
    denom = int(inside.sum())
    if denom == 0:
        return 0.0
    return float((fire & inside).sum() / denom)


def _stat_inside(values: np.ndarray, roi_mask: np.ndarray | None, op: str) -> float:
    """Mean or std of `values` restricted to `roi_mask` (or whole crop if None)."""
    if roi_mask is None:
        return float(values.mean() if op == "mean" else values.std())
    inside = roi_mask.astype(bool)
    if not inside.any():
        return 0.0
    sample = values[inside]
    return float(sample.mean() if op == "mean" else sample.std())


def pigmentation_raw(bgr: np.ndarray, roi_mask: np.ndarray | None = None) -> float:
    """Pixel ratio of dark spots detected by black-hat morphology.

    Black-hat highlights small dark structures on a brighter background — exactly
    the signature of melanin spots. The metric is the fraction of pixels whose
    black-hat response exceeds a fixed cutoff, computed inside `roi_mask` when
    provided (so the score reflects only the anatomical polygon, not the
    enclosing bounding box).
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # Denoise before morphology (same 3x3 Gaussian the wrinkle metric uses):
    # the black-hat cutoff otherwise counts sensor/CLAHE noise, whose level
    # varies with the input's downscale factor — measured as a ~25% raw drift
    # between full- and half-resolution captures of the same face.
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    blackhat = cv2.morphologyEx(blurred, cv2.MORPH_BLACKHAT, kernel)
    return _ratio_inside(blackhat > 18, _effective_mask(bgr, roi_mask))


def erythema_raw(bgr: np.ndarray, roi_mask: np.ndarray | None = None) -> float:
    """Mean a* channel value in CIE Lab. Higher = redder."""
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    return _stat_inside(lab[..., 1], _effective_mask(bgr, roi_mask), op="mean")


def wrinkle_raw(bgr: np.ndarray, roi_mask: np.ndarray | None = None) -> float:
    """Fraction of pixels with strong oriented gradient response."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    gx = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = np.sqrt(gx * gx + gy * gy)
    return _ratio_inside(magnitude > 30, _effective_mask(bgr, roi_mask))


def pore_raw(bgr: np.ndarray, roi_mask: np.ndarray | None = None) -> float:
    """LoG-blob density at small scale, normalized by area."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    blurred = cv2.GaussianBlur(gray, (5, 5), sigmaX=1.4)
    log_response = cv2.Laplacian(blurred, cv2.CV_32F, ksize=3)
    return _ratio_inside(log_response > 0.045, _effective_mask(bgr, roi_mask))


def uniformity_raw(bgr: np.ndarray, roi_mask: np.ndarray | None = None) -> float:
    """Standard deviation of the L* channel. Higher = less uniform."""
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    return _stat_inside(lab[..., 0], _effective_mask(bgr, roi_mask), op="std")


def score_region(bgr: np.ndarray, roi_mask: np.ndarray | None = None) -> RegionScores:
    """Compute all five metrics + 0-10 scores for one ROI.

    If `roi_mask` is provided (same H×W as `bgr`, uint8 with 255 inside the
    anatomical polygon), every metric is computed only on the masked pixels.
    This makes the displayed score correspond exactly to the polygon drawn on
    the intake view.
    """
    raw = RawMetrics(
        pigmentation_raw=pigmentation_raw(bgr, roi_mask),
        erythema_raw=erythema_raw(bgr, roi_mask),
        wrinkle_raw=wrinkle_raw(bgr, roi_mask),
        pore_raw=pore_raw(bgr, roi_mask),
        uniformity_raw=uniformity_raw(bgr, roi_mask),
    )
    return RegionScores(
        pigmentation=_clamp_score(raw.pigmentation_raw, *PIGMENTATION_RAW_RANGE),
        erythema=_clamp_score(raw.erythema_raw, *ERYTHEMA_RAW_RANGE),
        wrinkle=_clamp_score(raw.wrinkle_raw, *WRINKLE_RAW_RANGE),
        pore=_clamp_score(raw.pore_raw, *PORE_RAW_RANGE),
        uniformity=_clamp_score(raw.uniformity_raw, *UNIFORMITY_RAW_RANGE, invert=True),
        raw=raw,
    )


def score_visit(
    rois: dict[Region, np.ndarray],
    roi_masks: dict[Region, np.ndarray] | None = None,
) -> dict[Region, RegionScores]:
    """Score every ROI present in the pipeline output.

    Args:
        rois: Mapping of Region enum to a cropped, light-normalized BGR image.
        roi_masks: Optional per-region polygon mask (same H×W as the crop). When
            provided, scoring is restricted to the polygon, not the bounding
            rectangle. When omitted, behaviour matches the original bbox-only
            scoring contract.

    Returns:
        Same mapping with RegionScores in place of images.
    """
    if roi_masks is None:
        return {region: score_region(img) for region, img in rois.items()}
    return {region: score_region(img, roi_masks.get(region)) for region, img in rois.items()}


def aggregate_face_scores(per_region: dict[Region, RegionScores]) -> dict[str, float]:
    """Average each metric across all available regions.

    Returns:
        Dict with keys pigmentation / erythema / wrinkle / pore / uniformity.
        Useful for the radar chart on the patient overview page.
    """
    if not per_region:
        return {k: 0.0 for k in ("pigmentation", "erythema", "wrinkle", "pore", "uniformity")}
    metrics = ("pigmentation", "erythema", "wrinkle", "pore", "uniformity")
    out: dict[str, float] = {}
    for m in metrics:
        values = [getattr(s, m) for s in per_region.values()]
        out[m] = round(float(np.mean(values)), 2)
    return out

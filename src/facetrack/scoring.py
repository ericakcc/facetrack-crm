"""Quantitative skin scoring engine.

The core IP. Five reproducible, deterministic CV metrics — never an LLM:

    pigmentation   black-hat morphology density (dark-spot pixel ratio)
    erythema       mean a* in CIE Lab (redness)
    wrinkle        Sobel-magnitude edge density at face-line orientations
    pore           Laplacian-of-Gaussian blob density at small scale
    uniformity     inverse-normalized L* standard deviation

Each metric maps to a 0–10 score via linear clamping against an empirical
range observed on healthy adult faces. The ranges are intentionally
documented as constants so they can be re-calibrated when a clinic
provides its own training distribution.

Score convention:
    * pigmentation / erythema / wrinkle / pore — HIGHER = more concern
    * uniformity                                — HIGHER = more uniform (better)

All functions return floats; no I/O, no LLM, no randomness.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from facetrack.db import Region

# Empirical raw-metric ranges, calibrated on a small reference set of
# pipeline-aligned + CLAHE-normalized ROI crops at ~1024px face width.
# Re-calibrate when a clinic provides its own training distribution.
PIGMENTATION_RAW_RANGE = (0.02, 0.30)
ERYTHEMA_RAW_RANGE = (134.0, 148.0)
WRINKLE_RAW_RANGE = (0.10, 0.50)
PORE_RAW_RANGE = (0.01, 0.15)
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


def pigmentation_raw(bgr: np.ndarray) -> float:
    """Pixel ratio of dark spots detected by black-hat morphology.

    Black-hat highlights small dark structures on a brighter background — exactly
    the signature of melanin spots. The metric is the fraction of pixels whose
    black-hat response exceeds a fixed cutoff.
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
    mask = blackhat > 18
    return float(mask.sum() / mask.size)


def erythema_raw(bgr: np.ndarray) -> float:
    """Mean a* channel value in CIE Lab. Higher = redder."""
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    a = lab[..., 1]
    return float(a.mean())


def wrinkle_raw(bgr: np.ndarray) -> float:
    """Fraction of pixels with strong oriented gradient response.

    Sobel magnitude after light smoothing, thresholded — a cheap, reproducible
    proxy for fine-line / wrinkle content. Range typically 0.5–6 % of pixels.
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    gx = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = np.sqrt(gx * gx + gy * gy)
    mask = magnitude > 30
    return float(mask.sum() / mask.size)


def pore_raw(bgr: np.ndarray) -> float:
    """LoG-blob density at small scale, normalized by area.

    Pores in typical clinic photos register as small isotropic dark blobs around
    2–5 px after Gaussian smoothing.
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    blurred = cv2.GaussianBlur(gray, (5, 5), sigmaX=1.4)
    log_response = cv2.Laplacian(blurred, cv2.CV_32F, ksize=3)
    mask = log_response > 0.045
    return float(mask.sum() / mask.size)


def uniformity_raw(bgr: np.ndarray) -> float:
    """Standard deviation of the L* channel. Higher = less uniform."""
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    lightness = lab[..., 0]
    return float(lightness.std())


def score_region(bgr: np.ndarray) -> RegionScores:
    """Compute all five metrics + 0-10 scores for one ROI."""
    raw = RawMetrics(
        pigmentation_raw=pigmentation_raw(bgr),
        erythema_raw=erythema_raw(bgr),
        wrinkle_raw=wrinkle_raw(bgr),
        pore_raw=pore_raw(bgr),
        uniformity_raw=uniformity_raw(bgr),
    )
    return RegionScores(
        pigmentation=_clamp_score(raw.pigmentation_raw, *PIGMENTATION_RAW_RANGE),
        erythema=_clamp_score(raw.erythema_raw, *ERYTHEMA_RAW_RANGE),
        wrinkle=_clamp_score(raw.wrinkle_raw, *WRINKLE_RAW_RANGE),
        pore=_clamp_score(raw.pore_raw, *PORE_RAW_RANGE),
        uniformity=_clamp_score(raw.uniformity_raw, *UNIFORMITY_RAW_RANGE, invert=True),
        raw=raw,
    )


def score_visit(rois: dict[Region, np.ndarray]) -> dict[Region, RegionScores]:
    """Score every ROI present in the pipeline output.

    Args:
        rois: Mapping of Region enum to a cropped, light-normalized BGR image.

    Returns:
        Same mapping with RegionScores in place of images.
    """
    return {region: score_region(img) for region, img in rois.items()}


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

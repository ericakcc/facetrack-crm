"""Overlay helpers for the intake UI — landmarks, ROI boxes, metric heatmaps.

Pure functions, no streamlit deps. Each helper accepts a BGR image (as returned
by `cv_pipeline.process`) and returns a BGR image of the same shape so they can
be composed:

    composed = draw_landmarks(aligned, landmarks)
    composed = draw_roi_boxes(composed, roi_bboxes)
    composed = overlay_heatmap(composed, response_map, face_mask)

The response maps are *the same intermediates* the scoring engine computes from;
they are exposed here without modification so the heatmap a clinician sees IS the
signal the score is derived from (TDD §3 explainability promise).
"""

from __future__ import annotations

import cv2
import numpy as np

from facetrack.db import Region

# Distinct colors per ROI (BGR). Chosen for high-contrast against skin.
ROI_COLORS_BGR: dict[Region, tuple[int, int, int]] = {
    Region.FOREHEAD: (90, 220, 90),
    Region.LEFT_CHEEK: (90, 120, 250),
    Region.RIGHT_CHEEK: (250, 140, 90),
    Region.CHIN: (220, 120, 220),
}

# Short English labels for cv2.putText (no CJK in default Hershey fonts).
ROI_LABELS_EN: dict[Region, str] = {
    Region.FOREHEAD: "Forehead",
    Region.LEFT_CHEEK: "L-Cheek",
    Region.RIGHT_CHEEK: "R-Cheek",
    Region.CHIN: "Chin",
}

# Subset of MediaPipe Face Mesh indices forming the outer face oval, used to
# build a convex-hull mask so heatmaps stay inside skin (no painting hair or
# background). Sourced from MediaPipe's FACEMESH_FACE_OVAL connection list.
FACE_OVAL_INDICES: tuple[int, ...] = (
    10,
    338,
    297,
    332,
    284,
    251,
    389,
    356,
    454,
    323,
    361,
    288,
    397,
    365,
    379,
    378,
    400,
    377,
    152,
    148,
    176,
    149,
    150,
    136,
    172,
    58,
    132,
    93,
    234,
    127,
    162,
    21,
    54,
    103,
    67,
    109,
)


# ---------------------------------------------------------------------------
# Geometric overlays
# ---------------------------------------------------------------------------


def draw_landmarks(
    image_bgr: np.ndarray,
    landmarks_px: np.ndarray,
    *,
    radius: int = 1,
    color_bgr: tuple[int, int, int] = (80, 220, 80),
    alpha: float = 0.55,
) -> np.ndarray:
    """Overlay all face-mesh landmarks as small dots.

    Args:
        image_bgr: H×W×3 BGR image.
        landmarks_px: (N, 2) array of pixel coordinates on `image_bgr`.
        radius: dot radius in pixels.
        color_bgr: dot color.
        alpha: blend factor for the overlay layer.

    Returns:
        Blended BGR image of the same shape.
    """
    if landmarks_px is None or len(landmarks_px) == 0:
        return image_bgr.copy()
    overlay = image_bgr.copy()
    for point in landmarks_px:
        center = (int(point[0]), int(point[1]))
        cv2.circle(overlay, center, radius, color_bgr, -1, lineType=cv2.LINE_AA)
    return cv2.addWeighted(overlay, alpha, image_bgr, 1.0 - alpha, 0)


def draw_roi_boxes(
    image_bgr: np.ndarray,
    roi_bboxes: dict[Region, tuple[int, int, int, int]],
    *,
    thickness: int = 2,
    font_scale: float = 0.5,
) -> np.ndarray:
    """Draw colored ROI rectangles plus a short English label per box.

    English labels avoid the missing-CJK-glyph issue in cv2.putText; the
    Streamlit page surrounds this image with the 繁中 caption row.
    """
    out = image_bgr.copy()
    for region, bbox in roi_bboxes.items():
        x, y, w, h = bbox
        color = ROI_COLORS_BGR.get(region, (255, 255, 255))
        cv2.rectangle(out, (x, y), (x + w, y + h), color, thickness, lineType=cv2.LINE_AA)
        label = ROI_LABELS_EN.get(region, region.value)
        text_y = y - 6 if y - 6 > 8 else y + h + 16
        cv2.putText(
            out,
            label,
            (x, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            color,
            1,
            lineType=cv2.LINE_AA,
        )
    return out


def face_mask_from_landmarks(
    landmarks_px: np.ndarray,
    image_shape: tuple[int, int] | tuple[int, int, int],
    *,
    feather_px: int = 9,
) -> np.ndarray:
    """Build a soft face-only mask from the face-oval landmarks.

    Convex hull of the oval landmark subset → filled polygon → Gaussian feather.
    Values are normalized to [0, 1] so callers can use it as an alpha map.

    Returns:
        H×W float32 array with values in [0, 1]; 1 = inside face.
    """
    height, width = image_shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    if landmarks_px is None or len(landmarks_px) == 0:
        return mask.astype(np.float32)

    valid_indices = [i for i in FACE_OVAL_INDICES if i < len(landmarks_px)]
    if len(valid_indices) < 3:
        return mask.astype(np.float32)

    points = landmarks_px[list(valid_indices)].astype(np.int32)
    hull = cv2.convexHull(points)
    cv2.fillConvexPoly(mask, hull, 255)

    if feather_px > 0:
        ksize = max(3, feather_px | 1)  # ensure odd
        mask = cv2.GaussianBlur(mask, (ksize, ksize), 0)
    return (mask.astype(np.float32) / 255.0).clip(0.0, 1.0)


# ---------------------------------------------------------------------------
# Per-metric response maps — same intermediates the scoring engine uses
# ---------------------------------------------------------------------------


def _response_pigmentation(bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    return cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel).astype(np.float32)


def _response_wrinkle(bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    gx = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    return np.sqrt(gx * gx + gy * gy)


def _response_pore(bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    blurred = cv2.GaussianBlur(gray, (5, 5), sigmaX=1.4)
    log_response = cv2.Laplacian(blurred, cv2.CV_32F, ksize=3)
    return np.clip(log_response, 0.0, None)


def _response_erythema(bgr: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    a_channel = lab[..., 1]
    # OpenCV encodes a* with neutral=128; subtract so positive = redder.
    return np.clip(a_channel - 128.0, 0.0, None)


def _response_uniformity(bgr: np.ndarray, window: int = 15) -> np.ndarray:
    """Local L*-channel standard deviation — high = locally non-uniform."""
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    lightness = lab[..., 0]
    mean = cv2.boxFilter(lightness, ddepth=-1, ksize=(window, window))
    mean_sq = cv2.boxFilter(lightness * lightness, ddepth=-1, ksize=(window, window))
    variance = np.clip(mean_sq - mean * mean, 0.0, None)
    return np.sqrt(variance)


_RESPONSE_FUNCS = {
    "pigmentation": _response_pigmentation,
    "wrinkle": _response_wrinkle,
    "pore": _response_pore,
    "erythema": _response_erythema,
    "uniformity": _response_uniformity,
}


def metric_response_map(image_bgr: np.ndarray, metric: str) -> np.ndarray:
    """Return the per-pixel response field for a named scoring metric.

    Raises:
        KeyError: if `metric` is not one of the five supported names.
    """
    if metric not in _RESPONSE_FUNCS:
        raise KeyError(f"Unknown metric '{metric}'. Choose from {list(_RESPONSE_FUNCS)}.")
    return _RESPONSE_FUNCS[metric](image_bgr)


# ---------------------------------------------------------------------------
# Heatmap blend
# ---------------------------------------------------------------------------


def overlay_heatmap(
    image_bgr: np.ndarray,
    response_map: np.ndarray,
    *,
    face_mask: np.ndarray | None = None,
    alpha: float = 0.75,
    colormap: int = cv2.COLORMAP_INFERNO,
    percentile_clip: tuple[float, float] = (60.0, 99.0),
) -> np.ndarray:
    """Blend a per-pixel response map onto `image_bgr` as a heatmap overlay.

    The map is robustly normalized to [0, 1] via percentile clipping so a
    handful of outlier pixels do not collapse the dynamic range. The
    *normalized magnitude itself* modulates the per-pixel alpha — weak
    response stays transparent, strong response shows through fully. This
    keeps the overlay visually faithful to *where* the metric fires, instead
    of painting the whole face in a single warm/cool gradient.

    Args:
        image_bgr: H×W×3 base image.
        response_map: H×W float; same spatial size as the image.
        face_mask: optional H×W float in [0,1] confining the overlay to skin.
        alpha: maximum blend opacity at the brightest response.
        colormap: OpenCV colormap constant. INFERNO is dark-at-bottom so the
            modulated alpha produces a clean fade-to-skin effect.
        percentile_clip: (low, high) percentiles to map onto [0, 1]. The low
            percentile is intentionally aggressive (≥50) so only the upper
            tail of the response distribution lights up.

    Returns:
        Composed BGR image, same shape as input.
    """
    if response_map.shape[:2] != image_bgr.shape[:2]:
        raise ValueError(
            f"response_map shape {response_map.shape} must match image shape {image_bgr.shape[:2]}"
        )

    if face_mask is not None:
        skin = response_map[face_mask > 0.05]
        sample = skin if skin.size > 0 else response_map
    else:
        sample = response_map

    lo_pct, hi_pct = percentile_clip
    lo = float(np.percentile(sample, lo_pct))
    hi = float(np.percentile(sample, hi_pct))
    if hi - lo < 1e-6:
        normalized = np.zeros_like(response_map, dtype=np.float32)
    else:
        normalized = np.clip((response_map - lo) / (hi - lo), 0.0, 1.0)

    heatmap_u8 = (normalized * 255).astype(np.uint8)
    colored = cv2.applyColorMap(heatmap_u8, colormap)

    # Magnitude-modulated alpha: weak signal = transparent, strong = `alpha`.
    intensity_alpha = normalized * alpha
    if face_mask is not None:
        intensity_alpha = intensity_alpha * face_mask
    alpha_map = intensity_alpha[..., None]

    base = image_bgr.astype(np.float32)
    composed = base * (1.0 - alpha_map) + colored.astype(np.float32) * alpha_map
    return np.clip(composed, 0, 255).astype(np.uint8)


def compose_intake_view(
    aligned_bgr: np.ndarray,
    landmarks_px: np.ndarray,
    roi_bboxes: dict[Region, tuple[int, int, int, int]],
    *,
    heatmap_metric: str | None = None,
    show_landmarks: bool = True,
    show_roi: bool = True,
) -> np.ndarray:
    """Convenience: build the composite intake image in the canonical order.

    1. Heatmap (so it sits under landmarks/boxes and stays readable)
    2. Landmarks (small green dots)
    3. ROI boxes + labels (on top)
    """
    out = aligned_bgr.copy()
    if heatmap_metric:
        response = metric_response_map(aligned_bgr, heatmap_metric)
        mask = face_mask_from_landmarks(landmarks_px, aligned_bgr.shape)
        out = overlay_heatmap(out, response, face_mask=mask)
    if show_landmarks:
        out = draw_landmarks(out, landmarks_px)
    if show_roi:
        out = draw_roi_boxes(out, roi_bboxes)
    return out

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

# Per-face-part colors for landmark dots (BGR). Inspired by MediaPipe's
# default drawing styles + Sander de Snaijer's face-mesh explorer.
LANDMARK_COLOR_LIPS: tuple[int, int, int] = (80, 80, 240)  # rich red
LANDMARK_COLOR_EYES: tuple[int, int, int] = (240, 200, 80)  # cyan
LANDMARK_COLOR_BROWS: tuple[int, int, int] = (60, 220, 240)  # yellow
LANDMARK_COLOR_IRIS: tuple[int, int, int] = (80, 240, 120)  # green
LANDMARK_COLOR_NOSE: tuple[int, int, int] = (80, 160, 240)  # orange
LANDMARK_COLOR_OVAL: tuple[int, int, int] = (235, 235, 235)  # off-white
LANDMARK_COLOR_OTHER: tuple[int, int, int] = (220, 180, 120)  # light blue

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

# Face-feature point sets used to *subtract* non-skin regions when building
# the heatmap mask. Sourced from MediaPipe's FACEMESH_LIPS / FACEMESH_LEFT_EYE /
# FACEMESH_RIGHT_EYE / FACEMESH_LEFT_EYEBROW / FACEMESH_RIGHT_EYEBROW connection
# frozensets in mediapipe/python/solutions/face_mesh_connections.py — deduplicated
# into point-index tuples. Each set is fed to cv2.convexHull → fillConvexPoly,
# so ordering does not matter.
LIPS_INDICES: tuple[int, ...] = (
    0,
    13,
    14,
    17,
    37,
    39,
    40,
    61,
    78,
    80,
    81,
    82,
    84,
    87,
    88,
    91,
    95,
    146,
    178,
    181,
    185,
    191,
    267,
    269,
    270,
    291,
    308,
    310,
    311,
    312,
    314,
    317,
    318,
    321,
    324,
    375,
    402,
    405,
    409,
    415,
)
LEFT_EYE_INDICES: tuple[int, ...] = (
    263,
    249,
    390,
    373,
    374,
    380,
    381,
    382,
    362,
    466,
    388,
    387,
    386,
    385,
    384,
    398,
)
RIGHT_EYE_INDICES: tuple[int, ...] = (
    33,
    7,
    163,
    144,
    145,
    153,
    154,
    155,
    133,
    246,
    161,
    160,
    159,
    158,
    157,
    173,
)
LEFT_EYEBROW_INDICES: tuple[int, ...] = (
    276,
    283,
    282,
    295,
    285,
    300,
    293,
    334,
    296,
    336,
)
RIGHT_EYEBROW_INDICES: tuple[int, ...] = (
    46,
    53,
    52,
    65,
    55,
    70,
    63,
    105,
    66,
    107,
)
# Curated nostril+columella subset only — explicitly NOT the full FACEMESH_NOSE,
# whose lateral points reach into the alar groove (where clinicians read static
# lines / erythema). Keeping the nasolabial fold as skin is load-bearing.
NOSTRIL_INDICES: tuple[int, ...] = (
    102,
    49,
    48,
    115,
    64,
    219,
    331,
    279,
    278,
    344,
    294,
    439,
)

# Iris landmarks (refined output, indices 468-477). May be absent if the
# Tasks API was configured without refined landmarks; visualization handles
# that gracefully by filtering out-of-range indices.
LEFT_IRIS_INDICES: tuple[int, ...] = (474, 475, 476, 477)
RIGHT_IRIS_INDICES: tuple[int, ...] = (469, 470, 471, 472)

# ---------------------------------------------------------------------------
# Anatomical ROI polygons — ordered point sequences (clockwise on the image
# plane) so cv2.fillPoly / cv2.polylines render them correctly.
# ---------------------------------------------------------------------------
#
# These define the actual measurement region for each Region. The polygon
# both (a) drives the boundary drawn in the intake view and (b) masks the
# scoring metrics so the number a clinician sees corresponds to exactly the
# painted area. Indices chosen to hug anatomical landmarks instead of
# axis-aligned rectangles.

FOREHEAD_POLYGON: tuple[int, ...] = (
    # Upper boundary along face oval, left temple → right temple
    21,
    54,
    103,
    67,
    109,
    10,
    338,
    297,
    332,
    284,
    251,
    # Drop to upper edge of left brow (image right), then traverse to
    # glabella, then upper edge of right brow (image left), back to start.
    285,
    295,
    282,
    9,
    55,
    65,
    52,
)

LEFT_CHEEK_POLYGON: tuple[int, ...] = (
    # Subject's left cheek = image right side. Ordered clockwise on the image.
    # Top edge (under-eye lid), inner (near nose) → outer (toward temple):
    453,
    452,
    451,
    450,
    449,
    448,
    261,
    340,
    # Outer-lateral face oval going down to mouth-level (stop before jaw):
    323,
    361,
    288,
    # Inner-lower (mouth corner):
    291,
    # Nasolabial fold going back up to start:
    436,
    426,
    327,
    358,
)

RIGHT_CHEEK_POLYGON: tuple[int, ...] = (
    # Subject's right cheek = image left side. Ordered clockwise on the image.
    # Top edge (under-eye lid), inner (near nose) → outer (toward temple):
    233,
    232,
    231,
    230,
    229,
    228,
    31,
    111,
    # Outer-lateral face oval going down to mouth-level (stop before jaw):
    93,
    132,
    58,
    # Inner-lower (mouth corner):
    61,
    # Nasolabial fold going back up to start:
    216,
    206,
    98,
    129,
)

CHIN_POLYGON: tuple[int, ...] = (
    # Ordered clockwise on the image, starting from the left mouth corner.
    # Top: outer lower lip line (left → right):
    61,
    146,
    91,
    181,
    84,
    17,
    314,
    405,
    321,
    375,
    291,
    # Right jaw going down to chin tip:
    365,
    379,
    378,
    400,
    377,
    # Chin tip:
    152,
    # Left jaw going back up to start:
    148,
    176,
    149,
    150,
    136,
)


# ---------------------------------------------------------------------------
# Geometric overlays
# ---------------------------------------------------------------------------


def _landmark_color_map() -> dict[int, tuple[int, int, int]]:
    """Build per-landmark-index color lookup, one color per anatomical group.

    Lookup order matters: an index that belongs to multiple groups (e.g. the
    eye-iris boundary) takes the most specific group's color.
    """
    color_map: dict[int, tuple[int, int, int]] = {}
    # Generic / face-oval points painted first (lowest priority).
    for i in FACE_OVAL_INDICES:
        color_map[i] = LANDMARK_COLOR_OVAL
    for i in (*LEFT_EYEBROW_INDICES, *RIGHT_EYEBROW_INDICES):
        color_map[i] = LANDMARK_COLOR_BROWS
    for i in (*LEFT_EYE_INDICES, *RIGHT_EYE_INDICES):
        color_map[i] = LANDMARK_COLOR_EYES
    for i in NOSTRIL_INDICES:
        color_map[i] = LANDMARK_COLOR_NOSE
    for i in LIPS_INDICES:
        color_map[i] = LANDMARK_COLOR_LIPS
    for i in (*LEFT_IRIS_INDICES, *RIGHT_IRIS_INDICES):
        color_map[i] = LANDMARK_COLOR_IRIS
    return color_map


_LANDMARK_COLOR_MAP = _landmark_color_map()


def draw_landmarks(
    image_bgr: np.ndarray,
    landmarks_px: np.ndarray,
    *,
    radius: int = 2,
    alpha: float = 0.75,
    color_groups: bool = True,
) -> np.ndarray:
    """Overlay face-mesh landmarks as colored dots — one color per face part.

    Args:
        image_bgr: H×W×3 BGR image.
        landmarks_px: (N, 2) array of pixel coordinates on `image_bgr`.
        radius: dot radius in pixels (2 = clearly visible, won't drown a 1024² face).
        alpha: blend factor for the overlay layer.
        color_groups: if True, colour each landmark by its anatomical group
            (lips/eyes/brows/iris/nose/oval/other). If False, falls back to a
            single light-blue colour. The grouped version mirrors MediaPipe's
            default drawing style + Sander de Snaijer's face-mesh explorer.

    Returns:
        Blended BGR image of the same shape.
    """
    if landmarks_px is None or len(landmarks_px) == 0:
        return image_bgr.copy()
    overlay = image_bgr.copy()
    for idx, point in enumerate(landmarks_px):
        center = (int(point[0]), int(point[1]))
        color = (
            _LANDMARK_COLOR_MAP.get(idx, LANDMARK_COLOR_OTHER)
            if color_groups
            else LANDMARK_COLOR_OTHER
        )
        cv2.circle(overlay, center, radius, color, -1, lineType=cv2.LINE_AA)
    return cv2.addWeighted(overlay, alpha, image_bgr, 1.0 - alpha, 0)


def draw_roi_polygons(
    image_bgr: np.ndarray,
    roi_polygons: dict[Region, np.ndarray],
    *,
    fill_alpha: float = 0.18,
    outline_thickness: int = 2,
    font_scale: float = 0.55,
) -> np.ndarray:
    """Draw anatomically-shaped ROI polygons with translucent fill + bold outline.

    Args:
        image_bgr: H×W×3 BGR image.
        roi_polygons: mapping of Region → (N, 2) ordered polygon points in
            image pixel coordinates. Same dict returned by
            `cv_pipeline.CVPipelineResult.roi_polygons`.
        fill_alpha: blend factor for the translucent interior. Low enough not
            to swamp the underlying heatmap.
        outline_thickness: outline stroke width in pixels.

    Returns:
        Composed BGR image of the same shape.
    """
    if not roi_polygons:
        return image_bgr.copy()

    fill_layer = image_bgr.copy()
    for region, polygon in roi_polygons.items():
        if polygon is None or len(polygon) < 3:
            continue
        pts = polygon.astype(np.int32).reshape(-1, 1, 2)
        color = ROI_COLORS_BGR.get(region, (255, 255, 255))
        cv2.fillPoly(fill_layer, [pts], color)

    out = cv2.addWeighted(fill_layer, fill_alpha, image_bgr, 1.0 - fill_alpha, 0)

    for region, polygon in roi_polygons.items():
        if polygon is None or len(polygon) < 3:
            continue
        pts = polygon.astype(np.int32).reshape(-1, 1, 2)
        color = ROI_COLORS_BGR.get(region, (255, 255, 255))
        cv2.polylines(
            out,
            [pts],
            isClosed=True,
            color=color,
            thickness=outline_thickness,
            lineType=cv2.LINE_AA,
        )

        # Label at polygon centroid
        centroid = polygon.mean(axis=0)
        text = ROI_LABELS_EN.get(region, region.value)
        cv2.putText(
            out,
            text,
            (int(centroid[0] - len(text) * 4), int(centroid[1])),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            color,
            1,
            lineType=cv2.LINE_AA,
        )
    return out


def draw_tessellation(
    image_bgr: np.ndarray,
    landmarks_px: np.ndarray,
    *,
    color_bgr: tuple[int, int, int] = (140, 140, 140),
    thickness: int = 1,
    alpha: float = 0.35,
    connections: tuple[tuple[int, int], ...] | None = None,
) -> np.ndarray:
    """Draw the face-mesh wireframe: thin gray lines for every triangle edge.

    For panel-style "neon mesh" demos. Default `connections=None` uses the
    feature contour edges (cheaper than the full FACEMESH_TESSELATION with
    ~2700 edges); pass a custom edge list for the full triangulation if the
    mediapipe drawing module is available.
    """
    if landmarks_px is None or len(landmarks_px) == 0:
        return image_bgr.copy()

    if connections is None:
        # Compose connections from each feature ring: consecutive pairs +
        # closure. Cheap (~ a few hundred segments) and visually informative
        # without dominating the heatmap.
        rings = (
            FACE_OVAL_INDICES,
            LIPS_INDICES,
            LEFT_EYE_INDICES,
            RIGHT_EYE_INDICES,
            LEFT_EYEBROW_INDICES,
            RIGHT_EYEBROW_INDICES,
            NOSTRIL_INDICES,
        )
        edges: list[tuple[int, int]] = []
        for ring in rings:
            valid = [i for i in ring if i < len(landmarks_px)]
            edges.extend(zip(valid, valid[1:] + valid[:1], strict=False))
        connections = tuple(edges)

    overlay = image_bgr.copy()
    n = len(landmarks_px)
    for a, b in connections:
        if a >= n or b >= n:
            continue
        p1 = (int(landmarks_px[a, 0]), int(landmarks_px[a, 1]))
        p2 = (int(landmarks_px[b, 0]), int(landmarks_px[b, 1]))
        cv2.line(overlay, p1, p2, color_bgr, thickness, lineType=cv2.LINE_AA)
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


def _fill_hull(mask: np.ndarray, points: np.ndarray) -> None:
    """Fill the convex hull of `points` into `mask` (in place, value 255)."""
    if len(points) < 3:
        return
    hull = cv2.convexHull(points.astype(np.int32))
    cv2.fillConvexPoly(mask, hull, 255)


def polygon_points(landmarks_px: np.ndarray, indices: tuple[int, ...]) -> np.ndarray:
    """Pick an ordered point sequence from landmarks by index.

    Out-of-range indices (e.g. iris when refined landmarks are off) are
    silently dropped — callers can detect "polygon collapsed" via `len(...) < 3`.
    """
    n = len(landmarks_px)
    valid = [i for i in indices if i < n]
    if not valid:
        return np.zeros((0, 2), dtype=np.float32)
    return landmarks_px[valid].astype(np.float32)


def polygon_mask(
    polygon_xy: np.ndarray,
    image_shape: tuple[int, int] | tuple[int, int, int],
    *,
    bbox: tuple[int, int, int, int] | None = None,
) -> np.ndarray:
    """Rasterise an ordered polygon into a uint8 mask of value 255 inside.

    Args:
        polygon_xy: (N, 2) float/int points in image coordinates.
        image_shape: shape of the target mask; we use shape[:2].
        bbox: if given (x, y, w, h), the mask is sized (h, w) and the
            polygon is translated into bbox-local coords. Useful when the
            caller already cropped the image to the polygon's bounding box.

    Returns:
        H×W uint8 mask (0 or 255). H×W = image_shape[:2] when bbox is None,
        or (h, w) from bbox when given.
    """
    if bbox is None:
        h, w = image_shape[:2]
        offset = np.zeros(2, dtype=np.float32)
    else:
        x, y, w, h = bbox
        offset = np.array([x, y], dtype=np.float32)
    mask = np.zeros((h, w), dtype=np.uint8)
    if len(polygon_xy) < 3:
        return mask
    pts = (polygon_xy - offset).astype(np.int32).reshape(-1, 1, 2)
    cv2.fillPoly(mask, [pts], 255)
    return mask


def skin_mask_from_landmarks(
    landmarks_px: np.ndarray,
    image_shape: tuple[int, int] | tuple[int, int, int],
    *,
    feather_px: int = 9,
    feature_buffer_px: int = 6,
    eyebrow_upward_buffer_px: int = 15,
) -> np.ndarray:
    """Skin-only soft mask: face oval minus eyes / eyebrows / lips / nostrils.

    Matches the regions the scoring engine actually measures
    (`scoring.py:score_region` only runs inside 4 anatomical ROIs that exclude
    these features by construction). Eyebrows get an additional upward
    expansion before convex-hulling because MediaPipe brow landmarks sit along
    or below the brow hair, not above it — see MediaPipe issue #963.

    The nasolabial fold is deliberately preserved as skin: only nostril rims +
    columella are subtracted from the nose region, never the full alar/dorsum
    set, since clinicians read static lines and erythema there.

    Returns:
        H×W float32 in [0, 1]; 1 = skin, 0 = excluded (feature or outside oval).
    """
    height, width = image_shape[:2]
    empty = np.zeros((height, width), dtype=np.float32)
    if landmarks_px is None or len(landmarks_px) == 0:
        return empty

    n = len(landmarks_px)
    valid_oval = [i for i in FACE_OVAL_INDICES if i < n]
    if len(valid_oval) < 3:
        return empty

    base = np.zeros((height, width), dtype=np.uint8)
    _fill_hull(base, landmarks_px[valid_oval])

    holes = np.zeros((height, width), dtype=np.uint8)

    def hull_indices(idx_tuple: tuple[int, ...]) -> np.ndarray:
        valid = [i for i in idx_tuple if i < n]
        return landmarks_px[valid] if valid else np.zeros((0, 2), dtype=np.float32)

    for indices in (LIPS_INDICES, LEFT_EYE_INDICES, RIGHT_EYE_INDICES, NOSTRIL_INDICES):
        _fill_hull(holes, hull_indices(indices))

    # Eyebrows: append copies shifted upward so the hull extends above the
    # brow hair (MediaPipe brow points hug the lower edge of the brow).
    for brow_indices in (LEFT_EYEBROW_INDICES, RIGHT_EYEBROW_INDICES):
        pts = hull_indices(brow_indices)
        if len(pts) == 0:
            continue
        shifted = pts.copy()
        shifted[:, 1] -= eyebrow_upward_buffer_px
        _fill_hull(holes, np.vstack([pts, shifted]))

    if feature_buffer_px > 0:
        ksize = max(3, feature_buffer_px | 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
        holes = cv2.dilate(holes, kernel, iterations=1)

    skin = cv2.subtract(base, holes)

    if feather_px > 0:
        ksize = max(3, feather_px | 1)
        skin = cv2.GaussianBlur(skin, (ksize, ksize), 0)
    return (skin.astype(np.float32) / 255.0).clip(0.0, 1.0)


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
    roi_polygons: dict[Region, np.ndarray] | None = None,
    *,
    roi_bboxes: dict[Region, tuple[int, int, int, int]] | None = None,
    heatmap_metric: str | None = None,
    show_landmarks: bool = True,
    show_roi: bool = True,
    show_tessellation: bool = False,
) -> np.ndarray:
    """Build the composite intake image in the canonical layered order.

    Layer order (bottom to top):
        1. Heatmap (response map of the chosen metric, masked to skin)
        2. Tessellation wireframe (optional)
        3. ROI polygons (translucent fill + outline)
        4. Landmarks (colored dots per face-part group)

    Args:
        aligned_bgr: aligned face image.
        landmarks_px: (N, 2) landmark coordinates in `aligned_bgr` pixel space.
        roi_polygons: anatomical ROI polygons (preferred). If omitted, falls back
            to drawing axis-aligned `roi_bboxes` rectangles for backwards-compat.
        roi_bboxes: legacy axis-aligned rectangles. Only used when `roi_polygons`
            is None.
        heatmap_metric: one of pigmentation/wrinkle/pore/erythema/uniformity,
            or None to skip the heatmap.
        show_landmarks: paint the 478 colored landmark dots.
        show_roi: paint the ROI polygons / boxes.
        show_tessellation: paint the face-mesh wireframe (thin gray edges).
    """
    out = aligned_bgr.copy()
    if heatmap_metric:
        response = metric_response_map(aligned_bgr, heatmap_metric)
        mask = skin_mask_from_landmarks(landmarks_px, aligned_bgr.shape)
        out = overlay_heatmap(out, response, face_mask=mask)
    if show_tessellation:
        out = draw_tessellation(out, landmarks_px)
    if show_roi:
        if roi_polygons:
            out = draw_roi_polygons(out, roi_polygons)
        elif roi_bboxes:
            out = draw_roi_boxes(out, roi_bboxes)
    if show_landmarks:
        out = draw_landmarks(out, landmarks_px)
    return out

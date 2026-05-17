"""Smoke tests for the overlay/heatmap helpers.

Verifies shapes, dtypes, masking behaviour, and that the metric response maps
match what the scoring engine would internally compute. No GUI assertions.
"""

from __future__ import annotations

import numpy as np
import pytest

from facetrack.db import Region
from facetrack.visualization import (
    _RESPONSE_FUNCS,
    compose_intake_view,
    draw_landmarks,
    draw_roi_boxes,
    face_mask_from_landmarks,
    metric_response_map,
    overlay_heatmap,
)


def _fake_image(h: int = 256, w: int = 256) -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8)


def _fake_landmarks(image_shape: tuple[int, int], n: int = 478) -> np.ndarray:
    h, w = image_shape
    rng = np.random.default_rng(1)
    cx, cy = w / 2.0, h / 2.0
    radius = min(h, w) * 0.35
    theta = rng.uniform(0, 2 * np.pi, size=n)
    r = rng.uniform(0.6 * radius, radius, size=n)
    xs = cx + r * np.cos(theta)
    ys = cy + r * np.sin(theta)
    return np.column_stack([xs, ys]).astype(np.float32)


def _fake_bboxes(image_shape: tuple[int, int]) -> dict[Region, tuple[int, int, int, int]]:
    h, w = image_shape
    return {
        Region.FOREHEAD: (w // 4, h // 8, w // 2, h // 8),
        Region.LEFT_CHEEK: (w // 6, h // 2, w // 5, h // 5),
        Region.RIGHT_CHEEK: (w * 3 // 5, h // 2, w // 5, h // 5),
        Region.CHIN: (w * 2 // 5, h * 3 // 4, w // 5, h // 8),
    }


def test_draw_landmarks_preserves_shape_dtype() -> None:
    image = _fake_image()
    landmarks = _fake_landmarks(image.shape[:2])
    out = draw_landmarks(image, landmarks)
    assert out.shape == image.shape
    assert out.dtype == np.uint8
    # Should be different from the input (at least one pixel painted).
    assert not np.array_equal(out, image)


def test_draw_landmarks_empty_safe() -> None:
    image = _fake_image()
    out = draw_landmarks(image, np.zeros((0, 2), dtype=np.float32))
    assert out.shape == image.shape
    assert np.array_equal(out, image)


def test_draw_roi_boxes_preserves_shape() -> None:
    image = _fake_image()
    boxes = _fake_bboxes(image.shape[:2])
    out = draw_roi_boxes(image, boxes)
    assert out.shape == image.shape
    assert out.dtype == np.uint8


def test_face_mask_is_normalized_alpha() -> None:
    image = _fake_image()
    landmarks = _fake_landmarks(image.shape[:2])
    mask = face_mask_from_landmarks(landmarks, image.shape)
    assert mask.shape == image.shape[:2]
    assert mask.dtype == np.float32
    assert mask.min() >= 0.0 and mask.max() <= 1.0
    # Center of image should be inside the convex hull → > 0.
    cy, cx = mask.shape[0] // 2, mask.shape[1] // 2
    assert mask[cy, cx] > 0.5


@pytest.mark.parametrize("metric", list(_RESPONSE_FUNCS.keys()))
def test_metric_response_map_shape_dtype(metric: str) -> None:
    image = _fake_image()
    response = metric_response_map(image, metric)
    assert response.shape == image.shape[:2]
    assert response.dtype == np.float32
    assert np.isfinite(response).all()


def test_metric_response_map_unknown_metric_raises() -> None:
    image = _fake_image()
    with pytest.raises(KeyError):
        metric_response_map(image, "not_a_real_metric")


def test_overlay_heatmap_respects_face_mask() -> None:
    """Pixels at alpha=0 must be left untouched by the heatmap blend."""
    image = _fake_image()
    # Non-uniform response so percentile clip produces a real gradient.
    yy, xx = np.mgrid[0 : image.shape[0], 0 : image.shape[1]].astype(np.float32)
    response = yy + xx  # ramps across the image; varied enough for percentiles
    mask = np.zeros(image.shape[:2], dtype=np.float32)
    mask[64:192, 64:192] = 1.0  # only center is in-face

    composed = overlay_heatmap(image, response, face_mask=mask)
    # Outside the mask = identical to original.
    assert np.array_equal(composed[0:32, 0:32], image[0:32, 0:32])
    # Inside the mask, on the strong-response side = different from original.
    assert not np.array_equal(composed[160:190, 160:190], image[160:190, 160:190])


def test_compose_intake_view_runs_with_heatmap() -> None:
    image = _fake_image()
    landmarks = _fake_landmarks(image.shape[:2])
    boxes = _fake_bboxes(image.shape[:2])
    out = compose_intake_view(image, landmarks, boxes, heatmap_metric="pigmentation")
    assert out.shape == image.shape
    assert out.dtype == np.uint8


def test_compose_intake_view_no_heatmap_no_overlays() -> None:
    image = _fake_image()
    landmarks = _fake_landmarks(image.shape[:2])
    boxes = _fake_bboxes(image.shape[:2])
    out = compose_intake_view(
        image,
        landmarks,
        boxes,
        heatmap_metric=None,
        show_landmarks=False,
        show_roi=False,
    )
    assert np.array_equal(out, image)

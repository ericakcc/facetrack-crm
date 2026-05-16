"""Determinism contract for the scoring engine.

These tests encode the central product claim:

    "Running the same input twice produces the same numbers."

If any of these tests start failing, the product's reproducibility
guarantee is broken — and the longitudinal chart is no longer
trustworthy. This is the test we point AI Fund's panel at when they
ask "how is your scoring different from a vision-LLM wrapper?".
"""

from __future__ import annotations

import numpy as np

from facetrack.db import Region
from facetrack.scoring import (
    aggregate_face_scores,
    erythema_raw,
    pigmentation_raw,
    pore_raw,
    score_region,
    score_visit,
    uniformity_raw,
    wrinkle_raw,
)


def _synthetic_skin_patch(seed: int = 0, size: int = 256) -> np.ndarray:
    """A reproducible synthetic skin-like BGR patch.

    Uses a fixed numpy RNG so the test inputs themselves are
    deterministic — otherwise we'd only be testing that scoring is
    pure with respect to its input, not that the whole pipeline
    is reproducible end-to-end.
    """
    rng = np.random.default_rng(seed)
    base = rng.integers(140, 200, size=(size, size, 3), dtype=np.uint8)
    # Add a few darker "spots" so pigmentation has signal to find.
    for _ in range(6):
        cy, cx = rng.integers(20, size - 20, size=2)
        r = int(rng.integers(4, 10))
        base[cy - r : cy + r, cx - r : cx + r] = rng.integers(60, 110)
    return base


def test_raw_metrics_are_bit_identical_across_calls() -> None:
    """Every raw scalar must be float-equal across two invocations on the same input."""
    img = _synthetic_skin_patch(seed=1)
    pairs = [
        (pigmentation_raw, "pigmentation"),
        (erythema_raw, "erythema"),
        (wrinkle_raw, "wrinkle"),
        (pore_raw, "pore"),
        (uniformity_raw, "uniformity"),
    ]
    for fn, name in pairs:
        first = fn(img)
        second = fn(img)
        assert first == second, f"{name}_raw not bit-identical: {first!r} != {second!r}"


def test_score_region_bit_identical_across_calls() -> None:
    """score_region must produce numerically identical RegionScores on repeat."""
    img = _synthetic_skin_patch(seed=2)
    a = score_region(img)
    b = score_region(img)
    for metric in ("pigmentation", "erythema", "wrinkle", "pore", "uniformity"):
        assert getattr(a, metric) == getattr(b, metric), f"{metric} drifted: {a} vs {b}"
    for metric in (
        "pigmentation_raw",
        "erythema_raw",
        "wrinkle_raw",
        "pore_raw",
        "uniformity_raw",
    ):
        assert getattr(a.raw, metric) == getattr(b.raw, metric)


def test_score_region_is_pure_no_input_mutation() -> None:
    """Scoring must not mutate its input array. Otherwise repeated calls drift."""
    img = _synthetic_skin_patch(seed=3)
    snapshot = img.copy()
    _ = score_region(img)
    assert np.array_equal(img, snapshot), "score_region mutated the input image"


def test_score_visit_is_deterministic_across_regions() -> None:
    """The dict-of-regions wrapper must also be deterministic."""
    rois = {
        Region.LEFT_CHEEK: _synthetic_skin_patch(seed=10),
        Region.RIGHT_CHEEK: _synthetic_skin_patch(seed=11),
        Region.FOREHEAD: _synthetic_skin_patch(seed=12),
        Region.CHIN: _synthetic_skin_patch(seed=13),
    }
    first = score_visit(rois)
    second = score_visit(rois)
    assert set(first.keys()) == set(second.keys())
    for region in first:
        for metric in ("pigmentation", "erythema", "wrinkle", "pore", "uniformity"):
            assert getattr(first[region], metric) == getattr(second[region], metric)


def test_aggregate_face_scores_deterministic() -> None:
    """The per-face aggregate must round-trip identically."""
    rois = {
        Region.LEFT_CHEEK: _synthetic_skin_patch(seed=20),
        Region.RIGHT_CHEEK: _synthetic_skin_patch(seed=21),
        Region.FOREHEAD: _synthetic_skin_patch(seed=22),
        Region.CHIN: _synthetic_skin_patch(seed=23),
    }
    a = aggregate_face_scores(score_visit(rois))
    b = aggregate_face_scores(score_visit(rois))
    assert a == b


def test_scores_are_within_zero_to_ten_range() -> None:
    """Sanity boundary: every 0-10 score must in fact lie in [0, 10]."""
    img = _synthetic_skin_patch(seed=4)
    out = score_region(img)
    for metric in ("pigmentation", "erythema", "wrinkle", "pore", "uniformity"):
        value = getattr(out, metric)
        assert 0.0 <= value <= 10.0, f"{metric}={value} outside [0,10]"


def test_aggregate_empty_input_returns_zero_dict() -> None:
    """No regions → safe zero baseline, not a crash."""
    out = aggregate_face_scores({})
    assert out == {
        "pigmentation": 0.0,
        "erythema": 0.0,
        "wrinkle": 0.0,
        "pore": 0.0,
        "uniformity": 0.0,
    }

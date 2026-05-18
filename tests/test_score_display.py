"""Behavioural contract for `facetrack.score_display` UI transforms."""

from __future__ import annotations

import pytest

from facetrack.score_display import (
    COLOR_AVERAGE,
    COLOR_GOOD,
    COLOR_POOR,
    CONCERN_METRICS,
    health_band,
    to_health_score,
)


@pytest.mark.parametrize(
    ("metric", "raw", "expected"),
    [
        ("pigmentation", 2.0, 8.0),
        ("pigmentation", 7.5, 2.5),
        ("erythema", 0.0, 10.0),
        ("wrinkle", 10.0, 0.0),
        ("pore", 5.0, 5.0),
    ],
)
def test_to_health_score_flips_concern_metrics(metric: str, raw: float, expected: float) -> None:
    assert to_health_score(metric, raw) == expected


def test_to_health_score_passes_uniformity_through() -> None:
    # Uniformity raw is already higher = better; must not be flipped.
    assert to_health_score("uniformity", 8.5) == 8.5
    assert to_health_score("uniformity", 0.0) == 0.0
    assert to_health_score("uniformity", 10.0) == 10.0


@pytest.mark.parametrize(
    ("health", "expected_emoji", "expected_color"),
    [
        (9.0, "🟢", COLOR_GOOD),
        (7.0, "🟢", COLOR_GOOD),  # boundary: exactly good_lower → 🟢
        (6.99, "🟡", COLOR_AVERAGE),
        (5.0, "🟡", COLOR_AVERAGE),
        (4.0, "🟡", COLOR_AVERAGE),  # boundary: exactly poor_upper → 🟡
        (3.99, "🔴", COLOR_POOR),
        (2.0, "🔴", COLOR_POOR),
        (0.0, "🔴", COLOR_POOR),
    ],
)
def test_health_band_thresholds(health: float, expected_emoji: str, expected_color: str) -> None:
    emoji, _label, color = health_band(health)
    assert emoji == expected_emoji
    assert color == expected_color


def test_to_health_score_clamps_to_valid_range() -> None:
    # Edge values for concern metrics
    assert to_health_score("pigmentation", 0.0) == 10.0
    assert to_health_score("pigmentation", 10.0) == 0.0


def test_concern_metrics_set_matches_scoring_convention() -> None:
    """Guard against silently misclassifying a future metric.

    If a new metric is added to `facetrack.scoring`, the developer must
    explicitly decide whether it's a concern metric (high = worse) or a
    quality metric (high = better).
    """
    assert frozenset({"pigmentation", "erythema", "wrinkle", "pore"}) == CONCERN_METRICS

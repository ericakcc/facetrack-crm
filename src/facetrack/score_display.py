"""UI-layer score transformation: raw 0-10 metrics → unified higher-is-better health scores.

The scoring engine (`facetrack.scoring`) keeps direction-specific conventions
where pigmentation / erythema / wrinkle / pore ascend with severity and only
uniformity ascends with quality. That asymmetry confuses clinic users, so this
module flips the four concern metrics at display time so all five metrics share
a single mental model: 高分 = 膚況好.

Pure functions only — no DB, no Streamlit, easy to unit-test.
"""

from __future__ import annotations

HEALTH_BAND_THRESHOLDS: tuple[float, float] = (4.0, 7.0)
"""(poor_upper, good_lower): score < 4 = 🔴, 4–7 = 🟡, ≥ 7 = 🟢."""

CONCERN_METRICS: frozenset[str] = frozenset({"pigmentation", "erythema", "wrinkle", "pore"})
"""The four raw metrics where HIGHER = worse. Flipped at display time."""

COLOR_GOOD: str = "#10b981"
COLOR_AVERAGE: str = "#f59e0b"
COLOR_POOR: str = "#ef4444"
COLOR_NEUTRAL: str = "#9ca3af"


def to_health_score(metric_key: str, raw_score: float) -> float:
    """Convert a raw 0-10 metric to a unified higher=better health score.

    Args:
        metric_key: One of pigmentation / erythema / wrinkle / pore / uniformity.
        raw_score: Raw 0-10 score from `facetrack.scoring`.

    Returns:
        A 0-10 score where higher always means healthier skin.
    """
    if metric_key in CONCERN_METRICS:
        return round(10.0 - raw_score, 2)
    return round(raw_score, 2)


def health_band(health_score: float) -> tuple[str, str, str]:
    """Map a unified health score to a (emoji, zh_label, hex_color) tuple.

    Args:
        health_score: A 0-10 health score (output of `to_health_score`).

    Returns:
        Tuple of UI elements suitable for badges and progress bars.
    """
    poor_upper, good_lower = HEALTH_BAND_THRESHOLDS
    if health_score >= good_lower:
        return ("🟢", "良好", COLOR_GOOD)
    if health_score >= poor_upper:
        return ("🟡", "注意", COLOR_AVERAGE)
    return ("🔴", "需改善", COLOR_POOR)

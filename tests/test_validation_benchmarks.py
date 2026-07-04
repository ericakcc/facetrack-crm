"""Ground-truth benchmark tests — opt-in via `uv run pytest -m validation`.

Turns the offline validators under scripts/validation/ into a regression
net: if a CV/scoring change breaks ground-truth alignment, these fail.
Thresholds are the Session-5 measured values minus a safety margin
(FFHQ ROI Spearman rho measured 0.42; real-face wrinkle_raw p5-p95
measured [0.197, 0.619]).

The datasets hold real-person pixels and are therefore gitignored; each
fixture skips with re-download instructions (data/validation/README.md)
when its dataset is absent. Module-scoped fixtures mean each dataset is
processed once per run — the FFHQ fixture takes ~10-20 minutes.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts" / "validation"))

import validate_wrinkle_ffhq  # noqa: E402

from facetrack.scoring import WRINKLE_RAW_RANGE  # noqa: E402

DATA = REPO / "data" / "validation"
RANGE_ENDPOINT_TOL = 0.05

pytestmark = pytest.mark.validation


@pytest.fixture(scope="module")
def ffhq_result() -> dict[str, Any]:
    """Full FFHQ-Wrinkle validation summary (skips when data is absent)."""
    masks = DATA / "ffhq_wrinkle" / "manual_wrinkle_masks"
    if not any(masks.glob("*.png")):
        pytest.skip("FFHQ-Wrinkle not downloaded — see data/validation/README.md")
    return validate_wrinkle_ffhq.run_validation()


def test_wrinkle_roi_ranking_tracks_human_annotations(ffhq_result: dict[str, Any]) -> None:
    """ROI-restricted wrinkle_raw must rank faces like the hand-drawn masks do."""
    assert ffhq_result["n"] >= 800, "partial FFHQ download — refetch before trusting stats"
    assert ffhq_result["roi_spearman"] >= 0.35, (
        f"ROI Spearman rho {ffhq_result['roi_spearman']:.3f} < 0.35 — "
        "wrinkle ranking no longer tracks ground truth (Session-5 baseline: 0.42)"
    )


def test_wrinkle_range_matches_real_face_distribution(ffhq_result: dict[str, Any]) -> None:
    """WRINKLE_RAW_RANGE endpoints must sit on the real-face p5/p95.

    A too-wide range silently kills the top/bottom of the 0-10 scale
    (scores clamp-saturate); this pins the config to the measured
    distribution within +/-0.05.
    """
    lo, hi = WRINKLE_RAW_RANGE
    assert abs(lo - ffhq_result["raw_p5"]) <= RANGE_ENDPOINT_TOL, (
        f"range low {lo} vs measured p5 {ffhq_result['raw_p5']:.3f}"
    )
    assert abs(hi - ffhq_result["raw_p95"]) <= RANGE_ENDPOINT_TOL, (
        f"range high {hi} vs measured p95 {ffhq_result['raw_p95']:.3f}"
    )

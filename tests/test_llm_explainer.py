"""Unit tests for the LLM explainer module."""

from __future__ import annotations

from facetrack.llm_explainer import MockExplainer, _format_delta, _identify_top_issues


def test_mock_explainer_returns_zh_explanation_and_suggestion() -> None:
    ex = MockExplainer()
    scores_now = {
        "pigmentation": 7.5,
        "erythema": 3.2,
        "wrinkle": 4.5,
        "pore": 5.0,
        "uniformity": 5.2,
    }
    scores_prev = {
        "pigmentation": 8.5,
        "erythema": 3.0,
        "wrinkle": 4.0,
        "pore": 5.0,
        "uniformity": 4.5,
    }
    out = ex.explain(scores_now, scores_prev, "林雅婷")

    assert out.backend == "mock"
    assert "林雅婷" in out.explanation_zh
    assert "色素沉澱" in out.explanation_zh  # top issue
    assert len(out.suggestion_zh) > 0


def test_mock_explainer_handles_no_history() -> None:
    ex = MockExplainer()
    scores = {
        "pigmentation": 5.0,
        "erythema": 5.0,
        "wrinkle": 5.0,
        "pore": 5.0,
        "uniformity": 5.0,
    }
    out = ex.explain(scores, None, "陳怡君")
    assert "首次評估" in out.explanation_zh


def test_identify_top_issues_uniformity_inverted() -> None:
    scores = {
        "pigmentation": 2.0,
        "erythema": 2.0,
        "wrinkle": 2.0,
        "pore": 2.0,
        "uniformity": 1.0,  # very poor uniformity should win
    }
    top = _identify_top_issues(scores, top_n=1)
    assert top[0][0] == "uniformity"


def test_format_delta_describes_change_direction() -> None:
    now = {"pigmentation": 5.0, "uniformity": 6.0}
    prev = {"pigmentation": 7.0, "uniformity": 4.0}
    msg = _format_delta(now, prev)
    assert "下降" in msg  # pigmentation went down
    assert "提升" in msg  # uniformity went up (good)

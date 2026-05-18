"""Unit tests for the LLM explainer module."""

from __future__ import annotations

from facetrack.llm_explainer import (
    MockExplainer,
    _coerce_to_string,
    _format_delta,
    _identify_top_issues,
    _to_health_dict,
)


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
    # pigmentation raw=7.5 → health=2.5 (lowest, worst). Should be top issue.
    assert "色素沉澱" in out.explanation_zh
    assert len(out.suggestion_zh) > 0
    # Explanation must speak in 'health' direction language, never raw '上升/下降'
    assert (
        "改善" in out.explanation_zh or "退步" in out.explanation_zh or "持平" in out.explanation_zh
    )


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


def test_identify_top_issues_lowest_health_wins() -> None:
    # Operates in HEALTH-SCORE space: lowest health = worst skin = top issue.
    health = {
        "pigmentation": 8.0,
        "erythema": 8.0,
        "wrinkle": 8.0,
        "pore": 8.0,
        "uniformity": 1.0,  # health 1.0 = very uneven skin, should rank first
    }
    top = _identify_top_issues(health, top_n=1)
    assert top[0][0] == "uniformity"
    assert top[0][1] == 1.0


def test_format_delta_uses_improvement_language() -> None:
    # Health-score deltas: positive = improvement, negative = regression.
    now = {"pigmentation": 5.0, "uniformity": 6.0}
    prev = {"pigmentation": 3.0, "uniformity": 8.0}
    msg = _format_delta(now, prev)
    assert "改善" in msg  # pigmentation health 3.0 → 5.0 = improved
    assert "退步" in msg  # uniformity health 8.0 → 6.0 = regressed
    # Old vocabulary must not leak — UI shows arrows, prose stays in 改善/退步.
    assert "上升" not in msg
    assert "提升" not in msg


def test_coerce_to_string_passes_string_through() -> None:
    assert _coerce_to_string("hello") == "hello"
    assert _coerce_to_string("") == ""


def test_coerce_to_string_joins_list_with_newlines() -> None:
    # LLMs that ignore the "single string" instruction return arrays.
    # Output must not render as Python list repr `['a', 'b']`.
    out = _coerce_to_string(["第一項建議", "第二項建議", "第三項建議"])
    assert out == "第一項建議\n第二項建議\n第三項建議"


def test_coerce_to_string_handles_none() -> None:
    assert _coerce_to_string(None) == ""


def test_coerce_to_string_flattens_dict() -> None:
    out = _coerce_to_string({"治療": "皮秒雷射", "頻率": "3 次"})
    assert "皮秒雷射" in out
    assert "3 次" in out


def test_to_health_dict_flips_concern_metrics() -> None:
    raw = {
        "pigmentation": 7.5,
        "erythema": 0.0,
        "wrinkle": 10.0,
        "pore": 5.0,
        "uniformity": 8.5,
    }
    health = _to_health_dict(raw)
    assert health["pigmentation"] == 2.5
    assert health["erythema"] == 10.0
    assert health["wrinkle"] == 0.0
    assert health["pore"] == 5.0
    assert health["uniformity"] == 8.5  # uniformity passes through unchanged

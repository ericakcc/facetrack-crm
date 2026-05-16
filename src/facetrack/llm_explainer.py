"""Natural-language explainer + treatment-suggestion drafter.

The LLM never produces the numbers — it only translates the deterministic
CV scores into 繁中 prose plus an editable treatment-plan draft.

Two backends are provided:

    MockExplainer       — deterministic rule-based fallback. Used when
                          ANTHROPIC_API_KEY is not set, so the prototype
                          remains fully runnable offline.
    AnthropicExplainer  — Claude (Sonnet 4.6 by default). Returns the same
                          interface so swapping in a real model takes one
                          env-var change.

`get_explainer()` picks based on env config. The clinician edits the
suggestion before saving — the LLM output is a draft, never authoritative.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from facetrack.config import ANTHROPIC_API_KEY, LLM_MODEL

if TYPE_CHECKING:
    pass


@dataclass
class ExplainerOutput:
    """Result returned by any Explainer backend."""

    explanation_zh: str
    suggestion_zh: str
    backend: str


class Explainer(ABC):
    """Common interface so the UI doesn't care which backend is wired in."""

    @abstractmethod
    def explain(
        self,
        scores_now: dict[str, float],
        scores_prev: dict[str, float] | None,
        patient_name: str,
    ) -> ExplainerOutput:
        """Produce a 繁中 explanation + treatment suggestion."""


# ---------------------------------------------------------------------------
# Mock backend — runs offline, deterministic, useful for demo without an API key.
# ---------------------------------------------------------------------------

_METRIC_LABEL_ZH: dict[str, str] = {
    "pigmentation": "色素沉澱",
    "erythema": "泛紅",
    "wrinkle": "細紋",
    "pore": "毛孔粗大",
    "uniformity": "膚色均勻度",
}

_TREATMENT_LIBRARY_ZH: dict[str, str] = {
    "pigmentation": "建議 4 週療程：皮秒雷射 1064nm 2 次（間隔 2 週）+ 居家美白精華（傳明酸 3% / 維他命 C 10%）。療程結束後回診評估色素變化。",
    "erythema": "建議先進行 2 週舒敏保養（停用酸類），可考慮染料雷射（VBeam）2 次治療微血管擴張。每日嚴格防曬 SPF50+。",
    "wrinkle": "建議肉毒桿菌素 20U（額紋）或玻尿酸 1ml（法令）。居家保養加入視黃醇 0.5% 與胜肽精華。",
    "pore": "建議水飛梭 4 週療程 + A 酸調理（外用 0.05%）。控油保濕並避免過度清潔，4 週後追蹤毛孔密度。",
    "uniformity": "建議杏仁酸換膚 3 次（每 2 週一次），搭配菸鹼醯胺 5% 居家精華。長期改善膚色不均。",
}


def _identify_top_issues(
    scores: dict[str, float], top_n: int = 2
) -> list[tuple[str, float]]:
    """Return the top-N concerning metrics. Uniformity is inverted (low = bad)."""
    concerns: list[tuple[str, float]] = []
    for key, value in scores.items():
        if key == "uniformity":
            concerns.append((key, 10.0 - value))
        else:
            concerns.append((key, value))
    concerns.sort(key=lambda kv: kv[1], reverse=True)
    return concerns[:top_n]


def _format_delta(
    scores_now: dict[str, float], scores_prev: dict[str, float] | None
) -> str:
    """Build a short 繁中 sentence summarizing change vs. previous visit."""
    if not scores_prev:
        return "（本次為首次評估，尚無歷史可對照。）"
    parts: list[str] = []
    for k, v in scores_now.items():
        prev = scores_prev.get(k)
        if prev is None:
            continue
        delta = v - prev
        if abs(delta) < 0.3:
            continue
        label = _METRIC_LABEL_ZH.get(k, k)
        if k == "uniformity":
            direction = "提升" if delta > 0 else "下降"
        else:
            direction = "上升" if delta > 0 else "下降"
        parts.append(f"{label}{direction} {abs(delta):.1f}")
    if not parts:
        return "與上次回診相較，整體分數變化不大。"
    return "與上次回診相較，" + "、".join(parts) + "。"


class MockExplainer(Explainer):
    """Rule-based fallback used when no API key is configured.

    Output is intentionally formulaic — its purpose is to keep the demo
    runnable offline, not to substitute for clinical judgement.
    """

    def explain(
        self,
        scores_now: dict[str, float],
        scores_prev: dict[str, float] | None,
        patient_name: str,
    ) -> ExplainerOutput:
        top_issues = _identify_top_issues(scores_now, top_n=2)
        delta_sentence = _format_delta(scores_now, scores_prev)

        issue_lines = []
        suggestion_lines = []
        for metric, severity in top_issues:
            label = _METRIC_LABEL_ZH.get(metric, metric)
            if metric == "uniformity":
                actual = 10.0 - severity
                issue_lines.append(f"- **{label}**：目前分數 {actual:.1f}/10（偏低，越高越均勻）")
            else:
                issue_lines.append(f"- **{label}**：目前分數 {severity:.1f}/10")
            suggestion_lines.append(_TREATMENT_LIBRARY_ZH.get(metric, ""))

        explanation = (
            f"### {patient_name} — 本次評估摘要\n\n"
            f"{delta_sentence}\n\n"
            f"**主要關注項目**：\n" + "\n".join(issue_lines)
        )
        suggestion = "\n\n".join(s for s in suggestion_lines if s)
        return ExplainerOutput(
            explanation_zh=explanation,
            suggestion_zh=suggestion,
            backend="mock",
        )


# ---------------------------------------------------------------------------
# Anthropic backend — wraps Claude when ANTHROPIC_API_KEY is set.
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_ZH = """你是一位醫美診所的資深皮膚科助理。
你的任務是把下方來自電腦視覺管線的「量化皮膚分數」翻譯成自然的繁體中文說明，並提供一段可由醫師編輯的療程建議草稿。

嚴格規則：
1. 你不可以自行更動分數。分數由 CV 管線決定，是事實。
2. 所有分數採 0-10 量表。除「膚色均勻度」外，越高代表問題越明顯；膚色均勻度越高代表越好。
3. 回覆必須是純 JSON，schema 為 {"explanation_zh": "...", "suggestion_zh": "..."}。
4. explanation_zh：以 Markdown 撰寫，3-5 行，描述主要關注點與相對上次的變化。
5. suggestion_zh：以條列式給出 2-3 項具體建議，包含療程名稱、頻率、預期回診時間。語氣專業但保留編輯空間。
6. 全部使用繁體中文（台灣用語）。
"""


class AnthropicExplainer(Explainer):
    """Claude-backed explainer. Falls back to mock if the API call fails."""

    def __init__(self, api_key: str, model: str = LLM_MODEL) -> None:
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover
            raise ImportError("anthropic package not installed") from e
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._mock = MockExplainer()

    def explain(
        self,
        scores_now: dict[str, float],
        scores_prev: dict[str, float] | None,
        patient_name: str,
    ) -> ExplainerOutput:
        user_message = json.dumps(
            {
                "patient_name": patient_name,
                "scores_now": scores_now,
                "scores_prev": scores_prev,
            },
            ensure_ascii=False,
        )
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=600,
                system=_SYSTEM_PROMPT_ZH,
                messages=[{"role": "user", "content": user_message}],
            )
            text = "".join(
                block.text for block in response.content if getattr(block, "type", "") == "text"
            )
            payload = self._extract_json(text)
            return ExplainerOutput(
                explanation_zh=payload.get("explanation_zh", ""),
                suggestion_zh=payload.get("suggestion_zh", ""),
                backend=f"anthropic:{self._model}",
            )
        except Exception as e:
            logger.warning(f"Anthropic call failed ({e!r}); falling back to mock.")
            fallback = self._mock.explain(scores_now, scores_prev, patient_name)
            return ExplainerOutput(
                explanation_zh=fallback.explanation_zh,
                suggestion_zh=fallback.suggestion_zh,
                backend="mock-fallback",
            )

    @staticmethod
    def _extract_json(text: str) -> dict[str, str]:
        """Extract a JSON object even if the model wraps it in code fences."""
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_explainer() -> Explainer:
    """Return the best Explainer the environment can support."""
    if ANTHROPIC_API_KEY:
        logger.info(f"Using AnthropicExplainer (model={LLM_MODEL}).")
        return AnthropicExplainer(api_key=ANTHROPIC_API_KEY)
    logger.info("ANTHROPIC_API_KEY not set — using MockExplainer for offline demo.")
    return MockExplainer()

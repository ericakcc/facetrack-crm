"""Natural-language explainer + treatment-suggestion drafter.

The LLM never produces the numbers — it only translates the deterministic
CV scores into 繁中 prose plus an editable treatment-plan draft.

Three backends are provided:

    MockExplainer       — deterministic rule-based fallback. Used when no
                          API key is configured, so the prototype remains
                          fully runnable offline.
    AnthropicExplainer  — Claude (Sonnet 4.6 by default).
    GeminiExplainer     — Google Gemini (2.5 Flash by default).

`get_explainer()` picks based on env config:
    LLM_BACKEND=gemini    → force Gemini (requires GEMINI_API_KEY)
    LLM_BACKEND=anthropic → force Anthropic (requires ANTHROPIC_API_KEY)
    unset                 → prefer Anthropic, else Gemini, else Mock

Score convention (visible to LLM and to UI):
    All five metrics are presented as **health scores** where HIGHER = BETTER
    (10 = best skin condition). The raw direction from `facetrack.scoring` is
    flipped on the four concern metrics before being handed to any backend, so
    the LLM speaks the same language as the UI cards and radar chart.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from facetrack.config import (
    ANTHROPIC_API_KEY,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LLM_BACKEND,
    LLM_MODEL,
)
from facetrack.score_display import health_band, to_health_score

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
        """Produce a 繁中 explanation + treatment suggestion.

        Args:
            scores_now: Raw 0-10 metrics from the CV scoring engine, keyed by
                metric name. Direction matches `facetrack.scoring` conventions
                (concern metrics ascend with severity).
            scores_prev: Same shape as `scores_now`, from the previous visit,
                or None for first-time patients.
            patient_name: Display name (for personalised explanation header).
        """


# ---------------------------------------------------------------------------
# Shared helpers — work entirely in HEALTH-SCORE space (higher = better)
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


def _to_health_dict(raw_scores: dict[str, float]) -> dict[str, float]:
    """Convert a dict of raw 0-10 metric scores to unified health scores."""
    return {k: to_health_score(k, v) for k, v in raw_scores.items()}


def _identify_top_issues(
    health_scores: dict[str, float], top_n: int = 2
) -> list[tuple[str, float]]:
    """Return the top-N most concerning metrics (lowest health = worst).

    Args:
        health_scores: Already converted to health-score space (higher=better).
        top_n: How many to return.

    Returns:
        List of (metric_key, health_score) sorted ascending — worst first.
    """
    sorted_items = sorted(health_scores.items(), key=lambda kv: kv[1])
    return sorted_items[:top_n]


def _format_delta(health_now: dict[str, float], health_prev: dict[str, float] | None) -> str:
    """Build a 繁中 sentence summarising change vs. previous visit.

    Operates entirely in health-score space, so direction is unambiguous:
    delta > 0 means health improved (好轉), delta < 0 means health degraded
    (退步). This matches the UI card's up/down arrows.
    """
    if not health_prev:
        return "（本次為首次評估，尚無歷史可對照。）"
    parts: list[str] = []
    for k, v in health_now.items():
        prev = health_prev.get(k)
        if prev is None:
            continue
        delta = v - prev
        if abs(delta) < 0.3:
            continue
        label = _METRIC_LABEL_ZH.get(k, k)
        direction = "改善" if delta > 0 else "退步"
        parts.append(f"{label}{direction} {abs(delta):.1f} 分")
    if not parts:
        return "與上次回診相較，整體膚況變化不大。"
    return "與上次回診相較，" + "、".join(parts) + "。"


def _build_explanation_zh(
    patient_name: str,
    health_now: dict[str, float],
    health_prev: dict[str, float] | None,
) -> tuple[str, list[str]]:
    """Build the Mock backend's explanation Markdown + per-issue treatment lines.

    Returns:
        (explanation_markdown, suggestion_lines_to_concat)
    """
    top_issues = _identify_top_issues(health_now, top_n=2)
    delta_sentence = _format_delta(health_now, health_prev)

    issue_lines: list[str] = []
    suggestion_lines: list[str] = []
    for metric_key, health in top_issues:
        label = _METRIC_LABEL_ZH.get(metric_key, metric_key)
        emoji, band, _color = health_band(health)
        issue_lines.append(f"- **{label}**：膚況指數 {health:.1f}/10 {emoji} {band}（越高越好）")
        treatment = _TREATMENT_LIBRARY_ZH.get(metric_key, "")
        if treatment:
            suggestion_lines.append(treatment)

    explanation = (
        f"### {patient_name} — 本次評估摘要\n\n"
        f"{delta_sentence}\n\n"
        f"**主要關注項目**（膚況指數最低者）：\n" + "\n".join(issue_lines)
    )
    return explanation, suggestion_lines


# ---------------------------------------------------------------------------
# Mock backend — runs offline, deterministic, useful for demo without an API key.
# ---------------------------------------------------------------------------


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
        health_now = _to_health_dict(scores_now)
        health_prev = _to_health_dict(scores_prev) if scores_prev else None
        explanation, suggestion_lines = _build_explanation_zh(patient_name, health_now, health_prev)
        suggestion = "\n\n".join(s for s in suggestion_lines if s)
        return ExplainerOutput(
            explanation_zh=explanation,
            suggestion_zh=suggestion,
            backend="mock",
        )


# ---------------------------------------------------------------------------
# Shared system prompt for LLM-backed explainers — operates in health-score space.
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_ZH = """你是一位醫美診所的資深皮膚科助理。
你的任務是把下方來自電腦視覺管線的「膚況指數」翻譯成自然的繁體中文說明，並提供一段可由醫師編輯的療程建議草稿。

嚴格規則：
1. 你不可以自行更動分數。分數由 CV 管線決定，是事實。
2. 所有分數採 0-10 的**膚況指數**：**分數越高代表該項膚況越好**（10 為最佳，0 為最差）。
   - 例如「色素沉澱 2.1/10」表示色素問題嚴重；「色素沉澱 8.5/10」表示幾乎沒有色素問題。
   - 例如「膚色均勻度 9.0/10」表示膚色非常均勻。
3. 描述變化時，請用「改善 / 退步 / 持平」這類**以膚況為主詞**的字眼，不要用「分數上升/下降」這種模糊說法。
4. 主要關注的是**分數最低**的指標（膚況最差），請以這些指標為療程建議的核心。
5. 回覆必須是純 JSON，schema **嚴格**為 {"explanation_zh": "<string>", "suggestion_zh": "<string>"}。
   - 兩個欄位皆為**單一字串**，不可以是陣列、物件或巢狀結構。
   - 不要在字串外加任何包裝（如不要寫 {"suggestion_zh": ["...","..."]}）。
6. explanation_zh 格式（會用 Markdown 渲染）：
   - 3-5 行的自然段落，可使用 **粗體** 強調指標名稱
   - 起首先稱呼病患，再陳述本次膚況重點與相對上次的變化（用「改善/退步」字眼）
   - 結尾給一句整體判讀
7. suggestion_zh 格式（會在純文字編輯框顯示，**不會渲染 Markdown**，所以不要用 `**粗體**` 語法）：
   - 2-3 項具體建議，每項一行，行首用「1. 」「2. 」「3. 」編號
   - 每項格式：`<編號>. <療程名稱>｜<針對指標>：<頻率與療程數>，<預期回診時間>。`
   - 範例：`1. 皮秒雷射 (PicoSure)｜針對色素沉澱與毛孔粗大：3 次完整療程，每次間隔 3-4 週，預計第 4 週回診評估。`
   - 行與行之間用單一換行符隔開，不要用 Markdown bullet 符號（- 或 *）。
8. 全部使用繁體中文（台灣用語）。
"""


def _build_llm_user_message(
    patient_name: str,
    health_now: dict[str, float],
    health_prev: dict[str, float] | None,
) -> str:
    """Build the JSON payload sent to LLM backends, in health-score space."""
    return json.dumps(
        {
            "patient_name": patient_name,
            "health_scores_now": health_now,
            "health_scores_prev": health_prev,
            "score_convention": "higher_is_better",
            "metric_labels_zh": _METRIC_LABEL_ZH,
        },
        ensure_ascii=False,
    )


def _extract_json(text: str) -> dict[str, str]:
    """Extract a JSON object even if the model wraps it in code fences."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def _coerce_to_string(value: object) -> str:
    """Normalise an LLM-returned field that may be a string, list, or dict.

    LLMs occasionally ignore the 'must be a single string' instruction and
    return an array or object. This helper flattens the value to a single
    human-readable string so Streamlit's text_area never shows Python repr
    like `['item 1', 'item 2']`.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_coerce_to_string(item) for item in value if item is not None)
    if isinstance(value, dict):
        return "\n".join(f"{k}: {_coerce_to_string(v)}" for k, v in value.items())
    return str(value)


# ---------------------------------------------------------------------------
# Anthropic backend — wraps Claude when ANTHROPIC_API_KEY is set.
# ---------------------------------------------------------------------------


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
        health_now = _to_health_dict(scores_now)
        health_prev = _to_health_dict(scores_prev) if scores_prev else None
        user_message = _build_llm_user_message(patient_name, health_now, health_prev)
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
            payload = _extract_json(text)
            return ExplainerOutput(
                explanation_zh=_coerce_to_string(payload.get("explanation_zh", "")),
                suggestion_zh=_coerce_to_string(payload.get("suggestion_zh", "")),
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


# ---------------------------------------------------------------------------
# Gemini backend — wraps Google Gemini when GEMINI_API_KEY is set.
# ---------------------------------------------------------------------------


class GeminiExplainer(Explainer):
    """Google Gemini-backed explainer. Falls back to mock if the API call fails."""

    def __init__(self, api_key: str, model: str = GEMINI_MODEL) -> None:
        try:
            from google import genai
        except ImportError as e:  # pragma: no cover
            raise ImportError("google-genai package not installed") from e
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._mock = MockExplainer()

    def explain(
        self,
        scores_now: dict[str, float],
        scores_prev: dict[str, float] | None,
        patient_name: str,
    ) -> ExplainerOutput:
        from google.genai import types

        health_now = _to_health_dict(scores_now)
        health_prev = _to_health_dict(scores_prev) if scores_prev else None
        user_message = _build_llm_user_message(patient_name, health_now, health_prev)
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM_PROMPT_ZH,
                    response_mime_type="application/json",
                    # Gemini 2.5 Flash uses dynamic 'thinking' tokens by default,
                    # which can silently consume the entire output budget for
                    # simple JSON-shaped tasks like this. Disable it.
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                    max_output_tokens=2048,
                ),
            )
            text = (response.text or "").strip()
            if not text:
                logger.warning(
                    f"Gemini returned empty text (finish_reason="
                    f"{getattr(response.candidates[0], 'finish_reason', '?') if response.candidates else '?'})"
                    f"; falling back to mock."
                )
                return self._fallback(scores_now, scores_prev, patient_name)
            payload = _extract_json(text)
            explanation = _coerce_to_string(payload.get("explanation_zh", ""))
            suggestion = _coerce_to_string(payload.get("suggestion_zh", ""))
            if not explanation and not suggestion:
                logger.warning(
                    f"Gemini response could not be parsed as JSON "
                    f"(first 200 chars: {text[:200]!r}); falling back to mock."
                )
                return self._fallback(scores_now, scores_prev, patient_name)
            return ExplainerOutput(
                explanation_zh=explanation,
                suggestion_zh=suggestion,
                backend=f"gemini:{self._model}",
            )
        except Exception as e:
            logger.warning(f"Gemini call failed ({e!r}); falling back to mock.")
            return self._fallback(scores_now, scores_prev, patient_name)

    def _fallback(
        self,
        scores_now: dict[str, float],
        scores_prev: dict[str, float] | None,
        patient_name: str,
    ) -> ExplainerOutput:
        out = self._mock.explain(scores_now, scores_prev, patient_name)
        return ExplainerOutput(
            explanation_zh=out.explanation_zh,
            suggestion_zh=out.suggestion_zh,
            backend="mock-fallback",
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_explainer() -> Explainer:
    """Return the best Explainer the environment can support.

    Priority:
        1. LLM_BACKEND env var ('anthropic' | 'gemini') if set + matching key present
        2. Anthropic (if ANTHROPIC_API_KEY set)
        3. Gemini (if GEMINI_API_KEY set)
        4. Mock (offline fallback)
    """
    forced = (LLM_BACKEND or "").strip().lower() or None

    if forced == "anthropic":
        if not ANTHROPIC_API_KEY:
            logger.warning("LLM_BACKEND=anthropic but ANTHROPIC_API_KEY missing — using Mock.")
            return MockExplainer()
        logger.info(f"Using AnthropicExplainer (model={LLM_MODEL}, forced).")
        return AnthropicExplainer(api_key=ANTHROPIC_API_KEY)

    if forced == "gemini":
        if not GEMINI_API_KEY:
            logger.warning("LLM_BACKEND=gemini but GEMINI_API_KEY missing — using Mock.")
            return MockExplainer()
        logger.info(f"Using GeminiExplainer (model={GEMINI_MODEL}, forced).")
        return GeminiExplainer(api_key=GEMINI_API_KEY)

    if ANTHROPIC_API_KEY:
        logger.info(f"Using AnthropicExplainer (model={LLM_MODEL}).")
        return AnthropicExplainer(api_key=ANTHROPIC_API_KEY)

    if GEMINI_API_KEY:
        logger.info(f"Using GeminiExplainer (model={GEMINI_MODEL}).")
        return GeminiExplainer(api_key=GEMINI_API_KEY)

    logger.info("No LLM API key set — using MockExplainer for offline demo.")
    return MockExplainer()

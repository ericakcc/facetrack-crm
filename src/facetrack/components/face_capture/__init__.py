"""Live MediaPipe Face Mesh capture (front + left + right profile).

Renders a webcam stream with a neon face-mesh overlay, computes head pose
client-side from MediaPipe's `facialTransformationMatrixes`, and auto-captures
a JPEG when the user holds the requested pose stable for ~1.5 s (elapsed-time
hold, not frame-count — see `LIVE_CAPTURE_HOLD_MS`). A manual-shutter button
is also available as an escape hatch when auto-detect won't trigger.

Returns a dict shaped:

    {
        "front": {"jpeg_b64": str, "yaw": float, "pitch": float, "roll": float, "captured_at": iso},
        "left":  {...} | None,
        "right": {...} | None,
        "session_id": int,
    }

`None` is returned until the user clicks the "完成" button in the widget.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import streamlit.components.v1 as components

_FRONTEND_DIR = Path(__file__).parent / "frontend"
_VENDORED_MODEL = Path(__file__).resolve().parents[2] / "models" / "face_landmarker.task"
_FRONTEND_MODEL = _FRONTEND_DIR / "face_landmarker.task"


def _ensure_model_available() -> None:
    """Mirror the vendored MediaPipe model into the component's static dir.

    Streamlit serves the entire `path=` directory as the iframe's origin, so
    putting the model file here lets `index.html` load it with a relative URL
    — no CDN, no CORS, works offline. We avoid checking it into the repo
    twice by copying lazily on first import.
    """
    if not _VENDORED_MODEL.exists():
        return  # The component HTML degrades gracefully and shows a banner.
    if (
        _FRONTEND_MODEL.exists()
        and _FRONTEND_MODEL.stat().st_size == _VENDORED_MODEL.stat().st_size
    ):
        return
    shutil.copyfile(_VENDORED_MODEL, _FRONTEND_MODEL)


_ensure_model_available()

_component_func = components.declare_component(
    "face_capture",
    path=str(_FRONTEND_DIR),
)


def face_capture(
    *,
    key: str | None = None,
    hold_ms: int = 1500,
    profile_yaw_min_deg: float = 5.0,
    profile_pitch_tol_deg: float = 15.0,
    front_yaw_tol_deg: float = 15.0,
    front_pitch_tol_deg: float = 17.0,
    burst_ms: int = 500,
    pose_ema_alpha: float = 0.35,
    ghost_front: str | None = None,
    ghost_left: str | None = None,
    ghost_right: str | None = None,
    height: int = 1200,
) -> dict[str, Any] | None:
    """Render the live face-mesh capture widget.

    Args:
        key: Streamlit widget key (must be stable across reruns).
        hold_ms: Elapsed-time (ms) the pose must be held before auto-capture
            locks and the sharpest-frame burst begins. Frame-rate independent,
            unlike the old frame-count stability meter.
        profile_yaw_min_deg: Minimum |yaw| to count as a profile pose.
        profile_pitch_tol_deg: Pitch tolerance while in profile mode.
        front_yaw_tol_deg: Yaw tolerance for the frontal pose.
        front_pitch_tol_deg: Pitch tolerance for the frontal pose.
        burst_ms: Burst-window length (ms) after lock; the sharpest
            in-tolerance frame in this window is kept.
        pose_ema_alpha: EMA smoothing factor for head-pose angles (higher =
            snappier, less smooth).
        ghost_front / ghost_left / ghost_right: Optional prior-visit photos as
            data-URL strings, drawn faintly under the live preview to reproduce
            framing. ``None`` hides that angle's overlay.
        height: iframe height in pixels.

    Returns:
        The capture payload, or None until the user clicks "完成".
    """
    return _component_func(
        holdMs=hold_ms,
        profileYawMinDeg=profile_yaw_min_deg,
        profilePitchTolDeg=profile_pitch_tol_deg,
        frontYawTolDeg=front_yaw_tol_deg,
        frontPitchTolDeg=front_pitch_tol_deg,
        burstMs=burst_ms,
        poseEmaAlpha=pose_ema_alpha,
        ghostFront=ghost_front,
        ghostLeft=ghost_left,
        ghostRight=ghost_right,
        height=height,
        key=key,
        default=None,
    )

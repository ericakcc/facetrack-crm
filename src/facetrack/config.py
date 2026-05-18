"""Centralized paths and runtime configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
DATA_DIR: Path = PROJECT_ROOT / "data"
PHOTOS_DIR: Path = DATA_DIR / "photos"
DB_PATH: Path = DATA_DIR / "facetrack.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

DB_URL: str = f"sqlite:///{DB_PATH}"

ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
LLM_MODEL: str = os.getenv("LLM_MODEL", "claude-sonnet-4-6")

# Gemini backend. Set GEMINI_API_KEY in .env to enable. When both Anthropic
# and Gemini keys are configured, the factory in llm_explainer prefers
# whichever LLM_BACKEND is explicitly set, else Anthropic by default.
GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
LLM_BACKEND: str | None = os.getenv("LLM_BACKEND")  # 'anthropic' | 'gemini' | None=auto

# Originally tuned for clinic-grade DSLR photos. Loosened after switching to
# live webcam capture, which has lower native resolution and rarely produces
# Laplacian variances > 100 even on well-lit faces — anything stricter rejects
# real users repeatedly. The blurry-image regression test (GaussianBlur 51/25)
# crushes the variance to near zero, so the new threshold still catches the
# genuinely-blurry case.
POSE_TOLERANCE_DEG: float = 15.0
EXPOSURE_LOW_PCT: float = 0.02
EXPOSURE_HIGH_PCT: float = 0.02
SHARPNESS_MIN_LAPLACIAN_VAR: float = 30.0

# Live-capture / profile-pose tunables (used by the JS face_capture component
# and by the profile branch of ConsistencyGate._check_pose).
# 5° is intentionally tiny: the side photos exist to capture cheek skin
# texture from a slightly different angle (not a dramatic profile), so the
# threshold just needs to discriminate "user has nudged their head" from
# "user is still perfectly square to the camera". Front tolerance is ±8°,
# so a 5° profile threshold still gives a clean discrimination band.
PROFILE_YAW_MIN_DEG: float = 5.0
PROFILE_PITCH_TOLERANCE_DEG: float = 15.0
LIVE_CAPTURE_STABILITY_FRAMES: int = 10
LIVE_CAPTURE_COUNTDOWN_MS: int = 3000

# Face-distance gating. Computed in the JS component as the ratio of the face
# bounding-box width to the frame width. Skin texture metrics (pore, wrinkle)
# need ≥ ~35% face fill to be reliable; > 75% risks clipping the chin / ears
# and confuses the alignment landmarks.
LIVE_CAPTURE_MIN_FACE_WIDTH_RATIO: float = 0.35
LIVE_CAPTURE_MAX_FACE_WIDTH_RATIO: float = 0.75

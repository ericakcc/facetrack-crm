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

POSE_TOLERANCE_DEG: float = 15.0
# Full-frame exposure thresholds (fallback when no face is detected).
EXPOSURE_LOW_PCT: float = 0.02
EXPOSURE_HIGH_PCT: float = 0.02
# Face-crop exposure thresholds. Looser near-black budget than full-frame:
# pupils, eyebrows and nostril shadows are legitimately near-black and occupy
# 2-3% of a healthy face crop (measured on data/test_images) — genuine
# underexposure is caught by the mean-brightness floor (60) instead.
EXPOSURE_LOW_PCT_FACE: float = 0.06
EXPOSURE_HIGH_PCT_FACE: float = 0.05

# Sharpness is measured on the face crop RESIZED to a fixed width, so the
# Laplacian-variance threshold no longer depends on camera resolution or
# subject distance (the old unnormalized threshold whiplashed 80 -> 30 when
# the input source changed from DSLR to webcam — see CLAUDE.md §5 log).
# Calibrated on data/test_images: sharp faces measure 103-540 after
# normalization; GaussianBlur(51, 25) versions measure 1.9-3.7.
SHARPNESS_NORM_FACE_WIDTH_PX: int = 256
SHARPNESS_MIN_LAPLACIAN_VAR: float = 40.0

# Lighting uniformity: relative left/right mean-brightness difference on the
# face crop. Side-lit faces corrupt the left-cheek vs right-cheek comparison
# (and inflate uniformity/pigmentation on the shadow side). Calibrated on
# data/test_images: evenly-lit faces measure 0.065-0.143, side-lit 0.31-0.52.
LIGHTING_ASYMMETRY_MAX: float = 0.25

# Skin visibility: minimum fraction of YCrCb skin-classified pixels per ROI.
# Catches masks / sunglasses / hair occlusion (LIMITATIONS §2). Calibrated:
# real-face ROIs measure >= 0.50 (worst case, shadowed cheek), mask fabric /
# sunglasses measure 0.00. NOTE: the YCrCb band is tuned for Fitzpatrick
# II-IV (the Taiwan clinic population); re-validate before deploying to
# Fitzpatrick V-VI populations (see LIMITATIONS §4).
SKIN_RATIO_MIN: float = 0.35
SKIN_CR_RANGE: tuple[int, int] = (133, 180)
SKIN_CB_RANGE: tuple[int, int] = (77, 135)

# White-balance gains from the ArUco gray card are clamped so a mis-sampled
# card (or extreme cast) can never recolor the face harder than plausible
# clinic lighting would — beyond this range, uncalibrated is safer.
WB_GAIN_MIN: float = 0.6
WB_GAIN_MAX: float = 1.8

# Scale normalization: every aligned face is rescaled so the anatomical face
# width (landmark 234 <-> 454) equals this constant BEFORE ROI extraction.
# All five scoring metrics use fixed pixel-size kernels, so without this the
# same skin photographed at a different distance/resolution scores
# differently (measured: up to +5 points on pore/wrinkle at 0.5x input).
# 512 is chosen as the LOWEST-common-denominator scale: every input the gate
# accepts (native face width >= MIN_NATIVE_FACE_WIDTH_PX) reaches this scale
# by DOWNSCALING or mild (<= 1.28x) upscaling, so no accepted photo has a
# detail ceiling below the sampling grid — upscale-fabricated smoothness was
# the residual drift source when the target was 1024.
NORMALIZED_FACE_WIDTH_PX: float = 512.0
# Native (pre-normalization) face width floor. Below this the photo simply
# does not carry enough skin texture to score comparably — reject at the
# gate instead of scoring interpolated pixels. 400 sits under the live
# webcam capture's own floor (>= 35% of a 1280px frame = 448px), so every
# auto-captured frame passes; tiny uploads are rejected honestly.
MIN_NATIVE_FACE_WIDTH_PX: float = 400.0
SCALE_FACTOR_MIN: float = 0.25
SCALE_FACTOR_MAX: float = 4.0
MAX_ALIGNED_PIXELS: int = 16_000_000  # canvas cap: tiny face in a huge frame

# Version of the deterministic scoring formula. Bump whenever any scoring
# metric, threshold, or the pipeline geometry feeding it changes; the value
# is persisted per visit so longitudinal charts can annotate version
# boundaries instead of silently mixing incomparable numbers.
# v1 = 48hr-build formulas; v2 = scale normalization + specular/shadow
# exclusion (2026-07-04).
SCORING_VERSION: int = 2

# Live-capture / profile-pose tunables (used by the JS face_capture component
# and by the profile branch of ConsistencyGate._check_pose).
# 5° is intentionally tiny: the side photos exist to capture cheek skin
# texture from a slightly different angle (not a dramatic profile), so the
# threshold just needs to discriminate "user has nudged their head" from
# "user is still perfectly square to the camera". Front tolerance is ±15°,
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

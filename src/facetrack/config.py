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

POSE_TOLERANCE_DEG: float = 8.0
EXPOSURE_LOW_PCT: float = 0.02
EXPOSURE_HIGH_PCT: float = 0.02
SHARPNESS_MIN_LAPLACIAN_VAR: float = 80.0

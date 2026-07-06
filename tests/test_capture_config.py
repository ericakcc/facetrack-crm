"""Capture-timing config values are present and sane after the countdown removal."""

from __future__ import annotations

import facetrack.config as cfg


def test_burst_and_ema_defined():
    assert 200 <= cfg.LIVE_CAPTURE_BURST_MS <= 1200
    assert 0.1 <= cfg.LIVE_CAPTURE_POSE_EMA_ALPHA <= 0.8


def test_stability_frames_snappy():
    assert 4 <= cfg.LIVE_CAPTURE_STABILITY_FRAMES <= 9


def test_countdown_removed():
    assert not hasattr(cfg, "LIVE_CAPTURE_COUNTDOWN_MS")

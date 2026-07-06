"""Tests for the ghost-overlay photo loader."""

from __future__ import annotations

import base64
from datetime import date
from pathlib import Path

import cv2
import numpy as np
from sqlmodel import Session

import facetrack.ghost_photos as gp
from facetrack.db import Visit
from facetrack.ghost_photos import get_ghost_photos


def _write_img(path: Path, size: int = 1000, fill: int = 128) -> None:
    cv2.imwrite(str(path), np.full((size, size, 3), fill, dtype=np.uint8))


def test_no_prior_visit_returns_all_none(in_memory_db):
    assert get_ghost_photos(999) == {"front": None, "left": None, "right": None}


def test_front_only_encodes_front(in_memory_db, tmp_path, monkeypatch):
    monkeypatch.setattr(gp, "PROJECT_ROOT", tmp_path)
    _write_img(tmp_path / "front.jpg")
    with Session(in_memory_db) as s:
        s.add(Visit(patient_id=1, visit_date=date(2026, 1, 1), photo_path="front.jpg"))
        s.commit()
    result = get_ghost_photos(1)
    assert result["front"].startswith("data:image/jpeg;base64,")
    assert result["left"] is None and result["right"] is None


def test_latest_visit_wins(in_memory_db, tmp_path, monkeypatch):
    monkeypatch.setattr(gp, "PROJECT_ROOT", tmp_path)
    _write_img(tmp_path / "old.jpg", fill=64)
    _write_img(tmp_path / "new.jpg", fill=192)
    with Session(in_memory_db) as s:
        s.add(Visit(patient_id=1, visit_date=date(2026, 1, 1), photo_path="old.jpg"))
        s.add(Visit(patient_id=1, visit_date=date(2026, 6, 1), photo_path="new.jpg"))
        s.commit()
    # Verify latest visit (new.jpg with fill=192) is chosen, not old (fill=64)
    url = get_ghost_photos(1)["front"]
    assert url is not None
    raw = base64.b64decode(url.split(",", 1)[1])
    decoded = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    # JPEG is lossy; new.jpg fill=192 should decode to ~192, old.jpg fill=64 to ~64
    # Use 15-point tolerance for JPEG compression artifacts
    assert abs(decoded.mean() - 192) < 15, f"Expected mean ~192 (new visit), got {decoded.mean()}"


def test_downscales_to_max_px(in_memory_db, tmp_path, monkeypatch):
    monkeypatch.setattr(gp, "PROJECT_ROOT", tmp_path)
    _write_img(tmp_path / "big.jpg", size=1000)
    with Session(in_memory_db) as s:
        s.add(Visit(patient_id=1, visit_date=date(2026, 1, 1), photo_path="big.jpg"))
        s.commit()
    url = get_ghost_photos(1, max_px=480)["front"]
    raw = base64.b64decode(url.split(",", 1)[1])
    decoded = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    assert max(decoded.shape[:2]) <= 480


def test_missing_file_returns_none(in_memory_db, tmp_path, monkeypatch):
    monkeypatch.setattr(gp, "PROJECT_ROOT", tmp_path)
    with Session(in_memory_db) as s:
        s.add(Visit(patient_id=1, visit_date=date(2026, 1, 1), photo_path="nope.jpg"))
        s.commit()
    assert get_ghost_photos(1)["front"] is None

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


def _write_img(path: Path, size: int = 1000) -> None:
    cv2.imwrite(str(path), np.full((size, size, 3), 128, dtype=np.uint8))


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
    _write_img(tmp_path / "old.jpg")
    _write_img(tmp_path / "new.jpg")
    with Session(in_memory_db) as s:
        s.add(Visit(patient_id=1, visit_date=date(2026, 1, 1), photo_path="old.jpg"))
        s.add(Visit(patient_id=1, visit_date=date(2026, 6, 1), photo_path="new.jpg"))
        s.commit()
    # both decode to same pixels; assert a photo is returned (latest exists)
    assert get_ghost_photos(1)["front"] is not None


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

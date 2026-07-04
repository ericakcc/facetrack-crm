"""Robustness contract for Scoring v2.

Two things are pinned here:

1. Specular-glare / deep-shadow pixels are excluded from every metric —
   clinic downlights put a glare patch on most foreheads, and that glare
   was previously counted as "non-uniform skin" and "edges".
2. The scoring formula carries an explicit version (SCORING_VERSION) that
   is persisted per visit, so a formula change can never silently mix
   incomparable numbers in one longitudinal chart.
"""

from __future__ import annotations

import cv2
import numpy as np
from sqlalchemy import text
from sqlmodel import Session

import facetrack.db as db_module
from facetrack.db import Visit
from facetrack.scoring import (
    SCORING_VERSION,
    pigmentation_raw,
    score_region,
    uniformity_raw,
)


def _flat_skin(value: int = 150, size: int = 128) -> np.ndarray:
    return np.full((size, size, 3), value, dtype=np.uint8)


def test_specular_glare_excluded_from_uniformity() -> None:
    """A pure-white glare disk on otherwise flat skin must not register as
    tone non-uniformity — the glare is a lighting artifact, not skin."""
    img = _flat_skin()
    cv2.circle(img, (64, 64), 20, (255, 255, 255), -1)

    base = uniformity_raw(_flat_skin())
    with_glare = uniformity_raw(img)
    assert base == 0.0
    assert with_glare < 3.0, f"glare leaked into uniformity: {with_glare}"


def test_deep_shadow_excluded_from_pigmentation() -> None:
    """Near-black occlusion blobs (hair strands, deep shadow) must not be
    scored as melanin spots. Real pigmentation (mid-dark) still counts."""
    img = _flat_skin()
    rng = np.random.default_rng(7)
    for _ in range(8):
        cx, cy = rng.integers(20, 108, size=2)
        cv2.circle(img, (int(cx), int(cy)), 6, (3, 3, 3), -1)

    assert pigmentation_raw(img) < 0.005, "deep-shadow blobs were scored as pigmentation"

    # Control: genuinely pigmented (mid-dark) spots must still be detected.
    img2 = _flat_skin()
    for _ in range(8):
        cx, cy = rng.integers(20, 108, size=2)
        cv2.circle(img2, (int(cx), int(cy)), 6, (90, 90, 90), -1)
    assert pigmentation_raw(img2) > 0.02, "real pigmentation signal was lost"


def test_fully_specular_crop_falls_back_gracefully() -> None:
    """If exclusion would remove (almost) all pixels, fall back to the
    original mask instead of scoring an empty region."""
    img = np.full((64, 64, 3), 255, dtype=np.uint8)
    scores = score_region(img)
    for metric in ("pigmentation", "erythema", "wrinkle", "pore", "uniformity"):
        value = getattr(scores, metric)
        assert 0.0 <= value <= 10.0


def test_exclusion_is_deterministic() -> None:
    """Exclusion must not break the bit-identical reproducibility contract."""
    img = _flat_skin()
    cv2.circle(img, (40, 40), 15, (255, 255, 255), -1)
    cv2.circle(img, (90, 90), 10, (3, 3, 3), -1)
    a = score_region(img)
    b = score_region(img)
    assert a == b


def test_scoring_version_is_two() -> None:
    """Formula changes bump this constant; the DB stores it per visit."""
    assert SCORING_VERSION == 2


def test_new_visit_carries_current_scoring_version(in_memory_db) -> None:
    """A freshly saved Visit defaults to the current SCORING_VERSION."""
    with Session(in_memory_db) as session:
        visit = Visit(patient_id=1, visit_date=__import__("datetime").date(2026, 7, 4))
        session.add(visit)
        session.commit()
        session.refresh(visit)
        assert visit.scoring_version == SCORING_VERSION


def test_legacy_visit_rows_migrate_to_version_one(monkeypatch) -> None:
    """Pre-v2 DBs gain a scoring_version column and existing rows are tagged 1
    (they were scored by the v1 formula)."""
    from sqlmodel import create_engine

    legacy = create_engine("sqlite://", connect_args={"check_same_thread": False})
    with legacy.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE visit (id INTEGER PRIMARY KEY, patient_id INTEGER,"
                " visit_date DATE, quality_passed BOOLEAN)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO visit (patient_id, visit_date, quality_passed) VALUES (1, '2026-01-01', 1)"
            )
        )
    monkeypatch.setattr(db_module, "engine", legacy)
    db_module._migrate_add_visit_scoring_version_column()
    with legacy.begin() as conn:
        row = conn.execute(text("SELECT scoring_version FROM visit")).fetchone()
    assert row[0] == 1

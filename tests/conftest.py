"""Pytest fixtures for DB-touching tests.

Swaps `facetrack.db.engine` to an in-memory SQLite engine for the duration of
each test function so production data at `data/facetrack.db` is never touched
and tests start from a clean schema.
"""

from __future__ import annotations

import pytest
from sqlmodel import SQLModel, create_engine

import facetrack.db as db_module


@pytest.fixture
def in_memory_db(monkeypatch: pytest.MonkeyPatch):
    """Swap the module-level engine for an in-memory SQLite engine.

    `get_session()` resolves `engine` at call time, so the monkeypatch
    propagates to every caller (including `patient_service`) without each
    needing to re-import.
    """
    test_engine = create_engine(
        "sqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(test_engine)
    monkeypatch.setattr(db_module, "engine", test_engine)
    yield test_engine
    test_engine.dispose()

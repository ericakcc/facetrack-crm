"""Behavioural contract for `facetrack.patient_service` CRUD."""

from __future__ import annotations

from datetime import date

import pytest
from sqlmodel import select

from facetrack.db import Gender, Patient, Visit, get_session
from facetrack.patient_service import (
    create_patient,
    list_patients,
    restore_patient,
    soft_delete_patient,
    update_patient,
)


def _make_patient(name: str = "測試病患") -> Patient:
    return create_patient(
        name=name,
        gender=Gender.FEMALE,
        birth_date=date(1990, 1, 1),
        phone="0900-000-000",
        notes="unit test fixture",
    )


def test_create_patient_persists_with_default_active(in_memory_db) -> None:
    patient = _make_patient()
    assert patient.id is not None
    assert patient.is_active is True
    assert patient.name == "測試病患"

    listed = list_patients()
    assert len(listed) == 1
    assert listed[0].id == patient.id


def test_create_patient_rejects_empty_name(in_memory_db) -> None:
    with pytest.raises(ValueError):
        create_patient(
            name="   ",
            gender=Gender.FEMALE,
            birth_date=date(1990, 1, 1),
        )


def test_update_patient_partial_fields(in_memory_db) -> None:
    patient = _make_patient(name="原始姓名")
    updated = update_patient(patient.id, phone="0911-222-333")

    assert updated.phone == "0911-222-333"
    assert updated.name == "原始姓名"
    assert updated.birth_date == date(1990, 1, 1)
    assert updated.gender == Gender.FEMALE


def test_update_patient_missing_id_raises(in_memory_db) -> None:
    with pytest.raises(LookupError):
        update_patient(99999, name="鬼魂")


def test_soft_delete_then_list_excludes_by_default(in_memory_db) -> None:
    active = _make_patient(name="活著的")
    removed = _make_patient(name="要被停用的")
    soft_delete_patient(removed.id)

    default_list = list_patients()
    assert [p.id for p in default_list] == [active.id]

    full_list = list_patients(include_inactive=True)
    assert {p.id for p in full_list} == {active.id, removed.id}


def test_restore_patient_returns_to_default_list(in_memory_db) -> None:
    patient = _make_patient()
    soft_delete_patient(patient.id)
    assert list_patients() == []

    restore_patient(patient.id)
    listed = list_patients()
    assert [p.id for p in listed] == [patient.id]


def test_soft_delete_preserves_visits(in_memory_db) -> None:
    patient = _make_patient()
    with get_session() as session:
        visit = Visit(
            patient_id=patient.id,
            visit_date=date(2026, 5, 18),
            photo_path="dummy/path.jpg",
            quality_passed=True,
        )
        session.add(visit)
        session.commit()
        session.refresh(visit)
        visit_id = visit.id

    soft_delete_patient(patient.id)

    with get_session() as session:
        rows = list(session.exec(select(Visit).where(Visit.id == visit_id)).all())
    assert len(rows) == 1
    assert rows[0].patient_id == patient.id

"""Patient-domain CRUD service.

Owns all persistence write operations for the `Patient` table. Streamlit pages
import the public functions here rather than touching SQLModel sessions
directly, so business rules (e.g. soft-delete only, name-required validation,
default-active behaviour) live in one place and can be unit-tested without a
Streamlit context.
"""

from __future__ import annotations

from datetime import date

from loguru import logger
from sqlmodel import select

from facetrack.db import Gender, Patient, get_session


def list_patients(include_inactive: bool = False) -> list[Patient]:
    """Return all patients sorted by name.

    Args:
        include_inactive: When True, also return soft-deleted patients.
            Default False — only active patients appear in selector UIs.

    Returns:
        List of Patient rows, ordered by name ascending.
    """
    with get_session() as session:
        stmt = select(Patient)
        if not include_inactive:
            stmt = stmt.where(Patient.is_active == True)  # noqa: E712 — SQLModel needs == True
        stmt = stmt.order_by(Patient.name)
        return list(session.exec(stmt).all())


def get_patient(patient_id: int) -> Patient | None:
    """Look up a single patient by primary key.

    Args:
        patient_id: Patient row id.

    Returns:
        The Patient row, or None if no row matches.
    """
    with get_session() as session:
        return session.get(Patient, patient_id)


def create_patient(
    name: str,
    gender: Gender,
    birth_date: date,
    phone: str = "",
    notes: str = "",
) -> Patient:
    """Insert a new active patient.

    Args:
        name: Display name. Must contain at least one non-whitespace character.
        gender: Patient gender enum value.
        birth_date: Date of birth.
        phone: Contact phone (optional).
        notes: Free-text intake notes (optional).

    Returns:
        The persisted Patient row with `id` populated.

    Raises:
        ValueError: If `name` is empty or whitespace-only.
    """
    if not name.strip():
        raise ValueError("病患姓名不可為空白。")

    patient = Patient(
        name=name.strip(),
        gender=gender,
        birth_date=birth_date,
        phone=phone.strip(),
        notes=notes.strip(),
        is_active=True,
    )
    with get_session() as session:
        session.add(patient)
        session.commit()
        session.refresh(patient)
    logger.info(f"Created patient id={patient.id} name={patient.name!r}")
    return patient


def update_patient(
    patient_id: int,
    *,
    name: str | None = None,
    gender: Gender | None = None,
    birth_date: date | None = None,
    phone: str | None = None,
    notes: str | None = None,
) -> Patient:
    """Update selected fields on an existing patient.

    Keyword-only arguments; pass `None` (the default) to leave a field
    unchanged. Trims whitespace on string fields and rejects empty names.

    Args:
        patient_id: Row id of the patient to update.
        name: New display name (rejects empty/whitespace).
        gender: New gender enum.
        birth_date: New birth date.
        phone: New phone string.
        notes: New notes string.

    Returns:
        The refreshed Patient row.

    Raises:
        LookupError: If no patient row matches `patient_id`.
        ValueError: If `name` is provided but is empty/whitespace.
    """
    with get_session() as session:
        patient = session.get(Patient, patient_id)
        if patient is None:
            raise LookupError(f"找不到病患 id={patient_id}")

        if name is not None:
            if not name.strip():
                raise ValueError("病患姓名不可為空白。")
            patient.name = name.strip()
        if gender is not None:
            patient.gender = gender
        if birth_date is not None:
            patient.birth_date = birth_date
        if phone is not None:
            patient.phone = phone.strip()
        if notes is not None:
            patient.notes = notes.strip()

        session.add(patient)
        session.commit()
        session.refresh(patient)
    logger.info(f"Updated patient id={patient.id}")
    return patient


def soft_delete_patient(patient_id: int) -> None:
    """Mark a patient inactive without deleting their visit history.

    Idempotent: a no-op if the patient is already inactive. Raises if the
    patient does not exist (callers should never delete a non-existent row).

    Args:
        patient_id: Row id of the patient to deactivate.

    Raises:
        LookupError: If no patient row matches `patient_id`.
    """
    with get_session() as session:
        patient = session.get(Patient, patient_id)
        if patient is None:
            raise LookupError(f"找不到病患 id={patient_id}")
        if not patient.is_active:
            return
        patient.is_active = False
        session.add(patient)
        session.commit()
    logger.info(f"Soft-deleted patient id={patient_id}")


def restore_patient(patient_id: int) -> None:
    """Reactivate a previously soft-deleted patient.

    Idempotent: a no-op if the patient is already active.

    Args:
        patient_id: Row id of the patient to reactivate.

    Raises:
        LookupError: If no patient row matches `patient_id`.
    """
    with get_session() as session:
        patient = session.get(Patient, patient_id)
        if patient is None:
            raise LookupError(f"找不到病患 id={patient_id}")
        if patient.is_active:
            return
        patient.is_active = True
        session.add(patient)
        session.commit()
    logger.info(f"Restored patient id={patient_id}")

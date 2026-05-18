"""SQLModel schemas for patients, visits, quality reports, scores, and treatment notes.

Note: `from __future__ import annotations` is intentionally NOT used here, because
SQLModel introspects relationship annotations at class-definition time and breaks
when all annotations are turned into strings.
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlalchemy import text
from sqlmodel import Field, Relationship, Session, SQLModel, create_engine

from facetrack.config import DB_URL


# NOTE: Using (str, Enum) instead of StrEnum because SQLModel + SQLAlchemy column
# inference is well-tested against this pattern. StrEnum is the modern equivalent
# but introduces subtle equality differences we don't need here. Suppress UP042.
class Gender(str, Enum):  # noqa: UP042
    """Patient gender enum."""

    FEMALE = "female"
    MALE = "male"
    OTHER = "other"


class Region(str, Enum):  # noqa: UP042
    """Facial region of interest for per-region scoring."""

    LEFT_CHEEK = "left_cheek"
    RIGHT_CHEEK = "right_cheek"
    FOREHEAD = "forehead"
    CHIN = "chin"


class Patient(SQLModel, table=True):
    """A clinic patient with longitudinal visit history."""

    id: int | None = Field(default=None, primary_key=True)
    name: str
    gender: Gender = Field(default=Gender.FEMALE)
    birth_date: date
    phone: str = ""
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)

    visits: list["Visit"] = Relationship(
        back_populates="patient",
        sa_relationship_kwargs={"order_by": "Visit.visit_date.desc()"},
    )


class Visit(SQLModel, table=True):
    """A single clinic visit producing one intake photo + quality report + scores.

    `photo_path` is the canonical (frontal) photo used by the scoring engine.
    `photo_left_path` / `photo_right_path` store the optional side-profile photos
    captured by the live MediaPipe Face Mesh widget; they are kept for visual
    record only and not (yet) consumed by the scoring engine.
    """

    id: int | None = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    visit_date: date
    photo_path: str = ""
    photo_left_path: str | None = Field(default=None, nullable=True)
    photo_right_path: str | None = Field(default=None, nullable=True)
    quality_passed: bool = False
    quality_report_json: str = "{}"
    created_at: datetime = Field(default_factory=datetime.utcnow)

    patient: Patient | None = Relationship(back_populates="visits")
    scores: list["RegionScore"] = Relationship(back_populates="visit")
    treatment: Optional["TreatmentNote"] = Relationship(back_populates="visit")


class RegionScore(SQLModel, table=True):
    """Per-region quantitative skin metrics for a single visit."""

    id: int | None = Field(default=None, primary_key=True)
    visit_id: int = Field(foreign_key="visit.id", index=True)
    region: Region
    pigmentation: float = 0.0
    erythema: float = 0.0
    wrinkle: float = 0.0
    pore: float = 0.0
    uniformity: float = 0.0

    visit: Visit | None = Relationship(back_populates="scores")


class TreatmentNote(SQLModel, table=True):
    """AI-generated treatment suggestion (editable by clinician)."""

    id: int | None = Field(default=None, primary_key=True)
    visit_id: int = Field(foreign_key="visit.id", unique=True, index=True)
    ai_explanation: str = ""
    ai_suggestion: str = ""
    clinician_notes: str = ""
    edited_at: datetime = Field(default_factory=datetime.utcnow)

    visit: Visit | None = Relationship(back_populates="treatment")


engine = create_engine(DB_URL, echo=False, connect_args={"check_same_thread": False})


def init_db() -> None:
    """Create all tables if not present, and add columns introduced after a DB
    file already exists (SQLite zero-downtime migration for nullable columns)."""
    SQLModel.metadata.create_all(engine)
    _migrate_add_visit_side_photo_columns()


def _migrate_add_visit_side_photo_columns() -> None:
    """Backfill `photo_left_path` / `photo_right_path` on pre-existing DBs.

    SQLite is forgiving: ADD COLUMN works in O(1) for nullable columns with no
    default, so this is safe to run on every startup.
    """
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info('visit')"))}
        if "photo_left_path" not in cols:
            conn.execute(text("ALTER TABLE visit ADD COLUMN photo_left_path TEXT"))
        if "photo_right_path" not in cols:
            conn.execute(text("ALTER TABLE visit ADD COLUMN photo_right_path TEXT"))


def get_session() -> Session:
    """Return a new DB session (caller responsible for closing)."""
    return Session(engine)

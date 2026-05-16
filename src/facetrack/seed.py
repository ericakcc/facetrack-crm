"""Seed the database with demo patients and longitudinal visit history.

Scores are intentionally synthesized to show a believable improvement trajectory
for the longitudinal-tracking demo. When a real photo is later uploaded via the
intake flow, its computed scores replace these placeholders for that visit.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from loguru import logger
from sqlmodel import select

from facetrack.db import (
    Gender,
    Patient,
    Region,
    RegionScore,
    TreatmentNote,
    Visit,
    get_session,
    init_db,
)

DEMO_PATIENTS: list[dict] = [
    {
        "name": "林雅婷",
        "gender": Gender.FEMALE,
        "birth_date": date(1990, 3, 14),
        "phone": "0912-345-678",
        "notes": "主訴：兩頰色素沉澱，希望改善膚色均勻度。",
        "trajectory": "improving",
    },
    {
        "name": "陳怡君",
        "gender": Gender.FEMALE,
        "birth_date": date(1985, 7, 22),
        "phone": "0922-111-222",
        "notes": "主訴：法令紋與細紋。對皮秒雷射有興趣。",
        "trajectory": "mixed",
    },
    {
        "name": "張立宇",
        "gender": Gender.MALE,
        "birth_date": date(1988, 11, 5),
        "phone": "0933-444-555",
        "notes": "主訴：T字部位出油、毛孔粗大。",
        "trajectory": "stable",
    },
]

REGIONS: list[Region] = [Region.LEFT_CHEEK, Region.RIGHT_CHEEK, Region.FOREHEAD, Region.CHIN]


def _trajectory_scores(visit_index: int, total: int, trajectory: str) -> dict[str, float]:
    """Return per-region score deltas for the given visit position in series.

    Args:
        visit_index: 0-based index of the visit (0 = earliest).
        total: Total number of visits in the series.
        trajectory: One of "improving", "mixed", "stable".

    Returns:
        Mapping of metric name to a 0-10 float score.
    """
    progress = visit_index / max(total - 1, 1)
    base = {"pigmentation": 6.5, "erythema": 4.0, "wrinkle": 3.5, "pore": 5.0, "uniformity": 5.5}
    if trajectory == "improving":
        return {
            "pigmentation": round(base["pigmentation"] - 2.8 * progress, 2),
            "erythema": round(base["erythema"] - 1.2 * progress, 2),
            "wrinkle": round(base["wrinkle"] - 0.4 * progress, 2),
            "pore": round(base["pore"] - 0.6 * progress, 2),
            "uniformity": round(base["uniformity"] + 2.2 * progress, 2),
        }
    if trajectory == "mixed":
        return {
            "pigmentation": round(base["pigmentation"] - 1.0 * progress, 2),
            "erythema": round(base["erythema"] + 0.5 * progress, 2),
            "wrinkle": round(base["wrinkle"] - 1.2 * progress, 2),
            "pore": round(base["pore"] - 0.2 * progress, 2),
            "uniformity": round(base["uniformity"] + 0.8 * progress, 2),
        }
    return {  # stable
        "pigmentation": round(base["pigmentation"] - 0.2 * progress, 2),
        "erythema": round(base["erythema"] - 0.1 * progress, 2),
        "wrinkle": round(base["wrinkle"] + 0.1 * progress, 2),
        "pore": round(base["pore"] + 0.0 * progress, 2),
        "uniformity": round(base["uniformity"] + 0.3 * progress, 2),
    }


def _region_jitter(region: Region, base: dict[str, float]) -> dict[str, float]:
    """Apply small per-region offsets so each ROI looks different but coherent."""
    offsets = {
        Region.LEFT_CHEEK: {"pigmentation": 0.5, "erythema": 0.3},
        Region.RIGHT_CHEEK: {"pigmentation": -0.4, "erythema": -0.2},
        Region.FOREHEAD: {"wrinkle": 0.6, "pore": -0.4},
        Region.CHIN: {"pore": 0.5, "uniformity": -0.3},
    }
    offset = offsets.get(region, {})
    return {k: round(max(0.0, min(10.0, v + offset.get(k, 0.0))), 2) for k, v in base.items()}


def _treatment_for(scores: dict[str, float]) -> tuple[str, str]:
    """Generate a stub explanation + suggestion based on dominant issue."""
    sorted_issues = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    dominant = sorted_issues[0][0]
    explanation_map = {
        "pigmentation": "整體色素分數偏高，雙頰可見明顯斑點堆積。",
        "erythema": "局部泛紅指數升高，疑似敏感肌或微血管擴張。",
        "wrinkle": "額頭與眼周動態紋紋路評分上升。",
        "pore": "T字部位毛孔指標偏高，出油情況需追蹤。",
        "uniformity": "膚色均勻度尚有改善空間。",
    }
    suggestion_map = {
        "pigmentation": "建議：4 週療程，皮秒雷射 1064nm × 2 次 + 居家美白精華。",
        "erythema": "建議：先行舒敏保養 2 週後再評估，可考慮染料雷射。",
        "wrinkle": "建議：肉毒桿菌素 20U（額頭）+ 居家視黃醇導入。",
        "pore": "建議：水飛梭 + A 酸調理，4 週後追蹤。",
        "uniformity": "建議：杏仁酸換膚 × 3 次（每兩週一次）。",
    }
    return explanation_map[dominant], suggestion_map[dominant]


def seed_database(force: bool = False) -> None:
    """Populate DB with demo patients and visits.

    Args:
        force: If True, wipe existing patients before seeding.
    """
    init_db()
    with get_session() as session:
        if not force:
            existing = session.exec(select(Patient)).all()
            if existing:
                logger.info(f"Seed skipped — {len(existing)} patients already present.")
                return

        if force:
            for model in (TreatmentNote, RegionScore, Visit, Patient):
                for row in session.exec(select(model)).all():
                    session.delete(row)
            session.commit()

        today = date.today()
        for spec in DEMO_PATIENTS:
            trajectory = spec.pop("trajectory")
            patient = Patient(**spec)
            session.add(patient)
            session.commit()
            session.refresh(patient)

            visit_dates = [today - timedelta(days=d) for d in (120, 60, 0)]
            for i, vd in enumerate(visit_dates):
                base_scores = _trajectory_scores(i, len(visit_dates), trajectory)
                quality_report = {
                    "pose": {"yaw": 1.2, "pitch": -0.8, "roll": 0.3, "passed": True},
                    "exposure": {"score": 92.0, "passed": True},
                    "sharpness": {"laplacian_var": 145.0, "passed": True},
                    "color_calibrated": True,
                    "overall": "PASS",
                    "synthesized_for_demo": True,
                }
                visit = Visit(
                    patient_id=patient.id,
                    visit_date=vd,
                    photo_path="",
                    quality_passed=True,
                    quality_report_json=json.dumps(quality_report, ensure_ascii=False),
                )
                session.add(visit)
                session.commit()
                session.refresh(visit)

                for region in REGIONS:
                    region_scores = _region_jitter(region, base_scores)
                    session.add(
                        RegionScore(
                            visit_id=visit.id,
                            region=region,
                            **region_scores,
                        )
                    )

                explanation, suggestion = _treatment_for(base_scores)
                session.add(
                    TreatmentNote(
                        visit_id=visit.id,
                        ai_explanation=explanation,
                        ai_suggestion=suggestion,
                        clinician_notes="",
                    )
                )
                session.commit()

            logger.info(f"Seeded patient '{patient.name}' with {len(visit_dates)} visits.")


if __name__ == "__main__":
    seed_database(force=True)
    logger.info("Seed complete.")

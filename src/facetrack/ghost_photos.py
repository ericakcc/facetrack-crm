"""Load a patient's most-recent prior-visit photos as downscaled data URLs.

Feeds the live capture widget's ghost-overlay: the previous visit's front/left/
right photos are shown faintly over the live preview so the operator reproduces
framing across visits.
"""

from __future__ import annotations

import base64
from pathlib import Path

import cv2
from sqlmodel import select

from facetrack.config import PROJECT_ROOT
from facetrack.db import Visit, get_session


def _encode_data_url(abs_path: Path, max_px: int) -> str | None:
    """Read, downscale (longest edge ≤ max_px), and base64-encode a JPEG.

    Args:
        abs_path: Absolute path to the source image.
        max_px: Longest-edge cap for the downscaled overlay.

    Returns:
        A ``data:image/jpeg;base64,...`` string, or ``None`` if the file is
        missing or undecodable.
    """
    if not abs_path.exists():
        return None
    img = cv2.imread(str(abs_path))
    if img is None:
        return None
    h, w = img.shape[:2]
    scale = min(1.0, max_px / max(h, w))
    if scale < 1.0:
        img = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


def get_ghost_photos(patient_id: int, *, max_px: int = 480) -> dict[str, str | None]:
    """Return the patient's latest-visit photos as data URLs for ghost overlay.

    Args:
        patient_id: Patient whose most recent visit supplies the ghost images.
        max_px: Longest-edge cap for each downscaled overlay image.

    Returns:
        Mapping with keys ``front`` / ``left`` / ``right``; each value is a
        data-URL string, or ``None`` when that angle is absent (no prior visit,
        or that photo was never captured / file missing).
    """
    with get_session() as session:
        stmt = (
            select(Visit)
            .where(Visit.patient_id == patient_id)
            .order_by(Visit.visit_date.desc(), Visit.id.desc())
        )
        visit = session.exec(stmt).first()
    if visit is None:
        return {"front": None, "left": None, "right": None}
    rels = {
        "front": visit.photo_path or None,
        "left": visit.photo_left_path,
        "right": visit.photo_right_path,
    }
    return {
        key: (_encode_data_url(PROJECT_ROOT / rel, max_px) if rel else None)
        for key, rel in rels.items()
    }

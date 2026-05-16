"""Face alignment and region-of-interest extraction.

Stage 1 of the imaging pipeline. Takes a raw intake photo, locates landmarks via
MediaPipe Face Landmarker (Tasks API), rotation-corrects the face based on the
eye line, and crops four standardized regions (left cheek, right cheek, forehead,
chin). The cropped regions are then handed to the consistency gate (for quality
checks) and the scoring engine (for quantitative metrics).

The Tasks API additionally returns a facial transformation matrix which the
consistency gate uses to compute yaw/pitch/roll for pose-tolerance checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from loguru import logger
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

from facetrack.db import Region

MODEL_PATH = Path(__file__).resolve().parent / "models" / "face_landmarker.task"

LANDMARK_LEFT_EYE_OUTER = 33
LANDMARK_LEFT_EYE_INNER = 133
LANDMARK_RIGHT_EYE_INNER = 362
LANDMARK_RIGHT_EYE_OUTER = 263
LANDMARK_NOSE_TIP = 1
LANDMARK_FOREHEAD_CENTER = 10
LANDMARK_CHIN_BOTTOM = 152
LANDMARK_FACE_LEFT = 234
LANDMARK_FACE_RIGHT = 454
LANDMARK_MOUTH_TOP = 13
LANDMARK_MOUTH_LEFT = 61
LANDMARK_MOUTH_RIGHT = 291


@dataclass
class CVPipelineResult:
    """Output of the alignment + ROI extraction pipeline."""

    aligned_image: np.ndarray
    landmarks_px: np.ndarray  # shape (N, 2), pixel coords on aligned_image
    transformation_matrix: np.ndarray | None = None  # 4x4 facial transform
    rois: dict[Region, np.ndarray] = field(default_factory=dict)
    roi_bboxes: dict[Region, tuple[int, int, int, int]] = field(default_factory=dict)
    face_detected: bool = True

    @classmethod
    def no_face(cls) -> CVPipelineResult:
        """Sentinel result for the no-face-detected case."""
        return cls(
            aligned_image=np.zeros((1, 1, 3), dtype=np.uint8),
            landmarks_px=np.zeros((0, 2), dtype=np.float32),
            face_detected=False,
        )


class FacePipeline:
    """Alignment + ROI extraction. Construct once, reuse across photos."""

    def __init__(self, model_path: Path | None = None) -> None:
        model = model_path or MODEL_PATH
        if not model.exists():
            raise FileNotFoundError(
                f"Face landmarker model missing at {model}. "
                f"Download from https://storage.googleapis.com/mediapipe-models/"
                f"face_landmarker/face_landmarker/float16/1/face_landmarker.task"
            )
        options = mp_vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(model)),
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=True,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._landmarker = mp_vision.FaceLandmarker.create_from_options(options)

    def close(self) -> None:
        import contextlib

        with contextlib.suppress(Exception):
            self._landmarker.close()

    def process(self, image_bgr: np.ndarray) -> CVPipelineResult:
        """Run alignment + ROI extraction on a BGR image.

        Args:
            image_bgr: H x W x 3 uint8 BGR image (as loaded by cv2.imread).

        Returns:
            CVPipelineResult; check `.face_detected` before using ROIs.
        """
        if image_bgr is None or image_bgr.size == 0:
            return CVPipelineResult.no_face()

        landmarks_px, transform = self._detect(image_bgr)
        if landmarks_px is None:
            return CVPipelineResult.no_face()

        aligned, aligned_landmarks = self._align_face(image_bgr, landmarks_px)

        rois: dict[Region, np.ndarray] = {}
        bboxes: dict[Region, tuple[int, int, int, int]] = {}
        for region in Region:
            bbox = self._region_bbox(aligned_landmarks, region, aligned.shape[1], aligned.shape[0])
            if bbox is None:
                continue
            x, y, w, h = bbox
            crop = aligned[y : y + h, x : x + w].copy()
            if crop.size == 0:
                continue
            rois[region] = self._normalize_lighting(crop)
            bboxes[region] = bbox

        return CVPipelineResult(
            aligned_image=aligned,
            landmarks_px=aligned_landmarks,
            transformation_matrix=transform,
            rois=rois,
            roi_bboxes=bboxes,
            face_detected=True,
        )

    def process_file(self, image_path: str | Path) -> CVPipelineResult:
        """Convenience wrapper that loads an image from disk."""
        image_bgr = cv2.imread(str(image_path))
        if image_bgr is None:
            logger.warning(f"Could not read image: {image_path}")
            return CVPipelineResult.no_face()
        return self.process(image_bgr)

    def _detect(self, image_bgr: np.ndarray) -> tuple[np.ndarray | None, np.ndarray | None]:
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)
        result = self._landmarker.detect(mp_image)
        if not result.face_landmarks:
            return None, None
        h, w = image_bgr.shape[:2]
        landmarks = result.face_landmarks[0]
        pts = np.array([[lm.x * w, lm.y * h] for lm in landmarks], dtype=np.float32)
        transform = None
        if result.facial_transformation_matrixes:
            transform = np.array(result.facial_transformation_matrixes[0], dtype=np.float32)
        return pts, transform

    def _align_face(
        self, image_bgr: np.ndarray, landmarks_px: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        left_eye = landmarks_px[LANDMARK_LEFT_EYE_OUTER]
        right_eye = landmarks_px[LANDMARK_RIGHT_EYE_OUTER]
        dy = float(right_eye[1] - left_eye[1])
        dx = float(right_eye[0] - left_eye[0])
        angle = float(np.degrees(np.arctan2(dy, dx)))
        eye_center = ((left_eye + right_eye) / 2).tolist()
        center = (float(eye_center[0]), float(eye_center[1]))

        h, w = image_bgr.shape[:2]
        rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        aligned = cv2.warpAffine(image_bgr, rotation_matrix, (w, h), flags=cv2.INTER_LINEAR)

        ones = np.ones((landmarks_px.shape[0], 1), dtype=np.float32)
        landmarks_homo = np.hstack([landmarks_px, ones])
        aligned_landmarks = landmarks_homo @ rotation_matrix.T
        return aligned, aligned_landmarks.astype(np.float32)

    def _region_bbox(
        self,
        landmarks: np.ndarray,
        region: Region,
        img_w: int,
        img_h: int,
    ) -> tuple[int, int, int, int] | None:
        """Return (x, y, w, h) bounding box for the named region, clipped to image."""
        face_left = float(landmarks[LANDMARK_FACE_LEFT][0])
        face_right = float(landmarks[LANDMARK_FACE_RIGHT][0])
        face_top = float(landmarks[LANDMARK_FOREHEAD_CENTER][1])
        face_bot = float(landmarks[LANDMARK_CHIN_BOTTOM][1])
        face_w = face_right - face_left
        face_h = face_bot - face_top
        if face_w <= 0 or face_h <= 0:
            return None

        eye_y = float(landmarks[LANDMARK_LEFT_EYE_OUTER][1])
        mouth_y = float(landmarks[LANDMARK_MOUTH_TOP][1])
        mouth_left_x = float(landmarks[LANDMARK_MOUTH_LEFT][0])
        mouth_right_x = float(landmarks[LANDMARK_MOUTH_RIGHT][0])
        eye_left_inner_x = float(landmarks[LANDMARK_LEFT_EYE_INNER][0])
        eye_right_inner_x = float(landmarks[LANDMARK_RIGHT_EYE_INNER][0])

        if region == Region.LEFT_CHEEK:
            x1 = face_left + 0.05 * face_w
            x2 = eye_left_inner_x - 0.02 * face_w
            y1 = eye_y + 0.10 * face_h
            y2 = mouth_y - 0.02 * face_h
        elif region == Region.RIGHT_CHEEK:
            x1 = eye_right_inner_x + 0.02 * face_w
            x2 = face_right - 0.05 * face_w
            y1 = eye_y + 0.10 * face_h
            y2 = mouth_y - 0.02 * face_h
        elif region == Region.FOREHEAD:
            x1 = face_left + 0.20 * face_w
            x2 = face_right - 0.20 * face_w
            y1 = face_top + 0.05 * face_h
            y2 = eye_y - 0.12 * face_h
        elif region == Region.CHIN:
            x1 = mouth_left_x
            x2 = mouth_right_x
            y1 = mouth_y + 0.12 * face_h
            y2 = face_bot - 0.03 * face_h
        else:
            return None

        x = int(max(0, x1))
        y = int(max(0, y1))
        w = int(min(img_w - x, x2 - x1))
        h = int(min(img_h - y, y2 - y1))
        if w <= 4 or h <= 4:
            return None
        return (x, y, w, h)

    def _normalize_lighting(self, bgr: np.ndarray) -> np.ndarray:
        """Apply CLAHE on the L channel of LAB to reduce intra-photo lighting variance.

        This is a lightweight per-photo normalization. Cross-photo color consistency
        is the gate's responsibility (white-balance via gray card).
        """
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
        lightness, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        lightness_eq = clahe.apply(lightness)
        return cv2.cvtColor(cv2.merge((lightness_eq, a, b)), cv2.COLOR_LAB2BGR)


_default_pipeline: FacePipeline | None = None


def get_pipeline() -> FacePipeline:
    """Return a shared FacePipeline instance (lazy-initialized)."""
    global _default_pipeline
    if _default_pipeline is None:
        _default_pipeline = FacePipeline()
    return _default_pipeline

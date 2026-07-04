"""Photo-Consistency Gate — the depth-area module of FaceTrack CRM.

Before any quantitative score is computed, every intake photo passes through
this gate. The gate enforces that the photo is comparable to prior visits along
six dimensions, so that longitudinal scores reflect actual skin change rather
than camera/setup noise:

    1. POSE       — yaw / pitch / roll within tolerance (default ±15° frontal;
                    profile mode requires |yaw| ≥ 5°, see config.py)
    2. EXPOSURE   — over/under-exposure pixel ratio, measured on the FACE
                    crop when landmarks are available (a dark clinic wall must
                    not fail a well-lit face)
    3. SHARPNESS  — Laplacian-variance focus check on the face crop resized
                    to a fixed width (resolution-invariant threshold)
    4. LIGHTING   — left/right face-brightness asymmetry; side-lit faces
                    corrupt the left-cheek vs right-cheek comparison
    5. SKIN       — per-ROI skin-pixel ratio (YCrCb); catches masks,
                    sunglasses, hair occlusion before fabric gets scored
    6. COLOR      — optional white-balance via ArUco gray-reference marker
                    (soft warning; per-channel gains are clamped)

A photo that fails any check is rejected with a specific, actionable reason
("頭部右偏 12°, 請正對鏡頭"). This is the "show, don't tell" moment in the
demo video: two bad photos rejected, one good photo accepted.

The gate consumes the FacePipeline's output (it needs the alignment landmarks
and transformation matrix), so call `FacePipeline.process()` first, then
`ConsistencyGate.evaluate()`. Face-crop checks run on the pipeline's
scale-normalized `aligned_image` — the same pixels the scorer will see.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import cv2
import numpy as np

from facetrack.config import (
    EXPOSURE_HIGH_PCT,
    EXPOSURE_HIGH_PCT_FACE,
    EXPOSURE_LOW_PCT,
    EXPOSURE_LOW_PCT_FACE,
    LIGHTING_ASYMMETRY_MAX,
    MIN_NATIVE_FACE_WIDTH_PX,
    POSE_TOLERANCE_DEG,
    PROFILE_PITCH_TOLERANCE_DEG,
    PROFILE_YAW_MIN_DEG,
    SHARPNESS_MIN_LAPLACIAN_VAR,
    SHARPNESS_NORM_FACE_WIDTH_PX,
    SKIN_CB_RANGE,
    SKIN_CR_RANGE,
    SKIN_RATIO_MIN,
    WB_GAIN_MAX,
    WB_GAIN_MIN,
)
from facetrack.cv_pipeline import CVPipelineResult
from facetrack.db import REGION_LABELS_ZH

PoseMode = Literal["frontal", "profile_left", "profile_right"]


@dataclass
class CheckResult:
    """Outcome of a single quality check."""

    passed: bool
    measurement: dict[str, float]
    reason: str = ""


@dataclass
class QualityReport:
    """Aggregate report across all gate checks; serializable to JSON for the DB."""

    overall_passed: bool
    pose: CheckResult
    exposure: CheckResult
    sharpness: CheckResult
    lighting: CheckResult
    skin: CheckResult
    color: CheckResult
    summary_zh: str = ""
    failure_reasons_zh: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to plain dict suitable for json.dumps."""
        return asdict(self)


class ConsistencyGate:
    """The Photo-Consistency Gate. Stateless — safe to share across requests."""

    def __init__(
        self,
        pose_tolerance_deg: float = POSE_TOLERANCE_DEG,
        exposure_low_pct: float = EXPOSURE_LOW_PCT,
        exposure_high_pct: float = EXPOSURE_HIGH_PCT,
        sharpness_min_var: float = SHARPNESS_MIN_LAPLACIAN_VAR,
        profile_yaw_min_deg: float = PROFILE_YAW_MIN_DEG,
        profile_pitch_tolerance_deg: float = PROFILE_PITCH_TOLERANCE_DEG,
    ) -> None:
        self.pose_tolerance_deg = pose_tolerance_deg
        self.exposure_low_pct = exposure_low_pct
        self.exposure_high_pct = exposure_high_pct
        self.sharpness_min_var = sharpness_min_var
        self.profile_yaw_min_deg = profile_yaw_min_deg
        self.profile_pitch_tolerance_deg = profile_pitch_tolerance_deg
        self._aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_50)
        self._aruco_detector = cv2.aruco.ArucoDetector(self._aruco_dict)

    # -------- Public API --------

    def evaluate(
        self,
        image_bgr: np.ndarray,
        pipeline_result: CVPipelineResult,
        pose_mode: PoseMode = "frontal",
    ) -> tuple[QualityReport, np.ndarray]:
        """Run all four checks on a photo.

        Args:
            image_bgr: The original intake image (before alignment).
            pipeline_result: Output from FacePipeline.process(image_bgr).
            pose_mode: Which pose family to validate against —
                "frontal" (default, ±tolerance on yaw/pitch/roll),
                "profile_left" (yaw must be more negative than -profile_yaw_min_deg),
                "profile_right" (yaw must exceed +profile_yaw_min_deg).
                Roll is always checked against the frontal tolerance because the
                head should never tilt sideways, regardless of left/right rotation.

        Returns:
            Tuple of (QualityReport, calibrated_image).
            `calibrated_image` is the input with white-balance applied if a
            gray-card / ArUco marker was detected, otherwise unchanged.
        """
        face_crop = self._face_crop(pipeline_result)
        pose = self._check_pose(pipeline_result, pose_mode=pose_mode)
        exposure = self._check_exposure(image_bgr, face_crop)
        sharpness = self._check_sharpness(image_bgr, face_crop, pipeline_result)
        lighting = self._check_lighting(face_crop)
        skin = self._check_skin_visibility(pipeline_result)
        color, calibrated = self._check_and_calibrate_color(image_bgr)

        failure_reasons = [
            check.reason
            for check in (pose, exposure, sharpness, lighting, skin, color)
            if not check.passed and check.reason
        ]

        overall = (
            pose.passed and exposure.passed and sharpness.passed and lighting.passed and skin.passed
        )
        # Color failure (no marker detected) is a WARN, not a hard reject — many
        # clinics will adopt the marker later. We still report it.
        summary = (
            "通過：本張照片可作為縱向追蹤基準。" if overall else "未通過：請依下列原因重新拍攝。"
        )

        report = QualityReport(
            overall_passed=overall,
            pose=pose,
            exposure=exposure,
            sharpness=sharpness,
            lighting=lighting,
            skin=skin,
            color=color,
            summary_zh=summary,
            failure_reasons_zh=failure_reasons,
        )
        return report, calibrated

    # -------- Face crop shared by the exposure / sharpness / lighting checks --------

    @staticmethod
    def _face_crop(pipeline_result: CVPipelineResult) -> np.ndarray | None:
        """Face bounding-box crop from the pipeline's ALIGNED image.

        The aligned image is the coordinate frame the landmarks live in (and,
        since scale normalization, the only frame where landmark coordinates
        are valid). It is also scale-normalized, which makes the sharpness
        measurement resolution-invariant. Returns None when no usable face.
        """
        if not pipeline_result.face_detected or not pipeline_result.landmarks_px.size:
            return None
        image = pipeline_result.aligned_image
        pts = pipeline_result.landmarks_px
        x_min, y_min = pts.min(axis=0)
        x_max, y_max = pts.max(axis=0)
        h, w = image.shape[:2]
        x1 = max(0, int(x_min))
        y1 = max(0, int(y_min))
        x2 = min(w, int(x_max))
        y2 = min(h, int(y_max))
        if x2 - x1 < 32 or y2 - y1 < 32:
            return None
        return image[y1:y2, x1:x2]

    # -------- Pose --------

    def _check_pose(
        self,
        pipeline_result: CVPipelineResult,
        pose_mode: PoseMode = "frontal",
    ) -> CheckResult:
        if not pipeline_result.face_detected or pipeline_result.transformation_matrix is None:
            return CheckResult(
                passed=False,
                measurement={"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
                reason="未偵測到人臉。",
            )
        yaw, pitch, roll = self._euler_from_matrix(pipeline_result.transformation_matrix)

        if pose_mode == "frontal":
            tol = self.pose_tolerance_deg
            passed = abs(yaw) <= tol and abs(pitch) <= tol and abs(roll) <= tol
            reason = ""
            if not passed:
                parts: list[str] = []
                if abs(yaw) > tol:
                    parts.append(f"左右偏 {yaw:+.1f}°")
                if abs(pitch) > tol:
                    parts.append(f"上下偏 {pitch:+.1f}°")
                if abs(roll) > tol:
                    parts.append(f"頭部傾斜 {roll:+.1f}°")
                reason = (
                    "頭部姿勢超出容差（"
                    + "、".join(parts)
                    + f"，容差 ±{tol:.0f}°），請正對鏡頭重拍。"
                )
            return CheckResult(
                passed=passed,
                measurement={
                    "mode": "frontal",
                    "yaw_deg": round(yaw, 2),
                    "pitch_deg": round(pitch, 2),
                    "roll_deg": round(roll, 2),
                    "tolerance_deg": tol,
                },
                reason=reason,
            )

        # Profile modes: require strong yaw + modest pitch + level roll.
        yaw_min = self.profile_yaw_min_deg
        pitch_tol = self.profile_pitch_tolerance_deg
        roll_tol = self.pose_tolerance_deg
        side_label = "左" if pose_mode == "profile_left" else "右"
        yaw_ok = (yaw <= -yaw_min) if pose_mode == "profile_left" else (yaw >= yaw_min)
        pitch_ok = abs(pitch) <= pitch_tol
        roll_ok = abs(roll) <= roll_tol
        passed = yaw_ok and pitch_ok and roll_ok
        reason = ""
        if not passed:
            parts = []
            if not yaw_ok:
                parts.append(
                    f"請更明顯地轉向{side_label}側（目前 {yaw:+.1f}°，需 |yaw| ≥ {yaw_min:.0f}°）"
                )
            if not pitch_ok:
                parts.append(f"上下偏 {pitch:+.1f}°（容差 ±{pitch_tol:.0f}°）")
            if not roll_ok:
                parts.append(f"頭部傾斜 {roll:+.1f}°（容差 ±{roll_tol:.0f}°）")
            reason = f"側臉姿勢不正確：{'、'.join(parts)}。"
        return CheckResult(
            passed=passed,
            measurement={
                "mode": pose_mode,
                "yaw_deg": round(yaw, 2),
                "pitch_deg": round(pitch, 2),
                "roll_deg": round(roll, 2),
                "yaw_min_deg": yaw_min,
                "pitch_tolerance_deg": pitch_tol,
            },
            reason=reason,
        )

    @staticmethod
    def _euler_from_matrix(transform: np.ndarray) -> tuple[float, float, float]:
        """Extract yaw, pitch, roll (degrees) from MediaPipe 4x4 facial transform."""
        r = transform[:3, :3]
        sy = math.sqrt(r[0, 0] ** 2 + r[1, 0] ** 2)
        if sy > 1e-6:
            pitch = math.atan2(-r[2, 0], sy)
            yaw = math.atan2(r[1, 0], r[0, 0])
            roll = math.atan2(r[2, 1], r[2, 2])
        else:
            pitch = math.atan2(-r[2, 0], sy)
            yaw = 0.0
            roll = math.atan2(-r[1, 2], r[1, 1])
        return math.degrees(yaw), math.degrees(pitch), math.degrees(roll)

    # -------- Exposure --------

    def _check_exposure(
        self,
        image_bgr: np.ndarray,
        face_crop: np.ndarray | None = None,
    ) -> CheckResult:
        """Over/under-exposure check on the face crop (full-frame fallback).

        Measured on the face because that is the region the scorer consumes:
        a dark clinic wall must not reject a well-lit face, and a bright
        window behind the patient must not reject a correctly exposed one.
        """
        target = face_crop if face_crop is not None else image_bgr
        gray = cv2.cvtColor(target, cv2.COLOR_BGR2GRAY)
        total = gray.size
        low_pct = float(np.count_nonzero(gray < 10) / total)
        high_pct = float(np.count_nonzero(gray > 245) / total)
        mean = float(gray.mean())
        # On a face crop, pupils / eyebrows / nostrils are legitimately
        # near-black, so the clipped-shadow budget is looser than full-frame;
        # genuine underexposure trips the mean-brightness floor instead.
        low_limit = EXPOSURE_LOW_PCT_FACE if face_crop is not None else self.exposure_low_pct
        high_limit = EXPOSURE_HIGH_PCT_FACE if face_crop is not None else self.exposure_high_pct
        too_dark = low_pct > low_limit or mean < 60
        too_bright = high_pct > high_limit or mean > 210
        passed = not too_dark and not too_bright
        reason = ""
        scope = "臉部" if face_crop is not None else ""
        if too_dark:
            reason = f"{scope}曝光不足（暗部佔比 {low_pct * 100:.1f}%，平均亮度 {mean:.0f}/255）。"
        elif too_bright:
            reason = f"{scope}曝光過度（亮部佔比 {high_pct * 100:.1f}%，平均亮度 {mean:.0f}/255）。"
        return CheckResult(
            passed=passed,
            measurement={
                "mean_brightness": round(mean, 1),
                "underexposed_pixel_ratio": round(low_pct, 4),
                "overexposed_pixel_ratio": round(high_pct, 4),
                "measured_on": "face_crop" if face_crop is not None else "full_frame",
            },
            reason=reason,
        )

    # -------- Sharpness --------

    def _check_sharpness(
        self,
        image_bgr: np.ndarray,
        face_crop: np.ndarray | None = None,
        pipeline_result: CVPipelineResult | None = None,
    ) -> CheckResult:
        """Resolution-normalized Laplacian-variance focus check.

        Two-part: (a) the native face width must clear a floor — a face
        sampled below MIN_NATIVE_FACE_WIDTH_PX cannot carry comparable skin
        texture no matter how "sharp" it looks after normalization;
        (b) the crop is resized to a fixed width before measuring, so the
        threshold means the same thing for a 4K DSLR photo and a 720p
        webcam frame. (Unnormalized, the same face measures ~2.6x higher
        at half the pixel pitch — the old threshold had to be re-tuned
        every time the capture device changed.) Falls back to the full
        frame when no landmarks are present.
        """
        native_width = (
            pipeline_result.native_face_width_px
            if pipeline_result is not None and pipeline_result.face_detected
            else 0.0
        )
        if face_crop is not None and 0.0 < native_width < MIN_NATIVE_FACE_WIDTH_PX:
            return CheckResult(
                passed=False,
                measurement={
                    "native_face_width_px": round(native_width, 1),
                    "min_native_face_width_px": MIN_NATIVE_FACE_WIDTH_PX,
                    "measured_on": "face_crop",
                },
                reason=(
                    f"臉部影像過小（臉寬 {native_width:.0f}px，"
                    f"最低 {MIN_NATIVE_FACE_WIDTH_PX:.0f}px）。"
                    f"請靠近鏡頭或改用較高解析度拍攝。"
                ),
            )
        crop = face_crop if face_crop is not None else image_bgr
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        target_w = SHARPNESS_NORM_FACE_WIDTH_PX
        h, w = gray.shape[:2]
        if w != target_w:
            target_h = max(1, round(h * target_w / w))
            interp = cv2.INTER_AREA if target_w < w else cv2.INTER_LINEAR
            gray = cv2.resize(gray, (target_w, target_h), interpolation=interp)
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        passed = lap_var >= self.sharpness_min_var
        reason = ""
        if not passed:
            reason = (
                f"影像模糊（正規化 Laplacian 變異數 {lap_var:.1f}，"
                f"門檻 {self.sharpness_min_var:.0f}），請穩定持機重拍。"
            )
        measurement = {
            "laplacian_variance": round(lap_var, 2),
            "threshold": self.sharpness_min_var,
            "normalized_width_px": float(target_w),
            "measured_on": "face_crop" if face_crop is not None else "full_frame",
        }
        if native_width > 0.0:
            measurement["native_face_width_px"] = round(native_width, 1)
        return CheckResult(passed=passed, measurement=measurement, reason=reason)

    # -------- Lighting uniformity --------

    def _check_lighting(self, face_crop: np.ndarray | None) -> CheckResult:
        """Left/right brightness asymmetry on the face crop.

        A side-lit face passes every per-pixel exposure statistic yet
        systematically biases the left-cheek vs right-cheek comparison and
        inflates uniformity/pigmentation on the shadow side — the exact
        cross-visit noise this gate exists to block. Skipped (passes) when
        no face is available; the pose check already owns that failure.
        """
        if face_crop is None:
            return CheckResult(passed=True, measurement={"skipped": 1.0})
        gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        half = gray.shape[1] // 2
        if half == 0:
            return CheckResult(passed=True, measurement={"skipped": 1.0})
        left_mean = float(gray[:, :half].mean())
        right_mean = float(gray[:, half:].mean())
        asymmetry = abs(left_mean - right_mean) / max((left_mean + right_mean) / 2.0, 1.0)
        passed = asymmetry <= LIGHTING_ASYMMETRY_MAX
        reason = ""
        if not passed:
            brighter = "左" if left_mean > right_mean else "右"
            reason = (
                f"光照不均（{brighter}半臉較亮，左 {left_mean:.0f} vs 右 {right_mean:.0f}，"
                f"不對稱度 {asymmetry:.2f}，容差 {LIGHTING_ASYMMETRY_MAX:.2f}）。"
                f"請調整為正面均勻光源後重拍。"
            )
        return CheckResult(
            passed=passed,
            measurement={
                "left_mean_brightness": round(left_mean, 1),
                "right_mean_brightness": round(right_mean, 1),
                "asymmetry_ratio": round(asymmetry, 3),
                "threshold": LIGHTING_ASYMMETRY_MAX,
            },
            reason=reason,
        )

    # -------- Skin visibility (occlusion) --------

    def _check_skin_visibility(self, pipeline_result: CVPipelineResult) -> CheckResult:
        """Per-ROI skin-pixel ratio via a YCrCb skin-color band.

        MediaPipe happily reports landmarks over a surgical mask or
        sunglasses, so ROI extraction alone cannot tell fabric from skin —
        and the scorer would obediently score the fabric. Any ROI whose
        skin ratio falls below SKIN_RATIO_MIN rejects the photo, naming the
        occluded region. Skipped (passes) when no ROIs are available.
        """
        if not pipeline_result.face_detected or not pipeline_result.roi_bboxes:
            return CheckResult(passed=True, measurement={"skipped": 1.0})
        aligned = pipeline_result.aligned_image
        measurement: dict[str, float] = {}
        occluded_labels: list[str] = []
        for region, (x, y, w, h) in pipeline_result.roi_bboxes.items():
            crop = aligned[y : y + h, x : x + w]
            mask = pipeline_result.roi_masks.get(region)
            if crop.size == 0:
                continue
            ycrcb = cv2.cvtColor(crop, cv2.COLOR_BGR2YCrCb)
            cr = ycrcb[..., 1]
            cb = ycrcb[..., 2]
            skin = (
                (cr >= SKIN_CR_RANGE[0])
                & (cr <= SKIN_CR_RANGE[1])
                & (cb >= SKIN_CB_RANGE[0])
                & (cb <= SKIN_CB_RANGE[1])
            )
            if mask is not None and mask.shape == skin.shape:
                inside = mask.astype(bool)
                ratio = float(skin[inside].mean()) if inside.any() else 0.0
            else:
                ratio = float(skin.mean())
            measurement[f"skin_ratio_{region.value}"] = round(ratio, 3)
            if ratio < SKIN_RATIO_MIN:
                occluded_labels.append(REGION_LABELS_ZH.get(region, region.value))
        if not measurement:
            return CheckResult(passed=True, measurement={"skipped": 1.0})
        measurement["min_skin_ratio"] = min(
            v for k, v in measurement.items() if k.startswith("skin_ratio_")
        )
        measurement["threshold"] = SKIN_RATIO_MIN
        passed = not occluded_labels
        reason = ""
        if not passed:
            reason = (
                f"偵測到遮擋：{('、'.join(occluded_labels))}區域皮膚可見度不足"
                f"（門檻 {SKIN_RATIO_MIN:.0%}）。請移除口罩／墨鏡／頭髮遮擋後重拍。"
            )
        return CheckResult(passed=passed, measurement=measurement, reason=reason)

    # -------- Color calibration via ArUco gray-card --------

    def _check_and_calibrate_color(self, image_bgr: np.ndarray) -> tuple[CheckResult, np.ndarray]:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = self._aruco_detector.detectMarkers(gray)
        if ids is None or len(ids) == 0:
            return (
                CheckResult(
                    passed=False,
                    measurement={"marker_detected": 0.0},
                    reason="未偵測到色彩校正標記（ArUco gray card）— 已使用未校正影像評分，建議拍攝時將灰卡置於人臉旁。",
                ),
                image_bgr,
            )

        # Use the first detected marker; sample the patch immediately around it
        # (clinic-issued cards have a known-gray surround printed around the marker).
        marker_corners = corners[0].reshape(-1, 2)
        x_min, y_min = marker_corners.min(axis=0).astype(int)
        x_max, y_max = marker_corners.max(axis=0).astype(int)
        marker_w = max(8, x_max - x_min)
        marker_h = max(8, y_max - y_min)
        # Expand outward to grab the printed gray border around the marker
        h, w = image_bgr.shape[:2]
        pad_x = marker_w // 2
        pad_y = marker_h // 2
        bx1 = max(0, x_min - pad_x)
        by1 = max(0, y_min - pad_y)
        bx2 = min(w, x_max + pad_x)
        by2 = min(h, y_max + pad_y)
        border = image_bgr[by1:by2, bx1:bx2].astype(np.float32)
        # Mask out the marker itself
        mask = np.ones((by2 - by1, bx2 - bx1), dtype=bool)
        mx1 = x_min - bx1
        my1 = y_min - by1
        mx2 = x_max - bx1
        my2 = y_max - by1
        mask[my1:my2, mx1:mx2] = False
        sampled = border[mask]
        if sampled.size == 0:
            return (
                CheckResult(
                    passed=False,
                    measurement={"marker_detected": 1.0, "sample_size": 0.0},
                    reason="偵測到色彩標記但取樣失敗，使用未校正影像。",
                ),
                image_bgr,
            )
        avg_bgr = sampled.reshape(-1, 3).mean(axis=0)  # [B, G, R]
        avg_gray = float(avg_bgr.mean())
        raw_gains = avg_gray / np.clip(avg_bgr, 1.0, None)  # per-channel scale to neutral gray
        # Clamp: a mis-sampled card (glare on the gray surround, marker on a
        # colored sleeve) must not recolor the face harder than plausible
        # clinic lighting — runaway gains would corrupt the erythema (a*)
        # metric worse than skipping calibration entirely.
        gains = np.clip(raw_gains, WB_GAIN_MIN, WB_GAIN_MAX)
        gains_clamped = bool(np.any(gains != raw_gains))
        calibrated = np.clip(image_bgr.astype(np.float32) * gains, 0, 255).astype(np.uint8)
        return (
            CheckResult(
                passed=True,
                measurement={
                    "marker_detected": 1.0,
                    "sample_b": round(float(avg_bgr[0]), 1),
                    "sample_g": round(float(avg_bgr[1]), 1),
                    "sample_r": round(float(avg_bgr[2]), 1),
                    "gain_b": round(float(gains[0]), 3),
                    "gain_g": round(float(gains[1]), 3),
                    "gain_r": round(float(gains[2]), 3),
                    "gains_clamped": 1.0 if gains_clamped else 0.0,
                },
                reason="",
            ),
            calibrated,
        )


_default_gate: ConsistencyGate | None = None


def get_gate() -> ConsistencyGate:
    """Return a shared ConsistencyGate instance (lazy-initialized)."""
    global _default_gate
    if _default_gate is None:
        _default_gate = ConsistencyGate()
    return _default_gate

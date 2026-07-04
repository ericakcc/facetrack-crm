"""Behavioural contract for the Photo-Consistency Gate.

The depth-area module. These tests make sure that the gate actually
rejects the failure modes its 繁中 reason strings claim it catches —
otherwise the demo will silently pass garbage.

Each test fabricates a minimal pathological image (no MediaPipe call
required for exposure / sharpness / color) so the suite stays fast
and offline-runnable in CI.
"""

from __future__ import annotations

import numpy as np

from facetrack.consistency_gate import ConsistencyGate
from facetrack.cv_pipeline import CVPipelineResult


def _no_face_result() -> CVPipelineResult:
    """A pipeline result indicating MediaPipe found no face.

    Pose check should fail with "未偵測到人臉"; the image-level
    checks (exposure / sharpness / color) still execute against
    the raw pixels.
    """
    return CVPipelineResult.no_face()


def _solid_image(value: int, size: int = 512) -> np.ndarray:
    """A flat BGR image at a fixed gray level."""
    return np.full((size, size, 3), value, dtype=np.uint8)


def _mid_gray_image_with_face_passable_brightness(size: int = 512) -> np.ndarray:
    """Mid-tone gray with structured texture so exposure/sharpness checks pass."""
    rng = np.random.default_rng(0)
    base = rng.integers(110, 160, size=(size, size, 3), dtype=np.uint8)
    return base


def test_underexposed_image_is_rejected_with_specific_reason() -> None:
    """A nearly-black image must fail the exposure check with a 繁中 reason."""
    gate = ConsistencyGate()
    img = _solid_image(value=5)  # well below mean threshold of 60
    report, _ = gate.evaluate(img, _no_face_result())

    assert report.exposure.passed is False
    assert "曝光不足" in report.exposure.reason
    assert report.overall_passed is False
    assert any("曝光不足" in r for r in report.failure_reasons_zh)


def test_overexposed_image_is_rejected_with_specific_reason() -> None:
    """A nearly-white image must fail the exposure check from the other side."""
    gate = ConsistencyGate()
    img = _solid_image(value=252)
    report, _ = gate.evaluate(img, _no_face_result())

    assert report.exposure.passed is False
    assert "曝光過度" in report.exposure.reason
    assert report.overall_passed is False


def test_blurry_image_is_rejected_by_sharpness() -> None:
    """A heavily blurred image must trip the Laplacian-variance threshold."""
    import cv2

    gate = ConsistencyGate()
    img = _mid_gray_image_with_face_passable_brightness()
    blurred = cv2.GaussianBlur(img, (51, 51), 25)
    report, _ = gate.evaluate(blurred, _no_face_result())

    assert report.sharpness.passed is False
    assert "模糊" in report.sharpness.reason
    assert report.overall_passed is False


def test_missing_face_fails_pose_check() -> None:
    """A pipeline result with no face must trigger the pose-check failure path."""
    gate = ConsistencyGate()
    img = _mid_gray_image_with_face_passable_brightness()
    report, _ = gate.evaluate(img, _no_face_result())

    assert report.pose.passed is False
    assert "未偵測到人臉" in report.pose.reason


def test_color_check_warns_when_no_aruco_marker_detected() -> None:
    """Without an ArUco marker, color check fails but is a soft warning (graceful degradation)."""
    gate = ConsistencyGate()
    img = _mid_gray_image_with_face_passable_brightness()
    report, calibrated = gate.evaluate(img, _no_face_result())

    assert report.color.passed is False
    assert "ArUco" in report.color.reason or "色彩校正" in report.color.reason
    # Calibrated image equals input when no marker is found.
    assert np.array_equal(calibrated, img)


def test_overall_passed_requires_pose_and_exposure_and_sharpness() -> None:
    """Color is a soft warning, but pose/exposure/sharpness are hard requirements."""
    gate = ConsistencyGate()
    # Synthetic image fails pose (no face) regardless of other checks.
    img = _mid_gray_image_with_face_passable_brightness()
    report, _ = gate.evaluate(img, _no_face_result())

    # Even though exposure and sharpness pass on this image, pose fails
    # because there is no face — so overall must be False.
    assert report.exposure.passed is True
    assert report.sharpness.passed is True
    assert report.pose.passed is False
    assert report.overall_passed is False


def _yaw_only_matrix(yaw_deg: float) -> np.ndarray:
    """Build a 4x4 facial-transform matrix with pure yaw, zero pitch/roll.

    Matches the convention in ConsistencyGate._euler_from_matrix:
        yaw   = atan2(r[1,0], r[0,0])
        pitch = atan2(-r[2,0], sqrt(r[0,0]^2 + r[1,0]^2))
        roll  = atan2(r[2,1], r[2,2])
    so a Z-axis rotation by theta gives the desired yaw=theta, pitch=0, roll=0.
    """
    import math

    theta = math.radians(yaw_deg)
    m = np.eye(4, dtype=np.float32)
    m[0, 0] = math.cos(theta)
    m[0, 1] = -math.sin(theta)
    m[1, 0] = math.sin(theta)
    m[1, 1] = math.cos(theta)
    return m


def _pipeline_result_with_pose(yaw_deg: float) -> CVPipelineResult:
    return CVPipelineResult(
        aligned_image=np.zeros((10, 10, 3), dtype=np.uint8),
        landmarks_px=np.zeros((0, 2), dtype=np.float32),
        transformation_matrix=_yaw_only_matrix(yaw_deg),
        face_detected=True,
    )


def test_pose_mode_frontal_passes_at_zero_yaw() -> None:
    """A perfectly centred head must pass the frontal pose check."""
    gate = ConsistencyGate()
    img = _mid_gray_image_with_face_passable_brightness()
    report, _ = gate.evaluate(img, _pipeline_result_with_pose(0.0), pose_mode="frontal")
    assert report.pose.passed is True


def test_pose_mode_profile_left_passes_at_strong_negative_yaw() -> None:
    """yaw = -70° should satisfy the profile_left mode (threshold -55°)."""
    gate = ConsistencyGate()
    img = _mid_gray_image_with_face_passable_brightness()
    report, _ = gate.evaluate(img, _pipeline_result_with_pose(-70.0), pose_mode="profile_left")
    assert report.pose.passed is True
    assert report.pose.measurement["mode"] == "profile_left"


def test_pose_mode_profile_left_rejects_frontal_pose() -> None:
    """A frontal photo must NOT pass when profile_left is requested."""
    gate = ConsistencyGate()
    img = _mid_gray_image_with_face_passable_brightness()
    report, _ = gate.evaluate(img, _pipeline_result_with_pose(0.0), pose_mode="profile_left")
    assert report.pose.passed is False
    assert "轉向左側" in report.pose.reason


def test_pose_mode_profile_right_passes_at_strong_positive_yaw() -> None:
    """yaw = +65° should satisfy the profile_right mode."""
    gate = ConsistencyGate()
    img = _mid_gray_image_with_face_passable_brightness()
    report, _ = gate.evaluate(img, _pipeline_result_with_pose(65.0), pose_mode="profile_right")
    assert report.pose.passed is True
    assert report.pose.measurement["mode"] == "profile_right"


def test_quality_report_serialises_to_json_compatible_dict() -> None:
    """QualityReport.to_dict() must round-trip through json.dumps for DB storage."""
    import json

    gate = ConsistencyGate()
    img = _mid_gray_image_with_face_passable_brightness()
    report, _ = gate.evaluate(img, _no_face_result())

    payload = report.to_dict()
    # Should not raise — this is what app.py writes into Visit.quality_report_json.
    serialized = json.dumps(payload, ensure_ascii=False, default=str)
    assert "pose" in serialized
    assert "exposure" in serialized
    assert "sharpness" in serialized
    assert "color" in serialized
    assert "lighting" in serialized
    assert "skin" in serialized


# -------- Gate v2: face-crop exposure --------


def _result_with_landmark_box(
    aligned: np.ndarray, x1: int, y1: int, x2: int, y2: int
) -> CVPipelineResult:
    """A pipeline result whose landmarks span the given box on `aligned`.

    The gate's face-crop checks (exposure / sharpness / lighting) read from
    the pipeline's aligned image — the frame the landmark coordinates and
    the scorer's ROIs live in.
    """
    pts = np.array(
        [[x1, y1], [x2, y1], [x1, y2], [x2, y2]],
        dtype=np.float32,
    )
    return CVPipelineResult(
        aligned_image=aligned,
        landmarks_px=pts,
        face_detected=True,
    )


def test_exposure_measured_on_face_crop_when_landmarks_present() -> None:
    """A well-lit face on a dark clinic background must pass exposure.

    Full-frame measurement rejects this photo (dark wall dominates pixel
    count); the metric that matters for skin scoring is the face itself.
    """
    gate = ConsistencyGate()
    img = np.full((512, 512, 3), 5, dtype=np.uint8)  # dark background
    img[100:400, 100:400] = 170  # well-lit face region
    report, _ = gate.evaluate(img, _result_with_landmark_box(img, 100, 100, 400, 400))

    assert report.exposure.passed is True
    assert report.exposure.measurement["measured_on"] == "face_crop"


def test_exposure_face_crop_overexposed_is_rejected() -> None:
    """A blown-out face must fail exposure even when the background is fine."""
    gate = ConsistencyGate()
    img = np.full((512, 512, 3), 128, dtype=np.uint8)
    img[100:400, 100:400] = 252  # clipped face
    report, _ = gate.evaluate(img, _result_with_landmark_box(img, 100, 100, 400, 400))

    assert report.exposure.passed is False
    assert "曝光過度" in report.exposure.reason


# -------- Gate v2: lighting uniformity --------


def test_lighting_asymmetry_is_rejected() -> None:
    """A side-lit face (one half bright, one half dark) corrupts the
    left-cheek vs right-cheek comparison and must be rejected."""
    gate = ConsistencyGate()
    img = np.full((512, 512, 3), 128, dtype=np.uint8)
    img[100:400, 100:250] = 210  # bright left half of face
    img[100:400, 250:400] = 70  # shadowed right half
    report, _ = gate.evaluate(img, _result_with_landmark_box(img, 100, 100, 400, 400))

    assert report.lighting.passed is False
    assert "光照不均" in report.lighting.reason
    assert report.overall_passed is False


def test_lighting_uniform_face_passes() -> None:
    """Evenly lit face passes the lighting-uniformity check."""
    gate = ConsistencyGate()
    img = np.full((512, 512, 3), 5, dtype=np.uint8)
    img[100:400, 100:400] = 160
    report, _ = gate.evaluate(img, _result_with_landmark_box(img, 100, 100, 400, 400))

    assert report.lighting.passed is True


def test_lighting_check_skipped_without_face() -> None:
    """No landmarks -> lighting check is skipped (pose already fails)."""
    gate = ConsistencyGate()
    img = _mid_gray_image_with_face_passable_brightness()
    report, _ = gate.evaluate(img, _no_face_result())

    assert report.lighting.passed is True
    assert report.lighting.measurement.get("skipped") == 1.0


# -------- Gate v2: resolution-normalized sharpness --------


def test_sharpness_is_resolution_invariant() -> None:
    """The same face content at 1x and 2x pixel density must yield (near-)
    identical sharpness measurements after normalization — the threshold must
    not depend on which camera took the photo."""
    import cv2

    gate = ConsistencyGate()
    rng = np.random.default_rng(5)
    base = rng.integers(90, 190, size=(256, 256, 3), dtype=np.uint8)
    big = cv2.resize(base, (512, 512), interpolation=cv2.INTER_NEAREST)

    report_base, _ = gate.evaluate(base, _result_with_landmark_box(base, 0, 0, 256, 256))
    report_big, _ = gate.evaluate(big, _result_with_landmark_box(big, 0, 0, 512, 512))

    var_base = report_base.sharpness.measurement["laplacian_variance"]
    var_big = report_big.sharpness.measurement["laplacian_variance"]
    assert report_base.sharpness.passed is True
    assert report_big.sharpness.passed is True
    assert abs(var_base - var_big) / max(var_base, 1e-6) < 0.05


# -------- Gate v2: skin-visibility (occlusion) --------

SKIN_BGR = (120, 160, 210)  # plausible skin tone, inside the YCrCb skin band
FABRIC_BGR = (200, 140, 80)  # surgical-mask blue, far outside the skin band


def _result_with_rois(roi_colors: dict) -> CVPipelineResult:
    """Pipeline result with one 64x64 ROI per region, filled with a solid color."""

    aligned = np.full((300, 300, 3), SKIN_BGR, dtype=np.uint8)
    bboxes = {}
    masks = {}
    x = 10
    for region, color in roi_colors.items():
        aligned[10:74, x : x + 64] = color
        bboxes[region] = (x, 10, 64, 64)
        masks[region] = np.full((64, 64), 255, dtype=np.uint8)
        x += 70
    pts = np.array([[0, 0], [300, 0], [0, 300], [300, 300]], dtype=np.float32)
    return CVPipelineResult(
        aligned_image=aligned,
        landmarks_px=pts,
        face_detected=True,
        roi_bboxes=bboxes,
        roi_masks=masks,
    )


def test_skin_visibility_rejects_occluded_roi() -> None:
    """A chin ROI full of mask fabric must be rejected, naming the region."""
    from facetrack.db import Region

    gate = ConsistencyGate()
    result = _result_with_rois({Region.LEFT_CHEEK: SKIN_BGR, Region.CHIN: FABRIC_BGR})
    img = np.full((512, 512, 3), 150, dtype=np.uint8)
    report, _ = gate.evaluate(img, result)

    assert report.skin.passed is False
    assert "遮擋" in report.skin.reason
    assert "下巴" in report.skin.reason
    assert report.overall_passed is False


def test_skin_visibility_passes_on_real_skin_tones() -> None:
    """All-skin ROIs pass the visibility check."""
    from facetrack.db import Region

    gate = ConsistencyGate()
    result = _result_with_rois({Region.LEFT_CHEEK: SKIN_BGR, Region.CHIN: SKIN_BGR})
    img = np.full((512, 512, 3), 150, dtype=np.uint8)
    report, _ = gate.evaluate(img, result)

    assert report.skin.passed is True


def test_skin_visibility_skipped_without_rois() -> None:
    """No ROIs (no face) -> skin check is skipped, pose carries the failure."""
    gate = ConsistencyGate()
    img = _mid_gray_image_with_face_passable_brightness()
    report, _ = gate.evaluate(img, _no_face_result())

    assert report.skin.passed is True
    assert report.skin.measurement.get("skipped") == 1.0


# -------- Gate v2: white-balance gain clamp --------


def test_white_balance_gains_are_clamped() -> None:
    """An extreme color cast must not produce runaway per-channel gains —
    a mis-sampled gray card would otherwise recolor the face and corrupt
    the erythema (a*) metric more than no calibration at all."""
    import cv2

    from facetrack.config import WB_GAIN_MAX, WB_GAIN_MIN

    gate = ConsistencyGate()
    # Strong blue cast background with a real ArUco marker embedded.
    img = np.full((400, 400, 3), (200, 80, 40), dtype=np.uint8)
    marker = cv2.aruco.generateImageMarker(
        cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_50), 1, 100
    )
    img[150:250, 150:250] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    report, calibrated = gate.evaluate(img, _no_face_result())

    if report.color.measurement.get("marker_detected") == 1.0:
        for key in ("gain_b", "gain_g", "gain_r"):
            gain = report.color.measurement[key]
            assert WB_GAIN_MIN <= gain <= WB_GAIN_MAX, f"{key}={gain} outside clamp"

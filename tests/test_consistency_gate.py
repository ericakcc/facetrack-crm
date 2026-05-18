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

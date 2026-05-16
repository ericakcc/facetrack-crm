"""End-to-end pipeline latency benchmark.

Numbers reported here back the "what does this cost in production?"
claim in TDD §6. Runs the full intake pipeline (alignment → gate →
scoring) on every available test face N times each and prints
per-stage p50 / p95 latency in milliseconds.

The explainer stage is excluded because it is the only network call
in the loop — measured separately under "Explainer cost" in TDD §6
based on Anthropic's published Sonnet 4.6 latency.

Run::

    uv run python scripts/benchmark.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from statistics import mean

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from facetrack.consistency_gate import get_gate  # noqa: E402
from facetrack.cv_pipeline import get_pipeline  # noqa: E402
from facetrack.scoring import aggregate_face_scores, score_visit  # noqa: E402

TEST_DIR = PROJECT_ROOT / "data" / "test_images"
RUNS_PER_FACE = 5


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int(round((len(sorted_vals) - 1) * pct))
    return sorted_vals[idx]


def main() -> int:
    faces = sorted(TEST_DIR.glob("test_face_*.jpg"))
    if not faces:
        print(f"ERROR: no test faces under {TEST_DIR}", file=sys.stderr)
        return 1

    pipeline = get_pipeline()
    gate = get_gate()

    timings: dict[str, list[float]] = {
        "pipeline_ms": [],
        "gate_ms": [],
        "scoring_ms": [],
        "total_ms": [],
    }

    # Warm-up run — first MediaPipe inference allocates buffers and
    # would skew p50 otherwise.
    warmup = cv2.imread(str(faces[0]))
    _ = pipeline.process(warmup)

    print(f"Benchmarking on {len(faces)} faces, {RUNS_PER_FACE} runs each...\n")
    for face in faces:
        img = cv2.imread(str(face))
        if img is None:
            continue
        for _ in range(RUNS_PER_FACE):
            t0 = time.perf_counter()
            result = pipeline.process(img)
            t1 = time.perf_counter()
            report, _ = gate.evaluate(img, result)
            t2 = time.perf_counter()
            if result.face_detected and result.rois:
                _ = aggregate_face_scores(score_visit(result.rois))
            t3 = time.perf_counter()

            timings["pipeline_ms"].append((t1 - t0) * 1000)
            timings["gate_ms"].append((t2 - t1) * 1000)
            timings["scoring_ms"].append((t3 - t2) * 1000)
            timings["total_ms"].append((t3 - t0) * 1000)

    print(f"{'stage':<14}{'mean':>8}{'p50':>8}{'p95':>8}  (ms)")
    print("-" * 44)
    for stage, vals in timings.items():
        print(
            f"{stage:<14}"
            f"{mean(vals):>8.1f}"
            f"{percentile(vals, 0.50):>8.1f}"
            f"{percentile(vals, 0.95):>8.1f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

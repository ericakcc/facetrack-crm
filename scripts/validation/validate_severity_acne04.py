"""Known-groups validation of the erythema & texture metrics on ACNE04.

ACNE04 (Wu et al., ICCV 2019) ships 1,457 face photos graded 0-3 on the Hayashi
severity scale by dermatologists. We have no per-lesion ground truth for our
metrics, but we have a strong *ordinal* prior: as acne severity rises, an
inflammatory-redness metric (`erythema_raw`, mean a*) and a texture metric
(`wrinkle_raw` / `pore_raw`, high-frequency density) should rise monotonically.

This is a known-groups construct-validity test. It answers: do the metrics move
in the clinically expected direction across independent dermatologist grades?
A flat or non-monotone curve means the metric is not measuring what we claim.

Reports, per metric, the grade-0→3 means, the Spearman rank correlation of the
metric vs grade across all images, and a rank-biserial effect size for the
grade-0 vs grade-3 contrast (how cleanly the mildest and most severe groups
separate).

Usage:
    uv run python scripts/validation/validate_severity_acne04.py

Reads   data/validation/acne04/acne{0,1,2,3}_1024/*.jpg
Writes  data/validation/acne04/results/{acne_per_image.csv, acne_severity_trend.png}
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from facetrack.config import NORMALIZED_FACE_WIDTH_PX  # noqa: E402
from facetrack.scoring import erythema_raw, pore_raw, wrinkle_raw  # noqa: E402

DATA = REPO / "data" / "validation" / "acne04"
RESULTS = DATA / "results"
SIDE = int(NORMALIZED_FACE_WIDTH_PX)
GRADES = [0, 1, 2, 3]
METRICS = {
    "erythema_raw": erythema_raw,
    "wrinkle_raw": wrinkle_raw,
    "pore_raw": pore_raw,
}


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    rx = np.argsort(np.argsort(x)).astype(np.float64)
    ry = np.argsort(np.argsort(y)).astype(np.float64)
    x_, y_ = rx - rx.mean(), ry - ry.mean()
    denom = np.sqrt((x_ * x_).sum() * (y_ * y_).sum())
    return float((x_ * y_).sum() / denom) if denom else 0.0


def rank_biserial(a: np.ndarray, b: np.ndarray) -> float:
    """Effect size for a<b separation: P(b>a) - P(a>b), in [-1, 1]."""
    wins = ties = 0
    for bv in b:
        wins += int((bv > a).sum())
        ties += int((bv == a).sum())
    total = len(a) * len(b)
    gt = wins / total
    lt = (total - wins - ties) / total
    return gt - lt


def run_validation() -> dict[str, Any]:
    """Run the ACNE04 known-groups validation and return summary statistics.

    Returns:
        Dict with keys: n, n_by_grade ({grade: count}), metrics
        ({name: {"means": [grade0..grade3], "rho": float,
        "rank_biserial": float, "monotone": bool}}), rows (per-image
        tuples of (grade, filename, {metric: value})).

    Raises:
        FileNotFoundError: No ACNE04 images are downloaded.
    """
    rows: list[tuple[int, str, dict[str, float]]] = []
    for g in GRADES:
        folder = DATA / f"acne{g}_1024"
        files = sorted(folder.glob("*.jpg")) + sorted(folder.glob("*.png"))
        if not files:
            print(f"(warning: no images in {folder})")
            continue
        for fp in files:
            bgr = cv2.imread(str(fp))
            if bgr is None:
                continue
            bgr = cv2.resize(bgr, (SIDE, SIDE), interpolation=cv2.INTER_AREA)
            vals = {name: float(fn(bgr)) for name, fn in METRICS.items()}
            rows.append((g, fp.name, vals))
    if not rows:
        raise FileNotFoundError(f"No ACNE04 images under {DATA}. See data/validation/README.md.")

    grades = np.array([r[0] for r in rows])
    metrics_summary: dict[str, dict[str, Any]] = {}
    for m in METRICS:
        series = np.array([r[2][m] for r in rows])
        means = [float(series[grades == g].mean()) for g in GRADES]
        metrics_summary[m] = {
            "means": means,
            "rho": spearman(grades.astype(float), series),
            "rank_biserial": rank_biserial(series[grades == 0], series[grades == 3]),
            "monotone": means == sorted(means),
        }

    return {
        "n": len(rows),
        "n_by_grade": {g: int((grades == g).sum()) for g in GRADES},
        "metrics": metrics_summary,
        "rows": rows,
    }


def main() -> None:
    """CLI entry point: run the validation, write CSV/plot artifacts, print report."""
    try:
        res = run_validation()
    except FileNotFoundError as e:
        sys.exit(str(e))

    RESULTS.mkdir(exist_ok=True)
    print(f"Loaded {res['n']} graded faces  {res['n_by_grade']}\n")

    with (RESULTS / "acne_per_image.csv").open("w") as f:
        f.write("grade,file," + ",".join(METRICS) + "\n")
        for g, name, vals in res["rows"]:
            f.write(f"{g},{name}," + ",".join(f"{vals[m]:.6f}" for m in METRICS) + "\n")

    print(
        f"{'metric':14s}  "
        + "  ".join(f"grade{g}" for g in GRADES)
        + "   Spearman   rank-biserial(0 vs 3)"
    )
    for m, s in res["metrics"].items():
        arrow = "monotone↑" if s["monotone"] else "NON-MONOTONE"
        print(
            f"{m:14s}  "
            + "  ".join(f"{v:6.3f}" for v in s["means"])
            + f"   rho={s['rho']:+.3f}   rb={s['rank_biserial']:+.3f}   {arrow}"
        )

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, len(METRICS), figsize=(4 * len(METRICS), 4), dpi=120)
        for ax, m in zip(axes, METRICS, strict=True):
            ax.plot(GRADES, res["metrics"][m]["means"], "o-", color="#c05621")
            ax.set_title(m)
            ax.set_xlabel("Hayashi severity grade")
            ax.set_xticks(GRADES)
        axes[0].set_ylabel("metric value (mean)")
        fig.suptitle("ACNE04 known-groups: metric vs dermatologist severity")
        fig.tight_layout()
        fig.savefig(RESULTS / "acne_severity_trend.png")
        print(f"\nWrote {RESULTS}/acne_per_image.csv + acne_severity_trend.png")
    except Exception as e:  # noqa: BLE001
        print(f"\n(trend plot skipped: {e})")


if __name__ == "__main__":
    main()

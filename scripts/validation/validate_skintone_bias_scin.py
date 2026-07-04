"""Skin-tone fairness audit of the gate's YCrCb skin-visibility check (SCIN).

The gate rejects a photo when the fraction of pixels inside a fixed YCrCb skin
band (Cr∈SKIN_CR_RANGE, Cb∈SKIN_CB_RANGE) drops below SKIN_RATIO_MIN — the
"put your mask/sunglasses away" check. LIMITATIONS §4 flags the risk that this
band, tuned on lighter skin, under-counts very dark skin (Fitzpatrick V-VI):
melanin drops luminance and compresses chroma, so a fixed Cr/Cb box can read
real dark skin as "occluded" and wrongfully reject the patient.

This script quantifies that bias using SCIN (Google/Stanford, ~5k dermatology
photos with self-reported Fitzpatrick type). For a Fitzpatrick-stratified
sample it recomputes the gate's exact skin band per image, then reports, per
type: mean skin ratio, simulated pass-rate at SKIN_RATIO_MIN, and mean
luminance (the mechanism). A pass-rate that falls from FST1→FST6 is the bias,
measured — the offline signal for widening/adapting the band.

Note: SCIN images are body-part close-ups, not aligned faces, so we measure the
whole-image skin ratio as a band-coverage proxy rather than running the full
ROI pipeline. The Cr/Cb band under test is identical to production.

Usage:
    uv run python scripts/validation/validate_skintone_bias_scin.py

Reads   data/validation/scin/{scin_sample_manifest.csv, images/*.png}
Writes  data/validation/scin/results/{skintone_bias.csv, skintone_bias.png}
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from facetrack.config import (  # noqa: E402
    SKIN_CB_RANGE,
    SKIN_CR_RANGE,
    SKIN_RATIO_MIN,
)

DATA = REPO / "data" / "validation" / "scin"
IMAGES = DATA / "images"
RESULTS = DATA / "results"
TYPES = ["FST1", "FST2", "FST3", "FST4", "FST5", "FST6"]


def skin_ratio(bgr: np.ndarray) -> tuple[float, float]:
    """Return (fraction inside the gate's YCrCb skin band, mean luminance)."""
    ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
    y, cr, cb = ycrcb[..., 0], ycrcb[..., 1], ycrcb[..., 2]
    skin = (
        (cr >= SKIN_CR_RANGE[0])
        & (cr <= SKIN_CR_RANGE[1])
        & (cb >= SKIN_CB_RANGE[0])
        & (cb <= SKIN_CB_RANGE[1])
    )
    return float(skin.mean()), float(y.mean())


def run_validation() -> dict[str, Any]:
    """Run the SCIN skin-tone fairness audit and return summary statistics.

    Returns:
        Dict with keys: n, summary (per-type tuples of (fst, n, mean_ratio,
        pass_rate, mean_luma); NaN stats when a type has no images),
        pass_rate_fst12 / pass_rate_fst56 (group mean pass rates, None when
        a group is empty), pass_gap (fst12 - fst56; positive = darker skin
        rejected more; None when either group is empty), rows (per-image
        tuples of (fst, filename, skin_ratio, mean_luma, passes)).

    Raises:
        FileNotFoundError: The sample manifest is missing.
        RuntimeError: The manifest exists but no images were readable.
    """
    manifest = DATA / "scin_sample_manifest.csv"
    if not manifest.exists():
        raise FileNotFoundError(
            f"No manifest at {manifest}. Run data/validation/scin/sample_download_scin.py first."
        )

    by_type: dict[str, list[tuple[float, float]]] = defaultdict(list)
    rows: list[tuple[str, str, float, float, int]] = []
    for row in csv.DictReader(manifest.open()):
        fst = row["fitzpatrick"]
        img = IMAGES / row["file"]
        if fst not in TYPES or not img.exists():
            continue
        bgr = cv2.imread(str(img))
        if bgr is None:
            continue
        ratio, lum = skin_ratio(bgr)
        by_type[fst].append((ratio, lum))
        rows.append((fst, row["file"], ratio, lum, int(ratio >= SKIN_RATIO_MIN)))

    if not rows:
        raise RuntimeError(f"No SCIN images found under {IMAGES}.")

    summary: list[tuple[str, int, float, float, float]] = []
    for fst in TYPES:
        vals = by_type.get(fst, [])
        if not vals:
            summary.append((fst, 0, float("nan"), float("nan"), float("nan")))
            continue
        ratios = np.array([v[0] for v in vals])
        lums = np.array([v[1] for v in vals])
        pass_rate = float((ratios >= SKIN_RATIO_MIN).mean())
        summary.append((fst, len(vals), float(ratios.mean()), pass_rate, float(lums.mean())))

    light = [s for s in summary if s[0] in ("FST1", "FST2") and s[1]]
    dark = [s for s in summary if s[0] in ("FST5", "FST6") and s[1]]
    lp = float(np.mean([s[3] for s in light])) if light else None
    dp = float(np.mean([s[3] for s in dark])) if dark else None

    return {
        "n": len(rows),
        "summary": summary,
        "pass_rate_fst12": lp,
        "pass_rate_fst56": dp,
        "pass_gap": lp - dp if lp is not None and dp is not None else None,
        "rows": rows,
    }


def main() -> None:
    """CLI entry point: run the audit, write CSV/plot artifacts, print report."""
    try:
        res = run_validation()
    except (FileNotFoundError, RuntimeError) as e:
        sys.exit(str(e))

    RESULTS.mkdir(exist_ok=True)
    with (RESULTS / "skintone_bias.csv").open("w") as f:
        f.write("fitzpatrick,file,skin_ratio,mean_luma,passes_gate\n")
        for fst, name, ratio, lum, ok in res["rows"]:
            f.write(f"{fst},{name},{ratio:.4f},{lum:.1f},{ok}\n")

    print(
        f"Gate skin band: Cr∈{SKIN_CR_RANGE}, Cb∈{SKIN_CB_RANGE}, "
        f"pass if ratio ≥ {SKIN_RATIO_MIN:.0%}\n"
    )
    print(f"{'type':6s}   n   mean_ratio   pass_rate   mean_luma")
    for fst, n, mean_ratio, pass_rate, mean_luma in res["summary"]:
        if not n:
            print(f"{fst:6s}   0        —           —          —")
            continue
        print(f"{fst:6s}  {n:3d}   {mean_ratio:9.3f}   {pass_rate:8.1%}   {mean_luma:7.1f}")

    if res["pass_gap"] is not None:
        lp, dp, gap = res["pass_rate_fst12"], res["pass_rate_fst56"], res["pass_gap"]
        print(f"\n    Pass-rate  FST1-2 = {lp:.1%}   FST5-6 = {dp:.1%}   gap = {gap:+.1%}")
        verdict = (
            "BIAS CONFIRMED (dark skin rejected more)"
            if gap > 0.1
            else "no large gap at this sample"
        )
        print(
            f"    → {verdict}. Tune SKIN_CR_RANGE/SKIN_CB_RANGE or add "
            "luminance-adaptive skin detection (LIMITATIONS §4)."
        )

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plot_rows = [s for s in res["summary"] if s[1]]
        fig, ax = plt.subplots(figsize=(7, 4), dpi=120)
        ax.bar([s[0] for s in plot_rows], [s[3] * 100 for s in plot_rows], color="#805ad5")
        ax.axhline(100, ls="--", lw=0.8, color="#888")
        ax.set_ylabel("Simulated gate pass-rate (%)")
        ax.set_title("SCIN skin-tone bias: gate pass-rate by Fitzpatrick type")
        ax.set_ylim(0, 105)
        fig.tight_layout()
        fig.savefig(RESULTS / "skintone_bias.png")
        print(f"\nWrote {RESULTS}/skintone_bias.csv + skintone_bias.png")
    except Exception as e:  # noqa: BLE001
        print(f"\n(plot skipped: {e})")


if __name__ == "__main__":
    main()

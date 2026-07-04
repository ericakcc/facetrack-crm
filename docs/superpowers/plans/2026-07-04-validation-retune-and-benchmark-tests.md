# Wrinkle Range Retune + Validation Benchmark Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the FFHQ-derived `WRINKLE_RAW_RANGE` retune (0.25, 0.75) → (0.20, 0.62) and turn the three one-off validation scripts into an opt-in pytest regression layer (`pytest -m validation`).

**Architecture:** Each script under `scripts/validation/` gets a pure `run_validation() -> dict` function (computation only); the CLI `main()` keeps all printing/CSV/plot output by calling it. A new `tests/test_validation_benchmarks.py` imports those functions via module-scoped fixtures and asserts ground-truth thresholds. A pytest marker + `addopts` filter keeps the 92 fast tests unchanged by default.

**Tech Stack:** Python 3.11, uv, pytest, ruff, OpenCV, numpy, matplotlib (plots only). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-04-validation-retune-and-benchmark-tests-design.md`

## Global Constraints

- **uv only** — `uv run pytest`, `uv run ruff`, `uv run python`. Never pip.
- **Before every commit**: `uv run ruff check . --fix && uv run ruff format .` then verify `uv run ruff check . && uv run ruff format --check .` is clean.
- **Type hints + Google-style docstrings** on every new/refactored function. English-only code, comments, commit messages.
- **Conventional Commits** (`feat`, `fix`, `docs`, `refactor`, `test`, `chore`). Never `git commit --no-verify`. Never push.
- **Repo non-negotiables** (from `CLAUDE.md` §7): scoring stays deterministic and LLM-free; no real-person pixels enter git (verify staged files in Tasks 1–2); `SCORING_VERSION` stays **2** (v2 was never deployed; the retune folds into v2 — do NOT bump to 3).
- **Working directory**: `/Users/eric_tsou/collab/AIFound/facetrack-crm` (run all commands from here).
- **Slow steps are expected**: any command that touches the full FFHQ set (1,000 faces through MediaPipe) takes ~10–20 minutes. Do not assume a hang; do not add `--limit` to full verification runs.

---

### Task 1: Commit Session 4 work (git only, no code changes)

The working tree contains two uncommitted bodies of work on top of `2f6beae`. Land Session 4 (Gate v2 + Scoring v2 + docs + capture scripts) first, excluding the Session-5 validation harness paths.

**Files:**
- No file edits. Git staging only.

**Interfaces:**
- Consumes: current working tree.
- Produces: a commit containing everything except `.gitignore`, `data/validation/`, `scripts/validation/`.

- [ ] **Step 1: Confirm the baseline and test state**

Run: `git log --oneline -1 && uv run pytest tests/ -q 2>&1 | tail -1`
Expected: HEAD is `dfd337e` (spec commit) or later; `92 passed`.

- [ ] **Step 2: Stage everything except the Session-5 harness**

```bash
git add -A
git reset .gitignore data/validation scripts/validation
```

- [ ] **Step 3: Verify no real-person pixels and no harness files are staged**

Run: `git diff --cached --name-only | grep -E '^(data/validation|scripts/validation)|\.gitignore$'`
Expected: no output (exit code 1 from grep is the success case).

Run: `git diff --cached --stat | tail -3`
Expected: a summary listing app/src/tests/docs/scripts files only.

- [ ] **Step 4: Commit Session 4**

```bash
git commit -m "feat: gate v2 (6 checks) + scoring v2 (512px scale-norm, SCORING_VERSION)

Session 4 hardening: face-crop exposure, resolution-normalized sharpness
with a native-width floor, lighting-uniformity, skin-visibility, and WB
gain clamp checks; scoring on specular/shadow effective masks at a
normalized 512px face scale; per-visit scoring_version persisted with a
legacy migration. 71 -> 92 tests. Also: demo/pitch asset scripts and
docs/PROGRESS.md.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 5: Verify the commit**

Run: `git status --short`
Expected: only `?? data/validation/`, `?? scripts/validation/`, ` M .gitignore` remain.

---

### Task 2: Commit Session 5 validation harness (git only)

**Files:**
- No file edits. Git staging only.

**Interfaces:**
- Consumes: remaining unstaged paths from Task 1.
- Produces: a commit with `.gitignore` + `data/validation/**` (tracked subset) + `scripts/validation/**`.

- [ ] **Step 1: Stage the harness**

```bash
git add .gitignore data/validation scripts/validation
```

- [ ] **Step 2: Verify only reproducible artifacts are staged (no dataset pixels)**

Run: `git diff --cached --name-only | grep -E 'ffhq_wrinkle/images/|manual_wrinkle_masks/|acne04/acne[0-3]_1024/|scin/images/'`
Expected: no output (the `.gitignore` block keeps raw images/masks local).

Run: `git diff --cached --name-only | head -20`
Expected: `.gitignore`, `data/validation/README.md`, manifests/CSVs, `results/*.csv`, `results/*.png`, fetch scripts, and `scripts/validation/*.py`.

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(validation): real-data harness (FFHQ-Wrinkle, ACNE04, SCIN)

Download/sampling scripts, ID manifests, and validation scripts that grade
the production wrinkle metric (FFHQ-Wrinkle masks, n=1000), erythema
construct validity (ACNE04 dermatologist grades), and gate skin-tone
fairness (SCIN Fitzpatrick-stratified sample) against ground truth.
Real-person pixels stay local (gitignored); only scripts, manifests, and
aggregate result CSV/PNG are tracked.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 4: Verify clean tree**

Run: `git status --short`
Expected: empty output.

---

### Task 3: Refactor FFHQ wrinkle validator to expose `run_validation()`

Pure refactor, no behavior change: move the computation out of `main()` into a callable that returns summary statistics; `main()` keeps argument parsing, CSV writing, printing, and plotting.

**Files:**
- Modify: `scripts/validation/validate_wrinkle_ffhq.py` (currently: `main()` at lines 128–278 does everything)

**Interfaces:**
- Consumes: existing module-level helpers `spearman`, `pearson`, `firing_map`, `normalize_to_face_width`, `roi_union`, and constants `IMAGES`, `MASKS`, `RESULTS`, `MASK_DILATE_PX`.
- Produces (Tasks 4–5 rely on this exact contract):
  - `DEFAULT_THRESHOLDS: tuple[float, ...] = (15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 50.0, 60.0)`
  - `run_validation(limit: int | None = None, thresholds: Sequence[float] = DEFAULT_THRESHOLDS) -> dict[str, Any]` with keys:
    `n` (int), `n_detect_fail` (int), `roi_spearman`, `roi_pearson`, `whole_spearman`, `whole_pearson` (float), `raw_p5`, `raw_p95` (float), `rows` (list of `(ffhq_id, wrinkle_raw_roi, gt_density_roi, wrinkle_raw_whole, gt_density_whole)`), `sweep` (list of `(cutoff, precision, recall, f1)`), `best_cutoff` (float), `best_f1` (float).
  - Raises `FileNotFoundError` when masks are missing, `RuntimeError` when no face was usable.

- [ ] **Step 1: Add the new imports**

In `scripts/validation/validate_wrinkle_ffhq.py`, extend the stdlib import block (after `import argparse` / `import sys` / `from pathlib import Path`):

```python
from collections.abc import Sequence
from typing import Any
```

(Ruff will place them correctly on `ruff check --fix`; `Sequence`/`Any` are stdlib so they belong in the top import block, before the `sys.path.insert` line.)

- [ ] **Step 2: Replace `main()` with `run_validation()` + a thin `main()`**

Delete the entire current `main()` (from `def main() -> None:` down to its final `except` block, lines 128–278) and insert in its place:

```python
DEFAULT_THRESHOLDS: tuple[float, ...] = (15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 50.0, 60.0)


def run_validation(
    limit: int | None = None,
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
) -> dict[str, Any]:
    """Run the FFHQ-Wrinkle validation and return summary statistics.

    Args:
        limit: Cap the number of processed faces (None = all available).
        thresholds: Sobel cutoffs to sweep for the localization report.

    Returns:
        Dict with keys: n, n_detect_fail, roi_spearman, roi_pearson,
        whole_spearman, whole_pearson, raw_p5, raw_p95, rows (per-image
        tuples of (ffhq_id, wrinkle_raw_roi, gt_density_roi,
        wrinkle_raw_whole, gt_density_whole)), sweep (per-cutoff tuples of
        (cutoff, precision, recall, f1)), best_cutoff, best_f1.

    Raises:
        FileNotFoundError: No masks are downloaded.
        RuntimeError: No face produced usable landmarks/ROIs.
    """
    pipeline = FacePipeline()
    mask_ids = sorted(p.stem for p in MASKS.glob("*.png"))
    if not mask_ids:
        raise FileNotFoundError(f"No masks under {MASKS}. See data/validation/README.md.")

    kernel = np.ones((MASK_DILATE_PX * 2 + 1,) * 2, np.uint8)
    roi_metric, roi_gt, whole_metric, whole_gt = [], [], [], []
    rows: list[tuple[str, float, float, float, float]] = []
    tp = {t: 0 for t in thresholds}
    fp = {t: 0 for t in thresholds}
    fn = {t: 0 for t in thresholds}
    n_detect_fail = 0
    n_done = 0

    for fid in mask_ids:
        img_path = IMAGES / f"{fid}.webp"
        if not img_path.exists():
            continue
        bgr = cv2.imread(str(img_path))
        mask = cv2.imread(str(MASKS / f"{fid}.png"), cv2.IMREAD_GRAYSCALE)
        if bgr is None or mask is None:
            continue

        landmarks, _ = pipeline._detect(bgr)  # noqa: SLF001 (validation reuse)
        if landmarks is None:
            n_detect_fail += 1
            continue
        norm = normalize_to_face_width(bgr, mask > 0, landmarks)
        if norm is None:
            n_detect_fail += 1
            continue
        img, msk, lm = norm
        union = roi_union(pipeline, lm, img.shape)
        if union is None or not union.any():
            n_detect_fail += 1
            continue

        # Production scores the CLAHE-normalized crop, so measure on the same:
        # CLAHE raises local contrast and hence Sobel magnitudes, so the raw
        # values here are directly comparable to WRINKLE_RAW_RANGE / cutoff=30.
        norm_img = pipeline._normalize_lighting(img)  # noqa: SLF001 (validation reuse)

        # Q1: production metric (ROI) and whole-face contrast
        m_roi = float(wrinkle_raw(norm_img, (union.astype(np.uint8) * 255)))
        m_whole = float(wrinkle_raw(norm_img))
        d_roi = float(msk[union].mean())
        d_whole = float(msk.mean())
        roi_metric.append(m_roi)
        roi_gt.append(d_roi)
        whole_metric.append(m_whole)
        whole_gt.append(d_whole)
        rows.append((fid, m_roi, d_roi, m_whole, d_whole))

        # Q2: localization inside ROI union
        gt_dil = cv2.dilate(msk.astype(np.uint8), kernel).astype(bool)
        gt_line = msk
        for t in thresholds:
            fire = firing_map(norm_img, t) & union
            tp[t] += int((fire & gt_dil).sum())
            fp[t] += int((fire & ~gt_dil).sum())
            fn[t] += int((~fire & gt_line & union).sum())

        n_done += 1
        if limit and n_done >= limit:
            break
        if n_done % 200 == 0:
            print(f"  ...{n_done} faces processed", flush=True)

    if not rows:
        raise RuntimeError("No usable faces (detection failed on all). Check the download.")

    roi_metric_a = np.array(roi_metric)
    roi_gt_a = np.array(roi_gt)
    whole_metric_a = np.array(whole_metric)
    whole_gt_a = np.array(whole_gt)
    lo, hi = np.percentile(roi_metric_a, [5, 95])

    sweep: list[tuple[float, float, float, float]] = []
    best: tuple[float, float] = (float(thresholds[0]), -1.0)
    for t in thresholds:
        prec = tp[t] / (tp[t] + fp[t]) if tp[t] + fp[t] else 0.0
        rec = tp[t] / (tp[t] + fn[t]) if tp[t] + fn[t] else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        sweep.append((t, prec, rec, f1))
        if f1 > best[1]:
            best = (t, f1)

    return {
        "n": n_done,
        "n_detect_fail": n_detect_fail,
        "roi_spearman": spearman(roi_metric_a, roi_gt_a),
        "roi_pearson": pearson(roi_metric_a, roi_gt_a),
        "whole_spearman": spearman(whole_metric_a, whole_gt_a),
        "whole_pearson": pearson(whole_metric_a, whole_gt_a),
        "raw_p5": float(lo),
        "raw_p95": float(hi),
        "rows": rows,
        "sweep": sweep,
        "best_cutoff": best[0],
        "best_f1": best[1],
    }


def main() -> None:
    """CLI entry point: run the validation, write CSV/plot artifacts, print report."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, help="cap number of images (default all)")
    ap.add_argument(
        "--thresholds",
        type=str,
        default=",".join(f"{t:g}" for t in DEFAULT_THRESHOLDS),
        help="comma-separated Sobel cutoffs to sweep",
    )
    args = ap.parse_args()
    thresholds = [float(t) for t in args.thresholds.split(",")]

    try:
        res = run_validation(limit=args.limit, thresholds=thresholds)
    except (FileNotFoundError, RuntimeError) as e:
        sys.exit(str(e))

    RESULTS.mkdir(exist_ok=True)
    with (RESULTS / "wrinkle_per_image.csv").open("w") as f:
        f.write("ffhq_id,wrinkle_raw_roi,gt_density_roi,wrinkle_raw_whole,gt_density_whole\n")
        for fid, mr, dr, mw, dw in res["rows"]:
            f.write(f"{fid},{mr:.6f},{dr:.6f},{mw:.6f},{dw:.6f}\n")

    print(f"\nProcessed {res['n']} faces ({res['n_detect_fail']} skipped: no face / no ROI).\n")
    print("Q1  Ranking validity  (per-face wrinkle_raw vs human mask coverage)")
    print(
        f"    skin ROIs   Spearman rho = {res['roi_spearman']:+.3f}   "
        f"Pearson r = {res['roi_pearson']:+.3f}   ← production behavior"
    )
    print(
        f"    whole face  Spearman rho = {res['whole_spearman']:+.3f}   "
        f"Pearson r = {res['whole_pearson']:+.3f}   (contrast: eyes/hair contaminate)"
    )
    print(
        f"    wrinkle_raw(ROI) p5-p95 = [{res['raw_p5']:.3f}, {res['raw_p95']:.3f}]   "
        f"current WRINKLE_RAW_RANGE = {WRINKLE_RAW_RANGE}"
    )
    print()

    print("Q2  Localization / cutoff tuning  (firing pixels vs masks, inside skin ROIs)")
    print("    cutoff   precision   recall      F1")
    for t, prec, rec, f1 in res["sweep"]:
        print(f"    {t:6.0f}   {prec:8.3f}   {rec:7.3f}   {f1:6.3f}")

    with (RESULTS / "wrinkle_threshold_sweep.csv").open("w") as f:
        f.write("sobel_cutoff,precision,recall,f1\n")
        for t, p, rc, f1 in res["sweep"]:
            f.write(f"{t},{p:.6f},{rc:.6f},{f1:.6f}\n")
    print(
        f"\n    → F1-max cutoff = {res['best_cutoff']:.0f} (F1={res['best_f1']:.3f}); "
        "wrinkle_raw hard-codes 30 (scoring.py)."
    )

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        roi_gt_a = np.array([r[2] for r in res["rows"]])
        roi_metric_a = np.array([r[1] for r in res["rows"]])
        fig, ax = plt.subplots(figsize=(6, 5), dpi=120)
        ax.scatter(roi_gt_a * 100, roi_metric_a, s=8, alpha=0.4, color="#2b6cb0")
        ax.set_xlabel("Human wrinkle coverage inside skin ROIs (%)")
        ax.set_ylabel("wrinkle_raw (ROI Sobel firing ratio)")
        ax.set_title(f"FFHQ-Wrinkle · n={res['n']} · Spearman ρ={res['roi_spearman']:.2f}")
        fig.tight_layout()
        fig.savefig(RESULTS / "wrinkle_scatter.png")
        print(f"\nWrote results to {RESULTS}/")
    except Exception as e:  # noqa: BLE001
        print(f"\n(scatter plot skipped: {e})")
```

Keep everything above the old `main()` (docstring, imports, helpers) unchanged, and keep the trailing `if __name__ == "__main__": main()` block.

- [ ] **Step 3: Lint and smoke-run on a 40-face subset (~1 min)**

```bash
uv run ruff check scripts/validation/ --fix && uv run ruff format scripts/validation/
uv run python scripts/validation/validate_wrinkle_ffhq.py --limit 40
```

Expected: the Q1/Q2 report prints (rho values on 40 faces will differ from the full-run numbers — that is fine), `data/validation/ffhq_wrinkle/results/` files are rewritten, exit code 0.

- [ ] **Step 4: Restore the full-run result CSVs (the 40-face smoke run overwrote them)**

```bash
git checkout -- data/validation/ffhq_wrinkle/results/
git status --short
```

Expected: only `scripts/validation/validate_wrinkle_ffhq.py` modified.

- [ ] **Step 5: Run the fast suite and commit**

```bash
uv run pytest tests/ -q 2>&1 | tail -1
git add scripts/validation/validate_wrinkle_ffhq.py
git commit -m "refactor(validation): expose run_validation() from FFHQ wrinkle validator

Computation moves into a callable returning summary stats; the CLI keeps
CSV/plot/report output. No behavior change. Prepares the pytest
benchmark layer.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

Expected: `92 passed`.

---

### Task 4: pytest marker config + FFHQ benchmark tests (RED)

Write the FFHQ benchmark tests first. The rank-correlation test passes today; the range-calibration test **fails against the current (0.25, 0.75) range** — that failure is the driving red for Task 5's retune. No commit in this task (the tree is intentionally red).

**Files:**
- Modify: `pyproject.toml:46-48` (`[tool.pytest.ini_options]`)
- Create: `tests/test_validation_benchmarks.py`

**Interfaces:**
- Consumes: `validate_wrinkle_ffhq.run_validation()` (Task 3 contract), `facetrack.scoring.WRINKLE_RAW_RANGE`.
- Produces: the `validation` pytest marker and the `ffhq_result` module fixture; Tasks 6–7 append their fixtures/tests to this same file.

- [ ] **Step 1: Register the marker and exclude it from default runs**

In `pyproject.toml`, replace:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short"
```

with:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short -m 'not validation'"
markers = [
    "validation: real-data ground-truth benchmarks; needs data/validation/ downloads (run: uv run pytest -m validation)",
]
```

(A later `-m` on the command line overrides the one in `addopts`, so `uv run pytest -m validation` runs exactly the benchmark tests.)

- [ ] **Step 2: Create `tests/test_validation_benchmarks.py` with the FFHQ tests**

```python
"""Ground-truth benchmark tests — opt-in via `uv run pytest -m validation`.

Turns the offline validators under scripts/validation/ into a regression
net: if a CV/scoring change breaks ground-truth alignment, these fail.
Thresholds are the Session-5 measured values minus a safety margin
(FFHQ ROI Spearman rho measured 0.42; real-face wrinkle_raw p5-p95
measured [0.197, 0.619]).

The datasets hold real-person pixels and are therefore gitignored; each
fixture skips with re-download instructions (data/validation/README.md)
when its dataset is absent. Module-scoped fixtures mean each dataset is
processed once per run — the FFHQ fixture takes ~10-20 minutes.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts" / "validation"))

import validate_wrinkle_ffhq  # noqa: E402

from facetrack.scoring import WRINKLE_RAW_RANGE  # noqa: E402

DATA = REPO / "data" / "validation"
RANGE_ENDPOINT_TOL = 0.05

pytestmark = pytest.mark.validation


@pytest.fixture(scope="module")
def ffhq_result() -> dict[str, Any]:
    """Full FFHQ-Wrinkle validation summary (skips when data is absent)."""
    masks = DATA / "ffhq_wrinkle" / "manual_wrinkle_masks"
    if not any(masks.glob("*.png")):
        pytest.skip("FFHQ-Wrinkle not downloaded — see data/validation/README.md")
    return validate_wrinkle_ffhq.run_validation()


def test_wrinkle_roi_ranking_tracks_human_annotations(ffhq_result: dict[str, Any]) -> None:
    """ROI-restricted wrinkle_raw must rank faces like the hand-drawn masks do."""
    assert ffhq_result["n"] >= 800, "partial FFHQ download — refetch before trusting stats"
    assert ffhq_result["roi_spearman"] >= 0.35, (
        f"ROI Spearman rho {ffhq_result['roi_spearman']:.3f} < 0.35 — "
        "wrinkle ranking no longer tracks ground truth (Session-5 baseline: 0.42)"
    )


def test_wrinkle_range_matches_real_face_distribution(ffhq_result: dict[str, Any]) -> None:
    """WRINKLE_RAW_RANGE endpoints must sit on the real-face p5/p95.

    A too-wide range silently kills the top/bottom of the 0-10 scale
    (scores clamp-saturate); this pins the config to the measured
    distribution within +/-0.05.
    """
    lo, hi = WRINKLE_RAW_RANGE
    assert abs(lo - ffhq_result["raw_p5"]) <= RANGE_ENDPOINT_TOL, (
        f"range low {lo} vs measured p5 {ffhq_result['raw_p5']:.3f}"
    )
    assert abs(hi - ffhq_result["raw_p95"]) <= RANGE_ENDPOINT_TOL, (
        f"range high {hi} vs measured p95 {ffhq_result['raw_p95']:.3f}"
    )
```

- [ ] **Step 3: Verify the default suite is untouched**

Run: `uv run pytest tests/ -q 2>&1 | tail -1`
Expected: `92 passed, 2 deselected` (the two new tests are deselected by the `addopts` marker filter).

- [ ] **Step 4: Run the benchmark tests to verify the expected RED (~10–20 min)**

Run: `uv run pytest -m validation 2>&1 | tail -15`
Expected:
- `test_wrinkle_roi_ranking_tracks_human_annotations` **PASSED**
- `test_wrinkle_range_matches_real_face_distribution` **FAILED** with `range high 0.75 vs measured p95` ≈ `0.619` — this is the miscalibration the retune fixes. If instead the *rank* test fails or the measured p95 is not ≈0.62, STOP and report: the data or pipeline differs from Session 5.

- [ ] **Step 5: Lint (no commit — red is resolved in Task 5)**

```bash
uv run ruff check tests/ pyproject.toml --fix && uv run ruff format tests/
```

Expected: clean.

---

### Task 5: Apply the retune (GREEN) and commit tests + retune together

**Files:**
- Modify: `src/facetrack/scoring.py:65-77` (range comment block + `WRINKLE_RAW_RANGE`)
- Commit also picks up: `pyproject.toml`, `tests/test_validation_benchmarks.py` (from Task 4)

**Interfaces:**
- Consumes: the red test from Task 4.
- Produces: `WRINKLE_RAW_RANGE = (0.20, 0.62)` — consumed by `score_region` and the benchmark test.

- [ ] **Step 1: Retune the constant and document its new provenance**

In `src/facetrack/scoring.py`, replace:

```python
# Empirical raw-metric ranges, calibrated on the 5 evenly-lit reference
# faces in data/test_images at the v2 normalization scale (every face
# rescaled to NORMALIZED_FACE_WIDTH_PX = 512 before ROI extraction, so the
# ranges are stable across camera resolution and subject distance).
# Wrinkle/pore shifted upward vs v1 because texture-density ratios grow at
# the smaller sampling scale (fixed 3x3/5x5 kernels cover relatively larger
# anatomy); pigmentation/erythema/uniformity distributions were unchanged.
# Re-calibrate when a clinic provides its own training distribution.
PIGMENTATION_RAW_RANGE = (0.02, 0.30)
ERYTHEMA_RAW_RANGE = (134.0, 148.0)
WRINKLE_RAW_RANGE = (0.25, 0.75)
```

with:

```python
# Empirical raw-metric ranges, calibrated on the 5 evenly-lit reference
# faces in data/test_images at the v2 normalization scale (every face
# rescaled to NORMALIZED_FACE_WIDTH_PX = 512 before ROI extraction, so the
# ranges are stable across camera resolution and subject distance).
# Wrinkle/pore shifted upward vs v1 because texture-density ratios grow at
# the smaller sampling scale (fixed 3x3/5x5 kernels cover relatively larger
# anatomy); pigmentation/erythema/uniformity distributions were unchanged.
# Wrinkle was then re-fitted against FFHQ-Wrinkle ground truth (n=1000,
# ROI-restricted, CLAHE-matched): real-face p5-p95 = [0.197, 0.619], so the
# reference-face (0.25, 0.75) ceiling was never reached and the top of the
# 0-10 scale was dead range. Guarded by tests/test_validation_benchmarks.py.
# Re-calibrate when a clinic provides its own training distribution.
PIGMENTATION_RAW_RANGE = (0.02, 0.30)
ERYTHEMA_RAW_RANGE = (134.0, 148.0)
WRINKLE_RAW_RANGE = (0.20, 0.62)
```

- [ ] **Step 2: Run the fast suite — nothing may regress**

Run: `uv run pytest tests/ -q 2>&1 | tail -1`
Expected: `92 passed, 2 deselected`.

Contingency: the only test with headroom sensitivity is `tests/test_pipeline_scale.py:99` (`max cross-resolution drift < 1.5`; the narrower range scales wrinkle drift by 0.50/0.42 ≈ 1.19×, projected worst case ≈1.25). If it fails, do NOT raise the threshold — STOP and report the measured drift to Eric; that would be a real finding about the retune.

- [ ] **Step 3: Run the benchmark tests to verify GREEN (~10–20 min)**

Run: `uv run pytest -m validation 2>&1 | tail -5`
Expected: `2 passed` (both FFHQ tests).

- [ ] **Step 4: Lint and commit Tasks 4+5 together**

```bash
uv run ruff check . --fix && uv run ruff format .
uv run ruff check . && uv run ruff format --check .
git add src/facetrack/scoring.py tests/test_validation_benchmarks.py pyproject.toml
git commit -m "feat(scoring): retune WRINKLE_RAW_RANGE to FFHQ ground-truth p5-p95

(0.25, 0.75) -> (0.20, 0.62). FFHQ-Wrinkle (n=1000, ROI-restricted,
CLAHE-matched to production) measures real-face wrinkle_raw p5-p95 =
[0.197, 0.619]; the old 0.75 ceiling was never reached, so scores above
~7.4 were unreachable dead range. SCORING_VERSION stays 2 (v2 was never
deployed; no persisted v2 scores exist).

Adds the opt-in ground-truth benchmark layer (pytest -m validation):
ROI rank-correlation floor (rho >= 0.35) and range-endpoint calibration
(+/-0.05 of measured p5/p95). Default `pytest tests/` is unchanged.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: ACNE04 — refactor + known-groups benchmark tests

**Files:**
- Modify: `scripts/validation/validate_severity_acne04.py` (currently: `main()` at lines 70–135)
- Modify: `tests/test_validation_benchmarks.py` (append fixture + 2 tests)

**Interfaces:**
- Consumes: module helpers `spearman`, `rank_biserial`, constants `DATA`, `RESULTS`, `GRADES`, `METRICS`, `SIDE`.
- Produces: `run_validation() -> dict[str, Any]` with keys:
  `n` (int), `n_by_grade` (dict[int, int]), `metrics` (dict: metric name → `{"means": list[float], "rho": float, "rank_biserial": float, "monotone": bool}`), `rows` (list of `(grade, filename, {metric: value})`). Raises `FileNotFoundError` when no images exist.

- [ ] **Step 1: Write the failing tests — append to `tests/test_validation_benchmarks.py`**

Add `import validate_severity_acne04  # noqa: E402` to the script-import block (alphabetically first, before `validate_wrinkle_ffhq`), then append:

```python
@pytest.fixture(scope="module")
def acne_result() -> dict[str, Any]:
    """Full ACNE04 known-groups validation summary (skips when data is absent)."""
    if not (DATA / "acne04" / "acne0_1024").exists():
        pytest.skip("ACNE04 not downloaded — see data/validation/README.md")
    return validate_severity_acne04.run_validation()


def test_erythema_rises_with_acne_severity(acne_result: dict[str, Any]) -> None:
    """Construct validity: redness must climb with dermatologist severity grades."""
    assert acne_result["n"] >= 300, "partial ACNE04 download — refetch before trusting stats"
    rho = acne_result["metrics"]["erythema_raw"]["rho"]
    assert rho > 0.15, (
        f"erythema-vs-severity Spearman rho {rho:.3f} <= 0.15 — "
        "construct validity lost (Session-5 baseline: 0.23)"
    )


def test_texture_metrics_stay_flat_across_acne_severity(acne_result: dict[str, Any]) -> None:
    """Discriminant validity: texture metrics must NOT fire on inflammation."""
    for metric in ("wrinkle_raw", "pore_raw"):
        rho = acne_result["metrics"][metric]["rho"]
        assert abs(rho) < 0.10, (
            f"{metric} correlates with acne severity (rho {rho:+.3f}) — "
            "texture metric is picking up inflammation, not texture"
        )
```

- [ ] **Step 2: Run to verify they fail (missing function)**

Run: `uv run pytest -m validation -k acne 2>&1 | tail -5`
Expected: 2 errors — `AttributeError: module 'validate_severity_acne04' has no attribute 'run_validation'`.

- [ ] **Step 3: Refactor the script**

In `scripts/validation/validate_severity_acne04.py`, add `from typing import Any` to the stdlib import block, then delete the current `main()` (lines 70–135) and insert:

```python
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
```

Keep the module docstring, imports, helpers, and the `if __name__ == "__main__": main()` block unchanged.

- [ ] **Step 4: Run the ACNE04 benchmark tests (~1–3 min)**

Run: `uv run pytest -m validation -k acne 2>&1 | tail -3`
Expected: `2 passed`.

- [ ] **Step 5: Verify the CLI still works, restore results, lint, run fast suite, commit**

```bash
uv run python scripts/validation/validate_severity_acne04.py
git checkout -- data/validation/acne04/results/
uv run ruff check . --fix && uv run ruff format .
uv run pytest tests/ -q 2>&1 | tail -1
git add scripts/validation/validate_severity_acne04.py tests/test_validation_benchmarks.py
git commit -m "test(validation): ACNE04 known-groups benchmark (construct + discriminant)

erythema_raw must rise with dermatologist severity (rho > 0.15;
Session-5: 0.23); wrinkle/pore must stay flat (|rho| < 0.10) so texture
metrics don't fire on inflammation. Validator refactored to expose
run_validation(); CLI output unchanged.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

Expected: CLI prints the known-groups table (grade0 ≈ 136.4 → grade3 ≈ 139.7 for erythema), fast suite `92 passed, 4 deselected`.

---

### Task 7: SCIN — refactor + gate fairness benchmark test

**Files:**
- Modify: `scripts/validation/validate_skintone_bias_scin.py` (currently: `main()` at lines 66–151)
- Modify: `tests/test_validation_benchmarks.py` (append fixture + 1 test)

**Interfaces:**
- Consumes: module helper `skin_ratio`, constants `DATA`, `IMAGES`, `RESULTS`, `TYPES`, config `SKIN_RATIO_MIN`.
- Produces: `run_validation() -> dict[str, Any]` with keys:
  `n` (int), `summary` (list of `(fst, n, mean_ratio, pass_rate, mean_luma)`, NaN stats for empty types), `pass_rate_fst12` (float | None), `pass_rate_fst56` (float | None), `pass_gap` (float | None; fst12 − fst56, positive = darker skin rejected more), `rows` (per-image `(fst, filename, skin_ratio, mean_luma, passes)`). Raises `FileNotFoundError` (no manifest) / `RuntimeError` (manifest but no images).

- [ ] **Step 1: Write the failing test — append to `tests/test_validation_benchmarks.py`**

Add `import validate_skintone_bias_scin  # noqa: E402` to the script-import block (between the acne04 and wrinkle imports, keeping alphabetical order), then append:

```python
@pytest.fixture(scope="module")
def scin_result() -> dict[str, Any]:
    """Full SCIN fairness-audit summary (skips when data is absent)."""
    if not (DATA / "scin" / "scin_sample_manifest.csv").exists():
        pytest.skip("SCIN sample not downloaded — see data/validation/README.md")
    return validate_skintone_bias_scin.run_validation()


def test_gate_skin_check_has_no_large_skintone_gap(scin_result: dict[str, Any]) -> None:
    """Fairness: the YCrCb skin check must pass dark and light skin alike."""
    assert scin_result["n"] >= 300, "partial SCIN download — refetch before trusting stats"
    gap = scin_result["pass_gap"]
    assert gap is not None, "missing FST1-2 or FST5-6 samples — cannot audit bias"
    assert abs(gap) <= 0.05, (
        f"gate pass-rate gap FST1-2 vs FST5-6 = {gap:+.1%} exceeds 5pp — "
        "skin-tone bias regression (Session-5 baseline: -1.7pp)"
    )
```

- [ ] **Step 2: Run to verify it fails (missing function)**

Run: `uv run pytest -m validation -k scin 2>&1 | tail -5`
Expected: 1 error — `AttributeError: module 'validate_skintone_bias_scin' has no attribute 'run_validation'`.

- [ ] **Step 3: Refactor the script**

In `scripts/validation/validate_skintone_bias_scin.py`, add `from typing import Any` to the stdlib import block, then delete the current `main()` (lines 66–151) and insert:

```python
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
```

Keep the module docstring, imports, `skin_ratio`, and the `if __name__ == "__main__": main()` block unchanged.

- [ ] **Step 4: Run the SCIN benchmark test (~seconds)**

Run: `uv run pytest -m validation -k scin 2>&1 | tail -3`
Expected: `1 passed`.

- [ ] **Step 5: Verify the CLI still works, restore results, lint, run fast suite, commit**

```bash
uv run python scripts/validation/validate_skintone_bias_scin.py
git checkout -- data/validation/scin/results/
uv run ruff check . --fix && uv run ruff format .
uv run pytest tests/ -q 2>&1 | tail -1
git add scripts/validation/validate_skintone_bias_scin.py tests/test_validation_benchmarks.py
git commit -m "test(validation): SCIN gate skin-tone fairness benchmark

|FST1-2 minus FST5-6 pass-rate gap| must stay <= 5pp (Session-5
measured: -1.7pp, darker skin slightly HIGHER). Validator refactored to
expose run_validation(); CLI output unchanged.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

Expected: CLI prints the per-FST table with `gap` ≈ `-1.7%`, fast suite `92 passed, 5 deselected`.

---

### Task 8: Refresh reproducibility evidence + panel docs for the retuned range

The retune changes 0–10 wrinkle *scores* (raw values are untouched, so the validators' CSVs/plots are unchanged — the benchmark runs in Tasks 5–7 already re-validated them). What must be regenerated is everything derived from scores: the reproducibility figure and the σ tables quoted in BUILD_NOTES §4 and TDD §3.

**Files:**
- Regenerate: `docs/figures/reproducibility.png` (via `scripts/reproducibility_evidence.py`)
- Modify: `docs/BUILD_NOTES.md` (§4 σ table ~lines 163-170; §6 Session-4 bullet list ~line 364)
- Modify: `docs/TDD.md:50` (the reproducibility paragraph's σ numbers)
- Regenerate: `docs/PRD.pdf`, `docs/TDD.pdf`, `docs/BUILD_NOTES.pdf` (via `scripts/build_docs_pdf.sh`)

**Interfaces:**
- Consumes: retuned `WRINKLE_RAW_RANGE` from Task 5.
- Produces: panel docs whose numbers match the shipped code.

- [ ] **Step 1: Regenerate the reproducibility figure and capture the new σ values**

Run: `uv run python scripts/reproducibility_evidence.py`
Expected: prints a per-metric σ table (`CV (ours)` vs `LLM-baseline` columns) and writes `docs/figures/reproducibility.png`. Only the **wrinkle** row should move vs the current table (pigmentation 0.286 / erythema 0.139 / pore 0.232 / uniformity 0.119 stay identical — their ranges are untouched); expect wrinkle ≈ 0.25 (0.209 × 0.50/0.42 range-narrowing factor). Copy the actual printed numbers — do not use these estimates in the docs.

- [ ] **Step 2: Update the σ table in `docs/BUILD_NOTES.md` §4**

Replace the five metric rows and the mean row in the table at lines ~163–170 with the values printed in Step 1, and update the "~4× tighter" sentence only if the new ratio rounds to a different multiple. Leave the honesty note about v1 saturation untouched.

- [ ] **Step 3: Record the FFHQ retune in `docs/BUILD_NOTES.md` §6**

The Session-4 bullet ending `pigmentation / erythema / uniformity distributions were unchanged and keep their v1 ranges.` (~line 364-368) is a historical record — leave it. Immediately after that bullet, add:

```markdown
* **Wrinkle range re-fitted a second time, now against ground truth**
  (Session 6): FFHQ-Wrinkle (n=1000 hand-annotated faces, ROI-restricted,
  CLAHE-matched to production) measures real-face `wrinkle_raw` p5–p95 =
  [0.197, 0.619] — the reference-face ceiling of 0.75 was never reached,
  so the top quarter of the 0–10 wrinkle scale was dead range.
  `WRINKLE_RAW_RANGE` is now (0.20, 0.62), pinned to the measured
  distribution by `tests/test_validation_benchmarks.py`
  (`uv run pytest -m validation`).
```

- [ ] **Step 4: Update the σ numbers in `docs/TDD.md:50`**

In the sentence `**σ̄(ours) ≈ 0.197 vs σ̄(stochastic baseline at σ=1.0) ≈ 0.747 — a ~4× tighter band** (per-metric: pigmentation 0.286, erythema 0.139, wrinkle 0.209, pore 0.232, uniformity 0.119)`, substitute the Step-1 σ̄, baseline σ̄, per-metric values, and the ratio multiple. Leave the rest of the paragraph (honesty note, drift numbers) untouched.

- [ ] **Step 5: Rebuild the PDFs**

Run: `bash scripts/build_docs_pdf.sh`
Expected: regenerated `docs/PRD.pdf`, `docs/TDD.pdf`, `docs/BUILD_NOTES.pdf` (requires pandoc + Chrome; if the script fails on a missing tool, STOP and report — do not hand-edit PDFs).

- [ ] **Step 6: Lint, verify, commit**

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest tests/ -q 2>&1 | tail -1
git add docs/figures/reproducibility.png docs/BUILD_NOTES.md docs/TDD.md docs/PRD.pdf docs/TDD.pdf docs/BUILD_NOTES.pdf
git commit -m "docs: refresh reproducibility evidence for FFHQ-retuned wrinkle range

Regenerated figure + sigma tables (only the wrinkle row moves; its
narrower range scales perturbation sensitivity by ~1.19x). BUILD_NOTES
S6 records the ground-truth re-fit provenance.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

Expected: `92 passed, 5 deselected`.

---

### Task 9: `docs/VALIDATION.md` — the ground-truth evidence summary

**Files:**
- Create: `docs/VALIDATION.md`
- Modify: `data/validation/README.md` (add the benchmark-test pointer after the three `uv run python ...` lines, ~line 31)

**Interfaces:**
- Consumes: Session-5 findings (numbers already verified by the benchmark runs in Tasks 5–7).
- Produces: the CTO-call evidence document; linked from the validation README.

- [ ] **Step 1: Create `docs/VALIDATION.md`**

```markdown
# Ground-Truth Validation of the Core Metrics

> How the two core features — the Photo-Consistency Gate and the 5-metric
> scoring engine — were graded against independent, expert-annotated public
> datasets, and what changed as a result. Method + re-run instructions:
> `data/validation/README.md`. These findings are enforced as regression
> tests: `uv run pytest -m validation`.

All three studies import the **production** `facetrack` functions (no
re-implementation) at the deployed 512 px face scale. Real-person pixels
never enter git; only scripts, manifests, and aggregate results are tracked.

## 1. Wrinkle metric vs 1,000 hand-annotated faces (FFHQ-Wrinkle)

Kim et al.'s FFHQ-Wrinkle provides 1,000 dermatologically hand-drawn
wrinkle masks. Per-face `wrinkle_raw` (Sobel edge density) was compared
against human mask coverage, measured exactly the way production scores —
inside the forehead/cheek skin ROIs, on the CLAHE-normalized crop.

| Measurement | Result |
|---|---|
| Ranking validity, **production ROIs** | Spearman ρ = **+0.42** |
| Ranking validity, whole face (contrast) | Spearman ρ = +0.145 |
| Real-face `wrinkle_raw` p5–p95 | **[0.197, 0.619]** |

**Finding 1 — the ROI design is what makes the metric valid.** Restricting
to the production skin ROIs triples the ground-truth correlation vs a
whole-face measure (eyebrows, eyes, and hairline otherwise dominate the
edge signal). This is direct evidence for the pipeline's ROI architecture.

**Finding 2 — the score range was miscalibrated at the top.** The previous
`WRINKLE_RAW_RANGE = (0.25, 0.75)`, fitted on 5 reference faces, had a
ceiling no real face reached: scores above ~7.4/10 were unreachable dead
range. The range is now **(0.20, 0.62)** — the measured p5–p95 — and a
benchmark test pins the endpoints to the real-face distribution (±0.05).

Scope note: with the Sobel cutoff at 30, ROI recall vs the masks is 0.81
but pixel precision is 0.083 — the metric is a texture-*density* proxy
(right tool for a 0–10 severity score), not a wrinkle-line localizer.
Do not use it to draw wrinkle overlays.

## 2. Erythema construct validity vs dermatologist grades (ACNE04)

ACNE04 (Wu et al., ICCV 2019) buckets 394 sampled faces by Hayashi acne
severity grade 0–3. Inflammatory severity should move a redness metric and
leave pure-texture metrics alone — a known-groups test.

| Metric | Behaviour across grades 0→3 | Verdict |
|---|---|---|
| `erythema_raw` (mean a\*) | rises monotonically, 136.4 → 139.7; ρ = **+0.23**, rank-biserial (0 vs 3) = **+0.38** | construct validity ✓ |
| `wrinkle_raw`, `pore_raw` | flat (ρ ≈ 0) | discriminant validity ✓ |

The redness metric moves in the clinically expected direction, and the
texture metrics do **not** spuriously fire on inflammation.

## 3. Gate skin-tone fairness (SCIN, Fitzpatrick-stratified)

LIMITATIONS §4 flags the risk that the gate's fixed YCrCb skin band,
tuned on lighter skin, wrongfully rejects darker patients. Audited on a
Fitzpatrick-stratified SCIN sample (360 images, 60 per FST type, darker
types over-sampled for power):

| Group | Simulated gate pass-rate |
|---|---|
| FST 1–2 (lightest) | 92.5 % |
| FST 5–6 (darkest) | **94.2 %** |

Gap = **−1.7 pp** — darker skin passes slightly *more* often. The feared
dark-skin rejection bias is **not observed** at SCIN's luminance range.
Caveats: whole-image band-coverage proxy (SCIN photos are body-part
close-ups, not aligned faces), and SCIN may under-represent very-low-light
capture conditions; the benchmark test keeps the gap under 5 pp so any
future band change that introduces bias fails CI.

## What is enforced going forward

`tests/test_validation_benchmarks.py` (opt-in: `uv run pytest -m
validation`; requires the local datasets):

| Guard | Threshold | Measured |
|---|---|---|
| FFHQ ROI rank correlation | ρ ≥ 0.35 | 0.42 |
| `WRINKLE_RAW_RANGE` endpoints | within ±0.05 of measured p5/p95 | (0.20, 0.62) vs [0.197, 0.619] |
| ACNE04 erythema construct | ρ > 0.15 | 0.23 |
| ACNE04 texture discriminant | \|ρ\| < 0.10 | ≈ 0 |
| SCIN pass-rate gap | \|gap\| ≤ 5 pp | −1.7 pp |
```

- [ ] **Step 2: Add the pointer in `data/validation/README.md`**

Immediately after the three-command code block (ending line ~31), add:

```markdown
The same checks run as opt-in regression tests — `uv run pytest -m
validation` — with thresholds documented in `docs/VALIDATION.md`.
```

- [ ] **Step 3: Cross-check every number in VALIDATION.md against the tracked results**

Run: `head -3 data/validation/ffhq_wrinkle/results/wrinkle_per_image.csv data/validation/acne04/results/acne_per_image.csv data/validation/scin/results/skintone_bias.csv`
Expected: files exist with the documented columns. Then compare the doc's ρ/gap/percentile numbers against the Task 4–7 pytest output captured earlier (roi_spearman ≈ 0.42, p5/p95 ≈ 0.197/0.619, erythema rho ≈ 0.23, gap ≈ −1.7pp). Fix any mismatch in the doc — the measured values win.

- [ ] **Step 4: Commit**

```bash
git add docs/VALIDATION.md data/validation/README.md
git commit -m "docs(validation): ground-truth evidence summary

Three findings from grading production functions against public
expert-annotated datasets: ROI design validates the wrinkle metric
(rho 0.42 vs 0.145 whole-face), erythema has construct + discriminant
validity on ACNE04, and no dark-skin gate bias is observed on SCIN
(gap -1.7pp). Links the enforced pytest -m validation thresholds.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 10: Final verification (no new code)

**Files:** none.

- [ ] **Step 1: Full fast suite + lint**

```bash
uv run pytest tests/ -q 2>&1 | tail -1
uv run ruff check . && uv run ruff format --check .
```

Expected: `92 passed, 5 deselected`; ruff silent.

- [ ] **Step 2: Full benchmark run (~15–25 min — FFHQ dominates)**

Run: `uv run pytest -m validation 2>&1 | tail -8`
Expected: `5 passed` (2 FFHQ + 2 ACNE04 + 1 SCIN), zero skips (all data is local on this machine).

- [ ] **Step 3: Confirm clean tree and report**

Run: `git status --short && git log --oneline -9`
Expected: empty status; history shows the spec commit, S4, S5, refactor, retune, two benchmark commits, docs refresh, VALIDATION.md.

Report to Eric: retune applied (v2, no version bump), benchmark layer live, docs refreshed. Remaining manual follow-ups from the backlog (NOT in this plan): Streamlit Cloud redeploy, live-capture HUD parity, longitudinal chart version annotation.

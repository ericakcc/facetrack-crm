# Design: Wrinkle Range Retune + Validation Benchmark Test Layer

**Date**: 2026-07-04
**Status**: Approved by Eric (Session 6)
**Depends on**: Session 5 validation harness (3 public datasets + 3 validation scripts, currently uncommitted)

## Goal

Use the three downloaded ground-truth datasets (FFHQ-Wrinkle, ACNE04, SCIN) to:

1. **Optimize**: apply the FFHQ-derived retune of `WRINKLE_RAW_RANGE` so the 0-10 wrinkle score uses its full dynamic range.
2. **Test**: turn the three one-off validation scripts into a repeatable pytest regression layer, so any future CV/scoring change immediately reveals whether ground-truth alignment broke.

## Non-Goals

- Recalibrating erythema range, gate thresholds, or Sobel cutoff (data-driven refit deferred; current values keep their Session-5 validated status).
- Streamlit Cloud redeploy (separate follow-up step after this work lands).
- Live-capture HUD updates, longitudinal chart annotations (separate backlog items).

## Design

### 1. Precondition: commit existing Session 4 + 5 work

All S4 (Gate v2 + Scoring v2) and S5 (validation harness) changes are uncommitted on top of `2f6beae`. Land them first as two separate commits (S4 code/tests/docs, then S5 data manifests + validation scripts) so the retune is a clean, reviewable diff against a stable baseline.

### 2. Retune (the optimization)

- `src/facetrack/scoring.py`: `WRINKLE_RAW_RANGE = (0.25, 0.75)` → `(0.20, 0.62)`, matching the measured real-face p5-p95 of `[0.197, 0.619]` on FFHQ-Wrinkle (n=1000, CLAHE-matched to production). The old high end (0.75) was never reached, so the top of the 0-10 scale was dead range.
- **`SCORING_VERSION` stays 2**: v2 has never been committed or deployed and no persisted visit rows carry v2 scores, so the retune folds into the v2 definition. No version bump, no migration.
- Knock-on updates in the same change:
  - `tests/test_scoring_robustness.py` expectations that depend on the wrinkle range.
  - Regenerate the reproducibility figure via `scripts/reproducibility_evidence.py`.
  - Update the affected `docs/BUILD_NOTES.md` section and regenerate its PDF via `scripts/build_docs_pdf.sh`.

### 3. Refactor validation scripts into callable functions

Each of `scripts/validation/validate_wrinkle_ffhq.py`, `validate_severity_acne04.py`, `validate_skintone_bias_scin.py` exposes a `run_validation(data_dir: Path) -> dict` returning its summary statistics (Spearman rho values, raw-range percentiles, pass-rate gap, sample counts). The CLI entry point keeps producing the existing CSV/plot outputs by calling the same function. Tests import the function — no duplicated logic.

### 4. pytest validation layer (the tests)

New `tests/test_validation_benchmarks.py`:

- Every test carries `@pytest.mark.validation` and skips with a clear reason when `data/validation/<dataset>/` is missing (re-download instructions live in `data/validation/README.md`).
- Register the `validation` marker and add `addopts = -m "not validation"` to the pytest config, so:
  - Daily `uv run pytest tests/` → the existing 92 fast tests, unchanged behavior.
  - `uv run pytest -m validation` → runs the real-data benchmarks (opt-in, slow).

Threshold assertions (measured values with safety margin; rho is computed on raw metric values, so thresholds hold both before and after the retune):

| Test | Assertion | Session-5 measured |
|---|---|---|
| FFHQ ROI rank correlation | roi_spearman ≥ 0.35 | 0.42 |
| FFHQ dynamic range | `WRINKLE_RAW_RANGE` endpoints within ±0.05 of measured raw p5/p95 | [0.197, 0.619] |
| ACNE04 construct validity | erythema rho > 0.15 | 0.23 |
| ACNE04 discriminant validity | wrinkle & pore \|rho\| < 0.10 | ≈ 0 |
| SCIN gate fairness | \|FST5-6 − FST1-2 pass gap\| ≤ 5 pp | −1.7 pp |

### 5. Re-run validators + documentation

- After the retune, re-run all three validators to refresh each dataset's `results/` CSV/PNG (score-scale figures reflect the new range).
- Add `docs/VALIDATION.md` citing the three ground-truth findings (ROI design validated at rho 0.42 vs 0.145 whole-face; erythema monotone with acne severity; no dark-skin gate bias at SCIN's luminance range) — the CTO-call evidence document.

## Error handling

- Missing validation data → pytest skip with the download instruction path, never a failure.
- Validators keep their existing failure modes (explicit errors on malformed manifests); no silent fallbacks added.

## Testing strategy

- The 92 existing tests must pass after the retune (with updated robustness expectations).
- The new benchmark layer is itself the test deliverable; it must pass on the retuned code with the thresholds above.
- `uv run ruff check . --fix && uv run ruff format .` clean before each commit.

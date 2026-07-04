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

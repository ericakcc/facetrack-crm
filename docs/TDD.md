# FaceTrack CRM — Technical Design Document

**Author**: Eric Tsou
**For**: AI Fund Engineer in Residence — Build Challenge
**Date**: 2026-05-19
**Companion to**: `docs/PRD.md`

---

## 1. System architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Streamlit UI (繁體中文)                        │
│  sidebar nav + 5 pages (overview/intake/history/treatment/cfg)   │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Service layer (Python)                     │
│                                                                  │
│   FacePipeline ──▶ ConsistencyGate ──▶ ScoringEngine             │
│   (alignment +     (pose / exposure /   (5 deterministic         │
│    ROI extract)     sharpness / color)   CV metrics, 0–10)       │
│                            │                  │                  │
│                            ▼                  ▼                  │
│   Explainer (Mock | Anthropic Claude — translates scores only)   │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│   SQLite (SQLModel)                                              │
│   patient · visit · region_score · treatment_note                │
└─────────────────────────────────────────────────────────────────┘
```

The pipeline is strictly one-way: every intake photo flows
`FacePipeline → ConsistencyGate → ScoringEngine → DB`, with the LLM hanging off
the side as a presentation-layer convenience.

## 2. Imaging pipeline

`src/facetrack/cv_pipeline.py`

* **Model**: MediaPipe Face Landmarker (Tasks API, `face_landmarker.task`,
  3.6 MB, vendored under `src/facetrack/models/`). Returns 478 landmarks plus a
  4×4 facial-transformation matrix used downstream for pose estimation.
* **Alignment**: rotate around eye-center by the eye-line angle so the inter-pupillary
  line is horizontal. The same affine matrix is applied to the landmarks so ROI
  bounding boxes can be computed in aligned-image coordinates.
* **ROI extraction**: four anatomical regions (`Region.LEFT_CHEEK`,
  `RIGHT_CHEEK`, `FOREHEAD`, `CHIN`) defined as fractions of the face bounding
  box (`face_left/right/top/bot` from indices 234/454/10/152). Bounding-box
  rather than polygon-mask, deliberately: rectangles are easier to debug and
  produce contiguous patches for texture metrics.
* **Per-photo CLAHE** on the L channel of LAB applied to each cropped ROI. This
  normalizes *within-photo* lighting variation (one side brighter than the
  other) but does **not** normalize cross-photo variation — that is the gate's
  job.

## 3. Model reliability and explainability

Every score on the longitudinal chart is produced by a deterministic CV
function, not by an LLM. `src/facetrack/scoring.py`:

| Score | Formula | Why this choice |
|---|---|---|
| Pigmentation | Pixel ratio of `MORPH_BLACKHAT(gray, 15×15)` above 18 | Black-hat highlights small dark structures on brighter background — the morphological signature of melanin spots. |
| Erythema | Mean of `LAB.a*` over ROI | Standard clinical proxy for redness; a* is independent of luminance after gate calibration. |
| Wrinkle | Pixel ratio of Sobel magnitude above 30 (post-Gaussian blur) | Edge density is a cheap, isotropic proxy for fine-line content; reproducible across illumination. |
| Pore | Pixel ratio of Laplacian-of-Gaussian above 0.045 at σ=1.4 | LoG blob detection at pore-sized scale; a textbook isotropic-blob filter. |
| Uniformity (inverted) | `std(LAB.L)` mapped 0–10 then inverted | Low variance ⇒ uniform tone; the only metric where higher score is better. |

Each raw measurement is linearly clamped against a published constant
(`PIGMENTATION_RAW_RANGE`, etc.). Re-calibration on a clinic's own
distribution means editing one tuple, not re-training a model.

**Reproducibility.** Running the same input twice produces bit-identical
outputs. There are zero stochastic operations, zero LLM calls, and no
network I/O in the scoring path. This is the property the longitudinal chart
depends on, and it is what a typical "score this face with GPT-4o" prototype
does not have.

**Explainability.** The score formula is the explanation. A physician
asking "why is the pigmentation score 7.2 ?" can be answered with a
heatmap of the black-hat response — the same intermediate the score is
computed from.

## 4. Photo-consistency controls — the depth area

`src/facetrack/consistency_gate.py`

Four checks gate every intake photo before scoring:

1. **Pose.** Decompose MediaPipe's 4×4 facial-transformation matrix into yaw /
   pitch / roll via the ZYX Euler convention. Reject if any axis exceeds
   `POSE_TOLERANCE_DEG` (default ±8°). The transformation matrix is a more
   accurate pose source than landmark triangulation because it incorporates
   the model's own 3D head pose estimation.
2. **Exposure.** Compute fraction of pixels < 10 (underexposed) and > 245
   (overexposed) on grayscale. Reject if either exceeds 2 % OR if mean
   brightness is < 60 / > 210.
3. **Sharpness.** Laplacian variance on grayscale; reject if below 80.
4. **Color calibration.** Detect ArUco 5×5 markers (`DICT_5X5_50`); if a
   marker is present, sample the printed gray surround, compute per-channel
   gains to neutralize white balance, apply to the full image. If no marker is
   present, this check emits a warning rather than a hard reject — many clinics
   will adopt the calibration card progressively, so we degrade gracefully.

Failure modes produce actionable 繁中 reasons
(`"頭部右偏 12.3°, 容差 ±8°, 請正對鏡頭"`), surfaced to the receptionist in
the intake UI. The full `QualityReport` is JSON-serialized to the `Visit`
row so an audit trail exists.

## 5. Workflow integration

* **Streamlit** chosen over a React+FastAPI split because the build-challenge
  deliverable is a 48-hour prototype, not a production system. Streamlit gives
  the entire UI in a single file, can be deployed to Streamlit Cloud in one
  click, and is the right tool for "show a CV pipeline" demos. Switching to
  React+FastAPI is a 1-week refactor, deferred.
* **SQLModel** because it is the same `BaseModel` API the rest of the codebase
  uses for type-validated dataclasses, and it produces a single SQLite file we
  can ship in the repo for the panel review.
* **State** lives on disk (SQLite + photo blobs under `data/photos/`), so
  restarting the Streamlit process loses no data. No Redis, no background
  workers, no message queues — the entire pipeline runs synchronously in the
  request thread because the slowest stage (MediaPipe inference) is < 200 ms
  on Apple Silicon.

## 6. Tech stack & deployment

* Python 3.11 (mediapipe 0.10 still has spotty 3.12 support on macOS arm64)
* uv for dependency management — fast, lock-file-pinned, no `pip` in this repo
* mediapipe 0.10.35 / opencv-python-headless / sqlmodel / streamlit / plotly
* `anthropic` Python SDK for the optional Claude backend
* Deployment target: Streamlit Community Cloud (free tier), GitHub-linked

## 7. Known limitations / future hardening

1. **Empirical scoring ranges** are calibrated on three reference photos; a
   real pilot would re-fit on ~200 clinic images per Fitzpatrick skin type.
2. **No identity confirmation** — the system trusts that the receptionist
   selected the right patient before upload. Phase 2 should add face-embedding
   verification against the patient's first-visit photo.
3. **ArUco card adoption is voluntary**, which means color calibration is
   best-effort. Phase 2 introduces a small printable card distributed with
   every onboarding pack and a marker-required clinic setting.
4. **No HIPAA / PIPL story** — patient photos are in clear on disk. Phase 2
   needs at-rest encryption and a deletion API.

## 8. What was reused vs. built

| Reused | Built |
|---|---|
| MediaPipe Face Landmarker model | Alignment + ROI extraction code |
| OpenCV CLAHE, ArUco, morphology | All five scoring formulas + calibration ranges |
| Streamlit / Plotly / SQLModel | Photo-Consistency Gate (all four checks) |
| Anthropic SDK | Explainer interface + mock backend + JSON-output prompt |
| `thispersondoesnotexist.com` for 3 CC0 test faces | Seed-data trajectory generator, UI, DB schema |

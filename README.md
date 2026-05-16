# FaceTrack CRM

> AI-native CRM and clinical support system for Taiwan medical aesthetic / beauty clinics.
> **AI Fund Engineer in Residence — Build Challenge submission.**

## What it does

A standardized facial-photo intake flow that produces **quantified, reproducible**
skin profiles, supports longitudinal comparison across visits, and powers a
clinician-facing treatment-planning workflow — built around a **Photo-Consistency
Gate** that rejects low-quality intakes before they contaminate the patient's
longitudinal record.

## The product thesis (read this first)

Three decisions separate this prototype from "yet another Vision-LLM wrapper":

1. **Scoring is deterministic CV, never an LLM.** Pigmentation, erythema,
   wrinkle, pore, and uniformity scores are produced by fixed CV formulas
   (black-hat morphology, LAB `a*`, Sobel, LoG, L\* stddev). Running the same
   photo twice gives the same number — which is the precondition for any
   meaningful longitudinal chart.

2. **A Photo-Consistency Gate rejects bad intakes _before_ they reach scoring.**
   This is the prototype's depth area. Four checks: pose (yaw/pitch/roll ±8°),
   exposure (over/under), sharpness (Laplacian variance), and color (ArUco
   gray-card white balance). A failed photo is rejected with a 繁中 reason
   ("頭部右偏 12°，請正對鏡頭"). The chart never compares apples to oranges.

3. **The LLM is the final layer, not the engine.** Claude is wired in for
   translating numeric scores into natural 繁中 explanations and drafting an
   editable treatment plan. The clinician edits everything before saving.

## Why this is not an LLM wrapper

| Skin attribute | Method | Reproducible? |
|---|---|---|
| Pigmentation | Black-hat morphology pixel ratio | Yes |
| Erythema (redness) | LAB a\* channel mean | Yes |
| Wrinkles | Sobel-magnitude edge density | Yes |
| Pores | LoG blob detection | Yes |
| Tone uniformity | L\*-channel stddev (inverted) | Yes |

The LLM never produces the numbers on the chart.

## Architecture

```
Streamlit UI (繁體中文)
       │
       ▼
FacePipeline ── ConsistencyGate ── ScoringEngine ── (Mock | Claude) Explainer
(MediaPipe)     (pose/exp/sharp/color)  (5 CV metrics)        │
       │                                                       ▼
       └──────────────── SQLite (SQLModel) ◀──── editable TreatmentNote
```

## Quickstart

```bash
uv sync
uv run streamlit run app.py
```

Open <http://localhost:8501>. Three demo patients are auto-seeded on first
run. Try the **新增就診** page with any frontal portrait — the consistency
gate will reject under-/over-exposed photos with a concrete 繁中 reason, then
the scoring engine produces deterministic 0-10 metrics on what passes.

To swap the mock explainer for the real Claude backend:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
uv run streamlit run app.py
```

## Deployment

The repo is ready for **Streamlit Community Cloud**:

1. Push to GitHub (public repo).
2. <https://share.streamlit.io> → "New app" → pick this repo, branch `main`,
   main file `app.py`. Python version is pinned via `runtime.txt`.
3. Optional: set `ANTHROPIC_API_KEY` under "App settings → Secrets" to enable
   real Claude explanations.

`requirements.txt` is committed alongside `pyproject.toml` for compatibility
with deployment platforms that don't yet parse PEP-735 dependency groups.

## Project layout

```
facetrack-crm/
├── app.py                          # Streamlit entry point (繁中 UX)
├── src/facetrack/
│   ├── cv_pipeline.py              # MediaPipe Face Landmarker (Tasks API) + ROI
│   ├── consistency_gate.py         # ⭐ Photo-Consistency Gate — depth area
│   ├── scoring.py                  # Five deterministic CV metrics, 0–10
│   ├── llm_explainer.py            # Mock + Anthropic Claude adapter
│   ├── db.py                       # SQLModel schemas
│   ├── seed.py                     # 3 demo patients × 3 visits trajectory
│   └── models/face_landmarker.task # MediaPipe model (3.6 MB, vendored)
├── data/
│   ├── facetrack.db                # SQLite (gitignored)
│   ├── photos/                     # Saved intake photos (gitignored)
│   └── test_images/                # 3 CC0 AI-generated faces for smoke testing
├── docs/
│   ├── PRD.md                      # Product requirements (1-2 pages)
│   ├── TDD.md                      # Technical design (1-2 pages)
│   └── BUILD_NOTES.md              # Authorship / debugging note
├── scripts/
│   └── generate_demo_photos.py     # Nano Banana Pro longitudinal photo gen
├── tests/                          # pytest suite (mock explainer, app imports)
├── pyproject.toml                  # uv-managed deps + ruff/pytest config
├── requirements.txt                # Mirrors pyproject for Streamlit Cloud
└── runtime.txt                     # python-3.11 for Streamlit Cloud
```

## Demo recipe for the panel video

The 2-5 minute demo should hit these beats in order:

1. **Open the app**, select 林雅婷, show the **縱向追蹤** radar + line chart
   — the existing seed data demonstrates a downward pigmentation trend.
2. Switch to **新增就診**. Upload `data/test_images/test_face_1.jpg`. The
   Photo-Consistency Gate **rejects** it (underexposed) with a 繁中 reason.
   Upload `test_face_3.jpg`. **Rejected** (overexposed).
3. Upload `test_face_2.jpg`. **Passes.** Show the four ROI crops, then the
   five deterministic 0–10 scores, then the editable treatment-plan draft.
4. Click **儲存到病患歷史**, switch back to **縱向追蹤**, show the chart
   updated with the new visit.
5. (Optional) `export ANTHROPIC_API_KEY=...` and re-run to show the explainer
   swap from mock to Claude with no other code change.

That sequence makes the depth area (Photo-Consistency) **visible in product
evidence**, satisfying the panel's "depth area must be in the product, not
just described" rule.

## Tests

```bash
uv run pytest -v
uv run ruff check .
```

## What I built vs. reused

See `docs/BUILD_NOTES.md` for the authorship note required by the brief
(what was built, what was reused, the bugs hit, how they were debugged).

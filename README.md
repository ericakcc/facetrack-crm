# FaceTrack CRM

> AI-native CRM and clinical support system for Taiwan medical aesthetic / beauty clinics.
> **AI Fund Engineer in Residence — Build Challenge submission.**

## What it does

A standardized facial-photo intake flow that produces **quantified, reproducible** skin profiles,
supports longitudinal comparison across visits, and powers a clinician-facing treatment-planning
workflow — built around a **Photo-Consistency Gate** that rejects low-quality intakes before they
contaminate the patient's longitudinal record.

## Why this is not an LLM wrapper

Scoring is done with **deterministic CV metrics**, not an LLM:

| Skin attribute | Method | Reproducible? |
|---|---|---|
| Pigmentation | ITA° on CIE Lab | Yes |
| Erythema (redness) | LAB a\* channel mean | Yes |
| Wrinkles | Gabor filter response density | Yes |
| Pores | LoG blob detection | Yes |
| Tone uniformity | L-channel stddev | Yes |

The LLM is used **only** for natural-language explanation and an editable treatment-suggestion
draft — it never produces the numbers that go onto the longitudinal chart.

## Depth area: Photo-Consistency Gate

Before any score is computed, intake photos pass through a quality gate:

1. **Pose** — MediaPipe yaw/pitch/roll within tolerance
2. **Exposure** — histogram-based over/under-exposure detection
3. **Color** — gray-card / ArUco marker white-balance calibration
4. **Sharpness** — Laplacian variance threshold

A photo that fails any check is rejected with a specific reason, before it ever reaches the
scoring engine — so the longitudinal chart never compares apples to oranges.

## Quickstart

```bash
uv sync
uv run streamlit run app.py
```

## Project layout

```
facetrack-crm/
├── app.py                          # Streamlit entry point (繁中 UX)
├── src/facetrack/
│   ├── cv_pipeline.py              # MediaPipe alignment + ROI extraction
│   ├── consistency_gate.py         # Photo-Consistency Gate (depth area)
│   ├── scoring.py                  # Quantitative CV metrics
│   ├── llm_explainer.py            # Mock + Anthropic adapter
│   ├── db.py                       # SQLModel schemas
│   └── seed.py                     # Demo patients & visits
├── data/
│   ├── facetrack.db                # SQLite (gitignored)
│   └── photos/                     # Patient photos (gitignored)
├── docs/
│   ├── PRD.md
│   └── TDD.md
└── tests/
```

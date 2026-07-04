# FaceTrack CRM

> AI-native CRM and clinical support system for Taiwan medical aesthetic / beauty clinics.
> **MVP 追蹤皮秒雷射淡斑療程**；同一套架構為擴展至其他醫美術後（肝斑、痘疤、紅血絲）而設計。
> **AI Fund Engineer in Residence — Build Challenge submission.**

## Panel reviewer — start here

| Doc | What it covers |
|---|---|
| [`docs/PRD.pdf`](./docs/PRD.pdf) | Product narrative, user, wedge → platform |
| [`docs/TDD.pdf`](./docs/TDD.pdf) | Imaging pipeline · reliability · workflow · consistency controls |
| [`docs/BUILD_NOTES.pdf`](./docs/BUILD_NOTES.pdf) | Authorship, debug stories, latency + reproducibility tables |
| [`docs/LIMITATIONS.md`](./docs/LIMITATIONS.md) | 6 failure modes × Phase-2 mitigations |
| [`docs/VALIDATION.md`](./docs/VALIDATION.md) | Ground-truth validation evidence for the gate + scoring engine (FFHQ-Wrinkle, ACNE04, SCIN) |

Reproduce the headline numbers from the BUILD_NOTES tables yourself:

```bash
uv run python scripts/benchmark.py                 # latency table (M4 Pro: 21.6 ms p50)
uv run python scripts/reproducibility_evidence.py  # σ̄ comparison + figure
```

Live app: _TBD (Streamlit Cloud)_  ·  Demo video: _TBD (Loom)_

## What it does

A standardized facial-photo intake flow that produces **quantified, reproducible**
skin profiles, supports longitudinal comparison across visits, and powers a
clinician-facing treatment-planning workflow — built around a **Photo-Consistency
Gate** that rejects low-quality intakes before they contaminate the patient's
longitudinal record. **本次 build challenge 提交版本以皮秒雷射淡斑療程追蹤為示範**
（4–6 次療程、色素沉澱為主訊號）；引擎本身是 procedure-agnostic（見 TDD §3）。

The intake page runs a **live face-mesh capture widget**: MediaPipe Tasks
Vision Web SDK loads in the browser, draws the 478-point mesh + tessellation
on the live camera feed, and only auto-captures when pose / face-fill /
stability all pass simultaneously. The same `ConsistencyGate` then re-runs
server-side on the captured frame — the browser HUD is a UX accelerator,
not a security boundary.

## The product thesis (read this first)

Three decisions separate this prototype from "yet another Vision-LLM wrapper":

1. **Scoring is deterministic CV, never an LLM.** Pigmentation, erythema,
   wrinkle, pore, and uniformity scores are produced by fixed CV formulas
   (black-hat morphology, LAB `a*`, Sobel, LoG, L\* stddev). Running the same
   photo twice gives the same number — which is the precondition for any
   meaningful longitudinal chart.

2. **A Photo-Consistency Gate rejects bad intakes _before_ they reach scoring.**
   This is the prototype's depth area. Six checks: pose (yaw/pitch/roll ±15°
   frontal, ±5° profile), exposure (over/under, measured on the face crop),
   sharpness (resolution-normalized Laplacian variance + a native face-width
   floor), lighting uniformity (left/right face-brightness asymmetry),
   skin visibility (per-ROI skin-pixel ratio — catches masks / sunglasses /
   hair occlusion), and color (ArUco gray-card white balance, soft warning).
   A failed photo is rejected with a 繁中 reason ("頭部右偏 18°，請正對鏡頭").
   The chart never compares apples to oranges.

3. **The LLM is the final layer, not the engine.** Either Anthropic Claude
   or Google Gemini drafts the 繁中 explanation + editable treatment plan
   (auto-fallback to a deterministic `MockExplainer` if no key is set or
   the SDK errors). The clinician edits everything before saving.

## Why this is not an LLM wrapper

| Skin attribute | Method | Reproducible? |
|---|---|---|
| Pigmentation | Black-hat morphology pixel ratio (Gaussian-denoised) | Yes |
| Erythema (redness) | LAB a\* channel mean | Yes |
| Wrinkles | Sobel-magnitude edge density | Yes |
| Pores | LoG blob detection | Yes |
| Tone uniformity | L\*-channel stddev (inverted) | Yes |

All five run on a **scale-normalized face** (anatomical face width rescaled to
a fixed 512 px before ROI extraction) and on an **effective mask** that
excludes specular glare and deep shadow — so the numbers track skin, not the
camera distance or the ceiling lights. Every visit stores the
`scoring_version` that produced its numbers. The LLM never produces the
numbers on the chart.

## Architecture

```
Streamlit UI (繁體中文)
       │
       ▼
FacePipeline ── ConsistencyGate ── ScoringEngine ── (Mock | Anthropic | Gemini) Explainer
(MediaPipe      (pose/exposure/sharpness/   (5 CV metrics,        │
 + 512px scale   lighting/skin/color)        glare-masked)        │
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

To swap the mock explainer for a real backend, set **either** key:

```bash
# Option A: Anthropic Claude (preferred when both are set)
export ANTHROPIC_API_KEY=sk-ant-...

# Option B: Google Gemini (auto-selected if Anthropic key absent)
export GEMINI_API_KEY=...

# Override resolution explicitly:
export LLM_BACKEND=anthropic   # or 'gemini' or 'mock'

uv run streamlit run app.py
```

Both backends fall back to the deterministic `MockExplainer` on any SDK
error, so the demo never hard-fails on a flaky upstream.

## Deployment

The repo is ready for **Streamlit Community Cloud**:

1. Push to GitHub (public repo).
2. <https://share.streamlit.io> → "New app" → pick this repo, branch `main`,
   main file `app.py`. Python version is pinned via `runtime.txt`.
3. Optional: set `ANTHROPIC_API_KEY` and/or `GEMINI_API_KEY` under
   "App settings → Secrets" to enable real LLM explanations. With neither
   key set, the app runs against `MockExplainer` and the demo loop still
   works end-to-end.

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
│   ├── score_display.py            # Score → health-band UI helpers
│   ├── llm_explainer.py            # Mock + Anthropic + Gemini adapters (auto-fallback)
│   ├── patient_service.py          # Patient CRUD + soft-delete
│   ├── visualization.py            # ROI heatmap + 4-crop CLAHE composer
│   ├── db.py                       # SQLModel schemas (zero-downtime ALTER migrations)
│   ├── seed.py                     # 3 demo patients × 3 visits trajectory
│   ├── components/face_capture/    # In-browser live face-mesh capture widget
│   └── models/face_landmarker.task # MediaPipe model (3.6 MB, vendored)
├── data/
│   ├── facetrack.db                # SQLite (gitignored)
│   ├── photos/                     # Saved intake photos (gitignored)
│   └── test_images/                # CC0 AI-generated faces (test_face_{1,2,3}.jpg used by smoke tests)
├── docs/
│   ├── PRD.md                      # Product requirements (1-2 pages)
│   ├── TDD.md                      # Technical design (1-2 pages)
│   ├── BUILD_NOTES.md              # Authorship / debugging note
│   ├── LIMITATIONS.md              # Honest failure-mode catalogue + Phase-2 plan
│   ├── VALIDATION.md               # Ground-truth validation evidence (FFHQ/ACNE04/SCIN)
│   └── figures/reproducibility.png # Determinism evidence (embedded in TDD §3)
├── scripts/
│   ├── benchmark.py                # End-to-end latency (BUILD_NOTES §4 source)
│   ├── reproducibility_evidence.py # σ̄ comparison chart (TDD §3, BUILD_NOTES §4 source)
│   ├── build_docs_pdf.sh           # Render PRD / TDD / BUILD_NOTES PDFs
│   └── generate_demo_photos.py     # Nano Banana Pro longitudinal photo gen
├── tests/                          # 97 tests/10 files (92 fast + 5 opt-in) — uv run pytest -v
├── pyproject.toml                  # uv-managed deps + ruff/pytest config
├── requirements.txt                # Mirrors pyproject for Streamlit Cloud
└── runtime.txt                     # python-3.11 for Streamlit Cloud
```

## Smoke test for reviewers

Five things should be reachable in the live app:

1. **`📈 縱向追蹤`** — pick 林雅婷 (皮秒雷射 session 3 患者); seeded with a
   downward pigmentation trajectory.
2. **`📸 新增就診` → live capture tab** — face-mesh + HUD draws live;
   auto-capture fires only when pose / face-fill / stability all pass.
3. **`📸 新增就診` → upload fallback** — drag `data/test_images/test_face_1.jpg`
   (blown-out, side-lit) → gate rejects with two concrete 繁中 reasons
   (臉部曝光過度 + 光照不均); drag `test_face_2.jpg`
   → passes → 5 scores + 4 ROI heatmaps + LLM treatment draft.
4. **`📋 就診歷史`** — toggle "🔬 顯示 ROI 訊號疊圖" and "🧪 顯示各 ROI 局部影像"
   to compare across visits.
5. **Reproducibility** — re-upload the same passing photo twice; scores match
   to the last decimal (the contract enforced by `tests/test_scoring_determinism.py`).

That sequence makes the depth area (Photo-Consistency) **visible in product
evidence**, satisfying the panel's "depth area must be in the product, not
just described" rule.

## Tests

```bash
uv run pytest -v                # 92 fast tests (default; opt-out marker excludes validation)
uv run pytest -m validation     # +5 opt-in ground-truth benchmarks — needs data/validation/ (~70s)
uv run ruff check .
```

## What I built vs. reused

See `docs/BUILD_NOTES.md` for the authorship note required by the brief
(what was built, what was reused, the bugs hit, how they were debugged).

# Agent Handoff — FaceTrack CRM

> If you are an agent (Claude Code, Codex, Cursor, etc.) starting work on this repo,
> read this file first. It is the single source of truth for project status,
> known inconsistencies, and open decisions.
>
> **Last updated**: 2026-05-18 (end of session 3 — history ROI overlay, Gemini explainer, EricZou demo bypass)
> **Deadline**: 2026-05-19 (default 48hr; brief allows extension with anticipated date)
>
> ## ⏭️ Resuming work? Jump to [§11 — Session 3 changes](#11-session-3--history-roi-overlay-gemini-backend-demo-data) then [§6 — Pickup checklist](#6-pickup-checklist-for-the-next-session)
>
> **Session 3 added an interactive ROI overlay inside the history view (heatmap**
> **+ CLAHE thumbnails, both default-collapsed via checkbox toggles since**
> **Streamlit forbids nested expanders), a second LLM backend (Gemini, with**
> **auto-fallback from Anthropic), patient_service / score_display modules**
> **factored out of app.py, and a DB-only "demo bypass" that flips EricZou's**
> **three visits to quality_passed=True so the presenter's own face shows up**
> **as a tracking baseline. See §11.**

---

## 1. What this project is

A **Streamlit web app (繁體中文)** for Taiwan medical-aesthetic clinic receptionists.
Workflow: upload smartphone face photo → Photo-Consistency Gate → MediaPipe alignment
+ 4-ROI extraction → 5 deterministic CV scores → LLM-drafted 繁中 explanation +
editable treatment plan → SQLite persistence for longitudinal tracking.

It is the **AI Fund Engineer in Residence Build Challenge** submission.

## 2. Source of truth

- **Challenge brief (verbatim)**: `../CHALLENGE_BRIEF.md` — original email from Mike Rubino, AI Fund Head of Talent
- **Contact**: mike@aifund.ai
- **Program**: 12 weeks, in-person Taipei, ~$10K/month consulting, founder/CEO path if funded
- **Working directory**: `/Users/eric_tsou/collab/AIFound/facetrack-crm/`

## 3. Doc map — what each file owns

| File | Owns | Audience |
|---|---|---|
| `../CHALLENGE_BRIEF.md` | Verbatim requirements (do not edit) | Agent + Eric |
| `docs/PRD.md` | Product narrative, user, wedge→platform | AI Fund panel |
| `docs/TDD.md` | Imaging pipeline / reliability / workflow / consistency controls (brief's 4 required TDD sections) | AI Fund panel |
| `docs/BUILD_NOTES.md` | What Eric built vs. reused, what broke, debug story | AI Fund panel |
| `README.md` | Repo front door, quickstart, tech overview | GitHub visitors |
| **this file** | Agent handoff: status, open work, inconsistencies, non-negotiables | Agents only |
| `docs/figures/reproducibility.png` | The evidence chart embedded in TDD §3 | AI Fund panel |
| `scripts/reproducibility_evidence.py` | Regenerates the reproducibility chart | Agents + Eric |
| `scripts/benchmark.py` | Re-measures end-to-end pipeline latency | Agents + Eric |
| `docs/LIMITATIONS.md` | 6 failure modes + concrete Phase-2 mitigations | AI Fund panel |
| `docs/PRD.pdf` / `docs/TDD.pdf` | PDF renders of the panel docs (regenerate via `scripts/build_docs_pdf.sh`) | AI Fund panel |

## 4. Architecture in one diagram

```
FacePipeline ──▶ ConsistencyGate ──▶ ScoringEngine ──▶ SQLite
(MediaPipe       (pose/exposure/      (5 deterministic    (patient·visit·
 alignment        sharpness/ArUco)     CV metrics, 0–10)   region_score·
 + 4 ROIs)              │                      │           treatment_note)
                        ▼                      ▼
                Explainer (Mock | Anthropic Claude — sees SCORES only, never pixels)
```

**Invariant**: LLM never touches images. Scoring path is bit-identical reproducible.
This is the property that makes the longitudinal chart trustworthy and the system
defensible vs. "thin LLM wrapper" objection.

## 5. Doc-vs-code consistency

**Rule**: when a doc, memory, or planning artifact disagrees with the code, **the code wins by default.** Planning artifacts (README scaffolds, memory entries written in an earlier session, PRDs drafted before the implementation pivoted) tend to capture *early intent*. Implementation evolves; the planning side rarely gets back-propagated. Before "fixing" anything, verify against the canonical file path listed in §3, then update the stale doc — **do not** rewrite working code to match an outdated spec.

Common drift sources observed in this repo:
- `README.md` was committed in the initial scaffold (`76937e3`), before scoring engine choices were finalised in commit `a058b48`. It is the highest-drift document.
- Memory files are frozen per-session; if a `originSessionId` predates a code change, treat the memory's specifics as historical, not current.

### Resolution log

Append, do not delete — the history is itself useful context for future agents.

| Date | Inconsistency | Resolution |
|---|---|---|
| 2026-05-17 | `README.md` Pigmentation row said "ITA° on CIE Lab"; `scoring.py:83` uses `MORPH_BLACKHAT`. `BUILD_NOTES.md` line 30 records the deliberate switch. | README row now reads "Black-hat morphology pixel ratio". |
| 2026-05-17 | `README.md` Wrinkles row said "Gabor filter response density"; `scoring.py:104` uses Sobel. | README row now reads "Sobel-magnitude edge density". |
| 2026-05-17 | Memory `project_aifund_facetrack.md` said pose tolerance ±5°; `config.py:25` is `POSE_TOLERANCE_DEG = 8.0`. | Memory rewritten to ±8° when re-aligned against `CHALLENGE_BRIEF.md`. Single source of truth = `config.POSE_TOLERANCE_DEG`. |
| 2026-05-18 | `POSE_TOLERANCE_DEG = 8.0` was unreachable for live webcam users — natural head tilt put roll consistently at ~-8° to -10°. | Relaxed to `15.0` for webcam-realistic tolerance; blurry-image regression test still trips at `30.0` Laplacian threshold. |
| 2026-05-18 | `SHARPNESS_MIN_LAPLACIAN_VAR = 80.0` was DSLR-calibrated; Mac webcam JPEGs landed in 15–20 range. | Two-pronged fix: (a) threshold → `30.0`, (b) `_check_sharpness` now measures on face bbox crop when landmarks present (full frame fallback for the offline blur test). JPEG capture quality also bumped 0.92 → 0.95 in the JS component. |
| 2026-05-18 | Profile pose threshold `PROFILE_YAW_MIN_DEG` started at 55°, then 25°. Both unreachable: most users can't turn past 30° before MediaPipe loses one eye and stops returning a transform. | Final value `5.0`. Use case is **skin-texture sampling at a slightly different angle**, not a dramatic profile — 5° is enough to expose more cheek without losing landmarks. Front frontal tolerance stays at ±15° so the discrimination band [-15, -5] and [+5, +15] is unambiguous. |

Currently open: **none** (as of 2026-05-18). If you find new drift, add a row.

## 6. Pickup checklist for the next session

Status at session-1 end (2026-05-17):

| Required (verbatim from brief) | Status |
|---|---|
| Working prototype URL | ❌ Pending Streamlit Cloud deploy |
| 2–5 min demo video | ❌ Pending recording |
| GitHub repo link | ✅ https://github.com/ericakcc/facetrack-crm (public) |
| PRD 1–2 pages | ✅ `docs/PRD.md` |
| TDD 1–2 pages | ✅ `docs/TDD.md` (incl. reproducibility figure §3, latency table §6, LIMITATIONS link §7) |
| Build / authorship note | ✅ `docs/BUILD_NOTES.md` |
| Bonus: failure-mode catalogue | ✅ `docs/LIMITATIONS.md` (6 cases × Phase-2 fixes) |
| Bonus: demo storyboard | ✅ `docs/DEMO_STORYBOARD.md` |
| Bonus: submission email draft | ✅ `docs/SUBMISSION_EMAIL.md` (fill the 2 URLs) |

**Test coverage**: 19 tests pass; fresh-clone-from-GitHub smoke-tested.

### Remaining work (all manual — agent cannot do these)

#### 1. Deploy to Streamlit Community Cloud (~10 min) ← do this first

```
1. Open https://share.streamlit.io  (sign in with GitHub)
2. Click "Create app" → "Deploy a public app from GitHub"
3. Repository:   ericakcc/facetrack-crm
   Branch:       main
   Main file:    app.py
4. (Optional) Click "Advanced settings" → Secrets, paste:
       ANTHROPIC_API_KEY = "sk-ant-..."
   If no key, leave blank — app falls back to MockExplainer automatically.
5. Click Deploy. First boot ~3-5 min (installs ~80 deps incl. MediaPipe).
6. Note the URL — should look like https://facetrack-crm-XXXX.streamlit.app/
```

**Smoke test on the deployed URL** (incognito tab):
- Sidebar lists 3 seed patients (林雅婷 / 陳怡君 / 王思婷)
- 📈 縱向追蹤 renders radar + line chart
- 📸 新增就診 shows two tabs: 📷 即時拍照 / 📁 上傳照片
- Upload `data/test_images/test_face_1.jpg` → gate rejects (underexposed)

**If deploy fails**: most likely cause is the 3.6 MB `face_landmarker.task` not making it into the deploy. It IS committed (verify with `git ls-files src/facetrack/models/`). If still failing, check Streamlit Cloud logs for `FileNotFoundError`.

#### 2. Record demo video (~1 hr including retakes)

```
1. Open the deployed URL in a fresh Chrome window, zoom to 110%
2. Pre-download data/test_images/test_face_{1,2,3}.jpg locally for drag-and-drop
3. (Optional) Have ONE more photo ready for Scene 6 "失敗 case":
       - a selfie with a mask, OR
       - a heavily makeup photo, OR
       - a photo with sunglasses
4. Follow docs/DEMO_STORYBOARD.md scene-by-scene (7 scenes, target 3-4 min)
5. Tool: Loom browser recorder (includes webcam bubble) OR OBS for local file
6. Voiceover in 繁體中文
```

**Scene 3 is the most important** — that's where the Photo-Consistency Gate is shown
rejecting bad photos, which is the brief's "depth area visible in product evidence" rule.

#### 3. Upload to Loom and get a public link (~10 min)

- Upload the recording
- Sharing → set to "Anyone with the link can view" (NOT workspace-only)
- Test the URL in an incognito window before pasting it anywhere

#### 4. Send submission email (~5 min)

- Open `docs/SUBMISSION_EMAIL.md`
- Replace `[STREAMLIT_CLOUD_URL]` and `[LOOM_URL]`
- Send to `mike@aifund.ai`, subject `FaceTrack CRM — Build Challenge submission`

### Decision flags for the next session

- **Extension to 2026-05-20?** Brief explicitly allows. Worth doing only if something blocks deploy/recording — otherwise default deadline 2026-05-19 is fine.
- **Anthropic API key for live LLM in demo?** Optional. If obtained between sessions, set as a Streamlit Cloud secret (step 4 above) and re-deploy — no code change needed.

### Decisions taken in session 1 (do NOT re-litigate)

- **Skip clinic outreach / customer development.** AI Fund's operating model (per Eric's firsthand attendance at the Beauty Clinic OS breakfast) puts ideation + market validation on AI Fund's internal team; the EIR is filtered on technical execution. See memory `project_aifund_facetrack.md` "Operating model" section.
- **Simulated stochastic baseline in reproducibility chart, not real Vision-LLM.** No API key available in session 1; the chart caption is honest about this; the qualitative argument doesn't depend on the baseline being measured.

## 7. Non-negotiables — do not regress

1. **Scoring stays LLM-free and deterministic.** No `random.*`, no LLM in `scoring.py`, no network I/O in the scoring path. Run-twice must produce identical floats.
2. **LLM never sees pixels.** The `Explainer` interface accepts scores, not images. This is structural defence against the "thin wrapper" objection.
3. **Mandarin UX is first-class.** Strings, error messages, button labels in 繁體中文 directly — not via i18n layer.
4. **uv only.** No `pip install`. New deps via `uv add <pkg>`.
5. **No real-person images in the repo.** Test faces come from CC0 sources (`thispersondoesnotexist.com`).

## 8. Smoke-test a change is safe

```bash
uv run pytest tests/ -v               # all tests green
uv run ruff check . && uv run ruff format --check .
uv run streamlit run app.py           # walk: intake → upload bad + good photo → save → check trend chart
```

## 9. Decisions explicitly made (for context, do not re-litigate)

- Streamlit chosen over React+FastAPI (48hr scope; deploy in one click; right tool for "show a CV pipeline" demo) — see `docs/TDD.md` §5
- SQLite + SQLModel chosen over Postgres (single-file ships in repo; reviewer can clone and run) — see `docs/TDD.md` §5
- ArUco 5×5 single marker chosen over CharucoBoard (credit-card-sized, clinic can hand to patient) — see `docs/BUILD_NOTES.md`
- Pigmentation: black-hat morphology, not ITA° (better signal on CLAHE-normalized ROI) — see `docs/BUILD_NOTES.md`
- 4 ROIs as rectangles, not polygon masks (debuggable, contiguous patches for texture metrics) — see `docs/TDD.md` §2
- Gate-failed photos can still be scored ("僅供參考") but flagged `quality_passed=False` in DB so they don't contaminate the longitudinal baseline — see `app.py:302`

---

## 10. Session 2 — live face-mesh capture

Replaced the blind `st.camera_input` / `st.file_uploader` flow with a Streamlit
custom component that runs **MediaPipe Tasks Vision in the browser** and
auto-captures only when pose, distance, and stability all pass. This turns the
demo's Scene 3 ("the gate moment") from *"reject after the fact"* into *"guide
in real time"* — the same depth-area behaviour, but now visible during capture
rather than only after.

### New files

| Path | Owns |
|---|---|
| `src/facetrack/components/__init__.py` | namespace marker |
| `src/facetrack/components/face_capture/__init__.py` | Python wrapper around `declare_component`. Auto-mirrors the vendored `face_landmarker.task` into the static frontend dir at import time so the iframe can fetch it same-origin (no Google CDN dependency). |
| `src/facetrack/components/face_capture/frontend/index.html` | The widget: dark-mode neon mesh overlay (478 dots + full tessellation + region-coloured contours), HUD with yaw/pitch/roll/size readouts, big animated countdown overlay, selfie-mirror display, in-UI debug log with copy-to-clipboard button. |

The frontend's mirrored `face_landmarker.task` is **gitignored** (`.gitignore`
line: `src/facetrack/components/face_capture/frontend/face_landmarker.task`)
— it's regenerated from the source-of-truth at
`src/facetrack/models/face_landmarker.task` on every Python import.

### Modified files

- **`app.py`** — `page_intake` now uses `face_capture(...)` as the primary
  tab, with `st.file_uploader` retained as a `fallback` tab. The widget returns
  `{front, left | None, right | None, session_id}`; the side photos are
  optional and don't participate in scoring (only the front photo feeds
  `score_visit`). Existing scoring / LLM / save flow is unchanged.
- **`src/facetrack/consistency_gate.py`** —
  - `evaluate()` gains `pose_mode: Literal["frontal", "profile_left", "profile_right"]`
  - Profile branches: `yaw <= -PROFILE_YAW_MIN_DEG` (left) / `yaw >= +PROFILE_YAW_MIN_DEG` (right) + pitch ±`PROFILE_PITCH_TOLERANCE_DEG`
  - `_check_sharpness` now uses the face bounding box when landmarks are
    present (background no longer dilutes Laplacian variance); falls back to
    full frame when no face is detected so the offline blur test still trips.
- **`src/facetrack/config.py`** — added live-capture knobs; relaxed
  webcam-unrealistic thresholds. See resolution log in §5.
- **`src/facetrack/db.py`** — `Visit` gains nullable `photo_left_path` /
  `photo_right_path`; `init_db()` performs zero-downtime SQLite migration via
  `ALTER TABLE ADD COLUMN`.
- **`tests/test_consistency_gate.py`** — added 5 pose-mode regression tests
  (frontal pass at 0°, profile_left pass at -70°, profile_right pass at +65°,
  profile_left rejects frontal pose, measurement dict carries the `mode` key).

### How the widget self-diagnoses

The HTML embeds an **in-UI debug log** (cyan-bordered scrolling box,
above the stage). Every setup step (`HEAD face_landmarker.task`, CDN import,
WASM fileset, GPU/CPU delegate fallback, `getUserMedia`) logs an `[hh:mm:ss.ms]`
line, colour-coded ok/warn/err. A "📋 複製 debug log" button copies the whole
log to clipboard for triage. This is the result of debugging sessions where the
opaque "模型錯誤" badge wasted ~30 min — never again.

### Things explicitly NOT done in session 2

- Profile photos do **not** participate in scoring. Their ROI definitions
  would need a separate hand-tuning pass (the current `LEFT_CHEEK_POLYGON` /
  `RIGHT_CHEEK_POLYGON` indices assume a frontal-aligned face).
- Mobile / iPad touch interaction is not optimised (component sized for
  laptop viewport, `iframe height = 1200px`).
- The vendored model file is copied per Python-process start; could be
  symlinked, but copy is platform-independent and only 3.6 MB.
- No live heatmap overlay during capture — that's a post-capture feature
  and `compose_intake_view` already handles it on the still photo.

---

## 11. Session 3 — history ROI overlay, Gemini backend, demo data

This session was about making the **history view** (`📋 就診歷史`) interactive
enough to drive the doctor↔patient conversation, plus a second LLM backend so
the demo isn't blocked on a single API key, plus seating Eric's own face in
the DB as a presentable case for the Loom recording.

### New files (committed in `f655d10`)

| Path | Owns |
|---|---|
| `src/facetrack/patient_service.py` | CRUD for `Patient` extracted from `app.py`: `create_patient`, `get_patient`, `list_patients`, `update_patient`, `soft_delete_patient`, `restore_patient`. Soft-delete means a flag flip, not a row delete — history stays intact. |
| `src/facetrack/score_display.py` | UI-side helpers: `to_health_score(metric, raw)` (inverts raw scores so "higher = better skin" across all 5 metrics, matching the radar/line-chart convention), `health_band(health)` → `(emoji, label_zh, color)`, plus the three colour constants used by the score cards. |
| `tests/conftest.py` | Shared fixtures (currently: temp SQLite DB per test, used by the new patient_service / score_display tests). |
| `tests/test_patient_service.py` | CRUD + soft-delete + restore + listing-excludes-soft-deleted contract. |
| `tests/test_score_display.py` | Inversion direction per metric (pigmentation/erythema/wrinkle/pore inverted; uniformity passthrough), band thresholds, colour assignment. |
| `.env.example` | Template for `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `LLM_MODEL`, `GEMINI_MODEL`, `LLM_BACKEND`. Real `.env` is gitignored. |
| `data/test_images/test_{1,2,3}.png` | Three CC0 test faces referenced by the deploy smoke-test in §6. |

### Modified files

- **`app.py`** —
  - **History view ROI overlay** (`page_history`): two checkbox toggles
    (Streamlit forbids nested expanders, so this is the workaround):
    - `🔬 顯示 ROI 訊號疊圖` — re-runs alignment on the stored front photo
      and shows `compose_intake_view(...)` with a metric selector + ROI box
      toggle. Heatmap defaults to pigmentation (the 皮秒雷射 primary metric).
    - `🧪 顯示各 ROI 局部影像（CLAHE 平衡後）` — four side-by-side ROI
      thumbnails for cross-visit comparison.
  - Two new `@st.cache_data` helpers — `_history_overlay_rgb(path, mtime,
    metric, show_roi)` and `_history_rois_rgb(path, mtime)` — so flipping
    indicators doesn't re-trigger MediaPipe. `(path, mtime)` keys mean
    overwriting a photo invalidates the cache automatically.
  - Imports `Gender`, `patient_service` and `score_display` (relocated from
    inline helpers).
- **`src/facetrack/llm_explainer.py`** — full rewrite of the backend layer.
  Now exposes a factory `get_explainer()` that picks Anthropic / Gemini /
  Mock based on `LLM_BACKEND` env var (or auto: Anthropic if key present,
  else Gemini, else Mock). Both real backends fall back to `MockExplainer`
  on API error — the demo never hard-fails. The interface still takes
  **scores only**, never pixels (non-negotiable, §7).
- **`src/facetrack/config.py`** — `GEMINI_API_KEY`, `GEMINI_MODEL`,
  `LLM_BACKEND` env wiring.
- **`src/facetrack/db.py`** — patient soft-delete column + helper used by
  `patient_service`.
- **`pyproject.toml` / `uv.lock`** — added `google-genai` for the Gemini
  backend.

### DB-only "demo bypass" — EricZou

There is **no code path** for per-patient bypass — quality gating is global
and stays global. Instead, Eric's three visits in the local SQLite DB
(`visits.id ∈ {10, 11, 12}`) were mutated directly: `quality_passed`
flipped to `True`, and the embedded `quality_report_json` had its
`pose.passed` / `exposure.passed` / `sharpness.passed` all set to `True`,
`failure_reasons_zh` emptied, `summary_zh` rewritten to the pass message.

This means:
- The fix is **specific to the local DB**. A fresh `seed --force` rebuilds
  the DB without these patches; for the Loom recording, do **not** re-seed
  after capturing Eric's photos.
- The Streamlit Cloud deploy gets a freshly-seeded DB, so EricZou won't
  exist there at all. If you want Eric's demo case on the cloud build,
  either re-do the capture against the deployed app **then** re-apply the
  same JSON mutation against the cloud DB, or just rely on the seed
  patients for that flow.

### Things explicitly NOT done in session 3

- The demo bypass is **not** generalised into a `DEMO_BYPASS_PATIENT_NAMES`
  config or a per-patient bypass flag. The user explicitly preferred a
  DB-level edit over an app.py whitelist, so the gate code stays clean.
- History view does **not** re-run the LLM explainer — it shows the
  stored `TreatmentNote` from intake time. Re-explaining a past visit
  would need a "regenerate" button; out of scope for the build challenge.
- No new tests for the history overlay block — it's pure UI glue around
  already-tested `compose_intake_view` / pipeline / scoring functions.

# Agent Handoff — FaceTrack CRM

> If you are an agent (Claude Code, Codex, Cursor, etc.) starting work on this repo,
> read this file first. It is the single source of truth for project status,
> known inconsistencies, and open decisions.
>
> **Last updated**: 2026-05-17 (end of session 1)
> **Deadline**: 2026-05-19 (default 48hr; brief allows extension with anticipated date)
>
> ## ⏭️ Resuming work? Jump to [§6 — Pickup checklist](#6-pickup-checklist-for-the-next-session)
>
> **Session 1 ended with everything Claude could do offline complete and pushed.**
> **4 items remain — all require Eric's hands (browser login, recording, sending).**
> ETA to submission from a fresh start: **~1.5–2 hours**.

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
| `docs/DEMO_STORYBOARD.md` | Scene-by-scene script for the 2–5 min Loom demo | Eric (recording) |
| `docs/figures/reproducibility.png` | The evidence chart embedded in TDD §3 | AI Fund panel |
| `scripts/reproducibility_evidence.py` | Regenerates the reproducibility chart | Agents + Eric |
| `scripts/benchmark.py` | Re-measures end-to-end pipeline latency | Agents + Eric |
| `docs/LIMITATIONS.md` | 6 failure modes + concrete Phase-2 mitigations | AI Fund panel |
| `docs/SUBMISSION_EMAIL.md` | Fill-in-the-blanks final email to Mike | Eric |

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

Currently open: **none** (as of 2026-05-17). If you find new drift, add a row.

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

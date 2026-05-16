# Agent Handoff — FaceTrack CRM

> If you are an agent (Claude Code, Codex, Cursor, etc.) starting work on this repo,
> read this file first. It is the single source of truth for project status,
> known inconsistencies, and open decisions.
>
> **Last updated**: 2026-05-17
> **Deadline**: 2026-05-19 (default 48hr; brief allows extension with anticipated date)

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

## 6. Open submission gaps (verbatim from brief's "What To Submit")

| Required | Status | Notes |
|---|---|---|
| Working prototype URL | ❌ Pending Streamlit Cloud deploy | Repo is GitHub-linked; one-click deploy from share.streamlit.io |
| 2–5 min demo video | ❌ Pending recording | Script ready at `docs/DEMO_STORYBOARD.md` |
| GitHub repo link | ✅ https://github.com/ericakcc/facetrack-crm (public) | |
| PRD 1–2 pages | ✅ `docs/PRD.md` | |
| TDD 1–2 pages | ✅ `docs/TDD.md` — covers imaging / reliability / workflow / consistency; §3 now includes reproducibility-evidence figure | |
| Build / authorship note | ✅ `docs/BUILD_NOTES.md` | |

**Test coverage** (defensible against deep code review):
- `tests/test_scoring_determinism.py` — 7 tests asserting bit-identical scoring output
- `tests/test_consistency_gate.py` — 7 tests covering all four gate branches + JSON-serialisability
- `tests/test_llm_explainer.py` — 4 tests on mock explainer
- `tests/test_app_imports.py` — smoke test
- **19 tests pass, fresh-clone-from-GitHub smoke-tested 2026-05-17**

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

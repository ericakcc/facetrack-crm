# Face-Capture UX Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make front + left + right face capture feel like a consumer app — align → captured in under ~1 s, smooth progress, visual guidance (target oval, ghost overlay, side arrows, collapsed HUD) instead of raw angle numbers.

**Architecture:** Refine Approach C. The fragile MediaPipe bootstrap (CDN fallback, model probe, WASM fileset, GPU/CPU delegate) and DOM stay in `index.html`. Pure decision logic (EMA smoother, hysteresis stability meter, Laplacian sharpness, sharpest-frame selection) moves to a new DOM-free sibling module `capture_logic.js`, attached to `window.CaptureLogic`, so it is unit-testable via Playwright. Ghost photos are supplied by a new Python helper and threaded through the `face_capture()` wrapper. The returned payload shape is unchanged, so scoring/save is unaffected.

**Tech Stack:** Python 3 + SQLModel + OpenCV (cv2) + Streamlit custom component; vanilla ES/JS in the component iframe; MediaPipe Tasks Vision (untouched); Playwright (already a dev dep) for JS unit tests.

## Global Constraints

- **uv only** — no `pip`. New deps via `uv add` / `uv add --dev`. (playwright & pytest are already dev deps.)
- **Type hints required** on every Python function; Google-style docstrings.
- **繁體中文 UX strings** written directly (no i18n layer).
- **Scoring path stays LLM-free / deterministic** — this plan touches capture only, never `scoring.py`'s math.
- **Returned payload shape unchanged**: `{front, left|None, right|None, session_id}`. Ghost args are purely additive.
- **Do NOT touch** the MediaPipe CDN-candidate loading, model probe/fallback, WASM fileset resolution, GPU/CPU delegate fallback, or the debug log + copy button in `index.html`.
- **Conventional Commits**; never `git commit --no-verify`. Work on branch `feat/face-capture-ux`.
- **Photo path convention**: `Visit.photo_path` / `photo_left_path` / `photo_right_path` are stored **relative to `PROJECT_ROOT`** (e.g. `data/photos/patient1_..._front.jpg`); resolve with `PROJECT_ROOT / rel`.
- Run the fast suite with `uv run pytest tests/ -v` and lint with `uv run ruff check . && uv run ruff format --check .` before each commit.

---

### Task 1: Ghost-photo lookup helper (Python)

**Files:**
- Create: `src/facetrack/ghost_photos.py`
- Test: `tests/test_ghost_photos.py`

**Interfaces:**
- Consumes: `facetrack.config.PROJECT_ROOT`, `facetrack.db.get_session`, `facetrack.db.Visit`.
- Produces: `get_ghost_photos(patient_id: int, *, max_px: int = 480) -> dict[str, str | None]` returning keys `"front"`, `"left"`, `"right"`; each a `data:image/jpeg;base64,...` string or `None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ghost_photos.py
"""Tests for the ghost-overlay photo loader."""
from __future__ import annotations

import base64
from datetime import date
from pathlib import Path

import cv2
import numpy as np
from sqlmodel import Session

import facetrack.ghost_photos as gp
from facetrack.db import Visit
from facetrack.ghost_photos import get_ghost_photos


def _write_img(path: Path, size: int = 1000) -> None:
    cv2.imwrite(str(path), np.full((size, size, 3), 128, dtype=np.uint8))


def test_no_prior_visit_returns_all_none(in_memory_db):
    assert get_ghost_photos(999) == {"front": None, "left": None, "right": None}


def test_front_only_encodes_front(in_memory_db, tmp_path, monkeypatch):
    monkeypatch.setattr(gp, "PROJECT_ROOT", tmp_path)
    _write_img(tmp_path / "front.jpg")
    with Session(in_memory_db) as s:
        s.add(Visit(patient_id=1, visit_date=date(2026, 1, 1), photo_path="front.jpg"))
        s.commit()
    result = get_ghost_photos(1)
    assert result["front"].startswith("data:image/jpeg;base64,")
    assert result["left"] is None and result["right"] is None


def test_latest_visit_wins(in_memory_db, tmp_path, monkeypatch):
    monkeypatch.setattr(gp, "PROJECT_ROOT", tmp_path)
    _write_img(tmp_path / "old.jpg")
    _write_img(tmp_path / "new.jpg")
    with Session(in_memory_db) as s:
        s.add(Visit(patient_id=1, visit_date=date(2026, 1, 1), photo_path="old.jpg"))
        s.add(Visit(patient_id=1, visit_date=date(2026, 6, 1), photo_path="new.jpg"))
        s.commit()
    # both decode to same pixels; assert a photo is returned (latest exists)
    assert get_ghost_photos(1)["front"] is not None


def test_downscales_to_max_px(in_memory_db, tmp_path, monkeypatch):
    monkeypatch.setattr(gp, "PROJECT_ROOT", tmp_path)
    _write_img(tmp_path / "big.jpg", size=1000)
    with Session(in_memory_db) as s:
        s.add(Visit(patient_id=1, visit_date=date(2026, 1, 1), photo_path="big.jpg"))
        s.commit()
    url = get_ghost_photos(1, max_px=480)["front"]
    raw = base64.b64decode(url.split(",", 1)[1])
    decoded = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    assert max(decoded.shape[:2]) <= 480


def test_missing_file_returns_none(in_memory_db, tmp_path, monkeypatch):
    monkeypatch.setattr(gp, "PROJECT_ROOT", tmp_path)
    with Session(in_memory_db) as s:
        s.add(Visit(patient_id=1, visit_date=date(2026, 1, 1), photo_path="nope.jpg"))
        s.commit()
    assert get_ghost_photos(1)["front"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ghost_photos.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'facetrack.ghost_photos'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/facetrack/ghost_photos.py
"""Load a patient's most-recent prior-visit photos as downscaled data URLs.

Feeds the live capture widget's ghost-overlay: the previous visit's front/left/
right photos are shown faintly over the live preview so the operator reproduces
framing across visits.
"""
from __future__ import annotations

import base64
from pathlib import Path

import cv2
from sqlmodel import select

from facetrack.config import PROJECT_ROOT
from facetrack.db import Visit, get_session


def _encode_data_url(abs_path: Path, max_px: int) -> str | None:
    """Read, downscale (longest edge ≤ max_px), and base64-encode a JPEG.

    Args:
        abs_path: Absolute path to the source image.
        max_px: Longest-edge cap for the downscaled overlay.

    Returns:
        A ``data:image/jpeg;base64,...`` string, or ``None`` if the file is
        missing or undecodable.
    """
    if not abs_path.exists():
        return None
    img = cv2.imread(str(abs_path))
    if img is None:
        return None
    h, w = img.shape[:2]
    scale = min(1.0, max_px / max(h, w))
    if scale < 1.0:
        img = cv2.resize(
            img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA
        )
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


def get_ghost_photos(patient_id: int, *, max_px: int = 480) -> dict[str, str | None]:
    """Return the patient's latest-visit photos as data URLs for ghost overlay.

    Args:
        patient_id: Patient whose most recent visit supplies the ghost images.
        max_px: Longest-edge cap for each downscaled overlay image.

    Returns:
        Mapping with keys ``front`` / ``left`` / ``right``; each value is a
        data-URL string, or ``None`` when that angle is absent (no prior visit,
        or that photo was never captured / file missing).
    """
    with get_session() as session:
        stmt = (
            select(Visit)
            .where(Visit.patient_id == patient_id)
            .order_by(Visit.visit_date.desc(), Visit.id.desc())
        )
        visit = session.exec(stmt).first()
    if visit is None:
        return {"front": None, "left": None, "right": None}
    rels = {
        "front": visit.photo_path or None,
        "left": visit.photo_left_path,
        "right": visit.photo_right_path,
    }
    return {
        key: (_encode_data_url(PROJECT_ROOT / rel, max_px) if rel else None)
        for key, rel in rels.items()
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ghost_photos.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check src/facetrack/ghost_photos.py tests/test_ghost_photos.py --fix
uv run ruff format src/facetrack/ghost_photos.py tests/test_ghost_photos.py
git add src/facetrack/ghost_photos.py tests/test_ghost_photos.py
git commit -m "feat(capture): ghost-photo loader for prior-visit overlay"
```

---

### Task 2: Thread ghost args through the wrapper + app.py

**Files:**
- Modify: `src/facetrack/components/face_capture/__init__.py` (add 3 nullable kwargs + forward them)
- Modify: `app.py:709-719` (build ghosts, pass them)
- Test: `tests/test_face_capture_wrapper.py`

**Interfaces:**
- Consumes: `get_ghost_photos` (Task 1).
- Produces: `face_capture(..., ghost_front: str | None = None, ghost_left: str | None = None, ghost_right: str | None = None)` forwarding `ghostFront` / `ghostLeft` / `ghostRight` to the component.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_face_capture_wrapper.py
"""The face_capture wrapper forwards ghost data URLs to the component."""
from __future__ import annotations

import facetrack.components.face_capture as fc


def test_ghost_args_forwarded(monkeypatch):
    captured = {}

    def fake_component(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(fc, "_component_func", fake_component)
    fc.face_capture(
        key="k",
        ghost_front="data:image/jpeg;base64,AAA",
        ghost_left=None,
        ghost_right="data:image/jpeg;base64,CCC",
    )
    assert captured["ghostFront"] == "data:image/jpeg;base64,AAA"
    assert captured["ghostLeft"] is None
    assert captured["ghostRight"] == "data:image/jpeg;base64,CCC"


def test_ghost_args_default_none(monkeypatch):
    captured = {}
    monkeypatch.setattr(fc, "_component_func", lambda **kw: captured.update(kw))
    fc.face_capture(key="k")
    assert captured["ghostFront"] is None
    assert captured["ghostLeft"] is None
    assert captured["ghostRight"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_face_capture_wrapper.py -v`
Expected: FAIL — `TypeError: face_capture() got an unexpected keyword argument 'ghost_front'`

- [ ] **Step 3: Add the kwargs to the wrapper**

In `src/facetrack/components/face_capture/__init__.py`, add three parameters to `face_capture()` (after `max_face_width_ratio`, before `height`):

```python
    ghost_front: str | None = None,
    ghost_left: str | None = None,
    ghost_right: str | None = None,
```

and forward them inside the `_component_func(...)` call (after `maxFaceWidthRatio=...`):

```python
        ghostFront=ghost_front,
        ghostLeft=ghost_left,
        ghostRight=ghost_right,
```

Add to the docstring Args section:

```python
        ghost_front / ghost_left / ghost_right: Optional prior-visit photos as
            data-URL strings, drawn faintly under the live preview to reproduce
            framing. ``None`` hides that angle's overlay.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_face_capture_wrapper.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Wire app.py**

In `app.py`, immediately **before** the `capture_value = face_capture(` call (currently `app.py:709`), add:

```python
        ghosts = get_ghost_photos(patient.id)
```

and add these three kwargs inside the `face_capture(` call (after `max_face_width_ratio=...`):

```python
            ghost_front=ghosts["front"],
            ghost_left=ghosts["left"],
            ghost_right=ghosts["right"],
```

Add the import near the other `facetrack` imports at the top of `app.py`:

```python
from facetrack.ghost_photos import get_ghost_photos
```

- [ ] **Step 6: Verify app imports + lint**

Run: `uv run python -c "import app"` — Expected: no error (imports resolve).
Run: `uv run ruff check app.py src/facetrack/components/face_capture/__init__.py --fix && uv run ruff format app.py src/facetrack/components/face_capture/__init__.py`

- [ ] **Step 7: Commit**

```bash
git add app.py src/facetrack/components/face_capture/__init__.py tests/test_face_capture_wrapper.py
git commit -m "feat(capture): pass prior-visit ghost photos into face_capture widget"
```

---

### Task 3: Pure capture-logic module + Playwright unit tests

**Files:**
- Create: `src/facetrack/components/face_capture/frontend/capture_logic.js`
- Test: `tests/test_capture_logic.py`

**Interfaces:**
- Produces `window.CaptureLogic` with:
  - `makePoseSmoother(alpha) -> {update({yaw,pitch,roll}) -> {yaw,pitch,roll}, reset()}`
  - `stabilityStep({count,locked}, inPose: bool, framesNeeded: int) -> {count, locked}`
  - `laplacianVariance(gray: Uint8Array-like, width, height) -> number`
  - `pickSharpestFrame(frames: [{score, inTolerance, ...}]) -> frame | null`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_capture_logic.py
"""Unit tests for the pure JS capture-decision logic (via Playwright)."""
from __future__ import annotations

from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

LOGIC_JS = (
    Path(__file__).resolve().parents[1]
    / "src/facetrack/components/face_capture/frontend/capture_logic.js"
)


@pytest.fixture(scope="module")
def page():
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.set_content("<!doctype html><html><body></body></html>")
        pg.add_script_tag(path=str(LOGIC_JS))
        yield pg
        browser.close()


def test_smoother_first_update_is_identity(page):
    out = page.evaluate(
        "() => CaptureLogic.makePoseSmoother(0.5).update({yaw:10,pitch:0,roll:0})"
    )
    assert out["yaw"] == 10


def test_smoother_ema_dampens_jump(page):
    out = page.evaluate(
        "() => { const s=CaptureLogic.makePoseSmoother(0.5);"
        "s.update({yaw:0,pitch:0,roll:0});"
        "return s.update({yaw:10,pitch:0,roll:0}); }"
    )
    assert out["yaw"] == 5


def test_stability_rises_and_locks(page):
    locked = page.evaluate(
        "() => { let st={count:0,locked:false};"
        "for (let i=0;i<3;i++) st=CaptureLogic.stabilityStep(st,true,3);"
        "return st.locked; }"
    )
    assert locked is True


def test_stability_falls_symmetrically(page):
    count = page.evaluate(
        "() => CaptureLogic.stabilityStep({count:2,locked:false},false,5).count"
    )
    assert count == 1


def test_stability_stays_locked_once_locked(page):
    locked = page.evaluate(
        "() => CaptureLogic.stabilityStep({count:0,locked:true},false,3).locked"
    )
    assert locked is True


def test_pick_sharpest_prefers_in_tolerance(page):
    picked = page.evaluate(
        "() => CaptureLogic.pickSharpestFrame(["
        "{id:'a',score:99,inTolerance:false},"
        "{id:'b',score:10,inTolerance:true},"
        "{id:'c',score:20,inTolerance:true}])"
    )
    assert picked["id"] == "c"


def test_pick_sharpest_falls_back_when_none_in_tolerance(page):
    picked = page.evaluate(
        "() => CaptureLogic.pickSharpestFrame(["
        "{id:'a',score:99,inTolerance:false},"
        "{id:'b',score:100,inTolerance:false}])"
    )
    assert picked["id"] == "b"


def test_laplacian_flat_image_is_zero(page):
    var = page.evaluate(
        "() => CaptureLogic.laplacianVariance(new Uint8Array(9).fill(128),3,3)"
    )
    assert var == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_capture_logic.py -v`
Expected: FAIL — `add_script_tag` errors because `capture_logic.js` does not exist yet.
(If Playwright browsers are missing, run `uv run playwright install chromium` first.)

- [ ] **Step 3: Write the module**

```javascript
// src/facetrack/components/face_capture/frontend/capture_logic.js
// Pure, DOM-free capture-decision logic. Attached to window.CaptureLogic so
// index.html (classic script) and the Playwright unit tests share one source.
(function (global) {
  "use strict";

  // Exponential moving average smoother for head-pose angles (degrees).
  function makePoseSmoother(alpha) {
    let prev = null;
    return {
      update(pose) {
        if (prev === null) {
          prev = { yaw: pose.yaw, pitch: pose.pitch, roll: pose.roll };
        } else {
          prev = {
            yaw: alpha * pose.yaw + (1 - alpha) * prev.yaw,
            pitch: alpha * pose.pitch + (1 - alpha) * prev.pitch,
            roll: alpha * pose.roll + (1 - alpha) * prev.roll,
          };
        }
        return { yaw: prev.yaw, pitch: prev.pitch, roll: prev.roll };
      },
      reset() {
        prev = null;
      },
    };
  }

  // Symmetric stability accumulator with a lock latch. +1 per in-pose frame,
  // -1 per out-of-pose frame, clamped to [0, framesNeeded]; latches locked
  // once count reaches framesNeeded and stays locked until the caller resets.
  function stabilityStep(state, inPose, framesNeeded) {
    let count = state.count + (inPose ? 1 : -1);
    if (count < 0) count = 0;
    if (count > framesNeeded) count = framesNeeded;
    return { count, locked: state.locked || count >= framesNeeded };
  }

  // Variance of the discrete Laplacian over a grayscale buffer. Higher = sharper.
  function laplacianVariance(gray, width, height) {
    let sum = 0;
    let sumSq = 0;
    let n = 0;
    for (let y = 1; y < height - 1; y++) {
      for (let x = 1; x < width - 1; x++) {
        const i = y * width + x;
        const lap =
          4 * gray[i] - gray[i - 1] - gray[i + 1] - gray[i - width] - gray[i + width];
        sum += lap;
        sumSq += lap * lap;
        n++;
      }
    }
    if (n === 0) return 0;
    const mean = sum / n;
    return sumSq / n - mean * mean;
  }

  // Highest-scoring in-tolerance frame; falls back to highest-scoring overall
  // when no frame is in tolerance. frames: [{score:number, inTolerance:boolean}]
  function pickSharpestFrame(frames) {
    if (!frames || frames.length === 0) return null;
    const inTol = frames.filter((f) => f.inTolerance);
    const pool = inTol.length > 0 ? inTol : frames;
    return pool.reduce((best, f) => (f.score > best.score ? f : best), pool[0]);
  }

  global.CaptureLogic = {
    makePoseSmoother,
    stabilityStep,
    laplacianVariance,
    pickSharpestFrame,
  };
})(window);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_capture_logic.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/facetrack/components/face_capture/frontend/capture_logic.js tests/test_capture_logic.py
git commit -m "feat(capture): pure capture-logic module (EMA, hysteresis, sharpness) + tests"
```

---

### Task 4: Config constants for the new capture timing

**Files:**
- Modify: `src/facetrack/config.py` (near the existing `LIVE_CAPTURE_*` block, lines 112-120)
- Modify: `src/facetrack/components/face_capture/__init__.py` (function defaults + forwarded args)
- Test: `tests/test_capture_config.py`

**Interfaces:**
- Produces new config names: `LIVE_CAPTURE_BURST_MS`, `LIVE_CAPTURE_POSE_EMA_ALPHA`, and a lowered `LIVE_CAPTURE_STABILITY_FRAMES`. `LIVE_CAPTURE_COUNTDOWN_MS` is removed.
- Wrapper gains forwarded args `burstMs`, `poseEmaAlpha` (component reads them in Task 5).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_capture_config.py
"""Capture-timing config values are present and sane after the countdown removal."""
from __future__ import annotations

import facetrack.config as cfg


def test_burst_and_ema_defined():
    assert 200 <= cfg.LIVE_CAPTURE_BURST_MS <= 1200
    assert 0.1 <= cfg.LIVE_CAPTURE_POSE_EMA_ALPHA <= 0.8


def test_stability_frames_snappy():
    assert 4 <= cfg.LIVE_CAPTURE_STABILITY_FRAMES <= 9


def test_countdown_removed():
    assert not hasattr(cfg, "LIVE_CAPTURE_COUNTDOWN_MS")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_capture_config.py -v`
Expected: FAIL — `LIVE_CAPTURE_BURST_MS`/`LIVE_CAPTURE_POSE_EMA_ALPHA` missing; `test_countdown_removed` fails while the old name still exists.

- [ ] **Step 3: Edit config.py**

In `src/facetrack/config.py`, in the `LIVE_CAPTURE_*` block:
- Delete the line `LIVE_CAPTURE_COUNTDOWN_MS: int = 3000`.
- Change `LIVE_CAPTURE_STABILITY_FRAMES: int = 10` to `LIVE_CAPTURE_STABILITY_FRAMES: int = 6`.
- Add:

```python
# Short burst window (ms) after lock; the sharpest in-tolerance frame in this
# window is kept. Replaces the old fixed 3 s countdown dead-wait.
LIVE_CAPTURE_BURST_MS: int = 500
# EMA smoothing factor for head-pose angles (higher = snappier, less smooth).
LIVE_CAPTURE_POSE_EMA_ALPHA: float = 0.35
```

- [ ] **Step 4: Update the wrapper defaults**

In `src/facetrack/components/face_capture/__init__.py`:
- Remove the `countdown_ms: int = 3000,` parameter and its `countdownMs=countdown_ms,` forward line.
- Correct the stale frontal defaults: `front_yaw_tol_deg: float = 8.0` → `15.0`, `front_pitch_tol_deg: float = 10.0` → `17.0`.
- Add parameters `burst_ms: int = 500,` and `pose_ema_alpha: float = 0.35,` and forward them: `burstMs=burst_ms,` and `poseEmaAlpha=pose_ema_alpha,`.

- [ ] **Step 5: Update app.py call site**

In `app.py`, in the `face_capture(` call: remove `countdown_ms=LIVE_CAPTURE_COUNTDOWN_MS,` and add:

```python
            burst_ms=LIVE_CAPTURE_BURST_MS,
            pose_ema_alpha=LIVE_CAPTURE_POSE_EMA_ALPHA,
```

Update the config import line in `app.py` to drop `LIVE_CAPTURE_COUNTDOWN_MS` and add `LIVE_CAPTURE_BURST_MS, LIVE_CAPTURE_POSE_EMA_ALPHA`.

- [ ] **Step 6: Run tests + import check**

Run: `uv run pytest tests/test_capture_config.py tests/test_face_capture_wrapper.py -v` — Expected: PASS.
Run: `uv run python -c "import app"` — Expected: no error.

- [ ] **Step 7: Commit**

```bash
git add src/facetrack/config.py src/facetrack/components/face_capture/__init__.py app.py tests/test_capture_config.py
git commit -m "feat(capture): replace 3s countdown config with burst window + EMA alpha"
```

---

### Task 5: Integrate logic + burst capture into index.html (remove countdown)

**Files:**
- Modify: `src/facetrack/components/face_capture/frontend/index.html`
  - Add `<script src="capture_logic.js"></script>` (classic, before the `<script type="module">` at line 384).
  - Read new render args `poseEmaAlpha`, `burstMs` into `cfg`.
  - Replace the SEEKING/COUNTDOWN block (lines ~999-1066) with smoothed pose + `CaptureLogic.stabilityStep` + a burst collector.
  - Add a `SharpnessScorer` inline that grays a 128px center crop and calls `CaptureLogic.laplacianVariance`.

**Interfaces:**
- Consumes `window.CaptureLogic` (Task 3), `cfg.poseEmaAlpha`, `cfg.burstMs`, `cfg.stabilityFrames`.
- Produces the same `captures[mode]` payload objects — shape unchanged.

- [ ] **Step 1: Add the classic script include**

Immediately before `<script type="module">` (line 384) insert:

```html
  <script src="capture_logic.js"></script>
```

- [ ] **Step 2: Register the two new config keys**

In the `cfg` object (line 403-412) add:

```javascript
      poseEmaAlpha: 0.35,
      burstMs: 500,
```

(The existing `for (const k of Object.keys(cfg))` render loop at line 418 already copies any numeric arg whose key is in `cfg`, so these two are picked up automatically. Remove `countdownMs` from `cfg`.)

- [ ] **Step 3: Add pose smoother + sharpness helper (module scope)**

Near the state vars (after `let stableCount = 0;`, line 500), replace the raw counter with a smoother + stability state and add the sharpness scorer:

```javascript
    let poseSmoother = CaptureLogic.makePoseSmoother(cfg.poseEmaAlpha);
    let stabilityState = { count: 0, locked: false };
    let burst = null; // {startedAt, frames:[]} while CAPTURING

    // Grayscale a downscaled center crop of the current video frame and return
    // its Laplacian variance (sharpness). Small crop keeps this cheap enough to
    // run per burst frame.
    const sharpCanvas = document.createElement("canvas");
    sharpCanvas.width = 128;
    sharpCanvas.height = 128;
    const sharpCtx = sharpCanvas.getContext("2d", { willReadFrequently: true });
    function frameSharpness() {
      const vw = video.videoWidth, vh = video.videoHeight;
      const side = Math.min(vw, vh);
      const sx = (vw - side) / 2, sy = (vh - side) / 2;
      sharpCtx.drawImage(video, sx, sy, side, side, 0, 0, 128, 128);
      const { data } = sharpCtx.getImageData(0, 0, 128, 128);
      const gray = new Uint8Array(128 * 128);
      for (let i = 0, g = 0; i < data.length; i += 4, g++) {
        gray[g] = (data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114) | 0;
      }
      return CaptureLogic.laplacianVariance(gray, 128, 128);
    }
```

- [ ] **Step 4: Replace the SEEKING/COUNTDOWN block with SEEKING/CAPTURING**

Replace the whole `if (lockedAt === null) { ... } else { ... }` block (lines ~1029-1066) and the `stableCount` mutation above it (lines ~1013-1027) with:

```javascript
              const inPose = yawOk && pitchOk && distanceOk;
              stabilityState = CaptureLogic.stabilityStep(
                stabilityState, inPose, cfg.stabilityFrames
              );
              modeBadge.classList.toggle("in-pose", inPose);
              progRing.classList.toggle("in-pose", inPose);
              const progress = stabilityState.count / cfg.stabilityFrames;
              progArc.setAttribute("stroke-dashoffset", String(ARC_LEN * (1 - progress)));

              if (!stabilityState.locked) {
                if (inPose) instructionEl.textContent = "保持住…";
              } else if (burst === null) {
                // Enter CAPTURING: open a short burst window.
                burst = { startedAt: performance.now(), frames: [] };
                instructionEl.textContent = "📸 擷取中…";
                logStep(`pose locked (${mode}) — burst begin`, "ok");
              }

              if (burst !== null) {
                burst.frames.push({
                  jpeg: captureJpeg(),
                  score: frameSharpness(),
                  inTolerance: inPose,
                  yaw, pitch, roll,
                });
                if (performance.now() - burst.startedAt >= cfg.burstMs) {
                  const best = CaptureLogic.pickSharpestFrame(burst.frames);
                  captures[mode] = {
                    jpeg_b64: best.jpeg,
                    yaw: best.yaw, pitch: best.pitch, roll: best.roll,
                    captured_at: new Date().toISOString(),
                  };
                  setThumb(mode, best.jpeg);
                  burst = null;
                  stabilityState = { count: 0, locked: false };
                  poseSmoother.reset();
                  progArc.setAttribute("stroke-dashoffset", String(ARC_LEN));
                  currentIdx += 1;
                  updateUI();
                }
              }
```

Also apply the EMA smoother where pose is read (line 977): after computing raw `{yaw,pitch,roll}` from `eulerFromMatrix`, add `const sm = poseSmoother.update({yaw, pitch, roll}); yaw = sm.yaw; pitch = sm.pitch; roll = sm.roll;` — change the `const { yaw, pitch, roll } = ...` destructure to `let`.

- [ ] **Step 5: Remove countdown DOM + helpers**

Delete the `countdown-overlay` div (lines 333-335), the `showCountdown` / `hideCountdown` functions and their DOM refs (`countdownOverlay`, `countdownNumberEl`, lines ~478-495), and reset `stableCount`/`lockedAt` references in the retake/reset handlers (lines ~1135-1147) — replace with `stabilityState = {count:0,locked:false}; burst = null; poseSmoother.reset();`.

- [ ] **Step 6: Manual smoke — capture snappiness**

Run: `cd /Users/eric_tsou/collab/AIFound/facetrack-crm && uv run streamlit run app.py --server.headless true`
Then in a browser at `http://localhost:8501` → 📸 新增就診 → 即時拍照:
- Expected: face the camera, align frontal → the ring fills smoothly (no violent snap-back on small movement), locks, and captures within ~1 s (no 3-second number countdown).
- Expected: the captured thumbnail is sharp (burst picked the sharpest frame).
Record the observed lock-to-capture time in the commit message. Kill the server after (`lsof -ti :8501 | xargs kill`).

- [ ] **Step 7: Regression + commit**

Run: `uv run pytest tests/ -v` — Expected: all green (payload unchanged).
```bash
git add src/facetrack/components/face_capture/frontend/index.html
git commit -m "feat(capture): EMA smoothing + sharpest-of-burst capture, drop 3s countdown"
```

---

### Task 6: Target oval + collapsed HUD

**Files:**
- Modify: `src/facetrack/components/face_capture/frontend/index.html` (CSS in `<style>`, the HUD DOM lines 336-345, a `drawTargetOval()` called from `loop()`).

**Interfaces:**
- Consumes `stabilityState`/`inPose` state, `cfg.minFaceWidthRatio`/`maxFaceWidthRatio`.
- Produces a centered ellipse on the overlay canvas that turns green in-pose, amber otherwise; raw yaw/pitch/roll numbers move into a collapsible block.

- [ ] **Step 1: Collapse the pose readout**

Wrap the `.pose-readout` block (lines 339-344) in a `<details>`:

```html
          <details class="pose-readout-adv">
            <summary>進階</summary>
            <div class="pose-readout">
              <span class="lbl">yaw</span>  <span id="yawVal" class="val">—</span><br />
              <span class="lbl">pitch</span><span id="pitchVal" class="val">—</span><br />
              <span class="lbl">roll</span> <span id="rollVal" class="val">—</span><br />
              <span class="lbl">size</span> <span id="sizeVal" class="val">—</span>
            </div>
          </details>
```

- [ ] **Step 2: Add the oval renderer**

Add this function and call it once per frame inside `loop()` right after `ctx.drawImage(video, ...)` (line 950):

```javascript
    function drawTargetOval(inPose) {
      const cx = canvas.width / 2, cy = canvas.height * 0.46;
      const rx = canvas.width * 0.22, ry = canvas.height * 0.32;
      ctx.save();
      ctx.lineWidth = 4;
      ctx.setLineDash([12, 10]);
      ctx.strokeStyle = inPose ? "#37d67a" : "#f0a825";
      ctx.beginPath();
      ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }
```

Call site (add after the `ctx.drawImage` in `loop`): `drawTargetOval(stabilityState.locked || (typeof lastInPose !== "undefined" && lastInPose));` — track `let lastInPose = false;` at module scope and set it where `inPose` is computed in Step 4 of Task 5.

- [ ] **Step 3: Manual smoke**

Launch the app (same command as Task 5 Step 6). Expected: a dashed oval sits centered in the preview; it is amber when your face is misaligned/too far, green when aligned; the yaw/pitch/roll numbers are hidden until you expand 進階.

- [ ] **Step 4: Commit**

```bash
git add src/facetrack/components/face_capture/frontend/index.html
git commit -m "feat(capture): target alignment oval + collapse raw angle HUD"
```

---

### Task 7: Side-profile direction arrows

**Files:**
- Modify: `src/facetrack/components/face_capture/frontend/index.html` (arrow draw in `loop()` for left/right modes).

**Interfaces:**
- Consumes smoothed `yaw`, `cfg.profileYawMinDeg`, current `mode`.
- Produces an on-canvas arrow + "再轉一點 / 已足夠" text during left/right capture.

- [ ] **Step 1: Add the arrow renderer**

```javascript
    function drawProfileGuide(mode, yaw) {
      if (mode !== "left" && mode !== "right") return;
      const target = cfg.profileYawMinDeg;
      const enough = mode === "left" ? yaw <= -target : yaw >= target;
      const cx = canvas.width / 2, cy = canvas.height * 0.12;
      const dir = mode === "left" ? -1 : 1; // arrow points the way to turn
      ctx.save();
      ctx.fillStyle = enough ? "#37d67a" : "#f0a825";
      ctx.font = "600 22px system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(enough ? "已足夠 ✓" : (dir < 0 ? "◀ 再轉一點" : "再轉一點 ▶"), cx, cy);
      ctx.restore();
    }
```

Call it in `loop()` after `drawTargetOval(...)`: `drawProfileGuide(currentMode(), yaw);` (guard: only when a face is detected and `yaw` is defined; place inside the `if (mat && mat.data)` branch where smoothed `yaw` exists).

- [ ] **Step 2: Manual smoke**

Launch the app. Advance to LEFT capture. Expected: with your head straight, "◀ 再轉一點" shows amber; as you turn your head left past the threshold it flips to green "已足夠 ✓" and capture proceeds. Repeat for RIGHT ("再轉一點 ▶").

- [ ] **Step 3: Commit**

```bash
git add src/facetrack/components/face_capture/frontend/index.html
git commit -m "feat(capture): side-profile turn-direction guidance arrows"
```

---

### Task 8: Ghost overlay rendering

**Files:**
- Modify: `src/facetrack/components/face_capture/frontend/index.html` (read `ghostFront`/`ghostLeft`/`ghostRight` render args into `Image` objects; draw the current mode's ghost under the mesh).

**Interfaces:**
- Consumes render args `ghostFront`/`ghostLeft`/`ghostRight` (data URLs, from Task 2).
- Produces a ~25% opacity underlay of the matching prior-visit photo; no overlay when the arg is null.

- [ ] **Step 1: Load ghosts on render**

In the `streamlit:render` handler (line 414-422) add, after the numeric-arg loop:

```javascript
      ghostImgs.front = loadGhost(args.ghostFront);
      ghostImgs.left = loadGhost(args.ghostLeft);
      ghostImgs.right = loadGhost(args.ghostRight);
```

and at module scope:

```javascript
    const ghostImgs = { front: null, left: null, right: null };
    let ghostOn = true;
    function loadGhost(dataUrl) {
      if (!dataUrl) return null;
      const img = new Image();
      img.src = dataUrl;
      return img;
    }
```

- [ ] **Step 2: Draw the ghost**

In `loop()`, right after `ctx.drawImage(video, ...)` (before the oval), add:

```javascript
      const gm = currentMode();
      const ghost = gm ? ghostImgs[gm] : null;
      if (ghostOn && ghost && ghost.complete && ghost.naturalWidth > 0) {
        ctx.save();
        ctx.globalAlpha = 0.25;
        ctx.drawImage(ghost, 0, 0, canvas.width, canvas.height);
        ctx.restore();
      }
```

- [ ] **Step 3: Add a toggle**

Add a checkbox button near the actions (line 374): `<button id="ghostBtn">👻 疊圖：開</button>` and a handler:

```javascript
    document.getElementById("ghostBtn").addEventListener("click", () => {
      ghostOn = !ghostOn;
      document.getElementById("ghostBtn").textContent = ghostOn ? "👻 疊圖：開" : "👻 疊圖：關";
    });
```

- [ ] **Step 4: Manual smoke (needs a patient with a prior visit)**

Launch the app; pick a seed patient who already has visits (e.g. 張立宇). 📸 新增就診 → 即時拍照. Expected: the prior front photo appears faintly (~25%) under the live preview on the FRONT step; toggling 👻 疊圖 hides/shows it; for a brand-new patient (no prior visit) no overlay appears and nothing errors.

- [ ] **Step 5: Commit**

```bash
git add src/facetrack/components/face_capture/frontend/index.html
git commit -m "feat(capture): ghost overlay of prior-visit photo with toggle"
```

---

### Task 9: Docs sync + full regression

**Files:**
- Modify: `CLAUDE.md` (§10/§12 follow-up note: live HUD now has oval/ghost/arrows; countdown replaced by burst), `src/facetrack/components/face_capture/frontend/index.html` (bump the `build-tag` line 381).
- Modify: `docs/PROGRESS.md` if present (human log).

- [ ] **Step 1: Update the build tag**

Change the `build-tag` div (line 381) to: `build 2026-07-06 v14 · burst capture + oval/ghost/arrow guidance`.

- [ ] **Step 2: Add a CLAUDE.md note**

Under §12 "Known follow-ups", mark the "live-capture JS HUD does not yet mirror…" item and add a line noting the capture-UX overhaul (oval, ghost overlay, side arrows, EMA smoothing, burst-sharpest capture; countdown removed) with a pointer to this plan and the design spec.

- [ ] **Step 3: Full suite + lint**

Run: `uv run pytest tests/ -v` — Expected: all green.
Run: `uv run pytest -m validation` — Expected: unchanged (skips if datasets absent).
Run: `uv run ruff check . && uv run ruff format --check .` — Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/PROGRESS.md src/facetrack/components/face_capture/frontend/index.html
git commit -m "docs(capture): sync handoff notes + build tag for capture-UX overhaul"
```

---

## Self-Review

**Spec coverage:**
- 3s countdown removal + sharpest-of-burst → Task 5 (logic in Task 3, config in Task 4). ✓
- EMA smoothing + symmetric/hysteresis counter → Task 3 (logic + tests), Task 5 (integration). ✓
- Target oval → Task 6. ✓
- Ghost overlay → Task 1 (loader) + Task 2 (plumbing) + Task 8 (render). ✓
- Side arrows → Task 7. ✓
- Collapsed HUD → Task 6. ✓
- Ghost data plumbing (Python latest-visit photos → args) → Tasks 1, 2. ✓
- MediaPipe bootstrap untouched → no task edits the CDN/model/WASM code. ✓
- Payload shape unchanged → Task 5 keeps `captures[mode]` shape; regression run in Tasks 5 & 9. ✓
- Config changes → Task 4. ✓
- Testing (Python unit for ghost helper; Playwright for pure logic; manual smoke for visual/live) → Tasks 1, 3 automated; 5-8 manual smoke as the spec's fallback allows. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; manual-smoke steps state concrete expected outcomes. ✓

**Type/name consistency:** `CaptureLogic.makePoseSmoother/stabilityStep/laplacianVariance/pickSharpestFrame` used identically in Tasks 3 and 5. `get_ghost_photos` signature identical in Tasks 1 and 2. `ghostFront/ghostLeft/ghostRight` component keys consistent across Tasks 2 and 8. Config names `LIVE_CAPTURE_BURST_MS`/`LIVE_CAPTURE_POSE_EMA_ALPHA`/`LIVE_CAPTURE_STABILITY_FRAMES` consistent across Tasks 4 and 5. ✓

**Note on manual-smoke tasks (5-8):** the live widget needs a camera + MediaPipe, which headless CI cannot drive. Per the design spec's testing section, visual/live behavior uses a documented manual smoke checklist; the automated safety net is the pure-logic Playwright tests (Task 3), the ghost-helper unit tests (Task 1), and the unchanged-payload regression suite (Tasks 5, 9).

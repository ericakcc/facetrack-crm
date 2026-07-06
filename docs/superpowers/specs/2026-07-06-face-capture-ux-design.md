# Face-Capture UX Overhaul — Design Spec

> **Date**: 2026-07-06
> **Status**: Approved (design), pending implementation plan
> **Target scenario**: clinic daily use — stable, few retakes, no dead-wait
> **Approach**: C — single `index.html`, reorganized around an explicit state
> machine; the fragile MediaPipe bootstrap is left untouched.
> **Research basis**: `docs/CAPTURE_STABILITY_RESEARCH.md` (ghost overlay =
> highest-ROI capture-stabilization technique with prior art).

## 1. Problem

The live face-capture widget (`src/facetrack/components/face_capture/frontend/index.html`,
1185 lines) feels sluggish and fights the user. Diagnosed root causes, from the
actual runtime values:

1. **3-second dead-wait after lock** (`countdownMs: 3000`). After a stable pose
   locks, the user must hold still for a full 3 s while a number counts down.
   The code even captures a wobbly frame if the user moves during countdown — so
   the 3 s buys nothing but waiting.
2. **Progress ring stutters.** In-pose adds `+1`/frame; out-of-pose subtracts
   `-2`/frame, and raw MediaPipe pose readings feed the thresholds with no
   temporal smoothing. Natural per-frame jitter makes the ring fill slowly and
   empty fast.
3. **Engineer's HUD, not a consumer UI.** The user reads raw yaw/pitch/roll
   numbers instead of aligning into a target. No silhouette, no ghost overlay.
4. **Side-profile capture is painful** — and per `CLAUDE.md` §10, profile
   photos do **not** feed scoring. (Decision: keep all three photos mandatory
   for the visual record, but make the side experience smooth.)

## 2. Goals / Non-goals

**Goals**
- Front + left + right capture feels like a consumer app (FaceID / AbbVie AR):
  align → captured in under ~1 s, no multi-second wait.
- Progress feedback is smooth, not stuttery.
- Visual guidance replaces angle-number reading: target oval, ghost overlay,
  side arrows, collapsed HUD.
- Ghost overlay reproduces framing against the patient's own prior visit.

**Non-goals (YAGNI)**
- No at-home tier in this pass (that's a later phase from the research doc).
- No change to the scoring/gate/save path or the returned payload shape.
- No touching the MediaPipe CDN-fallback / model-probe / WASM bootstrap.
- No mailed physical calibration card (future home-tier item).

## 3. Architecture — single file, explicit state machine

Reorganize `index.html`'s capture logic into one state machine plus four
single-purpose helpers (all in-file; no new served modules, to protect the
working bootstrap).

### 3.1 Capture state machine (`CaptureController`)

```
SEEKING ──(stable pose held ~0.4–0.5s)──▶ LOCKING ──(confirm)──▶ CAPTURING
   ▲                                                                  │
   │                                                    (sharpest in-tolerance
   │                                                     frame of burst)
   └──────────────(user leaves / out of tolerance)◀──────────────────┤
                                                                      ▼
                                                              DONE (this mode)
                                                         → advance to next mode
```

- **SEEKING**: smoothed pose fills a stability meter. Symmetric counter
  (`+1`/`-1`) with a hysteresis band — the *enter-pose* thresholds are slightly
  tighter than the *exit-pose* thresholds, so a borderline pose does not
  oscillate the meter.
- **LOCKING**: stability target reached; brief confirmation frame.
- **CAPTURING**: capture a burst over a short window (~0.5 s / ~10 frames). Each
  frame is scored on (a) Laplacian sharpness and (b) pose-in-tolerance. Pick the
  sharpest in-tolerance frame. If none qualifies (user moved), fall back to
  sharpest-overall for that window, or drop back to SEEKING if the pose left the
  band entirely.
- **DONE**: set thumbnail, advance `currentIdx` to the next mode. Existing
  "完成" flow and payload unchanged.

### 3.2 Helpers

| Helper | Responsibility | Depends on |
|---|---|---|
| `PoseSmoother` | EMA filter over yaw/pitch/roll; kills per-frame jitter | config alpha |
| `SharpnessScorer` | Laplacian variance on a 128px center crop of a frame | canvas 2D |
| `GuidanceRenderer` | Draw target oval (color feedback), side arrows, ghost overlay, collapsed HUD | canvas + ghost images |
| `CaptureController` | The state machine; consumes smoothed pose + sharpness, drives capture | all of the above |

**Interfaces (contracts):**
- `PoseSmoother.update({yaw,pitch,roll}) → {yaw,pitch,roll}` (smoothed).
- `SharpnessScorer.score(videoOrCanvas) → number` (higher = sharper).
- `GuidanceRenderer.render(state, mode, smoothedPose, faceWidthRatio, ghostImg)`.
- `CaptureController.tick(detectionResult) → void` (called per animation frame).

## 4. Behavior changes (detail)

### 4.1 Trigger (replaces the 3 s countdown)
- Remove the fixed multi-second countdown. Time from aligned → captured is the
  stability hold (~0.4–0.5 s) + burst window (~0.5 s) ≈ under 1 s.
- Burst frame selection prefers the sharpest **in-tolerance** frame, so quality
  is equal-or-better than the old "capture whatever is there at t+3s".

### 4.2 Smoothing + stutter fix
- EMA on yaw/pitch/roll, alpha configurable (~0.35).
- Symmetric stability counter (`+1`/`-1`) with hysteresis so borderline poses
  don't flicker the ring.

### 4.3 Visual guidance (all four)
- **Target oval**: face-shaped ellipse centered in the stage, sized to the
  target face-width band (doubles as distance guidance). Amber when
  out-of-pose/misaligned, green when in-pose.
- **Ghost overlay**: if a prior-visit photo exists for the current mode, draw it
  at ~25% opacity under the live preview. Auto-hidden when absent (first visit).
  A toggle turns it off.
- **Side arrows**: in left/right mode, a directional arrow + "再轉一點 / 已足夠"
  keyed to how far smoothed yaw is from the profile target.
- **Simplified HUD**: raw yaw/pitch/roll collapse into an "進階/除錯" section.
  Default view = one instruction line + oval color + stability ring. The debug
  log (load-bearing for triage) stays but tucked away.

## 5. Data plumbing — ghost overlay

- **Python** (`app.py` + a new helper): before rendering `face_capture`, query
  the patient's most recent visit. If it exists, load its `front` / `left` /
  `right` photo files, downscale to ~480 px, encode as data URLs, and pass via
  new nullable args `ghost_front` / `ghost_left` / `ghost_right` on
  `face_capture()`.
- **Frontend**: `GuidanceRenderer` draws whichever ghost matches the current
  mode. Missing ghost → no overlay.
- **Wrapper** (`components/face_capture/__init__.py`): add the three nullable
  string args, forward them to the component (following the existing pattern).

## 6. Config changes (`config.py`)

- Remove reliance on `LIVE_CAPTURE_COUNTDOWN_MS` for the dead-wait; add:
  - `LIVE_CAPTURE_BURST_MS` (~500)
  - `LIVE_CAPTURE_STABILITY_FRAMES` lowered (~6–8) for a snappier lock
  - `LIVE_CAPTURE_POSE_EMA_ALPHA` (~0.35)
  - hysteresis margin constant(s)
- All threaded through `face_capture()` per the existing override pattern
  (defaults in the Python signature are updated too — the stale 8°/10° defaults
  get corrected, though `app.py` already overrides them at 15°/17°).

## 7. Explicitly untouched (de-risking)

MediaPipe CDN-candidate loading, model probe/fallback, WASM fileset resolution,
GPU/CPU delegate fallback, and the debug log + copy button. The returned payload
shape (`front`/`left`/`right`/`session_id`) is unchanged, so `app.py`
scoring/save is unaffected; ghost args are purely additive.

## 8. Testing

- **Python unit tests** for the new ghost-photo lookup helper: returns latest
  visit's photo paths; `None` when no prior visit; downscale/encode correctness.
- **Frontend state machine**: Playwright headless with a fake `getUserMedia`
  video stream to verify state transitions and sharpest-frame selection. If that
  proves too heavy for the widget's iframe, fall back to a documented manual
  smoke checklist.
- **Regression**: existing gate/scoring tests stay green (payload unchanged);
  `uv run pytest tests/ -v` and `uv run pytest -m validation` unaffected.

## 9. Risks / open points

- **Per-frame Laplacian cost**: mitigate by scoring a 128 px center crop, only
  during the ~0.5 s burst — not every frame continuously.
- **Ghost overlay privacy**: shows a prior patient photo on screen. Acceptable
  in-clinic; a future home tier would need a consent consideration. Out of scope.
- **Playwright fake-stream feasibility** in the Streamlit iframe is unproven;
  manual smoke is the fallback.

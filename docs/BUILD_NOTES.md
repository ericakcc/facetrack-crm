# Build / Authorship Notes — FaceTrack CRM

**Author**: Eric Tsou
**Window**: 48 hours from 2026-05-17 receipt
**Tooling**: solo build, paired with Claude Code (Opus 4.7) as a pair-programmer
            for scaffolding, type-hint cleanup, and OpenCV API recall.

This note covers the questions in the build-challenge brief: what I personally
built, what I reused, what broke, and how I debugged it.

---

## What I personally built

* **The product thesis.** The choice to make the scoring engine deterministic
  CV (not LLM) and to gate every photo through a Photo-Consistency check
  *before* it can contaminate the longitudinal record. This is the single
  decision that separates the prototype from "yet another Vision-LLM wrapper",
  and it came from reading the brief twice and noticing that "tracks
  consistently across visits" is incompatible with stochastic scoring.

* **The Photo-Consistency Gate** (`src/facetrack/consistency_gate.py`). All
  four checks, including the ArUco gray-card colour-calibration math. I picked
  ArUco over OpenCV's CharucoBoard because a single 5×5 marker is easier to
  print on a credit-card-sized card a clinic can hand to a patient at intake.

* **The scoring formulas.** All five metrics, the choice of black-hat
  morphology for pigmentation (over the more common ITA° on average L*),
  and the empirical raw-range calibration on three reference faces.

* **The hybrid LLM-vs-CV split.** The `Explainer` interface deliberately accepts
  *scores*, not images — the LLM is structurally prevented from making up
  numbers, because it never sees the source pixels.

* **Streamlit 5-page UX in 繁體中文**, the DB schema, and the seed-trajectory
  generator (`improving / mixed / stable` per patient so the line chart tells
  a story even before real photos arrive).

## What I reused

* MediaPipe Face Landmarker (Tasks API) — pre-trained model, vendored as a
  3.6 MB `.task` file.
* OpenCV primitives: CLAHE, ArUco, morphology, Sobel, Laplacian.
* Streamlit / Plotly / SQLModel — standard scaffolding.
* `thispersondoesnotexist.com` for three CC0 test faces used for pipeline
  calibration. No real-person images in the repo.

## What broke and how I debugged it

1. **`from __future__ import annotations` broke SQLModel relationships.**
   SQLModel introspects relationship annotations at class-definition time, and
   PEP 563 turns them into strings it can't resolve. The error was a deep
   SQLAlchemy `_resolve_name` traceback that didn't mention the future import.
   *Fix*: removed the future import from `db.py` only (other modules keep it),
   and switched `list["Visit"]` to a forward-ref-then-rebuild pattern that
   SQLModel handles. Documented this gotcha in the module docstring so future
   me doesn't re-introduce it.

2. **`mp.solutions.face_mesh` is gone in MediaPipe 0.10.35.** The Gemini-style
   sample code in every tutorial uses the legacy `solutions` namespace, which
   was dropped from the macOS arm64 wheel. The error was a flat `AttributeError`,
   and there is no deprecation warning.
   *Fix*: rewrote `cv_pipeline.py` against the new Tasks API
   (`mediapipe.tasks.python.vision.FaceLandmarker`). As a bonus the Tasks API
   returns a 4×4 facial-transformation matrix, which made the pose check in
   the consistency gate much more accurate than my original
   landmark-triangulation plan.

3. **Scoring saturated at 10/10 on the first run.** Initial raw-metric
   ranges were calibrated against rough textbook numbers; the actual outputs
   after CLAHE-normalized ROIs were 5-10× higher.
   *Fix*: instrumented `scoring.py` to print raw values on the three test faces,
   read the actual distribution, and re-set the four constants
   (`PIGMENTATION_RAW_RANGE`, etc.) to the observed range. Documented this
   as a re-calibration knob for clinics with different photo distributions.

4. **The Bash sandbox initially refused to download faces over HTTPS** because
   I had wrapped `urllib.request.urlopen` in a `ssl.CERT_NONE` context out of
   habit. The denial was correct — there was no reason to disable TLS for a
   public Wikimedia / TPDNE URL.
   *Fix*: removed the SSL bypass, re-ran with default TLS verification, three
   faces downloaded in 4 seconds.

## What I'd do next with more time

* Wire `nano-banana-pro` to generate same-identity "before / mid / after"
  triptychs so the demo video shows the longitudinal pipeline on synthetic
  but visually compelling progression imagery.
* Replace the linear-clamp scoring normalization with per-cohort percentile
  scoring, so a 7.0 always means "worse than 70 % of comparable patients".
* Add identity verification on intake (compare the uploaded photo's face
  embedding to the patient's first-visit embedding) to catch wrong-patient
  uploads.

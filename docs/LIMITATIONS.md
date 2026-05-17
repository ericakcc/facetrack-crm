# Known Limitations — FaceTrack CRM

**Author**: Eric Tsou
**For**: AI Fund Engineer in Residence — Build Challenge (companion to PRD / TDD / BUILD_NOTES)
**Date**: 2026-05-17

This document exists because every "AI for medical imaging" product I've
seen at this maturity level silently fails on edge cases and ships
anyway. I would rather AI Fund's panel see the failure modes I know
about — and the concrete Phase-2 work each one would need — than
discover them at a clinic pilot in month 8.

Each entry follows the same structure: **what breaks**, **why our
current design can't catch it**, and **Phase-2 mitigation** that we
have a real plan for.

---

## 1. Heavy makeup (foundation, contouring, BB cream)

**What breaks**
Foundation flattens the surface texture that the pore (LoG) and wrinkle
(Sobel) metrics depend on, while concealer hides pigmentation. Contouring
introduces dark/light gradients that the black-hat morphology mistakes for
melasma. A heavily made-up patient gets falsely low pore/wrinkle scores
and a noisy pigmentation reading.

**Why our gate can't catch it**
The four consistency checks (pose, exposure, sharpness, color) are all
about *capture quality*, not *skin-surface visibility*. A heavily-painted
face passes every check.

**Phase-2 mitigation**
Train a small binary classifier (`makeup_present`: yes / no) on a few
hundred clinic-supplied paired photos. Surface it as a soft warning in
the intake UI: "高度修飾，分數可能失真 — 是否請患者卸妝重拍？" Block
saving as a *baseline* when triggered; allow saving as *non-baseline*
for routine progress photos.

---

## 2. Partial occlusion (face mask, hand, hair, sunglasses)

**What breaks**
MediaPipe will often still report a high-confidence face landmark when a
mask or hand covers the lower half. The ROI extraction then crops empty
ROIs over the obstruction (chin / lower cheek) and feeds them to the
scorer, which obediently returns scores for whatever was inside the
bounding box — usually fabric, not skin.

**Why our gate can't catch it**
We trust the face-detection confidence. There is no per-ROI "is this
actually skin?" check.

**Phase-2 mitigation**
Add an `is_skin` filter per ROI: a fast HSV-range mask combined with a
texture-entropy threshold. ROIs that fall below the skin-pixel ratio
threshold (say 70 %) are dropped from the aggregate and the report
notes "右頰因遮擋未納入評分".

---

## 3. Multiple faces in frame

**What breaks**
`FacePipeline` is configured with `num_faces=1` — if a receptionist
accidentally photographs the patient with a nurse leaning in, the
*nurse's* face is scored and saved against the patient's chart.

**Why our gate can't catch it**
We score only one face. We do not check whether *more than one* face
was present in the frame before we picked.

**Phase-2 mitigation**
Two-part:
(a) Increase `num_faces=3`, and if more than one face is detected,
    require the user to click which face is the patient (with a
    bounding-box overlay).
(b) Combine with the Phase-2 identity verification (§6 below) so the
    chosen face must also match the patient's first-visit embedding.

---

## 4. Extreme Fitzpatrick skin tones (V–VI)

**What breaks**
The scoring `*_RAW_RANGE` constants were calibrated on three reference
faces (CC0 stock, all Fitzpatrick II–III). Black-hat morphology on
Fitzpatrick V/VI skin produces near-saturation pigmentation values
because the global luminance is lower; the LAB `a*` channel for
erythema is similarly compressed. A Fitzpatrick VI patient with
healthy skin can be incorrectly scored as having severe pigmentation
and erythema.

**Why our gate can't catch it**
The gate is colour-blind by design — it standardises white balance via
ArUco but does not stratify against skin-type baselines.

**Phase-2 mitigation**
Per-Fitzpatrick lookup tables for the five scoring ranges, populated
from a clinic's own intake distribution (the system already exposes the
ranges as module-level constants — re-calibration is one tuple edit, not
a retrain). Detect Fitzpatrick type from the first-visit photo via
mean LAB-L on the cheek ROI, and select the matching range table at
score time.

---

## 5. Smartphone beauty filters / computational HDR

**What breaks**
Modern iPhones and Galaxies apply involuntary skin-smoothing and
HDR tone-mapping at the OS level — patient or receptionist often
cannot tell it has happened. Smoothed photos suppress the wrinkle
Sobel response and the pore LoG response, producing artificially
"better" scores that drift downward across visits as phones get
newer rather than as the patient gets better.

**Why our gate can't catch it**
A smoothed photo is not "low quality" by any of our four metrics —
it is high-quality fake skin. Sharpness, exposure, pose, and colour
all pass.

**Phase-2 mitigation**
EXIF + image-statistics heuristic: detect smoothing by comparing
high-frequency energy in the cheek ROI to a phone-camera baseline.
Recommend the clinic adopt a "FaceTrack mode" intake camera profile
(controllable via the iOS Camera API extension Apple ships in
iOS 17+) that disables computational enhancement during clinic use.

---

## 6. Wrong-patient identity confusion

**What breaks**
The product trusts the receptionist's sidebar selection. If the wrong
patient is selected (it happens — 林雅婷 and 林雅婕 are one keystroke
apart), the photo and scores write to the wrong chart and contaminate
two patients' longitudinal records simultaneously.

**Why our gate can't catch it**
The gate cares about the photo, not who the photo is of.

**Phase-2 mitigation**
On a patient's first visit, store a 128-D face embedding (FaceNet
or MediaPipe FaceMesh-derived). On every subsequent intake, compute
the embedding of the new photo and compare against the stored
reference; refuse to save if cosine similarity is below a threshold,
with a 繁中 reason: "本張照片與病患 X 的歷史照片相似度過低，請確認
病患選擇正確。"

---

## What we explicitly did NOT do

These would be the next investments after the six above:

- **Lesion-level segmentation** (per-spot tracking instead of per-ROI density). Useful for derm/laser-treatment outcome tracking but a substantial ML undertaking.
- **3D face reconstruction** for true volumetric wrinkle / sag tracking. MediaPipe gives us a transformation matrix but not a dense mesh.
- **Multi-modal integration** with dermatoscope, Wood's lamp, or polarised imaging. Each is a separate hardware adapter.
- **Cohort outcome correlation** (the optional 4th depth area in the brief). A page that says "Pico laser → −0.8 pigmentation across N patients" is high-value for the clinic owner but requires real treatment-coded data we don't have yet.

---

## Why this document exists

The submission rules say "Build evidence matters more than polish."
Limitations are part of the build evidence. A system whose author can
list six concrete failure modes — and a real Phase-2 plan for each —
is a system whose author has actually used it, not just shipped it.

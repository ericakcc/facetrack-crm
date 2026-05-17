# FaceTrack CRM — Product Requirements Document

**Author**: Eric Tsou
**For**: AI Fund Engineer in Residence — Build Challenge
**Date**: 2026-05-19
**Status**: MVP prototype, panel review

---

## 1. The problem

Taiwan's medical-aesthetic clinics (醫美診所) run a multi-billion-NTD industry on
WhatsApp, paper consent forms, and three-ring binders of "before / after" photos.
The single most common procedure — **皮秒雷射淡斑 / 淨膚** — is also the worst
served by this status quo:

* **A pico-laser course is 4–6 sessions across 3–6 months.** Patients pay
  NTD 6–8 K per session and the only signal they get back is the physician's
  eyeballed "有比較好" / "差不多" between visits. Whether session #2 actually
  worked, or whether the patient just wants it to have worked, is unanswerable.
* **No standard intake photo workflow.** Photos are shot ad-hoc, on the
  receptionist's iPhone, under whatever ceiling light happens to be on. The
  same patient at visit #3 looks objectively different from visit #1 because
  the *camera setup* changed, not the skin.
* **No quantified pigmentation baseline.** Dermal scoring tools exist (VISIA,
  Observ520) but cost USD 25 k+ and live on dedicated hardware — only the top
  5 % of clinics have one. The other 95 % run pico-laser courses with no
  numeric "is this working?" feedback loop.
* **No longitudinal record that survives clinician churn.** When the founding
  doctor leaves for a competitor, so does the institutional memory of "how this
  patient responded to last summer's pico laser course."

The wedge is a tablet-friendly intake flow + a longitudinal skin chart that
the front-desk staff can run in 60 seconds, on any smartphone, with no special
hardware — anchored on the metric that matters for pico: **quantified
pigmentation across the course**.

## 2. Target user

| User | Role | What they need from the product |
|---|---|---|
| **Reception nurse** (primary) | Greets patient, captures intake photo | Idiot-proof flow that *refuses* to save a bad photo, so they don't get blamed for skewed scores later. |
| **Clinic physician** (decision-maker) | Sees patient for 5–8 minutes per consult | An at-a-glance chart that says "is this patient actually improving?" + an editable treatment-plan draft they can override. |
| **Clinic owner** (buyer) | Runs P&L; reviews retention | Outcome trends across patient cohorts, so they know which treatments to upsell. |

In Taiwan specifically, the receptionist is overwhelmingly female, in her
twenties, comfortable with LINE-style UIs, and speaks no English. The product
must be 繁體中文 first-class, not localized as an afterthought.

## 3. Workflow that the prototype demonstrates

**Target workflow**: 皮秒雷射療程追蹤. Visit #1 establishes the pigmentation
baseline; visits #2–6 (each ~4 weeks apart) are compared against it to answer
"is this course actually working?" The same flow generalises to other 醫美
procedures (see §5), but pico is the MVP target.

1. **Patient check-in** — receptionist selects the patient in the sidebar.
2. **Intake photo** — receptionist drags a smartphone photo into "📸 新增就診".
3. **Photo-Consistency Gate** runs *before* anything else:
   * If the photo fails (head turned, over-exposed, blurry, no calibration card),
     the system rejects it with a 繁中 reason — the receptionist re-shoots.
   * **The gate is the product's most important property.** It is what prevents
     longitudinal scores from being garbage.
4. **CV pipeline** aligns the face, extracts 4 ROIs (left/right cheek, forehead,
   chin), applies CLAHE.
5. **Scoring engine** computes 5 deterministic skin metrics per ROI.
6. **AI explainer** drafts a 繁中 explanation + treatment suggestion, which the
   physician sees and edits before saving.
7. **Longitudinal view** updates the radar chart + line chart automatically.

## 4. Why this approach fits clinic operations

Three product decisions are non-obvious and deliberate:

1. **Reject bad photos at intake, not later.** Most "AI for medical imaging"
   products silently accept garbage and produce confident-looking outputs. In a
   clinic, that erodes trust the first time a clinician notices the score moved
   while the patient hadn't been treated. We make the gate visible and audible.

2. **CV scores are deterministic; the LLM is decorative.** The number on the
   chart comes from a fixed formula (e.g., black-hat morphology pixel ratio →
   pigmentation). Re-running on the same photo gives the same number, every
   time. The LLM only translates the numbers into 繁中 prose and a draft
   treatment plan, both of which the physician can edit. This makes the system
   defensible if a patient or regulator asks "how did you get this number?"

3. **Editable AI output.** Every AI suggestion is a draft, never a verdict.
   The physician's edits are stored alongside the AI output. This is the only
   pattern clinics will buy — they will not accept a system that overwrites their
   judgement.

## 5. Wedge → platform path

* **Wedge (this prototype, ~5 clinics in pilot).** Single-procedure focus:
  皮秒雷射淡斑追蹤. Streamlit app, intake + Photo-Consistency Gate +
  deterministic pigmentation scoring + longitudinal chart + editable
  treatment notes. One procedure, one hero metric, one clean demo loop.
* **Phase 2 (extend to other 醫美 procedures, 6 months).** The same
  three-stage pipeline — ConsistencyGate → deterministic CV ScoringEngine →
  scores-only LLM Explainer — accepts new procedures by registering new
  metric functions. Concrete next-up procedures:
  - **肝斑治療** — pigmentation metric reused, chronic-course visualization
    (months → years).
  - **痘疤治療**（雷射磨皮 / 微針）— pore + wrinkle + uniformity metric
    bundle for textural recovery.
  - **紅血絲 / 酒糟治療**（脈衝光 / IPL）— erythema metric (LAB a*) as hero.
  Each new procedure is a metric registration + a clinic-specific raw-range
  calibration tuple — not a pipeline rewrite.
* **Phase 3 (multi-clinic SaaS, 12 months).** Patient consent, photo-history
  vault, appointment integration, LINE Pay billing. Multi-procedure
  longitudinal record per patient.
* **Phase 4 (outcome-tracking moat, 18–24 months).** Once enough procedures
  and clinics report into the system, "which laser settings correlate with
  the largest pigmentation drop across the cohort" becomes answerable —
  anonymized aggregate insights become the data moat and the basis for a
  skin-data exchange across Greater China medical aesthetics.

## 6. Out of scope for this prototype

* Patient self-service / mobile app
* Payment / billing integration
* HIPAA / PIPL compliance hardening (data stays on-device for the demo)
* Hardware-paired imaging (we accept *any* smartphone photo, then gate it —
  that is the whole point)

## 7. Success metric for the panel review

The reviewer should be able to:

1. Upload a face photo and see the **Photo-Consistency Gate reject it** for a
   concrete reason.
2. Upload a better photo, watch the system produce **the same scores** if they
   upload it twice.
3. See the **longitudinal chart update** with the new visit.
4. **Edit the AI treatment draft** and save the edit.

All four flows are wired and demonstrable in the live app.

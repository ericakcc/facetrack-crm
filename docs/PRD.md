# FaceTrack CRM — Product Requirements Document

**Author**: Eric Tsou  **For**: AI Fund Engineer in Residence — Build Challenge  **Date**: 2026-05-19  **Companion**: `docs/TDD.md`

## 1. The problem & the wedge

Taiwan's medical-aesthetic clinics run a multi-billion-NTD industry on paper consent forms, three-ring binders of "before / after" photos, and the receptionist's iPhone. The single most common procedure — a **pico-laser pigmentation course** — is 4–6 sessions at NTD 6–8 K each (≈ USD 200 / session) over 3–6 months, and the only signal patients get back between visits is the physician's eyeballed *"a little better"* vs *"about the same"*. Whether session #2 actually worked, or whether the patient just wants it to have worked, is unanswerable. Photos are shot ad-hoc under whatever ceiling light is on; the same patient at visit #3 looks different from visit #1 because the *camera setup* changed, not the skin. Dermal-scoring hardware (VISIA, Observ520) exists but costs USD 25 k+ and lives on a dedicated station — only the top 5 % of clinics have one. The other 95 % run pico-laser courses with no numeric "is this working?" feedback loop.

**The wedge is the AI-native CRM entry point for the clinic** — a tablet-friendly intake flow plus a longitudinal skin chart that the front-desk staff runs in 60 seconds on any smartphone, no special hardware, anchored on the metric that matters for pico: **quantified pigmentation across the course**. The intake event is the only moment in the clinic day when every patient is in front of a camera with their face squared up; owning that moment is what makes the longitudinal skin record defensible, and the longitudinal skin record is what turns a CRM from "appointments + chat history" into a clinical decision-support surface. **This submission demonstrates the engine on pico-laser pigmentation tracking** as the hero procedure; the engine itself is procedure-agnostic (TDD §3).

## 2. Target user

| User | Role | What they need |
|---|---|---|
| **Reception nurse** (primary) | Greets patient, captures intake photo | An idiot-proof flow that *refuses* to save a bad photo, so they don't get blamed for skewed scores later. |
| **Clinic physician** (decision-maker) | 5–8 min per consult | An at-a-glance "is this patient actually improving?" chart, plus an editable treatment-plan draft they can override. |
| **Clinic owner** (buyer) | P&L, retention | Outcome trends across cohorts — which treatments to upsell, which to retire. |

In Taiwan, the receptionist is overwhelmingly female, twenties, fluent in messaging-app UIs but not English. The product must be **Traditional Chinese first-class**, not localised as an afterthought.

## 3. Workflow the prototype demonstrates

1. **Check-in** — receptionist picks the patient in the sidebar.
2. **Intake photo** — on the "New visit" page: live face-mesh capture (auto-fires when pose / face-fill / stability all pass) **or** an upload fallback.
3. **Photo-Consistency Gate** runs *before* anything else. Failing photos are rejected with a concrete reason ("head turned 18° right; please face the camera") and the receptionist re-shoots. **This is the product's most important property** — without it, the longitudinal scores are garbage.
4. **CV pipeline** aligns the face, extracts four ROIs (left/right cheek, forehead, chin) as polygon masks, applies per-photo CLAHE.
5. **Scoring engine** computes five deterministic skin metrics per ROI; identical photo → identical score.
6. **LLM explainer** drafts an explanation + treatment suggestion in Traditional Chinese. **The physician edits everything before saving** — every AI output is a draft, never a verdict.
7. **Longitudinal view** updates the radar + line chart automatically.

## 4. Why this approach fits clinic operations

Three non-obvious decisions:

1. **Reject bad photos at intake, not later.** Most "AI for medical imaging" silently accepts garbage and emits confident-looking output. In a clinic that erodes trust the first time a clinician notices the score moved while the patient wasn't treated. We make the gate visible and audible *at the moment of capture*.
2. **CV scores are deterministic; the LLM is decorative.** The number on the chart comes from a fixed formula (black-hat morphology pixel ratio → pigmentation). Re-run on the same photo → same number, to the last decimal. The LLM only translates numbers into prose + a draft plan. The system is defensible when a patient or a regulator asks "how did you get this number?"
3. **Editable AI output, always.** The physician's edits are stored alongside the AI draft. Clinics will not buy a system that overwrites their judgement.

## 5. Wedge → platform path

* **Wedge** (this prototype, ~5 pilot clinics) — single-procedure focus: pico-laser pigmentation tracking. One procedure, one hero metric, one clean demo loop.
* **Phase 2** (6 mo, more aesthetic procedures) — the same three-stage pipeline (`ConsistencyGate → ScoringEngine → scores-only Explainer`) accepts new procedures by **registering a metric function**, not rewriting the pipeline. Next up: **melasma** (pigmentation metric reused, chronic-course visualisation over months → years), **acne scars** (pore + wrinkle + uniformity bundle for textural recovery via laser resurfacing or microneedling), **vascular redness / rosacea** (LAB `a*` channel as the hero metric, treated via IPL).
* **Phase 3** (12 mo, multi-clinic SaaS) — patient consent, photo-history vault, appointment integration, LINE Pay billing. **Competitive positioning**: the CRMs Taiwanese aesthetic clinics already pay for (LINE Official Account CRM, hospital-style ERPs, appointment SaaS) own the booking and message-history surfaces but **none owns a quantified skin record** — because none runs a CV pipeline at intake. They can layer appointments onto a record they don't own; we own the record and layer appointments later. The CV pipeline is the moat. Appointments are commodity.
* **Phase 4** (18–24 mo, outcome-tracking moat) — once enough procedures × clinics report into the system, "which laser settings correlate with the largest pigmentation drop across the cohort" becomes answerable. Anonymised aggregate outcomes become the data flywheel and the basis for a skin-data exchange across Greater China aesthetic medicine.

## 6. Out of scope & success criterion

**Out of scope for this prototype**: patient self-service, payment, HIPAA / PIPL hardening, hardware-paired imaging. We accept *any* smartphone photo and gate it — that is the whole point.

**Panel success**: a reviewer can (a) upload a face photo and see the **gate reject it** with a concrete reason; (b) upload a better photo and see **identical scores on a repeat upload**; (c) watch the **longitudinal chart update** with the new visit; (d) **edit the AI treatment draft** and save the edit. All four are wired in the live app.

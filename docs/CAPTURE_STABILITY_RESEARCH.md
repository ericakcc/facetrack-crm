# Capture-Stability Research — Clinic Station vs. Guided Smartphone

> **Question**: Is a fixed in-clinic photo station the only way to get stable,
> comparable input for longitudinal skin tracking — or can guided smartphone
> capture get close enough, including at home?
>
> **Method**: 5-angle parallel web search → 20 sources → 99 extracted claims →
> 3-vote adversarial verification on the top 25 (15 confirmed, 3 refuted, 7
> unverified due to a session-limit interruption during verification).
> Generated 2026-07-06. Claims marked *(unverified)* were extracted from a
> primary source but did not complete adversarial verification — cite with care.

---

## TL;DR for the CTO call

A fixed photo booth locks **pose, distance, and lighting-uniformity** — all
three of which guided software can approximate. The only thing hardware truly
owns is **absolute spectral control** (cross-polarized / UV illumination), which
matters for *absolute diagnosis*, not for *relative trend tracking*. FaceTrack
is a relative tracker, so the booth is not a hard requirement.

There is **randomized-trial evidence** that software guidance alone works: an
AI photo-quality gate cut poor-quality submissions by **68%**
([PMC10018405](https://pmc.ncbi.nlm.nih.gov/articles/PMC10018405/)). And a
pharma-grade AR face-capture app (AbbVie/Allergan) scored **better** image
quality than in-clinic DSLR imaging
([PMC12851522](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12851522/)).

**Design principle every successful product converges on**: measure change
**relative to the patient's own baseline captured under gated conditions**, not
absolute values. Anchor the baseline in the clinic; let home captures track the
delta.

---

## 1. What a fixed clinic station actually locks (and whether software can match it)

| Variable the booth fixes | Hardware mechanism | Can software approximate it? |
|---|---|---|
| Pose / position | Chin rest, head support, live positioning feedback | ✅ Yes — face-mesh HUD does this |
| Distance / scale | Fixed focal length + fixed rig geometry | ✅ Yes — 512px face-scale normalization |
| Lighting uniformity | Dark room + fixed light sources | 🟡 Partial — CLAHE + lighting-asymmetry gate cover uniformity, not absolute spectrum |
| Absolute spectrum | Cross-polarized / parallel-polarized / Wood's / true-UV modes | ❌ No — hardware-only; needed for *absolute* diagnosis, not *relative* tracking |
| Subject/environment state | Product removal, 15-min acclimation, neutral expression | ❌ Process discipline (SOP), not a hardware property |

**Key insight**: much of a clinic station's value is *SOP discipline*
(de-makeup, acclimate, neutral expression), enforced by staff, not by the
camera ([VISIA-CR protocol, ASJ Open Forum](https://academic.oup.com/asjopenforum/article/doi/10.1093/asjof/ojag034/8482225)).
The only irreplaceable hardware advantage is absolute spectral control.

### The booth is not perfect either (useful for CTO framing)

- **Reproducibility target**: VISIA repeat-capture wrinkle scores differ by only
  ~3.4%, no significant session difference (Wilcoxon p=0.376)
  ([PMC10665717](https://pmc.ncbi.nlm.nih.gov/articles/PMC10665717/)). This is
  the bar to approach — not unreachable.
- **Even the gold standard warns against individual absolute claims**: VISIA
  "skin age" correlated with chronological age (Spearman r=0.83–0.90) but with
  −7 to +9 years of individual-level spread; the authors say individual
  assessments "should be interpreted with caution"
  ([PMC10665717](https://pmc.ncbi.nlm.nih.gov/articles/PMC10665717/)). This
  directly justifies a relative-tracking positioning.
- **Wrinkles and UV spots are the least reproducible metrics** across capture
  angles even inside a controlled booth
  ([PMC9175133](https://pmc.ncbi.nlm.nih.gov/articles/PMC9175133/)) — consistent
  with why the wrinkle range needed the FFHQ recalibration.

---

## 2. Does software guidance alone measurably help? — Yes (with a randomized trial)

| Evidence | Result | Source |
|---|---|---|
| AI quality gate that rejects bad photos and prompts retake | **−68%** patients submitting a poor-quality image (live clinical pilot, software-only) | [PMC10018405](https://pmc.ncbi.nlm.nih.gov/articles/PMC10018405/) |
| Smartphone wound app with real-time quality feedback | Sharpness median 804 vs 700 (P<.001) | [PMC8367165](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8367165/) |
| Randomized prospective cohort, 360 patients, 3 photo sets each (unassisted self / self after brief training / resident) | Diagnostic concordance rises 84% → 87% as guidance is added | [Saade et al. 2025, PMC12488292](https://pmc.ncbi.nlm.nih.gov/articles/PMC12488292/) |
| Auto-detectable quality defects | Overall ROC-AUC 0.781; blur 0.84; lighting 0.70 | [PMC10018405](https://pmc.ncbi.nlm.nih.gov/articles/PMC10018405/) |

---

## 3. Closest prior art (ranked) and what each implies for FaceTrack

### 1. ⭐ AbbVie / Allergan remote aesthetics face-capture app — nearly the same product
AR face-tracking auto-capture scored **better** BRISQUE image quality (14.05–19.81,
lower is better) than in-clinic Canfield VISIA-CR + DSLR (34.47) and Canfield's own
mobile app (23.43). ([PMC12851522](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12851522/))
→ **Implication**: a major pharma has already validated AR-guided smartphone face
capture beating clinic DSLRs in aesthetics trials. FaceTrack's differentiation is
the deterministic CV scoring + longitudinal tracking layered on top.

### 2. ⭐ DentalMonitoring ScanBox — the textbook at-home longitudinal solution *(unverified)*
Patients self-capture weekly at home over ~18-month treatments; 3D reconstructions
stay within the ±0.5 mm ABO clinical-acceptability threshold vs. iTero; multicenter
study (104 patients) reports 98.9% agreement with in-person expert assessment.
([white paper](https://dentalmonitoring.com/wp-content/uploads/2024/04/AD_MON_PA_UIC-Accuracy-white-paper.pdf))
→ **Core pattern for FaceTrack's home tier**: home photos are **never the absolute
baseline**. Each patient's baseline is captured in-clinic (iTero); all home captures
compute change *relative to that clinic baseline*. Absolute anchor in clinic, delta at home.

### 3. Swift Medical HealX — physical calibration marker makes phones measurement-grade
A precision adhesive fiducial in-frame calibrates color, lighting, and size in real
time on a consumer phone. ([Swift](https://swiftmedical.com/how-a-small-scientific-calibrant-can-drastically-enhance-wound-care/))
→ **Implication**: same philosophy as FaceTrack's ArUco gray card, already
commercialized. A home tier could **mail patients a calibration card** — near-zero
cost, pulls phone capture toward measurement-grade. FaceTrack's gate check #6 already
supports this.

### 4. Follicle app "Ghost Overlay" — consumer trick for reproducing framing at home *(unverified)*
Superimposes a faint prior reference photo on the live preview so users reproduce
angle/position/framing; plus an "AI Photo Consistency" score comparing each new photo
to the user's own baseline. ([Google Play](https://play.google.com/store/apps/details?id=com.follicleapp.follicle))
→ **Highest-ROI next feature**: ghost overlay is cheap to add on top of the existing
face-mesh HUD and directly targets framing consistency — the hardest home-capture
variable.

### 5. Home wound-care app with real-time feedback — same three tricks as FaceTrack
Combines Laplacian sharpness detection + auto color-card detection + historical-image
overlay. ([PMC8367165](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8367165/))
→ **Implication**: FaceTrack's gate already matches two of the three; ghost overlay is
the third. The design is the field's converged standard, not a one-off.

---

## 4. Refuted claims — do NOT cite

Adversarial verification killed these (3-0):
- ✗ "VISIA cross-angle correlation is only r=0.74."
- ✗ "VISIA-CR tracks longitudinally via operator-saved manual ROIs."
- ✗ "Standardized capture makes pigmentation correlate with MASI r=0.43 while
  traditional VISIA shows none."

---

## 5. Conclusions

**(a) Is a clinic station the only route to stable input?** No. It locks pose,
distance, and lighting-uniformity — all software-approximable. Only absolute
spectral control is hardware-exclusive, and that is needed for absolute diagnosis,
not relative tracking.

**(b) Proven stabilization techniques, ranked by evidence:**
1. Real-time on-device quality gate with retake prompt (randomized-trial evidence, −68%).
2. Physical calibration marker in-frame (commercialized: Swift HealX; FaceTrack: ArUco).
3. Scale/geometry normalization in software (FaceTrack: 512px norm).
4. Historical/ghost overlay for framing reproduction (Follicle, wound-care apps).
5. Anchoring home captures to an in-clinic baseline (DentalMonitoring).

**(c) Recommended tiered architecture:**

| Tier | Setting | Stabilization | Positioning |
|---|---|---|---|
| Clinic baseline | First visit, clinic | Full gate + gray card + 512px norm | Establishes per-patient anchor |
| Home tracking | Patient self-capture | Gate + **ghost overlay** (new) + **mailed calibration card** (new) + relative-Δ only | Tracks trend, no absolute claims |
| Simple check | Casual snapshot | Gate guidance only, flagged "reference only, not in baseline" | Already supported via `quality_passed=False` |

**Two hard rules for the home tier**: (1) keep the absolute anchor in the clinic
(per DentalMonitoring); (2) add ghost overlay + calibration card — both low-cost,
both with prior art.

---

## Sources

- VISIA reproducibility / skin age: https://pmc.ncbi.nlm.nih.gov/articles/PMC10665717/
- Vectra stereophotogrammetry accuracy: https://www.mdpi.com/1660-4601/19/14/8820
- Vectra H1 handheld validation: https://www.sciencedirect.com/science/article/abs/pii/S2468785519301089
- Cross-angle skin metric reproducibility: https://pmc.ncbi.nlm.nih.gov/articles/PMC9175133/
- VISIA-CR standardization protocol: https://academic.oup.com/asjopenforum/article/doi/10.1093/asjof/ojag034/8482225
- OBSERV 520x station + comparison: https://www.nature.com/articles/s41598-024-63274-7
- Wound app real-time feedback (RCT-style): https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8367165/
- AI photo-quality gate (−68%): https://pmc.ncbi.nlm.nih.gov/articles/PMC10018405/
- Swift Medical HealX calibrant: https://swiftmedical.com/how-a-small-scientific-calibrant-can-drastically-enhance-wound-care/
- DentalMonitoring accuracy white paper *(unverified)*: https://dentalmonitoring.com/wp-content/uploads/2024/04/AD_MON_PA_UIC-Accuracy-white-paper.pdf
- Follicle ghost overlay *(unverified)*: https://play.google.com/store/apps/details?id=com.follicleapp.follicle
- DentalMonitoring multicenter validity *(unverified)*: https://www.researchgate.net/publication/395834105
- Teledermatology randomized cohort (Saade et al. 2025): https://pmc.ncbi.nlm.nih.gov/articles/PMC12488292/
- AbbVie/Allergan mobile facial capture vs DSLR: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12851522/

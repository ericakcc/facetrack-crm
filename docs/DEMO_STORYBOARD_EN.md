# Demo Video Storyboard — FaceTrack CRM (English Narration)

**Target length**: 2 min 50 s ± 15 s
**Audience**: AI Fund panel reviewers
**Recording tool**: Loom (browser, includes mic + camera-bubble) or OBS
**URL to record against**: `localhost:8501` — the local DB has EricZou and the
three nano-banana progression photos; the deployed Streamlit Cloud URL has
only the three seed patients and gets cited in the submission email as the
working-prototype link.
**Language**: English voiceover
**Demo subject**: **EricZou** (presenter's own face). Three pre-existing visits
in the local database are nano-banana-pro-generated progressions of the same
face — visit 1 heavy pigmentation, visit 2 mild improvement, visit 3 greatly
improved — so the longitudinal chart tells a personal, visually credible story.

The brief's hardest rule:
> "At least one depth area must be visible in the product or implementation evidence,
> not just described in the PRD or TDD."

In this script the **Photo-Consistency Gate is shown in two places** — once as
a live, on-screen guidance loop during capture (Scene 3 — countdown only fires
when pose / distance / stability all pass), and once as a structural property
in the longitudinal chart's credibility (Scene 4).

The 繁體中文 sibling of this script lives in `DEMO_STORYBOARD.md`. Pick one to
record against; the action beats are identical.

---

## Scene-by-scene

### Scene 1 · 00:00 – 00:30 · Opening + product framing (30s)

**Visual**: Browser at `localhost:8501`. Sidebar fully expanded.

**Voiceover**:
> "Hi, I'm Eric — this is FaceTrack CRM, my Build Challenge submission.
> Based on our earlier discussion, the target beauty clinics will start in Taiwan, 
> so I built the UI in Traditional Chinese first.
> Given the 48-hour window, I deployed a POC with Streamlit. The product
> targets two problems:
> **First** — how to capture photos that are **comparable across visits**
> using everyday hardware like a smartphone. This is where some basic
> computer vision comes in.
> **Second** — how to **track and quantify a patient's skin state at each
> visit**, so 'is it getting better?' moves from the physician's subjective
> judgment to a reproducible number."

---

### Scene 2 · 00:30 – 00:50 · Product structure walkthrough (20s)

**Action**:
1. Hover over the sidebar
2. Point at `👤 病患作業` group — list its four pages
3. Point at `📊 資料分析` group — list its two pages
4. Click `👥 病患管理` to show the patient list briefly
5. Select **EricZou** from the dropdown

**Voiceover**:
> "The sidebar is split in two. The top group, 'Patient Operations,' holds
> patient management, new intake, visit history, and treatment planning.
> The bottom group, 'Data Analytics,' holds the longitudinal tracking view
> and system settings.
> I'll demo both groups. with my photo — EricZou."

---

### Scene 3 · 00:50 – 01:40 · Intelligent photo capture (50s)

**Action**:
1. Click `📸 新增就診`
2. Stay on the default `📷 即時拍照（MediaPipe Face Mesh）` tab
3. Allow camera permission if prompted
4. Once the green mesh appears overlaid on the face:
   - Show the HUD readout (yaw / pitch / roll / face width)
   - **Hold the face out of position briefly** — the countdown does NOT start
   - **Move to centered, in-range** — the 3-second countdown overlay fires
   - Auto-capture for the **front photo**
5. After front capture, **demonstrate the optional side**:
   - Turn head ~5° left — left profile captures
   - (Optionally skip right) — click **「✓ 完成」** to finalise

**Voiceover** (timed across the capture):
> "First, the photo capture. I'm running MediaPipe Face Mesh **in the
> browser** — not on a server. That's 478 facial landmarks computed live,
> client-side.
> The HUD up top shows yaw, pitch, roll, and face-width ratio. The countdown
> only starts when **all four** conditions go green — head is centered, the
> user is at the right distance, not too close not too far, and they're
> stable for a few frames.
> This is what I call the 'Photo-Consistency Gate.' It doesn't tell you the
> photo is unusable **after** you've taken it. It guides you to take it
> correctly **before** you press the shutter.
> The front photo is mandatory, because the scoring depends on the
> regions of a frontal face.
> Left and right profiles are optional — they get saved as extra record,
> but they don't enter the scoring for now. They give the physician a closer look
> at cheek texture from the side.
> When done, click Finish to send everything back."

---

### Scene 4 · 01:40 – 02:40 · Longitudinal tracking + scoring + LLM explainer (60s)

**Action**:
1. Click `📈 縱向追蹤`
2. Show the radar chart (5 dimensions × 3 visits, blue → red gradient)
3. Move to the line chart — trace pigmentation from Jan to May
4. Briefly: 各回診詳細分數 table
5. Click `📋 就診歷史` → expand the 5/18 visit
6. Tick **🔬 顯示 ROI 訊號疊圖** — show heatmap, switch metric once
7. Scroll to the AI 解釋 + 治療建議 section

**Voiceover**:
> "Now the tracking side. To be honest: doing three real pico-laser sessions
> would take four months. So I used nano-banana-pro to generate three
> progression variants of my own face — visit one with heavy pigmentation,
> visit two with mild improvement, visit three greatly improved — and
> seeded them as three real visits in the system.
> Here are the radar chart and the line chart. You can see the pigmentation
> health score climbing from 4 to 8 — higher means better skin.
> This score is computed **entirely by computer vision** — not by an LLM.
> I have a separate image-processing algorithm for each of the five metrics:
> pigmentation, wrinkles, erythema, pores, and skin-tone uniformity.
> Re-run the same photo a hundred times and the scores are bit-identical.
> **That's something an LLM scorer cannot do.**
> So where's the LLM? It sits in the **explanation layer.** If I open a past
> visit and toggle this ROI signal overlay, you'll see a heatmap — the
> bright areas are the raw signal the score was computed from. The
> physician sees directly **why** the score landed where it did.
> Below that, the LLM translates the numbers into a Traditional Chinese
> narrative and drafts a treatment suggestion — for the consultant or
> patient to read, or as a starting point the physician can edit.
> I'll be honest — the LLM prompt still needs work. What you see is a
> basic version. Phase 2 will add grounding and physician-preference
> learning. But structurally, **the LLM never sees pixels — only scores**
> — so it cannot fabricate numbers."

---

### Scene 5 · 02:40 – 02:55 · Wrap-up + honest limitations (15s)

**Voiceover**:
> "Built in 48 hours. Known limitations are documented in BUILD_NOTES —
> makeup detection, patient identity verification, and Fitzpatrick
> skin-type recalibration are phase-2 items.
> Links to the GitHub repo, PRD, TDD, and the limitations doc are in the
> submission email. The deployed Streamlit Cloud URL is also in the email
> as the working-prototype reference. Thanks for watching — looking forward
> to hearing back from the AI Fund team."

---

## Delivery notes (English-specific)

- **Slow down on the technical terms.** "Photo-Consistency Gate,"
  "black-hat morphology," "LAB a-star," "Laplacian-of-Gaussian" — these are
  the panel's keywords for identifying a senior engineer. Don't blur them.
- **Pause half a second before "I'll be honest"** in Scene 4. That's the
  signal moment of intellectual honesty — let it land.
- **Don't over-pronounce 繁體中文 / 病患作業 / 縱向追蹤.** Use them
  naturally as you would in code-switching speech, then explain in English.
  Native Mandarin pronunciation isn't required — your audience cares that
  you can build for that market, not that you sound like a Beijing news
  anchor.
- **End the wrap-up looking at the camera, not the screen.** It's the only
  beat where eye contact matters more than visual proof.

## Recording checklist

- [ ] Local Streamlit running: `uv run streamlit run app.py` → `localhost:8501`
- [ ] EricZou patient + 3 nano-banana visits exist in local DB
      (`uv run python -c "from facetrack.db import get_session; from facetrack.db import Patient; from sqlmodel import select; s=next(get_session().__enter__() for _ in range(1)); print([p.name for p in s.exec(select(Patient)).all()])"` — should list 林雅婷, 陳怡君, 張立宇, EricZou)
- [ ] Screen recording set to 1920×1080 (or 1280×720 if bandwidth tight)
- [ ] Browser zoomed to ~110% so labels are readable
- [ ] Mic level checked — record a 5-second sample first
- [ ] Webcam bubble in bottom-right corner ON
- [ ] Loom set to "Anyone with the link can view" (not 'Workspace only')
- [ ] Camera permission pre-granted for `localhost:8501`
- [ ] Run through once silently to time the Scene-3 live-capture beat

## Things to NOT do

- ❌ Don't narrate the architecture diagram. The TDD covers it.
- ❌ Don't show code. The reviewer reads code separately.
- ❌ Don't apologise for the UI being plain. The brief says "Rough is fine."
- ❌ Don't exceed 3 min 10 s. Cut the optional left profile in Scene 3 first.
- ❌ Don't hide the nano-banana origin of EricZou's visits. Honest framing
     ("I generated this progression on my own face") is stronger than
     implying it's a real laser course.
- ❌ Don't translate UI labels for the panel. The fact that the UI is in
     Traditional Chinese is *the point* — it's the depth-area "Mandarin UX"
     made literal.
- ❌ Don't record at midnight bleary-eyed — your delivery is half the signal.

## Mapping to the brief's submission rules

| Brief requirement | Where it lands |
|---|---|
| "Working prototype is the main event" | Deployed URL in submission email + every scene runs against the running app |
| "Depth area visible in product, not just docs" | **Scene 3** (gate as real-time capture guidance) + **Scene 4** (heatmap shows score origin) |
| "Standardized intake → quantified profile" | Scene 3 + Scene 4 |
| "Longitudinal comparison across visits" | Scene 4 (radar + line for EricZou) |
| "Treatment suggestions explainable and editable" | Scene 4 (heatmap + editable AI draft) |
| "Real-world imaging variation" | Scene 3 (gate gates pose/distance/stability before capture, not after) |
| "Optional depth: Mandarin UX" | Scene 1 framing + every UI string on screen |
| "What you built / reused / broke" | Scene 5 voiceover + BUILD_NOTES.md link in email |

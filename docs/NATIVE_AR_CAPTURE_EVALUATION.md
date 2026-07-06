# Native AR Capture Feasibility — ARKit / ARCore vs. Web MediaPipe

**Author**: Eric Tsou · **For**: FaceTrack CRM — strategic evaluation (not for the AI Fund panel; internal decision doc) · **Date**: 2026-07-06
**Companion**: `docs/CAPTURE_STABILITY_RESEARCH.md` (booth-vs-software stabilization — same question one layer down: not "is a physical booth needed" but "is native OS-level depth sensing needed")

> **Scope note**: this is a medium/long-term strategic evaluation, not a task for the current sprint. The pragmatic web-capture rework happening now is separate work and is not blocked by this document either way.

---

## 執行摘要（給 Eric）

結論先講：**現階段不需要做原生 AR App**。網頁版 MediaPipe FaceLandmarker 搭配現有的 6 項 Consistency Gate，對「同一支手機、同一位患者、長期追蹤相對變化」這個產品定位已經足夠——這正是 FaceTrack 的核心情境，而不是需要絕對量測精度的醫療影像系統。原生 AR（ARKit TrueDepth / ARCore Augmented Faces）唯一無可取代的優勢，是 iPhone TrueDepth 的**結構光深度感測**能在大角度（側臉/顴骨角度）下仍持續追蹤，不會像純 2D 的 MediaPipe 一樣直接「丟失一隻眼睛」而整個 transform 失效——這正是 repo 裡 `PROFILE_YAW_MIN_DEG = 5.0` 這個很窄的容忍度背後的真正限制。但要注意一個重要的、容易被忽略的事實：**ARCore 的 Augmented Faces 其實跟 MediaPipe 一樣，也是純 2D/ML 推論、不需要深度感測器**——換句話說，做原生 Android App 並不會讓 Android 端的臉部追蹤精度變好，只有 iOS + TrueDepth 這條線才是真正的精度升級。全平台做到 production-ready，粗估是一位資深工程師 3–6 個月的量級，而且會直接引入 App Store 的「醫療器材身份聲明」新規（2026 年生效，2027 年初前既有 App 也要補），以及失去現在「複製 repo、瀏覽器打開就能跑」這個對 AI Fund 評審非常重要的低摩擦體驗。**建議**：先不做；但把「居家患者自行拍攝」變成核心分層，或「側臉/3D 精度」變成硬性產品需求，就是拉原生 AR 這個扳機的兩個具體觸發條件，本文結尾給出可判斷的量化門檻。

---

## 1. What native AR gives over web MediaPipe

### 1.1 The mechanism difference

Web MediaPipe FaceLandmarker (what FaceTrack runs today, both server-side in `cv_pipeline.py` and client-side in the live-capture JS widget) is a **monocular RGB model**: it infers a 478-point 3D mesh from a single 2D image using a learned prior of face geometry. The `z` coordinate is a *relative, inferred* depth, not a *measured* one.

ARKit's `ARFaceTrackingConfiguration` on TrueDepth-equipped devices is fundamentally different: the TrueDepth camera projects ~30,000 infrared dots (VCSEL dot projector + IR camera + flood illuminator) and *measures* structured-light depth per point, producing a 1,220-point mesh + 52 blendshape coefficients at 60 fps ([Apple ARKit docs](https://developer.apple.com/documentation/arkit/arfacetrackingconfiguration); [ARKit TrueDepth deep-dive](https://www.oreateai.com/blog/indepth-analysis-of-arkit-facial-recognition-technology-from-truedepth-camera-to-expression-capture-system/04656b4af7dc89ea9c7e33bf67b09d44)). This is a real depth sensor, not an ML-inferred proxy.

**ARCore's Augmented Faces API is the important asterisk**: it uses a **468-point mesh with no depth sensor at all** — pure monocular ML on the standard camera, explicitly documented as not requiring "uncommon or special hardware such as a depth sensor" ([Google ARCore docs](https://developers.google.com/ar/develop/augmented-faces); [GeeksforGeeks walkthrough](https://www.geeksforgeeks.org/augmented-faces-with-arcore-in-android/)). That is the *same class of technique* MediaPipe FaceMesh already uses in the browser today ([MediaPipe Face Mesh, 468 landmarks](https://github.com/google-ai-edge/mediapipe/wiki/MediaPipe-Face-Mesh)). **A native Android app does not give FaceTrack better face-tracking fidelity than the current web widget already has.** The entire "FaceID-grade" upside is an iOS + TrueDepth story, full stop.

### 1.2 Tie back to FaceTrack's two actual needs

| FaceTrack need | Does native (iOS TrueDepth) help? | Evidence |
|---|---|---|
| **Consistent, comparable longitudinal capture** (same framing/pose across visits) | Marginal. This is a *software-guidance* problem (ghost-overlay, pose HUD, gate), already shown to work via SOP + software per `CAPTURE_STABILITY_RESEARCH.md` — depth sensing doesn't make a patient hold the same pose, it just measures the pose they held more precisely. | `docs/CAPTURE_STABILITY_RESEARCH.md` §1–2 |
| **Slight-cheek-angle side shots** (the repo's own `PROFILE_YAW_MIN_DEG = 5.0`) | Real, but bounded. TrueDepth's advantage is *not* "perfect accuracy at profile" — a peer-reviewed accuracy study of ARKit facial-distance measurement found error climbing from ~5.3% frontal to **10.36% at ±22.5° yaw**, worse still (8.7–20.2%) at extreme diagonal angles. The advantage is that TrueDepth *keeps producing a valid, if degraded, measurement* at angles where monocular MediaPipe self-occludes (one eye disappears) and the transform matrix stops being returned at all — a hard failure, not a graceful one. | [ARKit facial-distance accuracy study, PMC10181530](https://pmc.ncbi.nlm.nih.gov/articles/PMC10181530/) |

**Honesty check on "sub-mm stability"**: Apple's dot-projector hardware is *capable* of sub-mm depth resolution at FaceID range (that's the marketing spec). The above independent study measured *applied face-landmark accuracy* at 0.88–9.07% error depending on distance/angle — single-digit-percent, not sub-mm, once you're asking "how far apart are these two points on this face," and it gets *worse*, not flat, with angle. Treat "sub-mm" as a hardware capability claim, not a face-mesh accuracy guarantee.

**Net**: native TrueDepth buys graceful degradation + continued tracking at angles where MediaPipe hard-fails, and 60fps/1220-point mesh density useful for future volumetric work (LIMITATIONS.md already flags "3D face reconstruction for true volumetric wrinkle/sag tracking" as an explicit gap MediaPipe's transformation matrix can't fill — that's the concrete future use case where native AR actually pays for itself). It does not buy dramatically better *relative-tracking* consistency, which is software's job either way.

---

## 2. Routes to native, with tradeoffs

**Shared prerequisite across all four routes**: today the entire pipeline (`cv_pipeline.py` → `consistency_gate.py` → `scoring.py` → `llm_explainer.py` → SQLite) runs in-process inside the Streamlit server. Any native client needs that pipeline behind an HTTP API instead of an in-process Python call. `docs/TDD.md` §5 already sizes this: *"React + FastAPI is a 1-week refactor, deferred."* That 1-week API-ification is a **shared, one-time cost paid once**, not per-route — every option below reuses it as-is.

| Route | What's native | Reuses backend as-is? | New engineering | Key tradeoff |
|---|---|---|---|---|
| **(a) Fully native**: Swift + `ARFaceTrackingConfiguration` (iOS) / Kotlin + ARCore Augmented Faces (Android) | Capture UI + AR session per platform | Yes — via the FastAPI wrapper | Two codebases, two app-store listings, two release cadences | Best possible iOS fidelity; **Android leg buys app-store presence, not better tracking** (§1.1) |
| **(b) React Native / Expo** + AR modules (ViroReact, `react-native-arkit`, or custom Expo config-plugin native modules) | Capture UI in JS/TS, thin native bridge to ARKit/ARCore | Yes | One JS codebase, but face-tracking-specific RN wrappers are thinner and less consistently maintained than raw platform SDKs — expect to still hand-write native module code for the parts (blendshapes, real-time landmark stream) the community libraries don't expose well | Shares more code across platforms than (a); still needs native iOS/Android skill for the AR module itself |
| **(c) Flutter + platform channels** (e.g. `ar_flutter_plugin`, `arkit_plugin`) | Capture UI in Dart, platform channels to ARKit/ARCore | Yes | Existing Flutter AR plugins are general-purpose (markerless AR, object placement) rather than face-tracking-specialized — the face-mesh/blendshape capture code likely still gets hand-written in Swift/Kotlin underneath and piped up through platform channels | Flutter mainly buys shared CRUD/nav UI around the capture screen, not the AR engineering itself |
| **(d) Capacitor/Cordova wrapping** (WebView shell + custom native plugin only for the capture screen) | Everything *except* capture stays web; capture screen is a native plugin | Yes | Official ARKit/ARCore plugins for Capacitor are still at **proposal stage**, not shipped ([capacitor-community/proposals#99](https://github.com/capacitor-community/proposals/issues/99)) — you'd write and maintain the plugin yourself, which is nearly the same native lift as (a) for that one screen. Also: Streamlit is server-rendered, not a static SPA, so wrapping *today's* frontend in a WebView shell isn't a drop-in — this route only gets cheap if the frontend is first rewritten as a real client SPA (which may or may not be an outcome of the current pragmatic web rework) | Lowest **incremental** native surface area of the four, but only if the web layer is already SPA-shaped; camera-frame-rate data crossing a JS↔native bridge is also not what Capacitor/Cordova bridges are optimized for |

**The one universal truth**: in every route, `scoring.py`'s deterministic CV scoring, SQLite persistence, and the LLM explainer are **untouched** — the non-negotiables in `CLAUDE.md` §7 (LLM never sees pixels, scoring stays deterministic) hold regardless of which capture client sends the photo. Only the capture client — currently a Streamlit `declare_component` JS widget — gets replaced or duplicated.

---

## 3. Rough scope / cost / timeline

**Hardware gate, upfront**: `ARFaceTrackingConfiguration` requires a TrueDepth front camera — iPhone X (2017) or later with Face ID, or TrueDepth-equipped iPad Pro models — checked at runtime via `.isSupported` ([Apple docs](https://developer.apple.com/documentation/arkit/arfacetrackingconfiguration)). ARCore Augmented Faces has no such gate — any ARCore-certified Android phone with a standard camera qualifies ([ARCore supported devices](https://developers.google.com/ar/devices)), which is consistent with §1.1: no depth hardware requirement because there's no depth sensing happening.

**Timeline, order of magnitude**:

| Milestone | Estimate | Basis |
|---|---|---|
| Backend API-ification (shared prerequisite) | ~1 week | Already sized in `docs/TDD.md` §5 |
| iOS-only ARKit capture screen, demo/PoC-grade | 4–6 weeks | "AR proof-of-concept can be shipped in 4–6 weeks with a senior team" ([weareaffective.com](https://weareaffective.com/learning-centre/how-long-does-it-take-to-develop-an-ar-mobile-app)) |
| iOS-only, production-hardened (error states, device-fragmentation testing, App Store submission) | 2–4 months | "Basic AR integration into existing apps requires 2-4 months" ([weareaffective.com](https://weareaffective.com/learning-centre/how-long-does-it-take-to-develop-an-ar-mobile-app)) |
| **iOS + Android, both production-shipped, one senior mobile/AR engineer** | **~3–6 months** | Synthesized from the above plus Android release parity work and store-review cycles below — this is Eric's own order-of-magnitude estimate, not a single quoted source; treat as a planning range, not a committed figure |

**Cost, if outsourced instead of built in-house**: agency quotes for AR features run **$100K–$750K** for MVP-to-enterprise scope, at **$60–275/hr** for senior AR engineering talent depending on region ([virtualverse.studio, 2026 pricing](https://virtualverse.studio/blogs/ar-development-cost/)). For FaceTrack specifically — a single capture screen bolted onto an already-built CRUD app, not a general AR product — the realistic framing is **~3–6 months of one senior engineer's time** (in-house opportunity cost), not an agency engagement; agency figures are cited here only to calibrate that the $100K+ end of that range is what happens when the same effort is bought externally rather than built by someone who already knows this codebase.

**App Store review time adds to the above, not included in the estimate**: health/medical-category apps commonly see 5–14 day review cycles vs. days for plain utility apps, plus additional privacy review for apps handling personal health data ([App Store review time overview](https://ptkd.com/app-store/how-long-does-apple-app-store-review-take)).

---

## 4. What you don't get / risks

1. **New regulatory surface FaceTrack doesn't have today.** Apple now requires apps in the Health/Medical category (or with "frequent references to medical or treatment information") to declare **regulated medical device status** on the App Store — effective immediately for new apps, with existing apps required to comply by **early 2027** or lose the ability to ship updates ([MacRumors, 2026-03-26](https://www.macrumors.com/2026/03/26/app-store-medical-device-status/)). A skin-scoring, treatment-tracking clinic app is a plausible trigger for this declaration depending on how it's positioned (cosmetic tracking vs. diagnostic claim) — today, as a browser page, FaceTrack has zero App Store surface and zero exposure to this requirement.
2. **Device fragmentation, and it's asymmetric.** iOS gets real fidelity gains only on TrueDepth hardware (2017+ devices) — old iPhones and all non-Pro iPads are excluded from the AR path entirely and would need a MediaPipe-equivalent fallback anyway, i.e. you'd likely maintain *both* capture paths on iOS. Android gets no fidelity gain at all (§1.1) — you'd be shipping a native Android app purely for app-store presence.
3. **Losing "clone-and-run in a browser" demo simplicity.** `CLAUDE.md` §6 explicitly treats a one-click Streamlit Cloud URL a reviewer opens in any browser, no install, as load-bearing for the AI Fund panel's review experience. A native path replaces that with a TestFlight/Play-internal-testing install flow — real friction for exactly the audience this build challenge is optimizing for.
4. **Two capture clients to keep in sync, not one.** The resolution log in `CLAUDE.md` §5 already shows repeated threshold drift *within a single Python codebase* (pose tolerance re-tuned three times, docstrings falling out of sync with `config.py` constants, multiple "found stale after the fact" entries). Add a second, cross-language capture client (Swift/Kotlin pose/exposure/lighting logic mirroring `consistency_gate.py`) and that class of drift gets strictly harder to catch, not easier — different language, different reviewer, different release cadence.
5. **Unverified: do the clinics even have the hardware?** No primary research yet on what device sits at a Taiwan aesthetic clinic's front desk today. If it's a 3-year-old Android phone or an older iPhone without TrueDepth, native buys nothing until hardware is replaced — this needs a real answer before betting an engineering quarter on it, not an assumption.
6. **Maintenance surface, ongoing.** Every iOS/Android OS release (typically 1/year each) is a new device-compat + API-deprecation cycle for two native codebases, on top of the existing one Python codebase — a permanent multiplier on maintenance cost, not a one-time build cost.

---

## 5. Recommendation

**Not now.** For the clinic MVP and the AI Fund panel demo, the web MediaPipe capture (post the current pragmatic rework) is sufficient: FaceTrack's positioning is **relative longitudinal tracking on a clinic-controlled device**, not absolute diagnostic measurement — exactly the use case `docs/CAPTURE_STABILITY_RESEARCH.md` already found software guidance handles well without hardware. A clinic that wants consistent capture today can simply provision one specific device for the intake station (receptionist-operated, per the existing workflow) — that sidesteps most of §4's fragmentation risk for the in-clinic tier specifically, without writing a single line of native code.

**Revisit native IF, concretely:**

| Trigger | Falsifiable signal |
|---|---|
| (a) At-home patient self-capture becomes a **core** tier, not a peripheral one | Product roadmap commits to home tracking as a primary (not opt-in/secondary) revenue tier — at that point you no longer control the device or environment, and OS-level camera-quality controls + depth-based graceful degradation start mattering for capture *success rate*, not just fidelity |
| (b) Profile/3D fidelity becomes a **hard requirement** | A specific clinical use case needs volumetric measurement (e.g. filler/volume-loss tracking) that MediaPipe's inferred transformation matrix structurally cannot provide — this is the exact gap `docs/LIMITATIONS.md`'s "what we explicitly did not do" section already names |
| (c) Primary research resolves the device-inventory unknown *and* it's favorable | A real survey of target clinics' front-desk hardware shows majority TrueDepth-class iPhones already in use — removes risk #5 above and make the iOS-only leg of route (a) low-regret |

Absent all three, the ~3–6 month engineering investment is better spent hardening the web capture path (the ongoing pragmatic rework), the scoring engine's ground-truth calibration (`docs/VALIDATION.md`), or the at-home ghost-overlay/calibration-card features `CAPTURE_STABILITY_RESEARCH.md` already identifies as the field's converged, cheaper answer to the same longitudinal-consistency problem.

---

## Sources

- ARFaceTrackingConfiguration (device support, `.isSupported`): https://developer.apple.com/documentation/arkit/arfacetrackingconfiguration
- ARKit TrueDepth camera / face-tracking deep-dive (1,220 points, 52 blendshapes, 60fps): https://www.oreateai.com/blog/indepth-analysis-of-arkit-facial-recognition-technology-from-truedepth-camera-to-expression-capture-system/04656b4af7dc89ea9c7e33bf67b09d44
- ARKit facial-distance measurement accuracy across angles (0.88–9.07% error, 10.36% at ±22.5°): https://pmc.ncbi.nlm.nih.gov/articles/PMC10181530/
- ARCore Augmented Faces — no depth sensor required, 468-point mesh: https://developers.google.com/ar/develop/augmented-faces
- ARCore Augmented Faces walkthrough: https://www.geeksforgeeks.org/augmented-faces-with-arcore-in-android/
- ARCore supported devices: https://developers.google.com/ar/devices
- MediaPipe Face Mesh (468-point monocular ML, same class as ARCore Augmented Faces): https://github.com/google-ai-edge/mediapipe/wiki/MediaPipe-Face-Mesh
- React Native AR ecosystem, 2025 state: https://medium.com/@nikhithsomasani/react-native-in-2025-powering-ar-3d-magic-on-mobile-1c0237396876
- Capacitor community AR plugin — still proposal stage: https://github.com/capacitor-community/proposals/issues/99
- Flutter AR plugins (`arkit_plugin`, `ar_flutter_plugin`): https://pub.dev/packages/arkit_plugin
- PWA camera access vs. native capability gaps: https://edana.ch/en/2026/03/25/can-a-web-app-pwa-access-the-camera-like-a-native-app/
- AR development cost, 2026 pricing breakdown: https://virtualverse.studio/blogs/ar-development-cost/
- AR mobile app development timeline: https://weareaffective.com/learning-centre/how-long-does-it-take-to-develop-an-ar-mobile-app
- Apple App Store regulated-medical-device-status declaration requirement (2026-03-26): https://www.macrumors.com/2026/03/26/app-store-medical-device-status/
- App Store review time by app category: https://ptkd.com/app-store/how-long-does-apple-app-store-review-take

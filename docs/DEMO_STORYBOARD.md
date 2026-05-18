# Demo Video Storyboard — FaceTrack CRM

**Target length**: 2 min 50 s ± 15 s
**Audience**: AI Fund panel reviewers
**Recording tool**: Loom (browser, includes mic + camera-bubble) or OBS
**URL to record against**: the **deployed Streamlit Cloud URL**, NOT localhost — proves
the prototype is actually shipped.
**Language**: 繁體中文 voiceover
**Demo subject**: **EricZou** (presenter's own face). Three pre-existing visits
in the database are nano-banana-pro-generated progressions of the same face —
visit 1 with heavy pigmentation, visit 2 mild improvement, visit 3 greatly
improved — so the longitudinal chart tells a personal, visually credible story.

The brief's hardest rule:
> "At least one depth area must be visible in the product or implementation evidence,
> not just described in the PRD or TDD."

In this script the **Photo-Consistency Gate is shown in two places** — once as
a live, on-screen guidance loop during capture (Scene 3 — countdown only fires
when pose / distance / stability all pass), and once as a structural property
in the longitudinal chart's credibility (Scene 4).

---

## Scene-by-scene

### Scene 1 · 00:00 – 00:30 · 開場 + 產品定位（30s）

**Visual**: Browser at the deployed URL. Sidebar fully expanded.

**Voiceover**:
> 「Hi，我是 Eric，這是我的 Build Challenge 作品 FaceTrack CRM。
> 根據上次討論，目標的醫美診所基本上會從台灣開始，所以這邊的 UI 我就先用**繁體中文**。
> 因為時間只有兩天，我用 Streamlit 部署了一個 POC。產品目前嘗試解決兩個問題：
> **第一**，用手機這類一般攝影設備，怎麼拍出**跨次就診可以比對**的照片 — 這邊用到的是基礎的電腦視覺技術；
> **第二**，**追蹤並量化每次病患的皮膚狀態** — 把『有沒有變好』從醫師主觀判斷變成可重現的數字。」

---

### Scene 2 · 00:30 – 00:50 · 產品結構 walkthrough（20s）

**Action**:
1. Hover over the sidebar
2. Point at `👤 病患作業` group — list its 4 pages out loud
3. Point at `📊 資料分析` group — list its 2 pages
4. Click `👥 病患管理` to show the patient list briefly (EricZou + 3 seed patients)
5. Use the dropdown to select **EricZou**

**Voiceover**:
> 「左邊側邊欄分兩塊。上面『**病患作業**』 — 病患管理、新增就診、就診歷史、治療計畫；
> 下面『**資料分析**』 — 縱向追蹤跟系統設定。
> 接下來我會分別 demo 這兩塊，主角是我自己 — EricZou。」

---

### Scene 3 · 00:50 – 01:40 · 智能拍照功能 (50s)

**Action**:
1. Click `📸 新增就診`
2. Stay on the default `📷 即時拍照（MediaPipe Face Mesh）` tab
3. Allow camera permission if prompted
4. Once the green mesh appears overlaid on the face:
   - Show the HUD readout (yaw / pitch / roll / face width)
   - **Hold the face out of position briefly** — the countdown does NOT start
   - **Move to centred, in-range** — the 3-second countdown overlay fires
   - Auto-capture for the **正面 (front)**
5. After front capture, **demonstrate the optional side**:
   - Turn head ~5° left — left profile captures
   - (Optionally skip right) — just click **「✓ 完成」** to finalise

**Voiceover** (timed across the capture):
> 「先示範拍照。我用 MediaPipe Face Mesh 在瀏覽器端跑即時臉部偵測 — 不是傳到 server，
> 是在你的瀏覽器裡跑 478 個地標。
> 你看上面這個 HUD 顯示頭部 yaw、pitch、roll 跟臉部佔比，**只有四個條件全綠了**
> — 姿勢正、距離夠、不太近不太遠、連續穩定 — **倒數計時才會開始**。
> 這就是我講的『影像品管 Gate』 — 它**不是**等你拍完才告訴你照片不能用，
> 是在你按下快門之前就引導你拍對。
> 正面是**必拍**的，因為計分是基於正臉的解剖區域。
> 左右側可以選擇要不要拍 — 拍了會留作紀錄、不參與計分，給醫師參考臉頰側面的紋理。
> 拍完按『完成』送出。」

---

### Scene 4 · 01:40 – 02:40 · 縱向追蹤 + 評分原理 + LLM 解釋 (60s)

**Action**:
1. Click `📈 縱向追蹤`（EricZou 已選）
2. Show the radar chart (5 dimensions × 3 visits, blue → red gradient)
3. Move to the line chart — trace pigmentation from Jan to May
4. Briefly: 各回診詳細分數 table
5. Click `📋 就診歷史` → expand the 5/18 visit
6. Tick **🔬 顯示 ROI 訊號疊圖** — show heatmap, switch metric once
7. Scroll to the AI 解釋 + 治療建議 section

**Voiceover**:
> 「接下來看追蹤的部分。要先說明：做真的三次療程可能會需要數個月，所以我**用 nano-banana-pro
> 把我自己的臉生成三個進展版本** — 第一次是我今天原始的狀態、第二次稍微改善、第三次大幅改善 —
> 然後當作三次就診的資料灌進系統。
> 這是雷達圖跟折線圖：可以看到色素沉澱的 health score 從 4 升到 8，越高代表膚況越好。
> 這個分數**完全是用電腦視覺算的**，不是 LLM 給的 — 我針對色素沉澱、細紋、泛紅、毛孔、膚色均勻度這五個指標，分別用對應的影像演算法算出量化分數。
> 同一張照片重跑 100 次，分數一模一樣。**這是 LLM 評分做不到的。**
> 那 LLM 在哪？我把它放在**解釋層** — 打開歷史紀錄、勾這個 ROI 訊號疊圖，
> 你會看到熱力圖，紅色就是分數的訊號來源，醫師可以直接看到『為什麼是這個分數』。
> 下面 LLM 把數字翻成繁中說明 + 草擬治療建議，給顧問跟病患聽、或者協助醫師決策。
> 當然目前這個版本只是初版 未來還會需要很多優化 — 目前是基本版，phase 2 會做 grounding
> 跟醫師偏好學習。但**結構上 LLM 看不到 pixel，只看分數**，所以它編不出假數字。」

---

### Scene 5 · 02:40 – 02:55 · 收尾 + 誠實列限制 (15s)

**Voiceover**:
> 「48 小時做完。已知限制都寫在 BUILD_NOTES — 化妝偵測、病患身份比對、Fitzpatrick
> 膚色校準是 phase 2 的事。
> GitHub repo、PRD、TDD、限制列表的連結都在信裡。謝謝看完，期待 AI Fund 的回覆。」

---

## Recording checklist

- [ ] Screen recording set to 1920×1080 (or 1280×720 if bandwidth tight)
- [ ] Browser zoomed to ~110% so labels are readable
- [ ] Mic level checked — record a 5-second sample first
- [ ] Webcam bubble in bottom-right corner ON (humanises the demo)
- [ ] Loom set to "Anyone with the link can view" (not 'Workspace only')
- [ ] Tab title shows the deployed URL clearly (not localhost)
- [ ] Camera permission pre-granted for the deployed origin (avoids the
      browser permission popup interrupting Scene 3)
- [ ] EricZou patient + 3 nano-banana visits exist in the DB you're recording
      against. **Streamlit Cloud has a fresh-seeded DB** that does NOT include
      EricZou — so either (a) record against a local `streamlit run app.py`
      whose DB has the bypass, or (b) re-create EricZou's 3 visits on the
      deployed app before recording. See CLAUDE.md §11 for the bypass note.
- [ ] Run through once silently to time the live-capture beat in Scene 3
      (the most variable section)

## Things to NOT do

- ❌ Do not narrate the architecture diagram. The TDD does that already.
- ❌ Do not show code. Reviewer reads code separately.
- ❌ Do not apologise for the UI being plain. Brief says "Rough is fine."
- ❌ Do not exceed 3 min 10 s. Cut the optional left profile capture in
     Scene 3 first if running long.
- ❌ Do not hide the nano-banana origin of EricZou's visits. Honest framing
     ("I generated this progression on my own face") is stronger than implying
     it's a real laser course.
- ❌ Do not record at midnight bleary-eyed — your delivery is half the signal.

## Mapping to the brief's submission rules

| Brief requirement | Where it lands |
|---|---|
| "Working prototype is the main event" | Every scene runs against the live deployed URL |
| "Depth area visible in product, not just docs" | **Scene 3** (gate as real-time capture guidance) + **Scene 4** (heatmap shows score origin) |
| "Standardized intake → quantified profile" | Scene 3 + Scene 4 |
| "Longitudinal comparison across visits" | Scene 4 (radar + line for EricZou) |
| "Treatment suggestions explainable and editable" | Scene 4 (heatmap + editable AI draft) |
| "Real-world imaging variation" | Scene 3 (gate gates pose/distance/stability before capture, not after) |
| "Optional depth: Mandarin UX" | Scene 1 framing + every UI string + voiceover language |
| "What you built / reused / broke" | Voiceover in Scene 5 + BUILD_NOTES.md link |

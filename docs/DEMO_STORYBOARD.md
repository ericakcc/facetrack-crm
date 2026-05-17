# Demo Video Storyboard — FaceTrack CRM

**Target length**: 3–4 minutes
**Audience**: AI Fund panel reviewers
**Recording tool**: Loom (browser, includes mic + camera-bubble) or OBS
**URL to record against**: the **deployed Streamlit Cloud URL**, NOT localhost — proves
the prototype is actually shipped.
**Language**: 繁體中文 voiceover (matches the product's target market)

The whole point of this video is to satisfy the brief's hardest rule:
> "At least one depth area must be visible in the product or implementation evidence,
> not just described in the PRD or TDD."

So the **Photo-Consistency Gate must be shown rejecting real photos**, on camera,
with the 繁中 reason visible. Everything else is supporting evidence.

---

## Scene-by-scene

### Scene 1 · 00:00 – 00:20 · 開場 + 產品定位 (20s)

**Visual**: Browser at the deployed URL. Sidebar showing 3 seed patients.

**Voiceover**:
> 「這是 FaceTrack CRM，給台灣醫美診所櫃台用的智能拍照系統。
> 我用台灣醫美最大宗的療程 — **皮秒雷射淡斑** — 作為 MVP 的追蹤對象。
> 它解決一個被忽略的問題：同一個病患在不同次回診的照片，因為角度、光線、相機都不一樣，
> **根本沒辦法做縱向比較**，所以櫃台跟醫師對『session 2 有沒有效』都只能用眼睛猜。
> 我們用一個確定性的 CV 評分引擎 + 一個影像品管 gate 來解決這個問題。」

---

### Scene 2 · 00:20 – 00:50 · 縱向追蹤 (30s)

**Action**:
1. Click 林雅婷 in sidebar
2. Stay on 📈 縱向追蹤 page
3. Hover over the radar chart, then the trend line chart
4. Show the 各回診詳細分數 table

**Voiceover**:
> 「先看醫師端的縱向追蹤頁。雷達圖把五個皮膚指標疊在同一張圖，每次回診一個顏色。
> 折線圖看時間趨勢 — 例如林雅婷的色素沉澱分數，三次回診從 7.8 降到 4.5，**這代表治療有效**。
> 但前提是：每次的分數要可比。這就是接下來要 demo 的核心。」

---

### Scene 3 · 00:50 – 02:00 · Photo-Consistency Gate（核心 depth area，70s）

**Action**:
1. Switch to 📸 新增就診
2. **Upload `test_face_1.jpg`** (under-exposed)
   - Gate panel shows ❌ on 曝光 column
   - Red error box appears: 「曝光不足（暗部佔比 X%，平均亮度 Y/255）」
3. **Re-upload `test_face_3.jpg`** (over-exposed)
   - Gate panel shows ❌ on 曝光
   - Red error: 「曝光過度…」
4. **Upload `test_face_2.jpg`** (good)
   - Gate panel shows ✅ on 姿勢 / 曝光 / 清晰度
   - Green success: 「通過：本張照片可作為縱向追蹤基準。」
   - Page continues automatically to alignment, ROI crops, scores

**Voiceover** (timed across the three uploads):
> 「現在我以櫃台的身份新增一次就診。每張照片進系統的第一關，是 **影像一致性檢查 Gate**。
> 它做四件事：MediaPipe 算出頭部姿勢、檢查曝光直方圖、Laplacian 變異數判斷清晰度、ArUco 灰卡做白平衡。
> 第一張照片太暗 — gate 直接拒絕，告訴櫃台**為什麼**拒絕、要怎麼重拍。
> 第二張太亮 — 一樣拒絕。
> 第三張通過 — 才進入評分流程。
> 這就是『縱向追蹤要可信』的前提：**爛照片連進門都不准進**。」

---

### Scene 4 · 02:00 – 02:40 · 評分引擎 + AI 草稿 (40s)

**Action**:
1. On the same intake page, scroll to ② 對齊與 ROI 擷取 — show the 4 ROI crops
2. Scroll to ③ 量化分數 — show the 5 metric cards
3. Scroll to ④ AI 解釋與治療建議草稿 — show the Chinese explanation + editable textarea
4. Edit the suggestion textarea (add a phrase like 「先做 patch test」)
5. Click 💾 儲存到病患歷史

**Voiceover**:
> 「通過 gate 後，pipeline 對齊臉部，切出四個感興趣區域：兩頰、額頭、下巴。
> 每個區域跑五個**確定性的 CV metric** — black-hat 形態學、LAB a*、Sobel、LoG、L* stddev。
> 同一張照片重跑 100 次，分數一模一樣。**這是 LLM 評分做不到的事**。
> LLM 在這裡只做最後一層 — 把分數翻成繁中說明 + 草擬一段醫師可以編輯的療程建議。
> 醫師永遠是最後決策者，AI 從來不會覆蓋他的判斷。」

---

### Scene 5 · 02:40 – 03:00 · 確認縱向更新 (20s)

**Action**:
1. Click sidebar 📈 縱向追蹤
2. Show that the trend line now has a new point appended

**Voiceover**:
> 「回到縱向追蹤頁，新加入的這次就診已經寫進趨勢圖，**而且因為它通過 gate，
> 可以放心地跟前面三次直接比較**。這就是整個產品的閉環。
> 下一步，如果要從皮秒淡斑展開到痘疤、肝斑、紅血絲 — **引擎不變、gate 不變、
> Streamlit UI 不變，只是註冊一個新的 metric function**。這套追蹤架構是為這個
> 擴展路徑設計的。」

---

### Scene 6 · 03:00 – 03:30 · 「我也承認系統會壞」(D — failure case, 30s)

**Action**: Upload a **deliberately bad** photo — either a heavy-makeup photo or one
where part of the face is occluded (e.g., hand over mouth, sunglasses).

**Voiceover**:
> 「最後一件事 — 我要展示我的系統會壞的地方。重度上妝、口罩遮臉、或裝飾性鏡頭，
> 我的 gate 可能會誤判通過，但裡面的 CV metric 已經被妝感污染。
> Phase 2 我會加上：(1) 化妝偵測、(2) 病患身份比對（避免櫃台點錯人）、
> (3) 按 Fitzpatrick 膚色分型的分數重新校準。
> 我把這些寫進 BUILD_NOTES 的 limitations 段 — 因為我相信誠實面對 edge case，
> 是這個系統能不能撐到 Phase 3 outcome tracking 的關鍵。」

---

### Scene 7 · 03:30 – 03:45 · 收尾 (15s)

**Voiceover**:
> 「程式碼、PRD、TDD 都在 GitHub repo 的描述裡。Streamlit Cloud 連結也在。
> 謝謝你看完，期待跟 AI Fund team 的下一步討論。」

---

## Recording checklist

- [ ] Screen recording set to 1920×1080 (or 1280×720 if bandwidth is tight)
- [ ] Browser zoomed to ~110% so labels are readable
- [ ] Mic level checked — record a 5-second sample first
- [ ] Webcam bubble in bottom-right corner ON (humanises the demo)
- [ ] Loom set to "Anyone with the link can view" (not 'Workspace only')
- [ ] Tab title shows the deployed URL clearly (not localhost)
- [ ] Have all 3 test photos pre-downloaded so drag-drop is fast
- [ ] Run through once silently to time it before recording with audio

## Things to NOT do

- ❌ Do not narrate the architecture diagram. The TDD does that already.
- ❌ Do not show code. Reviewer will read code separately.
- ❌ Do not apologise for the UI being plain. Brief says "Rough is fine."
- ❌ Do not exceed 4 minutes. Cut Scene 6 first if running long.
- ❌ Do not record at midnight bleary-eyed — your delivery is half the signal.

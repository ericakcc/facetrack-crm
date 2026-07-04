# 專案進度

> 本文件由 `/progress` 指令維護,給人看的進度紀錄。
> 「目前狀態總覽」會被覆寫更新;「進度日誌」逐筆累積(最新在最上)。

## 目前狀態總覽

### ✅ 已完成
- **Session 1–3**(2026-05-17 → 05-19,已提交至 AI Fund):可跑的 Streamlit 原型、Photo-Consistency Gate、五項確定性 CV 膚質指標、LLM 解釋層(Mock/Anthropic/Gemini)、縱向追蹤、實況人臉拍攝元件、就診歷史 ROI 疊圖。GitHub 公開 repo、Streamlit Cloud 部署、Loom demo、PRD/TDD/BUILD_NOTES/LIMITATIONS 四份 panel 文件 + PDF。
- **Session 4**(2026-07-04,已 commit)兩大核心功能全面優化:
  - **Gate v2**:4 → 6 項檢查(臉部曝光、解析度正規化清晰度 + 400px 臉寬下限、光照均勻、皮膚可見度/遮擋、白平衡增益限幅)。
  - **Scoring v2**:512px 臉寬尺度正規化(修掉「分數隨拍攝距離變動」的致命傷)、反光/深影有效遮罩、色素指標去噪、皺紋/毛孔範圍重校、`SCORING_VERSION=2` 逐 visit 存檔 + 零停機 migration。
  - 92 測試全過(原 71)、`ruff` 乾淨;6 份文件 + 3 份 PDF 同步更新;可重現性圖 + 延遲基準重跑。
- **Session 5**(2026-07-04,已 commit)真實資料驗證骨架——把兩大核心功能拿去對 ground-truth 打分:
  - 下載 3 個公開資料集(`data/validation/`,真人像素 gitignore):**FFHQ-Wrinkle**(1000 臉 + 1000 人工皺紋遮罩)、**ACNE04**(394 張醫師分級)、**SCIN**(360 張 Fitzpatrick 分層)。
  - 寫 3 支驗證腳本(`scripts/validation/`,import production 函式、ruff 乾淨)。
  - **實測結論**:皺紋 ROI 排序 ρ=0.42(整臉僅 0.145,實測驗證 ROI 設計);泛紅隨痘痘嚴重度單調上升(建構效度);gate 膚色檢查無深膚偏誤(LIMITATIONS §4 顧慮未成立)。
- **Session 6**(2026-07-05,已 commit)把 Session 5 的發現套用回產品 + 蓋上迴歸測試層:
  - **`WRINKLE_RAW_RANGE` 重校已套用**:`(0.25, 0.75)` → **`(0.20, 0.62)`**(FFHQ 真人臉 p5–p95 實測值),`SCORING_VERSION` 維持 **2**(範圍調整不算公式版本變更)。
  - **驗證骨架轉正為迴歸網**:新增 `tests/test_validation_benchmarks.py`(5 個 opt-in 測試,`pytest -m validation`,~70s,需本機資料);pyproject `addopts` 預設 `-m 'not validation'` 排除,fixtures 在資料缺失時一律 **skip**(不 fail、不 error)。
  - **文件全面重新對齊**:新增 `docs/VALIDATION.md`(3 項 ground-truth 發現的彙總證據,CTO/panel 用);可重現性數字更新為 **σ̄ 0.173 vs 基線 0.686**(~4×),其中皺紋 σ=0.091 部分是 p95 天花板夾制而非純粹穩健性——誠實揭露寫在 `BUILD_NOTES.md` §4;CLAUDE.md / README / TDD 測試數字同步為 **97 tests / 10 files(92 fast + 5 opt-in)**。

### ⚠️ 目前資料 / 狀態
- Session 4 + 5 + 6 皆已 commit(見 `git log`);working tree 乾淨。
- Streamlit Cloud 線上版仍是 v1,需**重新部署**才會吃到 v2 + 重校後的 wrinkle range。
- 現行數字(取代所有舊值):**97 tests / 10 files**(92 fast + 5 opt-in 真實資料 benchmark,`uv run pytest -m validation`)、延遲 **21.6ms p50**、可重現性 **σ̄ 0.173 vs 基線 0.686(~4×)**。臨床準確度有外部 ground-truth 佐證(見 `docs/VALIDATION.md`;仍非院內儀器對照)。

### ❌ 試過但放棄的路(及原因)
- **驗證用整臉 `wrinkle_raw`**:ρ 僅 0.06–0.15,被眼/眉/髮際邊緣污染。改限定 production 皮膚 ROI 後 ρ 跳到 0.42。
- **驗證時跳過 CLAHE**:給出錯誤範圍 [0.05, 0.29] 與「範圍嚴重錯位」的錯誤結論。必須先 `_normalize_lighting`(production 是對 CLAHE 後的裁切計分)→ 真實範圍 [0.20, 0.62]。驗證腳本必須忠實復現 pipeline,否則會給誤導的優化建議。
- **gdown 抓官方 FFHQ 逐圖 Drive ID**:NVIDIA Drive 資料夾擋 gdown。改用 HuggingFace `gaunernst/ffhq-1024-wds` 串流鏡像(只抓需要的 12 個 shard)。
- **正規化到 1024px**(v1 名義尺度):殘餘漂移仍在——500px 網路攝影機臉放大到 1024 沒有原生取樣以上的細節,插值只生出假平滑。改用 **512px**(最低公分母)。
- **找 melasma/MASI、rosacea CEA 分級的公開影像資料集**:確認不存在(相關研究全為院內 VISIA 私有資料)。下次別再重找。

### ⏭️ 待辦(排序)
1. 重新部署 Streamlit Cloud(v2 + wrinkle range 重校)。
2. 實況拍攝 JS HUD 補上光照均勻 + 皮膚可見度兩項新檢查的即時提示。
3. 縱向圖表加 scoring_version 邊界註記(CTO call 前)。
4. 寫信向 Kesty(drkesty@stpeteskinandlaser.com)申請 SkinAnalysis 資料集(五指標最佳對應,須申請)。
5. 考慮為可重現性評測挑一張分數落中段(非高紋理天花板)的參考臉,讓皺紋 σ 不再被 p95 夾制稀釋。

---

## 進度日誌

## 2026-07-04 — Session 5:真實資料驗證骨架(3 資料集 + 3 腳本,對 ground-truth 打分)

**目標**(回應「找真實資料讓我離線優化核心功能」):取得公開、可下載的真人資料,對兩大核心功能(拍照品質 gate + 膚質 scoring)做外部 ground-truth 驗證與調參。

**下載 3 個公開資料集**(全部落 `data/validation/`,真人像素依紅線 #5 gitignore,只留腳本/manifest/彙總 CSV·PNG):
- **FFHQ-Wrinkle**(Kim et al.,CC BY-NC-SA 4.0):1000 張人工皺紋遮罩(gdown)+ 1000 張對應 FFHQ 臉。臉圖用 `stream_extract_ffhq.py` 從 HuggingFace `gaunernst/ffhq-1024-wds` 串流,只抓需要的 12 個 shard、只留有遮罩的 ID(避開 90GB 全下載)。
- **ACNE04**(Wu et al. ICCV 2019,HF `ManuelHettich/acne04`):394 張醫師 Hayashi 0–3 分級臉。
- **SCIN**(Google×Stanford,公開 GCS `dx-scin-public-data`):元資料 CSV + 360 張 Fitzpatrick 分層抽樣(FST1–6 各 60,`sample_download_scin.py` + manifest)。

**寫 3 支驗證腳本**(`scripts/validation/`,直接 import production `facetrack` 函式、無重寫、ruff 乾淨):
- `validate_wrinkle_ffhq.py` — 皺紋排序效度 + Sobel 門檻 sweep + 範圍檢查。
- `validate_severity_acne04.py` — 泛紅/紋理 vs 醫師嚴重度 known-groups。
- `validate_skintone_bias_scin.py` — gate YCrCb 膚色檢查跨 Fitzpatrick 公平性。

**實測發現**:
- **皺紋(n=1000,CLAHE 對齊 production)**:限定 forehead/cheek ROI 排序 ρ=**0.42**,整臉僅 0.145 → 實測驗證 ROI 設計(整臉被眼/眉/髮際邊緣污染)。`wrinkle_raw` 真人臉 p5–p95=**[0.197, 0.619]**,但 `WRINKLE_RAW_RANGE=(0.25, 0.75)` 上限從未觸及 → 建議重校 ≈(0.20, 0.62)(**未套用**,留給人決定)。Sobel=30 在 ROI 內 recall 0.81 / precision 0.083(遮罩是細線、指標是紋理密度代理,非逐線定位——當 0–10 分數 OK,畫皺紋疊圖不夠)。
- **泛紅(ACNE04 known-groups)**:`erythema_raw` 隨嚴重度單調上升(grade0 136.4→grade3 139.7,ρ=+0.23,rank-biserial +0.38)→ 建構效度;wrinkle/pore 正確保持平坦(ρ≈0)→ 區辨效度。
- **膚色公平性(SCIN)**:YCrCb 檢查通過率 FST5-6=94.2% vs FST1-2=92.5%(gap −1.7%,深膚略高)→ LIMITATIONS §4「深膚被誤拒」顧慮在 SCIN 亮度範圍**未成立**(caveat:整圖代理非 ROI patch)。

**其他**:`.gitignore` 新增 validation 區塊(real pixels ignore、scripts/manifest/results 追蹤,已用 `git check-ignore` 驗證);`data/validation/README.md` 記錄來源/license/re-fetch。92 測試仍全過(只新增檔案,未動 `src/`)。auto-memory 快照同步。

**狀態**:S4 + S5 全部未 commit;Streamlit Cloud 待重新部署。

## 2026-07-04 — Session 4:Gate v2 + Scoring v2 全面優化 + 驗證資料集研究

**兩大核心功能優化(先在 `data/test_images` 實測校準,再 TDD 實作):**

- **膚質偵測致命傷修正**:分數取決於拍攝距離/解析度(同照片縮 0.5×,毛孔 4.94→10.00)。三層修法:512px 臉寬尺度正規化(`cv_pipeline._align_face` 同一仿射變換內縮放)+ gate 原生臉寬下限 400px + 色素指標加 3×3 Gaussian 去噪(其固定門檻本在計數隨縮放變動的雜訊)。跨解析度漂移 5.5 → ≤1.05 分。
- **反光/深影排除**:`scoring._effective_mask()` 排除 L*>235 反光與 L*<20 深影(侵蝕 1px,<30% 保留則退回原遮罩)。
- **分數版本化**:`SCORING_VERSION=2` 逐 visit 存檔,`db._migrate_add_visit_scoring_version_column()` 舊資料補 1。
- **校色影像進計分路徑**:灰卡生效時 pipeline 重跑校色影像再計分(修掉「存的照片和存的分數對不上」)。
- **Gate 4→6 檢查**:曝光/清晰度改測臉部裁切、清晰度解析度正規化、新增光照均勻 + 皮膚可見度、白平衡增益限幅 [0.6,1.8]。修掉潛伏 bug:臉部裁切改從 `aligned_image` 取(原本用對齊座標裁原圖,加入縮放後必炸)。

**改動檔案**:`config.py`(v2 常數)、`cv_pipeline.py`、`consistency_gate.py`、`scoring.py`、`db.py`、`app.py`;測試 +21(`test_pipeline_scale.py`、`test_scoring_robustness.py` 新增,`test_consistency_gate.py` +10)。**92 測試全過,`ruff check src/ tests/ app.py` 乾淨。**

**文件同步**:PRD §3–5、TDD §1–7(含新延遲表 21.6ms、誠實可重現性註記)、BUILD_NOTES §4/§6(Session 4 完整理由)、LIMITATIONS §2(遮擋標為已出貨)/§4、README、CLAUDE.md(§12 + resolution log ×4)。`docs/*.pdf` ×3 + `reproducibility.png` 重建。auto-memory 亦同步。

**可重現性數字修正(誠實揭露)**:v1 的 σ̄ 0.074 部分是「皺紋/毛孔分數飽和在 10.0 → 假 σ=0」的假象;v2 範圍讓分數落中段,σ̄ 0.197 vs 基線 0.747。真正重要的跨解析度漂移改善 5 倍。

**驗證資料集研究**(回應「有沒有可驗證的資料」):
- FFHQ-Wrinkle(公開,1000 人工皺紋遮罩)— 驗皺紋,最直接。
- ACNE04(公開,1457 張醫師分級)— known-groups 驗泛紅/紋理。
- SCIN(公開,Google×Stanford,含 Fitzpatrick)— 驗 gate YCrCb 膚色偏誤(LIMITATIONS §4 的洞)。
- Kesty SkinAnalysis(須申請,3662 張,色素+泛紅+皺紋分級)— 五指標最佳對應。
- 免標註替代:UTKFace/FFHQ-Aging 年齡收斂效度;pilot 階段 VISIA 儀器對照。

**狀態**:全部未 commit;Streamlit Cloud 待重新部署。

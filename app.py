"""FaceTrack CRM — Streamlit entry point (繁體中文 UX)."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sqlmodel import select

from facetrack.config import PHOTOS_DIR
from facetrack.consistency_gate import QualityReport, get_gate
from facetrack.cv_pipeline import get_pipeline
from facetrack.db import (
    Patient,
    Region,
    RegionScore,
    TreatmentNote,
    Visit,
    get_session,
    init_db,
)
from facetrack.llm_explainer import get_explainer
from facetrack.scoring import aggregate_face_scores, score_visit
from facetrack.seed import seed_database
from facetrack.visualization import compose_intake_view

METRICS = ("pigmentation", "erythema", "wrinkle", "pore", "uniformity")
METRIC_LABELS_ZH = {
    "pigmentation": "色素沉澱",
    "erythema": "泛紅",
    "wrinkle": "細紋",
    "pore": "毛孔",
    "uniformity": "膚色均勻度",
}

st.set_page_config(
    page_title="FaceTrack CRM｜醫美智能診療系統",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ----------------------------- Bootstrap ------------------------------------


@st.cache_resource
def _bootstrap() -> None:
    """Initialise DB schema and seed once per app process."""
    init_db()
    seed_database(force=False)


@st.cache_resource
def _pipeline():
    return get_pipeline()


@st.cache_resource
def _gate():
    return get_gate()


@st.cache_resource
def _explainer():
    return get_explainer()


_bootstrap()


# ----------------------------- Data access ----------------------------------


def list_patients() -> list[Patient]:
    with get_session() as s:
        return list(s.exec(select(Patient).order_by(Patient.name)).all())


def get_patient(pid: int) -> Patient | None:
    with get_session() as s:
        return s.get(Patient, pid)


def list_visits(patient_id: int) -> list[Visit]:
    with get_session() as s:
        stmt = select(Visit).where(Visit.patient_id == patient_id).order_by(Visit.visit_date)
        return list(s.exec(stmt).all())


def scores_for_visit(visit_id: int) -> dict[Region, RegionScore]:
    with get_session() as s:
        stmt = select(RegionScore).where(RegionScore.visit_id == visit_id)
        return {row.region: row for row in s.exec(stmt).all()}


def treatment_for_visit(visit_id: int) -> TreatmentNote | None:
    with get_session() as s:
        stmt = select(TreatmentNote).where(TreatmentNote.visit_id == visit_id)
        return s.exec(stmt).first()


# ----------------------------- Charts ---------------------------------------


def visit_score_dict(visit_id: int) -> dict[str, float]:
    """Aggregate per-region scores for a visit into one dict keyed by metric."""
    regions = scores_for_visit(visit_id)
    if not regions:
        return {m: 0.0 for m in METRICS}
    out: dict[str, float] = {}
    for m in METRICS:
        vals = [getattr(s, m) for s in regions.values()]
        out[m] = round(float(np.mean(vals)), 2)
    return out


def radar_chart(visits: list[Visit], scores_by_visit: dict[int, dict[str, float]]) -> go.Figure:
    """Polar chart: one trace per visit, axes = 5 metrics."""
    fig = go.Figure()
    categories = [METRIC_LABELS_ZH[m] for m in METRICS]
    for v in visits:
        scores = scores_by_visit.get(v.id, {})
        # Invert uniformity so high = better visually on radar
        values = [
            scores.get(m, 0.0) if m != "uniformity" else 10.0 - scores.get(m, 0.0) for m in METRICS
        ]
        fig.add_trace(
            go.Scatterpolar(
                r=values + [values[0]],
                theta=categories + [categories[0]],
                fill="toself",
                name=v.visit_date.strftime("%Y-%m-%d"),
                opacity=0.55,
            )
        )
    fig.update_layout(
        polar={"radialaxis": {"visible": True, "range": [0, 10]}},
        showlegend=True,
        margin=dict(t=20, b=20, l=20, r=20),
        height=420,
    )
    return fig


def line_chart(visits: list[Visit], scores_by_visit: dict[int, dict[str, float]]) -> go.Figure:
    """Multi-metric line chart over visit dates."""
    fig = go.Figure()
    dates = [v.visit_date for v in visits]
    for m in METRICS:
        ys = [scores_by_visit.get(v.id, {}).get(m, 0.0) for v in visits]
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=ys,
                mode="lines+markers",
                name=METRIC_LABELS_ZH[m],
            )
        )
    fig.update_layout(
        xaxis_title="就診日期",
        yaxis_title="分數 (0–10)",
        yaxis=dict(range=[0, 10]),
        margin=dict(t=10, b=40, l=40, r=10),
        height=360,
        legend=dict(orientation="h", y=-0.2),
    )
    return fig


# ----------------------------- Sidebar --------------------------------------


def sidebar_nav() -> tuple[Patient | None, str]:
    st.sidebar.title("✨ FaceTrack CRM")
    st.sidebar.caption("醫美診所｜智能診療系統")

    patients = list_patients()
    if not patients:
        st.sidebar.warning("尚無病患資料，請先執行 seed 腳本。")
        return None, "list"

    name_map = {f"{p.name}（{p.id}）": p for p in patients}
    selected_name = st.sidebar.selectbox("選擇病患", list(name_map.keys()))
    selected = name_map[selected_name]

    st.sidebar.markdown("---")
    page = st.sidebar.radio(
        "頁面",
        options=["overview", "intake", "history", "treatment", "settings"],
        format_func=lambda key: {
            "overview": "📈 縱向追蹤",
            "intake": "📸 新增就診（攝入流程）",
            "history": "📋 就診歷史",
            "treatment": "💉 治療計畫",
            "settings": "⚙️ 設定",
        }[key],
    )
    st.sidebar.markdown("---")
    st.sidebar.caption(f"病患總數：{len(patients)}")
    st.sidebar.caption(f"目前模型：{_explainer().__class__.__name__}")
    return selected, page


# ----------------------------- Pages ----------------------------------------


def page_overview(patient: Patient) -> None:
    st.header(f"📈 縱向追蹤｜{patient.name}")
    st.caption(f"電話：{patient.phone}　生日：{patient.birth_date}　主訴：{patient.notes}")

    visits = list_visits(patient.id)
    if not visits:
        st.info("尚無就診紀錄，請至『新增就診』上傳照片。")
        return

    scores_by_visit = {v.id: visit_score_dict(v.id) for v in visits}

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("分數雷達圖")
        st.caption(
            "外緣為 10 分。色素沉澱／泛紅／細紋／毛孔越靠外越嚴重；膚色均勻度已反向，越靠外越好。"
        )
        st.plotly_chart(radar_chart(visits, scores_by_visit), use_container_width=True)
    with col2:
        st.subheader("分數趨勢")
        st.caption("時間序列追蹤每項指標的變化。")
        st.plotly_chart(line_chart(visits, scores_by_visit), use_container_width=True)

    st.subheader("各回診詳細分數")
    rows: list[dict[str, Any]] = []
    for v in visits:
        row = {"就診日期": v.visit_date, "品管": "✅" if v.quality_passed else "❌"}
        scores = scores_by_visit[v.id]
        for m in METRICS:
            row[METRIC_LABELS_ZH[m]] = scores[m]
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_quality_report(report: QualityReport) -> None:
    """Side-by-side visualization of the four quality checks."""
    cols = st.columns(4)
    checks = [
        ("姿勢", report.pose, "yaw_deg"),
        ("曝光", report.exposure, "mean_brightness"),
        ("清晰度", report.sharpness, "laplacian_variance"),
        ("色彩校正", report.color, "marker_detected"),
    ]
    for col, (name, check, key) in zip(cols, checks, strict=False):
        with col:
            icon = "✅" if check.passed else "❌"
            st.metric(label=f"{icon} {name}", value=str(check.measurement.get(key, "—")))
    if report.failure_reasons_zh:
        st.error("**未通過原因**：\n\n" + "\n\n".join(f"- {r}" for r in report.failure_reasons_zh))
    else:
        st.success(report.summary_zh)


def page_intake(patient: Patient) -> None:
    st.header(f"📸 新增就診｜{patient.name}")
    st.caption(
        "使用相機即時拍攝、或上傳既有照片。系統會先執行『影像一致性檢查』，通過後才計算分數。"
    )

    source_tabs = st.tabs(["📷 即時拍照", "📁 上傳照片"])
    with source_tabs[0]:
        camera_photo = st.camera_input(
            "請對準鏡頭，按下方按鈕拍攝",
            help="與真實診所動線一致：櫃台拍攝後系統即時把關，不通過會立刻退回重拍。",
            key=f"camera_{patient.id}",
        )
    with source_tabs[1]:
        uploaded_file = st.file_uploader(
            "選擇照片（JPG / PNG）",
            type=["jpg", "jpeg", "png"],
            key=f"uploader_{patient.id}",
        )

    uploaded = camera_photo or uploaded_file
    if not uploaded:
        st.info("尚未取得照片。建議拍攝條件：正面、均勻光線、距離 30–50 公分、無濾鏡。")
        return

    file_bytes = np.frombuffer(uploaded.getvalue(), dtype=np.uint8)
    image_bgr = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    if image_bgr is None:
        st.error("無法解讀此圖檔。")
        return

    pipeline = _pipeline()
    pipeline_result = pipeline.process(image_bgr)
    gate = _gate()
    report, calibrated = gate.evaluate(image_bgr, pipeline_result)

    st.subheader("① 影像一致性檢查")
    _render_quality_report(report)

    if not pipeline_result.face_detected:
        st.error("未偵測到臉部，已中止後續處理。")
        return

    st.subheader("② 對齊與色素熱力圖")
    st.caption(
        "**皮秒雷射療程追蹤模式**｜預設顯示色素沉澱熱力圖。"
        "可下拉切換其他指標（細紋／毛孔／泛紅／均勻度）、開啟 478 地標點或 ROI 框。"
    )
    st.caption(
        "熱力圖直接呈現分數的中間訊號 — black-hat 形態學在哪裡反應強，色素分數就是怎麼算出來的。"
        "這也是 TDD §3 explainability 承諾的兌現。"
    )

    viz_cols = st.columns([3, 1])
    with viz_cols[1]:
        heatmap_option = st.selectbox(
            "熱力圖",
            options=["none", *METRICS],
            index=1,  # default = "pigmentation" — primary metric for laser-pigmentation tracking
            format_func=lambda key: "（無）" if key == "none" else f"{METRIC_LABELS_ZH[key]}",
            key=f"heatmap_{patient.id}",
        )
        show_landmarks = st.checkbox("顯示 478 地標點（分色）", value=False, key=f"lm_{patient.id}")
        show_roi_boxes = st.checkbox("顯示 ROI 解剖區域", value=False, key=f"roi_{patient.id}")
        show_tessellation = st.checkbox("顯示 mesh 線稿", value=False, key=f"tess_{patient.id}")
        st.caption(
            "熱力圖中：紅 = 訊號強（該指標反應大）；藍 = 訊號弱。"
            "色素沉澱看 black-hat、細紋看 Sobel、毛孔看 LoG、泛紅看 LAB a*、"
            "均勻度看 L* 局部標準差。"
        )

    composed_bgr = compose_intake_view(
        pipeline_result.aligned_image,
        pipeline_result.landmarks_px,
        pipeline_result.roi_polygons,
        roi_bboxes=pipeline_result.roi_bboxes,
        heatmap_metric=None if heatmap_option == "none" else heatmap_option,
        show_landmarks=show_landmarks,
        show_roi=show_roi_boxes,
        show_tessellation=show_tessellation,
    )
    composed_caption = (
        "對齊後（已套用熱力圖：" + METRIC_LABELS_ZH[heatmap_option] + "）"
        if heatmap_option != "none"
        else "對齊後（無熱力圖）"
    )
    viz_cols[0].image(
        cv2.cvtColor(composed_bgr, cv2.COLOR_BGR2RGB),
        caption=composed_caption,
        use_container_width=True,
    )

    with st.expander("各 ROI 局部影像（CLAHE 平衡後）", expanded=False):
        roi_cols = st.columns(4)
        for col, region in zip(roi_cols, Region, strict=False):
            roi = pipeline_result.rois.get(region)
            if roi is not None:
                col.image(
                    cv2.cvtColor(roi, cv2.COLOR_BGR2RGB),
                    caption=region_label_zh(region),
                    use_container_width=True,
                )

    if not report.overall_passed:
        st.warning("此照片未通過一致性檢查，可繼續評分，但不會用於縱向追蹤基準。")
        proceed = st.checkbox("我仍要繼續評分（僅供參考）", value=False)
        if not proceed:
            return

    st.subheader("③ 量化分數")
    region_scores = score_visit(pipeline_result.rois, pipeline_result.roi_masks)
    agg = aggregate_face_scores(region_scores)
    score_cols = st.columns(5)
    for col, m in zip(score_cols, METRICS, strict=False):
        col.metric(METRIC_LABELS_ZH[m], f"{agg[m]:.1f}")

    st.subheader("④ AI 解釋與治療建議草稿")
    prev_visits = list_visits(patient.id)
    scores_prev = visit_score_dict(prev_visits[-1].id) if prev_visits else None
    explainer = _explainer()
    with st.spinner("生成解釋中…"):
        explainer_out = explainer.explain(agg, scores_prev, patient.name)
    st.markdown(explainer_out.explanation_zh)
    suggestion_text = st.text_area(
        "治療建議（可編輯）",
        value=explainer_out.suggestion_zh,
        height=180,
        key="suggestion_draft",
    )
    clinician_notes = st.text_area("醫師備註（可選）", value="", height=80, key="clinician_notes")
    st.caption(f"模型來源：{explainer_out.backend}")

    st.subheader("⑤ 儲存就診紀錄")
    save_col, _ = st.columns([1, 3])
    if save_col.button("💾 儲存到病患歷史", type="primary"):
        photo_path = PHOTOS_DIR / f"patient{patient.id}_{datetime.utcnow():%Y%m%d_%H%M%S}.jpg"
        cv2.imwrite(str(photo_path), calibrated)
        with get_session() as session:
            visit = Visit(
                patient_id=patient.id,
                visit_date=date.today(),
                photo_path=str(photo_path.relative_to(PHOTOS_DIR.parent.parent)),
                quality_passed=report.overall_passed,
                quality_report_json=json.dumps(report.to_dict(), ensure_ascii=False, default=str),
            )
            session.add(visit)
            session.commit()
            session.refresh(visit)
            for region, scores in region_scores.items():
                session.add(
                    RegionScore(
                        visit_id=visit.id,
                        region=region,
                        pigmentation=scores.pigmentation,
                        erythema=scores.erythema,
                        wrinkle=scores.wrinkle,
                        pore=scores.pore,
                        uniformity=scores.uniformity,
                    )
                )
            session.add(
                TreatmentNote(
                    visit_id=visit.id,
                    ai_explanation=explainer_out.explanation_zh,
                    ai_suggestion=suggestion_text,
                    clinician_notes=clinician_notes,
                )
            )
            session.commit()
        st.success(
            f"已儲存就診紀錄（visit_id={visit.id}）。請切換到『縱向追蹤』檢視更新後的趨勢圖。"
        )


def region_label_zh(region: Region) -> str:
    mapping = {
        Region.LEFT_CHEEK: "左頰",
        Region.RIGHT_CHEEK: "右頰",
        Region.FOREHEAD: "額頭",
        Region.CHIN: "下巴",
    }
    return mapping.get(region, region.value)


def page_history(patient: Patient) -> None:
    st.header(f"📋 就診歷史｜{patient.name}")
    visits = list_visits(patient.id)
    if not visits:
        st.info("尚無就診紀錄。")
        return
    for v in reversed(visits):  # newest first
        with st.expander(f"📅 {v.visit_date} — 品管 {'通過' if v.quality_passed else '未通過'}"):
            cols = st.columns([1, 2])
            with cols[0]:
                photo = Path(v.photo_path) if v.photo_path else None
                if photo and photo.exists():
                    st.image(str(photo), caption="儲存的照片")
                else:
                    st.caption("（此筆為 seed 資料，無實際照片）")
            with cols[1]:
                try:
                    report_data = json.loads(v.quality_report_json)
                    st.json(report_data, expanded=False)
                except json.JSONDecodeError:
                    st.caption("品管報告不可讀。")
            scores = scores_for_visit(v.id)
            if scores:
                df = pd.DataFrame(
                    [
                        {
                            "區域": region_label_zh(s.region),
                            **{METRIC_LABELS_ZH[m]: getattr(s, m) for m in METRICS},
                        }
                        for s in scores.values()
                    ]
                )
                st.dataframe(df, hide_index=True, use_container_width=True)
            note = treatment_for_visit(v.id)
            if note:
                st.markdown(f"**AI 解釋**：{note.ai_explanation}")
                st.markdown(f"**治療建議**：\n\n{note.ai_suggestion}")
                if note.clinician_notes:
                    st.markdown(f"**醫師備註**：{note.clinician_notes}")


def page_treatment(patient: Patient) -> None:
    st.header(f"💉 治療計畫｜{patient.name}")
    visits = list_visits(patient.id)
    if not visits:
        st.info("尚無就診紀錄。")
        return
    latest = visits[-1]
    note = treatment_for_visit(latest.id)
    if not note:
        st.info("最近一次就診尚無治療建議。請至『新增就診』完成評估。")
        return

    st.caption(f"基於最近一次就診（{latest.visit_date}）")
    st.markdown("### AI 自動解釋")
    st.markdown(note.ai_explanation)

    st.markdown("### 治療建議（可編輯）")
    new_suggestion = st.text_area(
        "建議內容",
        value=note.ai_suggestion,
        height=200,
        key=f"edit_suggestion_{latest.id}",
    )
    new_clinician_notes = st.text_area(
        "醫師備註",
        value=note.clinician_notes,
        height=120,
        key=f"edit_notes_{latest.id}",
    )
    if st.button("💾 儲存修改", type="primary"):
        with get_session() as session:
            db_note = session.get(TreatmentNote, note.id)
            db_note.ai_suggestion = new_suggestion
            db_note.clinician_notes = new_clinician_notes
            db_note.edited_at = datetime.utcnow()
            session.commit()
        st.success("已儲存修改。")


def page_settings() -> None:
    st.header("⚙️ 設定")
    from facetrack.config import (
        ANTHROPIC_API_KEY,
        DB_PATH,
        EXPOSURE_HIGH_PCT,
        EXPOSURE_LOW_PCT,
        LLM_MODEL,
        POSE_TOLERANCE_DEG,
        SHARPNESS_MIN_LAPLACIAN_VAR,
    )

    st.subheader("環境")
    st.code(
        f"DB_PATH            = {DB_PATH}\n"
        f"LLM_MODEL          = {LLM_MODEL}\n"
        f"ANTHROPIC_API_KEY  = {'(已設定)' if ANTHROPIC_API_KEY else '(未設定 — 使用 Mock)'}",
        language="text",
    )

    st.subheader("一致性檢查參數")
    st.code(
        f"POSE_TOLERANCE_DEG          = ±{POSE_TOLERANCE_DEG}°\n"
        f"EXPOSURE_LOW_PCT            = {EXPOSURE_LOW_PCT}\n"
        f"EXPOSURE_HIGH_PCT           = {EXPOSURE_HIGH_PCT}\n"
        f"SHARPNESS_MIN_LAPLACIAN_VAR = {SHARPNESS_MIN_LAPLACIAN_VAR}",
        language="text",
    )

    st.subheader("重置示範資料")
    if st.button("⚠️ 清空並重新 seed", help="刪除所有病患與就診紀錄，重新建立 3 名示範病患。"):
        seed_database(force=True)
        st.success("已重新 seed。請重新整理頁面。")


# ----------------------------- Router ---------------------------------------

selected_patient, page = sidebar_nav()

if page == "settings" or selected_patient is None:
    if page == "settings":
        page_settings()
    else:
        st.info("請從左側選擇病患。")
elif page == "overview":
    page_overview(selected_patient)
elif page == "intake":
    page_intake(selected_patient)
elif page == "history":
    page_history(selected_patient)
elif page == "treatment":
    page_treatment(selected_patient)
else:
    st.error(f"未知頁面：{page}")

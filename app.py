"""FaceTrack CRM — Streamlit entry point (繁體中文 UX)."""

from __future__ import annotations

import base64
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

from facetrack.components.face_capture import face_capture
from facetrack.config import (
    LIVE_CAPTURE_COUNTDOWN_MS,
    LIVE_CAPTURE_MAX_FACE_WIDTH_RATIO,
    LIVE_CAPTURE_MIN_FACE_WIDTH_RATIO,
    LIVE_CAPTURE_STABILITY_FRAMES,
    PHOTOS_DIR,
    POSE_TOLERANCE_DEG,
    PROFILE_PITCH_TOLERANCE_DEG,
    PROFILE_YAW_MIN_DEG,
)
from facetrack.consistency_gate import QualityReport, get_gate
from facetrack.cv_pipeline import get_pipeline
from facetrack.db import (
    REGION_LABELS_ZH,
    Gender,
    Patient,
    Region,
    RegionScore,
    TreatmentNote,
    Visit,
    get_session,
    init_db,
)
from facetrack.ghost_photos import get_ghost_photos
from facetrack.llm_explainer import get_explainer
from facetrack.patient_service import (
    create_patient,
    get_patient,
    list_patients,
    restore_patient,
    soft_delete_patient,
    update_patient,
)
from facetrack.score_display import (
    COLOR_GOOD,
    COLOR_NEUTRAL,
    COLOR_POOR,
    health_band,
    to_health_score,
)
from facetrack.scoring import SCORING_VERSION, aggregate_face_scores, score_visit
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


@st.cache_data(show_spinner=False)
def _history_overlay_rgb(
    photo_relpath: str,
    mtime: float,
    metric: str | None,
    show_roi: bool,
) -> np.ndarray | None:
    """Re-run alignment + heatmap compose on a stored visit photo.

    Cached on (path, mtime, metric, show_roi) so flipping metrics in the
    history view doesn't re-trigger MediaPipe. Returns None when the file
    can't be read or no face is detected (caller renders a fallback caption).
    """
    p = Path(photo_relpath)
    img_bgr = cv2.imread(str(p), cv2.IMREAD_COLOR)
    if img_bgr is None:
        return None
    result = _pipeline().process(img_bgr)
    if not result.face_detected:
        return None
    composed = compose_intake_view(
        result.aligned_image,
        result.landmarks_px,
        result.roi_polygons,
        roi_bboxes=result.roi_bboxes,
        heatmap_metric=metric,
        show_landmarks=False,
        show_roi=show_roi,
        show_tessellation=False,
    )
    return cv2.cvtColor(composed, cv2.COLOR_BGR2RGB)


@st.cache_data(show_spinner=False)
def _history_rois_rgb(
    photo_relpath: str,
    mtime: float,
) -> dict[str, np.ndarray] | None:
    """Return per-ROI CLAHE-balanced crops keyed by Region.value (str).

    Region keys are stringified so the dict survives cache serialization.
    """
    p = Path(photo_relpath)
    img_bgr = cv2.imread(str(p), cv2.IMREAD_COLOR)
    if img_bgr is None:
        return None
    result = _pipeline().process(img_bgr)
    if not result.face_detected:
        return None
    return {
        region.value: cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
        for region, roi in result.rois.items()
        if roi is not None
    }


@st.cache_resource
def _explainer():
    return get_explainer()


_bootstrap()


# ----------------------------- Data access ----------------------------------
# Patient CRUD lives in facetrack.patient_service and is imported above.


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
    """Polar chart: one trace per visit, axes = 5 metrics, outer edge = healthier."""
    fig = go.Figure()
    categories = [METRIC_LABELS_ZH[m] for m in METRICS]
    for v in visits:
        scores = scores_by_visit.get(v.id, {})
        # Unified health scores: concern metrics are flipped so outer = better
        # across all 5 axes. A bigger polygon now means a healthier patient.
        values = [to_health_score(m, scores.get(m, 0.0)) for m in METRICS]
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
    """Multi-metric line chart over visit dates (unified health score, high = better)."""
    fig = go.Figure()
    dates = [v.visit_date for v in visits]
    for m in METRICS:
        ys = [to_health_score(m, scores_by_visit.get(v.id, {}).get(m, 0.0)) for v in visits]
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
        yaxis_title="膚況指數 (高 = 好)",
        yaxis=dict(range=[0, 10]),
        margin=dict(t=10, b=40, l=40, r=10),
        height=360,
        legend=dict(orientation="h", y=-0.2),
    )
    return fig


# ----------------------------- Sidebar --------------------------------------


PAGE_LABELS: dict[str, str] = {
    "patients": "👥 病患管理",
    "intake": "📸 新增就診",
    "history": "📋 就診歷史",
    "treatment": "💉 治療計畫",
    "overview": "📈 縱向追蹤",
    "settings": "⚙️ 設定",
}
PATIENT_OPS_PAGES: tuple[str, ...] = ("patients", "intake", "history", "treatment")
ANALYTICS_PAGES: tuple[str, ...] = ("overview", "settings")
PATIENT_REQUIRED_PAGES: frozenset[str] = frozenset({"overview", "intake", "history", "treatment"})


def _on_patient_ops_change() -> None:
    """Sync the patient-ops radio into the canonical active_page; clear analytics radio."""
    st.session_state["active_page"] = st.session_state["radio_patient_ops"]
    st.session_state["radio_analytics"] = None


def _on_analytics_change() -> None:
    """Sync the analytics radio into the canonical active_page; clear patient-ops radio."""
    st.session_state["active_page"] = st.session_state["radio_analytics"]
    st.session_state["radio_patient_ops"] = None


def sidebar_nav() -> tuple[Patient | None, str]:
    st.sidebar.title("✨ FaceTrack CRM")
    st.sidebar.caption("醫美診所｜智能診療系統")

    # First-time default: land on patient management so a fresh user always
    # sees the empty-state "add your first patient" CTA.
    if "active_page" not in st.session_state:
        st.session_state["active_page"] = "patients"

    patients = list_patients(include_inactive=False)

    # ----- Patient selectbox (with cross-page navigation override) -----
    selected: Patient | None = None
    if patients:
        name_map = {f"{p.name}（{p.id}）": p for p in patients}
        names = list(name_map.keys())

        forced_id = st.session_state.pop("force_select_patient_id", None)
        if forced_id is not None:
            forced_label = next((label for label, p in name_map.items() if p.id == forced_id), None)
            if forced_label is not None:
                st.session_state["patient_selectbox"] = forced_label

        selected_name = st.sidebar.selectbox(
            "選擇病患",
            names,
            key="patient_selectbox",
        )
        selected = name_map[selected_name]
    else:
        st.sidebar.info("尚無病患資料 — 請在「👥 病患管理」新增第一位病患。")
        # Force the user onto the management page; no other choices make sense.
        st.session_state["active_page"] = "patients"

    st.sidebar.markdown("---")

    # ----- Two grouped radios with mutual exclusion via session_state -----
    active = st.session_state["active_page"]

    st.sidebar.markdown("**👤 病患作業**")
    patient_ops_index = PATIENT_OPS_PAGES.index(active) if active in PATIENT_OPS_PAGES else None
    st.sidebar.radio(
        "patient_ops",
        options=PATIENT_OPS_PAGES,
        index=patient_ops_index,
        format_func=lambda key: PAGE_LABELS[key],
        key="radio_patient_ops",
        on_change=_on_patient_ops_change,
        label_visibility="collapsed",
    )

    st.sidebar.markdown("**📊 資料分析**")
    analytics_index = ANALYTICS_PAGES.index(active) if active in ANALYTICS_PAGES else None
    st.sidebar.radio(
        "analytics",
        options=ANALYTICS_PAGES,
        index=analytics_index,
        format_func=lambda key: PAGE_LABELS[key],
        key="radio_analytics",
        on_change=_on_analytics_change,
        label_visibility="collapsed",
    )

    st.sidebar.markdown("---")
    st.sidebar.caption(f"病患總數：{len(patients)}")
    st.sidebar.caption(f"目前模型：{_explainer().__class__.__name__}")

    return selected, st.session_state["active_page"]


# ----------------------------- Pages ----------------------------------------


def _count_visits(patient_id: int) -> int:
    """Number of visits for a patient (used in the management table)."""
    with get_session() as session:
        return len(list(session.exec(select(Visit).where(Visit.patient_id == patient_id)).all()))


@st.dialog("編輯病患資料")
def _edit_patient_dialog(patient_id: int) -> None:
    patient = get_patient(patient_id)
    if patient is None:
        st.error("找不到該病患（可能已被移除）。")
        return

    with st.form(f"edit_patient_form_{patient_id}", clear_on_submit=False):
        new_name = st.text_input("姓名 *", value=patient.name)
        new_gender = st.selectbox(
            "性別",
            options=list(Gender),
            index=list(Gender).index(patient.gender),
            format_func=lambda g: {"female": "女", "male": "男", "other": "其他"}[g.value],
        )
        new_birth = st.date_input(
            "生日",
            value=patient.birth_date,
            min_value=date(1900, 1, 1),
            max_value=date.today(),
        )
        new_phone = st.text_input("聯絡電話", value=patient.phone)
        new_notes = st.text_area("主訴／備註", value=patient.notes, height=100)
        col_save, col_cancel = st.columns(2)
        save = col_save.form_submit_button("💾 儲存", type="primary", width="stretch")
        cancel = col_cancel.form_submit_button("取消", width="stretch")

    if cancel:
        st.rerun()
    if save:
        try:
            update_patient(
                patient_id,
                name=new_name,
                gender=new_gender,
                birth_date=new_birth,
                phone=new_phone,
                notes=new_notes,
            )
        except ValueError as exc:
            st.error(str(exc))
            return
        st.success("已更新病患資料。")
        st.rerun()


@st.dialog("確認停用病患")
def _confirm_soft_delete_dialog(patient_id: int) -> None:
    patient = get_patient(patient_id)
    if patient is None:
        st.error("找不到該病患。")
        return
    visit_count = _count_visits(patient_id)
    st.warning(
        f"即將停用 **{patient.name}**。\n\n"
        f"此病患有 **{visit_count}** 筆歷史就診資料 — 停用後資料仍會保留，"
        "可在「顯示已停用病患」中還原。"
    )
    col_confirm, col_cancel = st.columns(2)
    if col_confirm.button("🗑️ 確認停用", type="primary", width="stretch"):
        soft_delete_patient(patient_id)
        st.session_state.pop("patient_selectbox", None)
        st.rerun()
    if col_cancel.button("取消", width="stretch"):
        st.rerun()


def _gender_label(gender: Gender) -> str:
    return {"female": "女", "male": "男", "other": "其他"}[gender.value]


def page_patients() -> None:
    st.header("👥 病患管理")
    st.caption(
        "新增、編輯或停用病患資料。"
        "停用的病患會保留歷史就診資料，可隨時還原；側邊欄的下拉選單不會顯示停用病患。"
    )

    all_active = list_patients(include_inactive=False)

    with st.expander("➕ 新增病患", expanded=not all_active):
        with st.form("new_patient_form", clear_on_submit=True):
            col_name, col_gender = st.columns([2, 1])
            new_name = col_name.text_input("姓名 *", placeholder="如：林雅婷")
            new_gender = col_gender.selectbox(
                "性別",
                options=list(Gender),
                format_func=_gender_label,
            )
            col_birth, col_phone = st.columns(2)
            new_birth = col_birth.date_input(
                "生日",
                value=date(1990, 1, 1),
                min_value=date(1900, 1, 1),
                max_value=date.today(),
            )
            new_phone = col_phone.text_input("聯絡電話", placeholder="如：0912-345-678")
            new_notes = st.text_area(
                "主訴／備註", placeholder="如：兩頰色素沉澱，希望改善膚色均勻度。"
            )
            submitted = st.form_submit_button("✓ 建立病患", type="primary")
        if submitted:
            try:
                created = create_patient(
                    name=new_name,
                    gender=new_gender,
                    birth_date=new_birth,
                    phone=new_phone,
                    notes=new_notes,
                )
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.success(f"已新增病患「{created.name}」。請至『新增就診』為其建立第一筆紀錄。")
                st.session_state.pop("patient_selectbox", None)
                st.rerun()

    st.markdown("---")
    show_inactive = st.toggle(
        "顯示已停用病患",
        value=False,
        help="勾選後會列出已停用的病患並提供還原按鈕。",
    )
    patients = list_patients(include_inactive=show_inactive)

    if not patients:
        if show_inactive:
            st.info("尚無已停用病患。")
        else:
            st.info("尚未新增任何病患。請使用上方表單建立第一位病患。")
        return

    st.markdown(f"#### 病患列表（共 {len(patients)} 位）")
    for p in patients:
        with st.container(border=True):
            col_meta, col_clinical, col_visits, col_actions = st.columns([3, 2, 1, 2])
            inactive_tag = " 　🚫 已停用" if not p.is_active else ""
            col_meta.markdown(f"**{p.name}**{inactive_tag}")
            col_meta.caption(f"📞 {p.phone or '—'}")
            col_clinical.markdown(f"🎂 {p.birth_date}")
            col_clinical.caption(f"性別：{_gender_label(p.gender)}")
            col_visits.metric("就診數", _count_visits(p.id))
            if p.is_active:
                if col_actions.button("✏️ 編輯", key=f"edit_btn_{p.id}", width="stretch"):
                    _edit_patient_dialog(p.id)
                if col_actions.button("🗑️ 停用", key=f"del_btn_{p.id}", width="stretch"):
                    _confirm_soft_delete_dialog(p.id)
            else:
                if col_actions.button(
                    "↩️ 還原", key=f"restore_btn_{p.id}", type="primary", width="stretch"
                ):
                    restore_patient(p.id)
                    st.session_state.pop("patient_selectbox", None)
                    st.rerun()
            if p.notes:
                st.caption(f"📝 {p.notes}")


def page_overview(patient: Patient) -> None:
    st.header(f"📈 縱向追蹤｜{patient.name}")
    st.caption(f"電話：{patient.phone}　生日：{patient.birth_date}　主訴：{patient.notes}")

    visits = list_visits(patient.id)
    if not visits:
        st.info("尚無就診紀錄，請至『新增就診』上傳照片。")
        return

    include_failed = st.checkbox(
        "將品質未通過的就診納入趨勢圖",
        value=False,
        help="預設只把品管通過的就診畫進雷達圖與趨勢線，避免被未對齊或曝光異常的照片誤導判讀。",
    )
    chart_visits = visits if include_failed else [v for v in visits if v.quality_passed]

    scores_by_visit = {v.id: visit_score_dict(v.id) for v in visits}

    if not chart_visits:
        st.warning(
            "尚無品管通過的就診可供趨勢分析。"
            "請勾選上方核取方塊以查看全部資料，或於『新增就診』重新拍攝。"
        )
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("分數雷達圖")
            st.caption(
                "外緣為 10 分（最佳）。**越靠外 = 該指標膚況越好；圖形越完整代表整體狀態越佳**。"
                "5 軸方向已統一翻成『高=好』，與分數卡片一致。"
            )
            st.plotly_chart(radar_chart(chart_visits, scores_by_visit), width="stretch")
        with col2:
            st.subheader("分數趨勢")
            st.caption("時間序列追蹤每項指標的變化（膚況指數，高 = 好）。")
            st.plotly_chart(line_chart(chart_visits, scores_by_visit), width="stretch")

    st.subheader("各回診詳細分數")
    st.caption(
        "此表使用統一的**膚況指數（高=好）**，與卡片、雷達圖方向一致。"
        "含品質未通過的就診（以 ❌ 標示）；趨勢圖則依上方核取方塊過濾。"
    )
    rows: list[dict[str, Any]] = []
    for v in visits:
        row = {"就診日期": v.visit_date, "品管": "✅" if v.quality_passed else "❌"}
        scores = scores_by_visit[v.id]
        health_scores = [to_health_score(m, scores[m]) for m in METRICS]
        for m, h in zip(METRICS, health_scores, strict=False):
            row[METRIC_LABELS_ZH[m]] = h
        # 整體膚況：5 指標平均後查色帶 emoji
        overall = round(sum(health_scores) / len(health_scores), 2)
        row["狀態"] = f"{health_band(overall)[0]} {overall:.1f}"
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _format_delta_html(curr_health: float, prev_health: float) -> str:
    delta = round(curr_health - prev_health, 1)
    if delta > 0.1:
        return (
            f'<span style="color:{COLOR_GOOD}; font-weight:600;">↑ +{delta:.1f}</span> 較上次改善'
        )
    if delta < -0.1:
        return f'<span style="color:{COLOR_POOR}; font-weight:600;">↓ {delta:.1f}</span> 較上次退步'
    return f'<span style="color:{COLOR_NEUTRAL};">→ 持平</span>'


def _render_health_card(
    metric_zh: str,
    raw_score: float,
    metric_key: str,
    prev_raw: float | None = None,
) -> str:
    """Render one metric as a colored health card (HTML string).

    Uses semi-transparent borders + transparent background so the card stays
    readable under both Streamlit light and dark themes. Only the saturated
    health-band color is theme-fixed.
    """
    health = to_health_score(metric_key, raw_score)
    emoji, band_label, color = health_band(health)
    bar_pct = max(2, int(round(health * 10)))

    delta_html = ""
    if prev_raw is not None:
        prev_health = to_health_score(metric_key, prev_raw)
        delta_html = (
            f'<div style="font-size:12px; margin-top:8px;">'
            f"{_format_delta_html(health, prev_health)}</div>"
        )

    return (
        f'<div style="border:1px solid rgba(128,128,128,0.25); border-radius:10px;'
        f' padding:14px; height:100%;">'
        f'<div style="font-size:13px; opacity:0.7; margin-bottom:4px;">{metric_zh}</div>'
        f'<div style="font-size:32px; font-weight:700; color:{color}; line-height:1.1;">'
        f'{health:.1f}<span style="font-size:13px; opacity:0.5; font-weight:400;"> / 10</span>'
        f"</div>"
        f'<div style="font-size:13px; margin-top:6px;">{emoji} {band_label}</div>'
        f'<div style="height:6px; background:rgba(128,128,128,0.15); border-radius:3px;'
        f' margin-top:10px; overflow:hidden;">'
        f'<div style="width:{bar_pct}%; height:100%; background:{color}; border-radius:3px;">'
        f"</div></div>"
        f"{delta_html}"
        f"</div>"
    )


def _render_quality_report(report: QualityReport) -> None:
    """Side-by-side visualization of the six quality checks (two rows of 3)."""
    checks = [
        ("姿勢", report.pose, "yaw_deg"),
        ("曝光（臉部）", report.exposure, "mean_brightness"),
        ("清晰度", report.sharpness, "laplacian_variance"),
        ("光照均勻", report.lighting, "asymmetry_ratio"),
        ("皮膚可見度", report.skin, "min_skin_ratio"),
        ("色彩校正", report.color, "marker_detected"),
    ]
    for row_start in (0, 3):
        cols = st.columns(3)
        for col, (name, check, key) in zip(cols, checks[row_start : row_start + 3], strict=False):
            with col:
                icon = "✅" if check.passed else "❌"
                st.metric(label=f"{icon} {name}", value=str(check.measurement.get(key, "—")))
    if report.failure_reasons_zh:
        st.error("**未通過原因**：\n\n" + "\n\n".join(f"- {r}" for r in report.failure_reasons_zh))
    else:
        st.success(report.summary_zh)


def _decode_b64_jpeg(b64: str) -> np.ndarray | None:
    """Decode a base64 JPEG (no data URL prefix) into a BGR np.ndarray."""
    try:
        raw = base64.b64decode(b64)
    except (ValueError, TypeError):
        return None
    arr = np.frombuffer(raw, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


INTAKE_LOCK_KEY = "intake_locked_patient_id"
INTAKE_DRAFT_KEYS = (INTAKE_LOCK_KEY, "suggestion_draft", "clinician_notes")


def _clear_intake_draft() -> None:
    for key in INTAKE_DRAFT_KEYS:
        st.session_state.pop(key, None)


def page_intake(patient: Patient) -> None:
    st.header(f"📸 新增就診｜{patient.name}")
    st.caption(
        "即時相機會用 MediaPipe Face Mesh 引導拍攝。"
        "**正臉是必須的**，左右側臉是選擇性（拍了會作為紀錄、但不參與計分）。"
        "正臉拍完後可直接按『✓ 完成』送出；若鏡頭無法使用，可改用『上傳照片』fallback。"
    )

    # Race-condition guard: if a previous patient still has an in-flight draft
    # in session_state, refuse to silently overwrite their photo against the
    # newly-selected patient. Force the user to either commit or discard.
    locked_id = st.session_state.get(INTAKE_LOCK_KEY)
    if locked_id is not None and locked_id != patient.id:
        locked = get_patient(locked_id)
        locked_name = locked.name if locked is not None else f"id={locked_id}"
        st.warning(
            f"⚠️ 偵測到未完成的草稿：上一張捕捉的照片屬於 **{locked_name}**，"
            f"目前已切換到 **{patient.name}**。請先決定如何處理草稿，避免照片存到錯誤病患。"
        )
        col_abort, col_continue = st.columns(2)
        if col_abort.button(
            f"🗑️ 放棄 {locked_name} 的草稿，改拍 {patient.name}",
            width="stretch",
        ):
            _clear_intake_draft()
            st.rerun()
        if col_continue.button(f"↩️ 切回 {locked_name} 繼續完成", type="primary", width="stretch"):
            st.session_state["force_select_patient_id"] = locked_id
            st.rerun()
        return

    front_image_bgr: np.ndarray | None = None
    left_image_bgr: np.ndarray | None = None
    right_image_bgr: np.ndarray | None = None
    capture_meta: dict[str, Any] = {}

    source_tabs = st.tabs(["📷 即時拍照（MediaPipe Face Mesh）", "📁 上傳照片（fallback）"])

    with source_tabs[0]:
        st.markdown(
            "**操作流程**：對著鏡頭 → 系統偵測到正臉、鎖定後倒數 3 秒自動拍照 → 按下「✓ 完成」送回。"
            "拍完正臉後若想多留一張側臉膚質紀錄，可繼續轉頭；不想拍直接按「完成」即可。"
        )
        ghosts = get_ghost_photos(patient.id)
        capture_value = face_capture(
            key=f"face_capture_{patient.id}",
            stability_frames=LIVE_CAPTURE_STABILITY_FRAMES,
            countdown_ms=LIVE_CAPTURE_COUNTDOWN_MS,
            profile_yaw_min_deg=PROFILE_YAW_MIN_DEG,
            profile_pitch_tol_deg=PROFILE_PITCH_TOLERANCE_DEG,
            front_yaw_tol_deg=POSE_TOLERANCE_DEG,
            front_pitch_tol_deg=POSE_TOLERANCE_DEG + 2.0,
            min_face_width_ratio=LIVE_CAPTURE_MIN_FACE_WIDTH_RATIO,
            max_face_width_ratio=LIVE_CAPTURE_MAX_FACE_WIDTH_RATIO,
            ghost_front=ghosts["front"],
            ghost_left=ghosts["left"],
            ghost_right=ghosts["right"],
        )
        if capture_value:
            front_image_bgr = _decode_b64_jpeg(capture_value["front"]["jpeg_b64"])
            if capture_value.get("left"):
                left_image_bgr = _decode_b64_jpeg(capture_value["left"]["jpeg_b64"])
            if capture_value.get("right"):
                right_image_bgr = _decode_b64_jpeg(capture_value["right"]["jpeg_b64"])
            capture_meta = {
                role: {k: v for k, v in payload.items() if k != "jpeg_b64"}
                for role, payload in capture_value.items()
                if isinstance(payload, dict)
            }
            with st.expander("瀏覽器端 pose 量測（給 reviewer 看）", expanded=False):
                st.json(capture_meta, expanded=False)

    with source_tabs[1]:
        uploaded_file = st.file_uploader(
            "選擇正臉照片（JPG / PNG）— 不會自動帶側臉",
            type=["jpg", "jpeg", "png"],
            key=f"uploader_{patient.id}",
        )
        if uploaded_file is not None:
            file_bytes = np.frombuffer(uploaded_file.getvalue(), dtype=np.uint8)
            decoded = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            if decoded is None:
                st.error("無法解讀此圖檔。")
            else:
                front_image_bgr = decoded

    if front_image_bgr is None:
        st.info(
            "尚未取得正臉照片。建議拍攝條件：正面、均勻光線、距離 30–50 公分、無濾鏡。"
            "若上方鏡頭無法啟動，請點選『上傳照片（fallback）』分頁。"
        )
        return

    # We have a front photo for this patient — claim the draft lock so any
    # subsequent sidebar swap will trip the guard at the top of this function.
    st.session_state[INTAKE_LOCK_KEY] = patient.id

    pipeline = _pipeline()
    pipeline_result = pipeline.process(front_image_bgr)
    gate = _gate()
    report, calibrated = gate.evaluate(front_image_bgr, pipeline_result, pose_mode="frontal")

    if report.color.passed:
        # The gray-card white balance was applied. Re-run the pipeline on the
        # calibrated pixels so the ROIs we score are the SAME pixels as the
        # photo we persist — otherwise the stored photo re-scores differently
        # from the stored score, and the erythema (a*) metric never actually
        # benefits from the calibration the TDD promises.
        recalibrated_result = pipeline.process(calibrated)
        if recalibrated_result.face_detected:
            pipeline_result = recalibrated_result

    st.subheader("① 影像一致性檢查（正臉）")
    _render_quality_report(report)

    if left_image_bgr is not None or right_image_bgr is not None:
        st.subheader("側臉一致性檢查（不參與計分，僅作為紀錄）")
        side_specs = []
        if left_image_bgr is not None:
            side_specs.append(("左側", "profile_left", left_image_bgr))
        if right_image_bgr is not None:
            side_specs.append(("右側", "profile_right", right_image_bgr))
        side_cols = st.columns(len(side_specs)) if side_specs else []
        side_calibrated_imgs: dict[str, np.ndarray] = {}
        side_reports: dict[str, QualityReport] = {}
        for col, (label, mode, img) in zip(side_cols, side_specs, strict=False):
            side_pipe = pipeline.process(img)
            s_report, s_cal = gate.evaluate(img, side_pipe, pose_mode=mode)
            side_reports[mode] = s_report
            side_calibrated_imgs[mode] = s_cal
            with col:
                st.markdown(f"**{label}**")
                _render_quality_report(s_report)
                st.image(
                    cv2.cvtColor(s_cal, cv2.COLOR_BGR2RGB),
                    width="stretch",
                )
    else:
        side_calibrated_imgs = {}

    if not pipeline_result.face_detected:
        st.error("正臉未偵測到臉部，已中止後續處理。")
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
        width="stretch",
    )

    with st.expander("各 ROI 局部影像（CLAHE 平衡後）", expanded=False):
        roi_cols = st.columns(4)
        for col, region in zip(roi_cols, Region, strict=False):
            roi = pipeline_result.rois.get(region)
            if roi is not None:
                col.image(
                    cv2.cvtColor(roi, cv2.COLOR_BGR2RGB),
                    caption=region_label_zh(region),
                    width="stretch",
                )

    if not report.overall_passed:
        st.warning("此照片未通過一致性檢查，可繼續評分，但不會用於縱向追蹤基準。")
        proceed = st.checkbox("我仍要繼續評分（僅供參考）", value=False)
        if not proceed:
            return

    st.subheader("③ 量化分數")
    region_scores = score_visit(pipeline_result.rois, pipeline_result.roi_masks)
    agg = aggregate_face_scores(region_scores)

    # Pull the previous visit's scores so the cards can show delta arrows.
    # Reused by the ④ AI explainer block below — single query, not duplicated.
    prev_visits = list_visits(patient.id)
    scores_prev = visit_score_dict(prev_visits[-1].id) if prev_visits else None

    if scores_prev is not None:
        st.caption(
            f"與上次（{prev_visits[-1].visit_date}）比較。卡片下方顯示變化方向；"
            "**分數越高 = 膚況越好**（0~10，10 為最佳）。"
        )
    else:
        st.caption("首次就診，無變化比較。**分數越高 = 膚況越好**（0~10，10 為最佳）。")

    score_cols = st.columns(5)
    for col, m in zip(score_cols, METRICS, strict=False):
        prev_raw = scores_prev.get(m) if scores_prev else None
        with col:
            st.markdown(
                _render_health_card(METRIC_LABELS_ZH[m], agg[m], m, prev_raw),
                unsafe_allow_html=True,
            )

    st.subheader("④ AI 解釋與治療建議草稿")
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
        ts = f"{datetime.utcnow():%Y%m%d_%H%M%S}"
        front_path = PHOTOS_DIR / f"patient{patient.id}_{ts}_front.jpg"
        cv2.imwrite(str(front_path), calibrated)
        photo_root = PHOTOS_DIR.parent.parent

        side_paths: dict[str, str | None] = {"profile_left": None, "profile_right": None}
        for mode, img in side_calibrated_imgs.items():
            suffix = "left" if mode == "profile_left" else "right"
            side_file = PHOTOS_DIR / f"patient{patient.id}_{ts}_{suffix}.jpg"
            cv2.imwrite(str(side_file), img)
            side_paths[mode] = str(side_file.relative_to(photo_root))

        with get_session() as session:
            visit = Visit(
                patient_id=patient.id,
                visit_date=date.today(),
                photo_path=str(front_path.relative_to(photo_root)),
                photo_left_path=side_paths["profile_left"],
                photo_right_path=side_paths["profile_right"],
                quality_passed=report.overall_passed,
                quality_report_json=json.dumps(report.to_dict(), ensure_ascii=False, default=str),
                scoring_version=SCORING_VERSION,
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
            saved_visit_id = visit.id
        side_count = sum(1 for p in side_paths.values() if p)
        _clear_intake_draft()
        st.success(
            f"已儲存就診紀錄（visit_id={saved_visit_id}，含 {side_count} 張側臉）。"
            "請切換到『縱向追蹤』檢視更新後的趨勢圖。"
        )


def region_label_zh(region: Region) -> str:
    return REGION_LABELS_ZH.get(region, region.value)


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
                photo_specs = [
                    ("正臉", v.photo_path),
                    ("左側", getattr(v, "photo_left_path", None)),
                    ("右側", getattr(v, "photo_right_path", None)),
                ]
                shown = 0
                for label, path_str in photo_specs:
                    if not path_str:
                        continue
                    p = Path(path_str)
                    if p.exists():
                        st.image(str(p), caption=label, width="stretch")
                        shown += 1
                if shown == 0:
                    st.caption("（此筆為 seed 資料，無實際照片）")
            with cols[1]:
                try:
                    report_data = json.loads(v.quality_report_json)
                    st.json(report_data, expanded=False)
                except json.JSONDecodeError:
                    st.caption("品管報告不可讀。")

            if v.photo_path:
                front_p = Path(v.photo_path)
                if front_p.exists():
                    mtime = front_p.stat().st_mtime
                    show_overlay = st.checkbox(
                        "🔬 顯示 ROI 訊號疊圖",
                        value=False,
                        key=f"hist_overlay_show_{v.id}",
                        help="對齊後正臉 + 熱力圖：直接看分數的中間訊號分布（紅=強，藍=弱）。",
                    )
                    if show_overlay:
                        overlay_cols = st.columns([3, 1])
                        with overlay_cols[1]:
                            sel_metric = st.selectbox(
                                "熱力圖指標",
                                options=["none", *METRICS],
                                index=1,  # default = pigmentation（皮秒雷射主指標）
                                format_func=lambda k: (
                                    "（無）" if k == "none" else METRIC_LABELS_ZH[k]
                                ),
                                key=f"hist_metric_{v.id}",
                            )
                            show_roi_box = st.checkbox(
                                "顯示 ROI 區域",
                                value=True,
                                key=f"hist_roi_{v.id}",
                            )
                        overlay = _history_overlay_rgb(
                            v.photo_path,
                            mtime,
                            None if sel_metric == "none" else sel_metric,
                            show_roi_box,
                        )
                        if overlay is None:
                            overlay_cols[0].caption("此照片無法偵測人臉，已跳過疊圖。")
                        else:
                            caption = (
                                "對齊後（熱力圖：" + METRIC_LABELS_ZH[sel_metric] + "）"
                                if sel_metric != "none"
                                else "對齊後"
                            )
                            overlay_cols[0].image(overlay, caption=caption, width="stretch")

                    show_rois = st.checkbox(
                        "🧪 顯示各 ROI 局部影像（CLAHE 平衡後）",
                        value=False,
                        key=f"hist_clahe_show_{v.id}",
                        help="四個解剖區域的局部裁切，已做 CLAHE 對比度平衡；可比較同一區域跨次就診的變化。",
                    )
                    if show_rois:
                        rois_rgb = _history_rois_rgb(v.photo_path, mtime)
                        if not rois_rgb:
                            st.caption("此照片無法偵測人臉或無 ROI 可顯示。")
                        else:
                            roi_cols = st.columns(4)
                            for col, region in zip(roi_cols, Region, strict=False):
                                roi = rois_rgb.get(region.value)
                                if roi is not None:
                                    col.image(
                                        roi,
                                        caption=region_label_zh(region),
                                        width="stretch",
                                    )

            scores = scores_for_visit(v.id)
            if scores:
                st.caption("膚況指數（高=好），與卡片、雷達圖方向一致。")
                rows = []
                for s in scores.values():
                    region_health = [to_health_score(m, getattr(s, m)) for m in METRICS]
                    row = {
                        "區域": region_label_zh(s.region),
                        **{
                            METRIC_LABELS_ZH[m]: h
                            for m, h in zip(METRICS, region_health, strict=False)
                        },
                    }
                    avg = round(sum(region_health) / len(region_health), 2)
                    row["狀態"] = f"{health_band(avg)[0]} {avg:.1f}"
                    rows.append(row)
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
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
        GEMINI_API_KEY,
        GEMINI_MODEL,
        LLM_BACKEND,
        LLM_MODEL,
        POSE_TOLERANCE_DEG,
        SHARPNESS_MIN_LAPLACIAN_VAR,
    )

    active_backend = _explainer().__class__.__name__

    st.subheader("環境")
    st.code(
        f"DB_PATH            = {DB_PATH}\n"
        f"LLM_BACKEND        = {LLM_BACKEND or '(auto — 依 API key 自動選擇)'}\n"
        f"使用中 explainer   = {active_backend}\n"
        f"\n"
        f"ANTHROPIC_API_KEY  = {'(已設定)' if ANTHROPIC_API_KEY else '(未設定)'}\n"
        f"LLM_MODEL          = {LLM_MODEL}\n"
        f"\n"
        f"GEMINI_API_KEY     = {'(已設定)' if GEMINI_API_KEY else '(未設定)'}\n"
        f"GEMINI_MODEL       = {GEMINI_MODEL}",
        language="text",
    )
    st.caption(
        "在專案根目錄建立 `.env` 檔即可設定 API key（不要 commit）。"
        "兩個都設時預設用 Anthropic；若想強制使用 Gemini，加上 `LLM_BACKEND=gemini`。"
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

PAGE_DISPATCH = {
    "overview": page_overview,
    "intake": page_intake,
    "history": page_history,
    "treatment": page_treatment,
}

if page == "patients":
    page_patients()
elif page == "settings":
    page_settings()
elif page in PATIENT_REQUIRED_PAGES:
    if selected_patient is None:
        st.info("請先在「👥 病患管理」新增或選擇一位病患。")
        if st.button("前往病患管理"):
            st.session_state["active_page"] = "patients"
            st.rerun()
    else:
        PAGE_DISPATCH[page](selected_patient)
else:
    st.error(f"未知頁面：{page}")

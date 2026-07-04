"""Drive the running Streamlit app with Playwright and screenshot the real pages.

Captures EricZou's actual results straight out of the live app:
    - 縱向追蹤 (overview): real radar + line charts
    - 就診歷史 (history): visit timeline + ROI heatmap overlay on the real face
    - 治療計畫 (treatment): the editable AI draft
    - 病患管理 (patients): the patient table

Prereq: streamlit already running on :8502 (see launch in the session).
Usage:  uv run python scripts/capture_app.py
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://localhost:8502/"
OUT = Path(__file__).resolve().parents[1] / "docs" / "assets"
OUT.mkdir(parents=True, exist_ok=True)


def settle(page, ms: int = 3500) -> None:
    """Wait for a Streamlit rerun to finish."""
    with contextlib.suppress(Exception):
        page.wait_for_load_state("networkidle", timeout=8000)
    page.wait_for_timeout(ms)


def click_text(page, text: str) -> bool:
    """Click the first visible element containing `text`."""
    loc = page.get_by_text(text, exact=False).first
    try:
        loc.scroll_into_view_if_needed(timeout=4000)
        loc.click(timeout=4000)
        return True
    except Exception as e:
        print(f"   ! could not click '{text}': {e!r}")
        return False


def select_patient(page, name: str) -> None:
    print(f" select patient: {name}")
    box = page.locator('[data-testid="stSelectbox"]').first
    box.click()
    page.wait_for_timeout(800)
    opt = page.get_by_role("option").filter(has_text=name).first
    opt.click()
    settle(page)


def shot(page, name: str, full: bool = True) -> None:
    path = OUT / name
    page.screenshot(path=str(path), full_page=full)
    print(f"   wrote {path.name}")


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1460, "height": 1000}, device_scale_factor=2)
        print("goto", URL)
        page.goto(URL, wait_until="domcontentloaded")
        settle(page, 5000)  # first boot loads mediapipe etc.

        # 1. patients (default landing)
        click_text(page, "👥 病患管理")
        settle(page)
        shot(page, "app_patients.png")

        # pick EricZou for the patient-scoped pages
        select_patient(page, "EricZou")

        # 2. overview — radar + line (the hero longitudinal screen)
        click_text(page, "📈 縱向追蹤")
        settle(page)
        try:
            page.wait_for_selector('[data-testid="stPlotlyChart"]', timeout=8000)
        except Exception:
            print("   ! plotly chart not detected")
        settle(page, 2500)
        shot(page, "app_overview.png")

        # 3. history — timeline, then turn on the ROI heatmap overlay
        click_text(page, "📋 就診歷史")
        settle(page)
        shot(page, "app_history.png")
        if click_text(page, "顯示 ROI 訊號疊圖"):
            settle(page, 5000)  # re-runs MediaPipe alignment + heatmap compose
            shot(page, "app_history_overlay.png")

        # 4. treatment — editable AI draft
        click_text(page, "💉 治療計畫")
        settle(page)
        shot(page, "app_treatment.png")

        browser.close()
    print("\nDone.")


if __name__ == "__main__":
    main()

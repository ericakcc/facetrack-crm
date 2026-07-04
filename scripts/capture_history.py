"""Capture the history page with a visit expanded + ROI heatmap overlay ON.

The visit rows are collapsed expanders; the ROI-overlay checkbox lives inside.
So: select EricZou -> history -> expand latest visit -> tick the overlay ->
wait for MediaPipe re-run -> screenshot the real face in its system state.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://localhost:8502/"
OUT = Path(__file__).resolve().parents[1] / "docs" / "assets"


def settle(page, ms: int = 3500) -> None:
    with contextlib.suppress(Exception):
        page.wait_for_load_state("networkidle", timeout=8000)
    page.wait_for_timeout(ms)


def click_text(page, text: str) -> bool:
    loc = page.get_by_text(text, exact=False).first
    try:
        loc.scroll_into_view_if_needed(timeout=4000)
        loc.click(timeout=4000)
        return True
    except Exception as e:
        print(f"   ! click '{text}': {e!r}")
        return False


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1460, "height": 1200}, device_scale_factor=2)
        page.goto(URL, wait_until="domcontentloaded")
        settle(page, 5000)

        # select EricZou
        page.locator('[data-testid="stSelectbox"]').first.click()
        page.wait_for_timeout(800)
        page.get_by_role("option").filter(has_text="EricZou").first.click()
        settle(page)

        # history
        click_text(page, "📋 就診歷史")
        settle(page)

        # expand the latest visit row
        click_text(page, "2026-05-18")
        settle(page, 2500)
        page.screenshot(path=str(OUT / "app_history_expanded.png"), full_page=True)
        print("   wrote app_history_expanded.png")

        # tick the ROI overlay checkbox (the <p> isn't the click target)
        cb = page.locator('[data-testid="stCheckbox"]').filter(has_text="ROI 訊號疊圖").first
        try:
            cb.click(timeout=5000)
            print("   ticked ROI overlay")
        except Exception as e:
            print(f"   ! overlay checkbox: {e!r}")
        settle(page, 6000)  # MediaPipe alignment + heatmap compose
        page.screenshot(path=str(OUT / "app_history_overlay.png"), full_page=True)
        print("   wrote app_history_overlay.png")

        # also tick the per-ROI CLAHE thumbnails toggle if present
        cb2 = page.locator('[data-testid="stCheckbox"]').filter(has_text="各 ROI 局部影像").first
        try:
            cb2.click(timeout=4000)
            settle(page, 5000)
            page.screenshot(path=str(OUT / "app_history_rois.png"), full_page=True)
            print("   wrote app_history_rois.png")
        except Exception as e:
            print(f"   ! roi thumbs: {e!r}")

        browser.close()
    print("Done.")


if __name__ == "__main__":
    main()

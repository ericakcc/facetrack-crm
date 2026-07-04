"""Capture a real Photo-Consistency Gate rejection from the live app.

Select EricZou -> 新增就診 -> 上傳照片 fallback tab -> upload a known-bad photo
(test_face_1.jpg, underexposed) -> screenshot the gate's actual rejection card.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://localhost:8502/"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets"
BAD = ROOT / "data" / "test_images" / "test_face_1.jpg"


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

        page.locator('[data-testid="stSelectbox"]').first.click()
        page.wait_for_timeout(800)
        page.get_by_role("option").filter(has_text="EricZou").first.click()
        settle(page)

        click_text(page, "📸 新增就診")
        settle(page, 4000)

        # switch to the upload fallback tab via the tab role
        switched = False
        for name in ("上傳照片", "fallback", "上傳"):
            try:
                page.get_by_role("tab", name=name).first.click(timeout=3000)
                switched = True
                print(f"   switched to tab '{name}'")
                break
            except Exception:
                continue
        if not switched:
            click_text(page, "上傳照片")
        settle(page, 2500)

        # upload the bad photo into the Streamlit file uploader specifically
        try:
            inp = page.locator('[data-testid="stFileUploader"] input[type="file"]').first
            inp.set_input_files(str(BAD), timeout=5000)
            print(f"   uploaded {BAD.name}")
        except Exception as e:
            print(f"   ! scoped upload failed ({e!r}); trying any file input")
            try:
                page.locator('input[type="file"]').last.set_input_files(str(BAD))
                print("   uploaded via fallback input")
            except Exception as e2:
                print(f"   ! upload failed: {e2!r}")

        settle(page, 7000)  # pipeline + gate run
        # scroll to the gate report region if present
        click_text(page, "未通過") or click_text(page, "品質")
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / "app_intake_gate.png"), full_page=True)
        print("   wrote app_intake_gate.png")

        browser.close()
    print("Done.")


if __name__ == "__main__":
    main()

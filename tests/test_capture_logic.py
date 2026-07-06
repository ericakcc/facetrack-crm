"""Unit tests for the pure JS capture-decision logic (via Playwright)."""
from __future__ import annotations

from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

LOGIC_JS = (
    Path(__file__).resolve().parents[1]
    / "src/facetrack/components/face_capture/frontend/capture_logic.js"
)


@pytest.fixture(scope="module")
def page():
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.set_content("<!doctype html><html><body></body></html>")
        pg.add_script_tag(path=str(LOGIC_JS))
        yield pg
        browser.close()


def test_smoother_first_update_is_identity(page):
    out = page.evaluate(
        "() => CaptureLogic.makePoseSmoother(0.5).update({yaw:10,pitch:0,roll:0})"
    )
    assert out["yaw"] == 10


def test_smoother_ema_dampens_jump(page):
    out = page.evaluate(
        "() => { const s=CaptureLogic.makePoseSmoother(0.5);"
        "s.update({yaw:0,pitch:0,roll:0});"
        "return s.update({yaw:10,pitch:0,roll:0}); }"
    )
    assert out["yaw"] == 5


def test_stability_rises_and_locks(page):
    locked = page.evaluate(
        "() => { let st={count:0,locked:false};"
        "for (let i=0;i<3;i++) st=CaptureLogic.stabilityStep(st,true,3);"
        "return st.locked; }"
    )
    assert locked is True


def test_stability_falls_symmetrically(page):
    count = page.evaluate(
        "() => CaptureLogic.stabilityStep({count:2,locked:false},false,5).count"
    )
    assert count == 1


def test_stability_stays_locked_once_locked(page):
    locked = page.evaluate(
        "() => CaptureLogic.stabilityStep({count:0,locked:true},false,3).locked"
    )
    assert locked is True


def test_pick_sharpest_prefers_in_tolerance(page):
    picked = page.evaluate(
        "() => CaptureLogic.pickSharpestFrame(["
        "{id:'a',score:99,inTolerance:false},"
        "{id:'b',score:10,inTolerance:true},"
        "{id:'c',score:20,inTolerance:true}])"
    )
    assert picked["id"] == "c"


def test_pick_sharpest_falls_back_when_none_in_tolerance(page):
    picked = page.evaluate(
        "() => CaptureLogic.pickSharpestFrame(["
        "{id:'a',score:99,inTolerance:false},"
        "{id:'b',score:100,inTolerance:false}])"
    )
    assert picked["id"] == "b"


def test_laplacian_flat_image_is_zero(page):
    var = page.evaluate(
        "() => CaptureLogic.laplacianVariance(new Uint8Array(9).fill(128),3,3)"
    )
    assert var == 0

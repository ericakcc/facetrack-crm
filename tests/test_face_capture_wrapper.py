"""The face_capture wrapper forwards ghost data URLs to the component."""

from __future__ import annotations

import facetrack.components.face_capture as fc


def test_ghost_args_forwarded(monkeypatch):
    captured = {}

    def fake_component(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(fc, "_component_func", fake_component)
    fc.face_capture(
        key="k",
        ghost_front="data:image/jpeg;base64,AAA",
        ghost_left=None,
        ghost_right="data:image/jpeg;base64,CCC",
    )
    assert captured["ghostFront"] == "data:image/jpeg;base64,AAA"
    assert captured["ghostLeft"] is None
    assert captured["ghostRight"] == "data:image/jpeg;base64,CCC"


def test_ghost_args_default_none(monkeypatch):
    captured = {}
    monkeypatch.setattr(fc, "_component_func", lambda **kw: captured.update(kw))
    fc.face_capture(key="k")
    assert captured["ghostFront"] is None
    assert captured["ghostLeft"] is None
    assert captured["ghostRight"] is None

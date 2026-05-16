"""Smoke test: verify app.py imports cleanly and the bootstrap path works."""

from __future__ import annotations

import importlib
import sys


def test_app_imports_and_module_objects_exist() -> None:
    """Importing app.py runs the bootstrap; ensure no exceptions and the page funcs exist."""
    if "app" in sys.modules:
        del sys.modules["app"]
    module = importlib.import_module("app")

    for fn_name in ("page_overview", "page_intake", "page_history", "page_treatment", "page_settings"):
        assert hasattr(module, fn_name), f"app.{fn_name} missing"

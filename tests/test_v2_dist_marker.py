"""Verify official dashboard markers are preserved after Vite build."""
from pathlib import Path

import pytest


DIST_INDEX = (
    Path(__file__).resolve().parents[1]
    / "webui"
    / "static"
    / "v2"
    / "dist"
    / "index.html"
)
OFFICIAL_SHELL_MARKER = "kronos-dashboard-shell"
LEGACY_PUBLIC_MARKERS = (
    "kronos-v2-version",
    "p1-ssr",
    "p1-5-spa",
)


def _dist_body() -> str:
    return DIST_INDEX.read_text(encoding="utf-8")


@pytest.mark.skipif(not DIST_INDEX.exists(), reason="dist has not been built yet")
def test_official_dist_marker_preserved_after_build():
    body = _dist_body()

    assert OFFICIAL_SHELL_MARKER in body
    for marker in LEGACY_PUBLIC_MARKERS:
        assert marker not in body


@pytest.mark.skipif(not DIST_INDEX.exists(), reason="dist has not been built yet")
def test_dist_base_url_matches_flask_static():
    body = _dist_body()

    assert "/static/v2/dist/assets/" in body


@pytest.mark.skipif(not DIST_INDEX.exists(), reason="dist has not been built yet")
def test_dist_fallback_first_paint_present():
    body = _dist_body()

    assert 'id="hero-strip"' in body
    assert 'data-tab="live-training"' in body


@pytest.mark.skipif(not DIST_INDEX.exists(), reason="dist has not been built yet")
def test_dist_public_copy_has_no_versioned_dashboard_label():
    body = _dist_body()

    assert "Kronos v2" not in body
    assert "P1" not in body
    assert "P1.5" not in body

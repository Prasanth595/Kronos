"""Verify official dashboard canonical routes and legacy redirects."""
from urllib.parse import urlparse

from webui.app import app


OFFICIAL_SHELL_MARKER = "kronos-dashboard-shell"
LEGACY_PUBLIC_MARKERS = (
    "kronos-v2-version",
    "p1-ssr",
    "p1-5-spa",
)


def _location_path(location: str | None) -> str:
    assert location is not None
    parsed = urlparse(location)
    return parsed.path or "/"


def _assert_official_shell(body: str) -> None:
    assert OFFICIAL_SHELL_MARKER in body
    for marker in LEGACY_PUBLIC_MARKERS:
        assert marker not in body


def test_root_returns_official_dashboard_shell():
    client = app.test_client()

    resp = client.get("/")

    assert resp.status_code == 200
    _assert_official_shell(resp.data.decode("utf-8"))


def test_training_bookmarks_return_official_shell():
    client = app.test_client()

    for path in ("/training", "/dashboard"):
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} broke"
        _assert_official_shell(resp.data.decode("utf-8"))


def test_rl_canonical_route_returns_official_shell():
    client = app.test_client()

    resp = client.get("/rl")

    assert resp.status_code == 200
    _assert_official_shell(resp.data.decode("utf-8"))


def test_daily_ohlcv_route_returns_official_shell():
    client = app.test_client()

    for path in ("/daily-ohlcv", "/daily", "/daily-rl-guide", "/daily-ohlcv/rl-guide"):
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} broke"
        _assert_official_shell(resp.data.decode("utf-8"))


def test_legacy_v2_routes_redirect_to_canonical_routes():
    client = app.test_client()

    main_routes = ("/v2", "/v2/")
    for path in main_routes:
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 301, f"{path} should redirect"
        assert _location_path(resp.headers.get("Location")) == "/"

    rl_routes = ("/rl-lab", "/v2/rl-trading", "/v2/rl-lab")
    for path in rl_routes:
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 301, f"{path} should redirect"
        assert _location_path(resp.headers.get("Location")) == "/rl"


def test_unknown_v2_subpath_redirects_to_root_without_catchall():
    client = app.test_client()

    resp = client.get("/v2/unknown", follow_redirects=False)

    assert resp.status_code == 301
    assert _location_path(resp.headers.get("Location")) == "/"

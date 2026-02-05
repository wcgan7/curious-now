from __future__ import annotations

from curious_now.api.app import app


def _has_route(method: str, path: str) -> bool:
    for r in app.router.routes:
        if getattr(r, "path", None) != path:
            continue
        methods: set[str] = set(getattr(r, "methods", set()))
        if method.upper() in methods:
            return True
    return False


def test_stage2_routes_registered() -> None:
    assert _has_route("GET", "/v1/feed")
    assert _has_route("GET", "/v1/clusters/{id}")
    assert _has_route("GET", "/v1/topics")
    assert _has_route("GET", "/v1/topics/{id}")
    assert _has_route("GET", "/v1/search")

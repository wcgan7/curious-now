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


def test_stage1_routes_registered() -> None:
    assert _has_route("GET", "/healthz")
    assert _has_route("GET", "/v1/items/feed")
    assert _has_route("GET", "/v1/sources")
    assert _has_route("POST", "/v1/admin/source_pack/import")
    assert _has_route("PATCH", "/v1/admin/sources/{id}")
    assert _has_route("PATCH", "/v1/admin/feeds/{id}")
    assert _has_route("POST", "/v1/admin/ingestion/run")

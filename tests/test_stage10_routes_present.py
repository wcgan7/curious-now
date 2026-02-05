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


def test_stage10_routes_registered() -> None:
    assert _has_route("GET", "/v1/entities")
    assert _has_route("GET", "/v1/entities/{id}")

    assert _has_route("GET", "/v1/user/follows/entities")
    assert _has_route("POST", "/v1/user/follows/entities/{entity_id}")
    assert _has_route("DELETE", "/v1/user/follows/entities/{entity_id}")

    assert _has_route("POST", "/v1/admin/entities")
    assert _has_route("PATCH", "/v1/admin/entities/{id}")
    assert _has_route("POST", "/v1/admin/entities/{id}/merge")
    assert _has_route("PUT", "/v1/admin/clusters/{id}/entities")

    assert _has_route("POST", "/v1/admin/experiments")
    assert _has_route("PATCH", "/v1/admin/experiments/{id}")
    assert _has_route("PUT", "/v1/admin/feature_flags/{key}")


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


def test_stage8_routes_registered() -> None:
    assert _has_route("POST", "/v1/feedback")

    assert _has_route("GET", "/v1/admin/feedback")
    assert _has_route("PATCH", "/v1/admin/feedback/{id}")

    assert _has_route("POST", "/v1/admin/clusters/{id}/merge")
    assert _has_route("POST", "/v1/admin/clusters/{id}/split")
    assert _has_route("POST", "/v1/admin/clusters/{id}/quarantine")
    assert _has_route("POST", "/v1/admin/clusters/{id}/unquarantine")
    assert _has_route("PATCH", "/v1/admin/clusters/{id}")
    assert _has_route("PUT", "/v1/admin/clusters/{id}/topics")

    assert _has_route("POST", "/v1/admin/topics")
    assert _has_route("PATCH", "/v1/admin/topics/{id}")
    assert _has_route("POST", "/v1/admin/topics/{id}/merge")

    assert _has_route("POST", "/v1/admin/lineage/nodes")
    assert _has_route("POST", "/v1/admin/lineage/edges")


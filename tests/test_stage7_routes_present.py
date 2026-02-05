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


def test_stage7_routes_registered() -> None:
    # PWA manifest
    assert _has_route("GET", "/v1/manifest.json")

    # Offline support
    assert _has_route("GET", "/v1/offline/clusters")
    assert _has_route("POST", "/v1/offline/sync")

    # Semantic search
    assert _has_route("POST", "/v1/search/semantic")

    # Cache management
    assert _has_route("GET", "/v1/cache/stats")
    assert _has_route("DELETE", "/v1/cache/invalidate")

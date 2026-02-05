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


def test_stage9_routes_registered() -> None:
    # Health check
    assert _has_route("GET", "/v1/health/detailed")

    # Rate limit management
    assert _has_route("GET", "/v1/admin/rate-limits")
    assert _has_route("DELETE", "/v1/admin/rate-limits/{key}")

    # Maintenance mode
    assert _has_route("GET", "/v1/admin/maintenance/status")
    assert _has_route("POST", "/v1/admin/maintenance/enable")
    assert _has_route("POST", "/v1/admin/maintenance/disable")

    # Backup
    assert _has_route("POST", "/v1/admin/backup")

    # Audit log
    assert _has_route("GET", "/v1/admin/audit-log")

    # Enhanced search
    assert _has_route("GET", "/v1/search/enhanced")

    # Metrics
    assert _has_route("GET", "/v1/metrics")

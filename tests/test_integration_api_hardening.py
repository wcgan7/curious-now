from __future__ import annotations

from uuid import uuid4

import pytest


@pytest.mark.integration
def test_livez_and_readyz(client) -> None:  # type: ignore[no-untyped-def]
    livez = client.get("/livez")
    assert livez.status_code == 200, livez.text
    assert livez.json() == {"status": "ok"}

    readyz = client.get("/readyz")
    assert readyz.status_code == 200, readyz.text
    assert readyz.json() == {"status": "ready"}


@pytest.mark.integration
def test_security_headers_are_set(client) -> None:  # type: ignore[no-untyped-def]
    request_id = "req-security-headers"
    resp = client.get("/healthz", headers={"X-Request-ID": request_id})
    assert resp.status_code == 200, resp.text

    assert resp.headers.get("x-request-id") == request_id
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert resp.headers.get("permissions-policy") == "camera=(), microphone=(), geolocation=()"
    assert resp.headers.get("x-permitted-cross-domain-policies") == "none"


@pytest.mark.integration
def test_error_envelope_is_consistent(client) -> None:  # type: ignore[no-untyped-def]
    request_id = "req-error-envelope"
    resp = client.get(f"/v1/topics/{uuid4()}", headers={"X-Request-ID": request_id})
    assert resp.status_code == 404, resp.text

    payload = resp.json()
    assert payload["detail"] == "Not found"
    assert payload["error"]["code"] == "http_error"
    assert payload["error"]["message"] == "Not found"
    assert payload["error"]["request_id"] == request_id

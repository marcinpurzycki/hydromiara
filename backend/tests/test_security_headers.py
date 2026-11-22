"""Security headers on every kind of answer, the body limit, the interface description."""

import pytest

from app.api import limits
from app.api.limits import LimitSettings, Rule
from app.main import app
from tests.analysis_helpers import ANALYSIS, assert_error

EXPECTED = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
    "cross-origin-resource-policy": "same-origin",
    "cache-control": "no-store",
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
}


def assert_headers(response, **changed: str) -> None:
    for name, value in {**EXPECTED, **changed}.items():
        assert response.headers.get(name) == value, (name, response.headers.get(name))
    # No cross-origin access is opened.
    assert not [name for name in response.headers if name.startswith("access-control-")]


@pytest.mark.parametrize(
    ("path", "status_code"),
    [
        ("/api/health", 200),
        ("/api/crops", 200),
        ("/api/reports/demo", 200),
        ("/api/openapi.json", 200),
        ("/api/reports/unknown", 404),
        ("/api/no-such-route", 404),
        ("/outside-the-api", 404),
        ("/api/parcels/at?lon=abc&lat=1", 422),
        ("/api/analyses", 405),
    ],
)
def test_headers_on_success_and_on_errors(client, path, status_code):
    response = client.get(path)
    assert response.status_code == status_code
    assert_headers(response)


def test_headers_on_accepted_and_refused_posts(client):
    assert_headers(client.post("/api/analyses", json=ANALYSIS))
    refused = client.post("/api/analyses", json={**ANALYSIS, "crop_id": "unknown"})
    assert refused.status_code == 422
    assert_headers(refused)


def test_headers_on_429(client):
    app.state.rate_limiter.configure(LimitSettings(rules=(Rule(limits.OTHER, 60.0, 1),)))
    assert client.get("/api/crops").status_code == 200
    refused = client.get("/api/crops")
    assert refused.status_code == 429
    assert_headers(refused)
    assert refused.headers["retry-after"]


def test_cross_origin_request_gets_no_permission(client):
    response = client.get("/api/crops", headers={"Origin": "https://other.example"})
    assert_headers(response)
    preflight = client.options(
        "/api/analyses",
        headers={"Origin": "https://other.example", "Access-Control-Request-Method": "POST"},
    )
    assert preflight.status_code == 405
    assert_headers(preflight)


def test_interface_description_page_still_works(client):
    page = client.get("/api/docs")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "swagger-ui" in page.text and "/api/openapi.json" in page.text
    # The page loads its script from a CDN, so it carries only the framing ban.
    assert_headers(page, **{"content-security-policy": "frame-ancestors 'none'"})
    schema = client.get("/api/openapi.json")
    assert schema.json()["paths"]["/api/analyses"]


def test_body_larger_than_the_limit_is_refused_before_it_is_read(client):
    huge = {**ANALYSIS, "parcel_id": "9" * (limits.MAX_REQUEST_BODY_BYTES + 1)}
    refused = client.post("/api/analyses", json=huge)
    assert_error(refused, 413, "request_too_large")
    assert_headers(refused)
    megabytes = client.put(
        "/api/analyses/abc/crop-history",
        content=b"{" + b" " * 5_000_000 + b"}",
        headers={"Content-Type": "application/json"},
    )
    assert_error(megabytes, 413, "request_too_large")


def test_body_at_the_limit_is_read(client):
    padding = limits.MAX_REQUEST_BODY_BYTES - 2
    response = client.post(
        "/api/analyses",
        content=b"{" + b" " * padding + b"}",
        headers={"Content-Type": "application/json"},
    )
    # Read and refused for what it says, not for its size.
    assert_error(response, 422, "validation_error")


def test_body_without_a_declared_length_is_refused(client):
    def chunks():
        yield b'{"parcel_id": "'
        yield b"9" * 100
        yield b'"}'

    refused = client.post(
        "/api/analyses", content=chunks(), headers={"Content-Type": "application/json"}
    )
    assert_error(refused, 411, "length_required")
    assert_headers(refused)


def test_unreadable_declared_length_is_refused(client):
    refused = client.get("/api/crops", headers={"Content-Length": "-5"})
    assert_error(refused, 400, "invalid_request")


def test_unexpected_error_has_the_uniform_body(reports_db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.api import catalog

    def broken():
        raise RuntimeError("secret detail that must not reach the client")

    monkeypatch.setattr(catalog, "contract_crops", broken)
    with TestClient(app, raise_server_exceptions=False) as quiet:
        response = quiet.get("/api/crops")
    assert_error(response, 500, "internal_error")
    assert "secret detail" not in response.text

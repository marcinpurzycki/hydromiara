"""Hostile and boundary input on the report and analysis routes: the uniform error body."""

from datetime import date, timedelta

import pytest

from app.api import limits
from app.orchestrator import runtime
from tests.analysis_helpers import ANALYSIS, PARCEL_ID, assert_error, start

LONG = "9" * 5000
BAD_REPORT_IDS = [
    "a" * (limits.MAX_REPORT_ID_CHARS + 1),
    LONG,
    "..",
    "%2e%2e",
    "..%2f..%2fetc%2fpasswd",
    "abc%00def",
    "abc%0adef",
    "abc def",
    "abc;drop",
    "<script>",
    "ąę",
]
REPORT_ROUTES = [
    ("GET", "/api/analyses/{}/status"),
    ("PUT", "/api/analyses/{}/crop-history"),
    ("GET", "/api/reports/{}"),
    ("POST", "/api/reports/{}/derive"),
    ("POST", "/api/reports/{}/critical-period"),
    ("GET", "/api/reports/{}/simulation/ranking"),
    ("GET", "/api/reports/{}/simulation/compare?crop_id=winter_wheat"),
]
HISTORY = {"same_every_year": True}


def call(client, method: str, path: str):
    body = None
    if method == "PUT":
        body = HISTORY
    elif path.endswith("/derive"):
        body = {"crop_history": HISTORY}
    return client.request(method, path, json=body)


@pytest.mark.parametrize(("method", "route"), REPORT_ROUTES)
@pytest.mark.parametrize("report_id", BAD_REPORT_IDS)
def test_text_that_cannot_be_a_report_identifier_is_an_unknown_report(
    client, method, route, report_id
):
    response = call(client, method, route.format(report_id))
    # The test client resolves ".." and "%2f" itself, so those reach no route at all.
    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"code", "message"}
    assert body["code"] in {"report_not_found", "not_found"}


@pytest.mark.parametrize(("method", "route"), REPORT_ROUTES)
def test_well_formed_unknown_report_identifier(client, method, route):
    assert_error(call(client, method, route.format("A" * 22)), 404, "report_not_found")


def test_longest_report_identifier_is_looked_up(client):
    longest = "a" * limits.MAX_REPORT_ID_CHARS
    assert_error(client.get(f"/api/reports/{longest}"), 404, "report_not_found")


@pytest.mark.parametrize(
    "changes",
    [
        {"parcel_id": ""},
        {"parcel_id": LONG},
        {"parcel_id": "040704_2.0020." + "9" * 60},
        {"crop_id": ""},
        {"crop_id": "w" * 65},
        {"crop_id": "Winter Wheat"},
        {"crop_id": "winter_wheat\u0000"},
        {"crop_id": "../winter_wheat"},
        {"analysis_date": "2023-02-30"},
        {"analysis_date": "20.06.2023"},
        {"analysis_date": "0000-01-01"},
        {"analysis_date": "99999-01-01"},
        {"analysis_date": 20230620},
        {"analysis_date": None},
        {"parcel_id": ["040704_2.0020.34/2"]},
        {"unexpected": "field"},
        {"report_id": "chosen-by-the-client"},
    ],
)
def test_start_refuses_malformed_requests(client, changes):
    response = client.post("/api/analyses", json={**ANALYSIS, **changes})
    assert_error(response, 422, "validation_error")


@pytest.mark.parametrize(
    "parcel_id",
    [
        "34/2",
        "Krusza Podlotowa 34/2",
        "040704_2.0020.34/2\u0000",
        "040704_2.0020.34/2\n040704_2.0020.1",
        "040704_2.0020.<script>",
        "040704_2.0020.34/2&request=GetParcelByXY",
        "040704_2.0020.34/2?x=1",
        "040704_2.0020.%2e%2e",
        "040704_2.0020.3 4",
    ],
)
def test_start_refuses_text_that_is_not_a_parcel_identifier(client, uldk, parcel_id):
    response = client.post("/api/analyses", json={**ANALYSIS, "parcel_id": parcel_id})
    assert_error(response, 422, "invalid_parcel_id")
    assert uldk.requests == []


def test_start_accepts_identifiers_with_a_sheet_and_with_spaces_around(client):
    start(client, parcel_id=f"  {PARCEL_ID} ")
    # Unknown to the recorded service, but of a valid form: accepted, fails later.
    start(client, parcel_id="060606_2.0014.AR_3.756")


def test_analysis_date_bounds(client):
    today = runtime.local_today()
    tomorrow = (today + timedelta(days=1)).isoformat()
    assert_error(
        client.post("/api/analyses", json={**ANALYSIS, "analysis_date": tomorrow}),
        422, "analysis_date_in_future",
    )  # fmt: skip
    for early in (limits.EARLIEST_ANALYSIS_DATE - timedelta(days=1), date(1, 1, 1)):
        refused = client.post("/api/analyses", json={**ANALYSIS, "analysis_date": early.isoformat()})
        assert_error(refused, 422, "analysis_date_too_early")
        assert "01.01.2000" in refused.json()["message"]
    for accepted in (limits.EARLIEST_ANALYSIS_DATE, today):
        start(client, analysis_date=accepted.isoformat())


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"null",
        b"[]",
        b'"text"',
        b"{",
        b"\xff\xfe",
        b'{"parcel_id": "040704_2.0020.34/2", "crop_id": "winter_wheat"}',
    ],
)
def test_start_refuses_bodies_that_are_not_the_expected_document(client, body):
    response = client.post(
        "/api/analyses", content=body, headers={"Content-Type": "application/json"}
    )
    assert_error(response, 422, "validation_error")

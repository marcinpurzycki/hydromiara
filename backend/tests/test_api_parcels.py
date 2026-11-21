"""Parcel routes on recorded answers of the parcel service."""

import httpx
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import KNOWN_ID

client = TestClient(app)


def assert_error(response, status_code: int, code: str) -> None:
    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"code", "message"}
    assert body["code"] == code


def search(q: str):
    return client.get("/api/parcels/search", params={"q": q})


def test_search_one_match_by_number_and_region_in_both_orders():
    for q in ("Krusza Podlotowa 34/2", "34/2, Krusza Podlotowa"):
        matches = search(q).json()["matches"]
        assert [match["parcel_id"] for match in matches] == [KNOWN_ID]
        assert matches[0]["region"] == "Krusza Podlotowa"
        assert matches[0]["geometry"] is None


def test_search_by_identifier():
    matches = search(KNOWN_ID).json()["matches"]
    assert [match["parcel_id"] for match in matches] == [KNOWN_ID]


def test_search_many_matches_are_all_returned():
    matches = search("Stara Wieś 756").json()["matches"]
    assert len(matches) == 8
    assert len({match["commune"] for match in matches}) == 8


def test_search_without_match():
    response = search("Krusza Podlotowa 99999")
    assert response.status_code == 200
    assert response.json() == {"matches": []}


def test_search_in_wrong_form(uldk):
    assert_error(search("nic"), 422, "invalid_parcel_query")
    assert_error(search("ul. Polna 5, Brzoza"), 422, "invalid_parcel_query")
    assert_error(client.get("/api/parcels/search"), 422, "validation_error")
    assert uldk.requests == []


def test_at_returns_parcel_with_geometry():
    response = client.get("/api/parcels/at", params={"lon": 18.2, "lat": 52.75})
    (match,) = response.json()["matches"]
    assert match["parcel_id"] == KNOWN_ID
    assert match["geometry"]["type"] == "Polygon"
    assert match["geometry"]["coordinates"][0][0] == [18.2024467151364, 52.749196783764]


def test_at_without_parcel_and_outside_poland(uldk):
    inside = client.get("/api/parcels/at", params={"lon": 20.0, "lat": 50.0})
    assert inside.json() == {"matches": []}
    asked = len(uldk.requests)
    assert_error(
        client.get("/api/parcels/at", params={"lon": 13.4, "lat": 52.52}), 422, "point_outside_poland"
    )
    assert_error(client.get("/api/parcels/at", params={"lon": "x", "lat": 52}), 422, "validation_error")
    assert len(uldk.requests) == asked


def test_detail_and_unknown_parcel():
    detail = client.get(f"/api/parcels/{KNOWN_ID}")
    assert detail.status_code == 200
    assert detail.json()["parcel_id"] == KNOWN_ID
    assert detail.json()["geometry"]["type"] == "Polygon"
    assert_error(client.get("/api/parcels/040704_2.0020.99999"), 404, "parcel_not_found")
    assert_error(client.get("/api/parcels/not-an-identifier"), 404, "parcel_not_found")


def test_service_failure_is_reported_as_unavailable(uldk):
    uldk.failure = httpx.ReadTimeout("slow")
    assert_error(search("Krusza Podlotowa 34/2"), 503, "parcel_source_unavailable")
    assert_error(
        client.get("/api/parcels/at", params={"lon": 18.2, "lat": 52.75}),
        503,
        "parcel_source_unavailable",
    )
    assert_error(client.get(f"/api/parcels/{KNOWN_ID}"), 503, "parcel_source_unavailable")

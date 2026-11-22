"""Hostile and boundary input on the lookup, crop history and simulation routes."""

import pytest

from app.contracts.analyses import MAX_HISTORY_YEARS
from tests.analysis_helpers import ANALYSIS, PARCEL_ID, assert_error, start, wait_finished

LONG = "9" * 5000


@pytest.mark.parametrize(
    "query",
    [
        "x" * 121,
        "Stara Wieś\u0000756",
        "Stara Wieś\r\n756",
        "‮Stara Wieś 756",
        "bez numeru",
        "../../etc/passwd",
    ],
)
def test_search_refuses_unusable_text(client, uldk, query):
    response = client.get("/api/parcels/search", params={"q": query})
    assert response.status_code == 422
    assert set(response.json()) == {"code", "message"}
    assert uldk.requests == []


def test_search_requires_its_parameter(client):
    assert_error(client.get("/api/parcels/search"), 422, "validation_error")
    assert_error(client.get("/api/parcels/search", params={"q": ""}), 422, "validation_error")


@pytest.mark.parametrize(
    "params",
    [
        {"lon": "nan", "lat": "52"},
        {"lon": "18", "lat": "inf"},
        {"lon": "1e999", "lat": "52"},
        {"lon": "181", "lat": "52"},
        {"lon": "18", "lat": "-91"},
        {"lon": "18,2", "lat": "52"},
        {"lon": "18"},
        {},
    ],
)
def test_point_outside_any_map_is_refused(client, uldk, params):
    assert_error(client.get("/api/parcels/at", params=params), 422, "validation_error")
    assert uldk.requests == []


def test_point_outside_poland_is_refused_without_asking_the_parcel_service(client, uldk):
    response = client.get("/api/parcels/at", params={"lon": 2.35, "lat": 48.85})
    assert_error(response, 422, "point_outside_poland")
    assert uldk.requests == []


@pytest.mark.parametrize(
    "parcel_id",
    [
        "..",
        "../../etc/passwd",
        "%2e%2e/%2e%2e",
        "040704_2.0020." + "9" * 100,
        LONG,
        "040704_2.0020.34/2%00",
        "040704_2.0020.<b>",
        "040704_2.0020.34/2 OR 1=1",
        "34/2",
    ],
)
def test_parcel_detail_does_not_send_malformed_identifiers_on(client, uldk, parcel_id):
    response = client.get(f"/api/parcels/{parcel_id}")
    assert response.status_code == 404
    assert set(response.json()) == {"code", "message"}
    assert uldk.requests == []


def test_parcel_detail_of_a_known_parcel(client):
    assert client.get(f"/api/parcels/{PARCEL_ID}").json()["parcel_id"] == PARCEL_ID


@pytest.mark.parametrize(
    "history",
    [
        {},
        {"years": {"2019": "winter_wheat"}, "same_every_year": True},
        {"years": {str(1990 + number): "winter_wheat" for number in range(MAX_HISTORY_YEARS + 1)}},
        {"years": {"2019": "w" * 65}},
        {"years": {"2019": ""}},
        {"years": {"2019": 5}},
        {"years": {"1899": "winter_wheat"}},
        {"years": {"2201": "winter_wheat"}},
        {"years": {"9" * 400: "winter_wheat"}},
        {"years": {"two thousand": "winter_wheat"}},
        {"years": {"2019.5": "winter_wheat"}},
        {"years": ["winter_wheat"]},
        {"same_every_year": "perhaps"},
        {"same_every_year": True, "notes": "x"},
    ],
)
def test_crop_history_bounds(client, weather, history):
    weather.hold = True
    report_id = start(client)
    put = client.put(f"/api/analyses/{report_id}/crop-history", json=history)
    assert_error(put, 422, "validation_error")
    weather.hold = False
    wait_finished(client, report_id)
    derived = client.post(f"/api/reports/{report_id}/derive", json={"crop_history": history})
    assert_error(derived, 422, "validation_error")


def test_crop_history_of_the_largest_accepted_size_reaches_the_window_check(client):
    report_id = start(client)
    wait_finished(client, report_id)
    years = {str(1990 + number): "winter_wheat" for number in range(MAX_HISTORY_YEARS)}
    response = client.post(f"/api/reports/{report_id}/derive", json={"crop_history": {"years": years}})
    assert_error(response, 422, "crop_history_year_outside_window")


@pytest.mark.parametrize("crop_id", ["", "w" * 65, "no_such_crop", "../winter_wheat", "a\u0000b"])
def test_compare_refuses_unknown_crop_identifiers(client, crop_id):
    report_id = start(client)
    wait_finished(client, report_id)
    response = client.get(
        f"/api/reports/{report_id}/simulation/compare", params={"crop_id": crop_id}
    )
    assert response.status_code == 422
    assert response.json()["code"] in {"validation_error", "unknown_crop"}


def test_compare_requires_its_parameter(client):
    assert_error(
        client.get("/api/reports/demo/simulation/compare"), 422, "validation_error"
    )


def test_error_message_does_not_repeat_hostile_input(client):
    """The validation message names fields, never the value that was sent."""
    marker = "<img src=x onerror=alert(1)>"
    for response in (
        client.post("/api/analyses", json={**ANALYSIS, "crop_id": marker}),
        client.post("/api/analyses", json={**ANALYSIS, "parcel_id": marker}),
        client.post("/api/analyses", json={**ANALYSIS, marker: 1}),
        client.get("/api/parcels/search", params={"q": marker}),
        client.get(f"/api/reports/{marker}"),
    ):
        assert response.status_code in (404, 422)
        assert "onerror" not in response.text

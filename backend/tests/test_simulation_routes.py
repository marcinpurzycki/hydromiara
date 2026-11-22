"""The simulation routes on the whole path: analysis, stored Report, simulation."""

import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.api import simulation as routes
from app.catalog.crops import list_crops
from app.contracts.report import Report
from app.contracts.simulation import CompareResponse, RankingResponse
from app.engine.limitations import SIMULATION_LIMITATIONS
from app.engine.params import DEFAULT_PARAMS
from app.main import app
from app.orchestrator.sources import get_optional_sources, get_weather_source
from app.sources.parcels import get_parcel_source
from tests.analysis_helpers import assert_error, start, wait_finished
from tests.simulation_helpers import many_crops


def finished(client, **changes: str) -> str:
    report_id = start(client, **changes)
    assert wait_finished(client, report_id)["state"] == "done"
    return report_id


def ranking(client, report_id: str):
    return client.get(f"/api/reports/{report_id}/simulation/ranking")


def compare(client, report_id: str, crop_id: str):
    return client.get(f"/api/reports/{report_id}/simulation/compare", params={"crop_id": crop_id})


def reported(client, report_id: str) -> dict:
    """What the Report says about the current crop, in the shape of the simulation."""
    report = Report.model_validate(client.get(f"/api/reports/{report_id}").json())
    multiyear = report.multiyear_susceptibility
    return {
        "crop_id": report.meta.crop.id,
        "name": report.meta.crop.name,
        "deficit_years": multiyear.deficit_years,
        "total_years": multiyear.total_years,
        "deficit_level": multiyear.deficit_level,
    }


def _no_fetching():
    raise AssertionError("the simulation must not fetch anything")


@pytest.fixture
def many(monkeypatch):
    """A crop list of 22: the two real positions and 20 made-up crops."""
    crops = (*list_crops(), *many_crops(20))
    monkeypatch.setattr(routes, "list_crops", lambda: crops)
    return crops


def test_ranking_with_the_present_crop_list_shows_the_current_crop_only(client, uldk, weather):
    report_id = finished(client)
    before = client.get(f"/api/reports/{report_id}").content
    fetched = (len(uldk.requests), len(weather.requests))
    for dependency in (get_parcel_source, get_weather_source, get_optional_sources):
        app.dependency_overrides[dependency] = _no_fetching

    response = ranking(client, report_id)
    assert response.status_code == 200, response.text
    body = RankingResponse.model_validate(response.json())
    # The current crop has exactly the numbers of the Report.
    assert response.json()["current"] == reported(client, report_id)
    assert body.current.total_years == 10
    # The list has winter wheat and the field without a crop: nothing to rank.
    assert body.top == []
    assert body.limitations[:2] == list(SIMULATION_LIMITATIONS)
    texts = [item.text for item in body.limitations[2:]]
    assert len(texts) == 2
    assert "nie ma teraz innej Uprawy" in texts[0] and "Pole bez uprawy" in texts[1]

    assert ranking(client, report_id).json() == response.json()
    assert (len(uldk.requests), len(weather.requests)) == fetched
    assert client.get(f"/api/reports/{report_id}").content == before


def test_ranking_and_comparison_with_a_full_crop_list(client, uldk, weather, many):
    report_id = finished(client)
    before = client.get(f"/api/reports/{report_id}").content
    fetched = (len(uldk.requests), len(weather.requests))
    current = reported(client, report_id)

    started = time.perf_counter()
    response = ranking(client, report_id)
    elapsed = time.perf_counter() - started
    assert response.status_code == 200, response.text
    # Condition of the simulation: the answer comes within 2 s.
    assert elapsed < 2.0
    body = response.json()
    assert body["current"] == current
    top = body["top"]
    assert len(top) == 3
    assert all(crop["crop_id"] not in ("winter_wheat", "bare_field") for crop in top)
    shares = [crop["deficit_years"] / crop["total_years"] for crop in top]
    assert shares == sorted(shares)
    assert "porównano 20 innych Upraw z listy" in body["limitations"][2]["text"]

    started = time.perf_counter()
    response = compare(client, report_id, top[0]["crop_id"])
    assert time.perf_counter() - started < 2.0
    assert response.status_code == 200, response.text
    answer = CompareResponse.model_validate(response.json())
    assert response.json()["current"] == current
    assert response.json()["other"] == top[0]
    report = Report.model_validate_json(before)
    report_years = {year.year: year for year in report.multiyear_susceptibility.years}
    assert answer.years and {year.year for year in answer.years} <= set(report_years)
    for year in answer.years:
        assert year.current_deficit == report_years[year.year].deficit

    assert (len(uldk.requests), len(weather.requests)) == fetched
    assert client.get(f"/api/reports/{report_id}").content == before


def test_comparison_refuses_crops_that_cannot_be_compared(client):
    report_id = finished(client)
    assert_error(compare(client, report_id, "maize"), 422, "unknown_crop")
    assert_error(compare(client, report_id, "winter_wheat"), 422, "same_crop")
    bare = compare(client, report_id, "bare_field")
    assert_error(bare, 422, "crop_not_comparable")
    assert "Dla Pola bez uprawy nie wyznacza się Stopnia niedoboru" in bare.json()["message"]
    missing = client.get(f"/api/reports/{report_id}/simulation/compare")
    assert_error(missing, 422, "validation_error")


def test_report_of_the_field_without_a_crop_has_no_simulation(client, many):
    report_id = finished(client, crop_id="bare_field")
    for response in (ranking(client, report_id), compare(client, report_id, "winter_wheat")):
        assert_error(response, 409, "simulation_not_available")
        assert "Dla Pola bez uprawy" in response.json()["message"]


def test_unknown_running_failed_and_expired_reports(client, weather, monkeypatch):
    assert_error(ranking(client, "unknown"), 404, "report_not_found")
    assert_error(compare(client, "unknown", "bare_field"), 404, "report_not_found")

    weather.hold = True
    running = start(client)
    assert_error(ranking(client, running), 425, "report_not_ready")
    assert_error(compare(client, running, "bare_field"), 425, "report_not_ready")
    weather.hold = False
    wait_finished(client, running)
    assert ranking(client, running).status_code == 200

    weather.status_code = 500
    failed = start(client)
    assert wait_finished(client, failed)["state"] == "failed"
    assert_error(ranking(client, failed), 404, "weather_unavailable")
    assert_error(compare(client, failed, "bare_field"), 404, "weather_unavailable")

    # After the retention time the Report and its data are gone for readers.
    later = datetime.now(UTC) + timedelta(days=366)
    monkeypatch.setattr(routes, "utc_now", lambda: later)
    assert_error(ranking(client, running), 404, "report_not_found")


def test_report_stored_with_other_parameters_is_not_contradicted(client, many, monkeypatch):
    report_id = finished(client)
    assert ranking(client, report_id).status_code == 200
    # The method changed after the Report was written: its numbers no longer
    # come out of the engine, so the simulation gives no answer at all.
    changed = replace(DEFAULT_PARAMS, deficit_year_min_stress_days=40)
    original = routes.simulate
    monkeypatch.setattr(
        routes, "simulate", lambda data, crop, day, crops: original(data, crop, day, crops, changed)
    )
    for response in (ranking(client, report_id), compare(client, report_id, many[2].id)):
        assert_error(response, 409, "report_outdated")
        assert "Uruchom analizę ponownie" in response.json()["message"]


def test_example_report_keeps_its_placeholder_answers(client, many):
    body = ranking(client, "demo").json()
    assert [crop["crop_id"] for crop in body["top"]] == ["winter_rapeseed", "potato", "maize"]
    assert compare(client, "demo", "maize").status_code == 200
    assert_error(compare(client, "demo", "made_00"), 422, "unknown_crop")


def test_derived_report_is_simulated_like_its_source(client, many):
    # The crop history changes neither the multi-year susceptibility nor the simulation.
    source_id = finished(client)
    history = {"crop_history": {"years": {"2015": "bare_field", "2016": "bare_field"}}}
    derived = client.post(f"/api/reports/{source_id}/derive", json=history)
    assert derived.status_code == 201, derived.text
    derived_id = derived.json()["report_id"]
    answer = ranking(client, derived_id)
    assert answer.status_code == 200, answer.text
    assert answer.json() == ranking(client, source_id).json()
    assert answer.json()["current"] == reported(client, derived_id)

"""The critical-period route and the off-season Report on the whole analysis path."""

from app.contracts.report import Report
from app.engine.season_texts import OFF_SEASON_IRRIGATION
from tests.analysis_helpers import ANALYSIS, assert_error, start, wait_finished


def finished(client, **changes: str) -> str:
    report_id = start(client, **changes)
    assert wait_finished(client, report_id)["state"] == "done"
    return report_id


def report_of(client, report_id: str) -> Report:
    response = client.get(f"/api/reports/{report_id}")
    assert response.status_code == 200, response.text
    return Report.model_validate(response.json())


def go(client, report_id: str):
    return client.post(f"/api/reports/{report_id}/critical-period")


def test_critical_period_starts_an_ordinary_analysis_with_the_new_date(client, uldk, weather):
    original_id = finished(client)  # 20 June 2023, after the middle of the critical period
    before = client.get(f"/api/reports/{original_id}").content
    fetched = (len(uldk.requests), len(weather.requests))

    response = go(client, original_id)
    assert response.status_code == 202, response.text
    body = response.json()
    assert set(body) == {"report_id", "analysis_date"}
    assert body["analysis_date"] == "2023-06-07" and body["report_id"] != original_id
    assert wait_finished(client, body["report_id"])["state"] == "done"
    # The data are fetched again for the new analysis.
    assert (len(uldk.requests), len(weather.requests)) == (fetched[0] + 1, fetched[1] + 1)

    new = report_of(client, body["report_id"])
    assert new.meta.analysis_date.isoformat() == "2023-06-07"
    assert new.meta.changed_from_date.isoformat() == ANALYSIS["analysis_date"]
    assert new.meta.derived_from is None
    assert new.meta.parcel.parcel_id == ANALYSIS["parcel_id"]
    assert new.meta.crop.id == ANALYSIS["crop_id"]
    assert new.current_status.details["state_date"] == "2023-06-07"
    assert new.season.in_season

    # The original Report is untouched, byte for byte.
    assert client.get(f"/api/reports/{original_id}").content == before
    assert report_of(client, original_id).meta.changed_from_date is None


def test_before_the_middle_of_the_period_the_previous_year_is_used(client):
    report_id = finished(client, analysis_date="2023-06-01")
    assert go(client, report_id).json()["analysis_date"] == "2022-06-07"


def test_report_already_on_the_middle_day_gets_a_plain_answer(client):
    first = go(client, finished(client)).json()
    wait_finished(client, first["report_id"])
    response = go(client, first["report_id"])
    assert_error(response, 409, "already_critical_period")
    assert "07.06.2023" in response.json()["message"]
    assert_error(go(client, finished(client, analysis_date="2023-06-07")), 409,
                 "already_critical_period")


def test_field_without_a_crop_has_no_critical_period(client):
    response = go(client, finished(client, crop_id="bare_field"))
    assert_error(response, 409, "no_critical_period")
    assert "Pole bez uprawy nie ma Okresu krytycznego" in response.json()["message"]


def test_unknown_running_and_failed_reports(client, weather):
    assert_error(go(client, "unknown"), 404, "report_not_found")
    weather.hold = True
    running = start(client)
    assert_error(go(client, running), 425, "report_not_ready")
    weather.hold = False
    wait_finished(client, running)
    assert go(client, running).status_code == 202

    weather.status_code = 500
    failed = start(client)
    assert wait_finished(client, failed)["state"] == "failed"
    assert_error(go(client, failed), 404, "weather_unavailable")


def test_example_report_keeps_its_stand_in_answer(client):
    response = go(client, "demo")
    assert response.status_code == 202
    assert response.json()["analysis_date"] == "2023-06-07"
    assert client.get(f"/api/analyses/{response.json()['report_id']}/status").status_code == 200


def test_dormant_date_on_the_whole_path_and_the_way_to_the_critical_period(client):
    report_id = finished(client, analysis_date="2023-11-15")
    report = report_of(client, report_id)
    assert report.season.in_season and "w spoczynku (27.10.2023–15.03.2024)" in report.season.note
    assert report.current_status.label.startswith("Zapas wody w glebie: ")
    assert "Poprzedni Sezon uprawy (25.09.2022–31.07.2023)" in report.current_status.reason
    assert report.current_status.details["state_date"] == "2023-11-15"
    again = report_of(client, finished(client, analysis_date="2023-11-15"))
    # Identifier, creation time and fetch times differ; everything computed is the same.
    varying = {"meta", "sources"}
    assert again.model_dump(exclude=varying) == report.model_dump(exclude=varying)

    body = go(client, report_id).json()
    assert body["analysis_date"] == "2023-06-07"
    wait_finished(client, body["report_id"])
    assert report_of(client, body["report_id"]).meta.changed_from_date.isoformat() == "2023-11-15"


def test_date_outside_the_season_on_the_whole_path(client):
    report = report_of(client, finished(client, analysis_date="2023-08-31"))
    assert not report.season.in_season
    assert report.season.last_season.end.isoformat() == "2023-07-31"
    assert "poza Sezonem uprawy pszenicy ozimej" in report.season.note
    assert "Miniony Sezon uprawy (25.09.2022–31.07.2023)" in report.current_status.reason
    assert report.current_status.details["assessment_subject"] == "soil_water_store"
    assert report.irrigation.applicable is False
    assert report.irrigation.text == (
        f"{OFF_SEASON_IRRIGATION}. Ostatni Sezon uprawy pszenicy ozimej: "
        "25.09.2022–31.07.2023."
    )
    assert "Zapasu wody w glebie" in report.consistency_check.sentence or (
        report.consistency_check.result == "brak danych"
    )

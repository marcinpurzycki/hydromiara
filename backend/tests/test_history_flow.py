"""The crop history on the analysis path: given while running, carried to a new date, stored."""

from datetime import date

from app.api.crop_history import carried_history
from app.contracts.analyses import CropHistory
from app.contracts.report import Report
from app.storage.reports import ReportStore
from tests.analysis_helpers import NOW, REQUEST, assert_error, start, wait_finished
from tests.test_report_store import DONE, SOURCES, finish, report_for

YEARS = {"years": {"2015": "bare_field", "2016": "bare_field"}}


def report_of(client, report_id: str) -> Report:
    response = client.get(f"/api/reports/{report_id}")
    assert response.status_code == 200, response.text
    return Report.model_validate(response.json())


def put(client, report_id: str, body: dict):
    return client.put(f"/api/analyses/{report_id}/crop-history", json=body)


def test_history_given_while_running_enters_the_report(client, weather):
    plain = report_of(client, start_and_finish(client))
    weather.hold = True
    report_id = start(client)
    assert put(client, report_id, {"same_every_year": True}).status_code == 204
    assert put(client, report_id, YEARS).status_code == 204
    weather.hold = False
    assert wait_finished(client, report_id)["state"] == "done"

    report = report_of(client, report_id)
    course = report.historical_course
    assert [year.crop.id for year in course.years][:3] == [
        "winter_wheat", "bare_field", "bare_field",
    ]
    assert "nie oceniono: 2015 (Pole bez uprawy), 2016 (Pole bez uprawy)" in (
        course.comparison_sentence
    )
    assert "w latach 2015, 2016" in report.multiyear_susceptibility.history_assumption
    assert report.meta.derived_from is None
    # Everything the verdicts say is what the analysis without a history says.
    assert plain.historical_course is None
    for part in ("headline", "current_status", "causes", "irrigation", "limitations"):
        assert getattr(report, part) == getattr(plain, part), part
    assert report.multiyear_susceptibility.years == plain.multiyear_susceptibility.years
    assert_error(put(client, report_id, YEARS), 409, "analysis_finished")


def start_and_finish(client, **changes: str) -> str:
    report_id = start(client, **changes)
    assert wait_finished(client, report_id)["state"] == "done"
    return report_id


def test_history_is_checked_against_the_window_of_the_analysis(client, weather):
    weather.hold = True
    report_id = start(client)
    response = put(client, report_id, {"years": {"2013": "bare_field", "2019": "bare_field"}})
    assert_error(response, 422, "crop_history_year_outside_window")
    assert "2014–2023" in response.json()["message"] and "2013" in response.json()["message"]
    assert_error(put(client, report_id, {"years": {"2019": "maize"}}), 422, "unknown_crop")

    bare = start(client, crop_id="bare_field")
    assert_error(put(client, bare, {"same_every_year": True}), 409, "crop_history_not_applicable")
    weather.hold = False
    wait_finished(client, report_id)
    wait_finished(client, bare)
    # Nothing refused was stored: the Report has no course.
    assert report_of(client, report_id).historical_course is None


def test_history_goes_with_the_analysis_of_the_critical_period(client, weather):
    weather.hold = True
    original = start(client, analysis_date="2023-06-01")
    history = {"years": {"2015": "bare_field", "2023": "bare_field"}}
    assert put(client, original, history).status_code == 204
    weather.hold = False
    wait_finished(client, original)

    body = client.post(f"/api/reports/{original}/critical-period").json()
    # Before the middle of the period of 2023 the analysis goes to 2022, whose
    # window is 2013-2022: the year 2023 of the history no longer applies.
    assert body["analysis_date"] == "2022-06-07"
    wait_finished(client, body["report_id"])
    new = report_of(client, body["report_id"])
    by_year = {year.year: year.crop.id for year in new.historical_course.years}
    assert sorted(by_year) == list(range(2013, 2023))
    assert by_year[2015] == "bare_field" and by_year[2022] == "winter_wheat"
    assert new.meta.changed_from_date == date(2023, 6, 1) and new.meta.derived_from is None

    derived = client.post(
        f"/api/reports/{body['report_id']}/derive", json={"crop_history": {"same_every_year": True}}
    ).json()["report_id"]
    # A Report derived from it is still the analysis of the changed date.
    assert report_of(client, derived).meta.changed_from_date == date(2023, 6, 1)


def test_analysis_without_a_history_carries_none(client):
    original = start_and_finish(client)
    body = client.post(f"/api/reports/{original}/critical-period").json()
    wait_finished(client, body["report_id"])
    assert report_of(client, body["report_id"]).historical_course is None


def test_carried_history_keeps_only_the_years_of_the_new_window():
    same = CropHistory(same_every_year=True)
    assert carried_history(None, "winter_wheat", date(2022, 6, 7)) is None
    assert carried_history(same, "winter_wheat", date(2022, 6, 7)) == same
    history = CropHistory(years={2013: "bare_field", 2015: "bare_field", 2023: "bare_field"})
    assert carried_history(history, "winter_wheat", date(2022, 6, 7)).years == {
        2013: "bare_field", 2015: "bare_field",
    }
    assert carried_history(history, "winter_wheat", date(2023, 6, 7)).years == {
        2015: "bare_field", 2023: "bare_field",
    }


def test_store_keeps_a_history_given_at_the_start(tmp_path):
    store = ReportStore(tmp_path / "reports.sqlite3")
    history = CropHistory(years={2019: "bare_field"})
    store.create("r1", REQUEST, SOURCES, NOW, history)
    assert store.get("r1", NOW).crop_history == history
    assert store.begin_finalize("r1") == history


def test_store_writes_a_derived_report_as_a_finished_analysis_of_its_own(tmp_path):
    store = ReportStore(tmp_path / "reports.sqlite3")
    source = finish(store)
    history = CropHistory(same_every_year=True)
    derived = report_for("r2")
    assert store.save_derived(derived, "r1", history, NOW)
    assert store.report_json("r2", NOW) == derived.model_dump_json()
    assert store.report_json("r1", NOW) == source.model_dump_json()
    record = store.get("r2", NOW)
    assert (record.state, record.sources, record.crop_history) == ("done", DONE, history)
    assert (record.created_at, record.finished_at) == (NOW, NOW)
    assert store.inputs("r2", NOW).source_data == store.inputs("r1", NOW).source_data
    assert store.inputs("r2", NOW).source_limitations == store.inputs("r1", NOW).source_limitations
    # No source, a source without a Report, an identifier already taken.
    assert not store.save_derived(report_for("r3"), "unknown", history, NOW)
    store.create("running", REQUEST, SOURCES, NOW)
    assert not store.save_derived(report_for("r3"), "running", history, NOW)
    assert store.get("r3", NOW) is None

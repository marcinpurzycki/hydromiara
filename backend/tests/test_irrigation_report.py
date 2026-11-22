"""The irrigation part inside the Report: every date state, the limitations, the trace."""

from datetime import date

import pytest

from app.catalog.crop_model import CatalogCrop
from app.contracts.report import Report
from app.engine.irrigation import RULE_ID
from app.engine.season_texts import OFF_SEASON_IRRIGATION
from app.orchestrator.report_builder import ReportInputs, build_report
from tests.analysis_helpers import NOW, start, stored_source_data, wait_finished
from tests.engine_helpers import BARE_FIELD, WHEAT, recorded_soil
from tests.season_helpers import SPRING

NO_FORECAST = "Raport nie korzysta z prognozy pogody."


def build(crop: CatalogCrop, day: date, data=None) -> Report:
    inputs = ReportInputs(
        report_id="r1",
        created_at=NOW,
        source_data=stored_source_data() if data is None else data,
        crop=crop,
        analysis_date=day,
    )
    return build_report(inputs)


def with_soil():
    return stored_source_data().model_copy(update={"soil": recorded_soil()})


def trace_of(report: Report):
    return next(entry for entry in report.trace if entry.rule_id == RULE_ID)


@pytest.mark.parametrize(
    ("crop", "day", "justified"),
    [(WHEAT, date(2023, 7, 15), True), (WHEAT, date(2016, 7, 15), False),
     (SPRING, date(2023, 7, 15), True), (SPRING, date(2016, 7, 15), False),
     (WHEAT, date(2023, 6, 20), True)],
)
def test_in_the_season_irrigation_follows_the_current_water_status(crop, day, justified):
    report = build(crop, day)
    assert Report.model_validate_json(report.model_dump_json()) == report
    irrigation, details = report.irrigation, report.current_status.details
    assert irrigation.applicable and irrigation.justified is justified
    assert (report.current_status.deficit_level > 0) is justified
    assert trace_of(report).values["deficit_level"] == report.current_status.deficit_level
    if not justified:
        assert irrigation.amount_mm is irrigation.amount_m3_ha is None
        assert irrigation.reason_if_none.startswith("Nawadnianie nie jest teraz zasadne.")
        return
    low, high = irrigation.amount_mm
    assert 0 < low <= high <= details["total_available_water_mm"]
    assert irrigation.amount_m3_ha == (10 * low, 10 * high)
    assert low == int(low) and high == int(high)
    # The ends follow the balance of the Report: Dr - RAW and Dr, within one rounding step.
    assert abs(high - details["depletion_mm"]) <= 1
    exact_low = details["depletion_mm"] - details["readily_available_water_mm"]
    assert abs(low - exact_low) <= 2
    assert irrigation.reason_if_none is None and irrigation.timing.startswith("Teraz")
    assert f"od {low:g} do {high:g} mm" in irrigation.text


def test_november_winter_wheat_is_dormant_and_the_spring_crop_is_off_season():
    day = date(2023, 11, 15)
    dormant = build(WHEAT, day).irrigation
    assert (dormant.applicable, dormant.justified, dormant.amount_mm) == (True, False, None)
    assert "uprawa jest w spoczynku (27.10.2023–15.03.2024)" in dormant.text
    assert OFF_SEASON_IRRIGATION not in dormant.text
    off = build(SPRING, day).irrigation
    assert (off.applicable, off.justified, off.amount_mm, off.timing) == (False, None, None, None)
    assert off.text == (
        f"{OFF_SEASON_IRRIGATION}. Ostatni Sezon uprawy uprawy jarej testowej: "
        "20.04.2023–10.10.2023."
    )


def test_field_without_a_crop_gets_a_plain_not_applicable():
    irrigation = build(BARE_FIELD, date(2023, 7, 15)).irrigation
    assert (irrigation.applicable, irrigation.justified) == (False, None)
    assert "nie dotyczy" in irrigation.text and "Pola bez uprawy" in irrigation.reason_if_none


def test_stand_in_soil_capacity_is_named_once_as_a_limitation_and_in_the_text():
    day = date(2023, 6, 20)
    stand_in, measured = build(WHEAT, day), build(WHEAT, day, with_soil())
    assert "pojemność wodną gleby przyjęto zastępczo" in stand_in.irrigation.text
    assert "przyjęto zastępczo" not in measured.irrigation.text
    limitations = [limitation.text for limitation in stand_in.limitations]
    assert sum("przyjęto zastępczo" in text for text in limitations) == 1
    assert trace_of(stand_in).values["capacity_source"] == "fallback"
    assert trace_of(measured).values["capacity_source"] == "soil_profile"
    # A larger capacity of the same parcel gives a wider range, still inside it.
    assert measured.irrigation.amount_mm[1] <= (
        measured.current_status.details["total_available_water_mm"]
    )


@pytest.mark.parametrize(
    ("crop", "day"),
    [(WHEAT, date(2023, 6, 20)), (WHEAT, date(2016, 7, 15)), (WHEAT, date(2023, 11, 15)),
     (WHEAT, date(2023, 8, 31)), (SPRING, date(2023, 11, 15)), (BARE_FIELD, date(2023, 7, 15))],
)
def test_the_report_names_the_missing_forecast_once_and_nothing_is_pending(crop, day):
    report = build(crop, day)
    limitations = [limitation.text for limitation in report.limitations]
    assert sum(text.startswith(NO_FORECAST) for text in limitations) == 1
    assert not any("nie wyznacza jeszcze" in text and "nawadnia" in text for text in limitations)
    assert "jeszcze" not in report.irrigation.text
    rule_ids = [entry.rule_id for entry in report.trace]
    assert rule_ids.count(RULE_ID) == 1 and rule_ids[-1] == "consistency_check.result"
    assert trace_of(report).values["season_state"] == (
        report.current_status.details["season_state"]
    )
    # Weather after the analysis date changes nothing.
    data = stored_source_data()
    kept = [record for record in data.weather.days if record.date <= day]
    cut = data.model_copy(update={"weather": data.weather.model_copy(update={"days": kept})})
    assert build(crop, day, cut).model_dump_json() == report.model_dump_json()


def test_without_weather_in_the_season_the_need_is_not_decided():
    data = stored_source_data()
    empty = data.model_copy(update={"weather": data.weather.model_copy(update={"days": []})})
    irrigation = build(WHEAT, date(2023, 6, 20), empty).irrigation
    assert (irrigation.applicable, irrigation.justified, irrigation.amount_mm) == (
        True, None, None
    )
    assert "nie można ocenić" in irrigation.reason_if_none


def test_report_from_the_whole_analysis_path_carries_the_irrigation_part(client):
    report_id = start(client)
    assert wait_finished(client, report_id)["state"] == "done"
    report = Report.model_validate(client.get(f"/api/reports/{report_id}").json())
    irrigation = report.irrigation
    assert irrigation.applicable and irrigation.justified is True
    assert irrigation.amount_m3_ha == (10 * irrigation.amount_mm[0], 10 * irrigation.amount_mm[1])
    assert irrigation.text.startswith("Jeśli masz możliwość nawadniania")
    assert trace_of(report).result.startswith("zasadne: od ")

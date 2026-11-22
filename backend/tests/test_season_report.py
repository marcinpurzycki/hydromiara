"""The Report outside the crop season, in dormancy and in the season."""

from datetime import date

import pytest

from app.catalog.crop_model import CatalogCrop
from app.contracts.report import Report
from app.engine.season import past_season, season_status
from app.engine.season_texts import OFF_SEASON_IRRIGATION
from app.orchestrator import report_pending as pending
from app.orchestrator.report_builder import ReportInputs, build_report
from app.orchestrator.report_verdicts import NOT_ASSESSED_LABEL
from tests.analysis_helpers import NOW, stored_source_data
from tests.engine_helpers import BARE_FIELD, WHEAT, balance_with_stress, day_range
from tests.season_helpers import SPRING

OUT_OF_SEASON = date(2023, 8, 31)
DORMANT = date(2023, 11, 15)
STORE_NOT_NEEDS = "Stopień niedoboru dotyczy Zapasu wody w glebie, nie potrzeb rośliny"
# Words the project glossary reserves or rejects.
AVOIDED = ("wilgotn", "wegetac", "susz", "ryzyk")


def build(crop: CatalogCrop, day: date, data=None) -> Report:
    inputs = ReportInputs(
        report_id="r1",
        created_at=NOW,
        source_data=stored_source_data() if data is None else data,
        crop=crop,
        analysis_date=day,
    )
    return build_report(inputs)


def own_texts(report: Report) -> str:
    current, irrigation = report.current_status, report.irrigation
    parts = [report.headline, report.season.note or "", current.label, current.reason]
    return " ".join([*parts, irrigation.text, irrigation.reason_if_none or ""])


def without_weather_after(day: date, first: date | None = None):
    data = stored_source_data()
    kept = [d for d in data.weather.days if d.date <= day and (first is None or d.date >= first)]
    return data.model_copy(update={"weather": data.weather.model_copy(update={"days": kept})})


def test_outside_the_season_the_report_describes_the_soil_water_store():
    report = build(WHEAT, OUT_OF_SEASON)
    assert Report.model_validate_json(report.model_dump_json()) == report
    season = report.season
    assert not season.in_season
    assert (season.last_season.start, season.last_season.end) == (
        date(2022, 9, 25), date(2023, 7, 31)
    )
    assert season.note == (
        "Data analizy 31.08.2023 jest poza Sezonem uprawy pszenicy ozimej. Ostatni Sezon "
        "uprawy: 25.09.2022–31.07.2023. Bieżąca sytuacja wodna opisuje miniony sezon "
        f"i odbudowę Zapasu wody w glebie, a jej {STORE_NOT_NEEDS}. {OFF_SEASON_IRRIGATION}."
    )
    current = report.current_status
    assert current.label == "Zapas wody w glebie: w normie" and current.deficit_level == 0
    assert current.reason == (
        "Data analizy 31.08.2023 jest poza Sezonem uprawy pszenicy ozimej, więc "
        f"{STORE_NOT_NEEDS}. Zapas wody w glebie na 31.08.2023: 99 mm z 150 mm, które gleba "
        "może zmagazynować w zasięgu korzeni (66%). Miniony Sezon uprawy "
        "(25.09.2022–31.07.2023): wody brakowało przez 71 dni, w tym 40 dni w Okresie "
        "krytycznym (15.05.2023–30.06.2023). Na koniec tego sezonu w glebie było 45 mm wody "
        "dostępnej dla roślin; od tego czasu Zapas wody w glebie wzrósł o 54 mm przy 85 mm "
        "opadu."
    )
    details = current.details
    assert details["season_state"] == "out_of_season"
    assert details["assessment_subject"] == "soil_water_store"
    assert details["soil_water_store_mm"] == 99 == (
        details["total_available_water_mm"] - details["depletion_mm"]
    )
    assert (details["past_season_start"], details["past_season_end"]) == (
        "2022-09-25", "2023-07-31"
    )
    assert details["past_season_stress_days"] == 71
    assert details["past_season_critical_period_stress_days"] == 40
    assert details["store_change_since_season_end_mm"] == 99 - details["past_season_end_store_mm"]
    assert report.headline.startswith(
        "Data analizy 31.08.2023 jest poza Sezonem uprawy — Zapas wody w glebie: w normie. "
    )


def test_outside_the_season_irrigation_text_is_literal_with_the_season_dates():
    report = build(WHEAT, OUT_OF_SEASON)
    irrigation = report.irrigation
    assert irrigation.applicable is False and irrigation.justified is None
    assert irrigation.amount_mm is irrigation.amount_m3_ha is irrigation.timing is None
    assert irrigation.text == irrigation.reason_if_none == (
        "Rekomendacje nawadniania: brak — wybrana data jest poza sezonem. "
        "Ostatni Sezon uprawy pszenicy ozimej: 25.09.2022–31.07.2023."
    )
    assert OFF_SEASON_IRRIGATION in report.season.note


def test_dormant_winter_crop_is_in_season_and_the_store_is_assessed():
    report = build(WHEAT, DORMANT)
    assert Report.model_validate_json(report.model_dump_json()) == report
    season = report.season
    assert season.in_season and season.last_season.start == date(2023, 9, 25)
    assert season.note == (
        "Data analizy 15.11.2023 wypada w Sezonie uprawy pszenicy ozimej "
        "(25.09.2023–31.07.2024), ale uprawa jest w spoczynku (27.10.2023–15.03.2024). "
        f"Oceniany jest Zapas wody w glebie: {STORE_NOT_NEEDS}."
    )
    current = report.current_status
    assert current.label.startswith("Zapas wody w glebie: ")
    assert "ale uprawa jest w spoczynku (27.10.2023–15.03.2024)" in current.reason
    assert STORE_NOT_NEEDS in current.reason
    assert "Poprzedni Sezon uprawy (25.09.2022–31.07.2023): wody brakowało przez 71 dni" in (
        current.reason
    )
    assert "od tego czasu Zapas wody w glebie wzrósł o" in current.reason
    assert current.details["season_state"] == "dormant"
    assert current.details["assessment_subject"] == "soil_water_store"
    assert report.headline.startswith("W dniu 15.11.2023 uprawa jest w spoczynku — Zapas wody")
    # In the season: irrigation is not closed with the off-season sentence.
    assert report.irrigation.applicable and report.irrigation.justified is False
    assert OFF_SEASON_IRRIGATION not in own_texts(report)


def test_spring_crop_in_november_is_outside_the_season():
    report = build(SPRING, date(2023, 11, 15))
    assert not report.season.in_season
    assert report.season.last_season.end == date(2023, 10, 10)
    assert report.current_status.label.startswith("Zapas wody w glebie: ")
    assert "Miniony Sezon uprawy (20.04.2023–10.10.2023)" in report.current_status.reason
    assert "w Okresie krytycznym (01.07.2023–20.08.2023)" in report.current_status.reason
    assert "20.04.2023–10.10.2023" in report.irrigation.text
    assert report.irrigation.text.startswith(OFF_SEASON_IRRIGATION)


@pytest.mark.parametrize(
    ("crop", "day", "deficit"),
    [(WHEAT, date(2023, 7, 15), True), (WHEAT, date(2016, 7, 15), False),
     (SPRING, date(2023, 7, 15), True), (SPRING, date(2016, 7, 15), False)],
)
def test_in_july_the_level_describes_the_needs_of_the_crop(crop, day, deficit):
    report = build(crop, day)
    current = report.current_status
    assert (current.deficit_level > 0) == deficit
    assert current.label in ("w normie", "lekki niedobór", "wyraźny niedobór", "silny niedobór")
    assert current.reason == pending.REASON_PENDING
    assert current.details["season_state"] == "in_season"
    assert current.details["assessment_subject"] == "crop_water_needs"
    assert "soil_water_store_mm" not in current.details
    assert report.season.in_season and report.season.note is None
    assert report.irrigation.applicable and report.irrigation.justified is deficit
    assert report.headline.startswith(f"Bieżąca sytuacja wodna na {day:%d.%m.%Y}: ")


def test_store_level_uses_the_same_scale_and_a_deficit_is_named_as_of_the_store():
    report = build(WHEAT, date(2013, 8, 5))
    current = report.current_status
    assert (current.deficit_level, current.label) == (2, "Zapas wody w glebie: wyraźny niedobór")
    assert "od tego czasu Zapas wody w glebie zmalał o 1 mm przy 3 mm opadu" in current.reason
    assert current.details["store_change_since_season_end_mm"] == -1


@pytest.mark.parametrize(
    ("crop", "day"),
    [(WHEAT, OUT_OF_SEASON), (WHEAT, DORMANT), (SPRING, date(2023, 11, 15)),
     (WHEAT, date(2013, 8, 5)), (BARE_FIELD, DORMANT)],
)
def test_wording_repeatable_and_free_of_later_data(crop, day):
    report = build(crop, day)
    assert not [word for word in AVOIDED if word in own_texts(report).lower()]
    assert build(crop, day).model_dump_json() == report.model_dump_json()
    # Weather after the analysis date changes nothing.
    assert build(crop, day, without_weather_after(day)).model_dump_json() == (
        report.model_dump_json()
    )
    values = report.trace[3].values
    assert report.trace[3].rule_id == "season.state"
    assert values["season_state"] == report.current_status.details["season_state"]
    assert (values["critical_period_analysis_date"] or "") <= day.isoformat()


def test_past_season_without_weather_is_said_plainly():
    data = without_weather_after(OUT_OF_SEASON, first=date(2023, 8, 10))
    current = build(WHEAT, OUT_OF_SEASON, data).current_status
    assert "Dane pogodowe nie obejmują ostatniego zakończonego Sezonu uprawy" in current.reason
    assert "past_season_start" not in current.details
    partly = build(WHEAT, OUT_OF_SEASON, without_weather_after(OUT_OF_SEASON, date(2023, 7, 1)))
    assert "dane pogodowe obejmują 31 z 310 dni sezonu" in partly.current_status.reason


def test_without_weather_nothing_is_assessed_but_the_season_is_still_described():
    report = build(WHEAT, OUT_OF_SEASON, without_weather_after(date(2000, 1, 1)))
    current = report.current_status
    assert current.label == NOT_ASSESSED_LABEL and current.details["assessed"] is False
    assert current.details["assessment_subject"] is None
    assert "poza Sezonem uprawy" in report.season.note
    assert report.irrigation.text.startswith(OFF_SEASON_IRRIGATION)
    assert NOT_ASSESSED_LABEL in report.headline


def test_field_without_a_crop_gets_no_season_and_no_store_wording():
    report = build(BARE_FIELD, DORMANT)
    assert not report.season.in_season and report.season.last_season is None
    assert report.season.note == "Pole bez uprawy nie ma Sezonu uprawy."
    assert report.current_status.label == "bez uprawy, nie oceniane"
    assert report.current_status.details["season_state"] == "no_crop"
    assert not report.irrigation.applicable and report.irrigation.justified is None
    assert report.trace[3].values["critical_period_analysis_date"] is None


def test_past_season_numbers_counted_by_hand():
    # Stress on 10 days of the critical period and 5 days of August (after the season).
    stressed = day_range(date(2023, 6, 1), 10) | day_range(date(2023, 8, 1), 5)
    balance = balance_with_stress(date(2022, 9, 1), date(2023, 8, 20), stressed)
    past = past_season(balance, WHEAT, season_status(WHEAT, date(2023, 8, 20)))
    assert (past.season.start, past.season.end) == (date(2022, 9, 25), date(2023, 7, 31))
    assert past.days_in_balance == past.season.days == 310
    assert (past.stress_days, past.critical_period_stress_days) == (10, 10)
    assert (past.end_depletion_mm, past.depletion_mm, past.store_change_mm) == (10.0, 10.0, 0.0)
    assert past.precipitation_since_mm == 20.0 and past.state_date == date(2023, 8, 20)
    # In the season the finished one is the season before; nothing of it is in the series.
    assert past_season(balance, WHEAT, season_status(WHEAT, date(2023, 6, 20))) is None
    assert past_season(balance, BARE_FIELD, season_status(BARE_FIELD, date(2023, 8, 20))) is None

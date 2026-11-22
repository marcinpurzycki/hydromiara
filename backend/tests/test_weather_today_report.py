"""Limitations and confidence for an analysis of the current day and of a past one."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from app.contracts.report import Report
from app.contracts.source_data import SourceData
from app.engine.limitations import PERMANENT_LIMITATIONS
from app.main import app
from app.orchestrator.sources import get_weather_source
from app.sources.weather import WeatherSource
from tests.analysis_helpers import ANALYSIS_DATE, start, wait_finished
from tests.engine_helpers import recorded_weather
from tests.limitation_helpers import complete_source_data, judge

# Moments of the weather fetch, in UTC; Poland is two hours ahead in June.
ON_THE_DAY = datetime(2023, 6, 20, 8, 0, tzinfo=UTC)
LATE_ON_THE_DAY = datetime(2023, 6, 20, 21, 30, tzinfo=UTC)
AFTER_MIDNIGHT = datetime(2023, 6, 20, 22, 30, tzinfo=UTC)
YEARS_LATER = datetime(2026, 11, 22, 10, 0, tzinfo=UTC)
ENDS_YESTERDAY = (
    "Dane pogodowe kończą się wczoraj (19.06.2023). Dzisiejszy dzień nie jest "
    "uwzględniony, bo jeszcze trwa."
)


def data_with(days_missing: int, fetched_at: datetime | None) -> SourceData:
    """Complete source data whose weather ends `days_missing` before the analysis date."""
    last = ANALYSIS_DATE - timedelta(days=days_missing)
    data = complete_source_data([day for day in recorded_weather() if day.date <= last])
    outcomes = [
        outcome.model_copy(update={"fetched_at": fetched_at})
        if outcome.topic == "weather"
        else outcome
        for outcome in data.outcomes
        if outcome.topic != "weather" or fetched_at is not None
    ]
    return data.model_copy(update={"outcomes": outcomes})


@dataclass(frozen=True)
class Case:
    days_missing: int
    fetched_at: datetime | None
    current: str
    # None: no sentence about the end of the series; True: the informative one.
    informative: bool | None
    gap_text: str | None = None


CASES = {
    "today, series ends yesterday": Case(1, ON_THE_DAY, "wysoka", True),
    "today late in the evening": Case(1, LATE_ON_THE_DAY, "wysoka", True),
    "today, two days missing": Case(2, ON_THE_DAY, "średnia", False, "2 dni przed Datą analizy"),
    "today, a week missing": Case(7, ON_THE_DAY, "średnia", False, "7 dni przed Datą analizy"),
    "fetched after midnight, whole day there": Case(0, AFTER_MIDNIGHT, "wysoka", None),
    "fetched after midnight, the day missing": Case(
        1, AFTER_MIDNIGHT, "średnia", False, "1 dzień przed Datą analizy"
    ),
    "past date, complete": Case(0, YEARS_LATER, "wysoka", None),
    "past date, one day missing": Case(
        1, YEARS_LATER, "średnia", False, "1 dzień przed Datą analizy"
    ),
    "past date, three days missing": Case(
        3, YEARS_LATER, "średnia", False, "3 dni przed Datą analizy"
    ),
    "no record of the fetch, one day missing": Case(
        1, None, "średnia", False, "1 dzień przed Datą analizy"
    ),
}


@pytest.mark.parametrize("name", CASES)
def test_end_of_the_series_and_the_confidence(name):
    case = CASES[name]
    findings, confidences, _ = judge(data_with(case.days_missing, case.fetched_at))
    about_end = [f for f in findings if f.limitation.text.startswith("Dane pogodowe kończą się")]
    assert confidences.current.level == case.current
    # The multi-year verdict never depends on the last days.
    assert confidences.multiyear.level == "wysoka"
    if case.informative is None:
        assert about_end == []
        return
    (finding,) = about_end
    assert finding.limitation.affects == "current"
    assert finding.limitation.permanent is case.informative
    assert finding.concerns("current") is not case.informative
    if case.informative:
        assert finding.limitation.text == ENDS_YESTERDAY
        assert "kończą się" not in confidences.current.why
    else:
        assert case.gap_text in finding.limitation.text


def test_informative_sentence_stands_before_the_permanent_limitations():
    findings, _, _ = judge(data_with(1, ON_THE_DAY))
    texts = [finding.limitation.text for finding in findings]
    permanent = [item.text for item in PERMANENT_LIMITATIONS]
    assert texts[-len(permanent):] == permanent
    assert texts[-len(permanent) - 1] == ENDS_YESTERDAY


def test_later_weather_does_not_change_the_assessment_of_today():
    """Days after the last fetched one, were they in the data, change nothing."""
    until_yesterday = [d for d in recorded_weather() if d.date < ANALYSIS_DATE]
    fetched = data_with(1, ON_THE_DAY).outcomes
    cut = complete_source_data(until_yesterday).model_copy(update={"outcomes": fetched})
    whole = complete_source_data().model_copy(update={"outcomes": fetched})
    _, _, from_cut = judge(cut, analysis_date=ANALYSIS_DATE - timedelta(days=1))
    _, _, from_whole = judge(whole, analysis_date=ANALYSIS_DATE - timedelta(days=1))
    assert from_cut.current_status == from_whole.current_status
    assert from_cut.multiyear_susceptibility == from_whole.multiyear_susceptibility


def finished_report(client) -> Report:
    report_id = start(client)
    assert wait_finished(client, report_id)["state"] == "done"
    return Report.model_validate(client.get(f"/api/reports/{report_id}").json())


def test_whole_analysis_of_today_against_the_same_date_analysed_later(client, weather):
    past = finished_report(client)
    app.dependency_overrides[get_weather_source] = lambda: WeatherSource(
        transport=weather, clock=lambda: ON_THE_DAY
    )
    today = finished_report(client)

    assert weather.requests[-2].url.params["end_date"] == "2023-06-20"
    assert weather.requests[-1].url.params["end_date"] == "2023-06-19"
    assert today.current_status.details["state_date"] == "2023-06-19"
    assert "na 19.06.2023" in today.headline and "20.06.2023" not in today.headline
    assert "na 20.06.2023" in past.headline

    today_texts = [item.text for item in today.limitations]
    past_texts = [item.text for item in past.limitations]
    assert [text for text in today_texts if text not in past_texts] == [ENDS_YESTERDAY]
    assert [text for text in past_texts if text not in today_texts] == []
    for verdict in ("current_status", "multiyear_susceptibility"):
        assert getattr(today, verdict).confidence == getattr(past, verdict).confidence
    weather_source = next(source for source in today.sources if source.topic == "weather")
    assert weather_source.data_date.endswith("/2023-06-19")
    assert weather_source.fetched_at == ON_THE_DAY

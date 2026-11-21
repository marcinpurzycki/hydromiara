"""Current water status: levels at the thresholds and the numbers behind them."""

from datetime import date

import pytest

from app.contracts.common import Confidence
from app.contracts.verdicts import CurrentStatus
from app.engine.balance import run_balance
from app.engine.params import EngineParams
from app.engine.verdicts import current_level, current_status, level_label
from tests.engine_helpers import (
    BARE_FIELD,
    SIMPLE_BARE_ZONE,
    SIMPLE_ZONE,
    WHEAT,
    weather_day,
    weather_from,
)

AUG_1 = date(2021, 8, 1)


def status_after(values, share=0.0, analysis_date=date(2021, 8, 31), **changes):
    params = EngineParams(bare_soil_kc=1.0, initial_depletion_share=share, **changes)
    balance = run_balance(weather_from(AUG_1, values), WHEAT, SIMPLE_ZONE, analysis_date, params)
    return current_status(balance, params)


@pytest.mark.parametrize(
    ("ks", "level"),
    [
        (1.0, 0),
        (0.9999, 1),
        (0.75, 1),
        (0.7499, 2),
        (0.4, 2),
        (0.3999, 3),
        (0.0, 3),
    ],
)
def test_level_thresholds_are_inclusive(ks, level):
    assert current_level(ks) == level


def test_level_thresholds_come_from_parameters():
    params = EngineParams(current_level_min_ks=(0.9, 0.6, 0.2))
    assert [current_level(ks, params) for ks in (0.95, 0.9, 0.6, 0.2, 0.1)] == [0, 0, 1, 2, 3]


def test_labels_use_the_agreed_words():
    assert [level_label(level) for level in range(4)] == [
        "w normie",
        "lekki niedobór",
        "wyraźny niedobór",
        "silny niedobór",
    ]


@pytest.mark.parametrize(
    ("share", "ks", "level", "label"),
    [
        (0.5, 1.0, 0, "w normie"),
        (0.625, 0.75, 1, "lekki niedobór"),
        (0.8, 0.4, 2, "wyraźny niedobór"),
        (0.9, 0.2, 3, "silny niedobór"),
    ],
)
def test_level_follows_the_state_of_the_last_day(share, ks, level, label):
    # TAW 100, RAW 50, a day without rain and ET0 keeps the initial depletion.
    verdict = status_after([(0.0, 0.0)], share)
    assert verdict.stress_coefficient == pytest.approx(ks)
    assert (verdict.deficit_level, verdict.label) == (level, label)
    assert verdict.assessed and verdict.not_assessed_reason is None
    assert verdict.depletion_mm == pytest.approx(100 * share)
    assert verdict.depletion_share == pytest.approx(share)
    assert verdict.total_available_water_mm == 100.0
    assert verdict.readily_available_water_mm == 50.0


def test_stress_run_counts_only_the_last_unbroken_days():
    # Starts at 60 mm (stress). 1-2 Aug stress, rain on 3 Aug ends it, 4-6 Aug stress again.
    values = [(0.0, 2.0), (0.0, 2.0), (30.0, 0.0), (0.0, 30.0), (0.0, 1.0), (0.0, 1.0)]
    verdict = status_after(values, 0.6)
    assert verdict.stress_run_days == 3
    assert verdict.state_date == date(2021, 8, 6)


def test_no_stress_run_when_the_last_day_is_not_stressed():
    assert status_after([(0.0, 2.0), (40.0, 0.0)], 0.6).stress_run_days == 0


def test_recent_sums_cover_the_configured_days():
    values = [(1.0, 2.0)] * 10
    verdict = status_after(values, recent_days=4)
    assert verdict.precipitation_recent_mm == pytest.approx(4.0)
    assert verdict.et0_recent_mm == pytest.approx(8.0)
    assert verdict.recent_days_without_weather == 0
    assert set(verdict.details()) >= {"precipitation_4d_mm", "et0_4d_mm"}


def test_recent_days_without_weather_are_counted():
    values = [(1.0, 2.0), (None, 2.0), (1.0, 2.0)]
    verdict = status_after(values, recent_days=5)
    # 3 days in the series, one of them incomplete: 2 of 5 window days are complete.
    assert verdict.recent_days_without_weather == 3
    assert verdict.precipitation_recent_mm == pytest.approx(2.0)


def test_state_refers_to_the_last_day_with_weather():
    verdict = status_after([(0.0, 5.0)], analysis_date=date(2021, 8, 4))
    assert verdict.state_date == date(2021, 8, 1)
    assert verdict.days_behind == 3


def test_no_weather_means_not_assessed():
    verdict = current_status(run_balance([], WHEAT, SIMPLE_ZONE, date(2021, 8, 31)))
    assert not verdict.assessed
    assert verdict.not_assessed_reason == "no_weather"
    assert verdict.deficit_level is None and verdict.label is None
    assert verdict.depletion_mm is None and verdict.depletion_share is None
    assert verdict.details()["depletion_pct"] is None


def test_bare_field_reports_the_store_without_a_level():
    weather = [weather_day(AUG_1, 0.0, 5.0)]
    params = EngineParams(bare_soil_kc=1.0)
    balance = run_balance(weather, BARE_FIELD, SIMPLE_BARE_ZONE, AUG_1, params)
    verdict = current_status(balance, params)
    assert not verdict.assessed
    assert verdict.not_assessed_reason == "no_crop"
    assert verdict.stress_coefficient is None
    assert verdict.readily_available_water_mm is None
    assert verdict.depletion_mm == pytest.approx(5.0)
    assert verdict.stress_run_days == 0


def test_details_fit_the_report_contract():
    verdict = status_after([(2.0, 3.0)] * 5, 0.9)
    details = verdict.details()
    assert set(details) == {
        "depletion_mm",
        "readily_available_water_mm",
        "total_available_water_mm",
        "depletion_pct",
        "stress_coefficient",
        "stress_run_days",
        "precipitation_30d_mm",
        "et0_30d_mm",
    }
    status = CurrentStatus(
        deficit_level=verdict.deficit_level,
        label=verdict.label,
        reason="-",
        confidence=Confidence(level="średnia", why="-"),
        details=details,
    )
    assert status.deficit_level == 3

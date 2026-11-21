"""Daily water balance on cases small enough to compute by hand.

Winter wheat in August is outside its season, so its Kc is the bare-soil
value; the tests set it to 1.0, which makes ETc = Ks * ET0. The root zone has
TAW 100 mm and p 0.5 (RAW 50 mm).
"""

from datetime import date

import pytest

from app.engine.balance import run_balance
from app.engine.params import EngineParams
from tests.engine_helpers import (
    BARE_FIELD,
    SIMPLE_BARE_ZONE,
    SIMPLE_ZONE,
    WHEAT,
    weather_day,
    weather_from,
)

AUG_1 = date(2021, 8, 1)
KC_ONE = EngineParams(bare_soil_kc=1.0)


def starting_at(share: float) -> EngineParams:
    return EngineParams(bare_soil_kc=1.0, initial_depletion_share=share)


def run(values, params=KC_ONE, zone=SIMPLE_ZONE, crop=WHEAT, analysis_date=date(2021, 8, 31)):
    return run_balance(weather_from(AUG_1, values), crop, zone, analysis_date, params)


def test_evapotranspiration_depletes_and_rain_refills():
    days = run([(0.0, 5.0), (0.0, 4.0), (6.0, 1.0)]).days
    assert [day.depletion_mm for day in days] == pytest.approx([5.0, 9.0, 4.0])
    assert [day.etc_mm for day in days] == pytest.approx([5.0, 4.0, 1.0])
    assert all(day.ks == 1.0 and not day.stressed and day.drainage_mm == 0.0 for day in days)


def test_rain_above_field_capacity_drains():
    days = run([(0.0, 5.0), (12.0, 2.0)]).days
    # 5 + 2 - 12 = -5: the store is full and 5 mm is lost.
    assert days[1].depletion_mm == 0.0
    assert days[1].drainage_mm == pytest.approx(5.0)


def test_crop_coefficient_scales_evapotranspiration():
    # 10 June lies in the mid-season of winter wheat: Kc = 1.15.
    balance = run_balance(
        [weather_day(date(2021, 6, 10), 0.0, 4.0)], WHEAT, SIMPLE_ZONE, date(2021, 6, 10)
    )
    assert balance.days[0].kc == pytest.approx(1.15)
    assert balance.days[0].etc_mm == pytest.approx(4.6)
    assert balance.days[0].depletion_mm == pytest.approx(4.6)


def test_stress_reduces_evapotranspiration():
    # Dr 75 mm > RAW 50 mm: Ks = (100 - 75) / (100 - 50) = 0.5.
    day = run([(0.0, 4.0)], starting_at(0.75)).days[0]
    assert day.ks == pytest.approx(0.5)
    assert day.etc_mm == pytest.approx(2.0)
    assert day.depletion_mm == pytest.approx(77.0)
    assert day.stressed


def test_depletion_equal_to_raw_is_not_stress():
    day = run([(0.0, 0.0)], starting_at(0.5)).days[0]
    assert day.depletion_mm == pytest.approx(50.0)
    assert day.ks == 1.0
    assert not day.stressed


def test_first_millimetre_above_raw_is_stress():
    day = run([(0.0, 1.0)], starting_at(0.5)).days[0]
    assert day.depletion_mm == pytest.approx(51.0)
    assert day.stressed


def test_empty_store_stops_evapotranspiration():
    days = run([(0.0, 6.0), (0.0, 6.0)], starting_at(1.0)).days
    assert [day.ks for day in days] == [0.0, 0.0]
    assert [day.depletion_mm for day in days] == pytest.approx([100.0, 100.0])


def test_depletion_never_exceeds_total_available_water():
    # Without a crop there is no stress coefficient, so only the limit stops the loss.
    days = run([(0.0, 5.0)], starting_at(0.99), zone=SIMPLE_BARE_ZONE, crop=BARE_FIELD).days
    assert days[0].ks == 1.0
    assert days[0].depletion_mm == pytest.approx(100.0)
    assert not days[0].stressed


def test_initial_state_is_field_capacity_by_default():
    assert run([(0.0, 0.0)]).days[0].depletion_mm == 0.0


def test_missing_values_leave_the_store_unchanged_and_are_counted():
    values = [(0.0, 5.0), (None, 3.0), (4.0, None), (None, None), (0.0, 1.0)]
    balance = run(values, analysis_date=date(2021, 8, 5))
    assert [day.depletion_mm for day in balance.days] == pytest.approx([5.0, 8.0, 4.0, 4.0, 5.0])
    assert [day.complete for day in balance.days] == [True, False, False, False, True]
    assert balance.incomplete_days == 3
    assert balance.missing_dates == 0


def test_absent_days_carry_the_state_and_are_counted():
    weather = [
        weather_day(date(2021, 8, 1), 0.0, 5.0),
        weather_day(date(2021, 8, 4), 0.0, 2.0),
    ]
    balance = run_balance(weather, WHEAT, SIMPLE_ZONE, date(2021, 8, 6), KC_ONE)
    assert [day.depletion_mm for day in balance.days] == pytest.approx([5.0, 7.0])
    # 2 and 3 August inside the series, 5 and 6 August after its end.
    assert balance.missing_dates == 4
    assert balance.days_behind == 2
    assert balance.last.date == date(2021, 8, 4)


def test_days_after_the_analysis_date_are_dropped():
    balance = run([(0.0, 5.0), (0.0, 5.0), (50.0, 0.0)], analysis_date=date(2021, 8, 2))
    assert [day.date for day in balance.days] == [date(2021, 8, 1), date(2021, 8, 2)]
    assert balance.last.depletion_mm == pytest.approx(10.0)
    assert balance.days_behind == 0


def test_order_of_the_input_does_not_matter():
    weather = weather_from(AUG_1, [(0.0, 5.0), (3.0, 1.0), (0.0, 2.0)])
    ordered = run_balance(weather, WHEAT, SIMPLE_ZONE, date(2021, 8, 31), KC_ONE)
    shuffled = run_balance(weather[::-1], WHEAT, SIMPLE_ZONE, date(2021, 8, 31), KC_ONE)
    assert ordered == shuffled


def test_two_records_for_one_day_are_rejected():
    weather = [weather_day(AUG_1, 0.0, 1.0), weather_day(AUG_1, 2.0, 1.0)]
    with pytest.raises(ValueError):
        run_balance(weather, WHEAT, SIMPLE_ZONE, date(2021, 8, 31))


def test_empty_series_gives_an_empty_balance():
    balance = run_balance([], WHEAT, SIMPLE_ZONE, date(2021, 8, 31))
    assert balance.days == ()
    assert balance.last is None
    assert balance.days_behind is None
    assert balance.missing_dates == 0


def test_between_returns_inclusive_range():
    balance = run([(0.0, 1.0)] * 10)
    picked = balance.between(date(2021, 8, 3), date(2021, 8, 5))
    assert [day.date.day for day in picked] == [3, 4, 5]
    assert balance.between(date(2021, 9, 1), date(2021, 9, 30)) == ()

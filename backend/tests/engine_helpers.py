"""Helpers for the engine tests: hand-made weather, recorded weather, source data."""

import json
from datetime import date, timedelta
from pathlib import Path

from app.catalog.crops import get_crop
from app.contracts.common import GeoJsonGeometry
from app.contracts.source_data import ParcelData, SoilData, SourceData, WeatherData, WeatherDay
from app.engine.balance import DayBalance, WaterBalance
from app.engine.root_zone import RootZone
from app.sources.soil import parse_response as parse_soil

FIXTURES = Path(__file__).parent / "fixtures"

WHEAT = get_crop("winter_wheat")
BARE_FIELD = get_crop("bare_field")

# Round numbers for hand calculation: TAW 100 mm, p 0.5, so RAW 50 mm.
SIMPLE_ZONE = RootZone(depth_cm=100.0, taw_mm=100.0, depletion_fraction=0.5)
SIMPLE_BARE_ZONE = RootZone(depth_cm=100.0, taw_mm=100.0, depletion_fraction=None)


def weather_day(day: date, precipitation: float | None, et0: float | None) -> WeatherDay:
    return WeatherDay(date=day, precipitation_mm=precipitation, et0_mm=et0, temperature_mean_c=None)


def weather_from(start: date, values: list[tuple[float | None, float | None]]) -> list[WeatherDay]:
    """Consecutive days from `start`, one (precipitation, ET0) pair per day."""
    return [
        weather_day(start + timedelta(days=offset), precipitation, et0)
        for offset, (precipitation, et0) in enumerate(values)
    ]


def recorded_weather() -> list[WeatherDay]:
    """Recorded archive answer for the trial parcel, 3.09.2012 - 31.12.2023."""
    path = FIXTURES / "open_meteo" / "archive_2012_2023.json"
    daily = json.loads(path.read_text(encoding="utf-8"))["daily"]
    return [
        WeatherDay(date=day, precipitation_mm=rain, et0_mm=et0, temperature_mean_c=temperature)
        for day, rain, et0, temperature in zip(
            daily["time"],
            daily["precipitation_sum"],
            daily["et0_fao_evapotranspiration"],
            daily["temperature_2m_mean"],
        )
    ]


def recorded_soil() -> SoilData:
    path = FIXTURES / "soilgrids" / "profile_field.json"
    return parse_soil(json.loads(path.read_text(encoding="utf-8")))


def source_data(days: list[WeatherDay], soil: SoilData | None = None) -> SourceData:
    parcel = ParcelData(
        parcel_id="000000_0.0000.1",
        number="1",
        region="Test",
        commune="Test",
        county="Test",
        voivodeship="Test",
        geometry=GeoJsonGeometry(type="Point", coordinates=[18.2, 52.75]),
        area_ha=1.0,
        centroid_lon=18.2,
        centroid_lat=52.75,
    )
    weather = WeatherData(grid_lat=52.75, grid_lon=18.2, days=days)
    return SourceData(parcel=parcel, weather=weather, soil=soil)


def balance_with_stress(
    first: date,
    last: date,
    stressed: set[date],
    analysis_date: date | None = None,
    zone: RootZone = SIMPLE_ZONE,
) -> WaterBalance:
    """A balance series whose stress days are given directly; 1 mm rain, 3 mm ET0 a day."""
    days = []
    day = first
    while day <= last:
        is_stressed = day in stressed
        days.append(
            DayBalance(
                date=day,
                precipitation_mm=1.0,
                et0_mm=3.0,
                kc=1.0,
                ks=1.0,
                etc_mm=3.0,
                drainage_mm=0.0,
                depletion_mm=60.0 if is_stressed else 10.0,
                stressed=is_stressed,
                complete=True,
            )
        )
        day += timedelta(days=1)
    return WaterBalance(
        analysis_date=analysis_date or last,
        root_zone=zone,
        days=tuple(days),
        incomplete_days=0,
        missing_dates=0,
    )


def day_range(first: date, count: int) -> set[date]:
    return {first + timedelta(days=offset) for offset in range(count)}

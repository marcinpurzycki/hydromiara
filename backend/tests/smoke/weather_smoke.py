"""Smoke check against the live weather archive (needs network).

Run from the backend directory:  python -m tests.smoke.weather_smoke
For one point and two analysis dates (a historical one and today) fetches the
full series and prints its range, the grid cell used and any reported gap.
Exits with 1 when a series is missing or a gap is neither absent nor reported.
"""

import asyncio
import sys
from datetime import date

from app.sources.weather import WeatherSource, series_start

LAT, LON = 52.75, 18.25


async def check(source: WeatherSource, analysis_date: date) -> bool:
    data, outcome, limitations = await source.fetch(LAT, LON, analysis_date)
    print(f"analysis date {analysis_date}  {outcome.duration_s:5.2f} s", end="  ")
    if data is None:
        print(f"NO DATA: {outcome.message}")
        return False
    first, last = data.days[0].date, data.days[-1].date
    print(f"{len(data.days)} days {first}..{last}, grid cell {data.grid_lat}, {data.grid_lon}")
    for limitation in limitations:
        print(f"  limitation ({limitation.affects}): {limitation.text}")
    starts_on_time = first == series_start(analysis_date)
    gap_reported = any(limitation.affects == "current" for limitation in limitations)
    return starts_on_time and last <= analysis_date and (last == analysis_date or gap_reported)


async def main() -> int:
    source = WeatherSource()
    results = [await check(source, day) for day in (date(2019, 6, 15), date.today())]
    print("OK" if all(results) else "FAILED")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

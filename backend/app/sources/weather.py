"""Daily weather history from the Open-Meteo archive.

One request returns precipitation, FAO-56 reference evapotranspiration and
mean temperature per day for the grid cell nearest to the point. The series
never reaches past the analysis date. When it ends earlier, or days inside
it have no values, the gap is reported as a report limitation instead of
being filled.
"""

import time
from datetime import UTC, datetime, timedelta
from datetime import date as Date
from typing import NamedTuple

import httpx
from pydantic import ValidationError

from app.contracts.report import Limitation
from app.contracts.source_data import SourceOutcome, WeatherData, WeatherDay
from app.sources import weather_params as params


class WeatherSourceError(Exception):
    """The weather archive did not answer or answered with something unreadable."""


class WeatherFetch(NamedTuple):
    """Weather for one analysis, how it was obtained and what is missing in it."""

    data: WeatherData | None
    outcome: SourceOutcome
    limitations: list[Limitation]


def series_start(analysis_date: Date) -> Date:
    """First day to fetch: start of the multi-year window minus the warm-up."""
    window_start = Date(analysis_date.year - params.MULTIYEAR_WINDOW_YEARS, 1, 1)
    return window_start - timedelta(days=params.BALANCE_WARMUP_DAYS)


def _is_complete(day: WeatherDay) -> bool:
    """A day the water balance can use: both precipitation and ET0 are known."""
    return day.precipitation_mm is not None and day.et0_mm is not None


def parse_response(payload: object, analysis_date: Date) -> WeatherData:
    """Normalised series from one archive answer.

    Days after the analysis date are dropped, and so are trailing days without
    values, so the series ends on the last day that has data.
    """
    try:
        daily = payload["daily"]
        columns = [daily["time"], *(daily[name] for name in params.DAILY_VARIABLES)]
        if len({len(column) for column in columns}) != 1:
            raise WeatherSourceError("daily columns differ in length")
        days = [
            WeatherDay(
                date=day, precipitation_mm=precipitation, et0_mm=et0, temperature_mean_c=temperature
            )
            for day, precipitation, et0, temperature in zip(*columns, strict=True)
        ]
        grid_lat, grid_lon = float(payload["latitude"]), float(payload["longitude"])
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise WeatherSourceError(f"unreadable answer: {type(exc).__name__}") from exc

    days = sorted((day for day in days if day.date <= analysis_date), key=lambda day: day.date)
    while days and not _is_complete(days[-1]):
        days.pop()
    if not days:
        raise WeatherSourceError("no day with data up to the analysis date")
    return WeatherData(grid_lat=grid_lat, grid_lon=grid_lon, days=days)


def _pl(day: Date) -> str:
    return day.strftime("%d.%m.%Y")


def _days_pl(count: int, genitive: bool = False) -> str:
    if count == 1:
        return "1 dnia" if genitive else "1 dzień"
    return f"{count} dni"


def find_limitations(data: WeatherData, start: Date, analysis_date: Date) -> list[Limitation]:
    """Gaps of the series against the requested range, worded for the report."""
    limitations: list[Limitation] = []
    first, last = data.days[0].date, data.days[-1].date

    if last < analysis_date:
        missing = (analysis_date - last).days
        limitations.append(
            Limitation(
                text=(
                    f"Dane pogodowe kończą się {_pl(last)}, czyli {_days_pl(missing)} przed "
                    f"Datą analizy ({_pl(analysis_date)}). Bieżąca sytuacja wodna nie "
                    "uwzględnia opadów i parowania z tego okresu."
                ),
                affects="current",
                permanent=False,
            )
        )

    present = {day.date for day in data.days if _is_complete(day)}
    inner_missing = (last - first).days + 1 - len(present)
    if inner_missing > 0:
        limitations.append(
            Limitation(
                text=(
                    f"W danych pogodowych z okresu {_pl(first)}–{_pl(last)} brakuje "
                    f"opadu lub parowania dla {_days_pl(inner_missing, genitive=True)}."
                ),
                affects="all",
                permanent=False,
            )
        )

    if first > start:
        limitations.append(
            Limitation(
                text=(
                    f"Dane pogodowe zaczynają się {_pl(first)} i nie obejmują całego "
                    "Okna wieloletniego."
                ),
                affects="multiyear",
                permanent=False,
            )
        )
    return limitations


class WeatherSource:
    """Weather history for a point, up to the analysis date."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def history(self, lat: float, lon: float, start: Date, end: Date) -> WeatherData:
        """Daily series for the grid cell nearest to the point, from start to end."""
        query = {
            "latitude": f"{lat:.5f}",
            "longitude": f"{lon:.5f}",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": ",".join(params.DAILY_VARIABLES),
            "timezone": params.TIMEZONE,
        }
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=params.TIMEOUT_S,
                headers={"User-Agent": params.USER_AGENT},
            ) as client:
                response = await client.get(params.ARCHIVE_URL, params=query)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            raise WeatherSourceError(type(exc).__name__) from exc
        except ValueError as exc:
            raise WeatherSourceError("answer is not JSON") from exc
        return parse_response(payload, end)

    async def fetch(self, lat: float, lon: float, analysis_date: Date) -> WeatherFetch:
        """Weather for an analysis: the series, its outcome record and its gaps."""
        started = time.monotonic()
        start = series_start(analysis_date)
        data, message, limitations = None, None, []
        try:
            data = await self.history(lat, lon, start, analysis_date)
            limitations = find_limitations(data, start, analysis_date)
            if limitations:
                message = " ".join(limitation.text for limitation in limitations)
        except WeatherSourceError:
            message = "Archiwum pogodowe nie odpowiedziało lub nie ma danych dla tej daty."
        outcome = SourceOutcome(
            topic="weather",
            source_name=params.SOURCE_NAME if data else None,
            chain_step=1 if data else None,
            ok=data is not None,
            duration_s=round(time.monotonic() - started, 3),
            data_date=(
                f"{data.days[0].date.isoformat()}/{data.days[-1].date.isoformat()}"
                if data
                else None
            ),
            fetched_at=datetime.now(UTC),
            message=message,
        )
        return WeatherFetch(data=data, outcome=outcome, limitations=limitations)

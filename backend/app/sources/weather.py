"""Daily weather history from the Open-Meteo archive.

One request returns precipitation and FAO-56 reference evapotranspiration per
day for the grid cell nearest to the point. The series ends on the analysis
date, or on the day before the current one when the analysis is made for the
current day (see `weather_series`). When it ends earlier, or days inside it
have no values, the gap is reported as a report limitation instead of being
filled.

The current moment comes from a clock given to the adapter; the same reading
decides the last day to fetch and is stored as the time of the fetch.

A request refused for the rate limit (429) is repeated once, after the wait
the archive asks for, and only when that wait fits into the time the analysis
gives this source; otherwise the fetch ends at once with its own message.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from datetime import date as Date
from typing import NamedTuple

import httpx

from app.contracts.report import Limitation
from app.contracts.source_data import SourceOutcome, WeatherData
from app.sources import weather_params as params
from app.sources.weather_series import (
    WeatherSourceError,
    find_limitations,
    parse_response,
    series_end,
    series_start,
)

__all__ = [
    "WeatherFetch",
    "WeatherRateLimited",
    "WeatherSource",
    "WeatherSourceError",
    "find_limitations",
    "parse_response",
    "series_end",
    "series_start",
]

logger = logging.getLogger("hydromiara.sources.weather")


class WeatherRateLimited(WeatherSourceError):
    """The archive refused the request because the free allowance is used up."""

    def __init__(self, retry_after_s: float | None) -> None:
        super().__init__("rate limit reached", params.REASON_RATE_LIMITED)
        self.retry_after_s = retry_after_s


class WeatherFetch(NamedTuple):
    """Weather for one analysis, how it was obtained and what is missing in it."""

    data: WeatherData | None
    outcome: SourceOutcome
    limitations: list[Limitation]


def utc_now() -> datetime:
    return datetime.now(UTC)


def retry_after_s(response: httpx.Response) -> float | None:
    """Seconds the archive asks to wait; None when it does not say."""
    try:
        seconds = float(response.headers.get("Retry-After", ""))
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def log_allowance(response: httpx.Response) -> None:
    """Status and allowance headers of one answer; nothing about the request."""
    seen = " ".join(
        f"{name}={response.headers.get(name, '-')}" for name in params.RATE_LIMIT_HEADERS
    )
    logger.info("weather archive status=%s %s", response.status_code, seen)


class WeatherSource:
    """Weather history for a point, up to the analysis date."""

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        *,
        clock: Callable[[], datetime] = utc_now,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        budget_s: float = params.FETCH_BUDGET_S,
    ) -> None:
        self._transport = transport
        self._clock = clock
        self._sleep = sleep
        self._budget_s = budget_s

    async def _ask(self, client: httpx.AsyncClient, query: dict[str, str]) -> object:
        response = await client.get(params.ARCHIVE_URL, params=query)
        log_allowance(response)
        if response.status_code == params.RATE_LIMITED_STATUS:
            raise WeatherRateLimited(retry_after_s(response))
        response.raise_for_status()
        return response.json()

    async def history(
        self, lat: float, lon: float, start: Date, end: Date, deadline: float | None = None
    ) -> WeatherData:
        """Daily series for the grid cell nearest to the point, from start to end.

        `deadline` (monotonic clock) is when the caller stops waiting; without
        it a refused request is never repeated.
        """
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
                try:
                    payload = await self._ask(client, query)
                except WeatherRateLimited as refusal:
                    wait_s = refusal.retry_after_s
                    left_s = 0.0 if deadline is None else deadline - time.monotonic()
                    if wait_s is None or wait_s + params.RETRY_REQUEST_RESERVE_S > left_s:
                        raise
                    await self._sleep(wait_s)
                    payload = await self._ask(client, query)
        except httpx.HTTPError as exc:
            raise WeatherSourceError(type(exc).__name__) from exc
        except ValueError as exc:
            raise WeatherSourceError("answer is not JSON", params.REASON_UNREADABLE) from exc
        return parse_response(payload, end)

    async def fetch(self, lat: float, lon: float, analysis_date: Date) -> WeatherFetch:
        """Weather for an analysis: the series, its outcome record and its gaps."""
        now = self._clock()
        started = time.monotonic()
        start = series_start(analysis_date)
        end = series_end(analysis_date, now)
        data, message, limitations = None, None, []
        try:
            data = await self.history(lat, lon, start, end, started + self._budget_s)
            limitations = find_limitations(data, start, analysis_date, end)
            if limitations:
                message = " ".join(limitation.text for limitation in limitations)
        except WeatherSourceError as failure:
            logger.info("weather archive gave no series: reason=%s", failure.reason)
            message = params.FAILURE_MESSAGES[failure.reason]
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
            # The clock reading that decided the last day of the series, so that
            # the stored data tell whether the analysis date was the current day.
            fetched_at=now,
            message=message,
        )
        return WeatherFetch(data=data, outcome=outcome, limitations=limitations)

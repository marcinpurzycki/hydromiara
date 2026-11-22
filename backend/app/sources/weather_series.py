"""The weather series of one analysis: its date range, reading it, its gaps.

Pure: the current moment is always given by the caller.

The series never reaches past the analysis date and never contains the current
day. The archive gives the current day as a forecast of the weather model and
counts "today" in UTC, so for an analysis of the current day the series ends on
the day before, counted in the time zone of the analysed country.
"""

from datetime import UTC, datetime, timedelta
from datetime import date as Date
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.contracts.report import Limitation
from app.contracts.source_data import WeatherData, WeatherDay
from app.sources import weather_params as params


class WeatherSourceError(Exception):
    """The weather archive gave no usable answer; `reason` is a code of the cause."""

    def __init__(self, detail: str, reason: str = params.REASON_NO_ANSWER) -> None:
        super().__init__(detail)
        self.reason = reason


def series_start(analysis_date: Date) -> Date:
    """First day to fetch: start of the multi-year window minus the warm-up."""
    window_start = Date(analysis_date.year - params.MULTIYEAR_WINDOW_YEARS, 1, 1)
    return window_start - timedelta(days=params.BALANCE_WARMUP_DAYS)


def local_day(moment: datetime) -> Date:
    """The calendar day of a moment in the time zone of the daily sums."""
    return moment.astimezone(ZoneInfo(params.TIMEZONE)).date()


def series_end(analysis_date: Date, now: datetime) -> Date:
    """Last day to fetch: the analysis date, but never later than yesterday.

    Yesterday is counted in the local time zone. It is never later than the
    current day in UTC, the latest day the archive accepts; the second bound
    states that rule on its own.
    """
    yesterday = local_day(now) - timedelta(days=1)
    return min(analysis_date, yesterday, now.astimezone(UTC).date())


def _is_complete(day: WeatherDay) -> bool:
    """A day the water balance can use: both precipitation and ET0 are known."""
    return day.precipitation_mm is not None and day.et0_mm is not None


def parse_response(payload: object, last_day: Date) -> WeatherData:
    """Normalised series from one archive answer.

    Days after `last_day` are dropped, and so are trailing days without
    values, so the series ends on the last day that has data. The mean
    temperature is not requested, so its field stays empty.
    """
    try:
        daily = payload["daily"]
        columns = [daily["time"], *(daily[name] for name in params.DAILY_VARIABLES)]
        if len({len(column) for column in columns}) != 1:
            raise WeatherSourceError("daily columns differ in length", params.REASON_UNREADABLE)
        days = [
            WeatherDay(date=day, precipitation_mm=rain, et0_mm=et0, temperature_mean_c=None)
            for day, rain, et0 in zip(*columns, strict=True)
        ]
        grid_lat, grid_lon = float(payload["latitude"]), float(payload["longitude"])
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        detail = f"unreadable answer: {type(exc).__name__}"
        raise WeatherSourceError(detail, params.REASON_UNREADABLE) from exc

    days = sorted((day for day in days if day.date <= last_day), key=lambda day: day.date)
    while days and not _is_complete(days[-1]):
        days.pop()
    if not days:
        raise WeatherSourceError("no day with data in the range", params.REASON_UNREADABLE)
    return WeatherData(grid_lat=grid_lat, grid_lon=grid_lon, days=days)


def pl(day: Date) -> str:
    return day.strftime("%d.%m.%Y")


def days_pl(count: int, genitive: bool = False) -> str:
    if count == 1:
        return "1 dnia" if genitive else "1 dzień"
    return f"{count} dni"


def ends_yesterday_text(last: Date) -> str:
    """The sentence for an analysis of the current day: the normal state, not a gap."""
    return (
        f"Dane pogodowe kończą się wczoraj ({pl(last)}). Dzisiejszy dzień nie jest "
        "uwzględniony, bo jeszcze trwa."
    )


def is_normal_end(last: Date, analysis_date: Date, expected_end: Date) -> bool:
    """True when the series ends one day early only because that day still lasted."""
    return last == expected_end and (analysis_date - last).days == 1


def find_limitations(
    data: WeatherData, start: Date, analysis_date: Date, expected_end: Date | None = None
) -> list[Limitation]:
    """Gaps of the series against the requested range, worded for the report.

    `expected_end` is the last day that was requested, when it is earlier than
    the analysis date. A series ending there, one day before the analysis
    date, is described by a sentence that does not lower the confidence.
    """
    limitations: list[Limitation] = []
    first, last = data.days[0].date, data.days[-1].date
    missing = (analysis_date - last).days

    if is_normal_end(last, analysis_date, expected_end or analysis_date):
        limitations.append(
            Limitation(text=ends_yesterday_text(last), affects="current", permanent=True)
        )
    elif missing > 0:
        limitations.append(
            Limitation(
                text=(
                    f"Dane pogodowe kończą się {pl(last)}, czyli {days_pl(missing)} przed "
                    f"Datą analizy ({pl(analysis_date)}). Bieżąca sytuacja wodna nie "
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
                    f"W danych pogodowych z okresu {pl(first)}–{pl(last)} brakuje "
                    f"opadu lub parowania dla {days_pl(inner_missing, genitive=True)}."
                ),
                affects="all",
                permanent=False,
            )
        )

    if first > start:
        limitations.append(
            Limitation(
                text=(
                    f"Dane pogodowe zaczynają się {pl(first)} i nie obejmują całego "
                    "Okna wieloletniego."
                ),
                affects="multiyear",
                permanent=False,
            )
        )
    return limitations

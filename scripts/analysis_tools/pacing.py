"""Keeping the tools within the published limits of the free data services.

One "start" is one run of all sources for one parcel and date: a whole
analysis, or one round of calling every source on its own. Each start makes
one call to the soil service, one to the parcel service and one large request
to the weather archive, so the limits below are counted in starts.

- Soil (ISRIC SoilGrids): 5 calls per minute. The default spacing of 13 s
  between starts keeps it under 4.7 per minute.
- Parcels (ULDK): 200 calls per minute by day, 40 at night, 10 000 per day.
  Far above anything the spacing allows.
- Weather archive (Open-Meteo, free access): 600 per minute, 5 000 per hour,
  10 000 per day, counted by the cost of a request and not by the number of
  requests. The request of one analysis (over ten years of daily values) was
  measured to cost about 88, which leaves about 6 analyses per minute, 56 per
  hour and 113 per day from one address. This is the limit that matters: the
  defaults are 50 starts per hour and 100 per day.

The counts cover what this tool started, including the rows already in its
output file. Other programs calling the services from the same address (the
service itself, other tools) are not seen; lower the limits when they run.
"""

import time
from collections.abc import Callable, Iterable
from datetime import datetime

DEFAULT_SPACING_S = 13.0
DEFAULT_PER_HOUR = 50
DEFAULT_PER_DAY = 100
HOUR_S = 3600.0
DAY_S = 86400.0
# Longest single sleep while waiting, so that an interrupt is answered quickly.
_SLEEP_STEP_S = 5.0


class DailyAllowanceUsed(Exception):
    """No more starts today; `again_at` is when the next one fits (epoch seconds)."""

    def __init__(self, again_at: float) -> None:
        super().__init__("daily allowance used")
        self.again_at = again_at

    @property
    def again_at_text(self) -> str:
        return datetime.fromtimestamp(self.again_at).strftime("%Y-%m-%d %H:%M")


class Pace:
    """Decides when the next start may happen.

    `spacing_s` is the shortest time between two starts; `per_hour` and
    `per_day` cap the starts within any hour and any 24 hours (0 = no cap).
    `earlier` are the times of starts made before this run.
    """

    def __init__(
        self,
        spacing_s: float = DEFAULT_SPACING_S,
        per_hour: int = DEFAULT_PER_HOUR,
        per_day: int = DEFAULT_PER_DAY,
        *,
        earlier: Iterable[datetime] = (),
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.spacing_s = max(0.0, spacing_s)
        self.per_hour = max(0, per_hour)
        self.per_day = max(0, per_day)
        self._clock = clock
        self._sleep = sleep
        now = clock()
        self._starts = sorted(
            moment.timestamp() for moment in earlier if now - moment.timestamp() < DAY_S
        )
        self._last_own_start: float | None = None

    def _window_wait(self, now: float, cap: int, window_s: float) -> float:
        """Seconds until fewer than `cap` starts lie within the last `window_s`."""
        if cap == 0:
            return 0.0
        inside = [start for start in self._starts if now - start < window_s]
        if len(inside) < cap:
            return 0.0
        # The start that has to leave the window before the next one fits.
        return inside[len(inside) - cap] + window_s - now

    def wait_s(self) -> float:
        """Seconds until the next start is allowed; 0 when it is allowed now.

        Raises `DailyAllowanceUsed` when the wait would be for the daily cap.
        """
        now = self._clock()
        day_wait = self._window_wait(now, self.per_day, DAY_S)
        if day_wait > 0:
            raise DailyAllowanceUsed(now + day_wait)
        spacing_wait = 0.0
        if self._last_own_start is not None:
            spacing_wait = self._last_own_start + self.spacing_s - now
        return max(0.0, spacing_wait, self._window_wait(now, self.per_hour, HOUR_S))

    def started(self) -> None:
        """Record a start made now."""
        now = self._clock()
        self._starts.append(now)
        self._last_own_start = now

    def acquire(self, announce: Callable[[str], None] = print) -> None:
        """Wait until a start is allowed and record it; announces a long wait."""
        wait = self.wait_s()
        if wait > max(60.0, 2 * self.spacing_s):
            announce(
                f"hourly allowance of the weather archive reached ({self.per_hour} starts); "
                f"waiting {wait / 60:.0f} min. Interrupt with Ctrl-C and run the same "
                "command later to continue."
            )
        while wait > 0:
            self._sleep(min(wait, _SLEEP_STEP_S))
            wait = self.wait_s()
        self.started()

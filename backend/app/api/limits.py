"""Limits that protect the service and the free data services behind it.

All values are engineering constants without a scientific source; none of
them decides a result. Each request limit can be changed with the environment
variable named next to it (0 switches that one limit off) and all of them can
be switched off together.

Why the routes are grouped: an analysis calls every external source (the free
weather archive allows about 56 analyses per hour from the address of the
server, the soil service 5 calls per minute), a parcel lookup calls the parcel
service, a derived Report and the simulation only cost processor time and
disk space, and asking for the progress of an analysis is cheap but frequent
(the page asks once per second, the measuring tools four times per second).
"""

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

logger = logging.getLogger("hydromiara.limits")

MINUTE_S = 60.0
HOUR_S = 3600.0

# Route groups; every request under the API prefix belongs to exactly one.
ANALYSIS = "analysis"  # start of an analysis, also for the critical period
DERIVE = "derive"  # a new Report from stored data
LOOKUP = "lookup"  # parcel search, parcel at a point, parcel geometry
SIMULATION = "simulation"  # crop ranking and comparison
STATUS = "status"  # progress of an analysis
OTHER = "other"  # everything else: reading a Report, lists, the interface description

ENABLED_ENV = "RATE_LIMIT_ENABLED"

# (group, window in seconds, environment variable, requests allowed per address)
DEFAULT_RULES: tuple[tuple[str, float, str, int], ...] = (
    (ANALYSIS, MINUTE_S, "RATE_LIMIT_ANALYSIS_PER_MINUTE", 6),
    (ANALYSIS, HOUR_S, "RATE_LIMIT_ANALYSIS_PER_HOUR", 50),
    (DERIVE, MINUTE_S, "RATE_LIMIT_DERIVE_PER_MINUTE", 10),
    (LOOKUP, MINUTE_S, "RATE_LIMIT_LOOKUP_PER_MINUTE", 40),
    (SIMULATION, MINUTE_S, "RATE_LIMIT_SIMULATION_PER_MINUTE", 30),
    (STATUS, MINUTE_S, "RATE_LIMIT_STATUS_PER_MINUTE", 600),
    (OTHER, MINUTE_S, "RATE_LIMIT_OTHER_PER_MINUTE", 300),
)

# Analyses running at the same time in the whole service, whoever started them.
MAX_CONCURRENT_ANALYSES_ENV = "MAX_CONCURRENT_ANALYSES"
DEFAULT_MAX_CONCURRENT_ANALYSES = 4
# Seconds a client is told to wait when every analysis slot is taken.
CAPACITY_RETRY_AFTER_S = 10

# Counters kept in memory at most; the oldest are dropped beyond this number.
MAX_TRACKED_COUNTERS = 20_000
# Counters whose window has ended are removed this often.
SWEEP_INTERVAL_S = 60.0

# Largest request body accepted. The largest valid body (a crop history) is
# well under 4 kB.
MAX_REQUEST_BODY_BYTES = 16_384

# Longest parcel identifier and longest report identifier accepted in a path.
MAX_PARCEL_ID_CHARS = 64
MAX_REPORT_ID_CHARS = 64

# Earliest analysis date accepted. The task asks for dates up to ten years
# back; earlier dates down to this one are accepted for checking the method,
# and anything before it is refused instead of being sent to the sources.
EARLIEST_ANALYSIS_DATE = date(2000, 1, 1)


@dataclass(frozen=True)
class Rule:
    """At most `limit` requests of one group from one address within `window_s`."""

    group: str
    window_s: float
    limit: int


@dataclass(frozen=True)
class LimitSettings:
    enabled: bool = True
    rules: tuple[Rule, ...] = field(
        default=tuple(Rule(group, window, limit) for group, window, _, limit in DEFAULT_RULES)
    )
    max_concurrent_analyses: int = DEFAULT_MAX_CONCURRENT_ANALYSES

    def rules_for(self, group: str) -> tuple[Rule, ...]:
        if not self.enabled:
            return ()
        return tuple(rule for rule in self.rules if rule.group == group and rule.limit > 0)


# No request limit and no limit of concurrent analyses (tests, in-process tools).
NO_LIMITS = LimitSettings(enabled=False, max_concurrent_analyses=0)


def _count(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        value = -1
    if value < 0:
        logger.warning("%s is not a whole number of 0 or more; using the default", name)
        return default
    return value


def settings_from_env(env: Mapping[str, str] | None = None) -> LimitSettings:
    """Limits as configured for this process; unset or unreadable values keep the default."""
    env = os.environ if env is None else env
    enabled = env.get(ENABLED_ENV, "").strip().lower() not in {"0", "false", "no", "off"}
    return LimitSettings(
        enabled=enabled,
        rules=tuple(
            Rule(group, window, _count(env, name, limit))
            for group, window, name, limit in DEFAULT_RULES
        ),
        max_concurrent_analyses=_count(
            env, MAX_CONCURRENT_ANALYSES_ENV, DEFAULT_MAX_CONCURRENT_ANALYSES
        ),
    )

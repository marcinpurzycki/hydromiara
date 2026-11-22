"""Limit of requests per client address, kept in the memory of the process.

The service runs as one process per database file, so the counters need no
shared store. A counter is a fixed window: it starts with the first request
of a group from an address and allows a set number of requests until the
window ends. Requests refused by a limit are not counted.

The client address is what the server reports as the peer of the connection.
Behind a reverse proxy this is the address of the real client only when the
server is told which proxy to trust (`FORWARDED_ALLOW_IPS` of Uvicorn);
otherwise every client shares the address of the proxy and with it one set of
counters. The forwarding headers are never read here.

Addresses are held only in memory, only until their windows end, and are
never written to the log or to the database.
"""

import ipaddress
import logging
import math
import re
import time
from collections.abc import Callable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api import limits
from app.api.limits import LimitSettings

logger = logging.getLogger("hydromiara.limits")

_ID = r"[^/]+"
# The same paths the router matches, relative to the API prefix.
_GROUPS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("POST", re.compile(r"/analyses"), limits.ANALYSIS),
    ("POST", re.compile(rf"/reports/{_ID}/critical-period"), limits.ANALYSIS),
    ("POST", re.compile(rf"/reports/{_ID}/derive"), limits.DERIVE),
    ("GET", re.compile(r"/parcels/.+"), limits.LOOKUP),
    ("GET", re.compile(rf"/reports/{_ID}/simulation/.+"), limits.SIMULATION),
    ("GET", re.compile(rf"/analyses/{_ID}/status"), limits.STATUS),
)
# Asked by the container health check and by the proxy; never limited.
_EXEMPT = {"/health"}

# Bits of an IPv6 address that identify one network of a client.
_IPV6_PREFIX = 64


def route_group(method: str, path: str) -> str | None:
    """Group of a request from its method and path below the API prefix; None = not limited."""
    if path in _EXEMPT:
        return None
    for group_method, pattern, group in _GROUPS:
        if method == group_method and pattern.fullmatch(path):
            return group
    return limits.OTHER


def client_key(scope: Scope) -> str:
    """What the counters are kept for: the client address, IPv6 cut to its network."""
    client = scope.get("client")
    host = client[0] if client else ""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host or "unknown"
    if address.version == 6:
        return str(ipaddress.ip_network((address, _IPV6_PREFIX), strict=False).network_address)
    return str(address)


class RateLimiter:
    """Counters of all addresses; `check` both asks and counts."""

    def __init__(
        self,
        settings: LimitSettings,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_counters: int = limits.MAX_TRACKED_COUNTERS,
    ) -> None:
        self.settings = settings
        self._clock = clock
        self._max_counters = max_counters
        # (group, window, address) -> [end of the window, requests counted, refusal logged]
        self._counters: dict[tuple[str, float, str], list] = {}
        self._next_sweep = clock() + limits.SWEEP_INTERVAL_S

    def configure(self, settings: LimitSettings, clock: Callable[[], float] | None = None) -> None:
        """Replace the limits (and the clock) and forget every counter."""
        self.settings = settings
        self._clock = clock or self._clock
        self._counters.clear()
        self._next_sweep = self._clock() + limits.SWEEP_INTERVAL_S

    @property
    def tracked(self) -> int:
        return len(self._counters)

    def check(self, group: str, address: str) -> int | None:
        """Count the request; None when allowed, else whole seconds until it will be."""
        rules = self.settings.rules_for(group)
        if not rules:
            return None
        now = self._clock()
        self._sweep(now)
        counters = []
        retry_after = 0.0
        for rule in rules:
            key = (rule.group, rule.window_s, address)
            counter = self._counters.get(key)
            if counter is None or counter[0] <= now:
                counter = self._counters[key] = [now + rule.window_s, 0, False]
            counters.append(counter)
            if counter[1] >= rule.limit:
                retry_after = max(retry_after, counter[0] - now)
                if not counter[2]:
                    counter[2] = True
                    # The address is left out on purpose.
                    logger.warning(
                        "request limit reached group=%s window_s=%.0f", group, rule.window_s
                    )
        if retry_after > 0:
            return max(1, math.ceil(retry_after))
        for counter in counters:
            counter[1] += 1
        return None

    def _sweep(self, now: float) -> None:
        """Keep memory bounded: drop ended windows, then the oldest counters if too many."""
        if now < self._next_sweep and len(self._counters) < self._max_counters:
            return
        self._next_sweep = now + limits.SWEEP_INTERVAL_S
        for key in [key for key, counter in self._counters.items() if counter[0] <= now]:
            del self._counters[key]
        excess = len(self._counters) - self._max_counters * 9 // 10
        if len(self._counters) >= self._max_counters and excess > 0:
            for key in list(self._counters)[:excess]:
                del self._counters[key]


def wait_text(seconds: int) -> str:
    if seconds < 90:
        return f"{seconds} s"
    return f"ok. {math.ceil(seconds / 60)} min"


def too_many_requests(retry_after_s: int) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "code": "rate_limited",
            "message": (
                "Za dużo zapytań z tego adresu w krótkim czasie. "
                f"Spróbuj ponownie za {wait_text(retry_after_s)}."
            ),
        },
        headers={"Retry-After": str(retry_after_s)},
    )


class RateLimitMiddleware:
    """Answers 429 with `Retry-After` when the address has used up a limit of the group."""

    def __init__(self, app: ASGIApp, *, limiter: RateLimiter, prefix: str) -> None:
        self.app = app
        self.limiter = limiter
        self.prefix = prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self.prefix + "/"):
            await self.app(scope, receive, send)
            return
        group = route_group(scope["method"], scope["path"][len(self.prefix) :])
        retry_after = None if group is None else self.limiter.check(group, client_key(scope))
        if retry_after is not None:
            await too_many_requests(retry_after)(scope, receive, send)
            return
        await self.app(scope, receive, send)

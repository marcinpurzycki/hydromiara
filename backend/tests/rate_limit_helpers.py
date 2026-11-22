"""Helpers of the request limit tests: a clock set by the test, limits put on the application."""

from app.api.limits import LimitSettings, Rule
from app.main import app


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def settings(*rules: Rule, concurrent: int = 0) -> LimitSettings:
    return LimitSettings(enabled=True, rules=rules, max_concurrent_analyses=concurrent)


def use(clock: Clock, *rules: Rule, concurrent: int = 0) -> None:
    app.state.rate_limiter.configure(settings(*rules, concurrent=concurrent), clock)


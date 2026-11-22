"""Request limits per client address: groups of routes, counting, windows, memory, settings."""

import pytest

from app.api import limits
from app.api.limits import LimitSettings, Rule, settings_from_env
from app.api.rate_limit import RateLimiter, client_key, route_group, wait_text
from tests.rate_limit_helpers import Clock, settings


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.mark.parametrize(
    ("method", "path", "group"),
    [
        ("POST", "/analyses", limits.ANALYSIS),
        ("POST", "/reports/abc/critical-period", limits.ANALYSIS),
        ("POST", "/reports/abc/derive", limits.DERIVE),
        ("GET", "/parcels/search", limits.LOOKUP),
        ("GET", "/parcels/at", limits.LOOKUP),
        ("GET", "/parcels/040704_2.0020.34/2", limits.LOOKUP),
        ("GET", "/reports/abc/simulation/ranking", limits.SIMULATION),
        ("GET", "/reports/abc/simulation/compare", limits.SIMULATION),
        ("GET", "/analyses/abc/status", limits.STATUS),
        ("GET", "/reports/abc", limits.OTHER),
        ("PUT", "/analyses/abc/crop-history", limits.OTHER),
        ("GET", "/crops", limits.OTHER),
        ("GET", "/docs", limits.OTHER),
        ("GET", "/analyses", limits.OTHER),
        ("GET", "/no-such-route", limits.OTHER),
        ("GET", "/health", None),
    ],
)
def test_every_route_has_its_group(method, path, group):
    assert route_group(method, path) == group


def test_every_declared_route_is_limited_as_intended(client):
    """A route added later lands in a group on purpose, not by accident."""
    expensive = {
        ("POST", "/api/analyses"): limits.ANALYSIS,
        ("POST", "/api/reports/{report_id}/critical-period"): limits.ANALYSIS,
        ("POST", "/api/reports/{report_id}/derive"): limits.DERIVE,
        ("GET", "/api/parcels/search"): limits.LOOKUP,
        ("GET", "/api/parcels/at"): limits.LOOKUP,
        ("GET", "/api/parcels/{parcel_id}"): limits.LOOKUP,
        ("GET", "/api/reports/{report_id}/simulation/ranking"): limits.SIMULATION,
        ("GET", "/api/reports/{report_id}/simulation/compare"): limits.SIMULATION,
        ("GET", "/api/analyses/{report_id}/status"): limits.STATUS,
        ("GET", "/api/health"): None,
    }
    paths = client.get("/api/openapi.json").json()["paths"]
    for path, operations in paths.items():
        for method in operations:
            concrete = path.replace("{report_id}", "abc").replace("{parcel_id}", "1/2")
            group = route_group(method.upper(), concrete.removeprefix("/api"))
            assert group == expensive.get((method.upper(), path), limits.OTHER), (method, path)


def test_limit_window_and_renewal(clock):
    limiter = RateLimiter(settings(Rule("g", 60.0, 3)), clock=clock)
    assert [limiter.check("g", "a") for _ in range(3)] == [None, None, None]
    assert limiter.check("g", "a") == 60
    clock.now += 59.2
    assert limiter.check("g", "a") == 1
    clock.now += 0.8
    assert limiter.check("g", "a") is None


def test_refused_requests_are_not_counted(clock):
    limiter = RateLimiter(settings(Rule("g", 60.0, 1)), clock=clock)
    assert limiter.check("g", "a") is None
    for _ in range(50):
        assert limiter.check("g", "a") is not None
    clock.now += 60
    assert limiter.check("g", "a") is None


def test_counters_are_separate_per_address_and_per_group(clock):
    limiter = RateLimiter(settings(Rule("g", 60.0, 1), Rule("h", 60.0, 1)), clock=clock)
    assert limiter.check("g", "a") is None
    assert limiter.check("g", "a") is not None
    assert limiter.check("g", "b") is None
    assert limiter.check("h", "a") is None
    assert limiter.check("ungrouped", "a") is None


def test_two_windows_of_one_group_and_the_longer_wait(clock):
    limiter = RateLimiter(settings(Rule("g", 60.0, 2), Rule("g", 3600.0, 3)), clock=clock)
    assert limiter.check("g", "a") is None
    assert limiter.check("g", "a") is None
    assert limiter.check("g", "a") == 60
    clock.now += 60
    assert limiter.check("g", "a") is None
    # The minute has room again, the hour has not.
    clock.now += 60
    assert limiter.check("g", "a") == 3600 - 120


def test_zero_switches_one_limit_off_and_disabled_switches_all(clock):
    limiter = RateLimiter(settings(Rule("g", 60.0, 0)), clock=clock)
    assert all(limiter.check("g", "a") is None for _ in range(100))
    assert limiter.tracked == 0
    limiter.configure(LimitSettings(enabled=False, rules=(Rule("g", 60.0, 1),)))
    assert all(limiter.check("g", "a") is None for _ in range(100))


def test_ended_windows_are_removed(clock):
    limiter = RateLimiter(settings(Rule("g", 60.0, 5)), clock=clock)
    for number in range(500):
        limiter.check("g", f"10.0.{number // 250}.{number % 250}")
    assert limiter.tracked == 500
    clock.now += limits.SWEEP_INTERVAL_S + 1
    limiter.check("g", "new")
    assert limiter.tracked == 1


def test_number_of_counters_is_bounded(clock):
    limiter = RateLimiter(settings(Rule("g", 3600.0, 5)), clock=clock, max_counters=100)
    for number in range(1000):
        limiter.check("g", f"address-{number}")
        assert limiter.tracked <= 100
    # The newest address is still counted.
    assert [limiter.check("g", "address-999") for _ in range(5)][-1] is not None


def test_client_key():
    assert client_key({"client": ("192.0.2.7", 1234)}) == "192.0.2.7"
    # One IPv6 network of a client counts as one address.
    first = client_key({"client": ("2001:db8:1:2:aaaa::1", 1)})
    assert first == client_key({"client": ("2001:db8:1:2:bbbb::2", 1)}) == "2001:db8:1:2::"
    assert first != client_key({"client": ("2001:db8:1:3::1", 1)})
    assert client_key({"client": None}) == "unknown"
    assert client_key({"client": ("testclient", 50000)}) == "testclient"


def test_wait_text():
    assert wait_text(42) == "42 s"
    assert wait_text(600) == "ok. 10 min"


def test_settings_from_env():
    default = settings_from_env({})
    assert default == LimitSettings()
    assert {(rule.group, rule.window_s): rule.limit for rule in default.rules} == {
        (limits.ANALYSIS, 60.0): 6,
        (limits.ANALYSIS, 3600.0): 50,
        (limits.DERIVE, 60.0): 10,
        (limits.LOOKUP, 60.0): 40,
        (limits.SIMULATION, 60.0): 30,
        (limits.STATUS, 60.0): 600,
        (limits.OTHER, 60.0): 300,
    }
    assert default.max_concurrent_analyses == 4
    changed = settings_from_env(
        {"RATE_LIMIT_STATUS_PER_MINUTE": "0", "RATE_LIMIT_LOOKUP_PER_MINUTE": " 7 ",
         "MAX_CONCURRENT_ANALYSES": "2", "RATE_LIMIT_OTHER_PER_MINUTE": "many",
         "RATE_LIMIT_DERIVE_PER_MINUTE": "-3"}
    )  # fmt: skip
    assert changed.rules_for(limits.STATUS) == ()
    assert changed.rules_for(limits.LOOKUP) == (Rule(limits.LOOKUP, 60.0, 7),)
    assert changed.rules_for(limits.OTHER) == (Rule(limits.OTHER, 60.0, 300),)
    assert changed.rules_for(limits.DERIVE) == (Rule(limits.DERIVE, 60.0, 10),)
    assert changed.max_concurrent_analyses == 2
    for off in ("0", "false", "OFF", "no"):
        assert settings_from_env({"RATE_LIMIT_ENABLED": off}).rules_for(limits.ANALYSIS) == ()
    assert settings_from_env({"RATE_LIMIT_ENABLED": "1"}).enabled

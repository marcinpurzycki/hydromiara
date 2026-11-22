"""Request limits over HTTP: 429 with Retry-After, separate counters, analyses at once."""

import pytest
from fastapi.testclient import TestClient

from app.api import limits
from app.api.limits import LimitSettings, Rule
from app.main import app
from tests.analysis_helpers import ANALYSIS, assert_error, start, wait_finished
from tests.rate_limit_helpers import Clock, use


@pytest.fixture
def clock() -> Clock:
    return Clock()


def test_below_the_limit_then_429_with_retry_after_then_renewal(client, clock):
    use(clock, Rule(limits.OTHER, 60.0, 3))
    for _ in range(3):
        assert client.get("/api/crops").status_code == 200
    refused = client.get("/api/crops")
    assert_error(refused, 429, "rate_limited")
    assert refused.headers["retry-after"] == "60"
    assert "60 s" in refused.json()["message"]
    clock.now += 60
    assert client.get("/api/crops").status_code == 200


def test_groups_do_not_share_a_counter_over_http(client, clock):
    use(clock, Rule(limits.LOOKUP, 60.0, 1), Rule(limits.OTHER, 60.0, 1))
    assert client.get("/api/parcels/search", params={"q": "Stara Wieś 756"}).status_code == 200
    assert client.get("/api/parcels/at", params={"lon": 18.2, "lat": 52.75}).status_code == 429
    assert client.get("/api/crops").status_code == 200
    assert client.get("/api/examples").status_code == 429
    # Never limited, whatever the other counters say.
    for _ in range(20):
        assert client.get("/api/health").status_code == 200


def test_addresses_do_not_share_a_counter_over_http(reports_db, clock):
    use(clock, Rule(limits.OTHER, 60.0, 1))
    with TestClient(app, client=("192.0.2.1", 50000)) as first:
        assert first.get("/api/crops").status_code == 200
        assert first.get("/api/crops").status_code == 429
        # A forwarding header sent by the client itself changes nothing.
        spoofed = first.get("/api/crops", headers={"X-Forwarded-For": "198.51.100.9"})
        assert spoofed.status_code == 429
    with TestClient(app, client=("192.0.2.2", 50000)) as second:
        assert second.get("/api/crops").status_code == 200


def test_starting_analyses_is_limited_separately_from_progress(client, clock):
    use(clock, *LimitSettings().rules)
    report_id = start(client)
    # A page asks once per second for up to 30 s, the tools four times per second:
    # 240 requests within one minute must pass.
    for _ in range(240):
        assert client.get(f"/api/analyses/{report_id}/status").status_code == 200
    wait_finished(client, report_id)
    for _ in range(5):
        wait_finished(client, start(client))
    refused = client.post("/api/analyses", json=ANALYSIS)
    assert_error(refused, 429, "rate_limited")
    assert int(refused.headers["retry-after"]) == 60
    # Reading stays possible while starting is refused.
    assert client.get(f"/api/reports/{report_id}").status_code == 200
    assert client.get(f"/api/analyses/{report_id}/status").status_code == 200
    clock.now += 61
    wait_finished(client, start(client))


def test_hourly_limit_of_analyses(client, clock):
    use(clock, Rule(limits.ANALYSIS, 3600.0, 2))
    wait_finished(client, start(client))
    wait_finished(client, start(client))
    refused = client.post("/api/analyses", json=ANALYSIS)
    assert_error(refused, 429, "rate_limited")
    assert refused.headers["retry-after"] == "3600"
    assert "ok. 60 min" in refused.json()["message"]


def test_limit_of_concurrent_analyses(client, clock, weather):
    use(clock, concurrent=2)
    weather.hold = True
    first, second = start(client), start(client)
    refused = client.post("/api/analyses", json=ANALYSIS)
    assert_error(refused, 503, "analysis_capacity_reached")
    assert refused.headers["retry-after"] == str(limits.CAPACITY_RETRY_AFTER_S)
    # Progress and the other routes are not affected.
    assert client.get(f"/api/analyses/{first}/status").status_code == 200
    weather.hold = False
    wait_finished(client, first)
    wait_finished(client, second)
    wait_finished(client, start(client))


def test_limit_of_concurrent_analyses_covers_the_critical_period_route(client, clock, weather):
    use(clock, concurrent=1)
    report_id = start(client, analysis_date="2023-11-15")
    wait_finished(client, report_id)
    weather.hold = True
    running = start(client)
    refused = client.post(f"/api/reports/{report_id}/critical-period")
    assert_error(refused, 503, "analysis_capacity_reached")
    weather.hold = False
    wait_finished(client, running)
    assert client.post(f"/api/reports/{report_id}/critical-period").status_code == 202


def test_limits_are_off_in_the_shared_test_setup(client):
    for _ in range(400):
        assert client.get("/api/crops").status_code == 200

"""Shared test setup: external services are replaced by recorded answers."""

import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.limits import NO_LIMITS
from app.main import app
from app.orchestrator.sources import OptionalSources, get_optional_sources, get_weather_source
from app.sources.parcels import ParcelSource, get_parcel_source
from app.sources.weather import WeatherSource
from app.storage.params import DB_PATH_ENV
from app.summary import params as summary_params

ULDK_FIXTURES = Path(__file__).parent / "fixtures" / "uldk"

KNOWN_ID = "040704_2.0020.34/2"
KNOWN_POINT = "18.2,52.75,4326"

_SEARCHES = {
    KNOWN_ID: "search_one.txt",
    "Krusza Podlotowa 34/2": "search_one.txt",
    "Stara Wieś 756": "search_many.txt",
}


def uldk_text(name: str) -> str:
    return (ULDK_FIXTURES / name).read_text(encoding="utf-8")


class RecordedUldk:
    """Answers like the parcel service did when the fixtures were recorded."""

    def __init__(self) -> None:
        self.requests: list[dict[str, str]] = []
        self.failure: Exception | int | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        self.requests.append(params)
        if isinstance(self.failure, Exception):
            raise self.failure
        if isinstance(self.failure, int):
            return httpx.Response(self.failure, text="error")
        return httpx.Response(200, text=uldk_text(self._fixture(params)))

    @staticmethod
    def _fixture(params: dict[str, str]) -> str:
        operation = params["request"]
        if operation == "GetParcelById":
            return "by_id_found.txt" if params["id"] == KNOWN_ID else "not_found.txt"
        if operation == "GetParcelByXY":
            return "by_xy_found.txt" if params["xy"] == KNOWN_POINT else "not_found.txt"
        return _SEARCHES.get(params["id"], "search_none.txt")


@pytest.fixture
def uldk() -> RecordedUldk:
    return RecordedUldk()


@pytest.fixture
def parcel_source(uldk: RecordedUldk) -> ParcelSource:
    return ParcelSource(transport=httpx.MockTransport(uldk))


@pytest.fixture(autouse=True)
def no_network_parcels(parcel_source: ParcelSource):
    """Every API test talks to the recorded parcel service, never to the network."""
    app.dependency_overrides[get_parcel_source] = lambda: parcel_source
    yield
    app.dependency_overrides.pop(get_parcel_source, None)


# --- Analyses: recorded weather archive, report database in a temporary file ---

WEATHER_FIXTURES = Path(__file__).parent / "fixtures" / "open_meteo"


class RecordedWeather(httpx.AsyncBaseTransport):
    """Answers like the weather archive did; can be held back, slowed down or broken."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.payload = (WEATHER_FIXTURES / "archive_2012_2023.json").read_text(encoding="utf-8")
        self.status_code = 200
        # While True the answer is not sent; a test sets it back to release it.
        self.hold = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        while self.hold:
            await asyncio.sleep(0.005)
        return httpx.Response(
            self.status_code, text=self.payload, headers={"content-type": "application/json"}
        )


@pytest.fixture
def weather() -> RecordedWeather:
    return RecordedWeather()


@pytest.fixture(autouse=True)
def no_network_weather(weather: RecordedWeather):
    """Every analysis reads the recorded weather archive, never the network."""
    app.dependency_overrides[get_weather_source] = lambda: WeatherSource(transport=weather)
    yield
    app.dependency_overrides.pop(get_weather_source, None)


class OptionalSourcesInUse:
    """The optional sources new analyses get; a test may replace `current`."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self.current: OptionalSources | None = None

    def recorded(self) -> OptionalSources:
        """Real adapters on recorded answers and on rasters written for this test."""
        from tests.recorded_sources import recorded_optional_sources

        return recorded_optional_sources(self._directory)

    def __call__(self) -> OptionalSources:
        if self.current is None:
            self.current = self.recorded()
        return self.current


@pytest.fixture
def optional_sources(tmp_path) -> OptionalSourcesInUse:
    return OptionalSourcesInUse(tmp_path)


@pytest.fixture(autouse=True)
def no_network_optional_sources(optional_sources: OptionalSourcesInUse):
    """Soil, terrain, satellite and drought background never touch the network."""
    app.dependency_overrides[get_optional_sources] = optional_sources
    yield
    app.dependency_overrides.pop(get_optional_sources, None)


@pytest.fixture(autouse=True)
def reports_db(tmp_path, monkeypatch) -> Path:
    """Each test gets its own report database file."""
    path = tmp_path / "reports.sqlite3"
    monkeypatch.setenv(DB_PATH_ENV, str(path))
    return path


@pytest.fixture(autouse=True)
def no_summary_provider(monkeypatch):
    """No test reaches a language model: its configuration is cleared from the environment."""
    for name in ("API_KEY_ENV", "MODEL_ENV", "BASE_URL_ENV", "TIMEOUT_ENV", "REASONING_EFFORT_ENV"):
        monkeypatch.delenv(getattr(summary_params, name), raising=False)


@pytest.fixture(autouse=True)
def no_request_limits():
    """Tests send requests as fast as they can; the limits are tested on their own."""
    app.state.rate_limiter.configure(NO_LIMITS)
    yield
    app.state.rate_limiter.configure(NO_LIMITS)


@pytest.fixture
def client(reports_db):
    """Client of the running application: the lifespan opens the report store."""
    with TestClient(app) as running:
        yield running

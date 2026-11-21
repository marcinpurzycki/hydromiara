"""Shared test setup: the parcel service is replaced by recorded answers."""

from pathlib import Path

import httpx
import pytest

from app.main import app
from app.sources.parcels import ParcelSource, get_parcel_source

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

"""Helpers for the analysis tests: requests, waiting for the end, stored inputs."""

import time
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from app.contracts.analyses import AnalysisRequest
from app.contracts.source_data import SourceData, SourceOutcome
from tests.engine_helpers import recorded_weather, source_data

PARCEL_ID = "040704_2.0020.34/2"
ANALYSIS_DATE = date(2023, 6, 20)
ANALYSIS = {
    "parcel_id": PARCEL_ID,
    "crop_id": "winter_wheat",
    "analysis_date": ANALYSIS_DATE.isoformat(),
}
REQUEST = AnalysisRequest.model_validate(ANALYSIS)
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


def start(client: TestClient, **changes: str) -> str:
    response = client.post("/api/analyses", json={**ANALYSIS, **changes})
    assert response.status_code == 202, response.text
    return response.json()["report_id"]


def status_of(client: TestClient, report_id: str) -> dict:
    response = client.get(f"/api/analyses/{report_id}/status")
    assert response.status_code == 200, response.text
    return response.json()


def wait_finished(client: TestClient, report_id: str, timeout_s: float = 10.0) -> dict:
    """Poll the status route until the analysis is no longer running."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        status = status_of(client, report_id)
        if status["state"] != "running":
            return status
        time.sleep(0.01)
    raise AssertionError("the analysis did not finish in time")


def source_states(status: dict) -> dict[str, str]:
    return {source["id"]: source["state"] for source in status["sources"]}


def assert_error(response, status_code: int, code: str) -> None:
    assert response.status_code == status_code, response.text
    body = response.json()
    assert set(body) == {"code", "message"}
    assert body["code"] == code
    assert body["message"]


def stored_source_data() -> SourceData:
    """Source data as an analysis stores them: recorded weather, no soil, two outcomes."""
    data = source_data(recorded_weather())
    outcomes = [
        SourceOutcome(
            topic=topic,
            source_name=name,
            chain_step=1,
            ok=True,
            duration_s=0.3,
            data_date="2023-06-20",
            fetched_at=NOW,
        )
        for topic, name in (("parcel", "ULDK GUGiK"), ("weather", "Open-Meteo"))
    ]
    return data.model_copy(update={"outcomes": outcomes})

"""The service log holds no client address and never a whole report identifier."""

import logging

from fastapi.testclient import TestClient

from app.api import limits
from app.api.limits import LimitSettings, Rule
from app.main import app
from app.orchestrator.params import LOG_ID_CHARS
from tests.analysis_helpers import ANALYSIS, PARCEL_ID, start, wait_finished

CLIENT_ADDRESS = "203.0.113.77"


# Loggers of the service and of the server; the test client logs its own requests too.
SERVICE_LOGGERS = ("hydromiara", "uvicorn", "fastapi", "starlette")


def logged(caplog) -> str:
    return "\n".join(
        record.getMessage() for record in caplog.records if record.name.startswith(SERVICE_LOGGERS)
    )


def test_whole_run_logs_neither_the_address_nor_the_whole_identifier(reports_db, caplog):
    caplog.set_level(logging.DEBUG)
    app.state.rate_limiter.configure(
        LimitSettings(rules=(Rule(limits.ANALYSIS, 60.0, 2), Rule(limits.OTHER, 60.0, 50)))
    )
    with TestClient(app, client=(CLIENT_ADDRESS, 50000)) as client:
        report_id = start(client)
        wait_finished(client, report_id)
        assert client.get(f"/api/reports/{report_id}").status_code == 200
        history = {"crop_history": {"same_every_year": True}}
        derived = client.post(f"/api/reports/{report_id}/derive", json=history).json()["report_id"]
        assert client.get(f"/api/reports/{report_id}/simulation/ranking").status_code == 200
        failed = start(client, parcel_id="141201_1.0001.9999")
        wait_finished(client, failed)
        assert client.post("/api/analyses", json=ANALYSIS).status_code == 429
        assert client.get("/api/reports/not-a-report").status_code == 404

    text = logged(caplog)
    # The run did log: the analysis with its shortened identifier and the refusal.
    assert f"analysis {report_id[:LOG_ID_CHARS]} finished" in text
    assert "request limit reached group=analysis" in text
    assert PARCEL_ID in text  # the parcel identifier is not a secret and may be logged
    for identifier in (report_id, derived, failed):
        assert identifier not in text
        assert identifier[: LOG_ID_CHARS + 1] not in text
    assert CLIENT_ADDRESS not in text
    assert "not-a-report" not in text


def test_logged_identifier_is_too_short_to_open_a_report():
    # 6 of 22 characters: 36 of the 128 random bits.
    assert LOG_ID_CHARS <= 8

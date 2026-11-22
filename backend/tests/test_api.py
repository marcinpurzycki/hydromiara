"""Every route of the contract answers with the declared shape."""

import pytest

from app.contracts.report import Report
from app.mock import store

PARCEL_ID = "040704_2.0020.34/2"
ANALYSIS = {"parcel_id": PARCEL_ID, "crop_id": "winter_wheat", "analysis_date": "2023-06-20"}


@pytest.fixture
def instant(monkeypatch):
    """Analyses finish immediately."""
    monkeypatch.setattr(store, "speed", 0.0)


def assert_error(response, status_code: int, code: str) -> None:
    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"code", "message"}
    assert body["code"] == code


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_lists_all_contract_paths(client):
    paths = client.get("/api/openapi.json").json()["paths"]
    assert set(paths) == {
        "/api/health",
        "/api/crops",
        "/api/examples",
        "/api/parcels/search",
        "/api/parcels/at",
        "/api/parcels/{parcel_id}",
        "/api/analyses",
        "/api/analyses/{report_id}/status",
        "/api/analyses/{report_id}/crop-history",
        "/api/reports/{report_id}",
        "/api/reports/{report_id}/derive",
        "/api/reports/{report_id}/critical-period",
        "/api/reports/{report_id}/simulation/ranking",
        "/api/reports/{report_id}/simulation/compare",
    }


def test_crops_and_examples(client):
    crops = client.get("/api/crops").json()
    assert {"winter_wheat", "bare_field"} <= {crop["id"] for crop in crops}
    examples = client.get("/api/examples").json()
    assert len(examples) == 6
    assert [example["kind"] for example in examples].count("deficit") == 3
    assert {example["crop_id"] for example in examples} <= {crop["id"] for crop in crops}
    assert not any("Atrapa" in example["label"] for example in examples)


def test_unknown_route_and_bad_query_use_error_body(client):
    assert_error(client.get("/api/parcels/at", params={"lon": "x", "lat": 52}), 422, "validation_error")
    assert_error(client.get("/api/nothing"), 404, "not_found")


def test_demo_report_is_always_available(client):
    response = client.get("/api/reports/demo")
    assert response.status_code == 200
    assert Report.model_validate(response.json()).meta.report_id == "demo"


def test_analysis_starts_and_ends_with_a_report(client):
    started = client.post("/api/analyses", json=ANALYSIS)
    assert started.status_code == 202
    report_id = started.json()["report_id"]

    status = client.get(f"/api/analyses/{report_id}/status").json()
    assert [source["id"] for source in status["sources"]] == [
        "weather", "soil", "terrain", "satellite", "hydro",
    ]
    while status["state"] == "running":
        status = client.get(f"/api/analyses/{report_id}/status").json()
    assert status["state"] == "done"
    assert {source["state"] for source in status["sources"]} == {"done", "missing"}
    assert client.get(f"/api/reports/{report_id}").json()["meta"]["report_id"] == report_id
    history = {"same_every_year": True}
    assert_error(
        client.put(f"/api/analyses/{report_id}/crop-history", json=history), 409, "analysis_finished"
    )


def test_demo_report_keeps_its_placeholder_progress(client):
    status = client.get("/api/analyses/demo/status").json()
    assert status["state"] == "done"
    history = {"same_every_year": True}
    assert_error(
        client.put("/api/analyses/demo/crop-history", json=history), 409, "analysis_finished"
    )


def test_analysis_validation(client):
    assert_error(client.post("/api/analyses", json={**ANALYSIS, "crop_id": "x"}), 422, "unknown_crop")
    assert_error(
        client.post("/api/analyses", json={**ANALYSIS, "analysis_date": "20.06.2023"}),
        422,
        "validation_error",
    )
    assert_error(client.get("/api/analyses/unknown/status"), 404, "report_not_found")
    assert_error(client.get("/api/reports/unknown"), 404, "report_not_found")


def test_derive_and_critical_period(client, instant):
    derived = client.post(
        "/api/reports/demo/derive", json={"crop_history": {"years": {"2019": "maize"}}}
    )
    assert derived.status_code == 201
    assert client.get(f"/api/reports/{derived.json()['report_id']}").status_code == 200

    critical = client.post("/api/reports/demo/critical-period")
    assert critical.status_code == 202
    assert set(critical.json()) == {"report_id", "analysis_date"}


def test_simulation(client):
    ranking = client.get("/api/reports/demo/simulation/ranking").json()
    assert len(ranking["top"]) == 3
    assert ranking["current"]["crop_id"] == "winter_wheat"
    deficits = [crop["deficit_years"] for crop in ranking["top"]]
    assert deficits == sorted(deficits)

    compare = client.get("/api/reports/demo/simulation/compare", params={"crop_id": "maize"})
    assert compare.status_code == 200
    assert len(compare.json()["years"]) == 10
    assert_error(
        client.get("/api/reports/demo/simulation/compare", params={"crop_id": "x"}),
        422,
        "unknown_crop",
    )

"""Smoke check of a whole analysis with the waters read live (needs network).

Run from the backend directory:
    python -m tests.smoke.water_analysis_smoke [PARCEL_ID [CROP_ID [ANALYSIS_DATE]]]
    python -m tests.smoke.water_analysis_smoke --url http://127.0.0.1:8000 [...]

Starts one analysis, waits for its end and prints the total time and what the
waters gave to the Report: the source entry, the objects on the map by kind,
the trace of the water analysis, the recommendations that depend on waters
with their retention sites, and the limitations about waters. Exits with 1
when the analysis fails or takes longer than the time budget; waters without
data are a normal result and are printed as such.
"""

import argparse
import sys
import time
from collections import Counter

from app.contracts.report import Report
from app.orchestrator.params import ANALYSIS_BUDGET_S
from tests.smoke.analysis_smoke import DEFAULTS, api_client

WATER_WORDS = ("rów", "row", "ciek", "wod", "BDOT")


def run(client, parcel_id: str, crop_id: str, analysis_date: str) -> bool:
    request = {"parcel_id": parcel_id, "crop_id": crop_id, "analysis_date": analysis_date}
    started = time.monotonic()
    response = client.post("/api/analyses", json=request)
    if response.status_code != 202:
        print(f"NOT ACCEPTED: {response.status_code} {response.text}")
        return False
    report_id = response.json()["report_id"]
    while True:
        status = client.get(f"/api/analyses/{report_id}/status").json()
        if status["state"] != "running" or time.monotonic() - started > 2 * ANALYSIS_BUDGET_S:
            break
        time.sleep(0.1)
    total_s = time.monotonic() - started
    print(f"{parcel_id} {crop_id} {analysis_date}: state {status['state']} after {total_s:.2f} s")
    for source in status["sources"]:
        print(f"  status {source['id']:<10} {source['state']:<8} {source['note'] or ''}")
    answer = client.get(f"/api/reports/{report_id}")
    if answer.status_code != 200:
        print(f"NO REPORT: {answer.status_code} {answer.text}")
        return False
    report = Report.model_validate(answer.json())
    for source in report.sources:
        if source.topic == "hydro":
            print(f"  source: {source.name}; step {source.chain_step}; mode {source.mode}; "
                  f"missing={source.missing}; data {source.data_date}; licence: {source.license}")
    kinds = Counter(item.kind for item in report.map.water_objects)
    print(f"  map.water_objects: {len(report.map.water_objects)} {dict(kinds)}")
    for site in report.map.retention_sites:
        print(f"  map.retention_sites: {site.id}: {site.label} ({site.geometry.type})")
    for entry in report.trace:
        if entry.rule_id == "water.nearest" or "ditch" in entry.rule_id:
            print(f"  trace {entry.rule_id}: {entry.result} {entry.values}")
    for cause in report.causes:
        for item in cause.recommendations:
            if item.retention_site is not None or "ditch" in item.id:
                print(f"  recommendation {item.id} (under {cause.id}): {item.text}")
                print(f"    rule: {item.rule}")
    for limitation in report.limitations:
        if any(word in limitation.text for word in WATER_WORDS):
            print(f"  limitation ({limitation.affects}): {limitation.text}")
    print(f"  report {len(answer.content)} bytes")
    return status["state"] == "done" and total_s <= ANALYSIS_BUDGET_S


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", help="base address of a running service")
    parser.add_argument("values", nargs="*", help="parcel identifier, crop, analysis date")
    arguments = parser.parse_args()
    values = (*arguments.values, *DEFAULTS[len(arguments.values):])[:3]
    with api_client(arguments.url) as client:
        ok = run(client, *values)
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

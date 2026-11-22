"""Smoke check of a Report derived with a crop history, live (needs network).

Run from the backend directory:
    python -m tests.smoke.history_smoke [PARCEL_ID [CROP_ID [ANALYSIS_DATE]]]
    python -m tests.smoke.history_smoke --url http://127.0.0.1:8000 [...]

Runs one ordinary analysis, then asks for a Report derived from it with a
crop history that names the third and the fourth year of the multi-year
window as the field without a crop. Prints the time of the derive call, the
crop history assumption and the historical course of the new Report. Exits
with 1 when the analysis fails, the susceptibility or another part that must
not depend on the history differs, the new Report does not name its source,
or the first Report changed.
"""

import argparse
import sys
import time

from app.contracts.report import Report
from tests.smoke.analysis_smoke import api_client
from tests.smoke.season_smoke import wait

DEFAULTS = ("040704_2.0020.34/2", "winter_wheat", "2023-06-20")
SAME_PARTS = ("headline", "current_status", "causes", "irrigation", "consistency_check",
              "limitations", "sources")


def same_verdicts(first: Report, second: Report) -> bool:
    ignored = {"history_assumption"}
    before = first.multiyear_susceptibility.model_dump(exclude=ignored)
    after = second.multiyear_susceptibility.model_dump(exclude=ignored)
    different = [part for part in SAME_PARTS if getattr(first, part) != getattr(second, part)]
    print(f"susceptibility identical: {before == after}; other parts that differ: {different}")
    return before == after and not different


def run(client, parcel_id: str, crop_id: str, analysis_date: str) -> bool:
    request = {"parcel_id": parcel_id, "crop_id": crop_id, "analysis_date": analysis_date}
    response = client.post("/api/analyses", json=request)
    if response.status_code != 202:
        print(f"NOT ACCEPTED: {response.status_code} {response.text}")
        return False
    first_id = response.json()["report_id"]
    first = wait(client, first_id)
    if first is None:
        return False
    multiyear = first[1].multiyear_susceptibility
    print(f"susceptibility: {multiyear.deficit_years}/{multiyear.total_years}, "
          f"confidence {multiyear.confidence.level}")
    print(f"assumption: {multiyear.history_assumption}")
    print(f"historical course: {first[1].historical_course}")
    if len(multiyear.years) < 4:
        print("the window has fewer than four years")
        return False

    named = {str(year.year): "bare_field" for year in multiyear.years[2:4]}
    print(f"--- derive with {named} ---")
    started = time.monotonic()
    response = client.post(
        f"/api/reports/{first_id}/derive", json={"crop_history": {"years": named}}
    )
    print(f"answer: {response.status_code} {response.text} in {time.monotonic() - started:.3f} s")
    if response.status_code != 201:
        return False
    answer = client.get(f"/api/reports/{response.json()['report_id']}")
    if answer.status_code != 200:
        print(f"NO REPORT: {answer.status_code} {answer.text}")
        return False
    second = Report.model_validate(answer.json())
    print(f"derived from source: {second.meta.derived_from == first_id}")
    print(f"assumption: {second.multiyear_susceptibility.history_assumption}")
    if second.historical_course is None:
        print("NO HISTORICAL COURSE")
        return False
    for year in second.historical_course.years:
        print(f"  {year.year} | {year.crop.name} | deficit={year.deficit} | {year.satellite_note}")
    print(f"comparison: {second.historical_course.comparison_sentence}")
    unchanged = client.get(f"/api/reports/{first_id}").content == first[0]
    print(f"first report unchanged: {unchanged}")
    return unchanged and second.meta.derived_from == first_id and same_verdicts(first[1], second)


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

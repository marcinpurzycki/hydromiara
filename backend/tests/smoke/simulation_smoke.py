"""Smoke check of the simulation of a Report from a live analysis (needs network).

Run from the backend directory:
    python -m tests.smoke.simulation_smoke [PARCEL_ID [CROP_ID [ANALYSIS_DATE]]]
    python -m tests.smoke.simulation_smoke --url http://127.0.0.1:8000 [...]
    python -m tests.smoke.simulation_smoke --made-up-crops 20 [...]

Runs one analysis, then asks for the crop ranking and for the comparison with
every other position of the crop list, and prints the answers word for word
with their times. `--made-up-crops N` (only without --url) adds N made-up crops
to the crop list of this process, to time a ranking over a full list; their
values are not agronomic data. Exits with 1 when the analysis fails, the
ranking does not answer, the current crop differs from the Report, an answer
takes 2 s or longer, or the Report changed.
"""

import argparse
import sys
import time

from app.catalog.crops import list_crops
from app.contracts.report import Report
from tests.smoke.analysis_smoke import api_client
from tests.smoke.season_smoke import wait

DEFAULTS = ("040704_2.0020.34/2", "winter_wheat", "2023-06-20")
ANSWER_LIMIT_S = 2.0
REPEATS = 5


def timed(client, url: str, **params: str):
    """The answer and the times of `REPEATS` requests, shortest first."""
    times = []
    for _ in range(REPEATS):
        started = time.perf_counter()
        response = client.get(url, params=params)
        times.append(time.perf_counter() - started)
    times.sort()
    print(f"GET {url} {params or ''} -> {response.status_code}")
    print(f"  times s: min {times[0]:.3f}, median {times[len(times) // 2]:.3f}, max {times[-1]:.3f}")
    print(f"  {response.text}")
    return response, times[-1]


def run(client, crop_ids: list[str], parcel_id: str, crop_id: str, analysis_date: str) -> bool:
    request = {"parcel_id": parcel_id, "crop_id": crop_id, "analysis_date": analysis_date}
    response = client.post("/api/analyses", json=request)
    if response.status_code != 202:
        print(f"NOT ACCEPTED: {response.status_code} {response.text}")
        return False
    report_id = response.json()["report_id"]
    stored = wait(client, report_id)
    if stored is None:
        return False
    raw, report = stored
    multiyear = report.multiyear_susceptibility
    print(f"report: {multiyear.deficit_years} of {multiyear.total_years} years, "
          f"level {multiyear.deficit_level}")

    base = f"/api/reports/{report_id}/simulation"
    ranking, slowest = timed(client, f"{base}/ranking")
    if ranking.status_code != 200:
        # The field without a crop has no simulation; anything else is a failure.
        return ranking.status_code == 409 and report.meta.crop.id == "bare_field"
    current = ranking.json()["current"]
    same = (current["deficit_years"], current["total_years"], current["deficit_level"]) == (
        multiyear.deficit_years, multiyear.total_years, multiyear.deficit_level
    )
    print(f"current crop equals the Report: {same}")
    for other in crop_ids:
        if other != crop_id:
            _, longest = timed(client, f"{base}/compare", crop_id=other)
            slowest = max(slowest, longest)
    unchanged = client.get(f"/api/reports/{report_id}").content == raw
    print(f"report unchanged: {unchanged}; slowest answer {slowest:.3f} s")
    return same and unchanged and slowest < ANSWER_LIMIT_S


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", help="base address of a running service")
    parser.add_argument("--made-up-crops", type=int, default=0, help="extra crops, for timing")
    parser.add_argument("values", nargs="*", help="parcel identifier, crop, analysis date")
    arguments = parser.parse_args()
    values = (*arguments.values, *DEFAULTS[len(arguments.values):])[:3]
    crops = list(list_crops())
    if arguments.made_up_crops and not arguments.url:
        from app.api import simulation as routes
        from tests.simulation_helpers import many_crops

        crops += many_crops(arguments.made_up_crops)
        routes.list_crops = lambda: tuple(crops)
        print(f"crop list of this process: {len(crops)} positions, "
              f"{arguments.made_up_crops} of them made up for timing")
    with api_client(arguments.url) as client:
        ok = run(client, [crop.id for crop in crops][:4], *values)
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

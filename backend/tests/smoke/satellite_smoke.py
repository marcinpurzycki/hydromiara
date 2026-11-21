"""Smoke check against the live scene catalogue and scene files (needs network).

Run from the backend directory:  python -m tests.smoke.satellite_smoke
For one parcel outline and three analysis dates (two historical, today) runs
the adapter and prints the time taken, the service that answered, the scenes
read and what is missing. This is done for the configured order of services,
for each service alone, and with a fallback time too short for the primary
service, so that the switch to the secondary one is exercised.
Exits with 1 when a call returns neither scenes nor a reason, returns a scene
after the analysis date, or takes clearly longer than its time budget.
"""

import asyncio
import sys
from datetime import date

from app.contracts.common import GeoJsonGeometry
from app.sources import satellite_params as params
from app.sources.satellite import SatelliteSource
from app.sources.satellite_providers import PROVIDERS, configured_chain

# Outline of an arable parcel of about 2.5 ha (longitude, latitude).
OUTLINE = GeoJsonGeometry(
    type="Polygon",
    coordinates=[
        [
            [18.2024467151364, 52.749196783764],
            [18.2003168413755, 52.7502632828683],
            [18.1991119805698, 52.7494166763537],
            [18.201060596431, 52.7484852200819],
            [18.2016203684626, 52.7482176279139],
            [18.2024467151364, 52.749196783764],
        ]
    ],
)

# Seconds allowed past the budget for cancelling and building the answer.
BUDGET_SLACK_S = 1.0


async def check(source: SatelliteSource, analysis_date: date) -> bool:
    data, outcome, limitations = await source.fetch(OUTLINE, analysis_date)
    scenes = data.scenes if data else []
    print(
        f"analysis date {analysis_date}  {outcome.duration_s:5.2f} s  {len(scenes)} scene(s)  "
        f"step {outcome.chain_step}: {outcome.source_name}"
    )
    for scene in scenes:
        print(
            f"  {scene.date}  clear {scene.clear_share_pct:5.1f}%  "
            f"NDVI {scene.ndvi}  NDMI {scene.ndmi}"
        )
    for limitation in limitations:
        print(f"  limitation ({limitation.affects}): {limitation.text}")
    explained = bool(scenes) or bool(limitations)
    no_future = all(scene.date <= analysis_date for scene in scenes)
    in_budget = outcome.duration_s <= params.TIME_BUDGET_S + BUDGET_SLACK_S
    return explained and no_future and in_budget and outcome.ok == bool(scenes)


async def main() -> int:
    days = (date(2023, 6, 20), date(2019, 6, 15), date.today())
    chain = configured_chain()
    runs = {"configured order: " + " -> ".join(p.name for p in chain): SatelliteSource()}
    for provider in PROVIDERS.values():
        runs[f"{provider.name} alone"] = SatelliteSource(providers=[provider])
    runs["fallback after 0.05 s"] = SatelliteSource(fallback_after_s=0.05)
    results = []
    for title, source in runs.items():
        print(f"== {title}")
        results += [await check(source, day) for day in days]
    print("OK" if all(results) else "FAILED")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

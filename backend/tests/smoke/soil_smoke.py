"""Smoke check against the live soil service (needs network, takes about a minute).

Run from the backend directory:  python -m tests.smoke.soil_smoke
Asks for a field point, which must give a full profile, and for a point at
sea, which must give no data. Prints the time of each answer and marks the
ones slower than the adapter's default time limit; the check itself waits
longer, so that a slow service still shows what it returns. The service
allows 5 calls per minute, so the two calls are spaced apart. Exits with 1
when either point behaves differently or the service does not answer at all.
"""

import asyncio
import sys

from app.sources import soil_params as params
from app.sources.soil import NO_DATA_TEXT, SoilSource
from app.sources.soil_water import available_water_capacity

FIELD = (52.75, 18.2)
SEA = (55.0, 18.8)
PAUSE_S = 13
SMOKE_TIMEOUT_S = 90.0


async def check(source: SoilSource, lat: float, lon: float, expect_data: bool) -> bool:
    data, outcome, limitations = await source.fetch(lat, lon)
    slow = " (over the default limit)" if outcome.duration_s > params.TIMEOUT_S else ""
    print(f"point {lat}, {lon}  {outcome.duration_s:5.2f} s{slow}", end="  ")
    if data is None:
        print(f"NO DATA: {outcome.message}")
        return not expect_data and outcome.message == NO_DATA_TEXT
    capacity = available_water_capacity(data)
    print(f"{len(data.layers)} layers, sand {data.layers[0].sand_pct} % in the top layer", end="")
    if capacity is not None:
        print(f", available water {capacity.total_mm:.0f} mm in {capacity.covered_cm:g} cm")
    else:
        print(", no water contents")
    for limitation in limitations:
        print(f"  limitation ({limitation.affects}): {limitation.text}")
    return expect_data and capacity is not None and capacity.complete


async def main() -> int:
    source = SoilSource(timeout_s=SMOKE_TIMEOUT_S)
    field_ok = await check(source, *FIELD, expect_data=True)
    await asyncio.sleep(PAUSE_S)
    sea_ok = await check(source, *SEA, expect_data=False)
    print("OK" if field_ok and sea_ok else "FAILED")
    return 0 if field_ok and sea_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

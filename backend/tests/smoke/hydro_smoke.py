"""Smoke check of the water adapter against the live class files (needs network).

Run from the backend directory:  python -m tests.smoke.hydro_smoke
    python -m tests.smoke.hydro_smoke 040704_2.0020.34/2 022003_5.0007.170/4

For each parcel fetches the outline from the parcel service and then the
water objects around it, and prints which chain link answered, the time, the
number of HTTP requests and bytes of the live read, the objects by kind and
the nearest one of each kind with its distance from the parcel outline. At
the end prints the peak memory of the process. Exits with 1 when a parcel got
no water data; an empty list of objects is a normal result.
"""

import asyncio
import resource
import sys
from collections import Counter

from shapely.geometry import shape

from app.sources.hydro import HydroSource, LiveBdot
from app.sources.hydro_select import outline_in_file_crs
from app.sources.parcels import ParcelSource

PARCELS = ("040704_2.0020.34/2", "022003_5.0007.170/4")


async def check(live: LiveBdot, source: HydroSource, parcel_id: str) -> bool:
    parcel, parcel_outcome = await ParcelSource().fetch(parcel_id)
    if parcel is None:
        print(f"{parcel_id}: NO PARCEL: {parcel_outcome.message}")
        return False
    data, outcome, limitations = await source.fetch(parcel.parcel_id, parcel.geometry)
    print(f"{parcel_id}: {outcome.duration_s:.2f} s", end="  ")
    if data is None:
        print(f"NO DATA: {outcome.message}")
        return False
    print(
        f"{outcome.source_name} (chain step {outcome.chain_step}, data of {outcome.data_date}), "
        f"{live.last_requests} requests, {live.last_bytes / 1e6:.1f} MB, "
        f"{len(data.objects)} objects"
    )
    outline = outline_in_file_crs(shape(parcel.geometry.model_dump()))
    kinds = Counter(item.kind for item in data.objects)
    nearest: dict[str, tuple[float, str | None]] = {}
    for item in data.objects:
        geometry = outline_in_file_crs(shape(item.geometry.model_dump()))
        distance = outline.distance(geometry)
        if item.kind not in nearest or distance < nearest[item.kind][0]:
            nearest[item.kind] = (distance, item.name)
    for kind, count in sorted(kinds.items()):
        distance, name = nearest[kind]
        print(f"  {kind:12s} {count:3d}  nearest {distance:6.1f} m  {name or ''}")
    if outcome.message:
        print(f"  note: {outcome.message}")
    print(f"  limitations: {len(limitations)}")
    return True


async def main(parcel_ids: tuple[str, ...]) -> int:
    live = LiveBdot()
    source = HydroSource(links=[live])
    before_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    results = [await check(live, source, parcel_id) for parcel_id in parcel_ids]
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(f"peak memory of the process: {peak_mb:.0f} MB ({before_mb:.0f} MB before the reads)")
    print("OK" if all(results) else "FAILED")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(tuple(sys.argv[1:]) or PARCELS)))

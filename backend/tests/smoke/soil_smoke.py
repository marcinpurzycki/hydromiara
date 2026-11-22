"""Smoke check against the two live soil services (needs network).

Run from the backend directory:  python -m tests.smoke.soil_smoke [--runs 3]
For three parcels in different regions (fetched from the parcel service)
reads the soil several times and prints which chain link answered, the time,
the categories found at the parcel points, the estimated category and the
water capacity the balance would use. Also reads the category map alone and
the texture maps alone, so that each link is seen even when the first one
answers. Exits with 1 when a parcel that should have soil data gets none, or
when a service does not answer.
"""

import argparse
import asyncio
import sys
import time

from app.contracts.source_data import SoilData
from app.engine.params import FALLBACK_AVAILABLE_WATER_MM_PER_M
from app.engine.soil_capacity import CATEGORY_LABELS, estimated_category, soil_capacity
from app.sources.chain import LinkFailed
from app.sources.parcels import ParcelSource
from app.sources.raster import as_geometry
from app.sources.soil import SoilSource
from app.sources.soil_category import CategoryMap
from app.sources.soil_points import sample_points
from app.sources.soil_texture import TextureMaps

# Parcel -> whether soil data are expected. The second one is a small parcel in
# a town: the category map gives it no category (value 11 when recorded) and
# the texture maps are masked there, so the right result is no data from both.
PARCELS = {"040704_2.0020.34/2": True, "141201_1.0001.6509": False, "060405_2.0223.756": True}


def describe(data: SoilData) -> str:
    capacity = soil_capacity(data, FALLBACK_AVAILABLE_WATER_MM_PER_M)
    categories = ", ".join(
        f"{CATEGORY_LABELS[c.category]} {c.share_pct:g}%" for c in data.drought_categories or []
    )
    other = ", ".join(f"code {a.code} {a.share_pct:g}%" for a in data.unclassified_areas or [])
    estimate = estimated_category(data)
    return (
        f"{capacity.source}, {capacity.mm_per_m:.0f} mm/m | map: {categories or '-'}"
        f"{' | ' + other if other else ''} | estimated: "
        f"{CATEGORY_LABELS[estimate] if estimate else '-'}"
    )


async def timed(call) -> tuple[float, object]:
    started = time.monotonic()
    try:
        result = await call
    except LinkFailed as failure:
        result = failure
    return time.monotonic() - started, result


async def check(parcel_id: str, runs: int, expect_data: bool) -> bool:
    parcel = await ParcelSource().by_id(parcel_id)
    if parcel is None:
        print(f"{parcel_id}: parcel not found")
        return False
    points = sample_points(as_geometry(parcel.geometry))
    centre = (parcel.centroid_lon, parcel.centroid_lat)
    print(f"{parcel_id} ({parcel.area_ha:.2f} ha, {len(points)} points)")
    ok = True
    for run in range(1, runs + 1):
        data, outcome = await SoilSource().fetch(parcel.geometry, *centre)
        line = f"  run {run}: chain {outcome.duration_s:5.2f} s, "
        if data is None:
            ok = ok and not expect_data and "nie odpowiedzia" not in (outcome.message or "")
            print(line + f"NO DATA: {outcome.message}")
        else:
            print(line + f"link {outcome.chain_step} ({outcome.source_name}), {describe(data)}")
            if outcome.message:
                print(f"         note: {outcome.message}")
        map_s, shares = await timed(CategoryMap().read(points))
        texture_s, layers = await timed(TextureMaps().read(*centre))
        texture = f"{len(layers)} layers" if isinstance(layers, list) else f"none ({layers})"
        map_result = f"none ({shares})"
        if isinstance(shares, tuple):
            map_result = describe(SoilData(layers=[], drought_categories=shares[0],
                                           unclassified_areas=shares[1])).split(" | ", 1)[1]
        print(f"         alone: category map {map_s:.2f} s {map_result}, "
              f"texture maps {texture_s:.2f} s {texture}")
    return ok


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=3, help="reads of every parcel")
    parser.add_argument("--parcel", action="append", help="parcel identifier; repeatable")
    arguments = parser.parse_args()
    results = [
        await check(parcel_id, arguments.runs, PARCELS.get(parcel_id, True))
        for parcel_id in arguments.parcel or PARCELS
    ]
    print("OK" if all(results) else "FAILED")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

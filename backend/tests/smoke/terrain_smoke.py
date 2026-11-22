"""Smoke check against the live elevation sources (needs network).

Run from the backend directory:
    python -m tests.smoke.terrain_smoke
    python -m tests.smoke.terrain_smoke --parcel 040704_2.0020.34/2 --parcel 141201_1.0001.6509

For every parcel fetches the outline, then the elevation grid from the whole
chain and from the 30 m link alone, and prints for both: which link answered,
the time, the number of grid points, the share with a height, and the slope,
downhill direction and lowest part from the terrain analysis. Exits with 1
when a grid is missing; the point service not answering is reported, not hidden.
"""

import argparse
import asyncio
import sys

from app.engine.terrain_analysis import analyse_terrain
from app.sources.parcels import ParcelSource
from app.sources.terrain import TerrainSource
from app.sources.terrain_copernicus import CopernicusDem30

PARCELS = ("040704_2.0020.34/2", "141201_1.0001.6509", "060405_2.0223.756")


async def check(label: str, source: TerrainSource, parcel) -> bool:
    data, outcome = await source.fetch(parcel.geometry)
    print(f"  {label:9s} {outcome.duration_s:5.2f} s", end="  ")
    if data is None:
        print(f"NO DATA: {outcome.message}")
        return False
    values = [value for row in data.elevations_m for value in row]
    known = [value for value in values if value is not None]
    result = analyse_terrain(data, parcel.geometry)
    print(
        f"step {outcome.chain_step}, {data.resolution_m:g} m, {data.crs}, {len(values)} points "
        f"({100 * len(known) / len(values):.0f}% with a height), "
        f"{min(known):.1f}..{max(known):.1f} m"
    )
    print(f"            {outcome.source_name}")
    if result.analysed:
        azimuth = result.downhill_azimuth_deg
        print(
            f"            slope {result.slope_pct:.2f}% +- {result.slope_error_pct:.2f}, downhill "
            f"{'unresolved' if azimuth is None else f'{azimuth:.1f} deg ({result.downhill_label})'}"
            f", lowest part: {result.lowest_part}, cells inside {result.cells_used}"
        )
    else:
        print(f"            not analysed: {result.status}, cells inside {result.cells_used}")
    if outcome.message:
        print(f"            note: {outcome.message}")
    return bool(known)


async def main(parcel_ids: list[str]) -> int:
    chain, coarse = TerrainSource(), TerrainSource(links=[CopernicusDem30()])
    results = []
    for parcel_id in parcel_ids:
        parcel = await ParcelSource().by_id(parcel_id)
        print(f"{parcel_id} ({parcel.area_ha:.2f} ha)")
        results.append(await check("chain", chain, parcel))
        results.append(await check("30 m only", coarse, parcel))
    print("OK" if all(results) else "FAILED")
    return 0 if all(results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--parcel", action="append")
    sys.exit(asyncio.run(main(parser.parse_args().parcel or list(PARCELS))))

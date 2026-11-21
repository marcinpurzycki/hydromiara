"""Smoke check against the live elevation model (needs network).

Run from the backend directory:  python -m tests.smoke.terrain_smoke
For four parcel-sized outlines in different parts of Poland fetches the
elevation grid and prints which chain link answered, the grid size, the
elevation range and the time. Exits with 1 when a grid is missing or empty.
"""

import asyncio
import sys

from shapely.geometry import box

from app.sources.terrain import TerrainSource

# Rectangles of two to five hectares: lowland, foothills, lake district, and
# one lying across the edge of two tiles (a note about it is expected).
OUTLINES = {
    "Kujawy": box(18.1995, 52.7483, 18.2025, 52.7503),
    "Podkarpacie": box(22.3480, 49.6480, 22.3510, 49.6500),
    "Warmia": box(20.4980, 53.8490, 20.5010, 53.8508),
    "tile edge": box(20.4980, 53.9990, 20.5010, 54.0008),
}


async def check(source: TerrainSource, label: str, outline) -> bool:
    data, outcome = await source.fetch(outline)
    print(f"{label:12s} {outcome.duration_s:5.2f} s", end="  ")
    if data is None:
        print(f"NO DATA: {outcome.message}")
        return False
    cells = [value for row in data.elevations_m for value in row if value is not None]
    rows, cols = len(data.elevations_m), len(data.elevations_m[0])
    print(
        f"{outcome.source_name} (chain step {outcome.chain_step}, {data.resolution_m:g} m), "
        f"{rows} x {cols} cells, {min(cells):.1f}..{max(cells):.1f} m, {data.crs}"
    )
    if outcome.message:
        print(f"  note: {outcome.message}")
    return bool(cells) and rows > 1 and cols > 1


async def main() -> int:
    source = TerrainSource()
    results = [await check(source, label, outline) for label, outline in OUTLINES.items()]
    print("OK" if all(results) else "FAILED")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

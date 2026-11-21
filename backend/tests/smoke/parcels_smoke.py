"""Smoke check against the live parcel service (needs network).

Run from the backend directory:  python -m tests.smoke.parcels_smoke
For three real parcels: lookup by identifier, by the centre point of the parcel
and by number with region name. Exits with 1 when any check fails.
"""

import asyncio
import sys
import time

from app.sources.parcels import ParcelSource

PARCEL_IDS = ["040704_2.0020.34/2", "141201_1.0001.6509", "060405_2.0223.756"]


async def _timed(label: str, call):
    started = time.monotonic()
    result = await call
    print(f"  {label:<12} {time.monotonic() - started:5.2f} s", end="  ")
    return result


async def check(source: ParcelSource, parcel_id: str) -> bool:
    print(parcel_id)
    parcel = await _timed("by id", source.by_id(parcel_id))
    if parcel is None:
        print("NOT FOUND")
        return False
    print(f"{parcel.region} {parcel.number}, {parcel.commune}, {parcel.area_ha} ha")

    at = await _timed("by point", source.at(parcel.centroid_lon, parcel.centroid_lat))
    at_ok = at is not None and at.parcel_id == parcel_id
    print("ok" if at_ok else f"MISMATCH: {at.parcel_id if at else None}")

    found = await _timed("by number", source.search(f"{parcel.number}, {parcel.region}"))
    search_ok = parcel_id in {match.parcel_id for match in found}
    print(f"{len(found)} match(es), " + ("ok" if search_ok else "PARCEL MISSING"))
    return at_ok and search_ok


async def main() -> int:
    source = ParcelSource()
    results = [await check(source, parcel_id) for parcel_id in PARCEL_IDS]
    print("OK" if all(results) else "FAILED")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

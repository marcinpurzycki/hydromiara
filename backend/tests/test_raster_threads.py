"""Outline masks computed from many threads at once, no network."""

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
from rasterio.transform import from_origin
from shapely.geometry import box

from app.sources import raster

THREADS = 12
CALLS_PER_THREAD = 500
SHAPE = (40, 40)


def _masks(count, geometry, transform):
    return [raster.outline_mask(geometry, SHAPE, transform) for _ in range(count)]


# Any warning raised in a worker thread fails the test: it comes back as an
# exception from the thread result.
@pytest.mark.filterwarnings("error")
def test_outline_mask_from_many_threads_matches_the_reference():
    transform = from_origin(500_000.0, 5_800_000.0, 10.0, 10.0)
    # Columns 10-19 and rows 20-29 of the grid, given in its coordinates.
    geometry = box(500_100.0, 5_799_700.0, 500_200.0, 5_799_800.0)
    reference = np.zeros(SHAPE, dtype=bool)
    reference[20:30, 10:20] = True

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        jobs = [
            pool.submit(_masks, CALLS_PER_THREAD, geometry, transform) for _ in range(THREADS)
        ]
        masks = [mask for job in jobs for mask in job.result()]

    assert len(masks) == THREADS * CALLS_PER_THREAD
    assert all(np.array_equal(mask, reference) for mask in masks)

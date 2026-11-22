"""The two interchangeable services that serve the same Sentinel-2 L2A archive.

Both offer a scene catalogue (STAC API) and the scene files as cloud-optimised
GeoTIFFs; they differ in addresses, file names, how files are opened and how
stored values turn into reflectance. Which one is asked first is project
configuration (environment variables below); the other one takes over when
the first gives no result in time.
"""

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.sources import satellite_params as params

# Since processing baseline 04.00 the product stores reflectance shifted by
# 1000 digital numbers (ESA, Sentinel-2 processing baseline 04.00, 25.01.2022).
SHIFTED_BASELINE = "04.00"
SHIFT_OFFSET = -1000 * params.REFLECTANCE_SCALE


def _baseline(properties: Mapping[str, Any]) -> str | None:
    value = properties.get("s2:processing_baseline")
    return value if isinstance(value, str) and value else None


def planetary_computer_offset(properties: Mapping[str, Any]) -> float | None:
    """Files keep the product values: the shift applies from baseline 04.00 on."""
    baseline = _baseline(properties)
    if baseline is None:
        return None
    return SHIFT_OFFSET if baseline >= SHIFTED_BASELINE else 0.0


def earth_search_offset(properties: Mapping[str, Any]) -> float | None:
    """Files of most scenes already have the shift removed.

    A scene is used when it predates the shift or is flagged as having it
    removed. Other scenes are skipped (None): their files were found both
    with and without the shift, and the catalogue does not tell which.
    """
    baseline = _baseline(properties)
    if baseline is None:
        return None
    if baseline < SHIFTED_BASELINE or properties.get("earthsearch:boa_offset_applied") is True:
        return 0.0
    return None


@dataclass(frozen=True)
class Provider:
    """One catalogue with its scene files."""

    name: str  # value used in the configuration
    source_name: str  # shown in the report
    search_url: str
    token_url: str | None  # where a read token for the files is requested, if needed
    assets: Mapping[str, str]  # layer (satellite_params.ASSET_*) -> file name in the catalogue
    properties: tuple[str, ...]  # scene properties read by `offset`
    tile_property: str  # scene property naming the tile of the fixed tiling grid
    page_limit: int  # scenes per answer page (largest value checked against the service)
    read_workers: int  # scene files read at the same time
    archive_start: date  # first acquisition day the service holds
    archive_note: str  # sentence for the Report about the reach of the archive
    exclude: tuple[str, ...]  # fields left out of the catalogue answer
    offset: Callable[[Mapping[str, Any]], float | None]  # reflectance offset; None = skip scene


_LAYERS = params.REQUIRED_ASSETS

# Earth Search returns every file of a scene unless the unwanted ones are
# excluded by name; this keeps the answer about ten times smaller.
_ES_OTHER = (
    "aot", "blue", "coastal", "green", "nir09", "rededge1", "rededge2", "rededge3",
    "swir22", "visual", "wvp", "granule_metadata", "tileinfo_metadata", "thumbnail",
)  # fmt: skip
_ES_DETAILS = (
    "proj:shape", "proj:transform", "roles", "eo:bands", "title", "type", "gsd", "raster:bands",
)  # fmt: skip

PLANETARY_COMPUTER = Provider(
    name="planetary-computer",
    source_name="Copernicus Sentinel-2 L2A, katalog Planetary Computer",
    search_url="https://planetarycomputer.microsoft.com/api/stac/v1/search",
    token_url="https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-2-l2a",
    assets=dict(zip(_LAYERS, ("SCL", "B04", "B08", "B8A", "B11"), strict=True)),
    properties=("s2:processing_baseline",),
    tile_property="s2:mgrs_tile",
    page_limit=1000,
    read_workers=16,
    archive_start=date(2015, 7, 11),
    archive_note=(
        "Zdjęcia satelitarne Działki są dostępne od lipca 2015 r., a regularnie od 2018 r."
    ),
    exclude=(),
    offset=planetary_computer_offset,
)

EARTH_SEARCH = Provider(
    name="earth-search",
    source_name="Copernicus Sentinel-2 L2A, katalog Earth Search",
    search_url="https://earth-search.aws.element84.com/v1/search",
    token_url=None,
    assets=dict(zip(_LAYERS, _LAYERS, strict=True)),
    properties=("s2:processing_baseline", "earthsearch:boa_offset_applied"),
    tile_property="grid:code",
    # Works only with the reduced answer below; the full one fails from 250 on.
    page_limit=2000,
    # Measured from the target server: 32 threads read 16 scenes in 4.2 s, 16 in 5.5 s.
    read_workers=32,
    archive_start=date(2016, 11, 2),
    archive_note=(
        "Odczyty satelitarne pobrano z usługi zapasowej, która ma zdjęcia dopiero "
        "od listopada 2016 r."
    ),
    exclude=tuple(
        [f"assets.{name}" for name in _ES_OTHER]
        + [f"assets.{name}-jp2" for name in _ES_OTHER + _LAYERS]
        + [f"assets.{layer}.{detail}" for layer in _LAYERS for detail in _ES_DETAILS]
    ),
    offset=earth_search_offset,
)

PROVIDERS = {provider.name: provider for provider in (PLANETARY_COMPUTER, EARTH_SEARCH)}

# --- Project configuration ---------------------------------------------------

PRIMARY_ENV = "SATELLITE_PRIMARY"
SECONDARY_ENV = "SATELLITE_SECONDARY"
FALLBACK_AFTER_ENV = "SATELLITE_FALLBACK_AFTER_S"

# Project decision: Planetary Computer first (files in Europe, the faster one
# from the target server), Earth Search as the replacement.
DEFAULT_PRIMARY = PLANETARY_COMPUTER.name
DEFAULT_SECONDARY = EARTH_SEARCH.name
NO_SECONDARY = "none"

# Seconds the primary service has to deliver its first reading before the
# secondary one is asked instead.
DEFAULT_FALLBACK_AFTER_S = 4.0


def _provider(name: str, variable: str) -> Provider:
    if name not in PROVIDERS:
        known = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"{variable}={name!r}: unknown satellite service; known: {known}")
    return PROVIDERS[name]


def configured_chain(env: Mapping[str, str] | None = None) -> list[Provider]:
    """Services in the order they are asked: the primary, then the secondary if any."""
    env = os.environ if env is None else env
    primary = _provider(env.get(PRIMARY_ENV) or DEFAULT_PRIMARY, PRIMARY_ENV)
    second_name = env.get(SECONDARY_ENV) or DEFAULT_SECONDARY
    if second_name == NO_SECONDARY or second_name == primary.name:
        return [primary]
    return [primary, _provider(second_name, SECONDARY_ENV)]


def configured_fallback_after_s(env: Mapping[str, str] | None = None) -> float:
    """Seconds without a reading after which the secondary service takes over."""
    env = os.environ if env is None else env
    raw = env.get(FALLBACK_AFTER_ENV)
    if not raw:
        return DEFAULT_FALLBACK_AFTER_S
    try:
        value = float(raw)
    except ValueError:
        value = -1.0
    if value <= 0:
        raise ValueError(f"{FALLBACK_AFTER_ENV}={raw!r}: expected a positive number of seconds")
    return value

"""Finding Sentinel-2 scenes over a parcel in a scene catalogue (STAC API).

The catalogue is asked once per search window. Its answer is reduced to what
reading needs (acquisition day, file addresses, reflectance offset), scenes
outside the window are dropped. Choosing one scene per day among overlapping
tiles and reprocessed copies is done in satellite_selection.py.
"""

from dataclasses import dataclass
from datetime import date as Date
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.sources import satellite_params as params
from app.sources.satellite_providers import Provider


class SatelliteSearchError(Exception):
    """The scene catalogue did not answer or answered with something unreadable."""


@dataclass(frozen=True)
class SearchWindow:
    """Inclusive range of acquisition days searched for scenes."""

    start: Date
    end: Date
    # The day the window is built around: the analysis date, or the same day
    # of an earlier year.
    anchor: Date
    # True for the window ending on the analysis date.
    current: bool = True

    @property
    def quota(self) -> int:
        """Clear scenes whose bands are read."""
        return params.CURRENT_SCENES if self.current else params.HISTORY_SCENES_PER_YEAR


@dataclass(frozen=True)
class SceneItem:
    """One catalogued scene: its day and the addresses of the files to read."""

    scene_id: str
    date: Date
    hrefs: dict[str, str]  # layer name -> file address, ready to open
    reflectance_offset: float = 0.0
    tile: str = ""  # tile of the fixed tiling grid the scene is cut to
    baseline: str = ""  # processing version of the scene


def _years_back(day: Date, years: int) -> Date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February in a year that has none
        return day.replace(year=day.year - years, day=28)


def search_windows(analysis_date: Date) -> list[SearchWindow]:
    """Windows to search, the one ending on the analysis date first.

    The current window ends on the analysis date. Each earlier year gets a
    window around the same day of that year; the latest of them ends almost a
    year before the analysis date, so no window reaches past it.
    """
    windows = [
        SearchWindow(
            start=analysis_date - timedelta(days=params.CURRENT_WINDOW_DAYS),
            end=analysis_date,
            anchor=analysis_date,
        )
    ]
    half = timedelta(days=params.HISTORY_HALF_WINDOW_DAYS)
    for years in range(1, params.HISTORY_YEARS + 1):
        anchor = _years_back(analysis_date, years)
        windows.append(
            SearchWindow(start=anchor - half, end=anchor + half, anchor=anchor, current=False)
        )
    return windows


def search_body(provider: Provider, geometry: dict[str, Any], window: SearchWindow) -> dict:
    """Request body: scenes of the collection intersecting the outline in the window."""
    wanted = ["id", "properties.datetime"]
    wanted += [f"properties.{name}" for name in (*provider.properties, provider.tile_property)]
    wanted += [f"assets.{name}.href" for name in provider.assets.values()]
    return {
        "collections": [params.COLLECTION],
        "intersects": geometry,
        "datetime": f"{window.start.isoformat()}T00:00:00Z/{window.end.isoformat()}T23:59:59Z",
        "limit": provider.page_limit,
        "fields": {
            "include": wanted,
            "exclude": ["links", "geometry", "bbox", "stac_extensions", *provider.exclude],
        },
    }


def parse_items(
    payload: object, window: SearchWindow, provider: Provider, token: str | None = None
) -> list[SceneItem]:
    """Scenes of one answer page that lie in the window and can be read.

    A scene is left out when a file is missing or is not served over HTTPS,
    or when its reflectance offset cannot be told. With a read token, every
    file address is signed with it.
    """
    try:
        features = payload["features"]
        items = []
        for feature in features:
            properties = feature["properties"]
            taken = datetime.fromisoformat(properties["datetime"]).date()
            assets = feature.get("assets") or {}
            hrefs = {
                layer: assets[name]["href"]
                for layer, name in provider.assets.items()
                if name in assets
            }
            offset = provider.offset(properties)
            readable = len(hrefs) == len(provider.assets) and all(
                href.startswith("https://") for href in hrefs.values()
            )
            if not readable or offset is None or not window.start <= taken <= window.end:
                continue
            if token:
                hrefs = {layer: f"{href}?{token}" for layer, href in hrefs.items()}
            items.append(
                SceneItem(
                    scene_id=str(feature["id"]),
                    date=taken,
                    hrefs=hrefs,
                    reflectance_offset=offset,
                    tile=str(properties.get(provider.tile_property) or ""),
                    baseline=str(properties.get("s2:processing_baseline") or ""),
                )
            )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise SatelliteSearchError(f"unreadable answer: {type(exc).__name__}") from exc
    return items


def _next_request(payload: dict, body: dict) -> tuple[str, dict] | None:
    """Address and body of the next page, from the `next` link of the answer."""
    for link in payload.get("links") or []:
        if link.get("rel") == "next" and link.get("href"):
            link_body = link.get("body") or {}
            return link["href"], ({**body, **link_body} if link.get("merge") else link_body)
    return None


async def read_token(client: httpx.AsyncClient, provider: Provider) -> tuple[str, datetime]:
    """Read token for the files of a catalogue and the moment it expires."""
    try:
        response = await client.get(provider.token_url)
        response.raise_for_status()
        payload = response.json()
        token = payload["token"]
        expires = datetime.fromisoformat(payload["msft:expiry"])
    except httpx.HTTPError as exc:
        raise SatelliteSearchError(type(exc).__name__) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise SatelliteSearchError("unreadable token answer") from exc
    if not isinstance(token, str) or not token:
        raise SatelliteSearchError("unreadable token answer")
    return token, expires if expires.tzinfo else expires.replace(tzinfo=UTC)


async def find_scenes(
    client: httpx.AsyncClient,
    provider: Provider,
    geometry: dict[str, Any],
    window: SearchWindow,
    token: str | None = None,
) -> list[SceneItem]:
    """Every readable scene over the outline in one window, as the catalogue lists them."""
    url, body = provider.search_url, search_body(provider, geometry, window)
    items: list[SceneItem] = []
    for _ in range(params.SEARCH_MAX_PAGES):
        try:
            response = await client.post(url, json=body)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise SatelliteSearchError(type(exc).__name__) from exc
        except ValueError as exc:
            raise SatelliteSearchError("answer is not JSON") from exc
        if not isinstance(payload, dict):
            raise SatelliteSearchError("unreadable answer: not an object")
        page = parse_items(payload, window, provider, token)
        items.extend(page)
        following = _next_request(payload, body)
        # The catalogue links a next page even after the last one, so a page
        # that is not full ends the search.
        if len(payload["features"]) < provider.page_limit or following is None:
            break
        url, body = following
    return items

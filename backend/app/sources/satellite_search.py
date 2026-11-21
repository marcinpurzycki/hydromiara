"""Finding Sentinel-2 scenes over a parcel in a scene catalogue (STAC API).

The catalogue is asked once per search window. Its answer is reduced to what
reading needs (acquisition day, file addresses, reflectance offset), scenes
after the analysis date are dropped and scenes of the same day (overlapping
tiles, reprocessed copies) are grouped so that only one of them is used.
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


@dataclass(frozen=True)
class SceneItem:
    """One catalogued scene: its day and the addresses of the files to read."""

    scene_id: str
    date: Date
    hrefs: dict[str, str]  # layer name -> file address, ready to open
    reflectance_offset: float = 0.0


def _years_back(day: Date, years: int) -> Date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February in a year that has none
        return day.replace(year=day.year - years, day=28)


def search_windows(analysis_date: Date) -> list[SearchWindow]:
    """Windows to search, the one ending on the analysis date first.

    No window reaches past the analysis date.
    """
    windows = []
    for years in range(params.PREVIOUS_YEARS + 1):
        end = _years_back(analysis_date, years)
        windows.append(SearchWindow(start=end - timedelta(days=params.WINDOW_DAYS), end=end))
    return windows


def search_body(provider: Provider, geometry: dict[str, Any], window: SearchWindow) -> dict:
    """Request body: scenes of the collection intersecting the outline in the window."""
    wanted = ["id", "properties.datetime"]
    wanted += [f"properties.{name}" for name in provider.properties]
    wanted += [f"assets.{name}.href" for name in provider.assets.values()]
    return {
        "collections": [params.COLLECTION],
        "intersects": geometry,
        "datetime": f"{window.start.isoformat()}T00:00:00Z/{window.end.isoformat()}T23:59:59Z",
        "limit": params.SEARCH_PAGE_LIMIT,
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
            items.append(SceneItem(str(feature["id"]), taken, hrefs, offset))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise SatelliteSearchError(f"unreadable answer: {type(exc).__name__}") from exc
    return items


def group_by_day(items: list[SceneItem]) -> list[list[SceneItem]]:
    """Scenes grouped by acquisition day, newest day first.

    Each group lists the copies of one day in a fixed order (scene id,
    descending); the reader uses the first copy that covers the parcel.
    """
    by_day: dict[Date, dict[str, SceneItem]] = {}
    for item in items:
        by_day.setdefault(item.date, {})[item.scene_id] = item
    return [
        [copies[scene_id] for scene_id in sorted(copies, reverse=True)]
        for _, copies in sorted(by_day.items(), reverse=True)
    ]


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
) -> list[list[SceneItem]]:
    """Scenes over the outline in one window, grouped by day, newest first."""
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
        if len(payload["features"]) < params.SEARCH_PAGE_LIMIT or following is None:
            break
        url, body = following
    return group_by_day(items)

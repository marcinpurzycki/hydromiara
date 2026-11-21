"""Finding Sentinel-2 scenes over a parcel in the scene catalogue (STAC API).

The catalogue is asked once per search window. Its answer is reduced to what
reading needs (acquisition day and file addresses), scenes after the analysis
date are dropped and scenes of the same day (overlapping tiles, reprocessed
copies) are grouped so that only one of them is used.
"""

from dataclasses import dataclass
from datetime import date as Date
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.sources import satellite_params as params


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
    hrefs: dict[str, str]  # asset name -> file address


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


def search_body(geometry: dict[str, Any], window: SearchWindow) -> dict[str, Any]:
    """Request body: scenes of the collection intersecting the outline in the window."""
    return {
        "collections": [params.COLLECTION],
        "intersects": geometry,
        "datetime": f"{window.start.isoformat()}T00:00:00Z/{window.end.isoformat()}T23:59:59Z",
        "limit": params.SEARCH_PAGE_LIMIT,
        # Narrows the scene properties to the one that is read; the catalogue
        # keeps the file list in its default set of fields.
        "fields": {"include": ["id", "properties.datetime"]},
    }


def parse_items(payload: object, window: SearchWindow) -> list[SceneItem]:
    """Scenes of one answer page that lie in the window and have all files."""
    try:
        features = payload["features"]
        items = []
        for feature in features:
            taken = datetime.fromisoformat(feature["properties"]["datetime"]).date()
            assets = feature.get("assets") or {}
            hrefs = {
                name: assets[name]["href"] for name in params.REQUIRED_ASSETS if name in assets
            }
            if len(hrefs) < len(params.REQUIRED_ASSETS) or not window.start <= taken <= window.end:
                continue
            items.append(SceneItem(scene_id=str(feature["id"]), date=taken, hrefs=hrefs))
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


async def find_scenes(
    client: httpx.AsyncClient, geometry: dict[str, Any], window: SearchWindow
) -> list[list[SceneItem]]:
    """Scenes over the outline in one window, grouped by day, newest first."""
    url, body = params.SEARCH_URL, search_body(geometry, window)
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
        page = parse_items(payload, window)
        items.extend(page)
        following = _next_request(payload, body)
        # The catalogue links a next page even after the last one, so a page
        # that is not full ends the search.
        if len(payload["features"]) < params.SEARCH_PAGE_LIMIT or following is None:
            break
        url, body = following
    return group_by_day(items)

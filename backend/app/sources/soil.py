"""Soil profile of a point from the SoilGrids point query.

One request returns texture, organic carbon and volumetric water content at
33 and 1500 kPa for the standard depth layers. The whole request has a time
limit, because the service is slow and at times unavailable. Every profile
comes with the permanent limitation that its water capacity is unverified;
missing values are reported instead of being filled.
"""

import asyncio
import time
from datetime import UTC, datetime
from typing import NamedTuple

import httpx
from pydantic import ValidationError

from app.contracts.report import Limitation
from app.contracts.source_data import SoilData, SoilLayer, SourceOutcome
from app.sources import soil_params as params

NO_ANSWER_TEXT = (
    "Źródło danych o glebie nie odpowiedziało w wyznaczonym czasie "
    "albo odpowiedziało nieczytelnie."
)
NO_DATA_TEXT = (
    "Źródło danych o glebie nie ma wartości dla tego punktu (np. woda albo teren zabudowany)."
)


class SoilSourceError(Exception):
    """The soil service did not answer in time or answered with something unreadable."""


class SoilNoDataError(SoilSourceError):
    """The service answered, but has no value for this point."""


class SoilFetch(NamedTuple):
    """Soil for one analysis, how it was obtained and what limits its use."""

    data: SoilData | None
    outcome: SourceOutcome
    limitations: list[Limitation]


def parse_response(payload: object) -> SoilData:
    """Layers from one answer, top to bottom, in conventional units.

    A value the answer lacks or gives as null stays None. An answer in which
    every value is null means the point has no data.
    """
    by_property = {name: field for field, name in params.PROPERTIES.items()}
    layers: dict[tuple[float, float], dict[str, float | None]] = {}
    try:
        for entry in payload["properties"]["layers"]:
            field = by_property.get(entry["name"])
            if field is None:
                continue
            divisor = float(entry["unit_measure"]["d_factor"])
            if divisor <= 0:
                raise ValueError("divisor is not positive")
            for depth in entry["depths"]:
                bounds = depth["range"]
                if bounds["unit_depth"] != "cm":
                    raise ValueError("depth is not in centimetres")
                key = (float(bounds["top_depth"]), float(bounds["bottom_depth"]))
                value = depth["values"][params.VALUE_STATISTIC]
                layers.setdefault(key, {})[field] = None if value is None else value / divisor
        profile = SoilData(
            layers=[
                SoilLayer(
                    top_cm=top,
                    bottom_cm=bottom,
                    **{field: values.get(field) for field in params.PROPERTIES},
                )
                for (top, bottom), values in sorted(layers.items())
            ]
        )
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise SoilSourceError(f"unreadable answer: {type(exc).__name__}") from exc

    if not profile.layers:
        raise SoilSourceError("answer has no layers")
    if all(
        getattr(layer, field) is None for layer in profile.layers for field in params.PROPERTIES
    ):
        raise SoilNoDataError("every value is null")
    return profile


def _layers_pl(layers: list[SoilLayer]) -> str:
    return ", ".join(f"{layer.top_cm:g}–{layer.bottom_cm:g} cm" for layer in layers)


def find_limitations(data: SoilData) -> list[Limitation]:
    """The permanent limitation of the source plus gaps of this profile."""
    limitations = [
        Limitation(text=params.UNVERIFIED_CAPACITY_TEXT, affects="all", permanent=True)
    ]
    no_water = [
        layer
        for layer in data.layers
        if any(getattr(layer, field) is None for field in params.WATER_FIELDS)
    ]
    if no_water:
        limitations.append(
            Limitation(
                text=(
                    "W danych o glebie brakuje zawartości wody dla warstw: "
                    f"{_layers_pl(no_water)}. Pojemność wodna gleby jest policzona "
                    "tylko z pozostałych warstw."
                ),
                affects="all",
                permanent=False,
            )
        )
    other_fields = [field for field in params.PROPERTIES if field not in params.WATER_FIELDS]
    no_texture = [
        layer for layer in data.layers if any(getattr(layer, f) is None for f in other_fields)
    ]
    if no_texture:
        limitations.append(
            Limitation(
                text=(
                    "W danych o glebie brakuje uziarnienia lub węgla organicznego "
                    f"dla warstw: {_layers_pl(no_texture)}."
                ),
                affects="recommendations",
                permanent=False,
            )
        )
    return limitations


class SoilSource:
    """Soil profile for a point."""

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = params.TIMEOUT_S,
    ) -> None:
        self._transport = transport
        self._timeout_s = timeout_s

    async def profile(self, lat: float, lon: float) -> SoilData:
        """Layers of the grid cell containing the point; raises SoilSourceError."""
        query = {
            "lon": f"{lon:.5f}",
            "lat": f"{lat:.5f}",
            "property": list(params.PROPERTIES.values()),
            "depth": list(params.DEPTHS),
            "value": params.VALUE_STATISTIC,
        }
        try:
            # The client timeout limits each phase of the exchange; the outer
            # one limits the request as a whole.
            async with asyncio.timeout(self._timeout_s):
                async with httpx.AsyncClient(
                    transport=self._transport,
                    timeout=self._timeout_s,
                    headers={"User-Agent": params.USER_AGENT},
                ) as client:
                    response = await client.get(params.QUERY_URL, params=query)
                    response.raise_for_status()
                    payload = response.json()
        except (httpx.HTTPError, TimeoutError) as exc:
            raise SoilSourceError(type(exc).__name__) from exc
        except ValueError as exc:
            raise SoilSourceError("answer is not JSON") from exc
        return parse_response(payload)

    async def fetch(self, lat: float, lon: float) -> SoilFetch:
        """Soil for an analysis: the profile, its outcome record and its limitations."""
        started = time.monotonic()
        data, message, limitations = None, None, []
        try:
            data = await self.profile(lat, lon)
            limitations = find_limitations(data)
            message = " ".join(limitation.text for limitation in limitations)
        except SoilNoDataError:
            message = NO_DATA_TEXT
        except SoilSourceError:
            message = NO_ANSWER_TEXT
        outcome = SourceOutcome(
            topic="soil",
            source_name=params.SOURCE_NAME if data else None,
            chain_step=1 if data else None,
            ok=data is not None,
            duration_s=round(time.monotonic() - started, 3),
            # The maps are static predictions, not tied to a day.
            data_date=None,
            fetched_at=datetime.now(UTC),
            message=message,
        )
        return SoilFetch(data=data, outcome=outcome, limitations=limitations)

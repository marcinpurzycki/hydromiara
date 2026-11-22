"""The terrain analysis as Report parts: map direction, trace entry, limitations.

The limitations say what the terrain data cannot show for this parcel. They
all concern the cause "water runs off the field quickly" and the water
retention sites, so they are marked as affecting the recommendations. A
missing terrain grid is not named here: the limitation of a missing data
category already covers it.

Pure: reads only the analysis result and the stored source outcomes.
"""

from app.contracts.report import DownhillDirection, Limitation, TraceEntry
from app.contracts.source_data import SourceData
from app.engine.cause_model import pl_number
from app.engine.cause_params import (
    DEFAULT_CAUSE_PARAMS,
    ROUNDED_HEIGHTS_FLAT_SLOPE_PCT,
    CauseParams,
)
from app.engine.terrain_analysis import TerrainAnalysis
from app.sources.terrain_params import COPERNICUS_SOURCE_NAME, GUGIK_SOURCE_NAME

# Terrain sources that describe the surface with buildings and vegetation
# (a surface model), not the bare ground.
SURFACE_MODEL_SOURCES: frozenset[str] = frozenset({COPERNICUS_SOURCE_NAME})
# Terrain sources read from the national 1 m terrain model (bare ground).
POINT_HEIGHT_SOURCES: frozenset[str] = frozenset({GUGIK_SOURCE_NAME})

_MEAN_DIRECTION = (
    "Kierunek spływu to kierunek średniego spadku całej Działki. Na części pola woda może "
    "płynąć inaczej (na trzech zmierzonych działkach na 16–43% powierzchni kierunek miejscowy "
    "odbiegał od średniego o ponad 45°). Model terenu nie pokazuje bruzd, redlin, kolein ani "
    "drenów i pochodzi z pomiarów sprzed kilku lat."
)

_NOT_ASSESSED = (
    "nie wyznaczono spadku ani kierunku spływu, więc nie można ocenić, czy woda szybko "
    "odpływa z pola."
)
_TRACE_RESULTS = {
    "too_few_cells": "za mało punktów siatki wysokości wewnątrz Działki",
    "unsupported_grid": "siatka wysokości w układzie, który nie jest analizowany",
}


def downhill_direction(analysis: TerrainAnalysis | None) -> DownhillDirection | None:
    """Direction for the map; None when the terrain does not show one."""
    if analysis is None or analysis.downhill_azimuth_deg is None:
        return None
    return DownhillDirection(
        label=analysis.downhill_label, azimuth_deg=round(analysis.downhill_azimuth_deg) % 360
    )


def _rounded(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


def terrain_trace(
    analysis: TerrainAnalysis, params: CauseParams = DEFAULT_CAUSE_PARAMS
) -> TraceEntry:
    """How the slope and the downhill direction were obtained."""
    if not analysis.analysed:
        result = _TRACE_RESULTS[analysis.status]
    elif analysis.direction_resolved:
        result = f"teren opada na {analysis.downhill_label}"
    else:
        result = "kierunek spływu nieokreślony: spadek zbyt mały względem rozrzutu wysokości"
    direction = downhill_direction(analysis)
    return TraceEntry(
        rule_id="terrain.slope",
        condition=(
            "spadek i kierunek spływu z płaszczyzny dopasowanej do punktów siatki wysokości "
            f"wewnątrz Działki (co najmniej {params.terrain_min_cells}); kierunek i najniższa "
            "część są podawane, gdy spadek jest co najmniej "
            f"{pl_number(params.slope_min_signal_to_error, 1)} razy większy od swojej "
            "niepewności"
        ),
        values={
            "cells_inside": analysis.cells_inside,
            "cells_used": analysis.cells_used,
            "covers_parcel": analysis.covers_parcel,
            "slope_pct": _rounded(analysis.slope_pct, 1),
            "slope_error_pct": _rounded(analysis.slope_error_pct, 1),
            "downhill_azimuth_deg": None if direction is None else direction.azimuth_deg,
            "lowest_part": analysis.lowest_part,
            "relief_m": _rounded(analysis.relief_m, 2),
        },
        result=result,
    )


def _terrain_source_name(source_data: SourceData) -> str | None:
    for outcome in source_data.outcomes:
        if outcome.topic == "terrain" and outcome.ok:
            return outcome.source_name
    return None


def terrain_limitations(
    source_data: SourceData,
    analysis: TerrainAnalysis | None,
    params: CauseParams = DEFAULT_CAUSE_PARAMS,
) -> list[Limitation]:
    """What the terrain data cannot show for this parcel; empty without terrain data."""
    if analysis is None:
        return []
    texts: list[str] = []
    if analysis.status == "unsupported_grid":
        texts.append(
            "Dane o ukształtowaniu terenu są w układzie, którego ta wersja nie analizuje: "
            + _NOT_ASSESSED
        )
    elif not analysis.analysed:
        texts.append(
            "Wewnątrz Działki leży za mało punktów siatki wysokości "
            f"({analysis.cells_used}; potrzeba co najmniej {params.terrain_min_cells}, które "
            "nie leżą w jednej linii): " + _NOT_ASSESSED
        )
    else:
        if not analysis.direction_resolved:
            texts.append(
                f"Spadek terenu na Działce ({pl_number(analysis.slope_pct, 1)}%) jest zbyt "
                f"mały względem rozrzutu wysokości w danych (± "
                f"{pl_number(analysis.slope_error_pct, 1)}), aby wskazać kierunek spływu "
                "i najniższą część Działki."
            )
        if analysis.cells_used < analysis.cells_inside:
            texts.append(
                f"Część punktów siatki wysokości wewnątrz Działki nie ma wartości "
                f"({analysis.cells_inside - analysis.cells_used} z {analysis.cells_inside}); "
                "spadek i kierunek spływu policzono z pozostałych."
            )
    if analysis.status != "unsupported_grid" and not analysis.covers_parcel:
        texts.append(
            "Siatka wysokości obejmuje tylko część Działki; ocena, czy woda szybko odpływa "
            "z pola, dotyczy tej części."
        )
    name = _terrain_source_name(source_data)
    if name in SURFACE_MODEL_SOURCES and analysis.analysed:
        texts.append(
            f"Spadek i kierunek spływu policzono z modelu satelitarnego o oczku około 30 m "
            f"({name}), który opisuje powierzchnię razem z budynkami i roślinnością, a nie sam "
            "grunt. Średni spadek pola jest wiarygodny, ale miejsca, w którym woda się zbiera, "
            "nie da się z niego wskazać dokładniej niż do strony pola."
        )
        if analysis.cells_used < params.coarse_grid_min_cells:
            texts.append(
                "Działka jest za mała albo za wąska dla modelu terenu o oczku 30 m; spadek "
                "jest przybliżony."
            )
    elif name in POINT_HEIGHT_SOURCES and analysis.analysed and analysis.cell_size_m:
        texts.append(
            "Ukształtowanie terenu odczytano z numerycznego modelu terenu GUGiK co "
            f"{pl_number(min(analysis.cell_size_m), 0)} m. Wysokości są zaokrąglone do 10 cm, "
            "więc na polu prawie płaskim (spadek poniżej "
            f"{pl_number(ROUNDED_HEIGHTS_FLAT_SLOPE_PCT, 1)}%) kierunek spływu wody jest "
            "orientacyjny."
        )
    if analysis.direction_resolved:
        texts.append(_MEAN_DIRECTION)
    return [Limitation(text=text, affects="recommendations", permanent=False) for text in texts]

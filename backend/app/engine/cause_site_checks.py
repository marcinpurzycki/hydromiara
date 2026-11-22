"""Two deficit causes read from the parcel itself: its soil and its terrain.

- "The soil stores water poorly": available water capacity per metre of the
  root zone the balance was run for, from the soil category of the parcel or
  from a category estimated from texture. A stand-in capacity (no soil data,
  organic soil) is never a basis for the cause: the state is then "no data".
- "Water runs off the field quickly": mean slope of the parcel from the
  terrain analysis. A slope above the threshold that cannot be told apart from
  the scatter of the elevations is "no data", not a found cause.

The thresholds are working values without a scientific source, kept in
`cause_params`.
"""

from app.contracts.causes import Fact
from app.engine.assessment import WaterAssessment
from app.engine.cause_model import CauseResult, SourceNames, pl_number
from app.engine.cause_params import CauseParams
from app.engine.soil_capacity import CATEGORY_LABELS
from app.engine.soil_limitations import soil_basis_pl
from app.engine.terrain_analysis import TerrainAnalysis

_SOIL = "gleba słabo magazynuje wodę"
_RUNOFF = "woda szybko odpływa z pola"


def soil_cause(
    assessment: WaterAssessment, params: CauseParams, sources: SourceNames
) -> CauseResult:
    zone = assessment.root_zone
    threshold = params.soil_min_available_water_mm_per_m
    name = "Woda dostępna dla roślin na metr głębokości gleby"
    condition = f"woda dostępna dla roślin poniżej {pl_number(threshold)} mm na metr gleby"
    trace_values = {"capacity_source": zone.capacity_source}
    if zone.capacity_source == "fallback":
        return CauseResult(
            id="soil", state="no_data", indicator_name=name, unit="mm/m", value=None,
            threshold=threshold, condition=condition, trace_values=trace_values,
            finding=(
                f"Nie można ocenić, czy {_SOIL}: brak danych o glebie Działki. Pojemność "
                "wodna przyjęta zastępczo w bilansie wodnym nie jest podstawą do "
                "stwierdzenia tej przyczyny."
            ),
        )
    value = float(round(zone.available_water_mm_per_m))
    found = value < threshold
    facts = [
        Fact(
            text=(
                f"Gleba Działki mieści {pl_number(value)} mm wody dostępnej dla roślin na "
                f"metr głębokości; w warstwie {pl_number(zone.depth_cm)} cm przyjętej "
                f"w bilansie wodnym to {pl_number(zone.taw_mm)} mm."
            ),
            source=sources.soil,
        )
    ]
    basis = soil_basis_pl(zone)
    if basis is not None:
        facts.append(Fact(text=basis, source=sources.soil))
    start = f"Na tej Działce {_SOIL}" if found else f"Nie stwierdzono, że {_SOIL}"
    return CauseResult(
        id="soil", state="found" if found else "not_found", indicator_name=name,
        unit="mm/m", value=value, threshold=threshold, condition=condition,
        facts=tuple(facts),
        finding=(
            f"{start}: mieści {pl_number(value)} mm wody dostępnej dla roślin na metr "
            f"głębokości (próg: poniżej {pl_number(threshold)} mm)."
        ),
        trace_values={
            **trace_values,
            "available_water_mm_per_m": value,
            "root_zone_depth_cm": round(zone.depth_cm),
            **({} if zone.soil is None or zone.soil.category is None
               else {"soil_category": CATEGORY_LABELS[zone.soil.category]}),
        },
    )


def _terrain_facts(terrain: TerrainAnalysis, source: str) -> tuple[Fact, ...]:
    slope, error = pl_number(terrain.slope_pct, 1), pl_number(terrain.slope_error_pct, 1)
    if terrain.direction_resolved:
        direction = f"teren opada na {terrain.downhill_label}"
    else:
        direction = (
            "kierunku spływu nie da się wskazać, bo spadek jest zbyt mały względem "
            "rozrzutu wysokości w danych"
        )
    facts = [
        Fact(
            text=f"Średni spadek terenu na Działce wynosi {slope}% (± {error}); {direction}.",
            source=source,
        )
    ]
    if terrain.lowest_part is not None:
        facts.append(
            Fact(
                text=f"Najniżej położona jest {terrain.lowest_part} część Działki.",
                source=source,
            )
        )
    width, height = terrain.cell_size_m
    method = (
        f"Spadek policzono z siatki wysokości o oczku około {pl_number(width)} × "
        f"{pl_number(height)} m; liczba punktów siatki wewnątrz Działki: "
        f"{terrain.cells_used}. Różnica między najwyższym a najniższym z nich: "
        f"{pl_number(terrain.relief_m, 1)} m."
    )
    if not terrain.covers_parcel:
        method += " Siatka obejmuje tylko część Działki."
    facts.append(Fact(text=method, source=source))
    return tuple(facts)


def runoff_cause(
    terrain: TerrainAnalysis | None, params: CauseParams, sources: SourceNames
) -> CauseResult:
    threshold = params.runoff_max_slope_pct
    name = "Średni spadek terenu na Działce"
    condition = (
        f"średni spadek terenu powyżej {pl_number(threshold, 1)}% i co najmniej "
        f"{pl_number(params.slope_min_signal_to_error, 1)} razy większy od swojej niepewności"
    )

    def no_data(why: str, facts: tuple[Fact, ...] = (), **trace_values) -> CauseResult:
        return CauseResult(
            id="runoff", state="no_data", indicator_name=name, unit="%", value=None,
            threshold=threshold, condition=condition, facts=facts, trace_values=trace_values,
            finding=f"Nie można ocenić, czy {_RUNOFF}: {why}",
        )

    if terrain is None:
        return no_data("brak danych o ukształtowaniu terenu.", terrain_status="missing")
    if terrain.status == "unsupported_grid":
        return no_data(
            "dane o ukształtowaniu terenu są w układzie, którego ta wersja nie analizuje.",
            terrain_status=terrain.status,
        )
    if not terrain.analysed:
        return no_data(
            f"wewnątrz Działki leży za mało punktów siatki wysokości ({terrain.cells_used}); "
            f"potrzeba co najmniej {params.terrain_min_cells}, które nie leżą w jednej linii.",
            terrain_status=terrain.status,
            cells_used=terrain.cells_used,
        )

    value = round(terrain.slope_pct, 1)
    error = round(terrain.slope_error_pct, 1)
    facts = _terrain_facts(terrain, sources.terrain)
    trace_values = {
        "terrain_status": terrain.status,
        "slope_pct": value,
        "slope_error_pct": error,
        "direction_resolved": terrain.direction_resolved,
        "cells_used": terrain.cells_used,
    }
    above = value > threshold
    if above and not terrain.direction_resolved:
        return no_data(
            f"wyliczony spadek ({pl_number(value, 1)}%) jest zbyt mały względem rozrzutu "
            f"wysokości w danych (± {pl_number(error, 1)}), aby uznać go za rzeczywisty.",
            facts,
            **trace_values,
        )
    start = f"Na tej Działce {_RUNOFF}" if above else f"Nie stwierdzono, że {_RUNOFF}"
    return CauseResult(
        id="runoff", state="found" if above else "not_found", indicator_name=name, unit="%",
        value=value, threshold=threshold, condition=condition, facts=facts,
        finding=(
            f"{start}: średni spadek terenu wynosi {pl_number(value, 1)}% "
            f"(próg: powyżej {pl_number(threshold, 1)}%)."
        ),
        trace_values=trace_values,
    )

"""Two deficit causes read from the weather and the crop catalogue.

- "Too little precipitation against evaporation": precipitation as a share of
  the reference evapotranspiration ET0 of the same period. The period follows
  the verdict that shows the deficit: the deficit years of the multi-year
  window (the months the engine already sums for every year), otherwise the
  recent days behind the current status.
- "A crop with high water needs": the mid-season crop coefficient Kc of the
  crop from the catalogue, whatever crops the catalogue holds.

Both rules are working rules without a scientific source; the thresholds are
in `cause_params`.
"""

from app.catalog.crop_model import CatalogCrop
from app.contracts.causes import Fact
from app.engine.assessment import WaterAssessment
from app.engine.cause_model import CauseResult, SourceNames, pl_number
from app.engine.cause_params import CauseParams
from app.engine.susceptibility import YearResult

_MONTHS = (
    "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
    "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
)
_PRECIPITATION = "za mało opadów względem parowania"
_ET0_NOTE = "opad i parowanie wskaźnikowe ET0 (FAO-56)"


def _share_pct(rain_mm: float, et0_mm: float) -> float:
    return float(round(100.0 * rain_mm / et0_mm))


def _with_sums(years: list[YearResult]) -> list[YearResult]:
    return [
        year
        for year in years
        if year.precipitation_mm is not None and year.climatic_water_balance_mm is not None
    ]


def _et0(year: YearResult) -> float:
    # The climatic water balance of a year is precipitation minus ET0.
    return year.precipitation_mm - year.climatic_water_balance_mm


def _precipitation_result(
    params: CauseParams, period: str, rain: float | None, et0: float | None,
    facts: tuple[Fact, ...], trace_values: dict,
) -> CauseResult:
    threshold = params.precipitation_min_share_of_et0_pct
    name = f"Opad jako część parowania {period}"
    condition = f"opad {period} poniżej {pl_number(threshold)}% parowania wskaźnikowego ET0"
    if rain is None or et0 is None or et0 <= 0:
        return CauseResult(
            id="precipitation", state="no_data", indicator_name=name, unit="%", value=None,
            threshold=threshold, condition=condition, trace_values=trace_values,
            finding=(
                f"Nie można ocenić, czy jest {_PRECIPITATION}: brak danych o opadzie "
                f"i parowaniu {period}."
            ),
        )
    value = _share_pct(rain, et0)
    found = value < threshold
    start = (
        f"Jest {_PRECIPITATION}" if found else f"Nie stwierdzono, że jest {_PRECIPITATION}"
    )
    return CauseResult(
        id="precipitation", state="found" if found else "not_found", indicator_name=name,
        unit="%", value=value, threshold=threshold, condition=condition, facts=facts,
        finding=(
            f"{start}: {period} opad pokrył {pl_number(value)}% parowania "
            f"(próg: poniżej {pl_number(threshold)}%)."
        ),
        trace_values={**trace_values, "precipitation_share_of_et0_pct": value},
    )


def precipitation_cause(
    assessment: WaterAssessment, params: CauseParams, sources: SourceNames
) -> CauseResult:
    multiyear, current = assessment.multiyear_susceptibility, assessment.current_status
    source = f"{sources.weather}: {_ET0_NOTE}"
    assessed = _with_sums([year for year in multiyear.years if year.assessed])
    deficit = [year for year in assessed if year.deficit]
    if (multiyear.deficit_level or 0) >= 1:
        first, last = multiyear.years[-1].sum_months
        months = f"{_MONTHS[first - 1]}–{_MONTHS[last - 1]}"
        period = f"w miesiącach {months} w latach z niedoborem"
        if not deficit:
            values = {"basis": "multiyear_deficit_years", "years": 0}
            return _precipitation_result(params, period, None, None, (), values)
        rain = sum(year.precipitation_mm for year in deficit)
        et0 = sum(_et0(year) for year in deficit)
        listed = ", ".join(str(year.year) for year in deficit)
        facts = [
            Fact(
                text=(
                    f"W latach z niedoborem ({listed}) w miesiącach {months} spadło średnio "
                    f"{pl_number(rain / len(deficit))} mm opadu, a parowanie wyniosło średnio "
                    f"{pl_number(et0 / len(deficit))} mm."
                ),
                source=source,
            )
        ]
        others = [year for year in assessed if not year.deficit]
        others_et0 = sum(_et0(year) for year in others)
        if others and others_et0 > 0:
            share = _share_pct(sum(year.precipitation_mm for year in others), others_et0)
            facts.append(
                Fact(
                    text=(
                        "W pozostałych latach Okna wieloletniego opad pokrył w tych "
                        f"miesiącach średnio {pl_number(share)}% parowania."
                    ),
                    source=source,
                )
            )
        values = {
            "basis": "multiyear_deficit_years",
            "years": len(deficit),
            "precipitation_mm": round(rain),
            "et0_mm": round(et0),
        }
        return _precipitation_result(params, period, rain, et0, tuple(facts), values)

    rain, et0 = current.precipitation_recent_mm, current.et0_recent_mm
    if current.state_date is None:
        period = f"w {current.recent_days} dniach przed Datą analizy"
        return _precipitation_result(params, period, None, None, (), {"basis": "recent_days"})
    period = f"w {current.recent_days} dniach do {current.state_date.strftime('%d.%m.%Y')}"
    facts = ()
    if rain is not None and et0 is not None:
        facts = (
            Fact(
                text=(
                    f"{period[0].upper()}{period[1:]} spadło {pl_number(rain)} mm opadu, "
                    f"a parowanie wyniosło {pl_number(et0)} mm."
                ),
                source=source,
            ),
        )
    values = {
        "basis": "recent_days",
        "days": current.recent_days,
        "precipitation_mm": None if rain is None else round(rain),
        "et0_mm": None if et0 is None else round(et0),
    }
    return _precipitation_result(params, period, rain, et0, facts, values)


def _critical_period_fact(
    assessment: WaterAssessment, sources: SourceNames, catalogue_source: str
) -> Fact | None:
    """Mean water need and rain of the complete critical periods of the window."""
    years = [
        year for year in assessment.multiyear_susceptibility.years
        if year.assessed and not year.partial
    ]
    if not years:
        return None
    need = rain = 0.0
    for year in years:
        days = assessment.balance.between(year.critical_period.start, year.critical_period.end)
        need += sum(day.kc * day.et0_mm for day in days)
        rain += sum(day.precipitation_mm for day in days)
    period = years[-1].critical_period
    return Fact(
        text=(
            f"W Okresie krytycznym ({period.start.strftime('%d.%m')}–"
            f"{period.end.strftime('%d.%m')}) Uprawa potrzebuje średnio "
            f"{pl_number(need / len(years))} mm wody, a opad daje w tym czasie średnio "
            f"{pl_number(rain / len(years))} mm (średnia z pełnych lat Okna wieloletniego: "
            f"{len(years)})."
        ),
        source=f"{sources.weather}; współczynniki uprawy: {catalogue_source}",
    )


def crop_demand_cause(
    assessment: WaterAssessment, crop: CatalogCrop, params: CauseParams, sources: SourceNames
) -> CauseResult:
    threshold = params.crop_demand_max_kc_mid
    name = "Współczynnik uprawy Kc w środkowej fazie wzrostu"
    condition = (
        f"współczynnik uprawy Kc w środkowej fazie wzrostu powyżej {pl_number(threshold, 2)}"
    )
    if crop.growth is None:
        return CauseResult(
            id="crop_demand", state="no_data", indicator_name=name, unit="", value=None,
            threshold=threshold, condition=condition, trace_values={"crop_id": crop.id},
            finding=(
                "Nie można ocenić potrzeb wodnych Uprawy: dla Pola bez uprawy katalog nie "
                "podaje współczynnika uprawy."
            ),
        )
    kc_mid = crop.growth.kc_mid
    value = round(kc_mid.value, 2)
    found = value > threshold
    catalogue_source = kc_mid.source or "katalog Upraw (wartość robocza)"
    facts = [
        Fact(
            text=(
                f"{crop.name}: współczynnik uprawy Kc w środkowej fazie wzrostu wynosi "
                f"{pl_number(value, 2)}. Wartość 1 oznacza zużycie wody takie jak trawy "
                "wzorcowej, dla której liczone jest parowanie."
            ),
            source=catalogue_source,
        )
    ]
    period_fact = _critical_period_fact(assessment, sources, catalogue_source)
    if period_fact is not None:
        facts.append(period_fact)
    if found:
        finding = (
            f"{crop.name} to Uprawa o dużych potrzebach wodnych: w środkowej fazie wzrostu "
            f"współczynnik uprawy Kc wynosi {pl_number(value, 2)} "
            f"(próg: powyżej {pl_number(threshold, 2)})."
        )
    else:
        finding = (
            f"Nie stwierdzono, że {crop.name} to Uprawa o dużych potrzebach wodnych: "
            f"w środkowej fazie wzrostu współczynnik uprawy Kc wynosi {pl_number(value, 2)} "
            f"(próg: powyżej {pl_number(threshold, 2)})."
        )
    return CauseResult(
        id="crop_demand", state="found" if found else "not_found", finding=finding,
        indicator_name=name, unit="", value=value, threshold=threshold, condition=condition,
        facts=tuple(facts), trace_values={"crop_id": crop.id, "kc_mid": value},
    )

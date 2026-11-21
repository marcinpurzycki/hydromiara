"""All limitations of one Report, in a fixed order and without repeats.

Sources of a limitation:
- the permanent ones, present in every Report;
- what the water assessment shows about its own inputs: a stand-in water
  capacity, a soil profile covering part of the depth, weather ending before
  the analysis date, days without weather, years of the multi-year window
  that could not be assessed;
- how the source data were obtained: a missing data category, data from a
  less accurate substitute;
- the consistency check ending as divergent;
- limitations the source adapters returned next to their data.

Pure: the same inputs always give the same list. Order: limitations of this
analysis first, the permanent ones last.
"""

from collections.abc import Iterable, Sequence
from datetime import date
from typing import Literal

from app.contracts.report import Limitation
from app.contracts.source_data import SourceData
from app.engine.assessment import WaterAssessment
from app.engine.findings import POINTS_DIVERGENT, POINTS_STAND_IN, Finding, plain
from app.engine.source_limitations import (
    Affects,
    missing_source_findings,
    step_down_findings,
)

ConsistencyResult = Literal["zgodne", "rozbieżne", "brak danych"]

# Present in every Report, whatever the data.
PERMANENT_LIMITATIONS: tuple[Limitation, ...] = (
    Limitation(
        text="Raport nie jest urzędowym stwierdzeniem suszy rolniczej.",
        affects="all",
        permanent=True,
    ),
    Limitation(
        text="Raport nie ocenia nadmiaru wody: podtopień ani zastoisk.",
        affects="all",
        permanent=True,
    ),
    Limitation(
        text=(
            "Raport nie korzysta z prognozy pogody. Rekomendacje nawadniania wynikają "
            "wyłącznie ze stanu na Datę analizy."
        ),
        affects="recommendations",
        permanent=True,
    ),
    Limitation(
        text=(
            "Publiczne dane o rowach i ciekach są niekompletne. Rów lub ciek, którego nie ma "
            "w danych, nie jest brany pod uwagę w Rekomendacjach. Jeśli masz taki rów na "
            "Działce lub obok niej, uwzględnij go przy planowaniu zatrzymywania wody."
        ),
        affects="recommendations",
        permanent=True,
    ),
)

# Permanent limitations of the simulation; shown with its answers, not in the Report.
SIMULATION_LIMITATIONS: tuple[Limitation, ...] = (
    Limitation(
        text="Symulacja nie korzysta z danych satelitarnych: liczy wyłącznie z bilansu wodnego.",
        affects="multiyear",
        permanent=True,
    ),
    Limitation(
        text=(
            "Symulacja nie ocenia plonu, opłacalności, przydatności gleby ani zmianowania."
        ),
        affects="multiyear",
        permanent=True,
    ),
)


def _pl(day: date) -> str:
    return day.strftime("%d.%m.%Y")


def _days(count: int, *, genitive: bool = False) -> str:
    if count == 1:
        return "1 dnia" if genitive else "1 dzień"
    return f"{count} dni"


def _finding(text: str, affects: Affects, reason: str, points: int | None = None) -> Finding:
    limitation = Limitation(text=text, affects=affects, permanent=False)
    if points is None:
        return Finding(limitation=limitation, reason=reason)
    return Finding(limitation=limitation, points=points, reason=reason)


def soil_findings(assessment: WaterAssessment) -> list[Finding]:
    """What the root zone used by the balance says about the soil data."""
    zone = assessment.root_zone
    if zone.capacity_source == "fallback":
        return [
            _finding(
                "Brak danych o glebie Działki: pojemność wodną gleby przyjęto zastępczo "
                f"({zone.available_water_mm_per_m:.0f} mm wody dostępnej na metr "
                "głębokości). Od tej wartości zależą oba werdykty: Bieżąca sytuacja wodna "
                "i Podatność wieloletnia.",
                "all",
                "pojemność wodną gleby przyjęto zastępczo, bez danych o glebie Działki",
                POINTS_STAND_IN,
            )
        ]
    if zone.capacity_source == "partial_soil_profile":
        return [
            _finding(
                f"Dane o glebie obejmują {zone.covered_cm:.0f} cm z {zone.depth_cm:.0f} cm "
                "głębokości przyjętej w bilansie wodnym; dla pozostałej części przyjęto taką "
                "samą pojemność wodną. Wpływa to na oba werdykty.",
                "all",
                "dane o glebie obejmują tylko część głębokości przyjętej w bilansie wodnym",
            )
        ]
    return []


def weather_findings(assessment: WaterAssessment) -> list[Finding]:
    """Gaps of the weather series, as the balance and the verdicts met them."""
    balance, current = assessment.balance, assessment.current_status
    multiyear = assessment.multiyear_susceptibility
    findings: list[Finding] = []
    behind = balance.days_behind or 0
    if behind > 0 and current.state_date is not None:
        findings.append(
            _finding(
                f"Dane pogodowe kończą się {_pl(current.state_date)}, czyli {_days(behind)} "
                f"przed Datą analizy ({_pl(assessment.analysis_date)}). Bieżąca sytuacja "
                "wodna opisuje stan z tego dnia i nie uwzględnia opadów ani parowania "
                "z brakującego okresu.",
                "current",
                f"dane pogodowe kończą się {_days(behind)} przed Datą analizy",
            )
        )
    inner = balance.incomplete_days + balance.missing_dates - behind
    if inner > 0 and balance.days:
        first, last = balance.days[0].date, balance.days[-1].date
        findings.append(
            _finding(
                f"W danych pogodowych z okresu {_pl(first)}–{_pl(last)} brakuje opadu lub "
                f"parowania dla {_days(inner, genitive=True)}; w bilansie wodnym przyjęto dla "
                "nich zero. Wpływa to na oba werdykty.",
                "all",
                f"w danych pogodowych brakuje {_days(inner, genitive=True)}",
            )
        )
    skipped = [year.year for year in multiyear.years if not year.assessed]
    if skipped and multiyear.assessed:
        window = len(multiyear.years)
        years = ", ".join(str(year) for year in skipped)
        findings.append(
            _finding(
                "Dane pogodowe nie obejmują całego Okna wieloletniego: Podatność wieloletnia "
                f"jest oceniona z {multiyear.total_years} zamiast {window} lat (bez danych: "
                f"{years}).",
                "multiyear",
                f"Okno wieloletnie ocenione z {multiyear.total_years} zamiast {window} lat",
            )
        )
    return findings


def consistency_findings(
    result: ConsistencyResult | None, affects: Affects = "current"
) -> list[Finding]:
    """The divergent consistency check as a limitation of the verdict it compared.

    The other results add nothing: missing comparison data are already named
    by the limitations of their sources.
    """
    if result != "rozbieżne":
        return []
    return [
        _finding(
            "Sprawdzenie zgodności dało wynik „rozbieżne”: werdykt różni się od "
            "niezależnego wskaźnika suszy lub od odczytu satelitarnego dla tego samego "
            "okresu. Szczegóły są w części Sprawdzenie zgodności.",
            affects,
            "Sprawdzenie zgodności dało wynik „rozbieżne”",
            POINTS_DIVERGENT,
        )
    ]


def _unique(findings: Iterable[Finding]) -> list[Finding]:
    seen: set[str] = set()
    kept = []
    for finding in findings:
        if finding.limitation.text not in seen:
            seen.add(finding.limitation.text)
            kept.append(finding)
    return kept


def report_findings(
    source_data: SourceData,
    assessment: WaterAssessment,
    *,
    source_limitations: Sequence[Limitation] = (),
    consistency: ConsistencyResult | None = None,
    consistency_affects: Affects = "current",
    first: Sequence[Limitation] = (),
    last: Sequence[Limitation] = (),
) -> tuple[Finding, ...]:
    """Every limitation of the Report with its weight for the confidence.

    `consistency` is the result of the consistency check, when it was made.
    `first` and `last` are limitations of the caller placed before and after
    those found here. A text is kept once, at its first position.
    """
    found = _unique(
        [
            *(plain(limitation) for limitation in first),
            *consistency_findings(consistency, consistency_affects),
            *soil_findings(assessment),
            *weather_findings(assessment),
            *step_down_findings(source_data.outcomes),
            *missing_source_findings(source_data),
            *(plain(limitation) for limitation in source_limitations),
            *(plain(limitation) for limitation in last),
            *(plain(limitation) for limitation in PERMANENT_LIMITATIONS),
        ]
    )
    # Stable: limitations of this analysis first, the permanent ones last.
    return tuple(sorted(found, key=lambda finding: finding.limitation.permanent))


def limitations_of(findings: Iterable[Finding]) -> list[Limitation]:
    """The list for the Report."""
    return [finding.limitation for finding in findings]

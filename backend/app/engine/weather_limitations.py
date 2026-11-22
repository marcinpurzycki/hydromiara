"""Gaps of the weather series, as the balance and the verdicts met them.

The series of an analysis made for the current day ends on the day before,
because the current day still lasts and the archive gives it as a forecast.
That one day is the normal state: it is said in a sentence that does not lower
the confidence. Whether the analysis date was the current day is read from the
time of the weather fetch stored with the source data, so the same stored data
always give the same limitations. Any other gap before the analysis date
lowers the confidence of the current water status.

Pure: reads only the assessment and the outcome records of the sources.
"""

from collections.abc import Iterable
from datetime import date, timedelta

from app.contracts.report import Limitation
from app.contracts.source_data import SourceOutcome
from app.engine.assessment import WaterAssessment
from app.engine.findings import Finding
from app.engine.source_limitations import Affects
from app.sources.weather_series import days_pl, ends_yesterday_text, is_normal_end, local_day, pl


def expected_end(analysis_date: date, outcomes: Iterable[SourceOutcome]) -> date:
    """Last day the weather fetch could ask for: never the day of the fetch itself."""
    fetched = next(
        (outcome.fetched_at for outcome in outcomes if outcome.topic == "weather" and outcome.ok),
        None,
    )
    if fetched is None:
        return analysis_date
    return min(analysis_date, local_day(fetched) - timedelta(days=1))


def _finding(text: str, affects: Affects, reason: str) -> Finding:
    return Finding(
        limitation=Limitation(text=text, affects=affects, permanent=False), reason=reason
    )


def weather_findings(
    assessment: WaterAssessment, outcomes: Iterable[SourceOutcome] = ()
) -> list[Finding]:
    """`outcomes` are the outcome records stored with the source data."""
    balance, current = assessment.balance, assessment.current_status
    multiyear = assessment.multiyear_susceptibility
    findings: list[Finding] = []
    behind = balance.days_behind or 0
    last = current.state_date
    if last is not None and is_normal_end(
        last, assessment.analysis_date, expected_end(assessment.analysis_date, outcomes)
    ):
        # Marked permanent: a state of every analysis of the current day, which
        # says nothing about the completeness of the data.
        findings.append(
            Finding(
                limitation=Limitation(
                    text=ends_yesterday_text(last), affects="current", permanent=True
                ),
                points=0,
            )
        )
    elif behind > 0 and last is not None:
        findings.append(
            _finding(
                f"Dane pogodowe kończą się {pl(last)}, czyli {days_pl(behind)} "
                f"przed Datą analizy ({pl(assessment.analysis_date)}). Bieżąca sytuacja "
                "wodna opisuje stan z tego dnia i nie uwzględnia opadów ani parowania "
                "z brakującego okresu.",
                "current",
                f"dane pogodowe kończą się {days_pl(behind)} przed Datą analizy",
            )
        )
    inner = balance.incomplete_days + balance.missing_dates - behind
    if inner > 0 and balance.days:
        first, final = balance.days[0].date, balance.days[-1].date
        findings.append(
            _finding(
                f"W danych pogodowych z okresu {pl(first)}–{pl(final)} brakuje opadu lub "
                f"parowania dla {days_pl(inner, genitive=True)}; w bilansie wodnym przyjęto "
                "dla nich zero. Wpływa to na oba werdykty.",
                "all",
                f"w danych pogodowych brakuje {days_pl(inner, genitive=True)}",
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

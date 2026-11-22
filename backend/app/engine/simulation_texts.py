"""Sentences shown with the simulation: its limitations and why it gives no answer.

The two permanent limitations are always first. The other sentences say how
many crops were compared and why some were not, so that a short ranking is
never read as "nothing else grows well here".
"""

from app.contracts.report import Limitation
from app.engine.limitations import SIMULATION_LIMITATIONS
from app.engine.simulation import TOP_COUNT, CropResult, Simulation

# Why a crop has no multi-year susceptibility to compare.
NOT_COMPARABLE = {
    "no_crop": (
        "Dla Pola bez uprawy nie wyznacza się Stopnia niedoboru, więc nie ma czego "
        "porównać w Symulacji."
    ),
    "no_weather": (
        "Brak danych pogodowych z Okresu krytycznego tej Uprawy, więc nie da się jej "
        "porównać w Symulacji."
    ),
}


def not_comparable_sentence(result: CropResult) -> str:
    """Why the crop cannot be compared; only for a crop without a verdict."""
    return NOT_COMPARABLE[result.verdict.not_assessed_reason]


def _other_crops(count: int) -> str:
    """Polish accusative of "<count> other crops"."""
    if count == 1:
        return "1 inną Uprawę"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return f"{count} inne Uprawy"
    return f"{count} innych Upraw"


def _compared_sentence(count: int) -> str:
    if count == 0:
        return (
            "Na liście nie ma teraz innej Uprawy, którą można porównać z bieżącą, więc "
            "Ranking upraw pokazuje tylko bieżącą Uprawę."
        )
    if count < TOP_COUNT:
        return (
            f"Z bieżącą Uprawą porównano {_other_crops(count)}, bo tyle jest teraz na "
            "liście, więc Ranking upraw pokazuje mniej niż trzy Uprawy."
        )
    return (
        f"Z bieżącą Uprawą porównano {_other_crops(count)} z listy. Ranking upraw pokazuje "
        "trzy najmniej narażone na niedobór wody."
    )


def _not_compared_sentences(simulation: Simulation) -> list[str]:
    sentences = []
    if any(result.crop.is_bare_field for result in simulation.not_compared):
        sentences.append(
            "Pole bez uprawy nie jest porównywane, bo nie wyznacza się dla niego Stopnia "
            "niedoboru."
        )
    without_weather = [
        result.crop.name for result in simulation.not_compared if not result.crop.is_bare_field
    ]
    if without_weather:
        sentences.append(
            "Nie porównano Upraw, dla których brakuje danych pogodowych z Okresu "
            f"krytycznego: {', '.join(without_weather)}."
        )
    return sentences


def _years_sentence(simulation: Simulation) -> str | None:
    """Says that the shown crops were assessed over different numbers of years."""
    totals = {result.verdict.total_years for result in (simulation.current, *simulation.top)}
    if len(totals) < 2:
        return None
    return (
        f"Uprawy oceniono z różnej liczby lat (od {min(totals)} do {max(totals)}), bo ich "
        "Okresy krytyczne wypadają w innych dniach roku. Kolejność wynika z udziału lat z "
        "niedoborem wody w ocenionych latach."
    )


def ranking_limitations(simulation: Simulation) -> list[Limitation]:
    """Limitations of a ranking answer: the permanent ones, then those of this ranking."""
    sentences = [
        _compared_sentence(len(simulation.ranked)),
        *_not_compared_sentences(simulation),
    ]
    years = _years_sentence(simulation)
    if years is not None:
        sentences.append(years)
    return [
        *SIMULATION_LIMITATIONS,
        *(Limitation(text=text, affects="multiyear", permanent=False) for text in sentences),
    ]

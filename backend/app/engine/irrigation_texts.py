"""Wording of the irrigation part of the Report.

Every sentence is built from the state of the water balance on the analysis
date. Nothing here promises a yield effect or names sizes, costs or equipment.
Pure: the same input always gives the same text.
"""

from datetime import date, timedelta

from app.catalog.periods import DateRange
from app.engine.consistency_parts import pl
from app.engine.params import DEFICIT_LEVEL_LABELS
from app.engine.root_zone import RootZone
from app.engine.season_texts import STORE_NOT_NEEDS, span
from app.engine.verdicts import CurrentVerdict

NO_CROP = "Rekomendacje nawadniania: nie dotyczy — dla Pola bez uprawy Raport ich nie przedstawia."
NO_WEATHER = (
    "Zasadności nawadniania nie można ocenić: brak danych pogodowych do Daty analizy, "
    "z których wyznaczana jest Bieżąca sytuacja wodna."
)
NOT_JUSTIFIED = "Nawadnianie nie jest teraz zasadne"
OPENING = "Jeśli masz możliwość nawadniania, jest ono teraz zasadne"
NOT_INSTEAD_OF_RETENTION = "Nawadnianie nie zastępuje zatrzymywania wody na Działce."
NET_AMOUNT = "Podane ilości to woda, która ma wsiąknąć w glebę."
_CAPACITY_NOTES = {
    "fallback": (
        "Brak danych o glebie Działki: pojemność wodną gleby przyjęto zastępczo, więc podane "
        "ilości wody są mniej pewne."
    ),
    "partial_soil_profile": (
        "Dane o glebie obejmują tylko część głębokości przyjętej w bilansie wodnym, więc "
        "podane ilości wody są mniej pewne."
    ),
}


def number(value: float) -> str:
    """Polish notation: decimal comma, no trailing zeros."""
    return f"{round(value, 1):g}".replace(".", ",")


def _join(*sentences: str | None) -> str:
    return " ".join(sentence for sentence in sentences if sentence)


def _store(verdict: CurrentVerdict) -> tuple[str, str]:
    """(water in the root zone, its capacity), whole mm."""
    taw = verdict.total_available_water_mm
    return str(round(taw - verdict.depletion_mm)), str(round(taw))


def conditional(state_date: date, justified: bool) -> str:
    """The answer is a reading of one day, without a weather forecast."""
    opening = f"To ocena ze stanu na {pl(state_date)}, bez prognozy pogody"
    if justified:
        return (
            f"{opening}: opad po tym dniu zmniejsza potrzebę nawadniania, a o nawadnianiu "
            "decydujesz Ty."
        )
    return f"{opening}: okres bez opadu po tym dniu może ją zmienić."


def capacity_note(zone: RootZone) -> str | None:
    """Names the weaker basis of the amounts; the limitation itself is elsewhere."""
    return _CAPACITY_NOTES.get(zone.capacity_source)


def range_sentence(mm: tuple[float, float], m3_ha: tuple[float, float]) -> str:
    if mm[0] == mm[1]:
        return f"Zakres: {number(mm[0])} mm wody, czyli {number(m3_ha[0])} m³ na hektar."
    return (
        f"Zakres: od {number(mm[0])} do {number(mm[1])} mm wody, czyli od "
        f"{number(m3_ha[0])} do {number(m3_ha[1])} m³ na hektar."
    )


def justified_text(
    verdict: CurrentVerdict, zone: RootZone, mm: tuple[float, float], m3_ha: tuple[float, float]
) -> str:
    stored, capacity = _store(verdict)
    return _join(
        f"{OPENING}. Bieżąca sytuacja wodna na {pl(verdict.state_date)}: {verdict.label}.",
        f"W glebie zostało {stored} mm wody dostępnej dla roślin z {capacity} mm, które gleba "
        "może zmagazynować w zasięgu korzeni.",
        range_sentence(mm, m3_ha),
        "Mniejsza z tych ilości uzupełnia Zapas wody w glebie do poziomu, od którego uprawie "
        "przestaje brakować wody, większa do pełna; więcej wody gleba w zasięgu korzeni nie "
        "zatrzyma.",
        NET_AMOUNT,
        capacity_note(zone),
        conditional(verdict.state_date, justified=True),
        NOT_INSTEAD_OF_RETENTION,
    )


def justified_timing(verdict: CurrentVerdict, critical_period: DateRange | None) -> str:
    run = verdict.stress_run_days
    since = "" if run < 1 else f": wody brakuje uprawie od {'1 dnia' if run == 1 else f'{run} dni'}"
    since += " z rzędu" if run > 1 else ""
    critical = None
    if critical_period is not None:
        critical = (
            f"Data analizy wypada w Okresie krytycznym ({span(critical_period)}), w którym "
            "uprawa potrzebuje najwięcej wody i najsilniej reaguje na jej brak."
        )
    return _join(f"Teraz, według stanu na {pl(verdict.state_date)}{since}.", critical)


def not_justified_reason(verdict: CurrentVerdict) -> str:
    stored, capacity = _store(verdict)
    return (
        f"{NOT_JUSTIFIED}. Bieżąca sytuacja wodna na {pl(verdict.state_date)}: "
        f"{verdict.label}. W glebie jest {stored} mm wody dostępnej dla roślin z {capacity} mm, "
        "które gleba może zmagazynować w zasięgu korzeni."
    )


def not_justified_text(verdict: CurrentVerdict, zone: RootZone) -> str:
    return _join(
        not_justified_reason(verdict),
        capacity_note(zone),
        conditional(verdict.state_date, justified=False),
    )


def not_justified_timing(verdict: CurrentVerdict, from_level: int) -> str:
    raw = verdict.readily_available_water_mm
    if verdict.depletion_mm <= raw:
        stored, _ = _store(verdict)
        threshold = round(verdict.total_available_water_mm - raw)
        return (
            "Nie teraz. Nawadnianie stanie się zasadne, gdy Zapas wody w glebie spadnie "
            f"poniżej {threshold} mm; na {pl(verdict.state_date)} jest {stored} mm."
        )
    return (
        "Nie teraz. Nawadnianie stanie się zasadne, gdy Bieżąca sytuacja wodna wskaże "
        f"co najmniej {DEFICIT_LEVEL_LABELS[from_level]}."
    )


def dormant_reason(verdict: CurrentVerdict, dormancy: DateRange) -> str:
    stored, capacity = _store(verdict)
    return (
        f"{NOT_JUSTIFIED}: uprawa jest w spoczynku ({span(dormancy)}), a {STORE_NOT_NEEDS}. "
        f"Zapas wody w glebie na {pl(verdict.state_date)}: {stored} mm z {capacity} mm."
    )


def dormant_text(verdict: CurrentVerdict, zone: RootZone, dormancy: DateRange) -> str:
    return _join(
        dormant_reason(verdict, dormancy),
        capacity_note(zone),
        f"To ocena ze stanu na {pl(verdict.state_date)}, bez prognozy pogody.",
    )


def dormant_timing(dormancy: DateRange) -> str:
    growth = dormancy.end + timedelta(days=1)
    return (
        "Nie teraz. Nawadnianie będzie oceniane ponownie, gdy uprawa ruszy ze wzrostem po "
        f"spoczynku (typowo od {pl(growth)})."
    )

"""Limitations that follow from where the water capacity of the soil came from.

Read from the root zone the balance really used, so they hold also for
results derived later from stored source data. Each step down the substitute
chain of the soil (category map, texture estimate, stand-in value) has its
own text and weight; the generic substitute limitation is not used for soil.

Pure: the same root zone always gives the same list.
"""

from app.contracts.common import Scalar
from app.contracts.report import Limitation
from app.engine.assessment import WaterAssessment
from app.engine.findings import POINTS_DEFAULT, POINTS_STAND_IN, Finding
from app.engine.root_zone import RootZone
from app.engine.soil_capacity import CATEGORY_LABELS, CapacitySource, SoilCapacity

# How the origin of the capacity is named in the decision trace.
CAPACITY_SOURCE_LABELS: dict[CapacitySource, str] = {
    "iung_category": "kategoria gleby z mapy IUNG-PIB",
    "texture_estimate": "kategoria oszacowana z uziarnienia gleby",
    "fallback": "wartość zastępcza",
}

# PROVISIONAL: no source; weights in the confidence rule, by the same working
# rule as the other limitations: a category estimated from texture and two
# soil sources that disagree count as an ordinary limitation, a stand-in
# capacity counts double.
POINTS_TEXTURE_ESTIMATE = POINTS_DEFAULT
POINTS_SOURCES_DIVERGE = POINTS_DEFAULT
# Says how the parcel is built, not that data are missing.
POINTS_MIXED_PARCEL = 0

CATEGORY_MAP_TEXT = (
    "Zdolność gleby do magazynowania wody przyjęliśmy z mapy kategorii podatności gleb "
    "na suszę IUNG-PIB. Mapa powstała z map glebowo-rolniczych i opisuje typową glebę "
    "w danym miejscu, a nie pomiar na Twojej działce."
)
_ESTIMATE_TAIL = (
    "Zdolność gleby do magazynowania wody oszacowaliśmy z globalnej mapy gleb o oczku "
    "250 m. To szacunek zgrubny: na działkach testowych mylił się o jedną kategorię "
    "w co czwartym przypadku."
)
NO_CATEGORY_TEXT = f"Dla tej działki nie ma kategorii gleby na mapie IUNG-PIB. {_ESTIMATE_TAIL}"
MAP_NOT_READ_TEXT = (
    f"Nie udało się odczytać kategorii gleby z mapy IUNG-PIB. {_ESTIMATE_TAIL}"
)
ORGANIC_TEXT = (
    "Mapa IUNG-PIB oznacza tę działkę jako glebę organiczną (torfową lub murszową). "
    "Nasz model opisuje gleby mineralne, więc ocena zapasu wody jest tu mało pewna."
)
NO_SOIL_TEXT = (
    "Nie udało się pobrać danych o glebie. Przyjęliśmy przeciętną zdolność gleby do "
    "magazynowania wody, więc wynik jest mniej pewny."
)


def shares_pl(capacity: SoilCapacity) -> str:
    """E.g. "kategoria III na 56% powierzchni, kategoria I na 44%"."""
    parts = [
        f"kategoria {CATEGORY_LABELS[category]} na {share:.0f}%"
        + (" powierzchni" if position == 0 else "")
        for position, (category, share) in enumerate(capacity.shares)
    ]
    return ", ".join(parts)


def soil_basis_pl(zone: RootZone) -> str | None:
    """Where the capacity comes from, as one sentence; None for a stand-in value."""
    capacity = zone.soil
    if capacity is None or capacity.category is None:
        return None
    if zone.capacity_source == "texture_estimate":
        return (
            f"Kategoria podatności gleby na suszę oszacowana z uziarnienia: "
            f"{CATEGORY_LABELS[capacity.category]} (na mapie IUNG-PIB działka nie ma kategorii)."
        )
    return f"Mapa kategorii podatności gleb na suszę IUNG-PIB: {shares_pl(capacity)}."


def capacity_trace_values(zone: RootZone) -> dict[str, Scalar]:
    """Values of the decision trace that say what the capacity rests on."""
    values: dict[str, Scalar] = {
        "available_water_mm_per_m": round(zone.available_water_mm_per_m)
    }
    capacity = zone.soil
    if capacity is None:
        return values
    if capacity.category is not None:
        values["soil_category"] = CATEGORY_LABELS[capacity.category]
    if capacity.shares:
        values["category_shares"] = shares_pl(capacity)
    if capacity.source == "iung_category" and capacity.estimated_category is not None:
        values["estimated_category"] = CATEGORY_LABELS[capacity.estimated_category]
    return values


def _finding(text: str, reason: str, points: int, permanent: bool = False) -> Finding:
    limitation = Limitation(text=text, affects="all", permanent=permanent)
    return Finding(limitation=limitation, points=points, reason=reason)


def _category_map_findings(capacity: SoilCapacity) -> list[Finding]:
    findings = []
    if capacity.mixed:
        findings.append(
            _finding(
                "Na działce występują gleby o różnej podatności na suszę: "
                f"{shares_pl(capacity)}. Wynik dotyczy działki jako całości; na słabszej "
                "części wody zabraknie wcześniej.",
                "na działce występują gleby o różnej podatności na suszę",
                POINTS_MIXED_PARCEL,
            )
        )
    if capacity.divergent:
        findings.append(
            _finding(
                "Dwa źródła danych o glebie opisują tę działkę różnie: mapa IUNG-PIB "
                f"wskazuje kategorię {CATEGORY_LABELS[capacity.category]}, a globalna mapa "
                f"gleb sugeruje {CATEGORY_LABELS[capacity.estimated_category]}. Przyjęliśmy "
                "mapę IUNG-PIB. Jeśli znasz glebę na swojej działce, potraktuj wynik ostrożnie.",
                "dwa źródła danych o glebie opisują działkę różnie",
                POINTS_SOURCES_DIVERGE,
            )
        )
    findings.append(_finding(CATEGORY_MAP_TEXT, "", 0, permanent=True))
    return findings


def soil_findings(assessment: WaterAssessment) -> list[Finding]:
    """What the root zone used by the balance says about the soil data."""
    zone = assessment.root_zone
    capacity = zone.soil
    if capacity is not None and zone.capacity_source == "iung_category":
        return _category_map_findings(capacity)
    if zone.capacity_source == "iung_category":
        return []
    if zone.capacity_source == "texture_estimate":
        map_read = capacity is None or capacity.map_read
        return [
            _finding(
                NO_CATEGORY_TEXT if map_read else MAP_NOT_READ_TEXT,
                "zdolność gleby do magazynowania wody oszacowano z globalnej mapy gleb",
                POINTS_TEXTURE_ESTIMATE,
            )
        ]
    if capacity is not None and capacity.organic:
        return [
            _finding(
                ORGANIC_TEXT,
                "mapa IUNG-PIB oznacza działkę jako glebę organiczną, której model nie opisuje",
                POINTS_STAND_IN,
            )
        ]
    return [
        _finding(
            NO_SOIL_TEXT,
            "nie udało się pobrać danych o glebie, przyjęto przeciętną zdolność gleby "
            "do magazynowania wody",
            POINTS_STAND_IN,
        )
    ]

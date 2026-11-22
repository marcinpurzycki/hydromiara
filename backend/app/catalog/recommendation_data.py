"""Recommendation catalogue: the irrigation pattern entry and the whole list.

Landscape and agrotechnical entries are in `recommendation_data_terrain`, soil
entries in `recommendation_data_soil`; this module joins them in the order of
the Report. The irrigation group still holds one pattern entry that states the
justification only, without amounts, and is marked provisional. Entries do not
state sizes, costs or parameters of a structure.

Order matters twice: entries of one group appear in the Report in the order
listed here, and a `fired` condition may only name entries listed before it.
"""

from app.catalog.crop_model import Sourced
from app.catalog.recommendation_data_soil import SOIL_ENTRIES
from app.catalog.recommendation_data_water import WATER_ENTRIES
from app.catalog.recommendation_data_terrain import AGROTECHNICS_ENTRIES, LANDSCAPE_ENTRIES
from app.catalog.recommendation_model import CatalogRecommendation, Compare, Threshold

TASK = (
    "KOWR, zadanie konkursowe HackNation 2026 „Zatrzymaj wodę, chroń plony”, "
    "pkt 3.2 „Oczekiwany rezultat”"
)
BASIS = (
    "KOWR, „Podstawy naukowe oceny sytuacji wodnej oraz zwiększania retencji wody "
    "w rolnictwie”, materiał pomocniczy HackNation 2026, rozdz. „Retencja jako podstawowy "
    "kierunek działań adaptacyjnych”"
)

_NOT_PRIMARY = "cites the organiser's task and its summary, not a primary publication"
_NO_NUMBERS = " Efektu nie podajemy w liczbach."

# PROVISIONAL: no source for the level from which a verdict triggers a
# recommendation; level 1 is the lowest deficit level, the same that opens
# the deficit causes.
_FROM_LIGHT_DEFICIT = Sourced[Threshold](
    value=1,
    provisional="working value: the lowest deficit level, as in the gate of the causes",
)

IRRIGATION_ENTRIES: tuple[CatalogRecommendation, ...] = (
    # PROVISIONAL: a pattern entry of the group. It states the justification
    # only; amount and timing belong to the irrigation part of the Report.
    CatalogRecommendation(
        id="irrigation_when_water_is_short",
        title="Nawadnianie przy niedoborze wody",
        group="nawadnianie",
        causes=("precipitation", "soil", "crop_demand"),
        requires=("balance", "crop"),
        conditions=(
            Compare(
                fact="in_season",
                op="eq",
                value=Sourced[Threshold](
                    value=True,
                    source="project rule: outside the crop season no irrigation is recommended",
                ),
                wording="Data analizy wypada w Sezonie uprawy",
            ),
            Compare(
                fact="dormant",
                op="eq",
                value=Sourced[Threshold](
                    value=False,
                    source="project rule: for a dormant crop the soil water store is assessed",
                ),
                wording="Uprawa nie jest w spoczynku",
            ),
            Compare(
                fact="current_deficit_level",
                op="ge",
                value=_FROM_LIGHT_DEFICIT,
                wording="Bieżąca sytuacja wodna wskazuje co najmniej lekki niedobór",
            ),
        ),
        text=(
            "Jeśli masz możliwość nawadniania: Bieżąca sytuacja wodna to {current_label}, "
            "więc nawadnianie jest teraz uzasadnione. Nawadnianie nie zastępuje zatrzymywania "
            "wody na Działce."
        ),
        gain="Uprawa dostaje wodę, której teraz brakuje w glebie.",
        citation=(
            f"{TASK} (etap 3: zasadność, termin i zakres nawadniania); {BASIS} "
            "(nawadnianie po działaniach zwiększających retencję)."
        ),
        provisional=(
            f"{_NOT_PRIMARY}; pattern entry without amount and timing; working threshold "
            "of the rule"
        ),
    ),
)

CATALOG: tuple[CatalogRecommendation, ...] = (
    *LANDSCAPE_ENTRIES,
    *WATER_ENTRIES,
    *SOIL_ENTRIES,
    *AGROTECHNICS_ENTRIES,
    *IRRIGATION_ENTRIES,
)

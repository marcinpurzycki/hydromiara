"""Recommendation catalogue data. Adding or correcting an entry changes this file only.

One entry per group, as a pattern for the full catalogue. The content of each
comes from the competition task of the organiser and from its supporting
summary of the scientific basis; neither names the primary publication behind
a single statement, so every entry is marked provisional until it cites one.
No entry states an effect in numbers, sizes, costs or parameters of a structure.

Order matters twice: entries of one group appear in the Report in the order
listed here, and a `fired` condition may only name entries listed before it.
"""

from app.catalog.crop_model import Sourced
from app.catalog.recommendation_model import CatalogRecommendation, Compare, Known, Threshold

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

CATALOG: tuple[CatalogRecommendation, ...] = (
    # PROVISIONAL: organiser's documents instead of a primary publication. The
    # terrain shows where water gathers, not whether holding it there is feasible.
    CatalogRecommendation(
        id="hold_rainwater_in_lowest_part",
        title="Okresowe zatrzymywanie wód opadowych w najniższej części Działki",
        group="retencja krajobrazowa",
        causes=("runoff", "precipitation"),
        requires=("terrain",),
        conditions=(
            Known(
                fact="lowest_part",
                wording="analiza terenu wskazuje najniższą część Działki",
            ),
        ),
        text=(
            "Teren Działki opada na {downhill_label}, a jej najniżej położona część to część "
            "{lowest_part}. W tę stronę spływa woda po deszczach. Warto rozważyć okresowe "
            "zatrzymywanie wód opadowych w tej części Działki albo spowolnienie ich odpływu. "
            "Sposób omów z doradcą rolniczym: niektóre działania wymagają zgłoszenia "
            "w urzędzie."
        ),
        gain=(
            "Woda opadowa dłużej zostaje na Działce i wolniej z niej odpływa. Takie działania "
            "zwiększają dostępność wody dla upraw i ograniczają erozję." + _NO_NUMBERS
        ),
        citation=f"{BASIS}; {TASK} (przykładowa rekomendacja o retencji krajobrazowej).",
        provisional=(
            f"{_NOT_PRIMARY}; suitability of the lowest part for holding water is not "
            "assessed (no water data, coarse terrain grid)"
        ),
        retention_site="lowest_part",
    ),
    # PROVISIONAL: organiser's documents instead of a primary publication.
    CatalogRecommendation(
        id="catch_crops_and_residues",
        title="Międzyplony i resztki pożniwne",
        group="retencja glebowa",
        causes=("soil", "precipitation", "runoff"),
        requires=("crop",),
        text=(
            "W uprawie {crop_name_genitive} na tej Działce warto rozważyć międzyplony "
            "i pozostawianie resztek pożniwnych, a także działania spowalniające odpływ wód "
            "opadowych w obrębie Działki."
        ),
        gain=(
            "Te działania poprawiają strukturę gleby i zwiększają wsiąkanie wody, więc opady "
            "są lepiej wykorzystane." + _NO_NUMBERS
        ),
        citation=f"{BASIS}; {TASK} (przykładowa rekomendacja o międzyplonach).",
        provisional=_NOT_PRIMARY,
    ),
    # PROVISIONAL: the task gives the action only; the wording of the gain is
    # ours and the threshold of the rule is a working value.
    CatalogRecommendation(
        id="watch_crop_in_critical_period",
        title="Obserwacja Uprawy w Okresie krytycznym",
        group="agrotechnika",
        causes=("precipitation", "crop_demand"),
        requires=("balance", "crop"),
        conditions=(
            Compare(
                fact="multiyear_deficit_level",
                op="ge",
                value=_FROM_LIGHT_DEFICIT,
                wording="Podatność wieloletnia wskazuje co najmniej lekki niedobór",
            ),
        ),
        text=(
            "W {deficit_years} z {total_years} ocenionych lat Uprawie brakowało wody w Okresie "
            "krytycznym, który trwa od {critical_period_start} do {critical_period_end}. "
            "W tym czasie warto częściej sprawdzać stan Uprawy i dostępność wody."
        ),
        gain="Wcześniej zauważysz, że Uprawie zaczyna brakować wody, i zdążysz zareagować.",
        citation=f"{TASK} (przykładowa rekomendacja o okresie największego niedoboru wody).",
        provisional=(
            f"{_NOT_PRIMARY}; the task names the action only, the gain is worded by us; "
            "working threshold of the rule"
        ),
    ),
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

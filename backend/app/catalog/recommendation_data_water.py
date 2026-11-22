"""Catalogue entries that depend on data about waters around the parcel."""

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
_NO_NUMBERS = " Efektu nie podajemy w liczbach."

# PROVISIONAL: a ditch counts as lying at the parcel up to this distance from
# its outline, in metres; a margin for the position accuracy of the water
# data, which has not been verified.
_DITCH_AT_PARCEL_WITHIN_M = Sourced[Threshold](
    value=20,
    provisional="working value: margin for the position accuracy of the water data",
)

WATER_ENTRIES: tuple[CatalogRecommendation, ...] = (
    # PROVISIONAL: pattern entry of the recommendations that depend on waters in
    # the data. It appears only when a ditch or canal is in the data; the
    # distance limit is a working value.
    CatalogRecommendation(
        id="ditch_water_retention",
        title="Zatrzymywanie wody w rowie przy Działce",
        group="retencja krajobrazowa",
        causes=("precipitation", "runoff"),
        requires=("water",),
        conditions=(
            Known(
                fact="ditch_distance_m",
                wording="w danych o wodach jest rów melioracyjny lub kanał w otoczeniu Działki",
            ),
            Compare(
                fact="ditch_distance_m",
                op="le",
                value=_DITCH_AT_PARCEL_WITHIN_M,
                wording="rów lub kanał leży najwyżej 20 m od granicy Działki",
            ),
        ),
        text=(
            "Przy Działce biegnie {ditch_label} ({ditch_location}). Warto rozważyć "
            "zatrzymywanie w nim wody po roztopach i po większych deszczach, zamiast pozwalać "
            "jej od razu odpłynąć. Woda zatrzymana w rowie podnosi poziom wody w gruncie obok "
            "rowu. Zanim zaczniesz, omów to z doradcą rolniczym: część działań wymaga "
            "zgłoszenia lub pozwolenia, a jeśli rów utrzymuje spółka wodna, także uzgodnienia "
            "z nią."
        ),
        gain=(
            "Wyższy poziom wody gruntowej w pasie przy rowie i dłuższy dostęp roślin do wody "
            "w okresach bez deszczu. Efekt zależy od gleby i od tego, jak długo woda stoi "
            "w rowie." + _NO_NUMBERS
        ),
        citation=(
            "Kaca E. (red.), „Melioracje, retencja i gospodarka wodna w rolnictwie. "
            "E-poradnik”, Centrum Doradztwa Rolniczego, Brwinów 2025, s. 81 (gromadzenie "
            "wody w rowach), s. 120–121 i 131 (odpływ regulowany); "
            f"{BASIS}; {TASK} (przykładowa rekomendacja o rowach i małych ciekach)."
        ),
        provisional=(
            "pattern entry of the water-dependent group; working distance limit; formal "
            "requirements are left to the advisor until the full catalogue words them"
        ),
        retention_site="water_object",
    ),
)

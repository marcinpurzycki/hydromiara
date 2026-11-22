"""Vocabulary of the recommendation catalogue: data topics, parcel facts, cause names.

A rule of the catalogue never reads the source data directly. It names facts:
single values the engine has already derived for the parcel (a deficit level,
the slope, the lowest part). Each fact belongs to one data topic, so a rule
that requires a topic without data is not run and the Report says so.

Adding a catalogue entry that uses the facts below is a change of data only.
A new fact (for example the distance to a ditch, once water data are
connected) is added here with its topic and wording, and filled by the
engine where the other facts are filled.
"""

from dataclasses import dataclass
from typing import Literal

from app.contracts.causes import CauseId, RecommendationGroup

# Data a rule may require beyond the found cause itself.
DataTopic = Literal["balance", "crop", "soil", "terrain", "water"]

# Topics as named in a limitation: "Brak danych o ...".
TOPIC_LABELS: dict[DataTopic, str] = {
    "balance": "bilansie wodnym",
    "crop": "Uprawie",
    "soil": "glebie Działki",
    "terrain": "spadku i kierunku spływu wody na Działce",
    "water": "ciekach, rowach i zbiornikach w otoczeniu Działki",
}

# Groups in the order of the Report: retention first, irrigation last.
GROUP_ORDER: tuple[RecommendationGroup, ...] = (
    "retencja krajobrazowa",
    "retencja glebowa",
    "agrotechnika",
    "nawadnianie",
)

# Groups whose entries may point to a water retention site.
RETENTION_GROUPS: frozenset[RecommendationGroup] = frozenset(
    {"retencja krajobrazowa", "retencja glebowa"}
)

CAUSE_LABELS: dict[CauseId, str] = {
    "precipitation": "za mało opadów względem parowania",
    "soil": "gleba słabo magazynuje wodę",
    "runoff": "woda szybko odpływa z pola",
    "crop_demand": "uprawa o dużych potrzebach wodnych",
}

# What a retention site of an entry is derived from; the geometry is supplied
# by the engine when the data allow it, otherwise the entry has no site.
SiteKind = Literal["lowest_part", "water_object"]


@dataclass(frozen=True)
class FactSpec:
    topic: DataTopic
    # Wording used in the rule shown with a recommendation and in the trace.
    label: str


FACTS: dict[str, FactSpec] = {
    # Both verdicts of the water balance.
    "current_deficit_level": FactSpec("balance", "Stopień niedoboru Bieżącej sytuacji wodnej"),
    "current_label": FactSpec("balance", "Bieżąca sytuacja wodna"),
    "stress_coefficient": FactSpec("balance", "współczynnik stresu wodnego Ks"),
    "multiyear_deficit_level": FactSpec("balance", "Stopień niedoboru Podatności wieloletniej"),
    "multiyear_label": FactSpec("balance", "Podatność wieloletnia"),
    "deficit_years": FactSpec("balance", "liczba lat z niedoborem w Oknie wieloletnim"),
    "total_years": FactSpec("balance", "liczba ocenionych lat Okna wieloletniego"),
    # The crop of the analysis, from the crop catalogue.
    "crop_name": FactSpec("crop", "Uprawa"),
    "crop_name_genitive": FactSpec("crop", "Uprawa (dopełniacz)"),
    "in_season": FactSpec("crop", "Data analizy w Sezonie uprawy"),
    "dormant": FactSpec("crop", "Uprawa w spoczynku w dniu Daty analizy"),
    "critical_period_start": FactSpec("crop", "początek Okresu krytycznego"),
    "critical_period_end": FactSpec("crop", "koniec Okresu krytycznego"),
    # The soil profile of the parcel (absent when a stand-in capacity was used).
    "available_water_mm_per_m": FactSpec("soil", "woda dostępna dla roślin, mm na metr gleby"),
    # The terrain analysis of the parcel.
    "slope_pct": FactSpec("terrain", "średni spadek terenu Działki, %"),
    "downhill_label": FactSpec("terrain", "kierunek, w którym opada teren Działki"),
    "lowest_part": FactSpec("terrain", "najniższa część Działki"),
}

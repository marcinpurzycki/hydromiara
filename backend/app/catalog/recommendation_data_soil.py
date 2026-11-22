"""Catalogue entries of soil retention: cover crops, mulch, organic matter, tillage."""

from app.catalog.crop_model import Sourced
from app.catalog.recommendation_model import Addition, CatalogRecommendation, Compare, Threshold

CDR = "e-poradnik „Zatrzymaj wodę”, CDR 2025"
NWRM = "przewodnik NWRM 2015"
BASIS = "KOWR, „Podstawy naukowe oceny sytuacji wodnej oraz zwiększania retencji wody w rolnictwie”, s. 2"


def _flag(fact: str, value: bool, wording: str) -> Compare:
    return Compare(
        fact=fact, op="eq", wording=wording,
        value=Sourced[Threshold](value=value, source="crop catalogue"),
    )


SOIL_ENTRIES: tuple[CatalogRecommendation, ...] = (
    CatalogRecommendation(
        id="catch_crops",
        title="Międzyplony i poplony",
        group="retencja glebowa",
        causes=("soil", "precipitation", "runoff"),
        requires=("crop",),
        conditions=(_flag("crop_perennial", False, "Uprawa jest jednoroczna"),),
        text="Po zbiorze {crop_name_genitive} nie zostawiaj gołej gleby.",
        additions=(
            Addition(
                text="Wysiej międzyplon ścierniskowy lub ozimy.",
                conditions=(_flag("harvest_by_august_end", True, "zbiór do końca sierpnia"),),
            ),
            Addition(
                text="Wysiej wsiewkę lub międzyplon ozimy.",
                conditions=(_flag("harvest_by_august_end", False, "zbiór po sierpniu"),),
            ),
            Addition(text="Okrywa gleby po zbiorze jest też wymogiem normy GAEC 6."),
        ),
        gain=(
            "Okrywa chroni glebę przed wysychaniem i zmywaniem, zwiększa wsiąkanie wody "
            "i z czasem ilość próchnicy. Zimą zatrzymuje śnieg."
        ),
        citation=(
            f"{CDR}, s. 101–102 (zielona okrywa, poplony, międzyplony), s. 81 (retencja "
            f"śnieżna); {BASIS}; {NWRM}, środek A8 „Green cover”."
        ),
    ),
    CatalogRecommendation(
        id="crop_residue_mulch",
        title="Resztki pożniwne i mulcz na powierzchni",
        group="retencja glebowa",
        causes=("precipitation", "runoff", "soil"),
        requires=("balance",),
        text=(
            "Po zbiorze zostaw na powierzchni rozdrobnioną słomę i resztki roślin zamiast "
            "je od razu przyorywać."
        ),
        gain=(
            "Mulcz osłania glebę przed słońcem i wiatrem. Parowanie z gleby maleje o około 5% "
            "na każde 10% powierzchni przykrytej mulczem, czyli o około 25% przy pokryciu "
            "połowy powierzchni. Mulcz spowalnia też spływ wody podczas ulew."
        ),
        citation=(
            "FAO-56, rozdz. 10, „Organic mulches” (reguła 5% na 10%); "
            f"{CDR}, s. 99–101 (mulczowanie; „nawet o blisko 60%” przy pełnym pokryciu); "
            f"{NWRM}, środek A13 „Mulching”."
        ),
    ),
    CatalogRecommendation(
        id="organic_matter",
        title="Zwiększanie zawartości próchnicy",
        group="retencja glebowa",
        causes=("soil",),
        requires=("soil",),
        text=(
            "Gleba na tej Działce mieści mało wody ({available_water_mm_per_m} mm na metr). "
            "Regularnie wnoś materię organiczną: obornik, przyoraną słomę, międzyplony na "
            "zielony nawóz, rośliny bobowate i trawy w zmianowaniu."
        ),
        gain=(
            "Wzrost zawartości materii organicznej o 1 punkt procentowy zwiększa ilość wody "
            "zatrzymywanej w warstwie ornej o około 10 mm. To zmiana na lata: "
            "próchnica przyrasta powoli."
        ),
        citation=(
            f"{CDR}, s. 85 (10 mm na 1%, za Ryszkowski, Bałazy, Kędziora 2003), s. 78 (lista "
            f"zabiegów); {BASIS}; Minasny i in. 2017, tab. 1, s. 64–65 (przyrost węgla przy "
            "uprawie bezorkowej 0,05–0,51 t C/ha rocznie w badaniach trwających 3–34 lata)."
        ),
    ),
    CatalogRecommendation(
        id="reduced_tillage",
        title="Uprawa uproszczona lub bezorkowa",
        group="retencja glebowa",
        causes=("precipitation", "soil", "runoff"),
        requires=("balance",),
        text="Rozważ ograniczenie orki: spłycenie uprawy albo uprawę bezorkową, najlepiej razem z mulczem.",
        gain=(
            "Gleba nie przesycha po orce, woda opadowa wsiąka szybciej, a z czasem przybywa "
            "próchnicy. Mniejsze są też koszty uprawy."
        ),
        citation=(
            f"{CDR}, s. 102–103 (uprawa uproszczona); {BASIS} („ograniczanie intensywnej "
            f"uprawy”); {NWRM}, środki A6 „No till agriculture” i A7 „Low till agriculture”."
        ),
    ),
)

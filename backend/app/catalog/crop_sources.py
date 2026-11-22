"""Source texts shared by the crop catalogue entries (shown to the user, so in Polish).

Full references:
FAO-56: Allen R.G., Pereira L.S., Raes D., Smith M. (1998). Crop
  evapotranspiration: guidelines for computing crop water requirements. FAO
  Irrigation and Drainage Paper 56. Table 11 (lengths of growth stages),
  Table 12 (single crop coefficients Kc), Table 22 (maximum effective rooting
  depth Zr and depletion fraction p), Table 24 (yield response factor Ky).
COBORU: Centralny Osrodek Badania Odmian Roslin Uprawnych, "Wyniki
  porejestrowych doswiadczen odmianowych" (post-registration variety trials),
  tables of sowing, harvest and growth stage dates.
CDR 2025: Centrum Doradztwa Rolniczego (2025), e-poradnik "Melioracje,
  retencja i gospodarka wodna w rolnictwie", part IV.
IUNG: IUNG-PIB, System Monitoringu Suszy Rolniczej, crop groups of the
  climatic water balance thresholds.
"""

FAO56_TABLE_12 = "FAO-56 tab. 12"
FAO56_TABLE_22 = "FAO-56 tab. 22"
FAO56_TABLE_24 = "FAO-56 tab. 24 (współczynnik reakcji plonu Ky)"

COBORU = (
    "COBORU, Wyniki porejestrowych doświadczeń odmianowych, "
    "średnia z lat zbioru 2018-2022, 2024, 2025"
)
COBORU_VEGETABLES = "COBORU, Wyniki porejestrowych doświadczeń odmianowych, rośliny warzywne"
# Cereals: the late stage starts 30 days before full maturity.
COBORU_CEREALS = (
    f"{COBORU}; początek fazy końcowej = dojrzałość pełna - 30 dni "
    "(FAO-56 tab. 11, L_late zbóż)"
)

CDR = "CDR 2025, e-poradnik Melioracje, retencja i gospodarka wodna, cz. IV"
CDR_CEREALS = f"{CDR}, s. 229-230 (za Żarski 2006), gleby średnie"
CDR_MAIZE = f"{CDR}, s. 230"
CDR_LEGUMES = f"{CDR}, tab. 8 (Drupka 1980: oleiste i strączkowe zbierane w środku lata)"
CDR_VEGETABLES = (
    f"{CDR}, tab. 8 (Drupka 1980: warzywa 15 IV - 30 IX), przycięte do Sezonu uprawy"
)

IUNG_GROUPS = (
    "IUNG-PIB, System Monitoringu Suszy Rolniczej, grupy upraw w progach "
    "klimatycznego bilansu wodnego (https://susza.iung.pulawy.pl/progi/)"
)

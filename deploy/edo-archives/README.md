# Archiwa wskaźnika suszy (Combined Drought Indicator)

Roczne archiwa wskaźnika CDI Europejskiego Obserwatorium Suszy (EDO), z których usługa czyta tło suszowe.
Są w repozytorium po to, żeby aplikację dało się uruchomić od razu, bez osobnego pobierania danych.

- **Źródło:** katalog `EDO_Combined_Drought_Indicator` pod adresem
  `https://drought.emergency.copernicus.eu/data/Drought_Observatories_datasets/`.
- **Stan plików:** pobrane 21.11.2026; dekady od 01.01.2016 do 01.11.2026 (jedno archiwum na rok,
  `cdinx_m_edo_RRRR0101_RRRRMMDD_t.zip`, w środku jeden plik GeoTIFF na dekadę).
- **Pliki są niezmienione:** archiwa leżą tu w postaci pobranej ze źródła.

## Licencja i nota o źródle

Dane: Combined Drought Indicator (CDI), European Drought Observatory (EDO), Komisja Europejska,
Wspólne Centrum Badawcze (JRC); © Unia Europejska, 1995–2026. Usługa Copernicus Emergency Management Service.

Licencja: Creative Commons Uznanie autorstwa 4.0 Międzynarodowe (CC BY 4.0),
`https://creativecommons.org/licenses/by/4.0/`. Przy dalszym udostępnianiu trzeba podać źródło, wskazać licencję
i zaznaczyć ewentualne zmiany. Warunki korzystania z danych EDO: `https://drought.emergency.copernicus.eu/terms&conditions/`.

Nota wymagana przez warunki źródła:

> Generated using Copernicus Emergency Management Service information 2016–2026.

Dla danych zmienionych (np. przyciętych lub przeliczonych) obowiązuje brzmienie
„Contains modified Copernicus Emergency Management Service information [rok]".

## Rozpakowanie

Usługa czyta rozpakowane pliki GeoTIFF z katalogu `EDO_DATA_PATH` (domyślnie `./data/edo`), nie same archiwa.

- Skrypt wdrożenia `scripts/deploy.sh` rozpakowuje te archiwa sam, gdy katalog danych jest pusty
  (wymaga `python3` na serwerze).
- Ręcznie, w katalogu głównym repozytorium: `python3 scripts/unpack_drought_files.py deploy/edo-archives`
  (drugi argument to katalog docelowy, domyślnie `./data/edo`).

Restart usługi nie jest potrzebny: pliki są czytane przy każdej analizie.

## Aktualizacja

Nowa dekada pojawia się u źródła co 10 dni, z opóźnieniem. Dopóki nie ma pliku dla dekady Daty analizy,
raport podaje w Sprawdzeniu zgodności „brak danych".

1. Pobierz ze źródła aktualne archiwum bieżącego roku (jego nazwa kończy się datą ostatniej dekady,
   np. `cdinx_m_edo_20260101_20261111_t.zip`); w styczniu także pierwsze archiwum nowego roku.
2. Na działającym serwerze wystarczy rozpakować je do katalogu danych:
   `python3 scripts/unpack_drought_files.py KATALOG_Z_POBRANYM_ARCHIWUM` — skrypt dopisuje tylko brakujące pliki,
   istniejących o tym samym rozmiarze nie rusza.
3. Żeby nowy stan był też w repozytorium: zastąp w tym katalogu stare archiwum bieżącego roku nowym
   (jedno archiwum na rok), popraw wyżej „Stan plików" oraz datę stanu w tabeli źródeł danych w README
   i zatwierdź zmianę.

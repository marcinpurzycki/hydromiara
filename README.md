# Hydromiara

Narzędzie dla rolnika, które dla wskazanej działki ewidencyjnej i uprawy ocenia sytuację wodną
oraz przedstawia rekomendacje retencyjne, agrotechniczne i nawodnieniowe uzasadnione danymi.

## Zgłoszenie

| | |
|---|---|
| Wydarzenie | HackNation 2026, Bydgoszcz, 21–22 listopada 2026 r. |
| Zadanie | KOWR: „Zatrzymaj wodę, chroń plony – Inteligentne wsparcie gospodarowania wodą w rolnictwie" |
| Tytuł rozwiązania | Hydromiara |
| Zespół | Pair Pressure |
| Stan | prototyp w budowie |

## Autorstwo i wykorzystanie AI

Autorem rozwiązania jest zespół. Ludzie ustalają wymagania, podejmują decyzje projektowe, dobierają metody
i źródła danych, przeglądają każdą zmianę i odpowiadają za wynik. Narzędzia AI służą do pisania implementacji
według planu zespołu, pod nadzorem programisty.

Szczegółowy wykaz narzędzi i modeli AI oraz zakres ich użycia zostanie uzupełniony przed zgłoszeniem.

## Uruchomienie

Usługa `api` (FastAPI) wystawia wszystkie trasy pod `/api`. Wyszukiwanie działek (`/api/parcels/...`) korzysta
na żywo z usługi ULDK; pozostałe trasy na obecnym etapie odpowiadają danymi przykładowymi (atrapą) o docelowym
kształcie; gotowy raport przykładowy jest pod `/api/reports/demo`.
Opis interfejsu: `/api/docs` (Swagger UI) i `/api/openapi.json`.

Lokalnie, bez Dockera:

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/fastapi dev app/main.py        # http://127.0.0.1:8000/api/docs
.venv/bin/python -m pytest               # testy bez dostępu do sieci
.venv/bin/python -m tests.smoke.parcels_smoke   # sprawdzenie na żywej usłudze działek (wymaga sieci)
.venv/bin/python -m tests.smoke.satellite_smoke # sprawdzenie na żywym katalogu scen satelitarnych (wymaga sieci)
```

Lokalnie w Dockerze (API na `http://127.0.0.1:8000`):

```bash
cp .env.example .env                     # uzupełnij DOMAIN, TRAEFIK_ENTRYPOINT, TRAEFIK_CERTRESOLVER
docker network create proxy              # jednorazowo
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build api
```

Na serwerze za Traefikiem (istniejąca sieć `proxy`): `docker compose up -d --build`. Ruch dla `DOMAIN` trafia do
usługi `web`, a dla `DOMAIN` ze ścieżką `/api` do usługi `api`. Raporty są zapisywane w wolumenie `reports`,
a pliki wskaźnika suszy są czytane z katalogu `EDO_DATA_PATH` (domyślnie `./data/edo`).

## Biblioteki

| Biblioteka | Zastosowanie | Licencja |
|---|---|---|
| FastAPI | interfejs HTTP, opis OpenAPI | MIT |
| Pydantic | modele kontraktu i walidacja | MIT |
| Uvicorn | serwer aplikacji | BSD-3-Clause |
| pytest | testy | MIT |
| HTTPX | zapytania do źródeł danych, klient testowy | BSD-3-Clause |
| Shapely | geometria działki (WKT, GeoJSON, powierzchnia) | BSD-3-Clause |
| pyproj | przeliczenie układów współrzędnych (EPSG:4326 → EPSG:2180) | MIT |
| Rasterio (z biblioteką GDAL) | odczyt fragmentu rastra nad działką, maska obrysu, odczyt plików GeoTIFF wskaźnika CDI | BSD-3-Clause (GDAL: MIT) |
| NumPy | tablice wartości rastra (wymagane przez Rasterio) | BSD-3-Clause |

## Źródła danych

| Dane | Źródło | Tryb | Warunki wykorzystania |
|---|---|---|---|
| Działki ewidencyjne: identyfikator, położenie administracyjne, geometria | Główny Urząd Geodezji i Kartografii (GUGiK), Usługa Lokalizacji Działek Katastralnych (ULDK), `https://uldk.gugik.gov.pl/` | na żywo | bezpłatnie, bez rejestracji; wymagane podanie źródła; limit zapytań na adres IP |
| Pogoda dzienna do Daty analizy: suma opadu, ewapotranspiracja wskaźnikowa ET0 (FAO-56), średnia temperatura | Open-Meteo, archiwum pogodowe (reanaliza ERA5 / ECMWF IFS), `https://archive-api.open-meteo.com/v1/archive` | na żywo | dane na licencji CC BY 4.0, wymagane podanie źródła; bezpłatny dostęp bez klucza tylko do zastosowań niekomercyjnych; limit 600 zapytań na minutę, 5000 na godzinę i 10 000 na dobę |
| Tło suszowe: klasa wskaźnika Combined Drought Indicator (CDI) w komórce siatki działki, co dekadę, od 2016 r. | European Drought Observatory (EDO), Komisja Europejska, Wspólne Centrum Badawcze (JRC); © Unia Europejska, 1995–2026; `https://drought.emergency.copernicus.eu/data/Drought_Observatories_datasets/` (katalog `EDO_Combined_Drought_Indicator`) | plik lokalny: archiwa roczne rozpakowane do `EDO_DATA_PATH` poleceniem `python3 scripts/unpack_drought_files.py KATALOG_ARCHIWÓW`; stan plików na 21.11.2026, dekady od 01.01.2016 do 01.11.2026 | CC BY 4.0; wymagane podanie źródła i zaznaczenie zmian (pliki testowe w `backend/tests/fixtures/edo/` to wycinki 3 × 3 komórki bez metadanych) |
| Ukształtowanie terenu: siatka wysokości ok. 30 m wokół działki | Copernicus DEM GLO-30 (model pokrycia terenu z misji TanDEM-X, pomiary z lat 2011–2015; wysokości obejmują budynki i roślinność), pliki z `https://registry.opendata.aws/copernicus-dem/`, arkusz wyszukiwany w katalogu Earth Search (`https://earth-search.aws.element84.com/v1`, kolekcja `cop-dem-glo-30`) | na żywo | bezpłatnie dla każdego na warunkach licencji Copernicus DEM (GLO-30 Public), bez rejestracji; wymagane podanie źródła i informacji o prawach autorskich |
| Parametry wodne Upraw: współczynniki Kc, głębokość korzeni, dopuszczalne wyczerpanie wody w glebie (p) | Allen R.G., Pereira L.S., Raes D., Smith M. (1998), „Crop evapotranspiration: guidelines for computing crop water requirements”, FAO Irrigation and Drainage Paper 56, tabele 12 i 22 | wartości wpisane w kodzie (`backend/app/catalog/crop_data.py`), każda ze wskazaniem tabeli; wartości bez źródła są tam oznaczone jako robocze | publikacja FAO; wartości liczbowe przytoczone z podaniem źródła |
| Gleba w punkcie działki, warstwy do 100 cm: piasek, pył, ił, węgiel organiczny, zawartość wody przy 33 i 1500 kPa; z nich pojemność wodna (różnica zawartości wody, niezweryfikowana pomiarem na działce) | ISRIC – World Soil Information, SoilGrids 2.0 (model globalny, siatka 250 m), `https://rest.isric.org/soilgrids/v2.0/properties/query` | na żywo | CC BY 4.0, wymagane podanie źródła; usługa w fazie beta, bez gwarancji dostępności; limit 5 zapytań na minutę; zmierzony czas odpowiedzi 11–35 s |
| Obserwacje satelitarne do Daty analizy: klasyfikacja sceny (SCL) oraz pasma czerwone, bliskiej podczerwieni i krótkofalowej podczerwieni nad działką; z nich udział czystych pikseli, NDVI i NDMI | Copernicus Sentinel-2, poziom L2A (ESA / Komisja Europejska); wyszukiwanie scen: Earth Search (Element 84), `https://earth-search.aws.element84.com/v1`, kolekcja `sentinel-2-l2a`; pliki pasm (COG) w rejestrze otwartych danych AWS | na żywo | bezpłatny, pełny i otwarty dostęp na warunkach noty prawnej danych Sentinel (`https://sentinel.esa.int/documents/247904/690755/Sentinel_Data_Legal_Notice`); wymagane podanie źródła i zaznaczenie przetworzenia danych; bez klucza |

Źródło: Główny Urząd Geodezji i Kartografii (GUGiK), Usługa Lokalizacji Działek Katastralnych (ULDK).

Dane pogodowe: Open-Meteo.com (CC BY 4.0). Zawierają informacje usługi Copernicus Climate Change Service.

Wysokości terenu: produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved. Copernicus Digital Elevation Model (DEM) was accessed on 21.11.2026 from https://registry.opendata.aws/copernicus-dem.

Dane o glebie: ISRIC – World Soil Information, SoilGrids 2.0 (CC BY 4.0); Poggio, L. i in. (2021), SOIL 7, 217–240, doi:10.5194/soil-7-217-2021.

Obserwacje satelitarne: zawiera zmodyfikowane dane Copernicus Sentinel (2015–2026).

## Dokumentacja

W przygotowaniu: opis funkcjonalności i architektury, źródła danych z licencjami,
znane ograniczenia oraz sposób weryfikacji wyników.

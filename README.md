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
| Rasterio (z biblioteką GDAL) | odczyt fragmentu rastra nad działką, maska obrysu | BSD-3-Clause (GDAL: MIT) |
| NumPy | tablice wartości rastra | BSD-3-Clause |

## Źródła danych

| Dane | Źródło | Tryb | Warunki wykorzystania |
|---|---|---|---|
| Działki ewidencyjne: identyfikator, położenie administracyjne, geometria | Główny Urząd Geodezji i Kartografii (GUGiK), Usługa Lokalizacji Działek Katastralnych (ULDK), `https://uldk.gugik.gov.pl/` | na żywo | bezpłatnie, bez rejestracji; wymagane podanie źródła; limit zapytań na adres IP |
| Pogoda dzienna do Daty analizy: suma opadu, ewapotranspiracja wskaźnikowa ET0 (FAO-56), średnia temperatura | Open-Meteo, archiwum pogodowe (reanaliza ERA5 / ECMWF IFS), `https://archive-api.open-meteo.com/v1/archive` | na żywo | dane na licencji CC BY 4.0, wymagane podanie źródła; bezpłatny dostęp bez klucza tylko do zastosowań niekomercyjnych; limit 600 zapytań na minutę, 5000 na godzinę i 10 000 na dobę |

Źródło: Główny Urząd Geodezji i Kartografii (GUGiK), Usługa Lokalizacji Działek Katastralnych (ULDK).

Dane pogodowe: Open-Meteo.com (CC BY 4.0). Zawierają informacje usługi Copernicus Climate Change Service.

## Dokumentacja

W przygotowaniu: opis funkcjonalności i architektury, źródła danych z licencjami,
znane ograniczenia oraz sposób weryfikacji wyników.

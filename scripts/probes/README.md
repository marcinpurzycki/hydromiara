# Programy pomiarowe

Każdy program mierzy z danej maszyny czas i dostępność jednego rodzaju zewnętrznych źródeł danych
i zapisuje jeden plik wyniku `<temat>-probe-<host>-<czas UTC>.json` w katalogu bieżącym.
Programy nie czytają `.env`, nie wymagają kluczy ani kont i wysyłają na zewnątrz tylko obrysy działek testowych i daty.
Pliki wyników nie są śledzone przez git.

Wymagany jest tylko Docker. Komendy uruchamiaj z katalogu głównego repozytorium.

## Satelita (Sentinel-2)

Mierzy dwa bezpłatne serwery tego samego archiwum Sentinel-2 L2A: wyszukiwanie scen dla kilku szerokości okna dat
oraz równoległy odczyt 1, 4, 8 i 16 scen (sama klasyfikacja sceny, potem komplet pasm) dla trzech działek
z różnych regionów, każde zapytanie trzy razy. Trwa około 10 minut, zależnie od łącza.

```bash
docker run --rm -e PROBE_HOST="$(hostname)" -v "$PWD":/work -w /work python:3.12 \
  sh -c "pip install -q --root-user-action=ignore rasterio==1.5.2 && python scripts/probes/satellite_probe.py"
```

Wynik: `satellite-probe-<host>-<czas UTC>.json`. Plik powstaje także wtedy, gdy część zapytań się nie uda
albo program zostanie przerwany (`Ctrl-C`).

| Co | Źródło | Warunki wykorzystania |
|---|---|---|
| Katalog scen i pliki pasm | Element 84 Earth Search, `https://earth-search.aws.element84.com/v1`, pliki w zasobie AWS Open Data `sentinel-cogs` | bezpłatnie, bez konta, bez gwarancji dostępności |
| Katalog scen i pliki pasm | Microsoft Planetary Computer, `https://planetarycomputer.microsoft.com/api/stac/v1`, odczyt plików z bezpłatnym tokenem pobieranym bez konta | bezpłatnie, bez konta |
| Dane Sentinel-2 | program Copernicus (ESA, Komisja Europejska) | dostęp bezpłatny, pełny i otwarty; wymagana informacja o źródle: „Contains modified Copernicus Sentinel data [rok]" |
| Biblioteka Rasterio | odczyt wycinków rastrów | BSD-3-Clause |

## Wody (rowy, cieki, zbiorniki)

Sprawdza każde kandydujące źródło danych o wodach w promieniu 500 m od środka trzech działek z różnych regionów,
każde zapytanie trzy razy: cztery publiczne serwery Overpass (dane OpenStreetMap), odczyt wycinka krajowych plików
BDOT10k wprost z serwera GUGiK (rowy melioracyjne, rzeki i strumienie, kanały, wody powierzchniowe), usługę WMS
BDOT10k oraz usługę WMS Mapy Podziału Hydrograficznego Polski. Mierzy też szybkość pobierania plików BDOT10k,
żeby oszacować czas pobrania całego kraju. Trwa około 8 minut.

```bash
docker run --rm -e PROBE_HOST="$(hostname)" -v "$PWD":/work -w /work python:3.12 \
  sh -c "pip install -q --root-user-action=ignore pyarrow==26.0.1 && python scripts/probes/water_probe.py"
```

Wynik: `water-probe-<host>-<czas UTC>.json`. Plik powstaje także wtedy, gdy część zapytań się nie uda
albo program zostanie przerwany (`Ctrl-C`).

| Co | Źródło | Warunki wykorzystania |
|---|---|---|
| Cieki, rowy i zbiorniki z OpenStreetMap | serwery Overpass API: `overpass-api.de`, `overpass.private.coffee`, `maps.mail.ru`, `overpass.openstreetmap.fr` | dane na licencji ODbL 1.0, wymagane podanie źródła „© autorzy OpenStreetMap"; serwery bezpłatne, bez konta, bez gwarancji dostępności |
| Baza Danych Obiektów Topograficznych BDOT10k, pliki klas obiektów dla całego kraju | GUGiK, `https://opendata.geoportal.gov.pl/bdot10k/schemat2021/GeoParquet/` | bezpłatnie, bez konta |
| BDOT10k, usługa przeglądania WMS | GUGiK, `https://mapy.geoportal.gov.pl/wss/service/pub/guest/kompozycja_BDOT10k_WMS/MapServer/WMSServer` | bezpłatnie; usługa zabrania automatycznego pobierania i gromadzenia obrazów oraz opisów obiektów |
| Mapa Podziału Hydrograficznego Polski, usługa WMS | Wody Polskie, `https://wody.isok.gov.pl/gpservices/KZGW/ISOK_MPHP/MapServer/WMSServer` | bezpłatnie, bez konta |
| Biblioteka PyArrow | odczyt plików Parquet | Apache-2.0 |

## Teren (model wysokości)

Sprawdza cztery drogi do wysokości terenu dla trzech działek z różnych regionów, każde zapytanie trzy razy:
usługę WCS modelu terenu 1 m GUGiK (sześć form zapytania `GetCoverage`, okna od 100 m do 1 km, limit 90 s),
usługę wysokości punktów GUGiK (siatka punktów co 5 m i co 2 m), całe arkusze modelu 1 m wskazane przez skorowidz WFS
oraz model Copernicus 30 m. Dla każdej udanej odpowiedzi liczy spadek, kierunek spadku i najniższy punkt działki,
żeby dało się porównać źródła. Zapytania WCS idą równolegle. Trwa do 15 minut; pobiera około 400 MB.

```bash
docker run --rm -e PROBE_HOST="$(hostname)" -v "$PWD":/work -w /work python:3.12 \
  sh -c "pip install -q --root-user-action=ignore rasterio==1.5.2 && python scripts/probes/terrain_probe.py"
```

Wynik: `terrain-probe-<host>-<czas UTC>.json`. Plik powstaje także wtedy, gdy część zapytań się nie uda
albo program zostanie przerwany (`Ctrl-C`).

| Co | Źródło | Warunki wykorzystania |
|---|---|---|
| Numeryczny model terenu 1 m, usługi WCS | GUGiK, `https://mapy.geoportal.gov.pl/wss/service/PZGIK/NMT/GRID1/WCS/DigitalTerrainModelFormatTIFF` i `.../DigitalTerrainModel` | bezpłatnie, bez konta; dane NMT „dostępne bezpłatnie i możliwe do dowolnego wykorzystania" (geoportal.gov.pl) |
| Wysokość punktów z numerycznego modelu terenu | GUGiK, `https://services.gugik.gov.pl/nmt/` | bezpłatnie, bez konta |
| Arkusze numerycznego modelu terenu i ich skorowidz | GUGiK, skorowidz WFS `https://mapy.geoportal.gov.pl/wss/service/PZGIK/NumerycznyModelTerenuEVRF2007/WFS/Skorowidze`, pliki `https://opendata.geoportal.gov.pl/NumDaneWys/NMT/` | bezpłatnie, bez konta |
| Copernicus DEM GLO-30 | zasób AWS Open Data `copernicus-dem-30m`, adres pliku z katalogu Element 84 Earth Search (kolekcja `cop-dem-glo-30`) | bezpłatnie; wymagana informacja: „© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved" |
| Biblioteka Rasterio (z NumPy) | odczyt rastrów i przeliczenia współrzędnych | BSD-3-Clause |

## Wydajność (czas źródeł i całej analizy)

Dla dziesięciu działek z różnych województw mierzy główne źródła jednej analizy: obrys działki (ULDK), pogodę
z 10 lat (Open-Meteo), kategorię podatności gleby na suszę w 25 punktach (IUNG-PIB), uziarnienie gleby (SoilGrids,
20 warstw), wysokości terenu w siatce punktów (GUGiK) oraz sceny Sentinel-2 z sześciu okien dat (Planetary Computer).
Każde źródło jest pytane osobno, a potem wszystkie naraz, tak jak w analizie; całość dwa razy. Źródła zapasowe
i wody mierzą programy opisane wyżej. Trwa około 6 minut.

```bash
docker run --rm -e PROBE_HOST="$(hostname)" -v "$PWD":/work -w /work python:3.12 \
  sh -c "pip install -q --root-user-action=ignore rasterio==1.5.2 && python scripts/probes/performance_probe.py"
```

Gdy usługa API działa, jej adres podany jako jedyny argument dodaje pomiar całych analiz (`POST /api/analyses`
do zakończenia): po jednej dla każdej działki i trzy naraz. Program zapisuje czas całości i chwilę, w której
każde źródło skończyło pracę. Trwa wtedy około 10 minut. Przykład dla usługi dostępnej na tym samym komputerze
pod portem 8000:

```bash
docker run --rm --network host -e PROBE_HOST="$(hostname)" -v "$PWD":/work -w /work python:3.12 \
  sh -c "pip install -q --root-user-action=ignore rasterio==1.5.2 && \
         python scripts/probes/performance_probe.py http://127.0.0.1:8000"
```

Wynik: `performance-probe-<host>-<czas UTC>.json`. Plik powstaje także wtedy, gdy część zapytań się nie uda
albo program zostanie przerwany (`Ctrl-C`). Jeden przebieg zużywa około połowy godzinowego limitu bezpłatnego
archiwum Open-Meteo dla adresu IP komputera, więc nie uruchamiaj go częściej niż raz na godzinę.

| Co | Źródło | Warunki wykorzystania |
|---|---|---|
| Obrys działki | ULDK GUGiK, `https://uldk.gugik.gov.pl/` | bezpłatnie, bez konta |
| Pogoda dzienna z 10 lat | Open-Meteo, `https://archive-api.open-meteo.com/v1/archive` | dane CC BY 4.0; bezpłatny dostęp tylko do użytku niekomercyjnego, z limitem zapytań na adres IP |
| Kategoria podatności gleb na suszę | IUNG-PIB, usługa WMS `https://sgeo.iung.pl/geoserver/ows`, warstwa `Susza:katgl_landuse2024` | usługa publiczna i bezpłatna; warunków ponownego wykorzystania nie opublikowano |
| Uziarnienie i węgiel organiczny gleby | ISRIC SoilGrids 2.0, usługa WCS `https://maps.isric.org/mapserv` | CC BY 4.0 |
| Wysokość punktów z numerycznego modelu terenu | GUGiK, `https://services.gugik.gov.pl/nmt/` | bezpłatnie, bez konta |
| Katalog scen i pliki pasm Sentinel-2 | Microsoft Planetary Computer, jak w sekcji „Satelita" | bezpłatnie, bez konta; dane programu Copernicus |
| Biblioteka Rasterio | odczyt wycinków rastrów i przeliczenia współrzędnych | BSD-3-Clause |

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

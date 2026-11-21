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

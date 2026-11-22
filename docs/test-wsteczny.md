# Test wsteczny

Zwykłe analizy dla 16 działek z 16 województw i dat z lat o znanym przebiegu, wykonane narzędziem
`scripts/backtest.py` tym samym kodem i na tych samych żywych źródłach co analiza z aplikacji.

- **Kiedy i skąd:** 22.11.2026, z serwera wersji pokazowej, kod z gałęzi `main` w wersji `6f748f4`.
- **Wejście:** `scripts/examples/backtest_parcels.csv` (43 wiersze). Uprawa: pszenica ozima. Dla każdej działki
  jeden rok z suszą i jeden bez suszy według raportów Systemu Monitoringu Suszy Rolniczej IUNG-PIB, dzień 20 czerwca
  (leży w Okresie krytycznym i jest ostatnim dniem dekady wskaźnika CDI); do tego sześć dat sprzed 2020 r. opisanych
  tylko wskaźnikiem CDI oraz pięć dat poza Okresem krytycznym (spoczynek, po zbiorze, ostatni pełny dzień).
- **Powtórzenie:** `EDO_DATA_PATH=./data/edo backend/.venv/bin/python scripts/backtest.py scripts/examples/backtest_parcels.csv`
  (polecenie dla kontenera: README, punkt 1, „Narzędzia”). Źródła są żywe, więc powtórzenie w innym dniu może dać
  nieco inne liczby.

## Wynik w skrócie

- Wszystkie 43 analizy zakończyły się raportem, każda w budżecie 30 s: od 6,66 do 13,13 s, mediana 9,77 s.
- Pojemność wodna gleby pochodziła w każdej analizie z mapy kategorii podatności gleb na suszę IUNG-PIB; teren
  w każdej z modelu 1 m. Bez danych o wodach skończyło się 7 analiz, bez odczytu satelitarnego 3.
- Sprawdzenie zgodności z niezależnym wskaźnikiem suszy CDI: „zgodne” 22, „rozbieżne” 15, „brak danych” 6.
- **Lata i daty opisane jako suche** (19 analiz z 20 czerwca): Bieżąca sytuacja wodna wskazała niedobór w 17;
  Sprawdzenie zgodności: „zgodne” 15, „rozbieżne” 3, „brak danych” 1.
- **Lata i daty opisane jako mokre** (18 analiz z 20 czerwca): Bieżąca sytuacja wodna wskazała niedobór w 11,
  za każdym razem przy klasie CDI 0 (brak suszy); Sprawdzenie zgodności: „zgodne” 5, „rozbieżne” 11, „brak danych” 2.
- **Podatność wieloletnia:** w 30 z 43 analiz wyszło 8–10 lat z niedoborem na 10, a tylko w 5 co najwyżej 2 lata.

## Co z tego wynika

- Rozwiązanie rozpoznaje lata suche: tam, gdzie niezależne źródła mówią o suszy, raport prawie zawsze pokazuje
  wyraźny albo silny niedobór, a Sprawdzenie zgodności to potwierdza.
- **Rozwiązanie zawyża niedobór.** W latach bez suszy Bieżąca sytuacja wodna często nadal wskazuje niedobór,
  a liczba lat z niedoborem jest dla większości działek bliska 10 na 10. Przyczyną jest robocza reguła roku
  z niedoborem („co najmniej 10 dni z brakiem wody w Okresie krytycznym”) i robocze progi Stopni niedoboru
  (README, punkt 8). Wynik „rozbieżne” w Sprawdzeniu zgodności jest w takich raportach uzasadniony i obniża
  Pewność oceny.
- Wynik „bez niedoboru” w obu werdyktach dały tylko dwie działki, obie na glebach najlepiej magazynujących wodę
  (kategoria IV).
- Test obejmuje jedną Uprawę i 16 działek; nie jest próbą reprezentatywną. Nie porównano w nim raportów
  rok po roku z tabelami gminnymi IUNG-PIB.

## Tabela wyników

Kolumny: Stopień niedoboru Bieżącej sytuacji wodnej i jego Pewność oceny; liczba lat z niedoborem i Pewność
Podatności wieloletniej; klasa CDI ostatniej dekady zakończonej nie później niż Data analizy (0 brak suszy,
1 obserwacja, 2 ostrzeżenie, 3 alarm, 4–6 stany przejściowe); wynik Sprawdzenia zgodności; źródła bez danych;
czas analizy.

| Działka | Województwo | Data analizy | Opis daty | Bieżąca sytuacja wodna | Pewność | Lata z niedoborem | Pewność | CDI | Sprawdzenie zgodności | Bez danych | Czas, s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `040704_2.0020.34/2` | kujawsko-pomorskie | 20.06.2023 | rok z suszą | silny niedobór | wysoka | 10 z 10 | wysoka | 2 | zgodne | — | 7,85 |
| `040704_2.0020.34/2` | kujawsko-pomorskie | 20.06.2021 | rok bez suszy | wyraźny niedobór | średnia | 8 z 10 | wysoka | 0 | rozbieżne | — | 8,94 |
| `220404_2.0003.101/1` | pomorskie | 20.06.2023 | rok z suszą | silny niedobór | wysoka | 6 z 10 | wysoka | 2 | zgodne | — | 12,14 |
| `220404_2.0003.101/1` | pomorskie | 20.06.2020 | rok bez suszy | w normie | wysoka | 7 z 10 | średnia | 0 | zgodne | — | 11,82 |
| `120611_5.0008.980` | małopolskie | 20.06.2022 | rok z suszą | w normie | niska | 2 z 10 | średnia | 2 | rozbieżne | — | 10,02 |
| `120611_5.0008.980` | małopolskie | 20.06.2021 | rok bez suszy | w normie | średnia | 2 z 10 | średnia | 0 | zgodne | — | 11 |
| `061605_2.0005.88` | lubelskie | 20.06.2024 | rok z suszą | wyraźny niedobór | średnia | 10 z 10 | średnia | 2 | zgodne | — | 13,04 |
| `061605_2.0005.88` | lubelskie | 20.06.2020 | rok bez suszy | w normie | średnia | 8 z 10 | średnia | 4 | brak danych | — | 7,24 |
| `142604_2.0025.73` | mazowieckie | 20.06.2024 | rok z suszą | wyraźny niedobór | wysoka | 10 z 10 | wysoka | 2 | zgodne | — | 10,76 |
| `142604_2.0025.73` | mazowieckie | 20.06.2021 | rok bez suszy | wyraźny niedobór | średnia | 9 z 10 | wysoka | 0 | rozbieżne | — | 9,77 |
| `200602_2.0025.88` | podlaskie | 20.06.2023 | rok z suszą | wyraźny niedobór | wysoka | 10 z 10 | wysoka | 2 | zgodne | wody | 12,62 |
| `200602_2.0025.88` | podlaskie | 20.06.2025 | rok bez suszy | silny niedobór | średnia | 10 z 10 | wysoka | 0 | rozbieżne | wody | 12,82 |
| `280502_2.0013.71` | warmińsko-mazurskie | 20.06.2023 | rok z suszą | wyraźny niedobór | średnia | 8 z 10 | średnia | 2 | zgodne | satelita | 8,02 |
| `280502_2.0013.71` | warmińsko-mazurskie | 20.06.2020 | rok bez suszy | lekki niedobór | niska | 7 z 10 | średnia | 0 | rozbieżne | satelita | 7,38 |
| `260504_5.0004.33` | świętokrzyskie | 20.06.2023 | rok z suszą | wyraźny niedobór | wysoka | 9 z 10 | wysoka | 2 | zgodne | — | 9,89 |
| `260504_5.0004.33` | świętokrzyskie | 20.06.2020 | rok bez suszy | w normie | średnia | 8 z 10 | średnia | 4 | brak danych | — | 10,79 |
| `301007_5.0020.453` | wielkopolskie | 20.06.2023 | rok z suszą | silny niedobór | wysoka | 10 z 10 | wysoka | 3 | zgodne | — | 8,59 |
| `301007_5.0020.453` | wielkopolskie | 20.06.2025 | rok bez suszy | silny niedobór | średnia | 10 z 10 | wysoka | 0 | rozbieżne | — | 9,29 |
| `321005_2.0008.183/1` | zachodniopomorskie | 20.06.2023 | rok z suszą | silny niedobór | średnia | 10 z 10 | wysoka | 4 | brak danych | — | 9,65 |
| `321005_2.0008.183/1` | zachodniopomorskie | 20.06.2021 | rok bez suszy | silny niedobór | średnia | 10 z 10 | średnia | 0 | rozbieżne | — | 8,22 |
| `022305_2.0008.9/3` | dolnośląskie | 20.06.2022 | rok z suszą | wyraźny niedobór | wysoka | 7 z 10 | wysoka | 2 | zgodne | — | 7,44 |
| `022305_2.0008.9/3` | dolnośląskie | 20.06.2021 | rok bez suszy | lekki niedobór | średnia | 6 z 10 | wysoka | 0 | rozbieżne | — | 8,84 |
| `240205_2.0013.1472/6` | śląskie | 20.06.2022 | rok z suszą | w normie | średnia | 1 z 10 | średnia | 2 | rozbieżne | — | 10,05 |
| `240205_2.0013.1472/6` | śląskie | 20.06.2021 | rok bez suszy | w normie | wysoka | 1 z 10 | średnia | 0 | zgodne | wody | 13,13 |
| `101406_2.0025.13` | łódzkie | 20.06.2023 | rok z suszą | silny niedobór | wysoka | 10 z 10 | wysoka | 1 | zgodne | — | 10,13 |
| `101406_2.0025.13` | łódzkie | 20.06.2025 | rok bez suszy | wyraźny niedobór | średnia | 10 z 10 | wysoka | 0 | rozbieżne | — | 10,11 |
| `081202_5.0007.533/6` | lubuskie | 20.06.2023 | rok z suszą | silny niedobór | średnia | 10 z 10 | wysoka | 0 | rozbieżne | — | 8,42 |
| `081202_5.0007.533/6` | lubuskie | 20.06.2021 | rok bez suszy | silny niedobór | średnia | 9 z 10 | wysoka | 0 | rozbieżne | — | 8,35 |
| `160702_2.0013.137/1` | opolskie | 20.06.2026 | rok z suszą | wyraźny niedobór | wysoka | 9 z 10 | wysoka | 2 | zgodne | wody | 12,77 |
| `160702_2.0013.137/1` | opolskie | 20.06.2021 | rok bez suszy | lekki niedobór | średnia | 5 z 10 | wysoka | 0 | rozbieżne | — | 10,95 |
| `182001_5.0011.742` | podkarpackie | 20.06.2024 | rok z suszą | wyraźny niedobór | średnia | 10 z 10 | średnia | 2 | zgodne | wody | 12,56 |
| `182001_5.0011.742` | podkarpackie | 20.06.2021 | rok bez suszy | silny niedobór | niska | 10 z 10 | średnia | 0 | rozbieżne | wody | 12,45 |
| `301007_5.0020.453` | wielkopolskie | 20.06.2019 | sprzed 2020 r., susza według CDI | silny niedobór | wysoka | 10 z 10 | średnia | 2 | zgodne | — | 9,59 |
| `081202_5.0007.533/6` | lubuskie | 20.06.2019 | sprzed 2020 r., susza według CDI | silny niedobór | wysoka | 9 z 10 | średnia | 2 | zgodne | — | 8,53 |
| `022305_2.0008.9/3` | dolnośląskie | 20.06.2018 | sprzed 2020 r., susza według CDI | wyraźny niedobór | wysoka | 6 z 10 | średnia | 2 | zgodne | — | 6,66 |
| `142604_2.0025.73` | mazowieckie | 20.06.2018 | sprzed 2020 r., CDI słabo | silny niedobór | wysoka | 9 z 10 | średnia | 1 | zgodne | — | 8,8 |
| `022305_2.0008.9/3` | dolnośląskie | 20.06.2017 | sprzed 2020 r., bez suszy według CDI | w normie | wysoka | 5 z 10 | średnia | 0 | zgodne | — | 7,94 |
| `220404_2.0003.101/1` | pomorskie | 20.06.2017 | sprzed 2020 r., bez suszy według CDI | w normie | wysoka | 8 z 10 | średnia | 0 | zgodne | — | 10,89 |
| `040704_2.0020.34/2` | kujawsko-pomorskie | 25.11.2016 | spoczynek, 10 lat wstecz | Zapas wody w glebie: w normie | średnia | 8 z 10 | średnia | 0 | zgodne | satelita | 7,87 |
| `101406_2.0025.13` | łódzkie | 15.11.2023 | spoczynek po suchym sezonie | Zapas wody w glebie: w normie | średnia | 10 z 10 | średnia | 5 | brak danych | — | 9,67 |
| `200602_2.0025.88` | podlaskie | 31.08.2024 | po zbiorze | Zapas wody w glebie: w normie | niska | 10 z 10 | wysoka | 1 | rozbieżne | wody | 12,82 |
| `321005_2.0008.183/1` | zachodniopomorskie | 21.11.2026 | ostatni pełny dzień | Zapas wody w glebie: w normie | średnia | 10 z 10 | średnia | — | brak danych | — | 8,25 |
| `240205_2.0013.1472/6` | śląskie | 21.11.2026 | ostatni pełny dzień | Zapas wody w glebie: w normie | średnia | 1 z 10 | wysoka | — | brak danych | — | 10,66 |

Tło suszowe: wygenerowano z użyciem informacji usługi Copernicus Emergency Management Service
(Generated using Copernicus Emergency Management Service information 2016–2026).

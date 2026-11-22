# Hydromiara: metoda oceny

Szczegółowy opis tego, jak aplikacja dochodzi do treści raportu. Skrót i pozostałe części dokumentacji są
w [README](../README.md). Wszystkie reguły poniżej wykonuje deterministyczny kod w `backend/app/engine/`
(bez sieci, bez zegara, bez bazy): te same dane wejściowe dają ten sam raport.

Wartość, która nie ma źródła naukowego, jest w kodzie oznaczona komentarzem `PROVISIONAL` (wartość robocza)
i zebrana w pliku parametrów swojego modułu, więc jej wymiana jest zmianą danych, a nie kodu. Pliki z wartościami
roboczymi: `backend/app/engine/params.py`, `cause_params.py`, `consistency_params.py`, `findings.py`,
`irrigation_params.py`, `soil_capacity.py`, `soil_limitations.py`, `water_params.py`, `backend/app/catalog/crop_data.py`, `recommendation_data.py`,
`backend/app/sources/hydro_params.py`, `satellite_params.py`, `soil_params.py`, `terrain_params.py`,
`weather_params.py`, `raster.py`,
`backend/app/storage/params.py`, `backend/app/summary/params.py`.

## Katalog Upraw

Zamknięta lista ma 21 Upraw i Pole bez uprawy (`backend/app/catalog/`: model w `crop_model.py`, dane
w `crop_data*.py`, funkcje w `crops.py`). Każda wartość ma w danych tekst źródła, a wartość przyjęta przez analogię
albo roboczo także powód; pozycja z taką wartością jest oznaczona jako warunkowa (`conditional`).

- **Kc, głębokość korzeni, p, Ky**: FAO-56, tabele 12, 22 i 24, wiersz gatunku albo grupy. Dla zbóż ozimych
  Kc początkowe 0,4 (wariant dla gleb zamarzających), Kc końcowe zbóż 0,25 (dolna wartość zakresu; wyższa dotyczy
  zbioru ręcznego), Kc końcowe kukurydzy na ziarno 0,60 (zbiór przy wysokiej wilgotności ziarna).
- **Sezon uprawy i daty faz**: średnie daty siewu, wschodów, wiosennego ruszenia wegetacji, kłoszenia lub początku
  kwitnienia, dojrzałości i zbioru z doświadczeń odmianowych COBORU. Faza środkowa krzywej Kc zaczyna się dla zbóż
  w dniu kłoszenia, dla strączkowych i rzepaku na początku kwitnienia (FAO-56, rozdz. 5); faza końcowa zbóż 30 dni
  przed dojrzałością pełną. Dla kukurydzy, ziemniaka, buraków i warzyw długości faz pochodzą z tabeli 11 FAO-56,
  odłożone od polskiej daty siewu lub sadzenia (dla buraków i warzyw przeskalowane do długości sezonu).
- **Krzywa Kc w roku**: od siewu do końca wschodów wzrost od wartości gołej gleby do Kc początkowego; do początku
  rozwoju Kc początkowe (u ozimin spoczynek zimowy); liniowy wzrost do Kc środkowego; faza środkowa; liniowy spadek
  do Kc końcowego, który kończy się w dniu dojrzałości, jeśli katalog ją podaje, a inaczej w dniu zbioru. Poza
  sezonem obowiązuje współczynnik gołej gleby 0,3 (wartość robocza).
- **Okres krytyczny**: e-poradnik CDR (2025), część IV; dla zbóż wariant dla gleb średnich; dla warzyw jeden wspólny
  okres 15 kwietnia – 30 września, przycięty do Sezonu uprawy.
- **Uprawa wieloletnia** (łąka lub pastwisko) jest opisana tym samym modelem: „siew” to początek, a „zbiór” koniec
  okresu wegetacji.

## Bilans wodny i dwa werdykty

Podstawą obu werdyktów jest dzienny bilans wody w strefie korzeniowej według FAO-56, rozdział 8
(`backend/app/engine/balance.py`, `root_zone.py`; równania 80, 82–86 i 88): woda dostępna dla roślin (TAW), woda
łatwo dostępna (RAW = p · TAW), wyczerpanie strefy korzeniowej (Dr) i współczynnik stresu wodnego Ks; ewapotranspiracja
uprawy to Ks · Kc · ET0. Opad i ET0 pochodzą z archiwum pogodowego, współczynnik Kc z katalogu upraw (krzywa
w ciągu roku z dat faz), pojemność wodna z kategorii gleby (niżej). Seria zaczyna się przed Oknem wieloletnim (rozruch
bilansu), a dni po Dacie analizy są odrzucane na wejściu, więc wynik dla danej daty nie zależy od późniejszych danych.

Seria pogodowa kończy się na Dacie analizy. Wyjątkiem jest analiza na dzień bieżący: wtedy ostatnim dniem serii jest
dzień poprzedni (według czasu polskiego), bo dzień bieżący jeszcze trwa, a archiwum podaje jego sumy jako wynik modelu
na resztę doby. Bieżąca sytuacja wodna opisuje wtedy stan z końca dnia poprzedniego i raport podaje ten dzień wprost
(w nagłówku, w uzasadnieniu werdyktu i zdaniem „Dane pogodowe kończą się wczoraj”). Z archiwum pobierane są tylko
opad i ET0; średnia temperatura nie jest pobierana, bo bilans jej nie używa.

Uproszczenia: bez spływu powierzchniowego, podsiąku i nawodnień; stała głębokość korzeni; współczynnik p bez
korekty na wielkość ewapotranspiracji; strefa korzeniowa ograniczona do 100 cm i brana z większego końca zakresu
FAO-56 (tabela 22, przypis 1: większe wartości dla upraw bez nawadniania); bilans zaczyna od pojemności polowej.

Pojemność wodna gleby (`backend/app/engine/soil_capacity.py`, `backend/app/sources/soil.py`) pochodzi z Łańcucha
zamienników:

1. **Kategoria podatności gleby na suszę IUNG-PIB** (I–IV), odczytana z mapy w siatce do 25 punktów wewnątrz
   obrysu Działki. Pojemność kategorii: I 110, II 149, III 186, IV 220 mm wody dostępnej na metr gleby (wartości
   robocze wewnątrz przedziałów IUNG-PIB: poniżej 127,5; 127,5–169,9; 170–202,5; powyżej 202,5 mm). Pojemność
   Działki to średnia ważona liczbą punktów z kategorią. Ogniwo jest spełnione, gdy kategorię ma co najmniej
   połowa punktów (wartość robocza). Działkę o kilku kategoriach raport opisuje udziałami.
2. **Kategoria oszacowana z uziarnienia**: piasek, ił i węgiel organiczny z map SoilGrids (warstwy do 100 cm,
   środek Działki) przeliczone wzorami Saxtona i Rawlsa (2006, równania 1 i 2) na pojemność profilu; próchnica
   z węgla organicznego (× 1,724), ograniczona do 3,5% (wartość robocza). Wzór daje wartości na niższej skali niż
   kategorie IUNG-PIB, więc do bilansu idzie pojemność kategorii szacowanej (progi 85, 113 i 135 mm na metr,
   wartości robocze), a nie wynik wzoru. Zawartości wody przy 33 i 1500 kPa z SoilGrids nie są używane: nie
   odróżniają piasków od glin.
3. **Wartość zastępcza** 150 mm na metr, gdy żadne źródło nie dało danych albo mapa oznacza Działkę jako glebę
   organiczną, której model nie opisuje.

Uziarnienie jest pobierane także wtedy, gdy mapa IUNG-PIB dała kategorię: gdy oba źródła różnią się o dwie
kategorie lub więcej, raport podaje to jako Ograniczenie (do bilansu idzie kategoria z mapy). Ograniczenia
i Pewność oceny: kategoria z mapy to stałe Ograniczenie bez wpływu na Pewność; kategoria szacowana i rozbieżność
źródeł liczą się za 1 punkt, wartość zastępcza za 2.

- **Bieżąca sytuacja wodna** wynika ze współczynnika Ks w dniu Daty analizy. Stopnie niedoboru (wartości robocze):
  Ks równe 1 to „w normie”, od 0,75 „lekki niedobór”, od 0,4 „wyraźny niedobór”, poniżej „silny niedobór”.
- **Podatność wieloletnia** to liczba lat z niedoborem w Oknie wieloletnim: 10 ostatnich Okresach krytycznych
  rozpoczętych nie później niż Data analizy (ostatni może być częściowy). Rok z niedoborem to rok, w którym
  w Okresie krytycznym było co najmniej 10 dni z wyczerpaniem ponad wodę łatwo dostępną (wartość robocza; wiadomo,
  że jest zbyt czuła: na działce próbnej dała 9 lat z 10). Stopnie niedoboru (wartości robocze): 0–2 lata „w normie”,
  3–4 „lekki niedobór”, 5–7 „wyraźny niedobór”, 8–10 „silny niedobór”. Lata bez danych pogodowych nie są oceniane.
- Oba werdykty są osobne i nigdy nie są uśredniane. Dla Pola bez uprawy bilans jest liczony, ale żaden werdykt nie
  dostaje Stopnia niedoboru (nie ma dla niego reguły); raport mówi to wprost.

## Pewność oceny i Ograniczenia raportu

Każdy raport podaje Pewność oceny osobno dla Bieżącej sytuacji wodnej i dla Podatności wieloletniej (wysoka, średnia,
niska) razem z powodami oraz pełną listę Ograniczeń raportu. Ograniczenia stałe (raport nie jest urzędowym stwierdzeniem
suszy rolniczej, nie ocenia nadmiaru wody, nie korzysta z prognozy pogody, publiczne dane o rowach są niekompletne,
pogoda pochodzi z modelu o siatce około 9 km, a nie z deszczomierza na polu, i model ten podaje przeciętnie
o kilkanaście procent więcej opadu niż pomiary IMGW; bilans obejmuje glebę do głębokości 1 m) są w każdym raporcie i Pewności nie obniżają. Nie obniża jej też
zdanie o serii pogodowej kończącej się wczoraj w analizie na dzień bieżący: to stan każdej takiej analizy, a nie
brak danych. Pozostałe wynikają z danych tej analizy: brak kategorii danych, dane
z mniej dokładnego zamiennika (Łańcuch zamienników: źródło podstawowe, zamiennik, brak danych), pojemność wodna gleby
oszacowana z uziarnienia albo przyjęta zastępczo, dane pogodowe kończące się przed Datą analizy (dla analizy na dzień bieżący: co najmniej 2 dni
przed nią), dni bez pogody, niepełne Okno wieloletnie.
Pewność werdyktu obniżają tylko Ograniczenia, które go dotyczą (Ograniczenia odczytu satelitarnego opisuje sekcja
„Odczyt satelitarny”). Reguła jest robocza i nie ma źródła naukowego:
Ograniczenie liczy się za 1 punkt, pojemność wodna przyjęta zastępczo i wynik „rozbieżne” Sprawdzenia zgodności
za 2; od 1 punktu Pewność jest średnia, od 3 niska; werdykt bez oceny ma Pewność niską. Wagi i progi są nazwanymi
parametrami w `backend/app/engine/findings.py`.

## Sprawdzenie zgodności

Każdy raport zawiera Sprawdzenie zgodności: Bieżąca sytuacja wodna jest zestawiana z niezależnym wskaźnikiem suszy
CDI (European Drought Observatory) i pokazywana obok odczytu satelitarnego z tego samego okresu. Wynik to „zgodne”,
„rozbieżne” albo „brak danych”, ze zdaniem opisującym, co z czym porównano, i z listą pozycji (źródło, okres, wartość,
znaczenie). Używana jest ostatnia dekada wskaźnika zakończona nie później niż Data analizy: dekada, która w tym dniu
jeszcze trwa, powstaje z późniejszych obserwacji, więc nie jest czytana. Reguły są robocze i nie mają źródła naukowego
(nazwane parametry w `backend/app/engine/consistency_params.py`): niedobór to Stopień niedoboru od „lekki niedobór”
wzwyż; klasy wskaźnika 1–3 (obserwacja, ostrzeżenie, alarm) wskazują suszę, klasa 0 jej nie wskazuje, a klasy 4–6
(powrót do normy, chwilowa poprawa) nie są zestawiane; wynik jest „zgodne”, gdy oba wskazują to samo. Odczyt
satelitarny jest opisany w pozycjach Sprawdzenia zgodności i nie zmienia jego wyniku (sekcja „Odczyt satelitarny”);
poza Sezonem uprawy i dla Pola bez uprawy opisuje tylko pokrywę pola. Wynik „rozbieżne” obniża Pewność oceny Bieżącej
sytuacji wodnej i jest Ograniczeniem raportu; Ograniczeniem jest też brak wartości wskaźnika dla potrzebnej dekady
(wskaźnik jest dostępny od 2016 r. i ukazuje się z opóźnieniem). Podatność wieloletnia nie jest zestawiana. Werdykt
bez Stopnia niedoboru (Pole bez uprawy) daje „brak danych” z podaniem powodu.

## Odczyt satelitarny

Źródłem są sceny Sentinel-2 L2A z dwóch wymiennych usług (Planetary Computer, zapasowo Earth Search). Parametry
z uzasadnieniem są w `backend/app/sources/satellite_params.py` i `backend/app/engine/satellite_reading.py`; pochodzą
z pomiaru własnego (10 lat scen nad czterema działkami w czterech województwach, odczyt z serwera docelowego)
i z literatury podanej niżej.

**Które sceny.** Okno bieżące to 30 dni przed Datą analizy i sama data (w pomiarze dla dni kwiecień–wrzesień okno
30 dni nie miało czystej sceny w 0–3% dni, okno 15 dni w 8–10%); klasyfikacja sceny (SCL) jest czytana dla każdego
dnia pozyskania, a pasma dla najwyżej 6 najnowszych czystych scen. Dla każdego z 5 poprzednich lat czytane jest okno
15 dni przed i po tym samym dniu roku i najwyżej 2 czyste sceny najbliższe temu dniu. Razem najwyżej 16 scen
z pasmami. Żadna scena po Dacie analizy nie jest czytana. Bez filtra zachmurzenia całej sceny: w pomiarze odrzucał
sceny czyste nad Działką i przepuszczał zakryte. Z kilku kopii jednego dnia używana jest jedna: zawsze ten sam kafel
(najczęstszy w wynikach, żeby siatka pikseli była stała) i najwyższa wersja przetworzenia. Okna lat poprzednich są
czytane zawsze, bo Historia upraw może zostać podana później; o tym, które lata wolno porównać, decyduje silnik.

**Przeliczenie na odbicie.** Odbicie = (wartość z pliku + przesunięcie) / 10000; wartość 0 to brak danych.
Planetary Computer: przesunięcie −1000 od wersji przetworzenia 04.00 (zmiana produktu ESA z 25.01.2022), wcześniej 0.
Earth Search: 0 dla wersji sprzed 04.00 i dla scen oznaczonych jako już skorygowane; pozostałe sceny są pomijane.
Scena, w której mediana odbicia pasma nad Działką nie jest dodatnia, jest odrzucana.

**Które piksele.** Obrys Działki jest zmniejszany do wewnątrz o pół piksela: 5 m dla pasm 10 m i 10 m dla pasm 20 m
(Vajsová i in. 2020, Remote Sens. 12:2195; Sen4CAP, ATBD Parcels Heterogeneity Check); liczą się piksele, których
środek leży w zmniejszonym obrysie. Piksel czysty ma klasę SCL 4 (roślinność) albo 5 (bez roślinności). Scena jest
czysta nad Działką, gdy co najmniej 95% pikseli klasyfikacji w obrysie jest czystych (wybór własny: sceny są nad
Działką prawie zawsze albo w pełni czyste, albo całkiem zakryte, a niższy próg wpuszcza krawędzie chmur). Wskaźnik
wymaga co najmniej 8 pikseli (Vajsová i in. 2020), osobno na każdej siatce: Działka wąska ma sam NDVI, a zbyt mała
nie ma odczytu. NDVI = (B08 − B04) / (B08 + B04) na siatce 10 m, NDMI = (B8A − B11) / (B8A + B11) na siatce 20 m;
wynik sceny to mediana z czystych pikseli.

**Interpretacja** (bez progów bezwzględnych: nie znaleziono zweryfikowanych progów dla upraw polowych).

| Odczyt | Reguła | Kiedy |
|---|---|---|
| Pokrywa pola | NDVI i NDMI najnowszej czystej sceny okna bieżącego, opisowo | zawsze, także poza Sezonem uprawy i dla Pola bez uprawy |
| Kierunek zmiany | najnowsza scena wobec mediany wcześniejszych scen okna; zmiana od 0,10 (w pomiarze czyste sceny odległe o najwyżej 5 dni różniły się o 0,06–0,13 w 90. percentylu); potrzebne co najmniej dwie sceny | tylko w Okresie krytycznym |
| Porównanie z wcześniejszymi latami | NDMI najnowszej sceny wobec mediany z lat, w których Historia upraw podaje tę samą Uprawę; co najmniej 3 takie lata (wartość robocza) | tylko w Okresie krytycznym i tylko z Historią upraw; lata niepodane w Historii nie są liczone |
| Zgodność zdjęć z Uprawą | Uprawa ozima, a mediana NDVI scen z kwietnia bieżącego sezonu poniżej 0,4 (wartość robocza, pomiar na jednej działce) | gdy odczytane sceny obejmują kwiecień; daje Ograniczenie raportu dotyczące obu werdyktów |

Kierunek i porównanie są ograniczone do Okresu krytycznego, bo nie ma źródła z datami faz, w których spadek wskaźników
jest naturalny (dojrzewanie). Rośliny reagują na niedobór wody z opóźnieniem (Hua i in. 2019, Remote Sens. 11:1873:
30–45 dni; van Hoek i in. 2016, Remote Sens. 8:422: 8–15 dni), dlatego niedobór w bilansie bez spadku wskaźników nie
jest rozbieżnością. Ślad decyzyjny zapisuje, co odczyt mówi obok bilansu (`satellite_signal`): potwierdza (niedobór
i istotny spadek NDMI albo NDMI istotnie niższy niż w latach tej samej Uprawy), nie potwierdza, przeczy (brak
niedoboru i istotny spadek NDMI), bez zastrzeżeń, tylko pokrywa, za mało danych; oraz `satellite_crop_mismatch`.
Wynik Sprawdzenia zgodności z tych wartości dziś nie korzysta.

Reguły według Uprawy (`backend/app/engine/satellite_crops.py`): zboża i kukurydza: NDMI, a NDVI tylko jako pokrywa,
bo w zwartym łanie jest nasycony (Jackson i in. 2004, Remote Sens. Environ. 92:475–482); rzepak ozimy: NDMI, bo NDVI
spada w czasie kwitnienia (d'Andrimont i in. 2020, Remote Sens. Environ. 239:111660); ziemniak i burak cukrowy: NDMI
tylko opisowo (Vannoppen i Gobin 2022, Water 14:1188); użytki zielone: NDVI i NDMI razem (Bartold i in. 2024, Plants
13:2319). Uprawa bez wpisu jest tylko opisywana.

**Ograniczenia raportu i Pewność oceny.** Brak czystej sceny w oknie bieżącym to jedno Ograniczenie Bieżącej sytuacji
wodnej; braki we wszystkich oknach lat poprzednich to razem jedno Ograniczenie (z listą lat i powodów, w tym lat
sprzed początku archiwum), dzięki czemu odczyt z lukami nie waży więcej niż całkowity brak odczytu. Poza Sezonem uprawy
odczyt opisuje tylko pokrywę pola i jest Ograniczeniem Bieżącej sytuacji wodnej. Cały etap ma limit 12 s; po jego
upływie używane są sceny odczytane do tej chwili.

## Przyczyny niedoboru

Przyczyny niedoboru są wyznaczane tylko wtedy, gdy co najmniej jeden werdykt wskazuje niedobór. Każda z czterech
ma wskaźnik, próg i wartość dla Działki oraz jeden z trzech stanów: stwierdzona, niestwierdzona albo brak danych
do oceny (w raporcie: `found = false` i `indicator.value = null`). Wskaźniki: opad jako część parowania
wskaźnikowego ET0 (w latach z niedoborem, a gdy niedobór wskazuje tylko Bieżąca sytuacja wodna, w ostatnich 30
dniach), woda dostępna dla roślin na metr gleby, średni spadek terenu, współczynnik uprawy Kc w środkowej fazie
wzrostu. Wszystkie cztery progi (50%, 140 mm/m, 2%, Kc 1,0) są wartościami roboczymi bez źródła naukowego,
zapisanymi jako nazwane parametry w `backend/app/engine/cause_params.py`. Wodę dostępną na metr gleby wyznacza
kategoria gleby (z mapy IUNG-PIB albo oszacowana z uziarnienia). Pojemność wodna przyjęta zastępczo nie
jest podstawą do stwierdzenia przyczyny glebowej. Gdy żaden werdykt nie wskazuje niedoboru albo werdykty nie mają
Stopnia niedoboru (Pole bez uprawy), lista przyczyn jest pusta, a raport mówi to wprost.

## Analiza terenu

Wysokości terenu pochodzą z Łańcucha zamienników. Źródłem podstawowym jest numeryczny model terenu GUGiK w siatce
1 m, odczytywany usługą wysokości punktów w siatce co 5 m (punkty o całkowitych współrzędnych układu PL-1992
w prostokącie otaczającym Działkę powiększonym o 30 m; najwyżej 4000 punktów, więc duża Działka dostaje rzadszą
siatkę). Punkty są wysyłane po 400 w zapytaniu, do 8 zapytań jednocześnie. Wiersz odpowiedzi bez wysokości oznacza
brak danych dla punktu. Odpowiedź z wysokościami równymi dokładnie 0,0 bywa nieudanym zapytaniem, a nie terenem na
poziomie morza, dlatego część siatki zawierająca zera jest odczytywana drugi raz: zero zostaje tylko wtedy, gdy
powtórzy się w obu odczytach, a część, która dwa razy wróciła z samymi zerami, jest odrzucana. Źródło jest przyjęte,
gdy wysokość ma co najmniej 90% punktów wewnątrz Działki i odpowiedź przyszła w 8 s; w przeciwnym razie używany jest
zamiennik, Copernicus DEM GLO-30 (siatka ok. 30 m), a Raport podaje to jako Ograniczenie.

Spadek, kierunek spływu i najniższa część Działki pochodzą z płaszczyzny dopasowanej metodą najmniejszych kwadratów
do punktów siatki wysokości leżących wewnątrz obrysu Działki. Dla siatki w układzie PL-1992 odległości wynikają
wprost ze współrzędnych, a kierunki są obracane do północy geograficznej: północ siatki odbiega od niej o tzw.
zbieżność południków, do około 4° na wschodnim i zachodnim krańcu Polski. Skala odwzorowania (0,9993–1,0008) jest
pomijana, bo zmienia spadek o mniej niż jedną tysięczną jego wartości. Dla siatki 30 m odległości są liczone
z położenia punktów i szerokości geograficznej, bo jej oczka nie są kwadratowe (ok. 28 × 31 m). Rozrzut wysokości
wokół płaszczyzny daje niepewność spadku: kierunek i najniższa część są podawane tylko wtedy, gdy spadek jest co
najmniej 2 razy większy od swojej niepewności. Poniżej 6 punktów wewnątrz obrysu albo gdy punkty leżą w jednej linii,
spadek nie jest wyznaczany i raport to podaje. Najniższa część to położenie 10% najniżej leżących punktów względem
środka Działki, podawane jako strona Działki, nie punkt. Na trzech działkach porównawczych siatka co 5 m dała spadek
i kierunek zgodne z pełnym modelem 1 m (różnica do 0,03 punktu procentowego i 0,2°), a model 30 m różnił się
o 0,06–0,41 punktu procentowego i 2–6°. Dane Copernicus DEM opisują powierzchnię razem z budynkami i roślinnością,
co raport podaje jako Ograniczenie; poniżej 10 punktów tego modelu wewnątrz Działki spadek jest opisany jako
przybliżony.

## Sezon uprawy, data poza sezonem i Okres krytyczny

Raport rozpoznaje, gdzie Data analizy wypada względem Sezonu uprawy (`backend/app/engine/season.py`): w sezonie,
w sezonie w spoczynku (uprawa ozima od końca jesiennych wschodów do dnia przed wiosennym wzrostem; granice pochodzą
z dat faz w katalogu upraw) albo poza sezonem. Poza sezonem i w spoczynku Stopień niedoboru Bieżącej sytuacji wodnej
dotyczy Zapasu wody w glebie, nie potrzeb rośliny, i jest tak podpisany; liczony jest tą samą miarą i tymi samymi
progami co w sezonie (osobnej skali dla zapasu nie ma), a uzasadnienie opisuje ostatni zakończony sezon (dni,
w których wody brakowało, także w Okresie krytycznym) i zmianę zapasu od jego końca. Poza sezonem raport podaje
„Rekomendacje nawadniania: brak — wybrana data jest poza sezonem” z datami ostatniego sezonu.
`POST /api/reports/{report_id}/critical-period` uruchamia zwykłą analizę tej samej Działki i Uprawy (z nowym
pobraniem danych) na środkowy dzień ostatniego Okresu krytycznego, którego środek nie jest późniejszy niż Data
analizy raportu, więc nowa data nigdy nie jest późniejsza od pierwotnej. Odpowiedź to `202 {report_id, analysis_date}`;
nowy raport podaje pierwotną datę w `meta.changed_from_date`, a pierwotny raport się nie zmienia. Raport, którego
data już jest takim środkowym dniem, oraz Pole bez uprawy (nie ma Okresu krytycznego) dostają `409` z wyjaśnieniem
(`already_critical_period`, `no_critical_period`). Datę, którą da to przejście, raport podaje w śladzie decyzyjnym
(`trace`, reguła `season.state`).

## Wody w otoczeniu Działki

Z obiektów bazy BDOT10k leżących do 500 m od granicy Działki (wartość robocza) silnik wybiera
(`backend/app/engine/water_analysis.py`, parametry w `water_params.py`) najbliższy obiekt każdej z trzech grup: rów
(rów melioracyjny albo kanał), ciek (rzeka albo strumień, także powierzchnia wody płynącej) i zbiornik wodny (woda
powierzchniowa inna niż płynąca). Dla każdego podaje odległość od granicy Działki w metrach (0, gdy obiekt przecina
Działkę), stronę Działki (kierunek od środka Działki do środka tej części obiektu, która leży najbliżej granicy:
nie dalej niż najbliższy punkt plus 50 m) oraz to, czy jest to strona, w którą opada teren (kierunek do obiektu różni
się od kierunku spadku najwyżej o 45°; bez wyznaczonego kierunku spadku wartość jest nieznana). Odległości są liczone
na lokalnej płaskiej siatce w metrach wokół Działki. Miejsce zatrzymania wody związane z rowem to ta sama najbliższa
część rowu; pojawia się na mapie tylko razem z uruchomioną Rekomendacją i nie ma wymiarów ani parametrów. Progi 50 m
i 45° nie mają źródła w literaturze i są wartościami roboczymi. Odczyt danych obejmuje powiat, w którym leży
Działka, co raport podaje jako Ograniczenie razem z tym, czego baza nie zawiera (dreny, stan techniczny rowów, rowy
przydrożne, bieżący stan wody).

## Rekomendacje

Rekomendacje pochodzą z zamkniętego katalogu (`backend/app/catalog/recommendation_data.py`). Pozycja katalogu to
dane, nie kod: grupa, Przyczyny niedoboru, na które odpowiada, wymagane dane, warunki z zamkniętego zestawu rodzajów
(porównanie wartości z progiem, znana wartość, stwierdzona Przyczyna, uruchomiona inna pozycja oraz ich połączenia),
szablon tekstu, szablon „Co uzyskasz” i źródło. Silnik reguł (`backend/app/engine/rules.py`) sprawdza pozycję tylko
wtedy, gdy stwierdzono co najmniej jedną z jej Przyczyn; bez wymaganych danych reguła się nie uruchamia, a raport
podaje to jako Ograniczenie. Każda Rekomendacja stoi w raporcie raz, przy najsilniejszej ze stwierdzonych Przyczyn,
na które odpowiada, i podaje regułę, wartości, które ją uruchomiły, oraz źródło; każda sprawdzona pozycja zostawia
wpis w śladzie decyzyjnym. Bez stwierdzonej Przyczyny raport nie zawiera Rekomendacji i mówi to wprost. Rekomendacje
nigdy nie podają wymiarów, kosztów ani parametrów budowli. Katalog zawiera na razie po jednej pozycji wzorcowej na
grupę; ich treść opiera się na treści zadania konkursowego i materiale „Podstawy naukowe” organizatora, a nie na
publikacjach źródłowych, więc wszystkie są oznaczone jako robocze, podobnie jak progi ich reguł (Stopień niedoboru
od „lekki niedobór”). Pozycja z grupy nawadnianie nie trafia do sekcji Przyczyn: o nawadnianiu raport mówi w jednym
miejscu, na końcu (część o nawadnianiu, opisana niżej), a tekst tej pozycji katalogu nie jest w nim pokazywany. Jedna pozycja wzorcowa zależy od danych
o wodach: zatrzymywanie wody w rowie przy Działce, gdy rów melioracyjny albo kanał z danych leży najwyżej 20 m od
granicy Działki (wartość robocza: zapas na dokładność położenia obiektów). Bez danych o wodach reguła się nie
uruchamia i raport podaje to jako Ograniczenie; rów, którego nie ma w danych, nie jest brany pod uwagę.

## Nawadnianie

Część raportu o nawadnianiu (`backend/app/engine/irrigation.py`, parametry w `irrigation_params.py`) wynika wyłącznie
ze stanu bilansu wodnego na Datę analizy, bez prognozy pogody. W sezonie nawadnianie jest zasadne, gdy Bieżąca
sytuacja wodna wskazuje niedobór (od stopnia „lekki niedobór”; wartość robocza). Zakres podawany jest jako przedział
w mm i m³ na hektar (1 mm = 10 m³/ha): od ilości, która kończy brak wody (wyczerpanie strefy korzeniowej ponad wodę
łatwo dostępną), do ilości, która uzupełnia strefę korzeniową do pełna (całe wyczerpanie); granice są zaokrąglane do
1 mm do wewnątrz przedziału. Podstawa: FAO-56, rozdz. 8, „Forecasting or allocating irrigations” (nawadniać, zanim
wyczerpie się woda łatwo dostępna; dawka netto nie większa niż wyczerpanie strefy korzeniowej). Są to ilości netto:
strat przy nawadnianiu, sprawności urządzeń ani dawek jednorazowych raport nie uwzględnia. Tekst jest warunkowy
(„Jeśli masz możliwość nawadniania…”) i zawiera zdanie, że nawadnianie nie zastępuje zatrzymywania wody. Bez niedoboru
raport podaje „nie jest teraz zasadne” z wartością bilansu; w spoczynku uprawy ozimej także, bo Stopień niedoboru
dotyczy wtedy Zapasu wody w glebie; dla Pola bez uprawy część o nawadnianiu ma postać „nie dotyczy”. Gdy pojemność
wodna gleby jest oszacowana z uziarnienia albo przyjęta zastępczo, tekst mówi, że podane ilości są mniej pewne.

## Historia upraw i raport pochodny

Historia upraw (`backend/app/engine/history.py`, teksty w `history_texts.py`) jest opcjonalna. Bez niej raport
przyjmuje tę samą Uprawę w każdym roku i mówi to zdaniem przy Podatności wieloletniej (`history_assumption`); to samo
zdanie odróżnia potwierdzenie „ta sama Uprawa co roku” od Historii z innymi Uprawami. Podana Historia dokłada
Przebieg historyczny (`historical_course`): dla każdego roku Okna wieloletniego Uprawę, która wtedy rosła, wynik roku
i notę o odczycie satelitarnym, oraz zdanie porównujące z Podatnością wieloletnią. Przebieg stoi obok Podatności
i jej nie zastępuje: Podatność wieloletnia, Bieżąca sytuacja wodna, Pewność oceny, Przyczyny niedoboru, Rekomendacje
i część o nawadnianiu są takie same z Historią i bez niej. Zasady: lata Historii to lata Okna wieloletniego tej
analizy (rok to rok, w którym zaczyna się Okres krytyczny Uprawy, czyli dla uprawy ozimej rok zbioru); lata niepodane
przyjmują Uprawę z sezonu Daty analizy; rok jest oceniany tą samą miarą i tymi samymi parametrami co rok w Podatności
wieloletniej, na bilansie wodnym policzonym dla Uprawy z tego roku na tej samej pogodzie i glebie. Bilans każdej
Uprawy jest liczony osobno na całej serii, więc zapas wody na początku roku jest taki, jakby ta Uprawa rosła także
wcześniej; wpływu poprzedniej, innej Uprawy na ten zapas raport nie uwzględnia. Roku z Polem bez uprawy raport nie
ocenia (nie ma dla niego reguły Stopnia niedoboru), podobnie roku bez danych pogodowych i roku, w którym Okres
krytyczny Uprawy zaczyna się po Dacie analizy; taki rok ma w raporcie `deficit = false`, a jego nota zaczyna się od
„Roku nie oceniono” z powodem. Nota satelitarna podaje datę i wartości najnowszej sceny z danego roku oraz to, czy
dzień odczytu wypada w Sezonie uprawy Uprawy z tego roku; niczego nie ocenia, a dla lat bez sceny mówi „brak odczytu”
(sceny są czytane dla 5 poprzednich lat, z okresu wokół tego samego dnia roku).
Historię można podać w trakcie analizy (`PUT /api/analyses/{report_id}/crop-history`, po jej zakończeniu `409`) albo
później: `POST /api/reports/{report_id}/derive` z `{crop_history}` tworzy nowy raport z danych źródłowych zapisanych
z raportem źródłowym, bez pobierania czegokolwiek, i odpowiada `201 {report_id}`. Nowy raport ma własny adres i kopię
danych źródłowych, wskazuje raport źródłowy w `meta.derived_from` i sam może być źródłem kolejnego; raport źródłowy się
nie zmienia. Odpowiedzi z błędem: `404` (nie ma raportu, analiza się nie powiodła albo raport został już usunięty),
`425` (analiza trwa), `422 unknown_crop` (Uprawa spoza listy), `422 crop_history_year_outside_window` (rok spoza Okna
wieloletniego; komunikat podaje dozwolone lata), `409 crop_history_not_applicable` (Pole bez uprawy). Przejście na
Okres krytyczny przenosi Historię upraw raportu do nowej analizy, z pominięciem lat, które wypadły z jej Okna.

## Symulacja

Symulacja (`backend/app/engine/simulation.py`; trasy `GET /api/reports/{report_id}/simulation/ranking` i
`.../simulation/compare?crop_id=`) porównuje Podatność wieloletnią bieżącej Uprawy z podatnością innych Upraw z listy
na tej samej Działce. Liczy wyłącznie z bilansu wodnego, z pogody i gleby zapisanych razem z raportem: niczego nie
pobiera, niczego nie zapisuje i nie zmienia raportu. Każda Uprawa jest oceniana tym samym kodem i z tymi samymi
parametrami co raport, więc wynik bieżącej Uprawy jest równy Podatności wieloletniej z raportu; gdy raport powstał
przed zmianą sposobu liczenia, Symulacja nie odpowiada (`409 report_outdated`), zamiast pokazać inne liczby niż raport.
Ranking upraw pokazuje do trzech innych Upraw najmniej narażonych na niedobór wody, zawsze obok bieżącej; kolejność
wynika z udziału lat z niedoborem wody w ocenionych latach (przy tej samej liczbie lat: z liczby lat z niedoborem),
przy równym udziale z liczby dni z brakiem wody w Okresach krytycznych, potem z kolejności listy Upraw. Pole bez
uprawy nie jest porównywane, bo nie wyznacza się dla niego Stopnia niedoboru. Symulacja obejmuje wszystkie Uprawy
z listy (21), także oznaczone w katalogu jako warunkowe. Porównanie rok po roku zawiera lata, w których obie Uprawy mają ocenę. Symulacja nie
korzysta z danych satelitarnych i nie ocenia plonu, opłacalności, przydatności gleby ani zmianowania; te dwa stałe
Ograniczenia są w każdej odpowiedzi Rankingu upraw. Dla raportu przykładowego `/api/reports/demo` obie trasy
odpowiadają danymi przykładowymi (atrapą).

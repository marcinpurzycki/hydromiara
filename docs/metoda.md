# Hydromiara: metoda oceny

Szczegółowy opis tego, jak aplikacja dochodzi do treści raportu. Skrót i pozostałe części dokumentacji są
w [README](../README.md). Wszystkie reguły poniżej wykonuje deterministyczny kod w `backend/app/engine/`
(bez sieci, bez zegara, bez bazy): te same dane wejściowe dają ten sam raport.

Wartość, która nie ma źródła naukowego, jest w kodzie oznaczona komentarzem `PROVISIONAL` (wartość robocza)
i zebrana w pliku parametrów swojego modułu, więc jej wymiana jest zmianą danych, a nie kodu. Pliki z wartościami
roboczymi: `backend/app/engine/params.py`, `cause_params.py`, `consistency_params.py`, `findings.py`,
`irrigation_params.py`, `backend/app/catalog/crop_data.py`, `recommendation_data.py`,
`backend/app/sources/satellite_params.py`, `soil_params.py`, `terrain_params.py`, `weather_params.py`, `raster.py`,
`backend/app/storage/params.py`, `backend/app/summary/params.py`.

## Bilans wodny i dwa werdykty

Podstawą obu werdyktów jest dzienny bilans wody w strefie korzeniowej według FAO-56, rozdział 8
(`backend/app/engine/balance.py`, `root_zone.py`; równania 80, 82–86 i 88): woda dostępna dla roślin (TAW), woda
łatwo dostępna (RAW = p · TAW), wyczerpanie strefy korzeniowej (Dr) i współczynnik stresu wodnego Ks; ewapotranspiracja
uprawy to Ks · Kc · ET0. Opad i ET0 pochodzą z archiwum pogodowego, współczynnik Kc z katalogu upraw (krzywa
w ciągu roku z dat faz), pojemność wodna z profilu glebowego. Seria zaczyna się przed Oknem wieloletnim (rozruch
bilansu), a dni po Dacie analizy są odrzucane na wejściu, więc wynik dla danej daty nie zależy od późniejszych danych.

Uproszczenia: bez spływu powierzchniowego, podsiąku i nawodnień; stała głębokość korzeni; współczynnik p bez
korekty na wielkość ewapotranspiracji; strefa korzeniowa ograniczona do 100 cm (zasięg danych o glebie) i brana
z płytszego końca zakresu FAO-56; bilans zaczyna od pojemności polowej. Gdy profilu glebowego nie ma, przyjmowana
jest pojemność zastępcza 150 mm wody dostępnej na metr gleby, a raport podaje to jako Ograniczenie.

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
suszy rolniczej, nie ocenia nadmiaru wody, nie korzysta z prognozy pogody, publiczne dane o rowach są niekompletne) są
w każdym raporcie i Pewności nie obniżają. Pozostałe wynikają z danych tej analizy: brak kategorii danych, dane
z mniej dokładnego zamiennika (Łańcuch zamienników: źródło podstawowe, zamiennik, brak danych), pojemność wodna gleby
przyjęta zastępczo, dane pogodowe kończące się przed Datą analizy, dni bez pogody, niepełne Okno wieloletnie.
Pewność werdyktu obniżają tylko Ograniczenia, które go dotyczą. Reguła jest robocza i nie ma źródła naukowego:
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
satelitarny (NDVI, NDMI z najnowszej sceny z 30 dni przed Datą analizy) jest podawany opisowo i nie zmienia wyniku;
poza Sezonem uprawy i dla Pola bez uprawy opisuje tylko pokrywę pola. Wynik „rozbieżne” obniża Pewność oceny Bieżącej
sytuacji wodnej i jest Ograniczeniem raportu; Ograniczeniem jest też brak wartości wskaźnika dla potrzebnej dekady
(wskaźnik jest dostępny od 2016 r. i ukazuje się z opóźnieniem). Podatność wieloletnia nie jest zestawiana. Werdykt
bez Stopnia niedoboru (Pole bez uprawy) daje „brak danych” z podaniem powodu.

## Przyczyny niedoboru

Przyczyny niedoboru są wyznaczane tylko wtedy, gdy co najmniej jeden werdykt wskazuje niedobór. Każda z czterech
ma wskaźnik, próg i wartość dla Działki oraz jeden z trzech stanów: stwierdzona, niestwierdzona albo brak danych
do oceny (w raporcie: `found = false` i `indicator.value = null`). Wskaźniki: opad jako część parowania
wskaźnikowego ET0 (w latach z niedoborem, a gdy niedobór wskazuje tylko Bieżąca sytuacja wodna, w ostatnich 30
dniach), woda dostępna dla roślin na metr gleby, średni spadek terenu, współczynnik uprawy Kc w środkowej fazie
wzrostu. Wszystkie cztery progi (50%, 140 mm/m, 2%, Kc 1,0) są wartościami roboczymi bez źródła naukowego,
zapisanymi jako nazwane parametry w `backend/app/engine/cause_params.py`. Pojemność wodna przyjęta zastępczo nie
jest podstawą do stwierdzenia przyczyny glebowej. Gdy żaden werdykt nie wskazuje niedoboru albo werdykty nie mają
Stopnia niedoboru (Pole bez uprawy), lista przyczyn jest pusta, a raport mówi to wprost.

## Analiza terenu

Spadek, kierunek spływu i najniższa część Działki pochodzą z płaszczyzny dopasowanej metodą najmniejszych kwadratów
do punktów siatki wysokości leżących wewnątrz obrysu Działki; odległości są liczone z położenia punktów i szerokości
geograficznej, bo oczka siatki nie są kwadratowe (ok. 28 × 31 m). Rozrzut wysokości wokół płaszczyzny daje niepewność
spadku: kierunek i najniższa część są podawane tylko wtedy, gdy spadek jest co najmniej 2 razy większy od swojej
niepewności. Poniżej 6 punktów wewnątrz obrysu albo gdy punkty leżą w jednej linii, spadek nie jest wyznaczany
i raport to podaje. Dane Copernicus DEM opisują powierzchnię razem z budynkami i roślinnością, co raport podaje jako
Ograniczenie; na siatce 30 m najniższa część jest wskazywana tylko jako strona Działki, nie punkt.

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
miejscu, na końcu (część o nawadnianiu, opisana niżej), a tekst tej pozycji katalogu nie jest w nim pokazywany. Pozycje wymagające danych o wodach nie uruchamiają się,
dopóki dane o ciekach, rowach i zbiornikach nie są pobierane.

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
wodna gleby jest przyjęta zastępczo, tekst mówi, że podane ilości są mniej pewne.

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
dzień odczytu wypada w Sezonie uprawy Uprawy z tego roku; niczego nie ocenia, a dla lat bez sceny mówi „brak odczytu”.
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
uprawy nie jest porównywane, bo nie wyznacza się dla niego Stopnia niedoboru. Lista ma teraz jedną Uprawę i Pole bez
uprawy, więc Ranking upraw pokazuje samą bieżącą Uprawę i mówi to wprost; po uzupełnieniu listy Symulacja obejmie
nowe Uprawy bez zmian w kodzie. Porównanie rok po roku zawiera lata, w których obie Uprawy mają ocenę. Symulacja nie
korzysta z danych satelitarnych i nie ocenia plonu, opłacalności, przydatności gleby ani zmianowania; te dwa stałe
Ograniczenia są w każdej odpowiedzi Rankingu upraw. Dla raportu przykładowego `/api/reports/demo` obie trasy
odpowiadają danymi przykładowymi (atrapą).

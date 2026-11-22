# Hydromiara: instrukcja wdrożenia pełnoskalowego

Instrukcja dla zespołu, który chciałby udostępnić rozwiązanie wielu rolnikom jako stałą usługę. Opisuje, co trzeba
zmienić względem [wdrożenia pokazowego](wdrozenie-pokazowe.md), które jest punktem wyjścia i którego kroki
(skrypt `scripts/deploy.sh`, plik `.env`, pliki wskaźnika suszy) pozostają w mocy. Pozostała dokumentacja jest
w [README](../README.md).

**Takiego wdrożenia nie wykonano.** Dlatego każda część tego dokumentu rozdziela dwie rzeczy:

- **Sprawdzone**: zmierzone albo odczytane ze stron dostawców, z datą;
- **Zalecenie niesprawdzone**: kierunek zmian wynikający z budowy aplikacji i z pomiarów, którego nikt nie
  uruchomił w tej postaci.

Rozdział 6 streszcza warunki korzystania z usług zewnętrznych na podstawie stron ich dostawców, z adresem i datą
odczytu. Nie jest poradą prawną. Miejsca oznaczone **„do sprawdzenia przez człowieka przed wdrożeniem”** trzeba
rozstrzygnąć przed uruchomieniem usługi; ich zestawienie jest w rozdziale 7. Dokument nie podaje żadnych kwot:
ceny trzeba odczytać z aktualnych cenników dostawców.

## 1. Czym różni się wdrożenie pełnoskalowe

| Obszar | Wersja pokazowa | Wdrożenie pełnoskalowe |
|---|---|---|
| Charakter użycia | prototyp konkursowy, bez opłat i reklam | stała usługa; trzeba ustalić, czy jest użyciem komercyjnym w rozumieniu warunków dostawców |
| Dostępy do danych | bezpłatne, bez kont i kluczy | płatne plany albo własne kopie tam, gdzie wymagają tego warunki lub limity (rozdział 2 i 6) |
| Limity dostawców | liczone na jeden adres IP serwera | uzgodnione z dostawcami: plan płatny, zgłoszenie adresów, klucz |
| Dane między analizami | nic nie jest buforowane | kopie lokalne i pamięć podręczna (rozdział 3) |
| Usługa | jeden proces, plik bazy SQLite, liczniki w pamięci | wspólna baza, wspólne liczniki, kolejka (rozdział 4) |
| Utrzymanie | ręczne | kopie zapasowe, monitoring, zadania okresowe (rozdział 5) |
| Warunki prawne | streszczone ze stron dostawców | przegląd prawny przez człowieka (rozdział 7) |

## 2. Dostępy do usług: co trzeba zmienić

### Pogoda (Open-Meteo): pierwszy limit, na który trafi usługa

**Sprawdzone.** Bezpłatny dostęp jest przeznaczony wyłącznie do zastosowań niekomercyjnych i ma limity 600 zapytań
na minutę, 5000 na godzinę i 10 000 na dobę z adresu IP (`https://open-meteo.com/en/terms`, odczyt 22.11.2026).
Jedna analiza zużywa około 88 jednostek limitu, czyli z jednego adresu wykonuje się około 6 analiz na minutę,
56 na godzinę i 113 na dobę. Limit dobowy odnawia się o północy czasu UTC; po jego wyczerpaniu nowe analizy
kończą się niepowodzeniem (zaobserwowane 22.11.2026). Płatny plan daje według cennika licencję na użycie
komercyjne, klucz, osobny adres usługi dla klientów, brak limitu dobowego i miesięczny budżet zapytań: 1 mln
(Standard), 5 mln (Professional), ponad 50 mln (Enterprise); archiwum pogodowe wymaga planu Professional
(`https://open-meteo.com/en/pricing`, odczyt 22.11.2026). Kod serwera Open-Meteo jest otwarty (AGPLv3), a cennik
wskazuje własną instalację jako drogę dla bardzo dużej liczby zapytań.

**Zalecenie niesprawdzone.**

1. Ustalić, czy planowana usługa jest użyciem komercyjnym w rozumieniu warunków (przegląd prawny, rozdział 7).
2. Wybrać jedną z dróg: płatny plan obejmujący archiwum pogodowe albo własna instalacja serwera Open-Meteo
   z własną kopią danych. Budżet 5 mln zapytań na miesiąc odpowiada około 57 tysiącom analiz bez buforowania
   (wyliczenie z kosztu jednej analizy, nie pomiar).
3. Dodać w adapterze pogody obsługę klucza i adresu usługi dla klientów; obecna wersja nie obsługuje żadnego
   z nich i pyta wyłącznie adres bezpłatny.
4. Niezależnie od planu wprowadzić kopię lokalną serii pogodowych (rozdział 3).

**Do sprawdzenia przez człowieka przed wdrożeniem:** aktualna cena i limity planu płatnego
(`https://open-meteo.com/en/pricing`) oraz warunki użycia komercyjnego (`https://open-meteo.com/en/terms`);
licencja i wymagania własnej instalacji (AGPLv3) oraz licencje danych źródłowych, które trzeba by wtedy pobierać
samodzielnie.

### Dane satelitarne (Planetary Computer i Earth Search)

**Sprawdzone.** Obie usługi są dziś używane w dostępie bezpłatnym, bez konta i klucza, bez gwarancji dostępności
i z limitami, których dostawcy nie podają liczbowo. Dokumentacja Planetary Computer mówi, że limity i czas
ważności tokenu są korzystniejsze dla zapytań z kluczem subskrypcji i z regionu Azure West Europe. Opis Earth
Search mówi, że publiczny interfejs nie ma gwarancji usługi, a przy użyciu produkcyjnym odsyła do kontaktu
z operatorem w sprawie prywatnego katalogu (adresy źródeł w rozdziale 6, odczyt 22.11.2026). Pomiar z serwera
(21.11.2026): odczyt 16 scen po 5 pasm trwał 1,2 s z Planetary Computer i 5,5 s z Earth Search. Same dane
Sentinel-2 mają dostęp bezpłatny, pełny i otwarty niezależnie od usługi.

**Zalecenie niesprawdzone.**

1. Przejść na dostęp z gwarancją dostępności i znanymi limitami u dostawcy usługi podstawowej, a najlepiej obu,
   albo czytać pliki pasm bezpośrednio z otwartych zasobów i utrzymywać własny katalog scen.
2. Dodać w adapterze przekazywanie klucza dostępu; obecna wersja klucza nie obsługuje.
3. Do tego czasu jedyną ochroną przed niedostępnością pozostaje druga, wymienna usługa.

**Do sprawdzenia przez człowieka przed wdrożeniem:** warunki korzystania z Planetary Computer (strony
`https://planetarycomputer.microsoft.com/terms` nie dało się odczytać automatycznie), istnienie, warunki i cennik
płatnego lub gwarantowanego dostępu u obu dostawców (nie odczytano żadnego), sposób uzyskania klucza subskrypcji
Planetary Computer i limity, które on daje.

### Działki (ULDK)

**Sprawdzone.** Usługa jest bezpłatna także dla aplikacji komercyjnych i nie wymaga umowy ani klucza. Limity
standardowe to 200 zapytań na minutę w godzinach 6–18, 40 na minutę w pozostałych i 10 000 na dobę na adres IP.
Gdy ruch ma regularnie przekraczać limity, adresy IP serwera można bezpłatnie zgłosić do listy zaufanej GUGiK,
której limity nie dotyczą; zgłoszenie wysyła osoba upoważniona, pocztą elektroniczną, na adres podany w opisie
usługi (`https://uldk.gugik.gov.pl/opis.html`, odczyt 22.11.2026).

**Zalecenie niesprawdzone.** Zgłosić adresy serwerów do listy zaufanej przed uruchomieniem; zapisywać geometrię raz
analizowanej działki, żeby ponowna analiza nie pytała usługi (z odświeżaniem, bo rejestr się zmienia).

### Gleba

**Sprawdzone.** Usługa REST SoilGrids jest w fazie beta, bez gwarancji dostępności, z zasadą 5 zapytań na minutę,
a jej strona zawierała komunikat o czasowym wstrzymaniu (odczyt 22.11.2026). W pomiarze z serwera (22.11.2026)
nie odpowiedziała w 24 s w żadnej z 13 analiz i to ona wyznaczała czas całej analizy (24–26 s). ISRIC zaleca
przy potrzebie stabilności dostęp przez WebDAV albo usługi sieciowe. Zmierzone zamienniki: odczyt kategorii
podatności gleb na suszę z usługi mapowej IUNG-PIB (około 1 s) i SoilGrids przez usługę WCS (2–3 s).

**Zalecenie niesprawdzone.** Nie opierać wdrożenia pełnoskalowego na usłudze REST. Podłączyć usługę IUNG-PIB jako
ogniwo podstawowe i SoilGrids WCS jako zamiennik; rozważyć własną kopię map SoilGrids (licencja CC BY 4.0 na to
pozwala przy podaniu źródła), bo wartości dla raz analizowanego miejsca się nie zmieniają.

**Do sprawdzenia przez człowieka przed wdrożeniem:** warunki ponownego wykorzystania usługi IUNG-PIB. Instytut nie
publikuje licencji ani regulaminu tej usługi, więc przed wdrożeniem trzeba wysłać do IUNG-PIB zapytanie o zgodę
i warunki (kontakt na stronie `https://susza.iung.pulawy.pl/mapa-kategorii/`).

### Teren i wody

**Sprawdzone.** Copernicus DEM GLO-30 jest dostępny bezpłatnie na warunkach własnej licencji, bez konta; odczyt
z serwera trwał około 1,4 s. Usługa wysokości punktów GUGiK (model 1 m) odpowiadała w 2–3,5 s, ale w około 4%
zapytań zwracała same zera i nie ma opisanych limitów. Odczyt danych o wodach BDOT10k na żywo trwał około 8–10 s,
a serwer plików zrywał część połączeń równoległych; kopia całego kraju (cztery pliki, około 560 MB) odpowiadała
w około 1 ms.

**Zalecenie niesprawdzone.** Po podłączeniu tych źródeł: dane o wodach czytać z kopii lokalnej odświeżanej raz
na tydzień, a pliki do kopii pobierać po kolei, nie równolegle; arkusze modelu terenu dla raz analizowanego
miejsca zapisywać lokalnie.

**Do sprawdzenia przez człowieka przed wdrożeniem:** limity i warunki usługi wysokości punktów GUGiK, dokument
licencji i wymagany zapis źródła dla plików BDOT10k, zasady korzystania z publicznego serwera Overpass (jeśli
zostanie użyty jako zamiennik; przy stałym ruchu właściwa jest własna instalacja).

### Tło suszowe (EDO)

**Sprawdzone.** Dane są czytane z plików lokalnych, więc dostępność usługi źródłowej nie wpływa na analizę. Odczyt
trwał 1,1–1,4 s przy jednej analizie i 3,1–3,6 s przy trzech naraz (limit źródła w aplikacji: 5 s); przy czterech
i więcej analizach naraz nie mierzono.

**Zalecenie niesprawdzone.** Pobieranie nowych plików zadaniem okresowym (nowa dekada co 10 dni; wystarczy
sprawdzanie raz na tydzień) zamiast ręcznie; pamięć podręczna serii wskaźnika dla komórki siatki i dłuższy limit
czasu, żeby odczyt nie zwalniał przy wielu analizach naraz.

### Model językowy

**Sprawdzone.** Aplikacja wysyła jedno krótkie zapytanie na analizę i jest kompletna bez modelu. Model nie dostaje
Identyfikatora działki, nazw miejsc ani współrzędnych. Na maszynie deweloperskiej podsumowanie zajmowało około
8 s; z serwera nie mierzono.

**Zalecenie niesprawdzone.** Wybrać dostawcę z umową odpowiednią dla instytucji, która będzie właścicielem usługi,
i z limitami dopasowanymi do liczby analiz; rozważyć model uruchamiany we własnej infrastrukturze (interfejs jest
wymienny przez `AI_BASE_URL`).

**Do sprawdzenia przez człowieka przed wdrożeniem:** warunki korzystania, cennik, limity oraz zasady przetwarzania
i przechowywania danych u wybranego dostawcy.

## 3. Buforowanie i kopie lokalne

**Sprawdzone** (pomiar z serwera z dwoma procesorami, 22.11.2026: 10 działek, każde źródło 40 razy, 13 całych
analiz): żadne źródło poza usługą REST gleby nie wymaga buforowania, żeby analiza zmieściła się w 30 s. Źródła
odpytane naraz odpowiadały w 1,7–3,2 s, a przy trzech analizach jednocześnie w 3,2–4,1 s; obliczenia zajmują
poniżej 0,1 s. Dziś aplikacja nie buforuje niczego między analizami; dane pobrane dla jednej analizy są zapisane
razem z Raportem, więc ponowne otwarcie, Symulacja i raport pochodny niczego nie pobierają.

**Zalecenie niesprawdzone.** Buforowanie uzasadniają limity i niezawodność, nie czas:

| Dane | Zalecenie | Odświeżanie |
|---|---|---|
| Pogoda | odczyt na żywo; kopia lokalna na dysku jako zamiennik przy niedostępności lub limicie; zapis serii z każdej analizy | wpis młodszy niż doba zastępuje zapytanie tylko wtedy, gdy pokrywa cały potrzebny zakres dat; dane historyczne się nie zmieniają, więc dla znanego miejsca wystarcza dopytanie o ostatnie dni |
| Dane o wodach | kopia całego kraju | raz na tydzień i przy starcie usługi |
| Tło suszowe | pliki lokalne (jak dziś) | sprawdzanie nowych plików raz na tydzień |
| Geometria działki, gleba, teren | zapis dla raz analizowanego miejsca | geometria okresowo (rejestr się zmienia); gleba i teren bez odświeżania |
| Sceny satelitarne | na żywo | nie dotyczy |

Granica kopii pogody: chroni miejsca już analizowane. Nowa działka w nowym miejscu podczas niedostępności usługi
pogodowej nadal nie dostanie danych, a kopii dla całego kraju nie da się pobrać w bezpłatnym limicie; wymaga ona
płatnego planu albo własnej instalacji. Liczby węzłów siatki archiwum nad Polską, potrzebnej do oszacowania takiej
kopii, nie ustalono.

## 4. Procesy, baza i limity aplikacji

**Sprawdzone.** Usługa działa jako jeden proces na jeden plik bazy SQLite. Liczniki limitów zapytań, limit analiz
trwających jednocześnie i stan trwających analiz są w pamięci tego procesu; przy starcie i przy zamknięciu każda
niedokończona analiza jest zamykana jako nieudana. Pracy w wielu procesach nie sprawdzano i obecna budowa jej nie
wspiera: drugi proces na tym samym pliku miałby własne liczniki i zamykałby analizy pierwszego. Równolegle
mierzono najwyżej trzy analizy.

**Zalecenie niesprawdzone.**

1. Nie zwiększać liczby procesów serwera aplikacji ani liczby kontenerów `api` bez zmian w kodzie.
2. Do pracy w wielu procesach potrzebne są: wspólna baza raportów (np. PostgreSQL) zamiast pliku SQLite, wspólne
   liczniki limitów (np. w bazie albo w pamięci współdzielonej), kolejka analiz zamiast odmowy przy zajętych
   miejscach i wspólna pula wywołań usług zewnętrznych, żeby suma zapytań wszystkich procesów mieściła się
   w limitach dostawców. Silnik oceny jest czystą funkcją, a pobieranie, przechowywanie i liczenie są rozdzielone,
   więc zmiana dotyczy warstwy przechowywania i uruchamiania.
3. Limity aplikacji (`RATE_LIMIT_*`, `MAX_CONCURRENT_ANALYSES`) dobrać do wykupionych limitów dostawców: suma
   analiz dopuszczonych przez aplikację nie powinna przekraczać tego, co przyjmie usługa pogodowa i ULDK.
   Wartości domyślne są stałymi inżynierskimi dobranymi dla prototypu.
4. `FORWARDED_ALLOW_IPS` musi wskazywać wszystkie serwery pośredniczące przed usługą; przy dodatkowej warstwie
   (równoważenie ruchu, ochrona przed atakami) sprawdzić, pod jakim adresem usługa widzi odwiedzającego.
5. Ochrona przed rozproszonym atakiem z wielu adresów i limity czasu połączeń należą do infrastruktury przed
   usługą; aplikacja ich nie zapewnia.

## 5. Retencja, kopie zapasowe, monitoring

**Sprawdzone.** Raporty są usuwane po 30 dniach; jeden Raport zajmuje około 350 kB. Raporty leżą w wolumenie
`reports`, który przetrwa aktualizację (`docker compose down` go nie usuwa, `docker compose down --volumes` usuwa).
Log usługi nie zawiera adresów IP ani pełnych adresów Raportów; log dostępu serwera aplikacji jest wyłączony.
Kontenery mają limit logów (3 pliki po 10 MB). Stan usługi podaje `GET /api/health`. Kopii zapasowych aplikacja
nie wykonuje.

**Zalecenie niesprawdzone.**

- **Retencja:** ustalić czas przechowywania Raportów z właścicielem usługi (Raport zawiera Identyfikator działki,
  który da się powiązać z właścicielem w rejestrach publicznych) i zaplanować miejsce na dysku: liczba analiz
  w okresie przechowywania razy około 350 kB, plus kopie lokalne danych. Jeśli zostanie włączony log dostępu
  w Traefiku, będzie zawierał adresy IP i pełne adresy Raportów: ustalić także jego czas przechowywania.
- **Kopie zapasowe:** okresowa kopia bazy raportów (dla SQLite wykonana mechanizmem kopii bazy, nie zwykłym
  kopiowaniem pliku podczas zapisu) oraz pliku `.env` przechowywanego jak sekret; próba odtworzenia przed
  uruchomieniem usługi. Kopii lokalnych danych źródłowych nie trzeba archiwizować, bo da się je pobrać ponownie.
- **Monitoring:** okresowe sprawdzanie `/api/health` z zewnątrz; zbieranie z logu czasów i niepowodzeń każdego
  źródła oraz odpowiedzi `429` i `503`; alarm przy zbliżaniu się do limitu usługi pogodowej (odpowiedzi usługi
  zawierają nagłówki z kosztem i pozostałym limitem), przy rosnącym udziale Raportów z brakującym źródłem
  i przy kończącym się miejscu na dysku; kontrola ważności certyfikatu.
- **Zadania okresowe:** dogrywanie plików wskaźnika suszy, odświeżanie kopii lokalnych, aktualizacje obrazów
  i systemu.
- **Aktualizacja bez przerwy:** dziś `scripts/deploy.sh --yes` przebudowuje obraz i restartuje usługę, a analizy
  trwające w tej chwili kończą się niepowodzeniem; ciągłość wymaga kolejki i więcej niż jednego procesu (rozdział 4).

## 6. Licencje i warunki korzystania z usług zewnętrznych we wdrożeniu pełnoskalowym

Dla każdej usługi: co wolno, czy potrzebny jest klucz, konto lub płatny plan, jakie są limity i jak podać źródło.
Wymagane noty o pochodzeniu danych są w README, punkt 7, i nie zmieniają się ze skalą. Data odczytu stron:
22.11.2026, o ile nie podano inaczej.

### Usługi, z których aplikacja korzysta dziś

**ULDK (Główny Urząd Geodezji i Kartografii), działki ewidencyjne**

- Co wolno: korzystanie w aplikacji komercyjnej i odpłatnej jest dopuszczalne i nieodpłatne, bez dodatkowych umów
  licencyjnych z GUGiK.
- Klucz, konto, płatny plan: nie są potrzebne; rejestracji nie ma.
- Limity: 200 zapytań na minutę w godzinach 6–18, 40 na minutę w pozostałych, 10 000 na dobę na adres IP.
  Adresy IP ruchu produkcyjnego można bezpłatnie zgłosić do listy zaufanej, której limity nie dotyczą.
- Podanie źródła: wymagane, np. „Źródło: Główny Urząd Geodezji i Kartografii (GUGiK), Usługa Lokalizacji Działek
  Katastralnych (ULDK).”
- Źródło: `https://uldk.gugik.gov.pl/opis.html`.

**Open-Meteo, archiwum pogodowe**

- Co wolno: bezpłatny dostęp tylko niekomercyjnie; strony i aplikacje z subskrypcją lub reklamami oraz produkty
  komercyjne warunki zaliczają do użycia komercyjnego, które wymaga subskrypcji. Usługa publiczna na pełną skalę
  nie jest wymieniona w przykładach żadnej z grup.
- Klucz, konto, płatny plan: przy użyciu komercyjnym albo większej liczbie zapytań płatna subskrypcja z kluczem
  i osobnym adresem usługi; archiwum pogodowe od planu Professional. Alternatywa: własna instalacja serwera
  (kod na licencji AGPLv3).
- Limity: w planach płatnych brak limitu minutowego, godzinowego i dobowego, miesięczny budżet zapytań zależny
  od planu (1 mln, 5 mln, ponad 50 mln); zapytanie o więcej niż 2 tygodnie danych liczy się wielokrotnie.
  Cennik podaje dla planów płatnych docelową dostępność 99,9%.
- Podanie źródła: dane na licencji CC BY 4.0, wymagane podanie źródła z odnośnikiem i zaznaczenie zmian, także
  w planie płatnym.
- Źródła: `https://open-meteo.com/en/terms`, `https://open-meteo.com/en/pricing`,
  `https://open-meteo.com/en/licence`.
- Do sprawdzenia przez człowieka przed wdrożeniem: czy planowana usługa jest użyciem komercyjnym; aktualna cena
  i warunki subskrypcji.

**SoilGrids 2.0 (ISRIC – World Soil Information), gleba**

- Co wolno: dane na licencji CC BY 4.0 (kopiowanie i przetwarzanie w dowolnym celu przy podaniu źródła
  i zaznaczeniu zmian), więc możliwa jest także własna kopia map.
- Klucz, konto, płatny plan: nie są potrzebne; płatnego planu z gwarancją dostawca nie opisuje.
- Limity: usługa REST ma zasadę 5 zapytań na minutę, jest w fazie beta i bez gwarancji dostępności, więc nie
  nadaje się na podstawę usługi produkcyjnej; ISRIC zaleca WebDAV albo usługi sieciowe. Limitu dla usługi WCS
  dokumentacja nie podaje.
- Podanie źródła: wymagane; cytowanie w README, punkt 7.
- Źródło: `https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_02.html`.

**Europejskie Obserwatorium Suszy (EDO), wskaźnik CDI, pliki lokalne**

- Co wolno: bezpłatny dostęp z prawem powielania, rozpowszechniania, publicznego udostępniania, adaptacji,
  modyfikacji i łączenia z innymi danymi; bez gwarancji; dane mają charakter informacyjny.
- Klucz, konto, płatny plan: nie są potrzebne.
- Limity: nie dotyczą analizy; limitów pobierania plików strona warunków nie podaje.
- Podanie źródła: nota „Generated using Copernicus Emergency Management Service information [rok]”, a przy danych
  zmienionych „Contains modified Copernicus Emergency Management Service information [rok]”.
- Źródło: `https://drought.emergency.copernicus.eu/terms&conditions/`.
- Licencja: CC BY 4.0 (ustalenie zespołu z 22.11.2026). Strona warunków, odczytana 22.11.2026, nie wymienia tej
  licencji z nazwy, tylko podaje prawa i noty opisane wyżej.

**Copernicus DEM GLO-30, ukształtowanie terenu**

- Co wolno: bezpłatnie dla każdego na warunkach licencji Copernicus DEM, bez ograniczenia w czasie; powielanie,
  rozpowszechnianie, publiczne udostępnianie, adaptacja, modyfikacja i łączenie z innymi danymi.
- Klucz, konto, płatny plan: nie są potrzebne (odczyt bez konta AWS).
- Limity: strona rejestru nie podaje limitów.
- Podanie źródła: nota o prawach autorskich z licencji (README, punkt 7); nie wolno sugerować oficjalnego poparcia;
  przy przekazywaniu danych dalej trzeba dołączyć zdanie o wyłączeniu odpowiedzialności organizacji programu
  Copernicus.
- Źródła: `https://registry.opendata.aws/copernicus-dem/`; tekst licencji „Licence for the use of the Copernicus
  WorldDEM-30” (odczytany z kopii pod adresem
  `https://docs.sentinel-hub.com/api/latest/static/files/data/dem/resources/license/License-COPDEM-30.pdf`).

**Copernicus Sentinel-2 L2A, dane satelitarne**

- Co wolno: dostęp bezpłatny, pełny i otwarty; powielanie, rozpowszechnianie, przetwarzanie i łączenie z innymi
  danymi.
- Podanie źródła: „Contains modified Copernicus Sentinel data [rok]” przy danych przetworzonych.
- Źródła: nota prawna danych Sentinel, `https://sentinel.esa.int/documents/247904/690755/Sentinel_Data_Legal_Notice`
  (odczyt 21.11.2026; 22.11.2026 adres nie odpowiadał); `https://registry.opendata.aws/sentinel-2-l2a-cogs/`.

**Microsoft Planetary Computer, podstawowa usługa danych satelitarnych**

- Co wolno: według dokumentacji dane są bezpłatne dla każdego i dostępne anonimowo; warunków korzystania z samej
  usługi nie odczytano.
- Klucz, konto, płatny plan: dziś bez klucza; dokumentacja wspomina klucz subskrypcji, który daje korzystniejsze
  limity i dłuższą ważność tokenu. Aplikacja klucza nie obsługuje.
- Limity: bez podanych liczb; zależą od regionu Azure i klucza. Gwarancji dostępności dokumentacja nie opisuje.
- Źródło: `https://github.com/microsoft/PlanetaryComputerDataCatalog` (plik `docs/concepts/sas.md`; repozytorium
  zarchiwizowane, treść może być nieaktualna).
- Do sprawdzenia przez człowieka przed wdrożeniem: warunki korzystania (`https://planetarycomputer.microsoft.com/terms`),
  dopuszczalność stałego użycia produkcyjnego, sposób uzyskania klucza, istnienie, warunki i cennik dostępu
  płatnego lub gwarantowanego.

**Earth Search (Element 84), zapasowa usługa danych satelitarnych i katalog arkuszy modelu terenu**

- Co wolno: publiczny interfejs opisany jako bezpłatny w użyciu, bez gwarancji usługi; przy użyciu produkcyjnym
  opis odsyła do kontaktu z operatorem.
- Klucz, konto, płatny plan: publiczny interfejs bez klucza; pliki pasm w rejestrze otwartych danych AWS bez konta.
- Limity: nieopisane.
- Źródła: `https://github.com/Element84/earth-search` (plik `README.md`),
  `https://registry.opendata.aws/sentinel-2-l2a-cogs/`.
- Do sprawdzenia przez człowieka przed wdrożeniem: warunki korzystania z publicznego interfejsu (dokumentu nie
  znaleziono), warunki i cennik oferty dla użycia produkcyjnego.

**Usługa modelu językowego (opcjonalna)**

- Co wolno: zależy od dostawcy wybranego przy wdrożeniu; repozytorium nie wskazuje dostawcy ani modelu.
- Klucz, konto, płatny plan: konto, klucz i opłaty według cennika dostawcy; jedno krótkie zapytanie na analizę.
- Limity: według planu u dostawcy; przekroczenie kończy się podsumowaniem z szablonu, nie błędem analizy.
- Do sprawdzenia przez człowieka przed wdrożeniem: warunki korzystania, cennik, limity, zasady przetwarzania
  i przechowywania danych oraz miejsce przetwarzania u wybranego dostawcy.

**Let's Encrypt (certyfikat TLS, przez Traefika)**

- Co wolno: bezpłatne certyfikaty na warunkach umowy subskrybenta Let's Encrypt.
- Klucz, konto, płatny plan: konto na adres e-mail administratora, bez opłat.
- Limity: m.in. do 50 certyfikatów na zarejestrowaną domenę w ciągu 7 dni i do 300 nowych zamówień na konto
  w ciągu 3 godzin.
- Źródła: `https://letsencrypt.org/repository/`, `https://letsencrypt.org/docs/rate-limits/`.
- Zalecenie niesprawdzone: instytucja może wymagać certyfikatu z własnego urzędu certyfikacji; wtedy konfigurację
  Traefika trzeba zmienić poza skryptem wdrożenia.

### Usługi, które obowiązują po podłączeniu

Aplikacja jeszcze z nich nie korzysta; wdrożenie pełnoskalowe będzie ich potrzebować (rozdział 2).

- **BDOT10k (GUGiK), cieki, rowy i zbiorniki** (po podłączeniu): zbiory udostępniane bez opłat na podstawie ustawy
  Prawo geodezyjne i kartograficzne (art. 40a ust. 2 pkt 1 lit. h); bez konta i klucza; podawane źródło: „BDOT10k,
  Główny Urząd Geodezji i Kartografii”. Usługa przeglądania BDOT10k zastrzega w swoim opisie zakaz automatycznego
  pobierania i gromadzenia informacji, dlatego dane trzeba brać z plików do pobrania, nie z usługi przeglądania
  (odczyt 21.11.2026). Do sprawdzenia przez człowieka przed wdrożeniem: dokument licencji i wymagany zapis źródła
  dla plików do pobrania; częstotliwość ich aktualizacji.
- **OpenStreetMap przez usługę Overpass** (po podłączeniu): dane na licencji ODbL 1.0 z wymaganym podaniem źródła
  „© autorzy OpenStreetMap” (odpowiedź serwera, odczyt 21.11.2026). Do sprawdzenia przez człowieka przed
  wdrożeniem: zasady korzystania z publicznego serwera Overpass i obowiązki wynikające z ODbL dla danych
  zapisywanych w Raporcie (tekstu licencji nie analizowano).
- **Usługa wysokości punktów GUGiK (numeryczny model terenu 1 m)** (po podłączeniu): „Dane NMT są dostępne
  bezpłatnie i możliwe do dowolnego wykorzystania” (`https://www.geoportal.gov.pl/pl/dane/numeryczny-model-terenu-nmt/`);
  bez konta i klucza. Strona usługi (`https://services.gugik.gov.pl/nmt/`) nie podaje limitów ani warunków.
  Do sprawdzenia przez człowieka przed wdrożeniem: limity i warunki usługi przy stałym ruchu; alternatywą są
  arkusze modelu pobrane na własny dysk.
- **Mapa kategorii podatności gleb na suszę, usługa mapowa IUNG-PIB** (po podłączeniu): usługa publiczna
  i bezpłatna; licencji ani regulaminu nie opublikowano (odczyt 21.11.2026 i 22.11.2026). Wymagany krok przed
  wdrożeniem: zapytanie do IUNG-PIB o zgodę na stałe, automatyczne korzystanie z usługi i o warunki ponownego
  wykorzystania danych. Podawane źródło: „Kategorie podatności gleb na suszę: IUNG-PIB, System Monitoringu Suszy
  Rolniczej, opracowanie na zlecenie Ministerstwa Rolnictwa i Rozwoju Wsi”.
- **SoilGrids przez usługę WCS (ISRIC)** (po podłączeniu): licencja CC BY 4.0 jak wyżej; limitu zapytań
  dokumentacja nie podaje; przy stałym ruchu rozważyć własną kopię map.

## 7. Przegląd prawny i zestawienie pozycji do sprawdzenia przez człowieka przed wdrożeniem

Ten dokument streszcza strony dostawców i nie zastępuje oceny prawnej. Przed uruchomieniem usługi człowiek
powinien rozstrzygnąć:

1. **Charakter użycia:** czy usługa prowadzona przez instytucję publiczną albo na jej zlecenie jest użyciem
   komercyjnym w rozumieniu warunków Open-Meteo.
2. **Pogoda:** aktualna cena, limity i warunki subskrypcji Open-Meteo albo warunki własnej instalacji.
3. **Dane satelitarne:** warunki korzystania z Planetary Computer; warunki, limity i cennik dostępu płatnego lub
   gwarantowanego w Planetary Computer i Earth Search.
4. **Gleba:** zgoda i warunki IUNG-PIB dla usługi mapy kategorii podatności gleb na suszę.
5. **Teren i wody:** limity i warunki usługi wysokości punktów GUGiK; licencja i zapis źródła plików BDOT10k;
   zasady serwera Overpass i skutki licencji ODbL.
6. **Model językowy:** umowa, cennik i zasady przetwarzania danych u wybranego dostawcy.
7. **Dane osobowe:** Identyfikator działki da się powiązać z właścicielem w rejestrach publicznych; trzeba ustalić
   administratora danych, czas przechowywania Raportów i logów oraz obowiązki informacyjne. Aplikacja nie ma kont
   i nie zbiera innych danych osobowych.
8. **Noty o pochodzeniu danych** w Raporcie, na stronie i na wydruku: komplet i brzmienie wymagane przez każdą
   licencję (README, punkt 7).
9. **Koszty:** łączny koszt miesięczny dla przyjętej liczby analiz (plan pogodowy, dostęp do danych
    satelitarnych, model językowy, serwery, baza, miejsce na kopie). Nie został oszacowany, bo wymaga cenników
    z punktów 2, 3 i 7.
10. **Licencja kodu rozwiązania** i prawa do korzystania z niego przez instytucję wdrażającą.

Do sprawdzenia technicznego przed wdrożeniem (nie wykonano): pełny przebieg skryptu wdrożenia na czystym serwerze
z domeną, praca usługi w wielu procesach po zmianach z rozdziału 4, zachowanie przy więcej niż trzech analizach
jednocześnie, zachowanie źródeł po przekroczeniu limitów, odtworzenie bazy z kopii zapasowej.

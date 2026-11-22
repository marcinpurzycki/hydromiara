# Hydromiara: instrukcja wdrożenia pokazowego (demo)

Instrukcja dla osoby, która chce uruchomić prototyp pod własną domeną, żeby go pokazać albo ocenić: jeden serwer,
wyłącznie bezpłatne dostępy do danych, bez kont i kluczy (poza opcjonalnym modelem językowym). Wdrożenie dla wielu
rolników opisuje osobny dokument: [wdrożenie pełnoskalowe](wdrozenie-pelnoskalowe.md). Pozostała dokumentacja jest
w [README](../README.md).

Rozdział 5 streszcza warunki korzystania z usług zewnętrznych na podstawie stron ich dostawców, z adresem i datą
odczytu. Nie jest poradą prawną. Miejsca oznaczone **„do potwierdzenia przed wdrożeniem produkcyjnym”** to
warunki, których nie dało się odczytać albo które nie rozstrzygają sprawy jednoznacznie.

## 1. Co jest potrzebne

- Serwer Linux z publicznym adresem, otwarte porty 80 i 443, uprawnienia roota (bezpośrednio albo przez `sudo`),
  `bash`, `curl` i `git`. Wystarcza jeden mały serwer: pomiar czasów wykonano na maszynie z dwoma procesorami.
- Domena z rekordem DNS wskazującym na ten serwer.
- Docker Engine z wtyczką Compose (wersja 2 lub nowsza). Na systemach Debian i Ubuntu skrypt instaluje go sam;
  na innych dystrybucjach trzeba to zrobić wcześniej według instrukcji Dockera.
- Opcjonalnie: konto i klucz w usłudze modelu językowego z interfejsem zgodnym z OpenAI Chat Completions.
  Bez niego aplikacja działa w pełni, a podsumowanie raportu pochodzi z szablonu.
- Opcjonalnie: pliki wskaźnika suszy (rozdział 3).

Żadna usługa danych nie wymaga w tym trybie konta, klucza ani opłaty.

## 2. Wdrożenie

Wdrożenie wykonuje jeden skrypt, uruchamiany w katalogu repozytorium na serwerze:

```bash
git clone ADRES_REPOZYTORIUM hydromiara && cd hydromiara
scripts/deploy.sh --dry-run     # tylko wykrywa i pokazuje plan; niczego nie zmienia i o nic nie pyta
scripts/deploy.sh               # pyta o brakujące wartości, pokazuje plan i czeka na zgodę
```

Skrypt wykonuje pięć kroków, a każdy można powtarzać:

1. **Docker**: sprawdza instalację albo, po potwierdzeniu, instaluje Docker Engine i Compose (Debian, Ubuntu).
2. **Traefik**: działającego Traefika i sieci `proxy` nie zmienia, tylko odczytuje nazwy punktu wejścia HTTPS
   i resolvera certyfikatów. Gdy Traefika nie ma, a porty 80 i 443 są wolne, uruchamia własnego
   (`deploy/traefik/docker-compose.yml`, certyfikaty Let's Encrypt) i pyta o adres e-mail konta Let's Encrypt.
3. **Domena**: pyta o domenę i porównuje jej rekord DNS z adresami serwera.
4. **Model językowy (opcjonalnie)**: adres bazowy usługi, nazwa modelu i klucz; opcja `--no-ai` pomija ten krok.
5. **Uruchomienie**: `docker compose up -d --build`, oczekiwanie na zdrowie usługi `api`, sprawdzenie
   `https://DOMENA/api/health` i strony głównej.

Ustawienia trafiają do pliku `.env` (prawa `600`, kopia przed każdą zmianą); wartości nie są wypisywane na ekran.
Pełny opis kroków, opcji, zachowania na serwerze z innymi usługami, aktualizacji i wycofania jest w README, część
„Wdrożenie”; lista opcji: `scripts/deploy.sh --help`. Wdrożenie bez pytań i bez modelu językowego:
`scripts/deploy.sh --yes --domain DOMENA --no-ai`.

**Sprawdzenie po wdrożeniu:** `docker compose ps` (usługa `api` w stanie `healthy`),
`curl -fsS https://DOMENA/api/health` (odpowiedź `{"status":"ok"}`), `docker compose logs --tail 50 api`.

**Weryfikacja.** Wdrożenie zweryfikowano 22.11.2026 na serwerze z systemem Debian 13 i działającym Traefikiem:
aplikacja działa pod domeną z certyfikatem. Skrypt ma też testy z atrapami poleceń systemowych
(`scripts/deploy/tests/run.sh`). Nagłówka HSTS skrypt nie ustawia.

## 3. Pliki wskaźnika suszy

Tło suszowe (wskaźnik CDI Europejskiego Obserwatorium Suszy) jest jedynym źródłem czytanym z plików lokalnych.
Archiwa roczne (stan na 21.11.2026) są w repozytorium w `deploy/edo-archives/`. Skrypt wdrożenia tworzy katalog
`EDO_DATA_PATH` (domyślnie `./data/edo`), rozpakowuje do niego te archiwa, gdy katalog jest pusty (wymaga `python3`
na serwerze), sprawdza, czy użytkownik kontenera (uid 10001) może go czytać, i podaje liczbę znalezionych plików.

1. Ręczne rozpakowanie, gdyby skrypt go nie wykonał: `python3 scripts/unpack_drought_files.py deploy/edo-archives`
   (restart usługi nie jest potrzebny).
2. Nowa dekada pojawia się co 10 dni. Nowsze archiwum pobiera się z katalogu `EDO_Combined_Drought_Indicator` pod
   adresem `https://drought.emergency.copernicus.eu/data/Drought_Observatories_datasets/` i rozpakowuje tym samym
   poleceniem; kroki, także aktualizacji archiwów w repozytorium, opisuje `deploy/edo-archives/README.md`.

Bez tych plików wdrożenie działa, a raport podaje brak tła suszowego jako Ograniczenie.

## 4. Limity w wersji pokazowej

### Limity aplikacji

Usługa liczy zapytania na adres odwiedzającego, w pamięci jednego procesu. Wartości domyślne (zmieniane w `.env`,
pełna tabela w README, część „Konfiguracja”):

| Zmienna | Wartość domyślna | Znaczenie |
|---|---|---|
| `RATE_LIMIT_ANALYSIS_PER_MINUTE`, `RATE_LIMIT_ANALYSIS_PER_HOUR` | `6`, `50` | starty analiz z jednego adresu |
| `RATE_LIMIT_DERIVE_PER_MINUTE` | `10` | raporty pochodne z jednego adresu na minutę |
| `RATE_LIMIT_LOOKUP_PER_MINUTE` | `40` | wyszukiwania działek z jednego adresu na minutę |
| `RATE_LIMIT_SIMULATION_PER_MINUTE` | `30` | zapytania Symulacji z jednego adresu na minutę |
| `RATE_LIMIT_STATUS_PER_MINUTE`, `RATE_LIMIT_OTHER_PER_MINUTE` | `600`, `300` | postęp analizy i pozostałe zapytania |
| `MAX_CONCURRENT_ANALYSES` | `4` | analizy trwające jednocześnie w całej usłudze |
| `RATE_LIMIT_ENABLED` | `1` | `0` wyłącza limity na adres |

`FORWARDED_ALLOW_IPS` musi wskazywać adres albo podsieć Traefika (skrypt wpisuje podsieć sieci `proxy`, o ile
wartości nie ma w `.env`). Bez tego usługa widzi wszystkich odwiedzających pod adresem Traefika i liczy im jeden
wspólny limit. Przy wdrożeniu trzeba potwierdzić, że Traefik zastępuje nagłówek `X-Forwarded-For`
przysłany przez klienta własną wartością.

### Limity usług zewnętrznych liczone na adres serwera

Wszystkie analizy wychodzą z jednego adresu IP serwera, więc limity dostawców dotyczą całego wdrożenia, a nie
pojedynczego odwiedzającego.

- **Pogoda (Open-Meteo) jest najciaśniejszym limitem.** Bezpłatny dostęp to mniej niż 600 zapytań na minutę,
  5000 na godzinę i 10 000 na dobę, przy czym zapytanie o więcej niż 2 tygodnie danych liczy się wielokrotnie.
  Jedna analiza (ponad 10 lat danych dziennych) zużywa około 88 jednostek, co daje około 6 analiz na minutę,
  56 na godzinę i 113 na dobę z adresu serwera. Limit dobowy odnawia się o północy czasu UTC; po jego wyczerpaniu
  nowe analizy kończą się niepowodzeniem do końca doby (zaobserwowane 22.11.2026 na maszynie deweloperskiej).
- **W dniu pokazu nie uruchamiaj z adresu serwera programów pomiarowych** (`scripts/measure_sources.py`,
  `scripts/backtest.py`): zużywają ten sam limit pogody co analizy odwiedzających.
- **Działki (ULDK):** 200 zapytań na minutę w godzinach 6–18, 40 na minutę w pozostałych, 10 000 na dobę z jednego
  adresu IP. Domyślny limit aplikacji (40 wyszukiwań na minutę na odwiedzającego) nie chroni przed przekroczeniem
  limitu nocnego przy kilku odwiedzających naraz.
- **Gleba (SoilGrids REST):** zasada uczciwego korzystania to 5 zapytań na minutę; usługa bywa wolna albo
  niedostępna. Raport powstaje wtedy bez danych o glebie, z Ograniczeniem.
- **Dane satelitarne:** dostawcy nie podają limitów liczbowo; ochroną przed niedostępnością jest druga, wymienna
  usługa (`SATELLITE_PRIMARY`, `SATELLITE_SECONDARY`).
- **Certyfikat (Let's Encrypt):** do 50 certyfikatów na zarejestrowaną domenę w ciągu 7 dni; ma znaczenie tylko
  przy wielokrotnym stawianiu wdrożenia od zera pod tą samą domeną.

## 5. Licencje i warunki korzystania z usług zewnętrznych w wersji pokazowej

Wersja pokazowa to prototyp konkursowy: bez opłat, reklam i subskrypcji, z niewielkim ruchem. Każdy Raport podaje
przy swoich źródłach nazwę i warunki (`sources[]`), a README (punkt 7) zawiera wymagane informacje o pochodzeniu
danych. Data odczytu stron: 22.11.2026, o ile nie podano inaczej.

### Usługi, z których aplikacja korzysta dziś

**ULDK (Główny Urząd Geodezji i Kartografii), działki ewidencyjne**

- Co wolno: korzystanie bezpłatne, także w aplikacji komercyjnej, bez umowy licencyjnej z GUGiK.
- Klucz, konto, płatny plan: nie są potrzebne.
- Limity: 200 zapytań na minutę w godzinach 6–18, 40 na minutę w pozostałych; 10 000 na dobę na adres IP.
- Podanie źródła: wymagane, np. „Źródło: Główny Urząd Geodezji i Kartografii (GUGiK), Usługa Lokalizacji Działek
  Katastralnych (ULDK).”
- Źródło: opis usługi z odpowiedziami na pytania, `https://uldk.gugik.gov.pl/opis.html`.

**Open-Meteo, archiwum pogodowe**

- Co wolno: bezpłatny dostęp wyłącznie do zastosowań niekomercyjnych. Warunki podają jako przykłady użycia
  niekomercyjnego m.in. prywatne lub niezarobkowe strony i aplikacje bez subskrypcji i reklam; jako komercyjne
  strony i aplikacje z subskrypcją lub reklamami oraz produkty komercyjne. Prototyp konkursowy odpowiada
  przykładom niekomercyjnym.
- Klucz, konto, płatny plan: nie są potrzebne w dostępie bezpłatnym.
- Limity: mniej niż 10 000 zapytań na dobę, 5000 na godzinę i 600 na minutę (cennik podaje też 300 000
  na miesiąc); limity są stosowane na adres IP i aplikację; zapytanie o więcej niż 10 zmiennych albo więcej niż
  2 tygodnie liczy się jako wiele zapytań. Dostęp bezpłatny nie ma gwarancji dostępności.
- Podanie źródła: dane na licencji CC BY 4.0, wymagane podanie źródła z odnośnikiem i zaznaczenie zmian.
- Źródła: `https://open-meteo.com/en/terms`, `https://open-meteo.com/en/pricing`,
  `https://open-meteo.com/en/licence`.

**SoilGrids 2.0 (ISRIC – World Soil Information), gleba, usługa REST**

- Co wolno: dane na licencji CC BY 4.0.
- Klucz, konto, płatny plan: nie są potrzebne.
- Limity: zasada uczciwego korzystania to 5 zapytań na minutę. Usługa REST jest w fazie beta, bez gwarancji
  dostępności i wsparcia; w dniu odczytu strona zawierała komunikat o czasowym wstrzymaniu usługi. ISRIC zaleca
  przy potrzebie stabilności inne sposoby dostępu (WebDAV, usługi sieciowe).
- Podanie źródła: wymagane (CC BY 4.0); cytowanie w README, punkt 7.
- Źródło: `https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_02.html`.

**Europejskie Obserwatorium Suszy (EDO), wskaźnik CDI, pliki lokalne**

- Co wolno: bezpłatny dostęp do danych EDO z prawem powielania, rozpowszechniania, publicznego udostępniania,
  adaptacji, modyfikacji i łączenia z innymi danymi; bez gwarancji. Dane mają charakter informacyjny i nie są
  ostrzeżeniem, do którego uprawnione są wyłącznie instytucje krajowe.
- Klucz, konto, płatny plan: nie są potrzebne (pliki pobiera się raz, bez rejestracji).
- Limity: nie dotyczą analizy (odczyt z plików lokalnych); limitów pobierania plików strona warunków nie podaje.
- Podanie źródła: wymagana nota „Generated using Copernicus Emergency Management Service information [rok]”,
  a przy danych zmienionych „Contains modified Copernicus Emergency Management Service information [rok]”.
- Źródło: `https://drought.emergency.copernicus.eu/terms&conditions/`.
- Licencja: CC BY 4.0 (ustalenie zespołu z 22.11.2026). Strona warunków, odczytana 22.11.2026, nie wymienia tej
  licencji z nazwy, tylko podaje prawa i noty opisane wyżej.

**Copernicus DEM GLO-30, ukształtowanie terenu (pliki w rejestrze otwartych danych AWS)**

- Co wolno: dane dostępne bezpłatnie dla każdego na warunkach licencji Copernicus DEM; licencja daje prawo
  powielania, rozpowszechniania, publicznego udostępniania, adaptacji, modyfikacji i łączenia z innymi danymi,
  bez opłat i bez ograniczenia w czasie.
- Klucz, konto, płatny plan: nie są potrzebne (odczyt bez konta AWS). Arkusz jest wyszukiwany w katalogu
  Earth Search (warunki niżej).
- Limity: strona rejestru nie podaje limitów.
- Podanie źródła: wymagana nota o prawach autorskich, a przy danych przetworzonych nota „produced using Copernicus
  WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the
  European Union and ESA; all rights reserved”; nie wolno sugerować, że działalność użytkownika jest oficjalnie
  popierana przez dostawcę lub program Copernicus.
- Źródła: `https://registry.opendata.aws/copernicus-dem/`; tekst licencji „Licence for the use of the Copernicus
  WorldDEM-30” (odczytany z kopii pod adresem
  `https://docs.sentinel-hub.com/api/latest/static/files/data/dem/resources/license/License-COPDEM-30.pdf`).

**Copernicus Sentinel-2 L2A, dane satelitarne**

- Co wolno: dostęp bezpłatny, pełny i otwarty; dozwolone powielanie, rozpowszechnianie, przetwarzanie i łączenie
  z innymi danymi.
- Podanie źródła: przy danych przetworzonych wymagana informacja „Contains modified Copernicus Sentinel data [rok]”.
- Źródła: nota prawna danych Sentinel, `https://sentinel.esa.int/documents/247904/690755/Sentinel_Data_Legal_Notice`
  (odczyt 21.11.2026; 22.11.2026 adres nie odpowiadał); `https://registry.opendata.aws/sentinel-2-l2a-cogs/`.

**Microsoft Planetary Computer, podstawowa usługa danych satelitarnych**

- Co wolno: według dokumentacji dane są bezpłatne dla każdego i dostępne anonimowo.
- Klucz, konto, płatny plan: token odczytu plików wydawany jest bez konta i bez klucza subskrypcji; aplikacja
  klucza nie obsługuje.
- Limity: istnieją, ale bez podanych liczb; zależą od regionu Azure, z którego przychodzi zapytanie, i od tego,
  czy podano klucz subskrypcji. Token ma ograniczony czas ważności.
- Źródło: dokument o tokenach dostępu w repozytorium dokumentacji usługi,
  `https://github.com/microsoft/PlanetaryComputerDataCatalog` (plik `docs/concepts/sas.md`); repozytorium jest
  zarchiwizowane, więc treść może być nieaktualna.
- Do potwierdzenia przed wdrożeniem produkcyjnym: strony warunków korzystania
  (`https://planetarycomputer.microsoft.com/terms`) nie dało się odczytać automatycznie; nie ustalono, czy warunki
  ograniczają rodzaj użycia.

**Earth Search (Element 84), zapasowa usługa danych satelitarnych i katalog arkuszy modelu terenu**

- Co wolno: publiczny interfejs opisany jako bezpłatny w użyciu; „nie daje żadnej gwarancji usługi”.
- Klucz, konto, płatny plan: nie są potrzebne. Pliki pasm leżą w rejestrze otwartych danych AWS i nie wymagają
  konta AWS.
- Limity: nieopisane.
- Źródła: `https://github.com/Element84/earth-search` (plik `README.md`),
  `https://registry.opendata.aws/sentinel-2-l2a-cogs/`.
- Do potwierdzenia przed wdrożeniem produkcyjnym: osobnego dokumentu warunków korzystania z publicznego interfejsu
  nie znaleziono.

**Usługa modelu językowego (opcjonalna)**

- Co wolno: zależy od dostawcy wybranego przy wdrożeniu (dowolna usługa z interfejsem zgodnym z OpenAI Chat
  Completions); repozytorium nie wskazuje dostawcy ani modelu.
- Klucz, konto, płatny plan: konto i klucz u dostawcy, opłaty według jego cennika. Aplikacja działa w pełni bez
  tej usługi.
- Limity: według planu u dostawcy; aplikacja wysyła jedno krótkie zapytanie na analizę, a każdy błąd lub limit
  kończy się podsumowaniem z szablonu.
- Co jest wysyłane: wyłącznie wybrane teksty gotowego raportu, bez Identyfikatora działki, nazw miejsc
  i współrzędnych (README, „AI w działaniu aplikacji”).
- Do potwierdzenia przed wdrożeniem produkcyjnym: warunki korzystania, cennik oraz zasady przetwarzania
  i przechowywania danych u wybranego dostawcy.

**Let's Encrypt (certyfikat TLS, przez Traefika)**

- Co wolno: bezpłatne certyfikaty na warunkach umowy subskrybenta Let's Encrypt.
- Klucz, konto, płatny plan: konto zakłada Traefik na adres e-mail podany przy wdrożeniu (dana osobowa, tylko
  w `.env`); bez opłat. Nazwa domeny trafia do publicznych rejestrów wystawionych certyfikatów.
- Limity: m.in. do 50 certyfikatów na zarejestrowaną domenę w ciągu 7 dni.
- Źródła: `https://letsencrypt.org/repository/`, `https://letsencrypt.org/docs/rate-limits/`.
- Gdy na serwerze działa już Traefik, obowiązują ustawienia i konto jego administratora.

Traefik, Docker i pozostałe komponenty uruchamiane na serwerze są oprogramowaniem na licencjach otwartych
(README, punkt 6), nie usługami zewnętrznymi.

### Pozostałe źródła

Źródła podłączone 22.11.2026 (wody, teren 1 m, gleba z mapy IUNG-PIB i z usługi WCS) oraz jedno przewidziane,
ale niepodłączone (OpenStreetMap przez usługę Overpass).

- **BDOT10k (GUGiK), cieki, rowy i zbiorniki** (podłączone): zbiory obiektów topograficznych tej szczegółowości
  są udostępniane bez opłat na podstawie ustawy Prawo geodezyjne i kartograficzne (art. 40a ust. 2 pkt 1 lit. h).
  Konto ani klucz nie są potrzebne. Podawane źródło: „BDOT10k, Główny Urząd Geodezji i Kartografii”. Limitów
  pobierania nie opublikowano; serwer plików zrywał część połączeń równoległych (obserwacja z 21.11.2026).
  Do potwierdzenia przed wdrożeniem produkcyjnym: dokumentu licencji i wymaganego zapisu źródła dla plików
  udostępnianych do pobrania nie znaleziono.
- **OpenStreetMap przez usługę Overpass, zamiennik danych o wodach** (niepodłączone): dane na licencji ODbL 1.0,
  wymagane podanie źródła „© autorzy OpenStreetMap” (odpowiedź serwera, odczyt 21.11.2026). Do potwierdzenia przed wdrożeniem
  produkcyjnym: zasady korzystania i limity operatora publicznego serwera Overpass nie zostały
  przeczytane.
- **Usługa wysokości punktów GUGiK (numeryczny model terenu 1 m)** (podłączone): „Dane NMT są dostępne
  bezpłatnie i możliwe do dowolnego wykorzystania” (strona opisu danych,
  `https://www.geoportal.gov.pl/pl/dane/numeryczny-model-terenu-nmt/`). Konto ani klucz nie są potrzebne. Strona
  usługi (`https://services.gugik.gov.pl/nmt/`) nie podaje limitów ani warunków; zaobserwowano do 1000 punktów
  w jednym zapytaniu. Do potwierdzenia przed wdrożeniem produkcyjnym: limity i warunki samej usługi.
- **Mapa kategorii podatności gleb na suszę, usługa mapowa IUNG-PIB** (podłączone): usługa publiczna
  i bezpłatna, bez konta i klucza; opis usługi podaje brak opłat i brak ograniczeń dostępu, ale mogą to być
  wartości domyślne oprogramowania serwera. Strona systemu (`https://susza.iung.pulawy.pl/mapa-kategorii/`) nie
  podaje licencji ani regulaminu (odczyt 21.11.2026 i 22.11.2026). W wersji pokazowej pobierane są pojedyncze
  wartości z podaniem źródła: „Kategorie podatności gleb na suszę: IUNG-PIB, System Monitoringu Suszy Rolniczej,
  opracowanie na zlecenie Ministerstwa Rolnictwa i Rozwoju Wsi”. Do potwierdzenia przed wdrożeniem produkcyjnym:
  warunki ponownego wykorzystania.
- **SoilGrids przez usługę WCS (ISRIC)** (podłączone): te same dane i ta sama licencja CC BY 4.0 co wyżej;
  ISRIC wskazuje usługi sieciowe jako stabilniejszy sposób dostępu niż REST. Limitu zapytań dla WCS dokumentacja
  nie podaje.

## 6. Zestawienie pozycji do potwierdzenia przed wdrożeniem produkcyjnym

- Warunki korzystania z Planetary Computer (strona nieodczytana) i z publicznego interfejsu Earth Search
  (dokumentu nie znaleziono).
- Warunki i cennik wybranego dostawcy modelu językowego, jeśli jest używany.
- Warunki usługi IUNG-PIB, usługi wysokości punktów GUGiK i plików BDOT10k; warunki publicznego serwera
  Overpass, gdyby został podłączony.

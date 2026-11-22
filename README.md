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
| Działająca wersja | do uzupełnienia przed zgłoszeniem: adres wdrożenia |
| Prezentacja (PDF), film, raporty wygenerowane przez prototyp | do uzupełnienia przed zgłoszeniem: gdzie się znajdują |

## Spis treści

Dokumentacja jest ułożona według dziewięciu punktów wymaganych w zadaniu (rozdz. 4.2), w tej samej kolejności:

1. [Instrukcja uruchomienia rozwiązania](#1-instrukcja-uruchomienia-rozwiązania)
2. [Opis podstawowych funkcjonalności](#2-opis-podstawowych-funkcjonalności)
3. [Skrócony opis architektury rozwiązania](#3-skrócony-opis-architektury-rozwiązania)
4. [Opis wykorzystanych źródeł i zakresów danych](#4-opis-wykorzystanych-źródeł-i-zakresów-danych)
5. [Wskazanie, które dane są pobierane na bieżąco, a które zostały pobrane lub przetworzone wcześniej, wraz z datami ich pobrania](#5-wskazanie-które-dane-są-pobierane-na-bieżąco-a-które-zostały-pobrane-lub-przetworzone-wcześniej-wraz-z-datami-ich-pobrania)
6. [Wykaz wykorzystanych bibliotek, komponentów, modeli, usług zewnętrznych i narzędzi sztucznej inteligencji](#6-wykaz-wykorzystanych-bibliotek-komponentów-modeli-usług-zewnętrznych-i-narzędzi-sztucznej-inteligencji)
7. [Wskazanie licencji lub innych warunków korzystania z danych i komponentów](#7-wskazanie-licencji-lub-innych-warunków-korzystania-z-danych-i-komponentów)
8. [Opis znanych ograniczeń technicznych rozwiązania](#8-opis-znanych-ograniczeń-technicznych-rozwiązania)
9. [Informacja o sposobie weryfikacji wygenerowanych wyników lub rekomendacji](#9-informacja-o-sposobie-weryfikacji-wygenerowanych-wyników-lub-rekomendacji)

Poza dziewięcioma punktami: [Skalowanie](#skalowanie), [Bezpieczeństwo i dane osobowe](#bezpieczeństwo-i-dane-osobowe).
Szczegółowy opis metody: [docs/metoda.md](docs/metoda.md).

Miejsca oznaczone „do uzupełnienia przed zgłoszeniem” opisują to, czego w chwili pisania nie da się jeszcze podać
(wyników, pomiarów albo części budowanych osobno); nic w nich nie jest założone z góry.

## 1. Instrukcja uruchomienia rozwiązania

Rozwiązanie składa się z dwóch usług w jednym pliku `docker-compose.yml`: `api` (kod w katalogu `backend/`) i `web`
(strona dla rolnika: kod w katalogu `frontend/`, zbudowane pliki serwuje `nginx`).

### Lokalnie, bez Dockera

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
REPORTS_DB_PATH=./data/reports.sqlite3 .venv/bin/fastapi dev app/main.py   # http://127.0.0.1:8000/api/docs
.venv/bin/python -m pytest               # testy bez dostępu do sieci
.venv/bin/python -m tests.smoke.parcels_smoke   # sprawdzenie na żywej usłudze działek (wymaga sieci)
.venv/bin/python -m tests.smoke.hydro_smoke     # wody w otoczeniu dwóch działek z żywych plików BDOT10k: czas, liczba zapytań, obiekty, pamięć (wymaga sieci)
.venv/bin/python -m tests.smoke.soil_smoke      # gleba trzech działek na żywych usługach: które ogniwo odpowiedziało, czas, kategoria, pojemność (wymaga sieci)
.venv/bin/python -m tests.smoke.satellite_smoke # sprawdzenie na żywych usługach scen satelitarnych, w tym przełączenia (wymaga sieci)
.venv/bin/python -m tests.smoke.analysis_smoke  # cała analiza jednej działki na żywych źródłach, z czasem każdego źródła (wymaga sieci)
.venv/bin/python -m tests.smoke.season_smoke    # raport poza sezonem lub w spoczynku i przejście na Okres krytyczny, na żywych źródłach (wymaga sieci)
.venv/bin/python -m tests.smoke.history_smoke   # analiza i raport pochodny z Historią upraw: czas, Przebieg historyczny, niezmieniona Podatność wieloletnia (wymaga sieci)
.venv/bin/python -m tests.smoke.simulation_smoke # analiza jednej działki, potem Ranking upraw i porównanie z jedną Uprawą, z czasami odpowiedzi (wymaga sieci)
EDO_DATA_PATH=./data/edo .venv/bin/python -m tests.smoke.full_analysis_smoke  # analizy trzech działek, dwie daty, kilka przebiegów: tabela czasów i wyników każdego źródła (wymaga sieci; kilka minut)
```

Opis interfejsu: `/api/docs` (Swagger UI) i `/api/openapi.json`.

### Lokalnie w Dockerze

Strona na `http://localhost:8080`, API na `http://127.0.0.1:8000` (strona sięga do niego pod ścieżką `/api`):

```bash
cp .env.example .env                     # uzupełnij DOMAIN, TRAEFIK_ENTRYPOINT, TRAEFIK_CERTRESOLVER
docker network create proxy              # jednorazowo
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

Praca nad samą stroną (Node.js 22; API uruchomione jak wyżej albo bez Dockera):

```bash
cd frontend
npm ci
npm run dev                              # http://localhost:5173, zapytania /api idą do 127.0.0.1:8000
npm test                                 # testy
npm run build                            # sprawdzenie typów i zbudowanie plików do katalogu dist/
```

### Wdrożenie

Wdrożenie na serwerze Linux wykonuje jeden skrypt, uruchamiany w katalogu repozytorium:

```bash
git clone ADRES_REPOZYTORIUM hydromiara && cd hydromiara
scripts/deploy.sh --dry-run     # tylko wykrywa i pokazuje plan; niczego nie zmienia i o nic nie pyta
scripts/deploy.sh               # pyta o brakujące wartości, pokazuje plan i czeka na zgodę
```

**Wymagania:** serwer Linux z publicznym adresem, rekord DNS domeny wskazujący na ten serwer, otwarte porty 80 i 443,
`bash`, `curl` i `git`, uprawnienia roota (bezpośrednio albo przez `sudo`). Dockera skrypt instaluje sam na systemach
Debian i Ubuntu (z oficjalnego repozytorium pakietów Dockera); na innych dystrybucjach trzeba najpierw zainstalować
Docker Engine i wtyczkę Compose według instrukcji Dockera, a skrypt zrobi resztę.

**Pięć kroków skryptu** (każdy można powtarzać; ponowne uruchomienie niczego nie psuje):

1. **Docker.** Gdy jest zainstalowany, skrypt tylko sprawdza, czy działa i czy jest wtyczka Compose (wersja 2 lub
   nowsza). Gdy go nie ma, po potwierdzeniu instaluje Docker Engine i Compose, włącza usługę przy starcie systemu
   i ustawia rotację logów kontenerów.
2. **Traefik.** Gdy na serwerze działa już Traefik, skrypt odczytuje z niego nazwy punktu wejścia HTTPS i resolvera
   certyfikatów i proponuje je do `.env`. Gdy Traefika nie ma, a porty 80 i 443 są wolne, tworzy sieć `proxy`
   i uruchamia własnego z pliku `deploy/traefik/docker-compose.yml` (przekierowanie na HTTPS, certyfikaty
   Let's Encrypt, bez panelu administracyjnego, gniazdo Dockera tylko do odczytu); pyta wtedy o adres e-mail konta
   Let's Encrypt. Gdy porty zajmuje coś innego niż Traefik, skrypt zatrzymuje się z komunikatem.
3. **Domena.** Pytanie o domenę (albo `--domain`), sprawdzenie rekordu DNS przez resolver systemowy i porównanie
   z adresami serwera, bez pytania usług zewnętrznych. Gdy zgodności nie da się potwierdzić (brak rekordu albo serwer
   za translacją adresów), skrypt ostrzega i pyta, czy kontynuować.
4. **Model językowy (opcjonalnie).** Adres bazowy usługi zgodnej z OpenAI Chat Completions, nazwa modelu i klucz
   (wpisywany bez wyświetlania). Bez tej konfiguracji albo z opcją `--no-ai` podsumowanie raportu pochodzi z szablonu.
5. **Uruchomienie.** `docker compose up -d --build`, oczekiwanie na zdrowie usługi `api`, sprawdzenie
   `https://DOMENA/api/health` i strony głównej. Przy niepowodzeniu skrypt podaje prawdopodobną przyczynę: DNS albo
   zapora, certyfikat, etykiety Traefika albo kontener.

Skrypt ustawia też `FORWARDED_ALLOW_IPS` na podsieć sieci `proxy`, o ile wartości nie ma jeszcze w `.env`. Bez niej
usługa widzi wszystkich odwiedzających pod adresem Traefika i liczy im wspólny limit zapytań (patrz „Bezpieczeństwo
i dane osobowe”). Limity (domyślnie 6 startów analizy na minutę i 50 na godzinę z jednego adresu, 4 analizy naraz)
zmienia się zmiennymi `RATE_LIMIT_*` i `MAX_CONCURRENT_ANALYSES` w `.env` (tabela w części „Konfiguracja”).

**Na serwerze, na którym działają już inne usługi,** skrypt:

- nie zmienia, nie restartuje i nie przebudowuje działającego Traefika, nie dotyka jego konfiguracji, certyfikatów,
  portów 80 i 443 ani istniejącej sieci `proxy`; nie uruchamia drugiego Traefika;
- nie zmienia instalacji Dockera ani jego konfiguracji. Rotacja logów na poziomie całego Dockera wymaga jego restartu,
  czyli chwilowej przerwy we wszystkich kontenerach serwera, dlatego jest domyślnie pomijana z komunikatem; wykonuje
  ją tylko osobna opcja `--enable-log-rotation` (nie obejmuje jej `--yes`) i tylko wtedy, gdy Docker nie ma jeszcze
  pliku konfiguracji. Kontenery aplikacji mają własny limit logów w plikach compose (3 pliki po 10 MB);
- sprawdza, czy nazwa projektu `hydromiara`, nazwy tras Traefika `hydromiara-api` i `hydromiara-web` oraz wybrana
  domena nie są już używane przez inne kontenery; przy kolizji zatrzymuje się, niczego nie zmieniając;
- nie usuwa żadnych kontenerów, obrazów ani wolumenów.

**Plik `.env`** powstaje z `.env.example` z prawami `600`. Istniejące wartości zostają: skrypt dopisuje tylko brakujące,
a zastępuje wyłącznie te podane wprost w opcjach. Przed każdą zmianą zapisuje kopię `.env.backup-DATA-GODZINA`
(prawa `600`). Wartości z `.env` (domena, klucz, model, adres e-mail) nie są wypisywane na ekran; plan podaje same
nazwy zmiennych. Skrypt zapisuje: `DOMAIN`, `TRAEFIK_ENTRYPOINT`, `TRAEFIK_CERTRESOLVER`, `FORWARDED_ALLOW_IPS`,
opcjonalnie `AI_BASE_URL`, `OPENAI_MODEL`, `AI_API_KEY`, a przy własnym Traefiku także `ACME_EMAIL`. Pozostałe
ustawienia (tabela w części „Konfiguracja”) zmienia się ręcznie w `.env` i uruchamia skrypt ponownie.

**Tryby i opcje** (pełna lista: `scripts/deploy.sh --help`):

| Opcja | Działanie |
|---|---|
| `--dry-run` | wykrywa stan serwera i wypisuje plan: co znalazł, co zrobi, czego nie ruszy; niczego nie zmienia |
| `--yes` | bez pytań: wartości z opcji albo z istniejącego `.env`; brak wymaganej wartości kończy się błędem, nie pytaniem |
| `--domain`, `--traefik-entrypoint`, `--traefik-certresolver`, `--acme-email` | wartości kroków 2 i 3 |
| `--ai-base-url`, `--ai-model`, `--ai-key-file`, `--no-ai` | krok 4; klucz można też podać w zmiennej środowiskowej `AI_API_KEY` (nigdy jako opcję, bo opcje widać na liście procesów) |
| `--skip-dns-check` | pomija porównanie rekordu DNS z adresami serwera (np. serwer za translacją adresów) |
| `--enable-log-rotation` | zapisuje rotację logów w konfiguracji Dockera i restartuje go (przerwa we wszystkich kontenerach) |

Przykład bez pytań: `scripts/deploy.sh --yes --domain hydromiara.example.org --no-ai`.

**Pliki wskaźnika suszy.** Usługa czyta je z katalogu `EDO_DATA_PATH` (domyślnie `./data/edo`, montowany tylko do
odczytu); skrypt tworzy katalog, sprawdza, czy użytkownik kontenera (uid 10001) może go czytać, i podaje liczbę
znalezionych plików. Archiwa roczne są w repozytorium w `deploy/edo-archives/` (stan i sposób aktualizacji:
`deploy/edo-archives/README.md`); gdy katalog danych jest pusty, skrypt rozpakowuje je sam (wymaga `python3`).
Ręcznie robi to polecenie `python3 scripts/unpack_drought_files.py deploy/edo-archives` (restart nie jest potrzebny).
Bez tych plików wdrożenie działa, a raport podaje brak tła suszowego jako Ograniczenie.

**Jak działa po wdrożeniu.** Ruch dla domeny trafia do usługi `web`, a ze ścieżką `/api` do usługi `api`; raporty są
zapisywane w wolumenie `reports`. Szyfrowanie (TLS) i przekierowanie na HTTPS zapewnia Traefik.

**Sprawdzenie:** `docker compose ps` (usługa `api` w stanie `healthy`), `curl -fsS https://DOMENA/api/health`
(odpowiedź `{"status":"ok"}`), `docker compose logs --tail 50 api`.

**Aktualizacja do nowej wersji:** `git pull`, potem `scripts/deploy.sh --yes` (wartości z `.env`; obraz jest budowany
od nowa, raporty w wolumenie zostają).

**Wycofanie:** `docker compose down` w katalogu repozytorium zatrzymuje i usuwa tylko kontenery aplikacji; inne usługi,
Traefik, sieć `proxy`, wolumen z raportami i plik `.env` zostają. Wolumen z raportami usuwa dopiero
`docker compose down --volumes`. Własnego Traefika (uruchomionego przez skrypt) zatrzymuje
`docker compose -f deploy/traefik/docker-compose.yml --env-file .env down`.

**Testy skryptu** (bez sieci, bez Dockera i bez uprawnień roota; polecenia systemowe zastąpione atrapami):
`scripts/deploy/tests/run.sh`. Kontrola składni: `shellcheck -x scripts/deploy.sh scripts/deploy/tests/run.sh`.

Nie sprawdzono (do sprawdzenia przez człowieka na czystej maszynie wirtualnej z systemem Debian albo Ubuntu
i z domeną): instalacji Dockera przez skrypt, uruchomienia własnego Traefika z wystawieniem certyfikatu
Let's Encrypt oraz pełnego przebiegu pod domeną. Nagłówka HSTS skrypt nie ustawia (należy do konfiguracji Traefika).

### Konfiguracja

Ustawienia wdrożenia są w pliku `.env` (wzór: `.env.example`); usługa `api` dostaje je jako zmienne środowiskowe.

| Zmienna | Wartość domyślna | Znaczenie |
|---|---|---|
| `DOMAIN`, `TRAEFIK_ENTRYPOINT`, `TRAEFIK_CERTRESOLVER` | brak (wymagane) | nazwa hosta oraz nazwy punktu wejścia HTTPS i resolvera certyfikatów Traefika |
| `ACME_EMAIL` | brak | adres konta Let's Encrypt; potrzebny tylko wtedy, gdy Traefika uruchamia skrypt wdrożenia (`deploy/traefik/docker-compose.yml`); dana osobowa, tylko w `.env` |
| `EDO_DATA_PATH` | `./data/edo` | katalog serwera z rozpakowanymi plikami wskaźnika suszy |
| `WATER_DATA_PATH` | `/data/water` (w kontenerze) | katalog z kopią plików klas wód BDOT10k (`OT_SWRM_L.parquet`, `OT_SWRS_L.parquet`, `OT_SWKN_L.parquet`, `OT_PTWP_A.parquet`); używany jako zamiennik odczytu na żywo tylko wtedy, gdy są w nim wszystkie cztery pliki |
| `REPORTS_DB_PATH` | `/data/reports/reports.sqlite3` | plik bazy raportów (w kontenerze: wolumen `reports`); przy uruchomieniu bez Dockera trzeba ją podać |
| `SATELLITE_PRIMARY` | `planetary-computer` | usługa danych satelitarnych pytana jako pierwsza: `planetary-computer` albo `earth-search` |
| `SATELLITE_SECONDARY` | `earth-search` | usługa zapasowa; `none` wyłącza przełączanie |
| `SATELLITE_FALLBACK_AFTER_S` | `4` | po tylu sekundach bez pierwszego odczytu z usługi podstawowej analiza przechodzi na zapasową |
| `AI_API_KEY` | brak | klucz usługi modelu językowego (sekret); bez klucza albo modelu podsumowanie raportu pochodzi z szablonu |
| `OPENAI_MODEL` | brak | nazwa modelu w usłudze; nie ma wartości domyślnej |
| `AI_BASE_URL` | `https://api.openai.com/v1` | adres bazowy usługi zgodnej z OpenAI Chat Completions; tylko `https` (wyjątek: `http` dla tej samej maszyny) |
| `AI_TIMEOUT_S` | `12` | najdłuższe oczekiwanie na model w sekundach; skracane do czasu, który został z budżetu analizy |
| `AI_REASONING_EFFORT` | brak | opcjonalne pole `reasoning_effort` zapytania (`none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`) dla modeli, które je obsługują; puste = niewysyłane |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | adresy (albo podsieci), od których usługa przyjmuje nagłówek `X-Forwarded-For`; wdrożenie podaje tu adres Traefika |
| `RATE_LIMIT_ENABLED` | `1` | `0` wyłącza wszystkie limity zapytań na adres |
| `RATE_LIMIT_ANALYSIS_PER_MINUTE`, `RATE_LIMIT_ANALYSIS_PER_HOUR` | `6`, `50` | starty analiz z jednego adresu (także analiz na Okres krytyczny); `0` wyłącza dany limit |
| `RATE_LIMIT_DERIVE_PER_MINUTE` | `10` | raporty pochodne z jednego adresu na minutę |
| `RATE_LIMIT_LOOKUP_PER_MINUTE` | `40` | wyszukiwania działek z jednego adresu na minutę |
| `RATE_LIMIT_SIMULATION_PER_MINUTE` | `30` | zapytania Symulacji z jednego adresu na minutę |
| `RATE_LIMIT_STATUS_PER_MINUTE` | `600` | zapytania o postęp analizy z jednego adresu na minutę |
| `RATE_LIMIT_OTHER_PER_MINUTE` | `300` | pozostałe zapytania z jednego adresu na minutę |
| `MAX_CONCURRENT_ANALYSES` | `4` | analizy trwające jednocześnie w całej usłudze; `0` wyłącza limit |

### Dane satelitarne: dwie wymienne usługi

- **Decyzja projektu:** podstawowa jest Planetary Computer, zapasowa Earth Search. Obie udostępniają to samo archiwum
  Sentinel-2 L2A i są wymienne: zamiana kolejności wymaga tylko zmiany dwóch zmiennych, bez zmian w kodzie.
  Dla tych samych dat odczyty NDVI i NDMI z obu usług różnią się o ok. 0,01–0,02 (inna wersja przetworzenia
  lub inny kafel tej samej sceny).
- **Przełączenie:** gdy usługa podstawowa zgłosi błąd albo w ciągu `SATELLITE_FALLBACK_AFTER_S` sekund nie dostarczy
  żadnego odczytu, jej praca jest porzucana, a zapytanie trafia do usługi zapasowej z pozostałym czasem
  (cały etap ma limit 12 s). Usługa, która odpowiedziała, że nie ma czystych scen, nie jest zastępowana.
  W danych źródłowych raportu zapisana jest usługa, z której pochodzi odczyt.
- **Skąd kolejność:** pomiar z serwera docelowego (21.11.2026, `scripts/probes/satellite_probe.py`): odczyt 16 scen
  po 5 pasm trwał 1,2 s z Planetary Computer i 5,5 s z Earth Search; archiwum Planetary Computer sięga lipca 2015 r.,
  Earth Search listopada 2016 r.
- **Obecnie używany jest dostęp bezpłatny** do obu usług: bez konta, bez klucza, bez gwarancji dostępności
  i z limitami zapytań, których dostawcy nie podają liczbowo. To wystarcza dla prototypu.
- **Przed wdrożeniem produkcyjnym trzeba przejść na płatny plan** z gwarancją dostępności i znanymi limitami
  (u dostawcy usługi podstawowej, a najlepiej obu) i dodać w adapterze przekazywanie klucza dostępu;
  obecna wersja klucza nie obsługuje. Do tego czasu ochroną przed niedostępnością jest wyłącznie usługa zapasowa.

### Narzędzia do sprawdzania wyników i czasów

Narzędzia do sprawdzania wyników i czasów (katalog `scripts/`, wymagają sieci): `scripts/backtest.py` uruchamia
zwykłą analizę dla każdego wiersza pliku CSV (`parcel_id,crop_id,analysis_date`, opcjonalnie `label,region`; wzór
formatu: `scripts/examples/input_format_example.csv`) i zapisuje tabelę: oba werdykty z Pewnością oceny, klasę
wskaźnika CDI i wynik Sprawdzenia zgodności, stwierdzone Przyczyny, źródła z danymi i bez, czasy.
`scripts/measure_sources.py` dla tej samej listy mierzy czas każdego źródła osobno i w całej analizie, w kilku
powtórzeniach, i podaje odsetek odpowiedzi w limicie czasu oraz minimum, medianę, 90. percentyl i maksimum.
Oba narzędzia używają kodu aplikacji i żywych źródeł, piszą plik CSV wiersz po wierszu (przerwane uruchomienie
można wznowić tym samym poleceniem) i na koniec wypisują tabelę Markdown. Domyślne tempo (jedna analiza naraz,
13 s odstępu, najwyżej 50 na godzinę i 100 na dobę) mieści się w limitach bezpłatnych usług. Uruchomienie z katalogu
głównego: `EDO_DATA_PATH=./data/edo backend/.venv/bin/python scripts/backtest.py scripts/examples/input_format_example.csv`;
opis opcji, uruchomienia w kontenerze usługi i przez adres działającej usługi (`--base-url`): `--help` obu narzędzi.
Uruchomione w swoim procesie narzędzia nie podlegają limitom zapytań usługi; przez `--base-url` mieszczą się
w limitach domyślnych przy domyślnym tempie (odpytywanie postępu co 0,25 s to 240 zapytań na minutę przy limicie 600).

Programy pomiarowe źródeł danych (czas i dostępność z danej maszyny) opisuje `scripts/probes/README.md`.

## 2. Opis podstawowych funkcjonalności

Rolnik wskazuje Działkę, wybiera Uprawę z listy i Datę analizy (domyślnie dzień bieżący; może być historyczna).
Aplikacja pobiera dane, liczy bilans wodny i zapisuje Raport pod własnym losowym adresem, bez konta użytkownika.

- **Wskazanie Działki** na trzy sposoby: pełny Identyfikator działki, Numer działki z nazwą obrębu (gdy pasuje
  wiele Działek, wybiera użytkownik) albo punkt na mapie. Adres nie jest sposobem wskazania.
- **Analiza w tle z widocznym postępem**: stan każdego źródła danych osobno; Raport powstaje także wtedy, gdy nie
  odpowie dowolne źródło poza działką i pogodą.
- **Dwa osobne werdykty**, każdy z własnym Stopniem niedoboru (w normie, lekki niedobór, wyraźny niedobór, silny
  niedobór) i własną Pewnością oceny: Bieżąca sytuacja wodna (stan na Datę analizy) i Podatność wieloletnia
  (w ilu z 10 lat Okna wieloletniego tej Uprawie brakowałoby wody).
- **Przyczyny niedoboru** (cztery, każda ze wskaźnikiem, progiem i wartością dla Działki) oraz **Rekomendacje**
  z zamkniętego katalogu, każda z regułą, wartościami, które ją uruchomiły, i źródłem. Bez stwierdzonej Przyczyny
  Raport nie zawiera Rekomendacji i mówi to wprost.
- **Nawadnianie**: zasadność, przedział w mm i m³/ha oraz termin słownie, wyłącznie ze stanu na Datę analizy, bez
  prognozy pogody, sformułowane warunkowo.
- **Data poza Sezonem uprawy**: Raport opisuje miniony sezon i Zapas wody w glebie; przejście „Pokaż okres
  największego zapotrzebowania na wodę” uruchamia zwykłą analizę na środek ostatniego Okresu krytycznego.
- **Historia upraw** (opcjonalna, w trakcie analizy albo później jako raport pochodny z tych samych danych)
  dokłada Przebieg historyczny rok po roku; werdyktów nie zmienia.
- **Symulacja**: Ranking upraw najmniej narażonych na niedobór wody na tej Działce i porównanie bieżącej Uprawy
  z jedną wybraną, rok po roku, tą samą miarą co w Raporcie.
- **Sprawdzenie zgodności** w każdym Raporcie: własny werdykt obok niezależnego wskaźnika suszy i odczytu satelitarnego.
- **Ograniczenia raportu** podane wprost: stałe (Raport nie jest urzędowym stwierdzeniem suszy rolniczej, nie ocenia
  nadmiaru wody, nie korzysta z prognozy pogody, publiczne dane o rowach są niekompletne, pogoda pochodzi z modelu
  o siatce około 9 km, który podaje przeciętnie więcej opadu niż deszczomierze) i wynikające z danych tej analizy.
- **Źródła i ślad decyzyjny**: Raport wymienia każde źródło z licencją, trybem pobrania, datą danych i czasem
  odczytu oraz każdą regułę z wartościami, które o niej zdecydowały.
- **Krótkie podsumowanie** Raportu: z szablonu albo, gdy skonfigurowano model językowy, zredagowane przez model
  i sprawdzone (punkt 6).

Trasy interfejsu (wszystkie pod `/api`, odpowiedzi JSON, błędy w postaci `{code, message}` z tekstem po polsku):

| Metoda i ścieżka | Cel |
|---|---|
| `GET /health` | stan usługi |
| `GET /crops`, `GET /examples` | zamknięta lista Upraw z katalogu (21 Upraw i Pole bez uprawy; Sezon uprawy, Okres krytyczny, znacznik kafla) oraz Przykłady (obecnie dane przykładowe, patrz punkt 8) |
| `GET /parcels/search?q=`, `GET /parcels/at?lon=&lat=`, `GET /parcels/{parcel_id}` | wyszukanie Działki, Działka w punkcie mapy, geometria Działki |
| `POST /analyses` | start analizy: `{parcel_id, crop_id, analysis_date}`, odpowiedź `202 {report_id}` od razu |
| `GET /analyses/{report_id}/status` | postęp analizy i stan każdego źródła |
| `PUT /analyses/{report_id}/crop-history` | Historia upraw podana w trakcie analizy |
| `GET /reports/{report_id}` | gotowy Raport (`425`, gdy jeszcze powstaje) |
| `POST /reports/{report_id}/derive` | nowy Raport z tych samych danych źródłowych i podanej Historii upraw |
| `POST /reports/{report_id}/critical-period` | analiza na środek ostatniego Okresu krytycznego |
| `GET /reports/{report_id}/simulation/ranking`, `.../simulation/compare?crop_id=` | Symulacja |

Raport przykładowy `/api/reports/demo` i trasy wywołane dla niego odpowiadają danymi przykładowymi (atrapą).

**Strona dla rolnika** (usługa `web`) prowadzi przez trzy etapy: Działka → Analiza → Raport.

- **Start.** Jedno pole przyjmuje identyfikator działki, numer działki z nazwą obrębu, adres albo numer TERYT
  obrębu, gminy, powiatu lub województwa. Adres i numer TERYT tylko przesuwają i przybliżają mapę (ortofotomapa); działkę wybiera kliknięcie na mapie, po którym strona od razu rysuje jej obrys.
  Wybór można zmieniać dowolnie wiele razy przed uruchomieniem analizy. Uprawę wybiera się kaflem albo z listy,
  Datę analizy z ostatnich 10 lat. Przycisk „Demo” wypełnia formularz gotowym Przykładem.
  Przycisk „O systemie” otwiera okno z krótkim opisem działania, listą źródeł danych (co z każdego jest brane
  i do czego służy), źródłami naukowymi i możliwościami rozwoju.
- **Analiza w toku.** Stan każdego źródła danych (czeka, sprawdzamy, gotowe, brak danych) i nieobowiązkowe pytanie
  o Historię upraw; Raport otwiera się sam.
- **Raport.** Podsumowanie, dwie oceny ze skalą i Pewnością, kafle stwierdzonych przyczyn ze wskaźnikiem, po
  rozwinięciu ścieżka Przyczyna → Zalecenia → Efekt ze szkicem działki (kierunek spływu, wody, Miejsce zatrzymania
  wody), nawadnianie oraz „Dodatkowe informacje”: Ograniczenia, źródła danych z datami i licencjami, Sprawdzenie
  zgodności i ślad decyzji. Raport ma własny adres, drukuje się w całości i zapisuje do PDF przez okno druku
  przeglądarki.
- **Historia upraw i Symulacja** otwierają się z Raportu; zapisanie Historii tworzy nowy Raport pod nowym adresem.

Do uzupełnienia przed zgłoszeniem: sześć Przykładów podpowiadanych w aplikacji (dziś dane zastępcze).

## 3. Skrócony opis architektury rozwiązania

```
przeglądarka ── HTTPS ──> Traefik ──┬─> web  (strona dla rolnika)
                                    └─> api  (FastAPI, jeden proces)  ──> usługi danych (na żywo)
                                              │                       ──> pliki wskaźnika suszy (lokalnie)
                                              └─> SQLite w wolumenie: raporty z danymi źródłowymi
```

Jedna domena: ścieżka `/api` trafia do usługi `api`, reszta do `web`, więc przeglądarka nie potrzebuje dostępu
między domenami (CORS nie jest otwarty). Kod usługi `api` (`backend/app/`):

| Katalog | Odpowiedzialność |
|---|---|
| `api/` | trasy, sprawdzanie danych wejściowych, limity zapytań, nagłówki odpowiedzi |
| `contracts/` | modele żądań i odpowiedzi, struktura danych źródłowych i Raportu |
| `sources/` | adaptery źródeł: tylko pobierają i normalizują dane; Łańcuch zamienników (źródło podstawowe, zamiennik, brak danych) |
| `engine/` | czyste funkcje: bilans wodny, werdykty, Przyczyny, reguły Rekomendacji, nawadnianie, Pewność oceny, Ograniczenia, Sprawdzenie zgodności, Symulacja; bez sieci, zegara i bazy |
| `catalog/` | zamknięta lista Upraw z parametrami i katalog Rekomendacji z szablonami tekstów (dane, nie kod) |
| `orchestrator/` | analiza w tle: równoległe pobieranie z limitami czasu, postęp, złożenie Raportu |
| `storage/` | SQLite: Raport, pełne dane źródłowe, Historia upraw; usuwanie po czasie |
| `summary/` | podsumowanie Raportu z szablonu albo z modelu językowego, z kontrolą odpowiedzi |

Przebieg analizy. `POST /api/analyses` zwraca identyfikator od razu, a praca biegnie w tle: najpierw działka
(usługa ULDK), potem równolegle pogoda, gleba, ukształtowanie terenu, wody w otoczeniu działki i obserwacje
satelitarne oraz odczyt tła suszowego z plików lokalnych; silnik liczy bilans wodny i resztę Raportu; Raport jest zapisywany razem
z wszystkimi pobranymi danymi źródłowymi. Pojemność wodna gleby w bilansie pochodzi z Łańcucha zamienników:
kategoria podatności gleby na suszę z mapy IUNG-PIB, potem kategoria oszacowana z uziarnienia (SoilGrids), na końcu
wartość zastępcza; każde zejście w dół Raport podaje jako Ograniczenie i obniża Pewność oceny.
Bez działki i pogody Raport nie powstaje; każde inne źródło, które nie odpowie, zgłosi błąd albo przekroczy swój
limit czasu, jest w Raporcie i w postępie oznaczone jako brak, a analiza biegnie dalej.

Limity czasu (`backend/app/orchestrator/params.py`): całość 30 s, z czego 3 s rezerwy na obliczenia i zapis;
pogoda 12 s, gleba 13 s (mapa kategorii 5 s, mapy uziarnienia 8 s), teren 17 s (po 8 s na każde z dwóch ogniw i sekunda zapasu), satelita 13 s (limit własny adaptera 12 s), tło suszowe 5 s; żadne źródło poza pogodą nie czeka dłużej niż
do sekundy przed końcem czasu na pobieranie. Wody mają limit 17 s (12 s odczyt na żywo, 4 s kopia lokalna i sekunda zapasu).
Tło suszowe nie ma własnej pozycji w postępie analizy (lista jego
pozycji jest stała); jest na liście źródeł Raportu.

Wynik liczy deterministyczny kod: oba werdykty, Przyczyny niedoboru, wybór Rekomendacji, wszystkie liczby
i Ograniczenia. Teksty Raportu pochodzą z szablonów przypisanych do reguł, więc Raport jest kompletny bez modelu
językowego; model może tylko zredagować krótkie podsumowanie z gotowego Raportu.

Przechowywanie. Raporty są w jednym pliku SQLite; jego ścieżkę podaje zmienna środowiskowa `REPORTS_DB_PATH`
(domyślnie `/data/reports/reports.sqlite3`, czyli wolumen `reports` kontenera). Raport ma losowy adres, nie zmienia
się po zapisaniu i jest usuwany po 30 dniach (wartość robocza). Ponowne otwarcie adresu niczego nie liczy od nowa;
Symulacja i raport pochodny korzystają z danych zapisanych z Raportem i niczego nie pobierają. Usługa działa
w jednym procesie: analiza przerwana ponownym uruchomieniem usługi kończy się stanem `failed` i trzeba ją
uruchomić ponownie.

Opis metody (bilans, werdykty, Pewność oceny, Sprawdzenie zgodności, Przyczyny, teren, sezon, Rekomendacje,
nawadnianie, Historia upraw, Symulacja): [docs/metoda.md](docs/metoda.md).

**Wody w otoczeniu działki** (`backend/app/sources/hydro*.py`, parametry w `hydro_params.py`). Łańcuch zamienników:
odczyt na żywo plików klas obiektów BDOT10k (rów melioracyjny, rzeka i strumień, kanał, woda powierzchniowa) →
kopia tych samych plików w katalogu `WATER_DATA_PATH` → brak danych. Każdy plik obejmuje cały kraj (159, 201, 4
i 199 MB), dlatego usługa czyta przez zapytania HTTP o zakres bajtów tylko grupy wierszy powiatu, w którym leży
działka (około 15 MB i 60 zapytań na analizę), cztery klasy po kolei i jednym połączeniem naraz, bo serwer zrywa
połączenia równoległe. Zostają obiekty do 500 m od granicy działki, przycięte do tego otoczenia i zapisane
w EPSG:4326 z rodzajem `ditch`, `canal`, `watercourse` albo `water_body`. Limit odczytu na żywo to 12 s
(zmierzone 6–8 s). Ogniwo „kopia lokalna” wchodzi do łańcucha tylko wtedy, gdy w katalogu są wszystkie cztery
pliki `<klasa>.parquet`; pobieranie i odświeżanie kopii nie należy do adaptera. Na zewnątrz nie wychodzi nic
o działce: zapytania wskazują tylko publiczny plik i zakres bajtów, z którego można wywnioskować najwyżej powiat.
Z danych o wodach silnik wyznacza (`backend/app/engine/water_analysis.py`) najbliższy rów lub kanał, ciek
i zbiornik: odległość od granicy działki, stronę działki i to, czy leży po stronie, w którą opada teren.
Rekomendacja dotycząca rowu powstaje tylko, gdy rów jest w danych; jej Miejsce zatrzymania wody
(`map.retention_sites`) to odcinek tego rowu najbliższy działce, bez wymiarów i parametrów budowli.

## 4. Opis wykorzystanych źródeł i zakresów danych

Jedna tabela służy punktom 4, 5 i 7: kolumna „Tryb” i „Data danych / odczytu” to punkt 5, kolumna „Warunki
wykorzystania” to punkt 7. Na zewnątrz wysyłane są tylko współrzędne, Identyfikator działki i zakres dat.

| Dane | Źródło | Tryb | Data danych / odczytu | Warunki wykorzystania |
|---|---|---|---|---|
| Działki ewidencyjne: identyfikator, położenie administracyjne, geometria | Główny Urząd Geodezji i Kartografii (GUGiK), Usługa Lokalizacji Działek Katastralnych (ULDK), `https://uldk.gugik.gov.pl/` | na żywo | stan rejestru w chwili analizy; czas odczytu zapisany w raporcie (`sources[].fetched_at`) | bezpłatnie, bez rejestracji; wymagane podanie źródła; limit zapytań na adres IP |
| Pogoda dzienna do Daty analizy: suma opadu, ewapotranspiracja wskaźnikowa ET0 (FAO-56) | Open-Meteo, archiwum pogodowe (reanaliza ERA5 / ECMWF IFS), `https://archive-api.open-meteo.com/v1/archive` | na żywo | wartości dzienne od 1 stycznia roku o 10 lat wcześniejszego niż Data analizy (z zapasem 120 dni na rozruch bilansu) do Daty analizy, a gdy Data analizy jest dniem bieżącym, do dnia poprzedniego (dzień bieżący jeszcze trwa, a archiwum podaje go jako wynik modelu na resztę doby); czas odczytu zapisany w raporcie | dane na licencji CC BY 4.0, wymagane podanie źródła z odnośnikiem [Weather data by Open-Meteo.com](https://open-meteo.com/); bezpłatny dostęp bez klucza tylko do zastosowań niekomercyjnych; limit 600 zapytań na minutę, 5000 na godzinę i 10 000 na dobę na adres IP; limity liczone kosztem zapytania, nie liczbą połączeń: jedna analiza to ok. 59 jednostek, czyli ok. 10 analiz na minutę, 85 na godzinę i 170 na dobę z jednego adresu IP; po wyczerpaniu limitu archiwum odmawia (`429`) i analiza kończy się bez Raportu z osobnym komunikatem |
| Tło suszowe: klasa wskaźnika Combined Drought Indicator (CDI) w komórce siatki działki, co dekadę, od 2016 r. | European Drought Observatory (EDO), Komisja Europejska, Wspólne Centrum Badawcze (JRC); © Unia Europejska, 1995–2026; `https://drought.emergency.copernicus.eu/data/Drought_Observatories_datasets/` (katalog `EDO_Combined_Drought_Indicator`) | plik lokalny: archiwa roczne rozpakowane do `EDO_DATA_PATH` poleceniem `python3 scripts/unpack_drought_files.py KATALOG_ARCHIWÓW`; stan plików na 21.11.2026, dekady od 01.01.2016 do 01.11.2026 | pliki pobrane wcześniej: stan na 21.11.2026, dekady od 01.01.2016 do 01.11.2026; raport podaje dekadę użytą w Sprawdzeniu zgodności | CC BY 4.0; wymagane podanie źródła i zaznaczenie zmian (pliki testowe w `backend/tests/fixtures/edo/` to wycinki 3 × 3 komórki bez metadanych) |
| Ukształtowanie terenu, źródło podstawowe: wysokości punktów w siatce co 5 m w prostokącie otaczającym działkę powiększonym o 30 m (najwyżej 4000 punktów; większa działka dostaje rzadszą siatkę) | Główny Urząd Geodezji i Kartografii (GUGiK), numeryczny model terenu w siatce 1 m z lotniczego skaningu laserowego, odczytywany usługą wysokości punktów `https://services.gugik.gov.pl/nmt/` (zapytanie `GetHByPointList`, układ PL-1992); na zewnątrz wysyłane są tylko współrzędne punktów siatki | na żywo | data nalotu nie jest podawana przez usługę; czas odczytu zapisany w raporcie | dane numerycznego modelu terenu są według opisu GUGiK (geoportal.gov.pl, „Numeryczny model terenu”) dostępne bezpłatnie i możliwe do dowolnego wykorzystania; bez rejestracji; strona usługi nie podaje limitu zapytań |
| Ukształtowanie terenu, zamiennik (gdy źródło podstawowe nie odpowie w 8 s albo poda wysokość dla mniej niż 90% punktów działki): siatka wysokości ok. 30 m wokół działki | Copernicus DEM GLO-30 (model pokrycia terenu z misji TanDEM-X, pomiary z lat 2011–2015; wysokości obejmują budynki i roślinność), pliki z `https://registry.opendata.aws/copernicus-dem/`, arkusz wyszukiwany w katalogu Earth Search (`https://earth-search.aws.element84.com/v1`, kolekcja `cop-dem-glo-30`) | na żywo | pomiary z lat 2011–2015; czas odczytu zapisany w raporcie | bezpłatnie dla każdego na warunkach licencji Copernicus DEM (GLO-30 Public), bez rejestracji; wymagane podanie źródła i informacji o prawach autorskich |
| Parametry wodne Upraw: współczynniki Kc, głębokość korzeni, dopuszczalne wyczerpanie wody w glebie (p), współczynnik reakcji plonu Ky | Allen R.G., Pereira L.S., Raes D., Smith M. (1998), „Crop evapotranspiration: guidelines for computing crop water requirements”, FAO Irrigation and Drainage Paper 56, tabele 12, 22 i 24; długości faz wzrostu kukurydzy, ziemniaka, buraków i warzyw z tabeli 11; `https://www.fao.org/4/x0490e/x0490e00.htm` | wartości wpisane w kodzie (`backend/app/catalog/crop_data*.py`), każda ze wskazaniem tabeli i wiersza; wartości przyjęte przez analogię albo roboczo mają tam podany powód | publikacja z 1998 r., odczyt 21.11.2026; wartości wpisane w kodzie, nie są pobierane | © FAO 1998; przytoczone pojedyncze wartości liczbowe z podaniem źródła, bez kopiowania tekstu i tabel |
| Terminy siewu, faz wzrostu i zbioru Upraw w Polsce (Sezon uprawy i daty faz krzywej Kc) | Centralny Ośrodek Badania Odmian Roślin Uprawnych (COBORU), „Wyniki porejestrowych doświadczeń odmianowych”, tabele dat siewu, zbioru i faz rozwojowych, `https://coboru.gov.pl/Publikacje_COBORU/Wyniki_PDO/`; rośliny rolnicze: średnia z lat zbioru 2018–2022, 2024 i 2025; warzywa: lata 2021–2025 (cebula, kapusta, burak ćwikłowy: tylko 2025) | średnie policzone z opublikowanych dat i wpisane w kodzie (`backend/app/catalog/crop_data*.py`) | wydania z lat 2019–2025, odczyt 21.11.2026 | publikacje jednostki państwowej udostępnione bezpłatnie; w plikach nie ma noty licencyjnej; użyte średnie własne z opublikowanych dat, z podaniem źródła |
| Okres krytyczny każdej Uprawy (okres największego zapotrzebowania na wodę) | Centrum Doradztwa Rolniczego (2025), e-poradnik „Melioracje, retencja i gospodarka wodna w rolnictwie”, część IV, rozdz. 3 i 4 (materiał organizatora) | wartości wpisane w kodzie (`backend/app/catalog/crop_data*.py`) ze wskazaniem strony lub tabeli | publikacja z 2025 r. | materiał sfinansowany ze środków publicznych; przytoczone terminy z podaniem źródła |
| Grupa Uprawy w monitoringu suszy rolniczej (do opisu przyczyn; progów jeszcze nie używamy) | IUNG-PIB, System Monitoringu Suszy Rolniczej, `https://susza.iung.pulawy.pl/progi/` | nazwa grupy wpisana w kodzie przy Uprawie | odczyt 21.11.2026 | treść rozporządzenia ministra (akt urzędowy) opublikowana przez IUNG-PIB; podane źródło |
| Gleba, źródło podstawowe: kategoria podatności gleby na suszę (I–IV) w siatce do 25 punktów wewnątrz obrysu działki; z udziałów kategorii pojemność wodna (110, 149, 186, 220 mm na metr gleby, wartości robocze wewnątrz przedziałów IUNG-PIB) | Instytut Uprawy Nawożenia i Gleboznawstwa – Państwowy Instytut Badawczy (IUNG-PIB), mapa kategorii podatności gleb na suszę Systemu Monitoringu Suszy Rolniczej (siatka 5 m, na podstawie mapy glebowo-rolniczej), usługa mapowa `https://sgeo.iung.pl/geoserver/ows`, warstwa `Susza:katgl_landuse2024` | na żywo | mapa statyczna, bez daty obserwacji; czas odczytu zapisany w raporcie | usługa publiczna i bezpłatna; warunków ponownego wykorzystania IUNG-PIB nie opublikował (przed wdrożeniem pełnoskalowym trzeba je uzyskać od IUNG-PIB); podajemy źródło; limitów zapytań nie opublikowano |
| Gleba, zamiennik i kontrola: piasek, pył, ił i węgiel organiczny w warstwach do 100 cm w środku działki; z nich kategoria szacowana wzorem Saxtona i Rawlsa (2006) | ISRIC – World Soil Information, SoilGrids 2.0 (model globalny, siatka 250 m), usługa WCS `https://maps.isric.org/mapserv` | na żywo | mapy statyczne (wersja 2.0), bez daty obserwacji; czas odczytu zapisany w raporcie | CC BY 4.0, wymagane podanie źródła; limitów zapytań dla usługi WCS nie opublikowano |
| Obserwacje satelitarne do Daty analizy: klasyfikacja sceny (SCL) oraz pasma B04, B08, B8A i B11 nad działką; z nich udział czystych pikseli, NDVI (siatka 10 m) i NDMI (siatka 20 m), mediana z czystych pikseli | Copernicus Sentinel-2, poziom L2A (ESA / Komisja Europejska), z dwóch wymiennych usług (kolejność w konfiguracji): podstawowa Microsoft Planetary Computer, `https://planetarycomputer.microsoft.com/api/stac/v1`, kolekcja `sentinel-2-l2a`, pliki pasm (COG) w Azure West Europe, odczyt z bezpłatnym tokenem pobieranym bez konta; zapasowa Earth Search (Element 84), `https://earth-search.aws.element84.com/v1`, kolekcja `sentinel-2-l2a`, pliki pasm (COG) w rejestrze otwartych danych AWS | na żywo | do 6 najnowszych czystych scen z 30 dni przed Datą analizy oraz do 2 czystych scen z 15 dni przed i po tym samym dniu roku w każdym z 5 poprzednich lat, razem najwyżej 16 (archiwum od 11.07.2015 w usłudze podstawowej, od 2.11.2016 w zapasowej); data każdej sceny i czas odczytu zapisane w raporcie | bezpłatny, pełny i otwarty dostęp do danych na warunkach noty prawnej danych Sentinel (`https://sentinel.esa.int/documents/247904/690755/Sentinel_Data_Legal_Notice`); wymagane podanie źródła i zaznaczenie przetworzenia danych; obie usługi obecnie w dostępie bezpłatnym, bez klucza i bez gwarancji dostępności (patrz „Konfiguracja”) |
| Metoda oceny: dzienny bilans wody w strefie korzeniowej, woda łatwo dostępna i współczynnik stresu wodnego Ks, z których powstają Bieżąca sytuacja wodna i Podatność wieloletnia | Allen R.G., Pereira L.S., Raes D., Smith M. (1998), „Crop evapotranspiration: guidelines for computing crop water requirements”, FAO Irrigation and Drainage Paper 56, rozdział 8 (równania 80, 82–86 i 88), tabela 19 | metoda zapisana w kodzie (`backend/app/engine/`); progi i wartości robocze w jednym pliku `backend/app/engine/params.py`, każda bez źródła oznaczona tam jako robocza | publikacja z 1998 r.; metoda zapisana w kodzie, nie jest pobierana | publikacja FAO; równania przytoczone z podaniem źródła |
| Wody w otoczeniu działki (do 500 m od granicy): rowy melioracyjne, kanały, rzeki i strumienie, wody powierzchniowe; rodzaj, nazwa, geometria | Baza Danych Obiektów Topograficznych BDOT10k, Główny Urząd Geodezji i Kartografii (GUGiK); pliki GeoParquet klas `OT_SWRM_L`, `OT_SWRS_L`, `OT_SWKN_L`, `OT_PTWP_A` z `https://opendata.geoportal.gov.pl/bdot10k/schemat2021/GeoParquet/` | na żywo (części plików dla powiatu działki); zamiennik: kopia plików w `WATER_DATA_PATH`, gdy jest na serwerze (wtedy tryb „plik lokalny”) | data ostatniej zmiany plików (`sources[].data_date`); obiekty mogą być starsze niż rok; czas odczytu zapisany w raporcie | bezpłatnie: zbiory obiektów topograficznych są udostępniane bez opłat (Prawo geodezyjne i kartograficzne, art. 40a ust. 2 pkt 1 lit. h); podajemy źródło „BDOT10k, Główny Urząd Geodezji i Kartografii”; osobnego dokumentu licencji dla katalogu plików nie znaleźliśmy: do sprawdzenia przez człowieka przed wdrożeniem pełnoskalowym |

## 5. Wskazanie, które dane są pobierane na bieżąco, a które zostały pobrane lub przetworzone wcześniej, wraz z datami ich pobrania

| Dane | Jak trafiają do analizy | Data |
|---|---|---|
| Działka, pogoda, gleba, ukształtowanie terenu, obserwacje satelitarne | **na bieżąco**, w trakcie każdej analizy, z usług wymienionych w punkcie 4 | czas odczytu każdego źródła jest zapisany w Raporcie (`sources[].fetched_at`) razem z datą danych (`data_date`) |
| Wody w otoczeniu działki (BDOT10k) | **na bieżąco**: części plików klas obiektów dla powiatu działki; gdy odczyt się nie uda, a na serwerze jest kopia plików w `WATER_DATA_PATH`, z tej kopii | data ostatniej zmiany plików i czas odczytu w raporcie (`sources[]`) |
| Tło suszowe (wskaźnik CDI) | **pobrane wcześniej**: archiwa roczne rozpakowane do plików lokalnych, bez przetwarzania wartości | stan plików na 21.11.2026; dekady od 01.01.2016 do 01.11.2026 |
| Parametry Upraw, katalog Rekomendacji, progi i reguły metody | **wpisane w kodzie** ze wskazaniem źródła albo z oznaczeniem wartości roboczej | publikacje wymienione w punkcie 4; stan kodu na dzień zgłoszenia |
| Raport i jego dane źródłowe | **zapisane przez aplikację** przy analizie; Symulacja i raport pochodny liczą z tego zapisu | czas utworzenia Raportu (`meta.created_at`) |

Wynik i Rekomendacje oblicza aplikacja z tych danych przy każdej analizie: nie ma gotowych wyników wpisanych
z góry, a Przykład podpowiadany w aplikacji tylko wypełnia formularz i uruchamia zwykłą analizę na żywo. Wyjątkiem
jest raport przykładowy `/api/reports/demo` (dane przykładowe do budowy strony, patrz punkt 8). Żadne dane nie są
dziś buforowane między analizami; decyzja, co buforować i jak często odświeżać, jest opisana w części „Skalowanie”.

## 6. Wykaz wykorzystanych bibliotek, komponentów, modeli, usług zewnętrznych i narzędzi sztucznej inteligencji

### Biblioteki

Wersje są przypięte w `backend/requirements.txt` i `backend/requirements-dev.txt`.

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
| PyArrow (Apache Arrow) | odczyt grup wierszy plików GeoParquet z danymi o wodach, także zdalnie po zakresach bajtów | Apache-2.0 |

Biblioteki strony dla rolnika (usługa `web`, katalog `frontend/`):

| Biblioteka | Zastosowanie | Licencja |
|---|---|---|
| React, React DOM | interfejs strony | MIT |
| React Router | adresy ekranów (Raport pod własnym adresem) | MIT |
| Leaflet | mapa wyboru działki | BSD-2-Clause |
| Open Sans (paczka `@fontsource/open-sans`) | czcionka, serwowana z własnego serwera | SIL Open Font License 1.1 |
| Vite, `@vitejs/plugin-react` | budowanie strony | MIT |
| TypeScript | sprawdzanie typów przy budowaniu | Apache-2.0 |
| Vitest | testy | MIT |

### Komponenty

| Komponent | Zastosowanie | Licencja |
|---|---|---|
| Python 3.13 (obraz `python:3.13-slim`) | środowisko usługi `api` | PSF License (obraz: pakiety Debiana na własnych licencjach) |
| SQLite (z biblioteki standardowej Pythona) | baza raportów | domena publiczna |
| Docker Engine z Docker Compose | uruchomienie usług | Apache-2.0 |
| Traefik (obraz `traefik:v3`, gdy uruchamia go skrypt wdrożenia) | serwer pośredniczący na serwerze docelowym: TLS, kierowanie ruchu | MIT |
| nginx (obraz `nginx:1.29-alpine`) | usługa `web`: serwuje stronę dla rolnika | BSD-2-Clause |
| Node.js (obraz `node:22-alpine`) | budowanie strony; nie ma go w obrazie końcowym | MIT |
| Swagger UI | strona `/api/docs` z opisem interfejsu; skrypt i styl ładowane przez przeglądarkę z publicznej sieci CDN | Apache-2.0 |

### Usługi zewnętrzne

Usługi danych: ULDK (GUGiK), usługa wysokości punktów GUGiK, archiwum pogodowe Open-Meteo, mapa kategorii podatności gleb na suszę (IUNG-PIB),
SoilGrids (ISRIC, usługa WCS), Copernicus DEM (pliki w rejestrze
otwartych danych AWS, katalog Earth Search), Sentinel-2 przez Microsoft Planetary Computer i Earth Search
(Element 84). Adresy, zakres i warunki: tabela w punkcie 4. Opcjonalnie usługa modelu językowego (niżej).
Żadna z usług danych nie wymaga konta ani klucza.

Strona dla rolnika woła z przeglądarki trzy publiczne usługi GUGiK, wszystkie bez konta i klucza: ortofotomapę jako
podkład mapy (WMTS, `https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMTS/StandardResolution`; usługa podaje
„brak ograniczeń” i odsyła do Regulaminu Geoportalu), Usługę Uniwersalnego Geokodowania do wyszukania adresu
(`https://services.gugik.gov.pl/uug/`) oraz ULDK (`https://uldk.gugik.gov.pl/`) do pokazania na mapie obrębu,
gminy, powiatu albo województwa wskazanego numerem TERYT (warunki ULDK: tabela w punkcie 4). Do geokodera trafia
wyłącznie tekst wpisany w pole działki, i tylko wtedy, gdy nie jest on identyfikatorem ani numerem działki
z obrębem; usługa oczekuje kolejności „miejscowość, ulica numer”, więc adres wpisany inaczej jest pytany także
w tej kolejności. Do ULDK z przeglądarki trafia wyłącznie wpisany numer TERYT. Wynik obu wyszukiwań tylko przesuwa
mapę; działkę i wszystkie dane do oceny pobiera usługa `api`.

Certyfikaty TLS wystawia Let's Encrypt (protokół ACME, obsługiwany przez Traefika): usługa bezpłatna, na warunkach
umowy subskrybenta Let's Encrypt (`https://letsencrypt.org/repository/`); konto zakłada Traefik na adres e-mail
podany przy wdrożeniu, a nazwa domeny trafia do publicznych rejestrów wystawionych certyfikatów. Skrypt wdrożenia
pobiera pakiety Dockera z `https://download.docker.com` (tylko gdy Dockera nie ma na serwerze).

### Modele

Aplikacja nie zawiera modelu uczenia maszynowego i żadnego nie trenuje. Ocena to bilans wodny i reguły. Jedyny
model to opcjonalny model językowy redagujący podsumowanie Raportu (niżej).

### Autorstwo i wykorzystanie AI

Autorem rozwiązania jest zespół. Ludzie ustalają wymagania, podejmują decyzje projektowe, dobierają metody
i źródła danych, przeglądają każdą zmianę i odpowiadają za wynik. Narzędzia AI służą do pisania implementacji
według planu zespołu, pod nadzorem programisty.

Udział AI w każdej zmianie jest zapisany w historii repozytorium, w stopkach commitów: `Authorship` (`mixed`:
praca zespołu i implementacja z udziałem AI; `human`: bez AI), `Implementation` (`agent`: kod napisało narzędzie AI,
programista go przejrzał; `agent+operator`: programista poprawiał ręcznie; `operator`: kod napisał człowiek)
i `Assisted-by` (narzędzie i model). Liczby wyprowadza się z historii:

```bash
git log --format='%(trailers:key=Implementation,valueonly)' | grep -v '^$' | sort | uniq -c
git log --format='%(trailers:key=Assisted-by,valueonly)' | grep -v '^$' | sort | uniq -c
```

Stan gałęzi `main` na 22.11.2026 (przed dołączeniem ostatnich zmian): 55 commitów (29 zmian i 26 scaleń), wszystkie
`Authorship: mixed` i `Implementation: agent`, wszystkie `Assisted-by: Claude Code:claude-fable-5-2` (narzędzie
Claude Code firmy Anthropic).

Do uzupełnienia przed zgłoszeniem: liczby na dzień zgłoszenia (te same polecenia), pełny wykaz narzędzi i modeli AI
użytych przez zespół (także przy stronie dla rolnika, badaniu źródeł i materiałach prezentacyjnych) z zakresem
użycia oraz ich warunki korzystania.

### AI w działaniu aplikacji: podsumowanie raportu

To jedyne miejsce, w którym działająca aplikacja korzysta z AI. Oba werdykty, Przyczyny niedoboru, Rekomendacje,
wszystkie liczby i Ograniczenia raportu wyznacza deterministyczny kod, a teksty raportu pochodzą z szablonów
przypisanych do reguł. Raport jest kompletny bez modelu językowego: pole `summary` zawiera wtedy podsumowanie złożone
z gotowych tekstów raportu (`summary.source = "template"`). To stan domyślny, gdy klucz lub nazwa modelu nie są ustawione.

- **Dostawca i model.** Usługa z interfejsem zgodnym z OpenAI Chat Completions (`POST {AI_BASE_URL}/chat/completions`,
  domyślnie `https://api.openai.com/v1`). Nazwa modelu pochodzi wyłącznie ze zmiennej `OPENAI_MODEL`; kod nie ma
  nazwy domyślnej. Nazwa modelu, który zredagował podsumowanie, jest zapisana w śladzie decyzyjnym raportu
  (`trace`, wpis `summary.source`). Jedno zapytanie na analizę, bez ponowień, bez dodatkowej biblioteki (HTTPX).
- **Co model dostaje.** Wyłącznie wybrane części gotowego raportu: nazwę Uprawy, Datę analizy, zdanie nagłówka,
  notę o Sezonie uprawy, oba werdykty z Pewnością oceny i jej uzasadnieniem, zdanie o Przebiegu historycznym,
  stwierdzone Przyczyny niedoboru z ich Rekomendacjami (grupa, tekst, „Co uzyskasz”), tekst i termin nawadniania,
  wynik i zdanie Sprawdzenia zgodności oraz do trzech Ograniczeń raportu dotyczących werdyktów. Instrukcja dla modelu
  jest stałą w kodzie (`backend/app/summary/prompt.py`), a dane raportu są przekazywane osobno, jako dane.
- **Czego model nie dostaje.** Identyfikatora i Numeru działki, nazw obrębu, gminy, powiatu i województwa, geometrii,
  współrzędnych, mapy, adresu raportu ani danych źródłowych (pogody, gleby, terenu, scen satelitarnych). Tekst raportu,
  w którym wystąpiłaby któraś z tych nazw albo współrzędna, jest pomijany w całości.
- **Czego model nie robi.** Niczego nie liczy i o niczym nie decyduje: nie zmienia werdyktów, nie dodaje liczb, dat ani
  działań, nie uśrednia dwóch werdyktów. Redaguje kilka zdań z tego, co już jest w raporcie.
- **Kontrola odpowiedzi** (`backend/app/summary/check.py`, `numbers.py`). Odpowiedź jest przyjmowana tylko wtedy, gdy:
  ma od 60 do 900 znaków i jest zwykłym tekstem; każda liczba, data, nazwa miesiąca i para „X z Y lat” występuje
  w danych wysłanych do modelu, a liczba nie zmienia jednostki (różnice zapisu nie są błędem: przecinek i kropka
  dziesiętna, `20.06.2023` / `2023-06-20` / „20 czerwca 2023”, `%` i „procent”, `1 790` i `1790`); Stopnie niedoboru,
  grupy Rekomendacji, wynik Sprawdzenia zgodności i słowa nakazujące działanie („warto”, „należy”, „trzeba”…) pojawiają
  się tylko, jeśli są w danych; poziom Pewności oceny jest jednym z podanych w raporcie; nie ma słów, których
  słownik projektu każe unikać (np. „ryzyko”, „porada”, „wilgotność”), a słowo „susza” występuje wyłącznie w stałych
  zwrotach raportu („nie jest urzędowym stwierdzeniem suszy”, „wskaźnik suszy”); gdy werdykty nie mają Stopnia
  niedoboru, odpowiedź mówi to wprost.
- **Granice kontroli.** Kontrola nie wykryje liczby użytej w innym znaczeniu niż w raporcie, liczby zapisanej słownie,
  zmienionego znaku ani zmyślonego działania opisanego bez żadnego z pilnowanych słów. To ryzyko ograniczają:
  instrukcja, krótka forma, mały zakres przekazanych danych oraz to, że pełne Rekomendacje z regułą i wartościami
  stoją w raporcie obok podsumowania. Podsumowanie modelu nie jest powtarzalne między uruchomieniami; raz zapisane
  w raporcie już się nie zmienia.
- **Wyjście awaryjne.** Brak konfiguracji, limit czasu, błąd usługi (np. 401, 429, 5xx), odpowiedź pusta, ucięta,
  nieczytelna albo odrzucona przez kontrolę kończą się podsumowaniem z szablonu; analiza nigdy nie kończy się
  niepowodzeniem z powodu modelu. Powód jest zapisany kodem w `trace` i w logu.
- **Kiedy i jak długo.** Model jest pytany po zbudowaniu raportu, a przed jego zapisem, tylko dla nowej analizy
  (także analizy na Okres krytyczny). Czeka się najwyżej `AI_TIMEOUT_S` sekund i nigdy dłużej, niż zostało z 30 s
  przeznaczonych na analizę (minus 1 s na zapis). Raport pochodny z Historią upraw nie jest nigdzie wysyłany
  i dostaje podsumowanie z szablonu.
- **Klucz.** Tylko w `.env` na serwerze; jest wysyłany wyłącznie w nagłówku zapytania do usługi (po HTTPS) i nie trafia
  do logów, raportu, bazy ani komunikatów błędów. Log zawiera czas wywołania, źródło podsumowania, kod powodu
  i nazwę modelu, bez treści zapytania i odpowiedzi.
- **Warunki korzystania.** Usługa modelu językowego jest płatna według cennika dostawcy i wymaga konta oraz klucza;
  aplikacja działa w pełni bez niej. Przekazane dane przetwarza dostawca na własnych warunkach: przed wdrożeniem
  pełnoskalowym człowiek powinien sprawdzić warunki przetwarzania i przechowywania danych u wybranego dostawcy.

## 7. Wskazanie licencji lub innych warunków korzystania z danych i komponentów

- **Dane i usługi danych**: kolumna „Warunki wykorzystania” tabeli w punkcie 4. Każdy Raport podaje przy swoich
  źródłach nazwę i licencję (`sources[]`).
- **Biblioteki i komponenty**: kolumna „Licencja” tabel w punkcie 6. Wszystkie są na licencjach otwartych.
- **Model językowy**: usługa płatna według cennika dostawcy, wymaga konta i klucza; aplikacja działa w pełni bez
  niej (punkt 6, „Warunki korzystania”).
- **Dane satelitarne**: dziś dostęp bezpłatny bez gwarancji dostępności; przed wdrożeniem produkcyjnym płatny plan
  (punkt 1, „Dane satelitarne: dwie wymienne usługi”).
- **Pogoda**: bezpłatny dostęp do Open-Meteo bez klucza jest przeznaczony wyłącznie do zastosowań niekomercyjnych;
  użycie komercyjne albo większy ruch wymaga płatnego planu.

Wymagane informacje o pochodzeniu danych:

Źródło: Główny Urząd Geodezji i Kartografii (GUGiK), Usługa Lokalizacji Działek Katastralnych (ULDK).

Dane pogodowe: [Weather data by Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0). Zawierają informacje usługi Copernicus Climate Change Service.

Wysokości terenu: Główny Urząd Geodezji i Kartografii (GUGiK), numeryczny model terenu (usługa wysokości punktów, https://services.gugik.gov.pl/nmt/).

Wysokości terenu, źródło zastępcze: produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved. Copernicus Digital Elevation Model (DEM) was accessed on 21.11.2026 from https://registry.opendata.aws/copernicus-dem.

Kategorie podatności gleb na suszę: IUNG-PIB, System Monitoringu Suszy Rolniczej, opracowanie na zlecenie Ministerstwa Rolnictwa i Rozwoju Wsi.

Uziarnienie i węgiel organiczny gleby: ISRIC – World Soil Information, SoilGrids 2.0 (CC BY 4.0); Poggio, L. i in. (2021), SOIL 7, 217–240, doi:10.5194/soil-7-217-2021.

Obserwacje satelitarne: zawiera zmodyfikowane dane Copernicus Sentinel (2015–2026).

### Licencje i warunki usług zewnętrznych: wersja demo i wersja pełnoskalowa

Skrót dwóch instrukcji: [wdrożenie pokazowe (demo)](docs/wdrozenie-pokazowe.md) i
[wdrożenie pełnoskalowe](docs/wdrozenie-pelnoskalowe.md). W każdej jest rozdział o licencjach z adresem strony
warunków i datą odczytu dla każdego stwierdzenia (strony odczytane 21–22.11.2026). Tabela streszcza strony
dostawców i nie jest poradą prawną; „do sprawdzenia” oznacza „do sprawdzenia przez człowieka przed wdrożeniem”.

| Usługa | Wersja demo | Wersja pełnoskalowa |
|---|---|---|
| ULDK (GUGiK), działki | bezpłatnie, bez konta i klucza; 200 zapytań na minutę w godz. 6–18, 40 poza nimi, 10 000 na dobę na adres IP; wymagane podanie źródła | bezpłatnie także w aplikacji komercyjnej, bez umowy; adresy serwerów można bezpłatnie zgłosić do listy zaufanej bez limitów; wymagane podanie źródła |
| Open-Meteo, archiwum pogodowe | bezpłatnie tylko niekomercyjnie, bez klucza; 600 zapytań na minutę, 5000 na godzinę, 10 000 na dobę na adres IP (około 56 analiz na godzinę); dane CC BY 4.0, wymagane podanie źródła | przy użyciu komercyjnym lub większym ruchu płatna subskrypcja z kluczem (archiwum od planu Professional) albo własna instalacja serwera (AGPLv3); aplikacja klucza jeszcze nie obsługuje; cena i kwalifikacja użycia: do sprawdzenia |
| SoilGrids 2.0 (ISRIC), gleba | dane CC BY 4.0, bez konta i klucza; usługa REST w fazie beta, bez gwarancji, 5 zapytań na minutę | ta sama licencja; usługa REST nie nadaje się na podstawę usługi stałej (dostawca zaleca WebDAV lub usługi sieciowe); limit usługi WCS nieopisany |
| European Drought Observatory, wskaźnik CDI (pliki lokalne) | bezpłatny dostęp, bez konta; wymagana nota o źródle (Copernicus Emergency Management Service) | te same warunki; licencja CC BY 4.0 |
| Copernicus DEM GLO-30 (rejestr otwartych danych AWS) | bezpłatnie na warunkach licencji Copernicus DEM, bez konta; wymagana nota o prawach autorskich | te same warunki; limitów nie podano |
| Copernicus Sentinel-2 L2A (dane) | dostęp bezpłatny, pełny i otwarty; wymagana nota o zmodyfikowanych danych Copernicus Sentinel | te same warunki |
| Microsoft Planetary Computer (usługa podstawowa danych satelitarnych) | dostęp anonimowy, bez klucza; limity bez podanych liczb, bez gwarancji; strona warunków nieodczytana: do sprawdzenia | potrzebny dostęp z gwarancją i znanymi limitami oraz obsługa klucza w aplikacji; warunki, klucz subskrypcji i cennik: do sprawdzenia |
| Earth Search (Element 84; usługa zapasowa i katalog arkuszy terenu) | publiczny interfejs bezpłatny w użyciu, bez klucza i bez gwarancji usługi; limity nieopisane | przy użyciu produkcyjnym dostawca odsyła do kontaktu; warunki i cennik: do sprawdzenia |
| Usługa modelu językowego (opcjonalna) | konto, klucz i opłaty według cennika wybranego dostawcy; aplikacja działa w pełni bez niej | jak w demo; umowa, limity i zasady przetwarzania danych u dostawcy: do sprawdzenia |
| Let's Encrypt (certyfikat TLS) | bezpłatnie, konto na adres e-mail administratora; do 50 certyfikatów na domenę w 7 dni | te same warunki |
| Po podłączeniu: BDOT10k (GUGiK), wody | bezpłatnie na podstawie ustawy, bez konta; limity nieopublikowane | kopia lokalna całego kraju; dokument licencji plików: do sprawdzenia |
| Po podłączeniu: usługa wysokości punktów GUGiK (model terenu 1 m) | dane NMT bezpłatne i do dowolnego wykorzystania; bez konta; limity usługi nieopisane | limity i warunki usługi przy stałym ruchu: do sprawdzenia |
| Po podłączeniu: mapa kategorii podatności gleb na suszę (IUNG-PIB) | usługa publiczna i bezpłatna; licencji ani regulaminu nie opublikowano; pojedyncze odczyty z podaniem źródła | wymagane zapytanie do IUNG-PIB o zgodę i warunki ponownego wykorzystania: do sprawdzenia |
| Po podłączeniu: SoilGrids przez usługę WCS (ISRIC) | dane CC BY 4.0, bez konta; limit nieopisany | ta sama licencja; przy stałym ruchu własna kopia map |

Tło suszowe: wygenerowano z użyciem informacji usługi Copernicus Emergency Management Service (2016–2026)
(Generated using Copernicus Emergency Management Service information 2016–2026).

Do uzupełnienia przed zgłoszeniem: licencja kodu rozwiązania.

## 8. Opis znanych ograniczeń technicznych rozwiązania

Zakres danych i katalogów:

- Lista Upraw ma 21 Upraw i Pole bez uprawy; `GET /api/crops` zwraca ją wprost z katalogu, a analiza, Historia
  upraw i Symulacja działają dla każdej pozycji. Jedenaście Upraw ma komplet wartości ze źródeł. Dziesięć jest
  w katalogu oznaczonych jako warunkowe (`conditional`), bo część ich wartości przyjęto przez analogię albo
  roboczo: żyto ozime i pszenżyto ozime (parametry pszenicy ozimej, źródło nie podaje ich osobno), rzepak ozimy
  (początek fazy końcowej; wybór Kc wewnątrz zakresu), łąka lub pastwisko (roślina wieloletnia opisana modelem
  „siew–zbiór”, od kwietnia do września, bez terminów pokosów i wypasu), mieszanka zbożowa jara (wszystko jak
  jęczmień jary i owies) oraz cebula, kapusta głowiasta, burak ćwikłowy, pomidor gruntowy i ogórek gruntowy
  (terminy z kilku stacji doświadczalnych, dla cebuli, kapusty i buraka ćwikłowego z jednego roku; długości faz
  z tabel FAO dla cieplejszego klimatu; jeden wspólny Okres krytyczny warzyw, przycięty do Sezonu uprawy).
  Kontrakt `GET /api/crops` nie ma pola na to oznaczenie, więc strona go nie pokazuje.
- Terminy siewu, faz i zbioru to średnie z doświadczeń odmianowych w całej Polsce; na konkretnym polu mogą
  różnić się o kilkanaście dni zależnie od regionu, odmiany i pogody. Okres krytyczny zbóż przyjęto dla gleb
  średnich (na lekkich zaczyna się około dziesięciu dni wcześniej). Dla kukurydzy, ziemniaka i buraka długości
  faz pochodzą z tabel FAO, nie z obserwacji w Polsce. Ziemniak to odmiany średnio wczesne i średnio późne,
  kapusta to odmiany późne. Współczynniki Kc dotyczą upraw dobrze prowadzonych, o pełnej obsadzie, bez poprawki
  na klimat. Warzywa są zwykle nawadniane; Raport pokazuje, ile wody brakowałoby im bez nawadniania. Sadów,
  krzewów owocowych i truskawek narzędzie nie ocenia. Tych zastrzeżeń Raport nie podaje jeszcze jako
  Ograniczeń przy konkretnej Uprawie.
- Poza Sezonem uprawy i dla Pola bez uprawy parowanie liczone jest stałym współczynnikiem gołej gleby 0,3
  (wartość robocza); dla ozimin jesienią przed siewem i dla łąki zimą to uproszczenie.
- Współczynnik reakcji plonu Ky i grupa monitoringu suszy są w katalogu, ale silnik jeszcze z nich nie korzysta.
- `GET /api/examples` zwraca dane przykładowe, a nie sześć sprawdzonych Przykładów; raport `/api/reports/demo`
  jest atrapą.
- Katalog Rekomendacji zawiera pozycje niezależne od danych o wodach (retencja glebowa, zadrzewienia, trwała okrywa,
  uprawa w poprzek spadku, obserwacja w Okresie krytycznym); pozycja nawadniania jest wzorcowa, bez dawek.
- Dane o wodach: katalog ma jedną wzorcową Rekomendację zależną od wód (rów lub kanał do 20 m od granicy działki);
  pozostałe pozycje zależne od cieków i zbiorników nie są jeszcze wpisane. Odczyt na żywo obejmuje wody z powiatu
  działki, więc obiekt tuż za granicą powiatu może zostać pominięty (Raport podaje to jako Ograniczenie).
  Miejsce zatrzymania wody z analizy terenu (najniższa część działki) nie ma jeszcze geometrii na mapie.
  Kopii danych o wodach usługa sama nie pobiera: bez plików w `WATER_DATA_PATH` łańcuch ma jedno ogniwo.
- Dla Pola bez uprawy żaden werdykt nie dostaje Stopnia niedoboru (nie ma reguły); Raport zapisuje wtedy stopień
  techniczny 0 z etykietą „bez uprawy, nie oceniane” i znacznikiem `details.assessed = false`. Nie ma dla niego Przyczyn,
  Rekomendacji, Historii upraw ani Symulacji.

Wartości robocze. Progi i reguły bez źródła naukowego są w kodzie oznaczone `PROVISIONAL` i zebrane w plikach
parametrów (lista w [docs/metoda.md](docs/metoda.md)): definicja roku z niedoborem (co najmniej 10 dni stresu
w Okresie krytycznym; zbyt czuła, zob. niżej), progi Stopni niedoboru, wartości Upraw warunkowych wymienione wyżej,
współczynnik gołej gleby, progi Przyczyn opadów i potrzeb wodnych uprawy, reguły Pewności oceny i Sprawdzenia zgodności,
dwa progi interpretacji odczytu satelitarnego (3 lata tej samej Uprawy do porównania, NDVI 0,4 w kwietniu dla
Uprawy ozimej),
zasadność i dolna granica nawadniania, czas przechowywania Raportów. Przy progu Kc 1,0 przyczyna „uprawa o dużych
potrzebach wodnych” będzie stwierdzana dla większości Upraw polowych.

Liczba lat z niedoborem jest liczona regułą roboczą „co najmniej 10 dni z brakiem wody w Okresie krytycznym”, która
zawyża tę liczbę (dla wielu Działek daje 9–10 lat na 10). Definicja oparta na względnym niedoborze ewapotranspiracji
została opracowana, ale nie jest włączona, bo jej próg wymaga ponownego dobrania po zmianie katalogu Upraw
i źródła danych o glebie.

Źródła danych:

- **Gleba.** Pojemność wodna pochodzi z kategorii podatności gleby na suszę (mapa IUNG-PIB): to typowa gleba
  w danym miejscu według map glebowo-rolniczych, a nie pomiar na działce (stałe Ograniczenie przy każdej
  kategorii). Wartości 110, 149, 186 i 220 mm na metr są robocze: leżą wewnątrz przedziałów IUNG-PIB, ale nie mają
  własnego źródła; nie ustalono też, czy przedziały IUNG-PIB dotyczą metra gleby, czy profilu 1,5 m (dla Upraw
  z korzeniami płytszymi niż 1 m pojemność strefy może być zawyżona). Działka bez kategorii na mapie (las,
  zabudowa, teren niesklasyfikowany) dostaje kategorię oszacowaną z uziarnienia SoilGrids (model globalny, siatka
  250 m); na 8 działkach testowych szacunek mylił się o jedną kategorię w 2 przypadkach, a progi szacunku
  wyprowadzono z tych samych działek. Gleby organiczne i działki bez danych w obu źródłach (np. w zabudowie) liczą
  na pojemności zastępczej 150 mm/m, z Ograniczeniem i niższą Pewnością oceny. Wzory Saxtona i Rawlsa (2006)
  przepisano z kodu USDA ARS, który je implementuje, nie z samej publikacji. Warunków ponownego wykorzystania
  usługi IUNG-PIB nie opublikowano; żadna z dwóch usług nie podaje limitów zapytań ani gwarancji dostępności.
  Zmierzony czas odczytu gleby (22.11.2026, maszyna deweloperska, 3 działki): 1,2–2,3 s; mapa kategorii odpowiadała
  w każdym odczycie.
- **Pogoda.** Bezpłatny dostęp do archiwum Open-Meteo jest tylko do zastosowań niekomercyjnych, a jego limit
  liczony kosztem zapytania pozwala na około 85 analiz na godzinę i 170 na dobę z adresu serwera. Opad i ET0
  pochodzą z modelu o siatce około 9 km (dla lat do 2016 r. około 25 km), a nie z deszczomierza na Działce;
  w porównaniu z opadami dobowymi ze stacji IMGW model podawał przeciętnie o kilkanaście procent więcej opadu,
  więc rzeczywisty niedobór może być większy. Analiza na dzień bieżący korzysta z pogody do dnia poprzedniego
  (dzień bieżący jeszcze trwa), więc dzisiejszy opad nie jest w niej uwzględniony. Nie wiadomo, czy archiwum
  poprawia później wartości z ostatnich dni: ta sama analiza powtórzona po kilku dniach może dać nieco inne liczby.
  Po wyczerpaniu limitu archiwum odmawia odpowiedzi i analiza nowej Działki kończy się bez Raportu, z komunikatem
  o limicie zapytań.
- **Teren.** Wysokości z modelu terenu GUGiK są odczytywane co 5 m i zaokrąglone do 10 cm, więc na polu prawie
  płaskim (spadek poniżej 0,5%) kierunek spływu jest orientacyjny. Usługa nie podaje limitów ani daty nalotu;
  zdarza się jej odpowiedź z samymi zerami zamiast wysokości, dlatego taka część siatki jest odczytywana
  ponownie, a gdy wysokość ma mniej niż 90% punktów Działki albo usługa nie zdąży w 8 s, analiza przechodzi na
  model 30 m i Raport to podaje. Kierunek spływu to kierunek średniego spadku całej Działki; miejscowo woda może
  płynąć inaczej, a bruzd, kolein i drenów model nie pokazuje. Najniższa część jest wskazywana jako strona
  Działki. Model 30 m (Copernicus DEM) opisuje powierzchnię razem z budynkami i roślinnością; wystarcza do
  średniego spadku i kierunku. Na modelu 30 m Działki wąskie albo mniejsze
  niż około 0,5 ha mają za mało punktów siatki i spadek nie jest wyznaczany. Działka na granicy arkuszy 1° × 1°
  dostaje siatkę tylko z arkusza swojego środka.
- **Tło suszowe.** Wskaźnik CDI jest dostępny od 2016 r. i ukazuje się z opóźnieniem, więc dla Daty analizy równej
  dniowi bieżącemu Sprawdzenie zgodności zwykle daje „brak danych”, a Pewność oceny Bieżącej sytuacji wodnej jest
  wtedy najwyżej „średnia”. Pliki są dogrywane ręcznie.
- **Satelita.** Zdjęcia pokazują stan roślin, nie ilość wody w glebie, a rośliny reagują na brak wody z opóźnieniem
  od kilku dni do kilku tygodni. Odczyt NDVI i NDMI nie zmienia żadnego werdyktu ani wyniku Sprawdzenia zgodności:
  jest opisany, a to, co mówi obok bilansu wodnego, zapisuje ślad decyzyjny. Kierunek zmiany i porównanie
  z wcześniejszymi latami powstają tylko w Okresie krytycznym, porównanie tylko z Historią upraw (co najmniej 3 lata
  tej samej Uprawy). Zgodność zdjęć z Uprawą ozimą jest sprawdzana tylko, gdy w odczytanych scenach są zdjęcia
  z kwietnia (Data analizy do końca maja). Archiwum zaczyna się w lipcu 2015 r. (usługa zapasowa: listopad 2016 r.).
  Działka wąska ma sam NDVI, a zbyt mała nie ma odczytu (minimum 8 pikseli). Reguły odczytu według Uprawy obejmują
  zboża, kukurydzę, rzepak, ziemniak, burak cukrowy i użytki zielone; dla pozostałych Upraw odczyt jest tylko opisowy.
  Braki odczytu dla wcześniejszych lat obniżają Pewność oceny Podatności wieloletniej, choć ten werdykt z nich nie
  korzysta (reguła robocza).
- Zachowanie usług po przekroczeniu ich limitów zapytań nie było sprawdzane; taka odpowiedź jest traktowana jak
  brak danych ze źródła.

Metoda:

- Bilans jest uproszczony: bez spływu powierzchniowego, podsiąku i nawodnień, ze stałą głębokością korzeni
  ograniczoną do 100 cm; nadmiar wody nie jest oceniany.
- Ilości nawadniania są ilościami netto, bez strat, sprawności urządzeń i podziału na dawki, więc górna granica
  przedziału bywa duża.
- Poza Sezonem uprawy i w spoczynku uprawy ozimej Stopień niedoboru dotyczy Zapasu wody w glebie i jest liczony
  tą samą skalą co w sezonie (osobnej skali nie ma).
- Podsumowanie zredagowane przez model językowy nie jest powtarzalne między uruchomieniami, a kontrola odpowiedzi
  ma granice opisane w punkcie 6.

Technika:

- Usługa działa w jednym procesie na jeden plik bazy: stan trwających analiz i liczniki limitów zapytań są
  w pamięci procesu, więc ponowne uruchomienie przerywa trwające analizy i zeruje liczniki.
- Jednocześnie biegną najwyżej 4 analizy; kolejna dostaje od razu odpowiedź `503` z nagłówkiem `Retry-After`
  (nie ma kolejki).
- Postęp analizy nie podaje powodu niepowodzenia (jest w odpowiedzi `GET /api/reports/{report_id}`).
- Raport z danymi źródłowymi zajmuje około 350 kB (głównie seria pogodowa); każdy raport pochodny to kolejny zapis.
- Nie sprawdzono: działania pod domeną na serwerze docelowym za Traefikiem, pracy pod obciążeniem wieloma
  analizami naraz, czasów z serwera docelowego dla całej analizy.

Do uzupełnienia przed zgłoszeniem: ograniczenia strony dla rolnika; aktualizacja tej listy po rozszerzeniu
katalogu Rekomendacji oraz po podłączeniu kolejnych źródeł.

## 9. Informacja o sposobie weryfikacji wygenerowanych wyników lub rekomendacji

- **Sprawdzenie zgodności w każdym Raporcie.** Bieżąca sytuacja wodna jest zestawiana z niezależnym wskaźnikiem
  suszy CDI (European Drought Observatory) z ostatniej dekady zakończonej nie później niż Data analizy i pokazywana
  obok odczytu satelitarnego z tego samego okresu. Wynik to „zgodne”, „rozbieżne” albo „brak danych”; „rozbieżne”
  obniża Pewność oceny i jest Ograniczeniem raportu. Reguły: [docs/metoda.md](docs/metoda.md).
- **Odtwarzalność.** Raport przechowuje dane źródłowe z czasem odczytu oraz ślad decyzyjny (`trace`): każdą
  regułę, warunek, wartości i wynik. Każdy wniosek da się przeliczyć ponownie i sprawdzić ręcznie; każda
  Rekomendacja podaje regułę, wartości, które ją uruchomiły, i źródło.
- **Powtarzalność i brak danych z przyszłości.** Silnik jest czystą funkcją danych, Uprawy, Daty analizy i Historii
  upraw. Testy sprawdzają, że ten sam wkład daje ten sam wynik i że wynik dla danej daty nie zmienia się po
  dopisaniu dni późniejszych; dekada wskaźnika CDI, która w Dacie analizy jeszcze trwa, nie jest czytana.
- **Pewność oceny i Ograniczenia.** Każdy werdykt mówi, na ile kompletne dane za nim stoją, a każde zejście
  w Łańcuchu zamienników i każdy brak danych jest nazwany w Raporcie.
- **Testy automatyczne** (`backend/tests/`, bez dostępu do sieci, na nagranych odpowiedziach usług): przypadki
  bilansu liczone ręcznie, wartości na granicach progów, tabela przypadków Pewności oceny, zgodność Symulacji
  z Raportem, niezmienność Podatności wieloletniej względem Historii upraw, a także sprawdzanie danych wejściowych,
  limity zapytań i brak sekretów w repozytorium.
- **Sprawdzenia na żywych źródłach** (`backend/tests/smoke/`): cała analiza prawdziwych działek z czasem i wynikiem
  każdego źródła.
- **Test wsteczny** (`scripts/backtest.py`): zwykłe analizy dla listy działek i dat z lat o znanym przebiegu, z tabelą
  obu werdyktów, klasy CDI, wyniku Sprawdzenia zgodności, stwierdzonych Przyczyn i czasów (punkt 1, „Narzędzia”).
- **Podsumowanie modelu językowego** jest przyjmowane tylko po kontroli liczb, dat i sformułowań względem Raportu
  (punkt 6); inaczej Raport dostaje podsumowanie z szablonu.

Do uzupełnienia przed zgłoszeniem: tabela wyników testu wstecznego (działki z różnych regionów, daty z lat suchych
i mokrych: werdykt, klasa CDI, zgodność, czas), porównanie z niezależnymi danymi o suszy rolniczej, jeśli da się
je pozyskać, oraz sześć Przykładów wybranych z tych wyników (trzy z niedoborem, trzy bez).

## Skalowanie

Prototyp działa dla dowolnej działki ewidencyjnej z terenu Polski: żadne dane nie są przygotowane z góry dla
wybranych miejsc (wyszukiwanie działek obejmuje cały kraj; punkt poza Polską jest odrzucany). Poniżej to, co
byłoby potrzebne, żeby rozwiązanie służyło wielu rolnikom.

Limity i dostępność zewnętrznych źródeł danych:

- Dziś: każde źródło ma własny limit czasu; brak odpowiedzi nie przerywa analizy, tylko tworzy Ograniczenie raportu
  i obniża Pewność oceny (Łańcuch zamienników; dane satelitarne mają dwie wymienne usługi). Wynik jest zapisywany
  razem z danymi źródłowymi, więc ponowne otwarcie Raportu, Symulacja i raport pochodny niczego nie pobierają.
  Usługa ogranicza liczbę zapytań na adres i liczbę analiz trwających jednocześnie (część „Bezpieczeństwo i dane
  osobowe”), a narzędzia pomiarowe trzymają własne tempo poniżej limitów usług.
- Wąskie gardła: limit bezpłatnego archiwum pogodowego (około 85 analiz na godzinę z adresu serwera),
  brak opublikowanych limitów i gwarancji dostępności usług gleby (mapa IUNG-PIB, WCS ISRIC) oraz bezpłatnych
  usług satelitarnych.
- Potrzebne przy większym ruchu: buforowanie danych, które się nie zmieniają (gleba, teren i geometria działki
  dla raz analizowanego miejsca, seria pogodowa do dnia poprzedniego), lokalna kopia danych o wodach odświeżana
  okresowo, płatne plany usług pogodowej i satelitarnych (albo własna kopia danych źródłowych), kolejka analiz
  zamiast odmowy przy zajętych miejscach.

Aktualizacja danych i czas odpowiedzi:

- Dane pobierane na żywo są aktualne z natury. Pliki wskaźnika suszy trzeba dogrywać (nowa dekada co 10 dni);
  dziś robi się to ręcznie skryptem `scripts/unpack_drought_files.py` (opis: `deploy/edo-archives/README.md`),
  docelowo zadaniem okresowym.
- Zmierzony czas całej analizy (21.11.2026, maszyna deweloperska, 18 analiz na żywych źródłach, gleba jeszcze
  z wolnej usługi REST SoilGrids): 8,7–24,7 s, mediana 15,5 s, przy budżecie 30 s. Po zmianie źródła gleby
  (22.11.2026, 3 analizy, pogoda z zapisanej odpowiedzi, pozostałe źródła na żywo): 2,2–3,2 s. Raport raz policzony otwiera się bez
  ponownego liczenia; Symulacja dla listy 22 pozycji (w tym 20 próbnych) policzyła się w około 0,4 s.
- Przy większym ruchu jeden proces z plikiem SQLite nie wystarczy: potrzebna jest wspólna baza (np. PostgreSQL),
  wspólne liczniki limitów i kolejka zadań, żeby uruchomić kilka procesów usługi. Kod jest na to przygotowany
  podziałem: silnik jest czystą funkcją, a pobieranie, przechowywanie i liczenie są rozdzielone.
- Do uzupełnienia przed zgłoszeniem: czasy analizy i poszczególnych źródeł zmierzone z serwera docelowego
  (`scripts/measure_sources.py`) oraz decyzja, które dane buforować i jak często je odświeżać.

Koszty infrastruktury:

- Prototyp: jeden mały serwer z Dockerem; wszystkie używane dane są bezpłatne, a model językowy jest opcjonalny.
  Miejsce na dysku: około 350 kB na Raport przy przechowywaniu przez 30 dni.
- Przy rozwoju pojawią się: płatny plan usługi pogodowej (wymagany także przy użyciu komercyjnym), płatny plan
  usług satelitarnych z gwarancją dostępności, opłaty za model językowy (jedno krótkie zapytanie na analizę),
  większy serwer albo kilka serwerów, baza danych i miejsce na buforowane dane.
- Do uzupełnienia przed zgłoszeniem: szacunek kosztów miesięcznych dla przyjętej liczby analiz i możliwe
  alternatywy dla usług płatnych (kwoty z aktualnych cenników dostawców).

Kierunek rozwoju: analiza gospodarstwa z wieloma działkami (dziś jedna analiza dotyczy jednej Działki).

## Bezpieczeństwo i dane osobowe

**Dane osobowe.** Aplikacja nie ma kont ani logowania i nie zbiera danych osobowych. Zapisywany jest Identyfikator
działki, który da się powiązać z właścicielem w rejestrach publicznych; dlatego Raport jest dostępny tylko pod
losowym adresem (128 bitów losowości), nie ma listy Raportów, a Raporty są usuwane po 30 dniach. Położenie
urządzenia, jeśli strona go użyje, zostaje w przeglądarce. Adres IP odwiedzającego jest trzymany wyłącznie
w pamięci procesu przez licznik limitu zapytań, najdłużej godzinę (adresy IPv6 skrócone do sieci /64), i nie jest
zapisywany w bazie ani w logu. Log usługi zawiera Identyfikator działki, Uprawę, Datę analizy, czasy źródeł
i pierwsze 6 znaków identyfikatora Raportu; nie zawiera adresów IP ani pełnych adresów Raportów. Log dostępu
serwera aplikacji jest wyłączony, bo zawierałby jedno i drugie. Jeśli wdrożenie włączy log dostępu w Traefiku,
będzie on zawierał adresy IP i pełne adresy Raportów: wtedy trzeba ustalić czas jego przechowywania.

**Sprawdzanie danych wejściowych.** Każda trasa sprawdza długość, znaki i zakres tego, co dostaje, zanim cokolwiek
trafi do bazy albo do usługi zewnętrznej: Identyfikator działki ma ustaloną postać i najwyżej 64 znaki, identyfikator
Uprawy to małe litery, cyfry i podkreślenia, Data analizy mieści się między 01.01.2000 a dniem bieżącym, Historia
upraw ma najwyżej 32 lata z zakresu 1900–2200, współrzędne muszą leżeć w Polsce, tekst wyszukiwania ma najwyżej
120 znaków bez znaków sterujących, a tekst, który nie może być identyfikatorem Raportu, jest traktowany jak
nieznany Raport. Pola spoza kontraktu są odrzucane. Treść żądania może mieć najwyżej 16 kB i musi podawać swoją
długość. Odpowiedź z błędem ma zawsze postać `{code, message}` i nie powtarza tekstu wymyślonego przez klienta.

**Limity zapytań na adres** (liczone w pamięci procesu; odpowiedź `429` z nagłówkiem `Retry-After`; wartości to
stałe inżynierskie, zmieniane zmiennymi z punktu 1):

| Grupa tras | Limit domyślny na adres | Uzasadnienie |
|---|---|---|
| start analizy (`POST /analyses`, `.../critical-period`) | 6 na minutę i 50 na godzinę | każda analiza odpytuje wszystkie usługi danych |
| raport pochodny (`.../derive`) | 10 na minutę | obliczenia i kolejny zapis około 350 kB |
| wyszukiwanie działek (`/parcels/...`) | 40 na minutę | każde zapytanie trafia do usługi ULDK |
| Symulacja | 30 na minutę | obliczenia dla wszystkich Upraw |
| postęp analizy (`.../status`) | 600 na minutę | strona pyta co sekundę, narzędzia pomiarowe cztery razy na sekundę |
| pozostałe (odczyt Raportu, listy, opis interfejsu) | 300 na minutę | tanie odczyty |
| `GET /health` | bez limitu | kontrola stanu usługi |

Niezależnie od adresu w całej usłudze biegną jednocześnie najwyżej 4 analizy (`503` z `Retry-After`). Adresem
klienta jest adres połączenia widziany przez serwer aplikacji. Za Traefikiem serwer przyjmuje nagłówek
`X-Forwarded-For` wyłącznie od adresów podanych w `FORWARDED_ALLOW_IPS`; nagłówek wysłany przez dowolnego klienta
jest ignorowany, więc nie da się nim zmienić adresu, pod którym liczony jest limit. Gdy wdrożenie nie poda adresu
Traefika, wszyscy odwiedzający mają jeden wspólny licznik.

**Nagłówki odpowiedzi API.** `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` (adres Raportu
nie jest przekazywany dalej), `X-Frame-Options: DENY`, `Content-Security-Policy: default-src 'none';
frame-ancestors 'none'`, `Cross-Origin-Resource-Policy: same-origin` i `Cache-Control: no-store` (kopia Raportu nie
zostaje w pamięci podręcznej po drodze). Serwer aplikacji nie wysyła nagłówka `Server`. CORS nie jest otwarty,
bo strona i API są pod jedną domeną. TLS, przekierowanie na HTTPS i HSTS zapewnia Traefik; nagłówki strony dla
rolnika ustawia usługa `web` (`frontend/nginx/headers.conf`): jej polityka treści pozwala tylko na własne pliki,
kafle ortofotomapy z Geoportalu i zapytania do geokodera GUGiK.

**Opis interfejsu jest publiczny.** `/api/docs` i `/api/openapi.json` są dostępne bez ograniczeń: korzysta z nich
zespół budujący stronę, a interfejs nie ma tras administracyjnych. Strona `/api/docs` ładuje skrypt z publicznej
sieci CDN, więc ma łagodniejszą politykę treści (tylko zakaz osadzania w ramce).

**Sekrety.** Jedyny sekret to opcjonalny klucz usługi modelu językowego: tylko w pliku `.env` na serwerze, poza
repozytorium (`.gitignore`) i poza obrazem (`.dockerignore`; do obrazu kopiowane są wyłącznie `requirements.txt`
i katalog `app/`). Usługa działa w kontenerze jako użytkownik bez uprawnień administratora, a pliki wskaźnika
suszy są montowane tylko do odczytu. Test automatyczny pilnuje, że w śledzonych plikach nie ma wzorców kluczy,
adresów e-mail ani ścieżek katalogów domowych.

Poza zakresem prototypu: ochrona przed rozproszonym atakiem z wielu adresów (należy do infrastruktury przed
usługą), limity czasu połączeń (ustawiane w Traefiku), kopie zapasowe bazy raportów.

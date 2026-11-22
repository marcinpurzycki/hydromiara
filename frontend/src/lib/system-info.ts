// Texts of the "About the system" window. They follow README (data sources),
// docs/metoda.md (method) and docs/wdrozenie-pelnoskalowe.md (scaling).

export interface InfoSource {
  name: string;
  /** What is read from the source. */
  data: string;
  /** What the assessment uses it for. */
  use: string;
}

export const INTRO =
  "Hydromiara ocenia, czy uprawie na wskazanej działce ewidencyjnej brakuje wody: w wybranym dniu " +
  "i w ostatnich 10 latach. Gdy stwierdza niedobór, wskazuje jego przyczyny i dobiera do nich rekomendacje: " +
  "zatrzymywanie wody, zabiegi agrotechniczne i nawadnianie. Wynik liczy jawna, powtarzalna metoda obliczeniowa " +
  "na danych publicznych, a model językowy tylko redaguje krótkie podsumowanie raportu.";

export const LIVE_SOURCES: InfoSource[] = [
  {
    name: "GUGiK, Usługa Lokalizacji Działek Katastralnych (ULDK)",
    data: "Identyfikator działki, gmina i obręb, granice działki.",
    use: "Wskazuje miejsce, dla którego czytane są wszystkie pozostałe dane.",
  },
  {
    name: "Open-Meteo, archiwum pogodowe (reanaliza ERA5)",
    data: "Dzienny opad i parowanie wskaźnikowe (ET0) z 10 lat, do Daty analizy.",
    use: "Podstawa dziennego bilansu wody w glebie: ile wody przybyło, a ile zużyły rośliny.",
  },
  {
    name: "IUNG-PIB, mapa kategorii podatności gleb na suszę",
    data: "Kategoria gleby (I–IV) w siatce punktów wewnątrz działki.",
    use: "Określa, ile wody gleba na działce potrafi zmagazynować dla roślin.",
  },
  {
    name: "ISRIC SoilGrids 2.0",
    data: "Udział piasku, pyłu, iłu i węgla organicznego w glebie do głębokości 1 m.",
    use: "Źródło zastępcze i kontrolne dla kategorii gleby: szacunek pojemności wodnej z uziarnienia.",
  },
  {
    name: "GUGiK, numeryczny model terenu 1 m (zastępczo Copernicus DEM 30 m)",
    data: "Wysokości terenu w siatce co 5 m na działce i wokół niej.",
    use: "Spadek, kierunek spływu wody i najniższa część działki.",
  },
  {
    name: "GUGiK, Baza Danych Obiektów Topograficznych (BDOT10k)",
    data: "Rowy melioracyjne, kanały, rzeki, strumienie i zbiorniki do 500 m od granicy działki.",
    use: "Odległość i położenie wód względem działki; podstawa rekomendacji zatrzymywania wody w rowie.",
  },
  {
    name: "Copernicus Sentinel-2 (zdjęcia satelitarne)",
    data: "Wskaźniki stanu roślin (NDVI) i uwilgotnienia (NDMI) z ostatnich 30 dni i z tej samej pory roku w 5 poprzednich latach.",
    use: "Niezależny obraz działki, pokazywany obok wyniku obliczeń.",
  },
  {
    name: "Europejskie Obserwatorium Suszy (EDO), wskaźnik CDI",
    data: "Klasa zagrożenia suszą w okolicy działki, co 10 dni, od 2016 r. (pliki uzupełniane okresowo).",
    use: "Sprawdzenie zgodności: czy niezależny wskaźnik europejski potwierdza ocenę bieżącej sytuacji wodnej.",
  },
  {
    name: "GUGiK, ortofotomapa i geokoder adresów",
    data: "Zdjęcie lotnicze jako podkład mapy i położenie wpisanego adresu.",
    use: "Wybór działki na pierwszym ekranie; nie wpływają na wynik.",
  },
];

export const DERIVED_SOURCES: InfoSource[] = [
  {
    name: "Metoda FAO-56 (Allen i in., 1998)",
    data: "Dzienny bilans wody w strefie korzeniowej oraz parametry wodne upraw: współczynnik Kc, głębokość korzeni, dopuszczalne wyczerpanie wody.",
    use: "Z bilansu powstają obie oceny: bieżąca sytuacja wodna i podatność wieloletnia, a także zakres nawadniania.",
  },
  {
    name: "COBORU, porejestrowe doświadczenia odmianowe",
    data: "Średnie z kilku lat terminy siewu, faz rozwoju i zbioru upraw w Polsce.",
    use: "Sezon uprawy i przebieg zapotrzebowania rośliny na wodę w ciągu roku.",
  },
  {
    name: "Centrum Doradztwa Rolniczego, e-poradnik o melioracjach i retencji (2025)",
    data: "Okres krytyczny każdej uprawy, czyli czas największego zapotrzebowania na wodę.",
    use: "Rok z niedoborem jest oceniany właśnie w tym okresie.",
  },
  {
    name: "IUNG-PIB, System Monitoringu Suszy Rolniczej",
    data: "Przedziały pojemności wodnej dla czterech kategorii gleb.",
    use: "Przeliczenie kategorii gleby z mapy na milimetry wody dostępnej dla roślin.",
  },
  {
    name: "Wzory Saxtona i Rawlsa (2006)",
    data: "Pojemność wodna gleby wyliczona z jej uziarnienia i zawartości próchnicy.",
    use: "Kategoria gleby szacowana tam, gdzie mapa IUNG-PIB nie daje odczytu.",
  },
  {
    name: "Badania własne zespołu (listopad 2026)",
    data: "Pomiary na rzeczywistych działkach: 10 lat scen satelitarnych nad czterema działkami w czterech województwach, porównanie siatki wysokości co 5 m z pełnym modelem terenu 1 m, porównanie źródeł danych o glebie, czasy odpowiedzi źródeł.",
    use: "Dobór źródeł, okien czasowych i progów. Progi bez oparcia w literaturze są w dokumentacji metody nazwane wartościami roboczymi.",
  },
];

export const REFERENCES: string[] = [
  "Allen R.G., Pereira L.S., Raes D., Smith M. (1998). Crop evapotranspiration: guidelines for computing crop water requirements. FAO Irrigation and Drainage Paper 56.",
  "Saxton K.E., Rawls W.J. (2006). Soil water characteristic estimates by texture and organic matter for hydrologic solutions. Soil Science Society of America Journal 70, 1569–1578.",
  "Poggio L. i in. (2021). SoilGrids 2.0: producing soil information for the globe with quantified spatial uncertainty. SOIL 7, 217–240.",
  "Vajsová B. i in. (2020). Remote Sensing 12, 2195 (najmniejsza działka, którą da się ocenić z danych Sentinel-2).",
  "Centrum Doradztwa Rolniczego (2025). Melioracje, retencja i gospodarka wodna w rolnictwie. E-poradnik, część IV.",
  "COBORU. Wyniki porejestrowych doświadczeń odmianowych, wydania 2019–2025.",
  "IUNG-PIB. System Monitoringu Suszy Rolniczej: kategorie podatności gleb na suszę.",
];

export const TRANSPARENCY =
  "Sposób użycia każdego źródła i wzoru jest dostępny przy każdym wyliczonym wyniku. W raporcie przy każdej " +
  "przyczynie niedoboru przycisk „i” pokazuje wskaźnik, próg, źródło danych i regułę rekomendacji, a część " +
  "„Dodatkowe informacje” zawiera listę użytych źródeł z datą danych i licencją, ograniczenia raportu, " +
  "sprawdzenie zgodności oraz ślad decyzji: krok po kroku, jaka wartość dała jaki wniosek.";

export interface InfoDirection {
  title: string;
  text: string;
  note: string;
}

export const DIRECTIONS: InfoDirection[] = [
  {
    title: "Pomiar na polu: sonda wilgotności gleby",
    text:
      "Rolnik mógłby kupić trzypoziomową sondę wilgotności gleby, która mierzy na trzech głębokościach " +
      "i wysyła odczyty przez LoRaWAN, czyli sieć radiową dalekiego zasięgu o małym poborze energii. " +
      "Odczyty zbierałby osobny backend, a bilans wody w glebie mógłby wtedy korzystać z pomiaru z działki, " +
      "a nie tylko z danych pogodowych i map glebowych.",
    note: "Wymaga dalszych badań w terenie.",
  },
  {
    title: "Skalowanie: wiele działek naraz",
    text:
      "API jest przygotowane do analizy wielu działek: przyjmuje dowolną działkę w Polsce, a każda analiza " +
      "jest osobnym, niezależnym zadaniem, więc tą samą drogą można zlecać większe obszary: gospodarstwo, " +
      "obręb lub gminę. Same obliczenia zajmują ułamek sekundy na działkę.",
    note:
      "Pełne skalowanie wymaga zmian wydajnościowych (wspólna baza, kolejka analiz, kopie lokalne danych) " +
      "i dostosowania limitów API dostawców danych. Szczegóły: „Instrukcja wdrożenia pełnoskalowego” " +
      "w dokumentacji rozwiązania.",
  },
];

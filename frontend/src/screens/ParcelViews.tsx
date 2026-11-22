import type { ParcelMatch } from "../api/types";

interface ChoiceProps {
  query: string;
  matches: ParcelMatch[];
  onChoose: (match: ParcelMatch) => void;
  onBack: () => void;
}

/** Several parcels match a number with a precinct name: the user picks one. */
export function ParcelChoice({ query, matches, onChoose, onBack }: ChoiceProps) {
  return (
    <div className="screen screen-narrow">
      <div>
        <h1>Która to działka?</h1>
        <p className="lead">Wpis „{query}” pasuje do kilku działek w Polsce. Wybierz swoją.</p>
      </div>
      <ul className="choice-list">
        {matches.map((match) => (
          <li key={match.parcel_id}>
            <button type="button" onClick={() => onChoose(match)}>
              <b>
                {match.region}, gmina {match.commune}
              </b>
              <span className="choice-pick">To ta działka →</span>
              <span className="muted">
                {match.county}, woj. {match.voivodeship}
              </span>
              <span className="muted small">Identyfikator działki: {match.parcel_id}</span>
            </button>
          </li>
        ))}
      </ul>
      <button type="button" className="link-button" onClick={onBack}>
        Nie ma tu mojej działki – wróć i popraw numer
      </button>
      <p className="hint">
        Jeśli znasz pełny identyfikator działki albo wskażesz ją na mapie, ten krok się nie pojawi.
      </p>
    </div>
  );
}

/** Nothing matches the typed text: neither a parcel nor an address. */
export function ParcelMissing({ query, onBack }: { query: string; onBack: () => void }) {
  return (
    <div className="screen screen-text">
      <h1>Nie znaleźliśmy takiej działki</h1>
      <div role="alert" className="notice notice-warning">
        <b>Wpisu „{query}” nie ma w ewidencji działek ani wśród adresów</b>
        <span>Analiza nie została uruchomiona. Sprawdź wpis i spróbuj jeszcze raz.</span>
      </div>
      <div className="card">
        <h2>Co możesz zrobić</h2>
        <ul className="plain-list">
          <li>Sprawdź, czy w numerze nie ma literówki, np. „125/3”, a nie „125-3”.</li>
          <li>Dopisz nazwę obrębu po przecinku, np. „125/3, Brzoza”.</li>
          <li>
            Wpisz pełny identyfikator działki, np. „040302_2.0004.125/3”. Znajdziesz go w wypisie z rejestru
            gruntów albo we wniosku o dopłaty.
          </li>
          <li>Wpisz adres albo nazwę miejscowości, a potem wskaż działkę kliknięciem na mapie.</li>
        </ul>
      </div>
      <button type="button" className="button button-primary button-large" onClick={onBack}>
        Wróć i popraw działkę
      </button>
      <p className="hint">Twój wybór uprawy i Data analizy zostały zachowane.</p>
    </div>
  );
}

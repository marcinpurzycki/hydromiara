import { useRef, useState } from "react";
import { todayIso, yearsBefore } from "../lib/format";
import { Icon } from "./Icon";

/** Analysis date: today by default, any day of the last ten years. */
export function DateField({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [infoOpen, setInfoOpen] = useState(false);
  const today = todayIso();

  const openPicker = () => {
    const element = input.current;
    if (!element) return;
    try {
      // showPicker is missing in older browsers and may refuse; focus is the fallback.
      element.showPicker();
    } catch {
      element.focus();
    }
  };

  return (
    <div className="field field-date">
      <label className="field-label" htmlFor="analysis-date">
        Data analizy
      </label>
      <div className="date-box">
        <input
          id="analysis-date"
          ref={input}
          type="date"
          value={value}
          min={yearsBefore(today, 10)}
          max={today}
          onChange={(event) => onChange(event.target.value || today)}
        />
        <button type="button" className="date-button" aria-label="Otwórz kalendarz" onClick={openPicker}>
          <Icon name="calendar" size={22} />
        </button>
        <button
          type="button"
          className={infoOpen ? "date-button date-info date-info-on" : "date-button date-info"}
          aria-expanded={infoOpen}
          aria-label="Co to jest Data analizy"
          onClick={() => setInfoOpen(!infoOpen)}
          onBlur={() => setInfoOpen(false)}
        >
          i
        </button>
      </div>
      {infoOpen && (
        <div role="tooltip" className="tooltip">
          <b>Data analizy</b> to dzień, na który liczymy stan wody. Domyślnie dziś. Możesz wybrać dowolny dzień
          z ostatnich 10 lat, np. żeby sprawdzić miniony sezon.
        </div>
      )}
    </div>
  );
}

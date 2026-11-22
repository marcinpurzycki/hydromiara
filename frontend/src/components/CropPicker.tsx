import { useState } from "react";
import type { Crop } from "../api/types";
import { lowerPl } from "../lib/format";

interface Props {
  crops: Crop[];
  cropId: string | null;
  error: string | null;
  onChange: (cropId: string | null) => void;
}

/** Tiles for the common crops and a search field over the whole closed list. */
export function CropPicker({ crops, cropId, error, onChange }: Props) {
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const tiles = crops.filter((crop) => crop.tile);
  const chosen = crops.find((crop) => crop.id === cropId) ?? null;
  const shownText = text || (chosen && !chosen.tile ? chosen.name : "");
  const matching = crops.filter((crop) => lowerPl(crop.name).includes(lowerPl(text.trim())));

  const pick = (crop: Crop) => {
    setText("");
    setOpen(false);
    onChange(crop.id);
  };

  return (
    <>
      <div className="field">
        <p className="field-label">Zaznacz, co rośnie na tym polu</p>
        <div className="crop-tiles">
          {tiles.map((crop) => (
            <button
              key={crop.id}
              type="button"
              className={crop.id === cropId && !text ? "tile tile-on" : "tile"}
              aria-pressed={crop.id === cropId && !text}
              onClick={() => pick(crop)}
            >
              {crop.name}
            </button>
          ))}
        </div>
      </div>
      <div className="field field-other-crop">
        <label className="field-label" htmlFor="other-crop">
          Inna uprawa
        </label>
        <input
          id="other-crop"
          type="text"
          autoComplete="off"
          placeholder="Zacznij pisać, np. Owies"
          value={shownText}
          onChange={(event) => {
            setText(event.target.value);
            setOpen(true);
            if (chosen) onChange(null);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => {
            // A full name typed by hand counts as a choice.
            const typed = crops.find((crop) => lowerPl(crop.name) === lowerPl(text.trim()));
            if (typed) pick(typed);
            else setOpen(false);
          }}
          onKeyDown={(event) => event.key === "Escape" && setOpen(false)}
        />
        {open && (
          <ul className="suggestions">
            {matching.map((crop) => (
              <li key={crop.id}>
                {/* mousedown: the choice has to land before the field loses focus */}
                <button type="button" onMouseDown={(event) => (event.preventDefault(), pick(crop))}>
                  {crop.name}
                </button>
              </li>
            ))}
            {matching.length === 0 && <li className="suggestions-empty">Tej uprawy nie ma na liście.</li>}
          </ul>
        )}
        {error && <p className="field-error">{error}</p>}
      </div>
    </>
  );
}

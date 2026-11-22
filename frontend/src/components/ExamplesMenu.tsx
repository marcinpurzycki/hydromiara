import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Crop, Example } from "../api/types";
import { datePl } from "../lib/format";

const GROUPS: [Example["kind"], string][] = [
  ["deficit", "Z niedoborem wody"],
  ["no_deficit", "Bez niedoboru wody"],
];

/** Floating list of ready-made examples; an example only fills the form. */
export function ExamplesMenu({ crops, onPick }: { crops: Crop[]; onPick: (example: Example) => void }) {
  const [open, setOpen] = useState(false);
  const [examples, setExamples] = useState<Example[] | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.examples().then(setExamples, () => setExamples([]));
  }, []);

  useEffect(() => {
    if (!open) return;
    const close = (event: Event) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !box.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("click", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("click", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  if (!examples || examples.length === 0) return null;
  const cropName = (id: string) => crops.find((crop) => crop.id === id)?.name ?? id;

  return (
    <div className="examples no-print" ref={box}>
      {open && (
        <div className="examples-list">
          {GROUPS.map(([kind, title]) => {
            const group = examples.filter((example) => example.kind === kind);
            if (group.length === 0) return null;
            return (
              <div key={kind} className="examples-group">
                <p className="eyebrow">{title}</p>
                {group.map((example) => (
                  <button
                    key={example.label}
                    type="button"
                    onClick={() => {
                      setOpen(false);
                      onPick(example);
                    }}
                  >
                    <b>
                      {cropName(example.crop_id)} · {datePl(example.analysis_date)}
                    </b>
                    <span>{example.parcel_id}</span>
                  </button>
                ))}
              </div>
            );
          })}
          <p className="hint">
            Przykład tylko wypełnia formularz. Analiza liczy się potem tak samo jak dla każdej działki.
          </p>
        </div>
      )}
      <button
        type="button"
        className={open ? "button button-large button-outline button-on" : "button button-large button-outline"}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        Demo
      </button>
    </div>
  );
}

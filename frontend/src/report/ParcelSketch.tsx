import { useMemo } from "react";
import type { ReportMap } from "../api/types";
import { waterLegend } from "../lib/report-view";
import { SKETCH_SIZE, buildSketch } from "../lib/sketch";

/** Parcel outline with the downhill direction, water nearby and places to hold water. */
export function ParcelSketch({ map }: { map: ReportMap }) {
  const sketch = useMemo(() => buildSketch(map), [map]);
  if (!sketch) return null;
  const parts = [
    sketch.arrow && `Strzałka: kierunek spływu (${map.downhill_direction?.label}).`,
    sketch.water.length > 0 && `Na niebiesko woda w okolicy: ${waterLegend(map).join("; ")}.`,
    sketch.sites.length > 0 && "Zielona linia: miejsce zatrzymania wody.",
  ].filter(Boolean);
  return (
    <figure className="sketch">
      <svg viewBox={`0 0 ${SKETCH_SIZE} ${SKETCH_SIZE}`} role="img" aria-label="Szkic działki, północ u góry">
        <defs>
          <marker id="sketch-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M0 0L10 5L0 10z" className="sketch-arrow-head" />
          </marker>
        </defs>
        <rect width={SKETCH_SIZE} height={SKETCH_SIZE} className="sketch-ground" />
        {sketch.water.map((item, index) => (
          <path key={`w${index}`} d={item.path} className={item.closed ? "sketch-water-area" : "sketch-water"} />
        ))}
        {sketch.parcel.map((path, index) => (
          <path key={`p${index}`} d={path} className="sketch-parcel" />
        ))}
        {sketch.sites.map((item, index) => (
          <path key={`s${index}`} d={item.path} className={item.closed ? "sketch-site-area" : "sketch-site"} />
        ))}
        {sketch.arrow && <line {...sketch.arrow} className="sketch-arrow" markerEnd="url(#sketch-arrow)" />}
        <text x={SKETCH_SIZE - 14} y={24} className="sketch-north">
          N
        </text>
      </svg>
      <figcaption>{parts.join(" ")} Szkic poglądowy z obrysu działki, nie projekt.</figcaption>
    </figure>
  );
}

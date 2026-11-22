import { describe, expect, it } from "vitest";
import type { Cause, Report } from "../api/types";
import { cropAbbreviation, datePl, rangePl } from "./format";
import {
  currentAssessed,
  currentReason,
  foundCauses,
  indicatorText,
  irrigationCells,
  noCausesSentence,
  unjudgedCauses,
  yearNotAssessed,
} from "./report-view";
import { buildSketch, linesOf } from "./sketch";

const cause = (id: Cause["id"], found: boolean, value: number | null, threshold: number | null = null): Cause => ({
  id,
  found,
  finding: "",
  indicator: { name: "", value, unit: id === "crop_demand" ? "" : "mm/m", threshold },
  facts: [],
  recommendations: [],
});

const report = (part: Record<string, unknown>) => part as unknown as Report;

describe("report reading", () => {
  it("does not take level 0 of an unassessed verdict for a norm", () => {
    const base = { deficit_level: 0, label: "nie oceniono", reason: "", confidence: { level: "niska", why: "" } };
    expect(currentAssessed(report({ current_status: { ...base, details: { assessed: false } } }))).toBe(false);
    expect(currentAssessed(report({ current_status: { ...base, details: {} } }))).toBe(true);
  });

  it("separates found causes from the ones without data", () => {
    const causes = [cause("soil", true, 120, 140), cause("runoff", false, 1.2, 3), cause("precipitation", false, null)];
    const read = report({ causes });
    expect(foundCauses(read).map((item) => item.id)).toEqual(["soil"]);
    expect(unjudgedCauses(read).map((item) => item.id)).toEqual(["precipitation"]);
  });

  it("writes the indicator with its unit and threshold", () => {
    expect(indicatorText(cause("soil", true, 120, 140))).toBe("120 mm/m (próg 140)");
    expect(indicatorText(cause("crop_demand", true, 1.15))).toBe("1,15");
    expect(indicatorText(cause("soil", false, null))).toBeNull();
  });

  it("replaces the placeholder reason with numbers", () => {
    const status = {
      reason: "Uzasadnienie słowne nie jest jeszcze dostępne w tej wersji; liczby są w szczegółach.",
      details: { depletion_pct: 84, precipitation_30d_mm: 13 },
    };
    const text = currentReason(report({ current_status: status }));
    expect(text).toContain("84%");
    expect(text).toContain("13 mm");
    expect(currentReason(report({ current_status: { reason: "Gotowe zdanie.", details: {} } }))).toBe("Gotowe zdanie.");
  });

  it("takes the sentence about no causes from the limitations", () => {
    const limitations = [
      { text: "Stałe.", affects: "recommendations", permanent: true },
      { text: "Na tej Działce nie stwierdzono niedoboru wody.", affects: "recommendations", permanent: false },
    ];
    expect(noCausesSentence(report({ limitations }))).toBe("Na tej Działce nie stwierdzono niedoboru wody.");
    expect(noCausesSentence(report({ limitations: [] }))).toContain("nie stwierdzono niedoboru");
  });

  it("shows irrigation amounts only when irrigation is justified", () => {
    const none = { applicable: true, text: "", justified: false, amount_mm: null, amount_m3_ha: null, timing: "Nie teraz.", reason_if_none: "" };
    expect(irrigationCells(none)).toEqual([]);
    const cells = irrigationCells({ ...none, justified: true, amount_mm: [62, 181], amount_m3_ha: [620, 1810], timing: "Teraz" });
    expect(cells.map((cell) => cell.label)).toEqual(["Czy warto", "Ile wody", "Kiedy"]);
    expect(cells[1].value).toBe("62–181 mm");
  });

  it("recognises a year of the historical course that was not assessed", () => {
    const crop = { id: "maize", name: "Kukurydza" };
    expect(yearNotAssessed({ year: 2015, crop, deficit: false, satellite_note: "Roku nie oceniono: brak pogody." })).toBe(true);
    expect(yearNotAssessed({ year: 2015, crop, deficit: false, satellite_note: null })).toBe(false);
  });
});

describe("formatting", () => {
  it("writes dates, ranges and crop marks", () => {
    expect(datePl("2023-06-20")).toBe("20.06.2023");
    expect(rangePl([62, 181])).toBe("62–181");
    expect(cropAbbreviation("Pszenica ozima")).toBe("PO");
    expect(cropAbbreviation("Żyto")).toBe("ŻY");
  });
});

describe("parcel sketch", () => {
  const square = { type: "Polygon" as const, coordinates: [[[18.0, 52.0], [18.001, 52.0], [18.001, 52.001], [18.0, 52.001], [18.0, 52.0]]] };

  it("reads the lines of polygons and lines", () => {
    expect(linesOf(square)).toHaveLength(1);
    expect(linesOf({ type: "MultiLineString", coordinates: [[[1, 2], [3, 4]], [[5, 6], [7, 8]]] })).toHaveLength(2);
  });

  it("points the arrow down the slope with north up", () => {
    const sketch = buildSketch({
      parcel_geometry: square,
      downhill_direction: { label: "południe", azimuth_deg: 180 },
      retention_sites: [],
      water_objects: [{ kind: "ditch", name: null, geometry: { type: "LineString", coordinates: [[18.0, 51.9995], [18.001, 51.9995]] } }],
    });
    expect(sketch?.parcel).toHaveLength(1);
    expect(sketch?.water).toHaveLength(1);
    expect(sketch!.arrow!.y2).toBeGreaterThan(sketch!.arrow!.y1);
    expect(sketch!.arrow!.x2).toBeCloseTo(sketch!.arrow!.x1, 3);
  });
});

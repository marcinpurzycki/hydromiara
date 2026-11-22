import { describe, expect, it } from "vitest";
import type { CropSusceptibility, Report, ReportMap } from "../api/types";
import { byDeficitShare, multiyearNotAssessedLabel, stateDay, waterLegend } from "./report-view";

const report = (part: Record<string, unknown>) => part as unknown as Report;
const line = { type: "LineString" as const, coordinates: [] };

describe("labels the page gives to the Report", () => {
  it("names the state day only when it differs from the analysis date", () => {
    const of = (state_date: unknown) =>
      stateDay(report({ meta: { analysis_date: "2026-11-22" }, current_status: { details: { state_date } } }));
    expect(of("2026-11-21")).toBe("2026-11-21");
    expect(of("2026-11-22")).toBeNull();
    expect(of(undefined)).toBeNull();
  });

  it("does not call a bare field an unassessed crop", () => {
    expect(multiyearNotAssessedLabel(report({ meta: { crop: { id: "bare_field" } } }))).toBe("Bez uprawy, nie oceniane");
    expect(multiyearNotAssessedLabel(report({ meta: { crop: { id: "maize" } } }))).toBe("Nie oceniono");
  });

  it("lists each kind of water once, with names", () => {
    const map = {
      water_objects: [
        { kind: "ditch", name: null, geometry: line },
        { kind: "watercourse", name: "Wkra", geometry: line },
        { kind: "ditch", name: null, geometry: line },
        { kind: "spring", name: null, geometry: line },
      ],
    } as unknown as ReportMap;
    expect(waterLegend(map)).toEqual(["rów melioracyjny", "rzeka lub strumień (Wkra)", "woda"]);
  });

  it("orders the ranking by the share of years with a deficit", () => {
    const crop = (crop_id: string, deficit_years: number, total_years: number): CropSusceptibility => ({
      crop_id,
      name: crop_id,
      deficit_years,
      total_years,
      deficit_level: 0,
    });
    const sorted = [crop("a", 4, 10), crop("b", 3, 5), crop("c", 2, 10), crop("d", 0, 0)].sort(byDeficitShare);
    expect(sorted.map((item) => item.crop_id)).toEqual(["c", "a", "b", "d"]);
  });
});

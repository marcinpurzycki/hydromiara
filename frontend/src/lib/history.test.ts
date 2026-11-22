import { describe, expect, it } from "vitest";
import {
  chooseCrop,
  defaultWindow,
  emptyDraft,
  givenCount,
  historyOfDraft,
  limitedTo,
  windowFromMessage,
} from "./history";

describe("crop history draft", () => {
  it("offers ten years ending with the analysis year", () => {
    expect(defaultWindow("2023-06-20")).toEqual([2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023]);
  });

  it("carries a choice back to the older years", () => {
    const draft = chooseCrop(emptyDraft(5), 3, "maize");
    expect(draft.crops).toEqual(["maize", "maize", "maize", "maize", ""]);
    expect(draft.filledFrom).toEqual([3, 3, 3, null, null]);
  });

  it("stops carrying at a year set by hand", () => {
    const first = chooseCrop(emptyDraft(5), 1, "potato");
    const second = chooseCrop(first, 4, "maize");
    expect(second.crops).toEqual(["potato", "potato", "maize", "maize", "maize"]);
  });

  it("overrides years filled from a newer year", () => {
    const first = chooseCrop(emptyDraft(4), 3, "maize");
    const second = chooseCrop(first, 1, "potato");
    expect(second.crops).toEqual(["potato", "potato", "maize", "maize"]);
  });

  it("clears only the years filled from the cleared one", () => {
    const first = chooseCrop(chooseCrop(emptyDraft(4), 0, "potato"), 3, "maize");
    const cleared = chooseCrop(first, 3, "");
    expect(cleared.crops).toEqual(["potato", "", "", ""]);
    expect(givenCount(cleared)).toBe(1);
  });

  it("sends only the years that were filled in", () => {
    const draft = chooseCrop(emptyDraft(3), 1, "maize");
    expect(historyOfDraft([2021, 2022, 2023], draft)).toEqual({ years: { "2021": "maize", "2022": "maize" } });
  });

  it("limits a history to the allowed years", () => {
    expect(limitedTo({ years: { "2012": "maize", "2015": "potato" } }, [2014, 2015])).toEqual({
      years: { "2015": "potato" },
    });
    expect(limitedTo({ same_every_year: true }, [2015])).toEqual({ same_every_year: true });
  });

  it("reads the window named in a refusal of the API", () => {
    const message = "Historia upraw może dotyczyć tylko lat Okna wieloletniego tej analizy (2013–2022). Poza nim: 2023.";
    expect(windowFromMessage(message)?.[0]).toBe(2013);
    expect(windowFromMessage(message)?.length).toBe(10);
    expect(windowFromMessage("bez zakresu")).toBeNull();
  });
});

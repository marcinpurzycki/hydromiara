import { describe, expect, it } from "vitest";
import { pageEnds, pdfFileName, type Span } from "./report-pdf";

describe("pages of the PDF file", () => {
  it("keeps a short strip on one page", () => {
    expect(pageEnds(900, 1000, [])).toEqual([900]);
  });

  it("ends a page between sections when one fits", () => {
    const blocks: Span[] = [[0, 400], [420, 980], [1010, 1500]];
    expect(pageEnds(1500, 1000, blocks, [410, 995])).toEqual([995, 1500]);
  });

  it("falls back to a boundary that cuts through no block", () => {
    const blocks: Span[] = [[0, 600], [620, 940], [960, 1300]];
    expect(pageEnds(1300, 1000, blocks, [100])).toEqual([960, 1300]);
  });

  it("cuts a block higher than a page at the page height", () => {
    expect(pageEnds(2500, 1000, [[0, 2500]])).toEqual([1000, 2000, 2500]);
  });

  it("does not leave a page less than half full for the sake of a boundary", () => {
    expect(pageEnds(1800, 1000, [[0, 300], [300, 1700]], [300])).toEqual([1000, 1800]);
  });

  it("names the file after the parcel and the date", () => {
    expect(pdfFileName("040704_2.0020.34/2", "2023-06-20")).toBe("hydromiara-raport-040704-2-0020-34-2-2023-06-20.pdf");
  });
});

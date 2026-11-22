// A PDF file of the Report, made in the browser: the Report as shown on the
// page is drawn to a canvas (html2canvas) and laid out on A4 pages (jsPDF).
// Both libraries are loaded only when the file is asked for.

const PAGE_WIDTH_MM = 210;
const PAGE_HEIGHT_MM = 297;
const MARGIN_MM = 12;
const FOOTER_MM = 8;
const CONTENT_WIDTH_MM = PAGE_WIDTH_MM - 2 * MARGIN_MM;
const CONTENT_HEIGHT_MM = PAGE_HEIGHT_MM - 2 * MARGIN_MM - FOOTER_MM;
// The Report is laid out for the file as on a wide screen, also on a phone.
const LAYOUT_WIDTH_PX = 1184;
const SCALE = 2;
const MAX_CANVAS_HEIGHT_PX = 30000;
// A page is cut at a block boundary unless that would leave it less than this full.
const MIN_PAGE_FILL = 0.5;
const JPEG_QUALITY = 0.92;

/** Blocks a page break must not cut through. */
const WHOLE_BLOCKS = "h1, h2, h3, p, li, tr, dt, dd, svg, .year-strip, .scale, .cause-indicator, .notice > *";
const SVG_STYLES = ["fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-dasharray", "opacity"];
const SVG_TEXT_STYLES = ["font-family", "font-size", "font-weight", "text-anchor"];

export type Span = [top: number, bottom: number];

/**
 * Ends of the pages of a strip `total` high. A page ends, in this order of
 * preference: between two sections (`gaps`), at the lowest boundary that cuts
 * through no block, or at the full page height (a block higher than a page).
 * A boundary that would leave the page less than half full is not used.
 */
export function pageEnds(total: number, pageHeight: number, blocks: Span[], gaps: number[] = []): number[] {
  const boundaries = [...new Set(blocks.flat())]
    .filter((y) => !blocks.some(([top, bottom]) => y > top + 0.5 && y < bottom - 0.5))
    .sort((a, b) => a - b);
  const sorted = [...gaps].sort((a, b) => a - b);
  const ends: number[] = [];
  let start = 0;
  while (total - start > pageHeight + 0.5) {
    const limit = start + pageHeight;
    const fits = (y: number) => y <= limit && y >= start + pageHeight * MIN_PAGE_FILL;
    start = sorted.filter(fits).pop() ?? boundaries.filter(fits).pop() ?? limit;
    ends.push(start);
  }
  ends.push(total);
  return ends;
}

/** File name from the parcel identifier and the analysis date. */
export function pdfFileName(parcelId: string, analysisDate: string): string {
  const parcel = parcelId.replace(/[^0-9A-Za-z]+/g, "-").replace(/^-|-$/g, "");
  return `hydromiara-raport-${parcel}-${analysisDate}.pdf`;
}

/** The drawing library reads inline SVG without the page styles, so they are written into it. */
function inlineSvgStyles(root: HTMLElement): void {
  const view = root.ownerDocument.defaultView;
  if (!view) return;
  for (const node of root.querySelectorAll<SVGElement>("svg, svg *")) {
    const style = view.getComputedStyle(node);
    const names = node.tagName.toLowerCase() === "text" ? [...SVG_STYLES, ...SVG_TEXT_STYLES] : SVG_STYLES;
    for (const name of names) {
      const value = style.getPropertyValue(name);
      if (value) node.setAttribute(name, value);
    }
  }
}

function blocksOf(root: HTMLElement): Span[] {
  const origin = root.getBoundingClientRect().top;
  return [...root.querySelectorAll<HTMLElement>(WHOLE_BLOCKS)]
    .map((node) => node.getBoundingClientRect())
    .filter((box) => box.height > 0)
    .map((box): Span => [box.top - origin, box.bottom - origin]);
}

/** Middles of the gaps between the sections (the direct children) of the element. */
function gapsOf(root: HTMLElement): number[] {
  const origin = root.getBoundingClientRect().top;
  const boxes = [...root.children].map((node) => node.getBoundingClientRect()).filter((box) => box.height > 0);
  return boxes.slice(1).map((box, index) => (boxes[index].bottom + box.top) / 2 - origin);
}

/** Draws the element and saves it as an A4 file; `footer` is repeated on every page. */
export async function saveElementAsPdf(element: HTMLElement, fileName: string, footer: string): Promise<void> {
  const [{ default: html2canvas }, { jsPDF }] = await Promise.all([import("html2canvas"), import("jspdf")]);
  await document.fonts.ready;
  let blocks: Span[] = [];
  let gaps: number[] = [];
  let layoutHeight = element.scrollHeight;
  const scale = Math.min(SCALE, MAX_CANVAS_HEIGHT_PX / Math.max(element.scrollHeight, 1));
  const canvas = await html2canvas(element, {
    scale,
    backgroundColor: "#ffffff",
    logging: false,
    windowWidth: LAYOUT_WIDTH_PX,
    ignoreElements: (node) => node.classList.contains("no-print") || node.classList.contains("chevron"),
    onclone: (_document, clone) => {
      clone.classList.add("pdf-export");
      inlineSvgStyles(clone);
      blocks = blocksOf(clone);
      gaps = gapsOf(clone);
      layoutHeight = clone.getBoundingClientRect().height;
    },
  });

  // Canvas pixels per layout pixel, and layout pixels per millimetre of the page.
  const ratio = canvas.height / layoutHeight;
  const pxPerMm = canvas.width / ratio / CONTENT_WIDTH_MM;
  const ends = pageEnds(layoutHeight, CONTENT_HEIGHT_MM * pxPerMm, blocks, gaps);
  const pdf = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4", compress: true });
  const footerHeight = Math.round(FOOTER_MM * pxPerMm * ratio);
  let top = 0;
  ends.forEach((end, index) => {
    const sliceTop = Math.round(top * ratio);
    const sliceHeight = Math.max(1, Math.round(end * ratio) - sliceTop);
    const page = document.createElement("canvas");
    page.width = canvas.width;
    page.height = Math.round(CONTENT_HEIGHT_MM * pxPerMm * ratio) + footerHeight;
    const context = page.getContext("2d");
    if (!context) throw new Error("canvas unavailable");
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, page.width, page.height);
    context.drawImage(canvas, 0, sliceTop, canvas.width, sliceHeight, 0, 0, canvas.width, sliceHeight);
    // The footer is drawn as a picture, so the file needs no font of its own.
    context.fillStyle = "#5f5852";
    context.font = `${Math.round(footerHeight * 0.36)}px "Open Sans", sans-serif`;
    context.textBaseline = "bottom";
    context.fillText(footer, 0, page.height);
    const count = `Strona ${index + 1} z ${ends.length}`;
    context.fillText(count, page.width - context.measureText(count).width, page.height);
    if (index > 0) pdf.addPage("a4", "portrait");
    pdf.addImage(
      page.toDataURL("image/jpeg", JPEG_QUALITY),
      "JPEG",
      MARGIN_MM,
      MARGIN_MM,
      CONTENT_WIDTH_MM,
      CONTENT_HEIGHT_MM + FOOTER_MM,
    );
    top = end;
  });
  pdf.save(fileName);
}

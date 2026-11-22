// Line icons drawn on a 36 × 36 grid.

const PATHS = {
  drop: "M18 4c6 8 10 13 10 18a10 10 0 0 1-20 0c0-5 4-10 10-18z",
  waves: "M4 13c5-4 9 4 14 0s9 4 14 0M4 23c5-4 9 4 14 0s9 4 14 0",
  cloud: "M11 23a6 6 0 0 1 0-12 8 8 0 0 1 15 2 5 5 0 0 1-1 10zM13 28v4M19 28v4M25 28v4",
  ear: "M18 33V12M18 12c-2-3-2-6 0-9 2 3 2 6 0 9zM18 19c-5-1-6-4-6-7 4 0 6 3 6 7zM18 19c5-1 6-4 6-7-4 0-6 3-6 7zM18 27c-5-1-6-4-6-7 4 0 6 3 6 7zM18 27c5-1 6-4 6-7-4 0-6 3-6 7z",
  sprout: "M18 32V17M18 17C18 10 13 6 5 6c0 8 5 11 13 11zM18 21c0-6 5-9 13-9 0 7-5 9-13 9z",
  print: "M10 13V5h16v8M10 26H6V13h24v13h-4M10 21h16v10H10z",
  pdf: "M9 4h12l8 8v20H9zM21 4v8h8M14 24h8M14 19h8",
  link: "M15 21a6 6 0 0 0 8.5 0l4-4a6 6 0 0 0-8.5-8.5l-2 2M21 15a6 6 0 0 0-8.5 0l-4 4a6 6 0 0 0 8.5 8.5l2-2",
  list: "M8 10h20M8 18h20M8 26h14",
  restart: "M7 18a11 11 0 1 0 3.2-7.8M7 6v5h5",
  calendar: "M6 8h24v22H6zM6 15h24M12 4v6M24 4v6",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 26 }: { name: IconName; size?: number }) {
  return (
    <svg className="icon" viewBox="0 0 36 36" width={size} height={size} aria-hidden="true">
      <path d={PATHS[name]} />
    </svg>
  );
}

export function Chevron({ open }: { open: boolean }) {
  return (
    <svg className={open ? "chevron chevron-open" : "chevron"} viewBox="0 0 20 20" aria-hidden="true">
      <path d="M5 8l5 5 5-5" />
    </svg>
  );
}

export function Arrow() {
  return (
    <svg className="flow-arrow" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 12h15m-6-6 6 6-6 6" />
    </svg>
  );
}

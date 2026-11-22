import type { Crop } from "../api/types";
import { lowerPl } from "../lib/format";
import { chooseCrop, type HistoryDraft } from "../lib/history";
import { Chevron } from "./Icon";

interface Props {
  years: number[];
  draft: HistoryDraft;
  crops: Crop[];
  currentCropName: string;
  wide?: boolean;
  onChange: (draft: HistoryDraft) => void;
}

/** One crop per year, newest year first; empty years count "as now". */
export function HistoryForm({ years, draft, crops, currentCropName, wide = false, onChange }: Props) {
  const options = crops.filter((crop) => crop.id !== "bare_field");
  const rows = years.map((year, index) => ({ year, index })).reverse();
  return (
    <div className={wide ? "history-grid history-grid-wide" : "history-grid"}>
      {rows.map(({ year, index }) => {
        const value = draft.crops[index];
        const tone = !value ? "select-empty" : draft.filledFrom[index] !== null ? "select-auto" : "";
        return (
          <div key={year} className="history-row">
            <label htmlFor={`history-${year}`}>{year}</label>
            <div className="select-wrap">
              <select
                id={`history-${year}`}
                className={tone}
                value={value}
                onChange={(event) => onChange(chooseCrop(draft, index, event.target.value))}
              >
                <option value="">jak obecnie ({lowerPl(currentCropName)})</option>
                {options.map((crop) => (
                  <option key={crop.id} value={crop.id}>
                    {crop.name}
                  </option>
                ))}
              </select>
              <Chevron open={false} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

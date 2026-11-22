// The crop list, fetched once and shared by all screens.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Crop } from "../api/types";

let cached: Promise<Crop[]> | null = null;

export function loadCrops(): Promise<Crop[]> {
  if (!cached) {
    cached = api.crops().catch((error) => {
      cached = null;
      throw error;
    });
  }
  return cached;
}

export function useCrops(): { crops: Crop[]; failed: boolean } {
  const [crops, setCrops] = useState<Crop[]>([]);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    loadCrops().then(
      (list) => active && setCrops(list),
      () => active && setFailed(true),
    );
    return () => {
      active = false;
    };
  }, []);
  return { crops, failed };
}

// What the Start screen knows about a started analysis, kept for the progress
// screen (the progress route of the API does not repeat it).
export interface AnalysisInfo {
  parcelId: string;
  region: string;
  cropId: string;
  cropName: string;
  analysisDate: string;
}

const infoKey = (reportId: string) => `hydromiara:analysis:${reportId}`;

export function storeAnalysisInfo(reportId: string, info: AnalysisInfo): void {
  try {
    sessionStorage.setItem(infoKey(reportId), JSON.stringify(info));
  } catch {
    // Storage switched off: the progress screen shows a shorter heading.
  }
}

export function readAnalysisInfo(reportId: string): AnalysisInfo | null {
  try {
    const raw = sessionStorage.getItem(infoKey(reportId));
    return raw ? (JSON.parse(raw) as AnalysisInfo) : null;
  } catch {
    return null;
  }
}

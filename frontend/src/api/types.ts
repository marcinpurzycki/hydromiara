// Shapes of the API responses, following backend/app/contracts.

export type Scalar = boolean | number | string | null;

export interface GeoJsonGeometry {
  type: "Point" | "MultiPoint" | "LineString" | "MultiLineString" | "Polygon" | "MultiPolygon";
  coordinates: unknown[];
}

export interface MonthDay {
  month: number;
  day: number;
}

export interface YearlyPeriod {
  start: MonthDay;
  end: MonthDay;
}

export interface Crop {
  id: string;
  name: string;
  name_genitive: string;
  tile: boolean;
  season: YearlyPeriod | null;
  critical_period: YearlyPeriod | null;
}

export interface Example {
  label: string;
  parcel_id: string;
  crop_id: string;
  analysis_date: string;
  kind: "deficit" | "no_deficit";
}

export interface ParcelMatch {
  parcel_id: string;
  number: string;
  region: string;
  commune: string;
  county: string;
  voivodeship: string;
  geometry?: GeoJsonGeometry | null;
}

export type SourceId = "weather" | "satellite" | "soil" | "hydro" | "terrain";
export type SourceState = "wait" | "run" | "done" | "missing";

export interface SourceProgress {
  id: SourceId;
  state: SourceState;
  note?: string | null;
}

export interface AnalysisStatus {
  state: "running" | "done" | "failed";
  sources: SourceProgress[];
}

export type CropHistory = { years: Record<string, string> } | { same_every_year: boolean };

export interface Confidence {
  level: "wysoka" | "średnia" | "niska";
  why: string;
}

export interface CropRef {
  id: string;
  name: string;
}

export interface CurrentStatus {
  deficit_level: number;
  label: string;
  reason: string;
  confidence: Confidence;
  details: Record<string, Scalar>;
}

export interface MultiyearYear {
  year: number;
  deficit: boolean;
  partial: boolean;
  values: Record<string, Scalar>;
}

export interface MultiyearSusceptibility {
  deficit_years: number;
  total_years: number;
  deficit_level: number;
  typical_period: string | null;
  confidence: Confidence;
  years: MultiyearYear[];
  history_assumption: string;
}

export interface HistoricalYear {
  year: number;
  crop: CropRef;
  deficit: boolean;
  satellite_note?: string | null;
}

export interface HistoricalCourse {
  years: HistoricalYear[];
  comparison_sentence: string;
}

export interface Indicator {
  name: string;
  value: number | null;
  unit: string;
  threshold: number | null;
}

export interface RetentionSite {
  id: string;
  label: string;
  geometry: GeoJsonGeometry;
}

export interface Recommendation {
  id: string;
  group: string;
  text: string;
  gain: string;
  rule: string;
  inputs: Record<string, Scalar>;
  citation: string;
  retention_site?: RetentionSite | null;
  link?: string | null;
}

export type CauseId = "precipitation" | "soil" | "runoff" | "crop_demand";

export interface Cause {
  id: CauseId;
  found: boolean;
  finding: string;
  indicator: Indicator;
  facts: { text: string; source: string }[];
  recommendations: Recommendation[];
}

export interface Irrigation {
  applicable: boolean;
  text: string;
  justified: boolean | null;
  amount_mm: [number, number] | null;
  amount_m3_ha: [number, number] | null;
  timing: string | null;
  reason_if_none: string | null;
}

export interface ConsistencyCheck {
  result: "zgodne" | "rozbieżne" | "brak danych";
  sentence: string;
  items: { source: string; period: string; value: string; meaning: string }[];
}

export interface ReportSource {
  topic: string;
  name: string;
  license: string;
  mode: string;
  data_date: string | null;
  fetched_at: string | null;
  chain_step: number;
  missing: boolean;
}

export interface Limitation {
  text: string;
  affects: "current" | "multiyear" | "recommendations" | "all";
  permanent: boolean;
}

export interface ReportMap {
  parcel_geometry: GeoJsonGeometry;
  downhill_direction: { label: string; azimuth_deg: number } | null;
  retention_sites: RetentionSite[];
  water_objects: { kind: string; name: string | null; geometry: GeoJsonGeometry }[];
}

export interface TraceEntry {
  rule_id: string;
  condition: string;
  values: Record<string, Scalar>;
  result: string;
}

export interface Report {
  meta: {
    report_id: string;
    created_at: string;
    parcel: ParcelMatch & { area_ha: number };
    crop: CropRef;
    analysis_date: string;
    derived_from: string | null;
    changed_from_date: string | null;
  };
  headline: string;
  summary: { text: string; source: "llm" | "template" };
  season: { in_season: boolean; last_season: { start: string; end: string } | null; note?: string | null };
  current_status: CurrentStatus;
  multiyear_susceptibility: MultiyearSusceptibility;
  historical_course: HistoricalCourse | null;
  causes: Cause[];
  irrigation: Irrigation;
  consistency_check: ConsistencyCheck;
  sources: ReportSource[];
  limitations: Limitation[];
  map: ReportMap;
  trace: TraceEntry[];
}

export interface CropSusceptibility {
  crop_id: string;
  name: string;
  deficit_years: number;
  total_years: number;
  deficit_level: number;
}

export interface RankingResponse {
  current: CropSusceptibility;
  top: CropSusceptibility[];
  limitations: Limitation[];
}

export interface CompareResponse {
  current: CropSusceptibility;
  other: CropSusceptibility;
  years: { year: number; current_deficit: boolean; other_deficit: boolean; partial: boolean }[];
}

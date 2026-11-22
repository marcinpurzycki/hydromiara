// Calls to the Hydromiara API under the relative path /api.
import type {
  AnalysisStatus,
  CompareResponse,
  Crop,
  CropHistory,
  Example,
  ParcelMatch,
  RankingResponse,
  Report,
} from "./types";

/** Error answered by the API: every error body is {code, message}. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly retryAfterS: number | null = null,
  ) {
    super(message);
  }
}

const NETWORK_MESSAGE = "Nie udało się połączyć z serwerem. Sprawdź połączenie i spróbuj ponownie.";
const GENERIC_MESSAGE = "Coś poszło nie tak po naszej stronie. Spróbuj ponownie za chwilę.";

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "network_error", NETWORK_MESSAGE);
  }
  if (response.ok) {
    return (response.status === 204 ? undefined : await response.json()) as T;
  }
  const retryAfter = Number(response.headers.get("Retry-After"));
  let code = "internal_error";
  let message = GENERIC_MESSAGE;
  try {
    const parsed = (await response.json()) as { code?: unknown; message?: unknown };
    if (typeof parsed.code === "string") code = parsed.code;
    if (typeof parsed.message === "string") message = parsed.message;
  } catch {
    // The body is not JSON (e.g. an answer of the reverse proxy); keep the generic text.
  }
  throw new ApiError(response.status, code, message, retryAfter > 0 ? retryAfter : null);
}

const query = (params: Record<string, string | number>) =>
  new URLSearchParams(Object.entries(params).map(([key, value]) => [key, String(value)])).toString();

export const api = {
  crops: () => request<Crop[]>("GET", "/crops"),
  examples: () => request<Example[]>("GET", "/examples"),

  searchParcels: (q: string) =>
    request<{ matches: ParcelMatch[] }>("GET", `/parcels/search?${query({ q })}`).then((r) => r.matches),
  parcelAt: (lon: number, lat: number) =>
    request<{ matches: ParcelMatch[] }>("GET", `/parcels/at?${query({ lon, lat })}`).then(
      (r) => r.matches[0] ?? null,
    ),
  // The identifier contains a slash and the route takes it as it is.
  parcel: (parcelId: string) => request<ParcelMatch>("GET", `/parcels/${parcelId}`),

  startAnalysis: (parcelId: string, cropId: string, analysisDate: string) =>
    request<{ report_id: string }>("POST", "/analyses", {
      parcel_id: parcelId,
      crop_id: cropId,
      analysis_date: analysisDate,
    }),
  status: (reportId: string) => request<AnalysisStatus>("GET", `/analyses/${reportId}/status`),
  putHistory: (reportId: string, history: CropHistory) =>
    request<void>("PUT", `/analyses/${reportId}/crop-history`, history),

  report: (reportId: string) => request<Report>("GET", `/reports/${reportId}`),
  derive: (reportId: string, history: CropHistory) =>
    request<{ report_id: string }>("POST", `/reports/${reportId}/derive`, { crop_history: history }),

  ranking: (reportId: string) => request<RankingResponse>("GET", `/reports/${reportId}/simulation/ranking`),
  compare: (reportId: string, cropId: string) =>
    request<CompareResponse>("GET", `/reports/${reportId}/simulation/compare?${query({ crop_id: cropId })}`),
};

export const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Message of any thrown value, ready to show. */
export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : GENERIC_MESSAGE;
}

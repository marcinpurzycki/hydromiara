import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, isAnalysisFailure } from "./client";

const answer = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers });

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("API client", () => {
  it("repeats a read once after a short refusal for too many requests", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(answer(429, { code: "rate_limited", message: "Za dużo zapytań." }, { "Retry-After": "2" }))
      .mockResolvedValueOnce(answer(200, []));
    vi.stubGlobal("fetch", fetchMock);
    const crops = api.crops();
    await vi.advanceTimersByTimeAsync(2000);
    expect(await crops).toEqual([]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not wait out a long refusal and never repeats a start of an analysis", async () => {
    const limited = () =>
      answer(429, { code: "rate_limited", message: "Za dużo zapytań." }, { "Retry-After": "600" });
    const fetchMock = vi.fn().mockImplementation(async () => limited());
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.crops()).rejects.toMatchObject({ code: "rate_limited", retryAfterS: 600 });
    await expect(api.startAnalysis("040704_2.0020.34/2", "maize", "2026-06-01")).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("tells a failed analysis from other errors", () => {
    expect(isAnalysisFailure(new ApiError(404, "weather_unavailable", ""))).toBe(true);
    expect(isAnalysisFailure(new ApiError(429, "rate_limited", ""))).toBe(false);
    expect(isAnalysisFailure(new Error("x"))).toBe(false);
  });
});

import type {
  CompareItem,
  FundDetailResponse,
  HoldingDraft,
  HoldingItem,
  ScreenerOptionResponse,
  ScreenerPreset,
  ScreenerQueryPayload,
  ScreenerQueryResponse,
  ScreenerSectorStat,
  WatchlistItem,
} from "../types";

async function request<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  const payload = (await response.json().catch(() => ({}))) as { error?: string } & T;

  if (!response.ok) {
    throw new Error(payload.error || "请求失败，请稍后再试。");
  }

  return payload as T;
}

export function getFundDetail(code: string) {
  return request<FundDetailResponse>(`/api/funds/${code}`);
}

export async function getWatchlist() {
  const payload = await request<{ items: WatchlistItem[] }>("/api/watchlist");
  return payload.items;
}

export function addWatchlist(code: string) {
  return request<{ ok: true }>("/api/watchlist", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

export function removeWatchlist(code: string) {
  return request<{ ok: true }>(`/api/watchlist/${code}`, {
    method: "DELETE",
  });
}

export async function getCompareList() {
  const payload = await request<{ items: CompareItem[] }>("/api/compare");
  return payload.items;
}

export function addCompare(code: string) {
  return request<{ ok: true }>("/api/compare", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

export function removeCompare(code: string) {
  return request<{ ok: true }>(`/api/compare/${code}`, {
    method: "DELETE",
  });
}

export async function getHoldings() {
  const payload = await request<{ items: HoldingItem[] }>("/api/holdings");
  return payload.items;
}

export function saveHolding(draft: HoldingDraft) {
  return request<{ ok: true }>("/api/holdings", {
    method: "POST",
    body: JSON.stringify(draft),
  });
}

export function removeHolding(code: string) {
  return request<{ ok: true }>(`/api/holdings/${code}`, {
    method: "DELETE",
  });
}

export function getScreenerOptions() {
  return request<ScreenerOptionResponse>("/api/screener/options");
}

export function queryScreener(query: ScreenerQueryPayload) {
  return request<ScreenerQueryResponse>("/api/screener/query", {
    method: "POST",
    body: JSON.stringify(query),
  });
}

export async function getScreenerSectors() {
  const payload = await request<{ items: ScreenerSectorStat[] }>("/api/screener/sectors");
  return payload.items;
}

export function getSectorFunds(sector: string, ranking?: string) {
  const query = ranking ? `?ranking=${encodeURIComponent(ranking)}` : "";
  return request<ScreenerQueryResponse>(`/api/screener/sectors/${encodeURIComponent(sector)}/funds${query}`);
}

export function refreshScreenerCache() {
  return request<{ ok: true; updatedAt: string | null; total: number; coverageNote: string }>("/api/screener/refresh", {
    method: "POST",
  });
}

export async function getScreenerPresets() {
  const payload = await request<{ items: ScreenerPreset[] }>("/api/screener/presets");
  return payload.items;
}

export function saveScreenerPreset(name: string, query: ScreenerQueryPayload) {
  return request<ScreenerPreset>("/api/screener/presets", {
    method: "POST",
    body: JSON.stringify({ name, query }),
  });
}

export function deleteScreenerPreset(id: string) {
  return request<{ ok: true }>(`/api/screener/presets/${id}`, {
    method: "DELETE",
  });
}

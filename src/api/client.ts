import type { FundDetailResponse, HoldingDraft, HoldingItem, WatchlistItem } from "../types";

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

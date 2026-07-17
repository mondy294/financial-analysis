export class ApiClientError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const err = data?.error;
    throw new ApiClientError(
      err?.code || "HTTP_ERROR",
      err?.message || res.statusText,
      res.status,
    );
  }
  return data as T;
}

export const api = {
  health: () => request<{ status: string; version: string }>("/api/health"),
  tradingDay: () =>
    request<{ latest_trading_day: string | null; pattern_latest_date: string | null }>(
      "/api/meta/trading-day",
    ),
  patternsMeta: () =>
    request<
      Array<{
        id: string;
        display_name: string;
        version: string;
        threshold: number;
        description: string;
      }>
    >("/api/meta/patterns"),
  searchStocks: (q: string) =>
    request<Array<{ code: string; name: string; industry_name?: string; is_st: boolean }>>(
      `/api/stocks/search?q=${encodeURIComponent(q)}`,
    ),
  stockDetail: (code: string) =>
    request<{
      code: string;
      name: string;
      exchange: string;
      industry_code?: string;
      industry_name?: string;
      list_date?: string;
      is_st: boolean;
      market_cap?: number;
    }>(`/api/stocks/${encodeURIComponent(code)}`),
  kline: (code: string, limit = 250) =>
    request<
      Array<{
        trade_date: string;
        open: number;
        high: number;
        low: number;
        close: number;
        volume: number;
        amount?: number;
        pct_change?: number;
      }>
    >(`/api/stocks/${encodeURIComponent(code)}/kline?limit=${limit}`),
  features: (code: string, limit = 250) =>
    request<
      Array<{
        trade_date: string;
        ma5?: number | null;
        ma10?: number | null;
        ma20?: number | null;
        ma60?: number | null;
        macd?: number | null;
        macd_signal?: number | null;
        macd_hist?: number | null;
        rsi_14?: number | null;
        atr_14?: number | null;
        boll_upper?: number | null;
        boll_mid?: number | null;
        boll_lower?: number | null;
        return_1d?: number | null;
        return_5d?: number | null;
        return_20d?: number | null;
        ma_position?: number | null;
        ma_bull_arrange?: boolean | null;
      }>
    >(`/api/stocks/${encodeURIComponent(code)}/features?limit=${limit}`),
  snapshot: (code: string, tradeDate?: string) => {
    const q = tradeDate ? `?trade_date=${tradeDate}` : "";
    return request<{
      code: string;
      trade_date: string;
      open?: number;
      high?: number;
      low?: number;
      close?: number;
      volume?: number;
      amount?: number;
      pct_change?: number;
      features: Record<string, number | boolean | null>;
    }>(`/api/stocks/${encodeURIComponent(code)}/snapshot${q}`);
  },
  relationships: (
    code: string,
    opts?: { tradeDate?: string; window?: string; limit?: number },
  ) => {
    const params = new URLSearchParams();
    if (opts?.tradeDate) params.set("trade_date", opts.tradeDate);
    if (opts?.window) params.set("window", opts.window);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    const q = params.toString() ? `?${params}` : "";
    return request<StockRelationships>(
      `/api/stocks/${encodeURIComponent(code)}/relationships${q}`,
    );
  },
  /** limit=0 表示全部命中（相似度降序） */
  patternTop: (patternId: string, tradeDate?: string, limit = 0) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (tradeDate) params.set("trade_date", tradeDate);
    return request<PatternHit[]>(
      `/api/patterns/${encodeURIComponent(patternId)}/top?${params}`,
    );
  },
  patternStats: (tradeDate?: string) => {
    const q = tradeDate ? `?trade_date=${tradeDate}` : "";
    return request<{ trade_date: string; stats: Record<string, Record<string, number>> }>(
      `/api/patterns/stats${q}`,
    );
  },
  patternHits: (code: string, tradeDate?: string) => {
    const q = tradeDate ? `?trade_date=${tradeDate}` : "";
    return request<PatternHit[]>(`/api/patterns/hits/${encodeURIComponent(code)}${q}`);
  },
  evalPattern: (body: { code: string; trade_date?: string; pattern_id?: string }) =>
    request<PatternEval>("/api/patterns/eval", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  scanPatterns: (body: {
    trade_date?: string;
    pattern_ids?: string[];
    force?: boolean;
  }) =>
    request<Job>("/api/patterns/scan", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  job: (jobId: string) => request<Job>(`/api/jobs/${encodeURIComponent(jobId)}`),
  jobs: (limit = 20) => request<Job[]>(`/api/jobs?limit=${limit}`),
  signals: (tradeDate?: string, limit = 50) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (tradeDate) params.set("trade_date", tradeDate);
    return request<SignalRow[]>(`/api/signals?${params}`);
  },
  reports: () =>
    request<Array<{ trade_date: string; html: boolean; md: boolean }>>("/api/reports"),
  doctor: () =>
    request<{
      db_ok: boolean;
      stock_count: number;
      kline_latest: string | null;
      feature_latest: string | null;
      pattern_latest: string | null;
    }>("/api/system/doctor"),
};

export type WindowRange = { length: number; start: string; end: string };

export type PatternHit = {
  trade_date: string;
  code: string;
  name: string;
  pattern_id: string;
  pattern_score: number;
  pattern_rank: number;
  reasons: string[];
  chosen_windows: Record<string, number>;
  chosen_window_ranges?: Record<string, WindowRange> | null;
  stage_similarity: Record<string, number>;
  feature_similarity: Record<string, number>;
  distance: number;
  hard_failed: string[];
  metrics_values: Record<string, unknown>;
};

export type PatternEval = {
  code: string;
  name: string;
  trade_date: string;
  pattern_id: string;
  matched: boolean;
  similarity: number;
  threshold: number;
  distance: number;
  version: string;
  chosen_windows: Record<string, number>;
  chosen_window_ranges: Record<string, WindowRange>;
  stage_similarity: Record<string, number>;
  feature_similarity: Record<string, number>;
  hard_failed: string[];
  reasons: string[];
  metrics_values: Record<string, unknown>;
};

export type Job = {
  job_id: string;
  kind: string;
  status: string;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  progress: number;
  message?: string | null;
  error?: string | null;
  result?: Record<string, unknown> | null;
};

export type SignalRow = {
  trade_date: string;
  code: string;
  name?: string;
  final_score?: number | null;
  rank?: number | null;
  reasons?: string[];
};

export type RelationNeighbor = {
  peer: string;
  peer_name: string;
  relation_value: number;
  sample_size: number;
  is_same_industry: boolean;
};

export type StockRelationships = {
  code: string;
  window: string;
  relation_type: string;
  calc_date: string | null;
  positive: RelationNeighbor[];
  negative: RelationNeighbor[];
};

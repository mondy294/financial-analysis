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
  clustersMeta: () => request<{ profiles: ClusterProfileMeta[] }>("/api/clusters/meta"),
  clustersList: (profileId = "pearson_w60", hideSingletons = true) => {
    const params = new URLSearchParams({
      profile_id: profileId,
      hide_singletons: String(hideSingletons),
    });
    return request<ClustersListOut>(`/api/clusters?${params}`);
  },
  clusterDetail: (clusterId: number, profileId = "pearson_w60", limit = 100) => {
    const params = new URLSearchParams({
      profile_id: profileId,
      limit: String(limit),
    });
    return request<ClusterDetailOut>(`/api/clusters/${clusterId}?${params}`);
  },
  stockCluster: (code: string, profileId = "pearson_w60", peers = 20) => {
    const params = new URLSearchParams({
      profile_id: profileId,
      peers: String(peers),
    });
    return request<StockClusterOut>(
      `/api/stocks/${encodeURIComponent(code)}/cluster?${params}`,
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
  systemTasks: () => request<SystemTasksPayload>("/api/system/tasks"),
  runSystemTask: (task_id: string, params: Record<string, unknown> = {}) =>
    request<Job>("/api/system/tasks/run", {
      method: "POST",
      body: JSON.stringify({ task_id, params }),
    }),
  cacheStats: () =>
    request<{ namespaces: Record<string, { count?: number; volume_bytes?: number }> }>(
      "/api/system/cache/stats",
    ),
  featureCatalog: () =>
    request<FeatureCatalogItem[]>("/api/meta/feature-catalog"),
  listDefinitions: () =>
    request<DefinitionListItem[]>("/api/patterns/definitions"),
  getDefinition: (id: string) =>
    request<DefinitionEditable>(`/api/patterns/definitions/${encodeURIComponent(id)}`),
  saveDefinition: (id: string, body: DefinitionBody, note?: string) =>
    request<DefinitionEditable>(`/api/patterns/definitions/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify({ body, note }),
    }),
  publishDefinition: (id: string, note?: string) =>
    request<DefinitionPublishOut>(
      `/api/patterns/definitions/${encodeURIComponent(id)}/publish`,
      { method: "POST", body: JSON.stringify({ note }) },
    ),
  cloneDefinition: (
    id: string,
    payload?: { new_id?: string; display_name?: string },
  ) =>
    request<DefinitionEditable>(
      `/api/patterns/definitions/${encodeURIComponent(id)}/clone`,
      { method: "POST", body: JSON.stringify(payload || {}) },
    ),
  deleteDefinition: (id: string) =>
    request<{ id: string; deleted: boolean }>(
      `/api/patterns/definitions/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    ),
  definitionRevisions: (id: string) =>
    request<RevisionMeta[]>(
      `/api/patterns/definitions/${encodeURIComponent(id)}/revisions`,
    ),
  evalPreview: (
    id: string,
    payload: { code: string; trade_date?: string; body?: DefinitionBody },
  ) =>
    request<PatternEval>(
      `/api/patterns/definitions/${encodeURIComponent(id)}/eval-preview`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  dryScan: (
    id: string,
    payload: { trade_date?: string; limit?: number; body?: DefinitionBody },
  ) =>
    request<Job>(`/api/patterns/definitions/${encodeURIComponent(id)}/dry-scan`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

export type TargetValueJson = {
  ideal: number;
  tolerance: number;
  weight?: number;
  mode?: string;
  hard?: boolean;
  hard_min_similarity?: number;
  hard_min?: number | null;
  hard_max?: number | null;
};

export type DefinitionBody = {
  id: string;
  version: string;
  display_name: string;
  description: string;
  threshold: number;
  history_bars?: number | null;
  stage_weights: Record<string, number>;
  timeline: Array<{
    name: string;
    role?: "range" | "up" | "down" | null;
    window: { min_length: number; max_length: number };
    targets: Record<string, TargetValueJson>;
  }>;
  relations: Array<{
    name: string;
    attach_to_stage: string;
    stage_map: Record<string, string>;
    target: TargetValueJson;
  }>;
  context_features: Array<{
    name: string;
    lookback_bars?: number | null;
    key?: string | null;
    target: TargetValueJson;
  }>;
  constraints?: {
    exclude_st?: boolean;
    min_list_days?: number | null;
    min_amount?: number | null;
    min_market_cap?: number | null;
    allow_suspended?: boolean;
  } | null;
  metadata?: Record<string, unknown>;
};

export type DefinitionListItem = {
  id: string;
  display_name: string;
  description: string;
  status: string;
  published_version: string | null;
  has_draft: boolean;
  deletable?: boolean;
  updated_at: string | null;
  created_at: string | null;
};

export type DefinitionEditable = {
  id: string;
  display_name: string;
  description: string;
  status: string;
  published_version: string | null;
  source: string;
  draft_updated_at: string | null;
  updated_at: string | null;
  body: DefinitionBody;
};

export type DefinitionPublishOut = {
  id: string;
  published_version: string;
  status: string;
  body: DefinitionBody;
  note?: string | null;
};

export type RevisionMeta = {
  version: string;
  note?: string | null;
  created_at?: string | null;
  created_by?: string | null;
  is_published: boolean;
};

export type FeatureCatalogItem = {
  name: string;
  category: string;
  kind: string;
  description: string;
  tier?: "universal" | "role_specific" | "relation" | "context" | string;
  roles?: string[] | null;
  ui_group?: string;
  default_target?: Partial<TargetValueJson> | null;
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

export type ClusterProfileMeta = {
  profile_id: string;
  run_id: string;
  calc_date: string | null;
  n_clusters: number | null;
  modularity: number | null;
  universe_size: number | null;
  edge_used: number | null;
  created_at: string | null;
};

export type ClustersListOut = {
  profile_id: string;
  run: {
    run_id: string;
    calc_date: string;
    n_clusters: number | null;
    modularity: number | null;
    universe_size: number | null;
    edge_used: number | null;
    resolution: number | null;
    graph_spec?: Record<string, unknown>;
  } | null;
  clusters: Array<{
    cluster_id: number;
    label: string;
    size: number;
    avg_internal_similarity: number | null;
    density: number | null;
    representative_code: string | null;
    top_members: Array<{ code: string; name: string; centrality: number }>;
  }>;
};

export type ClusterDetailOut = {
  profile_id: string;
  run_id: string;
  cluster: {
    cluster_id: number;
    label: string;
    size: number;
    avg_internal_similarity: number | null;
    density: number | null;
    representative_code: string | null;
  };
  members: Array<{
    code: string;
    name: string;
    centrality: number;
    rank_in_cluster: number;
  }>;
};

export type StockClusterOut = {
  profile_id: string;
  run_id?: string;
  cluster_id: number | null;
  label: string | null;
  size: number;
  rank_in_cluster?: number;
  centrality?: number;
  peers: Array<{
    code: string;
    name: string;
    rank_in_cluster: number;
    centrality: number;
  }>;
};

export type TaskParamSpec = {
  name: string;
  type: "date" | "bool" | "string" | "int" | "float" | "codes";
  label: string;
  required: boolean;
  default?: unknown;
  help?: string;
};

export type TaskSpec = {
  id: string;
  group: string;
  label: string;
  description: string;
  heavy: boolean;
  dangerous: boolean;
  params: TaskParamSpec[];
};

export type SystemTasksPayload = {
  groups: Array<{ group: string; label: string; tasks: TaskSpec[] }>;
  heavy_running: {
    job_id: string;
    kind: string;
    status: string;
    message?: string | null;
  } | null;
};

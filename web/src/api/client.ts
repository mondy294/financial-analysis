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
        display_name_en?: string;
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
      market_cap?: number | null;
      float_market_cap?: number | null;
      pe_ttm?: number | null;
      pe_static?: number | null;
      pb?: number | null;
      ps_ttm?: number | null;
      valuation_date?: string | null;
    }>(`/api/stocks/${encodeURIComponent(code)}`),
  /** 按公告日/区间的财务披露（预告/快报/定期报告） */
  disclosures: (opts: {
    startDate: string;
    endDate: string;
    mainOnly?: boolean;
    enrichForecast?: boolean;
    /** 公告后涨跌；默认 false，避免扫 K 线拖慢列表 */
    enrichReturns?: boolean;
    category?: string;
  }) => {
    const params = new URLSearchParams({
      start_date: opts.startDate,
      end_date: opts.endDate,
    });
    if (opts.mainOnly) params.set("main_only", "true");
    if (opts.enrichForecast) params.set("enrich_forecast", "true");
    if (opts.enrichReturns) params.set("enrich_returns", "true");
    if (opts.category) params.set("category", opts.category);
    return request<{
      start_date: string;
      end_date: string;
      notice_date?: string;
      main_only: boolean;
      enrich_forecast?: boolean;
      enrich_returns?: boolean;
      total: number;
      counts: Record<string, number>;
      items: Array<{
        code: string;
        name: string;
        board?: string;
        board_label?: string;
        category: string;
        category_label: string;
        notice_type: string;
        title: string;
        notice_date: string;
        url?: string | null;
        parent_np_yoy?: number | null;
        parent_np_value?: number | null;
        predict_type?: string | null;
        report_period?: string | null;
        parent_np_sq?: number | null;
        parent_np_qoq?: number | null;
        parent_np_qoq_prev?: number | null;
        parent_np_qoq_delta?: number | null;
        return_1d?: number | null;
        return_5d?: number | null;
        return_10d?: number | null;
        return_since_notice?: number | null;
        /** 最新总市值，单位亿元 */
        market_cap?: number | null;
      }>;
    }>(`/api/stocks/disclosures?${params}`);
  },
  /** 中报预告 × 估值 × 公告后涨跌 OLS 因子分析 */
  disclosuresFactorAnalysis: (opts: {
    startDate: string;
    endDate: string;
    mainOnly?: boolean;
  }) => {
    const params = new URLSearchParams({
      start_date: opts.startDate,
      end_date: opts.endDate,
    });
    if (opts.mainOnly !== false) params.set("main_only", "true");
    else params.set("main_only", "false");
    return request<{
      start_date: string;
      end_date: string;
      main_only: boolean;
      candidates: number;
      dropped_n: number;
      dropped: Array<{ code: string; reason: string }>;
      drop_hint?: string | null;
      ok: boolean;
      message?: string | null;
      n: number;
      feature_keys: string[];
      feature_labels: Record<string, string>;
      intercept: number | null;
      r_squared: number | null;
      std_intercept: number | null;
      std_r_squared: number | null;
      coefficients: Array<{
        key: string;
        label: string;
        coef: number;
        std_coef: number;
        mean: number;
        std: number;
      }>;
      formula: {
        text: string;
        intercept: number;
        coefs: Record<string, number>;
        means: Record<string, number>;
        stds: Record<string, number>;
        note: string;
      } | null;
      corr: Record<string, Record<string, number | null>>;
      groups: {
        up_n: number;
        down_n: number;
        flat_n: number;
        up_rate: number;
        down_rate: number;
        up_means: Record<string, number | null>;
        down_means: Record<string, number | null>;
        diff_down_minus_up: Record<string, number | null>;
      } | null;
      rows: Array<{
        code: string;
        name: string;
        notice_date: string;
        predict_type?: string | null;
        report_period?: string | null;
        valuation_date?: string | null;
        pe_ttm: number;
        market_cap: number;
        ln_mcap: number;
        parent_np_h1: number;
        parent_np_annualized: number;
        parent_np_yoy: number;
        parent_np_yoy_pct: number;
        forecast_pe: number;
        forecast_ey: number;
        forecast_ey_pct: number;
        return_since_notice: number;
        return_pct: number;
        fitted_return_pct?: number | null;
        residual_pct?: number | null;
      }>;
    }>(`/api/stocks/disclosures/factor-analysis?${params}`);
  },
  earningsFairAnchor: (code: string, lookbackDays = 5) =>
    request<{
      available: boolean;
      reason?: string | null;
      detail?: string | null;
      code: string;
      lookback_days: number;
      event?: {
        event_date?: string;
        event_kind?: string;
        parent_np?: number | null;
        parent_np_yoy?: number | null;
        title?: string | null;
        predict_type?: string | null;
      } | null;
      model_scope?: string | null;
      ref_close?: number | null;
      ref_date?: string | null;
      fair_price?: number | null;
      premium_pct?: number | null;
      implied_fair_mcap?: number | null;
      expected_return_20d?: number | null;
      price_at_expected_20d?: number | null;
    }>(
      `/api/stocks/${encodeURIComponent(code)}/earnings-fair-anchor?lookback_days=${lookbackDays}`,
    ),
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
      pe_ttm?: number | null;
      pe_static?: number | null;
      pb?: number | null;
      ps_ttm?: number | null;
      market_cap?: number | null;
      float_market_cap?: number | null;
      valuation_date?: string | null;
    }>(`/api/stocks/${encodeURIComponent(code)}/snapshot${q}`);
  },
  /** 近 N 年年报主要财务指标 + 季报/中报 + 业绩预告/快报 */
  financials: (code: string, years = 5) =>
    request<StockFinancials>(
      `/api/stocks/${encodeURIComponent(code)}/financials?years=${years}`,
    ),
  /** 个股近期财务公告（与披露页同源） */
  stockDisclosures: (code: string, aroundDate?: string, lookbackDays = 21) => {
    const params = new URLSearchParams({ lookback_days: String(lookbackDays) });
    if (aroundDate) params.set("around_date", aroundDate);
    return request<{
      code: string;
      name: string;
      start_date: string;
      end_date: string;
      total: number;
      items: Array<{
        code: string;
        name: string;
        category: string;
        category_label: string;
        notice_type: string;
        title: string;
        notice_date: string;
        url?: string | null;
      }>;
    }>(`/api/stocks/${encodeURIComponent(code)}/disclosures?${params}`);
  },
  /** @deprecated 同 financials */
  parentProfit: (code: string, years = 5) =>
    request<StockFinancials>(
      `/api/stocks/${encodeURIComponent(code)}/financials?years=${years}`,
    ),
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
  /** limit=0 表示全部命中（相似度降序）；可传 start/end 查区间 */
  patternTop: (
    patternId: string,
    tradeDate?: string,
    limit = 0,
    range?: { start?: string; end?: string },
  ) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (range?.start) params.set("start_date", range.start);
    if (range?.end) params.set("end_date", range.end);
    if (!range?.start && !range?.end && tradeDate) {
      params.set("trade_date", tradeDate);
    }
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
    start_date?: string;
    end_date?: string;
    pattern_ids?: string[];
    force?: boolean;
  }) =>
    request<Job>("/api/patterns/scan", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  eventStatsRun: (body: {
    pattern_id: string;
    start: string;
    end: string;
    codes?: string;
    universe?: {
      kind: string;
      codes?: string[];
      pool?: string;
      profile?: string;
      target_samples?: number;
      max_total?: number;
      per_cluster?: number;
      min_cluster_size?: number;
      seed?: number;
      prefer?: string;
    };
    horizon_bars?: number;
    return_horizons?: number[];
    dedup_policy?: string;
    calendar?: string;
    day_concurrency?: number;
    match_concurrency?: number;
    observe_concurrency?: number;
  }) =>
    request<Job>("/api/event-stats/runs", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  eventStatsRuns: (limit = 10, offset = 0) =>
    request<{ total: number; limit: number; offset: number; runs: EventStatsRun[] }>(
      `/api/event-stats/runs?limit=${limit}&offset=${offset}`,
    ),
  eventStatsRunDetail: (runId: string) =>
    request<EventStatsRun>(`/api/event-stats/runs/${encodeURIComponent(runId)}`),
  cancelEventStatsRun: (runId: string) =>
    request<EventStatsRun & { cancel_mode?: string; job_id?: string }>(
      `/api/event-stats/runs/${encodeURIComponent(runId)}/cancel`,
      { method: "POST" },
    ),
  deleteEventStatsRun: (runId: string) =>
    request<{ ok: boolean; run_id: string }>(
      `/api/event-stats/runs/${encodeURIComponent(runId)}`,
      { method: "DELETE" },
    ),
  eventStatsEvents: (
    runId: string,
    opts?: { limit?: number; offset?: number; order_by?: string; desc?: boolean },
  ) => {
    const params = new URLSearchParams({
      limit: String(opts?.limit ?? 100),
      offset: String(opts?.offset ?? 0),
      order_by: opts?.order_by ?? "entry_similarity",
      desc: String(opts?.desc ?? true),
    });
    return request<{ total: number; events: EventStatsEvent[] }>(
      `/api/event-stats/runs/${encodeURIComponent(runId)}/events?${params}`,
    );
  },
  job: (jobId: string) => request<Job>(`/api/jobs/${encodeURIComponent(jobId)}`),
  cancelJob: (jobId: string) =>
    request<Job>(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" }),
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

  /** Earnings Event Analytics */
  eeaModels: (panelTag?: string) => {
    const q = panelTag ? `?panel_tag=${encodeURIComponent(panelTag)}` : "";
    return request<
      Array<{
        model_id: string;
        fitted_at: string;
        panel_tag: string;
        model_scope: string;
        cluster_mode: string;
        cluster_id?: number | null;
        backend_id: string;
        estimator_id: string;
        n_samples: number;
        metrics: Record<string, number | null>;
        feature_cols: string[];
      }>
    >(`/api/analysis/earnings-events/models${q}`);
  },
  eeaModelDetail: (modelId: string) =>
    request<Record<string, unknown>>(
      `/api/analysis/earnings-events/models/${encodeURIComponent(modelId)}`,
    ),
  eeaPanelSummary: (panelTag = "default") =>
    request<{
      panel_tag: string;
      n_rows: number;
      n_with_ret_20d: number;
      n_with_ey: number;
      kinds: Record<string, number>;
    }>(`/api/analysis/earnings-events/panel/summary?panel_tag=${encodeURIComponent(panelTag)}`),
  eeaPanelByCluster: (panelTag = "default") =>
    request<{
      panel_tag: string;
      n_rows: number;
      global_mean_ret_20d: number | null;
      clusters: Array<{
        cluster_id: number;
        n: number;
        up_rate_20d: number | null;
        mean_ret_5d: number | null;
        mean_ret_10d: number | null;
        mean_ret_20d: number | null;
        mean_ey_event: number | null;
        excess_ret_20d: number | null;
      }>;
    }>(`/api/analysis/earnings-events/panel/by-cluster?panel_tag=${encodeURIComponent(panelTag)}`),
  eeaBuildPanel: (body: {
    start_date?: string;
    end_date?: string;
    panel_tag?: string;
    build_events?: boolean;
    main_only?: boolean;
    cluster_run_id?: string;
  }) =>
    request<Record<string, unknown>>("/api/analysis/earnings-events/build-panel", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  eeaFit: (body?: {
    panel_tag?: string;
    scopes?: string[];
    cluster_modes?: string[];
  }) =>
    request<Record<string, unknown>>("/api/analysis/earnings-events/fit", {
      method: "POST",
      body: JSON.stringify(body || {}),
    }),
  eeaScore: (body: {
    code: string;
    event_kind: string;
    parent_np: number;
    parent_np_yoy?: number | null;
    report_period?: string | null;
    as_of?: string | null;
    model_scope?: string;
    use_cluster?: boolean;
    model_id?: string | null;
    panel_tag?: string;
  }) =>
    request<{
      ok: boolean;
      unavailable_reason?: string;
      code?: string;
      as_of?: string;
      event_kind?: string;
      features?: Record<string, number | string | null>;
      prediction?: {
        expected_return_5d?: number | null;
        expected_return_10d?: number | null;
        expected_return_20d?: number | null;
        fair_ey?: number | null;
        fair_pe?: number | null;
        implied_fair_mcap?: number | null;
        premium_pct?: number | null;
        prediction_meta?: Record<string, unknown>;
      };
      score?: {
        mispricing_score?: number | null;
        confidence?: number | null;
        percentile?: number | null;
      };
      model?: Record<string, unknown>;
      explain?: {
        feature_contributions?: Array<{
          key: string;
          value: number;
          coef: number;
          contrib: number;
          rank: number;
        }>;
        natural_language?: string | null;
      };
    }>("/api/analysis/earnings-events/score", {
      method: "POST",
      body: JSON.stringify({ ...body, with_explain: true }),
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
  display_name_en?: string;
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
  display_name_en?: string;
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
  display_name_en?: string;
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
  /** 中文短名（编辑器展示用） */
  label?: string;
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
  /** 信号日后第 1/3/5 个交易日相对信号收盘的前复权收益 */
  return_1?: number | null;
  return_3?: number | null;
  return_5?: number | null;
};

export type EarningsGuidanceMetric = {
  metric: string;
  predict_type?: string | null;
  value_lower?: number | null;
  value_upper?: number | null;
  value_mid?: number | null;
  yoy_lower?: number | null;
  yoy_upper?: number | null;
  yoy_mid?: number | null;
  content?: string | null;
  reason?: string | null;
  preyear_value?: number | null;
};

export type EarningsGuidance = {
  kind: "forecast" | "express" | string;
  report_period: string;
  report_name?: string;
  notice_date?: string | null;
  metrics?: EarningsGuidanceMetric[];
  revenue?: number | null;
  revenue_yoy?: number | null;
  parent_net_profit?: number | null;
  parent_net_profit_yoy?: number | null;
  roe?: number | null;
  /** 预告/快报公告日 PE(TTM) */
  pe_ttm?: number | null;
  pe_static?: number | null;
  valuation_date?: string | null;
};

export type StockFinancials = {
  code: string;
  name: string;
  source: string;
  years: number;
  note?: string;
  points: Array<{
    year: number;
    report_period: string;
    report_name?: string;
    notice_date?: string | null;
    is_annual?: boolean;
    revenue?: number | null;
    revenue_yoy?: number | null;
    parent_net_profit?: number | null;
    parent_net_profit_yoy?: number | null;
    ded_net_profit?: number | null;
    ded_net_profit_yoy?: number | null;
    roe?: number | null;
    yoy?: number | null;
    /** 报告公告日 PE(TTM) */
    pe_ttm?: number | null;
    pe_static?: number | null;
    valuation_date?: string | null;
  }>;
  guidance?: EarningsGuidance[];
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
  params?: Record<string, unknown> | null;
  cancel_requested?: boolean;
};

export type EventStatsRun = {
  run_id: string;
  entry_pattern_id: string;
  entry_version: string;
  outcome_mode: string;
  universe_spec: Record<string, unknown>;
  start_date: string;
  end_date: string;
  horizon_bars: number;
  return_horizons: number[];
  dedup_policy?: string;
  calendar?: string;
  status: string;
  event_count?: number | null;
  summary?: Record<string, unknown> | null;
  duration_ms?: number | null;
  error_msg?: string | null;
  aggregation_version?: string;
  engine_config_hash?: string;
  job_id?: string | null;
  progress?: number | null;
  progress_msg?: string | null;
  job_alive?: boolean;
  live_job?: Job | null;
  created_at?: string | null;
};

export type EventStatsEvent = {
  event_id: number;
  code: string;
  signal_date: string;
  entry_similarity: number;
  tags?: string[];
  return_1?: number | null;
  return_3?: number | null;
  return_5?: number | null;
  return_10?: number | null;
  return_20?: number | null;
  return_60?: number | null;
  return_horizon?: number | null;
  mfe?: number | null;
  mae?: number | null;
  max_drawdown?: number | null;
  volatility?: number | null;
  bull_ratio?: number | null;
  forward_status: string;
  match_explain?: Record<string, unknown> | null;
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

import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type EventStatsRun, type Job } from "@/api/client";
import { JobProgress } from "@/components/JobProgress";
import { NumberInput } from "@/components/NumberInput";
import { Pager } from "@/components/Pager";
import { StockPicker } from "@/components/StockPicker";
import {
  formatJobParams,
  formatMetricValue,
  formatUniverseSpec,
  STATUS_LABELS,
  statsOf,
} from "@/lib/eventStatsLabels";
import {
  buildPatternMetaMap,
  lookupPatternMeta,
  patternLabel,
} from "@/lib/patternLabels";
import {
  ALL_START,
  CLUSTER_PROFILES,
  PAGE_SIZE_OPTIONS,
  RANGE_PRESETS,
  buildRerunBody,
  detectPreset,
  formatCreatedAt,
  runToProgressJob,
  shiftYears,
  type RangePreset,
  type UniverseMode,
} from "@/lib/eventStatsHelpers";

/** 事件统计任务台：发起（可折叠）+ 分页列表 */
export function EventStatsPage() {
  const [params] = useSearchParams();
  const legacyRun = params.get("run");
  if (legacyRun) {
    return <Navigate to={`/event-stats/runs/${legacyRun}`} replace />;
  }
  return <EventStatsHome />;
}

function EventStatsHome() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const jobId = params.get("job") || null;
  const page = Math.max(1, Number(params.get("page") || "1") || 1);
  const pageSize = (PAGE_SIZE_OPTIONS as readonly number[]).includes(
    Number(params.get("pageSize") || 10),
  )
    ? Number(params.get("pageSize") || 10)
    : 10;

  const [formOpen, setFormOpen] = useState(
    () => !!(params.get("cluster") || params.get("codes") || params.get("new")),
  );
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const [patternId, setPatternId] = useState(params.get("pattern") || "RANGE_BREAKOUT");
  const [start, setStart] = useState(params.get("start") || "");
  const [end, setEnd] = useState(params.get("end") || "");
  const [rangePreset, setRangePreset] = useState<RangePreset>(
    (params.get("range") as RangePreset) || "1y",
  );
  const [universeMode, setUniverseMode] = useState<UniverseMode>(() => {
    if (params.get("cluster")) return "cluster";
    if (params.get("codes")) return "codes";
    if (params.get("universe") === "cluster_sample") return "cluster_sample";
    return "all";
  });
  const [codes, setCodes] = useState(params.get("codes") || "");
  const [clusterProfile, setClusterProfile] = useState(params.get("profile") || "pearson_w60");
  const [clusterId, setClusterId] = useState(params.get("cluster") || "");
  const [horizon, setHorizon] = useState(20);
  const [dayWorkers, setDayWorkers] = useState(6);
  const [matchWorkers, setMatchWorkers] = useState(8);
  const [observeWorkers, setObserveWorkers] = useState(8);
  const [sampleTarget, setSampleTarget] = useState(80);
  const [sampleSeed, setSampleSeed] = useState(42);
  const [samplePrefer, setSamplePrefer] = useState<"central" | "uniform">("central");

  const setJobInUrl = (id: string | null) => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (id) next.set("job", id);
        else next.delete("job");
        return next;
      },
      { replace: true },
    );
  };

  const patterns = useQuery({ queryKey: ["patterns-meta"], queryFn: api.patternsMeta });
  const patternMetaMap = useMemo(
    () => buildPatternMetaMap(patterns.data),
    [patterns.data],
  );
  const meta = useQuery({ queryKey: ["trading-day"], queryFn: api.tradingDay });
  const asOf = meta.data?.latest_trading_day || "";

  const runs = useQuery({
    queryKey: ["event-stats-runs", page, pageSize],
    queryFn: () => api.eventStatsRuns(pageSize, (page - 1) * pageSize),
    refetchInterval: (q) => {
      const rows = q.state.data?.runs || [];
      if (rows.some((r) => r.status === "RUNNING" || r.status === "PENDING")) return 1000;
      return jobId ? 2000 : false;
    },
  });

  const jobsList = useQuery({
    queryKey: ["jobs", "event-stats"],
    queryFn: () => api.jobs(50),
    refetchInterval: (q) => {
      const active = (q.state.data || []).some(
        (j) =>
          j.kind === "pattern.event_stats" &&
          (j.status === "PENDING" || j.status === "RUNNING"),
      );
      return active || !!jobId ? 1500 : false;
    },
  });

  useEffect(() => {
    if (jobId) return;
    const active = (jobsList.data || []).find(
      (j) =>
        j.kind === "pattern.event_stats" &&
        (j.status === "PENDING" || j.status === "RUNNING"),
    );
    if (active) setJobInUrl(active.job_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobsList.data, jobId]);

  const clustersList = useQuery({
    queryKey: ["clusters", clusterProfile],
    queryFn: () => api.clustersList(clusterProfile, true),
    enabled: universeMode === "cluster" || universeMode === "cluster_sample",
  });

  const clusterDetail = useQuery({
    queryKey: ["cluster-detail", clusterProfile, clusterId],
    queryFn: () => api.clusterDetail(Number(clusterId), clusterProfile, 5000),
    enabled: universeMode === "cluster" && !!clusterId && Number.isFinite(Number(clusterId)),
  });

  useEffect(() => {
    if (universeMode !== "cluster" || !clusterId) return;
    const detail = clusterDetail.data;
    if (!detail?.members?.length) return;
    if (String(detail.cluster.cluster_id) !== String(clusterId)) return;
    setCodes(detail.members.map((m) => m.code).join(","));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [universeMode, clusterId, clusterDetail.data?.cluster?.cluster_id]);

  const applyPreset = (preset: RangePreset, endYmd: string) => {
    if (!endYmd && preset !== "custom") return;
    setRangePreset(preset);
    if (preset === "custom") return;
    setEnd(endYmd);
    if (preset === "all") {
      setStart(ALL_START);
      return;
    }
    const years = preset === "1y" ? 1 : preset === "3y" ? 3 : 5;
    setStart(shiftYears(endYmd, years));
  };

  useEffect(() => {
    if (!asOf) return;
    const urlStart = params.get("start");
    const urlEnd = params.get("end");
    if (urlStart || urlEnd) {
      const s = urlStart || start;
      const e = urlEnd || end || asOf;
      if (urlStart && !start) setStart(urlStart);
      if (urlEnd && !end) setEnd(urlEnd);
      setRangePreset(detectPreset(s, e, asOf));
      return;
    }
    if (!start && !end) applyPreset("1y", asOf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asOf]);

  const job = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.job(jobId!),
    enabled: !!jobId,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "PENDING" || s === "RUNNING" || q.state.data?.cancel_requested ? 400 : false;
    },
  });

  const listRunning = useMemo(
    () =>
      (runs.data?.runs || []).find((r) => r.status === "RUNNING" || r.status === "PENDING") ||
      null,
    [runs.data?.runs],
  );

  const progressRunId = listRunning?.run_id || "";
  const progressRun = useQuery({
    queryKey: ["event-stats-run", progressRunId],
    queryFn: () => api.eventStatsRunDetail(progressRunId),
    enabled: !!progressRunId,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "PENDING" || s === "RUNNING" ? 500 : false;
    },
  });

  const liveJob =
    job.data ??
    (jobsList.data || []).find((j) => j.job_id === jobId) ??
    (jobsList.data || []).find(
      (j) =>
        j.kind === "pattern.event_stats" &&
        (j.status === "PENDING" || j.status === "RUNNING"),
    ) ??
    progressRun.data?.live_job ??
    null;

  useEffect(() => {
    if (!jobId) return;
    const st = liveJob?.status;
    if (!st || st === "PENDING" || st === "RUNNING") return;
    const rid =
      (liveJob?.result?.run_id as string | undefined) ||
      (liveJob?.params?.run_id as string | undefined);
    void qc.invalidateQueries({ queryKey: ["event-stats-runs"] });
    void qc.invalidateQueries({ queryKey: ["jobs", "event-stats"] });
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete("job");
        return next;
      },
      { replace: true },
    );
    if (st === "SUCCESS" && rid) {
      navigate(`/event-stats/runs/${rid}`);
    }
  }, [jobId, liveJob?.status, liveJob?.result, liveJob?.params, qc, setParams, navigate]);

  const progressSourceRun =
    progressRun.data &&
    (progressRun.data.status === "RUNNING" || progressRun.data.status === "PENDING")
      ? progressRun.data
      : listRunning;

  const progressJob: Job | null = useMemo(() => {
    if (
      liveJob &&
      (liveJob.status === "PENDING" || liveJob.status === "RUNNING") &&
      !(progressSourceRun && progressSourceRun.job_alive === false)
    ) {
      const liveRid =
        (liveJob.params?.run_id as string | undefined) ||
        (liveJob.result?.run_id as string | undefined);
      if (!progressSourceRun || !liveRid || liveRid === progressSourceRun.run_id) {
        return liveJob;
      }
    }
    if (progressSourceRun) return runToProgressJob(progressSourceRun);
    return null;
  }, [liveJob, progressSourceRun]);

  const progressRunKey =
    progressSourceRun?.run_id ||
    (progressJob?.params?.run_id as string | undefined) ||
    progressJob?.job_id ||
    null;

  const codeCount = useMemo(
    () =>
      codes
        .split(/[,，\s]+/)
        .map((c) => c.trim())
        .filter(Boolean).length,
    [codes],
  );

  const clusterOptions = useMemo(() => {
    const rows = [...(clustersList.data?.clusters || [])];
    rows.sort((a, b) => b.size - a.size || a.cluster_id - b.cluster_id);
    return rows;
  }, [clustersList.data?.clusters]);

  const buildRunBodyFromForm = () => {
    if (universeMode === "cluster_sample") {
      return {
        pattern_id: patternId,
        start,
        end,
        universe: {
          kind: "cluster_sample" as const,
          profile: clusterProfile,
          target_samples: sampleTarget,
          seed: sampleSeed,
          prefer: samplePrefer,
        },
        horizon_bars: horizon,
        dedup_policy: "cooldown_h",
        day_concurrency: dayWorkers,
        match_concurrency: matchWorkers,
        observe_concurrency: observeWorkers,
      };
    }
    const useCodes =
      universeMode === "codes" || universeMode === "cluster"
        ? codes.trim() || undefined
        : undefined;
    if ((universeMode === "codes" || universeMode === "cluster") && !useCodes) {
      throw new Error(
        universeMode === "cluster" ? "请先选择相关簇（或等待成员加载）" : "请至少选择一只股票",
      );
    }
    return {
      pattern_id: patternId,
      start,
      end,
      codes: useCodes,
      horizon_bars: horizon,
      dedup_policy: "cooldown_h",
      day_concurrency: dayWorkers,
      match_concurrency: matchWorkers,
      observe_concurrency: observeWorkers,
    };
  };

  const runMut = useMutation({
    mutationFn: () => api.eventStatsRun(buildRunBodyFromForm()),
    onSuccess: (j) => {
      setJobInUrl(j.job_id);
      setFormOpen(false);
      void qc.invalidateQueries({ queryKey: ["jobs", "event-stats"] });
      void qc.invalidateQueries({ queryKey: ["event-stats-runs"] });
    },
  });

  const rerunMut = useMutation({
    mutationFn: (r: EventStatsRun) =>
      api.eventStatsRun(
        buildRerunBody(r, { day: dayWorkers, match: matchWorkers, observe: observeWorkers }),
      ),
    onSuccess: (j) => {
      setJobInUrl(j.job_id);
      void qc.invalidateQueries({ queryKey: ["jobs", "event-stats"] });
      void qc.invalidateQueries({ queryKey: ["event-stats-runs"] });
    },
  });

  const deleteMut = useMutation({
    mutationFn: (runId: string) => api.deleteEventStatsRun(runId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["event-stats-runs"] });
    },
  });

  const running =
    runMut.isPending ||
    rerunMut.isPending ||
    liveJob?.status === "PENDING" ||
    liveJob?.status === "RUNNING" ||
    !!progressSourceRun;

  const canRun =
    !!start &&
    !!end &&
    !running &&
    !(universeMode === "cluster" && (!clusterId || clusterDetail.isFetching)) &&
    !(universeMode === "codes" && codeCount < 1) &&
    !(universeMode === "cluster" && codeCount < 1) &&
    !(universeMode === "cluster_sample" && !clusterProfile);

  const total = runs.data?.total ?? 0;

  const setPage = (p: number) => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("page", String(Math.max(1, p)));
        next.set("pageSize", String(pageSize));
        return next;
      },
      { replace: true },
    );
  };

  const setPageSize = (size: number) => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("pageSize", String(size));
        next.set("page", "1");
        return next;
      },
      { replace: true },
    );
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>事件统计</h1>
          <p className="muted">发现形态命中 → 度量远期表现 → 聚合统计（不做策略打分）</p>
        </div>
        <div className="es-actions">
          <Link to="/event-stats/compare" className="btn">
            任务对比
          </Link>
          <button
            type="button"
            className="btn primary"
            onClick={() => setFormOpen((v) => !v)}
          >
            {formOpen ? "收起表单" : "新建统计"}
          </button>
        </div>
      </div>

      <JobProgress
        jobId={progressRunKey || jobId}
        job={progressJob}
        title="运行中"
        cancellable
        configSummary={
          progressJob?.params
            ? formatJobParams(progressJob.params)
            : progressSourceRun
              ? formatJobParams({
                  pattern_id: progressSourceRun.entry_pattern_id,
                  start: progressSourceRun.start_date,
                  end: progressSourceRun.end_date,
                  universe: progressSourceRun.universe_spec,
                  horizon_bars: progressSourceRun.horizon_bars,
                })
              : ""
        }
        hint={
          progressSourceRun?.job_alive === false &&
          (progressSourceRun.status === "RUNNING" || progressSourceRun.status === "PENDING")
            ? "后台进程已不存在。可取消以清理记录。"
            : undefined
        }
        pending={runMut.isPending || (!!progressJob && !progressJob.status)}
        onCancelRequest={
          progressRunKey ? () => api.cancelEventStatsRun(progressRunKey) : undefined
        }
        onCancelled={() => {
          void qc.invalidateQueries({ queryKey: ["job", jobId] });
          void qc.invalidateQueries({ queryKey: ["jobs", "event-stats"] });
          void qc.invalidateQueries({ queryKey: ["event-stats-runs"] });
          setJobInUrl(null);
        }}
      />

      {(runMut.error || rerunMut.error || deleteMut.error || progressJob?.error) && (
        <div className="error-box">
          {(runMut.error as Error)?.message ||
            (rerunMut.error as Error)?.message ||
            (deleteMut.error as Error)?.message ||
            progressJob?.error}
        </div>
      )}

      {formOpen && (
        <div className="panel" style={{ marginBottom: "1rem", padding: "1rem" }}>
          <div className="es-launch-head">
            <strong>发起统计</strong>
            <span className="muted" style={{ fontSize: "0.82rem" }}>
              完成后可在下方列表查看，点「查看」进入详情
            </span>
          </div>

          <p className="es-section-label">基础</p>
          <div className="toolbar" style={{ flexWrap: "wrap" }}>
            <label>
              Pattern
              <select value={patternId} onChange={(e) => setPatternId(e.target.value)}>
                {(patterns.data || []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {patternLabel(p.id, p)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              观测窗
              <NumberInput min={1} max={120} value={horizon} onChange={setHorizon} style={{ width: 72 }} />
            </label>
            <label>
              时间范围
              <select
                value={rangePreset}
                onChange={(e) => {
                  const p = e.target.value as RangePreset;
                  if (p === "custom") {
                    setRangePreset("custom");
                    return;
                  }
                  applyPreset(p, asOf || end);
                }}
              >
                {RANGE_PRESETS.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              开始
              <input
                type="date"
                value={start}
                onChange={(e) => {
                  setRangePreset("custom");
                  setStart(e.target.value);
                }}
              />
            </label>
            <label>
              结束
              <input
                type="date"
                value={end}
                onChange={(e) => {
                  setRangePreset("custom");
                  setEnd(e.target.value);
                }}
              />
            </label>
          </div>

          <p className="es-section-label">宇宙</p>
          <div className="toolbar" style={{ flexWrap: "wrap" }}>
            <label>
              模式
              <select
                value={universeMode}
                onChange={(e) => {
                  const m = e.target.value as UniverseMode;
                  setUniverseMode(m);
                  if (m === "all" || m === "cluster_sample") {
                    setCodes("");
                    setClusterId("");
                  }
                  if (m === "codes") setClusterId("");
                }}
              >
                <option value="all">全市场</option>
                <option value="codes">自选股票</option>
                <option value="cluster">相关簇</option>
                <option value="cluster_sample">簇分层抽样</option>
              </select>
            </label>
          </div>

          {universeMode === "codes" && (
            <div style={{ marginTop: "0.55rem" }}>
              <StockPicker mode="multi" value={codes} onChange={setCodes} />
              <p className="muted" style={{ margin: "0.35rem 0 0", fontSize: "0.82rem" }}>
                已选 {codeCount} 只
              </p>
            </div>
          )}

          {universeMode === "cluster" && (
            <div className="toolbar" style={{ marginTop: "0.55rem", flexWrap: "wrap" }}>
              <label>
                画像
                <select
                  value={clusterProfile}
                  onChange={(e) => {
                    setClusterProfile(e.target.value);
                    setClusterId("");
                    setCodes("");
                  }}
                >
                  {CLUSTER_PROFILES.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </label>
              <label style={{ minWidth: 240 }}>
                簇
                <select
                  value={clusterId}
                  onChange={(e) => {
                    setClusterId(e.target.value);
                    if (!e.target.value) setCodes("");
                  }}
                  disabled={clustersList.isFetching}
                >
                  <option value="">
                    {clustersList.isFetching ? "加载中…" : "选择簇…"}
                  </option>
                  {clusterOptions.map((c) => (
                    <option key={c.cluster_id} value={String(c.cluster_id)}>
                      {c.label} · {c.size} 只
                    </option>
                  ))}
                </select>
              </label>
              {codeCount > 0 && (
                <span className="muted" style={{ fontSize: "0.82rem" }}>
                  成员 {codeCount} 只
                </span>
              )}
            </div>
          )}

          {universeMode === "cluster_sample" && (
            <div className="toolbar" style={{ marginTop: "0.55rem", flexWrap: "wrap" }}>
              <label>
                画像
                <select value={clusterProfile} onChange={(e) => setClusterProfile(e.target.value)}>
                  {CLUSTER_PROFILES.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </label>
              <label title="算法按簇分层轮询抽取，尽量覆盖更多簇；每簇只数自动决定">
                大概样本数
                <NumberInput
                  min={1}
                  max={2000}
                  value={sampleTarget}
                  onChange={setSampleTarget}
                  style={{ width: 80 }}
                />
              </label>
              <label>
                偏好
                <select
                  value={samplePrefer}
                  onChange={(e) => setSamplePrefer(e.target.value as "central" | "uniform")}
                >
                  <option value="central">偏中心</option>
                  <option value="uniform">均匀</option>
                </select>
              </label>
              <label>
                种子
                <NumberInput min={0} max={999999} value={sampleSeed} onChange={setSampleSeed} style={{ width: 80 }} />
              </label>
              <button type="button" className="btn" onClick={() => setSampleSeed(Math.floor(Math.random() * 100000))}>
                换种子
              </button>
              <span className="muted" style={{ fontSize: "0.8rem", alignSelf: "center" }}>
                每簇抽几只由算法自动分配
              </span>
            </div>
          )}

          <p className="es-section-label">
            <button
              type="button"
              className="btn"
              style={{ fontSize: "0.78rem", padding: "0.15rem 0.5rem" }}
              onClick={() => setAdvancedOpen((v) => !v)}
            >
              {advancedOpen ? "收起高级" : "高级 · 并发"}
            </button>
          </p>
          {advancedOpen && (
            <div className="toolbar" style={{ flexWrap: "wrap" }}>
              <label title="按交易日并行">
                日并发
                <NumberInput min={1} max={16} value={dayWorkers} onChange={setDayWorkers} style={{ width: 64 }} />
              </label>
              <label title="日内股票匹配并行">
                匹配并发
                <NumberInput min={1} max={16} value={matchWorkers} onChange={setMatchWorkers} style={{ width: 64 }} />
              </label>
              <label title="远期指标计算并行">
                Observe并发
                <NumberInput min={1} max={32} value={observeWorkers} onChange={setObserveWorkers} style={{ width: 64 }} />
              </label>
            </div>
          )}

          <div style={{ marginTop: "0.85rem" }}>
            <button
              className="btn primary"
              type="button"
              disabled={!canRun}
              onClick={() => runMut.mutate()}
            >
              {running ? "运行中…" : "开始统计"}
            </button>
          </div>
        </div>
      )}

      <div className="panel" style={{ marginBottom: "0.85rem" }}>
        <div className="panel-head" style={{ justifyContent: "space-between" }}>
          <span>任务列表</span>
          <span className="muted" style={{ fontWeight: 400, fontSize: "0.82rem" }}>
            共 {total} 条
          </span>
        </div>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>时间</th>
                <th>策略</th>
                <th>区间</th>
                <th>宇宙</th>
                <th>结果</th>
                <th>状态</th>
                <th style={{ width: 168 }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {(runs.data?.runs || []).map((r) => {
                const linkedJob = (jobsList.data || []).find(
                  (j) =>
                    j.kind === "pattern.event_stats" &&
                    (j.job_id === r.job_id ||
                      j.params?.run_id === r.run_id ||
                      j.result?.run_id === r.run_id),
                );
                const jobAlive =
                  !!linkedJob &&
                  (linkedJob.status === "PENDING" || linkedJob.status === "RUNNING");
                const isActive = r.status === "PENDING" || r.status === "RUNNING";
                const r5 = statsOf(r.summary, "return_5").mean;
                const pMeta = lookupPatternMeta(patternMetaMap, r.entry_pattern_id);
                const label = `${patternLabel(r.entry_pattern_id, pMeta)} ${r.start_date}→${r.end_date}`;
                return (
                  <tr
                    key={r.run_id}
                    style={{ cursor: "pointer" }}
                    onClick={() => navigate(`/event-stats/runs/${r.run_id}`)}
                  >
                    <td className="muted mono" style={{ fontSize: "0.8rem" }}>
                      {formatCreatedAt(r.created_at)}
                    </td>
                    <td>
                      {patternLabel(r.entry_pattern_id, pMeta)}
                      <span className="muted" style={{ fontSize: "0.75rem" }}>
                        {" "}
                        <span className="mono">{r.entry_pattern_id}</span> v{r.entry_version}
                      </span>
                    </td>
                    <td className="muted mono" style={{ fontSize: "0.8rem" }}>
                      {r.start_date} → {r.end_date}
                    </td>
                    <td className="muted" style={{ fontSize: "0.8rem" }}>
                      {formatUniverseSpec(r.universe_spec)}
                    </td>
                    <td className="mono" style={{ fontSize: "0.85rem" }}>
                      {r.event_count ?? "—"} 事件
                      {r.status === "SUCCESS" && r5 != null ? (
                        <span className="muted" style={{ display: "block", fontSize: "0.75rem" }}>
                          5日 {formatMetricValue("return_5", r5)}
                        </span>
                      ) : null}
                      {isActive && typeof r.progress === "number" ? (
                        <span className="muted" style={{ display: "block", fontSize: "0.75rem" }}>
                          {(r.progress * 100).toFixed(1)}%
                        </span>
                      ) : null}
                    </td>
                    <td>
                      <span
                        className={`badge ${
                          r.status === "SUCCESS"
                            ? "ok"
                            : r.status === "FAILED" || r.status === "CANCELLED"
                              ? "fail"
                              : "warn"
                        }`}
                      >
                        {STATUS_LABELS[r.status] || r.status}
                      </span>
                    </td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <div className="es-actions">
                        <Link className="btn" to={`/event-stats/runs/${r.run_id}`}>
                          查看
                        </Link>
                        <button
                          type="button"
                          className="btn"
                          disabled={running}
                          onClick={() => {
                            if (
                              !window.confirm(
                                `确认按 ${r.run_id.slice(0, 8)}…（${label}）配置重新执行？`,
                              )
                            ) {
                              return;
                            }
                            rerunMut.mutate(r);
                          }}
                        >
                          重跑
                        </button>
                        <button
                          type="button"
                          className="btn"
                          disabled={jobAlive || deleteMut.isPending}
                          onClick={() => {
                            if (
                              !window.confirm(
                                `确认删除 ${r.run_id.slice(0, 8)}…？将删除全部事件，不可恢复。`,
                              )
                            ) {
                              return;
                            }
                            deleteMut.mutate(r.run_id);
                          }}
                        >
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {!runs.data?.runs?.length && (
                <tr>
                  <td colSpan={7} className="muted">
                    暂无任务。点击右上角「新建统计」开始。
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <Pager
          page={page}
          pageSize={pageSize}
          total={total}
          pageSizeOptions={PAGE_SIZE_OPTIONS}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
        />
      </div>
    </>
  );
}

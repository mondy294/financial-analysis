import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  type TaskParamSpec,
  type TaskSpec,
} from "@/api/client";
import { StockPicker } from "@/components/StockPicker";

function defaultParams(task: TaskSpec, tradeDate: string): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const p of task.params) {
    if (p.type === "date") {
      out[p.name] = tradeDate || p.default || "";
    } else if (p.default !== undefined && p.default !== null) {
      out[p.name] = p.default;
    } else if (p.type === "bool") {
      out[p.name] = false;
    } else {
      out[p.name] = "";
    }
  }
  return out;
}

export function SystemPage() {
  const qc = useQueryClient();
  const doctor = useQuery({ queryKey: ["doctor"], queryFn: api.doctor });
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const day = useQuery({ queryKey: ["trading-day"], queryFn: api.tradingDay });
  const tasksQ = useQuery({
    queryKey: ["system-tasks"],
    queryFn: api.systemTasks,
    refetchInterval: 4000,
  });
  const jobs = useQuery({
    queryKey: ["jobs-all"],
    queryFn: () => api.jobs(30),
    refetchInterval: 2000,
  });
  const cacheQ = useQuery({
    queryKey: ["cache-stats"],
    queryFn: api.cacheStats,
  });

  const tradeDate =
    day.data?.latest_trading_day || day.data?.pattern_latest_date || "";

  const [paramMap, setParamMap] = useState<Record<string, Record<string, unknown>>>({});
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!tasksQ.data || !tradeDate) return;
    setParamMap((prev) => {
      const next = { ...prev };
      for (const g of tasksQ.data.groups) {
        for (const t of g.tasks) {
          if (!next[t.id]) next[t.id] = defaultParams(t, tradeDate);
        }
      }
      return next;
    });
  }, [tasksQ.data, tradeDate]);

  const heavyRunning = tasksQ.data?.heavy_running;
  const busy = !!heavyRunning;

  const runMut = useMutation({
    mutationFn: ({ taskId, params }: { taskId: string; params: Record<string, unknown> }) =>
      api.runSystemTask(taskId, params),
    onSuccess: (job) => {
      setErr(null);
      setOkMsg(`已提交 ${job.kind} · ${job.job_id}`);
      setActiveJobId(job.job_id);
      qc.invalidateQueries({ queryKey: ["jobs-all"] });
      qc.invalidateQueries({ queryKey: ["system-tasks"] });
      qc.invalidateQueries({ queryKey: ["doctor"] });
    },
    onError: (e: Error) => {
      setOkMsg(null);
      setErr(e.message);
      qc.invalidateQueries({ queryKey: ["system-tasks"] });
    },
  });

  const onRun = (task: TaskSpec) => {
    if (task.dangerous) {
      const drop = !!paramMap[task.id]?.drop_first;
      const msg = drop
        ? "确认执行 init-db 且 drop_first=true？将删除全部表数据！"
        : "确认执行 init-db（建表/补种子，默认不删表）？";
      if (!window.confirm(msg)) return;
    }
    if (busy && task.heavy) {
      setErr(
        `已有重任务运行中: ${heavyRunning?.kind} (${heavyRunning?.job_id})，请等待完成`,
      );
      return;
    }
    setErr(null);
    runMut.mutate({ taskId: task.id, params: paramMap[task.id] || {} });
  };

  const setParam = (taskId: string, name: string, value: unknown) => {
    setParamMap((prev) => ({
      ...prev,
      [taskId]: { ...(prev[taskId] || {}), [name]: value },
    }));
  };

  const highlighted = useMemo(() => activeJobId, [activeJobId]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>系统</h1>
          <p className="muted">健康检查、批处理任务与运行状态</p>
        </div>
      </div>

      <div className="cards">
        <div className="card">
          <div className="label">API</div>
          <div className="value" style={{ fontSize: "1.1rem" }}>
            <span className={`badge ${health.data?.status === "ok" ? "ok" : "fail"}`}>
              {health.data?.status || "…"}
            </span>{" "}
            <span className="mono muted">{health.data?.version}</span>
          </div>
        </div>
        <div className="card">
          <div className="label">DB</div>
          <div className="value">
            <span className={`badge ${doctor.data?.db_ok ? "ok" : "fail"}`}>
              {doctor.data?.db_ok ? "OK" : "FAIL"}
            </span>
          </div>
        </div>
        <div className="card">
          <div className="label">股票数</div>
          <div className="value mono">{doctor.data?.stock_count ?? "—"}</div>
        </div>
        <div className="card">
          <div className="label">K 线最新</div>
          <div className="value mono" style={{ fontSize: "1.1rem" }}>
            {doctor.data?.kline_latest || "—"}
          </div>
        </div>
        <div className="card">
          <div className="label">特征最新</div>
          <div className="value mono" style={{ fontSize: "1.1rem" }}>
            {doctor.data?.feature_latest || "—"}
          </div>
        </div>
        <div className="card">
          <div className="label">Pattern 最新</div>
          <div className="value mono" style={{ fontSize: "1.1rem" }}>
            {doctor.data?.pattern_latest || "—"}
          </div>
        </div>
      </div>

      {busy && (
        <div className="warn-box">
          重任务运行中：<span className="mono">{heavyRunning?.kind}</span> ·{" "}
          {heavyRunning?.job_id} · {heavyRunning?.message || heavyRunning?.status}
        </div>
      )}
      {okMsg && <div className="ok-box">{okMsg}</div>}
      {err && <div className="error-box">{err}</div>}

      <div className="page-head" style={{ marginTop: "0.5rem" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: "1.15rem" }}>任务控制台</h2>
          <p className="muted">拉数 / 特征 / 流水线 / Pattern / 关系 / 运维（异步 Job，不落 qs 子进程）</p>
        </div>
      </div>

      {tasksQ.isLoading && <div className="muted">加载任务目录…</div>}
      {tasksQ.error && (
        <div className="error-box">{(tasksQ.error as Error).message}</div>
      )}

      {(tasksQ.data?.groups || []).map((g) => (
        <section key={g.group} className="panel task-group">
          <div className="panel-head">{g.label}</div>
          <div className="task-list">
            {g.tasks.map((task) => (
              <article key={task.id} className="task-row">
                <div className="task-meta">
                  <h3>
                    {task.label}
                    {task.dangerous ? <span className="pill danger">危险</span> : null}
                    {task.heavy ? <span className="pill">heavy</span> : null}
                  </h3>
                  <p className="muted">{task.description}</p>
                  <p className="mono muted" style={{ fontSize: "0.78rem" }}>
                    {task.id}
                  </p>
                </div>
                <div className="task-controls">
                  <div className="toolbar">
                    {task.params.map((p) => (
                      <ParamField
                        key={p.name}
                        param={p}
                        value={paramMap[task.id]?.[p.name]}
                        onChange={(v) => setParam(task.id, p.name, v)}
                      />
                    ))}
                    <button
                      type="button"
                      className={`btn ${task.dangerous ? "danger" : "primary"}`}
                      disabled={runMut.isPending || (busy && task.heavy)}
                      onClick={() => onRun(task)}
                    >
                      运行
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>
      ))}

      <div className="panel" style={{ marginTop: "1rem" }}>
        <div className="panel-head">
          <span>缓存统计</span>
          <button
            type="button"
            className="btn tiny"
            onClick={() => qc.invalidateQueries({ queryKey: ["cache-stats"] })}
          >
            刷新
          </button>
        </div>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>namespace</th>
                <th>条数</th>
                <th>体积</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(cacheQ.data?.namespaces || {}).map(([ns, info]) => (
                <tr key={ns}>
                  <td className="mono">{ns}</td>
                  <td className="mono">{info.count ?? "—"}</td>
                  <td className="mono">
                    {info.volume_bytes != null
                      ? `${(info.volume_bytes / 1024 / 1024).toFixed(2)} MB`
                      : "—"}
                  </td>
                </tr>
              ))}
              {!Object.keys(cacheQ.data?.namespaces || {}).length && (
                <tr>
                  <td colSpan={3} className="muted">
                    缓存目录为空或未加载
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel" style={{ marginTop: "1rem" }}>
        <div className="panel-head">最近任务</div>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>ID</th>
                <th>类型</th>
                <th>状态</th>
                <th>进度</th>
                <th>信息</th>
                <th>创建时间</th>
              </tr>
            </thead>
            <tbody>
              {(jobs.data || []).map((j) => (
                <tr
                  key={j.job_id}
                  className={j.job_id === highlighted ? "row-active" : undefined}
                >
                  <td className="mono">{j.job_id}</td>
                  <td className="mono">{j.kind}</td>
                  <td>
                    <span
                      className={`badge ${
                        j.status === "SUCCESS" ? "ok" : j.status === "FAILED" ? "fail" : "warn"
                      }`}
                    >
                      {j.status}
                    </span>
                  </td>
                  <td className="mono">{(j.progress * 100).toFixed(3)}%</td>
                  <td className="muted">{j.error || j.message || "—"}</td>
                  <td className="mono muted">{j.created_at}</td>
                </tr>
              ))}
              {!jobs.data?.length && (
                <tr>
                  <td colSpan={6} className="muted">
                    尚无任务（进程内内存态，重启后清空）
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function ParamField({
  param,
  value,
  onChange,
}: {
  param: TaskParamSpec;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  if (param.type === "bool") {
    return (
      <label className="field check" style={{ marginBottom: 0 }}>
        <input
          type="checkbox"
          checked={!!value}
          onChange={(e) => onChange(e.target.checked)}
        />
        {param.label}
      </label>
    );
  }
  if (param.type === "codes") {
    return (
      <label style={{ minWidth: 220 }}>
        {param.label}
        <StockPicker
          mode="multi"
          value={value === undefined || value === null ? "" : String(value)}
          onChange={onChange}
          placeholder={param.help || "搜索添加股票"}
        />
      </label>
    );
  }
  const inputType =
    param.type === "date" ? "date" : param.type === "int" || param.type === "float" ? "number" : "text";
  return (
    <label>
      {param.label}
      <input
        type={inputType}
        step={param.type === "float" ? "any" : undefined}
        value={value === undefined || value === null ? "" : String(value)}
        placeholder={param.help || ""}
        onChange={(e) => {
          const v = e.target.value;
          if (param.type === "int") onChange(v === "" ? "" : Number(v));
          else if (param.type === "float") onChange(v === "" ? "" : Number(v));
          else onChange(v);
        }}
        style={{ minWidth: param.type === "date" ? 140 : 110 }}
      />
    </label>
  );
}

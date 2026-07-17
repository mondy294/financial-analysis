import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

export function SystemPage() {
  const doctor = useQuery({ queryKey: ["doctor"], queryFn: api.doctor });
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const jobs = useQuery({
    queryKey: ["jobs-all"],
    queryFn: () => api.jobs(30),
    refetchInterval: 3000,
  });

  return (
    <>
      <div className="page-head">
        <div>
          <h1>系统</h1>
          <p className="muted">健康检查与任务状态</p>
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

      <div className="panel">
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
                <tr key={j.job_id}>
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
                  <td className="mono">{(j.progress * 100).toFixed(0)}%</td>
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

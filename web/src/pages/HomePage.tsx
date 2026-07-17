import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

export function HomePage() {
  const meta = useQuery({ queryKey: ["trading-day"], queryFn: api.tradingDay });
  const doctor = useQuery({ queryKey: ["doctor"], queryFn: api.doctor });
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: () => api.jobs(5) });
  const date = meta.data?.pattern_latest_date || meta.data?.latest_trading_day || undefined;
  const stats = useQuery({
    queryKey: ["pattern-stats", date],
    queryFn: () => api.patternStats(date),
    enabled: !!date,
  });
  const top = useQuery({
    queryKey: ["pattern-top-home", date],
    queryFn: () => api.patternTop("RANGE_BREAKOUT", date, 8),
    enabled: !!date,
  });

  const hitCount = stats.data
    ? Object.values(stats.data.stats).reduce(
        (n, s) => n + Object.values(s).reduce((a, b) => a + b, 0),
        0,
      )
    : null;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>工作台</h1>
          <p className="muted">最近交易日摘要 · Pattern / 选股 / 任务</p>
        </div>
        <div className="links-row">
          <Link className="btn primary" to="/patterns">
            Pattern 工作台
          </Link>
          <Link className="btn" to="/patterns/eval">
            单票评估
          </Link>
        </div>
      </div>

      <div className="cards">
        <div className="card">
          <div className="label">最近交易日</div>
          <div className="value mono">{meta.data?.latest_trading_day || "—"}</div>
        </div>
        <div className="card">
          <div className="label">Pattern 扫描日</div>
          <div className="value mono">{meta.data?.pattern_latest_date || "—"}</div>
        </div>
        <div className="card">
          <div className="label">当日命中</div>
          <div className="value mono">{hitCount ?? "—"}</div>
        </div>
        <div className="card">
          <div className="label">股票池</div>
          <div className="value mono">{doctor.data?.stock_count ?? "—"}</div>
        </div>
      </div>

      <div className="grid-2">
        <div className="panel">
          <div className="panel-head">
            RANGE_BREAKOUT Top
            <Link to="/patterns">查看全部</Link>
          </div>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>#</th>
                  <th>代码</th>
                  <th>相似度</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {(top.data || []).map((r) => (
                  <tr key={r.code}>
                    <td className="mono">{r.pattern_rank}</td>
                    <td>
                      <Link to={`/stocks/${r.code}?date=${r.trade_date}`}>
                        <span className="mono">{r.code}</span> {r.name}
                      </Link>
                    </td>
                    <td className="mono">{r.pattern_score.toFixed(1)}</td>
                    <td>
                      <Link to={`/patterns/eval?code=${r.code}&date=${r.trade_date}`}>eval</Link>
                    </td>
                  </tr>
                ))}
                {!top.data?.length && (
                  <tr>
                    <td colSpan={4} className="muted">
                      暂无榜单，可先触发扫描
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            最近任务
            <Link to="/system">系统</Link>
          </div>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>类型</th>
                  <th>状态</th>
                  <th>信息</th>
                </tr>
              </thead>
              <tbody>
                {(jobs.data || []).map((j) => (
                  <tr key={j.job_id}>
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
                    <td className="muted">{j.message || j.error || j.job_id}</td>
                  </tr>
                ))}
                {!jobs.data?.length && (
                  <tr>
                    <td colSpan={3} className="muted">
                      尚无任务
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}

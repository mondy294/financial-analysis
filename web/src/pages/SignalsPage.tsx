import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

export function SignalsPage() {
  const meta = useQuery({ queryKey: ["trading-day"], queryFn: api.tradingDay });
  const [date, setDate] = useState("");

  useEffect(() => {
    if (!date && meta.data?.latest_trading_day) setDate(meta.data.latest_trading_day);
  }, [meta.data, date]);

  const signals = useQuery({
    queryKey: ["signals", date],
    queryFn: () => api.signals(date || undefined, 100),
    enabled: !!date,
  });

  return (
    <>
      <div className="page-head">
        <div>
          <h1>选股信号</h1>
          <p className="muted">策略命中与评分（落库结果）</p>
        </div>
        <div className="toolbar">
          <label>
            交易日
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
        </div>
      </div>

      <div className="panel">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>代码</th>
                <th>评分</th>
                <th>原因</th>
              </tr>
            </thead>
            <tbody>
              {(signals.data || []).map((s) => (
                <tr key={s.code}>
                  <td>
                    <Link to={`/stocks/${s.code}?date=${s.trade_date}`}>
                      <span className="mono">{s.code}</span> {s.name}
                    </Link>
                  </td>
                  <td className="mono">
                    {s.final_score != null ? s.final_score.toFixed(2) : "—"}
                  </td>
                  <td className="muted" style={{ maxWidth: 480 }}>
                    {(s.reasons || []).slice(0, 3).join("；")}
                  </td>
                </tr>
              ))}
              {!signals.data?.length && (
                <tr>
                  <td colSpan={3} className="muted">
                    当日无信号
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

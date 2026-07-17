import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

export function ReportsPage() {
  const reports = useQuery({ queryKey: ["reports"], queryFn: api.reports });
  const [active, setActive] = useState("");

  useEffect(() => {
    if (!active && reports.data?.[0]?.trade_date) {
      setActive(reports.data[0].trade_date);
    }
  }, [reports.data, active]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>日报</h1>
          <p className="muted">已生成的 HTML 日报</p>
        </div>
      </div>

      <div className="grid-2">
        <div className="panel">
          <div className="panel-head">列表</div>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>日期</th>
                  <th>打开</th>
                </tr>
              </thead>
              <tbody>
                {(reports.data || []).map((r) => (
                  <tr key={r.trade_date}>
                    <td className="mono">{r.trade_date}</td>
                    <td className="links-row">
                      <button type="button" className="btn" onClick={() => setActive(r.trade_date)}>
                        预览
                      </button>
                      <a href={`/api/reports/${r.trade_date}`} target="_blank" rel="noreferrer">
                        新窗口
                      </a>
                    </td>
                  </tr>
                ))}
                {!reports.data?.length && (
                  <tr>
                    <td colSpan={2} className="muted">
                      暂无日报文件
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
        <div className="panel">
          <div className="panel-head">预览 {active || ""}</div>
          {active ? (
            <iframe
              title="report"
              src={`/api/reports/${active}`}
              style={{ width: "100%", height: 640, border: 0 }}
            />
          ) : (
            <div style={{ padding: "1rem" }} className="muted">
              选择一份日报预览
            </div>
          )}
        </div>
      </div>
    </>
  );
}

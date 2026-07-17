import { Link } from "react-router-dom";
import type { RelationNeighbor } from "@/api/client";

type Props = {
  rows: RelationNeighbor[];
  emptyText: string;
  dateQuery?: string;
};

export function RelationList({ rows, emptyText, dateQuery }: Props) {
  if (!rows.length) {
    return <p className="muted" style={{ margin: "0.5rem 0" }}>{emptyText}</p>;
  }
  return (
    <table className="data">
      <thead>
        <tr>
          <th>#</th>
          <th>股票</th>
          <th>相关系数</th>
          <th>样本</th>
          <th>同行业</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => {
          const href = dateQuery
            ? `/stocks/${r.peer}?date=${dateQuery}`
            : `/stocks/${r.peer}`;
          const corr = r.relation_value;
          const corrClass = corr >= 0 ? "corr-pos" : "corr-neg";
          return (
            <tr key={r.peer}>
              <td className="mono">{i + 1}</td>
              <td>
                <Link to={href}>
                  <span className="mono">{r.peer}</span> {r.peer_name}
                </Link>
              </td>
              <td className={`mono ${corrClass}`}>{corr.toFixed(3)}</td>
              <td className="mono muted">{r.sample_size}</td>
              <td>{r.is_same_industry ? "是" : ""}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/** 侧栏紧凑列表 */
export function RelationMiniList({
  title,
  rows,
  dateQuery,
  limit = 8,
}: {
  title: string;
  rows: RelationNeighbor[];
  dateQuery?: string;
  limit?: number;
}) {
  const slice = rows.slice(0, limit);
  return (
    <div className="panel">
      <div className="panel-head">{title}</div>
      <div style={{ padding: "0.4rem 0.75rem 0.75rem" }}>
        {!slice.length && <span className="muted">暂无</span>}
        {slice.map((r) => {
          const href = dateQuery
            ? `/stocks/${r.peer}?date=${dateQuery}`
            : `/stocks/${r.peer}`;
          const corrClass = r.relation_value >= 0 ? "corr-pos" : "corr-neg";
          return (
            <div key={r.peer} className="rel-mini-row">
              <Link to={href}>
                <span className="mono">{r.peer}</span>
                <span className="muted"> {r.peer_name}</span>
              </Link>
              <span className={`mono ${corrClass}`}>{r.relation_value.toFixed(3)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

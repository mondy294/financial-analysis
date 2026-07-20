import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQueries } from "@tanstack/react-query";
import { api } from "@/api/client";
import { StockPicker } from "@/components/StockPicker";
import {
  listWatchlist,
  removeWatch,
  addWatch,
  subscribeWatchlist,
  type WatchlistItem,
} from "@/lib/watchlist";

export function WatchlistPage() {
  const [items, setItems] = useState<WatchlistItem[]>(() => listWatchlist());
  const [picker, setPicker] = useState("");

  useEffect(() => subscribeWatchlist(() => setItems(listWatchlist())), []);

  const quotes = useQueries({
    queries: items.map((it) => ({
      queryKey: ["watchlist-quote", it.code],
      queryFn: async () => {
        const [detail, snap] = await Promise.all([
          api.stockDetail(it.code),
          api.snapshot(it.code).catch(() => null),
        ]);
        return {
          name: detail.name || "",
          close: snap?.close ?? null,
          pct_change: snap?.pct_change ?? null,
          trade_date: snap?.trade_date ?? null,
        };
      },
      staleTime: 5 * 60 * 1000,
      retry: false,
    })),
  });

  const rows = useMemo(() => {
    return items.map((it, i) => {
      const q = quotes[i]?.data;
      return {
        ...it,
        name: it.name || q?.name || "",
        close: q?.close ?? null,
        pct_change: q?.pct_change ?? null,
        trade_date: q?.trade_date ?? null,
        loading: quotes[i]?.isLoading,
      };
    });
  }, [items, quotes]);

  const onRemove = (code: string) => {
    setItems(removeWatch(code));
  };

  const onAddFromPicker = (code: string) => {
    if (!code.trim()) return;
    void (async () => {
      let name: string | undefined;
      try {
        const d = await api.stockDetail(code);
        name = d.name;
      } catch {
        /* ignore */
      }
      setItems(addWatch(code, name));
      setPicker("");
    })();
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>自选</h1>
          <p className="muted">保存在本机浏览器，可从股票详情页加入或在此删除</p>
        </div>
        <div className="toolbar">
          <label>
            添加股票
            <StockPicker
              mode="single"
              value={picker}
              onChange={(code) => {
                setPicker(code);
                if (code.trim()) onAddFromPicker(code);
              }}
              placeholder="搜索代码 / 名称加入自选"
            />
          </label>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <span>
            共 {items.length} 只
            {items.length ? (
              <span className="muted"> · 按加入时间倒序</span>
            ) : null}
          </span>
        </div>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>#</th>
                <th>代码</th>
                <th>名称</th>
                <th style={{ textAlign: "right" }}>最新价</th>
                <th style={{ textAlign: "right" }}>涨跌幅</th>
                <th>行情日</th>
                <th>加入时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const pct = r.pct_change;
                const pctColor =
                  pct == null || Number.isNaN(pct)
                    ? undefined
                    : pct > 0
                      ? "#c23b22"
                      : pct < 0
                        ? "#0b6e4f"
                        : undefined;
                return (
                  <tr key={r.code}>
                    <td className="mono muted">{i + 1}</td>
                    <td>
                      <Link to={`/stocks/${r.code}`}>
                        <span className="mono">{r.code}</span>
                      </Link>
                    </td>
                    <td>{r.name || (r.loading ? "…" : "—")}</td>
                    <td className="mono" style={{ textAlign: "right" }}>
                      {r.close != null ? r.close.toFixed(2) : r.loading ? "…" : "—"}
                    </td>
                    <td
                      className="mono"
                      style={{ textAlign: "right", color: pctColor }}
                    >
                      {pct != null && Number.isFinite(pct)
                        ? `${pct.toFixed(2)}%`
                        : r.loading
                          ? "…"
                          : "—"}
                    </td>
                    <td className="mono muted">{r.trade_date || "—"}</td>
                    <td className="muted" style={{ fontSize: "0.82rem" }}>
                      {r.added_at
                        ? r.added_at.slice(0, 19).replace("T", " ")
                        : "—"}
                    </td>
                    <td className="links-row">
                      <Link to={`/stocks/${r.code}`}>详情</Link>
                      <button
                        type="button"
                        className="btn danger"
                        style={{ padding: "0.15rem 0.5rem" }}
                        onClick={() => onRemove(r.code)}
                      >
                        删除
                      </button>
                    </td>
                  </tr>
                );
              })}
              {!items.length ? (
                <tr>
                  <td colSpan={8} className="muted">
                    暂无自选。可在上方搜索添加，或打开股票详情页点「加自选」。
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

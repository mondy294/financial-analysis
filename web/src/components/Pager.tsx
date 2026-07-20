type Props = {
  page: number; // 1-based
  pageSize: number;
  total: number;
  pageSizeOptions?: readonly number[];
  onPageChange: (page: number) => void;
  onPageSizeChange?: (size: number) => void;
};

/** 完整分页：首页/末页、跳转、条数、范围说明 */
export function Pager({
  page,
  pageSize,
  total,
  pageSizeOptions = [10, 20, 50],
  onPageChange,
  onPageSizeChange,
}: Props) {
  const totalPages = Math.max(1, Math.ceil(Math.max(0, total) / Math.max(1, pageSize)));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const from = total === 0 ? 0 : (safePage - 1) * pageSize + 1;
  const to = Math.min(total, safePage * pageSize);

  const goto = (p: number) => {
    const next = Math.min(Math.max(1, p), totalPages);
    if (next !== page) onPageChange(next);
  };

  return (
    <div className="es-pager">
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
        {onPageSizeChange ? (
          <label className="pager-size">
            每页
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
            >
              {pageSizeOptions.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <span className="muted mono" style={{ fontSize: "0.85rem" }}>
          {total === 0 ? "共 0 条" : `第 ${from}–${to} 条 · 共 ${total} 条`}
        </span>
      </div>
      <div className="es-pager-btns">
        <button type="button" className="btn" disabled={safePage <= 1} onClick={() => goto(1)}>
          首页
        </button>
        <button
          type="button"
          className="btn"
          disabled={safePage <= 1}
          onClick={() => goto(safePage - 1)}
        >
          上一页
        </button>
        <label className="muted" style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.85rem" }}>
          第
          <input
            type="number"
            className="mono"
            min={1}
            max={totalPages}
            value={safePage}
            style={{ width: 56 }}
            onChange={(e) => {
              const n = Number(e.target.value);
              if (Number.isFinite(n)) goto(n);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                const n = Number((e.target as HTMLInputElement).value);
                if (Number.isFinite(n)) goto(n);
              }
            }}
          />
          / {totalPages} 页
        </label>
        <button
          type="button"
          className="btn"
          disabled={safePage >= totalPages}
          onClick={() => goto(safePage + 1)}
        >
          下一页
        </button>
        <button
          type="button"
          className="btn"
          disabled={safePage >= totalPages}
          onClick={() => goto(totalPages)}
        >
          末页
        </button>
      </div>
    </div>
  );
}

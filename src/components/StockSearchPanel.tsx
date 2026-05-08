import { useState } from "react";

type StockSearchPanelProps = {
  loading: boolean;
  onSearch: (code: string) => Promise<void>;
};

const quickCodes = ["600519", "000333", "300750"];

export function StockSearchPanel({ loading, onSearch }: StockSearchPanelProps) {
  const [code, setCode] = useState("600519");

  return (
    <section className="search-panel panel">
      <div className="search-panel-copy">
        <span className="eyebrow">股票查询</span>
        <h2>输入股票代码，直接切到股票分析</h2>
        <p>这里专门看股票：先拉 K 线，再看技术指标和 Agent 推理，不跟基金页混在一起。</p>
      </div>

      <form
        className="search-form"
        onSubmit={async (event) => {
          event.preventDefault();
          await onSearch(code);
        }}
      >
        <label htmlFor="stock-code">
          <span>股票代码</span>
          <div className="search-row">
            <input
              id="stock-code"
              value={code}
              inputMode="numeric"
              maxLength={6}
              onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="例如 600519"
            />
            <button type="submit" className="primary-button" disabled={loading || code.length !== 6}>
              {loading ? "查询中..." : "查询股票"}
            </button>
          </div>
        </label>

        <div className="quick-actions">
          {quickCodes.map((item) => (
            <button
              key={item}
              type="button"
              className="ghost-chip"
              onClick={async () => {
                setCode(item);
                await onSearch(item);
              }}
            >
              {item}
            </button>
          ))}
        </div>
      </form>
    </section>
  );
}

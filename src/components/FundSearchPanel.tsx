import { useState } from "react";

type FundSearchPanelProps = {
  loading: boolean;
  onSearch: (code: string) => Promise<void>;
};

const quickCodes = ["161725", "005827", "000001"];

export function FundSearchPanel({ loading, onSearch }: FundSearchPanelProps) {
  const [code, setCode] = useState("161725");

  return (
    <section className="search-panel panel">
      <div className="search-panel-copy">
        <span className="eyebrow">基金查询</span>
        <h2>输入基金编号，直接切到总览</h2>
        <p>查询之后可以继续加入自选，或者顺手录入到我的持有。整个管理台的主线就这三步，别搞复杂了。</p>
      </div>

      <form
        className="search-form"
        onSubmit={async (event) => {
          event.preventDefault();
          await onSearch(code);
        }}
      >
        <label htmlFor="fund-code">
          <span>基金编号</span>
          <div className="search-row">
            <input
              id="fund-code"
              value={code}
              inputMode="numeric"
              maxLength={6}
              onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="例如 161725"
            />
            <button type="submit" className="primary-button" disabled={loading || code.length !== 6}>
              {loading ? "查询中..." : "查询基金"}
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

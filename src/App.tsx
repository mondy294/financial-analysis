import { useEffect, useMemo, useState } from "react";
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { addWatchlist, getFundDetail, getHoldings, getWatchlist, removeHolding, removeWatchlist, saveHolding } from "./api/client";
import { FundSearchPanel } from "./components/FundSearchPanel";
import { HoldingsPage } from "./pages/HoldingsPage";
import { OverviewPage } from "./pages/OverviewPage";
import { WatchlistPage } from "./pages/WatchlistPage";
import type { FundDetailResponse, HoldingDraft, HoldingItem, WatchlistItem } from "./types";

const emptyHoldingDraft: HoldingDraft = {
  code: "",
  status: "持有中",
  holdingReturnRate: null,
  positionAmount: null,
  costNav: null,
  note: "",
};

type Notice = { type: "success" | "error"; message: string } | null;

type PageMeta = {
  title: string;
  description: string;
};

const pageMetaMap: Record<string, PageMeta> = {
  "/overview": {
    title: "基金总览",
    description: "搜索基金、看更细的净值趋势，再决定是放进自选还是转进持有。",
  },
  "/watchlist": {
    title: "我的自选",
    description: "盯盘用这一页，保留重点基金，快速看最新净值、估值和阶段表现。",
  },
  "/holdings": {
    title: "我的持有",
    description: "这里记录你自己的仓位信息：状态、收益率、持仓金额和备注，全都持久化到本地 JSON。",
  },
};

export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const [searching, setSearching] = useState(false);
  const [holdingsLoading, setHoldingsLoading] = useState(true);
  const [watchlistLoading, setWatchlistLoading] = useState(true);
  const [spotlight, setSpotlight] = useState<FundDetailResponse | null>(null);
  const [holdings, setHoldings] = useState<HoldingItem[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [holdingDraft, setHoldingDraft] = useState<HoldingDraft | null>(null);
  const [notice, setNotice] = useState<Notice>(null);

  useEffect(() => {
    void Promise.all([reloadHoldings(), reloadWatchlist()]);
  }, []);

  useEffect(() => {
    if (!notice) {
      return;
    }

    const timer = window.setTimeout(() => setNotice(null), 2400);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const pageMeta = useMemo<PageMeta>(() => {
    return pageMetaMap[location.pathname] ?? pageMetaMap["/overview"];
  }, [location.pathname]);

  const spotlightHolding = useMemo(
    () => holdings.find((item) => item.code === spotlight?.fund.code) ?? null,
    [holdings, spotlight],
  );

  const spotlightInWatchlist = useMemo(
    () => watchlist.some((item) => item.code === spotlight?.fund.code),
    [watchlist, spotlight],
  );

  async function reloadHoldings() {
    setHoldingsLoading(true);
    try {
      setHoldings(await getHoldings());
    } catch (error) {
      setNotice({ type: "error", message: error instanceof Error ? error.message : "加载持有失败" });
    } finally {
      setHoldingsLoading(false);
    }
  }

  async function reloadWatchlist() {
    setWatchlistLoading(true);
    try {
      setWatchlist(await getWatchlist());
    } catch (error) {
      setNotice({ type: "error", message: error instanceof Error ? error.message : "加载自选失败" });
    } finally {
      setWatchlistLoading(false);
    }
  }

  async function handleSearch(code: string) {
    setSearching(true);
    try {
      const detail = await getFundDetail(code);
      setSpotlight(detail);
      navigate("/overview");
      setNotice({ type: "success", message: `已加载 ${detail.fund.name}` });
    } catch (error) {
      setNotice({ type: "error", message: error instanceof Error ? error.message : "查询失败" });
    } finally {
      setSearching(false);
    }
  }

  async function handleAddWatchlist(code: string) {
    try {
      await addWatchlist(code);
      await reloadWatchlist();
      setNotice({ type: "success", message: `已把 ${code} 加入自选` });
    } catch (error) {
      setNotice({ type: "error", message: error instanceof Error ? error.message : "加入自选失败" });
    }
  }

  async function handleRemoveWatchlist(code: string) {
    try {
      await removeWatchlist(code);
      await reloadWatchlist();
      setNotice({ type: "success", message: `已把 ${code} 从自选移除` });
    } catch (error) {
      setNotice({ type: "error", message: error instanceof Error ? error.message : "移除自选失败" });
    }
  }

  function prepareHolding(code: string) {
    const existing = holdings.find((item) => item.code === code);
    setHoldingDraft(
      existing
        ? {
            code: existing.code,
            status: existing.status,
            holdingReturnRate: existing.holdingReturnRate,
            positionAmount: existing.positionAmount,
            costNav: existing.costNav,
            note: existing.note,
          }
        : {
            ...emptyHoldingDraft,
            code,
          },
    );
    navigate("/holdings");
  }

  async function handleSaveHolding(draft: HoldingDraft) {
    try {
      await saveHolding(draft);
      await reloadHoldings();
      setHoldingDraft(null);
      setNotice({ type: "success", message: `已保存 ${draft.code} 的持有信息` });
    } catch (error) {
      setNotice({ type: "error", message: error instanceof Error ? error.message : "保存持有失败" });
      throw error;
    }
  }

  async function handleRemoveHolding(code: string) {
    try {
      await removeHolding(code);
      await reloadHoldings();
      setNotice({ type: "success", message: `已删除 ${code} 的持有记录` });
    } catch (error) {
      setNotice({ type: "error", message: error instanceof Error ? error.message : "删除持有失败" });
    }
  }

  function handleOpenDetail(detail: FundDetailResponse | null) {
    setSpotlight(detail);
    navigate("/overview");
  }

  return (
    <div className="console-shell">
      <div className="ambient ambient-a" />
      <div className="ambient ambient-b" />

      <aside className="sidebar-shell">
        <div className="brand-panel">
          <span className="eyebrow">Personal Console</span>
          <h1>基金管理台</h1>
          <p>一个干净点的本地工作台：自选负责盯，持有负责记，总览负责看清楚走势。</p>
        </div>

        <nav className="sidebar-nav">
          <NavLink to="/overview" className={({ isActive }) => `sidebar-link${isActive ? " active" : ""}`}>
            <div>
              <strong>基金总览</strong>
              <span>查询后看完整业绩和净值表</span>
            </div>
          </NavLink>
          <NavLink to="/watchlist" className={({ isActive }) => `sidebar-link${isActive ? " active" : ""}`}>
            <div>
              <strong>我的自选</strong>
              <span>重点观察池</span>
            </div>
            <em>{watchlist.length}</em>
          </NavLink>
          <NavLink to="/holdings" className={({ isActive }) => `sidebar-link${isActive ? " active" : ""}`}>
            <div>
              <strong>我的持有</strong>
              <span>仓位、收益率、备注</span>
            </div>
            <em>{holdings.length}</em>
          </NavLink>
        </nav>

        <section className="sidebar-panel">
          <div>
            <span>当前聚焦</span>
            <strong>{spotlight?.fund.name ?? "还没选基金"}</strong>
            <p>{spotlight?.fund.code ?? "先输入 6 位基金编号再说"}</p>
          </div>
          <div className="sidebar-divider" />
          <div className="sidebar-mini-grid">
            <article>
              <span>自选数量</span>
              <strong>{watchlist.length}</strong>
            </article>
            <article>
              <span>持有数量</span>
              <strong>{holdings.length}</strong>
            </article>
          </div>
        </section>
      </aside>

      <main className="workspace-shell">
        <header className="workspace-header">
          <div className="workspace-copy-block">
            <span className="eyebrow">Financial Fund Console</span>
            <h2>{pageMeta.title}</h2>
            <p>{pageMeta.description}</p>
          </div>
          <FundSearchPanel loading={searching} onSearch={handleSearch} />
        </header>

        {notice ? <div className={`toast toast-${notice.type}`}>{notice.message}</div> : null}

        <Routes>
          <Route path="/" element={<Navigate to="/overview" replace />} />
          <Route
            path="/overview"
            element={
              <OverviewPage
                spotlight={spotlight}
                inWatchlist={spotlightInWatchlist}
                holding={spotlightHolding}
                onAddWatchlist={handleAddWatchlist}
                onRemoveWatchlist={handleRemoveWatchlist}
                onUseForHolding={prepareHolding}
              />
            }
          />
          <Route
            path="/watchlist"
            element={
              <WatchlistPage
                items={watchlist}
                loading={watchlistLoading}
                onRemove={handleRemoveWatchlist}
                onOpenDetail={handleOpenDetail}
                onUseForHolding={prepareHolding}
              />
            }
          />
          <Route
            path="/holdings"
            element={
              <HoldingsPage
                items={holdings}
                loading={holdingsLoading}
                draft={holdingDraft}
                onSave={handleSaveHolding}
                onDelete={handleRemoveHolding}
                onOpenDetail={handleOpenDetail}
              />
            }
          />
        </Routes>
      </main>
    </div>
  );
}

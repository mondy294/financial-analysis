import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

const NAV = [
  { to: "/", label: "工作台", end: true },
  { to: "/patterns", label: "Pattern" },
  { to: "/strategies", label: "策略" },
  { to: "/clusters", label: "相关簇" },
  { to: "/patterns/eval", label: "评估" },
  { to: "/signals", label: "选股" },
  { to: "/reports", label: "日报" },
  { to: "/system", label: "系统" },
];

export function Layout() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  const search = useQuery({
    queryKey: ["search", q],
    queryFn: () => api.searchStocks(q),
    enabled: q.trim().length >= 1,
  });

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  return (
    <div className="app-shell">
      <header className="topbar">
        <Link to="/" className="brand">
          quant_<span>system</span>
        </Link>
        <nav className="nav">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="search-wrap" ref={boxRef}>
          <input
            placeholder="搜索代码 / 名称"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && search.data?.[0]) {
                navigate(`/stocks/${search.data[0].code}`);
                setOpen(false);
                setQ("");
              }
            }}
          />
          {open && q.trim() && (
            <div className="search-dropdown">
              {search.isFetching && <div style={{ padding: "0.6rem" }}>搜索中…</div>}
              {search.data?.length === 0 && !search.isFetching && (
                <div style={{ padding: "0.6rem" }} className="muted">
                  无结果
                </div>
              )}
              {search.data?.map((s) => (
                <button
                  key={s.code}
                  type="button"
                  onClick={() => {
                    navigate(`/stocks/${s.code}`);
                    setOpen(false);
                    setQ("");
                  }}
                >
                  <span className="mono">{s.code}</span> {s.name}
                  {s.industry_name ? (
                    <span className="muted"> · {s.industry_name}</span>
                  ) : null}
                </button>
              ))}
            </div>
          )}
        </div>
      </header>
      <main className="page">
        <Outlet />
      </main>
    </div>
  );
}

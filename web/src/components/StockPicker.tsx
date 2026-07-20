import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

type StockHit = { code: string; name: string; industry_name?: string; is_st: boolean };

type Props = {
  /** single：一只；multi：多只，value 为逗号分隔代码 */
  mode?: "single" | "multi";
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
};

type DropdownPos = { top: number; left: number; width: number };

function parseCodes(raw: string): string[] {
  return raw
    .split(/[,，\s]+/)
    .map((c) => c.trim().toUpperCase())
    .filter(Boolean);
}

function joinCodes(codes: string[]): string {
  return codes.join(",");
}

export function StockPicker({
  mode = "single",
  value,
  onChange,
  placeholder,
  disabled,
  className,
}: Props) {
  const boxRef = useRef<HTMLDivElement>(null);
  const anchorRef = useRef<HTMLElement | null>(null);
  const dropRef = useRef<HTMLDivElement | null>(null);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<DropdownPos | null>(null);
  const [nameMap, setNameMap] = useState<Record<string, string>>({});
  const selectedCodes = parseCodes(value);

  const search = useQuery({
    queryKey: ["stock-picker", q],
    queryFn: () => api.searchStocks(q.trim()),
    enabled: q.trim().length >= 1,
  });

  const showDropdown = open && q.trim().length >= 1;

  const updatePos = () => {
    const el = anchorRef.current || boxRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    setPos({
      top: r.bottom + 4,
      left: r.left,
      width: Math.max(r.width, 220),
    });
  };

  useLayoutEffect(() => {
    if (!showDropdown) {
      setPos(null);
      return;
    }
    updatePos();
  }, [showDropdown, q, selectedCodes.length]);

  useEffect(() => {
    if (!showDropdown) return;
    const onReposition = () => updatePos();
    window.addEventListener("resize", onReposition);
    // capture：面板/页面滚动时也跟位
    window.addEventListener("scroll", onReposition, true);
    return () => {
      window.removeEventListener("resize", onReposition);
      window.removeEventListener("scroll", onReposition, true);
    };
  }, [showDropdown]);

  // URL / 外部写入的代码：补名称
  useEffect(() => {
    let cancelled = false;
    const missing = selectedCodes.filter((c) => !nameMap[c]);
    if (!missing.length) return;
    void (async () => {
      const next: Record<string, string> = {};
      await Promise.all(
        missing.slice(0, 24).map(async (code) => {
          try {
            const d = await api.stockDetail(code);
            next[code] = d.name || "";
          } catch {
            next[code] = "";
          }
        }),
      );
      if (!cancelled) setNameMap((prev) => ({ ...prev, ...next }));
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      const t = e.target as Node;
      if (boxRef.current?.contains(t)) return;
      if (dropRef.current?.contains(t)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const remember = (s: StockHit) => {
    setNameMap((prev) => ({ ...prev, [s.code]: s.name }));
  };

  const pick = (s: StockHit) => {
    remember(s);
    if (mode === "single") {
      onChange(s.code);
      setQ("");
      setOpen(false);
      return;
    }
    if (selectedCodes.includes(s.code)) {
      setQ("");
      setOpen(false);
      return;
    }
    onChange(joinCodes([...selectedCodes, s.code]));
    setQ("");
    setOpen(false);
  };

  const remove = (code: string) => {
    if (mode === "single") {
      onChange("");
      return;
    }
    onChange(joinCodes(selectedCodes.filter((c) => c !== code)));
  };

  const ph =
    placeholder ||
    (mode === "single" ? "搜索代码 / 名称" : "搜索添加股票（可多只）");

  const singleSelected = mode === "single" && selectedCodes[0];
  const singleName = singleSelected ? nameMap[singleSelected] : "";

  const dropdown =
    showDropdown && pos
      ? createPortal(
          <div
            ref={dropRef}
            className="search-dropdown stock-picker-dropdown stock-picker-dropdown-portal"
            style={{
              top: pos.top,
              left: pos.left,
              width: pos.width,
            }}
          >
            {search.isFetching && <div style={{ padding: "0.6rem" }}>搜索中…</div>}
            {search.data?.length === 0 && !search.isFetching && (
              <div style={{ padding: "0.6rem" }} className="muted">
                无结果
              </div>
            )}
            {search.data?.map((s) => {
              const already = mode === "multi" && selectedCodes.includes(s.code);
              return (
                <button
                  key={s.code}
                  type="button"
                  disabled={already}
                  onClick={() => pick(s)}
                >
                  <span className="mono">{s.code}</span> {s.name}
                  {s.industry_name ? (
                    <span className="muted"> · {s.industry_name}</span>
                  ) : null}
                  {already ? <span className="muted"> · 已选</span> : null}
                </button>
              );
            })}
          </div>,
          document.body,
        )
      : null;

  return (
    <div className={`stock-picker ${className || ""}`} ref={boxRef}>
      {mode === "multi" && selectedCodes.length > 0 && (
        <div className="stock-picker-chips">
          {selectedCodes.map((code) => (
            <span key={code} className="stock-picker-chip">
              <span className="mono">{code}</span>
              {nameMap[code] ? ` ${nameMap[code]}` : ""}
              <button
                type="button"
                className="stock-picker-chip-x"
                disabled={disabled}
                onClick={() => remove(code)}
                aria-label={`移除 ${code}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {mode === "single" && singleSelected && !q ? (
        <div
          className="stock-picker-single"
          ref={(el) => {
            anchorRef.current = el;
          }}
        >
          <span className="mono">{singleSelected}</span>
          {singleName ? <span className="muted"> {singleName}</span> : null}
          <button
            type="button"
            className="btn"
            style={{ padding: "0.1rem 0.45rem", marginLeft: "auto" }}
            disabled={disabled}
            onClick={() => {
              onChange("");
              setQ("");
              setOpen(true);
            }}
          >
            更换
          </button>
        </div>
      ) : (
        <input
          ref={(el) => {
            anchorRef.current = el;
          }}
          value={q}
          disabled={disabled}
          placeholder={ph}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && search.data?.[0]) {
              e.preventDefault();
              pick(search.data[0]);
            }
            if (e.key === "Escape") setOpen(false);
          }}
        />
      )}

      {dropdown}
    </div>
  );
}

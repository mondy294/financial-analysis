import { useEffect, useMemo, useRef, useState } from "react";
import {
  ColorType,
  CrosshairMode,
  LineStyle,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Logical,
  type LogicalRange,
  type Time,
} from "lightweight-charts";
import type { WindowRange } from "@/api/client";
import { bollinger, macd, rsi, sma } from "@/lib/indicators";
import {
  aggregateKline,
  defaultVisibleCount,
  type KlinePeriod,
} from "@/lib/klineAggregate";

export type ChartBar = {
  trade_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type ChartFeature = {
  trade_date: string;
  ma5?: number | null;
  ma10?: number | null;
  ma20?: number | null;
  ma60?: number | null;
  macd?: number | null;
  macd_signal?: number | null;
  macd_hist?: number | null;
  rsi_14?: number | null;
  boll_upper?: number | null;
  boll_mid?: number | null;
  boll_lower?: number | null;
};

type Props = {
  bars: ChartBar[];
  features?: ChartFeature[];
  ranges?: Record<string, WindowRange> | null;
};

type OverlayKey = "ma5" | "ma10" | "ma20" | "ma60" | "boll";
type PaneKey = "macd" | "rsi";

const OVERLAYS: Array<{ key: OverlayKey; label: string; color: string }> = [
  { key: "ma5", label: "MA5", color: "#2563eb" },
  { key: "ma10", label: "MA10", color: "#7c3aed" },
  { key: "ma20", label: "MA20", color: "#ca8a04" },
  { key: "ma60", label: "MA60", color: "#64748b" },
  { key: "boll", label: "BOLL", color: "#0f766e" },
];

const PERIODS: Array<{ key: KlinePeriod; label: string }> = [
  { key: "day", label: "日K" },
  { key: "week", label: "周K" },
  { key: "month", label: "月K" },
];

/** 右侧留白 logical 单位，让最新一根贴右但不贴边 */
const RIGHT_PAD = 2;

function toTime(d: string): Time {
  return d as Time;
}

function lineFrom(
  bars: ChartBar[],
  values: Array<number | null | undefined>,
): Array<{ time: Time; value: number }> {
  const out: Array<{ time: Time; value: number }> = [];
  for (let i = 0; i < bars.length; i++) {
    const v = values[i];
    if (typeof v === "number" && Number.isFinite(v)) {
      out.push({ time: toTime(bars[i].trade_date), value: v });
    }
  }
  return out;
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

function buildVisibleRange(rightIndex: number, visibleCount: number): LogicalRange {
  const to = (rightIndex + RIGHT_PAD) as Logical;
  const from = (Number(to) - visibleCount) as Logical;
  return { from, to };
}

export function KlineChart({ bars: dailyBars, features = [], ranges }: Props) {
  const mainRef = useRef<HTMLDivElement>(null);
  const macdRef = useRef<HTMLDivElement>(null);
  const rsiRef = useRef<HTMLDivElement>(null);
  const chartsRef = useRef<IChartApi[]>([]);
  const syncingRef = useRef(false);
  const draggingRef = useRef(false);
  const rightIndexRef = useRef(0);
  const visibleCountRef = useRef(defaultVisibleCount("day"));

  const [period, setPeriod] = useState<KlinePeriod>("day");
  const [visibleCount, setVisibleCount] = useState(() => defaultVisibleCount("day"));
  /** 窗口右端对应的 bar 下标；默认最新一根 */
  const [rightIndex, setRightIndex] = useState(0);

  const [overlays, setOverlays] = useState<Record<OverlayKey, boolean>>({
    ma5: true,
    ma10: true,
    ma20: true,
    ma60: true,
    boll: true,
  });
  const [panes, setPanes] = useState<Record<PaneKey, boolean>>({
    macd: true,
    rsi: true,
  });

  const bars = useMemo(() => aggregateKline(dailyBars, period), [dailyBars, period]);

  const applyWindow = (ri: number, vc: number) => {
    if (!bars.length || !chartsRef.current.length) return;
    const last = Math.max(0, bars.length - 1);
    const safeRi = clamp(ri, 0, last);
    const safeVc = clamp(vc, 10, Math.max(10, bars.length + RIGHT_PAD));
    const range = buildVisibleRange(safeRi, safeVc);
    syncingRef.current = true;
    chartsRef.current.forEach((c) => c.timeScale().setVisibleLogicalRange(range));
    syncingRef.current = false;
  };

  // 切周期 / 换数据：回到「最新贴右」
  useEffect(() => {
    const vc = defaultVisibleCount(period);
    const ri = Math.max(0, bars.length - 1);
    visibleCountRef.current = vc;
    rightIndexRef.current = ri;
    setVisibleCount(vc);
    setRightIndex(ri);
  }, [period, bars.length]);

  const seriesPack = useMemo(() => {
    const closes = bars.map((b) => b.close);
    const useDb = period === "day";
    const featByDate = useDb
      ? new Map(features.map((f) => [f.trade_date, f]))
      : new Map<string, ChartFeature>();

    const pick = (key: keyof ChartFeature, fallback: Array<number | null>) => {
      const values = bars.map((b, i) => {
        const fromDb = featByDate.get(b.trade_date)?.[key];
        if (typeof fromDb === "number" && Number.isFinite(fromDb)) return fromDb;
        return fallback[i];
      });
      return lineFrom(bars, values);
    };

    const fbMa5 = sma(closes, 5);
    const fbMa10 = sma(closes, 10);
    const fbMa20 = sma(closes, 20);
    const fbMa60 = sma(closes, 60);
    const fbBoll = bollinger(closes, 20, 2);
    const fbMacd = macd(closes);
    const fbRsi = rsi(closes, 14);

    return {
      ma5: pick("ma5", fbMa5),
      ma10: pick("ma10", fbMa10),
      ma20: pick("ma20", fbMa20),
      ma60: pick("ma60", fbMa60),
      bollMid: pick("boll_mid", fbBoll.mid),
      bollUpper: pick("boll_upper", fbBoll.upper),
      bollLower: pick("boll_lower", fbBoll.lower),
      macd: pick("macd", fbMacd.dif),
      macdSignal: pick("macd_signal", fbMacd.dea),
      macdHist: lineFrom(
        bars,
        bars.map((b, i) => {
          const fromDb = featByDate.get(b.trade_date)?.macd_hist;
          if (typeof fromDb === "number") return fromDb;
          return fbMacd.hist[i];
        }),
      ),
      rsi: pick("rsi_14", fbRsi),
    };
  }, [bars, features, period]);

  // 建图（数据/指标变化时重建）；窗口位置用独立 effect 设置
  useEffect(() => {
    if (!mainRef.current || bars.length === 0) return;

    const charts: IChartApi[] = [];
    // 允许左右拖拽平移；禁用滚轮缩放（避免跳到中心），缩放用下方按钮
    const interaction = {
      handleScroll: {
        mouseWheel: false,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false,
      },
      handleScale: {
        axisPressedMouseMove: { time: false, price: false },
        mouseWheel: false,
        pinch: false,
      },
    };
    const common = {
      autoSize: true,
      ...interaction,
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" } as const,
        textColor: "#5c6b7a",
        fontFamily: "IBM Plex Sans, sans-serif",
      },
      grid: {
        vertLines: { color: "#eef1f4" },
        horzLines: { color: "#eef1f4" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#d4dbe3" },
      timeScale: {
        borderColor: "#d4dbe3",
        timeVisible: false,
        shiftVisibleRangeOnNewBar: false,
        fixLeftEdge: false,
        fixRightEdge: false,
        rightOffset: 0,
      },
    };

    const main = createChart(mainRef.current, {
      ...common,
      height: mainRef.current.clientHeight || 420,
    });
    charts.push(main);

    const candle = main.addCandlestickSeries({
      upColor: "#c2410c",
      downColor: "#0f766e",
      borderUpColor: "#c2410c",
      borderDownColor: "#0f766e",
      wickUpColor: "#c2410c",
      wickDownColor: "#0f766e",
    }) as ISeriesApi<"Candlestick">;

    candle.setData(
      bars.map((b) => ({
        time: toTime(b.trade_date),
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      })),
    );

    const vol = main.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
    });
    main.priceScale("vol").applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } });
    vol.setData(
      bars.map((b) => ({
        time: toTime(b.trade_date),
        value: b.volume,
        color: b.close >= b.open ? "rgba(194,65,12,0.35)" : "rgba(15,118,110,0.35)",
      })),
    );

    const addLine = (
      data: Array<{ time: Time; value: number }>,
      color: string,
      width: 1 | 2 | 3 | 4,
      style: LineStyle = LineStyle.Solid,
    ) => {
      if (!data.length) return;
      const s = main.addLineSeries({
        color,
        lineWidth: width,
        lineStyle: style,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      s.setData(data);
    };

    if (overlays.ma5) addLine(seriesPack.ma5, "#2563eb", 2);
    if (overlays.ma10) addLine(seriesPack.ma10, "#7c3aed", 1);
    if (overlays.ma20) addLine(seriesPack.ma20, "#ca8a04", 1);
    if (overlays.ma60) addLine(seriesPack.ma60, "#64748b", 1);
    if (overlays.boll) {
      addLine(seriesPack.bollUpper, "rgba(15,118,110,0.85)", 1, LineStyle.Dashed);
      addLine(seriesPack.bollMid, "rgba(15,118,110,0.55)", 1, LineStyle.Dotted);
      addLine(seriesPack.bollLower, "rgba(15,118,110,0.85)", 1, LineStyle.Dashed);
    }

    if (period === "day" && ranges) {
      const markers: Array<{
        time: Time;
        position: "belowBar" | "aboveBar";
        color: string;
        shape: "circle" | "square";
        text: string;
      }> = [];
      Object.entries(ranges).forEach(([name, r], idx) => {
        markers.push({
          time: toTime(r.start),
          position: idx % 2 === 0 ? "belowBar" : "aboveBar",
          color: name === "breakout" ? "#b42318" : "#0b6e4f",
          shape: name === "breakout" ? "square" : "circle",
          text: `${name} ${r.start}`,
        });
        if (r.end !== r.start) {
          markers.push({
            time: toTime(r.end),
            position: idx % 2 === 0 ? "belowBar" : "aboveBar",
            color: name === "breakout" ? "#b42318" : "#0b6e4f",
            shape: "circle",
            text: `${name} end`,
          });
        }
      });
      markers.sort((a, b) => String(a.time).localeCompare(String(b.time)));
      candle.setMarkers(markers);
    }

    if (panes.macd && macdRef.current) {
      const macdChart = createChart(macdRef.current, {
        ...common,
        height: macdRef.current.clientHeight || 140,
      });
      charts.push(macdChart);
      const hist = macdChart.addHistogramSeries({
        priceFormat: { type: "price", precision: 4, minMove: 0.0001 },
      });
      hist.setData(
        seriesPack.macdHist.map((p) => ({
          ...p,
          color: p.value >= 0 ? "rgba(194,65,12,0.55)" : "rgba(15,118,110,0.55)",
        })),
      );
      macdChart
        .addLineSeries({
          color: "#2563eb",
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
        })
        .setData(seriesPack.macd);
      macdChart
        .addLineSeries({
          color: "#ca8a04",
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
        })
        .setData(seriesPack.macdSignal);
    }

    if (panes.rsi && rsiRef.current) {
      const rsiChart = createChart(rsiRef.current, {
        ...common,
        height: rsiRef.current.clientHeight || 120,
      });
      charts.push(rsiChart);
      rsiChart
        .addLineSeries({
          color: "#7c3aed",
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: true,
        })
        .setData(seriesPack.rsi);
      const overbought = rsiChart.addLineSeries({
        color: "rgba(180,35,24,0.35)",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      const oversold = rsiChart.addLineSeries({
        color: "rgba(11,110,79,0.35)",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      if (bars.length) {
        const t0 = toTime(bars[0].trade_date);
        const t1 = toTime(bars[bars.length - 1].trade_date);
        overbought.setData([
          { time: t0, value: 70 },
          { time: t1, value: 70 },
        ]);
        oversold.setData([
          { time: t0, value: 30 },
          { time: t1, value: 30 },
        ]);
      }
      rsiChart.priceScale("right").applyOptions({
        scaleMargins: { top: 0.1, bottom: 0.1 },
      });
    }

    const syncing = { lock: false };
    charts.forEach((source) => {
      source.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (!range || syncing.lock || syncingRef.current) return;
        syncing.lock = true;
        charts.forEach((c) => {
          if (c !== source) c.timeScale().setVisibleLogicalRange(range);
        });
        syncing.lock = false;
        // 拖拽时回写窗口右端下标
        if (draggingRef.current) {
          const nextRi = clamp(
            Math.round(Number(range.to) - RIGHT_PAD),
            0,
            Math.max(0, bars.length - 1),
          );
          rightIndexRef.current = nextRi;
          setRightIndex(nextRi);
        }
      });
    });

    const host = mainRef.current;
    const onPointerDown = () => {
      draggingRef.current = true;
    };
    const onPointerUp = () => {
      draggingRef.current = false;
    };
    host.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("pointerup", onPointerUp);

    chartsRef.current = charts;
    applyWindow(rightIndexRef.current, visibleCountRef.current);

    return () => {
      host.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("pointerup", onPointerUp);
      charts.forEach((c) => c.remove());
      chartsRef.current = [];
    };
    // rightIndex/visibleCount 由按钮/拖拽单独 apply，避免重建
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bars, ranges, overlays, panes, seriesPack, period]);

  useEffect(() => {
    rightIndexRef.current = rightIndex;
    visibleCountRef.current = visibleCount;
    applyWindow(rightIndex, visibleCount);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rightIndex, visibleCount]);

  const lastIdx = Math.max(0, bars.length - 1);
  const minRight = Math.min(Math.max(visibleCount - 1, 0), lastIdx);
  const atLatest = rightIndex >= lastIdx;
  const atOldest = rightIndex <= minRight;

  const shift = (delta: number) => {
    const next = clamp(rightIndexRef.current + delta, minRight, lastIdx);
    rightIndexRef.current = next;
    setRightIndex(next);
    applyWindow(next, visibleCountRef.current);
  };

  const zoom = (factor: number) => {
    const next = clamp(
      Math.round(visibleCountRef.current * factor),
      20,
      Math.min(300, Math.max(20, bars.length)),
    );
    visibleCountRef.current = next;
    setVisibleCount(next);
    applyWindow(rightIndexRef.current, next);
  };

  const goLatest = () => {
    rightIndexRef.current = lastIdx;
    setRightIndex(lastIdx);
    applyWindow(lastIdx, visibleCountRef.current);
  };

  const windowLabel = useMemo(() => {
    if (!bars.length) return "—";
    const ri = clamp(rightIndex, 0, lastIdx);
    const left = clamp(ri - visibleCount + 1, 0, lastIdx);
    return `${bars[left]?.trade_date ?? "—"} → ${bars[ri]?.trade_date ?? "—"}`;
  }, [bars, rightIndex, visibleCount, lastIdx]);

  return (
    <div className="chart-stack">
      <div className="chart-toolbar">
        <div className="period-tabs">
          {PERIODS.map((p) => (
            <button
              key={p.key}
              type="button"
              className={period === p.key ? "active" : ""}
              onClick={() => setPeriod(p.key)}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="chart-toggles">
          {OVERLAYS.map((o) => (
            <label key={o.key} className="chart-toggle">
              <input
                type="checkbox"
                checked={overlays[o.key]}
                onChange={() =>
                  setOverlays((prev) => ({ ...prev, [o.key]: !prev[o.key] }))
                }
              />
              <span className="swatch" style={{ background: o.color }} />
              {o.label}
            </label>
          ))}
          <span className="chart-sep" />
          <label className="chart-toggle">
            <input
              type="checkbox"
              checked={panes.macd}
              onChange={() => setPanes((p) => ({ ...p, macd: !p.macd }))}
            />
            MACD
          </label>
          <label className="chart-toggle">
            <input
              type="checkbox"
              checked={panes.rsi}
              onChange={() => setPanes((p) => ({ ...p, rsi: !p.rsi }))}
            />
            RSI14
          </label>
        </div>
      </div>

      <div className="chart-box chart-main" ref={mainRef} />

      <div className="chart-nav">
        <div className="chart-nav-btns">
          <button
            type="button"
            className="btn"
            disabled={atOldest}
            onClick={() => shift(-visibleCount)}
          >
            上一屏
          </button>
          <button type="button" className="btn" disabled={atOldest} onClick={() => shift(-10)}>
            左移
          </button>
          <button type="button" className="btn" disabled={atLatest} onClick={() => shift(10)}>
            右移
          </button>
          <button
            type="button"
            className="btn"
            disabled={atLatest}
            onClick={() => shift(visibleCount)}
          >
            下一屏
          </button>
          <button type="button" className="btn primary" disabled={atLatest} onClick={goLatest}>
            回到最新
          </button>
          <span className="chart-sep" />
          <button type="button" className="btn" onClick={() => zoom(1 / 1.25)}>
            放大
          </button>
          <button type="button" className="btn" onClick={() => zoom(1.25)}>
            缩小
          </button>
        </div>
        <div className="muted mono chart-nav-meta">
          {windowLabel} · {visibleCount} 根 · 可拖拽或点按钮平移
        </div>
      </div>

      {panes.macd && (
        <div className="chart-pane">
          <div className="chart-pane-label">
            MACD <span className="swatch" style={{ background: "#2563eb" }} /> DIF{" "}
            <span className="swatch" style={{ background: "#ca8a04" }} /> DEA
          </div>
          <div className="chart-box chart-sub" ref={macdRef} />
        </div>
      )}

      {panes.rsi && (
        <div className="chart-pane">
          <div className="chart-pane-label">
            RSI(14) <span className="swatch" style={{ background: "#7c3aed" }} /> 线 · 30/70
          </div>
          <div className="chart-box chart-sub-rsi" ref={rsiRef} />
        </div>
      )}
    </div>
  );
}

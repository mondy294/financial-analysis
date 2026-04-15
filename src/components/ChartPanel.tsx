import { useEffect, useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, MarkPointComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import ReactECharts from "echarts-for-react/lib/core";
import type { ChartRange, FundTrendPoint } from "../types";
import {
  buildTrendIndicators,
  calculateRangeReturn,
  calculateTrendInsights,
  filterTrendByRange,
  formatNav,
  formatPercent,
  RANGE_OPTIONS,
  signedClass,
} from "../utils/fund";

type ChartPanelProps = {
  points: FundTrendPoint[];
  costNav?: number | null;
};

type OverlayKey = "nav" | "cost" | "ma5" | "ma10" | "ma20" | "ma60" | "bollUpper" | "bollLower";

use([LineChart, GridComponent, LegendComponent, MarkPointComponent, TooltipComponent, CanvasRenderer]);

const overlayMeta: Array<{ key: OverlayKey; label: string; color: string }> = [
  { key: "nav", label: "单位净值", color: "#4f8cff" },
  { key: "cost", label: "成本线", color: "#fb7185" },
  { key: "ma5", label: "MA5", color: "#22d3ee" },
  { key: "ma10", label: "MA10", color: "#f59e0b" },
  { key: "ma20", label: "MA20", color: "#34d399" },
  { key: "ma60", label: "MA60", color: "#a78bfa" },
  { key: "bollUpper", label: "BOLL 上轨", color: "#f472b6" },
  { key: "bollLower", label: "BOLL 下轨", color: "#c084fc" },
];

const legendNameMap: Record<string, OverlayKey> = {
  单位净值: "nav",
  成本线: "cost",
  MA5: "ma5",
  MA10: "ma10",
  MA20: "ma20",
  MA60: "ma60",
  "BOLL 上轨": "bollUpper",
  "BOLL 下轨": "bollLower",
};

function getDefaultOverlayState(hasCostLine: boolean): Record<OverlayKey, boolean> {
  return {
    nav: true,
    cost: hasCostLine,
    ma5: true,
    ma10: true,
    ma20: true,
    ma60: true,
    bollUpper: true,
    bollLower: true,
  };
}

export function ChartPanel({ points, costNav = null }: ChartPanelProps) {
  const [activeRange, setActiveRange] = useState<ChartRange>("3M");
  const hasCostLine = costNav !== null && Number.isFinite(costNav);
  const [overlayVisibility, setOverlayVisibility] = useState<Record<OverlayKey, boolean>>(() => getDefaultOverlayState(hasCostLine));

  useEffect(() => {
    setOverlayVisibility((previous) => {
      if (hasCostLine === previous.cost) {
        return previous;
      }

      return {
        ...previous,
        cost: hasCostLine,
      };
    });
  }, [hasCostLine]);

  const indicatorPoints = useMemo(() => buildTrendIndicators(points), [points]);
  const filteredPoints = useMemo(() => filterTrendByRange(indicatorPoints, activeRange), [indicatorPoints, activeRange]);
  const chartPoints = useMemo(
    () => filteredPoints.filter((item): item is typeof item & { nav: number } => item.nav !== null && Number.isFinite(item.nav)),
    [filteredPoints],
  );
  const rangeReturn = useMemo(() => calculateRangeReturn(chartPoints), [chartPoints]);
  const insights = useMemo(() => calculateTrendInsights(filteredPoints, costNav), [filteredPoints, costNav]);

  const indicatorCards = useMemo(
    () => [
      { key: "ma5", label: "5 日均线", value: insights.ma5, format: formatNav, signed: false },
      { key: "ma10", label: "10 日均线", value: insights.ma10, format: formatNav, signed: false },
      { key: "ma20", label: "20 日均线", value: insights.ma20, format: formatNav, signed: false },
      { key: "ma60", label: "60 日均线", value: insights.ma60, format: formatNav, signed: false },
      ...(hasCostLine
        ? [{ key: "deviationFromCost", label: "相对成本线", value: insights.deviationFromCost, format: formatPercent, signed: true }]
        : []),
      { key: "deviationFromMa20", label: "相对 MA20 乖离率", value: insights.deviationFromMa20, format: formatPercent, signed: true },
      { key: "bollWidth20", label: "20 日布林带宽", value: insights.bollWidth20, format: formatPercent, signed: false },
      { key: "annualizedVolatility20d", label: "20 日年化波动率", value: insights.annualizedVolatility20d, format: formatPercent, signed: false },
      { key: "maxDrawdown", label: "区间最大回撤", value: insights.maxDrawdown, format: formatPercent, signed: true },
    ],
    [hasCostLine, insights],
  );

  const option = useMemo<EChartsOption | null>(() => {
    if (chartPoints.length < 2) {
      return null;
    }

    const seriesValueBuckets: number[] = [];

    if (overlayVisibility.nav) {
      seriesValueBuckets.push(...chartPoints.map((item) => item.nav));
    }
    if (overlayVisibility.ma5) {
      seriesValueBuckets.push(...chartPoints.map((item) => item.ma5).filter((value): value is number => value !== null));
    }
    if (overlayVisibility.ma10) {
      seriesValueBuckets.push(...chartPoints.map((item) => item.ma10).filter((value): value is number => value !== null));
    }
    if (overlayVisibility.ma20) {
      seriesValueBuckets.push(...chartPoints.map((item) => item.ma20).filter((value): value is number => value !== null));
    }
    if (overlayVisibility.ma60) {
      seriesValueBuckets.push(...chartPoints.map((item) => item.ma60).filter((value): value is number => value !== null));
    }
    if (overlayVisibility.bollUpper) {
      seriesValueBuckets.push(...chartPoints.map((item) => item.bollUpper).filter((value): value is number => value !== null));
    }
    if (overlayVisibility.bollLower) {
      seriesValueBuckets.push(...chartPoints.map((item) => item.bollLower).filter((value): value is number => value !== null));
    }
    if (hasCostLine && overlayVisibility.cost && costNav !== null) {
      seriesValueBuckets.push(Number(costNav));
    }

    const allValues = seriesValueBuckets.length > 0 ? seriesValueBuckets : chartPoints.map((item) => item.nav);
    const min = Math.min(...allValues);
    const max = Math.max(...allValues);
    const spread = Math.max(max - min, 0.01);
    const firstNav = chartPoints[0]?.nav ?? null;

    return {
      backgroundColor: "transparent",
      animationDuration: 380,
      legend: {
        top: 0,
        right: 4,
        icon: "roundRect",
        itemWidth: 10,
        itemHeight: 10,
        selected: {
          单位净值: overlayVisibility.nav,
          成本线: hasCostLine ? overlayVisibility.cost : false,
          MA5: overlayVisibility.ma5,
          MA10: overlayVisibility.ma10,
          MA20: overlayVisibility.ma20,
          MA60: overlayVisibility.ma60,
          "BOLL 上轨": overlayVisibility.bollUpper,
          "BOLL 下轨": overlayVisibility.bollLower,
        },
        textStyle: {
          color: "#95a7c7",
        },
      },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(6, 17, 31, 0.94)",
        borderColor: "rgba(79, 140, 255, 0.36)",
        borderWidth: 1,
        padding: 12,
        textStyle: {
          color: "#ebf2ff",
        },
        axisPointer: {
          type: "cross",
          lineStyle: {
            color: "rgba(110, 231, 183, 0.55)",
            width: 1,
          },
          crossStyle: {
            color: "rgba(110, 231, 183, 0.35)",
          },
        },
        formatter: (params: unknown) => {
          const point = Array.isArray(params) ? params[0] : params;
          const dataIndex = typeof (point as { dataIndex?: number } | undefined)?.dataIndex === "number"
            ? (point as { dataIndex?: number }).dataIndex ?? 0
            : 0;
          const current = chartPoints[dataIndex];
          const drift = firstNav && current?.nav ? Number((((current.nav - firstNav) / firstNav) * 100).toFixed(2)) : null;
          const deviationFromMa20 = current?.nav && current.ma20 ? Number((((current.nav - current.ma20) / current.ma20) * 100).toFixed(2)) : null;
          const deviationFromCost = current?.nav && hasCostLine && costNav ? Number((((current.nav - costNav) / costNav) * 100).toFixed(2)) : null;

          return [
            `<div style="font-weight:600;margin-bottom:6px;">悬浮点坐标</div>`,
            `<div>横轴（日期）：${current?.date ?? "--"}</div>`,
            `<div>纵轴（单位净值）：${formatNav(current?.nav ?? null)}</div>`,
            `<div style="margin-top:6px;opacity:0.82;">均线 / 带宽</div>`,
            `<div>MA5：${formatNav(current?.ma5 ?? null)}</div>`,
            `<div>MA10：${formatNav(current?.ma10 ?? null)}</div>`,
            `<div>MA20：${formatNav(current?.ma20 ?? null)}</div>`,
            `<div>MA60：${formatNav(current?.ma60 ?? null)}</div>`,
            `<div>BOLL 上轨：${formatNav(current?.bollUpper ?? null)}</div>`,
            `<div>BOLL 下轨：${formatNav(current?.bollLower ?? null)}</div>`,
            ...(hasCostLine ? [`<div>成本线：${formatNav(costNav)}</div>`] : []),
            `<div style="margin-top:6px;opacity:0.82;">区间判断</div>`,
            `<div>区间涨跌：${formatPercent(drift)}</div>`,
            `<div>相对 MA20：${formatPercent(deviationFromMa20)}</div>`,
            ...(hasCostLine ? [`<div>相对成本：${formatPercent(deviationFromCost)}</div>`] : []),
          ].join("");
        },
      },
      grid: {
        left: 18,
        right: 18,
        top: 54,
        bottom: 32,
        containLabel: true,
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: chartPoints.map((item) => item.date),
        axisLine: {
          lineStyle: {
            color: "rgba(148, 163, 184, 0.22)",
          },
        },
        axisLabel: {
          color: "#95a7c7",
          hideOverlap: true,
        },
        axisTick: {
          show: false,
        },
      },
      yAxis: {
        type: "value",
        min: Number((min - spread * 0.08).toFixed(4)),
        max: Number((max + spread * 0.08).toFixed(4)),
        splitLine: {
          lineStyle: {
            color: "rgba(148, 163, 184, 0.12)",
            type: "dashed",
          },
        },
        axisLabel: {
          color: "#95a7c7",
          formatter: (value: number) => Number(value).toFixed(4),
        },
      },
      series: [
        {
          name: "单位净值",
          type: "line",
          smooth: 0.22,
          showSymbol: false,
          symbolSize: 8,
          emphasis: {
            focus: "series",
            scale: true,
          },
          lineStyle: {
            width: 3,
            color: "#4f8cff",
          },
          itemStyle: {
            color: "#6ee7b7",
          },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(79, 140, 255, 0.35)" },
                { offset: 1, color: "rgba(79, 140, 255, 0.03)" },
              ],
            },
          },
          markPoint: {
            symbolSize: 44,
            label: {
              color: "#ebf2ff",
              fontSize: 11,
            },
            itemStyle: {
              color: "rgba(7, 18, 35, 0.92)",
              borderColor: "rgba(79, 140, 255, 0.45)",
              borderWidth: 1,
            },
            data: [
              { type: "max", name: "区间高点", valueDim: "y", label: { formatter: "高" } },
              { type: "min", name: "区间低点", valueDim: "y", label: { formatter: "低" } },
            ],
          },
          data: chartPoints.map((item) => Number(item.nav.toFixed(4))),
        },
        ...(hasCostLine && costNav !== null
          ? [{
              name: "成本线",
              type: "line" as const,
              showSymbol: false,
              lineStyle: {
                width: 2,
                type: "dotted" as const,
                color: "#fb7185",
              },
              data: chartPoints.map(() => Number(costNav.toFixed(4))),
            }]
          : []),
        {
          name: "MA5",
          type: "line",
          smooth: 0.16,
          showSymbol: false,
          connectNulls: false,
          lineStyle: {
            width: 2,
            color: "#22d3ee",
          },
          data: chartPoints.map((item) => item.ma5),
        },
        {
          name: "MA10",
          type: "line",
          smooth: 0.14,
          showSymbol: false,
          connectNulls: false,
          lineStyle: {
            width: 2,
            color: "#f59e0b",
          },
          data: chartPoints.map((item) => item.ma10),
        },
        {
          name: "MA20",
          type: "line",
          smooth: 0.12,
          showSymbol: false,
          connectNulls: false,
          lineStyle: {
            width: 2,
            color: "#34d399",
          },
          data: chartPoints.map((item) => item.ma20),
        },
        {
          name: "MA60",
          type: "line",
          smooth: 0.08,
          showSymbol: false,
          connectNulls: false,
          lineStyle: {
            width: 2,
            type: "dashed",
            color: "#a78bfa",
          },
          data: chartPoints.map((item) => item.ma60),
        },
        {
          name: "BOLL 上轨",
          type: "line",
          smooth: 0.12,
          showSymbol: false,
          connectNulls: false,
          lineStyle: {
            width: 1.8,
            type: "dashed",
            color: "#f472b6",
            opacity: 0.92,
          },
          data: chartPoints.map((item) => item.bollUpper),
        },
        {
          name: "BOLL 下轨",
          type: "line",
          smooth: 0.12,
          showSymbol: false,
          connectNulls: false,
          lineStyle: {
            width: 1.8,
            type: "dashed",
            color: "#c084fc",
            opacity: 0.92,
          },
          data: chartPoints.map((item) => item.bollLower),
        },
      ],
    };
  }, [chartPoints, costNav, hasCostLine, overlayVisibility]);

  function toggleOverlay(key: OverlayKey) {
    if (key === "cost" && !hasCostLine) {
      return;
    }

    setOverlayVisibility((previous) => ({
      ...previous,
      [key]: !previous[key],
    }));
  }

  function handleLegendSelectChanged(event: { selected?: Record<string, boolean> }) {
    if (!event.selected) {
      return;
    }

    setOverlayVisibility((previous) => {
      const next = { ...previous };

      for (const [name, selected] of Object.entries(event.selected ?? {})) {
        const key = legendNameMap[name];
        if (!key) {
          continue;
        }
        next[key] = selected;
      }

      if (!hasCostLine) {
        next.cost = false;
      }

      return next;
    });
  }

  if (!option || chartPoints.length < 2) {
    return <div className="chart-empty">历史趋势数据不足，暂时画不出像样的曲线。</div>;
  }

  const values = chartPoints.map((item) => item.nav);
  const min = Math.min(...values);
  const max = Math.max(...values);

  return (
    <section className="panel chart-panel">
      <div className="section-head chart-header">
        <div>
          <h3>区间业绩图 + 技术指标</h3>
          <p>这次把 MA5、MA10、MA20、MA60、布林带和持有成本线都叠进去了。上方开关和图例都能控制显隐，悬浮时直接看日期和净值坐标，不用再盲猜。</p>
        </div>
        <div className={`range-return ${signedClass(rangeReturn)}`}>{formatPercent(rangeReturn)}</div>
      </div>

      <div className="range-tabs">
        {RANGE_OPTIONS.map((optionItem) => (
          <button
            key={optionItem.key}
            type="button"
            className={optionItem.key === activeRange ? "active" : ""}
            onClick={() => setActiveRange(optionItem.key)}
          >
            {optionItem.label}
          </button>
        ))}
      </div>

      <div className="overlay-toggle-row spaced-top">
        {overlayMeta.filter((item) => item.key !== "cost" || hasCostLine).map((item) => {
          const active = overlayVisibility[item.key];
          return (
            <button
              key={item.key}
              type="button"
              className={`overlay-toggle${active ? " active" : ""}`}
              onClick={() => toggleOverlay(item.key)}
            >
              <span className="overlay-dot" style={{ backgroundColor: item.color }} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>

      <ReactECharts
        echarts={echarts}
        option={option}
        className="echart-canvas"
        notMerge
        lazyUpdate
        onEvents={{ legendselectchanged: handleLegendSelectChanged }}
      />

      <div className="indicator-grid spaced-top">
        {indicatorCards.map((card) => (
          <article key={card.key} className="indicator-card">
            <span>{card.label}</span>
            <strong className={card.signed ? signedClass(card.value) : undefined}>{card.format(card.value)}</strong>
          </article>
        ))}
      </div>

      <div className="chart-footer">
        <span>{chartPoints[0]?.date}</span>
        <span>
          区间最低 {formatNav(min)} / 最高 {formatNav(max)}
        </span>
        <span>{chartPoints.at(-1)?.date}</span>
      </div>
    </section>
  );
}

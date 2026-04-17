import { useEffect, useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, MarkPointComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import ReactECharts from "echarts-for-react/lib/core";
import type { ChartRange, FundAgentForecast, FundTrendPoint } from "../types";
import {
  buildTrendIndicators,
  calculateBiasRate,
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
  forecast?: FundAgentForecast | null;
};

type OverlayKey = "nav" | "cost" | "ma5" | "ma10" | "ma20" | "ma60" | "bollUpper" | "bollLower";
type AxisMode = "nav" | "percent";

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

const forecastPalette = ["#34d399", "#f59e0b", "#fb7185", "#a78bfa"] as const;

type ForecastSeriesDatum = {
  value: number;
  rawNav: number;
  returnRate: number;
  probability: number;
  scenarioLabel: string;
  scenarioId: string;
  isForecast: true;
  isBaseAnchor?: boolean;
};

function getDefaultOverlayState(hasCostLine: boolean): Record<OverlayKey, boolean> {
  return {
    nav: true,
    cost: hasCostLine,
    ma5: false,
    ma10: false,
    ma20: false,
    ma60: false,
    bollUpper: false,
    bollLower: false,
  };
}

function toPercentChange(value: number | null | undefined, base: number | null | undefined) {
  if (value === null || value === undefined || base === null || base === undefined || !Number.isFinite(base) || base === 0) {
    return null;
  }

  return Number((((value - base) / base) * 100).toFixed(2));
}

function projectValueByMode(value: number | null | undefined, mode: AxisMode, base: number | null | undefined) {
  if (value === null || value === undefined) {
    return null;
  }

  if (mode === "percent") {
    return toPercentChange(value, base);
  }

  return Number(value.toFixed(4));
}

function formatAxisLabel(value: number, mode: AxisMode) {
  return mode === "percent" ? `${Number(value).toFixed(2)}%` : Number(value).toFixed(4);
}

function formatProbability(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  return `${Math.round(Number(value))}%`;
}

export function ChartPanel({ points, costNav = null, forecast = null }: ChartPanelProps) {
  const [activeRange, setActiveRange] = useState<ChartRange>("3M");
  const [axisMode, setAxisMode] = useState<AxisMode>("percent");
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
  const firstNav = chartPoints[0]?.nav ?? null;
  const lastHistoricalPoint = chartPoints.at(-1) ?? null;

  const forecastSeriesDescriptors = useMemo(() => {
    if (!forecast || !lastHistoricalPoint) {
      return [];
    }

    return (forecast.scenarios ?? [])
      .filter((scenario) => Array.isArray(scenario.points) && scenario.points.length > 0)
      .map((scenario, index) => ({
        ...scenario,
        color: forecastPalette[index % forecastPalette.length],
        pointsMap: new Map(scenario.points.map((point) => [point.date, point])),
      }));
  }, [forecast, lastHistoricalPoint]);

  const combinedDates = useMemo(() => {
    const historicalDates = chartPoints.map((item) => item.date);
    const knownDates = new Set(historicalDates);
    const futureDates = Array.from(
      new Set(
        forecastSeriesDescriptors.flatMap((scenario) => scenario.points.map((point) => point.date)),
      ),
    )
      .filter((date) => !knownDates.has(date))
      .sort((left, right) => new Date(`${left}T00:00:00`).getTime() - new Date(`${right}T00:00:00`).getTime());

    return [...historicalDates, ...futureDates];
  }, [chartPoints, forecastSeriesDescriptors]);

  const historicalPointMap = useMemo(() => new Map(chartPoints.map((item) => [item.date, item])), [chartPoints]);

  const indicatorCards = useMemo(
    () => [
      { key: "ma5", label: "5 日均线", value: insights.ma5, format: formatNav, signed: false },
      { key: "ma10", label: "10 日均线", value: insights.ma10, format: formatNav, signed: false },
      { key: "ma20", label: "20 日均线", value: insights.ma20, format: formatNav, signed: false },
      { key: "ma60", label: "60 日均线", value: insights.ma60, format: formatNav, signed: false },
      { key: "deviationFromMa10", label: "MA10 乖离率", value: insights.deviationFromMa10, format: formatPercent, signed: true },
      { key: "deviationFromMa20", label: "MA20 乖离率", value: insights.deviationFromMa20, format: formatPercent, signed: true },
      { key: "deviationFromMa60", label: "MA60 乖离率", value: insights.deviationFromMa60, format: formatPercent, signed: true },
      ...(hasCostLine
        ? [{ key: "deviationFromCost", label: "相对成本线", value: insights.deviationFromCost, format: formatPercent, signed: true }]
        : []),
      { key: "bollWidth20", label: "20 日布林带宽", value: insights.bollWidth20, format: formatPercent, signed: false },
      { key: "annualizedVolatility20d", label: "20 日年化波动率", value: insights.annualizedVolatility20d, format: formatPercent, signed: false },
      { key: "maxDrawdown", label: "区间最大回撤", value: insights.maxDrawdown, format: formatPercent, signed: true },
    ],
    [hasCostLine, insights],
  );

  const option = useMemo<EChartsOption | null>(() => {
    if (chartPoints.length < 2 || !lastHistoricalPoint) {
      return null;
    }

    const project = (value: number | null | undefined) => projectValueByMode(value, axisMode, firstNav);
    const buildHistoricalSeries = (selector: (item: typeof chartPoints[number]) => number | null | undefined) => combinedDates.map((date) => {
      const item = historicalPointMap.get(date);
      return item ? project(selector(item)) : null;
    });

    const mainNavData = buildHistoricalSeries((item) => item.nav);
    const ma5Data = buildHistoricalSeries((item) => item.ma5);
    const ma10Data = buildHistoricalSeries((item) => item.ma10);
    const ma20Data = buildHistoricalSeries((item) => item.ma20);
    const ma60Data = buildHistoricalSeries((item) => item.ma60);
    const bollUpperData = buildHistoricalSeries((item) => item.bollUpper);
    const bollLowerData = buildHistoricalSeries((item) => item.bollLower);
    const costLineData = hasCostLine && costNav !== null
      ? combinedDates.map((date) => (historicalPointMap.has(date) ? project(costNav) : null))
      : [];

    const forecastSeries = forecastSeriesDescriptors.map((scenario) => ({
      name: `预测-${scenario.label}`,
      type: "line" as const,
      smooth: false,
      showSymbol: false,
      connectNulls: false,
      emphasis: {
        focus: "series" as const,
        scale: true,
      },
      lineStyle: {
        width: 2.2,
        type: "dashed" as const,
        color: scenario.color,
        opacity: 0.96,
      },
      itemStyle: {
        color: scenario.color,
      },
      data: combinedDates.map((date) => {
        if (date === lastHistoricalPoint.date) {
          const anchorValue = project(lastHistoricalPoint.nav);
          return anchorValue === null ? null : {
            value: anchorValue,
            rawNav: lastHistoricalPoint.nav,
            returnRate: 0,
            probability: scenario.probability,
            scenarioLabel: scenario.label,
            scenarioId: scenario.id,
            isForecast: true,
            isBaseAnchor: true,
          } satisfies ForecastSeriesDatum;
        }

        const point = scenario.pointsMap.get(date);
        if (!point) {
          return null;
        }

        const value = project(point.nav);
        return value === null ? null : {
          value,
          rawNav: point.nav,
          returnRate: point.returnRate,
          probability: scenario.probability,
          scenarioLabel: scenario.label,
          scenarioId: scenario.id,
          isForecast: true,
        } satisfies ForecastSeriesDatum;
      }),
    }));

    const seriesValueBuckets: number[] = [];
    if (overlayVisibility.nav) {
      seriesValueBuckets.push(...mainNavData.filter((value): value is number => value !== null));
    }
    if (overlayVisibility.ma5) {
      seriesValueBuckets.push(...ma5Data.filter((value): value is number => value !== null));
    }
    if (overlayVisibility.ma10) {
      seriesValueBuckets.push(...ma10Data.filter((value): value is number => value !== null));
    }
    if (overlayVisibility.ma20) {
      seriesValueBuckets.push(...ma20Data.filter((value): value is number => value !== null));
    }
    if (overlayVisibility.ma60) {
      seriesValueBuckets.push(...ma60Data.filter((value): value is number => value !== null));
    }
    if (overlayVisibility.bollUpper) {
      seriesValueBuckets.push(...bollUpperData.filter((value): value is number => value !== null));
    }
    if (overlayVisibility.bollLower) {
      seriesValueBuckets.push(...bollLowerData.filter((value): value is number => value !== null));
    }
    if (hasCostLine && overlayVisibility.cost) {
      seriesValueBuckets.push(...costLineData.filter((value): value is number => value !== null));
    }
    forecastSeriesDescriptors.forEach((scenario) => {
      seriesValueBuckets.push(...scenario.points.map((point) => project(point.nav)).filter((value): value is number => value !== null));
    });

    const fallbackValues = mainNavData.filter((value): value is number => value !== null);
    const allValues = seriesValueBuckets.length > 0 ? seriesValueBuckets : fallbackValues;
    const min = Math.min(...allValues);
    const max = Math.max(...allValues);
    const spread = Math.max(max - min, axisMode === "percent" ? 0.2 : 0.004);
    const axisPadding = spread * (axisMode === "percent" ? 0.05 : 0.04);

    return {
      backgroundColor: "transparent",
      animationDuration: 380,
      legend: {
        top: 0,
        right: 4,
        icon: "roundRect",
        itemWidth: 10,
        itemHeight: 10,
        data: overlayMeta.filter((item) => item.key !== "cost" || hasCostLine).map((item) => item.label),
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
          const items = (Array.isArray(params) ? params : [params]) as Array<{
            dataIndex?: number;
            data?: unknown;
            marker?: string;
          }>;
          const dataIndex = typeof items[0]?.dataIndex === "number" ? items[0].dataIndex : 0;
          const axisDate = combinedDates[dataIndex] ?? "--";
          const current = historicalPointMap.get(axisDate) ?? null;
          const forecastEntries = items
            .map((item) => {
              const data = item.data as Partial<ForecastSeriesDatum> | null;
              if (!data || typeof data !== "object" || data.isForecast !== true || data.isBaseAnchor) {
                return null;
              }
              if (typeof data.rawNav !== "number") {
                return null;
              }
              return {
                marker: item.marker ?? "",
                label: data.scenarioLabel ?? "预测分支",
                probability: data.probability ?? null,
                rawNav: data.rawNav,
                returnRate: data.returnRate ?? null,
              };
            })
            .filter((item): item is { marker: string; label: string; probability: number | null; rawNav: number; returnRate: number | null } => item !== null);

          if (current) {
            const drift = toPercentChange(current.nav ?? null, firstNav);
            const axisValue = project(current.nav ?? null);
            const deviationFromMa10 = calculateBiasRate(current.nav ?? null, current.ma10 ?? null);
            const deviationFromMa20 = calculateBiasRate(current.nav ?? null, current.ma20 ?? null);
            const deviationFromMa60 = calculateBiasRate(current.nav ?? null, current.ma60 ?? null);
            const deviationFromCost = calculateBiasRate(current.nav ?? null, hasCostLine ? costNav : null);

            return [
              `<div style="font-weight:600;margin-bottom:6px;">悬浮点坐标</div>`,
              `<div>横轴（日期）：${axisDate}</div>`,
              `<div>纵轴（${axisMode === "percent" ? "涨跌幅" : "单位净值"}）：${axisValue === null ? "--" : formatAxisLabel(axisValue, axisMode)}</div>`,
              `<div>单位净值：${formatNav(current.nav ?? null)}</div>`,
              `<div>区间涨跌：${formatPercent(drift)}</div>`,
              `<div style="margin-top:6px;opacity:0.82;">均线 / 布林带</div>`,
              `<div>MA5：${formatNav(current.ma5 ?? null)}</div>`,
              `<div>MA10：${formatNav(current.ma10 ?? null)}</div>`,
              `<div>MA20：${formatNav(current.ma20 ?? null)}</div>`,
              `<div>MA60：${formatNav(current.ma60 ?? null)}</div>`,
              `<div>BOLL 上轨：${formatNav(current.bollUpper ?? null)}</div>`,
              `<div>BOLL 下轨：${formatNav(current.bollLower ?? null)}</div>`,
              `<div>BOLL 带宽：${formatPercent(current.bollWidth20 ?? null)}</div>`,
              ...(hasCostLine ? [`<div>成本线：${formatNav(costNav)}</div>`] : []),
              `<div style="margin-top:6px;opacity:0.82;">乖离率（净值-均线）/均线</div>`,
              `<div>MA10 乖离：${formatPercent(deviationFromMa10)}</div>`,
              `<div>MA20 乖离：${formatPercent(deviationFromMa20)}</div>`,
              `<div>MA60 乖离：${formatPercent(deviationFromMa60)}</div>`,
              ...(hasCostLine ? [`<div>相对成本：${formatPercent(deviationFromCost)}</div>`] : []),
              ...(forecastEntries.length > 0
                ? [
                    `<div style="margin-top:6px;opacity:0.82;">未来分支概率</div>`,
                    ...forecastEntries.map((entry) => `${entry.marker}<span>${entry.label}：${formatProbability(entry.probability)} · ${formatNav(entry.rawNav)}（${formatPercent(entry.returnRate)}）</span>`),
                  ]
                : []),
            ].join("");
          }

          if (forecastEntries.length > 0) {
            return [
              `<div style="font-weight:600;margin-bottom:6px;">未来路径预测</div>`,
              `<div>横轴（日期）：${axisDate}</div>`,
              `<div style="margin-top:6px;opacity:0.82;">不同分支</div>`,
              ...forecastEntries.map((entry) => `${entry.marker}<span>${entry.label}：单位净值 ${formatNav(entry.rawNav)} · 相对当前 ${formatPercent(entry.returnRate)} · 概率 ${formatProbability(entry.probability)}</span>`),
            ].join("");
          }

          return `<div style="font-weight:600;">${axisDate}</div>`;
        },
      },
      grid: {
        left: 18,
        right: 18,
        top: 46,
        bottom: 20,
        containLabel: true,
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: combinedDates,
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
        name: axisMode === "percent" ? "涨跌幅" : "单位净值",
        nameTextStyle: {
          color: "#95a7c7",
          padding: [0, 0, 0, 6],
        },
        min: Number((min - axisPadding).toFixed(axisMode === "percent" ? 2 : 4)),
        max: Number((max + axisPadding).toFixed(axisMode === "percent" ? 2 : 4)),
        splitLine: {
          lineStyle: {
            color: "rgba(148, 163, 184, 0.12)",
            type: "dashed",
          },
        },
        axisLabel: {
          color: "#95a7c7",
          formatter: (value: number) => formatAxisLabel(value, axisMode),
        },
      },
      series: [
        {
          name: "单位净值",
          type: "line",
          smooth: false,
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
          data: mainNavData,
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
              data: costLineData,
            }]
          : []),
        {
          name: "MA5",
          type: "line",
          smooth: false,
          showSymbol: false,
          connectNulls: false,
          lineStyle: {
            width: 2,
            color: "#22d3ee",
          },
          data: ma5Data,
        },
        {
          name: "MA10",
          type: "line",
          smooth: false,
          showSymbol: false,
          connectNulls: false,
          lineStyle: {
            width: 2,
            color: "#f59e0b",
          },
          data: ma10Data,
        },
        {
          name: "MA20",
          type: "line",
          smooth: false,
          showSymbol: false,
          connectNulls: false,
          lineStyle: {
            width: 2,
            color: "#34d399",
          },
          data: ma20Data,
        },
        {
          name: "MA60",
          type: "line",
          smooth: false,
          showSymbol: false,
          connectNulls: false,
          lineStyle: {
            width: 2,
            type: "dashed",
            color: "#a78bfa",
          },
          data: ma60Data,
        },
        {
          name: "BOLL 上轨",
          type: "line",
          smooth: false,
          showSymbol: false,
          connectNulls: false,
          lineStyle: {
            width: 1.8,
            type: "dashed",
            color: "#f472b6",
            opacity: 0.92,
          },
          data: bollUpperData,
        },
        {
          name: "BOLL 下轨",
          type: "line",
          smooth: false,
          showSymbol: false,
          connectNulls: false,
          lineStyle: {
            width: 1.8,
            type: "dashed",
            color: "#c084fc",
            opacity: 0.92,
          },
          data: bollLowerData,
        },
        ...forecastSeries,
      ],
    };
  }, [
    axisMode,
    chartPoints,
    combinedDates,
    costNav,
    firstNav,
    forecastSeriesDescriptors,
    hasCostLine,
    historicalPointMap,
    lastHistoricalPoint,
    overlayVisibility,
  ]);

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
  const forecastEndDate = forecastSeriesDescriptors.flatMap((scenario) => scenario.points.map((point) => point.date)).at(-1) ?? null;

  return (
    <section className="panel chart-panel">
      <div className="section-head chart-header">
        <div>
          <h3>区间业绩图 + 技术指标 + 未来路径预测</h3>
          <p>主折线仍然是历史净值；如果已经跑过 AI 分析，最右侧会继续接出多条虚线预测分支，鼠标移上去会额外显示对应概率。</p>
          <p className="chart-formula-note">乖离率统一按 (单位净值 - 对应均线) / 对应均线 × 100% 计算，BOLL 默认使用 20 日中轨 ± 2 倍标准差。</p>
        </div>
        <div className={`range-return ${signedClass(rangeReturn)}`}>{formatPercent(rangeReturn)}</div>
      </div>

      <div className="chart-toolbar">
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

        <div className="axis-mode-toggle">
          <button type="button" className={axisMode === "percent" ? "active" : ""} onClick={() => setAxisMode("percent")}>
            涨跌幅
          </button>
          <button type="button" className={axisMode === "nav" ? "active" : ""} onClick={() => setAxisMode("nav")}>
            单位净值
          </button>
        </div>
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

      {forecastSeriesDescriptors.length > 0 ? (
        <div className="forecast-branch-row spaced-top">
          {forecastSeriesDescriptors.map((scenario) => (
            <article key={scenario.id} className="forecast-branch-chip">
              <div className="forecast-branch-chip-head">
                <span className="overlay-dot" style={{ backgroundColor: scenario.color }} />
                <strong>{scenario.label}</strong>
                <em>概率 {formatProbability(scenario.probability)}</em>
              </div>
              <p>目标 {formatPercent(scenario.targetReturn)} · {scenario.summary}</p>
            </article>
          ))}
        </div>
      ) : null}

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
          区间最低 {formatNav(min)} / 最高 {formatNav(max)} · 区间涨跌 {formatPercent(rangeReturn)}{forecastEndDate ? ` · AI 预测延伸至 ${forecastEndDate}` : ""}
        </span>
        <span>{forecastEndDate ?? chartPoints.at(-1)?.date}</span>
      </div>
    </section>
  );
}


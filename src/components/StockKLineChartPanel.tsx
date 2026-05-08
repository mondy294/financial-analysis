import { useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import { BarChart, CandlestickChart, LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import ReactECharts from "echarts-for-react/lib/core";
import type { ChartRange, FundAgentForecast, StockAnalysisResponse } from "../types";
import { filterTrendByRange, formatPercent, RANGE_OPTIONS, signedClass } from "../utils/fund";

use([CandlestickChart, LineChart, BarChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

type StockKLineChartPanelProps = {
  detail: StockAnalysisResponse;
  forecast?: FundAgentForecast | null;
};

type OverlayKey = "kline" | "ma5" | "ma10" | "ma20" | "ma60" | "bollUpper" | "bollLower";

const overlayMeta: Array<{ key: OverlayKey; label: string; color: string }> = [
  { key: "kline", label: "日 K", color: "#ef4444" },
  { key: "ma5", label: "MA5", color: "#22d3ee" },
  { key: "ma10", label: "MA10", color: "#f59e0b" },
  { key: "ma20", label: "MA20", color: "#34d399" },
  { key: "ma60", label: "MA60", color: "#a78bfa" },
  { key: "bollUpper", label: "BOLL 上轨", color: "#f472b6" },
  { key: "bollLower", label: "BOLL 下轨", color: "#c084fc" },
];

const forecastPalette = ["#38bdf8", "#f59e0b", "#f97316", "#a78bfa"] as const;

function formatPrice(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  return Number(value).toFixed(2);
}

function formatVolume(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  const numeric = Number(value);
  if (numeric >= 1e8) {
    return `${(numeric / 1e8).toFixed(2)} 亿`;
  }
  if (numeric >= 1e4) {
    return `${(numeric / 1e4).toFixed(2)} 万`;
  }
  return numeric.toFixed(0);
}

export function StockKLineChartPanel({ detail, forecast = null }: StockKLineChartPanelProps) {
  const [activeRange, setActiveRange] = useState<ChartRange>("3M");
  const filteredPoints = useMemo(() => filterTrendByRange(detail.trendAnalysis.points, activeRange), [detail.trendAnalysis.points, activeRange]);
  const [overlayVisibility, setOverlayVisibility] = useState<Record<OverlayKey, boolean>>({
    kline: true,
    ma5: true,
    ma10: true,
    ma20: true,
    ma60: false,
    bollUpper: false,
    bollLower: false,
  });

  const lastPoint = filteredPoints.at(-1) ?? null;
  const historicalDates = filteredPoints.map((item) => item.date);
  const futureDates = Array.from(
    new Set((forecast?.scenarios ?? []).flatMap((scenario) => scenario.points.map((point) => point.date))),
  ).filter((date) => !historicalDates.includes(date));
  const combinedDates = [...historicalDates, ...futureDates];
  const pointMap = useMemo(() => new Map(filteredPoints.map((item) => [item.date, item])), [filteredPoints]);

  const option = useMemo<EChartsOption | null>(() => {
    if (filteredPoints.length < 2 || !lastPoint) {
      return null;
    }

    const candleData = combinedDates.map((date) => {
      const point = pointMap.get(date);
      return point ? [point.open, point.close, point.low, point.high] : null;
    });
    const ma5Data = combinedDates.map((date) => pointMap.get(date)?.ma5 ?? null);
    const ma10Data = combinedDates.map((date) => pointMap.get(date)?.ma10 ?? null);
    const ma20Data = combinedDates.map((date) => pointMap.get(date)?.ma20 ?? null);
    const ma60Data = combinedDates.map((date) => pointMap.get(date)?.ma60 ?? null);
    const bollUpperData = combinedDates.map((date) => pointMap.get(date)?.bollUpper ?? null);
    const bollLowerData = combinedDates.map((date) => pointMap.get(date)?.bollLower ?? null);
    const volumeData = combinedDates.map((date) => {
      const point = pointMap.get(date);
      if (!point || point.volume === null || point.volume === undefined) {
        return null;
      }
      return {
        value: point.volume,
        itemStyle: {
          color: point.close >= point.open ? "#ef4444" : "#22c55e",
        },
      };
    });

    const forecastSeries = (forecast?.scenarios ?? []).map((scenario, index) => ({
      name: `预测-${scenario.label}`,
      type: "line" as const,
      smooth: false,
      showSymbol: false,
      connectNulls: false,
      lineStyle: {
        width: 2,
        type: "dashed" as const,
        color: forecastPalette[index % forecastPalette.length],
      },
      data: combinedDates.map((date) => {
        if (date === lastPoint.date) {
          return lastPoint.close;
        }
        const point = scenario.points.find((item) => item.date === date);
        return point ? point.nav : null;
      }),
    }));

    return {
      animationDuration: 320,
      backgroundColor: "transparent",
      legend: {
        top: 0,
        right: 4,
        textStyle: { color: "#95a7c7" },
      },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        backgroundColor: "rgba(6, 17, 31, 0.94)",
        borderColor: "rgba(79, 140, 255, 0.36)",
        borderWidth: 1,
        textStyle: { color: "#ebf2ff" },
        formatter: (params: unknown) => {
          const items = (Array.isArray(params) ? params : [params]) as Array<{ dataIndex?: number }>;
          const dataIndex = typeof items[0]?.dataIndex === "number" ? items[0].dataIndex : 0;
          const axisDate = combinedDates[dataIndex] ?? "--";
          const point = pointMap.get(axisDate) ?? null;
          const scenarioRows = (forecast?.scenarios ?? [])
            .map((scenario) => {
              const target = scenario.points.find((item) => item.date === axisDate);
              return target
                ? `<div>${scenario.label}：${formatPrice(target.nav)}（${formatPercent(target.returnRate)}，概率 ${Math.round(scenario.probability)}%）</div>`
                : null;
            })
            .filter(Boolean)
            .join("");

          if (!point) {
            return [`<div style="font-weight:600;margin-bottom:6px;">${axisDate}</div>`, scenarioRows || "<div>暂无历史 K 线，只有未来预测路径。</div>"].join("");
          }

          return [
            `<div style="font-weight:600;margin-bottom:6px;">${axisDate}</div>`,
            `<div>开盘：${formatPrice(point.open)}</div>`,
            `<div>收盘：${formatPrice(point.close)}</div>`,
            `<div>最高 / 最低：${formatPrice(point.high)} / ${formatPrice(point.low)}</div>`,
            `<div>振幅：${formatPercent(point.amplitude)}</div>`,
            `<div>换手率：${formatPercent(point.turnoverRate)}</div>`,
            `<div>MA5 / MA10：${formatPrice(point.ma5)} / ${formatPrice(point.ma10)}</div>`,
            `<div>MA20 / MA60：${formatPrice(point.ma20)} / ${formatPrice(point.ma60)}</div>`,
            `<div>BOLL 上轨 / 下轨：${formatPrice(point.bollUpper)} / ${formatPrice(point.bollLower)}</div>`,
            scenarioRows,
          ].join("");
        },
      },
      axisPointer: {
        link: [{ xAxisIndex: [0, 1] }],
      },
      grid: [
        { left: 18, right: 18, top: 52, height: "62%", containLabel: true },
        { left: 18, right: 18, top: "78%", height: "14%", containLabel: true },
      ],
      xAxis: [
        {
          type: "category",
          data: combinedDates,
          scale: true,
          boundaryGap: true,
          axisLine: { lineStyle: { color: "rgba(148, 163, 184, 0.22)" } },
          axisLabel: { color: "#95a7c7", hideOverlap: true },
          splitLine: { show: false },
        },
        {
          type: "category",
          gridIndex: 1,
          data: combinedDates,
          scale: true,
          boundaryGap: true,
          axisLine: { lineStyle: { color: "rgba(148, 163, 184, 0.22)" } },
          axisLabel: { show: false },
          axisTick: { show: false },
          splitLine: { show: false },
        },
      ],
      yAxis: [
        {
          scale: true,
          splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.12)", type: "dashed" } },
          axisLabel: { color: "#95a7c7", formatter: (value: number) => formatPrice(value) },
        },
        {
          gridIndex: 1,
          scale: true,
          splitNumber: 2,
          axisLabel: { color: "#95a7c7", formatter: (value: number) => formatVolume(value) },
          splitLine: { show: false },
        },
      ],
      series: [
        ...(overlayVisibility.kline
          ? [{
              name: "日 K",
              type: "candlestick",
              data: candleData,
              itemStyle: {
                color: "#ef4444",
                color0: "#22c55e",
                borderColor: "#ef4444",
                borderColor0: "#22c55e",
              },
              emphasis: { focus: "series" },
            }]
          : []),
        ...(overlayVisibility.ma5
          ? [{
              name: "MA5",
              type: "line",
              data: ma5Data,
              smooth: false,
              showSymbol: false,
              lineStyle: { width: 1.8, color: "#22d3ee" },
            }]
          : []),
        ...(overlayVisibility.ma10
          ? [{
              name: "MA10",
              type: "line",
              data: ma10Data,
              smooth: false,
              showSymbol: false,
              lineStyle: { width: 1.8, color: "#f59e0b" },
            }]
          : []),
        ...(overlayVisibility.ma20
          ? [{
              name: "MA20",
              type: "line",
              data: ma20Data,
              smooth: false,
              showSymbol: false,
              lineStyle: { width: 1.8, color: "#34d399" },
            }]
          : []),
        ...(overlayVisibility.ma60
          ? [{
              name: "MA60",
              type: "line",
              data: ma60Data,
              smooth: false,
              showSymbol: false,
              lineStyle: { width: 1.6, color: "#a78bfa", type: "dashed" },
            }]
          : []),
        ...(overlayVisibility.bollUpper
          ? [{
              name: "BOLL 上轨",
              type: "line",
              data: bollUpperData,
              smooth: false,
              showSymbol: false,
              lineStyle: { width: 1.4, color: "#f472b6", type: "dashed" },
            }]
          : []),
        ...(overlayVisibility.bollLower
          ? [{
              name: "BOLL 下轨",
              type: "line",
              data: bollLowerData,
              smooth: false,
              showSymbol: false,
              lineStyle: { width: 1.4, color: "#c084fc", type: "dashed" },
            }]
          : []),
        ...forecastSeries,
        {
          name: "成交量",
          type: "bar",
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: volumeData,
        },
      ],
    } as EChartsOption;
  }, [combinedDates, detail, filteredPoints, forecast, lastPoint, overlayVisibility, pointMap]);

  if (!option || filteredPoints.length < 2 || !lastPoint) {
    return <div className="chart-empty">历史 K 线数据不足，暂时画不出像样的走势图。</div>;
  }

  const indicatorCards: Array<{
    key: string;
    label: string;
    value: number | null;
    signed: boolean;
    percent?: boolean;
  }> = [
    { key: "open", label: "最新开盘", value: lastPoint.open, signed: false },
    { key: "close", label: "最新收盘", value: lastPoint.close, signed: false },
    { key: "high", label: "区间内最新高点", value: lastPoint.high, signed: false },
    { key: "low", label: "区间内最新低点", value: lastPoint.low, signed: false },
    { key: "bias20", label: "MA20 乖离率", value: detail.trendAnalysis.latest.biasToMa20, signed: true, percent: true },
    { key: "bias60", label: "MA60 乖离率", value: detail.trendAnalysis.latest.biasToMa60, signed: true, percent: true },
    { key: "amplitude", label: "最新振幅", value: detail.trendAnalysis.latest.amplitude, signed: false, percent: true },
    { key: "turnover", label: "最新换手率", value: detail.trendAnalysis.latest.turnoverRate, signed: false, percent: true },
  ];

  const latestScenarioDate = forecast?.scenarios.flatMap((scenario) => scenario.points.map((point) => point.date)).at(-1) ?? null;

  return (
    <section className="panel chart-panel">
      <div className="section-head chart-header">
        <div>
          <h3>日 K 线 + 均线 / 布林带 + 未来路径预测</h3>
          <p>主图直接看开高低收，红涨绿跌；下方保留成交量，右侧预测分支继续沿收盘价往后延伸。</p>
          <p className="chart-formula-note">默认按前复权日线展示，均线与布林带统一基于收盘价计算。</p>
        </div>
        <div className={`range-return ${signedClass(detail.trendAnalysis.returns.range)}`}>{formatPercent(detail.trendAnalysis.returns.range)}</div>
      </div>

      <div className="chart-toolbar">
        <div className="range-tabs">
          {RANGE_OPTIONS.map((optionItem) => (
            <button key={optionItem.key} type="button" className={optionItem.key === activeRange ? "active" : ""} onClick={() => setActiveRange(optionItem.key)}>
              {optionItem.label}
            </button>
          ))}
        </div>
      </div>

      <div className="overlay-toggle-row spaced-top">
        {overlayMeta.map((item) => (
          <button
            key={item.key}
            type="button"
            className={`overlay-toggle${overlayVisibility[item.key] ? " active" : ""}`}
            onClick={() => setOverlayVisibility((previous) => ({ ...previous, [item.key]: !previous[item.key] }))}
          >
            <span className="overlay-dot" style={{ backgroundColor: item.color }} />
            <span>{item.label}</span>
          </button>
        ))}
      </div>

      {forecast?.scenarios?.length ? (
        <div className="forecast-branch-row spaced-top">
          {forecast.scenarios.map((scenario, index) => (
            <article key={scenario.id} className="forecast-branch-chip">
              <div className="forecast-branch-chip-head">
                <span className="overlay-dot" style={{ backgroundColor: forecastPalette[index % forecastPalette.length] }} />
                <strong>{scenario.label}</strong>
                <em>概率 {Math.round(scenario.probability)}%</em>
              </div>
              <p>目标 {formatPercent(scenario.targetReturn)} · {scenario.summary}</p>
            </article>
          ))}
        </div>
      ) : null}

      <ReactECharts echarts={echarts} option={option} className="echart-canvas" style={{ width: "100%", height: 560 }} notMerge lazyUpdate />

      <div className="indicator-grid spaced-top">
        {indicatorCards.map((card) => (
          <article key={card.key} className="indicator-card">
            <span>{card.label}</span>
            <strong className={card.signed ? signedClass(card.value) : undefined}>{card.percent ? formatPercent(card.value) : formatPrice(card.value)}</strong>
          </article>
        ))}
      </div>

      <div className="chart-footer">
        <span>{filteredPoints[0]?.date}</span>
        <span>
          最新信号 {detail.trendAnalysis.latest.signal} · 近 20 日 {formatPercent(detail.trendAnalysis.returns.day20)} · 近 90 日波动 {formatPercent(detail.trendAnalysis.risk.volatility90d)}{latestScenarioDate ? ` · AI 预测延伸至 ${latestScenarioDate}` : ""}
        </span>
        <span>{latestScenarioDate ?? filteredPoints.at(-1)?.date}</span>
      </div>
    </section>
  );
}

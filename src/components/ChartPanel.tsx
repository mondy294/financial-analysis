import { useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import ReactECharts from "echarts-for-react/lib/core";
import type { ChartRange, FundTrendPoint } from "../types";
import { calculateRangeReturn, filterTrendByRange, formatNav, formatPercent, RANGE_OPTIONS, signedClass } from "../utils/fund";

type ChartPanelProps = {
  points: FundTrendPoint[];
};

use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

export function ChartPanel({ points }: ChartPanelProps) {
  const [activeRange, setActiveRange] = useState<ChartRange>("3M");

  const filteredPoints = useMemo(() => filterTrendByRange(points, activeRange), [points, activeRange]);
  const chartPoints = useMemo(
    () => filteredPoints.filter((item): item is FundTrendPoint & { nav: number } => item.nav !== null && Number.isFinite(item.nav)),
    [filteredPoints],
  );
  const rangeReturn = useMemo(() => calculateRangeReturn(chartPoints), [chartPoints]);

  const option = useMemo<EChartsOption | null>(() => {
    if (chartPoints.length < 2) {
      return null;
    }

    const values = chartPoints.map((item) => item.nav);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const firstNav = chartPoints[0]?.nav ?? null;

    return {
      backgroundColor: "transparent",
      animationDuration: 380,
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
          type: "line",
          lineStyle: {
            color: "rgba(110, 231, 183, 0.55)",
            width: 1,
          },
        },
        formatter: (params: any) => {
          const point = Array.isArray(params) ? params[0] : params;
          const dataIndex = typeof point.dataIndex === "number" ? point.dataIndex : 0;
          const current = chartPoints[dataIndex];
          const drift = firstNav && current?.nav ? Number((((current.nav - firstNav) / firstNav) * 100).toFixed(2)) : null;

          return [
            `<div style="font-weight:600;margin-bottom:6px;">${current?.date ?? "--"}</div>`,
            `<div>横轴：${current?.date ?? "--"}</div>`,
            `<div>纵轴：${formatNav(current?.nav ?? null)}</div>`,
            `<div>区间涨跌：${formatPercent(drift)}</div>`,
          ].join("");
        },
      },
      grid: {
        left: 18,
        right: 18,
        top: 28,
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
        min: Number((min * 0.995).toFixed(4)),
        max: Number((max * 1.005).toFixed(4)),
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
          data: chartPoints.map((item) => Number(item.nav.toFixed(4))),
        },
      ],
    };
  }, [chartPoints]);

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
          <h3>区间业绩图</h3>
          <p>用了更正常的图表组件。鼠标悬浮就能直接看当前点的日期和净值，终于不是看一根寂寞折线瞎猜了。</p>
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

      <ReactECharts echarts={echarts} option={option} className="echart-canvas" notMerge lazyUpdate />

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

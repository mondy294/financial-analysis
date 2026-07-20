import { useMemo, type ReactNode } from "react";
import ReactECharts from "echarts-for-react";
import type { EventStatsEvent } from "@/api/client";
import { RETURN_KEYS, fmtPct, statsOf } from "@/lib/eventStatsLabels";

const SHORT: Record<string, string> = {
  return_1: "1日",
  return_3: "3日",
  return_5: "5日",
  return_10: "10日",
  return_20: "20日",
  return_60: "60日",
  return_horizon: "窗末",
};

type Props = {
  summary: Record<string, unknown>;
  events?: EventStatsEvent[];
};

type Row = {
  key: string;
  label: string;
  mean: number | null;
  median: number | null;
  p10: number | null;
  p90: number | null;
  win: number | null;
  n: number;
};

const ACCENT = "#0b6e4f";
const NEG = "#c23b22";
const MUTED = "#5c6b7a";

/** 详情页图表（ECharts）：均收益+中位数+胜率 / P10–P90 / 10日分布 */
export function RunDetailCharts({ summary, events = [] }: Props) {
  const rows = useMemo<Row[]>(
    () =>
      RETURN_KEYS.map((key) => {
        const s = statsOf(summary, key);
        return {
          key,
          label: SHORT[key] || key,
          mean: s.mean ?? null,
          median: s.median ?? null,
          p10: s.p10 ?? null,
          p90: s.p90 ?? null,
          win: s.win_rate ?? null,
          n: s.n_valid ?? 0,
        };
      }).filter((r) => r.n > 0 || r.mean != null || r.median != null),
    [summary],
  );

  const hist = useMemo(
    () => buildHistogram(events.map((e) => e.return_10), 16),
    [events],
  );

  const overviewOpt = useMemo(() => buildOverviewOption(rows), [rows]);
  const spreadOpt = useMemo(() => buildSpreadOption(rows), [rows]);
  const histOpt = useMemo(() => buildHistOption(hist), [hist]);

  if (!rows.length) {
    return (
      <div className="panel" style={{ marginBottom: "0.85rem" }}>
        <div className="panel-head">图表</div>
        <p className="muted" style={{ padding: "0.75rem 1rem" }}>
          暂无聚合指标可展示
        </p>
      </div>
    );
  }

  return (
    <div className="es-charts">
      <ChartBlock
        title="远期收益概览"
        footnote="柱：各期平均收益 / 中位数收益（相对信号日收盘）。折线：胜率（收益>0 占比，右轴）。"
      >
        <ReactECharts option={overviewOpt} style={{ height: 340 }} notMerge lazyUpdate />
      </ChartBlock>
      <ChartBlock
        title="收益离散度（P10–中位–P90）"
        footnote="箱线近似：须端为 P10/P90，盒中线为中位数。区间越长，结果越不稳定。"
      >
        <ReactECharts option={spreadOpt} style={{ height: 320 }} notMerge lazyUpdate />
      </ChartBlock>
      <ChartBlock
        title="10 日收益分布"
        footnote={`基于已加载事件（${events.length} 条）；虚线=0%，实线=均值，点线=中位数。`}
      >
        {hist.bins.length ? (
          <ReactECharts option={histOpt} style={{ height: 300 }} notMerge lazyUpdate />
        ) : (
          <p className="muted" style={{ padding: "0.5rem 0" }}>
            暂无事件明细
          </p>
        )}
      </ChartBlock>
    </div>
  );
}

function ChartBlock({
  title,
  footnote,
  children,
}: {
  title: string;
  footnote: string;
  children: ReactNode;
}) {
  return (
    <div className="panel es-chart-block" style={{ marginBottom: "0.75rem" }}>
      <div className="panel-head">{title}</div>
      <div style={{ padding: "0.5rem 0.75rem 0.25rem" }}>{children}</div>
      <p className="muted es-chart-note">{footnote}</p>
    </div>
  );
}

function buildOverviewOption(rows: Row[]) {
  const cats = rows.map((r) => r.label);
  return {
    color: [ACCENT, "#6aa890", MUTED],
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params: unknown) => {
        const list = params as Array<{
          seriesName: string;
          value: number | null;
          marker: string;
          axisValue: string;
        }>;
        if (!list?.length) return "";
        const lines = list.map((p) => {
          if (p.value == null || Number.isNaN(Number(p.value))) {
            return `${p.marker} ${p.seriesName}：—`;
          }
          const text =
            p.seriesName === "胜率"
              ? `${(Number(p.value) * 100).toFixed(1)}%`
              : fmtPct(Number(p.value));
          return `${p.marker} ${p.seriesName}：${text}`;
        });
        return `${list[0].axisValue}<br/>${lines.join("<br/>")}`;
      },
    },
    legend: { data: ["平均收益", "中位数收益", "胜率"], top: 4 },
    grid: { left: 52, right: 56, top: 44, bottom: 36 },
    xAxis: { type: "category", data: cats, axisLabel: { color: MUTED } },
    yAxis: [
      {
        type: "value",
        name: "收益",
        axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(0)}%`, color: MUTED },
        splitLine: { lineStyle: { type: "dashed", opacity: 0.4 } },
      },
      {
        type: "value",
        name: "胜率",
        min: 0,
        max: 1,
        axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(0)}%`, color: MUTED },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: "平均收益",
        type: "bar",
        data: rows.map((r) => r.mean),
        barMaxWidth: 26,
        itemStyle: {
          color: (p: { value: number }) => (Number(p.value) >= 0 ? ACCENT : NEG),
          borderRadius: [3, 3, 0, 0],
        },
      },
      {
        name: "中位数收益",
        type: "bar",
        data: rows.map((r) => r.median),
        barMaxWidth: 26,
        itemStyle: {
          color: (p: { value: number }) =>
            Number(p.value) >= 0 ? "rgba(11,110,79,0.4)" : "rgba(194,59,34,0.4)",
          borderRadius: [3, 3, 0, 0],
        },
      },
      {
        name: "胜率",
        type: "line",
        yAxisIndex: 1,
        data: rows.map((r) => r.win),
        smooth: true,
        symbol: "circle",
        symbolSize: 8,
        lineStyle: { width: 2, color: MUTED },
        itemStyle: { color: MUTED },
      },
    ],
  };
}

function buildSpreadOption(rows: Row[]) {
  // boxplot: [min, Q1, median, Q3, max] ≈ [p10, p10, median, p90, p90]
  const labels = rows.map((r) => r.label);
  const boxData = rows.map((r) => {
    const p10 = r.p10 ?? r.median ?? 0;
    const p90 = r.p90 ?? r.median ?? 0;
    const med = r.median ?? (p10 + p90) / 2;
    return [p10, p10, med, p90, p90];
  });

  return {
    tooltip: {
      trigger: "item",
      formatter: (p: { dataIndex: number }) => {
        const r = rows[p.dataIndex];
        if (!r) return "";
        return [
          `<b>${r.label}</b>`,
          `P10：${fmtPct(r.p10)}`,
          `中位数：${fmtPct(r.median)}`,
          `P90：${fmtPct(r.p90)}`,
          `均值：${fmtPct(r.mean)}`,
          `n=${r.n}`,
        ].join("<br/>");
      },
    },
    grid: { left: 56, right: 28, top: 24, bottom: 40 },
    xAxis: {
      type: "category",
      data: labels,
      axisLabel: { color: MUTED },
    },
    yAxis: {
      type: "value",
      axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(0)}%`, color: MUTED },
      splitLine: { lineStyle: { type: "dashed", opacity: 0.4 } },
    },
    series: [
      {
        name: "离散度",
        type: "boxplot",
        data: boxData,
        itemStyle: {
          color: "rgba(11,110,79,0.18)",
          borderColor: ACCENT,
        },
        emphasis: { itemStyle: { borderWidth: 2 } },
      },
      {
        name: "均值",
        type: "scatter",
        data: rows.map((r, i) => [i, r.mean]),
        symbolSize: 8,
        itemStyle: { color: NEG },
        tooltip: {
          formatter: (p: { dataIndex: number }) => {
            const r = rows[p.dataIndex];
            return r ? `${r.label} 均值：${fmtPct(r.mean)}` : "";
          },
        },
      },
    ],
  };
}

function buildHistOption(hist: {
  bins: Array<{ label: string; count: number; mid: number; from: number; to: number }>;
  mean: number | null;
  median: number | null;
}) {
  const cats = hist.bins.map((b) => b.label);
  const markAt = (value: number) => cats[nearestCatIndex(hist.bins, value)] ?? cats[0];
  const markLine: Array<Record<string, unknown>> = [
    {
      xAxis: markAt(0),
      name: "0%",
      lineStyle: { type: "dashed", color: MUTED },
      label: { formatter: "0%" },
    },
  ];
  if (hist.mean != null) {
    markLine.push({
      xAxis: markAt(hist.mean),
      name: "均值",
      lineStyle: { type: "solid", color: "#1a2332", width: 1.5 },
      label: { formatter: `均值 ${fmtPct(hist.mean)}` },
    });
  }
  if (hist.median != null) {
    markLine.push({
      xAxis: markAt(hist.median),
      name: "中位",
      lineStyle: { type: "dotted", color: ACCENT, width: 2 },
      label: { formatter: `中位 ${fmtPct(hist.median)}` },
    });
  }

  return {
    color: [ACCENT],
    tooltip: {
      trigger: "axis",
      formatter: (params: unknown) => {
        const list = params as Array<{ dataIndex: number; marker: string }>;
        const i = list?.[0]?.dataIndex ?? 0;
        const b = hist.bins[i];
        if (!b) return "";
        return `${fmtPct(b.from)} ~ ${fmtPct(b.to)}<br/>${list[0].marker} 次数：${b.count}`;
      },
    },
    grid: { left: 48, right: 24, top: 36, bottom: 44 },
    xAxis: {
      type: "category",
      data: cats,
      name: "10日收益(%)",
      axisLabel: { color: MUTED, interval: 1 },
    },
    yAxis: {
      type: "value",
      name: "事件数",
      axisLabel: { color: MUTED },
      splitLine: { lineStyle: { type: "dashed", opacity: 0.4 } },
    },
    series: [
      {
        type: "bar",
        data: hist.bins.map((b) => b.count),
        barMaxWidth: 36,
        itemStyle: { color: ACCENT, opacity: 0.8, borderRadius: [3, 3, 0, 0] },
        markLine: {
          symbol: "none",
          label: { color: MUTED, fontSize: 10 },
          data: markLine,
        },
      },
    ],
  };
}

function nearestCatIndex(bins: Array<{ mid: number }>, value: number): number {
  if (!bins.length) return 0;
  let best = 0;
  let bestDist = Infinity;
  bins.forEach((b, i) => {
    const d = Math.abs(b.mid - value);
    if (d < bestDist) {
      bestDist = d;
      best = i;
    }
  });
  return best;
}

function buildHistogram(values: Array<number | null | undefined>, bins: number) {
  const nums = values.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (!nums.length) {
    return {
      bins: [] as Array<{ label: string; count: number; mid: number; from: number; to: number }>,
      mean: null as number | null,
      median: null as number | null,
    };
  }
  let lo = Math.min(...nums);
  let hi = Math.max(...nums);
  if (lo === hi) {
    lo -= 0.01;
    hi += 0.01;
  }
  const width = (hi - lo) / bins;
  const counts = Array.from({ length: bins }, () => 0);
  for (const v of nums) {
    let idx = Math.floor((v - lo) / width);
    if (idx >= bins) idx = bins - 1;
    if (idx < 0) idx = 0;
    counts[idx] += 1;
  }
  const sorted = [...nums].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  const median =
    sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
  const mean = nums.reduce((a, b) => a + b, 0) / nums.length;
  return {
    mean,
    median,
    bins: counts.map((count, i) => {
      const from = lo + i * width;
      const to = from + width;
      const midV = from + width / 2;
      return { label: (midV * 100).toFixed(0), count, mid: midV, from, to };
    }),
  };
}

import { useMemo, type ReactNode } from "react";
import ReactECharts from "echarts-for-react";
import type { EventStatsEvent, EventStatsRun } from "@/api/client";
import {
  COMPARE_COLORS,
  RETURN_SHORT,
  runCompareLabel,
} from "@/lib/eventStatsCompare";
import { RETURN_KEYS, fmtPct, statsOf } from "@/lib/eventStatsLabels";

const MUTED = "#5c6b7a";

type RunBundle = {
  run: EventStatsRun;
  events: EventStatsEvent[];
  color: string;
  label: string;
};

type Props = {
  runs: EventStatsRun[];
  eventsByRunId: Record<string, EventStatsEvent[]>;
};

/** 多任务叠对比图表：均值/中位柱、胜率线、离散度、10日分布 */
export function CompareCharts({ runs, eventsByRunId }: Props) {
  const bundles = useMemo<RunBundle[]>(
    () =>
      runs.map((run, i) => ({
        run,
        events: eventsByRunId[run.run_id] || [],
        color: COMPARE_COLORS[i % COMPARE_COLORS.length],
        label: runCompareLabel(run, i),
      })),
    [runs, eventsByRunId],
  );

  const horizonLabels = useMemo(() => {
    const keys = RETURN_KEYS.filter((key) =>
      bundles.some((b) => {
        const s = statsOf(b.run.summary as Record<string, unknown>, key);
        return (s.n_valid ?? 0) > 0 || s.mean != null || s.median != null;
      }),
    );
    return keys.map((k) => ({ key: k, label: RETURN_SHORT[k] || k }));
  }, [bundles]);

  const returnsOpt = useMemo(
    () => buildReturnsOption(bundles, horizonLabels),
    [bundles, horizonLabels],
  );
  const winOpt = useMemo(
    () => buildWinRateOption(bundles, horizonLabels),
    [bundles, horizonLabels],
  );
  const spreadOpt = useMemo(
    () => buildSpreadOption(bundles, horizonLabels),
    [bundles, horizonLabels],
  );
  const histOpt = useMemo(() => buildHistOption(bundles), [bundles]);

  if (!bundles.length || !horizonLabels.length) {
    return (
      <div className="panel" style={{ marginBottom: "0.85rem" }}>
        <div className="panel-head">对比图表</div>
        <p className="muted" style={{ padding: "0.75rem 1rem" }}>
          暂无可用指标
        </p>
      </div>
    );
  }

  return (
    <div className="es-charts">
      <ChartBlock
        title="远期收益对比（均值 / 中位数）"
        footnote="分组柱：各任务在各期的平均收益（实心）与中位数收益（半透明）。悬停查看数值。"
      >
        <ReactECharts option={returnsOpt} style={{ height: 360 }} notMerge lazyUpdate />
      </ChartBlock>
      <ChartBlock
        title="胜率对比"
        footnote="折线：各期收益>0 占比。同条件任务可直接看哪条更高更稳。"
      >
        <ReactECharts option={winOpt} style={{ height: 300 }} notMerge lazyUpdate />
      </ChartBlock>
      <ChartBlock
        title="收益离散度对比（P10–中位–P90）"
        footnote="箱线：须端≈P10/P90，盒中线=中位数。同色为同一任务；区间越长波动越大。"
      >
        <ReactECharts option={spreadOpt} style={{ height: 340 }} notMerge lazyUpdate />
      </ChartBlock>
      <ChartBlock
        title="10 日收益分布对比"
        footnote="半透明叠柱，共用分箱；虚线=0%。基于各任务已加载事件（最多 500 条/任务）。"
      >
        <ReactECharts option={histOpt} style={{ height: 320 }} notMerge lazyUpdate />
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

function buildReturnsOption(
  bundles: RunBundle[],
  horizons: Array<{ key: string; label: string }>,
) {
  const cats = horizons.map((h) => h.label);
  const series: Record<string, unknown>[] = [];
  for (const b of bundles) {
    const summary = b.run.summary as Record<string, unknown>;
    series.push({
      name: `${b.label}·均值`,
      type: "bar",
      data: horizons.map((h) => statsOf(summary, h.key).mean ?? null),
      barMaxWidth: 14,
      itemStyle: { color: b.color, borderRadius: [2, 2, 0, 0] },
    });
    series.push({
      name: `${b.label}·中位`,
      type: "bar",
      data: horizons.map((h) => statsOf(summary, h.key).median ?? null),
      barMaxWidth: 14,
      itemStyle: {
        color: b.color,
        opacity: 0.4,
        borderRadius: [2, 2, 0, 0],
      },
    });
  }
  return {
    color: bundles.flatMap((b) => [b.color, b.color]),
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
          const v =
            p.value == null || Number.isNaN(Number(p.value))
              ? "—"
              : fmtPct(Number(p.value));
          return `${p.marker} ${p.seriesName}：${v}`;
        });
        return `${list[0].axisValue}<br/>${lines.join("<br/>")}`;
      },
    },
    legend: {
      type: "scroll",
      top: 4,
      textStyle: { fontSize: 11 },
    },
    grid: { left: 52, right: 20, top: 56, bottom: 36 },
    xAxis: { type: "category", data: cats, axisLabel: { color: MUTED } },
    yAxis: {
      type: "value",
      name: "收益",
      axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(0)}%`, color: MUTED },
      splitLine: { lineStyle: { type: "dashed", opacity: 0.4 } },
    },
    series,
  };
}

function buildWinRateOption(
  bundles: RunBundle[],
  horizons: Array<{ key: string; label: string }>,
) {
  const cats = horizons.map((h) => h.label);
  return {
    color: bundles.map((b) => b.color),
    tooltip: {
      trigger: "axis",
      formatter: (params: unknown) => {
        const list = params as Array<{
          seriesName: string;
          value: number | null;
          marker: string;
          axisValue: string;
        }>;
        if (!list?.length) return "";
        const lines = list.map((p) => {
          const v =
            p.value == null || Number.isNaN(Number(p.value))
              ? "—"
              : `${(Number(p.value) * 100).toFixed(1)}%`;
          return `${p.marker} ${p.seriesName}：${v}`;
        });
        return `${list[0].axisValue}<br/>${lines.join("<br/>")}`;
      },
    },
    legend: { top: 4, textStyle: { fontSize: 11 } },
    grid: { left: 52, right: 20, top: 44, bottom: 36 },
    xAxis: { type: "category", data: cats, axisLabel: { color: MUTED } },
    yAxis: {
      type: "value",
      min: 0,
      max: 1,
      name: "胜率",
      axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(0)}%`, color: MUTED },
      splitLine: { lineStyle: { type: "dashed", opacity: 0.4 } },
    },
    series: bundles.map((b) => {
      const summary = b.run.summary as Record<string, unknown>;
      return {
        name: b.label,
        type: "line",
        data: horizons.map((h) => statsOf(summary, h.key).win_rate ?? null),
        smooth: true,
        symbol: "circle",
        symbolSize: 7,
        lineStyle: { width: 2, color: b.color },
        itemStyle: { color: b.color },
      };
    }),
  };
}

function buildSpreadOption(
  bundles: RunBundle[],
  horizons: Array<{ key: string; label: string }>,
) {
  const cats = horizons.map((h) => h.label);
  return {
    color: bundles.map((b) => b.color),
    tooltip: {
      trigger: "item",
      formatter: (p: {
        seriesName: string;
        dataIndex: number;
        data: number[];
      }) => {
        const h = horizons[p.dataIndex];
        if (!h || !p.data?.length) return "";
        const [minV, , med, , maxV] = p.data;
        return [
          `<b>${p.seriesName} · ${h.label}</b>`,
          `P10：${fmtPct(minV)}`,
          `中位数：${fmtPct(med)}`,
          `P90：${fmtPct(maxV)}`,
        ].join("<br/>");
      },
    },
    legend: { top: 4, textStyle: { fontSize: 11 } },
    grid: { left: 52, right: 20, top: 44, bottom: 36 },
    xAxis: { type: "category", data: cats, axisLabel: { color: MUTED } },
    yAxis: {
      type: "value",
      axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(0)}%`, color: MUTED },
      splitLine: { lineStyle: { type: "dashed", opacity: 0.4 } },
    },
    series: bundles.map((b) => {
      const summary = b.run.summary as Record<string, unknown>;
      return {
        name: b.label,
        type: "boxplot",
        data: horizons.map((h) => {
          const s = statsOf(summary, h.key);
          const p10 = s.p10 ?? s.median ?? 0;
          const p90 = s.p90 ?? s.median ?? 0;
          const med = s.median ?? (p10 + p90) / 2;
          return [p10, p10, med, p90, p90];
        }),
        itemStyle: {
          color: `${b.color}33`,
          borderColor: b.color,
        },
      };
    }),
  };
}

function buildHistOption(bundles: RunBundle[]) {
  const allNums: number[] = [];
  const perRun: number[][] = bundles.map((b) => {
    const nums = b.events
      .map((e) => e.return_10)
      .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
    allNums.push(...nums);
    return nums;
  });

  if (!allNums.length) {
    return {
      title: {
        text: "暂无事件明细可画分布",
        left: "center",
        top: "middle",
        textStyle: { color: MUTED, fontSize: 13, fontWeight: 400 },
      },
      xAxis: { show: false },
      yAxis: { show: false },
      series: [],
    };
  }

  const bins = 16;
  let lo = Math.min(...allNums);
  let hi = Math.max(...allNums);
  if (lo === hi) {
    lo -= 0.01;
    hi += 0.01;
  }
  const width = (hi - lo) / bins;
  const edges = Array.from({ length: bins }, (_, i) => lo + i * width);
  const cats = edges.map((from) => {
    const mid = from + width / 2;
    return (mid * 100).toFixed(0);
  });

  const series = bundles.map((b, bi) => {
    const counts = Array.from({ length: bins }, () => 0);
    for (const v of perRun[bi]) {
      let idx = Math.floor((v - lo) / width);
      if (idx >= bins) idx = bins - 1;
      if (idx < 0) idx = 0;
      counts[idx] += 1;
    }
    return {
      name: b.label,
      type: "bar",
      data: counts,
      barMaxWidth: 28,
      itemStyle: { color: b.color, opacity: 0.45, borderRadius: [2, 2, 0, 0] },
      emphasis: { itemStyle: { opacity: 0.85 } },
    };
  });

  const zeroIdx = nearestBin(edges, width, 0);

  return {
    color: bundles.map((b) => b.color),
    tooltip: { trigger: "axis" },
    legend: { top: 4, textStyle: { fontSize: 11 } },
    grid: { left: 48, right: 20, top: 44, bottom: 44 },
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
    series: series.map((s, i) =>
      i === 0
        ? {
            ...s,
            markLine: {
              symbol: "none",
              label: { formatter: "0%", color: MUTED, fontSize: 10 },
              data: [{ xAxis: cats[zeroIdx], lineStyle: { type: "dashed", color: MUTED } }],
            },
          }
        : s,
    ),
  };
}

function nearestBin(edges: number[], width: number, value: number): number {
  let best = 0;
  let bestDist = Infinity;
  edges.forEach((from, i) => {
    const mid = from + width / 2;
    const d = Math.abs(mid - value);
    if (d < bestDist) {
      bestDist = d;
      best = i;
    }
  });
  return best;
}

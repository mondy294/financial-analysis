import { roundNullable } from "./analysis-utils.js";
import { StockAnalysisService } from "./stock-analysis-service.js";
import type { FundTradePlanLevel, StockTradePlanSnapshot, StockTrendSignal } from "./types.js";

function normalizeStockCode(code: string) {
  const cleanCode = String(code || "").trim();
  if (!/^\d{6}$/.test(cleanCode)) {
    throw new Error("股票代码必须是 6 位数字。");
  }
  return cleanCode;
}

function minValid(values: Array<number | null | undefined>) {
  const numbers = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  return numbers.length ? Math.min(...numbers) : null;
}

function maxValid(values: Array<number | null | undefined>) {
  const numbers = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  return numbers.length ? Math.max(...numbers) : null;
}

function formatPriceLevel(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(2) : "--";
}

function buildRelativeToLatest(levelPrice: number | null | undefined, latestPrice: number | null | undefined) {
  if (typeof levelPrice !== "number" || typeof latestPrice !== "number" || !Number.isFinite(levelPrice) || !Number.isFinite(latestPrice) || latestPrice === 0) {
    return null;
  }

  return roundNullable(((levelPrice - latestPrice) / latestPrice) * 100, 2);
}

function createPlanLevel(
  kind: FundTradePlanLevel["kind"],
  nav: number | null,
  latestPrice: number | null,
  reference: string,
  condition: string,
  action: string,
  reason: string,
): FundTradePlanLevel {
  return {
    kind,
    nav: roundNullable(nav, 2),
    relativeToLatest: buildRelativeToLatest(nav, latestPrice),
    reference,
    condition,
    action,
    reason,
  };
}

function buildActionBias(signal: StockTrendSignal) {
  switch (signal) {
    case "多头排列":
      return "当前结构偏强，更适合等回踩确认或突破回踩后的顺势处理，不追单日急拉。";
    case "空头排列":
      return "当前结构偏弱，优先控制试错频率，先把反抽和风控位看清楚。";
    case "震荡整理":
      return "当前还在区间博弈，动作以小仓位试探或继续观察为主。";
    default:
      return "当前数据还不足以给出激进结论，先观察关键价位再说。";
  }
}

function buildSizingGuidance(input: { signal: StockTrendSignal; volatility90d: number | null; turnoverRate: number | null }) {
  const highRisk = (typeof input.volatility90d === "number" && input.volatility90d >= 38)
    || (typeof input.turnoverRate === "number" && input.turnoverRate >= 8);

  return {
    currentActionBias: highRisk ? "单次动作控制在计划仓位的 5%-8%，先看确认再追加。" : "单次动作控制在计划仓位的 8%-12%，分两到三笔处理。",
    addOnDip: highRisk ? "若回踩支撑但没有破位，单次只用计划仓位的 5%-8% 试探。" : "若回踩支撑并出现承接，单次可用计划仓位的 8%-12% 试探。",
    addOnBreakout: highRisk ? "若放量突破后回踩确认，单次追加 3%-5% 即可。" : "若突破并站稳，再追加计划仓位的 5%-8%。",
    reduceOnWeakness: highRisk ? "若跌破风控位，优先减掉计划仓位的 8%-12%。" : "若跌破风控位，优先减掉计划仓位的 10%-15%。",
    initialProbe: highRisk ? "初次试探以 5%-8% 轻仓为主。" : "初次试探以 8%-12% 轻仓为主。",
  };
}

function buildObservationSignals(input: {
  latestPrice: number | null;
  ma20: number | null;
  ma60: number | null;
  turnoverRate: number | null;
  upperShadowRate: number | null;
}) {
  const signals: string[] = [];

  if (typeof input.ma20 === "number") {
    signals.push(
      typeof input.latestPrice === "number" && input.latestPrice >= input.ma20
        ? `回踩 ${formatPriceLevel(input.ma20)}（MA20）附近时，能否继续守住并出现承接。`
        : `收盘价能否重新站上 ${formatPriceLevel(input.ma20)}（MA20）并连续保持。`,
    );
  }

  if (typeof input.ma60 === "number") {
    signals.push(
      typeof input.latestPrice === "number" && input.latestPrice >= input.ma60
        ? `若回落到 ${formatPriceLevel(input.ma60)}（MA60）一带，是否仍然不破中期结构。`
        : `能否重新站上 ${formatPriceLevel(input.ma60)}（MA60），确认中期趋势开始修复。`,
    );
  }

  if (typeof input.turnoverRate === "number") {
    signals.push(`换手率是否继续维持在合理区间（当前约 ${input.turnoverRate.toFixed(2)}%），避免纯情绪驱动后迅速降温。`);
  }

  if (typeof input.upperShadowRate === "number" && input.upperShadowRate >= 2.5) {
    signals.push("长上影是否继续反复出现；如果持续出现，说明上方抛压还没有真正释放完。");
  }

  return signals.slice(0, 5);
}

function buildRiskFlags(input: {
  volatility90d: number | null;
  maxDrawdown90d: number | null;
  upperShadowRate: number | null;
  lowerShadowRate: number | null;
  turnoverRate: number | null;
}) {
  const flags: string[] = [];

  if (typeof input.volatility90d === "number" && input.volatility90d >= 38) {
    flags.push(`近 90 日年化波动率约 ${input.volatility90d.toFixed(2)}%，属于高波动区间。`);
  }

  if (typeof input.maxDrawdown90d === "number" && input.maxDrawdown90d <= -18) {
    flags.push(`近 90 日最大回撤约 ${input.maxDrawdown90d.toFixed(2)}%，说明向下惯性仍然明显。`);
  }

  if (typeof input.upperShadowRate === "number" && input.upperShadowRate >= 2.5) {
    flags.push(`最新 K 线长上影约 ${input.upperShadowRate.toFixed(2)}%，短线追高容易被上方抛压打回。`);
  }

  if (typeof input.lowerShadowRate === "number" && input.lowerShadowRate >= 2.5) {
    flags.push(`最新 K 线下影约 ${input.lowerShadowRate.toFixed(2)}%，说明波动放大，不能把日内回拉直接当成稳固企稳。`);
  }

  if (typeof input.turnoverRate === "number" && input.turnoverRate >= 10) {
    flags.push(`最新换手率约 ${input.turnoverRate.toFixed(2)}%，短线资金博弈偏激烈，仓位不宜过重。`);
  }

  return flags.slice(0, 5);
}

function buildPlanLevels(input: {
  latestPrice: number | null;
  ma10: number | null;
  ma20: number | null;
  ma60: number | null;
  bollUpper: number | null;
  signal: StockTrendSignal;
  addOnDipText: string;
  addOnBreakoutText: string;
  reduceText: string;
  initialProbeText: string;
}) {
  const latestPrice = input.latestPrice;
  const confirmPrice = maxValid([input.ma10, input.ma20]);
  const supportNear = minValid([input.ma10, input.ma20]);
  const supportDeep = minValid([input.ma20, input.ma60]);
  const reboundPrice = maxValid([input.ma10, input.ma20, input.ma60]);
  const overheatPrice = maxValid([
    input.bollUpper,
    typeof latestPrice === "number" ? roundNullable(latestPrice * 1.03, 2) : null,
  ]);
  const riskBase = minValid([input.ma60, input.ma20, typeof latestPrice === "number" ? latestPrice * 0.95 : null]);
  const riskPrice = typeof riskBase === "number" ? roundNullable(riskBase * 0.985, 2) : null;

  switch (input.signal) {
    case "多头排列":
      return [
        createPlanLevel(
          "观察确认位",
          confirmPrice,
          latestPrice,
          confirmPrice === input.ma10 ? "MA10" : "MA20",
          `若收盘继续稳定在 ${formatPriceLevel(confirmPrice)} 上方，说明偏强结构没有被破坏。`,
          "继续观察并优先等回踩，不追单日加速。",
          "多头结构里先确认短中期均线未失守，再考虑放大动作。",
        ),
        createPlanLevel(
          "试探加仓位",
          supportNear,
          latestPrice,
          supportNear === input.ma10 ? "MA10" : "MA20",
          `若回踩到 ${formatPriceLevel(supportNear)} 附近但没有有效跌破，可做第一笔试探。`,
          input.initialProbeText,
          "顺势结构中的回踩支撑，比追高更适合执行第一笔。",
        ),
        createPlanLevel(
          "分批加仓位",
          supportDeep,
          latestPrice,
          supportDeep === input.ma20 ? "MA20" : "MA60",
          `若回踩更深但仍守住 ${formatPriceLevel(supportDeep)}，可在确认后执行第二笔。`,
          input.addOnBreakoutText,
          "深一层支撑守住，往往比浅回踩更能验证承接。",
        ),
        createPlanLevel(
          "减仓位",
          overheatPrice,
          latestPrice,
          overheatPrice === input.bollUpper ? "BOLL 上轨 / 过热区" : "短线过热区",
          `若继续冲到 ${formatPriceLevel(overheatPrice)} 一带但无法稳住，更像情绪扩张后的兑现区。`,
          input.reduceText,
          "偏强不等于可以无限追价，过热区更适合先收缩风险。",
        ),
        createPlanLevel(
          "风控线",
          riskPrice,
          latestPrice,
          riskBase === input.ma60 ? "MA60 下沿" : "中期支撑失守",
          `若有效跌破 ${formatPriceLevel(riskPrice)}，原先的偏多假设就需要下调。`,
          input.reduceText,
          "跌破中期支撑意味着趋势级别变化，不能再按普通回踩处理。",
        ),
      ];
    case "空头排列":
      return [
        createPlanLevel(
          "减仓位",
          reboundPrice,
          latestPrice,
          reboundPrice === input.ma10 ? "MA10" : "MA20/MA60",
          `若反抽到 ${formatPriceLevel(reboundPrice)} 一带仍站不上去，更像弱势反抽。`,
          input.reduceText,
          "空头结构里先看反抽是不是减仓机会，而不是默认已经反转。",
        ),
        createPlanLevel(
          "试探加仓位",
          supportDeep,
          latestPrice,
          supportDeep === input.ma60 ? "MA60" : "MA20",
          `只有跌到 ${formatPriceLevel(supportDeep)} 一带并出现止跌迹象时，才值得考虑极小试探。`,
          input.initialProbeText,
          "空头阶段的试探必须建立在更低位置和止跌确认上。",
        ),
        createPlanLevel(
          "观察确认位",
          confirmPrice,
          latestPrice,
          confirmPrice === input.ma10 ? "MA10" : "MA20",
          `若后续重新站上 ${formatPriceLevel(confirmPrice)} 并保持数个交易日，才说明趋势开始修复。`,
          "确认修复后，再把结论从观望切回分批布局。",
          "空头修复必须先收复关键均线，否则只算反弹。",
        ),
        createPlanLevel(
          "风控线",
          riskPrice,
          latestPrice,
          riskBase === input.ma60 ? "MA60 下沿" : "阶段低点下沿",
          `若继续跌破 ${formatPriceLevel(riskPrice)}，说明下行趋势仍在延续。`,
          input.reduceText,
          "破位后向下空间会放大，必须优先控制试错。",
        ),
      ];
    case "震荡整理":
    case "数据不足":
    default:
      return [
        createPlanLevel(
          "观察确认位",
          confirmPrice,
          latestPrice,
          confirmPrice === input.ma10 ? "MA10" : "MA20",
          `若重新站上 ${formatPriceLevel(confirmPrice)} 并站稳，才说明震荡开始偏向上沿突破。`,
          "先观察，确认后再扩大动作。",
          "震荡区间里先看是否突破，避免在中间位置来回消耗。",
        ),
        createPlanLevel(
          "试探加仓位",
          supportDeep,
          latestPrice,
          supportDeep === input.ma60 ? "MA60" : "MA20",
          `若回落到 ${formatPriceLevel(supportDeep)} 附近且没有继续破位，可只做小幅试探。`,
          input.addOnDipText,
          "震荡里更适合靠近支撑位小步试探，而不是在中间追。",
        ),
        createPlanLevel(
          "减仓位",
          reboundPrice,
          latestPrice,
          reboundPrice === input.ma10 ? "MA10" : "MA20/MA60",
          `若反弹到 ${formatPriceLevel(reboundPrice)} 一带却迟迟无法突破，更适合先收缩一部分风险。`,
          input.reduceText,
          "震荡上沿承压往往意味着继续拉锯或回落，先锁定主动权更稳。",
        ),
        createPlanLevel(
          "风控线",
          riskPrice,
          latestPrice,
          riskBase === input.ma60 ? "MA60 下沿" : "震荡下沿",
          `若有效跌破 ${formatPriceLevel(riskPrice)}，说明区间向下破位。`,
          input.reduceText,
          "一旦向下破位，原来的震荡思路就不再成立。",
        ),
      ];
  }
}

export class StockResearchService {
  constructor(private readonly stockAnalysisService = new StockAnalysisService()) {}

  async getTradePlanSnapshot(code: string): Promise<StockTradePlanSnapshot> {
    const cleanCode = normalizeStockCode(code);
    const analysis = await this.stockAnalysisService.getStockAnalysis(cleanCode, { historyDays: 240, klineLimit: 1200 });
    const latest = analysis.trendAnalysis.latest;
    const sizingSuggestion = buildSizingGuidance({
      signal: latest.signal,
      volatility90d: analysis.trendAnalysis.risk.volatility90d,
      turnoverRate: latest.turnoverRate,
    });

    return {
      stockCode: cleanCode,
      stockName: analysis.stock.name,
      exchange: analysis.stock.exchange,
      signal: latest.signal,
      latestPrice: analysis.stock.latestPrice ?? latest.close,
      previousClose: analysis.stock.previousClose,
      ma10: latest.ma10,
      ma20: latest.ma20,
      ma60: latest.ma60,
      biasToMa20: latest.biasToMa20,
      biasToMa60: latest.biasToMa60,
      latestCandle: {
        open: latest.open,
        close: latest.close,
        high: latest.high,
        low: latest.low,
        amplitude: latest.amplitude,
        dailyChangeRate: latest.dailyChangeRate,
        bodyChangeRate: latest.bodyChangeRate,
        upperShadowRate: latest.upperShadowRate,
        lowerShadowRate: latest.lowerShadowRate,
      },
      sizingSuggestion: {
        currentActionBias: `${buildActionBias(latest.signal)} ${sizingSuggestion.currentActionBias}`.trim(),
        addOnDip: sizingSuggestion.addOnDip,
        addOnBreakout: sizingSuggestion.addOnBreakout,
        reduceOnWeakness: sizingSuggestion.reduceOnWeakness,
        initialProbe: sizingSuggestion.initialProbe,
      },
      planLevels: buildPlanLevels({
        latestPrice: analysis.stock.latestPrice ?? latest.close,
        ma10: latest.ma10,
        ma20: latest.ma20,
        ma60: latest.ma60,
        bollUpper: latest.bollUpper,
        signal: latest.signal,
        addOnDipText: sizingSuggestion.addOnDip,
        addOnBreakoutText: sizingSuggestion.addOnBreakout,
        reduceText: sizingSuggestion.reduceOnWeakness,
        initialProbeText: sizingSuggestion.initialProbe,
      }),
      observationSignals: buildObservationSignals({
        latestPrice: analysis.stock.latestPrice ?? latest.close,
        ma20: latest.ma20,
        ma60: latest.ma60,
        turnoverRate: latest.turnoverRate,
        upperShadowRate: latest.upperShadowRate,
      }),
      riskFlags: buildRiskFlags({
        volatility90d: analysis.trendAnalysis.risk.volatility90d,
        maxDrawdown90d: analysis.trendAnalysis.risk.maxDrawdown90d,
        upperShadowRate: latest.upperShadowRate,
        lowerShadowRate: latest.lowerShadowRate,
        turnoverRate: latest.turnoverRate,
      }),
    };
  }
}

import { divideNumbers, roundNullable, sumNumbers } from "./analysis-utils.js";
import { FundAnalysisService } from "./fund-analysis-service.js";
import { getFundHoldingStocks } from "./stock-service.js";
import { getFundUniverseCache } from "./data-store.js";
import { PortfolioService } from "./portfolio-service.js";
import { getUniverseItemByCode, refreshFundUniverseCache } from "./screener-service.js";
import type {
  FundHoldingBreadthResponse,
  FundPeerBenchmarkPeer,
  FundPeerBenchmarkResponse,
  FundTradePlanLevel,
  FundTradePlanSnapshot,
  FundTrendSignal,
  FundUniverseItem,
} from "./types.js";

function normalizeFundCode(code: string) {
  const cleanCode = String(code || "").trim();
  if (!/^\d{6}$/.test(cleanCode)) {
    throw new Error("基金编号必须是 6 位数字。");
  }
  return cleanCode;
}

function averageNumbers(values: Array<number | null | undefined>) {
  const numbers = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (numbers.length === 0) {
    return null;
  }
  return roundNullable(numbers.reduce((total, value) => total + value, 0) / numbers.length, 2);
}

function buildComparableUniverse(subject: FundUniverseItem, items: FundUniverseItem[]) {
  return items.filter((item) => item.category === subject.category && item.code !== subject.code);
}

function calculateOverlapScore(source: string[], target: string[], multiplier: number) {
  const sourceSet = new Set(source);
  const shared = target.filter((item) => sourceSet.has(item));
  return shared.length * multiplier;
}

function calculateDistanceScore(sourceValue: number | null, targetValue: number | null, tolerance: number, maxScore: number) {
  if (typeof sourceValue !== "number" || typeof targetValue !== "number") {
    return 0;
  }

  const distance = Math.abs(sourceValue - targetValue);
  if (distance >= tolerance) {
    return 0;
  }

  return roundNullable(((tolerance - distance) / tolerance) * maxScore, 2) ?? 0;
}

function buildPeerCandidate(subject: FundUniverseItem, candidate: FundUniverseItem): FundPeerBenchmarkPeer {
  const rawTypeBonus = subject.rawFundType && candidate.rawFundType && subject.rawFundType === candidate.rawFundType ? 8 : 0;
  const categoryBonus = subject.category === candidate.category ? 10 : 0;
  const sectorOverlapScore = calculateOverlapScore(subject.sectorTags, candidate.sectorTags, 10);
  const themeOverlapScore = calculateOverlapScore(subject.themeTags, candidate.themeTags, 6);
  const sizeClosenessScore = calculateDistanceScore(subject.metrics.size, candidate.metrics.size, 120, 12);
  const volatilityClosenessScore = calculateDistanceScore(subject.metrics.volatility1y, candidate.metrics.volatility1y, 18, 12);
  const drawdownClosenessScore = calculateDistanceScore(subject.metrics.maxDrawdown1y, candidate.metrics.maxDrawdown1y, 20, 10);
  const returnClosenessScore = calculateDistanceScore(subject.metrics.return1y, candidate.metrics.return1y, 35, 8);

  const similarityScore = roundNullable(
    categoryBonus + rawTypeBonus + sectorOverlapScore + themeOverlapScore + sizeClosenessScore + volatilityClosenessScore + drawdownClosenessScore + returnClosenessScore,
    2,
  ) ?? 0;

  return {
    code: candidate.code,
    name: candidate.name,
    category: candidate.category,
    rawFundType: candidate.rawFundType,
    sectorTags: candidate.sectorTags,
    themeTags: candidate.themeTags,
    scoreTotal: candidate.score.total,
    similarityScore,
    metrics: candidate.metrics,
  };
}

function percentileHigherIsBetter(items: FundUniverseItem[], targetCode: string, selector: (item: FundUniverseItem) => number | null) {
  const values = items
    .map((item) => ({ code: item.code, value: selector(item) }))
    .filter((item): item is { code: string; value: number } => typeof item.value === "number" && Number.isFinite(item.value));

  if (values.length === 0) {
    return null;
  }

  const target = values.find((item) => item.code === targetCode);
  if (!target) {
    return null;
  }

  const worseOrEqualCount = values.filter((item) => item.value <= target.value).length;
  return roundNullable((worseOrEqualCount / values.length) * 100, 1);
}

function percentileLowerIsBetter(items: FundUniverseItem[], targetCode: string, selector: (item: FundUniverseItem) => number | null) {
  const values = items
    .map((item) => ({ code: item.code, value: selector(item) }))
    .filter((item): item is { code: string; value: number } => typeof item.value === "number" && Number.isFinite(item.value));

  if (values.length === 0) {
    return null;
  }

  const target = values.find((item) => item.code === targetCode);
  if (!target) {
    return null;
  }

  const worseOrEqualCount = values.filter((item) => item.value >= target.value).length;
  return roundNullable((worseOrEqualCount / values.length) * 100, 1);
}

function minValid(values: Array<number | null | undefined>) {
  const numbers = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  return numbers.length ? Math.min(...numbers) : null;
}

function maxValid(values: Array<number | null | undefined>) {
  const numbers = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  return numbers.length ? Math.max(...numbers) : null;
}

function formatNavLevel(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(4) : "--";
}

function buildRelativeToLatest(levelNav: number | null | undefined, latestNav: number | null | undefined) {
  if (typeof levelNav !== "number" || typeof latestNav !== "number" || !Number.isFinite(levelNav) || !Number.isFinite(latestNav) || latestNav === 0) {
    return null;
  }

  return roundNullable(((levelNav - latestNav) / latestNav) * 100, 2);
}

function createPlanLevel(
  kind: FundTradePlanLevel["kind"],
  nav: number | null,
  latestNav: number | null,
  reference: string,
  condition: string,
  action: string,
  reason: string,
): FundTradePlanLevel {
  return {
    kind,
    nav: roundNullable(nav, 4),
    relativeToLatest: buildRelativeToLatest(nav, latestNav),
    reference,
    condition,
    action,
    reason,
  };
}

function ensureUniverseReady() {
  return getFundUniverseCache().then((cache) => {
    if (cache.items.length > 0) {
      return cache;
    }
    return refreshFundUniverseCache();
  });
}

function buildActionBias(signal: FundTrendSignal, hasHolding: boolean) {
  switch (signal) {
    case "多头排列":
      return hasHolding ? "当前偏向持有待跟踪，优先等回踩支撑后再分批处理。" : "当前不追单日大涨，优先等回踩支撑或趋势确认后再分批布局。";
    case "震荡整理":
      return hasHolding ? "当前偏向维持仓位，等站稳 MA20 或回踩支撑后再决定是否加减。" : "当前偏向观察，等待趋势进一步明确再放大动作。";
    case "空头排列":
      return hasHolding ? "当前偏向先控波动暴露，优先看反弹减仓位和风控线，不宜贸然补仓。" : "当前偏向观望，只有跌到关键支撑且出现止跌信号时才考虑极小试探仓。";
    default:
      return hasHolding ? "数据仍需进一步确认，当前先以小动作和观察为主。" : "数据仍需进一步确认，当前先不要急着建仓。";
  }
}

function buildSizingGuidance(input: {
  hasHolding: boolean;
  portfolioPositionRatio: number | null;
  category: string | null;
  isHighRisk: boolean;
}) {
  const ratio = input.portfolioPositionRatio;
  const baseAdd = ratio !== null && ratio >= 35 ? "5%-8%" : ratio !== null && ratio >= 20 ? "8%-12%" : "10%-15%";
  const cappedAdd = input.isHighRisk || input.category === "QDII" ? "5%-10%" : baseAdd;
  const reduce = ratio !== null && ratio >= 35 ? "12%-18%" : input.isHighRisk ? "8%-12%" : "10%-15%";
  const breakoutAdd = input.isHighRisk ? "3%-5%" : ratio !== null && ratio >= 20 ? "5%-8%" : "8%-10%";
  const initialProbe = input.isHighRisk || input.category === "QDII" ? "先用计划投入资金的 5%-8% 试探" : "先用计划投入资金的 8%-12% 试探";

  return {
    currentActionBias: input.hasHolding ? "优先围绕现有仓位做小步调整，不建议单次大幅动作。" : "优先做试探仓或继续观察，等确认后再加第二笔。",
    addOnDip: input.hasHolding ? `若触发加仓条件，单次加仓控制在当前持仓金额的 ${cappedAdd}` : `${initialProbe}，确认后再补第二笔`,
    addOnBreakout: input.hasHolding ? `若是突破确认后的加仓，单次控制在当前持仓金额的 ${breakoutAdd}` : `若突破确认，再追加计划投入资金的 ${breakoutAdd}`,
    reduceOnWeakness: input.hasHolding ? `若触发减仓/风控条件，优先减仓当前持仓金额的 ${reduce}` : "未持有时不需要减仓动作，只需取消试探计划",
    initialProbe,
  };
}

function buildRiskFlags(input: {
  category: string | null;
  volatility90d: number | null;
  maxDrawdown90d: number | null;
  concentrationTop5: number | null;
  hasHolding: boolean;
  portfolioPositionRatio: number | null;
}) {
  const flags: string[] = [];

  if (input.category === "QDII") {
    flags.push("QDII 基金受海外市场、汇率与时差影响，短线波动放大时不宜重手加仓。");
  }

  if (typeof input.volatility90d === "number" && input.volatility90d >= 25) {
    flags.push(`近 90 日年化波动率约 ${input.volatility90d.toFixed(2)}%，属于高波动区间。`);
  }

  if (typeof input.maxDrawdown90d === "number" && input.maxDrawdown90d <= -12) {
    flags.push(`近 90 日最大回撤约 ${input.maxDrawdown90d.toFixed(2)}%，说明下行阶段仍有惯性风险。`);
  }

  if (typeof input.concentrationTop5 === "number" && input.concentrationTop5 >= 55) {
    flags.push(`前 5 大重仓股集中度约 ${input.concentrationTop5.toFixed(2)}%，少数持仓会显著放大净值波动。`);
  }

  if (input.hasHolding && typeof input.portfolioPositionRatio === "number" && input.portfolioPositionRatio >= 35) {
    flags.push(`当前这只基金约占组合 ${input.portfolioPositionRatio.toFixed(2)}%，继续加仓前要先控制单只基金权重。`);
  }

  return flags;
}

function buildObservationSignals(input: {
  ma20: number | null;
  ma60: number | null;
  holdingBreadth: FundHoldingBreadthResponse | null;
  peerBaseCount: number;
  category: string | null;
}) {
  const signals: string[] = [];

  if (typeof input.ma20 === "number") {
    signals.push(`净值能否重新站上 ${formatNavLevel(input.ma20)}（MA20）并连续 2-3 个交易日不跌回。`);
  }

  if (typeof input.ma60 === "number") {
    signals.push(`回踩 ${formatNavLevel(input.ma60)}（MA60）附近时，是否出现止跌而不是继续破位。`);
  }

  if (input.holdingBreadth) {
    signals.push(`重仓股上涨/下跌家数能否继续改善（当前 ${input.holdingBreadth.positiveCount}:${input.holdingBreadth.negativeCount}）。`);
  }

  if (input.peerBaseCount > 0) {
    signals.push("同类收益/回撤分位是否继续改善，而不是只靠短期反弹。");
  }

  if (input.category === "QDII") {
    signals.push("美股主指数与人民币汇率是否继续同向支撑净值表现。");
  }

  return signals.slice(0, 5);
}

function buildPlanLevels(input: {
  latestNav: number | null;
  ma10: number | null;
  ma20: number | null;
  ma60: number | null;
  signal: FundTrendSignal;
  hasHolding: boolean;
  addOnDipText: string;
  addOnBreakoutText: string;
  reduceText: string;
  initialProbeText: string;
}) {
  const latestNav = input.latestNav;
  const supportNear = minValid([input.ma10, input.ma20]);
  const supportDeep = minValid([input.ma20, input.ma60]);
  const confirmNav = maxValid([input.ma10, input.ma20]);
  const reboundNav = maxValid([input.ma10, input.ma20, input.ma60]);
  const riskBase = minValid([input.ma60, input.ma20, latestNav !== null ? latestNav * 0.95 : null]);
  const riskNav = typeof riskBase === "number" ? roundNullable(riskBase * 0.985, 4) : null;

  switch (input.signal) {
    case "多头排列":
      return [
        createPlanLevel(
          "观察确认位",
          confirmNav,
          latestNav,
          confirmNav === input.ma10 ? "MA10" : "MA20",
          `净值继续稳定在 ${formatNavLevel(confirmNav)} 上方，说明强势结构没有被破坏。`,
          "继续持有，优先等回踩再处理。",
          "多头结构里先确认短中期均线没有失守，再考虑扩大仓位。",
        ),
        createPlanLevel(
          "试探加仓位",
          supportNear,
          latestNav,
          supportNear === input.ma10 ? "MA10" : "MA20",
          `若净值回踩到 ${formatNavLevel(supportNear)} 附近但没有有效跌破，可做第一笔动作。`,
          input.hasHolding ? input.addOnDipText : input.initialProbeText,
          "多头趋势中的回踩支撑，比追涨更适合执行加仓或试探建仓。",
        ),
        createPlanLevel(
          "分批加仓位",
          supportDeep,
          latestNav,
          supportDeep === input.ma20 ? "MA20" : "MA60",
          `若回踩更深但仍能守住 ${formatNavLevel(supportDeep)}，说明中期趋势还没坏，可执行第二笔。`,
          input.hasHolding ? input.addOnBreakoutText : "在试探仓基础上再补一笔，不要一次性打满。",
          "深一层支撑位守住，通常比浅回踩更能验证买盘承接。",
        ),
        createPlanLevel(
          "风控线",
          riskNav,
          latestNav,
          riskBase === input.ma60 ? "MA60 下沿" : "中期支撑失守",
          `若净值有效跌破 ${formatNavLevel(riskNav)}，原先的偏多假设就要下调。`,
          input.hasHolding ? input.reduceText : "取消建仓计划，重新等待趋势修复。",
          "跌破中期支撑意味着趋势级别发生变化，不能再按回踩机会看待。",
        ),
      ];
    case "空头排列":
      return [
        createPlanLevel(
          "减仓位",
          reboundNav,
          latestNav,
          reboundNav === input.ma10 ? "MA10" : "MA20/MA60",
          `若净值反弹到 ${formatNavLevel(reboundNav)} 一带仍站不上去，更像弱势反抽。`,
          input.hasHolding ? input.reduceText : "继续观望，不做追涨试探。",
          "空头结构里先看反弹是否只是给减仓机会，而不是默认已经反转。",
        ),
        createPlanLevel(
          "试探加仓位",
          supportDeep,
          latestNav,
          supportDeep === input.ma60 ? "MA60" : "MA20",
          `只有跌到 ${formatNavLevel(supportDeep)} 一带并出现止跌迹象时，才值得考虑极小试探。`,
          input.hasHolding ? `仅在止跌确认后，按 ${input.addOnDipText} 执行。` : input.initialProbeText,
          "空头阶段的加仓必须建立在更低位置和止跌确认上，而不是边跌边补。",
        ),
        createPlanLevel(
          "观察确认位",
          confirmNav,
          latestNav,
          confirmNav === input.ma10 ? "MA10" : "MA20",
          `若后续重新站上 ${formatNavLevel(confirmNav)} 并保持数个交易日，才说明趋势开始修复。`,
          "站稳后再把结论从观望切回分批布局。",
          "空头修复必须先收复关键均线，否则只算反弹而不是反转。",
        ),
        createPlanLevel(
          "风控线",
          riskNav,
          latestNav,
          riskBase === input.ma60 ? "MA60 下沿" : "阶段低点下沿",
          `若继续跌破 ${formatNavLevel(riskNav)}，说明下行趋势仍在延续。`,
          input.hasHolding ? input.reduceText : "继续等待，不做任何试探建仓。",
          "破位后向下空间会放大，必须优先保护仓位而不是抄底。",
        ),
      ];
    case "震荡整理":
    case "数据不足":
    default:
      return [
        createPlanLevel(
          "观察确认位",
          confirmNav,
          latestNav,
          confirmNav === input.ma10 ? "MA10" : "MA20",
          `若净值重新站上 ${formatNavLevel(confirmNav)} 并站稳，才说明震荡偏向上沿突破。`,
          "先观察，确认后再扩大动作。",
          "震荡区间里先看是否突破，避免在中间位置频繁来回操作。",
        ),
        createPlanLevel(
          "试探加仓位",
          supportDeep,
          latestNav,
          supportDeep === input.ma60 ? "MA60" : "MA20",
          `若净值回落到 ${formatNavLevel(supportDeep)} 附近且没有继续破位，可只做小幅试探。`,
          input.hasHolding ? input.addOnDipText : input.initialProbeText,
          "震荡区间里更适合靠近支撑位小步试探，而不是在中间价位追。",
        ),
        createPlanLevel(
          "减仓位",
          reboundNav,
          latestNav,
          reboundNav === input.ma10 ? "MA10" : "MA20/MA60",
          `若反弹到 ${formatNavLevel(reboundNav)} 一带却迟迟无法突破，适合先落袋一部分波动仓。`,
          input.hasHolding ? input.reduceText : "未持有时不需要减仓动作。",
          "震荡中上沿承压往往意味着继续横盘或回落，适合先锁定波动收益。",
        ),
        createPlanLevel(
          "风控线",
          riskNav,
          latestNav,
          riskBase === input.ma60 ? "MA60 下沿" : "震荡下沿",
          `若净值有效跌破 ${formatNavLevel(riskNav)}，说明震荡区间向下破位。`,
          input.hasHolding ? input.reduceText : "取消试探计划，继续等待。",
          "一旦向下破位，原来的震荡思路就不再成立，仓位要先收缩。",
        ),
      ];
  }
}

export class FundResearchService {
  constructor(
    private readonly portfolioService = new PortfolioService(),
    private readonly fundAnalysisService = new FundAnalysisService(portfolioService),
  ) {}

  async getPeerBenchmark(code: string, limit = 5): Promise<FundPeerBenchmarkResponse> {
    const cleanCode = normalizeFundCode(code);
    const cache = await ensureUniverseReady();
    const subject = (await getUniverseItemByCode(cleanCode)) ?? null;
    const safeLimit = Math.min(Math.max(Number(limit || 5), 1), 10);

    if (!subject) {
      return {
        fundCode: cleanCode,
        updatedAt: cache.updatedAt,
        peerBaseCount: 0,
        subject: null,
        percentile: null,
        peers: [],
      };
    }

    const peerBase = [subject, ...buildComparableUniverse(subject, cache.items)];
    const peers = peerBase
      .filter((item) => item.code !== subject.code)
      .map((item) => buildPeerCandidate(subject, item))
      .sort((left, right) => right.similarityScore - left.similarityScore || right.scoreTotal - left.scoreTotal)
      .slice(0, safeLimit);

    return {
      fundCode: cleanCode,
      updatedAt: cache.updatedAt,
      peerBaseCount: peerBase.length,
      subject,
      percentile: {
        return1m: percentileHigherIsBetter(peerBase, subject.code, (item) => item.metrics.return1m),
        return3m: percentileHigherIsBetter(peerBase, subject.code, (item) => item.metrics.return3m),
        return1y: percentileHigherIsBetter(peerBase, subject.code, (item) => item.metrics.return1y),
        maxDrawdown1y: percentileLowerIsBetter(peerBase, subject.code, (item) => item.metrics.maxDrawdown1y),
        volatility1y: percentileLowerIsBetter(peerBase, subject.code, (item) => item.metrics.volatility1y),
        feeRate: percentileLowerIsBetter(peerBase, subject.code, (item) => item.metrics.feeRate),
        scoreTotal: percentileHigherIsBetter(peerBase, subject.code, (item) => item.score.total),
      },
      peers,
    };
  }

  async getHoldingBreadth(code: string, topline = 10): Promise<FundHoldingBreadthResponse> {
    const cleanCode = normalizeFundCode(code);
    const safeTopline = Math.min(Math.max(Number(topline || 10), 1), 20);
    const payload = await getFundHoldingStocks(cleanCode, safeTopline);
    const items = payload.items;

    const positiveCount = items.filter((item) => typeof item.changeRate === "number" && item.changeRate > 0).length;
    const negativeCount = items.filter((item) => typeof item.changeRate === "number" && item.changeRate < 0).length;
    const flatCount = items.filter((item) => typeof item.changeRate === "number" && item.changeRate === 0).length;

    return {
      fundCode: cleanCode,
      reportDate: payload.reportDate,
      totalHoldings: items.length,
      positiveCount,
      negativeCount,
      flatCount,
      averageChangeRate: averageNumbers(items.map((item) => item.changeRate)),
      concentrationTop3: sumNumbers(items.slice(0, 3).map((item) => item.navRatio)),
      concentrationTop5: sumNumbers(items.slice(0, 5).map((item) => item.navRatio)),
      strongestStocks: [...items]
        .filter((item) => typeof item.changeRate === "number")
        .sort((left, right) => (right.changeRate ?? -Infinity) - (left.changeRate ?? -Infinity))
        .slice(0, 3),
      weakestStocks: [...items]
        .filter((item) => typeof item.changeRate === "number")
        .sort((left, right) => (left.changeRate ?? Infinity) - (right.changeRate ?? Infinity))
        .slice(0, 3),
    };
  }

  async getTradePlanSnapshot(code: string): Promise<FundTradePlanSnapshot> {
    const cleanCode = normalizeFundCode(code);
    const [analysis, holdingBreadth, peerBenchmark, portfolio] = await Promise.all([
      this.fundAnalysisService.getFundAnalysis(cleanCode, { historyDays: 180 }),
      this.getHoldingBreadth(cleanCode, 10).catch(() => null),
      this.getPeerBenchmark(cleanCode, 5).catch(() => ({ peerBaseCount: 0 } as Pick<FundPeerBenchmarkResponse, "peerBaseCount">)),
      this.portfolioService.getPortfolioResponse().catch(() => ({
        items: [],
        summary: {
          holdingsCount: 0,
          totalPositionAmount: null,
          totalCurrentMarketValue: null,
          totalEstimatedMarketValue: null,
          totalCurrentProfitAmount: null,
          totalEstimatedProfitAmount: null,
        },
      })),
    ]);

    const latest = analysis.trendAnalysis.latest;
    const holding = analysis.myHolding;
    const totalPositionAmount = portfolio.summary.totalPositionAmount;
    const portfolioPositionRatioDecimal = holding ? divideNumbers(holding.positionAmount, totalPositionAmount, 4) : null;
    const portfolioPositionRatio =
      typeof portfolioPositionRatioDecimal === "number" ? roundNullable(portfolioPositionRatioDecimal * 100, 2) : null;
    const category = analysis.screener?.category ?? null;
    const isHighRisk =
      category === "QDII"
      || (typeof analysis.trendAnalysis.risk.volatility90d === "number" && analysis.trendAnalysis.risk.volatility90d >= 25)
      || (typeof analysis.trendAnalysis.risk.maxDrawdown90d === "number" && analysis.trendAnalysis.risk.maxDrawdown90d <= -12)
      || (typeof holdingBreadth?.concentrationTop5 === "number" && holdingBreadth.concentrationTop5 >= 55);

    const sizingSuggestion = buildSizingGuidance({
      hasHolding: Boolean(holding),
      portfolioPositionRatio,
      category,
      isHighRisk,
    });

    return {
      fundCode: cleanCode,
      fundName: analysis.fund.name,
      category,
      signal: latest.signal,
      latestNav: analysis.fund.latestNav,
      estimatedNav: analysis.fund.estimatedNav,
      estimatedChangeRate: analysis.fund.estimatedChangeRate,
      ma10: latest.ma10,
      ma20: latest.ma20,
      ma60: latest.ma60,
      biasToMa20: latest.biasToMa20,
      biasToMa60: latest.biasToMa60,
      holding: {
        hasHolding: Boolean(holding),
        status: holding?.status ?? null,
        positionAmount: holding?.positionAmount ?? null,
        costNav: holding?.costNav ?? null,
        currentProfitRate: holding?.currentProfitRate ?? null,
        estimatedProfitRate: holding?.estimatedProfitRate ?? null,
        portfolioPositionRatio,
      },
      sizingSuggestion: {
        currentActionBias: `${buildActionBias(latest.signal, Boolean(holding))} ${sizingSuggestion.currentActionBias}`.trim(),
        addOnDip: sizingSuggestion.addOnDip,
        addOnBreakout: sizingSuggestion.addOnBreakout,
        reduceOnWeakness: sizingSuggestion.reduceOnWeakness,
        initialProbe: sizingSuggestion.initialProbe,
      },
      planLevels: buildPlanLevels({
        latestNav: analysis.fund.latestNav,
        ma10: latest.ma10,
        ma20: latest.ma20,
        ma60: latest.ma60,
        signal: latest.signal,
        hasHolding: Boolean(holding),
        addOnDipText: sizingSuggestion.addOnDip,
        addOnBreakoutText: sizingSuggestion.addOnBreakout,
        reduceText: sizingSuggestion.reduceOnWeakness,
        initialProbeText: sizingSuggestion.initialProbe,
      }),
      observationSignals: buildObservationSignals({
        ma20: latest.ma20,
        ma60: latest.ma60,
        holdingBreadth,
        peerBaseCount: peerBenchmark.peerBaseCount ?? 0,
        category,
      }),
      riskFlags: buildRiskFlags({
        category,
        volatility90d: analysis.trendAnalysis.risk.volatility90d,
        maxDrawdown90d: analysis.trendAnalysis.risk.maxDrawdown90d,
        concentrationTop5: holdingBreadth?.concentrationTop5 ?? null,
        hasHolding: Boolean(holding),
        portfolioPositionRatio,
      }),
    };
  }

  async getSnapshotForAgent(code: string) {
    const cleanCode = normalizeFundCode(code);
    const [detail, peerBenchmark, holdingBreadth, tradePlan] = await Promise.all([
      this.fundAnalysisService.getFundAnalysis(cleanCode, { historyDays: 180 }),
      this.getPeerBenchmark(cleanCode, 5),
      this.getHoldingBreadth(cleanCode, 10).catch(() => null),
      this.getTradePlanSnapshot(cleanCode).catch(() => null),
    ]);

    return {
      detail,
      peerBenchmark,
      holdingBreadth,
      tradePlan,
    };
  }
}

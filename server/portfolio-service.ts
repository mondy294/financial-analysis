import { getHoldings } from "./data-store.js";
import { getFundPerformance } from "./fund-service.js";
import { divideNumbers, roundNullable, sumNumbers } from "./analysis-utils.js";
import type { FundHoldingPortfolioResponse, FundHoldingSnapshot, PersistedHoldingItem } from "./types.js";

function normalizeFundCode(code: string) {
  const cleanCode = String(code || "").trim();
  if (!/^\d{6}$/.test(cleanCode)) {
    throw new Error("基金编号必须是 6 位数字。");
  }
  return cleanCode;
}

export class PortfolioService {
  async getHoldingRecord(code: string) {
    const cleanCode = normalizeFundCode(code);
    const payload = await getHoldings();
    return payload.items.find((item) => item.code === cleanCode) ?? null;
  }

  async listHoldingRecords() {
    const payload = await getHoldings();
    return payload.items;
  }

  async getHoldingSnapshot(code: string): Promise<FundHoldingSnapshot | null> {
    const record = await this.getHoldingRecord(code);
    if (!record) {
      return null;
    }

    return this.buildHoldingSnapshot(record);
  }

  async listHoldingSnapshots(): Promise<FundHoldingSnapshot[]> {
    const records = await this.listHoldingRecords();
    return Promise.all(records.map((record) => this.buildHoldingSnapshot(record)));
  }

  async getPortfolioResponse(): Promise<FundHoldingPortfolioResponse> {
    const items = await this.listHoldingSnapshots();
    return {
      items,
      summary: {
        holdingsCount: items.length,
        totalPositionAmount: sumNumbers(items.map((item) => item.positionAmount)),
        totalCurrentMarketValue: sumNumbers(items.map((item) => item.currentMarketValue)),
        totalEstimatedMarketValue: sumNumbers(items.map((item) => item.estimatedMarketValue)),
        totalCurrentProfitAmount: sumNumbers(items.map((item) => item.currentProfitAmount)),
        totalEstimatedProfitAmount: sumNumbers(items.map((item) => item.estimatedProfitAmount)),
      },
    };
  }

  private async buildHoldingSnapshot(record: PersistedHoldingItem): Promise<FundHoldingSnapshot> {
    try {
      const detail = await getFundPerformance(record.code);
      const fundName = detail.fund.name;
      const latestNav = detail.fund.latestNav;
      const estimatedNav = detail.fund.estimatedNav;
      const positionShares =
        typeof record.positionAmount === "number" && typeof record.costNav === "number" && record.costNav > 0
          ? roundNullable(record.positionAmount / record.costNav, 4)
          : null;
      const currentMarketValue =
        typeof positionShares === "number" && typeof latestNav === "number" ? roundNullable(positionShares * latestNav, 2) : null;
      const estimatedMarketValue =
        typeof positionShares === "number" && typeof estimatedNav === "number" ? roundNullable(positionShares * estimatedNav, 2) : null;
      const currentProfitAmount =
        typeof currentMarketValue === "number" && typeof record.positionAmount === "number"
          ? roundNullable(currentMarketValue - record.positionAmount, 2)
          : null;
      const estimatedProfitAmount =
        typeof estimatedMarketValue === "number" && typeof record.positionAmount === "number"
          ? roundNullable(estimatedMarketValue - record.positionAmount, 2)
          : null;

      return {
        code: record.code,
        fundName,
        status: record.status,
        holdingReturnRate: record.holdingReturnRate,
        positionAmount: record.positionAmount,
        costNav: record.costNav,
        note: record.note,
        updatedAt: record.updatedAt,
        positionShares,
        latestNav,
        latestNavDate: detail.fund.latestNavDate,
        estimatedNav,
        estimateTime: detail.fund.estimateTime,
        currentMarketValue,
        estimatedMarketValue,
        currentProfitAmount,
        currentProfitRate: divideNumbers(currentProfitAmount, record.positionAmount),
        estimatedProfitAmount,
        estimatedProfitRate: divideNumbers(estimatedProfitAmount, record.positionAmount),
      };
    } catch {
      return {
        code: record.code,
        fundName: null,
        status: record.status,
        holdingReturnRate: record.holdingReturnRate,
        positionAmount: record.positionAmount,
        costNav: record.costNav,
        note: record.note,
        updatedAt: record.updatedAt,
        positionShares:
          typeof record.positionAmount === "number" && typeof record.costNav === "number" && record.costNav > 0
            ? roundNullable(record.positionAmount / record.costNav, 4)
            : null,
        latestNav: null,
        latestNavDate: null,
        estimatedNav: null,
        estimateTime: null,
        currentMarketValue: null,
        estimatedMarketValue: null,
        currentProfitAmount: null,
        currentProfitRate: null,
        estimatedProfitAmount: null,
        estimatedProfitRate: null,
      };
    }
  }
}

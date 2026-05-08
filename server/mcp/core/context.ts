import { FundAnalysisService } from "../../fund-analysis-service.js";
import { FundResearchService } from "../../fund-research-service.js";
import { PortfolioService } from "../../portfolio-service.js";
import { StockAnalysisService } from "../../stock-analysis-service.js";
import { StockResearchService } from "../../stock-research-service.js";

export type FinancialMcpContext = {
  fundAnalysisService: FundAnalysisService;
  fundResearchService: FundResearchService;
  portfolioService: PortfolioService;
  stockAnalysisService: StockAnalysisService;
  stockResearchService: StockResearchService;
};

export function createFinancialMcpContext(): FinancialMcpContext {
  const portfolioService = new PortfolioService();
  const fundAnalysisService = new FundAnalysisService(portfolioService);
  const stockAnalysisService = new StockAnalysisService();

  return {
    portfolioService,
    fundAnalysisService,
    fundResearchService: new FundResearchService(portfolioService, fundAnalysisService),
    stockAnalysisService,
    stockResearchService: new StockResearchService(stockAnalysisService),
  };
}

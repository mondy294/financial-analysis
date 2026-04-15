import { FundAnalysisService } from "../../fund-analysis-service.js";
import { PortfolioService } from "../../portfolio-service.js";

export type FinancialMcpContext = {
  fundAnalysisService: FundAnalysisService;
  portfolioService: PortfolioService;
};

export function createFinancialMcpContext(): FinancialMcpContext {
  const portfolioService = new PortfolioService();

  return {
    portfolioService,
    fundAnalysisService: new FundAnalysisService(portfolioService),
  };
}

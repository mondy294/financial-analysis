import { FundAnalysisService } from "../../fund-analysis-service.js";
import { FundResearchService } from "../../fund-research-service.js";
import { PortfolioService } from "../../portfolio-service.js";

export type FinancialMcpContext = {
  fundAnalysisService: FundAnalysisService;
  fundResearchService: FundResearchService;
  portfolioService: PortfolioService;
};

export function createFinancialMcpContext(): FinancialMcpContext {
  const portfolioService = new PortfolioService();

  return {
    portfolioService,
    fundAnalysisService: new FundAnalysisService(portfolioService),
    fundResearchService: new FundResearchService(),
  };
}

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
  const fundAnalysisService = new FundAnalysisService(portfolioService);

  return {
    portfolioService,
    fundAnalysisService,
    fundResearchService: new FundResearchService(portfolioService, fundAnalysisService),
  };
}

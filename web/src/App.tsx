import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { HomePage } from "@/pages/HomePage";
import { PatternsPage } from "@/pages/PatternsPage";
import { EvalPage } from "@/pages/EvalPage";
import { StockPage } from "@/pages/StockPage";
import { SignalsPage } from "@/pages/SignalsPage";
import { ReportsPage } from "@/pages/ReportsPage";
import { SystemPage } from "@/pages/SystemPage";
import { StrategiesPage } from "@/pages/StrategiesPage";
import { StrategyEditorPage } from "@/pages/StrategyEditorPage";
import { ClustersPage } from "@/pages/ClustersPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="patterns" element={<PatternsPage />} />
        <Route path="patterns/eval" element={<EvalPage />} />
        <Route path="strategies" element={<StrategiesPage />} />
        <Route path="strategies/:id" element={<StrategyEditorPage />} />
        <Route path="clusters" element={<ClustersPage />} />
        <Route path="stocks/:code" element={<StockPage />} />
        <Route path="signals" element={<SignalsPage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="system" element={<SystemPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

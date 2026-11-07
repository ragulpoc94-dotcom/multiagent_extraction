import { Route, Routes } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import ArenaPage from "./pages/Arena";
import DocumentWorkspace from "./pages/DocumentWorkspace";
import EvaluationPage from "./pages/Evaluation";
import ExportCenter from "./pages/Exports";
import NotFound from "./pages/NotFound";
import OverviewPage from "./pages/Overview";
import PromptStudio from "./pages/PromptStudio";
import RequirementStudio from "./pages/RequirementStudio";
import ResultsPage from "./pages/Results";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<OverviewPage />} />
        <Route path="requirements" element={<RequirementStudio />} />
        <Route path="prompts" element={<PromptStudio />} />
        <Route path="documents" element={<DocumentWorkspace />} />
        <Route path="arena" element={<ArenaPage />} />
        <Route path="arena/:runId" element={<ArenaPage />} />
        <Route path="results" element={<ResultsPage />} />
        <Route path="evaluation" element={<EvaluationPage />} />
        <Route path="exports" element={<ExportCenter />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "@/App";
import { TooltipProvider } from "@/components/ui/tooltip";
import { WorkspaceProvider } from "@/lib/workspace";

export function renderApp(path = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <WorkspaceProvider>
        <TooltipProvider>
          <MemoryRouter initialEntries={[path]}>
            <App />
          </MemoryRouter>
        </TooltipProvider>
      </WorkspaceProvider>
    </QueryClientProvider>,
  );
}

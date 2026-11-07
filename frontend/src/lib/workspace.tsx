import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

/** The active selections that connect pages in the workflow. Persisted per browser. */
export interface Workspace {
  requirementId: string | null;
  promptRunId: string | null;
  documentId: string | null;
  competitionId: string | null;
}

const EMPTY: Workspace = { requirementId: null, promptRunId: null, documentId: null, competitionId: null };
const KEY = "n2.workspace";

function load(): Workspace {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? { ...EMPTY, ...JSON.parse(raw) } : EMPTY;
  } catch {
    return EMPTY;
  }
}

interface Ctx extends Workspace {
  set: (patch: Partial<Workspace>) => void;
}

const WorkspaceContext = createContext<Ctx | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [ws, setWs] = useState<Workspace>(load);
  const set = useCallback((patch: Partial<Workspace>) => {
    setWs((prev) => {
      const next = { ...prev, ...patch };
      try {
        localStorage.setItem(KEY, JSON.stringify(next));
      } catch {
        /* storage unavailable: keep in memory */
      }
      return next;
    });
  }, []);
  const value = useMemo(() => ({ ...ws, set }), [ws, set]);
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used inside WorkspaceProvider");
  return ctx;
}

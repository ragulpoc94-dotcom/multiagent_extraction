import { useQuery } from "@tanstack/react-query";
import {
  Download, FileSearch, FileSpreadsheet, Grid3x3, LayoutDashboard, Moon, ScrollText, Sun, Table2, Trophy,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { slotBg } from "@/components/common";
import { api } from "@/lib/api";
import { SLOTS, type Slot } from "@/lib/types";
import { cn } from "@/lib/utils";

// The workflow really is a sequence, so its steps are numbered.
const WORKFLOW = [
  { to: "/requirements", label: "Requirement Studio", icon: FileSpreadsheet },
  { to: "/prompts", label: "Prompt Engineering", icon: ScrollText },
  { to: "/documents", label: "Document Workspace", icon: FileSearch },
  { to: "/arena", label: "Competition Arena", icon: Grid3x3 },
];
const ANALYSIS = [
  { to: "/results", label: "Results Comparison", icon: Table2 },
  { to: "/evaluation", label: "Evaluation", icon: Trophy },
  { to: "/exports", label: "Export Center", icon: Download },
];

function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("theme", dark ? "dark" : "light");
    } catch {
      /* ignore */
    }
  }, [dark]);
  return [dark, setDark] as const;
}

function NavItem({ to, label, icon: Icon, step }: { to: string; label: string; icon: typeof Grid3x3; step?: number }) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        cn(
          "group flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
          isActive ? "bg-white/10 text-sidebar-foreground" : "text-sidebar-muted hover:bg-white/5 hover:text-sidebar-foreground",
        )
      }
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span className="flex-1 truncate">{label}</span>
      {step !== undefined && <span className="tabular text-2xs text-sidebar-muted/70">{step}</span>}
    </NavLink>
  );
}

function ModelLegend() {
  const { data } = useQuery({ queryKey: ["models"], queryFn: api.models, staleTime: 60_000 });
  const rows: { slot: Slot; model_id: string | null | undefined }[] =
    data?.models ?? SLOTS.map((slot) => ({ slot, model_id: undefined }));
  return (
    <div className="space-y-2 px-3">
      <p className="text-2xs text-sidebar-muted">Competing models</p>
      {rows.map((m) => (
        <div key={m.slot} className="flex items-center gap-2 text-xs text-sidebar-foreground/90">
          <span className={cn("h-2 w-2 shrink-0 rounded-full", slotBg(m.slot))} />
          <span className="font-medium">{m.slot}</span>
          <span className="truncate text-sidebar-muted" title={m.model_id ?? ""}>
            {m.model_id === undefined ? "…" : m.model_id ?? "not set"}
          </span>
        </div>
      ))}
    </div>
  );
}

export function AppShell({ children }: { children?: ReactNode }) {
  const [dark, setDark] = useTheme();
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col bg-sidebar text-sidebar-foreground md:flex">
        <div className="flex items-center gap-3 px-5 pb-6 pt-6">
          <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden>
            <rect width="32" height="32" rx="7" fill="rgba(255,255,255,0.08)" />
            <g fill="none" strokeWidth="2.4">
              <rect x="7" y="7" width="5" height="5" rx="1" className="stroke-m1" />
              <rect x="13.5" y="13.5" width="5" height="5" rx="1" className="stroke-m2" />
              <rect x="20" y="20" width="5" height="5" rx="1" className="stroke-m3" />
            </g>
          </svg>
          <div className="leading-tight">
            <p className="text-[0.95rem] font-semibold">N² Arena</p>
            <p className="text-2xs text-sidebar-muted">Agentic extraction benchmark</p>
          </div>
        </div>
        <nav className="flex-1 space-y-6 overflow-y-auto px-3">
          <div className="space-y-0.5">
            <NavItem to="/" label="Overview" icon={LayoutDashboard} />
          </div>
          <div className="space-y-0.5">
            <p className="px-3 pb-1.5 text-2xs text-sidebar-muted">Run a competition</p>
            {WORKFLOW.map((n, i) => (
              <NavItem key={n.to} {...n} step={i + 1} />
            ))}
          </div>
          <div className="space-y-0.5">
            <p className="px-3 pb-1.5 text-2xs text-sidebar-muted">Analyse</p>
            {ANALYSIS.map((n) => (
              <NavItem key={n.to} {...n} />
            ))}
          </div>
        </nav>
        <div className="space-y-4 border-t border-white/10 py-4">
          <ModelLegend />
          <div className="px-3">
            <button
              onClick={() => setDark(!dark)}
              className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-xs text-sidebar-muted hover:bg-white/5 hover:text-sidebar-foreground"
            >
              {dark ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
              {dark ? "Light theme" : "Dark theme"}
            </button>
          </div>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <MobileNav />
        <main className="mx-auto w-full max-w-[1440px] flex-1 px-6 py-8 lg:px-10">{children ?? <Outlet />}</main>
      </div>
    </div>
  );
}

function MobileNav() {
  return (
    <div className="flex gap-1 overflow-x-auto border-b bg-sidebar px-3 py-2 md:hidden">
      {[{ to: "/", label: "Overview", icon: LayoutDashboard }, ...WORKFLOW, ...ANALYSIS].map((n) => (
        <NavLink
          key={n.to}
          to={n.to}
          end={n.to === "/"}
          className={({ isActive }) =>
            cn("whitespace-nowrap rounded px-2.5 py-1.5 text-xs", isActive ? "bg-white/10 text-white" : "text-sidebar-muted")
          }
        >
          {n.label}
        </NavLink>
      ))}
    </div>
  );
}

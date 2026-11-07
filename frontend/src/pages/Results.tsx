import { useQuery } from "@tanstack/react-query";
import { Search, Table2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ExecutionDrawer } from "@/components/ExecutionDrawer";
import { EmptyState, ErrorBanner, FIELD_STATUS, PageHeader, slotText } from "@/components/common";
import { CompetitionPicker, useActiveCompetition } from "@/components/pickers";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tip } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { SLOTS, type Execution } from "@/lib/types";
import { cn, display, looseKey, shortModel } from "@/lib/utils";

type Kind = "agree" | "disagree" | "null" | "invalid" | "failed";

const KIND_LABEL: Record<Kind, string> = {
  agree: "Matches most common",
  disagree: "Differs",
  null: "Null",
  invalid: "Not returned or invalid",
  failed: "Run failed",
};

const KIND_CLS: Record<Kind, string> = {
  agree: "bg-success/10",
  disagree: "bg-warning/15",
  null: "text-muted-foreground",
  invalid: "bg-danger/10",
  failed: "text-muted-foreground bg-muted/50",
};

export default function ResultsPage() {
  const { id, list } = useActiveCompetition();
  const [gen, setGen] = useState("all");
  const [ext, setExt] = useState("all");
  const [q, setQ] = useState("");
  const [onlyDisagree, setOnlyDisagree] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const results = useQuery({ queryKey: ["results", id], queryFn: () => api.results(id!), enabled: !!id });
  const evaluation = useQuery({ queryKey: ["evaluation", id], queryFn: () => api.getEvaluation(id!), enabled: !!id, retry: false });
  const golden = evaluation.data?.golden_labels ?? null;

  const execs = useMemo(
    () => (results.data?.executions ?? []).filter((e) => (gen === "all" || e.prompt_slot === gen) && (ext === "all" || e.extraction_slot === ext)),
    [results.data, gen, ext],
  );

  const rows = useMemo(() => {
    if (!results.data) return [];
    const all = results.data.executions.filter((e) => e.status === "completed");
    return results.data.fields
      .filter((f) => !q || f.key.includes(q.toLowerCase()) || f.label.toLowerCase().includes(q.toLowerCase()))
      .map((f) => {
        const counts = new Map<string, number>();
        for (const e of all) {
          const k = looseKey(e.normalized?.extracted_fields[f.key]?.value);
          if (k) counts.set(k, (counts.get(k) ?? 0) + 1);
        }
        const majority = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
        return { f, majority, distinct: counts.size };
      })
      .filter((r) => !onlyDisagree || r.distinct > 1);
  }, [results.data, q, onlyDisagree]);

  const kindOf = (e: Execution, key: string, majority: string | null): Kind => {
    if (e.status !== "completed") return "failed";
    const fv = e.validation?.fields[key];
    if (!fv || fv.status === "not_returned" || fv.status === "type_error") return "invalid";
    if (fv.status === "missing") return "null";
    return looseKey(fv.value) === majority ? "agree" : "disagree";
  };

  if (!list.isLoading && !list.data?.length) {
    return (
      <div>
        <PageHeader title="Results Comparison" />
        <EmptyState icon={Table2} title="Nothing to compare yet" body="Run a competition first. This page lines up what all nine runs extracted for each field." action={<Button asChild><Link to="/documents">Start a competition</Link></Button>} />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Results Comparison"
        description="Every field, every run, side by side. Green means a run matches the most common value; amber means it differs. The most common value isn't necessarily correct, so check golden labels for accuracy."
        actions={<CompetitionPicker />}
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter fields" aria-label="Filter fields" className="h-9 w-56 rounded-md border border-input bg-card pl-8 pr-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
        </div>
        <NativeSelect aria-label="Prompt generator" value={gen} onChange={(e) => setGen(e.target.value)} className="w-48">
          <option value="all">All prompt generators</option>
          {SLOTS.map((s) => <option key={s} value={s}>Prompt P{s[1]} ({s})</option>)}
        </NativeSelect>
        <NativeSelect aria-label="Extraction model" value={ext} onChange={(e) => setExt(e.target.value)} className="w-48">
          <option value="all">All extraction models</option>
          {SLOTS.map((s) => <option key={s} value={s}>Extracted by {s}</option>)}
        </NativeSelect>
        <label className="ml-1 inline-flex items-center gap-2 text-sm">
          <input type="checkbox" checked={onlyDisagree} onChange={(e) => setOnlyDisagree(e.target.checked)} className="h-4 w-4 rounded border-input accent-[hsl(var(--foreground))]" />
          Only fields where runs disagree
        </label>
        <div className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
          {(["agree", "disagree", "null", "invalid"] as Kind[]).map((k) => (
            <span key={k} className="inline-flex items-center gap-1.5">
              <span className={cn("h-3 w-3 rounded-sm border", KIND_CLS[k])} />
              {KIND_LABEL[k]}
            </span>
          ))}
        </div>
      </div>

      <ErrorBanner error={results.error} />
      {results.isLoading ? (
        <Skeleton className="h-96" />
      ) : results.data ? (
        <Card className="overflow-hidden">
          <div className="overflow-auto scrollbar-thin">
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr className="border-b bg-muted/40">
                  <th className="sticky left-0 z-10 min-w-[180px] bg-muted/40 px-3 py-2.5 text-left font-medium text-muted-foreground backdrop-blur">Field</th>
                  {golden && <th className="min-w-[120px] border-l px-3 py-2.5 text-left font-medium">Golden</th>}
                  {execs.map((e) => (
                    <th key={e.id} className="min-w-[150px] border-l px-3 py-2 text-left font-normal">
                      <button onClick={() => setOpen(e.id)} className="text-left hover:underline">
                        <span className={cn("font-semibold", slotText(e.prompt_slot))}>{e.prompt_id}</span>
                        <span className="text-muted-foreground"> × </span>
                        <span className={cn("font-semibold", slotText(e.extraction_slot))}>{e.extraction_slot}</span>
                        <span className="block truncate text-2xs text-muted-foreground" title={e.extraction_model}>{shortModel(e.extraction_model)}</span>
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map(({ f, majority }) => (
                  <tr key={f.key} className="border-b last:border-0">
                    <td className="sticky left-0 z-10 bg-card px-3 py-2.5 align-top">
                      <p className="font-medium">{f.label}</p>
                      <p className="font-mono text-2xs text-muted-foreground">{f.key}, {f.data_type}</p>
                    </td>
                    {golden && <td className="border-l px-3 py-2.5 align-top font-medium">{golden[f.key] === undefined ? <span className="text-muted-foreground">not labelled</span> : display(golden[f.key]) || <span className="text-muted-foreground">null</span>}</td>}
                    {execs.map((e) => {
                      const kind = kindOf(e, f.key, majority);
                      const fv = e.validation?.fields[f.key];
                      const content = kind === "failed" ? e.status : kind === "null" ? "null" : fv?.value == null ? FIELD_STATUS[fv?.status ?? "not_returned"].label : display(fv.value);
                      return (
                        <td key={e.id} className={cn("border-l px-3 py-2.5 align-top", KIND_CLS[kind])}>
                          <Tip content={fv ? <span>{FIELD_STATUS[fv.status].label}{fv.evidence ? `: “${fv.evidence}”` : ""}{fv.page ? ` (page ${fv.page})` : ""}{fv.issues.length ? `. ${fv.issues.join("; ")}` : ""}</span> : e.error ?? e.status}>
                            <span className="block break-words">
                              {content}
                              {fv && ["unsupported", "page_invalid", "type_error"].includes(fv.status) && <span className={cn("ml-1 text-2xs font-medium", FIELD_STATUS[fv.status].cls)}>{FIELD_STATUS[fv.status].label.toLowerCase()}</span>}
                            </span>
                          </Tip>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {rows.length === 0 && <p className="p-6 text-center text-sm text-muted-foreground">No fields match these filters.</p>}
        </Card>
      ) : null}
      {id && <ExecutionDrawer runId={id} executionId={open} onClose={() => setOpen(null)} fields={results.data?.fields} metrics={evaluation.data?.combinations.find((c) => c.execution_id === open)} />}
    </div>
  );
}

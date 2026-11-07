import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, ChevronUp, FileSearch, ScrollText, Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { CopyButton, EmptyState, ErrorBanner, ModelChip, PageHeader, Spinner } from "@/components/common";
import { RequirementPicker } from "@/components/pickers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { GeneratedPrompt } from "@/lib/types";
import { cn, ms, num, pct, when } from "@/lib/utils";
import { useWorkspace } from "@/lib/workspace";

export default function PromptStudio() {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const runs = useQuery({
    queryKey: ["promptRuns", ws.requirementId],
    queryFn: () => api.listPromptRuns(ws.requirementId ?? undefined),
    enabled: !!ws.requirementId,
  });
  useEffect(() => {
    if (runs.data && runs.data.length && !runs.data.some((r) => r.id === ws.promptRunId)) ws.set({ promptRunId: runs.data[0].id });
  }, [runs.data, ws]);
  const run = useQuery({
    queryKey: ["promptRun", ws.promptRunId],
    queryFn: () => api.getPromptRun(ws.promptRunId!),
    enabled: !!ws.promptRunId,
  });
  const generate = useMutation({
    mutationFn: () => api.generatePrompts(ws.requirementId!),
    onSuccess: (r) => {
      ws.set({ promptRunId: r.id });
      qc.setQueryData(["promptRun", r.id], r);
      qc.invalidateQueries({ queryKey: ["promptRuns"] });
    },
  });

  return (
    <div>
      <PageHeader
        title="Prompt Engineering Studio"
        description="Each model wrote its own extraction prompt from the same workbook. These prompts run exactly as written: they aren't edited between runs."
        actions={
          <>
            <RequirementPicker />
            {runs.data && runs.data.length > 1 && (
              <NativeSelect aria-label="Prompt run" className="w-56" value={ws.promptRunId ?? ""} onChange={(e) => ws.set({ promptRunId: e.target.value })}>
                {runs.data.map((r) => <option key={r.id} value={r.id}>Generated {when(r.created_at)}</option>)}
              </NativeSelect>
            )}
            {ws.requirementId && (
              <Button variant="outline" onClick={() => generate.mutate()} disabled={generate.isPending}>
                {generate.isPending ? <Spinner /> : <Sparkles />} Regenerate
              </Button>
            )}
          </>
        }
      />
      <ErrorBanner error={generate.error} className="mb-4" />

      {!ws.requirementId ? (
        <EmptyState icon={ScrollText} title="Choose a requirement workbook first" body="Prompts are generated from a workbook's fields and rules." action={<Button asChild><Link to="/requirements">Go to Requirement Studio</Link></Button>} />
      ) : generate.isPending || run.isLoading ? (
        <div className="grid gap-4 xl:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-[420px]" />)}</div>
      ) : !run.data ? (
        <EmptyState
          icon={Sparkles}
          title="No prompts generated for this workbook"
          body="All three models will write a prompt in parallel. This usually takes 10 to 40 seconds."
          action={<Button onClick={() => generate.mutate()}><Sparkles /> Generate 3 prompts</Button>}
        />
      ) : (
        <>
          <div className="grid gap-4 xl:grid-cols-3">
            {run.data.prompts.map((p) => <PromptCard key={p.slot} p={p} />)}
          </div>
          <div className="mt-6 flex items-center justify-between rounded-lg border bg-card px-5 py-4">
            <p className="text-sm text-muted-foreground">
              Next: give these prompts a document. Each prompt runs on all three models, so 9 extraction runs in total.
            </p>
            <Button onClick={() => navigate("/documents")}><FileSearch /> Choose document</Button>
          </div>
        </>
      )}
    </div>
  );
}

function Check1({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 text-xs", ok ? "text-foreground" : "text-muted-foreground line-through")}>
      {ok ? <Check className="h-3 w-3 text-success" /> : <X className="h-3 w-3 text-danger" />}
      {label}
    </span>
  );
}

function PromptCard({ p }: { p: GeneratedPrompt }) {
  const [open, setOpen] = useState(false);
  return (
    <Card className="flex flex-col overflow-hidden">
      <div className={cn("h-1", { M1: "bg-m1", M2: "bg-m2", M3: "bg-m3" }[p.slot])} />
      <CardHeader className="gap-2">
        <div className="flex items-center justify-between gap-2">
          <ModelChip slot={p.slot} modelId={p.model_id} prefix={p.prompt_id} />
          {p.status === "completed" ? <Badge tone="success">Generated</Badge> : <Badge tone="danger">Failed</Badge>}
        </div>
        <p className="truncate font-mono text-2xs text-muted-foreground" title={p.model_id}>{p.model_id}</p>
        {p.status === "completed" && (
          <div className="tabular grid grid-cols-3 gap-2 border-y py-2.5 text-xs">
            <div><p className="text-muted-foreground">Time</p><p className="font-medium">{ms(p.latency_ms)}</p></div>
            <div><p className="text-muted-foreground">Tokens</p><p className="font-medium">{num(p.usage?.total_tokens)}</p></div>
            <div><p className="text-muted-foreground">Length</p><p className="font-medium">{num(p.checks?.characters)} chars</p></div>
          </div>
        )}
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-3">
        {p.error && <p className="text-sm text-danger">{p.error}</p>}
        {p.checks && (
          <div className="space-y-1.5">
            <p className="text-xs text-muted-foreground">
              Rule-based checks: mentions {pct(p.checks.field_key_coverage)} of field keys
              {p.checks.fields_not_mentioned.length > 0 && ` (missing ${p.checks.fields_not_mentioned.slice(0, 3).join(", ")}${p.checks.fields_not_mentioned.length > 3 ? "…" : ""})`}
            </p>
            <div className="flex flex-wrap gap-x-3 gap-y-1">
              <Check1 ok={p.checks.mentions_null_handling} label="Null handling" />
              <Check1 ok={p.checks.mentions_evidence} label="Evidence" />
              <Check1 ok={p.checks.mentions_page} label="Page refs" />
              <Check1 ok={p.checks.requests_json_only} label="JSON output" />
            </div>
          </div>
        )}
        {p.prompt_text && (
          <>
            <div className="relative">
              <pre className={cn("overflow-hidden whitespace-pre-wrap break-words rounded-md border bg-muted/40 p-3 font-mono text-[0.72rem] leading-relaxed", open ? "max-h-[640px] overflow-y-auto scrollbar-thin" : "max-h-56")}>
                {p.prompt_text}
              </pre>
              {!open && <div className="pointer-events-none absolute inset-x-px bottom-px h-16 rounded-b-md bg-gradient-to-t from-card to-transparent" />}
            </div>
            <div className="mt-auto flex items-center justify-between">
              <Button variant="ghost" size="sm" onClick={() => setOpen(!open)} aria-expanded={open}>
                {open ? <ChevronUp /> : <ChevronDown />} {open ? "Collapse" : "Show full prompt"}
              </Button>
              <CopyButton text={p.prompt_text} />
            </div>
          </>
        )}
        <p className="text-2xs text-muted-foreground">
          Generated {new Date(p.created_at).toLocaleString()}
          {p.used_own_interpretation ? ", using its own interpretation" : ""}
        </p>
      </CardContent>
    </Card>
  );
}

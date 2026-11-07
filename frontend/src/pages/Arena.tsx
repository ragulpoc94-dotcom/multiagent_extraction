import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Braces, Clock, Coins, Grid3x3, RotateCcw } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { ExecutionDrawer } from "@/components/ExecutionDrawer";
import { EmptyState, ErrorBanner, ModelChip, PageHeader, Spinner, StatusPill, slotBg } from "@/components/common";
import { CompetitionPicker, useActiveCompetition } from "@/components/pickers";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tip } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { SLOTS, type CellSummary, type ComboMetrics, type Slot } from "@/lib/types";
import { cn, ms, num, pct, shortModel } from "@/lib/utils";
import { useWorkspace } from "@/lib/workspace";

const ACTIVE = new Set(["queued", "running"]);

function useElapsed(start: string | null, end: string | null, live: boolean) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!live) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [live]);
  if (!start) return null;
  return ((end ? new Date(end).getTime() : now) - new Date(start).getTime()) / 1000;
}

export default function ArenaPage() {
  const { runId } = useParams();
  const ws = useWorkspace();
  const qc = useQueryClient();
  useEffect(() => {
    if (runId && runId !== ws.competitionId) ws.set({ competitionId: runId });
  }, [runId, ws]);
  const { id, list } = useActiveCompetition();
  const [openCell, setOpenCell] = useState<string | null>(null);

  const comp = useQuery({ queryKey: ["competition", id], queryFn: () => api.getCompetition(id!), enabled: !!id });
  const status = useQuery({
    queryKey: ["status", id],
    queryFn: () => api.competitionStatus(id!),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data && (q.state.data.is_running || ACTIVE.has(q.state.data.status)) ? 1500 : false),
  });
  const live = !!status.data && (status.data.is_running || ACTIVE.has(status.data.status));
  const evaluation = useQuery({
    queryKey: ["evaluation", id],
    queryFn: () => api.getEvaluation(id!),
    enabled: !!id && !!status.data && !live,
    retry: false,
  });
  const results = useQuery({ queryKey: ["results", id], queryFn: () => api.results(id!), enabled: !!id && !live });
  useEffect(() => {
    if (status.data && !live) {
      qc.invalidateQueries({ queryKey: ["evaluation", id] });
      qc.invalidateQueries({ queryKey: ["results", id] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    }
  }, [live, status.data?.status, id, qc]); // eslint-disable-line react-hooks/exhaustive-deps

  const resume = useMutation({
    mutationFn: () => api.resumeCompetition(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["status", id] }),
  });

  const elapsed = useElapsed(status.data?.started_at ?? null, live ? null : status.data?.finished_at ?? null, live);
  const metricsById = new Map<string, ComboMetrics>(evaluation.data?.combinations.map((c) => [c.execution_id, c]) ?? []);
  const cells = status.data?.cells ?? [];
  const cellAt = (g: Slot, e: Slot) => cells.find((c) => c.prompt_slot === g && c.extraction_slot === e);
  const done = cells.filter((c) => ["completed", "failed", "skipped"].includes(c.status)).length;
  const runnable = cells.filter((c) => c.status !== "skipped").length;
  const hasGolden = !!evaluation.data?.has_golden_labels;
  const bestId = evaluation.data?.best_combination?.execution_id;

  if (!list.isLoading && !list.data?.length) {
    return (
      <div>
        <PageHeader title="Model Competition Arena" />
        <EmptyState icon={Grid3x3} title="No competition has run yet" body="Generate prompts, process a document, then start the 3 × 3 competition from the Document Workspace." action={<Button asChild><Link to="/documents">Go to Document Workspace</Link></Button>} />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Model Competition Arena"
        description="Rows are the model that wrote the prompt. Columns are the model that ran it. The shaded diagonal is each model running its own prompt."
        actions={<CompetitionPicker />}
      />

      {status.isLoading || comp.isLoading ? (
        <Skeleton className="h-[560px]" />
      ) : status.error ? (
        <ErrorBanner error={status.error} />
      ) : status.data && comp.data ? (
        <>
          <Card className="mb-6 px-5 py-4">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <StatusPill status={live ? "running" : status.data.status} />
                <p className="text-sm">
                  <span className="font-medium">{comp.data.document_name}</span>
                  <span className="text-muted-foreground"> against {comp.data.requirement_name}, {comp.data.field_count} fields{comp.data.chunk_count > 1 ? `, ${comp.data.chunk_count} chunks per run` : ""}</span>
                </p>
              </div>
              <div className="flex items-center gap-5 text-sm">
                <span className="tabular text-muted-foreground">
                  <span className="font-semibold text-foreground">{done}</span> of {runnable} runs finished
                </span>
                {elapsed !== null && <span className="tabular text-muted-foreground"><Clock className="mr-1 inline h-3.5 w-3.5" />{ms(elapsed * 1000)}</span>}
                {["interrupted", "failed", "completed_with_errors"].includes(status.data.status) && !live && (
                  <Button variant="outline" size="sm" onClick={() => resume.mutate()} disabled={resume.isPending}>
                    {resume.isPending ? <Spinner /> : <RotateCcw />} Re-run unfinished
                  </Button>
                )}
              </div>
            </div>
            <div className="mt-3 flex h-1.5 gap-1" aria-hidden>
              {cells.map((c) => (
                <div key={c.id} className={cn("flex-1 rounded-full transition-colors duration-500", {
                  completed: "bg-success", failed: "bg-danger", interrupted: "bg-warning", skipped: "bg-muted", running: "bg-ring animate-cell-pulse", queued: "bg-muted",
                }[c.status])} />
              ))}
            </div>
            {status.data.error && <p className="mt-3 flex items-center gap-2 text-sm text-warning"><AlertTriangle className="h-4 w-4" />{status.data.error}</p>}
            <ErrorBanner error={resume.error} className="mt-3" />
          </Card>

          <Card className="overflow-x-auto p-5 lg:p-6">
            <div className="grid min-w-[760px] grid-cols-[180px_repeat(3,minmax(0,1fr))] gap-3">
              <div className="flex items-end pb-2 text-xs text-muted-foreground">
                <span>Prompt by ↓<br />Extracted by →</span>
              </div>
              {SLOTS.map((e) => (
                <div key={e} className="pb-2">
                  <div className={cn("mb-2 h-1 rounded-full", slotBg(e))} />
                  <ModelChip slot={e} modelId={comp.data.extraction_models[e]} compact />
                  <p className="mt-0.5 truncate text-xs text-muted-foreground" title={comp.data.extraction_models[e]}>{shortModel(comp.data.extraction_models[e])}</p>
                </div>
              ))}
              {SLOTS.map((g) => (
                <Row key={g} g={g} model={comp.data.models[g]}>
                  {SLOTS.map((e) => {
                    const c = cellAt(g, e);
                    return c ? (
                      <MatrixCell key={e} c={c} m={metricsById.get(c.id)} hasGolden={hasGolden} best={c.id === bestId} onOpen={() => setOpenCell(c.id)} />
                    ) : <div key={e} />;
                  })}
                </Row>
              ))}
            </div>
            <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 border-t pt-4 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1.5"><span className="self-hatch h-3 w-5 rounded-sm border" />Model ran its own prompt</span>
              <span className="inline-flex items-center gap-1.5"><span className="h-3 w-5 rounded-sm border-2 border-foreground" />Best combination</span>
              <span>
                {hasGolden ? "Score is field accuracy against your golden labels." : "Score is the verified fill rate: non-null, type-valid values whose evidence was found in the document. It isn't accuracy. Upload golden labels on the Evaluation page to measure accuracy."}
              </span>
            </div>
          </Card>
        </>
      ) : null}

      {id && <ExecutionDrawer runId={id} executionId={openCell} onClose={() => setOpenCell(null)} fields={results.data?.fields} metrics={openCell ? metricsById.get(openCell) : undefined} />}
    </div>
  );
}

function Row({ g, model, children }: { g: Slot; model: string; children: ReactNode }) {
  return (
    <>
      <div className="flex items-center gap-3 pr-2">
        <div className={cn("h-full w-1 rounded-full", slotBg(g))} />
        <div className="min-w-0">
          <ModelChip slot={g} modelId={model} prefix={`P${g[1]}`} compact />
          <p className="mt-0.5 truncate text-xs text-muted-foreground" title={model}>by {shortModel(model)}</p>
        </div>
      </div>
      {children}
    </>
  );
}

function MatrixCell({ c, m, hasGolden, best, onOpen }: { c: CellSummary; m?: ComboMetrics; hasGolden: boolean; best: boolean; onOpen: () => void }) {
  const score = hasGolden ? m?.field_accuracy : c.supported_fill_rate;
  const finished = c.status === "completed";
  return (
    <button
      onClick={onOpen}
      disabled={c.status === "skipped"}
      aria-label={`${c.prompt_id} prompt on ${c.extraction_slot}: ${c.status}`}
      className={cn(
        "group relative flex min-h-[148px] flex-col rounded-lg border bg-card p-4 text-left transition-all hover:-translate-y-px hover:shadow-md disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0 disabled:hover:shadow-none",
        c.is_self_prompt && "self-hatch",
        best && "border-2 border-foreground",
        c.status === "failed" && "border-danger/40",
        c.status === "running" && "border-ring/50",
        finished && "animate-fill-in",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="font-mono text-xs text-muted-foreground">{c.prompt_id}×{c.extraction_slot}</span>
        <StatusPill status={c.status} />
      </div>
      <div className="mt-3 flex-1">
        {finished ? (
          <p className="tabular text-[2rem] font-semibold leading-none tracking-[-0.02em]">{pct(score, 0)}</p>
        ) : c.status === "running" ? (
          <p className="text-sm text-muted-foreground animate-cell-pulse">{c.chunks_done > 0 ? `Chunk ${c.chunks_done} done…` : "Waiting for model…"}</p>
        ) : c.status === "queued" ? (
          <p className="text-sm text-muted-foreground">In queue</p>
        ) : (
          <p className="line-clamp-3 text-xs text-danger">{c.error}</p>
        )}
        {finished && <p className="mt-1 text-2xs text-muted-foreground">{hasGolden ? "field accuracy" : "verified fill rate"}</p>}
      </div>
      {(finished || c.status === "failed") && (
        <div className="tabular mt-3 flex items-center gap-3 border-t pt-2.5 text-xs text-muted-foreground">
          <Tip content="Total latency across chunks and retries"><span className="inline-flex items-center gap-1"><Clock className="h-3 w-3" />{ms(c.latency_ms)}</span></Tip>
          <Tip content="Total tokens (prompt + completion)"><span className="inline-flex items-center gap-1"><Coins className="h-3 w-3" />{num(c.usage?.total_tokens)}</span></Tip>
          {c.json_valid !== null && (
            <Tip content={c.json_valid ? "Response parsed and passed schema validation" : "Response was not valid JSON"}>
              <span className={cn("inline-flex items-center gap-1", c.json_valid ? "text-success" : "text-danger")}><Braces className="h-3 w-3" />{c.json_valid ? "Valid" : "Invalid"}</span>
            </Tip>
          )}
        </div>
      )}
    </button>
  );
}

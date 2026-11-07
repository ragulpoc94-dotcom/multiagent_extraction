import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, FileSpreadsheet, Grid3x3, KeyRound, ShieldCheck, XCircle } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { EmptyState, ErrorBanner, ModelChip, PageHeader, Spinner, Stat, StatusPill } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { pct, when } from "@/lib/utils";
import { useWorkspace } from "@/lib/workspace";

export default function OverviewPage() {
  const navigate = useNavigate();
  const ws = useWorkspace();
  const models = useQuery({ queryKey: ["models"], queryFn: api.models });
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const overview = useQuery({ queryKey: ["overview"], queryFn: api.overview, refetchInterval: 5000 });
  const verify = useMutation({ mutationFn: api.verifyModels });

  const latest = overview.data?.recent_competitions[0];
  const verified = new Map(verify.data?.models.map((m) => [m.slot, m.available]));

  return (
    <div>
      <PageHeader
        title="Overview"
        description="Three open-weight models each write an extraction prompt; every prompt then runs on every model. Nine runs per document show which model writes the best prompt and which extracts best."
        actions={
          <Button onClick={() => navigate("/requirements")}>
            <FileSpreadsheet /> New competition
          </Button>
        }
      />

      {models.data && models.data.missing.length > 0 && (
        <div className="mb-6 flex gap-3 rounded-lg border border-warning/40 bg-warning/5 px-4 py-3 text-sm">
          <KeyRound className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <div>
            <p className="font-medium">Groq isn't configured yet</p>
            <p className="text-muted-foreground">
              Set {models.data.missing.join(", ")} in <code className="font-mono text-xs">.env</code> at the project root, then restart
              the backend. You can still upload and inspect workbooks and documents.
            </p>
          </div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex-row items-start justify-between space-y-0">
            <div>
              <CardTitle>Model configuration</CardTitle>
              <CardDescription>One Groq key, three models. Each one both writes prompts and extracts.</CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={() => verify.mutate()} disabled={verify.isPending || !models.data?.api_key_configured}>
              {verify.isPending ? <Spinner /> : <ShieldCheck />} Check availability
            </Button>
          </CardHeader>
          <CardContent>
            {models.isLoading ? (
              <Skeleton className="h-28" />
            ) : (
              <div className="divide-y rounded-md border">
                {models.data?.models.map((m) => (
                  <div key={m.slot} className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
                    <div className="min-w-0">
                      <ModelChip slot={m.slot} modelId={m.model_id} compact />
                      <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground">{m.model_id ?? `${m.env_var} not set`}</p>
                    </div>
                    {verify.data ? (
                      verified.get(m.slot) ? (
                        <Badge tone="success"><CheckCircle2 className="h-3 w-3" /> Available</Badge>
                      ) : (
                        <Badge tone="danger"><XCircle className="h-3 w-3" /> Not available on this account</Badge>
                      )
                    ) : (
                      <span className="text-xs text-muted-foreground">{m.model_id ? "Not checked yet" : "Missing"}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
            <ErrorBanner error={verify.error} className="mt-3" />
            {models.data && (
              <p className="mt-3 text-xs text-muted-foreground">
                Up to {models.data.limits.max_concurrency} requests in parallel, {models.data.limits.requests_per_minute} requests/min,{" "}
                {models.data.limits.max_retries} retries with exponential backoff. Documents over{" "}
                {models.data.limits.max_document_tokens.toLocaleString()} tokens are split into page chunks.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Activity</CardTitle>
            <CardDescription>Across all runs stored locally</CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-x-4 gap-y-5">
            {overview.isLoading ? (
              <Skeleton className="col-span-2 h-28" />
            ) : (
              <>
                <Stat label="Competitions" value={overview.data?.counts.competitions ?? 0} />
                <Stat label="Workbooks" value={overview.data?.counts.requirements ?? 0} />
                <Stat label="Completed runs" value={overview.data?.counts.completed_executions ?? 0} />
                <Stat
                  label="Failed or interrupted"
                  value={<span className={overview.data?.counts.failed_executions ? "text-danger" : ""}>{overview.data?.counts.failed_executions ?? 0}</span>}
                />
              </>
            )}
            {health.data && (
              <div className="col-span-2 flex flex-wrap gap-1.5 border-t pt-4">
                <Badge tone={health.data.ocr_available ? "success" : "warning"}>OCR {health.data.ocr_available ? "ready" : "unavailable"}</Badge>
                <Badge tone="outline">PDF: {health.data.pdf_engine}</Badge>
                <Badge tone={health.data.groq_sdk_installed ? "success" : "danger"}>Groq SDK {health.data.groq_sdk_installed ? "installed" : "missing"}</Badge>
              </div>
            )}
            <ErrorBanner error={health.error} className="col-span-2" />
          </CardContent>
        </Card>
      </div>

      {latest && latest.best_combination && (
        <Card className="mt-6 overflow-hidden">
          <div className="grid md:grid-cols-[1.3fr_1fr]">
            <div className="p-6">
              <p className="text-sm text-muted-foreground">Latest result for {latest.document_name}</p>
              <p className="mt-2 text-2xl font-semibold tracking-[-0.015em]">
                {latest.best_combination.cell} leads with {pct(latest.best_score, 1)}{" "}
                <span className="text-base font-normal text-muted-foreground">
                  {latest.has_golden_labels ? "field accuracy" : "verified fill rate"}
                </span>
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                Prompt by {latest.best_combination.prompt_model}, extracted by {latest.best_combination.extraction_model}.
                {!latest.has_golden_labels && " Upload golden labels to measure true accuracy."}
              </p>
            </div>
            <div className="flex items-center gap-3 border-t bg-muted/40 p-6 md:border-l md:border-t-0">
              <Button
                variant="outline"
                onClick={() => {
                  ws.set({ competitionId: latest.id });
                  navigate("/arena");
                }}
              >
                <Grid3x3 /> Open arena
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  ws.set({ competitionId: latest.id });
                  navigate("/evaluation");
                }}
              >
                View evaluation
              </Button>
            </div>
          </div>
        </Card>
      )}

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Recent competitions</CardTitle>
        </CardHeader>
        <CardContent className="px-0 pb-2">
          <ErrorBanner error={overview.error} className="mx-5" />
          {overview.data && overview.data.recent_competitions.length === 0 ? (
            <div className="px-5 pb-3">
              <EmptyState
                icon={Grid3x3}
                title="No competitions yet"
                body="Upload a requirement workbook to start. The three models will interpret it, write prompts, and compete on your document."
                action={<Button asChild><Link to="/requirements">Upload requirements</Link></Button>}
              />
            </div>
          ) : (
            <Table>
              <THead>
                <TR className="hover:bg-transparent">
                  <TH className="pl-5">Document</TH>
                  <TH>Requirements</TH>
                  <TH>Status</TH>
                  <TH className="text-right">Runs done</TH>
                  <TH className="text-right">Failed</TH>
                  <TH>Best combination</TH>
                  <TH className="pr-5">Started</TH>
                </TR>
              </THead>
              <TBody>
                {overview.data?.recent_competitions.map((c) => (
                  <TR
                    key={c.id}
                    className="cursor-pointer"
                    onClick={() => {
                      ws.set({ competitionId: c.id });
                      navigate("/arena");
                    }}
                  >
                    <TD className="pl-5 font-medium">{c.document_name}</TD>
                    <TD className="text-muted-foreground">{c.requirement_name}</TD>
                    <TD><StatusPill status={c.status} /></TD>
                    <TD className="tabular text-right">{c.completed_cells}/{c.total_cells}</TD>
                    <TD className={`tabular text-right ${c.failed_cells ? "text-danger" : "text-muted-foreground"}`}>{c.failed_cells}</TD>
                    <TD>{c.best_combination ? <span className="font-medium">{c.best_combination.cell}</span> : <span className="text-muted-foreground">—</span>}</TD>
                    <TD className="pr-5 text-muted-foreground">{when(c.created_at)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

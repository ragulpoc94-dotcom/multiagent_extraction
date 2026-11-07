import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { CodeBlock, ErrorBanner, FIELD_STATUS, ModelChip, Stat, StatusPill } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import type { CanonicalField, ComboMetrics } from "@/lib/types";
import { cn, display, ms, num, pct } from "@/lib/utils";

export function ExecutionDrawer({
  runId, executionId, onClose, fields, metrics,
}: { runId: string; executionId: string | null; onClose: () => void; fields?: CanonicalField[]; metrics?: ComboMetrics }) {
  const ex = useQuery({
    queryKey: ["execution", runId, executionId],
    queryFn: () => api.execution(runId, executionId!),
    enabled: !!executionId,
    refetchInterval: (q) => (q.state.data && ["queued", "running"].includes(q.state.data.status) ? 1500 : false),
  });
  const e = ex.data;
  const v = e?.validation;
  const labels = new Map(fields?.map((f) => [f.key, f.label]));
  const keys = fields?.map((f) => f.key) ?? Object.keys(v?.fields ?? {});
  const golden = (metrics as unknown as { golden_field_results?: Record<string, { golden: unknown; correct: boolean }> })?.golden_field_results;

  return (
    <Dialog open={!!executionId} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{e ? `${e.prompt_id} prompt on ${e.extraction_slot}` : "Run details"}</DialogTitle>
          <DialogDescription asChild>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
              {e && (
                <>
                  <span>Prompt by <ModelChip slot={e.prompt_slot} modelId={e.prompt_model} /></span>
                  <span>Extracted by <ModelChip slot={e.extraction_slot} modelId={e.extraction_model} /></span>
                  <StatusPill status={e.status} />
                  {e.is_self_prompt && <Badge tone="outline">Model ran its own prompt</Badge>}
                </>
              )}
            </div>
          </DialogDescription>
        </DialogHeader>
        <div className="flex-1 overflow-y-auto px-6 py-5 scrollbar-thin">
          {ex.isLoading || !e ? (
            <Skeleton className="h-96" />
          ) : (
            <>
              <div className="mb-5 grid grid-cols-2 gap-4 rounded-lg border p-4 sm:grid-cols-5">
                <Stat label="Latency" value={ms(e.latency_ms)} />
                <Stat label="Tokens in / out" value={`${num(e.usage?.prompt_tokens)} / ${num(e.usage?.completion_tokens)}`} />
                <Stat label="Attempts" value={e.attempts || "—"} hint={e.chunks && e.chunks.length > 1 ? `${e.chunks.length} chunks` : undefined} />
                <Stat label="JSON" value={v ? (v.json_valid ? (v.schema_valid ? "Valid" : "Schema error") : "Invalid") : "—"} />
                <Stat label={metrics?.field_accuracy !== undefined ? "Field accuracy" : "Verified fill"} value={metrics?.field_accuracy !== undefined ? pct(metrics.field_accuracy, 1) : pct(v?.supported_fill_rate, 1)} />
              </div>
              {e.error && <ErrorBanner error={{ message: e.error }} className="mb-5" />}
              <Tabs defaultValue="fields">
                <TabsList>
                  <TabsTrigger value="fields">Extracted fields</TabsTrigger>
                  <TabsTrigger value="validation">Validation</TabsTrigger>
                  <TabsTrigger value="raw">Raw response</TabsTrigger>
                </TabsList>
                <TabsContent value="fields">
                  {!v ? (
                    <p className="text-sm text-muted-foreground">No output yet.</p>
                  ) : (
                    <Table className="text-xs">
                      <THead>
                        <TR className="hover:bg-transparent">
                          <TH>Field</TH><TH>Value</TH><TH>Evidence</TH><TH>Page</TH><TH>Check</TH>{golden && <TH>Golden</TH>}
                        </TR>
                      </THead>
                      <TBody>
                        {keys.map((k) => {
                          const f = v.fields[k];
                          const g = golden?.[k];
                          return (
                            <TR key={k}>
                              <TD className="font-medium">{labels.get(k) ?? k}</TD>
                              <TD className={cn("max-w-[180px] break-words", f?.value == null && "text-muted-foreground")}>{f?.value == null ? "null" : display(f.value)}</TD>
                              <TD className="max-w-[220px] break-words text-muted-foreground">{f?.evidence ? `“${f.evidence}”` : "—"}</TD>
                              <TD className="tabular">{f?.page ?? "—"}</TD>
                              <TD>
                                <span className={cn("font-medium", FIELD_STATUS[f?.status ?? "not_returned"].cls)} title={f?.issues.join("; ")}>
                                  {FIELD_STATUS[f?.status ?? "not_returned"].label}
                                </span>
                              </TD>
                              {golden && (
                                <TD className={g ? (g.correct ? "text-success" : "text-danger") : "text-muted-foreground"}>{g ? `${g.correct ? "✓" : "✗"} ${display(g.golden) || "null"}` : "not labelled"}</TD>
                              )}
                            </TR>
                          );
                        })}
                      </TBody>
                    </Table>
                  )}
                </TabsContent>
                <TabsContent value="validation" className="space-y-4 text-sm">
                  {v ? (
                    <>
                      <div className="grid grid-cols-3 gap-4 sm:grid-cols-6">
                        <Stat label="Expected" value={v.fields_expected} />
                        <Stat label="Filled" value={v.fields_filled} />
                        <Stat label="Null" value={v.missing} />
                        <Stat label="Not returned" value={v.not_returned} />
                        <Stat label="Type errors" value={v.type_errors} />
                        <Stat label="Unsupported" value={v.unsupported} />
                      </div>
                      {v.parse_error && <p className="text-danger">Parse error: {v.parse_error}</p>}
                      {v.unexpected_keys.length > 0 && <p className="text-muted-foreground">Keys not in the workbook: {v.unexpected_keys.join(", ")}</p>}
                      <ul className="space-y-1.5">
                        {Object.values(v.fields).filter((f) => f.issues.length).map((f) => (
                          <li key={f.key} className="rounded-md border px-3 py-2 text-xs">
                            <span className="font-medium">{labels.get(f.key) ?? f.key}</span>
                            <span className="text-muted-foreground">: {f.issues.join("; ")}</span>
                          </li>
                        ))}
                      </ul>
                      <p className="text-xs text-muted-foreground">“Unsupported” means a value was returned but its evidence quote wasn't found in the document text. Values are never repaired or filled in.</p>
                    </>
                  ) : (
                    <p className="text-muted-foreground">No validation yet.</p>
                  )}
                </TabsContent>
                <TabsContent value="raw" className="space-y-3">
                  {e.raw_response ? <CodeBlock>{e.raw_response}</CodeBlock> : <p className="text-sm text-muted-foreground">No response was received.</p>}
                  {e.chunks?.some((c) => c.notes?.length) && (
                    <p className="text-xs text-muted-foreground">Client notes: {e.chunks.flatMap((c) => c.notes ?? []).join(", ")}</p>
                  )}
                  <Button variant="outline" size="sm" asChild>
                    <a href={api.exportUrl(runId, "execution", e.id)}><Download /> Download this run as JSON</a>
                  </Button>
                </TabsContent>
              </Tabs>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

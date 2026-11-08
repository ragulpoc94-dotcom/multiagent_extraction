import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, BrainCircuit, FileSpreadsheet, ScrollText, Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Dropzone, EmptyState, ErrorBanner, ModelChip, PageHeader, Spinner } from "@/components/common";
import { RequirementPicker } from "@/components/pickers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import type { Interpretation, Requirement } from "@/lib/types";
import { cn, display, ms, num, pct } from "@/lib/utils";
import { useWorkspace } from "@/lib/workspace";

const ROLE_LABEL: Record<string, string> = {
  field: "Field name", description: "Description", data_type: "Data type", mandatory: "Mandatory",
  instructions: "Instructions", examples: "Example", allowed_values: "Allowed values",
};

export default function RequirementStudio() {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const req = useQuery({
    queryKey: ["requirement", ws.requirementId],
    queryFn: () => api.getRequirement(ws.requirementId!),
    enabled: !!ws.requirementId,
  });

  const uploadM = useMutation({
    mutationFn: api.uploadRequirements,
    onSuccess: (r) => {
      ws.set({ requirementId: r.id, promptRunId: null });
      qc.setQueryData(["requirement", r.id], r);
      qc.invalidateQueries({ queryKey: ["requirements"] });
    },
  });
  const understandM = useMutation({
    mutationFn: () => api.understand(ws.requirementId!),
    onSuccess: (r) => qc.setQueryData(["requirement", r.id], r),
  });
  const promptsM = useMutation({
    mutationFn: () => api.generatePrompts(ws.requirementId!),
    onSuccess: (run) => {
      ws.set({ promptRunId: run.id });
      qc.invalidateQueries({ queryKey: ["promptRuns"] });
      qc.setQueryData(["promptRun", run.id], run);
      navigate("/prompts");
    },
  });

  const r = req.data;

  return (
    <div>
      <PageHeader
        title="Requirement Studio"
        description="Upload the Excel workbook that defines what to extract. Fields, types and rules are discovered from the sheets themselves; nothing is hardcoded."
        actions={<RequirementPicker />}
      />

      <div className="grid gap-6 xl:grid-cols-[340px_1fr]">
        <div className="space-y-4">
          <Dropzone
            label="Drop a requirement workbook"
            hint=".xlsx, .xlsm, .xls or .csv, up to 25 MB"
            accept=".xlsx,.xlsm,.xls,.csv"
            busy={uploadM.isPending}
            onFile={(f) => uploadM.mutate(f)}
          />
          <ErrorBanner error={uploadM.error} />
          {r && (
            <Card>
              <CardHeader>
                <CardTitle className="truncate">{r.filename}</CardTitle>
                <CardDescription>
                  {r.requirement_set.fields.length} fields from {r.requirement_set.sheets.length} sheet
                  {r.requirement_set.sheets.length === 1 ? "" : "s"}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <Button className="w-full" variant="outline" onClick={() => understandM.mutate()} disabled={understandM.isPending}>
                  {understandM.isPending ? <Spinner /> : <BrainCircuit />}
                  {r.interpretations.length ? "Re-run model interpretation" : "Have the 3 models interpret it"}
                </Button>
                <Button className="w-full" onClick={() => promptsM.mutate()} disabled={promptsM.isPending}>
                  {promptsM.isPending ? <Spinner /> : <Sparkles />}
                  {promptsM.isPending ? "3 models are writing prompts…" : "Generate 3 extraction prompts"}
                </Button>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  Interpretation is optional. When it has run, each model writes its prompt with its own interpretation as
                  extra context, so the three stay independent.
                </p>
                <ErrorBanner error={understandM.error ?? promptsM.error} />
              </CardContent>
            </Card>
          )}
          {r && r.requirement_set.warnings.length > 0 && (
            <div className="space-y-1 rounded-lg border border-warning/40 bg-warning/5 p-3 text-xs">
              {r.requirement_set.warnings.map((w) => (
                <p key={w} className="flex gap-2"><AlertCircle className="h-3.5 w-3.5 shrink-0 text-warning" />{w}</p>
              ))}
            </div>
          )}
        </div>

        <div className="min-w-0">
          {!ws.requirementId ? (
            <EmptyState icon={FileSpreadsheet} title="No workbook selected" body="Upload a workbook with one row per field, such as Field Name, Description, Data Type, Mandatory and Instructions columns. A sheet whose headers are the fields also works." />
          ) : req.isLoading ? (
            <Skeleton className="h-96" />
          ) : req.error ? (
            <ErrorBanner error={req.error} />
          ) : r ? (
            <RequirementTabs r={r} understanding={understandM.isPending} />
          ) : null}
        </div>
      </div>
    </div>
  );
}

function RequirementTabs({ r, understanding }: { r: Requirement; understanding: boolean }) {
  const rs = r.requirement_set;
  return (
    <Tabs defaultValue="fields">
      <TabsList>
        <TabsTrigger value="fields">Interpreted fields ({rs.fields.length})</TabsTrigger>
        <TabsTrigger value="sheets">Worksheet preview</TabsTrigger>
        <TabsTrigger value="rules">Business rules ({rs.business_rules.length})</TabsTrigger>
        <TabsTrigger value="models">Model interpretations {r.interpretations.length ? `(${r.interpretations.length})` : ""}</TabsTrigger>
      </TabsList>

      <TabsContent value="fields">
        <Card>
          <Table>
            <THead>
              <TR className="hover:bg-transparent">
                <TH className="pl-5">Key</TH><TH>Label</TH><TH>Type</TH><TH>Required</TH><TH>Instructions and rules</TH><TH className="pr-5">Source</TH>
              </TR>
            </THead>
            <TBody>
              {rs.fields.map((f) => (
                <TR key={f.key}>
                  <TD className="pl-5 font-mono text-xs">{f.key}</TD>
                  <TD>
                    <p className="font-medium">{f.label}</p>
                    {f.description && <p className="text-xs text-muted-foreground">{f.description}</p>}
                  </TD>
                  <TD>
                    <Badge tone="outline">{f.data_type}</Badge>
                    {f.raw_type && f.raw_type.toLowerCase() !== f.data_type && <p className="mt-1 text-2xs text-muted-foreground">{f.raw_type}</p>}
                  </TD>
                  <TD>{f.mandatory ? <Badge tone="info">Required</Badge> : <span className="text-xs text-muted-foreground">Optional</span>}</TD>
                  <TD className="max-w-sm text-xs text-muted-foreground">
                    {f.instructions ?? "—"}
                    {f.allowed_values && <p className="mt-1">Allowed: {f.allowed_values.join(", ")}</p>}
                    {f.examples && <p className="mt-1">e.g. {f.examples}</p>}
                  </TD>
                  <TD className="pr-5 text-xs text-muted-foreground whitespace-nowrap">{f.source_sheet}{f.source_row ? `, row ${f.source_row}` : ""}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </Card>
      </TabsContent>

      <TabsContent value="sheets" className="space-y-4">
        {rs.sheets.map((s) => (
          <Card key={s.name}>
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <div>
                <CardTitle>{s.name}</CardTitle>
                <CardDescription>
                  {s.row_count} rows, read as {{ field_rows: "one field per row", header_template: "headers are fields", notes: "business rules", empty: "empty" }[s.layout]}
                </CardDescription>
              </div>
              <div className="flex flex-wrap justify-end gap-1">
                {Object.entries(s.detected_roles).map(([role, col]) => (
                  <Badge key={role} tone="outline" title={`Column "${col}"`}>{ROLE_LABEL[role] ?? role}: {col}</Badge>
                ))}
              </div>
            </CardHeader>
            {s.columns.length > 0 && (
              <Table className="text-xs">
                <THead>
                  <TR className="hover:bg-transparent">
                    {s.columns.map((c) => (
                      <TH key={c} className={cn(Object.values(s.detected_roles).includes(c) && "text-foreground")}>{c}</TH>
                    ))}
                  </TR>
                </THead>
                <TBody>
                  {s.rows.slice(0, 25).map((row, i) => (
                    <TR key={i}>
                      {s.columns.map((c) => <TD key={c} className="max-w-xs truncate py-2">{display(row[c])}</TD>)}
                    </TR>
                  ))}
                </TBody>
              </Table>
            )}
          </Card>
        ))}
      </TabsContent>

      <TabsContent value="rules">
        <Card>
          <CardContent className="pt-5">
            {rs.business_rules.length === 0 ? (
              <p className="text-sm text-muted-foreground">No sheet-level rules found. Field-level instructions are in the fields table.</p>
            ) : (
              <ol className="list-decimal space-y-2 pl-5 text-sm">
                {rs.business_rules.map((b, i) => <li key={i}>{b}</li>)}
              </ol>
            )}
          </CardContent>
        </Card>
      </TabsContent>

      <TabsContent value="models">
        {understanding ? (
          <div className="grid gap-4 lg:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-72" />)}</div>
        ) : r.interpretations.length === 0 ? (
          <EmptyState icon={ScrollText} title="Not interpreted yet" body="Ask the three models to read the workbook. Each returns its own understanding of fields, rules and ambiguities." />
        ) : (
          <div className="grid gap-4 lg:grid-cols-3">
            {r.interpretations.map((i) => <InterpretationCard key={i.slot} i={i} total={rs.fields.length} />)}
          </div>
        )}
      </TabsContent>
    </Tabs>
  );
}

function InterpretationCard({ i, total }: { i: Interpretation; total: number }) {
  return (
    <Card className="flex flex-col">
      <CardHeader>
        <ModelChip slot={i.slot} modelId={i.model_id} />
        {i.status === "completed" ? (
          <p className="tabular text-xs text-muted-foreground">
            {ms(i.latency_ms)}, {num(i.usage?.total_tokens)} tokens, covers {pct(i.coverage)} of {total} fields
          </p>
        ) : (
          <Badge tone="danger" className="w-fit">Failed</Badge>
        )}
      </CardHeader>
      <CardContent className="flex-1 space-y-4 text-sm">
        {i.error && <p className="text-danger">{i.error}</p>}
        {i.summary && <p className="leading-relaxed">{i.summary}</p>}
        {i.fields.length > 0 && (
          <div>
            <p className="mb-1.5 text-xs font-medium text-muted-foreground">Fields it identified</p>
            <div className="flex flex-wrap gap-1">
              {i.fields.map((f, n) => <Badge key={n} tone="outline">{f.name ?? f.key}</Badge>)}
            </div>
          </div>
        )}
        {i.ambiguities.length > 0 && (
          <div>
            <p className="mb-1.5 text-xs font-medium text-muted-foreground">Ambiguities it flagged</p>
            <ul className="list-disc space-y-1 pl-4 text-xs text-muted-foreground">{i.ambiguities.map((a, n) => <li key={n}>{a}</li>)}</ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

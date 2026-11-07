import { useQuery } from "@tanstack/react-query";
import { Braces, Download, FileJson, FileSpreadsheet, Package, ScrollText, Sheet } from "lucide-react";
import { Link } from "react-router-dom";
import { EmptyState, PageHeader, StatusPill } from "@/components/common";
import { CompetitionPicker, useActiveCompetition } from "@/components/pickers";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { shortModel } from "@/lib/utils";

export default function ExportCenter() {
  const { id, list } = useActiveCompetition();
  const status = useQuery({ queryKey: ["status", id], queryFn: () => api.competitionStatus(id!), enabled: !!id });

  if (!list.isLoading && !list.data?.length) {
    return (
      <div>
        <PageHeader title="Export Center" />
        <EmptyState icon={Package} title="Nothing to export yet" body="Exports become available once a competition has run." action={<Button asChild><Link to="/documents">Start a competition</Link></Button>} />
      </div>
    );
  }

  const files = id
    ? [
        { icon: FileSpreadsheet, title: "Excel evaluation report", body: "Summary, leaderboard, both rankings, own vs other prompt, field comparison, prompts and run log, one sheet each.", href: api.exportUrl(id, "xlsx"), ext: ".xlsx" },
        { icon: Sheet, title: "Field comparison CSV", body: "One row per field, with each run's value and validation status, plus golden labels if uploaded.", href: api.exportUrl(id, "csv"), ext: ".csv" },
        { icon: FileJson, title: "Consolidated results", body: "Everything in one file: fields, document details, prompts, all nine runs with raw responses, and the evaluation.", href: api.exportUrl(id, "consolidated"), ext: ".json" },
        { icon: ScrollText, title: "Generated prompts", body: "The three prompts exactly as the models wrote them, with model IDs, timestamps and token usage.", href: api.exportUrl(id, "prompts"), ext: ".json" },
      ]
    : [];

  return (
    <div>
      <PageHeader title="Export Center" description="Download prompts, run outputs and reports to share or archive. Files are generated from the stored results when you click." actions={<CompetitionPicker />} />
      <div className="grid gap-4 md:grid-cols-2">
        {files.map((f) => (
          <Card key={f.title} className="flex flex-col">
            <CardHeader className="flex-row items-start gap-4 space-y-0">
              <div className="rounded-md bg-secondary p-2.5"><f.icon className="h-5 w-5" /></div>
              <div className="flex-1">
                <CardTitle>{f.title}</CardTitle>
                <CardDescription className="mt-1">{f.body}</CardDescription>
              </div>
            </CardHeader>
            <CardContent className="mt-auto">
              <Button variant="outline" asChild><a href={f.href} download><Download /> Download {f.ext}</a></Button>
            </CardContent>
          </Card>
        ))}
      </div>
      {status.data && (
        <Card className="mt-6">
          <CardHeader><CardTitle>Individual run outputs</CardTitle><CardDescription>Normalised JSON, validation report and raw response for each combination.</CardDescription></CardHeader>
          <CardContent className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {status.data.cells.map((c) => (
              <a key={c.id} href={api.exportUrl(id!, "execution", c.id)} download className="flex items-center justify-between gap-3 rounded-md border px-3 py-2.5 text-sm transition-colors hover:bg-accent">
                <span className="flex min-w-0 items-center gap-2">
                  <Braces className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="font-medium">{c.cell}</span>
                  <span className="truncate text-xs text-muted-foreground">{shortModel(c.extraction_model)}</span>
                </span>
                <StatusPill status={c.status} />
              </a>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

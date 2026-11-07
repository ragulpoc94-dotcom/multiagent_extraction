import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, FileSearch, Grid3x3, ScanText } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Dropzone, EmptyState, ErrorBanner, PageHeader, Spinner, Stat, StatusPill } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { DocPage } from "@/lib/types";
import { bytes, cn, num, when } from "@/lib/utils";
import { useWorkspace } from "@/lib/workspace";

const METHOD: Record<DocPage["method"], { label: string; tone: "success" | "info" | "danger" | "neutral" }> = {
  digital: { label: "Digital text", tone: "success" },
  ocr: { label: "OCR", tone: "info" },
  ocr_failed: { label: "OCR failed", tone: "danger" },
  empty: { label: "No text", tone: "neutral" },
};

export default function DocumentWorkspace() {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const docs = useQuery({ queryKey: ["documents"], queryFn: api.listDocuments });
  const doc = useQuery({ queryKey: ["document", ws.documentId], queryFn: () => api.getDocument(ws.documentId!), enabled: !!ws.documentId });
  const promptRun = useQuery({ queryKey: ["promptRun", ws.promptRunId], queryFn: () => api.getPromptRun(ws.promptRunId!), enabled: !!ws.promptRunId });
  useEffect(() => setPage(1), [ws.documentId]);

  const process = useMutation({
    mutationFn: (id: string) => api.processDocument(id),
    onSuccess: (d) => {
      qc.setQueryData(["document", d.id], d);
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
  });
  const uploadM = useMutation({
    mutationFn: api.uploadDocument,
    onSuccess: (d) => {
      ws.set({ documentId: d.id });
      qc.setQueryData(["document", d.id], d);
      qc.invalidateQueries({ queryKey: ["documents"] });
      process.mutate(d.id);
    },
  });
  const start = useMutation({
    mutationFn: () => api.createCompetition(ws.promptRunId!, ws.documentId!),
    onSuccess: (c) => {
      ws.set({ competitionId: c.id });
      qc.invalidateQueries({ queryKey: ["competitions"] });
      navigate("/arena");
    },
  });

  const d = doc.data;
  const pages = d?.pages ?? [];
  const current = pages.find((p) => p.page === page);
  const okPrompts = promptRun.data?.prompts.filter((p) => p.status === "completed").length ?? 0;

  return (
    <div>
      <PageHeader
        title="Document Workspace"
        description="The document is processed once. All nine extraction runs then receive exactly the same page-tagged text."
        actions={
          docs.data && docs.data.length > 0 ? (
            <NativeSelect aria-label="Document" className="w-72" value={ws.documentId ?? ""} onChange={(e) => ws.set({ documentId: e.target.value })}>
              <option value="" disabled>Choose a document</option>
              {docs.data.map((x) => <option key={x.id} value={x.id}>{x.filename} — {when(x.created_at)}</option>)}
            </NativeSelect>
          ) : undefined
        }
      />

      <div className="grid gap-6 xl:grid-cols-[340px_1fr]">
        <div className="space-y-4">
          <Dropzone label="Drop a document" hint="PDF, PNG, JPEG or TIFF. Use synthetic or anonymised data." accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff" busy={uploadM.isPending} onFile={(f) => uploadM.mutate(f)} />
          <ErrorBanner error={uploadM.error ?? process.error} />

          {d && (
            <Card>
              <CardHeader>
                <div className="flex items-start justify-between gap-2">
                  <CardTitle className="truncate">{d.filename}</CardTitle>
                  <StatusPill status={process.isPending ? "running" : d.status === "processed" ? "completed" : d.status} />
                </div>
                <CardDescription>{bytes(d.size_bytes)}, {d.kind === "pdf" ? "PDF" : "image"}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {d.status === "processed" && (
                  <div className="grid grid-cols-2 gap-4">
                    <Stat label="Pages" value={d.page_count} />
                    <Stat label="Est. tokens" value={num(d.estimated_tokens)} />
                    <Stat label="Characters" value={num(d.total_chars)} />
                    <Stat label="Chunks per run" value={d.chunks_planned} hint={d.chunks_planned && d.chunks_planned > 1 ? "Split to fit the context window" : "Fits in one call"} />
                  </div>
                )}
                {d.error && <p className="text-sm text-danger">{d.error}</p>}
                {d.status !== "processed" && (
                  <Button variant="outline" className="w-full" onClick={() => process.mutate(d.id)} disabled={process.isPending}>
                    {process.isPending ? <Spinner /> : <ScanText />} {process.isPending ? "Extracting text…" : "Process document"}
                  </Button>
                )}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Start the competition</CardTitle>
              <CardDescription>
                {promptRun.data ? `${okPrompts} of 3 prompts ready. ${okPrompts * 3} of 9 runs can start.` : "Generate prompts in the Prompt Engineering Studio first."}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button className="w-full" size="lg" disabled={!promptRun.data || okPrompts === 0 || d?.status !== "processed" || start.isPending} onClick={() => start.mutate()}>
                {start.isPending ? <Spinner /> : <Grid3x3 />} Run 3 × 3 competition
              </Button>
              <ErrorBanner error={start.error} className="mt-3" />
            </CardContent>
          </Card>
        </div>

        <div className="min-w-0">
          {!ws.documentId ? (
            <EmptyState icon={FileSearch} title="No document selected" body="Upload a PDF or image. Digital PDF text is read directly; scanned pages and images go through Tesseract OCR, page by page." />
          ) : doc.isLoading ? (
            <Skeleton className="h-[640px]" />
          ) : d && pages.length > 0 ? (
            <Card className="overflow-hidden">
              <div className="flex items-center justify-between border-b px-4 py-2.5">
                <div className="flex items-center gap-1">
                  <Button variant="ghost" size="icon" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft /></Button>
                  <span className="tabular min-w-[90px] text-center text-sm">Page {page} of {pages.length}</span>
                  <Button variant="ghost" size="icon" aria-label="Next page" disabled={page >= pages.length} onClick={() => setPage(page + 1)}><ChevronRight /></Button>
                </div>
                {current && (
                  <div className="flex items-center gap-2">
                    <Badge tone={METHOD[current.method].tone}>{METHOD[current.method].label}</Badge>
                    {current.ocr_confidence !== null && <span className="tabular text-xs text-muted-foreground">OCR confidence {current.ocr_confidence}%</span>}
                  </div>
                )}
              </div>
              <div className="grid lg:grid-cols-2">
                <div className="flex min-h-[560px] items-start justify-center bg-muted/40 p-4">
                  <img key={`${d.id}-${page}`} src={api.pageImageUrl(d.id, page)} alt={`Page ${page} of ${d.filename}`} className="max-h-[760px] w-auto rounded border bg-white shadow-sm" loading="lazy" />
                </div>
                <div className="border-t lg:border-l lg:border-t-0">
                  <p className="border-b px-4 py-2 text-xs text-muted-foreground">Text the models receive for this page</p>
                  <pre className={cn("max-h-[720px] overflow-auto whitespace-pre-wrap break-words p-4 font-mono text-xs leading-relaxed scrollbar-thin", !current?.text && "text-muted-foreground")}>
                    {current?.error ? `OCR error: ${current.error}\n\n` : ""}
                    {current?.text || "No text extracted from this page."}
                  </pre>
                </div>
              </div>
              <div className="flex gap-1 overflow-x-auto border-t px-4 py-2.5 scrollbar-thin">
                {pages.map((p) => (
                  <button key={p.page} onClick={() => setPage(p.page)} className={cn("tabular rounded px-2 py-1 text-xs", p.page === page ? "bg-primary text-primary-foreground" : "hover:bg-accent", p.method === "ocr_failed" && p.page !== page && "text-danger")}>
                    {p.page}
                  </button>
                ))}
              </div>
            </Card>
          ) : d ? (
            <EmptyState icon={ScanText} title={process.isPending ? "Extracting text…" : "Not processed yet"} body="Processing reads each page and records whether its text came from the PDF or from OCR." />
          ) : null}
        </div>
      </div>
    </div>
  );
}

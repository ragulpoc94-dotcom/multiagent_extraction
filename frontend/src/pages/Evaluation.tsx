import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Info, RefreshCw, Trophy, Upload, X } from "lucide-react";
import { useRef } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EmptyState, ErrorBanner, ModelChip, PageHeader, Spinner, StatusPill } from "@/components/common";
import { CompetitionPicker, useActiveCompetition } from "@/components/pickers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { api, ApiError } from "@/lib/api";
import { SLOTS, type Evaluation, type GroupRanking, type Slot } from "@/lib/types";
import { cn, ms, num, pct, shortModel } from "@/lib/utils";

const SLOT_COLOR: Record<Slot, string> = { M1: "hsl(var(--m1))", M2: "hsl(var(--m2))", M3: "hsl(var(--m3))" };
const AXIS = { fontSize: 11, fill: "hsl(var(--muted-foreground))" };
const TOOLTIP_STYLE = { background: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12, color: "hsl(var(--foreground))" };

export default function EvaluationPage() {
  const qc = useQueryClient();
  const { id, list } = useActiveCompetition();
  const fileRef = useRef<HTMLInputElement>(null);
  const ev = useQuery({ queryKey: ["evaluation", id], queryFn: () => api.getEvaluation(id!), enabled: !!id, retry: false });
  const set = (e: Evaluation) => qc.setQueryData(["evaluation", id], e);
  const evaluate = useMutation({ mutationFn: (f?: File) => api.evaluate(id!, f), onSuccess: set });
  const clear = useMutation({ mutationFn: () => api.clearGolden(id!), onSuccess: set });
  const notYet = ev.error instanceof ApiError && ev.error.status === 404;

  if (!list.isLoading && !list.data?.length) {
    return (
      <div>
        <PageHeader title="Evaluation" />
        <EmptyState icon={Trophy} title="No competition to evaluate" body="Rankings appear here after a competition finishes." action={<Button asChild><Link to="/documents">Start a competition</Link></Button>} />
      </div>
    );
  }

  const e = ev.data;
  return (
    <div>
      <PageHeader
        title="Evaluation"
        description="Rankings of prompt writers, extraction models and their nine combinations, all from measured results."
        actions={
          <>
            <CompetitionPicker />
            <input ref={fileRef} type="file" accept=".json,.csv,.xlsx" className="hidden" onChange={(x) => { const f = x.target.files?.[0]; if (f) evaluate.mutate(f); x.target.value = ""; }} />
            <Button variant="outline" onClick={() => fileRef.current?.click()} disabled={!id || evaluate.isPending}>
              {evaluate.isPending ? <Spinner /> : <Upload />} {e?.has_golden_labels ? "Replace golden labels" : "Upload golden labels"}
            </Button>
            <Button variant="ghost" size="icon" aria-label="Recalculate" onClick={() => evaluate.mutate(undefined)} disabled={!id || evaluate.isPending}><RefreshCw /></Button>
          </>
        }
      />
      <ErrorBanner error={evaluate.error ?? clear.error} className="mb-4" />

      {ev.isLoading ? (
        <Skeleton className="h-[600px]" />
      ) : notYet ? (
        <EmptyState icon={Trophy} title="Not evaluated yet" body="Evaluation runs automatically when a competition finishes. If the run is still going, check the arena." action={<Button onClick={() => evaluate.mutate(undefined)}>Evaluate now</Button>} />
      ) : ev.error ? (
        <ErrorBanner error={ev.error} />
      ) : e ? (
        <div className="space-y-6">
          <MetricNotice e={e} onClear={() => clear.mutate()} clearing={clear.isPending} />
          <Podium e={e} />
          <div className="grid gap-6 xl:grid-cols-2">
            <RankingCard title="Prompt generator ranking" description="Each prompt's average across all three extraction models" rows={e.prompt_generator_ranking} prefix="P" e={e} />
            <RankingCard title="Extraction model ranking" description="Each model's average across all three generated prompts" rows={e.extraction_model_ranking} e={e} />
          </div>
          <div className="grid gap-6 xl:grid-cols-[1fr_1.2fr]">
            <Heatmap e={e} />
            <SelfVsCross e={e} />
          </div>
          <div className="grid gap-6 xl:grid-cols-2">
            <LatencyChart e={e} />
            <TokenChart e={e} />
          </div>
          <Leaderboard e={e} />
        </div>
      ) : null}
    </div>
  );
}

function MetricNotice({ e, onClear, clearing }: { e: Evaluation; onClear: () => void; clearing: boolean }) {
  return (
    <div className={cn("flex flex-wrap items-start gap-3 rounded-lg border px-4 py-3 text-sm", e.has_golden_labels ? "border-success/30 bg-success/5" : "border-ring/30 bg-ring/5")}>
      <Info className={cn("mt-0.5 h-4 w-4 shrink-0", e.has_golden_labels ? "text-success" : "text-ring")} />
      <div className="flex-1">
        <p className="font-medium">Ranked by {e.primary_metric_label.charAt(0).toLowerCase() + e.primary_metric_label.slice(1)}</p>
        <p className="text-muted-foreground">
          {e.has_golden_labels
            ? `Accuracy is measured against ${e.golden_field_count} golden labels you uploaded. Field accuracy normalises dates, numbers and spacing; exact match compares the raw strings.`
            : "No golden labels yet, so no accuracy figures are shown. Upload a JSON, CSV or Excel file of verified values to measure accuracy."}
          {" "}Agreement between models is shown separately and doesn't prove correctness.
        </p>
        {e.golden_unknown_keys.length > 0 && <p className="mt-1 text-warning">Ignored label keys not in the workbook: {e.golden_unknown_keys.join(", ")}</p>}
      </div>
      {e.has_golden_labels && <Button variant="ghost" size="sm" onClick={onClear} disabled={clearing}><X /> Remove labels</Button>}
    </div>
  );
}

function Podium({ e }: { e: Evaluation }) {
  const g = e.prompt_generator_ranking[0];
  const m = e.extraction_model_ranking[0];
  const b = e.best_combination;
  const metricLabel = e.has_golden_labels ? "field accuracy" : "verified fill rate";
  const items = [
    { title: "Best combination", slot: b?.prompt_slot, body: b ? `${b.prompt_id} prompt on ${b.extraction_slot}` : "—", score: b ? (b as unknown as Record<string, number>)[e.primary_metric] : null, sub: b ? `Prompt by ${shortModel(b.prompt_model)}, extracted by ${shortModel(b.extraction_model)}` : "" },
    { title: "Best prompt writer", slot: g?.slot, body: g ? shortModel(g.model_id) : "—", score: g?.primary_metric, sub: "Average over the 3 models running its prompt" },
    { title: "Best extraction model", slot: m?.slot, body: m ? shortModel(m.model_id) : "—", score: m?.primary_metric, sub: "Average over the 3 prompts it ran" },
  ];
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {items.map((it, i) => (
        <Card key={it.title} className={cn("relative overflow-hidden", i === 0 && "border-foreground/60")}>
          {it.slot && <div className="absolute inset-y-0 left-0 w-1" style={{ background: SLOT_COLOR[it.slot] }} />}
          <CardContent className="pt-5">
            <p className="text-sm text-muted-foreground">{it.title}</p>
            <p className="mt-1 truncate text-lg font-semibold" title={it.body}>{it.body}</p>
            <p className="tabular mt-3 text-3xl font-semibold tracking-[-0.02em]">{pct(it.score, 1)}</p>
            <p className="text-xs text-muted-foreground">{metricLabel}</p>
            <p className="mt-2 text-xs text-muted-foreground">{it.sub}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function RankingCard({ title, description, rows, prefix, e }: { title: string; description: string; rows: GroupRanking[]; prefix?: string; e: Evaluation }) {
  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle><CardDescription>{description}</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        {rows.map((r) => (
          <div key={r.slot}>
            <div className="mb-1.5 flex items-center justify-between gap-3 text-sm">
              <span className="flex min-w-0 items-center gap-2"><span className="tabular w-4 text-muted-foreground">{r.rank}</span><ModelChip slot={r.slot} modelId={r.model_id} prefix={prefix ? `${prefix}${r.slot[1]}` : undefined} /></span>
              <span className="tabular font-semibold">{pct(r.primary_metric, 1)}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full transition-[width] duration-700" style={{ width: `${(r.primary_metric ?? 0) * 100}%`, background: SLOT_COLOR[r.slot] }} />
            </div>
            <p className="tabular mt-1.5 text-xs text-muted-foreground">
              {e.has_golden_labels && `exact match ${pct(r.exact_match_accuracy)}, `}missing {pct(r.missing_rate)}, valid JSON {pct(r.json_validity_rate)}, API failures {pct(r.api_failure_rate)}, {ms(r.avg_latency_ms)} avg, {num(r.avg_total_tokens)} tokens avg
            </p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function Heatmap({ e }: { e: Evaluation }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{e.has_golden_labels ? "Accuracy heatmap" : "Verified fill rate heatmap"}</CardTitle>
        <CardDescription>Rows: prompt writer. Columns: extraction model.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-[60px_repeat(3,1fr)] gap-1.5">
          <div />
          {SLOTS.map((s) => <div key={s} className="pb-1 text-center text-xs font-semibold" style={{ color: SLOT_COLOR[s] }}>{s}</div>)}
          {e.heatmap.values.map((row, i) => (
            <div key={i} className="contents">
              <div className="flex items-center text-xs font-semibold" style={{ color: SLOT_COLOR[SLOTS[i]] }}>P{i + 1}</div>
              {row.map((v, j) => (
                <div
                  key={j}
                  className={cn("tabular flex aspect-[1.6] items-center justify-center rounded-md text-sm font-semibold", i === j && "ring-1 ring-inset ring-foreground/20")}
                  style={{ background: v === null ? "hsl(var(--muted))" : `hsl(var(--ring) / ${0.08 + v * 0.72})`, color: v !== null && v > 0.55 ? "white" : "hsl(var(--foreground))" }}
                  title={i === j ? "Model ran its own prompt" : undefined}
                >
                  {v === null ? "—" : pct(v)}
                </div>
              ))}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function SelfVsCross({ e }: { e: Evaluation }) {
  const { self, cross } = e.self_vs_cross;
  const rows: { label: string; s: string; c: string; better?: "s" | "c" | null }[] = [
    { label: e.has_golden_labels ? "Field accuracy" : "Verified fill rate", s: pct(self.primary_metric, 1), c: pct(cross.primary_metric, 1), better: cmp(self.primary_metric, cross.primary_metric, true) },
    { label: "Missing rate", s: pct(self.missing_rate, 1), c: pct(cross.missing_rate, 1), better: cmp(self.missing_rate, cross.missing_rate, false) },
    { label: "Avg latency", s: ms(self.avg_latency_ms), c: ms(cross.avg_latency_ms), better: cmp(self.avg_latency_ms, cross.avg_latency_ms, false) },
    { label: "Avg tokens", s: num(self.avg_total_tokens), c: num(cross.avg_total_tokens), better: cmp(self.avg_total_tokens, cross.avg_total_tokens, false) },
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Own prompt vs another model's prompt</CardTitle>
        <CardDescription>Do models extract better from prompts they wrote? {self.cells} self runs (diagonal) vs {cross.cells} cross runs.</CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <THead><TR className="hover:bg-transparent"><TH className="pl-0">Metric</TH><TH className="text-right">Own prompt</TH><TH className="pr-0 text-right">Other model's prompt</TH></TR></THead>
          <TBody>
            {rows.map((r) => (
              <TR key={r.label}>
                <TD className="pl-0 text-muted-foreground">{r.label}</TD>
                <TD className={cn("tabular text-right", r.better === "s" && "font-semibold")}>{r.s}</TD>
                <TD className={cn("tabular pr-0 text-right", r.better === "c" && "font-semibold")}>{r.c}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function cmp(a: number | null, b: number | null, higherBetter: boolean): "s" | "c" | null {
  if (a === null || b === null || a === b) return null;
  return (a > b) === higherBetter ? "s" : "c";
}

function LatencyChart({ e }: { e: Evaluation }) {
  const data = e.combinations.filter((c) => c.latency_ms !== null).map((c) => ({ name: c.cell, latency: Math.round((c.latency_ms ?? 0) / 100) / 10, slot: c.extraction_slot }));
  return (
    <Card>
      <CardHeader><CardTitle>Latency by combination</CardTitle><CardDescription>Seconds, including retries and all chunks. Coloured by extraction model.</CardDescription></CardHeader>
      <CardContent className="h-64">
        <ResponsiveContainer>
          <BarChart data={data} margin={{ left: -16, right: 8 }}>
            <CartesianGrid vertical={false} stroke="hsl(var(--border))" />
            <XAxis dataKey="name" tick={AXIS} tickLine={false} axisLine={false} />
            <YAxis tick={AXIS} tickLine={false} axisLine={false} unit="s" />
            <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "hsl(var(--muted))" }} formatter={(v) => [`${v} s`, "Latency"]} />
            <Bar dataKey="latency" radius={[4, 4, 0, 0]} maxBarSize={36}>
              {data.map((d) => <Cell key={d.name} fill={SLOT_COLOR[d.slot]} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

function TokenChart({ e }: { e: Evaluation }) {
  const data = e.combinations.filter((c) => c.total_tokens !== null).map((c) => ({ name: c.cell, prompt: c.prompt_tokens ?? 0, completion: c.completion_tokens ?? 0 }));
  return (
    <Card>
      <CardHeader><CardTitle>Token usage by combination</CardTitle><CardDescription>As reported by Groq for each run.</CardDescription></CardHeader>
      <CardContent className="h-64">
        <ResponsiveContainer>
          <BarChart data={data} margin={{ left: -4, right: 8 }}>
            <CartesianGrid vertical={false} stroke="hsl(var(--border))" />
            <XAxis dataKey="name" tick={AXIS} tickLine={false} axisLine={false} />
            <YAxis tick={AXIS} tickLine={false} axisLine={false} />
            <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "hsl(var(--muted))" }} />
            <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" iconSize={8} />
            <Bar dataKey="prompt" name="Input tokens" stackId="t" fill="hsl(var(--foreground) / 0.75)" maxBarSize={36} />
            <Bar dataKey="completion" name="Output tokens" stackId="t" fill="hsl(var(--ring))" radius={[4, 4, 0, 0]} maxBarSize={36} />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

function Leaderboard({ e }: { e: Evaluation }) {
  const g = e.has_golden_labels;
  return (
    <Card>
      <CardHeader><CardTitle>Leaderboard: all nine combinations</CardTitle><CardDescription>Sorted by {g ? "field accuracy" : "verified fill rate"}, then missing rate, then latency.</CardDescription></CardHeader>
      <CardContent className="px-0">
        <Table>
          <THead>
            <TR className="hover:bg-transparent">
              <TH className="pl-5">Rank</TH><TH>Combination</TH><TH>Status</TH>
              {g && <TH className="text-right">Field acc.</TH>}{g && <TH className="text-right">Exact match</TH>}{g && <TH className="text-right">Incorrect</TH>}
              <TH className="text-right">Verified fill</TH><TH className="text-right">Missing</TH><TH className="text-right">Unsupported</TH><TH className="text-right">Agreement</TH>
              <TH>JSON</TH><TH className="text-right">Latency</TH><TH className="pr-5 text-right">Tokens</TH>
            </TR>
          </THead>
          <TBody>
            {e.leaderboard.map((c) => (
              <TR key={c.execution_id}>
                <TD className="tabular pl-5 font-semibold">{c.rank}</TD>
                <TD>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{c.cell}</span>
                    {c.is_self_prompt && <Badge tone="outline">own prompt</Badge>}
                  </div>
                  <p className="text-xs text-muted-foreground">{shortModel(c.prompt_model)} → {shortModel(c.extraction_model)}</p>
                </TD>
                <TD><StatusPill status={c.status} /></TD>
                {g && <TD className="tabular text-right font-semibold">{pct(c.field_accuracy, 1)}</TD>}
                {g && <TD className="tabular text-right">{pct(c.exact_match_accuracy, 1)}</TD>}
                {g && <TD className="tabular text-right">{pct(c.incorrect_rate, 1)}</TD>}
                <TD className={cn("tabular text-right", !g && "font-semibold")}>{pct(c.supported_fill_rate, 1)}</TD>
                <TD className="tabular text-right">{pct(c.missing_rate, 1)}</TD>
                <TD className="tabular text-right">{pct(c.unsupported_rate, 1)}</TD>
                <TD className="tabular text-right text-muted-foreground">{pct(c.agreement_with_majority)}</TD>
                <TD>{c.status === "completed" ? (c.json_valid ? <span className="text-success">Valid</span> : <span className="text-danger">Invalid</span>) : "—"}</TD>
                <TD className="tabular text-right">{ms(c.latency_ms)}</TD>
                <TD className="tabular pr-5 text-right">{num(c.total_tokens)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </CardContent>
    </Card>
  );
}

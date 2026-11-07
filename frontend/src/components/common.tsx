import { AlertTriangle, Check, CircleDashed, Copy, Loader2, UploadCloud, XCircle, type LucideIcon } from "lucide-react";
import { useCallback, useRef, useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import type { CellStatus, FieldStatus, Slot } from "@/lib/types";
import { cn, shortModel } from "@/lib/utils";

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-2xl">
        <h1 className="text-[1.75rem] font-semibold leading-tight tracking-[-0.015em]">{title}</h1>
        {description && <p className="mt-1.5 text-[0.95rem] leading-relaxed text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function EmptyState({ icon: Icon, title, body, action }: { icon: LucideIcon; title: string; body: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed bg-card/50 px-6 py-16 text-center">
      <div className="mb-4 rounded-full bg-secondary p-3">
        <Icon className="h-5 w-5 text-muted-foreground" />
      </div>
      <h3 className="font-semibold">{title}</h3>
      <p className="mt-1 max-w-md text-sm text-muted-foreground">{body}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorBanner({ error, className }: { error: unknown; className?: string }) {
  if (!error) return null;
  const e = error as ApiError;
  const missing = (e.details as { missing?: string[] } | undefined)?.missing;
  return (
    <div role="alert" className={cn("flex gap-3 rounded-lg border border-danger/30 bg-danger/5 px-4 py-3 text-sm", className)}>
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-danger" />
      <div>
        <p className="font-medium text-danger">{e.message ?? String(error)}</p>
        {missing && missing.length > 0 && (
          <p className="mt-1 text-muted-foreground">
            Add {missing.join(", ")} to <code className="font-mono text-xs">.env</code> and restart the backend.
          </p>
        )}
      </div>
    </div>
  );
}

const SLOT_BG: Record<Slot, string> = { M1: "bg-m1", M2: "bg-m2", M3: "bg-m3" };
const SLOT_TEXT: Record<Slot, string> = { M1: "text-m1", M2: "text-m2", M3: "text-m3" };
export const slotBg = (s: Slot) => SLOT_BG[s];
export const slotText = (s: Slot) => SLOT_TEXT[s];

export function ModelChip({ slot, modelId, prefix, compact }: { slot: Slot; modelId?: string | null; prefix?: string; compact?: boolean }) {
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5" title={modelId ?? undefined}>
      <span className={cn("h-2 w-2 shrink-0 rounded-full", SLOT_BG[slot])} />
      <span className={cn("font-semibold", SLOT_TEXT[slot])}>{prefix ?? slot}</span>
      {!compact && <span className="truncate text-muted-foreground">{shortModel(modelId)}</span>}
    </span>
  );
}

const CELL_STATUS: Record<CellStatus, { label: string; tone: "neutral" | "success" | "warning" | "danger" | "info" | "outline"; icon: LucideIcon }> = {
  queued: { label: "Queued", tone: "outline", icon: CircleDashed },
  running: { label: "Running", tone: "info", icon: Loader2 },
  completed: { label: "Completed", tone: "success", icon: Check },
  failed: { label: "Failed", tone: "danger", icon: XCircle },
  interrupted: { label: "Interrupted", tone: "warning", icon: AlertTriangle },
  skipped: { label: "Skipped", tone: "neutral", icon: CircleDashed },
};

export function StatusPill({ status }: { status: CellStatus | string }) {
  const s = CELL_STATUS[status as CellStatus] ?? {
    label: status.replace(/_/g, " "),
    tone: status.includes("error") ? "warning" : status === "completed" ? "success" : "neutral",
    icon: CircleDashed,
  };
  const Icon = s.icon;
  return (
    <Badge tone={s.tone as never}>
      <Icon className={cn("h-3 w-3", status === "running" && "animate-spin")} />
      <span className="first-letter:uppercase">{s.label}</span>
    </Badge>
  );
}

export const FIELD_STATUS: Record<FieldStatus, { label: string; cls: string }> = {
  ok: { label: "Verified", cls: "text-success" },
  missing: { label: "Null", cls: "text-muted-foreground" },
  not_returned: { label: "Not returned", cls: "text-danger" },
  type_error: { label: "Type error", cls: "text-danger" },
  unsupported: { label: "Unsupported", cls: "text-warning" },
  page_invalid: { label: "Bad page", cls: "text-warning" },
};

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          setTimeout(() => setDone(false), 1500);
        } catch {
          /* clipboard blocked */
        }
      }}
    >
      {done ? <Check /> : <Copy />}
      {done ? "Copied" : label}
    </Button>
  );
}

export function Stat({ label, value, hint, className }: { label: string; value: ReactNode; hint?: ReactNode; className?: string }) {
  return (
    <div className={cn("min-w-0", className)}>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="tabular mt-0.5 truncate text-lg font-semibold tracking-[-0.01em]">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function Dropzone({ accept, hint, onFile, busy, label }: { accept: string; hint: string; onFile: (f: File) => void; busy?: boolean; label: string }) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const pick = useCallback((files: FileList | null) => files && files[0] && onFile(files[0]), [onFile]);
  return (
    <div
      role="button"
      tabIndex={0}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
      onClick={() => !busy && input.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (!busy) pick(e.dataTransfer.files);
      }}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors",
        over ? "border-ring bg-ring/5" : "border-border hover:border-muted-foreground/40 hover:bg-card",
        busy && "cursor-wait opacity-70",
      )}
    >
      {busy ? <Loader2 className="mb-3 h-6 w-6 animate-spin text-muted-foreground" /> : <UploadCloud className="mb-3 h-6 w-6 text-muted-foreground" />}
      <p className="text-sm font-medium">{busy ? "Uploading…" : label}</p>
      <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
      <input ref={input} type="file" accept={accept} className="hidden" onChange={(e) => pick(e.target.files)} />
    </div>
  );
}

export function CodeBlock({ children, className }: { children: string; className?: string }) {
  return (
    <pre className={cn("max-h-[480px] overflow-auto rounded-md border bg-muted/50 p-4 font-mono text-xs leading-relaxed whitespace-pre-wrap break-words scrollbar-thin", className)}>
      {children}
    </pre>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-4 w-4 animate-spin", className)} />;
}

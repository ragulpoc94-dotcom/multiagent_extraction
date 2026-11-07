import { ChevronDown } from "lucide-react";
import type { SelectHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function NativeSelect({ className, children, ...p }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className={cn("relative inline-flex", className)}>
      <select
        className="h-9 w-full appearance-none rounded-md border border-input bg-card pl-3 pr-8 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        {...p}
      >
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
    </div>
  );
}

import type { HTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export const Table = ({ className, ...p }: HTMLAttributes<HTMLTableElement>) => (
  <div className="w-full overflow-auto scrollbar-thin">
    <table className={cn("w-full caption-bottom text-sm", className)} {...p} />
  </div>
);
export const THead = ({ className, ...p }: HTMLAttributes<HTMLTableSectionElement>) => (
  <thead className={cn("[&_tr]:border-b", className)} {...p} />
);
export const TBody = ({ className, ...p }: HTMLAttributes<HTMLTableSectionElement>) => (
  <tbody className={cn("[&_tr:last-child]:border-0", className)} {...p} />
);
export const TR = ({ className, ...p }: HTMLAttributes<HTMLTableRowElement>) => (
  <tr className={cn("border-b transition-colors hover:bg-muted/40", className)} {...p} />
);
export const TH = ({ className, ...p }: ThHTMLAttributes<HTMLTableCellElement>) => (
  <th className={cn("h-9 px-3 text-left align-middle text-xs font-medium text-muted-foreground whitespace-nowrap", className)} {...p} />
);
export const TD = ({ className, ...p }: TdHTMLAttributes<HTMLTableCellElement>) => (
  <td className={cn("px-3 py-2.5 align-middle", className)} {...p} />
);

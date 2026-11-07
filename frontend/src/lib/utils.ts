import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const pct = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined ? "—" : `${(v * 100).toFixed(digits)}%`;

export const ms = (v: number | null | undefined) => {
  if (v === null || v === undefined) return "—";
  return v >= 1000 ? `${(v / 1000).toFixed(v >= 10000 ? 0 : 1)} s` : `${Math.round(v)} ms`;
};

export const num = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : new Intl.NumberFormat("en-US").format(Math.round(v));

export const bytes = (n: number) =>
  n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1048576).toFixed(1)} MB`;

export const when = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
};

export const shortModel = (id: string | null | undefined) => {
  if (!id) return "not configured";
  const tail = id.split("/").pop() ?? id;
  return tail.length > 28 ? `${tail.slice(0, 26)}…` : tail;
};

export const display = (v: unknown): string => {
  if (v === null || v === undefined) return "";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
};

/** Loose normalisation used only to highlight agreement in the UI (alphanumeric, lower-case). */
export const looseKey = (v: unknown) =>
  v === null || v === undefined ? null : String(typeof v === "object" ? JSON.stringify(v) : v).toLowerCase().replace(/[^0-9a-z]+/g, "");

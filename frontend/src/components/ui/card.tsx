import { forwardRef, type HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export const Card = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(({ className, ...p }, ref) => (
  <div ref={ref} className={cn("rounded-lg border bg-card text-card-foreground", className)} {...p} />
));
Card.displayName = "Card";

export const CardHeader = ({ className, ...p }: HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("flex flex-col gap-1 px-5 pt-5 pb-3", className)} {...p} />
);
export const CardTitle = ({ className, ...p }: HTMLAttributes<HTMLHeadingElement>) => (
  <h3 className={cn("text-[0.95rem] font-semibold leading-tight tracking-[-0.005em]", className)} {...p} />
);
export const CardDescription = ({ className, ...p }: HTMLAttributes<HTMLParagraphElement>) => (
  <p className={cn("text-sm text-muted-foreground", className)} {...p} />
);
export const CardContent = ({ className, ...p }: HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("px-5 pb-5", className)} {...p} />
);

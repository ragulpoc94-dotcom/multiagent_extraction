import * as TabsPrimitive from "@radix-ui/react-tabs";
import { forwardRef, type ComponentPropsWithoutRef, type ElementRef } from "react";
import { cn } from "@/lib/utils";

export const Tabs = TabsPrimitive.Root;

export const TabsList = forwardRef<ElementRef<typeof TabsPrimitive.List>, ComponentPropsWithoutRef<typeof TabsPrimitive.List>>(
  ({ className, ...p }, ref) => (
    <TabsPrimitive.List ref={ref} className={cn("inline-flex items-center gap-1 border-b w-full", className)} {...p} />
  ),
);
TabsList.displayName = "TabsList";

export const TabsTrigger = forwardRef<ElementRef<typeof TabsPrimitive.Trigger>, ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>>(
  ({ className, ...p }, ref) => (
    <TabsPrimitive.Trigger
      ref={ref}
      className={cn(
        "-mb-px border-b-2 border-transparent px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground data-[state=active]:border-foreground data-[state=active]:text-foreground data-[state=active]:font-medium",
        className,
      )}
      {...p}
    />
  ),
);
TabsTrigger.displayName = "TabsTrigger";

export const TabsContent = forwardRef<ElementRef<typeof TabsPrimitive.Content>, ComponentPropsWithoutRef<typeof TabsPrimitive.Content>>(
  ({ className, ...p }, ref) => <TabsPrimitive.Content ref={ref} className={cn("pt-4 focus-visible:ring-0", className)} {...p} />,
);
TabsContent.displayName = "TabsContent";

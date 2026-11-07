import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { forwardRef, type ComponentPropsWithoutRef, type ElementRef, type HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;

export const DialogContent = forwardRef<ElementRef<typeof DialogPrimitive.Content>, ComponentPropsWithoutRef<typeof DialogPrimitive.Content>>(
  ({ className, children, ...p }, ref) => (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-[hsl(222_51%_8%/0.45)] backdrop-blur-[2px] data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0" />
      <DialogPrimitive.Content
        ref={ref}
        className={cn(
          "fixed right-0 top-0 z-50 flex h-full w-full max-w-3xl flex-col border-l bg-background shadow-2xl data-[state=open]:animate-in data-[state=open]:slide-in-from-right-8 data-[state=closed]:animate-out data-[state=closed]:fade-out-0",
          className,
        )}
        {...p}
      >
        {children}
        <DialogPrimitive.Close className="absolute right-4 top-4 rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground">
          <X className="h-4 w-4" />
          <span className="sr-only">Close</span>
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  ),
);
DialogContent.displayName = "DialogContent";

export const DialogHeader = ({ className, ...p }: HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("border-b px-6 py-5 pr-14", className)} {...p} />
);
export const DialogTitle = forwardRef<ElementRef<typeof DialogPrimitive.Title>, ComponentPropsWithoutRef<typeof DialogPrimitive.Title>>(
  ({ className, ...p }, ref) => <DialogPrimitive.Title ref={ref} className={cn("text-lg font-semibold", className)} {...p} />,
);
DialogTitle.displayName = "DialogTitle";
export const DialogDescription = forwardRef<ElementRef<typeof DialogPrimitive.Description>, ComponentPropsWithoutRef<typeof DialogPrimitive.Description>>(
  ({ className, ...p }, ref) => <DialogPrimitive.Description ref={ref} className={cn("text-sm text-muted-foreground", className)} {...p} />,
);
DialogDescription.displayName = "DialogDescription";

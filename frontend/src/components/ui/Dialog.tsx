"use client";

import * as RadixDialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "./cn";

/** Centred modal (short forms, confirmations) or right-hand sheet (review
 * panels with a lot of content). Both trap focus, close on Esc and restore
 * focus to the trigger — courtesy of Radix. */
export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  variant = "modal",
  size = "md",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  variant?: "modal" | "sheet";
  size?: "md" | "lg";
}) {
  const sheet = variant === "sheet";
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="overlay-in fixed inset-0 z-40 bg-ink/30" />
        <RadixDialog.Content
          aria-describedby={undefined}
          className={cn(
            "fixed z-50 flex flex-col bg-surface shadow-lg focus-visible:outline-none",
            sheet
              ? "inset-y-0 right-0 w-full max-w-2xl border-l border-line"
              : cn(
                  "left-1/2 top-[12%] max-h-[76vh] w-[calc(100vw-2rem)] -translate-x-1/2 rounded-xl border border-line",
                  size === "lg" ? "max-w-2xl" : "max-w-lg",
                ),
            "popover-in",
          )}
        >
          <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
            <div className="min-w-0">
              <RadixDialog.Title className="text-[15px] font-semibold text-ink">
                {title}
              </RadixDialog.Title>
              {description && (
                <RadixDialog.Description className="mt-1 text-[13px] text-muted">
                  {description}
                </RadixDialog.Description>
              )}
            </div>
            <RadixDialog.Close
              aria-label="Close"
              className="-mr-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-hover hover:text-ink"
            >
              <X className="h-4 w-4" aria-hidden />
            </RadixDialog.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
          {footer && (
            <div className="flex flex-wrap items-center justify-end gap-2 border-t border-line bg-canvas px-5 py-3">
              {footer}
            </div>
          )}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}

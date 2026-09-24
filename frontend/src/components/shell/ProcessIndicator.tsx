"use client";

import * as Popover from "@radix-ui/react-popover";
import { Loader2 } from "lucide-react";
import { useProcesses } from "./Processes";

/** Shows only while something is running in the background, so the user always
 * knows work is in flight even after navigating away from where it started. */
export default function ProcessIndicator() {
  const { processes } = useProcesses();
  if (processes.length === 0) return null;

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          type="button"
          className="inline-flex h-8 items-center gap-2 rounded-md border border-line bg-surface px-2.5 text-[13px] font-medium text-ink hover:bg-hover"
        >
          <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" aria-hidden />
          {processes.length === 1 ? "1 process running" : `${processes.length} processes running`}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={6}
          className="popover-in z-50 w-72 rounded-lg border border-line bg-surface p-3 shadow-md"
        >
          <p className="text-xs font-medium text-muted">In progress</p>
          <ul className="mt-2 space-y-2">
            {processes.map((p) => (
              <li key={p.id} className="flex items-center gap-2 text-[13px] text-ink">
                <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-accent" aria-hidden />
                <span className="truncate">{p.label}</span>
              </li>
            ))}
          </ul>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

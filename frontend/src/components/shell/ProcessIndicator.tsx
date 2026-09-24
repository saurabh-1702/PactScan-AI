"use client";

import * as Popover from "@radix-ui/react-popover";
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { getActiveJobs, type JobProgress } from "@/lib/api";
import { useProcesses } from "./Processes";

const POLL_MS = 2500;

/** Shows only while something is running, so the user always knows work is in
 * flight even after navigating away from where it started. It combines the
 * server's real jobs (uploads, with their current stage) and short client-side
 * operations that have no server-side stages (e.g. drafting a fix). */
export default function ProcessIndicator() {
  const { processes } = useProcesses();
  const [jobs, setJobs] = useState<JobProgress[]>([]);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function poll() {
      try {
        const active = await getActiveJobs();
        if (!cancelled) setJobs(active);
      } catch {
        /* transient — retry on the next tick */
      }
      if (!cancelled) timer = setTimeout(poll, POLL_MS);
    }
    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  const total = jobs.length + processes.length;
  if (total === 0) return null;

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          type="button"
          className="inline-flex h-8 items-center gap-2 whitespace-nowrap rounded-md border border-line bg-surface px-2.5 text-[13px] font-medium text-ink hover:bg-hover"
        >
          <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" aria-hidden />
          {total === 1 ? "1 process running" : `${total} processes running`}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={6}
          className="popover-in z-50 w-80 max-w-[calc(100vw-2rem)] rounded-lg border border-line bg-surface p-3 shadow-md"
        >
          <p className="text-xs font-medium text-muted">In progress</p>
          <ul className="mt-2 space-y-3">
            {jobs.map((j) => {
              const current = j.stages.find((s) => s.status === "active");
              return (
                <li key={j.job_id} className="text-[13px]">
                  <p className="truncate font-medium text-ink">{j.label}</p>
                  {current && <p className="mt-0.5 text-xs text-muted">{current.label}…</p>}
                </li>
              );
            })}
            {processes.map((p) => (
              <li key={p.id} className="text-[13px]">
                <p className="truncate font-medium text-ink">{p.label}</p>
              </li>
            ))}
          </ul>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getJobProgress, type JobProgress } from "@/lib/api";

export interface LoadState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  /** Re-run the loader, keeping the current data on screen while it does. */
  reload: () => void;
}

/** Load something once (and again on `reload()` or when `key` changes). Keeps
 * stale data visible during a reload so lists never flash empty. */
export function useLoad<T>(loader: () => Promise<T>, key: string = ""): LoadState<T> {
  const [state, setState] = useState<{ data: T | null; error: string | null; loading: boolean }>({
    data: null,
    error: null,
    loading: true,
  });
  const [tick, setTick] = useState(0);
  const loaderRef = useRef(loader);
  useEffect(() => {
    loaderRef.current = loader;
  });

  useEffect(() => {
    let cancelled = false;
    loaderRef
      .current()
      .then((data) => {
        if (!cancelled) setState({ data, error: null, loading: false });
      })
      .catch((err) => {
        if (!cancelled)
          setState((prev) => ({
            data: prev.data,
            error: err instanceof Error ? err.message : "Something went wrong",
            loading: false,
          }));
      });
    return () => {
      cancelled = true;
    };
  }, [tick, key]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}

/** Polls the server's real stage-by-stage progress for a job while `jobId` is
 * set, and stops once the job is done or failed. */
export function useJobProgress(jobId: string | null, intervalMs = 700): JobProgress | null {
  const [progress, setProgress] = useState<JobProgress | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function tick() {
      try {
        const p = await getJobProgress(jobId!);
        if (cancelled) return;
        if (p) setProgress(p);
        if (p && p.state !== "running") return;
      } catch {
        /* a missed poll is harmless — try again */
      }
      if (!cancelled) timer = setTimeout(tick, intervalMs);
    }
    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [jobId, intervalMs]);

  // Progress belongs to one job: never show a previous job's stages for a new id.
  return jobId && progress?.job_id === jobId ? progress : null;
}

/** Debounces a fast-changing value (e.g. a search box). */
export function useDebounced<T>(value: T, ms = 200): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

export interface ProcessInfo {
  id: number;
  label: string;
  startedAt: number;
}

interface ProcessApi {
  processes: ProcessInfo[];
  /** Register long-running work for the global indicator; it is removed when
   * the promise settles. Returns the same promise, so it can wrap any call. */
  track: <T>(label: string, work: Promise<T>) => Promise<T>;
}

const ProcessContext = createContext<ProcessApi | null>(null);

export function ProcessProvider({ children }: { children: React.ReactNode }) {
  const [processes, setProcesses] = useState<ProcessInfo[]>([]);
  const nextId = useRef(1);

  const track = useCallback(<T,>(label: string, work: Promise<T>): Promise<T> => {
    const id = nextId.current++;
    setProcesses((p) => [...p, { id, label, startedAt: Date.now() }]);
    const done = () => setProcesses((p) => p.filter((x) => x.id !== id));
    work.then(done, done);
    return work;
  }, []);

  const value = useMemo(() => ({ processes, track }), [processes, track]);
  return <ProcessContext.Provider value={value}>{children}</ProcessContext.Provider>;
}

export function useProcesses(): ProcessApi {
  const ctx = useContext(ProcessContext);
  if (!ctx) throw new Error("useProcesses must be used inside ProcessProvider");
  return ctx;
}

import type { Severity } from "@/lib/api";
import { cn } from "./cn";

const STYLES: Record<Severity, { dot: string; text: string; label: string }> = {
  HIGH: { dot: "bg-danger", text: "text-danger-ink", label: "High" },
  MEDIUM: { dot: "bg-warn", text: "text-warn-ink", label: "Medium" },
  LOW: { dot: "bg-accent", text: "text-accent-strong", label: "Low" },
};

export const SEVERITY_ORDER: Record<Severity, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 };

/** A dot plus a word — the word carries the meaning, the colour reinforces it. */
export function SeverityLabel({ severity, className }: { severity: Severity; className?: string }) {
  const s = STYLES[severity];
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium", s.text, className)}>
      <span className={cn("h-2 w-2 rounded-full", s.dot)} aria-hidden />
      {s.label}
    </span>
  );
}

export const SEVERITY_DOT: Record<Severity, string> = {
  HIGH: "bg-danger",
  MEDIUM: "bg-warn",
  LOW: "bg-accent",
};

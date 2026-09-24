import { Check, Circle, Loader2, X } from "lucide-react";
import type { JobStage } from "@/lib/api";
import { cn } from "./cn";

/** The pipeline's real stages, exactly as the server reports them — never a
 * percentage, because there is no honest way to compute one. */
export function StageProgress({ stages, error }: { stages: JobStage[]; error?: string | null }) {
  return (
    <div>
      <ol className="space-y-2.5">
        {stages.map((s) => (
          <li key={s.key} className="flex items-center gap-3 text-[13px]">
            <span
              className={cn(
                "flex h-5 w-5 shrink-0 items-center justify-center rounded-full",
                s.status === "done" && "bg-success-soft text-success-ink",
                s.status === "active" && "bg-accent-soft text-accent",
                s.status === "failed" && "bg-danger-soft text-danger-ink",
                s.status === "pending" && "text-line-strong",
              )}
            >
              {s.status === "done" && <Check className="h-3 w-3" aria-hidden />}
              {s.status === "active" && <Loader2 className="h-3 w-3 animate-spin" aria-hidden />}
              {s.status === "failed" && <X className="h-3 w-3" aria-hidden />}
              {s.status === "pending" && <Circle className="h-2.5 w-2.5" aria-hidden />}
            </span>
            <span
              className={cn(
                s.status === "pending" && "text-muted",
                s.status === "active" && "font-medium text-ink",
                s.status === "done" && "text-muted",
                s.status === "failed" && "font-medium text-danger-ink",
              )}
            >
              {s.label}
            </span>
          </li>
        ))}
      </ol>
      {error && <p className="mt-3 text-[13px] text-danger-ink">{error}</p>}
    </div>
  );
}

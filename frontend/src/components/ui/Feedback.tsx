import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import { cn } from "./cn";

type Tone = "info" | "success" | "warn" | "danger";

const TONES: Record<Tone, { box: string; icon: React.ElementType }> = {
  info: { box: "border-accent/25 bg-accent-soft text-accent-strong", icon: Info },
  success: { box: "border-success/25 bg-success-soft text-success-ink", icon: CheckCircle2 },
  warn: { box: "border-warn/30 bg-warn-soft text-warn-ink", icon: AlertTriangle },
  danger: { box: "border-danger/30 bg-danger-soft text-danger-ink", icon: XCircle },
};

/** Inline message. Danger is announced assertively; the rest politely. */
export function Alert({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: Tone;
  title?: string;
  children?: React.ReactNode;
  className?: string;
}) {
  const { box, icon: Icon } = TONES[tone];
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn("flex gap-2.5 rounded-md border px-3 py-2.5 text-[13px]", box, className)}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="min-w-0">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={cn(title && "mt-0.5")}>{children}</div>}
      </div>
    </div>
  );
}

const BADGE: Record<Tone | "neutral", string> = {
  neutral: "bg-sunken text-muted",
  info: "bg-accent-soft text-accent-strong",
  success: "bg-success-soft text-success-ink",
  warn: "bg-warn-soft text-warn-ink",
  danger: "bg-danger-soft text-danger-ink",
};

export function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: Tone | "neutral";
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium leading-4",
        BADGE[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton", className)} aria-hidden />;
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cn(
        "inline-block h-4 w-4 animate-spin rounded-full border-2 border-line-strong border-t-accent",
        className,
      )}
    />
  );
}

/** A calm "nothing here" panel that says what the space is for and what to do. */
export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon: React.ElementType;
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center rounded-lg border border-dashed border-line-strong px-6 py-12 text-center">
      <span className="flex h-10 w-10 items-center justify-center rounded-full bg-sunken text-faint">
        <Icon className="h-5 w-5" aria-hidden />
      </span>
      <p className="mt-3 text-sm font-semibold text-ink">{title}</p>
      {children && <p className="mt-1 max-w-sm text-[13px] text-muted">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

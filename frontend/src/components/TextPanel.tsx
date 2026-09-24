import { cn } from "@/components/ui/cn";

/** A labelled block of contract text — the building block for "original /
 * AI draft / your edit / reviewer's edit" comparisons. */
export default function TextPanel({
  title,
  note,
  tone = "neutral",
  children,
}: {
  title: string;
  note?: string;
  tone?: "neutral" | "accent" | "success" | "danger";
  children: React.ReactNode;
}) {
  const bar = {
    neutral: "border-l-line-strong",
    accent: "border-l-accent",
    success: "border-l-success",
    danger: "border-l-danger",
  }[tone];
  return (
    <div className={cn("rounded-md border border-line border-l-[3px] bg-surface px-3.5 py-3", bar)}>
      <div className="flex flex-wrap items-baseline gap-x-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">{title}</p>
        {note && <p className="text-xs text-muted">{note}</p>}
      </div>
      <div className="mt-1.5 text-[13px] leading-relaxed text-ink">{children}</div>
    </div>
  );
}

export function PlainText({ children }: { children: string }) {
  return <p className="whitespace-pre-wrap">{children}</p>;
}

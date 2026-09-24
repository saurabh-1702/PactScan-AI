import { cn } from "./cn";

/** Standard page frame: consistent width, padding and entrance. */
export function Page({
  children,
  width = "default",
  className,
}: {
  children: React.ReactNode;
  width?: "default" | "narrow" | "wide";
  className?: string;
}) {
  const max = width === "narrow" ? "max-w-3xl" : width === "wide" ? "max-w-7xl" : "max-w-6xl";
  return (
    <div className={cn("page-in mx-auto w-full px-4 py-6 sm:px-8 sm:py-8", max, className)}>
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-[13px] text-muted">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Card({
  children,
  className,
  padded = true,
}: {
  children: React.ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <section
      className={cn("rounded-lg border border-line bg-surface shadow-sm", padded && "p-5", className)}
    >
      {children}
    </section>
  );
}

export function SectionTitle({
  children,
  action,
}: {
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="text-sm font-semibold text-ink">{children}</h2>
      {action}
    </div>
  );
}

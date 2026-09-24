import { cn } from "./cn";

/** Dense, calm data table. Rows are hoverable; pass `onClick` to make one
 * openable (it also becomes keyboard-focusable). */
export function Table({
  children,
  className,
  caption,
}: {
  children: React.ReactNode;
  className?: string;
  caption?: string;
}) {
  return (
    <div className={cn("overflow-x-auto rounded-lg border border-line bg-surface shadow-sm", className)}>
      <table className="w-full min-w-[36rem] border-collapse text-left text-[13px]">
        {caption && <caption className="sr-only">{caption}</caption>}
        {children}
      </table>
    </div>
  );
}

export function THead({ children }: { children: React.ReactNode }) {
  return <thead className="border-b border-line bg-canvas">{children}</thead>;
}

export function Th({
  children,
  className,
  align,
}: {
  children?: React.ReactNode;
  className?: string;
  align?: "right";
}) {
  return (
    <th
      scope="col"
      className={cn(
        "px-4 py-2.5 text-xs font-medium uppercase tracking-wide text-muted",
        align === "right" && "text-right",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function Tr({
  children,
  onClick,
  selected,
  className,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  selected?: boolean;
  className?: string;
}) {
  const interactive = !!onClick;
  return (
    <tr
      onClick={onClick}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={
        interactive
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick?.();
              }
            }
          : undefined
      }
      className={cn(
        "border-b border-line last:border-0 transition-colors duration-100",
        interactive && "cursor-pointer hover:bg-hover",
        selected && "bg-accent-soft/60",
        className,
      )}
    >
      {children}
    </tr>
  );
}

export function Td({
  children,
  className,
  align,
  muted,
}: {
  children?: React.ReactNode;
  className?: string;
  align?: "right";
  muted?: boolean;
}) {
  return (
    <td
      className={cn(
        "px-4 py-3 align-middle",
        muted ? "text-muted" : "text-ink",
        align === "right" && "text-right",
        className,
      )}
    >
      {children}
    </td>
  );
}

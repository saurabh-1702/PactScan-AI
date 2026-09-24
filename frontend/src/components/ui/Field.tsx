import { forwardRef, useId } from "react";
import { cn } from "./cn";

const CONTROL =
  "w-full rounded-md border border-line-strong bg-surface px-3 text-sm text-ink placeholder:text-faint " +
  "transition-colors duration-150 hover:border-faint focus:border-accent focus:outline-none " +
  "focus:ring-2 focus:ring-accent/20 disabled:cursor-not-allowed disabled:bg-sunken disabled:opacity-60";

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...rest }, ref) {
    return <input ref={ref} className={cn(CONTROL, "h-9", className)} {...rest} />;
  },
);

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(function Textarea({ className, ...rest }, ref) {
  return <textarea ref={ref} className={cn(CONTROL, "min-h-20 py-2 leading-relaxed", className)} {...rest} />;
});

export const Select = forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, ...rest }, ref) {
    return <select ref={ref} className={cn(CONTROL, "h-9 pr-8", className)} {...rest} />;
  },
);

/** Label + control + optional hint/error, wired together for screen readers. */
export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string | null;
  children: (props: {
    id: string;
    "aria-describedby"?: string;
    "aria-invalid"?: boolean;
  }) => React.ReactNode;
}) {
  const id = useId();
  const noteId = `${id}-note`;
  const note = error ?? hint;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[13px] font-medium text-ink">
        {label}
      </label>
      {children({
        id,
        "aria-describedby": note ? noteId : undefined,
        "aria-invalid": error ? true : undefined,
      })}
      {note && (
        <p id={noteId} className={cn("text-xs", error ? "text-danger-ink" : "text-muted")}>
          {note}
        </p>
      )}
    </div>
  );
}

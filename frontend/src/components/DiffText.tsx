import { wordDiff } from "@/lib/diff";

/** `after`, with words that were added highlighted and words that were removed
 * struck through, relative to `before`. Colour is never the only signal:
 * additions are underlined and removals struck through. */
export default function DiffText({ before, after }: { before: string; after: string }) {
  const parts = wordDiff(before, after);
  return (
    <p className="whitespace-pre-wrap text-[13px] leading-relaxed">
      {parts.map((p, i) =>
        p.op === "same" ? (
          <span key={i}>{p.text}</span>
        ) : p.op === "added" ? (
          <ins
            key={i}
            className="rounded-sm bg-success-soft px-0.5 text-success-ink underline decoration-success/50 underline-offset-2"
          >
            {p.text}
          </ins>
        ) : (
          <del key={i} className="rounded-sm bg-danger-soft px-0.5 text-danger-ink">
            {p.text}
          </del>
        ),
      )}
    </p>
  );
}

export function DiffLegend() {
  return (
    <p className="mt-2 text-xs text-muted">
      <ins className="rounded-sm bg-success-soft px-1 text-success-ink no-underline">Added</ins>{" "}
      <del className="rounded-sm bg-danger-soft px-1 text-danger-ink">removed</del> compared with the
      previous text.
    </p>
  );
}

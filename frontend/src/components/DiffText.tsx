import { wordDiff } from "@/lib/diff";

/** `after`, with words the reviewer added highlighted green and words they
 * removed struck through red, relative to `before`. */
export default function DiffText({ before, after }: { before: string; after: string }) {
  const parts = wordDiff(before, after);
  return (
    <p className="whitespace-pre-wrap text-sm">
      {parts.map((p, i) =>
        p.op === "same" ? (
          <span key={i}>{p.text}</span>
        ) : p.op === "added" ? (
          <mark key={i} className="rounded bg-emerald-200 px-0.5 text-emerald-950">
            {p.text}
          </mark>
        ) : (
          <del key={i} className="rounded bg-red-100 px-0.5 text-red-800">
            {p.text}
          </del>
        ),
      )}
    </p>
  );
}

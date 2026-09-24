"use client";

import Link from "next/link";
import { useState } from "react";
import { submitDraft, type DraftInfo } from "@/lib/api";

/** Shown wherever a fresh AI draft appears (Suggest fix on /detect, an edit
 * instruction in Ask, a draft in My Drafts). The requester previews the AI's
 * text, can edit it to match their company's requirements, and only then
 * submits it — as the AI draft untouched, or as their own edited version.
 * Nothing reaches a reviewer before this button. */
export default function DraftSubmitPanel({
  suggestionId,
  aiDraft,
  rationale,
  onSubmitted,
}: {
  suggestionId: string;
  aiDraft: string;
  rationale?: string;
  onSubmitted?: (d: DraftInfo) => void;
}) {
  const [text, setText] = useState(aiDraft);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState<DraftInfo | null>(null);

  const edited = text.trim() !== aiDraft.trim();

  async function onSubmit() {
    setBusy(true);
    setError(null);
    try {
      const d = await submitDraft(suggestionId, edited ? text : undefined);
      setSubmitted(d);
      onSubmitted?.(d);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit");
    } finally {
      setBusy(false);
    }
  }

  if (submitted) {
    return (
      <div className="mt-3 rounded border border-emerald-300 bg-emerald-50 p-3 text-xs text-emerald-900">
        <p className="font-semibold">
          Submitted for review{submitted.requester_edited_text ? " (your edited version)" : " (AI draft)"}.
        </p>
        <p className="mt-1">
          A reviewer will decide it and you&apos;ll get a notification.{" "}
          <Link href="/my-drafts" className="font-semibold underline">
            Track it in My Drafts →
          </Link>
        </p>
      </div>
    );
  }

  return (
    <div className="mt-3 rounded border border-neutral-300 bg-white/80 p-3 text-neutral-800">
      <p className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
        AI draft — not submitted yet. Edit it if you need to, then submit.
      </p>
      <textarea
        className="mt-2 w-full rounded border border-neutral-300 p-2 text-sm"
        rows={6}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      {rationale && (
        <p className="mt-1 text-xs text-neutral-600">
          <span className="font-semibold">Why: </span>
          {rationale}
        </p>
      )}
      {error && (
        <p className="mt-2 rounded border border-red-400 bg-red-50 p-2 text-xs text-red-800">
          {error}
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={busy || !text.trim()}
          onClick={onSubmit}
          className="rounded bg-neutral-900 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
        >
          {busy ? "Submitting…" : edited ? "Submit my edited version" : "Submit AI draft"}
        </button>
        {edited && (
          <button
            type="button"
            disabled={busy}
            onClick={() => setText(aiDraft)}
            className="rounded border border-neutral-400 px-3 py-1.5 text-xs font-semibold"
          >
            Reset to AI draft
          </button>
        )}
        <span className="text-[11px] text-neutral-500">
          {edited ? "You've changed the AI's text." : "Unchanged — submits the AI's text as-is."}
        </span>
      </div>
    </div>
  );
}

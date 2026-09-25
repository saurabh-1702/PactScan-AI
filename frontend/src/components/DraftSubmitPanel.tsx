"use client";

import Link from "next/link";
import { CheckCircle2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Feedback";
import { Textarea } from "@/components/ui/Field";
import { deleteDraft, submitDraft, type DraftInfo } from "@/lib/api";

/** Shown wherever a fresh AI draft appears (Suggest fix, an edit instruction in
 * Ask, a draft in My Drafts). The requester previews the AI's text, can edit it
 * to match their company's requirements, and only then submits it — as the AI
 * draft untouched, or as their own edited version. Nothing reaches a reviewer
 * before this button. */
export default function DraftSubmitPanel({
  suggestionId,
  aiDraft,
  rationale,
  onSubmitted,
  onDiscarded,
}: {
  suggestionId: string;
  aiDraft: string;
  rationale?: string;
  onSubmitted?: (d: DraftInfo) => void;
  /** Called after the user throws the draft away. */
  onDiscarded?: () => void;
}) {
  const [text, setText] = useState(aiDraft);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState<DraftInfo | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);

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

  async function onDiscard() {
    setBusy(true);
    setError(null);
    try {
      await deleteDraft(suggestionId);
      onDiscarded?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not discard the draft");
      setConfirmDiscard(false);
    } finally {
      setBusy(false);
    }
  }

  if (submitted) {
    return (
      <div className="mt-3 flex gap-2.5 rounded-md border border-success/25 bg-success-soft px-3.5 py-3 text-[13px] text-success-ink">
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <div>
          <p className="font-semibold">
            Submitted for review{submitted.requester_edited_text ? " — your edited version" : " — the AI draft"}.
          </p>
          <p className="mt-0.5">
            A reviewer will decide it and you&apos;ll be notified.{" "}
            <Link href="/my-drafts" className="font-medium underline underline-offset-2">
              Track it in My Drafts
            </Link>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="mt-3 rounded-md border border-line bg-surface p-3.5">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">
        AI draft — not submitted yet
      </p>
      <p className="mt-0.5 text-xs text-muted">
        Edit it if it needs to match your company&apos;s requirements, then submit it for review.
      </p>
      <Textarea
        className="mt-2.5 text-[13px]"
        rows={6}
        value={text}
        aria-label="Draft text"
        onChange={(e) => setText(e.target.value)}
      />
      {rationale && (
        <p className="mt-2 text-xs text-muted">
          <span className="font-semibold text-ink">Why this wording: </span>
          {rationale}
        </p>
      )}
      {error && (
        <Alert tone="danger" className="mt-3">
          {error}
        </Alert>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button variant="primary" size="sm" loading={busy} disabled={!text.trim()} onClick={onSubmit}>
          {edited ? "Submit my edited version" : "Submit AI draft"}
        </Button>
        {edited && (
          <Button size="sm" disabled={busy} onClick={() => setText(aiDraft)}>
            Reset to AI draft
          </Button>
        )}
        <span className="text-xs text-muted">
          {edited ? "You've changed the AI's text." : "Unchanged — submits the AI's text as-is."}
        </span>
        {onDiscarded && (
          <span className="ml-auto">
            {confirmDiscard ? (
              <span className="inline-flex items-center gap-2 text-xs text-muted">
                Discard this draft?
                <Button size="sm" variant="danger" loading={busy} onClick={onDiscard}>
                  Yes, discard
                </Button>
                <Button size="sm" variant="ghost" disabled={busy} onClick={() => setConfirmDiscard(false)}>
                  Keep
                </Button>
              </span>
            ) : (
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => setConfirmDiscard(true)}>
                Discard draft
              </Button>
            )}
          </span>
        )}
      </div>
    </div>
  );
}

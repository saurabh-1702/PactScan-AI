"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import DiffText from "@/components/DiffText";
import DraftSubmitPanel from "@/components/DraftSubmitPanel";
import { downloadDocumentVersion, getMyDrafts, type DraftInfo, type DraftStatus } from "@/lib/api";

const STATUS_STYLES: Record<DraftStatus, string> = {
  draft: "bg-neutral-200 text-neutral-700",
  pending: "bg-amber-100 text-amber-800",
  approved: "bg-emerald-100 text-emerald-800",
  rejected: "bg-red-100 text-red-800",
};

const STATUS_LABELS: Record<DraftStatus, string> = {
  draft: "Draft — not submitted",
  pending: "Waiting for a reviewer",
  approved: "Approved",
  rejected: "Rejected",
};

function TextBox({ title, tone, children }: { title: string; tone: string; children: React.ReactNode }) {
  return (
    <div className={`rounded border p-2 ${tone}`}>
      <p className="text-xs font-semibold uppercase opacity-70">{title}</p>
      <div className="mt-1">{children}</div>
    </div>
  );
}

export default function MyDraftsPage() {
  const [drafts, setDrafts] = useState<DraftInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setDrafts(await getMyDrafts());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load your drafts");
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">My Drafts</h1>
      <p className="mt-1 text-sm text-neutral-500">
        Every fix you&apos;ve drafted — the AI&apos;s version, your own edit if you made one, and
        what a reviewer changed before approving it.
      </p>

      {error && (
        <p className="mt-4 rounded border border-red-400 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      )}

      {drafts === null ? (
        <p className="mt-6 text-sm text-neutral-500">Loading…</p>
      ) : drafts.length === 0 ? (
        <p className="mt-6 rounded border border-neutral-300 bg-neutral-50 p-3 text-sm text-neutral-600">
          You haven&apos;t drafted anything yet. Use &quot;Suggest fix&quot; on a finding in Detect,
          or ask for an edit in Ask.
        </p>
      ) : (
        <ul className="mt-6 space-y-5">
          {drafts.map((d) => {
            const submitted = d.requester_edited_text ?? d.ai_draft_text;
            const reviewerChanged =
              d.reviewer_edited_text !== null && d.reviewer_edited_text.trim() !== submitted.trim();
            return (
              <li key={d.suggestion_id} className="rounded border border-neutral-300 p-4 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`rounded px-1.5 py-0.5 text-xs font-semibold uppercase ${STATUS_STYLES[d.status]}`}
                  >
                    {STATUS_LABELS[d.status]}
                  </span>
                  <Link
                    href={`/contracts/${d.contract_id}`}
                    className="font-medium text-sky-700 underline"
                  >
                    {d.filename ?? d.contract_id}
                  </Link>
                  <span className="text-xs text-neutral-400">
                    drafted {new Date(d.created_at).toLocaleString()}
                    {d.submitted_at && ` · submitted ${new Date(d.submitted_at).toLocaleString()}`}
                    {d.decided_at && ` · decided ${new Date(d.decided_at).toLocaleString()}`}
                  </span>
                </div>

                <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <TextBox title="Original clause" tone="border-red-300 bg-red-50">
                    <p className="whitespace-pre-wrap">{d.original_clause_text}</p>
                  </TextBox>
                  <TextBox title="AI draft" tone="border-sky-300 bg-sky-50">
                    <p className="whitespace-pre-wrap">{d.ai_draft_text}</p>
                  </TextBox>
                </div>

                {d.requester_edited_text && (
                  <div className="mt-3">
                    <TextBox title="Your edited version (what you submitted)" tone="border-violet-300 bg-violet-50">
                      <DiffText before={d.ai_draft_text} after={d.requester_edited_text} />
                      <p className="mt-1 text-[11px] text-neutral-500">
                        Highlighted = what you changed from the AI draft.
                      </p>
                    </TextBox>
                  </div>
                )}

                {d.status === "draft" && (
                  <DraftSubmitPanel
                    suggestionId={d.suggestion_id}
                    aiDraft={d.ai_draft_text}
                    rationale={d.rationale}
                    onSubmitted={() => load()}
                  />
                )}

                {(d.status === "approved" || d.status === "rejected") && (
                  <div className="mt-3 space-y-2">
                    {d.status === "approved" && (
                      <TextBox
                        title={
                          reviewerChanged
                            ? "Reviewer's approved version — they changed your text"
                            : "Approved as submitted — the reviewer made no changes"
                        }
                        tone="border-emerald-300 bg-emerald-50"
                      >
                        {reviewerChanged && d.reviewer_edited_text ? (
                          <>
                            <DiffText before={submitted} after={d.reviewer_edited_text} />
                            <p className="mt-1 text-[11px] text-neutral-500">
                              <mark className="rounded bg-emerald-200 px-0.5">Green</mark> = added by
                              the reviewer, <del className="rounded bg-red-100 px-0.5">red</del> =
                              removed from what you submitted.
                            </p>
                          </>
                        ) : (
                          <p className="whitespace-pre-wrap">{submitted}</p>
                        )}
                      </TextBox>
                    )}
                    {d.reviewer_note && (
                      <p className="text-xs">
                        <span className="font-semibold">Reviewer&apos;s note: </span>
                        <span className="italic">{d.reviewer_note}</span>
                      </p>
                    )}
                    {d.status === "approved" && d.document_version_id && (
                      <button
                        type="button"
                        onClick={() =>
                          downloadDocumentVersion(d.document_version_id!, `${d.contract_id}_updated.docx`)
                        }
                        className="text-xs font-semibold text-sky-700 underline"
                      >
                        Download the updated document
                      </button>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}

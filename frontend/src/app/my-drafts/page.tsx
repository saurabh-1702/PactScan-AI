"use client";

import Link from "next/link";
import { Download, FileEdit, Search } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import DiffText, { DiffLegend } from "@/components/DiffText";
import DraftSubmitPanel from "@/components/DraftSubmitPanel";
import TextPanel, { PlainText } from "@/components/TextPanel";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Alert, Badge, EmptyState, Skeleton } from "@/components/ui/Feedback";
import { Input, Select } from "@/components/ui/Field";
import { Page, PageHeader } from "@/components/ui/Layout";
import { Table, Td, Th, THead, Tr } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";
import { downloadDocumentVersion, getMyDrafts, type DraftInfo, type DraftStatus } from "@/lib/api";
import { formatDateTime, timeAgo } from "@/lib/format";
import { useDebounced, useLoad } from "@/lib/hooks";

const STATUS: Record<DraftStatus, { label: string; tone: "neutral" | "warn" | "success" | "danger" }> = {
  draft: { label: "Not submitted", tone: "neutral" },
  pending: { label: "With a reviewer", tone: "warn" },
  approved: { label: "Approved", tone: "success" },
  rejected: { label: "Rejected", tone: "danger" },
};

const FILTERS: { value: "all" | DraftStatus; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "draft", label: "Not submitted" },
  { value: "pending", label: "With a reviewer" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
];

function isStatus(v: string | null): v is DraftStatus {
  return v === "draft" || v === "pending" || v === "approved" || v === "rejected";
}

function DraftsView() {
  const toast = useToast();
  const params = useSearchParams();
  const initial = params.get("status");

  const drafts = useLoad(getMyDrafts);
  const [filter, setFilter] = useState<"all" | DraftStatus>(isStatus(initial) ? initial : "all");
  const [query, setQuery] = useState("");
  const q = useDebounced(query.trim().toLowerCase());
  const [openId, setOpenId] = useState<string | null>(null);

  const rows = useMemo(
    () =>
      (drafts.data ?? []).filter((d) => {
        if (filter !== "all" && d.status !== filter) return false;
        if (!q) return true;
        return (
          (d.filename ?? "").toLowerCase().includes(q) ||
          d.ai_draft_text.toLowerCase().includes(q) ||
          d.original_clause_text.toLowerCase().includes(q)
        );
      }),
    [drafts.data, filter, q],
  );
  const open = drafts.data?.find((d) => d.suggestion_id === openId) ?? null;

  async function onDownload(d: DraftInfo) {
    try {
      await downloadDocumentVersion(d.document_version_id!, `${d.filename ?? d.contract_id}_updated.docx`);
    } catch (err) {
      toast.error(`Download failed: ${err instanceof Error ? err.message : "unknown error"}`);
    }
  }

  return (
    <Page>
      <PageHeader
        title="My Drafts"
        description="Every fix you've drafted — the AI's version, your own edit if you made one, and what a reviewer changed before approving it."
      />

      {drafts.error && !drafts.data && <Alert tone="danger">{drafts.error}</Alert>}

      {drafts.loading && !drafts.data ? (
        <div className="space-y-2">
          <Skeleton className="h-10" />
          <Skeleton className="h-14" />
          <Skeleton className="h-14" />
        </div>
      ) : (drafts.data?.length ?? 0) === 0 ? (
        <EmptyState icon={FileEdit} title="You haven't drafted anything yet">
          Use “Draft a fix” on a finding in Detect, or ask for an edit in Ask. Drafts you create show
          up here.
        </EmptyState>
      ) : (
        <>
          <div className="mb-4 flex flex-wrap gap-3">
            <div className="relative min-w-56 flex-1 sm:max-w-xs">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint"
                aria-hidden
              />
              <Input
                aria-label="Search drafts"
                placeholder="Search by document or text"
                className="pl-9"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <Select
              aria-label="Filter by status"
              className="w-auto"
              value={filter}
              onChange={(e) => setFilter(e.target.value as "all" | DraftStatus)}
            >
              {FILTERS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </Select>
          </div>

          {rows.length === 0 ? (
            <EmptyState icon={Search} title="No drafts match">
              Try a different search or status.
            </EmptyState>
          ) : (
            <Table caption="My drafts">
              <THead>
                <tr>
                  <Th>Document</Th>
                  <Th>Status</Th>
                  <Th>Drafted</Th>
                  <Th>Decided by</Th>
                </tr>
              </THead>
              <tbody>
                {rows.map((d) => (
                  <Tr key={d.suggestion_id} onClick={() => setOpenId(d.suggestion_id)}>
                    <Td>
                      <span className="font-medium text-ink">{d.filename ?? d.contract_id}</span>
                      <span className="mt-0.5 line-clamp-1 max-w-md text-xs text-muted">
                        {d.requester_edited_text ?? d.ai_draft_text}
                      </span>
                    </Td>
                    <Td>
                      <Badge tone={STATUS[d.status].tone}>{STATUS[d.status].label}</Badge>
                    </Td>
                    <Td muted>{timeAgo(d.created_at)}</Td>
                    <Td muted>{d.decided_by_email ?? "—"}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </>
      )}

      <Dialog
        variant="sheet"
        open={!!open}
        onOpenChange={(o) => !o && setOpenId(null)}
        title={open?.filename ?? "Draft"}
        description={open ? STATUS[open.status].label : undefined}
      >
        {open && <DraftDetail d={open} onDownload={() => onDownload(open)} onSubmitted={drafts.reload} />}
      </Dialog>
    </Page>
  );
}

function DraftDetail({
  d,
  onDownload,
  onSubmitted,
}: {
  d: DraftInfo;
  onDownload: () => void;
  onSubmitted: () => void;
}) {
  const submitted = d.requester_edited_text ?? d.ai_draft_text;
  const reviewerChanged =
    d.reviewer_edited_text !== null && d.reviewer_edited_text.trim() !== submitted.trim();

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted">
        Drafted {formatDateTime(d.created_at)}
        {d.submitted_at && <> · submitted {formatDateTime(d.submitted_at)}</>}
        {d.decided_at && (
          <>
            {" "}
            · decided {formatDateTime(d.decided_at)}
            {d.decided_by_email && <> by {d.decided_by_email}</>}
          </>
        )}
      </p>

      <TextPanel title="Original clause" tone="danger">
        <PlainText>{d.original_clause_text}</PlainText>
      </TextPanel>

      <TextPanel title="AI draft" tone="accent">
        <PlainText>{d.ai_draft_text}</PlainText>
      </TextPanel>

      {d.requester_edited_text && (
        <TextPanel title="Your edited version" note="what you submitted" tone="neutral">
          <DiffText before={d.ai_draft_text} after={d.requester_edited_text} />
          <DiffLegend />
        </TextPanel>
      )}

      {d.status === "draft" && (
        <DraftSubmitPanel
          suggestionId={d.suggestion_id}
          aiDraft={d.ai_draft_text}
          rationale={d.rationale}
          onSubmitted={onSubmitted}
        />
      )}

      {d.status === "pending" && (
        <Alert tone="info">Waiting for a reviewer. You&apos;ll be notified when it&apos;s decided.</Alert>
      )}

      {d.status === "approved" && (
        <TextPanel
          title={reviewerChanged ? "Approved with the reviewer's changes" : "Approved as submitted"}
          note={reviewerChanged ? "changes shown against what you submitted" : "no changes were made"}
          tone="success"
        >
          {reviewerChanged && d.reviewer_edited_text ? (
            <>
              <DiffText before={submitted} after={d.reviewer_edited_text} />
              <DiffLegend />
            </>
          ) : (
            <PlainText>{submitted}</PlainText>
          )}
        </TextPanel>
      )}

      {d.status === "rejected" && (
        <Alert tone="danger" title="Rejected">
          {d.reviewer_note ? (
            <>
              <span className="font-medium">Reviewer&apos;s reason:</span> {d.reviewer_note}
            </>
          ) : (
            "The reviewer didn't give a reason."
          )}
        </Alert>
      )}
      {d.status === "approved" && d.reviewer_note && (
        <p className="text-[13px] text-muted">
          <span className="font-medium text-ink">Reviewer&apos;s note:</span> {d.reviewer_note}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4">
        {d.status === "approved" && d.document_version_id && (
          <Button variant="primary" size="sm" onClick={onDownload}>
            <Download className="h-3.5 w-3.5" aria-hidden /> Download updated document
          </Button>
        )}
        <Link
          href={`/contracts/${d.contract_id}`}
          className="text-[13px] font-medium text-accent hover:underline"
        >
          Open the contract
        </Link>
      </div>
    </div>
  );
}

export default function MyDraftsPage() {
  return (
    <Suspense fallback={null}>
      <DraftsView />
    </Suspense>
  );
}

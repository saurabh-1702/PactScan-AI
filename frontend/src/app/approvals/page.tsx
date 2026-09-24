"use client";

import { AlertTriangle, CheckSquare, Download } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import DiffText, { DiffLegend } from "@/components/DiffText";
import TextPanel, { PlainText } from "@/components/TextPanel";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Alert, Badge, EmptyState, Skeleton } from "@/components/ui/Feedback";
import { Field, Textarea } from "@/components/ui/Field";
import { Page, PageHeader } from "@/components/ui/Layout";
import { Tab, TabList, TabPanel, Tabs } from "@/components/ui/Tabs";
import { Table, Td, Th, THead, Tr } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";
import {
  decideApproval,
  decideRestoreRequest,
  downloadDocumentVersion,
  getAllApprovals,
  getContracts,
  getDocumentVersions,
  getRestoreRequests,
  type Approval,
  type RestoreRequestInfo,
} from "@/lib/api";
import { formatDateTime, timeAgo } from "@/lib/format";
import { useLoad } from "@/lib/hooks";

type Tone = "warn" | "success" | "danger";
const DECISION_TONE: Record<Approval["status"], Tone> = {
  pending: "warn",
  approved: "success",
  rejected: "danger",
};
const DECISION_LABEL: Record<Approval["status"], string> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
};

interface HistoryRow {
  key: string;
  kind: "Draft edit" | "Restore";
  contractId: string;
  requester: string | null;
  status: Approval["status"];
  decidedBy: string | null;
  decidedAt: string | null;
  note: string | null;
  detail: string;
}

function ApprovalsView() {
  const toast = useToast();
  const router = useRouter();
  const params = useSearchParams();
  const tab = params.get("tab") === "restore" ? "restore" : params.get("tab") === "history" ? "history" : "edits";

  const approvals = useLoad(getAllApprovals);
  const restores = useLoad(getRestoreRequests);
  const contracts = useLoad(getContracts);

  const filenames = useMemo(
    () => new Map((contracts.data ?? []).map((c) => [c.contract_id, c.filename])),
    [contracts.data],
  );
  const nameOf = (id: string) => filenames.get(id) ?? id;

  const pendingEdits = (approvals.data ?? []).filter((a) => a.status === "pending");
  const pendingRestores = (restores.data ?? []).filter((r) => r.status === "pending");

  const [reviewId, setReviewId] = useState<string | null>(null);
  const [restoreId, setRestoreId] = useState<string | null>(null);
  const review = approvals.data?.find((a) => a.id === reviewId) ?? null;
  const restore = restores.data?.find((r) => r.id === restoreId) ?? null;

  const history = useMemo<HistoryRow[]>(() => {
    const rows: HistoryRow[] = [];
    for (const a of approvals.data ?? []) {
      if (a.status === "pending") continue;
      rows.push({
        key: a.id,
        kind: "Draft edit",
        contractId: a.contract_id,
        requester: a.requested_by_email,
        status: a.status,
        decidedBy: a.decided_by_email,
        decidedAt: a.decided_at,
        note: a.reviewer_note,
        detail: a.edited_text ? "Approved with the reviewer's own edit" : a.proposed_text,
      });
    }
    for (const r of restores.data ?? []) {
      if (r.status === "pending") continue;
      rows.push({
        key: r.id,
        kind: "Restore",
        contractId: r.contract_id,
        requester: r.requested_by_email,
        status: r.status,
        decidedBy: r.decided_by_email,
        decidedAt: r.decided_at,
        note: r.reviewer_note,
        detail: `Restore to v${r.target_version_number}`,
      });
    }
    return rows.sort((a, b) => (b.decidedAt ?? "").localeCompare(a.decidedAt ?? ""));
  }, [approvals.data, restores.data]);

  function setTab(next: string) {
    router.replace(next === "edits" ? "/approvals" : `/approvals?tab=${next}`);
  }

  async function downloadLatest(contractId: string) {
    try {
      const versions = await getDocumentVersions(contractId);
      const latest = versions[versions.length - 1];
      if (!latest) throw new Error("no version on file");
      await downloadDocumentVersion(latest.id, `${nameOf(contractId)}_v${latest.version_number}.docx`);
    } catch (err) {
      toast.error(`Download failed: ${err instanceof Error ? err.message : "unknown error"}`);
    }
  }

  function afterDecision(message: string) {
    toast.success(message);
    approvals.reload();
    restores.reload();
  }

  const loading = approvals.loading && !approvals.data;

  return (
    <Page>
      <PageHeader
        title="Approvals"
        description="Nothing is written into a real document until a reviewer decides it here."
      />
      {approvals.error && !approvals.data && <Alert tone="danger">{approvals.error}</Alert>}

      <Tabs value={tab} onValueChange={setTab}>
        <TabList label="Approval queues">
          <Tab value="edits" count={pendingEdits.length}>
            Draft edits
          </Tab>
          <Tab value="restore" count={pendingRestores.length}>
            Restore requests
          </Tab>
          <Tab value="history">History</Tab>
        </TabList>

        <TabPanel value="edits">
          {loading ? (
            <Skeleton className="h-40" />
          ) : pendingEdits.length === 0 ? (
            <EmptyState icon={CheckSquare} title="No draft edits are waiting">
              When someone submits a drafted fix, it appears here for you to accept, edit or reject.
            </EmptyState>
          ) : (
            <Table caption="Draft edits waiting for review">
              <THead>
                <tr>
                  <Th>Document</Th>
                  <Th>Requested by</Th>
                  <Th>Submitted</Th>
                  <Th>Wording</Th>
                </tr>
              </THead>
              <tbody>
                {pendingEdits.map((a) => (
                  <Tr key={a.id} onClick={() => setReviewId(a.id)}>
                    <Td>
                      <span className="font-medium">{nameOf(a.contract_id)}</span>
                      <span className="mt-0.5 line-clamp-1 max-w-sm text-xs text-muted">
                        {a.proposed_text}
                      </span>
                    </Td>
                    <Td muted>{a.requested_by_email ?? "Unknown"}</Td>
                    <Td muted>{timeAgo(a.created_at)}</Td>
                    <Td>
                      <Badge tone={a.requester_edited_text ? "info" : "neutral"}>
                        {a.requester_edited_text ? "Edited by requester" : "AI draft"}
                      </Badge>
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </TabPanel>

        <TabPanel value="restore">
          {restores.loading && !restores.data ? (
            <Skeleton className="h-40" />
          ) : pendingRestores.length === 0 ? (
            <EmptyState icon={CheckSquare} title="No restore requests are waiting">
              A request to bring back an older version of a contract will appear here.
            </EmptyState>
          ) : (
            <Table caption="Restore requests waiting for a decision">
              <THead>
                <tr>
                  <Th>Document</Th>
                  <Th>Restore to</Th>
                  <Th>Requested by</Th>
                  <Th>Submitted</Th>
                  <Th>
                    <span className="sr-only">Flags</span>
                  </Th>
                </tr>
              </THead>
              <tbody>
                {pendingRestores.map((r) => (
                  <Tr key={r.id} onClick={() => setRestoreId(r.id)}>
                    <Td className="font-medium">{nameOf(r.contract_id)}</Td>
                    <Td>v{r.target_version_number}</Td>
                    <Td muted>{r.requested_by_email ?? "Unknown"}</Td>
                    <Td muted>{timeAgo(r.created_at)}</Td>
                    <Td>
                      {r.abuse_flagged && (
                        <Badge tone="danger">
                          <AlertTriangle className="mr-1 h-3 w-3" aria-hidden /> Repeated restores
                        </Badge>
                      )}
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </TabPanel>

        <TabPanel value="history">
          {loading ? (
            <Skeleton className="h-40" />
          ) : history.length === 0 ? (
            <EmptyState icon={CheckSquare} title="Nothing decided yet">
              Decisions you make on drafts and restores are recorded here.
            </EmptyState>
          ) : (
            <Table caption="Decision history">
              <THead>
                <tr>
                  <Th>Type</Th>
                  <Th>Document</Th>
                  <Th>Requested by</Th>
                  <Th>Decision</Th>
                  <Th>Decided</Th>
                  <Th align="right">
                    <span className="sr-only">Download</span>
                  </Th>
                </tr>
              </THead>
              <tbody>
                {history.map((h) => (
                  <Tr key={h.key}>
                    <Td muted>{h.kind}</Td>
                    <Td>
                      <span className="font-medium">{nameOf(h.contractId)}</span>
                      {h.note && <span className="mt-0.5 block text-xs italic text-muted">“{h.note}”</span>}
                    </Td>
                    <Td muted>{h.requester ?? "Unknown"}</Td>
                    <Td>
                      <Badge tone={DECISION_TONE[h.status]}>{DECISION_LABEL[h.status]}</Badge>
                    </Td>
                    <Td muted>
                      {formatDateTime(h.decidedAt)}
                      {h.decidedBy && <span className="block text-xs">by {h.decidedBy}</span>}
                    </Td>
                    <Td align="right">
                      {h.status === "approved" && (
                        <Button size="sm" onClick={() => downloadLatest(h.contractId)}>
                          <Download className="h-3.5 w-3.5" aria-hidden /> Latest
                        </Button>
                      )}
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </TabPanel>
      </Tabs>

      <ReviewSheet
        approval={review}
        filename={review ? nameOf(review.contract_id) : ""}
        onClose={() => setReviewId(null)}
        onDecided={(m) => {
          setReviewId(null);
          afterDecision(m);
        }}
      />
      <RestoreSheet
        request={restore}
        filename={restore ? nameOf(restore.contract_id) : ""}
        onClose={() => setRestoreId(null)}
        onDecided={(m) => {
          setRestoreId(null);
          afterDecision(m);
        }}
      />
    </Page>
  );
}

function ReviewSheet({
  approval: a,
  filename,
  onClose,
  onDecided,
}: {
  approval: Approval | null;
  filename: string;
  onClose: () => void;
  onDecided: (message: string) => void;
}) {
  const toast = useToast();
  const [mode, setMode] = useState<"view" | "edit" | "reject">("view");
  const [edited, setEdited] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  function reset() {
    setMode("view");
    setEdited("");
    setNote("");
  }

  async function decide(decision: "approved" | "rejected") {
    if (!a) return;
    setBusy(true);
    try {
      await decideApproval(a.id, decision, {
        editedText: decision === "approved" && mode === "edit" ? edited : undefined,
        note: decision === "rejected" ? note.trim() || undefined : undefined,
      });
      reset();
      onDecided(
        decision === "approved"
          ? "Approved — the change was written into a new document version."
          : "Rejected — the requester will see your reason, and no file was touched.",
      );
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not record the decision");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      variant="sheet"
      open={!!a}
      onOpenChange={(o) => {
        if (!o) {
          reset();
          onClose();
        }
      }}
      title={filename || "Review draft edit"}
      description={
        a ? `Requested by ${a.requested_by_email ?? "unknown"} · ${formatDateTime(a.created_at)}` : undefined
      }
      footer={
        a && (
          <>
            {mode === "view" && (
              <>
                <Button onClick={() => setMode("reject")} disabled={busy}>
                  Reject
                </Button>
                <Button
                  onClick={() => {
                    setEdited(a.proposed_text);
                    setMode("edit");
                  }}
                  disabled={busy}
                >
                  Edit
                </Button>
                <Button variant="primary" loading={busy} onClick={() => decide("approved")}>
                  Accept
                </Button>
              </>
            )}
            {mode === "edit" && (
              <>
                <Button onClick={reset} disabled={busy}>
                  Cancel
                </Button>
                <Button variant="primary" loading={busy} disabled={!edited.trim()} onClick={() => decide("approved")}>
                  Approve edited version
                </Button>
              </>
            )}
            {mode === "reject" && (
              <>
                <Button onClick={reset} disabled={busy}>
                  Cancel
                </Button>
                <Button variant="danger" loading={busy} onClick={() => decide("rejected")}>
                  Confirm rejection
                </Button>
              </>
            )}
          </>
        )
      }
    >
      {a && (
        <div className="space-y-4">
          <TextPanel title="Original clause" tone="danger">
            <PlainText>{a.original_clause_text}</PlainText>
          </TextPanel>

          <TextPanel
            title="Proposed wording"
            note={a.requester_edited_text ? "edited by the requester" : "AI draft, unchanged"}
            tone="success"
          >
            {mode === "edit" ? (
              <Textarea
                aria-label="Your edited wording"
                autoFocus
                rows={8}
                value={edited}
                onChange={(e) => setEdited(e.target.value)}
              />
            ) : (
              <PlainText>{a.proposed_text}</PlainText>
            )}
          </TextPanel>

          {a.requester_edited_text && a.ai_draft_text && mode === "view" && (
            <details className="rounded-md border border-line bg-surface px-3.5 py-2.5 text-[13px]">
              <summary className="cursor-pointer font-medium text-ink">
                What the requester changed from the AI draft
              </summary>
              <div className="mt-2">
                <DiffText before={a.ai_draft_text} after={a.requester_edited_text} />
                <DiffLegend />
              </div>
            </details>
          )}

          <p className="text-[13px] text-muted">
            <span className="font-medium text-ink">Rationale: </span>
            {a.rationale} (confidence {a.confidence})
          </p>

          {mode === "reject" && (
            <Field label="Reason for rejection" hint="Shown to whoever requested this fix.">
              {(p) => (
                <Textarea
                  {...p}
                  autoFocus
                  rows={3}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="e.g. This cap is still too low for our risk tolerance."
                />
              )}
            </Field>
          )}
        </div>
      )}
    </Dialog>
  );
}

function RestoreSheet({
  request: r,
  filename,
  onClose,
  onDecided,
}: {
  request: RestoreRequestInfo | null;
  filename: string;
  onClose: () => void;
  onDecided: (message: string) => void;
}) {
  const toast = useToast();
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  function reset() {
    setRejecting(false);
    setNote("");
  }

  async function decide(decision: "approved" | "rejected") {
    if (!r) return;
    setBusy(true);
    try {
      await decideRestoreRequest(r.id, decision, decision === "rejected" ? note.trim() || undefined : undefined);
      reset();
      onDecided(
        decision === "approved"
          ? "Approved — the older version was copied forward as a new version."
          : "Rejected — the requester will see your reason.",
      );
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not record the decision");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={!!r}
      onOpenChange={(o) => {
        if (!o) {
          reset();
          onClose();
        }
      }}
      title={r ? `Restore ${filename} to v${r.target_version_number}` : "Restore request"}
      description={r ? `Requested by ${r.requested_by_email ?? "unknown"} · ${formatDateTime(r.created_at)}` : undefined}
      footer={
        r &&
        (rejecting ? (
          <>
            <Button onClick={reset} disabled={busy}>
              Cancel
            </Button>
            <Button variant="danger" loading={busy} onClick={() => decide("rejected")}>
              Confirm rejection
            </Button>
          </>
        ) : (
          <>
            <Button onClick={() => setRejecting(true)} disabled={busy}>
              Reject
            </Button>
            <Button variant="primary" loading={busy} onClick={() => decide("approved")}>
              Accept
            </Button>
          </>
        ))
      }
    >
      {r && (
        <div className="space-y-4">
          {r.abuse_flagged && (
            <Alert tone="danger" title="Repeated restores">
              This contract has had several restores approved recently. Review this request carefully
              before approving another.
            </Alert>
          )}
          <TextPanel title="Reason given" tone="neutral">
            <PlainText>{r.reason}</PlainText>
          </TextPanel>
          <p className="text-xs text-muted">
            Approving copies v{r.target_version_number} forward as a new version. Nothing is
            overwritten.
          </p>
          {rejecting && (
            <Field label="Reason for rejection" hint="Shown to the requester.">
              {(p) => <Textarea {...p} autoFocus rows={3} value={note} onChange={(e) => setNote(e.target.value)} />}
            </Field>
          )}
        </div>
      )}
    </Dialog>
  );
}

export default function ApprovalsPage() {
  return (
    <Suspense fallback={null}>
      <ApprovalsView />
    </Suspense>
  );
}

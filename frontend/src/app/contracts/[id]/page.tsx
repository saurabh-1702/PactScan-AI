"use client";

import Link from "next/link";
import { ArrowLeft, CheckCircle2, History, RefreshCw } from "lucide-react";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import DownloadMenu from "@/components/DownloadMenu";
import FindingCard from "@/components/FindingCard";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Alert, Badge, EmptyState, Skeleton } from "@/components/ui/Feedback";
import { Field, Textarea } from "@/components/ui/Field";
import { Page } from "@/components/ui/Layout";
import { SEVERITY_ORDER } from "@/components/ui/Severity";
import { Tab, TabList, TabPanel, Tabs } from "@/components/ui/Tabs";
import { StageProgress } from "@/components/ui/StageProgress";
import { Table, Td, Th, THead, Tr } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";
import {
  createRestoreRequest,
  downloadDocumentVersion,
  getDetectReport,
  getDocumentVersions,
  getScanInfo,
  newJobId,
  postRescan,
  type DocumentVersionInfo,
  type ScanInfo,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useJobProgress, useLoad } from "@/lib/hooks";
import { useSession } from "@/lib/session";

/** Where a version came from. Only v1 is the original upload: an approved edit
 * is linked to its approval, and a restored copy is a later version with no
 * approval at all. */
function versionOrigin(v: DocumentVersionInfo): string {
  if (v.version_number === 1) return "Original upload";
  return v.approval_id ? "Approved edit" : "Restored copy";
}

export default function ContractDetailPage() {
  const params = useParams<{ id: string }>();
  const contractId = params.id;
  const toast = useToast();
  const { can } = useSession();

  const report = useLoad(() => getDetectReport(contractId), contractId);
  const versions = useLoad(() => getDocumentVersions(contractId), contractId);
  const scan = useLoad(() => getScanInfo(contractId), contractId);

  const [restoreTarget, setRestoreTarget] = useState<DocumentVersionInfo | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const findings = useMemo(
    () =>
      [...(report.data?.findings ?? [])].sort(
        (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity],
      ),
    [report.data],
  );
  const latest = versions.data?.length ? Math.max(...versions.data.map((v) => v.version_number)) : null;

  const baseName = (report.data?.filename ?? contractId).replace(/\.[^.]+$/, "");

  function downloadVersion(v: DocumentVersionInfo, format: "clean" | "redline") {
    return downloadDocumentVersion(v.id, `${baseName}_v${v.version_number}_${format}.docx`, format);
  }

  async function onRequestRestore() {
    if (!restoreTarget) return;
    setBusy(true);
    try {
      await createRestoreRequest(contractId, restoreTarget.id, reason.trim());
      toast.success(`Restore of v${restoreTarget.version_number} requested — a reviewer will decide it.`);
      setRestoreTarget(null);
      setReason("");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not submit the request");
    } finally {
      setBusy(false);
    }
  }

  const [rescanOpen, setRescanOpen] = useState(false);
  const [rescanJob, setRescanJob] = useState<string | null>(null);
  const [rescanError, setRescanError] = useState<string | null>(null);
  const rescanning = rescanJob !== null;
  const rescanProgress = useJobProgress(rescanJob);

  async function onRescan() {
    const jobId = newJobId();
    setRescanJob(jobId);
    setRescanError(null);
    try {
      const r = await postRescan(contractId, jobId);
      toast.success(
        `Re-scan complete — ${r.findings_after} finding${r.findings_after === 1 ? "" : "s"} (was ${r.findings_before}).`,
      );
      setRescanOpen(false);
    } catch (err) {
      setRescanError(err instanceof Error ? err.message : "The re-scan failed");
    } finally {
      setRescanJob(null);
      report.reload();
      versions.reload();
      scan.reload();
    }
  }

  return (
    <Page>
      <Link
        href="/dashboard"
        className="mb-4 inline-flex items-center gap-1 text-[13px] text-muted hover:text-ink"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> Dashboard
      </Link>

      <header className="mb-6">
        {report.loading && !report.data ? (
          <Skeleton className="h-7 w-72" />
        ) : (
          <h1 className="text-xl font-semibold tracking-tight text-ink">
            {report.data?.filename ?? "Contract"}
          </h1>
        )}
        <p className="mt-1 text-xs text-muted">
          {report.data?.timestamp && <>Last scanned {formatDateTime(report.data.timestamp)} · </>}
          <span className="font-mono">{contractId}</span>
        </p>
      </header>

      {report.error && !report.data && (
        <Alert tone="danger" title="Couldn't open this contract">
          {report.error}
        </Alert>
      )}

      {(!report.error || report.data) && (
        <Tabs defaultValue="findings">
          <TabList label="Contract sections">
            <Tab value="findings" count={report.data?.total_findings}>
              Findings
            </Tab>
            <Tab value="versions" count={versions.data?.length}>
              Versions
            </Tab>
          </TabList>

          <TabPanel value="findings">
            {report.loading && !report.data ? (
              <div className="space-y-3">
                <Skeleton className="h-28" />
                <Skeleton className="h-28" />
              </div>
            ) : findings.length === 0 ? (
              <Alert tone="success">
                <span className="inline-flex items-center gap-1.5">
                  <CheckCircle2 className="h-4 w-4" aria-hidden /> No compliance issues found in this
                  contract.
                </span>
              </Alert>
            ) : (
              <>
                <ScanStatus
                  scan={scan.data}
                  canRescan={can("contracts.rescan")}
                  onRescan={() => {
                    setRescanError(null);
                    setRescanOpen(true);
                  }}
                />
                <ul className="space-y-3">
                  {findings.map((f) => (
                    <FindingCard key={f.finding_id} finding={f} />
                  ))}
                </ul>
              </>
            )}
          </TabPanel>

          <TabPanel value="versions">
            {versions.loading && !versions.data ? (
              <Skeleton className="h-32" />
            ) : versions.error && !versions.data ? (
              <Alert tone="danger">{versions.error}</Alert>
            ) : (versions.data?.length ?? 0) === 0 ? (
              <EmptyState icon={History} title="No versions on file">
                A version is stored when the contract is scanned, and another each time a reviewer
                approves a change.
              </EmptyState>
            ) : (
              <>
                <Table caption="Document versions">
                  <THead>
                    <tr>
                      <Th>Version</Th>
                      <Th>Created</Th>
                      <Th>Origin</Th>
                      <Th align="right">
                        <span className="sr-only">Actions</span>
                      </Th>
                    </tr>
                  </THead>
                  <tbody>
                    {[...versions.data!].reverse().map((v) => (
                      <Tr key={v.id}>
                        <Td>
                          <span className="font-medium">v{v.version_number}</span>
                          {v.version_number === latest && (
                            <Badge tone="info" className="ml-2">
                              Current
                            </Badge>
                          )}
                        </Td>
                        <Td muted>{formatDateTime(v.created_at)}</Td>
                        <Td muted>{versionOrigin(v)}</Td>
                        <Td align="right">
                          <span className="inline-flex gap-2">
                            <DownloadMenu onDownload={(format) => downloadVersion(v, format)} />
                            {v.version_number !== latest && can("restore.request") && (
                              <Button size="sm" onClick={() => setRestoreTarget(v)}>
                                Request restore
                              </Button>
                            )}
                          </span>
                        </Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
                <p className="mt-3 text-xs text-muted">
                  Restoring never overwrites anything: an approved restore copies the older version
                  forward as a new version, so every earlier version stays downloadable.
                </p>
              </>
            )}
          </TabPanel>
        </Tabs>
      )}

      <Dialog
        open={!!restoreTarget}
        onOpenChange={(o) => {
          if (!o) {
            setRestoreTarget(null);
            setReason("");
          }
        }}
        title={`Request restore of v${restoreTarget?.version_number ?? ""}`}
        description="A reviewer must approve this before anything changes."
        footer={
          <>
            <Button onClick={() => setRestoreTarget(null)} disabled={busy}>
              Cancel
            </Button>
            <Button variant="primary" loading={busy} disabled={!reason.trim()} onClick={onRequestRestore}>
              Submit request
            </Button>
          </>
        }
      >
        <Field label="Why should this version be restored?">
          {(p) => (
            <Textarea
              {...p}
              autoFocus
              rows={4}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. The approved edit introduced an error we need to undo."
            />
          )}
        </Field>
      </Dialog>
      <Dialog
        open={rescanOpen}
        onOpenChange={(o) => {
          if (!rescanning) setRescanOpen(o);
        }}
        title="Re-scan the latest version"
        description="Read the current wording again and refresh this contract's findings."
        footer={
          <>
            <Button onClick={() => setRescanOpen(false)} disabled={rescanning}>
              Cancel
            </Button>
            <Button variant="primary" loading={rescanning} onClick={onRescan}>
              <RefreshCw className="h-3.5 w-3.5" aria-hidden /> Re-scan
            </Button>
          </>
        }
      >
        {rescanning ? (
          rescanProgress ? (
            <StageProgress stages={rescanProgress.stages} />
          ) : (
            <p className="text-[13px] text-muted">Starting…</p>
          )
        ) : (
          <div className="space-y-3 text-[13px] text-muted">
            <ul className="list-disc space-y-1.5 pl-5">
              <li>
                It reads the <span className="font-medium text-ink">clean copy</span> of the latest
                version — every approved change accepted.
              </li>
              <li>
                Findings are replaced with what the current wording actually produces, and it is
                re-checked against every regulation update recorded so far.
              </li>
              <li>
                Page numbers on findings may differ from the original PDF, because it re-reads the
                Word version.
              </li>
              <li>No notifications or emails are sent, and no new version is created.</li>
              <li>
                Your past drafts and decisions stay in My Drafts and Approvals, with the wording they
                were written against.
              </li>
            </ul>
            {rescanError && <Alert tone="danger">{rescanError}</Alert>}
          </div>
        )}
      </Dialog>
    </Page>
  );
}

function ScanStatus({
  scan,
  canRescan,
  onRescan,
}: {
  scan: ScanInfo | null;
  canRescan: boolean;
  onRescan: () => void;
}) {
  if (!scan) return null;

  const blockers = [
    scan.blockers.pending_approvals > 0 && `${scan.blockers.pending_approvals} draft(s) waiting for a reviewer`,
    scan.blockers.pending_restores > 0 && `${scan.blockers.pending_restores} restore request(s) waiting`,
    scan.blockers.unsubmitted_drafts > 0 && `${scan.blockers.unsubmitted_drafts} draft(s) not yet submitted`,
  ].filter(Boolean);

  const action = canRescan && (
    <div className="mt-2.5">
      <Button size="sm" variant="secondary" disabled={!scan.can_rescan} onClick={onRescan}>
        <RefreshCw className="h-3.5 w-3.5" aria-hidden /> Re-scan latest version
      </Button>
      {!scan.can_rescan && !scan.running && blockers.length > 0 && (
        <p className="mt-1.5 text-xs">
          Not available while there are {blockers.join(", ")}. Decide, submit or delete them first.
        </p>
      )}
    </div>
  );

  if (scan.running) {
    return (
      <Alert tone="info" className="mb-4" title="A re-scan is running">
        The findings below will refresh when it finishes.
      </Alert>
    );
  }
  if (scan.incomplete) {
    return (
      <Alert tone="warn" className="mb-4" title="The last re-scan didn't finish">
        Some findings may be missing. Run it again to rebuild them.
        {action}
      </Alert>
    );
  }
  if (scan.stale) {
    return (
      <Alert tone="info" className="mb-4" title={`These findings describe v${scan.scanned_version}`}>
        The current version is v{scan.latest_version}. Its wording has changed since, and it has not been
        re-checked, so a finding may already be resolved — or a new one may be missing.
        {action}
      </Alert>
    );
  }
  if (scan.latest_version > 1) {
    return (
      <p className="mb-3 text-xs text-muted">
        These findings describe the current wording
        {scan.last_rescan_at ? ` (re-scanned ${formatDateTime(scan.last_rescan_at)})` : " (v1)"}.
      </p>
    );
  }
  return null;
}

"use client";

import Link from "next/link";
import { ArrowLeft, CheckCircle2, Download, History } from "lucide-react";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import FindingCard from "@/components/FindingCard";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Alert, Badge, EmptyState, Skeleton } from "@/components/ui/Feedback";
import { Field, Textarea } from "@/components/ui/Field";
import { Page } from "@/components/ui/Layout";
import { SEVERITY_ORDER } from "@/components/ui/Severity";
import { Tab, TabList, TabPanel, Tabs } from "@/components/ui/Tabs";
import { Table, Td, Th, THead, Tr } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";
import {
  createRestoreRequest,
  downloadDocumentVersion,
  getDetectReport,
  getDocumentVersions,
  type DocumentVersionInfo,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useLoad } from "@/lib/hooks";
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

  async function onDownload(v: DocumentVersionInfo) {
    try {
      await downloadDocumentVersion(v.id, `${report.data?.filename ?? contractId}_v${v.version_number}.docx`);
    } catch (err) {
      toast.error(`Download failed: ${err instanceof Error ? err.message : "unknown error"}`);
    }
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
                {(versions.data?.length ?? 0) > 1 && (
                  <p className="mb-3 text-xs text-muted">
                    Findings come from the original upload. Approved edits and restores made since are
                    not re-scanned, so a finding marked “fix approved” means a reviewer approved a
                    change — not that the new wording was re-checked.
                  </p>
                )}
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
                            <Button size="sm" onClick={() => onDownload(v)}>
                              <Download className="h-3.5 w-3.5" aria-hidden /> Download
                            </Button>
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
    </Page>
  );
}

"use client";

import Link from "next/link";
import { ArrowRight, CheckCircle2, FileSearch } from "lucide-react";
import { useMemo, useState } from "react";
import DropZone from "@/components/DropZone";
import FindingCard from "@/components/FindingCard";
import { Button } from "@/components/ui/Button";
import { Alert, EmptyState, Skeleton } from "@/components/ui/Feedback";
import { Card, Page, PageHeader, SectionTitle } from "@/components/ui/Layout";
import { SEVERITY_ORDER } from "@/components/ui/Severity";
import { StageProgress } from "@/components/ui/StageProgress";
import { useToast } from "@/components/ui/Toast";
import { getContracts, newJobId, postDetect, type DetectReport } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useJobProgress, useLoad } from "@/lib/hooks";

export default function DetectPage() {
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<DetectReport | null>(null);

  const progress = useJobProgress(running ? jobId : null);
  const recent = useLoad(getContracts);

  async function onRun() {
    if (!file || running) return;
    const id = newJobId();
    setJobId(id);
    setRunning(true);
    setError(null);
    setReport(null);
    try {
      const result = await postDetect(file, id);
      setReport(result);
      setFile(null);
      recent.reload();
      toast.success(
        result.total_findings === 0
          ? `${result.filename} scanned — no compliance issues found.`
          : `${result.filename} scanned — ${result.total_findings} finding${result.total_findings === 1 ? "" : "s"}.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setRunning(false);
    }
  }

  const sorted = useMemo(
    () =>
      report
        ? [...report.findings].sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity])
        : [],
    [report],
  );
  const counts = useMemo(() => {
    const c = { HIGH: 0, MEDIUM: 0, LOW: 0 };
    for (const f of report?.findings ?? []) c[f.severity]++;
    return c;
  }, [report]);

  return (
    <Page width="narrow">
      <PageHeader
        title="Detect"
        description="Upload a vendor agreement. PactScan reads it, maps its clauses, and checks them against your playbook and the DPDP Act and GDPR."
      />

      <Card>
        {running ? (
          <div>
            <p className="text-sm font-medium text-ink">Scanning {file?.name}</p>
            <p className="mb-4 mt-0.5 text-xs text-muted">
              This runs the full compliance check, so it can take a minute. You can leave this page
              — it keeps running.
            </p>
            {progress ? (
              <StageProgress stages={progress.stages} />
            ) : (
              <p className="text-[13px] text-muted">Starting…</p>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <DropZone file={file} onFile={setFile} onReject={setError} />
            {error && (
              <Alert tone="danger" title="That didn't work">
                {error}
              </Alert>
            )}
            <div className="flex justify-end">
              <Button variant="primary" disabled={!file} onClick={onRun}>
                Run compliance check
              </Button>
            </div>
          </div>
        )}
      </Card>

      {report && (
        <section className="mt-8" aria-live="polite">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-ink">{report.filename}</h2>
              <p className="mt-0.5 text-[13px] text-muted">
                {report.total_findings === 0
                  ? "No compliance issues found."
                  : `${report.total_findings} finding${report.total_findings === 1 ? "" : "s"}: ${counts.HIGH} high, ${counts.MEDIUM} medium, ${counts.LOW} low.`}
              </p>
            </div>
            <Link
              href={`/contracts/${report.contract_id}`}
              className="inline-flex items-center gap-1 text-[13px] font-medium text-accent hover:underline"
            >
              Open contract and version history
              <ArrowRight className="h-3.5 w-3.5" aria-hidden />
            </Link>
          </div>

          {report.total_findings === 0 ? (
            <Alert tone="success" className="mt-4">
              <span className="inline-flex items-center gap-1.5">
                <CheckCircle2 className="h-4 w-4" aria-hidden /> Nothing in this contract conflicts with
                your playbook or the regulations.
              </span>
            </Alert>
          ) : (
            <ul className="mt-4 space-y-3">
              {sorted.map((f) => (
                <FindingCard key={f.finding_id} finding={f} />
              ))}
            </ul>
          )}
        </section>
      )}

      <section className="mt-10">
        <SectionTitle>Recent documents</SectionTitle>
        {recent.loading && !recent.data ? (
          <div className="space-y-2">
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
          </div>
        ) : recent.error && !recent.data ? (
          <Alert tone="danger">{recent.error}</Alert>
        ) : recent.data && recent.data.length === 0 ? (
          <EmptyState icon={FileSearch} title="No documents yet">
            Contracts you scan appear here so you can reopen their findings and versions.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface shadow-sm">
            {(recent.data ?? []).slice(0, 6).map((c) => (
              <li key={c.contract_id}>
                <Link
                  href={`/contracts/${c.contract_id}`}
                  className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-hover"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-[13px] font-medium text-ink">{c.filename}</span>
                    <span className="block text-xs text-muted">{formatDateTime(c.uploaded_at)}</span>
                  </span>
                  <span className="shrink-0 text-xs text-muted">
                    {c.total_findings === 0
                      ? "No findings"
                      : `${c.total_findings} finding${c.total_findings === 1 ? "" : "s"}`}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </Page>
  );
}

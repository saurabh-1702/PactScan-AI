"use client";

import Link from "next/link";
import { ArrowRight, CheckCircle2, FileText } from "lucide-react";
import { useMemo } from "react";
import { Alert, EmptyState, Skeleton } from "@/components/ui/Feedback";
import { Card, Page, PageHeader, SectionTitle } from "@/components/ui/Layout";
import { SEVERITY_DOT } from "@/components/ui/Severity";
import { Table, Td, Th, THead, Tr } from "@/components/ui/Table";
import { cn } from "@/components/ui/cn";
import {
  getContracts,
  getDashboardOverview,
  getFindingsPipeline,
  getMyDrafts,
  getNotifications,
  getRestoreRequests,
  getPendingApprovals,
  type FindingsPipeline,
  type Severity,
} from "@/lib/api";
import { formatDateTime, timeAgo } from "@/lib/format";
import { useLoad } from "@/lib/hooks";
import { useSession } from "@/lib/session";

const STAGES: { key: keyof FindingsPipeline; label: string }[] = [
  { key: "new_finding", label: "New" },
  { key: "redline_suggested", label: "Fix drafted" },
  { key: "pending_approval", label: "In review" },
  { key: "fixed_applied", label: "Fix approved" },
  { key: "rejected", label: "Rejected" },
];

const SEVERITIES: { key: Severity; label: string }[] = [
  { key: "HIGH", label: "High" },
  { key: "MEDIUM", label: "Medium" },
  { key: "LOW", label: "Low" },
];

interface AttentionItem {
  key: string;
  text: string;
  href: string;
}

export default function DashboardPage() {
  const { can } = useSession();
  const reviewer = can("approvals.review");

  const overview = useLoad(getDashboardOverview);
  const pipeline = useLoad(getFindingsPipeline);
  const contracts = useLoad(getContracts);
  const drafts = useLoad(getMyDrafts);
  const pending = useLoad(() => (reviewer ? getPendingApprovals() : Promise.resolve([])), String(reviewer));
  const restores = useLoad(
    () => (reviewer ? getRestoreRequests("pending") : Promise.resolve([])),
    String(reviewer),
  );
  const activity = useLoad(() => getNotifications(false));

  const attention = useMemo<AttentionItem[]>(() => {
    const items: AttentionItem[] = [];
    const n = (x: number, one: string, many: string) => `${x} ${x === 1 ? one : many}`;

    if (reviewer && (pending.data?.length ?? 0) > 0) {
      items.push({
        key: "approvals",
        text: `${n(pending.data!.length, "draft edit is", "draft edits are")} waiting for your review`,
        href: "/approvals",
      });
    }
    if (reviewer && (restores.data?.length ?? 0) > 0) {
      items.push({
        key: "restores",
        text: `${n(restores.data!.length, "restore request is", "restore requests are")} waiting for your decision`,
        href: "/approvals?tab=restore",
      });
    }
    const unsubmitted = (drafts.data ?? []).filter((d) => d.status === "draft").length;
    if (unsubmitted > 0) {
      items.push({
        key: "unsubmitted",
        text: `${n(unsubmitted, "draft is", "drafts are")} ready but not yet submitted`,
        href: "/my-drafts?status=draft",
      });
    }
    const rejected = (drafts.data ?? []).filter((d) => d.status === "rejected").length;
    if (rejected > 0) {
      items.push({
        key: "rejected",
        text: `${n(rejected, "of your drafts was", "of your drafts were")} rejected — see the reviewer's reason`,
        href: "/my-drafts?status=rejected",
      });
    }
    const highOpen = (pipeline.data?.new_finding ?? []).filter((f) => f.severity === "HIGH");
    if (highOpen.length > 0) {
      items.push({
        key: "high",
        text: `${n(highOpen.length, "high-severity finding has", "high-severity findings have")} no fix drafted yet`,
        href: `/contracts/${highOpen[0].contract_id}`,
      });
    }
    return items;
  }, [reviewer, pending.data, restores.data, drafts.data, pipeline.data]);

  const attentionLoading =
    (drafts.loading && !drafts.data) || (pipeline.loading && !pipeline.data) || (reviewer && pending.loading && !pending.data);

  const bySeverity = overview.data?.findings_by_severity;
  const totalFindings = bySeverity ? bySeverity.HIGH + bySeverity.MEDIUM + bySeverity.LOW : 0;
  const firstError = overview.error ?? pipeline.error ?? contracts.error;

  return (
    <Page>
      <PageHeader
        title="Dashboard"
        description={
          reviewer
            ? "What needs a decision, and the state of every contract in your organisation."
            : "What needs your attention, and the state of the contracts you've uploaded."
        }
      />

      {firstError && (
        <Alert tone="danger" className="mb-5">
          {firstError}
        </Alert>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="min-w-0 space-y-6 lg:col-span-2">
          <section>
            <SectionTitle>Needs attention</SectionTitle>
            <Card padded={false}>
              {attentionLoading ? (
                <div className="space-y-3 p-5">
                  <Skeleton className="h-5 w-3/4" />
                  <Skeleton className="h-5 w-2/3" />
                </div>
              ) : attention.length === 0 ? (
                <p className="flex items-center gap-2 px-5 py-4 text-[13px] text-muted">
                  <CheckCircle2 className="h-4 w-4 text-success" aria-hidden />
                  Nothing needs your attention right now.
                </p>
              ) : (
                <ul className="divide-y divide-line">
                  {attention.map((item) => (
                    <li key={item.key}>
                      <Link
                        href={item.href}
                        className="group flex items-center justify-between gap-4 px-5 py-3.5 text-[13px] text-ink hover:bg-hover"
                      >
                        <span>{item.text}</span>
                        <ArrowRight
                          className="h-4 w-4 shrink-0 text-faint transition-transform group-hover:translate-x-0.5 group-hover:text-ink"
                          aria-hidden
                        />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </section>

          <section>
            <SectionTitle
              action={
                <Link href="/detect" className="text-xs font-medium text-accent hover:underline">
                  Scan a contract
                </Link>
              }
            >
              Recent documents
            </SectionTitle>
            {contracts.loading && !contracts.data ? (
              <Skeleton className="h-40" />
            ) : (contracts.data?.length ?? 0) === 0 ? (
              <EmptyState
                icon={FileText}
                title="No contracts yet"
                action={
                  <Link href="/detect" className="text-[13px] font-medium text-accent hover:underline">
                    Scan your first contract
                  </Link>
                }
              >
                Upload a vendor agreement in Detect and its findings will appear here.
              </EmptyState>
            ) : (
              <Table caption="Recent documents">
                <THead>
                  <tr>
                    <Th>Document</Th>
                    <Th>Findings</Th>
                    <Th>Versions</Th>
                    <Th>Uploaded</Th>
                  </tr>
                </THead>
                <tbody>
                  {contracts.data!.slice(0, 6).map((c) => (
                    <Tr key={c.contract_id}>
                      <Td>
                        <Link
                          href={`/contracts/${c.contract_id}`}
                          className="font-medium text-ink hover:text-accent hover:underline"
                        >
                          {c.filename}
                        </Link>
                        {reviewer && c.uploaded_by_email && (
                          <span className="block text-xs text-muted">{c.uploaded_by_email}</span>
                        )}
                      </Td>
                      <Td>
                        {c.total_findings === 0 ? (
                          <span className="text-muted">None</span>
                        ) : (
                          <span className="inline-flex items-center gap-3 text-xs">
                            {SEVERITIES.map(({ key, label }) => {
                              const v = c[key.toLowerCase() as "high" | "medium" | "low"];
                              return v > 0 ? (
                                <span key={key} className="inline-flex items-center gap-1.5">
                                  <span className={cn("h-2 w-2 rounded-full", SEVERITY_DOT[key])} aria-hidden />
                                  {v} {label.toLowerCase()}
                                </span>
                              ) : null;
                            })}
                          </span>
                        )}
                      </Td>
                      <Td muted>{c.version_count || 1}</Td>
                      <Td muted>{formatDateTime(c.uploaded_at)}</Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            )}
          </section>
        </div>

        <div className="min-w-0 space-y-6">
          <section>
            <SectionTitle>Findings by severity</SectionTitle>
            <Card>
              {overview.loading && !overview.data ? (
                <Skeleton className="h-16" />
              ) : totalFindings === 0 ? (
                <p className="text-[13px] text-muted">No findings yet.</p>
              ) : (
                <>
                  <p className="text-2xl font-semibold tracking-tight text-ink">
                    {totalFindings}
                    <span className="ml-1.5 text-[13px] font-normal text-muted">
                      across {overview.data?.total_contracts} contract
                      {overview.data?.total_contracts === 1 ? "" : "s"}
                    </span>
                  </p>
                  <div
                    className="mt-3 flex h-2.5 overflow-hidden rounded-full bg-sunken"
                    role="img"
                    aria-label={`${bySeverity!.HIGH} high, ${bySeverity!.MEDIUM} medium, ${bySeverity!.LOW} low severity findings`}
                  >
                    {SEVERITIES.map(({ key }) =>
                      bySeverity![key] > 0 ? (
                        <div
                          key={key}
                          className={SEVERITY_DOT[key]}
                          style={{ width: `${(bySeverity![key] / totalFindings) * 100}%` }}
                        />
                      ) : null,
                    )}
                  </div>
                  <ul className="mt-3 space-y-1.5">
                    {SEVERITIES.map(({ key, label }) => (
                      <li key={key} className="flex items-center justify-between text-[13px]">
                        <span className="inline-flex items-center gap-2 text-muted">
                          <span className={cn("h-2 w-2 rounded-full", SEVERITY_DOT[key])} aria-hidden />
                          {label}
                        </span>
                        <span className="font-medium text-ink">{bySeverity![key]}</span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </Card>
          </section>

          <section>
            <SectionTitle>Where findings stand</SectionTitle>
            <Card>
              {pipeline.loading && !pipeline.data ? (
                <Skeleton className="h-24" />
              ) : (
                <>
                  <ul className="space-y-2">
                    {STAGES.map(({ key, label }) => (
                      <li key={key} className="flex items-center justify-between text-[13px]">
                        <span className="text-muted">{label}</span>
                        <span className="font-medium text-ink">{pipeline.data?.[key].length ?? 0}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-3 border-t border-line pt-3 text-xs text-muted">
                    Counted per finding, using its furthest-along draft. “Fix approved” means a reviewer approved a change; it isn&apos;t re-scanned. Drafts waiting with a
                    reviewer right now:{" "}
                    <span className="font-semibold text-ink">
                      {overview.data?.approvals_by_status.pending ?? 0}
                    </span>
                    .
                  </p>
                </>
              )}
            </Card>
          </section>

          <section>
            <SectionTitle
              action={
                <Link href="/notifications" className="text-xs font-medium text-accent hover:underline">
                  View all
                </Link>
              }
            >
              Recent activity
            </SectionTitle>
            <Card padded={false}>
              {activity.loading && !activity.data ? (
                <div className="p-4">
                  <Skeleton className="h-12" />
                </div>
              ) : (activity.data?.length ?? 0) === 0 ? (
                <p className="px-4 py-4 text-[13px] text-muted">Nothing new.</p>
              ) : (
                <ul className="divide-y divide-line">
                  {activity.data!.slice(0, 5).map((n) => (
                    <li key={n.id} className="px-4 py-3">
                      <p className={cn("text-[13px] leading-snug", n.is_read ? "text-muted" : "text-ink")}>
                        {n.message}
                      </p>
                      <p className="mt-0.5 text-xs text-muted">{timeAgo(n.created_at)}</p>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </section>
        </div>
      </div>
    </Page>
  );
}

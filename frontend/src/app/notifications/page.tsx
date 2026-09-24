"use client";

import { Bell, Download } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Alert, EmptyState, Skeleton } from "@/components/ui/Feedback";
import { Page, PageHeader } from "@/components/ui/Layout";
import { Tab, TabList, TabPanel, Tabs } from "@/components/ui/Tabs";
import { cn } from "@/components/ui/cn";
import { useToast } from "@/components/ui/Toast";
import {
  downloadDocumentVersion,
  getNotifications,
  markNotificationRead,
  type NotificationInfo,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useLoad } from "@/lib/hooks";

function dot(n: NotificationInfo): string {
  if (n.kind === "approval_decided") return n.message.includes("rejected") ? "bg-danger" : "bg-success";
  if (n.severity === "HIGH") return "bg-danger";
  if (n.severity === "MEDIUM") return "bg-warn";
  return "bg-accent";
}

function NotificationList({
  rows,
  onDownload,
  onMarkRead,
}: {
  rows: NotificationInfo[];
  onDownload: (versionId: string) => void;
  onMarkRead: (n: NotificationInfo) => void;
}) {
  if (rows.length === 0) {
    return (
      <EmptyState icon={Bell} title="Nothing here">
        New findings on your contracts and decisions on your drafts appear here.
      </EmptyState>
    );
  }
  return (
    <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface shadow-sm">
      {rows.map((n) => (
        <li key={n.id} className="flex items-start gap-3 px-4 py-3.5">
          <span
            className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", n.is_read ? "bg-line-strong" : dot(n))}
            aria-hidden
          />
          <div className="min-w-0 flex-1">
            <p className={cn("text-[13px] leading-snug", n.is_read ? "text-muted" : "font-medium text-ink")}>
              {n.message}
            </p>
            <p className="mt-1 text-xs text-muted">{formatDateTime(n.created_at)}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {n.document_version_id && (
              <Button size="sm" onClick={() => onDownload(n.document_version_id!)}>
                <Download className="h-3.5 w-3.5" aria-hidden /> Download
              </Button>
            )}
            {!n.is_read && (
              <Button size="sm" variant="ghost" onClick={() => onMarkRead(n)}>
                Mark read
              </Button>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

export default function NotificationsPage() {
  const toast = useToast();
  const all = useLoad(() => getNotifications(false));
  const [readIds, setReadIds] = useState<Set<string>>(new Set());

  const items = useMemo(
    () => (all.data ?? []).map((n) => (readIds.has(n.id) ? { ...n, is_read: true } : n)),
    [all.data, readIds],
  );
  const unread = items.filter((n) => !n.is_read);

  async function markRead(n: NotificationInfo) {
    if (n.is_read) return;
    try {
      await markNotificationRead(n.id);
      setReadIds((prev) => new Set(prev).add(n.id));
    } catch {
      toast.error("Couldn't mark that as read.");
    }
  }

  async function markAllRead() {
    await Promise.all(unread.map((n) => markNotificationRead(n.id).catch(() => null)));
    setReadIds((prev) => new Set([...prev, ...unread.map((n) => n.id)]));
  }

  async function download(id: string) {
    try {
      await downloadDocumentVersion(id, `${id}.docx`);
    } catch (err) {
      toast.error(`Download failed: ${err instanceof Error ? err.message : "unknown error"}`);
    }
  }

  return (
    <Page width="narrow">
      <PageHeader
        title="Notifications"
        description="New findings on your contracts, and decisions on the drafts and restores you requested."
        actions={
          unread.length > 0 && (
            <Button size="sm" onClick={markAllRead}>
              Mark all read
            </Button>
          )
        }
      />
      {all.error && !all.data && <Alert tone="danger">{all.error}</Alert>}
      {all.loading && !all.data ? (
        <Skeleton className="h-48" />
      ) : (
        <Tabs defaultValue="all">
          <TabList label="Notification filter">
            <Tab value="all" count={items.length}>
              All
            </Tab>
            <Tab value="unread" count={unread.length}>
              Unread
            </Tab>
          </TabList>
          <TabPanel value="all">
            <NotificationList rows={items} onDownload={download} onMarkRead={markRead} />
          </TabPanel>
          <TabPanel value="unread">
            <NotificationList rows={unread} onDownload={download} onMarkRead={markRead} />
          </TabPanel>
        </Tabs>
      )}
    </Page>
  );
}

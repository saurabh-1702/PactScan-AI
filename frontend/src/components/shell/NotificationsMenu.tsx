"use client";

import * as Popover from "@radix-ui/react-popover";
import { Bell, Download } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  downloadDocumentVersion,
  getNotifications,
  markNotificationRead,
  type NotificationInfo,
} from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { cn } from "@/components/ui/cn";

const POLL_MS = 7000;

function toneDot(n: NotificationInfo): string {
  if (n.kind === "approval_decided") {
    return n.message.includes("rejected") ? "bg-danger" : "bg-success";
  }
  if (n.severity === "HIGH") return "bg-danger";
  if (n.severity === "MEDIUM") return "bg-warn";
  return "bg-accent";
}

export default function NotificationsMenu() {
  const [items, setItems] = useState<NotificationInfo[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const rows = await getNotifications(false);
        if (!cancelled) setItems(rows.slice(0, 15));
      } catch {
        /* transient failure — the next poll retries */
      } finally {
        if (!cancelled) setLoaded(true);
      }
    }
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const unread = items.filter((n) => !n.is_read).length;

  async function markRead(n: NotificationInfo) {
    if (n.is_read) return;
    try {
      await markNotificationRead(n.id);
      setItems((prev) => prev.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)));
    } catch {
      /* non-fatal */
    }
  }

  async function download(versionId: string) {
    try {
      await downloadDocumentVersion(versionId, `${versionId}.docx`);
    } catch {
      /* non-fatal — the file remains reachable from the contract page */
    }
  }

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          type="button"
          aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
          className="relative inline-flex h-9 w-9 items-center justify-center rounded-md text-muted hover:bg-hover hover:text-ink"
        >
          <Bell className="h-[18px] w-[18px]" aria-hidden />
          {unread > 0 && (
            <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[10px] font-semibold leading-none text-white">
              {unread > 9 ? "9+" : unread}
            </span>
          )}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={6}
          className="popover-in z-50 w-[22rem] max-w-[calc(100vw-2rem)] rounded-lg border border-line bg-surface shadow-md"
        >
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <p className="text-sm font-semibold text-ink">Notifications</p>
            <Popover.Close asChild>
              <Link href="/notifications" className="text-xs font-medium text-accent hover:underline">
                View all
              </Link>
            </Popover.Close>
          </div>
          <ul className="max-h-96 overflow-y-auto">
            {!loaded && (
              <li className="px-4 py-6 text-center text-[13px] text-muted">Loading…</li>
            )}
            {loaded && items.length === 0 && (
              <li className="px-4 py-8 text-center text-[13px] text-muted">
                You&apos;re all caught up. New findings and review decisions appear here.
              </li>
            )}
            {items.map((n) => (
              <li key={n.id} className="flex gap-3 border-b border-line px-4 py-3 last:border-0">
                <span
                  className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", n.is_read ? "bg-line-strong" : toneDot(n))}
                  aria-hidden
                />
                <div className="min-w-0 flex-1">
                  <p className={cn("text-[13px] leading-snug", n.is_read ? "text-muted" : "font-medium text-ink")}>
                    {n.message}
                  </p>
                  <div className="mt-1.5 flex items-center gap-3">
                    <span className="text-xs text-muted">{timeAgo(n.created_at)}</span>
                    {n.document_version_id && (
                      <button
                        type="button"
                        onClick={() => download(n.document_version_id!)}
                        className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
                      >
                        <Download className="h-3 w-3" aria-hidden />
                        Download
                      </button>
                    )}
                    {!n.is_read && (
                      <button
                        type="button"
                        onClick={() => markRead(n)}
                        className="text-xs font-medium text-muted hover:text-ink"
                      >
                        Mark read
                      </button>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  downloadDocumentVersion,
  getNotifications,
  markNotificationRead,
  type NotificationInfo,
} from "@/lib/api";
import { clearToken, getCurrentUser } from "@/lib/auth";

const POLL_MS = 7000;

const NAV_LINKS: { href: string; label: string; roles?: string[] }[] = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/detect", label: "Detect" },
  { href: "/ask", label: "Ask" },
  { href: "/approvals", label: "Approvals", roles: ["reviewer", "admin"] },
];

export default function AppHeader() {
  const pathname = usePathname();
  const router = useRouter();
  const [role, setRole] = useState<string | null>(null);
  const [notifications, setNotifications] = useState<NotificationInfo[]>([]);
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setRole(getCurrentUser()?.role ?? null);
  }, [pathname]);

  useEffect(() => {
    if (!role) return;
    let cancelled = false;

    async function poll() {
      try {
        const rows = await getNotifications(false);
        if (!cancelled) setNotifications(rows.slice(0, 10));
      } catch {
        /* transient failure — next poll will retry */
      }
    }

    poll();
    const id = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [role]);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  if (pathname === "/login" || !role) return null;

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  async function onMarkRead(n: NotificationInfo) {
    if (n.is_read) return;
    try {
      await markNotificationRead(n.id);
      setNotifications((prev) => prev.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)));
    } catch {
      /* non-fatal */
    }
  }

  function onLogout() {
    clearToken();
    router.push("/login");
  }

  async function onDownload(e: React.MouseEvent, versionId: string) {
    e.stopPropagation(); // don't also trigger the row's mark-read/select handler
    try {
      await downloadDocumentVersion(versionId, `${versionId}.docx`);
    } catch {
      /* non-fatal — the document is still reachable from /approvals if a
         reviewer/admin, or the reviewer can be asked to re-share it */
    }
  }

  function dotColor(n: NotificationInfo): string {
    if (n.kind === "approval_decided") {
      return n.message.includes("rejected") ? "bg-red-500" : "bg-emerald-500";
    }
    if (n.severity === "HIGH") return "bg-red-500";
    if (n.severity === "MEDIUM") return "bg-amber-500";
    return "bg-sky-500";
  }

  return (
    <header className="flex items-center justify-between border-b border-neutral-200 bg-white px-6 py-3">
      <div className="flex items-center gap-6">
        <span className="text-sm font-semibold tracking-tight">PactScan AI</span>
        <nav className="flex gap-4 text-sm font-medium">
          {NAV_LINKS.filter((l) => !l.roles || l.roles.includes(role)).map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={
                pathname?.startsWith(l.href)
                  ? "text-sky-700 underline"
                  : "text-neutral-600 hover:text-sky-700"
              }
            >
              {l.label}
            </Link>
          ))}
        </nav>
      </div>

      <div className="flex items-center gap-4">
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="relative rounded p-1.5 text-neutral-600 hover:bg-neutral-100"
            aria-label="Notifications"
          >
            🔔
            {unreadCount > 0 && (
              <span className="absolute -right-0.5 -top-0.5 rounded-full bg-red-600 px-1 text-[10px] font-bold text-white">
                {unreadCount}
              </span>
            )}
          </button>
          {open && (
            <div className="absolute right-0 z-10 mt-2 w-80 rounded border border-neutral-200 bg-white shadow-lg">
              <div className="border-b border-neutral-100 px-3 py-2 text-xs font-semibold uppercase text-neutral-500">
                Notifications
              </div>
              <ul className="max-h-80 overflow-y-auto">
                {notifications.length === 0 && (
                  <li className="px-3 py-3 text-sm text-neutral-400">Nothing yet.</li>
                )}
                {notifications.map((n) => (
                  <li
                    key={n.id}
                    onClick={() => onMarkRead(n)}
                    className={`cursor-pointer border-b border-neutral-50 px-3 py-2 text-sm last:border-0 hover:bg-neutral-50 ${
                      n.is_read ? "text-neutral-500" : "font-medium text-neutral-900"
                    }`}
                  >
                    <span className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full ${dotColor(n)}`} />
                    {n.message}
                    <div className="mt-1 flex items-center justify-between">
                      <span className="text-[10px] text-neutral-400">
                        {new Date(n.created_at).toLocaleString()}
                      </span>
                      {n.document_version_id && (
                        <button
                          type="button"
                          onClick={(e) => onDownload(e, n.document_version_id!)}
                          className="text-[11px] font-semibold text-sky-700 underline"
                        >
                          Download
                        </button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <span className="text-xs uppercase text-neutral-400">{role}</span>
        <button
          type="button"
          onClick={onLogout}
          className="text-xs font-semibold text-neutral-500 hover:text-neutral-800"
        >
          Log out
        </button>
      </div>
    </header>
  );
}

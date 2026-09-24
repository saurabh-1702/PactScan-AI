"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { cn } from "@/components/ui/cn";
import { Hint } from "@/components/ui/Overlay";
import { navFor, type Role } from "@/lib/permissions";
import { NavGlyph } from "./NavIcons";

export function Wordmark({ collapsed }: { collapsed?: boolean }) {
  return (
    <span className="flex items-center gap-2 font-semibold tracking-tight text-ink">
      <span className="flex h-7 w-7 items-center justify-center rounded-md bg-accent text-[13px] font-bold text-white">
        P
      </span>
      {!collapsed && <span className="text-[15px]">PactScan</span>}
    </span>
  );
}

export default function Sidebar({
  role,
  collapsed,
  onToggle,
  onNavigate,
  mobile,
}: {
  role: Role;
  collapsed: boolean;
  onToggle: () => void;
  onNavigate?: () => void;
  mobile?: boolean;
}) {
  const pathname = usePathname() ?? "";
  const items = navFor(role);
  const slim = collapsed && !mobile;

  return (
    <nav
      aria-label="Main"
      className="flex h-full flex-col border-r border-line bg-surface"
    >
      <div className={cn("flex h-14 items-center", slim ? "justify-center" : "px-4")}>
        <Link href="/dashboard" onClick={onNavigate} aria-label="PactScan home">
          <Wordmark collapsed={slim} />
        </Link>
      </div>

      <ul className="flex-1 space-y-0.5 px-2 py-2">
        {items.map((item) => {
          const active = pathname === item.href || pathname.startsWith(item.href + "/");
          const link = (
            <Link
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "group relative flex h-9 items-center gap-3 rounded-md text-[13px] font-medium transition-colors duration-150",
                slim ? "justify-center px-0" : "px-3",
                active ? "bg-accent-soft text-accent-strong" : "text-muted hover:bg-hover hover:text-ink",
              )}
            >
              {active && (
                <span className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-accent" />
              )}
              <NavGlyph icon={item.icon} className="h-[18px] w-[18px] shrink-0" />
              {!slim && <span className="truncate">{item.label}</span>}
              {slim && <span className="sr-only">{item.label}</span>}
            </Link>
          );
          return (
            <li key={item.href}>
              {slim ? (
                <Hint label={item.label} side="right">
                  {link}
                </Hint>
              ) : (
                link
              )}
            </li>
          );
        })}
      </ul>

      {!mobile && (
        <div className={cn("border-t border-line p-2", slim && "flex justify-center")}>
          <button
            type="button"
            onClick={onToggle}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={cn(
              "flex h-9 items-center gap-3 rounded-md text-[13px] text-muted hover:bg-hover hover:text-ink",
              slim ? "w-9 justify-center" : "w-full px-3",
            )}
          >
            {collapsed ? (
              <PanelLeftOpen className="h-[18px] w-[18px]" aria-hidden />
            ) : (
              <>
                <PanelLeftClose className="h-[18px] w-[18px]" aria-hidden />
                Collapse
              </>
            )}
          </button>
        </div>
      )}
    </nav>
  );
}

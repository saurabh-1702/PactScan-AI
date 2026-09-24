"use client";

import { Command } from "cmdk";
import { FileText, LogOut, MessageSquare, Search, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getChatSessions, getContracts, type ChatSessionInfo, type ContractSummary } from "@/lib/api";
import { can, navFor, type Role } from "@/lib/permissions";
import { NavGlyph } from "./NavIcons";

const ITEM =
  "flex cursor-pointer items-center gap-3 rounded-md px-3 py-2 text-[13px] text-ink " +
  "data-[selected=true]:bg-hover";
const GROUP =
  "[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs " +
  "[&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted";

/** Ctrl/Cmd+K launcher: jump to any page the role may open, or run a quick
 * action. Only lists what the user is permitted to reach. */
export default function CommandPalette({
  role,
  open,
  onOpenChange,
  onSignOut,
}: {
  role: Role;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSignOut: () => void;
}) {
  const router = useRouter();
  const [contracts, setContracts] = useState<ContractSummary[]>([]);
  const [sessions, setSessions] = useState<ChatSessionInfo[]>([]);

  // Load the searchable records each time the palette opens.
  useEffect(() => {
    if (!open) return;
    getContracts().then(setContracts).catch(() => {});
    getChatSessions().then(setSessions).catch(() => {});
  }, [open]);

  function go(href: string) {
    onOpenChange(false);
    router.push(href);
  }

  return (
    <Command.Dialog
      open={open}
      onOpenChange={onOpenChange}
      label="Command palette"
      overlayClassName="overlay-in fixed inset-0 z-50 bg-ink/30"
      contentClassName="popover-in fixed left-1/2 top-[18%] z-50 w-[36rem] max-w-[calc(100vw-2rem)] -translate-x-1/2 overflow-hidden rounded-xl border border-line bg-surface shadow-lg"
    >
      <div className="flex items-center gap-3 border-b border-line px-4">
        <Search className="h-4 w-4 shrink-0 text-faint" aria-hidden />
        <Command.Input
          placeholder="Search pages and actions…"
          className="h-12 w-full bg-transparent text-sm text-ink placeholder:text-faint focus:outline-none focus-visible:outline-none"
        />
        <kbd className="hidden rounded border border-line px-1.5 py-0.5 text-[11px] text-muted sm:block">
          Esc
        </kbd>
      </div>
      <Command.List className="max-h-80 overflow-y-auto p-2">
        <Command.Empty className="px-3 py-8 text-center text-[13px] text-muted">
          No matching pages or actions.
        </Command.Empty>

        <Command.Group heading="Go to" className={GROUP}>
          {navFor(role).map((item) => (
            <Command.Item
              key={item.href}
              value={`${item.label} ${item.keywords ?? ""}`}
              onSelect={() => go(item.href)}
              className={ITEM}
            >
              <NavGlyph icon={item.icon} className="h-4 w-4 text-faint" />
              {item.label}
            </Command.Item>
          ))}
        </Command.Group>

        {contracts.length > 0 && (
          <Command.Group heading="Contracts" className={GROUP}>
            {contracts.slice(0, 30).map((c) => (
              <Command.Item
                key={c.contract_id}
                value={`contract ${c.filename} ${c.contract_id}`}
                onSelect={() => go(`/contracts/${c.contract_id}`)}
                className={ITEM}
              >
                <FileText className="h-4 w-4 text-faint" aria-hidden />
                <span className="truncate">{c.filename}</span>
              </Command.Item>
            ))}
          </Command.Group>
        )}

        {sessions.length > 0 && (
          <Command.Group heading="Conversations" className={GROUP}>
            {sessions.slice(0, 20).map((s) => (
              <Command.Item
                key={s.id}
                value={`conversation ${s.title} ${s.id}`}
                onSelect={() => go(`/ask?session=${s.id}`)}
                className={ITEM}
              >
                <MessageSquare className="h-4 w-4 text-faint" aria-hidden />
                <span className="truncate">{s.title}</span>
              </Command.Item>
            ))}
          </Command.Group>
        )}

        <Command.Group heading="Actions" className={GROUP}>
          {can(role, "contracts.upload") && (
            <Command.Item
              value="Upload a contract scan detect"
              onSelect={() => go("/detect")}
              className={ITEM}
            >
              <Upload className="h-4 w-4 text-faint" aria-hidden />
              Upload a contract
            </Command.Item>
          )}
          <Command.Item
            value="Sign out log out"
            onSelect={() => {
              onOpenChange(false);
              onSignOut();
            }}
            className={ITEM}
          >
            <LogOut className="h-4 w-4 text-faint" aria-hidden />
            Sign out
          </Command.Item>
        </Command.Group>
      </Command.List>
    </Command.Dialog>
  );
}

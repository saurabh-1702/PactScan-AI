"use client";

import { ChevronDown, LogOut } from "lucide-react";
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSeparator, MenuTrigger } from "@/components/ui/Overlay";
import { ROLE_LABELS, type Role } from "@/lib/permissions";

export default function UserMenu({ role, onSignOut }: { role: Role; onSignOut: () => void }) {
  return (
    <Menu>
      <MenuTrigger asChild>
        <button
          type="button"
          className="inline-flex h-9 items-center gap-2 rounded-md pl-1 pr-2 text-[13px] font-medium text-ink hover:bg-hover"
        >
          <span
            aria-hidden
            className="flex h-7 w-7 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-accent-strong"
          >
            {ROLE_LABELS[role].charAt(0)}
          </span>
          <span className="hidden sm:inline">{ROLE_LABELS[role]}</span>
          <ChevronDown className="h-3.5 w-3.5 text-faint" aria-hidden />
        </button>
      </MenuTrigger>
      <MenuContent>
        <MenuLabel>Signed in as {ROLE_LABELS[role]}</MenuLabel>
        <MenuSeparator />
        <MenuItem onSelect={onSignOut}>
          <LogOut className="h-4 w-4 text-faint" aria-hidden />
          Sign out
        </MenuItem>
      </MenuContent>
    </Menu>
  );
}

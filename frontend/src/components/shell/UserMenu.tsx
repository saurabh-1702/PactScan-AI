"use client";

import { ChevronDown, LogOut } from "lucide-react";
import { useEffect, useState } from "react";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/Overlay";
import { getMe, type MeInfo } from "@/lib/api";
import { ROLE_LABELS, type Role } from "@/lib/permissions";

export default function UserMenu({ role, onSignOut }: { role: Role; onSignOut: () => void }) {
  const [me, setMe] = useState<MeInfo | null>(null);

  useEffect(() => {
    getMe()
      .then(setMe)
      .catch(() => {
        /* the menu still works from the role alone */
      });
  }, []);

  const initial = (me?.email ?? ROLE_LABELS[role]).charAt(0).toUpperCase();

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
            {initial}
          </span>
          <span className="hidden sm:inline">{ROLE_LABELS[role]}</span>
          <ChevronDown className="h-3.5 w-3.5 text-faint" aria-hidden />
        </button>
      </MenuTrigger>
      <MenuContent className="min-w-64">
        <div className="px-2.5 py-2">
          <p className="truncate text-[13px] font-medium text-ink">{me?.email ?? "Signed in"}</p>
          <p className="text-xs text-muted">
            {ROLE_LABELS[role]}
            {me?.tenant_name ? ` · ${me.tenant_name}` : ""}
          </p>
        </div>
        <MenuSeparator />
        <MenuItem onSelect={onSignOut}>
          <LogOut className="h-4 w-4 text-faint" aria-hidden />
          Sign out
        </MenuItem>
      </MenuContent>
    </Menu>
  );
}

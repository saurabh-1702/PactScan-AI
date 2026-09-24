"use client";

import * as Tooltip from "@radix-ui/react-tooltip";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { cn } from "./cn";

export function TooltipProvider({ children }: { children: React.ReactNode }) {
  return (
    <Tooltip.Provider delayDuration={300} skipDelayDuration={100}>
      {children}
    </Tooltip.Provider>
  );
}

export function Hint({
  label,
  side = "bottom",
  children,
}: {
  label: string;
  side?: "top" | "right" | "bottom" | "left";
  children: React.ReactNode;
}) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          side={side}
          sideOffset={6}
          className="popover-in z-50 rounded-md bg-ink px-2 py-1 text-xs font-medium text-white shadow-md"
        >
          {label}
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

export const Menu = DropdownMenu.Root;
export const MenuTrigger = DropdownMenu.Trigger;

export function MenuContent({
  children,
  className,
  align = "end",
}: {
  children: React.ReactNode;
  className?: string;
  align?: "start" | "center" | "end";
}) {
  return (
    <DropdownMenu.Portal>
      <DropdownMenu.Content
        align={align}
        sideOffset={6}
        className={cn(
          "popover-in z-50 min-w-52 rounded-lg border border-line bg-surface p-1 shadow-md",
          className,
        )}
      >
        {children}
      </DropdownMenu.Content>
    </DropdownMenu.Portal>
  );
}

export function MenuItem({
  children,
  onSelect,
  danger,
}: {
  children: React.ReactNode;
  onSelect?: () => void;
  danger?: boolean;
}) {
  return (
    <DropdownMenu.Item
      onSelect={onSelect}
      className={cn(
        "flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] outline-none",
        "data-[highlighted]:bg-hover",
        danger ? "text-danger-ink" : "text-ink",
      )}
    >
      {children}
    </DropdownMenu.Item>
  );
}

export function MenuLabel({ children }: { children: React.ReactNode }) {
  return (
    <DropdownMenu.Label className="px-2.5 py-1.5 text-xs text-muted">{children}</DropdownMenu.Label>
  );
}

export function MenuSeparator() {
  return <DropdownMenu.Separator className="my-1 h-px bg-line" />;
}

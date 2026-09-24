"use client";

import * as RadixTabs from "@radix-ui/react-tabs";
import { cn } from "./cn";

export const Tabs = RadixTabs.Root;

export function TabList({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <RadixTabs.List
      aria-label={label}
      className="mb-5 flex gap-1 overflow-x-auto shadow-[inset_0_-1px_0_var(--color-line)]"
    >
      {children}
    </RadixTabs.List>
  );
}

export function Tab({
  value,
  children,
  count,
}: {
  value: string;
  children: React.ReactNode;
  count?: number;
}) {
  return (
    <RadixTabs.Trigger
      value={value}
      className={cn(
        "relative flex items-center gap-2 whitespace-nowrap border-b-2 border-transparent px-3 py-2.5 text-[13px] font-medium text-muted",
        "transition-colors duration-150 hover:text-ink",
        "data-[state=active]:border-accent data-[state=active]:text-ink",
      )}
    >
      {children}
      {count !== undefined && (
        <span className="rounded-full bg-sunken px-1.5 text-xs font-medium leading-5 text-muted">
          {count}
        </span>
      )}
    </RadixTabs.Trigger>
  );
}

export function TabPanel({ value, children }: { value: string; children: React.ReactNode }) {
  return (
    <RadixTabs.Content value={value} className="page-in focus-visible:outline-none">
      {children}
    </RadixTabs.Content>
  );
}

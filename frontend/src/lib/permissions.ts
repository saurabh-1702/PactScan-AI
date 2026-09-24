/**
 * Centralised role/permission model — the ONE place that says who may see or do
 * what in the UI. Navigation, route guards and action buttons all read from
 * here, so a role change is a one-line edit rather than a hunt through pages.
 *
 * This only shapes the interface. The backend re-checks every request
 * (require_role / ownership scoping) and stays the real security boundary.
 */

export type Role = "end_user" | "reviewer" | "admin";

export type Permission =
  | "contracts.upload" // run Detect / attach a file in Ask
  | "drafts.create" // draft + submit a redline
  | "approvals.review" // see the approval queue, approve / edit / reject
  | "restore.request" // ask for an older version to be restored
  | "restore.decide" // approve / reject restore requests
  | "horizon.view" // read the regulatory-update log
  | "horizon.trigger" // simulate / run a horizon scan
  | "portfolio.viewAll"; // see every contract in the tenant, not just own

const GRANTS: Record<Role, readonly Permission[]> = {
  end_user: ["contracts.upload", "drafts.create", "restore.request", "horizon.view"],
  reviewer: [
    "contracts.upload",
    "drafts.create",
    "approvals.review",
    "restore.request",
    "restore.decide",
    "horizon.view",
    "portfolio.viewAll",
  ],
  admin: [
    "contracts.upload",
    "drafts.create",
    "approvals.review",
    "restore.request",
    "restore.decide",
    "horizon.view",
    "horizon.trigger",
    "portfolio.viewAll",
  ],
};

export const ROLE_LABELS: Record<Role, string> = {
  end_user: "Legal User",
  reviewer: "Reviewer",
  admin: "Administrator",
};

export function can(role: Role | null | undefined, permission: Permission): boolean {
  return !!role && GRANTS[role].includes(permission);
}

/** Route → permission needed. Longest matching prefix wins; a route not listed
 * here only needs a signed-in user. */
const ROUTE_RULES: { prefix: string; permission: Permission }[] = [
  { prefix: "/approvals", permission: "approvals.review" },
  { prefix: "/horizon-scanning", permission: "horizon.view" },
];

export function canAccessRoute(role: Role | null | undefined, pathname: string): boolean {
  if (!role) return false;
  const rule = [...ROUTE_RULES]
    .sort((a, b) => b.prefix.length - a.prefix.length)
    .find((r) => pathname === r.prefix || pathname.startsWith(r.prefix + "/"));
  return !rule || can(role, rule.permission);
}

export type NavIcon = "dashboard" | "detect" | "ask" | "drafts" | "approvals" | "horizon";

export interface NavItem {
  href: string;
  label: string;
  icon: NavIcon;
  /** Extra search words for the command palette. */
  keywords?: string;
  permission?: Permission;
}

const NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: "dashboard", keywords: "home overview" },
  {
    href: "/detect",
    label: "Detect",
    icon: "detect",
    keywords: "upload scan contract compliance",
    permission: "contracts.upload",
  },
  { href: "/ask", label: "Ask", icon: "ask", keywords: "chat question assistant" },
  {
    href: "/my-drafts",
    label: "My Drafts",
    icon: "drafts",
    keywords: "suggestions edits submitted",
    permission: "drafts.create",
  },
  {
    href: "/approvals",
    label: "Approvals",
    icon: "approvals",
    keywords: "review queue restore",
    permission: "approvals.review",
  },
  {
    href: "/horizon-scanning",
    label: "Horizon Scanning",
    icon: "horizon",
    keywords: "regulation updates changes",
    permission: "horizon.view",
  },
];

export function navFor(role: Role | null | undefined): NavItem[] {
  return NAV.filter((n) => !n.permission || can(role, n.permission));
}

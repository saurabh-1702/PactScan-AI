"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getCurrentUser } from "@/lib/auth";

// Routes that need more than just "logged in". An end_user reaching one of
// these (via a link, a typed URL, or a stale bookmark) is bounced to the
// dashboard rather than shown a page full of buttons the API will 403 anyway.
const ROUTE_ROLES: { prefix: string; roles: string[] }[] = [
  { prefix: "/approvals", roles: ["reviewer", "admin"] },
  { prefix: "/admin", roles: ["admin"] },
];

/** Redirects to /login when no valid JWT is present, for every page except
 * /login itself, and to /dashboard when the user's role isn't allowed on the
 * route. Client-side only, matching this project's demo scope — the actual
 * security boundary is the backend's own require_role() on every
 * state-changing endpoint, which holds regardless of what this does. */
export default function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setReady(false);
    if (pathname === "/login") {
      setReady(true);
      return;
    }
    const user = getCurrentUser();
    if (!user) {
      router.replace("/login");
      return;
    }
    const rule = ROUTE_ROLES.find((r) => pathname?.startsWith(r.prefix));
    if (rule && !rule.roles.includes(user.role)) {
      router.replace("/dashboard");
      return;
    }
    setReady(true);
  }, [pathname, router]);

  if (!ready) return null;
  return <>{children}</>;
}

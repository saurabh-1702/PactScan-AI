"use client";

import { createContext, useContext } from "react";
import type { DecodedToken } from "@/lib/auth";
import { can, type Permission, type Role } from "@/lib/permissions";

/** The signed-in user, provided by AppShell once the route guard has passed.
 * Pages read the role from here instead of decoding the token themselves. */
const SessionContext = createContext<DecodedToken | null>(null);

export const SessionProvider = SessionContext.Provider;

export function useSession(): { user: DecodedToken; role: Role; can: (p: Permission) => boolean } {
  const user = useContext(SessionContext);
  if (!user) throw new Error("useSession must be used inside a signed-in page");
  return { user, role: user.role, can: (p) => can(user.role, p) };
}

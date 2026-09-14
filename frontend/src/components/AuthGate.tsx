"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getCurrentUser } from "@/lib/auth";

/** Redirects to /login when no valid JWT is present, for every page except
 * /login itself. Client-side only, matching this project's demo scope — a
 * real deployment would also enforce this server-side. */
export default function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (pathname === "/login") {
      setReady(true);
      return;
    }
    const user = getCurrentUser();
    if (!user) {
      router.replace("/login");
      return;
    }
    setReady(true);
  }, [pathname, router]);

  if (!ready) return null;
  return <>{children}</>;
}

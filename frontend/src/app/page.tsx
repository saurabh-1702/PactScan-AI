"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** The app's real home is the dashboard — the app shell has already confirmed a
 * valid session by the time this renders, so just forward there. */
export default function Home() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/dashboard");
  }, [router]);

  return null;
}

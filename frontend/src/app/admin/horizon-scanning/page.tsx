"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** The page moved to /horizon-scanning (it is now readable by every role);
 * this keeps old bookmarks and links working. */
export default function LegacyHorizonScanningRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/horizon-scanning");
  }, [router]);
  return null;
}

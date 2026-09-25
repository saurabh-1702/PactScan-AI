"use client";

import { ChevronDown, Download } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/Overlay";
import { useToast } from "@/components/ui/Toast";

export type DownloadFormat = "clean" | "redline";

/** Every document download offers both kinds: the CLEAN copy (all changes
 * accepted — the contract as it would be signed or sent) and the REDLINE copy
 * (old wording struck through, new wording underlined — what a reviewer
 * checks). The caller says how to fetch each; errors surface as a toast. */
export default function DownloadMenu({
  onDownload,
  label = "Download",
  variant = "secondary",
  size = "sm",
}: {
  onDownload: (format: DownloadFormat) => Promise<void>;
  label?: string;
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md";
}) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  async function run(format: DownloadFormat) {
    setBusy(true);
    try {
      await onDownload(format);
    } catch (err) {
      toast.error(`Download failed: ${err instanceof Error ? err.message : "unknown error"}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Menu>
      <MenuTrigger asChild>
        <Button variant={variant} size={size} loading={busy}>
          {!busy && <Download className="h-3.5 w-3.5" aria-hidden />}
          {label}
          <ChevronDown className="h-3.5 w-3.5 opacity-70" aria-hidden />
        </Button>
      </MenuTrigger>
      <MenuContent className="min-w-72">
        <MenuItem onSelect={() => run("clean")}>
          <span>
            <span className="block font-medium text-ink">Clean copy</span>
            <span className="block text-xs text-muted">All changes accepted — ready to sign or send</span>
          </span>
        </MenuItem>
        <MenuItem onSelect={() => run("redline")}>
          <span>
            <span className="block font-medium text-ink">Redline copy</span>
            <span className="block text-xs text-muted">Old wording struck through, new underlined</span>
          </span>
        </MenuItem>
      </MenuContent>
    </Menu>
  );
}

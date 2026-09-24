"use client";

import { FileText, UploadCloud, X } from "lucide-react";
import { useRef, useState } from "react";
import { cn } from "@/components/ui/cn";

const ACCEPT = ".pdf,.docx,.doc,.txt";
const ALLOWED = [".pdf", ".docx", ".doc", ".txt"];

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Drag-and-drop or click-to-browse file picker for a contract. */
export default function DropZone({
  file,
  onFile,
  disabled,
  onReject,
}: {
  file: File | null;
  onFile: (f: File | null) => void;
  disabled?: boolean;
  onReject?: (message: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  function take(f: File | undefined | null) {
    if (!f) return;
    const ok = ALLOWED.some((ext) => f.name.toLowerCase().endsWith(ext));
    if (!ok) {
      onReject?.(`“${f.name}” isn't a supported file. Use PDF, Word (.docx, .doc) or text.`);
      return;
    }
    onFile(f);
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (!disabled) take(e.dataTransfer.files?.[0]);
      }}
      className={cn(
        "rounded-lg border border-dashed px-5 py-8 text-center transition-colors duration-150",
        over ? "border-accent bg-accent-soft" : "border-line-strong bg-surface",
        disabled && "opacity-60",
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="sr-only"
        tabIndex={-1}
        onChange={(e) => {
          take(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      {file ? (
        <div className="mx-auto flex max-w-md items-center gap-3 rounded-md border border-line bg-canvas px-3 py-2.5 text-left">
          <FileText className="h-5 w-5 shrink-0 text-accent" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-medium text-ink">{file.name}</p>
            <p className="text-xs text-muted">{formatSize(file.size)}</p>
          </div>
          {!disabled && (
            <button
              type="button"
              aria-label="Remove file"
              onClick={() => onFile(null)}
              className="flex h-7 w-7 items-center justify-center rounded-md text-muted hover:bg-hover hover:text-ink"
            >
              <X className="h-4 w-4" aria-hidden />
            </button>
          )}
        </div>
      ) : (
        <>
          <UploadCloud className="mx-auto h-7 w-7 text-faint" aria-hidden />
          <p className="mt-2 text-[13px] text-ink">
            Drag a contract here, or{" "}
            <button
              type="button"
              disabled={disabled}
              onClick={() => inputRef.current?.click()}
              className="font-medium text-accent underline underline-offset-2 hover:text-accent-strong"
            >
              browse your files
            </button>
          </p>
          <p className="mt-1 text-xs text-muted">PDF, Word or text — a vendor DPA, MSA or SOW.</p>
        </>
      )}
    </div>
  );
}

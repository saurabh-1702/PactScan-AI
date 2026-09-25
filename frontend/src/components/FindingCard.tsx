"use client";

import { ChevronDown, Wand2 } from "lucide-react";
import { useState } from "react";
import DraftSubmitPanel from "@/components/DraftSubmitPanel";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Feedback";
import { SEVERITY_DOT, SeverityLabel } from "@/components/ui/Severity";
import { cn } from "@/components/ui/cn";
import { useProcesses } from "@/components/shell/Processes";
import { postSuggestFromFinding, type Finding, type SuggestResult } from "@/lib/api";
import { humanize } from "@/lib/format";

/** One compliance finding, with the "draft a fix" flow attached. Used on the
 * Detect results and on the contract page, so the two behave identically. */
export default function FindingCard({ finding: f }: { finding: Finding }) {
  const { track } = useProcesses();
  const [suggestion, setSuggestion] = useState<SuggestResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notesOpen, setNotesOpen] = useState(false);

  async function onSuggest() {
    setBusy(true);
    setError(null);
    try {
      setSuggestion(await track("Drafting a fix", postSuggestFromFinding(f.finding_id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  const hasNotes = !!(suggestion?.judge || suggestion?.negotiation);

  return (
    <li className="relative rounded-lg border border-line bg-surface p-4 pl-5 shadow-sm">
      <span
        aria-hidden
        className={cn("absolute inset-y-3 left-0 w-[3px] rounded-r-full", SEVERITY_DOT[f.severity])}
      />
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <SeverityLabel severity={f.severity} />
        <span className="text-xs text-muted">
          {humanize(f.clause_type)} · page {f.page_number}
          {f.section_header ? ` · ${f.section_header}` : ""}
        </span>
        {f.override_chain.length > 1 && (
          <span className="rounded-full bg-sunken px-2 py-0.5 text-xs text-muted">
            Overridden across {f.override_chain.length} clauses
          </span>
        )}
      </div>

      <p className="mt-2 text-sm font-medium text-ink">{f.rule_or_regulation_violated}</p>
      <p className="mt-1 text-[13px] leading-relaxed text-muted">{f.explanation}</p>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button size="sm" onClick={onSuggest} loading={busy}>
          {!busy && <Wand2 className="h-3.5 w-3.5" aria-hidden />}
          {busy ? "Drafting a fix" : suggestion ? "Draft another fix" : "Draft a fix"}
        </Button>
        <span className="text-xs text-muted">Confidence: {f.confidence}</span>
      </div>

      {error && (
        <Alert tone="danger" className="mt-3">
          {error}
        </Alert>
      )}

      {suggestion && (
        <div>
          <DraftSubmitPanel
            key={suggestion.suggestion_id}
            suggestionId={suggestion.suggestion_id}
            aiDraft={suggestion.proposed_text}
            rationale={`${suggestion.rationale} (confidence ${suggestion.confidence})`}
            onDiscarded={() => setSuggestion(null)}
          />
          {hasNotes && (
            <div className="mt-3">
              <button
                type="button"
                onClick={() => setNotesOpen((v) => !v)}
                aria-expanded={notesOpen}
                className="flex items-center gap-1.5 text-xs font-medium text-muted hover:text-ink"
              >
                <ChevronDown
                  className={cn("h-3.5 w-3.5 transition-transform", notesOpen && "rotate-180")}
                  aria-hidden
                />
                Review notes — adversarial check and negotiation fallback
              </button>
              {notesOpen && (
                <div className="mt-2 space-y-2.5 rounded-md bg-canvas p-3 text-[13px] text-muted">
                  {suggestion.judge && (
                    <p>
                      <span className="font-semibold text-ink">
                        Adversarial review — {suggestion.judge.verdict}:{" "}
                      </span>
                      {suggestion.judge.reasoning}
                    </p>
                  )}
                  {suggestion.negotiation && (
                    <>
                      <p>
                        <span className="font-semibold text-ink">Likely pushback: </span>
                        {suggestion.negotiation.predicted_pushback}
                      </p>
                      <p>
                        <span className="font-semibold text-ink">Fallback wording: </span>
                        {suggestion.negotiation.fallback_clause_text}
                      </p>
                    </>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </li>
  );
}

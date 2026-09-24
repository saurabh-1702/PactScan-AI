"use client";

import Link from "next/link";
import { FileText, Loader2, MessageSquare, Paperclip, Plus, SendHorizontal, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import DraftSubmitPanel from "@/components/DraftSubmitPanel";
import { Alert, Badge } from "@/components/ui/Feedback";
import { Select } from "@/components/ui/Field";
import { StageProgress } from "@/components/ui/StageProgress";
import { cn } from "@/components/ui/cn";
import {
  clearActiveDocument,
  getChatMessages,
  getChatSessions,
  getMyDraft,
  newJobId,
  postAsk,
  postAskAttach,
  type AskResponseType,
  type AskSourceInfo,
  type ChatSessionInfo,
  type DraftInfo,
} from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { useJobProgress } from "@/lib/hooks";

interface DisplayMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  responseType?: AskResponseType | null;
  sources?: AskSourceInfo[];
  suggestionId?: string | null;
  attachment?: string;
}

const TYPE_LABELS: Record<AskResponseType, string> = {
  contract_answer: "From your contracts",
  status_answer: "Compliance status",
  edit_draft: "Drafted edit",
  general_info: "General guidance — not from your documents",
  out_of_scope: "Outside what I can help with",
  abstained: "Not enough to answer",
  rate_limited: "Slow down",
  file_attached: "Document added",
};

const SUGGESTED = [
  "Which of my contracts mention breach notification?",
  "What compliance issues were detected in my contracts?",
  "What does the DPDP Act require from a data processor?",
];

/** The drafted edit for an Ask edit-instruction: still a draft -> preview, edit
 * and submit right here; already submitted -> just its status. */
function AskDraft({ suggestionId }: { suggestionId: string }) {
  const [draft, setDraft] = useState<DraftInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMyDraft(suggestionId)
      .then(setDraft)
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load the draft"));
  }, [suggestionId]);

  if (error) return <p className="mt-2 text-xs text-danger-ink">{error}</p>;
  if (!draft) return <p className="mt-2 text-xs text-muted">Loading draft…</p>;
  if (draft.status === "draft") {
    return (
      <DraftSubmitPanel
        suggestionId={draft.suggestion_id}
        aiDraft={draft.ai_draft_text}
        rationale={draft.rationale}
      />
    );
  }
  return (
    <p className="mt-2 text-[13px] text-muted">
      Status: <span className="font-medium text-ink">{draft.status}</span>.{" "}
      <Link href="/my-drafts" className="font-medium text-accent hover:underline">
        Track it in My Drafts
      </Link>
    </p>
  );
}

function Evidence({ sources }: { sources: AskSourceInfo[] }) {
  const quoted = sources.filter((s) => s.excerpt);
  const cited = sources.filter((s) => !s.excerpt);
  return (
    <div className="mt-3 space-y-2">
      {quoted.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">Evidence</p>
          <ul className="mt-1.5 space-y-2">
            {quoted.map((s, i) => (
              <li key={i} className="rounded-md border-l-[3px] border-l-accent/60 bg-canvas py-2 pl-3 pr-3">
                <blockquote className="text-[13px] italic leading-relaxed text-ink">
                  “{s.excerpt}”
                </blockquote>
                <p className="mt-1 text-xs text-muted">
                  {s.document_name}
                  {s.page_number > 0 ? ` · page ${s.page_number}` : ""}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
      {cited.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted">Sources</span>
          {cited.map((s, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 rounded-full border border-line bg-surface px-2 py-0.5 text-xs text-muted"
            >
              <FileText className="h-3 w-3" aria-hidden />
              {s.document_name}
              {s.page_number > 0 ? ` · p.${s.page_number}` : ""}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function AskView() {
  const params = useSearchParams();
  const requestedSession = params.get("session");

  const [sessions, setSessions] = useState<ChatSessionInfo[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attaching, setAttaching] = useState<{ name: string; jobId: string } | null>(null);
  const [activeDoc, setActiveDoc] = useState<{ id: string; name: string } | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const areaRef = useRef<HTMLTextAreaElement>(null);
  const attachProgress = useJobProgress(attaching?.jobId ?? null);

  const loadSessions = useCallback(async (): Promise<ChatSessionInfo[]> => {
    try {
      const list = await getChatSessions();
      setSessions(list);
      return list;
    } catch {
      return [];
    }
  }, []);

  const openSession = useCallback(async (id: string, known?: ChatSessionInfo[]) => {
    setSessionId(id);
    setError(null);
    const s = (known ?? []).find((x) => x.id === id);
    setActiveDoc(
      s?.active_contract_id ? { id: s.active_contract_id, name: s.active_filename ?? s.active_contract_id } : null,
    );
    try {
      const history = await getChatMessages(id);
      setMessages(
        history.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          responseType: m.response_type,
          sources: m.sources,
          suggestionId: m.suggestion_id,
        })),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load that conversation");
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    getChatSessions()
      .then((list) => {
        if (cancelled) return;
        setSessions(list);
        if (requestedSession && list.some((s) => s.id === requestedSession)) {
          openSession(requestedSession, list);
        }
      })
      .catch(() => {
        /* non-fatal — the sidebar just stays empty */
      });
    return () => {
      cancelled = true;
    };
  }, [openSession, requestedSession]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, sending, attaching]);

  function startNewChat() {
    setSessionId(null);
    setMessages([]);
    setActiveDoc(null);
    setError(null);
    areaRef.current?.focus();
  }

  async function send(text: string) {
    const message = text.trim();
    if (!message || sending || attaching) return;
    setInput("");
    if (areaRef.current) areaRef.current.style.height = "auto";
    setError(null);
    setMessages((prev) => [...prev, { id: `local-${Date.now()}`, role: "user", content: message }]);
    setSending(true);
    try {
      const res = await postAsk(message, sessionId);
      setSessionId(res.session_id);
      setMessages((prev) => [
        ...prev,
        {
          id: `local-${Date.now()}-a`,
          role: "assistant",
          content: res.answer_text,
          responseType: res.type,
          sources: res.sources,
          suggestionId: res.suggestion_id,
        },
      ]);
      loadSessions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setSending(false);
    }
  }

  async function onAttach(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || attaching || sending) return;
    setError(null);
    const jobId = newJobId();
    setAttaching({ name: file.name, jobId });
    setMessages((prev) => [
      ...prev,
      { id: `local-${Date.now()}`, role: "user", content: "", attachment: file.name },
    ]);
    try {
      const res = await postAskAttach(file, sessionId, jobId);
      setSessionId(res.session_id);
      if (res.contract_id) setActiveDoc({ id: res.contract_id, name: file.name });
      setMessages((prev) => [
        ...prev,
        { id: `local-${Date.now()}-a`, role: "assistant", content: res.answer_text, responseType: res.type },
      ]);
      loadSessions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not attach that file");
    } finally {
      setAttaching(null);
    }
  }

  async function onDetach() {
    if (!sessionId) return;
    try {
      await clearActiveDocument(sessionId);
      setActiveDoc(null);
      loadSessions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not detach the document");
    }
  }

  const busy = sending || !!attaching;
  const empty = messages.length === 0;

  return (
    <div className="flex min-h-0 flex-1">
      {/* Conversations */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-line bg-surface md:flex">
        <div className="flex items-center justify-between px-4 py-3">
          <h2 className="text-[13px] font-semibold text-ink">Conversations</h2>
          <button
            type="button"
            onClick={startNewChat}
            aria-label="New chat"
            className="flex h-7 w-7 items-center justify-center rounded-md text-muted hover:bg-hover hover:text-ink"
          >
            <Plus className="h-4 w-4" aria-hidden />
          </button>
        </div>
        <ul className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
          {sessions.length === 0 && (
            <li className="px-2 py-2 text-xs text-muted">Your conversations will be listed here.</li>
          )}
          {sessions.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => openSession(s.id, sessions)}
                aria-current={s.id === sessionId ? "true" : undefined}
                className={cn(
                  "block w-full rounded-md px-2.5 py-2 text-left",
                  s.id === sessionId ? "bg-accent-soft" : "hover:bg-hover",
                )}
              >
                <span className="block truncate text-[13px] font-medium text-ink">{s.title}</span>
                <span className="block text-xs text-muted">{timeAgo(s.updated_at)}</span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      {/* Thread */}
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-line bg-surface px-4 py-2.5 md:hidden">
          <Select
            aria-label="Conversations"
            className="min-w-0 flex-1"
            value={sessionId ?? ""}
            onChange={(e) => (e.target.value ? openSession(e.target.value, sessions) : startNewChat())}
          >
            <option value="">New chat</option>
            {sessions.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title}
              </option>
            ))}
          </Select>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto" role="log" aria-live="polite" aria-label="Conversation">
          <div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6">
            {empty && (
              <div className="page-in pt-6">
                <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent-soft text-accent">
                  <MessageSquare className="h-5 w-5" aria-hidden />
                </span>
                <h1 className="mt-4 text-xl font-semibold tracking-tight text-ink">
                  Ask about your contracts
                </h1>
                <p className="mt-1 max-w-xl text-[13px] text-muted">
                  Questions about your portfolio, its compliance status, or legal-tech topics. Answers
                  quote the contract they come from — or say plainly when there isn&apos;t enough to go on.
                  Attach a contract to ask about it directly.
                </p>
                <ul className="mt-5 space-y-2">
                  {SUGGESTED.map((q) => (
                    <li key={q}>
                      <button
                        type="button"
                        onClick={() => send(q)}
                        className="w-full rounded-lg border border-line bg-surface px-4 py-3 text-left text-[13px] text-ink shadow-sm transition-colors hover:border-line-strong hover:bg-hover"
                      >
                        {q}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <ul className="space-y-6">
              {messages.map((m) =>
                m.role === "user" ? (
                  <li key={m.id} className="flex justify-end">
                    <div className="max-w-[85%] rounded-lg bg-sunken px-3.5 py-2.5 text-[13px] leading-relaxed text-ink">
                      {m.attachment ? (
                        <span className="inline-flex items-center gap-2">
                          <Paperclip className="h-3.5 w-3.5 text-muted" aria-hidden />
                          {m.attachment}
                        </span>
                      ) : (
                        <p className="whitespace-pre-wrap">{m.content}</p>
                      )}
                    </div>
                  </li>
                ) : (
                  <li key={m.id} className="max-w-[92%]">
                    {m.responseType && (
                      <p className="mb-1 text-xs font-medium text-muted">{TYPE_LABELS[m.responseType]}</p>
                    )}
                    {m.responseType === "rate_limited" ? (
                      <Alert tone="warn">{m.content}</Alert>
                    ) : (
                      <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink">{m.content}</p>
                    )}
                    {!!m.sources?.length && <Evidence sources={m.sources} />}
                    {m.responseType === "edit_draft" && m.suggestionId && <AskDraft suggestionId={m.suggestionId} />}
                  </li>
                ),
              )}

              {sending && (
                <li className="flex items-center gap-2 text-[13px] text-muted">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> Looking through your contracts…
                </li>
              )}
              {attaching && (
                <li className="max-w-sm rounded-lg border border-line bg-surface p-4">
                  <p className="mb-3 text-[13px] font-medium text-ink">
                    Analysing {attaching.name}
                  </p>
                  {attachProgress ? (
                    <StageProgress stages={attachProgress.stages} />
                  ) : (
                    <p className="text-[13px] text-muted">Starting…</p>
                  )}
                </li>
              )}
            </ul>
            <div ref={bottomRef} />
          </div>
        </div>

        <div className="border-t border-line bg-surface">
          <div className="mx-auto w-full max-w-3xl px-4 py-3 sm:px-6">
            {error && (
              <Alert tone="danger" className="mb-3">
                {error}
              </Alert>
            )}
            {activeDoc && !attaching && (
              <div className="mb-2 inline-flex max-w-full items-center gap-2 rounded-full bg-accent-soft py-1 pl-3 pr-1.5 text-xs text-accent-strong">
                <FileText className="h-3.5 w-3.5 shrink-0" aria-hidden />
                <span className="truncate">
                  Asking about <span className="font-semibold">{activeDoc.name}</span>
                </span>
                <button
                  type="button"
                  onClick={onDetach}
                  aria-label="Stop asking about this document"
                  className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full hover:bg-accent/10"
                >
                  <X className="h-3.5 w-3.5" aria-hidden />
                </button>
              </div>
            )}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                send(input);
              }}
              className="flex items-end gap-2 rounded-lg border border-line-strong bg-surface p-1.5 focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/20"
            >
              <input
                ref={fileRef}
                type="file"
                accept=".pdf,.docx,.doc,.txt"
                onChange={onAttach}
                className="sr-only"
                tabIndex={-1}
              />
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                disabled={busy}
                aria-label="Attach a contract"
                title="Attach a contract to ask about it"
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-muted hover:bg-hover hover:text-ink disabled:opacity-40"
              >
                <Paperclip className="h-[18px] w-[18px]" aria-hidden />
              </button>
              <textarea
                ref={areaRef}
                rows={1}
                value={input}
                aria-label="Your question"
                onChange={(e) => {
                  setInput(e.target.value);
                  e.target.style.height = "auto";
                  e.target.style.height = `${Math.min(e.target.scrollHeight, 144)}px`;
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send(input);
                  }
                }}
                placeholder={activeDoc ? `Ask about ${activeDoc.name}…` : "Ask about your contracts…"}
                className="max-h-36 min-h-9 flex-1 resize-none bg-transparent px-2 py-2 text-sm text-ink placeholder:text-faint focus:outline-none"
              />
              <button
                type="submit"
                disabled={busy || !input.trim()}
                aria-label="Send"
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-accent text-white transition-colors hover:bg-accent-strong disabled:opacity-40"
              >
                <SendHorizontal className="h-4 w-4" aria-hidden />
              </button>
            </form>
            <p className="mt-1.5 text-xs text-muted">
              Enter to send, Shift+Enter for a new line. <Badge>Not legal advice</Badge>
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}

export default function AskPage() {
  return (
    <Suspense fallback={null}>
      <AskView />
    </Suspense>
  );
}

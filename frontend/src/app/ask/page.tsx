"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  getChatMessages,
  getChatSessions,
  postAsk,
  type AskResponseType,
  type AskSourceInfo,
  type ChatSessionInfo,
} from "@/lib/api";

interface DisplayMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  responseType?: AskResponseType | null;
  sources?: AskSourceInfo[];
  suggestionId?: string | null;
  approvalId?: string | null;
}

const TYPE_LABELS: Record<AskResponseType, string> = {
  contract_answer: "Contract content",
  status_answer: "Compliance status",
  edit_draft: "Draft edit",
  general_info: "General legal-tech info",
  out_of_scope: "Out of scope",
  abstained: "I don't know",
};

const TYPE_STYLES: Record<AskResponseType, string> = {
  contract_answer: "bg-sky-100 text-sky-800",
  status_answer: "bg-violet-100 text-violet-800",
  edit_draft: "bg-emerald-100 text-emerald-800",
  general_info: "bg-neutral-200 text-neutral-700",
  out_of_scope: "bg-neutral-200 text-neutral-500",
  abstained: "bg-amber-100 text-amber-800",
};

export default function AskPage() {
  const [sessions, setSessions] = useState<ChatSessionInfo[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  async function loadSessions() {
    try {
      setSessions(await getChatSessions());
    } catch {
      /* non-fatal — sidebar just stays empty */
    }
  }

  useEffect(() => {
    loadSessions();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function openSession(id: string) {
    setSessionId(id);
    setError(null);
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
          approvalId: m.approval_id,
        })),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load conversation");
    }
  }

  function startNewChat() {
    setSessionId(null);
    setMessages([]);
    setError(null);
  }

  async function onSend(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setError(null);
    setMessages((prev) => [...prev, { id: `local-${Date.now()}`, role: "user", content: text }]);
    setSending(true);
    try {
      const res = await postAsk(text, sessionId);
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
          approvalId: res.approval_id,
        },
      ]);
      loadSessions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setSending(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-0 flex-1 max-w-5xl">
      <aside className="w-56 shrink-0 border-r border-neutral-200 p-3">
        <h2 className="text-sm font-semibold">Conversations</h2>
        <button
          type="button"
          onClick={startNewChat}
          className="mt-2 w-full rounded bg-neutral-900 px-2 py-1.5 text-xs font-semibold text-white"
        >
          + New chat
        </button>
        <ul className="mt-3 space-y-1 overflow-y-auto">
          {sessions.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => openSession(s.id)}
                className={`block w-full truncate rounded px-2 py-1.5 text-left text-xs ${
                  s.id === sessionId ? "bg-neutral-200 font-medium" : "hover:bg-neutral-100"
                }`}
                title={s.title}
              >
                {s.title}
                <span className="ml-1 text-neutral-400">({s.message_count})</span>
              </button>
            </li>
          ))}
          {sessions.length === 0 && (
            <li className="px-2 py-1.5 text-xs text-neutral-400">No conversations yet.</li>
          )}
        </ul>
      </aside>

      <section className="flex flex-1 flex-col">
        <header className="border-b border-neutral-200 p-4">
          <h1 className="text-lg font-semibold tracking-tight">PactScan AI — Ask</h1>
          <p className="text-xs text-neutral-500">
            Questions about your contract portfolio, its compliance status, or general
            legal-tech topics. Grounded, cited answers — or an honest &quot;I don&apos;t
            know&quot; when nothing supports one.
          </p>
        </header>

        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {messages.map((m) => (
            <div key={m.id} className={m.role === "user" ? "text-right" : "text-left"}>
              <div
                className={`inline-block max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                  m.role === "user" ? "bg-neutral-900 text-white" : "bg-neutral-100 text-neutral-900"
                }`}
              >
                {m.role === "assistant" && m.responseType && (
                  <span
                    className={`mb-1 inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${TYPE_STYLES[m.responseType]}`}
                  >
                    {TYPE_LABELS[m.responseType]}
                  </span>
                )}
                <p className="whitespace-pre-wrap">{m.content}</p>

                {!!m.sources?.length && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {m.sources.map((s, i) => (
                      <span
                        key={i}
                        className="rounded border border-neutral-300 bg-white px-1.5 py-0.5 text-[10px] text-neutral-600"
                      >
                        {s.document_name}
                        {s.page_number > 0 ? ` · p.${s.page_number}` : ""}
                      </span>
                    ))}
                  </div>
                )}

                {m.responseType === "edit_draft" && (
                  <Link
                    href="/approvals"
                    className="mt-2 block text-xs font-semibold text-emerald-700 underline"
                  >
                    → View this draft in the Approval Queue
                  </Link>
                )}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {error && (
          <p className="border-t border-red-300 bg-red-50 p-2 text-center text-xs text-red-800">
            {error}
          </p>
        )}

        <form onSubmit={onSend} className="flex gap-2 border-t border-neutral-200 p-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your contracts, compliance status, or legal-tech topics…"
            className="flex-1 rounded border border-neutral-300 px-3 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={sending || !input.trim()}
            className="rounded bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            {sending ? "…" : "Send"}
          </button>
        </form>
      </section>
    </main>
  );
}

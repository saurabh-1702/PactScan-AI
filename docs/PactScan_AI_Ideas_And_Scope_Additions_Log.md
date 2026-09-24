# PactScan AI — Ideas & Scope Additions Log

### A running record of features added beyond the literal phase prompts, and why

---

## Purpose of this document

This is not the phase prompts (see `Phase_0`–`Phase_7`) and not the bug/environment log
(see `PactScan_AI_Known_Issues_And_Lessons_Learned.md`). This tracks a third thing:
**ideas that came up mid-build, beyond what a phase prompt literally asked for**, and
were deliberately built in anyway. Each phase prompt is a floor, not a ceiling — this
file is the paper trail showing where the project went past that floor, on whose
initiative, and why. Useful for a capstone writeup or a demo narrative: "here's where
the build wasn't just following instructions."

Entries are chronological. Each one names the phase it landed in, whose idea it was,
what was built, and the reasoning.

---

## Phase 2 — Suggest agent

**All three "stretch goals" built as core, not skipped.**
The phase prompt listed Contrarian, Judge, and Negotiation Twin as optional stretch
goals. Built as required core functionality instead, once the LLM provider switch to
Groq (see Known Issues §2.10) removed the free-tier quota risk that would have made
three extra LLM calls per suggestion too expensive to justify skipping.

---

## Phase 3 — Fix & Learn

**`edited_text` on `Approval`, beyond the literal schema.**
The phase prompt's frontend spec required an "Edit" action for a reviewer to modify a
suggestion's text before approving it. The literal schema didn't have anywhere for that
edited text to persist, so a column was added to hold it — the Executor writes this
instead of the original `proposed_text` whenever it's set.

---

## Phase 4 — Ask agent

**Scope expanded from 4 routing categories to 5, plus persistent chat history.**
User's own words: *"i also want the tenant to have a chat storage wherein they can
visit their previous conversations... i want this Ask chatbot to mainly stick relevant
to their contracts and governmental guidelines... but also a bit general chatbot."*
The phase prompt specified `PORTFOLIO_QUESTION` / `SINGLE_DOCUMENT_QUESTION` /
`EDIT_INSTRUCTION` / `OUT_OF_SCOPE` only, with no chat persistence at all. Added:
- `COMPLIANCE_STATUS_QUESTION` — "what did Detect/Suggest/Fix & Learn actually do,"
  answered from Neo4j findings + Postgres suggestions/approvals directly, not vector
  search.
- `GENERAL_LEGAL_TECH_QUESTION` — general legal-tech knowledge, explicitly not
  portfolio-grounded, with a "not legal advice" disclaimer.
- `chat_sessions` / `chat_messages` tables and a full sidebar-plus-thread chat UI at
  `/ask`, instead of a single stateless Q&A box.

---

## Phase 5 — Login, Dashboard, Notifications

**Per-user draft rate limiting.**
Arose from a design discussion about whether `end_user` should be allowed to draft
edits at all (via Suggest or Ask's edit-instruction handoff). Decided drafting should
stay open to every role — it's always safe, since nothing writes to a real document
without a separate reviewer/admin approval — but should be *rate-limited* per user
instead of role-restricted, so one account can't flood the approval queue. User's
framing: *"maybe we should do this since it will showcase production grade quality."*
Backed by Redis — the container has existed since Phase 0's docker-compose but was
never actually used until this. New: `app/core/rate_limit.py` (mirrors the
`GraphStore` Neo4j/in-memory pattern), `enforce_draft_rate_limit` dependency, a
structured `RATE_LIMITED` response type from Ask.

**Closing the loop back to the requester.**
User's own framing, verbatim: *"lets suppose an end user puts a document for detect
and suggests a fix and drafts a new version.. the reviewer then accepts or rejects or
edits the draft.. can we put this?"* — followed by the exact three outcomes wanted:
- Reviewer **accepts** → requester gets a notification with a direct download link to
  the new document version.
- Reviewer **rejects** → requester gets a notification carrying the reviewer's typed
  reason (this also surfaced a real, separate bug: the frontend's Reject button had
  never actually collected a reason at all, despite the backend field existing since
  Phase 3 — see Known Issues §12.5).
- Reviewer **edits the draft themselves before approving** → requester gets a
  distinctly-worded notification saying their exact wording wasn't used, still with the
  download link.

Required: `RedlineSuggestion.requested_by_user_id` (tracks who asked for each draft),
and `Notification` gaining `kind` (`new_finding` broadcast tenant-wide vs.
`approval_decided` addressed to one `recipient_user_id`) plus `document_version_id`.
Not in any phase prompt — this whole notification-addressing model (broadcast vs.
targeted) didn't exist before this idea prompted it.

## Phase 6 — Horizon-Scanning & Restore

**Closing the loop for Restore requests too, matching Phase 5's pattern exactly.**
The Phase 6 prompt says nothing about notifying a restore requester once their
request is decided. Added on request, mirroring the Phase 5 "close the loop"
feature built for Suggest drafts: `notify_restore_decision()` addresses a
notification to whoever requested the restore — a rejection carries the
reviewer's note, an approval carries a direct download link to the new
version. The user's ask, once told the Suggest-side version existed: extend
the same idea to Restore, for consistency.

## Phase 6b — realism fixes (all from the user's own manual-testing list)

Listed by the user as *"Issues or Changes I thought should be there in order to make this product much more realistic and working"*. Each was assessed for viability first; all were built.

**Per-user dashboard and data (Issue 1).** *"End User and Reviewer, both share the same dashboard. The End User should only be able to see the numbers … for the contracts only that he has put."* The user confirmed the rule: only end users are restricted, reviewers and admins see everything. The gap turned out to be wider than the dashboard (Ask, contract pages, approvals, documents, restore and notifications were all tenant-wide), so the same rule was applied across all of them.

**Who requested a draft, and when (Issue 2).** Reviewers can now see the requester and the time on every pending/decided approval and restore request.

**Preview, edit, then submit (Issue 3).** *"…first shows the draft suggested by our AI and they should also get a chance to edit the suggested fix in case they are trying to bring some changes that are required by the company's specifications."* The user confirmed it should apply to both the Suggest button and Ask's edit instructions, so the two paths behave the same.

**Requester sees their own drafts and what the reviewer changed (Issue 4).** A "My Drafts" page showing the AI draft, the requester's edit, the reviewer's edit as a highlighted diff, the reviewer's note, and a download link.

**Attach a file in Ask (Issue 5).** *"An Attach file button in Ask chat … so that the end user can attach their own contract file and based on that file, they may also get to ask questions."* The user chose a real upload (full Detect run, saved under the user) over a temporary question-only file, which also meant giving the chat a remembered "active document".

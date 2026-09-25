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

## Frontend redesign

**A full UI rebuild from the user's own specification** (a 30-section "Legal Tech Platform — Frontend Redesign & Production UI/UX Specification"). Asked to review it first, the assistant reported what didn't fit the project (features the app doesn't have, conflicts with built ones, vague points, contrast problems) and the user answered four questions:

- **Real stage progress** instead of a fake percentage — which needed a small backend job-progress tracker so the UI can show the stage the pipeline is genuinely in, and lets a global "N processes running" indicator survive navigation.
- **Horizon Scanning as an update log plus an admin trigger** — the log became readable by every role (with the "simulated" disclaimer kept), so the page moved out of `/admin`.
- **Small read-only backend additions** — contract list, current-user info, who decided each approval, quoted evidence on Ask sources, the regulatory-update log.
- **Lucide + Radix primitives + cmdk** as the only new dependencies, with a "unique and not at all like AI-slop websites" brief: no gradients, no emoji, no decorative KPI tiles; findings marked with a dot *and* a word; one accent colour.

### Found by the user while testing the redesigned app

Three observations the user made on their own before following the test plan, all built:
- *"Drafts that have not been submitted to the Reviewer should have an option to delete them so that one does not get confused with so many drafts of the same contract"* — delete for never-submitted drafts (single and per-contract bulk). The user explicitly ruled out letting an end user withdraw a draft that is already with a reviewer.
- *"There should be a feature to 'Rename' the Titles of conversation in the Ask Feature"* — rename, and (at the user's request) delete, for conversations.
- *"I should have 3 written in the Dashboard's Where Findings Stand In Review feature, but it has only mentioned 2"* — traced to Ask drafts not being linked to a finding and to newest-draft-wins staging; fixed (see SETUP_NOTES).

### Found by the user asking "why?"

Asked what Horizon-Scanning's "0 contracts newly flagged · re-running is idempotent" result required, the user prompted a re-read of the code that showed it wasn't idempotent through the real API (fixed). Asked why Restore would need a re-scan, the user correctly pointed out that restoring the original version already matches the findings — which turned a proposed "re-scan" feature into a small honesty fix (clear wording, correct labels) instead of a risky one.

### The user's own end-to-end scenario

*"Upload contract A, detect and fix it; bring a Horizon-Scanning amendment that makes the fixed contract problematic again; re-fix it; re-check the re-fixed document through Detect to get a finally clean document."* — walked through step by step, this exposed that Horizon-Scanning and Detect could never see an edited document, and that the downloadable copy was a redline, not a clean contract. The user asked for **both** kinds of download ("clean copy and strikethrough copy") and for the re-scan to be built. Full design and safeguards: SETUP_NOTES ("Clean copy and re-scan").

### Additions made during the redesign, beyond the specification

These were not in the user's 30-section specification or in any phase prompt; each came from reviewing the spec against the real project, or from what testing revealed.
- **One central permission model** (`frontend/src/lib/permissions.ts`) — role -> permissions, route rules and the nav list in a single place, driving the sidebar, the command palette, the route guard and every action button. It replaced role lists scattered across the old header, gate and pages.
- **Who decided each approval/restore** (`decided_by_user_id` / `decided_by_email`), shown to the requester and in the queue history — a natural answer to "who reverted this, and why?".
- **Quoted evidence on Ask answers** — each cited source carries the actual passage that was retrieved (never taken from the model's own output), so an answer shows its proof.
- **A regulatory-update log** readable by every role, with each update's affected contracts (scoped to what the reader may see), instead of an admin-only form.
- **A contract list and "who am I" endpoint**, feeding the dashboard, the command palette and the user menu.
- **Real job progress** for uploads (Redis-backed, fails open) and a global "N processes running" indicator that survives navigation.
- **Accessibility and polish the spec only gestured at:** a skip-to-content link, a visible keyboard focus ring everywhere, `prefers-reduced-motion` respected, status shown as a dot *and* a word (colour is never the only signal), and darkened text shades so body text meets WCAG AA on the warm canvas.
- **Draft, then submit, with discard** — a fresh draft can be thrown away in place, and unsubmitted drafts can be deleted later (one, or all for one document); submitted drafts can never be deleted (they are the approval record).
- **`backend/scripts/reset_app_data.py`** — wipes everything a user created while testing (contracts, findings, drafts, versions and files, notifications, chats, Redis state) *without* stopping any server, keeping accounts, playbook rules and baseline regulations. Runs as a dry run unless given `--yes`. Its dry run was verified against the live databases; the wipe itself has not been executed on the user's data.
- **A startup schema upgrade** (`app/db/schema_upgrades.py`) so a new nullable column doesn't force a database reset (Known Issues 14.10).
- **An audit trail for the new actions** — `draft_deleted`, `contract_rescan_started` / `_completed` / `_failed`, alongside the existing approval and restore events.

### Decisions the user made that are worth remembering
- **Not built, deliberately:** withdrawing a draft that is already with a reviewer — once submitted, only the reviewer decides it.
- **Not built, deliberately (then built after all):** a "Re-scan" of an edited contract. It was first declined because *Restore* doesn't need it (restoring the original already matches the findings); the user's own lifecycle scenario (fix -> new regulation -> re-fix -> verify) then showed it was genuinely needed for a different reason, and it was built with safeguards.
- **Both download kinds kept:** the user asked for the clean copy *and* the redline copy, not one replacing the other.
- **Left to my judgement, stated openly:** how the dashboard should count drafts (Known Issues 14.9) — the user asked me to choose the best option and report what changed.

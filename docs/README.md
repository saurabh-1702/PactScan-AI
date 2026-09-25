# PactScan AI — Documentation

This folder holds the project specification and the phase-by-phase build plan.

## Contents

| Document | Description |
|---|---|
| `PactScan_AI_Final_Project_Document.md` | Master specification — single source of truth for architecture, scope, and design decisions. |
| `PactScan_AI_Known_Issues_And_Lessons_Learned.md` | Running log of environment bugs, process mistakes, and their fixes — **read before debugging**. Appended to whenever a new issue is hit and fixed. |
| `Phase_0_Repo_Setup_Prompt.md` … `Phase_7_Polish_And_Demo_Prep_Prompt.md` | The phase-by-phase build instructions. Phase 0 = repo/env scaffold; Phase 1 = Detect agent; Phase 2 = Suggest; Phase 3 = Fix & Learn; Phase 4 = Ask agent; Phase 5 = Login/Dashboard/Notifications; Phase 6 = Horizon-Scanning & Restore; Phase 7 = Polish & Demo prep. |
| `SETUP_NOTES.md` | Deviations from the phase prompts made during the actual build (dependency version substitutions, tooling notes). |
| `PactScan_AI_Ideas_And_Scope_Additions_Log.md` | Features added beyond what a phase prompt literally asked for — whose idea, what was built, and why. A paper trail of where the build went past the floor a prompt set. |

## Current status

**Frontend redesign (branch `frontend/redesign`, on top of Phase 6b).**
The whole UI was rebuilt to a restrained, light, enterprise legal-tech design: persistent
sidebar + Ctrl+K command palette, one central permission model, real stage-by-stage progress
for uploads with a global "N processes running" indicator, and every page restyled (Dashboard,
Detect, Ask with quoted evidence, My Drafts, Approvals with a review panel, Horizon Scanning
as an update log with an admin-only trigger, contract page, notifications).
- **Horizon Scanning is now at `/horizon-scanning`** (readable by every role; only admins can trigger).
- New backend endpoints: `/api/auth/me`, `/api/contracts`, `/api/progress/*`,
  `/api/horizon-scanning/updates`; `decided_by` recorded on approvals/restores.
- Delete unsubmitted drafts, rename/delete Ask conversations, corrected dashboard counts.
- Tests: 121 mocked pass. **Requires a dev DB reset** (`docker compose down -v`).
- Not yet merged; manual end-to-end testing (including G Horizon Scanning and H Restore) pending.

**Phase 6b — realism fixes from manual testing (built on the Phase 6 branch, before Phase 7).**
Five changes the user identified while testing:
- **Ownership** — an end_user sees only contracts they uploaded (dashboard, contract pages,
  approvals, documents, restore, Ask, notifications); reviewers/admins see the whole tenant.
- **Requester + time** on every approval and restore request, for reviewers.
- **Draft, then submit** — Suggest and Ask only draft; the requester previews the AI text,
  may edit it, then submits it as the AI draft or their own edited version.
- **My Drafts** (`/my-drafts`) — the AI draft, the requester's edit, and a highlighted diff of
  where the reviewer changed it, plus the reviewer's note and a download link.
- **Attach a file in Ask** — a real upload (full Detect run) that the chat remembers as its
  "active document", so follow-ups don't need to name it.
- Tests: 88 mocked pass (18 new: ownership, draft-submit flow, attachments); the new graph
  queries were also run against real Neo4j. **Requires a dev DB reset** (new Contract /
  Notification / redline_suggestions / chat_sessions columns) — `docker compose down -v`.
  Not yet manually tested end to end in the browser.

**Phase 6 built — Horizon-Scanning (simulated) + Document Restore.** Demonstrates the
project's strongest differentiator: an already-signed, already-reviewed contract gets
re-flagged automatically when a *new* regulation clause lands, without anyone
re-uploading anything. Honesty note (also shown in the UI itself, per the phase's own
requirement): real 24/7 monitoring against government regulatory feeds is out of
scope — this is the mechanism a real scheduler would call, triggered manually here via
an admin-only endpoint/button instead.

- **Horizon-Scanning**: `POST /api/horizon-scanning/simulate-update` (admin-only) adds
  a new `RegulationClause`, then re-diffs it against every clause across every contract
  in the tenant — reusing Phase 2's portfolio-wide vector search and Phase 1's own
  NLI-check + finding-creation helper (`build_finding_from_nli`), so a Horizon-Scanning
  finding is structurally identical to a Detect finding and fires the exact same
  notification hook. Additive by design — a new `GraphStore.add_findings()` (unlike
  `replace_findings`, which would have wiped a contract's original findings) means a
  contract's Detect-era findings are never lost when a later regulation update re-diffs it.
- **Document Restore**: `POST /api/restore-requests` (any role, requires a non-empty
  `reason`) + `POST /api/restore-requests/{id}/decide` (`reviewer`/`admin` only, the
  same gate as redline approvals) — approving copies the target version's file forward
  as a brand-new version, never shortening the history. An abuse-flag (2+ approved
  restores on one contract within 30 days) surfaces as a warning banner in the approval
  queue without blocking anything. The requester gets notified either way, matching
  Phase 5's "close the loop" pattern (see the Ideas & Scope Additions log).
- New: `backend/app/agents/horizon_scanning/`, `backend/app/agents/restore/`,
  `restore_requests` Postgres table, `RegulationClause.effective_date`, a new
  `/contracts/[id]` frontend page (version history + Request Restore — didn't exist
  before this phase), `/admin/horizon-scanning` admin trigger page, and a third seeded
  demo account (`admin@demo.pactscan.ai`) since nothing before this phase needed one.
- Tests: 70 mocked pass (9 new, incl. additivity, idempotency, the same-notification-path
  check, empty-reason rejection, the end_user-403/reviewer-200 exit-criteria test, version-
  history-preserved-on-restore, and both abuse-flagging edge cases); not yet run live or
  manually tested — pending before merge to `develop`.

**Phase 5 complete and merged to `develop` — Login, role-based dashboard, real-time notifications.** Real
email/password auth (bcrypt + JWT, no SSO — a deliberate simplification per
the phase prompt) replaces the hardcoded `tenant_id = "demo_tenant"` used
throughout Phases 1-4; every existing endpoint now resolves the real tenant
and role from the caller's JWT. `POST /api/approvals/{id}/decide` is gated to
`reviewer`/`admin` roles only. A dashboard visualizes data Phases 1-3 already
computed (nothing new is calculated) — severity breakdown, approvals-by-status,
and a findings pipeline derived by joining Neo4j findings with Postgres
suggestions/approvals. New findings fire an in-app notification, and HIGH
severity ones additionally attempt an email via Resend (optional — degrades
gracefully with no key configured).

- **⚠️ One-time action required before running this phase**: Phases 2-4 never
  gave `redline_suggestions`/`document_versions` a `tenant_id` column, and
  there's still no migration framework, so this is a breaking schema change
  for any existing dev Postgres volume. Reset it once:
  ```
  cd infra
  docker compose down -v
  docker compose up -d
  ```
- **Demo accounts** (seeded automatically at backend startup, under
  `tenant_id = "demo_tenant"`): `enduser@demo.pactscan.ai` (role `end_user`),
  `reviewer@demo.pactscan.ai` (role `reviewer`), and `admin@demo.pactscan.ai`
  (role `admin`, added Phase 6 for Horizon-Scanning's admin-only trigger),
  all with password `PactScanDemo123!`. Register additional accounts via
  `POST /api/auth/register`.
- `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/notifications`,
  `POST /api/notifications/{id}/mark-read`, `GET /api/dashboard/overview`,
  `GET /api/dashboard/findings-pipeline`
- Frontend: `/login`, `/dashboard` (role-aware — reviewers/admins additionally
  see a Pending Approvals panel), a shared header with nav + a polling
  notification bell (replacing each page's own inline nav links), and a
  client-side route guard redirecting to `/login` without a valid JWT
- New: `backend/app/core/security.py` (hashing + JWT), `backend/app/api/deps.py`
  (`get_current_user`, `require_role`, `enforce_draft_rate_limit`),
  `backend/app/agents/notifications/`, `tenants` / `users` / `notifications`
  Postgres tables, `tenant_id` added to `redline_suggestions` and
  `document_versions`
- **Per-user draft rate limiting**: any role may draft an edit (Suggest, or
  Ask's edit-instruction handoff) — drafting is always safe, since nothing
  writes to a real document without a separate reviewer/admin approval — but
  it's capped at `DRAFT_RATE_LIMIT_MAX` (default 10) per
  `DRAFT_RATE_LIMIT_WINDOW_SECONDS` (default 600) per user. Backed by
  Redis (`backend/app/core/rate_limit.py`) — the first real use of the Redis
  container provisioned since Phase 0; fails open if Redis is unreachable.
  Exceeding it returns `429` with a `Retry-After` header from the REST
  endpoints, or an `AskResponseType.RATE_LIMITED` structured response from Ask.
- **Per-user chat isolation**: `ChatSession` gained `user_id` (Phase 4's own
  docstring anticipated this, but it wasn't actually done until manual
  testing caught two different users under the same tenant seeing each
  other's Ask conversations). Every session query is now scoped by
  `(tenant_id, user_id)`, and reusing someone else's `session_id` 404s.
- **Closing the loop back to the requester**: once a reviewer/admin decides a
  pending approval, whoever originally requested that draft (Suggest, or
  Ask's edit-instruction handoff) gets a targeted notification —
  `RedlineSuggestion.requested_by_user_id` tracks the requester,
  `Notification.kind="approval_decided"` addresses it to just that person.
  Rejected includes the reviewer's note (now actually collected — the
  frontend's Reject button never had an input for it before this); approved
  includes a direct download link to the new version, worded differently if
  the reviewer wrote their own edit rather than using the exact drafted text.
- Tests: 61 mocked pass (14 new, incl. the tenant-isolation exit-criteria test
  with two seeded tenants, rate-limit tests for both entry points, a
  cross-user chat-session isolation regression test, and full coverage of
  all three requester-notification outcomes); verified live, and manually
  tested end-to-end including real email delivery via Resend

**Phase 4 complete and merged to `develop` — Ask agent (chatbot, contract Q&A, compliance-status Q&A, general legal-tech Q&A, edit-instruction handoff, chat history).** Scope
expanded beyond the literal phase prompt at the user's request: two extra
routing categories (`COMPLIANCE_STATUS_QUESTION`, `GENERAL_LEGAL_TECH_QUESTION`)
alongside the required `CONTRACT_QUESTION` / `EDIT_INSTRUCTION` / `OUT_OF_SCOPE`,
plus persistent chat sessions so a tenant can revisit prior conversations like
a normal chatbot. Edit instructions hand off into Phase 2's Suggest pipeline
(`suggest_standalone`) and never touch the Phase 3 Executor or write a file —
governance from Phase 3 is preserved end-to-end.

- `POST /api/ask`, `GET /api/ask/sessions`, `GET /api/ask/sessions/{id}/messages`
- Frontend: `/ask` — sidebar of past conversations + chat thread, response-type
  badges, citation chips, link into the Approval Queue for edit drafts
- New: `backend/app/agents/ask/` (scope_classifier, ask_retriever,
  answer_generator, status_query, general_legal, edit_handoff, pipeline),
  `chat_sessions` / `chat_messages` Postgres tables, `vector_search_similar_clauses`
  extended with an optional `contract_id` filter + `list_contracts()` on `GraphStore`
- Tests: 47 mocked pass (13 new: 9 agent-level + 3 API + chat persistence);
  verified live against real Neo4j + Postgres across all 7 response types;
  manually tested end-to-end in the browser (all 7 response types + chat
  history persistence across sessions)

**Phase 3 complete and merged to `develop` — Fix & Learn + human approval gate.** Every Suggest
output auto-enters a pending approval queue; nothing is ever written into a
real document except through `POST /api/approvals/{id}/decide`, and rejecting
never touches a file (proven by an explicit test, not just inspection).
Documents are versioned (never edited in place), with a visual
tracked-changes style edit (strikethrough+red / underline+green — python-docx
can't do Word's native revision XML).

- `POST /api/approvals`, `GET /api/approvals?status=pending`,
  `POST /api/approvals/{id}/decide` (the **only** entry point into the
  Executor), `GET /api/documents/contract/{id}/versions`,
  `GET /api/documents/version/{id}/download`
- Frontend: `/approvals` queue — Accept / Reject / Edit, side-by-side
  original/proposed text, download link once a version exists
- New: `backend/app/agents/fix_and_learn/` (document_store, executor,
  playbook_feedback), `approvals` / `document_versions` / `audit_log` /
  `playbook_feedback` Postgres tables, `backend/storage/documents/` (gitignored)
- Tests: 34 mocked pass (5 new); verified live against real Neo4j + real
  Postgres (incl. a real FK-constraint catch SQLite couldn't)

**Phase 2 complete and merged to `develop` — Suggest agent.** Retriever (vector search + OVERRIDES
context + violated-rule text) → drafting → Contrarian → Judge → Negotiation
Twin (all three stretch goals built, not skipped) → persisted to
`redline_suggestions`. Never writes to a file — that's Phase 3.

- `POST /api/suggest/from-finding/{finding_id}`, `POST /api/suggest/standalone`
- Frontend: "Suggest fix" button on `/detect`'s findings list
- New: `backend/app/llm/client.py::generate_embedding` (Gemini, dedicated pool),
  `backend/app/agents/suggest/`, `backend/app/db/models.py` (`RedlineSuggestion`)
- Tests: 29 mocked pass (incl. file-immutability + dismissed-verdict-persisted);
  `-m live` also needs `GEMINI_API_KEYS` for embeddings even with Groq leading

**Phase 1 complete and merged to `develop` — Detect agent.** Ingests a vendor DPA (LlamaParse), extracts
clauses, writes a Neo4j knowledge graph with `OVERRIDES` relationships, checks
clauses against the playbook + DPDP (primary) / GDPR (secondary), and returns a
severity-scored risk report with page/section citations.

- `POST /api/detect` (file upload) and `GET /api/detect/{contract_id}`
- Frontend: `/detect` upload + findings view
- LLM: provider-agnostic abstraction (`backend/app/llm/`) — response cache →
  7-tier Gemini model chain → multi-account fallback
- Tests: `cd backend && venv\Scripts\Activate.ps1 && pytest` (mocked, no keys
  needed); `pytest -m live` needs `GEMINI_API_KEYS` + `LLAMA_CLOUD_API_KEY` in
  `backend\.env`

**Phase 0 — Repository setup & local dev environment.** Scaffold; see root `README.md`.

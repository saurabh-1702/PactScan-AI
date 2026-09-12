# PactScan AI — Documentation

This folder holds the project specification and the phase-by-phase build plan.

## Contents

| Document | Description |
|---|---|
| `PactScan_AI_Final_Project_Document.md` | Master specification — single source of truth for architecture, scope, and design decisions. |
| `PactScan_AI_Known_Issues_And_Lessons_Learned.md` | Running log of environment bugs, process mistakes, and their fixes — **read before debugging**. Appended to whenever a new issue is hit and fixed. |
| `Phase_0_Repo_Setup_Prompt.md` … `Phase_7_Polish_And_Demo_Prep_Prompt.md` | The phase-by-phase build instructions. Phase 0 = repo/env scaffold; Phase 1 = Detect agent; Phase 2 = Suggest; Phase 3 = Fix & Learn; Phase 4 = Ask agent; Phase 5 = Login/Dashboard/Notifications; Phase 6 = Horizon-Scanning & Restore; Phase 7 = Polish & Demo prep. |
| `SETUP_NOTES.md` | Deviations from the phase prompts made during the actual build (dependency version substitutions, tooling notes). |

## Current status

**Phase 5 built — Login, role-based dashboard, real-time notifications.** Real
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
  `tenant_id = "demo_tenant"`): `enduser@demo.pactscan.ai` (role `end_user`)
  and `reviewer@demo.pactscan.ai` (role `reviewer`), both with password
  `PactScanDemo123!`. Register additional accounts via `POST /api/auth/register`.
- `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/notifications`,
  `POST /api/notifications/{id}/mark-read`, `GET /api/dashboard/overview`,
  `GET /api/dashboard/findings-pipeline`
- Frontend: `/login`, `/dashboard` (role-aware — reviewers/admins additionally
  see a Pending Approvals panel), a shared header with nav + a polling
  notification bell (replacing each page's own inline nav links), and a
  client-side route guard redirecting to `/login` without a valid JWT
- New: `backend/app/core/security.py` (hashing + JWT), `backend/app/api/deps.py`
  (`get_current_user`, `require_role`), `backend/app/agents/notifications/`,
  `tenants` / `users` / `notifications` Postgres tables, `tenant_id` added to
  `redline_suggestions` and `document_versions`
- Tests: 52 mocked pass (5 new, incl. the tenant-isolation exit-criteria test
  with two seeded tenants); not yet run live or manually tested — pending
  before merge to `develop`

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

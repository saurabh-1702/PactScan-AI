# PHASE 3 — Fix & Learn + Human Approval Gate — Windows Edition
### Prompt for Claude Code (paste this entire file as your instruction)

---

## PROJECT CONTEXT (read this first)

You are building **PactScan AI**, an agentic GraphRAG platform for legal contract compliance, scoped to SaaS/vendor Data Processing Agreements under India's DPDP Act (primary regulation; GDPR secondary). This is **Phase 3** of a 7-phase build. Phase 1 built the Detect Agent (findings from parsed contracts in Neo4j). Phase 2 built the Suggest Agent (drafts redlines into a `redline_suggestions` PostgreSQL table, never touching any file), using the provider-agnostic `app\llm\client.py` abstraction backed by a caching + 7-tier model + multi-account fallback LLM abstraction (Google Gemini, 3 accounts, extensible). Assume both exist and work. The real `.env` lives only at `backend\.env`.

**What Phase 3 must prove — this is the most important governance claim in the entire project:** a proposed redline from Phase 2 can only ever be written into a real document after an explicit, logged human approval action. There must be no code path, however convenient, that allows an automated write without that approval record existing first. This phase also introduces document versioning, so a bad approved edit can later be reverted (built fully in Phase 6, but the data model starts here).

**Do NOT build in this phase:** chat/Q&A (Phase 4), login/roles (Phase 5 — for now, treat every user as able to approve, but structure the code so role-gating can be added later without a rewrite), horizon-scanning (Phase 6).

---

## WINDOWS NOTE
Continue using `venv\Scripts\Activate.ps1` and `curl.exe` for manual testing throughout this phase.

---

## TECH FOR THIS PHASE
- Document writing: **python-docx** (add `python-docx==1.1.2` to `requirements.txt` — verify latest compatible at install time if unavailable) for `.docx` tracked-changes-style edits (python-docx does not natively support Word's real "Track Changes" XML feature well — implement it as: keep the original text visibly struck through and the new text visibly inserted, using distinct formatting such as strikethrough + red for deletions and underline + a different color for insertions, so the effect is visually equivalent even if it's not using Word's native revision-tracking XML. Note this simplification clearly in your code comments.)
- Storage: local filesystem under `backend\storage\documents\{tenant_id}\{contract_id}\` for this phase.
- Database: PostgreSQL (extend Phase 2's schema).

---

## STEP-BY-STEP BUILD INSTRUCTIONS

### 1. Extend the PostgreSQL schema (`backend\app\db\models.py` or your existing models file)
Add these tables:
- **`approvals`**: `id`, `redline_suggestion_id` (FK to Phase 2's `redline_suggestions`), `status` (`pending`/`approved`/`rejected`), `reviewer_note` (nullable text), `decided_at` (nullable), `created_at`.
- **`document_versions`**: `id`, `contract_id`, `version_number`, `file_path`, `approval_id` (FK to `approvals`, nullable for the very first/original version), `created_at`.
- **`audit_log`**: `id`, `event_type` (e.g., `approval_decided`, `document_written`), `entity_id`, `details` (JSON), `created_at`. Every state-changing action from this phase forward must write a row here.

### 2. Build the approval queue API (`backend\app\api\approvals.py`)
- `POST /api/approvals` — creates a new `approvals` row with `status=pending` for a given `redline_suggestion_id`. Wire this in automatically: after a Suggest call in Phase 2's flow succeeds, automatically create a pending approval.
- `GET /api/approvals?status=pending` — lists all pending approvals with their associated redline suggestion, original clause text, and rationale.
- `POST /api/approvals/{id}/decide` — accepts `{"decision": "approved" | "rejected", "note": "optional string"}`. This is the **only** function in the entire codebase permitted to trigger the Executor (step 3 below). Write this with explicit, obvious code comments stating: "THIS IS THE ONLY ENTRY POINT INTO THE EXECUTOR. DO NOT CALL THE EXECUTOR DIRECTLY FROM ANYWHERE ELSE."
- On `rejected`: update the `approvals` row, write an `audit_log` entry, and stop — do not touch any file.
- On `approved`: update the `approvals` row, write an `audit_log` entry, then call the Executor.

### 3. Build the Executor (`backend\app\agents\fix_and_learn\executor.py`)
Given an approved `redline_suggestion`:
1. Locate the current version of the target `.docx` (from `document_versions`, most recent entry for that `contract_id` — if none exists yet, this is the original uploaded file).
2. **Before writing anything, copy the current file to a new path and insert a new `document_versions` row for it** (preserves the pre-edit state — critical for Phase 6's restore feature).
3. Use python-docx to locate the target clause text (match against the `raw_text` stored on the `Clause` node/row from Phase 1) and apply the visual tracked-change style edit described above.
4. Save the new version to a new file path, insert a new `document_versions` row pointing to it, with `approval_id` set to the approval that authorized this write.
5. Write an `audit_log` entry: `document_written`, including the `contract_id`, `approval_id`, and both old/new file paths.
6. This function must raise an error (not silently fail) if called without a valid, `approved` `approval_id` — add an explicit guard clause at the top that checks the approval's status in the database before proceeding. Defense in depth, even though step 2's API design should already prevent this.

### 4. Build a simple "learning loop" stub (`backend\app\agents\fix_and_learn\playbook_feedback.py`)
- On approval, log the accepted redline's `clause_type` and final text to a simple `playbook_feedback` table (`id`, `clause_type`, `accepted_text`, `created_at`). This is a lightweight stand-in for the full "update the compliance playbook" learning loop — for Phase 3, just prove the data is being captured.

### 5. Frontend — build the approval queue UI (`frontend\app\approvals\page.tsx`)
- List all pending approvals, each showing: original clause text, proposed clause text (side-by-side or diff-style), rationale, confidence score.
- Three buttons per item: **Accept**, **Reject**, and **Edit** (Edit should let the reviewer modify the proposed text in a textarea before submitting as an edited-approval).
- After a decision, remove the item from the pending list and show a success/failure toast.
- Add a "Download" link next to any contract that has at least one `document_versions` entry, so you can open the actual edited `.docx` and visually confirm the tracked-change-style formatting.

---

## TESTS TO WRITE (`backend\tests\test_approval_gate.py`)
- Test that calling the Executor function directly, in isolation, with an `approval_id` that has `status=pending` (not `approved`) raises an error and writes no file.
- Test that `POST /api/approvals/{id}/decide` with `"decision": "rejected"` results in zero changes to any file on disk (compare file hash before/after).
- Test that `POST /api/approvals/{id}/decide` with `"decision": "approved"` results in: (a) a new file being written, (b) a new `document_versions` row pointing to it, (c) an `audit_log` row recording the event, (d) the original file's `document_versions` entry still existing and unmodified.
- Test that the resulting `.docx` file, when opened programmatically with python-docx, contains both the original struck-through text and the new inserted text.

## EXIT CRITERIA FOR THIS PHASE
All tests above pass. You can walk through the full flow in the frontend: view a Phase 2 suggestion in the approval queue → click Reject on one, confirm nothing changes on disk → click Accept on another → open the resulting `.docx` file and visually confirm the tracked-change-style edit is present and correct. Do not proceed to Phase 4 until the "reject never touches a file" guarantee is proven by an actual passing test, not just visual inspection.

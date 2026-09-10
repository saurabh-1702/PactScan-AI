# PHASE 6 — Horizon-Scanning (Simulated) + Document Restore — Windows Edition
### Prompt for Claude Code (paste this entire file as your instruction)

---

## PROJECT CONTEXT (read this first)

You are building **PactScan AI**, an agentic GraphRAG platform for legal contract compliance, scoped to SaaS/vendor Data Processing Agreements under India's DPDP Act (primary regulation; GDPR secondary). This is **Phase 6** of a 7-phase build, and it demonstrates the project's strongest differentiator: perpetual, automatic re-auditing of already-signed contracts when regulations change — plus the ability to safely revert a bad approved edit. By now you have: Phase 1's Detect Agent, Phase 2's Suggest Agent, Phase 3's Fix & Learn (with `document_versions` and the approval gate), Phase 4's Ask Agent, and Phase 5's login/roles/dashboard/notifications. All LLM calls go through `backend\app\llm\client.py`, backed by a caching + 7-tier model + multi-account fallback LLM abstraction (Google Gemini, 3 accounts, extensible). The real `.env` lives only at `backend\.env`.

**What Phase 6 must prove (two separate features):**
1. **Horizon-Scanning (simulated):** the system can detect that a *new* regulation affects an *already-signed, previously-reviewed* contract, without a human re-uploading anything, and this correctly produces new findings and notifications.
2. **Restore:** a client can request reverting a document to a prior version, and this request goes through the exact same human approval gate as any other edit.

**Important honesty note to build into the system itself:** true 24/7 continuous regulatory monitoring against real government sources is out of scope. Build the *mechanism* for real, but trigger it manually via an admin endpoint/button rather than a live scheduler — document this clearly in the UI itself.

---

## WINDOWS NOTE
Continue using `venv\Scripts\Activate.ps1` and `curl.exe` for all commands.

---

## STEP-BY-STEP BUILD INSTRUCTIONS

### PART A — Horizon-Scanning (simulated)

### 1. Extend the Neo4j schema for regulation versioning (`backend\app\agents\horizon_scanning\regulation_writer.py`)
- Add a `version` or `effective_date` property to existing `RegulationClause` nodes from Phase 1.
- Write a function `add_regulation_update(regulation_name, new_clause_text, effective_date)` that inserts a new `RegulationClause` node representing an amendment/new rule under an existing regulation (GDPR or DPDP).

### 2. Build the re-diff engine (`backend\app\agents\horizon_scanning\rediff.py`)
- Given a newly-added `RegulationClause`, query the graph for **every existing `Clause` node across every contract already in the system** that is topically related (reuse Phase 2's vector similarity search against the new regulation clause's embedding).
- Run the same NLI-style compliance check from Phase 1's Detect Agent (via `generate_structured()` in `app\llm\client.py`) between each matched clause and the new regulation text.
- For every `CONTRADICTS` or relevant `NEUTRAL` result, create a new finding using the exact same finding-creation logic as Phase 1's Detect Agent — refactor Phase 1's finding-creation into a shared function if it isn't already, and call that same function here. This keeps Detect-originated and Horizon-Scanning-originated findings structurally identical.
- Each newly-created finding must trigger Phase 5's notification hook exactly as a normal Detect finding would.

### 3. Build the trigger endpoint (`backend\app\api\horizon_scanning.py`)
- `POST /api/horizon-scanning/simulate-update` — accepts `{"regulation_name": string, "new_clause_text": string, "effective_date": string}`, calls step 1's `add_regulation_update()` then step 2's re-diff engine, returns a summary of how many existing contracts were newly flagged.
- Restrict this endpoint to `admin` role only (reuse Phase 5's `require_role` dependency).

### 4. Frontend — add a simple admin trigger UI (`frontend\app\admin\horizon-scanning\page.tsx`)
- A form for an admin user to input a mock regulation update and a button to trigger the endpoint.
- Show the result: "X contracts newly flagged" with links to each affected contract's findings.
- Add a visible note: *"In production, this runs automatically on a schedule against real regulatory feeds. This manual trigger simulates that process for demonstration purposes."*

---

### PART B — Document Restore

### 5. Build the restore request flow (`backend\app\agents\restore\restore_agent.py`)
- Accepts `contract_id` + `target_version_id` + a required `reason` string (validate non-empty).
- Creates a new row in a new `restore_requests` table: `id`, `contract_id`, `target_version_id`, `requested_by_user_id`, `reason`, `status` (`pending`/`approved`/`rejected`), `created_at`, `decided_at`.
- **Do not write anything to a file yet.**

### 6. Reuse Phase 3's approval mechanism for restore requests
- Extend `POST /api/approvals/{id}/decide` (or add a parallel `POST /api/restore-requests/{id}/decide` endpoint using the identical pattern) so that on `approved`:
  1. Copy the target version's file content forward as a **new** `document_versions` entry (do not delete or overwrite versions in between).
  2. Write an `audit_log` entry: `document_restored`.
- Must go through the exact same `require_role(["reviewer", "admin"])` gate.

### 7. Build the abuse-flagging check (`backend\app\agents\restore\abuse_check.py`)
- Count how many `restore_requests` with `status = approved` exist for a `contract_id` within the last 30 days. If 2+, flag it (don't block) — show a warning banner in the approval queue UI, log an `audit_log` entry of type `restore_pattern_flagged`.

### 8. Frontend — add restore UI
- On the contract detail page, list all versions with timestamps and a "Request Restore" button on any non-current version, prompting for the required `reason`.
- In the approval queue UI, render restore requests alongside normal redline approvals, showing the abuse-flag warning when applicable.

---

## TESTS TO WRITE (`backend\tests\test_horizon_scanning_and_restore.py`)
- Test that `POST /api/horizon-scanning/simulate-update` correctly flags at least one contract that should genuinely be affected, and does NOT flag `contract_c_clean.pdf` if it has no relevant clauses.
- Test that a Horizon-Scanning finding triggers a notification via the exact same code path as a Detect finding.
- Test that a restore request with an empty `reason` is rejected.
- Test that an `end_user`-role JWT can create a restore request but gets 403 attempting to approve/reject it.
- Test that approving a restore request creates a **new** `document_versions` entry rather than modifying existing ones — assert version history length increases by exactly 1, prior entries unchanged.
- Test the abuse-flagging logic directly: seed 2 already-approved restores for one contract within 30 days, submit a 3rd, assert the flag is set.

## EXIT CRITERIA FOR THIS PHASE
All tests above pass. You can, live: (1) trigger a simulated regulation update and watch it flag an existing contract with a real notification, without uploading anything, and (2) request a restore, approve it as a reviewer, and confirm the file reverts correctly while the full version history remains intact. Do not proceed to Phase 7 until both flows work end-to-end through the actual UI.

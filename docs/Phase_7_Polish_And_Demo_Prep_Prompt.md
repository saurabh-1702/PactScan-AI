# PHASE 7 — Polish, Evaluation, Final Demo Prep — Windows Edition
### Prompt for Claude Code (paste this entire file as your instruction)

---

## PROJECT CONTEXT (read this first)

You are building **PactScan AI**, an agentic GraphRAG platform for legal contract compliance, scoped to SaaS/vendor Data Processing Agreements under India's DPDP Act (primary regulation; GDPR secondary). This is **Phase 7**, the final phase of a 7-phase build. By now the full pipeline exists and works: login/roles (Phase 5), Detect (Phase 1), Suggest (Phase 2), approval-gated Fix & Learn with versioning (Phase 3 + 6), Ask (Phase 4), Horizon-Scanning simulation and restore (Phase 6), and a dashboard/notifications (Phase 5). All LLM calls run through `backend\app\llm\client.py`, backed by a caching + 7-tier model + multi-account fallback LLM abstraction (Google Gemini, 3 accounts, extensible). The real `.env` lives only at `backend\.env`.

**What Phase 7 must prove:** the system is stable enough to demo start-to-finish without manual intervention or debugging, has basic error handling for realistic edge cases, and has a lightweight evaluation mechanism proving output consistency. This phase adds **no new agent capabilities** — it is entirely about hardening what already exists, plus adding automated end-to-end UI testing via Playwright.

---

## WINDOWS NOTE
Continue using `venv\Scripts\Activate.ps1` and `curl.exe` for backend commands throughout this phase.

---

## STEP-BY-STEP BUILD INSTRUCTIONS

### 1. Build a lightweight evaluation script (`backend\scripts\eval_detect_consistency.py`)
- Run Phase 1's `POST /api/detect` on all 3 sample contracts **5 times each**.
- For each contract, assert: the same number of findings is produced every run, the same clause types are flagged every run, and the same page numbers are cited every run.
- Output a simple pass/fail report to the console (a lightweight stand-in for a full RAGAS/BERTScore evaluation harness — note this explicitly in the script's docstring).
- Runnable as a standalone command (`python scripts\eval_detect_consistency.py`). Optional: add `.github\workflows\eval.yml` running this on every PR to `develop`.

### 2. Harden error handling for these specific edge cases (add explicit handling + tests for each):
- **Bad file upload to `/api/detect`** — a non-PDF/DOCX file, or a corrupted file. Must return a clear 4xx error, not a 500 crash.
- **Empty portfolio** — a brand-new tenant with zero uploaded contracts asking the Ask Agent a question. Must return a clean "you haven't uploaded any contracts yet" message.
- **Duplicate contract upload** — uploading the exact same file twice. Decide and implement a clear behavior (detect via file hash, either reject with a clear message or treat as a new version) — document whichever choice you make.
- **Approval decision on an already-decided approval** — calling `POST /api/approvals/{id}/decide` twice on the same id. Must return a clear error on the second call.
- **Restore request targeting a non-existent version** — must return a clear 404.
- **Expired/invalid JWT on any protected route** — must consistently return 401 across every endpoint (test at least one endpoint from each phase — detect, suggest, approvals, ask, dashboard, horizon-scanning, restore — to confirm auth middleware is applied uniformly).

### 3. Add basic request logging/observability (`backend\app\middleware\logging.py`)
- A simple FastAPI middleware logging every request's method, path, status code, and duration to the console or a local log file — enough to debug a live demo quickly if something breaks.

### 4. Add Playwright E2E tests (recommended addition — does not block core exit criteria if time is short)
This is a self-contained addition that automates the same journey a human would click through in a live demo, adding real confidence beyond backend-only `pytest` coverage, without touching or complicating the existing architecture.

- In `frontend\`, add Playwright: `npm install --save-dev @playwright/test@latest` then `npx playwright install` (downloads browser binaries). Unlike the backend's pinned Python dependencies, `@latest` is acceptable here — Playwright's test API has been stable across recent versions, and this is a dev-only testing tool with no runtime coupling to the rest of the stack. Confirm the installed version with `npx playwright --version` after install and note it in `docs\` for reproducibility.
- Create `frontend\e2e\full_journey.spec.ts` covering, against the actually-running app (backend + frontend both up):
  1. Log in as the seeded `end_user` account (Phase 5).
  2. Upload `contract_a_conflict.pdf` via the Detect page, wait for and assert the multi-hop finding appears with the correct page citations.
  3. Click "Suggest Fix," assert a redline + rationale renders.
  4. Log out, log in as the seeded `reviewer` account.
  5. Navigate to the approval queue, assert the pending item is visible, click Accept.
  6. Navigate to the Ask page, ask a portfolio-wide question, assert a cited answer renders.
  7. As an `admin`-role account (seed one if not already present), trigger the Horizon-Scanning simulation from its admin page, assert the "X contracts newly flagged" result renders.
- Add an npm script (`"test:e2e": "playwright test"` in `frontend\package.json`) so this runs with one command: `npm run test:e2e`.
- **Keep this scoped to one comprehensive spec file, not a large suite** — the goal is one strong, realistic proof that the full user journey works end-to-end through the real UI, not exhaustive UI test coverage. Do not let this expand into testing every button/edge case in the frontend; that would add complexity disproportionate to its value for this project's scope.

### 5. Write a `docs\DEMO_SCRIPT.md` file
Combine everything into one literal, step-by-step script for a live demo, referencing the actual running application (exact URLs, exact sample file names, exact buttons to click). Include:
- Login as end-user, show dashboard
- Upload `contract_a_conflict.pdf`, run Full Pipeline, show the multi-hop finding
- Show the Suggest redline + rationale
- Log out, log in as reviewer, show approval queue, approve the fix, open the resulting `.docx`
- Ask the Ask Agent a portfolio-wide question
- Trigger the Horizon-Scanning simulation, show the notification fire on an old contract
- Request and approve a restore, show the version history
- Mention that this exact journey is also covered by an automated Playwright test (`npm run test:e2e`), if asked how you know it's reliable beyond the live demo
- One line ready for "what's simulated vs. fully built" if asked directly

### 6. Final smoke test (`backend\tests\test_full_pipeline_e2e.py`)
Write one single backend-level end-to-end test (separate from the Playwright UI test above — this one calls the API directly, no browser) that runs the entire flow programmatically, in order:
1. Register/login two users (end_user, reviewer)
2. End-user uploads `contract_a_conflict.pdf` via Detect
3. Assert a finding is produced
4. Call Suggest on that finding, assert a redline is produced
5. Assert a pending approval was auto-created
6. As reviewer, approve it, assert a new document version + audit log entry exist
7. As end-user, ask the Ask Agent about the now-modified contract, assert the answer reflects the approved change
8. As admin, trigger a horizon-scanning simulation, assert a new finding appears
9. Request a restore, approve it as reviewer, assert the file reverts and version history is intact

---

## FINAL CHECKLIST BEFORE PRESENTING

- [ ] `docker-compose up -d` (from `infra\`) + backend + frontend all start cleanly from a fresh clone
- [ ] The eval script from Step 1 passes (consistent Detect output across 5 runs)
- [ ] Every edge case in Step 2 is handled and tested
- [ ] The Playwright E2E spec from Step 4 passes (`npm run test:e2e`)
- [ ] The backend end-to-end test from Step 6 passes
- [ ] `docs\DEMO_SCRIPT.md` has been rehearsed at least once against the actual running application
- [ ] You can clearly state, for each phase, what was fully built vs. simplified vs. simulated

## EXIT CRITERIA
This phase — and the whole project build — is done when you can run the entire `docs\DEMO_SCRIPT.md` live, start to finish, without needing to fix anything or explain away an error, and the automated Playwright + backend E2E tests both pass as independent confirmation. If something breaks during rehearsal, fix it and re-rehearse before your actual presentation.

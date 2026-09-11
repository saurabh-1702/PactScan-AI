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

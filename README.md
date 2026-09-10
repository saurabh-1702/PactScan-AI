# PactScan AI

An agentic GraphRAG platform for legal contract compliance, scoped to SaaS/vendor
**Data Processing Agreements (DPAs)** and their parent MSAs. It analyzes vendor DPAs
against **India's DPDP Act, 2023** (primary) and **GDPR** (secondary, generalization
demo), detects compliance risks using a Neo4j knowledge graph plus LLM reasoning,
drafts redlines, and — only after a mandatory human approval gate — writes approved
edits into real Word documents.

This repository is built in 7 phases. **This is the Phase 0 scaffold**: repository
structure and local development environment only. No agent logic yet.

---

## Prerequisites

Exact versions confirmed working on the developer's machine:

| Tool | Version | Notes |
|---|---|---|
| Docker Desktop | 29.3.1+ | WSL2 backend enabled; `D:` drive file sharing enabled (Settings → Resources → File Sharing) |
| Node.js | 24.x LTS | This machine uses `nvm4w`; run `nvm use 24.14.1` before frontend commands |
| Python | 3.14.x | Use the existing 3.14.x install — do not install a separate interpreter |
| Git | 2.53+ | |

---

## Setup steps (Windows / PowerShell)

1. **Clone** the repository into `D:\PactScan-AI`:
   ```powershell
   git clone <repo-url> D:\PactScan-AI
   cd D:\PactScan-AI
   ```

2. **Start infrastructure** (Neo4j, PostgreSQL, Redis):
   ```powershell
   cd infra
   docker-compose up -d
   ```
   Wait until `docker ps` shows all three containers as `healthy`.
   PostgreSQL is mapped to host port **5433** (not 5432).

3. **Create the backend environment file:**
   ```powershell
   cd ..\backend
   copy .env.example .env
   ```
   Then open `backend\.env` and fill in real API keys.

4. **Create and activate the virtual environment, install dependencies:**
   ```powershell
   python -m venv venv
   venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
   Confirm your prompt shows `(venv)` before running any Python command.

5. **Run the backend:**
   ```powershell
   uvicorn app.main:app --reload
   ```

6. **In a separate terminal, run the frontend:**
   ```powershell
   cd D:\PactScan-AI\frontend
   nvm use 24.14.1
   npm install
   npm run dev
   ```

---

> ## ⚠️ Where the `.env` file must live
> The real `.env` file must be created at **`backend\.env`**, copied from
> **`backend\.env.example`**. Do **not** create a `.env` file anywhere else in the
> repository — `backend\app\config.py` loads `.env` relative to `backend\`, so any
> other copy is silently ignored. This has caused real setup failures before.

---

## How to verify it's working

| Check | Expected |
|---|---|
| `curl.exe http://localhost:8000/health` | `{"status": "ok"}` |
| Backend startup logs | `Neo4j connection OK` and `PostgreSQL connection OK` |
| `http://localhost:3000` in a browser | Page shows **"PactScan AI — Phase 0 Scaffold"** |
| `cd backend; venv\Scripts\Activate.ps1; pytest` | `test_health.py` passes |

On Windows, always use `curl.exe` (not `curl`, which is a PowerShell alias for
`Invoke-WebRequest` and does not accept standard curl flags).

---

## Project structure

| Folder | Purpose |
|---|---|
| `backend/` | FastAPI application, LLM abstraction, agents, tests. Runs from inside `backend\`. |
| `frontend/` | Next.js (App Router) + TypeScript + Tailwind reviewer UI. |
| `infra/` | `docker-compose.yml` for local Neo4j / PostgreSQL / Redis. |
| `docs/` | Full project specification and the phase-by-phase build plan. |

---

## Phase documents

`docs/` will contain the full project specification (`PactScan_AI_Final_Project_Document.md`)
and the phase-by-phase build prompts (`Phase_0` … `Phase_7`), plus a running
known-issues / lessons-learned log. See `docs/README.md`.

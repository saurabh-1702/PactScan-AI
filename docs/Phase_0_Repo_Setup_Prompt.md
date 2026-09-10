# PHASE 0 — Repository Setup & Team Foundations (Windows Edition)
### Prompt for Claude Code (paste this entire file as your instruction)

---

## PROJECT CONTEXT (read this first)

You are building **PactScan AI**, an agentic GraphRAG platform for legal contract compliance, **scoped specifically to SaaS/vendor Data Processing Agreements (DPAs) under India's DPDP Act, 2023 as the primary regulatory ground-truth** (GDPR retained as a secondary regulation to demonstrate generalization across jurisdictions). The clause taxonomy is informed by CUAD (Contract Understanding Atticus Dataset — Hendrycks et al., 2021), a peer-reviewed academic benchmark, used as a taxonomy reference only, not as loaded training data. The full product analyzes vendor DPAs/MSAs, detects compliance risks using a Neo4j knowledge graph + LLM reasoning, drafts redlines, and — after mandatory human approval — writes approved edits into real Word documents. It is being built in 7 phases; this is Phase 0, which sets up the repository and local development environment only. No agent logic is built in this phase.

**Tech stack for the whole project (so your setup matches later phases):**
- Backend: Python **3.14.x** (confirmed working with this exact stack — `neo4j` driver 6.2.0, `psycopg2-binary`, `sqlalchemy` 2.0.44 all install and function correctly on 3.14; use whatever Python 3.14.x is already installed on the developer's machine rather than requiring a separate install), FastAPI
- Graph database: Neo4j (local via Docker for dev)
- Relational database: PostgreSQL (local via Docker for dev)
- Cache/queue: Redis (local via Docker for dev)
- Frontend: Next.js (React) with TypeScript, Node.js 20 LTS
- Document parsing: LlamaParse (Phase 1+)
- Agent orchestration: LangGraph
- **LLM provider: Google Gemini, via the `google-genai` Python SDK (version >= 1.51.0 — required for Gemini 3's Interactions API and structured-output features).** The developer's Google AI Studio project is on the **free tier with no billing account attached**, which means `gemini-3.1-pro-preview` currently has zero usable quota (confirmed via the AI Studio Rate Limit dashboard — it shows 0/0 across every quota column). Instead, this build uses a **7-tier model fallback chain, wrapped inside a multi-account loop across 3 separate Google AI Studio accounts** (extensible to more via a comma-separated list, no code change needed to add a 4th/5th account): for the current account, try `gemini-3.8-flash` (20 requests/day) → `gemini-3.7-flash` (20/day) → `gemini-3.6-flash` (20/day) → `gemini-3.5-flash` (20/day) → `gemini-3.5-flash-lite` (500/day) → `gemini-3.1-flash-lite` (500/day) → `gemma-4-31b` (14,400/day); only once every tier under the current account is exhausted does the client advance to the next account's key and restart the same 7-tier chain from Tier 1. A **local response cache** (keyed by prompt content plus a prompt-version identifier, so a logic change never returns a stale cached answer) sits in front of this entire chain, so an identical call is never repeated against any account/tier at all. `gemini-embedding-001` is used separately and exclusively for vector embeddings (Phase 2+), with its own independent 1,000/day quota pool. `gemini-3.1-pro-preview` is kept configured but inactive, as a documented upgrade path if billing is ever enabled later. Build all LLM-calling code behind a provider-agnostic abstraction (detailed in Phase 1) that walks this cache → tier chain → account chain automatically.
- E2E testing (Phase 7 only): Playwright

---

## WORKING DIRECTORY (Windows)

The project root is fixed at `D:\PactScan-AI`. Set up the entire monorepo structure below directly inside this exact folder — do not create a nested subfolder.

**Windows-specific notes for the rest of this build (and all later phases):**
- Python virtual environments are activated with `venv\Scripts\Activate.ps1` in PowerShell. **Name the virtual environment folder exactly `venv`** (not `.venv`) — be consistent about this, since a mismatch between what's created and what's documented caused real confusion in a prior build attempt.
- Use `pathlib.Path` for all file path handling in Python code — never hardcode backslash string paths.
- Docker Desktop must have WSL2 backend enabled and file sharing enabled for the `D:` drive specifically (Settings → Resources → File Sharing) — if volume mounts fail, this is the first thing to check.
- Windows Terminal/PowerShell's built-in `curl` is an alias for `Invoke-WebRequest` and does **not** support standard curl flags like `-X`. When later phases reference `curl` commands, use `curl.exe` explicitly (which invokes the real curl binary bundled with Windows 10/11) to avoid this.

## CRITICAL — ENVIRONMENT FILE LOCATION (read carefully — this caused real, repeated problems in a prior attempt on this exact project)

There must be exactly **one** real `.env` file for the backend, located at **`backend\.env`** — not at the project root (`D:\PactScan-AI\.env`). This is because `backend\app\config.py` will be configured with `env_file=".env"`, which resolves **relative to the working directory the backend process is run from** — and the backend is always run from inside `backend\`. Do the following to avoid any ambiguity:
- Create `backend\.env.example` (placeholder values, safe to commit) — **do not** also create a `.env.example` at the project root; there should be only one, inside `backend\`.
- Instruct the developer (in `README.md`) to copy `backend\.env.example` to `backend\.env` and fill in real values — explicitly state in the README that this file must live inside `backend\`, not the project root, and that no other `.env` file should exist anywhere else in the repo.
- If you (the agent) ever need to add a new environment variable in a later phase, edit **only** `backend\.env.example` and `backend\.env` — never create or edit a root-level `.env` file.

---

## YOUR TASK

Set up a monorepo with the following exact structure, created directly inside `D:\PactScan-AI`:

```
PactScan-AI/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py               # FastAPI app entrypoint, health check endpoint at GET /health
│   │   ├── config.py              # loads env vars via pydantic-settings, env_file=".env"
│   │   ├── db/
│   │   │   ├── neo4j_client.py    # Neo4j driver connection helper (empty/stub for now)
│   │   │   └── postgres_client.py # SQLAlchemy engine + session setup (empty/stub for now)
│   │   ├── llm/                    # empty folder — will hold the provider-agnostic LLM client, built in Phase 1
│   │   ├── agents/                 # empty folder, populated in later phases
│   │   ├── api/                    # empty folder, populated in later phases
│   │   └── models/                 # empty folder, populated in later phases
│   ├── tests/
│   │   └── test_health.py          # test that GET /health returns 200
│   ├── requirements.txt
│   ├── .env.example                # THE ONLY .env.example in the whole repo — lives here, not at root
│   └── Dockerfile
├── frontend/
│   ├── (standard Next.js + TypeScript app, created via `npx create-next-app@latest`)
│   ├── package.json
│   └── Dockerfile
├── docs/
│   └── README.md                   # placeholder, will hold full project docs
├── infra/
│   └── docker-compose.yml          # see spec below
├── .gitignore
├── README.md
└── CONTRIBUTING.md
```

Note: there is **no `.env.example` or `.env` at the project root** — only inside `backend\`. Do not create one at the root, under any circumstance, in this or any later phase.

### 1. `infra\docker-compose.yml` — must include these exact services:

- **neo4j**: image `neo4j:5-community`, ports `7474:7474` and `7687:7687`, environment `NEO4J_AUTH=neo4j/testpassword123`, a named volume for data persistence.
- **postgres**: image `postgres:16`, **port `5433:5432`** (deliberately mapped to host port 5433, not the default 5432 — a prior build on this exact machine hit a port collision with a pre-existing native PostgreSQL Windows Service already listening on 5432; mapping to 5433 avoids this entirely without needing to touch the native service), environment `POSTGRES_USER=pactscan`, `POSTGRES_PASSWORD=testpassword123`, `POSTGRES_DB=pactscan_dev`, named volume for data persistence.
- **redis**: image `redis:7-alpine`, port `6379:6379`.

All three services must be reachable from the backend container on the same Docker network. Add healthchecks to each service so `docker-compose up` clearly reports when each is ready. Remove the obsolete top-level `version:` key from the compose file if your template includes one (modern Docker Compose ignores it and issues a warning).

### 2. `backend\.env.example` — include every variable below, with placeholder (non-real) values and a one-line comment explaining each:

```
# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=testpassword123

# PostgreSQL — note port 5433, not the default 5432 (see docker-compose.yml comment)
DATABASE_URL=postgresql://pactscan:testpassword123@localhost:5433/pactscan_dev

# Redis
REDIS_URL=redis://localhost:6379/0

# LLM provider — Google Gemini (free tier, no billing account attached)
# GEMINI_API_KEYS is a comma-separated list, in priority order. Currently 3 accounts.
# To add a 4th/5th account in future: just append another comma-separated key here — no code change needed.
GEMINI_API_KEYS=your_first_account_key,your_second_account_key,your_third_account_key
LLM_PROVIDER=gemini

# 7-tier MODEL fallback chain, ordered quality-first then volume-fallback.
# Each tier is a SEPARATE free-tier quota pool on Google AI Studio, PER ACCOUNT.
# The client walks the full 7-tier chain for the CURRENT account first; only once
# every tier under that account is exhausted does it advance to the next account
# in GEMINI_API_KEYS and restart the tier chain from Tier 1 under that account.
GEMINI_MODEL_TIER_1=gemini-3.8-flash
GEMINI_MODEL_TIER_2=gemini-3.7-flash
GEMINI_MODEL_TIER_3=gemini-3.6-flash
GEMINI_MODEL_TIER_4=gemini-3.5-flash
GEMINI_MODEL_TIER_5=gemini-3.5-flash-lite
GEMINI_MODEL_TIER_6=gemini-3.1-flash-lite
GEMINI_MODEL_TIER_7=gemma-4-31b

# Dedicated embeddings model (Phase 2+), separate quota pool, not part of the tier chain above.
# Uses the FIRST key in GEMINI_API_KEYS by default (embeddings are low-volume relative to
# the text-generation chain, so a dedicated fallback for embeddings is not built in this phase).
GEMINI_EMBEDDING_MODEL=gemini-embedding-001

# Kept configured but inactive — upgrade path if billing is ever enabled on the AI Studio project
GEMINI_MODEL_IF_BILLING_ENABLED=gemini-3.1-pro-preview

# LLM response cache (dev-mode quota conservation — see Phase 1 for full spec)
LLM_CACHE_ENABLED=true
LLM_CACHE_DIR=.llm_cache
LLM_PROMPT_VERSION=v1

# Anthropic — optional secondary provider, not required for this build to function
ANTHROPIC_API_KEY=

# LlamaParse (used starting Phase 1)
LLAMA_CLOUD_API_KEY=your_key_here

# App
ENVIRONMENT=development
```

### 3. `backend\requirements.txt` — pin these exact versions (verified mutually compatible as of this build):

```
fastapi==0.141.1
uvicorn[standard]==0.34.0
pydantic==2.10.4
pydantic-settings==2.6.1
neo4j==6.2.0
sqlalchemy==2.0.44
psycopg2-binary==2.9.10
redis==5.2.1
python-dotenv==1.0.1
pytest==8.3.4
pytest-asyncio==0.25.0
httpx==0.28.1
google-genai>=1.51.0
```

**Note on these pins:** `fastapi`, `uvicorn`, `pydantic`, `sqlalchemy`, `psycopg2-binary`, and `neo4j` are confirmed-current, mutually compatible versions as of this build. `pydantic-settings`, `redis`, `pytest`, `pytest-asyncio`, and `httpx` are reasonable current versions but were not individually version-verified — if `pip install` reports any of these as unavailable or yanked, install the latest available compatible version instead and note the substitution in `docs\`. `google-genai>=1.51.0` is a hard minimum, not a suggestion — this version is required for Gemini 3's Interactions API and structured-output features used starting Phase 1; do not downgrade below this.

### 4. `backend\app\main.py`
A minimal FastAPI app with:
- `GET /health` returning `{"status": "ok"}`
- CORS middleware allowing `http://localhost:3000` (for the Next.js frontend)
- Startup event that attempts to connect to Neo4j and Postgres and logs success/failure clearly (don't crash the app if they're unreachable — just log a warning, since this phase is about scaffolding, not real connections yet)

### 5. `frontend\` — scaffold a standard Next.js 14+ app with TypeScript and Tailwind CSS enabled. Add one page at `/` that simply says "PactScan AI — Phase 0 Scaffold" so there's something visible to confirm the frontend runs.

### 6. `README.md` (root) — must include these exact sections:
- **Project overview** (2-3 sentences)
- **Prerequisites**, with exact version numbers confirmed working on this developer's machine: Docker Desktop (WSL2 backend enabled, Docker 29.3.1+), Node.js 24.x, Python 3.14.x, Git 2.53+
- **Setup steps**, numbered, using Windows/PowerShell syntax:
  1. `git clone` the repo into `D:\PactScan-AI`
  2. `cd infra` then `docker-compose up -d`
  3. `cd ..\backend` then `copy .env.example .env` then fill in real API keys in `backend\.env`
  4. `python -m venv venv` then `venv\Scripts\Activate.ps1` then `pip install -r requirements.txt`
  5. `uvicorn app.main:app --reload`
  6. In a separate terminal: `cd frontend` then `npm install` then `npm run dev`
- **A clearly highlighted note:** "The real `.env` file must be created at `backend\.env`, copied from `backend\.env.example`. Do not create a `.env` file anywhere else in the repository — this has caused real setup failures before."
- **How to verify it's working** — hit `http://localhost:8000/health` and `http://localhost:3000`
- **Project structure** — brief explanation of each top-level folder
- **Link to phase documents** — note that `docs\` will contain the full project specification and phase-by-phase build plan

### 7. `CONTRIBUTING.md` — must include:
- **Branching model:** `main` (protected, demo-ready only), `develop` (integration branch), feature branches named `phase-N/short-description` branched off `develop`
- **Commit message format:** `type(scope): message` — list valid types (feat, fix, docs, test, chore)
- **Pull request checklist** as a literal markdown checklist:
  - [ ] Runs locally via `docker-compose up` + backend/frontend dev servers
  - [ ] New environment variables added to `backend\.env.example` (never elsewhere)
  - [ ] Relevant tests included or updated
  - [ ] No secrets or real API keys committed

### 8. `.gitignore` — standard Python + Node.js + IDE ignores, plus explicitly `backend/.env` and `**/venv/`.

---

## VERIFICATION STEPS (run these yourself before declaring Phase 0 done)

1. `cd infra` then `docker-compose up -d` then `docker ps` — confirm all three services report healthy, and confirm postgres shows port `5433->5432` in the mapping.
2. `cd ..\backend` then `copy .env.example .env` — then confirm the file exists at `backend\.env` (`dir .env`), not at the project root.
3. `python -m venv venv` then `venv\Scripts\Activate.ps1` then `pip install -r requirements.txt`
4. `uvicorn app.main:app --reload` — confirm `GET /health` returns `{"status": "ok"}` and check the startup logs for Neo4j/Postgres connection status (both should succeed, given the port-5433 fix above avoids the known collision).
5. `pytest` — confirm `test_health.py` passes.
6. `cd ..\frontend` then `npm install` then `npm run dev` — confirm `http://localhost:3000` loads and shows the placeholder text.
7. Confirm `backend\.env.example` has no real secrets, only placeholders, and confirm no `.env` or `.env.example` file exists anywhere outside `backend\`.

## EXIT CRITERIA FOR THIS PHASE
Phase 0 is complete when a person who has never seen this repository could clone it, follow `README.md` exactly, and have both backend and frontend running locally within about 30 minutes, with no undocumented steps, no port collisions, and zero ambiguity about where the `.env` file belongs. Do not proceed to Phase 1 until this is true.

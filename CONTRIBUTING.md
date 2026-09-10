# Contributing to PactScan AI

## Branching model

| Branch | Purpose |
|---|---|
| `main` | Protected. Demo-ready commits only. |
| `develop` | Integration branch. All feature branches merge here first. |
| `phase-N/short-description` | Feature branches, branched off `develop` (e.g. `phase-1/detect-agent`). |

## Commit message format

```
type(scope): message
```

Valid `type` values:

| Type | Use for |
|---|---|
| `feat` | A new feature |
| `fix` | A bug fix |
| `docs` | Documentation only |
| `test` | Adding or updating tests |
| `chore` | Tooling, deps, scaffolding, CI |

Example: `feat(detect): add PydanticAI clause extraction schema`

## Pull request checklist

- [ ] Runs locally via `docker-compose up` + backend/frontend dev servers
- [ ] New environment variables added to `backend\.env.example` (never elsewhere)
- [ ] Relevant tests included or updated
- [ ] No secrets or real API keys committed

## Testing discipline

- **Mocked tests** (`pytest` with no `-m live`): no API calls, no Docker dependency
  for LLM code. Run these repeatedly during iteration.
- **Live tests** (`pytest -m live`) and manual `curl.exe` calls: real API quota
  cost. Run once, deliberately, after mocked tests are green — not repeatedly.

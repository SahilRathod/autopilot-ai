# Architecture — Autopilot AI V0.3

Browser → Next.js 16 (apps/web, 127.0.0.1:3000) → same-origin API rewrite → FastAPI (apps/api, 127.0.0.1:8000) → app/platform_core.py → SQLite data/platform.sqlite3.

FastAPI uses Pydantic input validation and parameterized SQLite. Every channel/job route checks workspace membership; invalid approval transitions are rejected. Workspace IDs are local organizational scopes, not an authorization mechanism.

## API routes
- GET /api/v1/health
- GET, POST /api/v1/workspaces
- GET, POST /api/v1/workspaces/{id}/channels
- PATCH /api/v1/workspaces/{id}/channels/{channel_id}
- GET, POST /api/v1/workspaces/{id}/jobs
- POST /api/v1/workspaces/{id}/jobs/{job_id}/transition
- GET /api/v1/workspaces/{id}/audit
- GET /api/v1/workspaces/{id}/overview

The original gameplay CLI and data/agent.sqlite3 database remain separate; integrated production is next phase. There is no AI engine, YouTube OAuth, or live uploader.

## SaaS security boundary
No authentication. Keep servers on localhost. CORS is not an auth control. Before cloud deployment implement user sessions, tenant memberships, RBAC, server-derived tenant context, PostgreSQL/RLS and migrations, encrypted tokens, rate limiting, budget enforcement, and durable workers.

# Autopilot AI — Creator Studio V0.3

Local-first, multi-channel production management. Not yet an AI video generator or YouTube uploader.

## Features
- Next.js + TypeScript dashboard for workspaces, channel profiles, jobs, review approvals and audit history.
- FastAPI endpoints with validation, SQLite persistence, workspace scoping and OpenAPI docs.
- Original Python CLI and FFmpeg gameplay clip editor preserved.
- Zero-cost defaults and no real uploads, AI calls, or background jobs.

## Windows quick start
Requirements: Python 3.11+, Node.js >=20.9, Git. FFmpeg only for legacy clip rendering.

**Terminal 1 (repository root)**
```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r apps/api/requirements.txt
.\.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

**Terminal 2 (repository root)**
```powershell
cd apps/web
npm install
npm run dev
```

Open http://127.0.0.1:3000. API docs: http://127.0.0.1:8000/docs.

## Test
```powershell
# In repository root
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
# In apps/web after installing npm dependencies
npm run typecheck
npm run build
```

## Limitations
The servers must remain on 127.0.0.1 because authentication and real tenant isolation are not implemented. Do not deploy this base publicly. The queued/completed statuses are LOCAL workflow labels, not YouTube uploads. The original clip editor uses a separate database and is not yet connected to the new dashboard.
Read BASE_ARCHITECTURE.md and ROADMAP.md for future plans.

# Autopilot AI — AI Director V0.4

Local-first, multi-channel AI drafting and production management. Still not a YouTube video generator or uploader.

## V0.4 AI Director

- Draft title, hook, outline, script template, description, keywords, Shorts concepts and verification checklist.
- Persistent per-channel memory, SQLite drafts, 24-hour cache, offline mode and optional Gemini 2.5 Flash-Lite.
- No npm needed for Python-only AI CLI. See [V0.4 setup](V04_GUIDE.md).
- Cloud calls are off by default; draft handoff never publishes to YouTube.

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

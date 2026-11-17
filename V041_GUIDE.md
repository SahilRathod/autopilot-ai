# Autopilot AI V0.4.1 — Stability and AI Studio

## What works

- Offline content packs: **short** and **long** formats have distinct outlines and templates; stored tone and other channel notes influence generated drafts.
- Optional Gemini: single structured request; response fields checked; allowed model selection via `AUTOPILOT_GEMINI_MODEL`, default `gemini-2.5-flash-lite`. Only choose another model after confirming it exists and has the intended billing policy in your Google AI Studio project.
- Local daily request cap: `0` **disables all cloud use**, invalid/negative values fail closed. SQLite transaction protects the cap across concurrent requests. Same-event-loop duplicate requests share one in-flight Gemini call.
- AI Director screen in Next.js: choose channel, topic, provider, format; preview drafts, store a tone preference, submit to local production.
- Job content: `GET /api/v1/workspaces/{workspace_id}/jobs/{job_id}/content` returns the original stored script for linked AI jobs, with workspace isolation. Review the script in the dashboard.
- Manual FFmpeg render: records approved production job video output in the platform SQLite database. **No auto uploads**.

## Windows setup — no npm required for backend

```powershell
cd D:\AutoCopilot\autopilot-ai
git pull origin master
py -3 -m app.platform_cli init
py -3 -m app.platform_cli workspace-add "Creator Studio"
py -3 -m app.platform_cli channel-add --workspace 1 --name "Gaming" --niche gaming --language Hinglish
py -3 -m app.ai_cli remember --workspace 1 --channel 1 --key tone --value "Friendly Hinglish"
py -3 -m app.ai_cli generate --workspace 1 --channel 1 --topic "Valorant Beginner Tips" --format short
py -3 -m app.ai_cli drafts --workspace 1 --channel 1
py -3 -m unittest discover -s tests -v
```

Use **actual IDs** from command output. If workspace or channel already exists, do not recreate it.

To use FastAPI:
```powershell
.\.venv\Scripts\python.exe -m pip install -r apps/api/requirements.txt
.\.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```
Open `http://127.0.0.1:8000/docs`.

## Using the dashboard

With a working trusted npm connection, run `npm install` and `npm run dev` from `apps/web`, open `http://127.0.0.1:3000`, and select **AI Director**. This doesn't resolve the separate Windows npm TLS certificate problem: do not disable TLS verification.

The dashboard generates an **unapproved** draft production job. Move the job to `ready_for_review`, inspect its script in the Approval Center, then explicitly approve.

## Approved video render, entirely local

Place your own legal video source file inside `media/raw/`. Install FFmpeg and ffprobe, add both to PATH, and approve the job. Then:

```powershell
py -3 -m app.platform_cli render-job --workspace 1 --job 1 --source "footage.mp4" --start 0 --seconds 30
```

Files are written to `media/output/` and registered in `data/platform.sqlite3`, but they are not uploaded. The legacy database `data/agent.sqlite3` stays untouched. Failed renders release the claim and leave the approval state unchanged; a hard process crash can leave a rendering claim that needs manual recovery.

## Optional Gemini (only after checking zero-cost eligibility)

```powershell
$env:GEMINI_API_KEY = "YOUR_PRIVATE_KEY"
$env:AUTOPILOT_CLOUD_MODE = "free_only"
$env:GEMINI_FREE_TIER_CONFIRMED = "1"
$env:AUTOPILOT_DAILY_REQUEST_CAP = "10"
$env:AUTOPILOT_GEMINI_MODEL = "gemini-2.5-flash-lite"
```

These flags cannot verify Google billing status or guarantee that the model is available. Verify model access, quotas and nonbillable project status directly. Never commit credentials; avoid changing the model to one that can incur charges without explicit approval.

## Test commands

```powershell
py -3 -m unittest discover -s tests -v
cd apps/web
npm run typecheck
npm run build
```

CI runs Python unit/API tests and Next.js build. Live Gemini, real YouTube OAuth, Windows FFmpeg encoding and cross-browser E2E still require environment-specific testing.

## Known remaining limitations

- No authenticated users / SaaS-grade tenant access. Bind FastAPI to loopback only.
- No automatic uploads, publishing or video generation from a script alone.
- No live source research; offline templates are unverified drafts.
- npm lockfile and legacy database data migration require a separate verified follow-up.
- Cloud duplicate suppression applies within a single Python event loop; in multi-worker deployments the atomic daily cap still applies, but requests for the same topic may be repeated across workers.

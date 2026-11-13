# Autopilot AI Director — V0.4

V0.4 is **local-first** and **fast**. The system produces a draft content pack: title, hook, outline, script template, description, keywords, Shorts ideas, and a fact-check list. No automatic YouTube upload.

## Start without npm

From the project root (PowerShell):

```powershell
git pull origin master
py -3 -m app.platform_cli init
py -3 -m app.platform_cli workspace-add "My Studio"
py -3 -m app.platform_cli channel-add --workspace 1 --name "Gaming Hub" --niche gaming
py -3 -m app.ai_cli remember --workspace 1 --channel 1 --key tone --value "Friendly Hinglish"
py -3 -m app.ai_cli generate --workspace 1 --channel 1 --topic "Valorant beginner mistakes" --format long
py -3 -m app.ai_cli drafts --workspace 1 --channel 1
py -3 -m app.ai_cli submit --workspace 1 --channel 1 --draft 1
py -3 -m unittest discover -s tests -v
```

Use the actual workspace, channel and draft IDs returned by the commands. New AI jobs remain **unapproved drafts**. The offline engine generates a clearly labelled template, not fully researched content.

## FastAPI

Start the existing FastAPI server on `127.0.0.1:8000` and open `http://127.0.0.1:8000/docs`.
AI Director endpoints are under `/api/v1/workspaces/{workspace_id}/channels/{channel_id}/ai`:

- `GET /status`
- `GET /memory`
- `PUT /memory/{key}` with JSON `{"value":"Friendly Hinglish"}`
- `POST /generate` with JSON `{"topic":"Minecraft beginner mistakes","format":"long","provider":"offline"}`
- `GET /drafts`
- `POST /drafts/{draft_id}/submit`

## Optional Gemini cloud mode

The default is **offline** and requires no key. To use Gemini, obtain a key from a Google AI Studio project whose free-tier/billing status **you have independently verified**. Do not enable billing if your budget is strictly zero.

PowerShell environment variables, set before starting FastAPI:

```powershell
$env:GEMINI_API_KEY="YOUR_PRIVATE_KEY"
$env:AUTOPILOT_CLOUD_MODE="free_only"
$env:GEMINI_FREE_TIER_CONFIRMED="1"
$env:AUTOPILOT_DAILY_REQUEST_CAP="10"
```

Then submit with `"provider":"gemini"`. The system uses the fixed Gemini 2.5 Flash-Lite model and never silently falls back to paid providers. It sends one network request for a whole pack.

**Caution:** Local flags and rate limits cannot prove that a Google project is on a nonbillable free tier. A user-provided paid-tier key may incur charges. The local quota is per installation, not an account-level billing cap.

## Performance design

- One structured generation call per pack rather than multi-agent chained calls.
- Persistent 24-hour per-channel cache; no repeat API request for an unchanged topic, format, profile and notes.
- Pooled asynchronous connections with short timeouts.
- No heavyweight locally loaded model; offline templates are immediate.
- New drafts are saved in SQLite and submitted once to the existing review workflow.

## Current limits

No live trend research or source verification; no autonomous video editor integration, YouTube uploads, background agent executor, or secure SaaS authentication. Keep the API bound to 127.0.0.1 and do not publish it to the internet. Review facts, footage ownership and media rights before approval.
